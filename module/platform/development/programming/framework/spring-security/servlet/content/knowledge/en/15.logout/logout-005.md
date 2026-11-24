# `Clear-Site-Data` and Browser Support Limitations on Logout in Spring Security Servlet

## 1. Why Does Logout Also Need to Consider the Browser?

A user clicks **Log out** in a web application. On the server side, `HttpSession` has been invalidated, yet in the browser there may still remain cookies, caches of previous pages, `localStorage`, `sessionStorage`, `IndexedDB`, service workers, or rendered state in another tab. One mechanism to assist browser-side cleanup is the HTTP response header:

~~~http
Clear-Site-Data: "cache", "cookies", "storage"
~~~

**`Clear-Site-Data` is only a request from the server to the user agent.** How it is processed depends on the browser, version, directive, secure context, and device policies. This header **does not replace server-side session invalidation, refresh-token revocation, or revoking access permissions**.

This lesson focuses on **Spring Security Servlet**, topic **Logout**. After completing it, you will be able to:

- Explain accurately the purpose and syntax of `Clear-Site-Data` and the directives `"cache"`, `"cookies"`, `"storage"`, and `"executionContexts"`.
- Distinguish browser-side data clearing from server-side session/token invalidation.
- Identify limitations by browser, origin, cookie `Domain`, and sibling applications on the same site.
- Combine `POST /logout`, CSRF, `LogoutFilter`, `SecurityContextLogoutHandler`, cookie clearing, and `LogoutSuccessHandler`.
- Run a **Java 17+, Spring Boot 3.3.13, Spring Security 6** application using form login/session.
- Test using `curl`, `MockMvc`, and real browsers, knowing clearly what each tool proves.

The example uses demo credentials **learner / learn-pass** on localhost; never use them as production credentials.

## 2. Two Halves of Logout: Server-Side and Browser-Side

~~~text
Browser                               Spring Security Servlet
   |                                          |
   | POST /logout + CSRF token + cookie       |
   |----------------------------------------->|
   |                                    CsrfFilter
   |                                          |
   |                                    LogoutFilter
   |                                          |
   |                         clear SecurityContext
   |                         invalidate HttpSession
   |                         expire JSESSIONID cookie
   |                                          |
   |                         LogoutSuccessHandler
   |                         Clear-Site-Data header
   |                         HTTP 204 No Content
   |<-----------------------------------------|
   |                                          |
   | Browser may execute directives           |
   | if supported and HTTPS criteria met      |
   |                                          |
   | GET /me with old session                 |
   |----------------------------------------->|
   |               No longer authenticated    |
~~~

The **server-side** layer must ensure old credentials carry no privileges after logout. With session-based form login, that means **`invalidateHttpSession(true)`** and clearing `Authentication` in `SecurityContext`. If remember-me or refresh/access tokens exist, manage their lifecycles per your specific architecture; invalidating `HttpSession` alone does not automatically revoke tokens.

The **browser-side** layer can be asked to clear data groups via `Clear-Site-Data`, cookie expiration via `Set-Cookie`, and frontend app-state cleanup logic. These actions add privacy and UX value, yet must never serve as the sole evidence that logout is secure.

**Core invariant:** if the browser completely ignores `Clear-Site-Data`, any request using a destroyed `HttpSession` must still be rejected by the server. Conversely, if the browser deletes a token copy while that token remains valid on the server, an attacker holding a copy can still use it.

## 3. Syntax of the HTTP Response Header

The server sets the header on the **response** of a successful logout:

~~~http
HTTP/1.1 204 No Content
Clear-Site-Data: "cache", "cookies", "storage"
~~~

Directives are enclosed **in double quotes** and separated by commas. Do not confuse it with a client-sent request header or a JavaScript command capable of wiping data on arbitrary origins.

Examples of different directive sets:

~~~http
Clear-Site-Data: "cookies"
~~~

~~~http
Clear-Site-Data: "storage", "cache"
~~~

