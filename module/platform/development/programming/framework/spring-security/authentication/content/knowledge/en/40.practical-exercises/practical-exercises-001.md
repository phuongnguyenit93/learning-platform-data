# Hands-on Practice: Build Form Login with In-Memory Accounts, Then Migrate to a Database Store

## 1. Practice Objectives and Final Deliverable

This hands-on exercise builds **HTML form login** for a Spring Boot application, starting with two accounts stored in RAM via `InMemoryUserDetailsManager`, then **swapping only the account source** to `JdbcUserDetailsManager` and an H2 database. Users still log in at the same URL, using the same HTML template, the same authorization rules, and the same session/CSRF mechanisms; the change is isolated to **storing and retrieving UserDetails**. After testing the H2 version, the guide outlines how to transition the architecture to a real database with migrations, a secret manager, unique constraints, and safe operations.

Reference environment: **Java 17+, Spring Boot 3.x, Spring Security 6.x (preferring 6.5 APIs), Spring MVC/Servlet, Gradle**, Thymeleaf, JDBC, H2 for the local demo, and JUnit 5/MockMvc. Do not mix Servlet `HttpSecurity` snippets with WebFlux `ServerHttpSecurity`. Choose a Spring Boot 3.x line compatible with Spring Security 6.x per the BOM; do not manually force a spring-security version unmanaged by Boot.

Upon completion:

- Visiting `GET /login` displays a custom HTML form, and `POST /login` is handled by Spring Security's filter (no controller written to verify passwords manually).
- Alice with `ROLE_USER` can log in and view `/dashboard`, but is denied at `/admin`; Admin with `ROLE_ADMIN` can view both.
- Passwords are encoded with `BCryptPasswordEncoder`; no plain text is stored in the database. `PasswordEncoder.matches`/`DaoAuthenticationProvider` handles matching, not the controller.
- Logging in with a missing/wrong password does not create an authenticated principal; CSRF protection is kept on login/logout forms.
- Run the `memory` profile to use `InMemoryUserDetailsManager`, then switch to the `jdbc` profile to use the `users` + `authorities` schema and `JdbcUserDetailsManager` without changing controllers, templates, or authorization rules.
- Have an HTTP test suite using `MockMvc` for both profiles and a JDBC data verification suite; understand the limitations of in-memory H2 and the path to real PostgreSQL/MySQL.

**Important:** the examples contain public usernames/passwords intended only for local learning. Do not deploy these fixtures to the internet, do not expose the H2 Console publicly, and do not log passwords, headers, or session cookies. For a real application, create users through a verified registration flow, password reset/lockout/rate-limiting, MFA policies, and auditing.

## 2. Architecture: Swap UserDetailsService, Keep the Protection Points Unchanged

Main flow:

```text
Browser
  GET /dashboard (not logged in)
       |
       v
Spring Security AuthorizationFilter
  -> requires authentication
  -> LoginUrlAuthenticationEntryPoint
  -> 302 Location: /login
       |
       v
GET /login -> Controller -> Thymeleaf login.html
       |
       | POST /login {username, password, _csrf}
       v
UsernamePasswordAuthenticationFilter
       |
       v
AuthenticationManager / DaoAuthenticationProvider
       | 1. loadUserByUsername(username)
       v
UserDetailsService ----------------------+
   |                                    |
   | profile=memory                      | profile=jdbc
   v                                    v
InMemoryUserDetailsManager       JdbcUserDetailsManager
   |                                    |
   | Java objects in RAM                | DataSource / SQL
   |                                    | tables users, authorities
   +-----------------+------------------+
                     |
                     v
             UserDetails(username, encoded password,
                         enabled, authorities)
                     |
                     v
       PasswordEncoder.matches(raw, encoded)
                     |
             +-------+--------+
             |                |
           SUCCESS          FAILURE
             |                |
      SecurityContext    Clear/fail auth
      session strategy   redirect /login?error
             |
      302 /dashboard
             |
      /admin -> hasRole("ADMIN") -> 200 or 403
```

**Separation of responsibilities:**

| Component | Role | Should Not Do |
| --- | --- | --- |
| `SecurityFilterChain` | Protect URLs, enable form login/CSRF/logout/session | Contain SQL queries for users directly |
| `UsernamePasswordAuthenticationFilter` | Read `username/password` fields from POST /login | Let a controller manually create an authenticated token per request |
| `DaoAuthenticationProvider` | Fetch UserDetails, verify password hash and account status | Compare raw passwords using `String.equals` |
| `UserDetailsService` | Load account, authorities, and status | Accept raw passwords or return arbitrary accounts |
| `InMemoryUserDetailsManager` | Look up/manage users within a single JVM | Be treated as a persistent production account store |
| `JdbcUserDetailsManager` | Look up/manage users in a relational database | Be assumed to understand arbitrary custom/tenant JPA schemas |
| `PasswordEncoder` | Hash and verify passwords | Store `{noop}`/raw passwords in production |
| `SecurityContextRepository`/HttpSession | Maintain authenticated state across requests | Automatically revoke all JWT/refresh tokens at an IdP |
| `@Controller`/Thymeleaf | Render login/dashboard pages and messages | Query the DB directly to compare passwords on `POST /login` |

