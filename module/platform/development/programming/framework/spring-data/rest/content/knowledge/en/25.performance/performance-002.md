# Identifying N+1 Queries When Reading Associations, Projections, and Excerpts

## Objectives

After this lesson, you will be able to:

- Explain the N+1 query phenomenon in Spring Data REST applications using JPA/Hibernate.
- Identify how lazy associations are accessed when building HAL representations.
- Understand why projections and excerpts can trigger additional queries.
- Distinguish representation-layer projections from SQL query-layer projections.
- Read SQL logs and Hibernate statistics to find N+1 issues.
- Choose an appropriate fetch join, EntityGraph, batch fetching, or DTO projection.
- Avoid pagination bugs when fetching collections and verify query counts with integration tests.

## 1. What Is an N+1 Query?

N+1 is a query pattern in which an application executes one query to retrieve a list of N entities, and then executes one additional query per entity to load related data.

Suppose an API returns 50 Person records, each having one Address:

1. The first query fetches 50 Person records.
2. When the response is serialized, the application reads the address of the first Person and runs a query to fetch Address.
3. This repeats for the second, third, and remaining Person entities.
4. The total number of queries can be 1 + 50 = 51.

Illustrative SQL:

~~~sql
select p.id, p.name, p.address_id
from person p
order by p.id;

select a.id, a.city, a.street
from address a
where a.id = ?;
~~~

The second query can be executed repeatedly for each address_id. If the relationship is a collection such as a Person having many Orders, Hibernate can also execute a separate query per Person to load those Orders.

N+1 increases the number of round trips between the application and the database. Even if each individual query is very fast, total latency can rise significantly due to network overhead, connection pooling, database scheduling, and entity hydration costs.

N+1 does not mean the database always returns N+1 rows. It is a way of counting query executions: one initial query plus multiple follow-up queries triggered when accessing relationships.

## 2. Why Does Spring Data REST Easily Expose N+1 Issues?

Spring Data REST converts repository results into representations, usually HAL JSON. Building the representation may access entity getters, projections, or associations.

A JPA entity might declare a lazy relationship:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne(fetch = FetchType.LAZY)
    private Address address;
}
~~~

Repository:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

When calling the collection endpoint:

~~~http
GET /api/people
Accept: application/hal+json
~~~

The repository may initially load only Person. If the representation only provides a link to the association and does not read Address data, that association may not need to be loaded yet.

However, if a projection or serializer calls the relationship getter—such as getAddress().getCity()—Hibernate needs to fetch the Address. If this happens for each Person, N+1 appears.

Therefore, do not conclude that every Spring Data REST collection endpoint always has an N+1 issue. The outcome depends on:

- Whether the relationship is LAZY or EAGER.
- Whether the representation accesses the association.
- Whether the projection includes relationship getters.
- Whether an excerpt projection reads related properties.
- Whether the persistence context is still open or already closed.
- How the Hibernate fetch plan, batch size, and cache are configured.

## 3. Lazy Loading and When Queries Are Executed

JPA typically uses LAZY for to-many relationships and can use LAZY for many to-one relationships. A lazy association is loaded only when code actually accesses its data.

Example:

~~~java
Person person = personRepository.findById(1L).orElseThrow();

// Address may not be queried yet.
Address address = person.getAddress();

// When accessing a property, Hibernate may query Address.
String city = address.getCity();
~~~

With a collection:

~~~java
Person person = personRepository.findById(1L).orElseThrow();

// Order may not be queried yet.
List<Order> orders = person.getOrders();

// When iterating over the collection, Hibernate may query Orders.
for (Order order : orders) {
    System.out.println(order.getOrderNumber());
}
~~~

Lazy loading helps avoid loading unnecessary data. The problem arises when code accesses the same association repeatedly across many entities.

Distinguish between:

- **Lazy loading**: a mechanism for loading data on demand.
- **N+1**: a query pattern arising from how data is accessed.
- Lazy loading is not a bug by itself; it becomes a problem when query count scales with the number of entities in the result.

## 4. How Can Projections Trigger N+1?

