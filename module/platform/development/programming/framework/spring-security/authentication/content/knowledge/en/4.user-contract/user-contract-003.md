# UserDetailsManager and Account Management Operations

**Context:** Spring Security – authentication. **Knowledge group:** User Contract.

## 1. What Problem Does UserDetailsManager Solve?

In Spring Security, a **user account** has two related but distinct lifecycles:

1. **Reading identity for authentication:** When a user logs in with username/password, the authentication mechanism needs to find the account, hashed password, lock/expiration status, and permissions. That is `UserDetailsService`'s responsibility via `loadUserByUsername(String username)`.
2. **Managing account data:** When registering users, changing roles, locking accounts, changing passwords, or deleting users, the application needs write operations. `UserDetailsManager` extends `UserDetailsService` to provide the contract for those operations.

**Inheritance relationship:**

~~~text
                  UserDetails
                     ^
                     | object holding account info
                     |
              UserDetailsService
              + loadUserByUsername(username)
                     ^
                     | extends
                     |
              UserDetailsManager
              + createUser(user)
              + updateUser(user)
              + deleteUser(username)
              + changePassword(oldPassword, newPassword)
              + userExists(username)
                     ^
          +----------+----------------------+
          |          |                      |
 InMemoryUserDetailsManager   JdbcUserDetailsManager   LdapUserDetailsManager
     in-memory, demo/test         JDBC database            LDAP directory
~~~

`UserDetailsManager` is in the `org.springframework.security.provisioning` package. It is an **interface**, not a REST controller or an automatic admin management API. Spring Security does not automatically expose endpoints for clients to create, delete, or elevate privileges simply because you declare a bean of this type.

Consider two different questions:

- "Is `linh`'s password valid?" → `DaoAuthenticationProvider` calls `UserDetailsService.loadUserByUsername(...)`, checks credentials with `PasswordEncoder`, and returns an `Authentication`.
- "Administrator needs to add account `linh` with reader permissions" → business logic checks administrator authorization, builds a `UserDetails` containing a password hash, and calls `UserDetailsManager.createUser(...)`.

**Do not equate account management with authentication.** Creating a user successfully does not mean the user is logged in; conversely, a logged-in user does not by default have permission to modify someone else's account.

## 2. Full Contract and Meaning of Each Method

`UserDetailsManager extends UserDetailsService`, so in total it has one inherited read method and five management methods:

| Method | Function | Input/Subject | Return Value |
| --- | --- | --- | --- |
| `loadUserByUsername(String username)` | Loads account for authentication | Username to look up | `UserDetails` or `UsernameNotFoundException` |
| `userExists(String username)` | Checks whether an account exists per the implementation's lookup policy | Username | `boolean` |
| `createUser(UserDetails user)` | Creates a new account | Validly prepared `UserDetails` | `void` |
| `updateUser(UserDetails user)` | Updates existing account data | `UserDetails` with desired state | `void` |
| `deleteUser(String username)` | Deletes user per the implementation's storage mechanism | Username | `void` |
| `changePassword(String oldPassword, String newPassword)` | Changes password **of the current user** | Old password, new password in the format required by the provider | `void` |

### Reading `changePassword` Properly

The method **does not take a target username**. Implementations typically rely on the current `Authentication` in `SecurityContextHolder` to know which account is changing its password. `oldPassword` may be used to reauthenticate if an appropriate `AuthenticationManager` is configured; do not assume every implementation **always** checks the old password. When programming a password change flow, the application must ensure adequate security checks are performed.

`newPassword` in typical implementations like `InMemoryUserDetailsManager`/`JdbcUserDetailsManager` is usually **a password value already encoded by PasswordEncoder in storage format**, not a raw password to be hashed automatically. Check the specific contract and configuration before using it. A new password submitted by the client must be validated against policy and encoded in a trusted service layer before passing it down to storage.

### Reading `userExists` Properly

`userExists("linh") == false` at the time of calling does not promise that a subsequent `createUser(...)` will definitely succeed: two requests can check concurrently and both try to create. With persistent data stores, a **unique constraint** in storage along with conflict/transaction handling decides username uniqueness.

### Reading `updateUser` Properly

`updateUser` may modify the password hash, authorities, or account flags depending on the implementation. It does not automatically know which fields in a request were "intended to be edited". When building a new `UserDetails` to update, preserve the fields that must stay intact and do not allow users to assign themselves the ADMIN role.

