# TokenBasedRememberMeServices and signed cookies in Spring Security

## 1. Overview: remembering login does not mean keeping the session forever

When a user selects **Remember Me**, a website can allow them to return after their previous HTTP session has expired without re-entering their password immediately. The browser retains a cookie with a longer lifetime than the session; on a subsequent request, Spring Security inspects that cookie and builds an appropriate authentication object.

In **Spring Security Servlet**, there are two common approaches:

- **`TokenBasedRememberMeServices`**: issues a cookie carrying data and a hash-based signature computed from the username, expiry, server-stored password hash, and a secret key. No per-token database storage is required.
- **`PersistentTokenBasedRememberMeServices`**: issues a cookie and stores token records in `PersistentTokenRepository`, enabling token rotation and server-side record management/revocation.

This article focuses on **TokenBasedRememberMeServices and signed cookies**: how they work, how they plug into form login, key/cookie configuration, differences from sessions, automatic re-authentication, replay limitations, and tests.

Scope: **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet MVC**. The runnable example uses Maven with an in-memory learning account and MockMvc integration tests. For production, replace demo data with an appropriate user store and secrets management.

### Specific goals

1. Understand `RememberMeServices.loginSuccess`, `loginFail`, `autoLogin`, and where they are called.
2. Distinguish `UsernamePasswordAuthenticationFilter`, `RememberMeAuthenticationFilter`, `RememberMeAuthenticationProvider`, and `UserDetailsService`.
3. Read signed cookie structure accurately and understand that Base64 is not encryption.
4. Use the same signing key in the service and provider, avoid hard-coding secrets, and set sensible TTLs and cookie flags.
5. Verify that cookies are issued only on opt-in, reject tampered cookies, and block remember-me on endpoints requiring `fullyAuthenticated()`.
6. Recognize the security limitation: **a stolen cookie can be replayed before it expires**; clearing the current cookie on logout does not guarantee revoking copied tokens.

## 2. Comparing sessions, remember-me, and bearer tokens

| Criterion | HTTP session | Token-based remember-me | Bearer JWT |
| --- | --- | --- | --- |
| Client-held data | `JSESSIONID` cookie | Signed `APP_REMEMBER_ME` cookie | Usually `Authorization: Bearer ...` |
| Server handling | Looks up `HttpSession` / `SecurityContext` | Loads user, recomputes signature, authenticates remember-me token | Verifies JWT signature, expiry, issuer, audience |
| Long-lived server data | Session store | No separate remember-me token table | Can be stateless or have revocation mechanisms |
| Purpose | Maintain active session state | Recover identity after a previous session | API authentication via access token |
| Revocation | Invalidate session | Change password hash/key, expiry, or account status | Per TTL/revocation/introspection |
| Trust level | Can be an interactive login | Remembered identity, not a fresh login | Depends on token type/claims and policy |

**Example:** A user logs in today and selects remember me. The session expires after a few hours, while the remember-me cookie may stay valid for days. On the next visit, the server receives the remember-me cookie, verifies it, and establishes a new `Authentication`; it does not “resurrect” the expired session ID.

Remember-me is **not storing the password in the browser** and is **not a JWT**. The browser sends a time-bounded credential; the server verifies that credential. Cookie name, path, domain, SameSite, Secure, and HttpOnly must be properly designed.

## 3. Signed cookie structure

Spring Security 6.x documentation describes the logical payload as:

~~~text
base64(
    username + ":" +
    expirationTime + ":" +
    algorithmName + ":" +
    algorithmHex(
        username + ":" +
        expirationTime + ":" +
        password + ":" +
        key
    )
)
~~~

Meaning:

- `username`: user identifier recoverable via `UserDetailsService`.
- `expirationTime`: absolute expiration timestamp in **milliseconds since Unix epoch**.
- `algorithmName`: algorithm name used for the signature, e.g. `SHA256`.
- `password`: the value from `UserDetails.getPassword()` on the server, typically a **BCrypt/PasswordEncoder hash**, never a plaintext password sent to the client.
- `key`: application secret; the exact same value must be used across related remember-me components.
- `algorithmHex(...)`: hash digest formatted as hexadecimal.
- `base64(...)`: encoding for cookie transport, **not hiding data**.

An example format after Base64 decoding:

~~~text
student:1800000000000:SHA256:<signature-hex>
~~~

This is **illustrative shape data**, not a usable login cookie. A valid signature must be computed from the real server secret and data.

### Verification steps when receiving a cookie

~~~text
Browser sends Cookie: APP_REMEMBER_ME=...
                   |
                   v
RememberMeAuthenticationFilter
       (no Authentication on the request yet)
                   |
                   v
TokenBasedRememberMeServices.autoLogin(...)
       - locate and decode cookie
       - validate structure/expiry
       - UserDetailsService.loadUserByUsername(username)
       - check account status
       - recompute signature from password hash + key
       - compare signature
                   |
                   v
RememberMeAuthenticationToken
                   |
                   v
AuthenticationManager / RememberMeAuthenticationProvider
                   |
                   v
SecurityContext + authorization + controller
~~~

If the cookie's username, expiry, or signature is altered without recomputing a valid signature, the server rejects it. Because the expiration timestamp is included in the signed input, a client cannot extend a token by Base64-decoding and editing the expiry.

**Base64 provides no content confidentiality.** The username inside the cookie is readable. A non-expired cookie **can be sent from another device** if stolen; the signature prevents tampering, not replay from a different device.

### When does the lifetime start?

Token-based remember-me computes expiry from the **successful interactive login that issued the cookie**. Automatically re-authenticating via the remember-me cookie does not reissue a fresh cookie to extend the lifetime indefinitely by default. Spring Security defaults to **14 days**; the example below sets **7 days**.

Distinguish:
- `expirationTime` inside the payload: milliseconds, covered by the signature and checked on verification.
- `Cookie Max-Age`: seconds, instructing the browser how long to retain the cookie.
- Session timeout: a separate configuration that does not directly govern remember-me cookie lifetime.

### SHA-256 algorithm and legacy cookie compatibility

In Spring Security 6.5, there is a constructor:

~~~java
new TokenBasedRememberMeServices(
    key, userDetailsService, RememberMeTokenAlgorithm.SHA256);
~~~

`encodingAlgorithm` generates new signatures; `matchingAlgorithm` can verify legacy cookies that lack the algorithm field in their payload. Do not intentionally choose MD5 for new deployments just because legacy examples mention it. If migrating old cookies, evaluate and bound the compatibility window.

This format is Spring Security's signed-cookie solution; **there is no need to write a custom HMAC/JWT codec**. Never send the signing key to the frontend.

## 4. Coordinating components in the filter chain

`RememberMeServices` has three primary methods:

~~~java
Authentication autoLogin(
    HttpServletRequest request,
    HttpServletResponse response);

void loginFail(
    HttpServletRequest request,
    HttpServletResponse response);

void loginSuccess(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication successfulAuthentication);
~~~

| Component | When it runs | Responsibility |
| --- | --- | --- |
| `UsernamePasswordAuthenticationFilter` | User submits username/password form | Creates interactive authentication request |
| `AuthenticationManager`, `DaoAuthenticationProvider` | During password login | Checks password via `UserDetailsService` and `PasswordEncoder` |
| `RememberMeServices.loginSuccess` | After successful interactive login | Checks opt-in and issues remember-me cookie if appropriate |
| `RememberMeServices.loginFail` | After failed interactive login | May clear any remember-me cookie |
| `RememberMeAuthenticationFilter` | Request lacks authentication but carries remember-me cookie | Calls `autoLogin` and proceeds to authenticate the token |
| `RememberMeAuthenticationProvider` | When receiving `RememberMeAuthenticationToken` | Verifies the token against the remember-me mechanism key |
| `UserDetailsService` | When reloading the account | Provides current username/password hash/authorities |
| `LogoutFilter` + LogoutHandler | During logout | Deletes cookie and handles session/logout policy |
| `SecurityContextRepository` | When loading/saving context | Restores identity within request/session; does not replace remember-me signature |

### Interactive login

~~~text
POST /login
username=student&password=...&remember-me=on
            |
            v
UsernamePasswordAuthenticationFilter
            |
            v
DaoAuthenticationProvider: password valid?
            |
      +-----+------+
      |            |
   Invalid       Valid
      |            |
      v            v
loginFail(...)  loginSuccess(...)
      |            |
      v            v
