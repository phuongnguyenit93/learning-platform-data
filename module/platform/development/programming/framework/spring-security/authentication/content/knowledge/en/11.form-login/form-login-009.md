# Restricting Redirect Destinations to Prevent Open Redirects in Form Login

## 1. Objective and Context

In Spring Security's **form login** mechanism (Servlet applications), after authentication succeeds, the server typically returns HTTP `302 Found` with a `Location` header to send the user to the next page. This destination is a **security decision**: if the server blindly echoes an address sent by the browser, an attacker can turn the application's trusted domain into a stepping stone to a phishing site.

After this lesson, you should be able to distinguish:
- **Server-designated destinations** vs. **user/attacker-supplied destinations** via `next`, `returnUrl`, `redirect`, `targetUrl`, `Referer`, or saved requests.
- When `defaultSuccessUrl` and `SavedRequestAwareAuthenticationSuccessHandler` determine the target.
- How to allow only a valid subset of destinations and test spoofed URLs, absolute URLs, URLs starting with `//`, encoded paths, or out-of-scope paths.
- Limitations of open-redirect defenses: they **do not replace** authentication, authorization on the destination endpoint, CSRF, or trusted proxy configuration.

Scope: **post-form-login redirects** in Spring Security Servlet; OAuth2/OIDC `redirect_uri` is a separate flow with its own registration and redirect URI matching rules.

## 2. How Does an Open Redirect Occur?

Suppose an application at `https://app.example` lets users log in and return to the address specified by `next`:

~~~http
POST /login?next=https://evil.example/phishing HTTP/1.1
Host: app.example
Content-Type: application/x-www-form-urlencoded

username=alice&password=...
~~~

If the login-success code calls `response.sendRedirect(request.getParameter("next"))`, the response can be:

~~~http
HTTP/1.1 302 Found
Location: https://evil.example/phishing
~~~

The user clicks a link starting with the legitimate application's domain, logs in successfully, and gets redirected to a fake site. This is **CWE-601: URL Redirection to Untrusted Site**. An open redirect does not automatically grant account access; its impact typically includes phishing, bypassing domain-based URL checks, and chaining with other authentication/authorization flaws.

Dangerous inputs are not limited to `https://evil.example`:

| Untrusted input | Issue |
| --- | --- |
| `https://evil.example/login` | Absolute URL to an external host |
| `//evil.example/login` | Protocol-relative URL; browsers can switch to an external host |
| `https://app.example.evil.example/` | Host prefixed with the real domain name, yet a different domain |
| `https://app.example@evil.example/` | Part before `@` is userinfo; actual host is `evil.example` |
| `/admin`, `../private` | Can route to unauthorized areas even within the same app |
| `%2F%2Fevil.example`, `\` backslashes, or multi-encoded strings | Can be interpreted differently by URL decoders, proxies, frameworks, or browsers |
| `javascript:...`, control characters, CR/LF | Malformed strings must be rejected and never passed straight into headers/redirects |

Never rely on string checks like `url.startsWith("https://app.example")` or `url.contains("app.example")`: they do not verify the actual host and are easily bypassed.

## 3. Where Does Spring Security Choose the Redirect Destination?

Basic flow:

1. An unauthenticated visitor requests a URL requiring authentication. `ExceptionTranslationFilter` may save the original request via `RequestCache` and send the visitor to the login form.
2. `UsernamePasswordAuthenticationFilter` processes `POST /login`; if credentials are valid, `AuthenticationSuccessHandler` decides the next step.
3. The common default handler is `SavedRequestAwareAuthenticationSuccessHandler`. Depending on configuration, it considers the fixed target, `targetUrlParameter`, and `SavedRequest`.
4. The server sends the redirect response. The browser reads `Location` and requests the next URL.

Precedence to remember in `SavedRequestAwareAuthenticationSuccessHandler`: `alwaysUseDefaultTargetUrl=true` prioritizes the default target; otherwise, a configured `targetUrlParameter` may be used; next is the `SavedRequest` URL; finally `defaultTargetUrl`. On the base handler class, `useReferer` can use the `Referer` header if enabled. Both request parameters and `Referer` are untrusted inputs.

### Two Easily Confused Configurations

~~~java
// Acts only as a default fallback when no matching SavedRequest exists beforehand.
http.formLogin(form -> form.defaultSuccessUrl("/dashboard"));
~~~

~~~java
// Always redirects to /dashboard after successful form login;
// does not return to an earlier SavedRequest.
http.formLogin(form -> form.defaultSuccessUrl("/dashboard", true));
~~~

The second option is appropriate if the product **does not need dynamic post-login redirects**. It is the simplest and lowest-risk choice. Do not configure `targetUrlParameter("next")` assuming Spring Security will enforce your app's allowlist for you: the application itself must enforce destination policy. Likewise, do not rely on `Referer` to decide where to send users.

## 4. Choose the Redirect Policy Before Writing Code

Priority from simplest and safest outward:

1. **Fixed destination:** after every successful login, go to `/dashboard` using `defaultSuccessUrl("/dashboard", true)`.
2. **Server-managed destination catalog:** if customization is required, clients send only short keys like `profile` or `orders`; the server maps keys to approved paths. **Never accept arbitrary URLs.**
3. **Only when a dynamic path must truly be returned:** normalize and validate using a parser aligned with both your redirect API and browsers, accepting only valid internal paths or explicitly allowed origins; re-validate immediately before emitting `Location`.

Policy example:

| `next` in login request | Server-selected destination |
| --- | --- |
| `profile` | `/profile` |
| `orders` | `/orders` |
| Missing, empty, or other value | `/dashboard` |
| `https://evil.example/` or `//evil.example` | `/dashboard`, never redirect to an external host |

