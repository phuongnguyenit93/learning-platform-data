# Testing Security Filters and Caller Identity

## 1. Why Should Security Be Part of the HTTP Contract?

In a multi-service system, a contract does not merely specify what JSON `GET /api/orders/42` returns. Consumers also depend on **who is allowed to call the API**, how authentication credentials must be sent, and how the producer responds when the caller is unauthenticated or lacks permission. A security filter change can break consumers even when the controller and DTOs remain completely unchanged.

For example, `Checkout Service` is a consumer of `Order Service` (producer):

- A caller with role `ORDER_READ` can view order details.
- Sending no credentials causes the API to return `401 Unauthorized`.
- Being authenticated without the required role causes the API to return `403 Forbidden`.
- When access is granted, the API returns `200 OK` and the order body per the contract.

**Spring Cloud Contract** lets you express these cases using Groovy or YAML DSL, generate producer-side tests, publish verified stubs, and let consumers run tests via **Stub Runner**. Including security scenarios in CI helps catch accidentally exposing an endpoint publicly, changing authentication mechanisms, or returning incompatible error codes.

After this lesson, you will be able to:

1. Distinguish **authentication**, **authorization**, caller identity, and the security filter chain.
2. Write HTTP contracts for authorized, unauthenticated, and unauthorized callers.
3. Configure a base test class so security filters genuinely execute during producer verification.
4. Distinguish testing with mock users, real credentials in a test environment, and simulated stubs.
5. Diagnose `401`/`403` errors caused by tokens, roles, CSRF, tenants, or MockMvc setup.
6. Design a CI pipeline ensuring security contracts are not skipped.

## 2. Authentication, Authorization, and Caller Identity Are Three Related Concepts

### 2.1. Authentication: Who Is the Caller?

**Authentication** is the step of verifying identity credentials: username and password, HTTP Basic, bearer token/JWT, session cookies, mTLS, or another mechanism defined by the system.

After authentication succeeds, Spring Security typically stores an `Authentication` object in the request's `SecurityContext`. From it, you can access:

- `authentication.getName()`: the identifier recognized by Spring Security.
- `authentication.getPrincipal()`: the principal, such as `UserDetails`, `Jwt`, or a custom type.
- `authentication.getAuthorities()`: the permissions/roles granted to the identity.

The value of `getName()` and the `principal` type depend on the authentication mechanism. Do not assume JWT subject, email, username, and tenant ID are always the same field.

### 2.2. Authorization: What Is the Caller Allowed to Do?

**Authorization** checks whether an authenticated identity has permission to perform a specific action or access a specific resource. For example:

- `ROLE_ORDER_READ` can view orders.
- `ROLE_ORDER_ADMIN` can cancel orders.
- A user may only view orders **belonging to themselves or their tenant**, even if they hold the order-reading role.

Roles are a necessary condition in many systems, yet not always sufficient: accessing `/api/orders/42` may also depend on **resource ownership** and **tenant**.

### 2.3. Where Does the Security Filter Chain Sit?

With Spring Security on Spring MVC, requests pass through the `SecurityFilterChain` before the controller handles them. Filters and related components can authenticate credentials, restore the security context, enforce CSRF checks, or route access errors.

```mermaid
sequenceDiagram
    participant C as Consumer
    participant S as Spring Security Filters
    participant A as Controller / Service
    C->>S: GET /api/orders/42 + Authorization
    alt Authentication fails
        S-->>C: 401 (or configured entry point behavior)
    else Authenticated but lacks permission
        S-->>C: 403
    else Permitted
        S->>A: Request + Authentication/Principal
        A-->>S: Order response
        S-->>C: 200 + JSON
    end
```

A contract test that sends requests **straight to the controller without traversing filters** cannot verify the cases above thoroughly.

## 3. Understanding HTTP Status Codes When Testing Security

| Status | Typical meaning | Test example |
| --- | --- | --- |
| `200 OK` | Request is permitted and processed successfully | User with `ORDER_READ` fetches an order |
| `401 Unauthorized` | Request lacks valid authentication per the API mechanism | Missing or invalid HTTP Basic credentials; invalid bearer token |
| `403 Forbidden` | Server understood the request but denies access | Authenticated without `ORDER_READ`; or blocked by CSRF |
| `302 Found` | Some web apps redirect to a login page | Session/form login instead of a pure API returning `401` |
| `404 Not Found` | Resource not found, sometimes used to avoid leaking existence | Resource outside the caller's scope per API policy |

