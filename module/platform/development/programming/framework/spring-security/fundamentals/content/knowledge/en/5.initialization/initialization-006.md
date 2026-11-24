# Creating Public and Authenticated Endpoints with Spring Security

An application typically has **public APIs**, such as an intro page or product catalog, and **APIs restricted to logged-in users**, such as profile information. In Spring Boot, creating two Controller methods is the first step; deciding who may call each endpoint belongs in **Spring Security's `SecurityFilterChain`** so policies are enforced consistently before requests reach the Controller.

This lab creates exactly two endpoints:

- **GET /api/public**: anyone, including unauthenticated callers, can invoke it.
- **GET /api/me**: the caller must hold an authenticated identity.

The example uses **Java 17+, Spring Boot 3.3.6, Spring Security 6.x, Maven, Spring MVC, and HTTP Basic** to make differences easy to observe. Accounts reside in memory and are solely for localhost practice. In real systems, login mechanisms, credential storage, and session/token management must be designed separately.

## 1. Lesson Goals

After completing this lesson, you will be able to:

1. Create a REST Controller with two GET endpoints.
2. Add the Spring Security dependency and write a **`SecurityFilterChain`** bean.
3. Use **`permitAll()`** to allow public access and **`authenticated()`** to require login.
4. Configure a demo account with **`UserDetailsService`** and **`PasswordEncoder`**.
5. Observe **200 OK** and **401 Unauthorized** responses with curl.
6. Write MockMvc tests covering anonymous access, valid/invalid credentials, and other HTTP methods.
7. Explain why "valid login" still differs from "permitted to perform every action."

This exercise requires no database, frontend, OAuth2, or JWT setup. Two endpoints suffice to see the protection mechanism in action and build a foundation for upcoming authorization lessons.

## 2. Understanding Request Flow Before Writing Code

For a GET request from a browser or curl, Spring Boot processes it roughly as follows:

~~~text
HTTP client
    |
    v
Servlet container (e.g., Tomcat)
    |
    v
DelegatingFilterProxy
    |
    v
Spring Security FilterChainProxy
    |
    v
SecurityFilterChain matching the request
    |-- handles SecurityContext / authentication when needed
    |-- checks authorization rules
    |
    +-- Not allowed ----> AuthenticationEntryPoint / denied handling
    |                         --> HTTP 401, 403, or configured response
    |
    +-- Allowed --------> DispatcherServlet
                              |
                              v
                         REST Controller
                              |
                              v
                         HTTP response
~~~

**Authentication** answers "who is the caller and is their proof valid?" **Authorization** answers "is this authenticated caller allowed to perform this request?"

In this lesson:

- `GET /api/public` uses **`permitAll()`**, so it is allowed without supplying an identity.
- `GET /api/me` uses **`authenticated()`**, so it reaches the Controller only after a valid `Authentication` exists via the configured mechanism.
- For an HTTP Basic API, a request to `/api/me` **with missing or invalid credentials** usually receives **401** with **`WWW-Authenticate`** signaling authentication is required.
- A user who is **authenticated yet lacks a required role or privilege** typically receives **403** when policy requires higher privileges. This lesson only requires "logged in," without an ADMIN-only endpoint yet.

Spring Security can reject requests **before the Controller**. Therefore, the absence of an `if` statement checking passwords inside the Controller is intentional: the Controller handles business logic, while the filter chain enforces access policy.

## 3. Preparing the Environment and Project Structure

Requirements:

- **JDK 17 or higher**, with `java` and `javac` available.
- **Maven 3.9+** or a suitable Maven Wrapper.
- Port 8080 free on localhost.
- An HTTP tool like curl; on Windows PowerShell you can use **`curl.exe`** to avoid alias conflicts on some versions.

Create the project directory:

~~~text
public-private-api/
├── pom.xml
└── src
    ├── main
    │   └── java
    │       └── com
    │           └── example
    │               └── accessdemo
    │                   ├── AccessDemoApplication.java
    │                   ├── ApiController.java
    │                   └── SecurityConfig.java
    └── test
        └── java
            └── com
                └── example
                    └── accessdemo
                        └── ApiAccessTests.java
~~~

All Java files use package **`com.example.accessdemo`**, matching the directory path. The class annotated with **`@SpringBootApplication`** sits in the root package so Spring Boot scans the Controller and Configuration in the same package automatically.

To check tool versions if needed:

~~~bash
java -version
javac -version
mvn -version
~~~

## 4. Declaring Maven Dependencies

Create **`pom.xml`** in the project root directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>public-private-api</artifactId>
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

Role of each dependency:

| Dependency | What is it used for? |
| --- | --- |
| spring-boot-starter-web | Builds REST APIs with Spring MVC, runs the embedded Servlet container, and serializes JSON via Jackson. |
| spring-boot-starter-security | Provides the security filter chain, authentication, authorization, and PasswordEncoder. |
| spring-boot-starter-test | JUnit 5, Spring Boot Test, MockMvc, and related testing tools. |
| spring-security-test | MockMvc request post-processors such as **`httpBasic()`**, **`csrf()`**, and security testing utilities. |

When the Spring Security starter is present without custom configuration, a Spring Boot app usually applies default protection. When you want **one public endpoint and one endpoint requiring authentication under a specific policy**, declare an explicit `SecurityFilterChain` rather than relying on the framework to guess your application's needs.

Version 3.3.6 is used in the example to keep the lab source code consistent. In production, use a supported Spring Boot/Spring Security line with current patches.

## 5. Creating the Spring Boot Entry Point Class

Create **`src/main/java/com/example/accessdemo/AccessDemoApplication.java`**:

~~~java
package com.example.accessdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccessDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AccessDemoApplication.class, args);
    }
}
~~~

Purpose:

- **`@SpringBootApplication`** enables Spring Boot's standard auto-configuration and component scanning.
- **`SpringApplication.run(...)`** starts the application and embedded server.
- No manual Servlet Filter registration is needed in the main class.

At this point the app can start with valid dependencies, though it has no business endpoints yet.

## 6. Creating Two Endpoints in a REST Controller

Create **`src/main/java/com/example/accessdemo/ApiController.java`**:

~~~java
package com.example.accessdemo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
~~~

**What happens in each method?**

- **`@RestController`** tells Spring MVC this controller writes return values to the response body. With **`Map`**, Jackson produces JSON.
- **`@RequestMapping("/api")`** prefixes both methods.
- **`@GetMapping("/public")`** maps to `GET /api/public`.
- **`@GetMapping("/me")`** maps to `GET /api/me`.
- The **`Authentication authentication`** parameter is resolved by Spring MVC from the request's security context once a user is authenticated. In this flow, the `/api/me` protection rule ensures the handler runs only after `authenticated()` succeeds.
- **`authentication.getName()`** returns the principal's name from the verified identity rather than trusting an arbitrary `userId`/`role` sent by the client.

Sample payloads:

~~~json
{"message":"public"}
~~~

and:

~~~json
{"username":"learner"}
~~~

Never write logic like **`if (request.getHeader("X-Role").equals("USER"))`** to determine identity yourself: clients can craft arbitrary headers. Let Spring Security verify credentials and enforce policies.

## 7. Declaring SecurityFilterChain: permitAll and authenticated

Create **`src/main/java/com/example/accessdemo/SecurityConfig.java`**:

~~~java
package com.example.accessdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

This is the **complete configuration** for the lab. You do not need `WebSecurityConfigurerAdapter`; modern configuration uses a **`SecurityFilterChain`** bean.

### 7.1. What Does Each Rule Mean?

~~~java
.requestMatchers(HttpMethod.GET, "/api/public").permitAll()
~~~

Allows **`GET /api/public`** even when the caller has no account. **`permitAll()` is an authorization rule**: it does not create a separate `SecurityFilterChain`, does not bypass all filters, and does not mean the server skips other checks. For instance, if a client sends an `Authorization` header with invalid HTTP Basic credentials, the authentication filter can reject the request before `permitAll` is ever evaluated. Thus when testing "public," call **without sending credentials**.

~~~java
.requestMatchers(HttpMethod.GET, "/api/me").authenticated()
~~~

Requires `GET /api/me` to have a **valid `Authentication`**. Spring Security verifies the identity via configured HTTP Basic. An account with role `USER` suffices because **`authenticated()` does not require a specific role**.

~~~java
.anyRequest().denyAll()
~~~

Denies any request not matched by the rules above. This prevents new endpoints from accidentally becoming public. However, it also means **other paths** (such as `GET /hello`, `POST /api/public`, or `/actuator/**` if present) are not permitted automatically. When adding features, add explicit policies and tests.

