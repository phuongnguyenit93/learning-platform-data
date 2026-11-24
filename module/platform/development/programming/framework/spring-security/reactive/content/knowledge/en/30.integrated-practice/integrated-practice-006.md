# Calling External APIs with WebClient and OAuth2 Client Credentials

> **Module:** Spring Security - reactive → Integrated Practice. This lab builds a Spring WebFlux service using **WebClient** to call a partner API protected by OAuth2 **Client Credentials**, while explaining token issuance, attaching Bearer tokens, token reuse, handling expiration/errors, and testing calls to both the token endpoint and the resource API.

## 1. Scenario, Goals, and Boundaries

Suppose service **catalog-sync** needs to call **GET /v1/status** on **partner-api**. Both systems communicate server-to-server. **catalog-sync** is provisioned with **`client_id`/`client_secret`** and scope **`partner.read`** from the Authorization Server; end users are not involved in authorizing individual requests. The service must obtain an access token before calling the API and send the token in the header:

~~~http
GET /v1/status HTTP/1.1
Host: partner-api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Goals:

1. Understand the parties in OAuth2 Client Credentials: **client**, **authorization server** (AS), **resource server** (RS), and **access token**.
2. Configure OAuth2 client registration, token endpoint, scopes, and client authentication in Spring Security.
3. Use **`ReactiveOAuth2AuthorizedClientManager`** for service tasks that do not depend on an incoming user HTTP request.
4. Use WebClient to send tokens only to the intended API, avoiding leaking credentials to other hosts.
5. Explain token caching/renewal, timeouts, retries, 401/403/429/5xx errors, and observability.
6. Run integration tests with a mock token endpoint and mock API to verify **`grant_type=client_credentials`**, the Authorization header, and token reuse.
7. Understand the demo's limits compared with production TLS, secret managers, scope policies, and a real IdP.

This lab uses Java 17, Spring Boot 3.3.x / Spring Security 6.x, and Reactor. The demo **does not** simulate user delegation or OAuth2 Authorization Code. For APIs acting on behalf of individual users, design an appropriate delegation flow instead of using client credentials and asserting user identity manually.

## 2. Client Credentials Flow in a Reactive Application

~~~text
catalog-sync (OAuth2 Client)              Authorization Server
         |                                          |
         |  POST /oauth/token                       |
         |  Authorization: Basic base64(id:secret)  |
         |  Content-Type: application/x-www-form-urlencoded
         |  grant_type=client_credentials           |
         |  scope=partner.read                      |
         |----------------------------------------->|
         |<-----------------------------------------|
         |  200 {"access_token":"...",              |
         |       "token_type":"Bearer",             |
         |       "expires_in":3600}                 |
         |                                          |
         |             Partner Resource Server      |
         |  GET /v1/status                          |
         |  Authorization: Bearer <access_token>    |
         |----------------------------------------->|
         |<-----------------------------------------|
         |  200 {"status":"ready"}                  |
~~~

The **Authorization Server** authenticates the client application, evaluates allowed scopes/audiences, and issues tokens. The **Resource Server** validates tokens per the IdP's contract (JWT signature or opaque token introspection), issuer, audience, lifetime, and scopes before granting access. **`WebClient`** in `catalog-sync` acts as an **OAuth2 Client** making outbound requests; it does not turn `catalog-sync` into a Resource Server validating inbound requests.

Key characteristics:

- The grant sends **`grant_type=client_credentials`**. OAuth2 does not always mandate HTTP Basic; **`client_secret_basic`**, **`client_secret_post`**, `private_key_jwt`, or mTLS depends on the Authorization Server. The demo selects **`client_secret_basic`**.
- A successful response typically returns **`access_token`**, **`token_type=Bearer`**, **`expires_in`**, and optionally **`scope`**. RFC 6749 does not require issuing refresh tokens for the Client Credentials grant; normally, near expiration, the client simply requests a new access token.
- The token represents the **application's** permissions per AS scopes and policy; **`sub`/`client_id`** may represent the client rather than any user calling into `catalog-sync`.
- Both JWT and opaque access tokens work with Client Credentials. The OAuth2 Client does not need to decode the JWT to send it; the Resource Server is responsible for validation/authorization.
- Never confuse **client secret** with **access token**: the client secret goes only in token requests to the AS; the access token is the short-lived credential sent to allowed RS endpoints.

