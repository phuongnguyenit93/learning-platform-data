# Origin-Specific CORS and Restrictions on Protocol Endpoints

## 1. Context and Objectives

An OAuth 2.0/OpenID Connect Authorization Server typically serves multiple types of clients: browser-based web applications, backend-for-frontend (BFF) apps, service-to-service callers, mobile apps, and Resource Servers. When JavaScript running on one origin calls an API on another origin, the browser enforces **Cross-Origin Resource Sharing (CORS)** to decide whether JavaScript is allowed to read the response.

Example:

- The admin console runs at `https://console.example.com`.
- The Authorization Server runs at `https://auth.example.com`.
- The Inventory API runs at `https://inventory.example.com`.

These three URLs share the same registrable domain but have different origins because their hostnames differ. When JavaScript in the console calls the Token Endpoint or UserInfo endpoint, the browser may require CORS response headers. A backend service calling the same endpoint is not subject to browser CORS.

Configuring CORS for an Authorization Server requires answering three questions:

1. Which origins are allowed to call from a browser?
2. Which protocol endpoints actually need cross-origin access?
3. What methods, request headers, credentials, and response headers does each endpoint require?

After this lesson, you will be able to:

1. Distinguish between origin, site, and URL.
2. Explain the same-origin policy, CORS, and preflight requests.
3. Design environment-specific origin allow-lists.
4. Partition CORS policies per OAuth 2.0/OIDC endpoint.
5. Configure `CorsConfigurationSource` and `HttpSecurity.cors()` in Spring Security.
6. Order the CORS filter properly before authentication.
7. Distinguish CORS from authentication, authorization, CSRF, and redirect URI validation.
8. Manage credentialed requests, allowed headers, exposed headers, and preflight caching.
9. Avoid origin reflection, dangerous wildcards, and duplicate CORS configurations.
10. Test preflight requests, actual requests, negative origins, and individual endpoints.

**Version scope:** Examples reference Spring Authorization Server 1.5.8, Spring Security 6.x, and Spring Boot 3.x. Endpoint paths can be customized via `AuthorizationServerSettings`; keep CORS path mappings synchronized with actual endpoint configuration.

## 2. Origins and the Same-Origin Policy

### 2.1. What Comprises an Origin?

An origin is defined by the tuple:

- Scheme: `http` or `https`.
- Host: hostname or host address.
- Port: effective port of the URL.

Examples:

| URL | Compared to `https://console.example.com` | Same origin? |
| --- | --- | --- |
| `https://console.example.com/dashboard` | Same scheme, host, and default port. | Yes |
| `https://console.example.com:8443` | Different port. | No |
| `http://console.example.com` | Different scheme. | No |
| `https://auth.example.com` | Different host. | No |
| `https://console.example.net` | Different host. | No |

The path is not part of the origin. Two URLs with different paths but the same scheme, host, and port share the same origin.

### 2.2. Same-Origin Policy

The Same-Origin Policy (SOP) is a browser mechanism that restricts how a document or script interacts with resources from another origin. CORS is the mechanism by which a server declares which cross-origin responses the browser is allowed to share with JavaScript.

For example, JavaScript in the console calls:

~~~javascript
const response = await fetch("https://inventory.example.com/inventory", {
  headers: {
    Authorization: "Bearer " + accessToken
  }
});
~~~

The browser inspects the response CORS headers. If the origin is not allowed, JavaScript cannot read the response and the browser reports a CORS error.

### 2.3. CORS Is Not a Request Firewall

CORS primarily controls whether the browser shares responses with scripts. It does not authenticate callers and does not block all cross-origin requests:

- `curl`, backend services, and HTTP clients are not subject to browser CORS.
- Certain simple requests can be sent by the browser to the server even though JavaScript cannot read the response.
- Requests requiring preflight are blocked by the browser before sending the actual request if preflight is not approved.
- Attackers can still send requests using non-browser tools.

Therefore, CORS does not replace authentication, authorization, rate limiting, input validation, or CSRF protection.

## 3. CORS Requests and Preflight

### 3.1. Simple Requests

Certain requests meeting Fetch/CORS safelist criteria can be sent directly by the browser without a preflight. The server must still return appropriate `Access-Control-Allow-Origin` headers for JavaScript to read the response.

