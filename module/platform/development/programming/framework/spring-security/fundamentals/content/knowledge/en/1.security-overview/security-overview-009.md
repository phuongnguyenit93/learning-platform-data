# Prerequisites and Learning Sequence for Spring Security: From a Minimal Configuration to the Complete Processing Flow

## 1. Learning Objectives and Scope

This lesson answers two questions: **what do you need to know before learning Spring Security?** and **in what order should you learn so you progress from a small security configuration to explaining the entire request-processing flow?**

The destination is not merely writing a configuration that allows or denies URLs. After this roadmap, learners can:

1. Read an HTTP request and distinguish authentication data, sessions, tokens, HTTP methods, and response status codes.
2. Understand how Spring Boot creates a web application, Controllers, Beans, and the Servlet Filter system.
3. Distinguish **authentication**, **authorization**, roles/authorities, and data ownership checks.
4. Write a minimal **SecurityFilterChain**, create test accounts, use **PasswordEncoder**, and define which URLs may be accessed.
5. Trace a request from the client through filters, SecurityContext, permission checks, Controller, and out to the response.
6. Use authorized and unauthorized test cases to verify configuration; recognize why 200, 401, 403, or a login redirect occurs.
7. Know when to move on to CSRF, sessions, OAuth2/OIDC, Bearer tokens, method security, and security testing.

The hands-on example uses **Java 17+**, **Spring Boot 3.x**, and **Spring Security 6.x** on **Spring MVC/Servlet**. WebFlux has a reactive model and its own security configuration; do not apply Servlet HttpSecurity code directly to WebFlux.

## 2. Prerequisites Before Starting

You do not need to be a Java or Spring expert. However, the knowledge below is enough so you do not have to guess how the framework operates.

| Group | What You Need to Understand | Quick Self-Test |
| --- | --- | --- |
| Core Java | Class, interface, constructor, method, exception, annotation, lambda | Can read a Bean factory method and a configuration lambda |
| Spring Core | IoC container, Bean, dependency injection, @Configuration, @Bean, component scanning | Explain why a Controller receives a Spring-managed Service |
| Spring Boot | Starter, auto-configuration, application entry point, dependency setup | Understand what happens when adding a starter to the classpath |
| Spring MVC | @RestController, @GetMapping, @PostMapping, DispatcherServlet | Create a GET endpoint returning a string |
| Servlet | Filter, ServletRequest/Response, filter chain before Controller | Draw where filters sit ahead of DispatcherServlet |
| HTTP | GET/POST, URL, status 200/401/403/404, Authorization header | Distinguish missing credentials from insufficient permissions |
| Web state | Cookie, session, HTTPS; Bearer token concept | Know that browsers can automatically send cookies with requests |
| Basic security | Authentication, authorization, password hashing, least privilege | Explain why a successful login can still receive 403 |
| Tooling | JDK, Gradle/Maven, curl or Postman, application logs | Run a Boot app and send a request with headers |

### 2.1. Lock Down Four Concepts Before Writing Code

- **Authentication:** Verifying who is sending the request. The result is typically represented by an **Authentication** object.
- **Authorization:** Determining which actions the known identity is permitted to perform. Authorization can be enforced by URL, HTTP method, role, authority, or business data.
- **Principal:** The current identity, such as a username or an authenticated user object.
- **Authorities:** The set of permissions/permission labels attached to Authentication. Under standard configuration, **hasRole("ADMIN")** checks for the **ROLE_ADMIN** authority.

Example: account **learner** logs in successfully with authority **ROLE_USER**. When calling an endpoint requiring ADMIN, **authentication succeeds but authorization denies access**. Conversely, an unauthenticated caller hitting a private endpoint may be prompted to authenticate before reaching the Controller.

### 2.2. Understand HTTP Before Reading Security Configuration

An HTTP request has a method, URL, headers, and optionally a body. Example:

~~~http
GET /me HTTP/1.1
Host: localhost:8080
Authorization: Basic bGVhcm5lcjpsZWFybjEyMw==
~~~

The **Authorization: Basic** header carries the Base64 value of the username and password in the learning example. **Base64 is not secure encryption**; Basic Authentication should only be transmitted over **HTTPS** when communicating across a real network.

On the response side:

- **200 OK:** Valid request, processed successfully.
- **401 Unauthorized:** Valid authentication credentials are required, often accompanied by a challenge header for the active mechanism.
- **403 Forbidden:** Request is not permitted under the active policy; commonly authenticated with insufficient permissions, or due to a missing CSRF token.
- **302 Redirect:** With form login, an unauthenticated request may be redirected to a login page; not every configuration returns 401.
- **404 Not Found:** The application has no matching resource/handler, after earlier layers allowed the request through.

Do not guess response status codes solely from the URL. The authentication flow, authorization entry point, and exception handler determine the outcome.

## 3. Mental Model: From HTTP to Business Logic

Start with this simple diagram before inspecting framework interfaces:

~~~text
                         SPRING MVC / SERVLET
Client / curl
    |
    | HTTP request (path, method, headers, cookie/token)
    v
Servlet container (e.g., Tomcat)
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy
    |
    v
SecurityFilterChain matching the request
    |-- SecurityContext and related filters
    |-- Credential verification if needed
    |-- CSRF check when applicable
    |-- Authorization decision
    |       |
    |       +--> Invalid: 401 / 403 / redirect
    v
DispatcherServlet
    |
    v
Controller -> Service -> Repository
    |
    v
HTTP response
~~~

This is an **overview diagram**, not a claim of exact filter ordering across every configuration. Selecting a SecurityFilterChain depends on request matchers and the declared order of chains.

Components to understand in sequence:

1. **SecurityFilterChain:** List of security filters applied to a request. HttpSecurity configuration builds a chain for the Servlet stack.
2. **AuthenticationManager/AuthenticationProvider:** Performs credential verification for the appropriate authentication mechanism. For username/password, a provider can look up the user from UserDetailsService and verify the hashed password.
3. **SecurityContext:** Holds the active Authentication so subsequent checks know the principal and authorities.
4. **Authorization:** Compares Authentication against access policies to allow proceeding or deny.
5. **Controller/Service:** Invoked only after the request passes the chain's security checks; the business layer may still need to check resource ownership.

**Key point:** Spring Security does not simply "run inside Controllers". With Servlet, most HTTP access decisions happen in the **filter chain before the Controller**; method security can add another layer of checks closer to business logic.

## 4. Step-by-Step Learning Roadmap, From Minimal to Complete

| Stage | What to Do | What You Learn | Completion Criterion |
| --- | --- | --- | --- |
| 0. Basic Spring MVC | Create GET /public and GET /me | How requests reach a Controller | Call APIs and receive 200 |
| 1. Add dependency | Install starter-security, observe defaults | How auto-configuration can protect endpoints | Observe that APIs now require login |
| 2. URL rules | Declare SecurityFilterChain with permitAll, authenticated, hasRole | Authorization is expressed via policy | Accurately predict which endpoints are allowed |
| 3. Test identities | Configure PasswordEncoder and UserDetailsService | Account data, roles, and authentication process | Valid user calls /me successfully |
| 4. Small test suite | Test anonymous, wrong password, USER, ADMIN | Distinguish 200, 401, 403 | Results match the test table |
| 5. Trace a request | Step from Basic header through filters to Controller | Connect pieces into one flow | Can draw the flow and pinpoint where rejection occurs |
| 6. Business permissions | Add resource ownership checks in Service | Why roles are not enough for all data | User A cannot view User B's data |
| 7. Web security | Learn CSRF, session/cookie, CORS, HTTPS, and headers | Choose measures matching client types | Do not accidentally turn off needed protection layers |
| 8. Real architecture | Learn OAuth2/OIDC, Resource Server/JWT, method security, testing | Separate demos from production configuration | Explain the role of each component |

There is no need to learn all of OAuth2, JWT, or build an SSO server at stage 1. Each stage should create **one new observation**: first see the Controller run, then see requests blocked, next see the right user allowed, and finally explain every decision.

### Stage 0 — Have a Simple HTTP Application

Before adding Spring Security, make sure:

- The Boot application starts and listens on port 8080.
- A Controller can return a string at /public.
- You know how to inspect HTTP status codes with curl using the **-i** option.
- You understand Controllers belong to the Spring MVC pipeline; Beans are created and managed in the Spring container.

If not yet comfortable, review Spring Boot, dependency injection, and URL mapping. Errors creating Beans or endpoints are not Spring Security bugs.

### Stage 1 — Add the Starter and Observe Defaults

In a Spring Boot 3.x project using Gradle Groovy DSL, include these dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

When starter-security is present and the application has no custom security configuration yet, Boot typically protects endpoints with default settings, providing a test user with a random password in startup logs. That is **initial development behavior**, not a login system designed for production.

