# Username, Email Normalization, and Case-Sensitivity Policies

## 1. Why Does an Account Need an Explicit Identity Policy?

In a system with Spring Security, users might enter `Lan`, `lan`, `LAN`, ` Lan `, or an address like `Sales@Example.COM` to log in. If the sign-up screen, database, `UserDetailsService`, and login page **process those strings under different rules**, the application easily runs into bugs: someone cannot log in despite having the right password, multiple accounts share lookalike names, duplicate checks behave inconsistently, or identities get linked to the wrong person.

**Identifier normalization** is the process of applying a published rule to produce a **stable comparison key** from user input. **Case sensitivity** is an identity-model decision that must stay consistent across the entire account lifecycle: registration, login, search, updates, identity linking, uniqueness checks, and migrations.

A sound design typically separates:

| Field | Example | Purpose |
| --- | --- | --- |
| `user_id` | `4f2d...` or system-assigned numeric ID | Stable internal key used for foreign keys and authorization. |
| `username_display` | `Lan_08` | Preserves the user's chosen casing if the product wants to display it that way. |
| `username_key` | `lan_08` | Lookup and uniqueness constraint per username policy. |
| `email_original` | `Sales@Example.COM` | Address supplied by the user for verification/contact; preserves local part. |
| `email_lookup_key` | `Sales@example.com` | An email lookup key per intentional policy; do not assume the entire email must be lowercased by default. |
| `email_verified_at` | Timestamp when email control was verified | Distinguishes declared email from verified email. |

Not every application needs all of these columns. **What is mandatory is unifying the rules**: what serves as the identity key, what serves as display/contact info, and which string is used in queries finding an account.

In Spring Security, `UserDetailsService.loadUserByUsername(String username)` **does not impose a universal case-sensitivity policy**. Per the API contract, implementations may search case-sensitively or case-insensitively; the returned `UserDetails` may even carry a username with different casing from the requested parameter. The actual policy belongs to the user store/adapter and application data.

## 2. Three Actions Commonly Lumped Together as "Normalization"

You must distinguish three steps, because mixing them up can cause data loss or accidental account merging:

1. **Validation**: defines accepted input. For example, usernames contain only ASCII `a-z`, digits, dots, underscores, and hyphens; a demo email accepts only a simple syntax subset.
2. **Canonicalization**: maps strings considered **equivalent under the chosen policy** to the same key. For example, `Lan_08` and `LAN_08` both have `username_key=lan_08` when usernames are defined as case-insensitive.
3. **Presentation/preservation**: stores original data useful for UI or communicating with external systems. For example, keeping `Sales@Example.COM` as the original email rather than automatically rewriting it to `sales@example.com`.

Transformations can create **collisions**. Before normalization, `Lan` and `lan` are two distinct strings. After normalization under a case-insensitive policy, they become **one key**. This is the desired behavior for new registrations if the system specifies case-insensitive usernames, yet becomes a major issue if legacy data already holds **two distinct accounts**.

**Design rule:** define normalization to produce keys, check for collisions, and only then persist. Never alter policy on a live system without checking existing data first.

## 3. Deciding Policy for Usernames

Usernames are identifiers **managed by the application itself**, so the product has the right to pick a sensible policy, for example:

| Policy | Do `Lan` and `lan` Share a Key? | Benefits | Trade-offs |
| --- | --- | --- | --- |
| **Case-insensitive ASCII** | Yes | Users rarely have to remember casing; simple in APIs and databases. | Must block duplicates by canonical key; restricts non-ASCII characters. |
| **Case-sensitive ASCII** | No | Two strings can represent two separate accounts. | Easily causes confusion in support, search, and login; hard to migrate when changing policy. |
| **Unicode with rule-based case folding** | Depends on algorithm | Allows multilingual names. | Must solve Unicode normalization, full case folding, confusables, versioning, and collisions. |

**A practical choice for learning Spring Security**: login usernames following an **ASCII, case-insensitive** policy with bounded length and character set; if Vietnamese names or emoji are needed, use a separate **display name** field. This lets learners focus on the `UserDetailsService` and `DaoAuthenticationProvider` contracts without tackling undesigned Unicode edge cases.

A concrete policy might be:

- Accept names only 3–30 characters long after stripping leading/trailing whitespace.
- First character is an ASCII letter or digit.
- Subsequent characters belong to `a-z`, `0-9`, `.`, `_`, or `-`.
- Letters `A-Z` are accepted and lowercased in the **lookup key** via `toLowerCase(Locale.ROOT)`.
- Whitespace inside the username is rejected; Unicode characters outside the accepted set are rejected.
- Do not register two accounts with the same `username_key`.
- Maintain a list of system-reserved usernames such as `admin`, `root`, and `support` per product policy.

