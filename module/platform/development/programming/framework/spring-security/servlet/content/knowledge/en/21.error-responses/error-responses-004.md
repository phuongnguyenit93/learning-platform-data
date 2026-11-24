# AuthenticationTrustResolver and Handling Anonymous or Remember-Me Users

## Objectives

In Spring Security Servlet, **access denied** does not always equate to **403 Forbidden**. Three distinct cases arise: unauthenticated guests (anonymous) need to authenticate; remember-me users may need a full login before sensitive operations; and fully authenticated users lacking permission must be denied per policy. `AuthenticationTrustResolver` and `ExceptionTranslationFilter` collaborate to route each case to the appropriate `AuthenticationEntryPoint` or `AccessDeniedHandler`.

After finishing this lesson, you will be able to:

1. Distinguish `Authentication`, `AnonymousAuthenticationToken`, `RememberMeAuthenticationToken`, and full authentication.
2. Explain why the `Authentication.isAuthenticated()` flag alone is insufficient to treat a caller as a real user.
3. Use `AuthenticationTrustResolver.isAnonymous()` and `isRememberMe()` to classify tokens.
4. Grasp the differences among `permitAll()`, `anonymous()`, `authenticated()`, `fullyAuthenticated()`, and `hasRole()`.
5. Describe how `ExceptionTranslationFilter` handles `AuthenticationException`, `AccessDeniedException`, and chooses a response.
6. Distinguish 302 redirects, 401 challenges, 403 denials, and CSRF rejections.
7. Build a Spring Boot 3.x, Security 6.x, Java 17+ demo with `formLogin` and `rememberMe`.
8. Test anonymous, remember-me, fully authenticated, and missing-role scenarios with MockMvc.
9. Understand limitations of remember-me tokens, cookies, logout, persistent token storage, and key rotation.
10. Distinguish full authentication from recent authentication (fresh authentication) or MFA.

Scope: Spring Security **Servlet/MVC**. This lesson uses browser form login and `HttpSession`, not WebFlux. Hardcoded keys/passwords are strictly for localhost and must not be deployed to production.

## 1. Having an Authentication Does Not Necessarily Mean Logged In

Spring Security uses a `SecurityContext` holding an `Authentication` to represent caller details. On a request where the user has not logged in, `AnonymousAuthenticationFilter` may create an `AnonymousAuthenticationToken` with a principal such as `anonymousUser` and `ROLE_ANONYMOUS`. This model represents a guest **whose identity has not been verified**, not a validly authenticated user.

Example reading the context:

~~~java
Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

boolean flag = current != null && current.isAuthenticated();
~~~

The snippet above is **not** a safe check for "a real user has logged in". `AnonymousAuthenticationToken` can report `isAuthenticated()` as `true` per the token implementation. Spring Security distinguishes anonymous state based on trust semantics, not solely on that flag.

| Request type | Typical Authentication | Meaning |
| --- | --- | --- |
| No context yet | `null` | Identity unknown |
| Not logged in, passed anonymous filter | `AnonymousAuthenticationToken` | Anonymous caller, may carry `ROLE_ANONYMOUS` |
| Recognized via valid remember-me cookie | `RememberMeAuthenticationToken` | Identity restored, but not a full interactive login |
| Succeeded at form login | `UsernamePasswordAuthenticationToken` or provider-chosen token | Authenticated per the active full flow |
| JWT/OIDC API or custom | Mechanism-dependent `Authentication` | Must inspect the specific provider and level of assurance |

**Token class names are not proof of MFA.** If an API uses JWT, the default resolver does not automatically understand ACR/AMR, authentication recency, or how many factors were completed. Step-up requires its own explicit policy.

### Anonymous Processing Flow

~~~text
HTTP GET /account/profile
   |
SecurityContext has no real user yet
   |
AnonymousAuthenticationFilter
   | -> may place AnonymousAuthenticationToken
   |
AuthorizationFilter: route requires authenticated()
   | -> anonymous fails check
   |
