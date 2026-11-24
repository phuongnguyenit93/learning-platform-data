# Processing Chain from Credentials to an Authenticated Authentication

> **Scope:** Spring Security on the **Servlet stack**, Java 17+, Spring Boot 3.x / Spring Security 6.x applications. The topic is the **authentication flow**: from credentials sent by the client, through filters, an unauthenticated token, `AuthenticationManager`, and `AuthenticationProvider`, to a verified `Authentication` and how the result is placed into `SecurityContext`. It is important to distinguish authentication from authorization, as well as the differences between form login, HTTP Basic, and bearer tokens.

## 1. The Big Picture: Who Does What?

In a Servlet application using Spring Security, an HTTP request passes through the container filter chain. `DelegatingFilterProxy` typically delegates execution to `FilterChainProxy`, which finds a `SecurityFilterChain` whose `RequestMatcher` matches the URL. An authentication filter runs only if it is in the selected chain and if the request satisfies the condition handled by that filter.

~~~text
Client
  |  POST /login with username/password (e.g., form login)
  v
Servlet container
  -> DelegatingFilterProxy -> FilterChainProxy
     -> SecurityFilterChain matching the request
       -> filter loading SecurityContext for the request
       -> [CSRF filter when applicable]
       -> UsernamePasswordAuthenticationFilter
          (1) extract username/password
          (2) create an unauthenticated Authentication
          (3) call AuthenticationManager.authenticate(...)
                -> ProviderManager
                    -> select an AuthenticationProvider supporting the token
                        -> retrieve user data/keys/tokens to check
                        -> verify credentials + account status
                        -> return an authenticated Authentication
          (4) set Authentication in SecurityContext
          (5) save context to repository if needed, handle session/success
       -> response branch or subsequent filters/controller
       -> end of filter scope: clear SecurityContextHolder on the thread
~~~

The diagram illustrates a **typical successful form login**. Not every mechanism has the same endpoint, token type, or response. With HTTP Basic or bearer tokens, credentials typically appear in headers and the request can continue to the controller after being authenticated. With default form login, success usually results in a redirect and ends the login processing branch.

| Component | Primary Responsibility | Do Not Misassign Responsibility |
| --- | --- | --- |
| `SecurityFilterChain` / `FilterChainProxy` | Select and run the servlet security filters matching the request. | Does not compare passwords directly. |
| Authentication filter | Extract data sent by the client, create an unauthenticated token, call the manager, and handle the result. | Must not mark a token as authenticated without verification. |
| `AuthenticationManager` | Entry point for the `authenticate(authentication)` contract. | Does not necessarily understand every credential type itself. |
| `ProviderManager` | An `AuthenticationManager` implementation that coordinates providers. | Does not mean there must always be only one provider. |
| `AuthenticationProvider` | Verify the `Authentication` type it supports and produce an authenticated result or throw an error. | Does not decide the entire HTTP redirect / session cookie behavior. |
| `UserDetailsService` | Load `UserDetails` by username in the username/password model. | Not the place to compare the request password. |
| `PasswordEncoder` | Compare a raw password with a stored hash via `matches(raw, encoded)`. | Must not store passwords in plaintext in production. |
| `SecurityContextHolder` | Give code on the current thread access to `SecurityContext`. | Not a long-term session store. |
| `SecurityContextRepository` | Load/save context across dispatches/requests according to policy. | Does not automatically save every change in every configuration. |

In a real application, some filters may be absent, change order, or be replaced by other filters depending on configuration. The diagram is a conceptual model for understanding the processing flow, not a fixed exhaustive order list for every version.

## 2. What Does an HTTP Request Carrying "Credentials" Look Like?

Credentials are evidence the client provides to prove identity, such as a password, HTTP Basic credentials, a bearer token, or an assertion from an identity system. **A username or email alone is only a claimed identifier, not sufficient proof for authentication.**

With default Spring Security form login:

- The browser sends `POST /login` with form parameters `username` and `password`.
- The standard Spring Security form login configuration typically has `UsernamePasswordAuthenticationFilter` handling this URL.
- If CSRF protection is enabled (the appropriate default for cookie-based web applications), the form POST must include a valid CSRF token; the request can be blocked before reaching the authentication filter if the token is invalid.
- Data must be transmitted over **HTTPS** in real environments. Do not put passwords in the query string, as they easily leak into URLs, logs, and browser history.

