# Mapping HTTP Calls to Repository Methods

## Objective

When an application uses Spring Data REST, an exported repository can become a REST API without writing a dedicated CRUD controller. Spring Data REST reads the metadata of the repository and domain type, creates the corresponding resources, and maps each **path + HTTP method** pair to the appropriate repository operation.

Key point to remember: CRUD endpoints are not created by arbitrarily turning a Java method name into a URL. For standard resources, Spring Data REST decides the operation based on the resource type, HTTP method, and exported repository methods. Query methods are exposed separately under the `search` resource.

## 1. Processing flow from HTTP to repository

A request passes through the following high-level steps:

1. **Identify an exported repository.** Spring MVC receives the request. `RepositoryRestHandlerMapping` checks whether the first URL segment matches a resource mapping of an exported repository. If not, another handler mapping in the application may handle the request.
2. **Determine the resource type.** The path indicates whether the request targets a collection, an item by ID, an item's association, the search resource, or a query method.
3. **Check whether the HTTP method is supported.** Spring Data REST checks the required method against the methods declared and permitted for export on the repository. If the corresponding operation does not exist or is disabled with `exported = false`, that verb is not exposed and typically returns `405 Method Not Allowed`.
4. **Convert input data.** The ID in the URL is converted to the repository's ID type; the query string is converted into method parameters, `Pageable`, or `Sort`; the request body is deserialized into a domain object or update data.
5. **Invoke the repository.** For standard CRUD, Spring Data REST uses metadata and `RepositoryInvoker` to call the appropriate method such as `findAll`, `findById`, `save`, or `delete`. For query resources, the framework invokes the exported query method.
6. **Build the HTTP response.** The result is converted into a JSON/HAL representation, along with related links, pagination metadata, and appropriate headers such as `Location` when creating a resource.

The flow can be pictured as follows:

~~~text
HTTP request
    |
    v
RepositoryRestHandlerMapping
    |
    v
Resource mapping + HTTP method
    |
    v
Collection / Item / Association / Search
    |
    v
Bind ID, query parameters, Pageable, request body
    |
    v
RepositoryInvoker or exported query method
    |
    v
Spring Data repository proxy -> store implementation
    |
    v
HAL/JSON representation + HTTP status/headers
~~~

The Spring Data repository proxy is what actually executes the query or datastore operation. Spring Data REST handles recognizing the resource, translating the request into a repository call, and converting the result into an HTTP response.

## 2. Map of HTTP methods and repository methods

Suppose a repository manages the `Person` entity and is exported at `/people`.

| Resource | HTTP request | Repository method used |
|---|---|---|
| Collection `/people` | GET | Prefers `findAll(Pageable)`, then `findAll(Sort)`, then `findAll()` if available and exported |
| Collection `/people` | POST | `save(entity)` to create an entity from the request body |
| Collection `/people` | HEAD | Checks the resource using available `findAll` variants; returns no response body |
| Item `/people/{id}` | GET | `findById(id)` |
| Item `/people/{id}` | HEAD | Uses the same ID lookup capability as GET, without returning a response body |
| Item `/people/{id}` | PUT | `save(entity)` after replacing resource state with request data |
| Item `/people/{id}` | PATCH | `save(entity)` after applying the submitted partial changes |
| Item `/people/{id}` | DELETE | Uses the appropriate exported delete overload, such as `delete(entity)`, `delete(id)`, or `delete(entities)` |
| Search `/people/search` | GET | Returns a list of links to exported query methods; does not run a specific query yet |
| Query `/people/search/...` | GET | Calls the corresponding query method directly on the repository |

The selection order for collection GET matters. If the repository supports `findAll(Pageable)`, Spring Data REST can accept `page`, `size`, and `sort` and return data with pagination metadata/links. If no `Pageable` variant exists, the framework checks the other variants in the order shown in the table.

### Meaning of each operation group

