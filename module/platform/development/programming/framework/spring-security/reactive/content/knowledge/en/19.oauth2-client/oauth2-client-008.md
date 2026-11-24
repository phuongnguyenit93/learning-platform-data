# Selecting clientRegistrationId or OAuth2AuthorizedClient per Call

## Learning Objectives

This lesson belongs to the **OAuth2 Client** section of **Spring Security reactive / Spring WebFlux**. After studying it, you will be able to:

1. Distinguish `ClientRegistration`, `clientRegistrationId`, `OAuth2AuthorizedClient`, `ReactiveOAuth2AuthorizedClientManager`, and `ServerOAuth2AuthorizedClientExchangeFilterFunction`.
2. Select an OAuth2 client **per outbound WebClient request**, using `.attributes(clientRegistrationId("..."))` or `.attributes(oauth2AuthorizedClient(client))`.
3. Explain why the two approaches are not equivalent in every situation, especially when an app supports **multiple users, multiple OAuth2 providers, or multiple downstream APIs**.
4. Combine `@RegisteredOAuth2AuthorizedClient` in a WebFlux controller, `ReactiveSecurityContextHolder`, and the appropriate authorized-client store.
5. Configure **user-delegated `authorization_code`** versus **service-to-service `client_credentials`**, including a scheduled job without a `ServerWebExchange`.
6. Identify risks of implicit defaults, forwarding tokens to the wrong audience, SSRF, and token exfiltration.
7. Run a standalone Java 17 offline example with the real WebClient filter and a fake authorization manager/transport, writing `StepVerifier` tests for two registrations, explicit clients, and unauthenticated requests.
8. Handle near-expiry tokens, refresh/reauthorization, and 401/403 Resource Server responses per Spring Security reactive 6.5.

> Use **reactive OAuth2 Client** APIs only: `ServerOAuth2AuthorizedClientExchangeFilterFunction` and `ReactiveOAuth2AuthorizedClientManager`. The Servlet variant is `ServletOAuth2AuthorizedClientExchangeFilterFunction` and is not a drop-in replacement for WebFlux. Outbound OAuth2 Client also differs from `oauth2ResourceServer().jwt()`, which **validates inbound tokens**.

## 1. Why Select a Client on Every Request?

A WebFlux backend may call multiple services with different permissions:

~~~text
User/browser ----> Spring WebFlux application
                       |
                       +---> Catalog API
                       |       OAuth2 registration: catalog-client
                       |       Required scope: catalog.read
                       |
                       +---> Billing API
                       |       OAuth2 registration: billing-client
                       |       Required scope: billing.read
                       |
                       +---> Profile API
                               OAuth2AuthorizedClient
                               of the user who granted access
~~~

You should never send Alice's Profile access token to Billing, or a Catalog-audience token to CRM. A Bearer token is a credential: whoever holds it can attempt to use it wherever the server accepts it.

### 1.1. Core Terminology

| Entity | Role | What Is Inside? |
|---|---|---|
| `ClientRegistration` | OAuth2 client metadata registered in Spring. | `registrationId`, client ID/secret, grant type, scopes, provider/token/authorization URIs. |
| `clientRegistrationId` | String key used to look up the config. | E.g., `"catalog-client"`, **not** necessarily the IdP-issued client ID. |
| `OAuth2AuthorizedClient` | A client granted an access token for a resource owner. | `ClientRegistration`, `principalName`, access token, and optional refresh token. |
| `ReactiveOAuth2AuthorizedClientManager` | Manages authorize/re-authorize, load/save, refresh/renew. | Coordinates providers, service/repository, and principal/context. |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Integrates OAuth2 Client with reactive WebClient. | Reads request attributes, resolves authorized client, sets HTTP Bearer header. |
| `ServerOAuth2AuthorizedClientRepository` | Stores authorized clients per WebFlux request/principal. | Authorized client data serving web requests. |
| `ReactiveOAuth2AuthorizedClientService` | Application-level service to load/save authorized clients. | Typically keyed by `registrationId + principalName`. |

**Important:** One registration can map to many authorized clients:

~~~text
ClientRegistration ID = "profile-login"

  OAuth2AuthorizedClient(user="alice")
      -> accessToken A

  OAuth2AuthorizedClient(user="bob")
      -> accessToken B
~~~

Therefore, **knowing only the registration ID does not identify which user or token applies**. The manager needs the matching principal or current security context. Conversely, one user can hold multiple authorized clients across multiple registrations.

### 1.2. Registration ID Differs from the Provider's Client ID

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          catalog-client:
            client-id: catalog-application-id-issued-by-provider
            authorization-grant-type: client_credentials
~~~

