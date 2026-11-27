# Distinguishing URL Paths from Link Relation Names (rel)

In Spring Data REST, **path** and **rel** are two distinct configurations of a REST link. **path** determines the URL that a client calls; **rel** determines the relation name used to identify the link in a HAL document. They frequently appear side by side in annotations, yet they are not interchangeable.

Imagine an API that exposes a product collection at /api/catalog. Clients see this link in HAL under the name products. The name products is the rel; the URL /api/catalog is the href built from the path and the application's base path.

## 1. Distinguishing path and rel

| Attribute | Role | Example | Effect |
|---|---|---|---|
| path | Specifies the path segment of the resource or query in the URL. | catalog, by-category | Changes the address that clients use to access the resource. |
| rel | Names the relation for the link in HAL _links. | products, by-category | Changes the key that clients use to look up the link in the response document. |

For example, with the configuration:

~~~java
@RepositoryRestResource(
    path = "catalog",
    collectionResourceRel = "products"
)
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Spring Data REST publishes the collection resource at a URL like:

~~~text
/api/catalog
~~~

In the HAL document, the link to the collection has the relation products:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api"
    },
    "products": {
      "href": "http://localhost:8080/api/catalog"
    }
  }
}
~~~

In this example:

- catalog is the path used in the URL.
- products is the collection rel appearing under _links.
- The href value is the full URL that clients can navigate to.

If you change path to inventory, the collection URL changes to /api/inventory, while rel can remain products. Conversely, changing collectionResourceRel to items changes the link key to _links.items, while the URL stays /api/catalog.

## 2. Configuring path and collection rel at the Repository Level

@RepositoryRestResource allows configuring the path segment and relation name of the collection resource:

~~~java
@RepositoryRestResource(
    path = "catalog",
    collectionResourceRel = "products"
)
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

path specifies the URL segment dedicated to the collection. With a base path of /api, the collection resides at /api/catalog; item resources typically reside under the collection, for example /api/catalog/42.

collectionResourceRel specifies the collection's relation in HAL. Clients find the link via _links.products and then retrieve the URL from the href property.

The two values can be configured independently:

~~~java
@RepositoryRestResource(
    path = "inventory",
    collectionResourceRel = "products"
)
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

The result is the collection URL /api/inventory, while the HAL relation remains products. This is useful when you want the URL to reflect how endpoints are organized in the system while preserving a meaningful relation name for clients.

If these attributes are omitted, Spring Data REST applies default rules to generate the path and relation from the repository or domain type. When an API is consumed by multiple clients, explicit declarations make the URL contract and link names more predictable.

## 3. Configuring path and rel for Search Queries

@RestResource lets you set the path and rel for an exported repository method. For example:

~~~java
@RepositoryRestResource(
    path = "catalog",
    collectionResourceRel = "products"
)
public interface ProductRepository extends JpaRepository<Product, Long> {

    @RestResource(
        path = "by-category",
        rel = "by-category"
    )
    List<Product> findByCategoryIgnoreCase(
        @Param("category") String category
    );
}
~~~

The query has the path by-category, so the search URL has the form:

~~~http
GET /api/catalog/search/by-category?category=books
~~~

Here:

- /api/catalog is the collection path.
- /search is the repository's search resource area.
- by-category in the URL is the query path.
- by-category in HAL is the query rel.
- category=books is the query parameter value.

When a client opens /api/catalog/search, Spring Data REST returns links to the exported search queries. For example, the link might look like:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/catalog/search"
    },
    "by-category": {
      "href": "http://localhost:8080/api/catalog/search/by-category{?category}",
      "templated": true
    }
  }
}
~~~

href contains a URI template because the query requires the category parameter. The client reads the by-category rel, extracts the template from href, and fills in the parameter value to invoke the query.

You can set path and rel to different values:

~~~java
@RestResource(
    path = "category-filter",
    rel = "by-category"
)
List<Product> findByCategoryIgnoreCase(
    @Param("category") String category
);
~~~

In this case, the URL uses /search/category-filter, while the HAL link key remains by-category. Clients navigate by rel without needing to know the specific path name.

## 4. How Clients Use rel and href

In HAL, _links holds the links. Each key such as products, search, or by-category is a link relation; inside is an object describing the link, usually containing href and possibly templated.

JavaScript example reading a collection link:

~~~javascript
const response = await fetch("/api");
const api = await response.json();

const productsUrl = api._links.products.href;
const productsResponse = await fetch(productsUrl);
const products = await productsResponse.json();
~~~

This example locates the link by the products rel and then uses href to call the collection. The client does not need to hardcode /api/catalog.

Similarly, to find the query by category, a client can read the search link from the collection, open the search resource, and then read the by-category rel:

~~~javascript
const collection = await (await fetch("/api/catalog")).json();
const searchUrl = collection._links.search.href;

const search = await (await fetch(searchUrl)).json();
const categoryTemplate = search._links["by-category"].href;
~~~

If href is a URI template, the client needs a library or code snippet that expands URI templates to substitute the category parameter before sending the request. Do not send the raw {?category} string as a literal URL.

## 5. What Happens When path or rel Changes?

Path and rel are two parts of the API contract, so changing each has a different impact:

| Change | What Changes | Clients May Be Affected When |
|---|---|---|
| Change path | The URL in href changes. | Clients store old URLs or manually construct paths instead of following links. |
| Change collectionResourceRel | The collection link key in _links changes. | Clients look up the collection by the old rel name, such as _links.products. |
| Change @RestResource.path | The query URL in the search resource changes. | Clients call the old search URL directly. |
| Change @RestResource.rel | The query key in _links of the search resource changes. | Clients look up the query by the old rel, such as _links["by-category"]. |

For example, changing:

~~~java
@RepositoryRestResource(
    path = "catalog",
    collectionResourceRel = "products"
)
~~~

to:

~~~java
@RepositoryRestResource(
    path = "inventory",
    collectionResourceRel = "items"
)
~~~

will change the collection URL from /api/catalog to /api/inventory, and at the same time change the HAL key from _links.products to _links.items.

Therefore, if an API already has active clients, treat changes to path and rel as contract changes that must be communicated and coordinated. When you need to change a URL while keeping clients recognizing the same resource type, you can keep rel stable and change only path; conversely, you can keep path and change rel if you intentionally want to alter how clients identify the link.

## 6. Clear Naming Conventions

- Use short, meaningful path values that fit your URL structure, such as catalog, orders, or by-category.
- Use collectionResourceRel to describe the collection type, such as products or orders.
- Use rel on queries to describe the action or meaning of the link, such as by-category, recent, or by-name.
- Keep naming conventions consistent across repositories so clients can discover the API using uniform rules.
- Use @Param to give clear query parameter names, especially when URI templates are exposed to clients.
- Declare path and rel explicitly for important resources to avoid relying on default naming rules.

A rel name is a link relation identifier, not a mandatory display label for end users. Clients use rel to locate the right link in the HAL document; the application can decide how to present that content in the UI.

## 7. Verifying Configuration After Running the Application

After configuring the repository, you can verify using a browser, curl, or a REST client:

1. Open the root endpoint, for example GET /api, and confirm _links.products.href points to /api/catalog.
2. Call GET /api/catalog and check the collection resource along with item links.
3. Follow the search link from the collection resource.
4. In the search resource, confirm _links.by-category.href points to the query path /api/catalog/search/by-category.
5. Call the query with parameters, for example GET /api/catalog/search/by-category?category=books.
6. Try changing path or rel independently in the annotation to observe that only the corresponding URL or HAL key changes.

When verifying, inspect both the rel key and the href value. Looking only at the URL does not tell you which relation name clients must use to discover the link; looking only at the rel does not tell you where the actual endpoint lives.

## 8. Common Misconceptions

1. **Assuming path and rel are the same value.** They may share the same name, but they serve two distinct purposes.
2. **Assuming changing rel changes the URL.** Changing rel alters the link key in HAL; the URL is determined by path and the base path configuration.
3. **Assuming changing path changes the _links key.** path can change while rel stays the same.
4. **Using rel as a URL.** rel is a relation name; the target URL resides in the href property.
5. **Hardcoding URLs on the client.** Clients should discover links via rel and use href to reduce coupling to path structure.
6. **Forgetting query URI templates.** Parameterized search links typically have templated: true; clients must fill in parameters before sending the request.

Remember: path answers the question “at what address do I call the resource?”, while rel answers the question “what relation does this link represent in the HAL document?”. By separating these two concepts, you can structure URLs to fit your system while still providing meaningful, stable links to clients.