Do not rely on whether a request triggers a preflight to decide if the request is safe. CORS policy applies to both preflight and actual responses.

### 3.2. Preflight Requests

The browser sends an HTTP `OPTIONS` preflight when a request requires prior approval, such as non-safelisted methods, custom headers, or non-safelisted content types.

Example of JavaScript calling UserInfo with a Bearer token:

~~~http
OPTIONS /userinfo HTTP/1.1
Host: auth.example.com
Origin: https://console.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

The server responds if the origin, method, and header are allowed:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://console.example.com
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: Authorization
Access-Control-Max-Age: 600
Vary: Origin
~~~

Only then does the browser send the actual request. The exact status code may depend on the filter/server; what matters is that the response includes the required CORS headers.

### 3.3. Key Response Headers

| Header | Meaning |
| --- | --- |
| `Access-Control-Allow-Origin` | Origin allowed to read the response. |
| `Access-Control-Allow-Methods` | HTTP methods allowed for cross-origin requests. |
| `Access-Control-Allow-Headers` | Request headers the browser is allowed to send. |
| `Access-Control-Allow-Credentials` | Allows the browser to expose the response when the request uses credentials mode `include`. |
| `Access-Control-Expose-Headers` | Response headers JavaScript is allowed to read. |
| `Access-Control-Max-Age` | Duration the browser may cache the preflight result. |
| `Vary: Origin` | Signals caches that the response depends on the request `Origin`. |

`OPTIONS` is the method used to perform preflight; `Access-Control-Allow-Methods` lists the actual request methods allowed by the server, such as GET or POST.

## 4. Determining Which Endpoints Need CORS

Do not enable a single broad CORS policy across the entire Authorization Server. Each endpoint has a different usage pattern.

### 4.1. Authorization Endpoint

The Authorization Endpoint is normally accessed by the browser via top-level navigation or redirect in the Authorization Code Flow. This is not a typical `fetch()` call, so it usually does not need CORS.

Do not enable broad CORS on `/oauth2/authorize` just because a SPA is a client. A SPA can navigate the browser to the Authorization Endpoint, authenticate the user, and receive a redirect back to the callback URI.

### 4.2. Token Endpoint

The Token Endpoint may need CORS if a browser-based public client directly submits an authorization code to the Token Endpoint to exchange for tokens. A typical case is a SPA using Authorization Code + PKCE and performing the token exchange in the browser.

In a BFF architecture, the backend exchanges the authorization code and the browser calls only the same-origin BFF; the Token Endpoint is back-channel and usually needs no browser CORS.

If you allow a SPA to call the Token Endpoint:

- Allow only the exact origin of the registered SPA.
- Allow only the `POST` method.
- Allow only necessary request headers.
- Never embed a client secret in a SPA.
- Require Authorization Code + PKCE and an exact registered redirect URI.
- Never treat CORS as proof of a valid client.

### 4.3. Discovery and JWKS

OIDC Discovery and JWKS are normally read by clients/backends over HTTPS. If browser JavaScript or an in-browser library directly fetches metadata/JWKS from the Authorization Server, CORS `GET` may be required.

If only backends fetch discovery/JWKS, browsers do not need CORS for these endpoints. JWKS and metadata are typically public data; if allowing `*`, consider it only when the endpoints are genuinely public, do not use cookie credentials, and do not expose private tenant data.

### 4.4. UserInfo Endpoint

An OIDC relying party running in a browser may call UserInfo using a Bearer access token. If your architecture permits direct browser calls, configure CORS for exact frontend origins, GET/POST as supported by the endpoint, and the `Authorization` header.

If UserInfo is called through a BFF, only backend-to-backend access is needed; no browser CORS is required on this endpoint.

### 4.5. Revocation and Introspection

Token Revocation and Token Introspection are typically back-channel endpoints meant for confidential clients or Resource Servers. Do not open CORS to browsers merely for convenience.

These endpoints require client authentication and dedicated policies. CORS does not protect credentials and does not substitute for introspection/revocation permissions.

### 4.6. PAR, Device Authorization, Logout, and Dynamic Client Registration

