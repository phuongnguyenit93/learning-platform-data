# authenticated, fullyAuthenticated, rememberMe, and anonymous in HTTP Authorization (Spring Security Servlet)

## 1. The Problem: All Are Authentication, Yet Trust Levels Differ

An HTTP request can pass through `AuthorizationFilter` with an `Authentication` object representing:

- **Anonymous** — not logged in; the framework may place an `AnonymousAuthenticationToken` in the context for uniform handling.
- **Remember-me** — the user previously selected "remember me"; the full session is gone, yet the remember-me cookie is validated and creates a `RememberMeAuthenticationToken`.
- **Full authentication** — the user has just logged in or is logged in via a mechanism Spring Security treats as full authentication, such as username/password form login, and that state remains valid in the session.

Spring Security has four conditions that are very easy to confuse when writing HTTP authorization rules:

```java
.authenticated()
.fullyAuthenticated()
.rememberMe()
.anonymous()
```

They are **not four synonyms for "has permission"**. They depend on the type and trust level of the `Authentication`, which differs from checking authorities via `hasRole`/`hasAuthority`.

Business requirement examples:

- `/account` may allow both form login and remember-me.
- `/settings/security` should require full authentication, not just remember-me.
- `/welcome-new` is only for users who are not logged in.
- Illustrative endpoint `/remember-only` may only be accessed when the request is actually authenticated via remember-me.
- `/admin-sensitive` must check **both** the admin role **and** full authentication.

This lesson focuses on **Spring Security Servlet HTTP authorization decisions**, without conflating "enabling remember-me" with "writing a rememberMe matcher".

### 1.1. Learning Outcomes

After this lesson, you will be able to:

1. Predict whether a request is allowed or denied under each predicate.
2. Understand why `Authentication.isAuthenticated()` alone is insufficient to distinguish anonymous users.
3. Use `authorizeHttpRequests` with the right rules, in the right order.
4. Distinguish needing login (form redirect) from being authenticated yet failing a rule.
5. Combine authentication trust and authority/role on sensitive endpoints.
6. Test in practice using Spring Boot 3, Java 17, MockMvc, form login, and remember-me cookies.

## 2. Classifying States with AuthenticationTrustResolver

In Spring Security, `AuthenticationTrustResolver` is the abstraction used to identify the trust level of an authentication. The common implementation is `AuthenticationTrustResolverImpl`.

Key meanings:

- `isAnonymous(authentication)`: the token is of anonymous type per the trust resolver.
- `isRememberMe(authentication)`: the token is of remember-me type.
- `isAuthenticated(authentication)`: authenticated as recognized by the framework, not anonymous.
- `isFullyAuthenticated(authentication)`: validly authenticated and **neither** anonymous **nor** remember-me.

Here is the model table for standard tokens:

| Request Type | `isAnonymous` | `isRememberMe` | `isAuthenticated` | `isFullyAuthenticated` |
| --- | --- | --- | --- | --- |
| Anonymous | true | false | false | false |
| Valid remember-me | false | true | true | false |
| Full form login | false | false | true | true |

The table assumes tokens are created normally by Spring Security without a custom resolver. A custom `Authentication` or special setup must be tested against the system's actual resolver.

### 2.1. Pitfall: AnonymousAuthenticationToken.isAuthenticated()

`AnonymousAuthenticationToken` can have `isAuthenticated() == true` per the token API, even though the user has not proven an identity. Therefore self-written logic like:

```java
// DO NOT use alone to detect a genuinely logged-in user:
if (authentication != null && authentication.isAuthenticated()) {
    // ...
}
```

can draw the wrong conclusion about anonymous users. For HTTP authorization, use `authenticated()` and Spring Security's predicates instead of relying solely on that flag.

### 2.2. "Fully Authenticated" Does Not Mean MFA Was Completed

In this context "fully" means neither anonymous nor remember-me according to the trust resolver. It **does not automatically prove** the user:

- completed MFA;
- recently entered their password within the last few minutes;
- is using a trusted device;
- has permission to access another user's resources;
- has an unhijacked session;
- underwent step-up authentication for a funds transfer.

When business logic requires recent reauthentication or MFA, you must design additional policies on recency/level of authentication rather than relying solely on `fullyAuthenticated()`.

## 3. Truth Table of the Four HTTP Rules

Assume Spring Security Servlet has anonymous and remember-me enabled in a typical configuration.

| Rule | Anonymous | Remember-me | Full login |
| --- | --- | --- | --- |
| `authenticated()` | No | Yes | Yes |
| `fullyAuthenticated()` | No | No | Yes |
| `rememberMe()` | No | Yes | No |
| `anonymous()` | Yes | No | No |
| `permitAll()` | Yes | Yes | Yes |
| `denyAll()` | No | No | No |

**Key takeaway:** `rememberMe()` and `anonymous()` are **state-identifying predicates**, not "at least this trust level".

If a full-login user accesses an endpoint allowing only `rememberMe()`, the request **does not** satisfy that rule. Even though full authentication is normally stronger than remember-me, Spring Security does not interpret `rememberMe()` as "remember-me or higher". When you want to allow both remember-me and full, use `authenticated()`.

