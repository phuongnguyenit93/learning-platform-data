# Unique Identifiers, Data Constraints, and Handling Duplicate Account Names

In a Spring Security Authentication system, **successful authentication must lead to a clearly identified identity**, not "just pick the first row with a similar name". If two accounts are allowed to share a username without a defined distinguishing scope, looking up an account to verify passwords, attach a principal, and check permissions becomes ambiguous. If uniqueness is only checked via `SELECT` before `INSERT`, two concurrent requests can still create duplicate records unless the database enforces the corresponding constraint.

This lesson belongs to the **Account Store** group of Spring Security Authentication. The focus is on **unique and stable internal identifiers, login keys with a consistent normalization rule, database unique constraints/indexes, handling duplicate account names during registration/renaming, concurrency safety, and the boundary between the account repository and `UserDetailsService`**.

**Bottom line upfront:** Separate the **`accountId`** used as a durable identity from the **`loginName`** entered by the user; define *within what scope* a login name must be unique; store a **normalized `loginKey`**; and let the **database** enforce ultimate uniqueness. Application-level validation is only for clear user feedback, never a replacement for constraints.

## 1. Three Kinds of Identifiers That Must Not Be Conflated

An account can have multiple forms of identifiers:

| Component | Example | Contract | Should it be used as a foreign key? |
|---|---|---|---|
| **Internal account ID** | UUID `1a...` | Unique, immutable, system-owned | **Yes**, preferred for business data and audits |
| **Login name / username** | `linh`, `Linh`, `linh@company.example` | User-entered or managed; can be changed | Usually **no**; it is an alias/credential identifier |
| **Canonical login key** | `linh` | Normalized value for lookup and uniqueness enforcement | Used for lookup; does not replace `accountId` as primary key |
| **External identity key** | `(issuer, subject)` from OIDC | External identifier scoped by identity provider | Linked via a mapping table to `accountId` |
| **Display name** | `Linh Nguyen` | Display content, allowed to repeat freely | **No**; not an authentication factor |

For example, two people having the same display name `"Nguyen Van An"` is completely normal. However, if the login policy is "username unique within each organization", two accounts in the same organization cannot share the same **canonical login key**. Two different organizations can both have the username `"an"` if the login flow knows which organization is being authenticated against.

### 1.1. Why Must accountId Be Stable?

Tables such as `orders.created_by_account_id`, `project_memberships.account_id`, and `audit_logs.actor_account_id` should reference an account by internal ID, not email/username. If a user renames `linh` to `linh.nguyen`, order history, permissions, and audit logs still point to **the same account**.

A stable ID does not mean security checks can be skipped: a hard-to-guess UUID is not authorization. An API like `GET /accounts/{id}` must still check whether the caller is authorized to view that account. When an account is closed or personal data is erased, define retention/soft-delete policies and how audit logs retain references per policy.

### 1.2. "Unique" Always Has a Scope

There are two main models:

- **Global username:** each `loginKey` can be used at most once across the entire system. Login lookup can query by key alone.
- **Tenant-scoped username:** each `(tenantId, loginKey)` pair is unique. `linh` in company A and `linh` in company B are two distinct accounts.

Do not use global uniqueness if the business intentionally allows identical usernames across tenants; likewise, do not use tenant-scoped uniqueness when the login form only takes username/password with **no trustworthy way to select the tenant**, because the system cannot determine which account is being looked up. Depending on the product, users select an organization, a URL/subdomain identifies the tenant, or an identity broker performs account discovery before authentication; each approach requires permission checks and anti-enumeration protection.

One account can operate across multiple tenants through a membership table. In that case, **global identity**, **login identifier**, **per-tenant membership**, and **per-tenant authorization** are distinct concepts; do not force every system into a one-account = one-tenant model.

## 2. Normalizing Login Names: Are Two Similar-Looking Strings Actually Duplicates?

User-entered identifiers often vary in casing, whitespace, and Unicode:

~~~text
Alice
alice
  ALICE
Ａｌｉｃｅ  (fullwidth Unicode characters)
A\u0301lice (combining Unicode; only to illustrate what needs a policy)
~~~

No single `toLowerCase()` call is the right answer for every locale, every personal name, and every username. You must **choose the identity policy first**, then apply it consistently during registration, renaming, login, data imports, and migrations.

### 2.1. Simple ASCII Username Policy Example

To make testing easy and avoid Unicode pitfalls in the Java 17 example below, we choose an **illustrative** policy:

1. Trim leading/trailing whitespace with `String.strip()`.
2. Convert ASCII Latin letters to lowercase with `toLowerCase(Locale.ROOT)`.
3. Allow **only** characters `a-z`, `0-9`, dot, underscore, hyphen, total length 3–32.
4. Store `loginName` for display (the stripped version) and `loginKey` for lookup/uniqueness enforcement.

Under this policy:

| User input | loginKey | Result |
|---|---|---|
| `Alice` | `alice` | Valid |
| `  ALICE  ` | `alice` | Conflicts with `Alice` in the same namespace |
| `a.li_ce-2` | `a.li_ce-2` | Valid |
| `Álice` | — | Rejected because outside the chosen character set |
| `ab` | — | Rejected because too short |
| `alice@example.com` | — | Rejected because this example disallows `@` |

If the product **allows login by email**, design a dedicated canonicalization policy considering accepted email rules and address verification. Do not arbitrarily strip dots, plus signs, or `+tag` suffixes, or assume all emails map to the same mailbox: that depends on the mail provider and can accidentally merge accounts.

### 2.2. With Unicode or Multiple Languages

If allowing Vietnamese usernames, Han characters, or other Unicode characters, consider:

- Normalizing with `NFC` or `NFKC` per product policy; NFKC can collapse compatibility forms that users expect to remain distinct.
- Case mapping/case folding and locale rules; `Locale.ROOT` does not fully replace Unicode case folding.
- Visually confusable characters, zero-width characters, combining marks, and length measured by code point/grapheme rather than just `String.length()`.
- Whether database collation/index rules actually match the application policy.
- Migrations when normalization rules change, because previously distinct `loginKey` values can suddenly collide.

**Never apply two different algorithms** during registration and login. If the application saves keys using Java while SQL searches with `lower(login_name)` under a different collation, the same input can yield wrong lookups. For multilingual identifiers, explicitly test Unicode edge cases prone to unintended merging or splitting.

## 3. Placing Constraints at the Database Layer: PostgreSQL Example

Below is an **illustrative schema for PostgreSQL** assuming an account belongs to one tenant, usernames are ASCII-only, and password hash may be null if signing in via an IdP. A real product may need to separate accounts from memberships or store multiple login identities.

~~~sql
CREATE TABLE accounts (
    id            UUID PRIMARY KEY,
    tenant_id     UUID NOT NULL,
    login_name    TEXT NOT NULL,
    login_key     TEXT NOT NULL,
    password_hash TEXT,
    status        TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_accounts_login_name_not_blank
        CHECK (btrim(login_name) <> ''),
    CONSTRAINT ck_accounts_login_key
        CHECK (login_key ~ '^[a-z0-9._-]{3,32}$'),
    CONSTRAINT ck_accounts_status
        CHECK (status IN ('PENDING', 'ACTIVE', 'SUSPENDED', 'CLOSED')),
    CONSTRAINT uq_accounts_tenant_login_key
        UNIQUE (tenant_id, login_key),
    CONSTRAINT uq_accounts_tenant_id
        UNIQUE (tenant_id, id)
);
~~~

Explanation:

- `id`: unique primary key for every account; generated by the server or database per policy, never trusting a client-supplied ID.
- `tenant_id`: username scope. If referencing a `tenants` table, declare the actual FK in your production schema.
- `login_name`: controlled display/returned name, not used for fuzzy lookup comparisons.
- `login_key`: normalized key **computed with identical logic across all write paths**. The DB `CHECK` constrains the character set for this ASCII example; the DB does not automatically derive `login_key = normalize(login_name)`. Enforce consistency through the service layer, a suitable database-generated expression/trigger, or tested mechanisms.
- `password_hash`: nullable if the account does not use an internal password; business constraints must ensure the account has a valid sign-in method.
- `uq_accounts_tenant_login_key`: only one account per `(tenant_id, login_key)` pair, even under concurrent requests.
- `uq_accounts_tenant_id`: auxiliary constraint supporting the composite FK example below; redundant for uniqueness because `id` is already PK, yet useful when an FK must preserve tenant boundaries.

PostgreSQL automatically creates a unique B-tree index backing `UNIQUE`; typically **you do not need to create a duplicate index**. `UNIQUE (tenant_id, login_key)` does not enforce globally unique usernames and does not enforce unique display names.

### 3.1. Protecting Tenant Links in Child Tables

A membership table or tenant-scoped resource can use a composite FK:

~~~sql
CREATE TABLE account_audit_refs (
    id         UUID PRIMARY KEY,
    tenant_id  UUID NOT NULL,
    account_id UUID NOT NULL,
    CONSTRAINT fk_audit_account_same_tenant
        FOREIGN KEY (tenant_id, account_id)
        REFERENCES accounts (tenant_id, id)
);
~~~

Why not just an FK on `account_id`? In tenant-scoped business tables, a write bug could insert a row with `tenant_id = A` pointing to an account in `tenant_id = B`. A composite FK lets the database block this kind of **cross-tenant reference**. It does not replace authorization, row-level security, or ownership checks on reads/writes.

### 3.2. CHECK, NOT NULL, UNIQUE, PK, and FK Solve Different Problems

