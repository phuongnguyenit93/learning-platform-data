# Storing user entities, credentials, and managing multiple passkeys for one account

An application account can own **multiple passkeys**: for example, one passkey on a phone, one in a password manager, and one on a hardware security key. When implementing WebAuthn/Passkey login in Spring Security, the data problem is not merely "storing a public key," but **maintaining a stable link between the application account, the WebAuthn user entity, and each credential**, so you can sign in, list, label, revoke, and recover accounts without ever binding a passkey to the wrong person.

In Spring Security 6.5 (Servlet), the two primary repositories are:

- `PublicKeyCredentialUserEntityRepository`: stores the **WebAuthn user entity** of an account.
- `UserCredentialRepository`: stores **`CredentialRecord`** entries, where multiple records can link to **one user entity**.

This lesson explains the 1:N model, what data must/must not be stored, multi-passkey behavior, the default JDBC repositories, a **Java 17+ / Spring Boot 3.5 / Spring Security 6.5** example, and a passkey management API with ownership checks. Content applies to WebAuthn **Servlet**; when using Spring Security 7.x, check the dependencies/API for that exact branch, especially since the WebAuthn module is packaged differently.

## 1. Three objects that are easily confused

### 1.1. Application user — the business account

An account in the system may contain:

- `account_id`/durable internal ID (e.g., UUID);
- `username`, verified email, display name;
- active/locked status, tenant;
- roles/`GrantedAuthority` and profile data.

This account is usually managed by an `app_users` table and `UserDetailsService` or a separate identity service. It exists **independently** of login methods: the same account can have both a password and two passkeys.

**Do not confuse Spring Security's `UserDetails` with WebAuthn's `PublicKeyCredentialUserEntity`.** Both types have different responsibilities. `UserDetails` describes the user and authorities for authentication/authorization; the WebAuthn user entity is the identity object passed into credential creation.

### 1.2. `PublicKeyCredentialUserEntity` — user identity in WebAuthn

Under WebAuthn, a user entity has three basic properties:

| Property / Java API | Meaning | Storage rule |
| --- | --- | --- |
| `getId()` → `Bytes` | Opaque byte **user handle**, stable identifier of the account within the Relying Party (RP) | Cryptographically random, unique within the RP, max 64 bytes; do not rotate on every new passkey |
| `getName()` → `String` | Human-readable account name, e.g., `alice` | Do not treat as primary security key; may change per naming policy |
| `getDisplayName()` → `String` | Human-friendly label, e.g., "Alice Nguyen" | Used for UI, never used to verify ownership |

`PublicKeyCredentialUserEntityRepository` provides `findByUsername(String)`, `findById(Bytes)`, `save(PublicKeyCredentialUserEntity)`, and `delete(Bytes)`. For the same account, subsequent registrations should **reuse the existing user handle** rather than generating a new WebAuthn ID every time.

**Why not use email as the user handle?** Emails can change and expose personal information. WebAuthn specifies that handles must not directly identify users; use random bytes and keep a durable mapping between the handle and the account.

### 1.3. `CredentialRecord` — a single registered passkey

`CredentialRecord` represents **one public-key credential** verified during registration. One user entity can link to 0, 1, or N `CredentialRecord`s.

| Field / getter in Spring Security 6.5 | Purpose |
| --- | --- |
| `getCredentialId()` → `Bytes` | Credential identifier, used to look up the right public key and remove the exact record |
| `getUserEntityUserId()` → `Bytes` | Foreign key linking to the WebAuthn user entity's **user handle** |
| `getPublicKey()` | COSE-encoded public key used to verify signatures on subsequent logins |
| `getSignatureCount()` | Signature counter if supported by the authenticator, useful for anomaly detection |
| `getLabel()` | User-entered label to distinguish passkeys, e.g., "Backup security key" |
| `getCreated()` / `getLastUsed()` | Creation and last-used timestamps for display/administration |
| `getTransports()` | Transport hints advertised by the authenticator, not proof of device identity |
| `isBackupEligible()` / `isBackupState()` | Backup/sync eligibility and current backup status |
| `isUvInitialized()` | Indicates whether user verification has occurred during the credential's lifetime per recorded data |
| `getAttestationObject()` / `getAttestationClientDataJSON()` | Registration attestation data, optionally stored/evaluated per policy |

**Never store the passkey private key on the server.** The authenticator or passkey management platform keeps the private key; the server keeps the credential ID, public key, and metadata for verification. "The passkey is in the server database" means the **public credential record**, not a copy of the secret from the phone.

### 1.4. Relationship diagram

~~~text
Application Account: account_id = 7f42...             (business identity)
    │
    │ stable mapping: one account
    ▼
WebAuthn User Entity: id = opaque userHandle           (1)
    name        = "alice"
    displayName = "Alice"
    │
    │ getUserEntityUserId() = userEntity.getId()
    ├────────────── Credential Record A                (N)
    │                 credentialId = bytes-A
    │                 label = "Phone"
    │                 publicKey = COSE-A
    │                 created/lastUsed/signCount/BE/BS
    │
    ├────────────── Credential Record B
    │                 credentialId = bytes-B
    │                 label = "Backup security key"
    │                 publicKey = COSE-B
    │
    └────────────── Credential Record C
                      credentialId = bytes-C
                      label = "Passkey manager"
                      publicKey = COSE-C
~~~

**Critical invariants:**

1. An application `account_id` has **one** stable WebAuthn user handle per RP.
2. `credentialId` identifies **one credential**, not a user ID or a phone ID.
3. Every credential must point to the **right user handle**; never reassign a credential ID from user A to user B based on email or display name.
4. One user can have N credentials. Deleting one credential **does not delete the user entity** or other credentials.
5. A user handle must never be reused for someone else's account after an old account is deleted.
6. `label` is display metadata only; it does not determine ownership, signature validity, or role grants.

## 2. Multiple passkeys vs. synced passkeys

