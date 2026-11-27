# Internal URLs, Public URLs, and Issuers When Deploying Behind a Proxy

When an **Authorization Server** and **Spring Security OAuth 2.0/OIDC Resource Server** are deployed behind Nginx, an API Gateway, Ingress, or Load Balancer, two addresses easily emerge for the same system:

- **Internal URL:** the service address infrastructure uses for forwarding, for example `http://auth-service:8080`.
- **Published (public/external) URL:** the address visible to clients, browsers, and integrating components, for example `https://login.example.com`.

The key issue is that **`issuer` is not merely where a request happens to be routed**. In OAuth 2.0 and OpenID Connect, the issuer is the **stable logical identifier of the token publisher**. The `iss` claim in JWTs, the `issuer` field in metadata, and the `issuer-uri` configuration at the Resource Server must agree on the published identifier.

> **Design principle:** maintain a stable canonical issuer, typically the Authorization Server's published HTTPS URL, even when communication between the proxy and internal services uses different hostnames, ports, or paths.

This is the root cause behind many `401 invalid_token` errors, discovery `404`s, metadata containing `http` URLs, or clients being redirected to container names after deploying to production.

## 1. Three Kinds of URLs to Distinguish

Suppose the system has an Identity Provider (IdP) serving a shop:

| Address type | Example | What is it used for? |
|---|---|---|
| **Canonical issuer** | `https://login.example.com/realms/shop` | Identifies the AS in metadata, the `iss` claim, and Resource Server config |
| **Public endpoint URL** | `https://login.example.com/realms/shop/.well-known/openid-configuration` | Called by Clients/Resource Servers to discover AS configuration |
| **Internal upstream URL** | `http://auth-service:8080/realms/shop` | Reverse proxy forwards requests to the AS application on the private network |
| **JWK Set URI** | `https://login.example.com/realms/shop/protocol/openid-connect/certs` | Distributes public keys to verify JWT signatures |
| **Resource Server API URL** | `https://api.example.com/api/orders` | API address receiving bearer tokens from clients |

The addresses in the table are illustrative only. Actual JWKS paths depend on the Authorization Server; there is **no single fixed URL path across all IdPs**.

Pitfall to avoid: instead of declaring:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: http://auth-service:8080/realms/shop
~~~

merely because the Resource Server sits on the same Docker/Kubernetes network, use the issuer that **actually appears in JWTs and metadata**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
~~~

These two URIs represent **two different names**, even though the proxy routes to the same process. Spring Security does not automatically consider them equivalent as issuers.

## 2. Deployment Diagram with a Reverse Proxy

~~~text
       Browser / Mobile / Backend Client
                      |
                      | HTTPS
                      | https://login.example.com/realms/shop
                      v
                Reverse Proxy / Ingress
                      |
                      | internal upstream route
                      | http://auth-service:8080/realms/shop
                      v
             Authorization Server (AS)
                      |
              signs JWT access token
                      |
                      v
 JWT claims:
   iss = https://login.example.com/realms/shop
   aud = orders-api
   exp = ...
                      |
                      v
      Client -- Authorization: Bearer <JWT> --> Resource Server
                                                     |
                                            issuer-uri =
                                            https://login.example.com/realms/shop
                                                     |
                                             JWT signature + claim
                                                validation
~~~

There may also be a reverse proxy in front of the Resource Server, such as `https://api.example.com` forwarding to `http://orders-service:8080`. That **does not change the JWT's issuer**. A token issued by `login.example.com` still carries the AS's issuer in `iss`, even if the Resource Server receives the request through a different domain name.

### Who Determines the `iss` Value?

**The Authorization Server determines the issuer value in the token.** The Resource Server merely configures the value it trusts and checks the claim:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000000
}
~~~

If the AS issues a token containing:

~~~json
{
  "iss": "http://auth-service:8080/realms/shop"
}
~~~

while the Resource Server trusts `https://login.example.com/realms/shop`, issuer validation will fail even though both URLs reach the same service. The proper fix is normally **configuring the AS to emit the canonical issuer**, checking proxy/forwarded headers, and aligning the Resource Server. Never arbitrarily disable the `iss` validator.

## 3. Issuer Is an Identifier, Not a Network Routing Trick

OAuth 2.0 Authorization Server Metadata and OpenID Connect Discovery treat the issuer URI as an **identifier**. Separate two questions:

1. **Does the token come from a trusted publisher?** → validate `iss` against the canonical issuer.
2. **How does the Resource Server reach metadata/JWKS endpoints over the network?** → routing, DNS, proxy, TLS, or a trusted configured JWKS URI.

The two questions can have different answers. For example:

~~~text
Expected issuer (identity):
  https://login.example.com/realms/shop

Trusted public JWKS endpoint:
  https://login.example.com/realms/shop/protocol/openid-connect/certs

Optional trusted internal JWKS endpoint:
  https://auth-jwks.svc.cluster.local/realms/shop/protocol/openid-connect/certs
~~~

If using an internal JWKS, verify that URL **actually serves public keys for the same issuer**, protect the transport channel, and never let clients pick URLs arbitrarily. The `iss` value inside the token remains the **canonical public URL**.

### URI Matching Must Be Exact

The following values are **not implicitly equivalent** during issuer validation:

| Issuer 1 | Issuer 2 | Difference |
|---|---|---|
| `https://login.example.com` | `http://login.example.com` | Scheme |
| `https://login.example.com` | `https://login.example.com:8443` | Port |
| `https://login.example.com/realms/shop` | `https://login.example.com/realms/shop/` | Trailing slash |
| `https://login.example.com/realms/shop` | `https://login.example.com/shop` | Path |
| `https://login.example.com` | `https://login-internal` | Host |

Do not tweak strings by adding/stripping slashes or changing HTTP to HTTPS inside the JWT. The token signature covers the entire payload; modifying `iss` invalidates the signature. The exact value must be emitted by the AS and configured consistently across clients/Resource Servers.

## 4. How Does `issuer-uri`-Based Discovery Work?

With a Spring Boot Resource Server using JWT:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Spring Security uses the issuer URI to locate the **Provider Configuration (OIDC)** or **Authorization Server Metadata (OAuth 2.0)** endpoint according to supported discovery rules, then reads `jwks_uri` to fetch public keys.

Diagram:

~~~text
Resource Server
  |
  | issuer-uri = https://login.example.com/realms/shop
  v
Supported discovery endpoint
  |
  | metadata: issuer, jwks_uri, ...
  v
JWKS endpoint
  |
  | public keys by kid/kty/alg...
  v
JwtDecoder
  |
  +-- verify signature
  +-- validate iss / exp / nbf / aud per config
  +-- convert scope -> authorities
~~~

### 4.1. OIDC Metadata

For an issuer with path `/realms/shop`, a provider may publish:

~~~text
GET https://login.example.com/realms/shop/.well-known/openid-configuration
~~~

Abbreviated response:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "authorization_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs"
}
~~~

All URLs above illustrate one style of IdP deployment. Endpoints for Spring Authorization Server, Keycloak, Auth0, Okta, or other IdPs may use different paths.

**Metadata must publish the canonical issuer.** If clients fetch metadata via `https://login.example.com` yet the response contains:

~~~json
{
  "issuer": "http://auth-service:8080/realms/shop"
}
~~~

that indicates the AS/proxy has not aligned on the external URL. Changing `issuer-uri` on the Resource Server to the internal URL might mask the issue on one service while breaking the contract for browsers, clients, and other APIs.

### 4.2. OAuth 2.0 Metadata per RFC 8414

Not every AS is an OIDC Provider. A JWT Resource Server can use OAuth 2.0 metadata when supported.

For an issuer with a path, RFC 8414 defines inserting the well-known suffix between host and issuer path. For example, for issuer `https://login.example.com/realms/shop`, the OAuth metadata endpoint can be:

~~~text
https://login.example.com/.well-known/oauth-authorization-server/realms/shop
~~~

Whereas OIDC discovery typically uses:

~~~text
https://login.example.com/realms/shop/.well-known/openid-configuration
~~~

Spring Security may probe several standardized metadata endpoint forms. **Do not assume every well-known URL always uses one path construction rule**; check the endpoints supported by your IdP and its documentation.

### 4.3. The Resource Server Checks Metadata and JWT at Two Stages

Metadata discovery locates the issuer and key source. Once matching keys are obtained, the Resource Server verifies the JWS and validates `iss`/`aud`/lifetimes. A metadata JSON returning `200 OK` **does not automatically make every JWT valid**.

With modern Spring Security configuration, discovery may be deferred until the first JWT request; with a differently initialized decoder, startup network behavior may differ. Regardless of when metadata is fetched, **public DNS/TLS/routing must work when the Resource Server needs discovery or needs to load uncached keys**.

## 5. Characteristic Failures When an AS Sits Behind a Proxy

### 5.1. AS Publishes `http` Even Though Users Access HTTPS

Scenario:

~~~text
Browser   -- HTTPS --> https://login.example.com
Ingress   -- HTTP  --> http://auth-service:8080
AS sees internal request:
  scheme = http
  host   = auth-service
~~~

If the AS infers its issuer or endpoint URLs from the internal request without handling reverse proxies, metadata may contain `http://auth-service:8080`. That address is unsuitable for external clients and usually mismatches the `iss`/issuer expected by the Resource Server.

Solution: **configure an explicit canonical external issuer** if supported by the IdP; at the same time ensure the reverse proxy forwards `Host`, scheme, port, and prefix (when needed) accurately, and the AS trusts forwarded headers only from authenticated/trusted proxies.

### 5.2. Redirects Back to the Internal Hostname

A client opens:

~~~text
https://login.example.com/oauth2/authorize
~~~

but the AS responds:

~~~http
HTTP/1.1 302 Found
Location: http://auth-service:8080/login
~~~

Browsers outside the cluster cannot call `auth-service:8080`. This is an external URL reconstruction / issuer / forwarded headers or AS endpoint mapping error. Fix it at the AS/proxy, not by changing the client's `redirect_uri` to the container hostname.

### 5.3. Metadata Has the Right Issuer, but `jwks_uri` Is an Internal URL

For example:

~~~json
{
  "issuer": "https://login.example.com",
  "jwks_uri": "http://auth-service:8080/oauth2/jwks"
}
~~~

A Resource Server running in the same cluster **might** reach the internal URL, whereas external clients or other integrations cannot. Publicly published metadata should generally contain public endpoints reachable and verifiable by metadata consumers.

