# First-Match-Wins Principle for Selecting a Chain in Spring Security Servlet

This lesson belongs to the **Filter Architecture** topic of Spring Security on Servlet. The goal is to understand how <code>FilterChainProxy</code> decides which <code>SecurityFilterChain</code> handles an HTTP request, why chain ordering matters, and how to test to avoid leaving endpoints unprotected. Examples use Java 17+, Spring Boot 3.3.x, and Spring Security 6.x.

## 1. How does a request flow through FilterChainProxy?

A Servlet application normally has a chain of Servlet Filters managed by the container. Spring Security registers a <code>DelegatingFilterProxy</code> pointing to a bean named <code>springSecurityFilterChain</code>. This bean is typically <code>FilterChainProxy</code> and holds the list of <code>SecurityFilterChain</code>s created by the security configuration.

~~~text
Client sends HTTP request
        |
Servlet container filter chain
        |
DelegatingFilterProxy -> "springSecurityFilterChain" bean
        |
   FilterChainProxy
        |
        +-- Chain A: matcher /api/admin/**  (@Order(1))
        +-- Chain B: matcher /api/**        (@Order(2))
        +-- Chain C: matcher any request    (@Order(3))
        |
        v
 Only security filters of the FIRST MATCHING CHAIN
        |
 DispatcherServlet / Controller
~~~

Each <code>SecurityFilterChain</code> consists of **a RequestMatcher** that decides whether the request belongs to this chain and **a list of Security Filters** that run when that chain is selected. For example, an API chain uses HTTP Basic, while a web page chain uses form login. They can have different filter sets and processing policies.

Three easily confused concepts:
- **Servlet container filter chain** is the Servlet-level filter pipeline; it may contain filters not belonging to Spring Security.
- **FilterChainProxy** selects one SecurityFilterChain based on matchers and configured order.
- The selected **SecurityFilterChain** supplies the security filters for that request.

Ordering **among multiple SecurityFilterChains** is not the ordering of **filters inside one SecurityFilterChain**. <code>@Order</code> on the chain bean solves the first problem; Spring Security's internal filter ordering and APIs like <code>addFilterBefore</code> solve the second.

## 2. The first-match algorithm: only the first matching chain is selected

Suppose <code>FilterChainProxy</code> holds SecurityFilterChains in priority order.

1. Check <code>matches(request)</code> of the first chain.
2. If <code>false</code>, move to the next chain.
3. If <code>true</code>, select the **current chain immediately** and stop searching.
4. Run only the security filters of the selected chain; do not accumulate filters from other chains.

The pseudocode below illustrates the principle, not an application API or a copy of Spring Security source code:

~~~java
for (SecurityFilterChain chain : orderedChains) {
    if (chain.matches(request)) {
        runSecurityFiltersFromSelectedChain(chain, request);
        return; // Do not try the next chain.
    }
}
continueServletChainWithoutMatchingSpringSecurityChain(request);
~~~

**Three key conclusions:**

- A request may **match multiple matchers**, but only the **earliest matching chain** is selected. Spring Security does not automatically search for the longest/most specific matcher.
- If the selected chain returns 401 (unauthenticated) or 403 (insufficient permissions), <code>FilterChainProxy</code> **does not retry with a subsequent chain**. Authentication and authorization happen after chain selection.
- If **no SecurityFilterChain matches**, the request does not pass through the security filters of that list. The rest of the Servlet container chain can still run. Never assume URLs outside matchers will be blocked automatically by Spring Security.

Example list:

| Priority | Matcher | Purpose |
| --- | --- | --- |
| 1 | <code>/api/admin/**</code> | Admin APIs with specialized security mechanisms |
| 2 | <code>/api/**</code> | Other APIs |
| 3 | Any request | Web pages and remaining URLs |

<code>/api/admin/reports</code> matches all three but selects chain 1. <code>/api/orders</code> does not match chain 1 and selects chain 2. <code>/account</code> selects chain 3. If chain 3 were placed first using an any-request matcher, chains 1 and 2 would practically never be selected.

## 3. Distinguishing securityMatcher from requestMatchers in authorizeHttpRequests

This is the most common source of confusion when configuring multiple chains.

| Configuration | Operating scope | Meaning |
| --- | --- | --- |
| <code>http.securityMatcher("/api/**")</code> | **SecurityFilterChain selection level** | Only requests matching <code>/api/**</code> can select this chain. |
| <code>http.securityMatchers(...)</code> | **SecurityFilterChain selection level** | Configures additional matchers scoped to the entire chain. |
| <code>authorizeHttpRequests(a -> a.requestMatchers(...))</code> | **Inside the selected chain** | Defines permissions for URLs/request conditions belonging to the chain. |
| <code>authorizeHttpRequests(a -> a.anyRequest()...)</code> | **Inside the selected chain** | Catch-all authorization rule within the chain; does not expand the chain's matcher to the whole app. |

Two layers apply first-match at two different points:

~~~text
Layer 1: select SecurityFilterChain
    @Order(1) matcher /api/** ?       YES -> select API chain
    @Order(2) matcher any request ?   NOT EVALUATED

Layer 2: inside the selected API chain
    requestMatchers("/api/public") ?      NO
    requestMatchers("/api/admin/**") ?    YES -> require ADMIN role
    anyRequest().authenticated()          NOT EVALUATED
~~~

At layer 2, the order of rules in <code>authorizeHttpRequests</code> also matters: the first matching rule decides the authorization requirement. For example, <code>requestMatchers("/api/admin/**").hasRole("ADMIN")</code> should precede <code>anyRequest().authenticated()</code> within the same chain. This is still **one** SecurityFilterChain, not two.

Consider the following snippet:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

<code>/api/public</code> still passes through the API chain's security filters, even though the authorization rule permits public access. Conversely, <code>/orders</code> is outside <code>/api/**</code>, so the API chain's <code>anyRequest().authenticated()</code> rule does not protect it at all.

## 4. @Order determines chain evaluation order

<code>@Order(1)</code> takes precedence over <code>@Order(2)</code>; smaller numbers are evaluated first. Spring Security uses the sorted list of chains and matcher results, rather than measuring URL specificity to automatically pick the best chain.

When protected areas overlap, place **narrow chains before broad chains**. Only create multiple chains when different mechanisms are needed, such as APIs using HTTP Basic/tokens and web pages using form login; if you only need different permissions per URL, a single chain with multiple <code>authorizeHttpRequests</code> rules is usually easier to manage.

If <code>HttpSecurity</code> does not declare a dedicated <code>securityMatcher</code>, the default matcher covers all requests. Therefore, such a chain should sit last in a multi-chain design to serve as a fallback. Do not rely on arbitrary ordering of multiple beans lacking explicit precedence when their matchers overlap.

## 5. Runnable Java 17+ example: HTTP Basic API and form login web pages

The demo project uses **Spring Boot 3.3.5**, Maven, and Jakarta Servlet. We create two SecurityFilterChains: a narrow API chain at the top, and a default web chain covering the rest. The accounts are solely for learning; do not use them as-is in production.

Structure:

~~~text
first-match-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/firstmatch/
    │   ├── FirstMatchApplication.java
    │   └── SecurityConfiguration.java
    └── test/java/com/example/firstmatch/
        └── SecurityChainTest.java
~~~

**<code>pom.xml</code>:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>first-match-demo</artifactId>
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

**<code>src/main/java/com/example/firstmatch/FirstMatchApplication.java</code>:**

~~~java
package com.example.firstmatch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FirstMatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(FirstMatchApplication.class, args);
    }

    @GetMapping("/api/public")
    public String apiPublic() { return "api-public"; }

    @GetMapping("/api/data")
    public String apiData() { return "api-data"; }

    @GetMapping("/api/admin/report")
    public String apiAdmin() { return "api-admin-report"; }

    @GetMapping("/public")
    public String publicPage() { return "web-public"; }

    @GetMapping("/account")
    public String account() { return "web-account"; }

    @GetMapping("/admin/report")
    public String webAdmin() { return "web-admin-report"; }
}
~~~

**<code>src/main/java/com/example/firstmatch/SecurityConfiguration.java</code>:**

~~~java
package com.example.firstmatch;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**") // Matcher for the entire API chain.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
            // Default matcher matching all remaining requests.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Explanation of key lines:

- <code>apiChain</code> has <code>@Order(1)</code> and <code>securityMatcher("/api/**")</code>: all matching API URLs enter this chain before the web chain gets a chance to evaluate.
- <code>webChain</code> has <code>@Order(2)</code> and configures no custom matcher: this is the chain covering remaining requests. The default login page <code>/login</code> also belongs to the web chain.
- The API chain uses HTTP Basic; with <code>SessionCreationPolicy.STATELESS</code>, Spring Security does not use HttpSession to store/retrieve SecurityContext for API requests. This does not prove by itself that **no** Servlet component in the application ever creates an HttpSession.
- The web chain uses form login; web admin URLs require role <code>ADMIN</code>.
- The configuration does not globally disable CSRF. The example only exercises GET requests. State-changing operations need a CSRF policy suited to each chain's authentication mechanism.

## 6. Predicting results and testing with curl

The following table shows the chain selected first, followed by the authorization rule:

| Request | Selected chain | Authorization | Expected result |
| --- | --- | --- | --- |
| <code>GET /api/public</code> | API | <code>permitAll</code> | 200, <code>api-public</code> |
| <code>GET /api/data</code> without credentials | API | Authentication required | 401, HTTP Basic challenge |
| <code>GET /api/data</code> as viewer | API | <code>authenticated</code> | 200, <code>api-data</code> |
| <code>GET /api/admin/report</code> as viewer | API | ADMIN required | 403 |
| <code>GET /api/admin/report</code> as admin | API | ADMIN required | 200, <code>api-admin-report</code> |
| <code>GET /public</code> | Web | <code>permitAll</code> | 200, <code>web-public</code> |
| <code>GET /account</code> not logged in | Web | Authentication required | 302 to login page |
| <code>GET /login</code> | Web | Default login page | 200, login form |

Run inside the directory containing <code>pom.xml</code>:

~~~bash
mvn test
mvn spring-boot:run
~~~

In a second terminal, test:

~~~bash
# Public API.
curl -i http://localhost:8080/api/public

# API requiring login: missing Basic credentials -> 401.
curl -i http://localhost:8080/api/data

# Valid viewer -> 200.
curl -i -u viewer:viewer-pass http://localhost:8080/api/data

# Viewer without ADMIN role -> 403.
curl -i -u viewer:viewer-pass http://localhost:8080/api/admin/report

# Admin -> 200.
curl -i -u admin:admin-pass http://localhost:8080/api/admin/report

# Public web -> 200.
curl -i http://localhost:8080/public

# Private web -> redirect to /login.
curl -i http://localhost:8080/account
~~~

<code>curl -i</code> displays the HTTP status and response headers. By default curl does not follow redirects without <code>-L</code>, so seeing a 302 response from the web chain is normal. The API returns 401 with HTTP Basic when credentials are missing; the web chain uses form login's login path. This difference stems from the **first matching chain**, not from running both chains.

Notably: the <code>/api/admin/report</code> request also matches the web chain's broad matcher, but when viewer gets 403 in the API chain, Spring Security **does not fall back to the web chain** to retry with form login.

## 7. Automated tests to prevent ordering bugs

Create <code>src/test/java/com/example/firstmatch/SecurityChainTest.java</code>:

~~~java
package com.example.firstmatch;

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
class SecurityChainTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiChainIsSelectedBeforeWebChain() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api-public"));

        mvc.perform(get("/api/data"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/data").with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api-data"));

        mvc.perform(get("/api/admin/report")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin/report")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api-admin-report"));
    }

    @Test
    void nonApiRequestsUseWebChain() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("web-public"));

        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Run <code>mvn test</code> to verify HTTP statuses and bodies. Tests for both API and web prove the behavior of each configured chain; as the application grows, add negative tests for URLs near matcher boundaries and critical authorization routes. The code above is written to run standalone with the stated dependencies; actual statuses also depend on additional configuration if integrated into an existing application.

## 8. Mistake number one: catch-all before a specialized chain

Consider the flawed configuration (only for analysis, do not deploy):

~~~java
@Bean
@Order(1)
SecurityFilterChain overlyBroad(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().permitAll())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain intendedApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

With <code>GET /api/secret</code>, the first chain has a default matcher matching every request, so it is selected immediately. Its <code>permitAll()</code> rule lets the request through. The trailing API chain is **never evaluated**, even though it has the <code>/api/**</code> matcher and requires authentication. This mistake can leave endpoints more weakly protected than intended.

**How to fix:** place the API chain (narrow matcher) first and the general chain last. If two distinct filter sets are not needed, replace them with a single chain having exact authorization rules.

## 9. Mistake number two: overlapping matchers with different security rules

Suppose the order is:

~~~text
@Order(1): matcher /api/**       -> any authenticated user allowed
@Order(2): matcher /api/admin/** -> ADMIN role only
~~~

Request <code>/api/admin/report</code> is picked up by chain 1 first. Chain 2 cannot add the ADMIN condition; if chain 1 permits USER, then USER gets through. Conversely, if chain 1 rejects the request with 403, chain 2 is not tried either.

There are two design approaches:

**Approach A: One chain for the entire API** if only permissions differ.

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

**Approach B: Two chains when genuinely different filter mechanisms are required**, with the narrow matcher first:

~~~text
@Order(1) /api/admin/**   -> admin SecurityFilterChain
@Order(2) /api/**         -> API SecurityFilterChain
@Order(3) all requests    -> web SecurityFilterChain
~~~

In Approach B, test both admin and regular API URLs. Spring Security does not automatically promote the <code>/api/admin/**</code> chain ahead simply because its matcher is more specific.

## 10. No chain matches: a dangerous gap

Suppose the entire application only declares:

~~~java
@Bean
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

<code>/api/orders</code> has a chain protecting it. But <code>/billing</code> does not match <code>/api/**</code>, so it does not pass through the security filters of this sole chain. <code>anyRequest().authenticated()</code> sits **inside the API chain**, so it cannot protect <code>/billing</code> by "reaching outside" its matcher.

When you define a custom <code>SecurityFilterChain</code> bean, do not assume Spring Boot will automatically insert a catch-all chain to wrap all remaining URLs. If all endpoints must be processed by Spring Security, add an appropriate final chain and define access rules for it.

This differs from a route that **has a matching chain but uses <code>permitAll()</code>**. That route still passes through the selected chain's security filters.

## 11. PermitAll, web.ignoring, and first match

These configurations differ in effect:

| Case | Do the chain's Spring Security filters run? | Meaning |
| --- | --- | --- |
| <code>requestMatchers("/public").permitAll()</code> in selected chain | Yes | Allows the request past authorization, but other filters such as security headers can still apply. |
| Ignoring configured via <code>web.ignoring()</code> | No for the ignored URL | Intentionally skips security filters in <code>FilterChainProxy</code> for that URL. |
| Request matches no chain | No | No chain is selected to execute the list's security filters. |

Normally for a public page, <code>permitAll()</code> inside an appropriate chain is a clearer choice if application-wide security mechanisms are still needed. Never put a <code>/**</code> chain with <code>permitAll()</code> first and expect an API chain below it to run.

## 12. Login paths and authentication filters must also fall within the right chain

One thing to verify when a chain has <code>securityMatcher("/api/**")</code>: that matcher also restricts **the endpoints handled by security filters**. For instance, if you configure <code>formLogin()</code> whose default login URL is <code>/login</code>, the path <code>/login</code> is not under <code>/api/**</code>. Consequently, the API chain cannot handle the login page and submission endpoint at a URL outside its scope.

In this lesson's example, the web chain covers <code>/login</code>, so <code>formLogin</code> works for the web part. If you need a separate login mechanism inside the API chain, design the URLs and the chain's matcher so every request needing filter handling falls within the appropriate scope.

A further distinction: <code>securityMatcher</code> affects **chain selection**, whereas <code>addFilterBefore</code>/<code>addFilterAfter</code> only changes filter order **within that chain itself**; it will not give priority to a shadowed chain.

## 13. Diagnosing which chain is selected in an application

When an API returns 302 instead of 401, or an endpoint unexpectedly becomes public, check in order:

1. List **all SecurityFilterChain beans and their order**; check whether any default/catch-all chain sits too early.
2. Write down the chain-level matchers: <code>securityMatcher</code>, <code>securityMatchers</code>, or default matcher. Distinguish them from <code>requestMatchers</code> at the authorization layer.
3. For each suspect request, walk matchers from highest priority down and **stop at the first matcher returning true**.
4. Only after identifying the chain, inspect the filter list and authentication/authorization rules inside the selected chain.
5. Write MockMvc/integration tests to lock down expected behavior, especially at overlapping URLs and URLs matching no chain.

In a development environment, you can temporarily enable logs:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Inspect logs while calling URLs belonging to each chain. Detailed log contents vary by version and configuration; do not depend on a fixed log string. Avoid leaving TRACE enabled in production long-term, especially when logs could contain authentication/session details.

When evaluating matchers accurately, remember matching may inspect the HTTP method and path-handling rules of the actual <code>RequestMatcher</code> type; context path, servlet path, and how MVC matchers are used can affect scope. Do not just look at endpoint names and guess matchers as plain strings.

## 14. Common mistakes

| Configuration/conceptual mistake | Consequence | Remedy |
| --- | --- | --- |
| Placing matcher <code>/**</code> before <code>/api/**</code> | API chain is shadowed | Put narrow chains first, catch-all last |
| Placing <code>/api/**</code> before <code>/api/admin/**</code> when two different filter sets are needed | Admin chain may never run | Swap order or use one chain with admin rules |
| Thinking <code>requestMatchers</code> selects SecurityFilterChain | Misunderstanding protection scope | Use <code>securityMatcher</code> at the chain layer |
| Expecting 403 to fall back to the next chain | Misjudging authorization policy | Processing stays in the first matching chain only |
| No final chain for other URLs | Some endpoints receive no Spring Security filters | Add a chain covering the remainder when needed |
| Leaving login URL outside the matcher of the chain responsible for login | Login endpoint is not handled by that filter | Redesign URL/matcher and verify with tests |
| Creating multiple chains solely for different roles | Easy to overlap and hard to maintain | Use authorize rules inside the same chain |
| Not testing paths that can match multiple matchers | Small changes can open vulnerabilities | Test narrow, broad, and out-of-scope paths |

## 15. Self-check questions

**Question 1.** Given <code>@Order(1) /api/**</code> and <code>@Order(2) /**</code>. How many SecurityFilterChains does request <code>/api/orders</code> run through?  
**Answer:** One: the <code>/api/**</code> chain, because it matches first. Filters from the general chain are not appended afterward.

**Question 2.** A request matched chain 1 but received 403. Does the framework retry chain 2?  
**Answer:** No. 403 is the processing result of the selected chain and does not trigger re-selection.

**Question 3.** Does <code>anyRequest().authenticated()</code> in a chain restricted to <code>/api/**</code> protect <code>/account</code>?  
**Answer:** No. <code>/account</code> lies outside the chain's matcher; another appropriate chain is required.

**Question 4.** Why does <code>@Order</code> matter even when a matcher is narrower?  
**Answer:** Spring Security respects the declared/sorted order of chains; it does not automatically choose the "most specific" matcher.

**Question 5.** Does a <code>permitAll()</code> URL in a selected chain completely bypass Spring Security?  
**Answer:** No. The chain's security filters still run; <code>permitAll</code> is only a decision at the authorization layer.

**Key takeaway:** <code>FilterChainProxy</code> **selects the first SecurityFilterChain whose RequestMatcher matches the request**. After that, only that chain's security filters process the request and that chain's <code>authorizeHttpRequests</code> rules decide permissions. Designing matcher order properly and testing overlapping regions is how you avoid vulnerabilities when configuring multiple chains.
