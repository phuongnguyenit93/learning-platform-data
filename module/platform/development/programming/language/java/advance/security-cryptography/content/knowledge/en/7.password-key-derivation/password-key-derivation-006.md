# 7.6. Calibrating Computational Cost and Upgrading Parameters on Re-authentication

## Objectives and context

In a password authentication system, `password hashing` or a **password-based key derivation function (KDF)** transforms a password into a verification value with a salt and significant computational cost. An attacker holding a copy of the database can try guessing passwords **offline**; making every guess consume CPU, RAM, and time raises the cost of an attack. Conversely, the server side must remain fast enough that legitimate logins do not bottleneck and the KDF does not become a denial-of-service vector.

Computational cost must be **measured, calibrated, and increased over time** alongside hardware advances and threat changes. NIST SP 800-63B recommends choosing the highest cost compatible with verifier performance and increasing it as computing power evolves. OWASP recommends dedicated algorithms such as Argon2id, scrypt, or PBKDF2 depending on constraints.

After this lesson, you will be able to:

1. Distinguish the cost parameters of **Argon2id**, **scrypt**, **bcrypt**, and **PBKDF2**, as well as their effects on CPU/RAM/latency.
2. Design a **benchmark on target hardware and realistic load**, using p50/p95/p99 latency, concurrent authentications, memory, and anti-abuse limits.
3. Store **algorithm, version, parameters, salt, and hash** per account to support verifying legacy records.
4. Execute **verify with old parameters first; rehash with new parameters after the password matches**, using a fresh salt and atomic update.
5. Handle long-inactive accounts, algorithm migrations, concurrent password changes, and deployment incidents.

The code uses **Java 17+** with `PBKDF2WithHmacSHA256` from JCA so it runs directly on the JDK. This teaches the entire calibration and upgrade flow; if choosing Argon2id for production, use a maintained and vetted library rather than implementing cryptographic algorithms yourself.

## 1. Why not use a fixed work factor forever?

Human-chosen passwords typically have lower entropy than random keys. A unique salt prevents reusing precomputed hash tables across accounts, yet **does not** stop guessing individual passwords after a database leak. A KDF raises the cost of every guess, especially with memory-hard algorithms.

Suppose a configuration yields an acceptable authentication time today. As attacker hardware speeds up, that old configuration becomes cheaper for an attacker; meanwhile, your servers may have more capacity to raise cost. Therefore, store **per-hash parameters** and plan to **upgrade when users log in successfully**, rather than assuming every record always uses the current policy.

Three concepts to distinguish:

- **Password verification:** from the password entered by the user, compute the KDF using the **stored record's parameters and salt**, and compare against the stored hash.
- **Cost calibration:** benchmark candidate configurations on the target environment to pick parameters within your latency, CPU, memory, and attack-resistance budgets.
- **Rehash-on-login (opportunistic upgrade):** after a **successful authentication under an older configuration**, use the newly entered password to compute a new hash with a fresh salt and the new policy; save it only if the stored record is still the old one.

**You cannot** directly convert an existing PBKDF2/Argon2id hash to stronger parameters merely by editing the round count or “re-hashing the old hash” and treating the result as a standard password hash. Verification requires the original password (or a specially designed conversion protocol); only upon a successful login do you have the entered password available to rehash. Never store plaintext passwords waiting for migration.

## 2. Understanding “cost” per algorithm

| Algorithm | Core parameters | Primary resource / characteristics | When to consider |
| --- | --- | --- | --- |
| **Argon2id** | `m`: memory in KiB; `t`: passes; `p`: lanes/parallelism | **Memory-hard**, makes mass guessing expensive in RAM and memory bandwidth; balances time/memory | Preferred for new systems if a trusted library is available and compliance permits. |
| **scrypt** | `N`: CPU/memory cost; `r`: block size; `p`: parallelization | Uses CPU and memory; must account for RAM pressure under concurrent requests | Memory-hard option when suitable Argon2id is unavailable. |
| **bcrypt** | `cost` (logarithmic work factor) | Primarily CPU-bound; raising cost by 1 roughly doubles work | Existing systems; watch input limits (commonly 72 bytes), encoding, and migration. |
| **PBKDF2-HMAC-SHA256** | `iterations`, output bits, salt | Primarily CPU-bound, **not memory-hard** | Needed for built-in JCA availability or FIPS-compliant environments. |