An account can register **multiple credential IDs** across multiple authenticators. However, a passkey in a password manager or device ecosystem can **sync across devices**. When synced, **the exact same credential** can appear on two devices while the RP still stores only **one `CredentialRecord`** because the credential ID and public key do not change.

| Scenario | Typical `CredentialRecord` count | Meaning |
| --- | --- | --- |
| First registration on phone | 1 | Creates credential A |
| Second registration on security key | 2 | Creates independent credential B |
| Third registration in passkey manager | 3 | Creates independent credential C |
| Passkey C syncs to laptop | **Still 3** | Does not necessarily create a new server credential |
| User renames credential B's label | Still 3 | Only updates label metadata |
| User revokes credential A on RP | Drops to 2 | Authenticating with A must be rejected by the server |
| User removes synced copy on one device | May stay 3 | Removing a local copy does not necessarily revoke the credential on the RP |

Therefore, **never use the device name as a primary key**. A user-entered name like "My iPhone" is metadata that can collide or become inaccurate after replacing a device. If you want to count how many devices hold a copy of a synced passkey, the server generally **lacks sufficient evidence** to infer it from the `CredentialRecord` count.

`backupEligible` (BE) indicates capability for backup/sync, and `backupState` (BS) indicates the reported backup state. These are supplementary signals, **not** exact proof of "how many machines currently hold the credential." For synced passkeys, `signatureCount` may be 0 or fail to increment monotonically across devices; do not automatically lock accounts solely because the counter fails to increment—apply a policy based on authenticator type and validator results.

## 3. Data schema: map accurately, do not reinvent Spring's schema

### 3.1. Logical system model

Below is a **conceptual relational model**, **not the official DDL of `Jdbc*Repository`**:

~~~text
APPLICATION_USER
  account_id       PK
  username         UNIQUE
  email_verified
  enabled
      │ 1
      ▼ 1
WEBAUTHN_USER_ENTITY
  user_handle      PK, UNIQUE, opaque bytes
  account_id       UNIQUE -> APPLICATION_USER
  name
  display_name
      │ 1
      ▼ N
WEBAUTHN_CREDENTIAL
  credential_id    PK, opaque bytes
  user_handle      FK -> WEBAUTHN_USER_ENTITY
  public_key_cose
  signature_count
  label
  created_at, last_used_at
  backup_eligible, backup_state, transports, ...
~~~

A production database must enforce:

- `credential_id` **UNIQUE** across the entire RP system.
- `user_handle` **UNIQUE** per user entity, mapping to the exact stable `account_id`.
- Each credential stores the user handle verified during registration, with foreign keys or equivalent integrity checks.
- Labels do not need to be UNIQUE and must never be the authentication lookup key.
- Public key bytes, credential IDs, and handles must be stored in binary/base64url using consistent encoding rules; never turn raw bytes into Java `String`s using the default charset.

In multi-tenant applications, design namespaces cleanly: an RP has a specific `rpId`, and account identity may need a composite tenant+account ID. Never reuse user handles across tenants/accounts just because emails match.

### 3.2. Spring Security 6.5 includes JDBC repositories

Spring Security 6.4 introduced WebAuthn/Passkeys into the framework with **in-memory** repositories. Spring Security **6.5 adds JDBC implementations**:

- `JdbcPublicKeyCredentialUserEntityRepository`;
- `JdbcUserCredentialRepository`.

Javadoc specifies the tables must be created from these resources:

~~~text
classpath:org/springframework/security/user-entities-schema.sql
classpath:org/springframework/security/user-credentials-schema.sql
~~~

These are the **actual schemas expected by the default JDBC classes**. Do not take the conceptual tables in section 3.1, create them yourself, and expect `JdbcUserCredentialRepository`'s SQL statements to match automatically. To change table names or structure, write a custom repository implementation or customize SQL via version-supported APIs.

The two repositories store different things:

| Repository | Responsibility |
| --- | --- |
| `PublicKeyCredentialUserEntityRepository` | `findByUsername`, `findById`, `save`, `delete` user entities |
| `UserCredentialRepository` | `findByCredentialId`, `findByUserId`, `save`, `delete` credentials |
| Application's `UserDetailsService` | Maps username to user, account status, and business authorities |

**Do not confuse `JdbcUserDetailsManager`'s user schema** with the two WebAuthn schemas above. Using JDBC WebAuthn **does not automatically move** your application's users/passwords/roles to JDBC; they are independent storage concerns.

### 3.3. Default in-memory for testing, JDBC for shared state

| Option | Strengths | Limitations |
| --- | --- | --- |
| `MapPublicKeyCredentialUserEntityRepository` and `MapUserCredentialRepository` | Simple, suited for samples/tests | Not durable across restarts and not shared across nodes |
| `JdbcPublicKeyCredentialUserEntityRepository` and `JdbcUserCredentialRepository` | Shared across multiple instances via the same database | Requires schema/migrations, transactions, backups, availability, access controls |
| Custom repositories | Integrates with existing user/credential models | Must preserve Spring contracts, atomicity, uniqueness, ACLs, concurrent updates |

If the server runs 3 replicas and each holds its own in-memory repository, registration hitting node A followed by login hitting node B may fail to find the credential. Sticky sessions are neither the only nor a sufficient fix; you need **shared credential persistence** and proper challenge/session configuration.

### 3.4. Rule to avoid losing the handle when renaming a username

Suppose user `alice` changes her username to `alice.new`. **Do not create a new user handle and abandon old credentials.** The change should be coordinated in a transactional workflow:

1. Verify the authenticated account and permission to change username.
2. Update display/business username per policy.
3. Update the `username → WebAuthn user entity` mapping while **keeping `userEntity.getId()` unchanged**.
4. Ensure all `CredentialRecord`s still reference the exact same handle.
5. Verify login with all previously registered passkeys.
6. If username is used as a key in the repository, avoid transient states where both old and new names exist, causing collisions or identity leakage.

Verify the exact semantics of `save` and `delete` when implementing custom repositories or running migrations; never assume a JDBC backend's `save` automatically cascades updates across every application user/tenant table.

