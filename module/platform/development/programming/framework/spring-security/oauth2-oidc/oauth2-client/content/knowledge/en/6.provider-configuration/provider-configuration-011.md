# 6.11. Providers on Internal Networks, TLS, and Outbound Proxies

## 1. Context: OAuth2/OIDC Providers Are Not Always on the Public Internet

In a **Spring Security OAuth 2.0/OIDC Client** application, the Authorization Server or OpenID Provider may reside on a corporate internal network, reachable only over VPN, a Kubernetes private network, a private endpoint, or an outbound proxy. Meanwhile, the application may run behind an ingress/load balancer, use certificates issued by an internal CA, and be forbidden from connecting directly to the Internet.

In such setups, getting **client ID, client secret, and scopes** right is not enough. A successful OAuth2/OIDC flow requires every involved network path to work, use matching domain names, and trust TLS certificates:

- **The user's browser** must reach the Authorization Endpoint to authenticate and grant consent.
- **The backend running Spring Security** must reach server-side endpoints such as discovery, Token Endpoint, JWKS, and UserInfo when used.
- **The identity provider** must have a valid redirect URI bringing the browser back to the application.
- **The application** must trust the provider's TLS identity, while the provider may require the application to authenticate using client secret, private key JWT, or mutual TLS (mTLS), depending on configuration.
- **Network proxies** must be applied to each relevant HTTP client; configuring a proxy for one HTTP client does not automatically route every library in the application through that proxy.

This lesson aims to accurately trace the network paths, configure providers in Spring Boot/Spring Security, and diagnose connectivity, TLS, DNS, or proxy errors without weakening authentication mechanisms.

## 2. Separating Front-Channel and Back-Channel Flows

Consider an internal web application accessed via `https://portal.example.com`, using an OIDC Provider with issuer `https://sso.corp.example/realms/staff`.

~~~mermaid
flowchart LR
    B["Employee's Browser"] -->|"1. GET /login"| A["Spring Boot Web App / BFF"]
    A -.->|"2. 302 redirect to authorization-uri"| B
    B -->|"3. Open Authorization Endpoint"| I["OIDC Provider"]
    I -.->|"4. 302 callback + code"| B
    B -->|"5. Callback /login/oauth2/code/..."| A
    A -->|"6. Token Endpoint, JWKS, UserInfo (TLS)"| I
    A -->|"7. Session cookie"| B
~~~

**Front-channel** covers the steps occurring through the browser: redirecting to the Authorization Endpoint and redirecting back to the callback. **Back-channel** covers HTTP requests executed by the backend to exchange an authorization code for tokens, discover provider metadata, or fetch JWK keys; depending on the flow, the backend also calls the UserInfo Endpoint.

| Access point | Who initiates the connection? | Might need a proxy? | Critical conditions |
| --- | --- | --- | --- |
| Authorization Endpoint | User's browser | **User machine's** proxy/VPN | Browser resolves DNS, accesses HTTPS, trusts certificate |
| Redirect URI back to app | User's browser | **Application-side** reverse proxy/ingress | Public URL, exact callback, cookies and session |
| OIDC discovery metadata | Spring backend when building config | **Backend-side** proxy or network path | Exact issuer, valid TLS and metadata |
| Token Endpoint | Spring backend | Egress proxy, private network, firewall | HTTPS connection, client authentication, grant |
| JWKS endpoint | Spring backend or token-verifying component | Backend-side proxy/network path | Fetches right keyset, trusted TLS |
| UserInfo Endpoint | Spring backend if flow uses it | Backend-side proxy/network path | Access token with right permissions, HTTPS |
| Other protected APIs | Backend when acting as OAuth2 Client | Dedicated network path to target API | Bearer access token for the right Resource Server |

Do not confuse an **egress proxy** with a **reverse proxy/ingress**:

- An **egress proxy** governs requests **going outbound from the backend to** an IdP or external API.
- A reverse proxy/ingress receives requests **coming inbound from browsers into** the application and usually forwards headers describing the external host/scheme.
- Setting `https.proxyHost` on the JVM does not help a browser reach an IdP with an internal-only domain; setting `X-Forwarded-Proto` at the ingress does not fix a token request going through an egress proxy.

### 2.1. Three Common Deployment Topologies

