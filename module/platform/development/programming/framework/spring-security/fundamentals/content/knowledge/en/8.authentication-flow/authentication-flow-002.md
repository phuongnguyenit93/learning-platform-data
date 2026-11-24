# AuthenticationManager Receiving and Returning Authentication in Spring Security

In Spring Security, **`AuthenticationManager`** is the central interface of the authentication process: it **receives an `Authentication` object representing an unverified request**, checks the request through the configured authentication mechanism, and **returns a trusted result `Authentication` on success**. If authentication cannot succeed, the method reports failure with an appropriate `AuthenticationException`.

Both sides of the method can share the same Java interface type `Authentication` yet **do not share the same level of trust**:

- **Input:** information provided by the client or extracted by a filter, such as username/password, not yet considered an authenticated identity.
- **Output:** verified principal, authenticated status, and `GrantedAuthority` instances granted from a trusted source. Sensitive credentials may have been erased.
- **Failure:** the method **throws an exception**, rather than issuing a fake successful authentication object.
- **After receiving the result:** the caller of the manager, typically a security filter, handles `SecurityContext`, session, or token mechanisms according to the corresponding flow.

This lesson focuses on the question: **What does `AuthenticationManager.authenticate(...)` actually receive, do, and return, who uses the result, and why should you never manually set authenticated=true?** Examples use **Spring Boot 3.x with Spring Security 6.5, Java 17+, Spring MVC/Servlet**; APIs or behaviors specific to Spring Security 7, OAuth2, or WebFlux should be verified against the version in use.

## 1. The AuthenticationManager Contract

The `AuthenticationManager` interface resides in the package `org.springframework.security.authentication`. Its core contract is described by a single method:

```java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
```

This is a condensed form for study, not the full Javadoc declaration. Common names involved:

| Component | Role | Usage |
| --- | --- | --- |
| `AuthenticationManager` | Interface defining the **authentication contract** | Caller passes `Authentication` into `authenticate` |
| `ProviderManager` | Common `AuthenticationManager` implementation | Coordinates multiple `AuthenticationProvider` instances |
| `AuthenticationProvider` | Authenticates a specific `Authentication` type | Verifies credentials/identity source; may not support the request type |
| `Authentication` | Authentication request or result | `principal`, `credentials`, `authorities`, `isAuthenticated` |
| `AuthenticationException` | Authentication error hierarchy | Wrong password, locked account, unsupported token... |
| `SecurityContextHolder` | Place to access the current `SecurityContext` | Updated by the filter/caller flow after successful authentication |

`AuthenticationManager` is **not** an authorization mechanism. It returns a trusted identity and authorities so that rules like `hasRole("ADMIN")` or `hasAuthority("report:read")` can evaluate them later.

### 1.1. Why are both input and output of type Authentication?

Spring Security uses the shared `Authentication` abstraction for two roles:

1. Carrying authentication evidence and the claimed identity to the manager.
2. Carrying the verified result back to the filter, controller, or service responsible for establishing the context.

Example input:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "password-from-client"
    );
```

Then:

```java
Authentication result = authenticationManager.authenticate(request);
```

At this point `request.isAuthenticated()` is `false`, while `result.isAuthenticated()` in a standard successful authentication flow is `true`. `result.getPrincipal()` can be the verified `UserDetails`; `result.getAuthorities()` contains the permissions attached from the user store/provider. `result.getCredentials()` may already be `null` due to sensitive data erasure.

### 1.2. What must you never do?

Never construct a "successful" result from unverified data:

```java
// Anti-pattern: no credential verification or trusted authority source.
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        requestBody.username(),
        null,
        requestBody.roles().stream()
            .map(SimpleGrantedAuthority::new)
            .toList()
    );
```

The `authenticated(...)` factory **only creates an object carrying the authenticated state**. It does not prove the username/password is valid, does not validate any token, and does not verify client-supplied `roles`. Only a component inside the trust boundary that actually performed authentication may create a trusted result.

## 2. Reading Authentication Values Before and After authenticate()

Suppose Alice sends a valid username/password; the user store grants `ROLE_USER` and `report:read`.

| Property | Input `Authentication` | Successful result `Authentication` |
| --- | --- | --- |
| `getPrincipal()` | Usually the client-claimed `"alice"` string | Usually the retrieved and verified `UserDetails` object |
| `getCredentials()` | Raw password passed to the provider | May be erased (`null`) after authentication |
| `getAuthorities()` | Usually empty/no trusted authorities yet | Contains `ROLE_USER`, `report:read` from the user store |
| `isAuthenticated()` | `false` with `unauthenticated(...)` | `true` if the provider returns a verified result |
| `getName()` | May return the client-claimed name | Name according to the verified principal |
| Trust level | Not yet accepted | Successfully verified by the provider |
| How the app uses it | As evidence to be verified | Placed in security context and evaluated against policy |

`getName() == "alice"` on the **input** is not proof of the real Alice. `getName() == "alice"` on the **output** is meaningful after the provider checks credentials and user status under the trust policy.

Do not assume the manager always **mutates the input object itself**. A provider may create **a new Authentication object** or use a different representation. Application code must use **the value returned** from `authenticate`:

```java
Authentication request = UsernamePasswordAuthenticationToken
    .unauthenticated("alice", password);

Authentication verified = manager.authenticate(request);

// Correct: use verified.
// Wrong: ignore verified and treat the initial request as authenticated.
```

Do not cast input or output to `UsernamePasswordAuthenticationToken` if the system has multiple authentication mechanisms. `Authentication` is an interface; the concrete type depends on the provider and authentication method.

## 3. Real Servlet Flow: Who Calls AuthenticationManager?

A typical request using HTTP Basic or form login:

```text
Client
  |  username/password in Basic header or login form
  v
