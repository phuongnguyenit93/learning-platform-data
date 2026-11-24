# Distinguishing a Business Account from a Security Principal

Imagine a document management application has an account in its database:

~~~text
accounts
  id            = 101
  login_email   = "mai@example.test"
  display_name  = "Mai Nguyen"
  tenant_id     = "company-a"
  status        = "ACTIVE"
  password_hash = "{bcrypt}..."  (format illustration only)
~~~

Mai logs in successfully. When handling `GET /me`, Spring Security provides a **principal** representing the authenticated identity. Beginners often want to write `Account account = (Account) authentication.getPrincipal();` and then use this account directly to read or modify data. That way of thinking can be wrong in terms of both **Java type** and **trust boundaries and data lifecycle**.

A **business account** is the object the system manages to carry out business operations: profile, organization relationships, status, ownership, history, and data constraints. A **principal in Spring Security** is the identity representation attached to a single authentication or request in the **security context**; it can be a username string, `UserDetails`, `Jwt`, or a custom type.

The two objects can refer to the **same person or service**, but they are not required to share the same class, the same data, the same lifetime, or the same access permissions.

This lesson helps you design a clear boundary between **identity in security** and **account in the domain**, choose a stable identifier for mapping, handle account/multi-tenant changes, and implement a Java 17+ example with Spring Security.

## 1. Four Concepts to Keep Separate

| Concept | Whose responsibility? | Typical data | What cannot be inferred |
| --- | --- | --- | --- |
| **Business account (`Account`)** | Domain/database and business rules | `id`, email, display name, tenant, status, relationships, profile data | Having an `Account` object means already authenticated |
| **Principal** | Identifier in the authentication context | Username, subject ID, `UserDetails`, `Jwt`, `OAuth2User`, custom principal | Principal is always the `Account` entity or always has the latest data |
| **`Authentication`** | Authentication information/request/result in Spring Security | `principal`, `credentials`, `authorities`, status, `details` | Allowed to read all records |
| **`GrantedAuthority`** | Input for authorization | `ROLE_USER`, `DOCUMENT_READ`, `SCOPE_profile` | Having an authority means everyone else's records can also be viewed |

Two useful ways to frame the questions:

- Domain asks: **"Which organization does account 101 belong to, what is its current status, and is it allowed to edit this profile?"**
- Security asks: **"Under which identity is the current request authenticated, by which mechanism, and what authorities does it hold?"**

The bridge between the two sides is usually **a server-verified ID**, such as `accountId=101`, rather than an implicit cast between `Authentication` and a JPA entity.

## 2. A Domain Account Is Business Data, Not a Login Token

An entity/account in an application might look like this:

~~~java
// Simple domain model; not yet a complete JPA entity.
public record Account(
        long id,
        String loginEmail,
        String displayName,
        String tenantId,
        boolean enabled) {
}
~~~

In a real system, `Account` may also store relationships to departments, organizations, approval status, product limits, and update timestamps. Some systems have separate tables:

~~~text
users/accounts           -- account ID, profile, status
login_credentials        -- password hash, login method
external_identities      -- issuer + subject link from SSO
memberships              -- which tenant the user/account belongs to
roles/role_assignments   -- permissions per workspace/organization
audit_events             -- who did what, on which resource
~~~

There is no single mandatory schema. The core principle is that the **domain model is optimized for business operations and the authoritative data source**, while the principal is optimized for identifying the authenticated subject and carrying the **minimal information** needed within the request context.

An `Account` can exist before ever logging in, such as an account created by an administrator or one awaiting activation. Conversely, a `principal` of a machine account, guest user, or external identity may not yet map to an internal `Account` if the application has not allowed creating/linking an account.

**Do not let an entity class decide whether the caller is logged in just because a query found a record.** Finding an account and authenticating are two different operations.

### Domain Statuses That Are Easy to Misunderstand

| Account status | Possible business meaning | Impact on authentication/authorization |
| --- | --- | --- |
| `PENDING` | Email not yet verified or awaiting approval | May not be allowed to log in or may only use limited features |
| `ACTIVE` | Active | Still must authenticate and check permissions per request |
| `SUSPENDED` | Temporarily locked per business workflow | Needs rules to block login and possibly revoke old sessions/tokens |
| `DELETED` | Deleted/deactivated | Must not allow old principals/tokens to continue accessing data |
| `INVITED` | Invited to a tenant but not yet accepted | Does not automatically have permission to view that tenant's data |

Status names and meanings are application choices. Do not take a business enum and assume Spring Security understands it automatically. You must **map statuses to appropriate authentication and authorization policies**, including requests sent before the status change.

## 3. What Is a Principal in Spring Security?

