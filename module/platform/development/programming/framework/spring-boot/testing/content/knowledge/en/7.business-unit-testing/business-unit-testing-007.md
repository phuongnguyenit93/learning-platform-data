# Controlling Randomness, UUIDs, and ID Generators in Business Unit Tests

## 1. Why Does Randomness Make Tests Unreliable?

Suppose a Spring Boot application issues discount coupons, generates order codes, or mints tokens. Each run can produce a different result because it calls `Math.random()`, `new Random()`, `UUID.randomUUID()`, or `SecureRandom`. If a test asserts a specific value while production code generates random values internally, the test becomes **flaky**: sometimes PASS, sometimes FAIL even with unchanged source code.

Example of error-prone code:

~~~java
class CouponService {
    int discountPercent() {
        return Math.random() < 0.1 ? 25 : 5;
    }
}

// Wrong target: this test sometimes FAILS even when production code is right.
// assertEquals(25, new CouponService().discountPercent());
~~~

The snippet above only illustrates the problem; it is **not a standalone test file**. At runtime, `Math.random()` produces no fixed value that a unit test can deliberately select. If 10% of runs return 25 and 90% return 5, a hardcoded assertion expecting `25` cannot reliably pass.

We must separate two responsibilities:

- **Variable data source:** random numbers, UUIDs, sequence numbers, tokens, timestamps, or IDs from external systems.
- **Business rules:** what the outcome must be when the source yields value A, value B, or an error.

Unit tests focus on **running real business rules**, while the variable source is **dependency-injected** so tests can substitute deterministic values. Verifying that production generates compliant UUIDs, the database prevents duplicate keys, or tokens possess sufficient entropy belongs in separate tests with clear scopes.

After this lesson, you should be able to design components accepting `RandomGenerator`/`IdGenerator`, pick appropriate mocks/stubs/fakes/seeds, test boundaries, understand UUID v4 and sequential IDs, avoid predictable randomness for security, and build CI-reproducible suites.

## 2. Three Distinct Concepts: Random Source, UUID, and ID Generator

| Concept | Job | Java 17+ example | What unit tests should check |
| --- | --- | --- | --- |
| **Random source** | Provides choices or variable values, typically within a specific range | `RandomGenerator.nextInt(100)` | Application reacts properly to 0, 9, 10, 99… |
| **UUID** | A 128-bit identifier value type with formatting rules and multiple versions | `UUID.randomUUID()`, `UUID.fromString(...)` | Application processes/saves/returns the issued ID accurately; when testing an adapter, check version/variant |
| **ID generator** | Identifier-issuing policy: random UUID, sequence, DB-generated ID, or time/partitioned ID | `IdGenerator.nextId()` or `Supplier<UUID>` | SUT fetches ID at the right time and uses it properly; errors or collisions follow the contract |

**Random does not mean guaranteed unique.** UUID v4 is designed for negligible collision probability given a good random source, yet provides no absolute guarantee. An incrementing ID can be unique within **a single counter's scope**, yet not automatically unique across instances or restarts without coordination.

**Unique does not mean secret.** Order codes and IDs in URLs identify objects; they are not proof that a caller is authorized to access them. Never use “hard-to-guess UUIDs” as a substitute for authentication/authorization.

**Reproducible does not mean cryptographically secure.** `Random` with a fixed seed is great for replaying a simulation in tests; it is unsuitable for generating login tokens, API keys, password-reset secrets, or production OTPs.

## 3. Random Number Sources in Java 17+

### 3.1 RandomGenerator is a clean boundary for business logic

Since Java 17, `java.util.random.RandomGenerator` defines common random generation methods such as `nextInt(bound)`, `nextLong()`, and `nextDouble()`. A business class accepting this interface through its constructor is easy to substitute in tests.

~~~java
import java.util.random.RandomGenerator;

final class LuckyDraw {
    private final RandomGenerator random;

    LuckyDraw(RandomGenerator random) {
        this.random = random;
    }

    boolean isWinner() {
        return random.nextInt(100) < 10;
    }
}
~~~

This is an **illustrative class**, without a test file or `main` method. By contract, `nextInt(100)` returns integers from **0 to 99** (100 is an exclusive upper bound). Hence `< 10` covers 10 winning outcomes out of 100 possible values under uniform distribution: 0 through 9.

In unit tests, mock the interface to pick boundary values intentionally:

~~~java
RandomGenerator random = mock(RandomGenerator.class);

when(random.nextInt(100)).thenReturn(9);
assertTrue(new LuckyDraw(random).isWinner());

when(random.nextInt(100)).thenReturn(10);
assertFalse(new LuckyDraw(random).isWinner());
~~~

The snippet above belongs **inside a test with Mockito/JUnit and `LuckyDraw` declared**; it does not compile standalone. Each fixed value corresponds to one business branch to prove. No need to invoke random thousands of times hoping for an approximate 10% frequency.

