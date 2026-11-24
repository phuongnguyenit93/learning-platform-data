# Creating Authentication in Memory Does Not Automatically Persist Login for Subsequent Requests

## 1. Common issue: login succeeds, yet loading the next page becomes anonymous

Imagine a Spring Boot application with a POST /login endpoint. Upon receiving username and password, the developer calls AuthenticationManager.authenticate(...). The provider verifies the password and returns an authenticated Authentication. The developer creates a new SecurityContext, puts the Authentication inside, and sets it on SecurityContextHolder:

~~~java
Authentication verified = authenticationManager.authenticate(attempt);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

Within the current request, code reading SecurityContextHolder sees verified and isAuthenticated() is true. The endpoint returns 200 "Login successful".

Right afterward, however, the frontend calls GET /me in a new HTTP request and receives 401. This is **not necessarily a bug in PasswordEncoder, UserDetailsService, or AuthenticationManager**. The cause may simply be that the application only created **in-memory state for the current request**, without saving SecurityContext where the next request can retrieve it.

**Core thesis:**

> Successful authentication is distinct from placing Authentication into SecurityContextHolder, and both are distinct from **saving SecurityContext for retrieval on subsequent HTTP requests**.

In Spring Security Servlet 6.x, custom code wanting to maintain login across requests may need to call **SecurityContextRepository.saveContext(context, request, response)** explicitly. In addition, the browser must retain and resend the session cookie, the session must not have expired, the security chain must restore from the right repository, and the policy must not be configured as stateless.

This lesson uses **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. Examples apply only to the **Servlet stack** using HttpSecurity and HttpServletRequest; WebFlux requires ServerHttpSecurity and reactive context. A dedicated demo contrasts **setContext without saveContext** against **setContext plus saveContext**.

### After learning, you will

1. Distinguish Authentication, SecurityContext, SecurityContextHolder, SecurityContextRepository, and HttpSession.
2. Explain how the first request and subsequent request connect via a session cookie.
3. Understand Spring Security 6's default using SecurityContextHolderFilter and **explicit save**.
4. Distinguish HttpSessionSecurityContextRepository, RequestAttributeSecurityContextRepository, DelegatingSecurityContextRepository, and NullSecurityContextRepository.
5. Predict why current Authentication is valid yet the next GET /me returns 401.
6. Know when to call saveContext and why it must happen **before the response commits**.
7. Distinguish session-based form login from stateless HTTP Basic and Bearer/JWT.
8. Run a Java 17 Spring Boot example demonstrating the two contrasting behaviors.
9. Write MockMvc tests verifying two independent requests, with and without a session.
10. Spot errors in session policies, CSRF, session fixation, logout, cookies, multiple security chains, and async ThreadLocal.

## 2. Five objects not to conflate

| Concept | What is it? | Scope/lifecycle | What it does not do automatically |
| --- | --- | --- | --- |
| **Authentication** | Object representing identity, authorities, credentials, and authenticated state | Authentication data in code | Does not create a session or cookie by itself |
| **SecurityContext** | Object holding the current Authentication | Security context | Does not decide to save for the next request |
| **SecurityContextHolder** | API to access context for the current execution flow | Typically ThreadLocal in Servlet | Not long-term login storage |
| **SecurityContextRepository** | Mechanism to read/save context across request boundaries | Request attribute, HttpSession, or custom store | Does not verify passwords |
| **HttpSession + session cookie** | Associates browser with server-side session | Exists across HTTP requests when configured | A cookie does not imply the user is logged in |

### 2.1. Authentication is only a verification result

AuthenticationManager.authenticate(attempt) or an AuthenticationProvider can return a valid Authentication. That result is a Java object; if you merely hold it in a local variable and return a 200 response, the next request has no reason to know that local variable ever existed.

Having **authenticated=true** also does not indicate that Authentication was written to SecurityContextRepository. It only describes an object verified by a trusted provider.

### 2.2. SecurityContext and SecurityContextHolder

In Java Servlet, SecurityContextHolder defaults to **ThreadLocal**. A request processed on thread A can access thread A's context; when the request ends, the context-managing filter clears the holder to avoid leaking old identities into another request on a reused thread.

Therefore:

~~~java
SecurityContextHolder.getContext().setAuthentication(verified);
~~~

only operates on the active context. Beyond persistence, mutating an already-existing context can introduce shared-instance/concurrency risks in some cases. Spring Security docs recommend **creating a fresh SecurityContext** and placing Authentication inside it.

### 2.3. SecurityContextRepository is not PasswordEncoder

The repository does not verify passwords. It takes a context already properly built by a trusted authentication mechanism and stores it where it can be read back. In a session-based app, storage is usually **HttpSession**, looked up by the session ID the client sends via cookie.

If untrusted code constructs a context with role ADMIN without authentication, calling saveContext simply **persists a forged identity**. Persistence never replaces credential verification.

### 2.4. Having a JSESSIONID cookie does not prove login

An HttpSession can be created to hold a CSRF token, saved request, flash attribute, or other data even without any valid Authentication. **Session existence** is one thing; **session containing an authenticated SecurityContext** is another.

Conversely, when using stateless JWT/Bearer, a request can authenticate successfully **without any HttpSession**. Never treat cookie presence or absence as the sole authentication check.

## 3. Two timelines: current request and next request

### 3.1. Only setContext, no save

~~~text
Request #1: POST /lab/volatile, valid username/password
      |
      v
AuthenticationManager.authenticate()
      |
      v
Authentication verified
      |
      v
New SecurityContext -> setAuthentication(verified)
      |
      v
SecurityContextHolder.setContext(context)
      |
      v
Response 200: authenticatedNow=true
      |
      v