## 4. Registration flow must keep the user entity stable

### 4.1. Registering the first passkey

~~~text
User alice logged in via a secure bootstrap method
           │
           ▼
POST /webauthn/register/options + CSRF
           │
           ▼
Spring WebAuthn: load/initialize alice's user entity
   userHandle = opaque bytes U (kept stable)
   challenge and rpId/origin policy
           │
           ▼
Browser navigator.credentials.create(options)
           │ authenticator creates key pair
           │ private key stays on authenticator; public key goes to server
           ▼
POST /webauthn/register + CSRF
           │
           ▼
Spring verifies challenge, origin, rpId, attestation/policy
           │
           ▼
UserCredentialRepository.save(CredentialRecord A)
   credentialId = A
   userEntityUserId = U
   publicKey = publicKeyA
           │
           ▼
Management page displays: "Passkey A"
~~~

Per Spring Security 6.5 Servlet docs, registration consists of **`POST /webauthn/register/options`** to fetch options, followed by **`POST /webauthn/register`** to complete registration. POST requests require valid **CSRF tokens** when CSRF is enabled. The framework filters/libraries are responsible for validating WebAuthn data; never blindly trust JavaScript-submitted payloads just because the UI succeeded.

### 4.2. Registering a second passkey

When alice registers with another security key:

- `PublicKeyCredentialUserEntityRepository.findByUsername("alice")` must return the **same user handle U**.
- The authenticator generates a distinct **credentialId B** and `publicKeyB`.
- `UserCredentialRepository.save(B)` saves an additional record: `B.userEntityUserId == U`.
- **Do not** overwrite record A with B; **do not** delete A when the user registers B.
- When generating options for the new credential, `excludeCredentials` can list already-registered IDs to discourage duplicate registration on the same authenticator; never construct this list from unverified client input.

Spring's generation/registration operations must guarantee the **acting user** is the target account, especially if the app exposes an endpoint to "add a passkey for user X." Never take an arbitrary user ID from the request body and bind a new credential to someone else; use the current authenticated principal and apply re-authentication/step-up policies as needed.

### 4.3. Authentication with any one of the passkeys

~~~text
Login: POST /webauthn/authenticate/options + CSRF
      ↓ unique challenge / RP ID
Browser navigator.credentials.get(options)
      ↓ select any available credential A or B
POST /login/webauthn + assertion
      ↓ look up credentialId (A or B)
UserCredentialRepository.findByCredentialId(...)
      ↓ publicKeyA/publicKeyB + userHandle U
Relying Party verifies signature, challenge, origin, rpIdHash,
UP/UV, and policy requirements
      ↓ resolve U → alice
Spring Authentication + application authorities
      ↓
Authenticated session
~~~

Having two passkeys on an account does not mean **both must be used simultaneously**. In the standard design, one valid assertion from **any non-revoked credential** belonging to alice suffices to authenticate alice's account. Specific assurance levels or step-up policies may impose extra conditions.

## 5. Spring Boot 3.5 + Spring Security 6.5 example (Servlet, JDBC)

This example provides a **WebAuthn + JDBC user entity/credential** configuration along with a passkey management endpoint. The Java code uses package `example.passkeys`; place the files with exact names/packages into a Spring Boot 3.5 project on Java 17+. **No server-side private keys or real credentials** are pre-created; to test registration/authentication, use a WebAuthn-capable browser and an authenticator.

**Prerequisites:** JDK 17+, Spring Security **6.5.x**, Spring Boot 3.5.x, HTTPS in production. The local demo uses `localhost` and in-memory H2; H2 only demonstrates the JDBC repositories and is **not production persistence**.

### 5.1. Gradle dependencies

In the project's `build.gradle` with the Spring Boot plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    // Per Spring Security 6.5 Servlet docs:
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'

    runtimeOnly 'com.h2database:h2'  // Only for local lab.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-security` pulls in `spring-security-web` for servlet apps; `webauthn4j-core` is required by 6.5 docs as shown above. **Do not copy these exact dependencies into Spring Security 7.x**: the 7.x docs describe the `spring-security-webauthn` module and different dependencies. For each branch, use the matching BOM and docs.

### 5.2. DataSource and schema initialization for the lab

