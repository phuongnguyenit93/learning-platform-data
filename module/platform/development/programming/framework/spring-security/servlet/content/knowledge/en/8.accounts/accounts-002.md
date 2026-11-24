# InMemoryUserDetailsManager for Examples and Testing in Spring Security Servlet

## 1. Overview and Objectives

When first learning **Spring Security Servlet**, you often want to create a few fixed accounts to verify **login**, **role-based authorization**, **hashed passwords**, and HTTP responses without having to set up PostgreSQL, MySQL, or an external identity service. **InMemoryUserDetailsManager** meets this need: it stores **UserDetails objects in the Java process's memory** and provides both lookup and user management operations.

This lesson helps you:

1. Understand the roles of **UserDetailsService**, **UserDetailsManager**, **UserDetails**, **GrantedAuthority**, and **InMemoryUserDetailsManager**.
2. Create sample users using **User.withUsername(...)**, **PasswordEncoder**, and **roles(...)**.
3. Connect InMemoryUserDetailsManager with **SecurityFilterChain**, **DaoAuthenticationProvider** via the built-in integration mechanism, and HTTP Basic.
4. Test **200/401/403** outcomes, distinguishing failed authentication from insufficient authorization.
5. Use **createUser**, **loadUserByUsername**, **userExists**, **updateUser**, and **deleteUser** to prepare or clean up test data.
6. Write **MockMvc integration tests** that traverse the Spring Security filter chain, instead of merely mocking an already-authenticated user.
7. Recognize the limits of an in-memory solution: **not durable across restarts, not shared across nodes, does not replace a production database**, and requires security care even for test accounts.

The complete example uses **Java 17+**, **Spring Boot 3.3.13**, **Spring Security 6**, Maven, and **spring-security-test**. We only use **GET** for the demo API; if you add state-changing requests, you must separately consider CSRF and access permissions.

## 2. What Is InMemoryUserDetailsManager?

**org.springframework.security.provisioning.InMemoryUserDetailsManager** is an implementation providing a user store directly in JVM memory. It implements the operations of **UserDetailsManager**, thereby also fulfilling the **UserDetailsService** contract.

Distinguish the roles clearly:

| Component | Responsibility | Directly authenticates HTTP requests? |
| --- | --- | --- |
| **UserDetails** | Describes username, encoded password, account status, authorities | No |
| **UserDetailsService** | Returns UserDetails by username via loadUserByUsername | No |
| **UserDetailsManager** | Extends UserDetailsService with user management operations | No |
| **InMemoryUserDetailsManager** | Stores/queries/manages users in JVM memory | No |
| **PasswordEncoder** | encodes passwords before storage, matches passwords during authentication | Does not read requests directly |
| **DaoAuthenticationProvider** | Compares raw password with hash from UserDetailsService and checks account flags | Invoked by AuthenticationManager |
| **AuthenticationManager / ProviderManager** | Coordinates AuthenticationProviders | Yes, in the authentication flow |
| **SecurityFilterChain** | Attaches filters and security rules for Servlet requests | Processes requests |
| **AuthorizationFilter** | Decides whether authorities suffice for a URL | Checks authorization |

**InMemoryUserDetailsManager is not an AuthenticationManager.** It only provides user data. Actual authentication still requires an appropriate AuthenticationProvider and a PasswordEncoder matching the stored password hash.

### User Management Contract

The **UserDetailsManager** interface declares commonly used methods:

~~~java
void createUser(UserDetails user);
void updateUser(UserDetails user);
void deleteUser(String username);
void changePassword(String oldPassword, String newPassword);
boolean userExists(String username);
~~~

In addition, from UserDetailsService there is:

~~~java
UserDetails loadUserByUsername(String username)
    throws UsernameNotFoundException;
~~~

These are **illustrative signatures from the interface**, not a standalone Java program. To use it in an application, inject InMemoryUserDetailsManager or UserDetailsManager into test code or an authorized service.

**Important distinction:** updateUser takes a UserDetails representing the updated account state; **changePassword** has the semantics of changing the currently authenticated user's password, depending on the appropriate security context/encoder configuration. The hands-on example uses updateUser explicitly to test the data store; do not call changePassword in an anonymous request and assume it works.

## 3. What Does UserDetails Actually Contain?

UserDetails is the contract required for username/password authentication. Common properties:

- **getUsername()**: the login username.
- **getPassword()**: the **encoded/hashed** password, not the raw password.
- **getAuthorities()**: the set of authorities, e.g., **ROLE_USER**, **ROLE_ADMIN**.
- **isEnabled()**: whether the account is enabled.
- **isAccountNonLocked()**: whether the account is not locked.
- **isAccountNonExpired()**: whether the account has not expired.
- **isCredentialsNonExpired()**: whether the credentials have not expired.

Spring Security provides the built-in class **org.springframework.security.core.userdetails.User** and **User.UserBuilder**. Example:

~~~java
UserDetails learner = User.withUsername("learner")
    .password(encoder.encode("learn-pass"))
    .roles("USER")
    .build();
~~~

Key points to remember:

1. **roles("USER")** normally creates the **ROLE_USER** authority; pass only the role name **USER**, do not prepend ROLE_ before calling roles.
2. **hasRole("USER")** in default authorization configuration checks against the **ROLE_USER** authority.
3. **authorities("document:read")** lets you describe finer-grained permissions; hasAuthority matches the exact permission string.
4. **password(encoder.encode(...))** stores the hash using the configured encoder; do not put raw passwords into long-lived UserDetails objects.
5. The sample passwords in this article are strictly for localhost/test environments. Never use them in production.