**Do not compare work-factor numbers across algorithms as if they share the same unit.** For example, `600000` PBKDF2 iterations is not equivalent to `t=600000` in Argon2id. In Argon2id, `m` is **total memory per hash operation**, not multiplied directly by `p`; `p` is internal parallelism and must not be interpreted as “iteration count.” Actual resource formulas depend on the library and runtime machine.

Current starting baselines cited in OWASP's *Password Storage Cheat Sheet* (recheck current documentation at deployment time):

- **Argon2id:** e.g., `m=19456 KiB` (19 MiB), `t=2`, `p=1`; OWASP also lists alternative m/t combinations offering equivalent defense by their assessment.
- **PBKDF2-HMAC-SHA256:** reference recommendation of **600,000 iterations**; worth considering when PBKDF2/FIPS deployment is needed.
- **bcrypt:** minimum cost 10 under current guidance, while evaluating password length limits and application specifics.
- **scrypt:** reference settings such as `N=2^17, r=8, p=1` or equivalent options in the guidance.

**These are not “guaranteed secure configurations” merely by copying numbers.** Check the current guidance version, real load capacity, upgradability, FIPS status of *your specific implementation*, and risk profile. Java 17 includes `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")`, yet **has no standard Argon2id engine in core JCA**; using Argon2id requires an appropriate library/provider.

## 3. Self-describing, versioned record model

A password record needs enough metadata to verify even after default policy changes:

```text
algorithm | formatVersion | parameters | salt | derivedHash | optionalPepperKeyId
```

Example string layout stored in a database (illustrative format only):

```text
pbkdf2-sha256$v1$600000$<salt_base64url>$<hash_base64url>
```

In the Java code at the end of this lesson, `$` separates fields and `v1` marks the **record format version**; it is not the PBKDF2 algorithm version. You may use separate table columns instead of a single string; for Argon2id, prefer a standard format such as **PHC string** if your library supports it. Never silently alter field ordering or meaning on legacy records.

Store:

- **Algorithm/version:** selects the right verifier, preserves compatibility, and rejects unsupported formats.
- **Parameters per record:** for PBKDF2, `iterations` and output length; for Argon2id, `m, t, p`, algorithm version, and output length per format.
- **Unique random salt per hash creation:** e.g., **16 bytes (128 bits)** from `SecureRandom`, not needing secrecy. Generate a **fresh salt** when upgrading; never share a static salt across accounts.
- **Derived hash:** store bytes in Base64/hex; **never** store the password, and never log passwords or raw password-derived keys.
- **Pepper (if used):** a shared or centrally managed secret—**never** place the secret value next to database hashes; store at most a key ID/version, manage the secret in KMS/HSM, and design a separate pepper rotation workflow.

Having a random salt **does not** let you skip rate limiting. Rate limiting defends online authentication; the KDF slows offline testing after a data breach. They address two different attack surfaces.

### Bounds are mandatory when decoding records

Parameters in the database may be corrupted or untrusted (e.g., broken account imports or database compromise). **Never** parse `iterations` or `m` from a string and unconditionally allocate gigabytes of RAM or minutes of CPU.

- Accept only a known **allowlist of algorithms and versions**.
- Validate format, string length, Base64, salt, hash output length, and min/max bounds on iterations/`m`/`t`/`p` before running the KDF.
- Enforce a reasonable password input length limit to reduce DoS risk without silently truncating passwords; maintain consistent input and Unicode/encoding policy.
- When tightening policy, expand **valid hash verification bounds** deliberately so existing users are not locked out.
- Corrupted records must **fail closed**, log errors without leaking sensitive data, and follow a proper recovery/reset flow.

## 4. Build a performance budget before raising cost

Single-hash latency on a developer laptop does not directly reflect thousands of concurrent logins in production. A calibration process should follow these steps:

1. **Define the login endpoint budget:** e.g., total p95 latency target, success rate, dedicated CPU/RAM SLOs, and behavior under traffic spikes. These are product targets, **not** fixed numbers dictated by Java.
2. **Measure the current baseline:** user distribution across algorithms/parameter versions; verify p50/p95/p99; CPU, RSS/memory, GC, queue time, throughput, and concurrent authentications per instance; separate pure KDF time from full request time.
3. **Select candidate configs** based on security guidance and infrastructure limits. For Argon2id, evaluate **`m` × concurrent KDFs** plus overhead memory; for PBKDF2, focus on CPU time and worker/thread counts.
4. **Warm up before measuring:** run on the production-equivalent JDK/provider/library, container CPU quota, RAM limit, machine architecture, and GC configuration. Take multiple samples and exclude startup/JIT warmup from steady-state measurements.
5. **Load test concurrently** with realistic valid/invalid login ratios, busy tenants, traffic bursts, signups/password changes, and accounts needing rehash. Test under resource constraints: verify queues/backpressure and rate limits prevent system collapse.
6. **Pick a configuration strong enough with headroom** for peak traffic; measure allocation churn and failure overhead. Put policy parameters/versions in versioned config, run canary rollouts, and monitor before full deployment.
7. **Review periodically** when hardware/JDK/providers change, new compliance rules arrive, throughput grows, or security guidance updates.

Illustrative memory-pressure math: if one Argon2id call requires roughly **19 MiB**, dozens of concurrent computations can consume hundreds of MiB just for KDF working memory, excluding heap, native overhead, and other tasks. Increasing `p` does not guarantee better p95 latency: it can cause more cores to contend for resources. Measure under realistic concurrency.

**Never take the p95 of 11 single-threaded hashes as your service's p95 under load.** Microbenchmarks filter candidates; load tests reveal queuing, scheduling, contention, memory pressure, and rate-limiting behavior.

### Calibration results log table

| Candidate config | p50 KDF | p95 KDF | p95 login end-to-end | Peak CPU/RAM | Throughput/queue | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| Active policy | Measure | Measure | Measure | Measure | Measure | Baseline |
| Proposed config A | Measure | Measure | Measure | Measure | Measure | Accept/reject with rationale |
| Proposed config B | Measure | Measure | Measure | Measure | Measure | Accept/reject with rationale |

This table is solely a template for recording **values you must measure yourself**, not fabricated experimental data.

## 5. Java 17: microbenchmarking a PBKDF2 candidate

Save **`Pbkdf2CostBench.java`**:

```java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class Pbkdf2CostBench {
    private Pbkdf2CostBench() {}

    private static byte[] run(SecretKeyFactory factory, char[] password,
            byte[] salt, int iterations) throws Exception {
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, 256);
        try {
            return factory.generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java Pbkdf2CostBench <iterations>");
            return;
        }
        int iterations = Integer.parseInt(args[0]);
        if (iterations < 1_000 || iterations > 2_000_000) {
            throw new IllegalArgumentException("Iterations outside benchmark guardrails");
        }

        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        char[] password = "benchmark-only-password".toCharArray();
        SecretKeyFactory factory =
                SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
        try {
            for (int i = 0; i < 3; i++) {
                byte[] hash = run(factory, password, salt, iterations);
                Arrays.fill(hash, (byte) 0);
            }
            long[] elapsed = new long[11];
            for (int i = 0; i < elapsed.length; i++) {
                long begin = System.nanoTime();
                byte[] hash = run(factory, password, salt, iterations);
                elapsed[i] = System.nanoTime() - begin;
                Arrays.fill(hash, (byte) 0);
            }
            Arrays.sort(elapsed);
            System.out.printf(
                    "iterations=%d samples=%d p50Ms=%.2f p95Ms=%.2f%n",
                    iterations, elapsed.length,
                    elapsed[elapsed.length / 2] / 1_000_000.0,
                    elapsed[(int) Math.ceil(0.95 * elapsed.length) - 1]
                            / 1_000_000.0);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 Pbkdf2CostBench.java
java Pbkdf2CostBench 10000
java Pbkdf2CostBench 600000
```

Output format:

```text
iterations=<rounds> samples=11 p50Ms=<measured_ms> p95Ms=<measured_ms>
```

