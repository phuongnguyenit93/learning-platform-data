# Relaying Bearer Tokens with WebClient and Controlling Trust Boundaries in Spring Security WebFlux

## Lesson Objectives

This lesson belongs to the **Spring Security – reactive** module, topic **Resource Server Opaque**. After completing it, you can:

1. Accurately describe the request flow from a client to Spring WebFlux Resource Server A, through OAuth2 Token Introspection, and onward to downstream Resource Server B via `WebClient`.
2. Know when it is appropriate to **relay the verified Bearer token**, and when to use **OAuth2 Token Exchange / on-behalf-of** or a separate token via `client_credentials`.
3. Use `ServerBearerExchangeFilterFunction` in reactive `WebClient`, understanding that it reads the token credential from `Authentication` in the Reactor Context and does not refresh tokens itself.
4. Design a **dedicated WebClient per trusted upstream**; never attach the token-relay filter to a general-purpose WebClient for arbitrary URLs, and never accept absolute URLs from clients.
5. Protect trust boundaries: scheme/host/path allowlists, HTTPS/mTLS, redirect policies, DNS/egress, SSRF prevention, audience/scope, token secrecy, correlation IDs, and failure handling.
6. Build a Spring Boot 3.x / Java 17+ demo with `ReactiveOpaqueTokenIntrospector`, `SecurityWebFilterChain`, a relaying WebClient, and a non-relaying WebClient, then test with `WebTestClient`/`MockWebServer`/`StepVerifier`.
7. Distinguish HTTP 401/403 of **caller -> A** from **B** rejecting a token; prevent token leaks in logs, redirects, exception bodies, and tracing.
8. Understand why token relay neither creates extra permissions nor replaces downstream independent authentication and authorization.

> **Applicable versions:** Spring Security 6.5.x (reactive) on Java 17+ / Spring Boot 3.5.16 for an easily reproducible example. Spring Boot 3.5.16 is the final OSS release of the 3.5 branch; for new deployments, prefer a currently supported line with security patches. Code snippets outside the runnable project are clearly marked as fragments.

---

## 1. Business Scenario

A frontend holds an access token `reader-token` issued by the Authorization Server and calls:

```http
GET /api/relay/profile HTTP/1.1
Host: api-edge.example.test
Authorization: Bearer reader-token
```

API A is a **Spring Security WebFlux Resource Server using opaque token introspection**. A must call service B to fetch the profile:

```text
                    Authentication boundary                 Trust boundary
                     (client -> A)                            (A -> B)
                           |                                     |
Frontend                   v                                     v
  |
  | Authorization: Bearer <opaque-token>
  v
+-----------------------------+              +-------------------------------+
| Resource Server A           |              | Resource Server B             |
| Spring WebFlux              |              | profile-service               |
|                             |              |                               |
| 1. Token Introspection      |              | 5. Verify Bearer token        |
| 2. Authentication           |              | 6. Check aud/scope/ACL        |
| 3. Authorization            |              | 7. Return profile if valid    |
| 4. WebClient relay          |------------->|                               |
+-----------------------------+              +-------------------------------+
             |   ^                                          ^
             |   |                                          |
             v   |                                          |
      Authorization Server                             (May re-introspect
      POST /introspect                                 or verify separately)
      active, aud, scope, sub
```

A must not grab the raw HTTP `Authorization` header and forward it immediately. The proper sequence is:

1. A receives the Bearer token through the WebFlux Security chain.
2. `ReactiveOpaqueTokenIntrospector` queries the **trusted Authorization Server** for `active` status and scope/audience metadata.
3. A authenticates the identity/subject and enforces rules on `/api/relay/profile`.
4. Within the authorized request, a **dedicated WebClient** reads the token credential from `Authentication` in the Reactor Context.
5. A sends the token to **allowlisted B** over HTTPS.
6. B **independently** verifies the token and checks its own audience and permissions; A allowing the request does not mean B must allow it.
7. A returns a curated business response without echoing the token or request credentials.

**A Bearer token is a credential:** anyone holding the token string can use it within the token's permissions. Forwarding to the wrong host, logging it, or following unsafe redirects can leak authority equivalent to exposing a temporary password.

## 2. How Does an Opaque Resource Server Authenticate Inbound Tokens?

In Spring Security WebFlux:

```text
Incoming Authorization: Bearer TOKEN
          |
          v
ServerBearerTokenAuthenticationConverter
          |
          v
Opaque-token authentication
          |
          v
ReactiveOpaqueTokenIntrospector.introspect(TOKEN)
          |
          v
Authorization Server RFC 7662
          |
          +-- active=false / token invalid -> 401; no principal created
          |
          +-- active=true, sub, aud, scope, exp...
                    |
                    v
             OAuth2AuthenticatedPrincipal
                    |
                    v
             BearerTokenAuthentication
             - Principal: introspection attributes
             - Credentials: OAuth2AccessToken
             - Authorities: SCOPE_profile.read ...
                    |
                    v
             Reactor SecurityContext
                    |
                    v
             HTTP authorization + controller
```

**Critical boundary:** a token passing introspection at A **only** proves the Authorization Server accepted the token under A's policy. The token may still be disallowed at B due to a different audience, missing scope, or mismatched resource-owner/tenant.

Example introspection JSON:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "profile.read",
  "aud": ["api://relay-edge", "api://profile-service"],
  "client_id": "web-portal",
  "exp": 1799999999
}
```

In this example, the audience is explicitly issued for **both A and B** to illustrate when relaying a single token is permitted by the Authorization Server contract. Not all providers support multi-audience tokens. If B only accepts `api://profile-service` while the token carries only `aud=api://relay-edge`, B **must reject** the token even though A admitted the caller.

By default, each scope maps to authority `SCOPE_<scope>`, e.g., `scope: "profile.read"` yields `SCOPE_profile.read`. Endpoint A checks `hasAuthority("SCOPE_profile.read")`; B may require additional permissions under its own contract.

### Opaque Token Does Not Mean A Can Read Claims from the Token String

With an opaque token, the string `reader-token` is purely an identifier/credential. Do not split by dots, do not decode it yourself, and do not trust `scope` values added by the caller via headers or query parameters. Permissions must come from a trusted introspection server or verified authorization service.

## 3. What Is ServerBearerExchangeFilterFunction?

Spring Security provides a dedicated filter for **reactive token relay**:

```java
import org.springframework.security.oauth2.server.resource.web
        .reactive.function.client.ServerBearerExchangeFilterFunction;
```

