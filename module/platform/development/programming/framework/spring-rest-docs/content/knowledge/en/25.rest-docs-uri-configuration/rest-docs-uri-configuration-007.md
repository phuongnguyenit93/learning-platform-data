# Base Path, Context Path, and Servlet Path

## 1. Learning Objectives

In the **SPRING_REST_DOCS** module, we create verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, assert responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. These snippets are compiled with Asciidoctor/Markdown and integrated into builds and CI.

When an API is deployed behind an API gateway, inside a web application with a context path, or under a specific servlet mapping, the same endpoint can have multiple prefixes. Without distinguishing these parts, MockMvc can build incorrect requests, the application may fail to match the controller, or `http-request.adoc` may display URLs with missing or duplicated paths.

This lesson distinguishes the base path, Servlet context path, servlet path, and path info; then applies these values in MockMvc and verifies the URI recorded by Spring REST Docs.

After this lesson, you will be able to:

- Distinguish the API's public base path from the web application's context path.
- Explain the roles of `contextPath`, `servletPath`, and `pathInfo` according to Servlet requests.
- Determine the complete request URI from path components.
- Configure the MockMvc request builder correctly with context path and servlet mapping.
- Avoid duplicated prefixes when endpoints sit behind a gateway or reverse proxy.
- Verify paths generated in `http-request.adoc` and integrate into CI.

## 2. Overview of Path Layers

Suppose a client calls the public API:

~~~text
https://api.example.com/store/api/orders/42
~~~

The URL may be formed from these parts:

| Part | Example | Role |
| --- | --- | --- |
| Scheme/host | `https://api.example.com` | Public protocol and server. |
| Gateway/base path | `/store` | Prefix published by the gateway or application deployment. |
| Servlet context path | `/store` | Root path of the web application on the Servlet container. |
| Servlet mapping path | `/api` | Prefix used to map requests to DispatcherServlet when the servlet is mapped to `/api/*`. |
| Path info | `/orders/42` | Remainder after the servlet mapping in a specific path-mapping setup. |

In this example, `/store` is used as both the public prefix and the context path to illustrate a gateway forwarding the prefix unchanged. This is not a universal rule: a gateway can rewrite or strip the prefix, while the context path is determined by the web application deployment. Determine where prefixes are added before simulating requests.

~~~mermaid
flowchart LR
    A["Public URL"] --> B["Gateway/base prefix"]
    B --> C["Servlet context path"]
    C --> D["Servlet mapping"]
    D --> E["Path info / endpoint path"]
    E --> F["Spring MVC controller"]
~~~

Do not stack all prefixes out of habit. A proxy may strip `/store` before forwarding requests to the application, while the container might receive context path `/store`. In that case, the request URI seen by the client and the URI seen by the servlet application can differ.

## 3. What Is Base Path?

`Base path` is commonly used in API documentation to refer to the shared prefix preceding endpoints. It can be:

- A public prefix added by an API gateway/reverse proxy.
- An application deployment prefix.
- A fixed path segment used by clients as the root for endpoints.

For example, API documentation describes:

~~~text
https://api.example.com/v1/orders
https://api.example.com/v1/customers
https://api.example.com/v1/products
~~~

Here `/v1` is the shared base path of the API. In Spring MVC, it may be configured in the controller mapping:

~~~java
@RequestMapping("/v1/orders")
@RestController
class OrderController {
    // Endpoint methods
}
~~~

Or `/v1` may be added by the gateway before forwarding to the application. These two setups can produce the same public URL, but the request path received by the controller differs.

Therefore, when testing with MockMvc, use the exact path that the Servlet application actually receives; do not assume you should add the public prefix if the gateway already strips it.

## 4. Servlet Context Path

The context path identifies the prefix under which a web application is deployed on the Servlet container. It starts with `/`; an application deployed at the root context typically has an empty context path.

Examples:

| Deployment Type | Context Path |
| --- | --- |
| Root application | Empty string `""` |
| Application under `/store` | `/store` |
| Application under `/internal` | `/internal` |

