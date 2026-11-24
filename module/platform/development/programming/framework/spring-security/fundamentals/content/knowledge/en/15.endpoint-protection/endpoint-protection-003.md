# Requiring Login and Specific Permissions per Endpoint Group in Spring Security

## 1. Objectives

An application typically has multiple endpoint groups: public information, logged-in user profiles, report-reading APIs, data-updating APIs, and administrative areas. Putting the entire system under a single **authenticated()** rule is not enough: an employee who is only allowed to read reports must not be able to update reports, and regular users must not enter administrative functions.

This lesson walks through designing and configuring **authorization by URL + HTTP method + authority**, focusing on the questions:

- Which endpoints do not require login?
- Which endpoints only require an authenticated identity?
- Which endpoints require a specific **role** or **authority**?
- How do you apply rules by **URL group** without accidentally opening permissions for other endpoints?
- Why do matcher order, HTTP method, CSRF, and the final fallback rule determine security?

The main examples use **Spring Boot 3.x + Spring Security 6.x + Spring MVC/Servlet**, Java 17+. The final section shows how to transfer the idea to WebFlux. This lesson is about **endpoint protection**, not login protocols or identity provider design.

## 2. How Does Authentication Differ from Authorization?

**Authentication** answers: "Who does this request belong to; has that identity been verified?". Spring Security represents the result with an **Authentication**, containing the principal, authenticated status, and list of **GrantedAuthority** instances.

**Authorization** answers: "Is that identity allowed to perform this action?". Rules inspect the authentication and authorities to decide whether to let the request proceed to the endpoint.

~~~text
HTTP request
   |
   v
Spring Security filter chain
   |
   +--> Authentication (reads/verifies credentials if needed)
   |         |
   |         +--> Authentication with principal, authorities
   |
   +--> Authorization (evaluates path, HTTP method, required rules)
             |
             +--> Allowed --> Controller/endpoint
             |
             +--> Denied  --> Exception handling (e.g., 401/403)
~~~

Someone who is **logged in** may still **lack sufficient permissions**. Therefore:

| Rule | Meaning |
| --- | --- |
| **permitAll()** | Allows the request without authentication; other security filters may still apply. |
| **authenticated()** | Requires an Authentication considered authenticated; does not automatically require a specific business role. |
| **hasRole("ADMIN")** | By default requires the GrantedAuthority **ROLE_ADMIN**. |
| **hasAuthority("report:read")** | Requires a GrantedAuthority with the exact string **report:read**. |
| **hasAnyRole("ADMIN", "SUPPORT")** | Requires at least one of the corresponding roles. |
| **hasAnyAuthority("report:read", "report:write")** | Requires at least one of the listed authorities. |
| **denyAll()** | Disallows matching requests; useful as the final fallback rule. |

**hasRole("ADMIN") does more than check whether the user is logged in**: it also requires the ROLE_ADMIN authority. **hasAuthority("report:read")** does not prepend the ROLE_ prefix. Permissions are not granted by writing authorization rules; authorities must come from authentication/authority mapping.

## 3. Start with an Access Matrix Before Writing Code

Consider an internal reporting system with the following policy:

| Endpoint group | HTTP method | Allowed users | Intended rule |
| --- | --- | --- | --- |
| /public/info | GET | Everyone | permitAll() |
| /account/profile | GET | Any logged-in user | authenticated() |
| /reports/summary | GET | Users with report read permission | hasAuthority("report:read") |
| /reports/summary | POST | Users with report write permission | hasAuthority("report:write") |
| /admin/status | GET | Administrators | hasRole("ADMIN") |
| Other undeclared endpoints | Any method | Nobody | denyAll() |

**The matrix is a behavioral specification**, not just a presentation table. During development, it can be used to write tests for both allowed and denied cases.

Example with four accounts:

| Account | Actual authorities | Meaning |
| --- | --- | --- |
| member | ROLE_USER | Can log in; no report or admin permissions |
| reader | report:read | Can read reports; cannot update |
| editor | report:read, report:write | Can read and update reports |
| admin | ROLE_ADMIN | Can access the /admin/** group |

**Do not assume admin automatically has report:read.** If business logic requires admin to read reports, you must grant the additional authority or define an appropriate inheritance/authorization mechanism. In this example, they are independent authorities.

### Why Must You Consider HTTP Methods Too?

On the same path **/reports/summary**, two operations carry different risk levels:

- **GET** only reads results.
- **POST** triggers an update or report recalculation.