**Do not assume every unauthenticated request returns `401`.** Actual behavior depends on `AuthenticationEntryPoint`, form login, Basic/Bearer, `Accept`, security configuration, and even the API gateway. For the REST API using HTTP Basic throughout this lesson's examples, the three scenarios `200`, `401`, and `403` are clear choices.

HTTP `401` in Basic authentication often includes a `WWW-Authenticate` header. Include the header, realm, or error message in the contract only if the consumer genuinely depends on them; exact values must match application configuration rather than assumptions.

## 4. Designing the Example: `GET /api/orders/42`

Suppose a Spring Boot application uses Spring Security with these rules:

1. `GET /api/orders/**` requires role `ORDER_READ`.
2. Clients authenticate via HTTP Basic in the example environment.
3. The controller returns JSON `{"orderId":42,"status":"CREATED"}` when fixture data is prepared.

Illustrative Java configuration of the **application security policy**:

```java
package com.example.orders;

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
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasRole("ORDER_READ")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

This snippet illustrates modern Spring Security. In production, authentication mechanisms, path rules, tenant access controls, and other filters must be designed completely. Never put test accounts/passwords into production configurations.

To reproduce the scenarios, the test suite needs test identities:

| Test identity | Test-only password | Authority | Expected result |
| --- | --- | --- | --- |
| `reader` | `password` | `ROLE_ORDER_READ` | `200` |
| `viewer` | `password` | `ROLE_VIEWER` | `403` |
| No credentials sent | None | None | `401` |

**Security note:** credentials in this lesson are **fictional and strictly for isolated test environments**; never use them in deployed systems, and never commit real passwords or real bearer tokens into contracts or version control. If using production mechanisms like OAuth2/JWT, generate test identities or tokens with explicit expiration and scope.

## 5. Three Groovy DSL Contracts for the Same Endpoint

Each scenario needs its own contract: one valid request, one unauthenticated request, and one authenticated request lacking permissions.

### 5.1. Authorized: `200 OK`

Example `get_order_authorized.groovy`:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Authorized reader retrieves the order'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            header('Authorization', 'Basic cmVhZGVyOnBhc3N3b3Jk')
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 42,
            status: 'CREATED'
        )
    }
}
```

The Basic value in the example encodes `reader:password` in Base64, **not cryptographic encryption**. With HTTP Basic, credentials must be protected by HTTPS in real traffic; internal tests use fake accounts only.

The contract protects both sides: the producer test must receive `200` and the right body when valid credentials are sent; Stub Runner can simulate the `200` response for requests matching those conditions.

### 5.2. Unauthenticated: `401 Unauthorized`

Example `get_order_unauthenticated.groovy`:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Request without credentials is rejected'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status UNAUTHORIZED()
    }
}
```

The generated producer test sends a request **without `Authorization`**, verifying that the security filter rejects the request with `401` under the chosen Basic configuration. Do not add an error body to the contract if consumers do not rely on that body format.

**Important note on stubs:** *omitting* the `Authorization` header does not always mean the generated WireMock mapping enforces that **the header must be absent**. A mapping with only method/URL can match requests that carry credentials too, colliding with the `200` mapping. When publishing all three stubs for the same endpoint, inspect **generated mappings, priorities, and absence conditions** for your Spring Cloud Contract/WireMock version. When you need to express header absence explicitly, use only matcher syntax supported by your DSL version and verify with real consumer tests.

### 5.3. Authenticated Without Permission: `403 Forbidden`

Example `get_order_forbidden.groovy`:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Viewer lacks role to read order'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            header('Authorization', 'Basic dmlld2VyOnBhc3N3b3Jk')
            header('Accept', 'application/json')
        }
    }

    response {
        status FORBIDDEN()
    }
}
```

The example credential represents `viewer:password`, an existing identity holding only `ROLE_VIEWER`. When the security filter chain enforces `hasRole("ORDER_READ")`, this account is authenticated yet denied access.

**Do not equate `403` with "wrong password."** On a wrong password, HTTP Basic typically returns `401`; insufficient roles, or another security policy denying an authenticated request, can return `403`.

