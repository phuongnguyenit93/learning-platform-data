# SessionCreationPolicy: ALWAYS, IF_REQUIRED, NEVER and STATELESS

> **Context:** Spring Security 6 on the Servlet stack, Java 17+, Spring MVC applications. `SessionCreationPolicy` governs how Spring Security uses `HttpSession` to manage `SecurityContext`, not a switch that disables all sessions or all kinds of state in the application. This lesson compares the four values, highlights the core difference between `NEVER` and `STATELESS`, and demonstrates form login, REST APIs, and a runnable Spring Boot 3.3.5 project.

## 1. HTTP session and SecurityContext are two different concepts

HTTP handles each request independently. Web applications using form login usually want to remember logged-in users as they navigate between pages. In Servlet, `HttpSession` is a server-side data store identified by a session ID, typically passed via the `JSESSIONID` cookie. Spring Security can store `SecurityContext` in the session so subsequent requests can retrieve `Authentication`.

```text
Browser: POST /login + CSRF + credentials
       |
       v
Authentication filter
       |
       v
AuthenticationManager / AuthenticationProvider
       |
       v
Verified Authentication
       |
       v
SecurityContext / SecurityContextRepository
       |
       +-- May save context into HttpSession
       |
       v
Browser: GET /dashboard + JSESSIONID
       |
       v
SecurityContext is loaded according to the security policy
       |
       v
AuthorizationFilter checks permissions
```

However, not every application needs a browser login session. A REST API can receive a Bearer token or HTTP Basic credentials **on every request** and verify them itself. In this model, using a web UI session to authenticate API requests is sometimes undesirable.

`SessionCreationPolicy` answers: **May Spring Security create an HttpSession, and may it use an existing HttpSession to obtain SecurityContext?** It does **not** by itself define timeout, session fixation protection, URL permissions, CSRF, login forms, or token verification.

## 2. Comparison table of the four policies

The enum resides in `org.springframework.security.config.http.SessionCreationPolicy`:

```java
import org.springframework.security.config.http.SessionCreationPolicy;
```

| Policy | Proactively creates HttpSession for security? | Uses existing session to obtain SecurityContext? | Mental model |
| --- | --- | --- | --- |
| **`ALWAYS`** | **Yes**, creates eagerly even when not required | Yes | Always has a session |
| **`IF_REQUIRED`** | **Only when needed** for a security mechanism | Yes | Created on demand |
| **`NEVER`** | Does not create one itself for managing SecurityContext | **Can use an existing session** | Does not create, uses if present |
| **`STATELESS`** | Does not create one to manage SecurityContext | **Does not use HttpSession as a SecurityContext source** | Independent per-request authentication |

Note the bold text: **NEVER and STATELESS are not the same**. When a client carries a cookie for a valid `HttpSession` containing a `SecurityContext`:

- With `NEVER`, Spring Security **can** read the security context in that session.
- With `STATELESS`, Spring Security **does not** obtain authentication from that session.

This is an important point when an application has both **cookie-based web login** and **an API requiring Bearer token/Basic credentials**. If the API must not be allowed to use the web session for authentication, `STATELESS` has a clearer meaning than `NEVER`.

**Limitation of the table:** it describes how Spring Security is configured to use sessions. Application code, the Servlet container, an MVC library, or another component can still create an `HttpSession` during a request. In addition, features such as request cache, CSRF, and login handlers manage their own state, so you must inspect **the entire actual chain** if you want to be sure where a session is created.

## 3. How to configure with the Java DSL

Inside a `SecurityFilterChain` bean:

```java
@Bean
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http.sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
    );
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
    );
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
```

The snippet above is a **Java fragment**: it must reside inside `@Configuration` and requires Spring Security imports. The runnable project is in section 9. To change the policy, choose **one** of the four constants:

```java
SessionCreationPolicy.ALWAYS
SessionCreationPolicy.IF_REQUIRED
SessionCreationPolicy.NEVER
SessionCreationPolicy.STATELESS
```

Do not write `sessionCreationPolicy(...)` four times in the same chain and expect them to accumulate. Each chain has the session policy selected by its final configuration code.

### Spot common misconceptions right away

