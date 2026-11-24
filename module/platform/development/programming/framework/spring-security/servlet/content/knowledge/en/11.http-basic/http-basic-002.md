# BasicAuthenticationFilter and AuthenticationEntryPoint in Spring Security Servlet

> **Context:** Spring Security 6 on the Servlet stack, Java 17+; the Spring Boot 3.3.5 example runs an embedded Tomcat application. The main focus is how `BasicAuthenticationFilter` turns HTTP Basic credentials into an authentication request and how `AuthenticationEntryPoint` responds to the client with **HTTP 401 / WWW-Authenticate**. Clearly distinguish this from form login, authorization, CSRF, and session mechanisms.

## 1. HTTP Basic: The Path of Username and Password

With HTTP Basic, the client sends an `Authorization` header with the `Basic` scheme and a Base64 string representing `username:password`:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic dXNlcjpwYXNz
```

In this syntax example, `dXNlcjpwYXNz` is the Base64 encoding of `user:pass`. Base64 is **not secure encryption**: anyone who reads the header can recover the password. **HTTPS/TLS is mandatory** in real deployments; never write headers or decoded passwords to logs.

HTTP Basic has two distinct roles:

1. **`BasicAuthenticationFilter`**: the authentication filter. It recognizes the Basic header, reads username/password, creates an unauthenticated `Authentication`, and calls `AuthenticationManager`. On success, it populates the request's `SecurityContext`; on failure, it uses the appropriate authentication entry point.
2. **`AuthenticationEntryPoint`**: the contract that **initiates an authentication request** via an HTTP response. The `BasicAuthenticationEntryPoint` implementation typically returns **401 Unauthorized** and `WWW-Authenticate: Basic realm="..."`, letting the client know it should send Basic credentials.

Alongside these, `AuthorizationFilter`/authorization policy determines **which resources** an authenticated user may access. A valid password without the required role can result in **403 Forbidden**; that is not a `PasswordEncoder` failure or a sign that the Basic filter did not run.

### Quick Comparison with Form Login

| Aspect | HTTP Basic | Form login |
| --- | --- | --- |
| Credentials sent via | `Authorization: Basic ...` | `POST /login` with username/password |
| Typical filter | `BasicAuthenticationFilter` | `UsernamePasswordAuthenticationFilter` |
| Authentication needed for resource | Typically 401 + Basic challenge | Typically 302 redirect to `/login` page |
| How client maintains identity | Sends credentials per request or per client behavior/config | HTTP session/cookie commonly used |
| Experience | CLI, simple APIs, legacy systems | Browsers and HTML forms |
| Sending passwords over plain HTTP | **Insecure** | **Insecure** |

Do not pick a form-login entry point for a REST client merely because the system already has a `/login` page: the API will receive redirects/HTML instead of the right kind of challenge.

## 2. Spring Security Servlet Diagram When a Basic Header Is Present

```text
HTTP request
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy -> FilterChainProxy -> SecurityFilterChain
                                                |
                                                v
                                       BasicAuthenticationFilter
                                                |
                          +---------------------+-------------------+
                          |                                         |
                 Has Basic Authorization?                        Absent
                          |                                         |
                          v                                         v
                Read username/password                   Skip authentication,
                          |                               continue filters
                          v                                         |
           UsernamePasswordAuthenticationToken                      v
                 (not authenticated)                         AuthorizationFilter
                          |                                         |
                          v                              Endpoint requires login?
             AuthenticationManager                                  |
                          |                                         v
             ProviderManager/providers                    ExceptionTranslationFilter
                          |                                         |
             +------------+--------------+                          v
             |                           |                  AuthenticationEntryPoint
          Success                     Failure              (typically 401 challenge)
             |                           |
             v                           v
       Authenticated            AuthenticationException
       Authentication                    |
             |                           v
             v                    BasicAuthenticationFilter
      SecurityContext                 handles failure
             |                           |
             v                           v
       AuthorizationFilter        AuthenticationEntryPoint
             |                    (typically 401 challenge)
      +------+-------+
      |              |
  Authorized   Insufficient role
      |              |
   Controller      HTTP 403
