# Testing Spring Data REST Contracts Against a Real Database with Testcontainers

## Goal

After this lesson, you will be able to build Spring Data REST integration tests running against a real database in Testcontainers; test HTTP contracts of collection, item, association, and query resources; verify HAL links, status codes, headers, validation, and persistence; execute schema migrations on the test database; and structure independent, repeatable tests in CI.

## 1. Why Test Against a Real Database?

A controller or repository test using mocks can verify that code calls the right collaborators, but it does not prove the application works with the database used in production. Several classes of bugs only appear when running through the real JDBC driver, ORM provider, SQL dialect, and schema:

- Incompatible column types, precision, timezones, or constraints.
- Query methods generating different SQL between H2 and PostgreSQL/MySQL.
- Entity mappings, lazy loading, cascades, or orphan removal behaving unexpectedly.
- Broken unique constraints, foreign keys, and transaction rollbacks.
- Migrations missing indexes, ordered incorrectly, or failing on an empty database.
- Spring Data REST returning unexpected association links or representations after serializing entities loaded by the persistence provider.

Testcontainers allows starting a real database inside a container for testing. The Spring application connects to that container, runs migrations, and handles HTTP requests like a regular integrated application. Tests thus verify the contract end-to-end from HTTP down to the database.

The goal is not to replace all unit tests with container tests. Unit tests remain suitable for fast, pure business logic checks. Use Testcontainers for behaviors depending on the database, mappings, transactions, migrations, and HTTP integration.

## 2. How Does Testcontainers Work?

Testcontainers is a Java library controlling a container runtime to spin up temporary dependencies for tests. For databases, the test declares an image and settings such as username, password, and database name. When the test needs the container, the library starts the database, waits for readiness, provides the mapped host/port, and cleans up the container per lifecycle.

PostgreSQL example:

```java
PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16-alpine")
        .withDatabaseName("spring_data_rest_test")
        .withUsername("test")
        .withPassword("test");
```

The container port is typically mapped to an available port on the host. Never hard-code PostgreSQL port 5432 in test config; retrieve the JDBC URL, username, and password from the container.

Benefits:

- Uses the exact database engine close to production.
- Eliminates needing separate local database installations on every developer machine.
- Can run in parallel with other builds thanks to dynamic port mapping.
- Each test suite can get a clean database.
- Enables testing real migrations and constraints.

Testcontainers requires a running Docker-compatible container runtime. In CI, runners must permit starting containers or use an appropriate Testcontainers Cloud/remote runtime setup.

## 3. Adding Dependencies for Spring Boot and PostgreSQL

With Maven, example test dependencies:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

When using Spring Boot dependency management, let the BOM manage compatible Testcontainers versions rather than manually picking mismatched versions. With recent Spring Boot versions, you can use the corresponding Testcontainers module and `@ServiceConnection` annotation if supported by your dependencies.

If the project uses MySQL, MariaDB, SQL Server, or another database, pick the module and container class for that exact engine. Do not use a PostgreSQL container to conclude queries or migrations are compatible with production MySQL.

## 4. Starting PostgreSQL with JUnit 5

A straightforward approach is declaring the container with JUnit 5:

```java
@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
class PersonApiIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("spring_data_rest_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Components:

- `@Testcontainers` enables JUnit Jupiter integration.
- `@Container` marks the container managed by the test class lifecycle.
- Static containers typically start once per class and stop after the class finishes.
- `@DynamicPropertySource` registers the dynamic JDBC URL and credentials before Spring creates the application context.
- `@SpringBootTest` starts the full Spring context.
- `@AutoConfigureMockMvc` provides MockMvc to dispatch requests through the Spring MVC/Security stack without opening a real HTTP port.

If you want to test the full network stack over a real server port, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with `TestRestTemplate` or `WebTestClient`. MockMvc still runs against the real container database; it only mocks the HTTP client and servlet container layer at test scope.

### Using @ServiceConnection

With Spring Boot versions supporting service connections and compatible Testcontainers versions, configuration can be shorter:

```java
@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
class PersonApiIntegrationTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Spring Boot automatically generates connection details for the database container. Pick one clear configuration style for your project version; there is no need to declare duplicate dynamic properties if service connection already supplies full configuration.

## 5. Running Migrations on the Test Database

Contract tests must validate the schema the application actually uses. If production uses Flyway or Liquibase, let migrations execute on the test container instead of letting Hibernate generate the schema.

Example configuration:

```properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
spring.jpa.open-in-view=false
```

With this configuration:

- Flyway applies migrations onto the container's empty database.
- Hibernate validates that mappings match the schema.
- Tests catch missing columns, mismatched types, or missing constraints in migrations.
- `open-in-view=false` helps tests catch serialization accidentally accessing lazy associations outside a transaction.