ExceptionTranslationFilter:
   | -> anonymous -> AuthenticationEntryPoint
   |
Browser form login: typically 302 to /login
HTTP Basic API: typically 401 + WWW-Authenticate
~~~

Never compare the `anonymousUser` name against a path variable to grant access to user data, and never trust an `X-User` header sent by a client.

## 2. Remember-Me Is Not the Same as Full Login

Remember-me lets a browser stay recognized longer than a normal HTTP session. If the user checked remember-me at login, a suitable `RememberMeServices` can issue a cookie/token. When the `HttpSession` expires while a valid remember-me cookie is still sent, `RememberMeAuthenticationFilter` can use `RememberMeServices` to create a `RememberMeAuthenticationToken`.

~~~text
POST /login + valid password + remember-me
        |
Full Authentication
        | -> HttpSession/SecurityContext
        | -> Remember-me cookie/token (per config)
        v
Browser uses website normally

After session cookie is lost while remember-me cookie remains:
        |
RememberMeServices verifies cookie/token
        |
RememberMeAuthenticationToken
        |
GET /account/profile: authenticated() -> typically allowed
GET /account/payment: fullyAuthenticated() -> insufficient
        |
ExceptionTranslationFilter may require full login
~~~

Remember-me helps UX, but long-lived cookies risk being copied, stolen, or lingering on devices that are no longer trusted. For payments, password changes, email address updates, issuing API keys, or deleting critical data, consider requiring **full login and fresh authentication** according to your threat model.

`AuthenticationTrustResolver` **does not verify cookie signatures**, does not read persistent token repositories, does not decide token expiration, and does not replace `RememberMeServices`. It only classifies an existing `Authentication`.

## 3. The AuthenticationTrustResolver API

Common interface and implementation:

~~~java
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

boolean anonymous = resolver.isAnonymous(current);
boolean rememberMe = resolver.isRememberMe(current);
~~~

This snippet must live inside an appropriate Java method/class; it is not a standalone file. The two core methods are `isAnonymous(Authentication)` and `isRememberMe(Authentication)`. For standard tokens, `AuthenticationTrustResolverImpl` typically classifies based on token type.

Full authentication can be expressed for learning purposes as:

~~~java
boolean hasRealUser =
        current != null
        && current.isAuthenticated()
        && !resolver.isAnonymous(current);

boolean full =
        hasRealUser && !resolver.isRememberMe(current);
~~~

In HTTP policies, prefer built-in `AuthorizationManager`s or the DSL rather than duplicating classification logic across every controller. Utility methods such as `isAuthenticated`/`isFullyAuthenticated` may exist in the interface version in use; follow the exact Spring Security version when writing custom code.

### Constructing Tokens Manually in Tests Is Not Real Authentication

~~~java
var anon = new AnonymousAuthenticationToken(
        "test-key", "anonymousUser",
        List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));

var remembered = new RememberMeAuthenticationToken(
        "test-key", "alice",
        List.of(new SimpleGrantedAuthority("ROLE_USER")));

var full = UsernamePasswordAuthenticationToken.authenticated(
        "alice", null,
        List.of(new SimpleGrantedAuthority("ROLE_USER")));

var resolver = new AuthenticationTrustResolverImpl();

System.out.println(resolver.isAnonymous(anon));        // true
System.out.println(resolver.isRememberMe(remembered)); // true
System.out.println(resolver.isAnonymous(full));        // false
~~~

This snippet requires Spring Security imports and classpath. Outputs in comments are expected under the default resolver. These constructors do **not** verify users/passwords or cookies: use them only to unit-test state classification—never accept untrusted client data and build production tokens from it.

## 4. Common Authorization Conditions

Configuration example:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/status").permitAll()
        .requestMatchers("/account/profile").authenticated()
        .requestMatchers("/account/payment").fullyAuthenticated()
        .requestMatchers("/admin/report").hasRole("ADMIN")
        .anyRequest().denyAll());
~~~

