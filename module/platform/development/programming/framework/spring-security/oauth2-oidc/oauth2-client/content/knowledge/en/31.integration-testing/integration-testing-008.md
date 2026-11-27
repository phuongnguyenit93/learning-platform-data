# 31.8. Testing Client Credentials and Downstream Scopes

A Spring Boot application does not only call an OAuth2/OIDC Provider to **log in end-users**. It can also run an automated job—such as syncing reports, fetching catalogs, or sending invoices—that must call a **downstream API** using **the application's own authority**. In that case, the OAuth 2.0 **Client Credentials Grant** is a common choice.

For example:

```text
Reporting Worker (Spring Boot)
    |
    | POST /oauth2/token
    | grant_type=client_credentials
    | scope=reports.read
    | Client authentication: client_id/client_secret
    v
Authorization Server
    |
    | access_token = AT-123
    | token_type   = Bearer
    | expires_in   = 3600
    | scope        = reports.read
    v
Reporting Worker
    |
    | GET /api/reports
    | Authorization: Bearer AT-123
    v
Downstream Resource Server
    |
    +-- valid token + has reports.read -> 200
    +-- invalid token -> usually 401
    +-- valid token yet missing scope -> usually 403
```

To perform proper **integration testing**, we must prove two distinct behaviors:

1. **Client credentials flow:** Spring Security uses the right `ClientRegistration`, authenticates to the token endpoint, requests the configured scopes, handles the token response, and manages tokens in `OAuth2AuthorizedClient`.
2. **Downstream authorization:** the real HTTP call carries the proper access token; the Resource Server (or its test double) enforces **issuer/audience/scope** policies and returns the matching outcome.

Never stop at mocking:

```java
when(oauth2AuthorizedClientManager.authorize(any()))
    .thenReturn(fakeAuthorizedClient);
```

and claim Client Credentials Grant has been tested. That mock is helpful for **unit testing** a service, yet **does not test the HTTP token request, client authentication, scopes, or the mechanism attaching the Bearer token to downstream requests**.

This lesson belongs to Chapter **31. Integration Testing** of the *Spring Security OAuth 2.0 OIDC Client* module. Primary examples use Spring Boot 3.x, Spring Security 6.x, Java 17+, `RestClient`, `OAuth2AuthorizedClientManager`, JUnit 5, and **MockWebServer**. The final section compares with WebClient/Reactive.

> **Scope:** This is OAuth2 **Client Credentials**, not OIDC interactive login. There is no browser authorization redirect, authorization code, PKCE, or end-user ID Token in the standard flow. All URLs, client secrets, and access tokens in this lesson are synthetic data for test environments. Never use real accounts or production tokens.

---

## 1. What Problem Does Client Credentials Grant Solve?

The Client Credentials Grant (RFC 6749, Section 4.4) allows a **confidential client** to authenticate to the Authorization Server and receive an access token based on the client's own permissions.

Typical applications:
- Scheduled jobs reading reports from a Reporting API;
- Backend services syncing inventory between two systems;
- Event-processing services calling a downstream Audit API;
- Batch jobs accessing data granted specifically to a service account;
- An internal service calling another API **without acting on behalf of a specific end-user**.

### 1.1. Distinguishing from Authorization Code + OIDC Login

| Criterion | `authorization_code` + OIDC | **`client_credentials`** |
| --- | --- | --- |
| Who is being authenticated? | End-user via OP, plus client | **OAuth2 client/service identity** |
| Browser redirect to AS | Yes | **Not needed** |
| `/login/oauth2/code/{registrationId}` | Present in login flow | Absent |
| `state` and PKCE | Used in authorization redirect/code flow | Not used in this mechanism |
| OIDC `nonce` / ID Token | May be present | **Not a standard part of this grant** |
| Token endpoint | Exchanges authorization code | Directly requests token with `grant_type=client_credentials` |
| Scope | Per authorization/user/client policy | Per **client registration/service permission** |
| Refresh token | May be issued per OP policy | **Normally not issued**; RFC 6749 recommends against issuing refresh tokens |
| Principal of authorized-client cache | Usually tied to a user | Should use a **stable service principal name** |
| Downstream permissions | Per user/delegated token | Per **application/service token** |

**Never use client credentials as a way to "borrow admin privileges" to substitute for a failed user login.** This grant does not prove user Alice authenticated and does not allow self-assigning permissions as Alice.

### 1.2. Three Roles That Must Not Be Mixed

- **OAuth2 Client:** the Spring Boot Reporting Worker that needs to obtain a token.
- **Authorization Server (AS):** authenticates the client and issues an access token with granted scopes.
- **Resource Server (RS):** the Reporting API receiving the Bearer token, verifying it, and enforcing access permissions.

In practice, the AS and RS may belong to the same product/cluster, yet their **protocol responsibilities and permissions differ**.

---

## 2. What a Good Integration Test Must Measure

```mermaid
sequenceDiagram
    autonumber
    participant Test as JUnit Test
    participant App as Spring OAuth2 Client/RestClient
    participant AS as Mock Token Endpoint
    participant API as Mock Downstream API

    Test->>AS: Enqueue token response (scopes granted)
    Test->>API: Enqueue 200 / 401 / 403 response
    Test->>App: Invoke downstream client/service
    App->>AS: POST /token, client auth, grant_type, scope
    AS-->>App: access_token + token_type + expires_in + scope
    App->>App: Save OAuth2AuthorizedClient
    App->>API: GET /reports with Bearer access token
    API-->>App: HTTP response
    App-->>Test: Return result / surface error
    Test->>AS: Assert token request form and client auth
    Test->>API: Assert Authorization header, path, method
    Test->>App: Assert granted scopes/cache/error handling
```

An end-to-end test **across Spring Client components and mocked HTTP endpoints** should observe:

| Stage | Assertion |
| --- | --- |
| Registration | Exact `registrationId`, token URI, and `client_credentials` grant |
| Client authentication | AS receives client authentication with the right method, e.g. `client_secret_basic` |
| Token request | HTTP POST `application/x-www-form-urlencoded`, `grant_type=client_credentials` |
| Requested scopes | Form sends scopes matching registration policy |
| Token response | Accepts `Bearer` token, expiry, and **granted scopes** |
| Authorized client | Token stored under the matching registration and service principal |
| Outbound downstream request | Bearer token placed in the `Authorization` header |
| API authorization | 200 when token accepted/authorized; 401/403 per contract |
| Token reuse | Does not unnecessarily re-request tokens while valid and cached properly |
| Failure isolation | Token endpoint failures differ from downstream 401/403; never sends tokens to unknown hosts |

**Important:** A MockWebServer scripted to return HTTP 403 **does not prove the production Resource Server enforces scopes**. That is a **contract test** for how the client reacts. To test that Spring Resource Server enforces scopes, run a separate test through its `SecurityFilterChain`, JWT decoder/introspection, and authorization rules.

## 3. Scopes: "Requested," "Granted," and "Enforced"

OAuth2 has three scope sets that are easily confused:

```text
REQUESTED:
  Client registration requests:
    reports.read reports.export

GRANTED:
  Authorization Server actually grants:
    reports.read

ENFORCED:
  Resource Server endpoint /reports/export requires:
    reports.export

Result:
  Valid token yet missing reports.export -> 403 insufficient_scope
```

| Concept | Where Defined | Role |
| --- | --- | --- |
| **Requested scope** | `ClientRegistration.getScopes()` or token request | What the client asks for |
| **Granted scope** | Token response `scope`, token metadata/claims per AS contract | What the AS actually grants |
| **Required scope** | Resource Server authorization policy | What the endpoint demands |

### 3.1. Requesting a Scope Does Not Guarantee Receiving It

```yaml
scope:
  - reports.read
  - reports.export
```

is only what **the client wants to ask for**. The AS may reject with `invalid_scope` or issue a narrower set of scopes per policy.

Example token response:

```json
{
  "access_token": "TEST-ACCESS-TOKEN",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "reports.read"
}
```

If the application still attempts to call `/reports/export` requiring `reports.export`, the Resource Server should block it.

### 3.2. Token Responses Might Omit the scope Field

Per RFC 6749, the token response must include the `scope` field **if the granted scope differs from the requested scope**; if identical, the field may be omitted.

This means:
- Never build a custom parser requiring `scope` to always be present;
- Never assume a response omitting `scope` means "full permissions";
- Never blindly assume `ClientRegistration.getScopes()` equals granted scopes without checking your AS/client library contract;
- When testing scope narrowing/reduction, return **`scope` explicitly**.

### 3.3. JWT Claims `scope` and `scp`

Many ASes issue JWT access tokens containing:

```json
{
  "iss": "https://auth.example.test/issuer",
  "sub": "reporting-worker",
  "aud": ["https://reports-api.example.test"],
  "scope": "reports.read reports.export",
  "exp": 1893456000
}
```

Some providers use `scp` (string or collection per contract). Spring Resource Server can map recognized scopes to `SCOPE_*` authorities.

For example:
- `reports.read` → `SCOPE_reports.read`;
- `reports.export` → `SCOPE_reports.export`.

**Do not assume every role, group, or permissions claim is an OAuth2 scope**, and never equate `ROLE_ADMIN` with `SCOPE_reports.export`.

### 3.4. Audience Is Equally Critical

Even when a token carries `reports.read`, downstream must verify the token was minted **for the target Resource Server**, e.g. `aud=https://reports-api.example.test`.

A token with the same scope name yet issued for the Payments API audience **must not be accepted** by the Reports API. A valid scope **never substitutes** for issuer, audience, signature, expiry, or token status validation.

---

## 4. Spring Boot Configuration for Client Credentials

Suppose the application needs to call a Reporting API:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-machine:
            provider: reports-as
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
              - reports.export
        provider:
          reports-as:
            token-uri: https://auth.example.test/oauth2/token
```

**Explanation:**

- `reports-machine`: `registrationId` used by the service to select the client;
- `reports-as`: Authorization Server configuration key;
- `client-id` / `client-secret`: credentials of the confidential client;
- `client_secret_basic`: authenticates the client with HTTP Basic at the token endpoint;
- `client_credentials`: client requests tokens directly without browser login;
- `scope`: scopes requested by the client;
- `token-uri`: AS endpoint to obtain tokens.

Unlike OIDC Login, a client credentials registration **does not need** `redirect-uri` or `authorization-uri` for this flow.

### 4.1. Never Send the Client Secret to the Resource Server

```text
AS token request:
  Authorization: Basic base64(client-id:client-secret)
  grant_type=client_credentials

Downstream API request:
  Authorization: Bearer <access-token>
```

**The client secret is not an API Bearer token.** Downstream receives only the access token, never `client_secret`.

### 4.2. Client Authentication Methods Can Vary

The AS may require:
- `client_secret_basic`;
- `client_secret_post`;
- `private_key_jwt`;
- mTLS client authentication;
- A provider-specific method per AS documentation.

Do not swap methods in tests just to "make it pass" if production uses a different method. Each method carries distinct secret/key protection requirements. The lesson uses Basic for ease of illustration; real tests must follow the actual AS contract.

### 4.3. Never Configure Overly Broad Scopes

A batch job that only reads reports should not request:

```text
reports.read reports.write reports.export reports.delete admin
```

unless required. Least-privilege scopes limit blast radius if an access token leaks.

---

## 5. Relevant Spring Security Client Components

| Component | Function |
| --- | --- |
| `ClientRegistrationRepository` | Stores registration metadata |
| `OAuth2AuthorizedClientProvider` | Strategy handling grants, e.g., `clientCredentials()` |
| **`OAuth2AuthorizedClientManager`** | Coordinates token acquisition/refresh and saves authorized clients |
| `OAuth2AuthorizedClientService` | Persists `OAuth2AuthorizedClient` by registration/principal |
| `OAuth2AuthorizedClient` | Registration + access token, optional refresh token |
| **`AuthorizedClientServiceOAuth2AuthorizedClientManager`** | Manager suited for jobs/background tasks without `HttpServletRequest` |
| `DefaultOAuth2AuthorizedClientManager` | Manager designed for servlet request contexts |
| `OAuth2ClientHttpRequestInterceptor` | Attaches Bearer tokens to `RestClient` |
| `RequestAttributeClientRegistrationIdResolver` | Reads registration ID from RestClient request attributes |
| `RequestAttributePrincipalResolver` | Reads service principal name from RestClient request attributes |

### 5.1. Why Use AuthorizedClientServiceOAuth2AuthorizedClientManager?

A scheduled job runs:

```java
@Scheduled(fixedDelayString = "PT15M")
void syncReports() {
    // No end-user HttpServletRequest exists here.
}
```

`DefaultOAuth2AuthorizedClientManager` is typically tied to the servlet request context. Without an HTTP request, Spring Security 6.x recommends **`AuthorizedClientServiceOAuth2AuthorizedClientManager`**, using `OAuth2AuthorizedClientService` to store tokens per client/principal.

### 5.2. Dedicated Manager Bean for Client Credentials

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class MachineClientConfig {

    @Bean
    OAuth2AuthorizedClientManager machineAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

This manager can:
- Request a token when the client is not yet authorized;
- Reuse an unexpired token from storage/cache;
- Request a new access token when the old token expires per policy;
- Persist results through `OAuth2AuthorizedClientService`.

**Do not confuse requesting a new access token under client credentials with a refresh token grant.** Client Credentials normally does not need a refresh token; when the token expires, the client re-authenticates to the token endpoint for a new access token.

---

## 6. Machine Client Principal Name: Do Not Use Random Users

In Spring Security, `OAuth2AuthorizedClient` is commonly keyed by:

```text
(clientRegistrationId, principalName)
```

For user login:

```text
("google", "alice")
("google", "bob")
```

For application-level client credentials, use a **stable service principal name**:

```text
("reports-machine", "reports-batch")
```

If every request uses a random principal, the cache creates separate access tokens for the same service, bloating storage and token endpoint traffic.

### 6.1. Explicitly Requesting Tokens in a Service

```java
package example.reports;

import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class MachineTokenService {

    private final OAuth2AuthorizedClientManager manager;

    public MachineTokenService(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public OAuth2AuthorizedClient reportsClient() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-machine")
                .principal("reports-batch")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "Client credentials authorization was not completed");
        }
        return client;
    }
}
```

The resulting `OAuth2AuthorizedClient` carries the access token and granted scope metadata from the token response per Spring/AS contract. **Never return `getTokenValue()` of this client to a browser via a debug API.**

### 6.2. Cache Tests Must Keep the Same Principal

If the first test uses `principal("reports-batch")` while the next uses `principal("alice")`, an extra token request occurs because the storage keys differ. That is not necessarily a cache bug.

### 6.3. Separate Machine Principals from OAuth2 End-User Principals

A machine access token proves nothing about Alice logging in. If downstream endpoints scope data to Alice, an approved business policy/identity propagation mechanism is required. **Never substitute a client credentials token for a user token and inject a user ID from a raw HTTP header.**

---

## 7. RestClient: Attaching Bearer Tokens Automatically

Spring Security 6.5 provides `OAuth2ClientHttpRequestInterceptor` for `RestClient`.

```java
package example.http;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
import org.springframework.web.client.RestClient;

@Configuration
class ReportsRestClientConfig {

    @Bean
    RestClient reportsRestClient(
            OAuth2AuthorizedClientManager machineAuthorizedClientManager) {

        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(
                machineAuthorizedClientManager);

        // In scheduled jobs, do not depend on a current web user's SecurityContext.
        oauth2.setPrincipalResolver(
            new RequestAttributePrincipalResolver());

        return RestClient.builder()
            .baseUrl("https://reports-api.example.test")
            .requestInterceptor(oauth2)
            .build();
    }
}
```

When making a request:

```java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributePrincipalResolver.principal;

String response = reportsRestClient.get()
    .uri("/api/reports")
    .attributes(clientRegistrationId("reports-machine"))
    .attributes(principal("reports-batch"))
    .retrieve()
    .body(String.class);
```

The two attributes serve distinct roles:

- **`clientRegistrationId(...)`:** selects the **client registration**;
- **`principal(...)`:** selects the service principal name for the authorized-client manager/cache.

For valid Java syntax, write the static imports above on single lines:

```java
import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;
```

### 7.1. Why Explicitly Specify the Principal Resolver?

In Spring Security 6.5, `OAuth2ClientHttpRequestInterceptor` defaults to reading the principal from `SecurityContextHolder`. For machine-to-machine background calls, explicitly configure `RequestAttributePrincipalResolver` and supply a stable name.

Do not rely on whatever user happens to be logged in on another request to obtain an application-level token.

### 7.2. Never Send Tokens to User-Controlled URLs

A `RestClient` with an OAuth2 interceptor automatically attaches Bearer tokens to outbound HTTP requests. Never allow callers to supply an arbitrary URI like `https://evil.example.test` and receive `reports-machine`'s token.

Instead:
- Use an allowlisted base URL;
- Constrain callable paths;
- Never follow redirects to untrusted hosts with Bearer tokens;
- Check for SSRF/open redirects;
- Never enable a broad default registration across all HTTP clients.

---