| Mechanism | What does it prevent? | What does it not solve on its own? |
|---|---|---|
| `PRIMARY KEY` | Two rows with the same account ID; null IDs | Duplicate usernames, access permissions |
| `NOT NULL` | Missing required values | Empty strings or whitespace-only strings |
| `CHECK` | Values outside an allowed set/condition | Conflicts with another row |
| `UNIQUE` / unique index | Duplicate keys within the defined scope | Normalization before writing, granting permissions |
| `FOREIGN KEY` | References to non-existent rows or mismatched composite keys | Ensuring an HTTP caller is allowed to view the row |
| Transaction | Atomic group of changes per DB semantics | Uniqueness if you never created a constraint/index |

Java validation is a necessary layer for early error reporting, but **not the final arbiter** when multiple processes write to the same database.

### 3.3. Nullable Columns and Email Policies

In PostgreSQL, `UNIQUE(email)` by default **allows multiple rows with NULL email**; NULL values are not considered equal in default unique checks. PostgreSQL 15+ provides `UNIQUE NULLS NOT DISTINCT` syntax if policy requires treating NULLs as equivalent. Choose based on requirements rather than treating it as a universal database rule.

Do not blindly mark `email UNIQUE` if the business allows multiple accounts to share a contact address, or one person to hold accounts in different tenants. **Is the email verified?** and **is the email a login identifier?** are separate questions. If logging in by email, email uniqueness and canonicalization must be defined within the proper scope.

### 3.4. External Identity Provider Keys

For OIDC/OAuth2, subjects are meaningful within an issuer scope, so a mapping model can look like:

~~~sql
CREATE TABLE external_identities (
    id               UUID PRIMARY KEY,
    account_id       UUID NOT NULL REFERENCES accounts(id),
    issuer           TEXT NOT NULL,
    external_subject TEXT NOT NULL,
    CONSTRAINT uq_external_issuer_subject
        UNIQUE (issuer, external_subject)
);
~~~

`(issuer, external_subject)` identifies a linked external identity, while `account_id` points to the internal account. Do not auto-merge accounts based on an IdP-provided email without a verified linking policy. If there are multiple tenants or other identity types, define the unique scope upfront to prevent unwanted cross-links.

## 4. Why SELECT Before INSERT Fails to Prevent Duplicates Under Concurrency

A common mistake:

~~~text
Request A: SELECT login_key='linh' -> not found
Request B: SELECT login_key='linh' -> not found
Request A: INSERT account 'linh'  -> succeeds
Request B: INSERT account 'linh'  -> succeeds if DB lacks UNIQUE
~~~

Even if you run:

~~~sql
SELECT 1
FROM accounts
WHERE tenant_id = :tenantId AND login_key = :loginKey;
~~~

before inserting, the gap between **checking** and **writing** remains a race-condition window (*time of check/time of use*, TOCTOU). Application-level existence checks alone cannot stop requests from multiple app instances, background jobs, or admin tools from writing duplicates.

### 4.1. Unique Constraints Are the Final Arbiter

When `uq_accounts_tenant_login_key` exists:

~~~text
T0: Requests A and B both query first and see the key is available.
T1: A INSERT (tenant X, login_key='linh').
T2: B INSERT (tenant X, login_key='linh').
T3: Database guarantees no two committed rows share the same unique key.
    - A wins: B may wait and then receive a unique violation.
    - A rolls back: B may proceed depending on transaction/DB.
~~~

In PostgreSQL, unique key violations have SQLSTATE **`23505`** (`unique_violation`). The constraint name in the error identifies exactly which key conflicted; never assume every `DataIntegrityViolationException` or SQL error means "username already exists".

**A transaction alone does not replace a unique constraint.** Under standard isolation levels, two `SELECT` statements can still both observe zero rows. The reliable fix is creating the constraint/index that captures the business invariant and handling the conflict branch.

### 4.2. SQL INSERT and Conflict Handling

Standard insert:

~~~sql
INSERT INTO accounts (
    id, tenant_id, login_name, login_key, password_hash, status
) VALUES (
    :id, :tenantId, :loginName, :loginKey, :passwordHash, 'ACTIVE'
);
~~~

Parameters `:id` ... above are data-access-layer placeholders; do not run directly in `psql` without binding values. When a constraint is violated, roll back the transaction and respond per policy.

PostgreSQL supports an option to avoid throwing an exception for an **expected** duplicate:

~~~sql
INSERT INTO accounts (
    id, tenant_id, login_name, login_key, password_hash, status
) VALUES (
    :id, :tenantId, :loginName, :loginKey, :passwordHash, 'ACTIVE'
)
ON CONFLICT ON CONSTRAINT uq_accounts_tenant_login_key
DO NOTHING
RETURNING id;
~~~

If the statement returns an ID, the new account was inserted. If it returns **0 rows**, an account with that key already exists / conflicted; the service handles the duplicate properly rather than fetching the existing account and treating the requester as its owner. If other constraints exist, their errors must still be handled separately.