File `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.datasource.url=jdbc:h2:mem:passkey_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:org/springframework/security/user-entities-schema.sql,classpath:org/springframework/security/user-credentials-schema.sql
~~~

With the right dependencies and SQL resources present in that version, Spring Boot runs the initialization scripts on the lab H2 database. If a script/schema is incompatible with your target database, **do not drop the schema or swallow errors**; inspect the SQL and implement matching Flyway/Liquibase migrations for PostgreSQL/MySQL/production.

Notes:

- The two resources above belong to Spring Security's **user entity/credential** storage; they do not create application user tables with passwords/roles.
- H2 `mem` loses data when the application stops; to verify persistence across restarts, use a durable database and keep the schema intact.
- Production should not run DDL table creation on every startup; manage schemas via versioned migrations, backups/restores, least-privilege DB accounts, and access controls.

### 5.3. Security and JDBC repository beans

File `src/main/java/example/passkeys/PasskeyApplication.java`:

~~~java
package example.passkeys;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasskeyApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasskeyApplication.class, args);
    }
}
~~~

File `src/main/java/example/passkeys/PasskeySecurityConfig.java`:

~~~java
package example.passkeys;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.webauthn.management.JdbcPublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management.JdbcUserCredentialRepository;

@Configuration(proxyBeanMethods = false)
public class PasskeySecurityConfig {

    @Bean
    JdbcPublicKeyCredentialUserEntityRepository webAuthnUsers(
            JdbcOperations jdbc) {
        return new JdbcPublicKeyCredentialUserEntityRepository(jdbc);
    }

    @Bean
    JdbcUserCredentialRepository webAuthnCredentials(JdbcOperations jdbc) {
        return new JdbcUserCredentialRepository(jdbc);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService applicationUsers(PasswordEncoder passwordEncoder) {
        // Demo: bootstrap password strictly for local environments.
        // Production: replace with account database / identity provider.
        UserDetails student = User.withUsername("student")
                .password(passwordEncoder.encode("local-demo-change-me"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(student);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/settings/passkeys/**").authenticated()
                .anyRequest().authenticated());

        http.formLogin(Customizer.withDefaults());

        // Localhost is supported by browsers as a special secure context.
        // Production: rpId("example.com")
        //             .allowedOrigins("https://app.example.com")
        http.webAuthn(webAuthn -> webAuthn
                .rpId("localhost")
                .allowedOrigins("http://localhost:8080"));

        // Do not disable CSRF; WebAuthn registration/authentication uses POST.
        return http.build();
    }
}
~~~

**Why do we need both `UserDetailsService` and the two WebAuthn repositories?**

`UserDetailsService` in the example provides the `student` account to bootstrap via form login along with `ROLE_USER`. `JdbcPublicKeyCredentialUserEntityRepository` stores WebAuthn user handles; `JdbcUserCredentialRepository` stores credential public keys. These two JDBC beans **do not** replace the business account store. Sharing the same `username` for mapping is an agreement between the two sides that must stay consistent.

**Version warning:** the two JDBC classes above are **`Since 6.5`** APIs. If you are on Spring Security 6.4, passkeys exist, yet these JDBC classes do not. On WebFlux, do not copy Servlet `HttpSecurity`/`SecurityFilterChain` directly.

## 6. API to list and revoke registered passkeys

After logging in, users need a screen like:

| Passkey name | Created | Last used | Status | Action |
| --- | --- | --- | --- | --- |
| Phone | 2026-08-01 | 2026-11-01 | Syncable | Remove |
| Backup security key | 2026-09-15 | 2026-10-20 | Device-bound | Remove |
| Passkey manager | 2026-10-02 | 2026-11-05 | Synced | Remove |

This table shows **illustrative data**. Labels and backup capability do not prove where a specific physical device resides. Never allow another user to list this account's passkeys; never return raw public keys/attestations when the UI only needs names and dates.

### 6.1. Management principles

1. Get the **username from the authenticated `Authentication`**, never from an arbitrary `userId` in the query/body.
2. Look up the current user entity via `findByUsername` and obtain `userEntity.getId()`.
3. List via `findByUserId(userEntity.getId())`; never query all passkeys and filter on the client.
4. When removing, look up the record by `credentialId` and verify `record.getUserEntityUserId().equals(userEntity.getId())` **before** calling `delete`.
5. Do not remove the last passkey if the system has no alternative login/recovery path; the demo below enforces a policy blocking removal of the last credential.
6. Removal is a sensitive action: production should require **recent authentication/step-up**, preserve CSRF, and audit (without logging raw credential IDs).
7. Under concurrent requests, production requires DB-appropriate atomic ownership/revocation; checking-then-deleting across two separate statements can race under concurrent updates.

### 6.2. Java 17+ controller with ownership check

File `src/main/java/example/passkeys/PasskeyManagementController.java`:

~~~java
package example.passkeys;

import java.time.Instant;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.webauthn.api.Bytes;
import org.springframework.security.web.webauthn.api.CredentialRecord;
import org.springframework.security.web.webauthn.api.PublicKeyCredentialUserEntity;
import org.springframework.security.web.webauthn.management.PublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management.UserCredentialRepository;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/settings/passkeys")
public class PasskeyManagementController {

    private final PublicKeyCredentialUserEntityRepository users;
    private final UserCredentialRepository credentials;

    public PasskeyManagementController(
            PublicKeyCredentialUserEntityRepository users,
            UserCredentialRepository credentials) {
        this.users = users;
        this.credentials = credentials;
    }

    @GetMapping
    public List<PasskeySummary> list(Authentication authentication) {
        PublicKeyCredentialUserEntity owner =
                users.findByUsername(authentication.getName());

        if (owner == null) {
            return List.of();
        }

        return credentials.findByUserId(owner.getId())
                .stream()
                .map(record -> new PasskeySummary(
                        record.getCredentialId().toBase64UrlString(),
                        record.getLabel(),
                        record.getCreated(),
                        record.getLastUsed(),
                        record.isBackupEligible(),
                        record.isBackupState()))
                .toList();
    }

    @DeleteMapping("/{credentialId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(
            @PathVariable String credentialId,
            Authentication authentication) {

        Bytes id;
        try {
            id = Bytes.fromBase64(credentialId);
        } catch (IllegalArgumentException invalidId) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        if (id == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        PublicKeyCredentialUserEntity owner =
                users.findByUsername(authentication.getName());
        if (owner == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        CredentialRecord record = credentials.findByCredentialId(id);
        if (record == null
                || !owner.getId().equals(record.getUserEntityUserId())) {
            // Same response for "does not exist" and "not owned by account".
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        // Demo policy: always keep at least one passkey.
        // Production should consider dedicated recovery/password options.
        if (credentials.findByUserId(owner.getId()).size() <= 1) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "Cannot remove the last passkey in this demo");
        }

        credentials.delete(id);
    }

    public record PasskeySummary(
            String credentialId,
            String label,
            Instant created,
            Instant lastUsed,
            boolean backupEligible,
            boolean backupState) {
    }
}
~~~

**APIs used and available in Spring Security 6.5:**

- `PublicKeyCredentialUserEntityRepository.findByUsername(String)` and `getId()`;
- `UserCredentialRepository.findByUserId(Bytes)`, `findByCredentialId(Bytes)`, `delete(Bytes)`;
- `CredentialRecord.getUserEntityUserId()`, `getLabel()`, `getCreated()`, `getLastUsed()`, `isBackupEligible()`, `isBackupState()`;
- `Bytes.fromBase64(String)` and `toBase64UrlString()`.

`PasskeySummary` is a Java `record` (supported since Java 16, works on Java 17), exposing only metadata. User tokens, public keys, raw assertions, and attestations are **never** returned in the list.

**Demo limitations:** even with the ownership check, this controller is not a complete production management feature: it lacks re-authentication before removal, auditing, rate limiting, locking/atomic SQL deletion on `credential_id + user_handle`, and verification that the user retains an independent recovery channel. Additionally, URL paths containing raw credential IDs may appear in access logs; production should mask or use surrogate IDs if needed.

### 6.3. Specifics of version 6.5.10 and later

Spring Security 6.5.10 provides `CredentialRecordOwnerAuthorizationManager` in package `org.springframework.security.web.webauthn.management`, implementing `AuthorizationManager<Bytes>` to assist with credential ownership checks. It is a defense-in-depth option when designing management endpoints.

**Never substitute credential ID "unguessability" for ownership checks.** Credential IDs are highly random, yet can leak via logs, analytics, request histories, or compromised accounts. Deleting a passkey is a sensitive state mutation and must verify that **the logged-in user owns that credential**. In the example above, the check is performed explicitly before deletion; on versions supporting the authorization manager, you can integrate it as a dedicated rule per your architecture.

### 6.4. API responses and CSRF

Example after alice has two passkeys:

~~~http
GET /settings/passkeys HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=<lab-session>
~~~

**Illustrative** JSON body; real IDs are Base64URL-encoded credential bytes, not device-name strings:

~~~json
[
  {
    "credentialId": "AQIDBAUGBwgJCgsMDQ4PEA",
    "label": "Phone",
    "created": "2026-10-01T00:00:00Z",
    "lastUsed": "2026-11-05T08:30:00Z",
    "backupEligible": true,
    "backupState": true
  },
  {
    "credentialId": "EA8ODQwLCgkIBwYFBAMCAQ",
    "label": "Backup security key",
    "created": "2026-10-03T00:00:00Z",
    "lastUsed": "2026-10-20T08:00:00Z",
    "backupEligible": false,
    "backupState": false
  }
]
~~~

A delete request requires an authenticated session and a CSRF token when CSRF is enabled:

~~~http
DELETE /settings/passkeys/AQIDBAUGBwgJCgsMDQ4PEA HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=<lab-session>
X-CSRF-TOKEN: <csrf-token-from-app>
~~~

If the credential belongs to the current account and the user still has at least one other credential, the controller returns **204 No Content**. If the credential does not exist or does not belong to the logged-in user, it returns 404; if it is the last credential under the demo policy, it returns 409 Conflict. Ownership checks must always be enforced on the server—never rely on the UI only showing the user's own delete buttons.

### 6.5. Updating metadata without breaking the credential

The app can let users **rename labels** or add notes to passkeys:

- Validate label length/characters and prevent XSS when rendering HTML—disallow unsanitized markup/scripts.
- Renaming a label **must not alter** `credentialId`, `userEntityUserId`, `publicKey`, or `signatureCount`.
- With Spring Security 6.5, `ImmutableCredentialRecord.fromCredentialRecord(record)` creates a builder from an existing record; the builder exposes `label(String)` and `build()`. Then persist via `UserCredentialRepository.save(...)` per the active implementation's semantics.
- Verify ownership and atomic update mechanics before writing. Do not accidentally clobber concurrent `lastUsed` or `signatureCount` updates from another login.
- Never use a client-supplied label as the sole selector for a delete statement.

Java snippet **illustrated inside a service that already holds `record` and the repository, not a standalone program**:

~~~java
CredentialRecord renamed =
        ImmutableCredentialRecord.fromCredentialRecord(record)
                .label("Backup security key")
                .build();

credentials.save(renamed);
~~~

Add imports from `org.springframework.security.web.webauthn.api.ImmutableCredentialRecord`. When using this snippet in practice, **first** look up the record, verify ownership against the current user, validate the rename request, and handle concurrency. Without this check, a rename endpoint taking a guessable credential ID becomes an IDOR vulnerability.

## 7. Running the demo and testing in the browser

### 7.1. Setup

1. Use a Spring Boot 3.5/JDK 17 Gradle project and add the files from sections 5 and 6.
2. Run `./gradlew bootRun` (Windows: `gradlew.bat bootRun`).
3. Open a WebAuthn/passkey-capable browser at `http://localhost:8080`. `localhost` is a browser-supported secure context exception; on any arbitrary hostname/IP, real HTTPS with matching RP ID and origin is required.
4. Visit `/login` and sign in as the demo account **student** with the local-only demo password (`local-demo-change-me`).
5. Once logged in, use the framework's default WebAuthn registration page at `/webauthn/register` (or your app's management UI) to register a passkey; the browser should show an authenticator/platform prompt.
6. Register a second time using a **different authenticator**. For the same account, you will have at least two credential records once the second credential creation succeeds.
7. Call `GET /settings/passkeys` inside the authenticated browser session and verify two distinct records sharing the same owner.
8. Remove one credential via UI sending `DELETE` + CSRF; one credential remains in the list. Log out and try signing in with the removed credential: it must fail; the remaining credential must still sign in.

