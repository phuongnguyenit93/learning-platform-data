# Verifying Authenticated Requests with Test Data

In microservice applications, consumers often must send **authentication credentials** when calling producer APIs. For instance, the **Billing** service calls `GET /api/accounts/42` to read a customer's account, including an `Authorization: Bearer ...` header. If the producer changes its authentication mechanism, requires a different scope, or returns a different error code than committed, the consumer can fail even when the path and JSON structure stay the same.

With **Spring Cloud Contract**, teams can describe requests with authentication headers in **Groovy DSL or YAML DSL**, generate producer-side tests, create stubs for consumers to test with **Stub Runner**, and integrate checks into CI. However, you must understand the boundary: **contract tests check the described communication behavior**, whereas verifying JWT signatures, token expiration, user-level authorization, and real security configuration must be tested with the **security filter chain** or appropriate security tests.

This lesson belongs to the **Request HTTP** chapter. The goal is to prepare **reproducible authentication test data**, write contracts for `200`, `401`, and `403` scenarios, ensure the producer enforces expectations properly, and avoid mistaking a stub returning the right response for proof that an API is securely protected.

## 1. What Does "Verifying an Authenticated Request" Mean?

Consider an API for logged-in users:

```http
GET /api/accounts/42
Accept: application/json
Authorization: Bearer contract-reader-token
```

The producer needs to determine which user the request belongs to, whether the token is accepted, and whether that user is authorized to view account 42. If all conditions pass, an expected response is:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "ownerId": "user-42",
  "currency": "VND",
  "balance": 850000
}
```

From the consumer perspective, a useful contract describes **what is observable at the HTTP boundary**: method, URL, required headers, success response, error codes, and the data the consumer uses. Internal details such as the user table name or how the producer caches tokens do not necessarily belong in the contract.

Different testing layers must be distinguished:

| Layer | Question | Common Tools/Techniques |
|---|---|---|
| **Request contract** | Does the consumer send the exact headers, endpoint, and format required by the producer? | Spring Cloud Contract DSL and generated producer tests |
| **Behavior contract** | Given defined user/permission test data, does the producer return `200`, `401`, or `403` and the committed body? | Generated producer tests with authentication and business fixtures |
| **Security integration** | Do the filter chain, token decoder/introspector, access permissions, and expiration checks work? | Spring Security integration tests, MockMvc, or a test environment with real auth |
| **Consumer integration** | Does the consumer's HTTP client attach the token and handle responses properly? | Stub Runner, consumer's real HTTP client |
| **End-to-end** | Does the system authenticate properly against the identity provider, gateway, TLS, and real resources? | Integration/E2E tests in an appropriate environment |

No single row replaces all the others. For example, if Stub Runner returns `200` when seeing `Bearer contract-reader-token`, that **does not prove** the token's signature was verified or that it belongs to a real account.

## 2. Preparing Test Data Before Writing Contracts

Authentication contracts can only be tested if teams clearly define **identities, permissions, resource data, and responses**. Avoid writing a `200` contract and letting producer verification depend on random users in a shared database.

Suppose the producer is **Account Service** and the consumer is **Billing**. In a dedicated contract test environment, agree on a fixture set:

| Fixture | Meaning | Expected Outcome for `GET /api/accounts/42` |
|---|---|---|
| `contract-reader-token` | Valid test token for `user-42`, with `accounts.read` permission | `200 OK`, returns account 42 data |
| `contract-invalid-token` | Invalid test token | `401 Unauthorized` |
| `contract-no-scope-token` | Authenticated, but missing `accounts.read` | `403 Forbidden` |
| No `Authorization` | No authentication credentials supplied | Usually `401 Unauthorized` for Bearer APIs |
| `contract-other-user-token` | Has resource-type read permission, but does not own account 42 | `403` or `404` depending on resource-hiding policy |
| Account ID `42` | Exists, owned by `user-42` | Fixed data: `currency=VND`, `balance=850000` |

**Token names in this table are illustrative dummy strings**, never default valid access tokens. For the producer to accept them, the **test profile must include a test authentication setup** defining how these fixture strings map to identities and permissions. If the producer uses real JWTs, a string like `contract-reader-token` will be rejected by the JWT decoder; in that case, use test JWTs signed with a test-only key or a dynamic token-issuance mechanism compatible with the DSL/build.

The fixture set must specify:

1. **User ID:** who is calling, e.g. `user-42`.
2. **Permissions/scopes:** which endpoint is allowed, e.g. `accounts.read`.
3. **Resource attributes:** who owns account 42, which tenant it belongs to, and its data.
4. **Rejection cases:** missing/invalid/expired token, authenticated but insufficient permissions.
5. **Time:** if checking JWT `exp`/`nbf`, use a controllable clock or generate tokens at runtime so fixtures do not silently expire after a few weeks.
6. **HTTP output:** status code, headers such as `WWW-Authenticate`, and published error schema.

Example data in a test profile—this is an **illustrative mapping table**, not a configuration file automatically read by Spring Cloud Contract:

```yaml
testIdentities:
  contract-reader-token:
    subject: user-42
    scopes: [accounts.read]
    active: true
  contract-no-scope-token:
    subject: user-42
    scopes: [profile.read]
    active: true
  contract-invalid-token:
    active: false
