# Changing Passwords, Verifying the Current Password, and Atomic Data Updates

## Lesson Objectives

Changing a password while the user still has access to their account is a **security-sensitive** operation. It is not enough to accept `newPassword`, call `PasswordEncoder.encode(...)`, and overwrite the `password_hash` column: the application must also determine **who** is allowed to change it, verify proof that the caller **knows the current password** (or an equivalent policy-approved re-authentication mechanism), validate the new password, and update data so concurrent requests do not clobber each other's changes.

This article belongs to the **Password Upgrades** group in the *Spring Security - authentication* module. The focus rests on three interconnected concerns: **verifying the current password**, **persisting the new hash atomically**, and **keeping related data consistent**. The main example uses Java 17+, Spring Boot 3.x, Spring Security 6.x (`PasswordEncoder`), and Spring JDBC/H2. It runs as a command-line program to make transaction logic clear without building a login endpoint lacking CSRF/session protection.

After completing this lesson, you will know how to:

1. Distinguish **changing a password** while logged in from **forgot password / reset** via a recovery token, and from **automatic hash upgrades** on login.
2. Derive the target account from the server-authenticated identity instead of trusting a client-supplied `username`.
3. Verify `currentPassword` using `PasswordEncoder.matches(rawCurrent, storedHash)` rather than comparing hash strings or pulling passwords from `Authentication.getCredentials()`.
4. Encode `newPassword` with `PasswordEncoder.encode(rawNew)`, then update the hash and credential version using a **compare-and-set** SQL statement.
5. Use `@Transactional` so the hash update and outbox/audit records commit or roll back together, without mistakenly assuming transactions alone prevent lost updates.
6. Explain two concurrent password-change requests, stale reads, optimistic locking, row locking, transaction rollbacks, and non-atomic boundaries such as email or session revocation in external systems.
7. Run an H2 example with verifiable output: a wrong current password leaves the DB unchanged, a valid current password succeeds, the old hash no longer matches, the version increments exactly once, and the outbox adds only one event.

**Core principle:** always verify the current password against **the hash currently stored in the account store**; write the new hash with a conditional update guarding against concurrent overwrites; bind DB-local side effects into the same transaction; and enforce a session/token revocation policy after the change.

## 1. Distinguishing Three Frequently Conflated Flows

| Flow | What does the user prove? | Verification source | Primary outcome |
| --- | --- | --- | --- |
| **Password change** while logged in | Holds a valid session/identity **and** knows the current password (or equivalent strong re-auth) | `PasswordEncoder.matches(current, stored)` + policy | Saves new hash, increments credential version, considers revoking sessions |
| **Forgot password / reset** | Proves ownership via a valid recovery flow when password is forgotten | Reset token/OTP/passkey or allowed recovery method | Does not require old password; recovery token is single-use/short-lived |
| **Hash upgrade on login** | The password just entered was verified successfully by the provider | `PasswordEncoder.upgradeEncoding(stored)`, `UserDetailsPasswordService` | Rehashes the same password with a new cost/algorithm; not user-initiated password change |

These flows may write to the same password-hash column, yet **access control, authentication proof, and race conditions differ**. Never put all three behind one shared "change password code" and let the client pass `skipCurrentPassword=true`.

### 1.1. Why Still Require the Current Password When Already Logged In?

A user might forget to log out on a shared computer; a session cookie might be stolen; or a very old login session may no longer be strong enough proof for modifying credentials. Therefore, OWASP recommends **re-authentication** before sensitive changes like passwords or email addresses.

Users performing normal password changes usually must supply `currentPassword`. When an account authenticates exclusively via passkeys/SSO with no local password, design an equivalent **step-up authentication** step per assurance policy; never pretend you can verify a nonexistent password.

**Do not** retrieve the current password from `Authentication.getCredentials()`. Spring Security may have erased credentials after authentication; many mechanisms (JWT, sessions, OAuth2) never hold raw passwords at all. The current password must be **re-entered by the user over TLS** during the change operation or replaced by an explicitly designed valid re-authentication mechanism.

### 1.2. Who Can Change Whose Password?

Suppose Alice is authenticated yet submits this request body:

~~~json
{
  "username": "bob",
  "currentPassword": "alice-current",
  "newPassword": "new-value"
}
~~~

A `/me/password` endpoint **must not trust this `username` field** to select the account. The server must derive identity from `Authentication.getName()`, an account ID bound to a trusted principal, or the result of a re-authentication step, and then update **only that identity's credential**. Admin password resets for other users are a separate flow with dedicated authorization, auditing, and recovery mechanics; never turn a self-service endpoint into "change for any username".

In multi-tenant applications, username alone may not uniquely identify a user; use a stable account ID resolved from trusted identity/tenant context. **Never** trust client-declared `X-Tenant` headers or `userId` fields to pick the target row.

## 2. A Proper Password Change Workflow

Workflow at the business level:

~~~text
(1) Logged-in user invokes password change over HTTPS
        |
        v
(2) Server obtains account ID from trusted principal;
    applies authorization, CSRF, rate limits, step-up policy
        |
        v
(3) Load current hash + credential_version + account status
        |
        +-- Account no longer valid? -> reject
        |
        v
(4) PasswordEncoder.matches(currentRaw, storedHash)
        |
        +-- false -> reject; DO NOT write hash, DO NOT write audit success
        |
        v
(5) Check policy for newRaw:
    length, compromised password check, reuse policy, confirmation if any
        |
        v
(6) PasswordEncoder.encode(newRaw)
        |
        v
(7) Atomic UPDATE ... WHERE id = ? AND version = ?
        |
        +-- 0 rows -> stale/concurrent update; rollback, do not record success event
        |
        v
