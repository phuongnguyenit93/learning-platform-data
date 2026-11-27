# The Role of Resources, Representations, Links, and HTTP Methods in Spring Data REST

Spring Data REST turns Spring Data repositories into a REST API discoverable via hypermedia. Repositories provide data operations; Spring Data REST exposes appropriate operations as resources, builds JSON representations for those resources, and adds links so clients can find their way forward. Therefore, when reading a Spring Data REST response, you need to understand simultaneously **which resource is being accessed**, **what the representation describes**, **where the links lead**, and **which action the HTTP method is requesting**.

## 1. Four core concepts

| Concept | Meaning | Question to answer |
|---|---|---|
| Resource | An object or set of objects identified by a URI and accessible over HTTP | Is the client working with a collection, item, association, or search resource? |
| Representation | Data describing the state of a resource at response time, usually in JSON/HAL format | Which data fields, links, and metadata are being returned? |
| Link | A URI attached to a relation for the client to discover related resources or actions | Which URI should the client follow next and what does that URI mean? |
| HTTP method | Semantics of the operation the client sends to the resource | Does the client want to read, create, replace, partially update, delete, or modify a relationship? |

These concepts are related but do not replace one another. For example, a product resource has URI `/products/1`; its representation may contain name and price; the `category` link points to the category relationship resource; `GET` reads that representation while `PATCH` changes part of its state.

## 2. How are repositories exposed as resources?

Spring Data REST detects repositories allowed to be exported and maps them to endpoints. A repository typically extends `CrudRepository`, `PagingAndSortingRepository`, or `JpaRepository`. Existing repository methods determine which HTTP operations can be exposed.

Suppose the application has a `Product` entity and the following repository:

~~~java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "products",
    collectionResourceRel = "products",
    itemResourceRel = "product"
)
public interface ProductRepository extends JpaRepository<Product, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    List<Product> findByNameContainingIgnoreCase(@Param("name") String name);
}
~~~

This is a repository declaration, not a standalone program: the `Product` entity, Spring Boot configuration, and Spring Data REST dependency must exist in the application. The repository above allows Spring Data REST to expose the product collection, individual products, and the query method searching by name. The `RepositoryRestResource` annotation customizes the path and relation names; `RestResource` customizes the path and relation of the query method.

If no path is specified, Spring Data REST typically derives the collection path from the domain class's simple name after lowercasing and pluralizing it. You can set a base path, such as `spring.data.rest.base-path=/api`; the root and endpoints will then reside under `/api`.

Common resource types:

- **Root resource**: the entry point of the API, usually `/` or the configured base path. It returns links to exported repositories.
- **Collection resource**: represents a set of entities, for example `/products`.
- **Item resource**: represents a specific entity, for example `/products/1`.
- **Association resource**: represents a relationship of an item, for example `/products/1/category`.
- **Search resource**: exposes repository query methods, for example `/products/search`; each query method has its own endpoint.

The paths above are examples. Repository names, annotations, base path, and application configuration determine the actual URIs. Clients should discover links returned by the server rather than inferring every path manually.

## 3. Resource representations: JSON and HAL

Spring Data REST uses HAL (Hypertext Application Language) by default to represent resources. Clients typically request HAL using the `Accept: application/hal+json` header. Endpoints also support `application/json` for operations documented by Spring Data REST.

A HAL document typically has three parts:

- `_links`: links named by relation. Each link has an `href`; a link can be a URI template, in which case it also includes `templated: true`.
- `_embedded`: related resources embedded directly in the representation, commonly used for collection elements.
- `page`: pagination metadata such as page size, total elements, total pages, and current page index.

Example root response:

~~~json
{
  "_links": {
    "products": {
      "href": "http://localhost:8080/products"
    }
  }
}
~~~

The client learns about the product collection via the `products` relation. It does not need to build the URI from a naming convention.

