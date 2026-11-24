# AnonymousAuthenticationToken, Logged-In Users, and AuthenticationTrustResolver

## 1. Same `Authentication`, Different Levels of Trust

In a Servlet-based Spring Security application, a public request can pass through the security filter chain **without any account logged in**. Even so, after passing through `AnonymousAuthenticationFilter`, `SecurityContext` can still hold an `Authentication` object: `AnonymousAuthenticationToken`.

This is the easiest place to get tripped up:

- An anonymous token **typically returns `true` when you call `authentication.isAuthenticated()` directly**.
- An anonymous user **is still not logged in as an authenticated identity**.
- `AuthenticationTrustResolver` is used to distinguish anonymous, remember-me, and authenticated identities, rather than inferring from the token's `isAuthenticated()` flag alone.

A short example:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

boolean naive = authentication != null && authentication.isAuthenticated();

AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();
boolean actuallyLoggedIn = resolver.isAuthenticated(authentication);
```

If `authentication` is the default `AnonymousAuthenticationToken`, `naive` can be `true` while `actuallyLoggedIn` is `false`. The name `isAuthenticated` in **both places** looks identical, yet the criteria differ.

This lesson belongs to **Identity Models**, focusing on how identity states are represented in Spring Security and how to check those states properly. Username/password authentication, sessions, and authorization concepts are mentioned only to clarify anonymous/trust resolver behavior.

## 2. What Is Anonymous Authentication?

**Anonymous authentication** in Spring Security is a mechanism **representing an unauthenticated visitor with a structured token**. It lets authorization or auditing components see a consistent principal/authority in `SecurityContext` instead of constantly handling `null`.

In common default configuration:

| Property | `AnonymousAuthenticationToken` |
| --- | --- |
| Class | `org.springframework.security.authentication.AnonymousAuthenticationToken` |
| Principal | `anonymousUser` |
| Authorities | Typically `ROLE_ANONYMOUS` |
| `isAuthenticated()` on token | `true` |
| Identity proven? | **No**; anonymous is still an unauthenticated guest |
| `AuthenticationTrustResolver.isAnonymous(token)` | `true` |
| `AuthenticationTrustResolver.isAuthenticated(token)` | `false` |
| `AuthenticationTrustResolver.isFullyAuthenticated(token)` | `false` |

`anonymousUser` and `ROLE_ANONYMOUS` are **configurable defaults**, not a mandatory database account, and not a password or identifier that can be used to log in.

The phrase "anonymous **authentication**" is a framework mechanism/object name; it **does not mean** the visitor passed a password, OIDC, or JWT check. Spring Security uses this token to model an anonymous subject for policy evaluation.

### Why Is `AnonymousAuthenticationToken.isAuthenticated()` `true`?

The `Authentication` interface does not itself define "interactively logged in" as a full trust taxonomy. For an anonymous token, the object is created by an internal filter as a token **established by the framework to represent anonymous access**, so the flag on the token itself can be `true`. That is precisely why Spring Security uses **type/trust-level checks**, especially via `AuthenticationTrustResolver`, to tell whether it represents a genuinely logged-in user.

Do not try to "fix" `AnonymousAuthenticationToken` by calling `setAuthenticated(false)` and assuming the issue is solved. The right approach is configuring proper authorization rules and identity-type checks.

## 3. How `AnonymousAuthenticationFilter` Creates the Token

In a typical Servlet security chain, login mechanisms (such as HTTP Basic, form login, bearer tokens, or remember-me if configured) run first. **When execution reaches `AnonymousAuthenticationFilter` and `SecurityContext` still has no `Authentication`**, the filter places an `AnonymousAuthenticationToken` into the request context.

```text
HTTP request
    |
    v
Spring Security filter chain
    |
    +--> Configured authentication mechanism
    |      |
    |      +--> Success: context holds a real Authentication
    |      |
    |      +--> No Authentication set yet
    |                 |
    |                 v
    |        AnonymousAuthenticationFilter
    |                 |
    |                 +--> creates AnonymousAuthenticationToken
    |                       principal = "anonymousUser"
    |                       authorities = [ROLE_ANONYMOUS]
    |                       token.isAuthenticated() = true
    v