~~~http
Clear-Site-Data: "executionContexts"
~~~

The three blocks above are **three independent options** illustrating syntax, not three headers that must be sent simultaneously. The runnable example in this lesson uses **`"cache", "cookies", "storage"`**.

### Secure Context

`Clear-Site-Data` is tied to **HTTPS/secure context** requirements in browsers that implement it. Observing results on **`http://localhost`** is not enough to confirm production effectiveness; localhost may be treated as a trustworthy origin in some browsers, yet must not serve as proof of universal compatibility. Test on an **HTTPS origin** matching your production environment.

### Header Presence Differs from Actual Data Deletion

Four very different events:

1. The server produced a logout response.
2. The response contained a syntactically valid `Clear-Site-Data` header.
3. The browser received and was capable of executing the directives.
4. The intended data was actually deleted.

`curl`/`MockMvc` verify steps 1 and 2 well. Steps 3 and 4 must be tested in real browsers, by browser/version and data type.

## 4. Meaning of the Directives

| Directive | Browser-side request | Limitations and side effects |
| --- | --- | --- |
| **`"cache"`** | Clears browser caches scoped to the site/origin per implementation | Does not purge CDNs, reverse proxies, other origins' data, or screenshots |
| **`"cookies"`** | Clears cookies within the scope where the directive is implemented | Can affect cookies sharing a domain and sibling apps; support is inconsistent |
| **`"storage"`** | Clears web storage, `IndexedDB`, and related client storage areas per implementation | Can lose offline drafts; does not revoke tokens on the server |
| **`"executionContexts"`** | Requests refreshing/affecting open browsing contexts where browser supports it | Cannot rely on every tab auto-reloading; uneven support |
| **`"*"`** | Broadly requests clearing all supported data types | Should not be used by default; impacts many data types and UX |

The directive list and processing details can evolve across browser versions. Directives around prefetch/prerender or client hints may appear in specs depending on version; before using them, verify both **the targeted specification** and **behavior in supported browsers**.

### 4.1. `"cache"` Is Not `Cache-Control`

`Clear-Site-Data` `"cache"` asks the browser to clear applicable caches. It does **not** replace the response header:

~~~http
Cache-Control: no-store
~~~

For sensitive personal data, **`no-store`** should be applied at the time content is served; do not wait until logout to try deleting what was already cached. `Clear-Site-Data` does not fix CDN cache-key bugs, proxy caches, downloaded files, or tabs holding stale DOM.

### 4.2. `"cookies"` Requires Checking `Domain` and `Path`

Cookies do not share the same scoping rules as `localStorage`. Cookies can carry `Domain=example.com`, `Path=/`, `Secure`, `HttpOnly`, and `SameSite`; some cookies are shared across hosts on the same site.

Suppose you have:

~~~text
accounts.example.com
app.example.com
shop.example.com
~~~

If these apps use cookies on the parent domain, a site-scoped cookie-clearing request can reach beyond local logout. Do not assume the header always affects only cookies on **the `/logout` path itself**, or always affects only a single subdomain.

**Safe design:** terminate the server session, send `Set-Cookie` expiring specific cookies (exact name/`Path`/`Domain`), and use broad `"cookies"` only after evaluating the impact on related apps.

### 4.3. `"storage"` Can Lose Offline Data

Web Storage and `IndexedDB` typically hold **origin**-scoped data; PWA apps also have Cache Storage, service workers, and sync queues. Requesting `"storage"` cleanup may fit when data belongs to the logged-out account, yet it can also erase:

- Drafts not yet saved to the server.
- Offline data the user has not synced.
- Non-sensitive UI preferences or utilities.
- Application caches that must be re-downloaded on the next visit.

Do not add `"storage"` just because it sounds safer. Classify your data, decide what must be removed, define sync policies, and plan behavior for browsers that **do not support the directive**.

### 4.4. `"executionContexts"` Does Not Guarantee All Tabs Update Their UI

