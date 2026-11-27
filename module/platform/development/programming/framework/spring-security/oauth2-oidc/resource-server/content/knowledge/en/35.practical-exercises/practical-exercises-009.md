# Verifying 400, 401, 403, and the `WWW-Authenticate` Header

## 1. Why Verify Both Status Codes and `WWW-Authenticate`?

A Resource Server API can return the same HTTP status code in multiple scenarios, yet the error's meaning and how clients handle it differ. For instance, `400 Bad Request` can originate from malformed JSON or a syntactically invalid Bearer request; `401 Unauthorized` can stem from a missing token or an unverifiable token; `403 Forbidden` can result from a missing OAuth scope or a business policy denial.

With OAuth 2.0 Bearer Tokens, the response also carries a `WWW-Authenticate` header describing the authentication scheme and error challenge. Asserting the status code alone is not enough to confirm the Resource Server responds per the protocol.

A solid test should verify:

- At which layer the request failed: request parsing, authentication, or authorization?
- Is the status code semantically accurate?
- Does the `WWW-Authenticate` header carry the appropriate scheme and error?
- Does the error description leak tokens, sensitive claims, or internal details?
- Did the rejected request avoid side effects and avoid returning unauthorized data?

## 2. Distinguishing 400, 401, and 403

### 2.1. `400 Bad Request`

`400` indicates the server cannot or will not process the request due to a syntax or representation error. In a Resource Server API, two groups must be distinguished:

1. **Ordinary request/API errors:** malformed JSON, request body failing validation, malformed parameters, missing required fields.
2. **OAuth Bearer `invalid_request`:** the request delivers token information improperly, such as sending tokens via multiple methods simultaneously or invalid Bearer transport syntax.

Not every `400` error is an OAuth error. A Bean Validation error on a request body does not automatically require a Bearer challenge header.

### 2.2. `401 Unauthorized`

`401` means the request lacks valid authentication credentials. For a Bearer Resource Server, common cases include:

- No access token sent to an endpoint requiring authentication.
- Expired token.
- Invalid or unverifiable JWT signature.
- Unaccepted issuer/audience.
- Token inactive or invalid per introspection.
- Token does not match the configured profile/algorithm.

Per HTTP semantics, a `401` response must include at least one challenge in `WWW-Authenticate`. For a Bearer Resource Server, the challenge is typically `Bearer`.

When a request has no credentials, the server can return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

When a token was sent but is invalid, RFC 6750 defines the `invalid_token` error:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

The server may add `realm`, `error_description`, or `error_uri` per policy.

### 2.3. `403 Forbidden`

`403` means the server understood the request and `Authentication` was established, yet the principal lacks permission to perform the action.

Examples:

- Valid JWT missing `SCOPE_orders.read`.
- Principal lacks the role required by the endpoint.
- User lacks membership in the target tenant.
- Resource belongs to another owner/team.
- Business policy denies the operation.

In OAuth Bearer, the case of a valid access token lacking a required scope is described in RFC 6750 with `insufficient_scope` and status `403`:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

Not every authorization error is a missing scope. If the user has the API scope but is denied by a tenant/ownership policy, use an error contract matching your application; do not attach `insufficient_scope` when that misrepresents the cause.

## 3. Decision Table per RFC and API Behavior

| Scenario | Failure layer | Common status | Bearer challenge |
|---|---|---:|---|
| Malformed JSON body | Request parsing | 400 | No Bearer error needed |
| Body missing field/validation fails | API validation | 400 | No Bearer error needed |
| Bearer request uses multiple token methods or bad syntax | Token request parsing | 400 | `error="invalid_request"` |
| No token on protected endpoint | Authentication | 401 | `Bearer`; usually no `error` parameter |
| Wrong JWT signature/issuer/audience/expiry | Authentication | 401 | `error="invalid_token"` |
| Inactive opaque token | Authentication | 401 | `error="invalid_token"` |
| Valid token, missing required scope | Authorization | 403 | `error="insufficient_scope"`; scope may be listed |
| Valid token but tenant/owner policy denies | Authorization | 403 or 404 per contract | Do not default to `insufficient_scope` |
| Resource does not exist or is hidden | Resource lookup/policy | 404 | Normally no Bearer error |

