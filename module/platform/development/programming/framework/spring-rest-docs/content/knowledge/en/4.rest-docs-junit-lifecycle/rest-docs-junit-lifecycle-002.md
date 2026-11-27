# SpringExtension and Combining with Spring Testing

## 1. The Problem: REST API Documentation from Tests Running in Spring

Spring REST Docs helps generate verifiable REST API documentation: HTTP tests send requests, assert response results, and then generate snippets for requests, responses, payloads, path/query parameters, and headers. The snippets are included in Asciidoctor or a Markdown workflow and can be compiled into documentation during build/CI.

When an endpoint depends on Spring-managed controllers, services, MVC configuration, validation, serializers, or security mechanisms, a test that only instantiates the controller via `new` may not accurately reflect application behavior. **`SpringExtension`** enables JUnit 5 to initialize and use the **Spring TestContext Framework**, allowing tests to obtain beans from a real Spring context and use tools like `MockMvc`. **`RestDocumentationExtension`** provides the dedicated context for Spring REST Docs.

In the **JUnit and Lifecycle** chapter of the **SPRING_REST_DOCS** module, the goal of this lesson is to understand **how the two extensions collaborate**, choose the appropriate configuration approach, and organize tests capable of producing reliable documentation.

After this lesson, you will be able to:

- Distinguish the responsibilities of `SpringExtension` and `RestDocumentationExtension` in JUnit Jupiter.
- Know when `SpringExtension` must be declared explicitly and when Spring Boot annotations already declare it.
- Use `@Autowired WebApplicationContext` to build a `MockMvc` configured with REST Docs.
- Write an MVC test that generates snippets from an endpoint inside a Spring context.
- Avoid duplicate configuration, test client conflicts, and mistakes that prevent snippets from being generated.

## 2. What is SpringExtension?

`SpringExtension` belongs to the **Spring TestContext Framework**, located in the package:

~~~java
org.springframework.test.context.junit.jupiter.SpringExtension
~~~

It integrates Spring TestContext into **JUnit Jupiter** through the extension mechanism. Typical capabilities supported by Spring TestContext include:

- **Creating or retrieving the appropriate `ApplicationContext`** based on test configuration, along with context caching to reduce startup time.
- **Injecting dependencies into the test instance**, such as `@Autowired` for `WebApplicationContext`, services, or beans in the context.
- **Executing Spring `TestExecutionListener`s** for test preparation, before/after method hooks, and cleanup.
- **Supporting Spring Test features**, such as test profile configuration, transactional tests, handling dirtied contexts, and test slices.
- **Connecting to JUnit Jupiter's parameter resolution** for Spring-supported cases, such as certain parameters annotated with `@Autowired`.

Manual registration looks like this:

~~~java
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.junit.jupiter.SpringExtension;

@ExtendWith(SpringExtension.class)
class SpringContextTest {
    // ...
}
~~~

However, in Spring Boot applications, annotations such as `@SpringBootTest` or `@WebMvcTest` already include `SpringExtension` in their meta-configuration. **There is no need to register it again** just to use `@Autowired` in tests already configured with those annotations.

### Distinguishing the Two Extensions

| Aspect | `SpringExtension` | `RestDocumentationExtension` |
| --- | --- | --- |
| Belongs to library | Spring TestContext | Spring REST Docs |
| Primary purpose | Initialize, inject dependencies, and manage the Spring test context | Manage the REST Docs documentation context across the test lifecycle |
| Common inputs | `@ContextConfiguration`, `@SpringBootTest`, `@WebMvcTest`, `@Autowired` | `@ExtendWith(RestDocumentationExtension.class)`, `RestDocumentationContextProvider` |
| Resources provided | `ApplicationContext`, beans, configuration, and test infrastructure | `RestDocumentationContextProvider` used to configure REST Docs |
| Automatically sends HTTP requests? | No | No |
| Automatically generates snippets just by registering? | No | No |

**Key point:** `SpringExtension` does not replace `RestDocumentationExtension`, and neither replaces the HTTP test client. Requests are executed by `MockMvc`, `WebTestClient`, or `REST Assured`; snippets are generated when you configure REST Docs on the client and perform the `document(...)` operation (or use a configured auto-documentation mechanism).