`Authentication` is an interface that extends `java.security.Principal` and has methods such as `getPrincipal()`, `getAuthorities()`, `getCredentials()`, `getDetails()`, `isAuthenticated()`, and `getName()`.

Example when reading:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    Object principal = authentication.getPrincipal();
    String name = authentication.getName();
}
~~~

This is a **code snippet inside a Spring Security Servlet application**, not a standalone Java program; it requires importing `org.springframework.security.core.Authentication` and `org.springframework.security.core.context.SecurityContextHolder`.

The three variables have different meanings:

- `authentication`: the entire authentication state/request in the current context.
- `authentication.getPrincipal()`: the object representing the subject's identity; the actual type depends on the mechanism.
- `authentication.getName()`: the identifying name provided by the `Authentication` implementation; not guaranteed to be `account.id`, the current email, or the display name.

In Spring MVC, you can use `@AuthenticationPrincipal` to inject **the exact principal** as a controller parameter. This annotation solves how to access data in the request; **it does not query the database automatically and does not automatically turn a JWT into a domain Account**.

### What Types Can a Principal Have?

| Authentication mechanism | Common principal | Notes |
| --- | --- | --- |
| Username/password request before verification | Username string supplied by the user | Not yet a trusted authentication result |
| `DaoAuthenticationProvider` after username/password authentication | A `UserDetails` returned by `UserDetailsService` | `UserDetails` can be the default `User` class or custom |
| OAuth2/OIDC login | `OAuth2User` or `OidcUser` | Has external claims/attributes; display name may differ from internal ID |
| Resource Server validating JWT | Defaults typically to `Jwt` | Default `getName()` may map from the `sub` claim |
| HTTP Basic with custom provider | The provider's principal type | Must not blindly cast to `UserDetails` |
| Anonymous authentication | Anonymous placeholder value, which can be a string | Not a real account that has proved its identity |
| Service-to-service/client credentials | Application/service principal | Does not necessarily have a corresponding user in the database |

Do not write:

~~~java
// WRONG: assuming the principal is always a JPA entity / domain Account.
Account account = (Account) authentication.getPrincipal();
~~~

In a system using JWT, `getPrincipal()` can be `Jwt`; in a system using form login, it can be a custom `UserDetails`. The cast above can throw `ClassCastException`. Even if you deliberately put `Account` into the principal, doing so still requires careful design regarding data freshness and protecting sensitive information.

## 4. The Boundary to Visualize: Source of Truth, Projection, and Current Record

An easy-to-control architecture looks like this:

~~~text
                Request from browser/API client
                           |
                           v
              Authentication Mechanism
           (password / JWT / OIDC / mTLS ...)
                           |
                           v
              Verified Authentication
                 principal + authorities
                           |
                           v
                 Identity mapping bridge
       (internal accountId or verified issuer + subject)
                           |
                           v
                Account repository / service
                   -> current record
                   -> membership, tenant, status
                           |
                           v
                  Authorization policy
              (action + resource + context)
                           |
                           v
                  Domain operation / DTO
~~~

In the diagram, the **principal is the identity projection/carrier**, while the repository/service provides the latest and authoritative business information. Principal attributes can be snapshots created at login time or when a token was issued.

Two examples:

1. Mai changes her email from `mai@old.test` to `mai@new.test`. If the domain stores `accountId=101`, document ownership relationships still point to 101. But if the application uses email as the owner key, changing the email easily breaks the link.
2. Mai has her tenant A manager role revoked. A previously issued session/JWT may still contain an old authority or claim. To revoke permissions quickly, the policy must look at current permission data, versioning, token/session invalidation, or a re-check mechanism; do not assume every principal updates immediately on its own.

**An Account record is mutable data; a principal can be stale.** Therefore, for critical decisions such as disbursing money, viewing sensitive records, or changing permissions, you must check the policy at the time of the operation, not solely trust the login-time snapshot.

## 5. Distinguishing Identifier Types: Stable ID, Username, Email, Subject

One person can have multiple names:

| Value | Example | Should it be a long-term internal key? |
| --- | --- | --- |
| System-issued `accountId` | `101` or UUID | **Usually yes**, if the ID is immutable, never reused, and scopes identity properly |
| `username` | `mai.nguyen` | Can change; depends on policy |
| `email` | `mai@example.test` | **Should not** be assumed immutable or unique across time |
| `displayName` | `Mai Nguyễn` | No, for display only |
| JWT `sub` | `oidc-7f9d...` | Stable within an issuer's scope if guaranteed by the IdP; must be paired with `iss` |
| Tenant/membership ID | `tenant-A`, `membership-42` | Identifies a relationship in a specific scope; does not replace account ID |
| Role/authority | `ROLE_USER` | **Not** an identifier |