**Warning:** Avoid `ON CONFLICT DO UPDATE SET password_hash = EXCLUDED.password_hash` on a registration endpoint. It can allow an unverified caller to overwrite credentials or take over an existing account. "Duplicate registration" is never a valid reason to alter the password, permissions, verified email, or owner of an existing record.

### 4.3. Appropriate HTTP Responses and Account Enumeration

For a public username registration API, `409 Conflict` can make sense from a REST perspective when a resource name collides; however, **a distinct 409 response can also enable account enumeration**. Public policies must balance UX against anti-enumeration:

- For public usernames that are intentionally searchable, you can report unavailability behind rate limiting and load controls.
- For private emails/login identifiers, consider generic responses, email verification flows, and avoiding revealing account existence across endpoints.
- Regardless of response text, the backend must still prevent creating duplicate accounts or transferring rights on existing accounts.

Never return raw index names, SQLSTATEs, stack traces, or password hashes to clients. On the server, log a correlation ID and error code sufficient for diagnosis, never logging raw passwords.

## 5. Standalone Java 17 Example: Canonical Keys, Tenant Scope, and Races

The example below uses **plain JDK 17**, with no Spring Boot dependency, to demonstrate a verifiable invariant:

- The `(tenantId, loginKey)` pair is unique.
- `Alice` and `  ALICE  ` collide within the same tenant.
- The same `loginKey` in another tenant is permitted by policy.
- When two threads concurrently create `bob`, only one succeeds.
- `accountId` is generated separately and serves as the stable ID.

**Important:** `ConcurrentHashMap.putIfAbsent` in this example is only atomic **within a single JVM process**. It does not replace a database unique constraint when multiple service instances write concurrently. In production, the database must be the source of truth.

### 5.1. Structure and Java File

~~~text
account-name-demo/
└── src/example/AccountNameDemo.java
~~~

Create `src/example/AccountNameDemo.java`:

~~~java
package example;

import java.util.Locale;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class AccountNameDemo {

    record ScopedKey(UUID tenantId, String loginKey) {}

    record Account(UUID id, UUID tenantId,
                   String loginName, String loginKey) {}

    static final class DuplicateNameException
            extends RuntimeException {
        DuplicateNameException() {
            super("Login name already exists");
        }
    }

    static String normalize(String input) {
        Objects.requireNonNull(input, "loginName");
        String key = input.strip().toLowerCase(Locale.ROOT);
        if (!key.matches("[a-z0-9._-]{3,32}")) {
            throw new IllegalArgumentException("Invalid login name");
        }
        return key;
    }

    static final class AccountStore {
        private final ConcurrentMap<ScopedKey, Account> rows =
                new ConcurrentHashMap<>();

        Account create(UUID tenantId, String rawLoginName) {
            Objects.requireNonNull(tenantId, "tenantId");
            String key = normalize(rawLoginName);
            Account proposed = new Account(
                    UUID.randomUUID(), tenantId,
                    rawLoginName.strip(), key);
            ScopedKey scoped = new ScopedKey(tenantId, key);

            if (rows.putIfAbsent(scoped, proposed) != null) {
                throw new DuplicateNameException();
            }
            return proposed;
        }

        Optional<Account> find(UUID tenantId, String rawLoginName) {
            Objects.requireNonNull(tenantId, "tenantId");
            return Optional.ofNullable(rows.get(
                    new ScopedKey(tenantId, normalize(rawLoginName))));
        }
    }

    public static void main(String[] args) throws Exception {
        UUID tenantA = UUID.fromString(
                "00000000-0000-0000-0000-00000000000a");
        UUID tenantB = UUID.fromString(
                "00000000-0000-0000-0000-00000000000b");
        AccountStore store = new AccountStore();

        Account alice = store.create(tenantA, "Alice");
        System.out.println("A/Alice -> CREATED");

        try {
            store.create(tenantA, "  ALICE  ");
        } catch (DuplicateNameException ex) {
            System.out.println("A/ALICE -> DUPLICATE");
        }

        store.create(tenantB, "alice");
        System.out.println("B/alice -> CREATED");

        boolean found = store.find(tenantA, "aLiCe").isPresent();
        System.out.println("A/aLiCe found -> " + found);

        UUID lookedUpId = store.find(tenantA, "ALICE")
                .orElseThrow().id();
        System.out.println("stable account ID -> "
                + alice.id().equals(lookedUpId));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch go = new CountDownLatch(1);

        Callable<Boolean> createBob = () -> {
            go.await();
            try {
                store.create(tenantA, "bob");
                return true;
            } catch (DuplicateNameException ex) {
                return false;
            }
        };

        Future<Boolean> first = pool.submit(createBob);
        Future<Boolean> second = pool.submit(createBob);
        go.countDown();

        int created = (first.get() ? 1 : 0)
                    + (second.get() ? 1 : 0);
        pool.shutdown();
        System.out.println("concurrent bob -> created=" + created
                + ", duplicate=" + (2 - created));
    }
}
~~~