**Do not manually craft fake JSON and `POST /webauthn/register` to "create a passkey."** Registration requires `navigator.credentials.create` from the WebAuthn API and a valid response with attestation/challenge; signatures cannot be faked with a plain JSON file.

### 7.2. Key observations

- `GET /settings/passkeys` does not establish authentication; it returns the list for the already-authenticated user.
- `POST /webauthn/register/options` creates a registration challenge stored for matching per the configured repository/session mode. By default, part of this state resides in HTTP session; clusters require session/challenge consistency.
- `POST /webauthn/register` is accepted only when the client response is valid, origin/rpId match, and the logged-in user is authorized to register.
- `POST /webauthn/authenticate/options` creates an authentication challenge; `POST /login/webauthn` verifies the assertion using the stored public key.
- Removing a passkey on the server **does not force the authenticator or sync ecosystem to delete the private key**. The browser may still offer the old passkey in its picker, yet the server no longer has a credential record to verify it.
- If the server restarts in the lab using H2 `mem`, all demo credential records are lost; this does not mean passkeys lack persistence support, only that we chose an in-memory database.

## 8. Testing ownership and multiple credentials

### 8.1. JUnit controller tests without a browser

JUnit 5/Mockito example in a project with `spring-boot-starter-test`. The test mocks repositories to isolate the ownership check. It **does not prove WebAuthn signature/challenge verification**—that requires integration/e2e tests.