**InMemoryUserDetailsManager stores data in RAM**, which does not mean the system can recover the original password from the hash. Proper password hashing is one-way; the server verifies passwords with **PasswordEncoder.matches(raw, encoded)**.

### UserDetails and Principal After Authentication

After the provider authenticates, the Authentication object may carry a **UserDetails** as its principal. In Spring Security, **ProviderManager** typically enables erasing credentials from the authentication result. Therefore, do not write business logic or tests expecting principal.getPassword() to still hold the hash after login. When you need to check the initial hash, inspect it via the test source/user store **before authentication**, within a safe test scope, and never return the hash in an HTTP response.

In particular, if you build another custom UserDetailsService/cache and return the same mutable UserDetails instance for both the cache and the principal, credential erasure can wipe the password in the cache. InMemoryUserDetailsManager is a specific implementation; do not assume every repository/cache shares the same defensive-copy policy. For custom caches, check reference sharing and include repeated-login tests.

## 4. Lifecycle of In-Memory Users

~~~text
Spring Boot startup
        |
        v
SecurityConfig declares InMemoryUserDetailsManager bean
        |
        +--> creates UserDetails learner (ROLE_USER)
        |         BCrypt-hashed password
        |
        +--> creates UserDetails admin (ROLE_ADMIN)
                  BCrypt-hashed password
        |
        v
HTTP request to a protected endpoint
        |
        v
SecurityFilterChain -> BasicAuthenticationFilter
        |
        v
AuthenticationManager -> DaoAuthenticationProvider
        |
        +--> loadUserByUsername(username)
        +--> PasswordEncoder.matches(raw, hash)
        +--> check enabled/locked/expired
        |
        v
Authentication succeeded?
   /            \
  No            Yes
   |             |
 401      Authentication in SecurityContext
                 |
                 v
            AuthorizationFilter
                 |
           Sufficient authorities?
            /       \
          Yes        No
           |          |
       Controller     403
           |
          200
~~~

Not every request has to call UserDetailsService if another architecture uses sessions, remember-me, or a custom cache. The demo uses **HTTP Basic + SessionCreationPolicy.STATELESS** so each request with Basic credentials goes through proper authentication; this makes it easy to observe user changes immediately within the JVM.

**In-memory storage does not auto-sync across multiple machines.** If there are two JVMs, each JVM has its own user map. Calling createUser on JVM A does not make JVM B recognize that account. When a process stops or restarts, runtime changes are lost; only data re-seeded at startup is recreated.

## 5. Creating Beans and PasswordEncoder Properly

A basic configuration:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}

@Bean
InMemoryUserDetailsManager userDetailsService(
        PasswordEncoder encoder) {

    UserDetails learner = User.withUsername("learner")
        .password(encoder.encode("learn-pass"))
        .roles("USER")
        .build();

    return new InMemoryUserDetailsManager(learner);
}
~~~

This is a **fragment**; the full runnable SecurityConfig is in Section 7.

**Why is PasswordEncoder needed?** When a user sends a raw password via HTTP Basic, the provider must compare it against the stored hash. BCryptPasswordEncoder has a matches algorithm compatible with BCrypt hashes created by encode. If users were created with another encoder, such as DelegatingPasswordEncoder with the **{bcrypt}** prefix, you must choose a verification setup compatible with the stored format.

**Do not pass a raw password string directly** to .password(...) and pair it with BCryptPasswordEncoder. That is not an encoded password, and matches may reject it because the data is not a BCrypt hash. Also do not use **NoOpPasswordEncoder** in production to mask hashing bugs. Documentation examples sometimes use **{noop}** for demonstration purposes, but this article intentionally uses BCrypt consistently.

**BCrypt uses a random salt**: starting the application twice may generate different hash strings for the same demo password, yet HTTP Basic still authenticates when the raw password is correct. Never hardcode a specific hash string as expected stdout/test output.

## 6. Distinguishing UserDetailsService and UserDetailsManager in Tests

For code that only needs to load account info for authentication, injecting **UserDetailsService** is sufficient:

~~~java
UserDetails details = users.loadUserByUsername("learner");
~~~

For code that needs to prepare or clean up test data, use **UserDetailsManager** or **InMemoryUserDetailsManager**:

~~~java
manager.createUser(newUser);
boolean exists = manager.userExists("new-user");
manager.updateUser(updatedUser);
manager.deleteUser("new-user");
~~~

**These fragments are not standalone programs**: newUser, manager, and updatedUser must be declared, and permissions and operation order must be properly controlled. The project in Section 7 and tests in Section 9 give the complete example.

### No API to List All Users in UserDetailsManager

UserDetailsManager does not expose a standard **getAllUsers()** method. A test checking for a specific user should use **userExists(username)** or **loadUserByUsername(username)**. If a real application needs searching, pagination, or filtering of users, design an appropriate repository/service instead of assuming InMemoryUserDetailsManager is a database/query engine.

### Be Careful with Beans Shared Across Tests

SpringBootTest typically reuses the application context; an InMemoryUserDetailsManager bean mutated in test A can affect test B. Therefore:

- Keep seeded fixed accounts unchanged in regular tests.
- Use a dedicated username for each data-managing test.
- Use **try/finally** or @AfterEach to delete temporary users even if an assertion fails.
- Avoid running parallel tests on the same user or sharing uncontrolled mutable state.
- When strict isolation is needed, create a new manager in a unit test, or use an appropriate test context/test fixture rather than relying on test execution order.
- Never let tests modify or delete real system accounts.

In the demo, the management test creates a user named **temporary-user** and cleans it up in finally. Other tests use learner/admin without modifying them, so execution order does not matter.

## 7. Complete Spring Boot Project

### 7.1. File Structure

~~~text
inmemory-users-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/inmemory/
    │       ├── InMemoryDemoApplication.java
    │       ├── SecurityConfig.java
    │       └── AccountController.java
    └── test/
        └── java/com/example/inmemory/
            └── InMemoryUsersIntegrationTest.java
~~~

The demo has three endpoints:

- **GET /public**: public.
- **GET /me**: requires authentication; returns username and authorities, without password.
- **GET /admin**: requires ROLE_ADMIN.

Two initial users:

| Username | Demo password | Roles | /me | /admin |
| --- | --- | --- | --- | --- |
| learner | learn-pass | USER | 200 | 403 |
| admin | admin-pass | ADMIN | 200 | 200 |
| No credentials | — | None | 401 | 401 |

All passwords are only for local runs and testing. InMemoryUserDetailsManager does not expose a public user-admin API; CRUD operations are performed in integration tests under test code control.

### 7.2. pom.xml — Complete and Valid Maven Configuration

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>inmemory-users-demo</artifactId>
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
~~~

The Spring Boot parent manages compatible dependency versions for the example. Put the entire content above into **one pom.xml file**; no extra Maven profiles are needed. If a production system runs a different Spring Boot version, use that project's own dependency management/versions.

### 7.3. InMemoryDemoApplication.java

~~~java
package com.example.inmemory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InMemoryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(InMemoryDemoApplication.class, args);
    }
}
~~~

Spring Boot entry point. The remaining classes are in the same **com.example.inmemory** package, so Spring Boot scans the configuration and controller without special component-scan settings.

### 7.4. SecurityConfig.java

~~~java
package com.example.inmemory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
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
    InMemoryUserDetailsManager userDetailsService(
            PasswordEncoder encoder) {

        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learn-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
~~~

**Why can this configuration authenticate?**

1. There is an **InMemoryUserDetailsManager** bean, satisfying the **UserDetailsService** interface.
2. There is a **PasswordEncoder** bean, matching the encoding algorithm used when seeding users.
3. Spring Security uses the UserDetailsService/PasswordEncoder in the standard **username/password authentication** mechanism; the application does not need to write a custom controller comparing passwords or write BasicAuthenticationFilter.
4. **httpBasic** enables HTTP Basic and challenges protected endpoints.
5. **STATELESS** requires each request to carry its own credentials in the demo; it does not rely on HttpSession to remember login.
6. **formLogin disabled** avoids redirecting to an HTML login page while learning the Basic API.
7. **hasRole("ADMIN")** checks against ROLE_ADMIN generated by roles("ADMIN").
8. **anyRequest().denyAll()** avoids exposing any other endpoints outside the verified list.

If the project simultaneously declares a **custom AuthenticationProvider/AuthenticationManager** or multiple SecurityFilterChains, you must explicitly determine which provider/chain requests pass through; do not assume every bean will be used in the same order.

**Do not disable CSRF in this configuration.** The demo only uses GET to read data; GET does not require a CSRF token. If you add POST/PUT/DELETE, you must analyze CSRF according to the client/browser: HTTP Basic may be remembered and sent automatically by browsers. STATELESS does not inherently eliminate CSRF risk.

### 7.5. AccountController.java

~~~java
package com.example.inmemory;

import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, Object> currentUser(
            Authentication authentication) {

        List<String> roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", authentication.getName(),
            "authorities", roles
        );
    }

    @GetMapping("/admin")
    public Map<String, String> adminEndpoint() {
        return Map.of("message", "admin-only");
    }
}
~~~

The controller only uses the **Authentication** already verified by Spring Security. Do not access the password directly, do not call loadUserByUsername to re-authenticate manually, and do not let the client decide roles via request params or JSON.

### 7.6. Running the Application

From the **inmemory-users-demo** directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

On a machine with JDK 17+ and Maven, the application runs on port 8080 by default if that port is free. When dependencies are not yet in the Maven cache, repository access is needed to download them.

From another terminal, call:

~~~bash
curl -i http://localhost:8080/public
~~~

Expect status **200** and JSON with message = "public".

Without sending credentials:

~~~bash
curl -i http://localhost:8080/me
~~~

Expect **401 Unauthorized** with a WWW-Authenticate: Basic challenge (the specific realm depends on configuration).

Using the regular user:

~~~bash
curl -i -u learner:learn-pass http://localhost:8080/me
~~~

Expect **200 OK** with JSON:

~~~json
{
  "username": "learner",
  "authorities": ["ROLE_USER"]
}
~~~

Calling the admin endpoint with the regular user:

~~~bash
curl -i -u learner:learn-pass http://localhost:8080/admin
~~~

Expect **403 Forbidden**, because the user is authenticated but lacks ROLE_ADMIN.

Using admin:

~~~bash
curl -i -u admin:admin-pass http://localhost:8080/admin
~~~

Expect **200 OK** with JSON having message = "admin-only".

Wrong password:

~~~bash
curl -i -u learner:wrong-pass http://localhost:8080/me
~~~

Expect **401 Unauthorized**.

**Note on curl -u:** use the sample credentials from this article for local runs. With real secrets, a password in the command can be saved in shell history or appear in process information. Choose an appropriate secure secret provisioning mechanism; production must always use **HTTPS** because HTTP Basic only Base64-encodes username/password and does not encrypt secrets itself.

## 8. Why Is 401 Different from 403?

This is a very important part of testing in-memory users:

| Scenario | UserDetailsService / provider | Authorization | Result |
| --- | --- | --- | --- |
| GET /public without credentials | No authentication needed to permit | permitAll | 200 |
| GET /me without credentials | No valid identity yet | authenticated() not satisfied | 401 |
| GET /me wrong password | matches(raw, encoded) fails | Does not reach protected resource | 401 |
| GET /me valid learner | Has Authentication for learner | authenticated() satisfied | 200 |
| GET /admin valid learner | Has ROLE_USER, lacks ROLE_ADMIN | hasRole("ADMIN") denies | 403 |
| GET /admin valid admin | Has ROLE_ADMIN | hasRole("ADMIN") satisfied | 200 |

**401 Unauthorized** in HTTP Basic usually includes **WWW-Authenticate** so the client knows it must send credentials. **403 Forbidden** when a user is already authenticated but lacks a role is an authorization failure, and does not mean the password is wrong.

Other causes can also produce 403, such as CSRF on POST; do not infer that seeing 403 always means credentials were valid without checking the request and filter chain.

**Role and authority:** roles("ADMIN") creates ROLE_ADMIN. hasRole("ADMIN") checks ROLE_ADMIN by default. If you use authorities("ADMIN") without the ROLE_ prefix, the hasRole("ADMIN") rule will not match; in that case use hasAuthority("ADMIN") or keep the permission model consistent.

## 9. Complete MockMvc Integration Tests

The goal of testing is not just proving UserDetailsManager stores users; we need to test the **application's real HTTP flow**: Spring Security filters, HTTP Basic, PasswordEncoder, authorization, and then in-memory create/update/delete operations.

Create **src/test/java/com/example/inmemory/InMemoryUsersIntegrationTest.java**:

~~~java
package com.example.inmemory;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class InMemoryUsersIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    InMemoryUserDetailsManager users;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void publicEndpointWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void protectedEndpointWithoutCredentialsReturns401()
            throws Exception {

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordReturns401() throws Exception {
        mvc.perform(get("/me").with(
                httpBasic("learner", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void learnerCanReadOwnIdentity() throws Exception {
        mvc.perform(get("/me").with(
                httpBasic("learner", "learn-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authorities[0]")
                .value("ROLE_USER"));
    }

    @Test
    void learnerCannotReadAdminEndpoint() throws Exception {
        mvc.perform(get("/admin").with(
                httpBasic("learner", "learn-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void administratorCanReadAdminEndpoint() throws Exception {
        mvc.perform(get("/admin").with(
                httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin-only"));
    }

    @Test
    void seedUserPasswordIsEncoded() {
        UserDetails learner = users.loadUserByUsername("learner");

        assertTrue(users.userExists("learner"));
        assertNotEquals("learn-pass", learner.getPassword());
        assertTrue(encoder.matches("learn-pass", learner.getPassword()));
        assertFalse(encoder.matches(
            "wrong-pass", learner.getPassword()));
    }

    @Test
    void canCreateUpdateAndDeleteTemporaryAccount() throws Exception {
        String username = "temporary-user";

        assertFalse(users.userExists(username));

        UserDetails initial = User.withUsername(username)
            .password(encoder.encode("initial-pass"))
            .roles("USER")
            .build();

        try {
            // Create: new user can authenticate but lacks admin authority.
            users.createUser(initial);
            assertTrue(users.userExists(username));

            mvc.perform(get("/me").with(
                    httpBasic(username, "initial-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value(username));

            mvc.perform(get("/admin").with(
                    httpBasic(username, "initial-pass")))
                .andExpect(status().isForbidden());

            // Update: change password hash and authorities of the temporary user.
            UserDetails updated = User.withUsername(username)
                .password(encoder.encode("changed-pass"))
                .roles("ADMIN")
                .build();

            users.updateUser(updated);

            mvc.perform(get("/me").with(
                    httpBasic(username, "initial-pass")))
                .andExpect(status().isUnauthorized());

            mvc.perform(get("/admin").with(
                    httpBasic(username, "changed-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("admin-only"));

            // Delete: even the new credentials can no longer authenticate.
            users.deleteUser(username);
            assertFalse(users.userExists(username));

            mvc.perform(get("/me").with(
                    httpBasic(username, "changed-pass")))
                .andExpect(status().isUnauthorized());

        } finally {
            if (users.userExists(username)) {
                users.deleteUser(username);
            }
        }
    }

    @Test
    void disabledUserCannotAuthenticate() throws Exception {
        String username = "disabled-test";
        UserDetails disabled = User.withUsername(username)
            .password(encoder.encode("disabled-pass"))
            .roles("USER")
            .disabled(true)
            .build();

        try {
            users.createUser(disabled);

            mvc.perform(get("/me").with(
                    httpBasic(username, "disabled-pass")))
                .andExpect(status().isUnauthorized());

        } finally {
            if (users.userExists(username)) {
                users.deleteUser(username);
            }
        }
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

### 9.1. Explaining Each Test Group

**Basic HTTP group:** the tests for GET /public, GET /me without credentials, wrong password, valid learner, learner lacking role, and valid admin go through **MockMvc + Spring Security filter chain**. Thus you are verifying the actual passwords and authorities of the in-memory store, not merely mocking an authenticated user.

**Password encoding group:** the **seedUserPasswordIsEncoded** test reads UserDetails from the manager, verifies the stored password differs from the raw string, and uses **PasswordEncoder.matches** to verify it. The test never prints the password hash to the console or HTTP response.

**CRUD group:** the **canCreateUpdateAndDeleteTemporaryAccount** test exercises the full lifecycle:

1. Verify the user does not yet exist.
2. **createUser** adds the user with a BCrypt hash and ROLE_USER.
3. Authentication via HTTP Basic succeeds; accessing /admin returns 403.
4. **updateUser** updates the hash and role to ADMIN.
5. Old password gets 401; new password can access /admin.
6. **deleteUser** removes the account from the manager.
7. Basic credentials after deletion get 401.
8. **finally** ensures the user is cleaned up if an intermediate assertion throws an exception.

**Account status group:** the **disabledUserCannotAuthenticate** test creates a UserDetails with disabled(true). Even though the raw password matches the hash, DaoAuthenticationProvider still rejects a disabled account in the standard username/password flow.

### 9.2. Why Not Only Use @WithMockUser?

**@WithMockUser** is very useful for testing **authorization** quickly without going through real password authentication. For example, a controller test can mock ROLE_ADMIN to check controller/service behavior.

However, if the lesson aims to prove that InMemoryUserDetailsManager, BCrypt hashes, and DaoAuthenticationProvider are actually wired properly, **@WithMockUser is not enough**: it places a ready-made test Authentication into SecurityContext without looking up username/password from the manager. Therefore, this example intentionally uses **httpBasic(username, password)** from spring-security-test.

You can use both kinds of tests in a real project:

| Test type | Purpose | Verifies real user store/password in flow? |
| --- | --- | --- |
| Direct manager unit test | createUser, updateUser, deleteUser, loadUserByUsername | Does not test HTTP filters |
| MockMvc + @WithMockUser | Authorities of a mocked principal, controller logic | Typically no |
| MockMvc + httpBasic | HTTP Basic, UserDetailsService, PasswordEncoder, authorization | Yes, per app configuration |
| Integration test with real DB | Querying users, hashes/roles, transactions, cache | Yes, if set up properly |

### 9.3. Test Isolation and Parallel Execution

The example uses **temporary-user** and **disabled-test** solely for tests; no other test modifies those two users. Even so, if Maven/JUnit is configured to run the same test class across multiple processes or multiple test contexts sharing external data, you should generate unique usernames per test or create separate managers.

**Do not reflexively put @DirtiesContext on every test.** Reloading the entire Spring context can slow down the test suite. Cleaning up state in finally is usually sufficient for sequential tests, while special isolation needs should be solved with dedicated test fixtures.

### 9.4. Why Not Hardcode BCrypt Hashes in Tests?

BCrypt uses a random salt, so one raw password normally produces a different hash string each time it is encoded. Tests should rely on **encoder.matches** and system behavior rather than expecting a specific literal hash string. If a test requires changing a password, generate the new encoded hash with the same PasswordEncoder.

## 10. What Are the Limitations of UserDetailsManager CRUD?

**createUser(UserDetails):** adds a user to the manager. It does not automatically send verification emails, enforce password policies, provision MFA, or check legal requirements. In the example, the test encodes the password before passing UserDetails to createUser.

**loadUserByUsername(String):** looks up a user by username. When the user does not exist, the UserDetailsService contract normally throws **UsernameNotFoundException**; do not assume null is the standard return value. Some providers may convert a username-not-found error into a generic BadCredentials message to avoid leaking account existence.

**userExists(String):** checks whether a user is stored in the manager. This is an internal API for management and testing; do not expose a public endpoint that could help attackers enumerate usernames.

**updateUser(UserDetails):** updates the supplied user data, including hash/roles/status flags. It does not inherently provide DB transactions, audit trails, session/token invalidation, or optimistic locking like a production repository. In the demo, updateUser is used to demonstrate the effect upon HTTP Basic re-authentication.

**deleteUser(String):** removes a user from the current store. If the application uses a session already authenticated in a previous request, deleting the user from the store does not automatically erase the Authentication already sitting in the session. The example uses stateless HTTP Basic so every request checks the user store, meaning after deletion the credentials are no longer accepted on new requests.

**changePassword(String oldPassword, String newPassword):** has semantics intended for the currently authenticated user, and implementations may require a properly configured AuthenticationManager/PasswordEncoder. Do not use it as a shortcut to set a new password for an arbitrary account from an anonymous request. For real reset/change workflows, build a service that checks permissions, verifies the old password if needed, encodes the new password, and updates securely.

### Do Not Expose Manager CRUD Directly as a Public REST API

This is a common security mistake when demos are copied into production. Writing:

~~~java
// Anti-pattern example: DO NOT implement.
@PostMapping("/users")
public void create(@RequestBody UserDto user) {
    manager.createUser(...);
}
~~~

The snippet above is only an **anti-pattern illustration fragment**, not standalone runnable code: UserDto, manager, and the passed object would need separate definitions. The issue is not just syntax, but design: an external Internet request must never be allowed to pick its own role/encoded password and create a user without proper authorization, validation, rate limiting, CSRF protection, and auditing.

In the hands-on project, CRUD occurs only in **test code**, with no HTTP endpoint for creating or deleting users.

## 11. Is In-Memory Data Retained After a Restart?

**No.** Clearly distinguish four situations:

1. **Initial startup:** the userDetailsService bean creates learner and admin.
2. **Within the same JVM:** you call createUser("temporary-user"), and that user exists for requests using the same bean.
3. **JVM restart:** Spring recreates the bean from SecurityConfig; temporary users created at runtime are gone, while seeded users are recreated from configuration.
4. **Running two instances:** a user created in instance A does not automatically appear in instance B.

| Characteristic | InMemoryUserDetailsManager | Production repository/database |
| --- | --- | --- |
| Initial setup | Very fast | Needs database/migration/schema |
| Data across restarts | No, except seeded users recreated | Yes, when DB is durable and operated properly |
| Shared across app instances | Not automatically | Possible, depending on database/cache |
| Search, pagination, transactions | Limited, not a query engine | Can be designed |
| Use in tutorials/tests | Very suitable | Often unnecessary |
| Long-term real account storage | Not recommended | Appropriate with security controls |
| Password/role protection | Still required | Still required, plus transactions, audit, backup |

**Do not conclude that using in-memory means weak security in every case.** For demo apps, isolated prototypes, or tests, it is a reasonable choice. The main limitation lies in **persistence, data administration, and operations**, not the password hashing algorithm itself if BCrypt is used properly.

Conversely, a production system using a database is not automatically secure either if it stores raw passwords, lacks authorization config, leaks tokens in logs, or has no brute-force protection.

## 12. Notes on User Cache and Credentials Erasure

In a typical flow:

~~~text
InMemoryUserDetailsManager / UserDetailsService
          |
          v
DaoAuthenticationProvider retrieves UserDetails
          |
          v
PasswordEncoder.matches(rawPassword, storedHash)
          |
          v
ProviderManager creates successful Authentication
          |
          v
May erase credentials from Authentication/principal
          |
          v
Controller uses username + authorities
~~~

At the controller, **authentication.getCredentials() may be null** and the UserDetails principal may no longer retain the password. This is usually the intended behavior: after login, the application keeps identity/authorities without needing to keep raw passwords in Authentication.

If a **custom cache** returns the same mutable UserDetails instance used as the principal, the eraseCredentials mechanism could wipe the hash on the shared object. Keep cached data independent from principal objects that may be erased; test at least two consecutive login requests. The framework's InMemoryUserDetailsManager has specific implementation behavior; when building a different system, do not assume erasure/caching behavior is always identical.

Do not use disabling ProviderManager.eraseCredentialsAfterAuthentication by default as a first fix for a cache bug, because that can lengthen how long sensitive data remains in RAM.

## 13. Using InMemoryUserDetailsManager in Unit Tests Without Spring Boot

When you only need to test **user manager CRUD**, you can instantiate the manager directly instead of loading a Spring application context. The following is a **standalone JUnit 5 test class in the same Maven project**; it does not use HTTP and does not require Spring Boot to start.

Create an additional file: **src/test/java/com/example/inmemory/InMemoryManagerUnitTest.java**:

~~~java
package com.example.inmemory;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

class InMemoryManagerUnitTest {

    @Test
    void createsReadsAndDeletesUserWithoutApplicationContext() {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        InMemoryUserDetailsManager manager =
            new InMemoryUserDetailsManager();

        UserDetails user = User.withUsername("unit-user")
            .password(encoder.encode("unit-pass"))
            .roles("USER")
            .build();

        assertFalse(manager.userExists("unit-user"));

        manager.createUser(user);
        assertTrue(manager.userExists("unit-user"));

        UserDetails loaded =
            manager.loadUserByUsername("unit-user");

        assertTrue(encoder.matches(
            "unit-pass", loaded.getPassword()));

        manager.deleteUser("unit-user");
        assertFalse(manager.userExists("unit-user"));

        assertThrows(UsernameNotFoundException.class,
            () -> manager.loadUserByUsername("unit-user"));
    }
}
~~~

Run **mvn test** to execute both test classes. This is a good choice when the goal is only to test the manager; tests run quickly and do not depend on an HTTP container. However, it does **not** verify SecurityFilterChain or the correctness of requestMatchers. Therefore, combine unit tests and integration tests according to your needs.

**Point to remember:** InMemoryUserDetailsManager has a no-arg constructor for an initially empty store; you can add users with createUser. In the Spring Boot example, we used the constructor accepting varargs UserDetails to seed sample users.

## 14. Common Confusions with Other Components

### 14.1. InMemoryUserDetailsManager vs InMemoryAuthentication

Some older Spring Security examples use **inMemoryAuthentication()** configuration inside WebSecurityConfigurerAdapter. With Spring Security 6, you should prefer a **SecurityFilterChain bean** and a **UserDetailsService/InMemoryUserDetailsManager bean**, avoiding copying deprecated/removed configuration from older versions.

### 14.2. InMemoryUserDetailsManager vs InMemoryUserDetailsService

The actual implementation name in the common Servlet/username-password module is **InMemoryUserDetailsManager**. It can be injected via the **UserDetailsService** or **UserDetailsManager** interface. Do not invent similarly named classes based on API assumptions.

### 14.3. InMemoryUserDetailsManager vs MapReactiveUserDetailsService

**MapReactiveUserDetailsService** serves the **Reactive/WebFlux** ecosystem, whereas this article uses **Servlet**. The two stacks have different filter chain types and APIs; do not drop a reactive bean into a Servlet application and expect everything to wire automatically.

### 14.4. InMemoryUserDetailsManager vs a Database

A production application can use **JdbcUserDetailsManager** or a custom UserDetailsService/Repository implementation connected to a database. User management, password hashing, account status checks, and role mapping remain concepts to preserve when migrating from in-memory to persistent storage.

### 14.5. HTTP Basic vs Form Login

Both HTTP Basic and form login can use the **same UserDetailsService** to load users and PasswordEncoder to check raw passwords. The main differences lie in how credentials are received and how Authentication is persisted. HTTP Basic clients send an Authorization header, whereas form login uses form parameters and usually a session. You do not need to replace InMemoryUserDetailsManager just because the UI switches from Basic to form login.

### 14.6. Role vs Authority

**roles("ADMIN")** creates ROLE_ADMIN in the standard builder. **authorities("ADMIN")** creates the exact authority string ADMIN, without a prefix. hasRole("ADMIN") and hasAuthority("ADMIN") are not automatically equivalent. A prefix mismatch can cause 403 even with the right password.

## 15. Operations and Security Safety

**Do not use sample passwords outside localhost.** The article's seed data is for learning, not operational accounts. For real deployments, move secrets out of source code and choose a user store with password policies, reset/rotation, account lockout, and auditing.

**Never store raw passwords.** The UserDetails password field should be an encoded hash from an appropriate encoder. Use BCrypt/Argon2/PBKDF2/scrypt according to your system's policy and benchmarks, not fast unsalted hashes meant for integrity checks instead of password hashing.

**Do not expose user CRUD publicly.** Calling createUser/updateUser/deleteUser must be restricted to authorized code; for administrative APIs, enforce authorization checks, input validation, CSRF, rate limiting, and auditing.

**Do not trust authorities supplied by the client.** If a user sends JSON "roles":["ADMIN"], never automatically turn that into granted authorities; only the user store and approved administrative workflows determine authorities.

**Keep an appropriate CSRF policy.** With HTTP Basic through a browser, the browser may cache credentials. If adding POST endpoints, evaluate CSRF instead of disabling it due to mistakenly assuming STATELESS means safe.

**Do not log passwords/hashes/headers.** Never write Authorization, raw passwords, BCrypt hashes, session cookies, or full Authentication objects to loggers/telemetry. For tests, assert with booleans or non-sensitive attributes.

**Do not rely on fixed hashes in test output.** BCrypt generates a random salt. Tests should verify encoder.matches and expected states rather than snapshotting hash strings.

**Do not treat deleting a user as revoking all issued sessions.** For session-based apps, an Authentication already stored in HttpSession can continue to exist. Session invalidation/revocation and account state checks are needed as required.

**Accounts in one JVM are not a distributed identity store.** When scaling to multiple pods/instances, switch to a persistent store or an identity provider, and design cache consistency and session/token policies.

**Rate limiting and brute-force protection:** high-cost password hashing can consume heavy CPU during credential stuffing. Apply rate limiting, monitoring, and appropriate account lock/recovery policies when deploying real login.

## 16. Diagnosing Common Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| GET /me returns 401 despite correct raw password | Stored password was not encoded, or encoder mismatch | PasswordEncoder.matches on stored hash |
| UserDetailsService reports user not found | Username not seeded, typo, or different JVM | userExists, source bean, and environment |
| GET /admin returns 403 for learner | Only has ROLE_USER | hasRole("ADMIN") vs authorities |
| Valid admin still gets 403 | Used authorities("ADMIN") instead of roles("ADMIN") | Check ROLE_ prefix |
| createUser test passes, another test is affected | Shared ApplicationContext holds mutable manager | Use dedicated users and cleanup |
| Temporary user lost after restart | In-memory is not persistent | Switch to database/identity provider |
| Changed password but old requests still succeed | App uses session holding authenticated Authentication | Session revocation, security context policy |
| Password leaked in logs/curl history | Printed headers/shell/trace containing raw credentials | Redact and provision secrets securely |
| Form login 302 redirect instead of Basic challenge | formLogin enabled simultaneously or another chain | SecurityFilterChain, httpBasic, exception entry point |
| Changed role but requests still see old role | Old session/cache/principal | Re-authentication, cache/session invalidation |
| Test with @WithMockUser passes while HTTP Basic fails | Mock bypasses user store/password provider | Use MockMvc httpBasic integration test |
| createUser in production missing on another node | Store is RAM in the current JVM | Shared DB/identity service |
| New POST returns 403 | CSRF or authorization policy | CSRF token, HTTP method, security rules |
| Multiple UserDetailsService beans exist | Auto-configured provider source may be unclear | Verify AuthenticationManager/provider wiring |

### Quick Debugging Steps

1. Verify the exact URL, HTTP method, SecurityFilterChain, and app port.
2. Confirm the InMemoryUserDetailsManager bean is created and userExists(username) is true in the test environment.
3. Confirm the password is encoded with the PasswordEncoder used by the provider.
4. Confirm the request has a valid Basic Authorization header or uses MockMvc httpBasic.
5. If 401, inspect username, account flags, password matching, and authentication entry point; avoid logging credentials.
6. If 403, inspect authorities, ROLE_ prefix, CSRF, and authorizeHttpRequests rules.
7. If tests interfere with each other, check shared manager state, test user cleanup, and parallel execution.
8. If errors occur after restart or across multiple nodes, remember the manager is neither persistent nor distributed.
9. For complex integrations, check whether a custom AuthenticationProvider or multiple chains with overlapping matchers exist.
10. Add integration tests reproducing the bug instead of disabling authentication or CSRF to get status 200.

## 17. Self-Practice Exercises with Answers

### Exercise A — UserDetailsService or UserDetailsManager?

You only need to load a user to verify a password; which interface is sufficient? When you need to create/delete a test user, which interface is appropriate?

**Answer:** for only looking up users, UserDetailsService is sufficient; when you need create/update/delete/userExists, UserDetailsManager is appropriate.

### Exercise B — Why Encode?

Using .password("secret") in the builder while the provider has BCryptPasswordEncoder. Is login guaranteed to succeed?

**Answer:** No. The stored password must be in a BCrypt hash format that encoder.matches understands. Use encoder.encode("secret") when creating UserDetails; never store plaintext.

### Exercise C — Which Role Is Created?

~~~java
User.withUsername("reader")
    .password(encoder.encode("pass"))
    .roles("ADMIN")
    .build();
~~~

What authority does the fragment above create, and what does hasRole("ADMIN") check?

**Answer:** the ROLE_ADMIN authority. hasRole("ADMIN") checks against ROLE_ADMIN according to the default prefix.

### Exercise D — 401 or 403?

A user with the correct password and ROLE_USER calls GET /admin which requires ROLE_ADMIN. Which status makes sense in the demo?

**Answer:** 403 because authentication succeeded but authorities are insufficient. 401 applies when unauthenticated or when the password is wrong.

### Exercise E — Data Persistence

Create temporary-user via createUser, then restart Spring Boot. Does the temporary user still exist in the new manager?

**Answer:** No, unless re-seeded in startup configuration. The in-memory manager does not persist runtime changes.

### Exercise F — Unit Test or Integration Test?

A test only calls manager.createUser/loadUserByUsername without going through SecurityFilterChain. Is that enough to prove /admin blocks ROLE_USER?

**Answer:** No. You need an HTTP test through the filter chain, such as MockMvc with httpBasic using valid passwords and the hasRole rule.

### Exercise G — Changing Password

A test creates temporary-user with an old password, then calls updateUser with a new hash. Why must the old password be rejected on the next HTTP Basic request in the demo?

**Answer:** STATELESS requires re-authentication on every request; PasswordEncoder.matches against the new hash no longer matches the old raw password.

### Exercise H — Why Not Use @WithMockUser to Test BCrypt?

Does @WithMockUser check a raw password against the hash in InMemoryUserDetailsManager?

**Answer:** No. @WithMockUser supplies a mocked Authentication for tests, useful for testing authorization but not proving user store/password provider integration. Use MockMvc httpBasic when real verification is needed.

### Exercise I — Cleanup

If an assertion in a test creating a temporary user fails before deleteUser, how do you avoid affecting other tests?

**Answer:** Use try/finally or safely designed fixture teardown to delete the user if it still exists, and use a unique username per test.

### Exercise K — Multi-Node

You have two app instances with the same InMemoryUserDetailsManager configuration. A test adds a user on instance A, then sends a request to B. Does B know about the new user?

**Answer:** There is no automatic synchronization between JVMs. A shared persistent store or identity service is required if that is an architectural requirement.

## 18. Pre-Application Checklist

- [ ] Understand InMemoryUserDetailsManager is an **in-RAM UserDetails store**, not an AuthenticationManager.
- [ ] Create users with PasswordEncoder and matching hashes, never storing plaintext.
- [ ] Use User.withUsername(...).roles(...) following the ROLE_ convention.
- [ ] Configure SecurityFilterChain, httpBasic/formLogin, and requestMatchers clearly.
- [ ] Test requests without credentials, with wrong passwords, with right passwords, and lacking roles.
- [ ] Have at least one test traversing HTTP Basic + provider + store, not only @WithMockUser.
- [ ] For create/update/delete tests, use temporary users and clean up in finally/teardown.
- [ ] Do not run tests mutating shared context in parallel without isolation.
- [ ] Never output user passwords/hashes/Authorization headers to APIs or logs.
- [ ] Distinguish 401 authentication failure from 403 authorization/CSRF denial.
- [ ] Understand restarts/multi-node setups will not retain/share runtime-added users.
- [ ] Do not expose a CRUD API directly on the manager without authorization checks and auditing.
- [ ] Do not expect deleteUser/updateUser to automatically revoke issued sessions.
- [ ] Use HTTPS with real HTTP Basic and rate limiting for login endpoints.
- [ ] When moving to production, use an appropriate persistent UserDetailsService/identity store, transactions, and security policies.

**Conclusion:** **InMemoryUserDetailsManager** is a lightweight and useful choice for building examples or testing **Spring Security Servlet**. It provides UserDetailsService for username/password authentication and UserDetailsManager for creating, updating, and deleting test accounts. Combined with **BCryptPasswordEncoder**, **SecurityFilterChain**, HTTP Basic, and **MockMvc**, you can verify the full 200/401/403 flow and mutable user data within the same JVM. Remember that this is a **temporary store in RAM**, not a durable or distributed account management system for production.
