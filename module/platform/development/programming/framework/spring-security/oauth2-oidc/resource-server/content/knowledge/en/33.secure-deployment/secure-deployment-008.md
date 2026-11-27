# Limiting Token Size, Header Size, and Input Processing Costs

An **OAuth 2.0 Resource Server** receives an access token from a client request and verifies the token before granting `Authentication`. A token can be a JWT or an opaque string; in either case, input size and header count affect the API's availability. An oversized access token can exceed reverse-proxy or HTTP-connector limits, causing the request to be rejected before reaching Spring Security. If the request is accepted, large tokens and complex claims also increase the cost of reading headers, parsing, decoding, signature verification, introspection calls, and authority creation.

Therefore, input limits must be enforced across multiple layers:

- **Gateway/reverse proxy/load balancer:** limit request header sizes before forwarding to the application.
- **HTTP server connector:** enforce independent limits at Tomcat, Jetty, Undertow, or Reactor Netty.
- **Bearer token resolver:** separately limit the `Authorization` header value and token length before invoking the decoder/introspector.
- **Token/claim policy:** keep access tokens compact, limit the number of scopes/groups/claims, and bound authority creation cost.
- **Operational testing:** prove that in-bounds requests succeed, over-limit requests are rejected, and no path bypasses verification.

There is no single maximum number that fits every system. Sizes must be chosen from actual tokens issued by your issuer, infrastructure limits, and the Resource Server's processing budget. What matters is that limits are finite, consistent across hops, and tested.

## 1. Sizes to Distinguish

In an HTTP request, there are several distinct types of limits:

| Input | Example | Typically Enforced By |
|---|---|---|
| Single header field | `Authorization: Bearer ...` | Proxy and HTTP connector |
| Total request headers | `Authorization`, `Cookie`, tracing, custom headers | Proxy, load balancer, connector |
| Bearer token | The token portion after the `Bearer` prefix | Bearer token resolver |
| Request line / request target | Method, path, query string | HTTP server/proxy |
| Request body | JSON payload, form body | Dedicated body-size limit |
| Claims in JWT | `groups`, `scope`, `permissions`, nested JSON | Issuer policy, decoder/validator, converter |
| Introspection response | Attributes and authorities returned by the AS | HTTP client/response handling and introspector |

These limits do not replace one another. Body limits do not bound the `Authorization` header. A connector's total header limit does not necessarily set a separate cap for tokens. Token limits in the resolver only run after the HTTP server has read and accepted the request headers.

### 1.1. Header Size and Token Size Are Not the Same

Example:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6ImF0K2p3dCJ9...
Accept: application/json
X-Request-Id: 7f21a
~~~

The `Authorization` header contains the `Bearer` scheme, space, and token. The header field also includes the `Authorization` name, separator, and protocol framing. Token limits should apply to the credential string after the resolver strips the `Bearer` scheme; the HTTP server's header limit covers a header field or all request headers as defined by the connector.

JWT compact serialization is typically ASCII Base64URL. For valid tokens under the Bearer grammar, character count closely approximates byte count. However, total headers may include `Cookie`, tracing, and other headers, so never set the total header limit equal to the token limit.

### 1.2. Header Limits Can Block Requests Before Spring Security

Processing flow:

~~~text
Client
  |
  v
Gateway / Reverse proxy
  |  request-header limits
  v
HTTP server connector
  |  request-header limits
  v
Servlet container / Reactive server
  |
  v
Spring Security filters
  |
  v
Bearer token resolver
  |  token-specific limit
  v
JwtDecoder / OpaqueTokenIntrospector
  |
  v
Authorization + Controller
~~~

If the gateway or connector rejects oversized headers, the request never reaches the Bearer token resolver. Therefore, you cannot rely solely on `MockMvc` to prove the connector returns an error when headers exceed the threshold. Test with a real HTTP server or test separately at the proxy/gateway layer.

## 2. Why Large Tokens and Headers Consume Resources

