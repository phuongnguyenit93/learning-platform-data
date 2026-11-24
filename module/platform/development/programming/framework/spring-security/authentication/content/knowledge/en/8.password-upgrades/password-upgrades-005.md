# Migration Policy for Accounts That Cannot Be Upgraded Directly

In Spring Security Authentication, upgrading a password hashing policy does not mean the system can take an old password hash, call a new encoder, and immediately get an equivalent hash. **Password hashing is a one-way verification transformation**: to produce a new password hash that still lets the user log in with their original password, the application normally needs **the raw password just verified successfully**, or the user must **set a new password** through a trusted identity recovery flow.

Therefore, when switching algorithms, raising work factors, retiring weak formats, or migrating from a legacy account system to Spring Security, not every account can be upgraded immediately in a background job. Some accounts may not have logged in for years, lack a verified recovery email, use hashes of unknown format, depend on an external identity system, be disabled, or hold credentials considered at risk. **You need a migration policy based on state and risk level, rather than blindly hashing on top of old values.**

This article belongs to the **Password Upgrades** group and focuses on accounts that **cannot be upgraded directly**: identifying, segmenting, deciding between controlled legacy login vs. mandatory reset, designing safe recovery paths, integrating Spring Security's `PasswordEncoder`/`UserDetailsPasswordService`, handling concurrency, multi-version deployment, a runnable Java 17 example, and a practical test suite.

## 1. What Does "Cannot Be Upgraded Directly" Mean?

First, distinguish **three operations**:

| Operation | Needs raw password? | What actually changes |
|---|---|---|
| **Format labeling** | No, if old algorithm is accurately identified | E.g., `$2a$...` becomes `{bcrypt}$2a$...`; actual hash stays intact |
| **Rehash / algorithm or cost upgrade** | **Yes, normally requires a verified raw password** | Generates a new hash from the original password using a new KDF/cost |
| **Password reset** | Does not need old password, but **must verify ownership via safe recovery** | User chooses a new password; server encodes and stores the new hash |

### 1.1. Why Can't Old Hashes Be Hashed into New Hashes?

Suppose an account stores:

~~~text
oldHash = bcrypt("UserPassword", saltA, cost10)

Wrong idea:
newHash = argon2id(oldHash, saltB, newParams)

Subsequent login:
argon2id("UserPassword", saltB, newParams) != newHash
~~~

In the wrong flow, the server hashed **the `oldHash` string** rather than the `"UserPassword"` the user remembers. `matches(rawPassword, newHash)` with the original raw password will fail to match. Thus **`encode(storedHash)` is not a password hash upgrade**.

There are specialized *hash wrapping* strategies for transitioning off legacy hashes: they require a matching verification design, awareness of the old algorithm's risks, and attack-cost analysis. They are **not equivalent** to rehashing from raw passwords, can prolong dependence on weak hashes, and should not be used as a default recipe for account migration.

### 1.2. When Can You Upgrade During Login?

If the system **can still safely verify the legacy algorithm/format**, the user actively enters the right password, and the provider verifies it, then at that moment the raw password is available to create a new hash. Flow:

~~~text
User submits password over HTTPS
    |
    v
Read old storedHash for the account
    |
    +--> Legacy encoder.matches(raw, storedHash)
    |       |
    |       +-- false -> deny authentication
    |       '-- true  -> raw password is verified
    |
    +--> Policy: upgradeEncoding needed?
    |       |
    |       +-- yes -> currentEncoder.encode(raw)
    |       |          -> update DB with concurrency control
    |       '-- no  -> keep valid hash
    |
    v
Continue login if account passes all security checks
~~~

**Limitation:** "not logging in" means the server **has no raw password** to rehash on its own; and "no longer able to verify the legacy format" means even a raw password just sent by the client **cannot be trusted as correct** through guesswork comparison. The two situations require different policies.

## 2. Segmenting Accounts Before Building the Migration Roadmap

A migration campaign should begin with a **controlled inventory that never puts hashes/secrets into logs**. Segment accounts by credential state, verifiability, risk, and recoverability.

| Group | Example | Can rehash directly from old hash? | Handling approach |
|---|---|---|---|
| **A. Verifiable legacy** | `{bcrypt10}...` or old PBKDF2 with a trusted decoder | **No** without raw; **yes** after valid login | Keep decoder during transition window; upgrade after auth |
| **B. Unverifiable legacy** | Unknown hash algorithm, truncated data, missing salt | **No** | Block this password login path; verify ownership then reset |
| **C. Long-inactive accounts** | Months/years without login, hash still in weak format | **No** when raw is absent | Set support deadline; expire credential and require reset upon return |
| **D. No trusted recovery channel** | Unverified email, lost access to old mailbox | **No** | Escalated recovery via registered factors; hold if insufficient proof |
| **E. External identity / SSO-only** | Account logs in only via OIDC/SAML, no local password | **Not applicable** | Never generate local passwords; manage IdP mapping and credential state separately |
| **F. Disabled/locked/compromised accounts** | Locked due to risk or suspected breach | Must not open login just to upgrade | Investigate, preserve lock, or require recovery per policy |
| **G. Valid format missing ID** | Verified bare bcrypt `$2a$...` | Can **add ID metadata**; not a rehash | Prefix migration for exact algorithm, then upgrade on login |
| **H. Integrity/import errors** | Two accounts sharing wrong ID, hash assigned to wrong owner | Never rely on ambiguous rows | Quarantine, fix identity/provenance before credential flows resume |

Classification must rely on **evidence from trusted data sources**, not an ambiguous string pattern in a single row. For instance, a 64-hex-character string might be SHA-256, or it might be a token/custom format; guessing `{sha256}` and allowing logins is unsafe.

