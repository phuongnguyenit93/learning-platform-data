# 11.6 Managing IVs or Nonces Across Multiple Threads, Multiple Processes, and Restarts

## Learning Objectives

After this lesson, you will be able to:

1. Explain why an **IV/nonce is a resource managed alongside the key lifecycle**, rather than merely generating a byte array when calling `Cipher.init(...)`.
2. Distinguish the **uniqueness** requirement of AES-GCM, AES-CTR, and ChaCha20-Poly1305 from the **unpredictability** requirement of CBC IVs; never apply one formula blindly across all modes.
3. Build a thread-safe nonce allocator for **multiple threads in one JVM**, while understanding the limits of `AtomicLong`/`synchronized` across multiple processes or hosts.
4. Design **durable counters**, range leasing stores, and nonce namespace partitioning by key/worker; understand the order **reserve → durable commit → encrypt**.
5. Explain how to handle **crashes, restarts, retries, parallel deployments, backup rollbacks, and failovers**, and when you must **rotate to a new key**.
6. Test in Java 17 with AES-GCM: 1,600 concurrent encryptions across threads and a multi-JVM sequence example using `FileChannel`/`FileLock` with explicit limitations.

## 1. What Is an IV/Nonce and Why Do Operational Issues Arise?

An **IV (Initialization Vector)** and a **nonce (number used once)** are initialization inputs for certain cipher modes. In many modes, the IV/nonce is **transmitted publicly** alongside the ciphertext and need not be hidden like a key. Yet **being public does not mean it can be reused arbitrarily**.

Consider an AEAD record:

```text
  key K (secret)       nonce N (typically public)
        \                  /
         \                /
          AES-GCM encrypt(plaintext, AAD)
                        |
                        v
                  ciphertext || tag

  Stored/transmitted data:
  [version] [keyId] [nonce] [ciphertext || tag]
```

Key `K` can encrypt many records under an **invocation/key-usage policy**. Yet for AES-GCM, **the pair (K, N) must never be reused to encrypt two distinct input sets**. `Cipher.getInstance("AES/GCM/NoPadding")` itself executes only a single cryptographic operation per instance; it does not own a system-wide nonce allocator.

A system can implement a single encryption properly and still be dangerous when:

- Two threads read `counter = 7` simultaneously and both construct nonce `...0007`.
- Two processes/JVMs on the same host each initialize their own counter from `0`.
- Two containers on different nodes share the same key without partitioning the nonce namespace.
- A machine restart resets an in-memory counter back to `0` while **the old key remains in use**.
- A backup/restore or failover rolls a database sequence back to an earlier value.
- A request retry after timeout produces a different ciphertext while reusing the previously issued nonce.
- An internal API and a background job share the same key and nonce space due to missing centralized governance.

The real problem is **upholding the mode's invariant across all encryptions under the same key material**, across threads, processes, nodes, and the key's entire lifetime.

## 2. Not Every Mode Has the Same IV Requirement

| Mode / Algorithm | Primary Requirement for IV/Nonce | What Does Reuse Cause? | Key Takeaway |
| --- | --- | --- | --- |
| **AES-GCM** | Nonce/IV must be unique per key within scope and standard limits; 96-bit is common | Can break confidentiality and integrity, enabling tag forgery | Different plaintext/AAD alone **does not rescue** reuse |
| **AES-CTR** | No **counter block** may ever repeat under the same key, even across messages | Repeated keystream, leaking XOR relation of plaintexts | Manage every counter block inside each message too |
| **ChaCha20-Poly1305** | Unique nonce under the same key | Keystream reuse and integrity risk | Do not assume safe merely because nonce is 12 bytes |
| **AES-CBC** | IV meeting CBC standards, especially **unpredictable**; use a fresh IV | Repeated or predictable IVs can leak info/structure | Predictable counters alone are not a general CBC solution |
| **AES-ECB** | Uses no IV | Leaks repeated block patterns | Do not choose ECB for general payload encryption |

**Unique** and **unpredictable** are two different properties. Under GCM's deterministic IV construction, a sequential counter can be safe if it genuinely never repeats under the same key and obeys policy. Under CBC, an IV that is unique yet predictable **does not automatically satisfy CBC's requirement**. Therefore, never reuse one “nonce generator” across all cipher modes without analyzing each mode separately.

### 2.1 Consequences of Nonce Reuse in GCM and CTR

GCM uses a CTR-like mechanism for confidentiality. If the same key/nonce yields the same keystream for two messages, you get:

```text
C1 = P1 XOR S
C2 = P2 XOR S

C1 XOR C2 = P1 XOR P2
```

This depicts the corresponding CTR encryption layer, not the full GCM format including the tag. Knowing or guessing one plaintext can leak bytes of the other message. With GCM, the impact is even worse because authentication can also be attacked/forged. **A single key/nonce pair reuse can be a security incident**, not merely a “tiny ignorable probability.”

For CTR, NIST SP 800-38A requires that **every counter block used for encryption under the same key differ from every other counter block**, including across different messages. That is stronger than “distinct initial per-message nonces”: you must also prevent **counter wrap/overflow and enforce message length bounds**.

