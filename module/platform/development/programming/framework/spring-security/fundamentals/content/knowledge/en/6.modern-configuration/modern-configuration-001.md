# Security Configuration with Spring Beans and Lambda DSL

> **Scope:** Spring Security for **Servlet/Spring MVC**, Java 17+, Spring Boot 3.x, and Spring Security 6.x. This lesson explains how to create modern security configurations using **Spring beans**, read **HttpSecurity** **Lambda DSL** properly, combine authentication mechanisms with authorization, separate multiple filter chains, test thoroughly, and prepare for Spring Security 7. The runnable full examples focus on an API application using HTTP Basic so learners can observe 200/401/403 results.

## 1. Why Configure with Beans and Lambda DSL?

In older Spring Security projects, you might see classes extending **WebSecurityConfigurerAdapter**, overriding **configure(HttpSecurity)**, and calling **.and()** to return to the parent builder. That approach is no longer suitable for new applications:

- **WebSecurityConfigurerAdapter** has been removed from Spring Security 6.
- Since Spring Security 5.2, the framework has supported the **Lambda DSL**. This is the preferred configuration style in the 6.x line.
- Starting in Spring Security 7, the Lambda DSL syntax becomes mandatory for configuring HTTP security; the non-lambda chaining style with **.and()** from older documentation is no longer a valid upgrade path.
- Spring Boot manages components via the **IoC container**; you declare a **@Bean SecurityFilterChain** to describe the application's HTTP protection policy.

Minimal modern pattern:

~~~java
@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is a **configuration snippet**, requiring Spring Security imports and dependencies to compile; Section 5 provides a complete application. From this pattern you already see three points:

1. **@Configuration** indicates that Spring manages the class containing bean declarations.
2. **@Bean** exposes a **SecurityFilterChain** with a specific policy.
3. **authorizeHttpRequests(authorize -> ...)** and **httpBasic(Customizer.withDefaults())** use the Lambda DSL syntax and do not require calling **.and()**.

**A SecurityFilterChain bean does not create users by itself.** The rule "every request requires authenticated" is about **authorization**, whereas the source of username/password, password hashing, or token validation is **authentication**; those are configured separately via their own beans/mechanisms.

## 2. Understanding the Role of Spring Beans

A bean is an object instantiated, lifecycle-managed, and supplied to dependent components by the **Spring ApplicationContext** through dependency injection.

For a Spring Boot/Spring Security application, relevant beans may include:

| Bean/object | Why it is needed | Where it is typically declared |
| --- | --- | --- |
| **SecurityFilterChain** | Selects filters and rules protecting HTTP requests | **@Bean** method accepting HttpSecurity |
| **PasswordEncoder** | Verifies raw password against stored hash; encodes before storing | Configuration bean or appropriate component |
| **UserDetailsService** | Loads user/authorities/flags during username/password authentication | Bean or **@Service** |
| **AuthenticationProvider** | Performs a specific type of authentication | Bean when a custom provider is needed |
| **AuthenticationManager** | Coordinates providers | Usually configured by the framework; declared explicitly when architecture requires |
| **CorsConfigurationSource** | Provides CORS policy for the security chain when needed | Separate configuration bean |
| **AuthorizationManager** | Executes authorization logic per request/method | Default API or custom bean/policy |
| **Multiple SecurityFilterChain instances** | Separates policies for API and web | Multiple beans with clear matchers and ordering |

Not every application must declare everything in the table above. **Prefer appropriate framework defaults**, and only create custom beans when you need to change behavior. Defining too many competing providers or managers can cause requests to go through a different component than expected.

### 2.1. @Configuration, @Bean, and Dependency Injection

Example:

~~~java
@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

This is a **snippet**, requiring imports and a Spring Security project. Spring injects **PasswordEncoder** into the **users(...)** method, so we do not need to create a second encoder using **new BCryptPasswordEncoder()** inside this method. **BCryptPasswordEncoder** uses salts; use **matches** to verify a raw password against a hash, rather than comparing two hash strings with equals.

You can use **@Service** so Spring automatically detects a class implementing **UserDetailsService**, instead of creating a bean in the configuration class. Choose one declaration style intentionally to avoid accidentally providing two UserDetailsService beans of the same type and making authentication wiring ambiguous.

### 2.2. Is @EnableWebSecurity Required in Spring Boot?

