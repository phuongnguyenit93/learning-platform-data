# Testing Both Allowed Paths and Paths That Must Be Denied

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, HTTP authorization configuration is not just about letting users with a valid access token call the API. Equally important is ensuring **every unauthorized request is blocked at the right place**: missing tokens, invalid tokens, missing scopes, wrong HTTP methods, wrong URLs, or lacking permissions on a specific record.

If you only test `GET /api/orders/42` with a sufficiently privileged token and observe HTTP 200, you have verified only **that one allowed case works**. You still do not know:

- Can someone without a token reach the endpoint?
- Can a read-only token accidentally call a delete/cancel order endpoint?
- Is `POST` to a `GET`-only URL rejected?
- Is a newly added endpoint or a URL matching no rule protected?
- Is a token from another issuer, with the wrong audience, or with a bad signature rejected **before** creating a principal?
- Is a caller with read scope blocked when attempting to read an order belonging to another tenant?

**This lesson focuses on two-sided testing of HTTP authorization: paths that must be allowed (positive paths) and paths that must be denied (negative paths)**, in the context of a Spring Security API receiving OAuth 2.0 Bearer access tokens. The goal is to prove the policy applies accurately across **HTTP method + URL + identity/token + authority + business resource**, rather than verifying only a single "happy path."

> **Principle:** A security rule is adequately verified only with evidence for both **authorized callers getting in** and **unauthorized callers or wrong-path requests being blocked**. For a Resource Server, separate testing of **authentication (401)**, **authorization (403/404 per policy)**, and **business/data policy**. Everything outside the contract must be denied by default.

## 1. Distinguishing "Paths" Across Multiple Dimensions

Here, "path" does not mean only the URL. It means **the processing path a request takes through the security filter chain, authorization, and business layers**.

Suppose a retail system consists of:

- **Shop Web:** OAuth2 Client requesting access tokens for users or services.
- **Identity Server:** Authorization Server issuing signed JWT access tokens.
- **Orders API:** Spring Security Resource Server verifying tokens and protecting endpoints.
- **Order Service/Database:** deciding permissions over actual orders, tenants, and states.

A request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

Has at least four layers to examine:

| Layer | Question | Example cases that should be denied |
| --- | --- | --- |
| **Authentication** | Did the caller provide verified credentials? | No token, bad JWT signature, wrong issuer/audience, expired token |
| **HTTP authorization** | May a caller with this authority access this method + URL? | Has `orders.read` yet calls `POST /api/orders` |
| **Method authorization** | Does the business method require an extra permission/role? | Token has scope yet lacks cancel permission |
| **Resource/data policy** | May the caller access this **specific object**? | Has order-read permission yet order 42 belongs to another tenant |

A 200 response at the HTTP layer does not confirm data policy is right. Likewise, a 403 response does not prove a JWT was rejected for a bad signature. You must know **at which layer and why a request was blocked**.

~~~mermaid
flowchart TD
    A["HTTP request: method + path + Bearer token"]
    B["Selected SecurityFilterChain"]
    C["JwtDecoder: verify signature and validate claims"]
    D{"Valid authentication?"}
    E["401 / authentication error"]
    F["authorizeHttpRequests: method + URL + authorities"]
    G{"Does rule allow?"}
    H["403 / deny per policy"]
    I["Method security and resource policy"]
    J{"Permitted on resource?"}
    K["Return business result"]

    A --> B --> C --> D
    D -->|No| E
    D -->|Yes| F --> G
    G -->|No| H
    G -->|Yes| I --> J
    J -->|No| H
    J -->|Yes| K
~~~

The diagram is a conceptual model. For public endpoints, authentication may not be required; anonymous requests still pass through filter chain selection and the `permitAll()` rule. Exact responses depend on Spring Security configuration, entry points, access denied handlers, and business policies.

## 2. Defining the HTTP Contract Before Writing Tests

An API can align on an access matrix like this:

| HTTP method | URL | Who is allowed | Additional rules |
| --- | --- | --- | --- |
| `GET` | `/api/public/catalog` | Public, no Bearer token required | Public catalog data only |
| `GET` | `/api/orders` | Token with `orders.read` | Return only orders caller is permitted to view |
| `GET` | `/api/orders/{id}` | Token with `orders.read` | Verify order owner/tenant |
| `POST` | `/api/orders` | Token with `orders.write` | Verify permission to create in tenant |
| `POST` | `/api/orders/{id}/cancel` | Token with `orders.cancel` | Verify cancel permission, owner, and state |
| Other methods/URLs under `/api/**` | No rule granted | **Deny** | Open only via intentional contract changes |
| Paths outside `/api/**` | Depends on other chains | **Deny** in example | Never leave without a protective chain |

The scopes `orders.read`, `orders.write`, and `orders.cancel` are **illustrative contract names**, not standard permissions defined by OAuth 2.0. The Client team, Authorization Server, and Orders API must agree on scope meanings, audiences, and token issuance rules.

A well-tested policy must cover:

1. **Allowed paths:** specific endpoint, specific method, specific authentication/authority.
2. **Denied paths:** missing/invalid token, lower privilege, lookalike URLs, different methods, and unauthorized resources.
3. **Default:** are requests matching no rule denied?
4. **Chain boundaries:** are paths outside `securityMatcher` protected by another chain?
5. **Expected error codes:** authentication error vs. permission error, or 404 to avoid disclosing resources?

## 3. 401 and 403 Reflect Two Different Failure Types

Two commonly seen responses:

| Code | Typical meaning in a Bearer Resource Server | Example |
| --- | --- | --- |
| **401 Unauthorized** | No valid authentication yet for the protected resource | No Bearer token, bad JWT signature, expired, wrong issuer/audience |
| **403 Forbidden** | Authenticated, yet lacking required permission per rule | Valid token with `orders.read`, while endpoint requires `orders.write` |
| **404 Not Found** | Resource does not exist, or API intentionally hides existence per policy | Order in another tenant, policy hides IDs |

This distinction helps tests pinpoint the wrong layer:

- If a JWT with a bad signature reaches the controller, **authentication was bypassed**.
- If a valid token missing a scope gets 200 from the API, **HTTP authorization is missing or has a buggy rule**.
- If the scope is right yet returns another tenant's order, **data policy has a vulnerability**.

**Do not assume every negative test must return 403.** Anonymous requests to protected endpoints typically yield 401; authenticated callers lacking permissions typically yield 403. For paths lacking a controller or on special chains, you may see 404 or another status. Tests must assert outcomes per **the actual contract**, while confirming no protected action occurred.

Specifically, `permitAll()` means **no permission required to access that endpoint**, not "skip all filters." If a client sends an **invalid Bearer token** to a public endpoint, the authentication filter can reject the request before reaching `permitAll()`. Test the public case **without sending a Bearer token**, rather than assuming a fake token must return 200.

## 4. Sample Deny-by-Default HTTP Authorization Configuration

Example using **Spring Boot 3 / Spring Security 6** and Java 17+, with Orders API accepting OAuth2 JWT access tokens.

### 4.1. Dependencies and Issuer

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
~~~

A JWT Resource Server must verify **signature, issuer, lifetime, audience, and token type** per contract. Configuring `issuer-uri` and `jwk-set-uri` does not mean every version automatically validates audience the way your app expects; configure an explicit audience validator when needed. Real JWT testing is distinguished from `MockMvc.jwt()` in section 8.

### 4.2. SecurityFilterChain Authorizing by Both Method and Path

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders/{id}/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll())
            .build();
    }
}
~~~

This configuration illustrates:

- **The first chain** handles only `/api/**`, prioritized via `@Order(1)`.
- Inside the API chain, **the public path is opened very narrowly**: only `GET /api/public/catalog`.
- Each read, create, and cancel operation has its own **method/path and scope**.
- `anyRequest().denyAll()` in the API chain blocks all other API requests, including newly added URLs without rules.
- **The fallback chain** blocks paths outside `/api/**` in the example, so requests do not bypass Spring Security merely because they miss the first chain.

This is an illustrative design for a REST API **using Bearer tokens rather than cookies/sessions for authentication**; hence the API chain disables CSRF and uses stateless sessions. If the same app serves a web UI using cookies or special endpoints, design CSRF and filter chains appropriately rather than copying CSRF disabling across all chains.

### 4.3. Why Do `securityMatcher` and `requestMatchers` Differ?

**`securityMatcher("/api/**")`** decides **whether the entire `SecurityFilterChain` applies to the request**.

**`requestMatchers(...)`** inside `authorizeHttpRequests` decides **the authorization rule inside the already-selected chain**.

~~~text
Incoming request
   |
   +-- Chain @Order(1), securityMatcher("/api/**")?
   |      |
   |      +-- Yes -> apply GET/POST/denyAll rules of the API chain
   |
   +-- If no chain matched yet -> chain @Order(2)
                         |
                         +-- denyAll
~~~

If you declare only the first chain and no chain protects `/admin/**`, requests outside `/api/**` may **bypass the chain you thought was protecting everything**. Therefore, when multiple chains exist, test **paths inside chains**, **paths outside chains**, and **overlapping paths**.

### 4.4. Rule Ordering in `authorizeHttpRequests`

Matchers are evaluated in declaration order; an overly broad rule placed first can shadow a specific rule:

~~~java
// WRONG example: the broad rule can match before the narrow rule.
.requestMatchers("/api/**").permitAll()
.requestMatchers(HttpMethod.POST, "/api/orders/{id}/cancel")
    .hasAuthority("SCOPE_orders.cancel")
~~~

When the first matcher permits every request, the later rule may never apply. Thus **placing narrow rules first, broad rules later, and ending with `denyAll`** is an easy-to-audit principle.

Never assume that merely seeing `hasAuthority("SCOPE_orders.cancel")` in code means the cancel endpoint is definitely protected. You need **negative tests** proving callers lacking that scope are genuinely denied.

## 5. Positive and Negative Matrix for HTTP Routes

Once you have an endpoint contract, convert it into a test matrix. Never pick just one "admin" token carrying every scope to hit every endpoint, because that will not catch overly broad rules.