A user has tabs A and B open. Tab A logs out; tab B still displays the old username in its DOM. The `executionContexts` directive may be unsupported by the browser or may not behave as expected. Still, new API requests from tab B using the old session **must be rejected on the server**.

To improve multi-tab UI, apps can combine `BroadcastChannel`, `storage` events, focus-time refreshes, or account-status subscriptions. These are UX enhancements; server-side authorization checks remain the foundation.

## 5. Origin, Site, Cookie Scope, and SSO Systems

An **origin** is typically the tuple of scheme, host, and port. These addresses do not share the same origin:

~~~text
https://app.example.com
https://app.example.com:8443
https://login.example.com
http://app.example.com
~~~

**Site** and **cookie domain** are not strictly synonymous with origin. Hence each directive can have a different effective scope. Do not rely on a simplistic rule like “`Clear-Site-Data` always wipes exactly one origin” for all data, especially cookies.

### Logout at One App Is Not Global SSO Logout

If an app and an Identity Provider run on two origins or maintain separate sessions:

1. App A destroys its local `HttpSession`.
2. The browser may clear cookies/storage within supported scope.
3. The Identity Provider may still maintain its own **SSO session**.
4. Returning to app A, the user may be re-authenticated via SSO without typing a password.

If the goal is logging out across all federated logins, you need OIDC logout, refresh-token revocation, or session coordination per your identity product; `Clear-Site-Data` is not a cross-domain logout protocol.

### Data the Header Cannot Delete

`Clear-Site-Data` cannot revoke or delete:

- Tokens already copied to another device, origin, or attacker.
- Sessions still active in Redis/databases if the server did not revoke them.
- Screenshots, printouts, downloaded files, or emailed data.
- External CDN/proxy caches outside the browser.
- `localStorage`/`IndexedDB` belonging to other origins.
- Caches and storage of another browser on the same machine.

Never describe `Clear-Site-Data` as “erasing all user traces.”

## 6. Browser Support Limitations

`Clear-Site-Data` cannot be treated as a **universal** feature. Behavior depends on browser engine, version, directive, secure context, enterprise policies, and WebView/private-browsing modes.

| Environment | What to verify in practice | What not to assume |
| --- | --- | --- |
| Chrome/Edge and Chromium-based | Are cache, cookies, and storage processed over HTTPS? | One directive working means all directives work |
| Firefox | Does the browser/version support the expected directives? | Chromium results carry over identically |
| Safari macOS, Safari iOS/WebKit | Does receiving the header result in actual storage/cookie removal? | Full support just because the header appears in Network |
| Android System WebView, WKWebView | Does the WebView host/data store process the header? | Equivalent behavior to desktop browsers |
| Private browsing | Actual storage lifetime and clearing scope | Identical behavior to regular windows |
| Managed/enterprise browsers | Do administrative policies affect behavior? | Every user runs with default settings |

This is a **verification matrix**, not a promise that any specific version has 100% support. Never write security logic that requires the browser to succeed at cleanup; always maintain a safe server-side path if the header is ignored.

### Verification Technique

- Use **HTTPS** on a real test origin.
- Place harmless test keys into `localStorage`, `sessionStorage`, and if needed `IndexedDB`/Cache Storage.
- Before logout, record cookies, app storage, and session state.
- Send `POST /logout`, inspect the Network response for the header and exact double quotes.
- Inspect each storage/cookie type after logout; do not generalize from a single key.
- Request a protected resource again using the old session; confirm the server rejects it.
- Test two tabs; test the browsers/versions and devices officially supported by the product.
- Record **header present / client cleanup observed / server session invalid** as three independent criteria.

## 7. State-Cleanup Mechanisms Do Not Replace Each Other

