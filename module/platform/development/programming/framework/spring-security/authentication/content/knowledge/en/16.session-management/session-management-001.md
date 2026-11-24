# SessionCreationPolicy: ALWAYS, IF_REQUIRED, NEVER, and STATELESS

## Objectives and Scope

**SessionCreationPolicy** determines whether Spring Security Servlet proactively creates an **HttpSession** or uses an existing session when managing security state. This is a critical choice when building authentication with forms, JSON, HTTP Basic, API keys, or Bearer tokens.

After this lesson, you will be able to:

1. Accurately distinguish the four policies: **ALWAYS**, **IF_REQUIRED**, **NEVER**, and **STATELESS**.
2. Explain why **not creating a session** is different from **not using a session to restore SecurityContext**.
3. Connect SessionCreationPolicy with **HttpSession**, **JSESSIONID**, **SecurityContextHolder**, **SecurityContextRepository**, **RequestCache**, and authentication strategies.
4. Configure Spring Security Servlet using Java 17+ and verify session creation with real requests.
5. Choose the appropriate policy for stateful login or stateless APIs while avoiding misconceptions about CSRF, logout, and saving Authentication.

This lesson focuses on **Spring Security Servlet** (Spring Boot using Spring MVC/Jakarta Servlet). Spring Security WebFlux uses different context and session management components from the Reactive stack, so the Servlet enum and configuration below do not apply verbatim.

## 1. Four Concepts to Distinguish Before Choosing a Policy

### 1.1. What Is HttpSession?

**HttpSession** is a server-side session belonging to the Servlet API. It allows storing data associated with a client's communication session: session attributes, shopping carts, form state, or **SecurityContext** if the application is configured to do so.

Browsers typically hold a **JSESSIONID** cookie; when a subsequent request sends back a valid cookie, the Servlet container can look up the corresponding session.

- **Having an HttpSession** does not mean the user is logged in. An anonymous session can still contain a CSRF token or application data.
- **Not having an HttpSession** does not mean the request is unauthenticated. APIs accepting a Bearer token or HTTP Basic can authenticate independently on every request.
- **Having a JSESSIONID** does not guarantee that the session still exists or contains a valid Authentication: the session may have expired, been invalidated, or belong to another application.

### 1.2. SecurityContextHolder vs. HttpSession

**SecurityContextHolder** provides the **SecurityContext** for the current request-processing thread; inside it there is typically an authenticated **Authentication** or an anonymous state. It does not persist the identity for the next request by default.

**SecurityContextRepository** is the contract for reading/saving SecurityContext across requests:

- **HttpSessionSecurityContextRepository** can use HttpSession to store and restore the context.
- **RequestAttributeSecurityContextRepository** keeps the context within the scope of a request, which is useful when a request goes through multiple dispatches such as ERROR.
- **DelegatingSecurityContextRepository** can coordinate multiple repositories; Spring Security 6 uses this form in its default stateful configuration.
- **NullSecurityContextRepository** does not save the context for subsequent requests and does not read the session to restore Authentication.

**SessionCreationPolicy** is an important input when Spring Security chooses how to use sessions and context repositories, but it does not replace the entire repository, filter, or authentication mechanism configuration.

### 1.3. Who Can Create a Session?

Not only Spring Security: **the Servlet container, Spring MVC, RequestCache, CSRF token repository, other libraries, and application code** can create or use an HttpSession.

Therefore, you need to distinguish three questions:

1. **Does Spring Security proactively create an HttpSession?**
2. **Does Spring Security use an existing HttpSession to restore SecurityContext?**
3. **Does any other component of the application create an HttpSession?**

A real-world project can answer differently for all three. Never deduce one answer solely from another.

## 2. Exact Comparison Table of the Four SessionCreationPolicy Values

The enum resides at:

~~~java
org.springframework.security.config.http.SessionCreationPolicy
~~~

Four values:

| Policy | Does Spring Security proactively create HttpSession? | Can it use an existing HttpSession for SecurityContext? | Characteristic |
| --- | --- | --- | --- |
| **ALWAYS** | **Yes**: requests session creation when starting a request without a session | **Yes**, per configured repository | Favors eagerly created sessions |
| **IF_REQUIRED** | **Only when required** | **Yes**, per configured repository | Flexible, common stateful policy |
| **NEVER** | **Does not proactively create** under this policy | **Yes** | Reuses existing sessions; not equivalent to stateless |
| **STATELESS** | **No** for security management purposes | **No**, does not use HttpSession to obtain SecurityContext | Independent per-request authentication, suitable for stateless APIs |

**Core statements from the enum's contract:**

- **ALWAYS:** always create an HttpSession.
- **IF_REQUIRED:** Spring Security only creates an HttpSession if required.
- **NEVER:** Spring Security never proactively creates an HttpSession, but it may still use an existing HttpSession.
- **STATELESS:** Spring Security never creates an HttpSession and never uses it to obtain the SecurityContext.

There are two points that must be phrased carefully:

**First, NEVER is not STATELESS.** Both may look similar when a new client has no session yet, but when a valid session already exists and contains a SecurityContext, the Authentication restoration behavior can differ.

**Second, STATELESS does not forbid application code from calling request.getSession(true).** It prevents Spring Security from using a session to restore SecurityContext under the corresponding configuration model; application code or other components can still create a session themselves. You cannot claim "the server will never issue JSESSIONID" just because STATELESS is selected.

## 3. Understanding Each Policy Through Request Flows

### 3.1. ALWAYS — proactively creating a session

~~~text
GET /public, browser has no JSESSIONID yet
       |
       v
Spring Security with ALWAYS
       |
       +--> ensures an HttpSession exists
       |
       v
Controller processes the request
       |
       v
Response may include Set-Cookie: JSESSIONID=...
~~~

Spring Security has an eager session creation mechanism, such as **ForceEagerSessionCreationFilter**, when this policy is configured.

**Key takeaways:**

- A request to a **permitAll()** endpoint can still create an HttpSession, even without logging in.
- "ALWAYS" does **not** mean **every request creates a brand-new session** if a valid session already exists. It means the mechanism tries to ensure the request has a session.
- A created session does not automatically contain an authenticated user. **Creating an HttpSession** and **saving an Authentication** are two separate operations.
- There is overhead for session management, memory, cookies, and potentially session sharing when scaling across multiple instances.

**Suitable** when the application explicitly requires an early session, such as a traditional web flow relying on server-side sessions. Do not choose ALWAYS just to "make sure users can log in" if there is no need to create a session for every request.

### 3.2. IF_REQUIRED — creating a session only when needed

~~~text
GET /public
  -> If no component needs an HttpSession: may not create one

GET /login or POST /login in a session-based flow
  -> Security/application components may need an HttpSession
  -> Session is created when needed to store context, CSRF token,
     saved request, or other data depending on configuration
~~~

**IF_REQUIRED** does not mean "every request has a session." It allows Spring Security to use a session when required instead of creating one eagerly.

In stateful configurations, this is usually the practical choice for form login or JSON login with a session cookie: unauthenticated visitors may not need a session yet, while a successful login can create a session to store the SecurityContext.

However, merely having the IF_REQUIRED policy **does not automatically save** an Authentication created in a custom controller. In Spring Security 6, custom authentication code must explicitly call **SecurityContextRepository.saveContext(...)** if you want to persist the login across requests.

### 3.3. NEVER — never proactively creates, but can use an existing session

~~~text
Client A: no HttpSession yet
  -> Spring Security does not proactively create a session due to NEVER policy

Client B: already has a valid JSESSIONID
  -> Can restore SecurityContext from the existing HttpSession
     if the current repository and mechanism allow it
~~~

This is the most frequently misunderstood policy.