Basic usage:

```java
@Bean
WebClient downstreamWebClient() {
    return WebClient.builder()
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
}
```

When the downstream `WebClient` executes a request inside a **Reactor Context containing an Authentication** whose credentials are an `AbstractOAuth2Token`, the filter extracts the token value and adds `Authorization: Bearer ...` to the outbound request. In a default Opaque Resource Server, the authentication is typically `BearerTokenAuthentication` holding an OAuth2 token credential.

**Five things to remember:**

1. The filter **does not authenticate the inbound token**: that is the job of A's WebFlux Security chain.
2. The filter **does not check audience/scope for B**: that belongs to the A-B contract and Resource Server B.
3. The filter **does not refresh expired tokens**. It relays the current token, unlike an OAuth2 Client using `ReactiveOAuth2AuthorizedClientManager`.
4. The filter does not create or enforce hostname/URL allowlists. **Every request sent by a WebClient carrying this filter can attach the token** whenever an eligible Authentication is present.
5. The filter reads the token from the **Reactor SecurityContext**; if you lose context or run outside an HTTP request, it normally finds no credential to attach.

### Not a Servlet Filter

| Stack | Class | Context Source |
| --- | --- | --- |
| WebFlux reactive | `ServerBearerExchangeFilterFunction` | Reactor SecurityContext |
| Servlet | `ServletBearerExchangeFilterFunction` | Servlet/ThreadLocal SecurityContext |
| OAuth2 Client token acquisition | `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Authorized client manager, registration/principal |
| WebFlux Resource Server inbound | `ServerHttpSecurity.oauth2ResourceServer(...).opaqueToken(...)` | Bearer auth + introspection |

Never copy Servlet `SecurityFilterChain`/`HttpSecurity` examples into WebFlux, and never call `.block()` on the Netty event loop to fetch authentication or tokens.

## 4. Token Relay, client_credentials, and Token Exchange: When to Use Which?

Three common strategies:

| Strategy | Bearer Sent to B | When Appropriate | Key Risk |
| --- | --- | --- | --- |
| **Token relay** | Same token the caller sent to A | Token was issued by IdP with valid audience/scopes for B and B accepts this delegation | Over-scoped tokens, multi-hop exposure |
| **OAuth2 Token Exchange** (RFC 8693) | New token issued by IdP for B on behalf of caller | B requires its own audience/scopes or privilege downscoping per hop | Requires IdP exchange support and mapping policy |
| **client_credentials** | A's own service-identity token | B performs a system task, not on behalf of an end user | Confused deputy if a service token executes actions unauthorized for the user |

**Example 1 — Valid relay:** APIs A and B are both Resource Servers in the same trust domain, the Authorization Server issues a token with `aud=["api://relay-edge","api://profile-service"]` and proper scopes, and both validate independently. A may relay to a predefined endpoint without letting users pick B arbitrarily.

**Example 2 — Token exchange required:** The inbound token has only `aud=api://relay-edge`. B requires `aud=api://profile-service`. Never remove audience validation at B to "make relay work"; use Token Exchange / delegated authorization to obtain a fresh token scoped for B (if supported by the IdP).

**Example 3 — App-to-app:** A runs a system aggregation job with no user request. `ServerBearerExchangeFilterFunction` will have no user bearer credential. Use an OAuth2 Client service manager to obtain `client_credentials` for A, and let B authorize by service principal/scopes.

### Invariant of the "On Behalf of User" Model

Alice's token **must never** be used for Bob, even when both requests run in the same instance. Never store user tokens in singleton fields, shared static caches, reactive-incompatible `ThreadLocal`s, principal-less Redis keys, or default headers on a global `WebClient`. Tokens must come strictly from **the current request's subscription/context** and be sent only to authorized upstreams.

## 5. Trust Boundary: The Destination Matters as Much as the Token

### Why Is a General-Purpose WebClient Dangerous?

The following configuration is **unsafe** if the `WebClient` is reused for arbitrary URLs:

```java
// Anti-pattern: every URL called through this client may receive the bearer token.
@Bean
WebClient generalPurposeClient() {
    return WebClient.builder()
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
}
```

Another leak-prone example:

```java
// Anti-pattern: user controls the absolute outbound URL.
return generalPurposeClient.get()
        .uri(userProvidedUrl)
        .retrieve()
        .bodyToMono(String.class);
```

If `userProvidedUrl` points to an attacker host or an internal metadata IP, the token can be sent over the network to an untrusted party (SSRF and token exfiltration). Do not "fix" this merely by checking whether the URL string contains `example.test`; URL parsers, DNS, redirects, IPv4/IPv6 literals, userinfo, and encoding offer many bypasses.

**Solution:** configure a Bearer-relaying `WebClient` **solely for one trusted upstream**, reading the base URL from operational config, using fixed paths in code, never passing user-supplied absolute URIs, disabling redirects, and enforcing network egress and TLS controls.

### Required Production Controls

1. `https://` with certificate/hostname verification, or service-to-service mTLS; never use `trustAll` or disable TLS.
2. B's hostname, scheme, port, and path prefix belong to a **trusted allowlist** configured at deployment, never taken directly from requests, cookies, or headers.
3. Cluster/service-mesh/firewall egress rules allow A to call only B; in-code URI checks alone do not stop DNS rebinding or service-discovery abuse.
4. **Never auto-follow 30x redirects** on requests carrying Bearer tokens, especially redirects to another host or scheme. Distinguish HTTP 302 from business errors.
5. Maintain two separate WebClients: a token-relaying WebClient and a public WebClient **without** token relay.
6. Never log `Authorization` headers, token strings, URL queries containing tokens, or raw exceptions carrying credentials.
7. B independently introspects/verifies the token, validates B's own audience and scopes, and checks owner/tenant/resource permissions.
8. Configure timeouts, backpressure, response body limits, and cancellation; avoid infinite retries or automatic retries on unsafe POSTs.
9. Never blindly echo downstream `WWW-Authenticate` or sensitive response headers to callers where token details could leak.
10. Responses from A must not be publicly cached if identity-dependent; check cache keys, `Cache-Control`, and privacy policies.

## 6. Reactor SecurityContext and Reactive Rules

In WebFlux, `Authentication` lives in the **Reactor Context**, not in a traditional `ThreadLocal`.

```java
// Fragment reading Authentication when extra policy checks are needed:
return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .flatMap(authentication -> validatePolicy(authentication));
```