In MockMvc, you can set the context path for a request:

~~~java
mockMvc.perform(get("/store/api/orders/42")
        .contextPath("/store"))
    .andExpect(status().isOk());
~~~

The request path must match the configured context path. For request URI `/store/api/orders/42`, the path segment after the context path is `/api/orders/42`.

The context path is neither a host nor a servlet mapping. Do not set `.contextPath("https://api.example.com")`; the hostname belongs to the URI/base URL, while the context path is part of the web application path.

In most MVC tests, you can omit the context path from the request URI and not call `.contextPath(...)`, because controllers usually do not depend on the web application's deployment name. Only set the context path when you need to test the application under that prefix or want snippets to show the exact deployment structure.

## 5. Servlet Path and Path Info

The Servlet API separates the path used to select the servlet from the remaining path in certain mapping styles.

- `servletPath`: the path portion matching the servlet mapping.
- `pathInfo`: the remaining path after the servlet mapping; may be `null` if there is no remainder or the mapping style does not produce path info.

If `.pathInfo(...)` is not called, MockMvc automatically derives path info by stripping the context path and servlet path from the request URI and using the remainder. This is usually the simpler choice; only set path info directly when a test needs to assert a specific value.

Example where DispatcherServlet is mapped to `/api/*` and the application has context path `/store`:

~~~text
Request URI: /store/api/orders/42
Context path: /store
Servlet path: /api
Path info: /orders/42
~~~

These values illustrate a path-mapping example. How the container splits paths depends on the actual servlet mapping; do not manually set `servletPath` and `pathInfo` if the application uses the default DispatcherServlet mapping `/`.

### 5.1. Request Builder Example

MockMvc can configure context path, servlet path, and path info:

~~~java
mockMvc.perform(get("/store/api/orders/42")
        .contextPath("/store")
        .servletPath("/api")
        .pathInfo("/orders/42"))
    .andExpect(status().isOk());
~~~

The request builder must simulate the exact path structure that the Servlet container would produce. If the controller mapping is `/orders/{id}` and DispatcherServlet is mapped to `/api/*`, ensure the test servlet configuration actually matches this mapping. Do not apply the example above to every Spring MVC application.

### 5.2. When DispatcherServlet Is Mapped at Root

In common setups, DispatcherServlet is mapped to `/`. In that case, the servlet path can be the request path after the context path, and path info is unnecessary.

Example:

~~~text
Request URI: /store/orders/42
Context path: /store
Servlet path: /orders/42
Path info: null
~~~

In this case, the MockMvc test is usually simple:

~~~java
mockMvc.perform(get("/store/orders/42")
        .contextPath("/store"))
    .andExpect(status().isOk());
~~~

Specific values must match the project's Servlet mapping and request builder.

## 6. Distinguishing Public Base Path from Internal Context Path

A reverse proxy or API gateway may add, preserve, or strip prefixes before forwarding requests. Therefore, the path clients call is not necessarily the same path the Spring application receives.

Example A — gateway preserves prefix:

~~~text
Client calls:            /store/api/orders/42
Application receives:    /store/api/orders/42
Context path:            /store
Controller path:         /api/orders/42
~~~

Example B — gateway strips prefix:

~~~text
Client calls:            /store/api/orders/42
Gateway forwards:        /api/orders/42
Application receives:    /api/orders/42
Context path:            ""
Controller path:         /api/orders/42
~~~

In case B, do not add `.contextPath("/store")` to MockMvc just because public documentation has the `/store` prefix. Internal MockMvc tests need to simulate the request after the gateway has forwarded it. The public documentation URL can be described separately in the base URL or gateway configuration section.

| Question | Where to Determine |
| --- | --- |
| Which hostname/base path do clients start from? | Public gateway/API documentation. |
| Does the gateway preserve or strip the prefix? | Gateway route/rewrite configuration. |
| Which context path does the Servlet application have? | Deployment/container configuration. |
| Which path is DispatcherServlet mapped to? | Servlet registration/mapping. |
| Which endpoint path does the controller handle? | `@RequestMapping`, `@GetMapping`, and related mappings. |