- **NEVER** does not mean disabling all HttpSessions.
- If another component created a session earlier, Spring Security can use it.
- Some components such as **RequestCache** can still save requests for post-login processing and inadvertently cause you to observe a session. The Spring Security documentation specifically warns about this case.
- If you need to ensure Authentication is never restored from an HttpSession, choose **STATELESS** instead of NEVER and verify the repository.

**Scenario:** an application has an existing session created by a web UI or another module. You choose NEVER for a security chain. An existing SecurityContext can be read back, so a request may still be authenticated **even without sending a new credential header**. Do not conclude this is a bug based solely on the name "NEVER".

### 3.4. STATELESS — does not restore Authentication from session

~~~text
GET /api/me
Authorization: Bearer <valid token>
     |
     v
Token authentication filter for this request
     |
     v
SecurityContextHolder in this request
     |
     v
Authorization -> Controller -> Response
     |
     v
Next request must provide credentials on its own
~~~

With an appropriate default configuration, **STATELESS** causes Spring Security not to obtain SecurityContext from HttpSession, and typically uses **NullSecurityContextRepository** along with avoiding saving unauthenticated requests into the session.

Notes:

- **STATELESS does not mean there is no SecurityContextHolder.** The current request still has a context after the authentication filter succeeds.
- **STATELESS does not authenticate the client by itself.** You still need Basic, Bearer, API key, or an appropriate mechanism.
- **STATELESS does not mean there are no cookies anywhere in the system.** Other application components can still issue cookies/sessions.
- **STATELESS does not mean immune to CSRF.** If the browser automatically sends Basic credentials or other cookies to the server, CSRF must still be evaluated based on how the client operates.
- **STATELESS does not provide an "invalidate HttpSession" logout button** for self-contained Bearer tokens; token revocation depends on issuance mechanisms, expiration, and blacklist/revocation if implemented.

This policy fits **REST APIs using an Authorization header on every request**, especially Bearer tokens or API keys, when the server does not want to use sessions to maintain Authentication.

## 4. Where Exactly Do NEVER and STATELESS Differ?

Suppose the Servlet container already has a valid session before the request is passed through Spring Security.

| Scenario | NEVER | STATELESS |
| --- | --- | --- |
| Client has no session | Does not proactively create a session under policy | Does not proactively create a session for security context |
| Client has an old JSESSIONID | Can use the old session | Does not use the old session to obtain SecurityContext |
| Session contains a validly saved Authentication | Can restore per repository | Does not restore from session under stateless configuration |
| Controller code calls request.getSession(true) | Application code can still create one | Application code can still create one |
| Client only sends JSESSIONID without Authorization header | May be authenticated if context is stored in session | Not authenticated **solely via HttpSession context** |
| Typical use case | Application reuses an existing session and wants to limit creating new ones | API that does not keep server-side authentication state |

**Observable example:**

1. A trusted login flow stores Authentication for user "alice" in HttpSession.
2. The client holds that session's JSESSIONID cookie.
3. The client calls a protected resource without sending a Bearer/Basic header.

If the chain uses **NEVER** with a repository that reads HttpSession, it can retrieve the "alice" Authentication. If the chain uses **STATELESS** and does not override the repository against the policy, the context in the old session **is not used** to authenticate the request.

Distinguish "may" from "definitely": the outcome depends on **SecurityContextRepository**, other authentication filters, whether the session is still valid, which chain matches the URL, and whether other session/cookie mechanisms exist.

## 5. Configuring SessionCreationPolicy in Spring Security Servlet

How to use the DSL for a SecurityFilterChain:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    );
    return http.build();
}
~~~

Imports:

~~~java
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
~~~

Change **SessionCreationPolicy.STATELESS** to **ALWAYS**, **IF_REQUIRED**, or **NEVER** to select another strategy. The configuration applies specifically to the **SecurityFilterChain** containing it.

### When There Are Multiple SecurityFilterChains

