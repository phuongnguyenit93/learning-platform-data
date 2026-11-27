# Credentials for the Introspection Endpoint

## 1. Why Does the Resource Server Need Its Own Credentials?

In a **Spring Security OAuth 2.0 / OIDC Resource Server** running on **WebFlux**, clients typically send an OAuth 2.0 access token over HTTP:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <CALLER_ACCESS_TOKEN>
~~~

If the API chooses **opaque token introspection**, it must ask the Authorization Server (AS) whether the token is still active and which scopes were granted. To ask, the Resource Server (RS) itself acts as **a client of the introspection endpoint**, and the AS must authenticate and authorize the RS.

There are **two separate credentials**:

| Credential | Owner | Location | Meaning |
|---|---|---|---|
| Access token to introspect | OAuth client or user/service calling the API | Inbound `Authorization: Bearer` header, then outbound `token` form field | Target whose validity and permissions are being checked |
| Introspection credential | Resource Server | Outbound request to the AS, typically `Authorization: Basic` header | Proves **the RS is allowed to query token status** |

Contract example:

~~~text
Inbound API request:
  Authorization: Bearer <opaque-token-T>

Outbound introspection:
  POST https://id.example.test/oauth2/introspect
  Authorization: Basic <RS-client-id-and-secret>
  Content-Type: application/x-www-form-urlencoded
  Body: token=<opaque-token-T>
~~~

**Never send the caller's raw access token as the RS password; never replace Basic with the very Bearer token being inspected.** These are two distinct trust boundaries.

This lesson focuses on the **credentials the Resource Server uses when calling the introspection endpoint** within a **WebFlux reactive** architecture. Related topics include RFC 7662, RFC 6749, HTTP Basic, client credentials/secret management, mTLS, private-key JWT, customizing `ReactiveOpaqueTokenIntrospector`, HTTP error handling, rotation, and testing.

## 2. How Does RFC 7662 Describe Calling Introspection?

### 2.1. HTTP Request

**RFC 7662 — OAuth 2.0 Token Introspection** defines an HTTP POST with an `application/x-www-form-urlencoded` body. Example:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Authorization: Basic <RS_CLIENT_CREDENTIALS_BASE64>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<ACCESS_TOKEN_T>&token_type_hint=access_token
~~~

Where:

- `token`: **required** — the access token to be verified.
- `token_type_hint`: **optional** — a hint about the token type, not proof of validity.
- `Authorization: Basic`: one way to authenticate the **Resource Server to the AS**, if the AS supports `client_secret_basic`.
- Introspection URI: trusted AS endpoint, supplied by server-side configuration.
- HTTPS/TLS: required to protect both the Basic credentials and the access token in the request.

Some AS implementations support authentication methods other than HTTP Basic, such as a service Bearer token, mTLS, or a JWT client assertion. **RFC 7662 requires the endpoint to be protected, without mandating a single client authentication scheme.** Follow your AS's actual contract.

### 2.2. HTTP Response

When the token is active:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read orders.export",
  "client_id": "web-storefront",
  "aud": ["orders-api"],
  "exp": 2000000000
}
~~~

When the token is no longer active:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
~~~

**HTTP 200 does not mean the token is active**; status lives in the JSON `active` field. RFC 7662 does not require every response to include `sub`, `aud`, or `exp`; attributes beyond `active` depend on the token profile and authorization policy.

The AS must restrict who can introspect because the endpoint can disclose token status, user identity, or scopes. A Billing API RS should not by default be allowed to query metadata for every token issued to the Orders API.

### 2.3. Sequence Diagram

~~~mermaid
sequenceDiagram
    participant Caller as OAuth Client
    participant RS as WebFlux Resource Server
    participant Int as ReactiveOpaqueTokenIntrospector
    participant AS as Authorization Server
    Caller->>RS: Authorization: Bearer T
    RS->>Int: introspect(T)
    Int->>AS: POST form token=T + Basic RS credential
    AS->>AS: Verify RS identity/introspection permission
    AS->>AS: Check token T status
    AS-->>Int: active + attributes
    alt active=true
        Int-->>RS: OAuth2AuthenticatedPrincipal
        RS->>RS: Authorization by scopes/ACL
        RS-->>Caller: 2xx or 403
    else active=false
        Int-->>RS: Authentication failure
        RS-->>Caller: Typically 401
    else bad RS credential / AS error
        AS-->>Int: 401/403/5xx or timeout
        Int-->>RS: No trusted token decision
        RS-->>Caller: Fail closed per exception policy
    end
~~~

