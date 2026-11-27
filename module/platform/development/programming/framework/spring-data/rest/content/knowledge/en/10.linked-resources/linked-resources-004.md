# Sending Resource References by URI in JSON When Creating or Updating in Spring Data REST

## Objectives

After this lesson, you can link a new or existing entity to other resources by URI in JSON; distinguish URI references from nested objects; handle to-one and collection associations; and know when to use an association endpoint with `text/uri-list`.

## 1. Why Use URIs to Reference Related Resources?

In Spring Data REST, a repository resource can have associations to other resources. For example:

- An `Order` belongs to a `Customer`.
- A `Book` has a `Publisher`.
- An `Article` has many `Tag`s.

When a client creates or updates an `Order`, the client typically only needs to point to an existing `Customer` using that resource's URI. The server uses the URI to resolve the related entity and bind the association to the entity being saved.

This approach fits hypermedia well: the client takes the URI from the `self` link of a known resource, then sends that URI when creating or updating the relationship. The client does not need to resend all of the Customer's data and avoids creating unintended duplicates.

For example, the API exposes:

- Customer item resource: `http://localhost:8080/customers/42`
- Order collection resource: `http://localhost:8080/orders`

When creating an Order for Customer 42, the body can contain the Customer's URI:

```json
{
  "description": "Laptop order",
  "customer": "http://localhost:8080/customers/42"
}
```

The property name `customer` in JSON corresponds to the association property exposed by the domain object and Jackson. Use the exact property name exposed by the API; do not infer it from the class name if the entity has customized mappings.

## 2. Creating a New Resource with a URI Reference

Suppose the domain model has a many-to-one relationship from `Order` to `Customer`:

```java
@Entity
public class Order {

    @Id
    @GeneratedValue
    private Long id;

    private String description;

    @ManyToOne
    private Customer customer;

    // Constructors, getters, and setters
}
```

The repository is exposed by Spring Data REST under `/orders`. The client creates an `Order` by sending the URI of an existing `Customer`:

```http
POST /orders HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/hal+json

{
  "description": "Laptop order",
  "customer": "http://localhost:8080/customers/42"
}
```

Spring Data REST reads the body, resolves the URI to the related resource, and sets it on the `customer` association before saving the `Order`. A successful response is typically `201 Created`, accompanied by a `Location` header pointing to the newly created `Order`.

Abbreviated example response:

```http
HTTP/1.1 201 Created
Location: http://localhost:8080/orders/100
Content-Type: application/hal+json
```

```json
{
  "description": "Laptop order",
  "_links": {
    "self": { "href": "http://localhost:8080/orders/100" },
    "customer": { "href": "http://localhost:8080/orders/100/customer" }
  }
}
```

In a HAL response, associations are usually represented as links. The client can follow that link to view or modify the relationship using the operations supported by the endpoint.

## 3. Updating an Association by URI in JSON

When updating an existing `Order`, the client can send a new URI in the JSON payload. For example, reassigning Order 100 to Customer 43:

```http
PATCH /orders/100 HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "customer": "http://localhost:8080/customers/43"
}
```

Spring Data REST resolves the URI and assigns Customer 43 to the association. `PATCH` is appropriate when you only want to modify part of a resource. With `PUT`, clients typically send a full representation per the endpoint's replacement semantics; make sure required fields and associations to be kept are properly represented.

If you want to remove an association, do not send a dummy URI or empty string expecting the server to infer your intent. Use the appropriate association operation or update semantics supported by the endpoint; check the HAL links and domain model mapping before choosing how to unbind.

## 4. Referencing Collection Associations

An entity can be linked to multiple resources, for example an `Article` with many `Tag`s:

```java
@Entity
public class Article {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @ManyToMany
    private Set<Tag> tags = new HashSet<>();

    // Constructors, getters, and setters
}
```

When an endpoint accepts collection associations in JSON, the client sends an array of URIs corresponding to existing resources:

```http
POST /articles HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "title": "Spring Data REST",
  "tags": [
    "http://localhost:8080/tags/3",
    "http://localhost:8080/tags/8"
  ]
}
```

Each URI identifies a `Tag` to link to the new `Article`. The JSON type must match the association type in the domain model, such as a JSON array of URIs for a collection. Verify the exact property name and representation supported by the endpoint; do not send a nested object containing the entire `Tag` if the goal is simply to link to an existing `Tag`.

With collection associations, it is important to understand update semantics. A `PATCH` or `PUT` payload is applied according to the endpoint's binding mechanism and collection type; if the goal is specifically to add or remove an individual link, the association endpoint usually expresses that intent more clearly.

## 5. URI References vs. Nested Objects

Suppose Customer 42 already exists. This is how to send a reference:

```json
{
  "description": "Laptop order",
  "customer": "http://localhost:8080/customers/42"
}
```

This is a nested object:

```json
{
  "description": "Laptop order",
  "customer": {
    "id": 42,
    "name": "Ada Lovelace"
  }
}
```

The two payloads do not have the same meaning. A URI explicitly tells the client/server to link to an existing resource managed by a repository. A nested object may be treated by Jackson as data to deserialize into a new object or may not be converted as intended for an association; you should not rely on it to look up and update an existing entity.

If you need to create a new `Customer`, create the `Customer` via the Customer collection resource first, obtain its URI from the `Location` header or `self` link, and then use that URI when creating the `Order`. If you need to update Customer information, call the Customer endpoint with a separate update operation.