### 5.4. Why Must All Three Contracts Have Independent Test Data?

| Contract | Credential in request | Producer verification outcome |
| --- | --- | --- |
| Authorized | `reader` with `ROLE_ORDER_READ` | `200`, matching JSON |
| Unauthenticated | No credentials sent | `401` |
| Forbidden | Authenticated `viewer` lacking role | `403` |

If `viewer` does not exist in the test environment, the third contract will easily return `401` instead of `403`, failing to verify authorization. That is why fixtures must reproducibly set up both **authentication state** and **role sets**.

## 6. Equivalent YAML Contracts

In YAML DSL, the requests/responses have the same semantics:

```yaml
description: Authorized reader retrieves the order
request:
  method: GET
  url: /api/orders/42
  headers:
    Authorization: "Basic cmVhZGVyOnBhc3N3b3Jk"
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    orderId: 42
    status: CREATED
```

Rejected due to missing role:

```yaml
description: Viewer lacks role to read order
request:
  method: GET
  url: /api/orders/42
  headers:
    Authorization: "Basic dmlld2VyOnBhc3N3b3Jk"
    Accept: application/json
response:
  status: 403
```

Unauthenticated case:

```yaml
description: Missing credentials
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 401
```

In YAML, `response.status` is the HTTP code; `request.headers.Authorization` is the header sent to the producer. Never mistakenly place bearer tokens or Basic credentials inside `response`.

These examples are based on an API using Basic authentication. If the real API uses JWT, cookies, or mTLS, **design contracts matching the real mechanism** rather than copying Basic simply because it is simpler.

## 7. Configuring the Base Test Class So Security Filters Actually Run

Producer verification is trustworthy only when requests from generated tests pass through the **filter chain protecting the API**. With Spring Boot MVC and Spring Security, an illustrative base class is:

```java
package com.example.orders.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc(addFilters = true)
@ActiveProfiles("contract")
public abstract class HttpSecurityContractBase {

    @Autowired
    protected MockMvc mockMvc;

    @BeforeEach
    protected void setupMockMvc() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
```

Key points:

- `@SpringBootTest` starts the producer's test context, which contains `SecurityFilterChain`.
- `@AutoConfigureMockMvc(addFilters = true)` instructs Spring Boot to register the application context's filters when creating MockMvc. In standard Spring Boot configurations this is usually the default, yet writing it explicitly is good practice in security tests.
- `RestAssuredMockMvc.mockMvc(mockMvc)` attaches the client used by generated tests in MockMvc mode.
- `@ActiveProfiles("contract")` allows loading test-specific credentials/fixtures if the project defines that profile.

**Enabling filters alone does not test the entire security system.** Components residing in an API gateway, reverse proxy, external identity provider, or network layer do not appear automatically in MockMvc. Add integration/E2E tests for those boundaries.

### 7.1. Two Configurations That Defeat Security Testing

Do not use:

```java
@AutoConfigureMockMvc(addFilters = false)
```

in contract test suites meant to protect authentication/authorization. Removing filters lets the endpoint return `200` even without credentials, making `401` or `403` tests unrepresentative of the real API.

Also be careful with:

```java
MockMvcBuilders.standaloneSetup(controller).build();
```

Standalone MockMvc configures only the supplied controller and does not recreate the full Spring Security filter chain. It works for many controller unit tests, yet is **insufficient on its own** to verify a security contract unless matching security components are explicitly registered.

If generated tests use another test mode such as `EXPLICIT` or REST Assured against a real server, the base class must set up that mechanism—do not copy a MockMvc base class verbatim expecting it to work everywhere.

### 7.2. Configuring the Plugin to Select the Right Base Test

Illustrative Maven configuration:

```xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>com.example.orders.contract.HttpSecurityContractBase</baseClassForTests>
    </configuration>
</plugin>
```

The Spring Cloud Contract plugin version must match the Verifier dependency managed by the Spring Cloud BOM; property `${spring-cloud-contract.version}` must be defined in the POM or parent POM. Test dependencies (Spring Boot Test, Security test, and Spring Cloud Contract Verifier) must also be present on the test classpath.

When a system has multiple contract groups (public HTTP, protected HTTP, messaging), use `baseClassMappings` so the security group extends a base class with matching filters and fixtures instead of applying one configuration to every contract.