A user existing in the DB **does not automatically mean login succeeds**: the provider also checks the password, `enabled`, and other authentication policies. A user logging in successfully **does not automatically mean they have ROLE_ADMIN**: authorization is checked separately.

## 3. Create the Project, Dependencies, and Directory Structure

Use Spring Initializr to create **Spring Boot 3.x**, Gradle Groovy, Java 17, with dependencies:

- Spring Web (Servlet MVC), Spring Security;
- Thymeleaf;
- Spring JDBC and H2 Database for the data store exercise;
- Spring Boot Test + Spring Security Test.

If you already have the Gradle wrapper and Spring Boot plugin, the equivalent dependencies block is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

You do not need to specify versions manually for the dependencies above if the Spring Boot BOM manages them. Expected file structure:

```text
src/
  main/
    java/com/example/formlogin/
      FormLoginApplication.java
      SecurityConfig.java
      PageController.java
    resources/
      application.yml
      application-jdbc.yml
      schema-jdbc.sql
      templates/
        login.html
        dashboard.html
        admin.html
  test/java/com/example/formlogin/
      FormLoginMemoryTest.java
      FormLoginJdbcTest.java
```

**Note on the two profiles:** `memory` and `jdbc` are **mutually exclusive** modes. Do not run `--spring.profiles.active=memory,jdbc`, as that creates two beans providing `UserDetailsService` and makes provider/seeding selection ambiguous. When running without selecting a profile, the example app cannot be assumed to have selected the intended account store; always specify one profile and verify the actual bean created. `jdbc` in this exercise uses in-memory H2 **for demo purposes only**, not a real database configuration.

## 4. Create the Application Entry Point Class

File `src/main/java/com/example/formlogin/FormLoginApplication.java`:

```java
package com.example.formlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormLoginApplication.class, args);
    }
}
```

Place the remaining classes in the same `com.example.formlogin` package so component scanning finds `@Configuration` and `@Controller`. If you separate packages, ensure they sit under the base package of `@SpringBootApplication` or configure scanning explicitly.

## 5. Write SecurityFilterChain: One Shared Policy for Memory and JDBC

File `src/main/java/com/example/formlogin/SecurityConfig.java`:

```java
package com.example.formlogin;

import javax.sql.DataSource;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/css/**").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .failureUrl("/login?error")
                .defaultSuccessUrl("/dashboard", false)
                .permitAll())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .permitAll())
            // Do not disable CSRF; Spring Security keeps CSRF protection enabled.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    @Profile("memory")
    UserDetailsService memoryUsers(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();
        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    @Profile("jdbc")
    JdbcUserDetailsManager jdbcUsers(DataSource dataSource) {
        return new JdbcUserDetailsManager(dataSource);
    }

    @Bean
    @Profile("jdbc")
    CommandLineRunner seedJdbcDemoUsers(
            JdbcUserDetailsManager users, PasswordEncoder encoder) {
        return args -> {
            if (!users.userExists("alice")) {
                users.createUser(User.withUsername("alice")
                    .password(encoder.encode("alice-pass"))
                    .roles("USER")
                    .build());
            }
            if (!users.userExists("admin")) {
                users.createUser(User.withUsername("admin")
                    .password(encoder.encode("admin-pass"))
                    .roles("USER", "ADMIN")
                    .build());
            }
        };
    }
}
```

This is the **complete demo configuration**, with mandatory notes:

1. The `@Bean` methods under the two different `@Profile` annotations create **one UserDetails source per run**. `JdbcUserDetailsManager` implements `UserDetailsService`/`UserDetailsManager`, so Spring's authentication layer still uses `DaoAuthenticationProvider` just like the in-memory case.
2. `PasswordEncoder` uses BCrypt; each run of the `memory` profile may generate a different salt/hash, yet `PasswordEncoder.matches("alice-pass", storedHash)` still succeeds. **Never compare two BCrypt hashes with equals**, because their salts differ.
3. In `.roles("USER")`, Spring creates `ROLE_USER`. `.hasRole("ADMIN")` requires the `ROLE_ADMIN` authority. When using JDBC, the `authorities.authority` column must store the **full name** such as `ROLE_ADMIN`.
4. Form Login handles **POST /login**, so our controller only provides **GET /login**. Do not create another POST mapping claiming this URL or manually compare username/password.
5. `defaultSuccessUrl("/dashboard", false)` means dashboard is used as the default target, though if the user was originally redirected while accessing a protected URL, Spring Security may prioritize the saved request. Therefore, do not assert that every successful login always redirects strictly to dashboard when RequestCache is active.
6. `invalidateHttpSession(true)` handles logging out the current session; it does not automatically log out all devices, revoke remember-me cookies depending on configuration, or revoke OAuth access/refresh tokens. This example has neither remember-me nor OAuth2 enabled.
7. `seedJdbcDemoUsers` is only for immediate local execution. **Do not keep code that auto-creates accounts with public passwords in production**; a real system uses controlled migrations/provisioning, account enrollment, and secret management.
8. When a single `UserDetailsService` bean and a `PasswordEncoder` are present, Spring Security configures authentication based on those beans for standard username/password cases. If a project defines a custom AuthenticationProvider/AuthenticationManager, verify the actual provider setup rather than assuming auto-configuration always picks the right bean.

### Do Not Confuse UserDetailsService with UserDetailsManager

