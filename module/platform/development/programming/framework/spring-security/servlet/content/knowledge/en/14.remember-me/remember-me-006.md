# Remember-me, Anonymous, and fullyAuthenticated in Authorization Decisions (Spring Security Servlet)

## 1. Why Is “Authenticated” Still Not Necessarily Enough Permission?

In a Spring Security Servlet application, a user can hold an `Authentication` at different levels of trust:

- **Anonymous**: not logged in by normal means, yet the framework may construct an `AnonymousAuthenticationToken` to represent an anonymous identity during the request.
- **Remember-me**: the browser holds a valid remember-me cookie; when the interactive login session is gone, Spring Security can auto-authenticate and create a `RememberMeAuthenticationToken`.
- **Fully authenticated**: the user authenticated through a mechanism considered complete by `AuthenticationTrustResolver`, such as form login with username/password, **not solely via remember-me**.

These three states directly govern whether a path is permitted by:

```java
.requestMatchers("/account").authenticated()
.requestMatchers("/sensitive").fullyAuthenticated()
.requestMatchers("/guest").anonymous()
.requestMatchers("/remembered").rememberMe()
```

These are **configuration fragments** inside `authorizeHttpRequests`, not a standalone Java program.

**Key takeaways:**

1. `authenticated()` typically accepts both interactively logged-in users and users authenticated via remember-me; it excludes anonymous.
2. `fullyAuthenticated()` accepts “full” authentication yet **excludes remember-me and anonymous**.
3. `rememberMe()` requires an identity classified as remember-me; normal interactive logins **do not automatically satisfy** this specialized matcher.
4. `anonymous()` accepts only anonymous; it is not the same as `permitAll()`.
5. `hasRole("ADMIN")` checks authority only. **It does not implicitly require `fullyAuthenticated`**. For sensitive actions, evaluate authentication trust as well.

This lesson explains the mechanics, security boundaries, authorization policies, and practical testing—without conflating “remember-me” with normal session storage.

## 2. Distinguishing Authentication, Session, and Remember-me Cookie

`Authentication` is the object Spring Security uses to represent the principal, authorities, and authentication status of a request. In a form-login system, after login succeeds, `Authentication` is typically saved in `SecurityContext`; the context can be retained in `HttpSession` via `SecurityContextRepository`.

**Remember-me** is a separate mechanism: the browser can retain a cookie longer than the session. When the browser returns without a session holding an authentication, `RememberMeAuthenticationFilter` can call `RememberMeServices.autoLogin(...)` to verify the cookie and set a remember-me authentication.

```text
Browser
    |
    +-- HTTP session still holds SecurityContext?
    |      |
    |      +-- Yes: use restored Authentication
    |      |        (usually full after form login)
    |      |
    |      +-- No: evaluate remember-me mechanism (if enabled)
    |                 |
    |                 +-- Valid remember-me cookie:
    |                 |      RememberMeAuthenticationToken
    |                 |
    |                 +-- Absent/invalid:
    |                        anonymous (if anonymous is enabled)
    |
    v
AuthorizationFilter
    |
    +-- authenticated / fullyAuthenticated / anonymous / rememberMe
    +-- hasRole / hasAuthority / other authorization policies
    |
    v
Controller or rejection/challenge/redirect response
```

This diagram is a **conceptual model**: exact filter timing, repository load/save behavior, and success/failure handling depend on the security chain and version. There is no guarantee every request carrying a remember-me cookie restores as remember-me: if another authentication is already present, remember-me auto-login normally does not overwrite it.

### 2.1. Session Cookies and Remember-me Cookies Differ

| Property | Session cookie (usually `JSESSIONID`) | Remember-me cookie (usually `remember-me`) |
| --- | --- | --- |
| Purpose | Links the request to a server-side `HttpSession` | Enables automatic re-authentication when login session is absent |
| Contains raw password? | Should not | Should not |
| Is it an `Authentication`? | No | No |
| Lifetime | Governed by session/cookie/container | Governed by remember-me config and token type |
| When created? | Can be before or after login | Usually upon successful login when user opts in |
| Request permissions | Based on `SecurityContext` and policy | Once validated, produces remember-me Authentication, still subject to authorization |
| Logout | Usually invalidates session | Usually requires clearing cookie; server-side revocation depends on remember-me type |

A remember-me cookie is a valuable credential. **Never treat it as a “harmless convenience cookie”**: if stolen, it can be replayed until expiration or invalidation depending on design.

### 2.2. AnonymousAuthenticationToken Does Not Mean Logged In

Spring Security may place an `AnonymousAuthenticationToken` in `SecurityContextHolder` for an unauthenticated request. This token lets code deal consistently with an authentication object, yet it does not represent a verified user.

Notably, `AnonymousAuthenticationToken.isAuthenticated()` can return `true` per the token API, so **never rely solely on the `Authentication.isAuthenticated()` flag** to infer “a real user is logged in”. Spring Security's authorization managers use `AuthenticationTrustResolver` to tell them apart.

If an application disables anonymous authentication or uses custom mechanisms, observed behavior may differ. Do not hardcode an assumption that every unauthenticated request always carries an `AnonymousAuthenticationToken`.

## 3. AuthenticationTrustResolver and Trust Levels

`AuthenticationTrustResolver` (typically `AuthenticationTrustResolverImpl`) provides authentication classification checks. Key methods in Spring Security 6 include:

```java
boolean isAnonymous(Authentication authentication);
boolean isRememberMe(Authentication authentication);
boolean isAuthenticated(Authentication authentication);
boolean isFullyAuthenticated(Authentication authentication);
```