## 3. What Data Does UserDetails Contain?

`UserDetails` is the interface describing the data Spring Security needs to verify login and construct identity:

| Attribute/Method | Meaning and Notes |
| --- | --- |
| `getUsername()` | Login name / identifier looked up by `UserDetailsService` |
| `getPassword()` | Password **hashed/encoded with PasswordEncoder**, not the original password string |
| `getAuthorities()` | **Server-decided** `GrantedAuthority` instances (e.g., `ROLE_USER`, `ROLE_EDITOR`) |
| `isEnabled()` | Whether the account is still allowed to log in per policy |
| `isAccountNonLocked()` | Whether the account is not locked |
| `isAccountNonExpired()` | Whether the account is still valid |
| `isCredentialsNonExpired()` | Whether the credentials are still valid |

With the built-in `User` implementation, an immutable account configuration object can be created via the builder:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

UserDetails account = User.withUsername("linh")
        .password(encoder.encode("example-secret-only"))
        .roles("USER") // automatically maps to ROLE_USER
        .disabled(false)
        .accountLocked(false)
        .build();
~~~

**This is an illustrative snippet requiring imports/dependencies and does not run standalone.** Those boolean flags are policy inputs and should not be confused with the logged-in state of `Authentication`. Building a valid `UserDetails` does not create a session/token on its own. The data inside `UserDetails` is also not the full business model of a user profile (address, billing, personal settings…); those parts can live in separate entities/services.

**Roles and authorities:** `.roles("USER")` adds the `ROLE_` prefix; `.authorities("ROLE_USER", "document:read")` uses the authority strings as declared. Do not add the `ROLE_` prefix twice when using `roles(...)`. Authorization is enforced via `AuthorizationManager`, `@PreAuthorize`, or equivalent configuration after authentication.

## 4. Account Creation Workflow with createUser

A controlled account registration workflow typically looks like:

~~~text
POST /signup or /admin/users
      |
      v
Identify actor and permission to create accounts
      |
      v
Validate username, password policy, minimal info
      |
      v
Check business data + unique constraint at storage
      |
      v
PasswordEncoder.encode(rawPassword)
      |
      v
Server assigns initial roles (e.g., ROLE_USER)
      |
      v
UserDetailsManager.createUser(validatedUserDetails)
      |
      v
Audit event + trigger email verification flow if needed
~~~

**Before calling:**

- Clearly decide **who can create users**. Self-registered accounts usually receive only default permissions; creating admins belongs to a separate controlled flow.
- Canonicalize username/email per business policy, but do not arbitrarily alter casing and Unicode if the identity system treats names as case-sensitive. Configure uniqueness consistently with how the implementation looks up users.
- Check length, password strength, and anti-reuse policy; pass the raw password to `PasswordEncoder.encode(...)` and store the hash. Do not log the raw password or return the hash to the client.
- Update within the same transaction if business profiles, tenant links, or audit records also need to be created in the database. If emitting events outside the transaction, use an outbox/appropriate retry mechanism to avoid orphaned data.

Example call pattern:

~~~java
// Illustrative code inside a protected service, not a complete controller.
UserDetails user = User.withUsername(inputUsername)
        .password(passwordEncoder.encode(rawPassword))
        .roles("USER")
        .build();

if (!userDetailsManager.userExists(user.getUsername())) {
    userDetailsManager.createUser(user);
}
~~~

Checking `userExists` here only helps return a friendly message. **Do not use it in place of a database unique constraint**; you still must handle the case where another request creates the username first. If the application needs protection against account enumeration, registration/recovery responses should avoid messages that disclose account existence.

## 5. Updating Accounts with updateUser

`updateUser(UserDetails user)` is typically used when changing account status or permissions. Using the `User.withUserDetails(existing)` builder preserves existing data and lets you replace the desired fields:

~~~java
// Illustrative: admin has been authenticated and authorized before running.
UserDetails existing =
        userDetailsManager.loadUserByUsername("linh");

UserDetails updated = User.withUserDetails(existing)
        .authorities("ROLE_USER", "ROLE_EDITOR")
        .build();

userDetailsManager.updateUser(updated);
~~~