### 2.1. Cost of Receiving and Storing Headers

The HTTP server must read bytes from the socket, decode headers per protocol rules, validate structure, and store values for application access. Oversized headers can:

- Increase per-request memory usage.
- Hold connections and buffers longer.
- Increase string copying/parsing overhead.
- Cause many concurrent requests to consume much more memory.
- Enable request flooding or resource exhaustion.

HTTP/2 uses HPACK compression, which does not eliminate logical header size limits after decompression. Servers and proxies still need limits on decoded header list/field sizes to prevent a small wire header from expanding into large in-memory data.

### 2.2. Cost of Processing JWTs

Upon receiving a JWT, a Resource Server typically performs:

1. Splitting compact serialization into parts.
2. Base64URL-decoding the header and payload.
3. Parsing JOSE header and claims JSON.
4. Looking up the signing key by `kid` in a trusted key set.
5. Verifying the signature with an allowed algorithm.
6. Validating issuer, audience, timestamps, and token profile.
7. Mapping scopes/roles/groups to authorities.
8. Creating `Authentication` and passing the request into authorization.

Parsing and authority creation scale with the amount of data/claims processed. Signature verification has its own cryptographic cost; if the key is not cached, fetching JWKS also adds network latency. Never allow unbounded token sizes simply because the decoder can handle a normal token.

### 2.3. Cost of Processing Opaque Tokens

Opaque tokens are not necessarily shorter than JWTs. The Resource Server still has to read the token string and typically call an introspection endpoint. Long tokens enlarge request headers; large introspection responses with many attributes/groups also increase transfer, JSON parsing, and authority creation costs.

### 2.4. Bloated Claims

Common causes:

- Putting an entire organization's group list into the access token.
- Repeating profile, address, contact details, or metadata unnecessary for the API.
- Embedding permissions for thousands of resources.
- Deeply nested JSON objects or redundant claims.
- Issuing many granular scopes instead of an appropriate permission model.
- Sending data the Resource Server could look up by subject/resource.

An access token should carry the minimum information needed for the Resource Server to authenticate and make authorization decisions. Large profile data or rapidly changing permissions can be looked up from internal services per policy; there is no need to stuff everything into every request.

## 3. Choosing Appropriate Limits

Neither OAuth 2.0 nor JWT defines a universal token/header size limit. Limits depend on infrastructure and the issuer. Measure real tokens, add controlled headroom, and set caps.

Illustrative example:

| Limit | Illustrative Value |
|---|---:|
| Total request headers | 16 KiB |
| `Authorization` header value | 8 KiB |
| Bearer token after scheme | 6 KiB |
| Number of mapped group/permission claims | 100 |
| Scope string length | 2 KiB |

These numbers are **not default recommendations**. A system with large cookies or tracing headers needs a different header budget allocation. An issuer with a compact token profile can set lower caps; a system with large group claims should revise its token design rather than raising limits indefinitely.

### 3.1. Measuring Real Tokens

Collect size percentiles from test/staging environments or credential-scrubbed telemetry:

- Minimum, median, p95, p99, and observed maximum token sizes.
- `Authorization` header sizes.
- Total request header sizes.
- Counts of scopes/roles/groups.
- Counts and sizes of custom claims.
- Number of requests with tokens exceeding expected thresholds.

Record **sizes** only, never the tokens themselves. Never put raw access tokens into logs, tracing spans, metric labels, or error reports.

### 3.2. Leaving Budget for Other Headers

For example, if the total header limit is 16 KiB, do not let `Authorization` consume the full 16 KiB. Cookies, `traceparent`, correlation IDs, `Accept`, `Content-Type`, proxy metadata, and application headers also need space. One large header might be valid individually while the total header list still exceeds the limit.

### 3.3. Aligning Limits Across Layers

A consistent configuration might look like:

~~~text
Gateway total-header cap        = 16 KiB
HTTP connector total-header cap = 16 KiB
Application Authorization cap  = 8 KiB
Application Bearer-token cap    = 6 KiB
~~~