### 2.1. Distinguishing "Insufficient Data" from "Non-Existent Account"

An account record without a hash could be SSO-only, pending verification, credential-wiped by policy, or damaged by a buggy migration. Do not auto-generate default passwords or return the same internal state for every case without classification. However, **public** responses must still avoid disclosing whether an account exists to prevent account enumeration.

### 2.2. Migration State Is Not the Only Account State

An account can simultaneously have:

~~~text
account.status            = ACTIVE
credential.migrationState = RESET_REQUIRED
credential.hashAlgorithm  = LEGACY_UNKNOWN
mfa.enrollmentState       = ENROLLED
sessions.revocationEpoch  = ...
~~~

Being `ACTIVE` at the domain level does not automatically authorize password login. Credential state belongs in its own layer, while the account itself can also be `DISABLED`, `LOCKED`, or `EXPIRED`. Never collapse everything into a single `passwordNeedsUpgrade` boolean because **"should upgrade after login"** is very different from **"must no longer verify the old password"**.

## 3. Designing the Migration State Machine

A concise model for an account's credential:

| Migration state | Verifies with old password? | Exit transition |
|---|---|---|
| `CURRENT` | Yes | Current hash meets policy; change/reset password when needed |
| `LEGACY_VERIFIABLE` | Yes **temporarily**, per deadline/risk policy | Valid login → rehash with new encoder; or successful reset |
| `RESET_REQUIRED` | **No** via old password login | Verified recovery → set new password → `CURRENT` |
| `RECOVERY_HOLD` | No | Provide additional ownership proof via safe channel; or close account |
| `EXTERNAL_ONLY` | No local password | Authenticate via valid IdP; never create local secret |
| `SUSPENDED` | No | Status/incident resolution workflow, optionally followed by reset |

Key transitions:

~~~text
LEGACY_VERIFIABLE --(valid login + CAS rehash)-------> CURRENT
LEGACY_VERIFIABLE --(deadline/read access expired)---> RESET_REQUIRED
RESET_REQUIRED ----(verified recovery + reset)-----> CURRENT
RECOVERY_HOLD -----(sufficient identity proof)------> RESET_REQUIRED
EXTERNAL_ONLY -----(IdP auth)----------------------> External session flow
SUSPENDED --------(authorized process)-------------> appropriate permitted state
~~~

There is no `RESET_REQUIRED -> CURRENT` edge based solely on the client sending `"newPassword"`; **proof from a verified recovery flow** is mandatory. There is no `SUSPENDED -> CURRENT` edge just because a migration job succeeded.

### 3.1. Set Concrete Deadlines and Owners

Policy should specify:

- **Cutoff date for legacy decoder support**, with an accountable owner and rollback plan.
- **Which algorithms/costs are blocked immediately** due to high risk; which are allowed temporary login and rehash.
- **Notification window** to legitimate users; verified in-app/email channels, supportive wording, and anti-phishing link policy.
- **When a dormant account returns after the deadline**, route directly to recovery/reset without re-enabling weak decoders.
- **Milestones for deleting/quarantining weak hashes** and lawful backup/retention schedules; never keep them indefinitely "just in case".
- **Exception workflows** for service accounts, passwordless/no-email users, SSO-only users, or special legal cases.

Never scatter deadlines via `System.currentTimeMillis()` across layers: use managed/versioned policy, `Clock` for testing, and telemetry to verify enforcement.

## 4. Risk-Based Decision Rules

A policy can evaluate criteria such as:

1. **Verifiability:** is the legacy encoder supported, are salts/parameters intact, and is data uncorrupted?
2. **Scheme weakness:** is it plaintext/NoOp, fast MD5/SHA-1, PBKDF2 with too few iterations, low-cost bcrypt, or a homegrown format?
3. **Activity history:** last successful login, signs of credential stuffing, whether contact details are still usable.
4. **Account criticality:** admin, billing, access to PII/funds, or service accounts.
5. **Additional factors:** enrolled MFA/passkeys, recovery codes, trusted identity verification.
6. **Compatibility:** do all nodes support the new format, and could rollbacks render new hashes unreadable?
7. **Session/token lifecycle:** does the account hold active sessions or long-lived refresh tokens needing revocation after reset?

Example policy decision tree:

~~~text
Credential current and policy-compliant?
   |-- Yes -> CURRENT
   '-- No
        |
        +-- Trusted decoder, within deadline, risk allows?
        |      |-- Yes -> LEGACY_VERIFIABLE
        |      |          -> valid login -> rehash via CAS
        |      '-- No
        |
        +-- Verified recovery factor exists?
        |      |-- Yes -> RESET_REQUIRED -> recovery flow
        |      '-- No -> RECOVERY_HOLD, requires safe identity support
        |
        +-- IdP-only login account?
               -> EXTERNAL_ONLY, separate IdP policy
~~~

This is an **illustrative policy model**, not a built-in Spring Security authorization algorithm. You may need finer-grained reason states and manual review workflows for high-sensitivity accounts.

### 4.1. How Long Should Weak Decoders Be Kept?

Allowing legacy login and then rehashing has the UX benefit of not forcing immediate resets. However, if the decoder accepts an overly weak algorithm, was exposed in an incident, or is no longer trustworthy, an arbitrary "transition period" lets attackers keep using guessed passwords. In that case, **block legacy password logins and require recovery**. OWASP treats expiring/deleting hashes of long-inactive accounts and requiring resets as a valid strategy to purge weak hashes, despite the UX trade-off.

**Never equate product subscription lifetime with credential safety lifetime.** An account with active service access may still require an immediate password reset because its legacy authentication method is no longer acceptable.

## 5. Recovery/Reset for Accounts That Cannot Rehash Automatically

