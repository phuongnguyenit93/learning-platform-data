# Separating Admin, User, and Service Account Logins

> Scope: **Spring Security - authentication → Multiple Mechanisms** on **Spring Boot 3.5 / Spring Security 6.5 Servlet / Java 17+**. This lesson explains how to separate interactive logins for administrators and end users from non-interactive authentication for service accounts, covering credential intake, identity stores, authorities, sessions, and testing. The Java example uses three `SecurityFilterChain` beans and one fallback chain.

## 1. Three Identity Groups Do Not Share the Same Login Contract

| Group | Subject | Authentication flow | URL | Authorities | State |
| --- | --- | --- | --- | --- | --- |
| Administrators | Operations staff | Form login, hashed passwords; production requires MFA/step-up | `/admin/login`, `/admin/**` | `REALM_ADMIN` **and** `ROLE_ADMIN` | Session; admin context |
| Users | End users | Form login | `/user/login`, `/user/**` | `REALM_USER` **and** `ROLE_USER` | Session; user context |
| Service accounts | Workers, jobs, other apps | OAuth2 `client_credentials` to obtain access token; API verifies Bearer JWT | `/svc/**` | `SCOPE_reports.read` | Stateless, no form/cookie login |

This separation involves at least four parts: (1) authentication mechanism, (2) data source or issuer determining identity, (3) authorization policy, and (4) whether/how `SecurityContext` is persisted. Splitting login URLs alone while still sharing the same accounts, tokens, and session repository does not guarantee isolation.

Requirements that must be proven by tests:

1. User `alice` successfully signed in at `/user/login` **cannot** access `/admin/home` using only her cookie.
2. Administrator `operator` signed in at `/admin/login` **does not automatically have** a user context.
3. `operator`'s credentials sent to `/user/login` and `alice`'s credentials sent to `/admin/login` must both fail.
4. A browser `HttpSession` does not substitute for `Authorization: Bearer` on `/svc/reports`.
5. A service token with scope `reports.read` can only access service endpoints matching its policy; a bearer token is not an admin login session.
6. Requests outside any published URL group must still hit the fallback chain and never slip past Spring Security silently.

**Authentication** answers “who is the subject and how trustworthy is the proof?”; **authorization** answers “what is the subject allowed to do within what scope?”. Even an admin account does not implicitly have permissions across every app or tenant. A service account is a **machine identity**, not a staff account with `ROLE_SERVICE` tacked on.

## 2. How FilterChainProxy Selects a SecurityFilterChain

On the Servlet stack, Spring Security uses `FilterChainProxy` to match `SecurityFilterChain` beans in priority order. **Only the first matching chain executes**.

```text
HTTP request
     |
     v
FilterChainProxy
     |
     +-- /admin/** -> Admin chain @Order(1)
     |                 form login; admin AuthenticationManager
     |                 CSRF ON; SECCTX_ADMIN; ROLE_ADMIN + REALM_ADMIN
     |
     +-- /user/**  -> User chain @Order(2)
     |                 form login; user AuthenticationManager
     |                 CSRF ON; SECCTX_USER; ROLE_USER + REALM_USER
     |
     +-- /svc/**   -> Service chain @Order(3)
     |                 Bearer JWT / JwtDecoder
     |                 STATELESS; SCOPE_reports.read
     |
     '-- remaining -> Fallback @Order(4), denyAll()
```

- `http.securityMatcher("/admin/**")` determines **which requests enter the chain**. `authorizeHttpRequests(...requestMatchers(...))` only defines policy **inside** the selected chain. Never substitute one matcher type for the other.
- Filter-handled URLs (such as `POST /login`) must fall inside the chain's scope. When using `/admin/**`, set `loginProcessingUrl("/admin/login")` instead of leaving the default `/login`.
- When setting `loginPage("/admin/login")`, Spring Security **does not automatically generate the GET HTML page**. You must create a dedicated controller/template for `GET /admin/login`. The same applies to user login.
- A chain without a `securityMatcher` acts as the fallback so all remaining requests still pass through Spring Security.
- The service chain disables `formLogin` and does not accept browser sessions as authentication proof.

