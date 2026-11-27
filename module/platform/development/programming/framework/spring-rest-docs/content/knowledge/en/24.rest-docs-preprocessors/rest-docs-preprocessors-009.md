# Modifying URIs and Documented URIs

## 1. Why Might the URI in Snippets Differ from the Test URI?

In the **SPRING_REST_DOCS** module, HTTP tests using MockMvc, WebTestClient, or REST Assured both verify API behavior and generate snippets. Locally running tests might use the address:

```text
http://localhost:8080/api/orders/42
```

Whereas the address integrators need to call is:

```text
https://api.example.com/api/orders/42
```

A production application may sit behind a reverse proxy, ingress, or API gateway. Tests do not have to run on the public hostname and TLS port just to generate documentation. Spring REST Docs lets you normalize the URI written into snippets via default URI configuration or an operation preprocessor.

Distinguish between:

- **Actual test URI:** the address the HTTP client uses to execute the exchange.
- **Documented URI:** the URI presented to readers in generated snippets.
- **Path and query:** the resource/query portion belonging to the API contract.
- **`Host` header:** a separate HTTP header, not identical to the URI authority.

Changing the URI for documentation does not change server endpoints, DNS, TLS, gateway routing, or the actual request. Only normalize when you know the correct public base URI and keep paths/queries aligned with the contract.

## 2. Two Ways to Configure the Documented URI

| Approach | API | Scope |
| --- | --- | --- |
| Default URI configuration | `.uris().withScheme(...).withHost(...).withPort(...)` | Multiple operations sharing a public base URI |
| Per-operation preprocessor | `modifyUris()` | One operation needing a separate override |

With MockMvc, default configuration is attached to the configurer when building the client:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(documentationConfiguration(documentation)
                .uris()
                .withScheme("https")
                .withHost("api.example.com")
                .withPort(443))
        .build();
```

Tests can continue calling relative paths like `/api/orders/42`; the documented request URI uses the configured scheme, host, and port.

When only one operation needs a different URI, use `modifyUris()` inside `document(...)`:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.com")
            .removePort()
    )
))
```

Default configuration fits a shared base URI; the preprocessor fits local rules.

## 3. Scheme, Host, and Port

| Component | Local | Public |
| --- | --- | --- |
| Scheme | `http` | `https` |
| Host | `localhost` | `api.example.com` |
| Port | `8080` | `443` or another public port |
| Path | `/api/orders/42` | `/api/orders/42` |
| Query | `?expand=items` | `?expand=items` |

### 3.1. Changing the Scheme

```java
preprocessRequest(
    modifyUris().scheme("https")
)
```

Use HTTPS if that is the protocol public clients must use. Do not switch the scheme just to make snippets look production-like when the target API does not support HTTPS.

### 3.2. Changing the Host

```java
preprocessRequest(
    modifyUris().host("api.example.com")
)
```

Use the official domain or an organization-published example domain. Avoid developer machine hostnames or internal service names like `order-service.default.svc.cluster.local` in consumer documentation.

### 3.3. Setting or Removing the Port

If the public endpoint uses a specific port:

```java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.com")
        .port(8443)
)
```

If you do not want an explicit port displayed:

```java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.com")
        .removePort()
)
```

Do not confuse the application's internal port with the public gateway port. The application may listen on `8080` inside a container while the ingress accepts HTTPS on `443`; the documented URI should reflect the address consumers call.

## 4. Default URI Configuration for MockMvc

JUnit Jupiter example with standalone MockMvc:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class PublicUriDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation)
                        .uris()
                        .withScheme("https")
                        .withHost("api.example.com")
                        .withPort(443))
                .build();
    }

    @Test
    void getOrderDocumentsPublicUri() throws Exception {
        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andDo(document("orders-get"));
    }

    @RestController
    static class OrderController {
        @GetMapping(value = "/api/orders/42",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        OrderResponse getOrder() {
            return new OrderResponse("ORD-42", "CONFIRMED");
        }
    }

    record OrderResponse(String orderId, String status) {}
}
```

The test still performs the request through MockMvc; the public URI is configuration for the documentation configurer. Controller mappings and paths do not change.

With a real application context, you can configure similarly:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(documentationConfiguration(documentation)
                .uris()
                .withScheme("https")
                .withHost("api.example.com")
                .withPort(443))
        .build();
```