SecurityContextHolderFilter ends request, clears holder
      |
      |    DOES NOT call SecurityContextRepository.saveContext()
      v
Request #2: GET /me, even from same client
      |
      v
Repository has no context from previous login
      |
      v
Anonymous/unauthenticated -> HTTP 401 (per demo entry point)
~~~

Request #1 succeeds yet **does not create a login session usable in request #2**. A 200 response only means the current request finished processing; it does not promise the server persisted the identity.

### 3.2. setContext and saveContext

~~~text
Request #1: POST /lab/persist, valid username/password
      |
      v
AuthenticationManager.authenticate()
      |
      v
Authentication verified
      |
      v
Create SecurityContext -> setAuthentication(verified)
      |
      v
SecurityContextHolder.setContext(context)
      |
      v
SecurityContextRepository.saveContext(context, request, response)
      |
      v
HttpSession has SecurityContext; response can send Set-Cookie
      |
      v
Browser stores cookie and sends it back on Request #2
      |
      v
Request #2: GET /me + Cookie: JSESSIONID=...
      |
      v
SecurityContextHolderFilter reads repository
      |
      v
SecurityContext with saved Authentication
      |
      v
Authorization authenticated() lets it proceed
      |
      v
HTTP 200, authenticated user
~~~

If the client **does not send the cookie** or the server cannot resolve the session, GET /me can still return 401 even though the login request called saveContext.

### 3.3. Sufficient conditions for a session to stay active

For session-based authentication, at minimum all of the following are needed together:

1. Authentication was genuinely verified by a trusted source.
2. Context was placed into SecurityContextHolder for the current request to use.
3. Context was saved to a repository capable of persisting across HTTP requests.
4. Session/session identifier was sent to the client before the response committed.
5. Client retained and sent back the right session cookie on the subsequent request.
6. Server still holds the session, without logout/expiry/revocation, and reads from the right repository.
7. Subsequent request is processed through a security chain and session policy that permit restoring context.
8. Current authorities grant access to the target endpoint.

Missing a single link creates the impression of "logged in and immediately lost login".

## 4. Spring Security 5 vs Spring Security 6: what changed

Official documentation describes two main mechanisms:

- **SecurityContextPersistenceFilter:** could automatically save SecurityContext changes before response completion in setups using that filter.
- **SecurityContextHolderFilter:** loads context from SecurityContextRepository and places it into the holder, yet **does not automatically save changes**. If custom code wants persistence, it must call saveContext.

In **Spring Security 6 Servlet**, the default configuration switched to **SecurityContextHolderFilter requiring explicit save**. This easily triggers bugs when porting custom login code written for older versions to newer ones.

~~~java
// Not enough to persist Authentication for the next request.
SecurityContextHolder.setContext(context);

// Add the following step when intentionally persisting login.
securityContextRepository.saveContext(
    context, httpServletRequest, httpServletResponse
);
~~~

This is a **snippet assuming context and repository variables are already set up**, not a standalone Java file. It also contains no password verification; context is only saved **after** AuthenticationManager has authenticated successfully.

### 4.1. Defaults and customization

Spring Security 6 supports:

~~~java
http.securityContext(security -> security
    .requireExplicitSave(true)
);
~~~

This is a snippet inside an HttpSecurity configuration method; Spring Security 6 already uses explicit save by default on the standard Servlet stack. It is shown to clarify behavior, not as advice to toggle settings arbitrarily.

**Never configure both SecurityContextHolderFilter and SecurityContextPersistenceFilter** in the same chain expecting both to run together. When migrating from older releases, identify which filter is active, which repository loads/saves, and whether built-in login filters persist properly.

### 4.2. Built-in authentication filters already manage lifecycle

When using **formLogin(...)** or another Spring Security-provided mechanism, the success flow already invokes session strategy, sets context, and saves context per the filter's design. You **do not write a Controller calling saveContext** for every default login.

The topic of this lesson mainly arises when developers **manually invoke AuthenticationManager or construct Authentication inside a Controller/Filter** and assume Spring Security will auto-save the session.

### 4.3. Why is explicit save helpful?

It makes the moment of persistence intentional and easier to reason about, avoids unnecessary repository writes, and eliminates ambiguity when a response commits early. Code knows exactly when login succeeded and when context must be written to the session/store.

In return, custom code bears responsibility for doing so at the right time; forgetting saveContext causes the next request to lose authentication.

## 5. Types of SecurityContextRepository

### 5.1. HttpSessionSecurityContextRepository

Saves SecurityContext in **HttpSession**. In cookie-based browser apps, the client typically holds the session cookie and sends it back so the server locates the session holding context.

~~~text
Client Cookie: JSESSIONID=abc
            |
            v
Servlet container retrieves HttpSession "abc"
            |
            v
HttpSessionSecurityContextRepository.loadDeferredContext(...)
            |
            v
SecurityContext with saved Authentication
~~~

If saveContext needs to create a new session and policy permits, the response may need to send **Set-Cookie**. Save must happen before the response commits, otherwise the new session ID may not reach the client properly.

**Note:** An HttpSession can exist without the repository containing an authenticated Authentication. The session ID may also rotate after login to prevent session fixation.

### 5.2. RequestAttributeSecurityContextRepository

Stores context as a **request attribute** within a single HTTP request, helping Servlet dispatches like ERROR locate the context again. It **does not create login across multiple HTTP requests**.

If you use RequestAttributeSecurityContextRepository and call saveContext, the context can survive across dispatches belonging to the **same request**, yet an independent request #2 will not restore it from request #1.

This is a frequent configuration bug: the developer sees saveContext was called, yet the repository only writes request attributes and has no HttpSession backend.

