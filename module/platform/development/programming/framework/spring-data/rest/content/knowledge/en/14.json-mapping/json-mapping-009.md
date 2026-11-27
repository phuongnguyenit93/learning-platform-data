# Bidirectional Relationships, JSON Loops, and Hibernate Proxy Impact in Spring Data REST

## Objectives

In JPA models, two entities often reference each other. For example, an Order has a list of OrderLines, while each OrderLine holds a reference back to Order. This relationship makes sense at the domain and database layers, but can cause trouble when converting the object graph into JSON.

Jackson can traverse from Order to lines, from each line back to Order, and then down to lines again. Without handling rules, serialization can loop infinitely or throw an error due to a cyclic object graph.

Hibernate introduces a second issue: LAZY relationships are typically represented by proxies or uninitialized persistent collections. When Jackson calls getters to serialize, Hibernate may have to query the database. If the Session has already closed, that operation can trigger `LazyInitializationException`.

This lesson distinguishes three layers of problems:

1. **JPA bidirectional relationships:** how entities reference one another.
2. **JSON/HAL representations:** how Jackson and Spring Data REST turn object graphs into responses.
3. **Persistence context lifecycle:** when Hibernate proxies can load data.

## 1. Bidirectional Relationship Example

Suppose an order has many order lines, and each order line belongs to exactly one order.

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public void removeLine(OrderLine line) {
        lines.remove(line);
        line.setOrder(null);
    }

    // getters and setters
}
~~~

~~~java
@Entity
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;

    private int quantity;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    // getters and setters
}
~~~

This is a bidirectional relationship:

- `PurchaseOrder.lines` is the parent side, holding multiple OrderLines.
- `OrderLine.order` is the child side, pointing back to PurchaseOrder.
- `mappedBy = "order"` indicates OrderLine is the owning side of the relationship.
- The foreign key `order_id` resides on the order-line table.

The `addLine` and `removeLine` methods synchronize both sides in memory. If you only add an element to `order.getLines()` without setting `line.setOrder(order)`, the object graph can become inconsistent and JPA may not persist the relationship as intended.

## 2. Why Can JSON Loop Infinitely?

A regular serializer traverses getters and converts returned values into JSON. With the relationship above, the traversal path can be:

~~~text
PurchaseOrder
  └── lines
       └── OrderLine
            └── order
                 └── lines
                      └── OrderLine
                           └── order
                                └── ...
~~~

If Jackson serializes the entire graph directly without cycle-handling mechanisms, it can keep bouncing between parent and child until failing from excessive recursion or a serialization error.

For example, the desired JSON might only need:

~~~json
{
  "id": 42,
  "orderNumber": "PO-2026-0042",
  "lines": [
    {
      "id": 1,
      "sku": "KB-01",
      "quantity": 2
    },
    {
      "id": 2,
      "sku": "MS-02",
      "quantity": 1
    }
  ]
}
~~~

There is no need to repeat the entire PurchaseOrder inside every OrderLine. An intentional representation typically expresses only one direction of the relationship or uses an ID/link to reference back.

## 3. Spring Data REST Handles Associations with HAL Links by Default

Distinguish standard JSON serialization from representations produced by Spring Data REST.

Spring Data REST uses a specially configured ObjectMapper with dedicated serializers. The framework attempts to represent managed associations as hypermedia links instead of always embedding entire linked entities like regular POJOs.

For instance, an Order item resource can be returned as:

~~~json
{
  "id": 42,
  "orderNumber": "PO-2026-0042",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/42"
    },
    "lines": {
      "href": "http://localhost:8080/api/orders/42/lines"
    }
  }
}
~~~

Clients follow the `lines` link to read the association resource. Each OrderLine can have its own item resource if its corresponding repository is exported.

This representation avoids expanding the entire relationship graph on every response by default. Clients only load associations when needed, via URLs published by the server.

Important points:

- Spring Data REST typically generates association links based on the relationship property name.
- Path and relation can be changed using `@RestResource` on the property.
- Projections, excerpts, custom serializers, or custom controllers can alter how the object graph is serialized.
- If custom code returns entities directly through a different ObjectMapper, Spring Data REST's HAL rules may no longer apply.

Therefore, if a Spring Data REST response exhibits a JSON loop, determine whether the request goes through the repository exporter or a custom controller/serializer before adding annotations to entities. Not every bidirectional relationship automatically causes a loop in default HAL responses.

