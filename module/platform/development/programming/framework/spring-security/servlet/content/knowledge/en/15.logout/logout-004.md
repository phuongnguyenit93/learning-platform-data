# Clearing Session Cookies, Remember-Me, and Browser Data Properly

Logging out in **Spring Security for Servlet applications** is more than redirecting to the login page. A secure logout may need to address multiple layers of state: **`SecurityContext`**, server-side **`HttpSession`**, browser session cookies, **remember-me** cookies and associated tokens, CSRF tokens, application data held in tabs/the browser, as well as caches containing sensitive content.

Key point: **invalidating the session on the server and deleting cookies in the browser are two distinct operations**. A cookie may still exist after the session is invalidated, yet it can no longer look up a valid session. Conversely, deleting a cookie does not automatically revoke sessions, remember-me tokens in a database, or issued access tokens. You must therefore select measures matching the **actual authentication mechanism** in use.

This lesson focuses on Spring Boot 3.x, Spring Security 6.x, and Java 17+ in the **Servlet, form login, and session-based authentication** model. It walks through cookie scope, Spring Security's `logout` DSL, token-based/persistent remember-me, `Clear-Site-Data`, CSRF cookies, frontend cleanup, a complete configuration example, testing, common pitfalls, and a production checklist. Differences across versions, servlet containers, and HTTPS/reverse-proxy setups must be verified in the deployment environment.

## 1. After Logging In, Where Does State Live?

A typical web application may have several “pieces” of a login session:

~~~text
Browser                                      Server / infrastructure
+--------------------------------+         +--------------------------------+
| JSESSIONID cookie              | ------> | HttpSession (container/store)  |
| remember-me cookie             | ------> | RememberMeServices + key/token |
| XSRF-TOKEN (if using this repo)|         | CSRF token repository          |
| localStorage/sessionStorage    |         | SecurityContextRepository      |
| app memory / SPA state         |         | SessionRegistry (if used)      |
| browser cache / bfcache        |         | Remember-me persistent DB      |
+--------------------------------+         | JWT/refresh token store/IdP    |
                                           +--------------------------------+
~~~

Every component in the diagram **does not exist by default**. For example: a site storing CSRF tokens in the HTTP session will not need an `XSRF-TOKEN` cookie; a stateless resource server using only Bearer JWTs may have no `JSESSIONID` for authentication; an app without remember-me enabled will not use a remember-me cookie.

For stateful Servlet form login, the main concepts are:

- `HttpSession`: where the container or Spring Session keeps session data. The `JSESSIONID` cookie is typically an identifier to look up the session, **not a plaintext container holding `SecurityContext` directly**.
- `SecurityContext`: holds the current `Authentication`. With session-based login, `SecurityContextRepository` can save/load the context via the session; after logout, the context should no longer be reused.
- `RememberMeServices`: mechanism to recognize the user on later requests after the session disappears while the browser still holds a valid remember-me cookie; must be properly logged out/canceled.
- `CsrfTokenRepository`: stores/returns anti-CSRF tokens; may use the session or a cookie. A CSRF token's lifecycle differs from that of a JWT or remember-me token.
- Frontend data: cache, state, storage, and rendered content in tabs may remain even after the server rejects new requests.

A complete logout UX should clean up **server-side authentication state** and **client traces within allowed scope**, without recklessly wiping unrelated data.

## 2. What Does Spring Security's Standard Logout Do?

With default form login, Spring Security has `LogoutFilter` handling the configured logout endpoint. When a request matches, the filter runs the `LogoutHandler` instances to clean up state and then calls `LogoutSuccessHandler` to return a response/redirect.

~~~text
POST /logout + valid CSRF token
          |
          v
CsrfFilter (if enabled)
          |
          v
LogoutFilter
          |
          +--> SecurityContextLogoutHandler
          |      +--> invalidate HttpSession per config
          |      +--> clear Authentication / SecurityContext
          |      +--> save empty context state per repo
          |
          +--> CsrfLogoutHandler (if configured in chain)
          |      +--> clear corresponding CSRF token
          |
          +--> RememberMeServices.logout(...) (when remember-me enabled)
          |      +--> cancel cookie / token data per mechanism
          |
          +--> Custom LogoutHandler if any
          |
          v
LogoutSuccessHandler
          +--> redirect /login?logout
          or return HTTP 200/204/JSON for APIs
~~~

The diagram shows **responsibilities**, not an immutable internal order across all versions or custom handlers. Depending on beans/configuration, the actual list of handlers may vary.

### Key Lifecycle

1. **Before logout:** the browser has a session cookie; the server may hold `Authentication` in the session. A remember-me cookie may exist independently.
2. **During logout:** the server invalidates the session and clears the context per policy; the remember-me service gets an opportunity to handle its cookie/token. If a custom handler writes a bad response or throws an exception, logout may fail to reach the full intended state.
3. **After logout:** requests to protected resources must no longer authenticate via the old session. The browser may need to redirect/log in again. If remember-me stays valid, the next request may **auto-log in again**, creating the impression that “logout didn't work.”
4. **Client data:** content already open in a tab or sitting in storage may remain visible in the UI; clean it per product requirements, while the server always enforces authentication/authorization on new requests.

### Logout Must Use POST When CSRF Is Enabled