File `src/test/java/example/passkeys/PasskeyManagementControllerTest.java`:

~~~java
package example.passkeys;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.web.webauthn.api.Bytes;
import org.springframework.security.web.webauthn.api.CredentialRecord;
import org.springframework.security.web.webauthn.api.PublicKeyCredentialUserEntity;
import org.springframework.security.web.webauthn.management.PublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management.UserCredentialRepository;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class PasskeyManagementControllerTest {

    @Test
    void oneUserCanListTwoCredentials() {
        PublicKeyCredentialUserEntityRepository users =
                mock(PublicKeyCredentialUserEntityRepository.class);
        UserCredentialRepository credentials =
                mock(UserCredentialRepository.class);

        Bytes userHandle = Bytes.random();
        Bytes credentialA = Bytes.random();
        Bytes credentialB = Bytes.random();

        PublicKeyCredentialUserEntity owner =
                mock(PublicKeyCredentialUserEntity.class);
        when(users.findByUsername("student")).thenReturn(owner);
        when(owner.getId()).thenReturn(userHandle);

        CredentialRecord a = mock(CredentialRecord.class);
        when(a.getCredentialId()).thenReturn(credentialA);
        when(a.getLabel()).thenReturn("Phone");
        when(a.getCreated()).thenReturn(Instant.parse("2026-10-01T00:00:00Z"));

        CredentialRecord b = mock(CredentialRecord.class);
        when(b.getCredentialId()).thenReturn(credentialB);
        when(b.getLabel()).thenReturn("Backup key");
        when(b.getCreated()).thenReturn(Instant.parse("2026-10-02T00:00:00Z"));

        when(credentials.findByUserId(userHandle))
                .thenReturn(List.of(a, b));

        PasskeyManagementController controller =
                new PasskeyManagementController(users, credentials);

        var auth = new TestingAuthenticationToken("student", "unused");
        var result = controller.list(auth);

        assertEquals(2, result.size());
        assertEquals("Phone", result.get(0).label());
        assertEquals("Backup key", result.get(1).label());
    }

    @Test
    void cannotDeleteCredentialOwnedByAnotherUser() {
        PublicKeyCredentialUserEntityRepository users =
                mock(PublicKeyCredentialUserEntityRepository.class);
        UserCredentialRepository credentials =
                mock(UserCredentialRepository.class);

        Bytes currentUserId = Bytes.random();
        Bytes otherUserId = Bytes.random();
        Bytes credentialId = Bytes.random();

        PublicKeyCredentialUserEntity currentUser =
                mock(PublicKeyCredentialUserEntity.class);
        when(users.findByUsername("student")).thenReturn(currentUser);
        when(currentUser.getId()).thenReturn(currentUserId);

        CredentialRecord someoneElsesPasskey =
                mock(CredentialRecord.class);
        when(someoneElsesPasskey.getUserEntityUserId())
                .thenReturn(otherUserId);
        when(credentials.findByCredentialId(credentialId))
                .thenReturn(someoneElsesPasskey);

        PasskeyManagementController controller =
                new PasskeyManagementController(users, credentials);
        var auth = new TestingAuthenticationToken("student", "unused");

        assertThrows(ResponseStatusException.class, () ->
                controller.delete(
                        credentialId.toBase64UrlString(), auth));

        verify(credentials, never()).delete(any(Bytes.class));
    }
}
~~~

Run in the Gradle project:

~~~bash
./gradlew test --tests example.passkeys.PasskeyManagementControllerTest
~~~

Expected result: both tests pass if configuration/controller code is right; Gradle may print `BUILD SUCCESSFUL`, though exact log output depends on the Gradle version and CI setup. The tests verify: (1) one user handle can query two credentials; (2) a user cannot delete a credential belonging to another owner. They do **not** test HTTP/CSRF, recent-login, SQL transactions, real WebAuthn cryptography, or browser origins.

### 8.2. Functional/security test matrix

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| P01 | User A registers credential A1 | User entity A exists and A1 points to A's handle |
| P02 | Same user A registers A2 | A1 still exists; A2 has a distinct credential ID; both point to A's handle |
| P03 | User B registers B1 | B's handle differs from A's; A cannot see B1 |
| P04 | Sign in with A1 | Authenticates account A, not account B |
| P05 | Sign in with A2 | Still authenticates account A |
| P06 | A's list API | Returns only A's credentials |
| P07 | A tries to delete B1 using leaked ID | Rejected; B's data unchanged |
| P08 | A deletes A1 while still having A2 | A1 can no longer sign in; A2 still works |
| P09 | A deletes last credential | Applies 409/recovery policy; avoids self-lockout |
| P10 | Add passkey then edit label | Only label changes; `credentialId`/publicKey/`userHandle` stay intact |
| P11 | Two passkeys with duplicate labels | No ambiguity since all operations use credential ID |
| P12 | Change username/displayName | Handle stays stable; A1/A2 keep working after migration |
| P13 | Submit fake/non-existent credential ID | 404/blocked, never queries/deletes another user's data |
| P14 | Registration missing CSRF or unauthenticated | Blocked |
| P15 | Delete credential missing CSRF in browser session | Blocked |
| P16 | Login assertion with wrong challenge/origin/rpId | Authentication fails |
| P17 | Login assertion with invalid signature | Authentication fails, no valid `SecurityContext` created |
| P18 | Registration with duplicate credential ID | Never creates ambiguous duplicate records; unique constraint enforced |
| P19 | Two nodes running, shared DB | Credential registered on node A works on node B with proper session/challenge setup |
| P20 | Restart with durable DB | Credentials and user handles persist, no re-registration needed |
| P21 | Backup state changes | UI/metadata updated per validator, not misclassified as a new device |
| P22 | Two concurrent last-credential DELETEs | Production never deletes all methods when policy protects the last credential |
| P23 | Lost device holding a synced passkey | Enforce policy to revoke the full credential and re-register, not merely remove one copy |
| P24 | User account locked/deleted | Can no longer sign in; remove credentials via audited/retention-compliant workflow |
| P25 | No passkeys after bootstrap | Password/recovery login (if permitted) still follows policy, no `NullPointerException` |

