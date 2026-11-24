# SecurityContextRepository and Context Save/Load Strategies in Spring Security Servlet

## 1. Objectives and the Problem to Solve

When a user logs in successfully, Spring Security can place the **Authentication** object into the **SecurityContext** so downstream components in the same request know who is acting. However, the next question is:

> When the request finishes and a new request arrives, where does Spring Security retrieve the authentication information from?

**SecurityContextRepository** is the extension point that answers that question for **Servlet** applications. The repository is responsible for **loading** and **saving** the SecurityContext associated with an HTTP request/response. Depending on the application model, the context may be stored in **HttpSession**, in a **request attribute**, or **not persisted across requests**.

After this lesson, you will be able to:

1. Distinguish **SecurityContextHolder**, **SecurityContextHolderStrategy**, **SecurityContextRepository**, and the authentication mechanism.
2. Understand when SecurityContext is loaded/saved/cleared in Spring Security 6, especially **SecurityContextHolderFilter** and the **explicit save** requirement.
3. Choose appropriately between **HttpSessionSecurityContextRepository**, **RequestAttributeSecurityContextRepository**, **DelegatingSecurityContextRepository**, and **NullSecurityContextRepository**.
4. Explain the impact of **SessionCreationPolicy** on stateful/stateless authentication.
5. Run a Spring Boot example on the Servlet stack, log in via form login, and verify identity restoration on subsequent requests.
6. Know how to save SecurityContext manually when writing a custom authentication flow and diagnose "login succeeds but the next request loses login".

This lesson covers SecurityContext only in **Spring Security Servlet**. Reactor context integration in WebFlux uses a different storage/context model, and the Servlet classes below do not apply directly.

## 2. Four Easily Confused Objects

| Component | Role | Default scope / timing |
| --- | --- | --- |
| **Authentication** | Principal/identity, authorities, and authentication status; may hold credentials if not yet erased | Created/updated by the authentication mechanism |
| **SecurityContext** | Wrapper holding the active context's Authentication | Referenced during security processing |
| **SecurityContextHolder** + **SecurityContextHolderStrategy** | Provides access to get/set the active SecurityContext for currently executing code | Defaults to ThreadLocal in Servlet; requires special handling when switching threads |
| **SecurityContextRepository** | Loads/saves SecurityContext to bridge the context with HTTP requests, request attributes, or sessions | Depends on implementation and chain configuration |

For example, in a controller requiring login:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String username = authentication.getName();
~~~

This snippet **reads the context already present in the current execution scope**. It does not write Authentication to a database, does not create a session, and does not guarantee that the next HTTP request will have the same identity.

You can visualize it as:

~~~text
Current HTTP request
     |
     v
SecurityContextRepository --load--> SecurityContext
                                     |
                                     +--> Authentication(principal, authorities...)
                                     |
SecurityContextHolderStrategy -------+--> current code reads context
     |
     v
If an authentication event occurs and state must persist:
Repository.saveContext(context, request, response)
     |
     +--> request attribute, HttpSession, or not saved (depending on repo)
     |
HTTP response ends --> holder is cleared
     |
Next request --> repository reloads if suitable saved data exists
~~~

**Remember:** Holder addresses the **current execution context**; Repository addresses **how the context is loaded/saved in association with an HTTP request**. Calling `setContext(...)` alone is not enough to guarantee identity persistence for the next visit.

### SecurityContextHolder Is Not Session Storage

SecurityContextHolder defaults to **MODE_THREADLOCAL**, meaning data is bound to the processing thread. Servlet containers reuse threads across requests, so Spring Security must set up and clear the context properly on every request to avoid identity leaks between users. HttpSession, on the other hand, is a mechanism for storing state across multiple HTTP requests and is not synonymous with ThreadLocal.

Strategies like MODE_INHERITABLETHREADLOCAL or MODE_GLOBAL exist, though they are not universal solutions for securing requests. In particular, passing Authentication across thread pools/async requires intentional context propagation such as DelegatingSecurityContextExecutor or the framework's async integration; copying ThreadLocal indiscriminately can leak identities.

## 3. Context Load and Save Lifecycle in Spring Security 6

