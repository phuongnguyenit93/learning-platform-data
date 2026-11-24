# Relationship Between Spring Security, Spring Boot, and the Identity Store

## 1. Three Components Solving Three Different Responsibilities

When building login functionality for a Spring Boot application, distinguish the **application runtime platform**, the **security mechanism**, and the **source of identity data**:

| Component | Primary responsibility | Does not automatically replace the others |
| --- | --- | --- |
| **Spring Boot** | Bootstraps the application, manages dependencies, configuration, and auto-configuration; wires beans and starts the web application. | Does not inherently know whether real users live in a table, LDAP, or an identity provider. |
| **Spring Security** | Intercepts/processes requests at the security layer; performs *authentication*, *authorization*, manages `SecurityContext`, and integrates multiple login methods. | Is not a user administration system or an identity database. |
| **Identity store** | Stores or supplies identities, account status, hashed passwords (if any), groups/roles, or user attributes. Examples: in-memory for testing, database, LDAP/Active Directory. | Data merely existing does not mean an HTTP request is automatically authenticated or authorized. |
| **Identity Provider (IdP)**, if used | An independent system performing login/identity federation, such as an OpenID Connect (OIDC) or SAML system. | Is not synonymous with an internal `users` table; the application must still validate tokens/sessions and decide access permissions on its resources. |

**Core relationship:** Spring Boot builds and configures the application; Spring Security enforces security policies as requests enter; the identity store or IdP supplies evidence and information for the authentication mechanism to decide. The application is responsible for mapping an authenticated identity into concrete access permissions.

For example, a project declaring `spring-boot-starter-security` receives security components from Spring Security via Boot's configuration mechanism. If the application needs to log in using accounts in a database, the developer still has to connect Spring Security to the appropriate data source; merely adding Spring Data JPA and creating a `users` table is not enough.

## 2. Authentication, Authorization, and User Data Are Not One Operation

- **Authentication:** answers "who does this request represent?" by verifying appropriate evidence: password, login session, token, or IdP response.
- **Authorization:** answers "is that identity allowed to invoke this resource/action?" For example, a user with `ROLE_READER` can access `/private`.
- **Identity store:** where data needed for one or both steps is retrieved, such as username, password hash, locked flag, groups, and authorities.
- **Login credentials differ from identity data:** a username may be found in the DB, yet if the password is wrong it is not authenticated; having logged in successfully also does not mean access is allowed to every API.

In Spring Security, an `Authentication` object represents an authentication request or authenticated result; `principal` refers to the subject, `credentials` is the evidence, and `GrantedAuthority` represents permissions. `SecurityContext` holds the current `Authentication`. In Servlet applications, `SecurityContextHolder` typically binds the context to the processing thread; loading/saving the context across requests depends on the configured session, repository, and filters.

## 3. Typical Flow: HTTP Basic + Account and Password

The diagram below describes **one concrete case** of a Spring MVC/Servlet application using username/password. OIDC, JWT, or form-based login have their own flow details.

```text
HTTP client
    |
    v
Servlet container
    |
    v
Spring Security filter chain (FilterChainProxy / SecurityFilterChain)
    |
    +--> Filter receiving Basic credentials (username/password)
             |
             v
       AuthenticationManager (typically ProviderManager)
             |
             v
       AuthenticationProvider (e.g., DaoAuthenticationProvider)
             |                        |
             |                        +--> PasswordEncoder.matches(...)
             v
       UserDetailsService.loadUserByUsername(...)
             |
             v
       Adapter/Repository --> Identity store (in-memory, DB, LDAP...)
             |
             v
       UserDetails + authorities + password hash
             |
             v
       Authentication succeeded / failed
             |
             v
       SecurityContext containing authenticated Authentication
             |
             v
       AuthorizationFilter / access permission check
             |
             v
       Controller, service, protected resource
```

Points to understand accurately:

1. **`SecurityFilterChain` determines the request path** and the filters protecting it, such as configuring `httpBasic()`, `formLogin()`, or `oauth2Login()`. Boot assists in registering configurations into the application, while Spring Security provides the filters and rules.
2. **`AuthenticationManager` coordinates authentication**; `ProviderManager` can choose one of several `AuthenticationProvider` instances depending on the evidence type. Not every request goes through `DaoAuthenticationProvider`.
3. For **username/password**, `DaoAuthenticationProvider` typically uses `UserDetailsService` to load the account and `PasswordEncoder` to compare the entered password with the **hashed** password. `UserDetailsService` only loads data; it does not verify passwords itself and does not create accounts by default.
4. After successful authentication, Spring Security can use the `Authentication` in `SecurityContext` to check permissions; how the context is persisted across requests depends on the authentication mechanism. With HTTP Basic, clients typically re-send credentials on subsequent requests; with form login, a session may be used.
5. If unauthenticated when calling a protected resource, HTTP Basic typically returns **401 Unauthorized** with an authentication challenge. If authenticated but lacking permissions, it typically returns **403 Forbidden**. Actual status codes also depend on entry point/handler configuration.

**Important boundary:** data repositories must not be called directly from each controller to perform ad-hoc authentication and store an `isLoggedIn` flag. Build authentication through Spring Security so requests, context, and permission policies are handled consistently.

## 4. What Does Spring Boot Auto-Configure, and When Must You Configure Explicitly?

When Spring Security is on the classpath of a Servlet web application and no replacement configuration is provided, Spring Boot applies default security: requests are protected and login/HTTP Basic support is enabled per default configuration. In a simple setup with the default user mechanism, Boot may create a `user` account with a randomly generated password and print that password to the startup log. **This is a convenience for development, not a production user design.**

Two kinds of configuration can be changed **independently**:

| You declare | Meaning |
| --- | --- |
| `SecurityFilterChain` bean | You take ownership of URL rules, filters, and HTTP authentication mechanisms; Boot's default web security configuration backs off. |
| `UserDetailsService` bean | You supply the account-loading source for the username/password authentication branch. |
| `AuthenticationProvider` or `AuthenticationManager` bean | You supply an authentication mechanism or coordinator suited to your application. |
| `PasswordEncoder` bean | You specify the password matching algorithm/format for password-based authentication; it must match stored hashes. |

**A common misconception:** declaring only a `SecurityFilterChain` bean **does not automatically disable** Boot's default `UserDetailsService` auto-configuration. To control the application's user store, declare an appropriate bean such as `UserDetailsService`, `AuthenticationProvider`, or `AuthenticationManager`. Certain modules like OAuth2 Client/Resource Server/SAML2 also affect the conditions under which Boot auto-configures a default user; therefore never rely on an auto-generated account in real environments.

There is no rule that "Spring Boot always creates a users table automatically". Boot may auto-configure `DataSource` or JPA when dependencies/configuration are present, yet **data storage** and **authenticating against that data** remain two separate layers.

## 5. Runnable Example: Boot Connecting Spring Security to an In-Memory User Store

The example below uses **Spring Boot 3.3.x, Java 17+, and Gradle 8.5+**, forming a complete Java application class. Its purpose is to clearly show each participant's place: Boot launches the app, Security protects URLs, and `InMemoryUserDetailsManager` serves as the test identity store. The example uses a fixed demo password **for learning only**, never for production.

Structure:

```text
identity-demo/
├── build.gradle
└── src/main/java/demo/identity/IdentityDemoApplication.java
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
}
```

File `src/main/java/demo/identity/IdentityDemoApplication.java`:

```java
package demo.identity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class IdentityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/private").hasRole("READER")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("minh")
                .password(encoder.encode("ChangeMe123!"))
                .roles("READER")
                .build()
        );
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String publicPage() {
            return "Public OK";
        }

        @GetMapping("/private")
        String privatePage(Authentication authentication) {
            return "Hello " + authentication.getName();
        }
    }
}
```

In a terminal in the project directory, using JDK 17+ and compatible Gradle:

```bash
gradle bootRun

# Another terminal: public endpoint
curl -s http://localhost:8080/public

# Only get HTTP status when no account credentials are sent
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/private

# Send credentials to access the protected endpoint
curl -s -u 'minh:ChangeMe123!' http://localhost:8080/private
```

Response output (excluding startup logs):

```text
Public OK
401
Hello minh
```

