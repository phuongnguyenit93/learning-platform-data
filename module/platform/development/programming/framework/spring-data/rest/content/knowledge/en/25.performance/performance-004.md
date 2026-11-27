# Impact of Lazy Loading and Open Session in View

## 1. What is lazy loading in JPA?

Lazy loading is how an ORM defers loading an association or attribute until the application actually accesses it. With Spring Data JPA, Hibernate typically creates a proxy for an entity or collection to represent unloaded data.

For example, a Person has many Orders:

~~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @OneToMany(mappedBy = "person", fetch = FetchType.LAZY)
    private List<Order> orders = new ArrayList<>();
}
~~~~

When querying Person, Hibernate may load only the Person row. The orders collection is not fetched immediately. When the code calls person.getOrders().size() or iterates over the collection, Hibernate executes a query to fetch Order records if the persistence context is still open.

Lazy loading helps:

- Avoid loading related data when the use case does not need it.
- Reduce the amount of data read and the number of objects created in memory.
- Allow designing different fetch plans per use case.
- Avoid loading multiple large collections just because an entity has associations.

Lazy loading also introduces an important requirement: the proxy needs an active persistence context when initialized. If the context is already closed and the collection has not been loaded, Hibernate may throw LazyInitializationException.

Not all associations default to LAZY. In JPA, ManyToOne and OneToOne default to EAGER, while OneToMany and ManyToMany default to LAZY. You should declare fetch types intentionally and design queries according to the needs of the endpoint.

## 2. Persistence context and when proxies are initialized

The persistence context is the entity management area of an EntityManager. Hibernate uses it to track entities, identity, dirty checking, and lazy proxies.

A simple processing flow:

1. The repository runs a query and returns Person.
2. Person has an uninitialized orders collection.
3. The transaction ends.
4. The EntityManager or persistence context is closed.
5. The serializer reads the orders property.
6. Hibernate no longer has a context to run a query and may throw LazyInitializationException.

Example:

~~~~java
Person person = personRepository.findById(42L)
        .orElseThrow();

// If orders has not been loaded and the persistence context is closed,
// accessing the collection may throw LazyInitializationException.
int orderCount = person.getOrders().size();
~~~~

The failure point does not necessarily lie in the repository call. The error can appear later in a controller, mapper, logger, or JSON serializer when a getter inadvertently accesses a lazy association.

Therefore, you need to know exactly when an entity is serialized and how long the persistence context remains alive.

## 3. What is Open Session in View (OSIV)?

Open Session in View is a pattern that keeps the Hibernate Session or JPA EntityManager open throughout the lifecycle of an HTTP request. In Spring, this mechanism is typically implemented using OpenEntityManagerInViewFilter or its corresponding interceptor.

Overview flow:

~~~~text
HTTP request starts
       |
       v
Open EntityManager / bind to request thread
       |
       v
Controller calls Spring Data repository
       |
       v
Repository queries inside transaction
       |
       v
Transaction ends
       |
       v
Controller returns entity or representation
       |
       v
Jackson / HAL serializer reads getters
       |
       +--> Lazy proxy is accessed
       |        |
       |        v
       |    EntityManager is still open
       |        |
       |        v
       |    Hibernate can execute additional queries
       |
       v
HTTP response is written
       |
       v
Close EntityManager
~~~~

OSIV allows the serializer to initialize lazy associations after the repository transaction has ended, as long as the persistence context remains open.

This is why an endpoint can succeed even when the controller just returns an entity without an explicit fetch query. OSIV can hide the fact that the response is triggering many additional queries.

## 4. OSIV in Spring Boot

For web applications using Spring Boot and JPA, Open EntityManager in View is typically enabled by default unless configured otherwise. It can be controlled with the property:

~~~~properties
spring.jpa.open-in-view=true
~~~~

To disable OSIV:

~~~~properties
spring.jpa.open-in-view=false
~~~~

When disabled, the per-request EntityManager is not kept open for response rendering. Unloaded entities or proxies must be handled within the transaction/service boundary or via an appropriate fetch query.

For REST APIs, disabling OSIV usually makes each endpoint's actual fetch plan explicit. The application must then proactively load the data needed for serialization instead of relying on lazy getters during the rendering phase.