**Examples:**

| Input | Username Key | Valid? |
| --- | --- | --- |
| `Lan_08` | `lan_08` | Yes |
| ` LAN_08 ` | `lan_08` | Yes, because policy allows stripping leading/trailing whitespace |
| `lan.08` | `lan.08` | Yes |
| `lan name` | — | No, contains internal whitespace |
| `Lân_08` | — | No under the example's ASCII policy |
| `ab` | — | No, fewer than 3 characters |

This is **an illustrative suggested policy**, not a mandatory Spring Security rule or an international username standard. An application may choose case-sensitivity or Unicode, but must declare it explicitly and enforce it consistently everywhere accounts are created, read, or edited.

## 4. Java 17: Why Is `Locale.ROOT` Needed When Building Identifier Keys?

Java has both `String.toLowerCase()` and `String.toLowerCase(Locale locale)`. The **no-argument** overload depends on the JVM's default locale, so it can generate different keys on machines running different locales.

For example, uppercase `I` in Turkish can turn into `ı` (dotless i) when lowercased under the `tr-TR` locale. If one service defaults to English while another uses Turkish, lookup/registration workflows can disagree on the same username.

For **locale-neutral identifiers** under an ASCII policy, use:

```java
String key = input.strip().toLowerCase(Locale.ROOT);
```

`Locale.ROOT` keeps results independent of the machine's default locale. `strip()` removes certain leading/trailing Unicode whitespace per `Character.isWhitespace`; it **does not remove internal whitespace**. After conversion, the application **must re-validate** the entire string against the chosen character set and length.

**Do not confuse `toLowerCase(Locale.ROOT)` with "Unicode full case folding".** Java's lowercasing does not automatically resolve all Unicode equivalences such as `ß` and `ss`, characters with combining diacritics, lookalike characters across scripts, or differing Unicode versions. If the system genuinely allows Unicode usernames, you need dedicated normalization/folding policies and multilingual testing; never just call `toLowerCase` and declare characters equivalent.

### NFC, NFKC, and Ambiguity Risks

Unicode can represent one visible character with multiple code-point sequences. For instance, an accented letter can use a precomposed code point or a base letter plus a combining mark.

- **NFC** merges sequences equivalent under *canonical equivalence*; typically part of a Unicode username policy.
- **NFKC** additionally applies compatibility equivalence, which can alter the visual form or meaning of certain characters. Do not apply NFKC blindly to "fix all similar names".
- **Full case folding** differs from ordinary lowercasing; it requires dedicated libraries and deterministic rules, especially across scripts.
- **Confusables/homoglyphs**: Latin letter `a` can look identical to a character from another script; NFC/NFKC or lowercasing alone does not stop lookalike impersonation.

If choosing Unicode usernames, specify **the exact order normalize → fold → validate → store key**, publish the supported Unicode form, and check every write path. When upgrading libraries or Unicode versions, re-test for collisions before rollout.

## 5. Email Differs from Username in One Key Respect: Local Part and Domain

An email has the general form `local-part@domain`, e.g., `Sales@Example.COM`:

- **Domain** sits after `@`. By DNS/SMTP rules, domain names are **case-insensitive**: `Example.COM` and `example.com` are the same domain.
- **Local part** sits before `@`. By SMTP standards, this part **must have its letter casing preserved intact** when handling addresses; some mail servers may distinguish `Sales` and `sales`. Although many modern providers treat local parts case-insensitively, an application **cannot assume that for every domain**.

Therefore, there are two **distinct** questions:

1. **Using email to send notifications:** store the address the user provided/verified without arbitrarily altering the local part. You may canonicalize the domain per DNS/IDNA rules; ensure delivery formatting stays accurate.
2. **Using email as a login name/account key:** the application must choose an explicit lookup rule. It may decide to be case-insensitive across the entire address for UX, **yet doing so merges local parts that some mail servers treat as separate mailboxes**.

| Address A | Address B | Compare Domain Case-Insensitively | Compare Local Part per SMTP |
| --- | --- | --- | --- |
| `Sales@Example.COM` | `Sales@example.com` | Same domain | Same local part |
| `Sales@example.com` | `sales@example.com` | Same domain | **May be two different mailboxes** |
| `alice+promo@example.com` | `alice@example.com` | Same domain | **Must not merge by default** |
| `first.last@gmail.com` | `firstlast@gmail.com` | Same domain | Do not apply dot-stripping rules across all providers |

