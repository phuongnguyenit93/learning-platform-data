# 10.11. Customizing the HTTP Client, Timeouts, TLS, and Proxy Connections

## 1. Problem: An OAuth2/OIDC Client Must Connect Outbound

In the **Spring Security OAuth 2.0 OIDC Client** module, after the user logs in and the Authorization Server (AS) redirects the browser back to the callback with an authorization code, the application must call the **Token Endpoint** to exchange the code for tokens. Beyond the initial code exchange, the application can call the same endpoint to renew tokens with a refresh token or obtain access tokens via the `client_credentials` grant.

Example request for a confidential client's Authorization Code Grant:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_OF_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=authorization_code&code=CODE_VALUE&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo&code_verifier=ORIGINAL_PKCE_VERIFIER
~~~

This is an **HTTP request sent by the backend/client to the AS**, distinct from browser redirects. In real environments, it may require:

- Routing through a corporate **proxy**.
- Bounded timeouts so login does not hang indefinitely when the network or AS fails.
- A **TLS truststore** containing the provider's CA or an organization-approved CA.
- A **client certificate** when the AS requires mutual TLS (mTLS).
- Connection pooling, proxy authentication, secure logging, and error handling policies.
- Different mechanisms for Servlet (`RestClient`) vs. WebFlux (`WebClient`).

**Goal:** change how Spring Security **sends the HTTP request to the Token Endpoint** while letting the framework continue handling client authentication, PKCE, form bodies, token responses, OAuth2 errors, and OIDC token validation properly.

Running example:

| Component | Illustrative Value |
|---|---|
| Web application | `https://app.example.com` |
| OpenID Provider Issuer | `https://id.example.com` |
| Token Endpoint | `https://id.example.com/oauth2/token` |
| OAuth2 registration ID | `demo` |
| Optional proxy | `proxy.corp.example:3128` |
| Sample connect timeout | 3 seconds |
| Sample response timeout | 10 seconds |
| Sample TLS handshake timeout | 5 seconds |

Hosts and timeouts are purely illustrative; real systems must tune them according to network topology, actual latency, IdP SLAs, and load capacity.

## 2. Distinguish Token Endpoint Connections from Other OAuth2/OIDC Connections

An OIDC application typically uses **multiple HTTP clients or multiple HTTP transport layers**:

| Connection | Purpose | Who Executes It |
|---|---|---|
| Authorization Endpoint | Authentication/consent and issuing authorization code | **Browser** via redirect |
| Token Endpoint | Exchanging authorization code, refresh token, client credentials | **OAuth2 Client backend** |
| OIDC Discovery | Fetching metadata from `/.well-known/openid-configuration` | Discovery component when building registrations |
| JWKS Endpoint | Fetching public keys to verify ID Tokens | JWT decoder / JWK source |
| UserInfo Endpoint | Fetching user attributes per OIDC | OIDC user service |
| Resource Server API | Sending access token to fetch resources | Application's REST client |
| Logout Endpoint | Federated logout if supported by provider | Browser and/or logout components |

**Customizing the Token Endpoint's HTTP client does not automatically change the HTTP client used for Discovery, JWKS, UserInfo, or APIs.** This is critical when deploying behind firewalls/proxies: token exchange may succeed while login still fails because JWKS cannot be fetched to verify the ID Token.

Flow diagram:

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant App as Spring Security OAuth2 Client
    participant Proxy as Corporate Proxy
    participant AS as Authorization Server
    participant API as Resource Server
    Browser->>App: Start login
    App-->>Browser: Redirect to Authorization Endpoint
    Browser->>AS: Login/consent
    AS-->>Browser: Redirect callback?code=...&state=...
    Browser->>App: Authorization code callback
    Note over App: Verify state, retrieve PKCE verifier
    App->>Proxy: HTTP Token Request (timeout/TLS/proxy)
    Proxy->>AS: Connect to Token Endpoint
    AS-->>Proxy: Token response or OAuth2 error
    Proxy-->>App: Forward response
    Note over App: Verify ID Token if OIDC
    App->>API: Access token (separate connection)
    API-->>App: Data
    App-->>Browser: Application page
~~~

For direct connections, omit the proxy participant from the diagram. Over HTTPS through an HTTP `CONNECT` proxy, the application must still verify the TLS certificate of the Token Endpoint host.

## 3. The Right Spring Security Extension Points

Spring Security provides separate token response clients for Servlet and WebFlux.

| Role | Servlet/MVC | WebFlux/Reactive |
|---|---|---|
| Security configuration | `HttpSecurity` / `SecurityFilterChain` | `ServerHttpSecurity` / `SecurityWebFilterChain` |
| Authorization Code token response client | `RestClientAuthorizationCodeTokenResponseClient` | `WebClientReactiveAuthorizationCodeTokenResponseClient` |
| Contract | `OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>` | `ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>` |
| HTTP client | `RestClient` | `WebClient` |
| HTTP transport adapter | `ClientHttpRequestFactory` | `ClientHttpConnector` |
| Example transport implementation | `JdkClientHttpRequestFactory` | `ReactorClientHttpConnector` |
| How to attach client | `setRestClient(...)` | `setWebClient(...)` |

**Version note:** `RestClientAuthorizationCodeTokenResponseClient` appeared starting in **Spring Security 6.4**. In earlier versions, many Servlet projects use `DefaultAuthorizationCodeTokenResponseClient` and `RestTemplate`. Do not copy a 6.4 API assuming it exists in Spring Security 6.2/6.3.

