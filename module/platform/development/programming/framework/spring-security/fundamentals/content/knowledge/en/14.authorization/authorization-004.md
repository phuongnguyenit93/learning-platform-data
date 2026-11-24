# authenticated, anonymous, rememberMe, and fullyAuthenticated in Spring Security

In an application with login, the question “is the user authenticated?” is not enough to determine every access permission. Spring Security distinguishes **anonymous** visitors, users **re-identified from persistent login memory**, and users who are **fully authenticated**. The four authorization conditions `authenticated`, `anonymous`, `rememberMe`, and `fullyAuthenticated` let policies use those trust levels.

This lesson belongs to the **Authorization** topic of Spring Security fundamentals: the goal is to properly understand authorization conditions, write HTTP/method security rules, and predict outcomes before testing. The main examples use Java 17+, Spring Security 6.3.x with Servlet (`HttpSecurity`). The end of the lesson distinguishes what applies to WebFlux; do not mechanically copy Servlet syntax into reactive code.

## 1. The Problem: One Identity With Multiple Trust States

Imagine a banking application with three features:

- Overview page: anyone can read it.
- View personal dashboard: users who logged in directly or were re-authenticated via remember-me can view it.
- Change payment details: requires a fully authenticated session; re-authentication solely via a remember-me cookie is not enough.

If everything is configured with `authenticated()`, a user restored from remember-me can enter sensitive pages as well. If the personal dashboard is mistakenly configured with `rememberMe()`, a user who just logged in directly can be denied even though their authentication level is stronger. Therefore, first distinguish the **four conditions** and the **`Authentication` object states** they recognize.

Spring Security uses the concept of *authentication trust level* to make access decisions. This is an aspect of **authorization** (whether an action is permitted), yet it relies on how the application performed **authentication** (identifying the principal). Do not equate it with business permissions such as `ROLE_ADMIN`.

## 2. The Essential Comparison Table

The table below assumes Spring Security's default trust resolver and tokens, a user in a valid complete state, and a rule checking only the corresponding single condition.

| Request state | `authenticated()` | `anonymous()` | `rememberMe()` | `fullyAuthenticated()` |
| --- | :---: | :---: | :---: | :---: |
| Anonymous guest with `AnonymousAuthenticationToken` | ❌ | ✅ | ❌ | ❌ |
| User recognized via `RememberMeAuthenticationToken` | ✅ | ❌ | ✅ | ❌ |
| Fully logged-in user (e.g., successful `UsernamePasswordAuthenticationToken`) | ✅ | ❌ | ❌ | ✅ |

Reading the table by each condition:

- **`authenticated()`**: accepts users who are authenticated and not anonymous; **includes remember-me and full authentication**.
- **`anonymous()`**: matches only the anonymous state recognized by Spring Security; it is **not** another name for `permitAll()`.
- **`rememberMe()`**: true when the user was recognized by the remember-me mechanism; in the default resolvers, **a fully logged-in user is not considered “logged in via remember-me”**.
- **`fullyAuthenticated()`**: true when the user is authenticated and **neither anonymous nor remember-me**.

The table describes **individual conditions**, not yet including roles, resource permissions, session lifetime, device constraints, or multi-factor authentication. Routes can also add `hasRole` / `hasAuthority` and many other checks.

**Note on having no `Authentication` (`null`):** that is not an `AnonymousAuthenticationToken`. In standard Servlet configurations, `AnonymousAuthenticationFilter` creates an anonymous token when needed; if you intentionally disable this mechanism, do not assume `anonymous()` still has an anonymous token to evaluate. When there is no valid identity, rules requiring authentication are not satisfied.

## 3. authenticated(): Authenticated, Including Remember-Me

### Meaning

`authenticated()` is the common condition for personal pages or APIs requiring an authenticated identity. It allows:

- Users who recently logged in with password/OIDC or an equivalent complete authentication mechanism.
- Users whose login was restored via remember-me, if the application actually supports it and successfully verified the remember-me cookie.

It does **not** permit anonymous guests merely because Spring Security placed an anonymous token into the security context.