If no raw password can be verified by a trusted decoder, the proper path is **establishing a new credential after proving ownership**, not decrypting old hashes or letting an admin set a user's password without governance.

### 5.1. A Safe Reset Flow

~~~text
User submits recovery request
      |
      +--> Generic public response, never leak account existence
      +--> Throttle / anti-automation / rate limits
      |
      v
Generate random single-use challenge/token
      |
      +--> Send to REGISTERED and VERIFIED factor/channel
      +--> Store hashed token, short TTL, bound to account/action
      +--> Never use login or refresh tokens as reset tokens
      |
      v
User presents token/proof
      |
      +--> Verify TTL, signature/entropy if any, attempt count, one-time use
      +--> Check account state / MFA/step-up per risk policy
      |
      v
Accept NEW password meeting policy
      |
      +--> PasswordEncoder.encode(newPassword)
      +--> Transaction: CAS/version + transition state -> CURRENT
      +--> Consume challenge atomically, audit, invalidate cache
      +--> Revoke/rotate sessions and refresh tokens per policy
      +--> Send password-change notification
~~~

In real systems, recovery methods and step-up requirements depend on threat model, compliance rules, and account sensitivity. **Sending email to an unverified address is not sufficient proof of ownership.** Phone numbers or emails can be recycled, so privileged accounts may need stronger verification.

### 5.2. Non-Negotiable Safety Elements

- **Reset tokens must have high entropy, be unpredictable, short-lived, and single-use.** Never use guessable `username + timestamp` values or unmonitored long-lived tokens.
- **Hash reset tokens in storage** if they act as bearer secrets; avoid logging raw tokens or leaking them via analytics/Referer headers. Use constant-time/safe comparison and attempt limits.
- **Keep submission feedback generic without exposing account existence.** A message like "If a matching account exists, we will send instructions" is one option; still mind latency, response shape, and rate limits.
- **Verify the real `accountId`** and scope (tenant, realm, contact) before granting reset rights. Never let clients specify an arbitrary `accountId` with proof belonging to another account.
- **Separate password reset from post-login hash upgrades.** Reset verifies identity through an alternative factor rather than pretending the user supplied the old password.
- **Never mutate hashes in a failing transaction.** A reset code used twice must succeed at most once; block replays via transactions and unique/usedAt checks.
- **For accounts locked due to suspected compromise**, recovery must not automatically unlock them unless the investigation workflow permits it.

Never use predictable static security questions as a shortcut. Never email back old passwords; if an application can do that, its password storage design is fundamentally broken.

### 5.3. No Trusted Recovery Channel

`RECOVERY_HOLD` requires business and security decisions:

- Personal accounts may need extra identity verification or become unrecoverable if proof is lacking.
- Enterprise accounts may require a tenant admin to run a governed workflow, though **tenant admins must not automatically gain unrestricted power to take over any account**.
- Service accounts require rotation through a secret manager and authorized operators; they normally should not be forced into human email-based password resets.
- External-only accounts must return to their IdP or a verified identity-linking flow.
- Never "guess" that an old contact is valid or assign a new email without verification.

Document these decisions in a runbook featuring dual control for high-risk actions, role-restricted logging, and clear SLAs.

## 6. Integrating with Spring Security: Upgrading on Successful Authentication

Two APIs play distinct roles:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

This is a **condensed** signature, not a class to rewrite yourself. `matches` verifies the candidate password; `upgradeEncoding` merely signals that the encoded value should be regenerated under the encoder's policy. **It does not update the database automatically**.

Spring Security also provides `UserDetailsPasswordService`:

~~~java
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

Here `newPassword` per Spring Security's contract is **the password already encoded by `PasswordEncoder.encode(...)`**, not the raw password; the parameter name is easily misunderstood. Implementations update the persistent repository and return `UserDetails` with the new hash.

### 6.1. Configuring DaoAuthenticationProvider

With Spring Security 6.3.x, an illustrative integration:

~~~java
DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
provider.setUserDetailsService(userDetailsService);
provider.setPasswordEncoder(passwordEncoder);
provider.setUserDetailsPasswordService(userDetailsPasswordService);
~~~

This is a **Spring configuration snippet** requiring declared dependencies, imports, and beans. Newer Spring Security versions recommend the constructor taking `UserDetailsService`; check the Javadoc for your exact version. On successful login when the provider decides a hash upgrade is needed, it calls `userDetailsPasswordService.updatePassword(...)` if configured; this is **not an automatic mechanism for upgrading every type of account**.

To work properly, you need:

- `UserDetailsService` reading legacy hashes **in the right format** with `{id}` when using `DelegatingPasswordEncoder`.
- `PasswordEncoder` containing an appropriate decoder for legacy hashes and the new encoder for upgraded hashes.
- `UserDetailsPasswordService` actually persisting the new hash rather than mutating only an in-memory object.
- Account/credential state policy specifying which users are allowed legacy password login; `RESET_REQUIRED`/`EXTERNAL_ONLY` accounts must not slip through a weak fallback.
- Concurrency guards between reset and rehash plus cache invalidation so old hashes never overwrite new ones.

**Subtle point:** Spring Security does not know "block dormant users after date X", "recovery email unverified", "ambiguous imported credential", or "admin investigating account". All of those are custom policies that must run before or inside an appropriate authentication/recovery flow rather than relying solely on `upgradeEncoding`.

### 6.2. Preventing Overwriting Newer Passwords Under Concurrency

A repository-backed `UserDetailsPasswordService` should use `accountId`/version or the previously read old hash as optimistic update conditions:

~~~sql
UPDATE account_credentials
SET password_hash = :newEncodedHash,
    version = version + 1