| Mechanism | Handled by | Primary effect | Limitation |
| --- | --- | --- | --- |
| `invalidateHttpSession(true)` | Server | Destroys current `HttpSession` | Does not delete browser cache/`localStorage` |
| `clearAuthentication(true)` | Spring Security | Clears `Authentication` from context via logout handler | Does not revoke independent tokens |
| `deleteCookies("JSESSIONID")` | HTTP `Set-Cookie` / browser | Requests expiring a specific cookie | Requires matching `Path`/`Domain`; does not clear all cookies |
| `Clear-Site-Data` `"cookies"` | Supporting browsers | Clears cookies within directive scope | Can affect site-wide cookies |
| `Clear-Site-Data` `"storage"` | Supporting browsers | Clears client storage | Can lose offline data |
| `Clear-Site-Data` `"cache"` | Supporting browsers | Clears browser cache | Does not purge CDNs |
| `Cache-Control: no-store` | Browser/intermediaries | Restricts caching of sensitive responses | Not a session revocation command |
| Token/session revocation | Backend or identity provider | Prevents reuse of revoked credentials | Does not clear client UI/storage |
| App state reset / `BroadcastChannel` | Frontend | Updates UI and notifies logout across tabs | Does not replace server authorization |

**A sound logout requires at least safe server-side state**; client-side techniques supplement it per product needs.

## 8. Spring Security Servlet Logout Flow

With session-based form login and default CSRF:

~~~text
POST /logout
  |
  v
CsrfFilter verifies CSRF token for unsafe method
  |
  +-- missing/wrong --> HTTP 403, logout fails
  |
  v
LogoutFilter
  |
  v
SecurityContextLogoutHandler
  +-- clear Authentication/context
  +-- invalidate HttpSession
  |
  v
CookieClearingLogoutHandler (if configured)
  +-- expired Set-Cookie
  |
  v
LogoutSuccessHandler
  +-- Clear-Site-Data response header
  +-- HTTP 204 No Content
~~~

In Spring Security, use the `logout` DSL and standard handlers instead of writing a custom logout controller that removes a few session attributes.

A fragment:

~~~java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
    .logoutSuccessHandler((request, response, authentication) -> {
        response.setHeader("Clear-Site-Data",
            "\"cache\", \"cookies\", \"storage\"");
        response.setStatus(HttpServletResponse.SC_NO_CONTENT);
    })
);
~~~

The snippet above is a **fragment inside `SecurityFilterChain`**, not a standalone Java program. The complete project follows in the next section.

### Why Emit the Header Only on Logout?

If accidentally configured globally:

~~~http
GET /me
HTTP/1.1 200
Clear-Site-Data: "cookies", "storage"
~~~

then a supporting browser could wipe cookies/storage on every profile load, causing a login loop and data loss. Emit the header only on **intentional website-data clearing actions**, typically logout success or an authenticated account-deletion flow.

### What Is HTTP 204?

**204 No Content** signals that the request succeeded with no response body. For frontends that explicitly `POST /logout`, 204 is a clean choice; the frontend handles navigation to login/homepage. Never attempt to send a JSON body with 204. If using a 302 redirect instead, confirm the header sits on the exact response the browser processes.

### Why POST and CSRF?

With browser form login, session cookies are sent automatically. A GET URL that performs logout can be embedded, prefetched, or triggered unintentionally by third parties. When CSRF is enabled, logout should use **POST with a valid CSRF token**. In default configurations, `GET /logout` may lead to a confirmation page; do not confuse GET with a session-destroying action.

## 9. Runnable Java 17+ Project: Spring Boot Form Logout

We choose **form login/session** over HTTP Basic for clear verification: HTTP Basic clients may keep resending valid username/password on every request after logout, causing the server to re-authenticate even after invalidating the session.

The project exposes `GET /public`, `GET /csrf`, `GET /me`, the default `/login` page, and `POST /logout`. Successful login creates a session; logout invalidates the session and returns the header.

### 9.1. Directory Tree

~~~text
clear-site-data-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/clearsite/
    │   ├── ClearSiteDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/clearsite/
        └── ClearSiteLogoutTest.java
~~~

### 9.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>clear-site-data-demo</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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