**An RS authentication failure against the AS is not a user login failure.** These are two independent HTTP exchanges and must have independent error diagnostics.

## 3. Who Owns `client_id` and `client_secret` in Introspection?

Suppose the Orders API application is provisioned by the AS with:

~~~text
Introspection endpoint:
  https://id.example.test/oauth2/introspect

Resource Server client_id:
  orders-api-introspector

Resource Server client_secret:
  <SECRET_STORED_IN_SECRET_MANAGER>

Permitted resource/audience:
  orders-api
~~~

A user's JWT or opaque access token may carry `client_id=web-storefront`, yet the RS still uses **orders-api-introspector** when calling introspection.

Do not confuse:

- `client_id` in the introspection credential: identity of the **Resource Server** communicating with the AS.
- `client_id` in the introspection response: typically the identity of the **OAuth client that was issued the token**.
- `sub` in the introspection response: subject of the access token, not the RS introspection client.
- `scope`: delegated scope of the token, not the RS's permissions on the introspection endpoint.

RS credentials should follow **least privilege**. If the AS supports resource scoping, use per-API introspection credentials and allow the RS to query only tokens intended for itself.

## 4. HTTP Basic: More Than Just Base64

An HTTP Basic header has the syntax:

~~~http
Authorization: Basic <BASE64_OF_USERNAME_COLON_PASSWORD>
~~~

Base64 **is not encryption**; anyone reading the header can decode the username and password. HTTPS with server certificate and hostname verification is therefore essential.

### 4.1. OAuth Client-Secret Basic Has Specific Encoding Rules

**RFC 6749 Section 2.3.1** specifies that when an OAuth client uses HTTP Basic, `client_id` and `client_secret` are encoded using `application/x-www-form-urlencoded` before being used as the Basic username and password.

This matters for:

- Spaces.
- `:` and `+` characters.
- `&`, `=`, and `%` characters.
- Unicode/non-ASCII characters.

If you manually concatenate:

~~~java
String basic = Base64.getEncoder().encodeToString(
    (clientId + ":" + clientSecret).getBytes(StandardCharsets.UTF_8)
);
~~~

that approach **does not implement OAuth form encoding accurately in all cases**.

When using the `SpringReactiveOpaqueTokenIntrospector` builder, pass **unencoded values** to `clientId(...)` and `clientSecret(...)`; the builder handles encoding. If you build a `WebClient` manually, ensure HTTP Basic is constructed according to OAuth/AS requirements.

### 4.2. Never Pass Secrets in the Query String

Never send:

~~~http
GET /oauth2/introspect?token=T&client_secret=...
~~~

RFC 7662 uses a POST form body. Putting secrets or access tokens in URL query parameters can expose them in access logs, browser history, proxies, CDNs, or tracing. Even form bodies require redaction in logs/APM.

### 4.3. Do Not Treat a Basic Secret as a Service Bearer Access Token

Wrong:

~~~http
Authorization: Bearer <RS_CLIENT_SECRET>
~~~

A client secret is not an OAuth access token. If the AS requires Bearer authentication to authorize introspection, the RS must obtain a **dedicated service access token** with the right audience/scope—never turn a client secret into a Bearer token by swapping the prefix.

## 5. Default Configuration in Spring Boot WebFlux

### 5.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot may prefer the Servlet application type. Check your application's actual web stack; this lesson targets WebFlux.

### 5.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

These are the three primary properties for default opaque introspection. `OAUTH_INTROSPECTION_CLIENT_SECRET` is injected from runtime/secret manager, **never a plaintext secret committed to Git**.

In Spring Boot, when no other introspector bean overrides it, these properties can be used to auto-configure the default **`ReactiveOpaqueTokenIntrospector`** for the Resource Server.

### 5.3. WebFlux SecurityWebFilterChain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

`oauth2ResourceServer(...opaqueToken(...))` enables Bearer authentication via introspection. `hasAuthority("SCOPE_orders.read")` checks the scope once the token is active and Spring Security creates authorities.

**`anyExchange().authenticated()` does not replace object-level permissions.** Even a token with `orders.read` must not automatically allow reading an order belonging to another tenant.

### 5.4. When Do You Not Need a Custom WebClient?

If the AS uses standard Basic client credentials, Boot properties and `opaqueToken(Customizer.withDefaults())` are usually enough. Avoid writing a custom HTTP client just to reimplement built-in behavior, as it is easy to:

- Forget the Basic header.
- Attach credentials to the wrong request.
- Disable TLS verification.
- Leak tokens into request logs.
- Lose Spring Security's error handling.

## 6. Explicit Configuration with SpringReactiveOpaqueTokenIntrospector