With Basic authentication:

~~~http
GET /private HTTP/1.1
Host: example.test
Authorization: Basic <base64-credentials>
~~~

This is an **HTTP format illustration**, not a directly usable request, because `<base64-credentials>` is a placeholder. HTTP Basic uses Base64 to encode `username:password`, **not secure encryption**; HTTPS is still mandatory. `BasicAuthenticationFilter` can turn the data into an authentication request for `AuthenticationManager` to process.

With a bearer token:

~~~http
GET /api/orders HTTP/1.1
Host: example.test
Authorization: Bearer <access-token>
~~~

`BearerTokenAuthenticationFilter` processes bearer tokens in a correspondingly configured resource server. The token has its signature/claims verified or undergoes introspection depending on token type and configuration; it does **not** pass through `DaoAuthenticationProvider` just because it is also an authentication step. Do not put real tokens into logs or publicly shared examples.

## 3. *Unauthenticated* Token: The Input `Authentication` Object

`Authentication` is the central interface of Spring Security, encompassing the concepts:

- `getPrincipal()`: the object representing the identity; on input it may just be a username, and on output it may be `UserDetails` or a specialized principal.
- `getCredentials()`: the proof to verify, such as a password or token; after authentication, credentials may be erased.
- `getAuthorities()`: the list of authorities (`GrantedAuthority`) granted to the principal.
- `getDetails()`: mechanism-specific auxiliary information, such as request metadata; do not use it as trusted evidence without verification.
- `isAuthenticated()`: whether the token has been accepted by the authentication mechanism; this flag alone **does not by itself prove authorization for every resource**.

In a username/password flow, a filter can create:

~~~java
Authentication request = UsernamePasswordAuthenticationToken.unauthenticated(
    username, password
);
Authentication result = authenticationManager.authenticate(request);
~~~

**This is a Java snippet using Spring Security**, not a standalone Java SE program. It requires importing `org.springframework.security.core.Authentication`, `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`, `org.springframework.security.authentication.AuthenticationManager`, and having `username` and `password` variables extracted from a valid request.

When created via the `unauthenticated(...)` factory, the token represents only **the client's claim**. Do not create `UsernamePasswordAuthenticationToken.authenticated(...)` with an arbitrary authority list to "skip" the verification step: doing so can grant privileges to an unverified identity. A self-constructed object marked as authenticated does not replace the trust workflow of `AuthenticationProvider`.

### Input and Output Data

| Stage | Principal | Credentials | Authenticated | Authorities |
| --- | --- | --- | --- | --- |
| Form just submitted, before verification | Username provided by client | Raw password | `false` | Usually none yet |
| Provider authentication succeeds | Verified identity, e.g., `UserDetails` | May still exist during processing, then erased | `true` | Sourced from a trusted store/policy |
| Provider authentication fails | No trusted result | Must not be persisted/logged | No successful result produced | None granted |
| Subsequent authorization | Principal from the corresponding context | Usually password not needed | May be true, though token type and policy still matter | Checked against the specific access requirement |

`AnonymousAuthenticationToken` is a case to watch out for: this object can have `isAuthenticated() == true` while representing an **anonymous user**, not a logged-in user. Therefore, business code should not write `if (auth != null && auth.isAuthenticated())` and assume it means an authenticated login. Use authorization rules such as `authenticated()`, `hasAuthority(...)`, `hasRole(...)`, or an `AuthorizationManager` as required.

## 4. How Do `AuthenticationManager` and `ProviderManager` Coordinate?

The contract of `AuthenticationManager` can be visualized as:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

This is an **illustrative signature** from the Spring Security API; `AuthenticationException` is a Spring Security authentication error, not a Java SE exception. Success returns an authenticated `Authentication`; failure throws an exception rather than returning `false`.

A common implementation, `ProviderManager`, holds a list of `AuthenticationProvider` instances. Each provider indicates whether it supports a token type via `supports(Class<?>)`. `supports(...)` indicates capability to handle the token class; it **does not guarantee** the provider will successfully authenticate a specific token.

Conceptual example:

~~~text
AuthenticationManager.authenticate(
    UsernamePasswordAuthenticationToken{authenticated=false}
)
    |
    v
ProviderManager
    | -> DaoAuthenticationProvider.supports(...) = true
    |    -> read UserDetails
    |    -> check password, account status
    |    -> Authentication{authenticated=true} or AuthenticationException
    |
    | -> provider for another token: considered only if it can handle the token type
    v