**Case A — Provider resides solely on the corporate network.** Employees must be in the office or on VPN for their browser to open the Authorization Endpoint. The backend must have a route to the internal network from its deployment environment (VM, container, cluster). If a browser on the Internet cannot resolve or reach the provider's private domain, login fails even when the backend can reach the Token Endpoint.

**Case B — Provider has a public hostname, yet the backend has blocked outbound traffic.** The browser can open the login page, while the backend can only reach the Token Endpoint/JWKS through an HTTP CONNECT proxy. Egress must be configured on the actual HTTP component executing token requests and discovery.

**Case C — Split-horizon DNS.** The same issuer hostname `sso.corp.example` resolves to a private address on the backend network and a public address for browsers/Internet via separate DNS servers. This can work cleanly if **the canonical URL and issuer remain consistent**, the certificate is valid for the same hostname, and both paths reach the exact same provider.

## 3. Issuer, Endpoints, DNS, and Identity Consistency

An OIDC Provider has an **issuer** as its canonical identifier, for example:

~~~text
https://sso.corp.example/realms/staff
~~~

OIDC discovery supplies a metadata document that may contain fields like:

~~~json
{
  "issuer": "https://sso.corp.example/realms/staff",
  "authorization_endpoint": "https://sso.corp.example/realms/staff/protocol/openid-connect/auth",
  "token_endpoint": "https://sso.corp.example/realms/staff/protocol/openid-connect/token",
  "jwks_uri": "https://sso.corp.example/realms/staff/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://sso.corp.example/realms/staff/protocol/openid-connect/userinfo"
}
~~~

This illustrates a provider with an endpoint structure similar to Keycloak; **actual paths must be taken from metadata/IdP administrators**. Other providers do not necessarily use these URLs.

Operational principles:

1. **The issuer must be the identity published by the provider**—never arbitrarily swap it for an internal hostname for convenience. The `iss` claim in the ID Token must match the trusted issuer.
2. Endpoints may use different hostnames if declared in provider metadata and allowed by deployment policy; each hostname must resolve, have a network route, and carry a certificate matching its name.
3. **Tokens and ID Tokens must be verified against the real issuer.** Having a reverse proxy rewrite hostname, scheme, or path must never result in skipping validation of issuer, audience, signature, or expiration.
4. Use a **hostname matching a Subject Alternative Name (SAN)** on the certificate. Connecting by IP when the certificate only lists a domain name usually causes hostname verification errors.
5. Distinguish **laptop DNS**, **container/pod DNS**, and **proxy DNS**. An HTTP CONNECT proxy can resolve the destination on the proxy side; when bypassing the proxy, the backend must resolve and route directly.
6. If the IdP sits behind a reverse proxy, the provider must know its external hostname and HTTPS scheme to emit consistent metadata and redirects. Changing `https` to `http` just to dodge a configuration error is not a valid fix.

### 3.1. Discovery May Occur Immediately at Application Startup

When Spring Boot uses `spring.security.oauth2.client.provider.<id>.issuer-uri`, building `ClientRegistration` may query OIDC/OAuth2 provider metadata during initialization. Thus an application can **fail to start** when DNS, proxy, or TLS to the IdP is not ready yet, even before any user clicks Sign In.

When startup must be independent of discovery or when the provider does not publish standard metadata, configure endpoints explicitly in a manner compatible with your Spring Security version. For OIDC, preserve issuer and ID Token checks rather than omitting the issuer property and inadvertently weakening validation. For pure OAuth2 `client_credentials`, a static Token Endpoint is usually enough to initialize the client registration without an OIDC discovery flow.

## 4. Configuring the Provider in Spring Boot

### 4.1. OIDC Login with a Canonical Issuer

Example `application.yml` for a web app using `authorization_code`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-oidc:
            issuer-uri: https://sso.corp.example/realms/staff
~~~

In the configuration:

- `corporate` is the client's **registrationId** inside Spring Security; the default login initiation path is `/oauth2/authorization/corporate`.
- `corporate-oidc` is the **provider** declaration key reused by this registration.
- `issuer-uri` points to the **official issuer**; Spring Security relies on provider metadata to locate the Authorization Endpoint, Token Endpoint, and related details.
- `redirect-uri` is the URL where the browser returns to **the application**, not a URL at the IdP. The value resolved from `{baseUrl}` must match the redirect URI registered at the IdP.
- `CORPORATE_CLIENT_ID` and `CORPORATE_CLIENT_SECRET` must be supplied via environment configuration/secrets, never hard-coded in the repository.
- The `openid` scope indicates an OIDC authentication request; access token and ID Token serve different purposes.