These are **conceptual interface signatures**, not a complete definition to copy in place of the library.

With standard tokens:

- `AnonymousAuthenticationToken` → anonymous.
- `RememberMeAuthenticationToken` → remember-me.
- A `UsernamePasswordAuthenticationToken` authenticated via form login → treated as fully authenticated, provided no resolver classifies it as anonymous/remember-me.

An easy mental comparison:

```text
isAuthenticated(authentication)
    ~ authentication exists, isAuthenticated() true, NOT anonymous

isFullyAuthenticated(authentication)
    ~ authenticated, NOT remember-me
```

The `~` symbol represents **conceptual logic**, not exact source code across every version or custom resolver. The framework itself is the final authority when `AuthorizationManager` implementations evaluate rules.

### 3.1. “Fully Authenticated” Does Not Mean MFA

Spring Security uses “fully” in the trust-resolver context to **distinguish remember-me from other authentication**. It does not automatically prove:

- the user completed MFA;
- the user re-entered their password within 5 minutes;
- the device is not stolen;
- the current session has not been hijacked;
- authorities inside `Authentication` are still synchronized with the database;
- the request passed “step-up authentication” for a sensitive transaction.

If business logic requires MFA or recent re-authentication before changing an email, transferring funds, or viewing sensitive data, you must enforce **additional policies on authentication recency and factors**, not merely call `fullyAuthenticated()`.

### 3.2. Trust Resolver Does Not Decide All Authorization Alone

Expressions like `authenticated`, `fullyAuthenticated`, `rememberMe`, and `anonymous` are one part of a policy. The final decision may also depend on:

- authority/role;
- resource ownership, tenant, and account state;
- method security or business service policies;
- CSRF validation;
- matching filter chain;
- session/token validity;
- MFA requirements and risk conditions.

Do not treat “`fullyAuthenticated` returned true” as blanket permission to access every resource.

## 4. Decision Matrix: Anonymous, Remember-me, and Full Login

Assume a standard web security chain with Spring Security anonymous + form login + remember-me:

| Authorization rule | Anonymous | Valid remember-me | Full form login |
| --- | --- | --- | --- |
| `permitAll()` | Allowed | Allowed | Allowed |
| `denyAll()` | Denied | Denied | Denied |
| `anonymous()` | Allowed | Denied | Denied |
| `rememberMe()` | Denied | Allowed | Denied |
| `authenticated()` | Denied | Allowed | Allowed |
| `fullyAuthenticated()` | Denied | Denied | Allowed |
| `hasRole("READER")` | Usually lacks this role | Allowed if remembered principal holds `ROLE_READER` | Allowed if full principal holds `ROLE_READER` |

This table describes the **rule-level decision**. The final HTTP response (401, 302 redirect, or 403) depends on the authentication entry point, access denied handler, and current authentication type. With form login:

- Anonymous accessing `/account` requiring authentication → typically redirects to `/login` (302).
- Remember-me accessing `/sensitive` requiring fully authenticated → can be prompted to re-authenticate via the entry point to upgrade trust level.
- Full-login user accessing a `rememberMe()`-only route → denied by rule, despite having stronger authentication.

The last case can feel counterintuitive: `rememberMe()` does not mean “at least remember-me level”. It is an **exact classification check**. If the intent is “accept both remembered and full”, choose `authenticated()` instead of `rememberMe()`.

### 4.1. Choosing the Right Rule for Product Requirements

| Requirement | Suitable rule |
| --- | --- |
| Landing page, help, public home | `permitAll()` |
| Only unauthenticated visitors view an onboarding start page | `anonymous()`, if the product genuinely wants to block authenticated users |
| Personal account page requiring a recognized identity; remember-me acceptable | `authenticated()` plus data ownership checks |
| “Auto-authenticated by cookie” page for testing/demonstration | `rememberMe()` |
| Change password or confirm sensitive operation | At least `fullyAuthenticated()`, and possibly recent re-authentication/MFA |
| View administrative data | `hasRole("ADMIN")` **and** an appropriate trust-level policy if sensitive |
| Lock down an endpoint completely | `denyAll()` |

Authentication condition and authority condition are **two orthogonal axes**. An admin restored via remember-me may still carry `ROLE_ADMIN` in authorities. If an admin endpoint checks only `hasRole("ADMIN")`, do not assume that rule requires full login.

## 5. RememberMeServices Mechanism in Servlet

Spring Security Servlet typically uses these components:

| Component | Responsibility |
| --- | --- |
| `RememberMeServices` | Contract for auto-login, login success, and login failure |
| `RememberMeAuthenticationFilter` | When no suitable Authentication exists yet, tries auto-login from cookie |
| `TokenBasedRememberMeServices` | Remember-me backed by signature-protected tokens, without requiring per-device token storage in a DB |
| `PersistentTokenBasedRememberMeServices` | Remember-me backed by a token series stored on the server for long-lived token management |
| `PersistentTokenRepository` | Interface to save/read/update/delete persistent login tokens |
| `JdbcTokenRepositoryImpl` | A JDBC implementation requiring a matching schema |
| `RememberMeAuthenticationToken` | Authentication produced when remember-me auto-login succeeds |
| `UserDetailsService` | Looks up the user and account data when the remember-me service validates |

A typical flow:

