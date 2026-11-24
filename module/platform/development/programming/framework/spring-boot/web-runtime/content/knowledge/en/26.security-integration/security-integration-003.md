# Distinguishing Public, Authenticated, and Authorized Endpoints

## 1. Three Different Security Questions on the Same HTTP Request

When integrating **Spring Security** into Spring Boot, whether a URL returns data does not depend solely on whether a Controller exists. Each request can pass through multiple verification layers: path matching, identity authentication, authorization, and object-specific ownership checks.

Distinguish the three common access levels:

1. **Public endpoint:** unauthenticated callers are also allowed to invoke it. For example, GET /api/public/info displaying public product information.
2. **Authenticated endpoint:** the caller must be authenticated by the system, without yet requiring a specific role/privilege. For example, GET /api/me returning information about the currently logged-in user.
3. **Authorized/permission-protected endpoint:** in addition to having an authenticated identity, the caller must hold the appropriate role/authority/permission; for per-user data, **permission on the specific object** must also be checked. For example, viewing administrative reports, reading invoices, or accessing orders belonging to a user.

**Authentication** answers “who is the caller and have they proven their identity?”. **Authorization** answers “is this identity allowed to perform this action on this resource?”. A user can log in successfully yet **lack permission** to view an admin page.

This article belongs to the **Security Integration** group of Spring Boot web-runtime, focusing on **Spring Boot 3.3.x, Spring Security 6.x, Spring MVC/Servlet, and Java 17+**. With Spring WebFlux, the concepts are similar, though the APIs are typically **SecurityWebFilterChain** and ServerHttpSecurity rather than Servlet's HttpSecurity.

## 2. How Does a Request Pass Through Spring Security Before the Controller?

When using **spring-boot-starter-security**, Spring Security integrates into the web application via Servlet Filters. **FilterChainProxy** coordinates **SecurityFilterChain** instances; individual filters handle SecurityContext, authentication mechanisms, exceptions, and authorization.

Conceptual diagram:

~~~text
HTTP request
     |
     v
Servlet container / DelegatingFilterProxy
     |
     v
FilterChainProxy -> finds SecurityFilterChain matching request
     |
     +--> SecurityContext + Authentication mechanisms
     |        Basic / session / form login / bearer token ... per config
     |
     +--> AuthorizationFilter:
     |        requestMatchers ... FIRST MATCH
     |        permitAll? authenticated? hasRole? hasAuthority?
     |
     +--> ExceptionTranslationFilter / authentication entry point / 403 handler
     |
     v
DispatcherServlet -> Controller -> Service
                           |
                           +--> May check additional method security
                           +--> May check data owner/tenant
     |
     v
HTTP response
~~~

The diagram **does not guarantee the exact order of every filter** across all configurations; it only illustrates responsibilities. Rejected requests may **never reach the Controller**. Conversely, reaching the Controller does not prove the application has fully checked permissions on **specific data** inside.

An **Authentication** typically contains:
- **Principal:** the identity verified by the framework, such as username.
- **Credentials:** information used to authenticate, which must be handled/protected; usually not kept in raw form when unnecessary.
- **GrantedAuthority:** the set of permissions/roles assigned by the system.
- **authenticated flag:** the status of the Authentication, though you should not infer “any Authentication object means a valid logged-in user”; anonymous authentication can also be represented by an object.

**Practical rule:** rely on the **SecurityContext**/Authentication managed by Spring Security; never trust request headers like **X-User: admin** or cookies like **role=admin** if that source has not been verified.

## 3. URL Rules: permitAll, authenticated, hasRole, and hasAuthority

Spring Security declares rules via **HttpSecurity.authorizeHttpRequests(...)**. Common expressions:

| Rule | Meaning | Use Case |
| --- | --- | --- |
| permitAll() | No authentication/authority required to pass this authorization step | Public info, login page, intentionally public endpoints |
| authenticated() | Caller must be authenticated | Current user's own account info, endpoints for any logged-in user |
| hasRole("ADMIN") | Requires authority by convention **ROLE_ADMIN** | Role-based administration |
| hasAuthority("invoice:read") | Requires exact authority **invoice:read** | Narrow functional permission, granular permission |
| hasAnyRole("USER", "ADMIN") | Holds at least one of the listed roles | Multiple permitted groups |
| hasAnyAuthority("a", "b") | Holds at least one of the specified authorities | Multiple alternative permissions |
| denyAll() | Never allows request past this rule | Blocking internal endpoints, **fail closed** fallback |
| anonymous() | Allows only principals considered anonymous | E.g. pages/flows only for guests; not synonymous with permitAll() |

**permitAll() does not mean bypassing all of Spring Security.** The filter chain still runs and may add security headers, process authentication if the client sends credentials, enforce CSRF on state-changing methods, apply CORS, session-related logic, and other controls. A request to a public endpoint carrying **invalid Basic credentials** can still be rejected by the authentication filter.