This is only an illustrative diagram. If the gateway allows larger headers than the connector, requests may be rejected at the backend with a different status. If the backend allows larger headers than the gateway, direct backend access paths may have weaker limits. Expose the backend only through trusted proxies and set backend limits as an independent defense layer.

## 4. Limiting Request Headers in Spring Boot

In newer Spring Boot versions, general configuration typically uses:

~~~yaml
server:
  max-http-request-header-size: 16KB
~~~

This property sets the request-header size limit for the embedded server as supported by Spring Boot/the connector. Older versions may use a different property name, such as `server.max-http-header-size`; check the metadata and reference documentation for your exact Spring Boot version before applying.

### 4.1. Connector Limits Are Not Dedicated Token Limits

`server.max-http-request-header-size` controls request headers at the server layer. It does not replace a dedicated Bearer token limit and does not bound the number of authorities after a JWT is verified.

The connector may reject requests before Spring MVC/WebFlux receives them. Depending on the server and version, the response may be HTTP 400 or 431. Do not write tests assuming every connector returns the exact same status unless the implementation documentation guarantees it.

### 4.2. Tomcat, Jetty, Undertow, and Reactor Netty

Spring Boot supports multiple embedded servers. The common property maps to the corresponding server configuration, yet:

- How header size is measured (single field vs. entire request) can differ.
- Some connectors have additional separate limits.
- Container versions can change defaults and threshold-exceeded behavior.
- An upstream proxy may reject the request before the connector processes it.

When fine-grained tuning is needed, use `WebServerFactoryCustomizer` or a server-specific customizer for your exact connector/version. Do not copy Tomcat properties to Netty/Jetty without verifying support.

### 4.3. Limits at Reverse Proxies and Ingress

Setting limits at the edge rejects oversized requests before they consume application resources. Check all of the following together:

- Public load balancer.
- API gateway.
- Ingress controller/service mesh.
- Internal reverse proxy.
- Embedded HTTP server.

A request traversing multiple hops can be bounded at each stop. Log which layer rejected the request for diagnostics. Never raise limits across every layer just to accommodate a bloated token; first identify which claims are inflating the token.
## 5. Dedicated Bearer Token Limits in Servlet

Connector limits protect the HTTP parser. To set a smaller cap on the `Authorization` header/token, wrap the default `BearerTokenResolver` and validate before returning the token to the authentication filter.

### 5.1. Size-Limited Resolver

~~~java
import java.util.Enumeration;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

final class LimitedBearerTokenResolver implements BearerTokenResolver {

    private final BearerTokenResolver delegate =
        new DefaultBearerTokenResolver();

    private final int maxHeaderValueChars;
    private final int maxTokenChars;

    LimitedBearerTokenResolver(
            int maxHeaderValueChars,
            int maxTokenChars) {
        this.maxHeaderValueChars = maxHeaderValueChars;
        this.maxTokenChars = maxTokenChars;
    }

    @Override
    public String resolve(HttpServletRequest request) {
        Enumeration<String> values =
            request.getHeaders(HttpHeaders.AUTHORIZATION);

        if (values != null && values.hasMoreElements()) {
            String headerValue = values.nextElement();

            if (values.hasMoreElements()) {
                throw invalidRequest("Multiple Authorization headers");
            }

            if (!isAscii(headerValue)
                    || headerValue.length() > this.maxHeaderValueChars) {
                throw invalidRequest("Authorization header is too large");
            }
        }

        String token = this.delegate.resolve(request);
        if (token != null && token.length() > this.maxTokenChars) {
            throw invalidToken("Bearer token is too large");
        }
        return token;
    }

    private static boolean isAscii(String value) {
        for (int i = 0; i < value.length(); i++) {
            if (value.charAt(i) > 0x7f) {
                return false;
            }
        }
        return true;
    }