### 2.2 IV/Nonce vs. Tag, AAD, and Key ID

- **Key**: cryptographic secret; changing to **genuinely new key material** creates a new uniqueness domain.
- **Nonce/IV**: initialization input; for GCM it must not repeat **per key**.
- **AAD (Additional Authenticated Data)**: integrity-protected but unencrypted metadata; **different AAD does not legitimize a repeated nonce**.
- **Tag**: AEAD authentication output; **a 128-bit tag does not protect against nonce reuse**.
- **Key ID/version**: tells the app which key to load; **changing the key ID label while keeping the same old key bytes does not create a new cryptographic domain**.

Do not rely on `Cipher.init` occasionally rejecting reusing a key/IV on **the same Cipher object**. The API cannot know whether another process or host already used that pair. Defense must live at the **system-wide key management and nonce allocation layer**.

## 3. Two Common GCM Nonce Allocation Strategies

### 3.1 96-Bit Random Nonce from CSPRNG

A common pattern:

```java
byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);
```

This is an **embedded snippet**, not a standalone program. With a sound cryptographic RNG, each call yields an unpredictable 96-bit nonce. Yet **random does not mean strictly unique**. After many encryptions under the same key, collision probability rises per the birthday bound.

With `q` independently and nearly uniformly generated nonces in a 96-bit space:

```text
P(at least one duplicate pair)
  ≈ q(q-1) / (2 * 2^96)       when q << 2^48
```

For example, at `q = 1,000,000`, the probability is roughly `6.3 × 10^-18` if ideal assumptions actually hold. That figure is **not a guarantee** for every PRNG/VM/provider and must not be used to ignore standard invocation limits.

NIST SP 800-38D mandates uniqueness and sets a **total limit of 2^32 authenticated-encryption invocations per key for RBG-based (random) constructions** (and certain other configurations; see Section 8.3). This total counts **across all instances and all processes/hosts** using that key, not “2^32 per thread.”

Advantage: no global counter needed on every call. Drawback: collision probability is non-zero, requiring tracking total invocations per key and controlling instance count, entropy sources, and key rotation. Never arbitrarily mix **random nonces** and **deterministic nonces** under the same key when policy/standards select one construction.

### 3.2 Deterministic Nonce = Fixed Field || Invocation Counter

For a 96-bit nonce, a common structure is:

```text
96-bit nonce = 32-bit fixed field || 64-bit invocation field

bytes:
[ 4-byte fixed ] [ 8-byte sequence ]

N(0) = fixed || 0000000000000000
N(1) = fixed || 0000000000000001
N(2) = fixed || 0000000000000002
...
```

If the **fixed field stays constant** within a namespace and the sequence **strictly increases without wrapping**, every nonce is distinct. NIST SP 800-38D specifies a deterministic construction with a **fixed field** and an **invocation field**; fields must be allocated so the entire **(key, IV) pair** stays unique. The 32+64 split is a common illustration, not automatically suitable for every protocol or configuration.

All writers sharing **the same key and the same fixed field** must share **one truly coordinated sequence source**. If writers are assigned **distinct fixed fields** under the same key, each writer can maintain its own counter, provided the fixed-field allocator guarantees non-overlap and binds to key/worker/epoch.

**64 bits is not a license for infinite encryption.** You must still check invocation-field capacity, standard budgets, data volume per key, tag length, key rotation policies, and operational alerts. Never let a counter wrap back to `0`.

## 4. Allocating Nonces Across Multiple Threads in One JVM

### 4.1 Race Condition with Plain Variables

Unsafe example:

```java
long seq = nextSequence;   // Thread A reads 17; Thread B reads 17
nextSequence = seq + 1;
return makeNonce(seq);
```

Even if a `long` read/write is atomic, a **read-modify-write** sequence like this is not a single transaction. Two threads can grab the same value. Plain `volatile` does not fix this race either.

Within one JVM, use:

- `AtomicLong` with bounded increment checks;
- or `synchronized`/locks wrapping **the exact sequence-allocation step**;
- a **single allocator per key + fixed field**; never instantiate a fresh allocator per HTTP request.

`AtomicLong` guarantees threads inside one JVM receive distinct sequences, **does not** coordinate across separate processes/JVMs, and **does not** persist progress across restarts.

### 4.2 Practice 1: Multiple Threads Sharing One Allocator and Fresh Key

This program generates **one fresh AES key** per run, one 4-byte fixed field for that allocator, issues `4 + 8` nonces, and runs concurrent AES-GCM encryptions across multiple threads. This tests **one JVM and one short key lifetime**, not a persistence solution.