AuthorizationFilter / permission check
    |
    v
Controller or deny/redirect-to-login response
```

Points to note:

1. **The filter does not look up an anonymous user in the database.** It builds a default representation so the rest of the chain can work uniformly with `Authentication`.
2. **The filter does not replace a logged-in user.** If the context already holds a valid authentication, the filter does not overwrite it with anonymous.
3. **The mechanism can be customized or disabled.** If anonymous support is disabled, or code runs outside the filter chain, `SecurityContext.getAuthentication()` may still be `null`.
4. **There is a matching `AnonymousAuthenticationProvider`** when anonymous support is enabled to recognize tokens produced by this mechanism. The shared `key` between filter and provider is solely for internal management—**never treat it as a secret or a client-verification measure**.
5. **Never construct anonymous tokens from HTTP input** or treat `ROLE_ANONYMOUS` as a real user authority granted via login.

Examples of the difference:

- `GET /landing` is public: the visitor sends no credentials; after the anonymous filter, the context can hold an anonymous token; the request is allowed if policy permits.
- `GET /account` requires `authenticated()`: an anonymous context is **not enough**; the framework triggers the configured login entry point.
- `GET /account` after valid login: the context holds an authentication representing a real principal, such as an authenticated `UsernamePasswordAuthenticationToken` or OIDC/JWT token.

## 4. `AuthenticationTrustResolver`: Asking the Right Question

`AuthenticationTrustResolver` is an interface in `org.springframework.security.authentication`. Its standard implementation is `AuthenticationTrustResolverImpl`.

Four essential checks:

| Method | Meaning |
| --- | --- |
| `isAnonymous(authentication)` | Does the object represent an anonymous user according to the resolver? |
| `isRememberMe(authentication)` | Does the object represent a login restored via remember-me according to the resolver? |
| `isAuthenticated(authentication)` | Does the object exist, have the token's authenticated flag true, and **is not anonymous**? |
| `isFullyAuthenticated(authentication)` | Is it authenticated per above and **is not remember-me**? |

In Spring Security 6.5, the last two methods are **default methods** on the interface; evaluation relies on `isAnonymous` and `isRememberMe`. `AuthenticationTrustResolverImpl` recognizes standard token types by default; if a system uses custom authentication tokens outside this classification, revisit the trust-level strategy rather than guessing from the principal's name.

### Result Matrix to Remember

| Context state | Possible token | `token.isAuthenticated()` | `resolver.isAnonymous` | `resolver.isRememberMe` | `resolver.isAuthenticated` | `resolver.isFullyAuthenticated` |
| --- | --- | --- | --- | --- | --- | --- |
| No token | `null` | Cannot call | false | false | false | false |
| Unverified username/password request | `UsernamePasswordAuthenticationToken.unauthenticated(...)` | false | false | false | false | false |
| Anonymous guest | `AnonymousAuthenticationToken` | **true** | **true** | false | **false** | false |
| Remembered via remember-me | `RememberMeAuthenticationToken` | true | false | **true** | **true** | false |
| Valid login via normal mechanism | Authenticated token, neither anonymous nor remember-me | true | false | false | **true** | **true** |

This table describes **standard token types**; custom classes may require custom resolver configuration. An "unverified username/password request" token is an input object used during authentication, not a state an application should store as the current identity.

Note two details:

- `resolver.isAnonymous(null)` is `false`, yet that does not mean `null` represents a logged-in user. Both `resolver.isAuthenticated(null)` and `resolver.isFullyAuthenticated(null)` remain `false`.
- `resolver.isAuthenticated(rememberMeToken)` can be `true`. When stronger verification is required, use `fullyAuthenticated()` per policy. **Fully authenticated here does not mean MFA is enabled**; it solely distinguishes anonymous and remember-me within Spring Security's trust model.

## 5. Remember-Me Differs from Both Anonymous and Full Login

`RememberMeAuthenticationToken` typically appears when an application enables remember-me and restores a user's identity from a cookie via the configured mechanism. It is **not anonymous**: the framework ran a remember-me verification step, and the token normally carries the corresponding principal and authorities.

However, remember-me is not equivalent to a fresh session authenticated with full credentials. For sensitive operations (changing passwords, confirming payments, rotating security keys), an application may require **re-login** or stronger verification.

Comparison:

| Situation | `authenticated()` | `fullyAuthenticated()` |
| --- | --- | --- |
| Anonymous guest | Fails | Fails |
| Valid remember-me | Passes | Fails |
| Normal authenticated identity | Passes | Passes |

Keep in mind that a token being considered "fully authenticated" **does not by itself prove** the user just entered a password, passed MFA, or met a high assurance standard. For example, a `JwtAuthenticationToken` not classified as anonymous/remember-me can satisfy `fullyAuthenticated()`; if an API needs MFA/step-up, define policies checking claims, `acr`/`amr`, or a dedicated step-up mechanism.

## 6. Runnable Java 17+ Program: Observing Five States

This is a **standalone console example** using Spring Security 6.5.11 and Java 17+. It builds an in-memory account and performs real authentication via `DaoAuthenticationProvider` for the logged-in state. The anonymous and remember-me tokens are **constructed manually solely to illustrate how the resolver classifies tokens**, without running real HTTP/cookie/remember-me flows.

Structure:

```text
trust-resolver-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/TrustResolverDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'trust-resolver-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.TrustResolverDemo'
}
```

`src/main/java/demo/TrustResolverDemo.java`:

```java
package demo;

