# Configuring Security Headers and Protecting Login and Consent UIs

## Objectives

After this lesson, you will be able to:

- Explain the role of HTTP security response headers in an OAuth 2.0/OpenID Connect Authorization Server.
- Identify headers enabled by default in Spring Security alongside application-specific policies such as Content Security Policy (CSP), Referrer Policy, and Permissions Policy.
- Apply a consistent header policy across both the protocol endpoint filter chain and the web UI filter chain.
- Protect the login page, consent page, session cookies, and sensitive data rendered in the browser.
- Distinguish Spring Security's CSRF token from the `state` parameter used by Spring Authorization Server in the consent flow.
- Verify headers, CSP policies, and login/consent behavior using MockMvc, browsers, and `curl`.

## 1. Why Must an Authorization Server Protect Its Web UI?

An Authorization Server typically has two categories of surfaces to protect. The first consists of protocol endpoints such as the authorization endpoint, token endpoint, revocation endpoint, and OpenID Connect endpoints. The second consists of user-facing UIs, usually including the login page, consent page, error pages, and logout pages.

The login page accepts authentication credentials and creates a login session. The consent page displays which permissions an application is requesting and lets the user decide whether to grant them. If these pages are framed inside a malicious site, injected with scripts, cached on a shared machine, or leak information via auxiliary requests, attackers can steal credentials, trick user interactions, or cause unintended permission grants.

HTTP security headers instruct the browser on how to handle content. They add a browser defense layer, but do not replace authentication, authorization, input validation, output encoding, CSRF protection, or proper OAuth 2.0/OIDC configuration. For example, CSP can restrict which script sources are permitted to run, yet the application must still encode user-supplied data to prevent XSS.

In Spring Security, headers are written to responses by `HeaderWriterFilter`. Header configuration belongs to each `SecurityFilterChain`; a request passes only through the first chain matching its request matcher. Therefore, configuring headers only in the UI chain may leave protocol endpoints handled by a higher-priority chain unprotected.

## 2. Key Security Headers