- `permitAll()`: requires no authentication. Logged-in users can also access it.
- `anonymous()`: allows only callers considered anonymous. Do not blindly replace `permitAll` with `anonymous()` for every public page.
- `authenticated()`: requires an `Authentication` considered authenticated by the resolver; remember-me normally satisfies this, whereas anonymous does not.
- `fullyAuthenticated()`: excludes anonymous and remember-me; demands full authentication per framework semantics.
- `hasRole("ADMIN")`: requires `ROLE_ADMIN`; does not by default require full login or MFA.
- `denyAll()`: denies undeclared routes; actual response still depends on trust state and entry point.

| Caller | /public/status | /account/profile | /account/payment | /admin/report |
| --- | --- | --- | --- | --- |
| Anonymous | Allowed | Login required | Login required | Login required |
| Alice remember-me ROLE_USER | Allowed | Allowed | Full login required | Missing role; may be prompted to re-login |
| Alice full login ROLE_USER | Allowed | Allowed | Allowed | Permission denied |
| Root full login ROLE_ADMIN | Allowed | Allowed | Allowed | Allowed |

An easily missed detail: **a remember-me user with `ROLE_ADMIN` can still pass a `hasRole("ADMIN")` rule**, if the role matches and the rule does not require full authentication. If an admin action needs both the role and a full login, configure both conditions (for example method security expression `isFullyAuthenticated() and hasRole('ADMIN')`), rather than expecting the framework to block every remember-me user automatically.

Do not equate `fullyAuthenticated` with fresh login or MFA: a full session could have been authenticated many hours ago. Use `auth_time`, assurance level, step-up, MFA, or password re-verification per policy when business rules demand it.

## 5. ExceptionTranslationFilter and Error Responses

`ExceptionTranslationFilter` is the link converting certain security exceptions into HTTP responses. It typically sits ready to catch `AuthenticationException` or `AccessDeniedException` raised in downstream filters, then delegates to `AuthenticationEntryPoint` or `AccessDeniedHandler`.

~~~text
Request -> authentication/authorization
                |
                +-- OK -> Controller/Service
                |
                +-- AuthenticationException
                |        -> AuthenticationEntryPoint
                |           (login redirect, 401 challenge...)
                |
                +-- AccessDeniedException
                          |
                          +-- anonymous?
                          |       -> AuthenticationEntryPoint
                          |
                          +-- remember-me?
                          |       -> AuthenticationEntryPoint
                          |          (chance to perform full login)
                          |
                          +-- fully authenticated user?
                                  -> AccessDeniedHandler
                                     (typically HTTP 403)
~~~

**Trust classification determines how `AccessDeniedException` is handled.** For insufficiently trusted remember-me sessions, a permission failure can be treated as requiring additional authentication rather than a final forbidden response.

### Role of Each Component

- `AuthenticationTrustResolver`: classifies anonymous/remember-me.
- `AuthenticationEntryPoint`: initiates authentication; `formLogin` typically redirects, Basic typically challenges, and APIs may return JSON 401.
- `AccessDeniedHandler`: handles denials for fully authenticated callers lacking permissions, typically returning 403.
- `ExceptionTranslationFilter`: coordinates the three components above; does not verify passwords/tokens itself.
- `RequestCache`: may retain the saved request to return after login depending on configuration.

If fully logged in yet lacking `ROLE_ADMIN`, repeatedly prompting for a password **cannot fix missing permissions**. Return forbidden per the contract. If remember-me fails `fullyAuthenticated`, redirecting to login to upgrade the authentication level makes sense.

### Not Only 302, 401, and 403

| Code | Typical scenario | What not to conclude |
| --- | --- | --- |
| 302 | Form-login entry point redirects to `/login` | Does not prove the user entered a wrong password |
| 401 | HTTP Basic/bearer challenge or API entry point | Not every app uses this status for anonymous |
| 403 | Sufficiently authenticated user missing role or CSRF check rejected | Cannot deduce root cause from status alone |
| 400 | Container/firewall rejects invalid URL | Does not mean a role was denied |
| 404 | MVC route not found or API hides resource | Cannot verify trust state from status alone |

