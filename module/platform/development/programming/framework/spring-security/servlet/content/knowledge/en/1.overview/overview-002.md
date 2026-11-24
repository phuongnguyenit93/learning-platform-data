# Authentication, Authorization, and Exploit Protection: Three Related Responsibilities

In a **Spring Security application on the Servlet stack**, securing an HTTP request usually requires three independent yet coordinated decisions:

1. **Authentication:** who is sending the request, and is the proof of identity valid?
2. **Authorization:** is that identity allowed to perform the action on the specific resource?
3. **Exploit protection:** even for a request with a valid identity and permissions, is it abusing a vulnerable mechanism such as CSRF, page framing, login sessions, or malicious input data?

These three layers do not replace one another. Logging in successfully does not mean being able to read all data; being granted permission does not mean the request passed CSRF checks; enabling CSRF cannot fix a flaw that allows reading another user's data.

## 1. Distinguishing the Three Responsibilities

| Layer | Core Question | Commonly Used Inputs | Decision/Example |
| --- | --- | --- | --- |
| Authentication | "Who are you?" | Username/password, session, HTTP Basic, bearer token, certificate... | Build an Authentication object representing the identity; reject if authentication fails |
| Authorization | "What are you allowed to do with this resource?" | Authentication, authorities/roles, HTTP method, URL, owner, and business context | USER reads their own profile; ADMIN can access the admin page; unauthorized users are denied |
| Exploit protection | "Does this request violate anti-exploitation safeguards?" | HTTP method, CSRF token, cookie/session, headers, origin, URL structure... | Block POST missing a CSRF token in cookie-based apps; reduce clickjacking risk, handle abnormal requests |

A user named Lan can:
- Authenticate successfully via a session cookie.
- Be allowed to view her own order but be denied when requesting Minh's order.
- Be denied a POST request to change her address if the request lacks a valid CSRF token, even though Lan is logged in and has permission to edit her address.

**Principle:** check identity, access permissions, and anti-exploit measures at their appropriate places; passing an earlier layer does not automatically pass subsequent layers.

## 2. How Does a Request Pass Through Spring Security?

With Spring MVC/Servlet, the web application runs through a Servlet Filter chain before reaching DispatcherServlet and controllers. Conceptual diagram:

~~~text
Client HTTP request
    |
Servlet container
    |
DelegatingFilterProxy (springSecurityFilterChain)
    |
FilterChainProxy -> selects the SecurityFilterChain matching the request
    |
    +-- Loads/establishes security context (SecurityContextHolderFilter)
    +-- Filters for CORS, CSRF, security headers... if configured
    +-- Appropriate authentication filter (Basic, form login, bearer token...)
    +-- Anonymous handling, security exceptions
    +-- AuthorizationFilter checks access rules
    |
DispatcherServlet -> Controller -> Service -> resource
~~~

This is a **responsibility diagram**, not the exact order of every filter in all configurations. The actual filters present and their exact order depend on the Spring Security version, configuration, and authentication mechanism. You can enable DEBUG for org.springframework.security or inspect the filter chain at startup to find the actual chain.

Components to understand:

- **DelegatingFilterProxy** connects the Servlet container to the Spring Security bean; **FilterChainProxy** manages the SecurityFilterChains. If multiple chains exist, the **first matching** chain is selected. securityMatcher rules decide which chain applies; requestMatchers inside authorizeHttpRequests decide permissions *within* the chain.
- **SecurityContextHolder** provides the SecurityContext for the current execution thread; the context holds the Authentication if present. SecurityContextHolderFilter is part of the modern context reading/handling mechanism, while how context is persisted between requests depends on SecurityContextRepository and the authentication method.
- **Authentication** holds the principal (identity), credentials where applicable, and GrantedAuthorities (permissions). For username/password, AuthenticationManager typically delegates to an AuthenticationProvider to verify credentials; for bearer tokens, token authentication/decoding mechanisms follow their own path.
- **AnonymousAuthenticationFilter** can place an anonymous Authentication for unauthenticated requests. This is not an authenticated user identity capable of passing the authenticated() rule.
- **AuthorizationFilter** enforces the AuthorizationManager's decision on requests according to declared rules. Beyond URLs, method/service-level access control is often needed to prevent cross-resource access.
- **ExceptionTranslationFilter** translates security exceptions thrown downstream of it into appropriate HTTP behavior via AuthenticationEntryPoint or AccessDeniedHandler. The CSRF filter and other components also have their own request rejection paths; do not assume every error goes through the same filter.

Do not infer "reached the controller" merely because a request has a cookie or Authorization header: the request can be rejected before the controller, in the service, or by an exploit protection measure.