If the application sits behind an ingress while receiving HTTP requests internally on `http://portal-service:8080`, Spring must recognize the external URL `https://portal.example.com`; you can configure **forwarded headers** matching your trusted proxy:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Depending on platform, you can also use `native` strategy or corresponding ingress configuration. **Only accept forwarded headers from trusted reverse proxies**; never let external clients control the host/scheme used to build redirect URIs. If an environment has a fixed domain, declaring an explicit redirect URI can reduce reliance on host inference.

### 4.2. Internal Provider Used Only for `client_credentials`

For a backend running scheduled jobs or calling another API under the service's own authority, browser-based OIDC login is unnecessary:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          finance-api:
            provider: finance-auth
            client-id: ${FINANCE_CLIENT_ID}
            client-secret: ${FINANCE_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: finance.read
        provider:
          finance-auth:
            token-uri: https://token.corp.internal/oauth2/token
~~~

Here:

- The backend must reach `token.corp.internal` over the network with proper TLS and proxy/bypass rules.
- There is no browser authorization redirect and no user login session created.
- `ReactiveClientRegistrationRepository` or `ClientRegistrationRepository` holds the client configuration; an **authorized client manager** is responsible for requesting tokens and supplying them to the API-calling HTTP client.
- The Token Endpoint may require additional client authentication (mTLS, JWT assertion, or another method) per the contract with the Authorization Server.

## 5. TLS: Certificates, Trust Chains, Hostnames, and mTLS

### 5.1. What Happens During an HTTPS Connection

When the backend calls `https://sso.corp.example`, the HTTP client initiates a TLS handshake and verifies the peer's certificate. In standard configuration, verification checks:

1. The certificate is valid according to time and policy.
2. The requested hostname matches a SAN in the certificate.
3. The certificate chain leads to a **Certificate Authority (CA)** trusted by the HTTP client.
4. Algorithms, key usage, and TLS constraints meet the library/runtime security policy.

A provider using a certificate issued by an internal CA usually does not have that root CA in the JVM/container's default truststore. The typical result is an error such as **PKIX path building failed**, **unable to find valid certification path**, or **certificate verify failed**.

TLS is **not** properly configured just because "the connection succeeds." If certificate or hostname validation is disabled, a rogue server on the network path can intercept authorization codes, access tokens, or client secrets.

### 5.2. Importing an Internal CA into a Dedicated Truststore

PKI administrators supply the organization's valid **root CA** and, if needed, intermediate CAs. You can build a PKCS#12 truststore:

~~~bash
keytool -importcert +  -alias corporate-root-ca +  -file corporate-root-ca.pem +  -keystore corporate-truststore.p12 +  -storetype PKCS12
~~~

The command prompts for a truststore password if the file does not exist yet. Import only CA certificates verified through a trusted channel—**never** grab an arbitrary certificate returned by a failing endpoint and immediately trust it.

Example JVM configuration using a truststore mounted into a container:

~~~text
-Djavax.net.ssl.trustStore=/opt/app/certs/corporate-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<secret-managed-at-runtime>
~~~

These are illustrative JVM system properties; how passwords are supplied depends on your runtime platform and secret mechanism. Avoid putting passwords into Git, logs, command history, or process details readable by unauthorized users. Verify that the **actual HTTP client** in Spring Security uses the configured trust material: Netty, Apache HttpClient, or custom HTTP clients may use their own SSL contexts.

**Note:** when specifying a new truststore, the JVM may stop using the default public CA list. If the application also calls other public providers/APIs, prepare trust material covering **all trusted destinations**, or configure trust per HTTP client rather than arbitrarily replacing the global truststore.

### 5.3. Do Not Confuse Server TLS with Client Authentication

| Mechanism | Who presents credentials? | Purpose |
| --- | --- | --- |
| Standard TLS | Provider presents server certificate | Client authenticates server and encrypts connection |
| Client secret at Token Endpoint | OAuth client sends client credentials per registered method | Authorization Server authenticates the OAuth client's identity |
| mTLS | In addition to server certificate, client presents client certificate/private key | Mutual TLS authentication; can serve as an OAuth client authentication method |
| Private key JWT | OAuth client signs client assertion with registered private key | Authorization Server authenticates OAuth client via signature |

Adding a CA to the **truststore** only helps the client trust the server's certificate. It **does not** configure a client certificate/private key for mTLS. If the IdP mandates mTLS, configure **key material** on the HTTP client actually making token requests and ensure proxies permit the corresponding TLS/mTLS model.

### 5.4. Proxies Can Change Where TLS Terminates

- With an **HTTP CONNECT proxy** that only forwards a tunnel, TLS is normally established end-to-end between the backend and the provider inside the tunnel; the backend verifies the provider's server certificate.
- If an enterprise uses a **TLS-intercepting proxy**, the backend may see a certificate issued by the proxy's CA. Trust for the proxy CA must be granted per organizational policy and only within permitted scope.
- If the IdP requires **end-to-end mTLS**, TLS interception may be incompatible with authenticating the client certificate to the IdP; coordinate with network/IdP teams to design a proper network path.

**Never use** a "trust all certificates" configuration, skip hostname verification, or rely on `curl -k` as a deployment workaround. Those practices mask DNS, CA chain, or proxy issues and undermine OAuth2/OIDC security.

## 6. Egress Proxy: Understanding Where Proxies Are Configured

An application can contain multiple distinct HTTP clients:

- The library building **`ClientRegistration`** may fetch discovery metadata at startup.
- The **OAuth2 token response client** calls the Token Endpoint.
- Components calling **UserInfo** or fetching **JWK Sets** make separate HTTPS requests.
- Application **`WebClient`**, **`RestClient`**, **`RestTemplate`**, or SDKs call business APIs.

There is no guarantee that configuring a proxy on one of those components automatically applies to the rest.

### 6.1. Environment Variables, JVM System Properties, and HTTP Clients

Some CLI tools/SDKs read:

~~~text
HTTP_PROXY=http://proxy.corp.example:3128
HTTPS_PROXY=http://proxy.corp.example:3128
NO_PROXY=localhost,127.0.0.1,.corp.internal,.svc.cluster.local
~~~

However, **do not assume Java or Reactor Netty automatically honors all of these environment variables**. For instance, JVM HTTP clients relying on proxy system properties may use:

~~~text
-Dhttps.proxyHost=proxy.corp.example
-Dhttps.proxyPort=3128
-Dhttp.proxyHost=proxy.corp.example
-Dhttp.proxyPort=3128
-Dhttp.nonProxyHosts=localhost|127.*|*.corp.internal|*.svc.cluster.local
~~~

In JDK implementations, `http.nonProxyHosts` is also commonly used to exclude hosts for HTTPS. The `|` character here is the delimiter syntax in **JVM system properties** and `*` represents a wildcard, unlike the regex patterns used by some other HTTP clients.

These parameters are **not a global contract** across every Spring client: Reactor Netty, Apache HttpClient, JDK HttpClient, and OAuth2 libraries can read configuration differently. Check **which HTTP client is actually instantiated** for each request. If the proxy requires a username/password, configure proxy authentication on the exact client and safeguard credentials as secrets.

### 6.2. Bypassing the Proxy for Internal Networks

Not every internal domain should go through a proxy. If the backend has direct routing to `*.corp.internal` or Kubernetes services, routing through an Internet proxy can cause 502 errors, DNS failures, or blocked private IP access. Design **non-proxy hosts** to match the real network.

Conversely, some enterprises require routing through a **corporate egress proxy** even when the IdP endpoint has a corporate-looking hostname. Blindly excluding all `*.corp.example` out of habit can cause request timeouts. Bypass rules must follow **the environment's actual routing/firewall topology**, not guessed domain names.

## 7. WebFlux Example: Configuring a Proxy on a `WebClient`

In Spring WebFlux using Reactor Netty, you can specify an HTTP proxy for **a specific `WebClient`** so requests using that client follow the intended path:

~~~java
@Configuration
class ProviderHttpClientConfig {

    @Bean("providerWebClient")
    WebClient providerWebClient(
            @Value("${network.egress.proxy-host}") String proxyHost,
            @Value("${network.egress.proxy-port}") int proxyPort) {

        HttpClient nettyClient = HttpClient.create()
            .proxy(proxy -> proxy
                .type(ProxyProvider.Proxy.HTTP)
                .host(proxyHost)
                .port(proxyPort)
                .nonProxyHosts(
                    "localhost|127[.]0[.]0[.]1|.*[.]svc[.]cluster[.]local|.*[.]corp[.]internal"
                )
            )
            .responseTimeout(Duration.ofSeconds(12));

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(nettyClient))
            .build();
    }
}
~~~