    private static OAuth2AuthenticationException invalidRequest(
            String description) {
        return new OAuth2AuthenticationException(
            new OAuth2Error(
                OAuth2ErrorCodes.INVALID_REQUEST, description, null));
    }

    private static OAuth2AuthenticationException invalidToken(
            String description) {
        return new OAuth2AuthenticationException(
            new OAuth2Error(
                OAuth2ErrorCodes.INVALID_TOKEN, description, null));
    }
}
~~~

The resolver above illustrates these steps:

1. Read the `Authorization` header before invoking the default resolver.
2. Reject multiple `Authorization` headers instead of arbitrarily picking one value.
3. Reject header values that are too long or contain non-ASCII characters.
4. Let `DefaultBearerTokenResolver` validate the `Bearer` scheme/format.
5. Reject tokens exceeding the dedicated cap before the decoder/introspector runs.

Constructor caps must come from configuration, not scattered hard-coded values. `String.length()` is suitable for checking ASCII Bearer tokens after verifying ASCII; byte limits at the proxy/connector remain the authoritative boundary for wire size.

### 5.2. Registering the Resolver in `SecurityFilterChain`

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    LimitedBearerTokenResolver resolver =
        new LimitedBearerTokenResolver(
            8 * 1024,
            6 * 1024);

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .bearerTokenResolver(resolver)
            .jwt(Customizer.withDefaults()))
        .build();
}
~~~

The numbers here are examples. Real endpoint/resource server configurations must continue enforcing required authorities; `authenticated()` only illustrates where to attach the resolver. The resolver does not verify signatures, issuers, audiences, or expiry; it only bounds and extracts the credential before the decoder runs.

### 5.3. Why Check Before the Decoder?

If you wait until `JwtDecoder` to check size, the token has already passed through header reading, string allocation, and potentially the start of parsing. Bounding at the resolver rejects oversized tokens before decode/crypto/JWKS costs. Connector limits remain essential because the resolver only runs after request headers are accepted by the HTTP server.

## 6. Limiting Bearer Tokens in WebFlux

With WebFlux, use `ServerAuthenticationConverter` to wrap the default converter. The idea is the same as Servlet: check the raw `Authorization` header first, then delegate to create the Bearer authentication token.

~~~java
import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.server.authentication.ServerBearerTokenAuthenticationConverter;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

final class LimitedServerBearerTokenConverter
        implements ServerAuthenticationConverter {

    private final ServerAuthenticationConverter delegate =
        new ServerBearerTokenAuthenticationConverter();

    private final int maxHeaderValueChars;
    private final int maxTokenChars;

    LimitedServerBearerTokenConverter(
            int maxHeaderValueChars,
            int maxTokenChars) {
        this.maxHeaderValueChars = maxHeaderValueChars;
        this.maxTokenChars = maxTokenChars;
    }

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        List<String> values =
            exchange.getRequest().getHeaders().get(HttpHeaders.AUTHORIZATION);

        if (values != null && values.size() > 1) {
            return Mono.error(invalidRequest("Multiple Authorization headers"));
        }

        if (values != null && !values.isEmpty()) {
            String headerValue = values.get(0);
            if (!isAscii(headerValue)
                    || headerValue.length() > this.maxHeaderValueChars) {
                return Mono.error(
                    invalidRequest("Authorization header is too large"));
            }
        }

        return this.delegate.convert(exchange)
            .flatMap(authentication -> {
                if (authentication instanceof BearerTokenAuthenticationToken bearer
                        && bearer.getToken().length() > this.maxTokenChars) {
                    return Mono.error(
                        invalidToken("Bearer token is too large"));
                }
                return Mono.just(authentication);
            });
    }

    private static boolean isAscii(String value) {
        for (int i = 0; i < value.length(); i++) {
            if (value.charAt(i) > 0x7f) {
                return false;
            }
        }
        return true;
    }

    private static OAuth2AuthenticationException invalidRequest(
            String description) {
        return new OAuth2AuthenticationException(
            new OAuth2Error(
                OAuth2ErrorCodes.INVALID_REQUEST, description, null));
    }

    private static OAuth2AuthenticationException invalidToken(
            String description) {
        return new OAuth2AuthenticationException(
            new OAuth2Error(
                OAuth2ErrorCodes.INVALID_TOKEN, description, null));
    }
}
~~~