Pushed Authorization Requests, Device Authorization, and Dynamic Client Registration are normally invoked by backends or clients holding protocol credentials. Browsers may navigate to a verification URI or an end-session/logout URI, but navigation does not imply CORS is needed.

Add CORS only when there is an actual browser fetch use case with defined origins and methods. Never enable wildcards across the entire protocol endpoint matcher.

### 4.7. Reference Endpoint Matrix

| Endpoint | Is browser fetch typically needed? | Recommended CORS policy |
| --- | --- | --- |
| `/oauth2/authorize` | No; uses navigation/redirect. | Disabled by default. |
| `/oauth2/token` | Possibly, for PKCE SPAs exchanging codes directly. | `POST` and exact SPA origins. |
| `/.well-known/openid-configuration` | Only when browsers perform discovery directly. | `GET` for required origins or disabled. |
| `/.well-known/oauth-authorization-server` | Only when browsers read metadata directly. | `GET` for required origins or disabled. |
| `/oauth2/jwks` | Only when browsers download JWKS directly. | `GET`/`HEAD` for required origins or public read policy. |
| `/userinfo` | Possibly, if called directly by a SPA. | `GET`/`POST` per endpoint, `Authorization` header, and exact origins. |
| `/oauth2/revoke` | Should not be called from browsers. | Disabled by default. |
| `/oauth2/introspect` | No; back-channel. | Disabled by default. |
| `/oauth2/par` | No; back-channel. | Disabled by default. |
| `/oauth2/device_authorization` | No; back-channel. | Disabled by default. |
| `/connect/register` | No; registration requires its own policy. | Disabled by default. |
| `/connect/logout` | Typically navigation/form flow. | Disabled by default. |

The paths above are common defaults; verify your application's endpoint settings before configuring.

## 5. Designing an Origin-Specific Allow-List

### 5.1. Exact Origins

An origin allow-list should specify full scheme, hostname, and port:

~~~text
https://console.example.com
https://portal.example.com
https://admin.example.com:8443
~~~

The following values are not equivalent:

~~~text
http://console.example.com
https://console.example.com:8443
https://console.example.net
~~~

Do not include a path or trailing slash in an origin. An origin is `scheme + host + port`, not a full page URL.

### 5.2. Never Reflect Arbitrary Origins

A dangerous misconfiguration is reading the request `Origin` and echoing that exact value back in `Access-Control-Allow-Origin` without checking an allow-list. This can allow any website to read responses via JavaScript.

Never use logic such as:

~~~java
response.setHeader("Access-Control-Allow-Origin",
    request.getHeader("Origin"));
~~~

Compare the origin against a governed list. If it does not match, omit CORS headers and let the CORS processor reject the preflight/response according to policy.

### 5.3. Wildcards and Credentials

`Access-Control-Allow-Origin: *` is appropriate only for public resources that do not require browser credentials. When `allowCredentials=true` is enabled, you must not combine it with `allowedOrigins("*")`; browsers also reject wildcard origins on credentialed responses.

If cookie/session credentials are needed:

- Use exact origins.
- Enable `allowCredentials=true` only when genuinely needed.
- Never allow arbitrary origins.
- Pair with appropriate `Secure`, `HttpOnly`, and `SameSite` cookie attributes.
- Keep CSRF protection enabled for cookie/session endpoints.

### 5.4. allowedOriginPatterns

Spring supports origin patterns, but a broad pattern such as `https://*.example.com` can trust uncontrolled subdomains or subdomains vulnerable to takeover. Use patterns only when every hostname matching the pattern resides within the same trust boundary and is securely managed.

For Authorization Servers, exact origins are easier to review and create fewer vulnerabilities. Never use the `*` pattern as a quick fix for CORS errors.

### 5.5. The `null` Origin and `localhost`

Never allow the `null` origin in production without an explicitly evaluated use case. The `null` origin can come from sandboxed iframes, `file:` URLs, or opaque origin contexts.

Development environments may need `http://localhost:3000` or another port. Declare development origins explicitly in a development profile; never include `localhost` origins in the production allow-list.

### 5.6. CORS Origins Are Not Redirect URIs

These two lists serve different purposes:

- CORS origins determine which browser origins may read cross-origin responses.
- Redirect URIs determine where the Authorization Server is permitted to send authorization responses.