If one Resource Server has an operational reason to fetch JWKS via an internal address, **configure `jwk-set-uri` specifically for that Resource Server** while keeping `issuer-uri` canonical. Do not publish metadata containing internal-only hosts solely to work around routing for a single consumer.

### 5.4. Wrong Context Path or Path Rewrite

For example, externally:

~~~text
https://login.example.com/idp/realms/shop
~~~

while the internal service is at:

~~~text
http://auth-service:8080/realms/shop
~~~

The proxy must rewrite `/idp/realms/shop` to `/realms/shop` per the designed rule. The AS must also know the public `/idp` prefix when generating metadata, redirects, and issuer, if required by the product configuration. **`X-Forwarded-Prefix` can help certain frameworks reconstruct external paths, but does not automatically solve every IdP's rewrite/path handling**.

One misplaced slash, double-stripping a path, or double-adding a prefix can cause discovery `404`s, JWKS `404`s, or redirect loops.

## 6. Configuring the Issuer Directly on the Authorization Server

In terms of responsibility, **the AS must issue tokens with the canonical issuer**. The Resource Server has no obligation to “convert” an internal issuer into a public one.

### 6.1. Spring Authorization Server

For an AS built with Spring Authorization Server, you can configure the issuer explicitly:

~~~java
package com.example.auth.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration
public class AuthorizationServerIssuerConfig {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
            .issuer("https://login.example.com")
            .build();
    }
}
~~~

This is an example **for an Authorization Server with a root issuer without a path prefix**. If the real public issuer has a path, use the exact prescribed public issuer value and configure endpoints/routing accordingly.

Per Spring Authorization Server documentation, if no issuer is declared in `AuthorizationServerSettings`, the framework may resolve the issuer from the current request. Behind a proxy, internal requests may not reflect the published host/scheme unless forwarded headers are handled safely. **Declaring a fixed issuer stabilizes the AS's identity across requests and infrastructure environments.**

Note: changing the issuer of an AS **already issuing production tokens** is a contract change, not merely renaming a UI base URL. Clients/Resource Servers trusting the old issuer may reject new JWTs or metadata. Plan a proper migration.

### 6.2. With Other IdPs

Keycloak, Okta, Auth0, and other Authorization Servers have their own settings for public hostname/front-end URL, proxy mode, or issuer. Configure accurately per **the vendor's version and docs**, such as:

- External hostname/scheme/port seen by clients.
- Path prefix the IdP needs to publish.
- Reverse-proxy headers allowed to be trusted.
- Generated metadata issuer and endpoint URLs.
- JWKS endpoint and signing key rotation.

Never edit `iss` manually after signing a JWT, never re-encode tokens with Base64URL, and never turn off issuer checks at the Resource Server to hide external URL errors.

## 7. Forwarded Headers Help the AS See Public Request Details

When TLS terminates at a proxy, the backend application typically sees an internal HTTP request. The proxy can pass details of the original request via:

| Header | Suggested content | Example |
|---|---|---|
| `X-Forwarded-Proto` | External scheme | `https` |
| `X-Forwarded-Host` | External host | `login.example.com` |
| `X-Forwarded-Port` | External port | `443` |
| `X-Forwarded-Prefix` | External prefix, if any | `/idp` |
| `X-Forwarded-For` | Client/hop addresses per proxy policy | `203.0.113.10` |
| `Forwarded` (RFC 7239) | Standardized proxy info | `proto=https;host=login.example.com` |

These headers help frameworks build absolute URLs and redirects, but **they are not security truth if requests arrive directly from the Internet or if the proxy preserves client-forged headers**.

### 7.1. Spring Boot Handling Forwarded Headers

For a Spring Boot HTTP app behind a reverse proxy, you can configure:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Spring Boot has typical strategies:

- **`none`:** do not use forwarded headers to reconstruct request URLs.
- **`native`:** let the embedded web server use its own forwarded-headers support (Tomcat/Jetty/Undertow/Netty).
- **`framework`:** use Spring Framework's mechanism, such as `ForwardedHeaderFilter` in Servlet or `ForwardedHeaderTransformer` in WebFlux.

This is **configuration for an HTTP app sitting behind a proxy**; on the Authorization Server side with Spring Boot, it helps the AS build accurate URLs. If the Resource Server API also sits behind a proxy, forwarded headers can help the API handle redirects/links and related HTTP logic, yet **it does not automatically fix JWT `issuer-uri`**.

In some Tomcat setups with HTTPS termination at the proxy, you may also need:

~~~yaml
server:
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
~~~

This Tomcat property affects context-root redirects before the forwarded scheme takes effect. Apply only when appropriate for your Boot/Tomcat version and application behavior.

### 7.2. Illustrative Nginx Example

Suppose Nginx is a **trusted edge proxy**, accepting HTTPS at `login.example.com` and forwarding to the AS on a private network:

~~~nginx
server {
    listen 443 ssl;
    server_name login.example.com;

    # Must declare real ssl_certificate / ssl_certificate_key
    # and proper TLS configuration in production.

    location / {
        proxy_pass http://auth-service:8080;

        proxy_set_header Host login.example.com;
        proxy_set_header X-Forwarded-Host login.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;

        # The edge proxy must overwrite/strip forwarded headers
        # that clients might send themselves.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

This example explains **passing public host/scheme through a single proxy**. It is not a complete production Nginx config: you still need TLS certificates, timeouts, request limits, logging, upstream health checks, real-IP policy if another load balancer sits in front, and network configuration.

In multi-proxy chains, extracting `X-Forwarded-For` or the standard `Forwarded` header requires a clear trust boundary. Never copy an untrusted `X-Forwarded-For` string verbatim and treat its first address as a security ground truth.

### 7.3. Host Header and Forwarded-Header Injection Risks

If an attacker is allowed to send:

~~~http
Host: attacker.example
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: http
~~~

and the AS trusts those headers, it can emit forged redirects, metadata, or absolute URLs. In poorly controlled designs, incidents can involve open redirects, host-header injection, issuer confusion, or token leakage via URLs.

Foundational mitigations:

1. The proxy at the **trust boundary** must strip/overwrite `Forwarded` and `X-Forwarded-*` headers from untrusted sources.
2. Allow traffic to AS/RS backends only through the proxy or authorized internal paths; never let clients bypass the proxy and inject spoofed headers directly.
3. Enforce allowlists of permitted hosts and TLS hostnames.
4. Prefer **fixed canonical issuer configuration** when the product supports it.
5. Restrict permissions to modify issuer/JWKS configuration, as that controls trust decisions.

Simply enabling `server.forward-headers-strategy: framework` without protecting forwarded headers at the edge is insufficient.

## 8. Path Prefixes: External Path and Internal Path Can Differ

A common deployment uses a prefix:

~~~text
Public:
  https://login.example.com/idp/oauth2/jwks

Internal:
  http://auth-service:8080/oauth2/jwks
~~~

If the proxy strips `/idp` before forwarding, the AS might not know the public prefix. Some frameworks support `X-Forwarded-Prefix: /idp`, though actual support depends on the stack and the specific Authorization Server product.

Decisions to align on:

- Does the **canonical issuer** include `/idp` or not?
- Which absolute URLs does OIDC/OAuth metadata publish?
- Does Ingress preserve, rewrite, or strip the prefix?
- Is the AS configured with a matching context path or frontend URL?
- Which public URLs do client callback and logout endpoints target?
- Is anything double-adding or double-stripping the prefix?

### 8.1. Example When Path Is Unchanged

If both public and internal serve `/realms/shop`, the mapping is simple:

~~~text
https://login.example.com/realms/shop/*
    -> http://auth-service:8080/realms/shop/*
~~~

In this case, the AS can keep its route paths unchanged and only needs to know the public scheme/host/port.

### 8.2. Example When Path Is Rewritten

~~~text
https://login.example.com/idp/realms/shop/*
    -> http://auth-service:8080/realms/shop/*
~~~

Now, setting only `X-Forwarded-Proto=https` and `X-Forwarded-Host=login.example.com` is unlikely to suffice. Decide how the AS understands `/idp` and how the proxy rewrites paths. A misconfiguration can make metadata return 200 while advertising a non-existent JWKS URI or an `iss` missing `/idp`.

**Do not edit the Resource Server's `issuer-uri` to “match the internal path”** if tokens are issued with the prefixed public issuer. Fix metadata/token issuance or routing instead.

## 9. When the Resource Server Cannot Reach the Public Hostname

In Docker/Kubernetes, a Resource Server might reach `auth-service:8080` yet fail to resolve or connect to `login.example.com`. That is a **network routing/DNS issue**, not a reason to replace the issuer with an internal hostname.

Three common architectural options exist.

### 9.1. Let the Resource Server Reach the Public Issuer via Proper Routing

Issuer-only configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Infrastructure must allow the Resource Server to connect to metadata and JWKS endpoints via the published hostname. Traffic can pass through public ingress, private ingress, or split-horizon DNS, provided **TLS is properly verified** and metadata URLs stay consistent.

Advantage: one canonical public endpoint source seen by all consumers.

Note: in some clusters, requests from a pod to the ingress's own external hostname can hit hairpin NAT or routing issues. Solve that via appropriate ingress/DNS architecture, never by changing `iss`.

### 9.2. Split-Horizon DNS Keeps the URL Identical While Routing Internally

You can set up:

~~~text
On the Internet:
  login.example.com -> public ingress address

Inside the cluster:
  login.example.com -> internal ingress address
~~~

The application still calls `https://login.example.com`. Because the **hostname in the URL does not change**, TLS certificates and metadata endpoints still match `login.example.com`; destination IPs simply resolve differently by network zone.

This is often how a single canonical issuer is preserved across networks while optimizing internal traffic. Ensure the internal ingress enforces the same issuer/JWKS contract, has valid certificates/truststore, and never disables TLS hostname verification.

### 9.3. Public `issuer-uri` + Internal `jwk-set-uri`

Spring Security supports declaring a **public issuer to validate `iss`** together with a **direct JWK Set URI to fetch public keys**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://auth-jwks.svc.cluster.local/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

In this example:

- `issuer-uri` must still match the JWT's `iss` claim.
- `jwk-set-uri` is an **approved** internal address serving public keys for that exact AS/issuer.
- The Resource Server does not need metadata discovery to find the JWKS URI.
- Tokens must still pass signature verification, issuer/lifetime validation, and audience validation.

This configuration is very useful when the external issuer cannot be called directly from the internal network, yet a dedicated trusted JWKS endpoint is available.

**Conditions to guarantee:**

- `auth-jwks.svc.cluster.local` is genuinely the key source for that AS; never point to the wrong service or tenant.
- The channel to JWKS is protected (internal TLS or a clearly governed trusted channel); prevent tampering with JWKS in transit.
- If using an internal TLS hostname, the certificate must match that hostname and the JVM truststore.
- Public metadata published for external clients should still contain the appropriate public URLs.
- Key rotation must refresh keys consistently at the internal JWKS source and across all Resource Servers.

**Never configure only `jwk-set-uri` and omit `issuer-uri`** when the API has an explicit issuer contract. Knowing a set of public keys does not automatically verify which issuer a token belongs to.

## 10. Spring Security Resource Server: Complete Configuration

### 10.1. Dependencies

Gradle example for Spring Boot + Spring MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

The Resource Server starter pulls in the required JWT/JOSE components. If declaring libraries manually, include both `spring-security-oauth2-resource-server` and `spring-security-oauth2-jose`.

### 10.2. `application.yml`

Suppose the public issuer is `https://login.example.com/realms/shop` and `orders-api` accepts only tokens with audience `orders-api`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://auth-jwks.svc.cluster.local/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

If the Resource Server can reach public discovery/JWKS, you can omit `jwk-set-uri` and let Spring Security discover it automatically. If using a Spring Boot version that does not yet support the `audiences` property, add an `OAuth2TokenValidator<Jwt>` checking audience on the decoder.

### 10.3. `SecurityFilterChain`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Tokens with scope `orders.read` are typically mapped to authority `SCOPE_orders.read` after `JwtDecoder` verifies the token. This config omits specific session/cookie/CSRF policies; applications must handle those according to their actual clients and architecture.

More importantly, **do not use `server.forward-headers-strategy` on the Resource Server as a substitute for `issuer-uri`**. The former deals with HTTP request info arriving through a proxy; the latter is the **trusted issuer value inside tokens**.

### 10.4. If Creating a Custom `JwtDecoder`

When an application declares `@Bean JwtDecoder` itself or overrides the decoder in the security DSL, Spring Boot may **back off** from auto-configuration. Specifically:

- `issuer-uri` in YAML does not automatically add an issuer validator to a custom decoder.
- `jwk-set-uri` only supplies the key source.
- `audiences` may not apply to a custom decoder unless configured explicitly by the application.
- Whether metadata/JWKS are fetched at startup or runtime depends on the builder/factory used.

Example custom decoder using an internal JWKS while still validating the public issuer:

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class ExplicitJwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.com/realms/shop";

    private static final String JWKS =
        "https://auth-jwks.svc.cluster.local/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS).build();

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                values -> values != null && values.contains("orders-api"));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience));

        return decoder;
    }
}
~~~