- Having an `HttpSession` **does not mean** the user is logged in.
- Having an `Authentication` in `SecurityContextHolder` for the current request **does not prove** it is saved for the next request.
- Not seeing `Set-Cookie` on a response **does not prove** the request has no session, because the session may already exist and the client already sent the cookie.
- Seeing `JSESSIONID` under `STATELESS` **does not prove Spring Security uses the session for authentication**; another component may have created the session.
- `STATELESS` does **not** automatically enable a JWT decoder or token verification.
- `IF_REQUIRED` does **not** mean every anonymous request creates no session.

## 4. ALWAYS — Spring Security proactively creates a session

```java
http.sessionManagement(s -> s
        .sessionCreationPolicy(SessionCreationPolicy.ALWAYS));
```

With this policy, Spring Security creates an `HttpSession` early in the lifecycle of a request handled by the security chain, even when a public request does not yet need to save authentication. In common Servlet configurations, the framework may use `ForceEagerSessionCreationFilter` to perform that behavior.

Example:

```text
Browser without JSESSIONID yet
    |
    v
GET /public
    |
    v
Security filter chain (ALWAYS)
    |
    +--> creates HttpSession
    |
    v
Controller calls request.getSession(false)
    |
    v
Returns an HttpSession, even though the user is anonymous
```

**Pros:** useful if a legacy application or a stateful mechanism genuinely requires a session to be present for every request.

**Trade-offs:** public requests also create server-side state; this increases storage cost, memory usage, and load on the session store, which can make the application harder to scale. `ALWAYS` does not make password checking better, and does not automatically enable MFA, concurrent-session limits, or session timeout. Choose it when there is a specific architectural requirement, not to fix every login error.

## 5. IF_REQUIRED — create a session when needed

```java
http.sessionManagement(s -> s
        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
```

This is usually the right choice for **web form login using an HTTP session**. Spring Security can create a session when a mechanism genuinely needs one, such as storing the `SecurityContext` of a logged-in user or storing a `SavedRequest` to return to the pre-login resource.

Example protected flow:

```text
GET /home                   -> public, may not need a session yet
GET /dashboard              -> anonymous, requires authentication
  ExceptionTranslationFilter
  RequestCache.saveRequest  -> may create a session to store the original URL
  redirect /login
GET /login                  -> renders login form + CSRF
POST /login                 -> validates username/password
  Authentication succeeds
  SecurityContext is saved according to repository
  redirect saved URL
GET /dashboard + cookie     -> has Authentication, checks permissions
```

**Important point:** `IF_REQUIRED` **does not guarantee anonymous requests have no session**. `HttpSessionRequestCache` may need to save the URL accessed before login. CSRF tokens or a session-based CSRF repository may need state. When you want to know why a session appeared, check the request cache, CSRF, login flow, context repository, and other filters.

For a very simple public GET that uses no state, `IF_REQUIRED` usually **does not need to create** a session. However, this conclusion depends on the entire application's configuration, not just the enum.

## 6. NEVER — do not create a session to manage context, but can use an existing session

```java
http.sessionManagement(s -> s
        .sessionCreationPolicy(SessionCreationPolicy.NEVER));
```

`NEVER` means: Spring Security does not create an `HttpSession` itself for the purpose of managing `SecurityContext`, **but if a session already exists, the framework can still use it** according to the `SecurityContextRepository` configuration.

Two cases:

```text
Request A: no session, no credentials
    -> NEVER does not proactively create a session for SecurityContext
    -> user remains anonymous

Request B: carries a valid JSESSIONID
    -> HttpSession already exists
    -> if it contains a valid SecurityContext, NEVER can read it
    -> authorization can see Authentication from the session
```

This suits some systems that integrate sessions created by another part of the application. However, it is **not** a strict choice if an API requires authentication solely via a token sent in each request, even when the browser is logged into a website on the same origin.

### Why can you still see a session when using NEVER?

Do not infer that `NEVER` disables `HttpServletRequest.getSession(true)`. A controller or another library can still create a session. In addition, request cache, CSRF, and authentication handlers have their own state logic; when strict control over session creation is needed, examine each of those components alongside `SecurityContextRepository`.

**NEVER does not mean “reject all existing sessions”.** That is what distinguishes it from `STATELESS` in context management.

## 7. STATELESS — do not use HttpSession to obtain SecurityContext

```java
http.sessionManagement(s -> s
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

With `STATELESS`, Spring Security does not create a session to manage context and **does not use HttpSession to obtain SecurityContext** for the request. Instead, an API application can verify `Authorization: Bearer ...` or `Authorization: Basic ...` on each request.

```text
GET /api/orders + Authorization header
       |
       v