import java.util.List;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public class TrustResolverDemo {

    public static void main(String[] args) {
        AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();

        // No Authentication (can occur when anonymous is disabled).
        Authentication missing = null;

        // Authentication request: no verified proof yet.
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!");

        // Simulated token to observe resolver classification, not an HTTP login.
        Authentication anonymous = new AnonymousAuthenticationToken(
                "demo-key",
                "anonymousUser",
                List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));

        // Token simulating a remember-me state created by a trusted mechanism.
        // Never use this constructor to grant privileges from client data.
        Authentication remembered = new RememberMeAuthenticationToken(
                "demo-key",
                "lan",
                List.of(new SimpleGrantedAuthority("ROLE_READER")));

        // Real username/password authentication through a provider.
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        UserDetails user = User.withUsername("lan")
                .password(encoder.encode("DemoPass123!"))
                .roles("READER")
                .build();
        UserDetailsService users = new InMemoryUserDetailsManager(user);
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        AuthenticationManager manager = new ProviderManager(provider);

        Authentication loggedIn = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!"));

        show("missing", missing, resolver);
        show("request", request, resolver);
        show("anonymous", anonymous, resolver);
        show("rememberMe", remembered, resolver);
        show("loggedIn", loggedIn, resolver);

        // Having an Authentication in SecurityContext != being logged in.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(anonymous);
        SecurityContextHolder.setContext(context);
        try {
            Authentication current = SecurityContextHolder.getContext()
                    .getAuthentication();
            System.out.println("context.hasToken=" + (current != null));
            System.out.println("context.loggedIn=" + resolver.isAuthenticated(current));
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private static void show(
            String label,
            Authentication token,
            AuthenticationTrustResolver resolver) {

        boolean present = token != null;
        boolean raw = present && token.isAuthenticated();

        System.out.printf(
                "%s: present=%s raw=%s anonymous=%s rememberMe=%s authenticated=%s fully=%s%n",
                label,
                present,
                raw,
                resolver.isAnonymous(token),
                resolver.isRememberMe(token),
                resolver.isAuthenticated(token),
                resolver.isFullyAuthenticated(token));
    }
}
```

Run with JDK 17+ and a Java 17-compatible Gradle from the directory containing `build.gradle`:

```bash
gradle run --quiet
```

This is the **stdout printed by the program**, excluding any logs that Gradle's environment may emit:

```text
missing: present=false raw=false anonymous=false rememberMe=false authenticated=false fully=false
request: present=true raw=false anonymous=false rememberMe=false authenticated=false fully=false
anonymous: present=true raw=true anonymous=true rememberMe=false authenticated=false fully=false
rememberMe: present=true raw=true anonymous=false rememberMe=true authenticated=true fully=false
loggedIn: present=true raw=true anonymous=false rememberMe=false authenticated=true fully=true
context.hasToken=true
context.loggedIn=false
```

### Exact Explanation of Output

- **`missing`:** no token. You cannot call `missing.isAuthenticated()`; the program checks for null first. The resolver accepts `null` and returns false for all checks above.
- **`request`:** holds an unverified username/password. `raw=false` and not a logged-in user.
- **`anonymous`:** `raw=true` is misleading if you look only at the flag. The resolver identifies `AnonymousAuthenticationToken` and returns `authenticated=false`.
- **`rememberMe`:** both `raw` and `authenticated` are true, yet `fully=false`. In this program the token is created manually to observe classification; it **does not prove** any valid remember-me cookie.
- **`loggedIn`:** produced by `manager.authenticate(...)` through a provider verifying a BCrypt password hash, so `authenticated=true` and `fully=true` under default classification.
- **`context.hasToken=true` yet `context.loggedIn=false`:** proves that the presence of an `Authentication` in `SecurityContext` does not equate to an authenticated account.

Do not put manual `RememberMeAuthenticationToken` creation into production authentication flows. In real apps, the remember-me filter/provider, cookie settings, token verification, and security policies must determine when a remembered state is granted. Nor should you construct `UsernamePasswordAuthenticationToken.authenticated(...)` directly from client-submitted username/roles.

## 7. Distinctions in URL Protection Configuration

In Spring Security Servlet, the rules below differ even though all relate to "who gets in":

| Rule | Meaning |
| --- | --- |
| `permitAll()` | Public endpoint, allowing both anonymous guests and logged-in users; no authentication required. |
| `anonymous()` | Allows only subjects recognized as anonymous; e.g., a guest registration page. |
| `authenticated()` | Requires an authenticated identity, **excluding** anonymous; remember-me satisfies this rule. |
| `fullyAuthenticated()` | Requires an authenticated identity, excluding both anonymous and remember-me. |
| `hasRole("READER")` / `hasAuthority("document:read")` | Checks granted authorities; **does not replace** business resource-ownership checks. |
| `denyAll()` | Denies by default when no permissive rule matches. |

Example **configuration snippet** in a Spring Boot Servlet app with web/security dependencies; this snippet needs imports for `Bean`, `HttpSecurity`, `SecurityFilterChain`, and `Customizer`, and is not a standalone Java program:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/register").anonymous()
            .requestMatchers("/profile/**").authenticated()
            .requestMatchers("/payments/confirm").fullyAuthenticated()
            .anyRequest().denyAll()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
```

The application must also configure an appropriate user store, login flow, and authority policies. If remember-me is not enabled, `fullyAuthenticated()` is still valid, though there is no remember-me flow to contrast against. Whether a request receives 401/403 or redirects to the login page depends on the configured `AuthenticationEntryPoint` and `AccessDeniedHandler`.

**Scenario:** a visitor requests `/profile/me`. `AnonymousAuthenticationFilter` may have created an anonymous token, yet `authenticated()` still rejects it. When `ExceptionTranslationFilter` handles the missing authentication, it can invoke the entry point to start login, rather than treating an anonymous token with `isAuthenticated=true` as a real user and returning 403 by default. If a user is logged in yet lacks another permission, the application can return 403 per policy.

### Distinguishing `permitAll` and `anonymous`

`permitAll()` **does not mean** "only for unauthenticated visitors": users with a valid session can still access it. Conversely, `anonymous()` is a guest-only policy, so already logged-in users can be denied. That is useful for login/registration pages, though consider UX: redirecting logged-in users away from a registration screen is usually an app navigation choice, not a reason to weaken policies on sensitive endpoints.

## 8. Reading Anonymous in Spring MVC: Another Trap

There is a difference between **`SecurityContextHolder`** and the **Servlet principal API** when a request is anonymous.

In Spring MVC, a handler parameter of type `Authentication` or `Principal` can be resolved via `HttpServletRequest#getPrincipal()`. When anonymous, the Servlet API typically returns **`null`**, even while `SecurityContextHolder` holds an `AnonymousAuthenticationToken`. Therefore the pattern below is **unreliable for detecting anonymous** in Spring MVC:

```java
@GetMapping("/who-am-i")
String whoAmI(Authentication authentication) {
    return authentication instanceof AnonymousAuthenticationToken
        ? "anonymous"
        : "not anonymous";
}
```

It can return `not anonymous` on an anonymous request because the `authentication` parameter is actually `null`.

**When you genuinely need to inspect anonymous tokens too in a controller**, Spring Security provides `@CurrentSecurityContext`:

```java
// Snippet inside a @RestController with Spring Security MVC integration.
// Imports: GetMapping, CurrentSecurityContext, SecurityContext,
// Authentication, AuthenticationTrustResolver, AuthenticationTrustResolverImpl.
@GetMapping("/who-am-i")
String whoAmI(@CurrentSecurityContext SecurityContext context) {
    Authentication token = context.getAuthentication();
    AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();

    if (resolver.isAnonymous(token)) {
        return "anonymous";
    }
    if (!resolver.isAuthenticated(token)) {
        return "missing-or-unauthenticated";
    }
    return resolver.isFullyAuthenticated(token)
        ? "fully-authenticated"
        : "remember-me";
}
```

This illustrates **observing state**, not a reason to check permissions manually in every controller. URL policies and method security should handle access control. In custom authentication systems, the last branch might classify remembered tokens depending on the resolver; returning `remember-me` here assumes the default mechanism.

When moving to asynchronous execution, thread pools, or the reactive stack, never read context from an arbitrary thread assuming it carries the original request's identity. Context propagation depends on the runtime; the controller snippet above applies to **Servlet/Spring MVC**.

## 9. When Should You Use `AuthenticationTrustResolver` Directly?

Most applications only need the **authorization DSL**: `permitAll()`, `authenticated()`, `fullyAuthenticated()`, `anonymous()`, `hasRole()`. That is where security policies are expressed clearly, instead of scattering conditionals through controllers.

Using `AuthenticationTrustResolver` directly is helpful when:

1. Building an **audit/logging** component that needs to know whether the current request is anonymous, remembered, or authenticated without storing secrets.
2. Developing a custom `AuthorizationManager` or security component that needs to distinguish trust levels.
3. Returning user state in a session-inspection endpoint, with an explicit contract for anonymous/remember-me and possible empty contexts.
4. Tracing 401/403 error handling or entry points where recognizing anonymous affects how the system prompts the user to log in.

Pure Java classification example:

```java
// Illustrative helper using a standard AuthenticationTrustResolver.
String category(Authentication token, AuthenticationTrustResolver trust) {
    if (token == null) {
        return "missing";
    }
    if (trust.isAnonymous(token)) {
        return "anonymous";
    }
    if (trust.isRememberMe(token)) {
        return "remember-me";
    }
    if (trust.isFullyAuthenticated(token)) {
        return "fully-authenticated";
    }
    return "not-authenticated";
}
```

Never use `authentication.getName().equals("anonymousUser")` to distinguish anonymous: the name is configurable or could collide with a real username. Never use `getAuthorities().contains("ROLE_ANONYMOUS")` as raw string matching: authorities are `GrantedAuthority` instances, role names are configurable, and client-asserted roles are not proof. The resolver expresses state classification cleanly.

## 10. Mistakes That Easily Create Vulnerabilities

**Mistake A — "Having an `Authentication` means logged in."** The anonymous filter intentionally puts a token in the context. Replace existence checks with the resolver or appropriate policies.

**Mistake B — "The `Authentication.isAuthenticated()` flag is always enough."** Anonymous tokens can return true. Use `AuthenticationTrustResolver.isAuthenticated(...)` or the `authenticated()` DSL when checking for an authenticated user.

**Mistake C — "`anonymousUser` is an account in the identity store."** It is merely the default principal for the anonymous representation. Never create a real user named `anonymousUser` to "fix" behavior or use that name as an ownership key.

**Mistake D — "`ROLE_ANONYMOUS` is proof the client can send."** The mechanism must be server-managed; clients cannot define their own authorities. Never treat the anonymous provider's key as a security boundary.

**Mistake E — "Remember-me equals full login."** `resolver.isAuthenticated(...)` may be true for remember-me, while `isFullyAuthenticated(...)` is false. Enforce step-up/re-login on risky operations.

**Mistake F — "`fullyAuthenticated()` guarantees MFA."** Spring Security only determines it is neither anonymous nor remember-me under the standard resolver; never equate it with identity assurance level, MFA, or recent re-authentication.

**Mistake G — "A `permitAll()` endpoint is guest-only."** `permitAll` accepts logged-in users too. To restrict to anonymous guests only, express that explicitly and consider logged-in user UX.

**Mistake H — "I can read the anonymous token via a Spring MVC `Authentication` parameter."** Due to Servlet principal integration, the parameter can be null. Use `@CurrentSecurityContext` when you genuinely need to observe the anonymous token.

**Mistake I — "With no token, `resolver.isAnonymous(null)` must be true."** The resolver returns false for null; missing token and anonymous token are two distinct states. Neither represents a logged-in user.

**Mistake J — Manually creating `authenticated` tokens from JSON/forms.** Use `AuthenticationManager` and an appropriate provider for verification. Constructors in the demo exist solely to illustrate classification, not to implement production login.

## 11. Self-Check

**Question 1.** On a request carrying no credentials, the context holds `AnonymousAuthenticationToken` with `isAuthenticated()==true`. Has the user logged in?

**Answer:** No. `AuthenticationTrustResolver.isAnonymous(token)` returns true, and the resolver's `isAuthenticated(token)` returns false.

**Question 2.** Why can `/public` still work without a real user?

**Answer:** The `permitAll()` policy allows public requests; the anonymous filter can provide a representation for the context. No DB account or login is needed.

**Question 3.** Can a remember-me token pass `authenticated()`? What about `fullyAuthenticated()`?

**Answer:** Under standard classification, `authenticated()` permits remember-me; `fullyAuthenticated()` excludes it.

**Question 4.** Does `isFullyAuthenticated(token) == true` prove MFA occurred?

**Answer:** No. It only excludes anonymous/remember-me per the resolver, and does not verify MFA factors or authentication recency.

**Question 5.** In Spring MVC, which controller parameter should be used to inspect the current `AnonymousAuthenticationToken`?

**Answer:** `@CurrentSecurityContext SecurityContext context` to call `context.getAuthentication()`; an `Authentication` parameter resolved by MVC from the Servlet principal can be null when anonymous.

**Question 6.** What is the difference between `null` and an anonymous token?

**Answer:** Null means no authentication object is present. An anonymous token is an object created by the framework to represent a guest; the resolver recognizes it as anonymous. In both cases, the resolver's `isAuthenticated(...)` returns false.

## 12. Official References

- [Spring Security 6.5 — Anonymous Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/anonymous.html): rationale for anonymous tokens, filter, provider, trust resolver, and Spring MVC details.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContext`, and the authentication flow.
- [AuthenticationTrustResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html): contracts of `isAnonymous`, `isRememberMe`, `isAuthenticated`, and `isFullyAuthenticated`.
- [AuthenticationTrustResolverImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationTrustResolverImpl.html): default implementation based on token type.
- [AnonymousAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AnonymousAuthenticationToken.html): constructors, principal, authorities, and status flag.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): HTTP access control policies.

**Conclusion:** `AnonymousAuthenticationToken` helps represent an unauthenticated guest in `SecurityContext`, yet proves no identity. Use `AuthenticationTrustResolver` to ask accurately "is this anonymous, remember-me, or an authenticated user?", and use authorization rules to decide access rights. The mere presence of a token, or `isAuthenticated` being true on that token, is insufficient to conclude a real user has logged in.