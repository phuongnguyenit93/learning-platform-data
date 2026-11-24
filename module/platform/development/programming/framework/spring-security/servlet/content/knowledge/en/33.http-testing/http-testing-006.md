# Verifying authenticated, unauthenticated, Status, Headers, and Redirects in Spring Security Servlet

## 1. Lesson Objectives

When testing HTTP security in **Spring Security Servlet** with **Spring MVC** and **MockMvc**, verifying that an endpoint returns 200 is not enough. A proper test case must answer at the same time: is the request **authenticated**, is it **authorized**, what is the HTTP **status**, are the **response headers** correct, and where will the browser/API client be **redirected**?

An important distinction: **Spring Security's `Authentication`** is the security state inside the request, whereas **HTTP status, headers, and `Location`** are the communication output sent to the client. They are related, not synonymous.

For example:
- Unauthenticated user calling an HTTP Basic API: usually **401 Unauthorized**, with **WWW-Authenticate**.
- Logged-in user lacking `ROLE_ADMIN`: usually **403 Forbidden**.
- Unauthenticated user opening a web page requiring a login session: usually **302 Found** with **Location: /login**.
- User logging in successfully via form: usually **302** to the target page.
- Client sending a request to a public endpoint: can be **200** even **without a real user's `Authentication`**.

This lesson helps you build reliable tests for these cases, understand **spring-security-test** utilities, interpret MockMvc results, verify both **authenticated/unauthenticated** and **status/headers/redirects**, and distinguish a mock-user test from a real authentication test.

## 2. Distinguishing Four Dimensions to Test

| Dimension | Question | Testing tool |
| --- | --- | --- |
| **Authentication** | Has Spring Security authenticated the request, and as which user? | **`authenticated()`**, **`unauthenticated()`**, **`@WithMockUser`**, **`user()`**, or actually going through Basic/form login |
| **Authorization** | Is this user permitted for the required resource/role/scope? | Verify **200/403** and response payload; test multiple authorities |
| **HTTP status** | Which HTTP status code does the client receive? | **`status().isOk()`**, **`isUnauthorized()`**, **`isForbidden()`**, **`is3xxRedirection()`** |
| **Headers/redirect** | Does the response have the right challenge, cache directives, `Location`, and `Content-Type`? | **`header().string(...)`**, **`header().exists(...)`**, **`redirectedUrl(...)`**, **`redirectedUrlPattern(...)`** |

A single test can verify multiple dimensions in one request. For example, when missing a Bearer token or Basic credentials, **status 401** should accompany **WWW-Authenticate** with the proper scheme. Conversely, if a web app uses form login, an unauthenticated request typically receives **302 to the login page**, not 401.

**Do not hard-code one status across all configurations:** HTTP Basic, Bearer, `formLogin`, `oauth2Login`, custom entry points, request matchers, CSRF, and exception handlers determine the real outcome. Expected statuses must derive from the **security contract** of the API or UI under test.

## 3. Authentication != HTTP 200

An endpoint can be public:

~~~java
.requestMatchers("/api/public").permitAll()
~~~

When not logged in, the client still gets **200**. This does not prove the request was authenticated; it only proves the authorization rule permits anonymous access.

A protected endpoint:

~~~java
.requestMatchers("/api/admin").hasRole("ADMIN")
~~~

Authenticated user `alice` holding **`ROLE_USER`** without **`ROLE_ADMIN`** is rejected with **403**. Alice is **authenticated**, yet **not authorized for this resource**.

**`AnonymousAuthenticationToken`** may exist and even have **`isAuthenticated()` return true** per its implementation semantics. Therefore, never use:

~~~java
if (authentication != null && authentication.isAuthenticated()) {
    // Wrong if used to conclude the user is a real logged-in user.
}
~~~

to substitute for Spring Security authorization rules. When distinguishing anonymous callers from real users, the framework provides **`AuthenticationTrustResolver`**; when protecting endpoints, prefer **`authenticated()`**, **`fullyAuthenticated()`**, **`hasRole(...)`**, or **`hasAuthority(...)`** per policy.