Under heavy request load, Spring Security can store an **`OAuth2AuthorizedClient`** keyed by **`ClientRegistration`** and a stable principal name, reusing the still-valid access token. Not every request needs to hit the token endpoint. Token issuance may be rate-limited by the IdP, so track both token request counts and API request counts.

## 3. Choosing the Right Reactive Spring Security Components

| Component | Role |
| --- | --- |
| **`ReactiveClientRegistrationRepository`** | Stores registration config: client ID/secret, token URI, grant, and scopes |
| **`ReactiveOAuth2AuthorizedClientService`** | Persists/looks up authorized clients/tokens by registration and principal |
| **`ReactiveOAuth2AuthorizedClientProvider`** | Implements allowed grants—here only **`clientCredentials()`** |
| **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`** | Acquires/caches authorized clients **outside `ServerWebExchange`**, ideal for background jobs and service-to-service calls |
| **`DefaultReactiveOAuth2AuthorizedClientManager`** | Intended for cases bound to an incoming **`ServerWebExchange`** request |
| **`ServerOAuth2AuthorizedClientExchangeFilterFunction`** | Attaches the access token to WebClient requests |
| **`OAuth2AuthorizeRequest`** | Authorization request specifying registration ID and principal |

**Why not rely on `ServerWebExchange` by default?** Scheduled jobs, Kafka consumers, or services without an inbound HTTP request still need an application identity. In those cases, use **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`** and pass a fixed principal name such as **`catalog-sync-service`** when authorizing. This serves as a **token management key**, not a way to spoof a user to the resource server.

Many online examples use **`OAuth2AuthorizedClientManager`**, **`ServletOAuth2AuthorizedClientExchangeFilterFunction`**, and **`HttpSecurity`**. Those belong to the Servlet stack. WebFlux requires the **`Reactive...`** and **`ServerOAuth2...`** classes. Do not hand-roll HTTP calls to the token endpoint and parse JSON tokens when the OAuth2 Client framework already handles expiry, caching, and association.

Within a `ServerWebExchange` context, you can also use **`ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId("partner")`** with an appropriate principal. For background tasks, this guide explicitly calls **`manager.authorize()`** to obtain an authorized client for a service principal and then attaches **`oauth2AuthorizedClient(...)`** to the WebClient request. Do not mix the two patterns arbitrarily.

## 4. Java 17 + Spring Boot 3.3 Project: Complete Code

The demo uses a Spring Boot application exposing **`PartnerClient`**. The integration test starts **`MockWebServer`** to act as both the token endpoint and the resource API. Running tests requires no real IdP, credentials, or external API.

~~~text
client-credentials-demo/
├─ settings.gradle
├─ build.gradle
├─ src/main/resources/application.yml
├─ src/main/java/example/oauth/ClientCredentialsApplication.java
└─ src/test/java/example/oauth/PartnerClientIntegrationTest.java
~~~

### 4.1 Gradle

**settings.gradle**

~~~groovy
rootProject.name = 'client-credentials-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

You do not need **`spring-boot-starter-oauth2-resource-server`** if `catalog-sync` **only makes outbound API calls** using client credentials. If the application also verifies Bearer JWTs on **inbound** requests, add Resource Server and a **`SecurityWebFilterChain`** matching the inbound contract; that is separate from outbound token acquisition.

### 4.2 Configuring ClientRegistration and Secrets

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - partner.read
        provider:
          partner:
            token-uri: ${PARTNER_TOKEN_URI}

partner:
  api-base-url: ${PARTNER_API_BASE_URL}
~~~