In modern Servlet configurations, **SecurityContextHolderFilter** is typically responsible for bringing the SecurityContext from the repository into **SecurityContextHolderStrategy** when a request enters the filter chain. It uses a **deferred context** mechanism to avoid unnecessary loading if nothing accesses the context.

Conceptual flow:

~~~text
Client GET /me + Cookie: JSESSIONID=...
  |
  v
FilterChainProxy -> matched SecurityFilterChain
  |
  v
SecurityContextHolderFilter
  |  obtains DeferredSecurityContext from SecurityContextRepository
  |  registers it with SecurityContextHolderStrategy
  |
  v
Downstream filters need authentication -> context is resolved
  |
  +-- context exists in request attribute / HttpSession?
  |         |
  |         +-- yes -> retrieves saved Authentication
  |         +-- no  -> initially empty context
  |
  v
Authentication filter (if new authentication is needed)
  |
  v
AuthorizationFilter -> Controller
  |
  v
End of request -> context/holder cleared within scope
~~~

**Key point in Spring Security 6:** SecurityContextHolderFilter **loads** the context but **does not automatically save the context when the request finishes**. When an application sets Authentication manually and wants it saved for the next request, it must call **SecurityContextRepository.saveContext(...)** according to the chosen storage mechanism.

This differs from the older model often described via **SecurityContextPersistenceFilter**, where the filter observed/saved the context at the end of the chain. Spring Security 6 favors **explicit save** to avoid unnecessary writes and cases where the response is already committed before saving finishes.

Standard authentication filters like form login are configured by the framework to save the context when needed; developers using standard flows **do not** have to call saveContext manually after every login. Conversely, when building a custom login mechanism, only setting SecurityContextHolder without saving can cause login to "work for one request and then vanish".

### Why Must Saving Happen Before Response Commit?

After the server sends/commits the response (e.g., a 302 redirect), adding or modifying a session cookie may no longer be possible. For custom login flows, finish setting up the context and call **saveContext before redirecting or writing the response**, rather than relying uncertainly on the end of the request.

## 4. The SecurityContextRepository Interface

From a usage perspective, know the following operations:

| API | Meaning |
| --- | --- |
| **loadDeferredContext(HttpServletRequest)** | Returns a DeferredSecurityContext; the context may be loaded lazily only when needed |
| **saveContext(SecurityContext, HttpServletRequest, HttpServletResponse)** | Saves the context per the implementation's policy |
| **containsContext(HttpServletRequest)** | Reports whether the repository holds a context associated with the request per its implementation logic |

Older APIs such as `loadContext(HttpRequestResponseHolder)` appear in legacy docs/versions, but when designing new applications with Spring Security 6, understand deferred loading and explicit save.

A fragment reading the context directly (illustrative only, not a replacement for filter lifecycle):

~~~java
DeferredSecurityContext deferred =
    securityContextRepository.loadDeferredContext(request);

SecurityContext context = deferred.get();
Authentication authentication = context.getAuthentication();
~~~

Compiling this fragment requires `securityContextRepository`, `request`, and imports for `DeferredSecurityContext`, `SecurityContext`, and `Authentication`. In everyday application code, **retrieve the context from SecurityContextHolder** managed by Spring Security; do not call `repository.loadDeferredContext` repeatedly at random in controllers.

With **saveContext**, do not equate it with "permanently storing passwords/tokens". The repository only persists the SecurityContext object per the chosen policy; in a session model, Authentication contents can be tied to the session. This data must be protected and should not retain unnecessary credentials.

## 5. HttpSessionSecurityContextRepository: Persisting Login by Session

**HttpSessionSecurityContextRepository** reads/writes SecurityContext in **HttpSession**. After a browser logs in via form and the session is saved, subsequent requests send the session cookie so the server locates the session and retrieves Authentication.

~~~text
POST /login (credentials + valid CSRF token)
  |
  +-- Form-login authentication succeeds
  +-- creates SecurityContext holding Authentication
  +-- saveContext(...) -> HttpSession
  |
  +-- response sends session cookie if needed
          |
Browser holds cookie
          |
GET /me (Cookie: JSESSIONID=...)
  |
  +-- repository loads SecurityContext from HttpSession
  +-- AuthorizationFilter sees authenticated user
  +-- controller is invoked
~~~

Points to understand:

- **JSESSIONID is typically a lookup key referencing the session**, not the Authentication itself or a password. The server looks up the session based on the cookie; never infer permissions merely because a client sent an arbitrary cookie string.
- The repository may **avoid creating a new session** if the context is empty, anonymous, or has no changes requiring persistence; session creation policies and other application components can also influence this.
- **Session existence does not mean logged in.** Spring Security may create a session prior to login for request caching or CSRF tokens; inspect Authentication to determine identity.
- Sessions can expire, be invalidated on logout, or fail to be shared across nodes if the system lacks a shared-session strategy.
- By default, Spring Security stores SecurityContext in the session under an internal key defined by HttpSessionSecurityContextRepository; do not manually mutate this attribute from controllers.

**Good fit:** web MVC using form login, or applications requiring login persisted across multiple requests via HTTP session.

**Considerations:** CSRF, session fixation, appropriate Secure/HttpOnly/SameSite cookie flags, session timeout, logout, clustering, and protecting the session store. The repository does not replace these mechanisms.

## 6. RequestAttributeSecurityContextRepository: Keeping Context Within One Request

**RequestAttributeSecurityContextRepository** stores SecurityContext in a **Servlet request attribute** so dispatches within the same request can recover the context.

A useful example: an endpoint throws an error and the container performs an **ERROR dispatch** to an error page; some environments may clear SecurityContextHolder between dispatches. Request attributes allow a context saved on the request to remain accessible during error handling.

~~~text
Initial request
  |
  +-- context is saved in a request attribute
  |
  +-- error occurs
          |
          +-- ERROR dispatch (same request)
                  |
                  +-- repository reloads context from attribute
~~~

This is **not** equivalent to saving in HttpSession. RequestAttributeSecurityContextRepository **does not persist the context to a new HTTP request**: the next request has a different HttpServletRequest object, so it cannot retrieve the old attribute.

**Good fit:** preserving context across dispatches within a single request; typically one part of a composite repository. Using only the request-attribute repository means login will not survive into the next request.

## 7. DelegatingSecurityContextRepository: Combining Multiple Stores

**DelegatingSecurityContextRepository** accepts multiple SecurityContextRepository instances in order, for example:

~~~java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
~~~

When loading, it can use a context found from its delegates in order; when saving, it forwards `saveContext` calls to the delegates per contract. With request attributes first and HttpSession second, the application supports context across request dispatches while also persisting session login.

This is the **common default repository configuration in Spring Security 6 for session-enabled Servlet applications**. However, the actual configuration can change when enabling STATELESS, providing a custom repository, using multiple SecurityFilterChains, or customizing authentication mechanisms.

Do not view DelegatingSecurityContextRepository as a distributed session solution: it **does not replicate sessions across servers**. Each delegate retains its own limits and semantics.

## 8. NullSecurityContextRepository: No Cross-Request Persistence

**NullSecurityContextRepository** does not persist SecurityContext across requests. It typically appears in stateless API models where each request brings its own authentication evidence such as a **bearer token** or **HTTP Basic**.

~~~text
GET /api/me + Authorization: Bearer <token>
  |
  +-- filter validates this request's token
  +-- places Authentication in this request's context
  +-- controller processes request
  |
  +-- request ends, context is cleared
          |
GET /api/me without token
  |
  +-- no login context saved from previous request
  +-- protected endpoint -> 401
~~~

**Null repository does not disable authentication or authorization.** It only skips retaining the context across requests. Authentication filters can still place Authentication into SecurityContextHolder for components within the current request to use.

If the application uses tokens, validate signature/issuer/audience/expiry/scopes via an appropriate mechanism; the Null repository **does not make a token valid or safer**. For OAuth2 Resource Server, prefer Spring Security's built-in support over writing custom bearer-token parsing filters.

## 9. Comparing Context Storage Strategies

| Repository | Where is it stored? | Reusable in a new request? | Suitable use cases |
| --- | --- | --- | --- |
| HttpSessionSecurityContextRepository | Server-side HttpSession | **Yes**, if the session is valid and the context was saved | Form login / stateful web |
| RequestAttributeSecurityContextRepository | `HttpServletRequest` attribute | **No** | ERROR/FORWARD dispatches within one request |
| DelegatingSecurityContextRepository | Delegates to child repositories | **Depends on delegates**; typically includes HttpSession | Servlet web needing both request dispatch and session |
| NullSecurityContextRepository | Not stored | **No** | Stateless APIs, per-request authentication |

