# Reading HAL from a JavaScript Application and Handling _embedded, _links

Spring Data REST typically returns representations in HAL (Hypertext Application Language). A HAL response contains resource data, related resources embedded inside _embedded, and navigation links inside _links.

A JavaScript application can use fetch() to read HAL JSON. When processing the response, retrieve collections from _embedded by relation name and follow the URLs in _links to open resources, fetch the next page, or discover API capabilities. This approach helps clients adapt smoothly when the server changes paths or pagination configuration.

## 1. What does a HAL representation contain?

A single resource can contain data and links:

~~~json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 120.00,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products/42"
    },
    "products": {
      "href": "http://localhost:8080/api/products"
    }
  }
}
~~~

In this representation:

- Properties id, name, and price are the resource's data.
- _links contains link relations.
- self points to the current resource.
- products points to the collection resource.

A collection response can contain items inside _embedded:

~~~json
{
  "_embedded": {
    "products": [
      {
        "id": 42,
        "name": "Mechanical Keyboard",
        "price": 120.00,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/products/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products"
    },
    "next": {
      "href": "http://localhost:8080/api/products?page=1&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 45,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Here, products is the collection's relation name; _embedded.products contains the items. _links.next points to the next page and page contains pagination metadata.

The relation name in _embedded depends on the repository rel or API configuration. Do not assume every collection uses the key products; read the actual rel published by the server.

## 2. Requesting HAL from JavaScript with fetch

When calling Spring Data REST, send the appropriate Accept header to request HAL JSON:

~~~javascript
async function getHal(url) {
    const response = await fetch(url, {
        headers: {
            Accept: "application/hal+json"
        }
    });

    if (!response.ok) {
        throw new Error("HAL request failed: " + response.status);
    }

    return response.json();
}
~~~

The getHal function performs these steps:

1. Sends an HTTP GET to the passed URL.
2. Requests the response in media type application/hal+json.
3. Checks the status code; if the response fails, throws an error.
4. Parses the response body into a JavaScript object with response.json().

If the API requires a session cookie, configure credentials appropriately, such as credentials: "include", and configure server-side CORS/credentials for the application's origin. If the API uses a bearer token, attach the Authorization header from the application's token manager; never hardcode or log tokens to the console.

Do not assume every response is HAL JSON. For endpoints returning 204 No Content or errors with a different body format, check status and Content-Type before calling response.json().

## 3. Discovering collections from the API root

Spring Data REST typically exposes an API root with links to repository resources. Instead of assembling collection paths manually, clients can read the link relation from the root:

~~~javascript
const apiRoot = await getHal("/api");

const productsLink = apiRoot._links?.products;

if (!productsLink) {
    throw new Error("Products collection link was not published");
}

const productsCollection = await getHal(productsLink.href);
~~~

This example assumes the API root is at /api and the repository rel is products. In another application, the base path or rel may differ.

Benefits of this discovery approach:

- The client only needs to know the API entry point.
- The server can change collection URLs without requiring the client to edit endpoint strings.
- The client can discover published repository resources.
- Relationships between resources are expressed as links rather than custom URL conventions in JavaScript code.

If the API root lacks a products link, check whether the repository is exported, whether rel was customized, and whether the client is calling the right base path.

## 4. Reading lists from _embedded

After loading the collection response, extract items by relation name:

~~~javascript
const page = await getHal(productsLink.href);

const products = page._embedded?.products ?? [];

for (const product of products) {
    console.log(product.id, product.name, product.price);
}
~~~

Optional chaining (?.) prevents errors when _embedded or products does not exist. The ?? operator falls back to an empty array if the collection has no embedded items.

An empty collection may omit _embedded or the corresponding relation. Therefore, clients should not access page._embedded.products directly without checking existence.

Each item in the collection can carry its own _links:

~~~javascript
for (const product of products) {
    const selfUrl = product._links?.self?.href;

    if (selfUrl) {
        console.log("Product resource:", selfUrl);
    }
}
~~~

To open product details, use the item's self link:

~~~javascript
const firstProduct = products[0];

if (firstProduct?._links?.self?.href) {
    const productDetail = await getHal(
        firstProduct._links.self.href
    );

    console.log(productDetail);
}
~~~

The client does not need to build URLs like /api/products/{id}; the self link is the resource address supplied by the server. This avoids coupling to how the server formats IDs or routes.

## 5. Following _links to navigate between pages

A paginated collection can provide links such as first, prev, self, next, and last. Not every page includes all of these links: the first page typically omits prev, and the last page omits next.

To load the next page:

~~~javascript
const currentPage = await getHal(productsLink.href);
const nextUrl = currentPage._links?.next?.href;

if (nextUrl) {
    const nextPage = await getHal(nextUrl);
    const nextProducts = nextPage._embedded?.products ?? [];

    console.log("Next page items:", nextProducts);
}
~~~

Use the href of next rather than incrementing a page parameter manually. The server-provided link preserves filter, sort, size, or other query parameters from the current request.

Similarly, you can go back to the previous page:

~~~javascript
const previousUrl = currentPage._links?.prev?.href;

if (previousUrl) {
    const previousPage = await getHal(previousUrl);
}
~~~

If the client needs to display pagination information, read metadata from page:

~~~javascript
const metadata = currentPage.page;

if (metadata) {
    console.log(
        "Page", metadata.number + 1,
        "of", metadata.totalPages,
        "- total items:", metadata.totalElements
    );
}
~~~

number in HAL page metadata is 0-based; when displaying to users, 1 is typically added so page numbers start at 1.

## 6. Sequentially loading multiple pages when truly needed

Some tasks require reading the entire collection, such as exporting data or syncing. You can follow the next link until no pages remain:

~~~javascript
async function readAllProducts(firstPageUrl) {
    const allProducts = [];
    let nextUrl = firstPageUrl;

    while (nextUrl) {
        const page = await getHal(nextUrl);
        const items = page._embedded?.products ?? [];

        allProducts.push(...items);

        nextUrl = page._links?.next?.href ?? null;
    }

    return allProducts;
}
~~~

The function above does not construct next-page URLs itself. It uses the next link in each response, preserving the server-defined query and navigation.

Do not load the entire collection into the browser just to display a list. For regular UIs, load one page, render its items, and fetch the next page only when the user requests it. For very large datasets, holding all results in memory can slow down the browser tab or exhaust memory.

When running large sync tasks, consider processing each page and persisting or forwarding batches rather than holding every item in one array.

## 7. Exploring relationships and links on an item

An item can contain links to related resources, such as category or owner:

~~~json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products/42"
    },
    "category": {
      "href": "http://localhost:8080/api/products/42/category"
    }
  }
}
~~~

The client can follow the category relation:

~~~javascript
const categoryUrl = productDetail._links?.category?.href;

if (categoryUrl) {
    const category = await getHal(categoryUrl);
    console.log(category);
}
~~~

The relation name conveys the meaning of the link. Clients should use the relation name published in the response and not assume every Product has a category link.

A relation can hold a single link object or multiple link objects depending on the representation and relationship. If the API returns an array of links for a relation, process each element instead of always assuming a single object.

## 8. Handling templated links

Some HAL links can be URI templates accompanied by a templated property:

~~~json
{
  "_links": {
    "search": {
      "href": "http://localhost:8080/api/products/search{?name,page,size}",
      "templated": true
    }
  }
}
~~~

This link is not yet a complete URL. It describes variables that can be passed, such as name, page, and size.

Do not call fetch directly with a string containing curly braces. Use an RFC 6570-compatible URI Template library or a tested template-expansion helper to generate the URL from supplied values.

Conceptual usage example:

~~~javascript
const searchLink = apiRoot._links?.search;

if (searchLink?.templated) {
    // Use a URI-template library to expand href
    // with name, page, and size before calling getHal().
}
~~~

When a link does not have templated=true, href can usually be called directly. Check the metadata instead of guessing from the URL contents.

## 9. Distinguishing _embedded and _links

These two sections serve different roles:

| Section | Contents | How the client uses it |
|---|---|---|
| _embedded | Resources or collections embedded in the current response. | Read item data directly from the response. |
| _links | Relation URLs to other resources, collections, or actions. | Discover, open resources, or navigate to other pages. |
| page | Metadata for a paginated result. | Display page number, total elements, and page size. |

Not every link has corresponding data in _embedded. A category link may only contain an href; the client must call that URL if it needs the category representation.

Conversely, an item inside _embedded typically also carries a self link so the client can open its standalone representation. Embedded data reduces requests when related data is already provided; links let the client continue navigating when more data is needed.

## 10. Error handling and response validation

A client application should handle common cases:

- 401 Unauthorized: the request lacks valid authentication credentials.
- 403 Forbidden: the user is authenticated but not permitted to access the resource.
- 404 Not Found: the resource or target link no longer exists.
- 429 Too Many Requests: the client sent too many requests within a time window.
- 5xx: server or upstream dependency error.

Error-catching example:

~~~javascript
try {
    const page = await getHal(productsLink.href);
    const products = page._embedded?.products ?? [];
    renderProducts(products);
} catch (error) {
    showError(error.message);
}
~~~

If a response returns an error status, do not assume HAL JSON paths are present. Check Content-Type and the error body according to the application's API contract.

When testing, verify that the Accept header is application/hal+json, the response Content-Type is correct, _embedded contains the expected relation, and _links contains self and appropriate pagination links. For empty collections, verify the client does not fail when _embedded is absent.

## 11. CORS and authentication in the browser

If JavaScript runs on a different origin from Spring Data REST, the browser enforces CORS. The server must allow the client's origin, methods, and request headers, including Accept and Authorization if used.

With session cookies, fetch may need credentials: "include". The server must configure Access-Control-Allow-Credentials and specific origins; never use a wildcard origin together with credentials.

With bearer tokens, add the Authorization header from the application's secure token store. Do not place tokens in URLs, log tokens, or hardcode tokens in browser source code.

CORS only controls whether the browser permits JavaScript to read responses from another origin. It does not replace authentication or authorization in Spring Security. The API must still authenticate and authorize every resource.

## 12. Common pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Missing _embedded | Empty collection, wrong relation name, or non-HAL response. | Check Content-Type, fixtures, and rel in the response. |
| products is undefined | Repository uses a different rel or has no embedded items. | Read the actual relation and use optional chaining. |
| next link does not exist | Currently on the last page or collection has only one page. | Check before navigating. |
| fetch cannot read response | CORS, authentication, or network error. | Check origin, CORS policy, cookies/tokens, and status. |
| URL contains curly braces | Client called an unexpanded URI template. | Use a URI-template library to substitute variables. |
| Manually built URL is wrong | Client hardcoded routes or dropped active query parameters. | Follow href in _links. |
| Client loads all data and slows down | Loaded every page into one large array. | Render page by page or process in batches. |
| JSON parse fails | Empty response, 204, or non-JSON body. | Check status and Content-Type before parsing. |

## 13. Client integration workflow

When connecting a JavaScript application to Spring Data REST:

1. Send GET to the API root requesting application/hal+json.
2. Read the target collection's relation from _links.
3. Call the collection's href rather than assembling endpoints manually.
4. Read items from _embedded using the actual relation name.
5. Use the item's self link to open resource details.
6. Use next or prev links to change pages.
7. Read page metadata to display pagination state.
8. Check templated=true before expanding search links.
9. Handle empty collections, missing links, error responses, and CORS.
10. Load all pages only when the use case truly requires it; prefer paged rendering for UIs.

A JavaScript client consumes HAL by requesting application/hal+json, extracting embedded resources from _embedded, and discovering URLs via _links. Rely on server-provided relation names and hrefs, check links before calling them, and use next/prev for navigation. This approach reduces coupling to internal URL structures, handles pagination consistently, and adapts better to Spring Data REST APIs.
