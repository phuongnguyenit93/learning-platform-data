# Discovering Resources from the API Root Instead of Hard-Coding URLs

## 1. Why Should Clients Start from the API Root?

When building a client for Spring Data REST, you typically know the service's root URL, such as `http://localhost:8080/`. However, you should not infer the remaining endpoints by concatenating strings like `/customers`, `/customers/42`, or `/customers/search/findByEmail`.

Paths are an implementation detail of the API. They can change when the server configures `path`, `collectionResourceRel`, renames a repository, restructures resources, or moves the service to another version. If a client constructs URLs manually, every such change can force the client to be modified and re-released.

Spring Data REST uses hypermedia to publish the links a client can follow. The client fetches the API root, reads the links returned by the server, selects a link by its relation (commonly called `rel`), and continues exploring resources. This follows the HATEOAS principle: API responses provide the information the client needs to navigate to the next state.

The client still needs to know the API root and the business meaning of the operation it wants to perform. Beyond that starting point, the client should use the relations and URLs provided by the server instead of guessing path structures.

## 2. HAL and HATEOAS in Spring Data REST

**HATEOAS** (Hypertext as the Engine of Application State) is a design principle in which resources return links describing the next steps a client can take. Clients navigate via these links rather than depending on a fixed URL layout.

**HAL** (Hypertext Application Language) is a popular JSON format for representing resources and hypermedia links. Spring Data REST typically returns HAL JSON with the media type:

    application/hal+json

A HAL document typically has two notable sections:

- `_links`: links to related resources, grouped by link relation.
- `_embedded`: resources embedded in the response, commonly appearing in collection resources.

Illustrative example of a response at the API root:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/"
        },
        "profile": {
          "href": "http://localhost:8080/profile"
        },
        "customers": {
          "href": "http://localhost:8080/customers"
        }
      }
    }

In this example, `customers` is the relation leading to the customer collection resource. This is only an illustrative example: the actual rel depends on the application's configuration and metadata. The client must read the keys and `href` in the actual response, and should not assume every application uses the name `customers`.

A link can contain additional properties such as `templated`, `type`, `title`, or `deprecation`. Clients should rely on the HAL format and a hypermedia library to process those properties rather than treating every link value as just a plain URL string.

## 3. Discovering Collections from the API Root

The basic workflow consists of these steps:

1. Send a request to the configured API root.
2. Request HAL JSON using the `Accept: application/hal+json` header.
3. Read the `_links` object in the response.
4. Find the link by the rel the client needs, such as the rel representing the customer collection.
5. Send a request to that link's `href` value.

Example using JavaScript `fetch` in a browser or Node environment with fetch support:

    const rootResponse = await fetch("http://localhost:8080/", {
      headers: { Accept: "application/hal+json" }
    });

    if (!rootResponse.ok) {
      throw new Error("Unable to load API root: " + rootResponse.status);
    }

    const root = await rootResponse.json();

    // "customers" is an illustrative rel only; use the actual rel returned by the server.
    const customersLink = root._links.customers;

    if (!customersLink) {
      throw new Error("API root does not publish the customers rel");
    }

    const customersResponse = await fetch(customersLink.href, {
      headers: { Accept: "application/hal+json" }
    });

    if (!customersResponse.ok) {
      throw new Error("Unable to load customers collection");
    }

    const customersPage = await customersResponse.json();

This code only hard-codes the API root URL. The collection URL is taken from the `href` of the link returned by the server. In a real application, the rel to use must be defined by the API's hypermedia contract; if the server changes the path while keeping the rel, the client can still follow the new link.

Do not write:

    const customers = await fetch("http://localhost:8080/customers");
    const customer = await fetch("http://localhost:8080/customers/42");

Those two URLs force the client to know the path structure and how the server generates resource identifiers in advance.

## 4. Following a Link to a Specific Resource

A HAL collection response typically has `_embedded` containing items, along with the collection's links. Example:

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
          }
        ]
      },
      "page": {
        "size": 20,
        "totalElements": 1,
        "totalPages": 1,
        "number": 0
      }
    }

If the client wants to open the details of the first customer, retrieve the item's `self` link:

    const customer = customersPage._embedded.customers[0];
    const customerSelfLink = customer._links.self;

    const detailResponse = await fetch(customerSelfLink.href, {
      headers: { Accept: "application/hal+json" }
    });

    const customerDetail = await detailResponse.json();

In this example, the client does not assemble `/customers/42` itself. The server retains the freedom to change item URLs; the client continues working as long as the server provides a valid `self` link.

`_embedded` and the collection name inside it must also be read according to the actual response. Do not assume every collection is always named `_embedded.customers` if the application's rel is configured differently.

## 5. Discovering Search Capabilities via the `search` Rel

Spring Data REST can expose repository query methods under a search resource. Instead of guessing a finder's URL, the client should:

1. Read the `search` link from the collection response.
2. Follow that link to retrieve the list of published finders.
3. Select a finder by its rel.
4. Use the URL template provided by the server to pass parameters.

For example, the search resource may return:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers/search"
        },
        "findByEmail": {
          "href": "http://localhost:8080/customers/search/findByEmail{?email}",
          "templated": true
        }
      }
    }

The `templated: true` property indicates that `href` is a URI template. The `{?email}` portion describes an expandable query parameter. The client must use a URI-template expander or hypermedia library to substitute parameters properly, including encoding characters in values.

For example, with Spring HATEOAS `Traverson`, the client can navigate along a chain of rels and pass parameters to the template:

    Traverson traverson = new Traverson(
        URI.create("http://localhost:8080/"),
        MediaTypes.HAL_JSON
    );

    CollectionModel<EntityModel<Customer>> result =
        traverson.follow("customers", "search", "findByEmail")
            .withParameter("email", "an@example.com")
            .toObject(new ParameterizedTypeReference<>() {});