## 6. Getting the Right URI from the HAL Response

Do not construct URIs from IDs manually if the API can change its base path, context path, resource path, or run behind a reverse proxy. Use the links returned by the server.

Example Customer response:

```json
{
  "id": 42,
  "name": "Ada Lovelace",
  "_links": {
    "self": {
      "href": "https://api.example.com/shop/customers/42"
    }
  }
}
```

The client extracts `_links.self.href` and places it into the association property in the JSON of the `Order` create or update request. This preserves the exact host and path advertised by the server.

If the association is customized with `@RestResource`, the relation name shown in HAL may differ from the property name in the domain model. Use HAL links to locate association endpoints; when sending a JSON entity body, use the exact property name exposed by Jackson and Spring Data REST.

## 7. Association Endpoints and the text/uri-list Media Type

In addition to sending URIs inside the entity's JSON body, Spring Data REST also exposes dedicated association resources. These links usually appear on the item resource, for example:

```json
{
  "_links": {
    "self": { "href": "http://localhost:8080/orders/100" },
    "customer": { "href": "http://localhost:8080/orders/100/customer" },
    "tags": { "href": "http://localhost:8080/orders/100/tags" }
  }
}
```

To modify an association through its dedicated endpoint, the client can send the URI in the body with the `text/uri-list` media type. For example, assigning Customer 43 to Order 100:

```http
PUT /orders/100/customer HTTP/1.1
Content-Type: text/uri-list

http://localhost:8080/customers/43
```

For collection associations, `text/uri-list` can contain one URI per line:

```http
PUT /articles/10/tags HTTP/1.1
Content-Type: text/uri-list

http://localhost:8080/tags/3
http://localhost:8080/tags/8
```

Check the semantics of the association endpoint before using `PUT`: for collections, this operation typically sets the linked set to the submitted URI list. If you only want to add or remove a single link, choose the HTTP method supported by the association resource and check the Spring Data REST documentation for your version.

The two submission styles must be distinguished:

| Submission style | Endpoint | Content-Type | Purpose |
| --- | --- | --- | --- |
| URI in JSON | Collection or item resource | `application/json` | Create or update an entity along with its association |
| URI list | Association resource from HAL link | `text/uri-list` | Modify an association via its dedicated endpoint |

Do not send `text/uri-list` to a collection endpoint that creates entities if that endpoint expects a JSON representation.

## 8. URI Resolution Rules and Common Errors

When the server resolves an association URI, several conditions must be met:

1. The URI must point to a valid item resource, not a collection endpoint.
2. The target resource must exist and be resolvable within the application.
3. The URI must belong to the right association type. For example, the `customer` property must point to a Customer, not an Address.
4. The current user must be permitted to read or link the target resource according to the application's security policy.
5. The domain mapping must allow modifying the association; with JPA bidirectional relationships, the owning side must be updated so the change is persisted.

Common errors:

**Sending an ID instead of a URI**

The payload `"customer": 42` is just a JSON number, not a resource reference URI. Send the item resource URI, such as `"customer": "http://localhost:8080/customers/42"`.

**Sending a nested object**

The payload `"customer": {"id": 42}` does not clearly express the intent to link to an existing entity. Use the URI from the `self` link.

**Using a collection URI instead of an item URI**

`http://localhost:8080/customers` points to the collection. To link a specific Customer, use an item URI like `http://localhost:8080/customers/42`.

**Non-existent URI or wrong type**

The server cannot resolve the target resource; the request will fail according to the application's exception mapping. Check the URI, repository path, base path, and association type.

**Rejected by security**

A syntactically valid URI may still not be permitted to be linked. Check authorization for both the operation on the source entity and access to the target resource; do not trust a client-supplied URI just because its format is valid.

**Association changed but not persisted**

With JPA bidirectional relationships, check the owning side, cascade settings, and two-way synchronization helper methods. Spring Data REST may bind the association, but persistence still depends on the ORM mapping.

## 9. Complete Example: Creating an Order and Linking a Customer

Suppose the Customer has already been created and the HAL response returns:

```json
{
  "name": "Ada Lovelace",
  "_links": {
    "self": {
      "href": "http://localhost:8080/customers/42"
    }
  }
}
```

Use that `self` URI to create the Order:

```bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{
    "description": "Laptop order",
    "customer": "http://localhost:8080/customers/42"
  }'
```

After creation succeeds, read the response to get the new Order's URI from the `Location` header. Call that item resource and inspect the `customer` link to confirm the association. If you want to reassign the Order to another Customer, send a `PATCH` to the item resource with the new Customer URI or use the association endpoint advertised in HAL.

## Summary

- When creating or updating an entity, send the item resource URI in the association property of the JSON body to reference an existing entity.
- For to-one relationships, the value is typically a single URI string; for collection associations, the representation can be an array of URIs.
- Take URIs from the `self` link in HAL responses instead of constructing URLs manually.
- Nested objects and raw IDs do not replace resource reference URIs.
- Association endpoints provide a dedicated way to modify relationships; these endpoints typically accept `text/uri-list`.
- Verify the target resource, relationship type, access permissions, and ORM mapping before saving.

## References

- [Spring Data REST — Handling associations](https://docs.spring.io/spring-data/rest/reference/handling-associations.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing association resource exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
