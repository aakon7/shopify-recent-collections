import "dotenv/config";

const STORE = process.env.SHOPIFY_STORE;
const TOKEN = process.env.SHOPIFY_ACCESS_TOKEN;
const API_VERSION = "2025-01";
const ENDPOINT = `https://${STORE}.myshopify.com/admin/api/${API_VERSION}/graphql.json`;

// "Fabric" under "Arts & Entertainment > Hobbies & Creative Arts > Arts & Crafts > Art & Crafting Materials > Textiles > Fabric"
const TARGET_CATEGORY_ID = "gid://shopify/TaxonomyCategory/ae-2-1-2-14-2";

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
        category {
          id
        }
      }
    }
  }
`;

const UPDATE_MUTATION = `
  mutation UpdateProduct($input: ProductInput!) {
    productUpdate(input: $input) {
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

    if (json.errors && json.errors.some(e => e.message && e.message.includes("Throttled"))) {
      console.warn(`⚠️  THROTTLED by GraphQL! Waiting 2s before retry ${attempt}/${retries}...`);
      await sleep(2000);
      continue;
    }

    if (json.errors) {
      throw new Error(`GraphQL errors: ${JSON.stringify(json.errors)}`);
    }

    if (json.extensions && json.extensions.cost) {
      const available = json.extensions.cost.throttleStatus?.currentlyAvailable;
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
      // Check if category needs updating
      if (!product.category || product.category.id !== TARGET_CATEGORY_ID) {
        products.push({
          id: product.id,
          title: product.title,
          currentCategory: product.category?.id || "none",
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
  return shopifyGraphQL(UPDATE_MUTATION, {
    input: {
      id: product.id,
      category: TARGET_CATEGORY_ID,
    },
  });
}

async function main() {
  console.log("=== Shopify Bulk Update: Product Category ===");
  console.log(`Target Category: Fabric (Textiles)`);
  console.log(`Category ID: ${TARGET_CATEGORY_ID}\n`);

  const products = await getAllProducts();
  console.log(`\nFound ${products.length} products that need category update.\n`);

  if (products.length === 0) {
    console.log("Nothing to update. All products already have the correct category!");
    return;
  }

  let success = 0;
  let errors = 0;

  for (let i = 0; i < products.length; i++) {
    const product = products[i];
    const progress = `[${i + 1}/${products.length}]`;

    try {
      const result = await updateProduct(product);
      const userErrors = result.productUpdate.userErrors;

      if (userErrors.length > 0) {
        console.error(`${progress} ERROR "${product.title}": ${JSON.stringify(userErrors)}`);
        errors++;
      } else {
        console.log(`${progress} Updated "${product.title}"`);
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