### 5.3. DelegatingSecurityContextRepository

In Spring Security 6 Servlet, the default repository is commonly **DelegatingSecurityContextRepository** combining:

- **RequestAttributeSecurityContextRepository**
- **HttpSessionSecurityContextRepository**

The delegating repository attempts to read context from delegates in order and forwards saves to its delegates. This provides both intra-request/dispatch support and session-based persistence per policy.

Descriptive configuration:

~~~java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
~~~

This is a snippet inside a method with proper imports. The complete example in section 7 declares this same repository as a bean so **both filters and the Controller use the exact same instance**.

### 5.4. NullSecurityContextRepository

NullSecurityContextRepository neither saves context nor restores it from a session. It fits **stateless** authentication mechanisms intentionally designed to re-verify credentials/tokens on every request.

~~~java
SecurityContextRepository repository =
    new NullSecurityContextRepository();
~~~

If an app uses NullSecurityContextRepository, calling saveContext **does not create a login session**. This is not a bug; it is an architectural choice. Never mix NullSecurityContextRepository with a requirement that "the browser logs in once and stays in a session forever" without another persistence mechanism.

### 5.5. Summary table

| Repository | Where is it saved? | Does next request stay logged in? | When to use? |
| --- | --- | --- | --- |
| HttpSessionSecurityContextRepository | HttpSession | Yes, if session/cookie/policy are valid | Browser session login |
| RequestAttributeSecurityContextRepository | Servlet request attribute | **No** across independent requests | Supporting dispatches within one request |
| DelegatingSecurityContextRepository | Multiple delegates, usually request attribute + session | Possibly, if session delegate saves successfully | Standard Servlet setup |
| NullSecurityContextRepository | Not saved | **No** | Stateless authentication |
| Custom SecurityContextRepository | Custom store | Depends on implementation | Distributed sessions/specialized needs |

Never treat **saveContext returning cleanly** as proof a session was persisted if the repository/config intentionally avoids cross-request storage.

## 6. Correct recipe when authenticating manually

For an application-owned custom login mechanism, the basic flow is:

~~~java
// 1. Create untrusted request from login input.
Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password
    );

// 2. Provider/manager verifies credentials.
Authentication verified =
    authenticationManager.authenticate(attempt);

// 3. Create new context and set verified Authentication.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// 4. If subsequent requests must restore identity from session:
securityContextRepository.saveContext(context, request, response);
~~~

This is a **snippet inside a custom Controller or authentication filter with existing variables/imports/beans**, not a complete login endpoint to copy into production.

### 6.1. Never set authenticated=true directly from client input

Do not do this:

~~~java
// DANGEROUS: password/token not verified.
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        username, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    );
SecurityContextHolder.getContext().setAuthentication(forged);
~~~

This is an **illustrative anti-pattern** — never use it. An attacker can send any username, and the code self-grants ROLE_ADMIN. Saving a forged Authentication into the session makes the vulnerability even worse.

### 6.2. Save before committing the response

Once the response has been sent/committed (e.g., redirect or flushed response body), creating a new session and emitting Set-Cookie may fail to work properly. Call saveContext **in the successful authentication branch, before returning/redirecting/flushing the response**.

Never use HTTP 200 as proof the context was saved. Inspect the session repository and whether the HTTP response contains the session cookie when applicable.

### 6.3. SessionAuthenticationStrategy and session fixation

**saveContext does not replace the entire login lifecycle.** With custom login, consider **SessionAuthenticationStrategy**, especially rotating the session ID after login to defend against session fixation. Spring Security 6 does not run SessionManagementFilter by default to auto-detect arbitrary custom logins and invoke the strategy.

Built-in authentication mechanisms manage their own lifecycles; custom login may need to call the strategy explicitly:

~~~java
sessionAuthenticationStrategy.onAuthentication(
    verified, request, response
);
securityContextRepository.saveContext(
    context, request, response
);
~~~

Run the strategy before saving. This code does not cover CSRF, remember-me, concurrent sessions, success/failure handlers, MFA, or auditing; those must be evaluated for real deployments.

### 6.4. Do not disable CSRF globally to "fix login"

For browsers using session cookies, endpoints changing login state can suffer **login CSRF**. Never disable CSRF just because a curl POST got 403; use a valid CSRF token or an authentication and cookie architecture specifically evaluated for it.

The demo below keeps CSRF enabled by default and lets clients fetch a token from a learning endpoint. It is not yet a complete production login mechanism, yet avoids teaching CSRF bypass as a default fix.

## 7. Complete Spring Boot lab: single request vs multiple requests

Experiment goal: using the same username/password, create **two different POST endpoints**:

- **POST /lab/volatile:** Authenticates validly and sets context on the holder, yet intentionally **skips saveContext**.
- **POST /lab/persist:** Same valid authentication, sets context, calls session strategy, and calls **saveContext**.
- **GET /me:** Succeeds only if the request carries a non-anonymous Authentication.
- **GET /lab/csrf:** Issues a CSRF token so demo clients can send valid POSTs without disabling CSRF.

**Important:** the volatile endpoint intentionally omits persistence to demonstrate the bug, **not a production login pattern**. The persist endpoint is also a simplified lab: it omits full identity lifecycle responsibilities, rate limiting, MFA, concurrent-session policies, auditing, logout, and account recovery. Production should prefer built-in authentication mechanisms where appropriate.

### 7.1. Create the project and dependencies

Create a Java 17+, Spring Boot 3.x, Gradle Groovy DSL project with Gradle Wrapper via Spring Initializr. Select Spring Web, Spring Security, and Test. Inside the dependencies block of **build.gradle**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is only the **dependencies section of a Boot project that already has plugins/BOM**, not a standalone complete build.gradle.