- **`partner`** is the application-chosen registration ID and must match the argument passed to **`OAuth2AuthorizeRequest`**.
- **`token-uri`** is the Authorization Server endpoint; **`api-base-url`** is the Resource Server host—usually two distinct systems/hosts.
- **`client-id`/`client-secret`** are injected from environment variables or a secret manager. Never hardcode real secrets in source files, logs, or test output.
- **`scope`** represents the permissions requested by the client. The granted scope may be narrower, and the Resource Server decides allowed actions.
- With production APIs/IdPs, use HTTPS with certificate verification; never disable certificate validation for “convenience.”
- Tests in section 5 use **`@DynamicPropertySource`** to override config values with local endpoints and test credentials, so running tests requires no real secrets.

To run the app standalone, provide valid **`PARTNER_CLIENT_ID`**, **`PARTNER_CLIENT_SECRET`**, **`PARTNER_TOKEN_URI`**, and **`PARTNER_API_BASE_URL`** variables. The demo has no scheduler/controller calling the partner automatically; **`PartnerClient.status()`** is invoked by integration tests or explicit business logic.

### 4.3 Application, Manager, and WebClient

**src/main/java/example/oauth/ClientCredentialsApplication.java**

~~~java
package example.oauth;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@SpringBootApplication
public class ClientCredentialsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientCredentialsApplication.class, args);
    }
}

@Configuration
class PartnerOAuthConfiguration {
    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        // Demo: in-memory tokens per application instance.
        return new InMemoryReactiveOAuth2AuthorizedClientService(registrations);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService clients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, clients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("partnerWebClient")
    WebClient partnerWebClient(
            WebClient.Builder builder,
            ReactiveOAuth2AuthorizedClientManager manager,
            @Value("${partner.api-base-url}") String apiBaseUrl) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        // Dedicated client for the target Resource Server: do not enable default
        // token attachment across every WebClient in the application.
        return builder
                .baseUrl(apiBaseUrl)
                .filter(oauth2)
                .build();
    }
}

record PartnerStatus(String status) {}

@Service
class PartnerClient {
    private static final String REGISTRATION = "partner";
    private static final String SERVICE_PRINCIPAL = "catalog-sync-service";

    private final WebClient webClient;
    private final ReactiveOAuth2AuthorizedClientManager manager;

    PartnerClient(
            @Qualifier("partnerWebClient") WebClient webClient,
            ReactiveOAuth2AuthorizedClientManager manager) {
        this.webClient = webClient;
        this.manager = manager;
    }

    Mono<PartnerStatus> status() {
        OAuth2AuthorizeRequest authorizationRequest =
                OAuth2AuthorizeRequest.withClientRegistrationId(REGISTRATION)
                        .principal(SERVICE_PRINCIPAL)
                        .build();

        return manager.authorize(authorizationRequest)
                .switchIfEmpty(Mono.error(new IllegalStateException(
                        "Authorization Server did not authorize partner client")))
                .flatMap(authorizedClient ->
                        webClient.get()
                                .uri("/v1/status")
                                .attributes(oauth2AuthorizedClient(authorizedClient))
                                .retrieve()
                                .bodyToMono(PartnerStatus.class));
    }
}
~~~

**Explaining the call path:**

1. **`status()`** constructs an `OAuth2AuthorizeRequest` for registration **`partner`** and fixed principal **`catalog-sync-service`**. It does not use a username from an incoming request.
2. **`manager.authorize(...)`** returns **`Mono<OAuth2AuthorizedClient>`**. If no valid token exists, the **`clientCredentials()`** provider calls the token endpoint using a reactive HTTP client. If an unexpired cached token exists, the manager can reuse it.
3. **`switchIfEmpty(...)`** prevents a missing authorized client from silently turning into an unauthenticated request.
4. **`oauth2AuthorizedClient(authorizedClient)`** supplies the client/token to the OAuth2 filter; the filter attaches **`Authorization: Bearer ...`** to the GET request for that API.
5. **`retrieve().bodyToMono(PartnerStatus.class)`** decodes the JSON and emits a reactive error on HTTP failure statuses.
6. There is no manual **`block()`** or **`subscribe()`** inside the service. The caller manages subscription, cancellation, and timeouts.