Here `validatePolicy(...)` is an application method you define yourself; this fragment does not run standalone.

**Right way:** return the entire `Mono` or `Flux` from the controller/service so Spring WebFlux subscribes and carries the security context along the reactive pipeline.

```java
@GetMapping("/api/relay/profile")
public Mono<String> profile() {
    return service.profile();  // Reactor Context is preserved in the pipeline
}
```

**Wrong way:**

```java
// Anti-pattern: uncomposed side effect; errors and context are hard to manage.
webClient.get().uri("/internal/profile")
        .retrieve().bodyToMono(String.class)
        .subscribe();
return Mono.just("done");
```

Never use `Thread.sleep`, `block()`, blocking JDBC calls, or a `Runnable` outside the Reactor Context to "fetch a token." For background jobs, use machine tokens/`client_credentials` rather than borrowing an arbitrary request's token.

### When the Filter Encounters an Existing Authorization Header

Per Spring Security docs, if you explicitly set `headers.setBearerAuth(otherToken)` on an outbound call, the bearer relay filter leaves your explicitly set token intact. That **does not** make an arbitrarily chosen token safe. If the app needs another token, use OAuth2 Client / token exchange with clear client, audience, and permission controls.

---

## 7. Hands-On Java 17+ / Spring Boot 3.5.16 Project

Demo goals:

- A is a **WebFlux Opaque Resource Server**: receives Bearer tokens and calls the introspection server per Spring Security.
- A validates audience `api://relay-edge` and scope `profile.read`.
- A calls B via a **dedicated WebClient** with `ServerBearerExchangeFilterFunction`. The upstream URL comes from server config with fixed paths.
- A has a second WebClient to call B's public endpoint **without relaying tokens**.
- A disables redirect following on WebClients and safely translates non-2xx responses into errors.
- Tests use **MockWebServer** to simulate the IdP and B, plus a capture server to detect if tokens ever leak across redirects.
- Tests use loopback HTTP and dummy tokens; this is a **flow integration test**, not proof of production HTTPS/certs or B's production security policy.

### 7.1. Structure

```text
opaque-relay-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/relayload/
        OpaqueRelayApplication.java
        SecurityConfiguration.java
        DownstreamWebClientConfiguration.java
        DownstreamRelayService.java
        RelayController.java
      resources/
        application.yml
    test/
      java/example/relayload/
        OpaqueRelayIntegrationTest.java
```

The package is `example.relayload` across **all files**. Do not rename packages or individual classes inconsistently when copying.

### 7.2. Gradle

**`settings.gradle`**

```groovy
rootProject.name = 'opaque-relay-lab'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot's WebFlux starter brings in Reactor Netty and `WebClient`. The Resource Server starter brings in Bearer/opaque introspection components. `MockWebServer` is a test dependency; never deploy it with the app.

Requires JDK 17+ and a compatible Gradle Wrapper or pre-installed Gradle. If your project uses an organization-managed BOM, choose a currently supported patch release instead of keeping the lesson's pinned baseline.

### 7.3. application.yml

**`src/main/resources/application.yml`**

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: opaque-relay-lab
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${INTROSPECTION_URI:https://idp.example.invalid/oauth2/introspect}
          client-id: ${INTROSPECTION_CLIENT_ID:relay-resource-server}
          client-secret: ${INTROSPECTION_CLIENT_SECRET:local-demo-only}

downstream:
  profile-base-url: ${PROFILE_BASE_URL:https://profile.example.invalid}
  allow-insecure-loopback-for-tests: false
```

Explanation:

- API A binds to loopback only for a **single-machine learning setup**. Production behind containers/network policies needs dedicated listener config without accidentally exposing backends.
- `opaquetoken.introspection-uri` is the RFC 7662 endpoint, not the OAuth2 token endpoint.
- Client ID/secret authenticate A to the introspection endpoint; they are **not** the user's Bearer token—never commit real credentials to Git.
- `profile-base-url` is **server-owned trusted configuration**, never read from query parameters.
- `allow-insecure-loopback-for-tests: false` by default; integration tests override it to true solely for MockWebServer HTTP on `127.0.0.1`. Never permit sending tokens over plain HTTP to the Internet.
- `.invalid` addresses are dummy documentation placeholders; `bootRun` cannot reach real endpoints until a proper IdP and upstream are configured.

### 7.4. Main Class

**`src/main/java/example/relayload/OpaqueRelayApplication.java`**

```java
package example.relayload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueRelayApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpaqueRelayApplication.class, args);
    }
}
```

### 7.5. Resource Server Security: Validating Audience and Scope

**`src/main/java/example/relayload/SecurityConfiguration.java`**

```java
package example.relayload;

import java.util.Collection;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    private static final String EDGE_AUDIENCE = "api://relay-edge";

    @Bean
    ReactiveOpaqueTokenIntrospector introspector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
                    String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
                    String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
                    String clientSecret) {

        ReactiveOpaqueTokenIntrospector delegate =
                SpringReactiveOpaqueTokenIntrospector
                        .withIntrospectionUri(uri)
                        .clientId(clientId)
                        .clientSecret(clientSecret)
                        .build();

        return token -> delegate.introspect(token)
                .flatMap(principal -> {
                    Object aud = principal.getAttribute("aud");
                    if (!hasAudience(aud, EDGE_AUDIENCE)) {
                        return Mono.error(new OAuth2AuthenticationException(
                                new OAuth2Error("invalid_token",
                                        "Token not issued for relay edge", null)));
                    }
                    return Mono.just(principal);
                });
    }

    private static boolean hasAudience(Object aud, String expected) {
        if (aud instanceof String value) {
            return expected.equals(value);
        }
        if (aud instanceof Collection<?> values) {
            return values.contains(expected);
        }
        return false;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/api/public/ping",
                                "/api/public/downstream-check")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/relay/**")
                            .hasAuthority("SCOPE_profile.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(resource -> resource
                        .opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
```

This is **reactive** Spring Security; do not use `HttpSecurity` or Servlet `OpaqueTokenIntrospector`.

**Why check audience?** Spring OAuth2 opaque introspection verifies `active` and maps scope authorities by default; never assume it automatically checks your application's specific audience. The decorator above admits only tokens whose `aud` includes `api://relay-edge` into A. Inactive tokens are rejected by the delegate **before** the mapper callback.

**Why enforce a scope rule?** An active token with the right audience yet holding only `scope=profile.write` still receives HTTP 403 at A when calling `/api/relay/profile`. This avoids forwarding tokens lacking read permission to B just for B to reject them.