WHERE account_id = :accountId
  AND version = :observedVersion
  AND password_hash = :observedEncodedHash
  AND migration_state IN ('LEGACY_VERIFIABLE', 'CURRENT');
~~~

This is **illustrative SQL with bind parameters** and an assumed schema; do not run it directly on databases missing those tables/columns. Check `affectedRows == 1` to confirm the change. If zero rows matched, a password reset, state change, or competing request won — **never blindly retry to overwrite**, and never grant authentication from a stale credential snapshot when policy requires re-verification.

Never use a mutable username as the CAS key when the application has a stable account ID. In standard `UserDetailsPasswordService`, the interface receives `UserDetails`; depending on your implementation, keep `accountId` and row version inside the principal or look up the mapping safely. Never treat `user.getUsername()` as absolute proof of `accountId` in multi-tenant models.

### 6.3. After Rehash, the Returned Record Must Reflect the New Credential

`updatePassword(user,newEncodedPassword)` returns the updated `UserDetails`. If the DB write succeeds yet you return the stale `user` holding the old hash, principals or caches can become inconsistent and hard to test. Use safe per-request DTOs/`UserDetails` so credential erasure does not mutate shared cached objects.

### 6.4. Never Try to "Fix" Accounts Lacking a Decoder via UserDetailsPasswordService

If `PasswordEncoder.matches(raw,stored)` cannot verify due to an unknown ID or corrupted format, **there is no successful authentication to qualify for an upgrade**. The state must move to `RESET_REQUIRED` or `RECOVERY_HOLD`. Do not add a `NoOpPasswordEncoder` fallback, do not treat unknown strings as plaintext, and never let users request a new hash update without proving ownership.

## 7. Runnable Java 17 Example: States That Cannot Upgrade Directly

This console example uses Spring Security Crypto to illustrate a minimal migration policy. It distinguishes:

- **`LEGACY_VERIFIABLE`:** can still verify old bcrypt; after right password, transitions to new hash via compare-and-set.
- **`RESET_REQUIRED`:** system rejects old password logins; routes to recovery.
- **`EXTERNAL_ONLY`:** no local password; uses IdP.
- **`SUSPENDED`:** blocks authentication even if the hash might match.
- **`ACTIVE`:** current hash valid, normal login.
- **Hash with unknown ID:** never guesses; quarantines state to `RESET_REQUIRED`.

For deterministic stdout, the program does not print raw passwords, salts, hashes, or UUIDs. The demo uses an in-memory store representing CAS **within a single JVM only**. Production apps must use database transactions/conditional updates and a real recovery verifier.

### 7.1. Gradle Project Structure

~~~text
credential-migration-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/CredentialMigrationDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'credential-migration-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto:6.3.8'
    implementation 'org.springframework.security:spring-security-core:6.3.8'
}

application {
    mainClass = 'example.CredentialMigrationDemo'
}
~~~

Requires JDK 17+ and a compatible Gradle version; on the first run Gradle downloads Spring Security dependencies from Maven Central. In real Spring Boot projects, Spring Security versions are normally managed by Boot's BOM rather than pinned directly as in this demo.

### 7.2. Complete Code

Create `src/main/java/example/CredentialMigrationDemo.java`:

~~~java
package example;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class CredentialMigrationDemo {

    enum State {
        LEGACY_VERIFIABLE, ACTIVE, RESET_REQUIRED,
        EXTERNAL_ONLY, SUSPENDED
    }

    record Credential(String encoded, State state, long version) {}

    static final class Store {
        // Represents atomic CAS within a single Java process only.
        private final ConcurrentMap<String, Credential> rows =
                new ConcurrentHashMap<>();

        Credential get(String username) {
            return rows.get(username);
        }

        void seed(String username, Credential credential) {
            rows.put(username, credential);
        }

        boolean replace(String username,
                        Credential observed, Credential replacement) {
            return rows.replace(username, observed, replacement);
        }
    }

    static String login(Store store, PasswordEncoder encoder,
                        String username, String rawPassword) {
        Credential observed = store.get(username);
        if (observed == null || rawPassword == null) {
            return "DENIED";
        }

        switch (observed.state()) {
            case RESET_REQUIRED:
                return "RECOVERY_REQUIRED";
            case EXTERNAL_ONLY:
                return "FEDERATED_LOGIN_REQUIRED";
            case SUSPENDED:
                return "DENIED";
            case LEGACY_VERIFIABLE:
            case ACTIVE:
                break;
            default:
                return "DENIED";
        }

        if (observed.encoded() == null) {
            return "RECOVERY_REQUIRED";
        }

        try {
            if (!encoder.matches(rawPassword, observed.encoded())) {
                return "DENIED";
            }

            if (!encoder.upgradeEncoding(observed.encoded())) {
                return "OK";
            }

            // Rehash ONLY the RAW PASSWORD that just matched successfully.
            String replacementHash = encoder.encode(rawPassword);
            Credential replacement = new Credential(
                    replacementHash, State.ACTIVE,
                    observed.version() + 1);

            // Raced with reset/password change? Never overwrite blindly.
            return store.replace(username, observed, replacement)
                    ? "OK_UPGRADED" : "RETRY_AUTH";
        } catch (IllegalArgumentException malformedOrUnknownHash) {
            // Demo: quarantine broken credential; never allow login.
            Credential quarantined = new Credential(
                    observed.encoded(), State.RESET_REQUIRED,
                    observed.version() + 1);
            store.replace(username, observed, quarantined);
            return "RECOVERY_REQUIRED";
        }
    }

    public static void main(String[] args) {
        String demoPassword = "Example!MigrationPass";
        BCryptPasswordEncoder oldBcrypt =
                new BCryptPasswordEncoder(10);
        BCryptPasswordEncoder currentBcrypt =
                new BCryptPasswordEncoder(12);

        Map<String, PasswordEncoder> known = Map.of(
                "bcrypt10", oldBcrypt,
                "bcrypt12", currentBcrypt);
        PasswordEncoder policy =
                new DelegatingPasswordEncoder("bcrypt12", known);

        Store store = new Store();
        store.seed("linh", new Credential(
                "{bcrypt10}" + oldBcrypt.encode(demoPassword),
                State.LEGACY_VERIFIABLE, 1));
        store.seed("hong", new Credential(
                null, State.RESET_REQUIRED, 1));
        store.seed("minh", new Credential(
                null, State.EXTERNAL_ONLY, 1));
        store.seed("khoa", new Credential(
                "{bcrypt10}" + oldBcrypt.encode(demoPassword),
                State.SUSPENDED, 1));
        store.seed("loi", new Credential(
                "{unknown}unverifiable",
                State.ACTIVE, 1));

        System.out.println("linh first -> "
                + login(store, policy, "linh", demoPassword));
        System.out.println("linh current hash -> "
                + store.get("linh").encoded().startsWith("{bcrypt12}"));
        System.out.println("linh second -> "
                + login(store, policy, "linh", demoPassword));
        System.out.println("linh wrong -> "
                + login(store, policy, "linh", "wrong-password"));

        System.out.println("hong -> "
                + login(store, policy, "hong", demoPassword));
        System.out.println("minh -> "
                + login(store, policy, "minh", demoPassword));
        System.out.println("khoa -> "
                + login(store, policy, "khoa", demoPassword));

        System.out.println("loi -> "
                + login(store, policy, "loi", demoPassword));
        System.out.println("loi quarantined -> "
                + (store.get("loi").state() == State.RESET_REQUIRED));
        System.out.println("absent -> "
                + login(store, policy, "absent", demoPassword));
    }
}
~~~