Ask **"where is it saved?"** before asking **"why was the user logged out?"**. Choosing NullSecurityContextRepository and expecting a session on the next request contradicts the chosen policy.

### Four Session Creation Policies

**SessionCreationPolicy** is a SecurityFilterChain-level setting governing how Spring Security creates/uses HttpSession; it is not an alias for SecurityContextRepository.

| Policy | Primary meaning | Scenario |
| --- | --- | --- |
| **ALWAYS** | Spring Security creates a session | Applications intentionally requiring a session immediately |
| **IF_REQUIRED** | Spring Security creates a session only when needed | Typical stateful web login |
| **NEVER** | Spring Security does not proactively create a session, but may use an existing one | Policy restricting session creation while not fully stateless |
| **STATELESS** | Spring Security neither creates a session nor uses HttpSession to obtain SecurityContext | APIs authenticating independently per request |

A typical configuration:

~~~java
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
~~~

Or:

~~~java
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

These two snippets are **mutually exclusive alternatives**, not chained calls in one configuration. Once STATELESS is chosen, design per-request independent authentication flows and verify nothing relies on an old session.

**Important note:** seeing a cookie or existing session on an endpoint may originate from another part of the application. STATELESS constrains how Spring Security uses sessions to obtain context; it does not guarantee that third-party Servlet libraries outside Spring Security never create a session. Configuration and testing must still account for the whole application.

## 10. Runnable Example: Persisting SecurityContext Across Form Login

We will build a Spring Boot MVC application showing that **the first request authenticates and the subsequent request reloads the context from the session**. The example uses:

- Java 17 or higher, Maven.
- Spring Boot **3.3.13** (Spring Security 6 line).
- A SecurityFilterChain with default form login.
- DelegatingSecurityContextRepository combining RequestAttribute and HttpSession.
- An in-memory user with a BCrypt-hashed password.
- A controller that reads Authentication and checks whether a session exists.

### 10.1. Project Tree

~~~text
context-repository-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/contextdemo/
    │   ├── ContextDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/contextdemo/
        └── ContextRepositoryTest.java
~~~

### 10.2. pom.xml

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
    <artifactId>context-repository-demo</artifactId>
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

### 10.3. ContextDemoApplication.java

~~~java
package com.example.contextdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextDemoApplication.class, args);
    }
}
~~~

### 10.4. SecurityConfig.java

~~~java
package com.example.contextdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {

        http
            .securityContext(context ->
                context.securityContextRepository(repository))
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public", "/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("password123"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

**Explanation of decisions:**

1. **securityContextRepository()** is a bean configuring a repository with two delegates. In this lesson we declare it explicitly to make storage visible; in many typical session-based Servlet setups, Spring Security already configures a similar composite repository.
2. **http.securityContext(...repository(...))** assigns the repository to the SecurityFilterChain. Do not expect defining a standalone bean without wiring it into configuration to alter all chains in the application.
3. **IF_REQUIRED** allows Spring Security to use a session when needed to persist login state.
4. **formLogin(...)** enables the default login page, POST /login processing, and context saving per framework configuration after successful authentication.
5. **PasswordEncoder** produces BCrypt hashes. The sample password in source code is for learning only; production uses a durable user store and proper secret management.
6. **CSRF protection is not disabled.** The form login generated by Spring Security includes a CSRF token; the browser submits the token via the form on login or logout.

In modern Spring Security versions, standard authentication filters are configured to save the context when needed. You **do not need** to add a custom POST /login controller or manually call `repository.saveContext` after default form login.

### 10.5. DemoController.java

~~~java
package com.example.contextdemo;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/me")
    public Map<String, Object> me(
            Authentication authentication,
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);

        return Map.of(
            "username", authentication.getName(),
            "authenticated", authentication.isAuthenticated(),
            "sessionPresent", session != null
        );
    }
}
~~~

Observations on **/me**:

- **username** comes from the Authentication loaded/restored by Spring Security in this request.
- **authenticated** reports the active Authentication's flag state. Inside this protected endpoint, only valid form login can pass the `authenticated()` requirement.
- **sessionPresent** merely indicates whether an HttpSession exists when the controller runs; it does not return the session ID or sensitive cookies. **A `true` value alone does not prove the user is authenticated**, as a session can exist prior to login.