**Design recommendation:** issue an immutable internal `accountId`, use it as the owner/audit foreign key, and use it to link external identities. Email, display name, and roles are allowed to change independently. In multi-tenant systems, one `accountId` can belong to multiple tenants, so authorization decisions still need the appropriate membership and tenant.

### For SSO/OIDC, Do Not Rely Solely on Email

Two tokens with `sub="123"` coming from **two different issuers** do not automatically represent the same identity. A sensible linking key has the form:

~~~text
external_identity_key = (trustedIssuer, verifiedSubject)

("https://idp-a.example", "123") -> internal accountId=101
("https://idp-b.example", "123") -> internal accountId=709
~~~

For OIDC/JWT, the server must verify the signature, issuer, audience, expiration, and required conditions before using claims for mapping. Do not take `sub` from unverified JSON and treat it as a valid principal. When linking a new SSO identity to an existing account, a proper proof-of-ownership workflow is required; **do not automatically merge two accounts just because their emails match**.

Emails can change, be reassigned, or belong to multiple user spaces. The `iss + sub` key is usually more suitable for identifying an external subject; the internal ID is what anchors into the domain.

## 6. UserDetailsService Is Not AccountRepository

In password authentication, `DaoAuthenticationProvider` typically calls `UserDetailsService.loadUserByUsername(username)` to retrieve a `UserDetails`, then uses `PasswordEncoder` to verify the credentials. `UserDetailsService` is an **adapter for Spring Security's needs**, and does not require the business repository to share the same interface.

Model example:

~~~text
POST /login with username + password
             |
             v
     DaoAuthenticationProvider
             |
    +--------+----------+
    |                   |
    v                   v
UserDetailsService   PasswordEncoder
    |                 matches(...)
    v
AccountRepository
    |
    v
Account + credential hash + trusted status
    |
    v
Custom AccountPrincipal implements UserDetails
    |
    v
Successful Authentication carrying AccountPrincipal
    |
    v
Subsequent requests use accountId -> AccountService -> current Account
~~~

Division of responsibilities:

- `AccountRepository`: finds accounts, persists data, handles transactions and business relationships.
- `UserDetailsService`: translates authentication data into a `UserDetails` that the provider understands; does not return `null` when not found.
- `PasswordEncoder`: `matches(raw, storedHash)`; raw passwords must not be stored.
- `AuthenticationProvider`: verifies credentials, checks status, and produces the authenticated result.
- `AccountPrincipal` (a name you choose): holds the **stable internal ID** along with minimal security information.
- `AccountService`: loads the current business status and relationships at the time of use.
- Authorization policy: checks action/resource/tenant, never assuming "logged in means can view everything".

Writing a custom `UserDetails` is not mandatory in every application. If `UserDetails#getUsername()` is itself the stable ID by project contract, you can map from that name. If username/email can change, a custom principal with a dedicated `accountId` is usually clearer.

### Should You Put a Raw JPA Entity Inside the Principal?

Sometimes it is technically possible, but it easily causes several problems:

1. **Stale data:** the principal is kept in a session/token or cache, while the account has changed its name, permissions, or status.
2. **Heavy references:** entities carrying JPA relationships/lazy proxies can cause `LazyInitializationException` when used outside a transaction.
3. **Data leakage:** entities contain password hashes, emails, phone numbers, or sensitive information; logging/serializing the entire principal is dangerous.
4. **Hard to separate data sources:** business classes become tightly coupled to Spring Security, making them hard to reuse in batch jobs or tests.
5. **Mismatched lifecycle:** entities are tied to a persistence context/transaction, while a principal may outlive a single request or transaction.
6. **Changing permissions:** snapshot roles/memberships can drift out of sync with current data.

A **small, purposeful principal DTO that carries no managed entity** yields a cleaner design. If the principal needs to hold a password hash during password authentication, rely on the framework's credential-erasure mechanism after authentication; do not include the password hash in JSON responses or `toString()` logs.

## 7. Complete Example: Spring Boot 4.1.2 + Java 17 + Custom Principal

The example below runs a simple Servlet application with two mock in-memory accounts for illustration. The key thing to observe is that the **Account domain** and **AccountPrincipal security** are defined **as two distinct types**.

- User `mai@example.test` has `accountId=101`.
- User `an@example.test` has `accountId=102`.
- HTTP Basic lets you send credentials to `GET /me` for easy, observable testing.
- `@AuthenticationPrincipal AccountPrincipal` provides the **authenticated** account ID.
- The controller queries `AccountDirectory` to fetch the business record and returns only a safe `AccountView`.
- `GET /accounts/{id}` checks whether the requested ID matches the caller's ID; Mai is not allowed to view An's profile.

