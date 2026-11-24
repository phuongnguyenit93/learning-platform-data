# SecurityContextHolder in the Servlet Processing Model

**SecurityContextHolder** is the access point to the **SecurityContext** of the current execution thread in Spring Security. In a **Servlet** application such as Spring MVC running with Spring Security 6, this context indicates **which Authentication is bound to the request**: the current principal, authorities (`GrantedAuthority`), and related authentication details. By default, Spring Security uses a **ThreadLocal** mechanism so processing layers on the same thread can access the context without passing Authentication through every parameter.

However, thinking of SecurityContextHolder as merely a "global variable holding the user" leads to serious bugs. The context has a **per-request lifecycle**, must be **established, used, and cleared**, and is not synonymous with long-term session storage. Spring Security 6 has an important distinction between **SecurityContextHolderFilter**, **SecurityContextPersistenceFilter**, and **SecurityContextRepository**; switching to another thread also does not automatically carry ThreadLocal in all cases.

This lesson belongs to the **Security Context** topic, focusing on **SecurityContextHolder in the Servlet processing model**. It covers architecture, Java 17/Spring Boot 3.3.6 + Spring Security 6.x examples, MockMvc/JUnit tests, and real-world failure modes. **Do not apply this ThreadLocal access pattern verbatim to a WebFlux server**: the reactive model primarily uses Reactor Context and ReactiveSecurityContextHolder.

## 1. Three layers to distinguish first

| Component | What is it? | Responsibility |
| --- | --- | --- |
| **SecurityContextHolder** | Static API backed by a SecurityContextHolderStrategy. | Allows current code to access/set/clear SecurityContext according to the configured strategy. |
| **SecurityContext** | Object holding an Authentication, which may be empty. | Holds the authentication state currently considered the active context. |
| **Authentication** | Principal, credentials, authorities, authenticated status, and details. | Represents an authentication request or a verified authentication result. |
| **GrantedAuthority** | A permission/role/scope granted to the principal. | Used in authorization rules, e.g., ROLE_ADMIN or orders:read. |
| **SecurityContextRepository** | Contract for loading/saving context across requests or dispatches. | Determines whether context is restored from session/request and persisted back. |

Conceptual relationship:

~~~text
SecurityContextHolder
        |
        v
SecurityContext
        |
        v
Authentication
   |          |            |
   v          v            v
principal  credentials  authorities
("alice")  (usually     [ROLE_USER,
            erased       orders:read]
            after auth)
~~~

When a Controller calls:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();
~~~

it is retrieving the **Authentication inside the SecurityContext bound to the current thread** according to the holder's strategy. That code does **not** verify passwords, look up users from a database, validate JWTs, or create a session.

### 1.1. SecurityContext stores state, not AuthenticationManager

**AuthenticationManager** and AuthenticationProvider are responsible for verifying credentials to produce a valid Authentication. **SecurityContextHolder** only works with the context attached by the security mechanism. Manually creating an Authentication and putting it into the holder without verifying credentials is not a secure authentication flow.

A typical request has two distinct stages:

- **Authentication**: credentials are verified; a valid Authentication result is placed into the context.
- **Authorization**: URL/method/domain rules decide whether the current Authentication is permitted to invoke the operation.

If a user receives **403** after logging in with valid credentials, troubleshooting SecurityContextHolder should focus on authorities or authorization rules rather than automatically concluding the password is wrong.

## 2. SecurityContext lifecycle in a Servlet request

In a Servlet application, a request passes through the servlet filter chain before reaching DispatcherServlet, Controller, and Service:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["DelegatingFilterProxy"]
    B --> C["FilterChainProxy / matching SecurityFilterChain"]
    C --> D["SecurityContextHolderFilter: load/defer context"]
    D --> E["Authentication filter if credentials exist"]
    E --> F["AuthenticationManager/Provider verifies"]
    F --> G["SecurityContextHolder holds SecurityContext/Authentication"]
    G --> H["AuthorizationFilter + other security filters"]
    H --> I["DispatcherServlet / Controller / Service"]
    I --> J["Response"]
    J --> K["Finish filter processing: clear context"]
~~~

The diagram intentionally simplifies the ordering of some filters, exception translation, anonymous authentication, sessions, and error dispatches. **Not every request executes a successful authentication filter**: a public request without credentials may carry an anonymous Authentication; a rejected request may never enter the Controller.

Key points:

1. **DelegatingFilterProxy** bridges the Servlet container world with Spring-managed filters.
2. **FilterChainProxy** selects the SecurityFilterChain matching the request. Multi-chain configurations must protect URLs outside narrow matchers as well.
3. **SecurityContextHolderFilter** in common Spring Security 6 setups loads/defers context from SecurityContextRepository for downstream filters to use.
4. Authentication filters (Basic, form login, Bearer...) verify matching credentials and can populate a context containing a successful Authentication.
5. **Authorization** relies on the Authentication from the context; if requirements are not met, the request can be blocked.
6. Controller/Service can access the principal within the scope of the request.
7. When the request/filter flow finishes, the framework **clears the holder** so the thread reused by the Servlet container does not carry the previous user's identity.

### 2.1. Why must SecurityContextHolder be cleared?

Servlet containers use thread pools. Thread T1 that just served Alice may subsequently be reused to handle Bob or an anonymous request. If T1 still holds Alice's context, the next request could see **Alice's identity and permissions**, which is a severe security bug.

Spring Security manages clearing the context inside its filter lifecycle. If you manually call setContext in code running **outside** the standard filter lifecycle (unit tests, scheduled tasks, background executors, libraries managing their own threads), you must ensure **clearContext in finally** when you own cleanup responsibility. Do not rely on ThreadLocal disappearing on its own when a thread is reused.

### 2.2. What happens when a request has no Authentication?

SecurityContextHolder.getContext() may return a SecurityContext **containing no Authentication**. Therefore:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String username = authentication == null
    ? "none"
    : authentication.getName();
~~~

This is an **illustrative snippet that can be placed inside a method with imports**. Do not write getAuthentication().getName() in code running outside security filters without handling null.

In a request that has passed through **AnonymousAuthenticationFilter**, authentication may be an **AnonymousAuthenticationToken** rather than null. Subtle detail: AnonymousAuthenticationToken may return **isAuthenticated() = true** per the Authentication contract even though it does **not** represent a real logged-in user. Hence **auth != null && auth.isAuthenticated() is insufficient** to conclude the request comes from a logged-in user. Use Spring Security's authenticated() policy or AuthenticationTrustResolver/equivalent checks when you need to distinguish anonymous from a trusted principal.

## 3. Default strategy: MODE_THREADLOCAL