The statuses in this table reflect standard usage and the corresponding OAuth/HTTP contracts. APIs may have custom exception mappings for domain errors; the key is never confusing authentication failure with authorization failure.

### 3.1. Distinguishing `invalid_request` from `invalid_token`

These two errors are easily conflated:

- `invalid_request`: the request delivered the token to the server improperly, or the Bearer request violated transport syntax/format.
- `invalid_token`: a token was received, yet the token itself is invalid, expired, revoked, or unacceptable.

For example, a three-segment JWT with an invalid signature is normally `invalid_token`, not `invalid_request`. Conversely, a request sending tokens via multiple methods at once is a malformed token request.

### 3.2. Do Not Return `401` for Insufficient Permissions

If the token authenticated and produced an `Authentication`, lacking an authority is normally `403`. Returning `401` for everything leads clients to believe their credentials are invalid and trigger pointless token refreshes.

Conversely, do not return `403` for a JWT with an invalid signature. An invalid signature is an authentication failure and must be handled as `401`.

## 4. What Is the `WWW-Authenticate` Header?

`WWW-Authenticate` is a response header used to send an authentication challenge. It tells the client which scheme the server supports and, for OAuth Bearer, can supply a token-related error code.

This header differs from the request header `Authorization`:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...
~~~

Response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
~~~

- `Authorization`: client sends credentials to the server.
- `WWW-Authenticate`: server notifies the client of the challenge/error.

A challenge header is not an access token, not a response body, and not a token-endpoint JSON error.

### 4.1. Bearer Challenge Parameters

| Parameter | Meaning |
|---|---|
| `realm` | Protection space/resource area |
| `error` | Bearer error code per RFC 6750 |
| `error_description` | Short description for client/developer |
| `error_uri` | Documentation URI describing the error |
| `scope` | Required scope or scope associated with the error |

Important Bearer error codes:

| Error code | Meaning | Status per RFC 6750 |
|---|---|---:|
| `invalid_request` | Token request malformed or missing required structure | 400 |
| `invalid_token` | Token expired, revoked, malformed, or invalid | 401 |
| `insufficient_scope` | Token lacks required permission/scope | 403 |

Not every response needs every parameter. In particular, when the client sent no token, the server typically sends only the challenge scheme and omits `error="invalid_token"`, because no token was presented to judge invalid.

### 4.2. The Header Can Contain Multiple Challenges

A server supporting multiple authentication schemes may send multiple challenges in a response. Clients must parse challenges according to HTTP authentication grammar rather than assuming the header holds a single scheme or a fixed string.

Illustrative example:

~~~http
WWW-Authenticate: Bearer realm="api"
WWW-Authenticate: Basic realm="legacy"
~~~

Some HTTP libraries fold multiple header values on read. In tests, prefer checking the required scheme/error rather than matching the entire string verbatim when ordering or formatting may vary across servers/containers.

## 5. How Spring Security Produces 400/401/403

### 5.1. Authentication Failure and `AuthenticationEntryPoint`

In the Servlet stack, Bearer token authentication runs in the security filter chain. When a request lacks a valid `Authentication` or a token is rejected, Spring Security invokes `AuthenticationEntryPoint` to commence the authentication challenge.

For OAuth 2.0 Resource Server, the standard handlers are:

- `BearerTokenAuthenticationEntryPoint`: produces Bearer challenges for authentication failures.
- `BearerTokenAccessDeniedHandler`: handles access denied in a Bearer Resource Server.

When configuring Resource Server with defaults:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Spring Security wires the appropriate Bearer authentication handlers. Therefore, before writing custom handlers, inspect the default behavior of your active version and test actual responses.

### 5.2. `BearerTokenAuthenticationEntryPoint`

This entry point translates OAuth authentication errors into status codes and challenge headers. Key scenarios:

- Missing token: `401` and Bearer challenge.
- Invalid/expired token: `401` with `error="invalid_token"`.
- Bearer request classified as `invalid_request`: `400` with the corresponding error.

Example configuring it directly:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    entryPoint.setRealmName("orders");

    return http
        .exceptionHandling(errors -> errors
            .authenticationEntryPoint(entryPoint)
        )
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationEntryPoint(entryPoint)
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

