# HTTP Basic: Per-Request Authentication and Its Relationship to Session Policy

## Learning Objectives

After this lesson, you will be able to:
- Explain why HTTP Basic typically requires sending credentials on **every HTTP request** and how that differs from session-persisted login.
- Trace a request's path through **BasicAuthenticationFilter**, **AuthenticationManager**, **SecurityContextHolder**, and the authorization step.
- Distinguish the four **SessionCreationPolicy** values, especially **NEVER** and **STATELESS**.
- Configure and test stateless HTTP Basic in Spring Security Servlet and recognize signs of misconfiguration.

## 1. How Does HTTP Basic Authenticate a Request?

HTTP Basic is an HTTP-layer authentication mechanism: the client sends an **Authorization** header containing a username and password Base64-encoded in the form **username:password**.

Example with the practice account **demo** / **change-me**:

~~~http
GET /me HTTP/1.1
Host: localhost:8080
Authorization: Basic ZGVtbzpjaGFuZ2UtbWU=
~~~

The Base64 string above decodes to **demo:change-me**. Base64 is only data representation, **not cryptographic encryption**: anyone who reads the header can recover the login credentials. Therefore, HTTP Basic must be used over **HTTPS/TLS** in real environments; avoid writing this header into logs or telemetry.

When accessing a protected resource without valid credentials, the typical response is:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

The **WWW-Authenticate** header indicates that the client can resend the request with Basic credentials. The **realm** name is the protection space configured by the server; its value and other headers depend on the application. A browser may display a login dialog and automatically resend remembered credentials. Some responses intended for AJAX may be configured not to issue a browser challenge; do not treat the login dialog as the sole proof of Basic authentication.

**There is no separate mandatory login step** such as POST /login in the Basic protocol itself. Each request carries its own credentials or relies on an independently configured authentication persistence mechanism.

## 2. Request Path in Spring Security Servlet

Consider a request to **GET /me** when the application configures HTTP Basic:

1. **SecurityFilterChain** selects the filter chain matching the URL. **BasicAuthenticationFilter** checks whether the Authorization header has the **Basic** scheme.
2. If authentication from the header is needed, the filter decodes the username/password pair, creates an unauthenticated **UsernamePasswordAuthenticationToken**, and passes it to **AuthenticationManager**. The underlying mechanism (for example **DaoAuthenticationProvider**, **UserDetailsService**, **PasswordEncoder**) verifies the credentials.
3. On success, the resulting **Authentication** containing the principal and authorities is placed into the **SecurityContext** inside **SecurityContextHolder** for the current request. Downstream filters and controllers can retrieve that identity.
4. **AuthorizationFilter** checks access rules, such as **authenticated()** or **hasRole("ADMIN")**. Valid authentication does not mean permission to access every endpoint.
5. When the request finishes, the processing thread's security context is cleared by the filter mechanism. Whether the identity appears in the next request depends on **SecurityContextRepository** and other authentication mechanisms, not on variables in **SecurityContextHolder** persisting forever on their own.

If authentication fails, Spring Security clears the relevant context and triggers **AuthenticationEntryPoint** to return an authentication error, usually **401** with a Basic challenge. If authenticated but lacking permissions, the response is usually **403 Forbidden**.

If a request sends no Authorization header and is not yet authenticated: **AuthorizationFilter** denies access, and **ExceptionTranslationFilter** hands off to initiate authentication via the entry point. With Basic, **RequestCache** typically does not need to save the original request because the client can resend it on its own.

### Visualizing Three Independent Requests

~~~text
Request 1: GET /me, no Authorization
    -> no Authentication -> 401 (+ WWW-Authenticate)

Request 2: GET /me, Authorization: Basic <valid credentials>
    -> authenticated -> request SecurityContext -> 200

Request 3: GET /me, no Authorization, no login persistence mechanism
    -> no Authentication from previous request -> 401
~~~

The core point: **per-request authentication state** differs from **login state persisted across multiple requests**. Session policy determines whether Spring Security can rely on HttpSession to restore SecurityContext.

## 3. Basic, HttpSession, and SecurityContextRepository Are Three Different Concepts