By default SecurityContextHolder uses **MODE_THREADLOCAL**: SecurityContext is held per Java thread, typically the thread currently serving the Servlet request.

~~~text
Thread servlet-1
  SecurityContextHolder -> Authentication(alice)

Thread servlet-2
  SecurityContextHolder -> Authentication(bob)

Thread servlet-3
  SecurityContextHolder -> empty / anonymous
~~~

These three illustrative lines are not a global map showing all users; each thread only sees the context bound to itself.

**Benefit:** Services running on the same thread can access Authentication without passing the object through many layers. **Limitation:** when switching to another thread, the new thread's ThreadLocal normally **does not contain the previous context**.

### 3.1. SecurityContextHolder modes

| Mode | Behavior | Guidance |
| --- | --- | --- |
| **MODE_THREADLOCAL** | Context is bound to the current thread. | **Appropriate default** for most Servlet applications. |
| **MODE_INHERITABLETHREADLOCAL** | Newly created threads can inherit context value from parent thread at creation time. | Use only if you fully understand the lifecycle; **does not replace safe propagation in thread pools**. |
| **MODE_GLOBAL** | Uses a single shared context across the JVM. | Unsuitable for multi-user Servlet servers because requests can easily mix identities. |
| **Custom SecurityContextHolderStrategy** | Customizes how context is stored/accessed. | Only for specialized use cases with rigorous testing. |

**Do not switch to MODE_GLOBAL** to "solve" an async service not seeing the user. A server handling Alice and Bob concurrently would risk sharing the same principal for both.

**Do not change strategy dynamically while the server is serving requests**. Strategy is system-level configuration; changing it via setStrategyName or setContextHolderStrategy after multiple threads are active can cause race conditions and inconsistency. Most applications should keep the default.

### 3.2. ThreadLocal does not mean session

ThreadLocal lives per **thread**, not per **account** or **HTTP session**:

- A thread handling Alice today can handle Bob next.
- An HTTP session can span multiple requests and multiple threads.
- SecurityContextRepository can load context from the session into the holder on a new request.
- A stateless API can authenticate Bearer/Basic per request without storing context in a session.
- SecurityContextHolder is neither a user database nor a token store.

This is a decisive point when debugging: **"I called setContext in the previous request" does not guarantee the context appears in the next request**.

## 4. Commonly used SecurityContextHolder APIs

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

// 1. Read the current context.
SecurityContext current = SecurityContextHolder.getContext();

// 2. Read Authentication if present.
Authentication auth = current.getAuthentication();

// 3. Create a brand-new context for intentional setup.
SecurityContext fresh = SecurityContextHolder.createEmptyContext();

// 4. Only set an Authentication verified by a trusted source.
fresh.setAuthentication(verifiedAuthentication);

// 5. Place the context into the current thread's holder.
SecurityContextHolder.setContext(fresh);

// 6. Clear the context when your own code owns the lifecycle outside filters.
SecurityContextHolder.clearContext();
~~~

This is an **API explanation snippet**, not a single runnable method: the verifiedAuthentication variable must be produced by a trusted authentication mechanism, and you should not unconditionally set or clear the holder in the middle of a normal request.

### 4.1. Why use createEmptyContext()?

Spring Security recommends creating a **new SecurityContext** whenever you need to set Authentication manually:

~~~java
SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(authenticationVerified);
SecurityContextHolder.setContext(fresh);
~~~

Avoid arbitrarily mutating a shared SecurityContext directly:

~~~java
// Less safe if the context might be shared:
SecurityContextHolder.getContext()
    .setAuthentication(authenticationVerified);
~~~

Creating a new context reduces **race condition** risks when multiple threads/flows happen to reference the same SecurityContext object. It does not replace credential verification, nor does it automatically persist the context to the next request.

### 4.2. getContext() vs getDeferredContext()

Spring Security 6 versions also include a **deferred SecurityContext** mechanism, allowing context loading from the repository to occur only when needed. This can reduce unnecessary work on requests that never access authentication.

Do not assume calling getContext() always queries the database or session; behavior depends on the strategy/repository/filter. When writing deeply integrated filters, prefer the official API of your specific version rather than holding a long-lived static SecurityContext reference.

## 5. Which Servlet filters load, save, and clear context?

### 5.1. SecurityContextHolderFilter: the common approach in Spring Security 6

**SecurityContextHolderFilter** is responsible for **bringing the context from SecurityContextRepository into SecurityContextHolder's scope**, typically supporting deferred loading. It **does not automatically save context changes** back to the repository for subsequent requests.

With **requireExplicitSave(true)**, if **custom code** logs in manually and wants to persist login via session, it must **call SecurityContextRepository.saveContext(context, request, response)** at the appropriate point.

~~~text
New request
  -> SecurityContextHolderFilter loads/defers SecurityContext
  -> Authentication mechanism / authorization / Controller
  -> Custom authentication succeeded?
       -> SecurityContextHolder.setContext(newContext)
       -> If saving to subsequent requests is needed:
            SecurityContextRepository.saveContext(newContext, request, response)
  -> Filter ends and clears holder
~~~

Do not infer from SecurityContextHolder.getContext() having a principal in the current request that the session was successfully written.

### 5.2. SecurityContextPersistenceFilter: legacy mechanism and compatibility

**SecurityContextPersistenceFilter** loaded context before the filter chain and tracked saving modified context when the request completed/response committed via the repository. Under that mechanism, many legacy apps only needed to call setContext and the framework saved changes through the repository.

**Spring Security 6 normally defaults to SecurityContextHolderFilter with explicit-save**, instead of Spring Security 5's auto-saving SecurityContextPersistenceFilter. These two filters should not both be added as competing mechanisms in the same chain.

This is a common cause of bugs when upgrading:

~~~text
Legacy application:
  custom filter sets SecurityContextHolder
  -> legacy mechanism auto-saves context

Upgrade to Spring Security 6:
  custom filter sets SecurityContextHolder
  -> current request has user
  -> next request has no user because custom filter has not called saveContext()
~~~

**Do not fix this by disabling authorization or making endpoints public.** Identify the configured SecurityContextRepository and verify whether the authentication mechanism saves the context per policy.

### 5.3. Built-in authentication mechanisms already manage saving appropriately

Form login, remember-me, Basic, Bearer token, and framework-supported filters have their own logic for attaching context and saving when needed. **Do not add saveContext() to every Controller** just because framework 6 uses explicit-save.

Only when building a custom authentication filter/controller and intentionally wanting to **persist login across requests** should you apply the proper contract. If designed as **stateless**, not saving to session is the desired behavior; manually saving and assuming a session was created will fail with NullSecurityContextRepository.

## 6. SecurityContextRepository: where is it stored and for how long?

