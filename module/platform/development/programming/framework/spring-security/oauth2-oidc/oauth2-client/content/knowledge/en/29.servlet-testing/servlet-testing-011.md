# 29.11. Testing Client Manager, Refresh, and Authorized Client Persistence

## Lesson Objectives

In **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** on the Servlet stack, a successful login is only part of the system. When the application calls downstream APIs, `OAuth2AuthorizedClientManager` must coordinate multiple components to:

- Locate the right `ClientRegistration`.
- Load the principal's existing `OAuth2AuthorizedClient` from the repository/service.
- **Reuse a valid access token** without calling the token endpoint unnecessarily.
- **Refresh the access token** when it is about to expire or already expired, if a valid refresh token exists.
- Save the new access/refresh tokens after successful reauthorization.
- Handle `invalid_grant` or other errors per failure policy.
- Never mix tokens across principals, registrations, and tenants.

These behaviors must be **tested explicitly** instead of assuming "Spring Security manages tokens automatically, so no tests are needed".

This lesson focuses on **Chapter 29. Servlet Testing**: using JUnit 5, Spring Security Test, `MockHttpServletRequest`/`MockHttpServletResponse`, `OAuth2AuthorizedClientService`, and a fake token-response client to verify manager behavior **without connecting to a real Authorization Server**.

After this lesson, you will be able to:

1. Distinguish `ClientRegistrationRepository`, `OAuth2AuthorizedClientRepository`, `OAuth2AuthorizedClientService`, and `OAuth2AuthorizedClientManager`.
2. Understand how the manager loads tokens, invokes providers, handles outcomes, saves tokens, and handles failures.
3. Build test fixtures for `ClientRegistration`, principals, access/refresh tokens, and Servlet requests/responses.
4. Verify non-expired tokens are reused without refreshing.
5. Verify expired tokens are refreshed when a refresh token is present.
6. Use `RefreshTokenOAuth2AuthorizedClientProvider` with a fake `OAuth2AccessTokenResponseClient` instead of calling a real token endpoint.
7. Verify refresh token rotation R1 -> R2 and persistence of the updated authorized client.
8. Test expired tokens lacking a refresh token or unsupported grants.
9. Test `invalid_grant` and authorized-client removal via the failure handler.
10. Verify principal/registration isolation in the store.
11. Test custom success/failure handlers, repository interactions, and persistence.
12. Know when to use `DefaultOAuth2AuthorizedClientManager` vs. `AuthorizedClientServiceOAuth2AuthorizedClientManager`.
13. Distinguish fake-provider tests, mock HTTP token endpoint tests, and multi-instance integration tests.
14. Design tests for clock skew, concurrent refreshes, storage errors, logout, and token revocation.
15. Never confuse an OIDC login test using `oidcLogin()` with testing refresh tokens and authorized client persistence.

---

## 1. Context: Portal Calls the Orders API Repeatedly

Suppose the **Orders Portal** authenticates employees via OIDC and calls the Orders API using an OAuth access token.

~~~text
Browser
  -> Orders Portal (Servlet session)
      -> OAuth2AuthorizedClientManager
          -> Authorized client repository/service
          -> OAuth2AuthorizedClientProvider
          -> Authorization Server token endpoint when needed
      -> Orders API (Bearer access token)
~~~

User Alice logs in at 09:00. The Authorization Server returns:

~~~text
access_token = A1
expires_at   = 10:00
refresh_token = R1
registrationId = orders-client
principalName = alice
~~~

Subsequent requests produce three scenarios:

| Time | State | Expected behavior |
|---|---|---|
| 09:05 | A1 is still valid | Reuse A1, do not refresh |
| 09:59:30 | A1 is near expiry within clock skew | May refresh proactively with R1 |
| 10:10 | A1 expired, R1 valid | Request A2 and persist new tokens |

If the AS uses refresh token rotation:

~~~text
R1 -> token endpoint -> A2 + R2
~~~

then the store must update **both A2 and R2**. Updating only the access token while keeping the old refresh token will cause the next refresh to fail or trigger reuse detection.

### 1.1. What Must Tests Prove?

Do not merely assert that `manager.authorize(...)` returns a non-null object.

Observe:

1. Which authorization context the manager used.
2. Which provider ran and whether a refresh request was sent.
3. Which token was returned.
4. Whether a new `OAuth2AuthorizedClient` was persisted.
5. Which access/refresh tokens sit in the store afterward.
6. On failure, whether the store removes or retains the entry per policy.
7. Whether Alice and Bob can ever share tokens.

### 1.2. Commonly Missed Bugs

- Token is still valid, yet every API call requests a new token.
- Token is expired, yet refresh is never triggered.
- Token refresh succeeds, yet R2 is never saved.
- Repository key omits principal, causing Alice to use Bob's token.
- `invalid_grant` occurs, yet the stale token stays cached.
- Two concurrent refreshes overwrite R2 with R1.
- A background job uses a manager that depends on `HttpServletRequest`.
- Tests only mock `manager.authorize()`, never exercising the real manager.

## 2. Component Responsibility Diagram

~~~mermaid
flowchart TD
    A["Application calls authorize()"] --> M["OAuth2AuthorizedClientManager"]
    M --> REG["ClientRegistrationRepository"]
    M --> STORE["OAuth2AuthorizedClientRepository / Service"]
    STORE --> M
    M --> P["OAuth2AuthorizedClientProvider"]
    P --> D{"Token valid / grant?"}
    D -->|"Reuse"| M
    D -->|"Refresh needed"| TOKEN["OAuth2AccessTokenResponseClient"]
    TOKEN -->|"Token response"| P
    P -->|"New AuthorizedClient"| M
    M -->|"Success handler: save"| STORE
    M -->|"Failure handler: remove/policy"| STORE
    M --> A
~~~

Conceptual diagram. In code, the manager may invoke the provider even when a token is still valid; **the provider returns `null`** to signal no reauthorization is needed or possible, and the manager returns the existing authorized client.

### 2.1. `ClientRegistrationRepository`

Stores **client configuration**, such as:

~~~text
registrationId = orders-client
clientId = portal-web
authorizationGrantType = authorization_code
authorizationUri = ...
tokenUri = ...
scope = orders.read
~~~

It does not store Alice's individual access tokens.

### 2.2. `OAuth2AuthorizedClient`

Represents the authorization granted to a principal and registration:

~~~text
registration = orders-client
principalName = alice
accessToken = A1
refreshToken = R1
~~~

### 2.3. `OAuth2AuthorizedClientRepository`

Interface for Servlet web request contexts:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        HttpServletRequest request);

void saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal,
        HttpServletRequest request,
        HttpServletResponse response);

void removeAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        HttpServletRequest request,
        HttpServletResponse response);
~~~

The repository may be session-backed or delegate storage to `OAuth2AuthorizedClientService`.

### 2.4. `OAuth2AuthorizedClientService`

API for saving/loading/removing authorized clients by `registrationId` and `principalName` without requiring a Servlet request:

~~~java
<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
        String clientRegistrationId, String principalName);

void saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal);

void removeAuthorizedClient(
        String clientRegistrationId, String principalName);
~~~

Can be implemented as in-memory, JDBC, or a custom persistent store.

### 2.5. `OAuth2AuthorizedClientManager`

Coordinates how authorized clients are obtained for the application. Two key implementations:

| Manager | Typical context |
|---|---|
| `DefaultOAuth2AuthorizedClientManager` | Inside a Servlet request/response |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Background jobs, service layer outside Servlet requests |

### 2.6. `OAuth2AuthorizedClientProvider`

Executes a specific grant:

- `authorizationCode()`.
- `refreshToken()`.
- `clientCredentials()`.
- Custom providers if supported by the application.