**Common risk:** A step that "takes an object from the request and updates verbatim" can wipe authorities, overwrite the password hash with plaintext, unlock accounts, or self-escalate privileges. Every sensitive field must be selected and decided by server policy; never auto-bind DTO/JSON directly into `UserDetails` for updates.

In systems with multiple data sources, you may need to update **profiles** via a domain service while updating accounts and roles through an appropriate abstraction, instead of cramming every change into `UserDetailsManager`. Business rules like "cannot delete the last admin", "cannot elevate one's own privileges", or "forbid editing roles higher than one's own" are the service's responsibility, not something to delegate to the user management interface.

**When do role changes take effect?** If the system holds `Authentication` in an HTTP session or token, old authorities may persist until the context/token is refreshed. Design reload, session invalidation, token revocation/short lifetimes, or reauthentication according to risk. Simply calling `updateUser` does not guarantee every active request immediately sees the new role.

## 6. Deleting Accounts with deleteUser

`deleteUser(username)` asks the implementation to delete the account per its mechanism, but **does not automatically guarantee**:

- Deleting all related business records or meeting retention regulations;
- Terminating all active sessions and revoking access/refresh tokens;
- Emitting audit events or operational notifications;
- Releasing profile links, resource ownership, tenants, or groups;
- Applying a **soft delete** policy or retaining data for recovery.

Example:

~~~java
// Call only when the actor has delete permission and domain policy permits.
userDetailsManager.deleteUser("linh");
~~~

In real systems, **disabling an account** (`enabled=false`) can be a better choice than hard deletion to preserve history and satisfy business rules; that is an application decision. When deleting or locking a user, handle how active sessions are blocked from continued access. The outcome/behavior when deleting a non-existent user depends on the implementation; do not assume all implementations are idempotent or throw the same exception.

## 7. Changing Passwords with changePassword – Security Focus

### 7.1. No Target Username Parameter

Signature:

~~~java
void changePassword(String oldPassword, String newPassword);
~~~

There is no username parameter. With standard security-context-based implementations, the target account is **the authenticated user in the current request**. This fits **self-service password change**. An **admin resetting someone else's password** is a separate business flow requiring extra permissions and auditing, and should not spoof another user's context to call `changePassword`.

A secure self-service flow:

~~~text
Logged-in user
      |
      v
Check session, CSRF, and step-up/MFA policy if needed
      |
      v
Receive oldPassword + newPassword over HTTPS
      |
      v
Reauthenticate oldPassword via AuthenticationManager
      |
      v
Validate newPassword, prevent reuse per policy
      |
      v
Hash newPassword with PasswordEncoder
      |
      v
UserDetailsManager.changePassword(old, encodedNew)
      |
      v
Audit + notify + handle remaining active sessions/tokens
~~~

**Do not assume implementations always reauthenticate.** For example, `InMemoryUserDetailsManager.changePassword` only re-verifies `oldPassword` if an `AuthenticationManager` has been configured on that manager. Otherwise, the implementation may update the principal's password from the security context without checking the old password. Therefore, the application must **configure an appropriate AuthenticationManager and/or explicitly reauthenticate in the service layer** before modifying credentials.

**Value of `newPassword`:** For these implementations, you must pass the **password hash** created via `PasswordEncoder.encode(rawNewPassword)`. Passing plaintext assuming the manager hashes automatically stores the wrong format and causes login failures or weak security. Do not hand-roll raw SHA-256 instead of a dedicated password encoder.

### 7.2. Changing Password Does Not Automatically Solve Session Lifecycle

Once a password changes, old sessions, remember-me tokens, or previously issued API tokens may remain valid. Policy should specify: logging out other devices, requiring re-login, revoking refresh tokens, shortening sessions, sending password-change notifications, and handling account compromise cases. With JWTs, immediate revocation cannot be assumed just because the password hash in the database changed.

### 7.3. Distinguishing updateUser from changePassword

| Scenario | Contractually Appropriate API | Notes |
| --- | --- | --- |
| User changes own password supplying old password | `changePassword(old, encodedNew)` | Verify current Authentication and old password |
| Admin changes role or locks account | `updateUser(updatedDetails)` | Authorize actor and preserve unchanged fields |
| Admin resets another user's password | Dedicated business service; may update password hash after authorization | Audit, notify, invalidate sessions; do not spoof current user |
| Provider wants to upgrade hash after login | `UserDetailsPasswordService.updatePassword(user, encodedPassword)` if used | Different interface, different purpose from self-service changePassword |