In applications, you can leave Resource Server's default entry point if you do not need custom realm/error policies. When both global exception handling and a Resource Server-specific entry point are configured, verify which handler processes Bearer errors on each path.

### 5.3. `BearerTokenAccessDeniedHandler`

When `Authentication` is established but authorization denies access, Spring Security calls `AccessDeniedHandler`. Resource Server provides a Bearer-specific handler:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    BearerTokenAccessDeniedHandler deniedHandler =
        new BearerTokenAccessDeniedHandler();

    return http
        .exceptionHandling(errors -> errors
            .accessDeniedHandler(deniedHandler)
        )
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

For a valid token lacking scope, the response is typically `403` with a Bearer challenge describing `insufficient_scope`. The required scope may be included per policy.

For authorization failures unrelated to missing OAuth scopes—such as tenant membership or resource ownership—consider a separate error contract. Do not turn every access denial into a "missing orders.read" message when the real cause is that the user does not own the resource.

### 5.4. Customizing Error Response Bodies

`WWW-Authenticate` is a protocol header; the response body can be empty, Problem Detail, or an error envelope per the API contract. When standardizing the body:

- Keep the status code and challenge header intact.
- Do not overwrite or remove `WWW-Authenticate` when writing `ProblemDetail`.
- Never return raw exception messages, JWTs, sensitive claims, or introspection responses.
- Include a request ID to correlate responses with server logs.
- Never turn an authentication failure into HTTP `200` with an error object.

Example body an API might use:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required",
  "requestId": "req-7f2c"
}
~~~

This is an illustrative body, not the default body of the Bearer entry point. Clients should rely on the HTTP status and challenge header for OAuth authentication handling; the body supports API diagnostics per contract.

## 6. When to Customize `AuthenticationEntryPoint` or `AccessDeniedHandler`?

Customize only when the application has specific needs such as standardizing `ProblemDetail`, attaching correlation/request IDs, setting a custom realm name, localizing UI messages while preserving the challenge, classifying domain authorization errors, or maintaining compatibility with a legacy API error schema.

A custom entry point must preserve `401` and `WWW-Authenticate` semantics:

~~~java
@Component
public class ApiAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint delegate =
        new BearerTokenAuthenticationEntryPoint();

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException {

        delegate.commence(request, response, exception);

        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        response.getWriter().write("""
            {
              "type": "about:blank",
              "title": "Unauthorized",
              "status": 401,
              "detail": "Authentication is required"
            }
            """);
    }
}
~~~

This minimal example illustrates delegating to preserve the Bearer challenge. In production, serialize the body with `ObjectMapper`/`ProblemDetail`, set proper encoding and content length, and avoid overwriting headers set by the delegate. If the response is already committed, do not write a body again.

A custom `403` handler must preserve the challenge when the error is genuinely `insufficient_scope`. You can delegate to `BearerTokenAccessDeniedHandler` first and then append a safe body. For custom domain policies, use an error code/domain handler with accurate semantics.

### 6.1. Beware of Global Exception Handling

If configuring:

~~~java
.exceptionHandling(errors -> errors
    .authenticationEntryPoint(customEntryPoint)
    .accessDeniedHandler(customDeniedHandler)
)
~~~

verify handler precedence and scope relative to the Resource Server configurer. Resource Server may register its own entry point for Bearer requests. Setting a global handler does not guarantee every authentication exception routes through that same handler.

Test through the real filter chain, not solely by calling the handler directly.

## 7. Do Not Confuse OAuth Errors with Ordinary API Errors

An endpoint can return `400` completely unrelated to Bearer tokens:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <VALID-TOKEN>
Content-Type: application/json

{"quantity": "not-a-number"}
~~~

If the token is valid but the body has an invalid field type, the request passed authentication and failed at the binding/validation layer. The response is typically `400` with an API error body. No Bearer challenge with `error="invalid_token"` is needed.

Conversely:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <EXPIRED-TOKEN>
~~~

The request parses cleanly yet authentication fails, so it returns `401` and an `invalid_token` challenge.

