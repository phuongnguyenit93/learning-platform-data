# Ensuring Tests Run Reliably Across Environments

## Learning Objectives

After this lesson, you will be able to:

- Explain why documentation tests may pass locally yet fail or generate different snippets in CI.
- Design fixtures and test data with deterministic results.
- Control clocks, timezones, locales, random IDs, collection ordering, and database state.
- Isolate external dependencies such as HTTP services, message brokers, filesystems, and cloud storage.
- Keep MockMvc, WebTestClient, and REST Assured configurations consistent between local and CI environments.
- Avoid tests that depend on execution order, shared state, or unsafe parallel runs.
- Normalize snippets only as needed so diffs reflect API contract changes rather than environment noise.
- Collect logs and diagnose flaky tests systematically.

## 1. Why Must Documentation Tests Be Stable?

Spring REST Docs builds documentation from real tested HTTP exchanges. When tests run, requests, responses, and descriptors are written as snippets; Asciidoctor then includes those files in the documentation.

That means any unintended variation in a test can surface in the documentation:

- Timestamps changing with execution time.
- Randomly generated IDs making response bodies differ.
- Leftover database records from a prior run.
- Unspecified collection element ordering.
- Different host, port, or context path between local machines and CI.
- CI agent locale or timezone differing from developer environments.
- Flaky external dependencies or dependencies returning varying data.
- Parallel tests overwriting the same snippet output.

A test might pass while snippets constantly change. Pull requests then show diffs unrelated to the API contract, reviewers struggle to spot real changes, and builds can fail sporadically.

The goal is not to make every response look identical by hiding all data. The goal is to control non-contract factors while preserving the values consumers need to understand.

## 2. Principles for Designing Deterministic Tests

A stable documentation test usually has these traits:

1. Inputs are explicitly declared and do not depend on leftover environment data.
2. Clock, timezone, and locale are controlled when they affect output.
3. The database is reset or uses transactions/test containers with a clear lifecycle.
4. IDs and data ordering are predictable.
5. External dependencies are replaced with fakes/mocks or a stable test environment.
6. Server, port, context path, and serialization settings are consistent.
7. Each test has its own document identifier without overwriting another test's snippets.
8. Running repeatedly yields equivalent results.

Example fixture:

```java
Order order = new Order(
    42L,
    "ORD-2026-0001",
    OrderStatus.PENDING,
    Instant.parse("2026-01-15T08:30:00Z")
);
```

This fixture has fixed ID, order number, status, and timestamp. The test does not rely on randomly generated data or the current wall-clock time.

## 3. Controlling Time, Timezone, and Locale

Time is a common source of divergence. A response whose `createdAt` comes from `Instant.now()` changes on every run:

```java
order.setCreatedAt(Instant.now());
```

If the timestamp is part of the documented response, snippets can vary across builds. Inject a `Clock` so tests can fix the point in time.

### 3.1. Injecting Clock

In the application:

```java
@Configuration
class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Service using the clock:

```java
class OrderService {

    private final Clock clock;

    OrderService(Clock clock) {
        this.clock = clock;
    }