~~~yaml
network:
  egress:
    proxy-host: proxy.corp.example
    proxy-port: 3128
~~~

The relevant types include `reactor.netty.http.client.HttpClient`, `reactor.netty.transport.ProxyProvider`, `org.springframework.http.client.reactive.ReactorClientHttpConnector`, `org.springframework.web.reactive.function.client.WebClient`, `java.time.Duration`, and Spring annotations. Imports are omitted for brevity.

Here:

1. `ProxyProvider.Proxy.HTTP` configures an HTTP proxy; for HTTPS connections, Reactor Netty can establish a CONNECT tunnel as supported.
2. `nonProxyHosts(...)` in Reactor Netty uses a **regular expression**, not the JVM's `http.nonProxyHosts` wildcard syntax. This pattern illustrates bypassing internal hosts and must be adapted to your real topology.
3. `responseTimeout` bounds how long to wait for a response after sending a request; production systems also need connect timeout, proxy connect timeout, retries, and observability.
4. `providerWebClient` is a **dedicated bean**. Only calls made with this bean are guaranteed to follow this configuration.

**Critically important:** creating a proxied `WebClient` **does not automatically route** Spring Security's OAuth2 Login token exchange, OIDC metadata discovery, JWKS fetching, or UserInfo through this bean. Spring Security's components use their own HTTP clients; configure them at the extension points matching your Spring Security version.