A stable principal lets the **authorized-client service** reuse tokens under the same registration. In multi-tenant applications with **distinct client credentials**, never share principals/registrations and tokens casually across tenants; isolate config/tokens per IdP policy.

**Why not call `setDefaultOAuth2AuthorizedClient(true)`?** That setting can attach tokens to unintended requests if a `WebClient` is shared. The demo passes the authorized client **explicitly** and isolates a dedicated `WebClient` for the partner API. Also never forward inbound header tokens directly without an explicit token-relay or token-exchange contract.

## 5. Integration Test: Mock Token Endpoint + Resource API

`MockWebServer` returns a test access token and mocked JSON. The test boots the real Spring context and exercises **`ReactiveOAuth2AuthorizedClientManager → HTTP token endpoint → WebClient filter → HTTP resource API`**. This tests client credentials at the HTTP protocol level, though it does not test signature validation, introspection, TLS, or real authorization at the partner Resource Server.

**src/test/java/example/oauth/PartnerClientIntegrationTest.java**

~~~java
package example.oauth;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class PartnerClientIntegrationTest {
    private static final MockWebServer SERVER = startServer();

    @Autowired
    PartnerClient partner;

    private static MockWebServer startServer() {
        try {
            MockWebServer server = new MockWebServer();
            server.start();
            return server;
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry properties) {
        properties.add(
                "spring.security.oauth2.client.registration.partner.client-id",
                () -> "demo-client");
        properties.add(
                "spring.security.oauth2.client.registration.partner.client-secret",
                () -> "demo-secret");
        properties.add(
                "spring.security.oauth2.client.provider.partner.token-uri",
                () -> SERVER.url("/oauth/token").toString());
        properties.add(
                "partner.api-base-url",
                () -> SERVER.url("/").toString());
    }

    @AfterAll
    static void shutDown() throws IOException {
        SERVER.shutdown();
    }

    @Test
    void obtainsClientCredentialsTokenAndReusesItForApiCalls()
            throws InterruptedException {

        // Request 1: token endpoint.
        SERVER.enqueue(new MockResponse()
                .addHeader("Content-Type", "application/json")
                .setBody("""
                    {
                      "access_token": "demo-access-token",
                      "token_type": "Bearer",
                      "expires_in": 3600,
                      "scope": "partner.read"
                    }
                    """));

        // Requests 2 and 3: resource API.
        for (int i = 0; i < 2; i++) {
            SERVER.enqueue(new MockResponse()
                    .addHeader("Content-Type", "application/json")
                    .setBody("{\"status\":\"ready\"}"));
        }

        StepVerifier.create(partner.status())
                .assertNext(result -> assertEquals("ready", result.status()))
                .verifyComplete();

        StepVerifier.create(partner.status())
                .assertNext(result -> assertEquals("ready", result.status()))
                .verifyComplete();

        RecordedRequest token = SERVER.takeRequest(5, TimeUnit.SECONDS);
        RecordedRequest firstApi = SERVER.takeRequest(5, TimeUnit.SECONDS);
        RecordedRequest secondApi = SERVER.takeRequest(5, TimeUnit.SECONDS);

        assertNotNull(token, "Expected a token endpoint call");
        assertNotNull(firstApi, "Expected first resource call");
        assertNotNull(secondApi, "Expected second resource call");

        assertEquals("/oauth/token", token.getPath());
        assertEquals("POST", token.getMethod());
        assertTrue(token.getHeader("Authorization").startsWith("Basic "));
        assertTrue(token.getBody().readUtf8()
                .contains("grant_type=client_credentials"));

        assertEquals("/v1/status", firstApi.getPath());
        assertEquals("/v1/status", secondApi.getPath());
        assertEquals("Bearer demo-access-token",
                firstApi.getHeader("Authorization"));
        assertEquals("Bearer demo-access-token",
                secondApi.getHeader("Authorization"));

        // One token request, two API calls within the same token lifetime.
        assertEquals(3, SERVER.getRequestCount());
    }
}
~~~

**Run** in the directory containing **`build.gradle`**:

~~~bash
gradle test --tests example.oauth.PartnerClientIntegrationTest
~~~

Or if a compatible Gradle Wrapper is present:

~~~bash
./gradlew test --tests example.oauth.PartnerClientIntegrationTest
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.oauth.PartnerClientIntegrationTest
~~~

**Expected output:** the test build succeeds and **`obtainsClientCredentialsTokenAndReusesItForApiCalls`** passes. Gradle stdout varies by version/cache, so do not treat a fixed log line as proof. The core assertions are the contract: the first request is **`POST /oauth/token`**, the next two are **`GET /v1/status`**, the Bearer token matches, and only one token acquisition occurs while valid.

**Confidence and limits:** the mock token **`demo-access-token`** is accepted as-is by the mock Resource Server. The test verifies the client sends credentials, **not** that a real RS validates the token. The test relies on `OAuth2AuthorizedClientService` caching the token in the shared application context; if storage, principal, registration, or process changes, verify caching separately.

## 6. Token Reuse, Expiration, and Scopes

### 6.1 Token Caching

**`InMemoryReactiveOAuth2AuthorizedClientService`** keeps authorized clients in memory per instance. **`manager.authorize()`** with the same registration ID + principal name reuses an unexpired token; when near expiration, the `client_credentials` provider requests a new token according to the framework's expiry and clock skew settings. This is normally **issuing a new access token**, not a refresh token flow.

Do not assume **`expires_in=3600`** guarantees a token remains valid for exactly 3,600 seconds on every node: network latency, clock skew, and IdP policies all apply. Measure against your runtime.

### 6.2 When Running Multiple Replicas

Each replica with an in-memory service caches its **own** token; 10 replicas starting simultaneously can trigger 10 token requests. That may be acceptable, provided you account for IdP rate limits and capacity. If using a distributed store or custom cache, pay attention to credential encryption, TTLs, expiration races, tenant isolation, eviction, and revocation. Never store a Bearer token permanently in a static field.

### 6.3 Scopes, Audience, and Resources

Scope **`partner.read`** is what the client requests; final permissions are granted by the AS and enforced by the RS. The token's **audience** (when applicable per token format/IdP) must match the receiving API. A client cannot forge a trusted audience by editing a JWT payload. Client Credentials do not replace **mTLS/HTTPS** if the partner contract requires them.

When the API returns **403**, inspect scope/role/policy; when it returns **401**, inspect expiration/revocation, issuer/audience, and token errors. Never automatically escalate scopes or replay the token to another host to test.

## 7. Additional Test Matrix for Real Systems

For each scenario, stub the AS/RS in realistic order and assert request counts, status/exceptions, latency, and side effects:

| Scenario | Stub/input | What to assert |
| --- | --- | --- |
| Initial token issuance | AS returns 200 + Bearer + `expires_in` | AS receives POST `client_credentials`; API receives Bearer |
| Token reuse | Two API calls while token is valid | No redundant token requests for the same client/principal |
| Wrong client secret | AS returns **`invalid_client`** or 401 | API is not called with a bogus Bearer; pipeline emits error |
| Denied scope | AS returns **`invalid_scope`** | Scope is not altered to bypass limits; clear error emitted |
| Malformed token JSON | Missing `access_token`/`token_type` | Resource call is not treated as successful |
| Expired access token | Expired token fixture / controlled clock | Requests a fresh token instead of reusing the old one |
| Resource API returns 401 | Response with appropriate `WWW-Authenticate` | Never “allows”; does not retry infinitely |
| Resource API returns 403 | Token accepted but lacks permission | Does not escalate scopes or switch client IDs |
| AS timeout/TLS error | Token endpoint unreachable | Fail closed; without a token, never call the resource |
| API timeout/429/5xx | AS issues token, downstream fails | Bounded timeout and selective retries |
| API host changed | Redirect/config/absolute URI outside allowlist | Does not leak Bearer token |
| Request burst | Concurrent calls | Measure token storms, queueing, pool, and reuse |
| Tracing/logs | Wire logging enabled in test env | No `client_secret` or access token logged |

**Do not count AS calls by reading the cache before the test:** doing so mutates state. Observing `RecordedRequest` entries on a mock server provides stronger evidence.

### Example Failure Test with StepVerifier

~~~java
// Snippet added to a test whose mock AS has an error response enqueued.
// An isolated test must use a fixture without a cached access token.
StepVerifier.create(partner.status())
        .expectError()
        .verify();

// Also assert HTTP request count and that no GET /v1/status ran
// when the Authorization Server failed to issue a token.
~~~

This is an illustrative snippet, not a standalone program. When a token is already cached from another test, requests may skip the AS; isolate test contexts/registrations/principals or intentionally reset storage. For each failure case, assert the **specific exception type** if defined by your application contract.

### Retries Must Be Bounded

- **`invalid_client`, `invalid_scope`, permission-related 401/403:** repeated retries usually cannot fix misconfiguration.
- **429/503/transient network errors:** retry **boundedly** with backoff, jitter, and `Retry-After` inside the overall timeout budget.
- **POST with side effects:** do not auto-retry on timeout without an idempotency key/deduplication contract, because the request may have succeeded even if the response was lost.
- **Token endpoint:** avoid re-issuing a new token on every downstream failure. Invalidation/renewal on specific errors must be rate-bounded to prevent token storms.

## 8. Timeouts, Pooling, and Operational Observability

### 8.1 Two Outbound HTTP Paths Must Be Managed Separately

There are two outbound connections:

1. **Token endpoint** called by the OAuth2 client framework.
2. **Resource API** called by **`partnerWebClient`**.

Depending on the Spring Security version, the token endpoint HTTP client is configured via **`ReactiveOAuth2AccessTokenResponseClient`**. Customizing the Reactor Netty connector on **`partnerWebClient`** **does not automatically** alter timeouts, proxies, TLS, or pools on the token client. If deploying with mTLS or proxies, configure and test both paths. On Spring Security 6.3+, refer to customizing the token response client for the **`client_credentials`** grant.

Measure and bound:

- Connect timeout: waiting for TCP.
- Response timeout: waiting for response.
- Pool acquire timeout: waiting for a connection.
- **End-to-end deadline** from the caller: token acquisition + resource call + retries + queueing.

A **`Mono.timeout(Duration.ofSeconds(...))`** at the caller provides a useful overall deadline, though it does not replace connect timeouts or pool limits.

~~~java
// Caller injected with PartnerClient; snippet is not standalone.
Mono<PartnerStatus> result =
        partner.status().timeout(java.time.Duration.ofSeconds(8));
~~~

On timeout/cancellation, the server may already have received the HTTP request; do not assume mutations rolled back.

### 8.2 Metrics to Track

| Group | What to observe | Goal |
| --- | --- | --- |
| AS/token | request p50/p95/p99, 4xx/5xx statuses, timeouts | Detect slow IdP, wrong credentials, token storms |
| Token cache | token request count, reuse, expiry | Verify caching and rotation |
| RS/API | RPS, p95/p99, 401/403/429/5xx, timeouts | Separate policy failures from downstream load |
| HTTP pool | active/pending connections, DNS/connect/TLS | Catch pool/network bottlenecks |
| JVM/reactive | CPU, memory, event-loop blocking, scheduler queues | Spot blocking calls or saturation |
| Security | normalized error codes, registration ID | Debug without leaking tokens |

Never attach **raw tokens, client secrets, Authorization headers, user-provided URLs, or credential-bearing response bodies** to metric labels, span attributes, or logs. Use bounded values like registration/provider names. When debugging failures, log redacted error codes.

**Concurrency note:** when multiple requests arrive simultaneously as a token expires, multiple token requests may fire depending on provider/scheduler/storage. Test under real load or a mock AS rather than assuming strict single-flight behavior from the framework.

## 9. Inbound and Outbound Authorization Are Separate Responsibilities

~~~text
Incoming client ──JWT/session──> catalog-sync (WebFlux Resource Server)
                                    |
                                    | service principal + client_credentials
                                    v
                              Authorization Server
                                    |
                                    | catalog-sync's access token
                                    v
                              partner-api (Resource Server)
~~~

- **Incoming `SecurityWebFilterChain`** authenticates/authorizes callers entering `catalog-sync`.
- **Outgoing OAuth2 Client** obtains a token with the machine identity and scopes meant for `partner-api`.
- Do not forward an incoming client's token outbound without an explicit token-relay or token-exchange contract.
- If you need to “call the API on Alice's behalf,” Client Credentials **carry neither Alice's consent nor Alice's roles**. Use Authorization Code, token exchange, or an on-behalf-of flow supported by the AS.
- Never expose a public endpoint allowing arbitrary callers to trigger a WebClient holding broader machine privileges without inbound authorization.

**Example inbound config (illustrative only, not part of the complete project in section 4):**

~~~java
@Bean
SecurityWebFilterChain inboundSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers("/health").permitAll()
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth ->
                    oauth.jwt(Customizer.withDefaults()))
            .build();
}
~~~