In a standard Spring Boot Servlet application with starter-security and normal auto-configuration, **you do not need to add @EnableWebSecurity just for a @Bean SecurityFilterChain to take effect**. Many standalone Spring Security library examples still place @EnableWebSecurity explicitly.

**@EnableMethodSecurity** is separate: when you want to use **@PreAuthorize**, **@PostAuthorize**, and other method security annotations, you must enable the corresponding mechanism. Having only a SecurityFilterChain bean does not automatically enforce method-level annotations.

### 2.3. When You Declare a SecurityFilterChain, What Does Spring Boot Still Do Automatically?

Spring Boot protects web endpoints by default when Spring Security is on the classpath. **Declaring a SecurityFilterChain bean** causes Boot's **default web security configuration to back off**; the matchers, authorization rules, and login mechanisms in the new chain are designed by you.

That **does not automatically disable the default in-memory user account bean**. Auto-configuration for **UserDetailsService** is a separate part; an appropriate **UserDetailsService**, **AuthenticationProvider**, or **AuthenticationManager** bean can cause Boot's default user source configuration to back off. When using OAuth2 modules, auto-configuration conditions may also differ; always verify the actual configuration.

If the application still prints **Using generated security password**, that does not prove your SecurityFilterChain is being ignored. It can indicate that you have only customized the **web chain** without replacing the **user source**. The complete example below intentionally declares both.

## 3. Reading the Lambda DSL Properly

The Lambda DSL has the form:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers(HttpMethod.GET, "/public").permitAll()
        .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
~~~

**Decoding the syntax:**

- **http** is **HttpSecurity**: the overall builder for servlet security.
- **authorizeHttpRequests(...)** accepts a **Customizer** (lambda) to configure the group of authorization rules.
- **authorize** is the lambda parameter provided by the framework; the variable name is only for readability and can be named **auth**, **rules**, or something else.
- **requestMatchers(...)** narrows which requests a rule evaluates by path/method.
- **permitAll**, **authenticated**, **hasRole**, and **hasAuthority** are authorization decisions within a rule.
- **Customizer.withDefaults()** is shorthand for a lambda that does not modify the default options of the enabled feature, equivalent in intent to **basic -> {}**.
- **http.build()** produces the **SecurityFilterChain** bean. Call **build()** after finishing configuration.

**There is no need to call .and()** to exit each branch. Once the lambda ends, you continue configuring on **HttpSecurity** in the outer builder chain.

### 3.1. Comparing the Old Style and Lambda DSL

**Old style, only for recognizing legacy code when reading it:**

~~~java
// Old style; should not be used for Spring Security 7.
http
    .authorizeHttpRequests()
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated()
        .and()
    .httpBasic();
~~~

**Preferred style:**

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
~~~

Both snippets express the same **policy intent** within their respective version environments. The old style is neither recommended for new code nor guaranteed to work across all versions. From 7.x onward, the Lambda DSL syntax is required.

### 3.2. Empty Lambdas vs. Configured Lambdas

To enable HTTP Basic with defaults:

~~~java
.httpBasic(Customizer.withDefaults())
~~~

To configure a login page in a web application:

~~~java
.formLogin(form -> form
    .loginPage("/login")
    .permitAll()
)
~~~

The form login snippet requires the application to have **GET /login** to render your custom page and a matching **POST /login** for the filter to process credentials; if you only change **loginPage** without providing the page, users may hit a **404**. When you want to use the login page generated by Spring Security, you can use **formLogin(Customizer.withDefaults())** and let the framework handle the defaults.

When replacing AuthenticationEntryPoint, RequestCache, login success handler, or logout URL yourself, design both browser behavior and HTTP responses; you may also need to adjust CSRF/session policies.

### 3.3. Lambdas Do Not Automatically Enforce a Secure Policy

Here is a very broad configuration:

~~~java
http.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll()
);
~~~

It lets every request in the chain pass through the authorization step, including newly added controllers. The Lambda DSL **does not guarantee least privilege by itself**: you still must carefully review public, protected, and admin endpoints, HTTP methods, and resource-level permissions.