result or AuthenticationException
~~~

When multiple providers exist, coordination also depends on the exception type and which provider returns a result: a provider can return `null` to give another provider a chance, or throw an exception; certain account-status errors can halt the flow immediately. Do not assume all providers act as an unconditional "OR". `ProviderManager` can have a parent manager, can publish authentication events through a publisher, and by default can erase sensitive credential data on the result via `eraseCredentialsAfterAuthentication`.

Common error groups:

| Outcome | General Meaning |
| --- | --- |
| `BadCredentialsException` | Credentials were rejected. |
| `UsernameNotFoundException` | User not found in the lookup layer (often masked as a generic credentials error to reduce username enumeration). |
| `DisabledException`, `LockedException`, `AccountExpiredException` | Account is not in a state allowed to authenticate. |
| `CredentialsExpiredException` | Credentials have expired under policy. |
| `ProviderNotFoundException` | No suitable provider available to process the token. |

Do not expose separate "username does not exist" and "wrong password" messages in a way that helps attackers enumerate accounts. Apply rate limiting, brute-force monitoring, account lockout policies, and MFA according to actual risk.

## 5. Inside `DaoAuthenticationProvider`: Checking Username/Password

Typical case for username/password backed by a database:

1. The provider receives an unauthenticated `UsernamePasswordAuthenticationToken`.
2. `UserDetailsService.loadUserByUsername(...)` looks up `UserDetails`. The data source can be a database, an LDAP adapter, or another service.
3. Account details such as enabled/locked/expired are checked according to policy/provider.
4. `PasswordEncoder.matches(rawPassword, storedEncodedPassword)` verifies the submitted password against the stored hash.
5. If valid, the provider returns an authenticated `Authentication` containing the appropriate principal and authorities. Downstream components may erase credentials from the result object.

### Storing Passwords Properly

Example using `BCryptPasswordEncoder`:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String encoded = encoder.encode("demo-only-password");

boolean accepted = encoder.matches("demo-only-password", encoded);
boolean rejected = encoder.matches("wrong-password", encoded);
~~~

This is a **Spring Security code snippet**, importing `org.springframework.security.crypto.password.PasswordEncoder` and `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`. The `encoded` value includes a random salt, so **a fixed output hash string cannot be hardcoded in advance**; the Boolean results in the example are `accepted == true` and `rejected == false`. Do not store literal passwords in production code, and do not use a plain hash function like raw SHA-256 as a password encoder instead of properly configured BCrypt/Argon2/PBKDF2.

`UserDetailsService` **only provides user data**; it does not verify the request's password itself. `PasswordEncoder` performs the hash comparison, while the provider manages the authentication process and result. This is an important boundary so a login module can swap data sources without rewriting servlet filters.

## 6. A Spring Boot 3 Example: From Form Login to Authentication

Create a Spring Boot 3.x application on Java 17+ with the appropriate dependencies:

- `spring-boot-starter-web` (Servlet/Spring MVC).
- `spring-boot-starter-security`.
- For the test below: `spring-boot-starter-test` and `spring-security-test` in test scope.

The configuration below uses an **in-memory user solely for learning purposes**. For production, use a real user store and place secrets in a secure configuration system; do not hard-code credentials in the repository.