### Why Separate Chains Do Not Automatically Mean Separate Sessions

When two browser chains run on the same host, they can share the **same `JSESSIONID` cookie** and the same `HttpSession`. If both use the default `SPRING_SECURITY_CONTEXT` key, they can read the same `Authentication` regardless of which login URL created it.

This example uses two `HttpSessionSecurityContextRepository` instances with distinct keys:

```text
HttpSession (demo shares JSESSIONID)
  |
  +-- SECCTX_ADMIN -> Authentication operator, REALM_ADMIN, ROLE_ADMIN
  |
  '-- SECCTX_USER  -> Authentication alice, REALM_USER, ROLE_USER
```

This separates the **SecurityContext logically**, not into two physical sessions. A stolen cookie can expose both contexts; a default logout on one chain usually invalidates the entire `HttpSession`. For a strong admin boundary, separate the applications/origins such as `admin.example.com` and `app.example.com`, use host-only cookies, separate session stores and timeouts, and enforce MFA/step-up for admins. Do not treat renaming a session attribute as absolute isolation.

## 3. Runnable Example on Spring Boot 3.5 / Spring Security 6.5

The example demonstrates two independent in-memory user stores, each holding a single identity. For services, the application acts as an **OAuth2 Resource Server** and verifies JWTs from a trusted issuer. The tests in section 5 use a test-only fake `JwtDecoder` to verify the flow; do not use that decoder in production.

### 3.1. Dependencies and application.yml

In a Spring Boot 3.5 project configured with Gradle/Java 17, declare:

```groovy
// build.gradle - dependencies section
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**`src/main/resources/application.yml`**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          # Provide a real issuer with valid metadata/JWK when running against an IdP.
          issuer-uri: https://idp.example.test/realms/learning
          audiences: https://api.example.test
server:
  servlet:
    session:
      cookie:
        http-only: true
        same-site: lax
```

`idp.example.test` is a sample hostname, **not a real server**. `bootRun` requires a properly configured IdP to validate real Bearer JWTs; the test suite below uses a `@TestConfiguration JwtDecoder` and runs without an IdP. In production, use HTTPS and enable `Secure` cookies along with HSTS per deployment policy.

**`src/main/java/example/realms/RealmApplication.java`**

```java
package example.realms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RealmApplication {
    public static void main(String[] args) {
        SpringApplication.run(RealmApplication.class, args);
    }
}
```

### 3.2. SecurityConfig: Separate Identity Stores, Managers, and Contexts

**`src/main/java/example/realms/SecurityConfig.java`**