`UserDetailsService` only promises the `loadUserByUsername(String)` method. `InMemoryUserDetailsManager` and `JdbcUserDetailsManager` also provide user management capabilities (create/update/delete) via `UserDetailsManager`. That is why the JDBC seeding code calls `users.createUser(...)`, while login only needs UserDetailsService. In production, never expose full user creation capabilities on public endpoints by unconditionally injecting `UserDetailsManager`.

## 6. Write the Controller: HTML Pages Without Touching POST /login

File `src/main/java/com/example/formlogin/PageController.java`:

```java
package com.example.formlogin;

import java.security.Principal;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/")
    public String home() {
        return "redirect:/dashboard";
    }

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/dashboard")
    public String dashboard(Principal principal, Model model) {
        model.addAttribute("username", principal.getName());
        return "dashboard";
    }

    @GetMapping("/admin")
    public String admin(Principal principal, Model model) {
        model.addAttribute("username", principal.getName());
        return "admin";
    }
}
```

Because `/dashboard` and `/admin` are protected by the security chain, the code only calls `principal.getName()` after Spring Security grants access. In complex applications, never read a username from a query parameter and trust it as the principal. Permissions on individual objects/resources must also be checked at the service layer, not just at the URL layer.

**There is no POST /login controller** in the sample project. Login requests are processed by `UsernamePasswordAuthenticationFilter`. If you see a POST /login controller being invoked to query passwords manually, your filter chain/path may be misconfigured or your code may be bypassing Spring Security.

## 7. Create Thymeleaf Forms with Proper CSRF and Field Names

### 7.1. templates/login.html

File `src/main/resources/templates/login.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign In</title>
</head>
<body>
    <h1>Sign In</h1>

    <p th:if="${param.error}">
        Invalid username or password.
    </p>
    <p th:if="${param.logout}">
        You have been logged out.
    </p>

    <form th:action="@{/login}" method="post">
        <label for="username">Username</label>
        <input id="username" name="username" type="text"
               autocomplete="username" required>

        <label for="password">Password</label>
        <input id="password" name="password" type="password"
               autocomplete="current-password" required>

        <button type="submit">Sign In</button>
    </form>
</body>
</html>
```

**Details to verify:**

- `th:action="@{/login}"` resolves the context path properly and works with Spring MVC/Thymeleaf to inject a CSRF hidden input into the POST form when Security and CSRF integration are properly configured. Inspect the rendered HTML to confirm the `_csrf` field is present. Without it, POST requests are rejected by the Spring CSRF filter with **403**, not invalid-password errors.
- The exact default parameter names are `username` and `password`. If you rename the inputs, you must update `usernameParameter(...)`/`passwordParameter(...)` accordingly in the config.
- `th:if="${param.error}"` displays a generic message without stating "user does not exist" or "user exists but password is wrong" to prevent username enumeration. You also need rate limiting, backoff, monitoring, and risk-based MFA; a generic message **does not prevent brute force on its own**.
- Never put passwords into GET queries, localStorage, or hidden fields. `autocomplete="current-password"` allows password managers to work properly; do not disable password copy/paste unnecessarily.
- HTML templates live in `resources/templates` so Thymeleaf renders them. Placing the file in static without a controller may cause `/login` to 404 or break expected CSRF integration.

### 7.2. templates/dashboard.html

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Dashboard</title></head>
<body>
    <h1>Personal Dashboard</h1>
    <p>Hello <strong th:text="${username}">user</strong></p>

    <a th:href="@{/admin}">Admin Page</a>

    <form th:action="@{/logout}" method="post">
        <button type="submit">Log Out</button>
    </form>
</body>
</html>
```

`th:text` escapes input data as plain text, reducing XSS risk when displaying the username. Never use `th:utext` for untrusted data. The logout form uses **POST** with CSRF instead of a state-changing GET link. Never disable CSRF just to allow GET logout in an application using cookie-based sessions.

### 7.3. templates/admin.html

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Administration</title></head>
<body>
    <h1>Admin Page</h1>
    <p>Account: <span th:text="${username}">admin</span></p>
    <a th:href="@{/dashboard}">Back to dashboard</a>
</body>
</html>
```

Having the `/admin` link in the template does not mean Alice is authorized to access it. The server checks `hasRole("ADMIN")`; unauthorized users receive 403. **Hiding menus or links in the UI is not authorization**.

## 8. Run 1: In-Memory Accounts

Run from the project directory containing the Gradle wrapper:

```bash
./gradlew bootRun --args='--spring.profiles.active=memory'
```

On Windows PowerShell/cmd you can use:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=memory"
```

Open `http://localhost:8080/login` **on your local machine**. Real deployments must use HTTPS; HTTP on localhost is strictly for lab work. Test accounts:

| Account | Demo Password | Authorities | Behavior |
| --- | --- | --- | --- |
| `alice` | `alice-pass` | `ROLE_USER` | Login → dashboard; GET /admin → 403 |
| `admin` | `admin-pass` | `ROLE_USER` and `ROLE_ADMIN` | Login → dashboard; GET /admin → 200 |
| `ghost` | any | Does not exist | Login fails → /login?error page |
| `alice` | wrong password | Account exists | Login fails, not authenticated |

Browser walkthrough:

