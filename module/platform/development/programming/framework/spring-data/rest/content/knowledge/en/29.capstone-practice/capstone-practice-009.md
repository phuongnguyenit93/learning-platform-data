# Completing the Contract Test Suite, Error Handling, and Deployment Configuration

## Objective

A Spring Data REST API may work properly on a developer machine yet break clients when paths, HAL relations, media types, status codes, error structures, or deployment configurations change. A complete test suite must lock down those public behaviors and verify the application starts cleanly under each environment's configuration.

This guide combines five parts:

1. Testing the HTTP/HAL contract with MockMvc.
2. Generating API documentation from tests using Spring REST Docs.
3. Standardizing and verifying error responses.
4. Managing profiles, externalized configuration, secrets, and health endpoints for deployment.
5. Integration testing against a real database with Testcontainers; adding Spring Cloud Contract when independent service consumers exist.

Examples use Java, JUnit Jupiter, Spring Boot, Spring Data REST, and Spring Data JPA. Use the Spring Boot BOM and a Spring Cloud release train compatible with your project's Boot version; do not mix arbitrary latest versions of individual libraries.

## 1. Defining the API Contract to Protect

The HTTP contract encompasses everything clients observe across requests and responses. For Spring Data REST, the contract typically includes:

- Root URI, base path, collection paths, and item paths.
- Supported HTTP methods: GET, POST, PUT, PATCH, DELETE.
- Content negotiation: request Accept, Content-Type, and returned media types.
- Status codes, Location, ETag, and headers meaningful to clients.
- HAL link relations such as self, search, profile, next, and relation names in _embedded.
- Field names, data types, nullability, projections, and representation structure.
- Paging, sorting, search, and association rules.
- Handling of validation failures, missing resources, conflicts, and authentication/authorization errors.

To keep relations stable, explicitly declare the collection path and relation when they are part of the contract:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

If clients rely on the **people** relation, changing it to **persons** can break clients even when the endpoint still returns HTTP 200. Likewise, changing fields, projections, media types, or status codes constitutes a contract change.

Test behaviors that clients genuinely depend on. Avoid locking down incidental details such as auto-generated IDs, JSON field ordering, CI hostnames, or timestamps without business meaning.

## 2. Contract Testing with MockMvc

MockMvc exercises full Spring MVC request handling through DispatcherServlet using mock requests and responses without starting an HTTP server. It is well suited to verifying mappings, data binding, message conversion, validation, exception handlers, and Spring Data REST responses inside the application context.