A mental model for reading test flows:

~~~text
        Request
           |
           v
  Credentials/token?
           |
     +-----+------+
     |            |
    No           Yes
     |            |
  Public?    Valid auth?
   |   |         |    |
  Yes No        No   Yes
   |   |         |    |
  200 401/302   401  Check permissions
                      |         |
                  Sufficient  Missing
                     |          |
                    200        403
~~~

This is an **overview diagram**, and not every app returns these exact codes: the framework and custom entry points/handlers may return 400/404/302 or custom responses. In particular, **CSRF** can make a POST return **403** even for a valid user; never automatically equate 403 with a missing role.

## 4. Statuses: 200, 201, 204, 302, 401, 403, 404, and 405

| Status | Interpretation in tests | What else to check |
| --- | --- | --- |
| **200 OK** | Endpoint succeeded | Whether JSON/body and data ownership are right |
| **201 Created** | Resource created successfully | **`Location`** header, body, authorization, and idempotency |
| **204 No Content** | Operation succeeded, no body | Do not demand a JSON response; check side effects |
| **301/302/303/307/308** | Redirect | **`Location`** header, target path, method semantics, cookies/session |
| **401 Unauthorized** | Unauthenticated or credentials rejected | **`WWW-Authenticate`**, no accidental UI login redirect |
| **403 Forbidden** | Authenticated yet missing permission, or CSRF/policy denied | Distinguish authorization from CSRF and `AccessDeniedHandler` |
| **404 Not Found** | No matching route/resource or deliberately hiding existence | Verify the request passed through the expected security chain |
| **405 Method Not Allowed** | Route does not support the HTTP method | **`Allow`** header if returned by the framework; do not infer authentication from it |

401 is named "Unauthorized", yet in HTTP authentication semantics it usually means **no valid authentication yet**. An authenticated request lacking a role is typically **403**.

**Browser login clients:** status 302 is not necessarily an error. It can be completely correct when a user has no web session and must visit the login page. Machine-to-machine APIs normally expect **direct 401/403**, not an HTML login page via redirect.

## 5. Checking Headers for the Right Purpose

### 5.1. WWW-Authenticate

With HTTP Basic, 401 normally includes a challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

The exact realm depends on configuration; tests should not pin **`Realm`** unless it is part of the contract. To test the mechanism properly:

~~~java
.andExpect(status().isUnauthorized())
.andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE, startsWith("Basic")))
~~~

For OAuth2 Resource Server Bearer tokens, the scheme is typically **`Bearer`** and may include **`error`** / **`error_description`** or **`scope`** per RFC/implementation. If an API expects Bearer yet the test sees Basic or a `/login` redirect, the request may have hit **the wrong `SecurityFilterChain`**.

### 5.2. Location

When returning a redirect, **`Location`** tells the client which URL to navigate to:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

Test:

~~~java
.andExpect(status().is3xxRedirection())
.andExpect(header().string(HttpHeaders.LOCATION, endsWith("/login")))
~~~

Use **`redirectedUrl("/login")`** if the contract and test environment guarantee the exact URL. If `Location` may be absolute **`http://localhost/login`** or relative **`/login`**, you can use **`redirectedUrlPattern("**/login")`** or Hamcrest **`endsWith("/login")`**; be careful to relax matching only deliberately so you do not mask a redirect to the wrong domain.

For redirects with query strings like **`/login?error`**, check the query or redirect pattern explicitly; **`?`** in an Ant-style pattern can act as a wildcard character, so tests should pick a matcher aligned with the contract.

### 5.3. Cache-Control, Content-Type, and Security Headers

Spring Security can set headers such as **`Cache-Control`**, **`X-Content-Type-Options`**, and **`X-Frame-Options`** depending on version and configuration. Do not assume every header always appears on every route or in every Spring Security version. When required by the contract, use:

~~~java
.andExpect(header().exists(HttpHeaders.CACHE_CONTROL))
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
~~~