This YAML snippet is a **configuration fragment to identify field names**; it is incomplete for `client_credentials` because secret and provider/token URI are omitted. The argument `clientRegistrationId("catalog-client")` must be the **YAML key `catalog-client`**, not the string `catalog-application-id-issued-by-provider`.

## 2. How Does the WebClient OAuth2 Filter Work?

Typical configuration:

~~~java
@Bean
WebClient oauthWebClient(
    WebClient.Builder builder,
    ReactiveOAuth2AuthorizedClientManager manager) {

    var oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return builder.filter(oauth2).build();
}
~~~

This is a **Spring bean configuration method fragment**. The filter is not an Authorization Server. It bridges an outbound `WebClient` request and the authorized client manager.

~~~text
WebClient outgoing request
        |
        v
ServerOAuth2AuthorizedClientExchangeFilterFunction
        |
        +-- Has oauth2AuthorizedClient(object)?
        |       -> use explicit object;
        |          manager may re-authorize/refresh
        |
        +-- Has clientRegistrationId("id")?
        |       -> use id + principal/context,
        |          manager lookup/authorize/refresh
        |
        +-- No client specified?
                -> no implicit token unless an
                   appropriate default is enabled
        |
        v
Authorization: Bearer <access-token>
        |
        v
Downstream Resource Server validates token/permissions
~~~

This is a **conceptual diagram**. Avoid setting conflicting `oauth2AuthorizedClient(...)` and `clientRegistrationId(...)` attributes on the same request and relying on internal filter precedence. **Pick one style per call**.

### 2.1. What the Filter Does NOT Guarantee by Itself

- That the token definitely holds the target API's required scopes or audience.
- That the caller is authorized to invoke a sensitive service registration.
- That the Authorization Server will always issue/refresh a token.
- That the requested host is valid and free from SSRF.
- That the Resource Server will allow the business operation.
- That inbound APIs are protected against CSRF.
- That requests lacking any OAuth2 attribute will automatically carry a token.

Those constraints must be enforced across Authentication, Authorization, manager config, outbound routing, and the resource server.

## 3. Approach 1: Selecting clientRegistrationId per Request