### 7.3. Running the Program and Stdout

With a compatible Gradle Wrapper in the project directory:

~~~bash
./gradlew run
~~~

If no wrapper is present but a compatible Gradle is installed locally, run `gradle run`. On Windows PowerShell with a wrapper, use `.\gradlew.bat run`.

Output lines printed by the program itself (ignoring Gradle logs):

~~~text
linh first -> OK_UPGRADED
linh current hash -> true
linh second -> OK
linh wrong -> DENIED
hong -> RECOVERY_REQUIRED
minh -> FEDERATED_LOGIN_REQUIRED
khoa -> DENIED
loi -> RECOVERY_REQUIRED
loi quarantined -> true
absent -> DENIED
~~~

Interpretation:

1. `linh` has a legacy hash mapped by ID `bcrypt10`. With the right password, `matches` succeeds; `upgradeEncoding` detects the old ID differs from `idForEncode="bcrypt12"`. The app runs `encode(rawPassword)` under the new policy and CAS transitions to `ACTIVE`.
2. `linh`'s next login uses the new hash, `matches` passes, and no further upgrade is needed.
3. `hong` is in `RESET_REQUIRED`, preventing old-password logins from bypassing recovery. The example has no real recovery service; it only **routes** without letting users self-"confirm recovery".
4. `minh` is external-only and must go to the IdP or a real federated login workflow.
5. `khoa` is suspended and must never be unlocked just for migration.
6. `loi` has ID `unknown`, so `DelegatingPasswordEncoder.matches` throws `IllegalArgumentException`. The demo transitions state via CAS to `RESET_REQUIRED` instead of treating unknown strings as plaintext or granting login.
7. `absent` is denied. Output prints distinct reasons **solely for studying internal logic**; public login endpoints should use uniform messages to curb account enumeration.

**Demo limitations:** `Store` only uses `ConcurrentHashMap`; it does not protect updates across multiple pods. In production, use `accountId` + DB transactions/versioning/CAS; state transitions and recovery proofs must be server-verified. The example issues no sessions/JWTs, implements no email reset, and does not handle UX or compromised accounts automatically. Cost 10 for legacy only simulates old data and is **not** advice to create new passwords at a low cost.

### 7.4. Extension Exercises

- Change `"bcrypt10"` to an ID absent from the map: that branch must fail login without a trusted decoder.
- Simulate a password-reset request bumping version while an old login computes its rehash: `store.replace(username,observed,replacement)` must return false; the code returns `RETRY_AUTH` and does not overwrite the reset hash.
- Add `lastLoginAt` and a migration deadline, then use `Clock.fixed` to test accounts past deadline automatically moving to `RESET_REQUIRED` per policy.
- Write a PostgreSQL integration test for `UPDATE ... WHERE version=? AND password_hash=?` confirming two transactions cannot overwrite the winning version.

## 8. Data Design and Database Migration

An illustrative PostgreSQL schema:

~~~sql
CREATE TABLE account_credentials (
    account_id       UUID PRIMARY KEY,
    password_hash    TEXT,
    migration_state  TEXT NOT NULL,
    hash_scheme_id   TEXT,
    hash_version     INTEGER,
    version          BIGINT NOT NULL DEFAULT 1,
    last_login_at    TIMESTAMPTZ,
    migrated_at      TIMESTAMPTZ,
    CONSTRAINT ck_credential_state
        CHECK (migration_state IN (
            'CURRENT', 'LEGACY_VERIFIABLE', 'RESET_REQUIRED',
            'RECOVERY_HOLD', 'EXTERNAL_ONLY', 'SUSPENDED'
        ))
);
~~~

This is a **simplified** schema. Real apps need foreign keys to accounts, multi-tenant scoping, constraints matching external-only and reset states, ownership/recovery factors, auditing, TTLs, and import provenance; `hash_scheme_id` should not be treated as the sole source of truth if `{id}` is already inside the hash.