(8) INSERT outbox/audit record inside the same DB transaction
        |
        v
(9) Commit; only after commit is the change successful
        |
        v
(10) Revoke/adjust sessions and tokens, notify, observe
     per architecture; idempotent retries if off-DB side effects fail
~~~

An easily missed detail: if the operation runs inside a transaction, the `encode` step can be relatively CPU-intensive. In the learning example, we place the whole flow inside one `@Transactional` service to clearly demonstrate consistency. In high-load production systems, you can **read and verify outside the transaction**, then open a **short** transaction for the conditional update + audit/outbox; however, you must keep the version check to guard against changes between verification and commit, and re-check relevant account status policies.

### 2.1. currentPassword Must Be Verified Against the Stored Hash

Right approach:

~~~java
boolean correctCurrent = passwordEncoder.matches(
    currentPasswordFromRequest,
    passwordHashFromDatabase
);

if (!correctCurrent) {
    throw new CurrentPasswordRejectedException();
}
~~~

This is an **illustrative fragment** inside a service with its own variables and exceptions; not a standalone Java file. In Spring Security, `matches(CharSequence rawPassword, String encodedPassword)` takes the raw password first and the **full encoded string** second. It extracts the salt/cost from the stored hash string.

Two common mistakes:

~~~java
// WRONG: encode() with bcrypt generates a new random salt.
boolean wrong = passwordEncoder.encode(currentPasswordFromRequest)
    .equals(passwordHashFromDatabase);

// WRONG: grabbing credentials from Authentication and assuming it is the old password.
Object guessedCurrent = authentication.getCredentials();
// Credentials may be null/erased or a different credential type.
~~~

**Do not** use `String.equals(rawCurrent, storedHash)`; a raw password is not a hash. Do not try to decrypt bcrypt, do not log raw passwords or hashes, and never enable `NoOpPasswordEncoder` to "fix" logins.

### 2.2. newPassword Must Be Encoded Once for Storage

After verifying the current password and passing policy checks:

~~~java
String newEncodedPassword =
    passwordEncoder.encode(newPasswordFromRequest);
~~~

Keep the **entire** `newEncodedPassword` value, including salt/cost/algorithm prefix if the encoder emits one. With `BCryptPasswordEncoder`, encoding the same raw password twice produces different hashes; whether a password actually changed should be checked via policy and `matches(newRaw, oldStoredHash)` if blocking reuse of the current password, **never** via `newEncoded.equals(oldEncoded)`.