All primary Servlet examples below target Spring Security **6.4+** with Spring Framework supporting `RestClient`. Older versions are covered separately. WebFlux examples use Reactor Netty; if you pick another transport, timeout/proxy/TLS APIs may differ.

## 4. Which Timeouts Should Be Configured?

A `POST /token` request passes through multiple stages:

~~~text
Token request starts
    |
    +-- DNS lookup / proxy selection
    |
    +-- Wait for an available connection from pool
    |
    +-- TCP connection
    |
    +-- HTTP proxy CONNECT (if applicable)
    |
    +-- TLS handshake + certificate verification
    |
    +-- Send form body (code, verifier, client authentication)
    |
    +-- AS processes token issuance transaction
    |
    +-- Receive response headers/body
    |
    +-- Parse OAuth2 token response
    |
    +-- OIDC ID Token validation, if applicable
    v
Complete
~~~

### 4.1. Connect Timeout

Bounds the time to establish a TCP connection to the peer. With a proxy, the initial peer is typically the proxy; you may also need bounds for proxy tunnel creation or TLS handshake duration.

Without a bound, login flows can hang when firewalls drop packets, links go down, or routes are unreachable.

### 4.2. Response/Read Timeout

Bounds how long to wait for a response after the connection is established. Read each implementation's exact semantics:

- JDK HTTP client wrapped by Spring's `JdkClientHttpRequestFactory` supports `setReadTimeout(Duration)`, setting the request timeout per its HTTP implementation.
- Apache HttpComponents exposes `responseTimeout` alongside separate connection pool/tunnel settings.
- Reactor Netty supports `HttpClient.responseTimeout(Duration)`.

**A response timeout does not necessarily cover DNS, pool acquisition, TLS handshake, and overall application logic.** Exact names and timing rules depend on the transport.

### 4.3. TLS Handshake Timeout

TLS happens after TCP connect and can stall or fail even when TCP succeeds. Reactor Netty provides `handshakeTimeout(...)`. For JDK/Apache HTTP clients, handshake timeout options depend on implementation and version; never assume `connectTimeout` always covers this phase.

### 4.4. Connection Pool Acquire Timeout

When a pool is saturated, requests wait for a free connection. This bound differs from connect timeout. If pool acquisition stalls, many users can hang concurrently during login or refresh.

### 4.5. Overall Deadline

A request moves sequentially through DNS, proxy, TLS, and response phases. Projects can therefore add an overall deadline aligned with UX or SLAs, while avoiding cancelling valid token-issuance transactions prematurely.

| Timeout | Mitigates Risk | Caveat |
|---|---|---|
| Connect | Hanging TCP connection | Proxy/DNS may have separate timeouts |
| Proxy CONNECT | Proxy failing to open tunnel | Applies only when using a proxy |
| TLS handshake | Stalled TLS negotiation | Never "fix" by disabling certificate verification |
| Pool acquire | Waiting too long for a connection | Requires pool sizing and queue bounds |
| Response/read | Slow AS failing to respond | Not an overall request deadline |
| Overall | Total latency exceeding UX limits | May cancel after the AS already issued tokens |

## 5. Spring Boot Client Registration Does Not Configure Transport Automatically

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: example-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          example-idp:
            issuer-uri: https://id.example.com
~~~

This tells Spring Security the **client registration, grant, scopes, and provider**. It does not configure custom timeouts, proxies, or truststores for `POST /token`.

You can define your own application-specific property group:

~~~yaml
app:
  oidc:
    token-http:
      connect-timeout: 3s
      response-timeout: 10s
      proxy-enabled: false
      proxy-host: proxy.corp.example
      proxy-port: 3128
~~~

`app.oidc.token-http.*` are **custom application properties**. Spring Security does not automatically bind them to token response clients. Bind them with `@ConfigurationProperties` or injection and pass them into your constructed HTTP client. Avoid putting client secrets, proxy passwords, or keystore passwords in plain text inside the repository.

## 6. Servlet: Dedicated `RestClient` for the Token Endpoint

In the modern Servlet stack, `RestClientAuthorizationCodeTokenResponseClient` builds token requests and parses OAuth2 token responses. It uses `RestClient` to execute HTTP calls.

When replacing the default `RestClient`, preserve:

- `FormHttpMessageConverter` to serialize the `application/x-www-form-urlencoded` request body.
- `OAuth2AccessTokenResponseHttpMessageConverter` to parse the token response.
- `OAuth2ErrorResponseErrorHandler` to handle OAuth2 error responses such as `invalid_grant`.

### 6.1. Timeout Example with JDK `HttpClient`

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.converter.FormHttpMessageConverter;
import org.springframework.security.oauth2.client.http.OAuth2ErrorResponseErrorHandler;
import org.springframework.security.oauth2.core.http.converter.OAuth2AccessTokenResponseHttpMessageConverter;
import org.springframework.web.client.RestClient;

@Configuration
public class TokenTransportConfiguration {

    @Bean
    RestClient tokenRestClient() {
        HttpClient jdkClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        JdkClientHttpRequestFactory factory =
            new JdkClientHttpRequestFactory(jdkClient);
        factory.setReadTimeout(Duration.ofSeconds(10));

        return RestClient.builder()
            .requestFactory(factory)
            .messageConverters(converters -> {
                converters.clear();
                converters.add(new FormHttpMessageConverter());
                converters.add(
                    new OAuth2AccessTokenResponseHttpMessageConverter()
                );
            })
            .defaultStatusHandler(new OAuth2ErrorResponseErrorHandler())
            .build();
    }
}
~~~