Authentication filter + provider/decoder
       |
       v
Valid Authentication in the current request
       |
       v
SecurityContextHolder
       |
       v
AuthorizationFilter
       |
       v
Controller

Next GET /api/orders WITHOUT Authorization
       |
       v
Does not automatically pull Authentication from web HttpSession
       |
       v
Usually 401 if the endpoint requires authenticated()
```

The `STATELESS` policy does not verify JWTs by itself. A Bearer token application still needs a resource server, decoder/validator, trusted issuer/audience, token expiration, and appropriate authority mapping. HTTP Basic needs a manager/provider to verify username/password. **Setting STATELESS alone is not an authentication mechanism.**

### STATELESS does not forbid Servlet from creating an HttpSession

Application code can still explicitly execute:

```java
// Illustrative fragment, not recommended for production APIs:
HttpSession session = request.getSession(true);
session.setAttribute("demo", "created-by-controller");
```

Even with `STATELESS`, calling `getSession(true)` from a controller can create a session, and a subsequent request carrying the matching cookie can see that session via `request.getSession(false)`. **However, Spring Security still does not use it to obtain SecurityContext** under the `STATELESS` policy.

You must distinguish:

1. **Having an HttpSession on the Servlet container**: can be created by any application component.
2. **Spring Security using HttpSession as the identity source**: with `STATELESS`, the answer is **no**.

This is also why you cannot conclude “the application has zero state” from the enum alone: databases, rate limiting, caches, and audit logs are still state at other layers.

### Form login with STATELESS easily creates a login loop

Browser form login usually relies on session/context persistence. When configuring `STATELESS` without a mechanism to carry credentials/tokens into the next request:

```text
POST /login -> correct password, authentication succeeds
     |
     v
redirect /dashboard
     |
     v
GET /dashboard (new request)
     |
     v
Does not retrieve Authentication from HttpSession
     |
     v