### 3.2 Random(seed): reproducible, yet tied to algorithm and call sequence

`java.util.Random` accepts a seed on construction:

~~~java
import java.util.Random;

Random first = new Random(42L);
Random second = new Random(42L);

for (int i = 0; i < 5; i++) {
    if (first.nextInt(100) != second.nextInt(100)) {
        throw new AssertionError("Sequences differ");
    }
}
~~~

With the same algorithm, seed, bounds, and **call sequence**, two generators yield the same series of numbers. This helps replay a test case, simulate multi-step runs, or debug synthetic data. However:

- Adding one extra `nextInt(...)` call in code shifts every subsequent outcome, even if business rules stay unchanged.
- Two different PRNG algorithms are not guaranteed to emit the same sequence for the same seed.
- Sharing a stateful generator across parallel tests makes consumption order non-deterministic.
- Fixed seeds make sequences **predictable**; never use them for production secrets.

When the goal is testing **a branch or boundary**, stubbing direct input values is usually clearer than seeding. When testing **ordered multi-step behavior**, a seed or sequence fake can fit better.

### 3.3 Math.random, ThreadLocalRandom, and new Random() inside methods

Calls like `Math.random()`, `ThreadLocalRandom.current()`, or `new Random()` embedded inside a method make tests hard to control and create hidden dependencies. Mockito supports some static-mocking techniques, yet you should not turn controlling randomness into complex plumbing when a constructor-injected collaborator solves it cleanly.

In concurrent code, **thread safety** of each implementation is a separate concern: never assume every `RandomGenerator` implementation is thread-safe. Pick a generator matching bean lifecycle and concurrency, or scope generators appropriately; never let tests depend on access order to a shared source.

## 4. Dependency Injection Point: Replace Only the Source, Run Real Business Logic

A clean design:

~~~text
                   +------------------------+
HTTP/Command ----> | REAL CouponService     |
                   | - validate input       |
                   | - apply thresholds     |
                   | - build Coupon         |
                   +-----------+------------+
                               |
                   +-----------+-----------+
                   |                       |
                   v                       v
             IdGenerator              RandomGenerator
           production: UUID v4       production: proper PRNG
           unit test: fixed/sequence unit test: mock 0,9,10,99
~~~

Do not mock `CouponService` itself: if it holds the logic under test, the test must run the real implementation. The SUT decides **when** an ID is needed, **which random values** count as winning, and what the **final result** must contain.

For small dependencies, two common options exist:

~~~java
// Dedicated interface expressing the business contract:
interface IdGenerator {
    UUID nextId();
}

// Or use a standard library interface when clear enough:
Supplier<UUID> idSupplier = UUID::randomUUID;
~~~

These are **two alternative designs**, not a complete file: imports for `java.util.UUID` and `java.util.function.Supplier` are required. A dedicated interface helps name the contract, attach metrics, or model error paths; `Supplier<UUID>` works well for single-operation components without extra rules.

In Spring Boot, register production implementations as beans and constructor-inject them into services. Unit tests instantiate the service directly with mocks/fakes; no `@SpringBootTest` is needed merely to control randomness.

## 5. UUIDs: Values, Versions, Parsing, and Uniqueness

### 5.1 UUID v4 in Java

`UUID.randomUUID()` on Java 17 generates **version 4** UUIDs using a cryptographically strong pseudo-random source per the JDK contract. A UUID holds 128 bits, with designated bits for version and variant; a typical UUID v4 carries **122 random bits**. The string representation usually spans 36 hyphenated hex characters:

~~~text
xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
~~~

Here the version nibble is `4` and the variant nibble at `y` is one of `8`, `9`, `a`, `b`. This is a format pattern, **not a complete validation regex**. In Java code, you can check `uuid.version() == 4` and `uuid.variant() == 2` or parse via `UUID.fromString(...)`.

Example fixed ID in a unit test:

~~~java
UUID fixed = UUID.fromString("00000000-0000-4000-8000-000000000001");
~~~

A fixed value does not make it random; it is simply valid UUID v4-formatted test data. Never generate a fresh UUID inside a test and expect it to equal another fresh UUID generated by the service; two distinct calls have no reason to match.

**UUID v4 drastically lowers collision risk, yet does not replace unique constraints.** The database still needs a unique constraint whenever uniqueness is a business invariant. If a collision happens, the application needs a bounded handling policy (such as selective retry on confirmed duplicate-ID errors), never an infinite retry loop.

### 5.2 Random UUID vs name-based UUID

Java also provides `UUID.nameUUIDFromBytes(byte[])` to generate a **deterministic** UUID from a byte array: identical input bytes yield the identical UUID (in the JDK, this produces MD5-based UUID version 3). Example:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

UUID first = UUID.nameUUIDFromBytes(
        "coupon:user-1".getBytes(StandardCharsets.UTF_8));