Breakdown:

1. `HttpClient.newBuilder().connectTimeout(...)` sets the connect timeout.
2. `followRedirects(NEVER)` prevents automatically following redirects to another host with secret-bearing requests; 3xx responses should be surfaced and handled per protocol.
3. `JdkClientHttpRequestFactory` bridges Spring's `RestClient` and the JDK HTTP client.
4. `setReadTimeout(...)` sets the request-level wait limit.
5. The converters ensure token requests/responses continue to follow OAuth2 parsing.
6. `OAuth2ErrorResponseErrorHandler` preserves OAuth2 error details as the framework expects.

This example uses the JDK HTTP client supported in modern Spring Framework lines; older projects or Apache HttpClient setups use different timeout APIs. The 3s/10s numbers are only starting points and must be tuned to your real environment.

### 6.2. Attaching `RestClient` to the Token Response Client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.endpoint.RestClientAuthorizationCodeTokenResponseClient;
import org.springframework.web.client.RestClient;

@Configuration
public class AuthorizationCodeTokenConfiguration {

    @Bean
    OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
            authorizationCodeTokenResponseClient(RestClient tokenRestClient) {

        RestClientAuthorizationCodeTokenResponseClient client =
            new RestClientAuthorizationCodeTokenResponseClient();
        client.setRestClient(tokenRestClient);

        return client;
    }
}
~~~

This client still builds the token request from the grant request, reads `tokenUri` from `ClientRegistration`, sends `code`, `redirect_uri`, and `code_verifier` if present, and applies the proper client authentication method. HTTP transport changes without rewriting POST token request logic.

### 6.3. Wiring into OAuth2 Login in `HttpSecurity`

In Servlet, you can specify the token response client in the DSL:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
                    authorizationCodeTokenResponseClient)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(login -> login
                .tokenEndpoint(token -> token
                    .accessTokenResponseClient(
                        authorizationCodeTokenResponseClient)
                )
            )
            .oauth2Client(client -> client
                .authorizationCodeGrant(grant -> grant
                    .accessTokenResponseClient(
                        authorizationCodeTokenResponseClient)
                )
            );

        return http.build();
    }
}
~~~

`oauth2Login().tokenEndpoint()` applies to code exchange during user login. `oauth2Client().authorizationCodeGrant()` applies to OAuth2 Client authorization code flows. In certain modern Spring Security versions, publishing the token response client bean allows auto-detection by generic type; explicit wiring makes component connections unmistakable, especially in customized apps.

If the project already has a `SecurityFilterChain` bean, merge these blocks into the active chain. Do not define multiple chains with overlapping all-path matchers unintentionally.

## 7. Servlet: Configuring a Proxy via JDK `HttpClient`

If the backend must go through a corporate proxy to reach the Token Endpoint:

~~~java
import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient jdkClient = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))
    .followRedirects(HttpClient.Redirect.NEVER)
    .proxy(ProxySelector.of(
        new InetSocketAddress("proxy.corp.example", 3128)))
    .build();
~~~

Pass this `jdkClient` into `JdkClientHttpRequestFactory`, then build `RestClient` **with full form converter, token response converter, and error handler** as in section 6.1. Each example highlights only what changed; in real code, combine them into one complete configuration.

### 7.1. How Does an HTTPS Proxy Tunnel Work?

With an HTTP `CONNECT` proxy, the client asks to open a tunnel:

~~~http
CONNECT id.example.com:443 HTTP/1.1
Host: id.example.com:443
~~~

Once the proxy allows it, the client negotiates TLS directly with the target host through the tunnel. If the proxy does not intercept TLS, the form body and response stay encrypted between client and AS. If the proxy performs **TLS inspection**, it may present substitute certificates signed by a corporate CA and inspect decrypted HTTPS payloads—a trust boundary that must be approved by the organization.

Therefore, the application must use a valid truststore; **never disable hostname verification or accept all certificates** just to get through a proxy.

### 7.2. Proxy Authentication Differs from OAuth2 Client Authentication

A proxy may require `Proxy-Authorization`, while the AS may require `Authorization: Basic ...` or a client assertion.

| Secret | Intended Recipient | Never Send To |
|---|---|---|
| Proxy password | Corporate proxy | Token Endpoint as client secret |
| OAuth2 client secret | Authorization Server | Proxy credentials or browser |
| PKCE `code_verifier` | Token Endpoint, per code | Authorization request / front channel |
| Refresh token | Token Endpoint on refresh | URLs, logs, public browser |

JDK `HttpClient.Builder.authenticator(...)` supports authentication schemes per its implementation; for HTTP `CONNECT` and specific proxy policies, verify the auth scheme is supported by both the JDK and the proxy. Manage proxy passwords via secrets, never embedded in URLs or logs.

### 7.3. No-Proxy and Multi-Provider Routing

An app may reach an internal IdP directly while reaching a partner IdP via proxy:

~~~text
id.internal.example       -> direct
login.partner.example     -> proxy.corp.example:3128
api.internal.example      -> direct
~~~

In that case, use a `ProxySelector` with explicit routing rules or separate HTTP clients per provider group. Never assume `HTTP_PROXY` or `HTTPS_PROXY` environment variables are automatically honored by every Java HTTP library.

With a shared HTTP client, pay special attention to credential-bearing requests: routing must deliver them only to **trusted endpoints**, never to arbitrary hosts taken from user input.

## 8. TLS: Truststores and Server Certificate Verification

