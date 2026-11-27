# 8.13. Limiting Data, Sensitive Information, and URLs in Authorization Requests

In **Spring Security OAuth 2.0/OIDC Client**, initiating login usually begins with an **authorization request**: Spring constructs a URL to the identity provider's Authorization Endpoint and returns an HTTP redirect so the browser opens that URL. The request can include `client_id`, `redirect_uri`, `scope`, `state`, `nonce` (OIDC), `code_challenge` (PKCE), and application-customized parameters.

Because the authorization request passes through the **browser**, any data placed in the URL must be evaluated along two dimensions: **information security** and **technical limits on request URL length**. A sufficiently long URL can be rejected by a web server, reverse proxy, browser, or WAF. A URL containing sensitive data can appear in browsing history, logs, monitoring systems, support tools, or `Referer` headers depending on the environment.

The goal of this lesson is to understand which data belongs in an authorization request, which data must never be put into the URL, how to constrain size, and how Spring Security keeps the flow safe when applications must add custom parameters.

## 1. What Is an Authorization Request and Where Does It Travel?

With the Authorization Code Flow, Spring Security can start login via an internal endpoint:

```text
GET https://app.example.test/oauth2/authorization/company
```

Spring uses `ClientRegistration` to create an authorization request and redirects the browser to the IdP's Authorization Endpoint:

```http
HTTP/1.1 302 Found
Location: https://login.example.test/oauth2/authorize?response_type=code&client_id=web-client&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&scope=openid%20profile%20email&state=EXAMPLE_RANDOM_STATE&code_challenge=EXAMPLE_PKCE_CHALLENGE&code_challenge_method=S256
```

For OIDC, the request may also contain `nonce` and other OIDC parameters depending on the flow. The URL above is illustrative only; values prefixed with `EXAMPLE_` are not secure random strings suitable for real applications.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant C as Spring Security Client
    participant AS as Authorization Server / OP

    U->>B: Select sign in
    B->>C: GET /oauth2/authorization/company
    C->>C: Generate state, nonce/PKCE when applicable
    C->>C: Save authorization request for verification
    C-->>B: 302 Location: Authorization Endpoint?...
    B->>AS: GET /authorize?client_id=...&scope=...&state=...
    AS->>U: Authenticate, confirm permissions when needed
    AS-->>B: 302 to Redirect URI?code=...&state=...
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>C: Verify saved state/flow
    C->>AS: POST Token Endpoint with code and verifier if PKCE
    AS-->>C: Token response
    C->>C: Validate OIDC, create Authentication
```

Points to distinguish:

- **Authorization request URL** is sent over the browser's front channel. The query string is observable across many layers of the system.
- **Redirect URI** is the Client's callback, such as `https://app.example.test/login/oauth2/code/company`. This URL is included in the authorization request as the `redirect_uri` parameter.
- **Authorization response URL** is the callback URL after IdP processing, usually carrying `code` and `state`. It must also be protected against unredacted logging or uncontrolled forwarding.
- **Token request** is sent directly by Spring to the Token Endpoint over the back channel. `client_secret` and `code_verifier` (if used) belong on this channel and must never be put into browser URLs.

Not every piece of data appearing in an authorization URL is secret. However, **even a value not considered a secret may still need protection against unintended exposure**, such as `state`, `nonce`, or identity-related parameters.

## 2. Classifying Data Before Adding It to the Authorization URL

| Data / Parameter | Commonly Appears in Authorization Request? | Is It a Secret? | Rule |
|---|---|---|---|
| `response_type=code` | Yes | No | Specifies Authorization Code Flow |
| `client_id` | Yes | No | Client identifier, not the client secret |
| `redirect_uri` | Yes | Not a secret, but security-critical | Must match a callback allowed by the IdP |
| `scope` | Yes | Usually not | Request minimal scopes; scope names can still reveal access intent |
| `state` | Yes | Not an auth credential, but an anti-CSRF value | Must be random/unpredictable, verified at callback; never pack PII or secrets |
| `nonce` (OIDC) | Usually when applicable to flow | Not a secret token | Random value binding ID Token to request; never reuse |
| `code_challenge` | Yes when using PKCE | Not `code_verifier` | Use S256; challenge may travel on front channel |
| `code_challenge_method=S256` | Yes when using PKCE | No | Never downgrade to `plain` |
| `prompt`, `max_age`, `ui_locales` | Depends on OIDC needs | Usually not | Add only when supported by the provider |
| `login_hint` | Possible | May be **personal data** | Avoid or minimize use; weigh exposing email/username in URL |
| `claims` | Depends on OIDC/provider | May reveal sensitive requirements | Easily inflates URL; do not embed unnecessary personal data |
| `id_token_hint` | Certain OIDC flows | **Sensitive**, as it may be a real ID Token | Do not arbitrarily put in URL; use appropriate provider transmission and protection |
| `client_secret` | **No** | **Yes** | Never send in authorization URL; use only in appropriate Client authentication channel |
| `code_verifier` | **No** | **Yes / kept secret within flow** | Keep on Client, send at Token Endpoint |
| `access_token`, `refresh_token` | **No** in standard Authorization Code Flow | **Yes** | Never put in URLs or additional parameters |
| Passwords, OTPs, API keys, session cookies | **No** | **Yes** | Never put in query strings, fragments, or redirect payloads |
| Address, phone number, national ID | Should not | **PII** | Never put in authorization request unless truly required |

