# Distinguishing Default Excerpts from Client-Requested Projections

Spring Data REST can return multiple representations for the same entity. A collection typically needs a compact representation to display a list; when opening an item, the client may need additional properties; another screen may only need a specific subset of fields. An **excerpt projection** lets a repository preselect a default representation for entities embedded in collections. A **client-requested projection** lets the client choose an application-published projection using the `projection` parameter.

Both mechanisms rely on projection interfaces, but they differ in where the selection happens and when they apply.

## 1. What is a projection?

A projection is a view of an entity exposing only the properties needed by a use case. In Spring Data REST, a projection is usually declared using an interface annotated with `@Projection`.

Example entity:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phone;
    private String internalNote;

    // getters and setters
}
```

A projection showing only summary information:

```java
@Projection(name = "summary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();

    String getEmail();
}
```

When the representation uses this projection, the `phone` and `internalNote` properties are absent from the view defined by the interface. A projection changes the shape of the returned data; it does not create a new entity, does not update the database, and does not alter domain object mappings.

Spring Data REST discovers projections according to the application's package scanning rules. Place the interface in an appropriate package for the domain type and verify it is exported before using it in URLs. The name in `@Projection(name = "summary", ...)` is the name clients pass in the query parameter, which does not necessarily match the Java interface name.

## 2. Client-requested projections

When the application exposes a projection, clients can select it via the `projection` query parameter. For example:

```http
GET /people/42?projection=summary HTTP/1.1
Host: api.example.test
Accept: application/hal+json
```

The client is requesting the representation of Person 42 using the projection named `summary`. If the repository and endpoint support that projection, Spring Data REST returns the corresponding view.

A projection can also be requested on a collection:

```http
GET /people?projection=summary&page=0&size=20 HTTP/1.1
Accept: application/hal+json
```

In this case, the client asks for collection items to be represented using the `summary` projection. Pagination and sorting parameters can still be combined with the projection; they control the result set and paging, while the projection controls which properties are rendered.

The key point is that clients can only choose projections defined and published by the server. The `projection` query parameter does not allow a client to arbitrarily request any field on the entity.

## 3. What is an excerpt projection?

An excerpt projection is a projection configured on a repository as the default representation for entities embedded in collection responses. Clients do not need to add `?projection=...` to trigger that excerpt.

Example:

```java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();
}
```

Repository configuring the excerpt:

```java
@RepositoryRestResource(
    collectionResourceRel = "people",
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

When a client reads the `GET /people` collection, Persons embedded in the collection use the configured excerpt projection. The client does not need to know or send the excerpt name in the query string to receive that default view.

Excerpts are especially useful when a collection contains many entities or entities have complex associations. A compact list representation avoids repeatedly returning related data and reduces payload size. When a user opens an item, the client can call the item resource and request a more detailed projection if the API publishes one.

Excerpt projections are configured at the repository resource level. If multiple repositories export the same domain type, each repository may need an excerpt choice suited to its collection resource.

## 4. Where do they differ?

| Aspect | Excerpt projection | Client-requested projection |
|---|---|---|
| Who chooses the view? | Developer configures it on the repository | Client chooses an exposed projection name |
| How it is triggered | Automatically per repository excerpt configuration | Query parameter `?projection=name` |
| Common purpose | Compact default view for items embedded in collections | Specific view for a screen or use case |
| Does the client need to know the name? | No need to send the name to use the default excerpt | Yes, the client sends the projection name |
| Configuration scope | Repository resource | Projection defined and exported for the domain type |
| Changes stored data? | No | No |

Both are ways to construct representations. They do not change the entity in the database and do not replace authorization rules.

## 5. Excerpts typically apply to collection representations

A common point of confusion is that an excerpt projection is configured for collection resources, where entities are embedded inside `_embedded`. It should not be misunderstood as a rule that automatically trims every item access.

Example client calling a collection:

```http
GET /people HTTP/1.1
Accept: application/hal+json
```

Illustrative response:

```json
{
  "_embedded": {
    "people": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "_links": {
          "self": {
            "href": "https://api.example.test/people/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/people"
    }
  }
}
```

The fields inside the embedded Person reflect the configured excerpt projection. The `self` link still lets the client navigate to the item resource.

When the client calls the item directly:

```http
GET /people/42 HTTP/1.1
Accept: application/hal+json
```

The default representation of the item may contain a different set of properties than the collection's excerpt. If a well-defined view is needed, the client can request an exposed projection:

```http
GET /people/42?projection=summary HTTP/1.1
Accept: application/hal+json
```

Thus, an excerpt handles how a collection presents embedded items; the projection query parameter lets clients request a specific view at endpoints that support projections.

## 6. Multiple projections for multiple use cases

A single domain type can have multiple projections. Example:

```java
@Projection(name = "summary", types = Person.class)
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}

@Projection(name = "contact", types = Person.class)
public interface PersonContact {
    String getFirstName();
    String getLastName();
    String getEmail();
    String getPhone();
}
```

The client can choose:

```http
GET /people/42?projection=summary
GET /people/42?projection=contact
```

The `summary` view suits a short list; `contact` suits a screen requiring contact details. These names and fields are just examples; the application should pick data matching its API contract.

You can define derived properties in a projection using Spring Expression Language when appropriate:

```java
@Projection(name = "display", types = Person.class)
public interface PersonDisplay {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
```

The `displayName` property is computed from the entity when creating the representation. It is not a new column in the database and is not written back to the entity via the projection.

## 7. Projections and associations

A projection can declare getters for associations. When doing so, the representation can include additional related data in the way the projection defines.

Example:

```java
@Projection(name = "orderSummary", types = Order.class)
public interface OrderSummary {

    String getOrderNumber();

    OrderStatus getStatus();

    Customer getCustomer();
}
```

Including associations in a projection can make responses larger or create deeply nested structures. Consider the number of relationships, how serialization behaves, and the cost of querying related data. Avoid pulling an entire entity graph into one projection simply because getters can be declared.

Excerpt projections are often helpful for controlling data depth and size in collections. Client-requested projections are useful when a specific use case needs extra associations or properties. Either way, inspect actual responses and avoid creating oversized payloads.

## 8. Projections are not a security mechanism

If a field does not appear in a projection, that only means the field is omitted from the representation currently in use. It does not mean callers are forbidden from reading that field on every endpoint or via every other projection.

For example, excluding `internalNote` from `PersonSummary` does not guarantee this data is protected. If the server exposes another projection containing that field or another endpoint returning it, callers can still access it without proper authorization.

Therefore:

- Use projections to shape responses for each use case.
- Use Spring Security for authentication and authorization.
- Do not expose projections containing sensitive data to unauthorized callers.
- If sensitive data depends on the specific user or record, enforce permission checks on the server on the actual request.
- Do not treat hiding links or omitting fields from an excerpt as access control.

Projections are also not write DTOs. They primarily define how an entity is read/represented. If a separate write contract is needed, design an appropriate input model or endpoint instead of using projections as an entity update mechanism.

## 9. How to choose between an excerpt and a requested projection

You can use the following questions to decide:

| Need | Suitable choice |
|---|---|
| Every collection of a repository needs a compact default view | Configure an excerpt projection |
| Different screens need different fields | Define multiple projections and let clients choose |
| Item detail needs a specific view | Client requests a projection on the item URI |
| Collection needs a different view per use case | Client requests a projection on the collection if the endpoint supports it |
| Sensitive fields need protection | Authorization and permission-based representation design; do not rely solely on projections |

A common setup is configuring a compact excerpt projection for collections, then publishing more detailed projections for screens needing additional data. Clients use the item link to open details and pass `?projection=...` when they want a server-supported view.

## 10. Client workflow for discovering and requesting projections

1. Start from the collection link published by Spring Data REST.
2. Read the collection representation and embedded items; this may be the default excerpt.
3. Follow the item's `self` link to open the detailed resource.
4. If a specific view is needed, use a projection name published by the API and append `projection=name`.
5. Read the HAL response and inspect actual fields; do not assume the projection contains every entity property.
6. Keep server-side authorization checks active for every request, including requests selecting projections.

When configuring an excerpt projection on a repository, the application decides in advance how collections display embedded items. When publishing named projections, clients can choose a view suited to their use case. Clearly distinguishing these two mechanisms keeps collections compact, allows items to expand on demand, and makes the HAL contract easier to discover.