Conversely, `anonymous()` is not appropriate for every public page. An `/about` page for both guests and members should use `permitAll()`; if `anonymous()` is used, logged-in users will be denied.

### 3.1. Example Bound to URLs

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/welcome-new").anonymous()
    .requestMatchers("/account").authenticated()
    .requestMatchers("/remember-only").rememberMe()
    .requestMatchers("/settings/security").fullyAuthenticated()
    .anyRequest().denyAll()
);
```

This is a **snippet inside a SecurityFilterChain**, not a standalone runnable program. It defines authorization rules rather than configuring form login or remember-me cookies. The complete Maven example below declares the authentication mechanisms as well.

### 3.2. Distinguishing "Enabling Remember-Me" from "the rememberMe Rule"

There are two different APIs:

```java
// Enable automatic authentication using a remember-me cookie:
http.rememberMe(remember -> remember
    .key("only-for-demo")
    .userDetailsService(users));

// Authorization rule: this request must currently be in remember-me state:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/remember-only").rememberMe());
```

These are two illustrative configuration snippets (the first needs `HttpSecurity http` and `UserDetailsService users`). **The second line does not issue or validate remember-me cookies**. Without enabling remember-me authentication or another mechanism producing `RememberMeAuthenticationToken`, the `rememberMe()` endpoint may never be accessible.

## 4. Where Do They Run in the Filter Chain?

A Servlet flow can be visualized as follows:

```text
GET /account
     |
     v
DelegatingFilterProxy / FilterChainProxy
     |
     v
Selected SecurityFilterChain
     |
     +-- SecurityContext restored from repository if present
     |
     +-- Authentication filter / RememberMeAuthenticationFilter
     |       -> if full session remains: usually keeps existing Authentication
     |       -> otherwise if remember-me cookie is valid:
     |              creates RememberMeAuthenticationToken
     |
     +-- AnonymousAuthenticationFilter
     |       -> if still no Authentication: creates anonymous token
     |
     +-- ExceptionTranslationFilter
     |
     +-- AuthorizationFilter
             |
             +-- matching request matcher
             +-- AuthorizationManager checks rule
             |
             +-- GRANTED: continue to controller
             +-- DENIED: exception handling/entry point
```

This is a conceptual diagram, not an exhaustive list or guarantee that every version has these exact filters in that order. Other authentication mechanisms such as OAuth2, HTTP Basic, bearer tokens, or custom filters can create different `Authentication` types.

### 4.1. Request Matchers Do Not Select Authentication Mechanisms

`requestMatchers("/account").authenticated()` specifies an **authorization rule** for that URL. It does not automatically enable form login, HTTP Basic, remember-me, or sessions.

To enable mechanisms, configure them separately, e.g., `formLogin(...)` and `rememberMe(...)` in `HttpSecurity`. With multiple `SecurityFilterChain`s, these rules only apply within the chain selected by `FilterChainProxy` according to `securityMatcher` and `@Order`.

### 4.2. Rule Order Matters

In `authorizeHttpRequests`, the order of request matchers determines which rule applies. Only the first matching rule is selected; rules are not automatically ANDed together:

```java
// WRONG for protecting /admin with full authentication:
http.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
    // .requestMatchers("/admin").fullyAuthenticated() must not follow anyRequest
);
```

Replace with the specific rule before the fallback:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin").fullyAuthenticated()
    .anyRequest().authenticated()
);
```

These two snippets **illustrate rule order**; to require both the admin role and full authentication, combine both conditions explicitly rather than assuming two `requestMatchers` on the same URL will both run.

## 5. authenticated(): Accepts Remembered and Full Login

`authenticated()` aims to permit users with a framework-authenticated identity. With standard remember-me:

- Anonymous does not satisfy `authenticated()`.
- A valid `RememberMeAuthenticationToken` can satisfy `authenticated()`.
- A full form-login `Authentication` satisfies `authenticated()`.

Example route for viewing personal info with moderate risk:

```java
.requestMatchers("/account/overview").authenticated()
```

This **does not skip data-ownership checks**. A request from user A must not read account B simply because `authenticated` is true. You must combine resource-level authorization in the application service, tenant data, and appropriate permissions.

### 5.1. authenticated Is Not a Role Check

`authenticated()` does not guarantee `ROLE_ADMIN` or `invoice:read`. A remembered user with `ROLE_READER` may enter `/account/overview`, which does not mean they may read every order.

These are two independent axes:

```text
Authentication trust:   anonymous / remember-me / full
Authorization rights:   ROLE_READER / ROLE_ADMIN / invoice:read / ownership
```

Check both wherever risk warrants; one rule does not replace the other.

## 6. fullyAuthenticated(): When Remember-Me Is Not Enough

`fullyAuthenticated()` requires an authentication not classified by the trust resolver as anonymous or remember-me. Someone restored from a remember-me cookie may need to **log in interactively again** to access a full-only page.

Example:

```java
.requestMatchers("/settings/security").fullyAuthenticated()
```

