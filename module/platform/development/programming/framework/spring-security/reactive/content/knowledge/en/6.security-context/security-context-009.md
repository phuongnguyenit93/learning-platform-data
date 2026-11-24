# Distinguishing local security context from tokens sent to other services

> **Module:** Spring Security - reactive  
> **Group:** Security context  
> **Goal:** Understand the boundary between `SecurityContext` existing inside a reactive execution and an access token sent in an HTTP request to another service; practice reading context with `ReactiveSecurityContextHolder`, relaying Bearer tokens with `WebClient`, testing, and evaluating audience/scope and business permissions.

## 1. Learning outcomes

After this lesson, learners should be able to distinguish four things: (1) service A **authenticated** the caller and stored the result in its local `SecurityContext`; (2) an HTTP client in A can **choose a credential** when calling B; (3) B must **re-authenticate the credential** on the request arriving at B; (4) B must **authorize** each operation and data object itself, even when A already allowed the prior request.

Practical results must prove that **having a local SecurityContext is not enough for WebClient to automatically send a Bearer token**. When an authorized relay filter is configured on WebClient, the token can be attached in the `Authorization` header. That does not mean A's entire context, roles, or data permissions automatically transfer to B.

## 2. Two scopes: local context and HTTP credential

Suppose a client calls `GET /api/reports/current` on service A. A needs to query service B via `GET /internal/reports/current`.

~~~text
Client
  │ Bearer access token
  ▼
Service A — Spring WebFlux
  │ 1. SecurityWebFilterChain authenticates incoming request
  │ 2. Authentication resides in SecurityContext of A's Reactor pipeline
  │ 3. Controller/Service reads identity and checks A's permissions
  │ 4. WebClient creates a new outbound HTTP request
  │    Authorization: Bearer <credential permitted to send>
  ▼
Service B — Spring WebFlux, separate process
  │ 5. B's SecurityWebFilterChain re-verifies the token
  │ 6. B has a NEW SecurityContext for B's request
  │ 7. B checks scope, tenant/owner/data state
  ▼
B returns result to A, then A returns to client
~~~

**Reactor Context does not cross HTTP.** Even when both service A and service B use Spring Security Reactive, they live in two different memory spaces and two separate subscriptions. B cannot read A's `SecurityContext` object by calling `ReactiveSecurityContextHolder` inside B's process.

| Attribute | Local SecurityContext / Authentication | Outbound OAuth2 access token |
| --- | --- | --- |
| Nature | Authentication result state in the active execution | Credential issued by an identity provider/authorization server |
| Location | Reactor Context of the processing service | Usually in the `Authorization: Bearer ...` header of the HTTP request |
| Who reads it? | Code in the current service | Resource server receiving the new HTTP request |
| Contents | Principal, authorities, authenticated status, sometimes credentials | Signed JWT or opaque token; scope, audience, issuer, expiry per protocol |
| Crosses network automatically? | **No** | Only when an outbound client/flow explicitly sends it |
| Trust scope | Local execution + service A's policy | Scope granted for the target resource server |
| Decides B's data permissions | Cannot substitute for B's authorization | Even a valid token still needs B's business authorization |

**Never serialize the raw `SecurityContext`, `Authentication`, or username into JSON for B to trust as logged in.** Sending a username or `X-User: alice` does not create trustworthy proof of identity; if a trusted gateway pattern exists, it must have its own assertion protection/verification mechanism and trust boundary.

## 3. SecurityContext in Spring Security Reactive

### 3.1. Context and principal

`Authentication` represents the principal and `GrantedAuthority` instances verified by Spring Security; `SecurityContext` holds `Authentication`. In Spring WebFlux, Spring Security attaches `SecurityContext` to **Reactor Context**. Context data follows the **subscription**, rather than being bound to a fixed thread.

Example method reading the authenticated user's name:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentUserName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication())
        .map(Authentication::getName);
}
~~~