Create file **`ConcurrentGcmNonceDemo.java`** (Java 17 or higher):

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class ConcurrentGcmNonceDemo {
    private static final int THREADS = 8;
    private static final int PER_THREAD = 200;
    private static final long KEY_BUDGET = 1_000_000L;

    private static final class Allocator {
        private final byte[] fixedField;
        private final AtomicLong next = new AtomicLong();

        Allocator(byte[] fixedField) {
            if (fixedField.length != 4) throw new IllegalArgumentException();
            this.fixedField = fixedField.clone();
        }

        byte[] take() {
            long sequence = next.getAndUpdate(old -> {
                if (old >= KEY_BUDGET) {
                    throw new IllegalStateException("Rotate key: nonce budget exhausted");
                }
                return old + 1;
            });
            return ByteBuffer.allocate(12)
                    .put(fixedField).putLong(sequence).array();
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey freshKey = generator.generateKey();

        byte[] fixedField = new byte[4];
        new SecureRandom().nextBytes(fixedField);
        Allocator allocator = new Allocator(fixedField);
        Set<String> seen = ConcurrentHashMap.newKeySet();
        ExecutorService pool = Executors.newFixedThreadPool(THREADS);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int t = 0; t < THREADS; t++) {
                futures.add(pool.submit(() -> {
                    for (int i = 0; i < PER_THREAD; i++) {
                        byte[] iv = allocator.take();
                        if (!seen.add(HexFormat.of().formatHex(iv))) {
                            throw new IllegalStateException("Duplicate nonce!");
                        }
                        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                        cipher.init(Cipher.ENCRYPT_MODE, freshKey,
                                new GCMParameterSpec(128, iv));
                        cipher.updateAAD("record:v1".getBytes(StandardCharsets.US_ASCII));
                        byte[] sealed = cipher.doFinal(
                                "record".getBytes(StandardCharsets.US_ASCII));
                        if (sealed.length != 6 + 16) {
                            throw new IllegalStateException("Unexpected GCM output");
                        }
                    }
                    return null;
                }));
            }
            for (Future<?> future : futures) future.get();
        } finally {
            pool.shutdown();
        }

        System.out.println("threads: " + THREADS);
        System.out.println("encryptions: " + THREADS * PER_THREAD);
        System.out.println("unique nonces: " + seen.size());
        System.out.println("nonce bytes: " + allocator.take().length);
    }
}
```

Compile and run:

```bash
javac --release 17 ConcurrentGcmNonceDemo.java
java ConcurrentGcmNonceDemo
```

Verified output:

```text
threads: 8
encryptions: 1600
unique nonces: 1600
nonce bytes: 12
```

**Why is this correct within the demo's scope?**

1. `AtomicLong.getAndUpdate` makes reading and incrementing the sequence atomic within one JVM; the lambda blocks once `KEY_BUDGET` is reached. No duplicate numbers are issued even as 8 threads contend.
2. The nonce built by `ByteBuffer.put(fixedField).putLong(sequence)` is **12 bytes**, big-endian: 4-byte fixed field + 8-byte sequence.
3. `ConcurrentHashMap.newKeySet()` checks for nonce collisions in the test; this set is not required in production once the allocator proves uniqueness.
4. Each encryption creates its own `Cipher` (a mutable object not thread-safe by default), using a 128-bit GCM tag and feeding AAD before `doFinal`.
5. `Future.get()` propagates worker exceptions instead of silently printing success if a task fails.
6. The final `allocator.take().length` **consumes one extra unused nonce** solely to verify the 12-byte length. “Burning” a sequence number is safe; never reuse that number later.

**Critical limitation:** every run **generates a brand-new AES key** and resets the counter to `0`. Because the key is fresh, the demo does not demonstrate restart safety with a persisted key; never copy `new Allocator(...)` into a service where **the same key survives restarts**. If another process uses the same key, it does not share this `AtomicLong` and risks sequence collisions.

## 5. Multiple Processes/JVMs or Multiple Nodes: Namespace Partitioning Is Mandatory

A server may run 16 threads, 4 worker JVMs, multiple concurrent containers, and batch jobs. If all of them encrypt under **one key**, the nonce namespace must cover **every single one** of those writers.

There are three basic ways to organize this:

### Approach A — A Sequence Authority with Durable Transactions

```text
   Java process A ──┐
   Java process B ──┼──> durable/atomic sequence authority
   Java process C ──┘                |
                                    v
                        [nextSequence per keyId]
                                    |
                    unique reserved ranges / values
                                    |
                                    v
                        nonce = fixed || sequence
```

The issuing authority can be a database table with truly **linearizable and durable** updates/transactions. Processes may only use numbers that have **committed successfully**. The key is not “we called the counter-increment API,” but **after any crash or failover, the system cannot reissue a sequence already used to encrypt under the same key**.

When using a DB, evaluate:

- Transaction atomicity when concurrent transactions update the same row;
- commit durability under the declared fault-tolerance guarantees;
- whether snapshot restores, replica promotions, or failovers can **roll back committed sequences**;
- quota enforcement and key rotation triggers;
- whether caches or queues hold uncommitted ranges.

If a database rolls back after a ciphertext using the new sequence was already emitted externally, issuing that same sequence again causes **nonce reuse**, even though the code originally saw a committed transaction.

### Approach B — Pre-Allocate Ranges, Consume In-Process Afterward

Fetching a database lock on every single message can hurt latency. Instead, lease **disjoint number ranges**:

```text
   DB durable counter next = 1000