testAccounts:
  - id: 42
    ownerId: user-42
    currency: VND
    balance: 850000
```

The real application must **implement fixture loading and token checking** in its test configuration; Spring Cloud Contract does not read this `testIdentities` table on its own. You can use a test implementation of a token introspector, a JWT generator signed with a test-only key, or a test identity provider. Never use production credentials or private keys.

## 3. Designing an HTTP Scenario Matrix

Start with paths that directly affect the consumer:

| Scenario | Authentication | Authorization | Typically Expected HTTP | What Consumer Must Handle |
|---|---|---|---|---|
| Valid account read | Valid token | Sufficient permission, right owner | `200` | Parse and use JSON |
| Missing Bearer token | Unauthenticated | Not evaluated | `401` | Re-authenticate, supply credentials, or handle error |
| Invalid/expired token | Failed | Not evaluated | `401` | Refresh token if policy allows; do not retry infinitely |
| Authenticated, missing scope | Succeeded | Denied | `403` | Display insufficient permission or stop action |
| Has scope, wrong owner | Succeeded | Denied | `403` or `404` | Follow API policy; do not guess permissions |
| Account does not exist | Succeeded | May have resource-type permission | `404` | Handle missing resource |

**`401` and `403` are not synonymous.** With Bearer authentication, `401` usually applies when the request is not validly authenticated; `403` usually applies when authenticated but lacking permission. However, an API may intentionally return `404` to avoid leaking resource existence; contracts must follow the **agreed policy** rather than imposing a single status code across all systems.

With OAuth2 Bearer, many APIs include a `WWW-Authenticate` header when authentication is challenged, per configuration and applicable standards. Only declare exact header values if the producer **truly commits** to that structure and the consumer depends on it.

## 4. Groovy DSL: Verifying Requests Carrying a Valid Bearer Token

Example success contract for Billing calling Account Service. Assume the test profile is configured to accept `contract-reader-token` as identity `user-42` with scope `accounts.read`.

Illustrative file: `src/test/resources/contracts/billing/get_account_authorized_200.groovy`.

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'billing_get_account_authorized_200'
    description 'Billing reads account using a token with accounts.read permission'

    request {
        method GET()
        url '/api/accounts/42'
        headers {
            header 'Accept', 'application/json'
            header 'Authorization', 'Bearer contract-reader-token'
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            ownerId: 'user-42',
            currency: 'VND',
            balance: 850000
        )
    }
}
```

### 4.1. What Does This Contract Verify?

When Spring Cloud Contract is integrated properly with producer tests, the generated test sends a request containing `Authorization` and compares the response against DSL expectations. If the producer:

- misses the header or rejects the test token, the test may return `401`;
- accepts the token yet disallows `accounts.read`, the test may return `403`;
- returns `200` with missing `currency` or turns `balance` into a string, the test fails when corresponding assertions are generated;
- returns `200` with matching fields, the test passes for the described scenario.

**Critical condition:** generated tests must actually pass through the security configuration the system intends to test. If the test base uses a standalone controller and bypasses Spring Security filters, a green test **does not prove** the `Authorization` header was verified.

In addition, because the contract uses fixed value `contract-reader-token`, producer tests must **have the data and mechanism to accept this token**. Never replace a real token with a dummy string and expect full security checks to magically work.

### 4.2. When to Use Matchers for the `Authorization` Header?

In real applications, access tokens often vary by time, environment, or user. A contract locking down a single literal JWT string can make tests brittle. You may need a **request matcher** describing the Bearer format rule, or a mechanism generating values from test setup.

However, keep these distinct:

- A **format matcher** such as `Bearer <token>` only proves the header matches a pattern; **it does not prove the token authenticates successfully**.
- The **concrete value used by the producer test** must still be accepted by the producer environment.
- A **stub mapping** might match a broad header pattern; if overly broad, the stub returns `200` for tokens that the real producer would reject.
- **Security verification** must validate signature/expiry/issuer/audience/scope with a real mechanism or a clearly scoped test double.

Because DSL matcher syntax and `consumer/producer` distinction vary across versions, use the matcher API from the **Spring Cloud Contract documentation pinned for your project**. Avoid copying a regex that "accepts any token" without understanding how the generated producer request and WireMock mapping behave.

## 5. YAML DSL: Expressing the Same Behavior Structurally

If a team prefers YAML for easily reviewable contract specs, an equivalent definition looks like:

Illustrative file: `src/test/resources/contracts/billing/get_account_authorized_200.yml`.

```yaml
name: billing_get_account_authorized_200
description: Billing reads account using a token with accounts.read permission
request:
  method: GET
  url: /api/accounts/42
  headers:
    Accept: application/json
    Authorization: Bearer contract-reader-token
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    ownerId: user-42
    currency: VND
    balance: 850000
```

This YAML expresses the **same scenario** as the Groovy example in section 4. In a repository generating tests/stubs, **keep only one file as the primary source** for that request, unless you intentionally want multiple contracts with distinct match conditions. Keeping both can generate duplicate tests or two mappings matching the same request.

For the JSON body, notice `42` and `850000` are YAML numbers, while `user-42` and `VND` are strings. Changing types can break consumers even when the response remains valid JSON.

### 5.1. Other Headers Potentially Related to Auth

Besides `Authorization`, depending on the API there may be:

| Header / Attribute | Use Case | Note in Contracts |
|---|---|---|
| `Cookie` | Session-based authentication | Do not write real session IDs; prepare appropriate session fixtures |
| `X-API-Key` | API-key authentication | Use only dummy test keys or values from test environment |
| `X-Tenant-Id` | Tenant routing per API contract | This header **does not prove permission on its own**; producer must check against token/identity |
| `X-Correlation-Id` | Request tracing | Not an authentication mechanism |
| `X-CSRF-TOKEN` or project variant | Protecting state-changing operations in session apps | Test if real app requires it; do not assume every Bearer API sends CSRF tokens |
| `Accept` and `Content-Type` | JSON format negotiation | Do not replace auth, though they may participate in matchers/responses |

Contracts must reflect the **producer's real interface**, without adding headers merely to make stubs match a test scenario.

## 6. Contract for an Invalid Token: `401 Unauthorized`

For consumers, `401` matters because it can trigger re-login or a token-refresh flow. A scenario with an **explicitly specified invalid token** also lets the stub distinguish its mapping from requests carrying a valid token.