The code uses `Locale.ROOT` for the specific ASCII key rule, `UUID.randomUUID()` for the internal key, `ScopedKey` as the composite map key, and `putIfAbsent` for an atomic decision inside the JVM. Which thread wins is non-deterministic, yet **the count of successful creations** is deterministic because the map holds only one entry per key.

### 5.2. Compile, Run, and stdout

From the `account-name-demo` directory with JDK 17+:

~~~bash
javac -encoding UTF-8 -d out src/example/AccountNameDemo.java
java -cp out example.AccountNameDemo
~~~

Expected output:

~~~text
A/Alice -> CREATED
A/ALICE -> DUPLICATE
B/alice -> CREATED
A/aLiCe found -> true
stable account ID -> true
concurrent bob -> created=1, duplicate=1
~~~

Try changing `store.create(tenantA, "bob")` in the task to variants `"Bob"` and `" bOb "`: the result is still only one account because both normalize to `"bob"`. Try creating `"ab"` or `"linh@example.com"`: the program throws `IllegalArgumentException` per the example rule. If the business allows other characters, update the policy consistently across all layers, not just the regex.

### 5.3. Demo Limitations to Keep in Mind

- `ConcurrentHashMap` only protects within a single process. Two separate pods each have their own map and could still both create the same username; a DB unique constraint protects the system-wide invariant.
- There is no password hashing or Spring Security filter because this example focuses on **identity and uniqueness**, not demonstrating login.
- There is no renaming, account deletion, or multi-table transaction. Those operations must be designed atomically on the database.
- `UUID.randomUUID()` generates an ID with no authorization meaning; never expose or accept IDs from clients while skipping authorization.
- Output avoids printing UUIDs to keep stdout stable across runs. No step depends on which thread wins or their order.

## 6. Connecting to Spring Security: Looking Up Exactly One UserDetails

`UserDetailsService` has the contract:

~~~java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
~~~

It is a contract for loading authentication data by username for providers like `DaoAuthenticationProvider`; **it does not check passwords itself** and does not decide resource access permissions. Flow:

~~~text
Login request
  -> username is normalized per policy
  -> UserDetailsService / AccountRepository
  -> Lookup in the right namespace + canonical login key
  -> 0 row: UsernameNotFoundException
  -> 1 row: UserDetails containing trusted password hash/flags/authorities
  -> If >1 row: data integrity error; never pick the first row
  -> DaoAuthenticationProvider verifies password/status
  -> Authentication result with authenticated principal
~~~

An **illustrative implementation for an application with a single global login namespace**:

~~~java
@Service
public class AccountUserDetailsService implements UserDetailsService {

    private final AccountRepository repository;

    public AccountUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        String loginKey = LoginNames.normalize(username);
        AccountEntity account = repository.findByLoginKey(loginKey)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Invalid credentials"));

        return User.withUsername(account.getLoginName())
                .password(account.getPasswordHash())
                .authorities(account.getGrantedAuthorities())
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .build();
    }
}
~~~

**This is an integration snippet, not a standalone Java program.** It requires Spring imports, `AccountRepository`, `AccountEntity`, `LoginNames`, authority mapping, and status fields. `User.withUsername(...).password(...)` is only suitable when the account supports password login. If an account only uses OIDC, use the corresponding provider rather than putting a fake password hash on the account.

**With the `UNIQUE(tenant_id, login_key)` schema from section 3, you must not use `findByLoginKey(loginKey)` as-is** because one `loginKey` can exist in multiple tenants. You must pass the **tenant context established properly by the login flow** into the repository (for example `findByTenantIdAndLoginKey(tenantId, key)`) and configure an appropriate authentication pipeline/provider. Never blindly grab a tenant ID from the request body and treat it as verified authority.

### 6.1. If the Database Already Contains Duplicate Usernames from Legacy Data

A severe anti-pattern:

~~~java
return repository.findFirstByLoginKey(loginKey).orElseThrow(...);
~~~

If the database has two records sharing the key, a "first" query may return the wrong account or change depending on SQL execution plans, causing someone else's principal and business data to be used by mistake. **Never use `findFirst` as a workaround for duplicate identities.** Detect conflicts, refuse authentication for ambiguous identities, clean up the data, and add proper constraints. Never auto-merge two accounts if they have distinct data relations, credentials, or histories.

### 6.2. Spring Data/JPA and Constraint Naming

In Spring Data JPA, repository example:

~~~java
interface AccountRepository extends JpaRepository<AccountEntity, UUID> {
    Optional<AccountEntity> findByTenantIdAndLoginKey(
            UUID tenantId, String loginKey);
}
~~~

This is a **repository definition snippet**, requiring an `AccountEntity` with matching property names and imports. In a Spring app, putting `@Column(unique = true)` separately on both `tenantId` and `loginKey` **is not equivalent** to a composite unique `(tenantId, loginKey)`; doing so can forbid two tenants from using the same `loginKey`. Use explicit migration DDL (Flyway/Liquibase) or `@Table(uniqueConstraints = ...)` on the column pair, and verify the resulting schema.