To focus on learning identity, the example intentionally uses **mock** in-memory accounts and passwords. Do not put demo passwords into production; a real application needs a DB, HTTPS, password/session policies, permission management, and appropriate auditing.

### 7.1. Structure and Dependencies

~~~text
account-identity-demo/
  pom.xml
  src/main/java/com/example/identity/
    IdentityApplication.java
    Account.java
    AccountDirectory.java
    AccountPrincipal.java
    SecurityConfiguration.java
    AccountController.java
~~~

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>account-identity-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

Pin only the **Spring Boot** version in the parent; do not manually add versions for `spring-security-core`, `spring-security-web`, or Framework. The Boot BOM manages compatible dependencies. `spring-boot-starter-webmvc` is the Web MVC starter in the Boot 4 line; in Boot 3 tutorials commonly use `spring-boot-starter-web`.

### 7.2. Application Entry Point Class

Create `src/main/java/com/example/identity/IdentityApplication.java`:

~~~java
package com.example.identity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }
}
~~~

### 7.3. Account as the Domain Model

Create `src/main/java/com/example/identity/Account.java`:

~~~java
package com.example.identity;

public record Account(
        long id,
        String loginEmail,
        String displayName,
        String tenantId,
        String passwordHash,
        boolean enabled) {
}
~~~

In this example `passwordHash` sits alongside account info to reduce the number of files for the lesson. In a real product, consider separating credentials and the business profile. **Do not return the `Account` record directly through an API** because it contains `passwordHash`.

### 7.4. AccountDirectory as the Business Data Source

Create `src/main/java/com/example/identity/AccountDirectory.java`:

~~~java
package com.example.identity;

import java.util.Map;
import java.util.Optional;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class AccountDirectory {

    private final Map<Long, Account> records;

    public AccountDirectory(PasswordEncoder encoder) {
        this.records = Map.of(
            101L, new Account(
                101L, "mai@example.test", "Mai Nguyen", "company-a",
                encoder.encode("demo-password-mai"), true),
            102L, new Account(
                102L, "an@example.test", "An Tran", "company-a",
                encoder.encode("demo-password-an"), true)
        );
    }

    public Optional<Account> findByEmail(String email) {
        return records.values().stream()
            .filter(account -> account.loginEmail().equals(email))
            .findFirst();
    }

    public Optional<Account> findById(long id) {
        return Optional.ofNullable(records.get(id));
    }
}
~~~

`records` is immutable in-memory data, not a DB. Hashes are generated by `PasswordEncoder` at application startup; the passwords are mock values only for testing with HTTP Basic. In a real application, the repository should have dedicated queries by ID/email and enforce tenant boundaries.

### 7.5. AccountPrincipal as the Identity Projection for Spring Security

Create `src/main/java/com/example/identity/AccountPrincipal.java`:

~~~java
package com.example.identity;

import java.util.List;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;

public final class AccountPrincipal extends User {

    private final long accountId;