Prompted to log in again
```

Do not fix this with `permitAll("/dashboard")` because that exposes sensitive resources. Either choose a policy suited for web sessions (usually `IF_REQUIRED`), or design a complete per-request token-based login flow.

## 8. SecurityContextRepository affects actual behavior

`SecurityContextHolder` holds `SecurityContext` so code/filters in the request can read `Authentication`. `SecurityContextRepository` is responsible for loading/saving context through the storage location supported by its implementation.

| Repository | Typical purpose | Limitation |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Reads/saves SecurityContext in HttpSession | Must consider session creation permissions and save conditions |
| `RequestAttributeSecurityContextRepository` | Stores context in request attributes | Not a login session across multiple requests |
| `NullSecurityContextRepository` | Does not save/load SecurityContext via a state store | Suitable when every request authenticates itself |
| `DelegatingSecurityContextRepository` | Coordinates multiple repositories | Behavior depends on delegates and configuration |

`SessionCreationPolicy` influences the selection and usage of sessions in security config, but **cannot replace understanding the repository and authentication filter**. In Spring Security 6, `SecurityContextHolderFilter` reads the context via the repository; when writing a custom filter/login endpoint, merely calling `SecurityContextHolder.getContext().setAuthentication(...)` is usually **not enough to guarantee saving the context to the next request**. You need to understand `saveContext(...)`, session authentication strategies, success/failure handlers, and the repository mechanism in use.

If an API runs `STATELESS` yet a controller sees `Authentication` in the current request, that is **not a contradiction**: authentication was created by the filter for that very request. The policy only states that `HttpSession` is not used to load/save context as a login session across subsequent requests.

Some older guides rely on `SessionManagementFilter` running on every request. In modern Spring Security 6 configurations, do not assume this filter is always present as before; authentication mechanisms can proactively invoke `SessionAuthenticationStrategy` upon success.

## 9. Runnable example with Java 17 + Spring Boot 3 + HTTP Basic

We build a small Spring MVC Servlet application to **switch policies at startup** and inspect sessions without changing the code four times. The example uses `spring-boot-starter-web` and `spring-boot-starter-security`, Spring Boot **3.3.5** (a released illustrative version), and Java 17+.

Three endpoints:

- `GET /session-state`: public, reads `request.getSession(false)`, does not create a session itself.
- `GET /demo-create-session`: **for lab use only**, proactively calls `request.getSession(true)` to prove application code can still create an `HttpSession`; this state-creating GET endpoint is unsuitable for production REST APIs.
- `GET /private`: requires HTTP Basic; returns the username and whether a session already existed.

The application uses `NullRequestCache` so that form login saved requests do not interfere with the results. **This is a specific choice for the experiment**, not a recommendation to disable request cache in form login websites.

### 9.1. Directory structure

```text
session-policy-lab/
├── pom.xml
└── src/main/java/example/sessionlab/
    ├── SessionPolicyApplication.java
    ├── SecurityConfig.java
    └── SessionProbeController.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>session-policy-lab</artifactId>
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
```

### 9.3. SessionPolicyApplication.java

```java
package example.sessionlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionPolicyApplication.class, args);
    }
}
```

### 9.4. SecurityConfig.java

```java
package example.sessionlab;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http,
                                            Environment env) throws Exception {

        String configured = env.getProperty(
                "demo.session-policy", "IF_REQUIRED");
        SessionCreationPolicy policy = SessionCreationPolicy.valueOf(
                configured.trim().toUpperCase(Locale.ROOT));

        http.sessionManagement(session -> session
                .sessionCreationPolicy(policy));

        // HTTP Basic demo: avoid SavedRequest / form login request cache.
        http.requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/session-state", "/demo-create-session").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").authenticated()
                .anyRequest().denyAll()
        );
        http.httpBasic(basic -> basic.realmName("Session Policy Lab"));

        // Keep default CSRF. Demo uses GET, not state-changing POST.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }
}
```

`Environment.getProperty` lets you try all four policies via the `demo.session-policy` parameter. If you pass a name not in the enum (such as `STATE_FULL`), the application will fail to start properly and display a configuration error — it does not silently fall back.

`NullRequestCache` **does not save the original URL to redirect after form login**, but this example only uses Basic. `PasswordEncoder` and `UserDetailsService` provide the hashed username/password to Spring Security; `httpBasic` enables the authentication filter on requests. `anyRequest().denyAll()` blocks routes that are not explicitly declared.

### 9.5. SessionProbeController.java

```java
package example.sessionlab;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionProbeController {

    @GetMapping("/session-state")
    public String sessionState(HttpServletRequest request) {
        // Observe session if already present; do not create.
        HttpSession session = request.getSession(false);
        return "session=" + (session == null ? "absent" : "present");
    }

    @GetMapping("/demo-create-session")
    public String demoCreateSession(HttpServletRequest request) {
        // Learning only: the application intentionally creates a session.
        // A state-creating GET is an antipattern for production REST.
        HttpSession session = request.getSession(true);
        session.setAttribute("demo.marker", "created-by-controller");
        return "application-session=created";
    }

    @GetMapping("/private")
    public String privatePage(Authentication auth, HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        String present = session == null ? "absent" : "present";
        return "user=" + auth.getName() + ";session=" + present;
    }
}
```

`getSession(false)` differs from `getSession(true)`: the `false` argument only asks whether a session already exists; the `true` argument allows Servlet to create a new session.

### 9.6. Running with the four policies

From the directory containing `pom.xml`, Java 17+ and Maven are required:

```bash
mvn spring-boot:run
```

The default is `IF_REQUIRED`. To choose another policy, run **one** of these commands:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments="--demo.session-policy=ALWAYS"
mvn spring-boot:run -Dspring-boot.run.arguments="--demo.session-policy=IF_REQUIRED"
mvn spring-boot:run -Dspring-boot.run.arguments="--demo.session-policy=NEVER"
mvn spring-boot:run -Dspring-boot.run.arguments="--demo.session-policy=STATELESS"
```

**Stop the previous process before trying the next policy** to avoid a port `8080` conflict. The commands show Maven/POSIX shell syntax; PowerShell may require adjusting how parameters are quoted.

### 9.7. Testing a fresh public request without cookies

For each policy, send a request without carrying an old cookie:

```bash
curl -s http://localhost:8080/session-state
```

Expected output for this demo project:

| Policy | Expected body | Reason |
| --- | --- | --- |
| ALWAYS | `session=present` | Security creates a session before the controller runs |
| IF_REQUIRED | `session=absent` | Public GET request does not need a session in the demo configuration |
| NEVER | `session=absent` | No existing session; security does not create one for context |
| STATELESS | `session=absent` | No component in this request creates a session |

