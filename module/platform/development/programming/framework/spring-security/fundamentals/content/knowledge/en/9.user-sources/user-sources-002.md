# UserDetails with Username, Password, Authorities, and Account Status

When Spring Security authenticates using username/password, the system usually has to fetch account information from a trusted source: a database, user store, or identity service. **UserDetails** is the contract describing the information the authentication mechanism needs to know about an account: **username, password stored via a secure mechanism, granted authorities, and four account status flags**. This is one of the most important types for understanding why, with the same correct password, one user logs in successfully while another is locked or expired.

This lesson belongs to the **User Sources** section of Spring Security. The focus is on the structure of UserDetails, the meaning of each method, how UserDetailsService supplies data to DaoAuthenticationProvider, and how account status affects the authentication process. The lesson uses **Java 17+, Spring Boot 3.3.6, and Spring Security 6.x** along with a runnable Maven demo and MockMvc/JUnit tests. All accounts, passwords, and data are samples for running on localhost, not intended as a production identity storage design.

## 1. The Right Mental Model: UserDetails Is an Account Description for Security

A user in a business system can have dozens of attributes: ID, display name, email, address, tenant, registration date, billing policy, language, and change history. Spring Security does not need to carry that entire object to verify a password. It needs a **contract focused on authentication and permissions**.

~~~text
Database / identity store
  AccountRow:
    user_id, username, password_hash,
    enabled, locked, expires_at, password_expires_at,
    roles/permissions, tenant_id, ...
               |
               v
UserDetailsService.loadUserByUsername(username)
               |
               v
UserDetails:
  getUsername()
  getPassword()
  getAuthorities()
  isEnabled()
  isAccountNonLocked()
  isAccountNonExpired()
  isCredentialsNonExpired()
               |
               v
DaoAuthenticationProvider + PasswordEncoder
               |
               v
Authenticated Authentication or AuthenticationException
               |
               v
Authorization at HTTP/Service checks roles, permissions, resources
~~~

**UserDetails does not itself check passwords, does not itself query the database, and does not itself return HTTP 401/403.** It is a data-holder object. UserDetailsService finds and returns that object; AuthenticationProvider executes credential and account status verification; the rest of Spring Security decides the response and access rights.

This separation lets a database entity serve business logic while UserDetails exposes only the minimum data needed to handle authentication. When you need to add tenantId or accountId for business logic, design the data source and principal class explicitly rather than automatically putting all sensitive entity fields into SecurityContext.

## 2. What Methods Does the UserDetails Contract Include?

The interface **org.springframework.security.core.userdetails.UserDetails** has the following core members:

~~~java
// Describes the main signature of UserDetails, not the full framework source.
public interface UserDetails extends java.io.Serializable {

    Collection<? extends GrantedAuthority> getAuthorities();

    String getPassword();

    String getUsername();

    boolean isAccountNonExpired();

    boolean isAccountNonLocked();

    boolean isCredentialsNonExpired();

    boolean isEnabled();
}
~~~

Starting from Spring Security 6.x, some boolean methods may have default implementations; **the contract semantics still need to be understood and explicitly overridden/configured when a product has account statuses**. The code above is a simplified signature for learning, not a file to copy in place of the original interface.

| Method | Represented value | How it is used |
| --- | --- | --- |
| **getUsername()** | Identifier name used in username/password mechanism. | Identifies the user to look up, serves as Authentication.getName() when appropriate. |
| **getPassword()** | Stored password information, typically a **hash** per PasswordEncoder. | DaoAuthenticationProvider/PasswordEncoder matches submitted password against stored hash. |
| **getAuthorities()** | Collection of GrantedAuthority representing granted permissions. | Builds Authentication; later used by hasRole/hasAuthority rules. |
| **isEnabled()** | true if the account is enabled. | false typically causes the provider to reject authentication. |
| **isAccountNonLocked()** | true if the account is **not locked**. | false typically causes the provider to throw LockedException. |
| **isAccountNonExpired()** | true if the account is **not expired**. | false typically causes the provider to throw AccountExpiredException. |
| **isCredentialsNonExpired()** | true if the credentials are **not expired**. | false typically causes the provider to throw CredentialsExpiredException. |

**Easy rule to remember:** All three flags shaped like **Non...** must be **true** under normal conditions. enabled itself must also be true. Do not confuse a database boolean like locked=true with isAccountNonLocked=true. When mapping from entity to UserDetails, invert the sign properly:

~~~java
// Example when the database stores locked = true meaning it is currently locked.
boolean accountNonLocked = !databaseUser.isLocked();
~~~

A negation sign bug will create dangerous behavior: an account that should be locked is treated as valid, or vice versa. Always write tests for both states.

## 3. Username: The Identifier Name of an Account

**getUsername()** returns the username used by the authentication mechanism. In Spring Security, the return type is **String**; the practical meaning may be a login name, a normalized email, or a loginable ID depending on the design.

Example:

~~~text
username in account store: "alice"
UserDetails.getUsername(): "alice"
Authentication.getName(): "alice" (under the standard principal mechanism)
~~~

**Username is not necessarily an immutable internal ID.** Many systems allow changing email or login name while the user's primary key in the database never changes. If you need to check owner or tenant, rely on a trusted internal identifier mapped via the principal/service rather than comparing a mutable email directly against ownerId.

### 3.1. Username must have clear normalization rules

Common pitfalls:

- **Case sensitivity:** Are ALICE and alice the same account? Decide based on datastore and business rules rather than lowercasing in one place and forgetting in another.
- **Unicode normalization:** Visually identical strings can have different Unicode representations; the system needs consistent storage/lookup rules.
- **Uniqueness:** Username must be unique within the designed identity scope; in a multi-tenant system, tenantId + username may be needed.
- **Account enumeration:** Different error messages between "username does not exist" and "wrong password" can leak the account list.
- **Lookup key:** Do not use a client-sent username to skip credential verification; username is a lookup key, not proof that the caller owns the account.

In the demo, usernames are matched as exact strings and there are only a few sample accounts. A real application needs normalization, uniqueness constraints, and anti-enumeration policies right at the identity source layer.

### 3.2. If logging in by email, what is getUsername()?

You can design UserDetailsService to accept an email as the login name and return a UserDetails whose getUsername() is the normalized email. You can also use a separate identifier for the principal in Authentication after authentication. What must remain consistent is **the user lookup mechanism, returned identity, and data-binding policy**.

Do not use a userId query parameter on the /api/me endpoint to determine the current user. Obtain the principal from the system-authenticated Authentication/SecurityContext.

## 4. Password: Stored Hash, Not Raw Password

**getPassword() typically returns the stored password hash**, not the password the user just entered. When using DaoAuthenticationProvider:

~~~text
Client sends password (sensitive)
         |
         v
Authentication filter creates token holding raw password temporarily
         |
         v
DaoAuthenticationProvider
         |--> UserDetailsService.loadUserByUsername(username)
         |--> UserDetails.getPassword()  // stored encoded hash
         |--> PasswordEncoder.matches(raw, storedHash)
         |
         +--> Valid and status OK: Authentication succeeds
         +--> Invalid: AuthenticationException
~~~

Principles:

1. Never store plain-text passwords.
2. Never use plain Base64, unsalted SHA-256, or a fast hash as homebrew password storage.
3. Use an appropriate PasswordEncoder such as BCryptPasswordEncoder or DelegatingPasswordEncoder with a secure hash configuration.
4. **encode()** generates the hash on registration/password change; **matches(raw, encoded)** is used at login.
5. Never compare an encoded hash to a raw password using equals.
6. Never re-hash a password when only **looking up UserDetails**: getPassword() must return the **stored hash**, not create a new hash from a "real password" value for comparison.
7. Never include password hashes, raw passwords, API keys, or recovery codes in JSON responses, exception messages, or logs.
8. When changing algorithms/work factors, design migration/rehash policies and verify compatibility with old hashes.

### 4.1. How is BCrypt used?

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String storedHash = encoder.encode("demo-pass");

boolean correct = encoder.matches("demo-pass", storedHash);
boolean incorrect = encoder.matches("wrong", storedHash);
~~~

**Reliable logical output:**

~~~text
correct = true
incorrect = false
~~~

The storedHash string may differ on every run due to salting. Do not put a specific hash in documentation and treat it as required output. In example code, dummy passwords are for localhost only; never commit or print real secrets to logs/console.

A standalone Java 17 example you can run immediately (without Spring) to illustrate why the same input value can be processed with a salt:

~~~java
// File: HashDemo.java. Simulates a salted hash only to explain the concept,
// NOT a production password storage algorithm.
public class HashDemo {
    public static void main(String[] args) {
        String raw = "demo-pass";
        String stored = "salt-A:" + raw.hashCode();

        System.out.println("raw=" + raw);
        System.out.println("storedIsRaw=" + stored.equals(raw));
    }
}
~~~

Run with:

~~~bash
javac HashDemo.java
java HashDemo
~~~

Deterministic output:

~~~text
raw=demo-pass
storedIsRaw=false
~~~

The HashDemo code above is **an illustration to distinguish the two strings**; never use hashCode() to store real passwords. The Spring Boot example in the hands-on section uses BCryptPasswordEncoder properly.

## 5. Authorities: What Permissions Does UserDetails Carry?

**getAuthorities()** returns a collection of **GrantedAuthority**, commonly represented by **SimpleGrantedAuthority** with a String:

~~~java
// Java code fragment where Spring Security Core is already imported.
List<GrantedAuthority> permissions = List.of(
    new SimpleGrantedAuthority("ROLE_USER"),
    new SimpleGrantedAuthority("orders:read")
);
~~~

Authorities are placed into Authentication after authentication. Spring Security uses them to evaluate expressions such as:

~~~java
// Expression fragment in SecurityFilterChain:
.hasRole("USER")                   // usually checks authority "ROLE_USER"
.hasAuthority("orders:read")       // checks exact string "orders:read"
.hasAuthority("SCOPE_orders.read") // checks authority from OAuth scope if present
~~~

**Roles, permissions, and scopes are not automatically equivalent.** For instance, ROLE_USER does not automatically include orders:read; the authority SCOPE_orders.read is not automatically created by a standard UserDetails unless the system intentionally grants/maps it. Never grant ROLE_ADMIN based on an unverified X-Role header or JWT payload.

### 5.1. Spring Security User builder: roles and authorities

With the built-in class **org.springframework.security.core.userdetails.User**, you can write:

~~~java
UserDetails alice = User.withUsername("alice")
    .password(encodedPassword)
    .roles("USER")
    .build();
~~~

roles("USER") adds the **ROLE_USER** authority under the standard prefix. When you also want custom permissions:

~~~java
UserDetails alice = User.withUsername("alice")
    .password(encodedPassword)
    .authorities("ROLE_USER", "orders:read")
    .build();
~~~

**Do not assume .roles(...).authorities(...) always accumulates**: the builder may replace the configured list depending on how it is called; for clarity, this example uses **a single authorities(...) call** containing all strings to grant.

### 5.2. Do not infer permissions from the account name

An account with username admin does not automatically have ROLE_ADMIN. A user with a company-domain email also does not automatically have employee permissions unless the system has a verified source rule and an explicit grant policy. Checking **Authentication.getAuthorities()** is how Spring Security evaluates permissions, after which owner/tenant/resource policies still must be evaluated.

### 5.3. Avoid exposing authorities externally without purpose

In the lesson, the /api/me endpoint may return username and sample authorities for observation. In a real application, expose only the information needed by the UI and business logic; sensitive permissions or internal details should be handled server-side.

## 6. Four Account Statuses: Meaning and Interpretation

Spring Security uses UserDetails flags to indicate whether an account can authenticate via the corresponding mechanism.

| isEnabled | isAccountNonLocked | isAccountNonExpired | isCredentialsNonExpired | Interpretation |
| --- | --- | --- | --- | --- |
| true | true | true | true | Normal account across all four flags. |
| false | true | true | true | Account is disabled / not yet activated. |
| true | false | true | true | Account is locked. |
| true | true | false | true | Account has expired. |
| true | true | true | false | Credentials have expired, may require a password change. |
| false | false | false | false | Multiple denial conditions simultaneously; specific exception depends on check order. |

**True on the three Non... flags is healthy**, **false is a rejected state**. Pay attention to the negation in the method names. Reading isAccountNonLocked() quickly as "account is not locked" helps avoid boolean inversion bugs.

### 6.1. isEnabled(): Is the account activated?

Business cases that may set enabled=false:

- Email not yet verified or mandatory onboarding steps incomplete.
- Account disabled by administrators.
- Account deactivated and policy requires blocking login.
- An access-prohibited state confirmed by workflow.

Do not assume that enabled=false means "email not verified"; that meaning is defined by the product. Spring Security primarily knows a **boolean**, not the entire account lifecycle. If you need to distinguish reasons, store that information in the domain model and apply a safe response policy.

DaoAuthenticationProvider may throw **DisabledException** when the account is not enabled. An HTTP Basic endpoint typically turns authentication errors into 401; detailed reasons should not be exposed to unauthenticated callers.

### 6.2. isAccountNonLocked(): Is the account locked?

If **isAccountNonLocked() = false**, DaoAuthenticationProvider typically uses **LockedException**.

Distinguish two things:

- **Stored lock state**: UserDetails reports locked.
- **Auto-lock mechanism after N wrong passwords**: the system itself must design failure counting, rate limiting, lockout policy, and updating the identity source.

Spring Security **does not by default create an account lockout system after 5 failed attempts** just because UserDetails has an isAccountNonLocked() method. If you want this feature, you need to design concurrency handling, counter resets, brute-force protection, auditing, and an unlock flow; never trust counters from client requests.

In security design, indefinite lockouts can be abused to cause denial of service against other users' accounts. Depending on the product, you can choose rate limiting, delays, additional checks, or temporary locks with a recovery channel.

### 6.3. isAccountNonExpired(): Has the account expired?

If **isAccountNonExpired() = false**, the provider may throw **AccountExpiredException**. For example, a seasonal contractor account expires after its end date.