UUID again = UUID.nameUUIDFromBytes(
        "coupon:user-1".getBytes(StandardCharsets.UTF_8));

assertEquals(first, again);   // Same input -> same UUID.
assertEquals(3, first.version());
~~~

This is a **snippet inside a JUnit test method**; `assertEquals` requires a JUnit Jupiter import. It highlights the difference: *name-based* when the domain requires identical logical keys to produce identical IDs; *random v4* when each entity requires a fresh ID. Deterministic UUIDs do not ensure secrecy and are unsuitable for reset tokens or unguessable IDs.

When serializing API/JSON payloads or persisting to a database, choose a consistent ID representation. Parse and validate UUID strings at boundaries; compare IDs as `UUID` values rather than comparing strings that may differ in letter casing. Every ID type must still be paired with object-level authorization checks.

### 5.3 UUID v7, sequences, and other ID formats

Some systems prefer time-ordered IDs for sorting and index locality; **UUID v7** is a standardized time-ordered format. The Java 17 examples here use `UUID.randomUUID()`, which generates **v4**, not UUID v7. If you need v7, choose a supporting library/generator and verify output version, clock behavior, and collision handling. Never assume calling `UUID.randomUUID()` will automatically switch to v7.

| ID type | Strengths | What to verify |
| --- | --- | --- |
| UUID v4 | No central allocator, low collision risk, fits distributed systems | Unique constraint, format, indexing impact, never treat as secret |
| Name-based UUID | Identical input yields identical ID, useful for deterministic mapping | Canonical input definition, encoding, logical collisions, input-exposure risk |
| Database Sequence/IDENTITY | Unique within DB and easy table lifecycle management | DB locking, transactions, concurrency; do not test with mocks if real sequence behavior matters |
| In-process counter (`AtomicLong`) | Easy to fake in unit tests, issues sequential IDs | Resets on restart, collides across multiple instances; does not replace DB sequence in distributed production |
| Time/partitioned ID (e.g., snowflake-style) | Fast generation with approximate time ordering | Clock rollback, node ID, counter limits, instance synchronization |
| UUID v7 or other sortable IDs | Can improve time locality | Time order not necessarily strict, version/library, collisions and clock behavior |

A **business reference** such as `ORD-2026-000123` may require customer-facing formatting while the table still uses a UUID/sequence as its technical key. Separate those responsibilities if their rules evolve independently; never use pure randomness to “guarantee” monotonically increasing order numbers.

## 6. Complete Java 17+ Example: Testing CouponService with Controllable IDs and Randomness

Problem statement: a service issues coupons to valid users. Each coupon must carry an ID from `IdGenerator`; a single draw `nextInt(100)` determines the discount tier: values 0–9 receive **25%**, values 10–99 receive **5%**. Blank users are rejected before touching dependencies.

We will test the **real business code** using:

- `Mockito.mock(RandomGenerator.class)` to stub exact boundaries 0, 9, 10, 99.
- Mock `IdGenerator` when a single fixed ID is needed.
- `SequenceIds`, a fake issuing two IDs in order; the test avoids real OS randomness.
- `Random(42L)` illustrating sequence replayability.
- `UUID.fromString(...)` as test fixtures, plus a dedicated test verifying JDK UUID generator properties.

Place the entire content below into `src/test/java/example/CouponServiceTest.java`. This file is a **self-contained example** requiring Java 17+, JUnit Jupiter, and Mockito. It needs no Spring ApplicationContext, database, Docker, or network.

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.Objects;
import java.util.Random;
import java.util.UUID;
import java.util.random.RandomGenerator;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@DisplayName("CouponService: deterministic randomness and identifiers")
class CouponServiceTest {

    private static final UUID ID_A = UUID.fromString(
            "00000000-0000-4000-8000-000000000001");
    private static final UUID ID_B = UUID.fromString(
            "00000000-0000-4000-8000-000000000002");

    interface IdGenerator {
        UUID nextId();
    }

    record Coupon(UUID id, String userId, int discountPercent) {
    }

    static final class CouponService {
        private final IdGenerator ids;
        private final RandomGenerator random;

        CouponService(IdGenerator ids, RandomGenerator random) {
            this.ids = Objects.requireNonNull(ids);
            this.random = Objects.requireNonNull(random);
        }

        Coupon issue(String userId) {
            if (userId == null || userId.isBlank()) {
                throw new IllegalArgumentException("userId is required");
            }

            UUID id = Objects.requireNonNull(
                    ids.nextId(), "generated ID");

            // nextInt(100) returns values 0..99.
            int draw = random.nextInt(100);
            int discount = draw < 10 ? 25 : 5;

            return new Coupon(id, userId, discount);
        }
    }

    // Fake that emits only the exact IDs prepared by the test in sequence.
    static final class SequenceIds implements IdGenerator {
        private final Deque<UUID> remaining;