Disabling OSIV can expose LazyInitializationException on endpoints that currently rely on implicit lazy loading. Check responses with embedded associations, projections, or custom serializers before rolling out this configuration change.

## 5. How does OSIV affect Spring Data REST?

Spring Data REST builds representations from repository resources and uses message converters/serializers to produce HAL or JSON responses. A representation may include:

- Scalar properties of the entity.
- Links to association resources.
- Embedded resources via projections or excerpts.
- Fields added by custom controllers or serializers.

When a serializer or projection reads a lazy property, Hibernate can execute additional queries if OSIV still keeps the EntityManager open.

For example, a collection resource returns a list of Person entities. If each Person embeds a list of Orders, the serializer may access orders for each Person. With N people, the system may run one query to fetch Person and N additional queries to fetch Order.

Not every association link automatically loads the entire related entity. Spring Data REST typically represents associations as hypermedia links; additional queries occur when the representation, projection, custom code, or serializer actually accesses the lazy data.

Therefore, it is necessary to distinguish:

- An association link only exposes a URI for the client to navigate.
- An embedded association requires the related data to appear in the response.
- A projection may invoke association getters and trigger lazy loading.
- A custom serializer may inadvertently iterate over a large collection.

## 6. N+1 queries and the hidden cost of OSIV

An N+1 query occurs when the application loads N entities in one query, then runs an additional query for each entity to fetch an association.

Example:

~~~~java
List<Person> people = personRepository.findAll();

for (Person person : people) {
    int count = person.getOrders().size();
}
~~~~

If there are 100 Person records and orders is lazy, the application may execute:

- 1 query to fetch 100 Person records.
- 100 separate queries to fetch orders for each Person.

A total of 101 queries instead of a controlled number of queries.

When OSIV is enabled, lazy initialization errors may not appear, but N+1 still occurs. The response may return successfully while query time grows with the number of entities.

Common symptoms:

- The endpoint is fast with a few records but slow when page size increases.
- SQL logs show many identical SELECT statements with different IDs.
- Query count grows linearly with the number of items in the response.
- The serializer takes a long time even though the repository method looks simple.
- Connection/database load spikes during response rendering.

Do not evaluate performance solely by repository method duration. Measure the entire request, including HAL/JSON serialization and response writing.

## 7. LazyInitializationException when OSIV is disabled

When OSIV is disabled, if code accesses an uninitialized proxy after the transaction ends, Hibernate may throw:

~~~~text
org.hibernate.LazyInitializationException:
failed to lazily initialize a collection of role:
Person.orders: could not initialize proxy - no Session
~~~~

Controller example:

~~~~java
@GetMapping("/people/{id}")
public Person getPerson(@PathVariable Long id) {
    return personRepository.findById(id).orElseThrow();
}
~~~~

If the response serializer tries to read orders when the repository returned the entity after the persistence context closed, the response can fail.

The right fix is to decide what data the endpoint needs and load that data inside a transaction. Do not re-enable OSIV or change every association to EAGER just to mask the error.

## 8. Intentional data loading with EntityGraph

Spring Data JPA supports EntityGraph to specify which associations to load for a repository method.

Example:

~~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    @EntityGraph(attributePaths = {"orders"})
    Optional<Person> findWithOrdersById(Long id);
}
~~~~

A service can call this method inside a transaction and map the result to a DTO:

~~~~java
@Service
public class PersonQueryService {

    private final PersonRepository people;

    public PersonQueryService(PersonRepository people) {
        this.people = people;
    }

    @Transactional(readOnly = true)
    public PersonDetails getDetails(Long id) {
        Person person = people.findWithOrdersById(id)
                .orElseThrow(() -> new PersonNotFoundException(id));

        return PersonDetails.from(person);
    }
}
~~~~

EntityGraph makes the fetch plan explicit right on the query method. Use it for associations actually needed in the use case; do not load every relationship just because the entity happens to have them.

For large collections, consider separate pagination for the association instead of embedding everything.

## 9. Fetch join and custom queries

Another option is to use a JPQL fetch join:

~~~~java
@Query("""
    select distinct p
    from Person p
    left join fetch p.orders
    where p.id = :id
    """)