1. In an incognito window, open `/dashboard` directly. If not logged in, Spring Security redirects `302` to `/login`. The login page itself renders `200`, not a successful dashboard.
2. Log in as `alice/alice-pass` via the form; after the redirect, the dashboard page displays "Hello alice".
3. Open `/admin`: expect 403 due to missing `ROLE_ADMIN`. That is an authorization error, **not** a wrong password.
4. POST logout using the button on the dashboard page. Afterward, visiting `/dashboard` must require a fresh login.
5. Log in as `admin/admin-pass`, open `/admin`, and see the admin page.
6. In a separate window, enter `ghost`/wrong password. Verify there is no authenticated access and the message does not reveal whether the user exists.

**Real verification:** inspect the Network tab to observe POST /login (CSRF), status 302, Set-Cookie session, and the redirect target. If DevTools only shows 200 on the final page because it follows redirects automatically, do not conclude that POST returned 200.

### Characteristics of In-Memory Storage

`InMemoryUserDetailsManager` stores accounts inside a single JVM. On every restart, the bean recreates the two accounts from code; if you add an account at runtime without writing to a persistent store, that account disappears after a restart. Two pods each have separate memory and do not share users automatically; changing a password or disabling a user on pod A will not be visible to pod B. This is why a real database or identity store is needed for production.

## 9. MockMvc for the Memory Profile: Testing Authentication, Authorization, and CSRF

Create `src/test/java/com/example/formlogin/FormLoginMemoryTest.java`:

```java
package com.example.formlogin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("memory")
class FormLoginMemoryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginPageIsPublic() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk());
    }

    @Test
    void aliceCanAuthenticate() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("alice"))
                .andExpect(redirectedUrl("/dashboard"));
    }

    @Test
    void nonexistentAccountDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "ghost")
                    .param("password", "irrelevant"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(unauthenticated());
    }

    @Test
    void missingCsrfIsRejectedBeforePasswordCheck() throws Exception {
        mvc.perform(post("/login")
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(status().isForbidden());
    }

    @Test
    void aliceCannotAccessAdminButCanSeeDashboard() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk());
        mvc.perform(get("/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenAdminPage() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "admin")
                    .param("password", "admin-pass"))
                .andExpect(authenticated().withUsername("admin"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();
        mvc.perform(get("/admin").session(session))
                .andExpect(status().isOk());
    }

    @Test
    void logoutInvalidatesCurrentSession() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(authenticated())
                .andReturn();
        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);

        mvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection());

        assertThat(session.isInvalid()).isTrue();
    }
}
```

Run:

```bash
./gradlew test --tests com.example.formlogin.FormLoginMemoryTest
```

**What is the value of these tests?** `post("/login").with(csrf())` sends the request through the real login filter and PasswordEncoder without fabricating a mock principal. `SecurityMockMvcResultMatchers.authenticated()` verifies the Spring Security Context after the request; `get("/admin").session(session)` verifies session usage on subsequent requests, not just the HTTP 302 from login.

**Limitations:** MockMvc uses a mock servlet environment and does not prove real cookies or production reverse proxy/session stores. Add browser/E2E tests for `Set-Cookie`, HTTPS, session fixation, idle timeout, and concurrent sessions. In applications with RequestCache/saved requests or a custom success handler, the expected redirect target may differ, so you must assert according to your chosen configuration.

### Note on Mock Authentication

`@WithMockUser` is useful for testing controller/role policies, but it **does not invoke** `InMemoryUserDetailsManager`, does not verify passwords, and does not go through `POST /login`. Never use a `@WithMockUser(roles="ADMIN")` test to claim you proved database login works. To test authentication, submit real credentials through the provider and observe the resulting session/principal.

## 10. Run 2: Replace InMemoryUserDetailsManager with JDBC

At this stage, **do not change** `PageController`, `SecurityFilterChain`, the three templates, or any URLs. We add the schema and run the `jdbc` profile so the `jdbcUsers(DataSource)` bean replaces the `memoryUsers(...)` bean. That is the essence of "migrating to a database store": swapping the account lookup provider while **keeping the authentication protocol and authorization policy consistent**.

### 10.1. Default SQL Schema for JdbcUserDetailsManager

File `src/main/resources/schema-jdbc.sql`:

```sql
CREATE TABLE users (
    username VARCHAR(50) NOT NULL PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_authorities_user
        FOREIGN KEY (username) REFERENCES users(username),
    CONSTRAINT uk_user_authority
        UNIQUE (username, authority)
);
```

This schema matches the **default queries** of `JdbcUserDetailsManager`/`JdbcDaoImpl`:

```sql
SELECT username, password, enabled
FROM users
WHERE username = ?;

SELECT username, authority
FROM authorities
WHERE username = ?;
```

Never build queries by concatenating the username into SQL strings; use parameter binding via JDBC. The `password` column holds passwords encoded with PasswordEncoder, not raw text; `authority` holds `ROLE_USER`, `ROLE_ADMIN`. The UNIQUE constraint prevents duplicate identical authorities, and the foreign key prevents orphaned roles. Depending on the database and collation, `alice` and `Alice` may compare differently; production must enforce a normalized identity policy and unique keys per tenant/account.

