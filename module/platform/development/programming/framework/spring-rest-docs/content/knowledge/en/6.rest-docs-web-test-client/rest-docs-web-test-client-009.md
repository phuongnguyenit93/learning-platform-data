# Documenting WebFlux Endpoints and Compatible MVC Endpoints

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, we generate verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests and assert responses; Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers; Asciidoctor/Markdown assembles the snippets in the build and CI pipeline.

The **WebTestClient** chapter focuses on the HTTP test client with a fluent API. However, a Spring application can handle requests using two different web stacks:

- **Spring WebFlux**: reactive model, typically using controllers returning §Mono§/§Flux§ or functional endpoints.
- **Spring MVC**: Servlet model, typically using synchronous controllers returning DTOs/§ResponseEntity§, though MVC also supports several forms of asynchronous processing.

§WebTestClient§ was designed for testing WebFlux, but Spring also provides the §MockMvcWebTestClient§ adapter so you can use the WebTestClient interface with Spring MVC. Thanks to this adapter, you can write requests, assertions, and REST Docs in a similar style for both stacks.

After this lesson, you will be able to:

- Distinguish binding WebTestClient directly to WebFlux from binding via MockMvc for Spring MVC.
- Choose §bindToController(...)§ or §bindToApplicationContext(...)§ based on test scope.
- Configure the Spring REST Docs filter for both endpoint styles.
- Write JUnit 5 tests generating snippets from both reactive controllers and MVC controllers.
- Use §MockMvcWebTestClient.resultActionsFor(...)§ when MockMvc-specific assertions are needed.
- Avoid confusing the MVC test adapter with a real WebFlux server or an HTTP connection over the network.

## 2. Two Web Stacks, One Testing Interface

What they share is that tests can be written in the same fluent chain:

~~~java
client.get()
    .uri("/api/greetings")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.message").isEqualTo("Hello");
~~~

However, the target handling requests behind the client differs:

| Aspect | WebFlux | Spring MVC |
| --- | --- | --- |
| Web stack | Reactive WebFlux | Servlet-based Spring MVC |
| Direct controller binding | §WebTestClient.bindToController(...)§ | §MockMvcWebTestClient.bindToController(...)§ |
| Binding to Spring context | §WebTestClient.bindToApplicationContext(...)§ | §MockMvcWebTestClient.bindToApplicationContext(...)§ |
| Common controller return types | §Mono<T>§, §Flux<T>§, or other supported reactive types | DTOs, §ResponseEntity<T>§, MVC return types |
| Infrastructure under test | WebFlux §HttpHandler§ and WebFlux beans in context | MockMvc and Servlet MVC infrastructure |
| Opens a network port? | No, with direct/context binding | No, the adapter dispatches requests to MockMvc |

~~~mermaid
flowchart TD
    A["Test using fluent WebTestClient API"] --> B{"Which platform is the endpoint on?"}
    B -->|"Spring WebFlux"| C["WebTestClient.bindToController / bindToApplicationContext"]
    B -->|"Spring MVC"| D["MockMvcWebTestClient.bindToController / bindToApplicationContext"]
    C --> E["REST Docs documentationConfiguration filter"]
    D --> E
    E --> F["exchange + expectStatus/header/body"]
    F --> G["consumeWith(document(...))"]
    G --> H["Snippets → Asciidoctor / CI"]
~~~

**Rule for choosing the API:** use §WebTestClient.bindTo...§ for WebFlux applications; use §MockMvcWebTestClient.bindTo...§ when the endpoint runs on Spring MVC. The MVC adapter uses MockMvc to execute requests inside the test environment; it does not turn an MVC application into WebFlux.

## 3. Dependencies and Platform-Specific Configuration

### 3.1. WebFlux Project

Example Gradle Groovy DSL dependencies for a Spring Boot WebFlux application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient'
}
~~~

### 3.2. Spring MVC Project

For an MVC application, use starter web instead of starter WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient'
}
~~~

§spring-boot-starter-test§ provides Spring Test and MockMvc; §spring-restdocs-webtestclient§ provides REST Docs integration for WebTestClient. §MockMvcWebTestClient§ is part of Spring Test. Spring Boot usually manages compatible dependency versions.

For projects not using Spring Boot, declare compatible versions of Spring Framework, Spring Test, Spring REST Docs, and JUnit 5. Do not copy versions verbatim from another project if Spring Framework and Spring REST Docs versions are out of sync.

**Note on applications with both starters:** if both §spring-boot-starter-web§ and §spring-boot-starter-webflux§ are on the classpath, Spring Boot typically prefers MVC configuration when both are present. A controller returning §Mono§ does not by itself prove the application is running on WebFlux. Verify the web application type and actual runtime infrastructure before choosing the binding API. When tests use two separate configurations, isolate the test contexts to avoid accidentally testing the wrong stack.