The order of **requestMatchers** also matters: the first matching rule wins. A broad rule such as **/api/** placed before a rule requiring ADMIN on **/api/admin/** can prevent the more specific rule from ever being used.

## 4. Authentication, Authorization, and the Filter Chain Are Three Separate Parts

For an HTTP request:

~~~text
Browser / API client
       |
       v
Servlet container -> DelegatingFilterProxy
       |
       v
FilterChainProxy
       |
       +--> Select first matching SecurityFilterChain
                  |
                  +--> Context / headers / CSRF / CORS filters (as configured)
                  |
                  +--> Authentication filter (Basic, form login, bearer...)
                  |       |
                  |       +--> AuthenticationManager
                  |       +--> UserDetailsService + PasswordEncoder
                  |            or JwtDecoder, introspector...
                  |
                  +--> AuthorizationFilter
                          |
                          +--> ALLOW -> Controller / Service
                          |
                          +--> DENY -> exception translation -> HTTP response
~~~

**Authentication** verifies credentials to establish an identity. **Authorization** evaluates whether access is permitted. **SecurityFilterChain** wires together the filters that enforce those behaviors.

For example, **requestMatchers("/admin").hasRole("ADMIN")** specifies an authorization requirement. If no suitable authentication mechanism is enabled or configured, users do not automatically obtain valid credentials just because the rule mentions ADMIN. Conversely, enabling Basic while leaving **permitAll** too broad can expose resources despite having an authentication step.

### 4.1. HttpSecurity Describes Only One Chain

Each **SecurityFilterChain** bean is built from HttpSecurity; the bean is constructed at startup, not by executing **securityFilterChain(...)** on every request. When a request arrives, **FilterChainProxy** selects a chain and runs the already-built filters.

A chain can cover all URLs if no matcher restriction is set, or apply only to a specific scope via **securityMatcher**.

- **securityMatcher(...)**: selects which requests belong to the **chain**.
- **requestMatchers(...)** inside **authorizeHttpRequests(...)**: rules **within the selected chain**.
- **@Order**: order of chains when multiple beans exist.
- **anyRequest()**: applies only to remaining requests inside the current chain; it does not protect URLs outside all chains.

## 5. A Runnable Spring Boot 3 Application: Configuration with Beans and Lambda DSL

The project uses **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring Web MVC**. The example uses HTTP Basic to avoid building an HTML login page; it has two demo accounts. We declare:

1. **SecurityFilterChain** to specify URLs and HTTP methods.
2. **PasswordEncoder** using BCrypt.
3. **UserDetailsService** containing two sample users.
4. **Controller** with public, authenticated, ADMIN-only, and an intentionally unlisted endpoint outside the allowlist.
5. **MockMvc tests** to verify the full path through the filter chain.

### 5.1. Dependencies

In a Spring Boot 3.x project that already has the Gradle plugin, Java configuration, and version management, place the following block into the existing **build.gradle**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a **dependencies snippet**, not a standalone build.gradle; the Gradle Wrapper and Spring Boot plugin must already be configured. File layout:

~~~text
src/main/java/com/example/lambdasecurity/
  LambdaSecurityApplication.java
  SecurityConfig.java
  DemoController.java

src/test/java/com/example/lambdasecurity/
  LambdaSecurityTest.java
~~~

### 5.2. LambdaSecurityApplication.java

~~~java
package com.example.lambdasecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LambdaSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(LambdaSecurityApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java

~~~java
package com.example.lambdasecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
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
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/profile").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

**Reading each bean:**

- **apiSecurity(HttpSecurity http):** receives the builder provided by Spring Security; configures rules, HTTP Basic, and session policy with lambdas; returns **http.build()**.
- **passwordEncoder():** creates a Spring-managed BCrypt encoder. The hash generated each time a user is created may differ due to salting, but the correct raw password is still verified using **matches**.
- **users(PasswordEncoder encoder):** Spring injects the PasswordEncoder bean automatically; creates a **UserDetailsService** containing alice and admin. **roles("USER")** assigns authority **ROLE_USER**, and similarly ROLE_ADMIN.
- **STATELESS:** Spring Security does not rely on HttpSession to retrieve the SecurityContext on subsequent requests. It does not mean HTTP Basic is the only way to build an API, and it does not automatically disable CSRF.
- **anyRequest().denyAll():** endpoints and methods without an explicitly declared rule are denied in this chain.
- The example does not call **csrf.disable()** because the business endpoints are all GET; CSRF policy for POST/PUT/DELETE must be designed according to the client and credential transport.

**No formLogin is declared** in the chain above; when an anonymous client calls **/profile**, the Basic entry point typically responds with **401** and a challenge instead of redirecting to a browser login page.

**This configuration is for demo/localhost use:** simple passwords and in-memory storage are not suitable for production. Real systems require an identity store, secret management, and HTTPS/TLS.

### 5.4. DemoController.java