401 + cookie    If opt-in: build signed cookie
cleared         200 + session + remember-me cookie
~~~

### Cookie-based login on a subsequent request

~~~text
GET /api/me
sends APP_REMEMBER_ME only, no old JSESSIONID
            |
            v
RememberMeAuthenticationFilter
            |
            v
TokenBasedRememberMeServices.autoLogin(...)
            |
            v
UserDetailsService + check signature/expiry/account
            |
            v
RememberMeAuthenticationProvider
            |
            v
Authenticated principal at remember-me level
            |
            v
Authorization evaluates endpoint rules
~~~

When using `http.rememberMe(...)` inside `SecurityFilterChain`, Spring Security wires the related mechanisms automatically. Avoid adding a separate standalone `RememberMeAuthenticationFilter` when already using the DSL, to prevent duplicate filter execution or mismatched managers.

## 5. Configuration choices to decide

| Setting | Role | Recommendation |
| --- | --- | --- |
| `key` | Secret used to create/verify tokens | Random, long, environment-separated, stored in a secrets manager |
| `UserDetailsService` | Reads current user/password hash | Same trusted user store used for authentication |
| `RememberMeTokenAlgorithm.SHA256` | Signature generation algorithm | Reference choice for Spring Security 6.5 |
| `setTokenValiditySeconds(...)` | Token/cookie TTL | Choose based on risk; 7 days in demo |
| `setParameter("remember-me")` | Opt-in field | Must match the form field name |
| `setAlwaysRemember(false)` | Do not auto-issue cookies | Default should respect opt-in |
| `setCookieName("APP_REMEMBER_ME")` | Cookie name | Choose a clearly identifiable name |
| `setUseSecureCookie(true)` | Send cookie only over HTTPS | Mandatory in production |
| `setCookieCustomizer(...)` | Add cookie attributes | `SameSite=Lax` per threat model |
| `setMatchingAlgorithm(...)` | Fallback for verifying legacy cookies | Keep SHA256 if not migrating legacy data |

**Keys must be consistent across nodes.** If server A issues cookies with key A while server B uses key B, users will experience erratic remember-me rejections behind a load balancer. Conversely, sharing **the same key between dev and production** is unsafe. Maintain a dedicated secure key per environment, managed centrally.

**Password hashes must also remain stable.** If a service re-`encode()`s the user's password every time it reads from the database, BCrypt generates a new salt, altering the hash and breaking signatures of previously issued cookies. Password hashes must be stored and loaded consistently until an intentional password change or rehash.

## 6. Complete Java 17 + Spring Boot 3.5 program

The demo provides:
- `POST /login`: form-urlencoded, username/password, and `remember-me=on` checkbox.
- `GET /api/csrf`: returns the CSRF token for clients.
- `GET /api/me`: shows username and the `rememberMe` flag.
- `GET /api/strong`: requires `fullyAuthenticated()`, not remember-me alone.
- `POST /logout`: logs out and clears the cookie via framework mechanics.

`REMEMBER_ME_KEY` is a required environment/property value. Production defaults to requiring `Secure` cookies; localhost HTTP should only override this deliberately.

### 6.1. Project layout and Maven

~~~text
signed-remember-demo/
├── pom.xml
└── src/
    ├── main/java/demo/remember/SignedRememberApplication.java
    └── test/java/demo/remember/SignedRememberApplicationTests.java
~~~

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>demo</groupId>
    <artifactId>signed-remember-demo</artifactId>
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

### 6.2. Main source code

File `src/main/java/demo/remember/SignedRememberApplication.java`:

~~~java
package demo.remember;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.rememberme.TokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme.TokenBasedRememberMeServices.RememberMeTokenAlgorithm;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SignedRememberApplication {

    public static void main(String[] args) {
        SpringApplication.run(SignedRememberApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // Demo: password hash is regenerated when the application restarts.
        // Production requires a database with persistently stored hashes.
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    TokenBasedRememberMeServices rememberMeServices(
            UserDetailsService users, Environment env) {

        String key = env.getRequiredProperty("REMEMBER_ME_KEY");
        boolean secureCookie = Boolean.parseBoolean(
            env.getProperty("APP_REMEMBER_ME_SECURE", "true"));

        TokenBasedRememberMeServices services =
            new TokenBasedRememberMeServices(
                key, users, RememberMeTokenAlgorithm.SHA256);

        services.setMatchingAlgorithm(RememberMeTokenAlgorithm.SHA256);
        services.setTokenValiditySeconds(7 * 24 * 60 * 60);
        services.setParameter("remember-me");
        services.setAlwaysRemember(false);
        services.setCookieName("APP_REMEMBER_ME");
        services.setUseSecureCookie(secureCookie);

        // Spring Boot 3.5 supports Servlet 6 Cookie attributes.
        services.setCookieCustomizer(
            cookie -> cookie.setAttribute("SameSite", "Lax"));

        return services;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            TokenBasedRememberMeServices rememberMeServices,
            Environment env) throws Exception {

        String key = env.getRequiredProperty("REMEMBER_ME_KEY");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/strong")
                    .fullyAuthenticated()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginProcessingUrl("/login")
                .successHandler((request, response, auth) -> {
                    response.setStatus(HttpServletResponse.SC_OK);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.getWriter().write(
                        "{\"status\":\"authenticated\"}");
                })
                .failureHandler((request, response, error) -> {
                    response.setStatus(
                        HttpServletResponse.SC_UNAUTHORIZED);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.getWriter().write(
                        "{\"error\":\"login_failed\"}");
                })
                .permitAll()
            )
            .rememberMe(remember -> remember
                .key(key)
                .rememberMeServices(rememberMeServices)
            )
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (request, response, error) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)
            ))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            // Do not disable CSRF for cookie-based form login.
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessHandler((request, response, auth) ->
                    response.setStatus(
                        HttpServletResponse.SC_NO_CONTENT))
            );

        return http.build();
    }

    @RestController
    static class Api {

        private final AuthenticationTrustResolver trust =
            new AuthenticationTrustResolverImpl();

        @GetMapping("/api/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());
            return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken());
        }

        @GetMapping("/api/me")
        Map<String, Object> me(Authentication authentication) {
            return Map.of(
                "username", authentication.getName(),
                "rememberMe", trust.isRememberMe(authentication));
        }

        @GetMapping("/api/strong")
        Map<String, String> strong() {
            return Map.of("status", "interactive-login");
        }
    }
}
~~~

### 6.3. Key takeaways from the configuration

**Key from environment:** `Environment.getRequiredProperty("REMEMBER_ME_KEY")` prevents the application from starting if the key is missing. Never hard-code secrets in code. In tests, the property is set separately via `@SpringBootTest(properties=...)`; production uses a secret store or environment variables.

**Service and provider share the key:** the same `key` is passed to `TokenBasedRememberMeServices` and the `rememberMe(...).key(key)` DSL. Do not use two different keys between service and provider.

**Form login issues the cookie:** `formLogin` uses Spring Security's standard filter; after successful authentication, the `RememberMeServices.loginSuccess` hook runs and issues the cookie when `remember-me=on` is present in the form. The success handler only writes JSON and does not forge remember-me tokens manually.

**Scoped cookie with clear TTL:** `setTokenValiditySeconds(604800)`, cookie name `APP_REMEMBER_ME`, `HttpOnly` by default, `SameSite=Lax` via the Servlet cookie customizer. `APP_REMEMBER_ME_SECURE` defaults to `true`; only set `false` when running local HTTP demos.

**Do not confuse remembered and full login:** `GET /api/me` returns the `rememberMe` flag via `AuthenticationTrustResolver`; `GET /api/strong` uses `fullyAuthenticated()` to require interactive login when only the remember-me cookie is present.

**CSRF and logout:** because browsers attach cookies automatically, CSRF remains enabled. Logout is delegated to the DSL and built-in LogoutHandlers, including clearing the remember-me cookie in the browser.

**A limitation of in-memory users:** BCrypt generates a random salt when the app restarts, resulting in a different password hash; cookies signed with the earlier hash are invalidated. This is a side effect of the demo, not a mandatory token rotation mechanism on every restart.

## 7. Manual testing with curl

### 7.1. Preparing the key and running the application

In a Bash terminal on localhost, with JDK 17+, Maven, and OpenSSL installed:

~~~bash
export REMEMBER_ME_KEY="$(openssl rand -hex 32)"
export APP_REMEMBER_ME_SECURE=false
mvn spring-boot:run
~~~

`openssl rand -hex 32` generates 32 random bytes formatted as 64 hex characters. Note: **only** use `APP_REMEMBER_ME_SECURE=false` in a local HTTP demo; production must use HTTPS and Secure cookies.

On Windows PowerShell, set both environment variables via an appropriate secret generation mechanism, then run `mvn spring-boot:run`. In production, share the same key across instances and do not change it arbitrarily while cookies remain valid.

### 7.2. Fetching the CSRF token

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
~~~

Expected JSON shape:

~~~json
{"headerName":"X-CSRF-TOKEN","token":"<actual-token-value>"}
~~~

Keep the session cookie in `cookies.txt` and extract the real token from the response. Do not send the placeholder literally.

### 7.3. Logging in with remember-me checked

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'X-CSRF-TOKEN: <actual-token-value>' \
  --data-urlencode 'username=student' \
  --data-urlencode 'password=demo-password' \
  --data-urlencode 'remember-me=on' \
  http://localhost:8080/login
~~~

Expected result `200 OK` with body:

~~~json
{"status":"authenticated"}
~~~

You should see `Set-Cookie: APP_REMEMBER_ME=...` with `Max-Age=604800`. This cookie is a signed token; never put real values into logs or documentation. Attribute and header ordering varies by container/browser.

### 7.4. Logging in without remember-me checked

Use a clean cookie jar and omit `--data-urlencode 'remember-me=on'`. Login can still succeed and establish a normal session, but no **new remember-me cookie** should be issued. If the browser still holds an old cookie from a prior login, clear old cookies before testing to avoid confusion.

### 7.5. Verifying auto-login without JSESSIONID

Send only `APP_REMEMBER_ME` from the opt-in login request:

~~~bash
curl -i \
  -H 'Cookie: APP_REMEMBER_ME=<issued-cookie-value>' \
  http://localhost:8080/api/me
~~~

Expected:

~~~json
{"username":"student","rememberMe":true}
~~~

Conversely, if using the valid session cookie right after interactive login, `/api/me` normally returns `rememberMe=false`.

### 7.6. Sensitive endpoint and logout

~~~bash
curl -i \
  -H 'Cookie: APP_REMEMBER_ME=<issued-cookie-value>' \
  http://localhost:8080/api/strong
~~~

Remember-me alone **does not satisfy** `fullyAuthenticated()`, so the endpoint requires interactive re-authentication. With the API entry point in this example, expect HTTP 401.

Interactive logout uses `POST /logout` and the current CSRF token:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'X-CSRF-TOKEN: <current-csrf-token>' \
  -X POST http://localhost:8080/logout
~~~

Expected `204 No Content` from the logout success handler. Fetch the CSRF token again after login if the old token was rotated. Logout can delete the remember-me cookie in the browser, but **does not revoke stolen cookie copies** in a signed-token design lacking a revocation store.

## 8. Integration testing with MockMvc

Testing only `UserDetailsService` or Base64 decoding does not prove remember-me is actually wired into the filter chain. The following tests exercise opt-in login, non-opt-in login, cookie-only auto-login, expiry tampering resistance, remembered state, and CSRF.

Create `src/test/java/demo/remember/SignedRememberApplicationTests.java`:

~~~java
package demo.remember;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "REMEMBER_ME_KEY=integration-test-secret-only",
    "APP_REMEMBER_ME_SECURE=false"
})
@AutoConfigureMockMvc
class SignedRememberApplicationTests {

    @Autowired
    MockMvc mvc;

