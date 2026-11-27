# Handling Proxies, Gateways, and Forwarded Headers with Spring REST Docs

## 1. Why Does the Application-Side URI Differ from What Clients See?

In production, clients typically connect through a CDN, load balancer, API gateway, or reverse proxy:

```text
Client
  |
  | https://api.example.com/public/v1/orders/42
  v
Edge proxy / API gateway
  |
  | http://orders-service:8080/orders/42
  v
Spring application
```

The proxy may terminate TLS, change hostname/port, add a path prefix, or route requests to an internal service. The application may receive an HTTP connection on `orders-service:8080` while the client uses the URI `https://api.example.com/public/v1/orders/42`.

If the application uses the request URL to build links, redirects, or absolute URLs in responses, it needs to know the original connection details observed by the proxy. Proxies typically pass this information via the standard `Forwarded` header (RFC 7239) or the `X-Forwarded-*` group such as `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`, `X-Forwarded-For`, and `X-Forwarded-Prefix`.

Spring REST Docs records HTTP operations from MockMvc, WebTestClient, or REST Assured. When tests and proxy configuration do not align, snippets can expose internal hosts, use the wrong scheme, or miss a public path prefix. This lesson belongs to the **URI configuration** chapter of the **SPRING_REST_DOCS** module, which helps produce verifiable REST API documentation from HTTP tests, generating request/response/payload/header snippets and compiling Asciidoctor/Markdown in build/CI.

After this lesson, you will be able to understand forwarded headers, choose a strategy in Spring Boot, configure Framework filters/transformers, protect applications against spoofing, and test URLs/snippets when running behind a gateway.

## 2. Common Forwarded Headers

### 2.1. Standard Forwarded Header

RFC 7239 defines the `Forwarded` header. A proxy can attach client-facing connection details:

```http
Forwarded: for=203.0.113.10;proto=https;host=api.example.com
```

| Parameter | Meaning |
| --- | --- |
| `for` | Client address observed by the proxy |
| `by` | Proxy address generating the header |
| `proto` | Client-side scheme, typically http or https |
| `host` | Client-side authority, optionally including port |

The header may contain multiple elements if a request passes through multiple proxies. Do not blindly pick the first or last element without verifying which proxy produced each value.

### 2.2. X-Forwarded-* Headers

| Header | Purpose |
| --- | --- |
| `X-Forwarded-For` | Client address or chain of addresses through proxies |
| `X-Forwarded-Host` | Host used by the client |
| `X-Forwarded-Proto` | Client-side scheme |
| `X-Forwarded-Port` | Client-side port |
| `X-Forwarded-Prefix` | Public prefix added to the route by the proxy |
| `X-Forwarded-Ssl` | SSL indicator used by some proxies |

Example:

```http
X-Forwarded-For: 203.0.113.10
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /public/v1
```

Not every proxy sends all of these headers. Verify your actual gateway configuration and web server documentation rather than assuming every field is present.

## 3. Choosing a Forwarded-Header Strategy in Spring Boot

Spring Boot provides the `server.forward-headers-strategy` property:

| Value | Behavior |
| --- | --- |
| `NONE` | Does not actively interpret forwarded headers via Boot's strategy |
| `NATIVE` | Uses the proxy-handling capabilities of the running web server, if supported |
| `FRAMEWORK` | Uses Spring Framework support: `ForwardedHeaderFilter` for Servlet or `ForwardedHeaderTransformer` for Reactive |

Example:

```yaml
server:
  forward-headers-strategy: FRAMEWORK
```

Choose according to your architecture:

- `NATIVE` when the web server is properly configured and supports the headers the proxy sends.
- `FRAMEWORK` when Spring Framework behavior is needed or native support does not suffice.
- `NONE` when the application does not need forwarded headers or interpretation is managed at another layer.

The default strategy may depend on the deployment environment or supported cloud platform. Set an explicit value per deployment profile instead of relying on an unverified default. See [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html).

## 4. Spring Framework Filter and Transformer

### 4.1. Servlet Stack

For Spring MVC/Servlet, `ForwardedHeaderFilter` wraps the request so Servlet APIs see the scheme, host, and port adjusted from forwarded headers. The filter also strips these headers from the wrapped request so they do not continue affecting downstream components.