        SequenceIds(UUID... values) {
            remaining = new ArrayDeque<>(Arrays.asList(values));
        }

        @Override
        public UUID nextId() {
            if (remaining.isEmpty()) {
                throw new IllegalStateException("No IDs remaining");
            }
            return remaining.removeFirst();
        }
    }

    @Test
    @DisplayName("Draw 0 gets 25% and preserves fixed ID")
    void zeroDrawGetsBonusAndFixedId() {
        IdGenerator ids = mock(IdGenerator.class);
        RandomGenerator random = mock(RandomGenerator.class);
        when(ids.nextId()).thenReturn(ID_A);
        when(random.nextInt(100)).thenReturn(0);

        Coupon actual = new CouponService(ids, random).issue("user-1");

        assertAll(
                () -> assertEquals(ID_A, actual.id()),
                () -> assertEquals("user-1", actual.userId()),
                () -> assertEquals(25, actual.discountPercent()));

        verify(ids).nextId();
        verify(random).nextInt(100);
    }

    @Test
    @DisplayName("Draw 9 remains in the 25% tier")
    void nineIsLastBonusValue() {
        RandomGenerator random = mock(RandomGenerator.class);
        when(random.nextInt(100)).thenReturn(9);

        Coupon coupon = new CouponService(
                new SequenceIds(ID_A), random).issue("user-2");

        assertEquals(25, coupon.discountPercent());
    }

    @Test
    @DisplayName("Draw 10 moves to the 5% tier")
    void tenIsFirstBaseValue() {
        RandomGenerator random = mock(RandomGenerator.class);
        when(random.nextInt(100)).thenReturn(10);

        Coupon coupon = new CouponService(
                new SequenceIds(ID_A), random).issue("user-3");

        assertEquals(5, coupon.discountPercent());
    }

    @Test
    @DisplayName("Draw 99 remains in the 5% tier")
    void ninetyNineIsValidUpperValue() {
        RandomGenerator random = mock(RandomGenerator.class);
        when(random.nextInt(100)).thenReturn(99);

        Coupon coupon = new CouponService(
                new SequenceIds(ID_A), random).issue("user-4");

        assertEquals(5, coupon.discountPercent());
    }

    @Test
    @DisplayName("Blank user is rejected before generating ID or drawing")
    void invalidUserConsumesNoRandomnessOrId() {
        IdGenerator ids = mock(IdGenerator.class);
        RandomGenerator random = mock(RandomGenerator.class);

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> new CouponService(ids, random).issue("  "));

        assertEquals("userId is required", error.getMessage());
        verifyNoInteractions(ids, random);
    }

    @Test
    @DisplayName("Two calls consume the expected sequence of IDs and draws")
    void sequenceMakesMultipleIssuesPredictable() {
        RandomGenerator random = mock(RandomGenerator.class);
        when(random.nextInt(100)).thenReturn(9, 10);
        CouponService service = new CouponService(
                new SequenceIds(ID_A, ID_B), random);

        Coupon first = service.issue("user-1");
        Coupon second = service.issue("user-2");

        assertAll(
                () -> assertEquals(ID_A, first.id()),
                () -> assertEquals(25, first.discountPercent()),
                () -> assertEquals(ID_B, second.id()),
                () -> assertEquals(5, second.discountPercent()));
        verify(random, times(2)).nextInt(100);
    }

    @Test
    @DisplayName("Null generated ID is rejected before drawing randomness")
    void nullGeneratedIdDoesNotConsumeRandomness() {
        IdGenerator ids = mock(IdGenerator.class);
        RandomGenerator random = mock(RandomGenerator.class);
        when(ids.nextId()).thenReturn(null);

        NullPointerException error = assertThrows(
                NullPointerException.class,
                () -> new CouponService(ids, random).issue("user-1"));

        assertEquals("generated ID", error.getMessage());
        verifyNoInteractions(random);
    }

    @Test
    @DisplayName("Same seed and call order produce identical sequence")
    void sameSeedReplaysSequence() {
        Random first = new Random(42L);
        Random second = new Random(42L);

        for (int i = 0; i < 8; i++) {
            assertEquals(first.nextInt(100), second.nextInt(100));
        }
    }

    @Test
    @DisplayName("Name-based UUID repeats identically from the same bytes")
    void nameBasedUuidIsDeterministic() {
        byte[] key = "coupon:user-1".getBytes(StandardCharsets.UTF_8);
        UUID first = UUID.nameUUIDFromBytes(key);
        UUID second = UUID.nameUUIDFromBytes(key);

        assertEquals(first, second);
        assertEquals(3, first.version());
    }

    @Test
    @DisplayName("UUID.randomUUID creates UUID v4 with RFC variant")
    void randomUuidHasExpectedFormatVersion() {
        UUID id = UUID.randomUUID();

        assertEquals(4, id.version());
        assertEquals(2, id.variant());
    }
}
~~~