```java
package example.realms;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
@EnableWebSecurity
public class SecurityConfig {
    public static final String ADMIN_CONTEXT = "SECCTX_ADMIN";
    public static final String USER_CONTEXT = "SECCTX_USER";

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    // Admin identities only, not shared with appUsers.
    @Bean("adminUsers")
    UserDetailsService adminUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("operator")
                .password(encoder.encode("operator-pass"))
                .authorities("REALM_ADMIN", "ROLE_ADMIN")
                .build()
        );
    }

    // End-user identities only.
    @Bean("appUsers")
    UserDetailsService appUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .authorities("REALM_USER", "ROLE_USER")
                .build()
        );
    }

    private static AuthenticationManager manager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean("adminManager")
    AuthenticationManager adminManager(
            @Qualifier("adminUsers") UserDetailsService users,
            PasswordEncoder encoder) {
        return manager(users, encoder);
    }

    @Bean("appManager")
    AuthenticationManager appManager(
            @Qualifier("appUsers") UserDetailsService users,
            PasswordEncoder encoder) {
        return manager(users, encoder);
    }

    private static SecurityContextRepository sessionContext(String key) {
        HttpSessionSecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();
        repository.setSpringSecurityContextKey(key);
        return repository;
    }

    @Bean("adminRepo")
    SecurityContextRepository adminRepo() {
        return sessionContext(ADMIN_CONTEXT);
    }

    @Bean("appRepo")
    SecurityContextRepository appRepo() {
        return sessionContext(USER_CONTEXT);
    }

    // Access requires both the exact realm and a verified role.
    private static AuthorizationManager<RequestAuthorizationContext>
            realmAndRole(String realm, String role) {
        return AuthorizationManagers.allOf(
            AuthorityAuthorizationManager
                .<RequestAuthorizationContext>hasAuthority(realm),
            AuthorityAuthorizationManager
                .<RequestAuthorizationContext>hasRole(role)
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain adminChain(
            HttpSecurity http,
            @Qualifier("adminManager") AuthenticationManager manager,
            @Qualifier("adminRepo") SecurityContextRepository repository)
            throws Exception {
        http
            .securityMatcher("/admin/**")
            .authenticationManager(manager)
            .securityContext(sc -> sc.securityContextRepository(repository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/login").permitAll()
                .anyRequest().access(realmAndRole("REALM_ADMIN", "ADMIN")))
            .formLogin(form -> form
                .loginPage("/admin/login")
                .loginProcessingUrl("/admin/login")
                .defaultSuccessUrl("/admin/home", true)
                .failureUrl("/admin/login?error")
                .permitAll())
            .logout(logout -> logout
                .logoutUrl("/admin/logout")
                .logoutSuccessUrl("/admin/login?logout"));
        // Default CSRF still protects form POSTs.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain userChain(
            HttpSecurity http,
            @Qualifier("appManager") AuthenticationManager manager,
            @Qualifier("appRepo") SecurityContextRepository repository)
            throws Exception {
        http
            .securityMatcher("/user/**")
            .authenticationManager(manager)
            .securityContext(sc -> sc.securityContextRepository(repository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/user/login").permitAll()
                .anyRequest().access(realmAndRole("REALM_USER", "USER")))
            .formLogin(form -> form
                .loginPage("/user/login")
                .loginProcessingUrl("/user/login")
                .defaultSuccessUrl("/user/home", true)
                .failureUrl("/user/login?error")
                .permitAll())
            .logout(logout -> logout
                .logoutUrl("/user/logout")
                .logoutSuccessUrl("/user/login?logout"));
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain serviceChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/svc/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/svc/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(sc -> sc.securityContextRepository(
                new NullSecurityContextRepository()))
            .requestCache(AbstractHttpConfigurer::disable)
            .csrf(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(4)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
        return http.build();
    }
}
```

Points to review carefully:

1. `adminManager` and `appManager` each have a `DaoAuthenticationProvider` backed by a different `UserDetailsService`. Neither `operator` exists in `appUsers` nor `alice` in `adminUsers`. `ProviderManager` does not automatically share credential stores just because the chains live in the same application.
2. Authorities `REALM_ADMIN`/`REALM_USER` mark the identity type; `ROLE_ADMIN`/`ROLE_USER` represent the role. `realmAndRole(...)` requires **both**. These authorities are granted from server-side data, never read from client-submitted forms or headers.
3. `HttpSessionSecurityContextRepository.setSpringSecurityContextKey(...)` defines the context storage key; `securityContextRepository(...)` wires that repository for reading filters and saving authentication filters. Two chains can share an `HttpSession` without reading each other's `Authentication`.
4. Form login uses a processing URL inside the matcher; GET login is implemented in the next section. `defaultSuccessUrl(...,true)` makes redirect targets deterministic for tests.
5. The service chain uses `oauth2ResourceServer(...jwt(...))`; Bearer authentication creates a `JwtAuthenticationToken` only after `JwtDecoder` verifies the token. `SCOPE_reports.read` comes from a verified scope claim, distinct from a browser `ROLE_ADMIN`.
6. `SessionCreationPolicy.STATELESS` and `NullSecurityContextRepository` make it explicit that the service chain uses no session. CSRF is disabled only in this chain because the bearer header is attached intentionally by the client; do not disable CSRF on the two form chains.
7. The `denyAll()` fallback sits last so newly added routes are not left open. Any endpoint outside the three granted namespaces is denied.

### 3.3. GET Login Pages for Both Realms

When using `.loginPage("/admin/login")`, Spring Security does not automatically generate HTML for a custom page. The example uses a controller rendering minimal HTML forms with the CSRF token retrieved from the request.