**Note:** B must still validate **B's own audience**. The code above only shows A validating A's audience.

### 7.6. Separating Token-Relaying WebClient from Public WebClient

**`src/main/java/example/relayload/DownstreamWebClientConfiguration.java`**

```java
package example.relayload;

import java.net.URI;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.server.resource.web.reactive
        .function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class DownstreamWebClientConfiguration {

    private static URI validatedBase(
            String raw, boolean allowInsecureLoopbackForTests) {

        URI uri = URI.create(raw);

        boolean https = "https".equalsIgnoreCase(uri.getScheme());
        boolean localTest = allowInsecureLoopbackForTests
                && "http".equalsIgnoreCase(uri.getScheme())
                && "127.0.0.1".equals(uri.getHost());

        if (!(https || localTest)
                || uri.getHost() == null
                || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || (uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty()
                    && !"/".equals(uri.getRawPath()))) {
            throw new IllegalArgumentException(
                    "Profile upstream base URL is not allowed");
        }
        return uri;
    }

    private static ReactorClientHttpConnector connector() {
        HttpClient client = HttpClient.create()
                .followRedirect(false)
                .responseTimeout(Duration.ofSeconds(5));

        return new ReactorClientHttpConnector(client);
    }

    @Bean("profileRelayWebClient")
    WebClient profileRelayWebClient(
            @Value("${downstream.profile-base-url}") String rawBaseUrl,
            @Value("${downstream.allow-insecure-loopback-for-tests:false}")
                    boolean allowTestHttp) {

        URI base = validatedBase(rawBaseUrl, allowTestHttp);

        // Use this WebClient ONLY for the trusted profile service.
        return WebClient.builder()
                .baseUrl(base.toString())
                .clientConnector(connector())
                .filter(new ServerBearerExchangeFilterFunction())
                .build();
    }

    @Bean("publicWebClient")
    WebClient publicWebClient(
            @Value("${downstream.profile-base-url}") String rawBaseUrl,
            @Value("${downstream.allow-insecure-loopback-for-tests:false}")
                    boolean allowTestHttp) {

        URI base = validatedBase(rawBaseUrl, allowTestHttp);

        // No ServerBearerExchangeFilterFunction on this client.
        return WebClient.builder()
                .baseUrl(base.toString())
                .clientConnector(connector())
                .build();
    }
}
```

**Points to evaluate:**

- `profile-base-url` is **ops-owned configuration**. `validatedBase` checks scheme, userinfo, query, and fragment, requiring the base URL at host root; test-only HTTP is restricted to loopback and requires an explicit flag.
- `followRedirect(false)` is a defensive measure: a `302 Location: ...` response must never automatically forward credentials to another host.
- `responseTimeout(5s)` bounds response wait time. Production also needs connect timeouts, DNS policies, backpressure, body size limits, and explicit retry policies.
- A `WebClient` with `baseUrl` **does not by itself block absolute `.uri(...)` calls**. Therefore, the service below calls only **fixed constant paths**. Never expose this `WebClient` via an endpoint accepting arbitrary URLs.
- A valid host URL at startup does not prevent DNS rebinding or misconfigured proxy networks. **Enforce egress firewall/service-mesh allowlists**, workload identity, and TLS/mTLS.
- `publicWebClient` has no Bearer filter and is used for public requests. Never accidentally use `profileRelayWebClient` to call analytics, image fetches, webhooks, or third parties.
- Production can dedicate a `WebClient` to profile-service and add certificate pinning/mTLS per infrastructure, without ever disabling TLS hostname validation to work around handshake errors.
- Both beans are explicitly named to prevent accidental mis-injection.

### 7.7. Service Calling Downstream with Fixed Paths, No Auto-Redirects

**`src/main/java/example/relayload/DownstreamRelayService.java`**

```java
package example.relayload;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
public class DownstreamRelayService {

    private final WebClient relayClient;
    private final WebClient publicClient;

    public DownstreamRelayService(
            @Qualifier("profileRelayWebClient") WebClient relayClient,
            @Qualifier("publicWebClient") WebClient publicClient) {
        this.relayClient = relayClient;
        this.publicClient = publicClient;
    }

    public Mono<String> profile() {
        return fetch(relayClient, "/internal/profile");
    }

    public Mono<String> denied() {
        return fetch(relayClient, "/internal/denied");
    }

    public Mono<String> redirectProbe() {
        return fetch(relayClient, "/internal/redirect");
    }

    public Mono<String> publicCheck() {
        return fetch(publicClient, "/public/check");
    }

    private Mono<String> fetch(WebClient client, String fixedPath) {
        // fixedPath is determined solely by the code above, NEVER from HTTP query params.
        return client.get().uri(fixedPath)
                .exchangeToMono(this::handleResponse)
                .onErrorMap(WebClientRequestException.class,
                        error -> new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "Downstream unavailable"));
    }

    private Mono<String> handleResponse(ClientResponse response) {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(String.class)
                    .switchIfEmpty(Mono.error(
                            new ResponseStatusException(
                                    HttpStatus.BAD_GATEWAY,
                                    "Empty downstream response")));
        }

        // Includes 301/302/307/308, 401/403, and 5xx from B.
        // Never auto-follow Location or return B's sensitive error body.
        return response.releaseBody()
                .then(Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY,
                        "Downstream rejected request")));
    }
}
```

**Why does the code above map downstream failures to `502 Bad Gateway`?** It is a clean demo policy: A does not forward raw bodies or headers back to the caller, especially token-related diagnostics from B. Production may map downstream 401/403 to client 401/403 or a specific domain error code, **but must design it explicitly** so it neither triggers login/retry loops nor leaks credentials.

- `response.releaseBody()` frees the body for unused error responses.
- Never use unbounded `retry()`, especially on POSTs or side effects.
- Never grab the raw inbound HTTP `Authorization` header and call `setBearerAuth(...)` manually, as that could execute **before** the token is introspected.
- Never return `Mono.just("OK")` before the `WebClient` completes.
- When downstream endpoints or policies change, update config/code via review rather than taking URLs from users for "flexibility."

### 7.8. Controller

**`src/main/java/example/relayload/RelayController.java`**