This flag does not automatically know the current time or expiration date. **UserDetailsService must compute the flag from trusted data** when building UserDetails, or retrieve the status decided by the identity system. In a real application, you must define timezone, boundary instant, and data source time to avoid premature/late expiration bugs.

If an entity has expiryTimestamp, for example:

~~~java
// Illustrative fragment: expiresAt has type java.time.Instant.
boolean nonExpired =
    expiresAt == null || expiresAt.isAfter(Instant.now());
~~~

Using `>` (`isAfter`) means the account is considered expired **at or after** the expiresAt instant. This is a policy choice; document expectations and test boundaries rather than letting semantics depend on the server's default timezone.

### 6.4. isCredentialsNonExpired(): Are the password/credentials still valid?

If **isCredentialsNonExpired() = false**, the provider may throw **CredentialsExpiredException**. An application may use this flag when a password must be rotated per policy or has been revoked.

**Account expired** and **credentials expired** differ:

- Account expired: the identity/account itself is no longer permitted for use in the corresponding model.
- Credentials expired: the specific credential used for authentication has expired; the account may still exist and have another recovery/password-change mechanism.

When a password expires, do not use an API endpoint protected by that same expired password to perform "password change" without designing an appropriate verification flow: the user may be unable to log in. You need a recovery/reset flow or a sufficiently trusted additional verification mechanism.

### 6.5. What if multiple statuses fail at the same time?

**The provider's check order determines which exception is thrown first.** In the common DaoAuthenticationProvider/AbstractUserDetailsAuthenticationProvider flow, pre-authentication checks such as locked, disabled, and account expired occur before checking the password; credentials expired is typically a post-authentication check. Do not rely on this error display order as a public API contract, because the framework can change and applications may have custom providers/checkers.

For example, an account that is both locked and disabled may be reported as locked first if the checker prioritizes locked. Protect account information with a generic public error message, while internal logs retain only necessary reason codes without leaking credentials.

## 7. UserDetailsService Returns UserDetails, But Does Not Authenticate Passwords

**UserDetailsService** is the interface for loading UserDetails:

~~~java
// Signature describing the Spring Security interface.
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
~~~

**Primary duty:** find the account by username and return the right UserDetails with password hash, authorities, and status.

It **does not itself perform PasswordEncoder.matches(...)**, does not itself decide HTTP responses, and is not an AuthenticationManager.

A request is typically processed as follows:

~~~mermaid
flowchart TD
    A["HTTP Basic: username + password"] --> B["BasicAuthenticationFilter"]
    B --> C["Unauthenticated UsernamePasswordAuthenticationToken"]
    C --> D["ProviderManager"]
    D --> E["DaoAuthenticationProvider"]
    E --> F["UserDetailsService.loadUserByUsername"]
    F --> G["UserDetails: username / hash / authorities / flags"]
    G --> H["Account checks + PasswordEncoder.matches"]
    H --> I{"Valid?"}
    I -- "Yes" --> J["Authenticated Authentication"]
    I -- "No" --> K["AuthenticationException"]
    J --> L["Authorization + Controller"]
    K --> M["AuthenticationEntryPoint: usually 401"]
~~~

In complete code, DaoAuthenticationProvider already knows the configured UserDetailsService and PasswordEncoder, so it calls loadUserByUsername at the right time.

### 7.1. When the user does not exist

UserDetailsService should throw **UsernameNotFoundException** when not found; do not return null or a fake high-privilege user:

~~~java
@Override
public UserDetails loadUserByUsername(String username) {
    UserDetails user = repositoryFindByUsername(username);
    if (user == null) {
        throw new UsernameNotFoundException("Account not found");
    }
    return user;
}
~~~

This is an **illustrative code fragment**; repositoryFindByUsername requires a real implementation and will not run standalone. In DaoAuthenticationProvider, under common default configuration, missing-user information may be **hidden as BadCredentialsException** to reduce account enumeration via authentication errors. Therefore:

- Calling UserDetailsService directly: you may see UsernameNotFoundException.
- Calling AuthenticationManager with a non-existent username: you may receive BadCredentialsException.
- Calling an HTTP Basic API: you usually receive 401 without clearly distinguishing whether the account exists.

Do not take the exception message and return it verbatim in the API response to an unauthenticated client.

### 7.2. What if usernames are scoped per tenant?

The loadUserByUsername(String) method only has a username parameter. A multi-tenant system may need:

- A globally unique username rule, or
- A trusted mechanism identifying the tenant in the authentication request/context and querying the right identity domain, or
- A specialized AuthenticationProvider with a token containing a verified tenant.

Do not use a client-chosen X-Tenant header to turn the same username into access for another tenant. Multi-tenant login requires clearly verifying tenant routing, the permission source, and the Authentication scope.

### 7.3. What is UserDetailsManager?

**UserDetailsManager** extends UserDetailsService with account management operations such as creating, updating, deleting users, and changing passwords per implementation.

Common implementations:

- **InMemoryUserDetailsManager**: suited for demos/tests or very small setups.
- **JdbcUserDetailsManager**: supports Spring Security's standard JDBC schema model; requires verifying database schema and connection privileges.
- **Custom UserDetailsService**: reads from the application's user/role/permission tables.
- **ReactiveUserDetailsService**: for WebFlux/reactive, returns Mono<UserDetails>; you cannot drop the synchronous interface into a reactive pipeline and assume I/O becomes nonblocking.

A lookup-only UserDetailsService does not automatically become a CRUD manager. Separate the responsibility of reading accounts from the responsibility of changing permissions/passwords.

## 8. Spring Security Provides the Built-in User Class and UserBuilder

You **do not have to implement UserDetails yourself** for every project. The **org.springframework.security.core.userdetails.User** class already implements UserDetails and has a convenient builder:

~~~java
UserDetails user = User.withUsername("alice")
    .password(encodedPassword)
    .authorities("ROLE_USER", "orders:read")
    .disabled(false)
    .accountLocked(false)
    .accountExpired(false)
    .credentialsExpired(false)
    .build();
~~~

Here the builder setters use **negative** semantics:

- disabled(false) corresponds to isEnabled() = true.
- accountLocked(false) corresponds to isAccountNonLocked() = true.
- accountExpired(false) corresponds to isAccountNonExpired() = true.
- credentialsExpired(false) corresponds to isCredentialsNonExpired() = true.

Distinguish builder names from UserDetails names: **builder.accountLocked(true)** means UserDetails.isAccountNonLocked() returns false.

### 8.1. When should you write your own UserDetails?

You can implement UserDetails yourself when you need to place an internal identifier into the principal, for example:

- stable accountId;
- verified tenantId;
- principal type distinguishing user and service identity;
- username and display name having different lifecycles.

However, do not put an entire mutable database entity containing payment data or PII into Authentication. With a custom class, ensure getters, authorities, flags, equals/hashCode when needed, safe serializability, and credential erasure behavior if the object holds sensitive data.

A condensed example of boolean mapping in a custom implementation (not a complete file):

~~~java
@Override
public boolean isAccountNonLocked() {
    return !account.isLocked();
}

@Override
public boolean isEnabled() {
    return account.isEnabled();
}

@Override
public boolean isCredentialsNonExpired() {
    return account.getPasswordExpiresAt() == null ||
        account.getPasswordExpiresAt().isAfter(Instant.now());
}
~~~