SecurityFilterChain
  |
  +-- Authentication filter receives request
  |      |
  |      +-- Create authentication request Authentication
  |      |       principal = claimed username
  |      |       credentials = password
  |      |       authenticated = false
  |      |
  |      v
  |  AuthenticationManager.authenticate(request)
  |      |
  |      v
  |  ProviderManager
  |      |
  |      v
  |  Matching AuthenticationProvider
  |      |
  |      +-- Verify identity / evidence / account status
  |      +-- Assign authorities from trusted source
  |      |
  |      +-- FAILURE -> AuthenticationException
  |      |       -> failure handler / entry point, per mechanism
  |      |
  |      +-- SUCCESS -> Verified Authentication
  |              |
  |              +-- Credentials may be erased
  |              v
  |        Filter receives result
  |              |
  |              +-- SecurityContext / SecurityContextRepository
  |              +-- Session or token handling as appropriate
  |              v
  +-- AuthorizationFilter / method authorization
  |      |
  v      v
 Controller / Service
```

This diagram is a **responsibility model**, not a guarantee of exact filter order across every mechanism. A request may be blocked by CSRF before reaching the controller; with sessions, Authentication may be restored without calling the password provider on every request.

### 3.1. Filter creates input; manager does not read HTTP directly

`AuthenticationManager.authenticate` accepts only an `Authentication` object; it has no `HttpServletRequest` or `HttpServletResponse` parameters. A concrete filter such as `BasicAuthenticationFilter` or `UsernamePasswordAuthenticationFilter` is responsible for reading the request, creating the appropriate token, and passing it to the manager.

This allows different authentication methods to share a common contract. HTTP Basic and form login can both create a `UsernamePasswordAuthenticationToken`, though not every mechanism uses that type.

### 3.2. AuthenticationManager does not emit 401/403 directly

The manager usually **throws an exception** if authentication fails. Translating that exception into an HTTP response belongs to security filters/handlers:

- Missing or invalid HTTP Basic credentials usually return **401 Unauthorized** with a `WWW-Authenticate` challenge.
- Failed form login may redirect to `/login?error` instead of returning JSON 401.
- An authenticated user lacking `ROLE_ADMIN` usually receives **403 Forbidden** from **authorization**.
- An invalid CSRF token can also produce 403, unrelated to authorities.

A non-HTTP caller (for example a command-line job) can catch `AuthenticationException` and handle it in its own way, because `AuthenticationManager` is not coupled directly to HTTP status codes.

### 3.3. AuthenticationEntryPoint and AuthenticationFailureHandler

`AuthenticationEntryPoint` initiates an authentication request to the client when a resource requires credentials. `AuthenticationFailureHandler` typically handles failure of a login submission according to the mechanism. Neither component is an `AuthenticationManager`.

Depending on the filter and exception handling, the same `BadCredentialsException` may be presented differently across web UIs, APIs, or tests. Inspect the configured mechanism rather than inferring HTTP status solely from the exception name.

## 4. How Do AuthenticationProvider and ProviderManager Collaborate?

Most applications do not implement `AuthenticationManager` directly. Spring Security uses `ProviderManager` with one or more `AuthenticationProvider` instances.

Model:

```text
AuthenticationManager  (interface)
        |
        v
ProviderManager         (implementation)
        |
        +-- Provider A: DaoAuthenticationProvider
        |       supports UsernamePasswordAuthenticationToken
        |
        +-- Provider B: JWT / SAML / custom provider per system
        |       supports its own token type
        |
        +-- Provider C: another specialized mechanism
        |
        +-- Parent AuthenticationManager (if configured)
        |
        +-- Result Authentication or AuthenticationException
```

Do not assume every provider always runs. `ProviderManager` evaluates each provider's support and result according to configuration.

### 4.1. AuthenticationProvider contract

A provider has two primary methods:

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
```

Here:

- `supports(...)` states **which Authentication type** the provider can handle.
- If a provider **does not support** the request type, the manager can skip it and check another provider.
- If called but **unable to reach a conclusion**, the provider can return `null` so the coordinator tries the next provider.
- If verification **succeeds**, the provider returns the result Authentication.
- If credentials or authentication conditions **fail**, the provider can throw an appropriate `AuthenticationException`.

**Distinction needed:** a provider may return null to indicate "no decision"; for callers of `AuthenticationManager`, the standard contract is **return an authenticated object or throw an exception**, never treat null as "successful login without a user".

### 4.2. Multiple providers and parent manager

`ProviderManager` can coordinate multiple providers. Some providers only support username/password; another provider supports a custom token type. When a parent `AuthenticationManager` is configured, the child manager can delegate to the parent under actual runtime conditions.

This is useful in applications with multiple `SecurityFilterChain` beans:

```text
/api/** chain -> API manager -> token provider
                         |
                         +-- shared parent manager

/web/** chain -> Web manager -> password provider
                         |
                         +-- shared parent manager
```

This diagram is an architectural example you can design, **not an implication that Boot automatically creates all those managers**. With multiple chains/providers, identify exactly which manager/filter processes a given request to avoid a provider being used outside its intended scope.

### 4.3. When no provider supports the token type

If an `Authentication` type is submitted that **no provider handles** and no parent satisfies it, `ProviderManager` can throw `ProviderNotFoundException`.

For example, do not confuse `supports(UsernamePasswordAuthenticationToken.class)` with always succeeding at login. `supports` only indicates the request type understood. The provider still needs to verify the username/password and account conditions.

### 4.4. Why should you not create ProviderManager instances arbitrarily?

Creating multiple `ProviderManager` instances arbitrarily or injecting a manager unattached to the HTTP chain can cause requests to be processed by unexpected providers. When you need to expose a manager as a bean, explicitly configure its `AuthenticationProvider`, `UserDetailsService`, and `PasswordEncoder`, and bind it to the chain when appropriate.

For normal username/password web applications, Spring Boot and Spring Security can already configure the manager/provider from user store beans; **writing an AuthenticationManager bean manually is not strictly necessary**. Only create a dedicated manager when there is a clear need, such as direct calls from a service or designing a custom provider list.

## 5. DaoAuthenticationProvider: Username/Password Authentication Example

`DaoAuthenticationProvider` is an `AuthenticationProvider` that uses `UserDetailsService` and `PasswordEncoder` to verify username/password.

Conceptual process:

1. Receives an unauthenticated `UsernamePasswordAuthenticationToken`.
2. Reads the username from the token to call `UserDetailsService.loadUserByUsername(...)`.
3. Checks account status according to provider capabilities and the `UserDetails` type.
4. Retrieves the password hash from `UserDetails` and uses `PasswordEncoder.matches(rawPassword, storedHash)` to verify.
5. If invalid, throws the corresponding authentication error.
6. If valid, creates the result Authentication with the verified principal and appropriate authorities.
7. `ProviderManager` may erase sensitive credentials from the result afterward.

Example user store setup:

```java
UserDetails alice = User.withUsername("alice")
    .password(passwordEncoder.encode("demo-alice-pass"))
    .authorities("ROLE_USER", "report:read")
    .build();

UserDetailsService users = new InMemoryUserDetailsManager(alice);
```

This is a Spring Security snippet using imported classes and a configured encoder bean; it will not compile standalone with `javac` without dependencies.

**Points to remember:**

- `loadUserByUsername` **does not compare passwords itself**; it returns data for the provider to verify.
- `PasswordEncoder` **does not grant authorities itself**; it checks whether a raw password matches a hash.
- `AuthenticationManager` coordinates via providers; it does not read SQL or JWTs in a single hardcoded way for every application.
- `getAuthorities()` on the result normally comes from a **trusted** user store/provider/converter, not from a client-submitted roles array.
- `PasswordEncoder.encode(raw)` may use salt, so never compare two `encode` outputs with string equals; always use `matches`.
- Demo passwords are for learning only; real deployments require HTTPS, secret management, and an architectural user database/IdP.

### 5.1. Role of UserDetails

`UserDetails` describes the principal in many username/password flows. It holds username, password hash, authorities, and account status flags like enabled and account non-locked. After success, `Authentication.getPrincipal()` is usually a `UserDetails` rather than the input username string.

However, do not write:

```java
UserDetails user = (UserDetails) authentication.getPrincipal();
```

everywhere if the application also supports JWT/OIDC or custom providers. With a JWT resource server, the principal may be `Jwt`; with OAuth2 login, it may be `OAuth2User`. Rely on the configured mechanism, or use an adapter that normalizes subject IDs.

## 6. Exception Contract: When Does authenticate Fail?

`AuthenticationManager.authenticate(...)` may throw subclasses of `AuthenticationException`.

| Exception / group | Common scenario | Meaning |
| --- | --- | --- |
| `BadCredentialsException` | Username/password not accepted | Credentials invalid according to the provider |
| `DisabledException` | Account is disabled and manager can check status | Should not authenticate as an active account |
| `LockedException` | Account is locked and manager checks it | Rejects locked account |
| `CredentialsExpiredException` | Credentials have expired per policy | Requires credential update flow |
| `ProviderNotFoundException` | No provider/parent supports the submitted Authentication type | Manager lacks capability to handle the request |
| `AuthenticationServiceException` | Authentication service / related system error | Do not assume it is simply a wrong password |

Per the Javadoc contract, if disabled/locked status can be checked, those conditions should take appropriate precedence before checking credentials to avoid testing passwords on disabled/locked accounts. Error details returned to the client **must not reveal** whether an account exists.

### 6.1. Why not use null to signal failure?

In code calling `AuthenticationManager`, the pattern is:

```java
try {
    Authentication verified = manager.authenticate(request);
    // Use the authenticated verified result.
} catch (AuthenticationException failure) {
    // Handle authentication failure; do not grant access.
}
```

**Do not write** `if (manager.authenticate(request) == null)` to check for a wrong password as a general API pattern; that is not a contract manager callers should rely on. Use exceptions and the defined provider/filter behavior.

### 6.2. Do not expose raw exceptions in responses

For custom REST or form login, use an appropriate entry point/failure handler. The message shown to the client can be "Invalid login credentials" instead of exposing exact reasons like disabled account, user not found, or wrong password, to reduce user enumeration. Internally, keep proper audits and metrics without logging raw credentials, password hashes, access tokens, or session cookies.

### 6.3. Never swallow service errors into a successful Authentication

If the user database or IdP does not respond, the policy must **deny or report a controlled error**, never build an authenticated Authentication from client-supplied claims. Fail-closed behavior may return 503 for infrastructure errors instead of 401/403; that is a separate API decision, not a reason to let the request through.

## 7. Credential Erasure After Authentication: An Easily Misunderstood Detail

`ProviderManager` by default erases credentials from a successful Authentication when appropriate, typically via `CredentialsContainer.eraseCredentials()`. For `UsernamePasswordAuthenticationToken`, credentials are normally erased after authentication.

Example:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "demo-alice-pass"
    );

Authentication result = manager.authenticate(request);

System.out.println(result.isAuthenticated());   // true, if successful
System.out.println(result.getCredentials());    // usually null
```

Do not claim every provider/token always yields `getCredentials()==null`. Other authentication mechanisms may retain different data; the rule is **never store or log secrets beyond valid operational necessity**.

### 7.1. Null credentials does not mean logged out

If `result.isAuthenticated()==true` and principal/authorities are valid, `getCredentials()==null` after secret erasure does not mean the user was logged out. In practice, Spring Security still relies on the appropriate session/token/context to decide subsequent requests.

At the same time, **isAuthenticated true alone is not enough** to grant every permission; with an anonymous token, this flag can be true at the object level, while Spring Security's `authenticated()` policy distinguishes anonymous users.

### 7.2. Caution with cached UserDetails

If the provider and a cache share the same `UserDetails` reference, erasing credentials on the resulting Authentication may also erase the password field on the cached object. The next authentication attempt may then have no hash left to verify.

Appropriate ways to handle this include:

- Returning a copy of `UserDetails` when retrieving from cache/provider;
- Designing caches not to share objects subject to credential erasure;
- Reviewing the lifecycle of caching, provider, and password hash;
- Changing `eraseCredentialsAfterAuthentication` only after evaluating the risk of retaining sensitive data in memory.

Never disable credential erasure just to "make a test pass" without understanding the consequences.

## 8. After authenticate(): Who Saves the SecurityContext?

The most important architectural point: **calling `AuthenticationManager.authenticate` directly does not automatically turn the current HTTP request or future requests into a session-backed login**.

In a flow managed by Spring Security filters, the filter calls the manager and then processes the result; the filter can update `SecurityContextHolder`, persist the context via `SecurityContextRepository`, and run session strategies, success handlers, or remember-me depending on the mechanism.

Contrast:

```java
Authentication verified = manager.authenticate(request);