This is the **complete `pom.xml`** with a valid build block, requiring no extra XML assembly. The Spring Boot parent manages compatible Spring Security versions for the chosen branch.

### 9.3. `ClearSiteDemoApplication.java`

~~~java
package com.example.clearsite;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ClearSiteDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClearSiteDemoApplication.class, args);
    }
}
~~~

### 9.4. `SecurityConfig.java`

~~~java
package com.example.clearsite;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
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
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learn-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public", "/csrf").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessHandler((request, response, authentication) -> {
                    response.setHeader(
                        "Clear-Site-Data",
                        "\"cache\", \"cookies\", \"storage\"");
                    response.setStatus(
                        HttpServletResponse.SC_NO_CONTENT);
                })
            );

        return http.build();
    }
}
~~~

Explanation:

1. **`UserDetailsService` + `BCryptPasswordEncoder`** provides a test account with a hashed password. Never store raw passwords in `UserDetails`.
2. **`formLogin`** enables username/password authentication and the default login page.
3. **`/public`** and **`/csrf`** are public; **`/me`** requires authentication.
4. CSRF is **not disabled**. `POST /login` and `POST /logout` must carry tokens.
5. **`invalidateHttpSession(true)`** is the core server-side step.
6. **`clearAuthentication(true)`** clears `Authentication` via logout handlers.
7. **`deleteCookies("JSESSIONID")`** sends a session-cookie deletion instruction via `Set-Cookie` matching the current config; verify `Path`/`Domain` if using a reverse proxy or custom cookie.
8. **`LogoutSuccessHandler`** emits `Clear-Site-Data` only after logout processing, returning status **204** with no body.
9. Sample passwords are for localhost only. Never use hardcoded credentials in production.

**Do not add `Clear-Site-Data` to a security header writer applied to every response.** Spring Security's filter runs on many URLs; if the header is sent routinely, the browser may continuously lose sessions/data.

### 9.5. `DemoController.java`

~~~java
package com.example.clearsite;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/csrf")
    public Map<String, String> csrf(
            @RequestAttribute("_csrf") CsrfToken token) {
        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken()
        );
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
~~~

`GET /csrf` lets a client sharing the session fetch the token needed to `POST` login/logout. In real systems, enforce **same-origin/CORS** controls so untrusted sites cannot read tokens, and tailor the endpoint to your frontend architecture. Never return session IDs, raw passwords, or hashes in responses.

## 10. Testing with `curl`: Verifying the Server, Not Emulating a Browser

Start the app:

~~~bash
mvn spring-boot:run
~~~

Default is `localhost:8080` when the port is free. The commands below are for bash with **`curl` and `jq`**; on Windows, use `curl.exe` and `ConvertFrom-Json`. Use only demo credentials.

### 10.1. Retrieve CSRF Token and Session Cookie

~~~bash
TOKEN=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')
~~~

This creates/updates the **cookies.txt** cookie jar in the current directory. Never commit cookie files containing real sessions to Git, tickets, or logs.

### 10.2. Log In via Form POST

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "username=learner" \
  --data-urlencode "password=learn-pass" \
  --data-urlencode "_csrf=$TOKEN" \
  http://localhost:8080/login
~~~

Expect a **302 redirect** after login matching default `formLogin` (redirect target depends on saved request and configuration). `curl` does not follow redirects automatically unless `-L` is passed.

### 10.3. Verify Logged-In Session

~~~bash
curl -i -b cookies.txt http://localhost:8080/me
~~~

Expect **200** and username `learner`; `/me` needs no extra password because it uses the `HttpSession` created on login.

### 10.4. Fetch a Fresh Token, Since Login May Rotate the CSRF Token

~~~bash
TOKEN=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')
~~~

### 10.5. Successful Logout

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "_csrf=$TOKEN" \
  http://localhost:8080/logout
~~~

Important lines in the response:

~~~http
HTTP/1.1 204
Clear-Site-Data: "cache", "cookies", "storage"
~~~