- **GET collection** reads a list. When the repository supports paging, `page` is zero-based, `size` is the number of items per page, and `sort` describes the property and sort direction.
- **POST collection** receives an entity representation, calls `save`, and creates an item resource. The response typically has status `201 Created` with a `Location` header pointing to the new item. The response body depends on the `Accept` header and configuration for returning bodies on creation.
- **GET item** converts the ID in the URL to the right ID type, calls `findById`, and renders the found entity. Not finding the item typically leads to `404 Not Found`.
- **PUT item** replaces the resource state with the submitted representation. **PATCH item** applies only the changed fields/parts present in the request. Both use `save` to persist the final state; whether the datastore performs an insert or update depends on the repository and store.
- **DELETE item** deletes the item using a delete overload supported by the repository. `DELETE` on an association unlinks the relationship, which is different from deleting the entity.
- **Search** is the discovery point for query methods. `GET /people/search` returns links; `GET` on a specific query method link executes the query.

Do not assume that every repository method has a corresponding endpoint. Standard CRUD methods and eligible query methods are handled according to specific rules. An arbitrary business method does not automatically become a `POST` endpoint simply because it resides on the repository interface.

## 3. Query methods mapped under /search

Exported query methods appear under the `search` resource. The default resource name is usually derived from the method name, while the path and relation can be customized with `@RestResource`.

General repository example:

~~~java
@RepositoryRestResource(path = "people", collectionResourceRel = "people")
public interface PersonRepository
        extends CrudRepository<Person, Long>,
                PagingAndSortingRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    Page<Person> findByLastname(
            @Param("lastname") String lastname,
            Pageable pageable);
}
~~~

The example above uses both `CrudRepository` and `PagingAndSortingRepository` to clearly show both CRUD and paging capabilities. With store-specific repositories, such as `JpaRepository`, those interfaces are usually already combined.

If the base path is configured:

~~~properties
spring.data.rest.base-path=/api
~~~

then typical requests are:

~~~http
GET    /api/people
POST   /api/people
GET    /api/people/42
PUT    /api/people/42
PATCH  /api/people/42
DELETE /api/people/42

GET    /api/people/search
GET    /api/people/search/by-last-name?lastname=Nguyen&page=0&size=10
~~~

In the query method example:

- `by-last-name` is the path set by `@RestResource(path = "by-last-name")`.
- `lastname=Nguyen` is bound to the `@Param("lastname")` parameter.
- `page`, `size`, and `sort` are bound to `Pageable` if the method supports pagination.
- The returned result is a collection resource with pagination metadata and links; the query is executed by `findByLastname(...)`.

`GET /api/people/search` lets clients discover query method links instead of guessing URLs. Clients should read the HAL links returned by the server, especially when paths or relations have been customized.

## 4. Association resources are not ordinary CRUD items

For associations recognized by Spring Data REST in the domain model, an item can provide links to association resources, usually named after the property. For example:

~~~text
GET /api/people/42
    -> _links.address.href = /api/people/42/address
~~~

Association resources support operations according to the relationship:

| HTTP method | Meaning |
|---|---|
| GET | Reads the currently linked resource |
| PUT | Assigns the specified resource to the association; typically sends URIs with media type `text/uri-list` |
| POST | Used only for collection associations; adds a resource to the collection by URI |
| DELETE | Removes the link; does not mean deleting the linked entity |

Example body for assigning a link:

~~~http
PUT /api/people/42/address
Content-Type: text/uri-list

http://localhost:8080/api/addresses/8
~~~

Because associations are manipulated via the URI of the related resource, clients must use the exact URIs published by the API. For one-to-one/one-to-many associations, `PUT`/`POST`/`DELETE` support also depends on relationship type and domain model metadata. An association should not be thought of as an arbitrary call to a `saveAddress` method on the repository.

## 5. What determines whether an HTTP method is exposed?

Endpoint exposure depends on repository structure and Spring Data REST configuration:

- The repository must be discovered and exported. The default collection path is derived from the domain type; it can be changed with `@RepositoryRestResource`.
- An HTTP operation is only provided when the repository has the required method. For example, without `save`, standard creation/update routes cannot be served.
- A method can be hidden with `@RestResource(exported = false)`. For example:

~~~java
@RestResource(exported = false)
@Override
void deleteById(Long id);
~~~

- Exporting an entire repository can be disabled with `@RepositoryRestResource(exported = false)`.
- Paths and relations of a repository or query method can be changed with `@RepositoryRestResource` and `@RestResource`.
- Spring Data REST exposure configurations can restrict HTTP methods by resource type or repository.