```

The two 401 branches differ in nature:

- **No Basic header sent**: the filter may skip calling the manager. Later, an anonymous request is rejected by an `authenticated()` rule; `ExceptionTranslationFilter` decides to invoke `AuthenticationEntryPoint`.
- **Wrong username/password sent**: the Basic filter calls the manager, receives an `AuthenticationException`, and directly invokes the entry point or configured failure handling.

This helps you debug accurately: if there is no header, do not edit password-matching logic; if the header is present with the wrong password, inspect the authentication provider; if the password is right but you get 403, inspect authorities/rules/CSRF.

## 3. What Steps Does BasicAuthenticationFilter Perform?

### 3.1. Detecting and Reading Authorization

The filter looks for an `Authorization` header matching HTTP Basic. The string after `Basic ` is Base64-decoded to extract username/password separated by the first colon:

```text
username:password
         |
         v
    Base64 encode
         |
         v
Authorization: Basic <encoded-value>
```

If the username is `linh` and password is `demo123`, `curl --user linh:demo123` can generate the Basic header to test the flow. **Do not write real Base64 literals** into operational documentation or production logs.

Some HTTP Basic standard notes:

- Username should not contain a colon `:` because the first colon separates username/password; passwords can syntactically contain `:`.
- Syntactically valid Base64 does **not** prove valid credentials; the provider still has to check username and password.
- Encoding of non-ASCII characters requires agreement between client and server (see HTTP Basic charset rules, RFC 7617); do not assume all clients handle Unicode identically.
- Headers using another scheme, such as `Bearer`, are not verified as JWTs by `BasicAuthenticationFilter`. If the application needs Bearer, it must use the proper filter/provider/decoder.
- A malformed Basic header or wrong credentials can lead to an authentication error and challenge; exact behavior depends on the converter and configuration.

**Specifically:** an endpoint marked `permitAll()` does not make every authentication filter disappear. If a client deliberately sends a **bad Basic header** to a public URL, the Basic filter may still attempt authentication before reaching the `permitAll()` rule, resulting in 401.

### 3.2. Creating an Untrusted Authentication

Equivalent illustration:

```java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                usernameFromHeader, passwordFromHeader);
Authentication result = authenticationManager.authenticate(request);
```

This is an **explanatory fragment** (variables `usernameFromHeader`, `passwordFromHeader`, and `authenticationManager` must be supplied), not line-by-line internal source code of the filter. The request `Authentication` typically has `isAuthenticated()==false`, the initial username as principal, the password as credentials, and no granted authorities yet.

`AuthenticationManager` (usually `ProviderManager`) picks an `AuthenticationProvider` supporting `UsernamePasswordAuthenticationToken`. For accounts stored by username/password, `DaoAuthenticationProvider` uses `UserDetailsService` and `PasswordEncoder.matches(raw, storedHash)` to verify. Roles/authorities on the result must come from a **trusted source**, not from client-supplied JSON or headers.

### 3.3. When Authentication Succeeds

`AuthenticationManager.authenticate(...)` returns a trusted `Authentication`, typically with `isAuthenticated()==true`, principal, and authorities. The filter creates/updates the `SecurityContext` for the request so subsequent filters and controllers see the identity.

Keep in mind:

- `BasicAuthenticationFilter` does not decide which resources require `ROLE_ADMIN`; `authorizeHttpRequests` rules check permissions.
- `ProviderManager` typically tries to erase credentials on the result when the object implements `CredentialsContainer`. Do not rely on `getCredentials()` to read the password back after authentication, and never log raw credentials even before erasure.
- In some configurations, the Basic filter may check for an existing authentication in the context to avoid redundant authentication; however, do not infer that Basic **automatically creates a login session** or guarantees statelessness just from `httpBasic()`.
- `SecurityContextHolder` represents the current context. Whether the context is persisted across requests is a matter of `SecurityContextRepository` and session policy, not automatically dictated by the `AuthenticationManager` interface.

### 3.4. When Authentication Fails

If the provider throws `BadCredentialsException`, `DisabledException`, `LockedException`, or another `AuthenticationException`, the filter must not attach the result as an authenticated user. In a standard Basic flow, the entry point produces a 401 challenge.

A custom instance of `BasicAuthenticationFilter` may be configured differently, such as its `ignoreFailure` handling; therefore only draw conclusions from the actual response and filter chain rather than assuming all filter setups behave identically.

## 4. AuthenticationEntryPoint and BasicAuthenticationEntryPoint

The Servlet contract looks like:

```java
public interface AuthenticationEntryPoint {
    void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException authException)
            throws IOException, ServletException;
}
```

This is an **abbreviated signature** for explanation; the interface already exists in `org.springframework.security.web`. In Spring Security 6, Servlet APIs use **`jakarta.servlet.*`**, no longer `javax.servlet.*`.

`commence()` does not return an `Authentication`; it uses `HttpServletResponse` to emit an HTTP signal initiating authentication, for example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Learning API"
```

