# Configuring MockMvc with `documentationConfiguration`

## 1. Purpose and Context

**Spring REST Docs** generates REST API documentation from HTTP tests. It supports testing with MockMvc, WebTestClient, or REST Assured; this lesson focuses on **MockMvc**, where requests are executed through the simulated Spring MVC infrastructure without opening a real HTTP port. When a test passes, Spring REST Docs records the request, response, and declared descriptions as **snippets** for payloads, parameters, headers, and more; these snippets can be included in Asciidoctor or Markdown documentation during the build and CI process.

In this lesson, the bridge between MockMvc and Spring REST Docs is:

```java
MockMvcBuilders.standaloneSetup(controller)
    .apply(documentationConfiguration(restDocumentation))
    .build();
```

`documentationConfiguration(...)` sets up documentation support for MockMvc. Then, `document(...)` is attached to an HTTP execution to decide **which request** is recorded as snippets and **which parts** need to be described.

After completing this lesson, you will be able to:

- Initialize `RestDocumentationContextProvider` for each test using JUnit Jupiter.
- Apply `documentationConfiguration(...)` when building MockMvc with `standaloneSetup` or `webAppContextSetup`.
- Verify the status and payload, then generate snippets from the actual request using `.andDo(document(...))`.
- Identify snippet locations, customize displayed URIs, and avoid common configuration errors.

## 2. Where does `documentationConfiguration` fit in the test flow?

A documentation test has four related components with distinct responsibilities:

| Component | Responsibility |
| --- | --- |
| `RestDocumentationExtension` | Integrates with the JUnit Jupiter lifecycle and provides the documentation generation context for the test. |
| `RestDocumentationContextProvider` | Supplies the context required by Spring REST Docs configuration, including test run information and output location. |
| `documentationConfiguration(restDocumentation)` | Applies Spring REST Docs configuration to `MockMvcBuilder` **before** calling `.build()`. |
| `document("identifier", ...)` | Records a specific HTTP operation into a snippet group named `identifier`, along with optional descriptions. |

The processing flow can be visualized as follows:

```text
JUnit Jupiter + RestDocumentationExtension
             |
             v
RestDocumentationContextProvider
             |
             v
MockMvcBuilder.apply(documentationConfiguration(...))
             |
             v
        MockMvc.perform(...)
             |
             +--> andExpect(...): verify HTTP response
             |
             +--> andDo(document("greetings-get", ...))
                           |
                           v
                 build/generated-snippets/greetings-get/
```

**Key distinction:** `.apply(documentationConfiguration(...))` only prepares the documentation recording mechanism on MockMvc. It does not automatically generate snippets for every request. To generate snippets for a request, `.andDo(document(...))` is typically used after `.perform(...)`.

## 3. Preparing Dependencies and Environment

The examples in this lesson use **Java 17+**, **Spring MVC**, **JUnit Jupiter (JUnit 5)**, and Gradle. If the project uses Spring Boot, testing libraries are usually available via `spring-boot-starter-test`; you need to add the Spring REST Docs MockMvc integration module:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In a Spring Boot project with dependency management, let the Spring Boot BOM manage the compatible Spring REST Docs version. If not using dependency management, declare compatible versions for these dependencies and ensure Spring MVC, JUnit Jupiter, and Jackson (when returning JSON) are present.

The core imports are:

```java
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
```

The last two static imports point to two different methods: one to **configure MockMvc**, and one to **record snippets** for the request.

## 4. Complete Example with `standaloneSetup`

`standaloneSetup(...)` is suitable when you need to test and document a controller independently without loading the entire `WebApplicationContext`. Suppose the `GET /api/greetings/{name}` endpoint returns:

```json
{
  "message": "Hello, An"
}
```

