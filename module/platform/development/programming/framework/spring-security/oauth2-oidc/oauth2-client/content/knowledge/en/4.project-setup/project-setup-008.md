# 4.8. Configuring Redirect URIs for Local, Staging, and Production

When configuring **Spring Security OAuth 2.0 / OIDC Client**, one of the most error-prone settings is the **Redirect URI**. A small mismatch in `http`/`https`, domain name, port, context path, or `registrationId` can cause the Identity Provider to reject the login flow before the application ever receives an authorization code. Another common error occurs behind a reverse proxy: the browser accesses the app over public HTTPS, yet Spring Boot generates a callback containing HTTP or an internal hostname.

This lesson guides you through configuring Redirect URIs consistently across **local**, **staging**, and **production** environments via Spring Boot configuration, Spring Security, and client registration at the Authorization Server/OpenID Provider (OP).

## 1. Where Does the Redirect URI Fit in the OAuth 2.0 / OIDC Flow?

The **Redirect URI** (also called *callback URI*) is the **client application** address to which the Authorization Server sends the browser back after authentication and consent. In the **Authorization Code Flow**, the callback typically receives `code` and `state` parameters.

For example, a user opens:

```text
https://app.example.test/account
```

The application redirects the user to the OP:

```text
https://id.example.test/authorize?
  response_type=code&
  client_id=web-prod&
  redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
  scope=openid%20profile&
  state=<random-state>
```

After authentication, the OP redirects the browser back to:

```text
https://app.example.test/login/oauth2/code/company?code=<authorization-code>&state=<random-state>
```

The Spring Security application verifies `state`, uses the authorization code to call the token endpoint, and, for OIDC, validates the ID token before completing login.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant App as Spring Boot Client
    participant OP as Authorization Server / OP

    U->>B: Open /account
    B->>App: GET https://app.example.test/account
    App-->>B: Redirect to OP /authorize
    B->>OP: response_type=code; redirect_uri=public callback
    OP->>U: Login, MFA, consent (if needed)
    OP-->>B: Redirect to app callback with code, state
    B->>App: GET /login/oauth2/code/company?code=...&state=...
    App->>App: Verify state, saved authorization request
    App->>OP: Exchange authorization code for tokens
    OP-->>App: Token response
    App->>App: Validate OIDC, establish session
    App-->>B: Return to application / original page
```

### Distinguishing Three URLs

| URL | Role | Example |
| --- | --- | --- |
| **OP Authorization endpoint** | Where the browser goes to log in / grant consent | `https://id.example.test/authorize` |
| **Client Redirect URI** | Where the OP sends the browser back with `code` and `state` | `https://app.example.test/login/oauth2/code/company` |
| **Post-login destination page** | The page the application wants to show after login succeeds | `https://app.example.test/account` |

**The Redirect URI is neither the home page nor the post-login destination page.** Spring Security handles the callback at a dedicated endpoint and only then forwards the user to the originally requested resource or configured success URL.

**The OIDC post-logout redirect URI is also a separate URI type.** It returns the user after logging out at the OP and does not replace the login Redirect URI.

## 2. Spring Security's Default Callback Convention

For a Servlet application using `oauth2Login()`, Spring Security typically uses this default endpoint pair:

| Step | URL Pattern |
| --- | --- |
| Initiate login for a registration | `/oauth2/authorization/{registrationId}` |
| Receive the Authorization Code callback | `/login/oauth2/code/{registrationId}` |