When you know which registration serves an endpoint, without already holding an authorized client object:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> readCatalog(WebClient client) {
    return client.get()
        .uri("https://catalog-api.example.test/v1/items")
        .attributes(clientRegistrationId("catalog-client"))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

This is a Java method fragment; `client` must be configured with the OAuth2 filter. On subscribe, the manager can:

1. Look up `ClientRegistration` for `catalog-client`.
2. Determine the principal and authorization context.
3. Look up a saved `OAuth2AuthorizedClient`.
4. If needed and supported by a provider, request a new token or refresh/reauthorize.
5. Return the object so the filter places `Authorization: Bearer ...` on the HTTP request.

**Passing an ID does not guarantee a token is always returned**. `client_credentials` can request tokens directly, whereas a user's `authorization_code` flow may need browser redirect/consent. If the grant/provider is unsupported, the principal is wrong, or the token service errors, the request cannot be authorized.

### 3.1. Two Requests in One Pipeline

~~~java
Mono<String> catalog = webClient.get()
    .uri("https://catalog-api.example.test/v1/items")
    .attributes(clientRegistrationId("catalog-client"))
    .retrieve().bodyToMono(String.class);

Mono<String> billing = webClient.get()
    .uri("https://billing-api.example.test/v1/invoices")
    .attributes(clientRegistrationId("billing-client"))
    .retrieve().bodyToMono(String.class);

return Mono.zip(catalog, billing)
    .map(tuple -> tuple.getT1() + " | " + tuple.getT2());
~~~

This is a service snippet. The same `WebClient` bean serves both calls while each request keeps its own token selection. Never mutate a global default registration between two concurrent requests, as that causes races and credential leaks.

### 3.2. Never Take Registration or URL Directly from User Input

~~~java
// SECURITY ANTI-PATTERN, do not use in production:
@GetMapping("/proxy")
Mono<String> proxy(@RequestParam String registrationId,
                   @RequestParam String targetUrl) {
    return webClient.get()
        .uri(targetUrl)
        .attributes(clientRegistrationId(registrationId))
        .retrieve().bodyToMono(String.class);
}
~~~

Bug: the caller chooses both the **OAuth2 registration** and the **URL receiving the token**. This can trigger client credentials stronger than the caller's privileges or send Bearer tokens to an attacker's domain (**SSRF/token exfiltration**).

Replace with server-controlled routing:

~~~text
Operation listCatalog
   -> required app permission: catalog:read
   -> trusted registration: catalog-client
   -> trusted host: https://catalog-api.example.test

Operation listBilling
   -> required app permission: billing:read
   -> trusted registration: billing-client
   -> trusted host: https://billing-api.example.test
~~~

If multi-tenant dynamic routing is required, validate tenant/client registrations against a policy-enforced allowlist—never take raw registrationIds or URLs straight from query parameters.

## 4. Approach 2: Passing an Explicit OAuth2AuthorizedClient Object

When a controller already holds a **trusted** authorized client object, for instance via `@RegisteredOAuth2AuthorizedClient`:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@GetMapping("/my-profile")
Mono<String> profile(
    @RegisteredOAuth2AuthorizedClient("profile-login")
    OAuth2AuthorizedClient authorizedClient) {

    return webClient.get()
        .uri("https://profile-api.example.test/v1/me")
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve().bodyToMono(String.class);
}
~~~

This is a controller fragment requiring an injected `webClient` and corresponding imports. `@RegisteredOAuth2AuthorizedClient` from `org.springframework.security.oauth2.client.annotation` provides an argument resolver for Spring Security reactive controllers.

Conditions to verify:

- `authorizedClient.getClientRegistration().getRegistrationId()` is intended for the profile API.
- `authorizedClient.getPrincipalName()` belongs to the **resource owner currently being served**, not another user/tenant.
- The access token has an audience, scope, and issuer accepted by the target API.
- If the token has expired, the manager/provider may refresh it; do not assert that an explicit object always sends the old token unchanged.
- If consent/authorization is missing, handle the login flow or error; **never fall back to service/admin credentials**.
- Never place `authorizedClient.getAccessToken().getTokenValue()` in API JSON, logs, URLs, or the browser.

### 4.1. Comparing the Two Options

| Criterion | `clientRegistrationId("...")` | `oauth2AuthorizedClient(client)` |
|---|---|---|
| Input | Spring config key | Already-selected object |
| Principal dependency | Manager/repository looks up from context | Object carries its own `principalName` |
| Missing token | Manager can acquire token if grant supports it | Object must already be resolved |
| Refresh/re-authorize | Possible | Possible |
| User-delegated OAuth2 | Needs right current principal/store/consent | Explicit object for the right user |
| Service-to-service | Works with service manager and proper principal | Works when manager already issued object to job |
| Common mistake | Wrong registration/context | Using someone else's object |

**Neither option is automatically secure from its API signature alone**. Both must ensure tokens are sent only to trusted hosts with proper authorization.

### 4.2. Two OAuth2AuthorizedClients in One Controller

~~~java
@GetMapping("/dashboard")
Mono<String> dashboard(
    @RegisteredOAuth2AuthorizedClient("calendar-login")
    OAuth2AuthorizedClient calendar,
    @RegisteredOAuth2AuthorizedClient("crm-login")
    OAuth2AuthorizedClient crm) {

    Mono<String> events = webClient.get()
        .uri("https://calendar-api.example.test/v1/events")
        .attributes(oauth2AuthorizedClient(calendar))
        .retrieve().bodyToMono(String.class);

    Mono<String> contacts = webClient.get()
        .uri("https://crm-api.example.test/v1/contacts")
        .attributes(oauth2AuthorizedClient(crm))
        .retrieve().bodyToMono(String.class);

    return Mono.zip(events, contacts)
        .map(pair -> pair.getT1() + " / " + pair.getT2());
}
~~~

This is a controller fragment. It illustrates that the calendar token is not sent to CRM. If one provider lacks consent or rejects the request, handle the error gracefully in UX rather than reusing the other provider's token.

## 5. Right Principal, Reactor Context, and Authorized-Client Repository

In WebFlux, `Authentication` lives in the subscription's **Reactor Context**. Preserve this context when the outbound client looks up the user's authorized client.

~~~text
Alice's WebFlux request
      |
      +-- ReactiveSecurityContextHolder
              Authentication principal = Alice
              |
              +-- clientRegistrationId("crm-login")
                      |
                      +-- lookup authorized client:
                          registration = crm-login
                          principal = Alice
                          -> Alice's token, not Bob's token
~~~

### 5.1. Which Store Goes Where?

- `ServerOAuth2AuthorizedClientRepository` handles loading/saving authorized clients in the WebFlux **web request context**, tied to `ServerWebExchange`.
- `ReactiveOAuth2AuthorizedClientService` provides **application-level** storage, typically keyed by `registrationId` and `principalName`.
- `ServerSecurityContextRepository` stores **`Authentication`/`SecurityContext`** for login sessions, distinct from OAuth2 access/refresh token storage.
- `ReactiveOAuth2AuthorizedClientManager` coordinates these sources and issues/refreshes per grant.

### 5.2. Attaching ServerWebExchange When Configuration Requires It

The filter exposes a static helper:

~~~java
.attributes(
    ServerOAuth2AuthorizedClientExchangeFilterFunction
        .serverWebExchange(exchange))
~~~

`exchange` must be the `ServerWebExchange` from the current request. Do not assume every manager requires calling this helper; it depends on the constructor, repository, and available context.

If there is no web request (scheduler/worker), never fabricate a fake `ServerWebExchange` to bypass errors. Use a service-level manager as shown in section 6.

### 5.3. Do Not Subscribe or Block in the Wrong Place

~~~java
// Wrong in a WebFlux controller:
service.callCrm().subscribe();
return Mono.empty();
~~~

A detached subscription can lose security context and drop errors. The right pattern is to **return the publisher**:

~~~java
return service.callCrm();
~~~

`block()` must also never be called on the event loop. In a **console `main` program** or tests, blocking at the outer application boundary is acceptable and is demonstrated in section 7.

## 6. client_credentials in a Background Job

A scheduled job has no browser, HTTP request, or end-user principal. For machine-to-machine work, use:

`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`

and `ReactiveOAuth2AuthorizedClientService` to store service tokens. Spring Security clearly separates this manager from `DefaultReactiveOAuth2AuthorizedClientManager` used in web-request contexts.

~~~java
@Bean
ReactiveOAuth2AuthorizedClientManager backgroundManager(
    ReactiveClientRegistrationRepository registrations,
    ReactiveOAuth2AuthorizedClientService service) {

    var manager =
        new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
            registrations, service);

    manager.setAuthorizedClientProvider(
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build());

    return manager;
}
~~~