## 8. Preparing Test Identities and Permissions

The `reader` and `viewer` contracts only work if the authentication mechanism in the test context actually recognizes those two accounts. One solution for **isolated practice** is a test-only `UserDetailsService` providing in-memory accounts:

```java
package com.example.orders.contract;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@TestConfiguration(proxyBeanMethods = false)
public class ContractUsersConfiguration {

    @Bean
    UserDetailsService contractUsers() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}password")
                .roles("ORDER_READ")
                .build(),
            User.withUsername("viewer")
                .password("{noop}password")
                .roles("VIEWER")
                .build()
        );
    }
}
```

In the base class, you can use `@Import(ContractUsersConfiguration.class)` to register this test configuration **if** the application's security architecture uses `UserDetailsService` and can pick that exact test bean. If the project already has multiple `AuthenticationProvider`s or LDAP/OAuth2 mechanisms, adding a bean does not necessarily route producer tests through it; verify the actual flow.

**Note:** `{noop}password` is an unencoded format meant strictly for demos/isolated tests and must never be applied to real accounts. When using Basic authentication, credentials appearing in contracts are test data only. For high-security systems, use test credentials managed through internal workflows and never hard-code live secrets.

### 8.1. Roles and Authorities Are Not Identical

In Spring Security, `hasRole("ORDER_READ")` typically matches authority `ROLE_ORDER_READ`, whereas `hasAuthority("ORDER_READ")` matches the exact authority `ORDER_READ`. If a JWT token contains scope `orders.read`, the application may map it to `SCOPE_orders.read`, which is completely different from role `ROLE_ORDER_READ`.

Therefore, when testing `403`, check:

- Which authorities does the principal actually hold?
- Does the security rule use `hasRole`, `hasAuthority`, `@PreAuthorize`, or another policy?
- Does the authentication mechanism map JWT claims to authorities as expected?

A fake user with the right name yet wrong authority can cause a test intended for `200` to return `403`.

### 8.2. Test Accounts Do Not Replace Resource-Level Identity Checks

Even a user with role `ORDER_READ` is not necessarily allowed to view every order. The real rule may be "may view orders belonging to their own tenant."

For example:

| Caller | Resource | Assumed policy | Expectation |
| --- | --- | --- | --- |
| `reader` in `tenant-a` | Order of `tenant-a` | Has role and matching tenant | `200` |
| `reader` in `tenant-a` | Order of `tenant-b` | Has role but different tenant | `403` or `404` per API |
| `viewer` in `tenant-a` | Order of `tenant-a` | Insufficient role | `403` |

If consumers require guarantees against cross-tenant data leakage, write **contracts or additional authorization tests** for that scenario rather than only testing `hasRole` on a generic path. Tenant information must come from a trusted source (such as a verified token claim or server-side session), **never** blindly trusting a client-supplied `X-Tenant-Id` header.

## 9. Using `@WithMockUser` or Sending Real Credentials Over HTTP?

Spring Security Test supports `@WithMockUser` and `RequestPostProcessor`s like `user(...)` and `jwt(...)` to populate the security context in tests. They are useful, provided you understand **which layer they test**.

| How identity is created | What does it verify? | Limitations |
| --- | --- | --- |
| `@WithMockUser` | Authorization using mocked principal/authorities | Does not prove HTTP Basic parser, JWT decoder, or token signature checks work |
| MockMvc `.with(user("reader"))` | Authorization for request with test user | Not proof that real credentials are parsed properly |
| MockMvc `.with(jwt())` | Authorization rules using simulated principal/claims | May bypass signature, issuer, audience, or expiry verification |
| Sending Basic credentials through real filter chain | Basic authentication and role mapping in test context | Does not test external gateway/mTLS/IdP |
| Sending signed test JWT through real resource server config | Part of Bearer/JWT decoder and claim mapping pipeline | Depends on test issuer/key/clock; does not verify production IdP environment |

Example of a hand-written Spring Security Test:

```java
@Test
@WithMockUser(username = "reader", roles = "ORDER_READ")
void readerCanAccessOrder() throws Exception {
    mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk());
}
```

This is an example of **authorization testing**. It does not prove that a request missing or sending a bad `Authorization` header is rejected by filters, because the security context was pre-populated by the test.