In HTTP Basic:

- **401** means there is not yet a valid authentication satisfying the requirement. This code can appear when **no credentials are sent** or when **credentials are wrong**.
- **`WWW-Authenticate`** communicates the challenge/scheme to the client, letting HTTP tools or browsers know which type of credentials to send.
- **`realm`** is the protection space name in the challenge, **not a role**. Realm `Learning API` does not grant `ROLE_ADMIN` and does not replace `UserDetailsService`.
- `BasicAuthenticationEntryPoint` is an implementation suited for Basic; `LoginUrlAuthenticationEntryPoint` is instead meant for redirecting to a form login page.

You can configure the realm via the Java DSL:

```java
http.httpBasic(basic -> basic.realmName("Learning API"));
```

This snippet belongs inside the `SecurityFilterChain` method and does not create a “realm database”. It sets the realm name for the default Basic challenge in that configuration.

### 4.1. 401 vs 403 and 302

| Response | Typical case | Cause |
| --- | --- | --- |
| **200** | Valid credentials and sufficient permissions; or public endpoint | Request processed |
| **401** | Anonymous access to `/api/me` | `ExceptionTranslationFilter` calls entry point when rule requires authentication |
| **401** | Basic header sent with wrong password | Basic filter/manager/provider fails, entry point creates challenge |
| **403** | Valid password but missing `ROLE_ADMIN` | `AuthorizationFilter` and access-denied handling |
| **403** | POST missing CSRF token when CSRF is enabled | `CsrfFilter` |
| **302** | Form login redirects to `/login` | Login URL entry point, not a standard Basic response |

An HTTP status alone does not tell you the exact exception. You must inspect filters, AuthenticationManager, authorization rules, handlers, request headers, and context.

### 4.2. Two Paths to a Basic Challenge

**Without Authorization:**

```text
GET /api/me, no Basic header
  -> BasicAuthenticationFilter skips authentication
  -> AuthorizationFilter blocks anonymous
  -> ExceptionTranslationFilter calls AuthenticationEntryPoint
  -> 401 + WWW-Authenticate: Basic realm="Learning API"
```

**Basic header with wrong password:**

```text
GET /api/me + invalid Basic credentials
  -> BasicAuthenticationFilter attempts authentication
  -> AuthenticationManager/DaoAuthenticationProvider
  -> BadCredentialsException
  -> BasicAuthenticationFilter handles failure
  -> AuthenticationEntryPoint
  -> 401 + WWW-Authenticate: Basic realm="Learning API"
```

**Authenticated but missing role:** authentication succeeds, `AuthorizationFilter` denies access with **403**, not “re-prompt for password”.

## 5. Runnable Example: Servlet Application with HTTP Basic

Let's build a Spring Boot 3.3.5 + Java 17+ application using Spring MVC (Servlet), Spring Security, and HTTP Basic. Three endpoints:

| Endpoint | Requirement | Expected result |
| --- | --- | --- |
| `GET /api/public` | Public | `public:ok` |
| `GET /api/me` | `authenticated()` | `me:<username>` |
| `GET /api/admin` | `hasRole("ADMIN")` | `admin:<username>` |

Use two accounts **for local practice only**:

| Username | Password | Role |
| --- | --- | --- |
| `linh` | `demo123` | `ROLE_USER` |
| `admin` | `demo123` | `ROLE_ADMIN` |

