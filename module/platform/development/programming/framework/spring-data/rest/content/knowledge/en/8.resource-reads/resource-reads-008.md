# Practice: Following Links from a Collection to a Single Resource

## 1. Lab objectives

In Spring Data REST, a collection resource represents the set of entities of a repository, while an item resource represents a specific entity. For example, a customer collection may contain many customers; each customer has its own resource for reading or updating.

This lab follows the hypermedia flow from a collection to an item:

1. Send a request to fetch the collection resource.
2. Read the entities embedded in the HAL response.
3. Extract the `self` link of the entity to open.
4. Send a request to that link's `href` to fetch the single resource.
5. Handle empty collections, items missing links, or failed requests.

The client obtains the item URL from the server's response. The client does not construct the URL by concatenating the collection name with the ID, such as `/customers/42`.

## 2. Preparing the sample API

Suppose a Spring Data REST application has a repository:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

If the repository is exposed with the collection relation `customers`, the collection endpoint can be expressed as:

    GET http://localhost:8080/customers
    Accept: application/hal+json

The `/customers` path is only an example. An application may configure a different base path, path, or `collectionResourceRel`. In this lab, use the collection URL provided by the API root or your application's environment configuration.

HAL is a JSON format representing resources and hypermedia links. A collection response typically contains:

- **_embedded**: entities embedded in the collection.
- **_links**: collection links, such as `self`, `profile`, or pagination links.
- **page**: pagination information when the collection is paginated.

An illustrative response:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers"
        },
        "profile": {
          "href": "http://localhost:8080/profile/customers"
        }
      },
      "_embedded": {
        "customers": [
          {
            "name": "An",
            "email": "an@example.com",
            "_links": {
              "self": {
                "href": "http://localhost:8080/customers/42"
              }
            }
          },
          {
            "name": "Binh",
            "email": "binh@example.com",
            "_links": {
              "self": {
                "href": "http://localhost:8080/customers/57"
              }
            }
          }
        ]
      },
      "page": {
        "size": 20,
        "totalElements": 2,
        "totalPages": 1,
        "number": 0
      }
    }

In this example, `customers` is the collection relation. Each element in the `_embedded.customers` array is a representation of a customer and has a `_links.self.href` link pointing to the corresponding item resource.

The relation name in `_embedded` depends on the API configuration. If the application changes `collectionResourceRel`, this key may also change. Do not assume every collection has the key `customers`.

## 3. Step 1 — Fetch the collection resource

You can observe the response using curl:

    curl -i \
      -H "Accept: application/hal+json" \
      http://localhost:8080/customers

The `Accept` header asks the server to return a HAL JSON representation. Inspect the status code, `Content-Type`, and body. When the request succeeds, the body typically contains `_embedded` along with links.

If you receive `404 Not Found`, check whether the collection endpoint is correct and whether the repository is exposed by Spring Data REST. If you receive `401 Unauthorized` or `403 Forbidden`, appropriate authentication or access permissions are needed. These errors are not evidence that the link-following approach is wrong.

## 4. Step 2 — Select an entity in the collection

Suppose the client needs to open the first customer. First, retrieve the list of entities from `_embedded`:

    const customers = collection._embedded?.customers ?? [];

    if (customers.length === 0) {
      console.log("The collection currently has no customers.");
      return;
    }

    const selectedCustomer = customers[0];

In the snippet above, `customers` is the example's collection relation name. For another API, the client must use the corresponding relation in the response.

Do not take the ID from a data field and concatenate the URL:

    const customerUrl = "/customers/" + selectedCustomer.id;

This approach depends on the path name and how the server represents IDs. An entity may use a UUID, slug, or another identifier; the server may also change URLs without changing resource semantics.

## 5. Step 3 — Extract the item's self link

Each embedded entity typically has `_links.self`. This is the link to the standalone representation of that entity:

    const selfLink = selectedCustomer._links?.self;

    if (!selfLink?.href) {
      throw new Error("Entity has no self link.");
    }

The `href` value is a server-provided URI. It may be an absolute URL or a relative URI. When needed, the client can resolve a relative URI against the URL of the collection response:

    const itemUrl = new URL(selfLink.href, collectionUrl);

`new URL(...)` properly handles combining a relative URI with a base URL. Do not concatenate strings manually, as that can produce broken paths when URLs include a base path or slashes.

`self` is the relation commonly used to refer to the current resource. The client can follow this link without knowing whether the server constructed the item URL from an ID or another routing rule.

## 6. Step 4 — Send a request to fetch the single resource

Once you have `href`, send a new request to that link:

    const itemResponse = await fetch(itemUrl, {
      headers: {
        Accept: "application/hal+json"
      }
    });

    if (!itemResponse.ok) {
      throw new Error(
        "Unable to load customer: HTTP " + itemResponse.status
      );
    }

    const customerDetail = await itemResponse.json();

A single resource typically returns the entity's properties and related links. Example:

    {
      "name": "An",
      "email": "an@example.com",
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers/42"
        },
        "orders": {
          "href": "http://localhost:8080/customers/42/orders"
        }
      }
    }

The client can continue navigating from this representation. If orders are needed, read the `orders` relation and follow its corresponding `href` when that link is published. There is no need to guess association endpoints.

## 7. Complete example using JavaScript fetch