**`src/main/java/example/realms/LoginPageController.java`**

```java
package example.realms;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.MediaType;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.HtmlUtils;

@RestController
public class LoginPageController {

    @GetMapping(value = {"/admin/login", "/user/login"},
                produces = MediaType.TEXT_HTML_VALUE)
    public String loginPage(HttpServletRequest request) {
        CsrfToken csrf =
            (CsrfToken) request.getAttribute(CsrfToken.class.getName());
        if (csrf == null) {
            throw new IllegalStateException("CSRF token unavailable");
        }

        String action = request.getRequestURI()
            .substring(request.getContextPath().length());

        return """
            <!doctype html>
            <html lang="en">
            <head><meta charset="UTF-8"><title>Sign in</title></head>
            <body>
              <h1>Sign in</h1>
              <form method="post" action="%s">
                <input type="hidden" name="%s" value="%s">
                <label>Username
                  <input name="username" autocomplete="username">
                </label>
                <label>Password
                  <input name="password" type="password"
                         autocomplete="current-password">
                </label>
                <button type="submit">Sign in</button>
              </form>
            </body>
            </html>
            """.formatted(
                HtmlUtils.htmlEscape(action),
                HtmlUtils.htmlEscape(csrf.getParameterName()),
                HtmlUtils.htmlEscape(csrf.getToken()));
    }
}
```

The GET `/admin/login` form submits `POST /admin/login`, and the GET `/user/login` form submits `POST /user/login`. Both include CSRF, username, and password fields. Spring Security handles the POST and authenticates through the dedicated manager; the GET controller only renders the UI and never decides which accounts are valid. In a real application, use a template engine and separate UIs (especially for admin MFA), and never put passwords in URLs or JavaScript logs.

### 3.4. Sample Protected Resources

**`src/main/java/example/realms/RealmController.java`**

```java
package example.realms;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RealmController {

    @GetMapping("/admin/home")
    public String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }

    @GetMapping("/user/home")
    public String user(Authentication authentication) {
        return "user:" + authentication.getName();
    }

    @GetMapping("/svc/reports")
    public String reports(Authentication authentication) {
        return "service:" + authentication.getName();
    }
}
```

After admin login, `GET /admin/home` returns `admin:operator`. After user login, `GET /user/home` returns `user:alice`. With a service token having `sub=report-worker` and the right scope, `GET /svc/reports` returns `service:report-worker`. These are illustrative response bodies; in a real application, controllers should enforce business permissions per resource and tenant.

## 4. Why Should Service Accounts Use Client Credentials?

`client_credentials` is an OAuth 2.0 flow that issues an access token **directly to the client/workload** after the authorization server verifies it. There is no need for a browser, form login, `JSESSIONID`, user CSRF tokens, or default `ROLE_USER`/`ROLE_ADMIN` roles.

```text
report-worker
     |
     | client assertion / mTLS / client secret over HTTPS
     v
Authorization Server
     | verifies machine identity, policy, and scope
     '-- signs short-lived access token
              |
              v
report-worker sends:
Authorization: Bearer <access-token>
              |
              v
Resource Server: /svc/reports
     | JwtDecoder verifies signature, iss, aud, exp, nbf...
     | scope="reports.read" -> authority SCOPE_reports.read
     '-- GET allowed if scope matches
```

For JWTs, Spring Security maps verified `scope` or `scp` claims into authorities prefixed with `SCOPE_`. Thus `hasAuthority("SCOPE_reports.read")` has a different meaning from `hasRole("ADMIN")`. A token carrying the scope but having the wrong `iss`, wrong `aud`, expired timestamp, or invalid signature **must be rejected**—never merely parse JSON and trust claims.

In production, prefer strong client authentication such as private-key JWT, mTLS, or platform-appropriate workload identity; issue least-privilege scopes, short-lived tokens, rotate keys/secrets, and support revocation and per-client auditing. A service token meant for resource server A is not automatically valid on server B because it requires the proper audience.

**Never use a form-login “admin service user”** for background automation. Doing so mixes human and workload privileges, makes independent revocation/rotation difficult, and can bypass admin MFA or session controls.