    public AccountPrincipal(Account account) {
        super(
            account.loginEmail(),
            account.passwordHash(),
            account.enabled(),
            true,
            true,
            true,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
        this.accountId = account.id();
    }

    public long accountId() {
        return accountId;
    }
}
~~~

This is a **security type** extending Spring Security's `User` and adding `accountId`, mapped from the domain record. It does not contain the whole `Account`, holds no JPA entity, and does not need to carry display name or tenant inside the principal. `User` implements `UserDetails` and credential erasure; `ProviderManager` typically erases sensitive data when creating a successful authentication result.

`UserDetails#getUsername()` here is the email for login purposes. **The identifier used for business logic is `accountId()`**, not the email. When the email changes in the database, data links keyed by `accountId` remain stable, even though stored authentication sessions/usernames should be refreshed according to policy.

### 7.6. Configuring Username/Password Authentication

Create `src/main/java/com/example/identity/SecurityConfiguration.java`:

~~~java
package com.example.identity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(AccountDirectory accounts) {
        return username -> accounts.findByEmail(username)
            .map(AccountPrincipal::new)
            .orElseThrow(() -> new UsernameNotFoundException("Invalid user"));
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

In the HTTP Basic flow, Spring Security uses `UserDetailsService` and a compatible `PasswordEncoder` to verify the password. Success returns an `Authentication` whose principal is `AccountPrincipal` because the provider reads the `UserDetails` produced by the adapter above. When the password is wrong, no trusted principal is created.

`anyRequest().authenticated()` only checks **authentication**. It does not allow user A to view record B; that is enforced by the controller/service policy. Because the example only has GET endpoints and performs no write operations, there is no need to disable CSRF.

### 7.7. Controller Looking Up the Current Account by the Principal's ID

Create `src/main/java/com/example/identity/AccountController.java`:

~~~java
package com.example.identity;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class AccountController {

    private final AccountDirectory accounts;

    public AccountController(AccountDirectory accounts) {
        this.accounts = accounts;
    }

    public record AccountView(long id, String displayName, String tenantId) {
    }

    private AccountView view(Account account) {
        return new AccountView(
            account.id(), account.displayName(), account.tenantId());
    }

    @GetMapping("/me")
    public AccountView me(
            @AuthenticationPrincipal(errorOnInvalidType = true)
            AccountPrincipal principal) {
        Account account = accounts.findById(principal.accountId())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Account not found"));
        return view(account);
    }

    @GetMapping("/accounts/{id}")
    public AccountView getAccount(
            @PathVariable long id,
            @AuthenticationPrincipal(errorOnInvalidType = true)
            AccountPrincipal principal) {
        if (principal.accountId() != id) {
            throw new AccessDeniedException("Not allowed to view this account");
        }

        Account account = accounts.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Account not found"));
        return view(account);
    }
}
~~~

Key points to observe:

1. The `@AuthenticationPrincipal AccountPrincipal` parameter retrieves the **post-authentication** principal object. `errorOnInvalidType=true` helps catch situations where the authentication mechanism changes while the method still expects the old type.
2. `principal.accountId()` is the internal identifier mapped by the authentication source; the controller does not accept a client-supplied `accountId` when deciding "who I am".
3. `accounts.findById(...)` fetches the business object. This establishes a clear boundary between the **identity snapshot** and the **domain record**.
4. `getAccount` compares the caller's ID with the requested ID. A valid login does not allow a user to view every account.
5. `AccountView` is a safe DTO: the response only includes `id`, `displayName`, and `tenantId`, without `passwordHash`.

In a multi-tenant system, the policy must additionally check membership/tenant and granted permissions. The example simplifies ownership to focus on how a principal maps to an account.

### 7.8. Running and Self-Testing

With JDK 17 or newer, a suitable Maven installation, and access to download dependencies from Maven Central:

~~~bash
java -version
mvn -version
mvn -q -DskipTests package
mvn spring-boot:run
~~~

Once the server is running on localhost:8080, use another terminal:

~~~bash
curl -s -o /dev/null -w 'anonymous=%{http_code}\n' http://localhost:8080/me
curl -s -o /dev/null -w 'mai-me=%{http_code}\n' -u mai@example.test:demo-password-mai http://localhost:8080/me
curl -s -o /dev/null -w 'mai-own=%{http_code}\n' -u mai@example.test:demo-password-mai http://localhost:8080/accounts/101
curl -s -o /dev/null -w 'mai-other=%{http_code}\n' -u mai@example.test:demo-password-mai http://localhost:8080/accounts/102
curl -s -o /dev/null -w 'an-own=%{http_code}\n' -u an@example.test:demo-password-an http://localhost:8080/accounts/102
~~~

Expected statuses under the demo configuration:

~~~text
anonymous=401
mai-me=200
mai-own=200
mai-other=403
an-own=200
~~~

To inspect the DTO at `/me`, call:

~~~bash
curl -s -u mai@example.test:demo-password-mai http://localhost:8080/me
~~~

The JSON response contains:

~~~json
{"id":101,"displayName":"Mai Nguyen","tenantId":"company-a"}
~~~

JSON property order is not a security contract; what matters is that **there is no password hash**. The commands above use mock passwords for a local demo; in PowerShell on Windows use `curl.exe` if `curl` is an alias. Do not put production passwords on the command line or into shell history.

Analyzing the results:

- `anonymous=401`: no valid authentication credentials for `/me`.
- `mai-me=200`: Mai's account authenticates, the principal holds ID 101; the repository returns the current profile.
- `mai-own=200`: Mai reads her own record ID 101.
- `mai-other=403`: Mai still logged in successfully, but resource ID 102 does not belong to subject ID 101.
- `an-own=200`: An's account can read record 102.

In real systems, you also need to test non-existent accounts, locked accounts, email changes, per-tenant permissions, POST/PATCH/DELETE actions, and concurrent data changes.

### 7.9. Why This Example Is Better to Learn Than Casting an Entity

The example teaches separation of responsibilities:

~~~text
HTTP Basic request
   |
   v
DaoAuthenticationProvider + PasswordEncoder
   |
   v
UserDetailsService
   |
   v
AccountDirectory.findByEmail()
   |
   v
AccountPrincipal(accountId=101, username="mai@example.test")
   |
   v
Authentication in the request's SecurityContext
   |
   v
@AuthenticationPrincipal extracts accountId=101
   |
   v
AccountDirectory.findById(101)
   |
   v
AccountView JSON, resource permission check
~~~

There is no `(Account) authentication.getPrincipal()` operation. The business account and the principal still both refer to ID 101, yet each layer is responsible only for its own part.

## 8. When Not Using Username/Password: Mapping JWT and OAuth2/OIDC

With a Spring Security Resource Server validating a valid JWT, the **default** principal can be `Jwt`, while `Authentication#getName()` is typically taken from `sub`.

Illustrative controller snippet in an application configured as a JWT Resource Server:

~~~java
@GetMapping("/me")
public AccountView me(@AuthenticationPrincipal Jwt jwt) {
    String issuer = jwt.getIssuer().toString();
    String subject = jwt.getSubject();

    long internalAccountId =
        identityLinks.findAccountId(issuer, subject);
    return accountService.profileFor(internalAccountId);
}
~~~

The names `identityLinks`, `accountService`, and `AccountView` are **components the application must define itself**; these are not standalone classes. Remember to handle missing or mistyped `issuer/subject` as well as account status. Spring Security must be configured to **verify the JWT** before the controller trusts its claims. Do not parse a client-sent token with a JSON parser and use it directly.

The flow can be:

~~~text
Bearer token from client
      |
      v
JwtDecoder verifies signature, issuer, audience, expiration...
      |
      v
JwtAuthenticationToken, principal = Jwt
      |
      v
Verified (issuer, subject)
      |
      v
ExternalIdentityLink -> internal accountId
      |
      v
AccountService -> current account + memberships
      |
      v
Authorization -> DTO/response
~~~

**Not every token necessarily represents a human.** OAuth2 client credentials can authenticate a server application; if the system requires a user account, a separate policy for service identities is needed.

In modern Spring Security, you can customize the principal converter for JWTs, or use an intermediate application layer to map identity. However, when an API can accept multiple mechanisms (password, JWT, SSO), avoid writing controllers that hardcode every principal to the same type unless all providers agree on that contract.

### Do You Need to Replace the Principal in the Token Yourself?

It is not mandatory. There are two valid options:

- **Keep the framework-provided principal** and map via a `CurrentAccountResolver` or an appropriate service. This minimizes changes in the Security layer.
- **Create a custom principal** holding the internal ID and controlled metadata. Useful if many endpoints need a shared contract; requires configuring the provider/converter properly and handling lifecycle safely.

Neither option solves per-record access permissions on its own. Authorization rules must still check owner, tenant, status, and action.

## 9. One Person Having Multiple Accounts or Multiple Tenants

In SaaS, one individual may log in via a single identity yet hold multiple accounts or roles across multiple organizations. For example:

~~~text
Identity from SSO:
  issuer = https://idp.example
  subject = external-777

Internal user/account:
  accountId = 101

Memberships:
  accountId=101, tenant=A, role=EDITOR
  accountId=101, tenant=B, role=VIEWER
~~~

If the API receives `X-Tenant-Id: B`, that header is only the client's **requested target**, not proof that the caller belongs to tenant B. The server must confirm account 101 has the corresponding membership and then check whether the action is allowed in tenant B.

A proper access check looks like:

~~~text
allow(subject, action, resource, context) =
    verifiedAuthentication(subject)
    AND currentAccountIsEnabled(subject.accountId)
    AND belongsToTenant(subject.accountId, resource.tenantId)
    AND hasPermission(subject.accountId, action, resource)
~~~

This check is a conceptual model for learning, not an API provided out of the box by Spring Security. It can be implemented using an authorization service, `AuthorizationManager`, method security, or permission-scoped data queries.

**Do not store "current tenant" as an immutable string inside the principal and assume subsequent requests cannot switch tenants.** If there is a currently selected tenant, that selection must be validated against memberships; per-tenant permissions must be checked whenever needed. If the principal holds an authorities snapshot, a revocation mechanism must be clearly designed.

## 10. Accounts Can Change, Principals Can Be Stale: How to Handle It

| Event | Current domain | Previously issued principal/token | How to handle |
| --- | --- | --- | --- |
| Display name changed | New `displayName` | May still hold old name | Fetch profile from domain for display; do not use principal as sole profile source |
| Login email changed | New `loginEmail` | `getName()`/username may be old | Use stable account ID; design re-authentication or refresh |
| Account locked | `enabled=false` | Previous session/JWT may still be valid | Revoke session/token or check status on critical operations |
| Role revoked | Memberships/permissions table updated | Old authorities may still be present | Rules to update session/cache/token or evaluate current permissions |
| Tenant changed | Membership updated | Tenant claim/selected tenant may be stale | Check tenant relationship at operation time |
| Account deleted | Record gone | Old token still carries ID | Reject and revoke/manage token; do not recreate an account with the same ID |
| SSO provider changed | Different external `iss+sub` | Old principal belonged to prior issuer | Link verified identities, do not merely match email |

There is no single revocation strategy that fits every architecture. Server-side sessions can be invalidated or updated, whereas self-contained JWTs can remain valid until expiration if the API does not check status/session/token version against an authoritative source. Latency and revocation requirements must be balanced.

If the system manages sensitive permissions, "logged in an hour ago" is usually not enough to continue operating after an account has been disabled. Appropriate update policies and resource controls must be designed.

## 11. Resource Authorization Must Be Based on Verified Identity

Suppose a URL is `/accounts/102`. The caller has principal `accountId=101`. These are **two different ID roles**:

- `callerAccountId=101`: server-verified identity.
- `requestedAccountId=102`: **resource** ID requested by the client.
- Policy answers whether Mai is allowed to read 102, rather than inferring it from the URL containing a valid number.

A check in a service might look like:

~~~java
// Business logic snippet, not a standalone Java class.
public AccountView readAccount(long requestedId, long callerId) {
    if (requestedId != callerId && !permissionService.canSupport(callerId)) {
        throw new AccessDeniedException("Not allowed");
    }
    Account account = accountRepository.findById(requestedId)
        .orElseThrow(() -> new NotFoundException("No account"));
    return accountViewMapper.toView(account);
}
~~~

The repository, permission service, and exception mapper names are application-specific components. If there are support admins, permissions must come from a trusted source with clear scope (for example, the same tenant), not letting every `ROLE_ADMIN` view all tenants by default.

**IDOR/BOLA:** if the server only checks that the request has a principal and then fetches the record by `requestedId`, users can change the ID to access unauthorized data. Privacy must be enforced on the server whether the ID is numeric, a UUID, or a hard-to-guess string.

In systems with many endpoints, encapsulate the policy in a shared service/authorization component. Controllers simply invoke the policy instead of writing a slightly different check in every API.

## 12. What Should a Principal Contain, and What Should It Exclude?

A small custom principal usually only needs:

- **Stable subject ID** such as `accountId` or `actorId`.
- Username/login identifier if required by the mechanism.
- Verified authorities or authentication metadata, according to the refresh policy.
- Minimal attributes needed to handle security flows if truly required.

Avoid putting in the principal:

- Raw passwords, secret tokens, private keys, or session secrets.
- Entire JPA entity graphs, lazy collections, and overly large relationships.
- Personal information / financial details unnecessary for authentication.
- Frequently changing business data that code might assume is always fresh.
- Client-claimed permission strings not verified by the server/provider.
- Data intended for API responses without a DTO/authorization layer.

`UserDetails` used for password login may need to carry the **password hash** temporarily so the provider can verify it. This is a controlled exception for authentication, not a reason to return the hash to the client. Spring Security recommends supporting `CredentialsContainer` when implementing custom `UserDetails` so credentials are erased after use.

With Spring Security's `User`, `equals` and `hashCode` may rely on the username; if the username is a mutable email, **do not rely on principal equality as a domain ownership check**. Use an immutable `accountId` and explicit policies.

## 13. Common Mistakes

1. **"Account and principal must be the same class."** No. Domain and Security have different contracts and lifecycles.
2. **"`authentication.getPrincipal()` always returns Account."** No. The type depends on the provider/authentication mechanism.
3. **"`authentication.getName()` is always the database primary key."** No. It can be an email, username, or `sub` claim.
4. **"Having an Account record means already logged in."** No. An Account can exist independently of Authentication.
5. **"Having a principal means the user has full permissions."** No. Authentication and authorization are two separate decisions.
6. **"Storing email as the owner ID is fine because email is unique."** Emails can change or be reused; an immutable ID is usually preferable.
7. **"The JWT has `email`, so it can match directly to an account."** You must verify the token/issuer and have an identity linking policy; email is not always a trusted key.
8. **"JWT `sub=123` from any issuer is the same person."** No. Subject must be interpreted within the issuer's scope and IdP contract.
9. **"Putting the entire JPA entity in the session principal is the simplest way."** Can cause stale data, lazy loading issues, serialization failures, and data leakage.
10. **"Changing a role in the database automatically updates authorities in old tokens."** Not by default; refresh/revocation/re-evaluation must be designed.
11. **"A principal with a valid ID can read any record whose ID the client sends."** Wrong. Object-level authorization is required.
12. **"`@AuthenticationPrincipal` automatically queries the current account."** No; it retrieves `Authentication.getPrincipal()`.
13. **"The Account in the session is the freshest data source."** Not necessarily. A session can hold a stale snapshot.
14. **"Casting to UserDetails is safe for every API."** No; a JWT/OIDC resource server may use a different principal type.
15. **"Once an account is locked, all old tokens immediately become invalid."** Not by default; session/token lifecycle must be designed.
16. **"The tenant sent by the client is the trusted tenant."** No; it must be matched against current memberships/permissions.
17. **"Reading the entity and returning JSON directly is more convenient than a DTO."** Easily exposes password hashes and sensitive fields.
18. **"Using the principal ID as a role or authority."** An ID is an identity; permissions are a separate dataset/policy.

## 14. Identity Mapping Design Checklist

Before putting an application into a multi-user environment, answer the following:

- [ ] Is there a **stable internal account ID** serving as the owner/audit/membership key?
- [ ] Are the principal types known for **each authentication method** (password, JWT, OAuth2, service account)?
- [ ] Is there a trusted **identity mapping** from subject to account ID without relying on unverified claims?
- [ ] If using an external IdP, is identity determined by issuer + subject appropriately, with an account linking workflow?
- [ ] Does `UserDetailsService` return an appropriate `UserDetails` without unintentionally leaking domain entities into payloads?
- [ ] Do controllers/services fetch accounts by a trusted ID and return field-restricted DTOs?
- [ ] Do authorization rules evaluate action, resource, owner, and tenant rather than only `authenticated()`?
- [ ] Is there a strategy for email changes, locked/deleted accounts, revoked roles, and membership changes?
- [ ] Do sessions/tokens avoid carrying redundant sensitive data, with controlled storage and lifetime?
- [ ] Are tests covering authenticated accounts trying to access another user's resources, not just blocking anonymous requests?
- [ ] Is code avoiding the assumption that `SecurityContextHolder` ThreadLocal is available across all async/reactive threads, using proper stack-specific propagation instead?
- [ ] Do logs/audits use a trusted subject ID and avoid recording passwords/tokens in logs?

## 15. Self-Check Questions

**Question 1.** An `Account` entity with ID 101 is found in the database. Does that mean the current request is logged in as account 101?

*Answer:* No. There must be a trusted authentication result in `Authentication` and an identity bridge identifying that exact subject.

**Question 2.** Mai changes her email, but previous documents had `owner_account_id=101`. Should all owner keys be updated to the new email?

*Answer:* No, if the owner key is already an immutable internal ID. Updating the email is an account attribute change; ID 101 continues to represent the same account.

**Question 3.** When Spring Security uses a JWT Resource Server, why can `(Account) authentication.getPrincipal()` fail?

*Answer:* Because the default principal may be `Jwt`, not an `Account` entity. You need to map from verified claims to the account ID.

**Question 4.** An account has `ROLE_USER` and can call `GET /accounts/{id}`. What stops Mai from changing the ID in the URL to 102?

*Answer:* Server-side object-level access control, comparing the caller's trusted account ID with the resource's owner/allowed conditions.

**Question 5.** Two IdPs have the same `sub="123"`. Can they automatically be treated as the same person?

*Answer:* No. Subject is typically meaningful only within an issuer's scope; you must verify the issuer, subject, and use a dedicated account-linking workflow.

**Question 6.** Why might a principal carrying `displayName="Mai"` differ from the latest name in the database?

*Answer:* The principal is a snapshot/representation at authentication or token issuance time; the domain record can be updated afterward.

**Question 7.** When using `@AuthenticationPrincipal AccountPrincipal`, where should the current profile be retrieved from?

*Answer:* From `AccountService`/repository using the mapped and verified `accountId`; return only a DTO containing fields the caller is permitted to view.

**Question 8.** Should `passwordHash` be included in the `AccountView` response since it is not the raw password?

*Answer:* No. A password hash is still sensitive information and is not data a user should receive from an API.

**Question 9.** An account has been suspended, yet the client still holds a JWT with a valid signature and expiration. What should the application do?

*Answer:* Apply an intentional account lifecycle / permission revocation policy, such as checking current status, version/revocation, using appropriate token lifetimes, or blocking sensitive operations at the service layer.

**Question 10.** In a multi-tenant SaaS, can `accountId=101` read all documents across tenants A and B?

*Answer:* No. Membership and permissions must be verified on the specific requested tenant/document, not merely knowing the caller's ID.

The guiding principle for keeping a clear boundary is: **the principal identifies the subject of the request; the account is the current business record; the permission policy decides what that subject can do with which data**. Using a stable ID and a controlled mapping layer to connect them makes it easier to scale from form login to JWT/SSO and easier to maintain when emails, permissions, tenants, or account statuses change.

### References

- [Spring Security — Authentication Architecture (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authentication API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html)
- [Spring Security — UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html)
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/)
- [Spring Security — Spring MVC Integration and @AuthenticationPrincipal](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html)
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Boot — Spring Security Auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now)
