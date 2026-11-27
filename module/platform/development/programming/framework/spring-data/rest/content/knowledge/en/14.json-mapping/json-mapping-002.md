# Serializing Managed Objects and Regular Nested Objects in Spring Data REST

## Objectives

After this lesson, you will be able to distinguish a persistent entity managed by Spring Data from a regular nested object; predict how each type appears in JSON/HAL; understand why associations are typically represented as links; and choose the right approach when you need to embed data, handle circular references, or accept JSON input.

## 1. Two Object Categories Have Different Roles

A domain model typically contains both standalone entities and objects that only make sense inside another entity.

- **A managed persistent entity** is a type that Spring Data recognizes via the mapping context. An entity usually has its own identity, its own persistence lifecycle, and can be accessed via a repository resource if the repository is exported.
- **A regular nested object** is an object/value object residing inside an entity, without an independent repository resource. It usually describes part of the parent entity's value, such as contact information, coordinates, a time range, or display configuration.

The two categories of objects are not necessarily serialized the same way. Spring Data REST integrates with Jackson to understand persistent entity and association metadata. Jackson also serializes regular beans/value objects according to its property rules.

Example of a Customer with an independent Department and ContactInfo as a value object:

```java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne
    private Department department;

    @Embedded
    private ContactInfo contactInfo;

    // Constructor, getters, and setters
}

@Entity
public class Department {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    // Constructor, getters, and setters
}

@Embeddable
public class ContactInfo {

    private String phone;
    private String timezone;

    // Constructor, getters, and setters
}
```

In this example, `Department` is an entity with its own identity; `ContactInfo` is a value stored alongside Customer and has no separate repository item resource.

## 2. Persistent Entities Are Represented as Resources and Links

When Spring Data REST returns a persistent entity in HAL, the response is a resource representation. The resource contains the entity's data and hypermedia links describing how to access itself or related associations.

Abbreviated example response for Customer:

```json
{
  "name": "Ada Lovelace",
  "contactInfo": {
    "phone": "+84-28-5555-0101",
    "timezone": "Asia/Ho_Chi_Minh"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/customers/42"
    },
    "department": {
      "href": "http://localhost:8080/customers/42/department"
    }
  }
}
```

Here:

- `name` is a property of Customer, so it is included in the representation.
- `contactInfo` is a nested value object, so it appears as a JSON object.
- `department` is an association to another persistent entity; Spring Data REST represents the relationship as a link in `_links`, rather than expanding the entire Department into a nested object in the body by default.
- `self` points to the Customer item resource.

An association link typically points to an association resource, through which clients can read or modify the relationship using operations supported by the API. When Department information is needed, the client follows the link provided by the server. This keeps representations compact and helps avoid recursively serializing the entire object graph.

Specific links depend on repository exposure, mapping, relation names, and configuration. If a repository or association is hidden, clients may not see the corresponding link. Discover the API root and HAL responses rather than assuming URLs.

## 3. Regular Nested Objects Are Serialized Inline

A POJO or value object not recognized as a persistent association is typically serialized by Jackson directly inside the parent object's property. Properties may come from getters, fields, or constructor mapping depending on Jackson configuration.

For example, `ContactInfo` has no separate ID or repository. When Customer is serialized, this object is rendered directly:

```json
{
  "contactInfo": {
    "phone": "+84-28-5555-0101",
    "timezone": "Asia/Ho_Chi_Minh"
  }
}
```

There is no `self` link for ContactInfo because it is not an independent resource. Clients read and update these values through Customer or a business API designed by the application.

If the nested property is a collection of regular objects, Jackson typically produces a JSON array:

```json
{
  "preferences": [
    {
      "channel": "email",
      "enabled": true
    },
    {
      "channel": "sms",
      "enabled": false
    }
  ]
}
```

Nested objects/value objects are usually suited for data whose lifecycle is tied to the parent entity. If an object needs its own identity, separate access control, independent querying, or sharing across multiple entities, consider modeling it as a persistent entity with a repository resource.

## 4. Comparing the Two Representations

| Characteristic | Persistent entity association | Regular nested object |
| --- | --- | --- |
| Separate identity | Usually has its own ID | Usually has no independent identity |
| Repository resource | Available if the repository is exported | None by default |
| HAL representation | Usually a link in `_links` | Inline JSON object in the property |
| Accessing details | Follow the link to the resource/association | Read along with the parent entity's representation |
| Updating relationship/values | Use the association resource or appropriate entity operation | Update the nested property via the parent entity or a custom API |
| Lifecycle | Can exist independently | Usually tied to the parent entity |