The line above is an **output template**, not fixed numerical stdout: timings depend on CPU, JDK, provider, JIT, load, thermals, and container limits. `samples=11`, `p50Ms`, and `p95Ms` come from 11 sorted samples (nearest-rank p95). The program runs 3 warmup rounds and 11 single-threaded measurements; it is a quick check, **not sufficient** by itself to decide production policy.

**Code explanation:** `SecretKeyFactory` provides PBKDF2-HMAC-SHA256. `PBEKeySpec` holds password, salt, iteration count, and **256-bit** output length; `clearPassword()` attempts to clear its internal copy after use. Results are wiped from the temporary array immediately after measurement to limit sensitive data lingering on the heap. The demo password is a constant for repeatable tests; never use real passwords when benchmarking. The 10,000-round test is only for a fast trial run, **not a policy for storing new passwords**.

When evaluating real Argon2id/scrypt, keep the same warmup and multi-sample discipline, but always benchmark using **the actual chosen algorithm library**, with real `m, t, p` and server native memory limits. Never extrapolate Argon2id timings from PBKDF2 timings.

## 6. When must a hash be upgraded?

Separate **new hash creation policy** from **legacy hash verification**:

- **Current policy** specifies algorithm, version, minimum cost, salt length, output length, and constraints for *new credentials*.
- **Legacy verifier** still understands permitted legacy formats/algorithms using **the record's own metadata**, never arbitrarily applying new cost to verify an old hash.
- **`needsRehash(record, policy)`** returns true when algorithm/version is outdated or parameters fall below current policy under *algorithm-specific evaluation*. Never compare a single generic cost number across bcrypt/PBKDF2/Argon2id.
- Never automatically “downgrade” a record with stronger parameters than current policy; define an explicit migration policy when switching algorithms.

State examples:

| Stored record | Entered password | Verify result | Action |
| --- | --- | --- | --- |
| PBKDF2 12,000 rounds | Correct | PASS at 12,000 rounds | Generate fresh salt, rehash under new policy, update in controlled fashion. |
| PBKDF2 12,000 rounds | Wrong | FAIL | Reject; **do not rehash** or alter parameters. |
| PBKDF2 600,000 rounds | Correct | PASS | Log in; do not rehash if compliant and algorithm unchanged. |
| Unsupported record version | Any | No valid verifier | Fail closed and handle via authenticated recovery; do not guess parameters. |
| Two concurrent logins | Both match initial snapshot | Both PASS verify | Only one compare-and-set update wins; the other must check the new state. |
| Password reset wins before update | Old password verified on stale snapshot | Race condition | CAS fails; verify against new credential, never overwrite the password reset. |

**Upgrading on re-authentication** is usually transparent to the user: the password stays the same while salt/hash/cost update. However, account for the cost of **old verify + new rehash** during that login, since two KDF runs execute. If many legacy hashes exist, plan capacity and apply dedicated concurrency limits.

### Authentication and upgrade flow

```text
Receive password over protected channel
          |
          v
Load credential record + version
          |
          v
Validate format/algorithm/cost within allowed bounds
          |
          v
KDF(password, old salt, old params)
          |
          v
Compare result without byte-level timing leaks
          |
        Match?
       /      \
     No        Yes
      |         |
   Reject    needsRehash?
               /      \
             No        Yes
              |         |
            Login    Fresh salt + new policy KDF
                        |
                   Atomic CAS/UPDATE
                        |
             On conflict: reload record
             and verify against current credential
```

A common design bug is **creating a “new hash” by editing cost while keeping the old derived hash**, or **rehashing on every login even when already compliant**, wasting resources. Another bug is **rehashing before verifying**, which overwrites a user's credential on a wrong password attempt.

## 7. Java 17: complete verify-then-atomic-upgrade example

`PasswordUpgradeDemo` stores a `pbkdf2-sha256$v1$iterations$salt$hash` string inside an `AtomicReference` to simulate **a single database row**. The example defines two policies:

- `OLD_WORK = 12000`: simulates a **weak legacy record**, intentionally used solely for learning, not a production recommendation.
- `CURRENT_WORK = 600000`: illustrates a new policy aligned with current OWASP PBKDF2-HMAC-SHA256 reference levels. In real systems, **benchmark and externalize configuration** rather than hardcoding indefinitely.