**PII** (*personally identifiable information*) is data that can relate to an individual, such as email addresses, phone numbers, physical addresses, or identification numbers. Not all PII is a secret, yet placing it in URLs can violate data-minimization principles and broaden exposure in logs.

An especially dangerous mistake is confusing **`client_id`** with **`client_secret`**. `client_id` usually must be sent in the authorization request; `client_secret` must never be exposed there. Similarly, `code_challenge` is sent in the authorization request, while `code_verifier` appears only when exchanging the authorization code for tokens.

## 3. URLs Are Not Safe Storage for Sensitive Data

HTTPS encrypts traffic **in transit over the network** between parties, yet it does not turn a URL into a secret vault. Depending on architecture, URLs can be recorded in:

- **Browser history and address bars**; users may copy/share links or send screenshots.
- **Reverse proxies, load balancers, gateways, WAFs**: access logs typically record the HTTP request target or path with query string.
- **Web servers/IdPs**: authorization endpoints may log request URLs for diagnostics.
- **APM, tracing, metrics, error monitoring**: tools automatically capture URLs and request attributes.
- **Browser extensions or shared machines**: URLs can be observed by any component with access.
- **`Referer` headers**: when a page navigates or loads resources, browsers may send source URL info depending on `Referrer-Policy` and browser rules.
- **Support tickets and bug reports**: users or staff may paste raw URLs into external systems.

### 3.1. Does HTTPS Protect the Query String in Transit?

Yes: over HTTPS, the path and query string are encrypted while traversing TLS between proper TLS endpoints. However, **TLS-terminating components**, such as your load balancer or reverse proxy, can see the entire request-target for routing or logging. The browser and destination server also see the URL.

Therefore the rule remains: **never send unnecessary secrets, tokens, or PII in URLs**, even over HTTPS.

### 3.2. Why Does `Referer` Matter?

Suppose after callback the app renders a page or redirects through a route carrying sensitive query parameters. If that route loads third-party resources, whether `Referer` is sent depends on the browser and policy.

Modern browsers generally restrict cross-origin `Referer` by default, yet you cannot rely on general defaults to claim a query string will never leak. Policies vary across browsers, server configs, applications, and subsequent redirects.

A stricter policy for login/callback handling pages or pages with sensitive URLs can be:

```http
Referrer-Policy: no-referrer
```

Or `strict-origin-when-cross-origin` where appropriate. These headers help limit leakage via `Referer`, yet **do not replace keeping secrets out of URLs in the first place**. Avoid embedding third-party content on sensitive callback pages.

### 3.3. What Does `Cache-Control` Solve?

For responses containing login info or personal data, appropriate cache headers can be used, such as:

```http
Cache-Control: no-store
```

However, `Cache-Control` governs response caching under HTTP cache rules; it **does not erase** URLs from all browser history, web server logs, or tracing systems. Never treat `no-store` as the sole defense against query-string leakage.

## 4. URL Size Limits: There Is No Single Universal Number

Browser-redirect authorization requests use URLs with query parameters. Adding many scopes, `claims` JSON, hints, or extension parameters makes the URL grow rapidly.

**There is no single URL length limit honored identically by every browser, proxy, gateway, and IdP.** Limits can be enforced at any hop; a URL might pass through browser A yet be rejected by load balancer B.

Practical reference points to understand:

- **RFC 9110** recommends HTTP implementations support request-lines of at least **8,000 octets** for HTTP/1.1. That is **no guarantee** every OAuth2 system accepts authorization URLs that long or passes every intermediary.
- Older docs often mention **2,048 characters** for URLs. That is not a universal OAuth2/OIDC limit and should not be treated as an absolute constant across all browsers.
- Web servers, reverse proxies, WAFs, or IdPs may enforce their own limits on request-target, headers, query parameter count, or total request size.
- Displayed **character count** does not equal **wire byte count**: URL encoding and Unicode can expand size significantly.

### 4.1. Distinguishing Bytes and Characters

Example:

```text
Before URL encoding:
login_hint=nguyễn@example.test

After URL encoding (illustrative):
login_hint=nguy%E1%BB%85n@example.test
```

Unicode characters encoded in UTF-8 and percent-encoded can take many more bytes than an ASCII character. Meanwhile, `:` and `/` in `redirect_uri` must also be URL-encoded when placed **inside a query parameter**.

Example:

```text
Original callback:
https://app.example.test/login/oauth2/code/company

Query value after encoding:
https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany
```

If you only count characters in `application.yml`, you will miss the final URL length after Spring expands templates and URL-encodes parameters.