Servlet example:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/account/**").authenticated()
        .anyRequest().denyAll()
);
~~~

If `/account/profile` needs to show a basic profile, this may be an appropriate policy. If `/account/change-password` also falls under this pattern, create a separate exception using `fullyAuthenticated()` or a stronger authentication policy and place the specific rule before the broad rule.

### Why Not Check Authentication.isAuthenticated() Directly?

`Authentication.isAuthenticated()` is a flag indicating the token object was marked authenticated; it is **not the full contract of Spring Security's `authenticated` condition**. In particular, `AnonymousAuthenticationToken` normally has `isAuthenticated() == true` to handle the security context uniformly, yet it does **not** represent a logged-in user.

The following hand-written check is error-prone:

~~~java
// Wrong if treated as the definition of "a logged-in user".
boolean loggedIn = authentication != null && authentication.isAuthenticated();
~~~

Use the framework-provided rule, or when checking manually use `AuthenticationTrustResolver` / `AuthenticatedAuthorizationManager` appropriately instead of relying solely on the flag.

## 4. anonymous(): Requires an Anonymous Guest, Does Not Mean “Public Page”

Spring Security can place an `AnonymousAuthenticationToken` into `SecurityContextHolder` in the Servlet chain so downstream components always have an object representing the visitor, even when unauthenticated. The token usually carries a name like `anonymousUser` and authority `ROLE_ANONYMOUS`.

The `anonymous()` condition is used when **only unauthenticated guests** should access a feature, such as a dedicated guest onboarding page.

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/guest-only/**").anonymous()
        .anyRequest().authenticated()
);
~~~

Once fully logged in or recognized via remember-me, requests matching `/guest-only/**` do not satisfy `anonymous()`. It is a condition on **visitor state**; it does not automatically redirect logged-in users to another page.

**Difference from `permitAll()`:**

| Rule | Anonymous guest | Remember-me | Fully authenticated | Purpose |
| --- | :---: | :---: | :---: | --- |
| `permitAll()` | ✅ | ✅ | ✅ | Public resources for everyone |
| `anonymous()` | ✅ | ❌ | ❌ | Unauthenticated guests only |
| `authenticated()` | ❌ | ✅ | ✅ | Authenticated users |

Login pages, landing pages, and static assets usually fit `permitAll()`: logged-in users can still load them if needed. A guest-only page is a narrower case; never use `anonymous()` simply thinking it means “public”.

In Servlet, `AnonymousAuthenticationFilter` normally runs when there is no `Authentication`, but only when the anonymous mechanism is enabled in the security chain. In WebFlux, how anonymous is populated into the context and configured differs, so check the reactive API/configuration for the version in use.

## 5. rememberMe(): Knowing the User via Login Memory

### How Does Remember-Me Actually Work?

Remember-me is a mechanism that re-identifies a user across subsequent visits, typically using a long-lived cookie. On Servlet, Spring Security supports token-signature-based or server-side persistent-token solutions. When the cookie is valid and the remember-me filter runs properly, the system builds a `RememberMeAuthenticationToken` and puts it into the security context.

Overview flow:

~~~text
Interactive login succeeds
  ↓
Application issues remember-me cookie (if enabled and issuance criteria met)
  ↓
A later visit, no direct login session remains
  ↓
RememberMeAuthenticationFilter validates cookie
  ↓
RememberMeAuthenticationToken
  ↓
authenticated()  = true
rememberMe()     = true
fullyAuthenticated() = false
~~~

The key point is that **remember-me can authenticate an identity at a remembered level**, yet the application may require another direct authentication step before sensitive operations.

### rememberMe() Does Not Mean “Remember-Me or Stronger”

The `rememberMe()` condition of `AuthenticatedAuthorizationManager` / Servlet DSL checks specifically for users **recognized via remember-me**, not a trust-level comparison of “at least remember-me”. Therefore:

- `rememberMe()`: remember-me user **passes**; fully logged-in user **fails**.
- `authenticated()`: **both** authenticated states pass.
- `fullyAuthenticated()`: only fully authenticated users pass.

`rememberMe()` makes sense when you need to **distinguish the remember-me session group** to provide a special behavior or route. For features accessible to both remember-me and directly logged-in users, **choose `authenticated()`**, optionally combined with roles/permissions.

### How Does Remember-Me Differ from a Maintained HTTP Session?

A user with a session cookie (`JSESSIONID` or similar session store) after logging in successfully can remain a **fully authenticated** user across subsequent requests; a long-lived session does not automatically turn into remember-me. Conversely, when the direct session is gone, the remember-me mechanism can re-identify the user with its separate cookie and create a `RememberMeAuthenticationToken`.

Do not infer the authentication type merely from “the browser auto-logged in” or “there is a cookie”. Inspect which filter/mechanism produced the `Authentication`.

### Security When Using Remember-Me

A remember-me cookie is sensitive authentication material. In a real application, use HTTPS, proper cookie attributes (`Secure`, `HttpOnly`, `SameSite` per context), reasonable lifetimes, invalidation workflows on logout/password change, and an appropriate token storage strategy. If stolen, a long-lived cookie can be reused until it expires or is revoked.

Features like changing passwords, transferring funds, or changing account recovery methods should not rely solely on remember-me. `fullyAuthenticated()` can be an **additional requirement layer**, though it does not replace recent re-authentication near transaction time or MFA when policy demands it.

## 6. fullyAuthenticated(): Neither Anonymous Nor Remember-Me

`fullyAuthenticated()` requires Spring Security to consider the user authenticated by a mechanism other than remember-me. Its difference from `authenticated()` is that it **excludes remember-me**.

Example for sensitive pages:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/account/confirm-sensitive/**").fullyAuthenticated()
        .requestMatchers("/account/**").authenticated()
        .anyRequest().denyAll()
);
~~~

The specific rule must come **before** `/account/**` because the configuration picks the first matching rule. When a remember-me user accesses `/account/confirm-sensitive/email`, the `fullyAuthenticated` condition fails. Depending on error handling and the authentication entry point, the application may prompt for re-login rather than simply returning 403.

**Do not infer `fullyAuthenticated()` to mean:**

- The user just entered their password on the current request.
- MFA, biometrics, passkey, or an additional verification step was completed.
- The session is fresh within the last few minutes.
- The user holds a special role like ADMIN.

It speaks only to the **trust-level classification recognized by `AuthenticationTrustResolver`**. A session created hours ago after full login can still satisfy it. To enforce *step-up authentication* or recent re-authentication before a transaction, dedicated rules and mechanisms are needed: authentication timestamps, assurance levels from the identity provider, factor re-verification, or transaction-specific authentication; never use this condition name as proof of MFA.

## 7. Internal Mechanism: AuthenticationTrustResolver

Spring Security does not determine the four conditions simply by comparing strings `"anonymous"` or `"remember-me"`. The primary component is `AuthenticationTrustResolver`, implemented by `AuthenticationTrustResolverImpl`. Under the default model:

~~~text
Authentication
    |
    +-- null / no valid authentication
    |       └── fails authenticated / fullyAuthenticated
    |
    +-- AnonymousAuthenticationToken
    |       └── anonymous
    |
    +-- RememberMeAuthenticationToken
    |       └── remembered
    |
    +-- Fully authenticated token (and not in the two groups above)
            └── fullyAuthenticated
~~~

Corresponding checks:

- `isAnonymous(authentication)`: identifies anonymous users, typically via `AnonymousAuthenticationToken`.
- `isRememberMe(authentication)`: identifies remembered users, typically via `RememberMeAuthenticationToken`.
- `isAuthenticated(authentication)`: valid authentication value, not anonymous; usually includes remember-me and fully authenticated.
- `isFullyAuthenticated(authentication)`: valid authentication that is not remember-me; also excludes anonymous.

Logically, under the default trust configuration:

~~~text
authenticated        = authenticated and NOT anonymous
rememberMe           = token marked as remember-me
fullyAuthenticated   = authenticated and NOT remember-me
anonymous            = token marked as anonymous
~~~

The first line is the **policy meaning**: do not confuse it with calling `Authentication.isAuthenticated()`, which can return true on an anonymous token. With a custom `AuthenticationTrustResolver`, behavior may differ because token classification has changed.

### Missing Token Case and HTTP Handling

Having no valid `Authentication` or having an anonymous token does not mean the framework always returns the same HTTP status code. A request to a protected route might receive HTTP 401 if HTTP Basic/Bearer is configured, or HTTP 302 to a login screen with form login. When a user is logged in but lacks a business permission, 403 is the typical response. For a remember-me session blocked because `fullyAuthenticated` is required, the exception-handling filter can re-trigger authentication.

Therefore, **distinguish the authorization decision result from the final HTTP response**. Components such as `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler` (Servlet) determine the next step based on authentication state and configuration.

## 8. Complete Servlet Configuration: Four Conditions Across Four URLs

Below is a Java 17+ configuration using Spring Boot with `spring-boot-starter-web` and `spring-boot-starter-security`. Place it in `SecurityConfig.java` under your Java source directory and add a `package` declaration matching your project.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/css/**", "/login").permitAll()
                .requestMatchers("/guest-only/**").anonymous()
                .requestMatchers("/remember-only/**").rememberMe()
                .requestMatchers("/account/payment/**").fullyAuthenticated()
                .requestMatchers("/account/**").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .rememberMe(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Path meanings:

| Path | Rule | Example purpose |
| --- | --- | --- |
| `/`, `/css/**`, `/login` | `permitAll()` | Public resources |
| `/guest-only/**` | `anonymous()` | Guest-only experience |
| `/remember-only/**` | `rememberMe()` | Illustrates a route limited to remember-me state |
| `/account/payment/**` | `fullyAuthenticated()` | Rejects sessions recognized solely via remember-me |
| `/account/**` | `authenticated()` | Basic account area, accepts both remember-me and full login |
| All unlisted paths | `denyAll()` | Default deny |

**This is a teaching example of authorization conditions.** The endpoints in the table must be implemented separately (Controller, HTML, etc.) for real requests to return content. Remember-me configuration also needs an appropriate `UserDetailsService` and proper cookie/token policy for the deployment environment; the snippet above does not create a user database or Controller. In real systems, `/remember-only/**` is rarely needed; `authenticated()` is normally used so both authenticated states have access.

**Rule order determines the outcome:** If `.requestMatchers("/account/**").authenticated()` is written before `.requestMatchers("/account/payment/**").fullyAuthenticated()`, the sensitive path matches the broad rule first, losing the full-authentication requirement. This is a serious authorization bug even when every individual line is syntactically valid.

### Enabling Remember-Me Does Not Turn Every Session Into Remember-Me

`.rememberMe(Customizer.withDefaults())` enables the remember-me mechanism in the Servlet application. Normal interactive logins can still be treated as fully authenticated. Only when a subsequent request is authenticated via remember-me does Spring Security create a remember-me token. Test **both** direct login, cookie restoration, and logged-out sessions.

In production applications, specify a signing key and persistent token repository as required, rather than assuming a minimal demo configuration is safe enough. You must still handle CSRF protection, cookie constraints, token lifecycle, and revocation when credentials change.

## 9. Using in Method Security: @PreAuthorize

The four conditions also appear as Spring Security expressions, suitable when checking **business operations**, not just URLs. For Java Servlet using method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Once enabled, methods can be protected with expressions:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AccountService {

    @PreAuthorize("isAuthenticated()")
    public String readBasicProfile() {
        return "Basic profile";
    }

    @PreAuthorize("isAnonymous()")
    public String startGuestOnboarding() {
        return "Guest onboarding";
    }

    @PreAuthorize("isRememberMe()")
    public String explainRememberedSession() {
        return "Remembered session";
    }

    @PreAuthorize("isFullyAuthenticated() and hasRole('USER')")
    public String viewSensitiveAccountDetails() {
        return "Sensitive details";
    }
}
~~~

The code above represents two independent Java files inside **one Spring application** (`MethodSecurityConfiguration.java` and `AccountService.java`). They are shown to illustrate expressions and must run inside an application with method security configured. Never call the methods directly on an object instantiated via `new AccountService()` and treat that as a security test: doing so bypasses the proxy/interceptor Spring uses to enforce `@PreAuthorize`.

Two important notes:

1. `hasRole('USER')` checks the `ROLE_USER` authority by default convention, which is **different** from the fully authenticated state. A user having `ROLE_USER` but recognized only via remember-me **does not** satisfy `isFullyAuthenticated()`.
2. `isRememberMe()` is a condition matching only the remember-me state. If access should be allowed from remember-me upwards, use `isAuthenticated()` instead of `isRememberMe()`.

With WebFlux method security, the configuration mechanism and reactive return chain must match (`@EnableReactiveMethodSecurity` for reactive configuration); do not mix Servlet proxies and security-context lookup with Reactor.

## 10. Testing With Real Spring Security Tokens

Do not test only with a `UsernamePasswordAuthenticationToken` and extrapolate anonymous/remember-me behavior. In unit tests, build all three token types and verify each condition.

Assume the project uses Spring Boot 3.3.x with Spring Security 6.3.x and these dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Place `TrustLevelTest.java` in `src/test/java` of the project (add a `package` line matching your directory). The example below tests both `AuthenticationTrustResolver` and `AuthenticatedAuthorizationManager`; `check(...)` is an API available in Spring Security 6.3.x.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TrustLevelTest {

    private final AuthenticationTrustResolver trust =
            new AuthenticationTrustResolverImpl();

    private Authentication anonymous() {
        return new AnonymousAuthenticationToken(
                "demo-key", "guest",
                AuthorityUtils.createAuthorityList("ROLE_ANONYMOUS"));
    }

    private Authentication remembered() {
        return new RememberMeAuthenticationToken(
                "demo-key", "mai",
                AuthorityUtils.createAuthorityList("ROLE_USER"));
    }

    private Authentication fullyLoggedIn() {
        return UsernamePasswordAuthenticationToken.authenticated(
                "mai", "n/a",
                AuthorityUtils.createAuthorityList("ROLE_USER"));
    }

    @Test
    void anonymousTokenIsNotARealLogin() {
        Authentication auth = anonymous();

        // Trap: the anonymous token's flag can still be true.
        assertTrue(auth.isAuthenticated());
        assertTrue(trust.isAnonymous(auth));
        assertFalse(trust.isAuthenticated(auth));
        assertFalse(trust.isRememberMe(auth));
        assertFalse(trust.isFullyAuthenticated(auth));
    }

    @Test
    void rememberMeIsAuthenticatedButNotFullyAuthenticated() {
        Authentication auth = remembered();

        assertFalse(trust.isAnonymous(auth));
        assertTrue(trust.isAuthenticated(auth));
        assertTrue(trust.isRememberMe(auth));
        assertFalse(trust.isFullyAuthenticated(auth));
    }

    @Test
    void interactiveLoginIsFullyAuthenticated() {
        Authentication auth = fullyLoggedIn();

        assertFalse(trust.isAnonymous(auth));
        assertTrue(trust.isAuthenticated(auth));
        assertFalse(trust.isRememberMe(auth));
        assertTrue(trust.isFullyAuthenticated(auth));
    }

    @Test
    void policyFactoriesDistinguishTheFourStates() {
        Object resource = new Object();
        Authentication guest = anonymous();
        Authentication remembered = remembered();
        Authentication full = fullyLoggedIn();

        var anyAuthenticated =
                AuthenticatedAuthorizationManager.<Object>authenticated();
        var onlyAnonymous =
                AuthenticatedAuthorizationManager.<Object>anonymous();
        var onlyRemembered =
                AuthenticatedAuthorizationManager.<Object>rememberMe();
        var onlyFully =
                AuthenticatedAuthorizationManager.<Object>fullyAuthenticated();

        assertFalse(anyAuthenticated.check(() -> guest, resource).isGranted());
        assertTrue(anyAuthenticated.check(() -> remembered, resource).isGranted());
        assertTrue(anyAuthenticated.check(() -> full, resource).isGranted());

        assertTrue(onlyAnonymous.check(() -> guest, resource).isGranted());
        assertFalse(onlyAnonymous.check(() -> remembered, resource).isGranted());
        assertFalse(onlyAnonymous.check(() -> full, resource).isGranted());

        assertFalse(onlyRemembered.check(() -> guest, resource).isGranted());
        assertTrue(onlyRemembered.check(() -> remembered, resource).isGranted());
        assertFalse(onlyRemembered.check(() -> full, resource).isGranted());

        assertFalse(onlyFully.check(() -> guest, resource).isGranted());
        assertFalse(onlyFully.check(() -> remembered, resource).isGranted());
        assertTrue(onlyFully.check(() -> full, resource).isGranted());
    }
}
~~~

Run the test in a project configured with JUnit Platform:

~~~bash
./gradlew test --tests '*TrustLevelTest'
~~~

On Windows use `gradlew.bat test --tests "*TrustLevelTest"`. **Expected result:** all four test methods pass. This is an expectation based on the contract and the tokens constructed in code, not a log of an actual execution.

The purpose of this test is to demonstrate the state table; it does not test issuing cookies, running `RememberMeAuthenticationFilter`, HTTP filter matching, or status-code generation. Add `MockMvc` or real HTTP integration tests to verify those flows. With Spring Security versions where `AuthorizationManager.authorize(...)` is preferred, adjust the `check(...)` call for the version in use.

## 11. HTTP Testing: Predict the Decision Before Checking the Status Code

To integration-test the configuration in section 8, create a controller with matching paths. Send each request under **three authentication states** and verify whether it is allowed past the security layer:

| Endpoint | Anonymous | Remember-me | Fully authenticated |
| --- | :---: | :---: | :---: |
| `/` | Allow | Allow | Allow |
| `/guest-only/welcome` | Allow | Block | Block |
| `/remember-only/info` | Block | Allow | Block |
| `/account/profile` | Block | Allow | Allow |
| `/account/payment/confirm` | Block | Block | Allow |
| `/unknown` | Block | Block | Block |

“Allow” here means **passing the authorization step**. If no controller handles the path, the request may still receive 404. “Block” means **failing the authorization step**, without guaranteeing it always returns 401/403: form login may redirect the user to the login screen, and a remember-me session denied where full login is required may trigger re-login.

To simulate states during testing, you should:

- Use the filter's anonymous mechanism or `@WithAnonymousUser` if using Spring Security Test.
- Use `@WithMockUser` to represent an authenticated user in authorization tests; it is **not** equivalent to a remember-me token.
- To test the remember-me branch specifically, supply a `RememberMeAuthenticationToken` via `SecurityMockMvcRequestPostProcessors.authentication(...)` or generate a real remember-me cookie and pass through the filter chain.
- When testing cookie/login-chain correctness, use real integration tests instead of only manually creating tokens.

On failure, log the `Authentication` state, deciding filter/policy name, and matched path. A single HTTP status code is rarely enough to deduce which condition blocked the request.

## 12. Combining Authentication State With Roles/Permissions

The four conditions answer “how was the user identified?”, while `hasRole` / `hasAuthority` answer “what permissions does the user carry?”. The two questions are independent:

- A remember-me account with `ROLE_ADMIN` can still **fail** `fullyAuthenticated()`.
- A fully logged-in account lacking `ROLE_ADMIN` still **fails** `hasRole("ADMIN")`.
- `authenticated()` does not automatically grant ADMIN privilege or permission to act on a resource object.

Policies often need to combine conditions, such as “fully logged in **and** having approval permission”. In method security:

~~~java
@PreAuthorize("isFullyAuthenticated() and hasAuthority('PAYMENT_APPROVE')")
public void approvePayment(String paymentId) {
    // Business logic executed after the interceptor permits.
}
~~~

This is an **illustrative method snippet**, to be placed in a Spring bean with method security configured. Checking roles/permissions at the method layer matters when the same action can be called from HTTP, events, or other internal flows. Meanwhile, per-record permissions (owner, branch, amount, state) must still be evaluated separately.

Even with `fullyAuthenticated()` and `PAYMENT_APPROVE`, if business rules require re-authentication within 5 minutes or MFA at a specific assurance level, check the corresponding authentication timestamp/level; do not treat being fully logged in as automatic proof of freshness or MFA.

## 13. Distinguishing Servlet and WebFlux

The four conditions discussed in this lesson are Spring Security concepts/checks, but **the HTTP configuration interface is not identical between Servlet and WebFlux**.

In Servlet, `HttpSecurity.authorizeHttpRequests(...)` directly supports `authenticated()`, `anonymous()`, `rememberMe()`, and `fullyAuthenticated()` on the URL rule builder (depending on API version). Servlet also has `RememberMeAuthenticationFilter` and remember-me services.

In WebFlux, the common configuration is `ServerHttpSecurity.authorizeExchange(...)`. The `AuthorizeExchangeSpec.Access` API supports `authenticated()`, `permitAll()`, `denyAll()`, and role/authority rules; it **does not by default provide the exact same four Servlet DSL methods**. If you need a condition distinguishing token state, you can use `.access(ReactiveAuthorizationManager<AuthorizationContext>)` and read identity only through the Publisher supplied by the framework—do not use `ThreadLocal`-style `SecurityContextHolder` assuming a Servlet request context in reactive code.

Illustrative example of a WebFlux policy requiring full authentication, following the `ReactiveAuthorizationManager` contract in Spring Security 6.3.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        AuthenticationTrustResolver trust =
                new AuthenticationTrustResolverImpl();

        ReactiveAuthorizationManager<AuthorizationContext> requireFull =
                (authentication, context) -> authentication
                        .map(auth -> new AuthorizationDecision(
                                trust.isFullyAuthenticated(auth)))
                        .defaultIfEmpty(new AuthorizationDecision(false));

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/sensitive/**").access(requireFull)
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

This is an **alternative configuration when the application uses WebFlux**, not placed alongside the Servlet app above. It inspects the `Authentication` emitted by the Publisher and turns an empty emission into a deny decision. It **does not implement remember-me for WebFlux**; supporting remember-me via custom cookies requires designing and testing an authentication flow compatible with reactive applications. Custom tokens or custom trust resolvers must also be reviewed to ensure `isFullyAuthenticated` matches the policy.

## 14. Confusions That Lead to Authorization Vulnerabilities

1. **Confusing `anonymous()` with `permitAll()`.** The first is for anonymous guests only, whereas the latter allows all access states.
2. **Confusing `rememberMe()` with “remember-me or stronger login”.** This condition matches **specifically** the remember-me state; to include fully logged-in users, choose `authenticated()`.
3. **Confusing `authenticated()` with `fullyAuthenticated()`.** The `authenticated` condition includes remember-me, so it is not automatically suitable for all sensitive operations.
4. **Relying on `Authentication.isAuthenticated()` and forgetting anonymous tokens.** Use the framework's policy or `AuthenticationTrustResolver`.
5. **Using `fullyAuthenticated()` as proof of completed MFA.** This condition does not guarantee authentication method, freshness, device, or risk level.
6. **Placing broad URL rules before sensitive rules.** `/account/**` captures `/account/payment/**` first, causing the stricter policy never to be evaluated.
7. **Assuming any cookie means remember-me.** An HTTP session cookie and a remember-me cookie are two different things; inspect the actual authentication token.
8. **Hardcoding every denial as 403.** Unauthenticated/remember-me requests requiring re-login may trigger `AuthenticationEntryPoint`.
9. **Writing `rememberMe()` rules without enabling or properly configuring remember-me.** When no path produces a `RememberMeAuthenticationToken`, testing that branch has no practical meaning.
10. **Copying Servlet DSL into WebFlux.** API methods can differ; verify the actual version and interface before using.

## 15. Self-Check Questions

**Question 1.** A user restored from a remember-me cookie wants to view `/account/profile` protected by `authenticated()`. Does it satisfy the condition?

**Answer:** Yes, if remember-me was validly authenticated; `authenticated` accepts remember-me.

**Question 2.** A directly logged-in user accesses `/remember-only/info` protected by `rememberMe()`. Does it satisfy the condition?

**Answer:** No under default classification; `rememberMe()` checks the remember-me state, not “at least remembered”. To allow both states, use `authenticated()`.

**Question 3.** `AnonymousAuthenticationToken.isAuthenticated()` returns true. Does that prove the guest is logged in?

**Answer:** No. `AuthenticationTrustResolver.isAnonymous(...)` still identifies it as an anonymous guest and `isAuthenticated(...)` does not treat that token as a user login.

**Question 4.** Can `fullyAuthenticated()` be used to guarantee an operation is performed only within 5 minutes of re-entering a password?

**Answer:** No. You need a re-authentication mechanism and a check on timestamps or additional authentication proof.

**Question 5.** Do `permitAll()` and `anonymous()` give the same result for a logged-in user?

**Answer:** No. `permitAll()` permits; `anonymous()` does not match.

**Question 6.** Does a remember-me account with role ADMIN automatically pass `fullyAuthenticated()`?

**Answer:** No. The ADMIN role and authentication trust level are two separate conditions. A policy can require both.

## Reference Documentation

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthenticatedAuthorizationManager` and trust levels.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): URL rules, matcher ordering, `permitAll`, and permission handling.
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html): role of `AnonymousAuthenticationToken`.
- [Spring Security — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html): tokens/cookies and `RememberMeServices`.
- [AuthenticationTrustResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html): `isAuthenticated`, `isAnonymous`, `isRememberMe`, and `isFullyAuthenticated`.
- [AuthenticatedAuthorizationManager API 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authorization/AuthenticatedAuthorizationManager.html): the `authenticated`, `anonymous`, `rememberMe`, and `fullyAuthenticated` managers.
- [ServerHttpSecurity.AuthorizeExchangeSpec.Access API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html): direct conditions of the WebFlux DSL.