When using `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, stored values usually carry prefixes like `{bcrypt}...`; with plain `BCryptPasswordEncoder`, they look like `$2a$...` or a corresponding variant. Use an encoder compatible with the database format without stripping prefixes or coercing data formats.

### 2.3. How Does Confirming the New Password in a Form Differ?

UIs often have `newPassword` and `confirmNewPassword` fields. These are **two raw fields from the same request**, so you can compare them directly to check for typos:

~~~java
if (!newPassword.equals(confirmNewPassword)) {
    throw new IllegalArgumentException("Confirmation mismatch");
}
String newEncoded = passwordEncoder.encode(newPassword);
~~~

This is a validation snippet; it does not replace verifying the **current password**. Never encode both fields and compare the two encoded strings, because independent salts make them differ even when the user typed identically.

## 3. What Does "Atomic" Mean Exactly?

A successful password change must transition the system from:

~~~text
Before:
  account_id = 17
  password_hash = H_old
  credential_version = 8

After:
  account_id = 17
  password_hash = H_new
  credential_version = 9
~~~

We want **one complete state transition**—never leaving the DB with the new hash but the old version (or recording a success audit when the hash did not change). Nor do we want an older request to overwrite a newer password.

### 3.1. Three Distinct Concepts

| Technique | Solves | Does not automatically guarantee |
| --- | --- | --- |
| `@Transactional` on one DB | Commits/rolls back a group of SQL statements together | Does not automatically detect competing read–modify–write races; does not revoke JWTs/emails outside the DB |
| Conditional SQL update / compare-and-set | Updates only if the row still holds the expected version | Does not bundle other audit INSERT statements without a transaction |
| Row lock (`SELECT ... FOR UPDATE`) | Locks the row for the transaction duration per DB/isolation | Does not replace auth policy and does not make remote APIs/emails atomic |

A transaction **is not magic against lost updates**. Suppose two requests both read hash/version 8, both find the current password valid, and both run `UPDATE accounts SET password_hash = ? WHERE id = 17` without a version predicate. The later request can overwrite the earlier change, leaving the user unsure which password actually took effect.

### 3.2. Using Optimistic Compare-and-Set with Version

The key SQL statement:

~~~sql
UPDATE account_credentials
SET password_hash = ?,
    version = version + 1
WHERE id = ?
  AND version = ?
  AND enabled = TRUE;
~~~

The placeholders in order are:

1. New hash generated on the server by the encoder.
2. Stable account ID from the loaded row.
3. Version read right before verifying the current password.

If `updatedRows == 1`: exactly one row was still at the expected version and has been updated (pending transaction commit). If `updatedRows == 0`: data changed, the account was disabled, or the account no longer exists; **never claim the password change succeeded**. Return an appropriate conflict error and require retrying against the fresh state.

To keep the condition reliable, **all other** password-changing paths (recovery resets, admin changes, self-service changes, credential migrations) must follow the same `version`-incrementing convention. If one hash-updating path skips incrementing `version`, CAS on another path cannot reliably detect races.

**Never use `newHash.equals(oldHash)` as an optimistic lock.** Random salts and hash formats are not versioning mechanisms. Nor should you rely on low-resolution timestamps if multiple changes can occur within the same time unit; an integer version is explicit and easy to test.

### 3.3. Timeline of Two Concurrent Requests

~~~text
A: SELECT account #17, hash H8, version 8
B: SELECT account #17, hash H8, version 8

A: matches(current, H8) == true
B: matches(current, H8) == true

A: UPDATE ... WHERE id=17 AND version=8
   -> updatedRows=1, version becomes 9
   -> COMMIT

B: UPDATE ... WHERE id=17 AND version=8
   -> updatedRows=0 because version is now 9
   -> conflict/rollback

Result: CANNOT silently overwrite the password A just set.
~~~

Depending on the database and isolation level, request B might **wait on a lock**, encounter a deadlock/serialization failure, or observe fresh data if reading after commit. You are not required to get `updatedRows=0` under every locking model, but the invariant must hold: **never overwrite and falsely report success**. Retry starting from current verification after a conflict rather than blindly reusing stale snapshots/versions.

### 3.4. When Should SELECT FOR UPDATE Be Used?

Another option is:

~~~sql
SELECT id, password_hash, version, enabled
FROM account_credentials
WHERE id = ?
FOR UPDATE;
~~~

Inside a transaction, a row lock forces other transactions to wait or contend before modifying. It makes sense when complex multi-field state must be checked and updated consistently, yet it holds the lock while computing bcrypt/Argon2 (which can be slow). For password changes, **read-then-verify + CAS version update** is usually easier on contention. Never wrap `FOR UPDATE` around a long transaction doing email/network calls.

## 4. Complete Runnable Example: Spring Boot 3.x, JDBC, H2, BCrypt, and Transactions

This example is designed to run with Maven on Java 17+. It **does not start a web server**, using only `CommandLineRunner` to exercise test cases so there is no need to simulate cookies, CSRF, or HTTP status codes. The service layer is separated into a Spring-managed bean so `@Transactional` actually runs through its proxy.

Experimental goals:

- Alice starts with a hash of her initial password and `version=0`.
- Submitting a wrong current password → rejected, version stays `0`.
- Submitting the right current password → new hash saved, version becomes `1`.
- Old password no longer matches; new password matches.
- Exactly **one** `PASSWORD_CHANGED` event exists in the same-database outbox.
- Attempting to change again using the old password → rejected, no extra outbox event added.

### 4.1. Creating the Project and Dependencies

Generate a Maven project from Spring Initializr:

- Spring Boot **3.x**, Java **17 or 21**.
- Group `com.example`, artifact `atomic-password-change`.
- Package `com.example.demo`.
- Select **JDBC API / Spring JDBC** (`spring-boot-starter-jdbc`) and **H2 Database** (runtime).
- Add Spring Security Crypto directly under `dependencies` in `pom.xml`; Spring Boot's parent/dependency management manages the version:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-crypto</artifactId>
</dependency>
~~~

We do not need `spring-boot-starter-security` or `spring-boot-starter-web` in this CLI app. `spring-security-crypto` supplies `PasswordEncoder`/`BCryptPasswordEncoder` without setting up an HTTP security flow. When building a real endpoint, you will need Spring Web/Security starters and matching security configuration.

File tree:

~~~text
atomic-password-change/
├── pom.xml
└── src/main/
    ├── java/com/example/demo/
    │   ├── AtomicPasswordChangeApplication.java
    │   └── PasswordChangeService.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 4.2. Schema with Credential Version and Transactional Outbox

Create `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE account_credentials (
    id BIGINT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE credential_outbox (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES account_credentials(id)
);
~~~

`account_credentials.version` must be incremented **together** with the hash in the UPDATE; it is not a login session counter or failed-attempt counter. In production, you can name it `credential_version` to distinguish it from versions used for profile or account status fields.

`credential_outbox` records credential-change events **without containing raw passwords or hashes**. It demonstrates the transactional outbox pattern: writing an event inside the same DB transaction so a separate process can pick it up and send notifications/revoke tokens after commit. This demo does not implement the outbox consumer worker.

### 4.3. H2 DataSource Configuration

Create `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:password_change;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=embedded
~~~

In-memory H2 is non-durable once the app shuts down; the SQL is for demo use only. With Spring Boot and the JDBC starter, `schema.sql` runs against the embedded database before `CommandLineRunner` executes. On production databases, use migrations (Flyway/Liquibase) and proper connection pools/permissions/secret managers; never run learning `schema.sql` scripts on live data.

### 4.4. @Transactional Service: Verify Current, CAS, Outbox

Create `src/main/java/com/example/demo/PasswordChangeService.java`:

~~~java
package com.example.demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PasswordChangeService {

    private final JdbcTemplate jdbc;
    private final PasswordEncoder encoder;

    public PasswordChangeService(
        JdbcTemplate jdbc,
        PasswordEncoder encoder
    ) {
        this.jdbc = jdbc;
        this.encoder = encoder;
    }

    // Captures values read from the DB for compare-and-set.
    private record Credential(
        long id,
        String passwordHash,
        long version,
        boolean enabled
    ) { }

    public static final class InvalidCurrentPassword
            extends RuntimeException {
        public InvalidCurrentPassword() {
            super("Credential change rejected");
        }
    }

    public static final class InvalidNewPassword
            extends RuntimeException {
        public InvalidNewPassword() {
            super("New password rejected by policy");
        }
    }

    public static final class ConcurrentPasswordChange
            extends RuntimeException {
        public ConcurrentPasswordChange() {
            super("Credential changed concurrently");
        }
    }

    @Transactional
    public void changePassword(
        String authenticatedUsername,
        String currentPassword,
        String newPassword
    ) {
        if (authenticatedUsername == null
                || authenticatedUsername.isBlank()
                || currentPassword == null) {
            throw new InvalidCurrentPassword();
        }

        // Minimal policy for demo purposes only.
        if (newPassword == null
                || newPassword.length() < 12
                || newPassword.length() > 128) {
            throw new InvalidNewPassword();
        }

        Credential credential = jdbc.query(
            """
            SELECT id, password_hash, version, enabled
            FROM account_credentials
            WHERE username = ?
            """,
            rs -> {
                if (!rs.next()) {
                    return null;
                }
                return new Credential(
                    rs.getLong("id"),
                    rs.getString("password_hash"),
                    rs.getLong("version"),
                    rs.getBoolean("enabled")
                );
            },
            authenticatedUsername
        );

        if (credential == null
                || !credential.enabled()
                || !encoder.matches(
                    currentPassword, credential.passwordHash()
                )) {
            throw new InvalidCurrentPassword();
        }

        // Disallow reusing the exact current password.
        if (encoder.matches(
            newPassword, credential.passwordHash()
        )) {
            throw new InvalidNewPassword();
        }

        String nextHash = encoder.encode(newPassword);

        int changed = jdbc.update(
            """
            UPDATE account_credentials
            SET password_hash = ?,
                version = version + 1
            WHERE id = ?
              AND version = ?
              AND enabled = TRUE
            """,
            nextHash,
            credential.id(),
            credential.version()
        );

        if (changed != 1) {
            throw new ConcurrentPasswordChange();
        }

        // Same DB transaction as the UPDATE: no success event
        // is persisted if the credential change fails to commit.
        jdbc.update(
            """
            INSERT INTO credential_outbox(account_id, event_type)
            VALUES (?, ?)
            """,
            credential.id(),
            "PASSWORD_CHANGED"
        );
    }
}
~~~

**Explaining each key design choice:**

- `authenticatedUsername` is named that way as a reminder that **the caller must pass the username from the server's authenticated identity**, not a client-supplied username. In the CLI demo, we pass `"alice"` manually solely for simulation.
- Before changing the hash, the service loads the current record and calls `encoder.matches(current, storedHash)`. Without a valid current password, no new hash is generated and no update runs.
- `enabled` is checked from the DB; the `UPDATE` also includes `enabled=TRUE`. If the account gets disabled mid-operation, the conditional update offers partial protection. If policy requires guarding other status fields, include them in the predicate and versioning strategy.
- `newPassword.length()` measures **UTF-16 code units** and is merely a demo bound, not a full production policy. Production systems need Unicode/byte policies, breached-password checks, maximum payload bounds against DoS, reuse rules, and support for long passphrases.
- `encoder.matches(new, oldHash)` prevents picking **the current password again**; comparing two `encode` outputs fails due to random salts.
- `UPDATE ... WHERE version = ?` performs CAS: only one request holding the old version can succeed. `changed != 1` throws an unchecked exception to roll back.
- `INSERT credential_outbox` runs after the update, **in the same transaction**, so it commits or rolls back together with the password change. Never put hashes or raw passwords into the event table.
- The service bean is invoked from **another bean**, allowing Spring's transaction proxy to intercept calls. Calling `this.changePassword(...)` from another method inside the same object may **not** start a transaction in default proxy mode.
- If the outbox `INSERT` fails, Spring JDBC's unchecked `DataAccessException` rolls back the `UPDATE` too by default. If business logic throws a **checked exception** and expects rollback, configure rollback rules explicitly rather than assuming checked exceptions roll back.

### 4.5. Main Application, Seeding, and Exercising Branches

Create `src/main/java/com/example/demo/AtomicPasswordChangeApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class AtomicPasswordChangeApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            AtomicPasswordChangeApplication.class, args
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    CommandLineRunner demonstrate(
        JdbcTemplate jdbc,
        PasswordEncoder encoder,
        PasswordChangeService changes
    ) {
        return args -> {
            String oldPassword = "Initial-Password-2026!";
            String newPassword = "Future-Password-2027!";

            jdbc.update(
                """
                INSERT INTO account_credentials
                    (id, username, password_hash, enabled, version)
                VALUES (?, ?, ?, ?, ?)
                """,
                1L, "alice",
                encoder.encode(oldPassword),
                true, 0L
            );

            boolean badCurrentRejected = false;
            try {
                changes.changePassword(
                    "alice", "wrong-current", newPassword
                );
            }
            catch (PasswordChangeService.InvalidCurrentPassword ex) {
                badCurrentRejected = true;
            }

            Long versionAfterBad = jdbc.queryForObject(
                "SELECT version FROM account_credentials "
                    + "WHERE username = ?",
                Long.class,
                "alice"
            );

            changes.changePassword(
                "alice", oldPassword, newPassword
            );

            boolean oldCannotChangeAgain = false;
            try {
                changes.changePassword(
                    "alice", oldPassword, "Another-Password-2028!"
                );
            }
            catch (PasswordChangeService.InvalidCurrentPassword ex) {
                oldCannotChangeAgain = true;
            }

            String storedHash = jdbc.queryForObject(
                "SELECT password_hash FROM account_credentials "
                    + "WHERE username = ?",
                String.class,
                "alice"
            );

            Long newVersion = jdbc.queryForObject(
                "SELECT version FROM account_credentials "
                    + "WHERE username = ?",
                Long.class,
                "alice"
            );

            Integer eventCount = jdbc.queryForObject(
                "SELECT COUNT(*) FROM credential_outbox "
                    + "WHERE account_id = ?",
                Integer.class,
                1L
            );

            System.out.println("badCurrentRejected="
                + badCurrentRejected);
            System.out.println("versionAfterBad="
                + versionAfterBad);
            System.out.println("newPasswordMatches="
                + encoder.matches(newPassword, storedHash));
            System.out.println("oldPasswordRejected="
                + !encoder.matches(oldPassword, storedHash));
            System.out.println("versionAfterSuccess="
                + newVersion);
            System.out.println("outboxEvents="
                + eventCount);
            System.out.println("oldCannotChangeAgain="
                + oldCannotChangeAgain);
        };
    }
}
~~~