Choose standalone or application context based on test purpose. URI configuration does not replace routing, security, or converters needed in integration tests.

## 5. Using modifyUris() Per Operation

Some APIs expose endpoints across multiple hosts, such as uploads via object storage. You can document a different URI for the upload operation:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andDo(document("orders-get",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )));
```

Another operation:

```java
.andDo(document("documents-upload",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("uploads.example.com")
            .removePort()
    )
))
```

Only use a separate host when the public contract genuinely requires it. Do not use an operation preprocessor to mask routing errors or make a public URL look valid while the gateway is misconfigured.

If both default configuration and a per-operation preprocessor apply, inspect the final snippet to confirm the URI is right. Centralize base URI configuration in one place; only override intentional exceptions.

## 6. Keeping Path and Query Faithful to the Contract

When normalizing the base URI, you typically need to keep the resource path and query intact:

```text
Local:
http://localhost:8080/api/orders/42?expand=items

Documented:
https://api.example.com/api/orders/42?expand=items
```

Path and query carry API semantics. Do not delete or rewrite them without a contract change decision.

```java
mockMvc.perform(get("/api/orders/{id}", 42)
                .queryParam("expand", "items"))
        .andExpect(status().isOk())
        .andDo(document("orders-get-expanded",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )));
```

If a public gateway adds a context path such as `/gateway`, determine whether that is part of the base path consumers must call or purely an implementation detail. Only include the prefix in the documented URI when clients truly must use it.

## 7. URI and Host Header Are Two Distinct Pieces of Information

An HTTP request has a URI/authority and a `Host` header (or `:authority` in HTTP/2). They are related but are not the same field:

- URI preprocessing changes the URI shown in the operation.
- Header preprocessing changes headers in the recorded request.
- `modifyUris()` does not replace every header.
- To document the `Host` header, use an appropriate header descriptor or header preprocessor.

Example editing both the URI and header in the documentation record:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.com")
            .removePort(),
        modifyHeaders()
            .set("Host", "api.example.com")
    )
))
```

Only modify `Host` if that header is present in the recorded request and documentation needs to normalize it. With some HTTP clients/protocols, authority is represented under different rules; verify snippets rather than assuming headers behave identically to HTTP/1.1.

## 8. Reverse Proxy, Gateway, and Context Path

An application behind a reverse proxy might receive an internal request:

```text
http://order-service:8080/api/orders/42
```

While public clients call:

```text
https://api.example.com/store/api/orders/42
```

Differences can include scheme, host, port, and path prefix. Determine whether the `/store` prefix belongs to the public base path. If the prefix applies to all endpoints, establish a consistent documentation convention; if only one operation has a special route, handle the exception explicitly.

Proxies often pass original information via `Forwarded` or `X-Forwarded-*`. These headers can affect absolute links or redirects generated by the framework, but they do not automatically configure the documented URI in REST Docs.

Example simulating a proxied request when the application is configured to trust forwarded headers:

```java
mockMvc.perform(get("/api/orders/42")
        .header("X-Forwarded-Proto", "https")
        .header("X-Forwarded-Host", "api.example.com")
        .header("X-Forwarded-Prefix", "/store"))
    .andExpect(status().isOk())
    .andDo(document("orders-get"));
```

This is a test example, not a recommendation to trust forwarded headers sent by arbitrary clients. In production, the proxy/gateway must strip spoofed client headers and set trusted values; the application should only process forwarded headers under a secure configuration.

## 9. WebTestClient and REST Assured

### 9.1. WebTestClient

You can set URI defaults on the documentation configurer when building the client:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider documentation) {
    webTestClient = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(documentation)
                    .uris()
                    .withScheme("https")
                    .withHost("api.example.com")
                    .withPort(443))
            .build();
}
```

Depending on binding type and version, where the filter is configured may vary. Keep the test client target suited for the test environment; the documented URI is never a reason to send real requests to a public production host.

### 9.2. REST Assured

Configure URI defaults in the REST Docs filter:

```java
RequestSpecification spec = new RequestSpecBuilder()
        .addFilter(documentationConfiguration(documentation)
                .uris()
                .withScheme("https")
                .withHost("api.example.com")
                .withPort(443))
        .build();
