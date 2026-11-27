# Diagnosing Errors When the Documentation Filter Is Not Attached in WebTestClient

## 1. Role of the Documentation Filter

**Spring REST Docs** generates REST API documentation from HTTP tests written with **WebTestClient**, MockMvc, or REST Assured. Tests execute an exchange through WebTestClient, assert status/body, and then call `document(...)` to generate snippets for requests, responses, payloads, headers, or parameters.

For REST Docs to recognize and process WebTestClient exchanges, the builder must be configured with the **documentation filter**:

```java
.filter(documentationConfiguration(restDocumentation))
```

Where:

- `documentationConfiguration(restDocumentation)` creates the Spring REST Docs configuration/filter for WebTestClient.
- `filter(...)` registers that configuration in WebTestClient's `ExchangeFilterFunction` chain.
- `document("operation-id")` is called after the exchange, usually inside `consumeWith(...)`, to generate the operation's snippets.

If the filter registration step is missing, calling `document(...)` lacks the integration context provided by REST Docs' WebTestClient configuration. As a result, documentation may fail or fail to produce the expected snippet set, depending on how the test is configured and the library version. Always inspect the exact builder that creates the client used by the test.

This lesson guides you through diagnosing **a missing documentation filter**: identifying where configuration is missing, fixing the right builder, distinguishing it from other causes, and verifying snippets after running tests.

## 2. Proper Setup: Attaching the Filter Before Building WebTestClient