**Note:** the standard Spring Security schema in official docs often uses `varchar_ignorecase` for HSQL/H2; the SQL above uses more readable/portable types for H2 to illustrate the contract, but when porting to PostgreSQL/MySQL you must adjust DDL/constraints for the target RDBMS. This is not a complete migration set for a production system with lockout/MFA/auditing.

### 10.2. application-jdbc.yml for Local H2

File `src/main/resources/application-jdbc.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:formlogin-demo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
      schema-locations: classpath:schema-jdbc.sql
```

When the `jdbc` profile is active, Spring Boot creates an in-memory H2 datasource and executes the SQL schema before the CommandLineRunner seeds users in `SecurityConfig`. `JdbcUserDetailsManager.createUser(...)` inserts into `users`/`authorities` via SQL; BCrypt password hashing with salt happens in Java during seeding.

**Do not put the application-jdbc.yml above into production as a real database configuration.** H2 `mem:` only lives for the lifetime of the process; data is lost on restart. `spring.sql.init.mode=always` runs schema DDL on every startup, which can fail or break migration workflows on an existing DB. Production uses a real datasource and Flyway/Liquibase with versioned migrations, **never auto-creating schemas and seeding demo accounts on startup**.

### 10.3. Start with the JDBC Profile

```bash
./gradlew bootRun --args='--spring.profiles.active=jdbc'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=jdbc"
```

Expected result: both Alice and Admin still log in via the form just as before:

- Alice logs in → dashboard 200; admin route 403.
- Admin logs in → admin route 200.
- Ghost user / wrong password are still rejected.
- CSRF/logout/session behavior is unchanged.
- Restarting the in-memory H2 app recreates the schema and re-seeds both users; this proves it uses an in-memory DB rather than persistence across restarts.

This is a **useful regression test**: changing the user store must not break login routes, role mapping, CSRF, or session behavior.

## 11. JDBC Tests: Verify Data and Re-Run the Same HTTP Logins

Create `src/test/java/com/example/formlogin/FormLoginJdbcTest.java`:

```java
package com.example.formlogin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("jdbc")
class FormLoginJdbcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    JdbcUserDetailsManager users;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void jdbcUsersExistAndPasswordIsHashed() {
        assertThat(users.userExists("alice")).isTrue();
        assertThat(users.userExists("admin")).isTrue();
        assertThat(users.userExists("ghost")).isFalse();

        UserDetails alice = users.loadUserByUsername("alice");
        assertThat(alice.getPassword()).isNotEqualTo("alice-pass");
        assertThat(encoder.matches(
                "alice-pass", alice.getPassword())).isTrue();
        assertThat(alice.getAuthorities().stream()
                .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())))
                .isTrue();

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM users WHERE username = ?",
                Integer.class, "alice");
        assertThat(rows).isEqualTo(1);
    }

    @Test
    void jdbcLoginStillUsesSameFormAndRules() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk());
        mvc.perform(get("/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void jdbcAdminHasAdminRole() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "admin")
                    .param("password", "admin-pass"))
                .andExpect(authenticated().withUsername("admin"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/admin").session(session))
                .andExpect(status().isOk());
    }

    @Test
    void jdbcMissingUserAndWrongPasswordFail() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "ghost")
                    .param("password", "any"))
                .andExpect(unauthenticated());

        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "wrong"))
                .andExpect(unauthenticated());
    }

    @Test
    void jdbcLoginStillRequiresCsrf() throws Exception {
        mvc.perform(post("/login")
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(status().isForbidden());
    }
}
```

Run tests for both profiles:

```bash
./gradlew test --tests com.example.formlogin.FormLoginMemoryTest
./gradlew test --tests com.example.formlogin.FormLoginJdbcTest
```

Or run all tests in a single command:

```bash
./gradlew test
```

**Testing focus:** you must prove that after switching from in-memory to JDBC, accounts are **actually loaded from the DB**, the password hash verifies with PasswordEncoder, and `ROLE_ADMIN` is preserved. Having the controller return 200 is insufficient, because the app could still accidentally be using an in-memory bean left on the classpath.

**Regarding SQL:** `JdbcTemplate.queryForObject(..., "alice")` uses parameter binding; never build SQL by concatenating username values into strings. Testing `users.userExists("ghost")` does not prove that public login hides user existence against timing/error-message leaks; add security/penetration tests per policy.

### Catching a Provider Running "Silently"

If Spring Boot auto-configures a generated user or a custom AuthenticationProvider not scoped by profile, HTTP tests may pass or fail unexpectedly. Assert that the context has the `JdbcUserDetailsManager` bean in the `jdbc` profile and **no in-memory UserDetailsService** loaded; and vice versa in the `memory` profile. Check startup logs for a generated security password notice, which signals that your intended users bean was not registered properly.

## 12. Crucial Differences Between the H2 Demo and a Production Data Store