```text
[1] Browser POST /login
    username/password + CSRF token + remember-me checkbox
       |
       +-- Wrong credentials:
       |      RememberMeServices.loginFail(...)
       |      (may delete old remember-me cookie)
       |
       +-- Valid credentials:
              RememberMeServices.loginSuccess(...)
              may send Set-Cookie: remember-me=...
              Authentication from form login is full

[2] Login session lost/not sent
    Browser GET /account
    Cookie: remember-me=...
       |
       v
    RememberMeAuthenticationFilter
       |
       v
    RememberMeServices.autoLogin(...)
       |
       +-- invalid: no remembered Authentication created
       |
       +-- valid: RememberMeAuthenticationToken
                      |
                      v
               AuthorizationFilter
               authenticated() can allow
               fullyAuthenticated() will not allow
```

**Not every remember-me cookie qualifies**: it must be unexpired, validly signed or matching a persistent token, and the user must still be valid per service and policy checks. If an account is locked or password changed, behavior depends on service/algorithm/configuration.

### 5.1. Cookie Is Set When the User Opts Into Remember-me

With standard form login, the request carries the configured `remember-me` parameter; when the checkbox is ticked and login succeeds, the remember-me service can emit a remember-me cookie.

HTML form snippet (illustrating only part of a form):

```html
<label>
  <input type="checkbox" name="remember-me" value="on">
  Remember me
</label>
```

This is **not a complete login form**: it still needs username, password, CSRF token, action, and method. The runnable example in Section 9 uses the default login page generated by Spring Security, and tests submit the `remember-me` parameter via MockMvc.

Do not enable remember-me by default for all users without explaining the risk on shared devices.

### 5.2. No Session Does Not Mean No Authentication

A browser that lost its login session can still send a remember-me cookie. The system can automatically construct a `RememberMeAuthenticationToken` and satisfy `authenticated()`. This matches the design of remember-me; if a sensitive area must not be restored via cookie, enforce `fullyAuthenticated()` or step-up.

Conversely, if a session remains and holds a full Authentication, the browser also sending a remember-me cookie normally does not downgrade full Authentication to remember-me. **Prioritizing the existing authentication path** matters greatly when writing tests.

## 6. How Do Token-Based and Persistent Remember-me Differ?

### 6.1. TokenBasedRememberMeServices

Token-based remember-me typically signs data relating to username, expiration, verification data, and the application's secret key. Depending on the Spring Security version, the format may include an algorithm identifier and other fields. Never depend on a specific cookie string layout in application code.

Pros:

- Does not require a database table for every remember-me token.
- Easy to demonstrate and deploy with minimal components.
- Cookies expire per policy and can become invalid when verification inputs—such as the password hash—change.

Cons to be aware of:

- If someone **already copied a valid cookie**, merely deleting the cookie in the browser on logout **does not create a revocation mechanism for the stolen copy**.
- Revoking all tokens may require rotating the secret key, changing verification data, or another strategy; key rotation can impact many users.
- Difficult to manage individual devices/tokens without server-side state.

**Never claim token-based remember-me logout revoked every copy of the cookie across the network.**

### 6.2. PersistentTokenBasedRememberMeServices

The persistent-token implementation uses a server store to persist token series, typically using **series** and **token** concepts. On successful auto-login, the token can be rotated. Misuse of a token series can indicate theft or a conflict.

Useful capabilities:

- Manage tokens per user/series on the backend.
- Delete tokens server-side to invalidate future remember-me logins.
- Build “log out all devices” features when mapping and policies are complete.

However, it requires:

- Proper schema/persistence, such as `persistent_logins` with the default JDBC implementation.
- Concurrency handling (two simultaneous requests with the same cookie can race on token rotation).
- Transactions, consistency, auditing, TTL cleanup, and distinguishing token theft from race conditions.
- Data protection policies for the token store.
- Separate revocation of active sessions if “log out everywhere” is required, because deleting persistent tokens does not automatically destroy already-authenticated sessions.

### 6.3. Strategy Comparison

| Criterion | Token-based | Persistent-token |
| --- | --- | --- |
| Per-device token stored in DB | Not required | Yes |
| Server-side per-token revocation | Not by default with pure stateless tokens | Can be implemented by deleting/updating the token repository |
| Detect anomalous token use | Limited if relying on signature alone | Can detect misuse via series/token matching |
| Operational cost | Less state | Requires storage, transactions, and cleanup |
| Logout clears browser cookie | Yes | Yes |
| Multi-device management | Harder | More flexible with proper mapping design |
| Authentication level after auto-login | Remember-me | Remember-me |

Both produce **remember-me** authentication, never upgrading automatically into full login after the original session disappears.

## 7. Are Anonymous, Remembered, and Fully Authenticated a Permission Ladder?

You can visualize **trust levels** in order:

```text
Anonymous
   |
   | login / valid cookie
   v
Remember-me
   |
   | user re-authenticates interactively (e.g., form login)
   v
Fully authenticated
```

Yet this diagram **does not** mean that being on a higher rung makes every lower-rung predicate true:

- `authenticated()` is true for remember-me and full.
- `fullyAuthenticated()` is true only for full.
- `rememberMe()` is normally true only for remember-me, not for full.
- `anonymous()` is true only for anonymous, not for remembered or full.
- `permitAll()` ignores all of those states.

This is why you must separate two ideas: **business trust level** and **exact framework predicate**.

### 7.1. Some Surprising but Logical Cases

**Case A:** A user visits an anonymous-only `/guest` page after logging in fully. They are denied despite having stronger authentication. That is the exact intended behavior of `anonymous()`. If the page should be visible to everyone, use `permitAll()`.