## 8. Dependencies for Integration Testing

### 8.1. Maven

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
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
        <groupId>com.squareup.okhttp3</groupId>
        <artifactId>mockwebserver</artifactId>
        <version>4.12.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

This is for learning purposes. When using a Spring Boot BOM or dependency management plugin, verify project compatibility rather than blindly copying versions into production.

### 8.2. Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**This lesson writes Markdown only and does not run Gradle or alter a project build.** These dependency snippets guide learners building their own demo project.

### 8.3. Why Choose MockWebServer?

`MockWebServer` lets you:
- Spin up a local HTTP server on a random port;
- Enqueue JSON token responses;
- Inspect received HTTP method, path, headers, and body;
- Stub downstream HTTP 200/401/403 responses;
- Avoid connecting to a production OP;
- Test real `RestClient`/Spring HTTP transport rather than a mocked manager.

WireMock, MockServer, or a fake Authorization Server all work; the tool name matters less than **assertions on the HTTP contract**.

---

## 9. Hands-On Integration Test: Token Endpoint and Downstream HTTP

This is a **self-contained** example using JUnit 5, MockWebServer, Spring Security Client, and RestClient. It does not need to boot an entire Spring Boot application context, yet it exercises the **real manager, OAuth2 token client HTTP call, and outbound interceptor**—far more layers than a unit test mocking the manager.

### 9.1. Complete Test Class

```java
package example.reports;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

class MachineToMachineHttpIntegrationTest {

    private MockWebServer authorizationServer;
    private MockWebServer downstreamApi;

    private InMemoryOAuth2AuthorizedClientService authorizedClientService;
    private RestClient restClient;

    @BeforeEach
    void setUp() throws IOException {
        authorizationServer = new MockWebServer();
        downstreamApi = new MockWebServer();

        authorizationServer.start();
        downstreamApi.start();

        ClientRegistration registration =
            ClientRegistration.withRegistrationId("reports-machine")
                .clientId("test-reports-client")
                .clientSecret("test-only-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri(
                    authorizationServer.url("/oauth2/token").toString())
                .scope("reports.read", "reports.export")
                .build();

        InMemoryClientRegistrationRepository registrations =
            new InMemoryClientRegistrationRepository(registration);

        authorizedClientService =
            new InMemoryOAuth2AuthorizedClientService(registrations);

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());

        OAuth2ClientHttpRequestInterceptor interceptor =
            new OAuth2ClientHttpRequestInterceptor(manager);

        // Keep the service principal stable across calls.
        interceptor.setPrincipalResolver(
            new RequestAttributePrincipalResolver());

        restClient = RestClient.builder()
            .requestInterceptor(interceptor)
            .build();
    }

    @AfterEach
    void tearDown() throws IOException {
        authorizationServer.shutdown();
        downstreamApi.shutdown();
    }

    private void grantReadOnlyToken() {
        authorizationServer.enqueue(
            new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""
                    {
                      "access_token": "test-access-token",
                      "token_type": "Bearer",
                      "expires_in": 3600,
                      "scope": "reports.read"
                    }
                    """));
    }

    private String callReports() {
        return restClient.get()
            .uri(downstreamApi.url("/api/reports").toString())
            .attributes(clientRegistrationId("reports-machine"))
            .attributes(principal("reports-batch"))
            .retrieve()
            .body(String.class);
    }

    @Test
    void requestsScopesAndPassesAccessTokenToDownstream()
            throws InterruptedException {
        grantReadOnlyToken();

        downstreamApi.enqueue(
            new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("{\"items\":2}"));

        String body = callReports();

        assertThat(body).isEqualTo("{\"items\":2}");

        RecordedRequest tokenRequest =
            authorizationServer.takeRequest(3, TimeUnit.SECONDS);

        assertThat(tokenRequest).isNotNull();
        assertThat(tokenRequest.getMethod()).isEqualTo("POST");
        assertThat(tokenRequest.getPath())
            .isEqualTo("/oauth2/token");
        assertThat(tokenRequest.getHeader("Content-Type"))
            .startsWith("application/x-www-form-urlencoded");
        assertThat(tokenRequest.getHeader("Authorization"))
            .startsWith("Basic ");

        String form = tokenRequest.getBody().readUtf8();
        assertThat(form).contains("grant_type=client_credentials");
        assertThat(form).contains("scope=");
        assertThat(form).contains("reports.read");
        assertThat(form).contains("reports.export");

        RecordedRequest apiRequest =
            downstreamApi.takeRequest(3, TimeUnit.SECONDS);

        assertThat(apiRequest).isNotNull();
        assertThat(apiRequest.getMethod()).isEqualTo("GET");
        assertThat(apiRequest.getPath()).isEqualTo("/api/reports");
        assertThat(apiRequest.getHeader("Authorization"))
            .isEqualTo("Bearer test-access-token");

        // Token response granted only reports.read,
        // even though registration requested reports.export too.
        var saved = authorizedClientService
            .loadAuthorizedClient("reports-machine", "reports-batch");

        assertThat(saved).isNotNull();
        assertThat(saved.getAccessToken().getScopes())
            .contains("reports.read")
            .doesNotContain("reports.export");
    }
}
```

### 9.2. What Does This Test Actually Verify?

1. `ClientRegistration` actually uses the `client_credentials` grant;
2. The authorized client manager calls the fake HTTP token endpoint;
3. The HTTP token request is a POST form containing the grant type and requested scopes;
4. Client authentication uses an Authorization Basic header;
5. The token response is parsed;
6. `OAuth2AuthorizedClientService` persists the token under `reports-machine` and `reports-batch`;
7. The RestClient interceptor attaches the Bearer token to the downstream request;
8. Granted scopes reflect the explicit response rather than blindly assuming all requested scopes were granted.

**What it does not prove**:
- Whether the secret in real environments is right;
- Whether the real production Authorization Server accepts the client;
- JWT signature/issuer/audience verification;
- Whether the real production Reports API enforces `reports.read`;
- End-user authorization;
- Token rotation/DPoP/mTLS.

### 9.3. Why Not Assert Full Basic Credentials in Logs?

In tests, the secret is `test-only-secret`, yet good practice is to verify only the client authentication method and, when needed, decode/compare values **in test memory** without printing raw Authorization headers into test failure reports.

If you need to assert the exact client ID, decode the Basic header carefully inside the test and assert without logging the verbatim credential. In production, never write HTTP Authorization headers to telemetry.

### 9.4. Local HTTP Only, Still an Integration Test

The test traverses multiple real components:
- `OAuth2AuthorizedClientManager`;
- `OAuth2AuthorizedClientProvider`;
- Token response client/HTTP transport;
- Authorized client storage;
- RestClient interceptor;
- HTTP client;
- Local token server and local downstream.

It does not boot the full Spring application context, so it **does not prove `application.yml` bound properly or production `@Bean` wiring is right**. That belongs to the next integration test tier.

---

## 10. Adding Tests: Token Caching and Reuse

Within the same authorized-client service, `registrationId`, and `principalName`, an unexpired access token is typically reused.

```java
@Test
void reusesUnexpiredMachineToken() throws InterruptedException {
    grantReadOnlyToken();

    downstreamApi.enqueue(new MockResponse()
        .setResponseCode(200).setBody("first"));
    downstreamApi.enqueue(new MockResponse()
        .setResponseCode(200).setBody("second"));

    assertThat(callReports()).isEqualTo("first");
    assertThat(callReports()).isEqualTo("second");

    // Two API calls yet the token endpoint received only one request.
    assertThat(authorizationServer.getRequestCount()).isEqualTo(1);
    assertThat(downstreamApi.getRequestCount()).isEqualTo(2);
}
```

Here the token has `expires_in=3600`, well past any clock-skew renewal window.

### 10.1. Warning When Reading getRequestCount()

`getRequestCount()` counts requests **received by MockWebServer**, not authentication events or authorized clients across an entire cluster.

When running parallel tests or sharing a server, isolate server fixtures so assertions aren't skewed by requests from other tests.

### 10.2. Cache Key and Principal

If you change:

```java
.attributes(principal("reports-batch"))
```

to:

```java
.attributes(principal("random-" + UUID.randomUUID()))
```

each request uses a new cache key, so the manager keeps requesting new tokens. This is why you should use a **stable service principal** instead of a random string.

### 10.3. Expiration and Clock Skew

Spring Security may treat a near-expiry token as needing renewal **before the exact `expiresAt` timestamp** per the provider's clock skew. When designing expiry tests:
- Never use `Thread.sleep(3600_000)`;
- Consider a mock clock/version-appropriate provider setting;
- Test near-expiry or expired tokens using controllable time;
- Assert a new token request is sent and the new token is used;
- Do not assume every token endpoint issues a refresh token for client credentials.