Allowing a SPA origin in CORS does not mean every callback URL on that origin is valid. The Authorization Server must still perform exact redirect URI matching per client registration, along with PKCE, `state`, and OIDC `nonce` where applicable.

## 6. Per-Endpoint CORS Configuration in Spring Framework

### 6.1. Creating a CorsConfigurationSource

Example defining separate policies for the Token Endpoint, metadata/JWKS, and UserInfo:

~~~java
@Bean
CorsConfigurationSource authorizationServerCorsConfigurationSource() {
    CorsConfiguration tokenCors = new CorsConfiguration();
    tokenCors.setAllowedOrigins(List.of(
        "https://console.example.com"
    ));
    tokenCors.setAllowedMethods(List.of("POST"));
    tokenCors.setAllowedHeaders(List.of("Content-Type"));
    tokenCors.setAllowCredentials(false);
    tokenCors.setMaxAge(600L);

    CorsConfiguration publicReadCors = new CorsConfiguration();
    publicReadCors.setAllowedOrigins(List.of(
        "https://console.example.com",
        "https://portal.example.com"
    ));
    publicReadCors.setAllowedMethods(List.of("GET", "HEAD"));
    publicReadCors.setAllowedHeaders(List.of("Accept"));
    publicReadCors.setExposedHeaders(List.of("ETag", "Cache-Control"));
    publicReadCors.setAllowCredentials(false);
    publicReadCors.setMaxAge(1800L);

    CorsConfiguration userInfoCors = new CorsConfiguration();
    userInfoCors.setAllowedOrigins(List.of(
        "https://console.example.com"
    ));
    userInfoCors.setAllowedMethods(List.of("GET", "POST"));
    userInfoCors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    userInfoCors.setExposedHeaders(List.of("WWW-Authenticate"));
    userInfoCors.setAllowCredentials(false);
    userInfoCors.setMaxAge(600L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/oauth2/token", tokenCors);
    source.registerCorsConfiguration(
        "/.well-known/openid-configuration", publicReadCors);
    source.registerCorsConfiguration(
        "/.well-known/oauth-authorization-server", publicReadCors);
    source.registerCorsConfiguration("/oauth2/jwks", publicReadCors);
    source.registerCorsConfiguration("/userinfo", userInfoCors);
    return source;
}
~~~

This is an illustrative policy. If the SPA does not call the Token Endpoint directly, remove the `/oauth2/token` mapping. If no browser fetches metadata/JWKS or calls UserInfo, omit the corresponding mappings.

### 6.2. Allowed Headers Must Match Actual Requests

In the example:

- The Token Endpoint allows `Content-Type` so browsers can send form bodies or requests requiring that header.
- Metadata/JWKS allows only `Accept`.
- UserInfo allows `Authorization` because the browser sends a Bearer token, plus `Content-Type` if POST is used.

Do not allow every header out of habit. If deploying DPoP, add the `DPoP` header only when the endpoint actually supports it and browser clients must send it. Custom headers must be allow-listed intentionally.

### 6.3. Allowed Methods Must Be Minimal

The Token Endpoint needs only `POST`. Metadata/JWKS typically needs only `GET` and optionally `HEAD`. UserInfo uses `GET` or `POST` as supported by the endpoint.

Do not add `PUT`, `PATCH`, or `DELETE` just because another API uses those methods. CORS methods must match the protocol endpoint being served.

### 6.4. Exposed Headers

JavaScript can read only a set of safelisted response headers by default. If the application needs to read `ETag`, `Cache-Control`, or `WWW-Authenticate`, declare them in `setExposedHeaders`.

Never expose internal headers or headers containing credentials. Access tokens in the Token Endpoint response body remain sensitive data; CORS allows JavaScript from that origin to read the body, so allow only trusted origins.

### 6.5. allowCredentials

`allowCredentials` controls whether the browser may expose the response when a request is made with credentials mode `include`, such as cookies or browser-managed HTTP authentication. It is not a toggle for sending a Bearer token in the `Authorization` header.

If JavaScript explicitly sets a Bearer token in `Authorization`, allow that header via `allowedHeaders`. Typically, a token endpoint for a PKCE SPA does not need cookie credentials, so `allowCredentials(false)` is the appropriate choice.

## 7. Integration with Spring Security and Spring Authorization Server

### 7.1. CORS Must Run Before Authentication

Preflight requests generally do not carry the session cookie or Bearer token of the actual request. If Spring Security enforces authentication before CORS runs, preflight requests may receive 401/403 even for valid origins.

Spring Security integrates CORS via `http.cors(...)`. When configured properly, the CORS filter handles preflight requests before the corresponding authentication/authorization filters.

### 7.2. Configuring the Authorization Server SecurityFilterChain

Example using Spring Authorization Server's endpoint matcher:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        CorsConfigurationSource authorizationServerCorsConfigurationSource)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .cors(cors -> cors.configurationSource(
            authorizationServerCorsConfigurationSource))
        .with(authorizationServerConfigurer, Customizer.withDefaults());

    return http.build();
}
~~~