If the application is deployed under context path `/portal`, the paths in the right column must become `/portal/profile`, `/portal/orders`, etc. Never construct URLs from uncontrolled `Host` or `X-Forwarded-Host` headers.

## 5. Spring Boot + Spring Security Example: Redirecting Only to Approved Targets

The example below targets **Java 17+, Spring Boot 3.x / Spring Security 6.x, Servlet applications**. Place the file in a Spring Boot project with `spring-boot-starter-web` and `spring-boot-starter-security` dependencies. This is a complete demo program in **one Java file**; the in-memory account is for practice only. Real applications must use a proper user store/IdP and secret management.

File `src/main/java/com/example/redirectdemo/RedirectDemoApplication.java`:

~~~java
package com.example.redirectdemo;

import java.io.IOException;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RedirectDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedirectDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/error").permitAll()
                .anyRequest().authenticated()
            )
            // Demo always picks target from allowlist without restoring SavedRequest.
            .requestCache(cache -> cache.requestCache(new NullRequestCache()))
            .formLogin(form -> form
                // Spring Security generates the default GET /login page.
                .successHandler(this::onLoginSuccess)
                .permitAll()
            );

        return http.build();
    }

    private void onLoginSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication) throws IOException {

        // "next" is untrusted input; DO NOT pass directly to sendRedirect.
        String next = request.getParameter("next");
        String safePath = approvedPath(next);

        // safePath can only be a server-defined internal path constant.
        response.sendRedirect(request.getContextPath() + safePath);
    }

    private static String approvedPath(String next) {
        if ("profile".equals(next)) {
            return "/profile";
        }
        if ("orders".equals(next)) {
            return "/orders";
        }
        return "/dashboard";
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @RestController
    static class DemoPages {
        @GetMapping({"/dashboard", "/profile", "/orders"})
        String page(HttpServletRequest request) {
            return "OK " + request.getRequestURI();
        }
    }
}
~~~

**Why does this example block open redirects?**

- `approvedPath` checks **exact equality** against two approved keys. No branch ever returns the client-supplied `next` string.
- The `Location` destination is built from the servlet container's context path and one of three constant paths `/profile`, `/orders`, `/dashboard`; malicious strings never participate in URL construction.
- `NullRequestCache` disables saving/restoring pre-login paths in this demo so a `SavedRequest` cannot bypass the new redirect policy. **Trade-off:** users opening a protected URL before logging in will not automatically return to that URL after authentication.
- `.permitAll()` grants access to the login page/endpoint; everything else remains protected by `.anyRequest().authenticated()`. The valid redirect allowlist does not determine who is authorized to view a target page's content.
- CSRF for form login keeps its default configuration. **Never use `csrf.disable()` to make POST tests easier.**