### 4.2. Factors That Bloat Authorization URLs

| Component | Why Length Grows | How to Handle |
|---|---|---|
| `redirect_uri` | Callback with long host, port, context path; then percent-encoded | Use a simple, fixed callback aligned with IdP config |
| `scope` | Many long scopes, URI-style scopes | Request only needed scopes; consider staged authorization |
| `state` | App manually packs large JSON/base64 into state | Use a short, secure random state; store context server-side |
| `nonce` | Random string | Generate sufficient entropy; do not append extra data |
| `claims` | JSON describing many claims/essential requirements | Reduce requested claims; consider request objects/PAR if supported |
| `login_hint`, `ui_locales`, `acr_values` | Custom values | Send only when genuinely needed |
| Custom parameters | Duplicated or oversized serialized objects | Define a strictly bounded parameter list |
| `request` (JAR request object) | Signed/encrypted JWT can be quite long | Consider PAR or `request_uri` if supported by server |

### 4.3. Symptoms When Exceeding Limits

Errors depend on which component rejects the request:

- **HTTP 414 URI Too Long** at a reverse proxy or Authorization Server.
- **HTTP 400 Bad Request** when URL/query is rejected by the provider.
- **HTTP 431 Request Header Fields Too Large** if the issue is in headers—distinguish this from long URLs.
- URL blocked by a WAF, gateway, or browser; some environments show an error page the Spring app never sees.
- Provider reports `invalid_request` or vendor-specific error due to oversized/invalid parameters.

Do not attribute every `400` error to "URL too long": invalid scopes, mismatched redirect URIs, bad request-object signatures, or missing required parameters can also trigger errors.

### 4.4. How to Pinpoint the Bottleneck

1. Inspect the `Location` header returned by Spring when starting login (redacting sensitive values).
2. Determine the URL the browser actually sends to the Authorization Endpoint.
3. Compare the URL-encoded request-target size against browser/proxy/WAF/IdP limits.
4. Check the status code and **which system generated** the error: reverse proxy, WAF, or IdP.
5. Trim unnecessary optional parameters; if still too long, evaluate a back-channel authorization request mechanism such as **PAR** when supported by the provider.

Do not enforce an arbitrary "all authorization URLs must be under 2,048 characters" rule without checking your deployment topology. Still, establish a **conservative internal operational threshold** based on your real infrastructure chain and test the full flow.

## 5. `state`: Keep It Random, Minimal, and Free of User Data

`state` lets the Client link a callback to the initial authorization request, defending against login CSRF and session mix-ups. Spring Security handles generating, saving, and validating `state` for OAuth2 Login.

Proper `state` design uses an **unpredictable value** matched against Client-stored data:

```text
state = random opaque value
Session/server-side store:
  state -> authorization request + flow-specific context
```

Never replace `state` with JSON containing full context:

```json
{
  "email": "user@example.test",
  "phone": "+84901234567",
  "address": "Sample address",
  "next": "https://external.example.test/landing"
}
```

If you Base64-encode this object and put it in `state`, the data is **not encrypted**: Base64 is just character encoding, and anyone holding the URL can decode it. Even signing it to prevent tampering **does not hide the contents**. Beyond privacy concerns, JSON/Base64 bloats URL length.

### 5.1. What If You Need to Remember the Post-Login Page?

In a session-based Spring MVC application, use Spring Security's **`RequestCache` / saved request** to remember which page the user was visiting before login. This is separate from `AuthorizationRequestRepository`, which stores the authorization request and `state`.

Example:

```text
User visits /orders/123?tab=history
    -> Spring saves request /orders/123?tab=history
    -> Browser redirects to IdP with random state
    -> Valid callback, login succeeds
    -> Success handler returns user to saved request
```

If the app needs custom workflow context, store that context **server-side** under a short-lived opaque key bound to the session or auth flow. Never put sensitive details into `state`, `redirect_uri`, or custom query parameters.

### 5.2. Do Not Customize `state` Unnecessarily

Some developers want to set `state=tenantId|returnUrl` for convenient routing. Customizing `state` without matching storage and verification can cause Spring to reject callbacks or introduce CSRF vulnerabilities. When customizing authorization requests, leave Spring's `state` generation and checking intact and add only provider-permitted parameters under clear policy.

## 6. `nonce` and PKCE: What Can and Cannot Go on the URL

### 6.1. OIDC `nonce`

OIDC uses `nonce` to bind an ID Token to an authentication request in applicable flows/contexts. `nonce` must be randomly generated and properly verified when receiving tokens. It may appear in the authorization URL per protocol, yet must never embed PII or use fixed strings.

Never use `nonce` as an arbitrary state store in place of sessions.

### 6.2. PKCE: Challenge on Front Channel, Verifier on Back Channel

PKCE generates a random `code_verifier` and computes:

```text
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
```

Values travel in two steps:

| Step | Values Present | Channel |
|---|---|---|
| Authorization Endpoint | `code_challenge`, `code_challenge_method=S256` | Browser / front channel |
| Token Endpoint | `code_verifier` | Direct connection to token endpoint / back channel |