// verified is the authentication RESULT.
// Calling the manager directly in a service does not guarantee:
// - SecurityContextHolder has been set,
// - HttpSession has been created/saved,
// - cookie has been sent,
// - JWT/refresh token has been issued,
// - the next request automatically carries this identity.
```

A condensed example of setting context for a **custom-designed flow**, illustrating only the step on the current thread:

```java
SecurityContext newContext =
    SecurityContextHolder.createEmptyContext();
newContext.setAuthentication(verified);
SecurityContextHolder.setContext(newContext);
```

This snippet is **not a complete login endpoint**. When login must persist across requests, the application also needs `SecurityContextRepository.saveContext(...)` per the session mechanism, handling session fixation, CSRF, cookies, and proper success/failure flows. With stateless token APIs, issuing tokens and verifying them on subsequent requests is a separate design. Prefer supported form login/HTTP Basic/OAuth2 integrations rather than building a custom login controller missing protective steps.

### 8.1. Why create a new SecurityContext?

Spring Security recommends using `SecurityContextHolder.createEmptyContext()` and setting Authentication on that new context when doing it manually, rather than unconditionally mutating a context that could be shared. This reduces the risk of cross-thread issues in specialized configurations.

### 8.2. ThreadLocal and asynchronicity

In a standard Servlet model, `SecurityContextHolder` uses a thread-bound strategy. This does not mean Authentication automatically propagates to `CompletableFuture`, manually spawned threads, or background jobs. When asynchronous work must run under a user's identity, choose an appropriate context propagation mechanism and restrict permissions accordingly. Never use a global context containing an admin Authentication for all threads.

### 8.3. Distinguishing authentication and authorization

The manager verifies identity and produces authorities; `AuthorizationManager` or Spring Security rules evaluate access rights:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

User Alice may have been authenticated by the manager yet lack `ROLE_ADMIN`, so GET `/api/admin` is still blocked. `isAuthenticated()` does not replace `hasRole`, `hasAuthority`, and owner/tenant checks.

## 9. Spring Boot 3 / Spring Security 6.5 Example: Real Manager and Real Results

This exercise uses Java 17+, Spring MVC, and HTTP Basic, while **exposing an `AuthenticationManager` bean** so it can be called directly in `CommandLineRunner` and tests. The configuration creates a `ProviderManager` with a `DaoAuthenticationProvider`. The HTTP API uses **that exact manager** via `HttpSecurity.authenticationManager(manager)`, connecting theory to a real running system.

Demo accounts:

| Username | Test password | Authorities | Status |
| --- | --- | --- | --- |
| `alice` | `demo-alice-pass` | `ROLE_USER`, `report:read` | enabled |
| `admin` | `demo-admin-pass` | `ROLE_USER`, `ROLE_ADMIN` | enabled |
| `disabled` | `demo-disabled-pass` | `ROLE_USER` | disabled |

To run the example, use **Spring Boot 3.x managing a compatible Spring Security 6.5 version**; the `DaoAuthenticationProvider(UserDetailsService)` constructor API exists in Spring Security 6.5. If an older Boot 3 project resolves Spring Security 6.0–6.4, check the exact Javadoc/constructor or upgrade dependencies consistently via the BOM rather than mixing individual JARs.

### 9.1. Gradle dependencies

In a Spring Boot project with plugins, repository, Java toolchain, and dependency management configured, the `dependencies` block of `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is a **dependency snippet**, not a complete Gradle project. With Maven, use the two equivalent starters and `spring-security-test` in test scope. Do not hardcode a Spring Security version different from the Boot BOM without checking compatibility.

### 9.2. Main class

Create `src/main/java/example/authmanager/AuthenticationManagerDemoApplication.java`:

```java
package example.authmanager;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthenticationManagerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationManagerDemoApplication.class, args);
    }
}
```

### 9.3. SecurityConfig: defining and attaching the manager

Create `src/main/java/example/authmanager/SecurityConfig.java`:

```java
package example.authmanager;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
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
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice-pass"))
            .authorities("ROLE_USER", "report:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-pass"))
            .authorities("ROLE_USER", "ROLE_ADMIN")
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(encoder.encode("demo-disabled-pass"))
            .authorities("ROLE_USER")
            .disabled(true)
            .build();

        return new InMemoryUserDetailsManager(alice, admin, disabled);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder
    ) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            AuthenticationManager manager
    ) throws Exception {
        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/identity")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Each component has a clear responsibility:

1. `PasswordEncoder` hashes passwords when initializing the user store. Do not use plaintext or `{noop}` for real accounts.
2. `UserDetailsService` stores users and trusted permissions in memory for the demo; production uses a DB/IdP.
3. `DaoAuthenticationProvider` loads users from the store and checks passwords with the encoder.
4. `ProviderManager` coordinates the provider and is the `AuthenticationManager` implementation exposed as a Spring bean.
5. `HttpSecurity.authenticationManager(manager)` applies this manager to the created security chain.
6. `httpBasic` enables the HTTP Basic filter; this is where HTTP requests are converted into input Authentication objects.
7. `authorizeHttpRequests` is **authorization**: even if login succeeds, the right role is still required for `/api/admin`.
8. `anyRequest().denyAll()` blocks undeclared HTTP URLs. Real projects may have other public/login routes that must be declared explicitly.
9. Default CSRF security remains enabled for protected methods; this example uses only GET to stay focused on authenticate.

This configuration clearly illustrates the **manager–provider relationship**, not a recommendation that every Spring Boot app must manually declare its own provider and manager.

### 9.4. Directly observing authenticate at startup

Create `src/main/java/example/authmanager/AuthenticationInspector.java`:

```java
package example.authmanager;