The example below assumes the application configures base path **/api** and collection relation **people**:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PeopleApiContractTest {

    private static final MediaType HAL_JSON =
        MediaType.parseMediaType("application/hal+json");

    @Autowired
    private MockMvc mvc;

    @Autowired
    private PersonRepository people;

    @Test
    void rootPublishesPeopleRelation() throws Exception {
        mvc.perform(get("/api").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(HAL_JSON))
            .andExpect(jsonPath("$._links.people.href").exists());
    }

    @Test
    void collectionUsesExpectedHalRelation() throws Exception {
        mvc.perform(get("/api/people").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$.page.size").exists());
    }

    @Test
    void createsPersonAndReturnsLocation() throws Exception {
        String email = "contract-" + UUID.randomUUID() + "@example.test";

        mvc.perform(post("/api/people")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(HAL_JSON)
                .content("""
                    {
                      "name": "Mai",
                      "email": "%s"
                    }
                    """.formatted(email)))
            .andExpect(status().isCreated())
            .andExpect(header().exists(HttpHeaders.LOCATION));

        assertThat(people.existsByEmail(email)).isTrue();
    }

    @Test
    void unknownItemReturnsNotFound() throws Exception {
        mvc.perform(get("/api/people/999999999").accept(HAL_JSON))
            .andExpect(status().isNotFound());
    }
}
~~~

The example uses **PersonRepository.existsByEmail(...)** to verify persistence; add the corresponding finder method if the repository does not already declare it. Creation tests should use unique data so repeated test runs do not interfere with one another.

When running tests in a real application, add static imports for MockMvc request builders, result matchers, JSONPath, AssertJ, and the required Spring classes. The snippet illustrates behaviors to verify; endpoints, entities, and validators must match your project configuration.

### Testing Errors and Content Negotiation

A contract test suite should include at least the following scenarios:

| Scenario | Request | Behavior to Assert |
|---|---|---|
| Read root | GET /api, Accept HAL JSON | 200, HAL media type, published relations exist |
| Read collection | GET /api/people | 200, _embedded relation and page metadata match |
| Valid create | POST with valid JSON | 201, Location points to the newly created item |
| Invalid data | POST or PATCH failing validation | Client error, typically 400; invalid data is not saved |
| Missing item | GET /api/people/{non-existent-id} | 404 |
| Unsupported media type | POST with unsupported Content-Type | 415 |
| Unsupported Accept | GET with Accept having no matching representation | 406 |
| Non-exported method | Calling an unsupported method on a resource | 405 |
| Missing authentication | Request to a protected resource | 401 per security configuration |
| Insufficient permissions | Authenticated user lacking authority | 403 per security configuration |
| Business conflict | Command invalid for current state | 409 if the API defines conflict semantics |
| Failed precondition | Stale If-Match | 412 if the API uses conditional requests |

Exact statuses depend on Spring Security configuration, validation, exception handlers, and endpoint types. Tests must codify the actual contract chosen for your application rather than assuming every error returns 400.

When verifying HAL, check relations inside **_links** and **_embedded**. Do not hardcode full absolute URLs if host or context path varies across local, CI, and production environments. When checking paths, compare path segments or match by suffix.

For pagination, seed enough records to span multiple pages and verify page size, page number, sorting, and `next`/`prev` links. For search resources, test both the search relation and query parameters. For associations, verify linked URIs and request media types.

## 3. Generating Contract Documentation with Spring REST Docs

Spring REST Docs generates documentation from tested requests and responses. Whenever an endpoint changes its status, headers, or body, tests and snippets surface the change together. This keeps documentation aligned with actual behavior.

Add the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.restdocs</groupId>
    <artifactId>spring-restdocs-mockmvc</artifactId>
    <scope>test</scope>
</dependency>
~~~

Use your project's dependency management or declare a compatible Spring REST Docs version if not managed by the BOM.

Example test generating default snippets:

~~~java
@ExtendWith(RestDocumentationExtension.class)
@SpringBootTest
class PeopleDocumentationTest {

    private static final MediaType HAL_JSON =
        MediaType.parseMediaType("application/hal+json");

    @Autowired
    private WebApplicationContext context;

    private MockMvc mvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        this.mvc = MockMvcBuilders.webAppContextSetup(context)
            .apply(documentationConfiguration(documentation))
            .build();
    }

    @Test
    void documentsPeopleCollection() throws Exception {
        mvc.perform(get("/api/people").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andDo(document("people-collection"));
    }
}
~~~

Spring REST Docs generates default snippets such as curl-request, http-request, http-response, request-body, and response-body. You can add snippets for request fields, response fields, and HAL links when documentation needs to describe every field and relation explicitly.

In Asciidoctor documentation, include snippets generated in the test output directory, for example:

~~~asciidoc
== People collection

include::{snippets}/people-collection/http-request.adoc[]
include::{snippets}/people-collection/http-response.adoc[]
~~~

Run tests and documentation builds inside CI. If required snippets are missing, the documentation build must fail instead of publishing stale docs. Never edit generated snippet files by hand; update the test and re-run to regenerate them.

### When to Use Spring Cloud Contract

MockMvc contract tests and Spring REST Docs protect the application's own API. When independent service consumers exist, Spring Cloud Contract adds consumer-driven contracts:

- The producer defines request/response contracts.
- The plugin generates producer-side tests verifying the implementation satisfies the contracts.
- Stubs are packaged and published for consumers to use in integration tests.
- Stub Runner downloads stubs and starts an HTTP stub server for collaborating services.

A minimal HTTP contract can declare method, path, headers, and status:

~~~yaml
description: read the people collection
request:
  method: GET
  url: /api/people
  headers:
    Accept: application/hal+json
response:
  status: 200
  headers:
    Content-Type: application/hal+json
~~~

Detailed syntax and matchers can be expanded using Spring Cloud Contract's Groovy or YAML DSL. If your project uses Spring Cloud Contract, import a Spring Cloud BOM compatible with Spring Boot; do not add an arbitrary plugin version in isolation.

Spring Cloud Contract does not replace HAL representation tests within the application. Keep producer tests verifying relations, embedded resources, media types, and pagination. Use stubs for consumers so consumers do not need to boot the entire upstream dependency graph.

## 4. Designing a Stable Error Contract

Clients need to know the status, error category, and how to proceed. A solid error contract provides:

- HTTP statuses that accurately reflect the error class.
- Stable error codes so clients handle errors programmatically instead of parsing prose messages.
- Concise messages that do not leak SQL, stack traces, table names, file paths, or secrets.
- A correlation/request ID for log tracing.
- Field errors when input data fails validation.
- A consistent structure across endpoints controlled by the application.

### Spring Data REST and Repository Exceptions

Spring Data REST uses its own exception handling for framework-managed controllers. For example, when a Spring Validator reports errors, the framework throws **RepositoryConstraintViolationException**; this exception wraps an **Errors** object and extends **DataIntegrityViolationException**. Spring Data REST has dedicated handlers for repository requests.

Therefore, verify real responses from Spring Data REST endpoints in MockMvc. Do not assume a **@RestControllerAdvice** written for custom controllers will automatically replace all repository exporter error handling. If you need custom handlers under the API base path that share Spring Data REST's configuration, message converters, and exception handling, consider **@RepositoryRestController** for custom endpoints.

### Problem Details for Custom MVC Endpoints

Spring Framework supports RFC 9457 Problem Details via **ProblemDetail**, **ErrorResponse**, and **ResponseEntityExceptionHandler**. Spring Boot can enable Problem Details handling for built-in Spring MVC errors with:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

For business errors from custom controllers, an exception handler can return ProblemDetail:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ResourceConflictException.class)
    ProblemDetail handleConflict(ResourceConflictException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "The resource cannot be changed in its current state."
        );

        problem.setType(
            URI.create("https://api.example.test/problems/resource-conflict")
        );
        problem.setTitle("Resource conflict");
        problem.setProperty("code", "RESOURCE_CONFLICT");

        return problem;
    }
}
~~~