TLS protects Token Endpoint connections carrying authorization codes, client secrets, refresh tokens, and token responses. For public CA certificates, the JVM/JDK default truststore usually suffices. For private CAs or corporate TLS inspection, the app may need a managed truststore.

### 8.1. Concepts to Distinguish

| Concept | Purpose |
|---|---|
| Server certificate | Proves the identity of the HTTPS host |
| Certificate chain | Chain of certificates leading to a trust anchor |
| Truststore | Set of CAs/certificates trusted by the client |
| TrustManager | Validates trust chains in Java |
| Hostname verification | Verifies the certificate matches the hostname in the Token Endpoint URL |
| Keystore + KeyManager | Holds/presents the client certificate and private key for mTLS |
| `SSLContext` | TLS configuration used by the HTTP transport |

Typical error:

~~~text
javax.net.ssl.SSLHandshakeException:
PKIX path building failed
~~~

Causes include an untrusted private CA, a server chain missing intermediates, an expired certificate, or TLS inspection swapping certificates. Fix it by correcting the certificate chain or trust anchors—**never by making a trust manager trust every certificate**.

### 8.2. Example Creating an `SSLContext` from a PKCS#12 Truststore

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class TokenTlsSupport {

    private TokenTlsSupport() {
    }

    public static SSLContext sslContext(
            Path trustStorePath, char[] trustStorePassword)
            throws Exception {

        KeyStore trustStore = KeyStore.getInstance("PKCS12");

        try (InputStream stream =
                 Files.newInputStream(trustStorePath)) {
            trustStore.load(stream, trustStorePassword);
        }

        TrustManagerFactory trustManagerFactory =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trustManagerFactory.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
            null,
            trustManagerFactory.getTrustManagers(),
            new SecureRandom()
        );
        return sslContext;
    }
}
~~~

Wire into JDK `HttpClient`:

~~~java
SSLContext sslContext = TokenTlsSupport.sslContext(
    Path.of("/secure/config/oidc-truststore.p12"),
    trustStorePassword
);

HttpClient jdkClient = HttpClient.newBuilder()
    .sslContext(sslContext)
    .connectTimeout(Duration.ofSeconds(3))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();
~~~

`trustStorePassword` comes from a secret manager or environment variable, never hardcoded. Loading trust anchors from a custom truststore **can replace** the default CA bundle, so ensure the store includes all required CAs. Never create a trust-all manager just because a corporate CA hasn't been installed yet.

### 8.3. Hostname Verification Must Remain Intact

Even when the truststore contains the right CA, the client must still verify that the certificate is valid for **the hostname in the token URI**. If the URL is `https://id.example.com/oauth2/token` while the certificate is only valid for another host, the connection must be rejected.

Never "fix" this by disabling hostname verification. Inspect the provider's published URL, DNS, Server Name Indication (SNI), Subject Alternative Names (SANs), and reverse proxy/IdP config.

### 8.4. Mutual TLS (mTLS) Requires a Client Keystore

If the Authorization Server requires mTLS client authentication, in addition to a truststore, the client needs its own certificate and private key:

~~~text
client-keystore.p12
  -> KeyStore.load(...)
  -> KeyManagerFactory.init(...)
  -> SSLContext.init(keyManagers, trustManagers, random)
  -> HttpClient (Token Endpoint)
~~~

mTLS does not automatically replace `client_secret_basic` or `private_key_jwt` unless the registration and AS policy state so. For certificate-bound tokens, the Resource Server also enforces sender-proof checks. Never equate a successful TLS handshake with successful OAuth2 client authentication.

### 8.5. TLS and Secret Rotation

Rotating CAs, certificates, or client keys may require recreating the `SSLContext` and HTTP client, or restarting the application depending on deployment setup. Do not assume the transport automatically reloads truststore files. Protect secrets across filesystems, containers, CI/CD, and observability.

## 9. Servlet with Legacy Library: `DefaultAuthorizationCodeTokenResponseClient`

Projects on Spring Security before 6.4 may use:

- `DefaultAuthorizationCodeTokenResponseClient`.
- `RestTemplate` / `RestOperations`.
- `setRestOperations(...)` to swap the HTTP client.

Legacy-oriented example:

~~~java
import java.time.Duration;
import java.util.List;

import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.http.converter.FormHttpMessageConverter;
import org.springframework.security.oauth2.client.endpoint.DefaultAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.http.OAuth2ErrorResponseErrorHandler;
import org.springframework.security.oauth2.core.http.converter.OAuth2AccessTokenResponseHttpMessageConverter;
import org.springframework.web.client.RestTemplate;

SimpleClientHttpRequestFactory factory =
    new SimpleClientHttpRequestFactory();
factory.setConnectTimeout(Duration.ofSeconds(3));
factory.setReadTimeout(Duration.ofSeconds(10));

RestTemplate restTemplate = new RestTemplate(factory);
restTemplate.setMessageConverters(List.of(
    new FormHttpMessageConverter(),
    new OAuth2AccessTokenResponseHttpMessageConverter()
));
restTemplate.setErrorHandler(new OAuth2ErrorResponseErrorHandler());

DefaultAuthorizationCodeTokenResponseClient client =
    new DefaultAuthorizationCodeTokenResponseClient();
client.setRestOperations(restTemplate);
~~~

This snippet shows APIs for **versions that still provide the legacy class**. Newer releases deprecate or remove it; use `RestClientAuthorizationCodeTokenResponseClient` per section 6 instead. Do not carry legacy code into Spring Security 7.x where the class no longer exists.