### 10.6. Starting Up and Observing in a Browser

In the `context-repository-demo` directory:

~~~bash
mvn spring-boot:run
~~~

Open sequentially:

1. **http://localhost:8080/public**: public endpoint returns HTTP **200** and JSON with `message = "public-ok"`.
2. **http://localhost:8080/me** while not logged in: per formLogin configuration, the browser is typically **302 redirected** to `/login`.
3. On the Spring Security-generated `/login` page, enter username **learner** and password **password123**, then submit the form. The framework verifies credentials, establishes Authentication, saves SecurityContext, and redirects to the requested page or appropriate URL.
4. Open **http://localhost:8080/me** again in the **same browser** and **same session**. You will see HTTP **200**, `username = "learner"`, `authenticated = true`, and `sessionPresent = true`.
5. Open a new private window that does not share the same session and visit `/me`: you will have to log in again. This shows that the previous browser's context does not leak to another browser.
6. Visit **/logout** and complete logout using the form carrying the CSRF token (if a confirmation page is shown). Once the session is invalidated/context cleared, `/me` requires login again.

Example successful `/me` payload **values** (JSON key order may vary):

~~~json
{
  "username": "learner",
  "authenticated": true,
  "sessionPresent": true
}
~~~

Do not think the server "remembers" the typed password: in the standard flow, the HTTP session holds the context representing the authenticated identity, while the raw password does not need to be retained. Cookie/session names and lifetimes depend on container, Spring Security, and application configuration.

### 10.7. Automated Testing with MockMvc

To avoid relying solely on browser state, add **src/test/java/com/example/contextdemo/ContextRepositoryTest.java**:

~~~java
package com.example.contextdemo;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class ContextRepositoryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void formLoginPersistsAuthenticationAcrossRequests() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("learner").password("password123"))
            .andExpect(authenticated().withUsername("learner"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authenticated").value(true))
            .andExpect(jsonPath("$.sessionPresent").value(true));
    }

    @Test
    void newRequestWithoutSessionMustAuthenticateAgain() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Run in the project directory:

~~~bash
mvn test
~~~

The two tests verify **the difference between a request reusing a session and a request without a session**. In the first test, `formLogin()` from `spring-security-test` performs a test login request; the resulting `MockHttpSession` is attached to the subsequent `GET /me`. In the second test, `GET /me` from a client without a session is redirected to log in.

If you change the repository configuration to `NullSecurityContextRepository`, the session persistence test will no longer yield the same result; try comparing them after understanding the stateless policy in the next section.

## 11. Contrast Example: Stateless API Not Using HttpSession to Restore Context

For comparison, **replace** the SecurityFilterChain method in section 10 with the configuration below; this is a separate variant—do not register two chains with the same matcher simultaneously without explicit ordering.

~~~java
@Bean
SecurityFilterChain statelessSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .sessionManagement(session ->
            session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .securityContext(context ->
            context.securityContextRepository(new NullSecurityContextRepository()))
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/public").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .formLogin(AbstractHttpConfigurer::disable);

    return http.build();
}
~~~

This is a **bean-method replacement fragment**, requiring imports for `SessionCreationPolicy`, `NullSecurityContextRepository`, `AbstractHttpConfigurer`, `SecurityFilterChain`, `HttpSecurity`, `Customizer`, and `@Bean`. The **UserDetailsService/PasswordEncoder** beans from the previous example remain in use.

Differences:

- **STATELESS** tells Spring Security not to use a session to retrieve context.
- **NullSecurityContextRepository** does not persist Authentication to the next request.
- **HTTP Basic** allows each request to supply credentials via the Authorization header.
- **formLogin(disable)** removes form-based login; requests to `/me` lacking Basic credentials receive HTTP **401**.
- **CSRF is not automatically disabled** just because this code uses STATELESS. The example tests only GET requests, so no CSRF token is needed. When building state-changing endpoints, evaluate CSRF risks based on how clients send credentials; browsers may automatically resend cached HTTP Basic credentials.

After adding imports and restarting the application, invoke:

~~~bash
curl -i -u learner:password123 http://localhost:8080/me
curl -i http://localhost:8080/me
~~~

Expected results:

| Request | HTTP status | Observation |
| --- | --- | --- |
| GET `/me` with valid HTTP Basic | **200** | `username = learner`; this request holds Authentication |
| Subsequent GET `/me` without credentials | **401** | No login persisted from the previous request |

In a purely stateless test configuration, `sessionPresent` on a successful request is typically false if no other component creates a session. **Do not treat that flag as the sole test**; the key observation is that a subsequent unauthenticated request gets 401.

HTTP Basic is not a "password encryption" mechanism: it Base64-encodes credentials and **requires HTTPS in real environments**. For production APIs, bearer tokens are typically handled via OAuth2 Resource Server rather than hand-rolled session/token logic.

## 12. When Building Custom Authentication: Explicit saveContext

Consider a **custom** login endpoint or filter (not using the standard `formLogin` filter). After successful authentication, you want to save the context so the next request reuses the session.

Core sequence:

~~~java
// Illustrative fragment inside a handler that already has authenticationManager,
// securityContextRepository, request, and response.
// This is not a standalone Java class.

Authentication verified = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password));

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);