## 3. Authentication: Proving Identity

A typical username/password flow:

1. The client submits credentials to the configured login mechanism (form or HTTP Basic).
2. The filter receives the credentials and asks AuthenticationManager/AuthenticationProvider to verify against UserDetailsService, PasswordEncoder, or an identity system.
3. On success, Spring Security obtains an Authentication with a principal and authorities; SecurityContext is used for subsequent checks.
4. How identity is stored/retrieved on subsequent requests varies: browser sessions may use a session cookie; REST resource servers typically validate a bearer token on each request.

Distinctions to make:

- **HTTP Basic:** each request can send Authorization: Basic ...; the base64 string is just an encoding representation, **not security encryption**. HTTPS is mandatory.
- **Session login:** the browser usually sends cookies automatically for matching requests. Automatic cookie sending makes CSRF especially important for state-changing operations.
- **Bearer token/JWT:** the server verifies signature, expiration, issuer/audience/scope according to configuration; a valid token only proves what the token and trusted system permit, not blanket access to every resource.
- **Passwords:** production uses an appropriate PasswordEncoder such as BCrypt/Argon2 with key and account management policies; never store plaintext or use {noop} outside learning examples.

Failed authentication usually results in **401 Unauthorized** and an authentication challenge (for example, WWW-Authenticate with HTTP Basic). The status name is slightly misleading: 401 primarily indicates that valid authentication credentials are needed.

## 4. Authorization: Deciding Access Permissions

Once an identity context exists, authorization must cover both **functionality** and **data**:

- Request-level: permit GET /api/public without login; require authenticated() for /api/profile; require hasRole("ADMIN") for /api/admin.
- Method-level: check rules on services using @PreAuthorize when @EnableMethodSecurity is enabled. The annotated method call must be handled by Spring AOP; self-invocation within the same bean may bypass the proxy.
- Object-level: a user with role USER must still only view their own invoices or invoices belonging to an allowed organization. Checking roles only at the URL level is insufficient to prevent **IDOR/BOLA** (changing an ID in the path).

**Authority vs. role:** roles("ADMIN") in typical user configuration creates the authority ROLE_ADMIN; hasRole("ADMIN") checks the ROLE_ prefix by default. Conversely, hasAuthority("invoice:read") checks the exact granted permission string. Do not confuse roles with custom authority strings.

Design principles:

1. **Deny by default:** endpoints without explicitly declared permissions are denied; do not leave new endpoints accidentally public.
2. **Least privilege:** grant only the minimum required permissions on the right data scope.
3. **Server-side enforcement:** hiding buttons in the UI only improves UX, not authorization.
4. **Rule ordering:** specific rules should precede broader rules in authorizeHttpRequests because rules are evaluated in order.
5. **Business-layer checks:** verify owner/tenant/transaction state right when executing the action, even if URLs were already checked.

**403 Forbidden** is the typical result when an identity is valid but lacks permission. For unauthenticated users, Spring Security may choose 401 and require login first; the actual status code also depends on the configured entry point and handlers.

## 5. Exploit Protection: Adding Barriers for "Seemingly Valid" Requests

Spring Security provides many mechanisms, but not every type of attack is automatically mitigated.

| Risk | Appropriate Mechanism | Misconceptions to Avoid |
| --- | --- | --- |
| **CSRF**: another website triggers a data-modifying request under the victim's browser session | CSRF token bound/verified in flows with auto-sent credentials (such as session cookies) | Being logged in or having role EDITOR does not stop CSRF; CORS does not replace CSRF either |
| **Clickjacking**: an attacker embeds a page in a frame to trick user actions | Anti-framing headers (X-Frame-Options or CSP frame-ancestors) | Headers are only one layer; check the actual framing policy |
| **XSS**: untrusted data is interpreted as script | Context-appropriate output encoding, template escaping, actively configured CSP, input validation | Authentication and authorizeHttpRequests do not sanitize HTML or fix XSS |
| **Session abuse/fixation** | Session management, appropriate Secure/HttpOnly/SameSite cookies, session fixation protection, timeouts | Cookie flags cannot replace authorization or CSRF tokens |
| **Abnormal request URLs** | HttpFirewall and request normalization/control in the filter chain | Firewall does not replace input validation or business checks |
| **Brute force, API abuse, SQL injection, SSRF** | Rate limiting/MFA/monitoring, parameterized queries, URL/egress validation, and system layers | Adding spring-boot-starter-security does not make everything automatically safe |