The snippet above is an illustrative method inside a Spring bean, **not** a standalone Java file. If no context exists yet, the `Mono` can complete empty; the controller or service must define the policy for anonymous cases. For authenticated HTTP requests, Spring Security sets up the context for the matching pipeline.

### 3.2. Reactor Context differs from ThreadLocal

In Spring MVC Servlet, learners often see `SecurityContextHolder.getContext()` tied to threads. In WebFlux, a request can switch schedulers, and event-loop threads serve multiple requests. Using Servlet's `ThreadLocal` assuming the same thread always carries the user is unsafe.

**Right:** read context inside a `Mono` or `Flux` with `ReactiveSecurityContextHolder.getContext()` and compose with operators like `flatMap`. `publishOn` within **the same subscription** still preserves Reactor Context propagation. **Avoid** calling `block()` on the event loop or spawning a separate `subscribe()` expecting the original request's context to remain intact.

### 3.3. Context without an HTTP request

Example solely for a test method:

~~~java
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

TestingAuthenticationToken auth =
    new TestingAuthenticationToken("alice", "ignored", "ROLE_USER");

Mono<String> userName = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
~~~

When subscribed, the pipeline emits `alice`. There is no signed JWT, no HTTP request to B, and no external authentication. `contextWrite` only supplies information to **one reactive test subscription**; it does not turn an `Authentication` object into a network-transmittable credential.

## 4. Access token is a scoped credential

An HTTP Bearer credential typically looks like:

~~~http
GET /internal/reports/current HTTP/1.1
Host: reports.example.invalid
Authorization: Bearer <access-token>
~~~

A JWT access token can contain `iss` (issuer), `sub` (subject), `aud` (audience), `exp`/`nbf`, and `scope`. Service B must verify the signature (or introspection for opaque tokens), expiry, issuer, audience, and required permissions per policy. **Base64-decoding the payload alone does not authenticate a token.**

Distinguish:

- **Access token:** used to request access to a resource server within granted scopes.
- **ID token in OpenID Connect:** primarily for user authentication at the OAuth2/OIDC client; do not use it in place of an access token for API B.
- **Session cookie:** can prove a user logged into website A, but is not accepted by B as a Bearer token by default.
- **Username/role in body or custom headers:** not a credential without a trusted authentication protocol.

**A Bearer token is a secret:** anyone holding an unexpired token can attempt to use it within its valid scope. Send only over TLS, never log tokens, never echo tokens back in JSON responses, and never forward them to unauthorized hosts.

## 5. Four steps when A calls B

1. **Client → A:** A verifies the Bearer token/session on the **inbound** request and builds A's `Authentication`. Valid login at A does not prove permission to use B.
2. **Inside A:** Spring Security puts `SecurityContext` into Reactor Context. A's controller/service reads the principal for local processing and checks corresponding permissions.
3. **A → B:** A decides whether to send a credential. `WebClient` creates a **separate outbound request**; only tokens/headers attached to that request cross the network—no Reactor Context object travels with it.
4. **At B:** B re-authenticates the token, creates **B's** SecurityContext, and checks route/service permissions and record-level permissions. If the token is not intended for B, B must reject it.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Client
    participant A as Service A
    participant C as Reactor Context A
    participant B as Service B
    U->>A: GET /api/reports/current + Bearer token
    A->>A: Validate JWT / Authenticate
    A->>C: Store A's SecurityContext
    A->>C: Read principal and authorities
    A->>B: WebClient + permitted outbound token
    Note over A,B: Do not send SecurityContext object over network
    B->>B: Validate token + create context B + authorize
    B-->>A: 200 / 401 / 403
    A-->>U: Result or handled error
~~~

Note: B may see the same subject if A relays the user's access token, yet that is a **fresh authentication** at B. There is no rule that "if A allowed it, B must allow it".

## 6. Plain WebClient does not relay tokens automatically

The code below uses a default WebClient:

~~~java
WebClient plain = WebClient.create();

Mono<String> report = plain.get()
    .uri("https://reports.example.invalid/internal/reports/current")
    .retrieve()
    .bodyToMono(String.class);
~~~

Even when `ReactiveSecurityContextHolder.getContext()` holds a `JwtAuthenticationToken`, a plain WebClient **does not** automatically read `Authentication` and add an `Authorization` header. If B requires a Bearer token, a request without credentials can receive 401.

Do not fix this by having B skip JWT verification or trust a username A put into JSON. Instead, choose an **outbound credential mechanism** matching the A → B security contract.

## 7. Resource Server relay: ServerBearerExchangeFilterFunction

Spring Security Reactive provides `ServerBearerExchangeFilterFunction`, a WebClient `ExchangeFilterFunction`. The filter looks up `Authentication` in the reactive context, extracts credentials of type `AbstractOAuth2Token` (such as a JWT in `JwtAuthenticationToken`), and places the Bearer token into the outbound request header.

~~~java
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

WebClient relay = WebClient.builder()
    .filter(new ServerBearerExchangeFilterFunction())
    .build();
~~~

This **does not fetch a new token** from the issuer and **does not refresh** expired tokens. The filter can only forward an existing credential if the context/authentication matches. The relayed token can still be rejected by B if `aud`, `scope`, `iss`, or expiration do not satisfy B.

**Usage principle:** attach the filter only to WebClients dedicated to trusted downstreams with controlled destinations. Every outgoing request using that client can have the Bearer token attached; never pass arbitrary user-supplied URLs to this client, and do not assume `baseUrl` prevents off-host absolute URIs.

## 8. Sample Java 17+ project: Resource Server A calling B

The example designs **service A** with two endpoints:

- `GET /api/whoami` reads only the **local** principal.
- `GET /api/reports/current` requires authority `SCOPE_reports.read` and uses a dedicated WebClient to call service B at `/internal/reports/current`.

This lesson uses Spring Boot **3.3.13** to illustrate Spring Security 6.x and match the lab branch; Spring Boot 3.3 has reached end of open-source support, so new production systems must use a supported version. The files below form a standalone project sufficient to **compile and run unit tests**. Running end-to-end requires a real issuer, valid tokens, and a real service B; `example.invalid` domains are illustrative only.

### 8.1. Structure

~~~text
reactive-context-vs-token/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/context/
    │   │   ├── ContextVsTokenApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── ReportWebClientConfig.java
    │   │   ├── ReportClient.java
    │   │   └── ApiController.java
    │   └── resources/application.yml
    └── test/java/example/context/
        └── TokenPropagationTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-context-vs-token</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Do not add `spring-boot-starter-web` since the lab follows the WebFlux model.

### 8.3. Application entrypoint

File `src/main/java/example/context/ContextVsTokenApplication.java`:

~~~java
package example.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextVsTokenApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextVsTokenApplication.class, args);
    }
}
~~~

### 8.4. Service A's SecurityConfig: **inbound** authentication

File `src/main/java/example/context/SecurityConfig.java`:

~~~java
package example.context;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports/current")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This rule **only decides who can enter A**. `SCOPE_reports.read` assumes JWT scopes are mapped by default with the `SCOPE_` prefix. For non-standard permission claims, configure a custom converter. Beyond default validators, audience validation dedicated to A is needed.

### 8.5. Outbound WebClient configured for relay

File `src/main/java/example/context/ReportWebClientConfig.java`:

~~~java
package example.context;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportWebClientConfig {

    @Bean("reportWebClient")
    WebClient reportWebClient(
            WebClient.Builder builder,
            @Value("${app.reports.base-url}") String baseUrl) {

        return builder.clone()
            .baseUrl(baseUrl)
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
    }
}
~~~

Only the `reportWebClient` bean uses the relay filter. A dedicated bean limits credential usage scope; you still must avoid absolute URIs or redirects to untrusted hosts. `@Value` reads a configuration property shown in the YAML below.

