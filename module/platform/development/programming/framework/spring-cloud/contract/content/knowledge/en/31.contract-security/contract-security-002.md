# Token Headers, Cookies, and Certificates with Test Data in Spring Cloud Contract

In microservices systems, a consumer can call the right URL and parse the right JSON yet still fail to communicate with a producer due to **missing authentication headers**, **invalid session cookies**, or **a TLS connection rejecting a certificate**. When teams use **Spring Cloud Contract (SCC)**, these parts are easily misunderstood: an HTTP stub can check an `Authorization` string without verifying JWT signatures; a stub can return `Set-Cookie` without managing real sessions; and a contract DSL describing an HTTP response does not automatically verify certificate chains or mutual TLS.

This lesson belongs to the **Contract Security** chapter, covering **Token headers, cookies, and certificates with test data**, guiding how to create safe security fixtures, use **Groovy/YAML DSL** to check the HTTP interface, have **Spring Cloud Contract Verifier** generate **provider verification tests**, publish stubs, and run consumer tests with **Stub Runner**. At the same time, it identifies requirements that must move to **Spring Security integration tests**, **HTTPS/mTLS transport tests**, or appropriate browser/broker testing.

The running example uses `order-producer` exposing `GET /api/orders/1001`, `checkout-consumer` calling the API with a bearer token, and a session-based endpoint for an admin UI. All tokens, cookies, usernames, and certificates mentioned are **simulated data**, not production secrets or certificates.

## 1. Three protection layers that must not be equated

A request can pass through multiple layers:

```mermaid
flowchart TD
    C["Consumer HTTP client"] --> T["TLS: server certificate / optional mTLS"]
    T --> H["HTTP: Authorization, Cookie, headers"]
    H --> S["Security filter: authentication + authorization"]
    S --> A["Controller / business logic"]
    A --> R["HTTP status, headers, JSON response"]
    X["SCC contract / WireMock stub"] -. "Simulates part of the HTTP contract" .-> H
    Y["Transport integration tests"] -. "Verifies trust, hostname, client cert" .-> T
    Z["Security integration tests"] -. "Verifies token, session, roles" .-> S
```

| Layer | Question to answer | Appropriate testing tool |
| --- | --- | --- |
| HTTP contract | Does the consumer send `Authorization`/`Cookie` in the right format and handle 200/401/403? | SCC DSL, generated tests, Stub Runner, WireMock |
| Authentication | Does the token have a valid signature, is it unexpired, and are issuer/audience correct? | Spring Security integration tests, test issuer/JWKS |
| Authorization | Does this principal have permission to read the order for the corresponding tenant? | Security tests with filter chain/permission logic |
| Session | Is the cookie tied to a valid session, and is it rotated/invalidated? | Session integration tests, cookie jar/browser tests |
| TLS | Does the client trust the server certificate and check the hostname? | HTTPS client/server integration tests |
| mTLS | Does the server require a client certificate and verify the trust chain? | TLS handshake tests with test keystore/truststore |
| Operations | Are cert rotation/expiry handled properly? How is an unavailable auth service handled? | Resilience, security, and deployment tests |

**No single request matcher proves all seven layers on its own.** You need to identify whether a test proves the interface, security logic, or actual transport connection.

### 1.1. A passing test has a specific scope

If WireMock receives:

```http
GET /api/orders/1001 HTTP/1.1
Authorization: Bearer contract-test-token
Accept: application/json
```

and returns 200, the test shows **the client sent the expected header string and read the sample body**. It **does not** prove the token was signed by a trusted identity provider, passed `exp` validation, or has permission to read every order.

## 2. Classifying security test data

Only use **test-generated data with clear scope and lifecycle**.

| Fixture type | Example | Can be put in contract/stub? | What must be protected? |
| --- | --- | --- | --- |
| Plain string fake token | `contract-test-token` | Yes, when only testing HTTP matching | Must not be mistaken for a production token |
| JWT signed with test-only key | Token created in test with fake issuer | Conditionally, usually generated at runtime | Do not reuse production private keys |
| Fake session cookie | `session_id=test-session-42` | Yes for request/response matching | Do not use real session IDs |
| Test role/scope | `orders:read`, `orders:write` | Yes in identity fixtures | Separate real permissions from test scopes |
| Self-signed test certificate | Cert for `localhost` in test CA | Should be created in test environment | Private keys stay out of repository |
| Test truststore | PKCS#12 containing only test CA/cert | Can be generated ephemerally in CI | Do not mix with production truststore |
| Real refresh token / API key | No valid example in lesson | **No** | Do not write to Git, JAR, reports, or logs |

### 2.1. Fixture design rules

1. **Clearly identifiable:** prefix with `test-` or use an issuer like `https://issuer.test.invalid`, never resembling real active credentials.
2. **Deterministic where possible:** specify principal, scope, tenant, request path, and sample response.
3. **Ephemeral when private keys are involved:** generate keys/certs in the CI test job or fetch from a test-only secret manager.
4. **Zero production privileges:** test tokens must not be accepted by production endpoints.
5. **No PII leaks:** use `CUS-TEST-42`, never real customer emails/addresses.
6. **Cleaned up:** delete temporary keystores, session fixtures, and request journals containing auth data.
7. **Do not pretend to verify real security:** if only matching a literal token, state clearly that it is a contract test.

### 2.2. Test tokens and test JWTs are different

The string `contract-test-token` is only a **fixture string**. A real JWT has a three-part format, signature, and claims; a test JWT meant to verify signatures must be signed with **a test key trusted by the real verifier under test configuration**.

Do not write `Bearer abc.def.ghi` and assume a standard resource server must accept it; that may only be a string match in WireMock.

## 3. Authorization header: interface structure

Bearer authentication example:

```http
GET /api/orders/1001 HTTP/1.1
Host: order.example.test
Accept: application/json
Authorization: Bearer contract-test-token
```

Distinguish:

- `Authorization` is the **request HTTP header**.
- `Bearer` is an authentication scheme; the value after the space is the credential.
- The actual credential may be an opaque access token or a JWT.
- An API may also use cookie-based sessions or mTLS; those are different mechanisms.
- `WWW-Authenticate` in a 401 response signals the authentication scheme at the HTTP protocol level if used by the server.