## 5. Integration Testing with MockMvc

The test suite verifies chain routing, separate identity stores, and stateful/stateless boundaries. To run offline, a `@TestConfiguration` supplies a `JwtDecoder` returning JWT data only for **two predefined mock tokens**. This decoder performs no cryptographic verification and is only for testing the Resource Server filter and authorization after a `Jwt` is returned.

**`src/test/java/example/realms/RealmIsolationTest.java`**

```java
package example.realms;

import java.util.List;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RealmIsolationTest {
    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class FakeDecoderConfig {
        @Bean
        JwtDecoder jwtDecoder() {
            return raw -> {
                if (!raw.equals("test-service-token")
                        && !raw.equals("test-no-scope-token")) {
                    throw new BadJwtException("Unknown test token");
                }

                Jwt.Builder jwt = Jwt.withTokenValue(raw)
                    .header("alg", "RS256")
                    .claim("sub", "report-worker")
                    .claim("iss", "https://idp.example.test/realms/learning")
                    .claim("aud", List.of("https://api.example.test"));

                if (raw.equals("test-service-token")) {
                    jwt.claim("scope", "reports.read");
                }
                return jwt.build();
            };
        }
    }

    private MockHttpSession loginAdmin() throws Exception {
        MvcResult result = mvc.perform(post("/admin/login")
                .with(csrf())
                .param("username", "operator")
                .param("password", "operator-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/admin/home"))
            .andReturn();

        HttpSession session = result.getRequest().getSession(false);
        assertNotNull(session);
        return (MockHttpSession) session;
    }

    @Test
    void loginPagesContainCsrfFields() throws Exception {
        mvc.perform(get("/admin/login"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_HTML))
            .andExpect(content().string(containsString("name=\"_csrf\"")));

        mvc.perform(get("/user/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("action=\"/user/login\"")));
    }

    @Test
    void adminSessionCannotActAsUserSession() throws Exception {
        MockHttpSession session = loginAdmin();
        assertNotNull(session.getAttribute(SecurityConfig.ADMIN_CONTEXT));
        assertNull(session.getAttribute(SecurityConfig.USER_CONTEXT));

        mvc.perform(get("/admin/home").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:operator"));

        mvc.perform(get("/user/home").session(session))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/user/login"));
    }

    @Test
    void userSessionCannotActAsAdminSession() throws Exception {
        MvcResult result = mvc.perform(post("/user/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/user/home"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        assertNotNull(session.getAttribute(SecurityConfig.USER_CONTEXT));
        assertNull(session.getAttribute(SecurityConfig.ADMIN_CONTEXT));

        mvc.perform(get("/user/home").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("user:alice"));

        mvc.perform(get("/admin/home").session(session))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/admin/login"));
    }

    @Test
    void adminCredentialIsRejectedByUserLogin() throws Exception {
        mvc.perform(post("/user/login")
                .with(csrf())
                .param("username", "operator")
                .param("password", "operator-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/user/login?error"));
    }

    @Test
    void userCredentialIsRejectedByAdminLogin() throws Exception {
        mvc.perform(post("/admin/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/admin/login?error"));
    }

    @Test
    void twoContextKeysCanExistInSamePhysicalSession() throws Exception {
        MockHttpSession shared = loginAdmin();

        mvc.perform(post("/user/login")
                .session(shared)
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/user/home"));

        assertNotNull(shared.getAttribute(SecurityConfig.ADMIN_CONTEXT));
        assertNotNull(shared.getAttribute(SecurityConfig.USER_CONTEXT));

        mvc.perform(get("/admin/home").session(shared))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:operator"));

        mvc.perform(get("/user/home").session(shared))
            .andExpect(status().isOk())
            .andExpect(content().string("user:alice"));
    }

    @Test
    void browserCookieCannotAuthenticateServiceApi() throws Exception {
        MockHttpSession adminSession = loginAdmin();

        mvc.perform(get("/svc/reports").session(adminSession))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void serviceTokenWithScopeCanReadReport() throws Exception {
        mvc.perform(get("/svc/reports")
                .header("Authorization", "Bearer test-service-token"))
            .andExpect(status().isOk())
            .andExpect(content().string("service:report-worker"));
    }

    @Test
    void serviceTokenWithoutScopeGets403() throws Exception {
        mvc.perform(get("/svc/reports")
                .header("Authorization", "Bearer test-no-scope-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidServiceTokenGets401() throws Exception {
        mvc.perform(get("/svc/reports")
                .header("Authorization", "Bearer invalid"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void serviceBearerHeaderCannotAuthenticateAdminChain()
            throws Exception {
        mvc.perform(get("/admin/home")
                .header("Authorization", "Bearer test-service-token"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/admin/login"));
    }

    @Test
    void formLoginsRequireCsrf() throws Exception {
        mvc.perform(post("/admin/login")
                .param("username", "operator")
                .param("password", "operator-pass"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/user/login")
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().isForbidden());
    }
}
```

