# Mocking Authentication and Authorization in Producer Tests

An API can return the right JSON and HTTP status for a valid user while still **being accessible without a token**, **returning data to someone without sufficient permissions**, or **allowing access to another tenant's data**. If a producer contract test only sets up a controller without security filters, the test can pass even though the real application has a critical security flaw.

**Spring Cloud Contract** allows describing HTTP or message behavior using **Groovy/YAML DSL**, generating producer-side tests, packaging stubs for consumers to use with **Stub Runner**, and integrating these steps into **CI** to detect incompatible API changes. In the **SPRING_CLOUD_CONTRACT** learning path, this lesson belongs to the **Contract Security** chapter, covering the topic **Mocking authentication and authorization in producer tests**.

The goal is not to build a fake identity system with every production feature. The goal is to **simulate in a controlled way the identities and permissions needed for contract scenarios**, while still verifying that **the producer's real Spring Security and authorization logic** produce the correct outcome. This lesson also clarifies what **cannot be proven** with a fake token, why `401` differs from `403`, how to avoid leaking secrets in the stubs JAR, and how to verify results using generated producer tests.

## 1. How do authentication and authorization differ?

The two concepts are related but not identical:

- **Authentication:** who or which service is the request coming from? For example, validating a bearer token and extracting the identity `checkout-service`.
- **Authorization:** what is the authenticated identity **allowed to do, and on which resources**? For example, only a principal with the `orders.read` scope may read from Order Service, and only the tenant that owns the order may view that data.

An HTTP call can pass through multiple layers:

```mermaid
flowchart TD
    A[Checkout sends GET /api/orders/ORDER-42] --> B[Spring Security filter chain]
    B --> C{Can the token be authenticated?}
    C -- No --> D[401 Unauthorized]
    C -- Yes --> E{Does principal have required scope/role?}
    E -- No --> F[403 Forbidden]
    E -- Yes --> G{Allowed to access this resource/tenant?}
    G -- No --> H[403 or 404 per policy]
    G -- Yes --> I[Controller / Service / Repository]
    I --> J[200 + JSON per contract]
```

**A valid token does not mean sufficient permissions.** A token with a valid signature that lacks the `orders.read` scope must still be rejected. Conversely, a token containing the desired scope string that is not authenticated cannot be treated as a valid identity in production.

### 1.1. Common cases an API must protect

| Scenario | Input | Typical expected result | What to verify |
|---|---|---|---|
| Authenticated, sufficient permissions | Valid bearer token with `orders.read` | `200 OK` | Response matches contract |
| No credentials | Missing `Authorization` | `401 Unauthorized` | Cannot read data |
| Wrong or unaccepted token | `Bearer invalid-token` | `401 Unauthorized` | Authentication is not bypassed |
| Valid token, missing scope | Token has `orders.audit` | `403 Forbidden` | Authorization rule is enforced |
| Has scope, does not own order | Different tenant | `403` or `404` per API policy | No cross-tenant data leak |
| Authorized but resource does not exist | `ORDER-MISSING` | `404 Not Found` | Business error matches schema |
| POST missing CSRF in cookie-session app | Authenticated session, missing CSRF token | May be `403` | Must distinguish CSRF error from missing role |
| Request has malformed header | `Authorization: something` | Usually `401` or error per security stack | Must not be accepted unintentionally |

**Do not assume** an API always returns these exact codes across every framework or configuration. You must read the producer's policy and the HTTP semantics agreed upon by the team. When hiding resource existence is required, an API may intentionally return `404` instead of `403` for unauthorized callers; tests must follow the published policy.

## 2. Scope of security in producer contract tests

A producer contract test can prove:

1. A request with valid credentials, permissions, and fixtures returns `200` with the committed body.
2. An unauthenticated request is rejected according to policy.
3. A request with a valid identity but insufficient permissions receives `403`.
4. A request with the scope but without permission for a specific resource does not leak data.
5. Published error status, headers, body, and media type remain stable.
6. Generated tests use **the real security filter chain and application code**, not just a mock controller.
7. Unexpected producer changes to security rules cause the relevant contracts to fail.

Conversely, a test using a fake `JwtDecoder` **does not prove**:

- JWT signatures are verified with production private/public keys.
- JWK key rotation, issuer discovery, audience validation, and revocation work properly.
- TLS, mTLS, ingress proxies, or API gateways are configured securely.
- OAuth2 authorization code/client credentials flows work with a real Identity Provider.
- Browser session, CSRF, CORS, or cookie policies have been fully verified.
- All resources and all role/permission combinations not described in the contract are safe.

Those parts require appropriate **security integration tests**, authentication provider tests, authorization policy tests, API gateway tests, or penetration testing.

### 2.1. Boundaries of the three verification layers

| Layer | How it tests | Value | Limitation |
|---|---|---|---|
| **Producer contract test** | Generated test sends requests with test credentials to producer context | Protects committed status/header/body and authorization behavior | Covers only described cases |
| **Security integration test** | Token verified via real decoder/JWK/test IdP, proxy, or gateway | Verifies authn mechanisms more end-to-end | Costs infrastructure and time |
| **Consumer Stub Runner test** | Consumer sends credentials to WireMock stub and reads response | Verifies client sends header and handles `401/403` properly | Stub does not verify JWTs like a real IdP/producer |

Each layer should have a clear purpose. Do not treat a stub mapping `Authorization` as an actual authentication mechanism.

## 3. Running example: Checkout calls Order Service

Suppose Checkout is a consumer calling:

```http
GET /api/orders/ORDER-42
Accept: application/json
Authorization: Bearer contract-reader-token
```

When credentials and permissions match:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"ORDER-42","status":"PAID","totalAmount":125000}
```

In the **test environment**, we define two fake tokens with consistent semantics:

| Fake token | Principal | Scope | Tenant | Purpose |
|---|---|---|---|---|
| `contract-reader-token` | `checkout-contract-test` | `orders.read` | `TENANT-42` | Verify `200` |
| `contract-auditor-token` | `audit-contract-test` | `orders.audit` | `TENANT-42` | Verify `403` due to missing scope |
| No header | Anonymous | None | None | Verify `401` |
| `unknown-contract-token` | No accepted principal | None | None | Verify rejected token |

**These are not real JWTs** and have no valid signature from any Identity Provider. These strings are purely fixture IDs so that a `JwtDecoder` in the **Spring test context** can return a test principal or reject credentials.

In production, the system must use real bearer tokens, verified by issuer, audience, expiration, signature, and other architectural requirements.

### 3.1. Four independent contract cases

| Case | URL | Authorization | Expected |
|---|---|---|---|
| Happy path | `/api/orders/ORDER-42` | `Bearer contract-reader-token` | `200` + JSON |
| Unauthenticated | `/api/orders/ORDER-42` | None | `401` |
| Insufficient permissions | `/api/orders/ORDER-42` | `Bearer contract-auditor-token` | `403` |
| Not found | `/api/orders/ORDER-MISSING` | `Bearer contract-reader-token` | `404` + error body |

Using the same URL for `200/401/403` is **intentional** to test the effect of credentials. However, when these mappings are packaged into stubs, you must ensure request matchers distinguish between **header present, absent, or different values**. If the `401` mapping is too broad, consumer tests might receive `401` even when sending a valid token.

## 4. Groovy DSL contract: read permission returns `200`

Example file `src/test/resources/contracts/checkout/get_paid_order_authorized.groovy`:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'checkout_get_paid_order_authorized_200'
    description 'Checkout with scope orders.read can read the order'

    request {
        method GET()
        url '/api/orders/ORDER-42'
        headers {
            header 'Accept', 'application/json'
            header 'Authorization', 'Bearer contract-reader-token'
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 'ORDER-42',
            status: 'PAID',
            totalAmount: 125000
        )
    }
}
```