`UserDetailsPasswordService` is a separate API for updating password hashes (such as upgrading algorithms after successful authentication); implementations may support both simultaneously. Do not equate `updatePassword` with `changePassword` or `updateUser`.

## 8. Common Implementations

| Implementation | Storage | When Appropriate | Limitations and Notes |
| --- | --- | --- | --- |
| `InMemoryUserDetailsManager` | Map in process memory | Demos, experiments, tests, temporary sample accounts | Not persistent across restarts, not shared across instances; do not use as primary account system |
| `JdbcUserDetailsManager` | Database via JDBC/`DataSource` | Username/password apps backed by account/authorities tables | Requires proper schema/queries/transactions; group/authority updates have caveats |
| `LdapUserDetailsManager` | LDAP directory service | Enterprise environments with identities in LDAP | Requires LDAP config, directory structure, password policy/ACL, and write permissions |

### InMemoryUserDetailsManager

- Allows creating an empty manager or passing initial `UserDetails`.
- Implements both `UserDetailsService` and `UserDetailsManager` operations.
- Data lives inside one process; restarts lose runtime updates.
- Suitable for testing CRUD logic and authentication without needing a database yet.

### JdbcUserDetailsManager

`JdbcUserDetailsManager` extends `JdbcDaoImpl` and performs user management on top of JDBC authentication tables/queries. With Spring Security's default schema, it requires matching user and authority tables (`users`, `authorities`) and appropriate constraints. When using a custom schema, read/write SQL statements must be configured in sync with the existing schema and database dialect.

**Important:** If `enableAuthorities=false` in the JDBC configuration, create/update/delete operations will not write/delete authorities in the usual way; furthermore, direct authorities and group-derived authorities cannot always be distinguished from `UserDetails` alone. For complex authorization systems, understand how `JdbcUserDetailsManager` manages groups and roles before modifying accounts. Profile/tenant data beyond the default tables should have a separate domain service.

**Servlet/JDBC bean sample in Spring Boot** (integration snippet, does not compile/run standalone with `javac`):

~~~java
@Bean
UserDetailsManager userDetailsManager(DataSource dataSource) {
    return new JdbcUserDetailsManager(dataSource);
}

@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}
~~~

This is only the bean declaration part. The application still needs a `DataSource`, matching tables/SQL, a `SecurityFilterChain`, authorization policy for account management endpoints, and password encoding in the service layer. With Boot, the `spring-boot-starter-security` dependency alongside the JDBC starter/driver and BOM-managed versions provides the related components.

### LdapUserDetailsManager

Used when the account source is LDAP. Merely creating an instance does not mean you are connected or permitted to write to the directory. It requires LDAP address, bind identity, search base, attribute mapping, TLS, ACLs, schema, and directory password policy; `changePassword` behavior may depend on LDAP server policy. Do not apply the assumption "password is a password hash column in a JDBC table" to LDAP.

### When to Implement UserDetailsManager Yourself?

Applications with custom user data (JPA, REST identity service, multi-tenant) can write an adapter implementing `UserDetailsManager` and `UserDetailsService` per contract. For example, a read-only `UserDetailsService` may suffice for login; if account management business rules are complex, an **application service** allowed to update entities directly may fit better than forcing every domain model into a `UserDetailsManager`. When implementing it yourself, make each method's semantics, transactions, credential security, and authority loading crystal clear.

## 9. Runnable Java 17 Demo: Create, Read, Update, Change Password, and Delete

The example below runs standalone with Gradle and **Spring Security 6.5.11**, requiring no Spring Boot, database, or web server. The demo shows all five management methods and how `UserDetailsManager` simultaneously implements `loadUserByUsername`. All passwords in the example are purely for learning and must never go into production.

### 9.1. Directory Structure

~~~text
user-manager-demo/
├── build.gradle
└── src/main/java/demo/UserManagerDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.UserManagerDemo'
}
~~~

**File `src/main/java/demo/UserManagerDemo.java`:**