~~~java
package com.example.lambdasecurity;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "profile:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "admin";
    }

    @GetMapping("/unlisted")
    public String unlisted() {
        return "this-must-not-be-exposed";
    }
}
~~~

The **/unlisted** controller exists to demonstrate that a mapped endpoint remains inaccessible if the **SecurityFilterChain** has a deny fallback. The **/profile** controller receives an **Authentication** already verified by Spring Security; it does not parse the Basic header itself.

### 5.5. Running Manually and Observing Responses

From the project directory with the Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

From another terminal, send HTTP requests to localhost:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u alice:alice123 http://localhost:8080/profile
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/unlisted
curl -i -u alice:wrong http://localhost:8080/profile
~~~

Expected with **this exact demo application** and no reverse proxy or custom handlers:

| HTTP request | Status | Result |
| --- | --- | --- |
| GET /public, no credentials | **200** | Body **public** |
| GET /profile, no credentials | **401** | HTTP Basic challenge |
| GET /profile, alice correct password | **200** | Body **profile:alice** |
| GET /admin, alice ROLE_USER | **403** | Missing ROLE_ADMIN |
| GET /admin, admin ROLE_ADMIN | **200** | Body **admin** |
| GET /unlisted, admin | **403** | Fallback deny, controller does not run |
| GET /profile, wrong password | **401** | Authentication failed |

These are **HTTP statuses and bodies**, not stdout printed by the Java application. **curl -i** prints headers along with the body. On a 401 from HTTP Basic, the **WWW-Authenticate** header usually indicates the Basic challenge. Do not rely on the error body content because error handling configuration can change.

With HTTP Basic, the username/password string is only Base64-encoded in the header; **Base64 is not security encryption**. Only use real credentials over HTTPS and do not record passwords in shell history/logs. The passwords in the examples are learning data.

### 5.6. MockMvc Testing: Verifying Rules and Login Mechanisms

Create the file **src/test/java/com/example/lambdasecurity/LambdaSecurityTest.java**:

~~~java
package com.example.lambdasecurity;

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
class LambdaSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsPublic() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotAccessProfile() throws Exception {
        mvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadHerProfile() throws Exception {
        mvc.perform(get("/profile")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:alice"));
    }

    @Test
    void roleUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void unlistedControllerRemainsDenied() throws Exception {
        mvc.perform(get("/unlisted")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/profile")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Run tests in the project:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**httpBasic(...)** from Spring Security Test lets MockMvc construct a Basic header like a real request. The test passes through filters + provider + authorization; it **does not simply mark the user as logged in**. The 401/403 tests are especially valuable because they prove what happens when credentials or authorities are missing, rather than only checking 200 responses.

The test suite above targets **Spring Boot 3.x**. Do not copy imports verbatim when a project uses Spring Boot 4.x/Spring Security 7.x without checking dependencies and corresponding test package changes.

## 6. Splitting Configuration into Multiple Beans with Clear Responsibilities

For larger applications, you commonly separate:

- **WebSecurityConfig:** SecurityFilterChain beans and URL policies.
- **IdentityConfig/AccountConfig:** PasswordEncoder, UserDetailsService, or AuthenticationProvider.
- **CORS policy:** CorsConfigurationSource if cross-origin browser requests are actually used.
- **Service/domain policy:** services and method security annotations when needed.

Such separation lets you inspect which bean handles authentication, which handles authorization, and which handles session/CORS/CSRF. However, **it is not mandatory for each concern to live in a different class**: small demos can keep related beans in a single SecurityConfig class as in Section 5.

### 6.1. Writing a Custom UserDetailsService from a Database

Example app using JPA:

~~~java
// Snippet only: AccountEntity, AccountRepository, and imports
// must be defined in a real project.
@Service
public class AccountUserDetailsService implements UserDetailsService {

    private final AccountRepository repository;

    public AccountUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountEntity account = repository.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException(
                "Invalid credentials"
            ));

        return User.withUsername(account.getUsername())
            .password(account.getPasswordHash())
            .authorities(account.getAuthorities())
            .disabled(!account.isEnabled())
            .accountLocked(account.isLocked())
            .build();
    }
}
~~~

This is a **project-dependent snippet**, not a standalone Java file. **UserDetailsService** only loads the account; **DaoAuthenticationProvider** and **PasswordEncoder** verify credentials. In multi-tenant systems, usernames must be scoped to the right tenant to avoid colliding accounts with the same name. Passwords should be stored with an appropriate hash, never plaintext.

### 6.2. @EnableMethodSecurity and @PreAuthorize

If an operation reading data requires the **report:read** authority, you can enable method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

Then protect a Spring-managed service:

~~~java
@Service
class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "report";
    }
}
~~~

