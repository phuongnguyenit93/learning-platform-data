# SPA: Receiving, Sending, and Refreshing CSRF Tokens After Login or Logout

**Module:** Spring Security – Servlet  
**Topic group:** CSRF

## 1. Problem and Scope

In this lesson, **token** refers to the **CSRF token** (Cross-Site Request Forgery protection token), not an OAuth 2.0/OIDC access token, ID token, or refresh token. An SPA using **session-based login** typically receives a session cookie such as JSESSIONID; the browser automatically attaches matching cookies to requests. Hence a malicious page can try to make the browser send operations on behalf of the user. The CSRF token adds proof that a state-changing operation originated from the legitimate application.

The goal is to handle the entire lifecycle properly:

1. Before logging in, the SPA fetches a CSRF token from the server.
2. The SPA attaches the token in a header when sending the login POST or state-changing requests.
3. After successful login, the SPA **fetches a new token** because Spring Security may clear the old token.
4. Before logging out, the SPA sends the current token in the logout POST.
5. After successful logout, the SPA **fetches a new token** so the next login can proceed immediately.

If an application uses only a bearer access token actively added by JavaScript in the Authorization header, the CSRF model can differ. However, **every endpoint relying on auto-sent authentication cookies** must still be evaluated and protected against CSRF. Do not confuse refreshing a CSRF token with refreshing an OAuth access token.

## 2. How Does Spring Security Servlet Handle Tokens?

- **CsrfFilter** verifies tokens on state-changing requests; by default GET, HEAD, TRACE, and OPTIONS do not need tokens, while POST, PUT, PATCH, and DELETE require tokens. GET endpoints must not perform data-modifying operations.
- **CsrfTokenRepository** creates, saves, and loads the expected token. The common default for session-based servlet applications is HttpSessionCsrfTokenRepository. Another option is CookieCsrfTokenRepository.
- **CsrfTokenRequestHandler** decides how tokens are exposed to requests and how client-submitted tokens are read. Spring Security 6 uses XOR-masked token handling to mitigate leakage via response compression (BREACH).
- **Deferred token:** Spring Security can defer token creation/loading until needed. A bootstrap endpoint must genuinely access the token value, such as calling csrfToken.getToken(), so the token is generated and returned.
- **Authentication state changes:** CsrfAuthenticationStrategy clears the previous token upon successful authentication; CsrfLogoutHandler clears the token at logout. Therefore, the SPA must not continue using the old token after these two events.

A CSRF token **does not authenticate users**, does not determine roles, and does not replace authorization checks. Spring Security verifies CSRF and access permissions in separate steps.

## 3. Proper Request Sequence

| Moment | Request from SPA | CSRF token sent | What the SPA must do |
| --- | --- | --- | --- |
| Page open, not logged in | GET /api/csrf | Not needed | Obtain token and keep temporarily in memory |
| Log in | POST /api/login | Newly obtained token in header | Include session cookie if present |
| Login succeeds | GET /api/csrf | Not needed | **Replace old token** with new token |
| Business action | POST/PUT/PATCH/DELETE | Currently valid token | Send token in header |
| Log out | POST /api/logout | Currently valid token | Server clears session and old CSRF token |
| Logout succeeds | GET /api/csrf | Not needed | **Re-fetch token** for next login |
| Session expired/invalid token | Often gets HTTP 403 on wrong CSRF | Stale token | Reload token; decide whether to ask the user to retry |

Illustrative flow:

~~~text
SPA                       Spring Security (Servlet)
 |--- GET /api/csrf ------------------------>|
 |<-- 200 {headerName, token A} + session ---|
 |--- POST /api/login; CSRF: token A ------->|
 |<-- 204; token A is invalidated -----------|
 |--- GET /api/csrf ------------------------>|
 |<-- 200 {headerName, token B} -------------|
 |--- POST /api/data; CSRF: token B -------->|
 |<-- 200 -----------------------------------|
 |--- POST /api/logout; CSRF: token B ------>|
 |<-- 204; session/token B is cleared -------|
 |--- GET /api/csrf ------------------------>|
 |<-- 200 {headerName, token C} -------------|