```java
package example.relayload;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class RelayController {

    private final DownstreamRelayService downstream;

    public RelayController(DownstreamRelayService downstream) {
        this.downstream = downstream;
    }

    @GetMapping("/api/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/public/downstream-check")
    public Mono<String> publicDownstreamCheck() {
        return downstream.publicCheck();
    }

    @GetMapping("/api/relay/profile")
    public Mono<String> profile() {
        return downstream.profile();
    }

    @GetMapping("/api/relay/denied")
    public Mono<String> denied() {
        return downstream.denied();
    }

    @GetMapping("/api/relay/redirect")
    public Mono<String> redirectProbe() {
        return downstream.redirectProbe();
    }
}
```

The controller returns only data supplied by service B or safe errors, **never returning raw Bearer tokens**. Spring Security enforces `SCOPE_profile.read` before admitting requests into `/api/relay/**`. There is no endpoint letting callers specify `uri=...` or `host=...`.

---

## 8. WebTestClient and MockWebServer Integration Tests

Tests run **embedded Reactor Netty on a random port** alongside three MockWebServers:

- `IDP`: simulates the introspection endpoint, requires Basic auth from Resource Server A, and returns active/scope/audience.
- `PROFILE`: simulates downstream B, checking the Bearer header on `GET /internal/profile`; this is **not a full Resource Server B**, because it does not perform RFC 7662 introspection itself.
- `CAPTURE`: mocks another host to detect whether `WebClient` follows redirects to an external destination.

All tokens, Basic credentials, and HTTP endpoints are **loopback test-only**. Never copy HTTP introspection or dummy secrets into production.

### 8.1. Complete Test Suite

**`src/test/java/example/relayload/OpaqueRelayIntegrationTest.java`**

```java
package example.relayload;

import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.server.ResponseStatusException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OpaqueRelayIntegrationTest {

    private static final String BASIC = "Basic " +
            Base64.getEncoder().encodeToString(
                    "relay-resource-server:test-secret"
                            .getBytes(StandardCharsets.UTF_8));

    private static final MockWebServer CAPTURE = startCapture();
    private static final MockWebServer PROFILE = startProfile();
    private static final MockWebServer IDP = startIdp();

    @DynamicPropertySource
    static void configureEndpoints(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri",
                () -> IDP.url("/introspect").toString());
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.client-id",
                () -> "relay-resource-server");
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.client-secret",
                () -> "test-secret");
        registry.add("downstream.profile-base-url",
                () -> PROFILE.url("/").toString());
        registry.add("downstream.allow-insecure-loopback-for-tests",
                () -> "true");
    }

    @LocalServerPort
    int port;

    @Autowired
    DownstreamRelayService service;

    private WebTestClient client;

    @BeforeEach
    void prepare() throws InterruptedException {
        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        // Drain recorded requests from previous tests; tests run sequentially.
        while (PROFILE.takeRequest(0, TimeUnit.MILLISECONDS) != null) {
            // drain
        }
    }

    @AfterAll
    static void shutdown() throws IOException {
        IDP.shutdown();
        PROFILE.shutdown();
        CAPTURE.shutdown();
    }

    private static MockWebServer startCapture() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static MockWebServer startProfile() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                String path = request.getPath();
                if ("/internal/profile".equals(path)) {
                    if ("Bearer reader-token".equals(
                            request.getHeader("Authorization"))) {
                        return new MockResponse()
                                .setResponseCode(200)
                                .setBody("profile-for-alice");
                    }
                    return new MockResponse()
                            .setResponseCode(401)
                            .setBody("downstream-invalid-token");
                }

                if ("/internal/denied".equals(path)) {
                    return new MockResponse()
                            .setResponseCode(401)
                            .setBody("private-upstream-diagnostic");
                }

                if ("/internal/redirect".equals(path)) {
                    return new MockResponse()
                            .setResponseCode(302)
                            .setHeader("Location",
                                    CAPTURE.url("/capture").toString());
                }

                if ("/public/check".equals(path)) {
                    boolean noAuthorization =
                            request.getHeader("Authorization") == null;
                    return new MockResponse()
                            .setResponseCode(200)
                            .setBody(noAuthorization
                                    ? "no-token-received"
                                    : "unexpected-token");
                }

                return new MockResponse().setResponseCode(404);
            }
        });
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static MockWebServer startIdp() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                if (!"POST".equals(request.getMethod())
                        || !"/introspect".equals(request.getPath())) {
                    return new MockResponse().setResponseCode(404);
                }
                if (!BASIC.equals(request.getHeader("Authorization"))) {
                    return new MockResponse().setResponseCode(401);
                }

                String body = request.getBody().readUtf8();
                String token = Arrays.stream(body.split("&"))
                        .filter(v -> v.startsWith("token="))
                        .map(v -> URLDecoder.decode(
                                v.substring(6), StandardCharsets.UTF_8))
                        .findFirst().orElse("");

                return new MockResponse()
                        .setResponseCode(200)
                        .setHeader("Content-Type", "application/json")
                        .setBody(introspectionResult(token));
            }
        });

        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static String introspectionResult(String token) {
        return switch (token) {
            case "reader-token" -> """
                {
                  "active": true,
                  "sub": "alice",
                  "scope": "profile.read",
                  "aud": ["api://relay-edge", "api://profile-service"]
                }
                """;
            case "no-scope-token" -> """
                {
                  "active": true,
                  "sub": "bob",
                  "scope": "profile.write",
                  "aud": ["api://relay-edge", "api://profile-service"]
                }
                """;
            case "wrong-audience-token" -> """
                {
                  "active": true,
                  "sub": "mallory",
                  "scope": "profile.read",
                  "aud": "api://unrelated"
                }
                """;
            default -> """
                {"active":false}
                """;
        };
    }

    @Test
    void pingIsPublic() {
        client.get().uri("/api/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void noBearerToProtectedRouteIs401() {
        client.get().uri("/api/relay/profile")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void inactiveTokenIs401() {
        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("inactive-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void tokenForWrongAudienceIs401() {
        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("wrong-audience-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validTokenWithoutRequiredScopeIs403() {
        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("no-scope-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void goodBearerIsRelayedToFixedDownstream() throws InterruptedException {
        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("profile-for-alice");

        RecordedRequest request = PROFILE.takeRequest(
                2, TimeUnit.SECONDS);
        assertNotNull(request);
        assertEquals("/internal/profile", request.getPath());
        assertEquals("Bearer reader-token",
                request.getHeader("Authorization"));
    }

    @Test
    void publicWebClientNeverRelaysEvenIfCallerIsAuthenticated()
            throws InterruptedException {
        client.get().uri("/api/public/downstream-check")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("no-token-received");

        RecordedRequest request = PROFILE.takeRequest(
                2, TimeUnit.SECONDS);
        assertNotNull(request);
        assertEquals("/public/check", request.getPath());
        assertNull(request.getHeader("Authorization"));
    }

    @Test
    void downstream401BecomesSafeGatewayError() {
        client.get().uri("/api/relay/denied")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isEqualTo(502);
    }

    @Test
    void redirectToDifferentHostIsNotFollowed() {
        int before = CAPTURE.getRequestCount();

        client.get().uri("/api/relay/redirect")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isEqualTo(502);

        // If the HTTP client auto-followed redirects, CAPTURE would increment its count.
        assertEquals(before, CAPTURE.getRequestCount());
    }

    @Test
    void rejectedScopeDoesNotCallDownstream() {
        int before = PROFILE.getRequestCount();

        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("no-scope-token"))
                .exchange()
                .expectStatus().isForbidden();

        assertEquals(before, PROFILE.getRequestCount());
    }

    @Test
    void invalidAudienceDoesNotCallDownstream() {
        int before = PROFILE.getRequestCount();

        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("wrong-audience-token"))
                .exchange()
                .expectStatus().isUnauthorized();

        assertEquals(before, PROFILE.getRequestCount());
    }

    @Test
    void outsideRequestContextNoUserBearerIsInvented()
            throws InterruptedException {
        StepVerifier.create(service.profile())
                .expectError(ResponseStatusException.class)
                .verify();

        RecordedRequest request = PROFILE.takeRequest(
                2, TimeUnit.SECONDS);
        assertNotNull(request);
        assertNull(request.getHeader("Authorization"));
    }
}
```