Attach the converter to the reactive Resource Server DSL according to your project's Spring Security version:

~~~java
ServerAuthenticationConverter converter =
    new LimitedServerBearerTokenConverter(8 * 1024, 6 * 1024);

http.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenConverter(converter)
    .jwt(Customizer.withDefaults()));
~~~

Package/API names for the converter and DSL may change across versions. Check the corresponding Javadoc before using. Even if an application does not need a token-specific cap in the resolver, request-header limits at the connector and proxy are still required. Never introduce blocking parsing or `block()` inside a reactive converter.

## 7. Limiting Claims and Authority Creation Cost

Bounding token bytes caps how much data the decoder must parse, yet a small token can still hold many claim entries or nested structures. After decoding, the Resource Server should have a clear policy for claims converted into authorities.

### 7.1. Avoid Stuffing Groups/Permissions into Access Tokens

A `groups` claim with thousands of entries can inflate:

- Token size.
- JSON parsing time.
- Number of Java objects allocated.
- Number of `GrantedAuthority` instances.
- Cost of authorization checks and logging/debugging.

If an API only needs 2–3 scopes, do not emit the user's entire group list. Issue per-resource scopes, use condensed permission claims, or look up membership/permissions via an internal service with its own caching and policies.

### 7.2. Validator Bounding Claims Before Creating `Authentication`

A custom `OAuth2TokenValidator` can limit the number of entries in claims the application intends to map:

~~~java
private static final int MAX_GROUPS = 100;
private static final int MAX_SCOPE_CHARS = 2 * 1024;

OAuth2TokenValidator<Jwt> claimBudgetValidator = jwt -> {
    Object groupsClaim = jwt.getClaims().get("groups");
    if (groupsClaim instanceof Collection<?> groups
            && groups.size() > MAX_GROUPS) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Too many group values",
                null));
    }

    Object scopeClaim = jwt.getClaims().get("scope");
    if (scopeClaim instanceof String scope
            && scope.length() > MAX_SCOPE_CHARS) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Scope claim is too large",
                null));
    }

    return OAuth2TokenValidatorResult.success();
};
~~~

This validator runs after the JWT has been parsed and signature-verified by the decoder. It bounds claims by policy before `Authentication` is granted; it does not replace the token-size cap at the Bearer resolver. For claims with complex structures, define a schema and explicitly bound counts, depth, or length actually used by the application.

### 7.3. Do Not Create Authorities from Arbitrary Claims

Only map claims defined by the issuer contract and needed by the Resource Server. Never automatically turn every string/boolean in a JWT into a role. For example, `admin=true` only carries authorization meaning if the issuer contract, audience, and mapping policy explicitly define it. A large token with thousands of values must not produce thousands of authorities.

### 7.4. Opaque Tokens Also Need Response Budgets

For opaque tokens, the token resolver can bound the string before introspection. Yet the AS response must also be controlled: number of attributes, claim sizes, scope/group counts, and body size. If using a custom introspector, never generate unbounded authorities from the response. Configure HTTP client/response handling per your implementation's capabilities; never assume request-header limits automatically bound response bodies.

## 8. Do Not Raise Limits to Mask Token Design Flaws

When a token exceeds thresholds, investigate the root cause first:

1. Which claim consumes the most bytes?
2. Are groups/permissions duplicated?
3. Does the API truly need that claim on every request?
4. Can smaller scope/resource-specific access tokens be issued?
5. Can a reference/identifier be used with internal service lookups?
6. Is a client sending unnecessary cookies or extra headers?
7. Is a proxy duplicating or concatenating multiple `Authorization` headers?