~~~java
package demo;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class UserManagerDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        InMemoryUserDetailsManager users = new InMemoryUserDetailsManager();

        // 1. Check and create account. Stored password is a BCrypt hash.
        System.out.println("before.exists=" + users.userExists("linh"));

        UserDetails initial = User.withUsername("linh")
                .password(encoder.encode("demo-old-password"))
                .roles("USER")
                .build();
        users.createUser(initial);

        System.out.println("afterCreate.exists=" + users.userExists("linh"));

        // 2. Read back using the UserDetailsService contract.
        UserDetails loaded = users.loadUserByUsername("linh");
        boolean oldPasswordMatches = encoder.matches(
                "demo-old-password", loaded.getPassword());
        System.out.println("loaded.name=" + loaded.getUsername());
        System.out.println("loaded.passwordMatches=" + oldPasswordMatches);
        System.out.println("loaded.roleUser=" + loaded.getAuthorities().stream()
                .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())));

        // 3. Update roles with trusted UserDetails, preserving password hash.
        UserDetails edited = User.withUserDetails(loaded)
                .authorities("ROLE_USER", "ROLE_EDITOR")
                .build();
        users.updateUser(edited);

        UserDetails afterUpdate = users.loadUserByUsername("linh");
        System.out.println("afterUpdate.roleEditor="
                + afterUpdate.getAuthorities().stream()
                .anyMatch(a -> "ROLE_EDITOR".equals(a.getAuthority())));

        // 4. Configure manager so changePassword verifies oldPassword.
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);
        AuthenticationManager authManager = new ProviderManager(dao);
        users.setAuthenticationManager(authManager);

        Authentication verified = authManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "linh", "demo-old-password"));

        // Demo simulates SecurityContext of an authenticated user.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        try {
            users.changePassword(
                    "demo-old-password",
                    encoder.encode("demo-new-password"));
        } finally {
            SecurityContextHolder.clearContext();
        }

        String storedHash = users.loadUserByUsername("linh").getPassword();
        System.out.println("afterChange.newPasswordMatches="
                + encoder.matches("demo-new-password", storedHash));
        System.out.println("afterChange.oldPasswordMatches="
                + encoder.matches("demo-old-password", storedHash));

        // 5. Delete account from in-memory store.
        users.deleteUser("linh");
        System.out.println("afterDelete.exists=" + users.userExists("linh"));
    }
}
~~~

From the `user-manager-demo` directory, use JDK 17+ and a compatible Gradle version:

~~~bash
gradle -q run
~~~

If using Gradle Wrapper, run `./gradlew -q run` (PowerShell on Windows: `.\gradlew.bat -q run`). On the first run Gradle needs network access to download dependencies from Maven Central.

**Output produced by the `System.out.println` statements** (excluding any environment/Gradle logs):

~~~text
before.exists=false
afterCreate.exists=true
loaded.name=linh
loaded.passwordMatches=true
loaded.roleUser=true
afterUpdate.roleEditor=true
afterChange.newPasswordMatches=true
afterChange.oldPasswordMatches=false
afterDelete.exists=false
~~~

### 9.2. Result Analysis

- `before.exists=false`: the memory store starts empty.
- `afterCreate.exists=true`: `createUser` stores `UserDetails`; no login/session is created at this moment.
- `loaded.passwordMatches=true`: the value in `getPassword()` is a BCrypt hash, and `PasswordEncoder.matches` checks the raw password against it.
- `afterUpdate.roleEditor=true`: `updateUser` saved the new server-decided authorities.
- `users.setAuthenticationManager(authManager)`: this example **explicitly configures reauthentication**; do not skip that step and assume `changePassword` still checks the old password.
- `SecurityContextHolder.setContext(context)`: simulates a logged-in user so `changePassword` selects the current user; real Servlet applications have security filters managing context per request.
- `afterChange.newPasswordMatches=true`: the new password hash is valid.
- `afterChange.oldPasswordMatches=false`: the old raw password no longer matches the stored hash.
- `afterDelete.exists=false`: the account was removed from the in-memory store; this is not proof that all external sessions/tokens have been revoked.

**Demo scope:** The program intentionally omits web controllers, token/session backends, admin endpoints, databases, or multi-user concurrency. It directly illustrates the manager contract, not a production security template.

## 10. Integrating UserDetailsManager into Spring Security Authentication

Typical flow when a system uses username/password:

~~~text
                          +----------------------+
                          |  UserDetailsManager  |
                          |  read + manage users |
                          +-----------+----------+
                                      ^
                                      | implements UserDetailsService
                                      |