In Spring Boot, you can select:

```properties
server.forward-headers-strategy=framework
```

If registering the filter manually, place it before filters that need to read the modified request, such as `RequestContextFilter`. For manual registration, consider dispatcher types `REQUEST`, `ASYNC`, and `ERROR` if the application uses async/error dispatching.

### 4.2. Reactive Stack

For WebFlux, Spring Framework uses `ForwardedHeaderTransformer` instead of a Servlet filter. Spring Boot can also configure this via `server.forward-headers-strategy=framework`. Do not register a Servlet filter in a reactive stack; use the mechanism suited to the stack.

### 4.3. Remove-Only Mode

`ForwardedHeaderFilter` supports `removeOnly` mode. When enabled, the filter removes forwarded headers from the request rather than using them to rewrite the request URL. This is useful when the application should not interpret untrusted forwarded values. Avoid unintentionally combining multiple layers that both interpret forwarded headers.

## 5. Trust Boundaries and Forwarded Header Spoofing

Forwarded headers are metadata produced by a trusted proxy. A malicious client can send them directly:

```http
GET /account HTTP/1.1
Host: internal-service:8080
Forwarded: proto=https;host=attacker.example
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
```

If an application trusts these headers when requests have not passed through a trusted proxy, an attacker can influence absolute URLs, redirects, links, or host/scheme-based security decisions.

### 5.1. Edge Proxies Must Strip or Overwrite Incoming Headers

A proxy at the trust boundary must:

1. Strip both `Forwarded` and `X-Forwarded-*` headers sent by the client.
2. Regenerate the headers based on the connection the proxy actually observes.
3. Forward only headers created by trusted proxies to the application.
4. Keep the trusted proxies list as minimal as necessary.