SecurityContextHolder.setContext(context);

// Explicitly save to the repository configured for the security chain.
securityContextRepository.saveContext(context, request, response);
~~~

To compile this fragment inside an appropriate handler, import `Authentication`, `UsernamePasswordAuthenticationToken`, `SecurityContext`, `SecurityContextHolder`, and the dependency types. **`username`/`password` are only input variables**, which must come from a secure authentication flow with input validation and CSRF protection; never drop this directly into a public production endpoint as-is.

Step-by-step explanation:

1. **AuthenticationManager.authenticate(...)** checks credentials; use only the **verified** result.
2. **createEmptyContext()** creates a fresh SecurityContext. Avoid mutating a potentially shared context unless you understand its lifecycle; a fresh context prevents unintended side effects.
3. **setAuthentication(verified)** gives the context the valid identity.
4. **SecurityContextHolder.setContext(context)** makes the identity visible to code in the current request.
5. **securityContextRepository.saveContext(...)** persists according to the repository's policy (e.g., HttpSession) so subsequent requests can reload it.

If step 5 is omitted when using SecurityContextHolderFilter with explicit save, the current request sees the user, but the next request **does not recover the context**. With NullSecurityContextRepository, `saveContext` is a no-op for cross-request persistence; switch to a session repository and matching session policy if persisting login is the goal.

**Never** set Authentication with `authenticated=true` solely because the client sent a username; it must go through credential verification. A real login endpoint also needs failure handling, CSRF protection, brute-force defenses, session fixation protection, secret-safe logging, and clear responses. Also ensure you use **the exact repository** that the SecurityFilterChain loads on the next request, rather than saving to one place and loading from another.

### Why Not Call `request.getSession().setAttribute(...)` Arbitrarily?

Manually writing a username string or an Authentication object with the wrong schema into the session **does not substitute for saveContext**. SecurityContextRepository has its own contract for context wrapping, change detection, and filter-chain coordination. Use the official abstraction to avoid attribute-name mismatches, consistency bugs, and version-upgrade breakage.

## 13. Context, Anonymous, and Access Control

When a request is unauthenticated, **AnonymousAuthenticationFilter** may place an `AnonymousAuthenticationToken` into SecurityContextHolder so downstream components handle requests uniformly.

That does not mean the repository found a valid login. **`AnonymousAuthenticationToken.isAuthenticated()` can return `true`**, yet Spring Security still treats it as anonymous for **`authenticated()`** rules via `AuthenticationTrustResolver`.

If writing manual identity-checking code, avoid using just:

~~~java
boolean loggedIn =
    SecurityContextHolder.getContext()
        .getAuthentication()
        .isAuthenticated();
~~~

This snippet can also throw `NullPointerException` when no Authentication is present, and fails to distinguish anonymous tokens properly. Prefer **`authorizeHttpRequests(...authenticated())`**, `@PreAuthorize`, or official authentication/authorization mechanisms; when manual inspection is required, use `AuthenticationTrustResolver` or explicitly check the Authentication type and null.