## 4. Approach 1: JsonManagedReference and JsonBackReference

Jackson provides a pair of annotations to mark the forward and back directions of a bidirectional relationship.

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @JsonManagedReference("order-lines")
    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
    private List<OrderLine> lines = new ArrayList<>();

    // getters and setters
}
~~~

~~~java
@Entity
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    private String sku;

    @JsonBackReference("order-lines")
    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;

    // getters and setters
}
~~~

Meaning:

- `@JsonManagedReference` marks the parent/forward direction. This property is serialized normally.
- `@JsonBackReference` marks the child/back direction. The back property is omitted during serialization.
- When deserializing, Jackson uses the back reference to re-assign the parent reference on the child.
- The name value must match between the two annotations. Distinct names are useful when a class has multiple relationship pairs.

With the example above, JSON can contain Order and its lines list without repeating Order inside each line.

**Note on annotation placement:** `@JsonBackReference` must be placed on a single bean-typed property, such as `OrderLine.order`. Do not place it on a collection, array, or Map. The parent-side collection is where `@JsonManagedReference` belongs.

This approach fits simple parent-child trees. If a domain has many cross-references, multiple parents, or needs ID-based references, consider another approach instead of wiring hard-to-follow managed/back reference pairs.

## 5. Approach 2: JsonIdentityInfo and JsonIdentityReference

If you want to preserve bidirectional reference structure without repeating objects, you can use Jackson's object identity.

~~~java
@Entity
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    private String orderNumber;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

~~~java
@Entity
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    private String sku;

    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;
}
~~~

Jackson serializes the first occurrence of an object with all its properties plus its object ID. When encountering the same object again in the graph, the serializer can write an ID reference instead of re-serializing the entire object.

Illustrative example:

~~~json
{
  "id": 42,
  "orderNumber": "PO-2026-0042",
  "lines": [
    {
      "id": 1,
      "sku": "KB-01",
      "order": 42
    }
  ]
}
~~~

The exact shape depends on serialization order and identity configuration. If you want a property to always be represented by ID, you can also add `@JsonIdentityReference(alwaysAsId = true)` on the relationship property:

~~~java
@JsonIdentityReference(alwaysAsId = true)
@ManyToOne(fetch = FetchType.LAZY)
private PurchaseOrder order;
~~~

Watch out for the following with this approach:

- IDs must be unique within the configured identity generator/scope.
- Clients must understand that the reference value is an ID, not a full object.
- When deserializing a graph, Jackson must resolve the ID back to the corresponding object; if the ID is not defined in the payload or a resolver cannot locate it, reading JSON can fail.
- This is a Jackson serialization/deserialization rule and does not automatically replace Spring Data REST's association resources and URIs.

Do not choose JsonIdentityInfo just to "hide a loop error." First define the JSON contract that clients need to receive.

## 6. Approach 3: JsonIgnore or JsonProperty for One-Way Control

If the API does not need to return the back-reference, you can drop the back-reference property from JSON altogether:

~~~java
@Entity
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    private String sku;

    @JsonIgnore
    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;
}
~~~

During serialization, the `order` property is skipped and the loop is cut at the child.

However, `@JsonIgnore` generally affects both serialization and deserialization of the logical property. If you want clients to only read a field without writing it, you can use:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private PurchaseOrder order;
~~~

Or if you only want to accept input from requests without outputting it in responses:

~~~java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private PurchaseOrder order;
~~~

These are Jackson rules for JSON properties. When applying them to entities managed by Spring Data REST, test item representations, association links, and request bodies. Annotations can alter how the framework detects and serializes properties, so do not apply them broadly just to eliminate a loop in a custom endpoint.

## 7. Comparing Loop-Prevention Strategies

| Strategy | JSON Response | Deserialization | Suitable When |
| --- | --- | --- | --- |
| HAL association link | Returns links to related resources | Uses association endpoints/URIs | A Spring Data REST API wants clients to navigate via HATEOAS |
| JsonManagedReference / JsonBackReference | Keeps forward direction, omits back direction | Jackson rebinds the back reference | Simple parent-child trees |
| JsonIdentityInfo | First object in full, subsequent references as ID | Needs object ID resolution | Graphs with many cross-references |
| JsonIgnore | Omits property from JSON | Usually skips property on read too | API does not need that reference direction |
| JsonProperty Access | Chooses read-only or write-only | Follows the configured access mode | Field may only be read or only written |
| DTO / projection | Outputs only selected fields | Dedicated mapping or read model | API contract needs strict control |

