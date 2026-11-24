# Coordinating Security with CORS, CSRF, and Session Cookies in Spring Boot

In a Spring Boot application using session login, the browser typically receives a cookie holding a session ID to associate requests with the authenticated session. When the frontend and backend have different origins, **CORS** determines which origins' JavaScript is allowed to read responses. Because browsers can attach cookies automatically, **CSRF protection** shields state-changing operations from requests triggered by untrusted pages. **Cookie attributes** such as HttpOnly, Secure, and SameSite add transmission restrictions. These three mechanisms are closely connected yet cannot replace one another.

For example, a frontend running at **https://app.example.test** calls a Spring Boot API at **https://api.example.test**. The two hosts have different origins and need CORS if JavaScript reads responses. However, both are generally considered same-site when using HTTPS and sharing the registrable domain example.test. The API's host-only cookie can be sent by the browser when the frontend calls the API with an appropriate credentials mode; that in turn creates a need for CSRF protection on session-backed POST/PATCH/DELETE requests.

This article belongs to the **Security Integration** group in the **Spring Boot - web-runtime** module, using **Java 17+, Spring Boot 3.3.x, Spring Security 6.x, Spring MVC Servlet**, Maven, and Thymeleaf for examples. All accounts, passwords, and domains in the article are test data. Production must use HTTPS, proper identity management, and dedicated security policies.

## 1. Learning Objectives

After this article, you should be able to:

1. Distinguish **cross-origin** from **cross-site**, and understand why they are not synonymous.
2. Understand **CORS preflight OPTIONS**, Allowed-Origin, Allowed-Credentials, allowed methods/headers, and the browser's role.
3. Understand the **CSRF threat model** when browsers automatically send session cookies, and why CORS does not block CSRF by itself.
4. Grasp the meanings of **HttpOnly, Secure, SameSite=Strict/Lax/None, Domain, Path**, and the difference between cookie lifetime and session timeout.
5. Configure a **SecurityFilterChain** that enables CORS in the right place and keeps default CSRF enabled for state-changing methods.
6. Distinguish **401 unauthenticated**, **403 insufficient permission/CSRF token**, **CORS errors**, and cookie delivery failures.
7. Build a complete project featuring a login form, GET/POST APIs, Thymeleaf CSRF tokens, session cookies, and CORS configuration.
8. Write **MockMvc tests** for allowed/forbidden preflights, unauthenticated API calls, POST with/without CSRF, login, and sessions.
9. Solve cross-origin SPA challenges: XSRF-TOKEN, token refresh, deferred loading, and BREACH in Spring Security 6.
10. Build a security checklist for subdomains, proxies, caches, multiple replicas, and production.

## 2. What Question Does Each Mechanism Answer?

| Mechanism | Role | Cannot Replace |
| --- | --- | --- |
| **CORS** | Browser controls whether JavaScript across origins can read responses, and handles preflight for certain requests. | Authentication, authorization, CSRF, network firewalls. |
| **Session cookie** | Browser sends an ID so the server can look up the authenticated session. | User intent and operation permissions. |
| **CSRF token** | Does an unsafe request carry valid proof originating from the application? | Login, authorization, XSS protection, CORS. |
| **SameSite** | Browser restricts sending cookies in cross-site requests. | CSRF tokens in all scenarios, especially same-site subdomains. |
| **HttpOnly** | Prevents document.cookie from reading the session cookie. | Does not stop browsers from auto-sending cookies; does not prevent all XSS. |
| **Secure** | Restricts cookies to appropriately secure connections. | Does not prevent CSRF, XSS, or session fixation. |
| **Authorization** | Is the principal permitted to access this resource/operation? | Does not verify the request was not forged from another website. |

A malicious website can trigger a request even if CORS blocks it from reading the response; **side effects can still occur** if the app lacks CSRF protection. Conversely, a CORS-allowlisted origin does not automatically gain permission to read any user's account: the API must still authenticate and authorize.

## 3. Cross-Origin Differs from Cross-Site

### 3.1. Origin Is Defined by Scheme, Hostname, and Port

~~~text
https://app.example.test        origin A
https://api.example.test        origin B: different hostname
https://app.example.test:8443   origin C: different port
http://app.example.test         origin D: different scheme
~~~

JavaScript on A calling B is cross-origin and governed by the Same-Origin Policy. CORS is the mechanism by which **server B grants** specific origins permission to read responses via headers. CORS does not restrict a program like curl, Postman, or a backend service from sending HTTP requests.

### 3.2. Site Usually Depends on Scheme and Registrable Domain

Modern browsers use **schemeful same-site**, typically based on scheme and eTLD+1/registrable domain, which differs from origin:

| Frontend → API | Cross-origin | Cross-site | Meaning |
| --- | --- | --- | --- |
| **https://app.example.test → https://api.example.test** | Yes | Usually no | CORS still needed; SameSite=Lax can send cookies in fetch. |
| **https://app.example.test → https://api.other.test** | Yes | Yes | Cross-site cookies subject to SameSite, Secure, third-party cookie policy. |
| **https://app.example.test → http://api.example.test** | Yes | Yes by schemeful site | Different scheme; never downgrade HTTPS. |
| **http://localhost:5173 → http://localhost:8080** | Yes | Usually same-site | Different ports so fetch needs CORS; cookies are not scoped by port. |
| **https://app.example.test → https://app.example.test:8443** | Yes | No | Different origin due to port, yet same site. |

