# Multiple Security Filter Chains, Precedence, and Fallback Chains in Spring Security

## 1. Problem and Objectives

A Spring Boot application can have multiple HTTP areas with different security requirements: REST APIs, admin pages, public pages, and operational endpoints. For example:

- **/api/** uses HTTP Basic in the lab or OAuth2 Resource Server/Bearer tokens in a real application.
- **/admin/** requires the ADMIN role.
- **/** and **/status** are public endpoints.
- Unclassified URLs must have an explicit policy rather than becoming public automatically.

Spring Security supports multiple **SecurityFilterChain** beans. Each chain can hold its own set of filters and access rules. However, **FilterChainProxy applies only the first SecurityFilterChain matching the request**, rather than running all chains and combining their conditions.

Therefore you must control:

1. **Scope:** Which URL or RequestMatcher does this chain apply to?
2. **Order:** Which chain is evaluated first?
3. **Fallback:** How are requests outside specialized chains handled?
4. **Internal rules:** Once a chain is selected, does authorization allow the request?
5. **Testing:** Does every important URL have an appropriate chain with no bypass path?

This lesson uses **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. With WebFlux, the corresponding configuration uses SecurityWebFilterChain and ServerHttpSecurity, not Servlet's HttpSecurity directly.

### After This Lesson, You Can

- Distinguish **securityMatcher** from **requestMatchers**.
- Explain @Order, first-match selection, and fallback chains.
- Build three chains—API, admin, and fallback—using the modern lambda DSL.
- Read an HTTP test matrix covering **200, 401, 403, and 404**.
- Spot overly broad chains shadowing specific chains, missing fallbacks, login URLs outside a chain, or misordered authorization rules.
- Separate authentication, authorization, CSRF, sessions, and data permissions according to their proper responsibilities.

## 2. Where FilterChainProxy Sits

