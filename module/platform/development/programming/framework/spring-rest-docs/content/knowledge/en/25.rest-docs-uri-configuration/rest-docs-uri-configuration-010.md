# Verifying That Generated URIs Match the Deployment Environment

## 1. URIs in Snippets Must Accurately Reflect Where Clients Call the API

An API may be deployed across multiple environments:

| Environment | Published Base URL |
| --- | --- |
| Local development | `http://localhost:8080` |
| Integration test | `http://api.test.internal:8080` |
| Staging | `https://staging-api.example.com` |
| Production | `https://api.example.com` |

All environments may serve the same operation:

```http
GET /v1/orders/42 HTTP/1.1
Accept: application/json
```

However, the full URI differs. Documentation snippets generated from tests typically reflect the test client's configuration. If staging documentation contains `localhost`, an internal hostname, or a random port, integrators will call the wrong address.

The **SPRING_REST_DOCS** module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests generate request, response, payload, parameter, and header snippets, which are then compiled into Asciidoctor/Markdown and integrated into build/CI. This lesson belongs to the **URI configuration** chapter and focuses on verifying that final URIs in snippets match the deployment environment described by the documentation.

After this lesson, you will be able to distinguish test execution URIs from published URIs, configure scheme/host/port/context path/base URL per test client, choose a clear target environment, verify URLs in requests/cURL/response `Location`, and automatically detect unsuitable hostnames/ports in CI.

## 2. Components of a Deployment URI

Example:

```text
https://staging-api.example.com:8443/platform/v1/orders/42?expand=items
```

| Component | Value | What to Verify |
| --- | --- | --- |
| Scheme | https | Whether clients use HTTP or HTTPS |
| Host | staging-api.example.com | Public DNS or internal hostname |
| Port | 8443 | Published port; can be omitted if default |
| Context/base path | /platform | Prefix exposed by the application or gateway |
| API version | /v1 | Whether version belongs to the contract or is added by the gateway |
| Resource path | /orders/42 | Operation route |
| Query string | expand=items | Parameters and encoding |

A URI is only valid when all components are consistent. Changing the host from `localhost` to `api.example.com` is still insufficient if documentation is missing `/platform/v1` or uses the wrong scheme.

### 2.1. Separating Base URL from Operation Path

Base URL:

```text
https://api.example.com/platform/v1
```

Operation paths:

```text
GET /orders/{orderId}
POST /orders
PATCH /orders/{orderId}
```

This separation makes it easy to switch environments without rewriting every route. Identify which prefix belongs to the base URL and which belongs to the resource path to avoid duplication or omissions.

### 2.2. Context Path and Proxy Prefix Are Two Different Sources

An application may have context path `/platform`, while a gateway adds `/public`. In that case, the client URL may be:

```text
https://api.example.com/public/platform/v1/orders/42
```

If tests already call the route containing the full prefix, do not add the same prefix again when configuring URIs. If tests call the backend directly, verify the public route through the gateway before generating documentation. A URI preprocessor that replaces the authority does not automatically infer or verify the public route.

## 3. Choosing the Target Environment Before Generating Snippets

| Artifact | URI to Use |
| --- | --- |
| Local setup guide | Local URL and service startup instructions |
| Sandbox integration documentation | Sandbox/staging base URL |
| Production release documentation | Published production base URL |
| Internal contract tests | Test URI; do not use as public docs by default |

A project may publish separate documentation builds for sandbox and production. If there is only a single build, pick the official base URL and clearly state the environment in the introduction.

### 3.1. Use Test Properties Instead of Scattering Hostnames

Manage documentation targets via properties:

```yaml
docs:
  api:
    scheme: https
    host: staging-api.example.com
    port: 443
    base-path: /platform/v1
```

This configuration is for the staging documentation set. When building production docs, use a separate reviewed profile/property:

```yaml
docs:
  api:
    scheme: https
    host: api.example.com
    port: 443
    base-path: /platform/v1
```

Avoid pulling hosts and ports from uncontrolled environment variables and publishing artifacts without verification. The pipeline should explicitly record which profile built the documentation.

## 4. Configuring URIs for MockMvc

Under Spring REST Docs' default configuration, URIs documented by MockMvc use:

| Setting | Default |
| --- | --- |
| Scheme | http |
| Host | localhost |
| Port | 8080 |