    Instant currentTime() {
        return Instant.now(clock);
    }
}
```

In tests, provide a fixed clock:

```java
@TestConfiguration
class FixedClockConfiguration {

    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
            Instant.parse("2026-01-15T08:30:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

If the application has multiple `Clock` beans, use explicit qualifiers to avoid injecting the wrong one. Do not swap a global clock via mutable static state because parallel tests can interfere with each other.

### 3.2. Standardizing Timezone

Prefer storing and processing timestamps with `Instant` or `OffsetDateTime` when the API contract requires offset representation. If a response uses local date/time, specify the timezone explicitly.

In tests, you can set the JVM timezone:

```bash
./gradlew test -Duser.timezone=UTC
```

Or configure the test task:

```groovy
tasks.withType(Test).configureEach {
    systemProperty 'user.timezone', 'UTC'
}
```

This is a safeguard. The better practice remains using time types with clear semantics and injecting `Clock` into code that needs the current instant.

### 3.3. Locale and Number/Date Formatting

Do not rely on `Locale.getDefault()` when API output requires fixed formatting. A CI agent may use a different locale, altering decimals, month names, or validation messages.

Example formatting with an explicit locale:

```java
DateTimeFormatter formatter =
    DateTimeFormatter.ofPattern("dd MMM uuuu", Locale.US);
```

If the API returns ISO-8601 JSON dates, configure the serializer consistently and test actual values. Do not let the host machine's display locale become an implicit part of the contract.

## 4. Fixtures and Deterministic IDs

Avoid generating random IDs in responses recorded into snippets when the ID is not what needs illustrating:

```java
UUID.randomUUID()
```

Replace with a deliberate fixture:

```java
UUID.fromString("123e4567-e89b-12d3-a456-426614174000")
```

Or inject an ID generator:

```java
interface IdGenerator {
    UUID nextId();
}
```

In tests:

```java
given(idGenerator.nextId())
    .willReturn(UUID.fromString(
        "123e4567-e89b-12d3-a456-426614174000"
    ));
```

If IDs are generated by a database sequence, seed/reset the sequence in test setup or use repository test fixtures to control values. Never depend on a sequence continuing from a prior test.

### 4.1. Dummy Yet Meaningful Data

Documentation data should be:

- Easy to read and interpret.
- Free of personal or production data.
- Stable across runs.
- Representative of typical API cases.
- Independent of random fixture creation order.

Example:

```json
{
  "id": 42,
  "orderNumber": "ORD-2026-0001",
  "status": "PENDING",
  "createdAt": "2026-01-15T08:30:00Z"
}
```

Avoid fixtures filled solely with `"foo"`, `"bar"`, `1`, `2` if that makes domain semantics hard for consumers to grasp. Equally, there is no need to use production data to create realistic examples.

## 5. Controlling Collection Ordering

Some collections do not guarantee order. If a response returns a list from a `HashMap`, `HashSet`, or a database query without `ORDER BY`, ordering can differ across runs or database engines.

Example query missing sorting:

```sql
SELECT id, order_number, status
FROM orders;
```

If the API contract requires ordering, add an explicit `ORDER BY`:

```sql
SELECT id, order_number, status
FROM orders
ORDER BY created_at DESC, id ASC;
```

If ordering is not part of the contract, documentation tests should verify the set of elements rather than relying on fixed positions. Still, snippets could reflect arbitrary ordering. You can use an ordered fixture collection in documentation tests so output stays stable.

In Java:

```java
List<Order> orders = List.of(
    orderFixture(42L, "ORD-001"),
    orderFixture(43L, "ORD-002")
);
```

Do not rely on `HashMap`/`HashSet` iteration order to build sample responses. If JSON object key ordering is not part of the contract, do not write assertions depending on key order; if snippets need stability for review, configure serializers/fixtures appropriately without turning key order into an API promise when the contract does not specify it.

## 6. Database Isolation and Leftover Data

Documentation tests can run against a real or test database. Without data isolation, tests can:

- Fail on a second run due to duplicate keys.
- Return extra records created by other tests.
- Depend on test execution order.
- Produce different snippets based on database state.
- Pass locally yet fail on a clean CI database.

Ways to address this:

### 6.1. Transaction Rollback

Where appropriate, wrap tests in transactions and roll back afterward:

```java
@Transactional
@Test
void documentsOrder() throws Exception {
    // Arrange, perform request, assert and document.
}
```

Rollback only works if both the request and database operations participate in the same test transaction. When a server runs on another thread or uses a separate transaction boundary, the test's transaction may not cover the request. Check how MockMvc/WebTestClient is configured.

### 6.2. Cleaning Up Data Before Each Test

You can use repository cleanup or SQL scripts to reset the database to a known state:

```java
@BeforeEach
void resetData() {
    orderRepository.deleteAll();
    customerRepository.deleteAll();
    seedDocumentationFixtures();
}
```

Cleanup order must respect foreign keys. For large datasets, delete only records belonging to the test namespace/fixture rather than wiping shared tables.

### 6.3. Testcontainers

Testcontainers provides dependency services with a managed lifecycle, such as PostgreSQL or Redis. Pin image versions and keep schema/data initialization consistent.

Do not use floating image tags like `latest` in CI if version changes can alter test results. Pin image versions or digests per project policy.

## 7. Isolating External Dependencies

Documentation tests should verify the application's HTTP contract. Do not let an external payment service, email provider, or third-party API decide whether a test passes or what data appears in snippets.

Dependencies that typically need replacement:

| Dependency | How to isolate |
| --- | --- |
| Payment gateway | Stub HTTP server or mock adapter |
| Email provider | Fake mail sender, verify generated message |
| Object storage | Local emulator or fake storage client |
| Message broker | Testcontainer or embedded broker with pinned version |
| External catalog API | Stub response fixture |
| Clock | Fixed Clock |
| Random ID | Deterministic generator |

If a test's goal is verifying integration with an external service, create a separate integration test against a controlled test environment. Do not make core documentation tests depend on the public internet or unstable sandboxes.

### 7.1. Stubbing HTTP Services

Conceptual WireMock example:

```java
stubFor(get(urlEqualTo("/catalog/items/42"))
    .willReturn(okJson("""
        {"id":42,"name":"Keyboard"}
        """)));
```

Pin the WireMock version and response fixtures. Reset stubs/mappings before each test so requests from a previous test do not affect subsequent tests.

## 8. Configuring MockMvc, WebTestClient, and REST Assured

Each test client sends requests and connects differently, yet the stability principle is identical: use the same application configuration, serialization, security, and fixtures.

### 8.1. MockMvc

MockMvc typically executes requests through Spring MVC infrastructure without opening a real TCP port. This keeps tests fast and less environment-dependent:

```java
mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("orders-get"));
```

Ensure tests use the same filter chain, controller advice, message converters, and configuration used by the API at runtime. Standalone MockMvc can miss parts of configuration if the project manually wires only a controller.

### 8.2. WebTestClient

`WebTestClient` can bind to an application context or hit a running server. Choose what fits the goal:

```java
webTestClient.get()
    .uri("/api/orders/{id}", 42)
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-get"));
```

If using a random port, do not embed the runtime port in prose or compared files when it is not part of the contract. Spring REST Docs normalizes some request elements, yet you should still inspect generated snippets.

### 8.3. REST Assured

REST Assured often suits integration tests calling the application over HTTP:

```java
given()
    .accept(ContentType.JSON)
    .pathParam("id", 42)
    .filter(document("orders-get"))
    .when()
    .get("/api/orders/{id}")
    .then()
    .statusCode(200);
```

Ensure base URI, port, context path, and filter configuration come from the test environment instead of hard-coding a local hostname.

## 9. Standardizing Local and CI Environments

Settings to keep uniform:

| Factor | Configuration to control |
| --- | --- |
| Java | Pinned toolchain/version |
| Gradle/Maven | Wrapper and plugin versions committed |
| Timezone | UTC or defined project timezone |
| Locale | Explicit locale for locale-sensitive data |
| Encoding | UTF-8 for source, process, and output |
| Database | Deterministic engine/version/schema/seed |
| Port | Random port for transport only, excluded from contract |
| Context path | Same value across tests and documentation |
| Environment variables | Clear test defaults, independent of developer machines |
| Dependency images | Pinned version or digest |

Gradle example:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
    systemProperty 'user.timezone', 'UTC'
    systemProperty 'file.encoding', 'UTF-8'
    systemProperty 'user.language', 'en'
    systemProperty 'user.country', 'US'
}
```

Set locale `en-US` only when that is the intentional test environment. If an API must return Vietnamese responses, explicitly test the `vi-VN` locale instead of relying on the machine's default locale.

## 10. Avoiding Order Dependencies and Unsafe Parallelism

A test must not rely on another test having created data or initialized static state. Each test should prepare its own fixtures or use safely shared immutable fixtures.

Common parallel execution failures:

- Two tests writing to the same document identifier.
- Two tests resetting/seeding the same database schema concurrently.
- A shared mock server being reset while another test uses it.
- Shared mutable singletons or caches.
- Tests writing to the same output file.

Solutions:

1. Use a unique document identifier per exchange/scenario.
2. Isolate databases/schemas or serialize test groups that need shared state.
3. Avoid mutable static fixtures.
4. Initialize/reset stubs per test lifecycle.
5. Enable parallel execution only when resources and snippet outputs are safe.

Example identifiers:

| Scenario | Document identifier |
| --- | --- |
| GET order succeeded | orders-get |
| GET order not found | orders-get-not-found |
| POST order succeeded | orders-create |
| POST order validation error | orders-create-invalid |

Do not reuse the same identifier across tests with differing requests/responses when they can overwrite each other or produce non-deterministic output.

## 11. Stabilizing Snippets Without Hiding the Contract

Spring REST Docs records preprocessed requests and responses. You can use preprocessors to normalize non-contract volatile data:

- Replace random request IDs with placeholders.
- Mask tokens, cookies, or sensitive information.
- Normalize host/port if they vary across environments.
- Remove headers meaningless to consumers that depend on infrastructure.

Example:

```java
preprocessRequest(
    removeHeaders("X-Internal-Trace")
)
```

Do not strip every header or field just to make snippets shorter. Keep information that consumers must send or understand.

### 11.1. Controlled Timestamp Substitution

If a timestamp is a field in the response contract, fix the `Clock` so test values are meaningful. You can substitute a placeholder when exact instants do not matter to the example, while preserving format/type:

```json
{
  "createdAt": "<timestamp>"
}
```

Do not use placeholders to hide a timezone or formatting bug. Tests must assert the real value/format before snippet preprocessing.

### 11.2. Normalizing Host and Port

Some tests run a server on a random port. If the port appears in snippets, preprocess the URI or configure appropriate REST Docs operation/request preprocessing. Before replacing it, check whether host/port is information consumers need or merely a test-environment detail.

Do not hard-code a fake production port in documentation. If documentation needs a base URL, describe it with a clear placeholder such as `https://api.example.test`.

## 12. Verifying Stability via Repeated Runs

A single green run does not prove tests are deterministic. Run documentation tests multiple times from a clean state:

```bash
./gradlew clean test
./gradlew clean test
```

Compare snippets between the two runs. Diffs should focus on contract content; changing timestamps, UUIDs, ports, or unstable ordering are signals to investigate.

You can use Git diff to inspect changes:

```bash
git diff -- build/generated-snippets
```

If `generated-snippets` is not tracked in Git, save two outputs to temporary directories and compare them with a CI diff tool. Never commit output just to mask a flaky test.

## 13. Diagnosing Flaky Documentation Tests

When a test fails only intermittently, gather evidence before increasing retries:

1. Record the failing test name and document identifier.
2. Save the actual request/response and assertion mismatch.
3. Record Java version, timezone, locale, and environment variables.
4. Inspect database state and seed data.
5. Inspect external dependencies, timeouts, and server logs.
6. Re-run the failing test in isolation multiple times.
7. Run the full suite to detect order dependencies.
8. Compare snippets across runs.

Retries may turn a pipeline temporarily green without fixing the root cause. Use retries only for recognized infrastructure faults, bounded and backed by telemetry; never use retries to mask race conditions or non-deterministic fixtures.

## 14. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Snippet timestamp changes every build | Using system clock directly | Inject `Clock` and fix test time |
| Response IDs differ | Random UUID/sequence | Seed sequence or mock ID generator |
| Response list order changes | Query lacks `ORDER BY` or unordered collection | Specify sorting or ordered fixtures |
| Passes alone, fails in suite | Shared state or order dependency | Isolate fixtures/DB and remove mutable static state |
| Passes locally, fails in CI | Differing Java/locale/timezone/config | Pin toolchain and standardize environment |
| Intermittent test timeouts | External dependency or overly short timeout | Stub dependencies, set reasonable timeouts, log failures |
| Snippets overwritten | Multiple tests share an identifier | Use unique identifiers per scenario |
| Parallel runs corrupt output | Shared DB, stub, or output file | Isolate resources or serialize test groups |
| Retries make CI green while bug remains | Flaky root cause unfixed | Investigate and eliminate nondeterminism |

## 15. Stability Verification Checklist

- [ ] Fixtures hold deterministic values and never use production data.
- [ ] Clock/timezone/locale are controlled whenever they affect output.
- [ ] ID generators and database sequences never produce unpredictable values.
- [ ] Queries use `ORDER BY` when order is part of the contract.
- [ ] Database is reset or isolated between tests.
- [ ] External dependencies are stubbed/faked or run in a fixed test environment.
- [ ] Java, build tools, encoding, and environment variables are pinned.
- [ ] MockMvc/WebTestClient/REST Assured use configurations matching runtime.
- [ ] Document identifiers do not collide across scenarios.
- [ ] Parallel execution never shares mutable state or output files.
- [ ] Preprocessors normalize environment details only, without hiding the contract.
- [ ] Repeated runs of documentation tests yield stable snippets.
- [ ] CI preserves logs and outputs needed for failure diagnosis.

## 16. Hands-On Exercise

A `GET /api/orders` endpoint returns a list of orders with fields `id`, `orderNumber`, `status`, and `createdAt`. Current tests occasionally generate different snippets due to timestamps, IDs, and list ordering.

Carry out the following steps:

1. Create a fixture of three orders with fixed IDs, order numbers, and timestamps.
2. Inject `Clock` and configure a fixed clock in tests.
3. Ensure the repository query has explicit sorting or the fixture list is ordered.
4. Reset the database before tests and verify tests do not depend on stale data.
5. Stub payment/catalog services if the endpoint calls external dependencies.
6. Assign distinct document identifiers for success and error scenarios.
7. Standardize timezone, locale, and encoding in the Gradle test task.
8. Run documentation tests twice from a clean state and compare generated snippets.
9. Enable controlled parallel tests and observe whether race conditions or overwritten outputs occur.
10. Document the root cause and fix if any non-deterministic diff appears.

**Self-Check Question:** If a response timestamp changes on every run, should you strip `createdAt` from snippets with a preprocessor? Only if that field is unnecessary for understanding the contract and a separate test verifies its format/semantics. Typically, inject a fixed `Clock` so snippets still show a valid, meaningful, and stable timestamp.

## Conclusion

Documentation tests produce trustworthy documentation only when results are repeatable across local and CI runs. Control fixtures, clocks, timezones, locales, IDs, collection ordering, database state, and external dependencies; match application and serialization configuration to runtime. Avoid shared mutable state, duplicate document identifiers, and parallel execution over shared resources. Preprocessors should only normalize environment details or mask sensitive data, never strip information belonging to the API contract. Run tests repeatedly from a clean state and compare snippets to detect nondeterminism early. When these factors are controlled, documentation diffs reflect real API changes and CI builds stay reliable.
