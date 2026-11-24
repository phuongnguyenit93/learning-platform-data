# Bearer Tokens and What Token Possession Means in Spring Security

## 1. Learning Objectives

A **bearer token** is a type of credential where the right to use it is tied to **possessing the token**. According to RFC 6750, any party that holds a valid bearer token can use it to access the resources the token permits, **without having to prove possession of a separate cryptographic key**.

In an OAuth 2.0 system, a bearer access token is typically sent by the client to an API via a header:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer token-value-issued-by-authorization-server
~~~

The API server does not trust an arbitrary string just because it follows `Bearer`; it still must **verify that the token is valid and check permissions**. However, if an attacker manages to copy a **real, still-valid token**, the attacker can send that same token from another machine and be treated like the party holding the token, unless the system adds sender-constraining.

This lesson focuses on:
- The security meaning of the phrase **"token possession"**, including the difference between true identity and the party presenting the token.
- The Authorization Server, Client, and Resource Server components, along with the authentication/authorization process.
- JWT bearer and opaque bearer tokens; a valid token is different from a token permitted for use at this API.
- Leakage, theft, and replay attacks; ways to limit damage and **sender-constrained token** options.
- How Spring Security Servlet Resource Server receives a bearer token and validates `issuer`, `audience`, time, and `scope`.

## 2. What Is a Bearer Token?

### 2.1. "Bearer" Emphasizes Token Presentation

You can think of a bearer token like an **entry ticket**: the gatekeeper verifies that the ticket was validly issued, has not expired, and grants access to the right area. The person holding the ticket might not be the original recipient. This analogy only illustrates **transferability by copying**; electronic bearer tokens are much easier to copy than physical tickets and can carry a wide variety of permissions.

For example, an OAuth access token issued to application A to call an API:
- The token has permission `orders.read`, a 15-minute lifetime, and is intended for the `orders-api` API.
- Application A sends the token in `Authorization: Bearer ...`.
- If B obtains the exact token string, **B can call the same API** while the token remains valid, with the permissions that the API accepts.
- The API can inspect `sub`, `scope`, `aud`, `iss`, `exp`, but those claims by themselves **do not prove B is A**.

**Security takeaway:** a bearer token is a **secret worth as much as the corresponding access rights**. It must be protected like a credential, even when signed and even with a short lifetime.

### 2.2. What Does "Token Possession" Mean and What Does It Not Mean?

In the bearer context, "possession" means **having the ability to present the right token** in the HTTP protocol, not:
- proving the identity of the person holding the token via password or biometrics;
- proving possession of the client's private key;
- proving the request originated from the original device;
- proving the sender logged in directly;
- or proving the token was issued directly to the calling machine.

A token can be copied from memory, logs, proxies, debugging tools, or a compromised device. An API that only sees a valid token **cannot reliably distinguish** a call from the client that was issued the token from a call by someone who stole it. This is a **design property of bearer tokens**, not a bug specific to JWTs.

### 2.3. Presenting a Token Does Not Mean Every Permission Is Accepted

Possessing a bearer token only allows using the **permissions attached to the token and the Resource Server's policies**, not every API:
- `scope=orders.read` does not automatically allow `orders.write`.
- `aud=orders-api` does not mean the `payments-api` API should accept it.
- An expired, invalidly signed, wrong-issuer, revoked, or inactive token must be rejected.
- The API still enforces object-level authorization: having `orders.read` does not automatically grant access to another user's orders.
- If a token is bound to a certificate/key using mTLS or DPoP, simply knowing the token may **not be enough**; it is no longer a pure bearer token.

## 3. Bearer Tokens in the OAuth 2.0 Flow

Core roles:

| Component | Role |
|---|---|
| Resource Owner | The person or entity who owns the protected data |
| OAuth Client | The application that wants to call an API under a granted permission |
| Authorization Server | Authenticates/authorizes according to policy and issues access tokens |
| Resource Server | The API that validates tokens and decides whether to grant access to resources |

