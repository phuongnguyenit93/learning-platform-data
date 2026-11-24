# FilterChainProxy Selects a SecurityFilterChain

A Spring Boot application may simultaneously have machine-facing APIs (`/api/**`), an administrative UI (`/admin/**`), and web pages using form login (`/web/**`). These three request groups may need **different authentication mechanisms, session storage, error handling, and authorization policies**. So when an HTTP request enters the Servlet container, how does Spring Security know which security filters to run?

This is the job of **`FilterChainProxy`**: it inspects the configured `SecurityFilterChain` instances in priority order, **selects the first matching chain**, and executes **only the security filters in that chain**. It **does not combine** filters from all matching chains. If no chain matches, the request proceeds **without being protected by Spring Security** through any of those chains' filters.

This lesson explains the full path Servlet Filter → `DelegatingFilterProxy` → `FilterChainProxy` → `SecurityFilterChain` → DispatcherServlet, how `@Order` and `securityMatcher` determine the chain, how they differ from `requestMatchers` in authorization, vulnerabilities caused by wrong matchers/missing fallbacks, and how to test chain selection behavior on a Java 17+ application.

This covers **Spring Security Servlet/Spring MVC**. With Spring WebFlux, the system uses `SecurityWebFilterChain`/`WebFilterChainProxy` and a reactive-specific context; do not copy `jakarta.servlet.Filter` classes into WebFlux.

## 1. First, Understand Two Different Kinds of Filter Chains

The Servlet container (Tomcat/Jetty/Undertow...) manages a **Servlet `FilterChain`** for the request. Spring Security does not replace the Servlet container; it participates as a filter inside the container's chain.

~~~text
Browser / API client
        |
        v
Servlet Container (Tomcat)
        |
        v
Container Filter A, if present
        |
        v
DelegatingFilterProxy ("springSecurityFilterChain")
        |
        v
Spring Bean: FilterChainProxy
        |
        +-- Request matching --> First matching SecurityFilterChain
        |                               |
        |                               +--> Spring Security Filter 1
        |                               +--> Spring Security Filter 2
        |                               +--> ...
        |                               +--> Spring Security Filter N
        |
        v
Subsequent Servlet Filters (if any)
        |
        v
DispatcherServlet -> Controller -> Service
~~~

Distinguish three easily confused types:

| Type | Belongs To | Responsibility |
| --- | --- | --- |
| `jakarta.servlet.FilterChain` | Servlet API | Coordinates container filters and the Servlet for a request |
| `org.springframework.security.web.FilterChainProxy` | Spring Security | A special Servlet Filter that selects the security chain and orchestrates security filters |
| `org.springframework.security.web.SecurityFilterChain` | Spring Security | Defines a **`RequestMatcher`** and the list of security filters applied when a request matches |

**`SecurityFilterChain` is not directly a Servlet `FilterChain`.** It is a configuration object used by `FilterChainProxy`. When you declare `@Bean SecurityFilterChain`, Spring Security collects those beans and builds the corresponding execution structure.

You do not need to create `FilterChainProxy` yourself or manually register every security filter with the Servlet container in a normal Spring Boot application. The framework and Boot handle that wiring.

### What Can a Servlet Filter Do?

A `Filter` can:

1. Read/modify the request or response appropriately.
2. Call `chain.doFilter(request,response)` so the request continues.
3. **Not call** `chain.doFilter` when deciding to block or complete the response (e.g., returning 401/403).
4. Perform work after downstream processing completes, if the response/lifecycle allows.

Thus a `SecurityFilterChain` can halt a request **before the controller**. When an API returns 401, never assume the controller ran and threw the error.

## 2. DelegatingFilterProxy: Bridging the Servlet Container to a Spring Bean

The Servlet container understands the `jakarta.servlet.Filter` standard, whereas Spring manages beans in `ApplicationContext`. Spring Framework's `DelegatingFilterProxy` connects both worlds:

~~~text
Tomcat
  |
  +--> DelegatingFilterProxy
              |
              +--> Look up Spring Bean by name
                           |
                           v
                 "springSecurityFilterChain"
                           |
                           v
                      FilterChainProxy
~~~

In Servlet-based Spring Security, the delegated bean is typically named **`springSecurityFilterChain`**. This name is easily confused with the `SecurityFilterChain` interface: here it is **the name of the Spring Bean representing the proxy filter**, not the name of a single chain.

Pseudo-code:

~~~java
// Pseudocode: do not use as a replacement for the real DelegatingFilterProxy.
void doFilter(ServletRequest req, ServletResponse res, FilterChain chain) {
    Filter springManaged = findBean("springSecurityFilterChain");
    springManaged.doFilter(req, res, chain);
}
~~~

Normally you only define `SecurityFilterChain` `@Bean` methods in a configuration class. `DelegatingFilterProxy` is registered in the Servlet container via Boot/Spring Security integration. You should not arbitrarily create a second proxy, or requests may run duplicate security filtering.

**Lifecycle:** The Servlet container manages the lifecycle of the registered proxy/filter; internal Spring Security filters are managed by Spring. `FilterChainProxy` does not call standard Servlet `init/destroy` on each Spring-managed filter the way you might expect if wired manually. Use the appropriate bean lifecycle when building custom filters.

## 3. How Does FilterChainProxy Actually Select a Chain?

Each `SecurityFilterChain` has two essential parts:

- **Matcher:** `matches(HttpServletRequest)` decides whether the current request belongs to this chain.
- **Filters:** an ordered list of `jakarta.servlet.Filter` instances, executed only when the chain is selected.

A greatly simplified model:

~~~java
// Pseudocode illustrating FIRST MATCH; the framework includes firewall, wrappers,
// exception handling, and many other details.
for (SecurityFilterChain candidate : orderedChains) {
    if (candidate.matches(request)) {
        runOnly(candidate.getFilters(), request, response, servletChain);
        return;
    }
}
servletChain.doFilter(request, response); // no security chain
~~~

Read these two words carefully: **FIRST MATCH**. It is neither "pick the most specific chain by scoring" nor "merge all matching chains".

Suppose we have this setup:

| Order | Chain | Matcher | Authentication Type |
| --- | --- | --- | --- |
| 1 | API | `/api/**` | HTTP Basic or bearer token |
| 2 | Admin | `/admin/**` | Administrative policy |
| 3 | Web fallback | All remaining requests | Form login |

Execution path:

~~~text
Request GET /api/orders
    |
    +--> Chain #1 /api/**: MATCH!
    |        |
    |        +--> API security filters only
    |
    +--> DO NOT evaluate #2 or #3

Request GET /admin/panel
    |
    +--> Chain #1 /api/**: no
    +--> Chain #2 /admin/**: MATCH!
    |        |
    |        +--> Admin security filters only
    |
    +--> DO NOT evaluate #3

Request GET /web/profile
    |
    +--> Chain #1 /api/**: no
    +--> Chain #2 /admin/**: no
    +--> Chain #3 catch-all: MATCH!
             |
             +--> Web security filters only
~~~

**If the API chain returns 401 or 403, `FilterChainProxy` does not fall through to the Web fallback to try another login method.** Once a chain matches, chain selection is finished. Authorization failures or authentication failures occur **inside the selected chain** and do not cause the selector to try the next chain.

### Order, Not Path Length

Configuration:

~~~text
Order 1: /**             (catch-all)
Order 2: /api/**         (specific)
~~~

Will cause `/**` to match before `/api/**` ever gets a chance. Even though the API pattern looks more specific, Spring Security **does not reorder chains by specificity** when running `FilterChainProxy`. You must order them explicitly: **specific groups first, fallback last**.

Matchers can inspect HTTP method, headers, dispatcher type, or logic more complex than URLs; the first-match rule still holds. If two matchers overlap, `@Order` ordering is part of your security policy.

## 4. The Role of @Order with Multiple SecurityFilterChain Beans

In modern Java configuration, you can declare multiple beans:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain admin(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/admin/**")
        .authorizeHttpRequests(a -> a.anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(3)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

This is a **fragment** inside `@Configuration`; it requires imports, users, a password encoder, and an application. Section 7 has a complete project.

Rules:

- Lower `@Order` values are **evaluated first**: 1 before 2.
- A bean **without `@Order`** typically has lower priority than one annotated with `@Order(1)`; never rely on method declaration order in the file.
- Avoid giving two chains the same priority if you need deterministic ordering; order may not match assumptions.
- A fallback chain omits `securityMatcher` so it keeps the default matcher **matching every request**.
- `@Order` orders **among SecurityFilterChains**, which is different from the order of **Security Filters inside a chain**.

Do not confuse `@Order` on a chain with `@Order` on a `@Component Filter` registered separately by the container: they govern two different layers.

## 5. securityMatcher vs. requestMatchers: The Most Important Distinction

Two similarly named calls operate at different layers:

~~~java
http.securityMatcher("/api/**");
~~~

Means: **this chain applies only to requests matching `/api/**`**. This decides whether `FilterChainProxy` uses the chain at all.

~~~java
http.authorizeHttpRequests(a -> a
    .requestMatchers("/api/public").permitAll()
    .anyRequest().authenticated()
);
~~~

Means: **once this chain is selected, which authorization rule applies to the request?** This is not the outer chain selector.

Combined:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .requestMatchers("/api/public").permitAll()
        .anyRequest().authenticated()
    );
~~~

Behavior:

| Request | Enters API Chain? | Rule Inside Chain |
| --- | --- | --- |
| `GET /api/public` | Yes | `permitAll()` |
| `GET /api/orders` | Yes | `authenticated()` |
| `GET /admin/panel` | No | API rules are **not evaluated** |
| `GET /web/private` | No | API rules are **not evaluated** |

In this example, `anyRequest()` means "any request **currently handled by this chain**", not "every path across the entire application". If a chain has `securityMatcher("/api/**")`, then `.anyRequest().authenticated()` **does not cover** `/admin/**` or `/web/**`.

### Example of a Config That Looks Secure Yet Has a Gap

~~~java
// HAS A GAP if this is the ONLY SecurityFilterChain:
return http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .anyRequest().authenticated()
    )
    .build();
~~~

Endpoints outside `/api/**` **match no security chain**, so they are not protected by Spring Security filters; their controllers can receive requests directly. Recommendation: include a fallback chain protecting all remaining requests, or ensure leaving routes unprotected is an explicit, tested decision.

**`permitAll` and "no matching chain" are completely different**. `permitAll` stays inside the Spring Security pipeline, whereas matching no chain can bypass all of those protections.

### Why Doesn't a permitAll Rule Switch Chains?

If `/api/public` matches the API chain and a `permitAll` rule, Spring Security **does not hand the request over to the web chain** just because the endpoint is public. Chain selection is already done; permitAll only decides access inside that API chain.

Conversely, if the web chain has `requestMatchers("/api/public").permitAll()` while the API chain comes first and matches, the web chain's permitAll rule **never runs**. You must place rules in **the chain that is actually selected**.

## 6. HttpFirewall: A Trustworthy Path Is Needed Before Matching

`FilterChainProxy` also integrates **`HttpFirewall`** to inspect and wrap requests before matchers read paths. The typical implementation is `StrictHttpFirewall`, whose policy blocks certain abnormal URLs and potentially misleading path representations.

Example issues:

~~~text
/api/users
/api//users
/api/../admin/panel
/api/users;something=value
/api/%2e%2e/admin/panel
~~~

These strings are **not guaranteed to be treated identically by all servers**. The Servlet container, reverse proxy, URL decoder, firewall, and framework router may interpret paths differently. If the chain-selection layer sees one path while the controller layer sees another, a **path-based security bypass** can occur.

`HttpFirewall` aims to normalize/restrict risky inputs before matching. Never **disable StrictHttpFirewall or allow encoded slashes/semicolons** by default just to silence a 400 error on one endpoint; analyze path handling end-to-end from reverse proxy to Spring MVC and evaluate your threat model.

**Important:** filter chain selection can inspect properties of `HttpServletRequest`, not just the raw URI string. With custom matchers, understand `contextPath`, `servletPath`, `pathInfo`, encoding, query strings, and the matcher implementation of your exact Spring Security version.

### PathPatternRequestMatcher and Legacy Guides

In modern Spring Security, `securityMatcher("/api/**")` or `requestMatchers("/api/**")` builds matchers according to framework configuration. In Spring Security 7, do not blindly copy older guides using `antMatcher(...)` or `antMatchers(...)` from the `WebSecurityConfigurerAdapter` era. Check the documentation for the version you are running.

When a matcher must restrict by method, host, dispatcher type, or a custom predicate, you can use an appropriate `RequestMatcher`, but test equivalent URL variants and reverse-proxy path rewrites. An overly broad or semantically wrong matcher can select the wrong security chain.

## 7. Complete Hands-On Project: Three Chains, Two Login Styles, One Fallback

This example uses:

- Java **17+**.
- Spring Boot **4.1.2**, Spring Security managed by the Boot BOM.
- Spring MVC/Servlet on embedded Tomcat.
- HTTP Basic for `/api/**` and `/admin/**`, both with Spring Security's stateless session policy.
- Default form login for all remaining requests.
- A demo user with role `USER`; a demo admin with role `ADMIN`.
- `@Order(1)`, `@Order(2)`, `@Order(3)` with `securityMatcher` to prove first-match.
- `MockMvc` and `spring-security-test` exercising the real filter chain.

The goal is to see **where a request goes, which chain is selected, and which configuration produces 200/302/401/403**. All credentials here are local dummies. Never run unencrypted HTTP Basic APIs on the public Internet.

### 7.1. Project Structure

~~~text
filter-chain-proxy-lab/
  pom.xml
  src/main/java/com/example/filterlab/
    FilterChainLabApplication.java
    SecurityConfiguration.java
    DemoController.java
  src/test/java/com/example/filterlab/
    FilterChainSelectionTest.java
~~~

### 7.2. pom.xml

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>filter-chain-proxy-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-test</artifactId>
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

In Boot 4, the Servlet MVC starter is `spring-boot-starter-webmvc`; do not add `spring-boot-starter-webflux`. Test dependencies are managed by the Boot parent. In a real Boot app, do not override the Spring Security version individually unless deliberate and tested for compatibility.

### 7.3. Main Class

Create `src/main/java/com/example/filterlab/FilterChainLabApplication.java`:

~~~java
package com.example.filterlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterChainLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterChainLabApplication.class, args);
    }
}
~~~

### 7.4. SecurityConfiguration.java — Heart of the Lesson

Create `src/main/java/com/example/filterlab/SecurityConfiguration.java`:

~~~java
package com.example.filterlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("user")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-password"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain adminSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/admin/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            // NO securityMatcher: fallback chain for remaining requests.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .build();
    }
}
~~~

**How to read this code:**

1. `@Order(1)` causes the API chain to be evaluated first. Matcher `/api/**` defines the **chain scope**, not an authorization rule.
2. The API chain has `requestMatchers("/api/public").permitAll()`, whereas other `/api/**` paths require authentication.
3. `@Order(2)` is dedicated to `/admin/**`. Any request entering this chain requires `ROLE_ADMIN`; there is no `formLogin()` in this chain.
4. `@Order(3)` specifies no matcher, becoming the **fallback** for `/web/**`, `/public`, and `/login`.
5. `InMemoryUserDetailsManager` uses demo data; passwords are bcrypt-hashed, never stored in plaintext in `UserDetails`.
6. `SessionCreationPolicy.STATELESS` on API/Admin means those two chains do not rely on `HttpSession` to restore `SecurityContext`; they authenticate via Basic per request.
7. **This example does not call `csrf.disable()`.** The sample endpoints are GET-only. If you add POST/PUT/DELETE, evaluate CSRF based on whether browsers automatically send credentials—do not disable CSRF simply because you see the word API.

**One crucial detail:** `@Order(3)` on the web fallback does not make it "inactive" once API matches—it is never even reached. When a request targets `/api/data`, `FilterChainProxy` stops chain selection at API. It will not run the form-login chain's `UsernamePasswordAuthenticationFilter`.

### 7.5. DemoController.java

Create `src/main/java/com/example/filterlab/DemoController.java`:

~~~java
package com.example.filterlab;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String publicApi() {
        return "api-public";
    }

    @GetMapping("/api/data")
    public String apiData(Authentication authentication) {
        return "api-data:" + authentication.getName();
    }

    @GetMapping("/admin/panel")
    public String adminPanel(Authentication authentication) {
        return "admin-panel:" + authentication.getName();
    }

    @GetMapping("/public")
    public String publicWeb() {
        return "web-public";
    }

    @GetMapping("/web/private")
    public String privateWeb(Authentication authentication) {
        return "web-private:" + authentication.getName();
    }
}
~~~

The controller does not select a `SecurityFilterChain`; that happens **before the controller**. It simply works with the `Authentication` accepted by the corresponding security chain. Never determine admin privileges via `request.getParameter("role")` or pass a self-constructed `Authentication` from user input.

### 7.6. Testing with MockMvc: Right Chain, Right Result

Create `src/test/java/com/example/filterlab/FilterChainSelectionTest.java`:

~~~java
package com.example.filterlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterChainSelectionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiPublicIsAllowedByApiChain() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api-public"));
    }

    @Test
    void apiPrivateNeedsBasicCredentials() throws Exception {
        mvc.perform(get("/api/data"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/data")
                .with(httpBasic("user", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("api-data:user"));
    }

    @Test
    void adminChainRequiresAdminRole() throws Exception {
        mvc.perform(get("/admin/panel")
                .with(httpBasic("user", "demo-password")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin/panel")
                .with(httpBasic("admin", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-panel:admin"));
    }

    @Test
    void webFallbackAllowsPublicAndRedirectsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("web-public"));

        mvc.perform(get("/web/private"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void webFallbackUsesFormLoginAndSession() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("user").password("demo-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/web/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("web-private:user"));
    }
}
~~~

These are HTTP tests going through Spring MVC and the Spring Security filter chain, not direct controller calls. Key cases:

| Test | Request | Chain That Must Be Selected | Result |
| --- | --- | --- | --- |
| API public | GET `/api/public` without credentials | API | 200, `api-public` |
| API private anonymous | GET `/api/data` | API | 401 (Basic challenge) |
| API private user | GET `/api/data` with Basic user | API | 200, `api-data:user` |
| Admin with USER | GET `/admin/panel` with Basic user | Admin | 403 |
| Admin with ADMIN | GET `/admin/panel` with Basic admin | Admin | 200, `admin-panel:admin` |
| Web public | GET `/public` | Web fallback | 200, `web-public` |
| Web anonymous | GET `/web/private` | Web fallback | 3xx login redirect |
| Web form login | POST `/login`, then GET `/web/private` with session | Web fallback | 3xx then 200, `web-private:user` |

Because Spring Security Test's `formLogin()` simulates the relevant parameters and CSRF token, you do not need to disable CSRF to test login. HTTP Basic requests in the example are GETs and do not modify state.

**Why is this proof of chain selection?** The same `user` can access `/api/data` with HTTP Basic yet is denied admin access on `/admin/panel`, while `/web/private` uses form login and sessions. If the catch-all chain had the wrong order, or the API chain failed to match, these behaviors would change (notably 401 turning into a login redirect).

### 7.7. Build and Manual Verification

In the project directory:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Once the app runs at `http://localhost:8080`, open another terminal to test **using local dummy accounts only**:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/data
curl -i -u user:demo-password http://localhost:8080/api/data
curl -i -u user:demo-password http://localhost:8080/admin/panel
curl -i -u admin:demo-password http://localhost:8080/admin/panel
curl -i http://localhost:8080/public
curl -i http://localhost:8080/web/private
~~~

Expected responses:

~~~text
GET /api/public                 -> 200
GET /api/data (anonymous)       -> 401
GET /api/data (Basic USER)      -> 200
GET /admin/panel (Basic USER)   -> 403
GET /admin/panel (Basic ADMIN)  -> 200
GET /public                     -> 200
GET /web/private (anonymous)    -> 302 redirect to login
~~~

These are the designed outcomes of SecurityFilterChain and the controller; statuses/challenges/redirects may be affected by proxies, custom entry points, or other filters. **Never** use real passwords in `curl -u` commands because shell history or process inspection can expose credentials.

When visiting `/web/private` in a browser, you arrive at the default login page. After signing in with `user`/`demo-password`, Spring Security manages the session for the web fallback per the form-login flow.

## 8. First-Match vs. "Policy Merging"

Consider two chains:

~~~text
Chain A: /api/**    -> HTTP Basic, authenticated()
Chain B: /**        -> formLogin, role ADMIN for /api/admin/**
~~~

A request to `/api/admin/report` matches Chain A first. **Chain B's ADMIN role rule never executes** because Chain B is never selected for that request. This is a common misconfiguration: a developer thinks they can put general rules in a catch-all and specific rules in a dedicated chain and have both apply.

Remediation rules:

- Every mandatory authorization rule for `/api/**` must live inside the API chain (or in an independent layer guaranteed to run, such as method security).
- Never rely on a later chain to "layer on" CSRF, security headers, session policy, or permissions for an earlier chain.
- If the same policy must apply across multiple chains, extract a shared component/config **and apply it explicitly to each `HttpSecurity`**.
- When multiple chains are not truly necessary, prefer **one SecurityFilterChain with URL-based `requestMatchers`** to avoid overlapping-config risks. Create multiple chains when **the filter set itself or authentication mechanism** needs to differ.

### Fallback Rule: Making "Unmatched" Requests Intentional

A dangerous configuration:

~~~java
@Bean
@Order(1)
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

If this is the sole chain bean, `/admin/**` and `/web/**` are unprotected by Spring Security. You might assume Spring Boot "automatically adds a default chain" behind it; however, once you supply your own `SecurityFilterChain` configuration, auto-configuration normally **backs off** and does not add another fallback chain.

A common safe fallback:

~~~java
@Bean
@Order(99)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        // No securityMatcher -> matches all remaining requests.
        .authorizeHttpRequests(a -> a.anyRequest().denyAll())
        .build();
}
~~~

This snippet demonstrates a **deny-all fallback**, not a default replacement for web form login. It is useful when an app should expose only specific routes; requests outside the allowed list are denied instead of silently bypassing all Spring Security filters. Depending on design, you can also use an `authenticated()` + formLogin fallback as in Section 7.

**Testing negative paths** is critical: `/health`, `/error`, `/admin`, `/api` (without trailing `/`), `/api/`, duplicate/encoded paths, and reverse-proxy rewritten URLs. Never test only `/api/users` and assume `/api/**` covers every variant.

## 9. Filter-Generated Endpoints Must Also Belong to the Right Chain

A chain does not only select which controllers are protected; it also determines **which authentication filters are invoked**. Some endpoints are handled by filters without needing your own controller:

- `POST /login` when using default form login.
- `GET /login` when a filter generates the default login page (if no custom page exists).
- Logout endpoints depending on `LogoutFilter`.
- OAuth2 authorization/callback endpoints or SAML2 login endpoints depending on mechanism and configuration.

A problem arises when you narrow the web chain:

~~~java
http.securityMatcher("/web/**")
    .formLogin(Customizer.withDefaults());
~~~

If the login page and POST processing URL remain at `/login` **outside `/web/**`**, `/login` requests never enter that chain; the filter rendering/processing login will not run. Users may hit **404** despite `formLogin` being enabled, or another chain may unexpectedly handle that URL.

Three deliberate solutions:

1. Use a fallback web chain that matches `/login`, as in the complete example.
2. Configure both the login page and processing URL under the namespace matched by the chain, and test both GET and POST.
3. Use a composite `RequestMatcher` for the chain so it includes auxiliary authentication endpoints if truly needed.

Custom URL fragment example:

~~~java
http
    .securityMatcher("/web/**")
    .formLogin(form -> form
        .loginPage("/web/login")
        .loginProcessingUrl("/web/login")
        .permitAll()
    );
~~~

With this fragment, you **must provide your own GET /web/login page** (and an appropriate CSRF token on the form), instead of relying on Spring Security's default generated login page once `loginPage` is specified. Ensure routing covers all necessary URLs and HTTP methods so GET does not hit one chain while POST hits another.

**For OAuth2/OIDC:** callbacks like `/login/oauth2/code/*` must also enter the chain containing the OAuth2 login filter; login/callback/authorization redirect URLs must align with path matching and reverse-proxy base paths.

## 10. permitAll vs. web.ignoring(): Similar Surface, Different Security Layer

Two designs may both serve public content, yet are not equivalent:

~~~java
// Public endpoints that STILL run inside SecurityFilterChain.
http.authorizeHttpRequests(a -> a
    .requestMatchers("/public", "/assets/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Compared with:

~~~java
// Fragment: WebSecurityCustomizer; intentionally bypasses Spring Security filters.
@Bean
WebSecurityCustomizer ignoringStaticFiles() {
    return web -> web.ignoring().requestMatchers("/assets/**");
}
~~~

Differences:

| Behavior | `permitAll()` | `web.ignoring()` |
| --- | --- | --- |
| Does request pass through Spring Security chain? | Yes | Skips ignored security filters |
| Specific URL authorization rule | Permits | Not evaluated because skipped |
| Security headers and filter-level protections | Can still apply | May be skipped |
| Csrf/security context/other filters | Still participate per chain | Skipped accordingly |
| When to use | Public URLs inside a protected app | Only deliberately, understanding consequences |

Spring Security documentation generally recommends `permitAll` for public static resources rather than bypassing the entire filter chain, especially to preserve security headers. Modern versions optimize session handling for `permitAll`, so do not assume "permitAll is expensive because it always queries the session".

A `web.ignoring()` configuration is not just another authorization `requestMatchers`; it changes whether Spring Security processes the request at all. Audit it as a security decision.

## 11. What Else Does FilterChainProxy Do Beyond Selecting a Chain?

Per the official documentation, `FilterChainProxy` is the central entry point for Servlet security and also handles responsibilities such as:

1. **Applying `HttpFirewall`** to protect and standardize how request paths are viewed.
2. **Orchestrating the exact order of security filters** in the matched chain.
3. **Clearing `SecurityContext`** after the request per lifecycle, preventing identity leakage when Servlet threads are reused.
4. Supporting matchers based on attributes of `HttpServletRequest`.
5. Serving as a key debugging point to observe which chain/filters are invoked.

Bypassing `FilterChainProxy` and registering individual security filters as standalone Servlet filters loses these benefits—especially path/firewall control and security ordering. When writing a custom business filter, decide explicitly whether it belongs in the Spring Security chain or as a standalone Servlet filter.

### Filters Inside a Chain Have Their Own Order

A `SecurityFilterChain` may include filters for CSRF, SecurityContext, authentication, exception translation, authorization, and more. Their order **matters**: for instance, authentication normally must run before identity-based authorization decisions.

You can insert a custom filter:

~~~java
// Fragment when customFilter is an appropriate Servlet Filter, designed
// and tested to avoid duplicate execution.
http.addFilterBefore(customFilter, AuthorizationFilter.class);
~~~

Never order filters by calling `chain.doFilter` from a controller. `HttpSecurity` provides `addFilterBefore`, `addFilterAfter`, and `addFilterAt` anchored on filter classes.

**Double registration risk:** if a custom `Filter` is a `@Component`, Spring Boot may auto-register it with the Servlet container **outside** Spring Security. If you also add that filter to `HttpSecurity`, it can run twice or in an unintended position. Manage registration explicitly (e.g., a disabled `FilterRegistrationBean` when needed) and test with real requests.

Do not slap `@Order` on a filter to "force it after UsernamePasswordAuthenticationFilter" in the Spring Security chain; filter ordering **inside a chain** is controlled via the `HttpSecurity` API.

## 12. What Do 401, 403, 302, and 404 Reveal About the Selected Chain?

HTTP responses **hint** at the chain, yet are not absolute proof on their own.

| Outcome | Possible Cause | Do Not Immediately Assume |
| --- | --- | --- |
| `401 Unauthorized` | Basic/Bearer entry point requiring valid credentials | Request entered the web form chain |
| `403 Forbidden` | Missing role, bad CSRF token, AccessDeniedHandler | Password was definitely wrong |
| `302 Found` to login | Form-login entry point prompting user sign-in | Controller executed |
| `404 Not Found` | URL has no handler, or filter-provided endpoint missing from matched chain | Spring Security definitely blocked it |
| `200 OK` | Request permitted, or no security chain protects it | Authenticated and authorized properly |

For example, `/api/data` returning `302 /login` instead of 401 can signal that the request fell into the web form-login fallback, or that the API chain has a misconfigured entry point. Inspect **matchers, chain order, security filter logs**, and test the exact request.

**A single test asserting "GET /public returns 200" is not enough.** A public endpoint returns 200 even with no filter chain. You need negative tests proving private requests are blocked when anonymous and testing first-match behavior.

## 13. Multiple URL Routing Layers: contextPath, servletPath, and Reverse Proxies

Consider an app running behind a reverse proxy:

~~~text
Client:  https://example.com/service/api/orders
Proxy:   /service/api/orders -> /api/orders
App:     separately configured context path or servlet path
~~~

Spring Security matches requests **based on the request the Servlet stack actually receives**, via its matcher implementation and firewall, not necessarily the full browser address bar URL. Verify:

- `server.servlet.context-path` and how the matcher treats context path.
- Servlet mappings when multiple `DispatcherServlet` instances exist.
- Proxy path stripping, forwarded headers, and reverse-proxy trust configuration.
- Encoded slashes, semicolons, query strings, and normalization.
- Whether `/api` and `/api/` fall within the intended matcher scope.
- Whether URLs can undergo `FORWARD`, `ERROR`, or `ASYNC` dispatches.

**Do not guess and strip context-path prefixes manually** from patterns; test directly in an environment with the proxy or build tests mirroring exact container path mappings. A `securityMatcher("/api/**")` rule is only effective if the path observed by the matcher covers the scope you intend to protect.

### HTTP Method Can Also Be a Chain Boundary

Some systems need separate chains for `GET /api/**` and `POST /api/**`. A custom `RequestMatcher` can check the method, but if you do so you must ensure **all remaining methods** have a protective fallback. Methods like `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`, and `TRACE` must not silently slip past because the author only thought of GET/POST.

Usually, if methods differ only in access rules while sharing the same filter set, using `authorizeHttpRequests().requestMatchers(HttpMethod.GET,...)` inside **one chain** is simpler and safer than splitting into multiple chains.

### CORS Preflight Is Not a Failed Login

Browsers can send `OPTIONS /api/data` with CORS headers and **no credentials** prior to the actual request. If a security chain treats OPTIONS like a normal unauthenticated login attempt and rejects it, the frontend reports a CORS error rather than a clear diagnosis. CORS configuration should integrate with Spring Security using trusted origins and endpoint-appropriate policies. **Do not solve it by letting all `OPTIONS /**` bypass every security filter** unless that is a carefully evaluated decision.

## 14. DispatcherType: One URL Can Traverse Multiple Dispatches

Servlets support dispatcher types such as `REQUEST`, `FORWARD`, `ERROR`, and `ASYNC`. When the container dispatches to `/error`, a security filter chain may participate depending on registration and security config.

Common issues:

- `/error` gets blocked, masking the original API error.
- Custom filters with side effects run repeatedly on `FORWARD` or `ERROR`.
- `SecurityContext` gets cleared/restored at different dispatch stages.
- A rule applies to the initial request yet is skipped on an internal forward to a sensitive area.
- Returning 401/403 after an error dispatch instead of the intended error response.

When policies depend on dispatcher type, Spring Security provides corresponding matchers, but you must understand Servlet container filter registrations and avoid letting forwards bypass authorization. `permitAll` on a dispatcher type is a scoped decision, not a promise that the target controller is safe.

Do not manually declare `springSecurityFilterChain` multiple times across dispatcher types without verifying the effects. Spring Boot/Spring Security have default integration mechanisms; override only with sound reasons and real tests.

## 15. Observing Exactly Which Chain Is Selected

In dev/test environments, you can increase logging:

~~~properties
logging.level.org.springframework.security=TRACE
~~~

Or use DEBUG for a narrower scope:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
~~~

This helps inspect which security filters a request passes through. Exact log wording changes across versions; never write production tests asserting exact log text.

Debugging techniques:

1. Inspect the list of `SecurityFilterChain` beans created at startup and their order.
2. Set breakpoints in `FilterChainProxy.doFilterInternal` or `getFilters` selection logic when debugging.
3. Check `matches(HttpServletRequest)` on each chain after firewall/mapping processing.
4. Check which authentication filter is present in the chain: Basic, UsernamePassword, Bearer, etc.
5. Check `AuthorizationFilter`/entry point/AccessDeniedHandler and rules in the matched chain.
6. Use `MockMvc` to test both expected allow and expected deny per namespace.
7. Verify `springSecurityFilterChain` is registered in the Servlet container, not disabled or misconfigured on dispatcher types.

If you use Actuator or HTTP logging, **never log raw Authorization headers, cookies, session IDs, passwords, JWTs, or full Authentication objects**. For tracing, use correlation IDs and sanitized route/chain info.

### FilterChainProxy Introspection in Tests

You can inject the `FilterChainProxy` bean and inspect its chains:

~~~java
// JUnit/Spring test fragment, not standalone Java.
@Autowired
FilterChainProxy springSecurityFilterChain;

@Test
void expectedNumberOfSecurityChains() {
    assertEquals(3, springSecurityFilterChain.getFilterChains().size());
}
~~~

This checks the **number of chains in the demo setup**, without proving matchers are correct; other integrations/extensions can add chains. Requires importing `org.springframework.security.web.FilterChainProxy` and JUnit assertions.

Stronger tests send real requests through `MockMvc` as in Section 7, or build a `MockHttpServletRequest` with accurate servletPath/contextPath to test `SecurityFilterChain.matches(request)` per case. Never mock only `getRequestURI` while forgetting `getServletPath` and then conclude a matcher is broken.

## 16. Plain Java 17: Simulating First-Match Without Spring

To cement the mechanism, here is a **dependency-free** Java 17 program. It simulates matcher evaluation order only; it is **not** a `FilterChainProxy` replacement for Spring Security.

Create `ChainSelectionModel.java`:

~~~java
import java.util.List;
import java.util.function.Predicate;

public final class ChainSelectionModel {

    record Chain(String name, Predicate<String> matches) {}

    static String select(List<Chain> ordered, String requestPath) {
        for (Chain chain : ordered) {
            if (chain.matches().test(requestPath)) {
                return chain.name();
            }
        }
        return "NONE";
    }

    public static void main(String[] args) {
        List<Chain> chains = List.of(
            new Chain("API", path -> path.startsWith("/api/")),
            new Chain("ADMIN", path -> path.startsWith("/admin/")),
            new Chain("WEB", path -> true)
        );

        for (String path : List.of(
                "/api/data", "/admin/panel", "/web/private")) {
            System.out.println(path + " -> " + select(chains, path));
        }

        // Put fallback first: every request gets captured by it first.
        List<Chain> wrongOrder = List.of(
            new Chain("WEB", path -> true),
            new Chain("API", path -> path.startsWith("/api/"))
        );
        System.out.println("wrong-order -> "
                + select(wrongOrder, "/api/data"));
    }
}
~~~

Run with JDK 17:

~~~bash
javac ChainSelectionModel.java
java ChainSelectionModel
~~~

Stdout:

~~~text
/api/data -> API
/admin/panel -> ADMIN
/web/private -> WEB
wrong-order -> WEB
~~~

What this program shows: **with the exact same list of matchers, simply changing order changes which chain is selected**. However, never use `String.startsWith` to write a production `RequestMatcher` instead of Spring Security's firewall-backed path matching; this is only a mental model.

## 17. Configuration and Testing Matrix You Should Have

For a multi-chain project, build a table covering every important namespace:

| Request | Intended Chain | Auth Mechanism | What to Assert |
| --- | --- | --- | --- |
| `GET /api/public` | API | Public inside API chain | 200 and appropriate security headers |
| `GET /api/data` anonymous | API | Basic | 401, not a form redirect |
| `GET /api/data` with USER | API | Basic | 200 with expected principal |
| `GET /admin/panel` with USER | Admin | Basic | 403 |
| `GET /admin/panel` with ADMIN | Admin | Basic | 200 |
| `GET /public` anonymous | Web | Permit all | 200 |
| `GET /web/private` anonymous | Web | Form | Redirect to login |
| `POST /login` with valid CSRF/login | Web | Form | Creates valid login/session |
| `GET /web/private` after form login | Web | Session | 200, right username |
| `GET /unknown` | Web fallback | Authenticated | Must not bypass |
| `GET /api` without trailing slash | Explicitly defined | Per design | No edge-path bypass |
| `GET /admin` without trailing slash | Explicitly defined | Per design | No admin bypass |
| `OPTIONS /api/data` preflight | API/CORS per design | CORS | No failure from unexpected chain |
| Encoded/double-slash URLs | Firewall + matcher | Per policy | No path-interpretation bypass |
| `/error` ERROR dispatch | Per security config | Error handling | No data leak and no masked cause |
| URL after reverse proxy rewrite | Chain matching real path | Per endpoint | Does not fall into wrong fallback |
| Custom filter | Intended chain only | Dedicated policy | Does not run twice |
| No chain matches in test config | NONE | No Spring Security filter | Test flags unprotected gap |

**Do not run "self-healing" experiments by deleting the fallback in production**. Use test environments and matrix tests to detect unprotected regions.

### Should Role Rules Be Merged into One Chain?

If the only difference is:

~~~text
/api/report -> hasAuthority("REPORT_READ")
/api/admin  -> hasRole("ADMIN")
/api/data   -> authenticated()
~~~

and all three share the same Bearer mechanism, session policy, and CSRF/CORS config, then **one chain** with multiple `requestMatchers` is simpler and safer. Use multiple `SecurityFilterChain` beans when you need distinct filter sets (e.g., Basic for machines, form login for web, OAuth2 resource server for APIs).

## 18. Common Mistakes to Catch Yourself On

1. **"SecurityFilterChain is a servlet FilterChain."** No; `FilterChainProxy` uses it to choose a list of security filters.
2. **"DelegatingFilterProxy decides API vs Web."** It bridges to the `FilterChainProxy` bean; the proxy selects the chain.
3. **"FilterChainProxy picks the longest matching pattern."** No; it uses first-match in configured order.
4. **"If two chains match, both run."** No; only the first chain runs.
5. **"If API returns 403, FilterChainProxy falls back to Web."** No; permission errors stay inside the selected chain.
6. **"`requestMatchers` decides which chain runs."** No: it defines authorization rules **inside the chain**.
7. **"`anyRequest()` in the API chain protects every app URL."** No; only requests that matched the API chain.
8. **"A chain without `securityMatcher` is ignored."** On the contrary, it defaults to match-all and can swallow requests.
9. **"`@Order(99)` runs before `@Order(1)` because the number is bigger."** Wrong; lower numbers have higher priority.
10. **"Declaring `apiSecurity` before `webSecurity` guarantees order."** Do not rely on source order; use `@Order`.
11. **"No fallback is needed because Boot always adds a default chain."** No; custom chains normally make Boot's default back off.
12. **"PermitAll is the same as having no security chain."** No; permitAll still passes through Spring Security.
13. **"Static resources should always use web.ignoring()."** Not by default; you can lose security headers/protections.
14. **"Having `formLogin()` on `/web/**` means `/login` always works."** Not if login endpoints lie outside the matcher.
15. **"Every 404 on `/login` means a missing controller."** The login page/filter might simply not be in the matched chain.
16. **"`SessionCreationPolicy.STATELESS` enables JWT validation automatically."** No; you still need the corresponding filter/decoder and config.
17. **"HTTP Basic wrong password should return 403."** Usually 401; 403 is typically insufficient authority/CSRF.
18. **"A `@Component` custom Filter only runs inside HttpSecurity."** Boot may additionally register it at the container level.
19. **"Putting `@Order` on a custom filter changes its Spring Security filter order."** No; those are two separate ordering layers.
20. **"`HttpFirewall` is just an optimization with no security impact."** It protects path matching against abnormal inputs.
21. **"Encoded paths, contextPath, and reverse-proxy rewrites do not need testing."** They can break chain selection.
22. **"`/api` and `/api/**` are guaranteed equivalent on every matcher."** Never assume that.
23. **"OPTIONS preflight always carries an Authorization header."** No; browsers send preflights without credentials.
24. **"A 200 response proves authentication/authorization succeeded."** No; the request might not have entered any security chain.
25. **"Having a role check for `/admin` in the fallback is enough even if API matches first."** No; first-match stops before the fallback.
26. **"Spring Security only checks URLs, not methods or headers."** `RequestMatcher` can inspect any request attributes.
27. **"TRACE logging can stay on permanently in production to inspect chains."** Never; lower log levels and redact secrets.
28. **"A Spring MVC SecurityFilterChain can be copied straight to WebFlux."** No; different stack and filter APIs.
29. **"Clearing `SecurityContextHolder` in a controller logs out every session."** No; handle sessions/tokens explicitly.
30. **"Role ADMIN on a chain protects multi-tenant data automatically."** No; owner/tenant/resource-level authorization is still required.

## 19. Self-Check Questions

**Question 1.** Why can an app have multiple `SecurityFilterChain` beans yet the container only sees one Spring Security proxy filter?

*Answer:* `DelegatingFilterProxy` connects the container to the `FilterChainProxy` bean; the proxy holds multiple `SecurityFilterChain` configs and selects the filter list per request.

**Question 2.** If `/api/orders` matches both `/api/**` and `/**`, which chain runs?

*Answer:* Whichever chain appears **first** in the list evaluated by `FilterChainProxy`. With API `@Order(1)` and fallback `@Order(3)`, only the API chain runs.

**Question 3.** Once the API chain is selected, does `AuthorizationFilter` from the web fallback chain still run?

*Answer:* No. Only filters belonging to the selected chain execute under the proxy's orchestration. Required protections must be inside the API chain or another guaranteed layer.

**Question 4.** How does `securityMatcher("/api/**")` differ from `requestMatchers("/api/public").permitAll()`?

*Answer:* `securityMatcher` selects the **chain**; `requestMatchers` inside `authorizeHttpRequests` selects the **authorization rule** after the chain is chosen.

**Question 5.** If only a `securityMatcher("/api/**")` chain exists, what happens to `GET /admin/panel`?

*Answer:* No Spring Security chain matches, so the request may proceed unprotected by Spring Security. A fallback or another chain covering `/admin/**` is needed.

**Question 6.** Is `/**` at `@Order(1)` and `/api/**` at `@Order(2)` fine?

*Answer:* No if you want a distinct API policy: the catch-all matches first and swallows API requests. Put specific chains before the fallback.

**Question 7.** Why can enabling `formLogin` in a chain matching only `/web/**` break `POST /login`?

*Answer:* The login-processing URL lies outside the chain's scope, so the login-handling filter never runs. Include the login URL in the matcher or move login endpoints into the matched namespace.

**Question 8.** Does `permitAll` turn off CSRF, security headers, and all Spring Security filters?

*Answer:* No. It is an authorization allowance while other filters in the selected chain continue operating.

**Question 9.** Why should you avoid registering a custom Filter as both `@Component` and `addFilterBefore`?

*Answer:* It can be registered by the container outside Spring Security while also running inside the chain, causing duplicate runs or wrong ordering.

**Question 10.** Does a `403` on an API prove which chain ran?

*Answer:* Not conclusively. It could be authorization or CSRF. Inspect matchers, logs, config, and request-specific integration tests.

**Question 11.** What role does `FilterChainProxy` play regarding path firewalls?

*Answer:* It applies `HttpFirewall` to validate/wrap requests before matching and security filters, reducing inconsistent URL interpretation risks.

**Question 12.** When should you use one chain with multiple authorization rules instead of multiple chains?

*Answer:* When endpoints share the same security filters, authentication mechanism, and session policy, differing only by URL role/permission rules; one chain is easier to reason about.

**Question 13.** If an API request has valid Basic credentials but lacks `ROLE_ADMIN`, does the proxy switch to another chain to "find more permissions"?

*Answer:* No. Authorization failures inside the selected chain are handled there (typically 403); the proxy does not try subsequent chains.

**Question 14.** Why is testing `/api/public=200` insufficient to prove the configuration works?

*Answer:* A public endpoint can return 200 even if omitted from Spring Security filters altogether. You must test that anonymous `/api/data` returns 401 and verify the active rules/chains.

## 20. Pre-Deployment Checklist

- [ ] Confirmed the application uses Spring MVC/Servlet and uses `FilterChainProxy`/`SecurityFilterChain` rather than confusing with WebFlux.
- [ ] Only one `DelegatingFilterProxy` registration represents `springSecurityFilterChain`, with no extra proxies added.
- [ ] Each `SecurityFilterChain` has a clear matcher scope; specific chains are evaluated before catch-all chains.
- [ ] `@Order` is specified explicitly, avoiding reliance on method order or ambiguous equal priorities.
- [ ] Understand that `securityMatcher` selects the chain while `requestMatchers` selects authorization rules inside the chain.
- [ ] A clear fallback protects non-API/non-admin URLs; no requests are accidentally left outside Spring Security.
- [ ] Tested `/api`, `/api/`, `/admin`, `/admin/`, and boundary pattern URLs.
- [ ] Form login, logout, OAuth2 callbacks, and filter-provided endpoints belong to a chain that includes the corresponding filters.
- [ ] Critical security rules **reside in the chain that actually matches**, rather than relying on a later chain.
- [ ] Negative tests exist for 401/403, not just 200 on public endpoints.
- [ ] Tests exist for Basic/Bearer/form entry points to catch APIs unexpectedly returning login redirects.
- [ ] CSRF is not disabled wholesale simply because a chain serves APIs; browser credentials and unsafe methods are evaluated.
- [ ] CORS preflight/OPTIONS is handled properly without unintentionally bypassing all security filters.
- [ ] `HttpFirewall` and path matching are not relaxed carelessly; encoded/traversal paths and reverse-proxy routing are tested.
- [ ] Any custom filter is verified to register only once and in the right order within the chain.
- [ ] Session policy per chain is explicit; stateless APIs do not inadvertently inherit web sessions.
- [ ] Authorization also checks owner/tenant/resource-level permissions; coarse roles alone do not authorize every record.
- [ ] ERROR/FORWARD/ASYNC dispatcher types have explicit policies and do not leak context.
- [ ] Debugging observability/logs exist without recording cookies, session IDs, passwords, bearer tokens, or full Authentication objects.
- [ ] Whenever new chains are added, re-run the full route and edge-case test matrix.
- [ ] Verified against the documentation for the exact Spring Security and Spring Boot versions deployed.

### Summary

**`FilterChainProxy` does not ask "what permissions does this request have?" first; it asks "which `SecurityFilterChain` does this request belong to?"** Once the first matching chain is found, only that chain's filters execute to perform authentication, exploit protection, and configured authorization. **`securityMatcher` defines the chain scope; `requestMatchers` inside `authorizeHttpRequests` defines permission rules.**

The right mindset is to design a clear priority order, place specialized chains first, provide a protective fallback, keep login/callback endpoints inside the matching chain, and test both allowed and denied paths. Never assume chains merge or that Spring Security automatically protects routes claimed by no matcher.

### References

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Java Configuration, Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — FilterChainProxy API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html)
- [Spring Security — SecurityFilterChain API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/SecurityFilterChain.html)
- [Spring Security — DefaultSecurityFilterChain API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/DefaultSecurityFilterChain.html)
- [Spring Security — RequestMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/util/matcher/RequestMatcher.html)
- [Spring Security — HttpFirewall API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/HttpFirewall.html)
- [Spring Security — StrictHttpFirewall API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/StrictHttpFirewall.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Adding Custom Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-security-filters)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Boot 4.1.2 Release Note](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/)