With Spring Security form login and default CSRF protection, **POST `/logout`** with a valid CSRF token is the standard action. `GET /logout` in some configurations may only display a logout confirmation page, **not execute logout on an arbitrary GET**. Do not disable CSRF simply because a GET logout link feels convenient: logout CSRF can force users out unexpectedly, and complex apps carry additional risks.

## 3. Two Separate Actions: Invalidate Session and Delete Cookie

### 3.1. Server-Side Session Invalidation

DSL fragment:

~~~java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true));
~~~

`invalidateHttpSession(true)` instructs `SecurityContextLogoutHandler` to handle invalidation of the appropriate session. `clearAuthentication(true)` clears `Authentication` in the context upon logout. In standard Spring Security logout configuration, these baseline security behaviors are normally already enabled; specifying them explicitly makes intent clear to readers.

When a session is invalidated:

- Session data tied to the old ID can no longer be retrieved as a valid session through the session store/container.
- The context stored in the old session can no longer authenticate new requests.
- Business attributes stored inside the session may also be removed, not only `Authentication`.
- The old browser cookie **is not automatically deleted across every container/browser**. The browser may keep sending the old `JSESSIONID`; it simply no longer points to a valid session.

**Do not use cookie deletion as a substitute for session invalidation.** Cookie deletion is a request sent to the browser; it does not guarantee destruction of an existing server session object. Security relies on server-side invalidation and authentication checks first.

### 3.2. Instructing the Browser to Delete a Cookie

HTTP cookies have no special server “delete” command. The server sends `Set-Cookie` for the same cookie with `Max-Age=0` (or a past `Expires`), along with the matching `Path` and `Domain` scope; the browser uses that header to expire the cookie.

~~~http
HTTP/1.1 302 Found
Location: /login?logout
Set-Cookie: JSESSIONID=; Path=/; Max-Age=0; HttpOnly
~~~

This is an **illustrative HTTP example**, not a claim that every real app has `Path=/` or this exact attribute order. Servers may use a past `Expires`, and cookies may be configured with `Secure; SameSite=Lax`. When HTTPS is used, verify attributes match your cookie policy.

With Spring Security:

~~~java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .deleteCookies("JSESSIONID")
    .logoutSuccessUrl("/login?logout"));
~~~

`deleteCookies("JSESSIONID")` adds an instruction to send an expired cookie for that name; it **does not automatically know every `Path`/`Domain` variant** issued by other infrastructure layers. Apps setting `server.servlet.session.cookie.name=SESSIONID` or Spring Session using a different cookie name must delete the actual name. In projects behind reverse proxies/context paths, inspect the actual `Set-Cookie` header in responses.

### 3.3. Cookies Are Identified by Name, Domain, and Path

Two cookies with the same name but different `Path` or `Domain` can coexist. Deleting `JSESSIONID` with a mismatched `Path` may leave the old cookie untouched.

| Issued cookie | `Set-Cookie` to delete | Expectation |
| --- | --- | --- |
| `JSESSIONID`, host-only, `Path=/` | Same name, host-only, `Path=/`, `Max-Age=0` | Deletes the right cookie |
| `JSESSIONID`, host-only, `Path=/portal` | Same name but `Path=/` | **Does not delete** the cookie on `/portal` |
| `remember-me`, `Domain=example.test`, `Path=/` | Host-only cookie (no Domain) | May fail to delete the Domain-scoped cookie |
| `JSESSIONID`, `Path=/portal`, matching domain | Same name/domain/path, `Max-Age=0` | Deletes the right scope |

Inspect `Domain`/host-only from the `Set-Cookie` response **at issuance time**, rather than guessing from the cookie name alone. For special cookie names like `__Host-...`, browser `Secure`/`Path`/`Domain` rules must be respected both when issuing and expiring.

**Note on servlet app Path:** When an app runs under `/portal`, the session cookie often has `Path=/portal` or a configured value; with Spring Session, proxies, and load balancers, the name and Path may differ. Cookie deletion must match the infrastructure that actually sets the cookie.

### 3.4. `HttpOnly` and JavaScript

An `HttpOnly` cookie cannot be read or deleted directly via `document.cookie` from JavaScript. That is intentional to protect cookies from JavaScript access. The proper approach: **the server returns an expired `Set-Cookie`** and invalidates the session. Never remove `HttpOnly` just so the frontend can delete `JSESSIONID` itself.

Browsers may ignore or restrict `Set-Cookie` headers under mismatched domain, HTTPS, `SameSite`, CORS, or path conditions. Always test in real browsers.

## 4. Remember-Me: Why Does Logging Out Auto-Log Back In?

Remember-me exists to let a browser restore `Authentication` on a later request **when the session is gone yet the remember-me cookie remains valid**. If you only delete `JSESSIONID`, the app may encounter:

~~~text
User logs in + selects Remember me
   |
   v
Server issues session + remember-me cookie
   |
   v
User logs out; only session/JSESSIONID invalidated
   |
   v
Browser still holds remember-me cookie
   |
   v
GET /private
   |
   v
RememberMeAuthenticationFilter + RememberMeServices
   |
   v
Creates valid RememberMeAuthenticationToken per policy
   |
   v
User appears as if they never logged out
~~~

Therefore, logout configuration must integrate the appropriate **`RememberMeServices.logout(...)`**; deleting only the session cookie is not enough. With default remember-me configured via the `rememberMe(...)` DSL, Spring Security can wire remember-me services into the standard logout pipeline.

### Token-Based Remember-Me