A Spring Data REST projection defines which properties appear in a representation. A projection interface can declare getters for associations:

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getName();

    Address getAddress();
}
~~~

Nested projections can restrict the fields of Address:

~~~java
@Projection(name = "addressSummary", types = Address.class)
public interface AddressSummary {

    String getCity();
    String getStreet();
}
~~~

Or declare a projection for Person with an explicit relationship view:

~~~java
@Projection(name = "personWithAddressSummary", types = Person.class)
public interface PersonWithAddressSummary {

    String getName();

    AddressSummary getAddress();
}
~~~

When Spring Data REST builds representations for multiple Person entities, the getAddress() getter may be invoked on each Person. If Address is lazy and not yet in the persistence context, Hibernate may issue a separate query for each association.

The SQL pattern may look like:

~~~sql
select p.id, p.name, p.address_id
from person p;

select a.id, a.city, a.street
from address a
where a.id = ?;

select a.id, a.city, a.street
from address a
where a.id = ?;

-- Continue for the remaining Person entities.
~~~

Projections clarify what data the client wants to see, but reading relationship getters can still trigger lazy loading. Inspect the actual SQL rather than assuming fewer fields mean fewer queries.

## 5. Excerpt Projections Also Need Inspection

An excerpt projection is configured on the repository:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Example excerpt:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getName();

    AddressSummary getAddress();
}
~~~

When a collection resource embeds multiple Person items, the excerpt is used to build the configured representation for those items. If the excerpt only reads name, it may not need to load Address. If the excerpt reads address, building the representation can access the association and trigger extra queries.

An important point: **Spring Data REST excerpts/projections are a representation-selection mechanism**. They do not automatically guarantee that Hibernate will issue a single SQL join.

It is also important to distinguish two types of projections:

- **Spring Data REST projection**: determines which fields appear in the HAL representation of an entity.
- **Spring Data JPA query projection**: can ask a query to return an interface projection or DTO instead of hydrating the full entity, depending on the query and repository declaration.

The two mechanisms have similar names but are not synonymous. REST-layer projections may read entities and lazy associations; JPA-layer query projections can optimize selected columns if the query is designed appropriately.

## 6. A Default Excerpt Is Not a Fetch Plan

Example excerpt configuration:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {
    String getName();
    String getEmail();
}
~~~

The excerpt above reads only two basic properties of Person. If they are ordinary fields, the representation can be generated without accessing associations.

If you add a getter:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {
    String getName();
    AddressSummary getAddress();
}
~~~

then the view may need Address data. Hibernate's query plan is still governed by mappings, fetch plans, queries, and caches.

Do not use an excerpt as a substitute for designing a fetch strategy. Treat the excerpt as a representation contract and choose a dedicated fetch strategy for endpoints that need related data.

## 7. Distinguishing Link Associations from Inline Associations

Spring Data REST typically represents associations using hypermedia links. For example, Person might return:

~~~json
{
  "name": "Lan",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/1"
    },
    "address": {
      "href": "http://localhost:8080/api/people/1/address"
    }
  }
}
~~~

In this representation, Address does not have to be serialized as a nested object. The client can follow the association link when it actually needs Address data.

If a projection includes Address in the body:

~~~json
{
  "name": "Lan",
  "address": {
    "city": "Ho Chi Minh City",
    "street": "Le Loi"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/1"
    },
    "address": {
      "href": "http://localhost:8080/api/people/1/address"
    }
  }
}
~~~

then the server needs to fetch Address data to construct that inline section.

The two approaches have different trade-offs:

| Representation style | Advantage | Cost to consider |
|---|---|---|
| Association link | Compact representation; client loads the relation only when needed | Client may have to call additional endpoints |
| Inline projection | One response contains the relational data needed for the screen | Server may have to fetch many associations and cause N+1 |
| DTO/query projection | Can optimize fields and queries per use case | Requires defining dedicated queries/endpoints and maintaining a consistent representation |

Using links is not always faster; if the client calls every association for every item, N+1 can turn into multiple HTTP requests. Consider how the client consumes the API alongside the server-side fetch plan.