SecurityContextHolder and SecurityContextRepository solve two different problems:

- Holder lets **code on the current thread** access the context.
- Repository **reads/saves context** against an appropriate backing store across requests or dispatches.

| Repository | Meaning | When to use? |
| --- | --- | --- |
| **HttpSessionSecurityContextRepository** | Stores/associates context with HttpSession. | Web apps with session login, following session policy and lifecycle. |
| **RequestAttributeSecurityContextRepository** | Holds context in request attributes to serve servlet dispatches such as error dispatches within the same request. | When you want context available across dispatches of a single request. |
| **DelegatingSecurityContextRepository** | Combines multiple repositories; can load from one delegate and save across multiple delegates. | Default setup commonly combines request attribute + HTTP session in Spring Security 6. |
| **NullSecurityContextRepository** | Does not save context for retrieval in subsequent requests. | Stateless APIs that do not tie authentication to a session. |

**RequestAttributeSecurityContextRepository is not a session**: an error dispatch may still see context within the same request, but a new HTTP request does not inherit it.

**NullSecurityContextRepository does not mean skipping authentication**: filters can still verify Basic/Bearer tokens on each request and set Authentication in the current holder, after which context is cleared on completion.

### 6.1. Illustrative repository configuration for stateful login

In a **session-based** application (unlike the stateless example in section 9), configuration might include:

~~~java
// DSL snippet inside a session-based SecurityFilterChain:
.securityContext(securityContext -> securityContext
    .requireExplicitSave(true)
    .securityContextRepository(
        new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        )
    )
)
~~~

This code requires importing repositories from **org.springframework.security.web.context**. If you simply use Spring Security 6's appropriate defaults, you do not necessarily have to declare the repository manually; the example shows how delegates work together.

### 6.2. Illustrative stateless configuration

In an API that must not store authentication in HttpSession:

~~~java
// DSL snippet inside SecurityFilterChain using HttpSecurity:
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.securityContext(securityContext -> securityContext
    .securityContextRepository(new NullSecurityContextRepository()))
~~~

This code requires importing **org.springframework.security.config.http.SessionCreationPolicy** and **org.springframework.security.web.context.NullSecurityContextRepository**. It is not a complete Java file.

**STATELESS** in Spring Security is a policy of the security layer; it does not guarantee that the entire application, servlet container, or another library will never create an HttpSession for its own purposes. Inspect each component and response cookies.

### 6.3. Saving context does not equal granting permissions

If a custom login authenticates Alice with ROLE_USER and saves the context, a subsequent request can restore Alice's identity. This **does not automatically grant Alice ROLE_ADMIN**. Authorization still depends on Authentication authorities and policies at URL/Service/domain layers.

You also must consider **session fixation protection, CSRF, session timeout, logout, session invalidation, and concurrent sessions** when designing session-based login. SecurityContextRepository is one important piece, not the entire session security solution.

## 7. Custom authentication example: setting and saving context at the right time

This is an **illustrative snippet inside a custom authentication filter or a controlled login flow**. It is not a complete production login Controller to copy verbatim, because it does not show validation, exception handling, CSRF, session fixation, success/failure handlers, and other controls.

~~~java
// Assume authenticationManager, securityContextRepository,
// HttpServletRequest request, HttpServletResponse response,
// String username, and safely handled char/password input are available.

Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword);

Authentication result =
    authenticationManager.authenticate(attempt);

// Only after authenticate() succeeds, create a new context.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);

// Only if designing to PERSIST LOGIN across multiple requests.
// NullSecurityContextRepository will not persist the session.
securityContextRepository.saveContext(context, request, response);
~~~

Mandatory rules:

1. **Credentials must be verified first** via AuthenticationManager or a trusted mechanism; never accept a role from the client and call setAuthenticated(true).
2. Only use the **authenticated result Authentication**. Avoid putting an unverified UsernamePasswordAuthenticationToken into the holder and treating it as a real principal.
3. Use **createEmptyContext()** instead of mutating an old context that might be shared.
4. **Call saveContext only when persistence is needed** and the repository actually supports it; pass the right request/response before the response is committed as required.
5. If a custom filter manages context outside the standard lifecycle, clear it in finally; if running inside a Spring Security-managed chain, respect the framework lifecycle and avoid clearing the context prematurely.
6. If an HTTP session is involved, address session authentication strategy and session fixation rather than implementing login with just those ten lines.
7. Never log rawPassword, result credentials, or session cookies; secret-protection rules never change.

### 7.1. Why does login succeed in request A yet request B still gets 401?

Suppose a custom filter sets context properly in request A, the Controller returns 200, yet request B sends only the cookie and receives 401. Causes include:

- Using **SecurityContextHolderFilter** and custom code **forgot saveContext**.
- Saved into **NullSecurityContextRepository**, which does not retain state.
- Missing or wrong session cookie sent.
- Browser did not send the cookie due to domain/path/SameSite/Secure policy.
- Session expired or was invalidated.
- Request B's filter chain selected a different repository.
- The app uses stateless Basic/Bearer, so **request B must send credentials**.

The right way to debug is to check the authentication mechanism, repository, session policy, and actual cookie/token behavior — do not remove the authenticated() rule.

## 8. Ways to obtain the principal in a Servlet Controller

In Spring MVC, you do not always need to call SecurityContextHolder's static API directly. The framework can inject identity info into handler methods:

| Approach | Example | When appropriate |
| --- | --- | --- |
| **SecurityContextHolder.getContext()** | Get SecurityContext then call getAuthentication(). | Code needing context in a layer without method argument resolution. |
| **Authentication method argument** | public ... me(Authentication authentication) | Controller wants current Authentication directly. |
| **Principal method argument** | public ... me(Principal principal) | Only need the abstract name/identity. |
| **@AuthenticationPrincipal** | public ... me(@AuthenticationPrincipal UserDetails user) | You know the principal type of the active auth mechanism. |
| **@CurrentSecurityContext** | Receives SecurityContext or expression extracting Authentication. | Want to access current context via annotation. |
| **HttpServletRequest.getUserPrincipal()** | Servlet API from request wrapper. | Integrating with Servlet code, filters, or legacy libraries. |

### 8.1. Getting the principal via Authentication

~~~java
@GetMapping("/api/me")
Map<String, String> me(Authentication authentication) {
    return Map.of("username", authentication.getName());
}
~~~

This is a **method snippet**: running it requires @RestController/@GetMapping and imports. An endpoint protected by authenticated() can rely on the Authentication provided by Spring Security; never trust a userId from the request to determine identity.

### 8.2. Getting UserDetails via annotation

