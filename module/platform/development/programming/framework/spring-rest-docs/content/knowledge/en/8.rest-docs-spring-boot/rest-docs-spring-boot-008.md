# Configuring Profiles, Ports, and Base URIs by Environment

## 1. Three Configuration Layers to Distinguish

In the Spring Boot chapter of the SPRING_REST_DOCS module, this lesson shows how to separate application environment configuration, the actual client address, and the URI recorded into snippets by Spring REST Docs. These three layers serve different purposes and should not be used interchangeably.

| Layer | Example | Effect |
| --- | --- | --- |
| Application profile | @ActiveProfiles("test"), application-test.yml | Selects beans and properties when creating the Spring context. |
| HTTP client | @SpringBootTest(RANDOM_PORT), @LocalServerPort | Determines the server and port that requests actually target. |
| URI in snippets | uriScheme, uriHost, uriPort | Controls the URL displayed in documentation without changing the real server. |

After this lesson, you can select test profiles, boot an embedded server with RANDOM_PORT, configure the base URI for WebTestClient/REST Assured, customize snippet URLs, and integrate these configurations safely into CI.

Examples use Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and Java 17+. With Boot 4.x, use test packages/modules matching your major version.

## 2. Profiles for the Test Environment

Spring profiles let the application choose configuration when creating the ApplicationContext. In tests, @ActiveProfiles("test") tells Spring Test to activate the test profile.

The application-test.yml file can hold test-specific settings:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:catalog-test;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
```

This is an example for H2 and JPA; omit unrelated properties if the project does not use them. Never copy production credentials into test profiles.

```java
@SpringBootTest
@ActiveProfiles("test")
class CatalogApplicationTest {
    // ...
}
```

When you need to override a few properties for one test class, use @SpringBootTest(properties = {...}) or @TestPropertySource(properties = {...}). Tests should declare profiles explicitly rather than relying on whatever profile happens to be active in a developer's shell.

## 3. Server Ports: RANDOM_PORT and @LocalServerPort

| Mode | Behavior | Server Listening on a Port? |
| --- | --- | --- |
| MOCK | Mock web application context. | No |
| RANDOM_PORT | Starts an embedded server on a dynamically assigned port. | Yes |
| DEFINED_PORT | Starts the server on the configured port. | Yes |
| NONE | Does not start a web environment. | No |

For CI and parallel test runs, RANDOM_PORT is generally safer than DEFINED_PORT because it does not require port 8080 to always be free.

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class CatalogHttpIntegrationTest {
    @LocalServerPort
    int port;
}
```

Spring Boot assigns the port when the server starts; @LocalServerPort receives the actual port. Do not hardcode 8080. If constructing REST Assured or another HTTP client manually, pass the injected port into the client configuration.

## 4. Base URI of the HTTP Client

With WebFlux, @AutoConfigureWebTestClient provides WebTestClient. When combined with @SpringBootTest(RANDOM_PORT), Boot configures the client to call the embedded server.

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@AutoConfigureWebTestClient
@AutoConfigureRestDocs(outputDir = "build/generated-snippets/status-http")
class StatusHttpDocumentationTest {
    @Autowired
    WebTestClient client;

    @Test
    void status() {
        client.get().uri("/api/status")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("UP")
            .consumeWith(document("status-get"));
    }
}
```

If you use WebTestClient.bindToController(...) or bindToApplicationContext(...), the client binds directly to the controller/context; that is not HTTP evidence over a server port.

With REST Assured, configure RequestSpecification using the injected port:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@ExtendWith(RestDocumentationExtension.class)
class StatusRestAssuredDocumentationTest {
    @LocalServerPort
    int port;
    RequestSpecification spec;

    @BeforeEach
    void configure(RestDocumentationContextProvider context) {
        spec = new RequestSpecBuilder()
            .setBaseUri("http://localhost")
            .setPort(port)
            .addFilter(documentationConfiguration(context))
            .build();
    }
}
```

The actual base URI is http://localhost:<random-port>. The spring-restdocs-restassured dependency is required. Configuring the REST Docs filter manually is explicit; do not mix it with auto-configuration on the same client.

## 5. URI Displayed in Snippets

```java
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets/catalog-http",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
```

Suppose the real request goes to http://localhost:53127/api/catalog; the snippet can display https://api.example.com/api/catalog. uriScheme, uriHost, and uriPort only change the recorded URI; they do not enable TLS, do not change the server port, and do not change the client's base URL.

For individual operations, you can use modifyUris() as an operation preprocessor to rewrite host/scheme in the documented output. Inspect snippets after making changes and take care to preserve the base path accurately.

## 6. Context Path and Base Path

For Spring MVC servlets, server.servlet.context-path sets the runtime prefix. For WebFlux, the corresponding property is spring.webflux.base-path.