---

## 11. Downstream 403: How Must Missing Scopes Be Handled?

Suppose the token only holds `reports.read`, while `POST /reports/export` demands `reports.export`.

Downstream may respond:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.export"
Content-Type: application/json

{"error":"forbidden"}
```

The client should:
- Recognize this as an **authorization failure** at the Resource Server;
- Not retry indefinitely with the same token;
- Not attempt to "add scopes" onto an already-issued access token;
- Not fall back to another client registration with broader permissions without an explicit policy;
- Report appropriate business errors/telemetry and request AS permission updates when valid.

### 11.1. Contract Test for 403

```java
import org.springframework.web.client.HttpClientErrorException;

@Test
void propagatesInsufficientScopeFromDownstream() {
    grantReadOnlyToken();

    downstreamApi.enqueue(new MockResponse()
        .setResponseCode(403)
        .setHeader("WWW-Authenticate",
            "Bearer error=\"insufficient_scope\", scope=\"reports.export\"")
        .setHeader("Content-Type", "application/json")
        .setBody("{\"error\":\"forbidden\"}"));

    org.assertj.core.api.Assertions.assertThatThrownBy(
        () -> callReports())
        .isInstanceOf(HttpClientErrorException.Forbidden.class);

    assertThat(authorizationServer.getRequestCount()).isEqualTo(1);
    assertThat(downstreamApi.getRequestCount()).isEqualTo(1);
}
```

**Limitation:** MockWebServer does not decode tokens to evaluate scopes itself. The test above verifies **the client receives and propagates 403**, not that the Resource Server code implements scope enforcement properly.

### 11.2. Do Not Mix 403 with invalid_token

| HTTP Result | Common Meaning | Handling |
| --- | --- | --- |
| 200 OK | Resource Server accepted | Process response |
| **401 invalid_token** | Invalid/expired/revoked token or RS cannot verify | Check token validity; may remove/re-authorize per policy |
| **403 insufficient_scope** | Token authenticated yet lacks scope/permission | Do not retry refreshing the same scopes as a permissions workaround |
| 403 from business ACL | User/service lacks tenant/resource permission despite scope | Check domain authorization |
| 429 Too Many Requests | Rate limit | Backoff/quota; do not assume wrong scope |
| 503 Service Unavailable | RS outage | Bounded retry/backoff; do not delete token arbitrarily |

An RS can customize its status/error contract. With standard OAuth2 Bearer tokens, 401/403 and `WWW-Authenticate` help distinguish failures, yet tests must follow the actual contract.

---

## 12. Downstream 401: Invalid Tokens Differ from Missing Scopes

Sample response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Possible causes:
- Access token expired;
- Token revoked;
- Audience belongs to a different Resource Server;
- Wrong issuer/algorithm/signature;
- AS/RS keys out of sync;
- Malformed token;
- Resource Server introspection failed.

### 12.1. Do Not Treat Every 401 as an Expired Token

A token whose `exp` is still valid can still get 401 due to wrong `aud` or `iss`. Merely requesting another token with the same audience/scopes will keep failing.

### 12.2. Authorized Client Failure Handler

Spring Security's RestClient interceptor supports handling authorization failures to remove invalid authorized clients when appropriate:

```java
OAuth2ClientHttpRequestInterceptor oauth2 =
    new OAuth2ClientHttpRequestInterceptor(manager);

oauth2.setPrincipalResolver(
    new RequestAttributePrincipalResolver());

oauth2.setAuthorizationFailureHandler(
    OAuth2ClientHttpRequestInterceptor
        .authorizationFailureHandler(authorizedClientService));
```

Check your version and failure-handler semantics: it is not a "retry every HTTP error" interceptor. Removing an invalid authorized client and retrying a request **are two separate decisions**.

### 12.3. Testing 401 with Bounded Recovery

You can design a test:
1. AS issues `AT-OLD`;
2. RS returns 401 `invalid_token`;
3. Failure handler removes the saved client for registration/principal when policy allows;
4. A **new** request obtains `AT-NEW`;
5. RS receives `Bearer AT-NEW`.

However, **never automatically replay a non-idempotent POST** without ensuring the operation is safe. A 401 does not grant license to infinitely resend write requests.

---

## 13. Token Endpoint Failures Differ from Downstream Failures

The Authorization Server may return:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_client",
  "error_description": "Client authentication failed"
}
```

or:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_scope"}
```

Or HTTP 503 during an AS outage.

### 13.1. Error Classification

| OAuth2/HTTP Error | Layer | Common Cause | Should Retry? |
| --- | --- | --- | --- |
| `invalid_client` | AS token endpoint | Wrong secret/auth method, client disabled | Do not keep retrying; fix config |
| `unauthorized_client` | AS token endpoint | Client not permitted to use grant | Needs grant registration/AS policy |
| `invalid_scope` | AS token endpoint | Requested disallowed scope | Fix scope/permissions |
| `unsupported_grant_type` | AS token endpoint | AS does not support `client_credentials` | Fix integration |
| `invalid_request` | AS token endpoint | Bad form/parameters | Fix request |
| 429 | AS token endpoint | Rate limit | Backoff/quota |
| 502/503/timeout | AS/network | Outage | Bounded retry, appropriate circuit breaker |
| 401 `invalid_token` | RS | Token validation failure | Check audience/issuer/expiry |
| 403 `insufficient_scope` | RS | Valid token yet lacks permissions | Fix policy/consent/registration; never auto-escalate |

### 13.2. Negative Token Test Example

```java
@Test
void failsWhenClientCredentialsAreRejected() {
    authorizationServer.enqueue(new MockResponse()
        .setResponseCode(400)
        .setHeader("Content-Type", "application/json")
        .setBody("{\"error\":\"invalid_client\"}"));

    org.assertj.core.api.Assertions.assertThatThrownBy(
        () -> callReports())
        .isInstanceOf(
            org.springframework.security.oauth2.core.OAuth2AuthorizationException.class);

    assertThat(authorizationServer.getRequestCount()).isEqualTo(1);
    assertThat(downstreamApi.getRequestCount()).isZero();
}
```

Test goal: if **a token cannot be obtained**, the client **must never call downstream with an empty/dummy Bearer token**. Specific exception types may be wrapped across RestClient/Spring Security layers; when porting to another service architecture, assert the error contract rather than relying on stack traces.

### 13.3. Never Log Raw error_description

`error_description` comes from an HTTP response and may contain untrusted data, request URLs, credential hints, or PII. Show a generic message to users/operators and log a normalized error code—never log the entire token response.

---

## 14. Testing Scope Reduction by the AS

This is one of the most important tests for this topic.

Registration:

```java
.scope("reports.read", "reports.export")
```

AS responds:

```json
{
  "access_token": "AT-LIMITED",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "reports.read"
}
```

**Expected outcomes:**
- Client does not treat `reports.export` as granted;
- `OAuth2AccessToken.getScopes()` from the explicit fixture response reflects `reports.read`;
- A downstream endpoint requiring `reports.export` denies requests carrying the under-scoped token;
- Client does not retry requesting tokens using an unapproved broader client registration.

### 14.1. Two Approaches to Testing Scopes

**Client-side contract:** assert requested scopes in the form + granted scopes in token metadata.

**Resource-server integration:** run the downstream security filter/JWT converter/introspection and verify real 200/403 responses based on token scopes.

Having only the first does not prove downstream authorization; having only the second does not prove the client sent the right token request.

### 14.2. Never "Add" Scopes to a Token

Wrong:

```java
// Anti-pattern: turning requested scope into downstream authority.
String scope = "reports.read reports.export";
// Then assuming the bearer token holds those permissions.
```

Token permissions are **granted by the AS** and **enforced by the RS**, never fabricated by editing a Map or String on the client.

---

## 15. Resource Server Test: Verifying Scope Policy

A Reporting API using Spring Security Resource Server can define a policy:

```java
package example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ReportsResourceSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/reports/export")
                    .hasAuthority("SCOPE_reports.export")
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Here:
- `reports.read` and `reports.export` map to `SCOPE_reports.read` and `SCOPE_reports.export` when default JWT mapping recognizes scopes;
- The export endpoint demands a higher authority;
- Production runs a real JWT decoder to verify signature, issuer, expiry, and audience per configuration;
- Tests must not bypass `aud` validation if proving real resource boundaries.

### 15.1. MockMvc Security Policy Test

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Mock token turned into Authentication holding reports.read.
mvc.perform(get("/api/reports")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());

// Mock token with read only cannot export.
mvc.perform(get("/api/reports/export")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isForbidden());