`TokenBasedRememberMeServices` can generate a cookie containing data verified with a key/signature per its implementation. It differs from a session cookie: the session can expire while remember-me remains valid. Logout must expire the remember-me cookie in the browser. However, with a **stateless token-based** mechanism, deleting the cookie on the current device **does not necessarily revoke copied tokens immediately if they were stolen**; the server typically has no per-token record for instant revocation. Consider threat modeling, key rotation, password changes, or a server-side token architecture if your product demands it.

Do not confuse remember-me cookies with JWTs or OAuth2 refresh tokens. Each mechanism has a different storage and revocation model.

### Persistent Remember-Me

`PersistentTokenBasedRememberMeServices` can use `PersistentTokenRepository` to maintain token series/token state in a database. In this case, the server can **delete the user's tokens** via the service/repository mechanism. After logout, server data and browser cookies must be updated consistently; sending `Max-Age=0` while leaving tokens in the DB does not satisfy every revocation policy.

An implementation may remove remember-me tokens by **username** on logout, affecting multiple devices; actual behavior must be understood, tested, and explicitly designed. Do not promise “logging out this device revokes only one cookie” or “logs out all devices” without checking the implementation and additional logic.

### Comparing Both Types

| Attribute | Token-based remember-me | Persistent remember-me |
| --- | --- | --- |
| Where validity is decided | Cookie data + secret/password per implementation | Cookie data and repository record |
| Cookie deleted in browser | Stops auto-login on that browser once cookie is gone | Stops auto-login on that browser |
| Revoking stolen token copies | No built-in per-token revocation list | Supported via server-side repository |
| Standard logout | Ensure RememberMeServices is configured/invoked and cookie cleared | RememberMeServices + repository cleanup per policy |
| Multiple devices | Does not invalidate all token copies by default | Depends on how repository deletes tokens by username/series |

### Remember-Me Cookie Name and Expiration

The common name is `remember-me`, though it can be customized. If the app renames it, `deleteCookies("remember-me")` will not delete the custom cookie. Configure **consistent cookie names for issuance and deletion**, define `Path`/`Domain` and lifetime, and test real requests.

Never store passwords in custom cookies, never put user roles or client-authenticated state inside a trusted remember-me token without server verification, and never log remember-me cookies.

## 5. Spring Boot 3 Example: Form Login, Remember-Me, and Logout

The example below uses **`HttpSession` + form login + token-based remember-me** with an in-memory demo account. When the user logs out, Spring Security handles context/session cleanup, the remember-me service, and asks the browser to delete `JSESSIONID`. This example is for learning environments, not production-ready.

### 5.1. Maven Dependencies

In a Spring Boot project with compatible parent/BOM and build plugins, use:

~~~xml
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
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The Java sources below require the Spring Boot and Spring Security classpath; they **cannot run with bare JDK `javac` alone**. A standalone Java 17 example appears in section 12.

### 5.2. Main Class

Create `src/main/java/com/example/logout/LogoutApplication.java`:

~~~java
package com.example.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutApplication.class, args);
    }
}
~~~

### 5.3. `SecurityConfig`

Create `src/main/java/com/example/logout/SecurityConfig.java`:

~~~java
package com.example.logout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {

        // Secret used for remember-me signing; never hardcode in production.
        String rememberMeKey = System.getenv("DEMO_REMEMBER_ME_KEY");
        if (rememberMeKey == null || rememberMeKey.isBlank()) {
            throw new IllegalStateException(
                "Set DEMO_REMEMBER_ME_KEY for local demo");
        }

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/private")
                .permitAll())
            .rememberMe(remember -> remember
                .key(rememberMeKey)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessUrl("/login?logout")
                .permitAll());

        // CSRF remains enabled per Spring Security defaults.
        return http.build();
    }
}
~~~

**Configuration notes:**

1. `formLogin(...)` processes `POST /login` and can provide the default login page. If the user checks remember-me, the form submits the `remember-me` parameter and the remember-me service issues a cookie on successful authentication.
2. `rememberMe.key(...)` uses an environment-provided secret; never use weak static values in production. Real apps must manage secrets via a secret manager with rotation and compatible migration plans.
3. `rememberMe.userDetailsService(users)` tells the remember-me mechanism how to reload the user when needed.
4. `logout.invalidateHttpSession(true)` and `clearAuthentication(true)` explicitly declare session/context cleanup.
5. `deleteCookies("JSESSIONID")` asks the browser to delete the session cookie if name/scope match. This is a **supplementary step**, not a substitute for session invalidation.
6. Because remember-me is configured via the Spring Security DSL, standard logout can invoke `RememberMeServices.logout(...)` to cancel the remember-me cookie. Do not invent a custom endpoint to clear the remember-me cookie while bypassing the service.
7. `logoutSuccessUrl("/login?logout")` redirects after a successful logout. This page must not require the old session; `permitAll()` supports access to logout-related URLs.
8. CSRF is not disabled. Users must send **`POST /logout` with a valid CSRF token**. `GET /logout` should not be used as a “shortcut” to destroy sessions.

**Version caveat:** Spring Security 6.x has minor-version differences in APIs/constructors/configuration; use the compatible Spring Boot BOM and test against your project's libraries. Some Spring Session apps use a cookie named `SESSION` instead of `JSESSIONID`; adjust cookie deletion to the exact name and scope rather than copying blindly.

### 5.4. Controller to Test Logout

Create `src/main/java/com/example/logout/Pages.java`:

~~~java
package com.example.logout;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class Pages {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    public String privatePage(Principal principal) {
        return "private for " + principal.getName();
    }
}
~~~

All methods return plain text; the default `/login` page is generated by the framework when no custom login page is set. When the session is gone, accessing `/private` may redirect to `/login` instead of invoking the controller.

### 5.5. `application.properties`

Create `src/main/resources/application.properties` for the demo:

~~~properties
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
# Production HTTPS requires secure cookies and appropriate SameSite:
# server.servlet.session.cookie.secure=true
~~~

A 20-minute session timeout does **not** shorten a 7-day remember-me cookie; the two mechanisms have different lifecycles. If the browser retains the remember-me cookie, it can automatically restore authentication after the session expires. That is precisely why logout must cancel remember-me, not merely invalidate the session.

### 5.6. Running the Demo

Use a local environment variable containing no production secret:

~~~bash
# For development environments only, e.g., Unix-like shells.
export DEMO_REMEMBER_ME_KEY='random-local-demo-key-not-for-production'
./mvnw spring-boot:run
~~~

Open `http://localhost:8080/login`, log in as Alice using `demo-only-password`, optionally checking “Remember me.” In browser DevTools, observe cookies before/after logout **only locally**; never copy real cookie values into tickets, chats, or logs. After logout, requesting `/private` with old cookies must not regain `Authentication` because the session was destroyed or the remember-me token was canceled.

If the cookie is deleted yet `/private` still auto-logs back in, check whether the browser holds another remember-me cookie **with a different path/domain** or whether the app uses a second authentication mechanism (SSO, Bearer token, proxy auth). Never rely solely on a 302 response to conclude logout succeeded.

## 6. `CookieClearingLogoutHandler` and Scope-Accurate Cookie Deletion

Spring Security supports `CookieClearingLogoutHandler`, typically configured via `logout().deleteCookies(...)`. Treat it as a way to **emit a response asking the browser to expire a cookie**, not an API to revoke server sessions.

~~~java
// Fragment: delete additional cookies matching names actually used by the app.
http.logout(logout -> logout
    .deleteCookies("JSESSIONID", "my-app-pref"));
~~~

`my-app-pref` is a hypothetical cookie for illustration. **Do not indiscriminately delete** analytics, consent, accessibility preference, or other applications' cookies just because a user logs out; identify which data is genuinely sensitive or authentication-related.

### When Custom Cookie Deletion Is Needed

If a cookie was issued with a specific `Path`/`Domain`, you can use a custom `LogoutHandler` setting those exact attributes. Fragment:

~~~java
// Fragment inside Spring Security configuration; add imports
// per project: jakarta.servlet.http.Cookie, LogoutHandler, etc.
LogoutHandler expireCustomCookie = (request, response, auth) -> {
    Cookie cookie = new Cookie("MY_SESSION", "");
    cookie.setPath("/portal");
    cookie.setMaxAge(0);
    cookie.setHttpOnly(true);
    cookie.setSecure(request.isSecure()); // appropriate when app uses HTTPS
    response.addCookie(cookie);
};
~~~

This snippet is **only an example for a host-only cookie with `Path=/portal`**. If the original cookie had a `Domain`, set the matching `Domain`. `request.isSecure()` may not reflect HTTPS outside a reverse proxy if forwarded headers are not configured as trusted; in production HTTPS, rely on known cookie policies rather than guessing attributes from untrusted request headers. Browsers may ignore cookie deletion if attributes are invalid or scopes mismatch.

Wire it into the logout DSL:

~~~java
http.logout(logout -> logout
    .addLogoutHandler(expireCustomCookie));
~~~

`expireCustomCookie` is declared in scope or as an application-created bean. Do not replace the entire `LogoutFilter` with a custom controller just to emit `Set-Cookie`; doing so easily drops the framework's default `LogoutHandler`s.

## 7. CSRF Cookies, `XSRF-TOKEN`, and Logout

Spring Security can store CSRF tokens using `HttpSessionCsrfTokenRepository` or `CookieCsrfTokenRepository`. Both supply valid tokens for POST/PUT/DELETE requests; cookie-based repositories can emit a cookie named `XSRF-TOKEN` depending on configuration.

Distinguish clearly:

- The `JSESSIONID` cookie references the session (in the common model).
- The `remember-me` cookie enables long-lived re-authentication when enabled.
- The `XSRF-TOKEN` cookie lets the frontend read/send anti-CSRF tokens; **it is neither a session ID nor a remember-me credential**.

Spring Security provides `CsrfLogoutHandler` to clear stored CSRF tokens on logout in appropriate configurations. For SPAs using `CookieCsrfTokenRepository`, logout can render the previous CSRF token invalid, requiring the frontend to fetch a new token for subsequent interactions.

### Should You Call `deleteCookies("XSRF-TOKEN")`?

Not by default. With a cookie-based CSRF repository, token cleanup may already be handled by the repository/handler. Extra cookie deletion out of sync with server state can leave the frontend with a stale token or unable to POST after logout. Instead:

1. Identify the CSRF repository and actual token name/path/domain.
2. Test that logout responses clear CSRF tokens properly.
3. Have the frontend fetch a fresh CSRF token when needed to render/submit login, rather than reusing the pre-logout token.
4. Never disable CSRF globally just to make logout easier while browsers still rely on cookies.

**CSRF and CORS are not the same thing.** CORS governs which cross-origin scripts can read/send requests under browser rules; it does not replace protection against cross-site actions over cookie-based authentication.