If a method does not exist or is not exported, requests using the corresponding verb typically receive `405 Method Not Allowed`. This differs from `404`: `404` usually indicates the path/resource or item was not found, whereas `405` indicates the resource route exists but that verb is not supported.

Endpoint exposure and authorization are two separate concerns. `exported = false` controls whether the method/resource is published; Spring Security must still be configured to restrict who is allowed to read, create, edit, or delete data.

If you need a custom business operation, such as confirming an order or calculating fees, design an appropriate custom controller instead of expecting Spring Data REST to automatically map arbitrary methods into HTTP endpoints. Query methods under `search` are primarily intended for `GET` queries.

## 6. Reading requests and responses when debugging

When a request does not invoke the expected repository method, check in the following order:

1. **Check the root resource.** Send `GET` to the base path and inspect the HAL links. If the collection link does not appear, the repository may not have been discovered/exported or the path may have been customized.
2. **Check the collection link.** `GET` the collection to confirm the resource and see whether a `search` link is present.
3. **Check the search link.** `GET /search` to see which query methods are actually exported. Do not guess the path solely from the Java method name if `@RestResource` is present.
4. **Match the HTTP verb against repository methods.** `GET` item needs `findById` capability; `POST` collection needs `save`; `PUT`/`PATCH` need `save`; `DELETE` needs a suitable delete method.
5. **Check export annotations.** Look for `@RepositoryRestResource(exported = false)` or `@RestResource(exported = false)`, including annotations placed on overridden methods.
6. **Check binding.** Confirm the ID has the right type, query parameter names match `@Param`, `Pageable`/`Sort` are declared, and JSON has the expected structure and `Content-Type`.
7. **Inspect status and headers.** `Location` shows the created item's URI; `405` suggests the verb is not exported; `404` suggests the resource/item does not exist; `400` usually relates to invalid data or parameters; `415` indicates an unsupported media type.

Common responses:

| Status | How to interpret in this flow |
|---|---|
| 200 OK | `GET` succeeded; update/delete may also return a body depending on configuration |
| 201 Created | New resource created, usually with `Location` |
| 204 No Content | Operation succeeded without returning a body |
| 400 Bad Request | Invalid ID, parameters, or request body |
| 404 Not Found | Requested resource/item does not exist |
| 405 Method Not Allowed | Resource does not support that HTTP method or the repository method is hidden |
| 415 Unsupported Media Type | `Content-Type` is not among the media types supported by the endpoint |

## 7. Common misconceptions

- **GET collection does not automatically invoke an arbitrary `findBy...` method.** `GET` collection uses `findAll` variants; custom filtering queries are called via query resources under `/search`.
- **The repository method name does not determine the entire URL.** Collection paths, query paths, and relations can be customized via annotations.
- **`save` does not always mean `INSERT`.** Spring Data REST calls `save`; the repository/store decides how to persist the entity based on ID and state.
- **`PUT` and `PATCH` have different semantics.** `PUT` replaces the resource state; `PATCH` applies partial changes. Both can still route to `save` after data is bound.
- **`DELETE` on an association does not delete the related entity.** It unlinks the relationship between the two resources.
- **Not every method on the interface is exported.** Only resources/methods meeting export rules and configuration get endpoints.
- **405 is not a repository query error.** First check whether the method is exported and the verb is valid for that resource type.

## 8. Summary of how to trace a request

When looking at an HTTP request, read along this chain:

**URL → resource type → HTTP method → required repository method → parameter/body binding → repository result → HAL/JSON response.**

Example with `GET /api/people/42`:

1. `people` matches an exported repository.
2. `42` indicates this is an item resource, not a collection.
3. `GET` selects the item read operation.
4. The ID is converted to the ID type of `Person`.
5. Spring Data REST calls `findById(42L)`.
6. The entity is converted into a representation and returned; if no entity exists, the response is `404`.

Example with `GET /api/people/search/by-last-name?lastname=Nguyen`:

1. `people/search` identifies the repository's search resource.
2. `by-last-name` selects the exported query method.
3. `lastname` is bound to the method parameter.
4. `Pageable`/`Sort` are bound if the method supports them.
5. Spring Data invokes the query method and Spring Data REST renders the result.

## References

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Project overview](https://spring.io/projects/spring-data-rest/)