With `S256`, `code_challenge` does not practically reveal the verifier when the verifier has strong entropy. Yet if a developer places `code_verifier` directly in the authorization URL, PKCE's protection is destroyed.

For confidential clients, also never send `client_secret` on the authorization URL. That secret belongs to the registered Client authentication method at the Token Endpoint.

### 6.3. Do Not Add Duplicate Security Parameters

Spring Security usually already manages `state` and OIDC/PKCE fields per flow. When writing a custom resolver, never append a second copy of `state`, `nonce`, `redirect_uri`, or `code_challenge` via manual query strings.

A URL with duplicate parameter names may be parsed differently by different components, causing errors or opening parameter-pollution vectors. Use Spring's builder/resolver APIs and ensure every parameter retains its single protocol meaning.

## 7. Redirect URI Is Not a Vehicle for Business Data

`redirect_uri` is the **Client's callback URL**. Default example:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
```

For a request arriving at `https://app.example.test`, it expands to:

```text
https://app.example.test/login/oauth2/code/company
```

The IdP must allow this exact URI. Never attach personal data or navigation targets to the callback:

```text
DO NOT:
https://app.example.test/login/oauth2/code/company?email=user@example.test
https://app.example.test/login/oauth2/code/company?returnTo=https://external.example.test
```

Modifying query parameters can break exact URI matching at the IdP, while also creating data-leakage or open-redirect risks.

### 7.1. Three URLs to Keep Distinct

| URL | Example | Purpose |
|---|---|---|
| Spring login initiation | `/oauth2/authorization/company` | Starts OAuth2 Login |
| OAuth2 Redirect URI | `/login/oauth2/code/company` | Receives authorization response containing `code` and `state` |
| Success target | `/dashboard` or saved request URL | Page user reaches after login succeeds |

To return users to the page they were viewing before login, use saved-request / success-handler mechanisms. **Never treat the callback URL as a place to pass `returnTo` or session data.**

### 7.2. Proxies and Host Header Poisoning Risk

The `{baseUrl}` placeholder relies on the public address recognized by Spring. Behind a reverse proxy, Spring may see an internal connection `http://service:8080` while the public URL is `https://app.example.test`.

When forwarded headers must be processed, Spring Boot config can include:

```yaml
server:
  forward-headers-strategy: framework
```

However, trust `Forwarded` or `X-Forwarded-*` headers only from **trusted reverse proxies**. If external clients can spoof host/scheme and trick Spring into expanding `{baseUrl}` to an attacker-controlled domain, the risk goes beyond a routine redirect bug.

Enforce canonical host rules, proxy allowlists, and exact Redirect URI registration at the IdP. When an environment has a single public origin, consider configuring a fixed Redirect URI per environment:

```yaml
redirect-uri: "https://app.example.test/login/oauth2/code/company"
```

This option must also be permitted by the IdP, and the app must actually handle that path.

## 8. Optional Parameters: Useful, but Choose Selectively

OIDC and providers often allow extra authorization request parameters. Examples:

| Parameter | Purpose | Risks or Limits |
|---|---|---|
| `prompt=login` | Asks provider to actively re-authenticate per its rules | May add extra login friction |
| `prompt=select_account` | Suggests showing an account picker if supported | Provider-dependent |
| `max_age=300` | Sets maximum authentication age in OIDC request | Requires understanding provider's `auth_time` emission and validation |
| `ui_locales=vi en` | Hints UI languages | Hint only; does not force provider support |
| `acr_values` | Requests authentication assurance level/context | Syntax and support vary by provider; does not automatically prove MFA |
| `login_hint=user@example.test` | Hints user account | **Exposes email/username in URL**; may be unnecessary |
| `domain_hint` or tenant hint | Hints tenant/provider | Vendor-specific; values must be validated |
| `claims` | Requests granular claims in OIDC | Can carry PII/sensitive context and bloat URL length |
| `resource`, `audience` | Indicates target resource/API if supported by server | Not a universal parameter across all Authorization Servers |

Avoid stuffing full user objects, internal permission lists, or session state into a "convenient" parameter. Even though `login_hint` is defined by OIDC, putting an email in a URL remains **a choice with privacy consequences**: justify it with a concrete purpose and check whether it can be omitted.

### 8.1. A Well-Scoped Request

OIDC Authorization Code Login example:

```text
response_type=code
client_id=portal-web
redirect_uri=https://app.example.test/login/oauth2/code/company
scope=openid profile email
state=<opaque, random>
nonce=<opaque, random, if applicable>
code_challenge=<S256 challenge, if applicable>
code_challenge_method=S256
```

No `password`, `client_secret`, `access_token`, `refresh_token`, or detailed profile payloads.

### 8.2. A Request to Avoid

```text
response_type=code
client_id=portal-web
client_secret=plaintext-secret
state=BASE64_OF_EMAIL_PHONE_ADDRESS
redirect_uri=https://app.example.test/login/oauth2/code/company?next=https://evil.example.test
login_hint=user@example.test
custom_user_profile=VERY_LARGE_JSON_OBJECT
code_verifier=SECRET_PKCE_VERIFIER
```