// Mock token with export.
mvc.perform(get("/api/reports/export")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.export"))))
    .andExpect(status().isOk());
```

This is a **policy test**: it creates a mock `JwtAuthenticationToken`/authorities inside MockMvc. No genuinely signed JWT is verified.

To run, the test requires:
- `spring-security-test`;
- MockMvc with Spring Security filter integration;
- ResourceServer `SecurityFilterChain` + matching controller endpoints;
- Any `JwtDecoder` bean/config required by the test context (if demanded by security configuration).

### 15.2. Want to Test a Real JWT Rejected for Missing Scope?

Write an integration test going through:
1. A JWT signed with a test private key;
2. Resource Server using a trusted test JWKS/decoder;
3. Validation of `iss`, `aud`, `exp`, and signature;
4. Converter extracting `scope` or `scp`;
5. `SecurityFilterChain` enforcing `hasAuthority("SCOPE_reports.export")`;
6. Asserting HTTP 200/403 and 401 for invalid tokens.

At this stage, distinguish a **valid token missing scope** (403) from an **unverifiable token** (401).

### 15.3. What About Opaque Tokens?

For opaque access tokens, the Resource Server may use an introspection endpoint. Tests must verify:
- Introspection response `active` true/false;
- Granted scopes;
- Audience/resource policy;
- TTL/caching if any;
- 401 when inactive;
- 403 when active yet lacking permissions.

You cannot infer an opaque token's scopes from its random character string alone.

---

## 16. Combining Two Test Layers for High Confidence

A practical suite separates:

```text
Layer A: OAuth2 Client integration
  RestClient + AuthorizedClientManager
     -> Mock AS token endpoint
     -> Mock downstream contract
  Assert token request, scope, Bearer header, errors, cache

Layer B: Downstream Resource Server integration
  SecurityFilterChain + JwtDecoder/Introspector
     -> Synthetic signed JWT/opaque introspection
  Assert 200/401/403, issuer, audience, scope mapping

Layer C: Environment contract/E2E (controlled)
  Test AS + Test Resource Server (never using production secrets)
  Assert full machine-to-machine flow, networking, config
```

### 16.1. Why Is Mocking Everything in One Test Not Enough?

If you mock the manager to return an `OAuth2AuthorizedClient` with `reports.read` and mock the downstream client to return 200, you skip:
- Token endpoint form encoding;
- Client auth method;
- Access token parsing;
- Scope reduction;
- RestClient interceptor;
- Bearer header attachment;
- Real HTTP status handling;
- Caching/expiry.

Yet running every test against a live staging AS/RS makes suites slow and non-deterministic. **Combining test layers** gives strong coverage without depending on a live OP for every commit.

---

## 17. Testing Token Expiry and Reauthorization

With `client_credentials`, when an access token is no longer valid per expiry/clock skew, the manager can **request a new token using the same grant**.

```text
T0: OAuth2AuthorizedClient
    access_token=A1
    expiresAt=T0+3600s

T0+100s: downstream call
    -> reuse A1

T0+3590s (near expiration)
    -> manager may request new token A2

Downstream request
    -> Bearer A2
```

### 17.1. Tests Should Control Time

- Never wait a real hour;
- Use a clock/test provider configurable in your current version;
- Or return a very short expiry and observe controlled reauthorization;
- Avoid flaky tests tied to schedulers/system clocks;
- Remember providers/clients may apply **clock skew**, treating near-expiry tokens as already needing renewal.

### 17.2. Refresh Token Grant Is Not Automatically Called

RFC 6749 recommends **not issuing refresh tokens** with `client_credentials`. Do not write tests expecting `grant_type=refresh_token` simply because the access token expired. The standard flow is **`grant_type=client_credentials` again**.

### 17.3. Reauthorization and Cache Storage

If an application runs multiple replicas, `InMemoryOAuth2AuthorizedClientService` is per-instance. Replicas may request separate tokens despite sharing the same service principal.

When using persistent storage/shared caches:
- Key properly by registration + principal;
- Account for concurrent renewal;
- Guard against token leakage;
- Do not assume Spring Security provides distributed locking automatically;
- Never write raw tokens to logs.

---

## 18. Testing Concurrent Requests When No Token Is Cached Yet

Two HTTP requests arrive simultaneously:

```text
Request A -> authorize("reports-machine","reports-batch")
Request B -> authorize("reports-machine","reports-batch")
              |
              v
   Same cache misses token
              |
              +-- token request A
              +-- token request B (possible)
```

**Do not assume** only one token request will be sent on a concurrent cache miss if the manager/service lacks single-flight or locking. Two valid requests may occur.

Concurrency tests should verify:
- The AS may issue two tokens;
- Requests never use a token from a different registration;
- Authorized client store does not corrupt;
- No data races when writing to cache;
- Token endpoint quota/rate limits are managed;
- If business logic requires strictly one token request, implement and test a dedicated single-flight/lock strategy.

### 18.1. Distinguish Safety from Efficiency

- **Safety:** every downstream request uses only a valid token from the right AS/client registration;
- **Efficiency:** minimizing redundant token requests.

A concurrency test proving tokens/contexts never mix does not prove optimal request count; conversely, `requests == 1` does not prove the token has the right audience.

### 18.2. Never Store Tokens in a Static Global Field

```java
// ANTI-PATTERN
static String currentAccessToken;
```

If the same app has `reports-machine` and `payments-machine`, a static field causes cross-audience token mix-ups. Use the manager/service keyed by registration and principal, never a global variable.

---

## 19. Multiple Downstream APIs and Least Privilege

An application may call both a Reports API and a Billing API.

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-machine:
            provider: company-as
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: [reports.read]

          billing-machine:
            provider: company-as
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: [billing.write]

        provider:
          company-as:
            token-uri: https://auth.example.test/oauth2/token
```

**Separate clients/registrations whenever policy or trust boundaries require.**

Never send:
- Billing tokens to Reports API;
- Reports tokens to Billing API;
- A `reports.read`-scoped token to a Billing write endpoint;
- Billing's client secret to an untrusted token endpoint.

### 19.1. Testing Token Audience Isolation

Appropriate tests:
- Mock AS issues token R for Reports;
- Mock AS issues token B for Billing;
- Reports RestClient always sends Bearer R;
- Billing RestClient always sends Bearer B;
- Zero requests send token R to the Billing host;
- Resource Server rejects wrong-audience tokens when testing real validation.

### 19.2. Registration Does Not Equal Endpoint

`ClientRegistration` describes the OAuth2 client. `RestClient.baseUrl` describes the downstream destination. They must be **bound through trusted configuration**.

A test should verify `clientRegistrationId("billing-machine")` cannot be injected from raw user queries into an arbitrary downstream URL to cause credential exfiltration.

### 19.3. Protecting DNS/Redirects

If an outbound HTTP client follows a redirect from Reports API to another hostname, ensure it never forwards the Bearer token outside permitted destinations. This is HTTP client hardening/SSRF protection that scopes alone do not solve.

---

## 20. Configuring a Spring Boot Integration Test with a Dynamic Token URI

A `@SpringBootTest` testing **Spring Boot property binding and `@Bean` wiring** beyond the isolated HTTP client layer can point to a local MockWebServer endpoint using `@DynamicPropertySource`.

Conceptual example:

```java
@SpringBootTest
class ReportsClientApplicationIntegrationTest {

    static final MockWebServer as = new MockWebServer();

    static {
        try {
            as.start();
        } catch (IOException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    @DynamicPropertySource
    static void oauthProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.security.oauth2.client.provider.reports-as.token-uri",
            () -> as.url("/oauth2/token").toString());
    }

    @AfterAll
    static void stopServer() throws IOException {
        as.shutdown();
    }

    // @Autowired OAuth2AuthorizedClientManager manager;
    // @Test ... assert real manager.authorize(...) against mock endpoint
}
```

This is **only a `@SpringBootTest` skeleton**. You still need:
- Imports and dependencies;
- Registration `reports-machine` in test properties (`client_id`, secret, grant, scope);
- Mock AS responses for each test;
- Do not add `issuer-uri` if it triggers unrelated OIDC discovery at startup for client credentials;
- If running multiple contexts/tests in parallel, isolate mock servers and lifecycles to avoid races;
- Downstream base URL via test property as well;
- Assertions as in Section 9.

### 20.1. Why Dynamic Ports?

`MockWebServer` uses a random port to avoid conflicts with services on CI machines. `@DynamicPropertySource` lets Spring build the registration with the exact URL before context initialization.

### 20.2. Never Put Production Localhost Overrides in YAML

In production:
- Token URI must be trusted HTTPS;
- Test URIs must point only to local servers/testcontainers;
- Test client secrets are loaded from test-only config;
- Never let property overrides leak into production profiles.

### 20.3. Never Call Production AS in CI

Tests should be deterministic and offline/reproducible whenever possible. Any test requiring a staging AS needs:
- Controlled, dedicated secrets;
- Network policies;
- Rate limits;
- Cleanup;
- Strict rule against touching real data;
- Skip/isolated pipeline handling if staging is unavailable.

---

## 21. Reactive WebFlux: Testing Client Credentials with WebClient

On WebFlux, use `ReactiveOAuth2AuthorizedClientManager` instead of the Servlet manager.

Service-level configuration:

```java
package example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
class ReactiveMachineConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager machineManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService service) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, service);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

**When there is no `ServerWebExchange` (scheduled/background jobs), use the service-level reactive manager.** `DefaultReactiveOAuth2AuthorizedClientManager` is meant for WebFlux web request contexts.

### 21.1. WebClient OAuth2 Filter

```java
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient reportsWebClient(
        ReactiveOAuth2AuthorizedClientManager manager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .baseUrl("https://reports-api.example.test")
        .filter(oauth2)
        .build();
}
```

A call:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> result = reportsWebClient.get()
    .uri("/api/reports")
    .attributes(clientRegistrationId("reports-machine"))
    .retrieve()
    .bodyToMono(String.class);
```

**Note on principal:** For service-level client credentials, a service principal is needed in the authorization request/context. How it is supplied depends on integration/version; an unambiguous approach is **calling the manager explicitly** with `OAuth2AuthorizeRequest.principal("reports-batch")` and passing the resulting authorized client to WebClient.

### 21.2. Calling the Reactive Manager Explicitly

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import reactor.core.publisher.Mono;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-machine")
        .principal("reports-batch")
        .build();

Mono<OAuth2AuthorizedClient> authorized =
    reactiveManager.authorize(request);
```

In tests:

```java
StepVerifier.create(authorized)
    .assertNext(client -> {
        assertThat(client.getClientRegistration().getRegistrationId())
            .isEqualTo("reports-machine");
        assertThat(client.getAccessToken().getScopes())
            .contains("reports.read");
    })
    .verifyComplete();
```

**Never call `block()` in reactive request-processing code.** Use `StepVerifier` at the test boundary and compose `Mono` in services.

### 21.3. Passing the Authorized Client into WebClient

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

Mono<String> response = reactiveManager.authorize(request)
    .flatMap(client ->
        reportsWebClient.get()
            .uri("/api/reports")
            .attributes(oauth2AuthorizedClient(client))
            .retrieve()
            .bodyToMono(String.class));
```

This ensures the request uses **the exact authorized client** looked up/issued by the manager under a stable service principal. Test HTTP against mock token endpoint/downstream similarly to Section 9, using `StepVerifier`/WebClient and reactive dependencies.

### 21.4. Do Not Confuse WebTestClient mockOidcLogin

`mockOidcLogin()` creates an OIDC user for **inbound WebFlux HTTP security tests**. It **does not mint a real `client_credentials` token** or verify downstream scopes.

For M2M integration tests, mock the token endpoint and test the real outbound WebClient/manager rather than calling `mockOidcLogin()`.

---

## 22. Servlet WebClient Is a Distinct Case

A Servlet MVC application can also use `WebClient` for outbound HTTP. In that case, do not use WebFlux's `ServerOAuth2AuthorizedClientExchangeFilterFunction` when running inside a Servlet context per Spring Security Servlet APIs.

Use:

```java
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;

ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

WebClient client = WebClient.builder()
    .apply(oauth2.oauth2Configuration())
    .build();
```

If using client credentials for scheduled/background jobs, choose an explicit manager/service principal rather than depending on the current `HttpServletRequest`.

### 22.1. Warning About Default Tokens on All Requests

Spring Security offers default authorized client/default registration ID options for WebClient. Used carelessly, they can attach access tokens to every outbound call, even to URLs that should never receive tokens.

**Prefer specifying registration/authorized client explicitly on protected requests** and restricting base URLs. This is also a valuable assertion in integration tests.

---

## 23. Scopes per RFC and Request Format

A standard client credentials request looks like:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=reports.read+reports.export
```

The `+` in form encoding represents a space between scopes. Do not compare raw bodies as a single fixed string if scope order can vary.

### 23.1. Parse the Form Instead of Comparing Order

When strict assertions are needed, parse `application/x-www-form-urlencoded` into a Map with a test helper and compare the **set** of scopes rather than byte-for-byte text.

```java
String encodedForm = tokenRequest.getBody().readUtf8();

Map<String, String> form = java.util.Arrays.stream(
        encodedForm.split("&"))
    .map(part -> part.split("=", 2))
    .collect(java.util.stream.Collectors.toMap(
        part -> java.net.URLDecoder.decode(
            part[0], java.nio.charset.StandardCharsets.UTF_8),
        part -> java.net.URLDecoder.decode(
            part.length > 1 ? part[1] : "",
            java.nio.charset.StandardCharsets.UTF_8)));

assertThat(form.get("grant_type")).isEqualTo("client_credentials");

assertThat(java.util.Set.of(form.get("scope").split(" ")))
    .containsExactlyInAnyOrder("reports.read", "reports.export");
```

This helper snippet assumes a valid form where each key appears once; production-grade parsers must handle URL-encoded values, duplicate fields, and error cases thoroughly.

### 23.2. Client Secret Basic Encoding

Basic client authentication has specific OAuth2 encoding rules. Never hand-build `client_id:client_secret` and Base64-encode with non-compliant logic when Spring Security already handles it.

Tests can verify the `Authorization` header starts with `Basic` and, when strict verification is desired, decode it against the test-only secret in memory. Never output raw Basic credentials in logs.

### 23.3. Requested Scopes May Be Restricted by the AS

An Authorization Server can grant narrower scopes, or return `invalid_scope` if disallowed permissions are requested. Tests should cover both, especially when configuration upgrades add new scopes.

---

## 24. Security Boundary: Tokens for the Right Audience

A Reports API requires:

```json
{
  "iss": "https://auth.example.test",
  "aud": ["reports-api"],
  "scope": "reports.read"
}
```

A Billing token:

```json
{
  "iss": "https://auth.example.test",
  "aud": ["billing-api"],
  "scope": "reports.read"
}
```

Despite sharing `scope=reports.read`, the Billing token **must not be permitted** to access the Reports API if audience policy separates the two resource servers.

### 24.1. Testing Audience Mismatch

- Build a test JWT with `aud=billing-api`;
- Send that JWT to the Reports Resource Server with a real JWT decoder and audience validator;
- Assert 401 or appropriate contract rejection;
- Then build a JWT with `aud=reports-api`, right scope, valid signature → 200;
- Token with right audience yet missing scope → 403.

### 24.2. Never Infer Audience from Scope

A client with granted scopes yet lacking the matching resource/audience must still be rejected by the RS. On some ASes, requesting a token for a specific API requires the `resource` parameter (RFC 8707) or a provider-specific audience/resource setting. Configuring scopes alone **does not guarantee the token carries the right audience**.

### 24.3. Token Exchange Is a Different Flow

If an app holds a user token and wants a token scoped down for a downstream audience, that may call for **token exchange (RFC 8693)** or delegated authorization per AS contract—not calling `client_credentials` and "attaching the user" manually.

---

## 25. Managing Secrets in Tests and Production

### 25.1. In Integration Tests

- Use synthetic client IDs/secrets like `test-reports-client` / `test-only-secret`;
- Point Token URI to localhost MockWebServer;
- Use fixture access tokens like `test-access-token`;
- Never commit staging/production credentials into source;
- Never print raw Authorization headers in test failure logs;
- Reset mock servers and the authorized client store between tests;
- Never run these test fixtures on a public network.

### 25.2. In Production

- Store secrets in an environment secret manager/secure vault;
- Require TLS for token endpoints and APIs;
- Match the client authentication method to AS policy;
- Rotate secrets/certificates;
- Never maintain an unprotected global singleton Map holding plaintext tokens;
- Keep scopes and audiences minimal;
- Restrict outbound network permissions;
- Alert on abnormal token issuance;
- Never substitute M2M tokens for end-user Authentication.

### 25.3. No ID Token in Standard Client Credentials

Client Credentials belongs to **OAuth2**, and does not automatically produce an `OidcUser` or ID Token. Therefore, in tests:
- Do not expect `openid`, `nonce`, or `id_token` unless the AS has a custom contract;
- Do not test `@AuthenticationPrincipal OidcUser` as proof of machine identity;
- Test access tokens, client registrations, and resource authorization.

---

## 26. Observability for Client Credentials

A safe telemetry event:

```json
{
  "event": "m2m_oauth2_token_request",
  "registration_id": "reports-machine",
  "grant_type": "client_credentials",
  "result": "success",
  "requested_scope_category": "reporting-read-export",
  "latency_bucket_ms": "100-250",
  "trace_id": "test-safe-trace"
}
```

This is an application-defined schema, not Spring Security's default log format.

### 26.1. What to Log

- Allowlisted `registrationId`;
- Token request success/failure;
- Normalized OAuth2 error code;
- HTTP status category and latency;
- Fixed requested scope category containing no raw untrusted input;
- Downstream name/route category;
- 401/403/429/503 rates per API;
- Internal trace ID containing no credentials.

### 26.2. What Never to Log

- `client_secret`;
- Full Basic authorization header;
- Access/refresh tokens;
- Full HTTP token responses;
- Raw JWT claims if they contain PII;
- Raw URI queries containing bearer tokens;
- Unsanitized `error_description`;
- Dumped `OAuth2AuthorizedClient` objects.

### 26.3. Metrics Should Separate AS and RS

```text
oauth2_client_token_requests_total{registration="reports-machine",result="success"}
oauth2_client_token_failures_total{registration="reports-machine",error="invalid_scope"}
downstream_requests_total{service="reports",status="200"}
downstream_requests_total{service="reports",status="403"}
downstream_requests_total{service="reports",status="503"}
```

Collapsing everything into one "OAuth error" metric makes it hard to tell a wrong client secret from an under-scoped token or a downstream outage.

---

## 27. Comprehensive Troubleshooting

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| No token request sent | Manager lacks `client_credentials` or `authorize` not called | Authorized client provider, registration ID |
| `authorize()` returns null | Registration/grant/provider mismatch | Inspect manager and policy |
| Token endpoint 401/400 `invalid_client` | Wrong client secret/auth method | Registration, AS config, Basic/`private_key_jwt`/mTLS |
| Token endpoint `invalid_scope` | Scopes disallowed by AS | Client permissions, requested scopes |
| `unsupported_grant_type` | AS/client does not support `client_credentials` | Grant registration and AS |
| Mock token response fails to parse | Missing `token_type`, `expires_in`, or invalid JSON | Token endpoint contract, `Content-Type` |
| Test sees only one scope | AS returned reduced scope | Requested vs granted differ |
| API call sends wrong header | RestClient interceptor missing or wrong registration | HTTP client wiring/attributes |
| RestClient has no principal | Default resolver relies on `SecurityContextHolder` | `RequestAttributePrincipalResolver` and service principal |
| Every request asks for a token | Changing principal name, cache disabled, near-expiry token | Cache key, storage, clock skew |
| Two concurrent calls request two tokens | Cache miss race | Single-flight/locking if needed |
| Downstream 401 despite unexpired token | Wrong audience/issuer/signature/revocation | Resource Server validation, AS contract |
| 403 `insufficient_scope` | Missing granted scope | Scope/permissions, never blindly retry |
| 403 business ACL | Tenant/resource access policy | Domain authorization |
| 429 token endpoint | Rate limit, too many token requests | Stable principal, caching/backoff |
| 503 AS | Authorization Server outage | Timeout/circuit breaker; never call API without token |
| 503 RS | Downstream outage | Do not treat AS token as invalid |
| Reports token sent to Billing | Wrong registration/URI mapping | Dedicated clients/base URLs, SSRF controls |
| JWT scope test passes yet signature invalid | Test used `mockJwt` bypassing decoder | Signed JWT integration test |
| MockWebServer returns 403 yet no scope check | Stub just scripted status | Real Resource Server security test |
| Unexpected refresh token grant appears | Wrong grant/configuration in use | Client Credentials normally reauthorizes |
| Scheduled job works in controller yet fails in background | Used servlet request manager | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| Reactive job lacks `ServerWebExchange` | Used reactive request-bound manager | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| WebClient attaches token to all hosts | Broad default client registration/authorized client | Explicit per-request client + allowed destinations |
| Client secret leaked in CI logs | HTTP wire logging/token body dump | Redact Authorization & token responses |
| Boot test fails attempting OIDC discovery | Unnecessary `issuer-uri`/network dependency | Explicit `token-uri` for M2M |
| API reports missing authority despite JWT scope | Converter claim/prefix varies by provider | `JwtGrantedAuthoritiesConverter`, `scope`/`scp` |
| Token issued yet wrong audience | AS resource/audience config wrong | RFC 8707/resource-specific issuance |

---

## 28. Practice Exercises

### Exercise 1 — Requesting the Right Grant

The client needs a Reports token.

**Prompt:** Which `grant_type` must the token endpoint receive?

> **`client_credentials`**, HTTP POST form, with client authentication per AS-permitted method. No authorization code or PKCE verifier.

### Exercise 2 — Requested vs Granted Scopes

Registration requests `reports.read reports.export`; token response contains only `reports.read`.

**Prompt:** Can the client call the export endpoint and expect 200?

> No. The token lacks `reports.export`; the Resource Server must protect the endpoint using actually granted permissions, typically returning 403 when a valid token lacks the scope.

### Exercise 3 — Omitted scope Field

The token response has no `scope` field.

**Prompt:** Can you conclude the token has all permissions?

> No. Per RFC, `scope` may be omitted when identical to the requested scope; follow the AS contract and never infer "full permissions."

### Exercise 4 — client_secret_basic

**Prompt:** Where is the Basic credential sent?

> To the **Authorization Server token endpoint**, never to the downstream API. Downstream receives the **Bearer access token**.

### Exercise 5 — Static Service Principal

A job runs 100 times; each time it uses `principal(UUID.randomUUID().toString())`.

**Issue:** the authorized client cache stores 100 separate principals, driving up token requests. Use a single stable principal matching the service identity.

### Exercise 6 — Manager Running Outside HTTP Requests

A scheduled job uses `DefaultOAuth2AuthorizedClientManager` and fails on missing request context.

**Fix:** `AuthorizedClientServiceOAuth2AuthorizedClientManager` backed by `OAuth2AuthorizedClientService`.

### Exercise 7 — Calling the API Without a Token

The AS returns `invalid_client`; fallback code sends `Authorization: Bearer null` to the API.

**Assessment:** Wrong. If the token request fails, never execute the authorized downstream call.

### Exercise 8 — Unexpired Token Yet Downstream 401

**Prompt:** Is the token definitely expired?

> No. It could be wrong audience, wrong issuer, revoked token, or a signature issue. Check Resource Server validation and response challenges.

### Exercise 9 — 403 insufficient_scope

The client immediately retries using an admin client ID.

**Assessment:** Unapproved privilege escalation. Fix registration/scope/AS policy if valid, rather than switching to stronger credentials.

### Exercise 10 — Token Response Missing refresh_token

**Prompt:** Is the server missing a feature?

> No. Client Credentials normally does not issue refresh tokens. When the token expires, the client requests a new token using `client_credentials`.

### Exercise 11 — Resource Server JWT Mock Tests

A test uses `jwt().authorities(SCOPE_reports.read)` and receives 200.

**Prompt:** Has the JWT signature been tested?

> Not yet. Mock JWT bypasses decoding/signature verification; add a signed JWT integration test or `JwtDecoder` test.

### Exercise 12 — Valid Scope Yet Wrong aud

Token has `reports.read` yet `aud=billing-api`.

**Expected outcome:** Reports API rejects it due to invalid audience. Scopes do not replace audience validation.

### Exercise 13 — Mock Downstream Returns 403

A MockWebServer test script returns 403 for requests carrying a token.

**Prompt:** Does this prove the production RS authorization code works?

> Not yet. It only proves the client handles the HTTP contract. Maintain a dedicated Resource Server security integration test.

### Exercise 14 — Concurrent Cache Miss

Two concurrent requests both request a token once.

**Prompt:** Can you conclude the manager is broken?

> Not necessarily. Without single-flight/locking, concurrent cache misses can emit two requests. Evaluate safety, quota, and efficiency requirements separately.

### Exercise 15 — WebFlux Background Job

A reactive service runs outside a `ServerWebExchange`.

**Solution:** `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` and `ReactiveOAuth2AuthorizedClientService`; test with `StepVerifier`.

### Exercise 16 — Access Token Leaked in Logs

RestClient debug logging prints the full `Authorization: Bearer ...`.

**Solution:** Redact at the HTTP client/interceptor/proxy/APM layers; never log token values. Use test tokens only.

### Exercise 17 — Two APIs Sharing One Registration

Reports and Billing have different scope/audience requirements yet share one token.

**Risk:** Token used on the wrong resource. Design separate registrations/AS audiences/resources per policy and test that tokens never cross over.

### Exercise 18 — Client Wants to Impersonate a User

Business wants to "log in on behalf of Alice" using a `client_credentials` token.

**Assessment:** This grant authenticates the client/service, not Alice. Use an appropriate delegated authorization/token exchange flow with explicit policy.

### Exercise 19 — Token Endpoint Accepts Only private_key_jwt

The test client uses Basic and receives `invalid_client`.

**Prompt:** Should you change the test server to accept Basic?

> No, if the production AS requires `private_key_jwt`. Update client configuration and test methods to match the real contract.

### Exercise 20 — M2M Token Accepted Outside Its Audience

The Reports API trusts tokens solely on signature/issuer without checking `aud`.

**Risk:** Token substitution across resource servers. Add an audience validator and negative integration tests.

---

## 29. Production-Readiness Test Matrix

| ID | Test Layer | Condition | Expected |
| --- | --- | --- | --- |
| M2M-01 | Client HTTP | Token 200, full scope | Valid Bearer header |
| M2M-02 | Client HTTP | Token 200, reduced scope | Granted scopes hold subset only |
| M2M-03 | Client HTTP | Token 400 `invalid_client` | Zero downstream calls |
| M2M-04 | Client HTTP | Token 400 `invalid_scope` | Zero downstream calls |
| M2M-05 | Client HTTP | AS timeout/503 | Clear failure category, bounded retry |
| M2M-06 | Client HTTP | Malformed token response | Fail closed |
| M2M-07 | Client HTTP | Same principal, valid token | Reuses token |
| M2M-08 | Client HTTP | Expired/near-expiry token | New client credentials request |
| M2M-09 | Client HTTP | Different registration | Never reuses wrong token |
| M2M-10 | Client HTTP | Two concurrent calls | Never mixes tokens; verify races |
| M2M-11 | Downstream contract | API 200 | Parses response |
| M2M-12 | Downstream contract | API 401 `invalid_token` | Failure handler/authorized client lifecycle |
| M2M-13 | Downstream contract | API 403 `insufficient_scope` | Never self-escalates permissions |
| M2M-14 | Downstream contract | API 429 | Rate-limit handling |
| M2M-15 | Downstream contract | API 503 | RS-specific outage |
| M2M-16 | RS security | Valid JWT + required scope | HTTP 200 |
| M2M-17 | RS security | Valid JWT + missing scope | HTTP 403 |
| M2M-18 | RS security | JWT wrong issuer | HTTP 401 |
| M2M-19 | RS security | JWT wrong audience | HTTP 401 |
| M2M-20 | RS security | JWT expired/invalid signature | HTTP 401 |
| M2M-21 | RS security | Opaque `active=false` | HTTP 401 |
| M2M-22 | Configuration | Boot registration `token-uri` binding | Points to mock AS |
| M2M-23 | Security | User-supplied outbound host | Never sends Bearer token to unknown host |
| M2M-24 | Security | No real tokens in logs | Zero leaked secrets |
| M2M-25 | Reactive | WebClient + reactive manager | Mono completes with right token/header |
| M2M-26 | Lifecycle | After AS recovery | Can obtain new token |
| M2M-27 | Policy | Client token lacks tenant permission | API denied per ACL |
| M2M-28 | Separation | Browser OIDC user vs machine identity | Never impersonates user |

### 29.1. Cases Never to Skip

A suite containing only 200 happy paths without **`invalid_client`**, **reduced scope**, **downstream 403**, and **audience mismatch** will miss high-severity security bugs.

### 29.2. Tests Must Define Clear Boundaries

- **Mock manager** → unit service test;
- **Real manager + mock AS** → client integration;
- **Real HTTP interceptor + mock RS** → outbound contract;
- **Real RS `SecurityFilterChain` + decoder** → downstream authorization;
- **Browser/`mockOidcLogin`** → interactive login testing, **not** M2M grants.

---

## 30. Investigation Procedure When Integration Tests Fail

1. Confirm registration `reports-machine` exists with grant `client_credentials`.
2. Confirm code selects the exact `clientRegistrationId`.
3. If the job has no HTTP request, confirm the manager is **service-level** rather than request-bound.
4. Confirm the service principal is stable and matches the cache key.
5. Confirm the test token URI points to the local mock AS, never production.
6. Confirm the POST token request has proper client authentication, form encoding, and `grant_type`.
7. Confirm requested scopes and granted scopes **are not confused**.
8. Confirm the token response includes `access_token`, `token_type`, expiry, and scope per contract.
9. Verify the RestClient/WebClient interceptor is attached to the exact client instance.
10. Verify outbound requests reach only allowlisted downstream hosts and carry the Bearer header.
11. On HTTP 401, check expiry/issuer/audience/token status/signature.
12. On HTTP 403, check required scope or business ACL.
13. On `invalid_scope` at the token endpoint, fix client/AS policy rather than the RS.
14. If multiple token requests occur, check cache principal, expiry/skew, and concurrent misses.
15. On WebFlux, confirm the `Mono` is actually subscribed and the manager fits WebExchange/background usage.
16. If using Resource Server `mockJwt`, remember signature validation **is not executed**.
17. Ensure logs/test artifacts redact Authorization headers, secrets, and tokens.
18. Fix code/config only after isolating the failing layer; never drop validation just to "pass tests."

---

## 31. Summary by Component Responsibility

```text
                   SPRING OAUTH2 CLIENT
                    (client_credentials)
                             |
                             | ClientRegistration:
                             |   id=reports-machine
                             |   grant=client_credentials
                             |   requested scopes=reports.read reports.export
                             v
              OAuth2AuthorizedClientManager
                             |
                             | POST /token
                             | Client authentication
                             | grant_type=client_credentials
                             | scope=...
                             v
                     AUTHORIZATION SERVER
                             |
                             | Access token, expiry,
                             | granted scope=reports.read
                             v
              OAuth2AuthorizedClientService
                key=(registration, service principal)
                             |
                             v
                    RestClient / WebClient
                             |
                             | Authorization: Bearer <access_token>
                             v
                     DOWNSTREAM API / RS
                             |
                  +----------+------------+
                  |          |            |
               200 OK      401         403
               scope ok    invalid     insufficient
                           token       scope/ACL

Integration tests:
  1. Assert token request + client auth + requested scope
  2. Assert token response + granted scopes + cache
  3. Assert downstream Bearer header and HTTP contract
  4. Assert actual Resource Server scope/issuer/audience policy separately
```

### Key Takeaways

1. **Client Credentials is machine-to-machine OAuth2**, not OIDC end-user login.
2. **`grant_type=client_credentials`** must be sent to the token endpoint with proper client authentication.
3. **Requested scopes, granted scopes, and required downstream scopes are three distinct layers**.
4. **`AuthorizedClientServiceOAuth2AuthorizedClientManager`** suits scheduled/service code outside servlet requests.
5. **RestClient `OAuth2ClientHttpRequestInterceptor`** automates token retrieval and Bearer attachment; tests should use a stable service principal.
6. **Token cache keys normally pair registration and principal**; changing principals triggers extra token requests.
7. **Downstream 401 differs from 403**: invalid tokens differ from insufficient scope; never retry or escalate blindly.
8. **A mock downstream returning 403 does not prove real scope enforcement**; maintain separate Resource Server security tests.
9. **JWT scope/issuer/audience/signature/expiry** all matter; a right scope alone never makes a token valid for every API.
10. **Reactive WebFlux uses `ReactiveOAuth2AuthorizedClientManager` and `WebClient`**, never substituted with Servlet managers.
11. **Client Credentials rarely issues refresh tokens**; when access tokens expire, request a new one via the same grant.
12. **Never leak secrets/tokens, never forward Bearer tokens to untrusted URLs, and never impersonate end-users** with machine credentials.

### Official References

- [Spring Security 6.5 — Servlet OAuth2 Client Core Interfaces](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html)
- [Spring Security 6.5 — Authorized Client Features: RestClient, WebClient, principals](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Reactive OAuth2 Client Core](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [Spring Security 6.5 — Reactive Authorized Client Features](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Resource Server JWT and Scope Authorities](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html)
- [Spring Security API — OAuth2ClientHttpRequestInterceptor](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/client/OAuth2ClientHttpRequestInterceptor.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework, Client Credentials](https://www.rfc-editor.org/rfc/rfc6749#section-4.4)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [MockWebServer — Square OkHttp](https://github.com/square/okhttp/tree/master/mockwebserver)