Never work around this by raising header limits across all environments without measuring. A bloated token may indicate that the authorization model or issuer mapping needs adjustment.

## 9. Accept Bearer Tokens Only via the Header

Spring Security's `DefaultBearerTokenResolver` reads Bearer tokens from the `Authorization` header by default. Do not enable query parameter or form body tokens unless there is a special compatibility requirement and risks have been assessed.

Discouraged:

~~~http
GET /api/orders?access_token=eyJ...
~~~

Tokens in URLs easily appear in:

- Browser history.
- Reverse proxy/access logs.
- Analytics and tracing.
- `Referer` headers.
- Cache keys or monitoring systems.

Enabling multiple token transport methods lets a request carry multiple conflicting credentials and creates ambiguity. Keep one clear token transport method; reject requests with multiple `Authorization` headers or multiple token sources.
## 10. HTTP Statuses When Inputs Exceed Limits

The status code depends on which layer detects the violation:

| Rejecting Layer | Typical Status | Meaning |
|---|---:|---|
Gateway/HTTP server header limit | 431 or 400 | Request header field/list too large; some connectors return 400 |
Request target too long | 414 | URI too long, distinct from `Authorization` header |
Request body too large | 413 | Content too large, not headers |
Malformed/invalid Bearer token | 401 | Credential cannot be authenticated |
Valid token but missing authority | 403 | Authentication succeeded, authorization denied |
Custom application policy rejecting over-cap token | Per error contract, usually 400 or 401 | Resolver received request, yet token fails policy |

HTTP 431 is defined for Request Header Fields Too Large. Do not require every connector to return 431; some implementations return 400. Clients should not retry the exact same request with the same oversized headers. Raising limits only makes sense if tokens genuinely need that size and all proxies/servers allow it.

## 11. Testing Token Limits in Servlet

### 11.1. Unit Testing the Resolver at Boundaries

With a token cap of `MAX_TOKEN_CHARS`, test:

| Token Length | Result |
|---|---|
`MAX_TOKEN_CHARS - 1` | Resolver can return token |
`MAX_TOKEN_CHARS` | Resolver accepts if format is valid |
`MAX_TOKEN_CHARS + 1` | Resolver rejects before decoder |
Non-ASCII | Resolver rejects |
Two `Authorization` headers | Resolver rejects |
No `Authorization` | Resolver returns null |
Header not using Bearer scheme | Does not produce Bearer token |

Resolver unit tests do not prove HTTP connector limits. They only verify the token-specific guard.

### 11.2. Verifying the Decoder Is Not Called

In tests for the resolver cap, use a spy/mock decoder:

~~~java
@Test
void oversizedBearerTokenIsRejectedBeforeJwtDecoder() throws Exception {
    String oversized = "a".repeat(MAX_TOKEN_CHARS + 1);

    mockMvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + oversized))
        .andExpect(status().isUnauthorized());

    verify(jwtDecoder, never()).decode(anyString());
}
~~~

The exact status depends on how `OAuth2AuthenticationException` is mapped by the configured entry point. The key assertion is that the resolver rejects it and the decoder is never invoked. `MockMvc` is appropriate for this test because the target is the guard in the Security filter; it does not test connector limits.

### 11.3. Testing Duplicate `Authorization` Headers

~~~java
@Test
void rejectsMultipleAuthorizationHeaders() throws Exception {
    mockMvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer first-token",
                "Bearer second-token"))
        .andExpect(status().is4xxClientError());

    verify(jwtDecoder, never()).decode(anyString());
}
~~~

HTTP clients, proxies, or servlet containers may normalize/merge duplicate headers differently. Resolver tests should directly verify the request abstraction's behavior; add a test through a real connector/proxy to verify wire behavior.

## 12. Testing Header Limits on a Real HTTP Server

`MockMvc` does not open sockets through the embedded server connector. To test the connector:

1. Run the application with `@SpringBootTest(webEnvironment = RANDOM_PORT)`.
2. Send real HTTP requests with `Authorization` headers just below, equal to, and above the limit.
3. Observe the status returned by the active connector.
4. Confirm over-limit requests never reach the controller.
5. Repeat through the gateway/ingress in a test deployment if the gateway has its own limits.

Example test using `TestRestTemplate` in Spring Boot Servlet:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RequestHeaderLimitIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void connectorRejectsOversizedAuthorizationHeader() {
        String token = "a".repeat(20 * 1024);
        HttpHeaders headers = new HttpHeaders();
        headers.set(
            HttpHeaders.AUTHORIZATION,
            "Bearer " + token);

        ResponseEntity<String> response =
            new TestRestTemplate().exchange(
                "http://localhost:" + port + "/api/orders",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class);

        assertThat(response.getStatusCode().is4xxClientError()).isTrue();
    }
}
~~~

The size in the example must exceed the test configuration's connector cap. The status may be 400 or 431 depending on the embedded server. Ensure the test is not accidentally rejected by a custom resolver before exercising the connector; to test the connector, set the `Authorization` value above the total header limit and observe the server response. To test the token-specific cap, keep headers below the connector limit while exceeding only the token cap.

For WebFlux, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client connecting to the real port; `WebTestClient.bindToApplicationContext(...)` does not test socket/connector limits the same way. For proxies/ingress, test in a deployment environment with a real proxy.

## 13. Testing Processing Costs and Claim Limits

Beyond size, verify element counts and execution path:

- Small token, few claims: verified normally.
- Token near cap: verified within latency budget.
- Token over cap: resolver rejects; decoder/introspector does not run.
- Token within cap but excessive `groups`: validator rejects before authorities are created.
- Valid token with insufficient scope: 403.
- Malformed token: 401, with no payload parsing fallback.

Do not make a fixed latency benchmark a pass/fail unit test across arbitrary CI machines. Use functional assertions to prove expensive steps do not execute when inputs exceed caps; use dedicated load/performance tests to measure p95/p99, CPU, allocations, and throughput per infrastructure configuration.

### 13.1. Confirming Execution Order

~~~text
oversized Authorization
  -> resolver rejects
  -> decoder calls = 0
  -> controller calls = 0

valid-size Bearer token
  -> resolver returns token
  -> decoder called
  -> validation result decides Authentication

valid token with excessive group claim
  -> decoder verifies signature
  -> claim-budget validator rejects
  -> authentication not created
  -> controller calls = 0
~~~

For opaque tokens, substitute introspector for decoder. Over-cap tokens must be blocked before any network call; tests can verify `MockWebServer` receives zero introspection requests.

## 14. Common Mistakes

| Practice | Problem | Mitigation |
|---|---|---|
Limiting only body size | `Authorization` header can still be huge | Set dedicated request-header caps |
Limiting only in Spring resolver | HTTP server already read/parsed headers beforehand | Enforce limits at proxy and connector |
Limiting only total headers | One token can consume nearly the whole budget | Add `Authorization`/token caps |
Setting caps only at the gateway | Direct backend path may have weaker limits | Set caps at the embedded server too |
Setting huge header limits | Expands memory/DoS budget | Measure tokens, trim claims, set tight caps |
Checking size after decoding JWT | Parser already paid input cost | Check token length before decoder |
Merging duplicate `Authorization` headers | Credential ambiguity and proxy/server discrepancies | Reject duplicate headers |
Allowing tokens in query strings | Tokens leak to logs/history/referrers | Use `Authorization` header |
Stuffing all groups into JWTs | Token and authority bloat | Issue minimal scopes or look up permissions |
Mapping every claim to an authority | Privilege inflation and cost increase | Map only claims per issuer contract |
Logging raw `Authorization` headers | Bearer credential leakage | Log only size and request ID |
Assuming HTTP/2 compression solves header size | Decompressed headers can still be huge | Enforce decoded header limits |
Using `MockMvc` to test connector 431 | `MockMvc` does not traverse socket connectors | Test `RANDOM_PORT` and real gateway |
Assuming every server returns 431 | Connectors may return 400 | Assert contract matching server/version |
Testing large tokens without checking decoder calls | Doesn't prove the guard runs before crypto/network | Spy decoder/introspector and assert zero calls |