This is an **HTTP-level contract**. The Verifier generates a test that sends an HTTP request with the defined headers to the producer test setup, then asserts the status and body. However, the test **only proves authorization is correct** if the corresponding filter chain or authorization interceptor actually runs.

If the base test uses a mock controller that always returns `200`, the contract will pass even if production security rules are deleted. That is a **false positive**.

### 4.1. Sample tokens are not secrets

`contract-reader-token` must not map to a real username/password, production API key, or any user's token. Do not store real OAuth2 tokens in Groovy/YAML DSL because:

- Contracts may be committed to Git.
- Generated tests print/log request data.
- The stubs JAR may be published to many consumers.
- WireMock request journals may retain headers.
- CI artifacts often have long retention lifecycles.

To test the same set of credentials across multiple modules, choose **fixed, non-sensitive test strings** and maintain consistent conventions in the test environment.

## 5. YAML contract: missing authentication returns `401`

File `src/test/resources/contracts/checkout/get_paid_order_unauthenticated.yml`:

```yaml
name: checkout_get_paid_order_unauthenticated_401
description: Request without bearer token must be rejected
request:
  method: GET
  url: /api/orders/ORDER-42
  headers:
    Accept: application/json
response:
  status: 401
```

Characteristics:

- No `Authorization` header in the request.
- Expected response is `401 Unauthorized`.
- Do not assume the producer always returns a JSON error body.
- Only add `WWW-Authenticate` to the contract if the header/value is genuinely committed by the API and the generated assertion checks it with appropriate semantics.

**Important point:** a contract request that "does not declare `Authorization`" **does not automatically express a matcher forbidding all Authorization headers** in the generated WireMock mapping. For producer verification, the generated test typically sends only the declared headers, so it can test missing credentials. But for consumer stub tests, a mapping without an Authorization matcher might accidentally **match requests that include a bearer token**.

If consumer tests need to share `200` and `401` mappings on the same URL, you must inspect the actual generated mapping, apply an **absent-header matcher**/priority appropriate for your WireMock version, or use isolated scenarios. Do not assume that omitting a header in a contract automatically makes the mapping accept only anonymous requests.

### 5.1. `WWW-Authenticate` in 401 errors

In many Bearer resource servers, a `401` response includes the header:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Depending on the invalid token case, the header may contain additional `error` or metadata per the Bearer standard. Do not hardcode a single string for all authentication errors if the framework has multiple error cases. When this header is part of the interface used by the consumer, define the corresponding assertion per your supported Contract DSL/version or an explicit producer integration test.

## 6. YAML contract: authenticated but missing permissions returns `403`

File `src/test/resources/contracts/checkout/get_paid_order_forbidden.yml`:

```yaml
name: checkout_get_paid_order_forbidden_403
description: Token can be authenticated but lacks scope orders.read
request:
  method: GET
  url: /api/orders/ORDER-42
  headers:
    Accept: application/json
    Authorization: 'Bearer contract-auditor-token'
response:
  status: 403
```

This scenario is only meaningful if:

1. `contract-auditor-token` is **accepted** by the test decoder.
2. The decoder produces a valid principal with the `orders.audit` scope.
3. The Spring Security filter chain/authorization manager requires `orders.read`.
4. The request passes through the real filter chain.
5. The result is `403` due to missing permissions, **not `401` due to an invalid token**.

If the decoder rejects the auditor token, the generated test will receive `401` and fail, yet the cause is **not authorization**. Therefore, fixtures must clearly distinguish between "invalid token" and "valid token lacking scope".

### 6.1. Do not use `403` as a generic name for every security error

- `401`: authentication is missing or not accepted per API policy.
- `403`: the principal is authenticated but **not permitted** to perform the action, or is blocked by another policy such as CSRF.
- `404`: the resource may not exist, or the API intentionally hides resources the caller is not allowed to know about.

A `403` can be caused by **CSRF protection**, method security, or a gateway policy. Tests need to know **which policy** blocked the request before drawing conclusions.

## 7. Additional contract: authorized but resource does not exist