| Aspect | `memory` | `jdbc` H2 in-memory in lab | Production RDBMS |
| --- | --- | --- | --- |
| Where do accounts live? | JVM Heap | In-process H2 engine | PostgreSQL/MySQL/Oracle or managed DB |
| Service restart | Recreated from code | Schema recreated and demo seeded | Data must persist across restarts/deploys |
| Multi-node sharing | No | No, unless using discouraged external H2 service | Yes, shared DB and safe connection pool |
| Passwords | BCrypt in UserDetails | BCrypt hash in `users.password` | BCrypt/Argon2/DelegatingEncoder with migration policy |
| Roles | In Java fixtures | `authorities` table | Standard role/permission tables, scope/tenant if needed |
| Schema changes | Code changes | `schema-jdbc.sql` every startup | Flyway/Liquibase versioned migrations |
| Account locking/MFA | Must be built manually | Default schema only has `enabled` | Needs extended model or provider checks |
| Backup/DR | None | Not like a persistent DB | Backup, restore, audit, encryption-at-rest |
| Secret management | Demo passwords in code | Demo passwords in CommandLineRunner | Secret manager, enrollment, reset/recovery |
| Session persistence | Separate default HttpSession | Still separate HttpSession, **not in users DB** | Needs dedicated Spring Session for cross-node sharing/revocation |

**Moving users to a DB does not automatically move HTTP sessions to the DB.** Authentication state in `SecurityContext`/HttpSession has its own lifecycle; if running multiple server replicas and needing shared sessions, consider Spring Session with Redis/JDBC. Do not conflate the `users`/`authorities` tables with Spring Session's session storage tables.

### Limitations of Default JdbcUserDetailsManager

The default schema only has `users.username`, `password`, `enabled`, and `authorities`. It cannot fully represent tenants, `locked-until` timestamps, password rotation history, MFA credentials, email verification, or arbitrary account statuses. When a richer domain model is needed, you can write a custom `UserDetailsService` backed by repositories/JPA while **keeping the `loadUserByUsername` contract** and letting DaoAuthenticationProvider/PasswordEncoder verify passwords. Never read roles directly from the request.

## 13. Migrating to Real PostgreSQL/MySQL: Safe Step-by-Step Guide

This section describes a **production workflow**, not files to drop directly into the H2 demo project. It clarifies what must be completed before you can call the system "migrated to a database store".

### 13.1. Use Versioned Migrations, Never Seed Plaintext from Code

1. Provision a dedicated RDBMS per environment and a service account with least-privilege permissions. Enable TLS for connections, separate read/write/migration privileges where possible, and test backup/restore.
2. Create DDL with **Flyway/Liquibase** in `db/migration/V1__create_auth_tables.sql` matching your project's dialect and user/authority schema; include clear indexes/unique constraints, foreign keys, and a username normalization policy.
3. Set `spring.sql.init.mode=never` in production when Flyway/Liquibase manages migrations; do not run `schema-jdbc.sql` with `CREATE TABLE` on every restart. Never enable the H2 console in production.
4. Remove the `seedJdbcDemoUsers(...)` bean or restrict it to local/test profiles only. Real accounts are created via admin registration workflows, password reset/email verification, IdP provisioning, IAM, or audited migration jobs.
5. Supply DB connection credentials via a secret manager/environment variables (never commit `spring.datasource.password` to Git). Rotate DB passwords per runbook and never log URLs containing secrets.
6. Configure connection pools and safe timeouts; DB failures must never cause login to **fail-open** (granting a guest/default user) or fall back to in-memory accounts.
7. Test migrations on an anonymized data snapshot, then canary the service; cut over only once data, roles, and password encoders are all verified.
8. Bounded rollback: backup/schema compatibility and a change plan, never "rolling back" by reverting to hardcoded admin credentials.

**Illustrative configuration example** for a PostgreSQL production environment (requires adding a JDBC driver and Flyway dependencies compatible with the BOM):

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal.example:5432/authdb
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  sql:
    init:
      mode: never
  flyway:
    enabled: true