## 3. Combined Lifecycle in JUnit 5

Suppose a test needs both a Spring context and REST Docs. After the extensions are registered, the conceptual execution flow is:

~~~mermaid
sequenceDiagram
    participant JUnit as JUnit Jupiter
    participant Spring as SpringExtension
    participant Context as Spring TestContext
    participant Docs as RestDocumentationExtension
    participant Setup as @BeforeEach
    participant MVC as MockMvc

    JUnit->>Spring: Prepare test instance
    Spring->>Context: Load or retrieve Spring context from cache
    Context-->>Spring: Beans and WebApplicationContext
    Spring-->>JUnit: Inject dependencies into test
    JUnit->>Docs: Start REST Docs context for the test
    JUnit->>Setup: Call setUp(RestDocumentationContextProvider)
    Setup->>MVC: webAppContextSetup(context)
    Setup->>MVC: apply(documentationConfiguration(provider))
    JUnit->>MVC: perform(request) + assertions
    JUnit->>MVC: document("identifier", ...)
    MVC-->>JUnit: REST Docs snippets
    JUnit->>Spring: Post-test callbacks
    JUnit->>Docs: Complete documentation lifecycle
~~~

This is a **responsibility diagram**, not a guarantee of absolute ordering between every callback of the two extensions. JUnit Jupiter has its own callback registration and execution rules; the extensions are designed to provide their services at the required phases. What truly matters to the test author is: **before `@BeforeEach`**, Spring has already prepared the necessary dependencies and REST Docs can supply the provider for the current test.

Three concepts to keep distinct:

1. **Spring `ApplicationContext`:** can be **cached and reused** across tests with compatible configurations. This is a Spring TestContext mechanism; it does not mean mutable bean state is always cleaned up automatically.
2. **Test instance/JUnit lifecycle:** by default, JUnit Jupiter typically creates a new instance per test method (unless configured otherwise). `@BeforeEach` runs before each test execution.
3. **REST Docs context and identifiers:** `RestDocumentationContextProvider` is tied to the documentation context of the test run; the name in `document("...")` determines the snippet output area. Distinct identifiers should be chosen for different scenarios.

When running tests in parallel, do not let independent scenarios write to the same identifier. When tests mutate context state, a database, or singletons, you must have an appropriate data isolation strategy; the two extensions themselves do not guarantee business-state isolation.

## 4. Configuring a Plain Spring MVC Test Using Both Extensions

To clearly see the role of each component, the example below **does not use Spring Boot auto-configuration**. Spring TestContext loads a `WebApplicationContext` containing the controller, `MockMvc` uses that context, and REST Docs generates snippets once the request is verified.

For a project using compatible versions of **JUnit Jupiter**, **Spring MVC/Spring Test**, and `spring-restdocs-mockmvc`, place the following class in `src/test/java`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith({SpringExtension.class, RestDocumentationExtension.class})
@WebAppConfiguration
@ContextConfiguration(classes = GreetingDocumentationTest.WebConfig.class)
class GreetingDocumentationTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsGreeting() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "Lan")
                        .accept(MediaType.TEXT_PLAIN))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Lan"))
                .andDo(document("greetings-get",
                        pathParameters(
                                parameterWithName("name")
                                        .description("Name of the person being greeted")
                        )
                ));
    }

    @Configuration
    @EnableWebMvc
    static class WebConfig {
        @Bean
        GreetingController greetingController() {
            return new GreetingController();
        }
    }

    @RestController
    static class GreetingController {
        @GetMapping(value = "/api/greetings/{name}",
                    produces = MediaType.TEXT_PLAIN_VALUE)
        public String greeting(@PathVariable String name) {
            return "Hello, " + name;
        }
    }
}
~~~

### Why Does This Example Work?