These are **two supplemental snippets**, requiring imports for **Configuration**, **EnableMethodSecurity**, **Service**, and **PreAuthorize**. When invoked through a Spring proxy with appropriate configuration, the method has its permissions checked; **self-invocation** within the same bean can bypass the proxy. **@EnableMethodSecurity does not automatically block every unannotated method**: control points must be identified by business logic and tested.

URL rules and method rules can work together. Even so, permission to read a resource type does not prove the user owns a **specific resource**; owner, tenant, and record state checks are needed when required by policy.

### 6.3. Is Declaring an AuthenticationManager Bean Necessary?

Usually **no**, you do not need to create a ProviderManager manually to use HTTP Basic with **one UserDetailsService** and **PasswordEncoder**. Spring Security has mechanisms to configure the manager/provider for common cases. When using multiple providers or needing specialized authentication flows, declare it intentionally; avoid adding an arbitrary **AuthenticationManager** just to "have all beans" and accidentally bypassing default providers.

## 7. Multiple SecurityFilterChains with @Order

An application may have both an HTTP API and a web UI with form login. In that case, create **multiple SecurityFilterChain beans**, scope them with **securityMatcher(...)**, and order them with **@Order**.

The following example is only a **snippet from a different configuration**; do not paste it verbatim into the demo SecurityConfig from Section 5:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/login").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Requires importing **Bean**, **Order**, **HttpMethod**, **HttpSecurity**, **SecurityFilterChain**, and **Customizer**. In the example:

1. Requests under **/api/** match the API chain first.
2. Remaining requests can enter the web chain, which declares no **securityMatcher** restriction.
3. **FilterChainProxy selects the first matching chain**; it does not apply all chains simultaneously to the same request.
4. Because authentication mechanisms and entry points differ, the API can return 401 Basic while a browser visiting a web route can be redirected to login.
5. When using form login, verify the login endpoint is handled by the filter chain and that a suitable CSRF token is present for POST /login.

### 7.1. Do Not Confuse the Two Types of Matchers

| API | Role | Example |
| --- | --- | --- |
| **securityMatcher("/api/**")** | Decides whether a request belongs to the **chain** | /api/orders yes; /login no |
| **requestMatchers(HttpMethod.GET, "/api/ping")** | Decides the authorization rule inside the chain | GET /api/ping permitAll |
| **anyRequest().authenticated()** | Final rule for remaining requests belonging to the chain | /api/orders requires authentication |
| **@Order(1)** | Chooses which chain has higher priority | API before web |

If you only have **securityMatcher("/api/**")** and do not create a chain covering the rest, **/internal/debug** can fall outside Spring Security. Putting **anyRequest().denyAll()** inside the API chain will also not block requests **outside the API chain**. Always provide a fallback chain and test coverage across all servlet URLs.

### 7.2. Form Login URL Must Be Within the Chain's Scope

If a chain only matches **/secured/** but form login uses the default **/login**, requests to **/login** may not be handled by that chain, causing the login endpoint to behave as missing. When using **loginPage("/secured/login")** or **loginProcessingUrl(...)**, ensure the related GET/POST requests belong to the chain and the application has a controller/view for the custom login page.

### 7.3. @Order Only Matters with Multiple Chains

If an application has only a single chain with no securityMatcher restriction, setting **@Order** is usually unnecessary. When there are multiple chains, place **more specific** matchers first and the **broadest** chain last, and test both matching requests and requests outside the matchers.

## 8. Configuring CSRF, CORS, and Session with Lambdas

The Lambda DSL is not only for authorizeHttpRequests. Other concerns also use lambdas, though you must understand their semantics before copying them.

### 8.1. Session Management

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
)
~~~

**STATELESS** tells Spring Security not to use HttpSession to obtain the SecurityContext. This is useful for APIs that authenticate credentials on every request, but it **does not enable JWT** and does not mean the entire server holds no state. If a web app uses form login + sessions, the session policy needs to be different.

### 8.2. CSRF

Servlet Spring Security enables **CSRF protection** for unsafe HTTP methods by default unless configured otherwise. A web app using session cookies should protect POST/PUT/DELETE properly with CSRF tokens; **HttpOnly cookies do not replace CSRF tokens**.