| # | Method and path | Principal / token | Expectation |
| --- | --- | --- | --- |
| P1 | `GET /api/public/catalog` | No Bearer token | **200** |
| P2 | `GET /api/orders` | Valid JWT, `orders.read` | Passes HTTP layer, returns data per policy |
| P3 | `GET /api/orders/42` | Valid JWT, `orders.read` | Passes HTTP layer, proceeds to owner/tenant checks |
| P4 | `POST /api/orders` | Valid JWT, `orders.write` | Passes HTTP layer, proceeds to order-creation policy |
| P5 | `POST /api/orders/42/cancel` | Valid JWT, `orders.cancel` | Passes HTTP layer, proceeds to cancel policy |
| N1 | `GET /api/orders/42` | No token | Typically **401** |
| N2 | `GET /api/orders/42` | Valid JWT, `orders.write` only | **403** |
| N3 | `POST /api/orders` | Valid JWT, `orders.read` only | **403** |
| N4 | `POST /api/orders/42/cancel` | Valid JWT, `orders.write` only | **403** |
| N5 | `POST /api/orders/42/refund` | Valid JWT, multiple scopes | **403** because no rule exists |
| N6 | `GET /api/orders/42/notes` | Valid JWT, `orders.read` | **403** because no rule exists for subpath |
| N7 | `POST /api/public/catalog` | Valid JWT | **403** because only GET is public |
| N8 | `GET /internal/secrets` | Valid JWT | Blocked by fallback chain |
| N9 | `GET /api/orders/42` | JWT with bad signature | Rejected at authentication |
| N10 | `GET /api/orders/42` | Valid signature JWT with wrong audience | Rejected at authentication |
| N11 | `GET /api/orders/42` | JWT with `orders.read` yet wrong tenant | Rejected at data policy |

**Expectations for P2–P5 are not automatically 200 in real applications**: if a resource does not exist, payload is invalid, or business policy forbids it, the API may return an appropriate error. In HTTP-only unit tests with a simple stub controller, 200 can show the rule allowed the request through. When testing the full system, assert the exact expected business outcome.

### 5.1. Why Test an Unrelated Scope?

If you only test a token with zero scopes, a minor mapping bug might still deny and let the test pass. A token with **`orders.write` yet missing `orders.read`** is a stronger test, because it proves permissions are not treated as interchangeable.

Similarly, an `orders.cancel` token **does not automatically include** `orders.write` or `orders.read`, unless the contract and policy define an explicit inclusion rule. Never assume scopes inherit from one another.

### 5.2. Why Test Lookalike URLs?

A matcher like `/api/orders/**` can cover more subpaths than the author intended. If `/api/orders/{id}/refund` or `/api/orders/{id}/export` is added later under an overly broad GET/POST rule, the new endpoint can inherit unsuitable legacy permissions.

Writing denial tests for **undeclared subpaths** catches "silent overexposure" changes. You can use **negative-space testing**: pick requests **outside the permitted set** that look very similar to valid requests.

## 6. MockMvc: Testing HTTP Policies in a Controlled Way

`spring-security-test` provides `SecurityMockMvcRequestPostProcessors.jwt()` to attach a simulated `JwtAuthenticationToken` to test requests. This is very useful when targeting **method/path rules and authorities**, because you do not need to spin up an Authorization Server, sign JWTs, or fetch JWKS in every test.

**Important limitation:** `jwt()` **does not prove real signature, issuer, audience, or `JwtDecoder` validation works**. It populates authentication state for the test. Therefore, use it to test **HTTP authorization**; use integration tests with **real signed Bearer JWTs** to test the authentication boundary.

### 6.1. A Minimal Test Controller

To keep tests independent of a database, assume a test controller returning plain strings:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class DemoOrdersController {

    @GetMapping("/public/catalog")
    String catalog() {
        return "public-catalog";
    }

    @GetMapping("/orders")
    String listOrders() {
        return "orders";
    }

    @GetMapping("/orders/{id}")
    String readOrder(@PathVariable String id) {
        return "order:" + id;
    }

    @PostMapping("/orders")
    String createOrder() {
        return "created";
    }

    @PostMapping("/orders/{id}/cancel")
    String cancelOrder(@PathVariable String id) {
        return "cancelled:" + id;
    }
}
~~~

This is **not a production controller**: it intentionally omits owner, tenant, status, or persistence checks. It merely lets tests observe that a request **cleared the HTTP authorization layer**. Data policies must be tested separately.

### 6.2. Allowed and Denied Tests

Example with **Spring Boot 3 / Spring Security 6**, JUnit Jupiter, and MockMvc:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = DemoOrdersController.class)
@Import({ApiSecurityConfig.class, HttpAuthorizationTest.TestDecoder.class})
class HttpAuthorizationTest {

    @Autowired
    MockMvc mvc;

    // Placeholder decoder solely for testing rules with simulated jwt().
    // Do not use it in tests verifying real signed JWTs.
    @TestConfiguration
    static class TestDecoder {
        @Bean
        JwtDecoder jwtDecoder() {
            return token -> {
                throw new JwtException("Real JWT validation is tested separately");
            };
        }
    }