For example, a system has a browser UI with session-based login and a REST API with Bearer tokens. The design can split them:

~~~java
// Illustrative two-chain configuration snippet, not a standalone application.
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .sessionManagement(sm -> sm
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    // Add the specific Bearer/API-key mechanism here.
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http
        .sessionManagement(sm -> sm
            .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

This snippet requires importing **@Bean, @Order, Customizer** and fully configuring the authentication mechanism for the API. It illustrates **choosing a policy per chain**, not a standalone runnable project.

Note especially: the JSESSIONID cookie created by the web UI may still be sent by the browser when calling **/api/**, but the STATELESS API chain will not use that cookie to restore SecurityContext. In hybrid applications, test **matchers, chain ordering, CSRF, CORS, cookie paths, and authorization**. Do not infer the entire application's policy from a single bean.

## 6. Runnable Java 17+ Example: Verifying the Four Policies

We will create a small Spring Boot Servlet application that allows choosing the policy via a startup parameter. The example is solely for observing when a session is created; the authentication mechanism is HTTP Basic.

**Important point:** HTTP Basic normally authenticates credentials on every request and does not automatically become a login session. Therefore, calling **/me** with valid Basic credentials does not prove that SecurityContext was saved in HttpSession. Do not confuse the "sessionExists" measurement with "logged in".

### 6.1. Gradle project

Requires **JDK 17+**, Gradle compatible with Spring Boot 3.5.x. Create **settings.gradle**:

~~~groovy
rootProject.name = 'session-policy-demo'
~~~

Create **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

The Spring Boot plugin manages the classpath and dependencies for the example; a standalone Java file cannot be compiled and run with **javac** alone without the Spring libraries.

### 6.2. Application

Create the file **src/main/java/example/session/SessionPolicyDemoApplication.java**:

~~~java
package example.session;

import java.util.Locale;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionPolicyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionPolicyDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, Environment environment) throws Exception {

        String configured = environment.getProperty(
            "demo.session-policy", "IF_REQUIRED"
        );
        SessionCreationPolicy policy = SessionCreationPolicy.valueOf(
            configured.trim().toUpperCase(Locale.ROOT)
        );

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/probe",
                    "/demo/create-session"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .requestCache(cache -> cache.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(policy)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwordEncoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(passwordEncoder.encode("change-me"))
                .roles("READER")
                .build()
        );
    }

    @RestController
    static class Api {

        public record Probe(boolean sessionExists) {
        }

        @GetMapping("/probe")
        Probe probe(HttpServletRequest request) {
            // false => DO NOT auto-create a session when probing.
            HttpSession session = request.getSession(false);
            return new Probe(session != null);
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "hello, " + authentication.getName();
        }

        @GetMapping("/demo/create-session")
        String createSession(HttpServletRequest request) {
            // Only to prove that the APPLICATION can create a session itself.
            // Do not deploy a state-creating GET endpoint to production.
            request.getSession(true).setAttribute("demo", "created");
            return "application-created-session";
        }
    }
}
~~~

**Explanation of choices in the example:**

1. **/probe** uses **request.getSession(false)**. This is crucial: if you use **getSession()** or **getSession(true)** while probing, the controller itself creates a session, leading you to draw the wrong conclusion about the policy.
2. **/demo/create-session** intentionally calls **getSession(true)** to prove that application code can still create an HttpSession under all four policies. This endpoint is for learning environments only and should be removed in production; state-creating GET requests are not ideal HTTP design.
3. **/me** requires a request with a valid Authentication; in the example, the client can send **Authorization: Basic** each time.
4. **requestCache.disable()** prevents saved requests from the security mechanism from skewing the session measurement. The application does not use form login or post-login redirects.
5. Do not disable **CSRF** arbitrarily. The demo endpoints here are GET requests and perform no business state-updating actions. In a real system using browsers/cookies, CSRF must be evaluated separately.
6. User **demo/change-me** is only for local testing; do not embed real credentials in source code.