CSRF can be configured via:

~~~java
.csrf(csrf -> csrf
    // Add rules only when the threat model and client type are clear.
)
~~~

The snippet above **only illustrates the DSL extension point** and does not need to be added to an application if you just want the default. Calling **csrf -> csrf.disable()** should not be applied out of habit to every API; browsers can automatically send cookies or HTTP authentication credentials and create CSRF risk.

### 8.3. CORS

In applications with a cross-origin browser frontend, cross-origin requests carrying an Authorization header usually trigger a CORS preflight. You can enable CORS integration:

~~~java
.cors(Customizer.withDefaults())
~~~

This **does not define the allowed origins/methods/headers by itself**. You need a **CorsConfigurationSource** or suitable MVC CORS configuration, ensuring preflight requests are handled and credentialed CORS does not illegally use a wildcard origin.

**CORS is not authorization.** It controls cross-origin browser behavior; it does not validate tokens or decide whether a user has permission to read a specific document.

### 8.4. Exception Handling

An API application may want JSON responses instead of HTML pages. **AuthenticationEntryPoint** commences authentication (typically 401 Basic or login redirect), while **AccessDeniedHandler** handles an authenticated identity lacking permissions (typically 403).

This can be configured via:

~~~java
.exceptionHandling(errors -> errors
    .authenticationEntryPoint(customEntryPoint)
    .accessDeniedHandler(customDeniedHandler)
)
~~~

This is a **snippet**: you must declare/import both real handlers with concrete HTTP contracts and test responses. If overriding the HTTP Basic entry point, consider preserving the **WWW-Authenticate** header when clients rely on the Basic challenge.

### 8.5. Headers and Logout

Other configurations also use lambdas:

~~~java
.headers(headers -> headers
    .frameOptions(frame -> frame
        .sameOrigin()
    )
)
.logout(logout -> logout
    .logoutUrl("/logout")
)
~~~

This snippet only illustrates syntax; **do not open same-origin framing** unless the application genuinely requires it, since frame policies should be chosen based on clickjacking protection needs. When using logout with sessions/cookies vs. JWT, semantics differ; configuring a logout endpoint does not automatically revoke every issued token.

## 9. Modularizing the DSL: When Should You Do It?

In large projects, security policies can grow long. Three common ways to organize them are:

1. Keep the **@Bean SecurityFilterChain** method concise, calling private helper methods to configure groups of rules in the same class (if API-supported and readable).
2. Define multiple chains for **request regions with genuinely different policies**, with clear @Order and fallback.
3. On supported Spring Security versions, use **Customizer<HttpSecurity> beans** or a **custom DSL** to share common chain setup. This requires verifying the lifecycle and customizer application order on the target version; do not assume every Customizer bean is applied automatically in every version.

An advanced **custom DSL** can be applied via **http.with(...)** in Spring Security 6.2+, replacing the older **http.apply(...)** for compatibility toward Spring Security 7. Only introduce this abstraction when multiple chains truly share complex behavior; demos and small apps do not need a custom DSL.

**Do not overuse multiple @Configuration classes** if conflicting rules for the same URL become hard to spot. Establish clear policy ownership alongside tests for matchers and HTTP methods.

## 10. Testing Configuration Changes and Preventing Security Bugs

When migrating to the Lambda DSL, the goal is not only that the project **compiles** but that it **preserves the intended behavior**. An upgrade can cause a different chain to be selected, a login URL to disappear, a 401 to turn into a 302, or a new endpoint to be exposed accidentally.

A test suite should cover:

| Test case | Reason |
| --- | --- |
| Anonymous calls public GET | Proves permitAll rule is in the right place |
| Anonymous calls protected GET | Proves entry point requires authentication |
| Valid user accesses profile | Proves authentication filter/provider works |
| User without required role accesses admin | Proves authorization is distinct from authentication |
| Admin accesses admin | Proves ROLE_ADMIN authority works properly |
| Endpoint outside the allowlist | Proves fallback deny |
| Different HTTP methods on the same path | Proves method-level rules and CSRF need consideration |
| Request outside the API chain's securityMatcher | Proves fallback chain still protects |
| Form login GET/POST and CSRF | Proves login endpoint is actually handled by filters |
| OAuth2/Bearer token with wrong audience/scope (if used) | Proves token validation and permissions |

In the Section 5 demo, the MockMvc tests cover seven core HTTP scenarios. When inspecting the filter chain in detail, you can enable:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