In Spring Boot's client configuration, the key property is:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
```

Where:

- **`{baseUrl}`**: base URL computed by Spring Security from the current request, typically including scheme, host, port, and context path.
- **`{registrationId}`**: registration name in configuration, `company` in this example.
- **`/login/oauth2/code/*`**: callback path handled by the default `OAuth2LoginAuthenticationFilter`.

For example, when the application runs directly at `http://localhost:8080`, the generated URI is:

```text
http://localhost:8080/login/oauth2/code/company
```

With public origin `https://app.example.test`:

```text
https://app.example.test/login/oauth2/code/company
```

**Crucial point:** the value sent in the `redirect_uri` parameter of the authorization request must be a valid URI registered at the OP for that exact `client_id`. Most OPs require an exact match against a registered entry under their validation policy. Do not assume you can change ports or hostnames without updating the OP side.

## 3. Designing for Local, Staging, and Production

Suppose the application uses `registrationId = company` across every environment, while maintaining **separate client registrations on the Authorization Server** to isolate secrets, redirect URIs, and access policies.

| Environment | Public Origin Used by Browser | Redirect URI to Register at OP |
| --- | --- | --- |
| **Local** | `http://localhost:8080` | `http://localhost:8080/login/oauth2/code/company` |
| **Staging** | `https://staging.app.example.test` | `https://staging.app.example.test/login/oauth2/code/company` |
| **Production** | `https://app.example.test` | `https://app.example.test/login/oauth2/code/company` |

The `example.test` domains are for illustration only; replace them with real deployment addresses.

One way to organize clients on the OP:

```text
Authorization Server / OpenID Provider
├── Client: app-local
│   ├── Client ID: <local-client-id>
│   └── Redirect URI:
│       http://localhost:8080/login/oauth2/code/company
├── Client: app-staging
│   ├── Client ID: <staging-client-id>
│   └── Redirect URI:
│       https://staging.app.example.test/login/oauth2/code/company
└── Client: app-prod
    ├── Client ID: <production-client-id>
    └── Redirect URI:
        https://app.example.test/login/oauth2/code/company
```

The three client IDs at the OP **do not have to match `registrationId` in Spring Boot**. `registrationId` is the application's internal configuration key; `client-id` is the identity issued by the OP for the client. Keeping the same `company` name across deployments helps reuse configuration and callback paths.

Separating client IDs and secrets between staging and production is usually valuable because you can revoke them independently and restrict each environment's redirect allowlist, scopes, and permissions. If the OP supports separate realms/tenants, consider isolating test accounts and staging APIs from production data as well.

### Why Keep the Callback Path Consistent?

Keeping `/login/oauth2/code/company` identical across environments helps:

1. Avoid editing Java code just because a domain or port changed.
2. Easily compare a URI registered at the OP against the URI emitted by the app.
3. Keep `SecurityFilterChain` and OAuth2 Login configurations uniform.
4. Make clear that environment differences live in **public origin**, **client credentials**, **issuer**, and proxy infrastructure.

However, not every environment is forced to share the same path if routing infrastructure differs. When paths differ, both Spring Security configuration and the OP's allowlist must align.

## 4. Shared Configuration in Spring Boot

Example for **Spring Boot 3.x / Spring Security 6.x**, a Servlet web application logging in via OIDC Authorization Code.

### 4.1. `application.yml`: Shared Configuration

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}

server:
  port: 8080
```

- **`OIDC_CLIENT_ID`** and **`OIDC_CLIENT_SECRET`** come from environment-specific secret configuration; never commit real values to the repository.
- **`OIDC_ISSUER_URI`** points to the OP issuer supporting discovery; the issuer in tokens must match what the client trusts.
- **`redirect-uri`** uses Spring Security's standard placeholders, avoiding hardcoding localhost into deployed images/containers.
- **`server.port`** is the port Spring Boot listens on inside its runtime environment. The public port may be 443 if the app sits behind a reverse proxy.

Depending on your organization, client ID/secret/issuer can be provided via environment variables, a secrets manager, Kubernetes Secrets, or centralized config. What is essential is that **each deployment receives the right environment variables**, and the public callback address is in the corresponding OP's allowlist.

### 4.2. Configuring `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

When a user accesses a protected resource, Spring Security can send them to a login selection page or start the authorization flow per configuration. You can also render a link:

```html
<a href="/oauth2/authorization/company">Sign in with company account</a>
```

With the default configuration, **you do not need to write a controller for `/login/oauth2/code/company`**. The callback is handled by the OAuth2 Login filter before an MVC controller receives the request. Declaring a controller at that URL usually fails to fix redirect URI errors and can confuse the flow.

## 5. Local Setup

In a local environment, a Spring Boot application runs at:

```text
http://localhost:8080
```

You can register the following callback on the `app-local` client at the OP:

```text
http://localhost:8080/login/oauth2/code/company
```

Example startup with the `local` profile and matching environment variables:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:OIDC_CLIENT_ID = "<local-client-id>"
$env:OIDC_CLIENT_SECRET = "<local-secret>"
$env:OIDC_ISSUER_URI = "https://id-dev.example.test/realms/demo"

./mvnw spring-boot:run
```

Use `./gradlew bootRun` if the project uses Gradle; these commands merely illustrate launching and do not dictate a specific build tool.

**Easy-to-miss details in local setup:**

- `localhost` and `127.0.0.1` are two distinct hostnames for Redirect URI matching.
- `8080` and `8081` are two distinct ports. If `server.port` changes, the callback changes too.
- `http` and `https` are two distinct schemes.
- `/login/oauth2/code/company` and `/login/oauth2/code/company/` differ by a trailing slash.
- Some OPs allow `http` only for loopback/`localhost` in development; production must use HTTPS. Exact rules vary by OP.
- If the OP runs inside Docker while the user logs in via a browser outside the container, **the Redirect URI must still be a URL reachable by the browser**, not an internal Docker hostname like `http://spring-app:8080`.

If you run the app in a container with port mapping `-p 8080:8080`, the browser still visits `localhost:8080` and the corresponding callback remains localhost. If the browser actually connects via a different domain or port, base the callback on that actual URL.

### 5.1. When Local Uses HTTPS

If configuring local TLS at `https://localhost:8443`, register the exact URI:

```text
https://localhost:8443/login/oauth2/code/company
```

The local certificate must be trusted by the browser to avoid warnings or interruptions. Never casually disable TLS verification in configurations carried over to real environments.

## 6. Staging Setup

Staging usually has **its own domain, HTTPS, and a proxy/load balancer** in front of Spring Boot. For example:

```text
Internet / Browser
    |
    | HTTPS https://staging.app.example.test
    v
Ingress / Reverse Proxy :443
    |
    | HTTP http://spring-app:8080 (internal network)
    v
Spring Boot
```

Here, register the **public URL**:

```text
https://staging.app.example.test/login/oauth2/code/company
```

**Do not register an internal URI** like `http://spring-app:8080/login/oauth2/code/company`, because the browser cannot reach it and it does not reflect the address users visit.

Staging can use a test client ID, secret, and issuer:

```text
OIDC_CLIENT_ID=<staging-client-id>
OIDC_CLIENT_SECRET=<staging-client-secret>
OIDC_ISSUER_URI=https://id-staging.example.test/realms/company
```

When using the `{baseUrl}` placeholder, Spring Security must know the browser is using HTTPS and the public hostname even though the backend receives an internal request. That involves **forwarded headers** (section 8).

## 7. Production Setup

Production needs a stable origin and HTTPS:

```text
https://app.example.test/login/oauth2/code/company
```

At the OP, create a dedicated production client and register this exact URI. Grant only necessary scopes; manage the client secret in a secrets system with strict access control.

A clear deployment convention:

| Parameter | Local | Staging | Production |
| --- | --- | --- | --- |
| `SPRING_PROFILES_ACTIVE` | `local` | `staging` | `prod` |
| Public origin | `http://localhost:8080` | `https://staging.app.example.test` | `https://app.example.test` |
| `OIDC_CLIENT_ID` | Local Client ID | Staging Client ID | Production Client ID |
| `OIDC_CLIENT_SECRET` | Local secret if needed | Staging secret | Production secret |
| `OIDC_ISSUER_URI` | Local/dev issuer | Staging issuer | Production issuer |
| Redirect URI at OP | Matches local origin | Matches staging origin | Matches production origin |

One application image can be deployed across all three environments using different **externalized configurations**. Avoid editing Java files or rebuilding images solely to change callback URLs.

### When to Share One Client ID Across Multiple Environments?

Some OPs let you list multiple Redirect URIs for the same client ID. That setup can work, but it creates shared dependencies on secrets, scopes, and policies across environments. **Separating client registrations** helps prevent a staging secret from affecting production, reduces callback mix-ups, and makes independent revocation easy.

Similarly, if staging and production share an OP, still use separate client IDs/secrets and appropriate audiences/permissions; ideally separate realms/tenants when data and identity isolation is required.

## 8. Reverse Proxies, Ingress, and `{baseUrl}`

This is a common root cause behind errors like:

```text
Invalid redirect_uri:
http://spring-app:8080/login/oauth2/code/company
```

Even though the user actually visited:

```text
https://staging.app.example.test
```

### 8.1. Why Does Spring Boot Generate the Wrong URL?

The reverse proxy receives HTTPS on port 443 and forwards HTTP to the backend on port 8080. Looking only at the internal request, the app infers:

- Scheme = `http`.
- Host = `spring-app` or an internal service hostname.
- Port = `8080`.

When `{baseUrl}` expands from that information, the OP receives a `redirect_uri` that is absent from its allowlist or unreachable by the browser.

### 8.2. Letting Spring Process Forwarded Headers

With Spring Boot on the Servlet stack, you can use:

```yaml
server:
  forward-headers-strategy: framework
```

This lets the framework process forwarded headers such as `Forwarded` or `X-Forwarded-Proto`, `X-Forwarded-Host`, and related headers sent by a trusted proxy. Some environments can use the `native` strategy relying on the servlet container; the choice depends on infrastructure and how the container handles forwarded headers.

Example reverse proxy (Nginx) when TLS terminates at the proxy:

```nginx
location / {
    proxy_pass http://spring-app:8080;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port 443;
}
```

This example assumes the proxy serves HTTPS only on 443 and `spring-app:8080` is a reachable internal upstream. Real configurations must also account for ingress routes and policies.

**Security requirement:** the application must only trust forwarded headers coming from **a reverse proxy you control**. The proxy must strip or overwrite any client-supplied `Forwarded` / `X-Forwarded-*` headers, and the backend should not be directly reachable from the Internet. Trusting attacker-supplied headers lets an attacker make the app generate redirects pointing to unwanted hostnames.

### 8.3. When a Proxy Adds or Strips a Prefix

Suppose the public URL is:

```text
https://app.example.test/portal/login/oauth2/code/company
```

but the backend actually receives:

```text
/login/oauth2/code/company
```

because the proxy strips the `/portal` prefix. In that case, ensure the public prefix is forwarded and interpreted consistently (e.g., configuring `X-Forwarded-Prefix` where supported) **or configure the public Redirect URI explicitly**. The OP must permit the exact public URL containing `/portal`; the proxy must route requests back to the callback handled by Spring Security.

If the application itself configures:

```yaml
server:
  servlet:
    context-path: /portal
```

then callbacks served directly by the app typically sit under the `/portal` prefix. Do not add a context path on the backend and add the same prefix at the proxy without checking routing, as this easily produces `/portal/portal/...`.

**Rule:** Register at the OP the URL that **the browser actually sees**; simultaneously ensure that URL routes to the matching callback filter in the application.

## 9. When Should You Set an Explicit Redirect URI?

The `{baseUrl}` placeholder works well when the proxy forwards the app's public origin accurately. In complex infrastructures, you can use an environment variable holding **the entire callback URL**, avoiding reliance on inferring host/scheme from requests:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "${OIDC_REDIRECT_URI}"
```

Set per environment:

```text
# Local
OIDC_REDIRECT_URI=http://localhost:8080/login/oauth2/code/company

# Staging
OIDC_REDIRECT_URI=https://staging.app.example.test/login/oauth2/code/company

# Production
OIDC_REDIRECT_URI=https://app.example.test/login/oauth2/code/company
```

**Pros:** the callback is deterministic and easy to cross-check against the OP. **Trade-off:** whenever hostname/port/context path changes, you must update the environment variable, routing, and OP allowlist together. This option is very helpful when the public origin is fixed, ingress has multiple hops, or reliable forwarded headers are hard to guarantee.

Never build a callback `redirect_uri` dynamically from user-supplied request parameters. For OAuth/OIDC login, callbacks must originate from trusted configuration or strictly validated URIs to prevent **open redirects** or sending codes/tokens to an attacker's endpoint.

## 10. Customizing the Callback Path Beyond the Default

Some projects require a callback such as:

```text
https://app.example.test/auth/callback/company
```

In that case, you must update **both** the registration redirect URI **and** the endpoint where Spring Security listens for callbacks.

### 10.1. Changing Client Configuration

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
```

### 10.2. Changing the Endpoint in `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class CustomCallbackSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .redirectionEndpoint(redirection -> redirection
                    .baseUri("/auth/callback/*")))
            .build();
    }
}
```

### 10.3. Registering the New URI at the OP

```text
https://app.example.test/auth/callback/company
```

If you change `redirect-uri` **without** changing `redirectionEndpoint().baseUri(...)`, the OAuth2 Login filter will not intercept the callback. If you change only the filter without updating the registration at the OP, the OP will reject the authorize request because the Redirect URI is not in its allowlist.

The two URLs below serve **two distinct functions**:

```text
/oauth2/authorization/company  -> INITIATE login
/auth/callback/company         -> RECEIVE login CALLBACK
```

Changing the callback does not require changing the login initiation URL. `authorizationEndpoint().baseUri(...)` is an independent setting if you want to change the initiation endpoint.

## 11. Common Discrepancies and Diagnostics

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| OP returns `invalid_redirect_uri` or "redirect URI mismatch" | Scheme/host/port/path does not match allowlist, wrong client ID selected, missing prefix | Compare the actual `redirect_uri` parameter in the authorize request with URIs registered for that client |
| OP sees `http://spring-app:8080/...` instead of public HTTPS | Proxy is not forwarding headers, or Spring is not configured to use them | Fix proxy and `forward-headers-strategy`, or use an explicit URI |
| Callback hits 404 | Wrong path/context path, wrong ingress route, or mismatched custom filter | Compare public URL, proxy rewrites, and `redirectionEndpoint().baseUri` |
| Browser reaches callback but login fails with `invalid_state` | Lost session/cookie, callback hit another instance, altered state, restart mid-flow | Check cookies, session persistence, sticky sessions/distributed session, and hostname |
| Callback reaches app but Spring ignores code | `oauth2Login()` not enabled, callback path mismatch, security chain not applied | Check which filter chain handles the request and custom callback config |
| Local runs on 8081 while 8080 is registered | Port changed | Register port 8081 URI or move the app back to port 8080 |
| `localhost` works while `127.0.0.1` fails | Host mismatch or OP policy difference | Use one consistent hostname and register it accurately |
| Staging callback redirects back to production | Wrong environment client ID, secret, issuer, or redirect config | Separate configs/deployment secrets and check authorize parameters |
| Redirect loop between app and OP after login | Session not saved, Secure/SameSite cookie mismatch, domain switched mid-flow, route continuously requires login | Inspect `Set-Cookie`, callback, security context, and proxy |
| OIDC callback succeeds but OP rejects logout redirect | Confused login Redirect URI with post-logout Redirect URI | Configure a dedicated logout URI per supported protocol |

**Note on `invalid_state` errors:** by default in Servlet OAuth2 Login, pending authorization requests are stored in the HTTP session. If the callback from the OP does not send back the session cookie, or hits a replica lacking that session state, Spring Security cannot match the original request. In that case, fixing only the Redirect URI allowlist will not be enough.

### 11.1. Case: Public HTTPS, Yet Callback Is HTTP

The browser opens `https://staging.app.example.test`, and ingress forwards over HTTP. In the Network tab, the authorize request shows:

```text
redirect_uri=http%3A%2F%2Fspring-app%3A8080%2Flogin%2Foauth2%2Fcode%2Fcompany
```

This proves the URI was constructed from **the internal backend address**. Inspect proxy configuration, forwarded headers, and Spring Boot's header-handling strategy; you can also use an explicit `OIDC_REDIRECT_URI` if the public origin is fixed.

### 11.2. Case: URI Is Right, Yet Callback Fails with `invalid_state`

The Authorization Server returns:

```text
https://app.example.test/login/oauth2/code/company?code=...&state=...
```

but Spring Security cannot find the original authorization request. When this happens:

1. Check session cookies on the outgoing redirect to the OP and the incoming callback to the app.
2. Confirm the callback returns to **the exact same origin/session** rather than switching from `www` to non-`www` or HTTPS to HTTP.
3. If multiple replicas exist, verify shared sessions or consistent routing; do not rely on single-pod in-memory sessions when callbacks can land on another pod.
4. For `SameSite` cookies, check how the OP redirects. OAuth2 code flows returning via top-level GET usually work with `Lax`; POST/cross-site callbacks have different cookie rules and require evaluating CSRF risk.
5. Verify the `state` parameter is returned intact by the OP without being rewritten or truncated.

Do not "fix" `invalid_state` by disabling `state` validation.

### 11.3. Case: Custom Callback Path Returns 404

You configured:

```yaml
redirect-uri: "{baseUrl}/signin/callback/{registrationId}"
```

but forgot to update `.oauth2Login(...redirectionEndpoint...)`. When the callback arrives at `/signin/callback/company`, the filter is still listening on `/login/oauth2/code/*`. Update both the callback filter base URI and the OP's allowlist to match.

## 12. How to Verify Before Releasing an Environment

You do not need to print or store authorization codes, tokens, or secrets to verify that redirects are configured properly. You can inspect **the authorize URL** before login even completes.

### 12.1. Browser Network Inspection

1. Open the app at the environment's expected public origin.
2. Navigate to `/oauth2/authorization/company`.
3. In Developer Tools → Network, locate the redirect response going to the OP's authorization endpoint.
4. Decode the `redirect_uri` query parameter in the authorize URL; compare the full scheme, host, port, and path against the OP allowlist for that client ID.
5. Log in with a test account and confirm the callback returns to the expected domain and establishes a session.
6. Issue a subsequent authenticated request to confirm the cookie/session persists.

**Never copy full URLs containing authorization codes or tokens into shared tickets or logs.** When reporting issues, keep only the callback path, host, error type, and non-sensitive metadata.

### 12.2. Checking with an Environment Matrix

| Check | Local | Staging | Production |
| --- | :---: | :---: | :---: |
| App opened at expected public origin | ✓ | ✓ | ✓ |
| OP has callback URI with exact scheme/host/port/path | ✓ | ✓ | ✓ |
| `client-id` belongs to the right environment | ✓ | ✓ | ✓ |
| Authorize request emits the right `redirect_uri` | ✓ | ✓ | ✓ |
| Callback routes to the OAuth2 Login filter | ✓ | ✓ | ✓ |
| `state` and session are restored properly | ✓ | ✓ | ✓ |
| Trusted forwarded headers / explicit URI | Per topology | ✓ | ✓ |
| HTTPS and cookies match public origin | Per local setup | ✓ | ✓ |

This table is a practical guide for whoever configures environments; specific choices must fit your topology and OP policies.

## 13. Security Principles When Registering Redirect URIs

### 13.1. Register Specific URIs; Avoid Broad Wildcards

An allowlist entry like:

```text
https://*.example.test/*
```

if permitted by the OP, can dangerously expand the destinations allowed to receive authorization responses. Prefer exact entries:

```text
https://app.example.test/login/oauth2/code/company
```

Never allow uncontrolled hostnames or arbitrary paths to receive codes. If an OP supports redirect patterns, evaluate its exact rules carefully; **never treat wildcards as a safe default**.

### 13.2. Enforce HTTPS for Staging/Production

Authorization codes are returned via browser redirects. HTTPS protects the channel from eavesdropping and tampering. `http://localhost` is a local development exception per OP policy; never use public HTTP in production.

### 13.3. Never Build Callbacks from User-Controlled Parameters

Avoid logic like:

```text
redirect_uri = request.queryParameter("returnUrl")
```

because if an attacker controls `returnUrl`, the app could ask the OP to send the code to an unintended destination. If the app needs to return users to a specific page after login, use `SavedRequest` or a success handler with proper target URL validation rather than turning the destination page into the OAuth Redirect URI.

### 13.4. Keep `state`, OIDC `nonce`, and PKCE Enabled

- **`state`** binds the authorization response to the original request, defending against CSRF and login injection.
- **OIDC `nonce`**, when used, binds the ID token to the corresponding authentication session.
- **PKCE** protects authorization code exchange with `code_verifier`, which is especially critical for public clients.

All of these are complementary protections; **an exact Redirect URI does not replace them**.

### 13.5. Protect Secrets, Cookies, and Sessions

- Never commit client secrets to Git; supply them via environment-specific secret management.
- Set `Secure` cookies over HTTPS, `HttpOnly` for sessions, and pick `SameSite` according to the login flow and CSRF policy.
- Avoid logging `Authorization` headers, token responses, or full callback query strings containing codes.
- In multi-replica environments, implement appropriate session persistence or routing.
- Accept forwarded headers only from trusted proxies/ingresses.

## 14. Comprehensive Practice Exercise

Suppose you have a Spring Boot application with `registrationId=company`, issued by a shared OP, deployed at three addresses:

```text
Local      http://localhost:8080
Staging    https://staging.app.example.test
Production https://app.example.test
```

**Requirement:** when clicking login, in every environment the OP returns the browser to the standard callback, and Spring Security processes the code and establishes a login session.

**Step 1 — Determine callbacks and register them at the OP:**

```text
Local:
  http://localhost:8080/login/oauth2/code/company

Staging:
  https://staging.app.example.test/login/oauth2/code/company

Production:
  https://app.example.test/login/oauth2/code/company
```

Create separate clients per environment and configure matching client IDs/secrets.

**Step 2 — Keep the same application configuration:**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
```

**Step 3 — Supply environment variables:** provide `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_ISSUER_URI` matching each deployment without hardcoding secrets.

**Step 4 — Configure proxies:** on staging/production, expose HTTPS publicly, safeguard forwarded headers, and configure `server.forward-headers-strategy` when needed. If ingress rewrites prefixes in complex ways, use an explicit `OIDC_REDIRECT_URI` as shown in section 9.

**Step 5 — Observe the authorization request:** confirm the `redirect_uri` parameter sent to the OP matches each environment's callback **exactly**. After authentication, the callback must be handled by Spring Security and the session must persist on subsequent requests.

### Self-Check Questions

**Question 1:** A production app runs in a container on port 8080, while users access it via `https://app.example.test`. Should `http://container-name:8080/login/oauth2/code/company` be registered at the OP?

> No. The callback address must be the public URL reachable by the browser, in this example `https://app.example.test/login/oauth2/code/company`. Backend port 8080 is an internal infrastructure detail.

**Question 2:** You changed `redirect-uri` to `{baseUrl}/custom/callback/{registrationId}` without updating `SecurityFilterChain`. What happens?

> The OP may successfully redirect to the new URL, but the default OAuth2 Login filter will not intercept callbacks there. You must configure `redirectionEndpoint().baseUri("/custom/callback/*")` and update the OP's allowlist.

**Question 3:** `http://localhost:8080/login/oauth2/code/company` is allowlisted, yet the app runs on `http://localhost:8081`. Can the allowlist stay as-is?

> Usually no. The port is part of the Redirect URI. Either move the app back to port 8080 or register a new callback on 8081 according to OP policy.

**Question 4:** Why might staging show `redirect_uri=http://spring-app:8080/...` even though the browser opened an HTTPS URL?

> Because the proxy terminates HTTPS and forwards HTTP to the backend, and Spring is not yet picking up the public scheme/host. Configure and trust forwarded headers properly, or use an explicit Redirect URI.

**Question 5:** The callback URL matches the allowlist, yet login still fails with missing `state`. Should you disable state validation?

> No. Check whether the callback shares the same session/cookie as the authorize request, plus multi-replica setup, hostname, cookie policy, and proxy routing. State validation is a critical OAuth/OIDC security defense.

---

## Remember

A working Redirect URI setup requires **three places to agree**: (1) the URL Spring Security sends in `redirect_uri`, (2) the URI allowlist for **the exact client ID** at the Authorization Server, and (3) the public route forwarding callbacks to **the right filter** in the application.

For the default callback, the practical formula is:

```text
{public-origin}{context-path}/login/oauth2/code/{registrationId}
```

Local typically uses `http://localhost:port`; staging and production use HTTPS and public hostnames. When deploying behind a proxy, process forwarded headers from a trusted source or configure an explicit Redirect URI per environment. When debugging, compare **the actual `redirect_uri` value in the authorize request** before modifying application code.