When `CsrfFilter` rejects a `POST` missing a CSRF token, the response can be 403 **before** authorization rules execute; test with valid CSRF if you want to prove role/trust checks.

A `@PreAuthorize` on a service can also throw `AccessDeniedException`. If the exception occurs during a web request and propagates back through the filter chain, `ExceptionTranslationFilter` can handle it. However, if `@ControllerAdvice` catches and swallows the exception, or a job/message listener calls the service outside HTTP, response/handling will differ.

## 6. Spring Boot 3.x Project: Form Login + Remember Me

### 6.1. Structure and Gradle

~~~text
trust-resolver-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (generate wrapper if not present)
  src/main/java/dev/example/trust/
    TrustDemoApplication.java
    SecurityConfig.java
    TrustController.java
  src/test/java/dev/example/trust/
    TrustDemoIntegrationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'trust-resolver-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Security dependencies are managed by the Boot version; do not force artifacts from a different major version. Use JDK 17+, Gradle Wrapper, and Internet access for initial Maven dependency downloads or a prepared cache.

### 6.2. Java Main

File `src/main/java/dev/example/trust/TrustDemoApplication.java`:

~~~java
package dev.example.trust;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TrustDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TrustDemoApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfig

File `src/main/java/dev/example/trust/SecurityConfig.java`:

~~~java
package dev.example.trust;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-only"))
                        .roles("USER")
                        .build(),
                User.withUsername("root")
                        .password(encoder.encode("root-demo-only"))
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/status").permitAll()
                        .requestMatchers("/account/profile").authenticated()
                        .requestMatchers("/account/payment").fullyAuthenticated()
                        .requestMatchers("/admin/report").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .formLogin(form -> form.permitAll())
                .rememberMe(remember -> remember
                        .userDetailsService(users)
                        .key("local-demo-key-not-for-production")
                        .tokenValiditySeconds(3600))
                .logout(Customizer.withDefaults())
                .build();
    }
}
~~~

Key points to remember:

1. `formLogin(form -> form.permitAll())` opens the Spring Security-provided login page/form to anonymous users.
2. `rememberMe` enables remember-me services, using the user store and demo key; `tokenValiditySeconds=3600` is purely a lab parameter.
3. `authenticated()` on profile accepts remember-me per policy; `fullyAuthenticated()` on payment does not.
4. `hasRole` `ADMIN` checks the role; it does not automatically demand full login for a remember-me admin.
5. `anyRequest().denyAll()` protects routes without explicit policies.
6. Standard `LogoutFilter` is retained. Remember-me cleanup steps should be tested against your remember-me configuration.
7. Default CSRF is not disabled; login/logout POSTs require appropriate CSRF tokens.

Never hardcode passwords and signing keys in production source; use secret management, HTTPS, secure cookie flags, key rotation, and an appropriate user/token repository. Multi-node systems must share the same key or use compatible design when verifying tokens.

### 6.4. TrustController: Observing State Locally

File `src/main/java/dev/example/trust/TrustController.java`:

~~~java
package dev.example.trust;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TrustController {

    private final AuthenticationTrustResolver resolver =
            new AuthenticationTrustResolverImpl();

    @GetMapping("/public/status")
    public TrustState status() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        boolean anonymous = authentication == null
                || resolver.isAnonymous(authentication);
        boolean remembered = authentication != null
                && resolver.isRememberMe(authentication);
        boolean full = authentication != null
                && authentication.isAuthenticated()
                && !anonymous
                && !remembered;
        String name = anonymous ? "guest" : authentication.getName();

        return new TrustState(anonymous, remembered, full, name);
    }

    @GetMapping("/account/profile")
    public String profile() {
        return "PROFILE_OK";
    }

    @GetMapping("/account/payment")
    public String payment() {
        return "PAYMENT_READY";
    }

    @GetMapping("/admin/report")
    public String report() {
        return "ADMIN_REPORT";
    }

    public record TrustState(
            boolean anonymous,
            boolean rememberMe,
            boolean fullyAuthenticated,
            String name) {
    }
}
~~~