~~~

A, B, and C are logical labels for valid tokens at each stage. Due to the XOR mechanism, **the returned token string may differ across two GET requests** even when the token stored in the repository has not changed; do not compare two response strings to assert that the session changed.

## 4. Runnable Example: Spring Boot 3 + Spring Security 6 + Session

The example runs with **Java 17+**, **Maven**, and Spring Boot **3.3.5**. This is a same-origin learning setup (SPA and API on the same host). In real usage, choose Spring Boot/Spring Security versions updated with appropriate patches. To reproduce the results, create the following files.

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>csrf-spa-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

**src/main/java/demo/DemoApplication.java**

~~~java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginProcessingUrl("/api/login")
                .successHandler((request, response, authentication) ->
                    response.setStatus(204))
                .failureHandler((request, response, exception) ->
                    response.sendError(401))
                .permitAll())
            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(204))
                .permitAll())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint((request, response, exception) ->
                    response.sendError(401)))
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    // Only for local testing on a personal machine. Do not hardcode real accounts.
    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("local-demo-pass"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @RestController
    static class Api {
        // Allowed to be called when unauthenticated and right after logging out.
        @GetMapping("/api/csrf")
        ResponseEntity<Map<String, String>> csrf(CsrfToken csrfToken) {
            return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                    "headerName", csrfToken.getHeaderName(),
                    "token", csrfToken.getToken()
                ));
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("username", authentication.getName());
        }

        @PostMapping("/api/data")
        Map<String, String> data(@RequestBody Map<String, String> body) {
            // Demo echo; does not write to a database.
            return Map.of("echo", body.getOrDefault("value", ""));
        }
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Configuration explanation:

- GET /api/csrf is permitted via permitAll so the SPA can bootstrap **before login and after logout**. By calling csrfToken.getToken(), the endpoint forces the deferred token to be generated/loaded. The no-store response discourages token caching.
- Spring Security maintains the session via cookies, handles POST /api/login with a form-urlencoded body containing username and password, returns 204 on success, and 401 on wrong credentials.
- POST /api/logout is processed by LogoutFilter and returns 204. This endpoint **is still subject to CSRF protection**.
- CSRF protection is kept enabled with default configuration; **do not use csrf.disable()**, nor exempt login/logout from CSRF.
- /api/me and /api/data require login. /api/data merely echoes back the received value; it illustrates a POST requiring a CSRF token, not a real data-persistence API.

## 5. SPA Code: Fetching Token, Sending Header, Refreshing After Both Events