If you only write **requestMatchers("/reports/**").hasAuthority("report:read")**, the same read permission can be used for POST. To distinguish them, combine **HttpMethod.GET/POST** with the path in the matcher, and account for undeclared methods such as PUT, PATCH, or DELETE. Unapproved methods must fall into a deny rule.

## 4. How Spring Security Selects a Rule for a Request

With Spring Security 6.x on Servlet, the standard API is:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/public/info").permitAll()
        .requestMatchers(HttpMethod.GET, "/account/profile").authenticated()
        .requestMatchers(HttpMethod.GET, "/reports/**").hasAuthority("report:read")
        .requestMatchers(HttpMethod.POST, "/reports/**").hasAuthority("report:write")
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll());
~~~

This is a **configuration fragment** inside a SecurityFilterChain bean, not a standalone program.

For a **selected SecurityFilterChain**, Spring Security evaluates **RequestMatcher → AuthorizationManager** pairs in **declaration order**. The first matching rule decides the permission check. Once a rule matches but the authority is missing, Spring Security **does not continue trying later rules to find a more permissive one**.

Example:

~~~text
GET /reports/summary
   |
   +--> GET /public/info     ? no
   +--> GET /account/profile ? no
   +--> GET /reports/**      ? YES
             |
             +--> requires report:read
                     |
                     +--> reader has it   --> allowed
                     +--> member lacks it --> denied
~~~

**Place specific rules before broad catch-all rules.** The following two configurations differ sharply:

~~~java
// Wrong for the goal "admin requires role ADMIN":
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/**").authenticated()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll());
~~~

The first rule already matched /admin/status, so the hasRole rule afterward is never applied.

~~~java
// Correct: prioritize the admin area before the general area:
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

The second (correct) example only illustrates **ordering**; in an API requiring deny-by-default, declare all necessary groups and end with **anyRequest().denyAll()**.

### `requestMatchers` and `securityMatcher` Are Different

- **http.securityMatcher(...)** decides whether a request belongs to **this SecurityFilterChain**, especially when an application has multiple SecurityFilterChain beans.
- **authorizeHttpRequests(...requestMatchers(...))** selects **an authorization rule inside the already-applied SecurityFilterChain**.

A basic application can use **a single SecurityFilterChain** to protect all requests; this is also the choice in the example below. With multiple chains, you must arrange `@Order` properly and ensure no URL accidentally falls outside all chains. **anyRequest().denyAll() in one chain does not protect URLs that the chain never matches**.

## 5. Complete, Runnable Spring Boot 3.x Example

### 5.1. Create the Project

Use Spring Initializr to create a **Gradle** project, Java **17+**, Spring Boot **3.x**, group **com.example**, package **com.example.demo**, with two dependencies:

- **Spring Web** = spring-boot-starter-web
- **Spring Security** = spring-boot-starter-security

The example uses **HTTP Basic** so requests are easy to send with curl, **in-memory users** to show authorities directly, and **REST endpoints** returning plain strings.

Create the file **src/main/java/com/example/demo/EndpointAuthorizationApplication.java** with the **complete contents** below:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class EndpointAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(EndpointAuthorizationApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                // For local curl demo only. See CSRF warning below.
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        // Public group
                        .requestMatchers(HttpMethod.GET, "/public/info")
                            .permitAll()

                        // Authenticated-only group
                        .requestMatchers(HttpMethod.GET, "/account/profile")
                            .authenticated()

                        // Reports group: read and write require separate authorities
                        .requestMatchers(HttpMethod.GET, "/reports/**")
                            .hasAuthority("report:read")
                        .requestMatchers(HttpMethod.POST, "/reports/**")
                            .hasAuthority("report:write")

                        // Admin group: requires ROLE_ADMIN
                        .requestMatchers("/admin/**")
                            .hasRole("ADMIN")

                        // Deny other URLs/methods by default
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails member = User.withUsername("member")
                .password("{noop}demo123")
                .roles("USER")
                .build();

        UserDetails reader = User.withUsername("reader")
                .password("{noop}demo123")
                .authorities("report:read")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password("{noop}demo123")
                .authorities("report:read", "report:write")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}demo123")
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(
                member, reader, editor, admin);
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/public/info")
    String info() {
        return "public-info";
    }

    @GetMapping("/account/profile")
    String profile(Authentication authentication) {
        return "hello-" + authentication.getName();
    }

    @GetMapping("/reports/summary")
    String readReport() {
        return "report-summary";
    }

    @PostMapping("/reports/summary")
    String updateReport() {
        return "report-updated";
    }

    @GetMapping("/admin/status")
    String adminStatus() {
        return "admin-ok";
    }

    @GetMapping("/unlisted")
    String unlisted() {
        return "should-not-be-visible";
    }
}
~~~

**Why does this single file run?** Java allows only one public top-level class matching the filename. The remaining classes are package-private in the same package; Spring Boot scans `@Configuration`/`@RestController` classes in the same package. The endpoints are intentionally simple to separate **request matching + authority checks** from database/business logic.

**Notes when running:**

- The password **{noop}demo123** is for this lesson only; never store passwords this way in production.
- **csrf(AbstractHttpConfigurer::disable)** is used only so the curl commands below can send POST without supplying a CSRF token. **Do not copy this setting blindly into a real product.** Even HTTP Basic credentials can be resent automatically by browsers; evaluate CSRF based on client type, how browsers send credentials, and the threat model. Browser applications using cookies/sessions normally must keep appropriate CSRF protection.
- **SessionCreationPolicy.STATELESS** avoids HTTP login session dependency for the Basic API demo; it **does not replace** CSRF evaluation.
- The example code does not implement authentication from JWT, a database, or an identity provider; in practice, map that system's roles/permissions into the right GrantedAuthority values.

### 5.2. Start and Send Requests

In the root directory of the created Gradle project:

~~~bash
./gradlew bootRun
~~~

On Windows, use **gradlew.bat bootRun**. Wait for the application to listen on **http://localhost:8080**, then in another terminal:

~~~bash
# Public endpoint: no credentials needed
curl -i http://localhost:8080/public/info

# Endpoint requiring only an authenticated identity
curl -i http://localhost:8080/account/profile
curl -i -u member:demo123 http://localhost:8080/account/profile

# Reports: GET requires report:read
curl -i -u member:demo123 http://localhost:8080/reports/summary
curl -i -u reader:demo123 http://localhost:8080/reports/summary

# Reports: POST requires report:write
curl -i -X POST -u reader:demo123 http://localhost:8080/reports/summary
curl -i -X POST -u editor:demo123 http://localhost:8080/reports/summary

# Admin group
curl -i -u member:demo123 http://localhost:8080/admin/status
curl -i -u admin:demo123 http://localhost:8080/admin/status

# Endpoint that exists but is not allowlisted
curl -i -u admin:demo123 http://localhost:8080/unlisted
~~~

In PowerShell, **curl** may be an alias for another command; use **curl.exe** instead of **curl** if needed.

### 5.3. Expected HTTP Results

| Request | Applied rule | Expected result | Body when 200 |
| --- | --- | --- | --- |
| GET /public/info, anonymous | permitAll | **200** | public-info |
| GET /account/profile, anonymous | authenticated | **401** | — |
| GET /account/profile, member | authenticated | **200** | hello-member |
| GET /reports/summary, member | hasAuthority(report:read) | **403** | — |
| GET /reports/summary, reader | hasAuthority(report:read) | **200** | report-summary |
| POST /reports/summary, reader | hasAuthority(report:write) | **403** | — |
| POST /reports/summary, editor | hasAuthority(report:write) | **200** | report-updated |
| GET /admin/status, member | hasRole(ADMIN) | **403** | — |
| GET /admin/status, admin | hasRole(ADMIN) | **200** | admin-ok |
| GET /unlisted, admin | anyRequest().denyAll() | **403** | — |

These are **expected results derived from the configuration source code**, not a transcript of an actual run. Headers, error response bodies, and port details may vary by environment. Because the example has no login form, HTTP Basic normally returns **401 Unauthorized** for requests without valid authentication instead of redirecting to a login page.

**Why does admin get 403 on /unlisted?** The final policy is denyAll, with no "admin is allowed everywhere" exception. Even after successful authentication and with ROLE_ADMIN, endpoints outside the allowlist are denied.

**Why can't reader POST?** The `POST /reports/summary` request matches the POST rule, which requires report:write; report:read is insufficient. Sharing the same path does not make the two permissions interchangeable.

## 6. Tracing a Request Step by Step

### Case A: Unauthenticated user calls /account/profile

~~~text
GET /account/profile, no Authorization header
        |
        +--> GET /public/info? no
        +--> GET /account/profile? yes
                      |
                      v
                authenticated()
                      |
                      +--> no valid Authentication
                      |
                      v
                HTTP Basic entry point -> 401
~~~

The profile() controller method is not called.

### Case B: reader sends GET /reports/summary

~~~text
GET /reports/summary
Authorization: reader's Basic credentials
        |
        +--> user reader authenticated successfully
        +--> GrantedAuthority = ["report:read"]
        +--> GET /reports/** matches
        +--> hasAuthority("report:read") satisfied
        |
        v
readReport() controller -> HTTP 200, "report-summary"
~~~

### Case C: reader sends POST /reports/summary

~~~text
POST /reports/summary
Authorization: reader's Basic credentials
        |
        +--> user reader authenticated successfully
        +--> GrantedAuthority = ["report:read"]
        +--> GET /reports/**? no, different HTTP method
        +--> POST /reports/**? yes
        +--> requires "report:write" but missing
        |
        v
HTTP 403; updateReport() is not called
~~~

The POST in this example is not blocked by CSRF beforehand because the demo **explicitly disabled CSRF**. In an application with CSRF enabled, a POST request can receive **403 due to a missing/invalid CSRF token even when the user already has report:write**. You must distinguish CSRF errors from authorization errors.

### Case D: User with the admin role

~~~text
GET /admin/status, admin credentials
        |
        +--> UserDetails built with roles("ADMIN")
        +--> authorities contain "ROLE_ADMIN"
        +--> /admin/** matches, requires hasRole("ADMIN")
        +--> by default hasRole("ADMIN") expects "ROLE_ADMIN"
        |
        v
HTTP 200, "admin-ok"
~~~

If the system grants the authority **ADMIN** without a prefix, hasRole("ADMIN") by default does **not** consider it satisfied. Authority naming must be consistent at the layer that maps data into Authentication.

## 7. Designing Endpoint Groups Without Unintended Exposure

### 7.1. Set an Explicit Policy for Each Group

Suppose the system adds URLs:

~~~text
/public/**
/account/**
/reports/**
/admin/**
~~~

Do not use **/reports/** → authenticated()** if reading and writing reports require separate permissions. Define explicit GET and POST rules, then use denyAll for unimplemented operations.

Do not leave the ordering like this:

~~~java
// Dangerous: broad rule hides specific protection rule:
.requestMatchers("/reports/**").authenticated()
.requestMatchers(HttpMethod.POST, "/reports/**")
    .hasAuthority("report:write")
~~~

The first rule already matches every /reports/** request, including POST.

Fix by putting method-specific rules first:

~~~java
.requestMatchers(HttpMethod.GET, "/reports/**")
    .hasAuthority("report:read")
.requestMatchers(HttpMethod.POST, "/reports/**")
    .hasAuthority("report:write")
.anyRequest().denyAll()
~~~

If there are additional rules for PUT/PATCH/DELETE, declare them explicitly before denyAll after confirming business requirements.

### 7.2. Do Not Mix Public and Internal Groups

Do not write **requestMatchers("/**").permitAll()** as a "temporary fix for 403"; it renders the rules below ineffective. Nor should you set **anyRequest().permitAll()** as a default when the project requires endpoint protection. A safe policy allows strictly what is in the matrix and denies the rest, unless business logic intentionally requires otherwise.

### 7.3. URLs Alone Are Not Enough to Decide All Permissions

For example:

- A user has report:read but may only view reports belonging to **their own tenant**.
- Someone with report:write may only update a report while it is in **DRAFT** status.
- An administrator for department A may not approve transactions for department B.

Conditions such as tenant, ownership, and resource state must be checked in the service/authorization layer or an AuthorizationManager with sufficient business context. **hasRole/hasAuthority on a URL group is only the first line of defense**, not proof that the user may act on *every record* behind that endpoint.

### 7.4. Watch Out for Internal URLs and Dispatchers

Spring Security generally evaluates the request path; **do not rely on the frontend hiding a button** or on controller names to enforce permissions. If the application uses forwards, error dispatches, static assets, CORS preflight, or actuator endpoints, decide which policy governs them. For instance, an application with special ERROR/FORWARD dispatchers may need appropriate dispatcherTypeMatchers configuration so error pages work; do not blindly open all dispatchers in a system with risk.

## 8. Accompanying Security Concerns

### CSRF When Protecting State-Changing HTTP Methods

**Authorization** and **CSRF** are two distinct checks. Having **report:write** does not mean a browser POST request is always legitimate; if authentication is sent automatically by the browser (cookies, sessions, and in some cases Basic), another website can abuse the browser environment to trigger unwanted requests.

In the curl example, CSRF was disabled to demonstrate POST authorization outcomes. In a real system:

1. Determine whether browsers automatically attach credentials to cross-origin requests.
2. If CSRF applies, configure CSRF tokens and require the frontend to send a valid token on state-changing requests.
3. If the API design does not depend on automatic browser credentials, evaluate and document the rationale before disabling CSRF for the applicable API scope.
4. Do not use **permitAll** or **hasAuthority** as a substitute for CSRF checks.

### CORS Is Not Authorization

CORS decides whether a web page at another origin is allowed by the browser to read or send certain requests; it **does not grant business permissions**. An API cannot treat setting Access-Control-Allow-Origin as equivalent to hasAuthority. Non-browser attackers/clients can still call the API directly, so the server must always enforce Authentication and Authorization.

### Permissions Should Follow Least Privilege

Do not assign **ROLE_ADMIN** or write permissions by default to every new account. When using JWT or an identity provider, verify the conversion into GrantedAuthority (for example, scopes may be named **SCOPE_...** rather than report:read). Authority names in policy rules must match the mapped names.

### Method Security Supplements URL Policy

If a sensitive operation can be invoked from multiple paths, you can use **@EnableMethodSecurity** and **@PreAuthorize** on service methods to enforce permissions close to business logic. This is a complementary layer, not a reason to skip reviewing URL rules. For per-record permission checks, the service must receive the resource/user context to perform accurate validation.

## 9. Distinguishing 401, 403, and 404 During Testing

| HTTP status | Common meaning in the demo | What to check |
| --- | --- | --- |
| **200** | Authentication/authorization allowed the request; handler succeeded | Is the right rule matched and is the business response body correct? |
| **401** | Missing or invalid credentials; Basic entry point requests authentication | Authorization header, user details, Basic/token mechanism |
| **403** | Authenticated but missing permission, hit denyAll, or rejected by another protection layer (like CSRF) | Actual authorities, first matching rule, CSRF, fallback rule |
| **404** | No matching handler after the request passed required security layers | URL mapping, HTTP method, context path; do not jump to blaming permissions |
| **405** | Path exists but HTTP method is unsupported by the controller, provided security checks passed | @GetMapping/@PostMapping annotations, router, method rules |

Do not claim every non-existent URL returns 404: if **anyRequest().denyAll()** rejects it beforehand, the application can return 401/403 before reaching handler lookup. Likewise, a page using form login may redirect **302** for unauthenticated users instead of returning 401.

### Enable Logs When Diagnosing

Use only in development when needed:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Check in order: (1) request method/path, (2) applied SecurityFilterChain, (3) Authentication/principal, (4) actual GrantedAuthority values, (5) first matching RequestMatcher, (6) rule, (7) CSRF/entry point/handler errors. Avoid logging passwords, session identifiers, tokens, or sensitive data.

## 10. A Valuable Testing Strategy

From the matrix in section 3, each group should have:

- **At least one allowed case**: e.g., reader GET /reports/summary receives 200.
- **One missing-authentication case**: anonymous GET /account/profile receives 401 with Basic.
- **One authenticated-but-unauthorized case**: reader POST /reports/summary receives 403.
- **One negative case for other operations**: editor PUT /reports/summary is not automatically allowed just for having report:write.
- **One negative case for undeclared paths**: admin GET /unlisted is blocked by denyAll.

You can write integration tests with **spring-boot-starter-test**, **spring-security-test**, and **MockMvc** to avoid manual re-testing on every config change. The snippet below is an **illustrative fragment** inside a test class with MockMvc configured, not a standalone Java program:

~~~java
mvc.perform(get("/reports/summary")
        .with(httpBasic("reader", "demo123")))
    .andExpect(status().isOk());

mvc.perform(post("/reports/summary")
        .with(httpBasic("reader", "demo123")))
    .andExpect(status().isForbidden());

mvc.perform(post("/reports/summary")
        .with(httpBasic("editor", "demo123")))
    .andExpect(status().isOk());
~~~

Common static imports: **org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic**, **org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get/post**, **org.springframework.test.web.servlet.result.MockMvcResultMatchers.status**. If the application enables CSRF for POST, tests must supply a valid token when testing authorization rather than failing at CSRF.

When URLs change or endpoint groups are added, update the **permission matrix first**, then update rules and tests. Never test with only a single admin account, as that misses many authorization bugs.

## 11. Applying the Idea with Spring WebFlux

With WebFlux, the configuration API names differ from Servlet:

| Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- |
| SecurityFilterChain | SecurityWebFilterChain |
| HttpSecurity | ServerHttpSecurity |
| authorizeHttpRequests | authorizeExchange |
| requestMatchers | pathMatchers |
| HttpServletRequest | ServerWebExchange |

Policy-equivalent reactive fragment (placed in **ServerHttpSecurity** configuration, not a standalone Java program):

~~~java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/public/info").permitAll()
        .pathMatchers(HttpMethod.GET, "/account/profile").authenticated()
        .pathMatchers(HttpMethod.GET, "/reports/**")
            .hasAuthority("report:read")
        .pathMatchers(HttpMethod.POST, "/reports/**")
            .hasAuthority("report:write")
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll());
~~~

The principles remain checking paths, methods, Authentication, authorities, and rule order. **Do not use HttpSecurity in a pure WebFlux project**. Reactive has its own asynchronous authentication/security context mechanism; when switching stacks, verify security filters, CSRF, test clients, and converters accordingly. This fragment only translates the **authorization policy**, not a complete SecurityWebFilterChain bean.

## 12. Common Configuration Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Placing /**.authenticated() before /admin/**.hasRole("ADMIN") | Regular users can enter the admin group because the first rule matches | Move specific rules first; consider denyAll at the end. |
| Using /reports/**.authenticated() for both GET/POST | Any logged-in user can also modify data | Distinguish HTTP methods and require read/write authorities. |
| Only checking whether the frontend shows a button | Clients can call the API directly | Protect requests on the backend with Spring Security. |
| Allowing all unmatched requests with permitAll() | New endpoints can become unintentionally public | Use anyRequest().denyAll() in an allowlist policy. |
| Omitting a fallback SecurityFilterChain when using multiple chains | URLs may match no chain and bypass Spring Security protection | Design matchers/priorities properly; include a suitable fallback chain. |
| Having ADMIN while hasRole("ADMIN") returns 403 | Actual Authentication only has ADMIN, not ROLE_ADMIN | Standardize mapping or use hasAuthority accordingly. |
| Having report:read while GET returns 403 | Different authority name, converter not granting the right authority, or an earlier matcher intercepts | Inspect Authentication.getAuthorities() and the first matching rule. |
| POST returns 403 despite having report:write | May lack a CSRF token or another rule matched first | Check logs, token, CSRF configuration, and matcher order. |
| Broadening write permissions as a quick fix | Violates the principle of least privilege | Fix the root cause in matchers/mappings and test denied cases. |
| Using hasRole for permissions like invoice:approve | Easy to confuse the ROLE_ prefix and business roles | Use hasAuthority("invoice:approve") for granular permissions. |
| Checking only general permission without data ownership | Users with group access can read/modify others' records | Add ownership/tenant/resource checks in the service/authorization layer. |
| Letting all OPTIONS through with unconditional permitAll | May widen access beyond policy intent | Configure CORS/preflight in context and test actual behavior. |

## 13. Questions and Exercises

1. If **GET /reports/summary** requires report:read, why is a successful user login not enough?
2. Why must **requestMatchers("/admin/**").hasRole("ADMIN")** be placed before a broad rule like **requestMatchers("/**").authenticated()**?
3. If editor has report:read and report:write, can editor access **/admin/status** by default? Explain using GrantedAuthority.
4. For endpoint **DELETE /reports/summary**, what will the demo configuration do? What prevents the report:write authority from automatically allowing DELETE?
5. Why can POST return 403 even when Authentication contains the right authority? Explain the role of CSRF.
6. When creating an **/orders/** API group, how would you authorize GET (read), POST (create), DELETE (delete), and per-*order* permissions?
7. If an application uses two SecurityFilterChain beans, how do **securityMatcher** and **requestMatchers** control two different decisions?
8. Trace reading: **reader** calls **POST /reports/summary** with valid credentials. Authentication succeeds; which rule matches, and why is the controller not invoked?

**Key takeaway:** Endpoint protection design starts with a **method + URL + identity/authority matrix**. Inside a SecurityFilterChain, the **first matching rule** decides the check. Use **permitAll** for public endpoints, **authenticated** for login-only areas, **hasRole/hasAuthority** for permission-specific areas, and **denyAll** for everything not explicitly allowed. Always verify CSRF and data-level permission conditions when business logic requires them.

## Official Spring Security Documentation

- Spring Security 6.5 — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Java Configuration, securityMatcher vs requestMatchers: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Authorize ServerHttpRequest (Reactive): https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