POST /login --> AuthenticationFilter --> AuthenticationManager
                                            |
                                            v
                                      DaoAuthenticationProvider
                                            |
                                            +--> loadUserByUsername(...)
                                            +--> PasswordEncoder.matches(...)
                                            +--> check account state
                                            |
                                            v
                                      authenticated Authentication
                                            |
                                            v
                                      SecurityContext
                                            |
                                            v
                                      Authorization check

/admin/users --> authorized service --> createUser/updateUser/deleteUser
/me/password --> reauthenticated service --> changePassword
~~~

`DaoAuthenticationProvider` only needs the `UserDetailsService` interface. Because `UserDetailsManager extends UserDetailsService`, the same implementation can serve both reading users on login and updating accounts during administration. However, it **is not an authentication manager**; `UserDetailsManager` does not verify passwords in `createUser` and does not return `Authentication` when updating a user.

**Using the bean from services:** In Spring Boot, you can inject `UserDetailsManager` into registration/admin services while injecting `UserDetailsService` (which is the same manager) into `DaoAuthenticationProvider` depending on configuration. When multiple providers or identity sources exist, ensure the authenticating provider reads the exact store updated by account business logic.

Design-level admin service example:

~~~java
// ILLUSTRATIVE CODE INSIDE A SERVICE WITH CONFIGURED DEPENDENCIES/SECURITY.
// Admin authorization checks must be enforced at the controller/service boundary.
public void registerNormalUser(String username, String rawPassword) {
    UserDetails user = User.withUsername(username)
            .password(passwordEncoder.encode(rawPassword))
            .roles("USER") // role assigned on the server side
            .build();

    // Storage must protect username uniqueness; handle races/conflicts.
    userDetailsManager.createUser(user);
}
~~~

This is **an illustrative method that does not compile standalone**, since `passwordEncoder` and `userDetailsManager` are dependencies of an unshown service class. It highlights an important boundary: role data comes from application policy, not from client payloads.

## 11. Common Mistakes When Managing Accounts

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Having only `UserDetailsService` yet calling `createUser` | Compile error, management methods missing | Pick `UserDetailsManager` / appropriate write service |
| Assuming `UserDetailsManager` creates a REST API automatically | Risk of skipping authorization design | Write protected APIs and enforce policies |
| Storing plaintext in `User.withUsername(...).password(...)` | Credential exposure or auth failure from invalid hash | Use `PasswordEncoder.encode(...)` before saving |
| Using `User.withDefaultPasswordEncoder` in production | Source contains raw passwords, exposure risk and demo config | Use PasswordEncoder bean and secrets supplied through secure channels |
| Letting browsers submit `ROLE_ADMIN` and creating user verbatim | Privilege escalation | Server decides default roles and admin rights |
| Using `userExists` as a lock guaranteeing uniqueness | Race condition, duplicate accounts | Unique constraint + transaction/conflict handling |
| Calling `updateUser` with an under-populated object | Overwrites password hash/roles/account status | Load existing account, alter fields intentionally, validate |
| Calling `changePassword` without a current Authentication | Cannot identify current user, likely failure | Require logged-in user and verify SecurityContext |
| Assuming `changePassword` always checks `oldPassword` | A user with a hijacked session can change password without old password | Configure reauthentication/step-up and test the implementation |
| Passing raw `newPassword` to an implementation expecting a hash | Stored in wrong format / login fails | Encode in service before calling |
| Changing another user's password by mutating SecurityContext | Bypasses identity boundaries and auditing | Use a separate admin reset flow with strong authorization |
| Thinking deleting a user instantly invalidates all tokens/sessions | Old sessions or JWTs may remain usable | Design revocation, invalidation, and revalidation |
| Thinking changing roles immediately updates logged-in user's permissions | SecurityContext/tokens still hold old roles | Refresh identity, revoke sessions/tokens, or adjust TTL |
| Using InMemory for distributed environments | Accounts diverge across instances, lost on restart | Use appropriate database/LDAP/IdP |
| Calling `updateUser` to change roles without auditing | No trail of privilege escalation/revocation | Log security event, actor, target, timestamp, and changes |

**Log neither password hashes nor raw passwords.** Strong hashes are still sensitive data because they can be attacked offline. When debugging, log allowed internal usernames, operation type, request ID, and outcome; avoid logging credentials or entire `UserDetails`.