A provider returns a new authorized client or `null` when the grant cannot or need not run.

## 3. Lifecycle of an `authorize()` Call

Example application code:

~~~java
OAuth2AuthorizedClient client =
        authorizedClientManager.authorize(authorizeRequest);
~~~

Typical execution flow:

1. Manager looks up the registration and/or existing authorized client.
2. Builds `OAuth2AuthorizationContext` holding registration, principal, authorized client, and attributes.
3. Invokes the authorized client provider chain.
4. If the provider returns `null`, the manager may return the existing authorized client.
5. If the provider returns a new client, the manager calls the success handler to save it.
6. If the provider raises an authorization failure, the manager calls the failure handler.
7. Returns the result to the application or propagates the exception.

### 3.1. Three Outcomes to Distinguish

| Provider outcome | Typical manager behavior | Meaning |
|---|---|---|
| `null` when an existing client is present | Returns existing client | No new reauthorization occurred |
| New `OAuth2AuthorizedClient` | Calls success handler, returns new client | Authorization/refresh succeeded |
| Exception | Calls failure handler, rethrows error | Grant or token endpoint failed |

### 3.2. Do Not Equate Provider Invocation with a Network Request

The manager may call `RefreshTokenOAuth2AuthorizedClientProvider.authorize(...)` on every application `authorize()` call.

While the access token is valid, the provider **does not call the token endpoint**. Tests should count calls to the fake token-response client, not merely provider invocations.

### 3.3. Lack of a Refresh Token Does Not Trigger a New Authorization Code

The refresh provider cannot request a new access token without a refresh token. For Authorization Code flow, initiating an interactive browser redirect is the responsibility of OAuth2 Login/Authorization Request filters, **not a token endpoint call invented by the manager**.

## 4. Test Dependencies