## 7. Configuring MockMvc Requests with a Context Path

Example where the application is deployed at context `/store`, DispatcherServlet is root-mapped, and the controller handles `/api/orders/{id}`:

~~~java
@Test
void getsOrderUnderStoreContext() throws Exception {
    mockMvc.perform(get("/store/api/orders/{id}", 42)
            .contextPath("/store"))
        .andExpect(status().isOk())
        .andDo(document("orders/get"));
}
~~~

The complete request URI simulated by MockMvc is `/store/api/orders/42`. The documented domain/scheme is configured separately in the Spring REST Docs MockMvc URI configurer:

~~~java
MockMvcBuilders.webAppContextSetup(context)
    .apply(documentationConfiguration(restDocumentation).uris()
        .withScheme("https")
        .withHost("api.example.com")
        .withPort(443))
    .build();
~~~

The snippet may record:

~~~http
GET https://api.example.com/store/api/orders/42 HTTP/1.1
~~~

Here scheme, host, and port come from the URI configurer; `/store` comes from the context path; `/api/orders/42` is the path segment handled by DispatcherServlet/the controller in the example. Port 443 is the default HTTPS port, so Spring REST Docs omits it from the snippet URI.

## 8. Configuring MockMvc for Servlet Mapping /api/*

When DispatcherServlet is mapped to `/api/*`, the Servlet container parses the request path according to that mapping. Example:

~~~text
Request URI: /store/api/orders/42
Context path: /store
Servlet path: /api
Path info: /orders/42
~~~

A MockMvc request can simulate those components:

~~~java
mockMvc.perform(get("/store/api/orders/42")
        .contextPath("/store")
        .servletPath("/api")
        .pathInfo("/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get"));
~~~

This is an example for when a project actually registers DispatcherServlet with `/api/*` and the controller mapping matches the remaining path. The servlet registration in tests must be configured accordingly; merely setting request attributes does not change the `ApplicationContext`'s servlet mapping.

If the actual controller mapping is `/api/orders/{id}` under a root DispatcherServlet mapping `/`, do not configure `servletPath("/api")` and `pathInfo("/orders/42")`. Use the root mapping configuration from the previous section.

## 9. Documenting Public Path vs. Internal Path

A system may have two perspectives:

- **Public URL**: the path integration clients must call through the gateway.
- **Internal servlet request**: the path the application receives after gateway rewriting and context deployment.

REST Docs MockMvc normally records the URI from the mock request. Therefore, if a test simulates an internal request, the default snippet may not contain the public prefix. There are two ways to handle this:

1. Simulate requests with the public prefix if the prefix is actually forwarded intact to the application.
2. Keep tests aligned with internal mappings and describe the public base path in the gateway/API guide; use URI configuration for scheme/host/port as needed.

Do not add a prefix by modifying `contextPath` if the gateway already strips it. Doing so tests a different request from what the application actually receives.

## 10. Complete JUnit 5 and MockMvc Example

The following example assumes root DispatcherServlet mapping, context path `/store`, and controller route `/api/orders/{id}`. The test context contains a controller handling this route.

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
class ContextPathDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = webAppContextSetup(this.context)
            .apply(documentationConfiguration(restDocumentation).uris()
                .withScheme("https")
                .withHost("api.example.com")
                .withPort(443))
            .build();
    }

    @Test
    void documentsOrderWithContextPath() throws Exception {
        this.mockMvc.perform(get("/store/api/orders/{id}", 42)
                .contextPath("/store"))
            .andExpect(status().isOk())
            .andDo(document("orders/get"));
    }
}
~~~

Because both the URI builder and context path contain matching segments, the test accurately simulates the application path. Expected request snippet:

~~~http
GET https://api.example.com/store/api/orders/42 HTTP/1.1
~~~

If the application is deployed at the root context, remove `.contextPath("/store")` and remove `/store` from the request URI. Never let a prefix appear as both the context path and part of the endpoint path unless it genuinely appears twice in real requests.

