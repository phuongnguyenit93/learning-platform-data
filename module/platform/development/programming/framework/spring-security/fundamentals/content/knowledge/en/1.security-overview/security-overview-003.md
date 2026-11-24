# Why Applications Need a Security Library Instead of Manual Checks in Every Controller

> **Context:** Java web application using Spring Boot, Spring MVC (Servlet), and Spring Security. The goal of this lesson is to understand **why security must be a cross-cutting mechanism across the application**, as well as which parts the library handles and which parts remain business responsibilities.

## 1. The Problem: Is a Check Inside a Controller Enough?

Suppose a report management application has three APIs:

- GET /api/public: readable by anyone.
- GET /api/profile: logged-in users only.
- GET /api/admin: administrators only.

A manual approach often starts with a check statement inside each Controller: look up the user in the session, read the role, and return 401 or 403. When there are many Controllers, each group of developers may implement a slightly different variant. Simply forgetting a check on one new endpoint, or checking only "is logged in" while forgetting access permissions, can expose resources.

Example of what is **wrong and must not be used**:

~~~java
// Snippet illustrating an anti-pattern, not a standalone program.
@GetMapping("/api/admin")
public ResponseEntity<String> admin(HttpServletRequest request) {
    String role = request.getHeader("X-Role"); // Data sent by the client itself!
    if (!"ADMIN".equals(role)) {
        return ResponseEntity.status(403).build();
    }
    return ResponseEntity.ok("admin");
}
~~~

A client can send the header X-Role: ADMIN itself; therefore this is **not** a way to authenticate identity or prove permission. Even if you replace the header with a self-managed session, the application still has to properly implement login, state storage, session expiration, anti-forgery, error handling, and protection of every entry point. The risk lies in **the entire fragmented security system**, not just inside an `if` statement.

Another scenario: user A is logged in and requests GET /api/orders/42, but order 42 belongs to user B. Checking "is logged in" is not enough; you must check **permission on the order object itself**. The security library supplies the identity and policy-enforcement mechanism, while the rule "who owns order 42" usually needs to be checked in the business layer.

## 2. Distinguishing Authentication and Authorization

| Concept | Question | Example |
| --- | --- | --- |
| **Authentication** | Who is sending the request, and is the proof valid? | Checking login credentials, verifying a JWT issued by a trusted source. |
| **Authorization** | What is the authenticated entity allowed to do? | Only role ADMIN can enter /api/admin; only the owner can read their own orders. |
| **Security context** | Which identity/authorities are bound to the current request? | SecurityContextHolder stores the active Authentication used while processing the request. |

Common HTTP conventions:

- **401 Unauthorized**: the request lacks or fails valid authentication credentials; often accompanied by an authentication challenge (such as WWW-Authenticate for HTTP Basic).
- **403 Forbidden**: the server understands the request but denies permission; for example, a logged-in user lacking the ADMIN role. CSRF can also lead to 403.
- **404 Not Found**: the resource/path does not exist, or the application deliberately hides the resource's existence. You should not infer that every 404 means proper protection is in place.