Open a page on the same origin as the server (e.g., http://localhost:8080/login), then run this JavaScript snippet in the DevTools Console; or put it into a same-origin frontend module. Use fetch credentials: "same-origin" so the browser sends/receives session cookies for same-origin requests.

~~~javascript
let csrf = null;

async function loadCsrf() {
  const response = await fetch("/api/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("Failed to obtain CSRF token: " + response.status);
  }

  const data = await response.json();
  if (!data.headerName || !data.token) {
    throw new Error("CSRF response missing headerName or token");
  }
  csrf = { headerName: data.headerName, token: data.token };
  return csrf;
}

async function protectedPost(path, body, contentType) {
  if (!csrf) await loadCsrf();

  const headers = { [csrf.headerName]: csrf.token };
  if (contentType) headers["Content-Type"] = contentType;

  const response = await fetch(path, {
    method: "POST",
    headers,
    body,
    credentials: "same-origin"
  });

  if (response.status === 403) {
    csrf = null; // Token may be stale; do not automatically resend POST.
    throw new Error("HTTP 403: need to reload CSRF token and retry intentionally");
  }
  return response;
}

async function login(username, password) {
  await loadCsrf(); // Obtain a token even when the user has no session yet.
  const form = new URLSearchParams({ username, password });
  const response = await protectedPost(
    "/api/login",
    form,
    "application/x-www-form-urlencoded;charset=UTF-8"
  );
  if (!response.ok) {
    throw new Error("Login failed: " + response.status);
  }

  csrf = null;       // Spring Security may have cleared the pre-login token.
  await loadCsrf();  // Mandatory step before the next business POST.
}

async function postData(value) {
  const response = await protectedPost(
    "/api/data",
    JSON.stringify({ value }),
    "application/json"
  );
  if (!response.ok) {
    throw new Error("POST failed: " + response.status);
  }
  return response.json();
}

async function logout() {
  const response = await protectedPost("/api/logout");
  if (!response.ok) {
    throw new Error("Logout failed: " + response.status);
  }

  csrf = null;       // Old token was cleared during logout.
  await loadCsrf();  // Need a new token for the next login POST.
}
~~~

Run sequentially in the Console:

~~~javascript
await loadCsrf();
await login("learner", "local-demo-pass");
await postData("hello"); // {echo: "hello"}
await logout();
await login("learner", "local-demo-pass"); // Second login still works.
~~~

**Expected:** GET /api/csrf returns 200; valid login returns 204; POST /api/data returns 200 and JSON echo; logout returns 204. Do not print or hardcode specific tokens in examples because the value changes per request/session.

In real applications, manage csrf in a shared service; after successful login/logout, allow data-modifying requests to proceed only **after** the loadCsrf() Promise completes. If multiple tabs are open, an old tab's token may become invalid after another tab logs in/out; upon encountering 403, synchronize state and reload the token.

## 6. Alternative: SPA Reading the XSRF-TOKEN Cookie

Some SPAs (such as clients with built-in XSRF cookie support) receive the token via an **XSRF-TOKEN** cookie and send the cookie value in the **X-XSRF-TOKEN** header. In Spring Security 6, a token read directly from a cookie is an **unmasked value**, whereas the default XOR handler normally expects a masked representation; merely switching to CookieCsrfTokenRepository while keeping the default handler can result in 403.

If choosing the cookie approach, **replace** the csrf configuration in the example above with:

~~~java
.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()))
~~~

The snippet above requires importing CookieCsrfTokenRepository and the following handler file:

**src/main/java/demo/SpaCsrfTokenRequestHandler.java**

~~~java
package demo;

import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