## 11. Verifying the URI in Snippets

After the test, open:

~~~text
build/generated-snippets/orders/get/http-request.adoc
~~~

Compare against:

| Item | Expected in Example |
| --- | --- |
| Scheme | `https` |
| Host | `api.example.com` |
| Port | Not displayed because 443 is the default HTTPS port |
| Context path | `/store` |
| Endpoint path | `/api/orders/42` |
| Complete URI | `https://api.example.com/store/api/orders/42` |

If `/store` is missing, check whether the request builder has `.contextPath("/store")` and whether the request URI is built properly. If `/store` appears twice, check the prefix in both the endpoint path and the context path. If host/scheme are wrong, check `documentationConfiguration(...).uris()` on the MockMvc instance actually used in the test.

## 12. Common Errors and How to Fix Them

| Symptom | Cause and Resolution |
| --- | --- |
| MockMvc returns 404 after adding context path | The request URI and `.contextPath(...)` are inconsistent, or the controller/servlet mapping does not match. |
| Snippet is missing public prefix | The gateway may add the prefix before reaching the application; decide whether that prefix belongs in internal mock requests. |
| Snippet duplicates `/store/store` | The prefix was placed in both the request path and the context path in a way that does not match the intended request. |
| Controller is not invoked when setting servletPath | The servlet mapping or request builder does not match how DispatcherServlet is registered. |
| `pathInfo` is incorrect | The servlet mapping style does not produce path info as assumed; check the mapping and request URI. |
| Context path used as host | Wrong URI component; hostname is configured via the documented URI configurer, while context path belongs in the request path. |
| Tests pass but documentation has wrong prefix | Tests are simulating internal paths while documentation requires public gateway paths; separate the two perspectives and clearly describe the gateway. |
| Some tests have the prefix while others do not | Build a shared helper/request builder or separate test configurations per deployment style. |

## 13. Integrating Asciidoctor and CI

Asciidoctor can include the generated request snippet:

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

Tests verify routing with the context/servlet path the application actually uses; REST Docs records the corresponding URI; Asciidoctor assembles snippets into documentation. When gateway rewrites or context paths change, update tests and public path guides together.

## 14. Practice Exercises

1. Run a MockMvc test at the root context and open `http-request.adoc`; note the full URI.
2. Add context path `/store`, adjust the request URI, and verify the snippet contains the prefix exactly once.
3. Try removing `.contextPath("/store")` while keeping the request URI, and observe the difference when the request is processed.
4. Simulate servlet mapping `/api/*` using `servletPath("/api")` and `pathInfo("/orders/42")`; confirm the configuration matches the test's servlet registration.
5. Compare the two scenarios: gateway preserving the `/store` prefix versus gateway stripping the prefix before forwarding requests.
6. Separate descriptions of the public URL and internal servlet path in documentation when the two paths differ.
7. Run Gradle/CI and review URI snippets after changing context or servlet mappings.

## 15. Key Takeaways

- Base path is typically the shared API prefix; it can come from a gateway, application deployment, or versioning convention.
- Context path defines the root of a web application in a Servlet container; root context uses an empty string.
- Servlet path is the segment matching the servlet mapping; path info is the remainder in mapping styles that produce path info.
- Use `.contextPath(...)`, `.servletPath(...)`, and `.pathInfo(...)` on the MockMvc request builder to match the actual Servlet structure.
- The public URI through a gateway can differ from the internal URI received by Spring MVC; do not add the public prefix to MockMvc if the gateway strips it.
- Documented URI scheme/host/port are configured separately from context path and servlet mapping.
- Inspect `http-request.adoc` to catch missing/duplicated prefixes, and run tests before Asciidoctor in CI.

## 16. References

- [Spring Framework — MockHttpServletRequestBuilder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/request/MockHttpServletRequestBuilder.html): rules for `contextPath`, `servletPath`, and `pathInfo`.
- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html): configuring scheme, host, and port of URIs recorded in snippets.
