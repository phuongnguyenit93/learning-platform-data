# Distinguishing HAL Links from Association Resources

## Objectives

After this lesson, you can:

- Recognize a HAL link in JSON returned by Spring Data REST.
- Distinguish a navigation link from an endpoint representing an association between two entities.
- Follow HAL links to locate an association resource without guessing URLs.
- Choose the right HTTP method and Content-Type when reading or modifying an association.
- Avoid confusing operations on an association resource with creating, updating, or deleting an entity.

## 1. Context: Spring Data REST and HAL

Spring Data REST exposes Spring Data repositories as REST resources. For example, a repository managing an `Order` entity can expose a collection resource at `/orders` and an item resource for each order at `/orders/{id}`.

By default, Spring Data REST uses HAL (Hypertext Application Language) to represent links in JSON. Responses typically have a `Content-Type` of `application/hal+json`. HAL places links inside the `_links` property; each key is a relation name, and its value contains information about the link, typically including at least `href`.

Example response at the API root:

~~~json
{
  "_links": {
    "orders": {
      "href": "http://localhost:8080/orders"
    },
    "profile": {
      "href": "http://localhost:8080/profile"
    }
  }
}
~~~

In this example:

- `orders` is the relation name indicating that the link leads to the orders collection.
- `href` is the URI that the client can call next.
- `profile` is another link, not an association between two business entities.

A HAL link is navigation information embedded in the representation. The link itself neither contains association data nor executes an operation. It tells the client what a URI means in the context of the current response.

HAL is not used solely for entity associations. Links can point to the API root, a collection, an item, a search resource, a profile, the next page, or an association resource. Therefore, do not assume that every entry in `_links` represents a data association.

## 2. What Is an Association Resource?

When an entity has an association to another entity, Spring Data REST can expose a dedicated sub-resource for that association. The Spring Data REST documentation refers to this as an association resource.

Suppose an `Order` references a `Customer`:

~~~java
@Entity
public class Customer {
    @Id
    @GeneratedValue
    private Long id;

    private String name;

    // constructors, getters and setters
}
~~~

~~~java
@Entity
public class Order {
    @Id
    @GeneratedValue
    private Long id;

    private String orderNumber;

    @ManyToOne
    private Customer customer;

    // constructors, getters and setters
}
~~~

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}

public interface OrderRepository
        extends JpaRepository<Order, Long> {
}
~~~

With these repositories exposed by Spring Data REST, the order item resource can return:

~~~json
{
  "orderNumber": "ORD-042",
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    },
    "customer": {
      "href": "http://localhost:8080/orders/42/customer"
    }
  }
}
~~~

Here you must distinguish between two URIs:

- `/orders/42` is the item resource for the order itself.
- `/orders/42/customer` is the association resource representing the `customer` association of that order.

The link with relation name `customer` inside `_links` points the way to the association resource. The association resource is the endpoint that the client calls to read or modify the link between Order 42 and a Customer.

By default, the name and path of an association resource are derived from the property name in the entity. You can customize the relation name and path using `@RestResource` on the association property. Therefore, clients should read the `href` provided by the server instead of constructing URLs from class names or field names.

## 3. Comparing the Two Concepts

| Criterion | HAL link | Association resource |
|---|---|---|
| Nature | Link metadata in a representation | REST endpoint representing an association |
| Location | Usually inside `_links` | Accessed via the URI in `href` |
| Key components | Relation name and `href` | Association state and supported HTTP operations |
| Role | Helps clients discover and navigate | Allows reading or modifying an association |
| Does it contain association data itself? | No; it primarily describes the link target | Can return the current state or the linked resources |
| Example | `_links.customer.href` | `/orders/42/customer` |

Remember: a HAL link is the "address advertised in the response"; an association resource is the "REST target that can be called to manipulate the association." The two concepts are closely related, but they are not synonymous.

## 4. Reading and Manipulating an Association Resource

### 4.1. Reading an association

The first step is to read the item resource and extract the URI from the corresponding relation:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

After locating the `customer` link, the client calls that link's URI:

~~~http
GET /orders/42/customer
Accept: application/hal+json
~~~

The association resource returns the current state of the association. For a to-one association, the response can be the representation of the currently linked `Customer`. For a collection association, the response can be a collection representation containing the linked resources.

Do not guess the Customer's URI from an ID or database structure. Follow the `href` advertised by the server.

### 4.2. Assigning a to-one association with PUT

For a to-one association, such as an `Order` having a `Customer`, Spring Data REST uses `PUT` against the association resource. The body contains the URI of the resource to link, and the `Content-Type` is `text/uri-list`.

Example assigning Customer 7 to Order 42:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/customers/7" \
  "http://localhost:8080/orders/42/customer"
~~~

Key points to remember:

- The request is sent to the association resource `/orders/42/customer`.
- The body is the Customer's URI, not a JSON object containing the Customer's fields.
- `Content-Type` must be `text/uri-list`.
- For a to-one association, send only one URI. Sending multiple URIs for a to-one association can result in `400 Bad Request`.

After updating, read the association resource again with `GET` to confirm the association now points to Customer 7. Depending on response body configuration, update operations may return `204 No Content`; a response without a body does not mean the operation failed.

### 4.3. Adding an item to a collection association with POST

Suppose an `Article` has a collection association to multiple `Tag` entities:

~~~java
@ManyToMany
private Set<Tag> tags = new HashSet<>();
~~~

The Article's item resource can expose a `tags` link pointing to the collection's association resource, such as `/articles/1/tags`.

To add Tag 5 to the collection, use `POST` and send the Tag's URI:

