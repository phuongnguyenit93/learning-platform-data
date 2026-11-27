# The /{collection}/{id}/{property} Path for Associations in Spring Data REST

## Context

Spring Data REST exposes Spring Data repositories as REST resources. In addition to collection resources and item resources, each item can also have **association resources** to read or modify relationships between that entity and other entities.

Path pattern:

    /{collection}/{id}/{property}

Examples:

    /orders/42/customer
    /people/42/addresses

This is an illustrative URI template. Curly braces indicate segments to be replaced with actual values; do not send the literal string containing curly braces to the server. Association resources let clients manipulate relationships over HTTP without having to write a custom controller for every association.

After this lesson, you can read the three parts of the URI correctly, locate association links from a HAL response, invoke the appropriate HTTP methods, and recognize common reasons why an endpoint might not work.

## 1. Meaning of Each URI Segment

| Segment | Meaning | Example |
| --- | --- | --- |
| collection | Collection resource path of the repository holding the parent entity | orders |
| id | Identifier of the parent item resource holding the association | 42 |
| property | Name of the association property on the parent entity; defaults to the property name in the domain model | customer |

Suppose there is an order with ID `42` and a `customer` property pointing to that order's customer. The association resource can be located at:

    /orders/42/customer

In this example:

- `orders` is the collection path of the order repository.
- `42` is the ID of the order, i.e., the parent entity.
- `customer` is the association property on the order entity.

The most common point of confusion is that `id` in this path pattern belongs to the **parent entity**. It is not the ID of the linked entity. The customer's ID is passed via the customer's URI when binding the association.

The collection path also does not have to match the class name, table name, or database collection name. Spring Data REST has default naming rules, though you can explicitly declare it with `@RepositoryRestResource(path = "...")`.

## 2. Example Domain Model

Suppose an order has one customer. The two repositories are exposed by Spring Data REST as follows:

    @Entity
    public class PurchaseOrder {

        @Id
        @GeneratedValue
        private Long id;

        @ManyToOne
        private Customer customer;

        // constructors, getters and setters
    }

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String name;

        // constructors, getters and setters
    }

    @RepositoryRestResource(path = "orders")
    public interface PurchaseOrderRepository
            extends JpaRepository<PurchaseOrder, Long> {
    }

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

With this configuration, the order item resource has the form `/orders/{id}`, and the customer item resource has the form `/customers/{id}`. The `customer` association property generates an association resource under the order item resource.

If order `42` is linked to customer `7`, the related URIs are:

    Order item resource:    /orders/42
    Association resource:   /orders/42/customer
    Customer item resource: /customers/7

The association resource and the customer item resource are two different resources. The first URI represents the `customer` association of order `42`; the second URI represents customer `7` itself.

## 3. Finding an Association Resource via HAL

When a client calls an item resource and requests HAL JSON, Spring Data REST returns the resource's links. The association link is typically named after the association property.

    GET http://localhost:8080/orders/42
    Accept: application/hal+json

An abbreviated response might look like this:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/orders/42"
        },
        "purchaseOrder": {
          "href": "http://localhost:8080/orders/42"
        },
        "customer": {
          "href": "http://localhost:8080/orders/42/customer"
        }
      }
    }

The client takes the `href` of the `customer` link to access the association resource. The key in `_links` is the HAL relation (`rel`); `href` is the actual URI to call.

Prefer following the `href` returned by the server rather than constructing the URI manually. Collection paths, base paths, association paths, and relation names can all be customized. When those settings change, the links provided by the server remain the reliable guide for clients.

Reading the association resource:

    GET http://localhost:8080/orders/42/customer
    Accept: application/hal+json

`GET` returns the current state of the association. The response may represent the linked resource or the association state depending on the representation and the association type.

## 4. HTTP Methods on an Association Resource

Spring Data REST supports `GET`, `PUT`, `POST`, and `DELETE` for association resources. Whether each method can be used depends on the association type.

| Method | Purpose | Scope |
| --- | --- | --- |
| GET | Read the association state | To-one and collection |
| PUT | Bind the resource specified by URI to the association | To-one and URI-accepting associations |
| POST | Add an item to the association | Collection associations only |
| DELETE | Unbind the association | Depends on whether the relationship is optional |

### GET — Reading the association

Use `GET` to inspect the current association:

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/orders/42/customer

`GET` does not mean fetching the entire parent entity. It specifically accesses the association resource nested under the item resource.

### PUT — Assigning a to-one association

For to-one associations such as `ManyToOne` or `OneToOne`, `PUT` takes the URI of the resource to link. The body uses the `text/uri-list` media type.

    curl -i -X PUT       -H "Content-Type: text/uri-list"       --data "http://localhost:8080/customers/7"       http://localhost:8080/orders/42/customer

This request asks to bind the customer at URI `/customers/7` to the `customer` association of order `42`.

Do not send JSON such as `{"id": 7}` to this association endpoint. The association API expects the URI of the target resource with `Content-Type: text/uri-list`. If the association is to-one and the request sends multiple URIs, the server can return `400 Bad Request`.

### POST — Adding an item to a collection association

For collection associations, such as a person having multiple addresses, `POST` adds a resource to the collection:

    curl -i -X POST       -H "Content-Type: text/uri-list"       --data "http://localhost:8080/addresses/10"       http://localhost:8080/people/42/addresses

In this example, `42` is still the ID of the person owning the association; `10` is the ID of the address being added. `POST` is for collection associations, not for assigning a to-one relationship.

You can send multiple URIs in `text/uri-list`, one URI per line, when the association and operation allow multiple elements.