Process A: reserve [1000, 2000) => commit next = 2000
Process B: reserve [2000, 3000) => commit next = 3000

A uses 1000, 1001, ...
B uses 2000, 2001, ...

A crashes at 1050:
[1051, 2000) is discarded, NEVER returned to the pool.
```

Rules:

1. **Commit the durable high-water mark before handing the range to a process**.
2. Inside each process, allocate numbers from its range via `AtomicLong` or a local lock.
3. When a range runs out, fetch a new range; **never wrap** or reclaim an old range.
4. After a crash, unused numbers in the leased range are treated as spent; gaps are safe, reuse is not.
5. Whenever commit state is uncertain, **do not encrypt**. Never “fall back” to an in-memory counter or temporary reset.

An illustrative **PostgreSQL-style SQL** example, not runnable Java:

```sql
-- Table nonce_state holds one unique row per active key_id:
-- (key_id PRIMARY KEY, next_seq BIGINT NOT NULL)
-- :lease_size > 0, :per_key_limit is the policy cap.

BEGIN;
UPDATE nonce_state
SET next_seq = next_seq + :lease_size
WHERE key_id = :key_id
  AND next_seq >= 0
  AND next_seq <= :per_key_limit - :lease_size
RETURNING next_seq - :lease_size AS start_inclusive,
          next_seq               AS end_exclusive;
COMMIT;
```

Read the result **only after COMMIT succeeds**; if zero rows return or commit fails, **grant no range**. Real contracts must account for concurrency, durability/replication, and database failover. Never equate a `RETURNING` row inside an uncommitted transaction with a durably granted range.

### Approach C — Dedicated Fixed Field per Writer, Independent Counter per Partition

If you want to avoid a global sequence call, centrally assign a **distinct fixed field** to each worker/tenant/node, and let each writer manage its own invocation counter:

```text
same key K
  ├─ writer 01: fixed=0x00000001 || local sequence 0,1,2,...
  ├─ writer 02: fixed=0x00000002 || local sequence 0,1,2,...
  └─ writer 03: fixed=0x00000003 || local sequence 0,1,2,...
```

**Never** assume `PID`, hostname, container ordinal, or timestamp makes a fixed field unique. Worker IDs can be reassigned during autoscaling, pod restarts, or failovers. If a new writer is reassigned an old fixed field under the same key, it **must resume from the prior durable counter**, never restart at `0`.

When the fixed field has finite bits, manage writer namespace exhaustion and per-writer invocation limits alongside total limits per key/standard. If each writer holds distinct key material derived via a properly domain-separated KDF, uniqueness becomes a **per-new-key** problem, though key issuance and rotation must still be governed consistently. Changing `keyId` without changing key bytes does not create a new key.

## 6. Restarts and Crashes: What Matters Most Is State Write Ordering

Compare two orderings:

**Unsafe:**

```text
read counter = 42
       |
       v
encrypt(key, nonce=42) --> ciphertext sent out
       |
       v
update counter = 43 to storage     <-- crash before this step
       |
       v
restart: reads counter = 42 --> NONCE REUSE
```

**Right direction:**

```text
read counter = 42
       |
       v
atomically reserve 42, persist/COMMIT next=43
       |
       v
only once commit succeeds:
encrypt(key, nonce=42) --> ciphertext
       |
      crash
       |
       v
restart: next >= 43, never reissues 42
```

Some **allocated but unused** numbers after a crash are normal; **skipping numbers is far better than reusing a nonce**.

### 6.1 Distinguishing Crash, Timeout, and Retry

- **Crash before commit**: range/sequence was not validly leased; encryption must not have happened yet.
- **Crash after commit, before encryption**: leaves a gap; never refund the sequence.
- **Crash after encryption, before saving ciphertext**: the sequence is already spent; re-encrypting requires a **different** sequence even for identical plaintext.
- **Timeout with unknown outcome**: you cannot “reclaim” the old nonce assuming the prior call definitely did not encrypt. Issue a fresh nonce while handling business idempotency independently.
- **Retry when prior encryption output is available**: you may **retransmit the exact old ciphertext/tag** per retransmission policy, which differs from **running a new encryption under the same key/nonce**. Anti-replay is a separate protocol concern, typically using message IDs/sequences and AAD.

If the nonce store is unavailable or cannot prove the latest committed state: **fail closed** and refuse encryption under the current key. You may transition to a **new key epoch with new key material** via a controlled recovery workflow.

## 7. Practice 2: Durable Counter Across Multiple JVMs with File Locks

This example demonstrates the principles of:

- Persisting `nextSequence` in a **state file**.
- Using an exclusive `FileLock` when multiple processes access **one file on a filesystem with proper locking semantics**.
- Adding a `synchronized` monitor to prevent two threads **within the same JVM** from contending on `FileLock` (per Java API, file locks are held on behalf of the entire JVM).
- Writing the **next sequence** and calling `FileChannel.force(true)` before issuing the nonce.
- Detecting corrupted size/magic/checksum and failing closed rather than resetting.
- Using `CREATE_NEW` when **initializing a unique new epoch/key**, avoiding accidental overwrite of an existing file.

**Important:** this is an educational local-filesystem model, **not a production allocator guaranteeing atomic crash recovery across all filesystems**. `FileChannel.force(true)` does not replace database transactions/WAL, CRC32 does not protect against malicious tampering, in-place updates risk torn writes, directory entry creation has its own semantics, and `FileLock` behavior depends on the OS/filesystem. Restoring a backup or deleting the file and calling `init` again with **the same key** can still cause nonce reuse. In production, use a well-evaluated transaction log/durable sequence authority/fencing bound to **the exact key epoch**.

In the demo, fixed field `0x10203040` is just an example byte prefix; the program **neither manages nor stores an AES key**. Applied to a real key, you must immutably bind the fixed field, key ID, and durable state to **the same key material**, and govern every writer.

Create file **`DurableGcmSequenceDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.zip.CRC32;