The response looks like:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "https://api.example.test/problems/resource-conflict",
  "title": "Resource conflict",
  "status": 409,
  "detail": "The resource cannot be changed in its current state.",
  "code": "RESOURCE_CONFLICT"
}
~~~

In this example, **ResourceConflictException** is an application-defined business exception. The **code** field is a ProblemDetail extension property. Do not expose raw exception messages in responses if they could contain internal details.

Testing the custom error contract:

~~~java
@Test
void returnsProblemDetailsForBusinessConflict() throws Exception {
    mvc.perform(get("/api/custom/conflict"))
        .andExpect(status().isConflict())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.type").value(
            "https://api.example.test/problems/resource-conflict"
        ))
        .andExpect(jsonPath("$.status").value(409))
        .andExpect(jsonPath("$.code").value("RESOURCE_CONFLICT"));
}
~~~

The endpoint under test must actually throw **ResourceConflictException**. If the custom endpoint resides within the Spring Data REST URI space and should use the exporter's converters/exception handling, consider **@RepositoryRestController**. Write separate tests for each endpoint type because response handlers and media types can differ.

### Error Classification Table

| HTTP Status | Typical Meaning | Example |
|---|---|---|
| 400 Bad Request | Invalid request | Malformed JSON, validation failure |
| 401 Unauthorized | Unauthenticated | Missing or invalid token |
| 403 Forbidden | Not permitted | User lacks required authority |
| 404 Not Found | Resource does not exist | Non-existent ID |
| 405 Method Not Allowed | Unsupported method | DELETE on a read-only resource |
| 406 Not Acceptable | No representation matches Accept | Client requests an unsupported media type |
| 409 Conflict | Conflict with current state | Duplicate unique business key or forbidden state transition |
| 412 Precondition Failed | Request precondition no longer holds | If-Match does not match current ETag |
| 415 Unsupported Media Type | Unsupported request Content-Type | Sending XML to a JSON-only endpoint |
| 500 Internal Server Error | Unexpected failure | Unmapped programming or infrastructure error |