URLs in code are illustrative only. In deployment, move them to trusted environment config with change controls. For typical applications, using Spring Boot properties is simpler.

## 11. Which Metadata Fields Must Be Accurate?

For issuer/proxy setups, at minimum verify:

| Metadata field | Meaning | Typical mistake |
|---|---|---|
| `issuer` | Canonical identifier of the AS | Exposes `http://auth-service:8080` |
| `jwks_uri` | Public keys endpoint | Only internal host, wrong scheme, or wrong path |
| `authorization_endpoint` | Browser/client goes here to request authorization | Redirects to container host or HTTP |
| `token_endpoint` | Client uses this to exchange codes/obtain tokens | Unreachable from external clients |
| `userinfo_endpoint` (OIDC, if present) | User info endpoint | Host/path differs from public contract |
| `end_session_endpoint` / logout endpoint (if present) | OIDC logout per provider | Redirects to wrong host/prefix |
| `introspection_endpoint` (if present) | Opaque token verification | API cannot connect or gets wrong URL |

A JWT Resource Server normally needs `issuer` and `jwks_uri` to verify tokens. OIDC clients may additionally need authorization/token/userinfo/logout endpoints. Fixing only JWKS to make one API work is not enough if browser login flows still redirect to an internal host.

**OIDC discovery metadata is not just a list of routes.** It is a contract that many clients rely on to know the trusted issuer and endpoints. Published URLs must stay consistent with the organization's managed public hostname/path.

## 12. Verifying Configuration Without Exposing Access Tokens

First check public and internal endpoints (from the right network environment). You can inspect metadata **without credentials**:

~~~bash
curl -fsS \
  https://login.example.com/realms/shop/.well-known/openid-configuration
~~~

If `jq` is installed:

~~~bash
curl -fsS \
  https://login.example.com/realms/shop/.well-known/openid-configuration \
  | jq '{issuer, jwks_uri, authorization_endpoint, token_endpoint}'
~~~

Expected output:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs",
  "authorization_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token"
}
~~~

Example paths match one IdP style; replace with the actual metadata endpoint supported by your provider.

Check public JWKS:

~~~bash
curl -fsS \
  https://login.example.com/realms/shop/protocol/openid-connect/certs \
  | jq '{keyCount: (.keys | length), kids: [.keys[].kid]}'
~~~

Check the trusted internal JWKS **from inside the Resource Server container/pod** if configuring an internal URI:

~~~bash
curl -fsS \
  https://auth-jwks.svc.cluster.local/realms/shop/protocol/openid-connect/certs \
  | jq '{keyCount: (.keys | length), kids: [.keys[].kid]}'
~~~

A successful `curl` only proves HTTP/TLS/routing and that some metadata is returned. It **does not yet prove JWTs verify**; you still need a real test access token signed by the AS with the right key and expected claims.

### 12.1. Checking from Multiple Network Perspectives

Verify from at least the relevant vantage points:

- Browser or external machine: are public issuer, redirects, and public JWKS reachable?
- Resource Server pod/container: does `issuer-uri` have working DNS/TLS/routing, or is the internal `jwk-set-uri` reachable?
- AS pod/container: did the AS receive the right forwarded headers and publish the canonical public issuer?
- Ingress/API Gateway: are there any unexpected path, host, or scheme rewrites?

A URL reachable from a developer laptop **does not mean** it is reachable from a Kubernetes pod. Conversely, `auth-service:8080` being reachable inside the cluster does not make it the right issuer.

### 12.2. When Inspecting a JWT's `iss` Claim

A JWS-formatted JWT has a Base64URL-decodable payload for diagnostics. However, reading unverified claims is only **what the token claims about itself**, never a replacement for the Resource Server's `JwtDecoder`. Never paste production tokens into public decoder websites or log raw `Authorization` headers.

Best practice is using a **short-lived test token**, comparing its `iss` claim against metadata `issuer` and the RS's `issuer-uri`, and then checking actual verification results from Spring Security.

## 13. Table Distinguishing Proxy, Discovery, and JWT Errors

| Symptom | Common cause | Where to fix |
|---|---|---|
| Discovery URL returns 404 | Wrong proxy path rewrite or AS lacks that well-known endpoint | Ingress routing, IdP metadata path |
| Metadata `issuer` is `http://auth-service:8080` | AS inferred internal URL due to missing external issuer/forwarded headers | AS config and trusted proxy |
| Metadata `issuer` is public, yet JWT `iss` is internal | AS emitting an issuer violating contract, or inconsistent instances | Token issuer config on AS |
| JWT `iss` is right public value, RS sets internal `issuer-uri` | RS mistook transport URL for identity | Set RS issuer URI to canonical value |
| JWT signature valid, yet wrong `aud` | Token issued for another API | Audience policy, obtain right access token |
| Public metadata has internal `jwks_uri` | AS published an endpoint hard to reach externally | Public metadata/AS config; internal JWKS override at RS if needed |
| `jwks_uri` returns 404 after prefix change | Extra/missing path segment during reverse proxy rewrite | Proxy path + AS endpoint mapping |
| Redirect `Location` points to HTTP | Misconfigured TLS termination and forwarded proto/AS URL | Proxy, Boot forwarded handling, or AS external URL |
| Redirect `Location` points to container name | Wrong forwarded host/public hostname | Trusted proxy, AS canonical hostname |
| JWKS TLS certificate error in pod | DNS/hostname/truststore mismatch | Certificate chain, internal DNS, truststore |
| New `kid` fails JWT verification | JWKS cache/rotation out of sync | AS key publication and decoder refresh |
| `401 invalid_token` when switching proxies | Different `iss`, key/JWKS mismatch, expired token | JWT auth logs and AS metadata |
| `403` after valid JWT | Missing scope/authority or data permission | Spring Security authorization rules |
| Fails only in Kubernetes, works locally | DNS, network policy, ingress/hairpin routing, proxy headers | Cluster infrastructure and environment config |

**Do not assume every `401` is caused by the issuer.** A JWT with an invalid signature, expired timestamp, wrong audience, or signed by another key will also be rejected. Classify errors based on actual verification logs, not metadata alone.

## 14. Distinguishing Changing the Issuer vs. Changing the JWKS Access Path

These two changes have very different impacts.

### 14.1. Changing `jwk-set-uri` While Keeping the Issuer

For example:

~~~text
Before:
  issuer-uri  = https://login.example.com/realms/shop
  jwk-set-uri = https://login.example.com/.../certs

After:
  issuer-uri  = https://login.example.com/realms/shop
  jwk-set-uri = https://auth-jwks.svc.cluster.local/.../certs
~~~

If both JWKS endpoints serve the **same trusted signing keys** over secure connections, this is purely a change in the **transport path for public keys**, not an issuer change. Existing JWTs remain accepted as long as signatures/claims are valid and matching keys are present.

### 14.2. Changing the Canonical Issuer

For example:

~~~text
Before:
  iss = https://old-login.example.com/realms/shop

After:
  iss = https://login.example.com/realms/shop
~~~

This is a change to the **AS's identity** under the OAuth/OIDC contract. Old and new JWTs will not share the same `iss`. If all Resource Servers suddenly switch to accepting only the new issuer, still-valid old tokens may be rejected.

Plan a migration: AS/client versions, metadata, Resource Servers, token TTLs, refresh tokens, a temporary approved issuer allowlist if accepted, and when to retire the old issuer. Never build “fuzzy issuer comparison” ignoring scheme/host/path to get past migration; that risks widening trust boundaries uncontrollably.

## 15. Why Do Issuer and Token Endpoint Not Have to Share the Same Path?

A public issuer can be:

~~~text
https://login.example.com
~~~

while the token endpoint is:

~~~text
https://login.example.com/oauth2/token
~~~

and JWKS is:

~~~text
https://login.example.com/oauth2/jwks
~~~

The issuer is the **identifier of the AS**, whereas the token endpoint/JWKS are **functional endpoints**. Never configure:

~~~yaml
issuer-uri: https://login.example.com/oauth2/token
~~~

simply because clients call the token endpoint at that URL. Take the issuer from the metadata `issuer` field or AS documentation and match it against the actual `iss` inside JWTs.

Similarly, the OpenID Connect Provider Configuration endpoint path is not always `issuer-uri + "/.well-known/openid-configuration"` across every standard/discovery pattern; for OAuth metadata, path rules differ. Rely on the official discovery mechanisms supported by your stack.

## 16. Must a Public Issuer Be Reachable by Everyone?

The issuer must be a **stable identifier usable for discovery per the system's contract**. For systems serving public clients, you usually pick a published HTTPS hostname that clients/Resource Servers can verify and connect to for metadata.

However, distinguish:

- **Issuer identifier:** the `iss` string and `issuer-uri` must match.
- **Metadata discoverability from a network:** may depend on firewalls, DNS, and ingress.
- **JWK Set retrieval:** can use a public URL, split-horizon DNS, or a trusted internal JWKS URI.
- **Endpoint access control:** endpoints like token/introspection may require their own authentication, even though metadata/JWKS are typically public information.

An internal Resource Server can use a public `issuer-uri` alongside an internal `jwk-set-uri`, provided it **preserves issuer validation and a trusted public key source**. This separates identity from transport without polluting the AS's metadata with container hostnames.

## 17. Realistic Scenario: Docker Compose Moving to Kubernetes

### 17.1. On a Developer Machine

Suppose the AS runs directly at:

~~~text
http://localhost:9000
~~~

In dev, if the AS issues tokens with `iss=http://localhost:9000`, a Resource Server running on the host can use the same issuer. However, if the Resource Server runs inside a container, `localhost` inside that container refers to the container itself, **not the host or the AS container**.

The fix is not changing `iss` per environment whenever a consumer calls it. Pick a consistent development hostname (e.g., internal DNS or controlled host mapping) and ensure every component needing the URL can route to it.

### 17.2. Moving to Kubernetes

The AS runs at:

~~~text
http://auth-service.security.svc.cluster.local:8080
~~~

Ingress serves:

~~~text
https://login.example.com
~~~

The Resource Server should trust issuer `https://login.example.com` if the AS publishes that value. Depending on network policy, the RS can:

1. Connect directly to the public HTTPS issuer through ingress.
2. Use split-horizon DNS resolving `login.example.com` to internal ingress.
3. Keep the public issuer and configure `jwk-set-uri` pointing to a trusted internal JWKS.

Never pass `auth-service.security.svc.cluster.local` into `issuer-uri` merely because it is Kubernetes's service discovery address.

### 17.3. Kubernetes Ingress and TLS Termination

Ingress may terminate TLS and send HTTP to the pod. That architecture is viable if internal traffic is secured per system requirements and proxies are trusted. However, the AS must generate metadata/token issuer/redirects from the **correct external URL**.

Check consistency across:

~~~text
Ingress host:     login.example.com
External scheme:  https
External port:    443
External prefix:  (if any)
AS public issuer: https://login.example.com[/path]
JWT iss:          https://login.example.com[/path]
RS issuer-uri:    https://login.example.com[/path]
~~~

The path component in every place must match the contract, not just the hostname portion.

## 18. A Spring Authorization Server + Resource Server Architecture

Suppose an organization has two Spring Boot services:

~~~text
https://login.example.com
  |
  +--> ingress --> spring-authorization-server:9000
                         |
                         +-- issuer: https://login.example.com
                         +-- metadata: https://login.example.com/.well-known/...
                         +-- JWKS: https://login.example.com/oauth2/jwks

https://api.example.com
  |
  +--> ingress --> orders-api:8080
                         |
                         +-- JWT issuer-uri: https://login.example.com
                         +-- audience: orders-api
                         +-- JWKS from metadata or trusted internal URI
~~~

On the Authorization Server side:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://login.example.com")
        .build();
}
~~~

On the Resource Server side:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
~~~

If `orders-api` cannot reach public metadata/JWKS, you can add:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          jwk-set-uri: https://auth-jwks.svc.cluster.local/oauth2/jwks
          audiences:
            - orders-api
~~~

The Spring Authorization Server must genuinely expose `/oauth2/jwks` and have a matching `JWKSource`; not every AS uses the same endpoint. Connections to `auth-jwks.svc.cluster.local` must be secured and serve the AS's trusted keys accurately.

**Both Resource Server configurations accept the exact same public `iss`.** They differ only in how public keys are fetched.

## 19. Multiple Issuers or Multiple Tenants

A system may have multiple public issuers:

~~~text
https://login.example.com/realms/tenant-a
https://login.example.com/realms/tenant-b
~~~

The issuer path distinguishes tenants, even when they share one host or proxy. **Do not strip paths when matching `iss`.** A JWT for tenant A is not automatically valid for tenant B's API.