The server may also emit an expired `Set-Cookie` and security headers. Do not depend on header ordering or specific cookie attributes beyond what was configured/tested.

**`curl` does not process `Clear-Site-Data` like a browser.** Seeing the header in `curl` only proves the server sent it; `curl` does not clear `IndexedDB`, `localStorage`, or browser caches.

### 10.6. Reusing the Session After Logout

~~~bash
curl -i -b cookies.txt http://localhost:8080/me
~~~

Expect the old session not to authenticate; with default `formLogin`, anonymous requests are normally **redirected to `/login`**. Do not assert an API must return 401 in every config, as `formLogin`'s entry point differs from HTTP Basic.

### 10.7. `POST /logout` Missing CSRF

~~~bash
curl -i --request POST http://localhost:8080/logout
~~~

Expect **403** if CSRF protection is active and no valid token is supplied. `LogoutSuccessHandler` does not run, so the response must not emit `Clear-Site-Data` from the lesson's handler.

## 11. `MockMvc` Testing: Exact Header and Invalidated Session

Create **`src/test/java/com/example/clearsite/ClearSiteLogoutTest.java`**:

~~~java
package com.example.clearsite;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class ClearSiteLogoutTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResponseDoesNotClearData() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public-ok"))
            .andExpect(header().doesNotExist("Clear-Site-Data"));
    }

    @Test
    void csrfTokenCanBeRetrieved() throws Exception {
        mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isString());
    }

    @Test
    void logoutWithoutCsrfDoesNotRunSuccessHandler()
            throws Exception {

        mvc.perform(post("/logout"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist("Clear-Site-Data"));
    }

    @Test
    void validLogoutClearsServerSessionAndAddsHeader()
            throws Exception {

        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "learn-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"));

        mvc.perform(post("/logout").session(session).with(csrf()))
            .andExpect(status().isNoContent())
            .andExpect(header().string(
                "Clear-Site-Data",
                "\"cache\", \"cookies\", \"storage\""));

        assertTrue(session.isInvalid());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The tests prove:

- Regular GET requests are **not** mistakenly tagged with `Clear-Site-Data`.
- The `/csrf` endpoint returns token metadata.
- `POST /logout` missing CSRF receives **403**, never reaching the success handler.
- Successful form login creates an `HttpSession`, and `GET /me` with that session returns 200.
- Valid `POST /logout` returns 204 + the exact header, and **`MockHttpSession` is invalidated**.

**Limitation of `MockMvc`:** it does not run a browser engine, does not verify `localStorage`/`IndexedDB` deletion, and cannot replace testing in real Safari/Firefox/WebView. Never report “browser data was cleared” solely because `MockMvc` assertions passed.

## 12. Hands-On Real Browser Testing Over HTTPS

On a test HTTPS origin, populate harmless test data in the DevTools Console:

~~~javascript
localStorage.setItem("clear-test", "local-before");
sessionStorage.setItem("clear-test", "session-before");
~~~

If possible, also create a dedicated test cookie and a test `IndexedDB` database. Never put real passwords/tokens/PII in test values.

Verification sequence:

1. Open **Network** and **Application/Storage** in Developer Tools.
2. Log in to establish a session; observe the active `JSESSIONID`.
3. In tab A, submit a valid `POST /logout`.
4. Confirm the real HTTPS response includes **`Clear-Site-Data: "cache", "cookies", "storage"`**.
5. Inspect the test keys in `localStorage` and `sessionStorage`, `IndexedDB`, Cache Storage, cookies, and service worker registrations.
6. Open or keep tab B open before logout; confirm tab B may still show stale UI yet new protected requests **are rejected by the server**.
7. Test on real Chrome/Edge, Firefox, Safari, and WebViews supported by the product.
8. Record separate outcomes for **header present**, **browser cleanup observed**, **server session invalid**, along with OS/browser versions.
9. If data is not cleared in a given browser, never try to compensate by dropping session invalidation; add appropriate client fallbacks.
10. Test the impact on cookies of sibling apps on the same domain before enabling broad `"cookies"` in production.

