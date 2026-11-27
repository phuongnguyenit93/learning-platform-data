# MockMvc URI Customization

## 1. Learning Objectives

In the **SPRING_REST_DOCS** module, we create verifiable REST API documentation through HTTP tests with MockMvc, WebTestClient, or REST Assured. Tests send requests, assert responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. These snippets are compiled with Asciidoctor/Markdown and integrated into builds and CI.

MockMvc runs requests in a Servlet test environment without opening a real HTTP port. Therefore, the URI written into snippets needs to be configured to reflect the address documentation readers will use. Spring REST Docs provides dedicated URI configuration for MockMvc via `MockMvcRestDocumentationConfigurer.uris()`.

After this lesson, you will be able to:

- Identify the default values of the documented URI when using MockMvc.
- Set scheme, host, and port using `uris().withScheme().withHost().withPort()`.
- Understand how default ports are omitted from snippet URIs.
- Configure a request's context path using `MockHttpServletRequestBuilder.contextPath(...)`.
- Distinguish the documented URI from the application's request URI/context path.
- Apply the configuration to MockMvc standalone setup or `WebApplicationContext` setup and verify snippet output.

## 2. Default MockMvc URI in Spring REST Docs

When using MockMvc, Spring REST Docs configures the default documented URI as follows:

| Component | Default Value |
| --- | --- |
| Scheme | `http` |
| Host | `localhost` |
| Port | `8080` |

Example test:

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andDo(document("orders/get"));
~~~

The request snippet has a URI like:

~~~http
GET http://localhost:8080/api/orders/42 HTTP/1.1
~~~

This address is the URI used in MockMvc documentation. MockMvc does not make a TCP connection to `localhost:8080`; the request is processed in the mock Servlet environment. The scheme/host/port in the snippet help give the request a complete, readable URL.

If documentation needs to describe a sandbox or public API, the default URI may not be appropriate. In that case, change the documented URI configuration before building MockMvc.

## 3. Configuring with MockMvcRestDocumentationConfigurer.uris()

The `documentationConfiguration(restDocumentation)` API returns a MockMvc configurer. Call `uris()` to obtain the documented URI configuration:

~~~java
documentationConfiguration(restDocumentation)
    .uris()
        .withScheme("https")
        .withHost("api.example.com")
        .withPort(443)
~~~

Applying when building MockMvc:

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
    .apply(documentationConfiguration(restDocumentation).uris()
        .withScheme("https")
        .withHost("api.example.com")
        .withPort(443))
    .build();
~~~

The request snippet will then use `https://api.example.com/...`. Because 443 is the default port for HTTPS, Spring REST Docs omits the port from the generated URI.

Methods:

| Method | Purpose |
| --- | --- |
| `withScheme("https")` | Sets the scheme in the documented URI. |
| `withHost("api.example.com")` | Sets the hostname in the documented URI. |
| `withPort(8443)` | Sets the port in the documented URI. |

This is configuration specific to MockMvc. With MockMvc, it is generally better to set the URI directly on `MockMvcRestDocumentationConfigurer` rather than using the `modifyUris()` request preprocessor to replace the URI after recording the operation.

## 4. Choosing Scheme and Host

### 4.1. Scheme

Set the scheme to match the protocol clients use in the documented environment:

~~~java
.uris()
    .withScheme("https")
~~~

If the sandbox/public API requires HTTPS, snippets should use HTTPS even though MockMvc tests do not run real TLS. MockMvc does not open a TLS connection; the scheme only describes the documented address.

Do not set HTTPS just to make URLs look like production. Verify the actual gateway, TLS, and integration environment before choosing a scheme.

### 4.2. Host

Set the public hostname:

~~~java
.uris()
    .withHost("sandbox-api.example.com")
~~~

Some illustrative choices:

| Documentation Set | Host |
| --- | --- |
| Local guide | `localhost` |
| Sandbox guide | `sandbox-api.example.com` |
| Public API guide | `api.example.com` |

Do not use internal CI hostnames or container hostnames in customer-facing documentation. Use a domain name that clients can actually resolve and are permitted to access.

## 5. Setting the Port and Default Port Rules

Use `withPort(...)` when the documented address needs a specific port:

~~~java
documentationConfiguration(restDocumentation).uris()
    .withScheme("https")
    .withHost("sandbox-api.example.com")
    .withPort(8443)
~~~

The documented URI takes the form:

~~~text
https://sandbox-api.example.com:8443/api/orders/42
~~~

If the configured port matches the scheme's default port, Spring REST Docs omits the port from snippets:

| Scheme | Default Port | Recorded URI Format |
| --- | ---: | --- |
| `http` | 80 | Omits `:80` |
| `https` | 443 | Omits `:443` |

Example configuring HTTPS on port 443:

~~~java
.withScheme("https")
.withHost("api.example.com")
.withPort(443)
~~~

The snippet is recorded as:

~~~text
https://api.example.com/api/orders/42
~~~

With HTTP on port 8080, that is not the default port, so the snippet still displays `:8080`. Choose the port based on the address clients are instructed to call, not an arbitrary port used by CI.

## 6. Configuring the Context Path for Requests

The documented URI and the context path are two separate configuration parts:

- `uris().withScheme().withHost().withPort()` determines the scheme, host, and port written into snippets.
- `MockHttpServletRequestBuilder.contextPath(...)` sets the context path of the Servlet request processed by MockMvc.

Example where the application is deployed under context path `/shop`:

~~~java
mockMvc.perform(get("/api/orders/42")
        .contextPath("/shop"))
    .andExpect(status().isOk())
    .andDo(document("orders/get"));
~~~

The context path is included in the request URI processed by MockMvc. It differs from setting the documented host or port. If the application does not use a context path, do not add `.contextPath(...)`.

When configuring a context path, ensure the request URI components are consistent with the Servlet test setup. The context path must start with `/`, must not end with `/`, and the request URI must be constructed to match the context path. If you encounter path errors in `MockHttpServletRequestBuilder`, check the URI, context path, and servlet path before changing the documented URI.

Do not use `withHost(...)` to add a context path, or append `/shop` to the host. Host is only the hostname; the context path belongs to the request path.

## 7. Complete Example with JUnit 5 and WebApplicationContext

The following example configures MockMvc so snippets use HTTPS and the sandbox hostname:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@ExtendWith(RestDocumentationExtension.class)
class MockMvcUriDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = webAppContextSetup(this.context)
            .apply(documentationConfiguration(restDocumentation).uris()
                .withScheme("https")
                .withHost("sandbox-api.example.com")
                .withPort(8443))
            .build();
    }

    @Test
    void documentsOrderUsingSandboxUri() throws Exception {
        this.mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andDo(document("orders/get"));
    }
}
~~~

This example assumes the Spring test context has a `GET /api/orders/42` endpoint returning status 200. The URI in the snippet will look like:

~~~http
GET https://sandbox-api.example.com:8443/api/orders/42 HTTP/1.1
~~~

MockMvc still handles the request in the test environment; the configured scheme, host, and port only adjust the documented URI.

## 8. Standalone Setup Example

If tests use `standaloneSetup(...)`, still apply the configurer to the MockMvc builder:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class StandaloneMockMvcUriTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
            .standaloneSetup(new OrderController())
            .apply(documentationConfiguration(restDocumentation).uris()
                .withScheme("https")
                .withHost("api.example.com")
                .withPort(443))
            .build();
    }

    @Test
    void documentsOrder() throws Exception {
        this.mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andDo(document("orders/get"));
    }
}
~~~

If the controller has dependencies, provide the necessary dependencies or use `WebApplicationContext` setup according to your application configuration.

With port 443 and scheme HTTPS, the snippet will not display `:443`.

## 9. Context Path in Documentation

Suppose the API is deployed under the `/store` prefix. The request builder needs to accurately simulate the path the application receives:

~~~java
mockMvc.perform(get("/api/orders/42")
        .contextPath("/store"))
    .andExpect(status().isOk())
    .andDo(document("orders/get"));
~~~

When a context path is present, the documented request URI will include the application's prefix segment. Illustrative URI example:

~~~text
https://api.example.com/store/api/orders/42
~~~

The scheme/host/port come from the URI configurer; `/store` comes from the MockMvc request's context path. By keeping these two configurations separate, you can document APIs sitting behind a servlet context or gateway prefix.

If the system uses a separate `servletPath` or `pathInfo`, configure the request builder and servlet mapping accordingly. Do not add the prefix to both the context path and the endpoint path unless the application actually routes with that structure, as doing so can produce duplicated paths.

## 10. Default Configuration and Environment Variations

The URI configurer is applied when building MockMvc. As a result, every operation documented through that instance uses the same scheme, host, and port.

Sandbox documentation set:

~~~java
.uris()
    .withScheme("https")
    .withHost("sandbox-api.example.com")
    .withPort(8443)
~~~

Public documentation set:

~~~java
.uris()
    .withScheme("https")
    .withHost("api.example.com")
    .withPort(443)
~~~

If you need two documentation sets, you can create two MockMvc instances or two test configurations with separate URI settings and write snippets to separate output directories. Avoid sharing operation identifiers and output directories when two sets have different addresses; one set may overwrite the other's snippets.

## 11. Distinguishing MockMvc URI Configuration from Request Preprocessors

Spring REST Docs includes `modifyUris()` in the operation preprocessors group. However, the URI reference distinguishes how to configure URIs by client type:

| Test Type | How to Configure Documented URI |
| --- | --- |
| MockMvc | Use `documentationConfiguration(...).uris()` with `withScheme`, `withHost`, `withPort`. |
| WebTestClient without server binding | Set the base URL in the builder configuration using `baseUrl(String)`. |
| WebTestClient bound to a server | A URI preprocessor can be used to replace the URI appearing in documentation when testing a local server. |
| REST Assured | Use the appropriate REST Assured integration/preprocessor because tests perform real HTTP requests. |

With MockMvc, prefer `MockMvcRestDocumentationConfigurer.uris()` to configure the documented URI. Use preprocessors when you need to process operation content for other purposes, such as normalizing headers or bodies. Do not confuse the documented URI with the base URL used to send actual HTTP requests.

## 12. Common Errors and How to Fix Them

| Symptom | Cause and Resolution |
| --- | --- |
| Snippet still records `http://localhost:8080` | The configurer was not applied with `.apply(documentationConfiguration(...).uris()...)` to the MockMvc instance being used. |
| Host changed but port is wrong | Check `withPort(...)`; remember that default ports 80/443 are omitted from snippets. |
| Snippet does not show port 443 | This is normal behavior because 443 is the default port for HTTPS. |
| Context path is missing | Set `.contextPath(...)` on `MockHttpServletRequestBuilder` if the application has a context path. |
| Context path appears twice | Check the request URI and context path; do not repeat the prefix in both places. |
| Request fails before documentation | Check that the context path, servlet path, and URI are constructed consistently in the MockMvc request builder. |
| Some snippets use the old URL | A test is using a different MockMvc instance or URI configuration was not applied to that builder. |
| Sandbox snippet records public hostname | Check the URI configurer of the MockMvc instance and the test class being executed. |

## 13. Integrating Asciidoctor and CI

After MockMvc tests generate snippets, Asciidoctor can include the request and response:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Get Order

include::{snippets}/orders/get/http-request.adoc[]
include::{snippets}/orders/get/http-response.adoc[]
~~~

Assuming the Asciidoctor plugin is configured, connect the documentation task to tests:

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

In CI:

~~~bash
./gradlew clean test asciidoctor
~~~

Snippet URLs stay stable because the MockMvc URI configurer uses the chosen scheme/host/port rather than depending on random network ports. When the public hostname or port changes, update the URI configuration and review snippets alongside the API documentation changes.

## 14. Practice Exercises

1. Run a MockMvc test with the default URI and open `http-request.adoc`; note the scheme, host, and port.
2. Use `.uris().withScheme("https").withHost("sandbox-api.example.com").withPort(8443)` and re-run the test.
3. Change the port to 443 and observe that the default HTTPS port is omitted from the snippet.
4. Set `.contextPath("/store")` on the request builder and verify that the prefix appears in the URI.
5. Create a second MockMvc instance with the public hostname; write snippets to a separate directory.
6. Run Gradle/CI and confirm all snippets use the chosen URI instead of the default address.

## 15. Key Takeaways

- The default MockMvc documented URI is `http://localhost:8080`.
- Use `MockMvcRestDocumentationConfigurer.uris()` to configure snippet URIs with `withScheme(...)`, `withHost(...)`, and `withPort(...)`.
- Default port 80 for HTTP and 443 for HTTPS are omitted from snippet URIs.
- Use `MockHttpServletRequestBuilder.contextPath(...)` to simulate a request's context path; do not use the host configurer to add a path.
- The documented URI only adjusts the address recorded in snippets; MockMvc still processes requests in the test environment.
- Use separate configurations when generating sandbox and public documentation, and separate outputs to avoid overwriting snippets.
- Run tests before Asciidoctor in CI so documentation is generated from verified interactions.

## 16. References

- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html): configuring documented URIs for MockMvc and WebTestClient.
- [MockMvcRestDocumentationConfigurer API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/mockmvc/MockMvcRestDocumentationConfigurer.html): API of the MockMvc configurer, including the `uris()` method.