Example 401 without credentials:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/json

{"code":"AUTH_REQUIRED"}
```

Example 403 for an authenticated principal lacking permission:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"code":"ORDER_ACCESS_DENIED"}
```

**401 usually relates to being unauthenticated or having invalid credentials; 403 usually relates to being authenticated without sufficient permissions.** An application may intentionally return 404 to avoid exposing resource existence; when so, that security decision must be agreed upon across teams.

### 3.1. Do not treat 401 and 403 statuses as equivalent

A consumer may need to:

- On `401`: refresh the access token via a safe mechanism if supported, or prompt for login.
- On `403`: not repeat the same credential infinitely; display unauthorized or handle a domain error.
- On `429` or `503`: consider retrying per a separate policy, without confusing them with auth failures.

Tests must distinguish these branches; a stub where "every error returns 401" destroys the meaning of the interface.

## 4. Groovy DSL contract checking a test token header

Suppose producer and consumer agreed that a request to read an order must include an `Authorization` header and return JSON when valid.

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Read order with bearer fixture header'

    request {
        method GET()
        url '/api/orders/1001'
        headers {
            header('Accept', 'application/json')
            header('Authorization', 'Bearer contract-test-token')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 1001,
            status: 'CREATED',
            currency: 'VND'
        )
    }
}
```

This contract describes **one specific HTTP request**. When SCC generates the provider test, the test needs a setup so `contract-test-token` is accepted in the **test environment**; if Spring Security is verifying real JWTs, that fake string will be rejected with 401 unless you configure a suitable decoder/test issuer.

### 4.1. One option: controlled acceptance of test fixture tokens by the resource server

You can provide a **test-only authentication component** or fake `JwtDecoder` exclusively for provider contract tests so the header `Bearer contract-test-token` maps to principal `test-user-42` with scope `orders:read`.

This checks that the request path and authorization rules pass through the configured filter chain, but **does not verify production JWT signatures** if the decoder is replaced by a fake. Therefore, an integration test layer verifying cryptographic validation with **a test signing key and real runtime-generated JWTs** is still needed.

### 4.2. Do not use production tokens in contracts

Contract files are committed, shared across repositories, and may be packaged into stubs JARs. A production token in a fixture can persist in Git history, artifact mirrors, and CI logs even after being deleted from the file later.

**If a real secret was ever committed, you must revoke/rotate the credential**, not merely delete the text in a new commit.

## 5. YAML DSL expressing the same Authorization requirement

An example equivalent to Groovy:

```yaml
description: "Read order with bearer fixture header"
request:
  method: GET
  url: /api/orders/1001
  headers:
    Accept: application/json
    Authorization: "Bearer contract-test-token"
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 1001
    status: CREATED
    currency: VND
```

Choose **Groovy or YAML** for the same scenario in a real build to avoid generating duplicate mappings.

The following still need checking:

1. Does the generated provider test send the right header?
2. Are security filters in the producer test context enabled?
3. Does the auth fixture produce the right principal/authorities?
4. Does the producer return the status/body matching the contract?
5. Does the generated WireMock mapping constrain `Authorization` as intended?
6. Does the real consumer produce this header when using Stub Runner?

**SCC does not provide an identity provider or issue valid tokens** just because YAML declares an `Authorization` header.

## 6. Evidence from Stub Runner and WireMock has limits

From the contract above, SCC can generate an HTTP stub mapping. When a consumer test uses Stub Runner:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest(properties = {
    "order.api.base-url=http://localhost:8085"
})
@AutoConfigureStubRunner(
    ids = "com.example:order-producer:1.4.0:stubs:8085",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutConsumerContractTest {
    // Inject real OrderClient and verify response.
}
```

Stub Runner uses the published/installed stubs JAR to run a simulation of the producer. Over HTTP, WireMock can reject requests missing the header because the mapping does not match.

However, you must distinguish **WireMock unmatched 404** from **401 described by a producer security contract**. If the consumer forgets the header and the success mapping does not match, WireMock may return a default 404. You cannot treat that 404 response as proof that the production endpoint returns 404 instead of 401.

### 6.1. A request matcher is not a JWT validator

If a WireMock mapping requires:

```json
{
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/1001",
    "headers": {
      "Authorization": {
        "equalTo": "Bearer contract-test-token"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": 1001,
      "status": "CREATED"
    }
  }
}
```

it only compares the **header value**. If real authentication is omitted on the producer and tests rely only on the stub, tests can pass even though the producer accepts forged tokens at runtime.

### 6.2. Regex for tokens only checks format

A matcher like `Bearer [A-Za-z0-9._~-]+` can be useful to ensure the consumer sends a reasonably structured token, but **does not guarantee signature, issuer, audience, expiration, scopes, or resource ownership**.

Do not use an overly broad regex and call it authentication testing. Identity verification must happen in appropriate security runtime/integration tests.

## 7. Using WireMock to test 200/401/403 by header

If you want to add stubs for the consumer to test error handling, you can declare three mappings **with mutually exclusive conditions**. These are **test-oriented mappings**; in real systems, public API statuses and error codes should be agreed upon with the producer and verified by provider tests.

### 7.1. Valid fixture auth header → 200

```json
{
  "name": "authorized-test-user",
  "priority": 2,
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/1001",
    "headers": {
      "Authorization": {
        "equalTo": "Bearer contract-test-token"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": 1001,
      "status": "CREATED"
    }
  }
}
```

### 7.2. Missing Authorization → 401

```json
{
  "name": "missing-authorization",
  "priority": 1,
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/1001",
    "headers": {
      "Authorization": {
        "absent": true
      }
    }
  },
  "response": {
    "status": 401,
    "headers": {
      "Content-Type": "application/json",
      "WWW-Authenticate": "Bearer"
    },
    "jsonBody": {
      "code": "AUTH_REQUIRED"
    }
  }
}
```

### 7.3. Insufficient permission fixture token → 403

```json
{
  "name": "insufficient-scope",
  "priority": 1,
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/1001",
    "headers": {
      "Authorization": {
        "equalTo": "Bearer contract-test-no-read-scope"
      }
    }
  },
  "response": {
    "status": 403,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "code": "ORDER_ACCESS_DENIED"
    }
  }
}
```