This snippet needs imports for **`@Bean`**, **`SecurityWebFilterChain`**, **`ServerHttpSecurity`**, **`Customizer`**, dependency **`spring-boot-starter-oauth2-resource-server`**, and a valid decoder/issuer/audience; it is not a standalone class. Adding an inbound Resource Server does not alter outbound authorization in section 4.

## 10. Production Security and Operations Decisions

**Credential protection.** Use a secret manager or workload identity (mTLS/`private_key_jwt` if supported by the AS) with least-privilege secret read access and formal rotation. Never store plaintext secrets in repos, logs, or query strings. A misconfigured token endpoint can leak Basic headers, so verify trusted endpoints at deployment time.

**Destination restriction.** Use a dedicated WebClient with an allowlisted base URL/host. Never accept an absolute URI from a query/body and attach Bearer tokens to arbitrary hosts; review redirects and proxies. Tokens must be scoped to the intended API per resource/audience policy.

**Least privilege.** Give each partner/integration its own registration and scopes; do not grant write when only read is needed. In multi-tenant setups, isolate registrations, stores, and credentials to avoid cache key collisions.

**Fail closed.** If the AS fails to issue a token or the RS returns 401/403, never bypass OAuth2 or reuse an expired token. Circuit breakers, timeouts, and throttling protect stability without overriding authorization decisions.