## 8. `Clear-Site-Data`: Clearing Browser Data via a Response Header

The `Clear-Site-Data` HTTP response header can ask the browser to clear specific categories of site data. Common directives:

~~~http
Clear-Site-Data: "cache", "cookies", "storage"
~~~

General meaning:

| Directive | Targeted data | Risks / caveats |
| --- | --- | --- |
| `"cache"` | Certain browser caches scoped to the site/origin per implementation | May increase reload times |
| `"cookies"` | Cookies within the scope defined by spec/browser | Can affect **multiple apps on the same domain or subdomains** |
| `"storage"` | Site data like `localStorage`, `IndexedDB`, and supported storage areas | Can wipe unsynced offline/user data |
| `"executionContexts"` | Requests refreshing/reloading open execution contexts where supported | Broad UX impact; not needed by default for every logout |

**Do not enable every directive unconditionally.** The `"cookies"` directive may affect cookies belonging to other applications on the same registrable domain depending on rules and browsers. The `"storage"` directive may wipe offline/PWA data and non-login state. Browsers vary in support levels, and the header is typically enforced only in **secure contexts (HTTPS)**; test compatibility, especially when developing on localhost and behind reverse proxies.

For applications that only need to clear sessions and remember-me, `Clear-Site-Data` is usually **not required**. If your system has a post-logout site-data cleanup policy and users understand the impact, choose narrow directives.

### Optional Addition in Spring Security

Once you decide to clear browser cache/storage and have evaluated the blast radius, an application can attach a `LogoutHandler` sending the header:

~~~java
// Fragment: apply only if logout policy requires clearing cache/storage.
// This is not a mandatory setting for every application.
http.logout(logout -> logout
    .addLogoutHandler((request, response, auth) ->
        response.setHeader(
            "Clear-Site-Data", "\"cache\", \"storage\"")));
~~~

The code uses Java string escaping so the actual response carries `"cache", "storage"`. This is a **fragment** placed inside `SecurityFilterChain`, not a standalone Java file. If there is an explicit requirement to wipe cookies via `Clear-Site-Data`, add `"cookies"` only after reviewing its impact on sibling apps on the same site, and **still perform server-side invalidation**.

The header is only a client-side request, not a server-side credential-revocation mechanism; full execution across every browser/version is not guaranteed. For frontends holding critical offline data, consider selective cleanup by app keys instead.

### Be Careful About “Clearing Browser Data”

A logout endpoint cannot arbitrarily wipe browsing history, unrelated domains' cookies, other apps' tabs, or global browser data. Browsers restrict permissions and scope. When communicating to users, state accurately “the application has logged you out and requested the browser to clear related data” rather than promising “all traces have been erased.”

## 9. What Should the Frontend Clean Up on Logout?

Server-side logout can succeed while a SPA still holds the username, avatar, or sensitive details in memory/state. Frontend cleanup is therefore needed, **scoped to the application and controlled**.

### 9.1. Clearing App State

After a successful logout response or once a session is confirmed expired:

- Clear cached user profiles and permissions from the state store.
- Delete access tokens/refresh tokens **if your architecture stores them on the frontend**; prefer designs that avoid keeping long-lived credentials in `localStorage` whenever possible.
- Clear cached authenticated API responses to prevent showing the previous user's data to the next user.
- Stop polling/requests requiring authenticated state and close corresponding subscriptions/WebSockets.
- Synchronize logout state across tabs of the same origin per frontend policy.

An illustrative **JavaScript frontend fragment**:

~~~javascript
async function logoutCurrentUser(csrfToken) {
  const response = await fetch("/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-TOKEN": csrfToken }
  });

  if (!response.ok && !response.redirected) {
    // Do not claim the server logged out if the request was rejected.
    throw new Error("Logout did not complete");
  }

  // Clear the app's own keys; DO NOT call localStorage.clear()
  // if the same origin stores important data for other modules.
  sessionStorage.removeItem("app-current-user");
  localStorage.removeItem("app-auth-cache");
  window.location.assign("/login?logout");
}
~~~

This is an illustrative fragment, **not a complete SDK**: the app needs a mechanism to obtain the CSRF token matching its repository/handler; `fetch` auto-following redirects may return HTML, and checking `response.redirected` does not replace confirming logout success via an explicit HTTP contract. Complex frontends should prefer an endpoint/logout response returning `204` or clear JSON. Handle network errors consistently without falsely “clearing UI and claiming the server session was revoked.”

### 9.2. Do Not Reflexively “Wipe All Storage”

`localStorage.clear()` and `sessionStorage.clear()` erase every key in the corresponding storage scope, potentially destroying offline drafts or other apps on the same origin. Prefer app-owned key prefixes/names; if the product requires clearing everything, make a deliberate UX and offline-data backup decision.

### 9.3. Old Tabs and Back/Forward Cache

Logout cannot automatically make already-rendered DOM in other tabs vanish immediately. After logging out and pressing Back, the browser may display a stale page snapshot from the back/forward cache (bfcache). Sensitive pages need proper cache policies and session checks at appropriate moments; most importantly, the server must still return 401/redirect for **new requests** after logout.

Pages/responses containing sensitive content should consider:

~~~http
Cache-Control: no-store
~~~

Spring Security HTTP headers include default caching policies on many protected responses, yet do not assume every HTML/API response or CDN-cached asset receives them when custom filters/proxies are involved. Inspect actual headers and CDN cache policies.