If the project uses Liquibase, configure Liquibase instead of Flyway and ensure changelogs run before tests. Avoid leaving `ddl-auto=create-drop`, which silently creates a schema differing from production; tests might pass while real migrations fail.

You can verify migrations directly via Flyway/Liquibase metadata or verify required behaviors like unique constraints and foreign keys through API tests.

## 6. Preparing Sample Repository and Entity

Example of Person with Address:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String firstName;

    @Column(nullable = false, length = 120)
    private String lastName;

    @ManyToOne(fetch = FetchType.LAZY)
    private Address address;

    protected Person() {
    }

    public Person(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    // Getters and setters
}
```

Repository:

```java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    List<Person> findByLastName(@Param("name") String lastName);
}
```

The example omits Address and migration files to focus on testing. In real projects, define constraints, ID generation, and associations according to production schema. Set explicit repository paths and relations so the HTTP contract can be verified.

## 7. Verifying API Root and Collection Contract

A contract test should start from the API root and verify media types along with links clients need for discovery.

```java
@Autowired
MockMvc mvc;

@Test
void apiRootPublishesPeopleAndProfileLinks() throws Exception {
    mvc.perform(get("/")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.people.href").exists())
        .andExpect(jsonPath("$._links.profile.href").exists());
}
```

Next, verify the collection:

```java
@Test
void peopleCollectionUsesHalAndExposesSearch() throws Exception {
    mvc.perform(get("/people")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.profile.href").exists())
        .andExpect(jsonPath("$._links.search.href").exists())
        .andExpect(jsonPath("$.page.size").exists());
}
```

Assertions should reflect the contract committed by the application. If the repository exports no query methods, a `search` link is not required. If the API root or base path is customized, use the application's actual paths.

## 8. Verifying POST, Location, and Persisted Data

A resource creation test must verify both the HTTP response and database state. Example:

```java
@Test
void postCreatesPersonAndReturnsLocation() throws Exception {
    String body = """
        {
          "firstName": "An",
          "lastName": "Nguyen"
        }
        """;

    MvcResult result = mvc.perform(post("/people")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaTypes.HAL_JSON)
            .content(body))
        .andExpect(status().isCreated())
        .andExpect(header().exists(HttpHeaders.LOCATION))
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andReturn();

    String location = result.getResponse()
        .getHeader(HttpHeaders.LOCATION);

    assertThat(location).isNotBlank();

    URI itemUri = URI.create(location);
    String path = itemUri.getPath();

    mvc.perform(get(path).accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.firstName").value("An"))
        .andExpect(jsonPath("$.lastName").value("Nguyen"));
}
```

This test verifies:

- POST collection returns `201 Created`.
- Response contains `Location` pointing to the new resource.
- Representation returns HAL with a self link.
- GET on the received resource URI returns the persisted data.

To verify persistence directly, you can inject `PersonRepository` and query after flushing/clearing the persistence context. However, re-checking via GET is valuable because it exercises the actual serialization and resource lookup paths used by clients.

Do not hard-code sequential IDs or concrete Locations like `/people/1`; IDs can vary with database sequences and test execution order.

## 9. Verifying GET Item, PUT/PATCH, and DELETE

An HTTP contract test should verify the semantics of each exported operation.

Example GET item after creation:

```java
@Test
void itemResourceContainsSelfLink() throws Exception {
    Person person = personRepository.saveAndFlush(
        new Person("Mai", "Tran"));

    mvc.perform(get("/people/" + person.getId())
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.firstName").value("Mai"))
        .andExpect(jsonPath("$._links.self.href").exists());
}
```

Example PATCH:

```java
@Test
void patchUpdatesOnlyRequestedProperty() throws Exception {
    Person person = personRepository.saveAndFlush(
        new Person("Mai", "Tran"));

    mvc.perform(patch("/people/" + person.getId())
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaTypes.HAL_JSON)
            .content("""
                {"firstName":"Linh"}
                """))
        .andExpect(status().isNoContent());

    Person updated = personRepository.findById(person.getId())
        .orElseThrow();

    assertThat(updated.getFirstName()).isEqualTo("Linh");
    assertThat(updated.getLastName()).isEqualTo("Tran");
}
```

Exact status codes depend on Spring Data REST version, configuration, and representation. Base assertions on your application's contract; if the framework returns `200` with a body instead of `204`, assertions must reflect the published and tested behavior.

Example DELETE:

```java
@Test
void deleteRemovesResource() throws Exception {
    Person person = personRepository.saveAndFlush(
        new Person("An", "Nguyen"));

    mvc.perform(delete("/people/" + person.getId()))
        .andExpect(status().isNoContent());

    assertThat(personRepository.existsById(person.getId())).isFalse();
}
```

Do not guess a status code. Cross-check your Spring Data REST version, configuration, and the endpoint's actual response contract.

## 10. Verifying Query Resources and Parameters

Exported query methods generate search resources. Tests should verify both discovery links and query results:

```java
@Test
void searchByLastNameReturnsMatchingPeople() throws Exception {
    personRepository.saveAndFlush(new Person("An", "Nguyen"));
    personRepository.saveAndFlush(new Person("Mai", "Tran"));

    mvc.perform(get("/people/search/findByLastName")
            .param("name", "Nguyen")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._embedded.people[0].lastName").value("Nguyen"));
}
```

If collection results can be empty or contain multiple items, avoid relying on fixed indices. Use appropriate JSONPath expressions to inspect the result set or check counts and item contents. Tests should create their own fixtures so results never depend on execution order of other tests.

## 11. Verifying Association Links and Persistence

For associations, tests must confirm the link relation appears and association mutations actually update the database.

Example creating Address and Person, then checking the association link:

```java
@Test
void personPublishesAddressAssociationLink() throws Exception {
    Address address = addressRepository.saveAndFlush(
        new Address("District 1"));

    Person person = personRepository.saveAndFlush(
        new Person("An", "Nguyen"));
    person.setAddress(address);
    personRepository.saveAndFlush(person);

    mvc.perform(get("/people/" + person.getId())
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.address.href").exists());
}
```

If the contract allows updating associations via URI, send requests with the media type and payload expected by the association endpoint. Afterward, reload the entity via the repository or GET the association to verify the foreign key changed.

Do not merely check that the link exists; the link must point to a working endpoint, the association must persist properly, and authorization must be enforced. For lazy associations, test serialization under production-like settings, especially with `open-in-view=false`.

## 12. Verifying Validation and Database Constraints

Bean Validation and database constraints protect different layers. You can test a request missing a required field:

```java
@Test
void invalidPersonIsRejected() throws Exception {
    mvc.perform(post("/people")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaTypes.HAL_JSON)
            .content("""
                {"lastName":"Nguyen"}
                """))
        .andExpect(status().isBadRequest());
}
```

If a unique constraint is part of the contract, create two resources with the same unique value and confirm the second request is rejected per the application's exception mapping. Do not rely on raw SQL messages or internal constraint names in public responses.

To prove a database constraint genuinely exists, you can test directly via repository/JDBC or attempt writes in separate transactions. When testing persistence errors, handle transactions marked rollback-only and avoid letting test errors corrupt a shared context.

Validation tests going only through HTTP might get blocked at Bean Validation before touching the database. Therefore, if the objective is verifying unique indexes/foreign keys, include dedicated persistence tests proving database constraints are enforced.

## 13. Transactions and Independent Test Data

Tests can pollute the database if created data is not cleaned up. Options include:

- Using `@Transactional` on tests to roll back changes within the same transaction.
- Deleting fixtures via repositories before/after tests.
- Using a separate database or schema per test class/suite.
- Using a separate container per class or suite.
- Using unique test data to prevent conflicts during parallel runs.

Be careful with `@Transactional` on MockMvc integration tests: HTTP requests may execute on a separate thread and transaction depending on test setup. The test transaction does not necessarily wrap the server request as expected, particularly with RANDOM_PORT. Verify whether data commits/rolls back per actual lifecycle and clean up proactively if needed.

With static containers, the database is normally shared across tests in the class. Fixture data must be cleaned or uniquely identified. Avoid test order dependencies and never rely on fixed sequence IDs.

## 14. Testing Contracts with a Server on a Real Port

MockMvc runs through the Spring MVC stack in the test process, but does not test network sockets or the full HTTP server runtime. For endpoints needing real HTTP verification, use RANDOM_PORT:

```java
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PersonHttpContractTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @LocalServerPort
    int port;

    @Test
    void rootRespondsWithHal() {
        given()
            .baseUri("http://localhost")
            .port(port)
            .accept("application/hal+json")
        .when()
            .get("/")
        .then()
            .statusCode(200)
            .contentType(containsString("application/hal+json"));
    }
}
```

This example uses RestAssured; appropriate dependencies and static imports are required. `TestRestTemplate` or `WebTestClient` can be used instead. The port is randomly chosen by Spring and injected via `@LocalServerPort`.

Use real-port tests for selected critical contracts, such as CORS, filter chains, cookies, redirects, headers, and network integration. MockMvc is generally faster and well suited for most endpoint tests.

## 15. Testing Migrations and Schema Drift

A fresh database container provides an opportunity to test all migrations from scratch:

1. Start an empty database.
2. Let Flyway/Liquibase run all migrations.
3. Boot JPA with `ddl-auto=validate`.
4. Run representative API create, read, update, and delete operations.
5. Verify required indexes, foreign keys, unique constraints, and defaults via behavior or database metadata.

You can add tests asserting the latest migration version was applied or that key tables/constraints exist. Avoid over-specifying non-contract implementation details; prioritize constraints protecting business integrity.

If production migrations rely on specific extensions, collations, enums, or timezone behavior, configure the container accordingly. Pin database image tags explicitly so builds today and tomorrow use the exact same engine version.

## 16. Testcontainers in CI

To keep tests reliable in CI:

- Use runners with a working Docker socket/runtime.
- Pin explicit image tags; avoid floating tags like `latest`.
- Set reasonable readiness timeouts and wait strategies if databases need startup time.
- Avoid hard-coding host ports.
- Do not share database containers across unrelated pipelines.
- Limit parallelism if CI resources are constrained.
- Use dedicated dummy credentials for tests; never pass production secrets into containers.
- Collect container logs when startup or migrations fail.
- Separate fast unit tests from Docker-dependent integration tests so developers can run each appropriately.

Maven command example:

```bash
mvn test
```

If integration tests run under Maven Failsafe, use the verify lifecycle:

```bash
mvn verify
```

Use naming conventions like `*IT` and configure Failsafe if you want to run the integration suite separately. Do not run Docker-dependent tests silently in every unit-test profile if some project environments lack container support.

## 17. Common Pitfalls

**Container fails to start**

Check Docker runtime, socket permissions, image pulls, resource limits, and container logs. Do not work around this by switching to H2 if the test goal is the real production database.

**Spring connects to database before container is ready**

Use `@Testcontainers`/container lifecycle or service connections properly; ensure dynamic properties are registered before the application context initializes.

**Tests pass on H2 but fail on PostgreSQL**

This is precisely why real engines matter. Check SQL dialect, reserved words, case sensitivity, type mappings, sequences, JSON columns, and migrations.

**Order-dependent tests**

Clean fixtures, use unique IDs/data, and never assume sequences start at 1.

**MockMvc test rolls back yet data persists**

Inspect transaction boundaries between the test thread and request processing. Use explicit cleanup or a verified transaction test strategy.

**Migrations do not run in tests**

Check whether Flyway/Liquibase is disabled by a test profile, whether the datasource points to the container, and whether schema locations/changelog paths are right.

**HAL response changes across versions**

Pin Spring Boot/Spring Data REST versions and assert contracts clients rely on, avoiding brittle dependence on JSON property order or unstable implementation details.

**Container tests are too slow**

Use static containers per test class/suite where safe, reuse application contexts, keep end-to-end test counts focused, and keep pure logic in unit tests. Only enable reusable containers when developer/CI environments have proper cleanup rules.

## 18. Minimum Recommended Contract Suite

For a Spring Data REST repository, an integration suite should cover core behaviors:

1. API root returns HAL and publishes collection/profile links.
2. Collection returns right media type, self/search/profile links, and page metadata.
3. POST returns matching status and Location; newly created resource can be read back.
4. GET item returns properties and self link.
5. PATCH/PUT modify data per published semantics.
6. DELETE removes resource and handles nonexistent items per contract.
7. Search resources and query parameters return right result sets.
8. Association links are navigable and association changes persist.
9. Validation rejects invalid payloads.
10. Database constraints enforce unique/foreign keys and migrations build the right schema.
11. Authorization/CSRF are tested per the application's security mode.
12. Conditional headers or pagination are tested if part of the client contract.

There is no need to test every endpoint over a real port. Choose a few representative flows to verify the server runtime; use MockMvc + Testcontainers for the bulk of integration tests.

## Summary

- Testcontainers provides a temporary real database to test Spring Data REST from HTTP through persistence.
- Use production-like images/versions and retrieve JDBC URL/credentials dynamically from the container.
- Combine `@SpringBootTest`, `@Testcontainers`, `@Container`, `@DynamicPropertySource`, or `@ServiceConnection`.
- Run Flyway/Liquibase against an empty database and use `ddl-auto=validate` to catch schema drift.
- Verify HAL links, media types, status codes, Location, queries, associations, and persisted data.
- MockMvc still works with real container databases; RANDOM_PORT additionally tests HTTP server/network behavior.
- Manage transactions and fixtures independently; avoid test order or fixed ID dependencies.
- Use real databases for SQL dialect, migrations, mappings, transactions, and constraints; keep unit tests for pure logic.
- CI needs a Docker-compatible runtime, pinned image tags, readiness strategies, and container logs on failure.

## References

- [Testcontainers for Java — JUnit 5 Quickstart](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/)
- [Spring Boot — Testcontainers Support](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot — Testing Spring Applications](https://docs.spring.io/spring-boot/reference/testing/)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Flyway — Migrations](https://documentation.red-gate.com/flyway)