A host-only cookie for **api.example.test** is sent to `api.example.test` itself on valid requests. You do not need to set **Domain=.example.test** merely because the frontend sits at `app.example.test`. Widening `Domain` across subdomains weakens cookie boundaries.

**Same-site does not mean trusted**: a malicious page on **evil.example.test** can be same-site with the API. Therefore, **SameSite=Lax does not replace CSRF tokens**, and CORS should never blindly permit all subdomains. When a subdomain is operated by a third party, treat it as a real trust boundary.

## 4. How Does CORS Work?

### 4.1. Simple Requests and Preflight

Certain CORS-safelisted requests can be sent directly by the browser, after which the browser checks response headers to decide whether JavaScript may read the data. Other requests (such as JSON POSTs or requests with custom CSRF headers) require an **OPTIONS preflight** before the actual request.

Example preflight:

~~~http
OPTIONS /api/notes HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Example response:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Max-Age: 3600
Vary: Origin
~~~

Preflight is a browser policy query, **not a business call**. It **typically carries no JSESSIONID**, so authentication filters must not demand login before CORS handles it. Spring Security documentation requires **CORS to be processed before Security** so preflights are not rejected as unauthenticated.

**Max-Age in preflight** is how long the browser caches the preflight result under its own policy—it does not mean the server session lives for 3600 seconds.

### 4.2. Credentialed CORS

When a cross-origin frontend wants the browser to consider sending cookies:

~~~javascript
fetch("https://api.example.test/api/me", {
  method: "GET",
  credentials: "include"
});
~~~

If the server allows that origin to read credentialed responses, it returns:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Never combine Access-Control-Allow-Origin: * with credentialed CORS**. Setting `credentials=true` requires a specific origin. Spring CORS includes validation that prevents pairing **allowedOrigins("*")** with **allowCredentials(true)**.

**credentials: include does not override other cookie policies**: SameSite, Secure, Domain/Path, third-party cookie blocking, browser permissions, or cleared cookies. If fetch sets `include` yet the network request has no `Cookie` header, inspect cookie policies instead of blindly tweaking CORS.

### 4.3. CORS Is Not CSRF Protection

A simple HTML form can cause a browser to send a cross-origin POST even though JavaScript cannot read the response. If the server executes side effects based purely on the session cookie, unintended actions can still happen. CORS restricts JavaScript response reading; it does not replace **CSRF token validation** for unsafe methods.

**curl also does not obey the browser Same-Origin Policy**. Sending curl without an `Origin` header can still call the API; the backend must enforce authentication and authorization on every request. Never treat the `Origin` header as sole proof of client identity.

### 4.4. Origin Reflection, Allowlists, and Vary

Configurations that **allow all origins or echo back whatever Origin was sent** are dangerous when cookies are involved. If permitting multiple controlled origins, caches/proxies must properly handle **Vary: Origin** and relevant preflight `Vary` fields. Never strip `Vary` to raise cache hit rates when responses vary by `Origin`.

**CORS should only be applied to routes that truly need cross-origin browser access**, such as `/api/**`; login, admin, or internal management endpoints should not be opened with the same policy out of habit.

## 5. What Is CSRF in a Session-Cookie System?

### 5.1. Browsers Automatically Send Ambient Credentials

A user is logged into a banking site, and the browser holds the session cookie. A malicious site can embed an HTML form that POSTs to the bank; if the browser attaches the cookie under current policies, the server sees a valid session even though the user never clicked transfer on the bank's site.

~~~html
<form action="https://bank.example.test/transfer" method="post">
  <input name="to" value="attacker">
  <input name="amount" value="100">
</form>
~~~

This **threat model illustration** shows why auto-attached cookies cause CSRF. CORS does not solve it because the attacker does not necessarily need to read the response. Modern `SameSite` policies block many cases, yet do not guarantee protection across all same-site subdomains or browser contexts.

### 5.2. Synchronizer CSRF Token

In an app using Spring Security + `HttpSession`, the typical flow is:

1. The server holds a **CSRF token** bound to the session/security context.
2. The application renders the token in an HTML form or supplies it to JavaScript through a controlled mechanism.
3. The browser sends the token in a **hidden form parameter** or **X-CSRF-TOKEN/X-XSRF-TOKEN header**.
4. Spring Security's **CsrfFilter** validates the token against the expected value.
5. Missing or invalid token → **403 Forbidden**; the state-changing controller does not execute.

HTML pattern illustrating the mechanism:

~~~html
<form action="/api/notes" method="post">
  <input name="note" value="hello">
  <input type="hidden" name="_csrf" value="TOKEN_SERVER_RENDERED">
  <button type="submit">Save</button>
</form>
~~~

**TOKEN_SERVER_RENDERED** is an explanatory placeholder, not a real token. Real tokens must be generated and verified by the framework. Never put tokens in URL query strings, as they can leak via browser history, proxy logs, and `Referer` headers.