Change these values through `MockMvcRestDocumentationConfigurer.uris()`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
                .apply(documentationConfiguration(restDocumentation).uris()
                        .withScheme("https")
                        .withHost("staging-api.example.com")
                        .withPort(443))
                .build();
    }
}
```

When the port is the scheme's default — 80 for HTTP or 443 for HTTPS — the port is omitted from URIs in snippets. HTTPS on port 443 typically renders as `https://staging-api.example.com/...`.

### 4.1. Context Path

MockMvc lets you set the context path on the request builder:

```java
mockMvc.perform(get("/orders/{id}", 42)
        .contextPath("/platform")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("order-detail"));
```

Ensure the context path reflects how the application is exposed in the documented environment. Do not put the API version into the context path if that version is already in the route or base URL.

### 4.2. Using Spring Boot AutoConfigureRestDocs

In Spring Boot integration tests, `@AutoConfigureRestDocs` can configure the host, scheme, and port appearing in documented URIs:

```java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(
        uriScheme = "https",
        uriHost = "staging-api.example.com",
        uriPort = 443)
class OrderDocumentationTest {
    // Inject MockMvc and document requests.
}
```

If more control is needed, Spring Boot provides `RestDocsMockMvcConfigurationCustomizer`. Choose one primary configuration mechanism so annotations and customizers do not unintentionally override each other.

## 5. Configuring URIs for WebTestClient