### 8.2. Running Tests

With the Gradle Wrapper in the project:

```bash
./gradlew test --tests example.relayload.OpaqueRelayIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.relayload.OpaqueRelayIntegrationTest
```

Or using a compatible pre-installed Gradle:

```bash
gradle test --tests example.relayload.OpaqueRelayIntegrationTest
```

**Expected result:** 12 tests PASS assuming the project, JDK 17+, dependencies, and loopback binding match the description. This is a **source-based expectation**, not an execution log from a live workspace.

### 8.3. What Was Verified in the Project?

| Test | What It Verifies |
| --- | --- |
| `pingIsPublic` | Public endpoint needs no Bearer token |
| `noBearerToProtectedRouteIs401` | Without Authentication, relay is never entered |
| `inactiveTokenIs401` | Introspection rejects inactive tokens |
| `tokenForWrongAudienceIs401` | A's audience must match |
| `validTokenWithoutRequiredScopeIs403` | Required scope must pass before outbound calls |
| `goodBearerIsRelayedToFixedDownstream` | B receives `Authorization: Bearer reader-token` at the fixed path |
| `publicWebClientNeverRelaysEvenIfCallerIsAuthenticated` | Public WebClient never relays tokens |
| `downstream401BecomesSafeGatewayError` | A never echoes B's body/`WWW-Authenticate` |
| `redirectToDifferentHostIsNotFollowed` | Outbound client refuses to follow redirects |
| `rejectedScopeDoesNotCallDownstream` | Authorization failure at A does not call B |
| `invalidAudienceDoesNotCallDownstream` | Wrong-audience tokens never reach B |
| `outsideRequestContextNoUserBearerIsInvented` | Without Reactor authentication, the filter never invents a Bearer token |

**Limitation:** Mock B compares the header against a test string rather than calling the IdP itself to verify active/scope/audience. This integration test proves **A introspects, A authorizes, A relays, and the two WebClients do not leak**; it does not prove a production Resource Server B validates properly. To verify the whole system, deploy B separately with JWT/opaque Resource Server config and run cross-service tests over real TLS.

### 8.4. Be Careful with Counters and Parallel Tests

The MockWebServers use static fields, shut down in `@AfterAll`. `@BeforeEach` drains recorded requests in `PROFILE`. The test suite is written for **JUnit's default sequential execution**; if CI enables parallel test execution, isolate MockWebServers/app contexts per test or synchronize `getRequestCount` checks to avoid races. Never run this test suite on a production network.

---

## 9. Practices Never to Use for Token Relay

### 9.1. Copying the Raw Authorization Header Immediately on Request Arrival

```java
// Anti-pattern: may forward credentials before authentication has succeeded.
String inboundAuthorization =
        exchange.getRequest().getHeaders().getFirst("Authorization");

return webClient.get().uri(userProvidedUrl)
        .header("Authorization", inboundAuthorization)
        .retrieve().bodyToMono(String.class);
```

Drawbacks:

- Easily executes before authentication succeeds or on `permitAll` endpoints.
- No audience/scope/ownership policy for B.
- `userProvidedUrl` opens SSRF and token exfiltration.
- Raw headers are often logged accidentally during debugging.
- On redirects or host mismatches, credentials can be sent to the wrong service.

**Prefer** `ServerBearerExchangeFilterFunction` after Spring Security authentication, on a dedicated outbound `WebClient` with fixed paths.

### 9.2. Using ThreadLocal SecurityContextHolder in WebFlux

```java
// Anti-pattern in reactive controllers/services:
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

Reactor can switch scheduling across threads. Traditional `ThreadLocal`-based `SecurityContextHolder` is not a reliable source for finding `Authentication` across reactive subscriptions. Use `ReactiveSecurityContextHolder` or official filters.

### 9.3. Storing Tokens in Mutable Singleton Fields

```java
// Anti-pattern: concurrent requests from Alice and Bob can mix tokens.
private String lastBearer;