The resolver instance in the controller is only for **displaying demo state**; it does not reconfigure the resolver used inside `ExceptionTranslationFilter`. Internally, Spring Security maintains its own chain components. In production, do not expose raw `Authentication`, principal attributes, session cookies, or tokens for debugging.

### 6.5. Running and Observing

~~~bash
./gradlew bootRun
~~~

With Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Open `http://localhost:8080/public/status` in an unauthenticated browser; expected body:

~~~json
{
  "anonymous": true,
  "rememberMe": false,
  "fullyAuthenticated": false,
  "name": "guest"
}
~~~

Visit `http://localhost:8080/account/profile`: browser `formLogin` typically redirects to `/login`. Log in as `alice` with password `alice-demo-only`, check Remember me, then visit `/account/profile` and `/account/payment`. Within the full login session, both are permitted.

To observe remember-me in action: in your local environment, delete only the **session cookie** (such as `JSESSIONID`) while keeping the remember-me cookie; then use the same browser profile to visit `/account/profile`. If the remember-me token is still valid and verified by services, the account can be recognized via `RememberMeAuthenticationToken`. `/public/status` is then expected to show `rememberMe=true`, `fullyAuthenticated=false`. Visiting `/account/payment` will prompt for full login.

If the status remains `full`, the session cookie may not actually have been removed. If status is `anonymous`, the remember-me cookie may be missing/expired/rejected or cookie settings may not match. Do not delete all cookies or perform a normal logout when your goal is to test **expired session with remember-me remaining**.

## 7. MockMvc Testing and Token Classification

File `src/test/java/dev/example/trust/TrustDemoIntegrationTest.java`:

~~~java
package dev.example.trust;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TrustDemoIntegrationTest {

    @Autowired
    MockMvc mvc;

    private static Authentication rememberAlice() {
        return new RememberMeAuthenticationToken(
                "test-key", "alice",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void trustResolverRecognizesTokenKinds() {
        var resolver = new AuthenticationTrustResolverImpl();
        Authentication anonymous = new AnonymousAuthenticationToken(
                "test-key", "anonymousUser",
                List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));
        Authentication remembered = rememberAlice();
        Authentication full =
                UsernamePasswordAuthenticationToken.authenticated(
                        "alice", null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER")));

        assertThat(resolver.isAnonymous(anonymous)).isTrue();
        assertThat(resolver.isRememberMe(anonymous)).isFalse();
        assertThat(resolver.isAnonymous(remembered)).isFalse();
        assertThat(resolver.isRememberMe(remembered)).isTrue();
        assertThat(resolver.isAnonymous(full)).isFalse();
        assertThat(resolver.isRememberMe(full)).isFalse();
    }

    @Test
    void anonymousStatusDoesNotClaimFullLogin() throws Exception {
        mvc.perform(get("/public/status").with(anonymous()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.anonymous").value(true))
                .andExpect(jsonPath("$.rememberMe").value(false))
                .andExpect(jsonPath("$.fullyAuthenticated").value(false))
                .andExpect(jsonPath("$.name").value("guest"));
    }

    @Test
    void anonymousIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/account/profile").with(anonymous()))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void rememberMeCanUseAuthenticatedRule() throws Exception {
        mvc.perform(get("/account/profile")
                        .with(authentication(rememberAlice())))
                .andExpect(status().isOk())
                .andExpect(content().string("PROFILE_OK"));
    }

    @Test
    void rememberMeMustReauthenticateForFullRule()
            throws Exception {
        mvc.perform(get("/public/status")
                        .with(authentication(rememberAlice())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.rememberMe").value(true))
                .andExpect(jsonPath("$.fullyAuthenticated").value(false));

        mvc.perform(get("/account/payment")
                        .with(authentication(rememberAlice())))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void fullUserCanUsePayment() throws Exception {
        mvc.perform(get("/account/payment")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("PAYMENT_READY"));
    }

    @Test
    void fullUserWithoutAdminGets403() throws Exception {
        mvc.perform(get("/admin/report")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void fullAdminCanViewReport() throws Exception {
        mvc.perform(get("/admin/report")
                        .with(user("root").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(content().string("ADMIN_REPORT"));
    }

    @Test
    void formLoginSupportsRememberMeParameter()
            throws Exception {
        mvc.perform(post("/login").with(csrf())
                        .param("username", "alice")
                        .param("password", "alice-demo-only")
                        .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The tests measure three key things: anonymous users require login; remember-me users can view `authenticated` routes but do not satisfy `fullyAuthenticated`; full login missing a role gets forbidden while full `ADMIN` is allowed.

**Testing limitation:** `with(authentication(rememberAlice()))` injects a simulated `Authentication` in MockMvc. It does not itself verify real remember-me cookies, signature/token expiry, persistent token stores, or logout cleanup. A browser/end-to-end HTTP test with real cookies is needed to prove `RememberMeServices` works. Likewise, `with(user("alice"))` is test authentication data, not password verification; the `POST /login` test separately exercises the form authentication flow.

## 8. If You Want JSON 401/403 Instead of Redirects

Browser `formLogin` typically uses a 302 redirect to `/login`. For REST APIs/mobile clients, HTML redirects may be unsuitable; choose `AuthenticationEntryPoint` and `AccessDeniedHandler` according to the API security chain.

**Alternative** snippet for an API security chain:

~~~java
http.exceptionHandling(ex -> ex
        .authenticationEntryPoint(
                (request, response, error) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED))
        .accessDeniedHandler(
                (request, response, error) ->
                    response.sendError(
                        HttpServletResponse.SC_FORBIDDEN)));
~~~

In a Java file using this snippet, import `jakarta.servlet.http.HttpServletResponse`. If using HTTP Basic, preserve the `WWW-Authenticate` challenge per contract—do not turn it into a headerless 401 where clients do not know how to authenticate. With Bearer, Spring Security resource-server entry points/denied handlers have their own contracts and headers.

Do not paste this replacement directly into the `formLogin` demo and still expect 302s in the MockMvc tests. You can create multiple `SecurityFilterChain`s: one for `/api/**` with Basic/Bearer and an API entry point; one for web MVC with `formLogin` and remember-me. Check `securityMatcher`/order and which chain handles which URLs. Never leave sensitive endpoints outside all chains.

A custom error handler does not decide permissions itself. Permissions are still decided by `Authentication` and the `AuthorizationManager`/service policy; the handler merely chooses the response upon denial.

## 9. Critical Operational Concerns

### Cookies and Logout

Remember-me cookies can persist after `HttpSession` is invalidated. If custom logout only clears `SecurityContextHolder` or calls `HttpSession.invalidate()` **without** clearing the remember-me token, subsequent requests can silently auto-login again. Prefer `LogoutFilter`/`LogoutConfigurer` and standard logout handlers; if writing custom MVC logout, add remember-me cleanup matching `RememberMeServices` and the application's token store policy.

Test logout: after a valid `POST /logout` with a CSRF token, reuse the browser/cookies and confirm new requests do not unexpectedly become authenticated again. A cookie remaining in the browser does not necessarily mean the server session is valid, yet a remember-me token can genuinely mint a new `Authentication`.

### Persistent Tokens and Revocation

Token-based remember-me differs from persistent-token-based remember-me. A persistent token repository can support per-device management and revocation by design; do not assume calling `rememberMe()` automatically stores and centrally revokes all tokens. Supporting "log out all devices", account locks, password resets, or replay detection requires explicit policies and token lifecycles.

### Multi-Node

In a cluster, keys, token repositories, `UserDetailsService`, and cookie scope must be compatible across nodes. Spring Session sharing `HttpSession` does not automatically solve every remember-me setup. If node A issues a token while node B uses a different key, browsers may be forced to log in again when the load balancer switches nodes.

### Non-HTTP Requests

A `@PreAuthorize` method can throw `AccessDeniedException` when invoked directly by a scheduled job or message listener. In that case `ExceptionTranslationFilter` does not exist because there is no Servlet response. Jobs must run with a least-privilege service identity/delegation and handle exceptions via retry/alert/fail-closed logic—never grant broad `ROLE_ADMIN` just to suppress errors.

### Authentication Does Not Mean Object-Level Permission

Even `fullyAuthenticated` and `ROLE_ADMIN` do not inherently grant permission on every document or tenant. You still need service/resource authorization, owner/tenant isolation, and business auditing. In multi-tenant APIs, remember that a remember-me token preserves identity—it does not substitute for checking current permissions in the database.

## 10. Common Pitfalls

**Pitfall A: `AnonymousAuthenticationToken.isAuthenticated()` is true, and the system returns private data.** Never use the token boolean flag as proof; use the resolver/authorization DSL and check object permissions.

**Pitfall B: A remember-me user is sent to login when opening payment.** This is expected behavior if payment requires `fullyAuthenticated`; verify policy and entry point before calling it a bug.

**Pitfall C: A full user missing `ROLE_ADMIN` keeps getting sent back to login.** The error handler may be confusing missing permissions with missing login. For fully logged-in users, normally return 403 via `AccessDeniedHandler`.

**Pitfall D: A remember-me admin slips past a sensitive page.** If the rule is only `hasRole("ADMIN")`, a remember-me user with that role can still be allowed. Explicitly require full auth or step-up if policy demands it.

**Pitfall E: After logout, the user logs back in automatically.** The remember-me cookie/token was not cleared; use the proper logout pipeline and retest with the same cookies.

**Pitfall F: An API sends a 302 login page instead of JSON 401.** The request hit the `formLogin` chain. Route to an API chain/entry point matching the client contract.

**Pitfall G: REST API returns 403 and developers assume it was a role check.** `CsrfFilter` can also return 403 for POST/PUT missing tokens. Check logs/tests with valid CSRF.

**Pitfall H: Custom `Authentication` is not recognized by the resolver.** `AuthenticationTrustResolverImpl` recognizes standard token classes and does not automatically know the assurance level of every custom provider. Design custom checks when needed.

**Pitfall I: Losing the remember-me key during a rolling deploy.** Old tokens become invalid and users must log in again. Manage keys via a secret store and have a rollout plan.

**Pitfall J: Node A remembers the user while node B does not.** Check keys, token repos, `UserDetailsService`, cookie domain/path, and load balancer behavior; do not conflate the issue with Redis `HttpSession`.

**Pitfall K: A locked user still has an active session/remember-me.** Implement revalidation, token revocation, and account lifecycle handling rather than assuming old tokens revoke themselves.

**Pitfall L: `ControllerAdvice` returns 200 for `AccessDeniedException`.** Never swallow security exceptions or grant fallback permissions. If handled specially, preserve proper denial semantics.

**Pitfall M: `isFullyAuthenticated` is assumed to mean recent MFA.** That is a misconception. Authentication-time/MFA requirements must inspect trusted claims/attributes and use dedicated step-up flows.

**Pitfall N: Simulating a token in tests and assuming cryptography was tested.** MockMvc `authentication` post-processors do not verify cookies; add E2E tests for real `RememberMeServices`.

## 11. Pre-Production Checklist

1. Define requirements for each URL: `permitAll`, `authenticated`, `fullyAuthenticated`, role, owner, tenant.
2. Keep the distinction between anonymous, remember-me, and full authentication clear.
3. Use `AuthenticationTrustResolver` to classify, never treating `anonymousUser` as proof of identity.
4. Configure `AuthenticationEntryPoint`/`AccessDeniedHandler` for browser vs. API needs.
5. Test 302/401/403 against the exact security chain rather than guessing from status alone.
6. Keep CSRF protection for form login and cookie authentication, and test unsafe requests with valid tokens.
7. Issue remember-me cookies only after genuine authentication—never mint tokens from client headers.
8. Limit remember-me lifetime and protect cookies with `Secure`/`HttpOnly`/`SameSite` over HTTPS.
9. Clear remember-me tokens on logout, password reset, and account lock per policy.
10. Synchronize keys and persistent token stores across multiple nodes.
11. Never log cookies, passwords, `Authentication` credentials, or raw `Authorization` headers.
12. Require full/step-up login for high-risk actions when specified by the threat model.
13. Combine role/trust checks with object authorization and tenant isolation.
14. Test both positive and negative cases: anonymous, remembered, full USER, full ADMIN, expired token.
15. If using multiple `SecurityFilterChain`s, test chain selection and fallback rules.
16. Never catch `AccessDeniedException` to return success or sensitive data.
17. For jobs/async tasks, establish safe service identities and `SecurityContext` propagation.
18. Review remember-me cookie/token policies after upgrading Spring Boot/Security.

## 12. Self-Practice

**Question 1.** Why can an anonymous token have `isAuthenticated=true`, yet Spring Security still blocks it at `authenticated()`?

**Answer:** that is an implementation flag, whereas the rule uses `AuthenticationTrustResolver` semantics to identify anonymous callers rather than logged-in users.

**Question 2.** Does `AuthenticationTrustResolver` read and verify remember-me cookie signatures?

**Answer:** no. `RememberMeServices` performs verification; the resolver classifies an already-created `Authentication`.

**Question 3.** A remember-me user is allowed on `/account/profile` but redirected to login on `/account/payment`. Why?

**Answer:** profile uses `authenticated`; payment uses `fullyAuthenticated`, which does not accept remember-me; `ExceptionTranslationFilter` can invoke `AuthenticationEntryPoint`.

**Question 4.** What does a fully logged-in user lacking `ROLE_ADMIN` typically receive?

**Answer:** 403 via `AccessDeniedHandler`, not a prompt to log in again.

**Question 5.** Do web form login and a Basic API respond identically to anonymous requests?

**Answer:** not necessarily. Form login typically sends 302 to `/login`, while Basic typically sends a 401 challenge; the entry point decides.

**Question 6.** A remember-me admin has `ROLE_ADMIN`; does a `hasRole("ADMIN")` rule force re-authentication?

**Answer:** no; you must combine a policy requiring full auth or step-up for sensitive actions.

**Question 7.** Does `fullyAuthenticated` confirm that MFA was completed?

**Answer:** no. It primarily separates anonymous/remember-me; MFA/fresh auth requires separate mechanisms.

**Question 8.** Logout invalidates the session while remember-me remains—what can happen?

**Answer:** the browser may automatically re-authenticate on the next request using the remember-me token; cookie/token cleanup is required.

**Question 9.** Does a test injecting `RememberMeAuthenticationToken` prove real cookies work?

**Answer:** no. It only tests classification/authorization; E2E cookie/token validation is still required.

**Question 10.** If POST returns 403, is it guaranteed to be caused by a role check?

**Answer:** no; it could be CSRF or another filter. You must inspect the handling path.

## Conclusion

**`AuthenticationTrustResolver` classifies anonymous and remember-me states; `ExceptionTranslationFilter` relies on that state to choose between starting authentication or returning forbidden.** Anonymous users and remember-me sessions needing elevated authentication are typically routed to `AuthenticationEntryPoint`, whereas fully logged-in users lacking permissions typically receive 403 via `AccessDeniedHandler`. Specific HTTP codes depend on the entry point and `SecurityFilterChain`.

Configure `authenticated()` and `fullyAuthenticated()` properly, protect remember-me cookies/tokens, preserve CSRF, and test both with MockMvc and real browser requests. For sensitive actions, add **fresh authentication/MFA and resource-level permission checks**, not merely token classification.