**Do not infer WebAuthn security from mocked repository tests.** Tests must include browser + authenticator integration or valid WebAuthn fixtures, negative rejection paths, and recovery policies.

## 9. Deleting credentials, deleting users, and account recovery

### 9.1. Deleting a single credential

Deleting via `UserCredentialRepository.delete(credentialId)` after ownership verification leaves the server **without the corresponding public key** to verify that credential. The user's other credentials are untouched. However, this operation **does not** send a command forcing the phone or password manager to delete the private key or synced copies, so the UI should clearly state "remove from this account."

### 9.2. Deleting the entire user entity

When an account is deleted per application workflow:

1. Resolve account ID and user handle via trusted mapping.
2. Find all `CredentialRecord`s with `findByUserId(handle)`.
3. Revoke/delete or safely tombstones credentials per policy and emit secret-free audit records.
4. Process the user entity via `PublicKeyCredentialUserEntityRepository.delete(handle)` per repository/DB semantics and foreign-key order.
5. Delete/deactivate the application user and any active sessions using controlled transactions and retention.

Never delete the user entity before handling credential records if doing so leaves orphans or violates foreign keys. Never reassign an old handle to a new account; credentials once registered under that handle must never link to someone else.

### 9.3. Recovery when all passkeys are lost

Never design "passwordless" to mean "no recovery mechanism exists." Common options include:

- A backup passkey on a security key stored safely.
- A verified sign-in channel (if password/SSO is accepted), then enrolling a new credential.
- A high-assurance recovery workflow checking multiple proofs and defending against social engineering.
- Policy to revoke lost credentials, close related sessions, and send security alerts.

**Never allow registering a new passkey simply by entering an email address**; if recovery accepts an unverified claim, an attacker can attach their passkey to the victim's account. In particular, changing email/recovery methods carries high account-takeover risk and should require extra verification and security notifications.

### 9.4. Credential sync and answering "lost one device"

If a passkey synced across multiple devices, revoking the **credential ID on the server** blocks all copies of that same credential against that RP (regardless of which devices still hold the private key). If you only remove the passkey from one device while the credential remains in another synced ecosystem, the RP may still accept assertions from it. Therefore, clearly distinguish "remove from phone," "delete in passkey manager," and "revoke login access on the server."

## 10. Advanced security and operational considerations

### 10.1. RP ID and origin

WebAuthn enforces **Relying Party ID** (`rpId`) and origin bindings. For a real domain, e.g.:

~~~java
http.webAuthn(webAuthn -> webAuthn
        .rpId("example.com")
        .allowedOrigins("https://app.example.com"));
~~~

This is a **snippet placed inside a `SecurityFilterChain` configuration**, not a standalone Java file. If accessed on a different domain than configured, the browser may block credential creation or the server may reject assertions. Never feed caller-supplied RP IDs/origins into trusted configuration. The WebAuthn protocol requires a secure context; `localhost` is typically a lab exception, while production uses HTTPS.

### 10.2. Information to protect in the DB

Private keys do not live on the server, yet the database remains sensitive security data:

- Public keys, credential IDs, user handles, and metadata can enable tracking or account correlation.
- Attestation and transport data can reveal device hints; limit retention and read access.
- `lastUsed`/IP/user-agent logs, if added by the application, are behavioral data; consider privacy.
- Protect mapping integrity: an attacker modifying `userEntityUserId` or inserting a public key can hijack authentication.
- Audits should record **hashes/internal reference IDs** rather than raw credential IDs/responses. Do not log full assertions or `clientDataJSON` unnecessarily.

### 10.3. Transactions and concurrency

In multi-node environments, operations carry race risks:

- Two registrations with duplicate credential IDs: a DB `UNIQUE` constraint must reject inconsistent state.
- Two concurrent DELETEs: checking "at least one passkey remains" then deleting two different credentials can leave the user with zero passkeys. If policy forbids that, use transactions/locks or a conditional SQL statement enforcing the invariant.
- Concurrent label rename and login updating `signatureCount`/`lastUsed`: saving a stale full record can overwrite newer updates. Use optimistic locking/versioning or field-specific/conditional updates.
- Concurrent username rename and registration: keep handles and mappings consistent within a single transaction.
- Stale credential cache: right after revocation, another node must not keep accepting cached public keys beyond policy limits.

A single-threaded demo or mocked repository cannot verify these scenarios.

### 10.4. Sign count and backup flags

`signCount` can help detect cloned devices on certain authenticators, yet passkey syncing can leave the counter at 0 or cause divergence across copies. Never apply a naive comparison like "counter did not increment = hacked account" across all authenticators. Signed BE/BS flags in WebAuthn data help classify backup behavior, **not** prove exact device counts or absolute trustworthiness.

### 10.5. Labels and device management

- Users can enter free-form labels; enforce length limits, escape HTML, and prevent XSS.
- Do not expose exact hardware serials/sensitive metadata unnecessarily.
- If you want to show a "platform/roaming" hint, use appropriate WebAuthn transport/attachment signals and state clearly that hints may be imprecise.
- When multiple passkeys exist, recommend adding an independent backup method rather than relying on one device.
- Changing a label does not require creating a new credential; deleting and re-registering will yield a **different credential ID and public key**.