**CSRF in Servlet:** HTTP methods considered "safe" (GET, HEAD, OPTIONS, TRACE by default in the CSRF matcher) do not require a CSRF token; POST, PUT, PATCH, DELETE are normally checked. Therefore, **never put state-changing operations in GET**. The token must be transmitted in a server-supported way (form field or request header as configured). Spring Security enables CSRF protection by default for standard web configurations; always verify your actual configuration.

**CORS is not authorization:** CORS dictates whether a browser may read/send certain cross-origin requests according to policy. Non-browser API clients can send requests directly; hence do not use CORS to decide who may edit or view data. When integrating CORS with Spring Security, handle preflight properly and avoid blocking OPTIONS before checking the origin.

**Security headers:** Spring Security provides useful default security headers, but **does not automatically add a general CSP** because the CSP policy must match the application's resources. HSTS is meaningful when accessed over HTTPS. Verify actual headers using a browser/curl and your specific configuration.

**When should disabling CSRF be considered?** A truly stateless API that only accepts bearer tokens explicitly placed in the Authorization header by the client and **does not use cookies/credentials automatically attached by the browser** may not need traditional CSRF protection. That is a decision per security chain's threat model; do not disable CSRF globally just because endpoints return JSON, use HTTP Basic, or are called a "REST API".

## 6. Runnable Example: Spring Boot 3.3.x, Spring Security 6, Java 17+

This example illustrates the three responsibilities in a single Servlet application. Uses Maven and JDK 17 or higher; file layout is as follows:

~~~text
three-responsibilities/
├── pom.xml
└── src/main/java/com/example/security/
    ├── DemoApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
~~~

**pom.xml**

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
    <artifactId>three-responsibilities</artifactId>
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
~~~

**src/main/java/com/example/security/DemoApplication.java**

~~~java
package com.example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/security/SecurityConfig.java**

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/profile").authenticated()
            .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
            .requestMatchers(HttpMethod.POST, "/api/changes").authenticated()
            .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        http.formLogin(AbstractHttpConfigurer::disable);

        // Do not call csrf().disable(): CSRF remains enabled by default.
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        // Use {noop} only for lessons; production must use a secure PasswordEncoder.
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader-pass")
            .roles("USER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin-pass")
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(reader, admin);
    }
}
~~~

**src/main/java/com/example/security/DemoController.java**

~~~java
package com.example.security;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {
    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of("message", "public");
    }

    @GetMapping("/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin-only");
    }

    @PostMapping("/changes")
    public Map<String, String> change() {
        return Map.of("status", "changed");
    }
}
~~~

Run in the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Verify from another terminal:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/profile
curl -i -u reader:reader-pass http://localhost:8080/api/profile
curl -i -u reader:reader-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
curl -i -u reader:reader-pass -X POST http://localhost:8080/api/changes
~~~

| Request | Expected HTTP Status | What Is Verified |
| --- | --- | --- |
| GET /api/public, no credentials | **200**; JSON {"message":"public"} | permitAll for public endpoint |
| GET /api/profile, no credentials | **401** | Missing authentication; HTTP Basic entry point challenges the client |
| GET /api/profile, valid reader | **200**; JSON {"user":"reader"} | Authenticated identity reader |
| GET /api/admin, valid reader | **403** | Authenticated but lacks ROLE_ADMIN |
| GET /api/admin, valid admin | **200**; JSON {"message":"admin-only"} | Both authentication and authorization pass |
| POST /api/changes, valid reader, no CSRF token | **403** | Has identity and URL permission, but fails anti-CSRF check |

The POST row illustrates a **request rejected before change() logic runs**, so JSON {"status":"changed"} is not returned. The 403 code here is due to CSRF protection, not because reader lacks a role. Detailed headers, error body, and logs may vary by configuration; the table only asserts the statuses/JSON relevant to the example.

The example uses HTTP Basic and in-memory accounts for clear observation. It is **not a production configuration**: replace {noop} with password hashing, use HTTPS, centralized identity management, rate limiting/auditing, check CSRF per actual browser mechanisms, and configure stateless only when there is a specific authentication requirement.

## 7. Two Design Mistakes Easily Confused When Combining the Three Layers

**Scenario A — Leaking Orders via URL**

- Alice logs in successfully; GET /orders/100 returns Alice's order.
- Alice tries GET /orders/101, which is Bob's order. If the server only checks authenticated(), the request can still pass the URL gate.
- You must check that order 101 belongs to Alice or that Alice has business permission before returning data. Return 403 (or 404 per policy to avoid disclosing resource existence) when invalid.

Conclusion: correct authentication does not prove **per-object** ownership.