These fragments assume account and Instant already exist/are imported. In production, consider evaluating status at lookup time and the lifetime of Authentication/session/token.

## 9. Runnable Project: UserDetails with All Four Statuses

The demo builds an in-memory account source resembling a database table, maps it to UserDetails, and uses DaoAuthenticationProvider. Each lookup returns **a new UserDetails object** to avoid sharing a mutable principal with cached data; sample account rows keep password hashes and flags separately.

Endpoints:

- **GET /api/public**: allows anonymous access.
- **GET /api/me**: requires successful authentication, returns sample username and authorities.
- **GET /api/ops**: requires ROLE_OPS.

Provided accounts:

| Username | Demo password | Authorities | Status |
| --- | --- | --- | --- |
| alice | demo-pass | ROLE_USER, orders:read | Active. |
| ops | demo-pass | ROLE_OPS, orders:read | Active, allowed into /api/ops. |
| locked | demo-pass | ROLE_USER | Account locked. |
| disabled | demo-pass | ROLE_USER | Account disabled. |
| expired | demo-pass | ROLE_USER | Account expired. |
| password-expired | demo-pass | ROLE_USER | Credentials expired. |

**This is a learning example**, not a production account list. Real passwords must be managed and rotated securely; this demo does not provide registration/password-change/MFA flows.

### 9.1. Requirements and directory structure

- JDK 17+.
- Maven 3.9+ or Maven Wrapper.
- Port 8080 free.
- curl/curl.exe to test HTTP.

~~~text
user-details-demo/
  pom.xml
  src/main/java/com/example/userdetails/
    UserDetailsDemoApplication.java
    ApiController.java
    DemoAccountService.java
    SecurityConfig.java
  src/test/java/com/example/userdetails/
    UserDetailsContractTests.java
~~~

The package name in all Java sources is **com.example.userdetails**. Paths and classes must match for Java compilation and Spring Boot component scanning.

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>user-details-demo</artifactId>
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

**Dependency explanation:**

- spring-boot-starter-web: Spring MVC, Servlet container, and JSON responses.
- spring-boot-starter-security: filter chain, UserDetails, DaoAuthenticationProvider, PasswordEncoder.
- spring-boot-starter-test and spring-security-test: JUnit 5, Spring Boot Test, MockMvc, and HTTP Basic test utilities.

Do not add spring-boot-starter-webflux to this demo: this is a **Servlet** application. In a WebFlux server, synchronous UserDetailsService is replaced by the appropriate reactive mechanism and security configuration uses ServerHttpSecurity.

### 9.3. UserDetailsDemoApplication.java

~~~java
package com.example.userdetails;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UserDetailsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(UserDetailsDemoApplication.class, args);
    }
}
~~~

The main class in the root package allows Spring Boot to scan @RestController, @Service, and @Configuration in the same package.

### 9.4. DemoAccountService.java

This is the sample user source. **AccountRow** simulates a database row: username, hash, permissions, and four flags with **positive semantics** to avoid confusion in the schema. In loadUserByUsername, we map the flags to the UserDetails builder.

~~~java
package com.example.userdetails;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class DemoAccountService implements UserDetailsService {

    private final Map<String, AccountRow> accounts;

    public DemoAccountService(PasswordEncoder encoder) {
        this.accounts = Map.of(
            "alice", row("alice", encoder,
                List.of("ROLE_USER", "orders:read"), true, true, true, true),
            "ops", row("ops", encoder,
                List.of("ROLE_OPS", "orders:read"), true, true, true, true),
            "locked", row("locked", encoder,
                List.of("ROLE_USER"), true, false, true, true),
            "disabled", row("disabled", encoder,
                List.of("ROLE_USER"), false, true, true, true),
            "expired", row("expired", encoder,
                List.of("ROLE_USER"), true, true, false, true),
            "password-expired", row("password-expired", encoder,
                List.of("ROLE_USER"), true, true, true, false)
        );
    }

    private static AccountRow row(
            String username,
            PasswordEncoder encoder,
            List<String> authorities,
            boolean enabled,
            boolean nonLocked,
            boolean nonExpired,
            boolean credentialsNonExpired) {
        return new AccountRow(
            username,
            encoder.encode("demo-pass"),
            List.copyOf(authorities),
            enabled,
            nonLocked,
            nonExpired,
            credentialsNonExpired
        );
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountRow account = accounts.get(username);

        if (account == null) {
            throw new UsernameNotFoundException("Account not found");
        }

        // Create a NEW UserDetails snapshot for each lookup.
        // Source AccountRow data keeps the password hash separately.
        return User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities().toArray(String[]::new))
            .disabled(!account.enabled())
            .accountLocked(!account.accountNonLocked())
            .accountExpired(!account.accountNonExpired())
            .credentialsExpired(!account.credentialsNonExpired())
            .build();
    }

    private record AccountRow(
            String username,
            String passwordHash,
            List<String> authorities,
            boolean enabled,
            boolean accountNonLocked,
            boolean accountNonExpired,
            boolean credentialsNonExpired) {
    }
}
~~~

**Key points in the code:**

1. The Map is a sample account store, **not a real database**.
2. encoder.encode("demo-pass") runs when creating the AccountRows; each account holds its own BCrypt hash. We do not call encode again during user lookup.
3. List.copyOf(authorities) keeps the source permission list unmodifiable via normal references.
4. When the user does not exist, UsernameNotFoundException is thrown.
5. A **fresh** UserDetails is created from AccountRow on every load. This avoids certain bugs where the password in UserDetails is erased after authentication and mutates a shared cached object.
6. .disabled(!enabled) and .accountLocked(!nonLocked) invert the booleans in the right direction; similarly for accountExpired and credentialsExpired.
7. ROLE_OPS is an explicitly granted authority, not automatically present because the username is ops.
8. This lesson does not check multi-tenant conditions. With a real database, you must query within a trusted identity scope and manage expiration and status consistently with policy.

**Why is the AccountRow record different from UserDetails?** The record describes the source data; UserDetails is a projection serving Spring Security. Never return a record containing a password hash from a REST Controller.

### 9.5. SecurityConfig.java

~~~java
package com.example.userdetails;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AuthenticationManager authenticationManager(
            DemoAccountService accounts,
            PasswordEncoder encoder) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider();
        provider.setUserDetailsService(accounts);
        provider.setPasswordEncoder(encoder);

        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager manager) throws Exception {

        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/ops").hasRole("OPS")
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

**Explanation of each bean:**

- PasswordEncoder creates BCrypt to protect password hashes.
- DaoAuthenticationProvider wires together DemoAccountService and encoder.
- ProviderManager receives the provider to execute AuthenticationManager.authenticate(...).
- http.authenticationManager(manager) attaches the manager to the HttpSecurity being configured, avoiding reliance on guesswork about automatic managers in multi-configuration apps.
- /api/public is public only for HTTP GET.
- /api/me only requires an authenticated identity.
- /api/ops requires ROLE_OPS; a valid user with ROLE_USER still gets 403.
- anyRequest().denyAll() blocks undeclared URLs/methods.
- HTTP Basic uses sample username/password; on a real network, HTTPS, secret policies, and an appropriate identity mechanism are required.

**Do not disable default CSRF** in the demo. All three endpoints perform only GET. When adding POST/PUT/PATCH/DELETE with browsers/cookies or auto-sent HTTP Basic credentials, you must design and test CSRF according to the threat model. Never resolve a 403 issue by blindly disabling CSRF.

**Version note:** The no-arg constructor of DaoAuthenticationProvider and setters in the illustrative code match the Spring Security 6.3.x line managed by Spring Boot 3.3.6. For newer lines, check the exact version Javadoc and adjust if initialization APIs change.

### 9.6. ApiController.java

~~~java
package com.example.userdetails;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    public Map<String, Object> currentUser(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", auth.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/api/ops")
    public Map<String, String> opsOnly() {
        return Map.of("message", "ops");
    }
}
~~~