## 8. Identifying N+1 via SQL Logs

Enable SQL logging in the development environment:

~~~properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

The parameter-binding logger name varies by Hibernate version. In Hibernate 5, the typical logger name differs from Hibernate 6; verify the exact version used in your application.

Call the collection endpoint with a sufficiently large item count:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  "http://localhost:8080/api/people?page=0&size=20"
~~~

Observe the logs:

~~~text
select ... from person ... limit ...;
select ... from address where id=?;
select ... from address where id=?;
select ... from address where id=?;
...
~~~

Signs of N+1:

- One query fetches the list of entities.
- Many queries share the same SQL structure for an association.
- The number of extra queries grows nearly linearly with the number of serialized items.
- Increasing page size from 10 to 30 noticeably increases the number of relationship queries.

Not every sequence of repeated queries is an N+1 issue. Identify which query loads the association and which getter/representation triggers it.

Avoid enabling SQL bind logging in production if logs may contain personal data, tokens, or sensitive values. SQL logging can produce high log volume and impact performance.

## 9. Using Hibernate Statistics to Measure Query Count

Hibernate statistics help observe query executions, entity loads, collection fetches, and cache hits.

They can be enabled in configuration:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
logging.level.org.hibernate.stat=DEBUG
~~~

Or configure SessionFactory statistics in a test:

~~~java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.setStatisticsEnabled(true);
statistics.clear();

personRepository.findAll(PageRequest.of(0, 20));

// Read the metrics after the operation completes.
long queryCount = statistics.getQueryExecutionCount();
long entityFetches = statistics.getEntityFetchCount();
long collectionFetches = statistics.getCollectionFetchCount();
~~~

Useful metrics:

- **QueryExecutionCount**: number of queries executed according to Hibernate query statistics.
- **EntityFetchCount**: number of entities fetched through the fetch mechanism.
- **CollectionFetchCount**: number of collections fetched.
- **SecondLevelCacheHitCount**: number of times data was retrieved from the second-level cache.

Statistics are not the only measurement. Some queries may execute via JDBC or paths not reflected identically in Hibernate query statistics. Combine statistics with SQL logs and datasource instrumentation when needed.

## 10. Solution 1: Fetch Join

A JPQL fetch join requests loading the association together with the main query:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @Query("""
        select p
        from Person p
        left join fetch p.address
        where p.active = true
        """)
    List<Person> findActiveWithAddress();
}
~~~

The SQL can become a single join query:

~~~sql
select p.*, a.*
from person p
left join address a on a.id = p.address_id
where p.active = true;
~~~

When building the representation for Person, Address is already loaded, so the getter does not need a separate query.

Fetch join is suitable for to-one relationships such as ManyToOne or OneToOne in many cases. However, check the number of returned rows and the associations being fetched.

### Be Careful with Collection Fetch Joins and Pagination

If you fetch join a to-many collection together with pagination, the SQL result can duplicate Person rows according to the number of Orders. Hibernate may have to perform pagination in memory or emit a warning/error depending on the version and configuration.

Example:

~~~java
@Query("""
    select distinct p
    from Person p
    left join fetch p.orders
    """)
Page<Person> findAllWithOrders(Pageable pageable);
~~~

This pattern requires special caution. Fetching a collection alongside Page can defeat pagination efficiency and produce huge intermediate datasets. Do not apply it blindly to collection endpoints.

For to-many relationships with pagination, it is usually better to paginate the IDs/root entities first, then load the associations for the page's ID set in a second query. This produces a fixed number of queries per page rather than one query per item.

## 11. Solution 2: @EntityGraph

Spring Data JPA supports **@EntityGraph** to declare the associations to load for a repository query.

Example:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @EntityGraph(attributePaths = {"address"})
    Optional<Person> findWithAddressById(Long id);

    @EntityGraph(attributePaths = {"address"})
    List<Person> findByActiveTrue();
}
~~~

An EntityGraph can use a fetch graph or load graph depending on the declared attributes and current mappings. It makes the fetch plan explicit without writing JPQL join fetch for every method.