## 15. Secure Deployment Checklist

### Edge and HTTP Server

- [ ] Gateway/load balancer enforces total request header limits.
- [ ] Embedded HTTP connector enforces request header limits.
- [ ] Limits are verified on the exact connector/version.
- [ ] Backend cannot be reached directly with unexpectedly weaker limits.
- [ ] Actual status returned for oversized headers (400/431) is verified.

### Bearer Token

- [ ] Accepts only `Authorization: Bearer` headers per policy.
- [ ] Dedicated limit on `Authorization` header value.
- [ ] Token length limit after stripping `Bearer` scheme.
- [ ] Rejects invalid characters and duplicate `Authorization` headers.
- [ ] Oversized tokens are rejected before decoder/introspector.
- [ ] Does not accept tokens in query strings barring an evaluated exception.

### Claims and Processing Cost

- [ ] Issuer emits access tokens containing only required claims.
- [ ] Budgets exist for scopes, groups, and permissions.
- [ ] Custom converters do not create unbounded authorities.
- [ ] JWT algorithms/key sources are restricted per trust policy.
- [ ] Introspection responses and custom attributes are bounded.
- [ ] Tokens, secrets, and raw `Authorization` headers are never logged.

### Tests

- [ ] Tests cover tokens below, equal to, and above the cap.
- [ ] Tests cover duplicate headers and non-ASCII input.
- [ ] Tests verify decoder/introspector is never called for oversized tokens.
- [ ] Tests verify over-threshold claim counts are rejected.
- [ ] Tests cover connector limits using a `RANDOM_PORT` HTTP server.
- [ ] Tests cover gateway/ingress limits in the deployment pipeline.
- [ ] Tests separately cover valid tokens, invalid tokens, and missing-scope tokens.

## 16. Conclusion

~~~text
REQUEST HEADERS
  gateway / proxy limit
      |
      v
  HTTP connector limit
      |
      v
AUTHORIZATION HEADER
  duplicate / ASCII / header-value cap
      |
      v
BEARER TOKEN
  token-length cap
      |
      v
TOKEN VALIDATION
  JWT signature + claims
  or opaque introspection
      |
      v
CLAIM / AUTHORITY BUDGET
      |
      v
AUTHORIZATION + CONTROLLER
~~~

Limiting token and header sizes is part of protecting a Resource Server against untrusted inputs. Proxy/connector limits protect resources before Spring Security runs; dedicated Bearer resolver limits prevent oversized tokens from entering decoders or introspectors; claim budgets control principal and authority creation costs. Every layer must have finite thresholds suited to tokens issued by your issuer and verified against the real HTTP connector/proxy.

When requests exceed thresholds, reject early without invoking expensive verification steps. When tokens are within limits, still verify the full signature or introspection, issuer, audience, timestamps, and permissions. Never raise limits unboundedly, never accept duplicate credentials, and never log raw tokens to troubleshoot size errors.

## References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer tokens in the `Authorization` header and error semantics.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP field limits and status semantics.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): HTTP 431 Request Header Fields Too Large.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 field sections and header processing.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT claims and compact serialization.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT validation and algorithm/key handling.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token claims/profile.
- [Spring Boot Reference — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): server request-header configuration; property availability depends on Boot version.
- [Spring Security API — BearerTokenResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenResolver.html): Servlet bearer-token resolution contract.
- [Spring Security API — DefaultBearerTokenResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html): default `Authorization`-header resolver.
- [Spring Security API — ServerBearerTokenAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/authentication/ServerBearerTokenAuthenticationConverter.html): reactive bearer-token conversion.
- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, validation, and authentication conversion.
- [Spring Security Reference — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and opaque-token authentication.