With JUnit 5 and Spring REST Docs, a common configuration uses `RestDocumentationExtension` to supply `RestDocumentationContextProvider`, then registers the filter on the builder.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class UsersDocumentationTest {

    private WebTestClient webTestClient;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.webTestClient = WebTestClient.bindToController(new UsersController())
                .configureClient()
                .filter(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

The key thing to verify is the configuration order:

1. Create a builder from a controller, application context, or server.
2. Call `configureClient()` when client configuration is required.
3. Register `documentationConfiguration(restDocumentation)` with `filter(...)`.
4. Call `build()` to create the client with the filter attached.

You cannot add a filter to a builder after the client has already been built and expect the existing client to pick up the new configuration. If there are multiple ways a WebTestClient is created, verify exactly which instance is injected or invoked in the test.

### 2.1. Configuration When Binding to ApplicationContext

In a Spring test with an application context, the setup is similar:

```java
@Autowired
private ApplicationContext context;

private WebTestClient webTestClient;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
}
```

The difference is the source of the client. Registering the documentation filter still happens on the builder before `build()`.

If you use WebTestClient to connect to a running server, you must also configure the filter on its builder. Do not confuse the REST Docs filter with application security, authentication, logging, or CORS filters. They can coexist in the chain, but they serve different purposes.

## 3. Complete Test Example Generating Snippets

The example below uses a simple controller returning fixed JSON. In a real project, replace the sample controller with your application endpoint and suitable fixtures.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class UserWebTestClientDocumentationTest {

    private WebTestClient webTestClient;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.webTestClient = WebTestClient.bindToController(new SampleController())
                .configureClient()
                .filter(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void getUser() {
        this.webTestClient.get()
                .uri("/users/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.displayName").isEqualTo("Ha Nguyen")
                .consumeWith(document("users-get"));
    }

    @RestController
    static class SampleController {

        @GetMapping(value = "/users/42",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        String getUser() {
            return """
                    {
                      "id": "42",
                      "displayName": "Ha Nguyen"
                    }
                    """;
        }
    }
}
```

In this example:

- `documentationConfiguration(restDocumentation)` is attached to the builder with `filter(...)`.
- `document("users-get")` is invoked after the exchange and assertions succeed.
- REST Docs writes snippets into the `users-get` operation directory under the configured output directory.

With default configuration, common HTTP snippets that may be generated include `curl-request.adoc`, `http-request.adoc`, `http-response.adoc`, `httpie-request.adoc`, `request-body.adoc`, and `response-body.adoc`. Actual snippets depend on the handlers and snippet configuration in use.

## 4. Signs That the Filter May Not Be Registered

Do not diagnose solely from a single error message. Check which step failed and inspect client configuration first.

| Observed Symptom | Possible Connection to Filter | What to Check |
| --- | --- | --- |
| Test calls `consumeWith(document(...))` but REST Docs cannot obtain the operation context | Documentation filter is not attached to the client or context config was not passed properly | Does the builder have `filter(documentationConfiguration(restDocumentation))`? |
| Client is created in another helper and the test lacks REST Docs config | Helper returns a client without the filter configured | Trace the client creation method and confirm the filter is registered before `build()` |
| Some tests generate snippets while others do not | Tests use different WebTestClient instances | Compare builders of the injected client, locally created client, and test helper client |
| Tests pass but the operation directory does not appear as expected | `document(...)` was not called, filter/context was unused, or output directory differs | Check `consumeWith`, test logs, REST Docs config, and output path |
| Default snippets exist, but field tables are missing | Filter is likely working; field handler was not added or branch did not run | Check `document(..., responseFields(...))` or `requestFields(...)` |
| Snippets exist, but expected headers/parameters are missing | Header/parameter documentation handler was not declared or request did not send values | Check descriptors and actual request |

Symptoms only help narrow things down; they do not guarantee a single root cause. Specifically, if a test throws an error inside `document(...)`, verify whether the client has the REST Docs filter and whether the test is using that exact instance.

## 5. Step-by-Step Diagnostic Procedure

### Step 1: Find All Places Creating WebTestClient

Search for calls to:

```java
WebTestClient.bindToController(...)
WebTestClient.bindToApplicationContext(...)
WebTestClient.bindToServer()
WebTestClient.builder()
```

Then determine which builder creates the instance invoked by the test. A project may have one client for regular API tests and another for REST Docs.

### Step 2: Check the Documentation Filter

In the builder chain of the client used for documentation, you must see:

```java
.filter(documentationConfiguration(restDocumentation))
```

Also verify the right class is imported:

```java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;
```

Avoid mistakenly importing the MockMvc configuration or another similarly named filter. For WebTestClient, use the API in `org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation`.

### Step 3: Check the REST Docs Context

When using JUnit 5, the extension must be enabled:

```java
@ExtendWith(RestDocumentationExtension.class)
class ApiDocumentationTest {
    // ...
}
```

And the setup method must receive the context:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    // configure WebTestClient here
}
```

If not using the extension, the project must supply `RestDocumentationContextProvider` through another integration mechanism. Never pass `documentationConfiguration(null)` or reuse another test's context.

### Step 4: Verify the Exact Instance Being Used

Example of a common configuration mistake:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    WebTestClient.Builder builder =
            WebTestClient.bindToController(new SampleController())
                    .configureClient();

    // The client is built before attaching the REST Docs filter.
    this.webTestClient = builder.build();
}

// The filter is added to a different builder, not affecting the client above.
```

The fix is to register the filter before building the client:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.webTestClient = WebTestClient.bindToController(new SampleController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
}
```

A similar mistake happens when a test creates a new client locally instead of using the configured `webTestClient` field.

### Step 5: Confirm `document(...)` Is Called

With WebTestClient, the document consumer is typically placed at the end of the exchange chain:

```java
webTestClient.get()
        .uri("/users/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("users-get"));
```

If the test simply calls `exchange()` and finishes, or an assertion/flow stops before `consumeWith`, documentation will not execute. An attached filter does not automatically generate snippets for every request; `document(...)` must be called.

### Step 6: Verify the Output Directory and Operation Identifier

After the test completes, identify the output directory used by REST Docs and check the exact operation name. For example:

```text
build/generated-snippets/
└── users-get/
    ├── curl-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── httpie-request.adoc
    ├── request-body.adoc
    └── response-body.adoc
```

If the output directory differs, snippets may still be written, just somewhere else than where you are looking. If the operation identifier differs, the directory name will also differ.

## 6. Distinguishing a Missing Filter from Other Configuration Errors

Not every missing-snippet issue is caused by the filter. Use the table below to distinguish causes:

| Cause | Error Location | How to Check |
| --- | --- | --- |
| Missing documentation filter | WebTestClient builder | Is `filter(documentationConfiguration(restDocumentation))` present before `build()`? |
| Missing REST Docs extension/context | JUnit setup | Is the extension/provider properly configured and passed? |
| Document consumer not called | Test method | Is `consumeWith(document("..."))` present after the exchange? |
| Wrong operation identifier | `document(...)` and `include` | Does the output directory name match the identifier? |
| Wrong output directory | REST Docs/build config | Do tests and Asciidoctor use the same snippets directory? |
| Missing field handlers | `document(...)` arguments | Are the required `requestFields`/`responseFields` present? |
| Assertion fails before document | Test chain | Which status/body assertion caused the test to stop? |
| Tests not executed in build | Gradle/Maven/CI | Does the test task include the right class/method? |

A quick diagnostic is to check **whether the test actually reaches and finishes `consumeWith(document(...))`**. If an earlier assertion fails, snippets may not be generated even though the filter is completely configured.

## 7. Spring Boot Auto-Configuration vs. Manual Configuration

In some Spring Boot projects, you can use Spring Boot Test's auto-configuration support with `@AutoConfigureRestDocs` and inject a preconfigured WebTestClient. Annotation usage may differ from manual client creation examples.

When using an auto-configuration mechanism:

- verify the annotation is on the right test class or test slice;
- use the WebTestClient instance injected by Spring;
- check the effective output directory configuration;
- avoid creating extra clients manually without registering the documentation filter.

When configuring manually with `documentationConfiguration(restDocumentation)`, attach the filter explicitly on the builder as shown in Section 2. **Choose one consistent configuration path** and verify the final client instance. Do not blindly add manual configuration if auto-configuration already manages the instance used by the test.

## 8. The Filter and Other Filters in WebTestClient

WebTestClient supports a chain of `ExchangeFilterFunction` instances. The REST Docs documentation filter can coexist with authentication filters, default headers, or logging filters.

Example:

```java
this.webTestClient = WebTestClient.bindToController(new SampleController())
        .configureClient()
        .defaultHeader("X-Test-Client", "docs")
        .filter(documentationConfiguration(restDocumentation))
        .build();
```

Ensure the REST Docs filter is genuinely registered on the builder of the final client. If you have a separate helper configuring filters, avoid creating a new builder after attaching REST Docs without carrying that configuration over.

Filter ordering can affect how filters observe requests and responses; if custom filters mutate bodies or headers, check whether snippets should reflect data before or after transformation. When modifying documentation content, REST Docs also provides operation preprocessors; do not use logging filters as a substitute for documentation preprocessing.

## 9. Including Snippets in Asciidoctor and CI

Once the filter and document consumer work, REST Docs writes snippets to the output directory. Asciidoctor needs to run after tests and read from that exact directory.

Gradle Groovy DSL example, assuming the project already applies the Asciidoctor plugin and configures REST Docs:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Document `src/docs/asciidoc/users.adoc`:

```asciidoc
= User API

== GET /users/{id}

include::{snippets}/users-get/http-response.adoc[]

include::{snippets}/users-get/response-body.adoc[]
```

Run:

```bash
./gradlew clean test asciidoctor
```

In CI, running tests before Asciidoctor ensures documentation uses snippets from the current test run. If an include path is wrong or a snippet has not been generated, the documentation build step should fail so the team re-checks the configuration.

With Maven, the snippet directory is typically `target/generated-snippets`; the documentation plugin configuration must depend on the tests that generate snippets. Never assume the filter alone is enough: operation identifiers, output paths, and includes must also align.

## 10. Quick Troubleshooting Checklist

When you suspect WebTestClient is missing the documentation filter, check each item in order:

- [ ] The correct Spring REST Docs WebTestClient dependency is on the test classpath.
- [ ] The test uses a valid JUnit extension or context provider.
- [ ] The right WebTestClient builder has `filter(documentationConfiguration(restDocumentation))`.
- [ ] The filter is registered before `build()`.
- [ ] The test uses the exact configured client instance.
- [ ] `document("operation-id")` is called after the exchange inside `consumeWith(...)`.
- [ ] Assertions before `document` do not fail.
- [ ] The output directory and operation identifier are correct.
- [ ] Tests run in Gradle/Maven/CI.
- [ ] Asciidoctor reads the same snippets directory just generated.

This checklist helps separate WebTestClient integration errors from document content errors or documentation build errors.

## 11. Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Error occurs when calling `document(...)` | Client lacks the filter or REST Docs context is not attached | Check `documentationConfiguration(restDocumentation)` and extension/provider |
| Filter is present, but snippets do not appear | Test uses a different instance or never reaches `consumeWith` | Trace the actual client and assertion chain |
| Only some tests generate snippets | Tests build clients through different builders | Standardize the WebTestClient creation method for documentation tests |
| Snippets exist, but Asciidoctor reports missing files | Wrong output directory or operation identifier | Check snippet configuration and include paths |
| HTTP snippets exist, but field tables are missing | Field handlers not passed to `document(...)` | Add `requestFields` or `responseFields` |
| Test stops before `document` | Status/body assertion failed | Fix test data or expectations; do not treat this as a filter error |
| REST Docs filter cannot be imported | Mistakenly imported MockMvc API | Use `WebTestClientRestDocumentation.documentationConfiguration` |
| Auto-config and manual client coexist | Test calls an unconfigured manual client | Use the injected client or add the filter to the manual builder |

## 12. Practice Exercise

Create the `UserWebTestClientDocumentationTest` test:

1. Create a WebTestClient using `bindToController` or `bindToApplicationContext`.
2. Intentionally omit `filter(documentationConfiguration(restDocumentation))`, run the test, and record the error or how documentation fails to complete under the current configuration.
3. Add the filter to the right builder before `build()` and re-run.
4. Confirm the test actually reaches `consumeWith(document("users-get"))` and the operation snippet directory appears.
5. Create another test using a new WebTestClient; verify that if the new client lacks the filter, documentation fails even though the first client was configured.
6. Intentionally change the operation identifier in Asciidoctor to verify the build catches the missing include path.
7. Run `./gradlew clean test asciidoctor` in a configured project, then open the HTML to verify the snippets are embedded.

**Completion criteria:** you locate the exact builder creating the client used by the test, recognize that the documentation filter must be registered before `build()`, distinguish filter errors from `document`/output/include errors, and confirm snippets are generated from the tested exchange.

## 13. Self-Check Questions

**1. Where is the WebTestClient documentation filter registered?**

On the WebTestClient builder via `.filter(documentationConfiguration(restDocumentation))`, before calling `build()`.

**2. Does `document("users-get")` attach the filter automatically?**

No. That is the document consumer used after the exchange. The client must be configured with the REST Docs filter to supply the required integration mechanism.

**3. What happens if the filter is present, but `consumeWith(document(...))` is not called?**

REST Docs does not automatically generate snippets for every request. The document consumer must be called on exchanges you want to document.

**4. The filter is attached, yet field tables are missing—what should you check?**

Check whether `responseFields(...)`/`requestFields(...)` handlers were passed into `document(...)` and whether the test reaches the document step.

**5. When using Spring Boot auto-configuration, should you add the filter manually?**

Do not add it blindly. Use the WebTestClient instance prepared by auto-configuration and verify the applied REST Docs configuration. If you create a new client manually, that client needs its own filter configuration.

## References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): WebTestClient exchange and document consumer examples.
- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html): configuring WebTestClient and registering the documentation filter on the builder.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): snippet configuration, preprocessors, and documentation integration.