Groovy example:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'billing_get_account_invalid_token_401'
    description 'Billing receives 401 when Bearer token is invalid'

    request {
        method GET()
        url '/api/accounts/42'
        headers {
            header 'Authorization', 'Bearer contract-invalid-token'
        }
    }

    response {
        status 401
        headers {
            header 'WWW-Authenticate', 'Bearer'
        }
    }
}
```

**Execution precondition:** the producer's security configuration in the test environment must reject `contract-invalid-token`, and if the contract requires `WWW-Authenticate: Bearer`, the real producer must return that header. Do not invent an error body or `error_description` message if the API does not publish them.

### 6.1. Is a Missing Token Different from an Invalid Token?

Both scenarios commonly return `401`, yet their **requests differ**:

```http
GET /api/accounts/42
Accept: application/json
```

and:

```http
GET /api/accounts/42
Authorization: Bearer contract-invalid-token
```

For producer tests, you can write a separate contract for the missing-header case and check status. However, when **packaging HTTP stubs**, a mapping specifying only `GET /api/accounts/42` **without constraining Authorization absence** can also match requests carrying a valid token. If two mappings return different `200`/`401` results, the stub server may pick an unintended mapping.

Therefore:

1. Inspect the actual mapping generated by the plugin from the contract.
2. When a "header absent" scenario is needed, define an **absent-header** condition using a matcher supported by your DSL/WireMock version, or test this case against the real security layer in the producer.
3. Never rely implicitly on file load order or mapping priority.
4. Run consumer tests with **both tokened and tokenless requests**, ensuring the stub never accidentally returns `401` for a valid request.

For Bearer flows, include a **direct security integration test** for the missing-token case even when a `401` contract exists.

## 7. Authenticated but Insufficient Permission: `403 Forbidden`

A request with an accepted token may still lack access rights. For instance, the user has scope `profile.read` while the API requires `accounts.read`.

YAML DSL for this scenario:

```yaml
name: billing_get_account_insufficient_scope_403
description: Token is authenticated but lacks permission to read account
request:
  method: GET
  url: /api/accounts/42
  headers:
    Authorization: Bearer contract-no-scope-token
response:
  status: 403
```

The producer test profile must map `contract-no-scope-token` to an **authenticated** identity lacking the required scope. If this token is treated as completely invalid, the producer returns `401` and the test fails. That indicates the fixture simulates the wrong scenario, not a reason to arbitrarily change `403` to `401`.

**Note on resource-level authorization:** a user holding scope `accounts.read` is not necessarily allowed to read **every** account. For example, `contract-other-user-token` may be denied access to account 42 despite holding the broad scope. To protect ownership boundaries, add scenarios testing `ownerId` or `tenantId` with corresponding test data.

### 7.1. Do Not Turn Contract Testing into Full Security Policy Testing

You can describe error cases the consumer must handle, while detailed combinations such as millisecond-exact JWT expiration, `nbf`, wrong issuer, wrong audience, revoked signing keys, mTLS, and nested roles are usually better suited to **dedicated security integration tests**.

Example expanded security matrix:

| Case | Layer Primarily Responsible |
|---|---|
| Missing `Authorization` → `401` | Contract if consumer depends on it; security integration should also cover it |
| Invalid test token → `401` | Contract and security integration |
| Valid token missing scope → `403` | Contract and security integration |
| JWT with wrong signature/issuer/audience → rejected | Security integration with real decoder/introspector |
| Expired token → rejected | Security integration with controllable clock |
| Authorization by `ownerId`/tenant | Security/integration with data fixtures |
| Success body must include `id`, `currency`, `balance` | Contract between producer and consumer |

This separation keeps contracts focused while still verifying essential security controls.

## 8. Configuring Producer Tests So Authentication Is Not Accidentally Bypassed

Spring Cloud Contract generates tests from the DSL, but tests are trustworthy only if the **test base** loads the real application properly and **goes through the Spring Security filter chain**. Projects may use MockMvc, RestAssured, or another web environment depending on plugin version and configuration.

For a Spring MVC producer using MockMvc, a common setup pattern is:

```java
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
public abstract class ContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
```

This is an **example test base**, not a complete configuration to enable Spring Cloud Contract in every project. You also need to:

- Configure the test-generation plugin to use `ContractTestBase` and **the MockMvc-compatible test mode**.
- Declare compatible dependencies for your Spring Boot, Spring Cloud Contract, and RestAssured MockMvc versions.
- Supply account 42 data and authentication fixtures to the test context.
- Ensure the Spring Security filter chain is loaded and active; `addFilters = true` lets filters participate in `MockMvc`, though it does not create security beans by itself.
- If the application uses Spring WebFlux or another test mode, use the corresponding base/test setup rather than copying the MVC example verbatim.

What to observe after running is that the `200` test **passes only with a valid token**. If removing the token still causes the controller to return `200`, security filters are likely bypassed, the test profile grants overly broad permissions, or the endpoint is unprotected.

### 8.1. Avoiding Configurations That Undermine Authentication Verification

Common mistakes:

- Using `MockMvcBuilders.standaloneSetup(controller)` and assuming the security filter chain is active. With standalone setup, filters must be registered explicitly; otherwise endpoints may return `200` with no token.
- Putting `@WithMockUser` or a mocked `SecurityContext` on **every** generated contract test. This causes the "invalid token" scenario to run with a valid mock identity and stops testing actual request headers.
- Disabling all security for the test profile via a blanket `permitAll()` rule. The `200` test passes effortlessly while verifying nothing about auth headers.
- Using expired test tokens or account fixtures that change across a shared environment. Failing tests then reflect flaky data rather than API changes.

Mock identities or test token decoders **can be useful**, provided boundaries are clear: they simulate identities/scopes in contract tests, while separate security tests verify real signature/expiry/authority mapping.

### 8.2. Additional Check Confirming Filters Are Active

A direct security integration test via `MockMvc`, independent of the DSL, might look like:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class AccountSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void requiresAuthentication() throws Exception {
        mockMvc.perform(get("/api/accounts/42"))
            .andExpect(status().isUnauthorized());
    }
}
```