**Scenario B — Email Change Request from a Malicious Website**

- Alice has a session cookie and permission to update her email.
- Another site tricks the browser into sending a POST to the application with Alice's cookie.
- If the application accepts auto-sent credentials without checking a CSRF token, the action can execute without Alice's intent. CSRF protection rejects requests lacking a valid token.

Conclusion: correct authorization does not prove **user intent** for state-changing requests.

**Scenario C — Submitting Input Containing Scripts**

- A user is allowed to update a profile description, but the data contains HTML/script.
- Authentication + authorization only answer "who can edit", not whether the data is safe to display.
- Context-appropriate escaping/output encoding for HTML/JavaScript is required, avoiding uncontrolled HTML construction and considering an appropriate CSP.

Conclusion: exploit protection includes many measures beyond CSRF; you must choose the right one for the risk and context.

## 8. Choosing Security Mechanisms by Client Model

| Model | Authentication | Authorization | Protections to Focus On |
| --- | --- | --- | --- |
| Web MVC using cookie sessions | Login and session | Route/method/object-level | CSRF token, cookie flags, session fixation, headers, XSS |
| API called with HTTP Basic | Username/password on each request | Route/method/object-level | HTTPS, login rate limits, CSRF if browser auto-sends credentials, do not expose Basic credentials |
| Resource Server receiving bearer token in Authorization header | OAuth2 resource server/JWT or opaque token per config | Authorities/scopes, owner/tenant, audience | Verify issuer/audience/expiry, token management, appropriate CORS; evaluate CSRF based on how client holds/sends credentials |

An application can use **multiple SecurityFilterChains** for browsers and APIs, each with appropriate matchers and policies. When doing so, verify all paths are protected by an intended chain; declaring a too-narrow securityMatcher can leave endpoints outside any protection chain if there is no fallback.

## 9. Diagnosing When You See 401 or 403

Instead of disabling protection "just to make it work", ask in order:

1. Did the request enter the right SecurityFilterChain? Check the matcher, HTTP method, and filter chain logs.
2. Were credentials actually sent and valid? Identify Basic/session/bearer mechanism; check SecurityContext/Authentication and authorities after authentication (do not log passwords/tokens).
3. Which URL rule matched first? hasRole("ADMIN") requires ROLE_ADMIN, whereas hasAuthority("ADMIN") requires the exact string ADMIN.
4. Are there method/object-level checks in the service? Are reads/writes to objects outside the user's permission blocked?
5. Is a state-changing request missing or using an invalid CSRF token? Is the browser sending cookies automatically?
6. Are CORS preflight, headers, firewall, or error handlers affecting it? A 403 from CSRF and a 403 from missing permissions must be distinguished using logs and actual configuration.
7. When returning 200, are the data and side effects within the allowed bounds? HTTP success does not guarantee no data is leaked.

When investigating, enable DEBUG selectively in development environments and **never print credentials, Authorization headers, or CSRF tokens into logs**.

## 10. Checklist for Designing a Sensitive Endpoint

Example POST /accounts/{id}/transfer:

- **Authentication:** verify the requester via the chosen session or token; do not trust a client-supplied userId as identity.
- **Authorization:** verify the user has permission to transfer money from the account id; check organization/owner, account status, and transaction limits in the service.
- **Exploit protection:** with cookie sessions, verify CSRF; validate inputs, rate limit, audit, anti-replay/idempotency per business requirements; use HTTPS and appropriate security headers.
- **Testing:** unauthenticated; wrong permission; wrong account owner; missing CSRF token; valid token; invalid input; repeated requests. Verify actual data state after rejection, not just the HTTP status.

## 11. Self-Check Questions

1. If a user logs in successfully but accesses another person's invoice, which layer must reject it? **Object/data-level authorization.**
2. If a user has permission to update a profile but the browser sends a POST missing a CSRF token, which layer can reject it? **Exploit protection/CSRF.**
3. If an API only allows browser origin A via CORS, can a user from curl send a request? **Yes**; CORS is not server-side authorization.
4. Why shouldn't CSRF be disabled application-wide just because JSON is used? **Because browsers may still send cookies or credentials automatically; the risk depends on the authentication mechanism and how the client sends credentials.**
5. Does the ADMIN role automatically permit viewing all other tenants' data? **No**; scope checks and business conditions are still necessary.

**Key point to remember:** Spring Security on Servlet solves problems at multiple layers. Authentication provides a trusted identity; authorization enforces action/resource policies; exploit protection prevents exploitations that occur even when identity and permissions appear valid. A secure system must design and verify all three, along with proper input controls, encryption, monitoring, and business rules.