The Authorization Server endpoint matcher routes protocol endpoints to this filter chain. `CorsConfigurationSource` further restricts origins/methods/headers per path; matching the chain does not mean every endpoint receives CORS.

The application still needs other beans and configuration such as authentication, JWK source, issuer, exception handling, and the chain for application endpoints.

### 7.3. Configuring Other Chains

If the same application hosts APIs or application endpoints in another `SecurityFilterChain`, that chain must configure CORS separately if cross-origin access is needed:

~~~java
http.cors(cors -> cors.configurationSource(apiCorsConfigurationSource));
~~~

CORS is integrated per security chain. Configuring CORS in the Authorization Server chain does not automatically configure CORS for another API chain or a separately deployed Resource Server service.

### 7.4. Never Use permitAll on OPTIONS as a Substitute

Never use `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` as a substitute for CORS configuration. That approach does not validate `Origin`, requested method, or requested headers.

The CORS processor must validate preflights and approve only when the policy matches. Regular non-preflight OPTIONS requests must still obey the endpoint's security policy.

### 7.5. Avoid Duplicate CORS Configurations

Designate a single component responsible for emitting CORS headers for each request:

- Spring Security `http.cors(...)`, or
- an explicitly designed CORS filter/edge gateway.

Do not let a CDN, reverse proxy, servlet filter, and Spring Security simultaneously append `Access-Control-Allow-Origin` under different policies. Duplicate allow-origin headers can cause browsers to reject responses or behave unpredictably.

## 8. CORS for Browser-Based OAuth Clients

### 8.1. SPAs Using Authorization Code + PKCE

A SPA can perform:

1. Generate `code_verifier` and `code_challenge`.
2. Navigate the browser to the Authorization Endpoint.
3. Have the user authenticate and grant consent if required.
4. Receive a redirect from the Authorization Server to the registered callback URI with an authorization code.
5. Send a POST to the Token Endpoint to exchange the code and verifier.
6. Call UserInfo or APIs using the access token.

In this flow:

- The Authorization Endpoint uses navigation and normally needs no CORS.
- The Token Endpoint needs CORS if the SPA calls it directly from the browser.
- UserInfo needs CORS if the SPA fetches it directly.
- Separate APIs need their own CORS policies if called directly by the browser.

If using a BFF, the browser calls only the BFF and the BFF calls the Token Endpoint/UserInfo/APIs over back-channel. This is often used to reduce exposure of access tokens in the JavaScript runtime.

### 8.2. No Client Secrets in SPAs

A SPA is a public client. Any client secret embedded in a JavaScript bundle is no longer secret and cannot prove confidential client identity.

Register SPAs with public-client authentication, use Authorization Code + PKCE, and enforce exact redirect URIs. CORS only determines which origins' browsers may read responses.

### 8.3. CORS Does Not Replace PKCE or State

CORS does not protect authorization codes from interception and does not prevent login CSRF. SPAs still require PKCE, `state`, and callback validation; OIDC requires `nonce` where applicable. Redirect URIs must be matched against client registration.

Never weaken PKCE requirements just because the Token Endpoint only allows the SPA's origin.

## 9. CORS, Cookie Credentials, and CSRF

### 9.1. Bearer Tokens and Cookie Sessions Differ

Browser fetch requests can send a Bearer token in the `Authorization` header. This case needs `Authorization` in allowed headers, not necessarily `allowCredentials(true)`.