This test makes sense when the endpoint enforces a `401` policy for requests lacking credentials. It verifies protection inside the app context; it **does not replace producer contract tests** verifying committed consumer responses.

## 9. Preparing Reproducible Test Tokens

Never put production JWTs or tokens copied manually from user sessions into `.groovy`, `.yml`, CI logs, or stub artifacts. Such tokens can expire, be revoked, or leak sensitive data.

Two common design approaches:

### 9.1. Approach A — Test-Specific Token Verifier/Introspector

In the test profile:

- Receive `contract-reader-token` → identity `user-42`, scope `accounts.read`.
- Receive `contract-no-scope-token` → identity `user-42`, scope `profile.read`.
- Receive `contract-invalid-token` → report invalid.
- No Bearer token → follow the security filter's real `401` flow.
- Account 42 data is freshly created or reset before each run.

Advantages are **stable fixtures, readable contracts, and fast tests**. The limitation is that the verifier/introspector is a **test double**; it does not prove the producer integrates properly with the real identity provider or decodes real JWTs. Separate security integration tests are required.

Important: enable the test verifier only in the test profile; never let the production application accept `contract-reader-token`.

### 9.2. Approach B — Test JWTs with Controlled Signing and Time

If you want to pass through a real JWT decoder:

1. Generate a key pair or secret **exclusively for tests**; never use production keys.
2. Mint tokens containing `sub=user-42`, issuer, audience, and exact scopes/roles expected by the producer.
3. Use a controllable clock, or mint fresh tokens at the start of each test run to prevent expiration.
4. Create tokens missing scopes, with invalid signatures, wrong issuers, or expired timestamps for dedicated security tests.
5. When the contract DSL needs a fixed header value, design a token/matcher mechanism supporting **dynamic producer-side values** compatible with your Spring Cloud Contract version; never hardcode an expiring JWT into files expected to last for years.

Approach B exercises deeper verification but requires finer setup for generated tests. Beginners can start with Approach A to grasp producer–consumer contracts, then add security integration tests with the real decoder.

### 9.3. Business Data Must Also Be Stable