### 6.3. Running and Observing

From the project directory containing the Gradle wrapper:

~~~bash
./gradlew bootRun --args='--demo.session-policy=ALWAYS'
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--demo.session-policy=ALWAYS"
~~~

By default the server listens on **http://localhost:8080** unless another port is configured. Stop the app and change the argument to **IF_REQUIRED**, **NEVER**, and **STATELESS** to test each in turn, using a fresh cookie session for each test.

**A. Observe the first anonymous request:**

~~~bash
curl -i http://localhost:8080/probe
~~~

In a clean example environment, with no cookie sent and no external component creating a session, the expected body is:

| Running app policy | /probe body on first request |
| --- | --- |
| ALWAYS | **{"sessionExists":true}** |
| IF_REQUIRED | **{"sessionExists":false}** |
| NEVER | **{"sessionExists":false}** |
| STATELESS | **{"sessionExists":false}** |

With **ALWAYS**, the response may also include a **Set-Cookie: JSESSIONID=...** header when creating a new session. The exact cookie, headers, and display order depend on the Servlet container/configuration. Do not infer "no session exists" simply from not seeing a cookie: the **/probe** endpoint reports the actual session presence during the request.

**B. Basic authenticates a request but does not prove a login session exists:**

~~~bash
curl -sS -u demo:change-me http://localhost:8080/me
# hello, demo

curl -i http://localhost:8080/me
# HTTP/1.1 401 ... (typical status when credentials are missing)
~~~

These are two separate requests. In this illustrative configuration, Basic serves per-request authentication; the example does not add configuration to save the Basic filter's Authentication into HttpSession. **IF_REQUIRED** or **ALWAYS** alone does not turn Basic into "log in once, subsequent requests only need a cookie."

**C. Prove that a session created by application code can exist even under STATELESS:**

~~~bash
curl -i -c demo-cookies.txt \
  http://localhost:8080/demo/create-session

curl -sS -b demo-cookies.txt http://localhost:8080/probe
# {"sessionExists":true}
~~~

The **demo-cookies.txt** cookie jar stores the JSESSIONID issued by the Servlet container for the session-creating endpoint. When the next request brings back the valid cookie, the controller sees an HttpSession.

If running **STATELESS**, the result above **does not violate the policy**: the application intentionally created a session itself. What matters is that Spring Security **does not use that session to restore SecurityContext** under the default stateless configuration. Merely having a session does not mean Authentication exists.

**D. Do not let cookies from a previous test contaminate a new test.** When switching policies, run /probe with a request that **sends no Cookie**, or use a separate cookie jar for each policy. If you reuse an old cookie, you may accidentally measure an already-existing session.

### 6.4. What the Demo Proves and Does Not Prove

What the demo directly observes:

- ALWAYS proactively creates a session on a request that does not yet have one.
- IF_REQUIRED/NEVER/STATELESS do not need to create a session for /probe in this simple configuration.
- Application code can create a session itself under any policy.
- Authentication via Basic does not inherently depend on HttpSession.

The demo **does not prove** how an Authentication is saved to or restored from a session, because it does not implement a login mechanism that writes SecurityContext. Verifying that requires adding session-backed form/JSON login with an appropriate repository, and testing multiple requests with cookies.

## 7. SecurityContextRepository and Saving Authentication in Spring Security 6

### 7.1. Why Is a Policy Alone Not Enough to "Log In Once"?

A custom login flow typically goes through:

~~~text
POST /login
  -> AuthenticationManager verifies credentials
  -> (if using sessions) SessionAuthenticationStrategy checks,
     protects against session fixation and enforces session policy
  -> creates a SecurityContext containing the successful Authentication
  -> SecurityContextHolder uses it in the current request
  -> SecurityContextRepository.saveContext(...) for later restoration
  -> Response + appropriate cookie
~~~