The following example combines the steps into a single flow. Replace `collectionUrl` and the collection relation with values appropriate for your application's API.

    async function loadFirstCustomer(collectionUrl) {
      const collectionResponse = await fetch(collectionUrl, {
        headers: {
          Accept: "application/hal+json"
        }
      });

      if (!collectionResponse.ok) {
        throw new Error(
          "Collection request failed: " + collectionResponse.status
        );
      }

      const collection = await collectionResponse.json();

      // This relation is an example; use the actual key in _embedded.
      const customers = collection._embedded?.customers ?? [];

      if (customers.length === 0) {
        return null;
      }

      const customer = customers[0];
      const selfHref = customer._links?.self?.href;

      if (!selfHref) {
        throw new Error("Customer representation has no self link");
      }

      // Supports both absolute and relative hrefs.
      const itemUrl = new URL(selfHref, collectionResponse.url);

      const itemResponse = await fetch(itemUrl, {
        headers: {
          Accept: "application/hal+json"
        }
      });

      if (!itemResponse.ok) {
        throw new Error(
          "Item request failed: " + itemResponse.status
        );
      }

      return await itemResponse.json();
    }

    const customer = await loadFirstCustomer(
      "http://localhost:8080/customers"
    );

    console.log(customer);

The function above returns `null` when the collection is empty; if the collection has entities, it returns the representation of the first item. In a real application, the collection URL should be obtained from the entry point or environment configuration, and the relation name should be determined from the API contract.

## 8. Distinguishing a collection's self link from an item's self link

Both a collection and an item can have a `self` relation, but the two links point to two different resources:

| Location | `_links.self.href` points to | Purpose |
|---|---|---|
| Collection response | The collection itself | Reload the current collection |
| Entity inside `_embedded` | The entity's single resource | Read or operate on the item |

Example:

- `collection._links.self.href` points to `/customers`.
- `collection._embedded.customers[0]._links.self.href` points to an item, such as `/customers/42`.

Do not take `self` at the collection level and use it as the item URL. Extract the `self` link inside the specific entity you want to open.

## 9. Paginated collections and multiple items

When a collection has more entities than the page size, the server may return only a portion of the data. The client can iterate over the entities on the current page and follow the `next` link to fetch the next page if that link exists.

Example:

    const nextHref = collection._links?.next?.href;

    if (nextHref) {
      const nextPageResponse = await fetch(
        new URL(nextHref, collectionResponse.url),
        {
          headers: {
            Accept: "application/hal+json"
          }
        }
      );

      if (!nextPageResponse.ok) {
        throw new Error("Unable to load the next page");
      }

      const nextPage = await nextPageResponse.json();
    }

For each item on a page, follow the same process: read `item._links.self.href`, resolve the URI, and send a request if the client needs the full representation. Reloading the item is not always necessary; the collection response may already contain enough fields for the UI. Only call the item endpoint when detailed data or item-specific operations are needed.

## 10. Common errors and how to handle them

**Reading the wrong self link**

If you extract `_links.self` from the collection, the next request just reloads the collection. Extract `_links.self` from the entity inside `_embedded`.

**Entity has no self link**

Do not manually build a URL from the ID as a workaround. Check whether the response is valid HAL, whether the entity is a Spring Data REST representation, and whether the server exposes that link. If the API does not provide the link, handle it as a missing capability in the API contract.

**Using the wrong key in _embedded**

Keys like `customers` depend on the collection relation. Inspect the actual response or use metadata/API contracts to know the relation. Do not assume the Java class name is always the key.

**Relative href**

If `href` is not an absolute URL, resolve it against the current response's URL using a URL resolver. Do not concatenate paths by hand.

**Item request rejected**

401 usually relates to authentication; 403 relates to access permissions; 404 may mean the resource no longer exists or the route is invalid. Handle according to the status code and the application's security policy.

**Stale collection data**

An entity may be deleted between the time the client loads the collection and the time it follows the `self` link. Therefore, item requests still need to check the status code; do not assume an item always exists simply because it appeared in the collection.

## 11. Practice exercises

Using a Spring Data REST application with at least two customers:

1. Send GET to the collection endpoint with `Accept: application/hal+json`.
2. Locate `_embedded` and identify the key containing the customers.
3. Select the second entity in the collection.
4. Read `_links.self.href` of that entity.
5. Send GET to the extracted `href` and verify the response is a single resource.
6. Compare `self` at the collection level with `self` at the entity level.
7. Test with an empty collection or a deleted entity to observe how the client handles it.

Self-check questions:

- Why should clients avoid building item URLs by concatenating IDs?
- Which `self` link points to the collection, and which points to the item?
- If `href` is relative, which URL should the client resolve it against?
- When an entity appears in a collection but is deleted before the next request, how should the client handle it?

## 12. Key takeaways

- A collection resource represents a set; an item resource represents a specific entity.
- Entities in `_embedded` can provide a `self` link pointing to the single resource.
- Extract the `self` link from the specific entity to open, not the collection's `self` link.
- Use the `href` returned by the server; do not hardcode URLs from IDs or repository names.
- Resolve relative `href` values against the response URL.
- Check status codes and handle empty collections, missing links, deleted items, or rejected requests.
- Only fetch an individual item separately when detailed representations or item-specific operations are needed.

## References

- Spring Data REST Reference: https://docs.spring.io/spring-data/rest/reference/
- Spring HATEOAS Reference: https://docs.spring.io/spring-hateoas/docs/current/reference/html/
- HAL specification: https://stateless.group/hal_specification.html
