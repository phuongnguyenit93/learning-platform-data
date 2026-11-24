# AnonymousAuthenticationToken and How to Identify Unauthenticated Users in Spring Security Servlet

## 1. Lesson Objectives

In a Spring MVC application using Spring Security, a request without login credentials does **not necessarily** cause `SecurityContextHolder.getContext().getAuthentication()` to return `null`. Under the default configuration, Spring Security can place an `AnonymousAuthenticationToken` in the security context to represent an **unauthenticated** caller.

The most confusing detail is: **`AnonymousAuthenticationToken.isAuthenticated()` typically returns `true`, yet the caller is still considered anonymous, not a logged-in user**. Misreading this flag can cause controllers, custom filters, or business code to open account-only features to guests.

This lesson focuses on **Spring Security on the Servlet stack** (Spring Boot, Spring MVC, `SecurityFilterChain`, `SecurityContextHolder`), answering these questions:

1. What is anonymous authentication, and why does Spring Security create a token for unauthenticated callers?
2. What does `AnonymousAuthenticationFilter` populate into `SecurityContext`? What do the principal, authorities, credentials, and `authenticated` flag mean?
3. How do you distinguish **no authentication**, **anonymous**, **authenticated user**, and **remember-me**?
4. Why do `permitAll()`, `anonymous()`, `authenticated()`, and `fullyAuthenticated()` produce different outcomes?
5. How to observe, test, and avoid authorization bugs in real Servlet applications.

## 2. Authentication Is Not Synonymous with "Logged In"

Spring Security uses the `Authentication` interface to represent information about a request's principal. An `Authentication` can hold:

- **`principal`**: the represented identity, such as a user, username, or an anonymous placeholder;
- **`credentials`**: authentication evidence, which may have been erased/masked after verification;
- **`authorities`**: list of `GrantedAuthority` instances used for authorization decisions;
- **`details`**: additional metadata about the request/authentication mechanism;
- **`isAuthenticated()`**: state flag of the authentication object according to its specific implementation contract.

`SecurityContext` holds the current `Authentication`; `SecurityContextHolder` gives running code access to that context. Under the standard Servlet model, the context is bound to the request execution thread and managed/cleared at request boundaries. Do not store `Authentication` in a static field or assume it automatically propagates to all asynchronous threads.

**Key point:** having an `Authentication` object in the context is an **internal state** condition, not proof of a logged-in user. Spring Security deliberately creates an `AnonymousAuthenticationToken` so multiple components can handle requests using the same `Authentication` abstraction.

### Four States to Distinguish

| State | `SecurityContext.getAuthentication()` | Correct interpretation |
| --- | --- | --- |
| Context unpopulated / outside filter | May be `null` | No `Authentication` yet; do not assume the request passed through all of Spring Security |
| Default anonymous | Usually `AnonymousAuthenticationToken` | Caller is **not logged in**, even though the token has `authenticated=true` |
| Logged in via valid Basic/form/token | An `Authentication` representing a real verification result, per mechanism | An authenticated user or client exists, though **permissions** must still be checked |
| Remember-me | An `Authentication` recognized as remember-me when the feature is configured | A remembered identity exists; some sensitive operations still require **full authentication** |

Not every request passes through the anonymous filter: configurations may disable anonymous authentication, different security chains may apply, code may execute directly outside a request, or context access may happen outside the lifecycle. Therefore, code should handle both `null` and anonymous tokens.

## 3. How Does `AnonymousAuthenticationFilter` Work?

In a Servlet `SecurityFilterChain` with anonymous authentication enabled (the default in standard configurations), `AnonymousAuthenticationFilter` participates in processing the security context. When execution reaches this filter and the context **does not yet have** an `Authentication`, the filter supplies an `AnonymousAuthenticationToken`.

High-level flow:

```text
HTTP GET /public without credentials
    |
Servlet Filter Chain
    |
Spring Security creates/loads SecurityContext
    |
Configured authentication mechanisms
    |  (no valid credentials received)
    v
AnonymousAuthenticationFilter
    |-- context has no Authentication yet?
    |       |-- YES -> supplies AnonymousAuthenticationToken
    |       |-- NO  -> keeps existing Authentication
    v
AuthorizationFilter
    |-- applies permitAll / anonymous / authenticated / ...
    v
Controller (if permitted)
```

Specifically with the standard anonymous configuration:

- The default principal is the string `"anonymousUser"`.
- The default authority is `ROLE_ANONYMOUS`.
- The object type is typically `AnonymousAuthenticationToken`.
- The `isAuthenticated()` property of the anonymous token can be `true`.
- An internal `key` is used in Spring Security's creation/verification of the anonymous token; **this key is not a user password, not a session ID, and does not turn the token into proof of login**.

Default values can be customized; never use the string `anonymousUser`, `ROLE_ANONYMOUS`, or the key configuration as the sole criterion for determining whether a user is logged in.

### Why Does the Anonymous Token Mark `authenticated=true`?

This implementation design lets Spring Security work uniformly with the `Authentication` abstraction: the anonymous token is an internal state object constructed and recognized by the framework. Its `authenticated=true` flag **does not mean** "a real account's password/token was verified."

Consequently, the following two checks are **insufficient** to determine whether a user is logged in:

```java
Authentication auth = SecurityContextHolder.getContext().getAuthentication();

boolean wrongA = auth != null;
boolean wrongB = auth != null && auth.isAuthenticated();
```

This is an **illustrative snippet inside request-processing code**, not a complete Java program. For a typical anonymous request, both `wrongA` and `wrongB` can be `true`. Using them to unlock user-only features risks wrong authorization decisions.

## 4. How to Identify Anonymous: Use `AuthenticationTrustResolver`

Spring Security provides the `AuthenticationTrustResolver` interface to classify `Authentication`. The commonly used implementation is `AuthenticationTrustResolverImpl`:

```java
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication auth = SecurityContextHolder.getContext().getAuthentication();
AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();

boolean anonymous = auth != null && resolver.isAnonymous(auth);
boolean rememberMe = auth != null && resolver.isRememberMe(auth);

boolean recognizedUser = auth != null
    && auth.isAuthenticated()
    && !anonymous;

boolean fullyAuthenticated = recognizedUser && !rememberMe;
```

The snippet above is also **illustrative code inside a method or execution path**, not a Java file with `main`. Interpret the expressions as follows:

- `resolver.isAnonymous(auth)` detects anonymous authentication by type rather than checking the username string.
- `resolver.isRememberMe(auth)` detects remember-me when that mechanism is used.
- `recognizedUser` here pragmatically interprets standard tokens: has an authentication marked valid by its flag and is **not** anonymous. This is still not an authorization enforcement mechanism.
- `fullyAuthenticated` in the illustration excludes both anonymous and remember-me. For security policies, prefer Spring Security's `fullyAuthenticated()` rule rather than building authorization policies out of booleans in a controller.

**`AuthenticationTrustResolver` is a classification mechanism**, not a new authentication system. For custom `Authentication` implementations, define the authentication contract clearly and integrate properly so Spring Security does not misclassify the state.

### When Should You Use `instanceof AnonymousAuthenticationToken`?

Code like the following can work in a system that only uses the default anonymous token:

```java
boolean anonymous = auth instanceof AnonymousAuthenticationToken;
```

However, `AuthenticationTrustResolver` communicates intent more clearly and aligns with how Spring Security distinguishes anonymous/remember-me in its authorization system. Do not build logic around `auth.getName().equals("anonymousUser")`, because a real user could share that default string and the anonymous principal can be renamed.

### What About `HttpServletRequest.getUserPrincipal()`?