No single annotation fits every domain model. Choose based on the representation clients need, request deserialization requirements, and how Spring Data REST manages associations.

## 8. What Is a Hibernate Proxy?

Hibernate typically uses lazy loading to avoid loading every association immediately when reading an entity. With `FetchType.LAZY`, a relationship can be represented by a proxy or an uninitialized persistent collection.

Example:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

When querying PurchaseOrder, Hibernate may only fetch order columns. The customer property may be a proxy holding only the identifier; lines may be a persistent collection whose data has not been read yet.

When a getter is called, Hibernate may need to query the database to load the real data. This saves queries and memory when associations go unused.

A proxy is not a fully loaded entity. It is a stand-in object for the entity/collection and requires an active persistence context to load missing data.

## 9. LazyInitializationException When Serializing After Session Closes

Hibernate throws `LazyInitializationException` when code accesses unloaded data outside an open Session. A common scenario:

1. A repository fetches PurchaseOrder.
2. A service returns the entity after the transaction ends.
3. The entity becomes detached; the customer proxy or lines collection remains uninitialized.
4. Jackson starts serializing and calls `getCustomer()` or iterates `getLines()`.
5. Hibernate no longer has a Session to load the data and throws `LazyInitializationException`.

Typical error in logs:

~~~text
org.hibernate.LazyInitializationException:
could not initialize proxy - no Session
~~~

Or:

~~~text
failed to lazily initialize a collection of role:
PurchaseOrder.lines: could not initialize proxy - no Session
~~~

This is a persistence context lifecycle issue, not a JSON loop. Adding `@JsonManagedReference` can break a loop, but it will not open a Session or load needed associations.

Conversely, keeping a Session open does not solve loops either: Jackson can still traverse parent-child-parent if the representation serializes the entire graph.

## 10. Open EntityManager in View and Queries Triggered During Serialization

In Spring Boot servlet applications, Open EntityManager in View is enabled by default under default configuration. Spring registers an interceptor to keep the EntityManager open during web request processing, enabling lazy loading in the view layer.

It can be disabled via:

~~~properties
spring.jpa.open-in-view=false
~~~

When OSIV is enabled, Jackson or Spring Data REST can touch proxies during serialization and trigger SQL statements during response rendering, even after the service transaction has finished. This can cause:

- Responses that work in development but fail when OSIV is disabled in production.
- A single response iterating over multiple entities triggering many extra queries (N+1).
- Query execution spread between the service layer and serialization, making it harder to observe.
- An association thought to be just a link/preview triggering data loads because a custom serializer or projection invokes getters.

OSIV is an architectural trade-off, not a fetch-plan solution. If disabling OSIV, prepare returned data inside transactions or use representations that do not access unloaded proxies.

## 11. Controlling Loaded Data Before Serialization

### Using EntityGraph

With Spring Data JPA, you can declare associations to load on query methods:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"lines", "customer"})
    Optional<PurchaseOrder> findWithDetailsById(Long id);
}
~~~

EntityGraph specifies which attributes to fetch for a query. It is useful when a use case needs a specific graph without switching every association to EAGER.

If Spring Data REST uses the default `findById` repository method, a custom `findWithDetailsById` method does not automatically replace the default item GET endpoint. You can use a custom service/controller calling the EntityGraph query and mapping the response, or configure appropriate repository method exposure. Do not assume declaring a method makes the default GET item endpoint call it.

### Using Fetch Join or Specialized Queries