Similarly, if using Apache HttpComponents instead of the JDK client, connection pool/proxy/TLS timeouts must be configured on the Apache client and `HttpComponentsClientHttpRequestFactory` adapter. Never assume every implementation exposes `setConnectTimeout` with identical semantics; several methods changed or were deprecated across Spring Framework lines.

## 10. WebFlux: `WebClientReactiveAuthorizationCodeTokenResponseClient`

In **Spring Security WebFlux** apps, token exchange relies on `WebClientReactiveAuthorizationCodeTokenResponseClient`, which accepts a configured `WebClient` via `setWebClient(...)`.

When using Reactor Netty, `HttpClient` can configure:

- TCP connect timeout;
- Response timeout;
- TLS handshake timeout;
- HTTP proxy and proxy connect timeout;
- Connection pool / connection acquire timeout.

### 10.1. Creating a `WebClient` with Timeouts and Proxy

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.transport.ProxyProvider;

@Configuration
public class ReactiveTokenTransportConfiguration {

    @Bean
    WebClient tokenWebClient() {
        HttpClient netty = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
            .responseTimeout(Duration.ofSeconds(10))
            .secure(ssl -> ssl
                .handshakeTimeout(Duration.ofSeconds(5)))
            .proxy(proxy -> proxy
                .type(ProxyProvider.Proxy.HTTP)
                .host("proxy.corp.example")
                .port(3128)
                .connectTimeoutMillis(5_000));

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(netty))
            .build();
    }
}
~~~

Explanation:

- `CONNECT_TIMEOUT_MILLIS` controls TCP connection establishment.
- `responseTimeout` bounds waiting for a response in Reactor Netty.
- `handshakeTimeout` bounds TLS handshake duration.
- `proxy(...)` sets the HTTP proxy. **Omit the proxy block** in direct-connect environments.
- `ReactorClientHttpConnector` bridges the HTTP transport with Spring `WebClient`.

Proxy config can be extended with `nonProxyHosts(...)`, authentication, and per-provider routing. For HTTPS through a proxy, Reactor Netty uses HTTP `CONNECT`; the proxy must permit tunneling as required by the network.

### 10.2. Attaching `WebClient` to the Reactive Token Response Client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveAuthorizationCodeTokenResponseClient;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReactiveTokenClientConfiguration {

    @Bean
    ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
            authorizationCodeTokenResponseClient(WebClient tokenWebClient) {

        WebClientReactiveAuthorizationCodeTokenResponseClient client =
            new WebClientReactiveAuthorizationCodeTokenResponseClient();
        client.setWebClient(tokenWebClient);
        return client;
    }
}
~~~

In Spring Security WebFlux versions that auto-detect token response client beans by generic grant type, OAuth2 Client components pick this up automatically. If your app defines a custom reactive authentication manager or `ReactiveOAuth2AuthorizedClientManager`, ensure it references the right token response client.

Do not hand-code `webClient.post()` to exchange codes just to add a proxy. `WebClientReactiveAuthorizationCodeTokenResponseClient` still needs to manage form requests, PKCE verifiers, parsing, and OAuth2 errors.

### 10.3. Reactive Pipelines Must Never Block the Event Loop

In WebFlux, calling the Token Endpoint is I/O inside a reactive pipeline. Avoid calling `.block()` on the event loop or spawning a manual blocking thread per login. Reactor Netty runs asynchronously; configure timeouts on the client/connector or reactive pipeline operators.

If blocking TLS/secret-loading libraries must run during bean initialization, run them once at configuration startup rather than repeating blocking I/O on every token request.

## 11. WebFlux: Refresh Tokens and Connection Pools

When refreshing access tokens, that grant can use `WebClientReactiveRefreshTokenTokenResponseClient`. Do not assume customizing only the authorization code client automatically covers refresh tokens.

Example bean to add inside a `@Configuration` class:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.endpoint.OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
        refreshTokenResponseClient(WebClient tokenWebClient) {

    WebClientReactiveRefreshTokenTokenResponseClient client =
        new WebClientReactiveRefreshTokenTokenResponseClient();
    client.setWebClient(tokenWebClient);
    return client;
}
~~~

If the framework/manager is customized, wire the refresh bean into the matching provider/manager; avoid defining two beans with the same generic type without disambiguation.

### 11.1. Connection Pooling in Reactor Netty

Example creating a bounded pool:

~~~java
import java.time.Duration;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

ConnectionProvider pool =
    ConnectionProvider.builder("oidc-token-pool")
        .maxConnections(40)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofSeconds(30))
        .build();

HttpClient netty = HttpClient.create(pool)
    .responseTimeout(Duration.ofSeconds(10));
~~~

`maxConnections` caps concurrent connections, `pendingAcquireTimeout` caps waiting for a free connection, and `maxIdleTime` controls idle lifetime. The number 40 and durations above are illustrative—size them to your app load and AS/proxy limits.

Create the pool once and dispose of it cleanly on application shutdown. Never create a new pool per callback, per refresh, or per HTTP request.

### 11.2. TLS Trust in Reactor Netty

If an IdP uses an approved corporate CA, you can configure Netty's `SslContext`:

~~~java
import java.io.File;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import reactor.netty.http.client.HttpClient;

SslContext tls = SslContextBuilder.forClient()
    .trustManager(new File("/secure/config/corp-root-ca.pem"))
    .build();

HttpClient netty = HttpClient.create()
    .secure(spec -> spec.sslContext(tls));
~~~