**Do not strip dots, plus signs, `+` suffixes, or lowercase local parts globally.** How a provider handles aliases/dots is that provider's own rule, subject to change and inapplicable across all domains. Even when a product knows a provider has special aliasing, account linking still requires ownership verification and security review.

### Email Can Be a Contact Attribute, Not a Permanent Identity Key

An email address can change hands, users can change emails, domains can expire, and email info from an IdP may be unverified. Therefore:

- The internal key for a user should be a stable `user_id`, not email as a business foreign key.
- Do not automatically merge two accounts just because they share an email after a new normalization rule.
- If using email for login/password reset, require **verified email control**, a secure email-change workflow, and duplicate-handling policies.
- With OIDC login, the proper linking identifier usually relies on the `issuer` + `sub` pair; never rely solely on an unverified email claim.
- When changing emails, retain relevant history/metadata per security and privacy requirements while avoiding sensitive data leaks.

### Internationalized Addresses

Real-world emails may include **internationalized domain names (IDN)** and **SMTPUTF8/EAI** with Unicode local parts, as well as quoted local parts per SMTP syntax. A short regex **cannot represent the full email standard**. Production systems should use maintained email-validation libraries, appropriate IDNA processing, and real mail-infrastructure send/receive tests.

For Unicode domains, **IDNA** defines how to represent them in equivalent ASCII form, though standards/algorithms have differences. Do not treat `String.toLowerCase` as a complete IDN solution. The upcoming Java example **deliberately accepts only an ASCII email subset, unquoted local parts, and common domain shapes** to highlight case-sensitivity principles.

## 6. Choosing an Email Login Policy: Document It as a Product Decision

There are three options to distinguish:

| Model | Lookup Key | Consequence |
| --- | --- | --- |
| **Email for contact, username for login** | Login via `username_key`; email stored verbatim with verification status. | Cleanly separates stable internal identity from email delivery, reducing local-part confusion. |
| **Email login preserving local part** | `localOriginal@domainLower`, exact key match. | Respects potentially case-sensitive local parts; users must remember casing when logging in. |
| **Case-insensitive email login by app policy** | `localLower@domainLower` after validation. | Simpler UX, yet risks conflating distinct mailboxes; use only after evaluating providers, verification policy, collisions, and account lifecycle. |

Whichever choice is made must apply **identically** across registration, login, email change, password reset, account search, and unique constraints. Never register with a case-sensitive key while logging in with case-insensitive matching: two accounts `Sales@...` and `sales@...` will cause ambiguous mapping.

If a project already exists, **do not unilaterally alter email case policy** based on a generic "best practice". Analyze existing data, real mailboxes, verification workflows, and collision risk first.

## 7. Standalone Runnable Java 17 Example: Creating Canonical Keys Explicitly

The example below uses **only JDK 17+**, requiring no Spring Boot or external libraries. It demonstrates two intentional policies:

- ASCII-only usernames, **case-insensitive**, stripping leading/trailing whitespace, length 3–30 characters.
- Emails in an **ASCII subset**: preserving local part in `smtpKey` while lowercasing the domain; also outputting `foldedLoginKey` **solely to show collisions if a product opts to ignore local-part case**. Do not use this key to assert two mailboxes are the same.

### 7.1. File `IdentityPolicyDemo.java`