1. `@ExtendWith({SpringExtension.class, RestDocumentationExtension.class})` registers both Spring Test infrastructure and REST Docs with JUnit Jupiter.
2. `@ContextConfiguration` declares the test bean configuration; `@WebAppConfiguration` instructs Spring to create a web context suitable for Spring MVC Test.
3. `@EnableWebMvc` creates the MVC infrastructure, while `@Bean` registers the example controller. `SpringExtension` allows Spring to inject `WebApplicationContext` into the `@Autowired` field.
4. `RestDocumentationExtension` allows JUnit to supply the `RestDocumentationContextProvider` parameter to `@BeforeEach`.
5. `MockMvcBuilders.webAppContextSetup(webApplicationContext)` builds a `MockMvc` using the mappings and MVC configuration from the Spring context. `.apply(documentationConfiguration(restDocumentation))` attaches REST Docs to the client.
6. `get("/api/greetings/{name}", "Lan")` is imported from **`RestDocumentationRequestBuilders`**: it preserves the URL template metadata so `pathParameters(...)` documents the `name` variable properly.
7. `.andExpect(...)` verifies status/body. `.andDo(document("greetings-get", ...))` triggers snippet generation for the HTTP operation and path parameter.

In this lesson, the response is a simple plain-text string to keep the focus on lifecycle. If the endpoint returns JSON, you can add `responseFields(...)`, `fieldWithPath(...)`, and corresponding JSON assertions. For requests with a body, query parameters, headers, or cookies, use the appropriate snippet descriptors with `document(...)`.

### What Happens If Each Piece of Configuration Is Omitted?

- Missing `SpringExtension` in a plain Spring test: Spring TestContext may not be initialized; `@Autowired` fields will not be injected as expected.
- Missing `RestDocumentationExtension` in the manual setup above: JUnit has no suitable resolver for the test's `RestDocumentationContextProvider` parameter.
- Missing `@WebAppConfiguration` or `@ContextConfiguration`: the test context may not be suitable for `webAppContextSetup(...)` or may not contain the controller.
- Missing `documentationConfiguration(restDocumentation)`: MockMvc is not configured with the REST Docs context.
- Missing `document(...)`: the request may still succeed, but the test does not instruct REST Docs to generate documentation snippets.

## 5. Combining with Spring Boot: @WebMvcTest and @AutoConfigureRestDocs

In Spring Boot applications, there is usually a more concise way to generate REST API documentation at the web layer. `@WebMvcTest` initializes a **Spring MVC slice** for the controller and related web components. `@AutoConfigureRestDocs` connects REST Docs with Boot's supported testing setup.

Skeleton example (assuming `GreetingController` is located in application code and exposes `GET /api/greetings/{name}`):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
@AutoConfigureRestDocs
class GreetingBootDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsGreeting() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "Lan"))
                .andExpect(status().isOk())
                .andDo(document("greetings-get-boot",
                        pathParameters(
                                parameterWithName("name")
                                        .description("Name of the person being greeted")
                        )
                ));
    }
}
~~~

This snippet illustrates the **Spring Boot integration style**, assuming the controller already exists and the project uses a Boot version providing those annotations.

Differences from the manual example:

| Criterion | Plain Spring MVC (Section 4) | Spring Boot Auto-Configuration (Section 5) |
| --- | --- | --- |
| Preparing the Spring context | `@ExtendWith(SpringExtension.class)` + `@ContextConfiguration` + `@WebAppConfiguration` | `@WebMvcTest` already integrates Spring TestContext |
| Preparing MockMvc | Call `MockMvcBuilders.webAppContextSetup(...)` | Boot provides `MockMvc` via `@Autowired` |
| Configuring REST Docs | `RestDocumentationExtension` + `documentationConfiguration(provider)` | `@AutoConfigureRestDocs` |
| Test scope | Context explicitly declared by the test | Web slice selected by Boot |
| Need to configure non-web dependencies? | Declare required beans manually | Provide controller dependencies if not included in the slice |

**Note on controller dependencies:** `@WebMvcTest` typically does not load all application services, repositories, and configurations. If the controller depends on a service, you must provide an appropriate bean in the test (for example, a mock bean using the mechanism available in your Spring version). Newer Spring Framework projects have `@MockitoBean`; some older Spring Boot versions use `@MockBean`. Do not assume both annotations exist in every version.

### When to Use @SpringBootTest?