import java.util.stream.Collectors;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;

@Configuration
public class AuthenticationInspector {

    @Bean
    CommandLineRunner inspectManager(AuthenticationManager manager) {
        return args -> {
            Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "demo-alice-pass"
                );

            System.out.println(
                "demo.request.authenticated=" + request.isAuthenticated()
            );
            System.out.println(
                "demo.request.authorities=" + request.getAuthorities().size()
            );

            Authentication result = manager.authenticate(request);

            String authorities = result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));

            System.out.println(
                "demo.result.name=" + result.getName()
            );
            System.out.println(
                "demo.result.authenticated=" + result.isAuthenticated()
            );
            System.out.println(
                "demo.result.authorities=" + authorities
            );
            System.out.println(
                "demo.result.credentialsErased="
                    + (result.getCredentials() == null)
            );
        };
    }
}
```

When the application starts successfully, among the Spring Boot log lines there are **six expected demo lines**:

```text
demo.request.authenticated=false
demo.request.authorities=0
demo.result.name=alice
demo.result.authenticated=true
demo.result.authorities=ROLE_USER,report:read
demo.result.credentialsErased=true
```

These are **expected outputs based on the code and ProviderManager in the configuration above**, not stdout captured from a live run here. Startup timestamps, versions, web port, and framework log ordering may differ. Only compare lines starting with `demo.`.

Because `ProviderManager` erases credentials from the resulting token by default, the `credentialsErased` flag in this example is expected to be `true`. However, do not assume that conclusion applies to every implementation/custom provider.

**Important point:** calling the manager in `CommandLineRunner` verifies username/password and returns an Authentication, but it **does not automatically create a login cookie or bind Alice to subsequent HTTP requests**. Every HTTP request to the API still requires its own authentication mechanism.

### 9.5. Controller reading Authentication from the security context

Create `src/main/java/example/authmanager/IdentityController.java`:

```java
package example.authmanager;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/identity")
    Map<String, Object> identity(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "name", authentication.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin allowed");
    }
}
```

The Controller receives the `Authentication` placed into the request/security context by the filter after HTTP Basic went through the manager. The Controller does not take identity from a `userId` query parameter or arbitrary client header, and does not need to call `manager.authenticate` again.

Alice's response may be:

```json
{
  "name": "alice",
  "authorities": ["ROLE_USER", "report:read"]
}
```

The order of **JSON fields** may vary depending on the serializer, while the authorities list is sorted in code. Never return `authentication.getCredentials()` or serialize the raw `Authentication` out of an API.

### 9.6. Running with an HTTP client

In the project root:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Assuming the application runs on `http://localhost:8080`:

```bash
# No Basic credentials: 401
curl -i http://localhost:8080/api/identity

# Alice with valid password: 200 and Alice's identity
curl -i -u alice:demo-alice-pass http://localhost:8080/api/identity

# Wrong password: 401
curl -i -u alice:wrong-pass http://localhost:8080/api/identity

# Disabled account: authentication rejected
curl -i -u disabled:demo-disabled-pass \
  http://localhost:8080/api/identity

# Alice is authenticated, but lacks ROLE_ADMIN: 403
curl -i -u alice:demo-alice-pass http://localhost:8080/api/admin

# Admin has ROLE_ADMIN: 200
curl -i -u admin:demo-admin-pass http://localhost:8080/api/admin
```

In PowerShell, write each command on a single line instead of using Bash's `\` line continuation. The passwords are local demo data only. **HTTP Basic uses Base64, not credential encryption**, so production must use HTTPS and proper secret management; `curl -u` containing a password on the command line may appear in history/process lists.

Illustrative results:

| Request | Expected status | Reason |
| --- | --- | --- |
| GET `/api/identity` without credentials | 401 | Endpoint requires authentication |
| GET `/api/identity` with Alice/valid password | 200 | DaoAuthenticationProvider accepts |
| GET `/api/identity` with wrong password | 401 | BadCredentialsException handled by filter |
| GET `/api/identity` with disabled account | 401 | Authentication fails |
| GET `/api/admin` with Alice | 403 | Authentication valid, but authority missing |
| GET `/api/admin` with Admin | 200 | Authentication valid and has `ROLE_ADMIN` |

## 10. Integration Tests Checking Manager, Provider, and Filter Together

Tests need to prove two independent things:

1. `AuthenticationManager.authenticate` directly processes requests, returns accurate results, and throws appropriate exceptions on failure.
2. The HTTP Basic filter uses the manager to handle the API and set the security context properly for the request, while authorization can still reject a logged-in user.

With `spring-boot-starter-test` and `spring-security-test`, create `src/test/java/example/authmanager/AuthenticationManagerFlowTest.java`:

```java
package example.authmanager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationManagerFlowTest {

    @Autowired
    AuthenticationManager manager;

    @Autowired
    MockMvc mvc;

    @Test
    void inputIsNotAuthenticatedYet() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-alice-pass"
            );

        assertThat(request.isAuthenticated()).isFalse();
        assertThat(request.getName()).isEqualTo("alice");
        assertThat(request.getAuthorities()).isEmpty();
    }

    @Test
    void managerReturnsAuthenticatedResultWithAuthorities() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-alice-pass"
            );

        Authentication result = manager.authenticate(request);

        assertThat(result).isNotSameAs(request);
        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("alice");
        assertThat(result.getPrincipal()).isInstanceOf(UserDetails.class);
        assertThat(result.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList())
            .contains("ROLE_USER", "report:read");
        assertThat(result.getCredentials()).isNull();
    }

    @Test
    void wrongPasswordThrowsAuthenticationException() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "wrong-password"
            );

        assertThatThrownBy(() -> manager.authenticate(request))
            .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void disabledAccountIsRejected() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "disabled", "demo-disabled-pass"
            );

        assertThatThrownBy(() -> manager.authenticate(request))
            .isInstanceOf(DisabledException.class);
    }

    @Test
    void directManagerCallDoesNotSetSecurityContext() {
        SecurityContextHolder.clearContext();
        try {
            Authentication result = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "demo-alice-pass"
                )
            );

            assertThat(result.isAuthenticated()).isTrue();
            assertThat(SecurityContextHolder.getContext()
                .getAuthentication()).isNull();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void anonymousRequestNeedsBasicAuthentication() throws Exception {
        mvc.perform(get("/api/identity"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsAreAccepted() throws Exception {
        mvc.perform(get("/api/identity")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void invalidBasicCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/identity")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizationStillChecksRoleAfterAuthentication()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isOk());
    }
}
```