### 4.1. Maven

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-security-test` is needed for MockMvc security helpers if testing controllers; pure JUnit manager tests can also use `spring-test`/Mockito/AssertJ from the Boot test starter.

### 4.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 4.3. Why Is a Production AS Unnecessary?

In unit/component tests, a fake `OAuth2AccessTokenResponseClient` can return test-built token responses. This lets you test manager/provider/storage logic without sending refresh tokens over the network.

However, HTTP request serialization, Basic client authentication, network timeouts, or AS-specific JSON responses still require dedicated **HTTP integration tests**.

## 5. Building a `ClientRegistration` Test Fixture

The registration must carry everything required by the grant/provider.

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;

public final class TestRegistrations {

    private TestRegistrations() {}

    public static ClientRegistration orders() {
        return ClientRegistration
                .withRegistrationId("orders-client")
                .clientId("portal-test-client")
                .clientSecret("test-secret-not-production")
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .authorizationUri("https://op.example.test/authorize")
                .tokenUri("https://op.example.test/token")
                .scope("openid", "orders.read")
                .clientName("Orders Test Client")
                .build();
    }
}
~~~

### 5.1. Key Fields

- `registrationId`: used to load/save tokens per client.
- `clientId`: OAuth client registered at the AS.
- `authorizationGrantType`: initial grant.
- `tokenUri`: target endpoint called by the provider in real flows.
- `scope`: token scopes.
- `redirectUri`/`authorizationUri`: required for Authorization Code registrations.

### 5.2. No Real Discovery Needed in These Tests

When testing the manager with fake token responses, the registration fixture can declare dummy endpoints without triggering `issuer-uri` metadata discovery.

If a Spring Boot context auto-builds `ClientRegistration` from `issuer-uri`, network discovery can fire on startup. Isolate test fixtures/repositories so tests never contact a production OP.

### 5.3. Never Use Real Credentials

`clientSecret` here is strictly a dummy string. All access/refresh token fixtures must likewise be synthetic data.

## 6. Creating Fake Access and Refresh Tokens

Token APIs:

~~~java
import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

public final class TestTokens {

    private TestTokens() {}

    public static OAuth2AccessToken accessToken(
            String value,
            Instant issuedAt,
            Instant expiresAt) {

        return new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                value,
                issuedAt,
                expiresAt,
                Set.of("orders.read"));
    }

    public static OAuth2RefreshToken refreshToken(
            String value,
            Instant issuedAt) {

        return new OAuth2RefreshToken(value, issuedAt);
    }
}
~~~

### 6.1. Shared Test Clock

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock clock = Clock.fixed(
        Instant.parse("2026-11-16T10:00:00Z"),
        ZoneOffset.UTC);
~~~

Fixing the clock prevents random flakiness near time boundaries.

### 6.2. Valid Token

~~~text
now = 10:00:00
accessToken.expiresAt = 11:00:00
clockSkew = 60 seconds

=> No refresh needed yet.
~~~

### 6.3. Nearly Expired Token

~~~text
now = 10:00:00
accessToken.expiresAt = 10:00:20
clockSkew = 60 seconds

=> May refresh proactively.
~~~

### 6.4. Expired Token

~~~text
now = 10:00:00
accessToken.expiresAt = 09:59:00

=> Refresh if R1 is present and grant/provider supports it.
~~~

## 7. Test Harness for the Servlet Manager

Use the real in-memory components:

~~~java
import org.springframework.security.oauth2.client.registration
        .InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client
        .InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web
        .AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web
        .DefaultOAuth2AuthorizedClientManager;

var registration = TestRegistrations.orders();

var registrations =
        new InMemoryClientRegistrationRepository(registration);

var service =
        new InMemoryOAuth2AuthorizedClientService(registrations);

var repository =
        new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(service);

var manager =
        new DefaultOAuth2AuthorizedClientManager(
                registrations, repository);
~~~

### 7.1. Why Choose `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`?

For authenticated principals, this repository delegates saves/loads to `OAuth2AuthorizedClientService`. That lets tests inspect the service directly for the new token after `manager.authorize(...)`.

For anonymous flows, implementations may use a different session-backed repository. This lesson focuses primarily on **authenticated principals**.

### 7.2. Principal for Manager Tests

You do not have to run OIDC Login just to test the manager.

~~~java
import org.springframework.security.authentication
        .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;

var alice = UsernamePasswordAuthenticationToken.authenticated(
        "alice",
        "test-only",
        AuthorityUtils.createAuthorityList("ROLE_USER"));
~~~

The manager needs an `Authentication` to determine `principalName`. This `Authentication` is a test fixture; it does **not** represent a real OIDC authentication flow.

### 7.3. Mock Servlet Request/Response

~~~java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

var servletRequest = new MockHttpServletRequest();
var servletResponse = new MockHttpServletResponse();
~~~

### 7.4. Building `OAuth2AuthorizeRequest`

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;

OAuth2AuthorizeRequest authorization =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("orders-client")
                .principal(alice)
                .attribute(
                        HttpServletRequest.class.getName(),
                        servletRequest)
                .attribute(
                        HttpServletResponse.class.getName(),
                        servletResponse)
                .build();
~~~

These two request/response attributes supply `DefaultOAuth2AuthorizedClientManager` with the Servlet context it needs without relying on a live HTTP request or global `RequestContextHolder`.

### 7.5. Why Not Simply Call `manager.authorize()`?

The manager interface has no parameterless `authorize()`. It requires an `OAuth2AuthorizeRequest` specifying client/principal and, for the Servlet manager, the request context.

Omitting Servlet request/response without an active thread-bound request context causes missing-request-attribute errors.

## 8. Configuring a Fake Refresh Token Response Client

To test **real refresh logic in Spring Security's provider** without calling an AS, configure `RefreshTokenOAuth2AuthorizedClientProvider` with a fake response client.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.oauth2.client
        .RefreshTokenOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.endpoint
        .OAuth2AccessTokenResponse;

AtomicInteger refreshHttpCalls = new AtomicInteger();

RefreshTokenOAuth2AuthorizedClientProvider provider =
        new RefreshTokenOAuth2AuthorizedClientProvider();

provider.setClock(clock);
provider.setClockSkew(Duration.ofSeconds(60));

provider.setAccessTokenResponseClient(grant -> {
    refreshHttpCalls.incrementAndGet();

    // No real HTTP. grant holds the flow's refresh token.
    org.assertj.core.api.Assertions.assertThat(
            grant.getRefreshToken().getTokenValue())
            .isEqualTo("refresh-R1");

    return OAuth2AccessTokenResponse
            .withToken("access-A2")
            .tokenType(OAuth2AccessToken.TokenType.BEARER)
            .expiresIn(3600)
            .refreshToken("refresh-R2")
            .scopes(Set.of("openid", "orders.read"))
            .build();
});

manager.setAuthorizedClientProvider(provider);
~~~

### 8.1. This Fake Still Tests Provider Decisions

`RefreshTokenOAuth2AuthorizedClientProvider` genuinely evaluates whether to refresh based on:

- Access token expiry.
- Clock and clock skew.
- Presence of a refresh token.
- Authorization context.

Only the **HTTP token exchange** is faked via the callback returning `OAuth2AccessTokenResponse`.

### 8.2. Do Not Confuse This with Mocking the Whole Manager

If you write:

~~~java
when(manager.authorize(any()))
        .thenReturn(newAuthorizedClient);
~~~

you fail to test whether the manager loads or saves authorized clients. A fake token-response client simulates at a **deeper** seam and exercises manager, provider, and storage behavior together.

### 8.3. Do Not Hardcode the Current Wall-Clock Time

A fake response specifies `expiresIn(3600)`. The provider computes token timestamps from the response and its clock. For refresh-branch tests, build the *old* access token relative to the fixed clock so refresh triggers (or skips) deterministically.

## 9. Test 1 — Valid Token Is Reused

Goal:

~~~text
Repository currently holds:
  registration = orders-client
  principal = alice
  accessToken = access-A1 (valid)
  refreshToken = refresh-R1

manager.authorize():
  -> returns access-A1
  -> does not call token response client
  -> creates no new refresh token
~~~

### 9.1. Create a Valid Authorized Client

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

Instant now = clock.instant();

OAuth2AuthorizedClient active =
        new OAuth2AuthorizedClient(
                registration,
                "alice",
                TestTokens.accessToken(
                        "access-A1",
                        now.minusSeconds(300),
                        now.plusSeconds(3600)),
                TestTokens.refreshToken(
                        "refresh-R1",
                        now.minusSeconds(300)));
~~~

### 9.2. Save the Client in the Repository

~~~java
repository.saveAuthorizedClient(
        active,
        alice,
        servletRequest,
        servletResponse);
~~~

### 9.3. Invoke the Manager and Assert

~~~java
OAuth2AuthorizedClient result =
        manager.authorize(authorization);

assertThat(result).isNotNull();

assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("access-A1");

assertThat(refreshHttpCalls.get())
        .isZero();

OAuth2AuthorizedClient stored =
        service.loadAuthorizedClient(
                "orders-client", "alice");

assertThat(stored.getAccessToken().getTokenValue())
        .isEqualTo("access-A1");

assertThat(stored.getRefreshToken().getTokenValue())
        .isEqualTo("refresh-R1");
~~~

### 9.4. Meaning of the Assertions

- The existing token is reused.
- No fake HTTP refresh occurs.
- The store retains the existing access and refresh tokens.

To verify **no save occurred** during reuse, wrap the repository in a spy and assert `Mockito.verify(..., never()).saveAuthorizedClient(...)`; remember to reset the spy after seeding initial data.

### 9.5. Do Not Assert Token Reuse by Object Identity Alone

The manager may return the exact same instance or an equivalent copy depending on implementation. Assertions on token values, expirations, and interactions are more reliable than expecting `assertSame`, which the contract does not guarantee.

## 10. Test 2 — Expired Token Is Refreshed and Persisted

Goal:

~~~text
Before:
  access = access-A1 (expired)
  refresh = refresh-R1

Provider calls fake token response client:
  refresh-R1 -> access-A2 + refresh-R2

After:
  manager returns access-A2
  service stores access-A2 + refresh-R2
~~~

### 10.1. Seed Expired Authorized Client

~~~java
Instant now = clock.instant();

OAuth2AuthorizedClient expired =
        new OAuth2AuthorizedClient(
                registration,
                "alice",
                TestTokens.accessToken(
                        "access-A1",
                        now.minusSeconds(7200),
                        now.minusSeconds(60)),
                TestTokens.refreshToken(
                        "refresh-R1",
                        now.minusSeconds(7200)));

repository.saveAuthorizedClient(
        expired,
        alice,
        servletRequest,
        servletResponse);
~~~

### 10.2. Authorize with the Refresh Provider

~~~java
OAuth2AuthorizedClient refreshed =
        manager.authorize(authorization);
~~~

### 10.3. Assert the Result

~~~java
assertThat(refreshed).isNotNull();

assertThat(refreshed.getAccessToken().getTokenValue())
        .isEqualTo("access-A2");

assertThat(refreshed.getRefreshToken().getTokenValue())
        .isEqualTo("refresh-R2");

assertThat(refreshHttpCalls.get())
        .isEqualTo(1);
~~~

### 10.4. Assert Storage After Refresh

~~~java
OAuth2AuthorizedClient persisted =
        service.loadAuthorizedClient(
                "orders-client", "alice");

assertThat(persisted).isNotNull();

assertThat(persisted.getAccessToken().getTokenValue())
        .isEqualTo("access-A2");

assertThat(persisted.getRefreshToken().getTokenValue())
        .isEqualTo("refresh-R2");
~~~

This assertion is **critical**: manager success means little if the new tokens only live in a local variable and were never saved to the repository/service.

### 10.5. Assert Registration and Principal

~~~java
assertThat(persisted.getClientRegistration()
        .getRegistrationId())
        .isEqualTo("orders-client");

assertThat(persisted.getPrincipalName())
        .isEqualTo("alice");
~~~

If tests check only the access token value without checking principal/registration, you could miss a bug that writes tokens under someone else's record.

## 11. Test 3 — Proactive Refresh Due to Clock Skew

Many applications refresh prior to expiration so access tokens do not expire mid-flight toward an API.

Suppose:

~~~text
Clock now = 10:00:00
Access expiresAt = 10:00:20
Clock skew = 60s

Token has not expired by wall-clock time,
yet falls inside the refresh threshold.
~~~

Test:

~~~java
Instant now = clock.instant();

OAuth2AuthorizedClient almostExpired =
        new OAuth2AuthorizedClient(
                registration,
                "alice",
                TestTokens.accessToken(
                        "access-A1",
                        now.minusSeconds(300),
                        now.plusSeconds(20)),
                TestTokens.refreshToken(
                        "refresh-R1",
                        now.minusSeconds(300)));

repository.saveAuthorizedClient(
        almostExpired, alice, servletRequest, servletResponse);

OAuth2AuthorizedClient result =
        manager.authorize(authorization);

assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("access-A2");

assertThat(refreshHttpCalls.get())
        .isEqualTo(1);
~~~

### 11.1. What the Test Verifies

- The refresh provider honors clock skew.
- It does not wait until exact expiration to refresh.
- The manager saves the updated result via the success handler.

### 11.2. Do Not Set Clock Skew Blindly Too Large

Overly large skew causes unnecessary token refreshes, extra AS load, and concurrency contention.

Base skew on latency, clock synchronization, and AS/API policies.

### 11.3. Keeping Tests Non-Flaky

Use `Clock.fixed(...)` or timestamps well away from boundaries. Never scatter `Instant.now()` calls and expect exact expiry-boundary branching regardless of test execution speed.

## 12. Test 4 — Missing Refresh Token

An `OAuth2AuthorizedClient` may hold only an access token:

~~~java
OAuth2AuthorizedClient withoutRefreshToken =
        new OAuth2AuthorizedClient(
                registration,
                "alice",
                TestTokens.accessToken(
                        "expired-A1",
                        now.minusSeconds(3600),
                        now.minusSeconds(120)));
~~~

When only a refresh-token provider is configured, it **cannot refresh** without a refresh token.

### 12.1. Important Expectation

Never write a test expecting the manager to conjure A2 without a matching grant/token-issuing mechanism.

When the provider returns `null` for an existing client, the manager may return the old client; **the application must never treat that expired token as usable**.

### 12.2. Behavior Assertion

~~~java
repository.saveAuthorizedClient(
        withoutRefreshToken,
        alice,
        servletRequest,
        servletResponse);

OAuth2AuthorizedClient result =
        manager.authorize(authorization);

assertThat(refreshHttpCalls.get()).isZero();

// If the manager returns the stale client,
// the app must enforce reauthorization/failure policy.
assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("expired-A1");
~~~

This example reflects `DefaultOAuth2AuthorizedClientManager` behavior with a refresh-only provider and a stored client. If the application adds custom providers or handlers, define and test the updated contract.

### 12.3. Authorization Code Requires a Browser Flow

If a token expires and cannot be refreshed, the app may need to restart the Authorization Code flow so the user/AS issues fresh tokens.

Never call the token endpoint with a nonexistent authorization code.

### 12.4. When the API Returns 401

If an access token expires or becomes invalid, the outbound API client may receive 401. The application must handle reauthorization/session UX per policy rather than retrying endlessly with the expired token.

## 13. Test 5 — `invalid_grant` During Refresh

The Authorization Server can reject a refresh token because:

- The refresh token expired.
- The refresh token was revoked.
- The refresh token rotated and old R1 is no longer valid.
- Refresh token reuse detection triggered.
- Client/grant policy changed.

For `invalid_grant`, Spring Security's default failure handling removes the stale authorized client so invalid tokens are not kept in use.

### 13.1. Fake Token Response Client Throws an Error

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;

provider.setAccessTokenResponseClient(grant -> {
    throw new OAuth2AuthorizationException(
            new OAuth2Error(
                    "invalid_grant",
                    "Refresh token invalid",
                    null));
});
~~~

### 13.2. Call the Manager and Assert Exception

~~~java
import org.springframework.security.oauth2.client.ClientAuthorizationException;

assertThatThrownBy(() ->
        manager.authorize(authorization))
        .isInstanceOf(ClientAuthorizationException.class);
~~~

### 13.3. Verify Record Removal

~~~java
OAuth2AuthorizedClient persisted =
        service.loadAuthorizedClient(
                "orders-client", "alice");

assertThat(persisted).isNull();
~~~

This test assumes the manager uses the matching default failure handler, the repository persists authenticated principals via the service, and the provider translates refresh errors into the right authorization exception.

### 13.4. Not Every Error Should Delete Tokens

A transient network error or AS 503 does not automatically mean the refresh token was revoked.

The failure handler and application policy must distinguish:

- `invalid_grant`: normally remove the stale authorized client.
- 5xx/timeouts: may perform bounded retries.
- Invalid client/misconfiguration: alert and stop pointless retries.
- Domain permission/API 403: normally cannot be fixed by refreshing.

### 13.5. Never Swallow Exceptions in Tests

A test that only calls `assertDoesNotThrow` and ignores the result can hide token-store/AS bugs. Assert exception type, error code, and post-failure storage state per policy.

## 14. Test 6 — Save Handler Invoked After Successful Authorization

The manager holds an `OAuth2AuthorizationSuccessHandler`. With default Servlet configuration, it saves the authorized client into the repository.

You can test the success branch directly with a fake provider:

~~~java
import org.springframework.security.oauth2.client
        .OAuth2AuthorizedClientProvider;

OAuth2AuthorizedClientProvider fakeProvider = context -> {
    ClientRegistration reg = context.getClientRegistration();

    return new OAuth2AuthorizedClient(
            reg,
            context.getPrincipal().getName(),
            TestTokens.accessToken(
                    "new-access",
                    clock.instant(),
                    clock.instant().plusSeconds(3600)));
};

manager.setAuthorizedClientProvider(fakeProvider);
~~~

### 14.1. Testing Initial Authorization When No Client Exists

~~~java
OAuth2AuthorizedClient result =
        manager.authorize(authorization);

assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("new-access");

assertThat(service.loadAuthorizedClient(
        "orders-client", "alice"))
        .isNotNull();
~~~

### 14.2. This Tests Orchestration, Not a Real Authorization Code Grant

The fake provider returns an authorized client directly to test manager persistence; it **does not simulate an OP issuing an authorization code**.

To test the Browser Authorization Code flow, test the OAuth2 Login filters/callbacks with a mock OP.

### 14.3. Spying on the Repository

When you need to assert the exact number of saves:

~~~java
OAuth2AuthorizedClientRepository spyRepository =
        org.mockito.Mockito.spy(repository);
~~~

Then construct the manager with the spy repository and verify:

~~~java
org.mockito.Mockito.verify(spyRepository,
        org.mockito.Mockito.times(1))
        .saveAuthorizedClient(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.eq(alice),
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any());
~~~

If you seeded data through the spy earlier, call `clearInvocations(...)` or reset after setup; otherwise the initial setup save will skew the count.

## 15. Test 7 — When the Provider Returns `null`, No New Token Is Saved

A provider may see a still-valid token and return `null`.

~~~java
OAuth2AuthorizedClientProvider noReauthorization =
        context -> null;

manager.setAuthorizedClientProvider(noReauthorization);
~~~

When the repository already holds A1:

~~~java
OAuth2AuthorizedClient result =
        manager.authorize(authorization);

assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("access-A1");
~~~

### 15.1. Distinguishing Load and Save

The manager calls repository `loadAuthorizedClient` to fetch the record. However, because the provider returned no new token, the default success handler does not need to save a new authorization.

If this invariant matters, use a spy to verify zero saves after seeding.

### 15.2. `null` When No Authorized Client Exists Yet

If no prior record exists and the provider does not support the current grant, the manager can return `null`. The application must handle the "not yet authorized" state cleanly instead of dereferencing a null token.

~~~java
OAuth2AuthorizedClient client =
        manager.authorize(authorization);

if (client == null) {
    // Initiate a supported authorization flow or fail clearly.
}
~~~

Never rely on `NullPointerException` for user control flow.

## 16. Test 8 — Principal Isolation

Suppose Alice and Bob both use registration `orders-client`.

~~~text
orders-client + alice -> A-alice / R-alice
orders-client + bob   -> A-bob   / R-bob
~~~

### 16.1. Seed Two Principals

~~~java
var bob = UsernamePasswordAuthenticationToken.authenticated(
        "bob",
        "test-only",
        AuthorityUtils.createAuthorityList("ROLE_USER"));

OAuth2AuthorizedClient aliceClient =
        new OAuth2AuthorizedClient(
                registration,
                "alice",
                TestTokens.accessToken(
                        "A-alice",
                        now.minusSeconds(100),
                        now.plusSeconds(3600)));

OAuth2AuthorizedClient bobClient =
        new OAuth2AuthorizedClient(
                registration,
                "bob",
                TestTokens.accessToken(
                        "A-bob",
                        now.minusSeconds(100),
                        now.plusSeconds(3600)));

service.saveAuthorizedClient(aliceClient, alice);
service.saveAuthorizedClient(bobClient, bob);
~~~

### 16.2. Verify Isolation

~~~java
assertThat(service.loadAuthorizedClient(
        "orders-client", "alice")
        .getAccessToken().getTokenValue())
        .isEqualTo("A-alice");

assertThat(service.loadAuthorizedClient(
        "orders-client", "bob")
        .getAccessToken().getTokenValue())
        .isEqualTo("A-bob");
~~~

### 16.3. Testing Through the Manager

Build two `OAuth2AuthorizeRequest` instances for the same registration with different principals and verify the manager returns each user's own token.

Never store `currentAccessToken` in a static field or key caches solely by registration ID.

### 16.4. OIDC Principal Name and Issuer

If the app uses `sub` as `principalName` across multiple issuers, two OPs can issue the same `sub`. In custom stores, namespace/map identities by `iss` + `sub` or a stable local user ID to avoid cross-provider collisions.

## 17. Test 9 — Registration Isolation

A single user can have multiple OAuth clients:

~~~text
alice + orders-client  -> orders token
alice + reports-client -> reports token
~~~

### 17.1. Storage Keys

Authorized-client stores normally partition by both registration ID and principal name.

### 17.2. Never Use Another Resource's Token

If the Orders API requires `aud=orders-api`, never send the `reports-client` token in its place.

### 17.3. Testing Wrong Registration

~~~text
Authorize request:
  registrationId = reports-client
  principal = alice

Expected:
  Never loads the orders-client token.
~~~

### 17.4. Resource Server Validation Is Still Required

Even when the manager returns the right registration's token, the Orders API must still verify issuer, audience, and scope. Client-side tests do not prove the API will accept the token.

## 18. Test 10 — Saving to JDBC or a Custom Persistent Store

`InMemoryOAuth2AuthorizedClientService` fits unit/component tests. When production uses JDBC/Redis/a custom store, test the real implementation.

### 18.1. Fields That Must Be Preserved

An authorized client record must typically preserve:

- Registration ID.
- Principal name/identity namespace.
- Access token value.
- Token type.
- Scopes.
- `issuedAt` and `expiresAt`.
- Refresh token value if present.
- Refresh token timestamps if stored.
- Version/concurrency metadata if used.

### 18.2. JDBC Persistence Test

An integration test can:

1. Stand up a test database/schema.
2. Save authorized client A1/R1.
3. Instantiate a fresh repository/service instance.
4. Load the record back.
5. Compare token values and timestamps.
6. Refresh to A2/R2.
7. Load again via a fresh instance.
8. Verify the record holds A2/R2.
9. Remove the record and verify it is gone.
10. Roll back/clean up after the test.

### 18.3. Serialization Must Not Drop the Refresh Token

With Redis/JSON or custom DTOs, tests must confirm refresh tokens are never dropped during serialization/deserialization and expiry timestamps remain accurate.

### 18.4. Protecting Tokens in Storage

Access and refresh tokens are sensitive credentials. Production stores need access controls, encryption where appropriate, bounded backup retention, and log redaction.

Tests must use dummy tokens only; never record raw production refresh tokens.

## 19. Service Manager for Background Jobs

`DefaultOAuth2AuthorizedClientManager` is built for Servlet request contexts.

For scheduled jobs without an `HttpServletRequest`, use:

~~~java
import org.springframework.security.oauth2.client
        .AuthorizedClientServiceOAuth2AuthorizedClientManager;

var backgroundManager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                service);
~~~

### 19.1. `client_credentials`

A registration:

~~~java
ClientRegistration reporting =
        ClientRegistration.withRegistrationId("reporting-client")
                .clientId("reporting-job")
                .clientSecret("test-only")
                .authorizationGrantType(
                        AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://as.example.test/token")
                .scope("reports.read")
                .build();
~~~

### 19.2. Manager Needs the Matching Provider

~~~java
import org.springframework.security.oauth2.client
        .OAuth2AuthorizedClientProviderBuilder;

backgroundManager.setAuthorizedClientProvider(
        OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());
~~~

In real tests, replace the HTTP token-response client with a fake so no AS is contacted.

### 19.3. Machine-to-Machine Principal

~~~java
OAuth2AuthorizeRequest authorizeRequest =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("reporting-client")
                .principal("reporting-job")
                .build();
~~~

`reporting-job` is a technical key for storing the authorized client, not a human OIDC user.

### 19.4. No Servlet Request/Response Needed

`AuthorizedClientServiceOAuth2AuthorizedClientManager` interacts directly with the service store. No `MockHttpServletRequest`/`MockHttpServletResponse` is required.

### 19.5. Testing Both Contexts Separately

| Use case | Manager/test |
|---|---|
| OIDC Portal calling API in a request | `DefaultOAuth2AuthorizedClientManager` |
| Scheduled reporting job | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| Browser OIDC login callback | Spring Security OAuth2 Login integration |
| API validating Bearer tokens | Resource Server tests |

## 20. Full JUnit Test Skeleton: Refresh and Persistence

The following combines the pieces into a pure Servlet test class with a fake token-response client.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.RefreshTokenOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

import static org.assertj.core.api.Assertions.assertThat;

class ServletAuthorizedClientManagerTest {

    private final Clock clock = Clock.fixed(
            Instant.parse("2026-11-16T10:00:00Z"),
            ZoneOffset.UTC);

    private ClientRegistration registration;
    private Authentication alice;
    private InMemoryOAuth2AuthorizedClientService service;
    private AuthenticatedPrincipalOAuth2AuthorizedClientRepository repository;
    private DefaultOAuth2AuthorizedClientManager manager;
    private MockHttpServletRequest request;
    private MockHttpServletResponse response;
    private AtomicInteger refreshCalls;

    @BeforeEach
    void setUp() {
        registration = ClientRegistration
                .withRegistrationId("orders-client")
                .clientId("portal-test")
                .clientSecret("test-secret")
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationUri(
                        "https://op.example.test/authorize")
                .tokenUri("https://op.example.test/token")
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "orders.read")
                .build();

        var registrations =
                new InMemoryClientRegistrationRepository(
                        registration);

        service =
                new InMemoryOAuth2AuthorizedClientService(
                        registrations);

        repository =
                new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
                        service);

        manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, repository);

        alice = UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                "test-only",
                AuthorityUtils.createAuthorityList("ROLE_USER"));

        request = new MockHttpServletRequest();
        response = new MockHttpServletResponse();
        refreshCalls = new AtomicInteger();

        var provider =
                new RefreshTokenOAuth2AuthorizedClientProvider();

        provider.setClock(clock);
        provider.setClockSkew(Duration.ofSeconds(60));

        provider.setAccessTokenResponseClient(grant -> {
            refreshCalls.incrementAndGet();

            assertThat(grant.getRefreshToken().getTokenValue())
                    .isEqualTo("R1");

            return OAuth2AccessTokenResponse
                    .withToken("A2")
                    .tokenType(
                            OAuth2AccessToken.TokenType.BEARER)
                    .expiresIn(3600)
                    .refreshToken("R2")
                    .scopes(Set.of("openid", "orders.read"))
                    .build();
        });

        manager.setAuthorizedClientProvider(provider);
    }

    private OAuth2AuthorizeRequest authorizeRequest() {
        return OAuth2AuthorizeRequest
                .withClientRegistrationId("orders-client")
                .principal(alice)
                .attribute(
                        HttpServletRequest.class.getName(),
                        request)
                .attribute(
                        HttpServletResponse.class.getName(),
                        response)
                .build();
    }

    private void saveOldToken(Instant expiresAt) {
        Instant now = clock.instant();

        var token = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "A1",
                now.minusSeconds(7200),
                expiresAt,
                Set.of("orders.read"));

        var refresh = new OAuth2RefreshToken(
                "R1", now.minusSeconds(7200));

        var authorized = new OAuth2AuthorizedClient(
                registration,
                "alice",
                token,
                refresh);

        repository.saveAuthorizedClient(
                authorized, alice, request, response);
    }

    @Test
    void reusesAccessTokenWhileStillValid() {
        saveOldToken(clock.instant().plusSeconds(3600));

        OAuth2AuthorizedClient result =
                manager.authorize(authorizeRequest());

        assertThat(result.getAccessToken().getTokenValue())
                .isEqualTo("A1");
        assertThat(refreshCalls.get()).isZero();

        OAuth2AuthorizedClient saved =
                service.loadAuthorizedClient(
                        "orders-client", "alice");

        assertThat(saved.getRefreshToken().getTokenValue())
                .isEqualTo("R1");
    }

    @Test
    void refreshesAndPersistsRotatedRefreshToken() {
        saveOldToken(clock.instant().minusSeconds(60));

        OAuth2AuthorizedClient result =
                manager.authorize(authorizeRequest());

        assertThat(result.getAccessToken().getTokenValue())
                .isEqualTo("A2");
        assertThat(result.getRefreshToken().getTokenValue())
                .isEqualTo("R2");
        assertThat(refreshCalls.get()).isEqualTo(1);

        OAuth2AuthorizedClient saved =
                service.loadAuthorizedClient(
                        "orders-client", "alice");

        assertThat(saved).isNotNull();
        assertThat(saved.getAccessToken().getTokenValue())
                .isEqualTo("A2");
        assertThat(saved.getRefreshToken().getTokenValue())
                .isEqualTo("R2");
        assertThat(saved.getPrincipalName())
                .isEqualTo("alice");
        assertThat(saved.getClientRegistration()
                .getRegistrationId())
                .isEqualTo("orders-client");
    }

    @Test
    void refreshesBeforeExpiryWhenWithinClockSkew() {
        saveOldToken(clock.instant().plusSeconds(20));

        OAuth2AuthorizedClient result =
                manager.authorize(authorizeRequest());

        assertThat(result.getAccessToken().getTokenValue())
                .isEqualTo("A2");
        assertThat(refreshCalls.get()).isEqualTo(1);
    }
}
~~~

### 20.1. Scope of the Skeleton

- Uses Spring Security 6.x / Spring Boot 3.x style APIs.
- Tests the real manager/provider/store at an in-memory level.
- Token endpoint is a fake callback, no network.
- Does not test OIDC Login or browser callbacks.
- Does not test JDBC/Redis persistence or multi-instance concurrency.
- Does not require `@SpringBootTest` when constructing the objects directly.

### 20.2. Most Important Check in Refresh Tests

Do not only assert:

~~~java
assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("A2");
~~~

also reload from the store:

~~~java
OAuth2AuthorizedClient saved =
        service.loadAuthorizedClient(
                "orders-client", "alice");

assertThat(saved.getRefreshToken().getTokenValue())
        .isEqualTo("R2");
~~~

This catches "refresh succeeded yet failed to persist the new token".

### 20.3. Never Call Production Token Endpoints

All URIs use `example.test` with fake token responses. Never put real refresh tokens into test logs or fixtures.

## 21. When Using a Multi-Grant Provider Chain

In real applications:

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

manager.setAuthorizedClientProvider(provider);
~~~

### 21.1. Test Every Branch

- `authorizationCode`: interactive flow that granted an authorized client.
- `refreshToken`: nearly expired token with R1 present.
- `clientCredentials`: service needing a token without a user.
- Provider returns `null` when a grant does not apply.

### 21.2. Do Not Test Every Grant with One Fixture

If a registration uses `client_credentials`, never use a fake human OIDC user as proof of service authorization.

### 21.3. Provider Ordering and Selection

The provider chain evaluates providers by logic and grant. Tests should confirm the right provider activates when the context matches its grant/authorized client.

### 21.4. The Manager Does Not Switch to an Unauthorized Grant

If a registration has `authorization_code` without authorization/refresh capability, the manager does not turn it into `client_credentials` just to "get a token".

## 22. Testing Custom Success/Failure Handlers

The manager supports configuring:

~~~java
manager.setAuthorizationSuccessHandler(successHandler);
manager.setAuthorizationFailureHandler(failureHandler);
~~~

### 22.1. Success Handler

Can save authorized clients to a custom repository, emit metrics, or audit. Tests must verify:

1. The handler receives the right authorized client.
2. Principal and registration match.
3. Save runs exactly once with the new tokens.
4. If saving fails, the app behaves per policy.
5. Raw access/refresh tokens are never logged.

### 22.2. Failure Handler

Can remove stale authorized clients on `invalid_grant`, or preserve records on transient errors.

Tests should distinguish:

| Error | Possible policy choice |
|---|---|
| `invalid_grant` | Remove stale token, require reauthorization |
| Network timeout | Do not assume R1 was revoked |
| AS 503 | Bounded retries, retain token per policy |
| `invalid_client` | Alert on configuration/credential error |
| API 403 | Do not blindly refresh token |
| API 401 due to wrong audience | Fix token contract; refreshing will not help |

### 22.3. Caution When Overriding Default Handlers

If you call `setAuthorizationSuccessHandler(...)` and only record metrics while forgetting to save, you replaced the default persistence logic.

A manager test should catch stores that go un-updated after refresh.

### 22.4. Do Not Assume the Failure Handler Runs for Every API 401

The manager's failure handler handles failures in the **client authorization flow**. A downstream API 401 affects the authorized-client store only if the app's outbound client/filter/interceptor explicitly handles that failure.

## 23. Logout, Revocation, and Authorized Client Cleanup

Local logout normally clears the session/`SecurityContext`, yet may not remove authorized clients from an out-of-session service store.

### 23.1. Testing Cleanup on Logout

Given a business requirement "logout must delete user tokens":

1. Seed Alice's authorized client.
2. Invoke the appropriate logout handler.
3. Query the service/repository.
4. Assert Alice's authorized client record is removed if policy requires it.
5. Verify Bob's token under the same registration is untouched.
6. If calling an AS revocation endpoint, test that HTTP request separately.

### 23.2. Local Removal Differs from Token Revocation

Deleting a database record does not revoke the token at the Authorization Server. Issued access tokens may stay valid until expiry or revocation per AS/Resource Server policy.

### 23.3. Session-Backed vs. Service-Backed Records

- Session repository: records generally vanish with the session.
- JDBC/service store: records can survive browser logout.
- Custom Redis store: TTL, serialization, and cleanup must be tested.

### 23.4. Do Not Delete All Tenant Tokens When One Membership Changes

A user may remain authorized in multiple tenants. Cleanup must follow exact principal/registration/tenant policies.

## 24. Refresh Token Rotation and Concurrency

This is a real-world failure class hard to catch with single-threaded unit tests.

### 24.1. Simple Race

~~~mermaid
sequenceDiagram
    participant R1 as Request A
    participant R2 as Request B
    participant S as Authorized Client Store
    participant AS as Authorization Server
    R1->>S: Load A1/R1
    R2->>S: Load A1/R1
    R1->>AS: Refresh R1
    AS-->>R1: A2/R2
    R2->>AS: Refresh R1
    AS-->>R2: invalid_grant / reuse detection
    R1->>S: Save A2/R2
    R2->>S: Remove stale record? (danger)
~~~

Request B can wipe out the fresh record A just saved if the failure handler ignores concurrency/versions.

### 24.2. Single-Threaded Unit Tests Are Not Enough

A passing refresh test proves the sequential path, not safe distributed concurrency.

### 24.3. Designing a Concurrency Test

You can use:

- A `CountDownLatch` so two threads both load R1 together.
- A fake AS returning A2/R2 on the first call and rejecting R1 on the second.
- A custom in-memory repository supporting versioning/CAS.
- Assertions that the final record is never deleted or overwritten with stale data.
- Multi-instance tests when using a shared JDBC/Redis store.

### 24.4. Strategies

- Single-flight refresh per principal/registration.
- Distributed locking where needed.
- Optimistic locking/versioning or compare-and-swap.
- Version-checked failure removal matching the failing token version.
- Controlled retries without blindly reusing R1.
- Avoid firing concurrent refresh requests when the AS enforces strict rotation.

### 24.5. Do Not Assume the Manager Solves Distributed Races Automatically

`DefaultOAuth2AuthorizedClientManager` coordinates providers and storage, yet atomic multi-process refresh depends on your repository, handlers, and application architecture.

## 25. Testing Storage Failures

When a custom JDBC/Redis store fails:

- Load failure: the app must avoid returning the wrong token.
- Save failure post-refresh: A2/R2 exists only in memory while the store still holds A1/R1.
- Remove failure after `invalid_grant`: stale record remains.
- Serialization failure: tokens lose timestamps or scopes.
- Network partition: two instances observe diverging states.

### 25.1. Fake Repository Throws

Using Mockito:

~~~java
doThrow(new IllegalStateException("Storage unavailable"))
        .when(repository)
        .saveAuthorizedClient(any(), any(), any(), any());
~~~

Works only when `repository` is a configured Mockito mock/spy. Tests must assert the system's expected exception/fallback policy.

### 25.2. Never Silently Swallow Persistence Errors

If refresh succeeds while saving fails, the backend might use A2 for the current request, yet load stale A1/R1 on the next request.

Emit error handling/metrics to surface the issue instead of treating a refresh as complete when persistence failed.

### 25.3. Testing Recovery

Once the store recovers, the flow may require reauthorization/re-refresh or handling the stale record. Base tests on your AS's real rotation policy.

## 26. HTTP-Level Refresh Tests with a Fake Authorization Server

A fake `OAuth2AccessTokenResponseClient` does not verify HTTP request encoding. To test the real HTTP layer, use a test Authorization Server such as WireMock, MockWebServer, or an HTTP transport mock compatible with your version.

### 26.1. Contract to Verify

A refresh HTTP request typically looks like:

~~~http
POST /oauth2/token HTTP/1.1
Host: as.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_CREDENTIALS>

grant_type=refresh_token&refresh_token=R1
~~~

Exact client authentication method and parameters depend on `ClientRegistration` and AS policy.

### 26.2. Fake Token Response

~~~json
{
  "access_token": "A2",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "R2",
  "scope": "orders.read"
}
~~~

### 26.3. Asserting Exact HTTP Behavior

- Calls the right token endpoint host.
- Sends `grant_type=refresh_token`.
- Sends the exact R1 value.
- Uses the right client authentication method (`Basic`/Post/`private_key_jwt`...).
- Parses A2/R2, `expires_in`, and scopes accurately.
- Handles AS 400 `invalid_grant` properly.
- Never logs `Authorization` headers or refresh tokens.
- Never follows redirects to unintended hosts carrying secrets or tokens.

### 26.4. Response Client APIs Vary Across Versions

Spring Security ships different HTTP client implementations for token endpoints across versions, such as `RestTemplate`-based and `RestClient`-based variants.

This lesson uses the **`OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` interface** as a stable seam for testing the manager. When testing HTTP serialization, select the concrete implementation matching your framework version.

### 26.5. Never Call a Production Authorization Server

Use a fake HTTP server and dummy credentials; never place production R1 tokens in test fixtures.

## 27. MockMvc Tests Combined with `oidcLogin()`

`oidcLogin()` is convenient when a controller needs a browser OIDC `Authentication`:

~~~java
mvc.perform(get("/orders")
                .with(oidcLogin()))
        .andExpect(status().isOk());
~~~

However, it does not prove:

- The authorized client manager refreshed A1 with R1.
- The token endpoint returned A2/R2.
- The repository saved the new tokens.
- The HTTP client sent A2 (not an ID token) to the Orders API.
- Distributed refresh token rotation is safe.

### 27.1. Layer Your Tests

| Layer | Tool |
|---|---|
| Post-OIDC-Login controller | `MockMvc` + `oidcLogin()` |
| Manager/provider refresh | Unit/component tests + fake token response |
| `AuthorizedClientService` persistence | JDBC/Redis integration tests |
| Outbound API `Authorization` header | Mock HTTP client/server |
| OIDC Authorization Code callback | Login filter + fake OP |
| Resource Server Bearer validation | `jwt()` and decoder tests |
| Multi-node concurrent refresh | Concurrency/integration tests |

### 27.2. Do Not Mock the Manager in a Controller Test and Claim Refresh Works

If a controller test only does:

~~~java
when(manager.authorize(any()))
        .thenReturn(fakeAuthorizedClient);
~~~

you have only verified the controller calls the manager. Test the manager separately as shown above.

## 28. Real-World Pitfall: Which API Was the Token Issued For?

A manager may return A2 cleanly from refresh, yet the Orders API still returns 401 if the token has the wrong audience or issuer.

### 28.1. Client Authorization Success Differs from Resource Server Acceptance

~~~text
Manager:
  A2 exists, expiresAt is valid.

Orders API:
  valid issuer?
  audience = orders-api?
  sufficient scopes?
  subject/tenant authorized?
~~~

Two separate layers.

### 28.2. Never Substitute an ID Token for an Access Token

An OIDC ID token is for the Relying Party. `OAuth2AuthorizedClient.getAccessToken()` is where to obtain the OAuth access token issued to the client.

### 28.3. An API 403 Does Not Need a Token Refresh

If A2 lacks the `orders.write` scope or the user lacks object-level permissions, refreshing under the same grant will not expand permissions.

### 28.4. Token Reuse Does Not Mean the Token Has Not Been Revoked

If an access token is still valid by `expiresAt` yet was revoked at the AS, the manager may reuse A1 based on local metadata. The Resource Server can still reject it.

Tests should account for tradeoffs among expiry, revocation freshness, and introspection/RS validation.

## 29. Comprehensive Test Plan

| Scenario | Evidence to assert |
|---|---|
| No authorized client, provider can issue | New token persisted |
| No authorized client, provider returns `null` | Manager returns `null`/matching state |
| Valid access token | No token endpoint call; A1 reused |
| Nearly expired access token | Proactive refresh per clock skew |
| Expired access token + R1 | A2 returned |
| Refresh response includes R2 | Store retains R2 |
| Refresh response omits R2 | Token retention/usage follows provider/AS contract |
| Expired + no refresh token | Never fabricates A2 |
| `invalid_grant` | Failure policy and stale client removal |
| AS timeout/503 | Does not wrongly delete token per policy |
| Save succeeds | Reload returns matching tokens |
| Save fails | Exception/handling per policy |
| Principal Alice vs. Bob | Token isolation |
| Registration `orders` vs. `reports` | Token isolation |
| Tenant issuer/subject collision | No identity/token mix-up |
| Browser logout | Session/store cleanup per policy |
| Concurrent refresh | R2 never lost in race |
| Client credentials job | Service manager, no Servlet request |
| HTTP token exchange | Form params, client auth, response parsing |
| API call | Bearer access token sent to right host/audience |
| OP authentication callback | Separate test, not manager unit test |

## 30. Troubleshooting

| Symptom | Common cause | What to check |
|---|---|---|
| `No thread-bound request found` | Servlet manager used outside request | Pass mock request/response or use service manager |
| `authorize()` returns `null` | No client and provider cannot authorize | Grant/provider/registration |
| Expired token still returned | No refresh token / provider returned `null` | Enforce reauthorization policy |
| Token refreshes on every call | Clock skew too large or wrong expiry | Fixed `Clock`/`expiresAt` |
| Never refreshes | Missing refresh token/provider or wrong clock | Provider chain/tokens |
| Refresh returns A2 yet store keeps A1 | Success handler/save skipped | Repository/service wiring |
| Rotated R2 lost | Serialization/persistence omits refresh token | Reload after save |
| Repeated `invalid_grant` | Stale record not removed | Failure handler |
| R1 used twice | Concurrency/rotation race | Lock/CAS |
| Bob sees Alice's token | Store key omits principal | Principal isolation |
| Orders receives reports token | Wrong registration ID selected | Registration isolation |
| API 401 despite valid A2 | Audience/issuer/revocation | Resource Server |
| API 403 | Missing scope/owner/tenant | Domain policy |
| Manager test hits real AS | Token response client not faked | Fake transport |
| Test triggers issuer discovery | `ClientRegistration` built from `issuer-uri` | Test registration fixture |
| `@WebMvcTest` lacks manager | Bean not loaded | Appropriate imports/mocks |
| Mockito verifies more saves than expected | Setup seeding counted by spy | `clearInvocations` after seeding |
| Expiry test is flaky | `Instant.now()` drifting during run | Fixed `Clock` |
| Redis fails loading token object | Serializer/version | Persistent store integration |

## 31. Common Misconceptions

**"The manager always calls the token endpoint on `authorize()`."**

No. Valid access tokens are normally reused.

**"A provider returning no new token means the manager always returns `null`."**

No. If an authorized client already exists, the manager can return the existing client.

**"An expired access token that cannot refresh will automatically request an authorization code."**

No. Authorization Code requires a browser/AS authorization flow.

**"A successful refresh means it was persisted."**

Not necessarily if the success handler was overridden or the store failed. Reload and assert.

**"When the AS rotates R1 to R2, only A2 needs to be saved."**

No. Save the new refresh token whenever issued.

**"`invalid_grant` is the same as a 503 network error."**

No. Removal and retry policies differ.

**"`DefaultOAuth2AuthorizedClientManager` works well in a scheduled job with no request."**

Avoid it. Use the service manager for non-web contexts.

**"`oidcLogin()` is enough to test refresh tokens."**

No. It mocks an OIDC principal without running token lifecycles.

**"In-memory store tests prove JDBC/Redis serializers are safe."**

No. Write separate persistence integration tests.

**"The manager handles atomic refreshes across multiple servers."**

Never assume so. Storage and concurrency require explicit design and testing.

**"An unexpired access token guarantees the API will accept it."**

No. The API still enforces issuer, audience, revocation, scope, and ownership rules.

## 32. Practice Scenarios

### A. Portal Calls Orders API Repeatedly

A1 remains valid for 30 minutes.

**Test:** seed A1/R1, call manager, assert zero calls to fake token-response client and A1 returned.

### B. Expired Token

A1 expired, R1 valid.

**Test:** fake AS returns A2/R2; assert both return value and persisted record hold A2/R2.

### C. Nearly Expired Token

A1 has 20 seconds left, clock skew is 60 seconds.

**Test:** refresh fires proactively once.

### D. AS Issues No Refresh Token

Only A1 exists, then expires.

**Test:** manager never invents R1 or A2; application handles reauthorization.

### E. Revoked Refresh Token

Fake AS returns `invalid_grant`.

**Test:** exception/failure handler and stale-client removal per policy.

### F. Background Reporting Job

Job runs outside requests using `client_credentials`.

**Test:** service manager with technical principal, no Servlet request needed.

### G. Two Users Sharing One Registration

Alice and Bob both use the Orders OAuth client.

**Test:** store and manager return isolated tokens per principal.

### H. Two API Registrations

Alice has both an Orders token and a Reporting token.

**Test:** tokens never cross between registration IDs.

### I. Two Requests Refreshing the Same R1

AS enforces refresh token rotation.

**Test:** concurrency harness with latch and CAS/store versioning, ensuring final R2 is never deleted by a failing stale request.

### J. API Still Returns 401 Post-Refresh

A2 has an audience meant for the Billing API.

**Test:** manager refresh works, yet the API contract/audience is wrong; test the Resource Server separately.

## 33. Self-Check Questions

**1. What does `ClientRegistrationRepository` store?**

OAuth client configuration such as client ID, grant type, endpoints, and scopes.

**2. What does `OAuth2AuthorizedClientService` store?**

Authorized client access/refresh tokens keyed by registration and principal.

**3. When should you use `DefaultOAuth2AuthorizedClientManager`?**

When running inside a Servlet request/response context.

**4. Which manager should a background job use?**

`AuthorizedClientServiceOAuth2AuthorizedClientManager`.

**5. Why are `MockHttpServletRequest`/`Response` needed?**

So the Servlet manager/repository can handle request context in tests without real HTTP.

**6. Does the manager always call the token endpoint?**

No. Valid tokens are reused.

**7. What does the refresh provider evaluate?**

Token expiry/clock skew, refresh token presence, and authorization context.

**8. Why use a fixed `Clock`?**

To avoid flaky tests at expiry boundaries.

**9. What does a fake token-response client help test?**

Provider refresh decisions and manager/store behavior without calling an AS over the network.

**10. When refresh returns A2/R2, what must be asserted?**

That the manager returns A2/R2 and the repository/service persists A2/R2.

**11. What happens if a custom success handler forgets to save?**

Refresh may return new tokens while the store retains stale tokens.

**12. What should `invalid_grant` normally trigger?**

Authorization failure handling and typically removing the stale client per policy.

**13. Should tokens be deleted on every timeout?**

Not automatically. Timeouts can be transient errors, not proof R1 was revoked.

**14. If a token expires without a refresh token, does the manager request a new authorization code?**

No. An interactive/appropriate authorization flow is required.

**15. Why test principal isolation?**

To prevent Alice from using Bob's token under the same registration.

**16. Why test registration isolation?**

To prevent sending one API/AS's token to another API.

**17. Do in-memory tests prove JDBC/Redis persistence works?**

No. Dedicated store integration tests are required.

**18. Does `oidcLogin()` test refresh token rotation?**

No.

**19. What risk arises when two requests refresh R1 concurrently?**

Rotation races, `invalid_grant`, or deleting/overwriting R2.

**20. Does the manager returning a valid access token guarantee the API accepts it?**

No. The Resource Server also enforces issuer, audience, scope, revocation, and domain authorization.

## Key Takeaways

- **`OAuth2AuthorizedClientManager` coordinates load -> provider decision -> save/failure**, rather than acting as a simple HTTP token client.
- **`ClientRegistrationRepository` stores client config**, while **`OAuth2AuthorizedClientRepository`/`Service` stores access/refresh tokens per registration and principal**.
- **Valid tokens should be reused**, avoiding unnecessary token endpoint calls.
- **The refresh provider relies on clock, clock skew, and refresh token**; test with a fake `OAuth2AccessTokenResponseClient` to verify refresh logic without a real AS.
- **After refresh, assert both the return value and the persisted record**, especially new access token A2 and rotated refresh token R2.
- **`invalid_grant`, timeouts, 503s, and API 403s do not share the same failure policy.** Never remove or retry blindly.
- **The Servlet manager needs request/response context**; background services use `AuthorizedClientServiceOAuth2AuthorizedClientManager`.
- **Never mix authorized clients across users, registrations, issuers, or tenants.** Token store/cache keys must align with trust boundaries.
- **Concurrency and real persistence require integration tests**; single-threaded in-memory tests do not prove safe atomic rotation on Redis/JDBC.
- **`oidcLogin()` only simulates an OIDC principal** and does not replace manager/token-refresh tests; OIDC callbacks, HTTP token endpoints, and Resource Server validation also require dedicated tests.