```java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

public final class IdentityPolicyDemo {

    private static final Pattern USERNAME =
            Pattern.compile("[a-z0-9][a-z0-9._-]{2,29}");

    // ASCII subset strictly for demo, not a full RFC email parser.
    private static final Pattern LOCAL =
            Pattern.compile("[A-Za-z0-9_%+-]+(?:\\.[A-Za-z0-9_%+-]+)*");

    private static final Pattern DOMAIN =
            Pattern.compile("[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                    + "(?:\\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}"
                    + "[A-Za-z0-9])?)+");

    private record EmailKeys(
            String original,
            String smtpKey,
            String foldedLoginKey) {
    }

    static String usernameKey(String input) {
        String key = Objects.requireNonNull(input, "username")
                .strip()
                .toLowerCase(Locale.ROOT);

        if (!USERNAME.matcher(key).matches()) {
            throw new IllegalArgumentException("Invalid username");
        }
        return key;
    }

    static EmailKeys emailKeys(String input) {
        String original = Objects.requireNonNull(input, "email").strip();
        int at = original.indexOf('@');

        if (at < 1 || at != original.lastIndexOf('@')
                || at == original.length() - 1) {
            throw new IllegalArgumentException("Invalid email");
        }

        String local = original.substring(0, at);
        String domain = original.substring(at + 1);

        if (original.length() > 254 || local.length() > 64
                || !LOCAL.matcher(local).matches()
                || !DOMAIN.matcher(domain).matches()) {
            throw new IllegalArgumentException("Invalid email");
        }

        String domainKey = domain.toLowerCase(Locale.ROOT);
        return new EmailKeys(
                original,
                local + "@" + domainKey,
                local.toLowerCase(Locale.ROOT) + "@" + domainKey);
    }

    public static void main(String[] args) {
        String first = usernameKey("  LaN_08  ");
        String second = usernameKey("LAN_08");

        System.out.println("username.key=" + first);
        System.out.println("username.sameKey=" + first.equals(second));

        Set<String> uniqueKeys = new HashSet<>();
        System.out.println("username.registerFirst=" + uniqueKeys.add(first));
        System.out.println("username.registerSecond=" + uniqueKeys.add(second));

        EmailKeys mail = emailKeys("Sales@Example.COM");
        System.out.println("email.original=" + mail.original());

        EmailKeys sameLocal = emailKeys("Sales@example.com");
        System.out.println("email.domainEquivalent="
                + mail.smtpKey().equals(sameLocal.smtpKey()));

        EmailKeys differentLocal = emailKeys("sales@example.com");
        System.out.println("email.localPreservedDistinct="
                + !mail.smtpKey().equals(differentLocal.smtpKey()));
        System.out.println("email.optionalFoldCollides="
                + mail.foldedLoginKey().equals(
                        differentLocal.foldedLoginKey()));

        EmailKeys plusAlias = emailKeys("sales+promo@example.com");
        System.out.println("email.plusIsDistinct="
                + !plusAlias.smtpKey().equals(
                        differentLocal.smtpKey()));

        try {
            usernameKey("lan name");
        } catch (IllegalArgumentException ex) {
            System.out.println("badUsernameRejected=true");
        }

        try {
            emailKeys("a@@example.com");
        } catch (IllegalArgumentException ex) {
            System.out.println("badEmailRejected=true");
        }

        System.out.println("passwordCaseSensitive="
                + !"Secret123!".equals("secret123!"));
    }
}
```

### 7.2. Compiling and Running

Save the file above with UTF-8 encoding. In the directory containing the file, using JDK 17+:

```bash
javac -encoding UTF-8 IdentityPolicyDemo.java
java IdentityPolicyDemo
```

**Expected stdout from the program:**

```text
username.key=lan_08
username.sameKey=true
username.registerFirst=true
username.registerSecond=false
email.original=Sales@Example.COM
email.domainEquivalent=true
email.localPreservedDistinct=true
email.optionalFoldCollides=true
email.plusIsDistinct=true
badUsernameRejected=true
badEmailRejected=true
passwordCaseSensitive=true
```

### 7.3. What the Example Actually Proves

1. `LaN_08` and `LAN_08` share `username_key=lan_08` per the application's policy; `HashSet` rejects adding the duplicate key a second time. In a real DB you need a unique constraint rather than relying on `HashSet`.
2. Two emails with **the same local part** and differently cased domains have the same `smtpKey`.
3. `Sales@...` and `sales@...` have different `smtpKey` values because **the local part is preserved**. Whether they actually route to two mailboxes or one is decided by the mail server.
4. `foldedLoginKey` shows that if a product automatically lowercases the whole email, those two strings **collide**. That is an account-identification decision, not a universal truth about mailboxes.
5. `sales+promo@...` and `sales@...` are treated as two distinct local parts under the preservation policy; never assume plus signs are aliases.
6. Usernames with internal spaces and emails with multiple `@` signs are rejected under the **demo subset**.
7. Passwords remain **case-sensitive**. **Never call `strip()`, `toLowerCase()`, or Unicode normalization on passwords** to "match" usernames; transforming secrets alters authentication semantics and can weaken entropy.

**Explicit limitations:** the demo regexes do not accept all RFC-valid emails, quoted local parts, Unicode/SMTPUTF8 emails, internationalized domains, address literals, or complex syntax. They also do not verify MX records, deliverability, or address ownership. Never copy these two `Pattern` fields as production email validation.

## 8. Connecting Username Policy to Spring Security