Both header families must be handled. If only `Forwarded` is stripped while `X-Forwarded-Host` is forwarded, or vice versa, the application can still receive forged values. Both Spring Framework and Spring Security emphasize that forwarded headers should only come from controlled proxies. See [Spring Framework — Forwarded headers and security considerations](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html) and [Spring Security — HTTP security considerations](https://docs.spring.io/spring-security/reference/features/exploits/http.html).

### 5.2. Tomcat Native Proxy Handling

With Tomcat, native support can rely on `RemoteIpValve`. Spring Boot allows configuring headers and trusted proxy patterns:

```yaml
server:
  forward-headers-strategy: NATIVE
  tomcat:
    remoteip:
      remote-ip-header: x-forwarded-for
      protocol-header: x-forwarded-proto
      internal-proxies: "10\\.0\\.\\d{1,3}\\.\\d{1,3}"
```

The regex illustrates a sample IP range only; replace it with actual proxy addresses/ranges. Do not configure the application to trust all proxies or leave `internal-proxies` empty in production. Native handling differs by web server. See [Spring Boot — Customize Tomcat proxy configuration](https://docs.spring.io/spring-boot/how-to/webserver.html).

## 6. Gateway Adding a Public Prefix

Example:

```text
Public URL:
https://api.example.com/store/v2/orders/42

Backend URL:
http://orders-service:8080/orders/42
```

Gateway sends:

```http
Forwarded: proto=https;host=api.example.com
X-Forwarded-Prefix: /store/v2
```

The public prefix does not have to match the backend context path. When the Framework processes the prefix, the application can generate links using the external path. Verify which prefix the proxy sends and configure a filter/transformer that actually supports it.

Do not manually add `/store/v2` to both the application context path and the forwarded prefix if doing so causes the prefix to appear twice. Likewise, do not just change host/scheme in Spring REST Docs and assume the path is right; snippets are only accurate when the recorded test path matches the public contract.

## 7. Testing Forwarded Headers with MockMvc

Illustrative controller generating an absolute URI based on the request:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

record LinkResponse(String self) {}

@RestController
class OrderLinkController {
    @GetMapping("/orders/42")
    LinkResponse order() {
        String self = ServletUriComponentsBuilder.fromCurrentRequest()
                .build().toUriString();
        return new LinkResponse(self);
    }
}
```

Merely adding headers in MockMvc does not prove they are processed. Tests must run through the actual `ForwardedHeaderFilter` or proxy handling configuration used by the application. `standaloneSetup` requires explicit filter registration if you want to test the filter.

Example registering the filter in a Servlet test:

```java
import org.springframework.web.filter.ForwardedHeaderFilter;

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderLinkController())
        .addFilters(new ForwardedHeaderFilter())
        .build();
```

Test request:

```java
mockMvc.perform(get("/orders/42")
        .header("Forwarded", "proto=https;host=api.example.com")
        .header("X-Forwarded-Prefix", "/store/v2"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.self")
        .value("https://api.example.com/store/v2/orders/42"));
```

The expected value depends on how the filter is configured to handle `X-Forwarded-Prefix`. If prefix handling is not enabled/supported in the actual configuration, adjust the test to match the real behavior. If choosing the native strategy, test the native container/configuration in an integration test rather than adding a Framework filter alongside it.

## 8. Which URI Does Spring REST Docs Record?

Spring REST Docs records the operation sent by the test client. It does not automatically detect production gateway configuration and does not know the public authority unless the test request carries that information.

### 8.1. Testing Through a Test Gateway

If the pipeline includes a gateway/test ingress equivalent to production:

- Send requests through the gateway's public hostname/path.
- The gateway generates forwarded headers according to deployment rules.
- The application processes forwarded headers just as in production.
- REST Docs generates snippets from real requests passing through the gateway.

This verifies routing, prefixes, and TLS termination end-to-end, though it requires a stable test environment.

### 8.2. Direct Backend Testing and Snippet URI Configuration

If tests call the backend directly, you can use URI defaults or `modifyUris()` to display the public scheme/host/port. However, this approach only modifies the snippet URI. It does not verify whether the gateway exposes that path, whether the proxy produces the right headers, whether links/redirects are accurate, or whether prefixes are dropped or duplicated.

Therefore, direct backend tests fit service/contract testing; add integration tests through the gateway when public routing is an important part of the contract.

## 9. Documenting Requests/Responses and Forwarded Headers

Normally, `Forwarded`, `X-Forwarded-Host`, and `X-Forwarded-Proto` are metadata between the proxy and the application. Do not present them as headers regular API clients must set themselves unless the API genuinely requires them.

Example where Spring REST Docs documents only the operation's public headers:

```java
document("order-detail",
    requestHeaders(
        headerWithName("Accept")
            .description("Response media type accepted by the client")
    ),
    responseFields(
        fieldWithPath("id").description("Order ID"),
        fieldWithPath("self").description("Public URI of the order")
    )
)
```

If you need to test forwarded headers, place them in test setup or integration test fixtures rather than putting them into `requestHeaders(...)` in public documentation. Client documentation should describe what clients must send; forwarded headers are the proxy infrastructure's responsibility.

## 10. WebTestClient and REST Assured

Headers are only processed if requests pass through an application stack with forwarded-header support registered.

### 10.1. WebTestClient

You can add headers to test requests:

```java
webTestClient.get()
        .uri("/orders/42")
        .header("Forwarded", "proto=https;host=api.example.com")
        .header("X-Forwarded-Prefix", "/store/v2")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.self")
        .isEqualTo("https://api.example.com/store/v2/orders/42");
```

The test only verifies forwarded behavior if `WebTestClient` passes through the corresponding WebFlux transformer/filter. An isolated `bindToController` setup may not reflect the full production filter chain; choose an appropriate integration setup when verifying the real pipeline.

### 10.2. REST Assured

REST Assured can also send forwarded headers:

```java
given()
        .header("Forwarded", "proto=https;host=api.example.com")
        .header("X-Forwarded-Prefix", "/store/v2")
        .when()
        .get("/orders/42")
        .then()
        .statusCode(200)
        .body("self", equalTo(
                "https://api.example.com/store/v2/orders/42"));
```

Do not include these headers in public client requests unless required by the contract. In tests, they represent headers sent by a trusted proxy to the backend; integration tests through a real proxy are better when verifying how the proxy strips/overwrites incoming values.

## 11. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Links/redirects use http even though client called HTTPS | Application is not interpreting `X-Forwarded-Proto` or `Forwarded` | Configure `NATIVE`/`FRAMEWORK` appropriately and inspect the proxy |
| Response URL exposes internal service hostname | Forwarded host is missing or not trusted/processed | Check `Forwarded`/`X-Forwarded-Host` at the gateway |
| Public prefix is missing | Gateway does not send the prefix or application does not apply it | Verify `X-Forwarded-Prefix` and stack configuration |
| Public prefix appears twice | Prefix is already in the context path and also added by the proxy | Pick one source for the path and test the external URI |
| Response host is controlled by client-sent headers | Proxy fails to strip/overwrite incoming forwarded headers | Fix the trust boundary; filter both header families |
| MockMvc test receives headers but URL does not change | Test does not register the filter or transformer | Use the proper application context/filter chain |
| Filter builds wrong URLs on async/error dispatch | Filter mapping is missing dispatcher types | Check `REQUEST`, `ASYNC`, `ERROR` mappings |
| Docs record a different URI from production | Only used `modifyUris()` without testing proxy behavior | Add integration tests through the gateway |

## 12. Integrating into Spring REST Docs and CI

A reliable pipeline should include these verification layers:

1. **Unit/integration validation:** test proxy header parsing and URL generation in the Spring stack.
2. **Gateway integration:** verify the proxy strips client-sent headers and regenerates trusted headers.
3. **REST Docs tests:** generate request/response snippets, including URIs or `Location` when part of the contract.
4. **Asciidoctor/Markdown build:** include newly generated snippets and render documentation.
5. **URL scan:** search public documentation for localhost, backend hostnames, internal ports, and wrong prefixes.

Gradle build example once tasks are configured:

```bash
./gradlew test asciidoctor
```

Snippet scan example:

```bash
grep -RniE 'localhost|127\\.0\\.0\\.1|orders-service:8080|http://.*internal' build/generated-snippets
```

Scan results should be reviewed in context; test fixtures or local guides may intentionally contain internal addresses. CI should restrict scans to public documentation artifacts rather than banning every occurrence across the entire repository.

If the application runs behind a proxy, the strategy must be consistent across deployment profiles. Never let the production profile trust arbitrary headers while the gateway fails to filter client-supplied values.

## 13. Practice Exercise

A gateway public route:

```text
https://shop.example.com/api/v2/orders/42
```

Backend route:

```text
http://order-service:8080/orders/42
```

The gateway adds:

```http
Forwarded: proto=https;host=shop.example.com
X-Forwarded-Prefix: /api/v2
```

Complete the following steps:

1. Configure Spring Boot with the appropriate `server.forward-headers-strategy` for your Servlet or Reactive stack.
2. Write an endpoint returning an absolute `self` link based on the current request.
3. Write a test sending forwarded headers and assert that the link has HTTPS, the public host, and the right prefix.
4. Add a spoofing test: client sends fake `Forwarded` and `X-Forwarded-*` headers; verify the edge proxy strips/overwrites those headers before requests reach the backend.
5. Run an integration test through a test gateway to verify actual routing and prefixes.
6. Generate Spring REST Docs snippets and verify URIs/`Location` in the output.
7. Render Asciidoctor and add an internal hostname scan to CI.

**Completion criteria:** The application generates the right public URI under trusted configuration; client-supplied forwarded headers cannot dictate host/scheme; tests cover path prefixes and response links; REST Docs snippets do not mislead integrators into calling the backend host.

## 14. Key Takeaways

Proxies and gateways can alter host, scheme, port, and path before requests reach a Spring application. `Forwarded` and `X-Forwarded-*` convey original connection details so applications can build accurate URLs, redirects, and links. In Spring Boot, choose `NONE`, `NATIVE`, or `FRAMEWORK` depending on your web server/stack; Servlet uses `ForwardedHeaderFilter`, while Reactive uses `ForwardedHeaderTransformer`. Trust only headers controlled by a proxy: edge proxies must strip or overwrite both header families from clients. Use HTTP tests to verify generated URLs and Spring REST Docs to document the contract; simply replacing the host in snippets does not replace testing gateway routing and trust boundaries.

### References

- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Spring Security — HTTP Security Considerations](https://docs.spring.io/spring-security/reference/features/exploits/http.html)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