public class DurableGcmSequenceDemo {
    private static final Object IN_JVM_GUARD = new Object();
    private static final byte[] MAGIC =
            "GCMSEQ01".getBytes(StandardCharsets.US_ASCII);
    private static final int RECORD_SIZE = 8 + 8 + 4;
    private static final long KEY_BUDGET = 1_000_000L;
    private static final int FIXED_FIELD = 0x10203040; // Demo: one fresh key/epoch.

    private static int checksum(long sequence) {
        CRC32 crc = new CRC32();
        crc.update(ByteBuffer.allocate(8).putLong(sequence).array());
        return (int) crc.getValue();
    }

    private static byte[] record(long next) {
        return ByteBuffer.allocate(RECORD_SIZE)
                .put(MAGIC).putLong(next).putInt(checksum(next))
                .array();
    }

    private static long readNext(FileChannel channel) throws IOException {
        if (channel.size() != RECORD_SIZE) {
            throw new IOException("Invalid state size: fail closed");
        }
        ByteBuffer buf = ByteBuffer.allocate(RECORD_SIZE);
        while (buf.hasRemaining()) {
            int n = channel.read(buf, buf.position());
            if (n <= 0) throw new IOException("Truncated state");
        }
        buf.flip();
        byte[] magic = new byte[MAGIC.length];
        buf.get(magic);
        long next = buf.getLong();
        int expected = buf.getInt();
        if (!Arrays.equals(magic, MAGIC) ||
                expected != checksum(next) || next < 0) {
            throw new IOException("Corrupted state: fail closed");
        }
        return next;
    }

    private static void persist(FileChannel channel, long next)
            throws IOException {
        ByteBuffer buf = ByteBuffer.wrap(record(next));
        while (buf.hasRemaining()) {
            int n = channel.write(buf, buf.position());
            if (n <= 0) throw new IOException("State write failed");
        }
        channel.force(true);
    }