If a Resource Server genuinely accepts multiple issuers, maintain an approved issuer **allowlist/registry** and a mechanism to select a decoder per issuer. You may need to read an unverified `iss` to pick a decoder, but you must:

1. Select only issuers in the trusted configured list.
2. Fetch keys from the corresponding trusted source.
3. Verify the signature and **re-validate `iss`** after decoding.
4. Enforce audience/tenant policies and resource permissions.
5. Prevent clients from arbitrarily specifying discovery/JWKS endpoints.

Never accept arbitrary issuers from tokens by auto-discovering arbitrary URLs. Behind a proxy, that risk is even more severe because internal hosts/private IPs may be reachable from the Resource Server.

## 20. Misconceptions to Avoid

**“The issuer is the internal URL where the container runs.”** Not necessarily. The issuer is the identifier issued/published by the AS; behind a proxy, it is usually the canonical public URL.

**“Since it's the same server, `http://auth-service:8080` and `https://login.example.com` count as the same issuer.”** No. These are distinct URI strings and must never be made equivalent via loose validators.

**“Changing the RS's `issuer-uri` to the internal URL is the right fix for DNS issues.”** Usually wrong if the JWT `iss` is the public URI. Fix routing or configure an internal `jwk-set-uri` while keeping issuer validation.

**“`jwks_uri` is the issuer.”** No. It is the public keys endpoint; the issuer is a separate identifier, and the token endpoint is also a separate URL.

**“Enabling `server.forward-headers-strategy: framework` is safe enough on its own.”** No. A trusted proxy must strip/overwrite untrusted forwarded headers, and the AS must enforce a proper issuer/URL policy.

**“If metadata publishes `http`, the Resource Server should turn off issuer validation.”** No. Fix external URL/issuer/forwarded configuration at the AS or proxy.

**“Trailing slashes in the issuer don't matter.”** No. The issuer value must match exactly across metadata, JWT, and RS.

**“Verifying only the signature is enough.”** No. You must check issuer, audience, lifetimes, and token policy.

**“Changing the public hostname is just a DNS change.”** Not necessarily. If the issuer changes, new tokens carry the new `iss`; clients and Resource Servers need a migration plan.

**“External metadata can publish internal hosts since the RS runs inside the cluster.”** Not advisable for metadata consumed by external clients. Keep public metadata separate from the RS's internal JWKS transport.

**“`403` errors are always caused by the issuer behind a proxy.”** No. Once JWT authentication succeeds, `403` typically points to permissions/scopes/resources.

## 21. Self-Check Questions

**Question 1.** The AS runs at `http://auth-service:8080` behind Ingress `https://login.example.com`. Tokens have `iss=https://login.example.com`. Which issuer should the Resource Server configure?

> `https://login.example.com`. That is the issuer published by the AS in tokens; `auth-service:8080` is only the internal upstream.

**Question 2.** An RS inside the cluster cannot reach `login.example.com`, yet can reach the internal JWKS. Can issuer validation still be preserved?

> Yes. Configure the canonical public `issuer-uri` together with `jwk-set-uri` pointing to the trusted internal JWKS, secure the channel, and ensure keys belong to the same AS.

**Question 3.** Metadata reports `issuer=http://auth-service:8080` while browsers hit the public HTTPS host. Where should this be fixed?

> In the AS's external issuer/hostname configuration and proxy/forwarded headers. Never edit tokens after signing and never disable issuer validation.

**Question 4.** TLS terminates at Ingress, so the AS sees HTTP requests. Which header typically informs the AS of the external scheme?

> `X-Forwarded-Proto: https` or `Forwarded: proto=https` from a trusted proxy, alongside the AS's external URL/issuer policy.

**Question 5.** An attacker can send `X-Forwarded-Host=attacker.example` directly to the AS. What is the problem?

> If the AS trusts untrusted headers, it can generate forged absolute URLs or redirects. Restrict direct backend access and strip/overwrite forwarded headers at the trusted edge.

**Question 6.** A JWT has a valid signature and right `iss`, yet `aud=billing-api` is sent to `orders-api`. Should it be accepted?

> No, if the RS requires `aud=orders-api`. Audience validation is independent of signature and issuer.

**Question 7.** The AS changes its issuer from `https://old-login.example.com` to `https://login.example.com`. Do old tokens automatically switch to the new issuer?

> No. Old tokens still carry the signed old `iss` claim; migration requires planning for clients, RSs, and token lifetimes.

## 22. References

- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `issuer-uri`, discovery, `jwk-set-uri`, and issuer/audience validation.
- [Spring Boot — Embedded Web Servers / Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/how-to/webserver.html): `server.forward-headers-strategy` and proxy support.
- [Spring Framework — Forwarded Headers / ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): handling `Forwarded`, `X-Forwarded-*`, and trust-boundary security.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` and issuer configuration.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration, issuer, and metadata.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata discovery and well-known URL construction for issuers with paths.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp` claims.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer/audience validation, key sources, and avoiding token confusion.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): `Forwarded` header when requests traverse proxies.

In a system with reverse proxies, **the public issuer is the identity contract**, whereas **internal URLs are network deployment details**. Keep JWT `iss`, metadata `issuer`, and Resource Server `issuer-uri` consistent; resolve routing differences via proxies, DNS, forwarded headers, or trusted internal JWKS sources rather than relaxing token verification.