If the documentation needs to test a fuller integration flow, you can use:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class FullApplicationDocumentationTest {
    @Autowired
    MockMvc mockMvc;

    // @Test methods execute requests and call document(...).
}
~~~

`@SpringBootTest` provides a broader application context; `@AutoConfigureMockMvc` creates MockMvc for the test application; `@AutoConfigureRestDocs` configures REST Docs. In exchange, startup overhead and test dependencies are usually greater than with `@WebMvcTest`.

Whichever style you choose, **use the client that actually has REST Docs configured**. If you `@Autowired MockMvc` provided by Boot and then manually create another MockMvc without applying REST Docs, calling `document(...)` on the new client may not work as expected.

## 6. Choosing the Extension Registration and Configuration Mechanism

There are three common practical setups:

| Context | Recommended Configuration |
| --- | --- |
| JUnit 5 + plain Spring Test + manually built MockMvc | `@ExtendWith({SpringExtension.class, RestDocumentationExtension.class})`, `@ContextConfiguration`, `@WebAppConfiguration`, and `documentationConfiguration(provider)` |
| Spring Boot for controller testing | `@WebMvcTest` + `@AutoConfigureRestDocs` + `@Autowired MockMvc` |
| Spring Boot for multi-layer application testing | `@SpringBootTest` + `@AutoConfigureMockMvc` + `@AutoConfigureRestDocs` |

Things to check during code review:

- **`@ExtendWith(SpringExtension.class)` may already be present via meta-annotations** such as `@WebMvcTest` or `@SpringBootTest`. Duplicating this annotation rarely fixes configuration errors; check how the test is actually being initialized.
- **Pick one clear REST Docs configuration path** per MockMvc. Mixing manual and auto-configuration arbitrarily in the same test makes it hard to trace where settings come from.
- **Do not reuse `RestDocumentationContextProvider` in a `static` field** or retain a provider from a previous test to configure a subsequent test.
- **Use distinct identifiers** for responses with different contracts, such as `greetings-get-success` and `greetings-get-not-found`, especially when tests run in parallel.
- **Only document what has been verified.** Assertions for status/body and snippet descriptors should reflect the exact same contract.

## 7. From Spring Tests to Snippets and Documentation Pages

When the test case in Section 4 passes, `document("greetings-get", ...)` instructs REST Docs to generate the default request/response snippets and an additional snippet for the path parameter.

Output typically appears in:

- Gradle: `build/generated-snippets/greetings-get/`.
- Maven: `target/generated-snippets/greetings-get/`.

The directory name may vary based on configuration. Examples of files to inspect:

| Snippet | Description |
| --- | --- |
| `http-request.adoc` | The HTTP request sent to the controller |
| `http-response.adoc` | The HTTP response after the controller processes it |
| `curl-request.adoc` | Equivalent curl command for reference |
| `path-parameters.adoc` | Table describing the `name` parameter |

An Asciidoctor page can reference the output as follows:

~~~asciidoc
= Greeting API

== Greet by Name

=== Request
include::{snippets}/greetings-get/http-request.adoc[]

=== Path parameters
include::{snippets}/greetings-get/path-parameters.adoc[]

=== Response
include::{snippets}/greetings-get/http-response.adoc[]
~~~

`{snippets}` is an Asciidoctor attribute configured to point to the snippets directory. Neither `SpringExtension` nor `RestDocumentationExtension` **compiles the final documentation**. The build/CI pipeline typically runs:

~~~text
JUnit 5 + Spring TestContext
        |
        v
MockMvc / WebTestClient / REST Assured
        |
        v
HTTP Assertions + Spring REST Docs
        |
        v
generated-snippets/{identifier}/
        |
        v
Asciidoctor or Markdown pipeline
        |
        v
Packaged/published REST API documentation
~~~

With Gradle/Maven, the compilation step must receive the correct snippet directory and properly depend on the test task. If you are compiling Markdown, you need rules to handle a compatible snippet format; the default snippets are typically in Asciidoctor format.