A named entity graph can be declared on the entity:

~~~java
@Entity
@NamedEntityGraph(
    name = "Person.withAddress",
    attributeNodes = @NamedAttributeNode("address")
)
public class Person {
    // Fields and relationships.
}
~~~

Using the graph:

~~~java
@EntityGraph(value = "Person.withAddress")
Optional<Person> findById(Long id);
~~~

This is an illustrative example; in a real repository, avoid inadvertently declaring methods with duplicate inherited signatures. Verify which method the REST exporter actually calls.

An important point with Spring Data REST: adding a finder method with @EntityGraph does not automatically change the query called by the default collection endpoint findAll(Pageable). To apply a fetch plan to that endpoint, design the corresponding access path, such as a custom repository method/resource, repository fragment, dedicated controller/service, or verified repository configuration.

## 12. Solution 3: Batch Fetching

Batch fetching allows Hibernate to load multiple associations in a single query using a list of IDs instead of one query per entity.

It can be configured globally:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Or on an association/entity using @BatchSize:

~~~java
@Entity
@BatchSize(size = 32)
public class Address {
    // Fields.
}
~~~

When multiple Person entities reference lazy Address records, Hibernate can load a group of Addresses using an IN query:

~~~sql
select a.id, a.city, a.street
from address a
where a.id in (?, ?, ?, ...);
~~~

If there are 50 Person records and the batch size is 32, the number of queries fetching Address can drop from around 50 to around 2, depending on mappings, caching, and access order.

Batch fetching does not guarantee only one query remains. It reduces query count by grouping multiple lazy loads into a batch.

Batch fetching is especially useful when:

- Associations still need lazy loading.
- You do not want to join too many tables in the main query.
- Multiple to-one relationships or collections are accessed in groups.
- An endpoint cannot easily be changed to a DTO or custom query.

Measure with SQL logs after changing the batch size to confirm Hibernate actually batches the queries.

## 13. Solution 4: DTO or Query Projection

If an endpoint only needs a fixed set of fields, a DTO projection can reduce hydrated data and prevent the serializer from accessing lazy associations.

Example:

~~~java
public record PersonSummary(
    Long id,
    String name,
    String city
) {
}
~~~

Repository query:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @Query("""
        select new com.example.api.PersonSummary(
            p.id,
            p.name,
            a.city
        )
        from Person p
        left join p.address a
        where p.active = true
        """)
    List<PersonSummary> findActiveSummaries();
}
~~~

The query fetches Person and City in a single join. The DTO holds no JPA proxies or lazy collections, so serialization does not trigger additional association queries.

DTO projections are well suited when:

- A screen needs a specific, stable view.
- Only a defined set of fields and relationships is needed.
- You want control over the SQL and response shape.
- You need to avoid complex entity graphs during serialization.

If you use a dedicated DTO endpoint, decide how to expose the resource: a custom controller, custom repository endpoint, or another API layer. Spring Data REST projections and JPA DTO projections are two separate mechanisms; they do not automatically convert into one another.

## 14. Separate Pagination from Page-Level Association Loading

For to-many collections, an often safe strategy is:

1. Query Page<Person> fetching only the root entities or needed IDs.
2. Extract the list of IDs in the page.
3. Run a single query to fetch all related data for those IDs.
4. Assemble the data into DTOs by ID.
5. Return a page representation with pagination metadata.

Example second query:

~~~java
@Query("""
    select p
    from Person p
    left join fetch p.address
    where p.id in :ids
    """)
List<Person> findAllWithAddressByIdIn(@Param("ids") Collection<Long> ids);
~~~

For an Order collection, you can load all Orders belonging to the Person records on the page in one query:

~~~java
@Query("""
    select o
    from Order o
    where o.person.id in :personIds
    """)
List<Order> findOrdersForPeople(
    @Param("personIds") Collection<Long> personIds
);
~~~

Then group Orders by person ID in the service and construct the DTOs.