In Spring Security's Servlet integration, `HttpServletRequest.getUserPrincipal()` typically returns `null` for anonymous users even when `SecurityContextHolder` holds an `AnonymousAuthenticationToken`. These are two different **views**:

- `SecurityContextHolder` exposes the `Authentication` being processed by the security filters, including the anonymous placeholder.
- The Servlet principal API represents the caller's principal per the Servlet wrapper contract and does not necessarily return the anonymous placeholder token.

Because injection mechanisms such as `Principal`, `Authentication`, or `@AuthenticationPrincipal` each resolve differently, **do not assume** they always return the same object or value as `SecurityContextHolder` in every configuration. When inspecting anonymous state at runtime, reading `Authentication` from `SecurityContextHolder` and using a trust resolver is the clear choice for this lesson.

## 5. `permitAll()`, `anonymous()`, `authenticated()`, `fullyAuthenticated()`

With Spring Security 6 on Servlet, `authorizeHttpRequests` provides rules that express business intent closely:

| Rule | Anonymous | Logged in via Basic/form | Remember-me accepted | Meaning |
| --- | --- | --- | --- | --- |
| `permitAll()` | Allowed | Allowed | Allowed | Endpoint open to all authentication states |
| `anonymous()` | Allowed | Denied | Usually denied | Only for callers considered anonymous |
| `authenticated()` | Denied | Allowed | Allowed | Requires an identity Spring Security considers authenticated, not anonymous |
| `fullyAuthenticated()` | Denied | Allowed | Denied | Requires full authentication, excluding remember-me |
| `hasRole("ADMIN")` | Usually denied | Allowed if holding `ROLE_ADMIN` | Depends on authorities and policy | Requires a specific authority; authentication alone does not grant roles |
| `denyAll()` | Denied | Denied | Denied | Blocks every request matching the rule |

The remember-me column assumes the application **has configured** that mechanism; Spring Security does not enable remember-me automatically for every application. The table describes **authorization** outcomes; requests may still be blocked earlier by other filters (e.g., CSRF) or fail for lacking a matching handler.