~~~text
User ───────log in / consent───────> Authorization Server
                 │                              │
                 │      issue access token      │
                 v                              v
               OAuth Client <───────────────────┘
                    │
                    │ GET /api/orders
                    │ Authorization: Bearer <access-token>
                    v
              Resource Server
               ├─ is token genuine/validly signed or active?
               ├─ are issuer / audience / exp / nbf valid?
               ├─ scope and resource-level permissions?
               └─ allow or deny
~~~

**The Authorization Server issues**, and **the Resource Server validates and enforces policy**. A client must not fabricate a `Bearer something` string and expect the API to accept it. When an OAuth2 Client accesses an API on behalf of a user, the bearer token reflects a **granted authorization**; the token is not a copy of the user's password.

### Why Use Authorization Code + PKCE?

For interactive applications (mobile, SPA, desktop) using OAuth 2.0, the Authorization Code flow with PKCE helps reduce the risk of the authorization code being intercepted and misused when exchanged for a token. However, **PKCE does not automatically turn the issued access token into a sender-constrained token**: if the bearer access token is subsequently leaked, it can still be replayed. Do not confuse protecting the **token issuance process** with protecting the **token presentation process to the API**.

## 4. HTTP Structure: How Is a Token Sent?

In the standard and recommended approach, the client sends the token in an HTTP header:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...redacted...signature
Accept: application/json
~~~

- `Authorization`: the standard header name for transmitting credentials.
- `Bearer`: the authentication scheme per RFC 6750, typically case-insensitive for the scheme name; follow the syntax supported by the resolver.
- What follows the space is the token; **do not include angle brackets, quotes, or a second `Bearer` prefix** inside the value.
- Response `Content-Type` or a JSON body is not the default place to carry a bearer token.
- HTTP is merely the transport for the token; always use **HTTPS with proper server authentication**.

**Avoid passing bearer tokens in URL query parameters**, such as `?access_token=...`: URLs can end up in browser history, reverse-proxy logs, analytics, monitoring, bookmarks, and other tracking systems. RFC 6750 describes a few ways to pass bearer tokens outside headers for compatibility, but URL transmission is discouraged and Spring Security focuses by default on the `Authorization` header.

Never treat a client-supplied header like `X-User: alice` or `X-Scope: admin` as authentication proof. The API must derive identity/permissions from a **verified token**, not from self-asserted client fields.

## 5. A Valid Token Is Not Necessarily Right for the Purpose

### 5.1. A JWT Can Be Read, but Its Contents Are Not Yet Trustworthy

A JWT typically has three parts `header.payload.signature`, Base64URL-encoded and joined by dots:

~~~text
<base64url-header>.<base64url-payload>.<base64url-signature>
~~~

Example **illustrative payload**, not a real token:

~~~json
{
  "iss": "https://idp.example.org/realms/demo",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893453300,
  "jti": "example-token-id-42"
}
~~~

These timestamps are for illustration only. Common claims:
- `iss` (*issuer*): the organization/server that issued the token; must be on the trusted list.
- `sub` (*subject*): the subject identifier within the issuer's namespace; does not by itself prove the caller presenting the request is the subject.
- `aud` (*audience*): the API or target audience the token was issued for; must include the API receiving the token.
- `exp` (*expires at*): after this time the token must not be used, accounting for reasonable clock skew.
- `nbf` (*not before*): the token must not be accepted before this time.
- `iat` (*issued at*): issuance time; useful for policy, but does not replace `exp`.
- `scope` / `scp`: permissions granted according to the issuer's contract; must be mapped properly.
- `jti`: token ID; can be used in tracking/revocation systems if the architecture supports it, though it does not automatically make a token single-use.

**A JWS-signed JWT has a signature, not default content encryption.** Anyone holding the token can usually read the payload after Base64URL decoding. Therefore, do not put passwords, secrets, or unnecessary sensitive data in a JWT. Decoding the payload or using a JWT debugger **is not verification**: the Resource Server must verify the signature using a trusted key, allowed algorithms, and claims/policies.

### 5.2. Validating a JWT at the Resource Server

A JWT should go through at least the following checks:

1. Validate structure, token type, and allowed signing algorithms; **do not trust an `alg` declared by an attacker to bypass verification**.
2. Obtain the proper public key/JWKS of a trusted issuer, verify the signature, and handle key rotation; do not use an arbitrary key/issuer from an untrusted claim.
3. Validate `iss`, `exp`, `nbf`, and `aud` accurately for the application; do not accept tokens intended for another service.
4. Verify that the token is an **appropriate access token** rather than confusing an ID Token or refresh token; check `typ`, `client_id`, and the RFC 9068 profile depending on token type/IdP.
5. Check scopes/authorities and **object-level authorization**.
6. When near-real-time revocation is required, add a strategy to reject old tokens (such as introspection, a `jti` denylist, shorter TTL, or session checks) suited to the architecture.

**A valid signature proves the token was signed by the corresponding key**, not who sent the request. A JWT signed by the issuer remains a bearer credential if the API only requires presenting the JWT string.

### 5.3. Opaque Tokens Do Not Change the Bearer Property

An opaque token is typically an unpredictable string with no public claims:

~~~text
6dP0...random-opaque-token...9x2Q
~~~

The Resource Server can call the Authorization Server's **introspection endpoint** to learn `active`, subject, scopes, expiry, and metadata. Unlike a JWT, the client cannot read claims inside the string. But if the token is used as a bearer token, **anyone who obtains the valid opaque string can still replay it**, just like a JWT bearer token.

| Criterion | JWT bearer | Opaque bearer |
|---|---|---|
| Format | Structured token, typically digitally signed | Reference string / opaque value |
| Verification | JWT signature and claim validators | Typically server introspection |
| Contains decodable claims | Usually yes | Not required |
| Replay resistance if token is copied | No, if pure bearer | No, if pure bearer |
| Near-real-time revocation | Requires extra strategy or short token TTL | Introspection can check `active` at call time |
| Common implementation mistakes | Missing `aud`, trusting wrong `alg`, exposing payload | Not checking `active`/metadata, wrong caching, timeouts |
| Requires HTTPS | Yes | Yes |

### 5.4. Access Token, ID Token, and Refresh Token

- **Access token**: the credential presented by the Client to the **Resource Server** to access resources.
- **ID Token**: an OIDC token describing an authentication event and identity for the **Relying Party/OIDC Client**; it is not automatically a valid API access token. APIs must reject tokens with the wrong audience or type.
- **Refresh token**: used with the Authorization Server to obtain a new access token while still eligible, **not used as a bearer access token to call a Resource Server**. Refresh tokens are typically more sensitive because they can mint multiple future access tokens; they require protection, rotation/binding, and revocation policies.

Never conclude that "because a token has `sub=alice`, every API must log Alice in." You must verify **who the token is for, who issued it, what permissions it carries, when it is valid, and whether it can be revoked**.

## 6. Why Is Token Theft Dangerous?

### 6.1. Replay: Reusing an Exposed Token

~~~text
Authorization Server
      │ issues access token to Client A
      v
Client A ─── Authorization: Bearer TOKEN ───> Orders API
      │
      │ Token is leaked (XSS, logs, debug, extension...)
      v
Attacker B ─ Authorization: Bearer TOKEN ───> Orders API
                                               │
                                               └─ API sees valid token
                                                  → may accept B
~~~

An attacker **does not need to break the JWT signature** or guess a password. They simply copy the real token string and call the API. Depending on the token, they can read or modify data within the granted scope. Restricting `aud` and `scope` reduces the blast radius, but **does not identify who presented the token**.

### 6.2. Common Leakage Paths