Even a valid token can receive `404` if account 42 has not been created yet, or `403` if the account owner does not match `user-42`. Seed test data **before generated tests run** and clean up afterward, or use transactions/testcontainers/fixture isolation appropriate for your project.

Avoid depending on:

- Real users in production or shared staging.
- Tokens copied by a developer from a browser.
- Uncontrolled random account IDs.
- Desynchronized CI clocks during expiration tests.
- User permissions mutated by other tests.

## 10. Consumer Using Stub Runner to Verify Sending `Authorization`

Once producer contract tests prove the implementation satisfies the contract, the build can package mappings into a **stub artifact**. The consumer downloads the stub via Stub Runner, points its HTTP client to the stub server, and invokes the API.

Example Stub Runner configuration in a Billing Spring Boot test:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:account-service:1.0.0-SNAPSHOT:stubs:8085",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class AccountClientContractIntegrationTest {
    // Configure Billing's client to call http://localhost:8085.
    // Write @Test methods verifying the client attaches Authorization and handles 200/401/403.
}
```

This is a **test environment declaration**, not a complete JUnit test. Prerequisites to run: compatible Stub Runner dependency, stub artifact installed in the local Maven repository, and port `8085` available. For parallel runs, use a dynamic port and obtain it from Stub Runner. Pipelines using remote repositories must configure `stubsMode` and the corresponding artifact repository.

Consumer tests must **exercise Billing's real HTTP client**, such as an adapter attaching `Authorization: Bearer contract-reader-token` and parsing `currency`/`balance`. If a test calls the stub server directly via a separate test client, it can miss bugs in Billing's header-attachment code.

### 10.1. Stub Runner Does Not Replace Producer Authentication

An HTTP stub typically relies on **WireMock request matching**. It can return `200` because the request contains the exact `Authorization` string recorded in the mapping, yet it:

- does not validate real JWT signatures;
- does not automatically check token expiration;
- knows nothing about real account state or ownership policies;
- may return a **stub server** `404` when a request matches no mapping, which **differs** from the API's business `404`.

For instance, suppose the consumer forgets to send `Authorization`: if only the `200` mapping requiring the header exists, WireMock fails to find a match and returns the stub server's default response. Never assume the real producer returns that exact status/body. To test `401`/`403` handling on the consumer, create explicit mappings or isolated error-simulation tests, alongside matching security tests on the producer.

### 10.2. Verifying That the Client Actually Sends the Token

In consumer tests:

1. Point the Account Service endpoint URL to Stub Runner.
2. Use a **test credentials provider** supplying `contract-reader-token`.
3. Call the real client method such as `accountClient.getAccount(42)`.
4. Verify the `200` body maps into Billing's model properly.
5. Supply invalid/no-scope tokens in scenarios with matching mappings and verify how Billing handles `401`/`403`.
6. Run an additional case without the header if the consumer must proactively handle missing credentials; check exact responses/mappings rather than inferring from an unmatched stub request.

This test catches consumer-side regressions, such as code dropping the `Bearer ` prefix, renaming the header, or picking a token from the wrong environment.

## 11. Preventing Auth Data Leaks in Contracts and CI Reports

Contract DSLs, stub artifacts, generated tests, and CI logs are often read by many people and systems. Therefore, auth data used in examples must **not contain real secrets**.

| Do | Avoid |
|---|---|
| Use placeholder tokens or test-environment-only tokens | Committing real access tokens or personal refresh tokens |
| Use dedicated, isolated test signing keys | Reusing production signing keys |
| Pin stub versions and control repository access | Publishing artifacts containing credentials to public repos |
| Mask `Authorization` headers in logs/request dumps | Printing raw tokens in CI logs, stack traces, or HTTP reports |
| Grant least-privilege scopes to identity fixtures | Giving every test token admin rights so all tests pass |
| Scrub personally identifiable data from fixtures | Using real customer emails or account numbers |

Masking tokens in logs **does not mean** you can omit auth headers from contracts. Contracts should still describe `Authorization` and appropriate matchers, while test setup supplies safe values.

For OAuth2/OIDC, do not simulate an entire login flow with one static Bearer string and claim login is verified. Token acquisition, refresh tokens, cookies/sessions, gateways, and identity providers require dedicated integration tests when the system depends on them.

## 12. Integrating Authentication Tests into CI

A pipeline can be structured into the following steps:

```mermaid
flowchart TD
    A[Review HTTP contracts with auth] --> B[Prepare test identities and resource data]
    B --> C[Generate producer contract tests]
    C --> D[Run producer tests through security filter chain]
    D --> E{200/401/403 match contract?}
    E -- No --> F[Fix implementation, fixtures, or negotiated contract]
    F --> C
    E -- Yes --> G[Run security integration tests]
    G --> H{Security tests pass?}
    H -- No --> F
    H -- Yes --> I[Package and publish versioned stub]
    I --> J[Consumer runs HTTP client tests via Stub Runner]
    J --> K{Consumer handles properly?}
    K -- No --> L[Fix client or update contract via review]
    L --> A
    K -- Yes --> M[Approve integration and release]