Run inside the application with the Gradle wrapper:

```bash
./gradlew test --tests example.realms.RealmIsolationTest
./gradlew bootRun
```

On Windows use `gradlew.bat`. The suite contains **12 `@Test` methods**. When running `bootRun` with a real Bearer JWT, update the example issuer/audience to an active token issuer. The tests use the fake decoder in `src/test` so routing and scope checks run without an IdP.

### Reading the Results Properly

- **Browser realms:** real logins via `POST` with CSRF; an admin session has `SECCTX_ADMIN` without `SECCTX_USER`, and vice versa. Accessing an unauthenticated realm redirects to **that realm's own** login page.
- **No credential mixing:** admin passwords sent to user login are still rejected because `appManager` does not contain `operator`. Two separate managers matter more than giving URLs different names.
- **Same session, still two contexts:** when admin and then user log in within the same `MockHttpSession`, both keys coexist while each chain still loads only its own key. This proves **logical context** separation, not independent physical cookies.
- **Stateless service:** the same browser cookie cannot satisfy `/svc/reports` because it requires a Bearer JWT. Requests without a token return `401`.
- **Service authorization:** a test JWT with the right scope returns `200`; missing scope returns `403`; a decoder-rejected token returns `401`. `401` means no accepted credentials; `403` means authenticated but lacking permissions.
- **No borrowing Bearer to enter admin:** the admin chain only has form authentication, with no bearer filter. An `Authorization: Bearer` header on an admin request does not make it an admin login.
- **Per-chain CSRF:** disabling CSRF in the service chain does not alter CSRF requirements for admin/user form logins.
- **Guarantee boundaries:** the test decoder does not verify signatures, issuers, audiences, expiration, or key rotation. Real integration tests with an actual IdP must cover validly signed tokens, invalid signatures, wrong issuer/audience, expired tokens, and not-yet-valid tokens.

## 6. Additional Policies to Truly Separate Risk

### Administrators

Admin form login uses a password in the example for learning simplicity. In production, require MFA or phishing-resistant authentication, step-up for high-privilege actions, short idle/absolute session timeouts, concurrent session management, dedicated reset/recovery policies, and auditing of privileged actions. Do not share cookies, session stores, or origins with the user portal when strong isolation is required. Every cookie-authenticated admin POST must be CSRF-protected. Restrict permissions per action rather than treating `ROLE_ADMIN` as an omnipotent permission.

### End Users

User login has its own policies for rate limiting, credential stuffing protection, account recovery, email/phone verification where appropriate, and cookie security. After authentication, resource authorization must also verify tenant, resource ownership, and business permissions. Never allow self-elevation from `REALM_USER` to `REALM_ADMIN` via client-controlled headers or claims.

### Service Accounts

Workloads need dedicated client IDs/identities, least-privilege token scopes, proper issuer/audience, exp/nbf, and key rotation. Never use an employee's email/password for cron jobs; never log access tokens; avoid very long-lived tokens; manage secrets via a secret manager or workload identity. When a service calls multiple APIs, issue tokens with the proper audience per API rather than a single all-powerful token. If using mTLS, manage certificate lifecycles and validate identity at connection acceptance.

### Logout and Permission Revocation