**Matcher order matters**: Spring Security evaluates rules in order and uses the first matching rule. Place specific rules before general ones. If **`anyRequest().denyAll()`** came first, subsequent rules would never be evaluated.

**`HttpMethod.GET`** distinguishes `GET /api/public` from `POST /api/public`. Specifying a public path without constraining the HTTP method can unintentionally expose mutating operations. Use method-specific matchers whenever business semantics call for it.

### 7.2. Why Use HTTP Basic in the First Lesson?

~~~java
.httpBasic(Customizer.withDefaults())
~~~

Enables handling **`Authorization: Basic ...`**. When a request arrives with credentials, Spring Security passes them to authentication components, checks the user and password via **`UserDetailsService`**/**`PasswordEncoder`**, builds an `Authentication`, and then runs authorization checks.

HTTP Basic is easy to invoke with curl and needs no login page. It has limitations:

- Credentials are **Base64**-encoded, not encrypted; use only over **HTTPS** on real networks.
- Clients typically send `Authorization` on every request; protect credentials, logs, and browser/cache behavior.
- It does not replace account lockout, MFA, password lifecycle, tokens, or user management outside this example's scope.
- HTTP Basic does not automatically make an app "stateless" in every sense; sessions/request caching and other filters still depend on configuration.
- If a browser automatically sends cached credentials, you still have to evaluate CSRF risk on state-changing requests.

This lesson **uses GET only**, so no CSRF token submission is needed. We do not disable Spring Security's default CSRF protection. When adding POST/PUT/PATCH/DELETE, design authentication and CSRF appropriately for your client types.

### 7.3. Demo Account, Password, and Role

~~~java
UserDetails learner = User.withUsername("learner")
    .password(encoder.encode("demo-password"))
    .roles("USER")
    .build();
~~~

- Username **`learner`**, demo password **`demo-password`**.
- **`BCryptPasswordEncoder`** creates the hash stored and matched inside `UserDetails`; plaintext passwords are not stored in the user's password property.
- **`InMemoryUserDetailsManager`** holds the account in memory. Restarting the app creates a fresh demo user.
- **`roles("USER")`** creates the **`ROLE_USER`** authority by convention. Yet `/api/me` only requires `authenticated()`, so the role is not a strict requirement in this lesson.

The demo password is in source code solely for learners to try. **Never deploy this account/password to public environments or use it for real data.** Production requires secret management and a proper identity store.

### 7.4. What This Configuration Does Not Solve Yet

Making an endpoint require login **is not the entirety of application security**:

- No real user management, password change, password reset, or MFA.
- No fine-grained role/permission authorization.
- No resource, `ownerId`, or tenant-level authorization.
- No OAuth2, OpenID Connect, or JWT Resource Server.
- No rate limiting, auditing, secret rotation, operational controls, or monitoring.
- No HTTPS/gateway configuration for deployment environments.

This is a foundation for understanding authentication and authorization decisions across two endpoints, not a full production template.

## 8. Running the Application and Observing Results

Open a terminal in the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

If startup succeeds, the embedded server usually listens at:

~~~text
http://localhost:8080
~~~

**The commands below use `curl.exe` on Windows**. On Linux/macOS, replace **`curl.exe`** with **`curl`**.

### 8.1. GET Public Endpoint Without Logging In

~~~powershell
curl.exe -i http://localhost:8080/api/public
~~~

Expected result:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"message":"public"}
~~~

Other headers may appear and header ordering is not fixed. What matters is **status 200** and JSON containing the `public` message.

**Why 200?** The **`permitAll()`** rule applies to `GET /api/public`. No `Authorization` header or login cookie is required.

### 8.2. GET Protected Endpoint Without Logging In

~~~powershell
curl.exe -i http://localhost:8080/api/me
~~~

Expected result: **401 Unauthorized** and an HTTP Basic challenge.

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"

~~~

The realm value, security headers, and error response body may vary with configuration. Do not hardcode the entire response. With HTTP Basic, **401** signals that the request needs valid credentials; `GET /api/me` does not enter the Controller's `me()` method in this case.

### 8.3. GET Protected Endpoint With the Right Account

~~~powershell
curl.exe -i -u learner:demo-password http://localhost:8080/api/me
~~~

Expected result:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"username":"learner"}
~~~

The **`-u`** flag makes curl construct an HTTP Basic `Authorization` header from the username/password pair. Spring Security verifies the password via `UserDetailsService` and `PasswordEncoder`, then checks `authenticated()` and allows the Controller to run.

**Never use `-u` with real passwords in shared/public examples**: secrets can leak into shell history or process arguments. Use dummy accounts on localhost only.

### 8.4. GET Protected Endpoint With the Wrong Password

~~~powershell
curl.exe -i -u learner:wrong-password http://localhost:8080/api/me
~~~

Expected result: **401 Unauthorized**. Even though the username exists, a wrong password does not produce a valid `Authentication`; the server denies access to `/api/me`.

In real APIs, authentication error messages should avoid revealing whether an account exists.

### 8.5. GET Public Endpoint Even Without Roles

You can open `http://localhost:8080/api/public` in a regular browser. At the web app level, the browser may render the JSON or download the response depending on browser behavior. If you open `http://localhost:8080/api/me`, the browser may pop up an HTTP Basic dialog depending on browser behavior and how the server issues the challenge. That is client behavior, not Spring Boot generating an HTML login form.

In this lesson, **`curl` is more reliable for inspecting exact status codes**, as it does not render login UIs or mask responses behind browser UX.

### 8.6. Quick Reference Table

| Method and Endpoint | Credentials | Expected | Reason |
| --- | --- | --- | --- |
| GET /api/public | None | **200** | Permitted by `permitAll()`. |
| GET /api/me | None | **401** | Unauthenticated; HTTP Basic challenge. |
| GET /api/me | learner / demo-password | **200** | Valid credentials, satisfies `authenticated()`. |
| GET /api/me | learner / wrong-password | **401** | Wrong password, authentication failed. |
| POST /api/public | learner / demo-password, with valid CSRF token | **403** | No rule allows POST; fallback `denyAll()`. |

For a POST request from curl **without a CSRF token**, Spring Security may return 403 from **`CsrfFilter`** before reaching authorization. Therefore seeing "POST /api/public returns 403" alone does not prove `denyAll()` was the cause. To test the GET matcher cleanly, include a valid CSRF token to isolate the CSRF filter's effect, as shown in the test section.

## 9. Writing Tests with MockMvc and Spring Security Test

Practice projects should include tests so nobody accidentally turns a protected endpoint public when changing configuration. Create:

**src/test/java/com/example/accessdemo/ApiAccessTests.java**

~~~java
package com.example.accessdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiAccessTests {

    @Autowired
    private MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void privateEndpointRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void privateEndpointAllowsValidBasicCredentials() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"));
    }

    @Test
    void privateEndpointRejectsWrongPassword() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicGetRuleDoesNotPermitPost() throws Exception {
        mvc.perform(post("/api/public")
                .with(httpBasic("learner", "demo-password"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void otherRouteIsDeniedForAuthenticatedUser() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("learner", "demo-password")))
            .andExpect(status().isForbidden());
    }
}
~~~

Run tests with Maven:

~~~bash
mvn test
~~~

**Expected result:** all six tests pass when code/configuration are correct and the environment is complete. Do not hardcode a `"Tests run: ..."` line from a specific Maven version because plugin output, timings, and logs vary.

### 9.1. Why Test Each of These Cases?

- **publicEndpointAllowsAnonymous**: proves the public endpoint requires no authentication.
- **privateEndpointRejectsAnonymous**: confirms the private route is blocked before the Controller.
- **privateEndpointAllowsValidBasicCredentials**: proves the valid path reaches the Controller and `Authentication` holds principal `learner`.
- **privateEndpointRejectsWrongPassword**: proves access controls cannot be bypassed by sending arbitrary `Authorization` headers.
- **publicGetRuleDoesNotPermitPost**: confirms the rule only allows GET. The test attaches **`csrf()`** so CSRF does not mask the authorization check, and supplies a valid user so the `denyAll()` fallback returns 403 rather than the unauthenticated branch.
- **otherRouteIsDeniedForAuthenticatedUser**: confirms fail-closed behavior: even logged-in users cannot call routes lacking an explicit policy.

When testing other endpoints with side effects, besides status codes also verify the database or messaging layer is unchanged when denied. A request returning 403 that still writes unauthorized data is a severe bug.

### 9.2. Do Tests Differ from Real curl Calls?

MockMvc invokes the Spring MVC stack and filters in the test context without opening a real HTTP port, making it great for checking routes and Spring Security policies. However, it does not prove TLS, reverse proxies, networking, or deployment configuration are right.

Use both:

- **MockMvc:** fast repeatable tests catching rule/auth/handler bugs.
- **curl/HTTP integration:** tests the real running application, statuses/headers, Basic challenges, and server paths.
- **Deployment testing:** verifies proxies, HTTPS, environment-specific properties, and management routes if any.

## 10. Common Mistakes When Creating Public and Protected Endpoints

### 10.1. Adding Spring Security and Suddenly Every URL Requires Login

When you add `spring-boot-starter-security`, Spring Boot can enable default security configuration. Without a declared `SecurityFilterChain`, previously public endpoints may begin requiring authentication. The fix is to **define an explicit policy**—do not remove the dependency just to skip the login screen.

### 10.2. Mistaking permitAll() for Skipping All Security

**`permitAll()`** grants authorization for that matcher, yet does not skip applied filters. Authentication, CSRF, security headers, and other controls remain active per configuration. Do not casually replace it with **`web.ignoring()`** for regular REST endpoints because bypassing the entire Spring Security filter chain also drops desired protections.

### 10.3. Controller URL and Matcher Do Not Align

For example, the Controller has `@RequestMapping("/api")` and `@GetMapping("/me")`, while `SecurityFilterChain` configures `"/me"` instead of `"/api/me"`. Consequently the real route misses the rule and may fall into `denyAll()`.

Always inspect the **final path** after combining Controller prefixes, context path, gateway rewrites, and exact HTTP methods. Never guess matchers from Java method names.

### 10.4. Declaring /api/public Without Restricting to GET

If you write:

~~~java
.requestMatchers("/api/public").permitAll()
~~~

the matcher does not constrain the HTTP method. If `POST /api/public` is added later, that request may pass the authorization layer even though it should have its own policy. Constrain matchers by HTTP method when business semantics require it.

### 10.5. Overly Broad anyRequest().permitAll()

~~~java
.anyRequest().permitAll()
~~~

This configuration can leave new endpoints publicly open unless preceded by stricter rules. This lesson uses **`anyRequest().denyAll()`** so every unlisted route requires an explicit decision.

When adding Actuator, static files, error pages, or a login UI later, update rules appropriately for each endpoint type; never open everything by default.

### 10.6. Believing Role USER Is Required by authenticated()

**`authenticated()`** only requires an identity authenticated under policy. It is not shorthand for **`hasRole("USER")`**. When a specific role is needed, add `hasRole`/`hasAuthority` matching your permission model and test per endpoint or method.

### 10.7. Calling the Right URL Yet Receiving 403 Instead of 401

Causes can vary:

- Valid principal rejected by policy.
- POST/PUT/DELETE missing a CSRF token when CSRF protection applies.
- A route missed every matcher and fell into `denyAll()`.
- A gateway or another filter actively denied the request.
- Custom authentication/authorization handlers changed the HTTP status.

Therefore debugging must examine **method, path, credentials, CSRF, chain match, and relevant logs**, rather than inferring solely from the status code.

### 10.8. Using HTTP Basic Over Plain HTTP in Real Systems

HTTP Basic sends credentials as Base64 in `Authorization`. This is **not encryption**. Use **HTTPS**, proper password/secret management, expiration, and auditing; never print `Authorization` or `Cookie` to logs and never use demo credentials.

### 10.9. Assuming Every 401 Originates Inside the Controller

For an anonymous `GET /api/me`, Spring Security can reject the request **before `ApiController.me()` runs**, via the Basic authentication entry point. Adding a `try/catch` inside the Controller cannot catch rejections from upstream filters. Customize 401/403 responses by configuring the appropriate security handlers when truly needed.

### 10.10. Confusing CORS with Authentication

If a JavaScript frontend runs on a different origin from the API, browsers also enforce **CORS**, sometimes with `OPTIONS` preflight requests. Curl is not blocked from reading responses by browser CORS policy. CORS never lets a user bypass Spring Security; `GET /api/me` still requires valid credentials even when `Access-Control-Allow-Origin` lets the browser read the response.

## 11. Extending Beyond the Basics

Once public vs. authenticated endpoints are clear, subsequent lessons typically increase complexity:

### 11.1. Role-Based Authorization

You can require role `ADMIN` for a dedicated URL:

~~~java
.requestMatchers(HttpMethod.GET, "/api/admin")
    .hasRole("ADMIN")
~~~

This is only an **illustrative configuration snippet**; the two-endpoint project above does not have that Controller method or an `ADMIN` role yet. When extending, add the matching endpoint and principal and test 403/200.

### 11.2. Data-Object-Level Authorization

For example, `GET /api/orders/42` may only require `authenticated()` at the URL layer, yet user A must not read order 42 belonging to user B. The service must verify **owner/tenant** permissions before returning data. A `SecurityFilterChain` checking URL roles does not automatically understand every business rule.

### 11.3. Moving from HTTP Basic to Bearer/JWT

For APIs acting as an OAuth2 Resource Server, clients send an `Authorization: Bearer` token, and the server must **verify signature or introspection, issuer, expiry, audience when required by policy, and scopes/authorities**. Simply decoding a JWT and trusting roles from its payload is insufficient. Conceptual `permitAll()`/`authenticated()` policies remain the same while the authentication mechanism changes.

### 11.4. Adding Write Operations

`POST /api/orders` or `PUT /api/profile` requires **action- and data-level authorization**, input validation, concurrency checks, and CSRF considerations matching how clients transmit credentials. Never disable CSRF merely to make curl POSTs succeed easily.

With browsers automatically sending cookies/sessions, CSRF protection is usually critical. With stateless APIs accepting only explicitly attached `Authorization: Bearer` tokens, the threat model and CSRF configuration can differ; tokens must still be protected against XSS and leakage.

### 11.5. Using Multiple SecurityFilterChains

Larger apps may need separate chains for `/api/**` and web form login with distinct ordering. In that case, verify **`securityMatcher`**, `@Order`, and fallbacks. Never configure a narrow chain and leave routes outside all chains accidentally unprotected. This lesson uses **a single chain** to stay focused on distinguishing public from authenticated.

## 12. Implementation and Self-Check Checklist

Before wrapping up this lesson, verify:

- **`GET /api/public`** works with a request carrying no `Authorization` header.
- **`GET /api/me`** without credentials receives 401 via HTTP Basic.
- **`GET /api/me`** with `learner`/`demo-password` receives JSON with username `learner`.
- **Wrong credentials** cannot access `/api/me`.
- **`POST /api/public`** is not exposed merely because `GET /api/public` is public.
- **New endpoints** are denied when no rule matches under fail-closed configuration.
- Configuration explicitly defines **`SecurityFilterChain`** and **`UserDetailsService`**.
- Passwords stored in `UserDetails` are hashed via **`PasswordEncoder`**.
- No real passwords/tokens are stored or logged; Basic over plain HTTP is never used outside isolated study environments.
- Run **`mvn test`** and test real HTTP requests on localhost.

**Self-Practice Questions:**

1. Why is `@GetMapping("/api/public")` not enough to declare a public endpoint when Spring Security is enabled?  
   **Hint:** Controller mappings handle routing; `SecurityFilterChain` decides authorization before the Controller.
2. What is the difference between `permitAll()` and `authenticated()`?  
   **Hint:** one rule permits anonymous callers, while the other requires a valid identity.
3. Why does anonymous `GET /api/me` usually return 401, while an authenticated user lacking a role usually returns 403?  
   **Hint:** distinguish authentication from authorization.
4. Why constrain `HttpMethod.GET` when you only intend to make a read endpoint public?  
   **Hint:** prevents unintentionally opening state-changing methods on the same path.
5. When `POST /api/public` returns 403, how do you tell whether it came from CSRF or `denyAll()`?  
   **Hint:** isolate CSRF using MockMvc `csrf()` and supply a valid identity to test the authorization rule separately.
6. Why are `InMemoryUserDetailsManager` and demo passwords unsuitable for production?  
   **Hint:** user management, secret lifecycle, credential protection, and operational scalability.
7. If you add `GET /api/orders/42`, is `authenticated()` alone enough to ensure user A cannot read B's order?  
   **Hint:** no; object-level permission checks are needed in the service/domain layer.

## Conclusion

To create one public endpoint and one authenticated endpoint in Spring Security, define the **Controller routes**, declare a **`SecurityFilterChain`** using **`permitAll()`** for the public route and **`authenticated()`** for the private route, and configure an appropriate authentication mechanism and user source. Test anonymous access, valid/invalid credentials, HTTP methods, and unlisted routes. This keeps Controllers focused on business logic while blocking unauthorized requests before data is touched; as the application grows, remember to layer in role-based and resource-specific authorization.