Never use `ddl-auto=update` as a substitute for reviewed migrations in production. More importantly, verify the live DB actually has the right constraints and legacy data is clean.

## 7. Registration and Renaming in Spring: Handling Concurrency in the Right Place

Safe registration flow at the business level:

~~~text
Input registration (tenant, username, password...)
   |
   +--> Validate format / normalize -> loginKey
   +--> Optional existence check for UX only, never relied on as a lock
   +--> Hash password / verify registration prerequisites
   |
   v
Transaction: INSERT account with new ID
   |
   +--> Success -> commit -> emit appropriate domain event
   |
   '--> UNIQUE violation -> rollback -> handle duplicate per policy
~~~

### 7.1. Illustrative Service Snippet

~~~java
@Service
public class RegistrationService {
    private final AccountRepository accounts;
    private final PasswordEncoder encoder;

    public RegistrationService(AccountRepository accounts,
                               PasswordEncoder encoder) {
        this.accounts = accounts;
        this.encoder = encoder;
    }

    @Transactional
    public UUID register(UUID tenantId, String loginName,
                         String rawPassword) {
        String key = LoginNames.normalize(loginName);
        AccountEntity entity = new AccountEntity(
                UUID.randomUUID(), tenantId, loginName.strip(), key,
                encoder.encode(rawPassword));
        // saveAndFlush helps constraint errors typically surface here.
        return accounts.saveAndFlush(entity).getId();
    }
}
~~~

**This snippet is not a standalone runnable file**: `AccountEntity` constructor, beans, imports, and other constraints belong to the real project; password/tenant validation and registration policies must be added. It assumes transactions are active through a properly configured Spring proxy. `saveAndFlush` surfaces constraint errors earlier, **not replacing transaction commit** or any DB checks deferred until commit.

Duplicate handling must sit at the proper boundary:

- When `DataIntegrityViolationException` occurs, inspect the **confirmed** root cause/constraint (`uq_accounts_tenant_login_key` or matching SQLSTATE), then translate it into a domain "login name conflict" error.
- **Never treat every `DataIntegrityViolationException` as a duplicate username**: it could be an FK, check constraint, NOT NULL, another unique constraint, or schema error.
- In PostgreSQL, after a SQL error puts a transaction into an aborted state, do not continue querying inside **the same transaction** as if nothing happened. Let the transaction roll back and build the response outside the boundary; or use SQL `ON CONFLICT` with explicit semantics.
- Do not blindly retry the same username across requests: retrying after a confirmed duplicate constraint violation will just fail again; only retry if logic genuinely generates a new identifier per policy with bounded attempts.
- After commit succeeds, do not automatically sign the client in before completing required email verification/MFA/account policy checks.

### 7.2. Renaming a Username Must Preserve the Account ID

Renaming should be handled inside a transaction:

1. Authenticate the actor; verify account ownership or explicit admin permission.
2. Normalize the new name, validating format and namespace.
3. Update `login_name` and `login_key` on **the same `accountId`**.
4. On unique conflict, roll back; **never** delete accounts or rename the account currently holding the key.
5. Upon success, synchronize caches, audit events, and sessions/JWTs/login aliases if policy requires.

Never update order foreign keys just because a username changed. For principals holding a username snapshot, plan how to refresh stale names; principals carrying a stable ID avoid breaking references.

### 7.3. Should Old Names Be Reused or Reserved?

One product may allow an old username to be registered by someone else after renaming or closing an account; another reserves old names permanently to prevent impersonation, confusion, or account takeover. This is a **business policy**, not a Spring Security default.

You can maintain a `reserved_login_names` table with scope, canonical key, reason, and timestamp; or use a conditional unique index on active accounts. Be aware: recycling old names can cause links, mentions, usernames in emails, or account recovery flows to point to the wrong person. Always use `accountId` for internal links.

## 8. Soft Delete and Partial Unique Indexes: A Difficult Trade-off

If account rows have `deleted_at` or `status='CLOSED'`, the requirement "username only needs to be unique among active accounts" can be expressed using a **partial unique index** in PostgreSQL:

~~~sql
CREATE UNIQUE INDEX uq_accounts_active_login
ON accounts (tenant_id, login_key)
WHERE deleted_at IS NULL;
~~~

This is a **schema variant** requiring a `deleted_at` column and adjusting/removing the full unique constraint `uq_accounts_tenant_login_key` from the earlier example. Keeping the full unique constraint prevents the partial index from allowing old names to be reused.

This choice carries significant risks:

- Two different rows can share the same key, one closed and one active; login lookup must **filter status and namespace accurately**.
- When restoring a soft-deleted account, a unique conflict can happen if the key has already been reused.
- Never take the "first row" while omitting status filters; query strictly according to domain policy.
- Systems sending emails/notifications by old usernames, audit trails, and external links need routing rules to avoid leaking closed-account data.
- Dedicated migrations and tests are required before switching policy from "no reuse" to "reusable".