### Explaining what the tests actually prove

- **`CouponService` is the real SUT.** If the threshold changes from `draw < 10` to `draw <= 10`, the test for `10` FAILS. If user validation is removed, the blank-user test FAILS. Business regressions are caught at the exact spot.
- **Mock `RandomGenerator` acts as a data stub.** `when(random.nextInt(100)).thenReturn(9)` does not “verify random is uniformly distributed”; it provides a boundary value to verify the business rule. `verify(random).nextInt(100)` adds value when the contract requires drawing exactly once from range 100.
- **`SequenceIds` is a stateful fake.** The first call returns `ID_A`, the next returns `ID_B`; when exhausted, the fake throws clearly. This lets you test multi-step operations without depending on fresh OS UUIDs.
- **`UUID.randomUUID()` appears only in the adapter/JDK property test.** The test checks version/variant, never comparing a freshly generated UUID against a hardcoded string or claiming any two arbitrary UUIDs are guaranteed distinct.
- **`Random(42L)` tests replayability of the same algorithm.** The test does not hardcode specific numbers from the algorithm; it compares two generators sharing the same seed and call sequence.
- **`nullGeneratedIdDoesNotConsumeRandomness()`** verifies both the error contract and that randomness is not consumed after an invalid ID. Call ordering in the SUT is an intentional design choice of this example.
- **No test relies on `Thread.sleep`**, thousands of probabilistic retries, or network calls. Branches are tested using inputs explicitly supplied by the test.

Expected outcome when JUnit Platform runs this file: **10 test methods PASS**. The tests print no stdout; display names and execution order in IDE/Gradle may vary, while the total declared tests remain 10.

**Limitation of self-contained examples:** `CouponService` and its domain types sit inside the test file so the entire contract is readable in one place. In real projects, **business implementations must live in `src/main/java`** and tests import those classes; never duplicate a copy of a “production service” inside `src/test/java` and mistake it for testing production code.

## 7. Running the Example with Gradle in a Spring Boot Project