This code fragment needs corresponding imports and belongs inside a configuration class. Use a stable service principal to manage tokens:

~~~java
Authentication servicePrincipal =
    new UsernamePasswordAuthenticationToken(
        "service:reporting", "N/A",
        AuthorityUtils.NO_AUTHORITIES);

OAuth2AuthorizeRequest authorizeRequest =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reporting-service")
        .principal(servicePrincipal)
        .build();

return backgroundManager.authorize(authorizeRequest)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("Authorization unavailable")))
    .flatMap(client -> webClient.get()
        .uri("https://reporting-api.example.test/v1/summary")
        .attributes(oauth2AuthorizedClient(client))
        .retrieve().bodyToMono(String.class));
~~~

This is a method fragment with `backgroundManager` and `webClient` injected. After the manager issues a token, pass the **exact authorized client** into the call. Never turn a service credential into a fallback when a user lacks OAuth2 consent: that creates a **confused deputy**.

**Note:** If the `WebClient` filter is configured with a different manager than `backgroundManager`, lookups/refreshes may split across two places. In production, wire the filter to a consistent manager/store or create a dedicated `WebClient` for background services.

## 7. Standalone Java 17 Example Without an IdP

We use Spring Security's **real `ServerOAuth2AuthorizedClientExchangeFilterFunction`**, substituting:

- A fixture `ReactiveOAuth2AuthorizedClientManager` returning two authorized clients with test tokens.
- An in-memory `ExchangeFunction` receiving requests **after the filter attaches Bearer**, echoing the header in a fake response.
- `ReactiveSecurityContextHolder.withAuthentication(...)` for the test principal context.

**There is no network traffic** to `trusted-api.invalid` or `idp.invalid`. Token strings are strictly unit-test data, **not credentials**. Never use this fake manager or echo Authorization headers in production.

### 7.1. Structure and Build

~~~text
oauth2-per-call-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/PerCallDemo.java
    └── test/java/example/PerCallDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'oauth2-per-call-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.16'
    }
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.PerCallDemo'
}