**Case B:** A remembered user can open `/account`, yet opening `/sensitive` prompts for interactive authentication. That is the goal of separating `authenticated` and `fullyAuthenticated`.

**Case C:** A full-login user opens `/remembered` and is denied, because the endpoint is restricted specifically to remembered users. In real products, a remember-me-only route is rarely needed; it is mainly useful for testing or clear UX demonstrations.

**Case D:** A remembered user with `ROLE_READER` opens `/reader`. If the rule is only `hasRole("READER")`, the request can be permitted. To enforce full login on sensitive areas, the policy must combine full authentication with the role check rather than guessing permissions from role names.

## 8. Combining Authentication Strength and Business Permissions

One way to model the boundary:

```text
Decision = identity/trust conditions
         + authorities/roles
         + resource ownership/tenant
         + session/token/account state
         + step-up / recent MFA if needed
```

This is a mental model, not an equation Spring Security evaluates with addition. Conditions can be combined using Spring Security `AuthorizationManager`, method security, or business checks in services.

### 8.1. hasRole Does Not Automatically Require Full

Example:

```java
// Rule fragment — checks authority only:
.requestMatchers("/admin").hasRole("ADMIN")
```

If a remembered Authentication carries `ROLE_ADMIN`, this rule alone does not force the user to re-enter a password. When an admin route is sensitive, design **role AND fully authenticated**, for instance via a combined authorization manager or expressive method security, and test the remembered path.

Do not resort to swapping a remembered user's role to `ROLE_GUEST` to block resources if that breaks real policy controls. Keep authorities reflective of the domain, and apply authentication trust where needed.

### 8.2. FullyAuthenticated Still Does Not Replace Step-Up MFA

Even when `fullyAuthenticated()` is true, the account may have logged in long ago. A funds transfer or security-settings change may require a fresh authentication, an MFA challenge, transaction confirmation, or risk evaluation.

Those requirements need dedicated evidence and timestamps/factors. Never infer from `UsernamePasswordAuthenticationToken` alone that the user just typed a password.

### 8.3. Privacy and Remember-me on Public Machines

If a user enables remember-me on a shared device, another person can open the site after the old browser session disappears and still be restored as the remembered user. Restricting low-risk pages to remembered level and requiring step-up for sensitive data therefore creates a useful boundary.

You cannot reliably classify every page as “safe” or “sensitive” from URLs alone; use a concrete product threat model and enforce resource ownership at the service layer.

## 9. Spring Boot 3.3.5 / Java 17 Example: Four Authorization States

This hands-on project uses the **Servlet stack**, Maven, JDK 17, and Spring Security. Endpoints:

| Route | Policy | With anonymous | With remembered | With full login |
| --- | --- | --- | --- | --- |
| `GET /public` | `permitAll` | 200 | 200 | 200 |
| `GET /guest` | `anonymous` | 200 | Not allowed | Not allowed |
| `GET /account` | `authenticated` | Redirect login | 200 | 200 |
| `GET /remembered` | `rememberMe` | Not allowed | 200 | Not allowed |
| `GET /sensitive` | `fullyAuthenticated` | Redirect login | Requires interactive login | 200 |
| `GET /reader` | `hasRole("READER")` | Not allowed | Possible 200 if holding authority | Possible 200 if holding authority |

These are **expectations for the specific configuration**; the exact HTTP status on denial depends on the entry point and access denied handler, so the table uses “Not allowed” where appropriate.

### 9.1. Project Structure

```text
remember-me-auth-levels/
  pom.xml
  src/
    main/java/demo/remember/
      RememberMeDemoApplication.java
      SecurityConfig.java
      DemoController.java
    test/java/demo/remember/
      RememberMeAuthorizationTest.java
```

### 9.2. pom.xml

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
    <groupId>demo</groupId>
    <artifactId>remember-me-auth-levels</artifactId>
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

### 9.3. Startup Class

File `src/main/java/demo/remember/RememberMeDemoApplication.java`:

```java
package demo.remember;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberMeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberMeDemoApplication.class, args);
    }
}
```

### 9.4. SecurityConfig: Remember-me and Distinct Rules

File `src/main/java/demo/remember/SecurityConfig.java`:

```java
package demo.remember;

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
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("training-pass"))
            .roles("READER")
            .build();

        return new InMemoryUserDetailsManager(reader);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login", "/error").permitAll()
                .requestMatchers("/guest").anonymous()
                .requestMatchers("/account").authenticated()
                .requestMatchers("/remembered").rememberMe()
                .requestMatchers("/sensitive").fullyAuthenticated()
                .requestMatchers("/reader").hasRole("READER")
                .anyRequest().authenticated())
            .formLogin(form -> form.permitAll())
            .rememberMe(remember -> remember
                // Fixed secret ONLY for demo; production uses a protected secret.
                .key("demo-only-remember-me-signing-key-change-me")
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60)
                .userDetailsService(users))
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

**Explanation:**

1. `UserDetailsService` provides the user and BCrypt password hash. Interactive login checks the password and constructs a full Authentication via the normal DAO flow.
2. `formLogin(form -> form.permitAll())` enables form login, including `POST /login` handling. `GET /login` uses the default generated page when no custom login page is specified.
3. `rememberMe(...)` enables remember-me, configuring the checkbox parameter name, token validity, and user lookup service.
4. `key(...)` in the example is a **demo secret**. Production must use a strong, confidential key that stays fixed across restarts, is distributed consistently across nodes, and supports rotation. Never commit real secrets into source code.
5. `rememberMe()` in authorization **is not** what enables remember-me. The feature is enabled via `http.rememberMe(...)`; the `rememberMe()` predicate is purely for **access control**.
6. `requestMatchers("/reader").hasRole("READER")` intentionally demonstrates that role checks **do not implicitly require full authentication**.
7. `anyRequest().authenticated()` is the fallback; real apps should explicitly review all routes under least-privilege principles.
8. Web form login retains **default CSRF protection**. Always use `POST /login` with valid CSRF in tests; never disable CSRF just to “make tests pass”.

**Never use demo passwords and demo remember-me keys in production.** Remember-me cookies are credentials requiring HTTPS, proper cookie flags, and revocation aligned with the threat model.

### 9.5. Controller for Observing Decisions

File `src/main/java/demo/remember/DemoController.java`:

```java
package demo.remember;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

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

    @GetMapping("/remembered")
    String remembered(Authentication authentication) {
        return "remembered:" + authentication.getName();
    }

    @GetMapping("/sensitive")
    String sensitive(Authentication authentication) {
        return "sensitive:" + authentication.getName();
    }

    @GetMapping("/reader")
    String reader(Authentication authentication) {
        return "reader:" + authentication.getName();
    }
}
```

The methods return simple strings to verify authorization. They **do not inspect the token class and decide permissions with if/else**; the security filter chain makes the decision before the controller runs.

### 9.6. MockMvc: Verifying Remember-me With a Real Cookie

File `src/test/java/demo/remember/RememberMeAuthorizationTest.java`:

```java
package demo.remember;

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
class RememberMeAuthorizationTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(boolean remember) throws Exception {
        MockHttpServletRequestBuilder request = post("/login")
            .with(csrf())
            .param("username", "reader")
            .param("password", "training-pass");

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    private Cookie rememberCookie() throws Exception {
        Cookie cookie = login(true).getResponse().getCookie("remember-me");
        assertNotNull(cookie);
        return cookie;
    }

    @Test
    void anonymousCanVisitPublicAndGuest() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/guest"))
            .andExpect(status().isOk())
            .andExpect(content().string("guest"));
    }

    @Test
    void anonymousCannotVisitAuthenticatedAccount()
            throws Exception {
        MvcResult result = mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertNotNull(result.getResponse().getRedirectedUrl());
        assertTrue(result.getResponse().getRedirectedUrl()
            .contains("/login"));
    }

    @Test
    void interactiveLoginSatisfiesFullyAuthenticated()
            throws Exception {
        MvcResult result = login(false);
        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("account:reader"));

        mvc.perform(get("/sensitive").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("sensitive:reader"));
    }

    @Test
    void fullLoginDoesNotMatchRememberMeOnly() throws Exception {
        MvcResult result = login(false);
        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/remembered").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void rememberCookieAuthenticatesWithoutWebSession()
            throws Exception {
        Cookie cookie = rememberCookie();

        // Do not pass .session(...): send a new request with only the remember-me cookie.
        mvc.perform(get("/account").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("account:reader"));
    }

    @Test
    void rememberedOnlyRouteRecognizesRememberMe()
            throws Exception {
        Cookie cookie = rememberCookie();

        mvc.perform(get("/remembered").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("remembered:reader"));
    }

    @Test
    void rememberCookieIsNotFullyAuthenticated()
            throws Exception {
        Cookie cookie = rememberCookie();

        MvcResult result = mvc.perform(get("/sensitive")
                .cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertNotNull(result.getResponse().getRedirectedUrl());
        assertTrue(result.getResponse().getRedirectedUrl()
            .contains("/login"));
    }

    @Test
    void rememberedUserCannotUseAnonymousOnlyPage()
            throws Exception {
        Cookie cookie = rememberCookie();

        int responseStatus = mvc.perform(get("/guest").cookie(cookie))
            .andReturn().getResponse().getStatus();

        assertNotEquals(200, responseStatus);
    }

    @Test
    void hasRoleAloneCanPermitRememberedPrincipal()
            throws Exception {
        Cookie cookie = rememberCookie();

        mvc.perform(get("/reader").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("reader:reader"));
    }

    @Test
    void wrongPasswordDoesNotGrantRememberMe()
            throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "incorrect")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        // Some failure handlers may send a cookie-clearing header.
        Cookie cookie = result.getResponse().getCookie("remember-me");
        assertTrue(cookie == null || cookie.getMaxAge() == 0);
    }
}
```

The tests execute real requests through the **Spring Security filter chain**, rather than using `.with(user(...))` or fabricating a `RememberMeAuthenticationToken` and claiming cookies were tested. `.with(user(...))` injects a test principal and can bypass the very remember-me mechanism under test.

Most importantly, **`rememberCookie()`** grabs the cookie from a successful `POST /login` response with the checkbox ticked, then invokes APIs in a fresh request **without sending a session**. Only then does the remember-me filter actually construct a `RememberMeAuthenticationToken`.

The `hasRoleAloneCanPermitRememberedPrincipal` test **illustrates a pitfall to watch for in security design**, not a recommendation to allow remember-me for high-sensitivity transactions.

### 9.7. Run Commands and Expected Results

From the `remember-me-auth-levels` project directory, with JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

**Ten tests are expected to pass** with the matching dependencies and configuration. This expectation is based on the source code, not an executed run log; there is no fixed Maven stdout because timings, versions, and systems vary.

Key outcomes:

| Scenario | Expected |
| --- | --- |
| Anonymous GET `/public` | 200 `public` |
| Anonymous GET `/guest` | 200 `guest` |
| Anonymous GET `/account` | Redirect to login |
| Full form login, GET `/sensitive` with session | 200 `sensitive:reader` |
| Full form login, GET `/remembered` with session | 403 (not remember-me authentication) |
| Sessionless request with remember-me cookie, GET `/account` | 200 `account:reader` |
| Same remember-me cookie, GET `/remembered` | 200 `remembered:reader` |
| Same remember-me cookie, GET `/sensitive` | Redirect to login because full authentication is needed |
| Remembered GET `/guest` | Not allowed |
| Remembered GET `/reader` | 200 if holding `ROLE_READER` |
| Wrong password login with remember-me checked | No valid new cookie |

**Never store or print remember-me cookies into public logs/test reports**. Doing so can allow others to authenticate as the cookie owner's account.

## 10. Standalone Java 17 Snippet: Authentication Predicate Model

Spring Security relies on token classes and `AuthenticationTrustResolver`, not an enum like the one below. However, this standalone Java 17 model helps visualize each predicate's Boolean result.

Create `AuthenticationLevelsDemo.java`:

```java
public class AuthenticationLevelsDemo {