If you need to verify **`Content-Security-Policy`**, **`Strict-Transport-Security`**, **`Referrer-Policy`**, or cookie **`Secure/HttpOnly/SameSite`**, base expectations on enabled config and request conditions. For example, HSTS relates to HTTPS; mock HTTP tests should not blindly assert HSTS must always appear.

### 5.4. Do Not Mistake Request Headers for Response Headers

**`Authorization: Basic ...`** is a client request header. **`WWW-Authenticate: Basic ...`** is a server challenge response header. **`Location`** is a response header on redirect. **`Cookie`** sent by the client differs from **`Set-Cookie`** returned by the server. Place assertions on **the right side** so tests never accidentally pass with the wrong data.

## 6. Spring Security Test and MockMvc: Two Helper Groups

### 6.1. RequestPostProcessors: Constructing Inputs

Spring Security Test provides:

- **`user("alice").roles("USER")`**: creates a mock `Authentication` for the request.
- **`anonymous()`**: creates an anonymous context in the test.
- **`httpBasic("alice", "password")`**: adds an HTTP Basic `Authorization` header so real filters validate credentials.
- **`csrf()`**: adds a valid CSRF token for POST/PUT/DELETE tests when the app uses CSRF protection.
- **`jwt()`**: creates a mock JWT `Authentication`, used when testing authorization of resource-server endpoints.
- **`oauth2Login()`**: mocks an OAuth2 logged-in state without running a real authorization code flow.

**Important distinction:** **`user()`**, **`@WithMockUser`**, and **`jwt()`** do not check passwords, token signatures, or contact an IdP. They mainly build an `Authentication` to test **authorization and controllers**. **`httpBasic()`** only adds a header; when running the Spring Security filter chain, the backend still has to check username/password.

### 6.2. ResultMatchers: Checking Outputs

~~~java
// Spring MVC HTTP-level:
.andExpect(status().isOk())
.andExpect(status().isUnauthorized())
.andExpect(status().isForbidden())
.andExpect(status().is3xxRedirection())

// Header-level:
.andExpect(header().string(HttpHeaders.LOCATION, endsWith("/login")))
.andExpect(header().exists(HttpHeaders.CACHE_CONTROL))

// Redirect-level:
.andExpect(redirectedUrlPattern("**/login"))

// JSON-level:
.andExpect(jsonPath("$.name").value("alice"))
~~~

In addition, **`SecurityMockMvcResultMatchers`** has **`authenticated()`** and **`unauthenticated()`** to check the authentication state observed by Spring Security Test. This is a different check from HTTP status:

~~~java
// Illustrative snippet on a request with a test Authentication attached.
mvc.perform(get("/api/me").with(user("alice").roles("USER")))
        .andExpect(status().isOk())
        .andExpect(authenticated().withUsername("alice"));
~~~

**`authenticated()`** requires a static import from **`org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers`**. In projects using stateless APIs, how the test stores/reads context must match the filter chain; do not conclude a failed result matcher automatically means the HTTP status was wrong.

**`unauthenticated()`** fits when proving a request has no authenticated user, whereas **status 200 on a public endpoint** does not guarantee that on its own. Use dedicated matchers rather than guessing authentication state from response status.

## 7. Complete Project: Two SecurityFilterChains, HTTP Basic API, and Web Form Login

To clearly show two different contracts, the project below uses:

- **API `/api/`**: HTTP Basic; no login redirect, returns 401 on missing/wrong credentials and 403 on insufficient permission.
- **Web `/dashboard`**: form login; unauthenticated users redirect 302 to **`/login`**; successful login redirects to **`/dashboard`**.
- **`/api/public`**: permits anonymous access to prove **200 does not equal authenticated**.
- **`/api/admin`**: requires `ROLE_ADMIN`.
- **`Cache-Control`**, **`Content-Type`**, **`WWW-Authenticate`**, **`Location`**, **CSRF**, and sessions are intentionally included in the tests.