    @Test
    void publicGetIsAllowedWithoutBearerToken() throws Exception {
        mvc.perform(get("/api/public/catalog"))
            .andExpect(status().isOk());
    }

    @Test
    void readScopeMayUseGetOrder() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void writeScopeMayCreateOrder() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isOk());
    }

    @Test
    void cancelScopeMayCancelOrder() throws Exception {
        mvc.perform(post("/api/orders/42/cancel")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.cancel"))))
            .andExpect(status().isOk());
    }

    @Test
    void protectedGetWithoutTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unrelatedScopeCannotReadOrder() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void readScopeCannotCreateOrder() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeCannotCancelOrder() throws Exception {
        mvc.perform(post("/api/orders/42/cancel")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedActionIsDeniedEvenWithValidAuthorities() throws Exception {
        mvc.perform(post("/api/orders/42/refund")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"),
                    new SimpleGrantedAuthority("SCOPE_orders.write"),
                    new SimpleGrantedAuthority("SCOPE_orders.cancel"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicPathIsNotAutomaticallyPublicForPost() throws Exception {
        mvc.perform(post("/api/public/catalog")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownSubpathIsDenied() throws Exception {
        mvc.perform(get("/api/orders/42/notes")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void pathOutsideApiIsNotUnprotected() throws Exception {
        mvc.perform(get("/internal/secrets")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().is4xxClientError());
    }
}
~~~

This example demonstrates a test suite for **specified methods/URLs**. `DemoOrdersController` and `ApiSecurityConfig` were defined earlier. `TestDecoder` fails on real string JWTs so tests never accidentally mix with signature verification; requests with `jwt()` receive pre-built authentication provided by the test harness. Because these tests supply authorities directly to `jwt()`, **configuration converting `scope` claims into authorities is not yet tested**.

`/internal/secrets` traverses the fallback chain; the exact code may be 403 per the example config. The assertion here checks **that access is not left open**, though in a system with an explicit error-code contract, assert the exact code and verify zero side effects.

### 6.3. Why Test Both `GET` and `POST` on the Same URL?

`GET /api/public/catalog` being permitted does not mean `POST /api/public/catalog` is permitted. HTTP matchers should combine **method + path**. Using a rule:

~~~java
.requestMatchers("/api/public/catalog").permitAll()
~~~

without restricting the method can open more methods than intended. Negative `POST` tests catch that.

Likewise, `POST /api/orders/{id}/cancel` does not imply `GET` or `DELETE` on that URL is allowed. Write dedicated tests for unexpected methods:

~~~java
@Test
void getCancelEndpointIsDenied() throws Exception {
    mvc.perform(get("/api/orders/42/cancel")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.cancel"))))
        .andExpect(status().isForbidden());
}
~~~

In a production API, Spring MVC might also handle `HEAD`, `OPTIONS`, or return `405 Method Not Allowed` when no handler exists. Define your expected contract and test real behavior rather than assuming every unexpected method always returns 403.

## 7. Testing Not Only Status Codes, But Also Whether Controllers Are Invoked

A stronger negative test checks beyond the response:

~~~text
Insufficient permissions -> 403
AND service.createOrder(...) was never called
AND no record was created/updated
~~~

At the web layer you can use `@MockitoBean` in Spring Framework 6.2+/compatible Spring Boot versions or `@MockBean` in earlier Spring Boot 3 versions to mock the service, then verify:

~~~java
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

// After a request blocked at the filter chain:
verify(orderService, never()).createOrder(
        org.mockito.ArgumentMatchers.any());
~~~

This is **an illustrative snippet placed inside a test mocking `orderService`**, not a standalone complete test. It reinforces an important principle: a "forbidden" outcome is trustworthy only if the request produced zero business side effects before being denied.

In systems with databases, queues, or events, integration tests should assert no writes or events occurred when authorization fails. If an HTTP error is raised **after** business logic already ran, a trailing 403 status is insufficient to protect data.

## 8. `jwt()` Is Not Equivalent to a Real Signed JWT: Testing the Authentication Boundary Separately

In the section 6 test:

~~~java
.with(jwt().authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")))
~~~

the test utility **injects an already-populated authentication with authorities** onto the request. It does not sign a JWT with a test private key, call JWKS, or run all issuer/audience/time validators like the production decoder.

Therefore, this test is solid evidence for:

- Whether a method/path requires the right authority.
- Whether the endpoint is blocked when **the simulated authentication** lacks the authority.
- `requestMatchers` ordering, `denyAll`, and filter chain selection.

Yet it **does not prove**:

- That JWTs with invalid signatures are rejected.
- That tokens from unknown issuers are rejected.
- That tokens with another API's `aud` are rejected.
- That expired JWTs are rejected.
- That mapping from `scope` or nested roles claims to `GrantedAuthority` works properly.

### 8.1. Real JWT Test Matrix

When testing the JWT decoder + `SecurityFilterChain` layer, send tokens **genuinely signed with a test key**, using a trusted mock JWKS:

| Token | JWT verification | HTTP authorization | Expected outcome |
| --- | --- | --- | --- |
| Properly signed, valid issuer/audience/time, `orders.read` scope | Succeeds | `GET /api/orders/42` allowed by scope | Passes security layer |
| Altered signature | Fails | Permissions not yet evaluated | Rejected, typically 401 |
| Signed with a private key absent from trusted JWKS | Fails | Permissions not yet evaluated | Rejected |
| Valid signature, `iss` differs from trusted issuer | Validation fails | Permissions not yet evaluated | Rejected |
| Valid signature, `aud = billing-api` | Validation fails | Permissions not yet evaluated | Rejected |
| Valid signature yet expired `exp` | Validation fails | Permissions not yet evaluated | Rejected |
| Valid JWT, `orders.write` only | Succeeds | `GET` requires `orders.read` | 403 |
| Valid JWT, `orders.read` | Succeeds | `POST /api/orders` requires `orders.write` | 403 |
| Valid JWT, right scope yet wrong owner | Succeeds | HTTP rule passes | Data policy denies |

A signed JWT test should include these pieces:

~~~text
Test-only RSA/EC signing key
  |
  +-- Private key: in test fixture only for signing JWTs
  +-- Public key: published via mock JWKS

Mock Authorization Server/JWKS
  |
  +-- trusted issuer / jwks_uri for tests

Spring Security Resource Server
  |
  +-- Real JwtDecoder
  +-- issuer/audience/time validators
  +-- Real JwtAuthenticationConverter
  +-- Real SecurityFilterChain

MockMvc or HTTP test client
  |
  +-- Authorization: Bearer <signed-JWT>
~~~

Never use production private keys as fixtures and never paste real access tokens onto token-decoding websites. You can use **Nimbus JOSE/JWT**, MockWebServer, or WireMock to sign tokens and serve public JWKs in tests. Test tokens carry valid `iss`, `aud`, and `scope`; variants alter signatures or claims to verify rejection.

### 8.2. Signed JWT Tests Must Traverse the Real Filter Chain

Pseudocode for an integration test:

~~~java
// Pseudocode: signedJwt(...) signs with a test key published by mock JWKS.
String goodToken = signedJwt(
        "trusted-test-issuer",
        "orders-api",
        "orders.read");

mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer " + goodToken))
    .andExpect(status().isOk());

String wrongAudience = signedJwt(
        "trusted-test-issuer",
        "billing-api",
        "orders.read");

mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer " + wrongAudience))
    .andExpect(status().isUnauthorized());
~~~

This is **scenario pseudocode**, requiring your project's JWT signing helper, JWKS test server, decoder, and real controllers. The core difference from `.with(jwt())` is that **the request carries the raw Bearer JWT string** so the real authentication filter and decoder process it.

### 8.3. Testing the Converter in Isolation

If the issuer places scopes in `scp` or roles in `realm_access.roles`, test:

1. Does `JwtAuthenticationConverter` convert contract claims into exact `GrantedAuthority` instances?
2. Do scopes receive the `SCOPE_` prefix? Do roles receive the `ROLE_` prefix?
3. Are unfamiliar claims or roles for other Resource Servers ignored?
4. Once the converter is wired into the chain, do HTTP rules receive the expected authorities?

**Never write HTTP tests using `jwt().authorities(...)` and conclude the production converter is definitely right**, because the test itself injected the authorities instead of the converter.

## 9. Testing Matcher Ordering and Breadth Accurately

### 9.1. Rule Order Can Change Outcomes

Example:

~~~java
// Dangerous: broad rule placed first.
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/{id}/cancel")
    .hasAuthority("SCOPE_orders.cancel")
~~~

Depending on the matcher, the first rule can match cancel requests and let callers with only `orders.read` pass. Negative tests must include:

~~~text
POST /api/orders/42/cancel + only SCOPE_orders.read
=> MUST DENY
~~~

In the clean example in section 4, each method/path is declared explicitly, avoiding such overlap. Whenever you must use wildcards, write tests for **every sensitive operation sitting beneath the wildcard**.

### 9.2. Testing Lookalike URLs and Path Normalization

Requests worth testing:

~~~text
GET /api/orders/42
GET /api/orders/42/
GET /api/orders/42/notes
GET /api/orders/42/export
GET /api/orders/42%2Fnotes
GET /api/orders//42
GET /API/orders/42
GET /api/orders/42;param=value
~~~

Not every request above is treated identically by Spring Security or the servlet container. Some are rejected immediately by the **HTTP firewall**, some normalize/route differently under Spring MVC, proxies, or path-matching settings, and some lack handlers. Testing must run against real infrastructure configuration to confirm **there is no bypass around policy**, rather than guessing fixed HTTP codes.

Points to watch closely:

- Is a **trailing slash** treated as the same route?
- Are **encoded slashes** and semicolon contents handled differently by proxy/server/firewall?
- Is URL **case sensitivity** consistent across gateway, Security, and MVC?
- Do **context path/servlet path** cause matchers to see a different path from the controller?
- If the gateway rewrites `/api/v1/orders` to `/api/orders`, at which layer do security rules apply?

A sound design writes rules against **the actual path received by `SecurityFilterChain`** and tests at that real boundary.

### 9.3. Unexpected Methods

If only `GET /api/orders/{id}` is supported, consider:

~~~text
POST /api/orders/42
PUT /api/orders/42
PATCH /api/orders/42
DELETE /api/orders/42
HEAD /api/orders/42
OPTIONS /api/orders/42
~~~

Do not apply one blanket expectation to every method. For example, `OPTIONS` may be a **CORS preflight** from a browser handled per CORS policy, while `HEAD` may relate to Spring MVC's GET-mapping behavior. What must be proven is that **an unpermitted method never executes protected data mutations**.

## 10. Multiple SecurityFilterChains: Testing Protected Zones and Missed Zones

An application might have chains:

~~~text
@Order(1): /api/**   -> Bearer JWT, scope rules
@Order(2): /admin/** -> web login, CSRF, ROLE_ADMIN
@Order(3): **        -> denyAll
~~~

Splitting into multiple chains often has valid reasons, yet requires testing:

| Path | Expected chain | Key negative test |
| --- | --- | --- |
| `/api/orders/42` | API JWT | Missing token or scope must be blocked |
| `/api/public/catalog` | API JWT | Anonymous GET works; POST is not public by default |
| `/admin/reports` | Admin chain | API JWT does not substitute for session/admin role |
| `/internal/jobs` | Matching chain or fallback | Must not bypass all chains |
| `/actuator/**` | Dedicated management policy | Sensitive endpoints not accidentally public |

When multiple chains can match, **`@Order` precedence** determines which chain is chosen first. A `/**` matcher placed too early can shadow the JWT chain. Conversely, a chain matching only `/api/**` with no fallback can miss admin paths outside the API.

**Do not test only rules inside one chain; also test the "boundaries" between chains.** If the system runs a management port/Actuator outside the application port, protection for those endpoints may live in separate configuration and requires dedicated tests.

## 11. Positive/Negative Tests Must Consider Both Authority and Identity

Holding `orders.read` does not entitle someone to view every order. In a Resource Server, **JWTs authenticate identity and scopes**, while data enforces owner/tenant/assigned groups.

Example verified token:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-A",
  "exp": 1893459600
}
~~~

Cases:

| Case | Order | Claims and scope | Expectation |
| --- | --- | --- | --- |
| D1 — valid owner | Order 42: owner `user-842`, tenant A | `orders.read`, subject `user-842` | Allowed if full policy matches |
| D2 — wrong owner | Order 43: owner `user-999`, tenant A | `orders.read`, subject `user-842` | Denied if permitted only to view own orders |
| D3 — wrong tenant | Order 44: tenant B | `orders.read`, tenant A | Denied |
| D4 — support role in right tenant | Order 44: tenant A | Valid support role/permission | Allowed when assigned properly |
| D5 — service token, not a user | Order 42: owner `user-842` | `client_credentials` with service `sub` | Never auto-applies user privileges |

One way to structure this:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') and " +
    "@orderAccess.canRead(authentication, #id)")
public OrderDto getOrder(String id) {
    return orders.findDtoById(id)
            .orElseThrow(OrderNotFoundException::new);
}
~~~

`orderAccess` and `orders` are illustrative business components. `canRead(...)` must use **verified** identity/tenant and server-side record data, never merely comparing a URL parameter against a client-set header. `@PreAuthorize` requires `@EnableMethodSecurity` and executes through Spring proxies under compatible configuration.

Negative tests here should check **same scope, different resource ownership**. That catches IDOR/BOLA vulnerabilities (insecure direct object reference / broken object level authorization), which cannot be detected merely by testing `hasAuthority("SCOPE_orders.read")`.

## 12. Testing Principal and Role Variants

Not every access token represents an end user. Under `client_credentials`, a token may represent a service; in multi-tenant systems, the same role may be valid in tenant A yet invalid in tenant B.

Design additional cases:

- User token has read scope yet lacks required business role/permission → **deny**.
- User token has scope and permission yet does not belong to the object's tenant → **deny**.
- Service token has dedicated internal scope calling the right service endpoint → **allow** if service policy permits.
- Service token sent to a user-only endpoint → **deny**.
- Token from another issuer with identical `sub` and `roles` → **deny** if not a trusted issuer.
- Token carrying another resource's role, e.g., `billing_admin`, calling the Orders API → **grants no Orders permissions**.

If the Resource Server uses a custom `JwtAuthenticationConverter`, write dedicated role/permission mapping tests: `hasRole("ORDER_SUPPORT")` typically checks `ROLE_ORDER_SUPPORT`; `hasAuthority("SCOPE_orders.read")` checks the `SCOPE_`-prefixed authority. A single typo or missing prefix can block all valid requests—or worse, stop the rule from enforcing where needed.

## 13. Testing CORS and CSRF Without Accidentally Opening Authorization

### 13.1. CORS Preflight Differs from Real API Requests

Browsers can send:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

A CORS preflight does not mean "the user is allowed to create an order." It asks whether the server permits the browser to send a cross-origin request. If the system supports CORS, configure `http.cors(...)` with an appropriate `CorsConfigurationSource` and test:

1. Allowed origin + valid preflight → CORS response matches contract.
2. Disallowed origin → cross-origin access is not granted.
3. **Actual POST request** after preflight still requires a Bearer token and `orders.write`.

**CORS does not replace authentication/authorization.** An API with properly configured CORS must still reject clients lacking scopes. Never fix preflight issues by adding `permitAll("/api/**")`.

### 13.2. CSRF Depends on the Credential Mechanism

The `csrf(AbstractHttpConfigurer::disable)` example in section 4 fits the assumption of a **REST API using only Bearer tokens in the Authorization header**, without session-cookie authentication. If the same app has cookie-based web login, configure a separate CSRF policy for that flow.

Negative tests for HTTP methods and permissions remain essential even when CSRF is disabled on the API chain. **Disabling CSRF does not mean allowing POST/DELETE unconditionally**; scope rules and business policies must still block unauthorized requests.

## 14. Testing Routes Added Later

HTTP authorization risks frequently emerge as an application evolves. Initially the API has only:

~~~text
GET  /api/orders
GET  /api/orders/{id}
POST /api/orders
~~~

Later the business team adds:

~~~text
POST /api/orders/{id}/refund
GET  /api/orders/{id}/export
DELETE /api/orders/{id}
~~~

If configuration uses an overly broad wildcard like:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

then refund/delete endpoints could be guarded by an inappropriate read scope or receive unintended privilege levels. With **default deny**, newly added endpoints without rules are blocked until the team defines permissions and tests for them.

One strategy is maintaining an **endpoint/contract catalog**:

~~~yaml
# Illustrative policy document, not YAML automatically read by Spring.
endpoints:
  - method: GET
    path: /api/public/catalog
    access: public
  - method: GET
    path: /api/orders/{id}
    required_scope: orders.read
    data_policy: owner_or_assigned_support
  - method: POST
    path: /api/orders/{id}/cancel
    required_scope: orders.cancel
    data_policy: owner_and_cancellable_status
  - method: POST
    path: /api/orders/{id}/refund
    access: deny_until_approved
default_access: deny
~~~

Whenever adding a route, code reviews should require **at least one positive case and key negative cases**. For sensitive operations, also test that zero side effects happen when denied.

## 15. Testing Mistakes That Create a False Sense of Security

### "One admin token can call every endpoint, so security works"

Testing only with a high-privilege token fails to prove least privilege. It cannot catch a read scope canceling orders, or a tenant-A user reading tenant B. You need **lower-privilege** tokens for negative cases.

### "Having `anyRequest().authenticated()` is good enough"

This rule requires only that the caller be authenticated; it does not check scopes, roles, or tenants. In an API requiring per-operation permissions, `authenticated()` can be far too broad. Use it only when the contract truly requires login alone; never use it instead of `hasAuthority(...)` across all actions.

### "Having `permitAll()` on a health endpoint means all methods should pass"

If only `GET` is meant to be public, evaluate other methods separately. A method-unrestricted matcher can accidentally open `POST`.

### "Tests using `jwt()` pass, meaning JWT signatures are verified"

No. `jwt()` mocks authentication; separate signed-JWT integration tests are needed for signatures/JWKS/issuer/audience/time.

### "MockMvc does not need Spring Security filters"

If Spring Security filters are not attached to MockMvc, tests can return 200 even when production security config is broken. When using `@WebMvcTest`/`@AutoConfigureMockMvc` with Spring Security, verify the filter chain is loaded and include a tokenless negative test proving it runs.

### "A 403 response proves the controller did not run"

Not guaranteed if an exception handler or business logic returns 403 **after side effects**. Tests for sensitive operations should verify the service was never invoked or data remained unchanged.

### "Matching the URL is enough; HTTP method doesn't matter"

Wrong. `GET`, `POST`, and `DELETE` carry different business semantics and risk levels; broad path-only matchers can bypass method-level authorization.

### "A `denyAll` at the end of the API chain protects the whole application"

Not if the chain matches only `/api/**` and has no fallback. Test paths outside `securityMatcher`.

### "Endpoints without a controller don't need tests"

A route currently returning 404 may gain a controller later. Negative-space tests and default deny protect against new routes opening by accident.

### "The right scope means access to any record"

Wrong. HTTP-layer scopes typically authorize an operation type; owner, tenant, assignment, and state must be verified at the business layer.

## 16. Designing a Concise Yet Multi-Dimensional Test Suite

A maintainable test suite structure:

~~~text
src/test/java/...
  HttpAuthorizationTest
    - public routes
    - allowed routes by scope
    - missing token
    - insufficient scope
    - wrong HTTP method
    - unexpected URL
    - fallback chain

  JwtVerificationIntegrationTest
    - trusted signature / issuer / audience
    - bad signature
    - expired / nbf not reached
    - wrong issuer / audience / token type
    - custom authority converter

  OrderAccessPolicyTest
    - own order
    - other owner's order
    - other tenant
    - support role and assignment
    - service principal cannot impersonate user

  OrderWriteSecurityIntegrationTest
    - authorized write has intended side effect
    - denied write has zero side effects
~~~

**Not every project must split into these exact four classes.** The idea is keeping boundaries clear: HTTP matchers, token validation, authority mapping, and data-level permissions. When a test fails, the team immediately knows which layer to inspect.

### 16.1. Minimum Test Matrix for a Sensitive Endpoint

Example `POST /api/orders/{id}/cancel`:

| Token/caller state | Order | Expected response/outcome |
| --- | --- | --- |
| No token | Any | Authentication rejects |
| JWT bad signature | Any | Authentication rejects |
| Valid JWT with wrong audience | Any | Authentication rejects |
| Valid JWT, `orders.read` only | Any | 403, not cancelled |
| Valid JWT, `orders.write` only | Any | 403, not cancelled |
| Valid JWT, has `orders.cancel` | Order not owned/permitted | 403/404 per policy, not cancelled |
| Valid JWT, has `orders.cancel` | Shipped order, non-cancellable | Rejected per policy, not cancelled |
| Valid JWT, has `orders.cancel` | Permitted order in cancellable state | Cancelled once per business rules |
| Valid JWT, `orders.cancel` | URL `/api/orders/{id}/refund` | Default deny, no refund |
| Valid JWT, `orders.cancel` | `GET` method on cancel path | Cancellation does not execute |

From here, extend the pattern to any sensitive endpoint. The big difference from happy-path-only testing is that **every permission has negative boundaries that must be proven**.

### 16.2. Checklist When Reviewing Pull Requests That Change Authorization

1. Does the new endpoint have an explicit **method + path** rule?
2. Does default `denyAll()` block out-of-contract requests?
3. Do paths outside `securityMatcher` have a protective chain?
4. Do public endpoint tests prove anonymous callers **get in** and other methods **are not opened automatically**?
5. Do protected endpoint tests cover both **sufficient scope → allow** and **wrong/missing scope → deny**?
6. Are missing Bearer tokens tested to fail at authentication?
7. Do wrong issuer/audience/signature/expired JWT tests run **real signed tokens** through the decoder?
8. Do authority converter tests accurately verify `scope`/roles/permissions claims?
9. Do per-object tenant/owner tests block horizontal privilege escalation?
10. Do denied-operation tests verify zero side effects occurred?
11. Are trailing slashes, special methods, gateway rewrites, and CORS tested against real infrastructure?
12. In production, are logs/correlation IDs sufficient for diagnostics without logging Bearer tokens or secrets?

## 17. Case Studies

**Scenario 1:** The API has `GET /api/orders/**` requiring `orders.read`. A developer adds `GET /api/orders/42/export`. Testing with an `orders.read` token returns 200. Is this secure enough?

**No.** The export endpoint may contain more sensitive data than reading a single order; define a separate scope/policy if needed. Negative tests catch overly broad matchers granting unintended permissions.

**Scenario 2:** Testing `GET /api/orders/42` with `jwt().authorities("SCOPE_orders.read")` passes. Does that prove tokens with the wrong audience will be rejected?

**No.** `jwt()` bypasses the real `JwtDecoder`. Write integration tests with a real signed Bearer JWT and a wrong audience.

**Scenario 3:** A valid token carrying `orders.write` is sent to `GET /api/orders/42`. What is the contract outcome?

**403** if the API requires and issues `orders.read` separately for the GET endpoint, with no rule saying `orders.write` includes `orders.read`. This test catches overly broad scope assumptions.

**Scenario 4:** Anonymous `GET /api/public/catalog` returns 200, yet `POST /api/public/catalog` also returns 200. Why is this dangerous?

The `permitAll()` rule may apply by path without restricting the HTTP method. Fix the matcher and add negative tests for POST/PUT/DELETE.

**Scenario 5:** `GET /internal/secrets` does not match `securityMatcher("/api/**")`. Is it guaranteed to be blocked?

**No, if no other filter chain exists.** Add a fallback/default chain or equivalent protection, and test paths outside the API.

**Scenario 6:** A user with `orders.read` can call the controller to view order 42, yet order 42 belongs to another tenant. HTTP scope tests pass; can we conclude authorization is safe?

**No.** You need object-permission tests checking owner/tenant/assignment on real records and denying out-of-scope data.

**Scenario 7:** An order-cancellation request returns 403, yet database logs show the order status changed to `CANCELLED`. Can the negative test be considered passing?

**No.** The side effect occurred before denial. Move authorization ahead of the mutation and add assertions that zero writes/events happen when denied.

---

## Conclusion

Testing **HTTP authorization** in a Spring Security Resource Server must prove **both directions**: valid requests with the right method, path, and scope **pass through** the security layer; requests missing authentication, carrying bad tokens, lacking authorities, using wrong methods, hitting unlisted paths, or violating resource permissions **are denied**.

A reliable strategy combines **specific method + path rules**, `anyRequest().denyAll()`, a fallback protecting paths outside `securityMatcher`, MockMvc suites with both positive and negative cases, **real signed Bearer JWT** integration tests for `JwtDecoder`, and ownership/tenant tests asserting **zero side effects on denial**. `jwt()` is a great tool for testing authority rules, yet it does not replace JWT verification testing. The ultimate goal is not "some request returns 200," but that **only contract-compliant requests can trigger protected business actions**.