The repository decides **where the context comes from**, while authorization decides **what that identity may do**. Having a session containing a valid Authentication does not automatically grant access to every order, tenant, or action.

## 14. Session Security and Production Operations

When choosing HttpSessionSecurityContextRepository, apply these additional principles:

**Session fixation protection.** After login, Spring Security normally rotates the session ID via an appropriate strategy to mitigate session fixation risks. Do not bypass this flow with untested custom login handlers.

**Cookie flags.** Use HTTPS and evaluate `Secure`/`HttpOnly`/`SameSite` along with proper cookie policies. Cookies help browsers reference sessions; protecting cookies is part of protecting identity.

**CSRF.** Browsers automatically attach session cookies on matching requests, so applications using cookie-based authentication must manage CSRF for state-changing operations. Using or omitting SecurityContextRepository does not automatically eliminate CSRF risks.

**Logout.** Clearing Authentication from the holder without invalidating the session/clearing the repository can cause the old context to reappear on the next request. Use Spring Security's logout support or ensure context and session are handled consistently.

**Session timeout.** When a session expires or is invalidated, HttpSessionSecurityContextRepository no longer has an old context to load; the user must re-authenticate per policy.

**Multiple nodes.** If requests can hit multiple application instances, manage distributed sessions or sticky sessions per architecture. DelegatingSecurityContextRepository does not share HttpSession across machines by itself.

**Serialization.** If sessions are replicated/serialized, objects inside the context may need to be compatible with the session store's serialization. Avoid storing large, unnecessary, or unprotected sensitive data inside the principal.

**Thread safety and async.** Context in the holder does not automatically follow tasks outside the request thread. With `@Async` or thread pools, use controlled SecurityContext propagation; never set the GLOBAL strategy to "fix" missing identity, as it can mix users.

**SessionCreationPolicy is not authorization.** Regardless of policy, always verify credentials and authorize requests, methods, and data properly.

## 15. Troubleshooting Common Issues

| Symptom | Common cause | Where to check |
| --- | --- | --- |
| Login returns redirect successfully, but next request is anonymous | Context bound only to request, custom login forgot `saveContext`, or session cookie was not sent | Check active repository, save/load logs, `Set-Cookie`/`Cookie`, redirect timing |
| Next request loses Authentication despite saving | Saved to Null/RequestAttribute repo while expecting session, or loaded via a different repo | Check which SecurityContextRepository is actually used on both requests |
| GET after login returns 401/302 despite cookie | Cookie/session expired, wrong domain/path, or server cannot find session | Check cookie settings, session store, load balancer, and logout |
| User "remembers" login despite expecting stateless | Chain lacks STATELESS or browser still sends credentials | Verify chain matcher, session policy, Authorization headers/cookies per request |
| Error page request has no Authentication | Holder cleared between dispatchers; missing request-attribute delegate | Check RequestAttributeSecurityContextRepository and ERROR dispatch config |
| HttpSession exists, yet `/me` has no user | Session has no valid SecurityContext; session was created for another reason | Do not treat `sessionPresent` as proof of authentication |
| New thread cannot read Authentication | ThreadLocal does not auto-propagate across thread pools/async | Use DelegatingSecurityContextExecutor or security async integration |
| Context is anonymous yet `isAuthenticated()` is true | `AnonymousAuthenticationToken` can mark authenticated | Use `authenticated()` rule or `AuthenticationTrustResolver` |
| Wrote to session manually, but Spring does not reload it | Bypassed SecurityContextRepository contract or used wrong attribute | Use official `saveContext` |
| Form login works, but POST requests fail with 403 | Missing CSRF token, not necessarily a repository issue | Check CSRF token, form/endpoint, origin, and policy |
| Multiple chains behave differently | First matching chain has a different repository/session policy | Check `securityMatcher`, `@Order`, and repo assigned to each chain |

### Repeatable Debugging Workflow

1. **Identify which SecurityFilterChain the request enters**; do not guess from URL names. With multiple chains, the first matching chain wins.
2. **Verify policy:** IF_REQUIRED/NEVER/STATELESS and the chain's actual repository configuration.
3. **Separate two milestones:** upon successful authentication, was Authentication set in the holder? Afterwards, was **saveContext** called before response commit?
4. **Observe the new request:** what cookie/token did the browser send? Is that session still valid? Did the repository reload the context?
5. **Distinguish repository from authorization:** is Authentication present? Does it have the expected authorities? Was the endpoint denied by auth, CSRF, or another rule?
6. **Check other scenarios:** error dispatch, logout, session timeout, node switching, async threads.
7. **Log safely:** log only request ID, timestamp, filter/chain, and high-level status; never log passwords, session IDs, cookies, tokens, or full sensitive principals.