In Servlet, a request enters the servlet container, passes through DelegatingFilterProxy, and reaches FilterChainProxy. FilterChainProxy holds an ordered list of SecurityFilterChains.

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
FilterChainProxy
    |
    +--> SecurityFilterChain 1: @Order(1), /api/** ?
    |        |
    |        +-- Match: SELECT chain 1, stop checking later chains
    |
    +--> SecurityFilterChain 2: @Order(2), /admin/** ?
    |        |
    |        +-- Match: SELECT chain 2, stop checking later chains
    |
    +--> SecurityFilterChain fallback: no securityMatcher
             |
             +-- Match: use last chain for remaining URLs

Inside the selected chain:
    authentication / security context / CSRF / authorization
    |
    v
DispatcherServlet -> Controller -> Service
~~~

This conceptual diagram does not assert the exact internal order of every security filter. It emphasizes that **a request is selected by only one SecurityFilterChain**.

For instance, GET /api/orders matches the /api/** scope. Even though the fallback chain has a default matcher matching all URLs, the request enters only the API chain because it has higher priority.

**Important:** If the API chain selects the request and then returns 403 due to a missing role, FilterChainProxy **does not forward the request to fallback to retry**. Fallback applies only to requests that matched no earlier chain.

### Three Different Kinds of Ordering

| Ordering type | Purpose | Example |
| --- | --- | --- |
| **SecurityFilterChain order** | Selects one chain for the request | @Order(1) before @Order(2) |
| **Filter order inside a chain** | Executes security steps of the chosen chain | Authentication filter, AuthorizationFilter |
| **Authorization rule order inside a chain** | Selects the rule protecting the request | Specific matchers before anyRequest |

Do not confuse multiple chains with multiple filters. One chain **contains multiple filters**; multiple chains are multiple configuration choices, and FilterChainProxy selects only the first matching chain.

## 3. securityMatcher and requestMatchers Are Not Equivalent

**securityMatcher** is an HttpSecurity/chain-level matcher: it decides whether the entire SecurityFilterChain is selected for a request.

**requestMatchers** is used inside authorizeHttpRequests: it selects an authorization rule **after the chain has already been selected**.

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public").permitAll()
        .anyRequest().hasRole("API")
    );
~~~

This is an illustrative DSL snippet inside a method building a SecurityFilterChain.

| Request | Does API chain match? | Rule once inside chain |
| --- | --- | --- |
| GET /api/public | Yes | permitAll |
| GET /api/orders | Yes | anyRequest().hasRole("API") |
| GET /admin/dashboard | No | No rule in the API chain is evaluated |
| GET /reports | No | Needs another chain or fallback |

**anyRequest() inside a chain with securityMatcher** applies only to requests that entered that chain's scope. It does not cover every URL in the entire application.

If you omit **securityMatcher("/api/**")** while keeping **requestMatchers("/api/**")** inside authorizeHttpRequests, the chain is not restricted to API-only. It can also accept admin requests; this is a serious source of bugs when chains have different priorities.

### Matchers and Real-World URLs

Spring Security can use RequestMatcher implementations suited to Servlet/Spring MVC. In applications with reverse proxy rewrites, context paths, servlet paths, or multiple servlet registrations, the URL seen by the client may differ from the path the app actually evaluates. Check the method and path inside the application rather than inferring matchers solely from public URLs.

## 4. @Order: Chain Evaluation Precedence

A **smaller** @Order number has higher priority. In this pattern:

| Bean | Priority | Scope |
| --- | --- | --- |
| apiChain with @Order(1) | Highest | /api/** |
| adminChain with @Order(2) | Next | /admin/** |
| fallbackChain without @Order | After the two chains above | All unselected URLs |

A chain that declares no securityMatcher defaults to matching **all requests**. Thus it should come after specific chains. Placing a catch-all at @Order(1) can capture all requests and shadow chains behind it.

### 4.1. Example of Misconfiguration from an Overly Broad Matcher

This is a **dangerous example solely for recognizing the bug**; never use it in practice:

~~~java
@Bean
@Order(1)
SecurityFilterChain accidentalCatchAll(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
        .build();
}
~~~

Lacking a securityMatcher, this chain matches /api/**, /admin/**, and every other path. With top priority and permitAll, it prevents API/admin protection chains behind it from ever being selected.

### 4.2. Example of Mistaking requestMatchers for a Chain Boundary

~~~java
@Bean
@Order(1)
SecurityFilterChain mistaken(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/**").hasRole("API")
            .anyRequest().permitAll()
        )
        .build();
}
~~~

This chain has no securityMatcher. A request to /admin/dashboard can enter this chain and match anyRequest().permitAll(). The right fix is setting **securityMatcher("/api/**")** at the HttpSecurity level before configuring rules.

### 4.3. Overlapping Scopes

If you have an /api/admin/** chain and an /api/** chain, both can match /api/admin/reports. In that case, the narrower **/api/admin/** matcher must have higher priority if you want it selected. Set @Order explicitly instead of relying on method/bean naming order, and test URLs in overlapping regions.

## 5. Fallback Chain and Behavior When No Chain Matches

If **no SecurityFilterChain matches**, the request **is not protected by Spring Security**. It can still reach Servlet/MVC or pass through other filters, but it will not be checked by Spring Security's authentication/authorization filters in those unmatched chains.

For example, with only two chains /api/** and /admin/**, GET /reports/export belongs to neither chain. When a /reports/export Controller is added later, the application can accidentally expose that endpoint.

To prevent this, add a fallback chain:

- Ordered after the API/admin chains.
- **No securityMatcher**, so it matches remaining requests.
- Only permitAll explicitly defined public endpoints.
- Use **anyRequest().denyAll()** or **anyRequest().authenticated()** depending on policy.

In this lesson, fallback uses **denyAll** for unclassified URLs.

### Fallback denyAll Does Not Always Mean HTTP 403

If an unauthenticated request enters a denyAll fallback while HTTP Basic is enabled, Spring Security can use the AuthenticationEntryPoint to return **401**. A request with valid credentials that still hits denyAll typically receives **403**.

The HTTP status depends on authentication state and how exception handling is configured. What truly matters is verifying **the request entered the right chain and was rejected by policy**, rather than rigidly expecting only one status code.

## 6. Designing the Three-Chain Example

We use the following endpoints:

| Endpoint | Selected chain | Rule |
| --- | --- | --- |
| GET /api/public | API @Order(1) | No authentication required |
| GET /api/orders | API @Order(1) | ROLE_API |
| GET /admin/dashboard | Admin @Order(2) | ROLE_ADMIN |
| GET / | Fallback | No authentication required |
| GET /status | Fallback | No authentication required |
| GET /unknown | Fallback | denyAll |

Sample accounts:

| Username | Demo password | Role |
| --- | --- | --- |
| api-user | api-pass | API |
| admin-user | admin-pass | ADMIN |
| ops-user | ops-pass | API and ADMIN |

With standard UserDetailsService, **roles("API")** creates authority **ROLE_API**, and **roles("ADMIN")** creates **ROLE_ADMIN**. The ADMIN role **does not automatically imply ROLE_API**. ops-user is granted both so it can call both areas.

These accounts are only for learning on localhost; real applications need an identity store, HTTPS, secret protection, and appropriate operational policies.

## 7. Complete Spring Boot 3.x Example

### 7.1. Dependencies

Use Spring Initializr to create a Boot 3.x, Java 17+ project with Gradle Wrapper and the following starters in **build.gradle** (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

This snippet sits inside a Boot project with plugins/build tools already generated; it is not a standalone Gradle file.

### 7.2. Java Source

Create **src/main/java/com/example/multichain/MultiChainApplication.java**:

~~~java
package com.example.multichain;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MultiChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiChainApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyRequest().hasRole("API")
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/admin/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    // Fallback without securityMatcher restriction.
    @Bean
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/", "/status").permitAll()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("api-user")
                .password(encoder.encode("api-pass"))
                .roles("API")
                .build(),
            User.withUsername("admin-user")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build(),
            User.withUsername("ops-user")
                .password(encoder.encode("ops-pass"))
                .roles("API", "ADMIN")
                .build()
        );
    }
}

@RestController
class DemoController {

    @GetMapping("/")
    String home() {
        return "home OK";
    }

    @GetMapping("/status")
    String status() {
        return "ready";
    }

    @GetMapping("/api/public")
    String publicApi() {
        return "api public OK";
    }

    @GetMapping("/api/orders")
    String orders(Principal principal) {
        return "orders for " + principal.getName();
    }

    @GetMapping("/admin/dashboard")
    String dashboard() {
        return "admin dashboard OK";
    }
}
~~~

This is **a single Java file** inside a configured Spring Boot project. The public class matches the filename; DemoController in the same package is picked up by Spring Boot component scanning. The three SecurityFilterChain beans have their own matchers and ordering.

**Explanation:**

1. **apiChain:** @Order(1), for /api/** only. GET /api/public is permitAll; remaining API requests require ROLE_API.
2. **adminChain:** @Order(2), for /admin/** only, requiring ROLE_ADMIN.
3. **fallbackChain:** no @Order and no securityMatcher, handling remaining URLs; GET / and GET /status are permitAll, and other URLs are denyAll.
4. **HTTP Basic** is enabled on all three chains so 401/403 responses can be observed via curl; form login is disabled in the demo.
5. **SessionCreationPolicy.STATELESS** is set only on the API chain. That does not make admin/fallback stateless and **does not automatically disable CSRF**.
6. **CSRF protection remains at its default.** The example only has GET endpoints. Adding POST/PUT/DELETE requires evaluating CSRF by how clients send credentials; HTTP Basic used in a browser can also carry CSRF risk.
7. **BCryptPasswordEncoder** hashes the in-memory users. Hardcoded passwords are for learning only, never for production.

## 8. Running and Testing with curl

At the project root directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell, use **.\gradlew.bat bootRun**. Once the server listens on localhost:8080, try:

~~~bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/status
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/orders
curl -i -u api-user:api-pass http://localhost:8080/api/orders
curl -i -u admin-user:admin-pass http://localhost:8080/api/orders
curl -i -u api-user:api-pass http://localhost:8080/admin/dashboard
curl -i -u admin-user:admin-pass http://localhost:8080/admin/dashboard
curl -i -u ops-user:ops-pass http://localhost:8080/api/orders
curl -i -u ops-user:ops-pass http://localhost:8080/admin/dashboard
curl -i -u admin-user:admin-pass http://localhost:8080/unknown
curl -i -u api-user:api-pass http://localhost:8080/api/unknown
~~~

PowerShell may require **curl.exe** because curl is an alias. Passwords in the commands are for local demo only; in real operations, you can use **curl -u api-user URL** to enter passwords via prompt instead of leaving them in shell history. Use HTTPS when sending credentials over a network.

### Expected Results

| Request | Chain | HTTP status | Body / reason |
| --- | --- | --- | --- |
| GET /, anonymous | Fallback | **200** | home OK |
| GET /status, anonymous | Fallback | **200** | ready |
| GET /api/public, anonymous | API | **200** | api public OK |
| GET /api/orders, anonymous | API | **401** | Missing Basic authentication |
| GET /api/orders, api-user | API | **200** | orders for api-user |
| GET /api/orders, admin-user | API | **403** | Missing ROLE_API |
| GET /admin/dashboard, api-user | Admin | **403** | Missing ROLE_ADMIN |
| GET /admin/dashboard, admin-user | Admin | **200** | admin dashboard OK |
| GET /api/orders, ops-user | API | **200** | Has ROLE_API |
| GET /admin/dashboard, ops-user | Admin | **200** | Has ROLE_ADMIN |
| GET /unknown, admin-user | Fallback | **403** | denyAll in fallback |
| GET /api/unknown, api-user | API | **404** may occur | Passed authorization but no Controller |

These are **expected statuses from the configuration**, not measurements captured from a running process in this document. URL rewrites, context paths, extra filters, or custom exception handlers can alter responses.

**Why can /api/unknown return 404 while /unknown returns 403?** The /api/unknown request enters the API chain; api-user has sufficient authority so it reaches MVC, where no mapping exists. /unknown enters fallback and is stopped by denyAll before MVC looks up a Controller.

**Why can permitAll still return 401?** If a client explicitly sends an Authorization: Basic header with the wrong password to /api/public, BasicAuthenticationFilter may attempt authentication and fail before permitAll authorization is evaluated. permitAll only means Authentication is not required for that endpoint.

## 9. Having No Fallback Is a Security Gap

Suppose only apiChain and adminChain exist. GET /reports/export matches neither /api/** nor /admin/**. Then **Spring Security does not protect this request with the declared chains**.

If no Controller exists yet, the request may return 404. Yet when a developer adds a Controller at /reports/export later, having no matching chain means the endpoint can be accessed without passing through the intended security filters.

That is why Spring Security documentation recommends having a SecurityFilterChain without a securityMatcher so the entire application is covered. The fallback should define an explicit policy, such as permitAll for known public URLs and anyRequest().denyAll().

**Do not assume fallback retries requests rejected by API/admin.** Only requests that matched no earlier chain enter fallback.

## 10. Rule Order Inside One Chain

Beyond @Order between chains, examine the order of requestMatchers inside authorizeHttpRequests.

**Correct:** Specific public rule before catch-all rule:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
    .anyRequest().hasRole("API")
)
~~~

**Error-prone:** Broad permitAll rule placed before private rule:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/private").hasRole("API")
    .anyRequest().denyAll()
)
~~~

/api/private can match the first permitAll rule, so the later hasRole rule fails to protect it. This is an **authorization rule ordering bug inside a chain**, distinct from **selecting the wrong SecurityFilterChain**.

## 11. Trap: Login URL Outside Chain Scope

Suppose a design has:

- adminChain matching only **/admin/**.
- Developer enables default **formLogin**.
- Form login uses **/login** as the processing endpoint by default.
- **/login** lies outside /admin/**.

POST /login then never enters adminChain, so adminChain's UsernamePasswordAuthenticationFilter does not process it as expected. You may get 404 or be denied by fallback.

The right design ensures login page, loginProcessingUrl, logout, and callbacks **belong to the chain whose filters handle them**. For example, use /admin/login for both GET page and POST processing, set permitAll for the relevant endpoint, and handle CSRF for POST and sessions according to the client type.

This lesson's runnable example uses **HTTP Basic on adminChain** to avoid needing a login form. When moving to real OIDC/form login, configure paths and handlers completely.

## 12. CSRF, Sessions, CORS, and Authentication Per Chain

Different chains can use different filter sets:

- API may use HTTP Basic or Resource Server validating Bearer tokens.
- Admin pages may use form login/OIDC, session cookies, and CSRF tokens.
- Fallback may deny unclassified URLs.

**Filters from the fallback chain do not accumulate onto the API chain.** For a control to apply to the API, it must be configured on the API chain or another layer that actually runs for that request.

Key reminders:

1. **Stateless does not make CSRF disappear automatically.** Risk depends on how browsers send credentials, such as HTTP Basic or cookies.
2. When using Bearer JWTs, verify signature, issuer, audience, expiry, and map claims to authorities per policy. Multiple SecurityFilterChains do not create an Authorization Server.
3. **OPTIONS/CORS preflight** must be handled properly before an authentication rule rejects it inappropriately.
4. An API's **AuthenticationEntryPoint** may return 401 while web login redirects 302; the selected chain determines which mechanism applies.
5. CSRF, headers, logout, cookies, and session policies must be verified on the right chain; never assume settings in fallback apply to the API.
6. **URL authorization** does not replace checking ownerId/permissions for individual records in Service/Repository.

### Actuator and Reverse Proxies

Spring Boot Actuator endpoints usually live under **/actuator/** or on a separate management port; /status in the demo is just an ordinary Controller. When using custom SecurityFilterChains, review Actuator endpoint exposure and access policies. Do not infer that /api/** and /admin/** cover all management endpoints.

Reverse proxies can rewrite URLs. Confirm the path Spring Security actually receives, context paths, and trusted headers before concluding a chain matcher is right.

## 13. Systematic Debugging Workflow

When a request produces an unexpected status:

1. Check HTTP method, URL, servlet/context path, and proxy rewrites.
2. List all SecurityFilterChains, matchers, and @Order values.
3. Determine the **first matching chain**, or spot that no chain matched.
4. Check whether that chain's authentication filter receives and verifies credentials.
5. Inspect principal, authorities, and authenticated status after authentication.
6. Identify which requestMatchers or anyRequest rule applied.
7. Check whether CSRF, CORS, session, or exception handling rejected the request.
8. Check Controller mappings to distinguish 403 from 404.
9. Test supporting URLs such as login/logout, OAuth2 callbacks, Actuator, and OPTIONS.
10. Write negative tests for undeclared URLs and users lacking roles.

You can enable Spring Security DEBUG logging during development to observe which chain is selected, but **never log raw Authorization headers, passwords, tokens, cookies, or secrets**.

### Pre-Deployment Test Matrix

| Test | Expected |
| --- | --- |
| Public API without credentials | 200 via API chain |
| Private API without credentials | 401 via API chain |
| Private API missing ROLE_API | 403 via API chain |
| Admin missing ROLE_ADMIN | 403 via adminChain |
| Admin with ROLE_ADMIN | 200 via adminChain |
| New unclassified URL | Denied by fallback |
| Overlapping API/admin URL | Higher-priority chain selected |
| Login processing and callback | Inside the chain handling authentication |
| Actuator and management endpoints | Protected by explicit policy |
| Resource owned by someone else | Denied by business authorization |

## 14. Common Misconceptions

**"Requests pass through every SecurityFilterChain."** False: FilterChainProxy uses the first matching chain.

**"@Order(1) is always best."** False: an overly broad high-priority chain can shadow later policies.

**"requestMatchers("/api/**") restricts the whole chain."** False: securityMatcher restricts chain scope.

**"anyRequest().denyAll() in adminChain blocks every URL."** False: it applies only to requests belonging to adminChain.

**"When no chain matches, Spring Security returns 403 automatically."** False: the request is unprotected by Spring Security's chains.

**"Fallback lets rejected API requests try again."** False: once a chain is selected, fallback is not invoked if authorization fails.

**"Form login /login works automatically in a chain matching only /admin/**."** Not necessarily: the login processing endpoint must lie within the scope of the chain holding that filter.

**"SessionCreationPolicy.STATELESS removes all CSRF risks automatically."** False: CSRF depends on browser/credential behavior.

**"ADMIN can always access the API."** False: API and ADMIN roles are independent unless policy grants shared access.

**"ROLE_API alone protects everyone's data."** False: resource ownership checks are still needed.

## 15. Self-Check Questions

**Question 1.** GET /api/orders matches both API and fallback; how many chains are selected?  
**Answer:** One: the API chain has higher priority.

**Question 2.** Remove fallback; GET /reports matches no chain. Is it guaranteed to return 403?  
**Answer:** No. The request is not protected by Spring Security chains.

**Question 3.** Does anyRequest().hasRole("ADMIN") in adminChain protect /api/orders?  
**Answer:** No, because /api/orders selects the API chain.

**Question 4.** What is the risk of a chain with no securityMatcher, @Order(1), and permitAll?  
**Answer:** It can match every request, shadowing the API/admin protection chains.

**Question 5.** admin-user gets 403 on /api/orders despite valid login; why?  
**Answer:** It has ROLE_ADMIN but lacks ROLE_API.

**Question 6.** Why is ops-user allowed into both areas?  
**Answer:** It holds both ROLE_API and ROLE_ADMIN.

**Question 7.** A chain matches only /admin/**, yet formLogin processes /login. What can go wrong?  
**Answer:** /login lies outside the chain, so the chain's login filter does not handle the request.

**Question 8.** /api/unknown can return 404 while /unknown gets 403 from fallback; what is the difference?  
**Answer:** The API request passed policy yet had no MVC mapping; fallback denied /unknown earlier.

**Question 9.** Distinguish securityMatcher from requestMatchers.  
**Answer:** One selects the SecurityFilterChain's scope; the other selects authorization rules inside the chain.

**Question 10.** Why check Actuator and OAuth2 callbacks when using multiple chains?  
**Answer:** They may sit outside application prefixes and require dedicated matchers/policies.

## 16. Official References

- Java Configuration and Multiple HttpSecurity Instances: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Servlet Architecture and Multiple SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Boot 3.3 Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