**Never enable a partial unique index just to make cleaning duplicate data easier.** Uniqueness scope must reflect product and security rules.

## 9. Cleaning Legacy Data Before Adding a UNIQUE Constraint

If a database already has legacy accounts, adding a unique constraint may fail due to duplicate rows. Execute a planned migration:

1. **Lock down the policy:** global vs. tenant-scoped, canonicalization, and whether names are reusable after closure.
2. **Backfill `loginKey`:** run the exact same normalization algorithm as the application, never an implicit SQL variant with different Unicode/case behavior.
3. **Find collisions:** group by scope + canonical key; report groups with more than one row.
4. **Classify:** typos, two distinct real people, duplicate imports, mistaken IdP links, or old soft-deleted accounts.
5. **Audited manual resolution:** rename the appropriate accounts and contact users when needed; never merge two people's passwords/permissions/data just because `loginKey` matched.
6. **Prevent duplicate writes during migration:** coordinate write freezes or a designed dual-write/constraint rollout; create the unique constraint once data is clean.
7. **Deploy atomically with a rollback plan:** test old/new app versions, caches, registration, login, renaming, and restore.
8. **Measure post-deploy:** unique conflict counts, login-not-found rates, unexpected duplicate accounts, query latency, and data alerts.

An **approximate** audit query **for this example's ASCII naming policy**:

~~~sql
SELECT tenant_id,
       lower(btrim(login_name)) AS candidate_key,
       count(*) AS duplicates
FROM accounts
GROUP BY tenant_id, lower(btrim(login_name))
HAVING count(*) > 1;
~~~

`lower(btrim(...))` is only for exploration here; it **must not be assumed unconditionally equivalent** to `String.strip().toLowerCase(Locale.ROOT)` when Unicode/collation or non-ASCII characters are involved. Production migrations should compute `login_key` using the confirmed policy and then group on the official column.

Also inspect **duplicate IDs, email/phone policies, external identity mappings, wrong tenant IDs, and orphaned foreign keys**. Never change account IDs to "eliminate duplicate usernames": the ID is the durable identity, while the login name is an adjustable alias per policy.

## 10. Common Errors and How to Fix Them

| Error | Impact | How to fix |
|---|---|---|
| Using username/email as primary key across tables | Renaming breaks relations/audits | Use immutable `accountId` |
| `findFirstByLoginName` when data can have duplicates | May log into the wrong account | Scope unique constraints properly, query expects 0/1 row |
| Only `existsByLoginName` followed by `save` | Race between two requests/pods | DB unique constraint + conflict handling |
| Using global unique in a tenant-scoped app | Wrongly blocks usernames in other tenants | Composite unique `(tenantId, loginKey)` |
| Using tenant-scoped unique when login only has username | Ambiguous lookup across tenants | Design trustworthy identity discovery/tenant selection |
| Lowercasing at registration, querying raw input at login | Same username resolves differently | Use identical canonicalization and `loginKey` column |
| Arbitrary Unicode normalization | Accidentally merges accounts or creates confusing aliases | Define policy, threat model, and Unicode tests |
| `@Column(unique=true)` on both columns separately | Creates two separate unique constraints, wrong logic | Composite unique constraint |
| Catching all DB errors as "duplicate username" | Masks FK/DB outage/check constraint failures | Classify by confirmed constraint/SQLSTATE |
| `ON CONFLICT DO UPDATE` overwriting password | Account takeover risk | On registration duplicate, never alter existing accounts |
| Soft-delete without updating unique/lookup | Wrong restore/login, unexpected name reuse | Clear recycle policy; matching partial index and queries |
| Returning SQL errors to client | Leaks schema and sensitive data | Controlled public responses, internal auditing |
| Renaming by creating a new account | Loses ownership/historical relations | UPDATE by stable ID, preserve audit trail |
| Using hard-to-guess UUIDs as proof of authorization | IDOR and data leaks | Check authorization on every resource |
| Slow cache sync after rename/lock | Old principal or permissions persist | Cache/session/token invalidation within security SLA |

## 11. Recommended Test Suite

Test at **two layers**: unit tests for canonicalization and integration tests against a **real database matching production**. H2/in-memory maps can illustrate logic, yet differ from PostgreSQL in collation, transactions, partial indexes, SQLSTATE, and concurrency; never substitute them for critical uniqueness tests.