- **HTTP Basic** describes how the client presents credentials in an HTTP header. It does not inherently define a server-side login session.
- **HttpSession** is the Servlet container's session object, typically identified via the **JSESSIONID** cookie. A session can store various kinds of data, which may or may not include SecurityContext.
- **SecurityContextHolder** provides Authentication for the **request currently being processed**. It is not a long-term session store.
- **SecurityContextRepository** determines how SecurityContext is loaded and saved between requests. **HttpSessionSecurityContextRepository** can use HttpSession, whereas **NullSecurityContextRepository** does not persist/read context across requests.

In a stateless HTTP Basic API design, each request is authenticated from its header and the result only needs to exist for that request. When the next request arrives, the server does not pull an identity from a session: **the client must send a valid Authorization header again**.

However, do not conclude that "whenever Basic is enabled, Spring Security always calls the password checker on every request." If the application has already restored a valid Authentication via session or another mechanism, the filter may not need to re-authenticate the same identity; remember-me, if enabled, also changes behavior. To be sure each request authenticates independently, you must inspect **both the Basic configuration and the SecurityContext persistence configuration**.

## 4. Four Session Creation and Usage Policies

Spring Security Servlet provides **SessionCreationPolicy**:

| Policy | Does Spring Security create HttpSession? | Can SecurityContext be read from an existing HttpSession? | Meaning when using Basic |
| --- | --- | --- | --- |
| **ALWAYS** | Yes, proactively creates one | Yes, depending on repository | Allows session-based architecture; does not automatically turn Basic into session-based login |
| **IF_REQUIRED** | Only when needed | Yes, depending on repository | A session may appear due to other components; does not guarantee Basic is saved |
| **NEVER** | Does not proactively create one | **Yes**, if a session already exists | Not equivalent to stateless; authentication data can be restored from an existing session |
| **STATELESS** | Does not create one for security context purposes | **Does not** use session to obtain SecurityContext | Suited for independent per-request Basic authentication |

**Important distinctions:**

- **NEVER**: Spring Security does not proactively create an HttpSession, but if a session already exists beforehand, the configuration allows using it to obtain the security context. Another component can still create a session.
- **STATELESS**: Spring Security neither creates an HttpSession for security context nor uses HttpSession to restore SecurityContext. Other application mechanisms can still create a session on their own; thus "STATELESS" does not mean the entire server will never ever emit a cookie.
- **ALWAYS** or **IF_REQUIRED** only controls the session policy; it **does not guarantee** that BasicAuthenticationFilter writes its Authentication to HttpSession by itself.

In modern Spring Security, saving Authentication depends on the repository configured on the filter. If you intentionally want to store Basic results in a session, you must configure the appropriate repository on **BasicAuthenticationFilter** and check the corresponding session policy. Simply switching **STATELESS** to **IF_REQUIRED** is not a reliable way to get "log in once."

### Two Scenarios to Distinguish

**A. Basic + STATELESS (typical API)**

~~~text
GET /me + valid Authorization  -> 200
GET /me without Authorization  -> 401
GET /me + old JSESSIONID       -> 401, if no other authentication mechanism exists
GET /me + valid Authorization  -> 200
~~~

Because Authentication is not restored from a session, each protected request needs credentials or another authentication mechanism acting on that request.

**B. Basic + storing Authentication in HttpSession (explicit configuration)**

~~~text
GET /me + valid Authorization  -> Authentication is stored in session
GET /me + valid session cookie -> can be authenticated via context from session
Session expired/deleted        -> uncredentialed request prompts for auth again
~~~

In scenario B, the server must manage expiration, invalidation, cookies, and session protection. That is a stateful design; Basic appearing on the first request does not make later requests "Basic on every request." Do not assume scenario B happens just because HTTP Basic is enabled.

## 5. Spring Boot Servlet Example: Per-Request Basic Authentication Without Sessions

The example uses **Java 17+**, Spring Boot Servlet with **spring-boot-starter-web** and **spring-boot-starter-security** dependencies. Create **src/main/java/com/example/basicauth/BasicAuthApplication.java** inside a Spring Boot application with the corresponding Gradle/Maven plugin:

~~~java
package com.example.basicauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
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
public class BasicAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicAuthApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(encoder.encode("change-me"))
                .roles("READER")
                .build()
        );
    }

    @RestController
    static class Api {
        @GetMapping("/public")
        String publicEndpoint() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "hello, " + authentication.getName();
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
~~~

Explanation of choices:

1. **httpBasic(Customizer.withDefaults())** enables Authorization: Basic processing in the configured SecurityFilterChain.
2. **sessionCreationPolicy(STATELESS)** sets the policy not to restore SecurityContext from HttpSession; this is what gives the example independent per-request authentication behavior.
3. **/public** allows anonymous access; **/me** requires an authenticated user; **/admin** needs the ADMIN role. The demo user only has the READER role.
4. **PasswordEncoderFactories.createDelegatingPasswordEncoder()** hashes the password in the example with an appropriate encoder; the plaintext password is only seed data for practice. In production, use secure user/secret management and stored password hashes, never embedded credentials in source code.
5. The example only exposes GET endpoints and therefore retains the default CSRF protection configuration. With state-changing methods, CSRF decisions must be based on client type and how browsers send credentials.

This is **a complete Java file in a Spring Boot project with dependencies**, not a program relying only on the JDK standard library; running **javac BasicAuthApplication.java** alone will lack the Spring classpath. For a Gradle Spring Boot project, run from the project directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell use **.\gradlew.bat bootRun**. If using Maven Spring Boot, the equivalent command is **./mvnw spring-boot:run**. By default the example serves at **localhost:8080**, unless another server.port is configured.

### Sending Requests and Verifying

~~~bash
curl -sS http://localhost:8080/public
# public

curl -sS -u demo:change-me http://localhost:8080/me
# hello, demo

curl -i http://localhost:8080/me
# HTTP/1.1 401 ... (status excerpt)
# WWW-Authenticate: Basic realm="Realm" (typical)

curl -i -u demo:wrong http://localhost:8080/me
# HTTP/1.1 401 ... (invalid credentials)

curl -i -u demo:change-me http://localhost:8080/admin
# HTTP/1.1 403 ... (authenticated, missing ADMIN role)
~~~

Lines starting with **#** in the command block are expected outcomes or statuses for reference, not full HTTP responses. Detailed headers may vary by configuration and version. The first two response bodies are literally **public** and **hello, demo** (with no trailing newline from the controller).

Be sure to try two commands in order: call **/me** with **-u demo:change-me** successfully, then call **/me** again without **-u**. The second command still returns **401**. This is not an "unexpected session loss": each curl invocation is a separate request, and the **STATELESS** policy does not allow reusing the previous request's Authentication from HttpSession.

In this example, **/public** does not require login. However, if a client proactively sends a Basic header to /public, the filter can still process the credentials; the **permitAll()** rule only means the resource does not require authentication to be accessed.

## 6. When Is a Request Actually Re-authenticated?

Label each request **R1**, **R2** for the same user:

| Configuration and header of R2 | Source of Authentication for R2 | Typical outcome |
| --- | --- | --- |
| **STATELESS**, R2 has valid Basic | Checks Basic in R2 | Can access permitted resources |
| **STATELESS**, R2 has no Basic | No context from R1 to restore | 401 on resources requiring login |
| **STATELESS**, R2 has invalid Basic | Attempts authentication with wrong credentials | 401, even if R1 succeeded |
| Context properly saved in HttpSession, R2 has session cookie | Can retrieve Authentication from session | Does not necessarily have to resend Basic |
| Remember-me or another mechanism present | Can use the alternative mechanism | Cannot assert every request re-checks password |

Therefore, the accurate statement is: **in a purely stateless HTTP Basic model, protected requests must carry their own credentials and are typically authenticated independently**. You must inspect the entire **SecurityFilterChain**, repository, and active authentication methods before drawing conclusions for a specific application.

## 7. Security, Operational, and Architectural Implications

**Repeated password transmission:** Basic carries recoverable login credentials across requests. Require HTTPS, restrict where headers are stored/logged, rotate secrets, and apply brute-force protections. Although TLS encryption protects traffic in transit, log leaks or compromised clients remain a risk.

**Permission revocation and password changes:** When authenticating fresh credentials on each request, password changes or account lockouts can take effect on the very next request, depending on provider caching. When using sessions, a stored Authentication can persist until the session expires or is invalidated; changing user data does not automatically delete every active session.

**Logout:** With purely stateless Basic, the server has no "Basic session" to invalidate. The client or browser can keep automatically sending the remembered Authorization header. Calling a logout endpoint or deleting JSESSIONID does not guarantee the browser stops sending the Basic header; you must stop sending credentials, clear client-side credential caches, or revoke/change the password as needed.

**CSRF:** Stateless does not mean immune to CSRF. **Browsers can automatically attach HTTP Basic credentials** to same-origin requests; if the application has state-changing operations, you must still evaluate and apply appropriate CSRF protection. Never disable CSRF just because you chose **STATELESS**. For APIs used solely by non-browser clients with non-auto-sent credentials, the decision may differ based on the actual threat model.

**Performance:** Re-authenticating every request can increase user lookups and password hash checks; measure load, use controlled caching, and apply rate limits. Do not enable session persistence haphazardly just to mask a performance issue without reviewing security implications.

**Suitable scope:** Basic is simple for technical clients or controlled internal services over TLS with tightly managed credentials. If you need a browser login experience, explicit logout, MFA, or federated login, evaluate an appropriate mechanism such as form sessions or OIDC/OAuth2 rather than expecting Basic to provide those features.

## 8. Misconceptions and How to Diagnose Them

| Symptom or assumption | Common cause | How to verify |
| --- | --- | --- |
| "First GET succeeded, next GET without Authorization returned 401" | This is the expected behavior of stateless Basic | Check whether the client sends Authorization on **every protected request** |
| "Set NEVER so there is definitely no session" | NEVER can still use an existing session; something else may create a session | Inspect HttpSession, RequestCache, and components calling getSession() |
| "Set IF_REQUIRED so Basic automatically saves login to session" | Policy does not change the Basic filter's Authentication persistence config | Inspect the **SecurityContextRepository** used upon successful authentication |
| "Enabled STATELESS so there will never be a JSESSIONID" | Other application code or libraries can still create an HttpSession | Trace where sessions are created; distinguish servlet session from security context |
| "Sent valid Basic but /admin returned 403—authentication error" | Authentication succeeded, but permissions are insufficient | Check authorities/roles and hasRole/hasAuthority requirements |
| "Logged out, yet the browser can still call the API" | Browser keeps sending cached Authorization | Inspect the actual request; change/revoke credentials if needed |
| "No Basic sent, yet access is still granted" | Context may be restored via session, remember-me, or another mechanism; or endpoint is permitAll | Inspect URL rules, filter chain, repository, and cookies |

When debugging, check **status 401 vs 403**, the **Authorization** header (check presence/absence only, never log secret values), **Cookie/JSESSIONID**, the filter chain matched to the URL, and the Authentication source in the request. Enable Spring Security logging in a safe, controlled environment; avoid logging passwords or Base64 credentials.

## 9. Self-Check Comprehension Questions

1. Request R1 sends valid Basic and receives 200. R2 sends no Authorization, the app uses STATELESS, and no other login mechanism exists. Why does R2 receive 401? **Because R1's Authentication is not restored from HttpSession; R2 must authenticate itself.**
2. Why is **NEVER** not the same as **STATELESS**? **NEVER does not proactively create a session but can use an existing one; STATELESS does not use a session to retrieve SecurityContext.**
3. Can HTTP Basic and sessions be used together? **Yes, when explicitly configuring Authentication persistence/restoration via a repository and managing sessions accordingly; Basic itself does not require it.**
4. Why does a client using valid Basic still get 403? **Because the authenticated identity lacks sufficient permissions for the endpoint.**
5. Should CSRF be disabled just because STATELESS is configured? **No; browsers can automatically send Basic credentials, so CSRF risk must be evaluated from client behavior.**

## References

- [Spring Security Reference — Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security Reference — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [SessionCreationPolicy API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/http/SessionCreationPolicy.html)
- [Spring Security Reference — CSRF](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)