### 8.6. Calling B within the same reactive pipeline

File `src/main/java/example/context/ReportClient.java`:

~~~java
package example.context;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReportClient {

    private final WebClient reportWebClient;

    public ReportClient(
            @Qualifier("reportWebClient") WebClient reportWebClient) {
        this.reportWebClient = reportWebClient;
    }

    public Mono<String> loadCurrentReport() {
        return reportWebClient.get()
            .uri("/internal/reports/current")
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

This is the HTTP call to B. When the chain is subscribed during an authenticated request, the filter can extract the token from the local `Authentication` and add `Authorization: Bearer ...` to the outgoing request. The method **does not** call `block()` or create a separate subscription via `subscribe()`; that keeps the pipeline/context intact and avoids blocking the event loop.

### 8.7. Controller distinguishing the two operations

File `src/main/java/example/context/ApiController.java`:

~~~java
package example.context;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    private final ReportClient reports;

    public ApiController(ReportClient reports) {
        this.reports = reports;
    }

    @GetMapping("/api/whoami")
    public Mono<Map<String, String>> whoAmI() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> Map.of(
                "principal", ctx.getAuthentication().getName()
            ));
    }

    @GetMapping("/api/reports/current")
    public Mono<String> currentReport() {
        return reports.loadCurrentReport();
    }
}
~~~

`whoAmI()` only reads the local principal; `currentReport()` requires a new HTTP request. This difference exists even though both methods live in the same controller and are invoked by the same user.

### 8.8. application.yml

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.invalid/realms/lab

app:
  reports:
    base-url: https://reports.example.invalid
~~~

The `.invalid` URLs are illustrative only. To run a real system, replace the issuer with an IdP having valid metadata/JWKS and replace the base URL with trusted service B over HTTPS. Provide real configuration via appropriate secret/config management; never allow arbitrary request parameters to choose which host receives tokens.

`issuer-uri` does not by itself ensure tokens are issued for the right audience of A and B. Check audience separately for each Resource Server. When B does not accept A's original token, obtain a token properly issued for B rather than disabling validation just to make the token work.

## 9. Testing three cases with a stubbed ExchangeFunction

You do not need to mint real signed JWTs to prove **the presence/absence of an outbound Bearer header**. The test below places a fake `JwtAuthenticationToken` in Reactor Context and uses an `ExchangeFunction` returning `report-ok`. No network calls, no IdP, and no production credentials are used.

File `src/test/java/example/context/TokenPropagationTest.java`:

~~~java
package example.context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TokenPropagationTest {

    private static final String DESTINATION =
        "https://reports.example.invalid/internal/reports/current";

    private JwtAuthenticationToken fakeAuthentication() {
        Jwt jwt = Jwt.withTokenValue("fake-test-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .claim("scope", "reports.read")
            .build();

        return new JwtAuthenticationToken(
            jwt,
            List.of(new SimpleGrantedAuthority("SCOPE_reports.read"))
        );
    }

    private WebClient fakeClient(
            AtomicReference<String> capturedAuth,
            boolean enableRelay) {

        WebClient.Builder builder = WebClient.builder()
            .exchangeFunction(request -> {
                capturedAuth.set(
                    request.headers().getFirst(HttpHeaders.AUTHORIZATION)
                );
                return Mono.just(
                    ClientResponse.create(HttpStatus.OK)
                        .body("report-ok")
                        .build()
                );
            });

        if (enableRelay) {
            builder.filter(new ServerBearerExchangeFilterFunction());
        }

        return builder.build();
    }

    @Test
    void localContextDoesNotAutomaticallySendBearer() {
        AtomicReference<String> observed = new AtomicReference<>();
        WebClient plain = fakeClient(observed, false);

        Mono<String> call = plain.get()
            .uri(DESTINATION)
            .retrieve()
            .bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    fakeAuthentication()
                )
            );

        StepVerifier.create(call)
            .expectNext("report-ok")
            .verifyComplete();

        assertNull(observed.get());
    }

    @Test
    void relayFilterSendsBearerFromReactiveContext() {
        AtomicReference<String> observed = new AtomicReference<>();
        WebClient relay = fakeClient(observed, true);

        Mono<String> call = relay.get()
            .uri(DESTINATION)
            .retrieve()
            .bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    fakeAuthentication()
                )
            );

        StepVerifier.create(call)
            .expectNext("report-ok")
            .verifyComplete();

        assertEquals("Bearer fake-test-token", observed.get());
    }

    @Test
    void noContextMeansNoBearerToRelay() {
        AtomicReference<String> observed = new AtomicReference<>();
        WebClient relay = fakeClient(observed, true);

        Mono<String> call = relay.get()
            .uri(DESTINATION)
            .retrieve()
            .bodyToMono(String.class);

        StepVerifier.create(call)
            .expectNext("report-ok")
            .verifyComplete();

        assertNull(observed.get());
    }
}
~~~