In Spring Security 6, **SecurityContextHolderFilter** typically reads the context from the repository and sets it for the request; it **does not automatically save** changes you place in the holder yourself. **SecurityContextPersistenceFilter** and **SessionManagementFilter** are not enabled by default the way they were in Spring Security 5.

With a **custom controller/filter**, if you want to use HttpSession to preserve login state, ensure:

1. Choose an appropriate policy, usually **IF_REQUIRED**.
2. Have a repository that reads/saves via session, such as **HttpSessionSecurityContextRepository**.
3. After **AuthenticationManager.authenticate(...)** succeeds, invoke **SessionAuthenticationStrategy** when the session mechanism requires it, especially for session fixation protection or concurrent sessions.
4. Create a new SecurityContext, set the authenticated Authentication, and call **repository.saveContext(context, request, response)**.
5. Subsequent requests send back the valid session cookie, and the filter reads from the same repository.

The following snippet illustrates **the save step after authentication**, inside a custom authentication mechanism with all dependencies prepared; it is not a standalone application:

~~~java
// authentication is a valid result from AuthenticationManager.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

// Same repository that SecurityFilterChain uses to read it back.
securityContextRepository.saveContext(context, request, response);
~~~

**Do not use this snippet to try to turn a STATELESS configuration into a session-based login.** If you override the repository to persist state, the entire architecture must consistently align with a truly stateful choice.

### 7.2. Watch Out for RequestCache

**RequestCache** can save the URL of a rejected request so the user is redirected back after logging in. The **HttpSessionRequestCache** implementation can use HttpSession for the saved request.

Therefore, in an application using **NEVER**, you may still observe an HttpSession being created due to a saved request, depending on the configuration and related mechanisms. If an API only returns JSON and does not need to redirect back to the pre-login request, you can disable request caching:

~~~java
http.requestCache(cache -> cache.disable());
~~~

Or configure **NullRequestCache** as needed. When diagnosing unexpected sessions, do not check only SessionCreationPolicy; also inspect the request cache, CSRF token repository, views/templates, controllers, and other libraries.

### 7.3. Watch Out for CSRF Tokens and Sessions

**HttpSessionCsrfTokenRepository** can store the CSRF token in the session. Accessing or saving the CSRF token can trigger HttpSession creation, depending on the repository and how the request is handled.

If the application authenticates via cookies or the browser can automatically send credentials (including cached HTTP Basic), CSRF risk must be evaluated. **STATELESS does not automatically exempt you from CSRF.**

For Bearer-token APIs sent **explicitly via the Authorization header** from non-browser clients, or mechanisms that do not auto-attach credentials, you can choose the corresponding CSRF configuration after analyzing the threat model. Do not disable CSRF just because an endpoint path contains "/api".

## 8. Choosing a Policy by Application Scenario

| Application | Usually suitable policy | Accompanying conditions |
| --- | --- | --- |
| Web MVC with form login, session kept via JSESSIONID | **IF_REQUIRED** | Context save/load repository, CSRF, session fixation, and logout are configured |
| JSON login in browser, then using session cookie | **IF_REQUIRED** | Custom login must explicitly save SecurityContext and handle SessionAuthenticationStrategy |
| Application needs HttpSession created before login | **ALWAYS** | Clear justification for per-client/request session cost |
| Project integrating with a session already created by another component | **NEVER** may fit | Accepts restoring SecurityContext from existing session; check repository and request cache |
| API authenticating via Bearer JWT or opaque token per request | **STATELESS** | Has authentication filter/resource server; handles expiry, signature/introspection, revocation |
| API key or HTTP Basic on every request | **STATELESS** usually fits | TLS, credential management, does not rely on session cookie to store Authentication |
| Hybrid web + API application | **Split chains:** web IF_REQUIRED, API STATELESS | Clear security matchers, chain ordering, CSRF/CORS/cookies |

This table is a design guide, **not a substitute for requirements analysis**. An inherently stateless mechanism like Basic can still be configured to store Authentication in a session, but that is a separate decision requiring specific testing.