This table describes common Spring Data REST behavior for persistent associations and value objects. Actual results also depend on the mapping context, repository exposure, projections, Jackson annotations, and custom serializers.

## 5. HAL Links and Embedded Resources Are Different from Regular Nested Objects

In HAL, `_links` contains URIs for discovering or interacting with resources. `_embedded` contains representations of other resources embedded in the response. A regular nested object, on the other hand, appears as a normal domain property, such as `contactInfo`.

For example, all three forms can appear in a single response:

```json
{
  "name": "Ada Lovelace",
  "contactInfo": {
    "phone": "+84-28-5555-0101"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/customers/42"
    },
    "department": {
      "href": "http://localhost:8080/customers/42/department"
    }
  },
  "_embedded": {
    "recentOrders": [
      {
        "description": "Laptop order",
        "_links": {
          "self": {
            "href": "http://localhost:8080/orders/100"
          }
        }
      }
    ]
  }
}
```

In the example:

- `contactInfo` is a value object serialized inline.
- `_links.department` is a link to the association resource.
- `_embedded.recentOrders` is a representation of Order resources embedded via a representation mechanism such as a projection/excerpt or appropriate configuration.

Do not treat every nested object in JSON as an embedded persistent entity. Determine whether a property is a value object, an association link, or an embedded resource based on the mapping and HAL structure.

## 6. Using Projections When Related Data Needs to Be Displayed

By default, associations of persistent entities are usually represented as links. If a client needs part of a related entity's data directly in the response, you can use an appropriate projection instead of serializing the entire object graph by default.

Example projection for Department:

```java
@Projection(name = "departmentSummary", types = Department.class)
public interface DepartmentSummary {

    String getName();
}
```

Projection for Customer:

```java
@Projection(name = "customerWithDepartment", types = Customer.class)
public interface CustomerWithDepartment {

    String getName();

    DepartmentSummary getDepartment();

    ContactInfo getContactInfo();
}
```

The client can request a registered projection:

```http
GET /customers/42?projection=customerWithDepartment
Accept: application/hal+json
```

A projection defines a view of the representation. Whether an association is rendered inline or as embedded/linked also depends on how Spring Data REST applies the projection and the media type. Inspect the actual response and use the exact links/structure exposed by the server.

For collection resources, an excerpt projection can define a summary representation for embedded elements. This keeps collections more compact while item resources can still provide a more detailed representation.

## 7. Sending JSON Input: Association URIs and Nested Value Objects

How requests are sent also reflects the difference between the two property types.

If `department` is an association to an existing persistent entity, clients typically send the URI of the related resource:

```http
POST /customers
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Ada Lovelace",
  "department": "http://localhost:8080/departments/7",
  "contactInfo": {
    "phone": "+84-28-5555-0101",
    "timezone": "Asia/Ho_Chi_Minh"
  }
}
```

In this payload:

- `department` is a URI referencing an existing Department entity.
- `contactInfo` is a regular JSON object; Jackson deserializes it into the nested ContactInfo in Customer.

Do not send a nested object containing Department's `id` assuming Spring Data REST will automatically look up the corresponding entity. A URI clearly expresses the intent to reference a managed resource. If you want to create a new Department, create that resource via its collection endpoint first, obtain its URI from `Location` or the `self` link, and then use that URI in the Customer request.

For value objects, send a JSON object matching the property shape exposed by the domain class and Jackson. There is no need to create a repository or URI for a value object stored solely as part of its parent entity.

## 8. Circular References and Deeply Nested Object Graphs

An object graph can contain bidirectional relationships:

```java
class Parent {
    private List<Child> children;
}

class Child {
    private Parent parent;
}
```

If Jackson serializes both sides directly without a control mechanism, it can loop Parent → Child → Parent until hitting an error or resource limit. With persistent entities, Spring Data REST typically uses association links to avoid unbounded expansion of relationships. With regular POJOs/value objects, Jackson still requires a serializable object graph structure.

Several approaches to handle this:

- Design value objects without circular references; keep nested objects as one-way structures.
- Use DTOs or projections to clearly define the depth of returned data.
- For regular Jackson object graphs, consider `@JsonManagedReference` and `@JsonBackReference` or `@JsonIdentityInfo` when the application semantics fit.
- Use `@JsonIgnore` on properties that should not appear in JSON, after carefully assessing the impact on both input and output.
- For Spring Data REST associations, prefer hypermedia links or projections/excerpts instead of forcing the serializer to expand the entire entity graph.