Explanation following the three responsibilities:

- **Spring Boot** runs the `@SpringBootApplication` class, sets up the web server, and creates the beans.
- **Spring Security** picks up the `SecurityFilterChain` bean: `/public` can be called publicly; `/private` requires `ROLE_READER`; other endpoints are denied. HTTP Basic supplies credentials for authentication.
- **The in-memory identity store** is `InMemoryUserDetailsManager`, containing user `minh` with a BCrypt hash and role `READER`. `hasRole("READER")` corresponds to authority `ROLE_READER`.
- **PasswordEncoder** hashes the demo password before storing it in memory and helps the authentication mechanism match it. Hashing is a one-way function; passwords are never "decrypted" from the DB.
- The private endpoint receives `Authentication` from Spring Security, so the controller does not need to check passwords itself.

This is a small application without registration, password reset, auditing, rate limiting, or durable data. HTTP Basic over a real network must be paired with **HTTPS**; transmitting credentials over plain HTTP is insecure. Keep default CSRF protection as in the example; when moving to other APIs, evaluate the specific authentication and CSRF mechanisms instead of disabling protection just for quick testing.

## 6. Switching from In-Memory to a Real Identity Store: What Changes Is the Adapter

Suppose internal tables hold data:

```text
users(id, username UNIQUE, password_hash, enabled)
user_roles(user_id, role_name)
```

A common design using Spring Data JPA:

1. `UserRepository` reads the account from the database by username/ID.
2. A `UserDetailsService` implementation (or suitable bean) converts the account into `UserDetails`: username, password **hash**, enabled/locked/expired flags, and `GrantedAuthority` entries. If not found, throw `UsernameNotFoundException`.
3. `DaoAuthenticationProvider` uses the configured `UserDetailsService` and `PasswordEncoder` to verify credentials.
4. After authentication, `SecurityFilterChain` and the authorization layer enforce policies. Business controllers can use the authenticated principal/user ID.

This wiring only describes username/password. Permissions in the DB need clear mapping: `hasRole("ADMIN")` checks authority `ROLE_ADMIN` with the default prefix, whereas `hasAuthority("invoice:read")` checks the exact string `invoice:read`. Existing in the DB does not grant an account all permissions by default; permissions on specific objects (such as "only view one's own invoices") still require checks at the business/method-security layer.

**Illustrative adapter code example** (this is a snippet within an application that already defines `AccountRepository`, `Account`, and role relationships; not a standalone Java program):

```java
@Service
class AccountDetailsService implements UserDetailsService {
    private final AccountRepository accounts;

    AccountDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        Account account = accounts.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException(username));

        String[] authorities = account.roleNames().stream()
            .map(role -> "ROLE_" + role)
            .toArray(String[]::new);

        return User.withUsername(account.username())
            .password(account.passwordHash())
            .disabled(!account.enabled())
            .authorities(authorities)
            .build();
    }
}
```

The snippet requires Spring Security imports and an application-implemented `AccountRepository` bean. Do not use this snippet as a user-creation or password-saving feature: registration/password-change flows must hash passwords with an appropriate algorithm before writing to the DB; transaction management, unique username constraints, disabling/locking, and permissions are separate business responsibilities.

## 7. How Do Identity Store Choices Change the Integration Flow?

| Identity source | Typical connection approach | Key distinction |
| --- | --- | --- |
| **In-memory** | `InMemoryUserDetailsManager` | Useful for demos/tests; data does not persist across restarts unless reloaded. |
| **SQL database** | `JdbcUserDetailsManager` with supported schema, or custom `UserDetailsService` via JPA/repository | Application owns designing/storing hashes, enabled status, and authorities; Boot/JPA does not automatically "enable login from a table". |
| **LDAP/Active Directory** | Spring Security's appropriate LDAP/AD authentication components | Flow can bind/query the directory; does not necessarily download password hashes to the app for comparison. |
| **External IdP via OpenID Connect** | `spring-security-oauth2-client` + client config, `oauth2Login()` | IdP logs the user in; the app receives and verifies protocol data, then maps local identity/authorities if needed. |
| **API receiving JWT access tokens** | `spring-security-oauth2-resource-server` + issuer/JWK config or suitable token validation | API verifies signature, issuer, audience/timestamps, and converts claims/scopes to authorities per configuration; typically does not check user passwords against a `users` table on every request. |