**In generated contract tests, putting `@WithMockUser` on the base class can defeat the purpose:** if every test gets a pre-set principal, the "no credentials sent" scenario can still be treated as a logged-in user. For contracts testing **authentication**, prefer sending test HTTP credentials through the filter just like real consumers.

## 10. OAuth2/JWT: Testing the Right Boundary

Many microservices use `Authorization: Bearer <token>` instead of Basic. In that case, separate at least three scenarios:

1. **No bearer token:** depending on configuration, the resource server usually returns `401`.
2. **Malformed, expired, or wrong-issuer/audience token:** verify the authentication failure path and published response.
3. **Valid token lacking scope/authority:** usually returns `403` on endpoints guarded by a specific authority.

To genuinely test authentication, a token must be valid under the **test decoder/verifier** configuration or signed with a test key trusted by the test application. Never copy production JWTs, refresh tokens, client secrets, or real private keys into contracts.

For example, a contract might specify:

```groovy
request {
    method GET()
    url '/api/orders/42'
    headers {
        header('Authorization', 'Bearer TEST_TOKEN_VALUE')
    }
}
```

This is **only an illustrative snippet**, not a valid token or complete contract. Before running tests, replace `TEST_TOKEN_VALUE` with a reproducibly generated test credential matching the application's JWT policy; if tokens expire in CI, establish controlled test issuance or use a test clock/issuer.

Never treat `@WithMockUser` or `.with(jwt())` as a complete substitute for testing signature/issuer/audience/expiry checks. They are great for authorization, while authentication tests must traverse the decoding and verification pipeline.

### 10.1. Should You Assert the Entire JWT Error Body?

Only when consumers genuinely require a stable error schema. `WWW-Authenticate` headers, error codes, messages, and bodies on `401`/`403` can depend on Spring Security, `AuthenticationEntryPoint`, `AccessDeniedHandler`, or custom handlers. Rather than locking down an English error message that may change across versions, protect the HTTP status code and the error code field agreed upon with the consumer.

## 11. CSRF Can Cause Confusing `403` Results

Spring Security typically enables **CSRF** protection on state-changing operations when applications use sessions/cookies. `POST`, `PUT`, `PATCH`, and `DELETE` requests without a valid CSRF token can be rejected with `403`, **even when the principal has permission**.

Example:

```text
POST /api/orders/42/cancel
Authorization: Basic <valid credential>
Content-Type: application/json

{}
```

If the test returns `403`, do not jump to concluding a role is missing. Determine whether it came from **CSRF**, authorization policy, or authentication.

For a stateless API accepting only bearer tokens without automatic browser cookies, CSRF policy may be designed differently. **Never disable CSRF just to make contract tests pass.** When CSRF protection is part of the interface, supply a valid token/cookie in tests and add missing-token cases if consumers need to handle that error.

Spring Security Test can provide a test CSRF token to MockMvc via `.with(csrf())`; that helps in some integration tests, yet **does not appear automatically in generated contract tests**. If producer tests generated from DSL send standard HTTP requests, configure the base class or request data to match how CSRF actually operates.

## 12. Does Stub Runner Test Real Security Filters?

**No.** Stub Runner can use WireMock to simulate `200`, `401`, and `403` responses from described contracts. It does not start the producer's security filter chain or validate credentials using the producer's `AuthenticationManager`.

```mermaid
flowchart TD
    A["HTTP security contracts"] --> B["Generate producer verification"]
    A --> C["Generate HTTP stubs"]
    B --> D["Send requests through real Spring Security filters in test"]
    D --> E["Verify status/headers/body"]
    E --> F{"Producer verification passes?"}
    F -->|No| G["Block build/stub publish"]
    F -->|Yes| H["Publish verified stubs"]
    C --> H
    H --> I["Consumer uses Stub Runner"]
    I --> J["Test client sends credentials and handles 200/401/403"]
```

Two distinct sides of testing:

| Producer verification | Consumer test with Stub Runner |
| --- | --- |
| Sends requests to application context with security filters | Sends requests to stub server |
| Verifies producer enforces authentication/authorization as committed | Verifies consumer sends proper headers and handles sample responses |
| Catches accidentally disabled filters, changed role mappings, or wrong responses | Catches clients dropping headers or mishandling `401`/`403` scenarios |
| Does not automatically test every consumer | Does not prove the live producer still enforces the security policy |