If a request relies on a cookie session, the browser may need `credentials: "include"` and the server needs `Access-Control-Allow-Credentials: true` together with an exact allowed origin. Cookies are also governed by `Secure`, `HttpOnly`, `SameSite`, and domain/path attributes.

### 9.2. CORS Does Not Prevent CSRF

A malicious website can attempt to send requests to an endpoint using the user's cookies. CORS can prevent JavaScript from reading the response, but it does not guarantee the request will not be sent. For simple requests, the request can still reach the server even if the browser blocks JavaScript from reading the response.

Therefore:

- Keep CSRF protection enabled for endpoints using cookies/sessions.
- Never use CORS as a CSRF defense.
- Never enable credentialed CORS for untrusted origins.
- Separate stateless bearer-token APIs from browser session endpoints if the architecture warrants it.

### 9.3. Token Endpoint and Cookies

A Token Endpoint serving a PKCE SPA typically authenticates the public client via authorization code, redirect URI, and PKCE; it does not need to rely on the Authorization Server's session cookie in cross-origin fetches. Hence, do not enable `allowCredentials(true)` without a specific requirement.

If your design uses cookie credentials, separately evaluate CSRF, `SameSite`, the origin allow-list, and browser behavior; never enable it just to fix a preflight error.

## 10. Dynamic Origins and Multi-Tenancy

### 10.1. Tenant Frontend Origins

In a multi-tenant platform, each tenant may have its own frontend origin, such as:

- `https://acme.portal.example.com`
- `https://fabrikam.portal.example.com`
- `https://app.customer.example`

Never derive allowed origins solely from a tenant ID, `Host` header, or hostname suffix. Maintain a verified registry binding each tenant to its allowed frontend origins.

### 10.2. Dynamic CORS Policies

If dynamic configuration is required, `CorsConfigurationSource` can look up the allow-list by request `Origin` and return a policy only when the origin is registered and the tenant status permits it.

The logic must ensure:

- Origins are parsed/normalized per origin rules, not treated as arbitrary URLs.
- Exact matching on scheme, host, and port.
- Tenant/domain binding is verified and active.
- Unverified origins are never reflected.
- Caching is not excessively long when an origin is revoked.
- `Vary: Origin` is emitted so caches never serve one tenant's response to another tenant.

### 10.3. Subdomain Wildcards Do Not Replace a Registry

Allowing `https://*.portal.example.com` is safe only if every subdomain matching the pattern is controlled by the platform, tenants cannot create arbitrary subdomains, and there is no dangling DNS/subdomain takeover risk.

For custom domains, an exact origin registry is usually the better choice.

## 11. Reverse Proxies, CDNs, and Caching

### 11.1. Choose One Layer to Emit CORS Headers

If CORS is handled in Spring Security, the gateway/CDN should forward request and response headers consistently. If CORS is handled at the edge, do not let the application add a conflicting policy.

Document this decision explicitly in deployment configuration to avoid production-only issues.

### 11.2. The Vary Header

When responses vary by `Origin`, caches must be aware of it. `Vary: Origin` prevents shared caches from serving a response containing one origin's `Access-Control-Allow-Origin` to a different origin.

For preflight responses, consider `Vary` on `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` when caching at a proxy/CDN.

### 11.3. Preflight Caching

`Access-Control-Max-Age` allows browsers to cache preflight results. High values reduce `OPTIONS` requests, but policy changes can take longer to take effect in browsers.

Choose a TTL aligned with how frequently the allow-list changes. For sensitive endpoints, use a moderate duration and plan for origin revocation. Do not confuse preflight caching with access token caching or authorization caching.

### 11.4. TLS and Public URLs

CORS origins must be the public origins the browser actually calls, such as the Authorization Server's HTTPS domain. Reverse proxies must forward scheme/host accurately and forwarded headers must be trusted only from trusted proxies.

Never allow a spoofed `Origin` to control the published issuer, redirect URIs, or endpoint URLs.

## 12. Common Mistakes

### Mistake 1: Using Wildcards for All Endpoints

**Symptom:** Unrelated websites can read cross-origin responses from exposed endpoints.

**Cause:** Configuring `allowedOrigins("*")` server-wide.

**Resolution:** Use exact origin allow-lists and separate policies per endpoint.