### 8.1. `UserDetailsService` Is a Critical Boundary

`DaoAuthenticationProvider` calls `UserDetailsService.loadUserByUsername(...)` to load account details. The contract allows implementations to look up by their own case policy, so **the adapter itself must use the exact canonical key chosen by the registration/storage system**.

Example adapter for an application using Spring Data:

```java
// Illustrative snippet, not a standalone runnable Java class.
// Project already defines AccountRepository, Account, and UsernameKeys.
// UsernameKeys.toKey(...) implements the same policy as usernameKey in example 7.
@Service
final class AccountUserDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    AccountUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String enteredUsername) {
        String key = UsernameKeys.toKey(enteredUsername);

        Account account = accounts.findByUsernameKey(key)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Account not found"));

        return User.withUsername(account.usernameDisplay())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .authorities(account.authorities())
                .build();
    }
}
```

Requires Spring imports `@Service`, `UserDetailsService`, `UserDetails`, `User`, `UsernameNotFoundException`, and project types. This is an adapter sketch, not a complete example with schema or repository.

What must remain consistent:

- Registration: compute `username_key` via one canonicalization function.
- Login query: use **the same function** to build the key before calling the repository.
- Username change: check uniqueness by key and update atomically.
- Non-login lookups (forgot password, admin): follow the same policy, without letting responses reveal account existence.
- Cache/identity mapping: key caches by a stable identifier or the same canonical key; do not store `Lan` and `lan` as two cache entries when policy treats them as one.
- Permissions: read authorities from the found account record, **never** from client-sent names/roles.

If `UsernameKeys.toKey` can throw `IllegalArgumentException` on invalid input, the adapter needs a proper handling policy to turn input errors into safe authentication failures—for example, using `UsernameNotFoundException` or validating earlier in a filter/service. Never let arbitrary validation exceptions cause HTTP 500 or leak whether a user exists.

### 8.2. `UserDetailsService` Does Not Decide Case Sensitivity Automatically

In Spring Security, `UserDetailsService` is only a user-reading contract. An in-memory implementation may use lowercase keys, a JPA repository may compare exact strings, and an SQL query with a case-insensitive collation may yield another result. There is no promise that **every `UserDetailsService` implementation is case-insensitive**.

Specifically, `InMemoryUserDetailsManager` in current Spring Security source stores/looks up usernames using `toLowerCase(Locale.ROOT)`. That is convenient for demos, yet switching to a database whose column uses case-sensitive comparison can change login behavior. Therefore, write shared contract tests before swapping stores.

**Do not normalize input strings only inside an HTTP filter.** A user is also looked up across many flows (registration, admin, password reset, integrations) outside the login filter. The rule must live in a shared identity/domain layer and apply consistently on create, update, and lookup.

### 8.3. `getName()` Does Not Necessarily Match Entered Casing

If a request sends username `LAN_08` while `UserDetailsService` returns `UserDetails.username="Lan_08"`, the resulting `Authentication.getName()` may contain `Lan_08`. This is not an authentication failure. The service contract permits implementations to return a username with different casing from the requested string.

Never use `authentication.getName()` as the primary foreign key for data like invoices, documents, or orders; use a stable `user_id` from the principal/domain mapping. If a comparison key is needed, derive it per policy from a trusted source and avoid relying on unverified request spelling.

### 8.4. Email Login Needs Its Own Lookup Strategy

If allowing login by username **or** email, do not naively check "if string contains `@`, lowercase everything" without an email policy.

A possible design:

1. Receive `loginIdentifier` from the filter/form.
2. Classify by defined format/policy.
3. For usernames, compute `username_key` and find the user.
4. For emails, validate input and compute the **published email lookup key**, returning **exactly one user** with a verified email per rules.
5. Load `UserDetails` and let the provider check password hash and account status.
6. If lookup yields 0 or multiple candidates, reject or route to the appropriate handling path—**never pick an arbitrary account yourself**.

In systems allowing email changes or sharing one email across accounts, email may no longer be a unique login key. That calls for a different policy, such as username-only login or an immutable third identifier.

## 9. Database: Unique Constraints Must Live on the Canonical Key

A **classic risk** is checking uniqueness only in Java:

```java
if (!accounts.existsByUsernameKey(key)) {
    accounts.save(new Account(...));
}
```

Two concurrent registration requests can both see "does not exist yet" and both write. Therefore, **service-level checks serve UX; database unique constraints handle race conditions**.

An illustrative schema, without trying to dictate one DBMS's syntax:

```sql
CREATE TABLE app_users (
    user_id        BIGINT PRIMARY KEY,
    username_display VARCHAR(30) NOT NULL,
    username_key     VARCHAR(30) NOT NULL,
    password_hash    VARCHAR(255) NOT NULL,
    email_original   VARCHAR(254),
    email_lookup_key VARCHAR(254),
    email_verified_at TIMESTAMP,
    enabled          BOOLEAN NOT NULL
);

CREATE UNIQUE INDEX ux_app_users_username_key
    ON app_users (username_key);
```

In a specific DBMS, you also need to define `user_id` generation, collation/indexes compatible with canonicalization rules, transactions, charsets, and NULL handling. If the product requires **one verified email per account**, design a unique constraint/index on the email key **matching verified status and NULL behavior** in that exact DBMS. Do not rush to add `UNIQUE(email_original)` if the product does not use email for login or allows unverified emails.

**Why store a key and also watch collation?** Java might normalize `Lan` to `lan`, yet the DB may have a different collation (case/accent-insensitive) causing `lan` and an accented name to collide unexpectedly. Conversely, if lookups are case-insensitive while the unique index uses exact comparison, two accounts can be created and cause login ambiguity.

Test directly against the deployed DB:

- Comparing `Lan`/`LAN` via `username_key` must produce the expected result.
- Concurrent registrations with the same key must yield at most one row.
- `ORDER BY` or search may differ from equality checks in a unique index; never infer one from the other.
- App and DB must agree on encoding, length limits, and diacritic/Unicode rules.
- If the DB supports expression indexes like `lower(username)`, carefully evaluate whether that truly equals **the application's entire canonicalization function**; usually a dedicated canonical column is easier to govern when policies are nuanced.

## 10. Migration: Changing Case Policy Is Not Just One SQL Statement

Suppose a legacy DB has:

| user_id | username_display | new username_key |
| --- | --- | --- |
| 101 | `Lan` | `lan` |
| 207 | `lan` | `lan` |
| 310 | `LAN` | `lan` |
| 420 | `Mai` | `mai` |

If you abruptly create a unique index on `username_key`, the first three rows **collide**. **Never merge users 101, 207, and 310 just because their spellings match after normalization**: they may be separate individuals with distinct data and permissions.

A controlled migration roadmap:

1. **Publish the new policy**: which usernames/emails are accepted, casing, Unicode, diacritic, and whitespace rules.
2. **Backfill into a shadow column**: compute `username_key_v2` for all accounts using the exact same function. Do not use this key for login yet.
3. **Report collisions**: group by the new key, count accounts, and identify independent owners. Never pick a winner automatically.
4. **Resolve valid collisions**: require username changes, create controlled aliases, or run an ownership-verification flow before linking data.
5. **Prevent new collisions**: roll out validation and planned unique constraints/backfills, handling concurrent writes and versioned rollouts across instances.
6. **Bounded dual-read/dual-write** if compatibility is needed: avoid having one instance on the old rule and another on the new rule without reconciliation.
7. **Switch official lookups** once data is clean; add DB uniqueness, monitor login/registration errors, and keep a rollback plan.
8. **Clean up legacy paths** after a transition window and re-verify password reset, external login, cache, audit, and search flows.

With emails, collisions are even more hazardous: `Sales@...` and `sales@...` may be separate mailboxes on the target mail system. **Never merge accounts or reset passwords based on the conclusion that differently cased emails are always identical.** Verify the address and ownership per an evaluated policy.

## 11. Testing Must Cover Both Data and Spring Security

### Canonical Username Test Matrix

| Input | Expected Result Under ASCII-Insensitive Policy |
| --- | --- |
| `Lan_08` | `lan_08` |
| `  LAN_08  ` | `lan_08` |
| `lan_08` | `lan_08` |
| `lan name` | Validation error |
| `ab` | Validation error |
| `lân_08` | Validation error as it is outside the ASCII subset |
| `Ivy` when JVM uses Turkish locale | `ivy` due to `Locale.ROOT` |
| Two requests with same key | Database allows only one record |

### Email Test Matrix

| Input/Comparison | Expectation |
| --- | --- |
| `Sales@Example.COM` vs `Sales@example.com` | Same key if only lowercasing domain. |
| `Sales@example.com` vs `sales@example.com` | Two distinct `smtpKey` values; `foldedLoginKey` collides if product intentionally ignores local case. |
| `sales+promo@example.com` vs `sales@example.com` | Do not auto-merge local parts. |
| Email with multiple `@` | Reject or handle with standards-compliant email parser, never "fix" by deleting characters. |
| IDN/Unicode email | Test with real library/protocol; ASCII regex example intentionally does not support it. |
| Unverified email | Never use directly to authorize password resets or account linking. |