| Leakage Source | Scenario | Mitigation |
|---|---|---|
| HTTP over an unprotected channel | Token is eavesdropped or altered in transit | Standard HTTPS/TLS, hostname/CA verification |
| URL query, mishandled URL fragment | Token enters logs, history, analytics, copied links | Use `Authorization` header; never pass bearer tokens in URLs |
| Console/logging | Logging raw `Authorization`, request/response, token claims | Redact/mask in app, gateway, APM, tracing |
| Browser XSS | Malicious script reads token from storage/JS memory or abuses session privileges | Prevent XSS, CSP, minimize storing tokens in JS, consider BFF |
| LocalStorage/SessionStorage | JS running on the same origin can read the token | Do not treat Web Storage as safe against XSS |
| Compromised client/mobile/desktop | Malware/extension or file dump reads the token | OS secure storage, shorter TTL, device controls |
| Sending token to the wrong API | Token goes to an untrusted host/redirect/proxy | Allowlist destinations, do not blindly forward Authorization across redirects |
| Third-party logs | Client SDK/APM collects headers | Govern collected fields, secret scrubbing, and auditing |
| Poorly stored refresh token | Attacker keeps minting new access tokens | Refresh rotation, client binding, revocation, and reuse detection |

**Browser note:** an `HttpOnly` cookie can prevent JavaScript from directly reading the cookie value, but the browser still sends the cookie automatically under its rules; proper `Secure`, `SameSite`, CSRF, and XSS protections are needed according to the architecture. The Backend-for-Frontend (BFF) pattern can keep OAuth tokens on the server and only use a controlled session cookie with the browser.

### 6.3. Impact Depends on the Token's Permissions

- A token with only `orders.read` can still leak data; read-only does not mean "safe."
- A token with `orders.write` can create/modify orders within allowed permissions.
- A token intended for multiple APIs or overly broad permissions increases the **blast radius**.
- A token living for hours/days allows longer replay; a short TTL narrows the window, but **does not prevent immediate replay**.
- If an attacker obtains a **refresh token**, they can continue obtaining new access tokens unless constrained/bound or revoked.

## 7. Defense: From Permission Scoping to Sender-Constrained Tokens

### 7.1. Protecting Pure Bearer Tokens

1. **TLS on every hop:** HTTPS from client to gateway/API; if TLS is terminated at a proxy, the proxy→backend link must also have a trusted path, network controls, and appropriate TLS/mTLS.
2. **Limit permissions:** issue tokens with the exact `aud`, least-privilege scopes, and resource/tenant/object-level policies.
3. **Reduce lifetime:** short-lived access tokens balancing UX and risk, tightly controlled refresh tokens; do not assume a short TTL solves replay completely.
4. **Protect at the client:** avoid storing plaintext on disk; keep tokens out of URLs/logs; mitigate XSS and manage credentials per platform.
5. **Validate strictly at the API:** signature/introspection, issuer, audience, time, token type, and authorization. Every sensitive API must enforce object-level checks.
6. **Revocation/rotation:** have a plan when a token leaks; for self-contained JWTs, clarify the latency of denylists/introspection/logout and key rotation.
7. **Observability:** log `requestId` and verified subject/issuer/scope where permitted, along with rate and risk signals; never log raw token strings. Apply rate limiting and anomaly detection.
8. **Fail closed:** JWKS/introspection/certificate/clock failures or missing permissions must deny access, never allow by default.

### 7.2. How Sender-Constrained Tokens Differ from Pure Bearer Tokens

**Sender-constrained / proof-of-possession** requires the presenter of a token to additionally prove possession of a secret or private key bound to the token. Two common techniques:

| Mechanism | Principle | Implementation Requirements |
|---|---|---|
| **mTLS certificate-bound access token** (RFC 8705) | Authorization Server binds the token to the client certificate; Resource Server verifies the client's certificate matches the binding | mTLS connection, cert/`cnf` binding verification, proxy support, key management |
| **DPoP** (RFC 9449) | Client signs a proof JWT for the request using a private key; the token is bound to that public key | Proof signature verification, `htm`, `htu`, `iat`, `jti`, `ath`, replay cache/nonce per policy, and key binding |

With DPoP, the token is typically presented using the `DPoP` scheme alongside a `DPoP` header containing the per-request proof, rather than just `Bearer token`. **Merely renaming the header to `DPoP` does not provide protection**: the Authorization Server must issue a key-bound token and the Resource Server must verify the proof and binding. An API that only enables `oauth2ResourceServer().jwt()` for standard bearer tokens **does not automatically implement full DPoP or mTLS-bound access tokens**.