dependencies {
    implementation 'org.springframework:spring-webflux'
    implementation 'org.springframework.security:spring-security-oauth2-client'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use Java 17+ and a compatible Gradle/Wrapper. The Spring Boot BOM manages framework and security versions in this console project.

### 7.2. Complete Main Class

File `src/main/java/example/PerCallDemo.java`:

~~~java
package example;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

public final class PerCallDemo {

    private PerCallDemo() {
    }

    static ClientRegistration registration(String id) {
        return ClientRegistration.withRegistrationId(id)
            .clientId("fixture-client-" + id)
            .clientSecret("fixture-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
            .tokenUri("https://idp.invalid/token")
            .scope("demo.read")
            .build();
    }

    static OAuth2AuthorizedClient fixture(String id, String value) {
        var token = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            value,
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2099-01-01T00:00:00Z"));

        return new OAuth2AuthorizedClient(
            registration(id), "demo-principal", token);
    }

    private static final Map<String, OAuth2AuthorizedClient> CLIENTS =
        Map.of(
            "catalog", fixture("catalog", "fixture-catalog"),
            "billing", fixture("billing", "fixture-billing"));

    static Authentication principal() {
        return new UsernamePasswordAuthenticationToken(
            "demo-principal", "N/A",
            List.of(new SimpleGrantedAuthority("ROLE_DEMO")));
    }

    static WebClient client() {
        // TEST ONLY: does not call a real Authorization Server.
        ReactiveOAuth2AuthorizedClientManager manager = request -> {
            if (request.getAuthorizedClient() != null) {
                return Mono.just(request.getAuthorizedClient());
            }

            OAuth2AuthorizedClient selected =
                CLIENTS.get(request.getClientRegistrationId());

            return selected == null
                ? Mono.empty()
                : Mono.just(selected);
        };

        var oauth =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager);

        // TEST ONLY: no HTTP network, only inspects Bearer header.
        ExchangeFunction fakeTransport = request -> {
            String authorization =
                request.headers().getFirst(HttpHeaders.AUTHORIZATION);

            String body = authorization == null
                ? "(no-token)"
                : authorization;

            return Mono.just(
                ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE, "text/plain")
                    .body(body)
                    .build());
        };

        return WebClient.builder()
            .filter(oauth)
            .exchangeFunction(fakeTransport)
            .build();
    }

    static Mono<String> byRegistration(WebClient client, String id) {
        return client.get()
            .uri("https://trusted-api.invalid/resource")
            .attributes(clientRegistrationId(id))
            .retrieve()
            .bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    principal()));
    }

    static Mono<String> byClient(
        WebClient client, OAuth2AuthorizedClient authorized) {

        return client.get()
            .uri("https://trusted-api.invalid/resource")
            .attributes(oauth2AuthorizedClient(authorized))
            .retrieve()
            .bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    principal()));
    }

    static Mono<String> withoutChoice(WebClient client) {
        return client.get()
            .uri("https://trusted-api.invalid/resource")
            .retrieve()
            .bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    principal()));
    }

    private static void verify(
        String label, String actual, String expected) {

        if (!expected.equals(actual)) {
            throw new IllegalStateException(label + " mismatch");
        }
        System.out.println(label + ": PASS");
    }

    public static void main(String[] args) {
        WebClient webClient = client();

        // block() is only at the console main boundary, NEVER in WebFlux.
        verify("catalog-registration",
            byRegistration(webClient, "catalog").block(),
            "Bearer fixture-catalog");

        verify("billing-registration",
            byRegistration(webClient, "billing").block(),
            "Bearer fixture-billing");

        verify("explicit-authorized-client",
            byClient(webClient,
                fixture("catalog", "fixture-explicit")).block(),
            "Bearer fixture-explicit");

        verify("no-implicit-default",
            withoutChoice(webClient).block(),
            "(no-token)");
    }
}
~~~

Why is this code instructive?

1. `ClientRegistration` is created for two IDs, sharing `client_credentials` while differing in client ID and token fixtures.
2. The fake `ReactiveOAuth2AuthorizedClientManager` shows the manager inspects `getClientRegistrationId()` or `getAuthorizedClient()` to pick an object. Production managers perform real OAuth2 flows.
3. `ServerOAuth2AuthorizedClientExchangeFilterFunction` is the **real filter**; it attaches the Bearer header.
4. The fake `ExchangeFunction` intercepts at the in-memory boundary without connecting to `.invalid` domains.
5. `byRegistration` and `byClient` share one `WebClient` yet carry distinct selections.
6. `withoutChoice` confirms that without an implicit default, requests receive no token automatically.
7. Reactor Context propagates the principal; only `main` calls `block()` because this is a CLI, not a WebFlux server.

### 7.3. Running and Expected Output

~~~bash
gradle run
~~~

Or `./gradlew run`, `gradlew.bat run` when a Gradle Wrapper is present. Expected **main stdout** (excluding Gradle logs):

~~~text
catalog-registration: PASS
billing-registration: PASS
explicit-authorized-client: PASS
no-implicit-default: PASS
~~~

This stdout is **expected from the code**, not a claim that a build was executed during authoring.

### 7.4. Testing with StepVerifier