Never collapse all exceptions into 200 or 400. Returning accurate statuses enables proxies, retry policies, and clients to distinguish fixable request errors, auth failures, conflicts, and server failures.

## 5. Managing Configuration per Environment

Never hardcode database URLs, passwords, API tokens, or production base paths in Java. Spring Boot supports externalized configuration via application.properties/YAML, profile-specific files, environment variables, system properties, command-line arguments, and configuration trees.

### Using Typed Configuration with Validation

For application-specific configuration groups, prefer **@ConfigurationProperties** over scattering **@Value** annotations:

~~~java
@ConfigurationProperties(prefix = "app.api")
@Validated
public record ApiProperties(
    @NotBlank String basePath,
    @Min(1) @Max(200) int defaultPageSize
) {
}
~~~

Enable scanning on the application class:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

YAML configuration:

~~~yaml
app:
  api:
    base-path: /api
    default-page-size: 25

spring:
  data:
    rest:
      base-path: /api
~~~

When using validation annotations, ensure a Jakarta Validation provider dependency is on the classpath. If configuration values are missing or invalid, the application should fail at startup rather than accepting requests and failing later.

### Separating Profiles

Example layout:

~~~text
src/main/resources/
  application.yaml
  application-dev.yaml
  application-test.yaml
  application-prod.yaml
~~~

The base file holds safe defaults only. Profile files hold non-sensitive differences such as log levels, datasource drivers, pool sizes, or endpoint paths. Activate the profile from the deployment environment:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Profiles can also be passed via command line:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Spring Boot uses profile-specific configuration to override common settings. Higher-precedence property sources can override values inside packaged files. Thus, when runtime values differ from YAML, check active profiles and property source precedence rather than editing only the default file.

Never set **spring.profiles.active** inside a profile-specific file. Activate profiles from the main configuration file, environment variables, system properties, or command-line arguments.

### Keeping Secrets Outside the Artifact

Database configuration can be injected via environment variables:

~~~text
SPRING_DATASOURCE_URL=jdbc:postgresql://db-host:5432/app
SPRING_DATASOURCE_USERNAME=app_user
SPRING_DATASOURCE_PASSWORD=<secret-from-secret-store>
SPRING_PROFILES_ACTIVE=prod
~~~

Never commit real secrets into repositories, Docker images, logs, or packaged config files. For Kubernetes Secrets or Docker Secrets mounted as files, Spring Boot supports configuration trees:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Filenames in the configuration tree become property names. For example, a secret file named **spring.datasource.password** supplies that property; directory hierarchies can also represent property segments. Only use **optional:** when the application can genuinely start safely if that directory does not exist. For mandatory production secrets, let startup fail fast when secrets are missing.

Never print secrets to logs to verify binding. When verifying configuration, log the active profile name and whether configuration is present, never sensitive values.

## 6. Operational Configuration and Actuator

A baseline production configuration might look like:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

Expose only the Actuator endpoints needed. Spring Boot exposes only **health** over HTTP by default; additional endpoints can leak configuration, environment details, beans, or metrics. Protect management endpoints with network policies and Spring Security; never expose all endpoints with ***** on public networks.

### Liveness and Readiness

When running on Kubernetes, Spring Boot Actuator provides:

- **/actuator/health/liveness**: whether the instance is alive and capable of self-healing.
- **/actuator/health/readiness**: whether the instance is ready to accept traffic.

Liveness should reflect internal process health. Do not blindly wire database or shared-service checks into liveness: if the database goes down briefly, Kubernetes could restart all instances simultaneously and worsen the outage.

Readiness may evaluate external dependencies if those dependencies truly determine whether the instance can serve requests. Putting shared dependencies into readiness requires considering the impact when all instances become unready together.

Example probes in Kubernetes:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 10
~~~

If **management.server.port** is configured separately, probes must target that port. Verify that endpoints are actually exposed and reachable from kubelet in the deployment environment.