Spring Security has already authenticated before the /api/me controller runs; username and authorities are taken from the Authentication built from trusted source data. The demo API prints only minimal info for observation. Never send the entire UserDetails object as JSON: it can expose password hashes, internal states, or data not meant for the client.

### 9.7. Starting the application

In the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

If the server starts successfully, it listens by default on **http://localhost:8080**. The commands below use **curl.exe** on Windows PowerShell; on Linux/macOS replace with curl.

**Test the public endpoint:**

~~~powershell
curl.exe -i http://localhost:8080/api/public
~~~

Main result:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"message":"public"}
~~~

Other headers may appear, and header order is not fixed.

**Test the login-required endpoint without sending credentials:**

~~~powershell
curl.exe -i http://localhost:8080/api/me
~~~

The result is typically **401 Unauthorized** and an HTTP Basic challenge header such as **WWW-Authenticate: Basic ...**.

**Test the active alice account:**

~~~powershell
curl.exe -i -u alice:demo-pass http://localhost:8080/api/me
~~~

The response body looks like:

~~~json
{
  "username": "alice",
  "authorities": ["ROLE_USER", "orders:read"]
}
~~~

Because the code sorts authorities before returning, the array element order above is defined in the demo. Key order in a JSON object should not be treated as a contract.

**Test the ROLE_OPS endpoint:**

~~~powershell
curl.exe -i -u alice:demo-pass http://localhost:8080/api/ops
curl.exe -i -u ops:demo-pass http://localhost:8080/api/ops
~~~

- Alice authenticates successfully but lacks ROLE_OPS, typically receiving **403**.
- Ops authenticates successfully and has ROLE_OPS, receiving **200** with JSON {"message":"ops"}.

### 9.8. Test the four invalid statuses

~~~powershell
curl.exe -i -u locked:demo-pass http://localhost:8080/api/me
curl.exe -i -u disabled:demo-pass http://localhost:8080/api/me
curl.exe -i -u expired:demo-pass http://localhost:8080/api/me
curl.exe -i -u password-expired:demo-pass http://localhost:8080/api/me
~~~

**All four are expected to receive 401 under HTTP Basic**, even though the user's entered password matches the hash. The reason is that UserDetails marks the account as not meeting status conditions.

Do not build a production API returning messages like "this username is locked" for all unauthenticated requests: balance UX against user enumeration risk. Some applications provide a separate recovery channel with additional identity verification.

**Self-check reference:**

| Request | Expected HTTP | Explanation |
| --- | --- | --- |
| GET /api/public without credentials | 200 | URL is permitAll. |
| GET /api/me without credentials | 401 | Missing authentication. |
| GET /api/me with alice + right password | 200 | All four status flags true, password matches. |
| GET /api/me with alice + wrong password | 401 | BadCredentialsException. |
| GET /api/me with locked | 401 | isAccountNonLocked=false; provider rejects. |
| GET /api/me with disabled | 401 | isEnabled=false; provider rejects. |
| GET /api/me with expired | 401 | isAccountNonExpired=false; provider rejects. |
| GET /api/me with password-expired | 401 | isCredentialsNonExpired=false; provider rejects. |
| GET /api/ops with alice | 403 | Authenticated but missing ROLE_OPS. |
| GET /api/ops with ops | 200 | Has ROLE_OPS. |

The status codes above reflect the **SecurityFilterChain + HTTP Basic** of the demo and do not mean every Spring Security app returns the same status: form login may redirect, and a custom entry point may return different JSON.

## 10. Comprehensive Testing with MockMvc and JUnit

Create file **src/test/java/com/example/userdetails/UserDetailsContractTests.java**. The tests distinguish three levels:

1. **Data contract** returned from UserDetailsService: username, password hash, authorities, and flags.
2. **Provider/AuthenticationManager**: exceptions for wrong passwords and account statuses.
3. **HTTP/SecurityFilterChain**: 200/401/403 and principal info in the response body.