### 8.1. Columns to Understand Clearly

- `password_hash` can be **NULL** for accounts lacking password login. Never auto-create default passwords because of this.
- `migration_state` describes **credential eligibility during transition**; it does not replace account `locked/disabled` status or resource permissions.
- `hash_scheme_id` is verified metadata only; if kept, it must stay synchronized with the actual prefix/format and never come from client input.
- `version` enables optimistic locking and prevents stale login requests from overwriting newly reset passwords.
- `last_login_at` must be updated inside trusted flows; never treat this timestamp as proof of account ownership.
- `migrated_at` supports auditing. Record events by `accountId` and policy version without logging hashes.

### 8.2. Batch Migrations Cannot "Rehash Everything"

A realistic plan:

1. Take encrypted backups and test restores per data governance rules.
2. Inventory account counts per scheme/state without exporting full password hashes into shared documents.
3. Mark `LEGACY_VERIFIABLE` for formats that the current encoder **has been verified** to check reliably.
4. Mark `RESET_REQUIRED` or `RECOVERY_HOLD` for formats that cannot or must no longer be verified.
5. Keep old-format reading capability on appropriate nodes during the approved migration window.
6. Let users log in validly and rehash via `PasswordEncoder`; support resets separately.
7. After the deadline, expire or purge weak hashes of dormant accounts per retention/risk policy.
8. Remove legacy decoders only when the DB and dependent systems no longer need them.
9. Audit older backups/exports/analytics copies still containing weak hashes and handle them per data protection schedules.

**Never automatically merge accounts or alter `accountId`** during password migration: identity is a separate layer tied to auditing, tenant membership, and permissions. Credential migration never grants ownership to someone matching a username/email in an old list.

### 8.3. Safe Inventory Query

~~~sql
SELECT migration_state, hash_scheme_id, count(*) AS accounts
FROM account_credentials
GROUP BY migration_state, hash_scheme_id
ORDER BY migration_state, hash_scheme_id;
~~~

This query aggregates by state and **outputs no hashes or passwords**. If you must inspect unprefixed hashes, check safe cohorts/samples only via privileged queries under data-minimization rules; avoid dashboards displaying per-account raw hashes.

### 8.4. Deleting Old Weak Hashes Must Follow Policy

For `RESET_REQUIRED`, choosing between keeping old hashes for rollback vs. deleting them early depends on security policy, incident status, recovery availability, and retention. If old hashes are very weak or leaked, leaving them in the DB for years still poses offline-cracking risk even with old logins blocked.

Perform data purging per policy while checking backups/replicas; never run `UPDATE password_hash=NULL` in bulk before confirming recovery flows actually work. If legal/forensic preservation applies, manage access and retention on documented grounds.

## 9. Coordinating Account State, Sessions, Tokens, and IdPs

### 9.1. Credential Reset Does Not Automatically Vanish Old Sessions

If a user is forced to reset their password due to an overly weak legacy hash, previously issued sessions/JWTs may stay active until expiration. Define explicit policies based on urgency:

| Case | Session/token handling options |
|---|---|
| Routine bcrypt cost bump, no suspected compromise | Sessions may stay per risk policy; new logins use new hash |
| Credential confirmed compromised | Revoke/invalidate related sessions and refresh tokens per policy |
| Account locked for fraud | Block existing requests too when required, not only new logins |
| Forced recovery for dormant account | May invalidate old sessions or require reauthentication per policy |
| External-only | Tokens/sessions managed by both IdP and RP; check revocation events and local account status |

With self-contained JWTs still having a valid `exp`, the backend will **not automatically know a credential was reset** without checking session version, token version, denylists, introspection, or account status per request. Never update only `migration_state` and claim all old sessions were revoked.

### 9.2. IdP Accounts Are Not Local-Password-Forgotten Accounts

With OIDC/SAML, a user may have an `(issuer, subject) -> accountId` mapping. Without a local password, never fabricate a fake hash just so `UserDetailsService` "has a password". Account/IdP linking, MFA, and resource authorization policies belong in the dedicated federated authentication path.

If migrating accounts from password login to IdP-only, verify subject linkage, plan cutover and rollback; never auto-link on unverified emails or leave password-login fallbacks enabled forever.

### 9.3. Service Accounts and API Keys

Machine-to-machine accounts may use client secrets, private keys, mTLS certificates, or API keys. `PasswordEncoder`/`UserDetailsPasswordService` for password logins does not cover the lifecycle of all these secrets. Rotation needs its own runbook: generate new credentials, test, distribute via secret manager, enforce a short controlled overlap, revoke old credentials, and audit.

Never force a service account into human email-based password reset when it lacks an appropriate human owner/verification channel.

## 10. Phased Rollout and Rollback

### 10.1. Safe Rollout Sequence

~~~text
Phase 0: Survey data, threat model, policy, recovery channels
Phase 1: Deploy new decoders/readers to all nodes, do not switch writers yet
Phase 2: Create state, telemetry, and tested recovery/force-reset flows
Phase 3: Switch encoder for NEW hashes, enable auto-upgrade on valid login
Phase 4: Monitor rehash %, login errors, support tickets, recovery completion
Phase 5: At deadline, block legacy verifiers / expire dormant credentials
Phase 6: Remove weak decoders, prune/delete weak hashes per retention, post-audit
~~~

Crucial point in Phase 1: **roll out reading before writing**. If node A starts storing `{argon2}...` while node B still runs a version lacking the Argon2 mapping, users can log in on A yet fail on B. When multiple backends/workers/portals read the same DB, every reader must be compatible before the write switch.