## 7. Testing Configuration and Real Databases

MockMvc contract tests verify MVC and Spring Data REST behavior, but an in-memory database may not reflect production database constraints, dialects, transactions, and migrations. For database-dependent flows, use Testcontainers to run a real database in Docker.

Add the test dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
~~~

Example declaring the container as a Spring bean using **@ServiceConnection**:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
~~~

Import the configuration into integration tests:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Import(PostgresTestConfiguration.class)
class PeopleDatabaseIntegrationTest {

    @Autowired
    private PersonRepository people;

    @Test
    void persistsAndReadsPerson() {
        Person saved = people.save(new Person(
            "Mai",
            "mai-" + UUID.randomUUID() + "@example.test"
        ));

        assertThat(people.findById(saved.getId())).isPresent();
    }
}
~~~

The example assumes a matching entity constructor and a PostgreSQL driver in the project. **@ServiceConnection** requires the **spring-boot-testcontainers** module; Docker must be available locally or on CI runners. On older Spring Boot versions without service connections, configure URL/username/password via **@DynamicPropertySource** or the property registration approach suited to that version.

Prefer managing container lifecycle via the Spring context when test contexts are cached. Do not let JUnit stop a container while an ApplicationContext is still reused by other tests. Testcontainers is ideal for verifying schema migrations, unique constraints, transaction rollbacks, paging, and query behavior on the real database engine.

### Testing Configuration Binding

You can pass test properties directly into a Spring Boot test:

~~~java
@SpringBootTest(properties = {
    "app.api.base-path=/test-api",
    "app.api.default-page-size=10"
})
class ApiPropertiesTest {

    @Autowired
    private ApiProperties properties;

    @Test
    void bindsConfiguredValues() {
        assertThat(properties.basePath()).isEqualTo("/test-api");
        assertThat(properties.defaultPageSize()).isEqualTo(10);
    }
}
~~~

Add tests verifying context startup fails when page size is 0 or base path is blank. This ensures invalid configuration is caught before deployment.

If using profile-specific files, verify the right profile is active in integration tests and CI. Never allow tests to accidentally pick up settings from a developer's local machine.

## 8. Integrating Steps into CI/CD

A pipeline can run steps in the following order:

1. **Compile and unit tests:** verify domain rules, mappers, services, and validators.
2. **HTTP contract tests:** run MockMvc tests for root, collections, CRUD, search, pagination, associations, media types, security, and error responses.
3. **REST Docs:** generate snippets from tests and build documentation; fail if required snippets are missing.
4. **Database integration tests:** run Testcontainers, apply migrations, and verify transactions and persistence.
5. **Package:** build the artifact/container image from the exact tested commit.
6. **Configuration validation:** supply required environment variables and verify the application context starts under the target profile.
7. **Deploy and smoke test:** verify health/readiness, API root, media types, authentication, and a safe read request.
8. **Post-deploy monitoring:** watch HTTP errors, startup failures, migrations, and readiness; keep an artifact rollback plan ready if smoke tests fail.

Never use production data in tests. Use ephemeral databases, test accounts, and CI secrets. Re-run documentation builds and contract tests whenever repository annotations, projections, DTOs, exception handlers, security, or base paths change.

### Post-Deployment Smoke Tests

Example verifying health and API root:

~~~bash
curl -fsS http://localhost:8080/actuator/health/readiness
curl -i -H "Accept: application/hal+json" https://api.example.test/api
~~~

The first command must succeed once the instance is ready. The second should return the expected media type, status, and root relations per the tested contract. If the API requires authentication, supply credentials retrieved from the pipeline secret store; never write tokens into scripts or logs.

## 9. Common Troubleshooting