~~~java
package com.example.userdetails;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UserDetailsContractTests {

    @Autowired DemoAccountService accounts;
    @Autowired PasswordEncoder encoder;
    @Autowired AuthenticationManager manager;
    @Autowired MockMvc mvc;

    private Authentication request(String user, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            user, password);
    }

    @Test
    void userDetailsHasUsernameAndAuthorities() {
        UserDetails alice = accounts.loadUserByUsername("alice");

        assertThat(alice.getUsername()).isEqualTo("alice");
        assertThat(alice.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("ROLE_USER", "orders:read");
        assertThat(alice.isEnabled()).isTrue();
        assertThat(alice.isAccountNonLocked()).isTrue();
        assertThat(alice.isAccountNonExpired()).isTrue();
        assertThat(alice.isCredentialsNonExpired()).isTrue();
    }

    @Test
    void storedPasswordIsHashAndEncoderMatchesRawInput() {
        UserDetails alice = accounts.loadUserByUsername("alice");

        assertThat(alice.getPassword()).isNotEqualTo("demo-pass");
        assertThat(encoder.matches("demo-pass", alice.getPassword()))
            .isTrue();
        assertThat(encoder.matches("wrong", alice.getPassword()))
            .isFalse();
    }

    @Test
    void lockedUserHasNonLockedFalse() {
        UserDetails locked = accounts.loadUserByUsername("locked");
        assertThat(locked.isAccountNonLocked()).isFalse();
        assertThat(locked.isEnabled()).isTrue();
    }

    @Test
    void disabledUserHasEnabledFalse() {
        UserDetails disabled = accounts.loadUserByUsername("disabled");
        assertThat(disabled.isEnabled()).isFalse();
    }

    @Test
    void expiredUserHasNonExpiredFalse() {
        UserDetails expired = accounts.loadUserByUsername("expired");
        assertThat(expired.isAccountNonExpired()).isFalse();
    }

    @Test
    void expiredPasswordHasCredentialsNonExpiredFalse() {
        UserDetails user = accounts.loadUserByUsername("password-expired");
        assertThat(user.isCredentialsNonExpired()).isFalse();
        assertThat(user.isAccountNonExpired()).isTrue();
    }

    @Test
    void unknownUserIsNotFoundAtDataSource() {
        assertThatThrownBy(
            () -> accounts.loadUserByUsername("does-not-exist"))
            .isInstanceOf(UsernameNotFoundException.class);
    }

    @Test
    void validPasswordAuthenticatesAndReturnsAuthorities() {
        Authentication result =
            manager.authenticate(request("alice", "demo-pass"));

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("alice");
        assertThat(result.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("ROLE_USER", "orders:read");
    }

    @Test
    void wrongPasswordIsRejected() {
        assertThatThrownBy(
            () -> manager.authenticate(request("alice", "wrong")))
            .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void lockedAccountIsRejectedByDaoProvider() {
        assertThatThrownBy(
            () -> manager.authenticate(request("locked", "demo-pass")))
            .isInstanceOf(LockedException.class);
    }

    @Test
    void disabledAccountIsRejectedByDaoProvider() {
        assertThatThrownBy(
            () -> manager.authenticate(request("disabled", "demo-pass")))
            .isInstanceOf(DisabledException.class);
    }

    @Test
    void expiredAccountIsRejectedByDaoProvider() {
        assertThatThrownBy(
            () -> manager.authenticate(request("expired", "demo-pass")))
            .isInstanceOf(AccountExpiredException.class);
    }

    @Test
    void expiredCredentialsAreRejectedByDaoProvider() {
        assertThatThrownBy(
            () -> manager.authenticate(
                request("password-expired", "demo-pass")))
            .isInstanceOf(CredentialsExpiredException.class);
    }

    @Test
    void publicEndpointIsAccessibleAnonymously() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void privateEndpointRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void privateEndpointAcceptsActiveUser() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"))
            .andExpect(jsonPath("$.authorities[1]").value("orders:read"));
    }

    @Test
    void privateEndpointRejectsWrongBasicPassword()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void lockedBasicAccountGetsUnauthorized() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("locked", "demo-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void roleUserDoesNotGetOpsAccess() throws Exception {
        mvc.perform(get("/api/ops")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void opsRoleGetsOpsAccess() throws Exception {
        mvc.perform(get("/api/ops")
                .with(httpBasic("ops", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("ops"));
    }

    @Test
    void fakeRoleHeaderCannotAuthenticate() throws Exception {
        mvc.perform(get("/api/ops")
                .header("X-Role", "OPS"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void undeclaredRouteIsDeniedEvenWithValidUser()
            throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**22 tests** cover the contract, password hash, 4 account flags, missing-user lookup, manager/provider, HTTP Basic, and authorization. In a real application with a database, add integration tests for queries, tenants, password upgrades, concurrency, account state changes, and ensuring no side effects occur when rejected.

This is a test suite provided for learners to **run locally**, not a Maven result executed while writing the documentation. If tests fail with different dependencies/versions, read the stack trace and check imports, account flags, security chain configuration, and endpoint matching before changing policy.

### 10.1. What does each testing layer prove?

| Testing layer | What it proves | What it does not itself prove |
| --- | --- | --- |
| Direct UserDetailsService | Correct username, hash, authorities, and flags data. | That password was checked or token was verified. |
| Direct AuthenticationManager | DaoAuthenticationProvider uses hash and status, rejects invalid credentials. | HTTP filters, cookies/sessions, TLS, and gateway. |
| MockMvc | Request runs through SecurityFilterChain/test Controller, matching status and body. | Reverse proxy, ingress, production user store, real database, and network. |
| HTTP curl with running app | Response via real HTTP stack on localhost. | Production TLS/IdP policies and owner/tenant permissions on real data. |

Keep both **success and failure tests**. A single successful login test is not enough to prove locked/disabled/password-expired are not bypassed.

## 11. When Does UserDetails Differ from Authentication Principal?

In username/password authentication using DaoAuthenticationProvider, the principal in a successful Authentication is typically **UserDetails** or a username String depending on configuration. However, **not every authentication mechanism uses UserDetails**.

Examples:

- HTTP Basic/form login via DaoAuthenticationProvider: UserDetails is usually loaded and placed into Authentication.
- OAuth2 login/OIDC: principal may be OAuth2User or OidcUser.
- JWT Resource Server: principal may be Jwt or a type created by a converter.
- Service identity/mTLS: principal may be a specialized type per authentication mechanism.
- Anonymous request: principal may represent anonymous, not an account in the user store.

Therefore the code below is brittle:

~~~java
// Anti-pattern: not valid for every Authentication type.
UserDetails user = (UserDetails) authentication.getPrincipal();
~~~

If a real system uses multiple login methods, the principal may be Jwt or another type → ClassCastException. When you only need the username, typically use **Authentication.getName()**; when you need userId/tenant, design a standardized principal adapter per verified identity mechanism.

### 11.1. Is UserDetails a database entity?

**Not required, and usually better separated.** A database entity may mutate with ORM/sessions and contain sensitive info; UserDetails is a projection sufficient for security.

One way to separate layers:

~~~text
Database entity / repository
         |
         v
AccountService / UserDetailsService
         |
         v
UserDetails snapshot
         |
         v
AuthenticationManager / provider
         |
         v
SecurityContext Authentication
         |
         v
Domain service checks object-level permissions
~~~

Data such as monetary balances, order lists, addresses, reset token hashes, or history should not be stuffed into the principal. When code needs a user profile, call a Service/repository with the verified id and appropriate access policy.

## 12. Credentials Erasure and Protecting Password Hashes in Memory

After successful authentication, ProviderManager by default attempts to **erase sensitive credentials** from the resulting Authentication if the implementation supports **CredentialsContainer**. This limits raw passwords from lingering in SecurityContext, sessions, or later logs.

However, distinguish carefully:

- **Raw password** from request: should be retained for the shortest time possible.
- **Password hash** retrieved from UserDetails: still sensitive data, must never be returned via API.
- **Authentication credentials**: may be erased after success.
- **Principal/UserDetails**: some implementations like User may participate in credential erasure; behavior depends on the class and how objects are shared.

### 12.1. Common cache bug

Suppose UserDetailsService returns the **exact mutable UserDetails object held in a cache**. A post-authentication flow erases credentials on the principal, causing the cached object's password hash to be wiped. The next login retrieving the same object may fail because getPassword() no longer has a hash.

Approaches:

1. Return a dedicated **UserDetails copy/snapshot** per Authentication when needed.
2. Cache AccountRow/domain DTOs holding the hash separately, then map to a fresh UserDetails on lookup.
3. Inspect actual UserDetails, CredentialsContainer, and UserCache implementations when adding caching.
4. Write tests for **multiple consecutive logins**, checking that the user source is not mutated unexpectedly.
5. Only change eraseCredentialsAfterAuthentication when there is a clear security/performance reason and after risk analysis; disabling credential erasure makes sensitive data live longer.

In the demo, **AccountRow holds the hash**, while loadUserByUsername builds a new UserDetails. This demonstrates a data boundary to avoid accidentally mutating the account source via credential erasure on Authentication.

**Do not conclude that the hash has vanished from the JVM after eraseCredentials() is called.** A String copy, cache, or log may still exist; GC offers no guarantee of immediate byte wiping. Additional controls over logs, dumps, memory access, and secret management are still required.

## 13. Account Status Changing While the User Is Already Logged In

A system may use session cookies or time-limited access tokens. When an account is locked/disabled in the database, what happens to a previously authenticated session?

**By default**, not every request using a session/JWT calls UserDetailsService and checks the four flags again.

- **HTTP Basic** typically sends credentials with each request; the provider can load the user and check status when authentication is needed.
- **Form login + session** may keep the authenticated Authentication in SecurityContext across many requests; changing account status in the DB does not necessarily terminate the session immediately.
- **JWT access token** is typically verified by signature/claims, without automatically loading UserDetails or knowing the account was just locked. Immediate revocation requires dedicated design.
- **Cached authorities** may become stale if roles/permissions change without refreshing the principal or token.

Solutions depend on the threat model: session invalidation, token revocation/introspection, short-lived tokens, dynamic status checks for sensitive actions, permission versioning, and forced re-login mechanisms. The system should define an SLA for permission revocation and test across multiple instances.

**UserDetails status is a snapshot at load time.** It is not a synchronization channel guaranteeing that every account change immediately affects all sessions/tokens.

## 14. Common Mistakes When Implementing UserDetails

### 14.1. Inverting nonLocked and accountLocked

~~~java
// If entity.locked=true means locked, this line is WRONG:
return entity.isLocked(); // inside isAccountNonLocked()

// The right semantics must be:
return !entity.isLocked();
~~~

This is an easy mistake to make because one side stores locked while the other asks nonLocked.

### 14.2. Storing raw passwords in getPassword()

If an implementation returns a raw password, the system may inadvertently retain secrets in the principal/session and PasswordEncoder will behave incorrectly. Passwords must be stored and returned as hashes compatible with the encoder.

### 14.3. Re-hashing passwords in loadUserByUsername

If the database already holds a BCrypt hash, do not call encoder.encode(hash) again; doing so creates a new hash of the old hash string and makes matches(raw, doubleHash) fail. Only encode passwords when creating/changing credentials per workflow.

### 14.4. Checking passwords inside UserDetailsService

UserDetailsService is responsible for lookup; let DaoAuthenticationProvider call PasswordEncoder.matches per the contract. If you want a special authentication mechanism, design an appropriate AuthenticationProvider rather than hiding password logic inside the user lookup service.

### 14.5. Returning null when no user exists

UserDetailsService should throw UsernameNotFoundException. Returning null can lead to confusing framework errors and violates the contract.

### 14.6. Granting permissions from client input

Do not build authorities from an "X-Role: ADMIN" request header or an unpoliced role field in a registration form. Permissions must be loaded from a trusted source and consider role assignment, tenant, scope, audit, and least privilege.

### 14.7. Assuming ROLE_USER includes all permissions

Roles, permissions, and scopes are distinct authorities. ROLE_USER does not automatically include orders:read; to use both, they must be explicitly granted or mapped according to policy.

### 14.8. Not checking account flags in a custom provider

DaoAuthenticationProvider handles status when properly configured. A **custom AuthenticationProvider** may not automatically check isEnabled()/isAccountNonLocked() if the author forgets. When using a custom provider, explicitly decide whether to use UserDetails, which statuses to check, and write locked/disabled/expired tests.

### 14.9. Returning UserDetails directly from a REST API

UserDetails typically contains a password hash and internal flags. Do not serialize this object intact; return a selective response DTO, such as username and displayable permissions when business logic requires it.

### 14.10. Confusing 401 and 403

- Typical 401: missing credentials or credentials/account state failed authentication checks.
- Typical 403: valid Authentication but lacking permission, or another mechanism such as CSRF blocked the request.
- 302 to login: may appear with browser form login.
- 404: may be due to a non-existent route/object or a resource-hiding policy.

Do not infer the exact reason an account was blocked solely from the HTTP status. Separate filter/provider/authorization layers in internal security logs.

### 14.11. Creating UserDetails with isEnabled() always true

If the database stores a disabled state yet the implementation ignores it or always returns true, a banned account can still log in with its old password. Status must come from a trusted source, stay updated, and be tested.

### 14.12. Relying on mutable username/email as ownerId

Email can change; a userId path parameter can be forged. For data permissions, use stable IDs, verified tenants, and object-level authorization checks.

### 14.13. Locking accounts after wrong passwords without considering DoS

Automatically locking an account permanently after a few wrong attempts can be exploited by attackers to block legitimate users. Design rate limiting, unlock flows, fraud detection, and load measurement per policy.

### 14.14. Not testing duplicate names, case sensitivity, and tenants

A database may use a case-insensitive collation while the application uses a case-sensitive Map. If the same username exists across multiple tenants, you must determine the right lookup key; never look up one user and grant access in another tenant.

### 14.15. Not testing permission/status updates after login

Active sessions/tokens may carry stale authorities or statuses. You need a revocation policy and tests covering the Authentication lifecycle, not just a single fresh login test.

## 15. When Combining with OAuth2, JWT, and LDAP

UserDetails is crucial for **DaoAuthenticationProvider** and username/password, yet Spring Security has many other authentication models:

| Mechanism | Is UserDetails always used? | Key point to understand |
| --- | --- | --- |
| Form login + DAO | Usually yes. | UserDetailsService + PasswordEncoder + account flags. |
| HTTP Basic + DAO | Usually yes. | BasicAuthenticationFilter passes credentials to DAO. |
| LDAP | Depends on provider and mapper. | User/authority data may come from LDAP; appropriate mapping/status is needed. |
| OAuth2/OIDC login | Not necessarily. | Principal is usually OAuth2User/OidcUser and other token metadata. |
| JWT Resource Server | Not by default. | JWT is processed by decoder/converter; UserDetails flags are not automatically checked. |
| Opaque token Resource Server | Not by default. | Token introspection and policy-based authority mapping. |
| WebFlux reactive username/password | Uses corresponding contract, possibly ReactiveUserDetailsService. | Returns Mono<UserDetails>, manages security context via Reactor. |
| Machine-to-machine / mTLS | Not necessarily. | Principal may represent a service, not a user in the users table. |

When migrating from Basic to JWT, if a disabled account previously caused DAO to reject login, a JWT decoder checking only token signature/expiry **does not automatically ensure immediate account disabling mid-token lifecycle**. Design revocation or dynamic account status checks if business requirements demand it.

Similarly, a resource server may use JWT claims containing roles/scopes. It does not automatically use UserDetails#getAuthorities() from the database without explicit mapping and active lookup.

## 16. From In-Memory to a Real Database: Design Checklist

If implementing with Spring Data JPA/JDBC, define:

1. **Schema**: username unique within the right scope, password_hash, enabled, locked, expires_at, credentials_expires_at; never store raw passwords.
2. **Roles/permissions**: join tables or trusted source; avoid eager loading an entire sensitive object graph just to return authorities.
3. **Transactions and consistency**: an account disabled concurrently while a login request is processing needs an explicit policy decision.
4. **Password encoder**: algorithm, work factor, version/identifier, and migration from legacy hashes.
5. **Lookup errors**: missing username → UsernameNotFoundException; DB unavailable → appropriate service error, never automatically returning a default user.
6. **Cache**: TTL and invalidation on password/role/locked flag changes; never cache mutable UserDetails and let eraseCredentials mutate the source.
7. **Audit**: when account status changed and who approved it; never log password hashes or full tokens.
8. **Lockout**: failure count policy, rate limiting, anti-account-enumeration, and unlock flow.
9. **Multi-tenant**: identify the right tenant, permissions per owner/tenant and resource; a valid login does not mean access to every row.
10. **Revocation**: how existing sessions/tokens are affected when permissions change or account is disabled.
11. **Tests**: missing username, wrong password, four flags, low privilege, role changes, missing object permissions, duplicate/case/Unicode data.
12. **Operations**: HTTPS, secret store, DB least privilege, backups, log redaction, rotation, and keeping Spring Security updated.

With Spring Data JPA, a UserDetailsService implementation typically uses a repository to find the account and maps the entity to UserDetails. There is no need to put password checking into the repository; keep authentication in AuthenticationProvider.

## 17. Debugging Procedure When Password Is Right Yet 401 Still Occurs

When a user is certain they entered the right password yet /api/me still returns 401, check in order:

1. **Which SecurityFilterChain applies?** Do URL/method match the chain using Basic/DAO, or did it fall into a different chain?
2. **Did the authentication filter read the credentials?** Is the Authorization: Basic header properly formatted, encoded, and forwarded by any gateway to the backend?
3. **Does AuthenticationManager have DaoAuthenticationProvider?** Does the provider used by the filter have the right UserDetailsService and PasswordEncoder?
4. **Did username lookup find the right account?** Check case, Unicode, tenant, and DB source; avoid printing sensitive info.
5. **Is getPassword() a hash of the right algorithm?** Not a raw password, double-hash, or wiped hash due to cache/credential erasure?
6. **Does PasswordEncoder.matches work?** Compare raw input with stored hash; check prefix if using DelegatingPasswordEncoder.
7. **Are the four flags right?** isEnabled, isAccountNonLocked, isAccountNonExpired, isCredentialsNonExpired; distinguish inverted DB flags.
8. **Was the account status changed or is cache stale?** Consider data lifecycle, TTL, and consistency.
9. **What is the actual exception?** BadCredentialsException, LockedException, DisabledException, AccountExpiredException, or CredentialsExpiredException? Check secret-redacted internal logs.
10. **Did a proxy/entry point alter the HTTP response?** 401/302/403 can come from different layers; identify the first rejecting source.
11. **Is authorization involved?** If the provider authenticated properly yet a role is missing, the endpoint usually returns 403, not due to password.
12. **Can it be reproduced with a test?** Use AuthenticationManager to test status directly, then MockMvc to check exact HTTP status.

**Do not resolve a 401 error by using permitAll or disabling SecurityFilterChain.** Fix the actual root cause: UserDetails data, encoder, status, provider wiring, or client policy.

## 18. Self-Practice Exercises

**Exercise 1 — Identify the contract.** List all seven core methods of UserDetails. Categorize the methods returning String, Collection, and boolean; explain why the three Non... flags are normally true.

**Exercise 2 — Boolean inversion.** A database has a column locked=true. Write the correct isAccountNonLocked(). Create tests for locked=false and locked=true.

**Exercise 3 — Explain a password bug.** A developer stores a BCrypt hash in the database, yet inside loadUserByUsername calls encoder.encode(hash) and returns the new hash. Why is the right password rejected?

**Exercise 4 — Authorities.** A user has ROLE_USER and orders:read. Does hasRole("ADMIN") pass? Does hasAuthority("orders:read") pass? Why does ROLE_USER not automatically include all permissions?

**Exercise 5 — Status.** Alice has the right password yet isCredentialsNonExpired=false. Which exception typically occurs with DaoAuthenticationProvider? What status does HTTP Basic usually return?

**Exercise 6 — UsernameNotFound.** When loadUserByUsername does not find an account, should it return null or throw UsernameNotFoundException? What public error might AuthenticationManager return?

**Exercise 7 — In-memory and production.** Why are InMemoryUserDetailsManager or a sample Map suitable for labs yet insufficient for real identity management?

**Exercise 8 — Data source and principal.** A database entity contains username, password_hash, phone, paymentInfo, tenantId, and 20 other fields. Design a UserDetails projection carrying only needed fields, then explain how a Service fetches business data by trusted ID.

**Exercise 9 — Account lifecycle.** A user was just disabled in the database yet still holds a JWT valid for 30 more minutes. Why might changing UserDetails.isEnabled() in the DB not block the API immediately? Propose an appropriate revocation strategy.

**Exercise 10 — Caching.** A mutable UserDetails is cached and ProviderManager erases credentials after login. What error might occur on the next login? Why does the demo create a new snapshot?

**Exercise 11 — Multi-tenant.** Two tenants share the same username "alice". Is calling loadUserByUsername("alice") alone enough to find the right person? Propose a trusted source for tenant identification.

**Exercise 12 — Testing.** Add a test where a disabled account in HTTP Basic receives 401, then add a direct provider test throwing DisabledException to distinguish HTTP response from authentication-layer error.

### Summary Checklist

- **UserDetails describes an account for security**, does not itself verify passwords, and is not the entire business entity.
- **getUsername()** is the identifier per lookup policy; **getPassword()** typically returns the stored hash.
- **getAuthorities()** returns GrantedAuthority; ROLE_ and permission strings must be granted from a trusted source.
- **isEnabled() = true**, **isAccountNonLocked() = true**, **isAccountNonExpired() = true**, **isCredentialsNonExpired() = true** is the normal state.
- **Account locked, disabled, expired, credentials expired** have different meanings and can produce different AuthenticationExceptions.
- **UserDetailsService only looks up**, **DaoAuthenticationProvider + PasswordEncoder** verify credentials and account status.
- **UsernameNotFoundException** is the signal that lookup found no user; APIs should not reveal whether an account exists.
- **Roles differ from object permissions**: authenticated()/hasRole does not replace owner/tenant checks in domain Services.
- **UserDetails is a snapshot**; existing sessions/JWTs may remain valid after account status changes unless a revocation mechanism exists.
- **Never serialize password hashes, raw passwords, or the entire UserDetails to an HTTP response**.
- **Test all four flags across data, provider, and HTTP layers**, not just 200 login.

## References

- [Spring Security — UserDetails JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html): username, password, authorities, and four account statuses.
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): user lookup contract.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): combining UserDetailsService, PasswordEncoder, and UserDetails.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): PasswordEncoder, algorithms, and credential storage.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): ProviderManager, Authentication, and SecurityContext.

**Version note:** Example code uses Spring Boot 3.3.6 and Spring Security 6.3.x, suitable for illustrating APIs in this lesson. In real projects, choose a supported line, apply patches, and verify API/constructor details against current dependency versions.

## Conclusion

**UserDetails is the account description serving username/password authentication**: getUsername() identifies the account, getPassword() supplies the hash, getAuthorities() supplies granted permissions, and the four status flags report whether the account is eligible for use. UserDetailsService is responsible for loading data from a trusted source, DaoAuthenticationProvider uses PasswordEncoder and account checks to verify, and Spring Security turns the result into Authentication and enforces authorization. Separating these responsibilities, mapping boolean signs correctly, protecting password hashes, and testing every status help prevent login bugs, secret leaks, and misgranted permissions.