## 16. Self-Practice Exercises

**Exercise 1 — Why isn't `setContext` enough?**  
You build a custom login handler using AuthenticationManager. The handler sets the context in SecurityContextHolder without calling `saveContext`, and the application uses SecurityContextHolderFilter. Explain why the login request sees the user while a subsequent `GET /me` loses the identity.

**Hint:** the holder manages the current request, while the repository manages storage; explicit save is required to reuse the context on subsequent requests.

**Exercise 2 — Choose a repository for each application.**  
(a) An MVC admin portal with form login preserving login across page navigations. (b) An API receiving a bearer token on every request. (c) Needing to recover Authentication on an error page within the same request.

**Hint:** (a) HttpSession, usually via Delegating. (b) Null/stateless when appropriately designed. (c) RequestAttribute, usually combined inside Delegating.

**Exercise 3 — Distinguish NEVER and STATELESS.**  
If the Servlet container or another component has already created an HttpSession, which policy can continue using that session, and which policy does not use HttpSession to load SecurityContext?

**Answer:** NEVER can use an existing session; STATELESS does not use HttpSession to obtain SecurityContext.

**Exercise 4 — Two-request test.**  
In the section 10 example, log in with MockMvc and perform `GET /me` with the obtained session. Then perform `GET /me` without passing a session. Why do the two requests yield different results?

**Answer:** the first request loads the context stored in the session; the second lacks the corresponding login session and is challenged to authenticate again.

**Exercise 5 — Anonymous Authentication.**  
A code snippet checks `Authentication.isAuthenticated()` to decide whether to grant a user access to a sensitive feature. Point out two problems.

**Answer:** `Authentication` can be null, and `AnonymousAuthenticationToken` can return `isAuthenticated()` as true. Use Spring Security authorization or check identity via an appropriate contract.

**Exercise 6 — Multi-node login failure analysis.**  
An application stores context in HttpSession on node A. The same browser's next request hits node B and is treated as unauthenticated. Which repository suits web login? Why is `DelegatingSecurityContextRepository` alone not enough to fix this?

**Answer:** HttpSession/Delegating fits web login, but requires session persistence/sharing or proper routing across nodes. Delegating combines context stores within the same process/request and does not synchronize sessions across machines.

## 17. Pre-Implementation Decision Checklist

- [ ] Distinguished **current SecurityContextHolder** from **SecurityContextRepository used to load/save**.
- [ ] Chosen a browser session model or stateless API model based on actual requirements.
- [ ] Understood that **SecurityContextHolderFilter in Spring Security 6 does not auto-save at the end of a request**.
- [ ] For custom login, called **saveContext on the right repository before response commit**.
- [ ] For standard formLogin, let the framework manage login, CSRF, and context saving in its flow.
- [ ] If using HttpSession, verified cookies/session timeout/logout/session fixation.
- [ ] If using Null repository, ensured every authenticated request carries appropriate credentials.
- [ ] If using RequestAttribute, did not expect cross-request persistence to subsequent HTTP requests.
- [ ] If using Delegating, understood each delegate's limits and every security chain's configuration.
- [ ] Tested initial request, subsequent request, missing cookie/token, timeout, logout, and error dispatch where relevant.
- [ ] Avoided logging credentials, session cookies, access tokens, or full SecurityContext in production.
- [ ] Separated resource authorization checks from session storage mechanics.

**Conclusion:** SecurityContextHolder tracks identity during execution; SecurityContextRepository governs how identity associated with an HTTP request is loaded and saved. For web applications maintaining login state, HttpSession (typically via DelegatingSecurityContextRepository) is the common choice; RequestAttribute serves dispatches within one request; Null fits per-request independent authentication. In Spring Security 6, always clarify **who creates Authentication, when saveContext happens, and where the next request loads from**, then pick the strategy matching your session or stateless model.