| Symptom | Causes to Check | Resolution |
|---|---|---|
| MockMvc returns 404 for all endpoints | Wrong base path, repository not scanned, or repository not exported | Check **spring.data.rest.base-path**, repository package, and export configuration |
| Root has link but collection test fails | Relation or collection path changed | Check **path**, **collectionResourceRel**, and JSONPath expressions |
| HAL response returns 406 | Accept does not match supported media types | Send an appropriate Accept header, typically **application/hal+json** |
| POST returns 415 | Content-Type unsupported by converters | Send Content-Type **application/json** or the endpoint's expected media type |
| POST returns 400 | JSON binding failed or validator rejected input | Inspect request body, field constraints, and error response |
| Test expects 404 but gets 200/204 | Test ID collided with existing data or endpoint has different semantics | Use a controlled non-existent ID and verify resource mapping |
| ProblemDetail does not appear | Endpoint handled by Spring Data REST's own handler, Boot property disabled, or unsupported version | Distinguish custom MVC endpoints from repository endpoints; check version and exception handling |
| REST Docs generates no snippets | Test did not call **document(...)**, wrong output directory, or misconfigured build task | Check REST Docs extension/configuration and test reports |
| Spring Cloud Contract tests not generated | Incompatible plugin/BOM or invalid contract DSL | Check Spring Cloud release train, plugin config, and contract verifier logs |
| Testcontainers fails to start | Docker daemon not running, image pull blocked, or CI lacks container runtime | Check Docker availability, image access, and runner permissions |
| Tests pass locally but fail in CI | Differing profiles, env vars, timezones, DB versions, or secrets | Declare test config explicitly and use containers matching the target DB engine |
| Runtime configuration differs from YAML | Overridden by environment variables, command-line args, or external config | Inspect active profiles and property source precedence |
| App fails to start in production | Missing config/secrets or binding validation failed | Check env var names, mounted config trees, and required properties |
| Health reports UP yet traffic never arrives | Readiness probe uses wrong path/port or endpoint is not exposed | Check health groups, management port, security, and Kubernetes probe config |
| Instance restarts repeatedly during DB outage | Liveness depends on external database | Keep liveness focused on internal process state; evaluate dependencies in readiness |

## 10. Pre-Release Checklist

- [ ] Root URI and collection/item URIs match production configuration.
- [ ] HAL relations, _embedded, search, paging, and media types are locked down with contract tests.
- [ ] POST/PUT/PATCH/DELETE have tests covering both valid and error cases.
- [ ] Status codes 400, 401, 403, 404, 405, 406, 409, 412, and 415 are tested where supported by the API.
- [ ] Custom business errors have stable error codes and do not leak internal details.
- [ ] Spring Data REST validation errors are tested via the actual repository endpoints.
- [ ] REST Docs are generated from tests and documentation is built in CI.
- [ ] Consumer-driven contracts are used when independent consumers exist and managed via a compatible Spring Cloud BOM.
- [ ] Application-specific configuration uses **@ConfigurationProperties** with validation.
- [ ] Production profile is activated from the deployment environment.
- [ ] Database credentials and tokens live in a secret store or configuration tree.
- [ ] Actuator exposes only required endpoints with appropriate protection.
- [ ] Liveness does not arbitrarily depend on databases or shared services.
- [ ] Readiness path/port matches the Kubernetes probe.
- [ ] Testcontainers verifies the real database engine and migrations.
- [ ] CI runs contract tests, REST Docs, integration tests, and post-deploy smoke tests.

## 11. Official Documentation

- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): full Spring MVC request handling tests without a real server.
- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): scope of testing mappings, binding, conversion, validation, and exception handling.
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): MockMvc setup, generated snippets, and documentation builds.
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html): default request/response snippets.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): defining request/response contracts and generating stubs.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): fetching and running stubs for consumer integration tests.
- [Spring Data REST — Reference](https://docs.spring.io/spring-data/rest/reference/): repository resources, representations, validation, security, and conditional requests.
- [RepositoryRestExceptionHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html): exception handler for Spring Data REST controllers.
- [RepositoryConstraintViolationException API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/RepositoryConstraintViolationException.html): Spring Data REST validation exception and access to Errors.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, ErrorResponse, ResponseEntityExceptionHandler, and RFC 9457.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property source precedence, environment variables, configuration trees, and @ConfigurationProperties validation.
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): profile-specific files, active profiles, and profile groups.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, access control, and Kubernetes probes.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): container management, @ServiceConnection, and lifecycle within the Spring test context.