Illustrative Groovy file:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'checkout_get_missing_order_authorized_404'

    request {
        method GET()
        url '/api/orders/ORDER-MISSING'
        headers {
            header 'Accept', 'application/json'
            header 'Authorization', 'Bearer contract-reader-token'
        }
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND'
        )
    }
}
```

During verification, the base fixture must ensure `ORDER-MISSING` does not exist and the token is accepted. If the test receives `401`, the bug is in the authentication setup; if it receives `403`, it may be authorization; if it receives `404` with a different body, you need to distinguish a business error from an unmatched route.

This scenario protects the boundary between **authorized access** and **failed business resource lookup**.

## 8. Producer Spring Security configuration that must be tested

Suppose Order Service is a Spring Boot MVC app using OAuth2 Resource Server and security rules:

- All `GET /api/orders/**` require authority `SCOPE_orders.read`.
- Other APIs require authentication per policy.
- JWT bearer tokens are processed by Spring Security.
- The real controller/service is responsible for looking up the order and returning the DTO.

A minimal **illustrative** configuration:

```java
package com.example.order.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orders/**"
                ).hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

For this configuration to take effect, the producer must have compatible Spring Security and OAuth2 Resource Server dependencies. For stateless bearer-token APIs, `POST/PUT/DELETE` may be affected by CSRF if a specific security configuration has not been designed yet; this example only uses `GET` so disabling CSRF is not covered.

**Do not copy `csrf().disable()` into every application just to make tests pass.** If an API uses browser sessions/cookies, removing CSRF protection can create a vulnerability. How CSRF is handled must be based on the threat model and actual authentication type.

### 8.1. Scope and authority do not share the same name

A JWT has claims:

```json
{
  "sub": "checkout-contract-test",
  "scope": "orders.read",
  "tenant_id": "TENANT-42"
}
```

In Spring Security Resource Server's default conversion, the `orders.read` scope typically becomes the authority:

```text
SCOPE_orders.read
```

Therefore `hasAuthority("SCOPE_orders.read")` must match the converter in use. If the project has a custom `JwtAuthenticationConverter`, the prefix or claim extraction may differ; inspect the runtime test configuration instead of inferring from the token string.

### 8.2. Role differs from permission and scope

| Level | Example | When used |
|---|---|---|
| Role | `ROLE_ADMIN` | User group permissions |
| OAuth2 scope | `orders.read` | Client/token capability |
| Authority in Spring Security | `SCOPE_orders.read` | `hasAuthority` rule |
| Business permission | `CAN_READ_ORDER` | Application rule per resource |
| Tenant ownership | `TENANT-42` | Prevent cross-tenant access |
| Resource ownership | `order.ownerId` | Check principal owns resource |

An `ADMIN` role does not automatically include every scope unless the application configures a mapping. An `orders.read` scope also does not automatically allow reading **all tenants**. Business rules must be implemented separately.

## 9. Producer test base: keep the filter chain, mock the JWT decoder

This is the core of the lesson.

We want generated contract tests to send HTTP requests normally through **Spring MockMvc** and the real security filters. However, in CI, we do not want to depend on an external Identity Provider just to obtain real tokens. One approach is to replace **only the JwtDecoder in the test context** with a decoder that controls fixtures:

- `contract-reader-token` → principal with scope `orders.read`.
- `contract-auditor-token` → principal with scope `orders.audit`.
- Any other token → authentication exception.
- Missing token → Spring Security bearer filter handles anonymous/401.
- **SecurityFilterChain remains intact** to enforce authorization.

An illustrative base test class:

```java
package com.example.order.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
@Import(OrderContractTestBase.ContractJwtDecoderConfig.class)
public abstract class OrderContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderContractFixture fixture;

    @BeforeEach
    protected void beforeContractTest() {
        fixture.resetOrders();
        fixture.insertPaidOrder(
            "ORDER-42",
            "TENANT-42",
            125000
        );
        fixture.ensureAbsent("ORDER-MISSING");

        RestAssuredMockMvc.mockMvc(mockMvc);
    }

    @TestConfiguration
    static class ContractJwtDecoderConfig {

        @Bean
        @Primary
        JwtDecoder contractJwtDecoder() {
            return token -> {
                final String scope;
                final String subject;

                if ("contract-reader-token".equals(token)) {
                    scope = "orders.read";
                    subject = "checkout-contract-test";
                } else if ("contract-auditor-token".equals(token)) {
                    scope = "orders.audit";
                    subject = "audit-contract-test";
                } else {
                    throw new BadJwtException(
                        "Token not accepted by contract test decoder"
                    );
                }

                return Jwt.withTokenValue(token)
                    .header("alg", "RS256")
                    .subject(subject)
                    .claim("scope", scope)
                    .claim("tenant_id", "TENANT-42")
                    .issuedAt(Instant.parse("2025-01-01T00:00:00Z"))
                    .expiresAt(Instant.parse("2035-01-01T00:00:00Z"))
                    .build();
            };
        }
    }
}
```

**Learning example requiring integration into a real project:**

- `OrderContractFixture` is a helper implemented by the producer, not built into Spring Cloud Contract.
- The `JwtDecoder` test double accepts **fake strings** and does not verify JWT signatures, issuer, audience, or key rotation.
- `@Primary` helps the test context prioritize this decoder if multiple beans exist; also ensure a second decoder is not unexpectedly initialized from issuer-uri/JWK discovery configuration.
- The test profile must be isolated from production deployment; the fake decoder must not enter the main source set or runtime.
- `RestAssuredMockMvc.mockMvc(mockMvc)` configures the adapter used in generated tests in `MOCKMVC` mode; other modes require different setup.
- The `2035` expiration is an illustrative fixture and is meaningless for real expiry checks. If you need to test expiration, use a real decoder/validator in a **security integration test**.
- The code requires compatible Spring Security OAuth2 Resource Server, Spring Test, RestAssured MockMvc, and Spring Cloud Contract Verifier dependencies.

### 9.1. A fake decoder is an intentional substitution point

Look at the request path:

```mermaid
flowchart LR
    A[Generated producer test] --> B[RestAssuredMockMvc]
    B --> C[MockMvc + security filters]
    C --> D[BearerTokenAuthenticationFilter]
    D --> E[Test-only JwtDecoder]
    E --> F[Spring Security authorities]
    F --> G[AuthorizationManager / method security]
    G --> H[Real controller + real service]
    H --> I[HTTP response verified]
```

We **do not mock the entire filter chain**, do not mock the controller to return canned JSON, and do not set a global `SecurityContext` for all tests. We only shorten the cryptographic token verification step to test contract behaviors related to authentication outcomes and authorization.

### 9.2. Why not use real tokens?

A real token from an Identity Provider can:

- Expire after a few minutes, making CI flaky.
- Require network calls to an IdP or JWKS endpoint.
- Be issued with permissions/tenants that are unstable across environments.
- Leak into source code, test reports, logs, stubs archives, or request journals.
- Make producer tests depend on state outside the API implementation.

**Secret-free test fixtures** are better for repeatable contract tests. However, a separate integration suite is still needed to validate real JWT/OAuth2 mechanisms.

### 9.3. Do not disable all of Spring Security in contract tests

A dangerous approach:

```java
@AutoConfigureMockMvc(addFilters = false)
```

If filters are turned off, requests without a token can go straight to the controller. Worse yet: if the team only creates a `200` contract with a token, the generated test still passes even though that header is never checked.

Similar approaches requiring caution:

- `MockMvcBuilders.standaloneSetup(controller)` without adding security filters.
- Test profile using `permitAll()` for `/api/**`.
- `@WithMockUser` applied to the entire base class, giving even anonymous tests a principal.
- Mocking `OrderAuthorizationService.canRead()` to always return true.
- Stubbing the controller/service to return `200` without going through the real implementation.

**A good mutation test:** temporarily delete or change a security rule on an experimental branch and confirm that the appropriate generated tests fail. If they do not fail, the tests are not protecting permissions as expected.

## 10. How do `@WithMockUser` and `jwt()` help, and where are their limits?

Spring Security Test provides utilities like `@WithMockUser`, `user()`, and `jwt()`. They are very useful, but not always suitable for testing **HTTP bearer authentication** through contracts.

### 10.1. `@WithMockUser` sets the SecurityContext, not a real bearer token

Example:

```java
@WithMockUser(
    username = "reader",
    authorities = "SCOPE_orders.read"
)
@Test
void canReadOrder() {
    // ...
}
```

This is useful when testing business authorization or a controller with a pre-existing principal. It **does not prove**:

- The `Authorization` request header is parsed properly.
- The JWT decoder rejects forged tokens.
- Issuer/audience/signature are verified.
- Missing the Authorization header causes a 401.

Do not apply `@WithMockUser` to all generated tests in the base class if there are **unauthenticated** contract cases; a pre-populated fake principal can prevent `401` from being tested properly.

### 10.2. The `jwt()` request post-processor

A manually written MockMvc test can use:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void readerWithScopeCanAccess() throws Exception {
    mockMvc.perform(
        get("/api/orders/ORDER-42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            ))
    ).andExpect(status().isOk());
}
```

`jwt()` sets the authentication object on the MockMvc request; it typically **bypasses the JWT decoder** rather than sending an actual bearer token for the decoder to parse. It is a good tool for **authorization rule tests**, but does not itself verify authentication filters or token parsing.

The snippet above is **illustrative** and requires the appropriate JUnit, MockMvc, `SimpleGrantedAuthority`, and Spring Security Test imports.

### 10.3. When to choose which approach?

| Setup approach | Goal | Limitation |
|---|---|---|
| `@WithMockUser` | Unit/controller/method-security test with a pre-set principal | Does not test Authorization header/token |
| `jwt()` request post-processor | MockMvc authorization test by claims/authorities | Does not test JWT signature/decoder |
| Test `JwtDecoder` + real filter chain | Producer contract tests with fake Bearer header and real authorization | Does not test token cryptography |
| Local/real IdP/JWKS integration test | Signature, issuer, audience, expiry, key rotation | Costs infrastructure/test setup |
| Stub Runner/WireMock | Consumer sends header and handles stub response | No production auth enforcement |

Choose the **smallest substitution point** that satisfies the test objective. The deeper you mock into the authorization policy, the easier it is for tests to skip the very behavior you need to protect.

## 11. Is `@WebMvcTest` enough?

`@WebMvcTest` typically loads only a web-layer slice, which can suit fast controller contract tests. However, when a project has a custom `SecurityFilterChain`, method security, tenant policies, or complex dependencies, a slice test may fail to load everything production uses.

Some risks:

- Security configuration is unintentionally excluded from the slice.
- The `OrderAccessPolicy` bean is not loaded; the test mocks it and accidentally always allows access.
- Method security proxies do not behave identically to the full application.
- Exception handlers, filters, or argument resolvers differ from production.
- A mock controller returns data without checking database owner/tenant.

You can use `@WebMvcTest` **if you have proven** the slice includes the filters and rules to verify. For security contracts involving data/tenants, `@SpringBootTest` combined with `@AutoConfigureMockMvc(addFilters=true)` usually stays closer to integration behavior, though it runs slower.

**No single annotation guarantees safety on its own.** You must inspect the generated test source and actual behavior when testing missing tokens or missing scopes.

## 12. Example standalone verification with MockMvc before running Verifier

Before running the generated contract suite, you can write a JUnit test to verify the exact setup being used:

```java
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void anonymousRequestIsRejected() throws Exception {
    mockMvc.perform(
        get("/api/orders/ORDER-42")
            .header("Accept", "application/json")
    ).andExpect(status().isUnauthorized());
}

@Test
void auditorTokenIsForbidden() throws Exception {
    mockMvc.perform(
        get("/api/orders/ORDER-42")
            .header("Authorization",
                "Bearer contract-auditor-token")
    ).andExpect(status().isForbidden());
}

@Test
void readerTokenIsAllowed() throws Exception {
    mockMvc.perform(
        get("/api/orders/ORDER-42")
            .header("Authorization",
                "Bearer contract-reader-token")
    ).andExpect(status().isOk());
}
```

These are **test methods to place inside a JUnit class with a Spring context and injected MockMvc**, not a standalone compilable file. They verify the test decoder + security filter chain before blaming the Contract DSL.

If an anonymous request unexpectedly returns `200`, stop and investigate whether the filter chain is applied rather than rewriting the `401` contract to `200` to make the test pass.

### 12.1. With an OAuth2 resource server, where do 401 and 403 happen?

One way to visualize it:

- Missing bearer token: the request hits the auth entry point/challenge and returns `401` when the endpoint requires authentication.
- Bearer token rejected by decoder: authentication fails, typically `401`.
- Bearer token accepted by decoder but missing scope: request is authenticated, authorization manager returns `403`.
- Sufficient scope but business policy denies: may be `403` or `404` per resource-level policy.

**Do not return `500` because a JWT lacks permissions.** Security exception mappings should be configured/tested separately so a routine failure does not turn into an internal server error.

## 13. Tenant-level and per-resource authorization

An HTTP `403` from a missing scope is only a coarse check. In a multi-tenant system, a principal with `orders.read` may only be allowed to view **orders belonging to its own tenant**.

Example:

| Order ID | Owning tenant | Reader tenant | Result |
|---|---|---|---|
| `ORDER-42` | `TENANT-42` | `TENANT-42` | `200` |
| `ORDER-99` | `TENANT-99` | `TENANT-42` | `403` or `404` per policy |
| `ORDER-MISSING` | Does not exist | `TENANT-42` | `404` |

If policy permits hiding resources outside the tenant, a `404` response may be chosen to avoid revealing that the ID exists. **The contract must reflect a reviewed design decision**, not use WireMock's default `404` as security evidence.

### 13.1. Method security can enforce business policies

Example service method:

```java
@PreAuthorize("@orderAccessPolicy.canRead(authentication, #orderId)")
public OrderDto getOrder(String orderId) {
    return orderRepository.findById(orderId)
        .map(orderMapper::toDto)
        .orElseThrow(OrderNotFoundException::new);
}
```

This snippet only works as intended if:

- `@EnableMethodSecurity` is enabled when using method authorization per your Spring Security version.
- The `orderAccessPolicy` bean is the real implementation or a test double with explicit data.
- The method security proxy/interceptor is actually applied.
- `orderRepository` and `orderMapper` are configured.
- The controller passes `orderId` correctly into the method.
- Exception handlers translate access denied/not found into the committed statuses.

**Do not mock `orderAccessPolicy.canRead()` to always return true** and then conclude that tenant isolation has been tested.

### 13.2. Contract testing per-resource permissions

An illustrative DSL with two tenants:

```yaml
name: checkout_cross_tenant_order_forbidden_403
request:
  method: GET
  url: /api/orders/ORDER-99
  headers:
    Accept: application/json
    Authorization: 'Bearer contract-reader-token'
response:
  status: 403
```

Condition: the base fixture creates `ORDER-99` belonging to `TENANT-99` while `contract-reader-token` carries tenant `TENANT-42`; the business policy rejects it and the API specifies returning `403`.

If policy specifies returning `404` to hide resource existence, change the contract status to match that policy rather than writing `403` out of habit.

### 13.3. Tests must prove cross-tenant access is blocked

Beyond status, verify there are no dangerous side effects:

- Do not return any PII fields of another tenant.
- Do not write access logs containing sensitive data outside policy.
- Do not update order state when the caller is rejected.
- Do not allow inferring resource existence via overly specific errors if hiding is required.
- Do not use an `ownerId`/`tenantId` self-declared in the request body as proof of permission without authentication.

These requirements may need **integration/security tests outside the Contract DSL**, especially when asserting that database records remain unchanged.

## 14. Verifying `401`, `403`, and error response bodies

A system may publish its own error envelope:

```json
{
  "code": "FORBIDDEN",
  "message": "Access denied",
  "traceId": "TRACE-TEST-42"
}
```

However, **Spring Security by default does not guarantee** that every `401` or `403` will have a JSON body in that format. If the team wants a consistent error envelope, you must implement:

- AuthenticationEntryPoint for `401`.
- AccessDeniedHandler for `403`.
- Appropriate exception handling for business `404`.
- Content-Type and challenge headers per policy.
- Safe logging/redaction.

Only write a contract requiring `code=FORBIDDEN` when the implementation actually returns that body.

### 14.1. Example error contract with a custom handler

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'checkout_insufficient_scope_json_403'

    request {
        method GET()
        url '/api/orders/ORDER-42'
        headers {
            header 'Authorization', 'Bearer contract-auditor-token'
        }
    }

    response {
        status FORBIDDEN()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'FORBIDDEN',
            message: 'Access denied'
        )
    }
}
```

**Mandatory condition:** the producer has a custom `AccessDeniedHandler` or equivalent handling mechanism returning this JSON. If not configured yet, use a contract that only asserts `403` rather than creating a "pretty" contract that does not match the implementation.

### 14.2. Avoid leaking internal details via error bodies

Error bodies must not expose:

- Full JWT claims.
- Internal lists of resource roles/permissions.
- Stack traces or Spring Security class names.
- Database keys, hostnames, or configuration details.
- Details distinguishing tenant/resource existence when policy requires hiding it.

Error messages help the consumer handle failures properly, but should not cause the API to leak secrets.

## 15. Be careful with `Authorization` in generated WireMock stubs

A producer contract containing:

```http
GET /api/orders/ORDER-42
Authorization: Bearer contract-reader-token
```

can generate a WireMock mapping that **only matches the header**:

```json
{
  "request": {
    "method": "GET",
    "url": "/api/orders/ORDER-42",
    "headers": {
      "Authorization": {
        "equalTo": "Bearer contract-reader-token"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": "ORDER-42",
      "status": "PAID",
      "totalAmount": 125000
    }
  }
}
```

This is an **illustrative WireMock JSON mapping**, not actual generated output from a specific plugin version. When a request matches the exact header, WireMock returns the defined response. It **does not verify JWT signatures**, issuer, expiry, or tenant ownership.

### 15.1. Why are false positives easy to hit?

Suppose the `401` mapping does not declare an Authorization matcher. If WireMock receives the same URL with the reader token, both the `401` and `200` mappings may match given the existing conditions; the outcome can then depend on mapping priority/registration.

You need to:

1. Inspect the **actually generated** JSON mapping files in the stubs JAR.
2. Check the request matcher for each scenario.
3. Use a mapping with an **Authorization absent** condition if required by your version and test goal.
4. Use explicit priority when multiple mappings share the same path.
5. Or separate server/test scopes so conflicting mappings are not loaded together.
6. Run a consumer smoke test with the reader token, auditor token, and no token.

**A `401` response from WireMock due to a non-matching stub does not prove producer authentication works properly.** In many cases an unmatched request even returns `404`, not `401`.

### 15.2. Avoid overly broad security matchers

Do not let a consumer stub accept:

```json
{
  "Authorization": {
    "matches": ".*"
  }
}
```

if the test needs to protect "the client sends the Bearer scheme". This regex can match even invalid strings. A `Bearer .+` matcher only proves **header shape**, not that a real token is valid.

For consumer stub tests, the goal is usually **the client sets the header properly and handles HTTP responses**. For producer auth tests, the goal is **filter chain and authorization behavior**. For real auth integration tests, the goal is **signatures/claims/IdP/JWKS**.

## 16. Do not put real secrets in contracts or stubs artifacts

Minimum principles:

| Item | Can be in contract? | Notes |
|---|---|---|
| Fake `Bearer contract-reader-token` | **Yes**, for tests | Must not be accepted by production decoder |
| Real production user JWT | **No** | Sensitive credential with expiration |
| Real API key | **No** | Can be exposed via Git/stubs JAR |
| Private signing key | **No** | Must stay in secret vault/dedicated test PKI |
| Fake tenant ID `TENANT-42` | **Yes** | Dummy data identifying no real user |
| Real customer PII | **No** | Do not put in fixtures/artifacts |
| Non-sensitive test public key | Possible | Manage per test PKI requirements |
| Test private key | Only when meeting specific security policy | Do not expose in public artifacts or logs |
| Token obtained via CI secrets | Do not write into contracts | Only inject for authorized integration tests |

### 16.1. Stubs artifacts often have wide sharing scope

A stubs JAR can travel from producer CI to a Maven artifact repository, and then to many consumer pipelines. If a contract contains a real bearer token, **anyone with read access to the artifact can view the token**.

You must:

- Pin meaningful yet non-sensitive fake fixtures.
- Scan for secrets before commit/publish.
- Not echo Authorization headers into CI logs.
- Redact tokens/cookies in request journals.
- Use least-privilege permissions for Maven repositories and CI runners.
- Never use a test JWT decoder in production runtime.
- Have a process to revoke/rotate credentials if exposed.

### 16.2. Test logs can be a leak channel

RestAssured, MockMvc, or WireMock request/response logging sometimes prints full headers. If a test fails, logs may retain bearer tokens longer than the request lifecycle. Log only necessary details such as request ID, status, test case scope, and correlation ID; do not log raw credentials.

In the lesson examples, token strings are **non-sensitive** values for illustration, but redaction policies still apply to integration tests using real secrets.

## 17. Other authentication types: Basic, API key, session, and mTLS

Not every producer uses JWT bearer tokens. Spring Cloud Contract only describes the **agreed HTTP request–response**, without dictating the authentication mechanism itself.

### 17.1. HTTP Basic

Header format:

```http
Authorization: Basic <base64-of-username-colon-password>
```

`Basic` only Base64-encodes, **it does not encrypt secrets**. If Basic auth needs testing, use **fake** credentials and test the security configuration separately; HTTPS remains mandatory in real systems. Never put real passwords into the DSL.

### 17.2. API key

Example:

```http
X-API-Key: contract-api-key
```

A contract can check that the client sends the header and the producer rejects requests missing the key. However, if the authentication filter is mocked away, the header appearing in the DSL **does not prove** real key validation.

### 17.3. Session cookie and CSRF

For browsers using cookie-sessions:

- Authentication may rely on `JSESSIONID` or another session mechanism.
- POST/PUT/DELETE may require a CSRF token.
- `403` may be caused by CSRF, not a missing role.
- Cookies need `Secure`, `HttpOnly`, and `SameSite` attributes per policy.
- CORS needs verification using Origin/preflight requests in dedicated tests.

Do not use bearer-token fixtures to infer results for cookie-session applications.

### 17.4. Mutual TLS (mTLS)

mTLS occurs during the **TLS handshake** before or outside the HTTP controller layer. A contract DSL with an `X-Client-Cert` header cannot prove the client certificate was verified by the ingress/proxy. You need an integration environment with TLS/client certificates and an appropriate reverse proxy/gateway.

## 18. Scopes, roles, and ownership need a clear test matrix

A common mistake is only testing "admin is allowed" and assuming authorization is sufficient. Build a matrix:

| Principal | Scope | Owner tenant | Resource tenant | Expected |
|---|---|---|---|---|
| Checkout reader | `orders.read` | `TENANT-42` | `TENANT-42` | `200` |
| Auditor | `orders.audit` | `TENANT-42` | `TENANT-42` | `403` |
| Checkout reader | `orders.read` | `TENANT-42` | `TENANT-99` | `403/404` per policy |
| Anonymous | None | — | `TENANT-42` | `401` |
| Invalid bearer | Unauthenticated | — | `TENANT-42` | `401` |
| Reader, order missing | `orders.read` | `TENANT-42` | Does not exist | `404` |

Test cases must distinguish:

1. **Authentication failed**.
2. **Authentication succeeded but lacks capability**.
3. **Has capability but lacks permission on the specific resource**.
4. **Has permission but resource does not exist**.

If you only assert `403` across these cases, an authentication or fixture bug may be masked.

### 18.1. Verify "deny by default"

When adding a new endpoint, if the security configuration uses:

```java
.anyRequest().permitAll()
```

a new route can accidentally become publicly open. Use an explicit policy and check **negative tests** for sensitive resources. A suitable option for many APIs is:

```java
.anyRequest().authenticated()
```

but that still **does not mean scope/resource-level authorization is verified**. Endpoints requiring different permissions must have specific rules.

Do not blindly apply a blanket rule across the entire system without considering public health endpoints, authentication callback routes, or static resources; the pattern above only illustrates the principle.

## 19. Producer Contract Verifier and test runner: ensure tests actually run

In a Maven producer, plugin configuration typically includes:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
```

And the build plugin:

```xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>CONTRACT_PLUGIN_VERSION_PHU_HOP</version>
    <extensions>true</extensions>
    <configuration>
        <baseClassForTests>
            com.example.order.contract.OrderContractTestBase
        </baseClassForTests>
        <testMode>MOCKMVC</testMode>
        <testFramework>JUNIT5</testFramework>
    </configuration>
</plugin>
```

These are **POM fragments**; running them requires compatible Spring Boot/Cloud/Contract versions, a test runtime, Security/OAuth2 Resource Server dependencies, and an appropriate parent/BOM. `CONTRACT_PLUGIN_VERSION_PHU_HOP` is a placeholder, not an actual version.

### 19.1. Verification steps on Maven

```bash
./mvnw -version
./mvnw -B -ntp clean verify

# Inspect actual generated test code and reports.
find target/generated-test-sources/contracts -type f -print
find target/surefire-reports -type f -name 'TEST-*.xml' -print
```

The paths above are common in the Maven plugin, though they may vary by version/configuration. In multi-module builds, run the command in the correct producer module and inspect reports in that module.

**Required evidence:**

- Generated tests exist for `200`, `401`, `403`, and `404`.
- Test classes properly extend `OrderContractTestBase`.
- The MockMvc/request adapter uses the corresponding filters.
- Tests execute and are not skipped by `skipTests` or exclusions.
- Test reports clearly record failures/errors/skips.
- Expected number of generated contract tests ran, not merely "0 tests yet BUILD SUCCESS".

### 19.2. Do not edit generated tests in `target`

When a test fails due to security, fix:

- The contract, if it describes the wrong agreed behavior.
- The security configuration or implementation, if the producer is actually wrong.
- The test-only JwtDecoder/fixture, if the setup is wrong.
- The test mode/base class, if generated requests bypass the filter chain.
- The plugin/dependencies, if generation/compilation fails.

Do not manually edit Java files in `target/generated-test-sources`; they will be overwritten on the next build.

## 20. Mutation testing: prove filters and authorization rules are not bypassed

A powerful way to detect false-positive safety in tests is to **intentionally break the implementation on an experimental branch**, then observe whether contract tests fail for the right reason.

### 20.1. Mutation 1 — remove authentication requirement

Suppose a developer changes the rule to:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .permitAll()
```

instead of:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Expectations:

- The `200` test with the reader token may still pass.
- The anonymous `401` test **must fail** if the filter/route is actually being tested.
- The auditor `403` test **must fail** when the endpoint is opened too broadly.

If both `401` and `403` still pass despite `permitAll()`, check whether responses are mocked/canned, whether another security rule blocks the request, or whether generated tests actually run.

### 20.2. Mutation 2 — remove tenant check

If code removes `orderAccessPolicy.canRead(authentication, orderId)`, the cross-tenant test must fail when a `TENANT-42` principal can retrieve `ORDER-99` belonging to `TENANT-99`.

If contracts only assert the `200` happy path, there will be no proof that cross-tenant access is blocked.

### 20.3. Mutation 3 — decoder accepts every token

If the test decoder accidentally always returns a reader principal for any string:

```java
return token -> createReaderJwt(token);
```

then the invalid-token `401` test must fail. Note, however: a test decoder **inherently does not prove cryptographic validation**. Mutation only verifies that the contract test setup distinguishes test credentials; it does not replace real JWT integration tests.

## 21. How does Spring Cloud Contract Stub Runner view security?

The producer publishes a stubs JAR from verified contracts. The consumer can configure:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest(
    properties = "clients.orders.base-url=http://localhost:8085"
)
@AutoConfigureStubRunner(
    ids = "com.example:order-service:1.4.0:stubs:8085",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutOrderClientContractTest {
    // Inject Checkout's real OrderClient.
    // Verify Authorization header and handling of 200/401/403/404.
}
```

**This is an illustrative test configuration**, not a standalone test class. The `clients.orders.base-url` property is defined by Checkout itself. Port `8085` belongs to the stub HTTP server, not the Maven artifact identity.

### 21.1. What should the consumer verify?

- The real client sends the `Authorization` header per the configured mechanism.
- The client does not accidentally omit the `Bearer ` prefix.
- On a `401` response, the client classifies it as unauthenticated and handles refresh/login/propagation per policy.
- On a `403` response, the client does not blindly retry or report a fake `404`.
- On a business `404` response, the client handles `ORDER_NOT_FOUND`.
- Raw tokens are not logged.
- Requests returning `401/403` are not retried infinitely.
- If token acquisition is another service, the client has separate integration tests for the token retrieval flow.

**Do not take a green WireMock result as proof that production JWT signature validation is safe.** Stub Runner uses HTTP mappings and does not run Order Service's Spring Security filter chain.

### 21.2. Stub mappings may need adjustments to avoid collisions

Contract cases use the same URL with different headers, so you need to inspect the generated WireMock mappings, especially **anonymous `401`** and **reader `200`**. If the generated mapping cannot express an absent Authorization header with the chosen DSL, you can:

1. Separate consumer tests by loaded server/mappings.
2. Use a WireMock custom mapping for `401` with an absent-header matcher.
3. Use explicitly configured priorities.
4. Use distinct request scenarios when within contract scope.
5. Verify that generated producer tests still protect the API without loosening the contract due to stub conflicts.

Do not manually edit a generated mapping and forget that the next package step will overwrite it; if customization is necessary, manage custom mappings and packaging clearly per version/plugin.

## 22. Message security: do not confuse HTTP auth with broker authorization

Order Service may emit an `ORDER_PAID` event for Billing:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'billing_order_paid_v1'
    label 'billing_order_paid_event_v1'

    input {
        triggeredBy('publishOrderPaid()')
    }

    outputMessage {
        sentTo('orders.events')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'ORDER_PAID')
        }
        body(
            eventId: 'EVENT-42',
            eventType: 'ORDER_PAID',
            orderId: 'ORDER-42'
        )
    }
}
```

A producer message contract can verify **destination, headers, and payload** of messages emitted through a test binder/broker. However, it **does not automatically verify**:

- Real Kafka ACL/SASL or RabbitMQ permissions.
- TLS/mTLS to the broker.
- Whether the consumer group has permission to subscribe to the topic/queue.
- Whether message data is encrypted/signed per policy.
- Whether the broker blocks unauthorized publishers from sending events.
- Secret rotation/certificate expiry.

An in-memory test binder can be very useful for contract tests, but separate **broker security integration tests** are needed when the producer runs against real middleware.

### 22.1. Do not embed access tokens in events

Messages should generally not carry raw user access tokens in the body or headers unless there is a reviewed threat model and special requirement. Producer contracts should use event IDs, fake actor IDs, correlation IDs, and the minimum necessary business claims. Do not turn the broker into a bearer token distributor via stubs JARs.

## 23. CI: producer security contract verification

A producer pipeline might look like this:

```mermaid
flowchart TD
    A[Review Groovy/YAML auth contracts] --> B[Verify test fixtures have no real secrets]
    B --> C[Generate producer tests]
    C --> D[Spring TestContext + security filter chain]
    D --> E[Test decoder and controlled tenant data]
    E --> F[Run 200, 401, 403, 404 cases]
    F --> G{Did generated tests actually run and pass?}
    G -- No --> H[Fail build / fix security or fixture]
    G -- Yes --> I[Convert mappings + package stubs]
    I --> J[Verify archive, classifier, no secrets]
    J --> K[Publish verified stubs with proper permissions]
    K --> L[Consumer Stub Runner tests]
    L --> M[CI compatibility gate]
```

### 23.1. CI checklist

- [ ] Source contracts clearly describe authorized/unauthenticated/forbidden/resource-not-found cases.
- [ ] Spring Security filters are enabled in producer contract tests.
- [ ] The test decoder exists only on the test classpath/profile.
- [ ] The test decoder accepts only defined fixture tokens.
- [ ] Authorization scope/role mappings match the producer's real policy.
- [ ] Tenant/object-level checks have dedicated tests when needed.
- [ ] `401` is distinguished from `403` and `404`.
- [ ] `WWW-Authenticate` and error bodies are asserted if part of the contract.
- [ ] Generated producer tests execute and are not skipped.
- [ ] Surefire/Failsafe reports clearly record test counts and failures.
- [ ] Negative tests exist to detect disabled security filters.
- [ ] No real tokens, API keys, or PII exist in source, logs, or stubs artifacts.
- [ ] Stubs JAR comes from the same build/version as the verified producer.
- [ ] Consumer Stub Runner tests handle auth errors using the real client.
- [ ] JWT signature/issuer/audience/JWK tests are verified in a separate suite.
- [ ] Broker ACL/TLS/mTLS are verified at the integration level if used by the system.
- [ ] CI release does not publish when security contract cases fail.
- [ ] Pull requests from untrusted sources cannot read deploy secrets.

### 23.2. Illustrative Maven verification

```bash
./mvnw -B -ntp clean verify

# Inspect generated test results in the project's output path.
find target/surefire-reports -type f -name 'TEST-*.xml' -print

# List entries in the stubs JAR for the exact version.
jar tf target/order-service-1.4.0-stubs.jar
```

These commands are **practical guidelines** only. Artifact/path names, Maven plugin lifecycle, and reports must be checked per project. Never use `-DskipTests` and then mark stubs as verified.

### 23.3. Separating auth contract and auth integration pipelines

| Pipeline/test group | Goal | When typically run? |
|---|---|---|
| Producer contract security | `200/401/403/404`, headers/body, permission rules | Every PR/important merge |
| JWT validation integration | Signature, exp/nbf, issuer/audience, JWKS rotation | Selected PRs or security pipeline |
| API gateway security | TLS, mTLS, forwarding headers, ingress rules | Integration/staging |
| Browser/session security | CSRF, CORS, cookies, session policies | Web app security suite |
| Broker authorization | SASL/ACL/TLS, topic/queue permissions | Messaging integration |
| Consumer stub security | Client sends headers, maps error statuses, no token leak | Consumer CI |
| Penetration/security audit | Check risks outside contract scenarios | Per security policy schedule |

**Contract tests are one control layer**, not a certificate that the entire system is secure.

## 24. Common errors and how to diagnose them

| Symptom | Possible cause | Investigation steps |
|---|---|---|
| Missing token still returns `200` | Filters disabled or route `permitAll` | `addFilters`, SecurityFilterChain, and mutation test |
| Reader token gets `401` | Test decoder not loaded or token mismatch | `JwtDecoder` bean, fixture string, redacted logs |
| Auditor token gets `401` instead of `403` | Decoder rejects token | Distinguish accepted token from missing scope |
| Reader token gets `403` | Wrong scope → authority mapping | Check `SCOPE_orders.read` and converter |
| Cross-tenant request gets `200` | Missing object-level policy | `OrderAccessPolicy` and tenant fixture |
| Cross-tenant returns `404` instead of `403` | Resource-hiding policy or mapper | Cross-check contract API policy |
| `403` on POST in session app | Missing CSRF token | Check CSRF setup, do not assume missing role |
| API `401` has no JSON body | Default Spring Security entry point | Assert body only if a real handler exists |
| Generated tests always pass even without auth | Mocked controller or pre-seeded principal | Check filter chain, `@WithMockUser`, and test code |
| Stub Runner returns `401` for reader token | Anonymous mapping too broad | Inspect mapping/priority/absent-header rules |
| Stub Runner returns `404` when token is missing | Request does not match mapping | Distinguish WireMock unmatched `404` |
| CI only fails token tests | Hard-coded real token expired | Use test decoder/non-sensitive fixture |
| Production JWT invalid yet tests stay green | Test decoder skips crypto checks | Run real JWT integration tests |
| Build green with `Tests run: 0` | Plugin/runner not executing generated tests | Check test reports, failOnNoContracts |
| `JwtDecoder` fails to compile | Missing OAuth2 Resource Server dependencies | Check POM/BOM compatibility |
| `@WithMockUser` makes 401 case pass falsely | SecurityContext pre-populated | Do not apply annotation to anonymous tests |
| Tests leak tenant data when run in parallel | Fixtures share DB | Reset/isolation/correlation IDs |
| Stubs artifact contains real token | Contract or logs contain secret | Secret scan and rotate/revoke credential |

### 24.1. Quick debugging workflow

1. Identify which `Authorization` header the request actually sends in the **test**, without printing sensitive tokens.
2. Verify MockMvc has security filters registered.
3. Verify whether the test `JwtDecoder` bean is being used.
4. Confirm reader/auditor fixture tokens decode into the expected authorities/tenant.
5. Confirm SecurityFilterChain path/method matchers match the request.
6. If method security is used, check proxies and business policy.
7. Check resource/tenant fixtures.
8. Compare actual status and error body against the DSL.
9. Read generated tests and Surefire/Failsafe reports.
10. For consumer stub failures, inspect WireMock mappings/priority rather than changing producer implementation by guesswork.

**Do not change a `403` contract to `200` just to silence CI failures** before knowing whether the test base is bypassing security or the implementation lost its policy.

## 25. Hands-on lab: securing Order API with contract tests

This lab combines both authentication and authorization.

### Phase A — create contracts

1. Create Groovy `checkout_get_paid_order_authorized_200`.
2. Create YAML `checkout_get_paid_order_unauthenticated_401`.
3. Create YAML `checkout_get_paid_order_forbidden_403`.
4. Create Groovy `checkout_get_missing_order_authorized_404`.
5. If using multi-tenancy, add a contract rejecting `ORDER-99` for another tenant.
6. Choose response headers/body matching real API policy; do not invent error JSON.

### Phase B — Spring Security and fixtures

1. Enable `SecurityFilterChain` requiring `SCOPE_orders.read` for GET orders.
2. Use `@SpringBootTest` and `@AutoConfigureMockMvc(addFilters=true)`.
3. Create a test-only `JwtDecoder` mapping fake reader/auditor tokens.
4. Keep the real business authorization policy; do not mock it to always return true.
5. Seed `ORDER-42` belonging to `TENANT-42`; `ORDER-99` belonging to `TENANT-99` if applicable.
6. Clean fixtures independently before each generated test.

### Phase C — verify each case

1. Send reader token, assert `200` and body.
2. Omit token, assert `401`.
3. Send auditor token, assert `403`.
4. Send a token not accepted by fixtures, assert `401`.
5. Use reader token with `ORDER-MISSING`, assert `404 ORDER_NOT_FOUND`.
6. Use reader token with another tenant's resource, assert `403` or `404` per policy.
7. If response differs from expectations, diagnose authn, authz, and data separately.

### Phase D — verify fault-detection capability

1. Temporarily replace `hasAuthority("SCOPE_orders.read")` with `permitAll()` on an experimental branch.
2. Run generated contract tests; anonymous/auditor cases must fail when the route is open.
3. Restore the security rule.
4. Temporarily bypass the tenant check policy; cross-tenant case must fail.
5. Restore and run the suite until passing.
6. Verify the test report shows the right count of generated tests without skips.

### Phase E — packaging and consumer Stub Runner

1. Run producer verification following the proper Maven/Gradle lifecycle.
2. Package the stubs JAR with the `stubs` classifier.
3. Verify the archive contains no real credentials.
4. Inspect generated WireMock mappings when cases share the same URL.
5. Consumer uses Stub Runner and the real client to verify headers/error mapping.
6. Note that WireMock does not verify JWT signatures.

### Phase F — security integration

1. Create tests with a mock JWKS/IdP having **real JWT signatures** in a dedicated test environment.
2. Verify invalid signature, expired token, and invalid issuer/audience per security policy.
3. If the API goes through a gateway, add ingress/auth forwarding tests.
4. If cookie sessions exist, add CSRF/CORS tests.
5. If broker messaging exists, check ACL/TLS and ensure no tokens appear in events.
6. Attach test reports to CI and block releases when security-contract tests fail.

**Completion criteria:** generated producer tests pass through real security filters and application code, properly distinguish `200/401/403/404`, do not leak other tenants' data, stubs artifacts contain no secrets, and the team can explain **why a fake test JWT decoder does not prove JWT cryptography is safe in production**.

## 26. Pre-merge checklist

- [ ] Contracts clearly document authorized, anonymous, insufficient-scope, and resource-not-found cases.
- [ ] `Authorization` values in contracts are non-sensitive fixtures only.
- [ ] The test profile does not alter production security configuration outside the approved substitution point.
- [ ] Security filters are not disabled in producer contract tests.
- [ ] The test decoder is used only in the test environment.
- [ ] Reader/auditor tokens have distinct authorities sufficient to separate `200` and `403`.
- [ ] `@WithMockUser` is not used globally on anonymous cases.
- [ ] Object-level/tenant-level authorization is tested if required by the product.
- [ ] `401`, `403`, and `404` are not lumped into a single error bucket.
- [ ] Error bodies/headers in contracts match the real implementation.
- [ ] Generated tests are generated, compiled, and executed.
- [ ] Negative/mutation tests exist proving filters/policies are not bypassed.
- [ ] WireMock mappings have proper matchers/priorities when sharing a URL.
- [ ] Stubs JAR contains no real JWTs, API keys, PII, or secrets.
- [ ] Consumer client tests handle HTTP auth errors per policy.
- [ ] Real JWT/IdP/JWKS validation has separate tests.
- [ ] Session/CSRF/CORS and gateway/mTLS are tested if applicable.
- [ ] CI stores reports and versioned artifacts, and blocks publishing when tests fail.

## 27. Self-check questions

1. **How does authentication differ from authorization?** Authentication identifies who the caller is; authorization determines what that identity is allowed to do on which resources.
2. **When should `401` be returned?** Typically when authentication credentials are missing or unacceptable.
3. **When should `403` be returned?** Typically when the principal is authenticated but lacks permission; it can also result from policies like CSRF.
4. **Can `404` be used to hide resources a caller is not allowed to see?** Yes, if that is the API's policy.
5. **Why does a `200` contract with an Authorization header not yet prove security works?** Because the filter chain might be bypassed while the controller still returns `200`.
6. **What is the risk of `@AutoConfigureMockMvc(addFilters=false)`?** It skips the security filters that need to be tested.
7. **Does a test-only JwtDecoder verify real JWT signatures?** No, it only simulates the decoding outcome.
8. **Why must the auditor token be accepted by the decoder yet lack the scope?** So the test actually measures `403` authorization rather than `401` authentication.
9. **What authority does `scope=orders.read` usually become?** `SCOPE_orders.read` in Spring Security Resource Server's default converter.
10. **Can `@WithMockUser` be used to verify the Bearer header is parsed properly?** No, it primarily sets the SecurityContext.
11. **What does the `jwt()` request post-processor test?** The authentication object/authorization path in MockMvc, not JWT signatures.
12. **Why not mock business policies to always return true?** Because doing so removes the resource-level authorization check itself.
13. **What fixtures does a tenant isolation test need?** Two resources belonging to two tenants and a principal with a specific tenant.
14. **If an anonymous request receives `200`, what should be checked?** The filter chain, security rules, and generated tests.
15. **Does Spring Security automatically return a JSON body for every `401/403`?** No; custom handlers may be required.
16. **What is `WWW-Authenticate` used for?** Conveying the appropriate authentication challenge/metadata.
17. **Does a contract omitting the Authorization header automatically create a WireMock absent-header matcher?** You should not assume so.
18. **Does Stub Runner verify cryptographic JWTs?** No; WireMock mainly matches requests and serves responses.
19. **Why not put production tokens into the DSL?** They can leak through Git, logs, and stubs artifacts.
20. **If using fake JWTs, are real JWT integration tests still needed?** Yes, if you need to verify signatures, issuer, audience, expiry, and JWKS.
21. **Is a `403` on POST definitely caused by a missing role?** No; in a session app it could be caused by CSRF.
22. **Can mTLS be proven by an Authorization header?** No; TLS/proxy integration tests are required.
23. **What evidence do generated tests need in CI?** Source, reports, executed test count, and passing results.
24. **How does security-rule mutation testing help?** It proves negative contracts actually catch endpoints whose permissions were overly broadened.
25. **Does a message contract automatically verify Kafka ACLs?** No; broker security integration tests are required.

## 28. References and version limits

Consult official documentation and cross-check against the project's actual Spring Cloud Contract/Spring Security versions:

- [Spring Cloud Contract — Reference](https://docs.spring.io/spring-cloud-contract/reference/)
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/)
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — MockMvc Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security — Testing with Mock Users](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [OWASP — API Security Top 10](https://owasp.org/www-project-api-security/)

**Version limits:** packages/imports, annotation names, test-mode support, mapping generation behavior, and claim-to-authority conversion may differ across Spring Cloud Contract, Spring Security, and Spring Boot versions. In newer Spring Boot/Spring Framework versions, mock bean annotations can also change; therefore this lesson prefers `@TestConfiguration` and an illustrative test-only decoder rather than assuming a single `@MockBean` API works across every release train.

The code examples in this lesson illustrate design approaches; **they have not been built and run inside a specific producer project**. When applying them, verify generated test sources, dependencies, Spring TestContext, security filters, and test reports against your pinned toolchain.

## Conclusion

**Mocking authentication and authorization in producer tests does not mean disabling security so requests run more easily.** The right approach is to simulate **controlled identities/credentials** using test-only fixtures while still letting the **real Spring Security filter chain, authorization rules, business policies, and producer implementation** decide the result. Contracts for `200`, `401`, `403`, `404`, and cross-tenant access protect the behaviors Checkout and Billing actually depend on.

Combining **Groovy/YAML DSL**, **generated producer verification**, **secret-free stubs JARs**, **consumer tests via Stub Runner**, and **CI release gates** helps catch both incompatible API changes and regressions in committed security behavior early. Nevertheless, **a fake test JwtDecoder does not replace checks for JWT signature/issuer/audience, gateway, TLS, CSRF, or broker ACLs**; those requirements need independent integration and security tests for reliable evidence.