~~~bash
curl -i -X POST \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/tags/5" \
  "http://localhost:8080/articles/1/tags"
~~~

`POST` on an association resource is only supported for collection associations and means adding an item to the collection. The body is still the URI of the resource to link, with `Content-Type: text/uri-list`.

### 4.4. Unbinding an association with DELETE

`DELETE` on an association resource means unbinding the link. It does not mean deleting the entity on the other side.

For example, if `customer` is an optional association on `Order`, you can call:

~~~http
DELETE /orders/42/customer
~~~

This operation removes the `customer` association from Order 42; it does not delete Customer 7 from `/customers/7`.

If the association is required or does not allow null values, Spring Data REST may return `405 Method Not Allowed`. Check the mapping, configuration, and actual HTTP status before concluding that the endpoint is broken.

Do not assume that `DELETE` on a collection association always means removing a single item. Read the exposed API and verify the exact endpoint supported by the server.

## 5. Same PUT Method, Two Different Resource Types

A common mistake is using `PUT` on an item resource and `PUT` on an association resource as if they took the same body.

| Request | Meaning | Typical body |
|---|---|---|
| `PUT /orders/42` | Replace the state of Order 42 | JSON representation of the Order |
| `PATCH /orders/42` | Partially update the state of Order 42 | JSON or supported patch document |
| `PUT /orders/42/customer` | Bind a Customer resource to the `customer` association | URI, `Content-Type: text/uri-list` |
| `POST /articles/1/tags` | Add a Tag resource to the `tags` collection association | URI, `Content-Type: text/uri-list` |

The target URI determines which resource is being operated on. The `Content-Type` and body structure must match that resource type.

Association resources have their own set of HTTP methods: `GET` to read, `PUT` to bind a resource by URI, `POST` to add an item to a collection association, and `DELETE` to unbind the association. Do not mechanically apply item resource `PUT`/`PATCH` rules to association endpoints.

## 6. Correct Client Workflow

When you need to manipulate an association in Spring Data REST, follow this sequence:

1. Call `GET` on a collection or item resource that the client already knows.
2. Read the relation name in `_links`, such as `customer` or `tags`.
3. Take the exact URI from the `href` property. If the link is a URI template, fill in the parameters according to the advertised template.
4. Call `GET` on the association resource to inspect the current state if needed.
5. Choose the HTTP method based on the association type: `PUT` for a to-one link; `POST` to add an item to a collection; `DELETE` to unbind the association when the mapping allows it.
6. For `PUT`/`POST` to an association resource, send the related resource's URI with `Content-Type: text/uri-list`.
7. Check the status code and read the association resource again to confirm the result.

If the server customizes the relation name or path with `@RestResource`, the client can still follow the exact same workflow because the actual URI is provided in the HAL response.

## 7. Common Mistakes

- **Confusing the link with the endpoint:** seeing `_links.customer` and assuming the JSON link object is the Customer data. Call the `href` to read the association resource or target resource.
- **Constructing URLs manually:** assembling `/orders/{id}/customer` from the field name even though the path may have been customized. Always prefer `href`.
- **Sending JSON instead of a URI:** association resources require `text/uri-list` for `PUT`/`POST`; an entity JSON object is not an equivalent payload.
- **Using POST for a to-one association:** `POST` is supported for collection associations. For to-one associations, use `PUT`.
- **Sending multiple URIs for a to-one association:** Spring Data REST may return `400 Bad Request` because the association only accepts a single resource.
- **Treating DELETE as entity deletion:** deleting an association only unbinds the link per association resource semantics; the referenced entity can still exist.
- **Assuming every HAL link is an association:** links such as `self`, `profile`, `search`, or pagination serve API navigation and discovery.
- **Inferring failure from an empty response:** `204 No Content` is a valid success result for many update operations. Check the status code.
- **Ignoring domain configuration:** required associations, non-exported repository methods, or exposure settings can affect which methods are supported.

## 8. Self-Check Exercises

A `GET /orders/42` response contains:

~~~json
{
  "orderNumber": "ORD-042",
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    },
    "customer": {
      "href": "http://localhost:8080/orders/42/customer"
    }
  }
}
~~~

**Question 1.** Which URI is the item resource of Order 42?

**Question 2.** Which URI is the association resource for the `customer` property?

**Question 3.** To assign Customer 7 to Order 42, which method should you call, to which URI, and with what `Content-Type`?

**Question 4.** If `DELETE /orders/42/customer` succeeds, is Customer 7 deleted from the repository?

**Answers:**

1. `/orders/42` is the item resource.
2. `/orders/42/customer` is the association resource.
3. Call `PUT` on `/orders/42/customer`, sending the URI `http://localhost:8080/customers/7` with `Content-Type: text/uri-list`.
4. No. `DELETE` unbinds the association; it is not a command to delete the Customer resource.

## 9. Key Takeaways

- A HAL link is navigation metadata inside a representation, typically under `_links`.
- An association resource is the endpoint representing the relationship between an item resource and its linked resource(s).
- A HAL link can point to an association resource; the link and the resource are two distinct concepts.
- For an association resource, `GET` reads the association, `PUT` binds by URI, `POST` adds an item to a collection, and `DELETE` unbinds when the mapping allows.
- Use the `href` advertised by the server, the proper HTTP method, and `Content-Type: text/uri-list` for linking operations.

## References

- Spring Data REST Reference — Repository resources: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST Reference — The Association Resource section describing `GET`, `PUT`, `POST`, `DELETE`, and the `text/uri-list` media type.