Optional<Person> findByIdWithOrders(@Param("id") Long id);
~~~~

Fetch join loads the association in the main query. From there, the mapper can access orders inside the transaction without generating additional lazy queries.

Be careful with collection fetch joins combined with pagination. One parent with many children produces multiple SQL rows for the same parent; database paging on joined rows may not correspond to paging on the root entity. Hibernate may have to perform pagination in memory or emit warnings depending on configuration.

For large collections and pages, it is usually better to:

1. Query the page of IDs or parent entities first.
2. Query the associations for that page's set of IDs using an IN query.
3. Assemble the data in the service/mapper.
4. Or use batch fetching to reduce query count.

Do not fetch join multiple large collections in a single query if doing so creates a Cartesian product or huge duplicate data.

## 10. DTOs and projections for API responses

REST responses do not have to serialize JPA entities directly. DTOs let you define the exact fields the endpoint needs to return.

Example:

~~~~java
public record PersonSummary(
        Long id,
        String name,
        int orderCount
) {
}
~~~~

The service constructs the DTO inside a transaction:

~~~~java
@Transactional(readOnly = true)
public PersonSummary getSummary(Long id) {
    Person person = personRepository.findById(id)
            .orElseThrow(() -> new PersonNotFoundException(id));

    return new PersonSummary(
            person.getId(),
            person.getName(),
            person.getOrders().size()
    );
}
~~~~

This example still needs orders to be loaded efficiently. You can use a separate count query or a projection query to get orderCount without loading full Order entities.

DTOs help:

- Control exposed data.
- Avoid serializing unnecessary proxies and collections.
- Decouple the API contract from the persistence structure.
- Perform mapping inside an explicit transaction.
- Reduce the risk of circular references when entities have bidirectional associations.

Spring Data REST also supports projections and excerpt projections. Projections can restrict which fields are exposed, but if a getter in the projection accesses a lazy association, it can still trigger a query. Projections do not automatically solve N+1; you must verify the fetch plan of each representation.

## 11. Batch fetching to reduce N+1

If an endpoint genuinely needs a lazy association for many entities, batch fetching can group the loading into batches instead of one query per parent.

With Hibernate, you can use @BatchSize:

~~~~java
@OneToMany(mappedBy = "person", fetch = FetchType.LAZY)
@org.hibernate.annotations.BatchSize(size = 50)
private List<Order> orders = new ArrayList<>();
~~~~

Or configure a default:

~~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=50
~~~~

Batch fetching can significantly reduce query count. However, it is not a substitute for selecting the right response data. If an endpoint only needs orderCount, a COUNT query or projection is usually more efficient than loading the entire collection.

Inspect the actual SQL to verify that batch size takes effect for the association and Hibernate version in use.

## 12. EAGER is not a general-purpose fix

When encountering LazyInitializationException, changing FetchType.LAZY to FetchType.EAGER might make an endpoint work, but it usually creates side effects:

- Every query fetching the entity may load the association even when the use case does not need it.
- Nested associations can pull in far more data than expected.
- Query count and data volume may increase.
- EAGER collections can cause N+1 depending on the query plan.
- It becomes harder to control representations and performance across endpoints.

Keep association mappings aligned with domain needs and define a fetch plan per use case using EntityGraph, fetch join, projections, or DTOs.

## 13. OSIV and transaction boundaries

OSIV keeps the persistence context open during the request, but it does not mean the entire request runs in a single transaction.

A repository method may open a transaction, execute a query, and then end the transaction. Afterward, the serializer still accesses proxies within the same EntityManager kept open by OSIV. Additional lazy queries may occur outside the original business transaction or in a different transaction depending on the transaction manager and provider.

This can lead to:

- The response reading associations at different points in time.
- Queries during serialization not participating in the same business transaction.
- Database logic being triggered from getters or serializers instead of services.
- Persistence context lifetime lasting longer than the business logic requires.
- Response behavior depending on which fields the serializer accesses.

OSIV does not guarantee a consistent snapshot for the entire response. If an endpoint needs consistent data within a use case, load the data inside the appropriate transaction and build the DTO before the transaction ends.

## 14. Configuring OSIV off for REST APIs

You can set this in application.properties:

~~~~properties
spring.jpa.open-in-view=false
~~~~

After disabling it, check these groups of endpoints:

- Item resources with embedded associations.
- Collection resources using excerpt projections.
- Custom repository controllers returning entities directly.
- Custom serializers or Jackson getters accessing associations.
- Logging/toString/equals/hashCode traversing lazy collections.
- APIs returning nested DTOs mapped after the transaction ends.

Some endpoints may continue working because they only return scalar fields or association links. Others may raise LazyInitializationException if the serializer needs unloaded data.

Enable SQL logging or Hibernate statistics in test environments to observe query counts and where queries are issued.

## 15. Avoiding accidental lazy loading triggers

Lazy loading does not only happen in controllers or serializers. The following operations can also access proxies:

- Calling toString() on an entity with associations.
- Calling equals() or hashCode() based on collections or associations.
- Logging the entire entity with a logger.
- Expanding objects in an IDE debugger.
- Auto-mappers reading all getters.
- JSON serializers traversing every property.
- Template engines or view renderers accessing properties.

Do not write a toString() that automatically includes every association. Use the ID and safe scalar fields. With Lombok, check @ToString and @EqualsAndHashCode and exclude inappropriate associations.

## 16. Testing with OSIV disabled

Integration tests should run with the same configuration as production:

~~~~properties
spring.jpa.open-in-view=false
~~~~

Verify:

1. GET item returns the exact defined fields.
2. Collection resources do not produce unexpected N+1 queries.
3. Embedded associations have an explicit fetch plan.
4. Projections do not access closed proxies.
5. Custom controllers map DTOs inside a transaction.
6. No LazyInitializationException occurs when serializing responses.
7. Increasing page size does not cause query count to grow linearly unexpectedly.
8. Endpoints that only need association links do not load full collections.
9. Responses do not contain unexposed persistence fields.

You can use Hibernate statistics, a datasource proxy, or SQL logging in integration tests to count queries. For N+1, check the query count across multiple data sizes, such as 1, 10, and 50 parents, rather than running only a small fixture.

Beyond functional tests, measure request duration and query count in a production-like environment to confirm that fetch plan changes actually improve performance.

## 17. Common errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| LazyInitializationException during serialization | OSIV is disabled and response accesses an uninitialized proxy | Fetch the association inside a transaction or map to a DTO |
| Endpoint works with OSIV enabled but is very slow | Serializer causes N+1 queries | Measure query count and declare a fetch plan |
| Switching to EAGER makes queries heavy | Association is loaded in every use case | Use LAZY and EntityGraph/custom queries |
| Collection fetch join breaks or slows paging | Join multiplies parent rows | Page parents first, then fetch children by ID |
| Projection still causes N+1 | Getter in projection accesses lazy association | Optimize the projection's query/fetch plan |
| Logging entity triggers queries | toString or logger traverses associations | Log ID/scalar fields, exclude associations from toString |
| JSON response has circular references | Bidirectional entity serialized directly | Use projection/DTO or hypermedia links |
| Response reads inconsistent data | Lazy queries run after business transaction | Load data inside transaction and map to DTO |
| OSIV enabled but lazy error still occurs | EntityManager no longer bound to request or proxy belongs to another context | Check transactions, filters, and entity origin |
| Query count scales with record count | N+1 from lazy association | Use batch fetch, projection, or appropriate query |

## 18. Conclusion

Lazy loading defers loading associations until needed, while Open Session in View keeps the EntityManager/Session open throughout the request so serializers can initialize proxies after the repository transaction ends. This can make responses work conveniently, but it also hides queries issued during serialization and creates N+1 problems.

With Spring Data REST, HAL/JSON representations, embedded associations, projections, and custom serializers can access lazy properties. When disabling OSIV with spring.jpa.open-in-view=false, endpoints must load required data within a transaction or map to DTOs before the context closes. Use EntityGraph, controlled fetch joins, projections, batch fetching, and separate count queries as needed. Avoid changing every association to EAGER to fix errors. Test with OSIV disabled, measure query counts, and verify that response serialization does not trigger unintended lazy loading.

## References

- [Spring Boot — Data Access and Open EntityManager in View](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Data JPA — Entity Graphs](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Hibernate ORM — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