### 7.3. Measures That Do Not Prevent Replay on Their Own

- **Signing a JWT:** prevents tampering with token contents, not copying the entire token.
- **Encrypting a token:** can protect contents from parties lacking the decryption key, but if the API accepts the token as a bearer token, a copy still works.
- **IP allowlist/UA fingerprint:** can be a risk-reduction layer, but NAT/mobile networks change and headers can be spoofed; not equivalent to proof-of-possession.
- **CORS:** enforced in browsers, does not stop `curl` or another server from sending a stolen bearer token.
- **`HttpOnly` cookie:** reduces JS ability to read the cookie, does not by itself block requests triggered by XSS or all CSRF.
- **Frontend-only logout:** deleting the token from the client does not necessarily revoke tokens already issued and held by an attacker.

## 8. How Does Spring Security Receive and Process Bearer Tokens?

In a **Servlet Resource Server** application, the typical pipeline is:

~~~text
HTTP Authorization: Bearer ...
           │
           v
BearerTokenAuthenticationFilter
           │ resolve bearer string (from Authorization by default)
           v
BearerTokenAuthenticationToken
           │
           v
AuthenticationManager / ProviderManager
           │
           ├─ JWT   → JwtAuthenticationProvider → JwtDecoder/validators
           │                                     → JwtAuthenticationToken
           │
           └─ Opaque→ OpaqueTokenAuthenticationProvider
                       → OpaqueTokenIntrospector
                       → BearerTokenAuthentication
           │
           v
SecurityContext (principal/authorities)
           │
           v
AuthorizationFilter → endpoint or 401/403
~~~

- **BearerTokenAuthenticationFilter** extracts the token from the request; it does not trust the token merely because the header exists.
- **JWT**: `JwtDecoder` verifies the signature and claims, then `JwtAuthenticationConverter` maps them to `Authentication` and authorities.
- **Opaque**: `OpaqueTokenIntrospector` queries the Authorization Server and handles whether the token is still `active`; audience/scope policies must be configured per contract.
- **Authorization** still runs after authentication: a token that authenticates successfully but lacks `SCOPE_orders.read` cannot call `GET /api/orders`.
- Resource Server authenticates **tokens for API requests**, distinct from the `oauth2Login()` flow used for browser logins.

### Distinguishing 401 and 403 Status Codes

| Scenario | Meaning | Typical HTTP Status |
|---|---|---|
| Missing bearer token on an endpoint requiring authentication | No credential provided to authenticate | **401 Unauthorized** |
| Forged, malformed, bad-signature, expired, or wrong-issuer/audience token | Invalid credential | **401 Unauthorized**, typically with `WWW-Authenticate: Bearer` and appropriate error |
| Valid token, missing scope/permission | Authenticated, but blocked at authorization | **403 Forbidden**, possibly `insufficient_scope` |
| Valid token and matching scope, but another user's object | Data access policy denies | **403** or **404** depending on non-disclosure design |
| Introspection/JWKS unavailable | Cannot safely verify token | Deny access; 5xx/401 depending on error type and handler |

Never infer that "HTTP 401 means wrong password": for an OAuth Resource Server, the cause may be a missing, expired, wrong-audience, or invalidly signed token.

## 9. Hands-On Example: Spring Boot 3.x, Spring Security 6.x, Java 17+

The following example is a **Resource Server accepting only JWT bearer tokens** from a trusted issuer, requiring `aud=orders-api` and scope `orders.read`. The code is written for a complete Spring Boot application without needing to write a custom JWT decoder. The issuer URL is an illustrative domain only; to run against a real server, replace it with an Authorization Server exposing discovery/JWKS and real tokens.

### 9.1. Create the Maven Project

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>bearer-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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

Spring Boot manages compatible Spring Security versions. The Resource Server starter brings in the Resource Server and JOSE dependencies needed for JWTs. Never parse tokens yourself with `Base64.getDecoder()` to make authorization decisions.