This is **expected behavior for this exact demo configuration**, not a guarantee for every application using the corresponding policies. If you add form login, request cache, a custom CSRF token repository, or session-creating code, the result may differ.

Inspect response headers:

```bash
curl -i http://localhost:8080/session-state
```

With `ALWAYS`, a client without a cookie yet may receive `Set-Cookie: JSESSIONID=...`. Do not rely on a single `Set-Cookie` header alone to confirm or deny the existence of a session in every configuration.

### 9.8. Intentionally creating a session from the controller

Use `curl` to save a cookie jar:

```bash
curl -s -c policy-cookies.txt \
  http://localhost:8080/demo-create-session

curl -s -b policy-cookies.txt \
  http://localhost:8080/session-state
```

Expected two response bodies in order:

```text
application-session=created
session=present
```

Even with `NEVER`/`STATELESS`, if the cookie points to a live `HttpSession`, the controller still sees it. **This does not mean STATELESS used the session for authentication**. The session was intentionally created via the Servlet API.

Use a fresh cookie jar after restarting the server because the session ID from the previous process is no longer valid. `/demo-create-session` is an experimental endpoint; do not keep a public state-creating GET endpoint in a real product.

### 9.9. Testing HTTP Basic authentication

Without credentials:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/private
```

Expected `401` with a Basic authentication challenge.

Sending the valid demo account:

```bash
curl -s --user student:demo123 \
  http://localhost:8080/private
```

The body is `user=student;session=absent` or `user=student;session=present`, depending on the policy and the actual filter/repository mechanism. `ALWAYS` is expected to be `present`, while `STATELESS` on a fresh request without cookies and without other code creating a session is usually `absent`. **Do not assume IF_REQUIRED always yields a single outcome for every authentication filter.**

If running `STATELESS`, a subsequent `/private` request **without Authorization** usually still returns `401`; it is not treated as “logged in” just because the previous request succeeded. An HTTP Basic client needs to send appropriate credentials on each request.

## 10. Web form login application case

Replacing HTTP Basic with form login in **another SecurityFilterChain**, the `IF_REQUIRED` policy is usually appropriate:

```java
// Alternative illustrative fragment, do not merge into the Basic demo in section 9.
http.sessionManagement(s -> s
        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public", "/login").permitAll()
        .anyRequest().authenticated());
http.formLogin(Customizer.withDefaults());
```

In web form login, `HttpSessionRequestCache` can save the URL of an intercepted request and create a session **before** the user enters a password. After login succeeds, `SecurityContext` can be saved in the session so the browser carries the cookie to the next request. This is an example of why `IF_REQUIRED` does not mean “anonymous users have no session”.

### RequestCache and CSRF have independent effects

`RequestCache` may need a session to remember `SavedRequest` and return to the original URL. The demo's `NullRequestCache` will not do that. If a website requires a “return to the previous page after logging in” experience, do not copy the `NullRequestCache` configuration from an API into a web chain.

CSRF can use `HttpSessionCsrfTokenRepository` or `CookieCsrfTokenRepository`; how the token is stored and when it is needed affect whether a session/cookie appears. **Do not disable CSRF just to avoid seeing a session**: browsers using automatically sent cookies/credentials need a CSRF policy matching the threat model.

### NEVER and form login

With `NEVER`, if a session already exists from another component, security can use the existing context; otherwise, a login flow may appear to succeed yet fail to persist the context across a new request depending on the repository in use. Do not treat `NEVER` as a way to automatically turn form login into stateless login; you must test session/cookie/`saveContext`.

### STATELESS and form login

Without a mechanism to carry tokens/credentials into subsequent requests, form login with `STATELESS` easily leads to a login loop. The solution is to choose `IF_REQUIRED` for the web UI or design full token authentication instead of traditional session mechanisms.

## 11. API and browser coexisting: using multiple SecurityFilterChains

For a website with both browser login and an API, separate URL boundaries:

```java
// Design fragment: placed inside a @Configuration class with imports for
// @Bean, @Order, HttpSecurity, SecurityFilterChain, SessionCreationPolicy,
// NullRequestCache, and Customizer. Not a standalone runnable class.