File layout:

```text
spring-basic-demo/
├── pom.xml
└── src/main/java/example/basic/
    ├── BasicDemoApplication.java
    ├── SecurityConfig.java
    └── ApiController.java
```

### 5.1. Create pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>spring-basic-demo</artifactId>
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
```

### 5.2. BasicDemoApplication.java

```java
package example.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicDemoApplication.class, args);
    }
}
```

### 5.3. SecurityConfig.java

```java
package example.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
        );

        // Enable BasicAuthenticationFilter and its corresponding entry point.
        http.httpBasic(basic -> basic.realmName("Learning API"));

        // Do not rely on HTTP session to keep SecurityContext across requests.
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        );

        // API does not need to store saved requests to redirect to an HTML login page.
        http.requestCache(cache -> cache
                .requestCache(new NullRequestCache())
        );

        // Keep default CSRF; this demo only uses GET.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails linh = User.withUsername("linh")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("demo123"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(linh, admin);
    }
}
```

Breakdown of the choices:

1. `httpBasic` enables header authentication filtering and the Basic entry point. `realmName("Learning API")` names the challenge.
2. `UserDetailsService` returns users with BCrypt-hashed passwords. Spring Security configures a suitable username/password provider; the filter delegates to the manager rather than checking passwords itself.
3. `SessionCreationPolicy.STATELESS` means Spring Security does not create/use an HTTP session to load/save `SecurityContext` **for this mechanism**; it does not prove no component anywhere in the system ever creates a session.
4. `NullRequestCache` avoids saving the protected URL for redirecting through form login and back. Basic is meant for HTTP clients that receive 401 and send credentials themselves, needing no HTML saved request.
5. `anyRequest().denyAll()` prevents accidentally exposing unlisted URLs. Method-specific `requestMatchers` clarifies the GET scope.
6. CSRF is kept at its default. The GET endpoints fit Basic testing; if adding POST/PUT/PATCH/DELETE, decide CSRF handling based on how clients send credentials rather than disabling it blindly.
7. The example uses a single `SecurityFilterChain` covering all URLs; in real mixed API/web apps you can split chains as shown in section 9.

**Note:** You do not need to define an `AuthenticationManager` manually in a simple example because Spring Security can build one from `UserDetailsService`/`PasswordEncoder`. When an app has multiple providers or custom managers, verify the wiring between Basic filter → manager → provider.

### 5.4. ApiController.java

```java
package example.basic;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public String publicData() {
        return "public:ok";
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
```

`Authentication` in the controller comes from the request's `SecurityContext` after the filter authenticates; `hasRole("ADMIN")` is checked **before the controller executes**. `@RestController` returns plain strings for easy stdout comparison, with no frontend/template needed.

### 5.5. Run

In the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

Under default configuration, Tomcat serves on `http://localhost:8080`. In production, deploy HTTP Basic only over **HTTPS**; the HTTP address here is for local learning.

## 6. Testing All Three Statuses 200, 401, 403 with curl

### 6.1. Public Without Authorization: 200

```bash
curl -s http://localhost:8080/api/public
```

Expected body:

```text
public:ok
```

`BasicAuthenticationFilter` skips authentication when no Basic header is present and the `permitAll()` rule allows the request.

### 6.2. Login-Protected Resource Without Header: 401

```bash
curl -i http://localhost:8080/api/me
```

Expect HTTP **401**. The response usually includes the challenge:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Learning API"
```

Those are the two relevant lines, **not a byte-for-byte full header dump**. The Basic filter has no data to authenticate; authorization then denies anonymous access and `ExceptionTranslationFilter` calls the Basic entry point.

### 6.3. Basic Header with Wrong Password: 401

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user linh:wrong-password http://localhost:8080/api/me
```

Expected result:

```text
401
```

`curl --user` generates the Basic header. This time `BasicAuthenticationFilter` actually passes a `UsernamePasswordAuthenticationToken` to `AuthenticationManager`; the provider detects an invalid password; filter/entry point returns 401.

### 6.4. Valid Username/Password: 200

```bash
curl -s --user linh:demo123 http://localhost:8080/api/me
```

Result:

```text
me:linh
```

The client must supply credentials on each new request; `STATELESS` does not make the next request automatically authenticated just because the previous one returned 200.

### 6.5. Authenticated but Missing ROLE_ADMIN: 403

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user linh:demo123 http://localhost:8080/api/admin
```

Result:

```text
403
```

`linh` is authenticated by the provider, but only holds `ROLE_USER`, failing `hasRole("ADMIN")`. This is an **authorization failure**, not an authentication failure.

### 6.6. Valid ADMIN: 200

```bash
curl -s --user admin:demo123 http://localhost:8080/api/admin
```

Result:

```text
admin:admin
```

No form session needs to be stored for the Basic demo; `curl` sends the Basic header on every invocation.

### 6.7. Expected Behavior Matrix

| Request | Basic filter | Authorization | Status/body |
| --- | --- | --- | --- |
| `GET /api/public` no header | Skips auth | `permitAll` | 200 `public:ok` |
| `GET /api/me` no header | Skips auth | Blocks anonymous | 401 + challenge |
| `GET /api/me` with `linh:wrong-password` | Auth fails | No authenticated context granted | 401 + challenge |
| `GET /api/me` with `linh:demo123` | Succeeds | `authenticated()` | 200 `me:linh` |
| `GET /api/admin` with `linh:demo123` | Succeeds | Missing `ROLE_ADMIN` | 403 |
| `GET /api/admin` with `admin:demo123` | Succeeds | Has `ROLE_ADMIN` | 200 `admin:admin` |
| `GET /api/public` actively sending bad Basic | May attempt auth and fail | `permitAll` does not disable auth filter | May return 401 |
| POST API without CSRF token | Depends on credentials | CSRF filter | Typically 403 |

Do not infer from `permitAll()` that a client can send an invalid Basic Authorization header and still always get 200: the authentication filter may fail **before** authorization rules apply.

## 7. Session, SecurityContext, and Browser Cache: Don't Confuse Them

HTTP Basic typically resends credentials rather than creating a form login session. Yet **`httpBasic()` alone does not guarantee the entire application is stateless**. A system may still have session login, request cache, remember-me, or custom filters.

The example explicitly configures:

```java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
http.requestCache(cache -> cache
        .requestCache(new NullRequestCache()));
```

`STATELESS` means Spring Security does not use `HttpSession` to retain `SecurityContext` across requests in the configured chain; **within a single request**, `SecurityContextHolder` still holds the authentication for authorization and controllers. `NullRequestCache` also avoids trying to redirect back to a saved request meant for form login.

Some browsers **cache Basic credentials on the client side** and automatically resend the header for matching protection spaces. Feeling “logged in” from a browser does not prove the server stored a session. This also makes logout harder: the server cannot always force a browser to clear its Basic credentials cache just via a logout endpoint. If you need clean logout, revocation, or MFA, consider a session/form flow or tokens with an explicit lifecycle.

## 8. Securing HTTP Basic: Easily Missed Issues

### HTTPS, Password Hashing, and Brute Force

- Base64 is **not secure**; passwords must be protected with HTTPS/TLS. Apply HSTS, proxy settings, and TLS suited to your deployment model.
- The server stores **password hashes** using a proper `PasswordEncoder` (BCrypt, Argon2, or a vetted scheme)—never plaintext, and never comparing Base64 strings against hashes.
- Rate-limit attempts, monitor credential stuffing, and apply risk-based lockout/step-up. `BasicAuthenticationFilter` does not provide full brute-force protection by itself.
- Never write raw `Authorization` headers, decoded username/password, Basic tokens, or reusable authentication secrets to logs/telemetry.

### CSRF When Browsers Auto-Send Credentials

**Never assume “HTTP Basic = stateless = no CSRF needed”.** Browsers can automatically resend cached credentials. If a browser client attaches credentials automatically, state-changing requests may need CSRF protection depending on architecture and threat model.

In the demo, default CSRF is kept because endpoints are GET-only. When adding POST/PUT/DELETE, identify the clients (browser, SPA, mobile, backend), whether credentials are sent automatically or explicitly, CORS, and required defenses. An API **accepting only Bearer tokens explicitly sent in headers** may have a different CSRF policy from a browser using cookies or cached Basic; do not disable CSRF site-wide just to make one curl POST work.

### Realm and Access Control

`realm="Learning API"` belongs to the HTTP challenge, **not `ROLE_ADMIN`**. Configuring a realm does not determine which user may view a resource; permissions are still governed by `authorizeHttpRequests`/method security and authorities from a trusted source.

## 9. Customizing AuthenticationEntryPoint for API Needs

If you need a JSON 401 response while still using HTTP Basic, you can customize the entry point. The replacement fragment below goes inside the `HttpSecurity` configuration method:

```java
http.httpBasic(basic -> basic.authenticationEntryPoint(
        (request, response, exception) -> {
            response.setStatus(401);
            response.setContentType("application/json;charset=UTF-8");
            response.setHeader("WWW-Authenticate",
                    "Basic realm=\"Learning API\"");
            response.getWriter().write("{\"error\":\"unauthorized\"}");
        }
));
```

This is a **replacement fragment for `http.httpBasic(basic -> basic.realmName(...))`** in the runnable example—do not apply both at once. The `WWW-Authenticate` header preserves the Basic challenge for clients. Never return detailed `AuthenticationException` messages, stack traces, username existence status, or passwords in the JSON.

If the HTTP response must produce a JSON body and consistent behavior across both the filter failure path and the `ExceptionTranslationFilter` anonymous path, test **both missing headers and invalid credentials**. When integrating multiple chains/entry points, content negotiation or client headers may affect which entry point is actually selected.

Some clients/browsers show a username/password prompt upon receiving a Basic challenge; that is **client** behavior, not a server-generated HTML form. If you want to avoid browser prompts or need custom login UX, choose another mechanism rather than merely changing status codes.

## 10. Combining Web Forms and REST APIs

If a Servlet application serves both a web UI and an API, a clean policy is typically:

- API `/api/**`: Basic or Bearer, entry point returning 401/403, separate stateless/request cache setup.
- Web UI: form login, sessions, and HTML redirect entry point.

Example **replacement fragment** (do not combine directly into section 5's runnable code):

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.httpBasic(basic -> basic.realmName("Learning API"));
    http.sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
    http.requestCache(cache -> cache
            .requestCache(new NullRequestCache()));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
```

This fragment requires `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `SessionCreationPolicy`, `NullRequestCache`, `Customizer`, and their imports. It illustrates how to split chains, **not a standalone Java class to paste directly**. Place the specific API chain at `@Order(1)` and the WEB fallback at `@Order(2)` so the web form does not “hijack” API URLs and redirect to an HTML login page. Also ensure the login route belongs to the web chain with `formLogin`.

Remember the distinction: `http.securityMatcher("/api/**")` selects **which chain applies**, whereas `authorizeHttpRequests().requestMatchers(...)` selects **policies inside that chain**. A request enters only the first matching chain, not both sequentially.

## 11. Common Issues and How to Diagnose Them

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| API returns 302 to `/login` instead of 401 | Web chain/form entry point selected | Chain order, matcher, entry point type |
| 401 despite sending Basic | Bad Base64 header, wrong password, disabled/locked user, or missing provider | Converter, manager/provider, encoder, account status |
| 401 missing `WWW-Authenticate` | Custom entry point omits the header or another mechanism ran | Selected filter/entry point, response headers |
| Browser pops up username/password dialog | Browser reacting to Basic challenge | Client behavior, not `UsernamePasswordAuthenticationFilter` |
| Public URL gets 401 when sending bad Basic | Filter attempts auth before `permitAll` authorization | Don't send bad header; check filter behavior |
| 403 with valid password | Missing role/authority or CSRF | Authorization rules, access-denied handler, CSRF |
| First request 200, next request 401 | API is stateless, next request lacks credentials | Client sends Authorization on every request |
| GET `/api/me` succeeds without credentials | Route misconfigured or context/session still has Authentication | Rules, security chain, and session/context |
| POST API returns 403 | CSRF enabled for unsafe methods | Design CSRF per client type, don't disable blindly |
| Basic mis-decodes Unicode | Client/server use different charsets | RFC 7617 conventions, client behavior |
| “Logged out” yet browser stays Basic logged in | Browser caches credentials independently | Choose session/token mechanism with proper revocation |
| JWT rejected by Basic filter | Basic does not verify Bearer automatically | Switch to appropriate JWT Resource Server |

### Debugging in Logical Order

1. Inspect the actual request (method, URL, `Accept`, Authorization scheme type), **without printing secrets**.
2. Verify which `SecurityFilterChain` was selected and whether `BasicAuthenticationFilter` is present.
3. If the Basic header is absent, inspect authorization rules and the anonymous entry point.
4. If the Basic header is present, check whether the converter builds the right token, whether manager/provider supports it, and whether password/account flags are valid.
5. If authentication succeeded, check `getAuthorities()`, `hasRole()`/`hasAuthority()`, and policies.
6. For 401, inspect `WWW-Authenticate`, entry point, and realm config; for 403, inspect rules or `CsrfFilter`.
7. For browser/cross-origin requests, check CORS preflight, cookies, Basic credential caching, and proxy headers.
8. Verify stateless session policy and context storage; never infer from `httpBasic()` alone.

Logging can be enabled in development:

```properties
logging.level.org.springframework.security=DEBUG
```

Log only safe information; never enable logging/tracing that exposes Basic credentials or `Authorization` headers in production.

## 12. Self-Check Questions and Checklist

1. **What data does BasicAuthenticationFilter receive?** `Authorization: Basic <base64(username:password)>`; it passes the request to `AuthenticationManager`.
2. **Does AuthenticationEntryPoint verify passwords?** No; it uses `HttpServletResponse` to initiate authentication, typically a 401 Basic challenge.
3. **Why does a missing header still return 401?** `AuthorizationFilter` blocks anonymous access, and `ExceptionTranslationFilter` invokes the entry point.
4. **Why does a wrong password still return 401 even though Authorization was sent?** The filter invokes manager/provider, authentication fails, and the entry point returns a challenge.
5. **Why 403 with the right password?** Authenticated, but lacking permission or denied by another policy such as CSRF.
6. **Is realm `Learning API` a role?** No, it is only the Basic challenge protection space name.
7. **Does Base64 securely encrypt passwords?** No; HTTPS must be used.
8. **Does HTTP Basic automatically create a session?** You cannot conclude that from the scheme name alone; check session/context policies.
9. **Are POST requests with HTTP Basic always exempt from CSRF?** No; browsers may resend credentials automatically, so evaluate the threat model.
10. **Does `permitAll` disable BasicAuthenticationFilter on public URLs?** No; an explicitly sent invalid Basic header can still trigger a 401.

Implementation checklist:

- [ ] Use `BasicAuthenticationFilter` in the right chain and a manager/provider capable of authenticating username/password.
- [ ] Verify entry point, 401 status, and `WWW-Authenticate` header when clients need a Basic challenge.
- [ ] Separate 401 authentication failure from 403 authorization/CSRF denial.
- [ ] Protect credentials with HTTPS, a suitable encoder, rate limiting, and safe logging practices.
- [ ] If statelessness is needed, configure and test `SessionCreationPolicy.STATELESS` along with context/request cache.
- [ ] Evaluate CSRF when browsers can auto-attach credentials; do not disable it globally without analysis.
- [ ] For web + API, separate chains/entry points so the API never redirects to an HTML login page.
- [ ] Thoroughly test public, anonymous, wrong credentials, valid credentials, missing role, custom entry point, and subsequent requests.
- [ ] If logout, MFA, or access revocation is needed, consider mechanisms better suited than long-lived Basic credentials.

**Conclusion:** `BasicAuthenticationFilter` handles **the Basic Authorization header and identity authentication**, `AuthenticationEntryPoint` handles **the HTTP signal requesting login** (typically **401 + `WWW-Authenticate`**), and `AuthorizationFilter` decides **whether the authenticated identity may access the resource**. Clearly understanding these three responsibilities lets you analyze 200/401/403 accurately and design safer APIs.