**Revocation.** Tokens can be revoked before `expires_in`. If the RS returns 401, define how to invalidate the authorized client and acquire a new token with a bounded retry limit—never loop into a token storm.

**Safe diagnostics.** Redact Authorization headers, token responses, and client credentials in HTTP wire logs, exceptions, traces, and test artifacts. Never dump raw requests/responses while troubleshooting, even in staging.

**Idempotency.** Safe GET calls can be retried selectively. Side-effecting POST/PUT/PATCH requests require idempotency keys/correlation IDs and reconciliation to avoid duplicate transactions.

## 11. Common Failures and Diagnostics

| Symptom | Possible cause | Verification / fix |
| --- | --- | --- |
| Missing **`ReactiveClientRegistrationRepository`** | Missing OAuth2 client starter or invalid registration | Check dependencies/YAML/runtime |
| **Unsupported authorization grant** | `clientCredentials()` not enabled or invalid registration | Check provider/registration |
| `manager.authorize()` is empty | Mismatched registration/principal/provider | Verify registration ID and grant |
| AS returns **`invalid_client`** | Wrong ID/secret or client auth method | Check token endpoint and IdP without logging secrets |
| AS returns **`invalid_scope`** | Requested scope exceeds permissions | Review policy and least privilege |
| 401 from `partner-api` | Expired/revoked token, wrong issuer/audience | Inspect RS error contract, not just Bearer presence |
| 403 from `partner-api` | Missing scope or resource rule | Compare granted scopes with policy |
| WebClient lacks Bearer header | Missing filter or **`oauth2AuthorizedClient(...)`** | Assert actual recorded request on mock server |
| Token sent to wrong API | Global default token, unallowlisted URI/redirect | Isolate WebClient and validate host |
| Test context fails on secret placeholders | Test does not override YAML env vars | Use **`@DynamicPropertySource`** |
| HTTP timeout | Slow AS or RS, exhausted pool | Measure both paths separately; tune timeouts/retries/pool |
| AS called on every request | Changing principal, unused cache, tiny TTL | Count AS calls and verify expiry |
| Blocked event loop | `RestTemplate`, `block()`, sync HTTP in handler | Use reactive WebClient, `StepVerifier`, and profiling |
| Production TLS fails while tests pass | HTTP `MockWebServer` skips certs/proxies | Add HTTPS/mTLS integration tests |