**authenticated() does not mean a user can view every record.** It only ensures authenticated status per config; checking user A's permission on user B's order is a separate responsibility.

**hasRole() and hasAuthority() are not synonymous.** By default **hasRole("ADMIN")** requires a **GrantedAuthority named ROLE_ADMIN** (prefix is customizable); **hasAuthority("ADMIN")** requires the exact string **ADMIN**. When creating users with **.roles("ADMIN")**, Spring Security normally grants the **ROLE_ADMIN** authority.

### 3.1. Comparing Cases in a Table

Suppose the system uses these rules:
- **GET /api/public/info**: permitAll.
- **GET /api/me**: authenticated.
- **GET /api/admin/report**: hasRole("ADMIN").
- **GET /api/invoices/report**: hasAuthority("invoice:read").

| Caller | Public | /api/me | /api/admin/report | /api/invoices/report |
| --- | --- | --- | --- | --- |
| No credentials | Allowed | Auth required | Auth required | Auth required |
| reader: ROLE_USER | Allowed | Allowed | Permission denied | Permission denied |
| admin: ROLE_USER, ROLE_ADMIN | Allowed | Allowed | Allowed | Denied if missing invoice:read |
| auditor: ROLE_USER, invoice:read | Allowed | Allowed | Denied if missing ROLE_ADMIN | Allowed |

Important observation: **ADMIN does not implicitly grant every authority**. Having ROLE_ADMIN automatically include invoice:read is only true if the application configures a specific **role hierarchy/mapping rule**. Do not assume an admin role is a “super-permission” when designing granular rules.

## 4. HTTP 401, 403, 302, and 404: All Deny Access, for Different Reasons

In an API application using HTTP Basic, typical outcomes are:

| Scenario | Typical HTTP Code | Interpretation |
| --- | --- | --- |
| Public GET without credentials | **200** when Controller succeeds | Login not required |
| Protected GET without credentials | **401 Unauthorized** and WWW-Authenticate: Basic ... | Unauthenticated; client needs credentials |
| Invalid Basic credentials | **401 Unauthorized** | Authentication failed |
| Authenticated, missing role/authority | **403 Forbidden** | Identity known, insufficient permission |
| Authenticated, sufficient permission | **200** if business logic succeeds | Passed authorization gates |
| Endpoint with denyAll rule | **403** for authenticated user | Rule intentionally forbids |
| Form-login app, not logged in | Possibly **302 redirect** to login page | Entry point differs from HTTP Basic |
| Nonexistent resource or hiding existence | **404** per design contract | Not necessarily an authentication error |

**Do not memorize that missing login always means 401**. With formLogin, the framework may redirect; apps customizing entry points/AccessDeniedHandler may return different structures. With a **missing CSRF token** on POST, an authenticated user can still receive **403** before regular authorization logic runs.

A **401** does not merely mean “no permission”: it specifically signals **authentication is required or has failed**. A **403** is usually **authorization/access denied**, though it can also come from CSRF, firewalls, or other policies. Inspect logs/filters and test the exact scenario rather than guessing from the status code alone.

### 4.1. Authentication Entry Point and Access Denied Handler

- **AuthenticationEntryPoint:** handles cases requiring authentication or failed authentication, such as returning 401 + Basic challenge or redirecting to login.
- **AccessDeniedHandler:** handles AccessDeniedException for authenticated users lacking permission, typically returning 403.
- **ExceptionTranslationFilter:** connects authentication/authorization exceptions to the appropriate handlers.

If you convert every 401/403 into 200 with JSON **success=false**, monitoring, browsers, and HTTP clients can misbehave. Keep meaningful HTTP status codes and return error bodies without leaking internal details.

## 5. Matcher Order: “First Match” Decides the Rule

Within a **SecurityFilterChain**, Spring Security evaluates **requestMatchers** in declaration order; the **first matching rule** wins. Therefore, order is part of security.

Wrong configuration:

~~~java
// WRONG: broad rule placed before specific rule.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
~~~