Spring Security enables several safe headers by default. On the Servlet stack, the default set includes:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
X-Frame-Options: DENY
X-XSS-Protection: 0
```

`Strict-Transport-Security` is added only to HTTPS responses. CSP, Referrer Policy, and Permissions Policy are not set automatically by Spring Security because appropriate policies depend on each application's content and functionality.

| Header | Purpose | Configuration guidance for an Authorization Server |
|---|---|---|
| `Cache-Control`, `Pragma`, `Expires` | Prevents browsers and intermediary caches from storing sensitive responses. | Keep defaults for login, consent, account pages, and responses containing personal data. |
| `X-Content-Type-Options: nosniff` | Prevents browsers from MIME-sniffing and misinterpreting content types. | Keep default; the server must return accurate `Content-Type` headers for HTML, CSS, JavaScript, and downloads. |
| `Strict-Transport-Security` | Remembers that the domain must be accessed over HTTPS. | Serve everything over HTTPS; enable `includeSubDomains` only when every relevant subdomain supports HTTPS. |
| `X-Frame-Options` | Restricts framing in `frame` or `iframe` elements to mitigate clickjacking. | Use `DENY` unless embedding is required. If same-origin framing is needed, evaluate `SAMEORIGIN` and align with CSP `frame-ancestors`. |
| `Content-Security-Policy` | Restricts sources for scripts, styles, images, frames, and form submissions. | Explicitly declare required sources; roll out `Report-Only` before enforcing. |
| `Referrer-Policy` | Restricts URL details sent in the `Referer` header. | Use `strict-origin-when-cross-origin`, or `no-referrer` for pages carrying sensitive query data. |
| `Permissions-Policy` | Disables browser features unneeded by the UI. | Disable camera, microphone, and geolocation on login/consent pages. |

### 2.1. Cache Control

Spring Security sends `no-store` and related cache directives by default so that after a user logs out, the next person clicking Back cannot view sensitive pages. This is especially valuable for login, consent, and account management pages.

Do not disable cache control across the entire application just to speed up page loads. For static assets like CSS, JavaScript, and images using versioned or content-hashed filenames, the application can apply a dedicated cache policy. Spring Security lets application-set cache headers override the default policy. Never place personal data, authorization codes, tokens, or consent details into cacheable static assets.

`no-cache` is not the same as `no-store`: `no-cache` allows storing the response while requiring revalidation before reuse; `no-store` forbids caching the response altogether. Also audit service workers and JavaScript-managed caches, as they do not necessarily obey HTTP cache headers.

### 2.2. HSTS and HTTPS

HSTS causes browsers to upgrade subsequent visits to HTTPS automatically after receiving the header over a valid HTTPS response. `max-age=31536000` equals one year. `includeSubDomains` extends the policy to all subdomains; enable it only when every subdomain already runs reliable TLS. `preload` is a broader operational commitment requiring eligibility for the HSTS preload list, so do not enable it merely to check off a sample configuration.

Spring Security emits HSTS only when the request is recognized as HTTPS. If TLS terminates at a reverse proxy or load balancer, the backend application must recognize the original scheme via forwarded headers from a trusted proxy. The proxy must strip client-supplied forwarded headers before setting canonical values. If the application always sees requests as HTTP, HSTS may be omitted even when users access HTTPS externally.

### 2.3. Clickjacking and CSP

`X-Frame-Options: DENY` blocks browsers from rendering the page inside frames. CSP provides the modern directive `frame-ancestors 'none'`; keep both policies consistent. If the UI genuinely needs embedding by a specific origin, declare that origin explicitly in `frame-ancestors` and re-evaluate `X-Frame-Options`. Never use `ALLOW-FROM`, as it is obsolete and lacks broad support.

CSP controls where the browser may load scripts, styles, images, fonts, connections, and frames. A baseline policy for login/consent pages might look like:

```http
Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'
```

Key directives:

- `default-src 'self'`: defaults resource types without dedicated directives to the current origin.
- `base-uri 'self'`: restricts allowed base URLs in `<base>` tags.
- `object-src 'none'`: blocks embedded plugins such as `<object>`/`<embed>`.
- `frame-ancestors 'none'`: forbids other origins from framing the page.
- `form-action 'self'`: allows forms to submit only to the same origin. This fits when login and consent are handled on the same Authorization Server.
- `script-src 'self'`: allows only same-origin scripts; blocks inline scripts and `eval`.

This is a starting policy, not a string to apply verbatim to every system. If the UI uses CDNs, external fonts, analytics, or inline scripts/styles, browsers may block those resources. Prefer moving scripts/styles into same-origin static files. If inline code is truly unavoidable, use a per-response random nonce or a hash of fixed content; avoid adding `'unsafe-inline'` or `'unsafe-eval'` just to silence CSP warnings.

Roll out with `Content-Security-Policy-Report-Only` first, collect violations in testing, fix any missing legitimate sources, and only then switch to enforcing `Content-Security-Policy`. CSP reduces the impact of some injection bugs, but does not replace output encoding and XSS controls.

## 3. Configuring Headers Across SecurityFilterChains

A typical Authorization Server configuration has at least two chains:

1. An `@Order(1)` chain using `securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())` for Spring Authorization Server protocol endpoints.
2. An `@Order(2)` chain handling the login page, consent page, logout, and remaining web requests.

`HeaderWriterFilter` belongs to each chain. Extract a shared helper method and invoke it in both chains to avoid policy divergence between login, consent, and protocol endpoint responses.

The example below uses Servlet APIs from Spring Security and Spring Authorization Server 1.5.x. If your project has migrated to Spring Security 7.x, Spring Authorization Server has been integrated into Spring Security; align with your project's dependency version and APIs.

```java
package com.example.authorizationserver.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer -> authorizationServer
                .oidc(Customizer.withDefaults())
                .authorizationEndpoint(endpoint -> endpoint
                    .consentPage("/oauth2/consent")
                )
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
            )
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
                )
            );

        configureSecurityHeaders(http);
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/css/**", "/images/**").permitAll()
                .requestMatchers("/oauth2/consent").authenticated()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .permitAll()
            );

        configureSecurityHeaders(http);
        return http.build();
    }

    private static void configureSecurityHeaders(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .frameOptions(frameOptions -> frameOptions.deny())
            .httpStrictTransportSecurity(hsts -> hsts
                .maxAgeInSeconds(31_536_000)
                .includeSubDomains(false)
            )
            .contentSecurityPolicy(csp -> csp.policyDirectives(
                "default-src 'self'; " +
                "base-uri 'self'; " +
                "object-src 'none'; " +
                "frame-ancestors 'none'; " +
                "form-action 'self'; " +
                "img-src 'self' data:; " +
                "style-src 'self'; " +
                "script-src 'self'"
            ))
            .referrerPolicy(referrer -> referrer.policy(
                ReferrerPolicyHeaderWriter.ReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN
            ))
            .permissionsPolicy(permissions -> permissions.policy(
                "camera=(), microphone=(), geolocation=()"
            ))
        );
    }
}
```

In this example:

- The first chain matches only endpoints registered by Spring Authorization Server. Headers are added to responses from those endpoints.
- The second chain handles `/login` and `/oauth2/consent`. The consent page requires an authenticated user; the login page and necessary UI assets are accessible before login.
- Both chains invoke `configureSecurityHeaders`, ensuring consistent policies across both areas.
- Default headers such as cache control and `X-Content-Type-Options` remain enabled. Never call `defaultsDisabled()` or `headers.disable()` without a plan to replace every default header completely.
- HSTS is configured for one year without extending to subdomains in the example. Switch `includeSubDomains(false)` to `true` only after verifying all subdomains support HTTPS.
- `frameOptions().deny()` and CSP `frame-ancestors 'none'` both forbid framing. If a product requires framing, redesign both policies together.
- `Permissions-Policy` disables camera, microphone, and geolocation. Re-enable only features the UI genuinely needs.

If the application has a third chain for APIs, actuator, or another area, evaluate and apply appropriate headers there too. `permitAll()` governs authorization only; it does not skip filters in the chain and does not add headers to requests outside that chain.

### 3.1. Switching to CSP Report-Only

During testing, adjust the CSP configuration to:

```java
.contentSecurityPolicy(csp -> csp
    .policyDirectives(
        "default-src 'self'; base-uri 'self'; object-src 'none'; " +
        "frame-ancestors 'none'; form-action 'self'; " +
        "img-src 'self' data:; style-src 'self'; script-src 'self'"
    )
    .reportOnly()
)
```

With `Report-Only`, the browser logs or sends violation reports without blocking resources. Monitor the console and reporting endpoint if configured, classify legitimate vs. unwanted sources, and only then enable enforcement. Never include sensitive data or tokens in custom report payloads.

## 4. Protecting the Login Page

### 4.1. Authorization and CSRF

The `GET /login` page must be accessible before login so users can initiate authentication. However, the `POST /login` endpoint must sit inside Spring Security's form login mechanism and be protected by a CSRF token. CSRF protection is enabled by default for state-changing requests in standard web configurations.

With Thymeleaf, a login form can be written as:

```html
<form th:action="@{/login}" method="post">
    <label for="username">Username</label>
    <input id="username" name="username" type="text"
           autocomplete="username" required>

    <label for="password">Password</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password" required>

    <button type="submit">Sign in</button>
</form>
```

Spring MVC integrates `RequestDataValueProcessor` to automatically inject the CSRF token into forms rendered via Spring MVC/Thymeleaf. Inspect the rendered HTML in the browser to confirm the hidden `_csrf` field is present. If a form is plain HTML or bypasses that integration, add the token manually:

```html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
```

Use only one token-injection mechanism to avoid duplicate hidden fields. Never disable CSRF across the entire application chain to fix a form error; locate the exact request matcher and configure a narrow exception only when clearly justified.

### 4.2. Content and Sessions

The login page should display a generic authentication error, such as "Invalid username or password," to avoid revealing which accounts exist. Use `autocomplete="username"` and `autocomplete="current-password"` to support password managers. Never write passwords, CSRF tokens, or session IDs into logs, URLs, or analytics.

Production session cookies need `Secure`, `HttpOnly`, and an appropriate `SameSite`. `Secure` instructs browsers to send cookies only over HTTPS; `HttpOnly` prevents JavaScript from reading cookies; `SameSite` restricts automatic cookie sending on certain cross-site requests. `SameSite=Lax` generally works well with common top-level OAuth/OIDC navigations. If deploying `response_mode=form_post`, SSO, or logout with special cross-site flows, test cookie behavior and use `SameSite=None; Secure` only when the flow truly requires it.

Example session cookie configuration in Spring Boot, placed in the production profile:

```yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
```

Do not enable `secure: true` in a local HTTP environment without HTTPS configured, as browsers will not send cookies over plain HTTP. Ensure Spring Security's session fixation protection remains active and the session ID rotates upon successful authentication per your session strategy.

## 5. Protecting the Consent Page

Consent is an authorization decision. Users need to know which application is requesting access, which scopes are requested, what data or actions correspond to each scope, and how their choices will be stored. A confusing consent screen can lead users to approve overly broad permissions even when technical controls function properly.

### 5.1. Spring Authorization Server Consent Flow

When enabling a custom consent page via `authorizationEndpoint(endpoint -> endpoint.consentPage("/oauth2/consent"))`, Spring Authorization Server redirects the browser there whenever an authorization request requires user consent. The consent page query string contains:

- `client_id`: identifier of the client requesting permissions.
- `scope`: space-delimited list of requested scopes.
- `state`: CSRF-protection token for the authorization flow generated by Spring Authorization Server.

The custom consent page must submit an `HTTP POST` form to the authorization endpoint configured in `AuthorizationServerSettings`. The form must return `client_id`, `state`, and the `scope` values approved by the user. The example below assumes the default authorization endpoint `/oauth2/authorize`.

Here, `state` is Spring Authorization Server's consent-flow token. It provides CSRF protection for the consent grant and must be round-tripped verbatim from the query string to the form POST. Never generate a new value, omit it, or replace it with Spring Security's `_csrf`. The two tokens serve two different mechanisms and flows.

Spring Authorization Server automatically configures a CSRF matcher to skip `CsrfFilter` checks on protocol endpoints matched by `getEndpointsMatcher()`. The authorization endpoint validates `state` per the authorization flow mechanism. The login page still runs through the application chain and still requires Spring Security's CSRF token. If you add custom POST endpoints outside Spring Authorization Server's matcher, they must have their own appropriate CSRF policies.

### 5.2. Rendering Client and Scope Details Safely

The controller handling `GET /oauth2/consent` should:

1. Read `client_id`, `scope`, and `state` from the framework-parsed request.
2. Look up the client in `RegisteredClientRepository` by `client_id` to obtain the registered application name and metadata. Never trust an arbitrary application name or logo submitted by the browser.
3. Map each scope to a clear description managed by the Authorization Server. Never render raw HTML supplied by a client or user.
4. Pass `client_id`, `state`, and the scope list to the model so the template renders them with auto-escaping.
5. Require explicit user selection of scopes to grant. Never pre-check sensitive scopes if product design requires affirmative action.

Example controller showing how to look up client details and populate the model:

```java
@Controller
public class ConsentController {

    private final RegisteredClientRepository registeredClientRepository;

    public ConsentController(RegisteredClientRepository registeredClientRepository) {
        this.registeredClientRepository = registeredClientRepository;
    }

    @GetMapping("/oauth2/consent")
    public String consent(
            @RequestParam("client_id") String clientId,
            @RequestParam(value = "scope", required = false) String requestedScopes,
            @RequestParam("state") String state,
            Model model) {

        RegisteredClient client = registeredClientRepository.findByClientId(clientId);
        if (client == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        String displayName = client.getClientName() != null
                ? client.getClientName()
                : client.getClientId();

        List<String> scopes = requestedScopes == null || requestedScopes.isBlank()
                ? List.of()
                : Arrays.stream(requestedScopes.split("\\s+"))
                    .filter(scope -> !scope.isBlank())
                    .toList();

        model.addAttribute("clientId", client.getClientId());
        model.addAttribute("clientName", displayName);
        model.addAttribute("state", state);
        model.addAttribute("scopes", scopes);
        return "consent";
    }
}
```

Required imports for this controller example include `java.util.Arrays`, `java.util.List`, `org.springframework.security.oauth2.server.authorization.client.RegisteredClient`, `RegisteredClientRepository`, `org.springframework.stereotype.Controller`, `org.springframework.ui.Model`, `org.springframework.web.bind.annotation.GetMapping`, `RequestParam`, `org.springframework.web.server.ResponseStatusException`, and `org.springframework.http.HttpStatus`. Add these imports in the actual class.

The `consent.html` template can build the form as follows:

```html
<h1>Allow application access?</h1>
<p>Application: <strong th:text="${clientName}">Application name</strong></p>
<p>The application requests the following permissions:</p>

<form th:action="@{/oauth2/authorize}" method="post">
    <input type="hidden" name="client_id" th:value="${clientId}">
    <input type="hidden" name="state" th:value="${state}">

    <div th:each="scope : ${scopes}">
        <label>
            <input type="checkbox" name="scope"
                   th:value="${scope}" checked>
            <span th:text="${scope}">Permission description</span>
        </label>
    </div>

    <button type="submit">Allow</button>
</form>
```

`th:text` and `th:value` HTML-encode data during rendering. Avoid `th:utext` for client names, scope descriptions, or request inputs. In production products, map scopes to human-readable descriptions—for example, `profile` as "View basic profile information"—rather than expecting users to understand technical names. Display the registered client name and verified domain/publisher when available.

The form above submits each selected scope as an HTTP `scope` parameter. Submitted values must belong to the scopes from the initial authorization request. `client_id` and `state` must be sent back unaltered. If the user denies consent, implement denial handling per your Spring Authorization Server version's contract and test the resulting OAuth2 response; never simulate denial by tampering with `state` or redirecting arbitrarily.

### 5.3. Reducing Data Leakage on the Consent Page

The consent page normally receives `client_id`, `scope`, and `state` in the query string. Therefore:

- Do not load third-party analytics, ads, fonts, or scripts on login/consent pages without an explicit requirement. External resources receive request metadata and expand leakage surfaces.
- Set an appropriate Referrer Policy. `strict-origin-when-cross-origin` sends only the origin on cross-origin requests; `no-referrer` is stricter when pages carry sensitive query strings and do not need a referrer.
- Keep `no-store` cache control on login/consent responses and exclude these pages from service worker caches.
- Never log full consent URL query strings, `state`, authorization codes, or session IDs in application logs, reverse proxy access logs, or telemetry without redaction.
- Never render client-supplied content as HTML. Use allowlists for managed and verified logos or metadata.

## 6. Testing and Verification

Testing must cover both filter chains and real OAuth flows. Testing only the login page is insufficient because protocol endpoints live in another chain.

### 6.1. Testing with MockMvc

Example testing headers on the login page over HTTPS:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersIntegrationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginPageContainsSecurityHeaders() throws Exception {
        mockMvc.perform(get("/login").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("X-Frame-Options", "DENY"))
            .andExpect(header().string("Strict-Transport-Security",
                    containsString("max-age=31536000")))
            .andExpect(header().string("Content-Security-Policy",
                    containsString("frame-ancestors 'none'")))
            .andExpect(header().string("Permissions-Policy",
                    containsString("camera=()")));
    }
}
```

This test assumes `GET /login` returns `200 OK` from a custom login controller and template. If your endpoint redirects or uses the auto-generated default login page, adjust the status assertion to match actual behavior.

Run equivalent checks on the authenticated consent page. To verify headers on the authorization endpoint, execute a valid authorization request through Spring Authorization Server test flows and inspect responses/redirects from the first chain. Integration tests need a matching `RegisteredClient`, registered redirect URI, and authenticated user; a request missing OAuth2 parameters may return a protocol error, yet still verifies headers if the response originates from the right chain.

### 6.2. Testing with curl and the Browser

Request the login page over HTTPS:

```bash
curl -sS -D - -o /dev/null https://auth.example.com/login
```

Verify the following headers are present with expected values:

- `Cache-Control` contains `no-store` for sensitive pages.
- `X-Content-Type-Options` is `nosniff`.
- `X-Frame-Options` aligns with `frame-ancestors`.
- `Strict-Transport-Security` appears only on HTTPS responses.
- `Content-Security-Policy` or `Content-Security-Policy-Report-Only` matches the intended policy.
- `Referrer-Policy` and `Permissions-Policy` have expected values.

In browser DevTools, open the Network tab and inspect responses for `GET /login`, `GET /oauth2/consent`, and the authorization endpoint. Use the Console tab to spot resources blocked by CSP. Try embedding the login/consent page inside an iframe from another HTML page to verify clickjacking defenses. Inspect rendered HTML to confirm the login form has a CSRF token and the consent form carries the exact `client_id`, `state`, and selected scopes.

### 6.3. Testing Security Scenarios

| Scenario | Expected result |
|---|---|
| Access login over HTTPS | Response includes security headers; cache control prevents caching sensitive pages. |
| Access authorization endpoint | Headers are applied by the authorization-server filter chain. |
| Access consent while unauthenticated | Authentication flow redirects the user to login per configuration. |
| Login POST missing or wrong CSRF token | Request is rejected by Spring Security CSRF protection. |
| Consent POST missing or tampered `state` | Spring Authorization Server rejects the authorization/consent request. |
| Consent POST alters `client_id` or submits unrequested scopes | Authorization flow grants no permissions beyond the valid request. |
| Login/consent page embedded in an iframe | Browser blocks rendering per configured `X-Frame-Options`/CSP. |
| External resource outside CSP | Blocked when enforcing; logged when running Report-Only. |
| Log out then click Back | Browser does not redisplay sensitive content from HTTP cache. |

## 7. Common Configuration Mistakes

### Adding Headers to Only One Filter Chain

**Symptom:** The login page has CSP and HSTS, while protocol endpoint responses lack headers, or vice versa.

**Cause:** Each chain has its own request matcher and order. Requests are handled by the first matching chain; settings in another chain do not apply automatically.

**Resolution:** Place header setup in a shared helper and call it from every relevant chain. Verify chains with real requests rather than only reading Java config.

### CSP Blocks Login Page CSS or JavaScript

**Symptom:** The login page has no styling, buttons fail to work, or the Console reports `script-src`/`style-src` violations.

**Cause:** Policy allows only `'self'` while templates load from CDNs or use inline code.

**Resolution:** Move assets to the application's own origin, or allowlist specific controlled origins. Use nonces/hashes for unavoidable inline code. Run Report-Only before enforcing, and never add `'unsafe-inline'` casually.

### HSTS Missing Behind a Reverse Proxy

**Symptom:** Users access HTTPS, yet application responses omit `Strict-Transport-Security`.

**Cause:** TLS terminates at the proxy, so the application sees HTTP requests and does not recognize the original scheme.

**Resolution:** Configure forwarded-header handling aligned with infrastructure, trust headers only from controlled proxies, and ensure proxies strip client-supplied forwarded headers.

### Consent Form Errors Out or Fails to Complete Authorization

**Symptom:** User clicks Allow, yet the server returns a request error, consent is not saved, or the flow fails to return to the client.

**Cause:** The form does not POST to the authorization endpoint, omits `client_id`, loses `state`, or submits scopes absent from the authorization request.

**Resolution:** Inspect the query string Spring Authorization Server passes to the consent page and the form POST payload. Preserve `state`, return the exact client ID, and submit only user-approved scopes. Never replace `state` with the login form's CSRF token.

### Disabling CSRF Globally to Fix a Form Error

**Symptom:** The login form works after disabling CSRF, but other web endpoints become vulnerable to CSRF.

**Cause:** Configuration stripped protection from all state-changing requests.

**Resolution:** Keep CSRF enabled for login and application forms. Spring Authorization Server configures its own matcher to handle CSRF for its protocol endpoints; custom endpoints outside that matcher must define and test their own policies.

### HSTS `includeSubDomains` Causes Service Outages

**Symptom:** A legacy HTTP-only subdomain becomes unreachable once browsers cache HSTS.

**Cause:** The header applies the HTTPS policy to all subdomains.

**Resolution:** Enable `includeSubDomains` only after inventorying and deploying TLS across every subdomain. Because browsers cache HSTS for `max-age`, reverting server config does not immediately clear cached browser policies.

## 8. Recommended Rollout Process

1. Inventory every `SecurityFilterChain`, request matcher, and UI/protocol endpoint handled by each chain.
2. Retain Spring Security's default headers; verify cache control and `X-Content-Type-Options` are active.
3. Finalize HTTPS, reverse proxy, and HSTS scope before enabling `includeSubDomains` or `preload`.
4. Build CSP for login/consent based on actual assets, starting in Report-Only mode.
5. Apply the header policy across all relevant chains via a shared configuration function.
6. Audit login forms, CSRF tokens, session cookies, consent forms, `client_id`, `state`, and scope lists.
7. Run integration tests, inspect response headers with `curl`, test CSP in browsers, and rehearse the full authorization-code flow.
8. Switch CSP to enforcing once legitimate violations are resolved; continue monitoring after every template or frontend asset update.

## 9. Conclusion

Security headers help browsers handle responses safely; login and consent pages additionally require controls over sessions, CSRF, rendered content, and form-submitted data. With Spring Authorization Server, remember to configure headers on every filter chain, preserve CSRF for login forms, and round-trip consent-flow `state` strictly per the authorization endpoint contract. Verify both response headers and end-to-end authorization request behavior before deploying policies to production.

## References

1. [Spring Security Reference — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
2. [Spring Security Reference — Cross Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
3. [Spring Authorization Server Reference — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html)
4. [Spring Authorization Server Reference — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
5. [Spring Authorization Server API — OAuth2AuthorizationEndpointConfigurer.consentPage](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationEndpointConfigurer.html)
6. [OWASP Cheat Sheet — HTTP Headers](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
7. [OWASP Cheat Sheet — Clickjacking Defense](https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html)
8. [OWASP Cheat Sheet — Content Security Policy](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
9. [RFC 6797 — HTTP Strict Transport Security (HSTS)](https://www.rfc-editor.org/rfc/rfc6797)
10. [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