In form login, a remember-me user blocked from a full route may be routed by `ExceptionTranslationFilter` to the authentication entry point, resulting in a redirect to `/login`. Actual responses depend on chain, entry point, URL, and custom handlers; do not treat 302 as absolute for every application.

### 6.1. Why Not Set fullyAuthenticated for All Routes?

If every route requires full authentication, remember-me loses most of its UX value. Usually only high-risk operations need a high trust level or extra verification. A balanced policy:

| Operation Type | Suggested Minimum Trust Level |
| --- | --- |
| Public help pages | `permitAll` |
| Viewing low-sensitivity personal dashboard | `authenticated` + ownership |
| Viewing verified info, changing email | `fullyAuthenticated` and possibly reauthentication |
| Deleting account, transferring funds, changing MFA | Full + step-up/recent authentication/MFA |
| Administrative endpoints | Admin role + trust policy + business checks |

Do not infer the exact protection level of an application solely from route names. Assess the threat model, how data is exposed, and device/cookie theft risks.

## 7. rememberMe(): Matches Only Remember-Me Authentication

`rememberMe()` is a specialized matcher often used for testing and identifying requests auto-authenticated by cookie. It does not mean "enable the Remember Me feature".

Cases:

```text
Session cookie holds full Authentication -> rememberMe() = false
No full session, valid remember-me cookie
    -> RememberMeAuthenticationToken -> rememberMe() = true
No valid login/cookie -> anonymous -> rememberMe() = false
```

A typical application rarely needs to block full-login users from a page. When you want to allow remembered or full users, **use `authenticated()`**, or an appropriate composite rule instead of `rememberMe()`.

### 7.1. Do Not Use rememberMe as a Substitute for Session Validity

Although a remember-me cookie has a long lifetime, it does not guarantee immutable session or user state. A user may change passwords, get locked, be deleted, or have cookies expire or tokens revoked. Only `RememberMeServices` verifying a valid cookie can create a remember-me `Authentication`.

## 8. anonymous(): Only for Users Not Logged In

`anonymous()` matches anonymous authentication as defined by the framework, not everyone allowed to access.

For example, it can be useful when UX wants to route logged-in users elsewhere:

```java
.requestMatchers("/register-intro").anonymous()
```

However, there are two limitations:

1. Blocking full or remember-me users from an info page does not necessarily carry security value. If content should genuinely be public, choose `permitAll()`.
2. Anonymous policy relies on the trust resolver/anonymous support. A security chain that disables anonymous or uses a custom resolver needs thorough testing.

### 8.1. anonymous Is an Authentication State, Not a Role

An authority named `ROLE_ANONYMOUS` does not automatically turn an arbitrary token into `AnonymousAuthenticationToken`. Likewise, a logged-in user with `ROLE_GUEST` does not automatically satisfy `anonymous()`.

Do not check for anonymous by comparing the username to the fixed string `anonymousUser`; that name can be customized or differ in the active mechanism.

## 9. Why Is hasRole("ADMIN") Not Enough for Sensitive Pages?

An admin user logs in via form and has `ROLE_ADMIN`. After the HTTP session expires, that user's remember-me cookie can still be verified and restore authorities, including `ROLE_ADMIN`.

If you only write:

```java
.requestMatchers("/admin-sensitive").hasRole("ADMIN")
```

this rule **does not enforce fullyAuthenticated**. A remembered admin can enter if they have the right authority and are not blocked by another policy.

A better design combines them:

```text
allow /admin-sensitive
  iff has ROLE_ADMIN
  AND AuthenticationTrustResolver.isFullyAuthenticated(authentication)
  AND other business policy (if any)
```

In the complete code example in section 11 there will be an `AuthorizationManager<RequestAuthorizationContext>` combining **role AND full trust**. That makes the evaluation order explicit and avoids assuming two overlapping request matchers intersect automatically.

### 9.1. Do Not Confuse Request Authorization with Method Authorization

`authorizeHttpRequests` protects requests before they reach the controller. For sensitive domain actions, check permissions at the service/method layer if business logic requires it, e.g., with `@PreAuthorize` when method security is enabled.

An illustrative method expression:

```java
// Illustrative inside a bean with method security enabled, not standalone:
@PreAuthorize("hasRole('ADMIN') and isFullyAuthenticated()")
public void approveSensitiveChange() {
    // Business validation and audit logging at the application layer.
}
```

Requires `@EnableMethodSecurity` and corresponding expression configuration. Do not call this method "already safe" if resource ownership checks, MFA, CSRF, or transactions are missing. Method security also protects calls that do not originate from a specific URL in appropriate architectures.

## 10. HTTP Responses When a Rule Is Not Satisfied

Do not memorize "authenticated fails -> 401" and "fullyAuthenticated fails -> 403". HTTP responses are the outcome of the **authentication entry point**, **access denied handler**, **trust resolver**, and active authentication mechanism.

In a session-based form-login web app:

| State | Blocked Rule | Typical Outcome |
| --- | --- | --- |
| Anonymous | `authenticated()` | 302 redirect to login page |
| Anonymous | `fullyAuthenticated()` | 302 redirect to login |
| Remember-me | `fullyAuthenticated()` | May be routed to login for interactive authentication |
| Remember-me | `anonymous()` | Not allowed; handling may redirect/re-auth depending on entry point |
| Full login | `rememberMe()` | Typically 403, since already authenticated but failed the rule |
| Full login | Missing `ROLE_ADMIN` | Typically 403 |
| Anonymous Basic API | `authenticated()` | Typically 401 + Basic challenge |
| JWT API without bearer token | `authenticated()` | Typically 401 per API entry point |

**302, 401, and 403 are not intrinsic properties of the predicate itself.** If the app has a custom `AuthenticationEntryPoint` returning JSON or a stateless security chain, responses differ from form login.

### 10.1. Why Can Remember-Me Failing Full Redirect Instead of Returning 403?

`ExceptionTranslationFilter` can treat remember-me as insufficient when full authentication is required, invoking the authentication entry point instead of returning a plain forbidden page. That is why a form-login remembered user hitting a sensitive page is usually prompted to log in again.

Do not conclude that a login redirect proves the remember-me cookie is "broken". The cookie may be completely valid, while the trust level is insufficient for the rule.

## 11. Complete Maven Spring Boot 3.3.5 and Java 17 Example

This sample application uses **Spring Security Servlet** with form login, a remember-me cookie, and one `SecurityFilterChain`. It includes two users, reader/admin, and routes clearly demonstrating the four predicates.

**Note:** Passwords and the signing key are only for local study on localhost. In production you must use HTTPS, a secret manager, key rotation, a real user store, safe logging, and token revocation policies.

### 11.1. Directory Structure

```text
http-auth-levels/
  pom.xml
  src/
    main/java/example/authlevel/
      AuthLevelApplication.java
      SecurityConfig.java
      PageController.java
    test/java/example/authlevel/
      AuthLevelsMvcTest.java
```

### 11.2. pom.xml

```xml
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
  <artifactId>http-auth-levels</artifactId>
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
```

### 11.3. Application Entry Point

File `src/main/java/example/authlevel/AuthLevelApplication.java`:

```java
package example.authlevel;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthLevelApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthLevelApplication.class, args);
    }
}
```

### 11.4. SecurityConfig with Route Rules and Role AND Full

File `src/main/java/example/authlevel/SecurityConfig.java`:

```java
package example.authlevel;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    private static AuthorizationManager<RequestAuthorizationContext>
            adminAndFullyAuthenticated() {

        AuthenticationTrustResolver trust =
            new AuthenticationTrustResolverImpl();

        return (authenticationSupplier, requestContext) -> {
            Authentication current = authenticationSupplier.get();

            boolean full = current != null
                && trust.isFullyAuthenticated(current);

            boolean admin = current != null
                && current.getAuthorities().stream().anyMatch(
                    a -> "ROLE_ADMIN".equals(a.getAuthority()));

            return new AuthorizationDecision(full && admin);
        };
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http,
                                    UserDetailsService users)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login", "/error")
                    .permitAll()
                .requestMatchers("/guest").anonymous()
                .requestMatchers("/account").authenticated()
                .requestMatchers("/remember-only").rememberMe()
                .requestMatchers("/settings").fullyAuthenticated()
                .requestMatchers("/admin-role-only").hasRole("ADMIN")
                .requestMatchers("/admin-sensitive")
                    .access(adminAndFullyAuthenticated())
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .rememberMe(me -> me
                .key("training-signing-key-not-for-production")
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(60 * 60 * 24 * 7)
                .userDetailsService(users))
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

**Detailed explanation:**

- `/public` uses `permitAll`; anonymous, remembered, and full users can all enter.
- `/guest` uses `anonymous`; users authenticated by either of the other two ways will not match.
- `/account` uses `authenticated`; valid remembered users are still allowed.
- `/remember-only` uses `rememberMe`; full users are not treated as remember-me.
- `/settings` uses `fullyAuthenticated`; requires full login, not just a remember-me cookie.
- `/admin-role-only` intentionally uses role alone; a remembered admin can access — an example to understand the policy gap if the real endpoint is sensitive.
- `/admin-sensitive` uses a **custom AuthorizationManager** checking both `ROLE_ADMIN` **and** full trust. This illustrates combining conditions properly rather than relying on defining two matchers for the same URL.
- `anyRequest().denyAll()` is a strict fallback for undeclared URLs; adding new routes requires explicitly defining permissions.
- `formLogin` provides interactive login and session handling; `rememberMe` registers cookie-based auto-authentication.
- `logout` is kept at defaults, including form-login logout/CSRF mechanics. Do not disable CSRF just to avoid supplying tokens in tests.

**Important:** the custom `AuthorizationManager` here clarifies the AND technique for the lesson. In large applications, you can use built-in `AuthorizationManager` combinators or appropriate method security. Determine full/recent MFA and ownership requirements at the business layer rather than merely comparing authority strings.

### 11.5. Controller

File `src/main/java/example/authlevel/PageController.java`:

```java
package example.authlevel;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PageController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/guest")
    String guestPage() {
        return "guest";
    }

    @GetMapping("/account")
    String account(Authentication authentication) {
        return "account:" + authentication.getName();
    }

    @GetMapping("/remember-only")
    String rememberOnly(Authentication authentication) {
        return "remember:" + authentication.getName();
    }

    @GetMapping("/settings")
    String settings(Authentication authentication) {
        return "settings:" + authentication.getName();
    }

    @GetMapping("/admin-role-only")
    String adminRoleOnly(Authentication authentication) {
        return "role:" + authentication.getName();
    }

    @GetMapping("/admin-sensitive")
    String adminSensitive(Authentication authentication) {
        return "sensitive:" + authentication.getName();
    }
}
```

The controller does not manually call `if (isRememberMe)` to authorize. `AuthorizationFilter` and `AuthorizationManager` check before the request reaches the handler.

## 12. MockMvc: Verifying via Real Form Login and Remember-Me Cookies

File `src/test/java/example/authlevel/AuthLevelsMvcTest.java`:

```java
package example.authlevel;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthLevelsMvcTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(String username, String password,
                            boolean remember) throws Exception {

        MockHttpServletRequestBuilder request = post("/login")
            .with(csrf())
            .param("username", username)
            .param("password", password);

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    private Cookie rememberCookie(String username, String password)
            throws Exception {
        Cookie cookie = login(username, password, true)
            .getResponse().getCookie("remember-me");
        assertNotNull(cookie);
        return cookie;
    }

    private MockHttpSession fullSession(String username, String password)
            throws Exception {
        MockHttpSession session = (MockHttpSession)
            login(username, password, false)
                .getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void anonymousCanUsePublicAndGuest() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/guest"))
            .andExpect(status().isOk())
            .andExpect(content().string("guest"));
    }

    @Test
    void anonymousIsRedirectedFromAuthenticatedRoute()
            throws Exception {
        MvcResult result = mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertNotNull(result.getResponse().getRedirectedUrl());
        assertTrue(result.getResponse().getRedirectedUrl()
            .contains("/login"));
    }

    @Test
    void anonymousCannotUseRememberOnlyRoute()
            throws Exception {
        MvcResult result = mvc.perform(get("/remember-only"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertTrue(result.getResponse().getRedirectedUrl()
            .contains("/login"));
    }

    @Test
    void fullLoginCanUseAuthenticatedAndFullyAuthenticated()
            throws Exception {
        MockHttpSession session =
            fullSession("reader", "reader-pass");

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("account:reader"));

        mvc.perform(get("/settings").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("settings:reader"));
    }

    @Test
    void fullLoginDoesNotMatchAnonymous()
            throws Exception {
        MockHttpSession session =
            fullSession("reader", "reader-pass");

        mvc.perform(get("/guest").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void fullLoginDoesNotMatchRememberMeOnly()
            throws Exception {
        MockHttpSession session =
            fullSession("reader", "reader-pass");

        mvc.perform(get("/remember-only").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void rememberedUserCanUseAuthenticated()
            throws Exception {
        Cookie cookie = rememberCookie("reader", "reader-pass");

        // Do not send .session(...): test auto-login from cookie.
        mvc.perform(get("/account").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("account:reader"));
    }

    @Test
    void rememberedUserMatchesRememberMeOnly()
            throws Exception {
        Cookie cookie = rememberCookie("reader", "reader-pass");

        mvc.perform(get("/remember-only").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("remember:reader"));
    }

    @Test
    void rememberedUserMustReauthenticateForSettings()
            throws Exception {
        Cookie cookie = rememberCookie("reader", "reader-pass");

        MvcResult result = mvc.perform(get("/settings")
                .cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertNotNull(result.getResponse().getRedirectedUrl());
        assertTrue(result.getResponse().getRedirectedUrl()
            .contains("/login"));
    }

    @Test
    void rememberedUserIsNotAnonymous()
            throws Exception {
        Cookie cookie = rememberCookie("reader", "reader-pass");
        int status = mvc.perform(get("/guest").cookie(cookie))
            .andReturn().getResponse().getStatus();

        assertNotEquals(200, status);
    }

    @Test
    void adminRoleAloneCanBeSatisfiedByRememberMe()
            throws Exception {
        Cookie cookie = rememberCookie("admin", "admin-pass");

        mvc.perform(get("/admin-role-only").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("role:admin"));
    }

    @Test
    void adminSensitiveRequiresAdminAndFull()
            throws Exception {
        Cookie cookie = rememberCookie("admin", "admin-pass");

        int status = mvc.perform(get("/admin-sensitive")
                .cookie(cookie))
            .andReturn().getResponse().getStatus();
        assertNotEquals(200, status);

        MockHttpSession admin =
            fullSession("admin", "admin-pass");

        mvc.perform(get("/admin-sensitive").session(admin))
            .andExpect(status().isOk())
            .andExpect(content().string("sensitive:admin"));

        MockHttpSession reader =
            fullSession("reader", "reader-pass");

        mvc.perform(get("/admin-sensitive").session(reader))
            .andExpect(status().isForbidden());
    }
}
```

### 12.1. Do These Tests Actually Verify Remember-Me?

Yes: the `rememberCookie(...)` helper POSTs `/login` with the `remember-me` parameter and extracts the cookie issued by the framework. The subsequent test request **sends only the cookie**, without sending the session used during login, so the remember-me filter must re-authenticate the cookie for the request to proceed.

This is a more realistic check than `.with(user("reader"))` — that post-processor constructs a pre-built test principal, bypassing cookie authentication and failing to prove that `RememberMeServices` actually works.

### 12.2. Why Do Some Tests Not Assert Strictly 403?

When a remember-me token is rejected on a route requiring full authentication, `ExceptionTranslationFilter` may send the user back to login (302) instead of 403. For `anonymous()` from a remembered user or a custom manager, the entry point policy may change how the response is rendered.

Therefore some tests only assert **not 200** when the goal is proving the rule denies access, whereas full-login denials in a known web config assert 403. In real deployments, add exact assertions matching your defined entry point.

### 12.3. Trust Level and Role Must Be Tested Together

`adminSensitiveRequiresAdminAndFull` has three cases:

1. Remembered admin: right role, insufficient trust -> not permitted.
2. Full admin: both role and trust satisfied -> 200.
3. Full reader: right trust, missing role -> 403.

This is a fault-catching matrix that a single "admin can log in" test misses.

## 13. Running and What Can Be Concluded

From the `http-auth-levels` directory with JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

**Twelve tests are expected to pass** when dependencies and configuration are correct. This is an expectation from the source code, not a report of an executed Maven run; build times/logs may vary by machine.

You can use a browser to open `http://localhost:8080/account` and log in. If remember-me is checked, once the old login session is gone while the remember-me cookie remains valid, `/account` can still open whereas `/settings` requires interactive login. When using browser developer tools, **never expose the `remember-me` or `JSESSIONID` cookie values**.

Observable results per rule:

| Action | Result with Sample Config |
| --- | --- |
| Anonymous GET `/public` | 200 `public` |
| Anonymous GET `/guest` | 200 `guest` |
| Anonymous GET `/account` | Redirect to login |
| Full reader GET `/account` | 200 `account:reader` |
| Full reader GET `/settings` | 200 `settings:reader` |
| Full reader GET `/remember-only` | 403 |
| Remembered reader GET `/account` | 200 `account:reader` |
| Remembered reader GET `/remember-only` | 200 `remember:reader` |
| Remembered reader GET `/settings` | Redirect to login |
| Remembered admin GET `/admin-role-only` | 200 `role:admin` |
| Remembered admin GET `/admin-sensitive` | Denied, requires appropriate trust |
| Full admin GET `/admin-sensitive` | 200 `sensitive:admin` |
| Full reader GET `/admin-sensitive` | 403 |

Do not assume "cookie present" means "cookie valid": the remember-me service must verify the signature/expiration or corresponding repository before creating an `Authentication`.

## 14. Standalone Java 17: Reasoning with a Predicate Table

To self-check the logic before writing Spring Security configuration, you can model the three states with an enum. **The code below is not an `AuthenticationTrustResolver` implementation**; it merely represents the truth table of the standard tokens in the example.

Create `HttpTrustRulesDemo.java`:

```java
public class HttpTrustRulesDemo {
    enum Kind {
        ANONYMOUS, REMEMBER_ME, FULL
    }

    static boolean authenticated(Kind kind) {
        return kind != Kind.ANONYMOUS;
    }

    static boolean fullyAuthenticated(Kind kind) {
        return kind == Kind.FULL;
    }

    static boolean rememberMe(Kind kind) {
        return kind == Kind.REMEMBER_ME;
    }

    static boolean anonymous(Kind kind) {
        return kind == Kind.ANONYMOUS;
    }

    static void print(Kind kind) {
        System.out.printf(
            "%s: authenticated=%b full=%b rememberMe=%b anonymous=%b%n",
            kind,
            authenticated(kind),
            fullyAuthenticated(kind),
            rememberMe(kind),
            anonymous(kind)
        );
    }

    public static void main(String[] args) {
        for (Kind kind : Kind.values()) {
            print(kind);
        }
    }
}
```

Compile and run:

```bash
javac HttpTrustRulesDemo.java
java HttpTrustRulesDemo
```

**Exact** stdout with Java 17:

```text
ANONYMOUS: authenticated=false full=false rememberMe=false anonymous=true
REMEMBER_ME: authenticated=true full=false rememberMe=true anonymous=false
FULL: authenticated=true full=true rememberMe=false anonymous=false
```

The Java enum here has no `SecurityContextHolder`, tokens, or servlets. Use it to reason, then verify real HTTP behavior with MockMvc as in section 12.

## 15. Remember-Me Security and Sensitive Access

### 15.1. A Remember-Me Cookie Is a Credential

A remember-me token can live longer than an HTTP session. If an attacker steals a still-valid cookie, they can be recognized as that user at the remember-me level. Therefore:

- Use HTTPS, appropriate cookie flags, and careful domain/path settings.
- Never put tokens/cookies in URLs, logs, metric labels, or screenshots.
- Enforce expiration policies and provide an option to disable remember-me, especially on shared machines.
- When the app requires per-device token revocation, consider a persistent-token design and state repository.
- With purely signed token-based cookies, deleting the cookie in the browser does not invalidate a stolen copy of the cookie.
- Changing a password or locking an account does not automatically invalidate every active session by default; a corresponding revocation workflow is required.

### 15.2. Logout Must Consider Both Session and Remember-Me

Form logout typically clears `SecurityContext`/invalidates the session and invokes the remember-me logout handler to delete the browser cookie. However, logging out on one device does not necessarily revoke sessions/remember-me tokens on all devices. If "logout everywhere" is needed, manage the session store/registry and token repository per explicit policy.

### 15.3. CSRF and Full Authentication Are Two Different Layers

Cookie-authenticated requests — including remember-me — can have credentials automatically attached by the browser. For endpoints with side effects such as state-changing POSTs, proper CSRF protection is needed. `fullyAuthenticated()` does not protect against CSRF; a full-login user can still suffer CSRF if controls are missing.

**Never use GET for state-changing actions** simply because the route is protected by full authentication. Respect HTTP semantics, CSRF, idempotency, validation, and business-level authorization.

## 16. Common Mistakes When Writing HTTP Authorization Rules

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Relying solely on `Authentication.isAuthenticated()` | Anonymous token can trick code into thinking user is logged in | Use `authenticated()`/trust resolver |
| Thinking `authenticated()` excludes remember-me | Remember-me cookie can still enter the route | Use `fullyAuthenticated()` when higher trust is needed |
| Thinking `fullyAuthenticated()` proves MFA | Wrong policy for sensitive actions | Add step-up/MFA and recent-auth checks |
| Thinking `rememberMe()` allows full login | Full token is not classified as remember-me | Use `authenticated()` if you want both |
| Using `anonymous()` for public pages | Logged-in users are denied | Use `permitAll()` |
| Thinking `hasRole("ADMIN")` automatically requires full | Remembered admin may still hold the role | Combine role AND full trust |
| Defining two rules for the same URL expecting automatic AND | The first matching rule is used | Use a single combined `AuthorizationManager` |
| Placing `anyRequest` before specific matchers | Specific policy lost or configuration error | Place specific matchers before fallback |
| Adding only a `rememberMe()` rule without enabling `http.rememberMe` | No cookie authentication happens | Configure mechanism and authorization separately |
| Assuming every denial of `fullyAuthenticated` returns 403 | Remembered browser user may be redirected to login | Test entry point, denied handler, and auth type |
| Testing with `.with(user("reader"))` and claiming remember-me works | Bypasses actual cookie authentication | Test real POST login, extract cookie, send request without session |
| Hardcoding token signing key in production | Key leak increases cookie forgery risk | Secret manager, rotation, and node management |
| Accessing entities just because user is authenticated | Can expose another user's resources | Check ownership, tenant, and domain policy |
| Disabling CSRF because `fullyAuthenticated` is required | Fails to block forged browser requests | Keep appropriate CSRF protection |
| Only deleting cookies to revoke stolen token-based cookies | Stolen copy may remain valid | Design real revocation |
| Not testing request matcher order | Endpoint gets hit by a broader rule | Test overlapping URLs and deny fallback |
| Sharing assumptions between form login and JWT APIs | Unexpected 302/401/403 responses | Check the actual security chain/entry point |

## 17. Debugging Flow for an Unexpected Request Outcome

1. **Which SecurityFilterChain did the request enter?** Check `securityMatcher`, `@Order`, and the filter chain actually selected.
2. **Where did Authentication come from?** Session, form login, remember-me cookie, HTTP Basic, bearer token, or custom provider?
3. **Was Authentication already present before RememberMeAuthenticationFilter?** An existing full session usually means the remember-me filter does not need to `autoLogin`.
4. **What is the token class?** `AnonymousAuthenticationToken`, `RememberMeAuthenticationToken`, or another `Authentication`?
5. **How does the trust resolver classify it?** `anonymous`, `rememberMe`, `authenticated`, and `fullyAuthenticated` are the core conditions in this lesson.
6. **Which HTTP rule matched first?** Is there a broad `requestMatchers` or misplaced `anyRequest`?
7. **Does the route require both role and trust, or only one?** For admins, do not look only at `ROLE_ADMIN`.
8. **Which handler generated the response?** Entry point login redirect, Basic 401 challenge, or `AccessDeniedHandler` 403?
9. **Is the cookie valid?** Expiration, signature/key, user store, token repository, path/domain, Secure/SameSite, and environment.
10. **Was a session sent with the test request?** If a full session was sent accidentally, you are no longer testing remember-me.
11. **Did CSRF block the POST?** Do not confuse a 403 from CSRF with a `fullyAuthenticated` failure.
12. **Did a method/business policy block afterwards?** A granted HTTP rule does not guarantee controller/service access.
13. **Custom AuthenticationTrustResolver?** If present, test classification for custom tokens/principals.
14. **Are there secondary token mechanisms?** Logging out a session does not automatically revoke remember-me or independent access tokens.

You can enable diagnostic logging in development:

```properties
logging.level.org.springframework.security=DEBUG
```

Never write raw tokens, passwords, remember-me cookies, session IDs, or full `Authorization` headers into logs.

## 18. Review Questions with Answers

**Question 1.** A user is not logged in, yet `AnonymousAuthenticationFilter` placed an `AnonymousAuthenticationToken`. `Authentication.isAuthenticated()` may be true; does `authenticated()` let them into `/account`?

**Answer:** No, under the normal trust resolver/authorization. The `authenticated()` predicate distinguishes anonymous users rather than relying solely on the token flag.

**Question 2.** A user logs in via form, the session expires, yet the remember-me cookie is still valid. `/account` uses `authenticated()`, `/settings` uses `fullyAuthenticated()`. Outcome?

**Answer:** `/account` can be permitted if `autoLogin` creates a valid `RememberMeAuthenticationToken`. `/settings` is not permitted by remember-me alone and may route the user to login to upgrade authentication.

**Question 3.** Is a full-login user allowed into `/remember-only`?

**Answer:** No, if the rule is strictly `rememberMe()`. A full token is not classified as remember-me by the resolver.

**Question 4.** If `/info` must be public for both guests and members, should you use `anonymous()` or `permitAll()`?

**Answer:** `permitAll()`. `anonymous()` excludes authenticated/remembered users.

**Question 5.** A remembered admin has `ROLE_ADMIN`, and `/admin` only has `hasRole("ADMIN")`. Can they enter?

**Answer:** Yes, because the role rule does not automatically enforce `fullyAuthenticated`. For sensitive endpoints, combine authority AND trust/full/step-up per policy.

**Question 6.** Does placing `.requestMatchers("/settings").authenticated()` followed by `.requestMatchers("/settings").fullyAuthenticated()` ensure both run?

**Answer:** No. The first matching matcher is used. Use one rule meeting the requirement or combine via an `AuthorizationManager`.

**Question 7.** Does `fullyAuthenticated()` automatically verify that the user entered an OTP 5 minutes ago?

**Answer:** No. It stores no evidence of MFA or step-up timestamp.

**Question 8.** A test uses `.with(user("reader"))` against `/account` and claims the remember-me cookie works well; is that convincing?

**Answer:** No. That post-processor supplies a test principal, bypassing cookie mechanics. You must perform a real login, extract the remember-me cookie, and send a new request without a session.

**Question 9.** A remembered request to `/settings` is redirected to `/login`. Does that prove the cookie failed?

**Answer:** No. The cookie may be valid while its trust level does not meet `fullyAuthenticated()`.

**Question 10.** After logout deletes the remember-me cookie in the browser, is a stolen copy of a token-based cookie guaranteed to be revoked?

**Answer:** No, unless there is a server-side revocation mechanism or the data used to verify the token has changed. Proper revocation must be designed.

## 19. Pre-Deployment Application Checklist

**Choosing rules by requirement:**

- Page needed by everyone to read? Use `permitAll`.
- Page only for unauthenticated users? Use `anonymous` if UX requires it.
- Accept both remembered and full? Use `authenticated`.
- Accept strictly remember-me requests? Use `rememberMe` (rare as a product requirement).
- Need full interactive login? Use `fullyAuthenticated`; add MFA/recent authentication if sensitive.
- Need role/authority/ownership? Combine explicitly; do not infer from trust level.

**Testing:**

- Anonymous, remembered, and full all have tests.
- Verify a full token does not satisfy `rememberMe` and a remembered token does not satisfy `fullyAuthenticated`.
- Include tests with right role/insufficient trust and right trust/missing role.
- Test distinguishing form redirects and API entry points.
- Test the remember-me cookie via a request **without sending the old session**.
- Protect side-effecting requests with CSRF and do not log secrets.

**Operations:**

- Protect the remember-me cookie like a credential.
- Consider TTL, rotation, revocation, multi-device, and logout-all.
- Ensure controller/service permission policies align with the security chain.
- Do not confuse full authentication with proof of MFA or authentication recency.

## 20. Key Takeaways

- `authenticated()` accepts **remember-me or full**, not anonymous.
- `fullyAuthenticated()` accepts only authentication considered **full** by the trust resolver, excluding remember-me and anonymous.
- `rememberMe()` accepts only **remember-me** state; full login does not satisfy this matcher.
- `anonymous()` is only for **anonymous**; public pages for everyone must use `permitAll()`.
- `AuthenticationTrustResolver` classifies tokens; never rely solely on `Authentication.isAuthenticated()` to infer a real logged-in user.
- `hasRole`/`hasAuthority` checks permissions, not full trust. For sensitive routes, combine conditions in **one** `AuthorizationManager` or appropriate method security.
- HTTP rules run inside the **selected SecurityFilterChain**, and specific matchers must come before the fallback. Do not confuse `requestMatchers` with `securityMatcher`.
- Test with a remember-me cookie issued by a real login, **without sending the session**, to accurately verify the difference between remembered and full authentication.