Spring Security's auto-generated default login page **does not automatically carry a `next` parameter from `GET /login?next=orders` into the POST**. If your product needs this, build a custom login form (with CSRF token) and pass the `next` **key** as a hidden field in `POST /login`. Hidden fields must still be treated as tamperable input. This lab uses MockMvc to send `next` directly on the POST request, testing the exact handler branch without extra templates.

Run in a Spring Boot project with the Maven wrapper:

~~~bash
./mvnw spring-boot:run
~~~

On Windows you can use `mvnw.cmd spring-boot:run`. After logging in with the demo account and visiting `/orders`, the controller returns `OK /orders`. After login, the default destination is `/dashboard` if the POST lacks an accepted key. Because this is a Spring Boot app, it **does not** compile standalone with `javac` without dependencies.

## 6. Testing Safe Redirects with MockMvc

Add `spring-boot-starter-test` and `spring-security-test` (`test` scope) to the project. This test suite targets the same Spring Boot 3.x project above. File `src/test/java/com/example/redirectdemo/RedirectDemoApplicationTests.java`:

~~~java
package com.example.redirectdemo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RedirectDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest
    @CsvSource({
        "profile, /profile",
        "orders, /orders",
        "https://evil.example/phish, /dashboard",
        "//evil.example/phish, /dashboard",
        "https://app.example.evil.example/, /dashboard",
        "https://app.example@evil.example/, /dashboard",
        "%2F%2Fevil.example, /dashboard",
        "../admin, /dashboard",
        "/admin, /dashboard",
        "javascript:alert(1), /dashboard",
        "unknown, /dashboard"
    })
    void choosesOnlyApprovedTargets(String next, String expected)
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-password")
                .param("next", next))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl(expected));
    }

    @Test
    void missingNextFallsBackToDashboard() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-password"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/dashboard"));
    }

    @Test
    void invalidCredentialsDoNotReachSuccessHandler() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "wrong")
                .param("next", "orders"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void postWithoutCsrfTokenIsDenied() throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "demo-password")
                .param("next", "orders"))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

Expectation: all tests pass; every `next` value outside the allowlist redirects to `/dashboard`, and no `Location` header points to `evil.example`. MockMvc uses `.with(csrf())` to simulate a valid form; only the negative CSRF test intentionally omits it. If the project uses a non-empty context path, adjust expected URLs accordingly and add matching context-path tests.

The test suite should be expanded for real-world features: empty inputs, case sensitivity, tabs/whitespace, Unicode, `\evil.example`, newline characters, single/multi-encoded URLs, query strings, redirects after session expiration, failed logins, role-restricted target paths, and reverse-proxy scenarios. Under a fixed-key policy, any string without an exact match falls back safely.

## 7. If the Product Must Return to the Page Requested Before Login

Do not automatically enable accepting arbitrary URLs just to preserve a "return to previous page" experience. Three design options exist:

**Option A — server-managed keys:** when prompting login, store a validated ID in the session (such as `orders`); after login, the server maps the ID to a constant target. If it must link to a parameterized entity (an order ID), the server must validate the ID format and order access permissions both before and after navigation. You can use a short-lived, session-bound, tamper-evident, expiring token referencing the verified destination.

**Option B — validating internal paths:** if business logic requires a variable return path, accept only paths validated by a parser under strict rules. Reject URLs with schemes/authorities, `//`, backslashes, control characters, userinfo, path traversal, invalid percent-encodings, and paths outside permitted prefixes/routes. Beware multi-layer decoding: the final destination the browser actually navigates to is what matters. Re-validate the target **right before emitting `Location`**. Never patch anomalies with ad-hoc string replacements and assume the result is safe.