### 9.4. Multiple Tabs on the Same Origin

When tab A logs out, tab B may still show the old user until a new request occurs. You can use `BroadcastChannel` or `storage` events to signal a **credential-free** logout state and clear UI state. Still, inter-tab messaging **is not a security proof**; server-side session invalidation/revocation is what blocks subsequent requests.

## 10. Stateless APIs, Bearer JWTs, and Refresh Tokens: Limits of Cookie Logout

Apps not using `HttpSession` and relying on `Authorization: Bearer ...` face a different problem set:

| Component | How should it be handled after logout? |
| --- | --- |
| Server session | If no session exists, there is no session to invalidate |
| Stateless JWT access token | Does not automatically expire simply because the browser deleted its local copy; requires short TTLs or a revocation architecture |
| Refresh token | Must be revoked/rotated at the authorization server or token store per policy |
| Browser storage/cookies holding tokens | Delete cookies/storage within scope, without replacing server-side revocation |
| OpenID Connect provider session | May require RP-initiated logout / back-channel / front-channel logout depending on the system |
| API cache containing user data | Clear client cache and avoid caching sensitive responses |

**Do not put `deleteCookies("JSESSIONID")` on a stateless resource server and claim all Bearer tokens are logged out.** Issued tokens may remain valid at the server until expiry or architectural revocation. If the app uses federated login, the identity provider's cookies on a **different origin** cannot be arbitrarily deleted by this application's logout handler.

### Logging Out All Devices Differs from Logging Out the Current Device

A single logout normally invalidates the **current session** and clears current cookies. Logging out all devices requires a dedicated server-side mechanism: tracking sessions per account via a registry/session store, revoking refresh tokens, token versioning, remember-me repository cleanup, event propagation, and so on. A `Set-Cookie: Max-Age=0` response reaches only the **browser receiving that response**, with no direct effect on cookies on other devices.

When a product requires “logout everywhere,” explicitly define both sessions and tokens/remember-me across all devices, design transactions/revocation, and test thoroughly. Do not assume Spring Security defaults cover everything out of the box.

## 11. Testing Spring Security Logout with `MockMvc`

For the Spring Boot app in section 5, verify at minimum:

1. `POST /logout` with a CSRF token when logged in.
2. The post-logout HTTP response matches the redirect/response contract.
3. The old session is no longer authenticated after logout.
4. The response includes session cookie expiration instructions if configured.
5. The remember-me cookie is canceled when remember-me was issued.
6. `POST /logout` missing CSRF is blocked per policy.
7. Unrelated cookies are not accidentally deleted.
8. Header-based cookie deletion does not replace testing server-side invalidation.

### 11.1. Testing Session Invalidation and Cookie Expiry

Create `src/test/java/com/example/logout/LogoutIntegrationTest.java`:

~~~java
package com.example.logout;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void logoutInvalidatesSessionAndExpiresSessionCookie()
            throws Exception {

        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk());

        MvcResult out = mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        List<String> cookies =
            out.getResponse().getHeaders("Set-Cookie");

        assertTrue(cookies.stream()
            .anyMatch(v -> v.startsWith("JSESSIONID=") &&
                (v.contains("Max-Age=0") || v.contains("Expires="))));

        // Session is invalidated on the server, not just deleted on the client.
        assertTrue(session.isInvalid());

        // New request without session/remember-me cookie -> unauthenticated.
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void csrfIsRequiredForLogout() throws Exception {
        mvc.perform(post("/logout"))
            .andExpect(status().isForbidden());
    }
}
~~~

The test expects the beans, classes, environment key, and filter chain from section 5 to load properly. It expects the `JSESSIONID` cookie to be expired because `deleteCookies("JSESSIONID")` was configured; actual cookie names may differ in other projects. `MockHttpSession.isInvalid()` verifies the mock session was invalidated. Systems using Spring Session with another store should verify the real storage, not just `MockHttpSession`.

**Caveat:** Assertions do not prove a real browser received/deleted the cookie, because `MockMvc` simulates Servlet requests/responses. Test against an embedded server/browser with real `Path`/`Domain`/`Secure`/`SameSite` settings to confirm cookie removal. Proper testing of remember-me cancellation should inspect the `Set-Cookie` header for the issued remember-me cookie name or verify the database token repository when using persistent remember-me; Spring Security versions may serialize/expire cookies differently.

### 11.2. Testing Remember-Me Properly

A rigorous integration test should create a logged-in session with the remember-me option, capture the remember-me `Set-Cookie`, then log out **with that same cookie/session**, verifying the remember-me cookie is expired and no longer auto-logs in. For persistent remember-me, verify `PersistentTokenRepository` no longer accepts the logged-out token (and other devices per policy). Do not use `@WithMockUser` to prove `RememberMeServices` participated in login/logout: mock principals bypass real token issuance and validation.

When supporting multi-device authentication, test with at least two independent cookie jars. If the system aims to log out one device rather than all devices, verify the implementation's exact revocation scope.

### 11.3. Testing Browser Storage Headers

If using `Clear-Site-Data`, you can assert the response header:

~~~java
// Test fragment when the logout handler configures this header.
String header = out.getResponse().getHeader("Clear-Site-Data");
assertEquals("\"cache\", \"storage\"", header);
~~~