### 7.2. Runnable Java file inside the Boot project

Create **src/main/java/com/example/contextlab/ContextLabApplication.java**:

~~~java
package com.example.contextlab;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ContextLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextLabApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SessionAuthenticationStrategy sessionStrategy() {
        return new ChangeSessionIdAuthenticationStrategy();
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {
        return http
            .securityContext(context -> context
                .requireExplicitSave(true)
                .securityContextRepository(repository)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/public", "/lab/csrf").permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/lab/volatile", "/lab/persist").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .anyRequest().denyAll()
            )
            // Do not disable CSRF: POST requests require a token.
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED))
            )
            .build();
    }
}

@RestController
class LabController {

    private final AuthenticationManager manager;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy;

    LabController(AuthenticationManager manager,
            SecurityContextRepository repository,
            SessionAuthenticationStrategy sessionStrategy) {
        this.manager = manager;
        this.repository = repository;
        this.sessionStrategy = sessionStrategy;
    }

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/lab/csrf")
    ResponseEntity<CsrfView> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException("CSRF token unavailable");
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfView(
                token.getHeaderName(), token.getToken()));
    }

    @PostMapping("/lab/volatile")
    ResponseEntity<Map<String, Object>> volatileLogin(
            @RequestParam String username,
            @RequestParam String password,
            HttpServletRequest request,
            HttpServletResponse response) {
        return authenticate(username, password, false,
            request, response);
    }

    @PostMapping("/lab/persist")
    ResponseEntity<Map<String, Object>> persistentLogin(
            @RequestParam String username,
            @RequestParam String password,
            HttpServletRequest request,
            HttpServletResponse response) {
        return authenticate(username, password, true,
            request, response);
    }

    private ResponseEntity<Map<String, Object>> authenticate(
            String username,
            String password,
            boolean persist,
            HttpServletRequest request,
            HttpServletResponse response) {

        final Authentication verified;
        try {
            verified = manager.authenticate(
                UsernamePasswordAuthenticationToken
                    .unauthenticated(username, password)
            );
        } catch (AuthenticationException failure) {
            SecurityContextHolder.clearContext();
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .cacheControl(CacheControl.noStore())
                .body(Map.of("error", "invalid_credentials"));
        }

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        if (persist) {
            sessionStrategy.onAuthentication(
                verified, request, response);
            repository.saveContext(context, request, response);
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "authenticatedNow",
                SecurityContextHolder.getContext()
                    .getAuthentication().isAuthenticated(),
                "savedForNextRequest", persist
            ));
    }

    @GetMapping("/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}

record CsrfView(String headerName, String token) {}
~~~

**Self-containment:** This is a complete Java file **inside the created Boot project**, with public class ContextLabApplication matching the filename, LabController, and record in the same package. The project must have the proper Gradle plugins/starters. Java 17 supports records, Map.of, and the syntax used in the code.

**Version note:** In the illustrative Spring Security 6.x range, DaoAuthenticationProvider supports no-arg instantiation followed by setUserDetailsService and setPasswordEncoder. Newer versions may change constructors or APIs; always check against your project's actual version. Never copy a lab pattern into production without reviewing session strategies and related security policies.

### 7.3. Explaining the beans

**PasswordEncoder + UserDetailsService:** Creates a single alice account strictly for the lab, with password BCrypt-hashed before insertion into the in-memory store. Hardcoded raw passwords in the demo are for isolated local environments only; never use these credentials in real deployments.

**AuthenticationManager:** ProviderManager invokes DaoAuthenticationProvider to verify username/password and only then returns an authenticated Authentication. Never construct authenticated tokens directly from client input.

**SecurityContextRepository:** DelegatingSecurityContextRepository combines RequestAttributeSecurityContextRepository and HttpSessionSecurityContextRepository, matching Spring Security 6 Servlet's default direction. Crucially, **both the filter and LabController inject the exact same repository bean**.

**SessionAuthenticationStrategy:** ChangeSessionIdAuthenticationStrategy illustrates the session fixation protection step when a session already exists. It does not replace all session-control/MFA mechanisms; when no session exists yet, strategy behavior depends on the actual context.

**SecurityFilterChain:** /public, /lab/csrf, and the two POST lab endpoints are permitAll; /me requires authenticated. HTTP Basic and formLogin are disabled so **the next request cannot accidentally re-authenticate from a Basic header or form login**, misleading us into thinking context was saved.

**CSRF:** The lesson keeps default CSRF protection. To POST to either endpoint, the client needs a valid CSRF token. GET /lab/csrf supplies the token for experimentation; it is not a complete production endpoint.

**NullRequestCache:** Disables saved-request caching in the lab so an HTTP 401 does not create unrelated session side effects, keeping results easier to interpret.

**HttpStatusEntryPoint:** When GET /me lacks authentication, the response is configured to return **401**. Without an explicit entry point, depending on active mechanisms, an app might redirect or return another status; do not assume 401 is automatic for every SecurityFilterChain.

### 7.4. Analyzing the two login methods

Both routes call shared authenticate(...), which performs:

~~~java
Authentication verified = manager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password
    )
);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

This is the shared snippet. Next:

- With **persist=false**, code returns 200 **without calling repository.saveContext**.
- With **persist=true**, code calls sessionStrategy.onAuthentication and **repository.saveContext**, and only then returns 200.

In the response, the **savedForNextRequest** field only indicates **which code branch requested saving**; it is not absolute proof the session will live forever or that the browser kept the cookie. You must test with a subsequent request carrying a real session cookie.

### 7.5. Why does the demo disallow GET-based login?