## 8. Common Errors When Integrating SpringExtension with REST Docs

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `@Autowired WebApplicationContext` is `null` in a plain Spring test | Missing `SpringExtension`, missing `@WebAppConfiguration`, or misconfigured Spring TestContext | Check annotations and MVC configuration classes |
| Failed to load `ApplicationContext` | Bean missing dependencies, broken configuration, or test slice missing a required bean | Inspect the root cause during context initialization; provide the required bean/mock |
| JUnit reports it cannot resolve `RestDocumentationContextProvider` | Missing `RestDocumentationExtension` in manual setup | Register the REST Docs extension in the JUnit Jupiter test |
| REST Docs does not generate snippets | Client does not have REST Docs configured, missing `document(...)`, or wrong MockMvc instance | Verify that the client executing the request is the configured one |
| `@WebMvcTest` test cannot find a service | The slice does not load application services/repositories | Mock or add the exact dependencies needed for the web test |
| Path parameter documentation test fails | Using a request builder that does not preserve the URL template | Use `RestDocumentationRequestBuilders.get` and the template `/api/greetings/{name}` |
| Test runs fine, but built documentation is missing snippets | Compilation task ran before tests or points to the wrong directory | Check task dependencies, `{snippets}`, and the output directory |
| Two tests produce unstable snippets | Using the same identifier across scenarios or concurrent writes | Choose distinct identifiers and define a parallel execution strategy |
| Test results depend on execution order | Mutable beans, shared data, or a reused context with leftover state | Isolate data; reset state at the proper scope; use `@DirtiesContext` selectively when needed |

**Layered diagnosis** is more effective: verify JUnit Jupiter ran properly → Spring context loaded and injected → MockMvc sent the right request → assertions passed → REST Docs wrote snippets → compilation task found the snippets. This helps avoid mistaking a Spring application issue for a REST Docs issue.

## 9. Practice: Experimenting with Configuration Layer by Layer

Use `GreetingDocumentationTest` from Section 4 as a starting point:

1. **Run the working test:** verify the `200 OK` response, body `Hello, Lan`, and confirm `greetings-get/path-parameters.adoc` is created.
2. **Observe SpringExtension:** temporarily remove `SpringExtension.class` from `@ExtendWith` and re-run. Note the difference in Spring context preparation/injection; then restore the annotation.
3. **Observe the REST Docs extension:** temporarily remove `RestDocumentationExtension.class` from `@ExtendWith` while keeping `@BeforeEach` accepting `RestDocumentationContextProvider`. Observe the parameter resolution error; restore the annotation.
4. **Observe client configuration:** keep both extensions, but temporarily remove `.apply(documentationConfiguration(restDocumentation))`. Observe what happens when `document(...)` runs on an unconfigured MockMvc; then restore it.
5. **Add an error test:** update the controller to support a `404` scenario and document it with a distinct identifier. Be sure to add assertions for the body/status matching the real response.
6. **Try Spring Boot:** in a suitable Boot project, replace manual setup with `@WebMvcTest` + `@AutoConfigureRestDocs`, and compare the amount of configuration and loaded beans.
7. **Build the documentation:** use Asciidoctor to include `http-request.adoc`, `path-parameters.adoc`, and `http-response.adoc`, and attach that step after tests in the build.

**Self-check criteria:** you can clearly identify **which extension provides the Spring context**, **which extension provides the REST Docs provider**, **which client executes the HTTP request**, **which call generates snippets**, and **which task compiles the documentation**.

## 10. Summary

- `SpringExtension` connects JUnit Jupiter with the Spring TestContext Framework: context, dependency injection, and Spring testing utilities.
- `RestDocumentationExtension` manages the REST Docs documentation context for the JUnit 5 test lifecycle; it does not manage Spring beans.
- In plain Spring MVC tests, you can register **both extensions**, build MockMvc with `WebApplicationContext`, and apply `documentationConfiguration(provider)`.
- In Spring Boot, `@WebMvcTest`/`@SpringBootTest` already integrate Spring TestContext; `@AutoConfigureRestDocs` provides a concise way to configure REST Docs for the corresponding client.
- REST API documentation quality depends on the same verification chain: **proper Spring test → asserted request/response → generated snippets → Asciidoctor/Markdown built in build and CI**.