### 6.1. Reactive Interface

In WebFlux, the interface is:

~~~java
org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector
~~~

Its conceptual method is:

~~~java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
~~~

Do not confuse it with Servlet `OpaqueTokenIntrospector`, which returns synchronously. When writing custom reactive introspection, never call `block()` in the request pipeline.

### 6.2. Builder with Client ID/Secret

Spring Security 6.5+ supports the builder:

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

@Configuration
public class ReactiveIntrospectionConfig {

    @Bean
    ReactiveOpaqueTokenIntrospector introspector(
            @Value("${app.security.introspection.uri}") String uri,
            @Value("${app.security.introspection.client-id}") String id,
            @Value("${app.security.introspection.client-secret}") String secret) {

        return SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(id)
            .clientSecret(secret)
            .build();
    }
}
~~~

Custom YAML properties:

~~~yaml
app:
  security:
    introspection:
      uri: https://id.example.test/oauth2/introspect
      client-id: orders-api-introspector
      client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

**Pass raw ID and raw secret to the builder**, without pre-URL-encoding, because the builder applies its own encoding.

The legacy constructor `new SpringReactiveOpaqueTokenIntrospector(uri, id, secret)` was deprecated starting in Spring Security 6.5. On versions that support the builder, prefer the builder. On older versions, consult that version's API.

### 6.3. Declaring Your Own Bean Replaces the Default

If the application declares a `ReactiveOpaqueTokenIntrospector` bean, Boot auto-configuration generally backs off. Therefore, your custom bean must maintain:

- Correct URI and HTTPS endpoint.
- Correct credentials/authentication mechanism.
- Correct HTTP method and form body.
- `active` and response-contract verification.
- Error handling / fail-closed behavior.
- Timeouts and transport policy.

Never create a custom bean returning `Mono.just(principal)` for every token just to bypass remote introspection: that is an **authentication bypass**.

### 6.4. Configuration via ServerHttpSecurity DSL

Instead of a bean, you can configure it directly:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        @Value("${app.security.introspection.uri}") String uri,
        @Value("${app.security.introspection.client-id}") String id,
        @Value("${app.security.introspection.client-secret}") String secret) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque
                .introspectionUri(uri)
                .introspectionClientCredentials(id, secret)
            )
        )
        .build();
}
~~~

This is an **alternative** to Boot properties or a custom bean. Do not configure different secrets in multiple places and assume they merge the way you expect.

## 7. Custom WebClient: You Must Configure Basic Authentication Yourself

### 7.1. Why Use a Custom WebClient?

Common needs include:

- Connect/read/response timeouts per SLO.
- Outbound proxy or egress policy.
- Connection pooling and concurrency limits.
- mTLS client certificate and truststore.
- HTTP tracing with redaction.
- A non-default client authentication scheme.

Spring Security provides the `SpringReactiveOpaqueTokenIntrospector(String, WebClient)` constructor in supported versions. When passing your own WebClient, **that WebClient must handle authenticating to the introspection endpoint itself**; never assume Boot automatically injects Basic client ID/secret.

### 7.2. HTTP Basic WebClient Example with Reactor Netty Timeouts

~~~java
package com.example.orders.security;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class IntrospectionHttpClientConfig {

    @Bean
    ReactiveOpaqueTokenIntrospector introspector(
            @Value("${app.security.introspection.uri}") String uri,
            @Value("${app.security.introspection.client-id}") String id,
            @Value("${app.security.introspection.client-secret}") String secret) {

        HttpClient transport = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
            .responseTimeout(Duration.ofSeconds(2));

        // RFC 6749 client_secret_basic: form-encode values first.
        String basicUsername = URLEncoder.encode(
            id, StandardCharsets.UTF_8);
        String basicPassword = URLEncoder.encode(
            secret, StandardCharsets.UTF_8);

        WebClient client = WebClient.builder()
            .clientConnector(
                new ReactorClientHttpConnector(transport))
            .defaultHeaders(headers -> headers.setBasicAuth(
                basicUsername,
                basicPassword
            ))
            .build();

        return new SpringReactiveOpaqueTokenIntrospector(
            uri, client);
    }
}
~~~

Both timeouts are **illustrative values**, not universal recommendations. Never configure Basic credentials on a shared `WebClient` used for other hosts, because `defaultHeaders(...)` would send those credentials to unintended destinations.

The encoding distinction is crucial:

- With the **builder `withIntrospectionUri(...).clientId(...).clientSecret(...)`**, pass **raw values**.
- With **custom `WebClient#setBasicAuth`** above, the code intentionally applies `URLEncoder` first to comply with OAuth `client_secret_basic`.
- Never URL-encode beforehand and then pass to the builder, which causes double encoding.
- Never split Basic strings on colons inside secrets in application logic; use a proper HTTP library.

### 7.3. Never Send Basic Credentials to Untrusted URLs

A `WebClient` with a default Basic header **must never** take the endpoint URL from a request:

~~~java
// Bad idea: URI controlled by the caller.
String uri = request.queryParams().getFirst("introspectUrl");
~~~

If code uses that URI with a WebClient carrying Basic credentials, an attacker can achieve **SSRF and credential exfiltration**.

Instead, use endpoints **managed server-side** via a host/issuer allowlist. If the AS returns a redirect to a different host, do not follow redirects automatically while forwarding Basic credentials without evaluating trust policy.

## 8. Other Introspection Authentication Methods

### 8.1. `client_secret_basic`

~~~http
Authorization: Basic <RS_CLIENT_ID_AND_SECRET>
Content-Type: application/x-www-form-urlencoded

token=<CALLER_ACCESS_TOKEN>
~~~

This is the most common mechanism, well supported by Spring Boot properties and the builder. Secrets must remain on the backend and travel over HTTPS.

### 8.2. `client_secret_post`

Some AS implementations expect client credentials in the form body:

~~~http
POST /oauth2/introspect HTTP/1.1
Content-Type: application/x-www-form-urlencoded

token=<CALLER_ACCESS_TOKEN>&client_id=<RS_ID>&client_secret=<RS_SECRET>
~~~

This is **not** a default behavior you can assume from `client-id`/`client-secret` properties. It requires custom integration matching the AS contract.

Risk: client secrets in form bodies are easily leaked by request-body logging/APM. Do not also send Basic credentials at the same time unless the profile explicitly requires it.

### 8.3. Dedicated Service Bearer Token for Introspection

RFC 7662 allows an AS to protect the endpoint with an OAuth access token issued to the RS:

~~~http
POST /oauth2/introspect HTTP/1.1
Authorization: Bearer <RS_INTROSPECTION_SERVICE_TOKEN>
Content-Type: application/x-www-form-urlencoded

token=<CALLER_ACCESS_TOKEN>
~~~

These two tokens are **distinct**. The RS may need a separate OAuth2 client-credentials flow to fetch its service token, cache it per `exp`, and rotate credentials. In WebFlux, fetching that token should use a reactive OAuth2 Client/WebClient—never `block()` on the event loop.

Never blindly forward the incoming Bearer token into the outbound `Authorization` header.

### 8.4. mTLS Client Authentication

With mTLS, the AS may require the RS to present a **client certificate** during the TLS handshake. The RS needs:

- A private key and client certificate registered/permitted by the AS.
- A truststore verifying the AS certificate.
- Proper hostname verification and SNI.
- Certificate rotation and expiry alerting.
- Matching HTTP client and egress proxy configuration.

**RFC 8705** describes OAuth 2.0 mutual-TLS client authentication and certificate-bound access tokens. Do not assume every introspection endpoint supports mTLS just because another AS endpoint does.

mTLS authenticating the RS **does not** replace token `active`/scope/audience checks.

### 8.5. `private_key_jwt`

Some AS implementations accept a JWT assertion signed by the RS:

~~~text
client_assertion_type =
  urn:ietf:params:oauth:client-assertion-type:jwt-bearer

client_assertion =
  <JWT_SIGNED_BY_RS_PRIVATE_KEY>
~~~

The assertion may contain:

~~~json
{
  "iss": "orders-api-introspector",
  "sub": "orders-api-introspector",
  "aud": "https://id.example.test/oauth2/introspect",
  "iat": 1900000000,
  "exp": 1900000060,
  "jti": "unique-assertion-id"
}
~~~

This is an illustrative payload only, without a real signature. The AS must verify client identity, signature, audience, expiration, replay protection, and key registration. **`introspectionClientCredentials(id, secret)` does not generate private-key JWT assertions automatically.** Custom integration matching the AS is required.

### 8.6. Comparison

| Mechanism | RS credential | Where sent | Typical configuration |
|---|---|---|---|
| `client_secret_basic` | ID + secret | Basic header | Spring Boot properties/builder |
| `client_secret_post` | ID + secret | Form body | Custom integration per AS |
| Service Bearer token | RS access token | Authorization Bearer | Reactive OAuth2 Client + custom introspector |
| mTLS | Client certificate/key | TLS handshake | HTTP client SSL configuration |
| `private_key_jwt` | Private key signing assertion | Form fields | JWT signing / custom integration |
| No RS authentication | None | None | Fails to satisfy RFC 7662 endpoint protection |