```

In CI, verify that:

- **The build uses compatible versions** of Spring Boot, Spring Cloud Contract, JDK, and Maven/Gradle Wrapper.
- **Fixtures are initialized before tests** and carry the same meaning on laptops and CI.
- **Generated producer tests actually execute**, not skipped via `skipTests` or exclude rules.
- **Security filters are truly enabled** for authentication scenarios.
- **Dedicated security integration tests** cover areas beyond contract simulation.
- **Stub artifacts are tied to verified producer builds**; consumers pull the exact version.
- **Real secrets and tokens never appear in artifacts or logs.**

A `preview` stub created before the producer finishes can help consumers develop early. However, it carries no proof of producer compliance until producer contract tests pass; never treat preview status as an official release gate.

## 13. Common Errors and Root-Cause Analysis

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `200` contract returns `401` | Test token unrecognized by decoder/introspector, fixture not installed, wrong issuer/audience | Inspect test auth configuration and actual request header |
| `200` contract returns `403` | Missing scope/role, wrong owner/tenant | Inspect user fixture and resource fixture |
| `200` contract still passes when token is removed | Security filter bypassed or test profile has `permitAll` | Run tokenless test, inspect MockMvc setup and filter chain |
| `401` returned when `403` was expected | "Insufficient scope" fixture is actually treated as invalid token | Separate authentication step from authorization step |
| Producer returns `200` yet body mismatches | Account fixture differs or producer changed schema | Compare JSON and seeded data against contract |
| Stub returns `404` when consumer omits Authorization | No mapping matches request; likely a WireMock `404` | Check mappings and request logs before blaming business error handling |
| Stub returns `200` for an unknown token | `Authorization` matcher is too broad | Inspect generated mapping, tighten matcher, check real auth on producer |
| Consumer sends token in the wrong header | Client interceptor, credentials provider, or header overwritten | Invoke via real client and inspect outgoing headers |
| JWT fixture worked yesterday, fails with `401` today | Token expired, clock skew, or test key rotated | Use controllable clock or deterministic test token issuance |
| CI fails while local passes | Missing test secret/issuer config, different JDK/dependencies, different DB fixture | Compare environment configs and masked logs |
| Tests pass yet production token leaked | Tests used a real secret or logged full HTTP dumps | Revoke/rotate secret per incident process and fix fixture/logging |

When failures occur, inspect the **actual request and test context** first before editing the DSL. If the contract is accurate and tests fail because the producer lacks `accounts.read` enforcement, the producer may be violating its commitment. If tests fail because account 42 seed data is missing, fix the fixture. Both cases call for very different actions.

## 14. Hands-On Exercise: Account Service and Billing

This exercise can be carried out across two Spring Boot apps or one producer plus a consumer test project. You need the Spring Cloud Contract plugin and Stub Runner matching your project version, alongside Spring Security and a test environment.

### Phase 1 — Design and Write Contracts

1. Define `GET /api/accounts/42`, the JSON fields Billing consumes, and the three scenarios `200`, `401`, and `403`.
2. Choose **Groovy or YAML DSL** for each scenario. Assign distinct filenames/`name` values for traceability.
3. Use `contract-reader-token` for `200`, `contract-invalid-token` for `401`, and `contract-no-scope-token` for `403`.
4. Seed account 42 owned by `user-42` with `currency=VND` and `balance=850000` in test fixtures.
5. Define the exact meaning of each token via a test profile, or generate test JWTs verifiable by the real mechanism.

### Phase 2 — Verify the Producer

1. Configure the plugin to generate tests from contracts, pointing to a test base that loads Spring Security filters.
2. Intentionally make the endpoint return `200` without checking tokens; run the tokenless test and observe the issue (if no tokenless test exists yet, add a security integration test).
3. Enable authentication/authorization per policy and re-run the `200`, `401`, and `403` scenarios.
4. Intentionally drop `accounts.read` from the reader fixture; observe the `200` contract test turn into `403`, then restore the fixture.
5. Verify generated tests, responses, and stub mappings all align with the DSL.

### Phase 3 — Verify Consumer and CI

1. Package the stub artifact from the producer build that passed tests.
2. Have Stub Runner start the stub and point Billing's HTTP client to it.
3. Verify Billing actually attaches `Authorization` when calling `getAccount(42)`; assert `200` JSON parsing.
4. Test invalid and no-scope tokens; verify Billing handles `401`/`403` per contract without endless retries.
5. Verify the missing-header case separately in producer security tests.
6. Pin stub versions and add producer contract tests, security tests, and consumer tests to CI.

**Completion criteria:** producer tests truly traverse the security filter chain; `200` passes only with valid auth and permission fixtures; `401`/`403` are clearly distinguished; consumer sends the right Bearer header and handles responses through Stub Runner; no production tokens or keys exist in source code.

## 15. Self-Check Questions

1. **Does a contract with an `Authorization` header prove the producer verifies JWT signatures?** No. You must ensure generated tests run through the appropriate verifier and maintain security integration tests for signature/expiry checks.
2. **Why might `contract-reader-token` receive `401` from the producer?** Because it is only a fixture string; the test environment must explicitly accept it or use tokens signed/verified by the real mechanism.
3. **How do `401` and `403` differ?** `401` usually indicates the request is not validly authenticated; `403` usually indicates authenticated but lacking permission.
4. **If a MockMvc test uses `standaloneSetup` without security filters, does a `200` test guarantee auth works?** No.
5. **Why might Stub Runner return `404` when the consumer forgets to attach `Authorization`?** Because the request does not match the generated mapping; that response may be the stub server's default unmatched reply, not a producer business `404`.
6. **Can you commit a Bearer token copied from production for testing convenience?** No. Use safe, isolated, reproducible test data.
7. **Does holding `accounts.read` guarantee access to read every account?** No. Ownership/tenant or resource-level authorization policies must also be checked.
8. **Is a passing producer contract test with a test token verifier enough to test the real identity provider?** No. Dedicated security integration/E2E tests are needed for those integrations.
9. **Why must consumer CI pin the stub artifact version?** To know exactly which contract set the consumer is tested against and avoid drift from silently picking up newer stubs.
10. **When the producer returns `401` instead of `200`, should you immediately edit the contract?** No. First inspect the actual sent headers, fixtures, auth filters, decoders, and the agreement between both teams.

## Conclusion

To **verify authenticated HTTP requests** with Spring Cloud Contract, teams must turn producer–consumer expectations into **scenarios with deterministic requests, token fixtures, permissions, and business data**. Groovy/YAML DSL can protect how `Authorization` is sent and how `200`, `401`, and `403` are handled; producer tests must traverse security filters, and Stub Runner lets consumers test independently. Combining **reproducible fixtures**, **security integration tests**, **traceable stub versions**, and **mandatory CI gates** catches incompatible API changes early while respecting the proper boundaries of contract testing.