### Spring Security Tests

In integration tests, create two case variants of the same username to prove `UserDetailsService` uses the canonical key:

- Create user with `username_display=Lan_08`, `username_key=lan_08`, and a valid password hash.
- Call `AuthenticationManager.authenticate(...)` with `LAN_08` and the right password: must succeed.
- Call with `lan_08` and a wrong password: must be rejected with `BadCredentialsException`.
- Try registering `LAN_08` when `Lan_08` already exists: unique constraint blocks the new record.
- Verify resulting authorities come from the found account, not from input parameters.
- Concurrently test two registration requests with the same key and verify **only one** commit succeeds.
- When changing email/username, check caches, sessions, and data links by `user_id`; do not alter resource ownership accidentally.

**Never rely on `@WithMockUser` alone to prove login canonicalization.** It creates a mocked authentication for tests and can bypass `UserDetailsService`. To test lookup + password, invoke the real manager/provider or run HTTP filters with form login/Basic under the appropriate configuration. `@WithMockUser` remains useful for authorization checks, yet answers a different question.

### Special Tests for Internationalization

If the app supports Unicode usernames, add tests for NFC vs. combining marks, Turkish I variants, Greek sigma, German sharp S, lookalike characters across scripts, and invisible formatting characters. Pick **one** outcome per product policy, pin the normalization version, and verify across every read/write path. Avoid assuming a single `toLowerCase(Locale.ROOT)` unit test proves Unicode case folding is safe.

## 12. Passwords Are Credentials, Not Identifiers

A mistake that happens easily when applying one normalization rule to every field on a login form:

```java
// WRONG: do not normalize passwords like usernames.
String username = submittedUsername.strip().toLowerCase(Locale.ROOT);
String password = submittedPassword.strip().toLowerCase(Locale.ROOT);
```

**Passwords must follow the credential contract**—never arbitrarily strip, lowercase, or apply normalization that the system has not defined in its password policy. If a user sets password `Secret123!`, normally `secret123!` must be a different secret.

With Spring Security:

- `UserDetailsService` finds the user using the policy-normalized identifier.
- `DaoAuthenticationProvider` uses `PasswordEncoder.matches(rawPassword, encodedPassword)` to compare the exact raw password against the stored hash.
- Password hashing requires an appropriate algorithm such as BCrypt/Argon2 per policy; never write plaintext to the database.
- Never log raw passwords, request bodies, authorization headers, or full authentication tokens.

For login APIs, "username not found" and "wrong password" should normally receive controlled external messages to avoid enumeration. Detailed validation can appear in **username registration** flows, yet login endpoints must not accidentally reveal whether an account exists via responses, timing, or status codes.

## 13. Common Design Mistakes

1. **Lowercasing usernames at login without lowercasing at registration.** Creates inconsistent data and lookup collisions.
2. **Calling `toLowerCase()` without `Locale.ROOT` for locale-neutral keys.** Can diverge across JVMs/locales.
3. **Believing Spring Security requires all user stores to be case-insensitive.** `UserDetailsService` leaves that decision to the implementation.
4. **Confusing `InMemoryUserDetailsManager` with a production database.** The demo manager's lookup behavior may differ from real JPA/SQL queries.
5. **Using `equalsIgnoreCase` as a comprehensive Unicode identity standard.** It does not replace canonical Unicode policies, full case folding, and confusable checks.
6. **Applying `NFKC` unconditionally to "fix" all characters.** Can cause distinct identifiers to collide; resolve collisions first.
7. **Lowercasing entire emails and claiming SMTP forces all local parts to be identical.** Domains are case-insensitive, while local parts must be preserved in transit.
8. **Stripping dots/plus signs from all emails because one provider has special aliasing.** Can merge two unrelated mailboxes.
9. **Storing email as the primary foreign key for orders.** Emails change; use a stable `user_id`.
10. **Using unverified emails to reset passwords or link SSO.** Risks account takeover via forged claims or data.
11. **Calling `existsByUsernameKey` before insert without a unique index.** Leaves a race condition under concurrent registration.
12. **Not checking DB collation.** DB equality/uniqueness rules can differ from Java normalization.
13. **Changing production normalization algorithms without checking collisions.** Can cause multiple legacy accounts to share a key or keys to shift.
14. **Automatically merging two legacy accounts after seeing the same canonical key.** There is no proof they belong to one person; linking data can become a severe vulnerability.
15. **Normalizing passwords like usernames.** Alters credentials, breaks hash checks, and reduces predictability.
16. **Trusting client-sent names to decide permissions.** Permissions must come from the provider-authenticated record.
17. **Matching display names to check resource ownership.** Use stable identifiers rather than capitalization or emails.
18. **Testing with mock users and concluding lookup and canonicalization work.** Mocks usually bypass the password provider and real user store.
19. **Dropping casing of `email_original` when saving.** Can break delivery to servers with case-sensitive local parts.
20. **Changing algorithms without versioning/rollout.** Multiple services concurrently running different versions can turn the same name into two keys.