Example collection response:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/products"
    },
    "search": {
      "href": "http://localhost:8080/products/search"
    }
  },
  "_embedded": {
    "products": [
      {
        "name": "Keyboard",
        "price": 1290000,
        "_links": {
          "self": {
            "href": "http://localhost:8080/products/1"
          },
          "category": {
            "href": "http://localhost:8080/products/1/category"
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
~~~

This is an illustrative example of data shape; the `category` link only appears if the domain model has a corresponding association exposed by Spring Data REST. The relation inside `_embedded` typically comes from `collectionResourceRel` or repository naming conventions.

Example item representation:

~~~json
{
  "name": "Keyboard",
  "price": 1290000,
  "_links": {
    "self": {
      "href": "http://localhost:8080/products/1"
    },
    "category": {
      "href": "http://localhost:8080/products/1/category"
    }
  }
}
~~~

By default, an entity's ID is not included as a regular JSON property. The `self` link already provides the URI identifying the resource. If the API contract requires the ID to appear in the payload, you can configure `RepositoryRestConfiguration.exposeIdsFor(Product.class)`. Enable this only when the client genuinely needs it; an ID in the payload and the resource URI are two different ways of representing identity.

A representation is not necessarily a verbatim copy of the entity or table structure. It can vary based on projections, excerpts, Jackson configuration, and application customizations. Therefore, you should not treat every Java property as a guarantee that the property will always appear in JSON.

## 4. Links and how clients discover the API

Spring Data REST applies the HATEOAS principle: responses provide links so clients can discover the next resource. A client starts at the root, reads the needed relation, calls the URI in `href`, and continues following newly received links.

A typical flow:

1. Send `GET` to the root to find the `products` relation.
2. Follow `products.href` to retrieve the collection.
3. Read elements in `_embedded.products`; follow an element's `self.href` to retrieve the item.
4. Follow the `category` relation to access the association.
5. Follow the `search` relation to find query methods; follow a query method's link to execute a search.
6. When a response includes `next`, `prev`, or a URI template, use that link directly to paginate or fill parameters.

A link has two key parts: **relation** describes the link's role, while **href** specifies the target URI. The `self` relation points to the current resource itself. The `products` relation can point to the collection; the `category` relation can point to the association. Relation names can be customized with annotations.

For associations, representation depends on whether the related object has an exported repository. If it has a repository, the relationship is typically represented by a link so the client can access the related resource. If not, the related object's data may be embedded directly. Therefore, do not assume every relationship is a nested JSON object or every relationship is a separate endpoint.

HATEOAS makes clients less dependent on specific URL structures. If the server changes the base path or customizes a repository path while continuing to publish appropriate relations, the client knows how to proceed by reading the new links. That only works when the client actually follows links rather than hard-coding URIs.

## 5. Role of HTTP methods

HTTP methods apply according to the resource type. The table below describes common default behavior; actual operations still depend on whether repository methods are exported and on application configuration.

| Resource | Method | Role |
|---|---|---|
| Collection `/products` | GET | Read list; may include pagination and sorting |
| Collection `/products` | POST | Create a new entity from the request body |
| Item `/products/{id}` | GET | Read a single entity |
| Item `/products/{id}` | PUT | Replace resource state with the request body |
| Item `/products/{id}` | PATCH | Partially update state |
| Item `/products/{id}` | DELETE | Delete the entity identified by the URI |
| Association `/products/{id}/category` | GET | Read relationship state |
| Association `/products/{id}/category` | PUT | Bind the URI of a related resource to the association |
| Collection association | POST | Add an element to the association |
| Association | DELETE | Remove the association link |
| Search/query resource | GET | Execute an exported query method |

### GET

`GET` reads a resource and should not alter business state. For a collection, the result may be a single page rather than all data. For an item, the result is the representation of one entity. For a search resource, `GET` returns links to query methods; `GET` on a query method executes the query.

### POST

`POST` on a collection creates a new entity from the request body. When creation succeeds, the server usually returns `201 Created` and a `Location` header pointing to the new resource's URI. The response body may be returned or empty depending on `Accept` and return-body-on-create configuration. If there is no body, the client can follow `Location` to read the new representation.

`POST` on a collection association has a different meaning: it adds a related URI to the collection association. Do not confuse this operation with creating a new entity in the repository.

### PUT

`PUT` on an item replaces the resource state with the submitted data. Clients should send a complete representation per the API contract; properties omitted from the request may be treated as absent in the new state. `PUT` is generally suitable when the client knows the entire state to write. Spring Data REST may also return `201 Created` if a `PUT` flow creates a new resource; check the actual status and `Location`.

`PUT` on an association binds the URI of a related resource. One-to-one or many-to-one associations typically accept a single URI; sending multiple URIs for a to-one relationship may result in `400 Bad Request`. The media type for association requests is `text/uri-list`, unlike the JSON body used to update an entity.

### PATCH

`PATCH` updates part of an item's state. Properties not present in the request are generally preserved. Spring Data REST supports media types such as `application/merge-patch+json` and `application/patch+json` alongside supported JSON formats. Send the `Content-Type` appropriate for the patch format the client uses.

### DELETE

`DELETE` on an item deletes the entity. `DELETE` on an association removes the relationship between two resources; it does not mean deleting the entity on the other side of the relationship. Whether deleting an entity also deletes related data depends on mappings, cascades, and application business rules.

### HEAD and response codes

`HEAD` can be used to check whether a resource is available without fetching the body. Allowed methods depend not only on HTTP in general, but also on the resource and exported repository methods. If the repository lacks the corresponding method or the method is hidden, Spring Data REST may return `405 Method Not Allowed`.

Some common status codes:

- `200 OK`: read succeeded; can also be used for updates when the server returns a body.
- `201 Created`: resource created successfully, usually accompanied by `Location`.
- `204 No Content`: update or delete succeeded, but the server returns no body.
- `400 Bad Request`: invalid request body, association URI, or input data.
- `404 Not Found`: the URI does not point to an existing resource.
- `405 Method Not Allowed`: the resource does not support that method or the corresponding repository operation is not exported.

For `PUT`, `PATCH`, and `DELETE`, whether `200` or `204` is returned depends on return-body configuration and the `Accept` header. Do not write clients that assume every update always returns JSON.

## 6. Sending requests and reading responses

The following examples assume the application runs at `http://localhost:8080`, the repository is exported as collection `/products`, and the entity has `name` and `price` properties.

Read root and collection:

~~~bash
curl -i -H 'Accept: application/hal+json' http://localhost:8080/
curl -i -H 'Accept: application/hal+json' http://localhost:8080/products
~~~

Create a product:

~~~bash
curl -i -X POST http://localhost:8080/products -H 'Content-Type: application/json' -H 'Accept: application/hal+json' -d '{"name":"Keyboard","price":1290000}'
~~~

Read, replace, partially update, and delete an item:

~~~bash
curl -i -H 'Accept: application/hal+json' http://localhost:8080/products/1
curl -i -X PUT http://localhost:8080/products/1 -H 'Content-Type: application/json' -H 'Accept: application/hal+json' -d '{"name":"Keyboard Pro","price":1590000}'
curl -i -X PATCH http://localhost:8080/products/1 -H 'Content-Type: application/merge-patch+json' -H 'Accept: application/hal+json' -d '{"price":1490000}'
curl -i -X DELETE http://localhost:8080/products/1
~~~

Replace URIs and data according to the actual application. The `PUT` request in the example sends both `name` and `price`; the `PATCH` request sends only `price`, illustrating partial update semantics. Specific results also depend on validation, security, return-body configuration, and data state.

Bind an existing category to a product via the association:

~~~bash
curl -i -X PUT http://localhost:8080/products/1/category -H 'Content-Type: text/uri-list' --data 'http://localhost:8080/categories/3'
~~~

The association path comes from the `category` link in the item representation. The target URI must be the URI of an exported related resource. For a collection association, `POST` with media type `text/uri-list` can add a URI to the collection; `DELETE` on the association removes the link.

## 7. Pagination, sorting, and searching

If the repository supports `Pageable` or `Sort`, the collection resource accepts these parameters:

- `page`: page number, starting from `0`.
- `size`: number of elements requested per page; the default is usually `20`.
- `sort`: property and sort direction, for example `name,asc` or `price,desc`.

Example:

~~~bash
curl -i -H 'Accept: application/hal+json' 'http://localhost:8080/products?page=0&size=10&sort=name,asc'
~~~

Collection responses include `page` metadata and links such as `next` and `prev` when applicable. Follow the returned links for pagination; this keeps pagination and sorting parameters consistent. Page size limits and defaults can be configured.

Query methods are exposed under `/search`. With the example repository above, clients can discover the `by-name` link in the search resource response and then call the query endpoint with the `name` parameter. Exported query methods are read-only resources and are typically called with `GET`.

## 8. Projections, excerpts, and embedded data

Projections allow defining a view of an entity using an interface with selected getters. This helps the API return only the properties needed for a use case. Projections can be registered automatically when placed in the entity package or a subpackage, or registered via configuration.

An excerpt is a projection automatically applied to embedded elements in a collection or related resource when the repository declares `excerptProjection`. Excerpts do not automatically apply to a single item resource; to use a projection for an item, the client needs to request the corresponding projection via the `projection` parameter if the endpoint exposes it.

Projections change the data in a representation, while links can still exist for clients to navigate to related resources. Do not treat embedding partial data as proof that the association has lost its own endpoint.

## 9. Endpoint control and security

Spring Data REST automatically exposes many operations from repositories, but that does not mean every operation should always be open to every client.

- Use `RepositoryRestResource(exported = false)` to prevent exporting a repository.
- Use `RestResource(exported = false)` on a method or association to hide the corresponding endpoint.
- Use Spring Data REST configuration to customize the base path, relations, media types, and supported HTTP methods.
- Use Spring Security to authenticate and authorize by resource, method, or business rule.
- Use validation and domain rules to protect data; a request having valid JSON does not mean the data is business-valid.

If an operation is a multi-step business workflow, requires coordinating multiple aggregates, or cannot be expressed clearly with CRUD and associations, consider a dedicated business controller/endpoint. Do not force every action into a repository operation simply because Spring Data REST can export that repository.

## 10. Common misconceptions

- **Treating URIs as fixed structures:** clients hard-code `/products/1` instead of following `href`. Start from the root and follow relations.
- **Equating entities with representations:** assuming every field in the entity, especially the ID, is always present in JSON. Representations can be affected by configuration and projections.
- **Confusing collections with items:** `POST` typically creates an item on a collection; `PUT`, `PATCH`, and `DELETE` typically operate on an item.
- **Using `PUT` when only one field needs to change:** `PUT` carries replacement semantics; use `PATCH` for partial updates.
- **Confusing association deletion with entity deletion:** `DELETE` on an association removes the link; `DELETE` on an item deletes the identified resource.
- **Assuming every repository supports full CRUD:** missing or hidden methods can prevent endpoints from being exposed and return `405`.
- **Ignoring content negotiation:** missing or wrong `Accept`/`Content-Type` headers can cause the body or status to differ from expectations.
- **Ignoring pagination:** large collections need `page`, `size`, `sort`, and navigation links rather than assuming a single response contains all items.
- **Assuming automatic export means secure:** endpoints must be protected with appropriate authentication, authorization, and validation.

## 11. Workflow for reading a Spring Data REST response

When debugging or integrating an API, answer the following questions in order:

1. Is the current URI a root, collection, item, association, or search resource?
2. Which format does `Content-Type` indicate the server is returning?
3. What state do the properties in the body describe? Is there a projection or excerpt?
4. Which relations are in `_links`? Where do `self`, `search`, `next`, `prev`, or association links lead?
5. What operation does the client intend to perform? Does the HTTP method match the resource type and business meaning?
6. Does the repository export the corresponding method? Do security, validation, and configuration allow the operation?
7. Do the status code and `Location` match the expected outcome?

Understanding these seven points lets you read and use a Spring Data REST API without guessing URL structures or confusing data, relationships, and actions.

## References

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — Projections and excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST Reference — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data REST Reference — Customizing JSON output](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-json-output.html)