void setBearer(String value) {
    this.lastBearer = value;
}
```

Never store raw user tokens in static fields, shared `WebClient` default `Authorization` headers, or caches not partitioned by principal. In a reactive app with concurrent requests, cross-user token leaks can become critical.

### 9.4. Substituting OAuth2 Client Filter for Relay Without Checking Grant Type

`ServerOAuth2AuthorizedClientExchangeFilterFunction` calls a manager to obtain/refresh an **authorized client** by registration and principal. It does not simply copy inbound `Authorization`.

If API A needs to request `client_credentials` for a job itself, choose OAuth2 Client. If B needs its own token scoped to B's audience, look into RFC 8693 Token Exchange. Never invoke the manager with a client registration picked from HTTP input and inadvertently obtain an over-privileged service-level token.

### 9.5. Skipping Audience Checks at B

Never treat A having verified a token as a reason for B to skip introspection/issuer/audience validation. A and B are **two separate trust boundaries**; downstream systems must not accept arbitrary tokens merely because the request arrived from an internal IP. In zero-trust/microservices, use workload identity/mTLS to authenticate service A, and Bearer tokens/scopes to authenticate user identity and permissions accordingly.

### 9.6. Treating CORS as Server-to-Server Authorization

CORS is a browser policy for cross-origin JavaScript; `WebClient`, cURL, and other servers are not blocked by browser CORS enforcement. An upstream is not protected merely by `Access-Control-Allow-Origin`. Authentication/authorization and trusted network policies are the real controls.

---

## 10. How to Prevent Bearer Token Leakage via Redirects?

Suppose a downstream service returns:

```http
HTTP/1.1 302 Found
Location: https://some-other.example.invalid/collect
```

If the HTTP client follows redirects automatically, credentials may be sent to another host depending on the implementation's redirect policy. **Never assume** a library always strips the `Authorization` header when the host changes. Explicitly configure `followRedirect(false)` and reject all 3xx responses in token-bearing outbound services as shown in the demo.

When redirecting to another host is genuinely required, the client should:

1. Check the new destination against a server-owned allowlist policy, never trusting unverified upstream headers directly.
2. Issue a **new request** with a token whose audience/scopes target that destination rather than blindly keeping the old token.
3. Never forward `Authorization`/cookies/sensitive headers from B to C unless C is authorized to receive them.
4. Validate HTTPS, certificate hostnames, egress network rules, DNS resolution, and response sizes/timeouts.
5. Audit token routing without logging token values.

**`WebClient.baseUrl(...)` alone does not constrain the destination.** Passing an absolute URI to `.uri(...)` overrides the base URL. Code reviews must therefore inspect **every call site** of `profileRelayWebClient` and ensure no arbitrary URI/path mapping is exposed on public APIs.

### HTTPS Alone Is Insufficient If the Destination Is Untrusted

TLS protects the **transport channel to the destination chosen by the client**. If the destination is an attacker-controlled domain with a valid certificate, TLS dutifully delivers the Bearer token securely **to the attacker**. You must control **which destinations are allowed**, not merely check that a URL starts with `https://`.

---

## 11. Retries, Timeouts, Cancellation, and Backpressure

### Timeouts

Both HTTP introspection (A -> IdP) and outbound calls (A -> B) add latency. Without timeouts, requests can hang and exhaust connection pools while resources and tokens remain pinned in the pipeline.

In the demo, `responseTimeout(Duration.ofSeconds(5))` bounds Netty's response wait time. Production also needs connect timeouts, DNS resolution policies, pool timeouts, end-to-end deadlines, and metrics. Every timeout must fail safely rather than falling back to `permitAll()`.

### Retries

Do not use:

```java
// Anti-pattern: can spam requests with unbounded retries on errors.
return service.profile().retry();
```

If retries are necessary:

- Retry only specific transient network/5xx errors on an explicit allowlist.
- Apply backoff, jitter, and a maximum attempt cap.
- Never retry 401/403 endlessly when B rejects a token: token relay cannot refresh credentials.
- For side-effecting POST/PUT calls, require idempotency keys and an explicit retry design.
- Ensure tracing never records tokens, and retried requests retain the right security context and authorization.

### Cancellation and Reactive Chains

When the client cancels a request, downstream subscriptions should cancel along the Reactor chain. Never manually `.subscribe()` to a `WebClient` request detached from the lifecycle so it keeps sending tokens after the upstream HTTP response ends. Move background work to jobs with proper service credentials instead of retaining user tokens.

### Response Bodies and Error Sanitization

In the demo, errors from B are translated into a generic `ResponseStatusException(502, ...)` and error bodies are released without echoing. Production must bound response sizes, prevent response-based injection, and validate content types/schemas before returning data to clients. If B returns PII, API A must still enforce data-level authorization.

---

## 12. Building Trust Boundaries for Multi-Service Architectures

### Simple Model

```text
Browser
  |
  | Token with audience for A and B
  v
Edge API A --mTLS/HTTPS + delegated Bearer--> Profile B
     |
     +-- separate: IdP introspection endpoint (HTTPS, Basic client auth)
```

Enforce policies:

- **Client -> A:** active token, A's audience, required scope, rate limit.
- **A -> IdP:** HTTPS introspection URI from trusted config only; protect secrets; validate response.
- **A -> B:** allowlisted hostname/path only, TLS/mTLS, no redirect following, no token logging.
- **B:** independent introspection/verification, B's audience, scope/ownership/tenant checks.
- **B -> DB:** row-level authorization by principal/tenant/resource. Never treat `sub` as a trusted string unless verified.

### Multi-Hop A -> B -> C

Never treat a multi-hop access token as an unlimitedly relayable bearer credential. The more services hold a token, the greater the leak blast radius. When C sits in another trust domain, prefer token exchange or a dedicated workload token with tight scopes and audience. Track the **delegation chain** and prevent confused deputies.

### Multi-Tenancy

Alice's token in tenant A must never access tenant B's data. Avoid:

- Using a shared `client_registration_id` to cache user tokens in a shared cache without subject/tenant keys.
- Relaying user tokens across tenants merely because scope names match.
- Relying on a caller-sent `X-Tenant-ID` header instead of an IdP-verified identity/tenant.
- Allowing `WebClient` to redirect or resolve hosts from unvalidated tenant names.

When each tenant has its own endpoint, use a server-side allowlisted `tenant -> endpoint` mapping rather than building URLs directly from raw tenant IDs or hostnames.

---

## 13. 401, 403, 502: Diagnosing the Right Layer

| Scenario | Did A Authenticate? | Did A Call B? | Typical HTTP |
| --- | --- | --- | --- |
| No Bearer | No | No | 401 at A |
| Inactive/invalid token | No | No | 401 at A |
| Token wrong audience for A | No | No | 401 at A |
| Active token, right audience, missing scope at A | Yes | No | 403 at A |
| Active token, A audience+scope valid, B accepts | Yes | Yes | 200 |
| Valid at A, rejected by B for B's audience/scope | Yes | Yes | Depends on A's mapping (502 in demo) |
| B returns 302 to external host | Yes | Yes (not followed) | 502 in demo |
| IdP introspection timeout/outage | No verification result | No | Serve no data; status per error handling |
| B timeout/unreachable | Yes | Attempted | 502/504 or safely mapped error |