This is a fragment inside a test method having `out` and static import `assertEquals`. The assertion checks the sent header, **not whether the browser actually cleared storage**. Separate browser integration tests and impact review on offline data / multi-app origins are required.

## 12. Standalone Java 17: Why Deleting a Cookie with the Wrong Path Fails

The following program runs **with JDK 17 alone**. It models cookie identity as the tuple `(name, path, domain)`. This is a simplified model for understanding cookie deletion, not a `Set-Cookie` parser or full RFC/browser implementation (browser domain normalization, prefix rules, and public suffix policies are more complex).

Save `CookieDeletionScopeDemo.java`:

~~~java
public class CookieDeletionScopeDemo {

    record CookieKey(String name, String path, String domain) {}

    static String delete(CookieKey issued, CookieKey expired) {
        if (issued.equals(expired)) {
            return "REMOVED";
        }
        return "STILL_PRESENT";
    }

    public static void main(String[] args) {
        CookieKey session = new CookieKey("JSESSIONID", "/portal", "");
        CookieKey same = new CookieKey("JSESSIONID", "/portal", "");
        CookieKey wrongPath = new CookieKey("JSESSIONID", "/", "");
        CookieKey wrongName = new CookieKey("SESSION", "/portal", "");

        System.out.println("same: " + delete(session, same));
        System.out.println("wrong-path: " + delete(session, wrongPath));
        System.out.println("wrong-name: " + delete(session, wrongName));

        CookieKey rememberMe =
            new CookieKey("remember-me", "/", "example.test");
        CookieKey hostOnly =
            new CookieKey("remember-me", "/", "");

        System.out.println("domain-mismatch: " +
            delete(rememberMe, hostOnly));
    }
}
~~~

Compile and run:

~~~bash
javac CookieDeletionScopeDemo.java
java CookieDeletionScopeDemo
~~~

**Exact** stdout:

~~~text
same: REMOVED
wrong-path: STILL_PRESENT
wrong-name: STILL_PRESENT
domain-mismatch: STILL_PRESENT
~~~

In real browsers, `Max-Age=0` or a past `Expires` is the expiration signal. This model only illustrates why **name, path, and domain** must align; it does not simulate expiration time, browser domain matching, or cookie prefix constraints. More importantly, even when cookies are properly deleted, the server must still invalidate sessions and tokens/remember-me per policy.

## 13. Real-World Errors and Diagnostics

| Symptom | Possible cause | Diagnostic steps |
| --- | --- | --- |
| Logout returns 302 yet `/private` stays accessible | Session/context not invalidated; request carries another auth credential | Check `LogoutFilter`, `SecurityContextRepository`, remember-me, Bearer/SSO |
| `JSESSIONID` still appears in browser | `Set-Cookie` deletion used wrong name/path/domain, or browser didn't receive response | Compare before/after `Set-Cookie` and actual cookie scope |
| Cookie cleared yet login keeps restoring | remember-me cookie remains or SSO auto-logs in | Check `RememberMeServices` and IdP |
| Clicking logout returns 403 | POST missing/invalid CSRF token | Keep CSRF, send valid token; check repo and request |
| `GET /logout` does not log out | CSRF enabled; GET is typically a confirmation page | Use POST with CSRF |
| Logout affects only one tab; another tab still displays data | Frontend state/bfcache remains | Sync tabs, clear app cache, revalidate session |
| `XSRF-TOKEN` cookie remains/changes after logout | Different CSRF repository/renewal policy | Check `CsrfLogoutHandler` and token repo |
| `Clear-Site-Data` has no effect | Unsupported browser, non-secure HTTP, or mismatched scope | Test on HTTPS/supported browser; add frontend cleanup |
| `Clear-Site-Data` wipes another app's data | `cookies`/`storage` directive too broad | Narrow directives and review shared domain |
| After logout, user auto-logs in via OAuth2 SSO | Independent IdP session still valid | Design RP-initiated logout and SSO architecture |
| Device A logs out yet token on B still works | Only A's cookie cleared without revoking B's token | Distinguish local logout vs. logout everywhere |
| `CookieClearingLogoutHandler` used yet session remains alive | Only handles browser cookie | Ensure `SecurityContextLogoutHandler` executes |
| Sensitive response still visible on Back button | Browser bfcache/cache holds snapshot | `Cache-Control: no-store`, revalidation, and UI cleanup |
| Two cookies share the name `JSESSIONID` | Different `Path`/`Domain` | Check DevTools cookie table and `Set-Cookie` headers |
| Persistent remember-me still accepts token | Server repository token not revoked | Check `RememberMeServices.logout` and repo cleanup |

### Systematic Debugging Process

1. Verify the logout request hits the right **`SecurityFilterChain`** and matcher/HTTP method. With CSRF enabled, does the request carry a valid token?
2. Verify the server response (status, `Location`, `Set-Cookie`, `Clear-Site-Data` if used). Do not rely solely on UI appearance.
3. Ensure the old server session was invalidated or `SecurityContext` was cleared per policy. Test whether a new request with the old cookie/session remains authenticated.
4. Confirm remember-me services participated in logout; if persistent, check the token store and revocation scope.
5. Compare cookie name, `Path`, `Domain`, and `Secure`/host-only between the **issued cookie** and **deletion cookie**.
6. Identify which app keys, memory state, API caches, and multiple tabs the frontend holds.
7. If auto-login persists, identify the authentication source: remember-me, SSO IdP, another Bearer token, or proxy auth.
8. Test across different browsers, HTTPS, reverse proxies, context paths, and CORS/cookie `SameSite` as needed.
9. Never log or copy raw session IDs, remember-me tokens, JWTs, passwords, or user objects containing credentials into incident reports.