The following test class is self-contained with the sample controller, MockMvc configuration, and documentation generation:

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class GreetingDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new GreetingController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGreeting() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "An")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, An"))
                .andDo(document("greetings-get",
                        pathParameters(
                                parameterWithName("name")
                                        .description("Name of the greeting recipient")),
                        responseFields(
                                fieldWithPath("message")
                                        .description("Greeting message content"))));
    }

    @RestController
    static class GreetingController {

        @GetMapping(value = "/api/greetings/{name}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> greet(@PathVariable("name") String name) {
            return Map.of("message", "Hello, " + name);
        }
    }
}
```

Important points in the example:

1. `@ExtendWith(RestDocumentationExtension.class)` registers the extension for JUnit Jupiter. The `RestDocumentationContextProvider` parameter is injected into `@BeforeEach` by the extension; there is no need to instantiate it with `new`.
2. `.apply(documentationConfiguration(restDocumentation))` appears **before** `.build()`. The MockMvc instance created afterwards will have Spring REST Docs configuration applied.
3. `get("/api/greetings/{name}", "An")` preserves the **URI template**. This allows the `pathParameters(...)` snippet to know that `name` is the path parameter name.
4. `andExpect(...)` verifies the endpoint's behavior; `andDo(document(...))` uses the HTTP result to generate documentation. When the response is wrong, the test fails instead of silently accepting an incorrect API contract.
5. `"greetings-get"` is the identifier for the documentation execution, as well as the directory name containing the snippets. Choose a stable and unique identifier for each documented HTTP operation.

> In a real application, the controller usually resides in `src/main/java` and the test class in `src/test/java`. Nesting the controller inside the test here is only so the example can be read standalone.

## 5. Configuring with `webAppContextSetup` When a Spring MVC Context Is Needed

If an endpoint depends on real MVC configuration—such as message converters, validation, exception handlers, filters, or `@ControllerAdvice`—you can build MockMvc from a `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@SpringBootTest
@ExtendWith(RestDocumentationExtension.class)
class GreetingWebContextDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    // Write @Test methods using mockMvc.perform(...).andDo(document(...)).
}
```

Here, `@SpringBootTest` creates the Spring application context and already supports Spring Test integration with JUnit Jupiter. `RestDocumentationExtension` handles the Spring REST Docs context. Both ways of building MockMvc use the same `documentationConfiguration(restDocumentation)` call.

| Criterion | `standaloneSetup` | `webAppContextSetup` |
| --- | --- | --- |
| Initialization | Pass the controller and required components directly | Use the `WebApplicationContext` created by Spring Test |
| Scope | Tests the controller with minimal configuration | Includes the MVC configuration of the loaded context |
| Speed and complexity | Usually fast, easy to isolate | Has context startup cost and many related configurations |
| When to use | Documenting independent, easily controlled endpoints | Documentation must reflect the application's real mappings, converters, and error handling |

With Spring Security, note that `standaloneSetup` does not automatically apply security filter configurations like the real application; when using `webAppContextSetup`, you need to configure the appropriate filters/security integration so the documented results reflect the behavior under test.

## 6. Customizing the URI Shown in Snippets

MockMvc requests do not pass through a real web server, so the URL displayed in snippets may need to be changed to match the public API address. This can be customized at configuration time:

```java
mockMvc = MockMvcBuilders.standaloneSetup(new GreetingController())
        .apply(documentationConfiguration(restDocumentation)
                .uris()
                    .withScheme("https")
                    .withHost("api.example.com")
                    .withPort(443))
        .build();
```

The configuration above only specifies the URI that Spring REST Docs uses when building snippets for the HTTP operation; MockMvc still executes the request inside the test harness and does not send requests to `api.example.com`.

When you need to adjust how the payload of a specific operation is represented, you can attach an **operation preprocessor** in `document(...)`, for example:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;

// The following is chained after mockMvc.perform(...).andExpect(...)
.andDo(document("greetings-get",
        preprocessRequest(prettyPrint()),
        preprocessResponse(prettyPrint()),
        pathParameters(parameterWithName("name").description("Recipient name")),
        responseFields(fieldWithPath("message").description("Greeting message"))));
```