## 9. Common Misinterpretations

### Mistake 1: "NEVER is stateless"

False. NEVER does not proactively create a session under its policy, yet it can use an existing session, including a validly stored SecurityContext. If the goal is not to rely on HttpSession to identify the user, choose STATELESS.

### Mistake 2: "STATELESS means there will never be a JSESSIONID"

False. Servlet code or a CSRF repository/other component can still create a session. STATELESS controls how Spring Security uses a session for the security context, not a system-wide block on every **getSession(true)** call.

### Mistake 3: "ALWAYS means the user is logged in"

False. An HttpSession can be completely anonymous. You need a valid, properly restored Authentication; a session cookie alone is not enough.

### Mistake 4: "IF_REQUIRED automatically saves Authentication when I call setContext"

False in Spring Security 6's explicit-save model. A custom controller/filter must explicitly call **SecurityContextRepository.saveContext(...)** if you want persistence across the next request.

### Mistake 5: "An HttpSession just appeared, so it must be caused by sessionManagement()"

Insufficient evidence. Check **RequestCache**, CSRF, form login, controllers calling getSession(), the servlet framework, and other libraries. Do not look only at Set-Cookie.

### Mistake 6: "Using Basic, a subsequent request without Authorization should still be logged in because IF_REQUIRED is set"

Not true as a default guarantee. Basic typically authenticates every request; to store Basic Authentication in a session requires configuring the appropriate repository/lifecycle for that filter.

### Mistake 7: "I enabled STATELESS, so there is no SecurityContextHolder"

False. The filter still populates Authentication for the current request. What is prevented is relying on HttpSession to restore Authentication in a new request.

### Mistake 8: "STATELESS allows disabling CSRF in all cases"

False. If the browser automatically sends credentials such as Basic or cookies, a CSRF vector still exists. The decision depends on the client, origin, authentication method, and state-changing resources.

### Mistake 9: "I defined multiple SecurityFilterChains, so one policy applies system-wide"

False. Each chain has its own configuration; only requests matching a chain go through that chain's filters and context policy. For multi-chain applications, test matchers and ordering.

### Mistake 10: "SessionCreationPolicy replaces session fixation, logout, and concurrent session control"

False. Creating or not creating a session is one concern; changing the ID after login, session limits, invalidation, timeouts, and logout are separate responsibilities. Do not infer them from the policy alone.

### Mistake 11: "An old cookie exists, so I restored Authentication"

False. The cookie may point to an invalidated/expired session, an anonymous session, or a session without a SecurityContext; verify from the actual Authentication in the request.

### Mistake 12: "STATELESS automatically prevents all server-side state storage"

False. An API can still use databases, caches, rate limiters, blacklists/revocation, and business data. STATELESS refers to **HttpSession-based authentication state**, not a claim that the entire system has no state.

## 10. Practical Diagnostics and Testing Strategy

When inspecting an application, observe:

1. **First request**: is there a JSESSIONID cookie, and does a filter create a session before the controller?
2. **In the controller**: call **request.getSession(false)** to inspect without creating a new session.
3. **After authentication**: which mechanism sets the SecurityContext, and is it saved to the repository?
4. **Next request**: does the client send a cookie or an Authorization header; does Authentication come from the session or get re-authenticated?
5. **On 401/403 errors**: distinguish missing Authentication from being authenticated but lacking permissions.
6. **SavedRequest/CSRF**: does any component create a session indirectly?
7. **Multi-chain**: verify which SecurityFilterChain actually matches the URL, especially when web and API are separated.
8. **Session lifecycle**: expiration, session ID change after login, logout, session limits, and state sharing across multiple instances.

### Minimum Scenarios to Test