### Mistake 2: Assuming CORS Authenticates Clients

**Symptom:** Backends or `curl` can still call the endpoint even though browsers block it via CORS.

**Cause:** Confusing browser policy with server-side authentication.

**Resolution:** Authenticate clients/tokens and authorize requests independently of CORS.

### Mistake 3: Preflight Returns 401

**Symptom:** Browser reports a CORS error before sending the actual request.

**Cause:** An authentication filter processes `OPTIONS` before CORS runs.

**Resolution:** Integrate `http.cors(...)` so CORS runs before authentication.

### Mistake 4: Allowing All Headers and Methods

**Symptom:** Policy is hard to audit and overly permissive beyond actual needs.

**Cause:** Using wildcard headers and methods.

**Resolution:** Explicitly declare `POST`, `GET`, `Authorization`, and `Content-Type` per endpoint.

### Mistake 5: Using allowCredentials with a Wildcard Origin

**Symptom:** Framework rejects the configuration or browsers refuse to expose the response.

**Cause:** Combining `Access-Control-Allow-Credentials: true` with `Access-Control-Allow-Origin: *`.

**Resolution:** Use exact origins and enable credentials only when required.

### Mistake 6: Assuming the Authorization Header Requires allowCredentials

**Symptom:** Enabling unnecessary cookie credentials just to send a Bearer token.

**Cause:** Confusing allowed headers with Fetch credentials mode.

**Resolution:** Allow `Authorization` in `allowedHeaders`; keep `allowCredentials(false)` when not sending cookies/browser credentials.

### Mistake 7: Enabling CORS on the Authorization Endpoint

**Symptom:** A single broad policy is applied across all protocol endpoints.

**Cause:** Confusing browser navigation with fetch/XHR.

**Resolution:** Do not enable CORS for authorization navigations without a specific use case.

### Mistake 8: Sharing One List for CORS Origins and Redirect URIs

**Symptom:** Invalid callback URLs or overly broad trust in frontend origins.

**Cause:** Mixing two distinct configuration sets.

**Resolution:** Manage CORS origins and redirect URIs separately.

### Mistake 9: Both Gateway and Application Add CORS Headers

**Symptom:** Responses contain multiple `Access-Control-Allow-Origin` headers.

**Cause:** Configuring CORS at multiple layers.

**Resolution:** Designate a single layer to own CORS responses for each route.

### Mistake 10: Revoking an Origin While Caches Still Permit It

**Symptom:** Browsers continue using cached preflight results for some time.

**Cause:** `Access-Control-Max-Age` set too long.

**Resolution:** Choose an appropriate TTL and understand that policy changes do not immediately clear every browser's preflight cache.

## 13. Test Matrix

| Case | Expected result |
| --- | --- |
| Exact SPA origin calls Token Endpoint POST | CORS headers match allow-list. |
| Origin not in allow-list | No valid allow-origin; preflight rejected. |
| Valid origin but PUT method | Preflight rejected. |
| Valid origin but disallowed custom header | Preflight rejected. |
| Valid origin, UserInfo GET with `Authorization` | Preflight and actual request succeed properly. |
| Valid origin, credentials mode `include` while policy is `false` | Browser does not expose credentialed response. |
| Wildcard origin with `allowCredentials` true | Invalid configuration / rejected by browser. |
| Authorization Endpoint top-level navigation | Works via redirect without depending on CORS. |
| Revocation/introspection from browser | No CORS allow-list; back-channel still requires authentication. |
| `OPTIONS` preflight without session | CORS filter handles before authentication. |
| Non-preflight `OPTIONS` request | Still subject to endpoint security policy. |
| `Origin: null` | Rejected per production policy. |
| Wrong scheme or port | Rejected as a different origin. |
| Revoked tenant origin | No longer CORS-allowed after policy/cache update. |
| Response served via CDN | `Vary` and allow-origin are not cross-cached across tenants/origins. |
| Request via `curl` | Can be sent despite no CORS; authentication/authorization still enforced. |

## 14. Testing with MockMvc

Example preflight test:

~~~java
mockMvc.perform(options("/oauth2/token")
        .header("Origin", "https://console.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers", "content-type"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Access-Control-Allow-Origin",
        "https://console.example.com"))
    .andExpect(header().string(
        "Access-Control-Allow-Methods",
        org.hamcrest.Matchers.containsString("POST")));