These mappings do not verify token logic themselves: each fixture is tied to a fixed response. A request sending any other arbitrary token may **match no mapping**, resulting in WireMock 404 instead of 401; if behavior for unknown tokens is needed, add a specific controlled mapping and corresponding test, avoiding broad fallbacks that mask request bugs.

### 7.4. Consumer scenario table

| Request | Expected in stub suite | What consumer must assert |
| --- | --- | --- |
| `Bearer contract-test-token` | 200 JSON | DTO and business flow |
| Missing `Authorization` | 401 `AUTH_REQUIRED` | Auth error mapping |
| `Bearer contract-test-no-read-scope` | 403 | Permission denied |
| `Bearer random-string` | No mapping unless defined | Do not interpret unmatched as contract 401 |
| Wrong method/path | Unmatched | Catch client routing error |
| Expired token in security integration test | 401 from real verifier/test issuer | Do not refresh infinitely |

**Do not run all three mappings alongside a `priority=1` catch-all**: a catch-all can shadow specialized scenarios. When SCC generates mappings, check priorities and matchers on the WireMock server.

## 8. Separating authentication and authorization in producer tests

There are at least three testing levels:

| Level | Approach | What it can claim |
| --- | --- | --- |
| Contract/stub | Match `Authorization` string, return sample status | HTTP client and error handling match fixtures |
| Security rule integration | Create test principal with scopes, run filter/authorization rules | Role/scope/ownership rules work under test configuration |
| Cryptographic validation | Sign token with test key, configure decoder/test issuer, send bearer token over real HTTP | Signature, issuer, audience, lifetime, etc. are checked per config |

### 8.1. A Spring Security test principal is not a real signed token