| Scenario | What to verify |
| --- | --- |
| Anonymous GET, no cookie, ALWAYS | HttpSession is created as designed |
| Anonymous GET, no cookie, IF_REQUIRED | Unnecessary session may not be created |
| Anonymous GET, no cookie, NEVER | Security does not proactively create a session |
| Anonymous GET, no cookie, STATELESS | Authentication is not restored from HttpSession |
| Request with old session containing valid context, NEVER | Authentication can be obtained from session per repository |
| Request with old session containing valid context, STATELESS | Context in session is not used as Authentication |
| Valid Bearer API call then new request missing token, STATELESS | New request does not inherit Authentication |
| Controller calls getSession(true) when policy is STATELESS | Session may still appear, but is not used to restore SecurityContext |
| JSON login with IF_REQUIRED but forgot saveContext | Login request may succeed, next request may lose Authentication |
| Logout/session timeout | Old cookie is no longer valid proof of login |

**QA Note:** do not write tests that merely call **SessionCreationPolicy.values()** and compare the four enum names; that test does not verify application behavior. Test real requests or **MockMvc** to observe sessions, SecurityContext, and HTTP behavior.

### When Using Spring Security Test

For projects with Spring Boot test dependencies, **MockMvc** can be used to check GET /probe and Authentication. However, session policies also interact with the servlet container and repositories. Real tests with curl, cookie jars, and a running server remain useful to catch cookie/Set-Cookie issues that mocks do not fully simulate.

For multi-instance applications, verify session replication or **Spring Session** if using stateful login, whereas stateless APIs must verify that every instance validates tokens and enforces revocation policies consistently. SessionCreationPolicy does not automatically implement cluster-wide session sharing.

## 11. Self-Check Exercises

**Question 1.** Both NEVER and STATELESS may avoid creating a session for a new request. What makes them different?

**Answer:** NEVER can still use an existing session to restore SecurityContext; STATELESS does not use HttpSession to restore SecurityContext.

**Question 2.** You choose ALWAYS, call /public, and see JSESSIONID. Is the user authenticated?

**Answer:** You cannot conclude that yet. An anonymous HttpSession can also exist; a valid Authentication is required.

**Question 3.** You choose IF_REQUIRED, a custom JSON controller authenticates successfully and sets SecurityContextHolder. The next request includes the cookie but still receives 401. Why?

**Answer:** It may not have called SecurityContextRepository.saveContext(...), or the repository used for saving does not match the repository read back by the security chain. Check the session strategy and chain.

**Question 4.** Someone says "STATELESS has absolutely no cookies, so seeing JSESSIONID is a Spring Security bug." Is that true?

**Answer:** No. Application code or other libraries can still create an HttpSession and cookies. What needs to be checked is whether Spring Security restores Authentication from HttpSession.

**Question 5.** The application uses an API Bearer token on every request and does not need a server-side login session. What should you choose?

**Answer:** Usually STATELESS along with a Bearer token verification mechanism. You still need to handle HTTPS, token errors, authorization, and CSRF per the threat model.

**Question 6.** NEVER still creates a session when accessing a URL that requires login. Where do you start debugging?

**Answer:** Inspect RequestCache storing saved requests, the CSRF token repository, controllers/filters calling getSession(true), the chain configuration, and components outside SessionManagement.

**Question 7.** Basic returns 200 on the first request with Authorization, while the second request without Authorization returns 401 despite IF_REQUIRED. Is this a policy bug?

**Answer:** Not necessarily. Basic does not imply a login session by default; check how the Basic filter persists SecurityContext and how the subsequent request behaves.

**Question 8.** Why shouldn't you use getSession(true) inside an endpoint that checks "does a session exist?"

**Answer:** Because the measurement itself creates a session. Use getSession(false) to check if a session already exists, and create a session intentionally in a separate step if you need to study that case.

## Official References

- [Spring Security 6.5 — SessionCreationPolicy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/http/SessionCreationPolicy.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Authentication Persistence](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Session Management Migration](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html)
- [Spring Security 6.5 — CSRF for Servlet Applications](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