Do not mechanically add these Jackson annotations to persistent associations. They can alter property serialization or remove information Spring Data REST needs to generate links. Inspect the representation after configuring.

## 9. Impact of Jackson Annotations and Custom Serializers

Jackson determines how POJOs/value objects are serialized through property visibility, naming strategies, mix-ins, annotations, custom serializers, and registered modules.

Some common annotations:

- `@JsonProperty` renames a property or controls access when reading/writing JSON.
- `@JsonIgnore` skips a property during JSON mapping.
- `@JsonInclude` controls conditions for including a property in output, such as omitting null values.
- `@JsonFormat` formats dates, times, or supported data types.
- `@JsonUnwrapped` flattens a nested object's properties to the same level as the parent; consider name collisions and deserialization compatibility.

Spring Data REST configures Jackson with its own modules to handle persistent entities and hypermedia. When you need to add custom serializers or modules, extend ObjectMapper through a supported configuration point, such as `RepositoryRestConfigurer.configureJacksonObjectMapper(...)`. Avoid replacing the default ObjectMapper with a self-constructed instance that drops registered Spring Data REST/HATEOAS modules.

Example configuration adding modules through the configurer:

```java
@Configuration
class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureJacksonObjectMapper(ObjectMapper objectMapper) {
        // Register necessary custom modules or mix-ins.
        // Preserve modules already configured by Spring Data REST.
    }
}
```

If a custom serializer changes how a persistent association is written to JSON, verify that HAL links and association resolution still work as expected.

## 10. Performance, Lazy Loading, and Response Size

Inline nested objects are convenient because clients receive data in a single response, but overly deep object graphs or large nested collections can bloat payloads. With an ORM like JPA, serializing lazy-loaded properties can trigger additional queries; multiple associations can lead to N+1 queries or lazy initialization errors if the session has already closed.

Association links keep responses compact and allow clients to load only the resources they need, at the cost of potentially issuing more HTTP requests. Projections and excerpt projections help select needed data; optimal fetch plans/queries still must be designed at the persistence layer.

When deciding between inline and linked, consider:

- Does the object have an identity and require independent access?
- Do clients frequently need all of the nested data?
- Can the collection grow large?
- Is the relationship lazy-loaded or likely to generate many queries?
- Is the data sensitive or in need of separate authorization?

## 11. How to Verify the Actual Representation

After implementing, verify responses by:

1. Calling the API root to find the repository's collection link.
2. Calling an item resource and inspecting regular properties, `_links`, and `_embedded`.
3. Confirming that associations to persistent entities appear as links published by the server.
4. Confirming that value objects/POJOs are serialized inline with the expected properties.
5. Testing projections if clients need part of a related entity's data.
6. Checking nested objects for circular references or large collections.
7. Checking SQL logs and query counts if serialization accesses JPA associations.
8. Testing POST/PATCH requests to confirm association URIs and nested value objects are deserialized properly.

Example reading Customer:

```bash
curl -i http://localhost:8080/customers/42 \
  -H "Accept: application/hal+json"
```

Reading Department via the returned association link:

```bash
curl -i http://localhost:8080/customers/42/department \
  -H "Accept: application/hal+json"
```

The association path in the example is illustrative; in a real application, use the exact URI from `_links` in the response.

## Summary

- Spring Data REST recognizes persistent entities via mapping metadata and represents resources/associations following hypermedia conventions.
- Associations to managed entities typically appear as links in `_links`, rather than automatically embedding the entire entity.
- POJOs/value objects without their own resource identity are typically serialized inline by Jackson as JSON objects or arrays inside the parent entity.
- `_links`, `_embedded`, and regular nested object properties are three distinct structures.
- Projections/excerpt projections can provide a view of related data without serializing the entire object graph.
- For JSON requests, associations to existing entities typically use URIs; nested value objects are sent as JSON objects.
- Control circular references, lazy loading, payload size, and authorization when choosing a representation strategy.

## References

- [Spring Data REST — Repository resources and representations](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing the Jackson ObjectMapper](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Projections and excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data Commons — Mapping metadata](https://docs.spring.io/spring-data/commons/reference/object-mapping.html)
- [Jackson annotations](https://github.com/FasterXML/jackson-annotations)