### 6.1. `SecurityConfig.java`

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("training-only"))
            .roles("LEARNER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

When the application starts, Spring creates the `SecurityFilterChain`, `PasswordEncoder`, and `UserDetailsService` beans. In a standard form login configuration, the username/password mechanism uses `DaoAuthenticationProvider` and the appropriate `AuthenticationManager`. For a login request, the provider retrieves the corresponding `UserDetails`, checks the password via the encoder, and returns an authenticated result if valid.

`.roles("LEARNER")` creates the `ROLE_LEARNER` authority; note that `hasRole("LEARNER")` automatically applies the `ROLE_` prefix by convention, whereas `hasAuthority("ROLE_LEARNER")` compares the full authority name.

### 6.2. `DemoController.java`

~~~java
package com.example.demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String currentUser(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

`Authentication` is supplied to the controller by Spring MVC after the request has passed through the security chain. The `/me` endpoint requires an authenticated user because of `anyRequest().authenticated()` in the chain. The controller only demonstrates reading the principal and contains no custom password-checking code.

### 6.3. Progression in the Browser

~~~text
GET /me without a logged-in session
  -> authorization requires an authenticated user
  -> Spring Security redirects to the login page (typically redirect /login)

GET /login
  -> login page generated by Spring Security if not customized

POST /login (username=learner, password=training-only, valid CSRF)
  -> UsernamePasswordAuthenticationFilter creates request Authentication
  -> AuthenticationManager -> DaoAuthenticationProvider
  -> UserDetailsService retrieves learner + password hash
  -> PasswordEncoder.matches(...) => true
  -> result Authentication(authenticated=true, ROLE_LEARNER)
  -> SecurityContext is updated and saved per login flow/repository
  -> success handler redirects to saved request or default URL

GET /me with a valid session
  -> security context is loaded for the new request
  -> Authentication.getName() == "learner"
  -> HTTP 200, body "learner"
~~~

The sequence above is the **typical flow of stateful form login**. The exact redirect URL depends on the request cache, success handler, Spring Security config, and browser; do not assert that every login always redirects to the exact same path. The client must send the valid session cookie back on subsequent requests.

### 6.4. Trying with `curl` and CSRF

You can run the application via the Maven Wrapper (`./mvnw spring-boot:run` on Unix or `mvnw.cmd spring-boot:run` on Windows) once the project has a build file and Spring Boot main class. The following command:

~~~bash
curl -i http://localhost:8080/me
~~~

will typically receive a redirect to `/login` when unauthenticated. To test logging in with `curl` while CSRF is enabled, you must maintain a cookie jar, extract the CSRF token from the login page, and submit the token along with the POST and cookie. **Do not** simply POST username/password without CSRF and treat a `403` response as a password error.

For more accurate automated verification, use Spring Security Test (next section). In a browser, DevTools can help inspect status codes, redirects, and cookies, but do not copy session cookie values, passwords, or tokens into public logs or tools.

## 7. Testing the Real Authentication Flow with Spring Security Test

Assuming the classes in section 6 reside in the same Boot application with `@SpringBootApplication`, create `SecurityFlowTest.java`:

~~~java
package com.example.demo;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
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
class SecurityFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validCredentialsProduceAuthenticatedPrincipal() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                    .user("learner").password("training-only"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("learner"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));
    }

    @Test
    void badCredentialsDoNotAuthenticate() throws Exception {
        mvc.perform(formLogin()
                    .user("learner").password("wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(unauthenticated());
    }
}
~~~

`formLogin()` here is a **request builder from the spring-security-test library**, different from the `http.formLogin(...)` configurer. The test builder constructs a login request following default form login and handles CSRF appropriately to test the authentication branch. `authenticated()` and `unauthenticated()` are **Spring Security Test assertions**; the test does not invoke `AuthenticationManager` directly, so it exercises the integration of the filter, manager, provider, and security context.

The success test reuses the session from the login HTTP request to confirm that the result **persists to a subsequent request**. If your application is configured as stateless, swaps the repository, or changes the success handler or login URL, this test must be adjusted to the actual policy. Avoid treating status `302` or a session cookie as a rigid contract for every authentication style.

Run with the Maven Wrapper in the configured project:

~~~bash
./mvnw test
~~~

This command runs real tests and prints environment-dependent logs/build output, so no assumed "exact stdout" is listed. If another `SecurityFilterChain` matches `/login` or `/me`, you must re-examine chain ordering before interpreting results.

## 8. Standalone Java 17 Illustration: State Transition, Not Real Authentication

To clearly see the difference between an **unauthenticated request token** and an **authenticated result token** without depending on Spring, the Java SE example below models the transition decided by a provider. The `credentialsWereVerified` variable is a **simulated outcome of an external verification step**, not a way to check passwords. Real applications must use a password encoder or token verifier.

Create the file `AuthenticationTransitionDemo.java`:

~~~java
import java.util.Set;

public final class AuthenticationTransitionDemo {

    record Token(String principal, boolean authenticated,
                 Set<String> authorities) {}

    static Token provider(Token submitted, boolean credentialsWereVerified) {
        if (!credentialsWereVerified) {
            throw new IllegalArgumentException("Bad credentials");
        }

        return new Token(
                submitted.principal(),
                true,
                Set.of("ROLE_LEARNER")
        );
    }

    static void attempt(String username, boolean credentialsWereVerified) {
        Token incoming = new Token(username, false, Set.of());
        System.out.println("Submitted: " + incoming.authenticated());

        try {
            Token result = provider(incoming, credentialsWereVerified);
            System.out.println("Accepted: " + result.principal()
                    + ", authenticated=" + result.authenticated()
                    + ", authority=" + result.authorities().iterator().next());
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        attempt("learner", true);
        attempt("learner", false);
    }
}
~~~

Run:

~~~bash
javac AuthenticationTransitionDemo.java
java AuthenticationTransitionDemo
~~~

Exact stdout:

~~~text
Submitted: false
Accepted: learner, authenticated=true, authority=ROLE_LEARNER
Submitted: false
Rejected: Bad credentials
~~~

The `credentialsWereVerified` value is passed manually solely to simulate a provider's decision. It **does not take a password**, has no session management workflow, does not use the Spring Security API, and **must not be used as a login mechanism**. The key takeaway is that the input token is not treated as authenticated; only when the provider produces a successful outcome is a result token created with a trusted identity and authorities.

## 9. After Success: SecurityContext, Session, and Thread Lifecycle

`AuthenticationManager.authenticate(...)` returning a successful `Authentication` **does not automatically** mean every subsequent request is logged in. There are steps outside the manager:

1. The authentication filter receives the result from the manager.
2. An appropriate `SecurityContext` is created/updated to hold the result.
3. `SecurityContextHolder` binds the context to the **current processing thread**.
4. Depending on the mechanism, the authentication filter may execute `SessionAuthenticationStrategy` to handle session fixation, concurrent sessions, or other policies.
5. For stateful login, the context must be saved by the authentication mechanism into the appropriate `SecurityContextRepository` per configuration; the response may carry a session cookie.
6. The success handler decides the response (redirect, status, cookie, etc.) based on the authentication type.
7. When the security filter chain finishes, the holder on the thread is cleared, while the context saved in the session/repository can be reloaded on the next request.

In modern Spring Security Servlet, `SecurityContextHolderFilter` provides context loading (which can be deferred) and **clears the holder** when exiting the filter. With the **explicit-save** model, this filter **does not automatically save the context when the request ends**; authentication components must save to the repository when login persistence is desired. Spring Security's built-in form login already integrates the appropriate save flow; if you write a custom authentication filter, you must control the save step as well according to the current configuration.

An illustrative snippet for a **custom authentication filter**, after verifying the request:

~~~java
Authentication verified = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(username, password)
);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

This is **not yet a complete filter**. It requires importing `org.springframework.security.core.Authentication`, `org.springframework.security.core.context.SecurityContext`, `org.springframework.security.core.context.SecurityContextHolder`, and the manager/repository types; it also still needs error handling, session strategy, success/failure handlers, CSRF, cookies, and login method/URL handling. **Do not copy this snippet directly into a controller** to create a new login lacking those standard components. When using a built-in filter, prefer configuring it rather than copying core logic yourself.

**Clearing the holder is not logging out:** `SecurityContextHolder.clearContext()` only removes the thread's context; it does not invalidate the session or delete saved state. Logout must use Spring Security's logout mechanism and the appropriate repository/session cleanup operations.

## 10. Which Path Does Failed Authentication Take?

If credentials are wrong or rejected:

~~~text
Authentication filter
  -> AuthenticationManager.authenticate(...)
      -> AuthenticationException
  -> failure path:
       no trusted result is created
       clear/stop using invalid context from this attempt
       handle remember-me failure / session per configuration
       failure handler or AuthenticationEntryPoint builds response
  -> no new authenticated principal is granted by this attempt
~~~

With default form login, failure typically leads to a redirect like `/login?error`; with HTTP Basic missing/invalid credentials, the response is typically `401 Unauthorized` with `WWW-Authenticate`; with an invalid bearer token, it is typically `401` per the bearer token mechanism. Exact status codes and headers depend on the authentication entry point, failure handler, and the application's security chain.

Do not treat `ExceptionTranslationFilter` as the place that directly resolves **every** login failure: authentication filters based on `AbstractAuthenticationProcessingFilter` have their own success/failure flows. `ExceptionTranslationFilter`'s role is to translate `AuthenticationException` or `AccessDeniedException` from downstream processing into appropriate HTTP behavior when they propagate to it.

Distinguish clearly:

| Case | Logical Outcome |
| --- | --- |
| No credentials, accessing an endpoint requiring login | Triggers the appropriate authentication entry point (redirect/401). |
| Credentials provided but wrong | Authentication fails; no new authenticated principal granted. |
| Authenticated but lacking authority for the resource | Authorization fails; usually `403 Forbidden`, may vary by context. |
| Login succeeds but next request is still anonymous | Check session cookie, repository, explicit save, stateless policy, and chain matching. |

The cases above may all lead to an "unable to access" screen, yet the fixes are completely different: missing login requires authentication; missing permission requires authorization; losing login between requests relates to persistence and client cookies/sessions.

## 11. Authentication Variants Not Using a Form Password

Same overarching model, but with different tokens and providers:

| Mechanism | Input Credentials | Typical Filter / Provider | Default Session? |
| --- | --- | --- | --- |
| Form login | Form username + password | `UsernamePasswordAuthenticationFilter` → `DaoAuthenticationProvider` | Typically uses session for login state in stateful web apps. |
| HTTP Basic | `Authorization: Basic ...` | `BasicAuthenticationFilter` → matching username/password provider | Does not require creating a session just to verify each request; depends on overall policy. |
| OAuth2 Resource Server JWT | `Authorization: Bearer token` | `BearerTokenAuthenticationFilter` → `JwtAuthenticationProvider` / `JwtDecoder` | Usually stateless, validating the token on the current request. |
| OAuth2 Resource Server opaque token | Bearer token | Bearer filter → `OpaqueTokenAuthenticationProvider` / introspector | Usually stateless, verifying via introspection. |
| SSO/OIDC login | Authorization code and response parameters | Filters/login handlers of `oauth2Login`, client and corresponding provider | Typically web login with session, depending on configuration. |

An application can have multiple `SecurityFilterChain`s: for example, `/api/**` using bearer tokens and the web UI using form login. When debugging, confirm **which chain selects the request**. You cannot fix authentication by adding `DaoAuthenticationProvider` if the request actually carries a JWT and is handled by the resource-server chain.

In REST systems, storing the result in an HTTP session is not strictly required: when a bearer token is sent on every request, the provider re-verifies it or uses appropriate caching/checks; each request's `SecurityContext` still exists for the duration needed to authorize. `SessionCreationPolicy.STATELESS` does not mean "skip `SecurityContextHolder`".

## 12. Common Pitfalls

### Pitfall A: "Having a username means already logged in"

A username is client-supplied data and can be forged. Only a provider or trusted authentication mechanism grants an authenticated result. If code writes:

~~~java
Authentication forged =
        UsernamePasswordAuthenticationToken.authenticated(
                username, null, authorityList
        );
~~~

then the code has **self-asserted successful authentication** without verification. This is a **security anti-pattern; never apply it to untrusted input**. It shows why the application must go through the manager/provider rather than directly constructing an authenticated result from user input.

### Pitfall B: "UserDetailsService will compare the password"

`UserDetailsService` only loads user details; the provider combines that data with `PasswordEncoder.matches(...)` to decide. If you want to swap the database, replace the appropriate adapter/service/repository; do not put password checking in a controller and set a flag.

### Pitfall C: "Authenticated means having all permissions"

No. `Authentication` represents authentication, whereas `AuthorizationFilter`, `AuthorizationManager`, method security, and other policies check specific requirements. `ROLE_LEARNER` does not automatically grant access to admin endpoints. Anonymous tokens and special authorities further illustrate why meaningful authorization rules are needed.

### Pitfall D: "Losing context in an async task means login failed"

`SecurityContextHolder` is bound to the current thread by default. Tasks run by `@Async`, `CompletableFuture`, or a custom executor do not inherently have the request's context. Pass minimal required data or use context propagation mechanisms such as the appropriate `DelegatingSecurityContext...` wrappers; ensure cleanup after the task. Do not use `InheritableThreadLocal` as a general solution for thread pools.

### Pitfall E: "Successful login guarantees session persistence"

With explicit-save and custom authentication flows, forgetting `SecurityContextRepository.saveContext(...)` can cause the next request to revert to anonymous. Conversely, valid stateless token authentication may intentionally **not save** between requests. The two models differ; not every model needs a session.

### Pitfall F: "CSRF must be disabled to test POST /login"

CSRF protects state-changing browser requests that rely on cookies. Tests should supply a valid CSRF token; disabling CSRF without evaluating the actual authentication model can introduce vulnerabilities. Spring Security Test provides appropriate request builders for testing form login.

### Pitfall G: "All filters are basically the same"

`UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter`, and `BearerTokenAuthenticationFilter` differ in input type, trigger condition, response, and authentication mechanism. `securityMatcher(...)` determines the matching chain; `requestMatchers(...)` inside `authorizeHttpRequests(...)` only determines authorization rules within that chain. Do not mistake a path hitting the wrong chain for a password error.

### Pitfall H: "Changing isAuthenticated to true bypasses verification"

The authenticated flag alone does not make a request trustworthy. If the application marks a token authenticated by itself, it can create a privilege escalation vulnerability. For passwords, always rely on the provider and encoder; for tokens, rely on the verifier/decoder plus full policy checks.

## 13. Ordered Implementation and Diagnostic Checklist

1. **Identify the actual request:** endpoint, method, body/headers, and HTTPS; did credentials reach the server in the expected format?
2. **Check chain matching:** did `FilterChainProxy` select the right `SecurityFilterChain`? Is the corresponding authentication filter in that chain?
3. **Verify filter conditions:** did form login receive `POST /login` and the expected parameter names? Is the CSRF token valid? Are Basic/Bearer headers well-formed?
4. **Check the input token:** does the `Authentication` type match the manager/provider, and is `isAuthenticated()` initially false?
5. **Check the provider:** does a provider `supports(...)` the token? Did `UserDetailsService` find the right user? Is the account locked/disabled/expired?
6. **Check credentials:** does `PasswordEncoder.matches(...)` compare against a properly formatted hash? A salted BCrypt hash must never be compared via direct `equals` against a raw password.
7. **Check the result:** does the verified authentication result have a trusted principal and authorities without self-setting flags from client input?
8. **Check SecurityContext:** did the filter place the result properly into the holder for the current execution? Is it cleaned up at the end of the chain?
9. **Check login persistence:** did the auth flow save the context to the repository when required? Does the client retain the right session cookie? Is session fixation protection active?
10. **Separate authn/authz:** valid login receiving `403` can mean insufficient authority; do not "fix" it by removing authorization.
11. **Check the exception path:** is a wrong password handled safely as a credentials error without leaking user existence or passwords, and without logging secrets?
12. **Test multi-request/async behavior:** users A and B do not leak across thread-locals; subsequent stateful requests have the right context; background tasks propagate context as designed.

**Never log** raw passwords, Bearer access tokens, Basic headers, full session IDs, or `Authentication.credentials`. Only record minimal diagnostic metadata such as correlation ID, authentication mechanism type, request path, and sanitized error type.

## 14. Self-Check Questions

**Q1. Why must a filter create an unauthenticated token?** Because credentials arriving from the client are untrusted data. A provider must verify them first before producing an authenticated result.

**Q2. How does `ProviderManager` differ from `DaoAuthenticationProvider`?** `ProviderManager` selects/coordinates providers by token type; `DaoAuthenticationProvider` is one way to authenticate username/password using `UserDetailsService` and `PasswordEncoder`.

**Q3. Does `UserDetailsService` verify the password?** No. It loads `UserDetails`; password matching is handled by the provider/encoder and authentication policy.

**Q4. Does a successful `Authentication` result automatically save into a session?** No. The authentication filter, session strategy, and repository handle placing it into the context and saving it according to configuration. Stateless resource servers may not save between requests.

**Q5. If login succeeds but an admin resource cannot be accessed, does that mean the password is wrong?** Not necessarily. Authentication may have succeeded while authorization denied access due to missing permissions.

**Q6. Does form login with a wrong password return HTTP 401 or a redirect?** By default, form login may redirect to `/login?error`; Basic/Bearer usually return `401`. Look at the actual mechanism and handler instead of assuming a fixed status code.

**Q7. Why shouldn't Spring Security code rely solely on `authentication.isAuthenticated()` to check if someone is logged in?** Because an anonymous token can also report true, and access decisions must consider authentication type, authorities, and authorization policy.

**Remember:** `untrusted credentials → unauthenticated authentication request → AuthenticationManager/Provider verification → authenticated Authentication result → SecurityContext → authorization and state persistence (if needed)`. Each arrow is a distinct responsibility boundary that must be preserved in security design.