Ask yourself: why could the very same Controller be called directly without security, yet require login after adding a dependency? Being able to answer this shows you understand auto-configuration's impact on requests.

### Stage 2 — Write the Minimal Access Policy

Start by picking three clear requirements:

- **GET /public**: accessible even without logging in.
- **GET /me**: authenticated identities only.
- **GET /admin**: identities with the ADMIN role only.
- Every other endpoint: deny by default.

Why start with three cases? Because they let you directly observe the difference between **permitAll**, **authenticated**, and **hasRole**, before the system has multiple roles, data sources, or token mechanisms.

### Stage 3 — Have Real Identities to Test

Create two accounts **strictly for demo purposes**:

| Username | Demo Password | Authority from roles config | Observed Permission |
| --- | --- | --- | --- |
| learner | learn123 | ROLE_USER | Can call /me, cannot call /admin |
| admin | admin123 | ROLE_ADMIN | Can call /me and /admin |

Configure **UserDetailsService** to return two in-memory accounts; **PasswordEncoder** handles hashing and verifying passwords. This is the easiest way to observe authn/authz. For real applications, never hardcode usernames/passwords, never use demo accounts, and never rely on an in-memory store as a full user management system.

### Stage 4 — Dive Into Filters Only After Having Tests

For each endpoint, test at least four perspectives: anonymous, wrong password, valid USER, valid ADMIN. Once the result table stabilizes, pick **one concrete request** and trace how Spring Security receives credentials, authenticates, writes Authentication into SecurityContext, and compares authorities.

This is when framework classes make sense: they explain a behavior you have already observed over HTTP.

## 5. Runnable Example: Connecting Configuration and Requests

**Assumptions:** A Spring Boot 3.x, Java 17+ project created with Spring Initializr or configured with an equivalent Boot plugin; includes the two starters from stage 1 and the Gradle Wrapper. The example below is a **complete Java file**, not scattered snippets to stitch together manually.

Create **src/main/java/com/example/securitypath/SecurityPathApplication.java**:

~~~java
package com.example.securitypath;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityPathApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityPathApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/me")
    String currentUser(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

**Why this code is a controlled step forward:**

1. **SecurityPathApplication** is the Spring Boot entry point. **DemoController** sits in the same package and is discovered by component scanning.
2. The **SecurityFilterChain** bean defines the HTTP policy. Only GET is allowed according to the explicit matchers; remaining requests go to **denyAll**.
3. **httpBasic** allows passing username/password in headers when testing with curl. **formLogin** is intentionally disabled in the demo to observe 401 instead of being redirected to a login page.
4. **InMemoryUserDetailsManager** holds two test users. **roles("USER")** generates the **ROLE_USER** authority, and similarly **ROLE_ADMIN** for admin.
5. **BCryptPasswordEncoder** hashes passwords before creating users. Using plaintext strings in code is solely for illustration and is never how production passwords are stored.
6. **CSRF keeps its default configuration.** All three endpoints are GET, so you do not have to disable CSRF to test them. Do not use GET for real state-changing operations.
7. **Principal** in the /me endpoint shows that the authenticated current identity is passed down to the MVC layer. If the client is invalid, the request is rejected before this method runs.

Run the application from the project root directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell, use **.\gradlew.bat bootRun**. With Maven, use the project's corresponding Boot command. The requests below assume the server is running on **http://localhost:8080** strictly for personal study on your local machine.

Test each case with curl:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u learner:wrong http://localhost:8080/me
curl -i -u learner:learn123 http://localhost:8080/me
curl -i -u learner:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

On PowerShell you can use **curl.exe** to avoid shell aliases. Never send real credentials to endpoints without HTTPS.

**Expected result table** for this exact demo configuration:

| Request | Result | What Is Verified |
| --- | --- | --- |
| GET /public, not logged in | 200, body **public OK** | permitAll works |
| GET /me, not logged in | 401 | Endpoint requires authentication |
| GET /me, learner + wrong password | 401 | Credentials must be verified |
| GET /me, valid learner | 200, body **hello learner** | Has identity, satisfies authenticated |
| GET /admin, valid learner | 403 | Authn succeeded but lacks ROLE_ADMIN |
| GET /admin, valid admin | 200, body **admin OK** | Has ROLE_ADMIN so passes authorization |

These rows are **expectations deduced from configuration**, not measurements from a live server run inside this lesson. If there are other security chains, different exception handler settings, a reverse proxy, a context path, or different endpoint policies, actual responses may vary.

## 6. How Does One Concrete Request Travel the Whole Path?

Use **learner**'s **GET /admin** request as an example. It is valuable because it clearly highlights the point where **authentication succeeds but authorization fails**.

~~~text
curl -u learner:learn123 GET /admin
  |
  v
Tomcat -> DelegatingFilterProxy -> FilterChainProxy
  |
  v
SecurityFilterChain with relevant filters
  |
  +-- Receives Basic Authorization header
  |     |
  |     +-- Decodes credentials
  |     +-- AuthenticationManager / AuthenticationProvider
  |     +-- UserDetailsService looks up "learner"
  |     +-- PasswordEncoder verifies password
  |     +-- Success: Authentication(principal=learner, ROLE_USER)
  |
  +-- SecurityContext holds active Authentication
  |
  +-- Authorization checks GET /admin -> hasRole("ADMIN")
  |     |
  |     +-- Has ROLE_USER, lacks ROLE_ADMIN -> denied
  |
  v
403 Forbidden
(Controller /admin is never invoked)
~~~

**Case 1 — no credentials:** There is no valid Authentication to enter an endpoint requiring login. With HTTP Basic as in the demo, the framework triggers the authentication entry point and returns **401**, usually with a **WWW-Authenticate** header.

**Case 2 — wrong credentials:** Username/password verification fails, so no valid identity is produced to enter /me. With Basic, the outcome is **401**.

**Case 3 — learner accesses /me:** Authentication is verified with principal learner. The /me matcher requires **authenticated()**, so the Controller runs and returns **hello learner**.

**Case 4 — learner accesses /admin:** Authentication completes, but the ADMIN role requirement is not satisfied. The framework handles the access error and returns **403**; the Controller does not run.

**Case 5 — admin accesses /admin:** Authentication has **ROLE_ADMIN**, so authorization lets the request proceed to DispatcherServlet and the Controller; returns **admin OK**.

In the Servlet stack, **SecurityContextHolder** is the familiar access point to the active SecurityContext. How context is stored and propagated depends on configuration, request, session, and execution model; do not assume ThreadLocal propagates automatically across every asynchronous task. In WebFlux, the reactive security context uses a different mechanism.

### Rules for Reading Logs and Debugging

When a request fails, pinpoint **which stage it stopped at**:

1. Did the application start and register the endpoints?
2. Which security chain did the request enter, and was there a matching matcher?
3. Are credentials present, following the proper Basic, session, or Bearer scheme?
4. Did authentication succeed or fail? Does the user have the exact required authorities?
5. Did CSRF or another policy reject it before reaching the Controller?
6. If it reached the Controller/Service, are there business permission checks or exception handlers involved?

In development environments, you can enable logging for the Spring Security namespace to observe filters and access decisions, while controlling verbosity and avoiding writing credentials, tokens, or personal data to logs.

## 7. Expanding From URL Permissions to Business Permissions

A real application usually needs more than **hasRole("USER")**. For instance, API **GET /orders/123** requires a logged-in user. If order 123 belongs to another account, allowing every USER to read it causes a data access-control vulnerability (IDOR/BOLA).

Therefore follow two checking layers:

1. **HTTP layer:** The request must be authenticated, use the right method, and target a permitted URL.
2. **Business layer:** The Service loads the order and compares the order's owner against the current principal, unless policy allows an admin role to read that order.

Never compare against a client-supplied ownerId from the request. Ownership data must come from a trustworthy source like the database; the principal must come from the verified Authentication.

With method security, you can enable **@EnableMethodSecurity** and use **@PreAuthorize** for suitable checks. Understand that invoking methods through Spring proxies, annotation placement, and data access permissions all affect correctness. A role expression on a method does not automatically replace an owner check on the record.

When practicing, add two separate USER accounts with independent data; require that USER A cannot read USER B's records. Testing this **negative case** is just as important as testing that ADMIN can perform admin tasks.

## 8. Topics to Learn Next and a Logical Order

### 8.1. CSRF, Sessions, and Cookies

Websites using **session + cookie** typically have the browser automatically send cookies on subsequent requests. This maintains the session, yet introduces **CSRF** risk when another site triggers a state-changing request. Spring Security has a CSRF token mechanism in the Servlet stack. Learn how CSRF protects unsafe HTTP methods before deciding to adjust or disable it in your architecture.

Also review cookie flags (**Secure**, **HttpOnly**, **SameSite**), session fixation, logout, timeouts, and HTTPS. CORS governs browser access to cross-origin responses; **CORS does not replace CSRF, authentication, or authorization**.

### 8.2. Resource Server and Bearer Tokens

When clients pass a **Bearer access token** to an API, Spring Security can validate tokens via OAuth2 Resource Server configuration. With JWTs, verify signature, issuer, audience, expiration, and map claims to authorities according to policy.

**JWT is a token format**, not a complete login system. Adding starter-security alone does not issue JWTs, set up refresh tokens, revoke tokens, or protect resource ownership.

### 8.3. OAuth2 and OpenID Connect

OAuth2 is a family of delegated authorization standards; **OIDC** builds on OAuth2 to provide an authentication/identity layer. At the foundational level, distinguish:

- **Client:** Application using OAuth2/OIDC to request permissions or sign users in.
- **Authorization Server / Identity Provider:** Component issuing tokens and performing related authentication/authorization steps.
- **Resource Server:** API receiving and validating access tokens before returning data.
- **ID Token:** Contains identity claims in OIDC; does not automatically substitute for an access token when calling APIs.

Learn the role structure first; then implement concrete flows for browser, mobile, or service-to-service clients.

### 8.4. Method Security and Multiple Filter Chains

Once you understand one SecurityFilterChain, learn how to configure multiple chains for different request scopes, method-level policies with @EnableMethodSecurity, and interactions with exception handling. Pay close attention to **securityMatcher**, **requestMatchers**, chain ordering, and deny-by-default so endpoints are never inadvertently left uncovered.

## 9. Mistakes That Commonly Sidetrack Beginners

| Symptom | Common Cause | How to Verify |
| --- | --- | --- |
| Every endpoint requires login | Just added starter, using default security | Check whether a custom SecurityFilterChain exists yet |
| GET /public is still blocked | Matcher misses path/method or a different chain was selected | Check context path, matchers, and chain order |
| /me returns 401 even though user was created | Wrong credentials, password encoder, or Authorization header format | Test HTTP Basic with the configured account |
| /admin returns 403 for USER | Authenticated, but missing authority ROLE_ADMIN | Check hasRole and authorities |
| Browser login returns redirect instead of 401 | Form login/entry point differs from HTTP Basic | Inspect the configured login mechanism |
| POST returns 403 despite correct role | Likely missing CSRF token or another policy applies | Verify CSRF and request method before changing rules |
| App has roles yet leaks other users' data | Missing owner check at Service/Repository layer | Test cross-user data access between two USERs |
| Boot cannot find Controller | Wrong package/component scanning or application entry point | Check the package of @SpringBootApplication |
| Trying to use HttpSecurity with WebFlux | Confusing Servlet with the reactive stack | Check whether using spring-boot-starter-web or webflux |
| Thinking Base64 protects HTTP Basic passwords | Confusing encoding with encryption | Use TLS and never hardcode production credentials |

Do not "fix" a 403 error by adding permitAll to all URLs or disabling CSRF immediately. That may make a test pass while defeating the original protection goal.

## 10. Exercises to Verify Full-Flow Understanding

**Exercise A — predict before running:** Write down the outcome for the six requests in section 5's table without looking at the code. Then run and compare. If wrong, identify the corresponding matcher or authentication step.

**Exercise B — add an endpoint:** Add GET /reports to the Controller without adding a matcher. Predict why it does not automatically become public. Then configure only ADMIN to view /reports, and test USER and ADMIN.

**Exercise C — change role:** Change learner's role from USER to ADMIN in the demo, restart, and predict what changes for GET /admin. Explain via the **ROLE_ADMIN** authority.

**Exercise D — enforce permission at the data layer:** Describe the flow of GET /orders/123 where user A has role USER but the order belongs to user B. Point out which step must read the owner from real data and deny access.

**Exercise E — expand authentication:** Compare Basic with session cookies and JWT Bearer. For each mechanism, identify how credentials are sent, which component verifies them, session storage needs, and CSRF considerations.

You have mastered this knowledge track when you can **draw a request's flow yourself**, explain why 401/403/200 is returned, and recognize that **URL permissions and data permissions are two complementary responsibilities**.

## 11. Official References

- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Servlet Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/index.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Boot — Spring Security: https://docs.spring.io/spring-boot/reference/web/spring-security.html