Spring REST Docs uses the default base URI `http://localhost:8080` when documenting WebTestClient. You can customize the base via `baseUrl(String)` on `WebTestClient.Builder`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class ReactiveOrderDocumentationTest {

    private WebTestClient webTestClient;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.webTestClient = WebTestClient.bindToApplicationContext(context)
                .configureClient()
                .baseUrl("https://staging-api.example.com/platform/v1")
                .filter(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

`baseUrl(...)` configures the base used in documented URIs. When bound to a mock server or application context, it does not mean actual requests go through DNS/a public gateway. If you need to verify networking, TLS termination, or gateway routing, add integration tests sending requests through the corresponding environment.

### 5.1. When Tests Use a Random Server Port

With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, a real server listens on a port chosen when the test runs. `WebTestClient` can connect to that server. Distinguish:

- The random port is the test's request destination.
- The base URL in snippets is the documented address.

Do not publish random ports as part of the API contract. For tests running a real server, configure the client so requests still reach the test server, while published documentation carries a stable environment-specific base URL.

## 6. Configuring URIs for REST Assured

REST Assured makes real HTTP requests. `baseURI`, `port`, and `basePath` determine the target address:

```java
RequestSpecification testApi = new RequestSpecBuilder()
        .setBaseUri("http://localhost")
        .setPort(53142)
        .setBasePath("/internal-api")
        .build();
```

If the snippet URI needs to differ from the test URI, apply a REST-Assured-specific preprocessor after the operation executes but before documenting:

```java
given(testApi)
        .filter(document("order-detail",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("staging-api.example.com")
                                .removePort()
                )))
        .when()
        .get("/orders/42")
        .then()
        .statusCode(200);
```

The preprocessor only changes the URI recorded in snippets, not the request destination. If the test calls `/internal-api/orders/42`, the snippet after replacing the authority still has path `/internal-api/orders/42`. Only document that path if it matches the public route.

## 7. Verifying Response URLs and Location

The request line is not the only place containing absolute URIs. An API may return a `Location` header or links in JSON:

```http
HTTP/1.1 201 Created
Location: https://staging-api.example.com/platform/v1/orders/42
Content-Type: application/json

{
  "id": "42",
  "self": "https://staging-api.example.com/platform/v1/orders/42"
}
```

Verify that these URLs share the same scheme, host, and base path as the documented environment. A request snippet with the right host while the response `Location` still contains an internal hostname produces inconsistent documentation.

With REST Assured or other integrations, if response URLs need normalization for snippets, use an appropriate response preprocessor. However, if the production application genuinely generates wrong URLs, do not just patch snippets to hide the bug. Fix proxy/URL generation configuration and test the runtime response.

## 8. Environment-Based URI Verification Matrix

Before publishing documentation, build an expected URI table:

| Component | Local | Staging | Production |
| --- | --- | --- | --- |
| Scheme | http | https | https |
| Host | localhost | staging-api.example.com | api.example.com |
| Port | 8080 | 443 | 443 |
| Base path | / | /platform/v1 | /platform/v1 |
| Operation | /orders/42 | /orders/42 | /orders/42 |

After tests generate snippets, compare actual URLs against the column of the environment being built. Check specifically:

1. `http-request.adoc` — request line and `Host` header.
2. `curl-request.adoc` — URL users will copy.
3. `http-response.adoc` — `Location` or other URI headers.
4. `response-body.adoc` — absolute links in the payload, if any.
5. Asciidoctor/Markdown pages — base URL and environment selection guidance.

## 9. Automating URI Verification in CI

A simple check step can scan output snippets after tests run:

```bash
grep -RniE 'localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0|:8080|internal-api' build/generated-snippets
```

The command above only flags items needing review. Matches may be valid for local tests, so CI for staging/production should match an allowlist/denylist against the environment being built rather than banning strings unconditionally.

Example checks for a staging build:

- The documented host must be `staging-api.example.com`.
- The URI scheme must be `https`.
- Port 443 must not appear explicitly if snippets omit default ports.
- The public base path must include `/platform/v1`.
- No `localhost`, internal service hosts, or random ports.
- `Location` and absolute links in responses must share the same public authority.

If a project maintains multiple documentation sets, store artifacts separately by environment or label them clearly in the pipeline. Never overwrite staging docs with production docs from an undifferentiated build.

### 9.1. Asciidoctor and Markdown

With Asciidoctor, centralize the base URL as an attribute:

```asciidoc
:api-base-url: https://staging-api.example.com/platform/v1

= Order API

Base URL: {api-base-url}

== Get Order

GET {api-base-url}/orders/{orderId}

include::{snippets}/order-detail/http-request.adoc[]
include::{snippets}/order-detail/http-response.adoc[]
```

For production builds, replace the attribute with the approved production value. With Markdown, use Spring REST Docs' Markdown template format and your project's snippet assembly mechanism; apply the same principle of configuring one clear base URL.

## 10. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Staging snippet has localhost | MockMvc/WebTestClient did not override the default URI | Configure `.uris()` or `.baseUrl()` |
| Snippet uses wrong port | Confused test server port with public port | Document the target environment's port |
| Host is right but URL returns 404 | Missing or duplicated context/base path | Verify the route through the gateway |
| HTTP appears in HTTPS docs | Scheme was not configured | Set HTTPS scheme for documented URIs |
| Request is right but Location is wrong | Response builds absolute URLs from internal request | Check proxy handling and URL generation |
| Different developer machines produce different hostnames | URIs derived from unstable local configuration | Use controlled profiles/properties |
| Production docs written with staging URL | Pipeline does not separate artifacts by environment | Separate tasks/profiles/outputs and check URIs before publishing |
| REST Assured test calls wrong server | Changed `baseURI` when only snippet URI should change | Keep the test destination; use a REST Docs preprocessor |

## 11. Practice Exercise

An order management API has three environments:

```text
Local:      http://localhost:8080
Staging:    https://staging-api.example.com/platform/v1
Production: https://api.example.com/platform/v1
```

Operations:

```text
GET /orders/{orderId}
POST /orders
```

Complete the following steps:

1. Create a MockMvc test for `GET /orders/42`, configuring the appropriate scheme/host/port and context path.
2. Create a WebTestClient test and configure `baseUrl(...)` for staging docs.
3. Create a REST Assured test using a local random port while documenting the staging URI with a preprocessor.
4. For `POST /orders`, verify the `Location` header and absolute links in the response body.
5. Generate `http-request`, `curl-request`, `http-response`, and response body snippets.
6. Build an expected URI matrix for staging, and add a CI step verifying host, scheme, port, and base path.
7. Render Asciidoctor/Markdown and check every URL integrators can copy.

**Completion criteria:** Each test sends requests to the right test server; snippets reflect the target environment; scheme/host/port/base path are consistent; response URLs do not leak internal hostnames; CI catches invalid URIs before publishing.

## 12. Key Takeaways

URIs in snippets must match the environment described by the documentation. MockMvc defaults to `http://localhost:8080` and supports `.uris()` to configure scheme/host/port; WebTestClient uses `.baseUrl()`; REST Assured needs a dedicated preprocessor because it sends real requests. Context path, gateway prefix, and resource path must be verified independently. Check the request line, cURL, `Location`, and absolute links in responses; use stable profiles/properties and a URI matrix in CI to prevent local, staging, and production documentation from getting mixed up.

### References

- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html)
- [Spring REST Docs — Configuration and Operation Preprocessors](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [Spring Boot — Auto-configured Spring REST Docs Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