public final class SpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();
    private final CsrfTokenRequestHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       Supplier<CsrfToken> csrfToken) {
        xor.handle(request, response, csrfToken);
        csrfToken.get(); // Force token/cookie to be ready for the SPA.
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request,
                                        CsrfToken csrfToken) {
        String header = request.getHeader(csrfToken.getHeaderName());
        return (StringUtils.hasText(header) ? plain : xor)
            .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

In **cookie mode**, the SPA calls GET /api/csrf to ensure the XSRF-TOKEN cookie has been issued (the JSON body can be ignored), then **reads the cookie** and sends that exact value in the X-XSRF-TOKEN header. After login/logout, call GET /api/csrf again and read the new cookie. Do not take the XOR token from the JSON in section 4's example and send it through this handler's raw-token header branch; the two transmission methods must be implemented consistently.

The XSRF-TOKEN cookie uses HttpOnly=false so JavaScript can read it; the **login session** cookie should still be HttpOnly, Secure over HTTPS, and configured with an appropriate SameSite. Being able to read the CSRF cookie does not grant login privileges to JavaScript. When the SPA and API are on different origins, the SPA's document.cookie cannot automatically read cookies belonging to the API's origin; usually a JSON endpoint flow or BFF design should be chosen instead of assuming cookies can be read cross-origin.

## 7. Why Refresh Tokens After Login/Logout?

**After login:** Spring Security typically changes the session identifier to prevent session fixation and uses CsrfAuthenticationStrategy to clear the previous CSRF token. If the SPA keeps the token used in POST /api/login and immediately sends POST /api/data, the subsequent request may receive **403 Forbidden** even though the user logged in successfully.

**After logout:** LogoutFilter clears the authentication context/session and CsrfLogoutHandler clears the CSRF token. If the SPA continues sending the pre-logout token for the next login POST, the request may receive 403. GET /api/csrf after logout must be callable while **anonymous**, because the user is unauthenticated at that moment.

Key distinction: **403 due to a missing/wrong/expired CSRF token** differs from **401 due to not being logged in** and **403 due to insufficient permissions**. Inspect the Network tab, response, and server logs before concluding the cause. Do not fix errors by disabling CSRF globally.

## 8. CORS, Cookies, and Deployment Environments

The main example uses **same origin** so CORS does not need to be enabled. If the SPA is at https://app.example.test and the API is at https://api.example.test:

- Configure CORS in Spring Security/Web MVC with a **specific origin**, allowing credentials, methods, and the required CSRF header; browsers will send an OPTIONS preflight in certain cases.
- Use fetch credentials: "include" when cookies are needed cross-origin; the server must return Access-Control-Allow-Credentials: true with Access-Control-Allow-Origin set to the specific origin, not `*`.
- CORS and SameSite address different parts of the problem: CORS controls JavaScript reading responses, SameSite affects whether the browser sends cookies, and CSRF tokens prove valid state-changing requests.
- Cross-site cookies usually require SameSite=None; Secure and HTTPS; browser third-party cookie blocking policies can make this unreliable. Same-site yet cross-origin setups also require separate cookie, CORS, and CSRF evaluation.
- Keep session cookies HttpOnly, use HTTPS, mitigate XSS via escaping/CSP, control redirects, and never write CSRF tokens, passwords, or authentication cookies to logs/analytics. CSRF tokens do not replace XSS defenses.

## 9. Common Errors and How to Diagnose Them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| POST /api/login returns 403 | Did not call GET /api/csrf; missing header or mismatched session cookie | Bootstrap token, send right header name and matching cookie/session |
| Login returns 204, next POST returns 403 | Still using pre-login token | Call GET /api/csrf and update token after successful login |
| Logout returns 403 | Sent DELETE/GET based on wrong assumption; missing CSRF on logout POST | Use POST /api/logout with current token |
| Cannot log back in right after logging out | Used token cleared during logout | Call GET /api/csrf after logout and before login POST |
| GET /api/csrf returns 401 | Bootstrap endpoint requires authenticated | Allow GET /api/csrf when anonymous |
| XSRF-TOKEN cookie present yet X-XSRF-TOKEN header gets 403 | Raw token from cookie mismatches default XOR mechanism | Use SPA handler supporting cookie headers or consistently choose the JSON endpoint approach |
| Fails only when separating frontend and API | CORS, credentials, SameSite, cookie domain/path, or HTTPS | Inspect Set-Cookie, Origin, preflight, and Cookie request headers in Network |
| 403 after switching accounts, session expiration, or in a second tab | Session/token rotated elsewhere | Refresh token and login state; let user decide whether to resubmit the action |

Do not automatically retry a POST with business side effects after a 403 error: the error response could be misinterpreted, or the request may have partially traversed infrastructure. For repeatable operations, use idempotency keys and dedicated retry rules.

## 10. Minimal Testing and Checklist

With the application running at localhost:8080, verify via the Network tab or the script in section 5:

1. GET /api/csrf when unauthenticated returns 200 with headerName/token.
2. POST /api/login **without a CSRF header** must be rejected (typically 403).
3. POST /api/login with a valid CSRF token and valid account returns 204.
4. After login call GET /api/csrf again, then POST /api/data with the newly received token returns 200.
5. POST /api/logout with a valid token returns 204; subsequent GET /api/me is no longer authenticated (in this example: 401).
6. GET /api/csrf when logged out returns 200; using the new token to POST /api/login succeeds.
7. Test omitting the session cookie, using an old token, opening multiple tabs, and expiring the session to confirm proper 403/401 handling.
8. Confirm GET does not mutate state, and HTTPS/cookie policy/CORS match the real environment.

**Rule to remember:** An SPA must have a CSRF token **before every state-changing request**, including login and logout. After **successful login** or **successful logout**, the pre-event token is no longer trustworthy: **reload the CSRF token from the server before sending the next operation**.