In the demo, the two repositories use distinct context keys but share the same `HttpSession`. Default logout for either admin or user can invalidate the whole session; if you need completely independent logout, choose separate sessions/origins or build a logout handler that inspects and clears only the targeted context with clear semantics. Removing an authority/role in the database **does not necessarily** update an active session immediately: define refresh, reauthentication, or session revocation rules. Likewise, a non-expired service JWT can continue being accepted per policy even if permissions changed at the IdP; consider short-lived tokens or appropriate introspection/revocation.

## 7. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Splitting only `/admin/login` and `/user/login` | May still share user store, manager, and context | Separate identity stores, managers, repositories, and authorization |
| Adding multiple chains without checking order | A broad chain catches requests before a specific chain | Explicit `@Order`, test URLs and fallback |
| `securityMatcher("/admin/**")` + form handled at `/login` | POST never enters the admin chain | Keep login processing URL inside the chain |
| Expecting Spring Security to generate the page after `loginPage(custom)` | GET login returns 404 | Provide GET HTML form and CSRF token |
| Using only `anyRequest().authenticated()` for admin | Valid identities from another realm might be accepted if context is shared | Enforce both realm and role with the right repository |
| Sharing `SPRING_SECURITY_CONTEXT` across two realms | Accidental reuse of Authentication | Use repositories with separate keys or separate physical sessions |
| Assuming two context keys mean two cookies | Compromising one cookie affects both | Separate origin/cookie/store for true isolation |
| Enabling form/httpBasic on a service API | Workloads might use human accounts or browsers might send cookies | Stateless JWT bearer/mTLS with scopes |
| Parsing JWT without verifying its signature | Clients can forge scope/admin claims | Let JwtDecoder verify cryptographic signature, iss/aud/time |
| Using `hasRole("ADMIN")` for services | Mixes human and machine permission namespaces | Use `SCOPE_*` for services; separate roles |
| Testing only with a fake decoder and assuming production JWTs are safe | Issuer/audience/signature untested | Real E2E/integration tests with an IdP and invalid tokens |
| No fallback chain | New URLs can bypass Spring Security | Catch-all `denyAll` |
| Leaving secrets, cookies, or tokens in logs | Credential leakage | Redaction, audit metadata, and secret rotation |
| Revoking roles in DB without considering live sessions/JWTs | Old privileges may persist until expiration | Define refresh/revoke/step-up policies |
| Assuming admin login suffices for ultra-sensitive operations | Compromised credentials can modify the system | MFA, step-up, action controls, and auditing |

## 8. Completion Checklist

- [ ] Requests to `/admin/**`, `/user/**`, `/svc/**` select the right chain in order.
- [ ] Both form logins have a GET page, POST processing URL, and CSRF token within the matcher.
- [ ] Admin and user use separate authentication managers and identity stores; no cross-credential login.
- [ ] Admin endpoints require `REALM_ADMIN` + `ROLE_ADMIN`; user endpoints require `REALM_USER` + `ROLE_USER`.
- [ ] Admin/user contexts are stored under separate keys; tested for both access and shared `HttpSession` scenarios.
- [ ] Isolation limits of sharing a cookie/session are understood; appropriate logout, timeout, session fixation, and physical isolation policies are in place.
- [ ] Service API authenticates Bearer JWTs without browser cookies or form login.
- [ ] JWTs have signature, issuer, audience, expiry, and scopes verified from a trusted source; real integration tests exist beyond mock tests.
- [ ] Scope `reports.read` maps to `SCOPE_reports.read`, distinct from human roles.
- [ ] Missing token returns `401`, valid token missing scope returns `403`, unauthenticated form access redirects to its respective login.
- [ ] Fallback chain denies undeclared endpoints.
- [ ] Production admin requires MFA/step-up, monitoring, and auditing; service tokens have rotation/revocation and least privilege.

### Official Documentation

- [Spring Security 6.5 — Multiple HttpSecurity, securityMatcher and login endpoints](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security — FilterChainProxy and multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security — Authentication Architecture / ProviderManager](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [HttpSessionSecurityContextRepository — setSpringSecurityContextKey](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth2 Client Credentials](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/index.html)
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