## 12. Decisions Needed in Real Systems

### Authorization for Account Management Operations

On `/admin/users`, require the appropriate role or permission, check tenant boundaries, prevent self-escalation, and forbid disabling the last administrator if business rules demand it. On `/me/password`, identify the current user from the security context, reauthenticate password/MFA, and enforce CSRF if using cookie sessions. Each operation has a different authorization policy; `UserDetailsManager` does not create those policies automatically.

### Write Consistency

With JDBC, the database may require transactions for creating users and authorities, updating multiple tables, deleting users/roles, and auditing. Design locks/unique constraints, rollbacks, and safe retry handling. With LDAP, write operations face ACL constraints and different transaction semantics from JDBC.

### Account Lifecycle

Distinguish **temporary lock**, **disable**, **delete**, **password reset**, and **password change with old password**. These actions have different impacts on UX, legal data retention, auditing, and sessions/tokens. `UserDetailsManager` is a data manipulation layer, not the definition of the full lifecycle policy.

### Updating Active Identities

Authentication may capture authorities into `Authentication` at login time. Afterward, session contexts, signed tokens, or caches may still hold the old copy. Designing permission changes/user locking must account for when changes take effect on running requests. Never assume a single `updateUser(...)` call immediately invalidates previously issued JWTs.

### Multi-Tenancy and Usernames

`UserDetailsService.loadUserByUsername(String)` accepts only a single username string. If two tenants share the same username, the application must define a clear global naming convention (e.g., tenant-scoped username) or have the adapter/service receive tenant context securely. Never let clients pick arbitrary tenants when querying higher-privileged accounts.

## 13. Self-Check

**Question 1:** What is the most important difference between `UserDetailsService` and `UserDetailsManager`?  
**Answer:** The service defines account lookup for authentication; the manager extends the service and adds account write/management operations.

**Question 2:** Which username's password does `changePassword("old", "new")` change?  
**Answer:** The account taken from the current Authentication per the implementation's contract, as there is no target username parameter. You must reauthenticate the old password and encode the new password properly.

**Question 3:** A user sends JSON `{"username":"linh","roles":["ADMIN"]}` to register. Should `createUser` be called with roles from the JSON?  
**Answer:** No. The server must enforce a default role policy; granting ADMIN is a separate, authorized operation.

**Question 4:** `userExists(...)` returns false—is a subsequent `createUser(...)` guaranteed not to collide?  
**Answer:** No; between the two calls another request might create the account. Storage needs a unique constraint and conflict handling.

**Question 5:** `updateUser` removed `ROLE_ADMIN`, yet an old session still has this role. What kind of issue is this?  
**Answer:** You need lifecycle management for `Authentication`/sessions/tokens and a strategy for refreshing or revoking permissions; modifying the account record does not automatically update all issued identities.

**Question 6:** Does running `InMemoryUserDetailsManager` across three instances create a shared store?  
**Answer:** No. Each process holds its own map; data is not synchronized and is lost on restart.

**Question 7:** Does `deleteUser` mean deleting all business records, history, and every refresh token?  
**Answer:** No. It handles the account portion per the implementation; the rest requires application service/transaction/revocation policies.

## 14. Official Documentation

- [Spring Security 6.5 – UserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/UserDetailsManager.html): full `createUser`, `updateUser`, `deleteUser`, `changePassword`, `userExists`, and `UserDetailsService` inheritance.
- [Spring Security 6.5 – InMemoryUserDetailsManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/InMemoryUserDetailsManager.html): in-memory storage, constructors, and management operations.
- [Spring Security 6.5 – JdbcUserDetailsManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/JdbcUserDetailsManager.html): JDBC user/group management and configuration properties.
- [Spring Security 6.5 – In-Memory Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html): InMemory configuration and production limitations.
- [Spring Security 6.5 – JDBC Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/jdbc.html): schema, `DataSource`, and JdbcUserDetailsManager.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, providers, `SecurityContext`, and authentication lifecycle.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): account management, password policies, and risk controls.

**Key takeaway:** `UserDetailsManager` gives the application **an account management contract**; `UserDetailsService` loads data for authentication, while `AuthenticationManager`/`AuthenticationProvider` verifies credentials. Registration policies, admin permissions, password hashing, auditing, transactions, and session revocation must still be designed in the application layer.