```

Tests using that specification:

```java
given(spec)
    .filter(document("orders-get"))
    .when()
    .get("/api/orders/42")
    .then()
    .statusCode(200);
```

Imports and overloads depend on integration/version. Use the API matching your project's artifact and verify the generated request snippet after running.

## 10. URIs in Response Headers and Links

Normalizing the request URI does not automatically fix all absolute URIs in responses. Example response header:

```http
Location: http://localhost:8080/api/orders/42
```

Or body:

```json
{
  "self": "http://localhost:8080/api/orders/42"
}
```

If the real API returns public URIs, the application/proxy must construct those URIs accurately from the base URL and forwarded-header configuration. If these are purely fixture/test URIs unsuitable for documentation, use a separate preprocessor for response headers/bodies.

Do not assume `modifyUris()` replaces every URL string in JSON or every `Location` value. It processes the URI of the operation request; headers and bodies are separate content.

## 11. Asciidoctor and Build/CI

Generated snippets using the documented URI can be included as usual:

```adoc
= Order API
:snippets: build/generated-snippets

== Retrieve Order

=== HTTP request
include::{snippets}/orders-get/http-request.adoc[]

=== HTTP response
include::{snippets}/orders-get/http-response.adoc[]
```

The build must run documentation tests before Asciidoctor. During code review, inspect the public domain, scheme, port, path/query, gateway prefix, `Host` header, and `Location`/link URLs in responses. Ensure tests do not accidentally call a production host just to generate snippets.

If local, staging, and production use different hostnames, public documentation should use the designated base URI for the target audience; never let developer machine or CI hostnames leak into artifacts.

## 12. Common Errors

| Symptom | Cause | Solution |
| --- | --- | --- |
| Snippet shows `localhost` | Documented URI not configured | Use `.uris()` or `modifyUris()` |
| Scheme is still `http` | Only changed host | Configure scheme matching public endpoint |
| Internal port appears | Used test server port as public port | Set public port or `removePort()` |
| Missing gateway prefix | Confused deployment prefix with public base path | Determine whether prefix belongs to contract |
| `Host` header unchanged | Only used URI processor | Use header processor if needed |
| `Location` still has `localhost` | Confused operation URI with response header | Process response header or configure application |
| Link in JSON still has local URL | `modifyUris()` does not rewrite body strings | Use an intentional body processor or fix fixture |
| Each operation uses a different host | Scattered URI overrides | Centralize defaults and only override exceptions |
| Test accidentally calls production host | Confused documented URI with HTTP client target | Keep test target local; rewrite documentation record |
| CI and local show different URIs | Relied on runtime host/port | Configure a fixed URI for documentation |

## 13. Practice Exercise

Use the `GET /api/orders/42` operation:

1. Run a MockMvc test without URI configuration; observe `localhost` and port in `http-request.adoc`.
2. Configure default URIs with `.uris().withScheme("https").withHost("api.example.com").withPort(443)`.
3. Re-run and confirm scheme/host/port changed while the path remains accurate.
4. Use `modifyUris()` specifically for an upload operation with host `uploads.example.com`.
5. Try `removePort()` when documentation should not display an explicit port.
6. Add query `expand=items`; confirm the query remains in the documented URI.
7. Simulate gateway prefix `/store`; decide whether it belongs to the public path or an internal route.
8. Create a `Location` response containing `localhost`; identify why the request URI preprocessor does not automatically fix this header.
9. Include snippets in Asciidoctor and verify no unintended local domains remain.
10. Ensure tests still send requests to the test target, not calling a production host merely because the documented URI uses a public domain.

**Completion criteria:** you distinguish the actual test URI from the documented URI; configure base URIs with `.uris()`; use `modifyUris()` for individual operations; understand scheme/host/port/path/query and the `Host` header; handle reverse proxies/context paths; and verify generated snippets/Asciidoctor accurately reflect the public API.

## References

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessing.html): normalizing URIs in recorded operation requests.
- [Spring REST Docs — MockMvc API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html): configuring documentation with MockMvc.
- [Spring REST Docs — UriModifyingOperationPreprocessor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/UriModifyingOperationPreprocessor.html): methods to edit scheme, host, port, and URI.
- [Spring Framework — HTTP Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): handling forwarded information from proxies/gateways.