### 7.1. Attaching the Proxied `WebClient` to a Client Credentials Token Flow

Example using Spring Security reactive's `WebClientReactiveClientCredentialsTokenResponseClient` and `ReactiveOAuth2AuthorizedClientProviderBuilder`:

~~~java
@Configuration
class ServiceToServiceTokenConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClientService,
            @Qualifier("providerWebClient") WebClient providerWebClient) {

        var tokenClient =
            new WebClientReactiveClientCredentialsTokenResponseClient();
        tokenClient.setWebClient(providerWebClient);

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials(configurer ->
                    configurer.accessTokenResponseClient(tokenClient))
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClientService);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

This example assumes the application already has `ReactiveOAuth2AuthorizedClientService` and `ReactiveClientRegistrationRepository`, either from Boot auto-configuration or custom code; imports are omitted. This manager is for a **service-to-service context** configured specifically with the `client_credentials` grant. When `authorize(...)` runs for the matching registration, the token response client uses `providerWebClient` for token requests.

If the application uses **OIDC Login/authorization code**, token exchange goes through different Spring Security components. You must customize the **authorization-code token response client**, **OIDC UserInfo client**, and **JWK retrieval** when they also need to traverse the proxy; configuring `client_credentials` as above **does not address** login-flow network hops.

For Spring MVC/Servlet, attaching an HTTP client/proxy differs from WebFlux; APIs such as `RestClientAuthorizationCodeTokenResponseClient`, `DefaultAuthorizationCodeTokenResponseClient`, or other hooks depending on version can use a separately configured HTTP client. Never pass reactive classes into Servlet `HttpSecurity` just because names look similar.

### 7.2. Why Can Startup Discovery Still Fail?

If a registration uses `issuer-uri`, metadata retrieval during bean construction may run **before the `providerWebClient` bean in the example is wired into the token manager**. Hence succeeding when calling an API with a dedicated `WebClient` does not prove OIDC discovery used the right proxy.

Common architectural options:

- Allow direct connectivity to the issuer inside the private network with proper DNS and routing.
- Configure the proxy on the HTTP client/pipeline used by Spring Security for discovery, per the API of your running version.
- Use explicit endpoint configuration or a custom repository when full control over initialization is needed, **while ensuring issuer and ID Token validation remain intact**.

Choose according to where the application runs and the IdP's contract. Never resolve connection failures by disabling TLS validation or ignoring the issuer.

## 8. Reverse Proxy in Front of the Application and the Redirect URI Problem

A common architecture:

~~~text
Browser -- HTTPS --> Ingress / Reverse Proxy -- HTTP --> Spring Boot
               Host: portal.example.com               portal-service:8080
~~~

If the backend infers `{baseUrl}` from the internal connection, the redirect URI can become `http://portal-service:8080/login/oauth2/code/corporate` instead of `https://portal.example.com/login/oauth2/code/corporate`. The IdP rejects it with **`redirect_uri_mismatch`**, or the browser cannot reach the internal URL.

Verify:

- The actual external hostname/scheme/path users visit.
- The exact redirect URI registered at the IdP.
- Whether the proxy sends `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and prefix headers when needed.
- Whether Spring Boot/Spring Security is configured to trust those headers only from controlled proxies.
- Whether login/session cookies have sensible `Secure`, `HttpOnly`, and `SameSite` attributes, and whether the callback retrieves the session holding prior login state.

A callback receiving an authorization code yet losing the session can fail with an error related to `state`/authorization request. That is a **cookie or session issue across the reverse proxy**, not a client secret or Token Endpoint TLS error.

## 9. Layer-by-Layer Connectivity Diagnostics

When an environment cannot log in, the fastest approach is identifying **which request failed and which machine ran that request**.

### 9.1. Check from the Exact Backend Runtime Location

Run diagnostic commands from the VM/container/pod running the application, or from an environment sharing the exact same DNS, egress policy, and trust material:

~~~bash
# DNS: which address does the domain resolve to?
nslookup sso.corp.example

# Check TCP reachability if tools are available.
nc -vz sso.corp.example 443

# Check TLS and metadata via direct path.
curl --connect-timeout 5 --max-time 15 -v +  https://sso.corp.example/realms/staff/.well-known/openid-configuration

# With internal CA: use the organization-verified CA bundle.
curl --cacert /opt/app/certs/corporate-root-ca.pem +  https://sso.corp.example/realms/staff/.well-known/openid-configuration

# Check explicit egress proxy when required by network.
curl --proxy http://proxy.corp.example:3128 +  --connect-timeout 5 --max-time 15 +  https://sso.corp.example/realms/staff/.well-known/openid-configuration
~~~

**The discovery path is illustrative only**; for some providers/metadata standards, the `.well-known` location differs. Use the discovery URL published by the IdP. Never paste access tokens, client secrets, or responses containing credentials into shared tickets or logs.

Interpreting symptoms:

- DNS fails to resolve: check DNS servers, split-horizon DNS, search domains, private zones/peering.
- TCP timeout: check routes, firewalls, security groups, Kubernetes `NetworkPolicy`, and proxies.
- TCP succeeds yet TLS fails: check root/intermediate CAs, SANs, SNI, proxy interception, and TLS protocol versions.
- Metadata downloads, yet `issuer` claim is wrong: check canonical hostname/realm and reverse proxy **on the IdP side**.
- Fails only in JVM while `curl` succeeds: compare **CA store, proxy config, and HTTP client implementation** between the JVM and curl.
- Browser login succeeds yet code exchange fails: focus on Token Endpoint, client authentication, egress, truststore, clock sync, and single-use authorization codes.

### 9.2. Inspecting Certificates and Hostnames

If OpenSSL is available:

~~~bash
openssl s_client -connect sso.corp.example:443 +  -servername sso.corp.example -showcerts
~~~

This command shows the certificate chain served directly by the endpoint. If traffic traverses an HTTP proxy or TLS inspection, run the check through **the exact matching proxy path**; direct and proxied connections can yield different certificates. Avoid concluding "the JVM is broken" from a tool using a different truststore and network path.

### 9.3. Appropriate Logging Level

In development, you can temporarily enable debug logs for the relevant Spring Security OAuth2 or Reactor Netty components to see endpoints, failing stages, and exceptions. Configure masking/redaction so you **never log authorization codes, bearer tokens, refresh tokens, client secrets, cookies, or proxy authorization headers**.

At minimum, observe:

1. **Stage:** startup/discovery, redirect, callback, token exchange, JWKS, UserInfo, or API call.
2. **Target:** hostname/port, whether a proxy is used, which side resolves DNS.
3. **Technical error:** DNS, timeout, TCP reset, TLS, HTTP status/OAuth2 response.
4. **Correlation/request ID** (without tokens) to tie together ingress, app, egress proxy, and IdP logs.

## 10. Error Matrix and Remediation Directions

| Symptom | Layer to check | Common cause | How to resolve |
| --- | --- | --- | --- |
| App fails to start with `issuer-uri` enabled | Discovery/startup | Cannot reach metadata; DNS/TLS/proxy error | Check routes, CA, metadata endpoint, and how Spring builds registrations |
| Browser cannot open SSO page | Front-channel | IdP only on private network; browser lacks VPN/DNS | Provide valid browser access or adjust IdP publication architecture |
| `UnknownHostException` | Backend DNS | Private zone unavailable in pod/VM | Check resolver, DNS zones, network paths |
| `ConnectTimeoutException`, TCP timeout | Route/firewall/proxy | Egress blocked, wrong host/port, wrong proxy bypass | Check routes, `NetworkPolicy`, proxy allowlists |
| `PKIX path building failed` | TLS trust | Missing internal CA, wrong truststore/client | Install proper CA chain and apply to the active HTTP client |
| Hostname mismatch or cert lacks matching SAN | TLS identity | Using IP/alias not on cert, wrong SNI | Use canonical hostname or reissue valid cert |
| HTTP `407 Proxy Authentication Required` | Egress proxy | Missing credentials or wrong proxy auth | Configure proxy authentication securely on client |
| HTTP `502/504` from proxy | Upstream proxy | Proxy cannot reach IdP, ACL denies | Check proxy logs, DNS, and route from proxy to IdP |
| `redirect_uri_mismatch` | Login/ingress | Callback differs from registered URL, lost HTTPS scheme | Fix redirect URI and forwarded headers config |
| `invalid_client` at Token Endpoint | OAuth2 client authentication | Wrong ID/secret, auth method, client cert | Compare client registration with IdP settings |
| `invalid_grant` | Authorization code/token flow | Expired/reused code, `redirect_uri`/PKCE mismatch | Check callback, clock sync, PKCE, and single code exchange |
| `invalid_scope` | Authorization Server | Scope not granted to client | Register/approve right scopes at provider |
| ID Token has mismatched `iss` | OIDC validation | Wrong metadata/external URL/realm | Fix canonical issuer configuration; keep validation |
| Cannot fetch JWKS or unknown `kid` | Key retrieval/rotation | JWKS unreachable, rotated key, or cache | Check JWKS URL, CA, route, cache/rotation |
| API returns `401` or `403` after login | Resource Server | Wrong audience, missing scope, or token not sent | Check access token, sender, and API policy |

Two easily confused HTTP codes: **401** usually indicates an unauthenticated request or rejected token; **403** usually indicates an authenticated request lacking permission. Some gateways/providers customize error responses, so inspect the OAuth2 payload and logs of the component actually returning the error.

## 11. Special Notes for Kubernetes, Containers, and Enterprise Environments

**DNS and networking:** A pod may resolve names differently from its host node or a developer laptop. Private Service DNS, private endpoints, NAT gateways, egress gateways, and `NetworkPolicy` can create completely different paths. Test from the actual pod or one with matching security context and network policy.

**CAs and container images:** Internal CA certificates are often absent from the JVM truststore of minimal container images, even if installed on developer machines. Mount the truststore or bake the CA in via a controlled build/deploy pipeline. Clarify whether the application uses the JDK SSL context, Netty native TLS, or a custom SSL context.

**Proxy policies:** Service mesh sidecars, egress gateways, and HTTP proxies can form multiple hops. Identify which hop handles DNS, CONNECT, TLS interception, and allowlists. Never create a loop pointing an egress proxy back at the application's own ingress.

**Accounts and secrets:** Client secrets, proxy credentials, and private keys are distinct secrets. Store them in a secret manager/Kubernetes Secret with least privilege, track rotation, never commit them into YAML, and never share one value across all environments.

**Clocks:** Authorization codes, ID Tokens, and access tokens carry expiration constraints. If clocks between the backend and IdP drift significantly, validation or token exchange can fail even when network and TLS are completely healthy. Synchronize clocks and inspect `iat`/`nbf`/`exp` claims safely.

**Performance and availability:** If metadata discovery or JWKS retrieval depends on private networks/proxies, outages there can slow down startup or authentication. Set sensible timeouts, targeted health checks, and appropriate cache/rotation policies; avoid infinite retries on live login requests.

**Proxy constraints:** Never accept an arbitrary provider URL from a user request and have the backend connect to it. Keep providers/issuers in an allowlist and verify tenant access permissions to prevent SSRF, proxy abuse, and unintended access to internal resources.

## 12. Practice Scenarios

### Scenario A — Backend on Cluster Reaches IdP, Yet Remote Employees Cannot Log In

The IdP's Authorization Endpoint is only reachable over VPN. Setting `https.proxyHost` in Java does not change the browser's network path. The fix must address **users' front-channel reachability**: VPN/zero-trust access, or an IdP publication model compliant with corporate policy. The backend must still reach the Token Endpoint/JWKS.

### Scenario B — Login Redirect Succeeds, Yet Callback Reports TLS Error on Code Exchange

The browser reached the IdP and returned to the app, proving the front-channel works. The backend may be missing the internal root CA or not routing the **token response client** through the proxy. Inspect the exception and test HTTPS from the backend runtime environment using the exact proxy and trust material. Never disable TLS validation to bypass the error.

### Scenario C — WebFlux App Has Proxied `WebClient`, Yet Still Fails at Startup

The custom `WebClient` only applies to requests using that bean, whereas `issuer-uri` can cause Spring Security to contact provider metadata before the manager ever uses `WebClient`. Fix the **discovery** path or use a version-compatible explicit provider configuration that avoids startup discovery while preserving issuer validation.

### Scenario D — One Environment Works, Container Environment Returns `invalid_redirect_uri`

Locally, the app runs HTTPS directly; in containers, TLS-terminating proxies forward HTTP to the app. `{baseUrl}` may infer the wrong scheme/host. Align the public hostname, forwarded headers from trusted proxies, and the redirect URI registered at the IdP; this error is normally not caused by egress TLS.

### Scenario E — Accessing via HTTP Proxy Returns `407`

The backend reached the proxy, yet the proxy requires authentication. Add username/password to the HTTP client's proxy settings using the mechanism supported by the library, store credentials securely, and verify the proxy permits CONNECT to the IdP's hostname/port. Do not confuse proxy credentials with the OAuth2 `client-secret`.

## 13. Self-Check Questions

**Question 1.** The browser reaches the IdP's login page, yet the backend cannot reach the Token Endpoint. Can you conclude the entire OAuth2 flow works at the network layer?

**Answer:** No. The browser uses the **front-channel**, while the backend uses the **back-channel**. You must separately verify DNS, routing, proxies, and TLS from the backend to the Token Endpoint.

**Question 2.** Does setting `HTTPS_PROXY` and `NO_PROXY` on a container guarantee every request from Spring Security OAuth2 Client uses that proxy?

**Answer:** Not guaranteed. Specific HTTP clients may read environment variables, JVM properties, or dedicated configuration. Discovery, token exchange, JWKS, UserInfo, and business `WebClient` instances can use different clients.

**Question 3.** Is importing an internal CA into the truststore enough when the Token Endpoint requires mTLS?

**Answer:** No. The truststore verifies the **server certificate**; mTLS also requires configuring a **client certificate/private key** on the HTTP client establishing the connection.

**Question 4.** Can you set `issuer-uri` to a private IP or internal backend name differing from `iss` in the ID Token just to avoid a proxy?

**Answer:** No. The issuer is a canonical identifier that must be verified. Fix DNS/routing or expose the provider consistently rather than weakening issuer validation.

**Question 5.** An HTTPS login callback turns into an internal HTTP hostname—which proxy should you inspect?

**Answer:** Inspect the application-side **reverse proxy/ingress**, forwarded headers, external base URL, and registered redirect URI. An egress proxy for the Token Endpoint does not directly determine the callback hostname.

## 14. References

- [Spring Security Reference — OAuth 2.0 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security Reference — OAuth 2.0 Client (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Spring Security Reference — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Boot Reference — Spring Security and OAuth2 Client Configuration](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication](https://www.rfc-editor.org/rfc/rfc8705)

**Remember:** When a provider sits on an internal network or the backend must traverse a proxy, map out clearly **who connects to which endpoint**. Then properly configure **DNS/routing, TLS trust and client identity, per-HTTP-client proxies, consistent issuers, and ingress redirect URIs**. Each layer has its own responsibility and all must work together for a secure OAuth2/OIDC flow to succeed.