In WebFlux, avoid manual **`.block()`** and **`.subscribe()`** in controllers/services. Return **`Mono<PartnerStatus>`** to the caller. CLI tests may await the `Mono` to assert; the demo uses `StepVerifier` to show reactive semantics.

## 12. Extension Exercises

1. **Expiry:** mock two distinct tokens with a short controlled lifetime; verify requests after expiration use the new token without long sleeps.
2. **Scope:** have the AS omit `partner.read` or the RS return 403; ensure the client does not escalate privileges.
3. **AS timeout:** delay the mock AS past the timeout; verify zero resource requests are sent without a token.
4. **Unauthorized RS:** have the RS return 401 with a Bearer error; verify authorized-client invalidation/failure handling for your version.
5. **Concurrency:** burst with `Flux.range(...).flatMap(...)`, count token vs. API requests, and measure pooling and token storms.
6. **Two registrations:** separate `partner-read` and `partner-write` scopes and confirm tokens are never mixed.
7. **Multi-tenant:** ensure tenant A's credentials and tokens are never used for tenant B.
8. **Observability:** enable redacted metrics/tracing and observe AS/RS errors and p95/p99 latencies.

Not every application needs a scheduler or controller. **`PartnerClient.status()`** can be reused in a task queue, periodic job, or WebFlux service handler protected by inbound security. Pick the invocation point per business rules without exposing machine privileges to untrusted callers.