| Layer | Example error | Status | Bearer header |
|---|---|---:|---|
| HTTP/request parsing | Malformed JSON | 400 | Not needed |
| Bean Validation | Invalid field | 400 | Not needed |
| Bearer request parsing | Invalid token transport | 400 | `invalid_request` |
| Authentication | Missing token | 401 | `Bearer` |
| Authentication | Invalid JWT | 401 | `invalid_token` |
| Authorization | Missing scope | 403 | `insufficient_scope` |
| Domain authorization | Wrong tenant/owner | 403/404 | Per policy; do not claim `insufficient_scope` |


## 8. Testing with MockMvc on the Servlet Stack

### 8.1. Ensure MockMvc Runs Through the Spring Security Filter Chain

A basic integration test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BearerErrorResponseTests {

    @Autowired
    MockMvc mvc;
}
~~~

If building MockMvc manually from `WebApplicationContext`, apply Spring Security:

~~~java
mvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Do not use `@AutoConfigureMockMvc(addFilters = false)` when testing Bearer extraction, authentication entry points, or access denied handlers. When filters are disabled, status codes may come from controllers and fail to prove Resource Server behavior.

### 8.2. Missing Token: `401` and Bearer Challenge

~~~java
@Test
void missingTokenReturns401WithBearerChallenge() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            startsWith("Bearer")
        ));
}
~~~

This test verifies the protected endpoint requires authentication and advertises the Bearer scheme. For requests without a token, do not require `error="invalid_token"` because the client sent no token for the server to deem invalid.

### 8.3. Invalid Token: `401` and `invalid_token`

When using a real decoder, send an improperly signed compact JWT or one with invalid claims via the `Authorization` header. Testing signature/issuer/audience/expiry with test keys verifies both the decoder and the filter chain.

To isolate response mapping, you can mock the decoder in the test context:

~~~java
@MockitoBean
JwtDecoder jwtDecoder;

@Test
void invalidJwtReturns401WithInvalidTokenChallenge() throws Exception {
    when(jwtDecoder.decode("invalid-fixture"))
        .thenThrow(new JwtException("Invalid test token"));

    mvc.perform(get("/api/orders/42")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer invalid-fixture"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            allOf(
                startsWith("Bearer"),
                containsString("error=\"invalid_token\"")
            )
        ));
}
~~~

`@MockitoBean` is available in Spring Framework 6.2+/Spring Boot 3.4+. Older versions may use `@MockBean`. This test verifies error mapping through the filter chain, though a mocked decoder does not check JWT signatures. To test signatures, issuer, and audience, use a real decoder with key fixtures.

### 8.4. Valid Token Missing Scope: `403`

Use the MockMvc JWT post-processor to create an authenticated JWT principal with insufficient authority:

~~~java
@Test
void jwtWithoutReadScopeReturns403() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile.read")
            )))
        .andExpect(status().isForbidden());
}
~~~

To check the access-denied handler's Bearer challenge, assert the scheme:

~~~java
.andExpect(header().string(
    HttpHeaders.WWW_AUTHENTICATE,
    startsWith("Bearer")
));
~~~

If the application uses `BearerTokenAccessDeniedHandler` and the denial is genuinely due to a missing scope, you can also assert:

~~~java
.andExpect(header().string(
    HttpHeaders.WWW_AUTHENTICATE,
    containsString("error=\"insufficient_scope\"")
));
~~~

Exact header values depend on the handler and version/configuration. If the endpoint rejects due to tenant/ownership policy, do not assert `insufficient_scope` unless the application intentionally models that policy as an OAuth scope.

### 8.5. Invalid Request Body: `400` Without Being a Bearer Error

Use a JWT principal with sufficient permissions so the request reaches the controller, then send a body failing validation:

~~~java
@Test
void invalidBodyReturns400WithoutInvalidTokenChallenge() throws Exception {
    mvc.perform(post("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            ))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"quantity": -1}
                """))
        .andExpect(status().isBadRequest())
        .andExpect(header().doesNotExist(
            HttpHeaders.WWW_AUTHENTICATE
        ));
}
~~~

Asserting the absence of the header fits when `400` comes from MVC validation/binding rather than Bearer token parsing. If the application has a policy that attaches a challenge to every response, adjust the test per the published contract.

In this example, the DTO needs a validation constraint such as `@Min(1)` and the controller needs `@Valid` so a negative value actually produces `400`. If the chain keeps CSRF enabled for `POST` requests, add `.with(csrf())` to the test request to isolate body validation rather than getting rejected by the CSRF filter first.

### 8.6. Testing `invalid_request` at the Bearer Entry Point

You can test `invalid_request` mapping with an entry point unit test:

~~~java
@Test
void invalidBearerRequestMapsTo400Challenge() throws Exception {
    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    MockHttpServletRequest request = new MockHttpServletRequest();
    MockHttpServletResponse response = new MockHttpServletResponse();

    OAuth2AuthenticationException exception =
        new OAuth2AuthenticationException(
            new OAuth2Error(OAuth2ErrorCodes.INVALID_REQUEST)
        );

    entryPoint.commence(request, response, exception);

    assertThat(response.getStatus()).isEqualTo(400);
    assertThat(response.getHeader(HttpHeaders.WWW_AUTHENTICATE))
        .contains("error=\"invalid_request\"");
}
~~~

This unit test verifies mapping from an OAuth error to an HTTP response. To prove the request resolver actually emits `invalid_request`, write an integration test using the application's actual `BearerTokenResolver`/transport configuration. Do not enable query/form token transport solely to make testing easier.

## 9. Testing with `WebTestClient` on WebFlux

Reactive Resource Server has the corresponding handlers for server web exchanges:

- `BearerTokenServerAuthenticationEntryPoint`.
- `BearerTokenServerAccessDeniedHandler`.

A test class can use:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveBearerErrorResponseTests {

    @Autowired
    WebTestClient webTestClient;
}
~~~

### 9.1. Missing Token: `401`

~~~java
@Test
void missingTokenReturnsBearerChallenge() {
    webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().valueMatches(
            HttpHeaders.WWW_AUTHENTICATE,
            "Bearer.*"
        );
}
~~~

### 9.2. JWT Lacking Authority: `403`

~~~java
@Test
void jwtWithoutReadScopeIsForbidden() {
    webTestClient.get()
        .uri("/api/orders/42")
        .mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read")
        ))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

`mockJwt()` creates a simulated `Authentication` to test authorization. It does not call `ReactiveJwtDecoder` and does not verify signatures. To test the decoder, send a signed compact token via the Bearer header with a real decoder configured.

### 9.3. Checking Challenge Headers

If the reactive Resource Server is configured with Bearer server handlers, you can assert the header when a request is rejected:

~~~java
.expectHeader().valueMatches(
    HttpHeaders.WWW_AUTHENTICATE,
    "Bearer.*"
);
~~~

For error parameters, verify against your exact policy and active handler. Do not assume every WebFlux `403` must carry `error="insufficient_scope"`.

## 10. Writing Resilient Header Assertions

### 10.1. Assert Required Scheme and Error

This assertion is usually more resilient than matching the entire header:

~~~java
.andExpect(header().string(
    HttpHeaders.WWW_AUTHENTICATE,
    allOf(
        startsWith("Bearer"),
        containsString("error=\"invalid_token\"")
    )
));
~~~

The header may also carry `realm`, `scope`, or `error_description`. Parameter order and serialization can vary across versions. Assert only the parts mandated by the contract.

### 10.2. Do Not Parse the Header with a Naive `split`

Avoid:

~~~java
String[] parts = header.split(",");
~~~

Challenge values can contain quoted strings, commas, or multiple challenges. Use an HTTP client/parser that understands authentication challenge grammar for general parsing. In tests, Hamcrest assertions on required fragments are usually sufficient.

### 10.3. Do Not Assert Fixed `error_description` Strings

`error_description` is supplemental information for developers/clients. Its wording can change across versions, locales, or configurations. Do not couple tests to raw exception messages like "JWT expired at ..." or library internals.

If the API publishes a stable error code, assert that code. Avoid returning or asserting content containing tokens, signatures, internal hostnames, key paths, stack traces, or sensitive claims.

## 11. Verifying Status Codes and Challenges with a Regression Matrix

A test suite should cover both positive and negative cases:

| Case | Request | Expected status | `WWW-Authenticate` |
|---|---|---:|---|
| Public endpoint | No token | `2xx` | Not needed |
| Protected endpoint, no token | No `Authorization` | 401 | Bearer challenge |
| Expired JWT | Expired Bearer token | 401 | Bearer, `invalid_token` |
| Invalid JWT signature | Bearer token signed with untrusted key | 401 | Bearer, `invalid_token` |
| Wrong issuer/audience | Bearer JWT failing validator | 401 | Bearer, `invalid_token` |
| Inactive opaque token | Bearer token rejected by introspection | 401 | Bearer, `invalid_token` |
| Malformed Bearer request | Wrong token transport/syntax | 400 | Bearer, `invalid_request` if mapped per RFC 6750 |
| Valid token, missing scope | Authenticated, missing authority | 403 | May include Bearer `insufficient_scope` |
| Valid token, tenant policy denies | Authenticated, wrong tenant | 403/404 | Per domain contract |
| Invalid JSON body | Valid token, invalid request body | 400 | No Bearer error needed |

In each test, beyond status and header, verify the response body leaks no credentials, stack traces, or denied resource data.

## 12. Diagnosing When Status Is Right but Header Is Wrong

### 12.1. `401` Missing `WWW-Authenticate`

Check:

- Did the endpoint actually traverse the Resource Server filter chain?
- Did a custom `AuthenticationEntryPoint` set the status and forget the challenge header?
- Did `@ControllerAdvice` catch an exception and turn it into `401`?
- Did a gateway strip response headers?
- Did a different `SecurityFilterChain` have another matcher/entry point?

A controller returning `ResponseEntity.status(401)` on its own does not emit a Bearer challenge. When an endpoint requires Bearer authentication, let the security layer handle authentication failures or use a handler that sets the right challenge.

### 12.2. `401` with the Wrong Error

If a token was sent and is invalid, the challenge should indicate `invalid_token`. If no token was sent, sending only the Bearer challenge is more accurate.

Check exception mappings and custom handlers. Do not attach `invalid_token` to every `401` from a controller, as a `401` might come from a different authentication scheme.

### 12.3. `403` Incorrectly Tagged with `insufficient_scope`

A principal can be denied due to tenant membership, object ownership, or business policy despite holding the scope. If the challenge reports `insufficient_scope`, clients will conclude they need to request another scope from the Authorization Server.

Return this error only when a scope is genuinely missing. Domain authorization can use its own error body and `403`/`404` per the API contract.

### 12.4. `400` Tagged with `invalid_token`

When a request body is malformed or query parameter validation fails, never use Bearer `invalid_token`. Determine whether the error happened before or after authentication. An invalid JWT is not malformed JSON; malformed JSON is not an invalid access token.

### 12.5. Gateway Altering Challenge Headers

Some proxies/gateways rewrite, normalize, or merge response headers. Compare direct backend responses against responses through the public route. If only the public route differs, check gateway response-header policies and CORS exposure.

If browser JavaScript needs to read the header, CORS may need to expose `WWW-Authenticate`:

~~~http
Access-Control-Expose-Headers: WWW-Authenticate
~~~

Exposing the header merely allows browser JavaScript to read it; it does not replace authentication challenges and grants no API access.

## 13. How Should Clients Handle Challenges?

Clients should not simply see a status code and refresh the token in every case.

| Response | Appropriate client action |
|---|---|
| `400` API validation | Fix the request/body/parameters |
| `400` `invalid_request` | Fix how the Bearer credential is sent; do not retry verbatim |
| `401` with no token | Perform authentication/token acquisition |
| `401` `invalid_token` | Refresh/acquire a new token if the flow allows; avoid infinite loops |
| `403` `insufficient_scope` | Request the appropriate grant/scope or inform the user of missing permissions |
| `403` domain policy | Report access denied; do not wastefully refresh tokens |
| `404` hidden resource | Handle as unavailable resource per contract |

When refreshing tokens, clients must avoid multiple concurrent requests refreshing the same credential if the provider uses refresh token rotation. After a `401`, never retry endlessly with the old token. On `403`, refreshing a token usually will not fix missing roles, tenant membership, or ownership.

## 14. Common Mistakes When Writing Tests

### Mistake 1 — Asserting Only Status Codes

`401` might lack a challenge header; `403` might carry the wrong error code. Assert status codes together with critical headers.

### Mistake 2 — Expecting `401` When a Valid Token Lacks Scope

That is an authorization failure, normally `403`. `401` is reserved for authentication failures.

### Mistake 3 — Attaching `invalid_token` to Requests Without a Token

With no credentials presented, the server cannot conclude a sent token is invalid. The Bearer challenge may include only scheme/realm.

### Mistake 4 — Using `jwt()` to Test Signatures

MockMvc `jwt()` or WebFlux `mockJwt()` creates a simulated `Authentication`. They do not run the decoder. Send signed JWTs via the Bearer header through a real decoder to test signatures/issuers/audiences.

### Mistake 5 — Using `@WithMockUser` to Test `WWW-Authenticate: Bearer`

`@WithMockUser` creates an already-authenticated `Authentication` in the test context. It fits authority-only tests and does not trigger Bearer authentication failures. Send requests with no token or invalid tokens through the filter chain to test the entry point.

### Mistake 6 — Returning `403` for All Token Errors

A JWT with a bad signature, wrong issuer, or expired timestamp is `401`. Only an authenticated principal lacking permissions returns `403`.

### Mistake 7 — Returning `400` for All Malformed JWTs

A token delivered via valid Bearer transport whose JWT fails parsing/verification is normally `invalid_token` and `401`. `invalid_request` is for malformed request/token transport under the Bearer protocol.

### Mistake 8 — Matching the Entire `WWW-Authenticate` String Verbatim

`realm`, `scope`, and `error_description` may be added, omitted, or ordered differently. Assert the required scheme and error parameter.

### Mistake 9 — Putting Tokens or Exception Details in `error_description`

Headers are part of the response sent to clients. Never put raw JWTs, signatures, internal hostnames, key paths, stack traces, or sensitive claims into them.

### Mistake 10 — `ControllerAdvice` Masking Security Challenges

A global exception handler may build a `401`/`403` body while dropping headers set by the security entry point/access-denied handler. Test through the filter chain and verify status, headers, and body together.

## 15. Pre-Release Checklist for Resource Server APIs

- [ ] Protected endpoints without a token return `401`.
- [ ] `401` responses include a `WWW-Authenticate` Bearer challenge.
- [ ] Requests without a token are not semantically mislabeled with `error="invalid_token"`.
- [ ] Invalid/expired/bad-signature/wrong-issuer/wrong-audience JWTs return `401` and `invalid_token`.
- [ ] Malformed Bearer requests are classified as `invalid_request` and `400` where applicable.
- [ ] Valid tokens missing scopes return `403`.
- [ ] `insufficient_scope` is used only when a scope is genuinely missing.
- [ ] Tenant/owner denials follow the domain's error contract.
- [ ] API validation `400`s are never turned into Bearer `invalid_token`.
- [ ] Custom entry points preserve challenge headers.
- [ ] Custom access-denied handlers preserve scope-denial semantics.
- [ ] Gateways do not strip or rewrite `WWW-Authenticate`.
- [ ] CORS exposes `WWW-Authenticate` if browser clients need to read it.
- [ ] Bodies/`error_description` leak no tokens, sensitive claims, or stack traces.
- [ ] MockMvc/`WebTestClient` tests execute through the filter chain.
- [ ] Signed-token tests run through a real decoder for authentication validation.
- [ ] Separate tests verify authorization and request validation.
- [ ] Clients do not refresh tokens endlessly upon `401`/`403`.

## 16. Conclusion

`400`, `401`, and `403` represent different failure layers. `400` usually signals an invalid request; under the Bearer protocol, `invalid_request` is also `400`. `401` is an authentication failure such as a missing token or `invalid_token` and must include a `WWW-Authenticate` challenge. `403` is an authorization denial; when a valid token lacks scope, RFC 6750 defines `insufficient_scope`.

When testing Spring Security Resource Servers, exercise the real filter chain, assert both status codes and challenge headers, and separate request validation errors from Bearer authentication errors. Use `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler`—or their WebFlux equivalents—to preserve protocol semantics when customizing responses. Inspect response bodies, side effects, and client behavior to prevent authentication errors from triggering infinite refresh or retry loops.

### References

- [RFC 9110 — HTTP Semantics, 401/403 and WWW-Authenticate](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage, Section 3](https://www.rfc-editor.org/rfc/rfc6750)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security API — BearerTokenAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html)
- [Spring Security API — BearerTokenAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html)
- [Spring Security Reference — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security Reference — Testing Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)