## 9. Introspection Secrets Must Never Reach the Frontend

An SPA/browser OAuth client is typically a **public client** and cannot safely store a client secret in a JavaScript bundle. Never put introspection secrets into `NEXT_PUBLIC_*`, `VITE_*`, or HTML.

Safe path:

~~~text
Browser SPA
    | Bearer user access token
    v
Orders Resource Server
    | Basic orders-api-introspector credential
    v
Authorization Server
~~~

If a Spring application is both an OAuth2 Login client and a Resource Server, the two configurations can differ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          browser-login:
            client-id: web-login-client
            client-secret: ${WEB_LOGIN_CLIENT_SECRET}

      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

This example only distinguishes credentials; it is not a full OIDC login setup. Never share one secret across frontend, OAuth login, and introspection merely to reduce configuration entries.

## 10. Secret Management and Rotation Lifecycle

### 10.1. Storing and Injecting Credentials

Prefer:

- Secret manager/Vault or managed secret service.
- Environment variables injected by the OS/orchestrator with proper RBAC.
- Kubernetes Secrets with RBAC and encryption at rest per policy.
- Keystore/HSM for private keys and mTLS credentials.

Avoid hardcoding in Java/YAML committed to Git, command-line arguments, logs, screenshots, metric labels, or crash reports.

Environment variables are not inherently completely confidential: admin/process inspection or crash dumps can read them. Design permissions and lifecycles accordingly.

### 10.2. Secret Rotation

A practical procedure:

1. The AS issues a new credential with a bounded overlap window if supported.
2. Update the secret manager.
3. Roll out/refresh RS instances to pick up the new credential.
4. Verify outbound HTTP introspection calls succeed via test/staging and metrics.
5. Revoke the old credential after confirming all replicas have switched.
6. Monitor 401s from the AS without logging either the old or new secret.

Many `@Value` fields and `WebClient` default headers are initialized **once at startup**. Updating a secret in the secret manager alone does not guarantee running instances automatically update their Basic header. A rolling restart or an explicit refreshable credential provider may be needed.

### 10.3. Least Privilege per Resource Server

Do not share one introspection credential across every microservice if the AS supports separate permissions:

~~~text
orders-api-introspector  -> orders-api tokens
billing-api-introspector -> billing-api tokens
users-api-introspector   -> users-api tokens
~~~

A compromised service must not be able to introspect tokens for all services. The AS can enforce permissions/metadata per RS client, while the RS still enforces audience and local authorization per the contract.

## 11. Multi-Issuer: Do Not Send Credentials to the Wrong Place

A system might trust two Authorization Servers:

~~~text
AS-A:
  https://as-a.example.test/introspect
  client: orders-a / secret-a

AS-B:
  https://as-b.example.test/introspect
  client: orders-b / secret-b
~~~

**Never send `secret-a` to AS-B**, and never send tenant B's user token to AS-A without an explicit contract. A safe design needs a trusted registry:

~~~mermaid
flowchart TD
    A["Request enters API"] --> B["Trusted route/tenant mapping"]
    B --> C{"Which allowlisted AS?"}
    C --> D["AS-A endpoint + credential A"]
    C --> E["AS-B endpoint + credential B"]
    D --> F["Reactive introspector A"]
    E --> G["Reactive introspector B"]
    F --> H["Validated principal"]
    G --> H
    H --> I["Scope + tenant/ACL authorization"]
~~~

Never use an **unverified** `iss` or a caller-supplied query/header as an arbitrary introspection URL. With opaque tokens, you cannot reliably parse the token to discover a trusted issuer.

You can use multiple `SecurityWebFilterChain` beans with matchers/`@Order` per API route, or a managed composite introspector. Check which chain matches first so a broad chain does not accidentally pick the wrong credentials.

## 12. AS 401 Errors Differ from 401 Errors Returned to API Clients

There are two HTTP exchanges:

~~~text
Exchange 1:
  Caller -> Resource Server API
  Authorization: Bearer <USER_ACCESS_TOKEN>

Exchange 2:
  Resource Server -> AS introspection
  Authorization: Basic <RS_CREDENTIAL>
  Body: token=<USER_ACCESS_TOKEN>
~~~