### 5.3. GET/HEAD/OPTIONS and Unsafe Methods

Spring Security applies CSRF by default to non-safe HTTP methods such as **POST, PUT, PATCH, DELETE**. **GET/HEAD/OPTIONS** are treated as safe under HTTP semantics; therefore, applications **must never mutate state via GET** expecting CSRF to block it.

**POST /login and POST /logout** are also state-changing actions in browser workflows. When CSRF is enabled, Spring Security requires a valid token for them. Session login and logout should never be converted to GET just to use a simple hyperlink.

### 5.4. CSRF Differs from Authorization and XSS

Having a CSRF token does not mean a user is allowed to perform every action. Requests must still pass **authentication and authorization** before processing data. A `VIEWER`-role user with a valid CSRF token still must not be allowed to delete documents.

XSS lets malicious scripts run within a trusted origin, enabling them to read tokens from the DOM or make same-origin API calls. Hence a CSRF token **does not prevent XSS**. You need HTML escaping, appropriate CSP, DOM-injection prevention, and supply-chain protection. **HttpOnly** stops JS from reading session cookies directly, yet does not stop same-origin malicious JS from sending requests.

## 6. Session Cookies: Attributes and Policies

### 6.1. Sample Cookie

~~~http
Set-Cookie: JSESSIONID=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **HttpOnly**: JavaScript cannot read the cookie value via `document.cookie`.
- **Secure**: the browser only sends the cookie over appropriately secure connections; production uses HTTPS.
- **SameSite=Strict**: restricts cookies more aggressively on cross-site requests, which can disrupt flows when navigating from external sites.
- **SameSite=Lax**: mitigates many cross-site POST scenarios while allowing safe top-level navigations and same-site requests.
- **SameSite=None**: allows sending cookies in certain cross-site contexts when paired with **Secure** and permitted by the browser; third-party cookie restrictions may still block it.
- **Path/Domain**: URL and host scope of the cookie, not a permission boundary.
- **Max-Age/Expires**: when the browser may evict the cookie, distinct from server `HttpSession` idle timeout.

### 6.2. Spring Boot Configuration

Example **application.yml** for local development:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        same-site: lax
~~~

**server.servlet.session.timeout** is the server-side session inactivity timeout. The cookie still existing does not mean the session is still valid; sending a stale ID can yield 401/redirect. **server.servlet.session.cookie.max-age** only controls how long the browser retains the cookie and does not extend `HttpSession` lifetime.

In HTTPS production environments, typically add:

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
~~~

Do not put this production `Secure` block into a localhost HTTP demo if your browser refuses to send the cookie over HTTP. Conversely, never downgrade to `Secure=false` in production just to work around reverse proxy errors; fix HTTPS and forwarded headers from trusted proxies.

### 6.3. SameSite and Topology

When **https://app.example.test** calls **https://api.example.test**, they are cross-origin yet usually same-site. A **host-only** API cookie can be sent on credentialed fetch requests if all other conditions are met. You do not need `Domain=.example.test` or `SameSite=None` just because hostnames differ.

When **https://app.other.test** calls **https://api.example.test**, they are cross-site. Cookie-based fetch requests may require **SameSite=None; Secure**, though browser third-party cookie restrictions can still block them. If your project must work when third-party cookies are blocked, consider a same-origin/same-site **backend-for-frontend (BFF)**, reverse-proxying frontend and API together, or a thoroughly reviewed alternative authentication model.

### 6.4. Host-Only Cookies, Domain, and Multiple Localhost Ports

Cookies are **not scoped by port**. Two apps on different localhost ports can share cookies of the same name and interfere during testing. In production, prefer **host-only** cookies when the API is the sole host needing the session. Only widen `Domain` when cookie sharing across subdomains is truly necessary and risks are analyzed—especially if third parties control any subdomain.

The **`__Host-`** cookie prefix enforces extra constraints requiring `Secure`, `Path=/`, and no `Domain`, which helps harden session cookies in some environments. Even so, it **does not replace CSRF tokens** or authorization.

### 6.5. Session Fixation, Logout, and CSRF Token Rotation

Spring Security normally rotates the session ID upon successful authentication to mitigate **session fixation**. On logout, invalidate the server-side session and expire the cookie with matching name/path/domain. Merely clearing frontend state or removing a `localStorage` entry does not revoke the server session.

Spring Security can also **clear CSRF tokens after login/logout**. Browsers/templates or SPAs must fetch the fresh token; reusing an old token on subsequent POSTs rightly returns 403. Never disable CSRF to fix token lifecycle bugs.

## 7. Complete Hands-On Project with Spring Boot 3.3 and Java 17

The demo project includes form login with `HttpSession`, two APIs, and CORS for a fixed origin:

- **GET /**: Thymeleaf page with a sample note POST form and a logout POST form.
- **GET /api/me**: returns JSON for the current user; requires an authenticated session.
- **POST /api/notes**: echoes a sample note; requires an authenticated session **and a CSRF token**.
- **GET/POST /login**, **POST /logout**: Spring Security's form login/logout.
- **CORS** opens only for origin **https://app.example.test** on **/api/** endpoints.

**Demo limitation:** The login page is served by the backend on the same origin as the API. This is not yet a full cross-origin SPA login flow; CORS simply illustrates frontend permission to read APIs once a session exists. For a real SPA, design token issuance and refresh explicitly (Section 11).

### 7.1. Project Structure

~~~text
cors-csrf-cookie-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/
    main/
      java/com/example/websecurity/
        WebSecurityApplication.java
        WebSecurityConfig.java
        PageController.java
        NotesController.java
      resources/
        application.yml
        templates/index.html
    test/
      java/com/example/websecurity/
        WebSecurityIntegrationTest.java
~~~

Create a Maven project via Spring Initializr with Java 17+, Spring Web, Spring Security, and Thymeleaf.

### 7.2. pom.xml

~~~xml
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
    <artifactId>cors-csrf-cookie-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

**spring-security-test** provides the MockMvc **user()** and **csrf()** helpers. Dependency versions are managed by the Spring Boot BOM; do not pin an incompatible Spring Security version manually. Spring Boot 3.3.13 is used for illustration; new deployments should use a supported release with current security patches.

### 7.3. Main Class

**src/main/java/com/example/websecurity/WebSecurityApplication.java**

~~~java
package com.example.websecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSecurityApplication.class, args);
    }
}
~~~

### 7.4. Complete Security Configuration

**src/main/java/com/example/websecurity/WebSecurityConfig.java**

~~~java
package com.example.websecurity;

import java.util.List;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            CorsConfigurationSource corsSource) throws Exception {

        http
            .cors(cors -> cors.configurationSource(corsSource))
            .csrf(withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().authenticated())
            .formLogin(withDefaults())
            .exceptionHandling(ex -> ex.defaultAuthenticationEntryPointFor(
                (request, response, exception) ->
                    response.sendError(
                            HttpServletResponse.SC_UNAUTHORIZED),
                new AntPathRequestMatcher("/api/**")))
            .logout(withDefaults());

        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Replace with an approved origin in production.
        cors.setAllowedOrigins(
                List.of("https://app.example.test"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build());
    }
}
~~~

**Key points to understand:**

1. **cors(cors -> cors.configurationSource(...))** integrates CORS into Spring Security so preflights are not blocked for lacking a session.
2. **csrf(withDefaults())** retains CSRF protection for POST/PUT/PATCH/DELETE and login/logout per default policy.
3. **requestMatchers("/api/**").authenticated()** enforces session authentication before APIs return data.
4. **formLogin(withDefaults())** enables the default login page, with CSRF tokens generated/issued via form integration.
5. **defaultAuthenticationEntryPointFor** returns **401** for unauthenticated API calls instead of sending AJAX clients to HTML `/login`.
6. CORS applies only to **/api/** and allowlists a single frontend origin; cross-origin login is not enabled in this demo.
7. **allowCredentials(true)** does not grant access to every user; session authentication is still required.
8. CORS methods and headers are minimally scoped for the GET/POST demo; adding PATCH/DELETE requires intentionally updating the policy.
9. **student/demo-pass** is a test account only. Production uses an identity provider and proper credential storage; never hardcode passwords in the repo.
10. Never replace the whole security config with **csrf.disable()** just to avoid 403 errors caused by missing tokens.

### 7.5. Page Controller

**src/main/java/com/example/websecurity/PageController.java**

~~~java
package com.example.websecurity;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {
    @GetMapping("/")
    public String index() {
        return "index";
    }
}
~~~

### 7.6. API Controller

**src/main/java/com/example/websecurity/NotesController.java**

~~~java
package com.example.websecurity;

import java.security.Principal;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class NotesController {

    @GetMapping("/me")
    public ResponseEntity<Map<String, String>> me(
            Principal principal) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of("username", principal.getName()));
    }

    @PostMapping("/notes")
    public ResponseEntity<Map<String, String>> save(
            Principal principal,
            @RequestParam String note) {

        // No DB write; returns echoed data for demonstration only.
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                    "savedBy", principal.getName(),
                    "note", note));
    }
}
~~~

**ResponseEntity.noStore()** is applied via **CacheControl.noStore()** so responses containing private info are not stored by HTTP caches. The demo controller performs no real persistence; production systems require resource-level authorization, validation, transactions, XSS protection, and safe logging.

### 7.7. Thymeleaf HTML with Automatic CSRF Integration

**src/main/resources/templates/index.html**

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Session + CORS + CSRF demo</title>
</head>
<body>
  <h1>Session Security Demo</h1>
  <p>Sign in at /login: student / demo-pass.</p>

  <form th:action="@{/api/notes}" method="post">
    <label for="note">Note</label>
    <input id="note" name="note" value="hello" required>
    <button type="submit">Send POST</button>
  </form>

  <form th:action="@{/logout}" method="post">
    <button type="submit">Log out</button>
  </form>
</body>
</html>
~~~

With Thymeleaf + Spring MVC/Spring Security, **th:action** on forms with unsafe methods integrates **RequestDataValueProcessor** to insert a hidden CSRF input. When viewing the rendered HTML, POST forms will contain an actual token; you **should never hardcode** a token into templates. When using template engines without built-in integration, render the hidden parameter via a mechanism reading the token provided by Spring Security.

The `/` page is public in the demo to display the form. If unauthenticated, `POST /api/notes` still requires authentication and CSRF; follow the login workflow before using it.

### 7.8. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: cors-csrf-cookie-demo

server:
  port: 8080
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        same-site: lax
~~~

This is an **HTTP localhost configuration for labs**. Production requires HTTPS and `Secure` cookies per security policy. A 30-minute session timeout does not mean the cookie is deleted after exactly 30 minutes; if an expired cookie ID is sent after the server idle timeout, the API must treat the session as invalid.

### 7.9. Running the Project

Linux/macOS:

~~~bash
./mvnw clean package
java -jar target/cors-csrf-cookie-demo-0.0.1-SNAPSHOT.jar
~~~

Windows:

~~~text
mvnw.cmd clean package
java -jar target/cors-csrf-cookie-demo-0.0.1-SNAPSHOT.jar
~~~

If the project lacks a Maven wrapper, run **mvn clean package** or **mvn spring-boot:run**. Visit **http://localhost:8080/login** in a browser, log in with **student/demo-pass**, then open **http://localhost:8080/** and submit the form. The sample POST carries a CSRF token so it succeeds; the browser displays the resulting JSON.

**Do not misunderstand** the `https://app.example.test` domain in the CORS config as an existing frontend. It is merely an illustrative allowlist; to test with a local browser frontend at `http://localhost:5173`, update the allowed origin to that exact local origin without using wildcards.

## 8. Testing with Spring Security Test and MockMvc

**MockMvc** tests the filter chain and controllers without needing a real browser. It works well for CORS policies, CSRF token validation, and authentication entry points. However, it does not enforce real Chrome/Firefox cookie rules (SameSite, Secure, third-party blocking) and does not prove HTTPS proxy configuration is correct.

### 8.1. Complete Test Class

**src/test/java/com/example/websecurity/WebSecurityIntegrationTest.java**

~~~java
package com.example.websecurity;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebSecurityIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void apiRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .header(HttpHeaders.ACCEPT, "application/json"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void preflightWithoutCookieAllowed() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN,
                        "https://app.example.test")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                        "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "https://app.example.test"))
            .andExpect(header().string(
                    "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void untrustedOriginPreflightRejected() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN,
                        "https://evil.example.test")
                .header("Access-Control-Request-Method", "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithoutCsrfForbiddenEvenWhenAuthenticated()
            throws Exception {
        mvc.perform(post("/api/notes")
                .with(user("student"))
                .param("note", "hello"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfAndUserSucceeds() throws Exception {
        mvc.perform(post("/api/notes")
                .with(user("student"))
                .with(csrf())
                .param("note", "hello"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.savedBy").value("student"))
            .andExpect(jsonPath("$.note").value("hello"));
    }

    @Test
    void loginSessionCanAccessApi() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        HttpSession raw = login.getRequest().getSession(false);
        assertNotNull(raw);
        MockHttpSession session = (MockHttpSession) raw;

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"));
    }
}
~~~

The tests verify:

- **API 401** when unauthenticated, preventing fetch from receiving HTML login 200.
- **Cookie-less OPTIONS preflight** handled by CORS before authentication.
- **Malicious origins** rejected by CORS.
- **POST with an authenticated principal yet missing CSRF token** gets 403.
- **POST with principal and CSRF token** returns 200 JSON.
- **Form login with CSRF** establishes a session and subsequent requests carry the identity.

To use **with(csrf())** and **with(user(...))**, the **spring-security-test** test dependency is required. Run:

~~~bash
./mvnw test
~~~

**MockMvc passing does not prove browsers will send cookies cross-site**. Also perform browser integration tests against real frontend/backend hosts and DevTools Network, especially when HTTPS terminates at a proxy/ingress.

## 9. Testing CORS with curl

### 9.1. OPTIONS with Allowed Origin

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

Expected **200** and headers **Access-Control-Allow-Origin: https://app.example.test**, **Access-Control-Allow-Credentials: true**, along with matching allow-methods/headers. This tests server responses; **curl does not perform browser CORS enforcement**.

### 9.2. OPTIONS with Unknown Origin

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: POST'
~~~

With the demo's `CorsFilter`, unknown origins typically return **403 Invalid CORS request**. Never change the allowlist to a wildcard just to make this request succeed.

### 9.3. GET API Without Login

~~~bash
curl -i -H 'Accept: application/json' \
  -H 'Origin: https://app.example.test' \
  http://localhost:8080/api/me
~~~

Expected **401** even though the origin is permitted. This proves a CORS allowlist **does not grant authentication**.

### 9.4. POST /login Without CSRF

~~~bash
curl -i -X POST http://localhost:8080/login \
  -d 'username=student&password=demo-pass'
~~~

This will return **403** because no CSRF token was sent, even with valid demo account credentials. To log in fully with curl, you must GET the login page to extract the hidden token and save cookies via a cookie jar before POSTing. Using a browser and inspecting the form is simpler. **Never use csrf.disable() to fix a test missing a token.**

## 10. Distinguishing API 401, 403, and Browser CORS Errors

| Result | Common Meaning | What to Check |
| --- | --- | --- |
| **401 Unauthorized** | Unauthenticated; cookie/session missing or expired | Whether cookie was sent, login/session store, entry point. |
| **403 from CSRF** | Unsafe request missing or invalid token | Hidden field/header, token lifecycle, request handler. |
| **403 from Authorization** | Authenticated, yet lacks permission | Principal, roles, tenant, access rules. |
| **403 Invalid CORS request** | Origin/method/header not allowed | CorsConfigurationSource, preflight headers. |
| **Browser CORS error** | JavaScript blocked from reading response under CORS policy | DevTools Origin/Allow-Origin/Credentials; request may still have reached backend. |
| **302 HTML login in fetch** | Form login entry point redirecting API | Separate API 401 from UI navigation redirects. |
| **200 HTML after redirect** | Fetch followed redirect to login page | Check response URL/Content-Type and security entry point. |
| **No Cookie on request** | `credentials` mode, SameSite, Secure, Domain/Path, or browser policy | Network tab Set-Cookie/Cookie; do not assume CORS error. |

**Never automatically retry POST requests upon seeing 403 or 401**, as doing so can cause duplicate side effects if the client does not know whether the previous request succeeded. Design idempotency keys/transactions for critical actions.

## 11. Cross-Origin SPAs: Getting CSRF Tokens Right

### 11.1. Why Do SPAs Need Special Handling?

Thymeleaf forms in the demo are server-rendered and use **RequestDataValueProcessor** to embed a CSRF hidden input. A JavaScript frontend on another origin has no backend-rendered form; it must have a **controlled mechanism to obtain a valid token** and send it in a custom HTTP header.

Example request from an SPA **once a token has been obtained**:

~~~javascript
async function createNote(csrfToken, note) {
  const res = await fetch(
    "https://api.example.test/api/notes",
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRF-TOKEN": csrfToken
      },
      body: new URLSearchParams({note}).toString()
    }
  );

  if (res.status === 401) {
    throw new Error("Login required");
  }
  if (res.status === 403) {
    throw new Error("Forbidden or invalid CSRF token");
  }
  if (!res.ok) {
    throw new Error("HTTP request failed");
  }
  return res.json();
}
~~~

**The code above does not generate `csrfToken`**. The token must be provided by the backend via a controlled flow such as a rendered HTML page, a dedicated endpoint, or an appropriate cookie repository; never hardcode it in the JavaScript bundle or pass it in query strings.

### 11.2. CookieCsrfTokenRepository and XSRF-TOKEN

Spring Security provides **CookieCsrfTokenRepository**, commonly used in SPAs with the **XSRF-TOKEN cookie** and **X-XSRF-TOKEN header** pattern. With **CookieCsrfTokenRepository.withHttpOnlyFalse()**, JavaScript can read the CSRF cookie when the cookie belongs to an accessible origin/scope. **This is not the JSESSIONID session cookie.** The session cookie should remain `HttpOnly`.

However, starting in Spring Security 6 there are several details to handle:

- **Deferred CSRF tokens:** tokens are not necessarily generated on every GET unless code requests them.
- **BREACH masking:** tokens placed in form/request attributes may be randomized/masked; raw tokens from cookies differ from masked form tokens.
- **CsrfTokenRequestHandler:** SPAs sending raw tokens in headers must be handled differently from forms submitting masked tokens. The documentation describes **SpaCsrfTokenRequestHandler** for this case.
- **CSRF token rotation:** after authentication/logout, old tokens may be cleared; the SPA must obtain a new token before the next POST.
- **403 is not always a token error:** it may be missing authorization; do not retry infinitely.

**Do not take a Spring Security 7 snippet and paste it straight into Security 6**: APIs/DSLs have changed. Follow the Spring Security documentation for your exact running version and write tests for token behavior after login/logout.

### 11.3. Frontend JS on Another Host Cannot Read a Host-Only API Cookie

If JavaScript runs on **app.example.test** while the CSRF cookie is **host-only** on **api.example.test**, the browser can send the API cookie on fetch, yet **`document.cookie` on `app.example.test` cannot read `api.example.test`'s cookie**. Two sites may share an eTLD+1, yet cookie visibility remains bound to the host.

Options to consider:

1. **Same-origin BFF/reverse proxy:** frontend and API sit behind one origin, simplifying cookie/token handling.
2. **Token-issuing endpoint** on the API: returns the token via JSON/headers with a strict CORS allowlist, session-bound and never publicly cached.
3. **Controlled shared Cookie Domain:** carefully evaluate subdomain trust, token leakage, and cookie injection risks; never widen `Domain` out of habit.
4. **Alternative token architecture:** if the API is truly stateless and uses no ambient cookies, the CSRF threat model differs, though every auth mechanism must still be audited.

### 11.4. SameSite=None Is Not a Silver Bullet for Every SPA

When frontend and API are **truly cross-site**, `SameSite=None; Secure` may be needed for browsers to send cookies in credentialed fetches. However, many browsers restrict third-party cookies, and setting `None` weakens `SameSite` defense. When a BFF/same-origin endpoint is feasible, that topology is generally more reliable. Never disable CSRF merely because `SameSite=None` is set.

## 12. When Is a CSRF Token Not Needed?

A **truly stateless** API where every request authenticates via a bearer token explicitly placed in the `Authorization` header by the client—with no session cookies, HTTP Basic, or other ambient browser credentials—can have a threat model that does not require synchronizer CSRF tokens for certain routes.

However, **there is no rule saying “REST APIs turn off CSRF”**. If the API still uses login cookies, form login, logout, or sessions, unsafe routes remain vulnerable to CSRF. When exempting a group of endpoints from CSRF, use precise scoping such as **csrf.ignoringRequestMatchers(...)** with documented justification and security review, rather than disabling it chain-wide. CORS and authorization must still remain enabled.

An upload/file-delete endpoint using explicit tokens also needs evaluation for request replay, idempotency, content types, session binding, and XSS; CSRF is not the sole layer of defense.

## 13. Impact of Reverse Proxies, HTTPS, and Spring Session

### 13.1. TLS Terminating at a Proxy

If browsers reach a reverse proxy over HTTPS while the proxy forwards internal HTTP to Spring Boot, `Secure` cookies and redirect URLs require proper configuration at the edge/Boot. The server should only trust **Forwarded/X-Forwarded-Proto** from controlled proxies, never forged headers from the public internet.

Test both the origin directly and via the proxy URL; compare **Set-Cookie, Cookie, Location, Scheme, Host, Port**, and `Origin`. A configuration that works on localhost can fail in staging if the browser sees cross-site or the proxy changes the scheme.

### 13.2. Sessions Across Multiple Replicas

If each instance holds local `HttpSession` state and the load balancer routes requests to another replica, users can receive 401 even though the cookie still exists. Use **Spring Session Redis/JDBC** or sticky routing with failover planning. With Spring Session, the cookie may be named **SESSION** instead of `JSESSIONID`. Both the CSRF token repository and session store must be consistent so POSTs hitting another replica do not randomly return 403.

### 13.3. Cookie Expiry Differs from Session Expiry

A session cookie can persist after the server removes `HttpSession`; a stale cookie carries no authentication. Conversely, `HttpSession` can remain on the server even if the client deletes its cookie, though it has no ID to look it up. Configure **server.servlet.session.timeout** and cookie `Max-Age` for their distinct purposes; never treat them as a single synchronized deadline.

### 13.4. Multi-Tab Behavior and Logout

A user may log out in one tab while another tab still holds an earlier CSRF token. Unsafe requests after logout must fail, and the UI should prompt re-login. After logging back in, never automatically replay side-effecting POSTs; refresh the CSRF token, check idempotency, and navigate safely.

## 14. Troubleshooting Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| OPTIONS returns 401 | CORS runs after authentication; preflight has no cookie | Integrate `http.cors` and test cookie-less OPTIONS. |
| Allow-Origin is wildcard with `credentials=true` | Invalid credentialed CORS rule | Allowlist specific origins. |
| GET succeeds yet POST returns 403 | Missing or stale CSRF token | Check hidden field/header, token repository, and lifecycle. |
| Browser CORS error, backend executes side effect | Simple request was sent, JS blocked from reading response | Enforce CSRF + authorization server-side; never rely on CORS. |
| Cookie not sent | `fetch` credentials, SameSite, Secure, Domain/Path, third-party blocking | Inspect Network tab instead of widening CORS origins. |
| Correct password on login yet 403 | POST `/login` missing CSRF | Use a form with token or valid token flow. |
| Session lost after redirect | Cookie Path/Domain, HTTP↔HTTPS, or reverse proxy | Compare effective URL and `Set-Cookie`. |
| Enabled `SameSite=None` yet cookie still dropped | Missing `Secure` or browser blocking third-party cookies | Use HTTPS; consider a BFF. |
| 403 after login in SPA | Token cleared/rotated, deferred/masked token | Refresh token and use Security 6-compatible request handler. |
| 403 calling endpoint from curl without Origin | Authorization or CSRF, not CORS | Check Principal, roles, and token. |
| API receives HTML login instead of JSON | Form login redirect applied to API | Separate API 401 entry point from UI redirects. |
| Multi-replica alternates between 200 and 401/403 | Local sessions/tokens not shared | Shared session store and consistent policy. |
| Cookie is `HttpOnly` yet still hit by CSRF | Cookies auto-send; `HttpOnly` only blocks JS reads | Keep CSRF tokens and `SameSite` defense-in-depth. |
| Data leaked via CDN/browser cache | Wrong `Cache-Control`/`Vary` | `no-store` for sensitive data, proper cache keys/authorization. |
| CSRF disabled to fix every POST | Ignoring cookie threat model | Restore CSRF and design proper token delivery. |

## 15. Browser Testing and Production Checklist

### 15.1. What to Inspect in DevTools

1. **Origin, Request URL**: identify exact scheme, host, port; distinguish sites.
2. **OPTIONS**: allowed methods/headers, status, Allow-Origin and Allow-Credentials, whether it hit 401/403.
3. **Actual Cookie**: did the browser send `JSESSIONID`/`SESSION`, is the cookie host-only or Domain, Path, SameSite, Secure.
4. **Set-Cookie**: did the browser reject the cookie due to `SameSite=None` missing `Secure`, third-party restrictions, or wrong domain.
5. **Request CSRF header/form field**: is the token present, named right, matching the session, and still valid.
6. **Response code**: 401 is authentication, 403 can be CSRF/authorization, browser CORS error is blocked read access.
7. **Redirects**: did fetch receive a 302 to HTML `/login`.
8. **Cache-Control**: do private responses specify `no-store`.
9. **Network topology**: TLS termination, forwarded headers, proxies/CDNs, and instances.
10. **Multi-tab state**: do logout/re-login update tokens and user state.

Never log or paste raw session cookies, CSRF tokens, passwords, or bearer tokens into bug reports. Use dedicated request IDs, redact sensitive data, and control retention.

### 15.2. Pre-Deployment Checklist

- [ ] CORS allows only **specific origins**, never combining wildcard with `allowCredentials=true`.
- [ ] **http.cors(...)** processes preflight before authentication/session filters.
- [ ] API paths, `allowedMethods`, and `allowedHeaders` are strictly scoped to actual needs.
- [ ] Unsafe methods using session cookies preserve CSRF protection or have a clear documented threat-model exemption.
- [ ] Form login/logout include tokens; never use GET to mutate state.
- [ ] Unauthenticated API requests return **401**, never unexpected HTML 200 after redirects.
- [ ] Logged-in users still receive **403** when lacking permissions; CSRF tokens do not replace authorization.
- [ ] Session cookies carry appropriate **HttpOnly, Secure over HTTPS, SameSite, and Path/Domain**.
- [ ] Do not confuse SameSite with CORS, and do not blindly set `Domain=.example.test`.
- [ ] SPAs have a mechanism to obtain/refresh CSRF tokens and handle Spring Security 6 BREACH/deferred tokens.
- [ ] Host-only API cookies are not assumed readable by frontend JS on another host.
- [ ] Cross-site cookies needing `None`/`Secure` are evaluated against third-party cookie restrictions.
- [ ] Private data is excluded from public shared caches; `Cache-Control: no-store` and proper `Vary` are set.
- [ ] Reverse proxies trust forwarded headers only from trusted sources.
- [ ] Clustered session stores and CSRF token repositories behave consistently across replicas.
- [ ] MockMvc tests cover 401, CORS preflight, forbidden origins, missing CSRF, and successful CSRF.
- [ ] Staging browser tests verify cookie delivery, logout, timeout, multi-tab behavior, and real HTTPS.
- [ ] Metrics/logs never expose session IDs, CSRF tokens, or credentials.

## 16. Self-Check Questions

**1. Is `app.example.test` calling `api.example.test` cross-origin?** Yes, because the hostnames differ, even though they may be same-site.

**2. Does CORS allowing an origin mean the user does not need to log in?** No. CORS is a browser read policy; authentication/authorization are independent.

**3. When `credentials=true`, can you return `Access-Control-Allow-Origin: *`?** Not for credentialed responses; specify an explicit origin.

**4. Must OPTIONS preflight include a session cookie?** No; preflights typically carry no cookies and must be handled by CORS before security authentication.

**5. Can another website blocked by CORS still trigger a POST side effect?** Yes, for instance via a simple form; you must rely on CSRF tokens and authorization.

**6. Does `HttpOnly` eliminate CSRF risk?** No. Cookies are still sent automatically even when JavaScript cannot read their values.

**7. Does `Lax` mean cookies are only sent same-origin?** No. `Lax` considers site, not origin.

**8. Why can `POST /login` return 403 even with the right password?** A CSRF token may be missing, because Spring Security protects login POSTs.

**9. Why can an SPA on `app.example.test` not read a host-only `XSRF-TOKEN` on `api.example.test`?** JS on a different host cannot read another host's cookies; you need a token endpoint or same-origin architecture.

**10. When can you evaluate disabling CSRF for an API?** When the API is truly stateless and does not rely on credentials automatically sent by browsers, with a clear threat model and route scope.

## 17. References

1. [Spring Security — CORS (Servlet)](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS processed before security, cookie-less preflight, `CorsConfigurationSource`.
2. [Spring Security — CSRF (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): token pattern, HTML forms, JavaScript SPAs, deferred CSRF, BREACH, and tests.
3. [Spring Security — CSRF MockMvc Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `with(csrf())` and positive/negative tests.
4. [Spring Boot 3.3 — Servlet Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): SameSite cookies and embedded servlet configuration.
5. [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `server.servlet.session.cookie.*`, timeout.
6. [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): cross-origin, preflight, credentials.
7. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie): `HttpOnly`, `Secure`, `SameSite`, `Domain`, `Path`.
8. [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF defenses and SameSite limitations.

**Summary:** **CORS** governs JavaScript's permission to read cross-origin responses; **session cookies** carry session IDs that browsers can attach automatically; **CSRF protection** shields unsafe requests against that automation; **authorization** decides whether the user has permission to act. In Spring Boot, integrate CORS before security, keep CSRF enabled for cookie login flows, configure `HttpOnly`/`Secure`/`SameSite` to match your site topology, and verify in real browsers rather than relying solely on MockMvc or curl.