Uses **Java 17**, **Spring Boot 3.4.5**, Maven, Spring MVC, and Spring Security Servlet. This version is pinned for reproducibility; no claim is made that it is the latest version.

Structure:

~~~text
security-http-tests/
├── pom.xml
└── src/
    ├── main/java/demo/httptest/SecurityHttpApplication.java
    └── test/java/demo/httptest/SecurityHttpTests.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-http-tests</artifactId>
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

### 7.2. src/main/java/demo/httptest/SecurityHttpApplication.java

~~~java
package demo.httptest;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityHttpApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityHttpApplication.class, args);
    }
}

@Configuration
class TestSecurityConfiguration {
    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}alice-pass")
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin-pass")
                        .roles("USER", "ADMIN")
                        .build());
    }

    // First chain applies only to /api/**.
    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                // Demo only has GETs. Do not disable CSRF mechanically.
                .build();
    }

    // Second chain is for web and the login page.
    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .defaultSuccessUrl("/dashboard", true))
                .build();
    }
}

@RestController
class DemoController {
    @GetMapping("/api/public")
    Map<String, String> publicApi() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication auth) {
        return Map.of("name", auth.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> admin(Authentication auth) {
        return Map.of("admin", auth.getName());
    }

    @GetMapping("/dashboard")
    Map<String, String> dashboard(Authentication auth) {
        return Map.of("welcome", auth.getName());
    }
}
~~~

**Configuration explanation:**

1. **`@Order(1) + securityMatcher("/api/**")`** ensures API requests enter the Basic chain before the web chain. API requests without Basic credentials are handled by the HTTP Basic entry point rather than redirecting to the login page.
2. **`/api/public`** uses **`permitAll()`**; anonymous requests still succeed.
3. **`/api/admin`** requires `ROLE_ADMIN`. User `alice` has `ROLE_USER` but lacks `ROLE_ADMIN`.
4. **`SessionCreationPolicy.STATELESS`** on the API does not store authentication state in `HttpSession`; each API call may need Basic credentials. This is an HTTP Basic demo over **`localhost`**; never use plaintext HTTP Basic in production.
5. **The web chain** has form login and **`defaultSuccessUrl("/dashboard", true)`**, so after successful login it redirects to dashboard regardless of saved request. Real apps may use saved requests or default targets depending on UX.
6. Web login uses **`HttpSession`** by default and keeps **CSRF**. Thus login POSTs in tests require **`csrf()`**.
7. The demo intentionally has only GETs on the API. If adding POST/PUT/DELETE, especially when browsers auto-send Basic/cookie credentials, design and test **CSRF**; never copy arbitrary CSRF-disable snippets.
8. **`{noop}alice-pass`** and **`{noop}admin-pass`** are lesson data, not production password design; real deployments need a proper password encoder, TLS, credential management, and security policies.
9. Only **`SecurityFilterChain`** beans are declared, with no extra custom filter altering statuses. Therefore, the HTTP assertions in the next section directly reflect the two entry points in this lesson.

## 8. Complete MockMvc Test Suite: Status, Headers, Redirects, and Sessions

Create **`src/test/java/demo/httptest/SecurityHttpTests.java`**:

~~~java
package demo.httptest;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.endsWith;
import static org.hamcrest.Matchers.startsWith;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHttpTests {
    @Autowired
    MockMvc mvc;

    @Test
    void publicApiAllowsUnauthenticatedRequest() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void apiWithoutCredentialsReturns401AndBasicChallenge()
            throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        startsWith("Basic")))
                .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
    }

    @Test
    void wrongBasicCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        startsWith("Basic")));
    }

    @Test
    void validBasicCredentialsReturn200AndExpectedHeaders()
            throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL,
                        containsString("no-store")))
                .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403()
            throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden())
                .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
    }

    @Test
    void adminCanReachAdminApi() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.admin").value("admin"));
    }

    @Test
    void anonymousWebRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        HttpHeaders.LOCATION,
                        endsWith("/login")));
    }

    @Test
    void defaultLoginPageIsHtml() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_HTML));
    }

    @Test
    void loginWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "alice-pass"))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongFormPasswordRedirectsToLoginError() throws Exception {
        mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "alice")
                        .param("password", "wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        HttpHeaders.LOCATION,
                        endsWith("/login?error")));
    }

    @Test
    void successfulLoginRedirectsAndSessionCanOpenDashboard()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "alice")
                        .param("password", "alice-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        HttpHeaders.LOCATION,
                        endsWith("/dashboard")))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.welcome").value("alice"));
    }
}
~~~