The snippet above illustrates the continuation of a MockMvc call chain, not a standalone Java statement. `prettyPrint()` makes the JSON in snippets easier to read without changing the actual response verified by `andExpect(...)`.

## 7. Snippet Generation Output and Integration into Documentation

Run the tests via Gradle:

```bash
./gradlew test
```

On Windows, you can use `gradlew.bat test`. With the default configuration when using Gradle, snippets are usually located at `build/generated-snippets`; with Maven, the location is usually `target/generated-snippets`. Running the example once will produce a structure similar to:

```text
build/
└── generated-snippets/
    └── greetings-get/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── request-body.adoc
        ├── response-body.adoc
        ├── path-parameters.adoc
        └── response-fields.adoc
```

This is an illustrative list of commonly generated snippets; the actual set of snippets depends on default configuration, Spring REST Docs version, and the `Snippet` instances passed to `document(...)`. Some configurations also generate `httpie-request.adoc`.

An Asciidoctor document example can reference the output:

```adoc
== Get Greeting

include::{snippets}/greetings-get/http-request.adoc[]
include::{snippets}/greetings-get/path-parameters.adoc[]
include::{snippets}/greetings-get/http-response.adoc[]
include::{snippets}/greetings-get/response-fields.adoc[]
```

The `{snippets}` attribute needs to be configured to point to the snippets directory during the Asciidoctor compilation step. For Markdown, you can embed or transform snippet contents depending on the chosen build configuration. To prevent documentation from using stale snippets, the documentation compilation task in the build/CI pipeline should depend on the test task that generates snippets.

## 8. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Snippet directory not found | Missing `.andDo(document(...))`, test did not run, or test did not reach the documentation step | Check that the test is discovered and executed; verify the output path and `document(...)` for the corresponding request. |
| Error due to missing REST Docs context | `RestDocumentationExtension` not registered or `documentationConfiguration(...)` not applied | Register the extension, accept `RestDocumentationContextProvider`, and call `.apply(...)` before `.build()`. |
| Path parameter documentation fails or misses names | Request did not preserve URI template or descriptor does not match | Use `get("/api/greetings/{name}", value)` and `parameterWithName("name")`. |
| `responseFields(...)` causes test failure | Descriptor missing a field present in JSON, incorrect path, or different data type than expected | Compare against the actual response; document all fields, using `.optional()` or `.ignored()` when appropriate for the API contract. |
| URL in snippets is `http://localhost:8080` | Using default URI values | Configure `.uris().withScheme(...).withHost(...).withPort(...)`. |
| Controller works in application but standalone test fails | `standaloneSetup` lacks converters, validators, advice, or controller dependencies | Register the needed components for standalone setup or switch to `webAppContextSetup`. |
| Documentation shows outdated results | Documentation build does not depend on the snippet-generating test step | Re-run tests before compiling docs; wire task dependencies in Gradle/Maven/CI. |

When a `Snippet` describing a request or response does not match actual data, Spring REST Docs can **fail the test**. This is the key characteristic of verifiable documentation: changing the API requires updating the test and descriptions consistently.

## 9. Practice Checklist

1. Add `spring-restdocs-mockmvc` in the test scope and ensure JUnit Jupiter is enabled.
2. Declare `@ExtendWith(RestDocumentationExtension.class)` and accept `RestDocumentationContextProvider` in `@BeforeEach`.
3. Choose `standaloneSetup` or `webAppContextSetup` based on the scope that needs testing.
4. Attach `.apply(documentationConfiguration(restDocumentation))` to the builder **before** creating MockMvc.
5. Execute the request with `mockMvc.perform(...)`, verify the response with `andExpect(...)`, then call `andDo(document(...))` with appropriate snippet descriptors.
6. Run the tests, inspect the `generated-snippets` directory, and then include the snippets into your documentation and build/CI pipeline.

**Remember:** `documentationConfiguration` connects the **documentation mechanism** to MockMvc; `document` connects **a tested HTTP operation** to the snippets. Together, these two parts produce REST API documentation that reflects the actual behavior of Spring MVC.