### 9.2. `application.yml`: Issuer and Audience Must Be Valid

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/demo
          audiences:
            - orders-api
~~~

- `issuer-uri` must **exactly** match `iss` in the token and point to an issuer with valid metadata/discovery.
- `audiences` requires the access token to contain `orders-api` in `aud`; this **blocks tokens that are valid but intended for another API**.
- Spring Security checks the JWT signature, `iss`, `exp`, and `nbf` per standard configuration; Boot supports `audiences` as shown above.
- Only trust issuers, signing algorithms, and JWKS per contract; never take `issuer-uri` from client-supplied request data.

### 9.3. Startup Class

File `src/main/java/com/example/bearer/BearerDemoApplication.java`:

~~~java
package com.example.bearer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BearerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BearerDemoApplication.class, args);
    }
}
~~~

### 9.4. SecurityFilterChain Allowing Only Reading Orders

File `src/main/java/com/example/bearer/SecurityConfiguration.java`:

~~~java
package com.example.bearer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

**Analysis:**
- `oauth2ResourceServer().jwt()` wires filter → provider → JWT decoder according to Spring Security.
- `SCOPE_orders.read` is the standard authority mapped by the JWT converter from scope `orders.read`; this is an **endpoint call permission**, not proof that the token holder is the original subject.
- `SessionCreationPolicy.STATELESS` avoids relying on server-side session Authentication for the demo API.
- `anyRequest().denyAll()` keeps all other routes closed by default, including unauthorized debug routes.
- The example only has GET; CSRF does not block GET by default. For a real API using bearer headers and not relying on automatically sent cookies, an appropriate CSRF strategy can be designed. **Do not disable CSRF on an application using browser cookies just because JWTs are used elsewhere.**
- Do not put `access_token` in paths, query parameters, or logs while testing.

### 9.5. Illustrative Endpoint

File `src/main/java/com/example/bearer/OrderController.java`:

~~~java
package com.example.bearer;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/api/orders")
    public List<OrderSummary> list() {
        return List.of(
                new OrderSummary("ORD-001", "Notebook"),
                new OrderSummary("ORD-002", "Keyboard"));
    }

    public record OrderSummary(String id, String description) {}
}
~~~

The endpoint returns **in-memory mock data** for learning about bearer tokens; in production you must filter orders by authenticated tenant/user. `hasAuthority` checks endpoint-level permission and **does not replace object-level authorization**.

Build/run (with Java 17+ and Maven installed):

~~~bash
mvn clean package
java -jar target/bearer-demo-0.0.1-SNAPSHOT.jar
~~~

The application may start even when issuer metadata is not yet reachable depending on version/configuration, but when processing a token it must reach/read valid keys. To get `200`, you need a **real** JWT with a valid signature, issuer `https://idp.example.org/realms/demo`, audience `orders-api`, valid `exp`, and scope `orders.read`.

### 9.6. Testing with curl

~~~bash
# Without token:
curl -i http://localhost:8080/api/orders

# With a real token obtained from the configured Authorization Server:
curl -i -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    http://localhost:8080/api/orders
~~~

Set `ACCESS_TOKEN` as an environment variable in your test environment; do not print the token to terminal logs. The sample above uses localhost for learning; in real environments always call over HTTPS.

**Expectations:**
- Missing token: HTTP `401`.
- Bad signature / expired / wrong issuer or `aud`: HTTP `401`.
- Valid JWT with matching audience but missing `orders.read`: HTTP `403`.
- Valid JWT with `orders.read`: HTTP `200` and JSON equivalent to:

~~~json
[
  {"id": "ORD-001", "description": "Notebook"},
  {"id": "ORD-002", "description": "Keyboard"}
]
~~~

Key ordering in JSON is insignificant; actual output depends on a real token/provider. This is **expected behavior by configuration**, not stdout generated from an illustrative token.

### 9.7. Using an Opaque Token Instead of a JWT

Keep the Controller/authorization rule, but replace the Resource Server DSL:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
        .opaqueToken(Customizer.withDefaults()))
~~~