| Scenario | Behavior to prove |
|---|---|
| Register `Alice`, then `ALICE` in same tenant | Second attempt flagged duplicate if policy ignores case |
| Register `Alice` in tenant A and tenant B | Allowed if policy is tenant-scoped |
| Look up user after normalization | Returns **one** account in the right scope |
| Username too short or disallowed characters | Rejected by validation, and DB rejects invalid `loginKey` |
| Two transactions insert the same `loginKey` concurrently | At most one row commits successfully |
| Retry request after network failure | Does not create a second account; proper idempotency strategy |
| DB throws non-unique FK/check error | Not misclassified as duplicate username |
| Switch `tenantId` during lookup | Never reads/issues principal from another tenant |
| Rename username | Account ID and foreign keys remain unchanged |
| Rename to an already-taken username | Rolls back; both old name and business data remain intact |
| Soft delete / restore | Respects name reuse policy and matching index |
| Migration data has collisions | Detected, never picks a random account |
| Two external IdPs share the same `sub` | Mapping by issuer + subject does not collide |
| Two accounts linked to one external identity | Unique constraint blocks duplicate link if disallowed |
| Login after account locked | Never grants authentication despite account row existing |
| Client supplies someone else's `accountId` | Cannot impersonate because server verifies actor/authorization |
| Registration returns conflict publicly | Leaks no information beyond allowed policy |

### 11.1. Self-Check Scenarios

**Question 1.** Two people in two companies share the username `linh`. Is `UNIQUE(login_key)` right?  
**Answer:** No if policy allows identical names per tenant; use `UNIQUE(tenant_id,login_key)` and ensure the login flow knows the trusted tenant.

**Question 2.** The service calls `existsByLoginKey` before `save`; why can duplicates still occur?  
**Answer:** Two requests can both observe the name does not exist yet. Only a DB unique constraint/unique index prevents duplicates under concurrent writes.

**Question 3.** A username changes from `Alice` to `alice.new`; should foreign keys in order tables be updated?  
**Answer:** No if they reference a stable `accountId`. Changing an alias does not create a new identity.

**Question 4.** Why is `UserDetailsService.findFirstByLoginName` dangerous when the DB already has duplicates?  
**Answer:** It hides ambiguity and can return the principal/credentials of the wrong record; fail closed and clean up the data.

**Question 5.** Should duplicate registration auto-update the password hash via `ON CONFLICT DO UPDATE`?  
**Answer:** No. Someone who has not proven account ownership could overwrite an existing account's credentials.

**Question 6.** Does `UNIQUE(email)` block multiple NULL emails in PostgreSQL?  
**Answer:** Not by default. Understand NULL semantics and nullable policies rather than guessing from the constraint name.

**Question 7.** What happens if you create a unique index with `deleted_at IS NULL` and forget to filter status during lookup?  
**Answer:** Multiple rows with the same `loginKey` (one active, one soft-deleted) can be found, causing identity confusion; keep indexes, queries, and restore policies aligned.

**Question 8.** A bearer token carries a valid `accountId` yet accesses another tenant's resource; is a valid ID enough to allow access?  
**Answer:** No. Valid identity does not replace tenant membership, ownership, and authorization.

## 12. Production Readiness Checklist

- [ ] Define **one immutable internal identity** (`accountId`) and use it for FKs/audits.
- [ ] Define the login identifier and **uniqueness scope**: global, tenant, or another identity namespace.
- [ ] Normalize and validate under one versioned/tested policy; keep **`loginKey`** consistent across registration, login, rename, and migration.
- [ ] Enforce a **real UNIQUE constraint/index** on the policy key and composite FKs if needed to block cross-tenant references.
- [ ] Define explicit rules for email/phone/external identities, nullability, and verification state.
- [ ] On concurrent duplicates, roll back / `DO NOTHING` cleanly; never overwrite existing accounts.
- [ ] Classify unique errors **by exact constraint**, never masking other infrastructure failures.
- [ ] Never use `findFirst` to sidestep duplicates; audit and clean up data via controlled migrations.
- [ ] Preserve `accountId` on username rename; update caches/sessions and audit logs per policy.
- [ ] Specify soft-delete, restoration, whether old names may be reused, and anti-impersonation rules.
- [ ] Test against real PostgreSQL for concurrent inserts, unique violations, collation, and transactions.
- [ ] Maintain clear boundaries between **account existence**, **authentication**, **authorization**, and **data privacy**.

**Remember:** **Login name is an alias within a namespace; account ID is the stable internal identity; a unique constraint is the final integrity safeguard under concurrent writes.** When Spring Security loads a user for authentication, it must receive exactly one principal resolved by namespace and normalization policy—never pick an arbitrary record among duplicate names.

### Official References

- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): `PRIMARY KEY`, `NOT NULL`, `CHECK`, `UNIQUE`, and `FOREIGN KEY`; multi-column unique, NULLs, and partial unique indexes.
- [PostgreSQL — Unique Indexes](https://www.postgresql.org/docs/current/indexes-unique.html): indexing mechanism for unique constraints and multi-column uniqueness.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): conflict handling on writes and `RETURNING`.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): `23505` / `unique_violation`.
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html): `loadUserByUsername` contract, returning `UserDetails` or throwing `UsernameNotFoundException`.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): username/password authentication after loading data via `UserDetailsService`.