Run:

```bash
./gradlew test --tests example.authmanager.AuthenticationManagerFlowTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.authmanager.AuthenticationManagerFlowTest
```

**Expectation:** all nine test methods pass with the matching Spring Boot 3/Spring Security 6.5, configuration, and controller above. This is an **expectation from the test design**, not an executed test result recorded in this lesson. When upgrading versions, re-check constructor APIs and default behavior against the BOM.

### 10.1. Distinguishing manager tests from HTTP tests

| Test type | Components tested | What it does not prove on its own |
| --- | --- | --- |
| Calling `manager.authenticate(...)` | Input/output contract, password, account status, authority | HTTP filter applied, session/cookie persisted |
| MockMvc `httpBasic(...)` | How filter extracts credentials and provider processes request | Another form login or token flow is guaranteed correct |
| Testing `hasRole("ADMIN")` | Authorization from authentication result | Account object belongs to the right tenant |
| `@WithMockUser` / `user()` | Policy with simulated Authentication | Real username/password going through the provider |
| Separate CSRF test | Protection on state-changing requests | Exact role/permission if blocked early by CSRF |

If you only test that a controller method returns a string, you may miss a disabled Spring Security configuration. Security tests should cover both allowed and rejected cases and, for operations with side effects, confirm the database/queue remains unchanged when a request is blocked.

### 10.2. Cautions about test assertions

- Do not assert `getCredentials()==null` for *every* Authentication type: this test applies specifically to `ProviderManager` + the username/password token in the example.
- Do not assert every provider always creates a new Java instance: under other designs, a provider may handle objects differently. This test describes `DaoAuthenticationProvider` behavior in the setup shown.
- Do not assert all 403s come from missing roles: CSRF or domain policies can also cause 403.
- Do not use `@WithMockUser` to prove disabled accounts or password hashes work.
- When testing method security, `@EnableMethodSecurity` must be active and calls must go through the appropriate Spring bean/proxy.
- When using a role hierarchy or custom prefix, adjust assertions to match the actual policy.

## 11. Standalone Java 17: Simulating input → manager → output

If Spring Boot is not yet available, the following program uses **plain JDK 17**, modeling the same record type carrying two states before and after authentication. The goal is to clearly see why **input cannot be trusted**, why the caller must use the **return value**, and why exceptions must never be turned into success.

**Mandatory note:** this is a learning model with a fixed demo secret string and simple comparison; **it is not secure password authentication**. In real applications, use `AuthenticationManager`/`Provider`, `PasswordEncoder`, and a properly designed identity store.

Create **`ManagerContractDemo.java`**:

```java
import java.util.List;

public class ManagerContractDemo {

    record AuthState(
        String principal,
        String credentials,
        List<String> authorities,
        boolean authenticated
    ) {}

    static final class AuthenticationFailed
            extends RuntimeException {
        AuthenticationFailed() {
            super("Authentication rejected");
        }
    }

    interface AuthManager {
        AuthState authenticate(AuthState request);
    }

    static final class DemoManager implements AuthManager {
        @Override
        public AuthState authenticate(AuthState request) {
            if (request == null
                    || !"alice".equals(request.principal())
                    || !"demo-secret".equals(request.credentials())) {
                throw new AuthenticationFailed();
            }

            return new AuthState(
                "alice",
                null,
                List.of("ROLE_USER", "report:read"),
                true
            );
        }
    }

    public static void main(String[] args) {
        AuthManager manager = new DemoManager();

        AuthState request = new AuthState(
            "alice", "demo-secret", List.of(), false
        );

        System.out.println(
            "request.authenticated=" + request.authenticated()
        );
        System.out.println(
            "request.authorities=" + request.authorities().size()
        );

        AuthState result = manager.authenticate(request);

        System.out.println(
            "result.principal=" + result.principal()
        );
        System.out.println(
            "result.authenticated=" + result.authenticated()
        );
        System.out.println(
            "result.authorities="
                + String.join(",", result.authorities())
        );
        System.out.println(
            "result.credentialsErased="
                + (result.credentials() == null)
        );

        try {
            manager.authenticate(new AuthState(
                "alice", "wrong", List.of(), false
            ));
        } catch (AuthenticationFailed ignored) {
            System.out.println("wrongPassword=rejected");
        }
    }
}
```

Compile and run:

```bash
javac ManagerContractDemo.java
java ManagerContractDemo
```

**Exact stdout per the program's Java logic:**

```text
request.authenticated=false
request.authorities=0
result.principal=alice
result.authenticated=true
result.authorities=ROLE_USER,report:read
result.credentialsErased=true
wrongPassword=rejected
```

Reading the output:

1. Request knows the username and credential, yet is **not authenticated**, with empty authorities.
2. Manager (simulated) checks evidence, creates **a new result object**, with the right authorities.
3. Caller uses `result`; do not assume the `request` object itself was mutated.
4. The simulated result erased the credential while keeping principal/authorities.
5. If the credential is wrong, the method throws an exception rather than creating a successful Authentication.
6. The program has no `SecurityContextHolder`, session, or Spring filters; it only simulates the contract, not real web protection.

Using `List<String>` instead of `GrantedAuthority` in this model is intentional so it runs without Spring libraries. In real applications, authorities are `Collection<? extends GrantedAuthority>`, and the manager/provider authenticates with an appropriate security mechanism.

## 12. Different Authentication Types Still Follow the Common Contract

`AuthenticationManager` does not mean "username/password manager". Systems can use:

| Mechanism | Input Authentication | Suitable provider | Output used for authorization |
| --- | --- | --- | --- |
| HTTP Basic | Usually unauthenticated `UsernamePasswordAuthenticationToken` | `DaoAuthenticationProvider` or similar username/password provider | Verified principal + roles/authorities |
| Form login | Usually `UsernamePasswordAuthenticationToken` | `DaoAuthenticationProvider` / custom provider | UserDetails/authorities; web login flow can then save session |
| JWT resource server | Appropriate token Authentication per mechanism | `JwtAuthenticationProvider` or corresponding converter/decoder | `JwtAuthenticationToken` with principal/authorities from verified JWT |
| OIDC/OAuth2 login | Tokens serving OAuth2/OIDC flow | Corresponding provider | `OAuth2AuthenticationToken`/principal per mechanism |
| Pre-authenticated proxy | Pre-authentication token | Provider trusting the proper boundary | Confirmed principal from pre-auth mechanism |
| Custom credential | Custom `Authentication` | Custom `AuthenticationProvider` | Result after custom verification succeeds |

**Do not force every input into `UsernamePasswordAuthenticationToken`**. For JWT, verify signature, issuer, audience, expiration, and trust source; for pre-auth, determine how forged headers are prevented; for custom providers, ensure the result is genuinely verified.

### 12.1. When multiple managers coexist

An application may have a global manager, a local manager for a `SecurityFilterChain`, or a parent manager. A service injecting `AuthenticationManager` does not necessarily use **the exact same instance** that all other filters use if the application configures multiple managers.

When debugging, check:

- Which `AuthenticationManager` bean is injected into the caller?
- Is `HttpSecurity.authenticationManager(...)` set?
- What `@Order` and `securityMatcher` does each chain have?
- Do the provider list and `supports` accept the right token type?
- Is a parent manager configured?
- Are authority mappings consistent between password and token flows?

Do not guess that "because an AuthenticationManager bean exists, every token type is accepted".

### 12.2. Direct authenticate is not access token issuance

Some custom login code looks like:

```java
Authentication verified = manager.authenticate(request);
// return some JWT?
```

`verified` is only an Authentication result. If the system wants to issue a token, it needs **a dedicated token issuance pipeline**: defining claims, scope/audience, expiration, signing keys, refresh/revocation, storage, and login endpoint protection policy. Spring Security Resource Server **verifies** API access tokens; it does not turn every `authenticate` call into an issued access token.

## 13. Anti-Patterns and How to Fix Them

### 13.1. Using the input token's getName() as the real identity

`request.getName()` before authentication may just be a client-claimed username. Using it to fetch sensitive data is wrong. Wait for `authenticate` to succeed and use the verified principal from the result or from the filter-populated context.

### 13.2. Ignoring the returned Authentication

Calling `manager.authenticate(request);` and then using `request` as if its authenticated flag and authorities were updated is a common bug. Providers may return a different object. Always capture and use `Authentication verified = ...`.

### 13.3. Returning null or authenticated=false and letting the request continue

In the manager contract, failed authentication must be handled via appropriate exceptions; an unverified result is not a successful login. Callers must never patch it by setting authenticated=true.

### 13.4. Creating roles directly from the request body

`new SimpleGrantedAuthority(clientSuppliedRole)` does not turn client input into trusted permissions. Authorities must be controlled by the provider/decoder/mapper after verifying identity and token trust.

### 13.5. Producing HTTP statuses inside AuthenticationManager

The manager's role is not to return HTTP 401/403/302 responses. Filters, entry points, access-denied handlers, and the web framework coordinate client interaction. Keeping AuthenticationManager independent of HTTP lets the contract be reused in non-HTTP flows.

### 13.6. Treating ProviderNotFoundException as a password error

`ProviderNotFoundException` usually indicates no provider supports that Authentication type; check the provider list, `supports`, injected manager, and chain. A wrong password in a DAO flow typically throws `BadCredentialsException`, not a missing provider.

### 13.7. Logging raw Authentication or credentials

An `Authentication` can contain principals and sensitive authentication data, especially on input. Never log raw passwords, bearer tokens, session IDs, or `Authorization` headers. For auditing, log minimal metadata such as auth type, safe principal ID, timestamp, and outcome category.

### 13.8. Retaining credentials too long or disabling erasure without cause

ProviderManager erases credentials to reduce secret exposure risk. If a cache holds shared objects, redesign the cache/objects before disabling erasure. Do not rely on erasure to replace TLS or secret management.

### 13.9. Assuming authenticated=true means allowed to do everything

Authentication only establishes identity and authorities; `hasRole`, `hasAuthority`, and domain authorization must still evaluate specific resources. A valid user can still receive 403.

### 13.10. Managing SecurityContext with the wrong lifecycle

If you call the manager in a custom login controller and only set context on the thread, the next request may lose the login; the session is not saved properly, and CSRF/session fixation/logout remain unhandled. Use Spring Security's supported integrations or implement the full context/repository lifecycle.

### 13.11. Using @WithMockUser to "prove" real authentication

`@WithMockUser` creates a simulated Authentication for authorization tests; it bypasses the password provider. Authentication tests must invoke the real manager or send HTTP Basic/form/token through the appropriate filter.

### 13.12. Misunderstanding anonymous isAuthenticated()

An `AnonymousAuthenticationToken` can have `isAuthenticated()==true` at the object level. Spring Security's `authenticated()` rule includes logic to distinguish anonymous tokens; do not replace it with `authentication != null && authentication.isAuthenticated()`.

### 13.13. Ignoring permission changes

Sessions/tokens may hold authorities captured at login time. When a role is revoked, an existing Authentication does not update immediately on its own; use refresh, revocation, TTL, or runtime checks depending on risk.

### 13.14. Adding multiple providers without checking order

A provider supporting the same Authentication type with different logic can change outcomes depending on ordering. Test provider order, null/exception contracts, and parent fallback with negative tests; never let a weaker mechanism accept a request that a stronger mechanism rejected.

## 14. Debugging Checklist When authenticate Does Not Behave as Expected