## 4. Shared REST Docs Configuration

With JUnit 5, Spring REST Docs provides §RestDocumentationExtension§ and §RestDocumentationContextProvider§:

~~~java
@ExtendWith(RestDocumentationExtension.class)
class GreetingDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        // Create the client according to the web platform under test.
    }
}
~~~

After creating the appropriate builder, attach the filter:

~~~java
.configureClient()
.filter(documentationConfiguration(restDocumentation))
.build();
~~~

For clients created via §bindToController(...)§ or §bindToApplicationContext(...)§, §configureClient()§ transitions from test server setup to client configuration so filters can be added. §documentationConfiguration(...)§ registers HTTP transaction recording for Spring REST Docs. In each test to be documented, call §consumeWith(document("operation-id", ...))§.

Two primary static imports:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;
~~~

The MVC test class uses §MockMvcWebTestClient§ to instantiate the client, yet the REST Docs filter is still configured through the WebTestClient mechanism. This allows using the exact same descriptor types such as §pathParameters§, §requestFields§, §responseFields§, §requestHeaders§, and §responseHeaders§.

## 5. WebFlux Example: Documenting a Reactive Controller

Suppose a WebFlux endpoint §GET /api/greetings§ returns JSON:

~~~json
{
  "message": "Hello"
}
~~~

Complete test:

~~~java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class WebFluxGreetingDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new GreetingController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsGreetingEndpoint() {
        client.get()
            .uri("/api/greetings")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.message").isEqualTo("Hello")
            .consumeWith(document("webflux/greetings",
                responseFields(
                    fieldWithPath("message")
                        .description("Greeting returned to the client")
                )
            ));
    }

    @RestController
    static class GreetingController {

        @GetMapping(
            path = "/api/greetings",
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Mono<Map<String, String>> greeting() {
            return Mono.just(Map.of("message", "Hello"));
        }
    }
}
~~~

Here:

1. §WebTestClient.bindToController(...)§ creates a WebFlux test environment from the specified controller.
2. §documentationConfiguration(...)§ registers the REST Docs filter on the client.
3. §exchange()§ performs the request; status, content type, and JSON are asserted.
4. §consumeWith(document("webflux/greetings", ...))§ generates snippets and the response field description table.

The controller returns a §Mono§, and the test only needs to verify a finite JSON response. If an endpoint returns a finite `Flux` encoded as a JSON array, you can verify elements with JSONPath and write descriptors matching the array structure. For non-terminating streams such as SSE, use a separate stream testing strategy rather than buffering the entire body just to generate snippets.

## 6. Spring MVC Example: Using MockMvcWebTestClient

Suppose an MVC application has a synchronous controller:

~~~java
@RestController
class MvcGreetingController {