**11 test methods** verify public access, missing credentials, wrong/right Basic credentials, roles, redirects, HTML login page, CSRF, login failure, login success, and session continuity. Actual execution depends on dependencies/versions/Servlet config, so run **`mvn test`** to confirm; this code is designed around Spring Security Servlet defaults for the stated configuration and assumes no external IdP.

### 8.1. Inspecting Each Key Assertion

**Case A — anonymous API:** `GET /api/public` returns **200**. The test checks public JSON; never write "user logged in" merely because status is 200.

**Case B — unauthenticated API:** `GET /api/me` without credentials returns **401**, with **`WWW-Authenticate: Basic ...`** and no **`Location`**. If you see 302 and `Location /login`, check `securityMatcher /api/**` and the ordering of `SecurityFilterChain` beans.

**Case C — wrong password:** Sends a Basic header yet fails `AuthenticationManager`. The test must still receive 401. This differs completely from **`.with(user(...))`**, which simulates an authenticated user and never tests passwords.

**Case D — valid user:** HTTP Basic `alice` with right password receives **200**, body contains `name: alice`. The test verifies **`Cache-Control`** contains **`no-store`** per the default header writer in the demo configuration. If a project changes header policy, update tests to match **the decided contract** rather than blindly deleting assertions.

**Case E — role:** Valid `alice` lacking ADMIN gets **403**. Admin holding `ROLE_ADMIN` gets **200**. This demonstrates the difference between Authentication and Authorization.

**Case F — web redirect:** `GET /dashboard` without a session gets **3xx** and **`Location`** ending in **`/login`**. Both status and redirect target must be checked; a test asserting only 302 will miss redirects to the wrong domain or route.

**Case G — CSRF:** `POST /login` without CSRF is blocked 403 before the login filter runs; POST with **`csrf()`** reaches form login. This shows why "403" does not always mean a missing role.

**Case H — login failure:** Wrong credentials redirect to **`/login?error`**. This is a browser flow, not an HTTP Basic challenge.

**Case I — login success:** Valid `POST /login` redirects to **`/dashboard`**; the test grabs the `HttpSession` created by login and makes a follow-up request with that session. Checking only the redirect would not prove the login session works on the next request.

### 8.2. Why Not Rely Solely on Response Username to Verify Everything?

An endpoint accidentally returning **`{"name":"alice"}`** from a hardcoded variable would still pass a JSON assertion. Therefore tests should combine:
- Status/challenge/redirect per security contract.
- Real authentication in appropriate tests: Basic login, form login, or signed JWT integration.
- Positive and negative authorization checks by roles.
- Verifying controllers return data derived from the principal, not from a request parameter.
- For owned resources, testing **record ownership**, not just status and username.

## 9. Run Commands and HTTP Examples

At the Maven root directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

Local test requests:

~~~bash
# Public API: expected 200
curl -i http://localhost:8080/api/public

# Protected API unauthenticated: expected 401 and WWW-Authenticate
curl -i http://localhost:8080/api/me

# Valid Basic authentication: expected 200
curl -i -u alice:alice-pass http://localhost:8080/api/me

# User lacking ROLE_ADMIN: expected 403
curl -i -u alice:alice-pass http://localhost:8080/api/admin

# Admin API with admin user: expected 200
curl -i -u admin:admin-pass http://localhost:8080/api/admin

# Web unauthenticated: expected 302 and Location
curl -i http://localhost:8080/dashboard