This example illustrates **insecure or improper** patterns; never test it with real secrets. It packs multiple flaws together: leaking Client secret and verifier, storing PII in `state`, appending an external redirect target to the callback, emailing in hint, and bloating the URL with oversized payloads.

## 9. Spring Boot Configuration: Keep Authorization Requests Simple

With Spring Boot using Spring Security OAuth2 Client and an OIDC Provider supporting discovery, a baseline setup is:

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
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company:
            issuer-uri: https://login.example.test/realms/company
```

The `example.test` domain and `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` variables are illustrative only. In a real application, configure your provider's actual issuer and Client registration, and register the matching callback at the IdP.

A common Servlet `SecurityFilterChain` configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Spring Security builds the authorization request from `ClientRegistration`. Application developers never need to manually concatenate `?client_id=...&scope=...&state=...` URLs in controllers. Using built-in filters and resolvers ensures protocol values are generated, stored, and verified consistently.

### 9.1. Minimal Scopes Shrink URLs and Data Exposure

If the application only needs identity authentication to create a session, you can start with just `openid` when supported by the provider. If displaying name/email is needed, add `profile` and `email` as required. Do not blindly add `address`, `phone`, or `offline_access` if unused.

Note: **reducing scopes does not change the Authorization Code Flow**. `scope` describes requested permissions/claims; `authorization-grant-type=authorization_code` defines how codes are obtained and exchanged for tokens.

### 9.2. Include Only Needed URIs

Keep `redirect-uri` as the concrete callback URL handled by Spring Security. Never smuggle another complete URL inside `scope`, `state`, or custom parameters to bypass registering callbacks with the provider.

Across multiple environments, use separate configurations for local/staging/production with their corresponding public URLs, and register only genuinely needed callbacks.

## 10. Customizing Authorization Requests Properly with Spring Security

Occasionally a provider needs a parameter such as `prompt=select_account`. In Spring Security Servlet, use `DefaultOAuth2AuthorizationRequestResolver` and its builder customizer rather than writing a custom controller to build URLs.

The example below adds only a fixed parameter with no PII:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;

@Configuration
public class OAuth2AuthorizationRequestConfig {

    @Bean
    OAuth2AuthorizationRequestResolver authorizationRequestResolver(
            ClientRegistrationRepository registrations) {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            registrations, "/oauth2/authorization"
        );

        resolver.setAuthorizationRequestCustomizer(builder ->
            builder.additionalParameters(parameters ->
                parameters.put("prompt", "select_account")
            )
        );

        return resolver;
    }
}
```

Wiring the resolver into `oauth2Login`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2AuthorizationRequestResolver requestResolver) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(requestResolver)
                )
            );

        return http.build();
    }
}
```

In practice, both example classes belong to the same application, and `SecurityConfig` uses the declared resolver bean. `prompt=select_account` should be sent only if the provider accepts it. With multiple distinct registrations, the customizer may need provider-specific rules rather than applying one parameter globally.

### 10.1. Why Choose `additionalParameters`?

- Spring continues managing core OAuth2 parameters such as `client_id`, `redirect_uri`, `state`, and authorization request attributes.
- No manual URL-encoding of individual characters.
- Gives one centralized place to constrain the list of custom parameters.
- Clearly separates **Spring-managed protocol parameters** from **provider-required extension parameters**.

Even so, **the builder does not automatically audit privacy risks of values you add**. If adding `login_hint`, `claims`, or parameters derived from HTTP requests, validating the values remains the application's responsibility.

### 10.2. Never Forward Unvalidated Request Data Straight into the URL

Risky example:

```java
// DO NOT DO THIS: user input placed directly on authorization URL.
String hint = request.getParameter("login_hint");
builder.additionalParameters(params -> params.put("login_hint", hint));
```

Risks include exposing PII, sending unexpected data to the IdP, exceeding URL limits, injecting control characters or malformed formats, or steering users into unintended tenant/account flows.

If the product has a legitimate need for a hint, enforce appropriate constraints:

1. The value must serve a clear purpose; check whether the hint can be omitted altogether.
2. Bound length and allowed characters/format.
3. Draw only from data the app has reason to trust and permission to share.
4. Never accept arbitrary target URLs or issuers to route to another provider.
5. Never log sensitive hints; document privacy impact if used.

### 10.3. Never Overwrite `state`, `nonce`, or PKCE via Extension Parameters

When applying a customizer, avoid altering flow-protection parameters. If PKCE `S256` is needed, use Spring Security's PKCE API on the same builder appropriate for your version—never generate `code_verifier` yourself and push it onto the front channel.

Custom parameters should be limited to permitted provider extensions. In apps with multiple `ClientRegistration` entries, the customizer must distinguish which provider supports which parameters.

## 11. When URLs Truly Get Too Long: Trim Requests or Use PAR

In some systems, authorization requests require fields beyond basic parameters—for instance, OIDC `claims` requesting many granular claims, `authorization_details` carrying structured payloads, or provider-mandated request objects.

Before adopting special mechanisms, **trim the request first**: drop unused scopes, remove PII, stop packing JSON into `state`, and omit unnecessary extension parameters. If the request remains large or demands higher security, consider these standards when supported by the Authorization Server.

### 11.1. Pushed Authorization Requests (PAR)

**PAR — RFC 9126** lets the Client push authorization request parameters directly to the Authorization Server over a back-channel endpoint, usually via HTTP POST. Upon receiving the request, the server returns a `request_uri` referencing the temporarily stored authorization request.

Illustrative flow:

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client backend
    participant AS as Authorization Server
    participant B as Browser

    C->>AS: POST Pushed Authorization Request Endpoint
    Note over C,AS: response_type, scope, redirect_uri, state, PKCE...
    AS-->>C: request_uri + expires_in
    C-->>B: 302 to /authorize?client_id=...&request_uri=...
    B->>AS: Authorization request with request_uri
    AS->>AS: Look up pushed request
    AS-->>B: 302 callback?code=...&state=...
```