```

**This snippet is not sufficient to run production:** it still requires the PostgreSQL driver, schema migrations, TLS/truststore, datasource permissions, startup readiness, rate limiting, metrics, and a secret management environment. Hostname `db.internal.example` is illustrative only. Boot only configures Flyway when the dependency and matching schema/migrations exist. In particular, the lab's `@Profile("jdbc")` bean includes a CommandLineRunner seeder: **do not activate that `jdbc` profile as-is in production**; create a separate profile/config for the real environment and remove the seeding code. If you share the same class, adjust `@Profile` explicitly so only one UserDetailsService is active and no demo users are created.

### 13.2. Password Migration Must Preserve Verification Capability

- When **compatible password hashes already exist**, migrate the **hashes** and metadata/algorithm IDs according to policy; plaintext is not needed. Never call `encoder.encode(existingHash)`, because that re-hashes the hash as a new password and locks users out of their old passwords.
- If using `DelegatingPasswordEncoder`, stored values can carry a prefix like `{bcrypt}...` to select the right encoder. This demo uses `BCryptPasswordEncoder` directly, so database hashes do not need a prefix; **do not arbitrarily add `{bcrypt}` and continue using BCryptPasswordEncoder directly if that code does not understand prefixes**.
- If legacy weak algorithms (MD5/SHA-1/legacy) were used, consider a staged upgrade at login using a policy-approved legacy-supporting encoder, forced password reset, or controlled migration. Never skip verification or accept plaintext due to "hash mismatch".
- Never derive new users/roles from request headers or DB folder names. Keep immutable account IDs/tenant mappings and UNIQUE constraints; migrations must catch duplicate/colliding usernames caused by lowercase/Unicode collation.
- Verify disabled, locked, account-expired, credentials-expired, MFA, and existing role states. Do not retain `ROLE_ADMIN` for a user whose access was revoked just because of stale migration data.

### 13.3. Zero-Downtime Cutover and Split-Brain Risks

Suppose the system currently holds in-memory accounts across multiple JVMs and needs to move to a DB:

1. Inventory all current accounts, roles, and account states; establish the **source of truth** and version at cutover time.
2. Backfill the DB via a job that checks counts/hashes/uniqueness/roles; *never* backfill plaintext passwords through logs.
3. Run authentication tests **in an isolated environment** against an appropriate DB copy; do not accept a hardcoded admin fallback account.
4. Deploy the JDBC build to a canary group; all requests after cutover must use **the same user store**. If A still uses memory while B uses the DB, password changes or disables will behave inconsistently across pods.
5. If temporary dual-read is required, explicitly design: source priority, conflict resolution, stable IDs, consistency, timeouts, and **no fail-open on DB errors**. For simple setups, perform a single cutover once the DB is verified.
6. Measure login success/failure ratios, UserDetailsService query latency, password mismatches, account lockouts, role mappings, session persistence, and login form error rates.
7. Maintain a tested rollback plan (database snapshot/version, app compatibility, incident criteria). **Never** revert to hardcoded passwords or leave two stores running in parallel without strict control.

## 14. Test Matrix from Memory to JDBC and Production

| ID | Stage | Scenario | Expected Result |
| --- | --- | --- | --- |
| M01 | Memory | GET /login anonymous | 200 HTML form |
| M02 | Memory | GET /dashboard anonymous | 302 to login |
| M03 | Memory | POST /login Alice valid + CSRF | Authenticated Alice, expected redirect |
| M04 | Memory | POST /login Alice invalid | Not authenticated |
| M05 | Memory | POST /login ghost | Not authenticated, does not leak user existence |
| M06 | Memory | POST /login without CSRF | 403, login does not succeed |
| M07 | Memory | GET /admin logged in as Alice | 403 role denied |
| M08 | Memory | GET /admin logged in as Admin | 200 |
| M09 | Memory | POST /logout + CSRF | Session invalidated |
| M10 | Memory | Access /dashboard with logged-out session | No longer authenticated |
| D01 | JDBC | Schema users/authorities created properly | Tables, indexes, FKs exist |
| D02 | JDBC | Alice has password hash | Encoder.matches(raw, hash) returns true |
| D03 | JDBC | JdbcUserDetailsManager.loadUserByUsername("alice") | Principal Alice, ROLE_USER |
| D04 | JDBC | Username "ghost" | UsernameNotFoundException in service, login fails in provider |
| D05 | JDBC | Alice wrong password | Authentication fails |
| D06 | JDBC | Admin ROLE_ADMIN | Can access /admin |
| D07 | JDBC | Alice ROLE_USER | Receives 403 at /admin |
| D08 | JDBC | Missing CSRF | 403 on POST login/logout |
| D09 | JDBC | Restart H2 mem app | Demo accounts re-seeded, not mistaken for persistence |
| D10 | JDBC | Missing/duplicate role | Never accidentally grants admin; unique key works |
| P01 | Production | DB restart after deployment | Users/roles remain persistent |
| P02 | Production | Duplicate normalized username/tenant | Constraint rejects or clear policy handles it |
| P03 | Production | Disable user | New logins blocked; old sessions follow revocation policy |
| P04 | Production | Password change | New hash verifies, old hash no longer authenticates |
| P05 | Production | DB timeout | Fails closed, alerts, no hardcoded user fallback |
| P06 | Production | Two replicas same account | Query same source of truth, consistent authorities |
| P07 | Production | Legacy password hash | Migration/DelegatingEncoder/reset per policy |
| P08 | Production | Account lockout/brute force | Rate limiting/lockout/audit, generic messages |
| P09 | Production | Unauthorized admin action | No business side effects |
| P10 | Production | Session fixation/timeout | ID rotated, timeout/invalid cookie enforced |
| P11 | Production | Rollback JDBC code | No data/role loss or fallback bypass opened |
| P12 | Production | CSRF/Cookie/HTTPS | Browser/session defenses against basic threats |

**Avoid testing at the wrong layer:** `@WithMockUser` only tests authorization with a mock user; `JdbcTemplate` queries only verify schema/data; POST login with CSRF tests the filter/provider; embedded-container/browser E2E confirms cookies over the network and real redirects. All three layers are needed to trust the system after migration.

## 15. Troubleshooting: From the Login Page to Database and Authorization

| Symptom | Common Cause | How to Diagnose |
| --- | --- | --- |
| GET /login returns 404 | Missing `@GetMapping("/login")` or `templates/login.html` | Check controller scan and Thymeleaf starter |
| GET /login redirect loop | Login page not permitAll / wrong matcher | Check `formLogin(...).permitAll()` and authorization rules |
| POST /login returns 403 | Missing/invalid CSRF token or session cookie | Check hidden `_csrf` field and Thymeleaf integration |
| POST /login with wrong password returns 302 | Expected form login failure behavior | Check `Location=/login?error`, do not treat 302 as pass |
| POST /login valid credentials still fails | Wrong profile bean, hash mismatch, disabled user, or other provider | Inspect trusted auth failure logs with masked secrets |
| Memory profile runs but Alice is missing | Profile not active or bean not scanned | Check `@Profile("memory")`, do not rely on generated password |
| JDBC profile fails to start | Missing H2 driver/schema, SQL init error, bad DataSource config | Check schema-jdbc.sql, JDBC URL, init order |
| SQLException table USERS not found | Spring SQL init did not run or wrong profile/resource | Check application-jdbc.yml and schema locations |
| Password "alice-pass" fails to match | DB column has plaintext/`{bcrypt}` incompatible with BCrypt bean | Check encoder format, do not use equals |
| Admin has ROLE_ADMIN in DB yet gets 403 | Wrong role prefix/row, different security chain, stale principal cache | Check `authorities.authority` and Authentication authorities |
| POST logout returns 403 | Missing CSRF token | Use a Thymeleaf POST form or `csrf()` in tests |
| GET dashboard after login redirects back | Session cookie not retained, Secure cookie on local HTTP, context repository | Check Set-Cookie/path/SameSite/session persistence |
| H2 works then loses users on restart | H2 `jdbc:h2:mem:...` is not durable | Move to a persistent DB and migrations |
| App crashes due to two UserDetailsService beans | Running memory+jdbc together or custom auto-config clash | Enable only one profile, inspect provider selection |
| Query returns wrong tenant's user | Username not unique/scoped per tenant | Use composite keys, stable principals, and tenant policy |
| Disabled user in DB still enters via old session | Existing HTTP session holds authenticated Authentication | Build logout-all/session version/revocation as required |
| DB fails yet demo admin can still log in | Memory fallback / hardcoded account still enabled | Remove fail-open fallback, inspect active beans |
| Template renders strange username HTML | Using `th:utext` on untrusted data | Use `th:text` and HTML escaping |
| DB not queried during JDBC login | In-memory bean still acting as provider or mock test bypassed filter | Check injected JdbcUserDetailsManager and SQL queries |
| Tests pass with @WithMockUser, real login fails | Tests bypass the password provider | POST /login with CSRF, assert authenticated |
| Production HTTPS stuck in login loop | Wrong proxy forwarded headers / Secure cookie / path | Configure trusted proxy headers, session fixation, and cookies |
| Role/user casing mismatch in DB | Inconsistent collation, trimming, or canonicalization | Define normalization/unique index and add tests |

## 16. Practice Handover Checklist

### Level 1 — Functional Completion

- [ ] Spring Boot 3/Java 17 project has Web/Security/Thymeleaf/JDBC/H2 dependencies managed by the BOM.
- [ ] `GET /login` renders the form, `POST /login` is handled by Spring Security, and username/password field names match.
- [ ] Thymeleaf templates generate CSRF hidden tokens for POST login/logout.
- [ ] `memory` profile has exactly two BCrypt-hashed users, with no `{noop}` in production.
- [ ] Alice has only ROLE_USER, Admin has ROLE_ADMIN; admin routes are protected server-side.
- [ ] POST logout invalidates the session; subsequent requests require re-authentication.
- [ ] Unit/MockMvc tests cover valid, invalid, missing user, CSRF, role, and session cases.

### Level 2 — Successful Data Store Migration

- [ ] JDBC schema `users`/`authorities` has the right structure, foreign key, and unique constraint.
- [ ] `JdbcUserDetailsManager` is the sole source under the `jdbc` profile; `memory` profile is not enabled simultaneously.
- [ ] Passwords are stored as BCrypt hashes; tests verify `matches` and correct DB authorities.
- [ ] PageController, login/dashboard/admin templates, and filter chain **did not require changes** when swapping the store.
- [ ] `jdbc` profile tests run through real HTTP logins, not database queries alone.
- [ ] Understand that in-memory H2 lacks durability across process restarts.

### Level 3 — Production Readiness

- [ ] Use a durable RDBMS, versioned migrations, a secret manager, and datasource TLS.
- [ ] Do not auto-create Alice/Admin with hardcoded passwords in production.
- [ ] Password hash migration is compatible; normalized data/tenant/roles are validated with unique constraints.
- [ ] Rate limiting/brute-force defense, MFA if needed, generic login errors, auditing, and account recovery are in place.
- [ ] Session fixation protection, idle/absolute timeout policies, and proper HTTPS/Secure/HttpOnly/SameSite settings are configured.
- [ ] Process exists to revoke sessions/remember-me after user disablement or password change when required.
- [ ] Backup/recovery, canary, rollback, login/database metrics, and negative tests are in place.
- [ ] Disallow falling back to an in-memory hardcoded admin when the datasource is unavailable.

**Conclusion:** The right way to move from RAM-stored accounts to a database is to **swap the UserDetailsService implementation** while preserving `UsernamePasswordAuthenticationFilter → DaoAuthenticationProvider → PasswordEncoder → SecurityContext` and all authorization policies. Successfully logging in against H2 only proves the **SQL lookup mechanism in a local lab**; it does not mean you have account persistence, production IAM, or a complete attack-resistant design.

### Official References

- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — In-Memory Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html)
- [Spring Security 6.5 — JDBC Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/jdbc.html)
- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — MockMvc Authentication Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security — Spring Security Test Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Boot 3.5 — Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html)
- [Spring Boot — SQL Databases and JdbcTemplate](https://docs.spring.io/spring-boot/reference/data/sql.html)