Example Spring MVC test when `spring-security-test` is present:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class OrderAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void userWithReadScopeCanRead() throws Exception {
        mockMvc.perform(get("/api/orders/1001")
                .with(jwt()
                    .jwt(jwt -> jwt.subject("test-user-42"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders:read"))))
            .andExpect(status().isOk());
    }

    @Test
    void userWithoutScopeIsForbidden() throws Exception {
        mockMvc.perform(get("/api/orders/1001")
                .with(jwt()
                    .jwt(jwt -> jwt.subject("test-user-42"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders:write"))))
            .andExpect(status().isForbidden());
    }
}
```

This snippet assumes the application has configured a **Spring Security filter chain** requiring `orders:read` to access the endpoint, the controller has fixture `1001`, and dependencies are compatible. `jwt()` creates a simulated principal without sending/issuing a real signed JWT over the network.

**This test mainly verifies authorization rules, not bearer parsing or JWT signature verification.** For authentication validation, a separate test is required using real tokens signed by a **test-only key** passing through the appropriate decoder/filter configuration.

### 8.2. Be careful when disabling filters in generated provider tests

`@AutoConfigureMockMvc(addFilters = false)` can make auth-protected endpoints easier to call in tests. That may fit some isolated controller tests, but **a pass cannot be used to conclude Spring Security protects the endpoint properly**.

When contracts include 401/403 behavior or auth headers, separate security integration tests or a provider test setup running the filter chain within proper scope is needed. Read generated tests to verify whether requests pass through security.

## 9. JWT fixtures: claims, timestamps, and signing keys

Test JWTs should be created using a dedicated test key/issuer with intentional claims. An illustrative payload:

```json
{
  "iss": "https://issuer.test.invalid",
  "sub": "test-user-42",
  "aud": ["order-api"],
  "scope": "orders:read",
  "tenant_id": "TENANT-TEST-1",
  "iat": 1795500000,
  "nbf": 1795500000,
  "exp": 1795500600
}
```

This is a **sample JSON payload**, not yet a validly signed JWT. The epoch seconds here only illustrate the format; **do not use these fixed timestamps as long-lived test credentials**, because tests will fail once real time passes `exp`.

### 9.1. Key claims matrix

| Attribute | Success case | Rejection case |
| --- | --- | --- |
| Signature | Test private key matching trusted public key | Tampered signature |
| `iss` | Configured trusted issuer | Unknown issuer |
| `aud` | Contains `order-api` audience per validation policy | Wrong/missing audience |
| `exp` | Still valid | Expired |
| `nbf` | Valid time reached | Not yet valid |
| `scope` | Has `orders:read` | Only has `orders:write` |
| `tenant_id` | Matches resource tenant | Different tenant |
| `kid` | Points to trusted test key | Non-existent or rotated key ID |

Depending on the framework, audience validation may require additional configuration; do not assume every resource server validates `aud` merely because the claim exists.

### 9.2. Control time with a test clock

If a test needs a token that "expires after 60 seconds", generate it relative to a **test-controlled clock**, or inject a test clock into the appropriate time-handling layer. Avoid committing a fixed JWT token with a past `exp` and hoping the test keeps passing for years.

When testing `nbf` and `exp`, clarify the clock skew/tolerance policy. An assertion of "expires in exactly one millisecond" is prone to flakiness if it depends on OS clocks, schedulers, or clock drift between containers.

### 9.3. Key rotation should only be tested with test-dedicated keys

With a test JWKS server, you can test two key IDs `test-key-a` and `test-key-b`, checking old/new tokens per rotation policy. Never use a production identity provider's private key or share secrets between test and production.

## 10. Request Cookie and response Set-Cookie: two different directions

In a session-based model:

```http
GET /admin/orders/1001 HTTP/1.1
Cookie: session_id=test-session-42
Accept: application/json
```

The server may respond with a new cookie or a cookie to clear the session:

```http
HTTP/1.1 200 OK
Set-Cookie: session_id=test-session-42; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json

{"id":1001,"status":"CREATED"}
```

**`Cookie` is the header the client sends up; `Set-Cookie` is the header the server sends back.** They are not interchangeable. A test asserting only that `Set-Cookie` appeared does not prove the client/browser stored the cookie and sent it back on the next request.

### 10.1. Meaning of common cookie attributes

| Attribute | Meaning | What tests should check |
| --- | --- | --- |
| `Path` | Restricts paths where cookie is sent | Applied to the right URLs |
| `Domain` | Cookie domain boundary | Not unintentionally widening domain |
| `Secure` | Cookie sent only over secure contexts per client/browser rules | HTTPS tests and browser behavior |
| `HttpOnly` | Disallows normal JavaScript reading via `document.cookie` | Browser/security behavior |
| `SameSite=Lax` | Restricts sending cookie in certain cross-site contexts | Browser integration |
| `SameSite=Strict` | Stricter cross-site policy | Browser integration |
| `SameSite=None; Secure` | Allows cross-site per browser policy, usually requires Secure | Browser integration |
| `Max-Age` / `Expires` | Cookie lifetime | Cookie jar/session expiry tests |
| `Partitioned` if used | Partitioned cookie rules in modern browsers | Browser compatibility tests |

**WireMock does not execute a browser.** It can emit a `Set-Cookie` header, yet it does not prove `HttpOnly` blocked JavaScript or `SameSite` properly protects cross-site requests.

### 10.2. Do not put real session IDs in stubs JARs

Cookie fixtures like `test-session-42` are synthetic data. Never extract `JSESSIONID` or real session cookies from an employee's or user's browser and place them into contracts or CI logs.

## 11. Groovy/YAML contracts for session cookies

Example contract for an endpoint **assuming a test session already exists**:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Read admin page with test session cookie'

    request {
        method GET()
        url '/admin/orders/1001'
        headers {
            header('Cookie', 'session_id=test-session-42')
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
            header('Set-Cookie',
                'session_id=test-session-42; Path=/; Secure; HttpOnly; SameSite=Lax')
        }
        body(
            id: 1001,
            status: 'CREATED'
        )
    }
}
```

Equivalent YAML:

```yaml
description: "Read admin page with test session cookie"
request:
  method: GET
  url: /admin/orders/1001
  headers:
    Cookie: "session_id=test-session-42"
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
    Set-Cookie: "session_id=test-session-42; Path=/; Secure; HttpOnly; SameSite=Lax"
  body:
    id: 1001
    status: CREATED
```

This is an **HTTP contract for specific headers and responses**, not a session issuance mechanism. Producer test setup must create a session fixture or test-only session resolver so the request is accepted when running provider tests.

**In practice, a normal GET endpoint should not be forced to always return the exact same session ID.** The example only illustrates testing an agreed cookie-issuing scenario. For session renewal, login, or logout, write contracts/tests for their proper endpoints and semantics.

### 11.1. When should cookies be checked with a dedicated matcher?

The `Cookie` header can contain multiple `name=value` pairs in varying order along with dynamic values. Matching the entire `Cookie` string can be too brittle. WireMock supports per-name cookie matchers, for example:

```json
{
  "name": "admin-session-test-fixture",
  "request": {
    "method": "GET",
    "urlPath": "/admin/orders/1001",
    "cookies": {
      "session_id": {
        "equalTo": "test-session-42"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": 1001,
      "status": "CREATED"
    }
  }
}
```

Note: **WireMock JSON mapping schema and Spring Cloud Contract YAML schema are two different things**. Do not copy the `cookies` field into SCC YAML without verifying support in your version/plugin. For source contracts, choose syntax confirmed by your SCC version and **inspect the generated WireMock mapping**.

### 11.2. Do not treat a cookie matcher as a session validator

The matcher `session_id=test-session-42` does not check whether the session was revoked, expired, belongs to the right account, or holds admin permissions. Those constraints belong to security/session integration tests.

## 12. Session lifecycle: login, using cookies, logout

A real flow typically has three steps:

```mermaid
sequenceDiagram
    participant U as Client / browser
    participant A as Auth/session service
    participant O as Order API
    U->>A: POST /login (test credentials)
    A-->>U: Set-Cookie: session_id=...
    U->>O: GET /admin/orders/1001 + Cookie
    O-->>U: 200 / 403
    U->>A: POST /logout + session cookie
    A-->>U: Set-Cookie: session_id=; Max-Age=0
    U->>O: GET /admin/orders/1001 + old Cookie
    O-->>U: 401 / redirect per policy
```

A static stub can issue a cookie on the first call and accept a cookie on the next request, but **does not itself manage session state, invalidation, or browser cookie storage**.

To verify the session lifecycle:

- Run the real Spring Security/session implementation in integration tests.
- Use an HTTP client with a cookie jar or browser tests.
- Verify session fixation protection/rotation if required by the application.
- Verify logout invalidates the old session.
- Verify idle/absolute expiration per policy.
- Assert cookie flags (`Secure`, `HttpOnly`, `SameSite`) via response/headers and appropriate browser behavior.

### 12.1. Do not assume every 401 automatically redirects

Browser session apps sometimes redirect to login (302) instead of returning 401 JSON. API clients usually want 401/403. That is an **interface decision to be agreed upon**, not a fixed value of Spring Cloud Contract.

## 13. CSRF and cookie-based authentication

Cookie-based sessions usually require attention to **Cross-Site Request Forgery** because browsers may automatically send cookies according to their policies. Protection mechanisms may require a separate CSRF token for state-changing operations.

Example:

```http
POST /admin/orders/1001/cancel HTTP/1.1
Cookie: session_id=test-session-42
X-CSRF-TOKEN: csrf-test-value
Content-Type: application/json

{"reason":"CUSTOMER_REQUEST"}
```

A contract can verify that the `X-CSRF-TOKEN` header exists on the request, but **does not prove the token is bound to the right session or is random/replay-resistant**. Security filters and the CSRF repository must be tested.

Spring Security MVC testing example:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void rejectsPostWithoutCsrf() throws Exception {
    mockMvc.perform(post("/admin/orders/1001/cancel")
            .with(user("admin-test").roles("ADMIN")))
        .andExpect(status().isForbidden());
}

@Test
void acceptsPostWithCsrfWhenAuthorized() throws Exception {
    mockMvc.perform(post("/admin/orders/1001/cancel")
            .with(user("admin-test").roles("ADMIN"))
            .with(csrf()))
        .andExpect(status().isOk());
}
```

This illustrative snippet assumes `MockMvc`, `user` imported from Spring Security test, filters enabled, the endpoint returning 200 on success, and the application actually having CSRF protection. The code is an **illustrative test method snippet**, not a complete standalone compilable class. A resource server using stateless bearer tokens may have a different CSRF policy: do not mechanically apply the cookie-session model to every API.

## 14. TLS certificates: not HTTP headers

Server certificates are exchanged during the **TLS handshake**, before the HTTP request is passed to the application. They are not header strings like:

```text
X-Client-Cert: ....
```

A gateway may forward client certificate metadata via an internal header after **verifying mTLS**, yet a header sent externally by a caller **does not prove client identity**. Only trust this kind of header when the gateway/proxy is configured to strip client-supplied values and inject authenticated information across a clear trust boundary.

### 14.1. TLS server authentication

Consumer connects to:

```text
https://localhost:<test-https-port>/api/orders/1001
```

The client must verify:

1. The certificate chain leads to a CA/cert trusted by the truststore.
2. The hostname matches a subject alternative name (SAN).
3. The certificate is valid for the current system time.
4. TLS algorithms and policies are configured for the test client/server.
5. Where revocation/OCSP policies exist, those mechanisms are tested separately if needed.

Never disable certificate verification just to make consumer tests pass.

### 14.2. mTLS: mutual authentication

With **mutual TLS**, in addition to presenting its own certificate, the server requires a **client certificate**. You need:

- **Server keystore:** server's private key + certificate.
- **Client truststore:** trusted CA/cert used to verify the server.
- **Client keystore:** client's private key + certificate.
- **Server truststore:** CA/cert used to verify the client.

```mermaid
sequenceDiagram
    participant C as Consumer HTTPS client
    participant S as Producer / test HTTPS server
    C->>S: TLS ClientHello
    S-->>C: Server certificate + certificate request if mTLS
    Note over C: Validate server chain and hostname
    C->>S: Client certificate if requested
    Note over S: Validate client chain and policy
    C->>S: HTTP GET + Authorization/Cookie if present
    S-->>C: HTTP response
```

**TLS authentication and bearer token authentication can coexist.** A valid certificate does not implicitly grant every `orders:read` scope; nor does a valid JWT replace a certificate when the server mandates mTLS.

## 15. Generating test-only certificates and truststores

You can generate a self-signed `localhost` certificate with JDK `keytool` in a **test environment**. The example below is solely for learning how to create a **test server certificate**, not a production CA/PKI:

```bash
keytool -genkeypair \
  -alias localhost \
  -keyalg RSA \
  -keysize 2048 \
  -validity 7 \
  -storetype PKCS12 \
  -keystore server-test.p12 \
  -storepass TEST_ONLY_PASSWORD \
  -keypass TEST_ONLY_PASSWORD \
  -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Export the public certificate from the keystore:

```bash
keytool -exportcert \
  -rfc \
  -alias localhost \
  -keystore server-test.p12 \
  -storepass TEST_ONLY_PASSWORD \
  -file server-test.crt
```

Create the test client truststore:

```bash
keytool -importcert \
  -noprompt \
  -alias localhost-test \
  -file server-test.crt \
  -storetype PKCS12 \
  -keystore truststore-test.p12 \
  -storepass TEST_ONLY_PASSWORD
```

**The commands above are examples to run in a dedicated test workspace, not executed while writing this lesson.** `TEST_ONLY_PASSWORD` must be replaced with an appropriate test value; never use it or these test key files as production secrets. Generate temporary files in CI and delete them according to the job lifecycle instead of committing private keys to Git.

### 15.1. Why is SAN needed?

Many modern TLS clients verify hostnames using **Subject Alternative Name**. A certificate containing only `CN=localhost` without a SAN may be rejected even when the truststore trusts the certificate.

If the test URL uses `127.0.0.1`, the SAN must include that IP address; if it uses `localhost`, an appropriate DNS SAN is needed. **Do not fix hostname mismatch errors by disabling hostname verification.**

### 15.2. Certificates can expire in CI

A certificate committed in test fixtures with a 7-day validity will break the pipeline after one week. The usual solution is to **generate ephemeral certificates when the job runs** or manage a test CA/certificate lifecycle with rotation, rather than setting infinite validity or skipping expiration checks.

When testing certificate expiry policies, use appropriate test clocks/fixtures; you do not need to wait for a real certificate to expire to verify client rejection.

## 16. WireMock HTTPS: testing real connections instead of only matching headers

A WireMock HTTP stub running on `http://localhost:8085` **cannot** test TLS certificate validation because the connection does not use HTTPS.

For the consumer to test its truststore/hostname, start an HTTPS stub server. Example Java DSL with **API/configuration compatible with your WireMock version**:

```java
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;
import static com.github.tomakehurst.wiremock.client.WireMock.*;

import com.github.tomakehurst.wiremock.WireMockServer;

WireMockServer server = new WireMockServer(
    options()
        .dynamicPort()
        .dynamicHttpsPort()
        .keystorePath("build/test-certs/server-test.p12")
        .keystorePassword("TEST_ONLY_PASSWORD")
);

server.start();

server.stubFor(
    get(urlEqualTo("/api/orders/1001"))
        .willReturn(okJson(
            "{\"id\":1001,\"status\":\"CREATED\"}"
        ))
);

int tlsPort = server.httpsPort();
// Client must call https://localhost:<tlsPort>/api/orders/1001
// Stop server in afterEach/finally.
```

This is an **illustrative setup snippet**, not a complete test class. Keystore configuration names and behavior may vary across WireMock versions; verify against the project's actual API and test certificate files.

### 16.1. The client must use a dedicated truststore

A Java HTTP client can be configured with an `SSLContext` from a **test-created** PKCS#12 truststore rather than using a global "trust all":

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.net.http.HttpClient;

char[] password = "TEST_ONLY_PASSWORD".toCharArray();

KeyStore truststore = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(
        Path.of("build/test-certs/truststore-test.p12"))) {
    truststore.load(in, password);
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
    TrustManagerFactory.getDefaultAlgorithm()
);
tmf.init(truststore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(null, tmf.getTrustManagers(), null);

HttpClient client = HttpClient.newBuilder()
    .sslContext(sslContext)
    .build();
```

Next, the test must use this `client` to call the HTTPS stub URL, assert the 200 response or expected exception, and verify the application's real client uses the **corresponding TLS configuration**. This snippet does not describe mTLS because **client key managers** are not configured.

### 16.2. Minimum three HTTPS test cases

| Test case | Test server / client | Expected |
| --- | --- | --- |
| Server cert valid per test truststore | `localhost` cert, client trusts test cert | HTTPS request succeeds |
| Cert not in truststore | Client trusts only another CA | TLS handshake fails |
| Hostname does not match SAN | Client calls a different hostname than cert | TLS validation fails |

Depending on the HTTP client, errors may appear as `SSLHandshakeException`, `SSLPeerUnverifiedException`, or an adapter exception with a corresponding root cause. Do not force every client library to throw the exact same Java exception class if the application API normalizes errors at another layer.

## 17. mTLS: testing with and without a client certificate

For mTLS, the test server must be configured to **require a client certificate** and trust a specific test CA or test client certificate.

Matrix:

| Server requires mTLS | Client cert | Client cert trusted? | Expected |
| --- | --- | --- | --- |
| Yes | None | Not applicable | TLS handshake rejected |
| Yes | Present | Yes | Handshake succeeds, then HTTP/auth checked |
| Yes | Present | No | TLS handshake rejected |
| Yes | Present but expired | Invalid per validation | Rejected |
| No | None | Not applicable | May reach HTTP, depending on bearer/session auth |

Do not use 401 or 403 responses from WireMock to substitute for a **TLS handshake failure** scenario. When the server mandates a client certificate and the handshake fails, typically **the HTTP request never reaches the controller**, so there is no controller-generated HTTP status.

### 17.1. Components to check when configuring mTLS

- Does the test server enable **need client authentication** mode or only optional client certs?
- Does the server truststore contain the test client's exact CA/cert?
- Does the client keystore contain the private key and certificate chain?
- Are key managers passed into the client `SSLContext`?
- Does the server cert have a SAN matching the URL the client calls?
- Do certificates have the proper key usage/EKU per policy?
- Are truststores and test credentials isolated and cleaned up after the job?

**Note:** SCC Groovy/YAML contracts do not provide a simple field to "turn on mTLS for WireMock". That is transport/security test infrastructure configuration; separate tests with a real TLS stack are required.

### 17.2. Client certificate headers injected by a proxy

Some gateways use headers like `X-Forwarded-Client-Cert` to pass metadata of a verified client cert. Consumers must not be able to send that header directly to an exposed backend and have the backend trust it unconditionally. You must test that the proxy **strips client-supplied headers** and only injects values from a verified TLS handshake.

An SCC contract can test that the backend receives the right header at the trust boundary, but **does not replace proxy security integration tests**.

## 18. Secure cookies, TLS, and browser behavior must go together

A contract may return:

```http
Set-Cookie: session_id=test-session-42; Path=/; Secure; HttpOnly; SameSite=None
```

However:

- `Secure` only takes effect when the client/browser enforces HTTPS semantics.
- `HttpOnly` governs JavaScript access to cookies, not whether a Java test can read the header.
- `SameSite=None` in modern browsers usually requires `Secure` and remains subject to other tracking/cookie policies.
- `Path` and `Domain` determine whether subsequent requests carry the cookie.
- `Max-Age=0` can be used to clear a cookie for its matching name/path/domain.

If the goal is ensuring browsers send cookies properly during cross-site navigation, you must use **browser integration tests** with an appropriate origin/HTTPS context. WireMock returning a header string is not enough.

### 18.1. Do not skip certificate checks to test cookies faster

If a cookie is only sent over HTTPS, switching consumer tests to HTTP and dropping `Secure` loses an important part of the behavior. You can have **a simple HTTP contract suite** and **a separate browser/TLS security suite**; do not claim the HTTP suite proved `Secure`/`SameSite` behavior.

## 19. Testing multiple identities: tokens, cookies, and certificates have different owners

In real environments:

| Artifact | Typical owner | Decisions needing coordination |
| --- | --- | --- |
| Bearer access token | Identity provider / auth platform | Issuer, audience, scopes, lifetime |
| Session cookie | Web app / session service | Session store, expiry, rotation, SameSite/CSRF |
| Server certificate | Platform/PKI | CA trust, SAN, renewals |
| mTLS client certificate | Platform/service identity | Identity binding, cert issuance/revocation |
| Resource permission | Producer/domain/security | Who can read/modify each order |
| Stub fixture string | Producer/consumer test teams | Format and committed test behavior |

A consumer team should not unilaterally decide the producer must drop audience validation just to make test tokens convenient; nor should a producer change cookie/permission semantics without notifying dependent consumers.

### 19.1. Tokens and certificates can work together

A system may use:

```text
mTLS client cert -> verify service identity
Bearer token     -> verify user/subject/scopes
Cookie           -> browser session (if applicable)
Resource policy  -> verify tenant/order ownership
```

Each layer can fail independently. Tests should isolate the cause rather than collapsing every error into `AUTH_FAILED` without distinguishing TLS, authentication, authorization, and session expiry.

## 20. Secrets and logs: security right inside testing

Even fake test fixtures should be handled under security principles, because pipelines can accidentally capture real tokens during debugging.

**Do not store in repositories or stubs JARs:**

- Real bearer tokens/API keys.
- Refresh tokens.
- Real users' session cookies.
- Private keys used for production certificates.
- Production keystore/truststore passwords.
- Maven repository credentials.
- Full request journals containing unredacted Authorization headers.

### 20.1. Redact in logs and reports

An unsafe log:

```text
GET /api/orders/1001
Authorization: Bearer LIVE_TOKEN_SHOULD_NEVER_APPEAR_HERE
Cookie: session_id=REAL_SESSION_SHOULD_NEVER_APPEAR_HERE
```

A better log:

```text
GET /api/orders/1001
Authorization: Bearer [REDACTED]
Cookie: session_id=[REDACTED]
TLS: handshake failed, category=UNTRUSTED_SERVER_CERT
```

When storing WireMock request journals or HTTP client debug logs, configure masking for `Authorization`, `Cookie`, `Set-Cookie`, and custom headers carrying credentials. Do not upload full request/response objects as CI artifacts without data controls.

### 20.2. Test-only secrets still need a lifecycle

If CI creates a test private key or keystore password, it is best kept **within the test job**, distributed only to the containers that need it, and deleted after use. Do not attach private key files in default `upload-artifact` steps when only test reports are needed.

When a pipeline needs to share test certs across jobs, consider **transferring only the public cert/trust anchor** while generating the private key inside the job that owns it; if sharing a private key within test infrastructure is unavoidable, enforce encryption, access controls, retention, and cleanup.

## 21. CI matrix: verify HTTP auth and TLS through separate gates

A pipeline strategy:

```mermaid
flowchart TD
    A["Producer PR: contract + code"] --> B["Generate / execute SCC provider tests"]
    B --> C{"Provider tests pass and not skipped?"}
    C -->|No| X["Block candidate"]
    C -->|Yes| D["Package candidate stubs JAR"]
    D --> E["Consumer Stub Runner HTTP tests"]
    C --> S["Producer security tests: JWT/scope/session/CSRF"]
    C --> T["HTTPS/mTLS tests: trust/hostname/client cert"]
    E --> G["Aggregate release gate"]
    S --> G
    T --> G
    G --> H{"Required gates pass?"}
    H -->|No| X
    H -->|Yes| I["Review / promote artifact"]
```

Each suite should state its scope:

| CI job | Minimum evidence |
| --- | --- |
| Contract provider verify | Generated tests execute, HTTP/message assertions pass |
| Stubs artifact | Correct GAV/`stubs` classifier, version/digest |
| Consumer Stub Runner | Real client sends fixture header/cookie, parses 200/401/403 |
| AuthN/AuthZ integration | JWT claim/signature tests, scopes/tenant ownership |
| Session/CSRF | Cookie lifecycle, invalidation, CSRF enforcement |
| TLS server authentication | Truststore, SAN/hostname, handshake errors |
| mTLS | Client cert required/trusted/rejected |
| Secrets hygiene | No real credentials in artifacts/logs |
| Release gate | All required suites pass against the exact candidate |

If the auth service, gateway, or PKI lives outside the producer repository, CI from other teams may be needed. **Do not mark unrun gates as PASS simply because provider contract tests are green.**

### 21.1. Separate fixtures by environment and principal

Example matrix:

```text
Fixture A: test-user-reader, scope orders:read, tenant TENANT-TEST-1
Fixture B: test-user-writer, scope orders:write, tenant TENANT-TEST-1
Fixture C: test-user-reader, scope orders:read, tenant TENANT-TEST-2
Fixture D: no credential
Fixture E: expired test JWT
Fixture F: valid test session cookie
Fixture G: revoked test session cookie
Fixture H: valid server cert, client trust configured
Fixture I: untrusted server cert
Fixture J: mTLS server requires client cert, client sends none
```

You do not need to run every cross-combination if it adds no value. Choose the **security boundaries** that consumers and producers actually depend on.

## 22. A consumer test suite with realistic assertions

Suppose consumer `OrderClient` uses a real HTTP client and maps these cases:

| Test | Input | Business assertion |
| --- | --- | --- |
| Valid reader | `Bearer contract-test-token` | Reads `id/status/currency` accurately |
| Missing token | No `Authorization` sent | Returns `Unauthenticated`/triggers login flow per policy |
| Missing scope | `Bearer contract-test-no-read-scope` | Returns `Forbidden`, does not retry infinitely |
| Expired token | Token signed with test key, `exp` passed | 401 from security integration, valid refresh/logout |
| Valid session cookie | Cookie jar holds test session | Client sends cookie for right host/path and parses response |
| Revoked cookie | Session invalidated | Subsequent request is not treated as authenticated |
| Untrusted TLS CA | Cert absent from truststore | HTTP request does not succeed |
| mTLS missing client cert | Server requires client auth | Handshake fails, not faked as 401 |

### 22.1. Example verifying the HTTP request sent to the stub

A WireMock test can verify:

```java
import static com.github.tomakehurst.wiremock.client.WireMock.*;

wireMockServer.verify(
    1,
    getRequestedFor(urlEqualTo("/api/orders/1001"))
        .withHeader(
            "Authorization",
            equalTo("Bearer contract-test-token")
        )
);
```

This example verifies the **HTTP interaction** after the consumer actually calls `OrderClient`. It does not validate the token's signature or permissions, and the request journal log may contain the fixture header. For real tokens, avoid writing values into assertion messages/logs.

### 22.2. Do not craft requests on behalf of the consumer

If a test only uses `curl` or a separate ad-hoc `HttpClient` outside the application to send the right header, it has not tested the real consumer's interceptor, token propagation, or cookie jar.

To gain real value, tests must invoke the **product's use case or client**, where Authorization/Cookie headers are built and response/security exceptions are handled.

## 23. Common errors and how to diagnose them

| Symptom | Common cause | Where to check |
| --- | --- | --- |
| Stub returns 404 when token is forgotten | Mapping does not match, WireMock unmatched | Request journal and mapping; do not confuse with contract 401 |
| Contract has fake token but provider test fails 401 | Real security verifier rejects fixture | Test issuer/decoder setup and filter chain |
| Provider test passes even though route is accidentally public | Security filters disabled | Test config and security integration |
| WireMock returns 200 for any token | Regex/catch-all matcher too broad | Constrain mapping and separate JWT integration |
| Token has valid signature but fails 401 | Wrong `iss`/`aud`/`exp`/`nbf`/`kid` | Redacted JWT decoder logs and test clock |
| Valid token fails 403 | Missing scope or wrong tenant/ownership | Authority mapping and domain policy |
| Cookie header present but server rejects | Domain/path/session store/sameSite/expiry | Session/browser integration |
| Cookie returned but browser does not store | `Secure` over HTTP, SameSite/Domain policy | Browser devtools/test environment |
| Still accessible after logout | Session not invalidated | Test session lifecycle and cache |
| HTTPS fails before controller | Cert/hostname/truststore mismatch | TLS handshake, SAN, trust anchors |
| mTLS fails despite bearer token | Missing client certificate or server does not trust client | mTLS configuration, key/trust stores |
| HTTPS test passes after "trust all" | TLS validation was disabled | Remove bypass, use test truststore |
| CI certificate expires after a few days | Fixed/non-rotating test cert | Generate ephemeral cert or manage test PKI |
| Test passes locally but fails in CI | Ports, clocks, test certificates, profiles, secrets | Isolate and record toolchain/environment |
| Stubs artifact leaks token | Test used real credential | Revoke token, remove from artifact/Git history per process |

### 23.1. Layer-by-layer troubleshooting runbook

```text
1. Determine whether the request uses http:// or https://, and whether mTLS is required.
2. If TLS fails: check truststore, SAN/hostname, and client certificate.
3. If an HTTP response arrived: distinguish 401, 403, and unmatched 404.
4. Confirm the consumer client sent Authorization/Cookie as expected.
5. Match the request against the selected WireMock mapping.
6. Confirm token/cookie fixtures exist only in the test environment.
7. On the producer, check filter chain, test issuer/decoder, and scope/tenant logic.
8. On the consumer, check auth interceptor, cookie jar, and retry/error mapping.
9. Confirm the stubs JAR version/classifier belongs to the candidate under test.
10. Review test reports and redacted logs; never copy secrets into tickets.
```

**Do not change every error to HTTP 200 in a stub just to make CI green.** If the consumer lacks a scope or the TLS client rejects the server certificate, changing the stub response only hides the real problem.

## 24. Practice: build three suites protecting security interfaces and mechanisms

Prepare a Spring Boot producer with Spring Cloud Contract and Spring Security, a consumer using Stub Runner, plus WireMock/test certificates strictly for a learning environment.

1. **Define the contract:** Write `GET /api/orders/1001` with `Authorization: Bearer contract-test-token` and a 200 response in Groovy.
2. **Convert DSL:** Write the equivalent YAML on a separate branch; do not keep two duplicate contracts for the same scenario in one build.
3. **Provider verification:** Configure the base test/filter chain and test-only authentication fixture; run generated tests.
4. **Induce failure:** Remove `Authorization` from the generated provider test request or fixture and confirm behavior no longer matches the contract.
5. **Publish stub:** Build the stubs JAR with classifier `stubs`, and verify the WireMock mapping constrains the header.
6. **Consumer Stub Runner:** Run the real client with the fake token and assert DTO/business success path.
7. **Missing credential:** Add a 401 stub with `Authorization.absent` matcher; assert the consumer handles unauthenticated.
8. **Insufficient permission:** Add a 403 stub for test-only token `no-read-scope`; assert no infinite retries.
9. **Security integration:** Write Spring Security tests with principal having `orders:read`, missing scope, and wrong tenant.
10. **JWT signature:** Generate runtime JWTs using a test key and test issuer; test valid, tampered, expired, and wrong issuer/audience.
11. **Cookie header:** Write a session fixture contract and `Set-Cookie` response, checking path/flags.
12. **Cookie jar:** Use an HTTP client/browser test through login → request → logout; verify the old session is rejected.
13. **CSRF:** For session-based POST, verify requests without CSRF are rejected per security policy and valid requests succeed.
14. **Test HTTPS:** Create a `localhost` certificate with SAN and a dedicated truststore; run WireMock HTTPS.
15. **Negative TLS:** Call with a client that does not trust the test cert; verify handshake fails.
16. **Hostname:** Try a URL host not matching SAN; do not disable validation to "fix" it.
17. **mTLS:** In an environment configured with the server requiring client certs, test valid client, missing cert, and untrusted cert.
18. **Logs:** Check request journals, CI reports, and artifacts contain no real tokens, cookies, or private keys.
19. **CI gates:** Separate provider contract, consumer stub, auth integration, and HTTPS/mTLS suites; verify the gate fails when a required suite fails.
20. **Summary:** Write a table showing which tests prove HTTP, authentication, authorization, cookie/session, or TLS layers.

### 24.1. Self-assessment checklist

| Competency | Evidence achieved |
| --- | --- |
| Distinguish boundaries | Do not confuse a header matcher with JWT verification |
| Token fixtures | Do not use production credentials in contracts |
| SCC Groovy/YAML | Can verify request Authorization and response |
| 401/403 | Consumer has assertions separating auth from permission |
| WireMock | Understand unmatched 404 and static mapping limits |
| Spring Security | Test scopes, tenants, and filter chain within proper scope |
| Cookies | Distinguish `Cookie`/`Set-Cookie` and flags |
| Sessions | Test rotation/revocation/expiry via integration |
| TLS | Verify truststore and SAN without disabling certificate checks |
| mTLS | Understand client keystore/server truststore and handshake failures |
| Data hygiene | No tokens, cookies, or private keys leaked via Git/JAR/logs |
| CI | Multiple complementary test gates and exact-version candidate stubs |

## 25. Conclusion: the right fixtures verify the right security layer

**Spring Cloud Contract** helps producers and consumers describe, verify, and consume **agreed HTTP/message interfaces**. For **token headers and cookies**, Groovy/YAML contracts and WireMock stubs can verify request/response shapes, header propagation, and error-code handling. However, **a string-matched fake token is not a valid JWT**, **a cookie stub is not a session store**, and **TLS certificates do not live in HTTP contract bodies/headers**.

Apply four principles:

1. **Test-only data:** use synthetic tokens/cookies and test-only certs/keys; never put production secrets in source or artifacts.
2. **Right tool for the right layer:** contract tests for interfaces, security integration for claims/scopes/sessions, HTTPS/mTLS tests for trust and handshakes.
3. **Protect the real client:** consumer tests must call the application's client/listener, not just hit WireMock with separate test code.
4. **CI chain of evidence:** provider verification passes, candidate stubs match the exact version, consumer assertions pass, and required security gates are not skipped.

When **matching**, **authentication**, **authorization**, **session**, and **TLS** are clearly separated, teams avoid false conclusions like "the stub returned 200 so the token is secure", while catching API or security configuration changes early before producer and consumer become incompatible.