The CA file must be trusted and protected from unauthorized modification. Specifying a custom CA can change the trusted CA set compared to the default transport; assemble the full trust chain properly. Never use `InsecureTrustManagerFactory` or bypass hostname verification. For mTLS, you also need key material and client auth configuration matching the AS.

## 12. Refresh Tokens Also Call the Token Endpoint but Need Their Own Policy

Multiple grants POST to the same Token Endpoint yet have different lifecycles.

| Grant | Purpose | Risk of Automatic Retry |
|---|---|---|
| `authorization_code` | Exchanges a single-use code | Code may already be consumed |
| `refresh_token` | Obtains a new access token | Refresh token may already be rotated |
| `client_credentials` | Fetches a service token | Aggressive retries can overload / hit rate limits |
| Token exchange / JWT bearer | Extended protocols | Depends on token assertions and AS policy |

Example in Spring Security 6.4+ Servlet sharing the same `RestClient` for the refresh client:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint.RestClientRefreshTokenTokenResponseClient;
import org.springframework.web.client.RestClient;

@Bean
OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
        refreshTokenResponseClient(RestClient tokenRestClient) {

    RestClientRefreshTokenTokenResponseClient client =
        new RestClientRefreshTokenTokenResponseClient();
    client.setRestClient(tokenRestClient);
    return client;
}
~~~

This is a method added inside a Spring configuration class, not a standalone file. When using a custom `OAuth2AuthorizedClientManager`, wire the refresh grant provider to this token client per your version's API.

### 12.1. Why Shouldn't Token Requests Be Retried Blindly?

Suppose:

~~~text
t=0s  Client POSTs /token with code K1
t=1s  AS validates and marks K1 as used
t=2s  AS issues token, starts sending response
t=3s  Proxy/network drops the response
t=10s Client hits response timeout
~~~

The Client **cannot conclude** the AS never processed the code. Retrying `K1` repeatedly will likely receive `invalid_grant` because codes are single-use. With refresh token rotation, retrying the old token can also trigger reuse detection policies.

Therefore:

- Never attach a generic retry interceptor across all `POST /token` calls.
- Distinguish pre-send connect timeouts from post-send timeouts where the AS may have processed the request.
- When an Authorization Code Grant outcome is ambiguous, you usually must **start a fresh authorization flow**.
- Where the AS and `client_credentials` allow retries, bound attempts and apply backoff.
- Never fall back by serving another principal's cached token.

## 13. Customizing Protocol Requests Differs from Customizing HTTP Transport

There are two configuration layers:

| Layer | Responsibility | Examples |
|---|---|---|
| **OAuth2 protocol** | Grant type, form body, client authentication, PKCE, token/error responses | `OAuth2AccessTokenResponseClient` |
| **HTTP transport** | DNS, connect/read timeouts, TLS, proxy, connection pool | `RestClient`/`WebClient` and factory/connector |

If you only need a proxy or timeout, swap the HTTP transport; **never rebuild the entire token request manually**. If a provider genuinely requires an extension parameter, use the token client's header/parameter customization API per Spring Security docs.

A classic mistake when replacing `RestClient` is omitting:

~~~java
new FormHttpMessageConverter()
new OAuth2AccessTokenResponseHttpMessageConverter()
new OAuth2ErrorResponseErrorHandler()
~~~

Without them, the app can fail to serialize form bodies, fail to parse access token responses, or lose OAuth2 error details. That is an HTTP client configuration bug, not an authorization code bug.

### 13.1. A Valid OAuth2 Error Response

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Authorization code expired or already used"
}
~~~

This is a **structured OAuth2 response** from the AS, not a TCP/TLS failure. The token response client must parse the error and surface sanitized information appropriately rather than treating it like arbitrary JSON.

If a provider returns non-standard errors, converter customization may be required, done carefully without dropping protocol checks.

## 14. Protecting Credentials Across Proxies, TLS, and Logging

A token request may contain:

~~~text
Authorization: Basic <client_id:client_secret>
code=<authorization-code>
code_verifier=<pkce-verifier>
refresh_token=<refresh-token>
client_assertion=<signed-assertion>
~~~

A token response may contain `access_token`, `id_token`, and `refresh_token`. This data **must never be logged** by the application, HTTP interceptors, trace spans, APM tools, or proxies without explicit protections.

### 14.1. What Is Safe to Log?

| Information | Safe to Log? | Example |
|---|---|---|
| Approved Registration ID | Yes | `demo` |
| Grant type | Yes | `authorization_code`, `refresh_token` |
| Endpoint category | Yes | `token` |
| HTTP duration | Yes | `elapsed_ms=153` |
| HTTP status | Yes | `200`, `400`, `502` |
| Sanitized OAuth2 error code | Yes | `invalid_client`, `invalid_grant` |
| Authorization code | **No** | Single-use credential |
| Client secret / client assertion | **No** | Credential |
| PKCE verifier | **No** | Per-transaction secret |
| Access/refresh/ID tokens | **No** | Credentials and assertions |
| Proxy password | **No** | Proxy credential |

When correlation is needed, generate a random trace ID containing no code or token. Never log raw `Authorization` or `Proxy-Authorization` headers. Never turn on unconditional HTTP wiretap/body logging in production around the Token Endpoint.

### 14.2. TLS Inspection Must Be Governed

If an enterprise requires proxy TLS inspection, the truststore must contain only the organization-approved corporate CA. Remember that the proxy can observe decrypted traffic; network egress and security policies must protect OAuth2 credentials and tokens accordingly.