Logging in mutates identity and session state. Using GET /login?username=...&password=... puts passwords into URLs easily logged in history/logs, risks login CSRF, and violates HTTP safe-method semantics.

Thus the lesson uses **POST** with form fields and CSRF protection. This is only a simplified learning mechanism; production systems should prefer framework-supported formLogin/oauth2Login or standard authentication mechanisms.

## 8. Running the lab and testing two HTTP requests

### 8.1. Running Spring Boot

From the project with Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell: **.\gradlew.bat bootRun**.

By default the server runs on http://localhost:8080. The commands below **use only local sample accounts and HTTP on localhost**; never put real raw passwords in command history or long-lived shell variables.

### 8.2. Preparation step: CSRF token and cookie jar

Since the server still enforces CSRF, request GET /lab/csrf to obtain a token and session cookie. Example with curl:

~~~bash
curl -i -c session-demo.txt http://localhost:8080/lab/csrf
~~~

The JSON response has the structure:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "token": "runtime-generated-token-value"
}
~~~

The token field in the example is illustrative, **not a real token**. Use the actual value returned by the server in your run. Cookie jars are sensitive files because they contain session IDs; restrict read permissions and delete them after the lab.

### 8.3. Flow A: set context without saving

Use the existing session cookie jar and the token from /lab/csrf. Replace **CSRF_TOKEN_FROM_RESPONSE** with the real token:

~~~bash
curl -i -b session-demo.txt -c session-demo.txt \
  -H "X-CSRF-TOKEN: CSRF_TOKEN_FROM_RESPONSE" \
  --data-urlencode "username=alice" \
  --data-urlencode "password=learn123" \
  http://localhost:8080/lab/volatile

curl -i -b session-demo.txt http://localhost:8080/me
~~~

On the first POST, expected response:

~~~json
{
  "authenticatedNow": true,
  "savedForNextRequest": false
}
~~~

Immediately afterward, GET /me with the **same cookie jar** expects **401** because the prior login's context was never saved to the session repository. Having a session holding a CSRF token does not make GET /me authenticated.

### 8.4. Flow B: save context into HttpSession

Create a **new** cookie jar to avoid any Authentication leftover from another experiment:

~~~bash
curl -i -c session-persist.txt http://localhost:8080/lab/csrf
~~~

Grab the new token and invoke:

~~~bash
curl -i -b session-persist.txt -c session-persist.txt \
  -H "X-CSRF-TOKEN: CSRF_TOKEN_FROM_RESPONSE" \
  --data-urlencode "username=alice" \
  --data-urlencode "password=learn123" \
  http://localhost:8080/lab/persist

curl -i -b session-persist.txt http://localhost:8080/me
~~~

POST returns:

~~~json
{
  "authenticatedNow": true,
  "savedForNextRequest": true
}
~~~

GET /me with the cookie jar updated after POST expects **200**:

~~~json
{
  "user": "alice"
}
~~~

If the browser/curl **does not resend the session cookie**, a new GET /me still gets 401 even though the server saved context for another session.

After the lab, stop the server and delete cookie jars in your controlled environment. Never commit cookie jars, session IDs, or CSRF tokens to Git. Passwords in the commands above are public demo values — **never substitute real passwords on shared environments** since arguments can appear in shell history and process listings.

### 8.5. Results table

| Action | Saves Context? | Session cookie resent? | Subsequent GET /me |
| --- | --- | --- | --- |
| POST /lab/volatile succeeds | **No** | Cookie may exist from CSRF | **401** |
| POST /lab/persist succeeds | **Yes** | **Yes** | **200** |
| POST /lab/persist succeeds | **Yes** | **No** | **401** |
| POST with wrong username/password | **No** | Any | **401** on login; next request has no new login |
| POST missing/wrong CSRF token | Does not reach login logic | Any | **403** on POST per CSRF policy |

These are **expected results based on the demo configuration**, not measured output captured in this document. If the browser already holds an authenticated session from an earlier test, use a fresh session/cookie jar for a fair comparison.

### 8.6. CSRF failure does not mean wrong password

POST /lab/persist with a valid body yet missing CSRF token can return 403 **before the Controller even invokes AuthenticationManager**. Do not try fixing it by swapping PasswordEncoder or constructing Authentication manually. Check the CSRF token and session cookie first, then debug credentials.

## 9. MockMvc: proving persistence with two independent requests

Uses **spring-security-test** and **spring-boot-starter-test** declared in section 7. Create **src/test/java/com/example/contextlab/ContextLabApplicationTest.java**:

~~~java
package com.example.contextlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextLabApplicationTest {

    @Autowired MockMvc mvc;

    @Test
    void setContextAloneDoesNotPersistForNextRequest()
            throws Exception {

        MvcResult login = mvc.perform(post("/lab/volatile")
                .with(csrf())
                .param("username", "alice")
                .param("password", "learn123"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.authenticatedNow").value(true))
            .andExpect(jsonPath("$.savedForNextRequest").value(false))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        MockHttpServletRequestBuilder next = get("/me");
        if (session != null) {
            // If a session exists due to CSRF, it does not yet hold login context.
            next.session(session);
        }

        mvc.perform(next)
            .andExpect(status().isUnauthorized());
    }

    @Test
    void explicitSaveAllowsNextRequestToReadSessionContext()
            throws Exception {

        MvcResult login = mvc.perform(post("/lab/persist")
                .with(csrf())
                .param("username", "alice")
                .param("password", "learn123"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.authenticatedNow").value(true))
            .andExpect(jsonPath("$.savedForNextRequest").value(true))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));

        // Do not pass session to new request: no identity.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordDoesNotCreateAuthenticatedContext()
            throws Exception {

        mvc.perform(post("/lab/persist")
                .with(csrf())
                .param("username", "alice")
                .param("password", "wrong"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value(
                "invalid_credentials"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfTokenIsRejectedBeforeLogin()
            throws Exception {

        mvc.perform(post("/lab/persist")
                .param("username", "alice")
                .param("password", "learn123"))
            .andExpect(status().isForbidden());
    }
}
~~~

This is a **complete test file inside the Boot project**. MockMvc does not open real HTTP connections; the session is carried between requests via **MockHttpSession**, simulating the browser resending the cookie and the server finding the corresponding session.

### 9.1. Why must two requests be used?

If a test only calls POST /lab/volatile and asserts a 200 response, it only proves Authentication existed inside the first request. It has **not tested persistence**. The test must send a follow-up request to an authenticated URL:

- Volatile: subsequent request with session if any still gets 401.
- Persist: subsequent request carrying the session returns 200.
- Persist without passing the session: subsequent request gets 401.
- Wrong password or missing CSRF: login fails.

That directly verifies the lesson's core concept.

### 9.2. Do not assert only Set-Cookie

A response having Set-Cookie does not guarantee that cookie points to a session storing Authentication; the cookie could have been created for CSRF, request cache, or another feature. Conversely, when login occurs inside an already-existing session, the response may not need to emit a new session ID in all configurations.

**Sending a follow-up GET /me with a valid session/cookie** is a far more meaningful check than merely looking for a Set-Cookie header.

### 9.3. Running tests

~~~bash
./gradlew test
~~~

PowerShell: **.\gradlew.bat test**.

Test results are described as **expectations from the source code**, not a build run inside this document. In real adoption, run tests against your project's actual Spring Boot/Security versions, servlet container, database, proxies, and deployment configuration.

## 10. Form login, HTTP Basic, and Bearer tokens: why do they differ?

### 10.1. Form login (session-based)

With Spring Security-managed formLogin, the flow can:

1. Receive form username/password and CSRF token.
2. Filter calls AuthenticationManager.
3. Provider verifies credentials.
4. SessionAuthenticationStrategy handles session fixation/concurrency per config.
5. Context is set and saved through the repository.
6. Browser receives/holds the session cookie.
7. Subsequent requests send the cookie; filter restores context.

With this mechanism, the framework already handles the necessary steps per configuration. There is no need to replace it with a custom Controller just to "call AuthenticationManager manually".

### 10.2. HTTP Basic

HTTP Basic sends Authorization: Basic on requests. The mechanism re-authenticates whenever the header is present; one successful Basic request does not necessarily create a persistent browser login session. In a stateless setup, each request must carry valid credentials.

Therefore, seeing consecutive 200 responses on GET /me when **every request includes an Authorization header** **does not prove HttpSession saved the context**.

### 10.3. Bearer/JWT resource server

With Bearer tokens, the client sends Authorization: Bearer on each request. The resource server validates the token, builds Authentication in the request's SecurityContext, and enforces authorization. When stateless, the next request authenticates again from the Bearer token sent.

Do not try saving access tokens or JWTs into HttpSession just to "fix lost login" when the system is designed to be stateless. Pick the right mechanism for SPA/mobile/server-rendered web and your threat model.

### 10.4. OAuth2/OIDC login

OAuth2/OIDC browser login typically involves authorization-code flow, state, callbacks, session/cookies, and protocol tokens. How authentication is stored or tokens are used depends on OAuth2 client/resource-server configuration. Never apply this lesson's custom username/password snippet directly to an OIDC callback.

**Distinction:** "Current request has Authentication" is framework state; "client has proof of identity for the next request" may be a **session cookie**, **Bearer token**, or other credentials. The two must align architecturally and do not always involve HttpSession.

## 11. SessionCreationPolicy and misconceptions about sessions

Spring Security provides **SessionCreationPolicy** to control how Security creates/uses sessions. General meaning:

| Policy | Intent | Notes |
| --- | --- | --- |
| **ALWAYS** | Spring Security creates a session | Does not imply an authenticated user exists |
| **IF_REQUIRED** | Creates a session when needed | Usually fits session-based login |
| **NEVER** | Spring Security does not proactively create a session, yet can use an existing one | Not equivalent to STATELESS |
| **STATELESS** | Spring Security neither creates nor uses HttpSession to obtain SecurityContext | Authenticates per request via token/credentials |

Example for a stateless API:

~~~java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
~~~

This is a snippet inside SecurityFilterChain, not a full application.

### 11.1. Does IF_REQUIRED auto-save Authentication?

**No.** IF_REQUIRED governs whether a session can be created when needed, yet custom code must still perform the context-saving step per SecurityContextRepository and explicit-save semantics. It does not guess which Authentication was just verified.

### 11.2. NEVER does not guarantee zero cookies

NEVER describes Spring Security's policy; the servlet container or another part of the app can still create a session. Spring Security can use an already-existing session. For a strict stateless design, inspect the repository and other components rather than relying on a single enum.

### 11.3. STATELESS and saveContext

With SessionCreationPolicy.STATELESS, Spring Security typically uses a repository that does not persist Authentication via HttpSession. A custom Controller calling saveContext expecting "the browser keeps session login" may not behave as hoped. Never blindly swap STATELESS for ALWAYS if the API is designed for JWT/Bearer; make the right architectural choice.

## 12. Cookies, CORS, and reverse proxies

Even when saveContext is right, the client may still fail to retain the session. Common causes:

- Cookie rejected because domain/path mismatches.
- Cookie has Secure while testing over plain HTTP; in production Secure requires HTTPS.
- SameSite policy blocks sending cookies in cross-site contexts.
- Browser uses cross-origin fetch without a credentials mode allowing cookies.
- Backend CORS config does not allow the origin/credentials properly.
- Proxy/load balancer modifies or strips Set-Cookie or Cookie.
- Session store on server A differs from server B without a shared store or sticky sessions.
- Session timeout, logout, invalidation, or restart wiped the session.
- Cookie is scoped to a subpath different from the subsequent request's URL.

### 12.1. Fetch from the browser

A frontend app calling a different-origin API may need:

~~~javascript
fetch("https://api.example.test/me", {
  credentials: "include"
});
~~~

This is an illustrative snippet, not a complete CORS configuration. The server must still emit matching CORS headers and permissive cookie policies. **credentials: "include" does not bypass SameSite, Secure, origin policies, or browser privacy restrictions.**

Never configure Access-Control-Allow-Origin: * alongside credentials=true; specify exact allowed origins. Use HTTPS in production and inspect session cookies carefully in Developer Tools.

### 12.2. Distinguish session cookies from API tokens

A session cookie is usually an identifier pointing to server-side state. A JWT/Bearer token usually carries or references access rights and is checked per protocol on each request. Never apply cookie-session troubleshooting to a Bearer API if the real cause is the client omitting the Authorization header.

## 13. Logout: clearing in-memory context alone is not enough

If a login session was stored in HttpSession, calling only:

~~~java
SecurityContextHolder.clearContext();
~~~

may clear only the context held for the current request; the repository/session still retains the saved context. A subsequent request carrying the same session cookie can restore the user and "log back in".

To log out properly with session-based login, you need:

- Invalidate HttpSession and remove relevant session data.
- Clear SecurityContextHolder.
- Persist the cleared state if repository/session policies require it.
- Clear cookies or instruct the browser not to reuse the cookie.
- Revoke remember-me/tokens when relevant mechanisms exist.
- Address CSRF and logout HTTP method policies.

**Prefer Spring Security's built-in logout()** because it handles multiple lifecycle steps. For custom logout, clearing ThreadLocal alone is insufficient to revoke a stored session.

Likewise, when a user changes passwords or loses a role, old sessions/tokens may still retain old authorities. An invalidation/refresh/recheck strategy is required — never assume an in-memory Authentication updates automatically from the database.

## 14. ThreadLocal, @Async, and concurrent requests

### 14.1. SecurityContextHolder is not an application-wide global variable

In Servlet, the holder defaults to ThreadLocal. Even when requests are handled by the same pool thread at different times, Spring Security clears the context so user A never leaks to user B.

Do not do this:

~~~java
// ANTI-PATTERN: global login state.
static Authentication currentUser;
~~~

Such a static variable mixes identities across concurrent users and has nothing to do with session cookies.

### 14.2. Running asynchronous work

Code spawning threads, using CompletableFuture, @Async, or executors does not automatically carry SecurityContextHolder from the active request to the new thread. Spring Security provides propagation adapters such as DelegatingSecurityContextRunnable and DelegatingSecurityContextExecutor when appropriate.

**Context propagation differs from persistence.** Copying context to a worker thread serving one task does not save identity for the next HTTP request. Conversely, saving context to a session does not guarantee an async thread automatically sees the holder.

When passing context to a worker, bound its scope and clear it after the task. Never retain principals/credentials long-term inside work queues or thread pools.

### 14.3. Create a fresh context instead of mutating a shared instance

Spring Security documentation recommends creating a new SecurityContext with createEmptyContext before calling setAuthentication, rather than mutating an existing SecurityContext arbitrarily. This reduces the risk of shared state across threads or components holding references to the same context.

Still, creating a new context **does not automatically save it to the session**. The two steps solve two distinct problems.

## 15. Common implementation pitfalls

| Symptom | Potential cause | How to check |
| --- | --- | --- |
| POST login returns 200 yet GET /me is 401 | Only called setContext, forgot saveContext | Review custom login code and repository |
| POST login has Authentication yet no cookie | Session not created/saved or response committed early | Check saveContext and Set-Cookie |
| Has JSESSIONID yet still anonymous | Session holds only CSRF/saved request, no context | Inspect session repository |
| Called saveContext yet next request still 401 | Repository is RequestAttribute/Null, or client omitted cookie | Verify concrete repository and headers |
| IF_REQUIRED yet login does not persist | IF_REQUIRED does not auto-save custom context | Add proper persistence step |
| STATELESS yet expecting HttpSession | Contradictory architecture | Choose session or token-based design |
| Sending Bearer token every time yields 200 | Token is re-verified; does not prove session saved | Test a request without token |
| Browser gets 200 yet fetch /me gets 401 | Cross-origin cookie/credentials/CORS/SameSite | Developer Tools and CORS settings |
| Tested only one POST so bug went unnoticed | Never sent a second request | MockMvc test with two requests + session |
| Custom Controller login does not rotate ID | Skipped SessionAuthenticationStrategy | Use built-in login or matching strategy |
| POST login gets 403 before Controller | Missing/wrong CSRF token | Inspect token + cookie; do not disable CSRF blindly |
| GET /me returns 302 to /login instead of 401 | Form login entry point is active | Distinguish redirect from Basic/API entry point |
| Logged out yet next request stays logged in | Only cleared holder; session still has context | Spring Security logout + session invalidation |
| User's role revoked yet session still passes | Stale authorities in session | Revocation/refresh/business authorization |
| Two SecurityFilterChains use different repositories | Context saved in chain A, chain B reads elsewhere | Check matchers and per-chain repositories |
| Async worker does not see Authentication | ThreadLocal does not auto-propagate | Use context propagation where appropriate |

### 15.1. Do not "fix" by storing Authentication in an arbitrary static Map

Storing Authentication by username in a global static Map and reading it on the next request does not create a secure session model. You would have to solve unpredictable session IDs, client binding, timeouts, logout, concurrency, storage, and rotation. Spring Security and the servlet container already provide far better mechanisms.

### 15.2. Do not "fix" by always setting authenticated=true

If a subsequent request returns 401 due to a missing context, flipping authenticated=true without checking credentials simply introduces an authentication bypass. Fix **persistence and cookies**, never remove security checks.

### 15.3. Do not log raw Authentication for debugging

Authentication or principals can contain password hashes, details, tokens, or personal data. When debugging, log only events, request correlation IDs, and permitted fields; avoid printing Authorization/Cookie/Session IDs, full SecurityContext, or credentials.

## 16. Step-by-step investigation checklist

When a user reports "login worked, next request gets 401", check in order:

1. **Did authentication succeed?** Verify whether AuthenticationManager returned verified or threw AuthenticationException.
2. **Is the context right?** Did custom code create a fresh context and call setAuthentication(verified)?
3. **Was it saved?** Was saveContext called in the success branch before the response committed?
4. **Which repository?** HttpSession, RequestAttribute, Delegating, or Null; do filter and Controller share the same repository?
5. **Session policy?** Does IF_REQUIRED/NEVER/STATELESS match the goal of browser-session login?
6. **Session strategy?** Are session fixation, concurrent session policies, and login lifecycle handled?
7. **Does the response emit a proper Set-Cookie?** If a new session was created or ID rotated, did the cookie reach the client?
8. **Does the next request send the Cookie?** Check domain, path, Secure, SameSite, CORS, fetch credentials, and proxies.
9. **Does the server session still exist?** Check timeouts, restarts, load balancers, distributed session stores, logout/revocation.
10. **Which SecurityFilterChain was selected?** Did the subsequent request enter the same chain/repository or a compatible one?
11. **Are authn and authz confused?** 401/302 may mean unauthenticated; 403 may mean missing role or CSRF.
12. **Is something silently re-authenticating?** An HTTP Basic or Bearer header on every request can mask broken session persistence.
13. **Test with two fresh requests:** use MockHttpSession or a separate cookie jar, not just asserting POST login 200.
14. **Verify log safety:** never print credentials, Cookie/Authorization headers, or session IDs while investigating.
15. **Check logout and expiry:** verify expected behavior after logout or session expiration.

## 17. Self-check questions

**Q1.** Does AuthenticationManager.authenticate returning an authenticated Authentication automatically create a session?  
**A:** No. It verifies credentials and returns the result; persistence belongs to filters/repositories or code designed to save.

**Q2.** Does SecurityContextHolder.setContext(context) guarantee GET /me after login returns 200?  
**A:** No. With Spring Security 6 and SecurityContextHolderFilter, custom code must call saveContext to persist across requests.

**Q3.** Why can a user receive HTTP 200 on POST /login yet 401 on GET /me?  
**A:** Login succeeded within the first request, yet the context was not saved/restored or the client did not resend the right session cookie.

**Q4.** Does RequestAttributeSecurityContextRepository keep login across separate HTTP requests?  
**A:** No. It serves dispatches within the same request.

**Q5.** Where does HttpSessionSecurityContextRepository save context?  
**A:** Inside HttpSession; the next request must identify that session, typically via cookie.

**Q6.** Why can JSESSIONID exist while the user is still anonymous?  
**A:** A session may have been created by CSRF, request cache, or another feature without any saved Authentication.

**Q7.** Does NullSecurityContextRepository.saveContext turn the client into a session login?  
**A:** No. That repository intentionally saves nothing.

**Q8.** Does IF_REQUIRED mean a custom controller needs no saveContext?  
**A:** No. Session policy and explicit persistence are two separate things.

**Q9.** Does STATELESS mean requests have no Authentication?  
**A:** No. Authentication can be built from JWT/Bearer on each request without saving to HttpSession.

**Q10.** Why does a login mechanism need SessionAuthenticationStrategy?  
**A:** It may need to rotate session IDs against fixation and enforce configured session policies. saveContext alone does not replace the whole lifecycle.

**Q11.** If POST login has the right password yet misses the CSRF token and returns 403, is the password wrong?  
**A:** No. The CSRF filter can reject the request before reaching the Controller or provider.

**Q12.** Is checking Set-Cookie on the response enough to prove persistent login?  
**A:** No. The cookie may be only for CSRF or other purposes; test a follow-up request with the session.

**Q13.** Why use MockHttpSession in persistence tests?  
**A:** To simulate a subsequent request belonging to the same session and verify SecurityContextRepository restores the context.

**Q14.** Does a Bearer API returning 200 repeatedly with the same token prove context was saved in session?  
**A:** No. Every request may simply be re-verifying the token.

**Q15.** What can happen if logout only calls SecurityContextHolder.clearContext()?  
**A:** The session repository still holds the old context, so a follow-up request can reload the identity.

**Q16.** Should we construct an authenticated token from a client-sent role to avoid GET /me 401?  
**A:** No. That is an authentication bypass; verify credentials and fix saving/loading context instead.

**Q17.** Does SecurityContextHolder automatically follow CompletableFuture or @Async?  
**A:** Not by default. Use propagation mechanisms when appropriate; this is also distinct from session persistence.

## 18. Official documentation

- Spring Security — Persisting Authentication (SecurityContextRepository, filters, and explicit save): https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Session Management Migration in Spring Security 6: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — Servlet Architecture, FilterChainProxy: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — HTTP Basic: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — Bearer/JWT Resource Server: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Session Fixation: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