Spring Boot initializes the H2 DataSource from `application.properties`, executes `schema.sql`, and then runs `CommandLineRunner`. Calls to `changes.changePassword(...)` from the runner into the service are **external bean calls**, so `@Transactional` applies once the JDBC starter auto-configures the transaction manager.

In the demo, BCrypt cost 10 is used solely to keep study runs fast; production deployments must choose hashing parameters from benchmarks and security guidance. Demo password strings are hardcoded for convenience—**never do that in production**—and the code prints neither raw passwords nor hashes.

### 4.6. Running and Expected Output

In the directory containing `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Aside from Spring Boot logs, the lines **printed by `CommandLineRunner`** are:

~~~text
badCurrentRejected=true
versionAfterBad=0
newPasswordMatches=true
oldPasswordRejected=true
versionAfterSuccess=1
outboxEvents=1
oldCannotChangeAgain=true
~~~

These are deterministic logical outputs independent of the exact BCrypt hash string (salts are randomly generated). If you print `storedHash` locally while studying, the string will vary across runs; **never log hashes in real operations**.

Meaning:

1. `badCurrentRejected=true`: the service rejected the wrong current password.
2. `versionAfterBad=0`: the failure branch did not overwrite the password.
3. `newPasswordMatches=true`: the hash in the DB matches the new password.
4. `oldPasswordRejected=true`: the new hash no longer accepts the old password.
5. `versionAfterSuccess=1`: one successful change incremented the version by exactly one.
6. `outboxEvents=1`: the success event was written once in the same transaction as the update.
7. `oldCannotChangeAgain=true`: after changing, the user cannot reuse the old password to change it again.

**Limitations:** the example does not run two concurrent threads, does not implement session/token invalidation, and does not simulate H2 commit failures. The **atomic CAS** property comes from the version-conditional SQL statement; proving it in production requires concurrency integration tests against your real database engine and isolation level.

## 5. Testing Atomicity: Mandatory Test Cases

| Test case | Expected outcome |
| --- | --- |
| Wrong current password | Hash unchanged; version unchanged; no outbox success event |
| Missing or disabled account | DB unchanged; public response leaks no account details |
| New password violates policy | Hash/version unchanged; returns controlled policy error |
| New password equals current password | Rejected per example policy; no DB write |
| Right current, valid new | Single UPDATE succeeds; version +1; outbox has one event |
| Two requests both read version `v` | At most one request commits `v` to `v+1`; the other gets stale/conflict or concurrency error; no silent overwrite |
| Outbox INSERT fails | Transaction rolls back: hash/version revert to old state |
| Password reset racing with self-service change | Shared version convention prevents stale updates from overwriting reset |
| Account disabled between read and update | Status/version predicate causes policy-violating update to fail |
| DB transaction commits then email fails | Hash **already changed**; outbox needs retry; never claim DB rolled back |
| Calling `@Transactional` method via `this.method()` | Test catches missing proxy and unapplied transaction |
| Retry after network timeout with unknown commit status | Must read fresh state / use idempotency policy; no blind retry with old version |

### 5.1. Testing Outbox Integrity

One way to test is deliberately making `INSERT credential_outbox` fail in an **isolated test database**, then reading back `password_hash` and `version` after the transaction finishes. Because Spring JDBC throws an unchecked exception, the default transaction manager rolls back. Never create destructive triggers in production schemas to test this.

If that test fails to roll back, check:

- Was the service actually instantiated by Spring behind a `@Transactional` proxy?
- Is it called from another bean rather than self-invocation?
- Does the `JdbcTemplate` writing the password and outbox share the **same DataSource and transaction manager**?
- Did code catch the exception without rethrowing or marking rollback-only?
- Did a query/driver bypass the transaction or auto-commit DDL?
- Were rollback rules altered by `noRollbackFor` or custom transaction settings?

`@Transactional` does not provide 2PC across multiple databases or email services; the example uses **the same DB** to guarantee atomic commits between the hash and outbox.

### 5.2. Testing Concurrency Without Depending on Thread Ordering

In integration tests, create two password-change operations using the same old current password but choosing **two different new passwords**. Use a barrier/latch so both read the same version, then release them together; or inject a test seam after the read if deterministic reproduction is needed.

Assert **invariants** rather than asserting thread A wins:

- Version moves from `v` to `v+1` for **one** valid change only.
- Final hash matches **one of the two** new passwords, never silently overwritten twice from the same version.
- There is **one** success event for that version.
- The losing transaction gets a conflict, re-authentication failure, or equivalent concurrency exception—**never** a false success.
- Retries must re-read the version and re-verify the current password, never reusing stale snapshot values.

With specific database isolation/drivers, the losing transaction may hit a lock timeout, deadlock, or serialization failure instead of `updatedRows=0`; the application should map this concurrency error group to appropriate API behavior without emitting extra side effects.

## 6. What to Watch When Exposing the Service as an HTTP Endpoint

The demo service **has no HTTP layer**, whereas a real API must accept requests with an authenticated identity, require the current password, and enforce web protections.

An **illustrative controller, not a standalone runnable file** without Spring Web/Spring Security/filter chain setup:

~~~java
record ChangePasswordRequest(
    String currentPassword,
    String newPassword
) { }

@PostMapping("/me/password")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void changePassword(
    Authentication authentication,
    @RequestBody ChangePasswordRequest request
) {
    // /me/password must be protected by SecurityFilterChain.
    // authentication comes from Spring Security, NOT from the body.
    changes.changePassword(
        authentication.getName(),
        request.currentPassword(),
        request.newPassword()
    );
}
~~~

This needs Spring MVC/Security imports, an injected `PasswordChangeService changes`, `/me/password` configured to require `authenticated()`, and an appropriate exception handler. If the principal carries an internal ID, prefer using that ID, especially when usernames can change or overlap across tenants.

**Never** expose `POST /users/{id}/password` checking only that a user is logged in without checking that `{id}` belongs to them, unless it is a separately authorized admin flow. That is an **IDOR/BOLA** vulnerability.

### 6.1. Being Authenticated Differs from "Just Re-Authenticated"

A session cookie created yesterday may still be `authenticated()`. That **does not** substitute for verifying the current password on a sensitive action. The service must run `matches` against the current hash at the moment of change, or use an appropriate step-up mechanism with explicit time/policy limits.

If the client uses JWT/SSO and the local account **has no password**, never let callers supply any arbitrary string and skip verification; identify the provider and the issuer's re-authentication mechanism, or direct the user to credential management at the IdP. Never store/change a local password for an exclusively IdP-managed account without an authorized workflow.

### 6.2. CSRF, CORS, SameSite, and TLS

When an application relies on **cookies/sessions** or browsers automatically sending Basic credentials, POST password-change endpoints must be protected against **CSRF**. Requiring the current password increases confidence, yet **does not** replace CSRF defenses. With Spring Security Servlet, keep appropriate CSRF protection enabled for browsers and wire the token/cookie/session flow properly; never disable `csrf` just to make a curl demo work.

CORS only controls browser-initiated cross-origin reads/requests and **is not a CSRF substitute**. Cookie `SameSite` is defense-in-depth, not a sole layer. All passwords in requests must travel over **HTTPS**, never appear in URLs/query strings or server logs, and responses with sensitive content should include `Cache-Control: no-store`.

### 6.3. Controlled HTTP Error Mapping

| Error | Possible API handling choice |
| --- | --- |
| Missing authentication or expired session | `401 Unauthorized`, require login |
| Authenticated user lacks permission | `403 Forbidden` |
| Current password mismatch | `400` or `403` per contract; message leaks no data |
| New password fails policy | `400` with standardized policy errors |
| Concurrent change / stale version | `409 Conflict` or appropriate retry contract |
| Success | `204 No Content` or `200` without raw/hash values |
| DB/outbox infrastructure failure | `5xx`/retry policy; never return success before commit |

These are **API contract suggestions**; Spring Security does not automatically map custom exceptions to those statuses. Never expose whether a user exists or an account is disabled in public messages. All failure branches must avoid leaving hashes or transactions half-applied.

## 7. Atomic Transactions Do Not Mean Instant Session Revocation

Successfully changing a password in the database **does not automatically invalidate** previously issued session cookies, remember-me tokens, refresh tokens, or JWT access tokens. An older session's `SecurityContext` may still hold a valid `Authentication`; a JWT resource server may only validate signature, expiry, issuer, and scopes.

Define a clear policy:

1. Keep the current session while forcing re-login on other sessions, or log out **all** sessions?
2. Is the session store single-node in-memory or distributed? Can you look up and terminate every session by account ID?
3. How are persistent remember-me tokens, refresh tokens, OAuth2 authorizations, and access tokens revoked?
4. If using stateless JWTs, do you enforce short TTLs, revocation lists, introspection, or checking `credential_version` in tokens against the account?
5. If events cannot be delivered immediately, can sensitive resources tolerate an eventual-consistency window?
6. After a change/reset, should a notification be sent via registered channels? Never put the new password or hash in the email.

### 7.1. Distinguish DB Atomicity from Off-DB Side Effects

An SQL transaction **cannot roll back an already-sent email**, an HTTP call to an IdP, or a session deleted in a separate Redis instance without appropriate distributed coordination.

Mistake:

~~~text
BEGIN DB TRANSACTION
  UPDATE password
  call email service
  invalidate Redis sessions
COMMIT DB
~~~

If the email succeeds and then `COMMIT DB` fails, the user receives a password-change alert while the old hash remains. If sessions are deleted before commit and the transaction rolls back, the user gets logged out without their password changing. The cross-system outcome is non-atomic.

The **transactional outbox** design in the example:

~~~text
Inside a transaction on the same DB:
  UPDATE account_credentials ... CAS
  INSERT credential_outbox(..., 'PASSWORD_CHANGED')
COMMIT

After commit, a worker/outbox relay:
  reads event
  -> sends notification
  -> revokes sessions/tokens per policy
  -> retries if infrastructure fails
  -> marks event processed, idempotently
~~~

An outbox ensures **we do not lose side-effect intent** once the DB commits, yet **does not make off-DB effects atomic or instantaneous**. If credential revocation cannot lag by even a single request, token/session validation must enforce synchronous version or state checks per SLA rather than relying solely on async emails/events.

### 7.2. Password Change vs. Password Reset on Sessions

For **forgot password / reset**, the user may be logged out; you need recovery tokens with strong entropy, TTLs, single-use semantics, rate limits, and accurate verification. OWASP recommends considering or automatically invalidating existing sessions and **not automatically logging the user in** after a reset unless there is a clear security reason.

For **changing passwords while logged in**, keeping the current session after step-up or requiring re-login depends on risk, policy, and product needs. Either way, revoking or keeping other sessions must be an intentional, tested decision—not something assumed to "happen automatically" because `password_hash` changed.

## 8. Roles of UserDetailsManager and UserDetailsPasswordService

Two easily confused interfaces:

| Component | Contract | When used |
| --- | --- | --- |
| `UserDetailsService` | `loadUserByUsername(...)` to load an account | Username/password authentication via provider |
| `UserDetailsManager` | Extends service with CRUD and `changePassword(oldPassword, newPassword)` | User/password management if implementation fits policy |
| `UserDetailsPasswordService` | `updatePassword(UserDetails user, String newPassword)`, receives **already-encoded** password | Provider-initiated hash upgrade after successful authentication |
| `PasswordEncoder` | `encode(raw)`, `matches(raw,encoded)`, `upgradeEncoding(encoded)` | Hashing/verification/migration |
| Domain `PasswordChangeService` in demo | Verifies current, enforces policy, CAS version, and outbox | Self-service password change with app-specific consistency rules |

Per Spring Security 6.5 JavaDoc, `UserDetailsManager.changePassword(String oldPassword, String newPassword)` modifies the current user's password in persistent storage; `oldPassword` is used for **re-authentication if the implementation requires it**. **Never infer from the interface alone** that every implementation verifies the old password, runs in one transaction, uses optimistic locking, or revokes sessions. Read the concrete implementation and test against your real schema/provider.

`UserDetailsPasswordService.updatePassword(UserDetails user, String newPassword)` is used with `DaoAuthenticationProvider` when upgrading password **encoding** after a successful login, typically wired via `provider.setUserDetailsPasswordService(...)`. It is not a user-initiated password-change endpoint taking `currentPassword`/`newPassword`. Its `newPassword` argument normally represents an **already-encoded value**, and persistence must be designed accordingly.

### 8.1. Changing Passwords Is Not Merely "Bumping Cost"

Suppose a user has raw password `P`, and the stored hash is bcrypt cost 10:

- **Hash upgrade:** after the provider verifies `P` successfully, it generates another hash of **the same `P`** at a higher cost and saves it with version/race control.
- **User change:** the user submits current `P` and new `Q`; the server verifies `P` and stores the hash of **`Q`**.
- **Forgot password reset:** the user need not know `P`; they prove ownership via a recovery token and set `Q`.

All three flows can touch the same credential version. A concurrent reset or hash upgrade must never silently overwrite a successful password change; share the same CAS convention and conflict resolution rules.

## 9. Implementation Pitfalls and Diagnostics

| Symptom | Problem | Fix |
| --- | --- | --- |
| Anyone with a session can change without current password | Missing step-up/re-authentication | Require current password or equivalent factor |
| Changing password for client-supplied ID | IDOR/BOLA | Take account ID from trusted principal/tenant and check authorization |
| Verifying with `encode(raw).equals(storedHash)` | Random salt makes new hash differ from old | Use `matches(raw,storedHash)` |
| Comparing raw password directly to stored hash | Different formats | Use the right `PasswordEncoder` |
| Reading current password from `Authentication.getCredentials()` | Credentials may be erased or not a raw password | Prompt for re-entry via step-up step |
| Two concurrent password-change requests both report OK, only one works | Lost update, missing CAS/version | Version-conditional `UPDATE`, check affected rows |
| `@Transactional` present yet lost update still happens | Transaction alone does not stop stale reads | Add CAS or suitable locking/isolation |
| `@Transactional` present yet outbox does not roll back | Self-invocation, wrong transaction manager/DataSource, swallowed exception | Call through Spring bean proxy, share DB transaction, test rollback |
| Password changed yet audit missing | Audit outside transaction or write failures unchecked | Write transactional outbox/audit in the same DB |
| Notification sent even though DB rolled back | Called remote service before commit | Outbox + post-commit relay, idempotent retries |
| Password changed yet other sessions keep running | Sessions/tokens not revoked | Build revocation policy across credential types |
| User change looks up username without tenant | Matches wrong account | Stable account ID and verified tenant context |
| New password matching old password still accepted | Missing reuse policy | Use `matches(newRaw, oldStoredHash)` to block current password reuse |
| Changing encoder breaks old hash verification | Mismatched bcrypt/delegating/legacy format | Controlled format migration, test before rollout |
| User sees failure even though hash changed | Timeout after commit, unclear retry state | Design error/idempotency/recovery flows and state reads |
| Passwords appear in logs/outbox | Unsafe telemetry design | Never put secrets/hashes in events; enforce strict secret hygiene |

### 9.1. Data Edge Cases to Consider

**Already-migrated hashes:** the column may store `{bcrypt}$2a$...` (delegating) or `$2a$...` (plain bcrypt). The encoder must match the DB format. Comparing strings during password changes can mislead when salts or costs differ even for identical passwords.

**Account status:** the demo checks `enabled`. Real systems may also have `locked`, `accountExpired`, `credentialsExpired`, `suspended`, and MFA policies. Never check `enabled` alone while ignoring other statuses during credential changes.

**Multiple credential stores:** an account might hold a local password, IdP password, API key, or passkey. Identify clearly **which credential** is changing; never write a new local hash if the user authenticates purely via SSO with no valid local password.

**Credential reuse history:** many products disallow reusing the last N passwords. Because of random salts, string equality cannot detect reuse. You must check `PasswordEncoder.matches(newRaw, historicalEncodedHash)` across a bounded history set or enforce an alternative policy, balancing CPU/DoS risk and data retention; never store raw passwords for comparison.

**Unicode/normalization:** do not automatically `trim()`, lowercase, or strip/alter Unicode diacritics (such as Vietnamese accents) on only one side of registration/change/login. Passwords may contain whitespace. If policy requires normalization, apply it consistently with a migration plan. `String.length()` counts UTF-16 code units, not bytes or Unicode graphemes.

**Bcrypt work factor:** new hashes get new salts and current cost. Higher costs increase CPU latency for verify/encode; transactions may hold DB connections while bcrypt runs. Test under concurrency, consider keeping transactions short, and protect login/change-password endpoints with rate limiting.

## 10. Exercises and Answers

**Exercise 1 — Wrong current password.** The service read `version=4`, and the user entered a wrong current password. Should you still compute a new hash and update before returning an error to avoid leaking timing?

**Answer:** No. Never update an account without verifying the current password. If timing protection is required, use vetted constant-time/timing-mitigation techniques rather than mutating credentials on failed authentication.

**Exercise 2 — Two updates without versioning.** A and B both read the old hash. A saves `A-new`, and B saves `B-new`. Both updates affect 1 row. Can both requests be called "successful" under policy?

**Answer:** No, if policy forbids concurrent overwrites. Use CAS/versioning or appropriate row locks, check affected row counts, and control side effects.

**Exercise 3 — CAS updates 0 rows.** Current password matched earlier, yet `UPDATE ... WHERE version=?` updates 0 rows. Should you still `INSERT` `"PASSWORD_CHANGED"` into the outbox and return 204?

**Answer:** No. That indicates a conflict or state change; roll back, do not emit success, and require the caller to re-verify against the new state.

**Exercise 4 — New hash and audit live in two tables of one DB.** Can a transaction commit both or roll back both together?

**Answer:** Yes, provided they share the same transaction manager/DataSource and both SQL statements genuinely execute inside the transaction. `@Transactional` does not synchronize external emails or Redis with the commit.

**Exercise 5 — Email fails after commit.** The hash changed and the outbox holds the event. Should you roll back the DB?

**Answer:** You cannot simply roll back an already-committed transaction. The worker retries idempotently from the outbox; apply notification and revocation policies in the meantime.

**Exercise 6 — User has a valid JWT and no local password.** Can you skip current password verification and let the client write any `newPassword`?

**Answer:** No. Define an authorized workflow for creating/changing local credentials with an equivalent step-up step; a normal bearer JWT does not prove the user knows a current password.

**Exercise 7 — Using `UserDetailsManager.changePassword(old,new)`.** Can you assume it always includes optimistic locking and outbox rollback?

**Answer:** No. The interface does not mandate those implementation details. Inspect the concrete provider/manager and test against your real database.

**Exercise 8 — Changing only the hash in the DB.** An old session still holds an authenticated principal and a JWT has not expired. Will new requests definitely be rejected?

**Answer:** No. You need explicit invalidation policies for sessions, refresh tokens, remember-me tokens, and JWT/token versions.

**Exercise 9 — Calling the service via `this.changePassword(...)`.** Why might `@Transactional` stop working?

**Answer:** In default proxy mode, self-invocation bypasses the Spring proxy so the transaction interceptor never runs. Call the service through a Spring-managed bean and test rollbacks.

**Exercise 10 — Password confirmation field present.** Should you compare the two raw fields or encode both and compare the two hashes?

**Answer:** Compare raw values during validation of the same request, then encode the new password only once policy and current verification pass. Two bcrypt hashes have distinct salts so `equals` cannot confirm form input.

## 11. Pre-Deployment Design Checklist

- [ ] Password-change endpoint is restricted to authenticated identities; account ID comes from trusted principal/tenant context.
- [ ] Current password verified via `PasswordEncoder.matches(currentRaw, storedEncoded)` or a policy-approved step-up equivalent.
- [ ] Never use `Authentication.getCredentials()` as the default current-password source; never craft authenticated tokens manually to skip checks.
- [ ] Validate new password policy (length, breach check, Unicode, reuse, payload limits) before persisting.
- [ ] Call `encode(newRaw)` once to store the full hash; never re-hash old hashes and never compare two `encode` results.
- [ ] Maintain a `credential_version` column or equivalent concurrency guard synchronized across change/reset/admin/migration flows.
- [ ] Use SQL `UPDATE ... WHERE id=? AND version=?`, inspect updated row counts, and handle conflicts/rollbacks.
- [ ] Accompanying DB writes (outbox/audit/version) share the same transaction and are rollback-tested on failures.
- [ ] Never assume transactions cover emails, Redis, or IdPs; use an outbox and idempotent retries for post-commit side effects.
- [ ] Protect endpoints with HTTPS, CSRF for browser cookies, rate limits, authorization, and re-authentication/MFA when needed.
- [ ] Define clear revocation policies for sessions, remember-me, refresh tokens, and access JWTs after password change/reset.
- [ ] Keep raw passwords, hashes, peppers, and tokens out of logs, audit events, emails, URLs, and responses.
- [ ] Tested wrong/right current, invalid/reused new, disabled account, two simultaneous changes, outbox rollback, stale version, DB errors, and old tokens.
- [ ] Benchmarked encoder cost, lock/transaction duration, and retry behavior on the same database engine/isolation as production.
- [ ] Have operational handling when a request times out after commit and the client does not know whether the change succeeded.

**Conclusion:** secure password changes go beyond `passwordEncoder.encode(newPassword)`. The critical steps are **verifying the current password against a trusted hash**, **persisting the new hash via version-guarded conditional SQL**, and using a **transaction** to keep credentials and DB outbox/audit records synchronized. That way, a wrong current password leaves data untouched, concurrent requests never silently overwrite one another, and events are recorded strictly on commit. Session/token revocation and post-commit notifications are separate concerns requiring explicit policies, error handling, and thorough testing.

## References

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security 6.5 — UserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/UserDetailsManager.html)
- [Spring Security 6.5 — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction Rollback Rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [OWASP — Authentication Cheat Sheet: Change Password Feature](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