## 14. Self-Check Questions

**Question 1.** An app allows both `Lan` and `lan` during registration, yet login calls `toLowerCase(Locale.ROOT)` before lookup. What is the problem?

**Answer:** Two different accounts can map to the same `lan` key at login, leading to ambiguous lookups or the wrong account. Define the same policy across registration, unique indexes, and authentication; resolve legacy data collisions before switching.

**Question 2.** Why can `Sales@Example.COM` normalize its domain to `Sales@example.com`, yet not default to `sales@example.com`?

**Answer:** Domains are case-insensitive per DNS. Local parts per SMTP must preserve casing; some mail servers distinguish `Sales` and `sales`. Lowercasing the whole address is a login policy trade-off, not a universal mail-delivery rule.

**Question 3.** `UserDetailsService.loadUserByUsername("LAN_08")` returns a user with `getUsername()=="Lan_08"`. Is that an API violation?

**Answer:** No. The API permits implementations to search case-insensitively and return a username with different casing from the input.

**Question 4.** Why is a unique constraint on `username_key` still needed when the service already checks for duplicate names?

**Answer:** Two transactions can both pass the check before inserting. The unique constraint handles the race; the service must catch and translate the error properly.

**Question 5.** Should `toLowerCase(Locale.ROOT)` be used on passwords?

**Answer:** No. Usernames and passwords serve different roles. Passwords must be verified accurately with `PasswordEncoder.matches(...)` without altering characters arbitrarily.

**Question 6.** A system has `user_id=101, username=Lan` and `user_id=207, username=lan`. When switching to case-insensitive, should they be merged automatically?

**Answer:** No. You need collision detection and a verification/rename workflow, preserving each account's data and permissions.

**Question 7.** An OIDC login returns an email matching an address already in the DB. Can the session be automatically attached to that account?

**Answer:** Not automatically. Check `email_verified`, issuer, `sub`, and account-linking policy. Email alone is neither an immutable identifier nor proof of long-term ownership.

**Question 8.** Why does a test using `@WithMockUser` not prove username normalization in `UserDetailsService`?

**Answer:** Mocks construct an `Authentication` for testing without necessarily running lookup or password validation. You need integration tests invoking the provider or HTTP security filter chain.

## 15. Reference Documentation

- [Spring Security — UserDetailsService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html): username lookup contract allowing case-sensitive or case-insensitive implementations.
- [Spring Security — InMemoryUserDetailsManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/provisioning/InMemoryUserDetailsManager.html): in-memory user store; demo behavior does not replace DB policies.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): loading users from `UserDetailsService` and checking credentials.
- [RFC 5321 — Simple Mail Transfer Protocol, Section 2.4](https://www.rfc-editor.org/rfc/rfc5321#section-2.4): case-insensitive domains; local parts must preserve casing.
- [Oracle Java 17 — String.toLowerCase(Locale)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#toLowerCase(java.util.Locale)): avoiding default locale dependence by choosing `Locale.ROOT`.
- [Oracle Java 17 — java.text.Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode NFC/NFKC and normalization scope.
- [RFC 6531 — SMTP Extension for Internationalized Email](https://www.rfc-editor.org/rfc/rfc6531): internationalized local parts and limits of the ASCII example.

**Key takeaway:** usernames can be normalized according to the application's own policy, yet **an email is not simply a username with an `@` sign**. Pick a stable canonical key, preserve necessary contact data, enforce uniqueness in the database, resolve collisions before migrating, and apply the same policy in `UserDetailsService` as well as all registration/update entry points. Passwords and the internal `user_id` identifier are two separate domains: never transform passwords by username rules, and never use spelling/email in place of an immutable user key.