The `customers`, `search`, and `findByEmail` rels in the code snippet are examples. Use the exact rels that appear in the application's HAL responses. The target return type must also match the actual finder result type; a finder returning a single item and a finder returning a collection have different response structures.

Do not assemble URLs like this:

    const url =
      "http://localhost:8080/customers/search/findByEmail?email=" +
      email;

This approach assumes the path, finder name, and parameter name never change. It also easily produces malformed URLs if the value contains `&`, `?`, or Unicode characters.

## 6. Following Pagination Links and Association Links

Large collections are typically returned page by page. A HAL response may contain pagination metadata in `page` and navigation links such as `first`, `prev`, `self`, `next`, or `last`, depending on the response and configuration.

The client should follow the `next` link if it is provided:

    const nextLink = customersPage._links.next;

    if (nextLink) {
      const nextResponse = await fetch(nextLink.href, {
        headers: { Accept: "application/hal+json" }
      });
      const nextPage = await nextResponse.json();
    }

If there is no `next` link, the client should not assume a next page exists. The `page` metadata can help display page number information, but the navigation links from the server are the authoritative instructions for moving forward.

An item resource can also contain links to related resources, such as addresses, orders, or an association. The client can use that rel to follow along without needing to know what path the association is mapped to.

## 7. Important Link Relations and How to Understand Them

| Relation or property | Common meaning |
|---|---|
| `self` | Link to the current resource itself |
| `profile` | Link to the resource's profile description |
| `search` | Link to the collection's search resource |
| `next` / `prev` | Navigation to the next or previous page when provided |
| `_embedded` | Resources embedded in the representation |
| `href` | Address of the link |
| `templated` | Indicates that href is a URI template requiring expansion |

A rel is an identifier for the relationship between the current resource and the target resource. Some rels are standard relations; others are defined by the application. Do not treat a rel name as a path. `customers` may be the key of a link, while `href` contains the actual URI for the client to access.

Rel names and response structure depend on the server. For example, `@RepositoryRestResource(collectionResourceRel = "people")` can make a collection's rel differ from the default name. This is an important reason for clients to discover links from the API root instead of hard-coding URLs.

## 8. Designing Resilient Clients

A well-designed HATEOAS client generally follows these principles:

- Only configure the API root or entry point address per environment.
- Request the hypermedia media type supported by the API, such as `application/hal+json`.
- Select links by meaningful rels, then access the `href` provided by the server.
- Use a URI-template expander for links with `templated: true`; do not manually perform string substitution.
- Follow the `self` link to open items and follow pagination links if provided.
- Handle missing links, error responses, or unexpected media types gracefully.
- Do not assume every link is always present in every state of a resource.
- Do not depend on JSON key ordering or the position of a link in an array.

Using rels does not mean the client needs no business understanding. The client still needs to know which operation suits the user's task and which rel in the API contract represents that operation. Hypermedia helps the client find the address and next step published by the server.

The API root is the known entry point; the remaining resources are discovered progressively from responses. If the server changes a collection path while still providing the same rel, the client can keep working without updating hard-coded URLs.

## 9. Common Mistakes

**Constructing paths from entity or repository names**

The client assumes the class name `Customer` always corresponds to `/customers`. However, `path` and `collectionResourceRel` can be configured differently. Use the rels and hrefs from the response.

**Using templated links as complete URLs**

A link with `templated: true` contains placeholders. Sending a request directly with unexpanded placeholders can result in an invalid URL. Expand templates using a compliant library.

**Reading data from the wrong location**

Collection items usually live in `_embedded`; navigation links live in `_links`. Do not assume items always reside in a fixed property outside HAL.

**Assuming every rel is always present**

A repository might not expose a search resource, a collection might have no next page, or an association might not be exposed. Clients must handle missing links as a normal state.

**Confusing profile with business endpoints**

The `profile` link describes the resource's profile; it is not necessarily an endpoint for reading or updating an entity.

**Testing only by opening URLs in a browser**

Being able to open a URL does not prove the client discovered the relation properly. Inspect the HAL response, media type, rels, and link templates to understand how the API guides clients.

## 10. Practicing with Spring Data REST

Suppose an application exposes a `CustomerRepository` and the API root is `http://localhost:8080/`.

1. Send `GET /` with `Accept: application/hal+json`.
2. Note the rels in `_links` and identify the customer collection rel.
3. Follow the collection rel's href to retrieve the HAL collection response.
4. Locate an item in `_embedded`, then follow the item's `self` link.
5. Look for the `search` link if the collection exposes search.
6. Follow a finder link; if the link has `templated: true`, expand the template with valid parameters.
7. If the response has `next`, follow that link to retrieve the next page.

You can use `curl` to observe the HAL response:

    curl -i -H "Accept: application/hal+json" http://localhost:8080/

Then inspect the returned hrefs to understand the next step. In a real client, navigation must be performed by code that reads rels and hrefs rather than relying on manual URL copying.

## 11. Key Takeaways

- HATEOAS allows clients to drive application state through links provided by the server.
- HAL represents links in `_links` and embedded resources in `_embedded`.
- The API root is the entry point; clients discover collections, items, search, and related resources from responses.
- Use rels to find the needed relationship type and use the href returned by the server to send requests.
- Links with `templated: true` must be expanded properly.
- Follow pagination and association links when published in the response.
- Do not hard-code URLs for resources behind the API root.

## References

- Spring Data REST Reference: https://docs.spring.io/spring-data/rest/reference/
- Spring HATEOAS Reference — Traverson client: https://docs.spring.io/spring-hateoas/docs/current/reference/html/
- HAL specification: https://stateless.group/hal_specification.html