**Option C — external-origin redirects genuinely required:** prefer mapping fixed keys to full HTTPS URLs on the server. If impossible, parse the URL using a maintained library, allow only `https`, match the normalized host and effective port **exactly** against an allowlist, reject userinfo and ambiguous constructs, and restrict paths as needed; never use prefix/suffix string matching. Consider an interstitial confirmation page when leaving the site.

With `SavedRequestAwareAuthenticationSuccessHandler`, understand that a saved URL can take precedence over `defaultSuccessUrl("/dashboard")`. If using `SavedRequest`, control what requests get saved, enforce host/public-origin rules, configure trusted proxies, and apply safety checks to saved targets. If deep linking is unnecessary, pick a fixed target with the `true` flag or a custom handler paired with `NullRequestCache` as in the example. Never assume "the URL is in the session" makes it inherently trustworthy: it may have originated from a client-initiated request.

## 8. Common Implementation Mistakes

| Mistake | Why it is unsafe / misleading | Fix |
| --- | --- | --- |
| `sendRedirect(request.getParameter("next"))` | Browser destination comes directly from external input | Use fixed targets or map keys to approved targets |
| `url.startsWith("https://app.example")` | Accepts `https://app.example.evil.example` | Compare parsed host/origin or use internal keys |
| `url.endsWith("app.example")` | Raw strings do not reflect host, scheme, userinfo, or port | Use a URL parser + exact allowlist |
| Allowing URLs starting with `/` | `//evil.example` also starts with `/` | Do not check just one character; prefer identifier mapping |
| Enabling `targetUrlParameter` for form-login convenience | Parameter can be tampered with by an adversary | Validate before redirecting or replace with allowlisted success handler |
| Setting `defaultSuccessUrl("/dashboard")` assuming it always lands there | `SavedRequest` can take precedence over the default target | Use the `(..., true)` overload if you want it fixed |
| Trusting `Referer`, `Host`, `X-Forwarded-Host` as safe origin sources | Headers can be forged when proxies are misconfigured | Configure trusted proxies/hosts explicitly; never take redirect targets from raw headers |
| Blocking external hosts yet allowing every internal path | Can route to unintended endpoints or cause logic bugs | Restrict valid routes and preserve endpoint authorization |
| Disabling CSRF to test `POST /login` | Weakens form-login security and hides config bugs | Use real CSRF tokens or `.with(csrf())` in tests |

**Access control note:** redirecting to `/admin` does not grant `/admin` access automatically; Spring Security must still block unauthorized users. Even so, redirect targets should never violate product policy. **Logging note:** log rejected anomalous `next` values at an appropriate level, while avoiding logging passwords, login tokens, or full query strings containing sensitive info.

## 9. Pre-Production Checklist

- [ ] Post-login target is determined from server configuration or an approved set of IDs/paths; never pass raw user input into `Location`.
- [ ] Reject URLs with external hosts in `next`/`returnUrl`, unless explicitly required by the product with a strict origin allowlist.
- [ ] Audit `targetUrlParameter`, `SavedRequest`, `Referer`, and custom success handlers; every redirect branch must follow the same policy.
- [ ] Login page passes the right business key when needed; hidden fields are validated server-side; CSRF remains enabled.
- [ ] Failed login or missing CSRF never triggers a `next` redirect.
- [ ] Test absolute URLs, `//host`, lookalike hosts, userinfo, URL-encoding, path traversal, and empty input.
- [ ] Deterministic fallback exists; handle context paths/reverse proxies consistently and trust forwarded headers only from authorized proxies.
- [ ] Every target route still enforces authentication/authorization independently.

## 10. Official References

1. Spring Security — Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
2. Spring Security API — `SavedRequestAwareAuthenticationSuccessHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html
3. Spring Security API — `AbstractAuthenticationTargetUrlRequestHandler` (`targetUrlParameter` and `useReferer` warnings): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationTargetUrlRequestHandler.html
4. Spring Security API — `RequestCache`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/savedrequest/RequestCache.html
5. Spring Security — Testing Form Based Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
6. OWASP — Unvalidated Redirects and Forwards Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

**Core principle to remember:** redirect only to destinations **decided or verified by the server**, and assert the `Location` header after **successful login**—not merely the login form or HTTP status code.