### DELETE — Unbinding the link

`DELETE` instructs the server to unbind the association:

    curl -i -X DELETE       http://localhost:8080/orders/42/customer

This operation unbinds the `customer` link from order `42`; it does not delete the `Customer` record from the database. If the relationship is configured as required and cannot be left empty, Spring Data REST may reject the operation and return `405 Method Not Allowed`.

Always check the domain mapping, database constraints, and permissions before modifying or unbinding links on real data.

## 5. Customizing the Association Path and HAL Relation

By default, the name and path of an association resource come from the association property name. You can customize them with `@RestResource` on the property.

    @Entity
    public class PurchaseOrder {

        @Id
        @GeneratedValue
        private Long id;

        @ManyToOne
        @RestResource(path = "buyer", rel = "buyer")
        private Customer customer;
    }

With this configuration, the association path is changed to `buyer`:

    /orders/42/buyer

The HAL relation is also named `buyer`. The two attributes have distinct roles:

- `path` determines the URL segment of the association resource.
- `rel` determines the link name in `_links` of the HAL response.

If you only rename the Java property, verify the actual URI and HAL relation. Once an API is consumed by clients, changing `path` or `rel` can affect backward compatibility.

You can also hide an association from the REST API by configuring `exported = false` on the association property:

    @ManyToOne
    @RestResource(exported = false)
    private Customer customer;

When an association is not exported, clients should not expect to find the corresponding association link.

## 6. Base Path and Full URIs

If the application configures a base path:

    spring.data.rest.base-path=/api

then the URI can take the form:

    /api/orders/42/customer

The base path is the common prefix for Spring Data REST resources. The servlet context path, reverse proxy, or gateway can also alter the external URI seen by clients.

Therefore, do not hardcode `/orders/42/customer` across all clients. Read the link from the HAL response to get the `href` generated by the server under the running configuration.

## 7. Distinguishing an Association Resource from an Item Resource

The following two URIs do not have the same meaning:

    /orders/42
    /orders/42/customer

`/orders/42` is the item resource of an order. Clients read or update the order's data here.

`/orders/42/customer` is the association resource representing that order's `customer` relationship. Clients use this endpoint to read or modify the link.

Meanwhile:

    /customers/7

is the item resource of customer `7`. This is typically the URI passed in the `text/uri-list` body when you want to bind that customer to the association.

Distinguishing these three URIs helps avoid common errors: placing the target entity's ID in the `{id}` segment or sending entity data instead of the target resource's URI.

## 8. Common Errors

| Symptom | Causes to check |
| --- | --- |
| 404 Not Found | Wrong collection path, parent entity ID, or association path; repository or association is not exported |
| Link missing from `_links` | Association is not linkable, hidden with `exported = false`, related repository is not exported, or `rel`/`path` was customized |
| 405 Method Not Allowed | Method not supported for the association type, or `DELETE` rejected because the relationship is not optional |
| 400 Bad Request on PUT | Multiple URIs sent for a to-one association |
| 415 Unsupported Media Type | JSON used instead of `text/uri-list` when calling `PUT` or `POST` on the association |
| 403 Forbidden | Spring Security does not permit the current principal to read or modify the resource |
| Relationship not persisted as expected | Check the owning side, bidirectional sync helpers, and JPA mapping transactions |

When debugging, follow this order:

1. `GET` the parent entity's item resource and inspect the HAL response.
2. Copy the exact `href` from the association link.
3. `GET` that `href` to verify the association resource exists.
4. Check the HTTP method, `Content-Type`, and URI body.
5. Check server logs, export configuration, security, and persistence mapping if the response is still not as expected.

Do not conclude an endpoint does not exist just because you guessed the property name wrong. Check the actual links returned by the server.

## 9. Persistence and Security Notes

An association resource is how Spring Data REST represents a relationship in the domain model; it is not a direct path to a foreign key column or database table name.

With JPA, identify the owning side of the relationship. For example, if the foreign key resides in the `orders` table, the `customer` property on `PurchaseOrder` is typically the owning side of the `ManyToOne` relationship. For bidirectional relationships, use helper methods to synchronize both sides in memory before saving to avoid an inconsistent object graph.

The fact that Spring Data REST renders an association link does not automatically grant access to every user. Spring Security configuration still determines who can `GET`, `PUT`, `POST`, or `DELETE`. Clients must handle `401`/`403` and should not treat seeing an `href` as proof that a write operation is permitted.

## 10. Practice Exercise

Suppose the API has these resources:

- Order `42` at `/orders/42`.
- Customer `7` at `/customers/7`.
- The `customer` association of order `42` at `/orders/42/customer`.

Perform the following steps in order:

1. Call `GET /orders/42` with `Accept: application/hal+json`.
2. Find the `customer` link inside `_links` and read its `href`.
3. Call `GET` on that `href` to inspect the currently linked customer.
4. Call `PUT` on the association `href` with `Content-Type: text/uri-list` and the body `/customers/7`.
5. Call `GET` on the association `href` again to confirm the relationship has changed.
6. Try sending two URIs to the to-one association and observe the `400` error.
7. Try `DELETE` in a test data environment, then verify the relationship has been unbound; if the server returns `405`, check whether the relationship is required.

Self-check questions:

- In `/orders/42/customer`, which entity does ID `42` belong to?
- What role does the URI `/customers/7` play when calling `PUT`?
- Why is `POST` only suitable for collection associations?
- How do `path` and `rel` in `@RestResource` differ?
- Why should you use `href` from HAL instead of constructing URLs manually?

## References

- [Spring Data REST Reference — Repository resources and Association Resource](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