    private MvcResult login(boolean remember) throws Exception {
        var request = post("/login")
            .with(csrf())
            .param("username", "student")
            .param("password", "demo-password");
        if (remember) {
            request.param("remember-me", "on");
        }
        return mvc.perform(request)
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("authenticated"))
            .andReturn();
    }

    private Cookie signedCookie() throws Exception {
        Cookie cookie = login(true).getResponse()
            .getCookie("APP_REMEMBER_ME");
        assertNotNull(cookie);
        return cookie;
    }

    @Test
    void optInIssuesCookieWithExpectedLifetime() throws Exception {
        Cookie cookie = signedCookie();
        assertEquals("APP_REMEMBER_ME", cookie.getName());
        assertTrue(cookie.isHttpOnly());
        assertEquals(7 * 24 * 60 * 60, cookie.getMaxAge());
        assertFalse(cookie.getValue().isBlank());
    }

    @Test
    void noOptInDoesNotIssueNewCookie() throws Exception {
        MvcResult result = login(false);
        assertNull(result.getResponse().getCookie("APP_REMEMBER_ME"));
    }

    @Test
    void interactiveSessionIsNotRememberMe() throws Exception {
        MvcResult login = login(true);
        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"))
            .andExpect(jsonPath("$.rememberMe").value(false));

        mvc.perform(get("/api/strong").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void rememberedCookieAuthenticatesWithoutOldSession()
            throws Exception {
        Cookie cookie = signedCookie();

        // Do not pass JSESSIONID or session from the previous login.
        mvc.perform(get("/api/me").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"))
            .andExpect(jsonPath("$.rememberMe").value(true));
    }

    @Test
    void rememberMeCannotEnterFullyAuthenticatedEndpoint()
            throws Exception {
        mvc.perform(get("/api/strong").cookie(signedCookie()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void tamperedExpiryDoesNotPassSignatureCheck() throws Exception {
        Cookie issued = signedCookie();
        String raw = new String(
            Base64.getDecoder().decode(issued.getValue()),
            StandardCharsets.UTF_8);
        String[] parts = raw.split(":", -1);

        assertEquals(4, parts.length);
        parts[1] = Long.toString(
            Long.parseLong(parts[1]) + 5_000L);

        String forged = Base64.getEncoder().encodeToString(
            String.join(":", parts).getBytes(StandardCharsets.UTF_8));

        mvc.perform(get("/api/me").cookie(
                new Cookie("APP_REMEMBER_ME", forged)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void malformedCookieIsRejected() throws Exception {
        mvc.perform(get("/api/me").cookie(
                new Cookie("APP_REMEMBER_ME", "invalid")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void badPasswordNeverIssuesUsableRememberMeCookie()
            throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "wrong")
                .param("remember-me", "on"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        Cookie cookie = result.getResponse()
            .getCookie("APP_REMEMBER_ME");

        // loginFail may return a deletion cookie with Max-Age=0.
        assertTrue(cookie == null || cookie.getMaxAge() == 0);
    }

    @Test
    void csrfIsRequiredForInteractiveLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "demo-password")
                .param("remember-me", "on"))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Expected:** 9 tests pass when dependencies and configuration match the example. This is test code for learners to execute; it is not an observed run result from a production project.

Notable points:
- `rememberedCookieAuthenticatesWithoutOldSession` sends only the remember-me cookie, avoiding confusion with an active session.
- `tamperedExpiryDoesNotPassSignatureCheck` alters **the signed expiry field** while keeping the signature, so it must be rejected.
- The failed-login test does not strictly assert “no Set-Cookie”, because `loginFail` may emit a **deletion** cookie with `Max-Age=0`.
- The `fullyAuthenticated()` endpoint test confirms a remembered principal is not equivalent to a fresh interactive login.

In a real application, add tests for key rotation, password hash updates, user locking, expiration under simulated time, logout, and multi-node behavior.

## 9. Biggest limitation: stolen-cookie replay

**Signatures protect integrity, not against replay of a stolen cookie.**

~~~text
Day 1: User logs in, receives cookie C valid for 7 days.
Day 2: Attacker copies cookie C.
Day 3: User logs out; browser deletes C.
Day 4: Attacker sends the copy of C to the server.
       If C has not expired and key/password hash/account remain valid,
       token-based service may still accept C.
~~~

With token-based remember-me, the system has no unique token record to mark copy C as “revoked”. Ways to invalidate it include:
- Waiting for the cookie to expire.
- Changing the account's password hash, e.g., changing the password.
- Changing the signing key (invalidating **all** cookies signed with the old key).
- Disabling/locking the account via user-status checkers and policies.
- Switching to a persistent-token/revocation design if per-device handling is needed.

Do not treat `HttpOnly`, `Secure`, or `SameSite` as revocation measures. They reduce some cookie-leak or risky-send vectors, but do not render a stolen copy useless.

## 10. Token-based vs. persistent-token: when to choose which?

| Characteristic | TokenBasedRememberMeServices | PersistentTokenBasedRememberMeServices |
| --- | --- | --- |
| Remember-me token database? | No | Yes (`PersistentTokenRepository`) |
| Operational footprint | Lightweight | Requires schema/cleanup and token state |
| Creation/verification | Hash-signature from username/expiry/password hash/key | Token series/value checked against repository |
| Clears cookie on logout | Yes | Yes |
| Revoke a specific stolen token | No dedicated stateful mechanism | Can manage tokens/series server-side |
| Requires UserDetailsService | Yes | Yes |
| Best suited for | Low-to-medium risk websites with modest TTLs | Systems needing stronger tracking and revocation |

Persistent tokens are not “zero-risk”: they require database management, rotation, lifecycle rules, reuse detection, and multi-node synchronization. When security requirements are very strict, consider **disabling remember-me** for those accounts or resources.

## 11. Authn trust level and access control

A remembered user may hold `ROLE_USER` and still be barred from transferring funds or changing sensitive information. Spring Security distinguishes `isRememberMe(Authentication)` from fully authenticated cases. Therefore:

~~~java
// Illustrative configuration snippet inside SecurityFilterChain:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/profile").authenticated()
    .requestMatchers("/payments/**").fullyAuthenticated()
    .anyRequest().denyAll());
~~~

`fullyAuthenticated()` does not prove MFA was completed, does not guarantee the authentication is “recent” in time, and does not replace ownership/tenant checks. For sensitive operations, design appropriate step-up authentication and authorization.

The remember-me filter only helps reconstruct identity; the system **still** must check authorities and resource permissions.

## 12. Keys, cookie security, and production operations

### Keys and hashes

- Keys must have high entropy, be separated per environment, and never be committed to repositories.
- Clustered instances must use consistent keys. Differing keys cause random auto-login failures.
- Key rotation invalidates cookies signed with the old key; prepare UX requiring re-login.
- Changing the password hash invalidates old cookies; this is generally desirable when users change passwords.
- If `loadUserByUsername` generates a new BCrypt hash on every call instead of reading a DB-stored hash, tokens will be unstable. In-memory demos rehash on **application restart**, so cookies from an earlier run may also become invalid.

### Cookies

- `Secure`: send only over HTTPS; must be enabled in production.
- `HttpOnly`: reduces the risk of JavaScript reading the cookie directly, though XSS can still issue requests with cookies attached automatically.
- `SameSite`: helps mitigate certain CSRF scenarios; does not replace CSRF tokens.
- `Path/Domain`: scope tightly, avoiding sending cookies to untrusted subdomains.
- `Max-Age`: is a browser hint, not a substitute for server-side signed expiration verification.
- Never write raw `Cookie` or `Set-Cookie` headers into access/trace logs.

### CSRF and CORS

Browsers send cookies automatically within scope, so remember-me applications still require CSRF protection per threat model. Form login and logout are state-changing actions; do not disable `csrf` merely because JSON is used.

In separate-origin SPAs, distinguish `SameSite`, CORS allowlists, and `fetch credentials`. Never combine `Access-Control-Allow-Origin: *` with credentials; never enable `SameSite=None` unconditionally.

### Sessions

Remember-me does not make sessions permanent. Session IDs are still issued by the Servlet container with their own timeout and rotation/fixation protections. A request carrying only a remember-me cookie can be used by Spring Security to rebuild context, after which the application may create a new session depending on configuration. Test sessions and cookies separately.

## 13. Common errors and diagnostics

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Login succeeds yet no remember-me cookie | Forgot `remember-me=on`, service not wired to filter, success did not complete | Check opt-in and `http.rememberMe` DSL |
| Cookie exists in browser yet request omits it | Secure on HTTP, wrong domain/path, SameSite/CORS | Inspect request headers and cookie scope |
| Request sends cookie yet gets 401 | Wrong key, expired token, password hash changed, user disabled | Match key, expiry, UserDetailsService |
| Works intermittently across multiple nodes | Different signing keys across instances | Synchronize secret across cluster |
| Cookie breaks after every demo restart | In-memory BCrypt re-encodes hash | Use persistent user store in real operations |
| Forgot to uncheck or old cookie lingers | Non-opt-in login does not clear all existing cookies as expected | Test with clean cookie jar, define UX |
| Cookie with tampered expiry still returns 200 | Another session is authenticated; test wasn't truly cookie-only | Drop JSESSIONID and modify the signed field |
| Still allowed in after logout | Another session active or cookie copy unrevoked | Check session and difference between cookie deletion vs. revocation |
| Sensitive endpoint does not ask for re-login | Configured only `authenticated()` | `fullyAuthenticated()` / step-up auth |
| 403 on login | Missing/invalid CSRF token | Keep session cookie, fetch fresh token, send proper header |
| Token valid yet permissions wrong | Inconsistent UserDetailsService/authority mapping | Check authorities loaded from server |
| Every user remembered without asking | `alwaysRemember=true` | Set false and provide checkbox |
| Key appears in source/logs | Poor secrets management | Move to secret store, rotate key, audit |

## 14. Security and testing checklist

- [ ] Issue remember-me cookies only after **successful interactive login** and clear opt-in.
- [ ] Secret key is long, secure, stable across nodes, and separated across dev/staging/prod.
- [ ] `TokenBasedRememberMeServices` and `RememberMeAuthenticationProvider` use a consistent key.
- [ ] Use an appropriate algorithm (e.g., SHA-256) and bounded TTL.
- [ ] `UserDetailsService` loads the current password hash rather than randomly rehashing per request.
- [ ] Locked/disabled accounts cannot auto-login via non-expired cookies.
- [ ] Cookie `Secure` under HTTPS, `HttpOnly`, `SameSite`, and domain/path are reviewed.
- [ ] CSRF protection remains active for cookie-authenticated requests.
- [ ] Tests distinguish session login from cookie-only remember-me.
- [ ] Tests cover tampered expiry/signature, invalid cookies, no opt-in, failed login, and logout.
- [ ] Require re-auth/step-up for sensitive endpoints rather than checking `authenticated()` alone.
- [ ] Never log signing keys, password hashes, or Cookie / Set-Cookie headers carrying credentials.
- [ ] Have a plan for cookie theft: password reset/key rotation or persistent tokens.
- [ ] Account for existing cookie volume when rotating keys/algorithms during rollouts.
- [ ] Do not reimplement the signing algorithm or build a custom JWT decoder for this cookie.

## 15. Self-check questions

1. Why does `TokenBasedRememberMeServices` need `UserDetailsService`?
2. Why doesn't Base64 protect the confidentiality of the username inside the cookie?
3. What capability does including the expiry field inside the signature provide?
4. When are `loginSuccess`, `loginFail`, and `autoLogin` invoked?
5. Why must `RememberMeAuthenticationProvider` use the same key?
6. Why does changing the password hash invalidate old tokens?
7. Is clearing the browser cookie on logout enough to revoke a stolen token?
8. Why can a principal with `ROLE_USER` still be rejected at `fullyAuthenticated()`?
9. Can Secure/HttpOnly/SameSite cookie flags replace CSRF protection?
10. When is `PersistentTokenBasedRememberMeServices` more appropriate?
11. Why must remember-me tests omit JSESSIONID?
12. What happens when nodes behind a load balancer use different keys?

## 16. References

1. Spring Security 6.5 — Remember-Me Authentication, signed cookies and persistent tokens: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
2. Spring Security 6.5 API — `TokenBasedRememberMeServices`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/TokenBasedRememberMeServices.html
3. Spring Security 6.5 API — `AbstractRememberMeServices` (cookie, opt-in, TTL, Secure, LogoutHandler): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/AbstractRememberMeServices.html
4. Spring Security 6.5 API — `RememberMeAuthenticationFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/RememberMeAuthenticationFilter.html
5. Spring Security 6.5 API — `RememberMeAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/RememberMeAuthenticationProvider.html
6. Spring Security 6.5 — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
7. Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
8. Spring Security 6.5 — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html

**Conclusion:** `TokenBasedRememberMeServices` helps re-identify users via a **signed cookie** once the old session is gone, but that cookie is a bearer credential that can be replayed if stolen. Use strong keys, explicit TTLs, opt-in, cookie security, and require fresh interactive login for sensitive actions; choose persistent tokens or another revocation mechanism when per-device control is needed.