And replace the `jwt` section in `application.yml` with:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.org/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

This is an **alternative configuration**, not declared simultaneously with the JWT example in a simple resource server. The Authorization Server must support introspection; introspection credentials are API secrets and must come from a secret manager, never committed. Check scope/audience per the introspection response contract; do not allow a token lacking permissions merely because `active=true`.

## 10. Scenario Walkthrough: Before and After Token Exposure

Suppose Alice is a legitimate user, and Alice's token is a signed, unexpired bearer JWT with audience `orders-api` and scope `orders.read`.

**Before exposure:**
1. Alice logs in at the Authorization Server via a valid flow.
2. The OAuth Client receives the token.
3. The Client calls `GET /api/orders` with `Authorization: Bearer tokenAlice`.
4. The API validates the JWT and returns data matching Alice's permissions.

**After the token is copied:**
1. A malicious script obtains `tokenAlice` from logs/storage.
2. The script on another machine sends the same header `Authorization: Bearer tokenAlice`.
3. If the API only validates the JWT as a standard bearer token, the script's request still passes **signature, issuer, audience, scope, and expiry** checks, because all of those remain true.
4. The API has no independent proof that the new request came from Alice or the original client. If object authorization relies solely on Alice's claims, the script can read Alice's resources.

**How to reduce risk:** eliminate leakage at the source, reduce TTL/permissions, revoke exposed tokens, and for systems requiring strong replay resistance, use token issuance/validation with DPoP or mTLS-bound access tokens. Enabling HTTPS is mandatory, yet does not stop tokens already stolen from a client or log.

## 11. Security Test Matrix for Bearer Tokens

| Test Case | Input | Expected Result |
|---|---|---|
| No token | GET without `Authorization` | 401 |
| Wrong header scheme | `Authorization: Basic ...` | Must not be treated as authenticated bearer |
| Fabricated string | `Authorization: Bearer garbage` | 401 |
| Tampered JWT payload | Change `scope`, keep old signature | 401 due to invalid signature |
| Valid signature, different issuer | `iss` not a trusted issuer | 401 |
| Token for another API | `aud` does not contain `orders-api` | 401 |
| Expired / not-yet-valid token | Past `exp` or future `nbf` | 401 considering clock skew |
| Valid token, missing scope | Only has `orders.write` | 403 when calling GET requiring `orders.read` |
| Valid token, matching permissions | `orders.read` + valid issuer/audience | 200 for the demo endpoint |
| Valid scope, accessing another user's order | Object ID outside user's ownership | 403/404 by design |
| Copy Alice's token to machine B | Unexpired bearer token | May still work: **this is the bearer property**; test demonstrates the risk |
| Revoked token | Revocation/introspection/denylist in effect | Must no longer be accepted |
| Copied DPoP/mTLS-bound token without proof | Different key/cert or invalid proof | Must be rejected if Resource Server supports it fully |
| Auth/JWKS/introspection failure | No reliable verification data available | Fail closed |
| Token in URL/log | Query `access_token` or logging full header | Blocked / raw credential not logged per policy |

**Test framework note:** `spring-security-test` with `MockMvc` and `jwt()` can test *authorization* (`SCOPE_...` → 200/403), but uses a mock JWT principal and **does not verify real signature/JWKS/issuer/audience**. To test token validation, run integration tests with test public keys/JWKS and real signed JWTs, or test `JwtDecoder` directly. Never claim a system resists replay based solely on scope tests.

## 12. Operations and Incident Checklist

Before taking an API using bearer tokens to production:

- [ ] Resource Server validates tokens via JWT signature/issuer/audience/time or trusted opaque introspection.
- [ ] ID Tokens and refresh tokens are never accepted in place of access tokens.
- [ ] Each API has its own audience and least-privilege scopes/permissions; object-level authorization is enforced.
- [ ] Tokens are transmitted only over HTTPS, preferably in the `Authorization` header; never in URL query parameters.
- [ ] Gateways, access logs, APM, metrics, exception handlers, and debug tools redact tokens.
- [ ] Access tokens and refresh tokens are not stored in easily readable client locations; XSS, CSRF, and BFF/cookies have been analyzed.
- [ ] Token TTLs are appropriate; refresh tokens use protection/rotation/reuse detection matching risk.
- [ ] There is a playbook to revoke tokens/token families/sessions on exposure, including unexpired JWTs.
- [ ] Policies exist for key/JWKS rotation and handling issuer downtime.
- [ ] Never trust client-supplied `X-User`, `X-Role`, or `X-Forwarded-For` in place of bearer token verification.
- [ ] Negative tests exist: fake, expired, wrong aud, wrong iss, missing scope, tenant/object mismatch.
- [ ] If tokens must not be replayable simply by copying, **true sender constraints** (mTLS/DPoP) are enforced by both issuer and API.
- [ ] Operators distinguish `401` (invalid/missing token) from `403` (valid token, insufficient permissions).

When leakage is suspected:
1. Identify the affected issuer, client, audience, and time window/token family from safe metadata **without spreading the raw token**.
2. Revoke or invalidate related tokens/sessions and refresh tokens according to Authorization Server capabilities; if JWTs are not directly revocable, apply a denylist/reduce TTL/appropriate controls.
3. Patch the leak source (logs, XSS, proxy, storage), rotate keys/secrets if actually compromised, and audit abnormal access activity.
4. Re-test all validation and authorization checks; add controls to prevent recurrence.

## 13. Common Misconceptions

1. **"A signed JWT cannot be stolen and reused."** False. A signature prevents payload tampering, while a valid copied JWT remains a usable credential.
2. **"A token with `sub=alice` means the request came from Alice."** False. The claim describes the subject the token represents, not the device or presenter of the bearer token.
3. **"Using HTTPS makes token leakage impossible."** False. TLS protects the transport path properly; tokens can still leak at endpoints, logs, extensions, or via XSS.
4. **"Opaque tokens resist copying better than JWTs."** False. Both can be bearer tokens; the difference lies in how they carry data and how they are verified.
5. **"Checking signature + `exp` is enough."** False. You must also check `iss`, `aud`, token type, scopes/roles, and allowed data access.
6. **"An ID Token contains email and name, so it can call APIs."** False. APIs must require an access token with the proper audience and token profile.
7. **"Having `SCOPE_orders.read` allows reading all orders."** False. Endpoint permissions do not replace object/tenant authorization.
8. **"Logging out deleted the token in the browser, so stolen tokens are invalidated."** Not necessarily. Revocation/expiry policies and session/refresh handling are required.
9. **"CORS stops someone from using a stolen bearer token."** No. Non-browser HTTP clients are not bound by CORS.
10. **"Changing `Authorization: Bearer` to `DPoP` prevents replay."** False. Full token binding and proof verification are required.
11. **"Setting audience binds the token to a device."** False. Audience binds the intended receiving resource, not the presenter.
12. **"Rate limiting replaces token validation."** No. Rate limiting reduces attack volume, not credential verification.

## 14. Key Takeaways

**Bearer = anyone who holds a valid token can present it to exercise its permissions.** The server validates the token and policies, yet presenting a token **does not by itself prove the identity of the holder**. Both JWT and opaque tokens can be bearer tokens. Signatures, scopes, issuer, audience, expiration, TLS, and revocation help protect and bound permissions; if you must prevent **copying a token for use on another machine**, you need an end-to-end verified sender-constrained design such as mTLS certificate binding or DPoP.

## 15. References

1. [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer definition, `Authorization: Bearer`, risks, and protections.
2. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): modern OAuth security recommendations.
3. [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): client certificate-bound access tokens.
4. [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): public/private key-bound tokens and per-request proofs.
5. [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT token profile for access tokens.
6. [Spring Security 6.5 — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT validation, issuer, audience, scopes, and authentication flow.
7. [Spring Security — Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): BearerTokenResolver and token extraction.
8. [Spring Security — Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `active` introspection, principal, and scopes.
9. [Spring Boot — OAuth2 Security Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): `issuer-uri`, `audiences`, Resource Server properties.