## 13. Acceptance Checklist

- Distinguish OAuth2 **Client Credentials** from Authorization Code, JWT validation, and token relay.
- Configure **registration/provider**, **`client_credentials`**, scopes, Basic client authentication, token URI, and resource API base URL correctly.
- Use **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`** for service/background tasks with a stable principal to reuse tokens.
- Attach tokens via **`ServerOAuth2AuthorizedClientExchangeFilterFunction`** on a dedicated WebClient without leaking Bearer headers to arbitrary hosts.
- Avoid **`block()`/`subscribe()`** in reactive request flows and never cache tokens permanently past expiry.
- Test the POST token endpoint, grant, Basic auth, two Bearer GETs, and single token acquisition using local mock HTTP.
- Plan tests for `invalid_client`, `invalid_scope`, 401/403, timeouts, retries, rotation/revocation, pools, and bursts.
- Enforce HTTPS, secret rotation, least privilege, token redaction, and separate inbound authorization in production.

**References:** [Spring Security – Reactive OAuth2 Client: Core Interfaces/Classes](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html), [RFC 6749 §4.4 – Client Credentials Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.4), [RFC 6750 – Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).

**Remember:** the safe path in WebFlux service-to-service calls is **`ClientRegistration → ReactiveOAuth2AuthorizedClientManager → valid authorized client → WebClient OAuth2 filter → partner API`**. Prove it with tests covering token issuance and the exact destination, even under expiration, network errors, or concurrent load.