A 403 at A and a 403 at B are two distinct events. In the demo, B returning 401 is translated to 502 at A so raw downstream bodies and challenge headers are not leaked; real systems may pick specific business error codes, provided the contract and observability are clear.

### How to Debug

1. Check whether A returned 401 before or after introspection (without logging tokens).
2. Check whether A received `SCOPE_profile.read` and audience `api://relay-edge`.
3. Check whether B is permitted to receive this token, and whether B sees `api://profile-service` and matching scopes.
4. Inspect outbound domain, scheme, path, DNS, and upstream certificates. Never let users control URLs.
5. Inspect trace/correlation IDs across A-IdP-B, without copying the `Authorization` header into trace baggage.
6. On 302s, treat `Location` as untrusted data and never auto-follow with a Bearer client.
7. If B returns 401 due to an expired token, the relay filter **does not auto-refresh**; design re-authentication or token exchange/client flows accordingly.
8. If B returns 403 due to `insufficient_scope`, never loosen policies or substitute an over-privileged service token to "fix" it.
9. Check retries, concurrency, and caching so user bearer tokens are never sent outside their lifecycle.
10. Reproduce with `WebTestClient` + `MockWebServer`, then verify in staging under real TLS.

---

## 14. Production Checklist and Review Questions

### Security Checklist

1. Protected endpoints at A use reactive `SecurityWebFilterChain` and standard opaque introspection.
2. Introspection endpoint uses trusted HTTPS, client-id/secret from a secret manager, and never fails open.
3. A's audience is validated; required scopes are enforced before outbound calls.
4. B independently verifies tokens and validates B's audience, scopes, owner, and tenant.
5. Token relay is used only when IdP policy allows B to accept the same token; otherwise use token exchange or appropriate credentials.
6. The Bearer relay filter sits only on a `WebClient` **dedicated to B**, never on a global/general-purpose `WebClient`.
7. B's URL comes from a server-owned allowlist/config with fixed paths; never accept arbitrary outbound URLs from users.
8. Automatic redirects are disabled; 3xx responses are never followed to untrusted destinations.
9. HTTPS/mTLS, hostname/certificate verification, DNS/egress restrictions, and network policies are verified.
10. Never log Bearer tokens, client secrets, raw introspection responses containing sensitive info, or `Authorization` headers.
11. Never store user tokens in static/singleton fields or non-reactive `ThreadLocal`s; never drop the Reactor `SecurityContext`.
12. Configure timeouts, bounded retries, circuit breakers/backpressure, and observability.
13. Distinguish 401/403/502 without echoing raw error responses or headers from B.
14. Never cache responses by URL while ignoring user/tenant, and never publicly cache PII.
15. Negative tests cover: inactive, wrong aud, missing scope, wrong host, redirect, no context, upstream 401, network errors, and token leakage.
16. Audit security dependency versions and patch CVEs before production; Spring Boot 3.5 is past OSS support.
17. In multi-tenant setups, enforce tenant/owner checks on B's data rather than relying solely on global scopes.
18. Maintain a clear threat model and runbook for token exchange, revocation, and trust boundaries whenever new services are added.

### Exercises

1. Explain where `ServerBearerExchangeFilterFunction` retrieves the token when a WebFlux controller returns a `Mono`.
2. Why can the exact same opaque token introspected successfully by A still receive a 401 from B?
3. Compare relay, `client_credentials`, and RFC 8693 Token Exchange in terms of audience and user permissions.
4. Remove `.filter(new ServerBearerExchangeFilterFunction())` from the relay client and run the tests; observe that B receives no token.
5. Add the relay filter to the public client and run the tests; why must the leak-prevention test fail?
6. Enable `followRedirect(true)` solely in **a test environment with MockWebServer** using no real tokens; inspect whether `CAPTURE` is called and how headers behave on host changes. Restore `false` afterward.
7. Send `no-scope-token` and observe A returning 403 **before** any HTTP call to B occurs.
8. Send an active token with the wrong audience and locate the introspector code returning 401.
9. Write an integration test against a real B to verify B's audience and scope validation, which the current MockWebServer test does not prove.
10. Change `PROFILE_BASE_URL` to a plain HTTP URL outside localhost: how must the application reject that configuration?
11. Allow a user-controlled query parameter for **search data**—not host/path. Write validation ensuring it cannot introduce an absolute URI or path traversal.
12. Add a Token Exchange option if supported by the IdP, ensuring the new token carries only `aud=api://profile-service`.
13. Compare Reactor Context with `ThreadLocal` `SecurityContext`; why can manual `.subscribe()` break the request lifecycle?
14. Design a 502 error response policy, correlation IDs, and log masking when B returns 401/403.
15. Assess the risks of relaying the same Bearer token across A -> B -> C and identify where relaying should stop.
16. Define a profile result caching policy keyed by subject/tenant to prevent serving Alice's data to Bob.
17. Combine mTLS with Bearer tokens at B and explain why mTLS only proves A is the calling service without replacing Alice's authorization.
18. Design a test verifying that the public `WebClient` sends no token even when the caller is authenticated.

## Summary

In **Spring Security reactive Resource Server Opaque**, A first uses `ReactiveOpaqueTokenIntrospector` to verify the Bearer token and create an `Authentication` in the Reactor Context. `ServerBearerExchangeFilterFunction` can then use that verified OAuth2 credential to attach `Authorization: Bearer ...` on outbound `WebClient` calls downstream.

**The core issue is not adding a header, but the authority to pass a token across a trust boundary:** the token must carry audience/scopes meant for B, `WebClient` may call only allowlisted upstreams, HTTPS/mTLS/egress must be enforced, redirects must not be followed automatically, tokens must never be logged, and B must verify independently. The relay filter does **not** renew tokens, does not replace OAuth2 Client/token exchange, and does not grant permissions. Token relay must be designed intentionally as an inter-service delegation mechanism, never as a blanket header copy on every outbound call.

## Official References

- [Spring Security 6.5 — Reactive Resource Server Bearer Token Propagation](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/bearer-tokens.html)
- [Spring Security 6.5 — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — ServerBearerExchangeFilterFunction API](https://docs.spring.io/spring-security/site/docs/6.5.4-SNAPSHOT/api/org/springframework/security/oauth2/server/resource/web/reactive/function/client/ServerBearerExchangeFilterFunction.html)
- [Spring Security 6.5 — OAuth2 Client in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html)
- [Spring Security — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Framework 6.2 — WebClient Filters](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-filter.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