# Login page: expected 200 HTML
curl -i http://localhost:8080/login
~~~

**Note:** `curl` does **not follow redirects by default** without `-L`; use **`-i`** to observe status and `Location`. If you pass **`-L`**, `curl` follows through to `/login` and the final result can be 200 HTML, misleading readers into thinking `/dashboard` returned 200. In security tests, inspect both the **initial response** and the redirect chain.

**`curl -u`** commands can appear in shell history; never use real passwords this way in production. Real-world HTTP Basic must be protected by HTTPS. The localhost demo uses fake credentials solely for learning.

## 10. Testing Spring Security's authenticated() and unauthenticated()

Sometimes you want to assert **security state**, not just HTTP status. Spring Security Test provides:

~~~java
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
~~~

Usage inside a test method (snippet, not a standalone file):

~~~java
mvc.perform(get("/api/me")
                .with(user("alice").roles("USER")))
        .andExpect(status().isOk())
        .andExpect(authenticated().withUsername("alice"));
~~~

For a public endpoint, you can assert the request has no real authenticated user via **`unauthenticated()`** when test setup and the security chain are wired properly. However, on systems using anonymous authentication, checking **anonymous vs authenticated** should rely on Spring Security Test semantics rather than **`Authentication != null`** alone.

**Difference between mock tests and real tests:**

| Test approach | What it checks | What it does not check |
| --- | --- | --- |
| `.with(user("alice"))` | Authorization and controller with a mock principal | Password encoder, HTTP Basic header, session login |
| `@WithMockUser` | Mock `SecurityContext` in tests | Real SSO/OIDC/JWT validation |
| `.with(httpBasic(...))` | Basic header + filter/provider processing credentials when MockMvc has filters | Real HTTPS, proxies, browser sessions |
| `POST /login` with `csrf()` | Login form filter, CSRF, session/redirect | External SSO provider if not configured |
| `.with(jwt())` | Simulated JWT principal/authorities | JWT signature, issuer, audience, key rotation |
| HTTP integration test with validly signed tokens | Closer to real-world authentication | Still needs gateway/proxy/authorization E2E if architecture includes them |

If tests only use **`@WithMockUser`** and claim form login/Basic passwords work, that conclusion is invalid. Maintain both **authorization unit tests** and **authentication integration tests** matching the real mechanism.

## 11. Checking Redirects and Saved Requests

Spring Security can record an unauthenticated request and send the user back to the initial URL after login. That depends on **`RequestCache`**, **`SavedRequestAwareAuthenticationSuccessHandler`**, default target URL, and session policy.

In section 7's example, **`defaultSuccessUrl("/dashboard", true)`** intentionally sets **`alwaysUse`** to true, so after login succeeds the user is sent to `/dashboard` even if a saved request exists. Tests can assert that exact destination.

If switching to saved-request restoration:
1. Call `GET /reports` before logging in.
2. Receive 302 `/login`; the request is saved as configured.
3. Reuse the same `HttpSession` and send `POST /login` with valid CSRF.
4. Verify the redirect returns to `/reports`.
5. Call `/reports` with the session and confirm user-specific content.

**Not every app has to redirect back to the original URL.** An app may intentionally send users to a dashboard, MFA step-up, or tenant-selection page. What must be tested is **the designed contract**, including **open redirect** controls.

### Preventing Open Redirects

Never let clients supply arbitrary external URLs as post-login redirect targets without allowlist/same-origin checks. Tests should cover:
- Valid relative URLs.
- Off-domain URLs rejected or normalized.
- URLs with unusual schemes or encoded characters not sending users to an attacker site.
- Saved requests not routing users to resources they have lost access to.

**Location matching** is not just substring checking; when security-sensitive, verify **scheme, host, path, and query** against policy.

## 12. Sessions, Cookies, and CSRF When Testing Browser Login

In web flows, successful login typically creates an **`HttpSession`** and session cookie. With **`MockMvc`**, you can pass **`MockHttpSession`** directly to the next request, as in section 8. In real browsers, the client receives the cookie via **`Set-Cookie`** and sends it back via **`Cookie`**.