In a Spring Boot module with suitable plugins and dependency management, `build.gradle` typically includes this configuration (a **snippet inside an existing project**, not a standalone build file):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` normally includes JUnit Jupiter and Mockito. This example calls `mock(...)` directly, so **`MockitoExtension` is not required** to populate `@Mock` fields. If switching to `@Mock`, add `@ExtendWith(MockitoExtension.class)` or an equivalent initializer.

From the module's appropriate Gradle root directory:

~~~bash
./gradlew test --tests example.CouponServiceTest
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.CouponServiceTest
~~~

**Expected outcome:** all 10 tests PASS and the Gradle task succeeds given valid dependencies/environment. No specific test stdout is shown because assertions print nothing and Gradle output formatting varies by version/configuration.

**If tests are not discovered**, check `org.junit.jupiter.api.Test`, `useJUnitPlatform()`, file path `src/test/java/example/CouponServiceTest.java`, package `example`, and JUnit Jupiter dependencies. You do not need `@SpringBootTest` just to run pure Java tests.

### Moving the example into production code

In production, create an `IdGenerator` implementation:

~~~java
// Inside production code, after declaring interface IdGenerator:
final class UuidV4Ids implements IdGenerator {
    @Override
    public UUID nextId() {
        return UUID.randomUUID();
    }
}
~~~

This snippet **only illustrates the implementation**, requiring `UUID` import and the application's `IdGenerator` interface; it is not a standalone file. In Spring Boot, register it as a bean and constructor-inject it into services. In unit tests, substitute `SequenceIds` or a mock. The goal is keeping business code on one contract while deciding ID generation at the configuration layer.

## 8. Numeric IDs, Sequences, and Concurrency: Never Confuse Fakes with Production

Some domains do not want UUIDs: they want ascending, readable numbers or database-generated IDs. A fake can emit sequential IDs in unit tests:

~~~java
import java.util.concurrent.atomic.AtomicLong;

final class InMemoryIds {
    private final AtomicLong next = new AtomicLong(1000);

    long nextId() {
        return next.getAndIncrement();
    }
}
~~~

This is an **illustrative class snippet**, without `main`. It gives tests predictable IDs 1000, 1001, 1002… when using a dedicated instance sequentially. `AtomicLong` makes increments thread-safe within **the same process**, yet **does not** make it a distributed ID generator:

- Two JVMs starting at the same initial value can emit identical IDs.
- After restart, an in-memory counter does not resume its last persisted position.
- When multiple instances share a database, coordination is required (DB sequences, an ID-issuing service, or node/time-partitioned algorithms with explicit guarantees).
- With DB `GENERATED IDENTITY`, ID assignment is database behavior; unit tests should stub the returned value from the repository, while integration tests verify the real DB generator.

**Never test uniqueness under contention by calling a fake sequentially twice.** Sequential unit tests only prove logic consumes the ID source per contract. Concurrency testing requires multiple threads/transactions against real storage when business invariants depend on it.

### Handling ID collisions in the right layer

If the application generates UUIDs itself and writes to a database, enforce a **unique constraint** on that key. Calling `repository.existsById(id)` followed by `save(...)` is insufficient because two concurrent requests can both observe “not present” and then insert. The database constraint must serve as the final arbiter; if the contract allows retries, retry only confirmed duplicate-key errors a bounded number of times and ensure earlier operations caused no unrepeatable side effects.

Unit tests can use a fake generator emitting “existing ID → fresh ID” alongside a fake persistence layer throwing a modeled duplicate error to test retry logic. However, **never treat that test as proof that DB transactions/concurrency work**. Real database integration tests are needed to verify constraints and real transaction behavior.

## 9. Randomness in Security: SecureRandom and Tokens

Randomness for prize draws and randomness for **authentication secrets** have fundamentally different requirements.

- `Random` and ordinary PRNGs can be predicted or recovered from internal state; never use them for session secrets, reset tokens, production OTPs, or API keys.
- `SecureRandom` is the JDK API using a cryptographically strong pseudo-random source. Java's `UUID.randomUUID()` generates UUID v4 using a cryptographically strong source per JDK docs, yet **a UUID does not automatically become a secure session token merely by being hard to guess**. Token security models require entropy, TTL, storage hashing policies, rotation, and authorization checks.
- **Never fix the seed of `SecureRandom` in production or tests to “predict” exact output bytes.** `SecureRandom.setSeed(...)` may supplement the entropy pool, and algorithms/providers differ; the same seed is not guaranteed to yield identical bytes across machines.
- To unit test token-issuing use cases deterministically, **inject `TokenGenerator`/`Supplier<String>` into the service** and stub the token value. Keep format/entropy checks in dedicated tests for the real generator.

Standalone production class example for URL-safe tokens:

File `src/main/java/example/ResetTokenGenerator.java`:

~~~java
package example;

import java.security.SecureRandom;
import java.util.Base64;
import java.util.Objects;

public final class ResetTokenGenerator {
    private final SecureRandom random;

    public ResetTokenGenerator(SecureRandom random) {
        this.random = Objects.requireNonNull(random);
    }

    public String nextToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

This is a **standalone compilable production class on Java 17+** using only the JDK, without `main`, so it produces no stdout. 32 random bytes yield 256 bits of input; unpadded URL-safe Base64 has an exact length of **43 characters** for 32 bytes.

An adapter test verifies **format invariants** instead of predicting exact tokens:

File `src/test/java/example/ResetTokenGeneratorTest.java`:

~~~java
package example;

import java.security.SecureRandom;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ResetTokenGeneratorTest {
    @Test
    void generatesUrlSafeTokenOfExpectedLength() {
        String token = new ResetTokenGenerator(
                new SecureRandom()).nextToken();

        assertEquals(43, token.length());
        assertTrue(token.matches("[A-Za-z0-9_-]{43}"));
    }
}
~~~

This test checks only length and character alphabet; it **does not quantitatively prove entropy**. Security reviews must assess algorithms, key management, hashed token storage, TTL, rate limiting, revocation, and full auth flows. Never log secrets or treat UUIDs as authorization proof.

In unit tests of use cases that send tokens, prefer:

~~~java
// Example of injecting a port inside a service test, not a standalone file:
Supplier<String> fakeTokenSource = () -> "fixed-token-for-test";
~~~

For real code, import `java.util.function.Supplier` and define an appropriate interface/constructor. Fixed tokens belong strictly in tests to assert outbound emails, stored hashes, or expiration bindings; production must use a secure generator.

## 10. Different Strategies for Testing Randomness

| Goal | Strategy | Assertions to use |
| --- | --- | --- |
| Test probability branches: 0–9 vs 10–99 | Mock/stub `nextInt(100)` values | 0 and 9 → 25%; 10 and 99 → 5% |
| Test ordered multi-step flows | Sequence fakes for random and IDs | Outputs matching each issued value |
| Replay a simulated bug | PRNG with fixed seed and algorithm | Replayed outcomes for identical input/call order |
| Test business service using generated UUID | Stub `IdGenerator` returning fixed UUID | Resulting ID equals the injected ID |
| Test UUID v4 adapter | Run real generator | `version() == 4` and `variant() == 2` |
| Test name-based ID | Canonicalized input bytes | Same input yields same UUID |
| Test DB unique constraint | Real DB in integration tests | Duplicate insert rejected at persistence layer |
| Test token format | Real `SecureRandom`, assert format | Length, character set, valid parsing |
| Test service sending token | Stub `TokenGenerator` at boundary | Message/state contains exact issued token |
| Test statistical distribution | Dedicated statistical test if truly required | Defined criteria/tolerance, avoiding tiny sample sizes |

**Avoid baseless random assertions:**

~~~java
// DO NOT do this:
// assertNotEquals(UUID.randomUUID(), UUID.randomUUID());
// assertEquals(25, service.discountPercent()); // without controlling the source
// assertEquals(100, uniqueIds.size());         // relying on 100 calls not colliding
~~~

These lines illustrate **anti-patterns**. Two UUID v4 values have minuscule collision odds, yet asserting “100 runs must be distinct” neither guarantees global uniqueness nor gives diagnosable feedback if the generator misbehaves. Testing ID-issuing rules, retry contracts, and DB constraints yields clear evidence.

### Should you test for an exact 10% outcome rate?

If the rule is “values below 10 earn 25%”, unit tests should test the **threshold** with fixed inputs. Whether a PRNG produces a uniform distribution is a separate concern. Sampling 10 or 100 calls and asserting an exact 10% hit rate has a high false-failure probability even when randomness works properly; rigorous statistical testing requires hypotheses, sample sizes, tolerances, and false-positive budgets. Normally you do not run flaky statistical tests on every CI build.

## 11. Controlling Shared State, Async Execution, and Seeds in CI

Even with a seed, a test can still behave non-deterministically if multiple threads share a generator or storage:

- If two threads call the same stateful PRNG, draw order can interleave unpredictably, changing which request gets which value.
- Static mutable `Random` instances in tests allow methods to affect each other depending on run order.
- If a service consumes one ID and later refactoring inserts an extra call beforehand, all downstream seeded outputs shift.
- Calling `UUID.randomUUID()` inside a test without saving it leads to comparing two unrelated UUIDs across assertions.
- Finite-sequence fake generators must be freshly initialized per test; never share one fake across independent tests.

Best practices:

1. Create fresh generators/fakes **per test** or inject isolated state. In JUnit Jupiter, `@BeforeEach` fits fixture initialization well.
2. Set seeds in **Arrange**, and log the seed whenever a complex data-generation test fails; never tweak seeds arbitrarily while debugging.
3. Fix algorithm, parameters, and call counts if replayability is needed; do not record only “seed = 42” and swap generators across versions.
4. For async/concurrency, scope random sources per request/thread/worker or design outcomes independent of access order; verify concurrency with dedicated coordinated tests.
5. For workflow identifiers, mint the ID at one clear boundary and **pass the same value** across services/repositories/events; avoid having every layer call `UUID.randomUUID()` separately.
6. Inject `Clock` or virtual time for time-based logic; **Random seeds do not control `Instant.now()`**. When identifiers embed timestamps, inject the time source too.
7. For Spring singleton beans, assess generator thread-safety and lifecycle; never assume all `RandomGenerator` implementations offer identical concurrency guarantees.

**Practical rule:** tests are far more stable when asserting **output contracts** (assigned ID, discount tier, ID request count) rather than asserting an entire algorithm's random sequence unrelated to business rules.

## 12. Integrating into Spring Boot Without Slowing Down Unit Tests

In production, declare `IdGenerator` as a bean and constructor-inject it into services. For non-security business draws, provide a `RandomGenerator` implementation matching concurrency needs. Illustrative configuration snippet (requires `IdGenerator` and `CouponService` defined in application code):

~~~java
@Configuration
class GeneratorConfig {

    @Bean
    IdGenerator idGenerator() {
        return UUID::randomUUID;
    }

    @Bean
    RandomGenerator drawRandomGenerator() {
        return new Random();
    }
}
~~~

This is an **illustrative configuration snippet**, not a standalone file. It needs imports for Spring `Configuration`/`Bean`, `UUID`, `Random`, and `RandomGenerator`. A shared `Random` instance is thread-safe per JDK guarantees, though it can experience contention under heavy load; choose another design if throughput/concurrency demands it. Never reuse this business PRNG bean for security tokens.

**Unit tests** instantiate `new CouponService(fakeIds, mockRandom)` as in section 6, needing no container or context. **Spring integration tests** use `ApplicationContext` when verifying bean wiring, configuration profiles, or transactions. A unit test with a mock `IdGenerator` does not by itself prove that production `@Bean` definitions load properly.

Never hardcode a fixed seed in production PRNG configuration merely to make unit tests easy. Seeds belong in intentional test harnesses or reproducible simulations; testability should come from **dependency boundaries**.

## 13. Ten Common Mistakes and Fixes

**1. Calling `UUID.randomUUID()` inside logic and comparing against another UUID in tests.** Two separate UUID calls have no equality relation. Inject `IdGenerator`, stub a fixed ID, and assert the SUT uses it.

**2. Using `Math.random()` to drive business branches in tests.** You cannot force it to return 0 or 0.1 deterministically. Extract `RandomGenerator` and stub boundary values like 0, 9, 10, 99.

**3. Setting a seed and assuming no code change can shift results.** Changing algorithms or call counts shifts the sequence. Use seeds for replay, and stub exact values for branch checks.

**4. Using `Random(42)` or `Math.random()` to generate reset tokens.** Output is predictable. Production needs `SecureRandom` and proper token lifecycle management; use-case tests should stub a token port.

**5. Assuming UUIDs can never collide.** Low collision probability is not a strict invariant. Enforce storage unique constraints and implement bounded conflict handling.

**6. Treating name-based UUIDs as fresh IDs per issuance.** `UUID.nameUUIDFromBytes(...)` yields identical IDs for identical bytes; great for logical keys, wrong when each issuance needs a distinct ID.

**7. Testing “100 calls didn't collide” and concluding the generator is safe.** A small sample proves neither distributed uniqueness nor cryptographic entropy. Verify algorithms, constraints, and error paths at their proper layers.

**8. Using an `AtomicLong` fake to prove production IDs are unique across instances.** `AtomicLong` is scoped to one process's in-memory state. Use integration tests for DB sequences or distributed ID allocators.

**9. Sharing RNG state across parallel tests.** Outcomes depend on execution order. Give every test its own fixture; avoid mutable statics and verify concurrent usage explicitly.

**10. Over-mocking and skipping business rules.** Mocking the service itself and stubbing the desired coupon tests Mockito, not thresholds or validation. Keep the real SUT and replace only variable sources.

**11. Treating UUIDs as authorization.** A UUID in a URL does not replace owner/tenant/role checks; enforce authorization on every request.

**12. Silently ignoring null or duplicate IDs from generators.** Depending on the contract, fail fast, apply bounded retries, or translate contextual errors; unit test those branches and test real storage where constraints execute.

## 14. Step-by-Step Workflow for a New Feature

Suppose you need to implement “award a bonus coupon to 10% of requests”:

1. **Write the contract:** valid users receive a coupon with an ID and 25% discount on draws 0–9, 5% on draws 10–99.
2. **Externalize variation from the service:** constructor accepts `IdGenerator` and `RandomGenerator`.
3. **Define error behavior:** blank input consumes neither ID nor randomness; null ID is rejected; storage conflicts have an explicit policy.
4. **List boundaries:** draws 0, 9, 10, and 99; no need for thousands of iterations.
5. **Test ID sequencing:** sequence fake `ID_A` then `ID_B` to verify outputs bind the right IDs.
6. **Test adapters separately:** UUID v4 version/variant, or name-based generator if required by the business.
7. **Integrate at the right layer:** repository with real unique constraints and transactions; bean config tests when verifying Spring wiring.
8. **Classify security requirements:** promotional draws can use ordinary PRNGs; security tokens require `SecureRandom` and security policies.
9. **Check CI stability:** tests must not rely on wall clock, thread scheduling, raw probabilities, or shared random sources.
10. **Review after refactoring:** assertions must continue protecting business behavior even if internal helper calls or class structure change.

### Quick checklist before finishing

- [ ] SUT executes real production logic; randomness and IDs are injected as explicit dependencies.
- [ ] Stubs/mocks supply exact **boundary** values rather than testing randomness by chance.
- [ ] Sequence fakes isolate state per test and fail clearly when exhausted.
- [ ] Seeds are used only when replay is genuinely needed, without assuming cross-algorithm stability.
- [ ] UUID tests verify the right ID is propagated; version/variant checks live in adapter tests where valuable.
- [ ] Databases enforce unique constraints on identifiers requiring uniqueness; collisions and concurrency are handled at the proper layer.
- [ ] UUIDs/IDs are never treated as authorization tokens; secrets use cryptographically secure sources.
- [ ] Spring Boot bean config, thread safety, and generator lifecycles are verified at integration level.
- [ ] Tests are independent without shared static RNGs, real clocks, or small-sample frequencies.
- [ ] Java examples run on JUnit Platform; assertions reflect the exact business contract.

**Key takeaway:** the goal is not “forcing random numbers to be identical on every run”, but **designing variable sources as dependencies so unit tests can supply the exact inputs under test**. Business code runs for real, tests stay deterministic, and properties specific to UUIDs, database sequences, or SecureRandom are verified in their proper places.

### References

- [Java 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): generation methods and `nextInt(bound)` contracts.
- [Java 17 API — Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): seeding and pseudo-random sequence rules.
- [Java 17 API — UUID](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html): UUID v4, `randomUUID`, `nameUUIDFromBytes`, version, and variant.
- [Java 17 API — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): cryptographically strong pseudo-random generator.
- [RFC 9562 — Universally Unique IDentifiers](https://www.rfc-editor.org/rfc/rfc9562): UUID format and versions including UUID v7.
- [Mockito Documentation](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html): stubbing values and verifying interactions.
- [JUnit Jupiter User Guide](https://docs.junit.org/5.11.4/user-guide/): organizing unit tests and assertions.