Save **`PasswordUpgradeDemo.java`**:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.concurrent.atomic.AtomicReference;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordUpgradeDemo {
    private static final String ID = "pbkdf2-sha256";
    private static final String VERSION = "v1";
    private static final int OLD_WORK = 12_000;
    private static final int CURRENT_WORK = 600_000;
    private static final int MAX_ACCEPTED_WORK = 2_000_000;
    private static final int SALT_SIZE = 16;
    private static final int HASH_SIZE = 32;
    private static final SecureRandom RNG = new SecureRandom();
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DECODER = Base64.getUrlDecoder();

    private record Stored(int work, byte[] salt, byte[] hash) {}
    private record LoginResult(boolean authenticated, boolean upgraded) {}

    private static byte[] pbkdf2(char[] password, byte[] salt, int work)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, work, HASH_SIZE * 8);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    private static String encode(char[] password, int work)
            throws GeneralSecurityException {
        byte[] salt = new byte[SALT_SIZE];
        RNG.nextBytes(salt);
        byte[] hash = pbkdf2(password, salt, work);
        try {
            return String.join("$", ID, VERSION, Integer.toString(work),
                    ENCODER.encodeToString(salt),
                    ENCODER.encodeToString(hash));
        } finally {
            Arrays.fill(hash, (byte) 0);
        }
    }

    private static Stored parse(String encoded) {
        if (encoded == null || encoded.length() > 256) {
            throw new IllegalArgumentException("Invalid credential record");
        }
        String[] f = encoded.split("\\$", -1);
        if (f.length != 5 || !ID.equals(f[0]) || !VERSION.equals(f[1])
                || !f[2].matches("[1-9][0-9]{0,6}")) {
            throw new IllegalArgumentException("Unsupported credential format");
        }
        int work = Integer.parseInt(f[2]);
        if (work > MAX_ACCEPTED_WORK) {
            throw new IllegalArgumentException("Unsupported work factor");
        }
        byte[] salt = DECODER.decode(f[3]);
        byte[] hash = DECODER.decode(f[4]);
        if (salt.length != SALT_SIZE || hash.length != HASH_SIZE) {
            throw new IllegalArgumentException("Invalid salt or hash size");
        }
        return new Stored(work, salt, hash);
    }

    private static boolean matches(char[] password, Stored stored)
            throws GeneralSecurityException {
        byte[] candidate = pbkdf2(password, stored.salt(), stored.work());
        try {
            return MessageDigest.isEqual(stored.hash(), candidate);
        } finally {
            Arrays.fill(candidate, (byte) 0);
        }
    }

    private static LoginResult signIn(AtomicReference<String> account,
            char[] password) throws GeneralSecurityException {
        String observed = account.get();
        Stored stored = parse(observed);
        if (!matches(password, stored)) {
            return new LoginResult(false, false);
        }
        if (stored.work() >= CURRENT_WORK) {
            return new LoginResult(true, false);
        }

        String replacement = encode(password, CURRENT_WORK);
        if (account.compareAndSet(observed, replacement)) {
            return new LoginResult(true, true);
        }

        // A concurrent change (including password reset) may have won.
        // Re-verify current state instead of trusting a stale password.
        return new LoginResult(matches(password, parse(account.get())), false);
    }

    public static void main(String[] args) throws Exception {
        char[] password = "example-only-password".toCharArray();
        char[] wrong = "incorrect".toCharArray();
        try {
            AtomicReference<String> row =
                    new AtomicReference<>(encode(password, OLD_WORK));
            Stored before = parse(row.get());
            System.out.println("oldWork=" + before.work());

            LoginResult first = signIn(row, password);
            Stored after = parse(row.get());
            System.out.println("authenticated=" + first.authenticated());
            System.out.println("upgraded=" + first.upgraded());
            System.out.println("newWork=" + after.work());
            System.out.println("freshSalt=" +
                    !Arrays.equals(before.salt(), after.salt()));
            System.out.println("upgradeAgain=" + signIn(row, password).upgraded());
            System.out.println("wrongPasswordAccepted=" +
                    signIn(row, wrong).authenticated());
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 PasswordUpgradeDemo.java
java PasswordUpgradeDemo
```

**Exact stdout on a normal run:**

```text
oldWork=12000
authenticated=true
upgraded=true
newWork=600000
freshSalt=true
upgradeAgain=false
wrongPasswordAccepted=false
```

Even though `SecureRandom` creates a different salt on each run, the program only prints **logical outcomes**, so stdout does not depend on the salt bytes. Collision probability for 16-byte random salts is tiny; the demo compares salts to show a fresh salt was created, not as a mathematical proof of zero collisions.

### Key points to study in the code

1. **Creating a hash:** `encode` generates a **16-byte random salt**, derives a 256-bit output with PBKDF2-HMAC-SHA256, and stores algorithm/version/work/salt/hash in the agreed order. Salt and hash are Base64URL-encoded. `String.join` only joins metadata fields and holds no password.
2. **Validated parsing:** `parse` accepts only allowed format/algorithm/version, bounded iterations, 16-byte salt, and 32-byte hash. `MAX_ACCEPTED_WORK` blocks abnormal records from exhausting CPU; every real policy change must update guardrails deliberately. In larger systems with multiple algorithms, dispatch explicitly via an allowlist and matching verifier.
3. **Verify with exact legacy parameters:** `matches` invokes PBKDF2 using `stored.work()` and `stored.salt()`—the **stored record's parameters**, never `CURRENT_WORK` for an old hash. `MessageDigest.isEqual` compares byte arrays; never use `==` on arrays.
4. **Never upgrade on failure:** `signIn` immediately returns `authenticated=false, upgraded=false` on mismatch; no new salt/hash is created.
5. **Upgrade at the right time:** only when the password is valid and `work < CURRENT_WORK` does `encode(password, CURRENT_WORK)` generate a **new hash + fresh salt**. If work already meets/exceeds policy, avoid pointless rehashing.
6. **Prevent blind overwrites:** `compareAndSet(observed, replacement)` succeeds only if the record is still the snapshot just verified. If a concurrent change (including a password reset) occurred, the demo **re-reads and verifies against the current state** before permitting login. This simulates CAS logic, not a full database transaction mechanism.
7. **Minimize password retention:** `PBEKeySpec.clearPassword()` clears the internal copy; `Arrays.fill(password, '\0')` clears the demo input array at the end. When applications receive passwords via `String`/HTTP bodies, not all immutable copies can be guaranteed erased; minimize logging, copying, and secret lifetime.

**About benchmarking:** 600,000 rounds in the demo can take different durations across machines. Use it to understand the migration flow and verify APIs; measure real load using sections 4–5 before going to production.

## 8. Bringing compare-and-set to the database and avoiding races

`AtomicReference` only simulates one account in a single process. Real systems require **conditional updates** in the database. Illustrative SQL pattern:

```sql
UPDATE accounts
SET password_record = :new_record,
    credential_version = credential_version + 1
WHERE id = :account_id
  AND credential_version = :version_read
  AND password_record = :old_record;
```

Mark the upgrade successful only when **affected rows = 1**. If affected rows = 0, the row was changed (by a rehash from another login, password change, or reset) or deleted. **Never** run an unconditional `UPDATE` using the old password; reload and handle appropriately. A successful password reset must never be overwritten by an earlier rehash flow.

Note: matching the full `password_record` string may be suboptimal or awkward in some schemas; use **`credential_version`** and optimistic locking/transaction isolation designed for your real system. If one flow could still issue a session from an older snapshot right during a password reset, define **session revocation** and auth/credential write coordination separately outside this minimal example.

There are two upgrade timing strategies:

- **Synchronous during login:** straightforward, with guaranteed migration status before responding, though legacy logins pay **old verify + new hash**. Set appropriate budgets/timeouts.
- **Offload to an internal job after verify:** only while the password stays within the operation's secure control boundary; avoid putting plaintext passwords into queues, logs, events, or databases. In many systems, not sending passwords to background queues is simpler and safer.

Never treat a legacy record as upgraded merely because verification passed. **Confirm the `UPDATE` succeeded**, while continuing to support legacy verifiers for remaining records during migration.

## 9. Rolling out upgrades system-wide

### Versioned policy and rollout

1. Create **new records under current policy** for registrations and password changes from rollout onward.
2. Continue **verifying legacy hashes with their exact legacy parameters** for accounts still permitted to log in.
3. After successful verification, if policy indicates migration is needed, **rehash with a fresh salt** and commit with CAS.
4. Track the share of hashes per algorithm/params/version and upgrade success/failure counts **without logging passwords/hashes/salts**. Record aggregate metrics, latency, overload, and format parse errors.
5. Under CPU/memory pressure, shed KDF load via rate limits, admission control, bounded queues, and verified autoscaling; consider staged rollouts or deferring non-urgent migrations per policy. **Never** silently lower new credential cost to mask resource bugs.
6. Once the legacy share is low, decide a retirement cutoff balancing risk and user impact; accounts that have not logged in for long periods need an **authenticated password reset flow**, as old hashes cannot have iterations increased without plaintext.
7. Ensure application rollbacks can still **read new records** if rollback is a realistic possibility; deploy verifiers supporting the new version **before** writing new hashes.

### Switching algorithms, not just raising iterations

Moving from PBKDF2 to Argon2id is an **algorithm migration**: the verifier recognizes PBKDF2 records and validates them; on success, the Argon2id library creates a new **PHC** record with `m`/`t`/`p` and a fresh salt. Never treat PBKDF2 `iterations` and Argon2id `t` as the same metric. A system may retain multiple verifiers during transition, while **only one policy creates new hashes**.

For legacy bcrypt systems, watch the **72-byte limit** and how the old system handled Unicode or long passwords; changing encoding arbitrarily can lock out previously valid passwords. When migrating algorithms, test non-ASCII and long passwords against legacy verifiers.

### When a pepper is used

A pepper adds a layer of defense when database hashes leak while external secrets stay safe; rotating a pepper may require **verifying with the old pepper key ID and creating a new record with the new pepper** or a reset flow. Never store plaintext peppers next to the DB and never treat adding a pepper as a substitute for salt/work factor. Design failure modes when HSM/KMS is unavailable, access auditing, rotation, key identifiers, and handling inactive accounts.

## 10. Risks from abuse and untrusted data

As cost rises, each valid login request consumes more resources; attackers can target this endpoint for **CPU/RAM exhaustion**. Consider layered defenses:

- **Per-account and per-source rate limiting**, credential-stuffing detection, appropriate throttling, and recovery endpoint protection. Avoid side channels that allow user enumeration via distinct errors or glaring timing differences.
- **Bounded concurrency**: permit only as many concurrent KDF runs as RAM/CPU safely support; bound queues and timeouts. For Argon2id, measure native memory alongside heap/container memory.
- **Parameters from records must be validated**: never allow an account row to request huge iterations or `m=GiB`, and never let attackers pick arbitrary algorithms in systems accepting external input.
- **Password input length**: allow long passphrases per policy, yet set a reasonable ceiling and test PBKDF2/long-password behavior to prevent abnormal processing costs. Never silently truncate passwords.
- **When a user does not exist**, avoid leaking existence via responses and timing. One option is running a dummy KDF under appropriate policy on the miss path; factor its cost into capacity planning and pair with rate limiting. The goal is consistent observable behavior, not promising mathematically flat timing.
- **Do not optimize with fast hashes** like SHA-256/MD5 for password storage. Fast hashes fit other problems, yet make offline guessing trivial.
- **Invalid inputs, unsupported versions, and corrupted records** must fail closed with user-support workflows, never silently falling back to weak algorithms.

Note on **repeated user failures**: always verify passwords with the KDF for existing accounts with valid records, paired with rate limits/lockouts designed to resist account-lockout DoS; never allow bypassing the KDF via a separate “fast” path.

## 11. Common mistakes and fixes

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Raising iterations in config and using the new value to verify all old hashes | Stored hashes were computed with old iterations; valid logins fail | Verify using **each record's own metadata**. |
| Rehashing the old hash instead of the password | Result does not equal `KDF(password, fresh salt, new params)` | Rehash only after verifying the right password while it is still in the request. |
| Rehashing before checking the password | Overwrites credentials on wrong-password requests | Verify first, then create the new record. |
| Reusing old salt or sharing one salt | Weakens independence across records/hashes | Fresh random salt for every new hash/upgrade. |
| Omitting algorithm/version/params | Cannot read legacy hashes after policy changes | Self-describing format with a migration path. |
| Accepting unbounded cost from DB | CPU/RAM DoS on corrupted or tampered records | Guardrails and allowlists for algorithms and versions. |
| Using `Arrays.equals` on hashes and assuming constant-time | Lacks proper timing guarantees | Use library verify primitives or `MessageDigest.isEqual` with validated lengths. |
| Granting authorization from an old snapshot after a concurrent password reset | May accept superseded credentials | CAS, re-check on conflict, and define session revocation. |
| Unconditional `UPDATE` after login | Overwrites password resets / concurrent migrations | Optimistic locking on credential version/record. |
| Rehashing every login | Wastes CPU/RAM unnecessarily | Only when `needsRehash` is true; avoid downgrades. |
| Adding Argon2id and immediately disabling the PBKDF2 verifier | Legacy accounts cannot log in | Deploy verifiers supporting both old and new before writing new hashes. |
| “Benchmarking” with one local request | Ignores p95/p99, queues, CPU quotas, native memory | Warmup + multiple samples + production-like load tests. |
| Raising cost sky-high without rate limiting | Attackers overload the KDF queue | Concurrency caps, rate limiting, and capacity planning. |
| Assuming PBKDF2 600k is enough forever | Hardware and guidance evolve | Benchmark periodically and review current standards. |
| Hardcoding one numeric cost across all algorithms | Cost parameters have different semantics | Per-algorithm policy definitions. |
| Logging passwords or hashes for debugging | Increases exposure of credential material | Log aggregate metadata only; never log secrets. |

## 12. Scenario exercises

1. **Choosing policy:** you have two server classes with different CPU/RAM limits. Tabulate candidate Argon2id `m`/`t`/`p` or PBKDF2 iterations and design load tests at 1, 10, and 50 concurrent KDF calls. Explain why single-threaded p95 is insufficient.
2. **Verifying with the right cost:** create a PBKDF2 record at 12,000 rounds, then attempt to verify it at 600,000 rounds using the same salt/hash. Explain why it fails to match and how to verify properly before upgrading.
3. **Java practice:** run `PasswordUpgradeDemo`; explain why `upgraded=true` on the first login, `upgradeAgain=false` on the second, and why the salt changed even though the password stayed identical.
4. **Error handling:** change the record's iterations field to `999999999` or format `v9`; why must the parser reject it **before calling the KDF**?
5. **Race condition:** two valid logins read the same legacy record; one session updates successfully. What should the other session do when compare-and-set fails? What changes if a password reset occurred concurrently?
6. **Dormant accounts:** 5% of users have not logged in for 2 years. Without plaintext passwords, why can't you rehash directly? Propose an authenticated reset or controlled legacy-verifier sunset policy.
7. **Double cost:** each legacy login verifies once at old cost and hashes once at new cost. Estimate peak CPU/RAM during rollout, and propose metrics and appropriate rate-limit/bounded-concurrency settings.
8. **Algorithm migration:** write pseudocode that verifies both PBKDF2 and Argon2id while **creating new hashes only with Argon2id**. Do not equate PBKDF2 `iterations` with Argon2id `t`.
9. **Practical security:** explain the distinct roles of salt, work factor, pepper, rate limiting, and TLS. Why does no single control completely replace the others?

**Mastery criteria:** you can distinguish each KDF's cost parameters; benchmark on representative infrastructure; store records with version/params/salt; verify with the **stored** cost before upgrading; generate new hashes from **password + fresh salt + new policy**, update atomically, and handle races; and prevent downgrades or resource exhaustion from malformed records.

## References

- [OWASP Password Storage Cheat Sheet — Work Factors, Argon2id, PBKDF2, and Upgrading the Work Factor](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [NIST SP 800-63B (Revision 4) — Password Verifiers, salted hashes, and cost factors](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [Java SE 17: `PBEKeySpec` and `clearPassword`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html)
- [Java SE 17: `SecretKeyFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html)
- [Java SE 17: `MessageDigest.isEqual`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html)
- [RFC 9106 — Argon2 Memory-Hard Function for Password Hashing](https://www.rfc-editor.org/rfc/rfc9106)