This approach typically produces a small, fixed number of queries per page: one query for the page, possibly one count query, and one query for the associations. It avoids a separate query per Person.

When handling large lists of IDs, mind your database's bind parameter limit. For small page sizes, a single IN query is usually suitable; for large ID sets, split into batches or use another strategy.

## 15. EAGER Is Not the Default Fix for N+1

Changing LAZY to EAGER may load data earlier, but it does not guarantee Hibernate will use a single JOIN. The persistence provider may still issue multiple queries to satisfy eager associations.

EAGER can also load data the endpoint does not need, increasing memory usage, joined row counts, or causing another N+1 in nested relationships.

Example of what not to change indiscriminately:

~~~java
@ManyToOne(fetch = FetchType.EAGER)
private Address address;
~~~

Choose fetch plans per use case rather than turning every association into EAGER.

A generally better strategy:

- Keep entity mappings LAZY for associations not needed by default.
- Use EntityGraph or fetch join on specific queries for required data.
- Use DTO projections for fixed responses.
- Use batch fetching when lazy loading in groups is needed.
- Have API representations inline only the associations clients truly need.

## 16. Projections and Fetch Plans Must Be Designed Together

When designing a Spring Data REST projection, list every getter that may access an association:

~~~java
@Projection(name = "personDetail", types = Person.class)
public interface PersonDetail {

    String getName();

    AddressSummary getAddress();

    List<OrderSummary> getOrders();
}
~~~

The projection above may need both Address and Orders. If the collection has 30 Person records, the serializer may access 30 Addresses and 30 Order collections. Optimizing only Address while ignoring Orders can still leave an N+1 problem.

A useful inventory table:

| Getter in projection | Relationship | Fetch risk |
|---|---|---|
| getName() | Basic field | Usually creates no relationship query |
| getAddress() | To-one | May create one query per Person |
| getOrders() | To-many | May create a collection query per Person |
| getOrders().getProduct() | Nested relationship | May create another layer of N+1 |

With nested projections, query count can multiply across levels—for example, loading Person, then each Person's Orders, then each Order's Product.

Inspect the entire projection tree, not just top-level getters.

## 17. A Count Query Is Not N+1

Paginated collections typically execute:

- One query to fetch the page content.
- One COUNT query to determine totalElements/totalPages when needed.
- Possibly additional queries for relationships accessed by projections or serializers.

A count query is normal pagination overhead, not N+1. N+1 is typically characterized by the same association query repeating once per item.

Example:

~~~sql
select count(p.id) from person p;

select p.id, p.name from person p
order by p.id
offset ? rows fetch first ? rows only;

select a.id, a.city from address a where a.id = ?;
select a.id, a.city from address a where a.id = ?;
select a.id, a.city from address a where a.id = ?;
~~~

The first two queries can be normal pagination. The repeated Address queries are the signal to investigate N+1.

Do not remove the count query just because the total query count looks high. First categorize each query by its purpose.

## 18. Testing to Prevent N+1 Regressions

You can write integration tests calling the exact repository/service or endpoint that the application uses.

Example with Hibernate statistics:

~~~java
@SpringBootTest
class PersonQueryPerformanceTest {

    @Autowired
    PersonRepository repository;

    @Autowired
    EntityManagerFactory entityManagerFactory;

    @Test
    void loadsAddressesInBatches() {
        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);

        Statistics statistics = sessionFactory.getStatistics();
        statistics.setStatisticsEnabled(true);
        statistics.clear();

        repository.findByActiveTrue();

        long entityFetches = statistics.getEntityFetchCount();
        long collectionFetches = statistics.getCollectionFetchCount();

        assertThat(entityFetches).isLessThanOrEqualTo(2);
        assertThat(collectionFetches).isLessThanOrEqualTo(2);
    }
}
~~~

This is an illustrative skeleton; test data, fetch access, and caching must be set up so the test actually exercises the code path you intend to measure. Calling a repository without accessing the association may fail to reproduce the N+1 from response serialization.

To test Spring Data REST thoroughly:

1. Create a sufficiently large set of Person records, each with Address/Orders.
2. Clear or disable relevant caches so caching does not hide queries.
3. Call the collection endpoint via MockMvc or an HTTP integration test.
4. Use the actual projection/excerpt requested by clients.
5. Count queries while the response is being serialized.
6. Compare query counts at page sizes 10 and 30.
7. Set a reasonable query threshold so the test detects linear query growth with item count.

You can use a datasource proxy or query-counting test utility if you need to count every JDBC statement, including queries that do not appear in Hibernate query statistics.

Do not assert an overly rigid query count if the implementation has count queries or metadata queries that differ across Hibernate/database versions. Verify the scaling trend and a reasonable upper bound for the endpoint.

## 19. Practical Diagnostic Workflow

When N+1 is suspected in Spring Data REST:

1. Identify the endpoint, page size, projection, and excerpt projection being used.
2. Enable SQL logging in the development environment.
3. Call the endpoint with a small page and record the initial query.
4. Look for repeated queries with the same structure and differing bind IDs.
5. Identify which getter or association is accessed in the representation.
6. Try removing the relationship getter from the projection to confirm the query source.
7. Choose fetch join, EntityGraph, batch fetching, or DTO projection.
8. Call the endpoint again and measure the query count.
9. Verify that pagination, memory usage, and the response body remain correct.
10. Add an integration test to enforce the query bound.

Do not optimize by guessing. An endpoint with multiple queries is not necessarily N+1; there may be count queries, pagination queries, audit queries, or other business logic. Correlate the SQL with the request path.

## 20. Common Mistakes

### Thinking Projections Always Reduce Query Count

Projections reduce fields in the representation but can still read lazy associations. If a relationship getter is called per item, N+1 still occurs.

### Thinking Excerpts Automatically Generate SQL Joins

An excerpt selects the default representation for embedded items. It is not a fetch plan and does not automatically guarantee a single join query.

### Checking Only the First Query

N+1 often appears after the collection query, during HAL response serialization. Measure the entire request until the response completes.

### Turning Every Relationship into EAGER

EAGER can load unnecessary data and still generate multiple queries. Use use-case-specific fetch plans.

### Fetch Joining a Collection Together with Page

A to-many fetch join can duplicate root rows and make pagination inefficient or unsafe. Separate the page query from the ID-based association query when appropriate.

### Adding EntityGraph Without Changing the Default Endpoint

EntityGraph applies only to the annotated query method. The default Spring Data REST collection endpoint may call findAll(Pageable), which differs from the finder method you annotated.

### Letting Caches Hide N+1

Second-level caches or application caches can keep query counts low in tests while cold caches in production generate many queries. Test both cold and warm caches.

### Optimizing Only One Relationship in a Nested Projection

Projections can access multiple levels of associations. Review the entire getter tree and corresponding fetch strategies.

### Using a DTO That Still Returns a Lazy Entity in One Field

A DTO can accidentally hold an entity or proxy. Use explicit scalar/value DTOs and complete mapping inside the appropriate transaction.

## 21. Key Takeaways

- N+1 is one list-fetching query plus repeated relationship queries per entity.
- Spring Data REST can expose N+1 when projections, excerpts, or serializers access lazy associations.
- REST-layer projections/excerpts govern the representation; they do not automatically guarantee joined SQL or a single query.
- Distinguish Spring Data REST projections from Spring Data JPA query projections / DTO projections.
- Use SQL logs and Hibernate statistics to identify repeated queries.
- Fetch joins and EntityGraph suit specific fetch plans; be careful when fetching collections alongside pagination.
- Batch fetching reduces lazy query count by grouping multiple IDs into a batch.
- DTO projections and the page-ID-then-fetch strategy are suitable when fixed responses or to-many relationships are needed.
- A pagination count query is not itself an N+1 issue.
- Test endpoints with real projections/excerpts, cold caches, and varying page sizes to prevent N+1 regressions.

## References

- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data JPA Reference — Query Methods and Entity Graphs](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA Reference — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Hibernate ORM User Guide — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Hibernate ORM User Guide — Batch Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#batch-fetching)