Every browser/version needs empirical results; never assume Safari/WebKit or Firefox supports everything fully just because Chromium did.

## 13. Real-World Scenarios Easily Misunderstood

### 13.1. Pressing Back After Logout Still Shows the User Page

Browsers can show a DOM state or cached page snapshot from history/bfcache. That **does not prove** the server still allows reading fresh data. Set `Cache-Control: no-store` on sensitive data and design the app to refresh/validate the session when the page becomes active again.

### 13.2. Client Continues Sending HTTP Basic

HTTP Basic may resend raw username/password on later requests, causing the server to re-authenticate. `Clear-Site-Data` does not invalidate a user's password or automatically revoke Basic credentials. The demo uses form/session to avoid this confusion.

### 13.3. SSO Logs Back In Immediately

The IdP holds a session on another domain; local app logout does not revoke it. An SSO logout policy or corresponding identity logout protocol is required.

### 13.4. Cookie Clearing Breaks Another App's State

A cookie scoped to `example.com` may be shared by multiple apps. Before emitting `"cookies"`, verify the scope and accept or mitigate side effects rather than adding headers blindly.

### 13.5. Storage Clearing Destroys Offline PWA Data

If an app has unsynced `IndexedDB` data, clearing `"storage"` can cause data loss. Define UX/warnings/syncing before logout and establish a storage classification policy.

### 13.6. CDN Still Returns PII

The `Clear-Site-Data` header does not purge CDN caches. Fix `Cache-Control`, cache keys, and CDN rules; ensure servers enforce authorization on sensitive resources.

### 13.7. iOS WebView Does Not Clear Data

WebViews may use isolated data stores or handle headers differently from desktop browsers. Test on the actual WebView version and host app, or use platform APIs to manage data stores when architecture requires it.

### 13.8. Header Appears on Every Response

Caused by configuring a global header writer instead of a logout handler. In supporting browsers, every request may wipe cookies/storage. Move header emission strictly into the logout success flow.

## 14. Diagnosing Unexpected `Clear-Site-Data` Behavior

| Symptom | Common cause | Check / fix |
| --- | --- | --- |
| `curl` sees the header yet storage stays intact | `curl` is not a browser | Test in a real HTTPS browser |
| Header is present yet browser doesn't clear | Browser/version/secure context | Compatibility matrix, HTTPS |
| Chrome and Safari behave differently | Different engines and directive support | Test per version |
| Logout returns 403 | Missing or invalid CSRF | POST valid token with matching session |
| Logout returns an unexpected redirect | Default handler / different chain | Check `LogoutSuccessHandler` |
| Session invalidated yet user auto-logs back in | SSO/Basic/remember-me still active | Identify credential source |
| Cookie does not disappear | Mismatched deletion `Path`/`Domain` | Inspect `Set-Cookie` and session |
| Multiple apps get logged out | Shared-domain cookies were cleared | Review site/cookie scope |
| Offline drafts lost | `"storage"` cleared all app data | Sync before logout |
| Another tab still displays old user | DOM/bfcache/UI state | Broadcast + refresh + server enforcement |
| CDN still caches sensitive data | Header only instructs browsers | `Cache-Control`, CDN config |
| Old tokens still work | No server-side revocation/expiry | Revocation/token rotation |
| Header sent even on `GET /public` | Misplaced global configuration | Emit only on successful logout |

Debugging workflow: verify `POST /logout` reached the right chain; CSRF is valid; `LogoutFilter` invalidated the session; the response has the header; proxies did not strip it; the browser is on HTTPS; actual storage was cleared; and post-logout API calls fail with the old session.

## 15. Exercises and Answers

**Exercise A.** The server sends only `Clear-Site-Data: "cookies"` without invalidating `HttpSession`. Is logout guaranteed secure?