Because `/api/admin/report` also matches **/api/**, the permitAll rule applies first, so the admin rule may **never be used**. Place narrower rules first:

~~~java
// RIGHT order: admin first, specific public next, clear fallback.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
);
~~~

The two snippets above are **fragments inside HttpSecurity configuration**, not standalone Java programs. They illustrate pattern ordering risks and do not replace a complete security policy.

### 5.1. Method-Specific Matchers Reduce Unintended Exposure

Rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/public/info").permitAll()
~~~

only opens **GET** on this path. Writing:

~~~java
.requestMatchers("/api/public/**").permitAll()
~~~

exposes additional methods and endpoints beneath the prefix (POST, DELETE...), including new APIs added later. Do not open an entire path subtree when the goal is only reading one public resource.

**HEAD and OPTIONS** have distinct HTTP/framework behavior; a GET matcher does not automatically guarantee all auxiliary methods are permitted. If browser clients require **CORS preflight OPTIONS**, configure CORS and rules properly instead of opening the whole API arbitrarily.

### 5.2. Choosing Fail Closed Instead of Forgetting a Rule

Two common fallbacks:

~~~java
// All remaining endpoints require login.
.anyRequest().authenticated()
~~~

~~~java
// All unlisted endpoints are blocked.
.anyRequest().denyAll()
~~~

Use **authenticated()** when policy allows any logged-in user to access the rest; use **denyAll()** when new endpoints should **remain closed** until explicitly granted access. Neither is universally right for every app, but **you must have a policy for new endpoints and test this rule**.

Avoid placing **anyRequest()** before specific requestMatchers because it is the final catch-all; doing so can make configuration invalid or render later rules meaningless.

## 6. Runnable Application: Three Access Levels on Spring Boot 3.3.13

The hands-on demo uses **Spring Boot 3.3.13, Spring Security 6.x, and Java 17+**, with a SecurityFilterChain using **HTTP Basic**. HTTP Basic is only for local demos, and production must run **HTTPS**; credentials are sent with Basic encoding and must not be considered encrypted over non-TLS HTTP.

Three **fixed demo accounts** (not production credentials):
- **reader / reader-pass** has **ROLE_USER**.
- **admin / admin-pass** has **ROLE_USER** and **ROLE_ADMIN**.
- **auditor / auditor-pass** has **ROLE_USER** and authority **invoice:read**.

The demo **does not disable CSRF**, though it only defines GET endpoints to stay focused on public/authentication/authorization. When adding POST/PUT/DELETE, handle CSRF and authentication models properly as covered in Section 10.

### 6.1. Project Structure

~~~text
endpoint-access-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/access/
    │   │   └── EndpointAccessDemoApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/access/
            └── EndpointAccessSecurityTest.java
~~~

**pom.xml**:

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
    <artifactId>endpoint-access-demo</artifactId>
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

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080
~~~

### 6.2. Complete Java Code: Single File Containing Application, Security Config, and Controller

**src/main/java/com/example/access/EndpointAccessDemoApplication.java**:

~~~java
package com.example.access;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class EndpointAccessDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointAccessDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/info")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/invoices/report")
                    .hasAuthority("invoice:read")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Do not call csrf.disable(): Spring Security keeps default CSRF.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        UserDetails auditor = User.withUsername("auditor")
                .password(encoder.encode("auditor-pass"))
                .authorities("ROLE_USER", "invoice:read")
                .build();

        return new InMemoryUserDetailsManager(reader, admin, auditor);
    }
}

@RestController
class AccessController {

    @GetMapping(
        path = "/api/public/info",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String publicInfo() {
        return "public-ok\n";
    }

    @GetMapping(
        path = "/api/me",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String me(Authentication authentication) {
        return "user=" + authentication.getName() + "\n";
    }

    @GetMapping(
        path = "/api/admin/report",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String adminReport() {
        return "admin-report\n";
    }

    @GetMapping(
        path = "/api/invoices/report",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String invoicesReport() {
        return "invoice-report\n";
    }
}
~~~

### 6.3. Exact Behavior Explained

1. **SecurityFilterChain** is a Spring Security Bean. Spring Boot uses this configuration instead of the starter's default protect-everything policy.
2. **requestMatchers(GET, "/api/public/info").permitAll()**: GET requires no credentials; other HTTP methods at the same path are not automatically made public by this matcher.
3. **GET /api/admin/report** allows only callers with **ROLE_ADMIN**. Users with only ROLE_USER are denied.
4. **GET /api/invoices/report** requires the exact string **invoice:read**, without assuming ADMIN has sufficient permission.
5. **GET /api/me** only requires authentication; the Controller receives **Authentication** supplied by Spring Security to read the username. Never read identity from query parameters.
6. **anyRequest().denyAll()**: unlisted paths/methods are denied even when the user is logged in. This is a **fail closed** policy.
7. **HTTP Basic** issues a 401 challenge for unauthenticated clients; form login is not enabled in the demo so curl results are easy to observe without 302 redirects.
8. **BCrypt PasswordEncoder** hashes passwords at startup for the three demo accounts. The code still contains plaintext passwords in source; this is **for labs only**—production must use an identity service/user repository and secret management. Never use **{noop}** or hardcoded passwords in real apps.
9. **CSRF remains enabled**. Because the demo endpoints are GET-only and do not mutate state, they do not need CSRF tokens for these test calls. **Do not add state-updating POSTs and then disable CSRF casually**.
10. The configuration above applies to **Spring MVC/Servlet**. For WebFlux apps, use **SecurityWebFilterChain/ServerHttpSecurity**, not HttpSecurity.

### 6.4. Running and Verifying with curl

Inside the **endpoint-access-demo** directory, with JDK 17+, Maven, and port 8080 free:

~~~bash
mvn spring-boot:run
~~~

You can also run **mvn package** then **java -jar target/endpoint-access-demo-1.0.0.jar**. Run in terminal 1; send requests from terminal 2. On Windows PowerShell, use **curl.exe** if the `curl` alias does not support the flags.

**Test 1 — public, no credentials:**

~~~bash
curl -i http://localhost:8080/api/public/info
~~~

Result: **HTTP 200**, body:

~~~text
public-ok
~~~

**Test 2 — authentication required, no credentials sent:**

~~~bash
curl -i http://localhost:8080/api/me
~~~

Typical result for this HTTP Basic demo: **HTTP 401 Unauthorized**, response includes **WWW-Authenticate: Basic ...**. The error body may be generated by the container/framework and you should not hardcode the entire stdout.

**Test 3 — authenticated as reader:**

~~~bash
curl -i -u reader:reader-pass http://localhost:8080/api/me
~~~

Result: **HTTP 200**, body:

~~~text
user=reader
~~~

**Test 4 — reader lacks admin permission:**

~~~bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/admin/report
~~~

Result: **HTTP 403 Forbidden**; the `adminReport` Controller method is not allowed to run.

**Test 5 — admin has ROLE_ADMIN:**

~~~bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin/report
~~~

Result: **HTTP 200**, body:

~~~text
admin-report
~~~

**Test 6 — auditor has granular authority:**

~~~bash
curl -i -u auditor:auditor-pass \
  http://localhost:8080/api/invoices/report
~~~

Result: **HTTP 200**, body:

~~~text
invoice-report
~~~

**Test 7 — admin is not automatically granted invoice:read:**

~~~bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/invoices/report
~~~

Result: **HTTP 403 Forbidden**, because admin's authorities list **does not contain** invoice:read.

**Test 8 — unknown path rejected by denyAll fallback:**

~~~bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/unlisted
~~~

Result: **HTTP 403 Forbidden** before normal routing runs, because the request does not match any permitted GET rule. Do not confuse this with a 404 from an app without a `denyAll` security rule.

**Test 9 — wrong password:**

~~~bash
curl -i -u reader:wrong-password \
  http://localhost:8080/api/me
~~~

Typical result: **HTTP 401 Unauthorized**. An existing username is not enough; credentials must verify successfully.

**Warning:** the **curl -u** flag can expose demo passwords in shell history, process listings, or scripts; use lab values and never put production credentials directly into commands or logs. In production, HTTP Basic must travel over **HTTPS**.

### 6.5. Expected Lab Results Table

| Request | Expected HTTP status | Why |
| --- | --- | --- |
| Anonymous GET /api/public/info | 200 | permitAll |
| Anonymous GET /api/me | 401 | authenticated requires login |
| reader GET /api/me | 200 | valid credentials |
| reader GET /api/admin/report | 403 | missing ROLE_ADMIN |
| admin GET /api/admin/report | 200 | has ROLE_ADMIN |
| auditor GET /api/invoices/report | 200 | has invoice:read |
| admin GET /api/invoices/report | 403 | missing invoice:read |
| reader GET /api/unlisted | 403 | anyRequest denyAll |
| reader:wrong-password GET /api/me | 401 | authentication failed |

These are the **expected results of the demo configuration**. When adding proxies, formLogin, error handlers, OAuth2, or customizations, HTTP codes may differ. Do not treat this table as a universal contract for all Spring Security apps.

## 7. Automated Testing with MockMvc + Spring Security Test

To avoid accidentally exposing a route during refactoring, turn the permission matrix into tests. The **spring-security-test** dependency is already in `pom.xml` with test scope.

File **src/test/java/com/example/access/EndpointAccessSecurityTest.java**:

~~~java
package com.example.access;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class EndpointAccessSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanReadPublicInfo() throws Exception {
        mvc.perform(get("/api/public/info"))
                .andExpect(status().isOk())
                .andExpect(content().string("public-ok\n"));
    }

    @Test
    void anonymousCannotReadOwnProfile() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void authenticatedUserCanReadOwnProfile() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isOk())
                .andExpect(content().string("user=reader\n"));
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void readerCannotReadAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = {"USER", "ADMIN"})
    void adminCanReadAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = {"ROLE_USER", "invoice:read"})
    void auditorCanReadInvoiceReport() throws Exception {
        mvc.perform(get("/api/invoices/report"))
                .andExpect(status().isOk())
                .andExpect(content().string("invoice-report\n"));
    }

    @Test
    @WithMockUser(roles = {"USER", "ADMIN"})
    void adminCannotReadInvoiceReportWithoutPermission() throws Exception {
        mvc.perform(get("/api/invoices/report"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "USER")
    void unknownRouteIsDenied() throws Exception {
        mvc.perform(get("/api/unlisted"))
                .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Expected result: **8 tests pass** with no `AssertionError`. Maven logs vary by OS/version; do not assume fixed stdout for `mvn test`.

**@WithMockUser** populates a test principal in Spring SecurityContext; it **does not prove BCrypt passwords or HTTP Basic parsing work**. Therefore, keep both MockMvc policy tests and **end-to-end tests** using curl, spring-security-test **httpBasic(...)**, or a real server when verifying the authentication mechanism. In production tests, add negative cases: anonymous, wrong role, wrong authority, wrong owner, expired token, CSRF, and other HTTP methods.

### 7.1. Testing Matcher Order Changes

A test protecting against the misconfiguration from Section 5 is:

~~~java
@Test
@WithMockUser(roles = "USER")
void adminRouteMustNeverBecomePublic() throws Exception {
    mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
}
~~~

This is an **additional fragment** to place inside a test class that already has `mvc` and imports. It helps catch cases where someone adds a broad `/api/**` rule without realizing the admin rule gets shadowed. In multi-module applications, every sensitive endpoint group needs at least one **authorized** test and one **unauthorized** test.

## 8. Authentication Can Come from Many Mechanisms; Authorization Must Still Be Explicit

The demo uses **HTTP Basic** to make 401/403 clear. Real applications may use:

| Authentication mechanism | What the client sends | Key considerations |
| --- | --- | --- |
| HTTP Basic | Authorization: Basic ... | Credentials require HTTPS; browsers cache credentials; CSRF still applies |
| Form Login + Session | Login form, then JSESSIONID/session cookie | Login redirect, CSRF, session fixation, and logout managed by framework |
| OAuth2 Resource Server JWT | Authorization: Bearer <token> | Verify signature, issuer/audience/expiry; map claims to authorities |
| Opaque Bearer Token | Authorization: Bearer <token> | Introspection server verifies token and determines permissions |
| mTLS | Client certificate over TLS | Verify certificate and map identity; does not replace business authorization |

Once authentication succeeds, SecurityContext can hold a principal/authorities for **authenticated/hasRole/hasAuthority** rules to evaluate. However, **not every authentication mechanism assigns authorities the same way**.

For example, an OAuth2 resource server typically maps scopes to authorities prefixed with **SCOPE_**. If a token has scope **orders.read**, a rule **hasAuthority("SCOPE_orders.read")** matches under the default converter; **hasRole("ADMIN")** will not match scopes automatically. Check **JwtAuthenticationConverter/GrantedAuthoritiesMapper** when customizing. Never trust JSON claims whose signature/token validity has not been verified.

### 8.1. Principal Has an Identity but Lacks Roles

An application may verify a token signature yet fail to map roles/authorities; in that case:
- authenticated() may pass.
- hasRole("ADMIN") or hasAuthority("invoice:read") may deny access.
- The bug lies in mapping/policy (or the token genuinely lacks permissions), not necessarily login/password.

When debugging, you may log the **authentication type** and **non-sensitive authority names** in a protected environment; never log raw tokens, passwords, session IDs, or the entire SecurityContext.

## 9. Roles, Authorities, and Per-Object Permissions

A rule like **hasRole("USER")** or **authenticated()** applies to a **group of callers**; it does not prove that caller is authorized to read **order 123**.

Dangerous example:

~~~java
// UNSAFE for business security if service only looks up by ID.
@GetMapping("/api/orders/{id}")
OrderDto read(@PathVariable long id) {
    return orderRepository.findById(id)
            .map(OrderDto::from)
            .orElseThrow();
}
~~~

With only a rule **/api/orders/** authenticated(), any logged-in user can change the ID to view other users' resources. This is **broken object-level authorization (BOLA)/IDOR**.

A better approach: combine caller authentication with queries constrained by **owner/tenant** or a service-level authorization policy:

~~~java
// Illustrative fragment; OrderDto, repository, and exception are application-defined.
@GetMapping("/api/orders/{id}")
OrderDto read(@PathVariable long id, Authentication auth) {
    return orderRepository.findByIdAndOwnerUsername(id, auth.getName())
            .map(OrderDto::from)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found"));
}
~~~

Here the repository only returns data belonging to the current user. Returning 404 can avoid disclosing the existence of the resource; in other systems, the contract may call for 403. Most importantly, **never return another user's data**. For admins/support representatives, policy may allow audited exceptions with separate requirements rather than leaving ID lookups open by default.

**These fragments do not compile standalone**: they require `@GetMapping`, `Authentication`, `ResponseStatusException`, `HttpStatus`, repository/DTO, and a Controller class. Do not add them to the runnable demo in Section 6 without implementing the data model.

### 9.1. Distinguishing Permission Groups and Fine-Grained Checks

- **Functional role/authority:** can read reports, create orders, change settings.
- **Resource ownership:** which user owns this order? Which tenant? Which project?
- **Attribute-based policy:** is the account locked? Is it allowed at this time? What state is the order in?
- **Scope/context:** viewing one's own data or acting on behalf of someone else? Is explicit approval present?

An **authenticated()** endpoint is not “safe for every record” if the service does not enforce these conditions.

## 10. Method Security: Checking Permissions at the Service Layer

Spring Security supports **@PreAuthorize, @PostAuthorize**, and related annotations for method-level authorization, but **the security starter does not enable method security automatically**. You must declare **@EnableMethodSecurity**.

Example **fragment** in a `@Configuration` class, not a complete standalone program:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

The Service layer can check:

~~~java
// Fragment inside a Spring-managed @Service.
@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceDto readInvoice(long id) {
    return invoiceRepository.findById(id)
            .map(InvoiceDto::from)
            .orElseThrow();
}
~~~

**@PreAuthorize** checks before invoking the method; if the check fails, the method does not run. However, the fragment above only checks the **general invoice:read permission**; if data is scoped by owner/tenant, an ownership condition is still required. Complex policies can delegate to a bean such as **@PreAuthorize("@invoicePolicy.canRead(authentication, #id)")** backed by an **invoicePolicy bean** implementing real logic.

Technical notes:
- Method security relies on Spring AOP/proxies in standard configurations. If an object calls **another method on itself** via **this.someMethod()**, that call can **bypass the proxy** and skip the annotation on the target method. Place policies at proper bean boundaries and test real invocation paths.
- Method security **supplements**, and should not blindly replace, URL rules.
- Both request-level and method-level rules can be evaluated; passing the URL layer does not guarantee passing method policies.
- Do not rely on decorative annotations when **@EnableMethodSecurity** is not enabled or the class is not Spring-managed.

**When to use which layer?** URL rules work well for coarse-grained gates such as “/admin/** only ADMIN”; method rules work well when a service is invoked from HTTP, batch jobs, or messaging and policy must stay close to business logic; object-level checks must use trustworthy owner/tenant data and be tested.

## 11. CSRF: Public, Authenticated, and Permissions Do Not Replace Forged-Request Checks

A user logged in via a **session cookie** or whose browser auto-sends HTTP Basic credentials can be tricked into visiting another page that submits requests on their behalf. That is the context of **Cross-Site Request Forgery (CSRF)**.

With Servlet, Spring Security **enables CSRF protection by default** for **unsafe HTTP methods**, such as POST/PUT/PATCH/DELETE. Thus:

~~~text
POST /api/orders
Authorization: Basic ...
(no valid CSRF token)
~~~

can receive **403** even when Basic authentication is valid and the user has the **order:write** authority. Do not immediately conclude the user lacks a role or the authorization matcher is wrong.

**Do not use GET to create/modify/delete data** just to avoid CSRF tokens. GET is designed as a safe method; mutating state via GET increases risk and breaks cache/crawler expectations.

### 11.1. When to Consider Disabling/Ignoring CSRF

Only when a specific threat model proves the endpoint **does not rely on credentials automatically attached by browsers** and appropriate safeguards exist. For instance, an API using only Bearer tokens in the Authorization header supplied by controlled clients and having no cookie-based auth **may** consider disabling CSRF on a dedicated chain. However:
- HTTP Basic with browsers still carries CSRF risk.
- A system using session cookies needs CSRF protection or equivalent safeguards.
- **.csrf(csrf -> csrf.disable())** applied broadly can be a mistake if the same app also uses login forms/cookies.
- **permitAll() does not disable CSRF**; a public POST can still return 403 if a CSRF token is missing.

In applications combining an SPA and browser sessions, handle tokens via the framework and proper headers/cookies; configuring CORS also does not replace CSRF.

### 11.2. Example Permission Rule for State-Changing Actions

~~~java
// Fragment for an API with matching authentication + CSRF design:
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("order:write")
~~~

This is an **authorization condition**, **not** CSRF handling. Holding **order:write** does not allow omitting the token when CSRF is enabled. You also still need to check which order data the user is allowed to modify.

## 12. Public Endpoints Still Need Other Security Protections

Configuring `permitAll` only removes the authz requirement of **that rule**; it does not guarantee a public endpoint is harmless. For example:
- **GET /api/catalog:** public, yet still needs input validation, rate limiting, caching, and anti-scraping controls per policy.
- **POST /register:** open to unauthenticated callers, yet must guard against spam, bots, account enumeration, brute force, and handle CSRF appropriately for browser forms.
- **GET /actuator/health:** liveness/readiness may be exposed on an internal network for operations, but do not expose `/actuator/env`, `/heapdump`, or all management endpoints by default. Whether an actuator endpoint appears also depends on dependencies/exposure config.
- **Static CSS/JS:** can be public; Spring Security recommends **permitAll() instead of web.ignoring()** to retain security headers/filter protections. If filters are bypassed completely, these protections may not apply.
- **Error responses:** never leak stack traces, file paths, or verbatim database errors to public users.

### 12.1. The CORS Preflight Issue

Cross-origin browsers may send an **OPTIONS preflight** before the real request. With **anyRequest().denyAll()**, an unhandled OPTIONS request may be rejected.

CORS is a browser mechanism controlling **which origins are allowed to read/send requests under CORS policy**; it is neither authentication nor does it grant users authorities. You must:
1. Define specific allowed origins, methods, headers, and credentials.
2. Configure **CorsConfigurationSource** or Spring MVC CORS and integrate **http.cors(...)** when needed.
3. Never carelessly combine **Access-Control-Allow-Origin: *** with credentialed requests.
4. Keep separate authorization rules for actual requests and test both preflight and credentialed requests.

Do not “fix” CORS by marking all of **/api/** `permitAll` and skipping permission checks.

## 13. When Using Multiple SecurityFilterChains: securityMatcher vs requestMatchers

In a multi-area application (web sessions, public API, internal API), you can declare multiple **SecurityFilterChain** beans with different **@Order** values.

- **securityMatcher(...)**: decides **which SecurityFilterChain applies** to the request.
- **authorizeHttpRequests().requestMatchers(...)**: decides **authorization rules inside the selected chain**.
- **FilterChainProxy** normally picks the **first matching chain** in configured order; it does not merge all chains into one rule set.

Illustrative fragment, not a standalone runnable configuration:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

If you only declare this chain without a fallback chain, requests outside **/api/** may **not pass through that Spring Security chain**. That does not mean Spring Boot automatically denies all URLs outside `/api`. Design a **fallback SecurityFilterChain** for remaining requests when needed and verify bean ordering.

Avoid using multiple chains merely to split up a few simple rules. A single chain with clear `requestMatchers` is usually easier to audit; multiple chains should have an architectural reason (such as browser sessions vs Bearer APIs) and broad integration tests.

## 14. Diagnosing “Already Logged In, Still Getting 403”

| Symptom | Common cause | How to check |
| --- | --- | --- |
| Public GET returns 401 | Client sent invalid Basic credentials, another chain applied, custom filter | Inspect credentials, selected SecurityFilterChain, and AuthenticationEntryPoint |
| Anonymous GET protected returns 302 instead of 401 | Form login entry point is enabled | Check httpBasic/formLogin/exceptionHandling |
| Logged in, yet `/admin` returns 403 | Missing ROLE_ADMIN or wrong matcher/rule | Check verified GrantedAuthorities and matcher order |
| Has authority ADMIN, yet hasRole("ADMIN") fails | hasRole usually requires ROLE_ADMIN | Check prefix/GrantedAuthoritiesMapper |
| Has ROLE_ADMIN, yet invoice:read is denied | Roles do not automatically include permissions | Grant/map authorities per policy or configure explicit hierarchy |
| Authenticated POST returns 403 | Missing CSRF token or policy denies | Check CsrfFilter/logs and method-specific rules |
| `/api/admin/**` unexpectedly public | Broad permitAll rule placed earlier | Review requestMatchers order, add regression test |
| Method has @PreAuthorize, yet still accessible | Missing @EnableMethodSecurity or self-invocation/proxy | Test calling from another Spring bean, check config |
| User A reads User B's record | Only checked authenticated, missing object ownership | Query by owner/tenant, test IDOR/BOLA |
| Some paths unprotected | securityMatcher covers only part of URLs, missing fallback chain | Review all filter chains and @Order |
| Browser CORS error despite user having permission | Origin/preflight/credentials policy | Check OPTIONS, CORS config, and headers |
| Error endpoint returns 403 instead of expected response | ERROR/FORWARD dispatch or denyAll fallback | Check dispatcher types and handlers without opening entire API |
| Valid JWT yet missing permissions | Wrong claims/scope -> GrantedAuthority mapping | Check converter and effective authorities |
| Static files return 403 | Fallback rule applies to static resources | permitAll specific paths; do not bypass filters indiscriminately |

### 14.1. Enabling Controlled Diagnostic Logging

In development environments, you can raise logging for Spring Security:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Logs can reveal filter/authorization decisions under your configuration, though you should **not** treat debug messages as stable across versions. Never leave broad debug logging enabled long-term in production: it adds overhead and can expose request metadata or authentication details. **Never log passwords, tokens, JSESSIONIDs, or raw Authorization headers**.

A sensible debugging workflow:
1. Identify exact **URL, HTTP method, principal**, and request type.
2. Identify which **SecurityFilterChain** was selected.
3. Identify the **first matching requestMatcher**.
4. Verify the authenticated Authentication and its authorities.
5. Check CSRF/CORS/request firewall if the request never reached the Controller.
6. If it entered the service, check method security and owner/tenant permissions.
7. Only customize entry points/handlers when the response contract truly needs to change.
8. Turn findings into negative/positive tests to prevent regressions.

## 15. Self-Assessment Exercises

**Exercise 1.** `GET /api/news` has `permitAll()`. Can an unauthenticated user call it?

**Answer:** They can pass the request authorization step without logging in. However, it must still pass other filters, and HTTP 200 is not guaranteed if the Controller fails or the client sends invalid credentials.

**Exercise 2.** A user is logged in with `ROLE_USER`, and the rule for `/api/me` is `authenticated()`. Is that sufficient?

**Answer:** Yes, for that request rule, since `authenticated()` does not require `ROLE_USER` specifically. Returned data must still be scoped to the current user.

**Exercise 3.** A user has `ROLE_USER`, and `/api/admin/**` requires `hasRole("ADMIN")`. What is the typical result?

**Answer:** With authenticated HTTP Basic, it typically returns HTTP 403 due to missing `ROLE_ADMIN`; not 401 because identity is already authenticated.

**Exercise 4.** A user has authority **ADMIN** (without `ROLE_ADMIN`). Does `hasRole("ADMIN")` let them through?

**Answer:** Not with the default prefix. `hasRole("ADMIN")` normally checks for `ROLE_ADMIN`. To match the exact string `ADMIN`, use `hasAuthority("ADMIN")` per chosen policy.

**Exercise 5.** Does `ROLE_ADMIN` automatically grant **invoice:read**?

**Answer:** No. Only if the system explicitly assigns the additional permission or configures a role hierarchy/mapping.

**Exercise 6.** Is placing `permitAll("/api/**")` before `hasRole("/api/admin/**")` safe?

**Answer:** No. The broad rule matches first; the admin rule is neutralized due to first-match semantics.

**Exercise 7.** `POST /api/orders` by a user with **order:write** still returns 403. Is it definitely a missing authority?

**Answer:** No. When default CSRF is enabled, a missing or invalid token also triggers 403. Check the filter and underlying error.

**Exercise 8.** `GET /api/orders/123` requires `authenticated()`. User A changes 123 to 124 and views B's order. What vulnerability is this?

**Answer:** **Broken object-level authorization (BOLA/IDOR)**. URL-level `authenticated()` does not verify record ownership/tenant.

**Exercise 9.** `@PreAuthorize` is on a service method, but `@EnableMethodSecurity` is missing. Is it enforced automatically?

**Answer:** No. Spring Boot Starter Security does not enable method security merely because the annotation is present. Enable it and test proxy invocation.

**Exercise 10.** A chain is scoped with `securityMatcher("/api/**")` and has no fallback. Will `/admin` definitely be denied?

**Answer:** No. It may not be protected by that chain at all; check other chains and configure an appropriate fallback.

**Exercise 11.** A public `/register` POST has `permitAll`. Can it still be blocked by CSRF?

**Answer:** Yes, if CSRF protection applies. Public authorization does not disable other filters.

**Exercise 12.** The browser reports a CORS error. Should you change every rule to `permitAll` to fix it?

**Answer:** No. Configure origins/preflight/credentials properly while preserving authentication/authorization for actual requests.

## 16. Pre-Deployment Spring Security Review Checklist

- **Define clear boundaries:** which endpoints are public, which only need authenticated, and which require roles/authorities.
- **Least privilege:** permit only truly necessary URLs and HTTP methods; avoid overly broad `/**` matchers.
- **Matcher order:** specific rules before broad rules; `anyRequest` is an intentional fallback.
- **Roles/authorities:** distinguish `ROLE_` prefixes from exact authorities and JWT/OAuth2 converters.
- **Object-level:** read/write data scoped by owner, tenant, state, and policy; never rely on `authenticated()` on paths alone.
- **Authentication:** identity comes from Spring `SecurityContext` after credentials/tokens are verified, not self-asserted headers/cookies.
- **Errors:** expect 401 for unauthenticated Basic APIs, 403 for authenticated without permission; understand 302/CSRF/404 per architecture.
- **CSRF/CORS:** never disable CSRF globally when browser cookies/Basic are used; test unsafe methods and preflight.
- **Chain selection:** if using multiple `SecurityFilterChain` beans, verify `@Order`, `securityMatcher`, and complete fallback coverage.
- **Method security:** enable `@EnableMethodSecurity` when needed; verify AOP self-invocation and resource permissions.
- **Passwords/tokens:** never hardcode production credentials, never use HTTP Basic over cleartext HTTP, protect secrets/logs.
- **Observability:** logs/metrics must not contain raw Basic headers, Bearer tokens, session IDs, or private data.
- **Regression tests:** every sensitive endpoint has tests for anonymous, valid permission, missing permission, and different owner/tenant; add cases for other HTTP methods.
- **Default deny:** new endpoints must be explicitly reviewed before being opened or granted access.

## 17. Conclusion

The three levels **public – authenticated – authorized** are three distinct decisions, not interchangeable labels:

- **permitAll()**: does not require user login to pass the declared **authorization rule**.
- **authenticated()**: requires an authenticated identity, **without proving access to every resource**.
- **hasRole()/hasAuthority()**: requires system-granted permissions; object-level policy also checks **who owns the specific data**.

For a secure web runtime, combine **properly ordered request matchers**, **appropriate CSRF/CORS models**, **SecurityFilterChain coverage across all protected areas**, **method/data authorization**, and **integration tests covering both allow and deny scenarios**. Fail-closed rules and checking permissions where data is accessed prevent turning a “login-required” endpoint into a data-exposure vulnerability across users.

## Official References

- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — In-Memory Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/in-memory.html
- Spring Security — HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Testing: https://docs.spring.io/spring-security/reference/servlet/test/index.html
- Spring Boot 3.3 — Spring Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html