    private static void initializeNewKeyState(Path path) throws IOException {
        try (FileChannel channel = FileChannel.open(
                path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            persist(channel, 0);
        }
    }

    private static long reserve(Path path) throws IOException {
        synchronized (IN_JVM_GUARD) {
            try (FileChannel channel = FileChannel.open(
                    path, StandardOpenOption.READ, StandardOpenOption.WRITE);
                 FileLock lock = channel.lock()) {
                long sequence = readNext(channel);
                if (sequence >= KEY_BUDGET) {
                    throw new IOException("Rotate key: budget exhausted");
                }
                // Reserve and force the NEXT sequence before returning this one.
                persist(channel, sequence + 1);
                return sequence;
            }
        }
    }

    private static byte[] iv(long sequence) {
        return ByteBuffer.allocate(12)
                .putInt(FIXED_FIELD).putLong(sequence).array();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: init|next <state-file>");
        }
        Path path = Path.of(args[1]);
        switch (args[0]) {
            case "init" -> {
                initializeNewKeyState(path);
                System.out.println("initialized: true");
            }
            case "next" -> {
                long sequence = reserve(path);
                System.out.println("iv hex: " + HexFormat.of().formatHex(iv(sequence)));
            }
            default -> throw new IllegalArgumentException("Use init or next");
        }
    }
}
```

Compile and run in a **test directory**, using a non-existent state file (e.g., `demo-state.bin`):

```bash
javac --release 17 DurableGcmSequenceDemo.java
java DurableGcmSequenceDemo init demo-state.bin
java DurableGcmSequenceDemo next demo-state.bin
java DurableGcmSequenceDemo next demo-state.bin
```

Verified output across separate `java` invocations:

```text
initialized: true
iv hex: 102030400000000000000000
iv hex: 102030400000000000000001
```

These are two **12-byte** IVs starting with fixed field `10203040` followed by big-endian sequences `0` and `1`. Unlike the in-memory `AtomicLong` program, two `next` calls in **two separately launched JVMs** read the same state file and receive consecutive sequences.

**Why does the code have two kinds of locks?** `synchronized (IN_JVM_GUARD)` coordinates threads within one JVM; `FileChannel.lock()` coordinates processes on a filesystem enforcing compatible file locks. Java `FileLock` is held “on behalf of the entire JVM,” not as a thread mutex inside one process. Never rely on file locks alone to replace intra-JVM synchronization.

**Do not miss this:** the `init` command demonstrates initializing state for **a new key epoch**, not “repairing” lost state. If the state file is corrupted, lost, or rolled back in a backup, **never reinitialize the counter from `0` under the old key**. Halt encryption, investigate, and if uniqueness cannot be proven, rotate to **new key material**. Restoring an older state snapshot with a valid checksum **is not detected by CRC32**; external generation/fencing and a durable source of truth are required.

### 7.1 Why Is the File Example Not Yet a Production Allocator?

`FileChannel.force(true)` requests flushing content/metadata to storage; it **does not provide an atomic transaction spanning key state, ciphertext, and all replicas**. Files can suffer torn writes, host crashes, power loss, devices ignoring flushes, snapshot rollbacks, or network filesystems that misimplement locks. CRC32 detects certain random corruptions, not malicious tampering or rollback to a valid older snapshot.

If `persist` fails in a real app, **fail closed** and reconcile durable state before issuing another sequence; never fall back to an in-memory `sequence` variable. If non-regression cannot be proven, move to a new key epoch. For distributed systems and high-value data, use a database/consensus store or range authority with **transactions/fencing** rather than a DIY counter file shared over NFS.

## 8. Retries, Backups, and Failover: Cases Too Easily Overlooked

| Event | Risk | Safe Policy |
| --- | --- | --- |
| Two concurrent threads | Read the same sequence | One atomic allocator per JVM |
| Two JVMs sharing a key | Each process starts counter at 0 | Shared durable allocator or centrally leased prefix namespaces |
| Container restart | RAM resets while old key stays active | Read durable high-water mark; never reset to 0 |
| Job retry | Re-encrypting with the old nonce | Fresh nonce for **each new encryption**; retransmitting old ciphertext is distinct |
| Reserve counter/lease then crash | Leaves some sequences unused | **Burn the remaining range**, never reuse |
| DB replica failover | Replica lacks committed nonce high-water | Fencing/consistency guaranteeing zero loss of committed high-water marks |
| Backup restore | Counter rolls backward | Halt encryption under old key; verify state or switch to a **new key** |
| Software rollback | Older version resets schema/key state | Controlled migrations protecting counter invariants |
| Blue-green/canary deploy | Two versions use the same key independently | Share the allocator or use disjoint writer namespaces |
| Multi-region active-active | Colliding sequences/fixed fields | Partition prefixes/keys per region or use one durable authority |
| Changing keyId without changing key bytes | Illusion of a new namespace | **No**: nonce uniqueness follows key material, not labels |
| Exhausting budget / counter wrap | Nonce reuse | Block encryption before limit; rotate key and version |

### 8.1 What About Data Already Encrypted Under the Old Key?

When rotating keys, old records still need decryption with **the matching old key version and stored nonce** per retention policy. Key rotation does not require immediately re-encrypting every record, yet namespaces must never be mixed:

```text
encrypted record:
[formatVersion] [keyId] [nonce] [ciphertext || tag]