**Technical note:** Do not rigidly assert that a MockMvc `POST /login` response always includes `Set-Cookie`, because MockMvc is not a full networked Servlet container and cookie creation can differ from a real server. When verifying **`Secure`, `HttpOnly`, `SameSite`**, add embedded-server/HTTP integration tests under the corresponding TLS/proxy setup.

**CSRF is a separate control from Authentication.** A user logged in with a cookie can still receive 403 on POST if a CSRF token is missing. Spring Security Test provides **`csrf()`** to simulate a valid token, or **`csrf().useInvalidToken()`** when testing an invalid token.

Snippet example:

~~~java
mvc.perform(post("/action")
                .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
~~~

This snippet only makes sense in a real project that has the route and CSRF enabled. Do not paste it into the demo project and expect a nonexistent **`/action`** endpoint test to pass. When an API uses Bearer tokens sent via the `Authorization` header without browser auto-sent credentials, the design can differ, yet CSRF must be evaluated across **the entire authentication mechanism**, rather than blindly disabled for all endpoints.

## 13. Testing Content, Body, and JSON Alongside Security

**Right status with wrong data** is still an incomplete test. For **`/api/me`**, verify:

~~~java
.andExpect(status().isOk())
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
.andExpect(jsonPath("$.name").value("alice"))
~~~

In real APIs, also check:
- Returned resource IDs belong to the calling principal.
- Tenant ID/scope is not taken from an unverified header or query parameter.
- Body does not leak credentials, raw access tokens, refresh tokens, cookies, or a serialized `SecurityContext`.
- Cache headers are appropriate when responses are sensitive.
- Unauthorized users never receive 200 data due to bad URL matching.
- Error bodies do not leak tokens, user details, or stack traces.

Do not write tests checking only **`response.getStatus() == 200`**, as that misses endpoints accidentally returning another account's data. Avoid relying on JSON key ordering; use **`jsonPath`** with explicit property names.

## 14. Bearer Token APIs and OAuth2 Login: Do Not Confuse Entry Points

The sample project uses HTTP Basic and form login, yet the same thinking applies to OAuth2:

**Resource Server Bearer:**
- Missing/invalid token: usually **401**, header **`WWW-Authenticate: Bearer ...`**.
- Valid token lacking scope: usually **403**.
- Valid token with sufficient scope: **200**, check resource ownership.
- MockMvc tests with **`jwt()`** test authorization; testing signatures/issuer/audience needs a real decoder or signed integration fixture.

**Web OAuth2/OIDC Login:**
- Unauthenticated user: usually **302** to an authorization initiation endpoint like **`/oauth2/authorization/{registrationId}`**, or a provider selection page.
- Successful login may create a session/cookie and redirect to the saved request/target URL.
- Test state, redirect URI, CSRF/session, and real configuration; mocking OAuth2 login does not prove an external IdP was contacted.

If a **Bearer API returns a 302 HTML login page**, suspect a chain selection bug; if a browser page expected to redirect returns 401 JSON instead, suspect the wrong entry point. Avoid using one broad `SecurityFilterChain` for all URLs without testing each client type.

## 15. Common Mistakes

1. **Asserting only `status().isOk()`.** Misses user identity, payload, headers, and permissions.
2. **Equating 200 with authenticated.** `permitAll()` also returns 200 for anonymous callers.
3. **Equating 403 with always missing a role.** CSRF can also return 403.
4. **Equating 302 with always login success.** Redirects can point to `/login`, `/login?error`, or the wrong URL.
5. **Using `@WithMockUser` to test real passwords.** It bypasses password verification.
6. **Testing an API's `WWW-Authenticate` via the `Authorization` header.** One is a response challenge; the other is a request credential.
7. **Treating `curl -L`'s final status as the initial redirect status.** It hides the `302 -> 200` chain.
8. **Using exact `redirectedUrl` when the app returns absolute URLs.** Pick the right matcher without overly loosening host security.
9. **Forgetting the session on the second request after login.** Re-runs as an unauthenticated user.
10. **Forgetting `csrf()` on form login POSTs.** A 403 test may be failing on CSRF before password validation ever runs.
11. **Skipping negative role tests.** ADMIN 200 does not prove USER gets 403.
12. **Confusing MockMvc with a full browser/HTTP server.** Cookie/TLS/proxy/redirect-following behavior needs E2E when critical.
13. **Checking only principal name, not ownership.** Users may read data that does not belong to them.
14. **Assuming default security headers never change.** Rely on Spring Security version/config and the contract.
15. **Ignoring request matcher order.** APIs may fall into the web login chain, producing wrong status/headers/redirects.

## 16. Checklist for Designing an HTTP Security Test Suite

- [ ] Clearly state whether endpoints are for browser/session or API/token clients.
- [ ] Test public/anonymous endpoints separately from endpoints requiring authentication.
- [ ] For Basic/Bearer APIs, test **401** and the **`WWW-Authenticate`** header with the right scheme.
- [ ] Test invalid credentials/tokens.
- [ ] Test valid user lacking permission => 403.
- [ ] Test user with sufficient permission => 200 and accurate response body.
- [ ] For form/OIDC login, test **3xx + Location** with the right destination.
- [ ] Test both login failure and success if the app uses forms.
- [ ] Test session continuity after login if using cookies/sessions.
- [ ] Test valid, missing, and invalid CSRF tokens for applicable mutation endpoints.
- [ ] Test `Content-Type`/`Cache-Control`/security headers per contract.
- [ ] Test that redirects cannot target untrusted domains.
- [ ] Test that multiple `SecurityFilterChain` beans select the right chain for API vs web.
- [ ] Distinguish **mock authentication** from **real filter/provider authentication**.
- [ ] Add integration tests with an HTTP server, proxy/TLS/cookies when those layers affect outcomes.
- [ ] Never log or serialize access tokens, passwords, or `SecurityContext` into test reports.

## 17. Self-Check Questions

1. **Does a public endpoint returning 200 prove authenticated?** No; `permitAll` allows anonymous access.
2. **What does a Basic API without credentials usually return?** 401 along with header `WWW-Authenticate: Basic ...`
3. **Authenticated user without `ROLE_ADMIN`?** Usually 403 on an endpoint requiring that role.
4. **How does unauthenticated web form login usually respond?** 302 to the login page via `Location`.
5. **Why inspect the `Location` header?** To confirm the redirect points to the right destination, not merely status 302.
6. **Does `.with(user("alice"))` verify Alice's password?** No, it simulates `Authentication`.
7. **How does `.with(httpBasic(...))` differ?** It builds a Basic `Authorization` header so filters/providers validate credentials when MockMvc has security filters.
8. **Does `POST /login` without `csrf()` returning 403 mean wrong password?** Not necessarily; it may be rejected by the CSRF filter before trying the password.
9. **After MockMvc login succeeds, what is needed to `GET /dashboard`?** Carry the `MockHttpSession` or appropriate cookie state into the next request.
10. **How to avoid confusing 302 with 200 when using `curl`?** Observe the initial response with `curl -i`; do not auto-follow redirects with `-L` when testing `Location`.
11. **What should you check if a Bearer API returns an HTML login page?** `SecurityFilterChain` matching, authentication entry point, and client contract.
12. **Is status 200 with the right username enough to verify authorization?** No; also check ownership/tenant/scope and returned data.

**Conclusion:** HTTP security testing in Spring Security Servlet must combine **Authentication state**, **Authorization**, **HTTP status**, **response headers**, **Location/redirects**, and returned payload. With **MockMvc + spring-security-test**, write both positive and negative cases, distinguish **401/403/302**, and check **`WWW-Authenticate`**, **`Location`**, CSRF, and sessions according to the client type. Mock-user tests help verify authorization, while tests traversing filters/providers and real-environment integration verify that login and token flows match the design.