    enum Level {
        ANONYMOUS,
        REMEMBER_ME,
        FULL
    }

    static boolean authenticated(Level level) {
        return level != Level.ANONYMOUS;
    }

    static boolean fullyAuthenticated(Level level) {
        return level == Level.FULL;
    }

    static boolean rememberMe(Level level) {
        return level == Level.REMEMBER_ME;
    }

    static boolean anonymous(Level level) {
        return level == Level.ANONYMOUS;
    }

    public static void main(String[] args) {
        for (Level level : Level.values()) {
            System.out.printf(
                "%s authenticated=%s fully=%s rememberMe=%s anonymous=%s%n",
                level,
                authenticated(level),
                fullyAuthenticated(level),
                rememberMe(level),
                anonymous(level)
            );
        }
    }
}
```

Compile and run:

```bash
javac AuthenticationLevelsDemo.java
java AuthenticationLevelsDemo
```

**Exact** stdout with Java 17:

```text
ANONYMOUS authenticated=false fully=false rememberMe=false anonymous=true
REMEMBER_ME authenticated=true fully=false rememberMe=true anonymous=false
FULL authenticated=true fully=true rememberMe=false anonymous=false
```

This is a learning model: it does not construct Spring `Authentication`, verify credentials, read cookies, evaluate authorities, or represent custom authentication resolvers. Section 9 tests Spring Security's real Servlet behavior.

## 11. Why Can Remember-me Succeed Even After the Session Expires?

A typical lifecycle:

```text
10:00 Form login succeeds with remember-me checked
       |
       +-- HttpSession holds full Authentication
       +-- Browser has JSESSIONID
       +-- Browser has remember-me cookie
       |
12:00 HttpSession expires due to inactivity
       |
12:10 Browser GET /account
       |
       +-- Old session cookie no longer restores Authentication
       +-- Remember-me cookie is still valid
       +-- RememberMeAuthenticationFilter autoLogin
       +-- RememberMeAuthenticationToken
       |
       +-- /account authenticated() --> may allow
       +-- /sensitive fullyAuthenticated() --> prompts interactive login