current encryption key: key-v2
old record key:       key-v1, read-only decrypt
```

Once `key-v1` stops being allowed to **encrypt**, no new nonces may ever be issued under `key-v1`. Decrypt permissions can remain for the allowed retention period. If records carry metadata that must be bound (tenant, keyId, record type, version), feed a canonical byte representation into **AAD** to prevent context swapping; distinct AADs never authorize nonce reuse.

### 8.2 Fencing Tokens and Split Brain

If two nodes both believe they are the allocator leader, an expired distributed lock or lagging replica can cause **both sides to issue the same range**. A **monotonically increasing fencing token/epoch** checked by the storage/authority blocks stale writers from committing updates after losing leadership. A TTL lock alone without epoch checks at the authority may be insufficient.

When storing counters in a distributed database, know clearly:
- where transactions commit and with what durability level;
- whether failover can lose committed writes;
- how a deposed leader is blocked from issuing ranges once its lease expires;
- whether backups capture the key epoch and an up-to-date high-water mark.

Sharing one key across two regions is only safe when nonce namespaces are allocated **globally**. An alternative is issuing **distinct key material** per region/worker via key management with domain separation, while still enforcing uniqueness under each key.

## 9. Checklist for Limit Enforcement and Monitoring

A system should maintain at least these metadata fields:

| Attribute | Purpose |
| --- | --- |
| `keyId`, `keyEpoch`, algorithm/mode | Identify exactly which **key material** namespace is issuing nonces |
| `fixedField` / worker namespace | Guarantee non-overlapping nonce partitions |
| `nextSequence` / `reservedUntil` | High-water mark committed prior to encryption |
| `invocationsUsed` / `keyBudget` | Cap total encryptions per key and drive rotation policy |
| `stateVersion` / allocator epoch / fencing token | Distinguish leadership handoffs |
| `lastDurableCommit` or transaction evidence | Support investigation across crashes/restarts/failovers |
| `algorithmParams` (IV length, tag length) | Decrypt consistently under the same format |
| `createdAt` / rotation state | Govern active-encrypt / decrypt-only / retired states |

Counters used solely for **monitoring** may cache asynchronously, but counters **enforcing uniqueness** must never rely on uncommitted eventually consistent metrics.

### 9.1 There Is No Single “GCM Threshold for Every Design”

NIST SP 800-38D Section 8 specifies:

- **IV uniqueness under the same key** is essential to GCM security.
- For **RBG-based IVs** (random construction) and deterministic IVs **other than 96 bits**, Section 8.3 sets a general cap of **at most 2^32 authenticated-encryption invocations per key** across all instances.
- For **96-bit deterministic IVs only**, exemption from that specific cap **does not** mean unlimited: you must still satisfy field structure, avoid invocation-field wrapping, bound device/context counts, limit data per key, and meet other security policies.

The example `KEY_BUDGET = 1_000_000` in code is a **lesson placeholder quota**, not a mandatory standard limit or recommended production target. Real limits must derive from your threat model, mode standards, nonce distribution scope, and rotation plan.

## 10. Choosing a Design by Environment

| Environment | Starting Design to Consider | Mandatory Constraints |
| --- | --- | --- |
| Short-lived CLI, **new key every run** | 96-bit CSPRNG nonce with small invocation count per key | Never reuse the old key across restarts; separate key versions clearly |
| Single JVM, key lives only in-process | `AtomicLong` + 96-bit deterministic nonce | One allocator per key; never recreate within the same key epoch |
| Single JVM, key survives restarts | Durable counter or DB-leased ranges | Persist/commit **before encrypting**; no rollbacks |
| Multiple JVMs on one host | Atomic DB sequence or file lock **only if FS/durability is proven** | Never use `synchronized` to coordinate across processes |
| Microservices / many nodes | Durable range authority + leases/fencing, or unique key/prefix domain per writer | Disjoint partitions and no state regression on failover |
| Multi-region active-active | Region-specific key material, or globally allocated fixed fields/ranges | Test DR/restore, replica promotion, and split-brain behavior |
| GCM via third-party API | Strictly follow the API's nonce/IV and invocation-limit contract | Never assume the provider/transport automatically assigns globally unique nonces |

A **sound design** prioritizes keeping the invariant simple: every encryption under the same key gets a unique nonce, backed by operational proof that the invariant holds after failures. Complex systems need not invent custom crypto primitives; they simply must manage primitive inputs properly.

## 11. Meaningful Pre-Production Testing

One passing encrypt/decrypt unit test **proves nothing** about allocator safety. Test:

1. **Multi-threaded within one JVM:** allocate thousands of concurrent nonces; zero duplicates; any failed `Future` must fail the test.
2. **Multi-process/JVM:** run parallel processes sharing a key namespace/allocator. Verify zero duplicate `(key, nonce)` pairs across all outputs.
3. **Restart preserving old key:** issue some nonces, stop, restart; new numbers must exceed the previously used high-water mark, never reset.
4. **Crash injection at every boundary:** before reservation, after transaction commit, before encryption, after encryption, and before saving the record. Gaps are allowed; reuse is forbidden.
5. **Leadership loss / fencing:** stale nodes must be blocked from leasing new ranges after losing their lease.
6. **Replica failover:** accept failover only if it cannot regress the durable high-water mark for the old key; without proof, rotate keys.
7. **Backup rollback:** simulate restoring an older state snapshot. Monitoring/design must detect or block encryption; a simple file checksum **is not enough**.
8. **Counter exhaustion:** at the quota boundary, fail closed/throw and trigger rotation—never wrap to `0`.
9. **Altered key ID/nonce format:** decrypting a record with swapped metadata must fail via AAD authentication or policy.
10. **Monitoring:** alert on used/budget ratio, range lease/commit errors, spikes in encryptions per key, missing new keys, and allocator unavailability.

Finite-run uniqueness tests are positive evidence, yet **do not replace design proofs and recovery testing**. An in-memory counter can pass every multithreaded test and still reuse nonces on the very first restart.

## 12. Common Mistakes

- **“`SecureRandom.nextBytes(12)` is always different.”** False: random nonces give probabilistic uniqueness; invocation limits and RNG/key policies are still required.
- **“`AtomicLong` is thread-safe, so microservices can each use `AtomicLong`.”** False: it is only atomic among threads sharing the same instance inside one JVM.
- **“Every container has a different PID, so using PID as a prefix suffices.”** False: PIDs/ordinals can be reused, collide across hosts, and ignore key epochs.
- **“Restarts reset the counter to 0, yet keeping the same key is fine.”** False: risks repeating previously used key/nonce pairs.
- **“Encrypt first and persist the counter afterward for higher throughput.”** False: crashes create a nonce-reuse window.
- **“Return unused leased ranges back to the pool.”** False: crashes obscure what was already spent; burn unused ranges.
- **“File locks work reliably on any NFS.”** False: behavior and durability depend on OS/filesystem; `FileLock` is not a distributed transaction.
- **“`force(true)` prevents snapshots from rolling back.”** False: flushing does not stop restore rollbacks, replica lag, or failovers.
- **“GCM has a 128-bit tag so nonce reuse is minor.”** False: reuse undermines both confidentiality and authenticity.
- **“Nonces are secret and should not be stored.”** Usually false: nonces are stored/transmitted publicly alongside ciphertext for decryption; protect **uniqueness and the key**.
- **“Different AAD creates a separate nonce namespace.”** False: uniqueness tracks the key and IV.
- **“Renaming `keyId` gives us a fresh key.”** False: you must rotate the actual **key material**.
- **“GCM and CBC share the same incrementing-IV formula.”** Generally false: CBC requires unpredictable IVs per its own specification.
- **“If unsure whether the counter regressed, test-encrypt and inspect.”** No post-hoc test restores security after reusing a nonce; when in doubt, **halt encryption under the old key**.

## 13. Self-Check Questions

**1.** Can two threads using a plain `long seq++` issue the same nonce?  
**Yes.** Read-increment-write is not atomic; use `AtomicLong` or proper synchronization.

**2.** Are separate `AtomicLong` instances in two JVMs on the same host safe if they share a key and fixed field?  
**No.** Each JVM can emit sequences 0, 1, ...; use a shared durable authority or truly disjoint namespaces.

**3.** Why must the counter commit **before** encryption?  
Because crashing after encryption but before persistence lets a restart reissue a nonce already used in emitted ciphertext.

**4.** A range [100, 200) is committed to a process, which crashes after using up to 120. May [121, 200) be reissued?  
**No.** Leased ranges are treated as spent; gaps are safe, reuse is not.

**5.** Should you reinitialize a counter file from 0 if the old file was lost while keeping the same AES key?  
**No.** Fail closed and reconcile with a durable authority; if exact state cannot be proven, rotate to a new key.

**6.** Is it safe to reuse an AES-GCM key/IV pair for a different message as long as the AAD differs?  
**No.** Different AAD does not excuse repeating a key/IV pair.

**7.** With a 32-bit fixed + 64-bit counter deterministic nonce, what is essential to prevent collisions across multiple processes?  
Maintain a **shared atomically and durably allocated counter**, or assign non-overlapping fixed fields per writer/key paired with durable per-partition counters.

**8.** Does using an incrementing counter as a CBC IV automatically guarantee safety?  
**No.** CBC requires unpredictable IVs per policy; GCM's deterministic nonce rules cannot be copied mechanically.

**9.** Does “96-bit random nonce” mean zero collision probability?  
**No.** The probability is small but non-zero; NIST sets limits per construction and per key.

**10.** Does rotating from `key-v1` to `key-v2` let you delete `key-v1` immediately?  
Depends on retention policy: old ciphertexts still need `key-v1` to decrypt until re-encrypted or expired. However, `key-v1` should transition to **decrypt-only**, forbidding new encryptions.

## Summary

Core rule for modes requiring unique nonces:

```text
                    key material K
                          |
                  one nonce namespace
                          |
          +---------------+----------------+
          |                                |
   random IV construction           deterministic IV
   (collision probability)          fixed || counter
          |                                |
   track invocations/key            atomic allocation
   and standard caps                + durable commit
          |                                |
          +---------------+----------------+
                          |
                          v
              encrypt with unused nonce
                          |
                          v
           store [keyId,nonce,ciphertext,tag]
                          |
                          v
      restart / process / host / failover still
      CANNOT reissue a nonce under the same key
```

**IV/nonce management is part of the key lifecycle, not a casual random detail inside a method.** It requires synchronization within the JVM, consensus/durability across processes, key versioning, and recovery policies across restarts. Whenever the invariant cannot be verified, stop encrypting under the old key and recover forward with a **new key**.

## Official References

- [NIST SP 800-38D — Galois/Counter Mode (GCM) and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): Sections 8.1–8.3 on IV/key uniqueness, deterministic vs. RBG constructions, and invocation limits.
- [NIST SP 800-38A — Block Cipher Modes of Operation](https://csrc.nist.gov/pubs/sp/800/38/a/final): CBC IV requirements and CTR counter-block uniqueness (Appendix B).
- [Java 17 — Cipher API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `AES/GCM/NoPadding`, `updateAAD`, and using a fresh IV per encryption.
- [Java 17 — GCMParameterSpec API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): tag `tLen` (bits) and IV bytes.
- [Java 17 — AtomicLong API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): atomic counters within a single JVM.
- [Java 17 — FileLock API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileLock.html): JVM-wide file locks, thread caveats, and OS/filesystem behavior.
- [Java 17 — FileChannel API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `lock()`, positional I/O, and `force(true)`.
