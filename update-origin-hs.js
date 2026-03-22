import "dotenv/config";

const STORE = process.env.SHOPIFY_STORE;
const TOKEN = process.env.SHOPIFY_ACCESS_TOKEN;
const API_VERSION = "2025-01";
const ENDPOINT = `https://${STORE}.myshopify.com/admin/api/${API_VERSION}/graphql.json`;

const COUNTRY_CODE = "US"; // United States
const HS_CODE = "520849"; // 5208.49 (no dots in Shopify API)

const PRODUCTS_QUERY = `
  query GetProducts($after: String) {
    products(first: 50, after: $after) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        id
        title
        variants(first: 250) {
          nodes {
            id
            inventoryItem {
              id
              countryCodeOfOrigin
              harmonizedSystemCode
            }
          }
        }
      }
    }
  }
`;

const BULK_UPDATE_MUTATION = `
  mutation BulkUpdateVariants($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
    productVariantsBulkUpdate(productId: $productId, variants: $variants) {
      product {
        id
      }
      userErrors {
        field
        message
      }
    }
  }
`;

async function shopifyGraphQL(query, variables = {}, retries = 3) {
  for (let attempt = 1; attempt <= retries; attempt++) {
    const res = await fetch(ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": TOKEN,
      },
      body: JSON.stringify({ query, variables }),
    });

    if (res.status === 429) {
      const retryAfter = parseFloat(res.headers.get("Retry-After") || "2");
      console.warn(`⚠️  RATE LIMITED! Waiting ${retryAfter}s before retry ${attempt}/${retries}...`);
      await sleep(retryAfter * 1000);
      continue;
    }

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Shopify API error ${res.status}: ${text}`);
    }

    const json = await res.json();

    // Check for throttled errors in GraphQL response
    if (json.errors && json.errors.some(e => e.message && e.message.includes("Throttled"))) {
      console.warn(`⚠️  THROTTLED by GraphQL! Waiting 2s before retry ${attempt}/${retries}...`);
      await sleep(2000);
      continue;
    }

    if (json.errors) {
      throw new Error(`GraphQL errors: ${JSON.stringify(json.errors)}`);
    }

    // Log available query cost if present
    if (json.extensions && json.extensions.cost) {
      const cost = json.extensions.cost;
      const available = cost.throttleStatus?.currentlyAvailable;
      if (available !== undefined && available < 100) {
        console.warn(`⚠️  Low API credits: ${available} remaining. Slowing down...`);
        await sleep(1000);
      }
    }

    return json.data;
  }
  throw new Error("Max retries exceeded due to rate limiting");
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function getAllProducts() {
  const products = [];
  let after = null;
  let page = 1;

  while (true) {
    console.log(`Fetching products page ${page}...`);
    const data = await shopifyGraphQL(PRODUCTS_QUERY, { after });
    const { products: productsPage } = data;

    for (const product of productsPage.nodes) {
      // Check if any variant needs updating
      const needsUpdate = product.variants.nodes.some(
        (v) =>
          v.inventoryItem.countryCodeOfOrigin !== COUNTRY_CODE ||
          v.inventoryItem.harmonizedSystemCode !== HS_CODE
      );

      if (needsUpdate) {
        products.push({
          id: product.id,
          title: product.title,
          variants: product.variants.nodes.map((v) => ({
            id: v.id,
            currentCountry: v.inventoryItem.countryCodeOfOrigin,
            currentHS: v.inventoryItem.harmonizedSystemCode,
          })),
        });
      }
    }

    if (!productsPage.pageInfo.hasNextPage) break;
    after = productsPage.pageInfo.endCursor;
    page++;
  }

  return products;
}

async function updateProduct(product) {
  const variants = product.variants.map((v) => ({
    id: v.id,
    inventoryItem: {
      countryCodeOfOrigin: COUNTRY_CODE,
      harmonizedSystemCode: HS_CODE,
    },
  }));

  return shopifyGraphQL(BULK_UPDATE_MUTATION, {
    productId: product.id,
    variants,
  });
}

async function main() {
  console.log("=== Shopify Bulk Update: Country of Origin & HS Code ===");
  console.log(`Country of Origin: ${COUNTRY_CODE} (United States)`);
  console.log(`HS Code: ${HS_CODE} (5208.49)`);
  console.log(`Using productVariantsBulkUpdate mutation\n`);

  // Step 1: Fetch all products that need updating
  const products = await getAllProducts();
  const totalVariants = products.reduce((sum, p) => sum + p.variants.length, 0);
  console.log(`\nFound ${products.length} products (${totalVariants} variants) that need updating.\n`);

  if (products.length === 0) {
    console.log("Nothing to update. All products are already set correctly!");
    return;
  }

  // Step 2: Update each product (all its variants at once)
  let success = 0;
  let errors = 0;

  for (let i = 0; i < products.length; i++) {
    const product = products[i];
    const progress = `[${i + 1}/${products.length}]`;

    try {
      const result = await updateProduct(product);
      const userErrors = result.productVariantsBulkUpdate.userErrors;

      if (userErrors.length > 0) {
        console.error(
          `${progress} ERROR "${product.title}" (${product.variants.length} variants): ${JSON.stringify(userErrors)}`
        );
        errors++;
      } else {
        console.log(
          `${progress} Updated "${product.title}" (${product.variants.length} variants)`
        );
        success++;
      }
    } catch (err) {
      console.error(`${progress} FAILED "${product.title}": ${err.message}`);
      errors++;
    }

    // Rate limiting: ~2 requests/second
    if (i < products.length - 1) {
      await sleep(500);
    }
  }

  console.log(`\n=== Complete ===`);
  console.log(`Products updated: ${success}`);
  console.log(`Products failed: ${errors}`);
  console.log(`Total products: ${products.length}`);
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