## 11. Common issues and troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Registering a second passkey makes the first disappear | App stores only 1 credential per user or overwrites key by mistake | Check 1:N mapping and `credentialId` primary key |
| Two users see the same passkey | Used email/name as user handle, broken mapping, or skipped ownership check | Check opaque IDs, foreign keys, and server-side authorization |
| Registration succeeds but restart loses passkeys | Using Map repository or H2 `mem` | Switch to JDBC + durable DB with proper migrations |
| Node A registers yet node B cannot log in | Challenge/session not shared or in-memory credential repo | Check shared DB and session/challenge store |
| `JdbcUserCredentialRepository` SQL/table-missing error | `user-credentials-schema.sql` not created or wrong dialect | Run exact schema/migrations, verify DB user privileges |
| IDE cannot find `JdbcPublicKeyCredentialUserEntityRepository` | Using Spring Security 6.4 | Upgrade to 6.5+ or write custom implementation |
| WebAuthn options returns 403 | Missing CSRF token or unauthenticated during registration | Check Spring CSRF and user session |
| Browser does not show passkey prompt | Wrong origin/RP ID, no secure context, unsupported device | Verify HTTPS/localhost, `rpId`, browser support |
| Valid credential but authentication rejected | Wrong challenge/origin/rpId or mismatched record/publicKey | Inspect request verification and record storage; never bypass validation |
| Someone else's DELETE succeeds | IDOR from trusting credential ID without owner check | Verify `userEntityUserId == current userHandle` on server |
| After server deletion UI still suggests old passkey | Credential remains in client passkey manager | Explain RP revocation vs. local deletion |
| User loses all passkeys after two parallel DELETEs | Last-passkey check is non-atomic | Use DB locking/transactions/conditional delete |
| User renames username and passkey stops working | Generated a new user handle or stale mapping | Keep handle intact and migrate mapping |
| Device count in UI differs from record count | One passkey synced across multiple devices | Do not infer device count from credential records |
| "Signature counter" does not increment | Synced passkey or authenticator doesn't support counters | Handle per RP policy and WebAuthn semantics |

## 12. Self-check questions

1. Why are application user, WebAuthn user entity, and credential not three names for the same object?
2. Which property links a `CredentialRecord` to a `PublicKeyCredentialUserEntity`? Which property locates the exact credential?
3. Should the user handle be an email address? Why or why not?
4. When an account has 3 credentials, which repository method must return a 3-element list?
5. Do two devices using the same synced passkey necessarily create two credential IDs on the server?
6. Why is checking "the credential ID is hard to guess" insufficient to authorize a `DELETE`?
7. After deleting a credential on the RP, does the private key automatically disappear from the device/sync manager?
8. When renaming a username, what must remain unchanged so old passkeys keep working?
9. How does an in-memory repository differ from JDBC when deploying 3 replicas?
10. Why does a single-request test showing "deleting the last passkey returns 409" not prove safety against two concurrent `DELETE`s?
11. What is `getLabel()`'s role? Should labels ever be used as primary keys?
12. When a user has 2 independent credentials, does authenticating with the second credential require separate permissions or still map to the same application user?

**Guiding answers:** (1) business account / WebAuthn user handle / public-key record; (2) `userEntityUserId` and `credentialId`; (3) no, because it leaks PII and can change; (4) `UserCredentialRepository.findByUserId(handle)`; (5) no; (6) owner ACL + CSRF/re-auth are needed; (7) no; (8) opaque user handle and mappings/credential records; (9) JDBC shares persistence, in-memory is per-instance; (10) TOCTOU race condition; (11) UI label, not a selector; (12) same user handle, therefore same account, once the Relying Party verifies the assertion.

## 13. Practical implementation checklist

- [ ] **Application account → 1 user entity → N credentials** model with durable mapping.
- [ ] User handle is opaque, unique, free of PII, and never rotated on each registration.
- [ ] Credential ID is unique, public key/COSE and metadata stored in proper types; no private keys on server.
- [ ] Registering a new credential does not overwrite existing credentials.
- [ ] Reading/renaming/removing credentials relies on the logged-in principal and server-side owner checks.
- [ ] Policy prevents locking out the account when deleting the last passkey; recovery/step-up/auditing in place.
- [ ] Exact Spring Security version chosen; for 6.5 JDBC repositories, run official schema/resources and migrations.
- [ ] Shared database for clusters with verified challenge/session consistency.
- [ ] Tests for 2+ passkeys on one account, cross-user IDOR, duplicates, expired challenges, signing, and revocation.
- [ ] HTTPS, RP ID, allowed origins, CSRF, and access controls protecting credential management.
- [ ] Concurrency tests for delete/rename operations, not just sequential tests.
- [ ] Clear understanding that synced passkeys do not equate to multiple DB credentials or exact physical device counts.
- [ ] Defined workflows for user rename, account deletion, recovery, and WebAuthn data backup/restore.

## 14. References

- [Spring Security 6.5 — Passkeys (Servlet, WebAuthn)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html)
- [Spring Security 6.5 — WebAuthn What's New: JDBC persistence](https://docs.spring.io/spring-security/reference/6.5/whats-new.html)
- [Spring Security 6.5 — PublicKeyCredentialUserEntityRepository API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/PublicKeyCredentialUserEntityRepository.html)
- [Spring Security 6.5 — UserCredentialRepository API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/UserCredentialRepository.html)
- [Spring Security 6.5 — CredentialRecord API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/api/CredentialRecord.html)
- [Spring Security 6.5 — Bytes API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/api/Bytes.html)
- [Spring Security 6.5 — JdbcUserCredentialRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/JdbcUserCredentialRepository.html)
- [Spring Security 6.5 — CredentialRecordOwnerAuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/CredentialRecordOwnerAuthorizationManager.html)
- [Spring Security 6.4 GA — Passkey support introduced](https://spring.io/blog/2024/11/19/spring-security-6-4-goes-ga/)
- [MDN — Passkeys: create multiple and backup](https://developer.mozilla.org/en-US/docs/Web/Security/Authentication/Passkeys)
- [W3C Web Authentication specification](https://www.w3.org/TR/webauthn-3/)