```yaml
server:
  servlet:
    context-path: /catalog
```

When a controller has @GetMapping("/products"), the full URL of the servlet app is /catalog/products. The client must request the matching prefix. If the client's base URL already includes the context path, do not prepend the prefix a second time in the request URI. Configuring a context path affects real routing, unlike uriHost/uriScheme/uriPort which only control snippet presentation.

If production runs behind a reverse proxy with prefix /gateway/catalog while the internal app serves /catalog, URL rewriting belongs to the gateway/deployment layer. You can preprocess snippet URIs to document the public URL, though a separate integration test is required if you want to verify the actual gateway.

## 7. Dynamic Property Values

When a database container or mock server uses a dynamic port, use @DynamicPropertySource to supply values to the Spring Environment instead of hardcoding them in application-test.yml.

```java
@DynamicPropertySource
static void partnerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.base-url", () -> partnerServer.url("/").toString());
}
```

This example assumes MockWebServer has started before the Spring context reads the dynamic property. With Testcontainers, you can register a supplier such as container::getJdbcUrl after the container initializes.

Distinguish @LocalServerPort (the application's port), @DynamicPropertySource (external dependency ports/URLs), and @AutoConfigureRestDocs(uriPort=...) (the port displayed in snippets).

## 8. Combining Profiles and REST Docs

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets/catalog-http",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
class CatalogHttpDocumentationTest {
    // Inject client, send request to embedded server, then call document(...).
}
```

The profile selects runtime configuration; RANDOM_PORT starts the embedded server; the client sends requests to the real server; outputDir determines where snippets are written; uriScheme/uriHost/uriPort only control the URI displayed in snippets.

## 9. Gradle, Maven, and CI

With Gradle, outputDir and Asciidoctor's input must match:

```groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets/catalog-http')

tasks.named('test') {
    useJUnitPlatform()
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.get().asFile
}
```

If HTTP tests reside in an integrationTest task, Asciidoctor must depend on that task. With Maven, if outputDir is target/generated-snippets/catalog-http, the snippets attribute must point to the corresponding directory under project.build.directory. Run Asciidoctor after the snippet-generating test group; prepare-package works for tests running in the test phase, but not if snippets are only created during Failsafe verify.

CI should run tests and build documentation in the same pipeline. Example: ./gradlew clean test asciidoctor. Supply secrets and dependent endpoints via a secret store/environment or mock services; never commit production tokens, passwords, or sensitive internal URLs into test profiles.

## 10. Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Test accidentally uses production profile | Missing @ActiveProfiles("test") or interference from environment variables. | Activate the profile explicitly and verify properties in the test context. |
| @LocalServerPort cannot be injected | Not running with RANDOM_PORT/DEFINED_PORT. | Use @SpringBootTest(RANDOM_PORT) with a web stack. |
| REST Assured calls the wrong port | Hardcoded 8080 or missing port injection. | Use @LocalServerPort and setPort(port). |
| Snippet shows localhost:random-port | REST Docs is recording the test server URI. | Set uriScheme, uriHost, and uriPort. |
| Snippet has public host and requests target that host | Confused snippet URI with client base URL. | Keep the client targeting the test server; configure REST Docs separately. |
| Context path duplicated twice | Prefix present in both base URL and request path. | Include the prefix only once. |
| Dynamic property reads a port before it is ready | Container/mock server has not started yet. | Start the resource before context initialization. |
| Asciidoctor cannot find snippets | outputDir and snippets attribute differ. | Align both paths and the operation ID. |

## 11. Practice Exercise

Create a Catalog API and complete the following:

1. Create application-test.yml with test-specific database/properties; enable @ActiveProfiles("test").
2. Use @SpringBootTest(RANDOM_PORT) and obtain the port via @LocalServerPort.
3. Send requests using WebTestClient for WebFlux or REST Assured for REST Assured; verify status, JSON, and headers.
4. Configure snippets to display https://api.example.com while the client still calls the local embedded server.
5. Add a context path, observe the client URL and snippet, and confirm the prefix is not duplicated.
6. Use @DynamicPropertySource to supply a mock server URL or Testcontainers JDBC URL.
7. Run a clean build and Asciidoctor in CI; confirm fresh snippets without secrets or unintended random ports.

**Completion criteria:** distinguish profiles, client base URIs, and snippet URIs; tests use dynamic ports; documentation renders the right URLs; base paths are handled only once; no production secrets appear in snippets; CI regenerates documentation independently of developer machines.

## 12. References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot 3.5 — AutoConfigureRestDocs API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/restdocs/AutoConfigureRestDocs.html)
- [Spring Boot 3.5 — LocalServerPort API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/server/LocalServerPort.html)
- [Spring REST Docs — Configuration: Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