Never install a CA from an untrusted source. Never configure global trust-all just to make one provider work.

## 15. Do Not Confuse Transport Errors with OAuth2 Protocol Errors

| Symptom | Cause Category | Where to Look |
|---|---|---|
| `ConnectException` / connect timeout | Firewall, routing, unreachable proxy | DNS/network/proxy |
| `UnknownHostException` | DNS resolution failure | Container/VPC DNS |
| `SSLHandshakeException` / PKIX | CA, certificate chain, TLS inspection | Truststore, server certificate |
| Hostname mismatch | Certificate not issued for target host | Token URI, SANs, and SNI |
| HTTP `407` | Proxy requires authentication | Proxy credentials/method |
| HTTP `502`/`503`/`504` | Proxy/gateway/upstream AS failure | Proxy/AS logs |
| Response timeout | Slow AS or dropped network/proxy response | Latency, response timeout |
| `invalid_client` | Wrong client auth method/secret/assertion | `ClientRegistration`, AS policy |
| `invalid_grant` | Used/expired code, wrong PKCE/redirect URI, invalid refresh token | Grant lifecycle |
| Token response parse error | Mismatched converter/body extractor/`Content-Type` | OAuth2 HTTP codecs |
| Code exchanged yet OIDC login fails | ID Token signature/JWKS/issuer/audience error | JWT decoder/JWKS |
| API returns `401` after login | Access token/audience/scope/API policy | Resource Server |

**Example:** increasing timeouts never fixes `invalid_client`; changing the client secret never fixes an HTTPS certificate with a wrong hostname. Accurate classification targets fixes at the component actually failing.

### 15.1. Scenario: Token Exchange Succeeds Yet JWKS Times Out

The AS returns tokens through the proxy, yet Spring Security needs the JWK Set to verify the ID Token signature. The JWKS loader uses a different HTTP client without proxy settings, so login fails.

Fix it by configuring connectivity for **JWKS**. Never disable signature verification or keep raising the Token Endpoint response timeout.

### 15.2. Scenario: Discovery Fails at Startup

`issuer-uri` tells Spring to fetch discovery metadata when creating registrations. If the discovery connection bypasses the proxy, the app may fail to start before the token response client **ever runs**.

Check network/TLS for metadata discovery or declare explicit endpoints matching the provider—changing the token client won't fix startup failures.

### 15.3. Scenario: Proxy Requires Authentication

The backend gets HTTP 407 when calling the Token Endpoint. This is an error **between client and proxy**, not the AS returning `invalid_client`. Configure proxy username/password/method on the HTTP transport rather than modifying the OAuth2 client secret.

### 15.4. Scenario: Session Lost on Callback

Spring Security cannot find the authorization request/PKCE verifier after redirect, and token exchange fails with `invalid_grant` or callback rejection. This is a session/state/callback issue, not a response timeout even though both surface during login.

## 16. Process for Deploying a Reliable Token Endpoint Connection

Follow this rollout sequence:

1. **Identify the stack:** Servlet with `RestClient` or WebFlux with `WebClient`.
2. **Identify grant types:** authorization code only, or also refresh token / client credentials.
3. **Verify client registration:** token URI, client authentication method, scopes, and redirect URI.
4. **Build a dedicated transport:** connect/read/TLS/proxy/pool configuration.
5. **Keep OAuth2 form converters/error handling:** never break protocol codecs when swapping transport.
6. **Attach transport to the right token response client:** `setRestClient` or `setWebClient`.
7. **Wire the token response client into Spring Security:** bean detection or DSL per version; include refresh token flows.
8. **Check discovery/JWKS/UserInfo paths separately:** they may use separate HTTP clients.
9. **Design safe logging:** log only status, latency, and error category—never secrets.
10. **Trace errors by phase:** DNS, connect, proxy, TLS, token response, ID Token validation.

### 16.1. Multi-Destination Network Topology Example

~~~text
Browser
    |
    v
Spring Boot App (private subnet)
    |
    +-- proxy.corp.example --> id.example.com/oauth2/token
    |
    +-- proxy.corp.example --> id.example.com/.well-known/jwks.json
    |
    +-- direct --------------> api.internal.example
~~~

The Token Endpoint path can use a custom `RestClient`, JWKS goes through the JWT decoder, and internal APIs use the app's API HTTP client. Keep network routing consistent per destination. Avoid global proxy settings that force private APIs out through an external proxy unnecessarily.

### 16.2. Environment-Specific Properties

Example custom properties bound by the application:

~~~yaml
# application-dev.yml
app:
  oidc:
    token-http:
      connect-timeout: 3s
      response-timeout: 10s
      proxy-enabled: false
~~~

~~~yaml
# application-prod.yml
app:
  oidc:
    token-http:
      connect-timeout: 3s
      response-timeout: 10s
      proxy-enabled: true
      proxy-host: proxy.corp.example
      proxy-port: 3128
~~~

Note that these **are not** automatically supported by Spring Security. Your application's HTTP client builder must explicitly read them. Never commit proxy passwords or private keys in YAML.

## 17. Applied Scenarios

### Scenario A: Read Timeout Configured Only on the API Client

The app calls APIs using a `WebClient` with `responseTimeout(10s)`, yet login still hangs for 60 seconds during code exchange.

**Explanation:** The API `WebClient` is likely a different instance from the Token Endpoint's HTTP client. Check the token response client and its transport.

### Scenario B: Private CA Certificate

Browser sign-in works, yet backend `POST /token` throws `PKIX path building failed`.