**Do not equate an IdP with a local account store.** An IdP may use LDAP/DB behind the scenes, yet the Spring Boot app only sees login/token protocols. With OIDC, stable attributes like `issuer` + `sub` are usually more reliable than email as an account-linking key because emails can change. And if an application is only a resource server receiving JWTs, it does not automatically become an OAuth2 Login Client and should not collect user passwords itself.

When replacing `InMemoryUserDetailsManager` in the example with a DB-reading adapter, **the rest of the endpoint policies can remain unchanged**. That is the benefit of separating "how to find/verify an identity" from "conditions to call an API". However, switching to OIDC or JWT may require changing the HTTP authentication mechanism itself, not merely swapping the repository.

## 8. Common Design Mistakes

1. **Confusing Spring Boot with an identity system.** Starters and auto-configuration build infrastructure; the application still needs the right identity store, permission policies, account lifecycle, and production configuration.
2. **Assuming adding `SecurityFilterChain` removes the default user.** These are two separate auto-configuration branches; explicitly verify `UserDetailsService`/`AuthenticationProvider`/`AuthenticationManager` beans.
3. **Storing plaintext passwords or using direct string comparison.** Store hashes using a suitable algorithm (e.g., policy-appropriate BCrypt/Argon2), use `PasswordEncoder.matches(...)`, manage hash upgrades, and rate-limit password attempts.
4. **Writing manual login checks inside controllers.** This easily misses endpoints, returns wrong status codes, or bypasses policies; integrate authentication into filters/providers.
5. **Confusing authentication with authorization.** "Logged in successfully" does not replace checking roles, permissions, and rights on business objects.
6. **Mixing up `role` and `authority`.** `hasRole("ADMIN")` usually adds the `ROLE_` prefix, while `hasAuthority("ADMIN")` does not. Authority naming conventions must be consistent across the identity adapter and policies.
7. **Assuming every request always reads the DB.** With sessions or tokens, authentication and context-lookup paths differ; permission data may be cached/embedded in tokens, requiring a strategy to refresh/revoke when permissions change.
8. **Disabling CSRF, opening `permitAll()` broadly, or dropping HTTPS to fix 401/403 errors.** Identify the exact request, authentication mechanism, and required policy; distinguish unauthenticated errors from insufficient permissions.
9. **Assuming a valid JWT equals permission.** Verify token configuration (issuer, audience, signature, expiration), map scopes/roles properly, and check per-resource permissions.
10. **Believing the identity store holds all business profile data.** Authentication info, profiles, HR/customer records, and system usage rights may be managed by different systems; link them with stable identifiers and clear data contracts.

## 9. Knowledge Self-Check

**Scenario A.** Adding `spring-boot-starter-data-jpa` and a `User` entity to a project with Spring Security. Does login with DB users work automatically?

**Answer:** No. Entities/repositories only handle storage; you must wire them via `UserDetailsService`, a provider, or an appropriate authentication mechanism, along with designing an encoder and authorities.

**Scenario B.** A custom `SecurityFilterChain` has been declared. Can you conclude Boot no longer has a default demo account?

**Answer:** No. You must check `UserDetailsService` auto-configuration conditions and the authentication beans supplied by the application.

**Scenario C.** An API only receives bearer JWTs from an IdP. Does it need to load user passwords from a `users` table on every request?

**Answer:** Usually no. The resource server validates the token and computes authorities per configuration; the application may look up additional business profiles/permissions if the design requires it.

## 10. Further Reading

- [Spring Boot – Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html): default configuration and conditions for replacing it with application beans.
- [Spring Security – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `SecurityContext`, `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`.
- [Spring Security – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): relationship between `UserDetailsService` and `PasswordEncoder`.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/): login via external providers.

**Takeaway:** Boot handles bootstrapping and configuring the application; Security handles enforcing authentication/authorization; the identity store/IdP provides data or evidence. When you keep these three boundaries clear, you can swap user sources, change login mechanisms, or expand access permissions without rewriting every controller.