| Result from AS | Valid conclusion | Invalid conclusion |
|---|---|---|
| 200, `active:true` | AS confirmed token is active at query time | Caller has all permissions |
| 200, `active:false` | Token is inactive | RS credentials are wrong |
| 401 from introspection endpoint | RS client auth may be wrong or missing | User token is definitely expired |
| 403 from introspection endpoint | RS may lack permission to introspect | User lacks an OAuth scope on the API |
| 429 | AS rate limiting | Token was revoked |
| 5xx | AS infrastructure error | Assume `active=true` |
| TLS/connect/read timeout | No trusted decision | Safe to skip introspection |

If the client secret is wrong, every request carrying a Bearer token can fail. **Asking users to log in again will not fix an RS credential rotation error.**

When the AS does not respond, the RS must **fail closed**—never construct an authenticated principal by guessing. The final HTTP status sent to callers depends on exception handling; avoid turning every network error into `invalid_token` and forcing clients into endless token refreshes.

### 12.1. An Active Request Missing Scope

If introspection returns:

~~~json
{
  "active": true,
  "scope": "profile"
}
~~~

while the URL rule requires `SCOPE_orders.read`, RS authentication may succeed, yet **authorization typically returns 403**. This is distinct from the AS rejecting the RS Basic credential.

### 12.2. Controlled Retries

Never retry `active:false`—that is a token decision. Never retry 401 client auth indefinitely—the secret may be wrong.

For 429/5xx/timeouts, you can apply:

- Connect/response timeouts.
- Retry budget and exponential backoff with jitter.
- Circuit breaker / bulkhead.
- Outbound rate limiting.
- AS availability alerting.

**Never fail open** just to keep the API returning 200 during an AS outage. Opaque introspection is an authentication-path dependency.

## 13. TLS, Proxies, and Credential-Leak Risks

### 13.1. Protecting Two Secrets in One Request

Outbound introspection carries:

1. The RS credential in the Basic header, service token, client assertion, or mTLS handshake.
2. The caller's access token in the `token` form field.

Therefore, enforce HTTPS, server certificate verification, a trusted host allowlist, egress restrictions, and log redaction. Never disable SSL verification because of truststore errors.

### 13.2. Dangerous Redirects

A `WebClient` with a default Basic header should never automatically follow redirects to another host carrying credentials. When an AS endpoint URL changes, update configuration through an approved process; never trust redirects from a compromised network or AS.

### 13.3. Never Log HTTP Wire Data

Avoid logging:

~~~text
Authorization: Basic Zm9vOmJhcg==
Authorization: Bearer <USER_TOKEN>
token=<USER_TOKEN>
client_secret=<SECRET>
~~~

Basic Base64 can be decoded. APM, tracing, and logging must redact request headers and form bodies, not just JSON responses.

Emit metrics instead:

~~~text
component=reactive-introspection
asHost=id.example.test
result=client_auth_failed
asHttpStatus=401
latencyMs=48
requestId=req-f71a
credentialVersion=v2
~~~

`credentialVersion` is a non-sensitive identifier managed by your system if available; never use the actual secret as an identifier.

## 14. Availability, Latency, and Caching

### 14.1. Introspection Introduces a Network Dependency

Without caching, every HTTP Bearer request can trigger a remote POST. This increases:

- Request latency p50/p95/p99.
- Load on the Authorization Server.
- Dependency on DNS, TLS, proxies, and the AS database.
- Outbound connection count and token-spray DoS exposure.

The Resource Server should set timeouts aligned with SLOs, limit concurrency, and track errors by root cause.

### 14.2. Caching Does Not Fix Secret Errors

A positive cache can allow previously introspected tokens to keep working during the TTL, but cache misses still require valid RS credentials. After a credential rotation that an RS missed, behavior may become inconsistent between cache hits and misses.

Caching `active:true` also delays revocation detection. Never retain stale positive results indefinitely during an AS outage. TTLs must align with the security contract, token expiry, and revocation requirements.

### 14.3. Do Not Confuse JWKS Caching with Introspection

A JWKS cache holds public signing keys for offline JWT verification. An introspection cache stores active/principal decisions. **JWKS does not authenticate the RS to the introspection endpoint** and does not eliminate the client secret.

## 15. Testing Outbound Basic Authentication

A WebFlux URL authorization test using `mockOpaqueToken()` **does not prove** the RS sent an HTTP POST or attached the right Basic credentials. To test outbound authentication, use an HTTP test server.

### 15.1. Test Dependencies

Example with MockWebServer and Reactor Test:

~~~groovy
dependencies {
    testImplementation 'com.squareup.okhttp3:mockwebserver'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

If dependency management does not specify a version, declare a compatible version. The test server runs locally only; **never run plain HTTP introspection over the Internet in production**.

### 15.2. Testing the Outbound Request

~~~java
package com.example.orders.security;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class IntrospectionClientAuthTest {

    @Test
    void sendsBasicClientCredentialsAndTokenInFormBody()
            throws Exception {

        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(
                new MockResponse()
                    .setResponseCode(200)
                    .setHeader("Content-Type", "application/json")
                    .setBody("""
                        {
                          "active": true,
                          "sub": "test-user",
                          "scope": "orders.read"
                        }
                        """)
            );

            ReactiveOpaqueTokenIntrospector introspector =
                SpringReactiveOpaqueTokenIntrospector
                    .withIntrospectionUri(
                        server.url("/introspect").toString())
                    .clientId("test-rs")
                    .clientSecret("test-secret")
                    .build();

            StepVerifier.create(
                introspector.introspect("test-access-token"))
                .assertNext(principal ->
                    assertThat(principal.getName())
                        .isEqualTo("test-user"))
                .verifyComplete();

            RecordedRequest request = server.takeRequest();

            assertThat(request.getMethod()).isEqualTo("POST");
            assertThat(request.getPath()).isEqualTo("/introspect");

            String authorization =
                request.getHeader("Authorization");

            assertThat(authorization).startsWith("Basic ");

            String decoded = new String(
                Base64.getDecoder().decode(
                    authorization.substring(6)),
                StandardCharsets.UTF_8
            );

            assertThat(decoded).isEqualTo("test-rs:test-secret");
            assertThat(request.getBody().readUtf8())
                .contains("token=test-access-token");
        }
    }
}
~~~

These are **test values**, not production credentials. When running, use compatible JUnit/MockWebServer versions. For client IDs/secrets containing special characters, add tests verifying OAuth `application/x-www-form-urlencoded` encoding rather than testing only simple ASCII credentials.

### 15.3. Additional Failure Cases to Test

| Test case | Expectation |
|---|---|
| AS returns `200 active:true` | Principal is created |
| AS returns `200 active:false` | No authenticated principal is created |
| AS returns 401 due to bad Basic | RS client-auth failure detected |
| AS returns 403 | Missing RS introspection permission detected |
| AS returns 429 | Does not retry indefinitely |
| AS returns 5xx | Fails closed and emits infrastructure telemetry |
| Timeout / TLS failure | No principal created |
| Client secret contains `:`, `+`, Unicode | Proper OAuth Basic encoding |
| Proxy strips Authorization | Test catches missing Basic header |
| Introspection URI changed to another host | Does not send secret to untrusted host |
| Valid caller token missing scope | URL authorization denies, typically 403 |
| Credential rotation | RS uses the new credential version after rollout |

Never treat `active:false` as proof that RS Basic credentials failed; that is a token decision, not a client authentication error.

## 16. WebTestClient `mockOpaqueToken` Tests Permissions, Not Credentials

Spring Security Test provides a reactive helper:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
~~~

With `WebTestClient` integrated with Spring Security test support:

~~~java
client.mutateWith(
        mockOpaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

This helper creates a test `BearerTokenAuthentication`, bypassing remote introspection. It is suitable for testing HTTP authorization by scope, but **does not verify**:

- Whether the introspection client ID/secret are valid.
- Whether the outbound Authorization header is Basic or Bearer.
- Whether the HTTP POST `token` form body is formatted properly.
- How the system behaves when the AS returns `active:false` or 401.
- TLS, rotation, timeouts, or introspection client permissions.

Maintain **two separate test tiers**: test the HTTP client/introspector against a mock AS, and test URL/method authorization with `WebTestClient`.

## 17. Runbook: Distinguishing Client Credential Failures from Access Token Failures

### 17.1. Widespread Request Failures After Secret Rotation

Check:

1. Did the AS rotate or revoke the old secret?
2. Which credential version is the secret manager serving?
3. Did RS replicas restart/refresh if beans read `@Value` at startup?
4. Did the AS switch client auth from Basic to mTLS or private-key JWT?
5. Are outbound headers using proper Basic and OAuth form encoding?
6. Does the Client ID belong to the right AS realm/tenant/resource?
7. Is a proxy or egress gateway stripping or modifying `Authorization`?
8. Did the URI, host, or TLS certificate change?

Do not tell all users to log in again when the root cause is an RS credential failure.

### 17.2. AS Returns `active=false` Even for Newly Issued Tokens

Check whether the token being introspected is an actual access token, whether it is intended for this RS, whether the AS node has synchronized token state, whether the grant was disabled, and whether the RS credential is permitted to introspect tokens for that resource.

Never hardcode `active=true` to keep the API running temporarily.

### 17.3. Spikes in Timeouts and Rate Limits

Check introspection RPS, tail latency, AS availability, HTTP client connection pooling, retries, token-spray traffic, and caching policy. Never fail open or retry indefinitely.

### 17.4. SSL/mTLS Handshake Errors

Check CA trust, SAN/hostname, certificate expiry, SNI, client keystore/keypair, file permissions, and egress proxies. **Never disable certificate verification** to fix errors.

## 18. Pitfalls to Avoid

### "The incoming Bearer token also authenticates the RS to the AS"

No. In Basic introspection, the caller's token goes in the `token` form field; the RS sends its own client credential in the outbound header.

### "Base64 Basic is secret encryption"

No. Base64 is trivially decoded; TLS and log protection are mandatory.

### "Spring Boot client ID/secret works for every AS"

No. Mechanisms such as `client_secret_post`, mTLS, Bearer service tokens, and `private_key_jwt` may require custom AS-specific integration.

### "A custom WebClient automatically pulls the client secret from properties"

Not necessarily. When passing a custom `WebClient` to the introspector, configure authentication directly on that HTTP client.

### "HTTP 200 from the AS means allow the request"

No. `active:true` is required, along with scope, audience/resource, and local ACL checks.

### "AS 401 means the user's token expired"

Not necessarily. It may be an RS Basic credential failure.

### "Updating the secret in Vault makes every instance pick it up automatically"

Not necessarily. `WebClient` and beans may retain startup values; plan a refresh or rollout strategy.

### "Using one credential across all issuers saves effort"

Huge privilege and credential-leakage risk. Per-issuer endpoint/credential mappings must be allowlisted.

### "With mTLS, token authorization is unnecessary"

Wrong. mTLS authenticates the Resource Server to the AS; the token still must be active and authorized for the resource.

### "`mockOpaqueToken` tests prove Basic auth is configured properly"

No. It simulates an Authentication; use a mock HTTP server to verify Basic headers and form bodies.

### "Timeouts can be solved by trusting all tokens"

No. Without a trusted verification decision, fail closed; improve AS availability and observability instead.

## 19. Implementation Checklist

1. The introspection endpoint uses **HTTPS** and belongs to a trusted host allowlist.
2. The RS uses **its own credentials**, never the caller's token as client authentication.
3. The required AS mechanism is confirmed: Basic, post, mTLS, service Bearer, or JWT assertion.
4. For Basic, client ID/secret are encoded per the OAuth contract without double-encoding.
5. Secrets come from a protected secret manager/environment, never committed to Git or frontend code.
6. Custom `WebClient` instances configure proper client authentication and target only trusted AS hosts.
7. Never follow arbitrary redirects while carrying Basic credentials.
8. The AS scopes the RS's introspection permissions per resource/tenant where supported.
9. Never confuse HTTP `401/403` from the introspection endpoint with `active:false`.
10. AS outages, timeouts, and TLS errors **never** produce an authenticated principal.
11. Rotation runbooks, alerts, and refresh/restart procedures are clearly established.
12. Logs and metrics never contain Basic headers, bearer tokens, or form bodies.
13. Outbound POST/Basic/form behavior and error responses are tested with a mock AS.
14. Authorization is tested independently using `WebTestClient.mockOpaqueToken()`.
15. With multiple AS instances, each introspection endpoint has its own credential and a trusted matcher/registry.

## 20. Summary

**The Resource Server must prove its own identity when asking the Authorization Server about a token.** Treat this as a separate machine-to-machine channel:

~~~text
Client -> Resource Server:
    Authorization: Bearer <CALLER_TOKEN>

Resource Server -> Introspection endpoint:
    Authorization: Basic <RESOURCE_SERVER_CREDENTIAL>
    Form body: token=<CALLER_TOKEN>

Authorization Server:
    Authenticate Resource Server
    Verify introspection permission
    Return active + token attributes

Resource Server:
    Create Authentication only when token is valid
    Enforce scope + business authorization
~~~

In Spring WebFlux, the simplest option for an AS supporting Basic is **Boot `opaquetoken.introspection-uri/client-id/client-secret`** or the **`SpringReactiveOpaqueTokenIntrospector` builder**. Customize the `WebClient` only when you need to change transport or credential profiles. When customizing, preserve HTTPS, proper Basic encoding, secret isolation, fail-closed handling, and outbound request tests.

### References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 2.3.1 Client Password](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication](https://www.rfc-editor.org/rfc/rfc7523)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication](https://www.rfc-editor.org/rfc/rfc8705)
- [Spring Security Reference — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Boot Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security API — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security Reference — Testing OAuth 2.0 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