**Explanation:** The browser and backend use separate truststores. Provide the right CA/truststore to **the backend HTTP transport**—never disable TLS verification.

### Scenario C: Authorization Code Consumed After Timeout

The client times out waiting for a token response, retries the same code, and receives `invalid_grant`.

**Explanation:** The AS may have consumed the code before the response dropped. Never retry blindly; when unrecoverable, start a fresh authorization flow.

### Scenario D: Proxy Configured Yet JWKS Still Fails

The token endpoint returns access token + ID Token through the proxy, then ID Token verification fails.

**Explanation:** The separate JWKS connection needs its own proxy/truststore configuration. Never accept an unverified ID Token.

### Scenario E: App Uses Both Authorization Code and Refresh Token

Initial login succeeds, then an hour later token refresh fails due to a firewall.

**Explanation:** Customization applied only to `RestClientAuthorizationCodeTokenResponseClient`, while the refresh grant uses a separate token client. Ensure the refresh client uses the proper transport too.

### Scenario F: WebFlux App Misuses `RestTemplate`

A developer places a blocking `RestTemplate` inside a reactive login pipeline and calls `.block()` on the event loop.

**Explanation:** Use `WebClientReactiveAuthorizationCodeTokenResponseClient` with `WebClient`/Reactor Netty; avoid blocking the event loop.

### Scenario G: Proxy Returns HTTP 407

Token requests fail to reach the AS because the proxy demands authentication.

**Explanation:** Proxy credentials differ from the client secret. Configure proxy authentication on the HTTP transport properly; never pass the OAuth2 client secret as the proxy password.

## 18. Self-Check Questions

**Question 1.** Which class does Spring Security Servlet 6.4+ use to exchange an authorization code for tokens?

**Answer:** `RestClientAuthorizationCodeTokenResponseClient`, which exposes `setRestClient(...)` to customize the HTTP client.

**Question 2.** Which class does WebFlux use?

**Answer:** `WebClientReactiveAuthorizationCodeTokenResponseClient` with `setWebClient(...)` and a matching `ClientHttpConnector`.

**Question 3.** Does customizing the Token Endpoint `RestClient` automatically change how JWKS is fetched?

**Answer:** No. The JWT decoder/JWK source can use its own HTTP client; configure its connectivity separately if needed.

**Question 4.** Why shouldn't `OAuth2AccessTokenResponseHttpMessageConverter` be dropped when replacing `RestClient`?

**Answer:** Spring Security relies on it to parse OAuth2 token responses; omitting it breaks response decoding.

**Question 5.** Should you automatically retry an authorization code grant on timeout?

**Answer:** Never retry blindly; the AS may already have consumed the code. Recover safely, typically via a fresh authorization flow.

**Question 6.** What is the difference between a truststore and a keystore?

**Answer:** A truststore holds trust anchors to verify server certificates; a keystore holds the client certificate and private key for mTLS when needed.

**Question 7.** Why might raising `server.connection-timeout` have no effect?

**Answer:** Token exchange is an outbound connection. Inbound server timeouts do not govern the HTTP client sending `POST /token`.

**Question 8.** When receiving HTTP 407, what should you inspect?

**Answer:** Proxy authentication and HTTP transport configuration, not the OAuth2 client secret unless other errors appear.

## 19. Key Takeaways

| Task | Servlet | WebFlux |
|---|---|---|
| Customize token HTTP client | Create a dedicated `RestClient` | Create a dedicated `WebClient` |
| Attach to token response client | `RestClientAuthorizationCodeTokenResponseClient.setRestClient` | `WebClientReactiveAuthorizationCodeTokenResponseClient.setWebClient` |
| Connect timeout | `HttpClient.Builder.connectTimeout` | `CONNECT_TIMEOUT_MILLIS` |
| Response timeout | `JdkClientHttpRequestFactory.setReadTimeout` | `HttpClient.responseTimeout` |
| TLS | `SSLContext` / truststore | Netty `SslContext` / trusted CA |
| Proxy | JDK `ProxySelector` or matching HTTP client | Reactor Netty `proxy(...)` |
| OAuth2 form/error handling | Keep form + token converters + OAuth2 error handler | Keep reactive token response parsing/error processing |
| Refresh grant | `RestClientRefreshTokenTokenResponseClient` | `WebClientReactiveRefreshTokenTokenResponseClient` |
| JWKS/Discovery/UserInfo | Inspect connections separately | Inspect connections separately |

When customizing the Token Endpoint in Spring Security OAuth 2.0/OIDC Client, **replace the HTTP transport on the right token response client**, tune timeouts and proxies for your deployment network, enforce strict TLS verification, and preserve protocol converters and error handlers. Crucially, account for both refresh token flows and other OIDC endpoints like discovery, JWKS, and UserInfo. PKCE, client authentication, and token validation remain the responsibility of their respective Spring Security and Authorization Server components.

## Official References

- [Spring Security — Authorization Grant Support (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): `RestClientAuthorizationCodeTokenResponseClient`, `setRestClient`, token response converters, and error handler.
- [Spring Security — OAuth2 Servlet](https://docs.spring.io/spring-security/reference/servlet/oauth2/): `oauth2Login`, `oauth2Client`, token response client beans.
- [Spring Security — Authorization Grant Support (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html): `WebClientReactiveAuthorizationCodeTokenResponseClient`, `setWebClient`.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): configuring `RestClient` and request factories.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): connectors and HTTP clients in WebFlux.
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection pools, proxies, and response/connect/TLS timeouts.