File `src/test/java/example/PerCallDemoTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PerCallDemoTest {

    private final WebClient client = PerCallDemo.client();

    @Test
    void catalogRegistrationUsesCatalogToken() {
        StepVerifier.create(
            PerCallDemo.byRegistration(client, "catalog"))
            .expectNext("Bearer fixture-catalog")
            .verifyComplete();
    }

    @Test
    void billingRegistrationUsesBillingToken() {
        StepVerifier.create(
            PerCallDemo.byRegistration(client, "billing"))
            .expectNext("Bearer fixture-billing")
            .verifyComplete();
    }

    @Test
    void explicitAuthorizedClientIsUsedForThisCall() {
        StepVerifier.create(
            PerCallDemo.byClient(client,
                PerCallDemo.fixture("catalog", "fixture-explicit")))
            .expectNext("Bearer fixture-explicit")
            .verifyComplete();
    }

    @Test
    void missingChoiceDoesNotSendBearer() {
        StepVerifier.create(
            PerCallDemo.withoutChoice(client))
            .expectNext("(no-token)")
            .verifyComplete();
    }

    @Test
    void oneCallDoesNotChangeGlobalDefault() {
        StepVerifier.create(
            PerCallDemo.byRegistration(client, "catalog")
                .then(PerCallDemo.byRegistration(
                    client, "billing"))
                .then(PerCallDemo.withoutChoice(client)))
            .expectNext("(no-token)")
            .verifyComplete();
    }

    @Test
    void concurrentCallsKeepSeparateTokens() {
        StepVerifier.create(
            PerCallDemo.byRegistration(client, "catalog")
                .zipWith(
                    PerCallDemo.byRegistration(client, "billing")))
            .assertNext(pair -> {
                assertEquals("Bearer fixture-catalog", pair.getT1());
                assertEquals("Bearer fixture-billing", pair.getT2());
            })
            .verifyComplete();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Expect **6 passing tests** with matching dependencies and toolchain; **actually run them** to verify in your own environment. These tests do not prove an IdP issues real tokens, refreshes properly, or that the resource server validates scopes/audience. Those require integration tests with a mock or real IdP and resource server.

**Never copy `fakeTransport` into production:** It echoes the `Authorization` header in the response purely to test fake tokens. With real credentials, never log or echo tokens.

## 8. Real-World Configuration with Multiple Registrations

Example YAML for a WebFlux Spring Boot app:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          catalog-client:
            provider: corp
            client-id: ${CATALOG_CLIENT_ID}
            client-secret: ${CATALOG_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: catalog.read
          billing-client:
            provider: corp
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: billing.read
        provider:
          corp:
            token-uri: https://idp.example.test/oauth2/token
~~~

The `${...}` environment variables must be supplied at deployment; never commit secrets to the repository. `idp.example.test` is an example domain; use your provider's real token endpoint with TLS. This is a **`client_credentials`** sample; if user tokens (`authorization_code`) are needed, configure grant/redirect/scopes and login/consent separately.

### 8.1. WebClient Filter Without Defaults Enabled

~~~java
@Configuration
public class OAuth2WebClientConfig {

    @Bean
    WebClient oauthWebClient(
        WebClient.Builder builder,
        ReactiveOAuth2AuthorizedClientManager manager) {

        var filter =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager);

        // Do not call setDefaultOAuth2AuthorizedClient(true).
        // Do not setDefaultClientRegistrationId on a shared WebClient.
        return builder.filter(filter).build();
    }
}
~~~

This is an illustrative class requiring imports. Spring Security reactive 6.5 can provide a default manager if no custom bean exists; when multiple managers exist, wire injection explicitly with bean names/`@Qualifier`.

Each business operation specifies its client:

~~~java
Mono<String> catalog(WebClient oauthWebClient) {
    return oauthWebClient.get()
        .uri("https://catalog-api.example.test/v1/items")
        .attributes(clientRegistrationId("catalog-client"))
        .retrieve().bodyToMono(String.class);
}

Mono<String> billing(WebClient oauthWebClient) {
    return oauthWebClient.get()
        .uri("https://billing-api.example.test/v1/invoices")
        .attributes(clientRegistrationId("billing-client"))
        .retrieve().bodyToMono(String.class);
}
~~~

For background `client_credentials`, remember the manager is paired with a service-level store and principal. This snippet does not turn a web-request manager configuration into a background manager.

### 8.2. Two Implicit Defaults to Weigh Carefully

~~~java
// Warning: use only when WebClient is already restricted to one trusted destination.
filter.setDefaultOAuth2AuthorizedClient(true);

filter.setDefaultClientRegistrationId("catalog-client");
~~~

- `setDefaultOAuth2AuthorizedClient(true)` can select the authorized client associated with the current OAuth2 Authentication and attach tokens to requests lacking an explicit choice.
- `setDefaultClientRegistrationId("catalog-client")` sets a default registration.
- The two setters mean different things; **enabling both is not required**.
- On a shared WebClient calling multiple APIs or accepting arbitrary URLs, defaults can leak Bearer tokens to the wrong host.

Safer approach: **disable implicit defaults**, select attributes per call, and restrict base URLs and redirect destinations. If a default is truly necessary, build a dedicated `WebClient` pointing strictly to **one trusted origin**, backed by tests proving no credential leaks.

## 9. Resource Server 401/403, Token Refresh, and Filter Constructors

The authorized client manager can:

- Load a saved token by `registrationId` and principal.
- Request a token when an appropriate provider is present.
- Refresh/renew when the access token is expired/near-expiry and the grant/refresh token supports it.
- Save the new authorized client or remove on failure per policy.
- Return empty or error when the flow is unsupported or the IdP errors.

### 9.1. Two Constructors with Different Failure Behavior

| `ServerOAuth2AuthorizedClientExchangeFilterFunction` Constructor | Downstream Error Response Handling |
|---|---|
| Takes `ReactiveClientRegistrationRepository` + `ServerOAuth2AuthorizedClientRepository` | Can come preconfigured with `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` for certain OAuth2 error codes. |
| Takes `ReactiveOAuth2AuthorizedClientManager` | Does **not** automatically configure a handler for downstream HTTP 401/403. To remove cached invalid tokens, call `setAuthorizationFailureHandler(...)` matching the store. |

**Do not claim every 401 triggers a refresh or every 403 deletes the cache.** Inspect the Bearer error code and removal policy. Abusing retries can create token-issuance loops, overload the IdP, and mask authorization bugs.

| Downstream Response | Common Cause | Handling |
|---|---|---|
| 401 + `invalid_token` | Token expired/revoked/invalid | Controlled refresh/re-authorize, remove cached invalid token per policy |
| 403 + `insufficient_scope` | Valid token lacking scope/role | Review registration scopes/consent/permissions; never retry infinitely |
| 401 due to wrong `aud`/`iss` | Token issued for another audience/provider | Fix registration/token request/resource mapping |
| 429 | Rate limiting | Bounded backoff |
| 5xx | Downstream failure | Retry only if idempotent, with timeout/circuit breaker |

### 9.2. An Explicit Object Does Not Guarantee an Immutable Token

Passing `oauth2AuthorizedClient(client)` selects the **current authorized client**; the manager can still refresh the token if configured. The offline test in section 7 uses tokens valid until 2099 so it focuses on measuring selection mechanics rather than refresh.

## 10. Security Boundaries

### 10.1. Browser CSRF Differs from Outbound OAuth2

If the application uses session cookies, inbound POST/PUT/DELETE APIs from the browser still need **CSRF protection** depending on the threat model. Selecting `clientRegistrationId` on outbound calls **does not replace** CSRF tokens or Origin/SameSite policies.

`state`/PKCE in OAuth2 login callbacks also does not replace CSRF protection for post-login business actions. Never disable CSRF app-wide simply because OAuth2 Client is used.

### 10.2. Bearer Tokens and SSRF

A token sent over HTTPS to an **attacker's host** is still compromised. Enforce hostname allowlists, DNS/redirect controls, and egress policies. Never let request input choose URIs and registrations arbitrarily.

Token audience and scopes must also be validated: sharing one Authorization Server does not mean every service trusts every token.

### 10.3. Never Blindly Relay Inbound Tokens

An access token issued for API A is not automatically valid for API B. When delegation or token exchange is required, use the appropriate flow instead of copying the raw `Authorization` header to every downstream service. An OIDC **ID Token** does not replace an access token for resource APIs.

### 10.4. Service Credentials Do Not Authorize Callers

Before the backend uses `billing-client` to call a privileged API, verify caller/tenant/business authorization. Never use a service token to bypass user permissions.

## 11. Common Mistakes

**1. Confusing `registrationId` with the IdP client ID.** Use Spring's config key.

**2. Adding the OAuth2 WebClient filter and expecting every request to carry a token.** Set per-call attributes or explicit policy-governed defaults.

**3. Using global defaults on a multi-purpose WebClient.** Can send tokens to unintended external URLs.

**4. Mutating global defaults between concurrent calls.** Causes race conditions; pass via request attributes.

**5. Looking up an authorized client by registration alone without principal.** Can hand Alice's token to Bob.

**6. Holding `OAuth2AuthorizedClient` in a singleton field.** Leaks the previous user's object to the next user.

**7. Using a service credential instead of a user credential when consent is missing.** Creates a confused deputy.

**8. Using the web-request manager in a background job.** Use the `ReactiveOAuth2AuthorizedClientService`-backed manager.

**9. Letting users pick raw target URLs and registrations.** Causes SSRF/Bearer exfiltration; enforce server-side allowlists.

**10. Calling `block()`/`subscribe()` inside the event loop.** Breaks reactive properties and context; return the `Publisher`.

**11. Assuming an `OAuth2AuthorizedClient` guarantees Resource Server acceptance.** Downstream still verifies audience/scope/issuer.

**12. Thinking an explicit client object's token can never refresh.** The manager can still re-authorize/refresh.

**13. Assuming downstream 401 always evicts the cached token.** The manager constructor does not auto-install the failure handler.

**14. Retrying `403 insufficient_scope` infinitely.** Missing scopes/policies cannot be fixed by retries.

**15. Using `ServletOAuth2AuthorizedClientExchangeFilterFunction` in WebFlux.** Wrong API stack.

**16. Confusing outbound OAuth2 Client with inbound Resource Server.** Two distinct roles.

**17. Logging Authorization/refresh tokens or returning them to the frontend.** Bearer tokens are credentials.

**18. Constructing an `AuthorizedClient` from a client-supplied raw string.** Bypasses OAuth2 validation.

**19. Failing to test calls with no attribute.** Can miss default token leaks.

**20. Failing to check principal/context in background jobs.** Can misuse user tokens or fail to locate authorized clients.

## 12. Pre-Deployment Checklist

1. Are registrations configured with exact client IDs, provider/token URIs, grants, and scopes?
2. Does every outbound call select a registration ID or authorized client **explicitly**?
3. Are destination URLs trusted hosts with allowlists, TLS, and redirect constraints?
4. Is the caller authorized to trigger the operation using that token?
5. Do user-delegated clients have accurate `principalName` values isolated across tenants?
6. Does background `client_credentials` use the service-level manager and stable principal?
7. Does the manager have providers supporting grants and token refresh?
8. Are global defaults disabled on any `WebClient` shared across hosts?
9. Do the OAuth2 filter constructor and failure handler handle 401/403 consistently with the cache store?
10. Is there zero fallback from user tokens to service/admin tokens?
11. Are `block()`/`subscribe()` absent from the WebFlux request pipeline?
12. Are Bearer tokens, client secrets, and refresh tokens kept out of logs and responses?
13. Are there tests for A/B registrations, explicit clients, missing attributes, and concurrent calls?
14. Are there real/mocked IdP integration tests for issuance, refresh, revocation, and expiry?
15. Does the Resource Server verify token issuer/audience/scope and business authorization?
16. Are inbound browser requests still protected by CSRF?
17. Is there a cleanup policy for user `OAuth2AuthorizedClient` records upon logout/revocation?
18. Whenever a new downstream is added, does the operations->registration/host policy undergo security review?

## 13. Self-Check with Answers

**1.** Does `clientRegistrationId("catalog-client")` pass the IdP's client ID?

**Answer:** No, it passes Spring's registration key; the manager uses it to locate metadata and the authorized client.

**2.** When you already hold the right user's `AuthorizedClient`, which API do you use?

**Answer:** `.attributes(oauth2AuthorizedClient(client))`, letting the filter attach the token.

**3.** Can one `WebClient` be shared for Catalog and Billing?

**Answer:** Yes. Select attributes per request without mutating global defaults.

**4.** Why does `registrationId` alone fail to uniquely identify Alice's token?

**Answer:** Authorized clients bind registration **and `principalName`**; Bob can have a separate object under the same registration.

**5.** With no web request in a scheduled job, which manager do you use?

**Answer:** `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` with a stable service principal.

**6.** Why is `setDefaultOAuth2AuthorizedClient(true)` dangerous?

**Answer:** A shared `WebClient` can attach tokens to unspecified outbound calls, including wrong hosts.

**7.** If the Resource Server returns `403 insufficient_scope`, should you keep retrying until it succeeds?

**Answer:** No. Fix scopes/consent/authorization rather than blindly retrying.

**8.** What do the offline tests in section 7 verify?

**Answer:** They verify the filter's per-request token selection using token fixtures; they do **not** prove IdP token flows, token refresh, or downstream JWT validation.

**9.** Does OAuth2 Client automatically validate inbound Bearer tokens?

**Answer:** No. Separate Resource Server configuration is needed if the app exposes token-protected APIs.

**10.** If an outbound URI uses HTTPS yet comes from user input, is it safe to send a token?

**Answer:** Not yet. HTTPS protects transit to that host, not whether the host is trustworthy. Allowlists and SSRF defenses are still required.

## Official Documentation

- Spring Security 6.5 — Reactive OAuth2 Authorized Clients (per-call attributes): https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html
- Spring Security 6.5 — Reactive OAuth2 Client WebClient Integration: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security — Reactive OAuth2 Core Interfaces and Managers: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html
- `ServerOAuth2AuthorizedClientExchangeFilterFunction` Javadoc, constructor-specific failure handling: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- `OAuth2AuthorizeRequest` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizeRequest.html
- `@RegisteredOAuth2AuthorizedClient` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/annotation/RegisteredOAuth2AuthorizedClient.html
- Spring Security — Reactive OAuth2 Client testing: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- RFC 6750 — Bearer Tokens: https://www.rfc-editor.org/rfc/rfc6750