In the directory containing `pom.xml`:

~~~bash
mvn clean test
~~~

| Test | Has local Authentication? | Has relay filter? | Authorization sent to fake B |
| --- | --- | --- | --- |
| `localContextDoesNotAutomaticallySendBearer` | Yes, fake JWT Authentication | No | **No header** |
| `relayFilterSendsBearerFromReactiveContext` | Yes, fake JWT Authentication | Yes | **Bearer fake-test-token** |
| `noContextMeansNoBearerToRelay` | No | Yes | **No header** |

**Test limitations:** `Jwt.withTokenValue("fake-test-token")` only builds an object for unit tests—it **does not** sign a JWT, verify signatures, make network calls, or test B. A fake token cannot be used as a real access token. To prove end-to-end security, add integration tests with issuer/test keys and a real authenticating B.

## 10. Service B must create its own context and authorize separately

An illustrative configuration snippet **inside B's own project**:

~~~java
@Bean
SecurityWebFilterChain downstreamSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers(HttpMethod.GET, "/internal/reports/current")
                .hasAuthority("SCOPE_reports.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}
~~~

This snippet uses the same imports as `SecurityConfig.java` above; it **must not** be treated as a standalone service B without B's Spring Boot app, decoder, endpoint, and issuer configuration.

When B receives a request, B must verify:

1. JWT signature / opaque introspection, issuer, and expiration.
2. **Audience dedicated to B**, not just the issuer. A token valid for A is not necessarily valid for B.
3. Scopes/roles required for the endpoint; proper authority mapping per convention.
4. Owner/tenant/object permissions and business state.
5. Scope of response data, logs, and caches.

You cannot "borrow" the `hasAuthority("SCOPE_reports.read")` decision at A to skip authorization at B. A only decides whether the caller may perform the action **through A**; B decides what the credential arriving at B may do **on B's resources**.

## 11. Audience and scope: when is relaying the raw token wrong?

Suppose A's inbound token has illustrative claims:

~~~json
{
  "iss": "https://issuer.example.invalid/realms/lab",
  "sub": "alice",
  "aud": ["api-a"],
  "scope": "profile.read",
  "exp": 2000000000
}
~~~

This is **an illustrative payload only**, not a signed token. Service B requires `aud=reports-api` and `reports.read`. If A forwards the raw token with `aud=["api-a"]` to B, then **B must reject it**. A cannot modify the audience/scope inside the token while keeping the signature valid.

The options are:

| Case | Approach | Must verify |
| --- | --- | --- |
| Original access token is **authorized** for both A and B | Relay existing token | Audience, scope, expiry, owner/tenant at B |
| Token is intended only for A | OAuth2 token exchange / on-behalf-of | IdP supports the flow; new token has B's audience/scope |
| A calls B under service A's own authority | OAuth2 client credentials | B authenticates machine identity; do not mistake for user delegation |
| A logs user in via session/OIDC | OAuth2 authorized client or valid delegation flow | Use **access token** for B, never cookies/ID tokens |
| B needs no credential | Do not send a token | Avoid leaking unnecessary tokens |

**Token exchange** means asking the IdP to issue a new access token per delegation policy, not altering payloads or copying headers to other hosts. Supported grants/flows depend on the Spring Security version and identity provider.

**Client credentials** identify a machine/service and do not automatically carry Alice's permissions. If B needs to know which tenant's report Alice is requesting, the design must use on-behalf-of/delegation or another trusted mechanism with transparent auditing.

## 12. Resource Server relay vs. OAuth2 Client authorized client

### 12.1. ServerBearerExchangeFilterFunction

This is the mechanism from section 7: **reusing the OAuth2 token credential** in local `Authentication`, without fetching or refreshing. Appropriate when A is a Resource Server and the incoming token is already valid for downstream B.

### 12.2. ServerOAuth2AuthorizedClientExchangeFilterFunction

When A acts as an **OAuth2 Client**, Spring Security provides `OAuth2AuthorizedClient` and `ReactiveOAuth2AuthorizedClientManager` to obtain/store/refresh access tokens via supported grants. WebClient can integrate via its dedicated filter:

~~~java
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient oauth2WebClient(
        ReactiveOAuth2AuthorizedClientManager manager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction filter =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .filter(filter)
        .build();
}
~~~

This configuration snippet **requires a real OAuth2 Client/ClientRegistration environment**; project A in section 8 **uses Resource Server only**, so it does not yet have a manager/registration for this snippet.

You can explicitly select an authorized client or `clientRegistrationId` per request. **Avoid enabling default attachment of user tokens to all HTTP requests** (such as `setDefaultOAuth2AuthorizedClient(true)`) if WebClient could reach unintended hosts; Spring Security documentation warns about attaching access tokens more broadly than intended.

### 12.3. OIDC login does not mean a token lives in Authentication.credentials

`oauth2Login()` usually represents a user's login with `OAuth2AuthenticationToken`, while the access token is managed via `OAuth2AuthorizedClient`. That differs from a Resource Server JWT held in `JwtAuthenticationToken`. Do not assume `ServerBearerExchangeFilterFunction` will always find an access token just because the user logged in via OIDC. Use the proper OAuth2 Client flow and identify the exact token type to send to B.

## 13. Boundaries where context is easily lost or leaked

| Processing | Local SecurityContext | Token to B |
| --- | --- | --- |
| Controller → Service chained with `Mono.flatMap` | Preserved across the same subscription | Not sent automatically |
| `publishOn` in the same Reactor pipeline | Context follows the subscription | Not sent automatically |
| `WebClient.create()` without filter | Local context still exists in A | No automatic Bearer |
| WebClient with `ServerBearerExchangeFilterFunction` | Reads authentication from context | Can relay Bearer under proper conditions |
| Spawning a thread / reading Servlet ThreadLocal | Not guaranteed | Not sent automatically |
| Manual `subscribe()` in a detached flow | Proper context inheritance not guaranteed | Not sent automatically |
| B receives HTTP from A | B gets a new context only after authenticating | B receives credentials in the request |
| Scheduled job or message consumer | Does not automatically hold old HTTP request identity | Needs appropriate service/delegated identity |

Never call `block()` to "fetch the principal and then call B", or put an access token in a static variable for later callbacks. For long-running requests, queues, or scheduled workers, tokens may expire or the user's permissions may have been revoked. Design a dedicated execution identity for such jobs.

Correlation ID / W3C trace context is for tracing calls across services, **not a credential**. Never treat `traceparent` or usernames in logs as authorization proof.

## 14. Handling 401, 403, and downstream errors

| Failure point | Example | Nature |
| --- | --- | --- |
| A inbound authentication | Missing/invalid Bearer token to A | A can return **401** |
| A inbound authorization | Valid token, missing `SCOPE_reports.read` | A can return **403** |
| A outbound credential | WebClient did not relay; B receives request without token | B returns **401** |
| B token validation | Token valid for A, wrong audience for B or expired | B rejects (usually **401**) |
| B authorization | Token valid for B, missing scope/owner/tenant | B rejects (**403/404** per policy) |
| A reading B's response | `retrieve()` encounters 4xx/5xx | WebClient emits a reactive error by default; status returned to A's client needs explicit mapping |

Do not conclude "Reactor Context was lost" solely from a 401 at B. Inspect each boundary in order: **A inbound token → A SecurityContext → WebClient filter → outbound header present/absent → B token validation → B authorization**. When logging, log only outcomes and safe metadata, **never Bearer token values**.

## 15. Security when passing credentials between services

1. **Restrict destinations:** relay only to allowlisted hosts/paths. An absolute URL passed to WebClient can override the base URL; if user-controlled, tokens can be sent to an attacker's domain (SSRF/credential leakage).
2. **TLS:** use HTTPS on the wire; Bearer tokens are secrets, and Base64/JWT serialization is not encryption. Control redirects so tokens never accidentally go to the wrong host.
3. **Never log tokens:** avoid printing `Authorization` headers, cookies, raw JWTs, or refresh tokens in request logs, tracing spans, proxy logs, and stack traces.
4. **Minimal scope/audience:** request only permissions B needs. Never disable B's audience check just to make A's original token "work".
5. **Object/tenant permissions:** a broad scope does not grant access to every report or another user's data. B enforces per-object permissions in its service/repository.
6. **Limit lifetime:** do not keep access tokens in global/static caches or long-lived queues without expiry/refresh/revocation policies.
7. **Prevent identity confusion:** do not claim a user is acting at B when outbound actually uses A's `client_credentials`. Audit actor and delegation clearly.
8. **Guard against environment gaps:** unit tests with fake tokens and stubbed HTTP only verify wiring; add integration tests for JWT verifiers, audience/scope, TLS, and B's business permissions.

## 16. Common mistakes and fixes

| Mistake | Explanation | Resolution |
| --- | --- | --- |
| "If A can read the principal, WebClient has the token" | Local context differs from outgoing Authorization | Add an authorized outbound mechanism and test the header |
| "Any token can be sent to every service" | Tokens have audience/scope and trust boundaries | Relay only to proper targets; use token exchange if B needs its own token |
| "B trusts that A already authenticated" | B is an independent resource server | B must re-verify the token and authorize |
| "Send the ID token to B" | ID tokens are not API access tokens | Obtain an access token for the target resource |
| "Spring OAuth2 login is relayed by Resource Server filter" | Access tokens may live in OAuth2AuthorizedClient | Use the appropriate OAuth2 Client filter/authorized client |
| "Attach relay filter to a shared general WebClient" | Every URI on that client risks receiving credentials | Use a dedicated bean; restrict hosts, redirects, and egress |
| "B returned 401 because local context broke" | B may reject issuer/audience/expiry/missing token | Isolate inbound/outbound/B validation with tests |
| "An X-Username header suffices for B to trust identity" | Arbitrary headers have no proof | Use verified tokens/assertions and trust boundaries |
| "Fake JWT in unit test proves production security" | Test lacks signatures, IdP, audience, or B | Build integration tests for real validators and APIs |
| "block()/subscribe() to grab the user quickly" | Can break pipelines and lose context | Keep Mono/Flux flow with flatMap and proper context |

## 17. Practice exercises

**Exercise A — observe local:** add a method that reads `ReactiveSecurityContextHolder.getContext()` and returns the principal. Explain why succeeding inside A **does not** mean B is granted that identity.

**Exercise B — prove outbound:** run the three tests in section 9. Try removing the filter in the second test; predict which assertion fails. Restore it and explain where the filter reads the token from.

**Exercise C — design audience:** the client-supplied token has `aud=["api-a"]`; B requires `aud=reports-api`. Write out the choice among relay, token exchange, and client credentials; explain why B's audience validation must not be disabled.

**Exercise D — data authorization:** Alice and Bob both have `reports.read`, yet report 42 belongs to Bob. When Alice calls B through A, which step prevents Alice from viewing report 42? Write a negative test on B for owner/tenant isolation.

**Exercise E — prevent token leakage:** describe a scenario where an attacker passes an absolute URL to a WebClient configured with the relay filter. Fix the design to allow only relative URIs to configured service B and add outbound host/redirect controls. Never use real credentials in the lab.

**Exercise F — compare OAuth2 Login:** A authenticates users via an OIDC session and holds an `OAuth2AuthorizedClient`. Explain why the Resource Server relay filter might fail to retrieve an access token and how to use the OAuth2 Client manager/filter instead.

## 18. Completion checklist

- [ ] Distinguish local `SecurityContext` from `Authorization: Bearer ...`.
- [ ] Understand Reactor Context resides in a single execution/subscription and does not cross the network automatically.
- [ ] Read the principal via `ReactiveSecurityContextHolder` instead of relying on Servlet ThreadLocal.
- [ ] Know that a plain WebClient does not forward tokens automatically.
- [ ] Know that `ServerBearerExchangeFilterFunction` can relay an existing OAuth2 token credential without doing token exchange/refresh.
- [ ] Test with context **without filter** sends no Authorization header.
- [ ] Test with context **and** relay filter sends the fake Bearer header.
- [ ] Test **without context** does not cause the filter to invent a token.
- [ ] B still validates tokens and enforces audience, scope, tenant, and owner checks.
- [ ] Distinguish relay, OAuth2 Client authorized client, token exchange, and service client credentials.
- [ ] Recognize risks of logging tokens, sending tokens to wrong hosts, wrong-audience JWTs, and misusing ID tokens.

## 19. Self-check questions

1. Do two Spring WebFlux services share one `Reactor Context`? Why or why not?
2. If `Authentication.getName()` in A returns `alice`, does B already know Alice?
3. When does `ServerBearerExchangeFilterFunction` have a token to add to an outgoing HTTP request?
4. Why doesn't `WebClient.create()` automatically relay Bearer even when A holds a `JwtAuthenticationToken`?
5. If a JWT was issued only for A, is modifying its audience and sending it to B valid?
6. How does `oauth2Login()` differ from Resource Server JWT in where access tokens are managed?
7. B returns 401 while A can still read the principal: what checkpoints should you inspect?
8. Why does A's `client_credentials` not prove Alice has access to B's report?
9. Which layer does the fake JWT test in section 9 prove, and which layers does it not prove?
10. Why can't a correlation ID or `X-User` replace an OAuth2 access token?

## 20. Official references

- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context and `ReactiveSecurityContextHolder`.
- [Spring Security — Bearer Token Propagation](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html): `ServerBearerExchangeFilterFunction` and its non-refreshing behavior.
- [Spring Security — OAuth2 Client Authorized Client Features](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html): WebClient filter for `OAuth2AuthorizedClient` and warning on default bearer propagation.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): OAuth2 client, manager, authorization grants.
- [Spring Security — Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): JWT/opaque token validation at B.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Subscription-scoped Context and how it differs from ThreadLocal.
- [Spring Cloud Gateway — TokenRelay](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html): gateway use case; this is a separate component, not built into every WebFlux app.

**Conclusion:** `SecurityContext` is the **local** authentication result of the executing service. An access token is a credential that can be sent to another resource server, but only when the client is configured, the token is authorized for the right audience/scope, and the connection protects the token. Service B must authenticate and authorize independently; there is no automatic conversion of A's SecurityContext into B's SecurityContext.