In development environments, logs can display the filters in the chain and authorization evaluation steps. Never log raw passwords, Basic Authorization headers, bearer tokens, session cookies, or private data.

### 10.1. Debugging from the Outside In

When a response is unexpected, ask in order:

1. **Did the request actually reach the right path and HTTP method?** Is there a different context path, reverse proxy, or servlet mapping?
2. **Which chain did FilterChainProxy select?** Is a securityMatcher, @Order, or fallback chain wrong?
3. **Which requestMatchers rule matched first?** Is a broad permitAll/authenticated rule placed before hasRole?
4. **Which authentication filter is active?** Basic, form, OAuth2 Resource Server, OAuth2 Login, or a custom filter?
5. **Which identity source is used?** Generated default user, UserDetailsService, AuthenticationProvider, JwtDecoder?
6. **Do the principal and authorities match?** ROLE_ADMIN differs from ADMIN; SCOPE_read differs from read.
7. **Did CSRF/CORS/error dispatch intervene?** Distinguish authentication failures, authorization denials, and other protection mechanisms.
8. **Does the controller/service check resource-level permissions?** URL rules do not automatically check ownership of a record owned by someone else.

## 11. Common Mistakes When Moving to Spring Beans and Lambda DSL

### 11.1. Still Pulling WebSecurityConfigurerAdapter into New Projects

**WebSecurityConfigurerAdapter** no longer exists in Spring Security 6. Declare a **@Bean SecurityFilterChain** and keep authentication logic in appropriate beans/providers. Do not copy an adapter class from an old Spring Security 5 tutorial and just swap a few imports.

### 11.2. Continuing with .and() and Non-Lambda Configurer Syntax

Non-lambda calls were replaced by the Lambda DSL. This makes it clearer which object is being configured and more consistent; notably, **Spring Security 7 requires the Lambda DSL** for this style of HTTP configuration.

### 11.3. Thinking @Bean SecurityFilterChain Creates Users/Passwords

The chain bean controls **web security**, not always the **authentication provider**. Check UserDetailsService/Provider/Manager and Spring Boot auto-configuration. If a generated password still appears, verify which beans are actually registered.

### 11.4. Setting anyRequest().permitAll() Too Broadly

An open catch-all rule can expose new endpoints. Use a path/method allowlist with a deny fallback where appropriate. Do not open the entire application just because the login page or CSS is returning 401.

### 11.5. Ordering requestMatchers Incorrectly

Broad rules can shadow narrow ones; some ways of adding matchers after **anyRequest()** are also rejected by the DSL. Put specific rules first and the fallback last.

### 11.6. Forgetting the Authentication Mechanism

**authenticated()** is a requirement; it does not enable **httpBasic** or **formLogin** by itself. For Bearer APIs, configure **oauth2ResourceServer(...)** and corresponding token validation; do not assume an Authorization Bearer header is treated as valid credentials in a Basic chain.

### 11.7. securityMatcher Leaving URLs Outside Every Chain