You can use JPQL fetch joins when needed:

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.customer
    left join fetch o.lines
    where o.id = :id
    """)
Optional<PurchaseOrder> findDetailedById(@Param("id") Long id);
~~~

Fetch join loads associations in the same query. When fetching multiple collections, watch out for row multiplication, duplicate root rows, pagination, and count queries. Do not unconditionally fetch-join collections for every endpoint.

### Mapping to DTOs Inside a Transaction

This is often the clearest way to control responses for custom APIs:

~~~java
public record OrderLineResponse(
        Long id,
        String sku,
        int quantity
) {}

public record OrderResponse(
        Long id,
        String orderNumber,
        String customerName,
        List<OrderLineResponse> lines
) {}
~~~

~~~java
@Service
public class OrderQueryService {

    private final PurchaseOrderRepository repository;

    public OrderQueryService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderResponse getOrder(Long id) {
        PurchaseOrder order = repository.findDetailedById(id)
                .orElseThrow();

        List<OrderLineResponse> lines = order.getLines().stream()
                .map(line -> new OrderLineResponse(
                        line.getId(),
                        line.getSku(),
                        line.getQuantity()))
                .toList();

        return new OrderResponse(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomer().getName(),
                lines);
    }
}
~~~

The DTO is built while the persistence context is still open. Jackson serializes materialized values rather than Hibernate proxies. DTOs also avoid directly returning entire entity graphs or internal properties.

When using default Spring Data REST, you can consider projections/excerpts to limit data. However, projection getters accessing LAZY associations can still trigger queries; projections control output fields without automatically ensuring an optimal fetch plan.

## 12. Hibernate.initialize and the Limits of Manual Initialization

Hibernate provides:

~~~java
Hibernate.initialize(order.getLines());
~~~

This forces initialization of a proxy or persistent collection while the Session is open. You can check status with:

~~~java
boolean initialized = Hibernate.isInitialized(order.getLines());
~~~

An important point: for multi-valued associations, `Hibernate.initialize(collection)` only guarantees the collection itself is initialized; it does not guarantee every entity inside the collection has all its nested associations loaded. If the serializer goes on to access a LAZY association on each OrderLine, additional queries or LazyInitializationException can still occur.

Do not sprinkle initialize everywhere to "fix" serialization. Use-case-specific fetch plans, EntityGraphs, or DTOs are usually more predictable and controllable.

## 13. Lombok Can Also Create Loops

Lombok annotations such as `@Data`, `@ToString`, and `@EqualsAndHashCode` can include relationship properties in auto-generated methods.

Example:

~~~java
@Data
@Entity
public class PurchaseOrder {

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines;
}
~~~

If Order.toString() prints lines and OrderLine.toString() prints order, logging an entity can trigger infinite recursion even when Jackson is not running.

For JPA entities, choose getters/setters intentionally or exclude associations from generated methods:

~~~java
@Getter
@Setter
@Entity
public class PurchaseOrder {

    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Carefully consider equals/hashCode on entities with auto-generated IDs. Comparing entire relationships can cause recursion, unwanted lazy loads, and hash-code changes when an entity transitions from transient to persistent.

## 14. Customizing Spring Data REST's ObjectMapper

Spring Data REST allows adding Jackson modules, serializers, and deserializers by overriding `configureJacksonObjectMapper` in `RepositoryRestConfigurer`.

Example structure:

~~~java
@Configuration
public class RestRepresentationConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureJacksonObjectMapper(
            MapperBuilder<? extends ObjectMapper,
                    ? extends MapperBuilder<?, ?>> mapperBuilder) {

        mapperBuilder.addModule(new SimpleModule("OrderJsonModule") {
            @Override
            public void setupModule(SetupContext context) {
                // Register only the serializers/deserializers
                // required by the application's domain model.
            }
        });
    }
}
~~~

Spring Data REST's ObjectMapper includes specialized modules to serialize and deserialize PersistentEntity into representations/links. When adding custom modules, preserve the settings and modules required by the exporter; do not replace the entire ObjectMapper with a self-constructed mapper without understanding Spring Data REST's serializers.

Use custom serializers only when the domain model genuinely cannot be represented appropriately via association links, projections, or DTOs. Serializers should produce stable output, avoid walking deep graphs, and not trigger a cascade of lazy loads.

## 15. Testing Loops and Proxies

Test these two groups independently.

### Testing JSON Loops

With the Jackson ObjectMapper used in custom endpoints, verify the response does not loop back to the parent:

~~~java
@Test
void serializesOrderWithoutBackReferenceLoop() throws Exception {
    String json = objectMapper.writeValueAsString(order);

    JsonNode root = objectMapper.readTree(json);

    assertThat(root.path("lines")).isNotEmpty();
    assertThat(root.path("lines").get(0).has("order")).isFalse();
}
~~~

Tests should use the application's actual ObjectMapper or an equivalently configured ObjectMapper. Testing with a standalone mapper does not prove the Spring Data REST exporter behaves identically.

### Testing HAL Association Links

~~~java
mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.lines.href").exists());
~~~

This test confirms associations are represented by links per Spring Data REST configuration.

### Testing Lazy Loading with OSIV Disabled

In integration tests, set:

~~~properties
spring.jpa.open-in-view=false
~~~

Then call endpoints whose projections/serializers read associations and verify:

- The response does not throw LazyInitializationException.
- SQL query counts match the fetch plan.
- No N+1 queries occur when collections have multiple elements.
- Required associations are loaded within the transaction.
- Unselected associations are not loaded unexpectedly.

You can enable Hibernate statistics or SQL logging in a test profile to observe query counts. Do not check only HTTP 200 because a response can succeed while issuing far more queries than intended.

## 16. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Jackson reports infinite recursion or StackOverflowError | Parent and child serialize references to each other | Use HAL links, managed/back references, object identity, or DTOs |
| Spring Data REST returns association links, but custom API loops | Two serialization paths use different ObjectMappers/representations | Check the controller and mapper handling the response |
| LazyInitializationException on GET | Serializer accesses a proxy after the Session closes | Fetch data inside the transaction or map to a DTO |
| Response works with OSIV on, fails when turned off | Serialization relies on lazy loading outside service transactions | Define a fetch plan and test with OSIV false |
| Response is slow despite fast entity query | Jackson/projections trigger many lazy queries | Use EntityGraph, fetch queries, or DTOs; measure SQL counts |
| JsonBackReference does not work | Annotation placed on a collection or mismatched pair names | Place on a single bean-typed property and use the same reference name |
| Deserialization loses parent-child link | Using @JsonIgnore or misoriented back-reference | Check managed/back reference pair and owning side |
| @JsonIdentityInfo emits an ID instead of an object | Jackson already encountered the object earlier in the graph | Ensure clients support ID references and resolvers |
| Logging entities recurses | Lombok toString/equals/hashCode traverses bidirectional relationships | Exclude associations or define methods intentionally |

## 17. Choosing an Approach by API Type

| Scenario | Suitable Approach |
| --- | --- |
| Standard Spring Data REST repository resources | Prefer association links and HAL navigation |
| Custom REST endpoint needing a parent-child JSON tree | DTOs or JsonManagedReference/JsonBackReference |
| Domain graph with many cross-references | JsonIdentityInfo or DTOs with ID references |
| Response only needs a few fields and summary associations | Projections or excerpts |
| Response needs LAZY data | EntityGraph/fetch queries and mapping inside a transaction |
| Need strict control over response and avoiding field leaks | DTOs with an allowlist of properties |

Separate the question "What structure should the JSON have?" from "Which data does Hibernate need to load?". Jackson annotations address JSON shape; EntityGraph/fetch queries address loaded data; transactions/persistence contexts determine whether proxies can load.

## References

- [Spring Data REST 5.1.2 — Domain Object Representations](https://docs.spring.io/spring-data/rest/reference/representations.html): The exporter's specialized ObjectMapper, association links, custom Jackson modules, and serializers.
- [Spring Data REST 5.1.2 — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): item resources, association resources, and HAL links.
- [Jackson 2.21 — JsonManagedReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.21/com/fasterxml/jackson/annotation/JsonManagedReference.html) and [JsonBackReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.21/com/fasterxml/jackson/annotation/JsonBackReference.html): forward/back reference pairs and serialization/deserialization rules.
- [Jackson 2.21 — JsonIdentityInfo](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.21/com/fasterxml/jackson/annotation/JsonIdentityInfo.html) and [JsonIdentityReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.21/com/fasterxml/jackson/annotation/JsonIdentityReference.html): object identity and ID-based references.
- [Hibernate ORM 7.2 — LazyInitializationException](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/LazyInitializationException.html): error when accessing unloaded data outside an open Session.
- [Hibernate ORM — Hibernate utilities](https://docs.jboss.org/hibernate/orm/current/javadocs/org/hibernate/Hibernate.html): Hibernate.initialize and Hibernate.isInitialized for proxies/collections.
- [Spring Boot — SQL Databases, Open EntityManager in View](https://docs.spring.io/spring-boot/reference/data/sql.html): default OpenEntityManagerInViewInterceptor and spring.jpa.open-in-view configuration.