~~~

Negative origin test:

~~~java
mockMvc.perform(options("/oauth2/token")
        .header("Origin", "https://attacker.example")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isForbidden());
~~~

The exact status code may depend on filter configuration and Spring version; what matters is that the disallowed origin never receives a valid `Access-Control-Allow-Origin`. Add actual-request tests with valid and invalid origins, as well as tests for each mapped path.

Do not test only preflights. Confirm that actual request responses also include CORS headers so browsers can read the body, including 4xx error responses from endpoints.

## 15. Production Checklist

| Item | Condition to verify |
| --- | --- |
| Origin model | Are exact scheme, host, and port specified? |
| Allow-list | No origin reflection and no broad wildcards? |
| Endpoint scope | Only endpoints with browser fetch use cases exposed? |
| Authorization endpoint | Uses navigation/redirect, without arbitrary CORS enabled? |
| Token endpoint | Only exact SPA origins, `POST`, and public-client PKCE if browser exchanges? |
| Discovery/JWKS | `GET` enabled only if browsers must fetch directly? |
| UserInfo | Exact origins and `Authorization` header per use case? |
| Back-channel endpoints | Browser CORS disabled on revocation/introspection/PAR? |
| Methods | Only methods supported by each endpoint? |
| Headers | Only necessary `Content-Type`/`Authorization`/custom headers? |
| Credentials | `allowCredentials` enabled only when cookies/browser credentials are required? |
| CSRF | Cookie/session endpoints keep CSRF protection enabled? |
| Filter order | CORS handles preflight before authentication? |
| Multiple chains | Each chain needing CORS configured separately? |
| Proxy/CDN | Only one layer emits CORS headers and caches with `Vary`? |
| Preflight TTL | `Max-Age` aligned with policy revocation needs? |
| Tenant origins | Dynamic origins looked up from a verified registry? |
| Logging | No tokens/secrets or sensitive data logged? |
| Tests | Positive, negative, preflight, and actual-request tests in place? |

## 16. Hands-On Exercise

A system has:

- An admin SPA at `https://console.example.com`.
- An Authorization Server at `https://auth.example.com`.
- An Inventory API at `https://inventory.example.com`.
- A BFF at `https://bff.example.com`.

The SPA can choose one of two architectures: call the Token Endpoint directly using Authorization Code + PKCE, or use the BFF to exchange codes on the back-channel. The SPA can also call UserInfo directly or via the BFF. Revocation and introspection are called only by the backend.

Complete the following:

1. Draw the request flows for direct SPA and BFF.
2. Build a table showing which endpoints need CORS in each architecture.
3. Configure environment-specific exact origin allow-lists.
4. Write a `CorsConfigurationSource` with separate policies for token, discovery/JWKS, and UserInfo if needed.
5. Integrate CORS into the Authorization Server `SecurityFilterChain`.
6. Configure separate CORS for the API chain if the SPA calls the Inventory API directly.
7. Keep `allowCredentials(false)` for bearer-token flows without cookies.
8. Test preflight, actual requests, wrong origins, wrong methods, and wrong headers.
9. Verify `Vary` when responses are cached through a CDN.
10. Demonstrate why revocation/introspection do not need browser CORS.

**Completion criteria:** each endpoint has a use-case-driven policy; origins are matched exactly; preflights are handled before authentication; CORS does not replace PKCE, authentication, authorization, or CSRF; no wildcard/credentialed-origin reflection exists.

## 17. References

- [Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol): origins, preflight, credentials, and CORS response headers.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/docs/Web/HTTP/CORS): browser behavior, preflight, and response headers.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): integrating the CORS filter with Spring Security.
- [Spring Framework — CORS Support](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `CorsConfiguration`, `CorsConfigurationSource`, and CORS processing.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): endpoints and Authorization Server configuration.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization endpoint, token endpoint, client registration semantics, and redirect URIs.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): protecting OAuth clients, redirect flows, and token usage.
- [OWASP — Cross-Origin Resource Sharing Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Origin_Resource_Sharing_Cheat_Sheet.html): origin controls and secure CORS configuration.