Abbreviated format example:

```http
POST /oauth2/par HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic EXAMPLE_CLIENT_AUTHENTICATION

response_type=code&
client_id=web-client&
redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
scope=openid%20profile%20email&
state=EXAMPLE_RANDOM_STATE&
code_challenge=EXAMPLE_PKCE_CHALLENGE&
code_challenge_method=S256
```

The Authorization Server may respond:

```json
{
  "request_uri": "urn:ietf:params:oauth:request_uri:EXAMPLE_REFERENCE",
  "expires_in": 90
}
```

The browser is then redirected to a much shorter URL:

```text
https://login.example.test/oauth2/authorize?client_id=web-client&request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3AEXAMPLE_REFERENCE
```

Advantages:

- Reduces the number and exposure duration of parameters on front-channel URLs.
- Helps reduce PII leakage from complex authorization requests.
- Avoids browser and proxy URL length limits.
- Lets the Authorization Server authenticate the Client and validate the request early per PAR policy.

Limitations:

- **PAR must be supported by the Authorization Server.** Not every IdP exposes a PAR endpoint.
- `request_uri` is a server-issued reference with specific lifetime and bindings; never fabricate one yourself.
- PAR does not excuse the Client from checking `state`, PKCE, redirect URI, issuer, or ID Token.
- **Spring Security's PAR support and configuration depend on version**; consult documentation for your exact release on how to enable or integrate it. Never assume every default `oauth2Login` setup automatically turns GET authorization requests into PAR.

### 11.2. JWT-Secured Authorization Request (JAR)

**JAR — RFC 9101** packages authorization request parameters inside a JWT **request object** that can be signed and, depending on context, encrypted.

Two common modes depending on provider support:

- Passing the request object directly via the `request` parameter: signing protects integrity, though the JWT can be **very long**, and if signed without encryption the payload remains readable.
- Passing a reference via `request_uri` per server rules: shortens the URL if the object is hosted appropriately and only referenced on the front channel.

**JAR does not by itself solve URL length limits** if a large JWT is passed inline via `request` in the query string. Nor should JAR be confused with PAR: PAR **pushes parameters over the back channel**, whereas JAR **encapsulates/protects request contents**. Both can be combined when supported by the server.

### 11.3. Does the Authorization Endpoint Accept POST?

OAuth 2.0 allows the Authorization Endpoint to support standard request bindings, yet web-based Spring Security OAuth2 Login typically starts with a **browser redirect carrying the authorization URL**. You cannot simply swap a 302 redirect for an arbitrary POST and expect every provider and Spring callback to work seamlessly.

To shrink URLs or keep sensitive data off the front channel, prefer standard mechanisms **confirmed as supported by your provider** such as PAR, rather than crafting custom browser POST forms containing client secrets or tokens.

## 12. Managing Logs and Observing Flows Without Leaking Data

Investigating OAuth2 errors often requires knowing what request the Client sent. Yet enabling naive logging can accidentally capture the very data you need to protect.

### 12.1. What Is Safe to Log vs. What Must Be Avoided

| Safe to Log at High Level | Never Log Raw Values |
|---|---|
| Configured `registrationId` | `client_secret` |
| Trusted provider/issuer name | `access_token`, `refresh_token`, `id_token` |
| Fact that an authorization request was created | `code_verifier`, `authorization_code` |
| Parameter names and total URL length | `state`, `nonce`, session cookies |
| HTTP status and error category | Full URLs containing emails, tokens, or sensitive user IDs |
| Sanitized proxy/IdP error reason | Raw `Authorization` or `Set-Cookie` headers |
| Latency and safe internal correlation ID | Token response bodies |

A randomly generated operational correlation ID containing no personal data helps link logs across layers. **Never use `state` or tokens as log correlation IDs** just because they are already present.