~~~java
@GetMapping("/api/principal")
Map<String, String> principal(
        @AuthenticationPrincipal UserDetails user) {
    return Map.of("username", user.getUsername());
}
~~~

**Only valid when the principal is actually UserDetails** (common in form/Basic with DaoAuthenticationProvider). With a JWT Resource Server, the principal may be Jwt; with OAuth2 login it may be OidcUser/OAuth2User. Hardcoding UserDetails across every endpoint can produce null or a ClassCastException if the auth mechanism changes.

When you only need the username, **Authentication.getName()** is usually less implementation-coupled. When you need an internal ID or tenant, design a principal/domain identity adapter backed by verified information.

### 8.3. @CurrentSecurityContext

~~~java
@GetMapping("/api/context-name")
Map<String, String> context(
    @CurrentSecurityContext(expression = "authentication.name")
    String username) {

    return Map.of("username", username);
}
~~~

This snippet requires importing org.springframework.security.core.annotation.CurrentSecurityContext and Spring MVC types. The expression is evaluated against the SecurityContext; if unauthenticated or if the principal differs in type, ensure the endpoint has appropriate policies and null handling.

**Never create a singleton service holding Authentication as a field** for "convenience in Controllers". A singleton is shared across all requests and risks mixing user data.

## 9. Complete Java 17 project: SecurityContextHolder with stateless HTTP Basic

This project is **deliberately stateless** to make context lifecycle easy to verify: the client sends HTTP Basic credentials on **every request**, the filter places Authentication in SecurityContextHolder **during the request**, the Controller reads it, and after the request no session authentication is saved. Tests also verify that a subsequent request without credentials gets 401 rather than inheriting Alice.

**Note:** HTTP Basic + demo passwords on localhost are for learning only. Production systems require HTTPS, a trusted identity store, credential protection, an appropriate authentication mechanism, and real security testing. The examples use only HTTP GET, requiring no CSRF disabling.

### 9.1. Directory structure

~~~text
servlet-context-demo/
  pom.xml
  src/main/java/com/example/contextdemo/
    ServletContextApplication.java
    SecurityConfig.java
    ContextController.java
  src/test/java/com/example/contextdemo/
    ContextHttpTests.java
    ContextThreadTests.java
~~~

Requires **Java 17+**, Maven 3.9+, and free port 8080. Package across all Java files is **com.example.contextdemo**.

### 9.2. pom.xml

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
    <artifactId>servlet-context-demo</artifactId>
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

This is a **Servlet/Spring MVC** application, not WebFlux. If you add spring-boot-starter-webflux to a project containing both web and webflux, Boot normally selects the MVC server per auto-configuration; do not use HttpSecurity to conclude a reactive chain is protected.

### 9.3. ServletContextApplication.java

~~~java
package com.example.contextdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletContextApplication.class, args);
    }
}
~~~

The main class sits in the root package so Spring Boot scans SecurityConfig and ContextController.

### 9.4. SecurityConfig.java

~~~java
package com.example.contextdemo;

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
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice"))
            .authorities("ROLE_USER", "orders:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .authorities("ROLE_ADMIN", "orders:read")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/principal")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

**Configuration analysis:**

1. **UserDetailsService** uses two mock users, with BCryptPasswordEncoder hashing the demo passwords.
2. HTTP Basic verifies username/password on each request carrying a valid Authorization header.
3. **SessionCreationPolicy.STATELESS** instructs Spring Security not to create or use an HTTP session to obtain Authentication. This is intentional for the API lab.
4. **NullSecurityContextRepository** does not save SecurityContext for restoration in subsequent requests.
5. **/api/public** is intentionally public for GET; any other HTTP method on the same path is not automatically allowed.
6. **/api/me** and **/api/principal** require authenticated().
7. **/api/admin** requires ROLE_ADMIN, not just anyone with valid credentials.
8. **anyRequest().denyAll()** rejects all other URLs/methods without an explicit policy.
9. The demo **does not disable CSRF**, because it only performs GET requests. If adding POST/PUT/DELETE, design CSRF according to your credential/browser threat model.
10. **SecurityContextHolder is managed by the framework in each request**, so the Controller does not call setContext or clearContext.

Never add a custom filter that sets ROLE_ADMIN just because an X-Role: ADMIN header is present; authorities must only come from UserDetails/a trusted authentication source after password verification.

### 9.5. ContextController.java

~~~java
package com.example.contextdemo;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ContextController {

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    public Map<String, Object> currentUser(
            Authentication methodArgument) {

        Authentication fromHolder = SecurityContextHolder
            .getContext().getAuthentication();

        List<String> authorities = fromHolder.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "name", fromHolder.getName(),
            "sameNameAsMethodArgument",
                fromHolder.getName().equals(methodArgument.getName()),
            "authorities", authorities
        );
    }

    @GetMapping("/api/principal")
    public Map<String, String> userDetailsPrincipal(
            @AuthenticationPrincipal UserDetails user) {

        return Map.of("username", user.getUsername());
    }

    @GetMapping("/api/admin")
    public Map<String, String> adminOnly() {
        return Map.of("message", "admin");
    }
}
~~~

**Why is the value from the holder non-null in /api/me?** SecurityFilterChain requires authenticated() for this endpoint and the HTTP Basic filter populated Authentication if credentials were valid. In a public Controller or scheduled job, that assumption may not hold; check for null or use appropriate annotations/method arguments.

**sameNameAsMethodArgument** shows that the Authentication injected by MVC and the Authentication from the holder describe the same principal in the request. **Do not use name comparison as a security check**; authentication already occurred in the filter and permission checking in authorization.

**Never return the full UserDetails object as JSON**: it may contain password hashes and account flags not meant for clients. The demo API only outputs username/authorities for observation. In production, even internal authorities should only be returned with a clear purpose.

### 9.6. Running the application

~~~bash
mvn test
mvn spring-boot:run
~~~

On Windows PowerShell use **curl.exe**; on Linux/macOS use curl. The commands below use mock credentials on localhost only:

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u alice:demo-alice http://localhost:8080/api/me
curl.exe -i -u alice:demo-alice http://localhost:8080/api/principal
curl.exe -i -u alice:demo-alice http://localhost:8080/api/admin
curl.exe -i -u admin:demo-admin http://localhost:8080/api/admin
curl.exe -i -H "X-Role: ADMIN" http://localhost:8080/api/admin
~~~

Expected results table:

| Request | Status | Reason |
| --- | --- | --- |
| Anonymous GET /api/public | 200 | Intentional PermitAll(), body message=public. |
| Anonymous GET /api/me | 401 | No valid credentials for protected endpoint. |
| GET /api/me with alice/demo-alice | 200 | Valid Basic auth, holder holds alice's Authentication during request. |
| GET /api/principal with alice | 200 | @AuthenticationPrincipal resolves UserDetails alice. |
| GET /api/admin with alice | 403 | Alice lacks ROLE_ADMIN. |
| GET /api/admin with admin/demo-admin | 200 | Has ROLE_ADMIN. |
| GET /api/admin with X-Role header only | 401 | Arbitrary header is not a trusted credential. |

JSON response of /api/me for alice has these fields:

~~~json
{
  "name": "alice",
  "sameNameAsMethodArgument": true,
  "authorities": ["ROLE_USER", "orders:read"]
}
~~~

**Do not assert that JSON key order always matches the example**; the elements in authorities are sorted in code so the array order is stable. Additional HTTP headers may appear depending on the servlet container.

**Independent request check:** After GET /api/me with valid Basic returns 200, calling **GET /api/me without sending Authorization** will return **401**. Reason: in this configuration Authentication is not stored in session, so the previous request's context does not carry over to the next request.

## 10. HTTP tests via MockMvc: reading per-request context

Create **src/test/java/com/example/contextdemo/ContextHttpTests.java**:

~~~java
package com.example.contextdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextHttpTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void privateEndpointNeedsCredentials() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicAuthenticationIsVisibleInHolder()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.sameNameAsMethodArgument")
                .value(true))
            .andExpect(jsonPath("$.authorities[0]")
                .value("ROLE_USER"))
            .andExpect(jsonPath("$.authorities[1]")
                .value("orders:read"));
    }

    @Test
    void authenticationPrincipalResolvesUserDetails()
            throws Exception {
        mvc.perform(get("/api/principal")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void incorrectPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUserIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("missing", "anything")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin"));
    }

    @Test
    void adminEndpointNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void forgedRoleHeaderDoesNotAuthenticate() throws Exception {
        mvc.perform(get("/api/admin")
                .header("X-Role", "ADMIN"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownRouteIsDeniedEvenForValidUser()
            throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void previousRequestDoesNotLeakIdentity()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

This suite has **12 HTTP tests**, covering 200/401/403 status codes, identity consistency within a request, and **no identity inheritance from a previous request**.

MockMvc integrates with Spring TestContext and SecurityFilterChain; it verifies the MVC/Security flow without opening a network port. It does not by itself prove reverse proxies, TLS, browser session cookies, or production setups are correct.

### 10.1. Why use httpBasic() instead of only @WithMockUser?

**@WithMockUser** is a tool that mocks an Authentication for authorization tests. It is very useful when you only care about permissions, yet **it does not verify real passwords, PasswordEncoder, UserDetailsService, or BasicAuthenticationFilter**.

In this test suite, **httpBasic("alice", "demo-alice")** sends an HTTP Basic header, letting the filter chain and sample user store decide authentication. Since the goal is to observe **SecurityContextHolder in a Servlet request**, that testing style demonstrates a more realistic auth flow.

When unit testing standalone methods that need a simulated principal, you can still use @WithMockUser or SecurityMockMvcRequestPostProcessors.user(...), as long as you know clearly what is mocked and what is truly verified.

## 11. SecurityContextHolder with new threads and ExecutorService

This is an area prone to subtle bugs. Because the default strategy uses **ThreadLocal**, the context in the servlet thread **does not automatically appear** in a thread executed by ExecutorService.

~~~text
Servlet thread:
  Authentication = alice
       |
       | executor.submit(task)
       v
Worker thread:
  SecurityContextHolder.getContext()
  -> usually does not have alice's Authentication
~~~

If a background job must be permitted to run under Alice's identity, there must be **intentional propagation**; otherwise it should run under a separate service identity with least privilege. Never copy a username string into a global variable to let a background task "impersonate" the user.

### 11.1. DelegatingSecurityContextRunnable

Spring Security provides **DelegatingSecurityContextRunnable** to run a Runnable with a supplied SecurityContext. The wrapper sets the context on the worker thread before invoking the delegate and clears the context afterward per contract, even if the delegate throws an exception.

~~~java
// Illustrative code snippet inside a method with appropriate variables.
// Use the chosen context after authentication and required authorization checks.
SecurityContext context =
    SecurityContextHolder.getContext();

Runnable businessTask = () -> {
    Authentication auth = SecurityContextHolder
        .getContext().getAuthentication();
    // Use auth per policy; do not log secrets.
};

Runnable wrapped =
    new DelegatingSecurityContextRunnable(businessTask, context);

executor.execute(wrapped);
~~~

Requires importing org.springframework.security.concurrent.DelegatingSecurityContextRunnable. **This is not advice to run every business task with the request's identity**. The context may carry sensitive privileges or a stale snapshot; jobs running hours later require appropriate re-authorization and auditing policies.

### 11.2. Why does MODE_INHERITABLETHREADLOCAL not solve thread pools?

Threads in an executor are typically created and reused; InheritableThreadLocal only inherits the value **when the thread is created**, rather than automatically updating every time a task is submitted. This can cause:

- Workers failing to see the new request context.
- Workers retaining an old identity from another request.
- Context inadvertently leaking to a job that should not have those permissions.
- Race conditions when multiple requests submit tasks to the same pool.

Prefer Spring Security's built-in wrappers/executors or a **controlled and verified** way of passing identity. Never change the global strategy to patch a per-task issue.

### 11.3. Async in Spring MVC

Spring MVC can use Callable, DeferredResult, @Async, or AsyncContext.start. Spring Security integrates propagation for **certain specific async mechanisms**, yet you must not assume **every CompletableFuture, ExecutorService, and callback library** automatically preserves SecurityContext.

Specifically:

- **Callable** managed by Spring MVC integrates via WebAsyncManagerIntegrationFilter under the corresponding model.
- **AsyncContext.start(Runnable)** has support through Spring Security's Servlet API integration when the wrapper is applied.
- **Self-created ExecutorService / CompletableFuture.supplyAsync** do not guarantee propagation by default.
- For **@Async**, an appropriate mechanism such as DelegatingSecurityContextAsyncTaskExecutor can be used, provided the executor is configured properly.

Test directly on the actual async path you use, because timing, thread reuse, and context clearing make these bugs hard to reproduce with synchronous login tests alone.

## 12. Testing ThreadLocal, propagation, and cleanup with JUnit

Create **src/test/java/com/example/contextdemo/ContextThreadTests.java**. This class tests SecurityContextHolder directly on the test thread and on an ExecutorService thread. It makes **no** HTTP requests, making it ideal for learning ThreadLocal boundaries without MVC involvement.

~~~java
package com.example.contextdemo;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

class ContextThreadTests {

    private static SecurityContext contextForUnitUser() {
        Authentication verifiedForTest =
            UsernamePasswordAuthenticationToken.authenticated(
                "unit-user",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            );

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verifiedForTest);
        return context;
    }

    @Test
    void manualContextMustBeClearedInFinally() {
        SecurityContextHolder.setContext(contextForUnitUser());
        try {
            assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName())
                .isEqualTo("unit-user");
        } finally {
            SecurityContextHolder.clearContext();
        }

        assertThat(SecurityContextHolder.getContext()
            .getAuthentication()).isNull();
    }

    @Test
    void newExecutorThreadDoesNotInheritDefaultThreadLocal()
            throws Exception {

        ExecutorService executor = Executors.newSingleThreadExecutor();
        SecurityContextHolder.setContext(contextForUnitUser());

        try {
            Authentication inWorker = executor.submit(() ->
                SecurityContextHolder.getContext()
                    .getAuthentication()
            ).get(5, TimeUnit.SECONDS);

            assertThat(inWorker).isNull();
        } finally {
            SecurityContextHolder.clearContext();
            executor.shutdownNow();
        }
    }

    @Test
    void delegatingRunnablePropagatesAndCleansWorkerContext()
            throws Exception {

        ExecutorService executor = Executors.newSingleThreadExecutor();
        SecurityContext context = contextForUnitUser();
        SecurityContextHolder.setContext(context);

        AtomicReference<String> observedName =
            new AtomicReference<>();

        Runnable work = () -> observedName.set(
            SecurityContextHolder.getContext()
                .getAuthentication().getName()
        );

        try {
            Runnable wrapped =
                new DelegatingSecurityContextRunnable(work, context);

            executor.submit(wrapped).get(5, TimeUnit.SECONDS);

            assertThat(observedName.get()).isEqualTo("unit-user");

            Authentication afterTask = executor.submit(() ->
                SecurityContextHolder.getContext()
                    .getAuthentication()
            ).get(5, TimeUnit.SECONDS);

            assertThat(afterTask).isNull();
        } finally {
            SecurityContextHolder.clearContext();
            executor.shutdownNow();
        }
    }
}
~~~

**Three tests** make clear:

1. When manually setting context in code without a managing filter, you must **clear in finally**.
2. A new thread from an executor, under default MODE_THREADLOCAL, **does not have the caller's Authentication** without propagation.
3. DelegatingSecurityContextRunnable **intentionally passes the context into the worker and clears it after completion**, so the next task on the same worker does not inherit unit-user's identity.

Remember that the context in the test is built via **UsernamePasswordAuthenticationToken.authenticated(...)** for unit-test purposes, not from credentials checked by PasswordEncoder. **Never reuse the pattern of creating an authenticated token directly from HTTP client data in production.**

### 12.1. Thread testing limitations

The tests above run with Spring Security's default MODE_THREADLOCAL; they do not prove every executor/framework behaves identically. If a project has changed the JVM-wide strategy, test conditions must be adjusted or safely restored before running tests.

For real products, add tests for worker pools reused many times, tasks throwing exceptions, cancelled tasks, and sessions/tokens revoked before the job executes. A task running with an old context may still need a **current permission check** at the time business logic executes.

## 13. SecurityContextHolder and session management

A session-based diagram:

~~~text
Request 1: POST /login
  -> filter verifies password successfully
  -> create SecurityContext(Authentication=alice)
  -> save to HttpSessionSecurityContextRepository
  -> browser holds session cookie

Request 2: GET /dashboard + session cookie
  -> filter loads context from repository
  -> request's SecurityContextHolder has Alice
  -> authorize + Controller
  -> end of request clears ThreadLocal

Request 3: GET /dashboard + session cookie
  -> may be handled by a different thread
  -> repository can still load Alice by session
~~~

Key takeaway: **It is not ThreadLocal surviving across three requests**. Connecting identity across requests happens via **repository/session cookie** or a token mechanism re-verified on each new request.

### 13.1. Form login and session fixation

When form login succeeds, the framework includes mechanisms to handle session fixation, such as rotating the session ID according to configuration. A custom authentication flow that saves SecurityContext while bypassing SessionAuthenticationStrategy can create risks of session fixation, concurrent session issues, or inconsistent state.

Do not "roll your own form login" simply with setContext followed by saveContext. If customization is needed, prefer standard authentication filters/handlers, configure session and security context properly, and test login success/failure/logout/CSRF/session invalidation.

### 13.2. What does logout do to the context?

Proper logout must address everything in the threat model: current SecurityContext, SecurityContextRepository/HttpSession if stateful, session cookies, and related remember-me/tokens. **SecurityContextHolder.clearContext() alone does not guarantee** old sessions are invalidated or previously issued tokens are revoked.

With stateless JWTs, clearContext only affects the current thread/request; a still-valid token can still be sent in a new request. Short TTL/revocation/introspection or an appropriate revocation policy is required when immediate logout is required.

### 13.3. User locked while session still exists

If a user previously logged in with a session and then an admin locks the account in the database, the context in the session may still contain the old Authentication. SecurityContextHolder does not by default call UserDetailsService on every request to refresh the four account flags.

Revoking sessions, permissions, and sensitive data must be designed separately from context storage. The same applies to JWT tokens carrying previously issued claims/authorities.

## 14. Anonymous Authentication and proper permission checks

AnonymousAuthenticationFilter can create an AnonymousAuthenticationToken for unauthenticated requests. This is an Authentication object used by the framework to represent an anonymous caller, not proof of a valid password or JWT.

Be careful to distinguish:

~~~java
Authentication auth = SecurityContextHolder
    .getContext().getAuthentication();

// Not enough to confirm a real user:
boolean flag = auth != null && auth.isAuthenticated();
~~~

An AnonymousAuthenticationToken can have isAuthenticated() = true. To decide URL access permissions, use framework rules **authenticated()** / **fullyAuthenticated()** / **anonymous()** as required, instead of writing if (auth.isAuthenticated()) manually in a Controller.

When application logic truly needs to inspect the current principal:

~~~java
Authentication auth = SecurityContextHolder
    .getContext().getAuthentication();

AuthenticationTrustResolver resolver =
    new AuthenticationTrustResolverImpl();

boolean realUser = auth != null
    && auth.isAuthenticated()
    && !resolver.isAnonymous(auth);
~~~

This snippet is a **Java fragment**, requiring imports of AuthenticationTrustResolver and AuthenticationTrustResolverImpl from org.springframework.security.authentication. For applications needing to distinguish remember-me from fully-authenticated, use resolver.isRememberMe(...) or the appropriate authorization rule for your version.

**Do not treat the username "anonymousUser" as a secure anonymous-detection mechanism**: that name is a configurable value, can be changed, or could collide with a real username. Always use official types/resolvers/policies.

### 14.1. Can SecurityContextHolder be used for manual role checks?

The technique:

~~~java
boolean isAdmin = SecurityContextHolder.getContext()
    .getAuthentication().getAuthorities().stream()
    .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
~~~

appears occasionally in integration code, yet is usually **not the first choice** to protect endpoints. Prefer configuring authorization at HTTP and method/domain levels:

- **requestMatchers("/api/admin/**").hasRole("ADMIN")** for HTTP routes.
- **@PreAuthorize("hasAuthority('orders:read')")** at Service level when method security is enabled.
- **Owner/tenant checks** in domain Services when access depends on a specific object.

Manual role checks inside Controllers are easy to miss on new routes or when Services are called outside HTTP, and do not handle IDOR/BOLA automatically. Authentication from context is trusted input **after authentication**, yet business permissions still need precise policies.

## 15. SecurityContextHolder and async/error dispatches

A Servlet request can go through multiple **dispatch types**: REQUEST, ASYNC, ERROR. This can change both the thread and the timing of security context handling.

### 15.1. Error dispatch

An exception in a Controller can lead to an ERROR dispatch. If the context only existed in a ThreadLocal on a branch that was already cleared, the error handler may not see the principal. **RequestAttributeSecurityContextRepository** is designed to retain context in request attributes within the same request, helping certain error dispatches access context when filters/dispatches are properly configured.

Do not use HttpSession just to patch every error dispatch issue; understand which repository holds state within one request and which is for cross-request persistence.

### 15.2. Async dispatch

With Callable/DeferredResult or servlet async, context may be propagated by framework integration or lost across thread hops depending on the API type. Things to verify:

- Does the filter chain participate in ASYNC dispatch as expected?
- Is the task created by Spring MVC or a self-managed ExecutorService?
- Which SecurityContext is snapshotted: before or after authentication completes?
- Who is responsible for clearing context on the worker thread?
- If the request finishes before the task, is the task still allowed to act under the old principal?

Never fix async issues by putting SecurityContext into an un-cleared **static ThreadLocal** or switching to MODE_GLOBAL. Use official propagation mechanisms and test them.

## 16. Common pitfalls with SecurityContextHolder

### 16.1. Storing Authentication in a static variable

~~~java
// ANTI-PATTERN: all requests can share a single variable.
static Authentication currentUser;
~~~

A multi-user application shares the same class inside the JVM. A static variable does not distinguish requests, so user A's data can leak to B. Use SecurityContextHolder per standard lifecycle or an appropriate request-scoped abstraction.

### 16.2. Setting Authentication before verifying credentials

If a Controller accepts username and role in the request body and calls UsernamePasswordAuthenticationToken.authenticated(...), the client can forge ROLE_ADMIN. Never create a trusted Authentication from unverified input.

### 16.3. Forgetting clearContext in a background worker

Thread pools reuse threads. Custom code that sets context manually without clearing it in finally can cause the next task to run with someone else's permissions.

### 16.4. Mutating a shared context

SecurityContext may reference the same object across threads or storage layers; directly mutating a shared context creates race conditions and privilege leaks. When manually setting Authentication, create a fresh context and set it only after valid authentication.

### 16.5. Assuming context is automatically saved to session

Calling setContext in the current request and repository persistence are two separate operations in Spring Security 6 with explicit-save. Custom login may succeed on one request yet return 401 on the next.

### 16.6. Adding both context-management filters

Configuring both SecurityContextPersistenceFilter and SecurityContextHolderFilter in the same chain can cause inconsistent lifecycles or overwrites. Use the configuration supported by your deployed Spring Security 6 version.

### 16.7. Switching to MODE_GLOBAL so @Async sees the user

Context becomes JVM-wide data, violating the multi-user Servlet model. Use DelegatingSecurityContextRunnable/Executor or a verified principal/service identity.

### 16.8. Assuming isAuthenticated() excludes anonymous

AnonymousAuthenticationToken can report authenticated=true. Use the authorization DSL's authenticated() or AuthenticationTrustResolver to distinguish them.

### 16.9. Always casting principal to UserDetails

With JWT/OIDC/mTLS, the principal may not be UserDetails. Use Authentication.getName() when you only need the name; design an identity adapter when you need a stable userId/tenant.

### 16.10. Returning SecurityContext or Authentication directly as JSON

Context/Authentication can contain credentials, details, session attributes, claims, or internal authorities. Return only the needed response DTO; never log raw Authorization headers, session cookies, password hashes, or tokens.

### 16.11. Treating 401/403 as certain proof of a holder bug

401 can stem from credentials, entry point, or session persistence; 403 can stem from authorities, CSRF, or object policies. Inspect filters, authentication manager, holder, repository, and authorization in order.

### 16.12. Confusing SecurityContextHolder with RequestContextHolder

Spring Web's **RequestContextHolder** stores request attributes, not Spring Security Authentication. Obtaining request context does not mean you have a verified principal.

### 16.13. Forgetting service/domain protection after authenticated()

A user with a valid Authentication calling GET /orders/42 belonging to someone else still requires owner/tenant checks. Context provides identity, **not automatic object-access verification**.

### 16.14. Forgetting to test session and thread leakage

Testing each 200 request in isolation does not catch subsequent requests seeing an old user. Test **authenticated request → anonymous request** on the same process and **worker task → next task** on the same executor.

## 17. Debugging SecurityContextHolder along the request trace

When an endpoint reads an unexpected Authentication, check in order:

1. **Is this really the Servlet stack?** If the server runs WebFlux, check Reactor Context and ReactiveSecurityContextHolder; do not force Servlet ThreadLocal.
2. **Which SecurityFilterChain matches?** Is a chain using a narrow securityMatcher leaving the request unprotected?
3. **Which repository is SecurityContextHolderFilter using?** HttpSession/RequestAttribute/Delegating/Null; is explicit-save enabled?
4. **What credentials/session cookie does the request carry?** Basic, Bearer, form session, or remember-me? Never print raw credentials into logs.
5. **Did an authentication filter run?** If no credentials were sent, is anonymous authentication active?
6. **Did AuthenticationManager succeed?** If it failed, did HTTP return a 401/challenge or redirect?
7. **In the Controller, what are Authentication principal/authorities?** Log only safe fields in controlled environments.
8. **If the same request spans multiple threads**, is context properly propagated via an executor/framework integration?
9. **If request B loses login**, was context saved to the repository? Did the browser send back the cookie? Is Null repository configured?
10. **If request B sees the wrong user**, inspect thread pools, custom context set/clear, singletons/static fields, and session routing.
11. **If 403 happens after login**, check hasRole/hasAuthority, CSRF, and object-level policy; do not rush to remove authorization.
12. **If errors only occur during ERROR/ASYNC dispatch**, check dispatcher types, request attributes, and security filter invocation.
13. **If old permissions persist after disable/logout**, check session/token revocation and the source of authorities, not just clearContext on one thread.
14. **Write reproduction tests** for successful requests, subsequent credential-less requests, worker threads, and thread cleanup.

This is a root-cause investigation process, not advice to enable raw SecurityContext logging in production. Context holds sensitive identity data; if logging is needed, keep only request IDs and redacted reason codes.

## 18. Testing to separate layers of responsibility

| Test | Layer verified | Expected evidence |
| --- | --- | --- |
| Anonymous request to /api/public | URL authorization | 200 and minimal public body. |
| Anonymous request to /api/me | Authentication entry point | 401, no protected data invoked. |
| Valid Basic to /api/me | Authentication filter + holder + Controller | Name/authorities match the authenticated principal. |
| Wrong Basic to /api/me | AuthenticationManager + filter failure | 401, no protected data body. |
| Alice calls /api/admin | Authorization, not password verification | 403 despite valid authentication. |
| Admin calls /api/admin | Role rule | 200 and matching role. |
| GET /api/me with Basic then another without Basic | No login persistence in stateless API | Next request gets 401. |
| Set context in a JUnit thread | ThreadLocal strategy | Current thread reads Authentication. |
| New executor without wrapper | Boundary of ThreadLocal | Worker does not automatically have Authentication. |
| DelegatingSecurityContextRunnable | Controlled propagation and cleanup | Worker reads principal while running; next task does not leak. |

If the application has stateful sessions, add tests for **form login creates session cookie → next request sends cookie and succeeds → logout → next request is rejected**. Do not reuse the stateless demo's expectations since the two models have different persistence policies.

## 19. Self-check questions

1. Does SecurityContextHolder directly verify passwords or JWTs? **Hint:** no; it manages access to SecurityContext.
2. What is the main object held inside SecurityContext? **Hint:** Authentication.
3. Why is createEmptyContext() recommended when manually attaching an Authentication? **Hint:** avoid mutating a context that might be shared.
4. What does MODE_THREADLOCAL do and what is lost when moving to ExecutorService? **Hint:** keeps per-thread, does not auto-propagate.
5. Why is MODE_GLOBAL dangerous in a multi-user Servlet server? **Hint:** a single JVM-wide context.
6. Request A logs in successfully, yet request B gets 401. Which repository/session/credential causes should be checked?
7. How does SecurityContextHolderFilter differ from SecurityContextPersistenceFilter in context saving?
8. Does RequestAttributeSecurityContextRepository preserve data across a **new HTTP request** or across dispatches of the same request?
9. How does HttpSessionSecurityContextRepository differ from NullSecurityContextRepository?
10. Why is SecurityContextHolder.clearContext() not equivalent to session logout or JWT revocation?
11. Can Authentication.isAuthenticated() alone identify a real user? **Hint:** anonymous token.
12. Is retrieving the principal via @AuthenticationPrincipal UserDetails safe with JWT/OIDC? **Hint:** different principal types.
13. Does @WithMockUser verify real password hashes? **Hint:** no; it mocks Authentication.
14. Why must a custom Servlet login consider SessionAuthenticationStrategy alongside saveContext?
15. How do you test context leakage between two tasks on the same thread pool?
16. With a session still alive after an account is disabled, why does the holder not automatically know permissions should be revoked?
17. If an app uses a WebFlux server, what mechanism should replace ThreadLocal holder for accessing security context? **Hint:** ReactiveSecurityContextHolder/Reactor Context.
18. The Controller already sees Authentication(alice); can Alice automatically read Bob's order? **Hint:** separate object-level policy is needed.

### Memory checklist

- **SecurityContextHolder** is the access point to the current execution's SecurityContext, not an AuthenticationManager or user database.
- **SecurityContext** holds Authentication; it may have no Authentication yet or hold an anonymous Authentication.
- **MODE_THREADLOCAL** is the Servlet default; it does not auto-propagate to every executor thread.
- **The Spring Security filter chain** manages establishing and clearing context for normal requests.
- When manually setting context in code outside filters, **create a new context and clear it in finally**.
- **SecurityContextHolderFilter** typically loads/defers context in Spring Security 6; **explicit save** is required when custom code wants to persist login across requests.
- **SecurityContextRepository** governs persistence: HttpSession, RequestAttribute, Delegating, or Null.
- **STATELESS + NullSecurityContextRepository** does not save Authentication for the next request.
- **SecurityContextHolder is not automatically a session** and clearContext does not automatically log out or revoke tokens.
- **AnonymousAuthenticationToken can have isAuthenticated=true**; use the authorization DSL/AuthenticationTrustResolver properly.
- **@AuthenticationPrincipal, Authentication method argument, and @CurrentSecurityContext** help read the principal in MVC.
- **DelegatingSecurityContextRunnable** enables intentional propagation and cleanup in worker threads.
- **Reading a principal differs from granting permissions**; role/permission/tenant/object authorization is still required separately.
- **Test HTTP and thread lifecycles**, not just a 200 login.

## References

1. [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): SecurityContextHolder, SecurityContext, Authentication, and ThreadLocal.
2. [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): SecurityContextRepository, SecurityContextHolderFilter, SecurityContextPersistenceFilter, and explicit save.
3. [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): sessions, requireExplicitSave, and framework behavior upgrades.
4. [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): DelegatingSecurityContextRunnable and cross-thread propagation.
5. [Spring Security — Servlet API Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html): HttpServletRequest, Principal, and servlet async.
6. [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc, @WithMockUser, and test context creation mechanisms.
7. [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): requestMatchers, hasRole, authenticated, and denyAll.

**Version note:** The lab code targets Java 17 and Spring Boot 3.3.6 (Spring Security 6.3.x) for consistent API examples. When creating a new project, choose a supported Spring Boot/Spring Security release, check the Javadoc for your active dependencies, and re-run tests. Default filter details, persistence, and integration specifics may vary across upgrades.

## Conclusion

In the **Servlet** processing model, **SecurityContextHolder** allows code to access the **current execution's SecurityContext**, which usually holds an Authentication verified by Spring Security. With the default **ThreadLocal** strategy, the context suits single-request processing, yet **does not automatically become session-wide data** and **does not automatically follow onto other threads**. The filter chain handles lifecycle; SecurityContextRepository governs persistence; async mechanisms need safe propagation; and authorization decides which resources a user may access. Clearly separating these roles and testing **next requests, next threads, authentication, and authorization** prevents identity leakage, lost sessions, and wrong permission grants.