```

Times in the diagram are **hypothetical**, not default timeout numbers. Whether a session expires after 2 hours depends on the Servlet session store configuration; the remember-me cookie has its own independent lifetime.

### 11.1. Never Always Permit Just Because a Remember-me Cookie Exists

A cookie may be:

- expired;
- carrying an invalid signature/key;
- belonging to a username that no longer exists;
- revoked in the persistent-token repository;
- mismatched against validation data required by the implementation;
- omitted due to `Domain`/`Path`/`SameSite`/`Secure`;
- cleared after logout;
- blocked or overwritten by the browser.

Only when remember-me services successfully validate the token does the framework supply an appropriate Authentication for the request. Never extract a cookie value yourself and trust the username inside that string.

### 11.2. Do Not Assume Redirecting to Login Upgrades All Security Checks

Redirecting to `/login` brings the user back to interactive authentication when needed. Yet reaching “full Authentication” after login **does not automatically satisfy** MFA requirements or recent password verification. For sensitive transactions, enforce step-up policies at the service/authorization layer.

## 12. Logout, Revocation, and Password Changes

### 12.1. Logout Usually Must Handle Both Session and Remember-me

A standard Spring Security logout form can invalidate the session and call `RememberMeServices.logout(...)` to remove the browser's remember-me cookie. However:

- **Clearing the browser cookie** stops that browser from continuing to auto-send the token.
- **Server-side token revocation** may be needed with persistent-token remember-me.
- With pure signed token-based cookies, **a stolen copy of the cookie** can remain valid while the secret key and verification inputs remain unchanged, until expiration.
- Logging out on one device does not necessarily log out all devices.
- Changing a password hash can invalidate token-based remember-me in some implementations; do not generalize this to every token or session.

Before claiming “log out all devices”, test sessions across multiple browsers, remember-me tokens, nodes, and secondary/SSO tokens.

### 12.2. Revoking Remember-me Does Not Revoke Existing HTTP Sessions

A user may have already restored remember-me into an Authentication and continued using a session, depending on configuration. Deleting the persistent token row in the DB does not automatically invalidate all previously logged-in sessions.

For comprehensive revocation after account compromise, manage separately: session store/registry, remember-me token repository, bearer/refresh tokens, external SSO, and in-flight requests.

### 12.3. Cookie Security

In production:

- Use **HTTPS**, set appropriate `Secure`/`HttpOnly`; choose `SameSite` per threat model without treating SameSite as a complete CSRF replacement.
- Never place remember-me tokens in URLs or logs.
- Never store raw tokens in analytics events or metric labels.
- Bound lifetimes to risk levels; multi-month remember-me periods require careful security and UX review.
- Never use static demo signing keys in real code; enforce secret management, key rotation, and consistent distribution across nodes.
- On shared devices, present the remember-me checkbox clearly and let users uncheck it and revoke sessions/tokens.

### 12.4. CSRF With Remember-me

Remember-me relies on cookies, which browsers can send automatically on requests. Therefore cookie-authenticated POST/PUT/DELETE operations require **proper CSRF protection**, not just authentication.

Applying `fullyAuthenticated()` to sensitive routes reduces certain risks, yet **does not replace CSRF controls**. CSRF and authentication trust solve two different problems.

## 13. Common Mistakes in Authorization Decisions

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Relying on `authentication.isAuthenticated()` to detect non-anonymous users | `AnonymousAuthenticationToken` can report true | Use proper authorization rules/trust resolvers |
| Assuming `authenticated()` always requires entering the current password | Remember-me can be accepted | Use `fullyAuthenticated()` for the full-login boundary |
| Assuming `fullyAuthenticated()` proves MFA succeeded | Can allow older non-MFA session logins | Add step-up/recent-authentication/MFA policy |
| Assuming `rememberMe()` accepts full login “because full is stronger” | Full token is not classified as remember-me | Use `authenticated()` if accepting both |
| Using `anonymous()` instead of `permitAll()` for public pages | Logged-in users get blocked from public pages | Choose `permitAll()` when everyone should view |
| Using only `hasRole("ADMIN")` for sensitive actions | Remembered admin still holds sufficient authority | Combine authority with authentication trust/step-up |
| Confusing `rememberMe` config with `rememberMe()` authorization rule | Enabling the feature and checking permissions are separate tasks | Configure remember-me in `http.rememberMe(...)`, rule in `authorizeHttpRequests` |
| Thinking JSESSIONID and remember-me are the same cookie | Wrong lifetime and auto-login mechanics | Separate session state from remember-me credentials |
| Testing remembered mode with `.with(user(...))` | Test can bypass `RememberMeAuthenticationFilter` | Obtain cookie from real form login and send a new sessionless request |
| Checking only status 200 on `/account` | Cannot tell whether authenticated via session or remember-me | Add tests for `fullyAuthenticated` and `rememberMe` routes |
| Clearing cookie and claiming server revoked copied tokens | Stateless token-based cookies may still be valid | Design real revocation for security requirements |
| Assuming password change always kills all active sessions | `SecurityContext` in session may stay valid | Maintain explicit session revocation policy |
| Storing remember-me key in production source code | Exposed key allows forging valid tokens | Use secret manager, key rotation, and proper scoping |
| Setting overly long remember-me cookie expiry without risk review | Widens abuse window for leaked tokens | Choose TTL per threat model, support revocation |
| Disabling CSRF because “we have a remember-me cookie” | Browser auto-sending cookie leads to CSRF risk | Keep CSRF for cookie-authenticated state-changing actions |
| Custom `Authentication` not classified properly by trust resolver | `fullyAuthenticated/rememberMe` rules behave unexpectedly | Test token class/trust resolver and policies |
| Interpreting 302 login redirect as “login failed” | Remembered user may simply need step-up | Distinguish full-authentication challenge from bad password |

## 14. Debugging a Blocked Request Despite Having a Remember-me Cookie

Walk through step by step:

1. **Right `SecurityFilterChain`?** If a stateless/Basic or JWT API chain does not enable remember-me, the cookie is ignored by design.
2. **Existing session authentication?** If a full Authentication already exists in the session, the remember-me filter typically creates no new token.
3. **Did the request actually send the remember-me cookie?** Check cookie name, Path, Domain, Secure, and SameSite; avoid logging cookie values.
4. **Which `RememberMeServices` is active?** `TokenBasedRememberMeServices` or `PersistentTokenBasedRememberMeServices`, and matching key/repository?
5. **Is the token valid?** Check TTL, key rotation, user state, password hash changes, or persistent token repo without printing the token.
6. **What authorities does the principal hold?** A `hasRole` rule can deny access even when remember-me succeeds.
7. **What is the route's policy?** `authenticated`, `fullyAuthenticated`, `rememberMe`, and `anonymous` mean different things.
8. **If redirected to login**, the remembered principal may simply not satisfy `fullyAuthenticated()`, rather than the cookie being broken.
9. **If the response is 403**, distinguish authorization denied from CSRF denied; do not lump every 403 into wrong permissions.
10. **Custom `AuthorizationManager`/trust resolver present?** Check how it classifies `RememberMeAuthenticationToken` and `AnonymousAuthenticationToken`.
11. **If copied cookies still work after logout**, that may be a limitation of a token-based strategy lacking server-side revocation.
12. **If only some nodes accept the token**, check key/repository/clock/config consistency across the cluster.

In development environments, you can enable:

```properties
logging.level.org.springframework.security=DEBUG
```

Never log raw `Authorization` headers, passwords, remember-me cookies, or tokens. Focus on chain, filter, route, authentication result, HTTP status, and trace IDs.

## 15. Scenario Exercises

**Q1.** Anonymous opens `/public`, which is configured with `permitAll()`. Must an `Authentication` exist?

**Answer:** The user does not need to be logged in. An `AnonymousAuthenticationToken` may appear via the anonymous filter, yet `permitAll` does not require a verified identity.

**Q2.** A user logs in via form with only `ROLE_READER`. When the session is lost, the remember-me cookie remains valid. Does an `authenticated()` route permit them into `/account`?

**Answer:** Yes, because a valid `RememberMeAuthenticationToken` counts as authenticated per the trust resolver; other resource/authority policies still apply if configured.

**Q3.** Why does `fullyAuthenticated()` block a `RememberMeAuthenticationToken` even though the token's `isAuthenticated()` is true?

**Answer:** The trust resolver distinguishes remember-me from full authentication. `fullyAuthenticated` requires authentication that is neither anonymous nor remember-me.

**Q4.** Someone who just entered the right password and holds full Authentication visits a `rememberMe()` route. Are they permitted?

**Answer:** Not under the exact remember-me predicate: a full token is not classified as a `RememberMeAuthenticationToken`. To allow both, use `authenticated()`.

**Q5.** `/admin` has only `hasRole("ADMIN")`. An admin logged in previously and holds a valid remember-me cookie after the old session expired. Can they access it?

**Answer:** Potentially yes, if the remember-me Authentication carries `ROLE_ADMIN` and no other condition applies. Sensitive actions should combine full/recent authentication or MFA per policy.

**Q6.** Does `fullyAuthenticated()` automatically force the user to enter a fresh MFA code within 5 minutes?

**Answer:** No. It excludes anonymous and remember-me, yet does not encode MFA or authentication recency requirements.

**Q7.** The user logs out and the server emits `Set-Cookie` clearing remember-me. Is an attacker who previously copied a token-based cookie guaranteed to be blocked?

**Answer:** There is no guarantee if the server lacks revocation state and the signed cookie remains valid. Assess the threat model and choose persistent-token/revocation or another appropriate solution.

**Q8.** A fully logged-in user opens `/guest` governed by `anonymous()` and receives 403. Is that a bug?

**Answer:** Not necessarily: the rule permits only anonymous. If the content is meant to be public, change it to `permitAll()`.

**Q9.** Is using `MockMvc .with(user("reader"))` enough to test `rememberMe()`?

**Answer:** No. It mocks a principal and can bypass creating `RememberMeAuthenticationToken` from cookies. Use real form login, capture the remember-me cookie, and send a fresh sessionless request.

**Q10.** An app shares the same remember-me cookie across staging and production with different keys. Should the cookie be expected to work in both?

**Answer:** No. Signing keys and cookie scope govern validity; distinct environments must isolate secrets, domains, and configurations.

## 16. Production Adoption Checklist

### 16.1. Checks Before Enabling Remember-me

- Is “remember me” genuinely needed, or is session timeout sufficient for the UX?
- Can users toggle remember-me, and is there a warning on shared devices?
- Does token-based or persistent-token fit revocation, multi-device, and audit requirements?
- Are secrets/keys properly managed and rotated?
- Does the cookie use appropriate `Secure`/`HttpOnly`/`Path`/`Domain`/`SameSite` flags per HTTPS and threat model?
- Do login/remember-me endpoints have rate limiting and abuse detection?
- Does logout clear the cookie and revoke server-side tokens when needed?
- Do password changes, account lockouts, and logout-all handle both active sessions and remember-me?

### 16.2. Per-Route Checks Before Release

- Is the route public (`permitAll`), anonymous-only, remembered-only, authenticated, or fullyAuthenticated?
- If roles/authorities are checked, which privileges can a remembered principal hold?
- Does the route expose sensitive data or side effects requiring full/recent authentication/MFA?
- Are business ownership checks, tenant checks, and method security in place where needed?
- Is CSRF handled for cookie-authenticated requests?
- If a remembered user hits a full-auth route, does UX redirect sensibly to login/step-up?
- Are both full login **and** sessionless remember-cookie paths tested for sensitive and non-sensitive routes?
- Are anonymous, failed login, and logout/expiration tested against expectations?

### 16.3. Operational Observability

- Separate anonymous/remember-me/full metrics for security investigations if policy allows, without putting tokens in metrics.
- Track auto-login failure spikes after key rotation, user store changes, deploys, or clock drift.
- Monitor login abuse, anomalous token usage, and account takeover indicators.
- Ensure telemetry never leaks sensitive customer/authentication details.

## 17. Core Takeaways

- Remember-me is a **cookie-based auto-authentication mechanism**, not merely extending `HttpSession`.
- `AnonymousAuthenticationToken` can exist even when a user is not logged in; never inspect `Authentication.isAuthenticated()` alone to infer a real user.
- `AuthenticationTrustResolver` distinguishes anonymous, remember-me, and fully authenticated; authorization rules rely on that classification.
- `authenticated()` accepts remember-me or full; `fullyAuthenticated()` excludes remember-me; `anonymous()` accepts only anonymous; `rememberMe()` accepts only remember-me; `permitAll()` accepts all states.
- Role/authority checks do not prove full login. For sensitive info or actions, pair trust conditions with domain authorization and step-up/MFA as needed.
- Token-based and persistent-token remember-me differ in revocation capabilities. Clearing a cookie does not automatically invalidate copied tokens.
- Test auto-authentication with **real cookies from form login**, sending a fresh **sessionless** request, then verify `authenticated`, `fullyAuthenticated`, `rememberMe`, `anonymous`, and `hasRole` across routes.