**Answer:** No. A browser might not clear cookies, or a session/token could have been copied. The server must invalidate/revoke active credentials.

**Exercise B.** Why does an HTTP response containing `Clear-Site-Data` fail to prove `localStorage` was cleared?

**Answer:** The browser might not support the directive, ignore it in an insecure context, or exhibit different behavior. Verify actual storage directly.

**Exercise C.** Apps A and B share a cookie with `Domain=example.com`. What is the risk if A's logout sends `"cookies"`?

**Answer:** Broad cookie clearing can wipe B's session or preferences, impacting SSO/UX. Inspect cookie scope first.

**Exercise D.** Does `Clear-Site-Data: "cache"` replace `Cache-Control: no-store` on PII responses?

**Answer:** No. `no-store` must protect sensitive responses at delivery time; `Clear-Site-Data` is a supplementary browser-side action at logout.

**Exercise E.** `POST /logout` without CSRF gets 403. Why is there no `Clear-Site-Data` header from the success handler?

**Answer:** `CsrfFilter` rejects the request before `LogoutFilter`/`LogoutSuccessHandler` runs.

**Exercise F.** `MockMvc` confirms the exact header and invalid `MockHttpSession`. Can you conclude Safari deleted `IndexedDB`?

**Answer:** No. `MockMvc` does not execute a browser. Test on real Safari/WebKit.

**Exercise G.** After logout, the client still sends `Authorization: Basic` with the valid password. Why can `/me` return 200?

**Answer:** The server re-authenticates raw credentials on the new request. Session logout does not invalidate Basic passwords.

**Exercise H.** Tab B still displays the old username. What should you check first to assess security risk?

**Answer:** Send a protected request using the old session/token to see if the server rejects it. Stale DOM may simply be cache/memory needing additional UI cleanup.

**Exercise I.** Why should you not set `Clear-Site-Data: "storage"` on every request?

**Answer:** Supporting browsers could continually wipe application state, causing data loss and login loops.

## 16. Implementation Checklist

- [ ] Understand that `Clear-Site-Data` is a **browser-side request**, not server-side token/session revocation.
- [ ] Invalidate `HttpSession` and clear `Authentication`; handle tokens/remember-me/SSO if present.
- [ ] Send cookie expiration with matching `Domain`/`Path` and verify browser execution.
- [ ] Emit `Clear-Site-Data` only on logout success or intentional site-data cleanup events.
- [ ] Quote every directive properly: `"cache"`, `"cookies"`, `"storage"`.
- [ ] Choose specific directives deliberately rather than defaulting to wildcard `"*"`.
- [ ] Use HTTPS in production and test in a secure context.
- [ ] Test across real browsers/OSes/versions; never promise identical support across Safari, Firefox, and Chromium.
- [ ] Include `MockMvc` tests for logout headers, invalid server session, CSRF denial, and normal responses lacking the header.
- [ ] Perform real browser tests for Cookies, `localStorage`, `sessionStorage`, `IndexedDB`, and Cache Storage.
- [ ] Audit cookies shared across multiple apps/subdomains before enabling `"cookies"`.
- [ ] Audit PWA/offline drafts and retained data before enabling `"storage"`.
- [ ] Configure `Cache-Control: no-store` for private responses and dedicated CDN policies.
- [ ] Handle other tabs / Back navigation appropriately while enforcing server-side session invalidation.
- [ ] Never log passwords, session cookies, tokens, or PII when debugging logout.

**Conclusion:** In Spring Security Servlet, **`Clear-Site-Data`** is a useful supplementary layer for logout, yet **browser support is limited and inconsistent**. Emit it on **successful logout responses** alongside `invalidateHttpSession`, `clearAuthentication`, and cookie clearing; revoke tokens/SSO sessions via their own protocols when needed. Consider logout secure only when **the server rejects reuse of revoked credentials**, while browser clearing of cache/cookies/storage must be verified over HTTPS across target browsers.