## 14. Self-Check Exercises

**Exercise 1.** An app calls `deleteCookies("JSESSIONID")` without invalidating `HttpSession`. What is missing?

**Answer:** Deleting the client cookie does not guarantee server-side session destruction. You need a logout handler clearing `SecurityContext` and invalidating the session per policy. A leaked or copied session ID must be rejected by the server.

**Exercise 2.** A browser was issued `JSESSIONID` with `Path=/portal`; the logout response only sends a deletion cookie for `Path=/`. Will the old cookie disappear?

**Answer:** You cannot assume it is deleted; name/path/domain must match the original cookie's scope. Inspect the issuance header and use the same `Path`/`Domain` when expiring it.

**Exercise 3.** After logout, the user visits `/private` and the app immediately recognizes them via remember-me. What went wrong?

**Answer:** The remember-me cookie/token may not have been canceled properly. Invalidating only the session is insufficient while remember-me remains active; integrate `RememberMeServices.logout` and proper token repository cleanup.

**Exercise 4.** Why does deleting a remember-me cookie in the browser not guarantee revocation of a stolen stateless token copy?

**Answer:** The server does not necessarily maintain per-token state for stateless tokens to invalidate them instantly. You need revocation policies, key rotation/password changes, or server-side tokens if the threat model demands it.

**Exercise 5.** An app uses cookie-based login with CSRF enabled. A developer switches logout to `GET /logout` for convenience. What is the risk?

**Answer:** It can introduce logout CSRF and conflict with the Spring Security flow. Use `POST /logout` with a valid CSRF token, and do not disable CSRF globally for cookie-based authentication.

**Exercise 6.** Why should you avoid sending `Clear-Site-Data: "cookies", "storage"` for every site on a shared domain?

**Answer:** Those directives can affect cookies of sibling apps and wipe shared offline/storage data. Evaluate scope and browser support; prefer minimal cleanup tailored to requirements.

**Exercise 7.** A user logs out, yet pressing browser Back still shows the old profile page. Does that prove the server is still authenticated?

**Answer:** No. The browser may display a cached/bfcache snapshot. Test a fresh request to a protected endpoint and configure caching/frontend handling per policy, without confusing stale UI with a live server session.

**Exercise 8.** A resource server authenticates Bearer JWTs, and the frontend removes the token from `localStorage` on logout. Is the issued token immediately invalid at the resource server?

**Answer:** Not by default. A JWT may remain valid until expiry or explicit architectural revocation. Logout must be designed specifically for access/refresh tokens and the authorization server.

**Exercise 9.** The frontend holds unsynced offline drafts. Should `localStorage.clear()` be called after logout?

**Answer:** Not by default. Clear authentication/sensitive keys belonging to the app while considering draft/offline data and user consent policies. Broad `storage` directives carry similar consequences.

**Exercise 10.** One window logs out successfully, yet another window on the same origin hasn't updated its UI. What is the solution?

**Answer:** Use `BroadcastChannel` or `storage` events to synchronize UI state and clear caches across tabs; however, the server must still invalidate sessions/revoke tokens to protect subsequent requests.

## 15. Secure Logout Implementation Checklist

- [ ] Identify whether the app uses session-based form login, remember-me, SSO, or Bearer tokens; do not apply one cookie logout recipe to every architecture.
- [ ] Ensure `LogoutFilter`, `SecurityContextLogoutHandler`, and the right logout handlers ran, cleaning server session/context per policy.
- [ ] Use `POST /logout` with a CSRF token when browsers rely on session cookies; never disable CSRF arbitrarily.
- [ ] Delete session cookies with the exact **name/Path/Domain**, verifying `Set-Cookie` responses in real browsers/HTTPS.
- [ ] If remember-me is enabled, verify `RememberMeServices.logout`, remember-me cookies, and persistent token repositories; distinguish token-based/stateless from persistent.
- [ ] Do not treat cookie deletion as token revocation; design all-devices logout separately if the product requires it.
- [ ] Understand `CsrfLogoutHandler` and `CookieCsrfTokenRepository` if using `XSRF-TOKEN`; ensure the frontend obtains fresh tokens at the right time.
- [ ] Use only appropriate `Clear-Site-Data` directives after reviewing impacts on shared domains, offline data, and browser support.
- [ ] Clean app state/cache/storage **selectively**; sync multi-tab UI; do not erase unrelated data.
- [ ] Protect APIs/private pages against inappropriate caching and test browser Back/bfcache behavior.
- [ ] Test login → remember-me → logout → new request, stale cookies, mismatched `Path`/`Domain` cookies, CSRF, multi-tab, and SSO/JWT if applicable.
- [ ] Never log credentials, JWTs, raw session IDs, remember-me tokens, or sensitive browser state.

**Conclusion:** Secure logout must combine **invalidating server-side authentication state**, **instructing the browser to expire the right cookies**, **canceling remember-me and revoking tokens per architecture**, and **selectively cleaning frontend data**. `deleteCookies("JSESSIONID")` is helpful yet does not invalidate sessions or remember-me tokens by itself; `Clear-Site-Data` is useful in certain systems yet is not a universally safe default for every website. Testing both server and browser with exact cookie scopes is how you verify a user is truly logged out.