    @GetMapping(
        path = "/api/mvc/greetings",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> greeting() {
        return Map.of("message", "Hello from MVC");
    }
}
~~~

To test this controller using the fluent WebTestClient API, initialize the client from §MockMvcWebTestClient§:

~~~java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class MvcGreetingDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = MockMvcWebTestClient
            .bindToController(new MvcGreetingController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsMvcGreetingEndpoint() {
        client.get()
            .uri("/api/mvc/greetings")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.message").isEqualTo("Hello from MVC")
            .consumeWith(document("mvc/greetings",
                responseFields(
                    fieldWithPath("message")
                        .description("Greeting from the Spring MVC controller")
                )
            ));
    }

    @RestController
    static class MvcGreetingController {

        @GetMapping(
            path = "/api/mvc/greetings",
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Map<String, String> greeting() {
            return Map.of("message", "Hello from MVC");
        }
    }
}
~~~

The difference lies in the initialization line:

~~~java
MockMvcWebTestClient.bindToController(new MvcGreetingController())
~~~

The adapter routes WebTestClient requests into MockMvc, where Spring MVC invokes the controller and Servlet MVC infrastructure. Calls to §exchange()§, §expectStatus()§, §expectHeader()§, §expectBody()§, and §consumeWith(document(...))§ remain familiar.

Do not replace that line with §WebTestClient.bindToController(...)§ to test an MVC controller. That direct binding targets WebFlux; it does not set up the MockMvc Servlet infrastructure.

## 7. Binding to ApplicationContext Instead of a Single Controller

Direct controller binding works well for endpoint-focused tests. When you need to verify routing, controller advice, converters/codecs, filters, or other beans in the web configuration, bind to a Spring context built for the test.

### 7.1. WebFlux ApplicationContext

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(webFluxApplicationContext)
    .configureClient()
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

§webFluxApplicationContext§ must be a context containing WebFlux configuration and the beans under test.

### 7.2. Spring MVC ApplicationContext

~~~java
WebTestClient client = MockMvcWebTestClient
    .bindToApplicationContext(mvcWebApplicationContext)
    .configureClient()
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

§mvcWebApplicationContext§ must be a Spring MVC WebApplicationContext. For Spring Boot MVC tests, you can use a test slice like §@WebMvcTest§ or a suitable integration context, then inject the context to create the adapter. For WebFlux, use the corresponding WebFlux test configuration.

**Do not use the wrong context:** an ApplicationContext containing a controller does not necessarily include the right web infrastructure. Check the application type, MVC/Flux configuration, bean dependencies, and required filters in the test. Test slices intentionally restrict loaded beans; services or repositories excluded from the slice must be supplied as mock/test beans if the controller depends on them.

## 8. When Do You Need Access to MockMvc ResultActions?

Usually, WebTestClient assertions are sufficient to verify status, headers, and body. In some MVC tests, you may need MockMvc-specific matchers or APIs. §MockMvcWebTestClient§ provides §resultActionsFor(exchangeResult)§ to obtain §ResultActions§ from the received result.

Example:

~~~java
import org.springframework.test.web.servlet.ResultActions;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

var exchangeResult = client.get()
    .uri("/api/mvc/greetings")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .returnResult();

ResultActions mvcResult = MockMvcWebTestClient.resultActionsFor(exchangeResult);

mvcResult
    .andExpect(status().isOk())
    .andExpect(handler().handlerType(MvcGreetingController.class));
~~~

This snippet assumes §client§ was created via §MockMvcWebTestClient§ and the MVC endpoint exists. §resultActionsFor(...)§ is strictly for the MVC adapter; do not use it with a regular WebFlux client. It is helpful when assertions rely on servlet handler details, models, or MockMvc execution results that WebTestClient's fluent assertions do not express directly.

For REST Docs documentation, continue using the §documentationConfiguration(...)§ filter and §document(...)§ callback on the WebTestClient exchange. You do not need to switch to MockMvc REST Docs just because the MVC test uses the adapter; stick to a single consistent documentation mechanism per test.

## 9. Using Common Descriptors for WebFlux and MVC

Because both approaches use the WebTestClient REST Docs integration, common descriptors stay identical:

| API Content | Descriptor |
| --- | --- |
| Path parameter | §pathParameters(parameterWithName("id").description(...))§ |
| Query parameter | Query/request parameter API matching your REST Docs version |
| Request header | §requestHeaders(headerWithName("X-Request-Id").description(...))§ |
| Response header | §responseHeaders(headerWithName("Location").description(...))§ |
| Request JSON field | §requestFields(fieldWithPath("name").description(...))§ |
| Response JSON field | §responseFields(fieldWithPath("message").description(...))§ |

Example of a POST operation that can share the same descriptor pattern:

~~~java
client.post()
    .uri("/api/greetings")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("name", "Lan"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .jsonPath("$.message").isEqualTo("Hello, Lan")
    .consumeWith(document("greetings/create",
        requestFields(
            fieldWithPath("name").description("Name of the greeting recipient")
        ),
        responseFields(
            fieldWithPath("message").description("The generated greeting")
        )
    ));
~~~

This is an illustrative snippet; the POST endpoint must actually be declared in the corresponding controller/router and return status 201 with JSON matching that structure. When targeting WebFlux or MVC, client initialization must match the stack as shown in earlier sections.

Descriptors ensure documentation is more than a copy of JSON. If the response adds an undocumented required field, REST Docs can fail the test. Update descriptors after reviewing the contract change; use §.optional()§ or §.ignored()§ when consistent with the field's actual semantics.

## 10. Comparing Direct Binding, Context Binding, and Real Servers

| Test Type | Initialization API | Infrastructure Included in Test | When to Use |
| --- | --- | --- | --- |
| WebFlux controller | §WebTestClient.bindToController(...)§ | Controller and mock WebFlux infrastructure | Narrowly scoped reactive endpoint tests |
| WebFlux context | §WebTestClient.bindToApplicationContext(...)§ | Beans and web config inside the WebFlux context | Testing WebFlux routing/filters/advice |
| MVC controller | §MockMvcWebTestClient.bindToController(...)§ | Controller and MockMvc MVC infrastructure | Testing MVC endpoints via the fluent WebTestClient API |
| MVC context | §MockMvcWebTestClient.bindToApplicationContext(...)§ | WebApplicationContext and MockMvc setup | Testing MVC configuration and beans in the context |
| Real HTTP server | §WebTestClient.bindToServer()§ | Network connection to a running server | Integration tests for ports, proxies, or end-to-end HTTP behavior |

§MockMvcWebTestClient§ does not open an HTTP port; requests are executed via MockMvc. If your goal is to test deployment, ports, proxies, or an actual network server, use a client bound to a running server. With the last option, server startup/shutdown and the base URL must be managed in test setup.

## 11. Including Snippets in Asciidoctor and CI

In the examples, identifiers separate the two platforms so readers can easily recognize the source:

~~~text
build/generated-snippets/
├── webflux/
│   └── greetings/
│       ├── http-request.adoc
│       ├── http-response.adoc
│       └── response-fields.adoc
└── mvc/
    └── greetings/
        ├── http-request.adoc
        ├── http-response.adoc
        └── response-fields.adoc
~~~

These are representative snippets; actual files depend on request/response types and descriptors. An Asciidoctor page can combine both:

~~~asciidoc
= Greetings API
:snippets: build/generated-snippets

== WebFlux endpoint
include::{snippets}/webflux/greetings/http-request.adoc[]
include::{snippets}/webflux/greetings/http-response.adoc[]
include::{snippets}/webflux/greetings/response-fields.adoc[]

== MVC endpoint
include::{snippets}/mvc/greetings/http-request.adoc[]
include::{snippets}/mvc/greetings/http-response.adoc[]
include::{snippets}/mvc/greetings/response-fields.adoc[]
~~~

With Gradle (assuming the Asciidoctor plugin and §asciidoctor§ task are configured):

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

CI can run §./gradlew clean test asciidoctor§ once tasks are fully configured. Both WebFlux and MVC tests must pass before the page is built. If descriptors do not match payloads or status/header/body assertions fail, the build must catch the error instead of publishing stale documentation as current. Plain Markdown requires a separate step to inline or link snippets; the §include::§ syntax belongs to Asciidoctor.

## 12. Common Errors and How to Resolve Them

| Symptom | Cause and Resolution |
| --- | --- |
| MVC controller is not mapped when using §WebTestClient.bindToController(...)§ | Wrong adapter in use; use §MockMvcWebTestClient.bindToController(...)§ for Spring MVC. |
| WebFlux controller does not work with MockMvc adapter | §MockMvcWebTestClient§ is for Spring MVC; switch to WebTestClient bound to WebFlux. |
| Spring Boot selects MVC despite WebFlux dependency | Check whether both starters are on the classpath and inspect application type configuration; identify the real infrastructure before selecting tests. |
| MVC test is missing a bean | Test slices omit business beans; add mock/test beans or use a broader context matching your goal. |
| Filters/ControllerAdvice do not run as in production | Direct controller binding does not load full configuration automatically; consider binding to the appropriate context. |
| REST Docs filter is not invoked | Verify the right client has §documentationConfiguration(...)§ and the request to document calls §consumeWith(document(...))§. |
| No snippets after MVC test passes | Check §spring-restdocs-webtestclient§, the document callback, and the generated snippets directory. |
| Cannot use §resultActionsFor(...)§ | This method is for results from MockMvcWebTestClient; do not call it on a regular WebFlux WebTestClient. |
| Asciidoctor cannot find snippet | Check the operation identifier, output directory, and the test → asciidoctor task dependency. |

## 13. Practice Exercises

1. Run §WebFluxGreetingDocumentationTest§, locate the §webflux/greetings§ snippets, and compare the JSON against the assertions.
2. Run §MvcGreetingDocumentationTest§, confirm the client is created with §MockMvcWebTestClient§, and check that snippets are under §mvc/greetings§.
3. Intentionally replace §MockMvcWebTestClient§ with §WebTestClient§ in the MVC test, observe the difference in environment setup, and restore the proper adapter.
4. Convert an MVC test from controller binding to ApplicationContext binding; add any needed mock beans and observe filters/routing active in the context.
5. Use §resultActionsFor(exchangeResult)§ to add a MockMvc handler assertion for an MVC endpoint.
6. Combine WebFlux and MVC snippets on the same Asciidoctor page; configure CI to run both test suites before building documentation.

## 14. Key Takeaways

- WebTestClient is a fluent interface for sending requests and asserting responses; the test server behind the client must match the application's web stack.
- WebFlux uses §WebTestClient.bindToController(...)§ or §bindToApplicationContext(...)§.
- Spring MVC uses §MockMvcWebTestClient.bindToController(...)§ or §bindToApplicationContext(...)§ when you want to write tests with the WebTestClient API.
- The REST Docs WebTestClient filter and descriptors can be shared across both endpoint types.
- §MockMvcWebTestClient.resultActionsFor(...)§ bridges to MockMvc-specific assertions when needed; it does not apply to standard WebFlux clients.
- Choose controller binding for narrow tests, ApplicationContext binding for broader web configuration, and real server binding when verifying HTTP over the network.
- Only build/publish documentation after tests for both stacks succeed in the build/CI.