**anyRequest().denyAll()** inside one chain only blocks requests belonging to that chain. If you only define a chain for **/api/**, an endpoint like **/internal/** may remain unprotected by Spring Security. Always provide a fallback chain and test coverage.

### 11.8. Forgetting @EnableMethodSecurity

Putting **@PreAuthorize** on a service without enabling method security properly can prevent the policy annotation from being enforced. Also avoid self-invocation that bypasses the Spring AOP proxy.

### 11.9. Confusing HTTP Basic with Sessions/JWT

**SessionCreationPolicy.STATELESS** does not enable JWT. HTTP Basic sends username/password (Base64) and requires HTTPS; JWT Bearer uses different validation. For browser session apps, state management and CSRF can be completely appropriate.

### 11.10. Disabling CSRF Just to Fix 403 on All POST Requests

A 403 can come from a missing CSRF token, missing permissions, or a custom handler. Determine whether the client uses cookies/sessions or a Bearer header, the CSRF threat model, and endpoint protection requirements before configuring exceptions or disabling CSRF.

### 11.11. Custom formLogin URL Not Being Handled

If the chain does not match **GET/POST /login** or the custom login page lacks a controller/view, users may encounter 404, a redirect loop, or 403. Keep matchers, loginProcessingUrl, CSRF tokens, and permitAll consistent.

### 11.12. Registering a Security Filter in the Wrong Place

Do not manually create another **FilterRegistrationBean** for a Spring Security filter if the framework already manages it in the chain and you have no special reason. Registering a filter twice or in the wrong order can cause duplicate processing or bypass security controls.

### 11.13. Assuming permitAll Means Bypassing Spring Security

**permitAll()** only allows the request at the authorization step. Security headers, CSRF/CORS, and other filters still apply according to the chain. Avoid overusing **web.ignoring()** for endpoints that should benefit from those protections.

### 11.14. Not Checking Library Versions

Spring Boot 3/Spring Security 6 and Spring Boot 4/Spring Security 7 differ in packages, auto-configuration, and APIs. Modern Lambda DSL documentation is the right direction, but always verify the versions **actually resolved by Gradle/Maven**. In particular, do not copy test imports or custom DSL code from a newer version into an older version without confirming compatibility.

## 12. Self-Check Questions

**Question 1.** Which bean is the standard entry point for configuring HTTP security in modern Servlet Spring Security?

**Answer:** A **@Bean SecurityFilterChain** accepting **HttpSecurity**, configured with the Lambda DSL and returning **http.build()**.

**Question 2.** Does declaring a SecurityFilterChain automatically disable Spring Boot's default in-memory UserDetailsService?

**Answer:** Not necessarily. The web chain and the authentication source are two separate auto-configuration parts. You must declare an appropriate authentication bean if you want to replace the default user source.

**Question 3.** What does **Customizer.withDefaults()** mean?

**Answer:** It enables/configures a feature with its default settings, instead of writing a lambda that customizes none of the inner properties.

**Question 4.** Why does the Lambda DSL not need **.and()**?

**Answer:** The framework returns to HttpSecurity automatically after executing the configuration lambda, so you can continue configuring the next group consistently.

**Question 5.** Does **hasRole("ADMIN")** check whether the username is "admin"?

**Answer:** No. With the default role prefix, it requires the **ROLE_ADMIN** authority.

**Question 6.** Suppose you only create a chain with **securityMatcher("/api/**")** and set **anyRequest().denyAll()** inside that chain. Is the URL **/debug** guaranteed to be protected?

**Answer:** No. If /debug does not match another chain, it can fall outside Spring Security. A catch-all fallback chain is needed.

**Question 7.** Does **.authorizeHttpRequests(auth -> auth.anyRequest().authenticated())** automatically enable HTTP Basic?

**Answer:** You should not assume so. A rule requiring authentication does not specify how credentials are obtained. Configure **httpBasic**, **formLogin**, or another mechanism appropriate for the client.

**Question 8.** Why might an authenticated user receive **403** when calling an endpoint?

**Answer:** Authentication verified the identity, but the policy may require a role/authority or resource permission that the user lacks. CSRF or other filters can also return 403 on certain requests.

**Question 9.** Is **@EnableMethodSecurity** needed for **@PreAuthorize**?

**Answer:** In standard application configurations, yes. A SecurityFilterChain bean for URLs does not automatically enable method-security annotations.

**Question 10.** Why can a custom formLogin receive 404 when using multiple chains?

**Answer:** The login URL may lie outside the **securityMatcher** of the chain containing the login filter, or the application may not yet provide a custom login page.

**Question 11.** Can **http.csrf(csrf -> csrf.disable())** be used for every application that returns JSON?

**Answer:** Do not infer that from JSON or REST. Evaluate whether browsers automatically attach credentials, session/cookie/HTTP auth usage, and the CSRF threat model before designing exceptions.

**Question 12.** Why are both positive and negative tests needed when changing a SecurityFilterChain?

**Answer:** One endpoint returning 200 does not prove another endpoint is properly blocked. Testing anonymous requests, wrong passwords, missing roles, and unlisted URLs helps catch accidental permission leaks or missing authentication mechanisms.

## 13. Official References

- Spring Security — **Java Configuration**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security 6.5 — **Use the Lambda DSL / Configuration Migrations**: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
- Spring Security — **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **Servlet Architecture**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — **Method Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — **Cross Site Request Forgery (CSRF)**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Boot 3.5 — **Spring Security auto-configuration**: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html

**Remember:** use **@Configuration + @Bean SecurityFilterChain + HttpSecurity Lambda DSL** to describe how the application protects requests. Configure the **Authentication** source with appropriate beans, apply authorization rules in the right order, understand each chain's scope, and test both allowed and denied requests. Modern syntax keeps code clear; **correct policies and complete coverage** determine whether the system is protected as intended.