### 12.2. URL Redaction at Proxies and APM

If access logs record entries like:

```text
GET /oauth2/authorize?client_id=...&state=...&login_hint=... HTTP/1.1
```

configure the logging pipeline to **omit query strings** or enforce redaction/allowlists at the very first tier receiving the request. Masking only in the final dashboard while shipping raw URLs down the pipeline may still fail data-protection requirements.

With Spring Client apps, the authorization request goes to the IdP, so the IdP's servers and proxies may also log the URL. Minimize data at the source; you cannot control every logging system on the provider side.

### 12.3. Never Share Unsanitized HAR/Network Exports

When troubleshooting logins, HAR files and Developer Tools screenshots can capture:

- Authorization URLs with `state`, `nonce`, and hints.
- Callback URLs containing authorization codes.
- Session cookies and sensitive headers.
- Token responses or account metadata.

Before sharing, strip or redact all such values. In documentation, use placeholders such as `EXAMPLE_STATE`, never real codes or tokens from live sessions.

## 13. Java Example: Monitoring URL Length Without Exposing Contents

To observe **technical size limits**, you can use an internal decorator/resolver or metrics at an appropriate layer to measure **authorization request URI length**. Report only total byte count or warn when exceeding an operational threshold—never print the full URL.

Simple utility example:

```java
import java.nio.charset.StandardCharsets;

public final class AuthorizationUrlMetrics {

    private AuthorizationUrlMetrics() {}

    public static int utf8Bytes(String authorizationRequestUri) {
        if (authorizationRequestUri == null) {
            return 0;
        }
        return authorizationRequestUri
            .getBytes(StandardCharsets.UTF_8)
            .length;
    }

    public static boolean exceedsOperationalLimit(
            String authorizationRequestUri,
            int maxBytes) {

        return utf8Bytes(authorizationRequestUri) > maxBytes;
    }
}
```

Usage:

```java
int actualSize = AuthorizationUrlMetrics.utf8Bytes(authorizationUri);

if (AuthorizationUrlMetrics.exceedsOperationalLimit(
        authorizationUri, configuredMaxBytes)) {
    // Do not log the full authorizationUri.
    logger.warn("Authorization request URI exceeded configured size limit");
}
```

Here `authorizationUri` and `logger` come from the application's integration/observability context; `configuredMaxBytes` is an internal threshold chosen by the team based on real infrastructure. Do not treat this snippet as a security filter to drop directly into `SecurityFilterChain`.

**Technical note:** `String#getBytes(UTF_8)` measures UTF-8 byte length of a Java string. To measure the exact percent-encoded request-target on the wire, measure the **final encoded URI used by Spring/browser** rather than a string before the resolver builds the URL. Logging only an integer byte count helps spot abnormal growth without collecting query values.

### 13.1. Avoid Fixing Length Errors by Dropping Required Parameters

If a URI is too long, never "truncate the string" by chopping trailing characters or dropping `state`, `nonce`, `redirect_uri`, or `code_challenge`. Doing so breaks OAuth2/OIDC constraints, causes failures, or weakens security.

The right fix is trimming optional parameters, requesting less data, or switching to a provider-supported mechanism like PAR.

## 14. Real-World Error Scenarios

| Symptom | Possible Cause | Appropriate Check |
|---|---|---|
| Browser reports URL too long | Authorization URL carries too many parameters/custom JSON | Measure final encoded URI; review `scope`, `claims`, `state` |
| IdP returns HTTP 414 | Proxy/IdP request-target limit hit | Identify which hop returned the error; compare size against configured limit |
| IdP returns `invalid_request` | Missing, invalid, or oversized parameter | Read sanitized provider message and inspect parameter list |
| Login fails with `invalid_scope` | Scope not permitted by provider | Remove excess scopes or request proper permissions; do not blame URL size |
| Callback fails with `state` mismatch | Custom code overwrote state or session was lost | Check resolver, `AuthorizationRequestRepository`, and session/cookies |
| Token Endpoint returns `invalid_grant` | Expired code, wrong PKCE verifier, or `redirect_uri` mismatch | Check flow/state/PKCE and callback; avoid logging codes |
| Login succeeds, yet email appears in IdP URL | Sent `login_hint` or PII inside `state` | Audit custom authorization parameters and remove unneeded data |
| Callback redirects to wrong host | Wrong `redirect_uri` or untrusted proxy headers | Check public host/scheme and URI allowlist at IdP |
| Signs of PII in APM | Pipeline captures raw URLs/queries | Update instrumentation policy and redact at source |
| Switched to JAR, yet URL grew even longer | Inline `request` parameter carries large JWT | Evaluate PAR or `request_uri` if supported by server |
| App works behind Proxy A, fails behind Proxy B | Different request-target/WAF limits across hops | Compare proxy, gateway, header, and error location |
| Multi-tab logins fail intermittently | Competing state/session/authorization requests or flawed custom handling | Review session and repository design; never manually tweak state |

A useful debugging approach is isolating issues by **stage**:

1. Fails before leaving Spring for the IdP: check URL construction, encoding, redirects, and browser/proxy limits.
2. Reaches the IdP but is rejected: check Client registration, scopes, redirect URI, optional parameters, and IdP policy.
3. IdP redirects to callback, yet Spring rejects it: check `state`, session, authorization request repository, and PKCE.
4. Code exchanges successfully, yet authentication fails: check ID Token issuer, audience, signature, and `nonce`—do not confuse with authorization URL length.
5. Login succeeds, yet sensitive data appears in logs: fix observability config and parameter sources without weakening the flow.

## 15. Practice Exercises

### Exercise 1: Identifying Data That Must Not Be Sent

A developer plans to add custom parameters:

```json
{
  "login_hint": "user@example.test",
  "client_secret": "secret-value",
  "code_verifier": "verifier-value",
  "prompt": "select_account"
}
```

**Question:** Which fields must never be placed in the authorization URL?

**Suggested answer:** `client_secret` and `code_verifier` must never be sent on the front channel. `login_hint` can be a valid OIDC parameter, yet contains PII; use it only if genuinely needed after risk review. `prompt=select_account` is an example low-risk extension parameter if supported by the provider.

### Exercise 2: Does Base64 Protect an Email in `state`?

An application builds:

```text
state = BASE64({"email":"user@example.test","next":"/reports"})
```

**Suggested answer:** No. Base64 does not encrypt contents. `state` also bloats and gets recorded in URLs/logs. Use a random `state`, keep context server-side, and use saved requests or success handlers for target URLs.

### Exercise 3: How Much Longer Does URL Encoding Make It?

Given callback `https://app.example.test/login/oauth2/code/company` and a long scope list. Compare the raw URI, the URI encoded as the `redirect_uri` query value, and the complete encoded authorization URL.

**Hint:** `:` and `/` in the callback normally become `%3A` and `%2F` inside a query parameter. Unicode values expand length even further. Never measure only the raw YAML string length.

### Exercise 4: Needing to Request Many Claims

A system requires complex `claims` JSON, causing the authorization URL to exceed WAF limits.

**Suggested answer:** First trim unnecessary claims and avoid sending PII; if the request genuinely needs many parameters, check whether the IdP supports PAR. Never truncate strings arbitrarily or drop `state`/PKCE to shorten the URI.

### Exercise 5: Choosing a Safe Debugging Method

An engineer asks for a full HAR capture including the callback `code`, session cookies, and token response for analysis.

**Suggested answer:** Provide only redacted data or a placeholder reproduction; you can share status codes, endpoint names, parameter names, total URL length, and error categories. Never share live codes, tokens, or cookies.

## 16. Implementation Principles to Remember

- **The Authorization URL is front-channel**: data can be observed in browsers, proxies, IdP logs, analytics, or support channels.
- **Never put secrets or tokens in URLs**: especially `client_secret`, `code_verifier`, `access_token`, `refresh_token`, passwords, and cookies.
- **Use random values for `state` and `nonce`, without PII**; never replace Spring's state with Base64/JSON containing session data.
- **`code_challenge` may travel on the front channel; `code_verifier` must be kept for token exchange**. Prefer PKCE `S256`.
- **`redirect_uri` is a specific IdP-permitted callback**; never embed business data or arbitrary external return URLs inside the callback.
- **Request only necessary scopes and parameters**. `login_hint`/`claims` can leak information or bloat URL size.
- **No single URL length limit applies universally**. Measure real encoded byte lengths across browsers, proxies, WAFs, and IdPs.
- **Use Spring Security resolver/customizer APIs** when the provider truly needs extra parameters; avoid manual URL concatenation or losing `state` and PKCE.
- **Minimize data at the source and redact logs**. HTTPS and `Referrer-Policy` are protective layers, not excuses to put secrets in URLs.
- **Consider PAR** when authorization requests are complex or URLs grow too long, provided both provider and Client version support it.

## 17. References

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization requests, `state`, `redirect_uri`, and token exchange.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier`, `code_challenge`, and `S256`.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): PAR endpoint and `request_uri`.
- [RFC 9101 — The OAuth 2.0 Authorization Framework: JWT-Secured Authorization Request (JAR)](https://www.rfc-editor.org/rfc/rfc9101): signed/encrypted request objects and request transmission.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): URIs, request semantics, and request-length notes.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): authorization requests, `nonce`, `claims`, `login_hint`, and OIDC parameters.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): `ClientRegistration`, flow, and callbacks in Servlet.
- [Spring Security Reference — Advanced OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): customizing authorization endpoint/resolver.
- [Spring Security API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html): customizer for adding authorization request parameters.

With Spring Security OAuth2/OIDC Client, a well-designed authorization request carries **enough protocol information for the IdP to authenticate and authorize**, without sending **secrets or unnecessary personal data through URLs**. Keeping requests lean, locking down redirect URIs, letting Spring manage flow-protection parameters, and extending only via standard mechanisms when genuinely needed form the foundation for reliable, maintainable login.