**Matcher warning:** if multiple stubs share `GET /api/orders/42` yet the `401` mapping does not constrain the missing header, mappings can collide. Inspect actual stub mappings, priorities, and consumer tests for all three cases; never assume WireMock distinguishes them properly based solely on contract filenames.

## 13. Which Security Requirements Should Be Tested at Which Layer?

Not every security requirement is best protected by contract tests alone. A layered strategy:

| Goal | Suitable test type |
| --- | --- |
| API returns `401` when credentials are missing | Producer contract test traversing real filters |
| API returns `403` when role/scope is missing | Producer contract test + Spring Security integration test |
| Consumer attaches `Authorization` header to requests | Consumer contract test with real HTTP client and Stub Runner |
| Invalidly signed or expired JWT is rejected | Security integration test with real decoder/verifier in test |
| Users cannot access other users' orders | Authorization/service tests and representative contracts |
| CSRF/session/cookies work properly | Spring MVC/security integration test with real request state |
| Gateway, mTLS, reverse proxy, IdP behavior | Integration/E2E tests in appropriate infrastructure |
| Brute-force defense, rate limits, security logging | Dedicated security/operational tests |

Contract tests catch **interface breakage** in described interactions; they do not replace penetration testing, threat modeling, or whole-system security assessments.

## 14. Common Errors and How to Diagnose Them

### Error 1: Request Without Credentials Still Returns `200`

**Likely cause:** MockMvc did not register security filters, endpoint is `permitAll`, base class applied `@WithMockUser`, or test mode runs only the controller.

**Fix:** inspect `SecurityFilterChain`, `@AutoConfigureMockMvc(addFilters = true)`, profiles, and base class; test a request without headers. Never change a `401` contract to `200` just to make tests pass if the API requires authentication.

### Error 2: Test Expects `403` Yet Receives `401`

**Likely cause:** user `viewer` does not exist, wrong credentials, password encoder mismatch, or token rejected by verifier.

**Fix:** confirm the request **authenticated successfully** before checking roles. Inspect authentication logs and principal authorities in the test environment without logging secrets.

### Error 3: Test Expects `401` Yet Receives `302`

**Likely cause:** app uses form login or a redirecting entry point; `Accept` and security config affect behavior.

**Fix:** verify what JSON/HTTP status the API interface actually commits to. For stateless APIs, configure security/entry points to match requirements rather than changing contracts to match accidental behavior.

### Error 4: Request Has Valid Role Yet Receives `403`

**Likely cause:** wrong `ROLE_` prefix, missing scope, tenant/owner policy, CSRF token, or method security.

**Fix:** check `Authentication.authorities`, `hasRole`/`hasAuthority`, `AccessDeniedHandler` logs, and request type. For POSTs, check CSRF before changing roles.

### Error 5: Consumer Test Always Receives `401` Despite Sending Valid Credentials

**Likely cause:** `401` stub has an overly broad matcher sharing the URL with the `200` stub; missing absence matcher or priority.

**Fix:** inspect generated WireMock mappings and unmatched/near-miss logs. Check which headers the actual request carried and which mapping took precedence; add exact matching criteria supported by your DSL version.

### Error 6: Contract Tests Pass Yet Cross-Tenant Access Is Still Allowed

**Likely cause:** contracts check only roles, omitting resource ownership or tenant checks. `X-Tenant-Id` is not verified against a trusted principal.

**Fix:** add service-layer authorization tests and representative contracts for cross-tenant resources; never rely solely on broad roles.

### Error 7: CI Is Green Yet Generated Tests Never Ran

**Likely cause:** plugin did not generate tests, test classes were not discovered, task/goal was skipped, or the contract group was excluded from the build.

**Fix:** check generator output, generated test count, and executed test count; fail the pipeline if a critical security group suddenly reports 0 tests.

## 15. Complete Practical Workflow

A team implementing security contracts should:

1. **Lock down API policy:** define identities, credential types, roles/scopes, tenants, and `200`/`401`/`403` statuses for each scenario.
2. **Write contracts separating states:** give each request unambiguous inputs; avoid overlapping stub mappings.
3. **Prepare authentication fixtures:** supply valid accounts/tokens and under-privileged users; never use real credentials or production secrets.
4. **Configure the base test properly:** Spring context includes security filters, MockMvc registers filters, and `@WithMockUser` is not applied globally to tests verifying missing credentials.
5. **Generate and run producer contract tests:** confirm requests traverse filters and status/headers/body match commitments.
6. **Run deliberate negative tests:** omit credentials, send bad credentials, drop roles, and try cross-tenant access if the API requires it.
7. **Inspect generated stub mappings:** especially cases sharing method/URL with differing `Authorization`.
8. **Publish stubs only after verification passes:** consumers use Stub Runner to verify client credential sending and response handling.
9. **Integrate into CI:** pin Spring Boot/Cloud/Contract versions, check test counts, classify authentication/authorization errors, and block releases on incompatible APIs.

## 16. Self-Check Exercise

Suppose `Inventory Service` exposes `GET /api/inventory/sku-1` using HTTP Basic:

- `stock-reader` with `ROLE_STOCK_READ` receives `200` and body `{"sku":"sku-1","available":12}`.
- `support-user` is authenticated without `STOCK_READ` and receives `403`.
- Without credentials, receives `401`.
- The system also has `POST /api/inventory/reserve` with CSRF protection per published policy.

Practice tasks:

1. Write three separate HTTP contracts for `200`, `401`, and `403` in Groovy or YAML DSL.
2. For `401`, why might **omitting the Authorization header** in the contract fail to produce a stub matching only requests missing the header?
3. If the generated producer test for `403` returns `401`, would you inspect credentials or roles first?
4. Why does `@AutoConfigureMockMvc(addFilters = false)` defeat the purpose of security testing?
5. If `POST /api/inventory/reserve` returns `403` for a user with sufficient roles, what else besides roles must you check?
6. If `stock-reader` accesses inventory of another tenant, what additional policy should a new contract describe?

**Answer hints:**

| Question | Key point |
| --- | --- |
| 1 | Contracts clearly separate credentials and status; `200` also checks the body |
| 2 | Stub mapping may match method/URL only; needs explicit header-absence condition if supported and mapping inspection |
| 3 | Confirm the user **authenticated first**; checking missing roles only makes sense after authentication succeeds |
| 4 | Requests may bypass security filters, no longer protecting authentication/authorization |
| 5 | Check the CSRF token, along with any other active rules/handlers |
| 6 | Resource/tenant ownership tied to verified identity, never trusting client-declared tenant headers |

### Negative Checks Recommended in CI

Once producer tests exist, proactively test broken cases (on an isolated branch or test environment): accidentally enabling `permitAll`, dropping a required role, disabling filters, or changing protected paths. Those changes must cause the corresponding tests to **fail**. If they still pass, re-examine the base class, generated test count, and executed DSL conditions.

## 17. Pre-Merge Checklist

- Do contracts properly distinguish **unauthenticated** from **authenticated without sufficient permissions**?
- Are credentials, tokens, and identities in tests fake data rather than live secrets?
- Does `SecurityFilterChain` genuinely participate in producer verification, not disabled by MockMvc or profiles?
- Does the base class avoid applying `@WithMockUser` to scenarios testing absent credentials?
- Do `hasRole`/`hasAuthority` and `ROLE_`/`SCOPE_` prefixes match test fixtures?
- Do POST/PUT/DELETE scenarios account for CSRF per API policy?
- Are resource/tenant permissions checked beyond roles when business rules require it?
- Do multiple stubs on the same endpoint have distinct matchers, preventing the `401` mapping from matching valid requests?
- Does CI run generated producer tests and publish only verified stubs to consumers via Stub Runner?

**Reference documentation to check per version:**

- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html).
- [Spring Cloud Contract — Contract Verifier](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html).
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html).
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

**Key takeaway:** An HTTP contract with security aspects must verify that **requests pass through real security filters**, **principals/authorities are recognized accurately**, and **responses match access policies**. With Spring Cloud Contract, define `200`, `401`, and `403` scenarios separately, prepare isolated test data, inspect generated producer tests and stub mappings, and integrate both producer verification and consumer tests into CI. A Stub Runner returning `403` does not prove on its own that the real producer enforces authorization properly.