### 10.2. Rollbacks Must Not Reopen Old Vulnerabilities

If migration hits an incident, rolling back application versions can leave old nodes unable to read new hashes. Even then, never:

- Restore old weak hashes over strong new hashes as a rollback method.
- Enable `NoOpPasswordEncoder` system-wide to silence ID errors.
- Clear the `RESET_REQUIRED` flag on suspected-compromise accounts without review.
- Allow raw passwords or reset tokens in logs for debugging.
- Bulk-reset passwords to a shared value.

Prepare reader/writer compatibility, access-controlled feature flags, an isolated migration-state rollback path, and the ability to pause **rehash writes** without permitting out-of-policy logins.

### 10.3. Measure Success by State, Not Job Execution Counts

Metrics to monitor:

- Account/credential counts by `migration_state` and `hash_scheme_id`.
- Remaining legacy percentage by cohort, including dormant accounts.
- Successful logins with rehash, and CAS conflict counts.
- Reset requests issued, completed, rejected, and `RECOVERY_HOLD` cases.
- Login errors due to unmapped ID/format, separate from wrong passwords.
- Privileged accounts still holding legacy credentials.
- Latency and KDF resource cost after raising work factors.
- Support/complaint volume and password-spraying/attack signals.

Never put password hashes or raw reset tokens into metric labels, as doing so increases data-exposure risk. Telemetry can use protected/aggregated `accountId` values per policy, omitting usernames/emails when unnecessary.

## 11. Common Mistakes and Consequences

| Mistake | Consequence | Right approach |
|---|---|---|
| `encode(oldHash)` and overwrite | Original password can no longer log in | Encode only verified raw passwords or fresh resets |
| Thinking "a batch job can rehash every account" | No plaintext available; produces invalid hashes | Use login-time upgrades and dormant/reset policy |
| Prepending `{bcrypt}` to every unprefixed hash | Legacy formats get misread | Inventory and verify actual algorithms |
| Enabling `NoOpPasswordEncoder` fallback for unknown hashes | Risk of accepting plaintext | Block unknown formats; use verified recovery |
| Allowing old password logins past deadline | Keeps weak hashes/decoders alive indefinitely | Enforce expiration policy and mandatory resets |
| Forcing dormant accounts to use old password to request recovery | Fails users who forgot old passwords | Independent recovery with ownership verification |
| Using unverified email as reset factor | Account takeover risk | Require verified registered factors or escalated procedure |
| Reusable or long-lived reset tokens | Replay/account takeover risk | Short TTL, high entropy, atomic consumption |
| Granting login when encoder throws `IllegalArgumentException` | Format error turns into auth bypass | Fail closed, quarantine/log incident |
| Rehash writes DB without CAS | Can overwrite fresh password reset | Version/hash conditional update |
| Upgrader auto-unlocks suspended accounts | Bypasses investigation/authorization | Separate account status from migration state |
| Assuming new hash revokes old JWTs | Old sessions keep access | Revoke/use session version/introspection per risk |
| Switching to new ID before all nodes can read it | Intermittent login failures | Deploy new decoder to all readers first |
| Hardcoding policy per service | Nodes make inconsistent state decisions | Versioned, centralized, tested policy |
| Not tracking dormant accounts | Weak hashes linger un-upgraded for years | Track cohorts, deadlines, expire/delete or reset |
| Wrapping old hash inside new hash and treating as fully strong | Legacy weakness may still affect security | Vetted design only; avoid ad-hoc wrapping |
| Putting account hashes in troubleshooting logs | Increases offline cracking risk if logs leak | Use error codes, controlled IDs, aggregates |
| Letting admins set user passwords via weakly protected forms | Account takeover via support | Two-person/step-up approval, audit, recovery proof |

## 12. Required Test Suite

### 12.1. Unit/Integration Matrix

| Scenario | Expected result |
|---|---|
| Valid legacy hash + right raw | `matches` true; `upgradeEncoding` signals upgrade per policy |
| Valid legacy hash + wrong raw | No rehash, authentication denied |
| Unmapped legacy ID | Never falls back to NoOp/plaintext; fails closed |
| Truncated legacy hash / bad salt | Never treats raw as verified; routes to policy path |
| `CURRENT` account | Normal login, no needless rehashing |
| `RESET_REQUIRED` account | Old password login blocked; verified recovery only |
| `RECOVERY_HOLD` account | Never unlocked via reset token sent to unverified factor |
| `EXTERNAL_ONLY` account | Logs in via valid identity-linked provider; no local password created |
| `SUSPENDED` account | Never auto-unlocked by migration |
| Concurrent login and password reset | CAS prevents old rehash from overwriting post-reset hash |
| Two simultaneous logins upgrading same account | Only one update wins; the other handles consistently per policy |
| Reset token used twice | First succeeds, second is rejected |
| Expired reset token | Rejected, hash unchanged |
| Mismatched accountId/tenant mapping | Never resets/upgrades someone else's account |
| Bcrypt cost change | Encoder reads old cost, encodes new at target cost |
| Old node reading new hash | Verified before new writer is turned on |
| Legacy `{noop}` hash | Never retained/accepted in long-term production policy |
| Dormant account past deadline | Moves to `RESET_REQUIRED`, weak decoder unused |
| Password change from compromised session | Revoke/notify per policy; sessions/tokens handled separately |
| Increased KDF cost under heavy login load | Performance/rate limits prevent DoS |
| Public recovery endpoint | Responses avoid leaking account existence |
| Audit/logging | Never outputs raw passwords, hashes, or reset tokens |

### 12.2. Testing Time Boundaries and Rollouts