| Symptom | Check first | Failure category |
| --- | --- | --- |
| `BadCredentialsException` | Password, user lookup, encoder/hash, and account status | Authentication rejected |
| `DisabledException` / `LockedException` | Account state in the user store | Account rules |
| `ProviderNotFoundException` | Authentication type, provider `supports`, parent manager | Manager/provider configuration |
| Login succeeds, yet next API call is still 401 | Filter, context repository, session/token, cookie | Saving/restoring identity |
| Login succeeds, yet admin API returns 403 | Authority, role prefix, authorization rule | Authorization |
| `getCredentials()==null` after login | Is erasure active? | Normal in many providers |
| Principal is Jwt instead of UserDetails | Active authentication mechanism | Data type selection |
| `@WithMockUser` test passes, real password fails | Provider or encoder not yet tested | Test scope |
| Password correct, yet account disabled | Status checked before/during authentication | Account policy |
| Custom POST login returns 403 | CSRF token, chain/method policy | Exploit protection |
| Service calls authenticate, yet context is empty | Forgot to set/persist context after direct call | Context lifecycle bug |
| JWT signature valid, yet wrong scopes | Converter, issuer/audience, authority mapping | Token trust & authorization |

### 14.1. Quick diagnostic sequence

1. Identify the exact `SecurityFilterChain` and active mechanism (HTTP Basic, form, token, or custom).
2. Check what type the input token is created with, initial `isAuthenticated`, and whether principal/credentials are present; **never print credentials**.
3. Identify which `AuthenticationManager` instance is used, the `AuthenticationProvider` list, and any parent.
4. Check whether a matching provider `supports` the incoming token type.
5. Check user lookup, password encoder, token decoder, and account status.
6. On failure, classify the exception; do not assume every error is `BadCredentialsException`.
7. On success, inspect the **result**: principal type, authorities, `isAuthenticated`, and credential erasure policy.
8. Check whether the filter persisted `SecurityContext` or if the next request must resend a token.
9. On 403, distinguish authorization, CSRF, and object-level policy.
10. For object-level access, verify owner, tenant, and business state from server data.
11. Write integration tests for both success and negative paths.
12. Verify logs are safe and never leak passwords/tokens.

### 14.2. Questions to ask when reading someone else's code

- Who creates the input Authentication, and which source is treated as untrusted?
- Which algorithm/verification source does the manager/provider use?
- Is any callback/handler catching exceptions and translating them to HTTP responses?
- Does the result differ from the request, and does the caller keep the result?
- Who grants authorities, and could they be forged by the client?
- After authentication, who holds SecurityContext and who persists the session/token?
- Where are action/resource permissions evaluated?
- When a user is locked or permissions are revoked, how are existing sessions/tokens handled?
- Does a passing test actually go through AuthenticationManager or only use a mock user?
- If multiple authentication mechanisms coexist, do providers/chains have clean boundaries?

## 15. Self-Check Questions

**Question 1.** Why does `AuthenticationManager.authenticate` accept and return the same `Authentication` type when the two objects have different trust levels?

**Question 2.** If a request contains username `alice` and a password string, why should you not use `request.getName()` to determine the real user before calling the manager?

**Question 3.** How does `ProviderManager` differ from `DaoAuthenticationProvider`?

**Question 4.** When a provider cannot handle an Authentication type, what are the roles of `supports`, `null`, and `ProviderNotFoundException`?

**Question 5.** What Java outcome does a wrong password normally produce with a username/password provider?

**Question 6.** Why is `Authentication result = manager.authenticate(request)` better than ignoring the return value?

**Question 7.** Does `result.getCredentials()==null` after authentication mean the manager logged the user out?

**Question 8.** After a direct `authenticate` call succeeds from a service, why might the next HTTP request still not be logged in?

**Question 9.** What is the role of `GrantedAuthority` in an Authentication result? Does it automatically allow Alice to view all orders?

**Question 10.** HTTP Basic with a wrong password returns 401, while an authenticated user lacking ADMIN returns 403: which two layers decide those?

**Question 11.** Why does a passing `@WithMockUser` test not prove that the user store and `PasswordEncoder` work?

**Question 12.** If a client JWT has a `ROLE_ADMIN` claim without verified signature/issuer/audience, can an authenticated Authentication be created from that claim?

**Question 13.** When using multiple `SecurityFilterChain` beans, what can cause a different AuthenticationManager to be used than the one injected into a service?

**Question 14.** If admin permissions are revoked, why might an existing Authentication in a session not lose the authority immediately?

**Suggested Answers**

1. The interface serves both requests and results; before the provider it is unverified data to check, after the provider it is verified identity/permissions.
2. The input username is claimed by the client without proof; it can be any string.
3. ProviderManager coordinates providers; DaoAuthenticationProvider executes username/password authentication via UserDetailsService/PasswordEncoder.
4. `supports` indicates which token types a provider understands; a provider may return null so the coordinator tries the next; lacking a handling provider can produce ProviderNotFoundException.
5. Throws an appropriate AuthenticationException, usually BadCredentialsException; there is no successful authentication result.
6. The provider may return a new Authentication result with different principal/authorities/state.
7. No. Credentials may be erased to reduce exposure; it is not logout.
8. A direct call does not automatically set and persist SecurityContext, nor issue a session cookie or token.
9. They are coarse-grained capabilities attached to the subject; owner/tenant/object policies are still needed.
10. Authentication/filter/entry point handles 401; authorization rejecting permissions produces 403 (in standard cases).
11. Mock user simulates the context without passing passwords through the real manager/provider.
12. No. Claims must come from a token verified under the trust policy before mapping authorities.
13. Local manager configuration, chain matcher/order, different provider/parent, or different bean injection.
14. Sessions/tokens hold permission data created earlier; refresh, revocation, or runtime checks are required.

## 16. Official Reference Documentation

- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 – Username/Password Authentication and AuthenticationManager bean](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/index.html)
- [Spring Security 6.5 – HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security – AuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [Spring Security – ProviderManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 – MockMvc Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/)