Example configuration intent:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/guest-only/**").anonymous()
    .requestMatchers("/account/**").authenticated()
    .requestMatchers("/sensitive/**").fullyAuthenticated()
    .anyRequest().denyAll()
)
```

This snippet **belongs inside an `HttpSecurity` configuration** and does not compile standalone. Spring Security does not evaluate `authenticated()` merely by calling `auth.isAuthenticated()` directly and trusting it; authorization logic uses trust resolver semantics to exclude anonymous callers.

**Important distinction:** `permitAll()` still lets the request pass through the security filter chain if the chain matches. `anonymous()` does not mean "for everyone, including logged-in users"; it intentionally restricts access to guests. And `fullyAuthenticated()` does not indicate whether a user has admin privileges or owns a specific domain resource.

## 6. Complete Example: Observing the Anonymous Token in Spring Boot Servlet

The example uses **Java 17+, Spring Boot 3.x, Spring Security 6.x**, Spring MVC, and HTTP Basic to produce observable states. Use only in development environments; HTTP Basic sends credentials on every request, so production must use HTTPS.

A Spring Boot project with build plugins and dependency management configured needs:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create `src/main/java/example/anonymous/AnonymousDemoApplication.java` with the following content:

```java
package example.anonymous;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AnonymousDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AnonymousDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/whoami").permitAll()
                .requestMatchers(HttpMethod.GET, "/guest").anonymous()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/strong").fullyAuthenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}

@RestController
class IdentityController {

    private final AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/whoami")
    Map<String, Object> whoami() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        boolean anonymous =
            auth != null && resolver.isAnonymous(auth);
        boolean rememberMe =
            auth != null && resolver.isRememberMe(auth);
        boolean loggedIn =
            auth != null && auth.isAuthenticated() && !anonymous;

        return Map.of(
            "type", auth == null ? "none" :
                auth.getClass().getSimpleName(),
            "name", auth == null ? "none" : auth.getName(),
            "tokenFlag", auth != null && auth.isAuthenticated(),
            "anonymous", anonymous,
            "loggedIn", loggedIn,
            "fullyAuthenticated", loggedIn && !rememberMe
        );
    }

    @GetMapping("/guest")
    String guest() {
        return "guest only";
    }

    @GetMapping("/me")
    String me() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        return "hello " + auth.getName();
    }

    @GetMapping("/strong")
    String strong() {
        return "fully authenticated";
    }
}
```

Within the same Java file, only `AnonymousDemoApplication` is `public`; the other two classes are package-private. This structure is valid in Java 17. `@SpringBootApplication` scans package `example.anonymous`, discovering both the configuration and the controller.

Key points to note:

- `.anonymous(...)` is not explicitly declared on `HttpSecurity` to enable the feature: anonymous authentication **is enabled by default** in standard Spring Security configurations.
- `/whoami` uses `permitAll`, allowing both anonymous and logged-in states to be observed; the controller reads the token from `SecurityContextHolder`.
- `/guest` uses `anonymous()`, admitting only anonymous callers; logged-in users are denied at authorization.
- `/me` uses `authenticated()`, so anonymous callers are not permitted even though the token has `isAuthenticated() == true`.
- `/strong` uses `fullyAuthenticated()`; Basic authentication qualifies. The demo does not configure remember-me, so it cannot directly demonstrate the difference against a remember-me token.
- `anyRequest().denyAll()` demonstrates blocking undeclared paths; it applies within this chain, which has no `securityMatcher` and thus matches all requests by default.
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` creates an encoder with an appropriate algorithm prefix when storing the demo password; plaintext passwords are not stored in the user store.
- The example uses only GET requests. Default CSRF protection remains enabled within its applicable scope; do not disable CSRF just to make browser POSTs work.

### Running and Observing

In a Spring Boot project with the Gradle wrapper, run:

```bash
./gradlew bootRun
```

On Windows PowerShell you can run `./gradlew.bat bootRun`. When the local server runs on the default port 8080, send:

```bash
# No credentials sent: inspect anonymous token.
curl -i http://localhost:8080/whoami

# Same URL with a valid account.
curl -i -u learner:demo-pass http://localhost:8080/whoami

# Compare rules for guests and real users.
curl -i http://localhost:8080/guest
curl -i -u learner:demo-pass http://localhost:8080/guest
curl -i http://localhost:8080/me
curl -i -u learner:demo-pass http://localhost:8080/me
curl -i -u learner:demo-pass http://localhost:8080/strong
```

The **expected results**, assuming no other custom configuration, are:

| Request | HTTP status | Meaning |
| --- | --- | --- |
| `GET /whoami`, anonymous | 200 | Shows token type `AnonymousAuthenticationToken`, `anonymous=true`, `loggedIn=false`, `tokenFlag=true` |
| `GET /whoami`, learner | 200 | Authentication from HTTP Basic, `anonymous=false`, `loggedIn=true`, `fullyAuthenticated=true` |
| `GET /guest`, anonymous | 200 | Body `guest only` |
| `GET /guest`, learner | 403 | Logged-in user is not in the anonymous state |
| `GET /me`, anonymous | 401 | HTTP Basic challenges for authentication; `me()` does not run |
| `GET /me`, learner | 200 | Body `hello learner` |
| `GET /strong`, learner | 200 | Body `fully authenticated` |

For an anonymous `GET /whoami`, the JSON typically has content **equivalent to**:

```json
{
  "type": "AnonymousAuthenticationToken",
  "name": "anonymousUser",
  "tokenFlag": true,
  "anonymous": true,
  "loggedIn": false,
  "fullyAuthenticated": false
}
```

JSON key ordering is not guaranteed because the example returns `Map.of(...)`. These are **expected** results, not actual captured log/stdout in this document; changing the anonymous configuration can change the default principal/type.

## 7. Why Does `authenticated()` Block Anonymous Callers When the Token Reports True?

Review the most important part of the previous behavior:

```text
AnonymousAuthenticationToken:
  auth != null                -> true
  auth.isAuthenticated()      -> true
  trustResolver.isAnonymous() -> true

Authorization rule authenticated():
  requires "authenticated" per Spring Security semantics,
  rejects AnonymousAuthenticationToken
```

The authorization step on Servlet should not be written as `auth.isAuthenticated() ? allow : deny` if the goal is to protect an endpoint for real users. Spring Security's `AuthorizationManager` and rules like `authenticated()` and `fullyAuthenticated()` understand anonymous/remember-me via the trust resolver.

When an anonymous caller requests `/me`, the `authenticated()` rule denies it. `ExceptionTranslationFilter` distinguishes an anonymous caller from an authenticated caller lacking permissions in order to trigger the appropriate `AuthenticationEntryPoint` (HTTP Basic typically returns **401** with a challenge, whereas form login may redirect to a login page). For an authenticated user lacking roles/permissions, the response is typically **403**.

Do not equate every 403 with "missing role": an invalid CSRF token can also trigger 403, and a custom authentication entry point can alter the response.

## 8. Comparing Four Check Approaches in Business Code

Suppose a controller needs to know whether the caller is logged in to render an optional UI block.

### Approach to Avoid: Null Check

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

if (auth != null) {
    // WRONG if treated as proof of a logged-in user.
}
```

With the anonymous filter enabled, `auth` can readily be a non-null anonymous token.

### Approach to Avoid: Checking Only the Flag

```java
if (auth != null && auth.isAuthenticated()) {
    // Can still enter this branch when the caller is anonymous.
}
```

`AnonymousAuthenticationToken` typically has `isAuthenticated() == true`, making this a subtle bug if tested only with logged-in accounts.

### Fragile Approach: Comparing the Username

```java
boolean guest = auth == null ||
    "anonymousUser".equals(auth.getName());
```

That string can be customized and could collide with a real account name. Do not rely on name or authority strings to define trust state.

### Appropriate Approach: Identifying via Trust Resolver

```java
AuthenticationTrustResolver resolver =
    new AuthenticationTrustResolverImpl();

boolean signedIn = auth != null
    && auth.isAuthenticated()
    && !resolver.isAnonymous(auth);
```

Use the result to **adjust presentation**, controlled logging, or application code that needs state awareness. When **enforcing authentication or authorization**, declare `authenticated()`, `fullyAuthenticated()`, `hasRole(...)`, `hasAuthority(...)` in security configuration and check resource ownership in the service/domain layer when required. Never use a self-computed flag to replace authorization.

## 9. Unit Tests and MockMvc to Prove Anonymous Semantics

To test the real Servlet security flow in the example, the project also needs:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create `src/test/java/example/anonymous/AnonymousSecurityTest.java`:

```java
package example.anonymous;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AnonymousSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousTokenHasTrueFlagButCallerIsNotLoggedIn() throws Exception {
        mvc.perform(get("/whoami"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.type").value("AnonymousAuthenticationToken"))
            .andExpect(jsonPath("$.tokenFlag").value(true))
            .andExpect(jsonPath("$.anonymous").value(true))
            .andExpect(jsonPath("$.loggedIn").value(false));
    }

    @Test
    void basicAuthenticationChangesCallerClassification() throws Exception {
        mvc.perform(get("/whoami").with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("learner"))
            .andExpect(jsonPath("$.anonymous").value(false))
            .andExpect(jsonPath("$.loggedIn").value(true))
            .andExpect(jsonPath("$.fullyAuthenticated").value(true));
    }

    @Test
    void guestRuleAcceptsOnlyAnonymousCaller() throws Exception {
        mvc.perform(get("/guest"))
            .andExpect(status().isOk())
            .andExpect(content().string("guest only"));

        mvc.perform(get("/guest").with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedRuleRejectsAnonymousCaller() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello learner"));
    }

    @Test
    void fullyAuthenticatedRuleAcceptsBasicLogin() throws Exception {
        mvc.perform(get("/strong").with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("fully authenticated"));
    }
}
```

Run tests:

```bash
./gradlew test
```

These tests are structured to run in a project satisfying the stated dependencies/versions; this document **does not claim to have executed the tests**. The first test intentionally demonstrates the apparent paradox: `tokenFlag=true` simultaneously with `anonymous=true` and `loggedIn=false`.

To further test remember-me, you must configure a real remember-me mechanism and an authentication restored from it. Do not construct a test request with a `UsernamePasswordAuthenticationToken` and conclude you have tested `fullyAuthenticated()` against remember-me.

## 10. Scenarios Outside Normal Requests

### 10.1. Anonymous Filter Does Not Run or Is Disabled

If `AnonymousAuthenticationFilter` is disabled (e.g., via `http.anonymous(...disable...)`) or code runs outside the Servlet filter chain, `SecurityContextHolder.getContext().getAuthentication()` may be `null`. Do not **disable anonymous authentication** just to turn `auth != null` into a "logged in" check; the proper solution is using appropriate rules and a trust resolver.

An application with multiple `SecurityFilterChain` beans may enable/disable or customize anonymous handling per chain. Before inspecting the context, verify which chain actually handles the request. `permitAll()` does not mean bypassing the entire filter chain.

### 10.2. Request with Wrong Credentials to a Public Endpoint

`permitAll()` allows access **at the authorization step** when authentication is not required, but that does not mean intentionally supplied invalid credentials are always ignored. For example, `BasicAuthenticationFilter` may process a malformed or wrong Basic header and return 401 before `AuthorizationFilter` evaluates `permitAll`. Keep this in mind when debugging "why does a public page return 401?".

### 10.3. Wrong Authentication State in a Custom Filter

If you write a custom filter and call `SecurityContextHolder.getContext().setAuthentication(...)`, you are responsible for ensuring the placed token was verified by an appropriate mechanism. Never insert a `UsernamePasswordAuthenticationToken` with `authenticated=true` solely because you received a username from a client-supplied header. `AnonymousAuthenticationToken` is likewise **not** trustworthy evidence for granting privileges.

### 10.4. Background Threads, Async, and Unit Tests

`SecurityContextHolder` typically uses a thread-based strategy. A task dispatched to another thread, a unit test calling a service directly, or a listener running outside a web request may not have the same context as a Servlet request. When context propagation is needed, use a propagation mechanism supported by Spring Security and define the lifecycle clearly; always handle `Authentication == null`. Never store user A's context in a global variable where user B's request could read it by mistake.

### 10.5. Remember-Me and Sensitive Resources

`authenticated()` typically accepts remember-me as a form of authentication; `fullyAuthenticated()` excludes remember-me to require fresher direct authentication. For operations such as password changes, fund transfers, or modifying account recovery methods, add re-authentication/step-up policies commensurate with the risk rather than assuming `fullyAuthenticated()` automatically provides MFA or guarantees a recent login timestamp.

### 10.6. Principal and Authorities Can Vary by Login Mechanism

After form login, Basic, OAuth2 login, or Resource Server authentication, the principal may be `UserDetails`, a string, `OAuth2User`, `Jwt`, or a custom type. Therefore, checking `instanceof UserDetails` or comparing `principal.toString()` is not a reliable way to determine whether a request has valid authentication across all mechanisms. Authorization should rely on the state and authorities evaluated by Spring Security.

## 11. Common Mistakes

| Mistake | Why it is wrong | Proper approach |
| --- | --- | --- |
| `auth != null` means logged in | Anonymous filter typically creates a non-null token | Use `AuthenticationTrustResolver` or `authenticated()` rule |
| `auth.isAuthenticated() == true` means logged in | `AnonymousAuthenticationToken` can return true | Exclude anonymous via trust resolver |
| Checking name equals `anonymousUser` | Anonymous principal can be customized, real user might share name | Detect state by type/trust resolver |
| Relying on `ROLE_ANONYMOUS` as sole login/guest proof | Authorities can be customized | Rely on `anonymous()` / trust resolver semantics |
| Guarding controllers with manual boolean checks | Easy to miss endpoints, lacks object-level permissions | Use URL/method rules and domain authorization |
| Using `permitAll()` and thinking no security filters run | Authentication, CSRF, and header filters can still run | Understand the chain and pre-authorization filters |
| Treating `anonymous()` as a synonym for `permitAll()` | Anonymous-only rejects logged-in users | Choose the rule matching who is actually allowed |
| Seeing 401 and concluding there is no anonymous token | 401 can originate from the entry point when anonymous is blocked | Inspect filters, trust resolver, and active rules |
| Disabling anonymous just to simplify null checks | Alters framework behavior and masks design flaws | Keep sensible defaults, write proper checks |
| Equating `fullyAuthenticated()` with MFA | Rule primarily distinguishes remember-me from full auth | Design separate step-up/re-auth/MFA if needed |
| Assuming all threads share the same context | Context is bound to the request thread by default | Propagate context properly and clear after processing |

## 12. Self-Check Exercises

**Question 1.** In a controller, `Authentication auth = SecurityContextHolder.getContext().getAuthentication();`, `auth != null`, `auth.isAuthenticated() == true`, yet `auth.getClass().getSimpleName()` is `AnonymousAuthenticationToken`. Is the caller logged in?

**Answer:** No. This is a token representing an anonymous caller. Use `AuthenticationTrustResolver.isAnonymous(auth)` or the `authenticated()` policy to identify it accurately.

**Question 2.** An endpoint is configured with `requestMatchers("/docs").permitAll()`. Does an anonymous request to `/docs` still pass through security filters?

**Answer:** Yes, if the request is covered by a `SecurityFilterChain`. `permitAll()` is only an authorization outcome; it does not bypass the filter chain itself.

**Question 3.** Why can `anonymous()` reject a logged-in user even though the same endpoint returns 200 for a guest?

**Answer:** `anonymous()` means "only for callers recognized as anonymous," unlike `permitAll()`, which allows all states.

**Question 4.** One feature allows remember-me, whereas a sensitive feature requires full authentication. Which two rules fit?

**Answer:** `authenticated()` for the former, `fullyAuthenticated()` for the latter; if MFA/step-up is needed, additional design is required.

**Question 5.** `HttpServletRequest.getUserPrincipal()` returns `null`, while `SecurityContextHolder` holds an anonymous token. Is this necessarily a bug?

**Answer:** No. The Servlet principal wrapper may hide the anonymous principal while the internal context still uses the anonymous token to enforce rules.

**Question 6.** A custom filter sets an `Authentication` with `isAuthenticated=true` based on an `X-User: admin` header without verifying the sender. Is this safe?

**Answer:** No. Clients can spoof headers; identity must be verified and trust boundaries established properly before placing `Authentication` into the context.

## Conclusion

`AnonymousAuthenticationToken` allows Spring Security Servlet to represent unauthenticated callers using the same `Authentication` abstraction employed by other authentication mechanisms. This is helpful for the filter chain and authorization, but creates a trap: **the presence of a token or `isAuthenticated() == true` is not enough to conclude the caller is logged in**.

In code that inspects state, handle both `null` and anonymous tokens using `AuthenticationTrustResolver`. In security policies, prefer `anonymous()`, `authenticated()`, `fullyAuthenticated()`, and Spring Security-managed authority rules, while continuing to enforce permissions on individual domain resources.