**URL-level authorization** differs from **data-level authorization**: guarding /api/orders/** in a filter cannot by itself determine who each order record belongs to. The two layers must work together.

## 3. Risks of Writing Manual Checks in Every Controller

1. **Missing an entry point:** new endpoints, URL variants, different HTTP methods, and Controllers added later all need policies. A check on GET does not automatically protect POST.
2. **Duplicated logic and inconsistency:** one place returns 401, another returns 403, another fetches data before checking; changing policy requires editing many places.
3. **Trusting client-supplied input incorrectly:** a role header, a userId in the request, or a JWT that is only decoded without verifying its signature does not prove permission.
4. **Rolling password/session management is error-prone:** passwords must be hashed with an appropriate algorithm rather than stored in plain text; login sessions must be protected against hijacking and session fixation.
5. **Forgetting protocol-level defenses:** CSRF, security headers, unauthorized access handling, login, and logout mechanisms must be configured consistently for the application type.
6. **Hard to test and audit:** there is no central place to view URL policies, and it is very easy to miss "anonymous / regular user / admin" tests.
7. **Coupling security to business logic:** Controllers handle HTTP while repeating authentication plumbing, making code hard to maintain.

Building a complete authentication/authorization library yourself also requires tracking vulnerabilities, keeping up with standards, and continuous testing. A widely used framework reduces the number of security mechanisms you have to build yourself, though **misconfiguration still creates vulnerabilities**.

## 4. Where Does Spring Security Place Controls?

In a Spring MVC application, HTTP requests pass through Servlet Filters before reaching a Controller. Spring Security uses filtering to enforce centralized policies:

~~~text
Client HTTP request
        |
        v
Servlet Filter chain
        |
        v
DelegatingFilterProxy
        |
        v
FilterChainProxy -> matching SecurityFilterChain for the request
        |            (authentication filters, security context,
        |             protections, and authorization per configuration)
        v
DispatcherServlet -> Controller -> Service -> Repository
        |
        v
HTTP response
~~~

Components to understand at a basic level:

- **SecurityFilterChain:** a collection of filters and rules applied to matching requests. Can be declared as a bean in Spring Boot.
- **Authentication:** represents a verified identity, principal information, and authorities. Do not assume a username in a header is a valid Authentication.
- **SecurityContextHolder:** access point for SecurityContext on an appropriate processing thread. Propagating context to other/async threads requires supported mechanisms; do not assume automatic propagation.
- **AuthenticationProvider / AuthenticationManager:** components that verify configured credential types.
- **Authorization:** rules such as permitAll(), authenticated(), hasRole(), and hasAuthority() evaluated consistently at the appropriate layer.
- **PasswordEncoder:** generates and matches password hashes, such as BCrypt; cannot be replaced by plain-text comparison.

This is a conceptual model; actual filter order depends on configuration and the login mechanism. A request can be rejected **before the Controller runs**. In modern Spring Security, declaring a SecurityFilterChain as a bean is the standard approach, rather than extending the removed WebSecurityConfigurerAdapter.

When rules are needed at method invocation time (such as only ADMIN being allowed to export reports), Spring Security also supports **method security** like @PreAuthorize when @EnableMethodSecurity is enabled. This layer complements URL policies, especially when a Service has multiple callers.

## 5. Runnable Example with Spring Boot and Java 17

This example uses **HTTP Basic and in-memory accounts to study the mechanism**; it does not implement real login or a production account system. All endpoints are GET to focus on authentication/authorization. Default CSRF is not disabled.

Requirements: JDK 17+, Maven 3.9+, Spring Boot 3.3.6 (an example in the 3.3.x line), and the Spring Web and Spring Security dependencies.

**File pom.xml**:

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
    <artifactId>security-demo</artifactId>
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

**File src/main/java/com/example/securitydemo/SecurityDemoApplication.java**:

~~~java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
~~~

**File src/main/java/com/example/securitydemo/ApiController.java**:

~~~java
package com.example.securitydemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "profile:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }
}
~~~

**File src/main/java/com/example/securitydemo/SecurityConfig.java**:

~~~java
package com.example.securitydemo;

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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/profile").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo-reader"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
~~~

**Configuration analysis:**

- /api/public uses permitAll(): no identity required.
- /api/profile uses authenticated(): only requires a valid login, not the ADMIN role.
- /api/admin uses hasRole("ADMIN"): Spring Security checks for an authority formatted as **ROLE_ADMIN**. hasAuthority("ADMIN") is a different condition; do not confuse the ROLE_ prefix.
- anyRequest().denyAll(): denies any request not matched by the rules above by default, reducing the risk of accidentally exposing new APIs. Narrow/specific rules should appear before general rules.
- httpBasic(): Spring Security accepts credentials, verifies them against UserDetailsService and PasswordEncoder, constructs an Authentication, and then evaluates permissions.
- Both passwords are for **demo** use only. BCryptPasswordEncoder stores a hash in memory rather than keeping plain text in UserDetails. Production requires properly managed identities/secrets, HTTPS, lock policies, and proper account management.

**Run the program** in the directory containing pom.xml:

~~~bash
mvn test
mvn spring-boot:run
~~~

In another terminal, test in sequence:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/profile
curl -i -u reader:demo-reader http://localhost:8080/api/profile
curl -i -u reader:demo-reader http://localhost:8080/api/admin
curl -i -u admin:demo-admin http://localhost:8080/api/admin
~~~

**Expected results** (listing HTTP status codes and bodies, without pinning HTTP headers since they depend on the environment):

| Request | HTTP | Body or meaning |
| --- | --- | --- |
| GET /api/public, anonymous | 200 | public |
| GET /api/profile, anonymous | 401 | Authentication required |
| GET /api/profile, reader | 200 | profile:reader |
| GET /api/admin, reader | 403 | Authenticated but missing ROLE_ADMIN |
| GET /api/admin, admin | 200 | admin |

The example shows **there is no role-checking statement inside the Controller**, yet Spring Security still blocks the /api/admin path before executing the Controller method. The Controller focuses on handling requests and responses after access policies allow it.

HTTP Basic sends login credentials in a decodable form inside the Authorization header, **not as secret encryption**. Use it only with HTTPS when exchanging credentials over a network; never use demo account pairs as real accounts.

## 6. Testing Policies Instead of Only Testing the Happy Path

A secure configuration needs testing for **denied cases**. With the two test dependencies in pom.xml above, create src/test/java/com/example/securitydemo/SecurityAccessTests.java:

~~~java
package com.example.securitydemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityAccessTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessibleAnonymously() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void profileRejectsAnonymousUser() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("reader", "demo-reader")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("admin", "demo-admin")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }
}
~~~

Run **mvn test**. The four tests verify policy across "public / anonymous rejected / insufficient permission / sufficient permission". In a real system, you must add tests for other HTTP methods, new routes, other roles, non-ownership cases, expired or invalid-signature tokens, and corresponding CSRF flows.

## 7. What Must Still Be Checked in the Service or Controller?

Spring Security does not understand every business rule. Divide responsibilities:

| Layer | Should Be Responsible For |
| --- | --- |
| SecurityFilterChain | Authentication under the configured mechanism, URL/HTTP rules, blocking unauthorized requests, handling access failures. |
| Method security | Enforcing permissions on Service methods via @PreAuthorize or equivalent tools when needed. |
| Service/domain | Object ownership, tenant permissions, business state, permissions on specific data. |
| Controller | Receiving and validating appropriate input, passing the request into a use case, and building the response; avoid rebuilding login, session management, or reading roles from headers. |

For example, if the URL /api/orders/42 has passed the authenticated() rule, the Service must still verify whether the current user is allowed to read order 42. You can query by both **orderId and the ownerId retrieved from the authenticated identity**, or verify the owner before returning data. Taking ownerId from a client-supplied query parameter and trusting it as the current identity leads to **IDOR** risk (unauthorized object access by identifier).

To protect Service methods with annotations, you must configure @EnableMethodSecurity. @PreAuthorize("hasRole('ADMIN')") is a clear example for operations only administrators may invoke. Understand that method security typically relies on Spring proxies: invoking a protected method through a Spring bean triggers the check; internal **self-invocation** may bypass the proxy. Test through real entry points, not only by directly calling a manually instantiated object.

The library provides **the mechanism and enforcement points**, while developers still decide **the policy** and must prove the policy with tests.

## 8. Common Misconceptions When Applying It

- **CSRF:** protection against forged requests is critical when browsers automatically send cookies/sessions or credentials. The GET endpoints in the demo do not need CSRF tokens, but adding POST/PUT/DELETE can cause 403 if the token is missing. Do not disable CSRF just to make requests "work"; evaluate the authentication model, clients, and threat model before configuring.
- **CORS differs from authentication/authorization:** CORS controls how browsers share responses across origins. It does not grant roles and does not replace server-side token/permission checks.
- **JWTs must be verified:** merely base64-decoding the payload and trusting a "role" claim is insufficient. With OAuth2 Resource Server, use signature verification and validate relevant claims (issuer, expiration, audience when required by the system) according to a trusted configuration.
- **Passwords:** use an appropriate PasswordEncoder; do not store plain text, and do not invent ad-hoc hashing algorithms. InMemoryUserDetailsManager is only for demos and simple tests.
- **Deny by default:** the rule anyRequest().denyAll() prevents new endpoints from becoming public accidentally. However, you must pay attention to requestMatcher order and multiple SecurityFilterChains if the application uses them.
- **Role-based authorization is not enough:** role USER does not mean reading every other USER's data; object ownership controls are still needed.
- **Error messages and logs:** avoid leaking passwords, tokens, and sensitive data in logs or responses; record failed access attempts at the level needed for investigation.
- **Updates and configuration:** Spring Security removes the burden of building a security foundation, but does not fix bad policies or outdated dependencies automatically. Track patches and verify configurations in real deployment environments.

## 9. When Is Checking Directly in the Controller Reasonable?

A Controller can validate **input data or request-bound rules** (for example required parameters, formatting, valid state transitions) and read the Authentication already verified by Spring Security to display user info. That is different from the Controller taking on responsibility for **verifying credentials** or arbitrarily repeating role checks.

For object-level rules, move them into the Service to avoid omissions when the same business logic is invoked from REST, jobs, or message consumers. For defense in depth, combine URL, method, and data controls along their proper boundaries; do not force the entire policy into a single layer.

## 10. Self-Check Your Understanding

1. If a new API only checks "is logged in", what can happen when a user reads someone else's resource? **Hint:** object-level authorization flaw / IDOR.
2. When an anonymous user calls /api/profile and when reader calls /api/admin, why do the expected status codes differ? **Hint:** 401 for missing authentication, 403 for insufficient permissions.
3. Why is a request carrying the header X-Role: ADMIN not enough to prove a role? **Hint:** the client controls headers itself.
4. Why do you still have to test paths, HTTP methods, and data ownership when using Spring Security? **Hint:** the framework enforces the policies configured by the application; misconfiguration or flawed business logic still creates vulnerabilities.
5. Before disabling CSRF to let a POST request succeed, what must you determine? **Hint:** authentication mechanism, how the client sends credentials, forged-request risk, and token policy.

**Conclusion:** Using a library like Spring Security consolidates repetitive security plumbing into a unified configuration, guards requests before the Controller, and provides tools for authentication, authorization, protocol protection, and testing. Controllers/Services continue handling business logic and authorization on specific data. Security comes from **standard mechanisms, proper policies, and tests covering access paths**, not from scattering `if` statements throughout every Controller.