Use `Clock.fixed` in unit tests for deadlines: **before deadline** remains `LEGACY_VERIFIABLE` if policy permits, **at deadline** moves to `RESET_REQUIRED`, **after deadline** denies legacy password logins. Separate *migration deadline* from account/domain expiration, session expiration, JWT expiration, and recovery token TTL.

Use integration tests with a real database or production-like environment to verify transaction rollbacks, unique constraints, optimistic updates, and concurrent reset/rehash races. Never rely on random `Thread.sleep` calls to test concurrency races.

### 12.3. Self-Assessment Questions

**Question 1.** Can you take a cost 10 bcrypt hash and call `Argon2id.encode(hash)` to upgrade a user's password?  
**Answer:** Not via normal rehashing. The result is a hash of the bcrypt string, not a hash of the raw password the user remembers.

**Question 2.** Why can't an account that hasn't logged in for three years automatically upgrade its cost right away?  
**Answer:** The server has no verified raw password. You can allow login-time rehashing if a trusted decoder remains, or force a reset upon return per policy.

**Question 3.** A hash is missing its prefix, yet is definitely known to be bcrypt. Does it require an immediate reset?  
**Answer:** Not solely for missing the ID. You can run a metadata migration prepending `{bcrypt}` for the exact algorithm; bumping cost still requires verified raw passwords or a reset.

**Question 4.** A legacy hash has an unknown algorithm; a client sends a password and asks to write a new hash. Should you accept it?  
**Answer:** No. If you cannot verify the raw password against an old scheme, ownership must be proven through recovery first.

**Question 5.** Does `UserDetailsPasswordService.updatePassword` receive a raw password or an encoded one?  
**Answer:** Per Spring Security's contract, it receives **the `newPassword` already encoded by the encoder**, and the implementation updates the repository.

**Question 6.** If a login is rehashing while a password reset just committed, what should happen?  
**Answer:** CAS/version update must not overwrite. The login request using the stale credential must re-evaluate authentication per policy rather than saving or succeeding on a stale snapshot.

**Question 7.** A `SUSPENDED` account somehow passed rehash; should it be unlocked?  
**Answer:** No. Migration state has no authority to override account status, especially during suspected compromise.

**Question 8.** Once all code writes new hashes, can legacy encoders be removed immediately?  
**Answer:** Not yet. Verify which accounts still hold legacy hashes, which nodes still read them, dormant deadlines, and rollback compatibility.

**Question 9.** Are still-valid JWTs blocked automatically when an account is forced into `RESET_REQUIRED`?  
**Answer:** Not necessarily; implement session/token revocation or per-request checks matching security requirements.

## 13. Migration Policy Implementation Checklist

- [ ] Identify the true reason an account cannot upgrade directly: missing raw, no decoder, malformed format, dormant account, SSO-only, or locked account.
- [ ] Distinguish **ID metadata tagging** from **rehashing** and **resetting**; never substitute one for another.
- [ ] Build a state machine covering `CURRENT`, `LEGACY_VERIFIABLE`, `RESET_REQUIRED`, `RECOVERY_HOLD`, `EXTERNAL_ONLY`, and blocking states.
- [ ] Define deadlines, owners, risk exceptions, and weak-hash expiration/deletion policies.
- [ ] If allowing legacy login, upgrade only after `matches` succeeds on an actual raw password; never rehash old hashes.
- [ ] Use a `PasswordEncoder` that reads trusted legacy formats and writes strong new hashes; never use a NoOp fallback.
- [ ] If using `DaoAuthenticationProvider` auto-upgrade, configure `UserDetailsPasswordService` and test real DB updates.
- [ ] Scope by `accountId`/tenant with CAS/versioning/transactions to prevent races with resets.
- [ ] Provide a recovery/reset flow with identity verification, short-lived single-use tokens, rate limiting, and auditing.
- [ ] Verify recovery contacts/factors; never reset someone else's account via an unverified email.
- [ ] Keep suspended/locked/compromised policies independent; never unlock due to migration.
- [ ] Coordinate sessions, JWTs, refresh tokens, and IdPs per risk policy; never assume changing hashes revokes tokens.
- [ ] Deploy reader compatibility across all nodes before writers emit new hash formats.
- [ ] Monitor dormant cohorts, reset completions, rehash successes, CAS conflicts, and unmapped-ID errors.
- [ ] Keep raw passwords, hashes, reset tokens, and secret-manager values out of logs and metrics.
- [ ] Test deadlines, concurrency, recovery, multi-node setups, and rollbacks in production-like environments.
- [ ] Remove legacy decoders on schedule and purge weak hashes in DBs/backups per retention rules.

**Remember:** **Accounts that cannot be upgraded directly are never an excuse to drop security or invent default passwords.** When you have a **verified raw password**, rehash with the new encoder and update atomically; when you **cannot verify safely**, block legacy password logins and require **ownership-verified recovery/reset**. An effective policy must cover long-inactive accounts, SSO accounts, account states, active sessions, concurrency, and a path to retire weak algorithms.

### Official Documentation

- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): one-way password transformations, `DelegatingPasswordEncoder`, hash formats, and safe encoding plans.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): `UserDetailsService` and `PasswordEncoder` in username/password login.
- [Spring Security — UserDetailsPasswordService JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html): `updatePassword` receiving encoded passwords, updating repositories, and returning updated `UserDetails`.
- [Spring Security — DaoAuthenticationProvider JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): `setUserDetailsPasswordService` and password encoders.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): increasing work factors, upgrading legacy hashes on login, and strategies for resetting dormant accounts.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): recovery tokens, expiration, account enumeration, and safe resets.
- [NIST SP 800-63B (Rev. 4)](https://pages.nist.gov/800-63-4/sp800-63b.html): password verifier storage, recovery/authenticator lifecycle, and session management.