@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
    http.requestCache(c -> c.requestCache(new NullRequestCache()));
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
```

Here the specific API chain `/api/**` is evaluated first; the fallback web chain applies to the remaining URLs. **A request is routed by `FilterChainProxy` to only the first matching chain**, never running through both. `securityMatcher` selects the chain, whereas `authorizeHttpRequests().requestMatchers` selects rules inside the chain.

**Why STATELESS for the API:** A browser can carry the web login cookie into `/api/**` requests. The API must not automatically pull `SecurityContext` from that session if the API contract mandates an `Authorization` header. The `NEVER` policy can use an existing web session, so it is **not equivalent** to `STATELESS` for this boundary.

If using JWT instead of HTTP Basic, you need an appropriate resource server/decoder/validator; simply switching `httpBasic` to `STATELESS` is not enough to protect Bearer tokens.

## 12. Things SessionCreationPolicy does not configure automatically

### Session timeout

The lifetime of an `HttpSession` depends on Servlet container/app configuration (for example, the Spring Boot Servlet property `server.servlet.session.timeout`), not set by `ALWAYS`/`IF_REQUIRED`/`NEVER`/`STATELESS`.

### Session fixation protection

After form login, a stateful application usually needs to change the session ID or apply session fixation protection. Spring Security provides session authentication strategies for this need; `SessionCreationPolicy` **does not replace** them. Seeing `JSESSIONID` change after login also does not mean session authentication was lost if the mechanism is configured properly.

### Concurrent-session control

Limiting the number of sessions per account (e.g., maximum sessions), session registry, expiring old sessions, and concurrent login policies are separate features. Setting `ALWAYS` does not automatically enable a single-session limit.

### Logout and token revocation

Web session logout can invalidate the session and clear `SecurityContext` depending on configuration. For stateless Bearer/JWT APIs, revoking/expiring tokens requires a dedicated design; `STATELESS` does **not** automatically revoke access tokens. With HTTP Basic, browsers may cache credentials on the client side, so clearing the session does not always “log out” Basic.

### Cookie, CORS, and CSRF

`Secure`, `HttpOnly`, `SameSite`, domain/path attributes, HTTPS, and CORS must be designed according to the client. Stateless **does not automatically exempt from CSRF**: browsers can send cookies or some cached Basic credentials automatically. When requests mutate state, check the threat model and the corresponding CSRF token policy rather than disabling it globally based on the enum name.

### “Completely stateless”

An API using `STATELESS` can still write to databases, audits, caches, rate-limit counters, and idempotency records. The enum specifically refers to **HttpSession serving SecurityContext**, not forcing the entire system to store no state.

## 13. When to choose which value?

| Practical requirement | Typically suitable policy | Why |
| --- | --- | --- |
| Web form login, cookie session, redirect back to opened URL | **IF_REQUIRED** | Session is created when authentication/request cache needs it |
| Legacy web app needing a session for every request | **ALWAYS** | Proactively creates a session even for public requests |
| Reuse a session created by another component without creating one for context | **NEVER** | Uses an existing session when present |
| API requiring Basic/Bearer credentials per request, not taking identity from web cookie session | **STATELESS** | Separates SecurityContext from HttpSession |
| Same application has web UI and REST API | **Two chains, two policies** | Each group has its own authentication/session/entry point |
| Want web form login while strictly avoiding sessions | **Revisit the authentication flow** | Must design a token/mechanism carrying identity across requests |

The policy must be chosen **together** with the authentication mechanism, security context repository, request cache, CSRF, logout, and operational requirements. There should not be a single “default for all endpoints” enum if the UI and API have different authentication contracts.

## 14. Common errors and how to debug

| Symptom | What to check | How to fix |
| --- | --- | --- |
| STATELESS yet JSESSIONID still appears | Whether controller/another library calls `getSession(true)`, old cookie | Identify where it was created; do not assume security uses it |
| NEVER yet still gets identity from session | This may be intended by NEVER design | If session auth is unwanted, choose STATELESS for the API |
| IF_REQUIRED yet anonymous has a session | SavedRequest, CSRF, app component needing state | Inspect request cache and token retrieval |
| ALWAYS causes high load on session store | Every public request creates a session | Choose IF_REQUIRED if eager session is not required |
| Form login accepts password then redirects back to login | STATELESS, context not saved/loaded, broken cookie | Check policy/repository/cookie/session strategy |
| API lacks Authorization yet remains accessible | Web session was used or request hit the wrong chain | Separate `securityMatcher` and a STATELESS API chain |
| JWT returns 401 even though STATELESS is enabled | Missing decoder/provider or invalid token | Configure Resource Server properly |
| Getting 403 after login | Missing role/authority or CSRF | Check authorization; do not tweak policy arbitrarily |
| Login succeeds but next request is anonymous | SecurityContextRepository did not save, invalid session/missing cookie | Test load/save context, filters, and success handler |
| NullRequestCache loses old redirect URL | SavedRequest not saved | Keep request cache in web flows needing redirect |
| Different chains for URLs with different policies | Order/matcher routed request to the wrong chain | Debug `FilterChainProxy`, `@Order`, and `securityMatcher` |
| Wrong cookie SameSite/domain/path | Browser does not send cookie when needed | Check HTTPS, proxy, and cookie attributes |

**Systematic inspection procedure:**

1. Identify the actual URL/method/cookie/Authorization without logging secrets.
2. Identify the selected **SecurityFilterChain** and its `SessionCreationPolicy`.
3. Determine whether a session already existed at request start or was newly created: inspect places calling `getSession(true)`.
4. Identify `SecurityContextRepository`, login filter, request cache, and CSRF repository.
5. Check whether authentication is obtained from a header/token or a session.
6. Check **authorization** independently from authentication, distinguishing 401/403.
7. Re-test with a browser carrying cookies and a cookieless REST client to prove the security boundary is correct.

In a development environment you can enable:

```properties
logging.level.org.springframework.security=DEBUG
```

Do not print session IDs, passwords, Bearer tokens, Authorization headers, or sensitive data into logs.

## 15. Self-check questions

1. **Does ALWAYS make the user automatically authenticated?** No, an empty session is not a verified identity.
2. **Does IF_REQUIRED guarantee anonymous requests never have a session?** No, request cache/CSRF or other code may need a session.
3. **Where do NEVER and STATELESS differ?** NEVER can use an existing session for SecurityContext; STATELESS does not.
4. **Can a controller create an HttpSession under STATELESS?** Yes, `getSession(true)` is still a valid Servlet API call.
5. **Why can STATELESS + default formLogin cause a login loop?** Subsequent requests are not authenticated from the session; there is no replacement credential.
6. **Does STATELESS verify JWTs automatically?** No, an appropriate Resource Server filter/provider/decoder is required.
7. **Can SecurityContextHolder in a STATELESS request contain an Authentication?** Yes, authentication is created during the current request, not from a session.
8. **Does JSESSIONID appearing prove Spring Security created it?** No.
9. **Which policy fits an API that must not accept web cookies as a form of login?** STATELESS on a separate API chain.
10. **Which SessionCreationPolicy automatically adjusts session timeout/MFA/concurrent login?** None of them.
11. **Why does a public GET with ALWAYS have a session?** The policy requires eager session creation.
12. **To test the difference, call getSession(false) or true?** `false` to observe; `true` proactively creates one and skews initial measurements if unintended.

## 16. Implementation checklist

- [ ] Choose the policy based on the authentication mechanism and the need to persist SecurityContext across requests.
- [ ] If the web app uses form login, verify session cookies, request cache, login success, CSRF, and security context persistence.
- [ ] If an API requires per-request Bearer/Basic authentication, configure STATELESS separately and test requests carrying only a web cookie.
- [ ] Do not confuse NEVER with STATELESS; remember NEVER can use an existing session.
- [ ] Do not use JSESSIONID/Set-Cookie as the sole proof of session/authentication origin.
- [ ] Inspect components that can create HttpSession, especially controllers, request cache, and CSRF repository.
- [ ] With Spring Security 6, understand explicit security context saving and session authentication strategies if writing custom login.
- [ ] Test behavior per HTTP request rather than only checking the enum in source code.
- [ ] Separately configure timeout, fixation protection, concurrent sessions, logout, and cookie security.
- [ ] Check CSRF and CORS based on how clients send credentials, rather than disabling them based on the policy name.
- [ ] Do not ship `/demo-create-session` to production, because it intentionally creates state from GET.
- [ ] After changing a policy, test anonymous, authenticated, subsequent requests, role-denied, and expired-session cases.

**Conclusion:** `ALWAYS` always creates an HttpSession; `IF_REQUIRED` creates one when needed; `NEVER` does not proactively create one to manage SecurityContext but **can use an existing session**; `STATELESS` **does not use a session to load SecurityContext**, making it suitable for APIs that authenticate each request independently. Understanding this boundary helps avoid login loops, unintended session creation, and especially prevents REST APIs from accidentally trusting web UI login cookies.