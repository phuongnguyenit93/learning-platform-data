# Keeping a Behavior Matrix as the Baseline When Refactoring or Upgrading a Test Suite

## 1. Why Can a Green Test Suite After Refactoring Still Hide a Regression?

A Spring Boot project is preparing to move from heavy `@SpringBootTest` classes to unit tests and test slices. Or the team upgrades Spring Boot 3.5 to 4.x, updates JUnit/test dependencies, migrates Mockito bean overrides, and fixes imports. Afterward, Gradle reports all tests green. Can you conclude that behavior did not change?

**Not yet.** A test suite can stay green because:

- A critical assertion was dropped while splitting test classes.
- Both service and repository were mocked for a controller, leaving nothing to catch broken real wiring.
- A JSON response changed a field name while the new test only checks HTTP 200.
- `@Valid` was accidentally removed, allowing invalid requests straight through to the service.
- The JPA slice switched databases and missed a SQL dialect error.
- The new test relies on a stubbed mock returning the expected answer instead of running the logic under protection.
- Critical tests were filtered, skipped, or missed by CI test discovery.
- Snapshots/expected outputs were batch-updated without verifying intentional changes.
- Refactoring dropped security, transaction, or real HTTP tests that previously caught bugs.

To avoid losing proof when changing **how we test**, we need a baseline independent of **framework versions, test classes, and annotations**: a **behavior matrix**. Each row describes a contract the system must uphold, the triggering input or event, the observable result, the data scope, and which test supplies the evidence. Throughout migration, the matrix is the **source of truth**; test code is simply the implementation verifying each row.

> **Never use "all tests pass" as the sole criterion. Ask: "Does every mandatory behavior in the matrix still have valid proof?"**

This lesson belongs to **Versions and Migration**, on **"Keeping a Behavior Matrix as the Baseline When Refactoring or Upgrading a Test Suite"**.

### Objectives

After this lesson, you can:

1. Build a behavior matrix from requirements, historical bugs, public APIs, integration contracts, and business invariants.
2. Assign stable IDs `B01`, `B02`... to behaviors **without** coupling them to test method names.
3. Distinguish **external contracts** from implementation details that may change during refactoring.
4. Identify the primary test owner at unit, MVC slice, JPA slice, full-context, or real HTTP layers.
5. Use negative/boundary cases to catch the exact class of regression.
6. Execute the sequence: baseline → dual-run → ownership transfer → suite/gate execution → redundant test removal.
7. Separate intentional behavior changes from regressions and infrastructure/test-harness changes.
8. Navigate Spring Boot 3.5 → 4.x upgrades without assuming imports or dependencies stay unchanged.
9. Avoid treating auto-updated snapshots as false proof.
10. Track CI test discovery, skip counts, context caching, isolation, flaky tests, and rollback.
11. Apply a Java 17+, Spring Boot **3.5.16**, Gradle, JUnit Jupiter example with **25 `@Test` methods** across four layers tied back to one matrix.
12. Treat the behavior matrix as a **versioned testing asset**, not just a pretty table in docs.

**Version note:** the compilable sample code targets **Spring Boot 3.5.x / Spring Framework 6.x / Java 17+**. Spring Boot 4.0 modularizes test modules, packages, and starter names; the upgrade guidance explains migration, while **Boot 3.5 demo sources are not claimed to compile with unchanged imports on Boot 4**. When upgrading, use the matrix rows themselves as the standard for rewriting test adapters.

## 2. What Must a Behavior Matrix Row Specify?

A matrix should describe **observable, verifiable behavior**, rather than only test names or coverage percentages.

| Field | Purpose | Example |
|---|---|---|
| `ID` | Long-lived identifier | `B08` |
| `Contract` | Invariant behavior | Subtotal ≥ 10,000 gives shipping = 0 |
| `Stimulus/input` | Triggering input | `subtotal = 10,000, itemCount = 2, member = false` |
| `Expected observable` | Measurable outcome | `shipping = 0, total = 10,000` |
| `Boundary/negative` | Distinguishing edge cases | `9,999` and `10,001` |
| `Owner layer` | Primary proof location | Unit policy |
| `Cross-layer evidence` | Seam proof if needed | Full-context MockMvc |
| `Old evidence` | Pre-refactor/upgrade test | `LegacyQuoteSpringBootTest` |
| `New evidence` | New responsible test | `QuotePolicyTest.b08...` |
| `State` | `COVERED`/`GAP`/`INTENTIONAL_CHANGE` | `COVERED` |
| `Why/source` | Requirement, decision, bug | Free-shipping operational rule |

**Not every project needs all 11 columns**; what matters is that a reviewer can answer: *If someone intentionally breaks this condition, which test will fail?* And *after changing Spring Boot/JUnit/Mockito, does that still hold?*

### 2.1. Two Distinct Types of Change

**Changing how we test:** switching `@SpringBootTest` to `@WebMvcTest`, replacing `@MockBean` with `@MockitoBean`, changing assertion APIs, bumping plugins. **Expected behavior stays identical.**

**Changing product behavior:** the business lowers the free-shipping threshold from 10,000 to 8,000. **Expected behavior changes**, backed by requirements, approval, and migration notes. Never quietly alter an expected value just to make a test pass.

### 2.2. The Matrix Is the Standard, Not the Test File

A test method might be renamed from `shouldCreate()` to `b12_postReturnsCreated()`. An assertion library might switch from Hamcrest to AssertJ. Neither is a reason to delete contract `B12`.

When a contract truly no longer applies, mark it `RETIRED` with the decision and rationale. Never quietly delete a row just to keep test/coverage metrics looking clean.

## 3. Building the Matrix From Trustworthy Sources

An accurate matrix cannot be built merely by listing existing tests. Legacy tests may omit negative cases or assert implementation details. Sources should include:

1. Business requirements, acceptance criteria, and public API specifications.
2. Past production incidents—behaviors regression tests must continue catching.
3. Spring MVC request/response contracts: status codes, headers, JSON, validation, errors.
4. Data rules: schemas, unique constraints, query predicates, transaction semantics.
5. Security contracts: anonymous/authorized/forbidden, CSRF, filters, method authorization.
6. Configuration contracts: profiles, `@ConfigurationProperties` defaults/validation, conditional beans.
7. External contracts: HTTP/Kafka/DB protocols, retry and idempotency behaviors.
8. Timing/ordering definitions where genuine SLAs or concurrency invariants exist.
9. Existing tests, to inventory what is already protected and where gaps lie.
10. Framework changelogs and migration guides, to proactively audit high-risk areas.

**Do not enshrine buggy test behavior as the baseline simply because the test has existed for a long time.** Verify against requirements before freezing expectations.

### 3.1. Prioritizing by Risk

| Level | Examples | Proof Required |
|---|---|---|
| Critical | Money, balances, access control, idempotent payments | Negative, boundary, and real integration where needed |
| High | API errors, transaction boundaries, DB mappings | Proper layer test + cross-layer seam path |
| Medium | Formatting, optional defaults, read-only queries | Appropriate unit/slice tests |
| Low | Log phrasing, internal helper details | Test only if a real contract |

Do not use risk tiers to skip mandatory behaviors; use them to decide which boundaries require proof and how deeply to review.

## 4. Baseline Matrix for a Sample Feature

To practice, we build a quote-creation API. **Example business rules** (not representing real enterprise pricing/shipping policy):

- `subtotalCents` is non-negative.
- `itemCount` must be ≥ 1.
- If `member=true`, shipping = 0.
- If subtotal ≥ 10,000, shipping = 0.
- If not free and at least 3 items, shipping = 300.
- If not free and 1–2 items, shipping = 500.
- `totalCents = subtotalCents + shippingCents`.
- `POST /api/quotes` accepts valid JSON, returns 201 and `Location`.
- `GET /api/quotes/{id}` returns the saved quote or a stable 404 error.
- Missing/invalid requests return 400 with a stable error code.
- Repository persists/loads and queries the total threshold.
- Full-context path must wire real controller → real service → real repository.

### 4.1. Mandatory Matrix

| ID | Input / Condition | Expected Behavior | Primary Owner |
|---|---|---|---|
| B01 | `subtotal = -1` | Reject negative amount | Unit |
| B02 | `count = 0` or `-1` | Reject non-positive item count | Unit |
| B03 | `subtotal 2,000; count 1; member false` | `shipping 500; total 2,500` | Unit |
| B04 | `subtotal 2,000; count 2; member false` | `shipping 500; total 2,500` | Unit |
| B05 | `subtotal 2,000; count 3; member false` | `shipping 300; total 2,300` | Unit |
| B06 | `subtotal 2,000; count 4; member false` | `shipping 300; total 2,300` | Unit |
| B07 | `subtotal 9,999; count 2; member false` | `shipping 500; total 10,499` | Unit |
| B08 | `subtotal 10,000; count 2; member false` | `shipping 0; total 10,000` | Unit + seam |
| B09 | `subtotal 10,001; count 2; member false` | `shipping 0; total 10,001` | Unit |
| B10 | `subtotal 1; count 1; member true` | `shipping 0; total 1` | Unit |
| B11 | `subtotal 0; count 1; member false` | Valid; `shipping 500; total 500` | Unit |
| B12 | `POST` valid JSON | `201`; `Location`; body has `id` and totals | MVC slice + seam |
| B13 | `POST` missing `subtotal`/`count` or `count=0` | `400`; code `INVALID_REQUEST`; never calls service/DB | MVC slice + seam |
| B14 | `GET` existing `id` in repository | `200`; JSON matches saved quote | MVC slice + seam |
| B15 | `GET` nonexistent `id` | `404`; code `QUOTE_NOT_FOUND` | MVC slice + seam |
| B16 | Persist entity and query `total >= 10,000` | Correct ID/columns; inclusive boundary | JPA slice |
| B17 | `POST` → real service → real JPA → `GET` | End-to-end bean wiring in full-context MockMvc | Full seam |
| B18 | `POST` malformed JSON | `400`; code `MALFORMED_JSON` | MVC slice |

**Point to watch:** B13 has *multiple sub-cases*; each missing/invalid input deserves its own test so failures point straight to the cause. One matrix row can map to multiple test methods. Conversely, one full-context test can exercise B08, B12, B14, B16, and B17 together. **There is no rule forcing a 1-to-1 ratio of IDs to `@Test` methods.**

### 4.2. What Lies Outside the Demo Matrix

The demo uses H2, `MockMvc`, no Spring Security, no Docker/Kafka, and no real HTTP sockets. Consequently, it **does not** prove PostgreSQL dialects, JWT authorization, TLS, transactions across HTTP server threads, or external broker delivery. Where a real app requires those, add matrix rows and matching integration tests; never mark them `COVERED` based on the demo tests.

## 5. Layering Proof: Fast Tests Do Not Automatically Replace Integration Tests

| Layer | What the Test Sees | What It Usually Misses |
|---|---|---|
| Pure JUnit unit | Java branching, outputs, exceptions, fake/mock side effects | Spring bean scan / AOP / HTTP / SQL |
| `@WebMvcTest` | MVC routes, JSON binding, validation, status, advice | Real service if `@MockitoBean` replaces it |
| `@DataJpaTest` | JPA mapping, derived queries, DataSource/transaction slice | Controller/service cross-layer behavior |
| `@SpringBootTest` + MockMvc | Spring-managed beans, in-process MVC, real repository | TCP sockets / server port / TLS |
| `@SpringBootTest(RANDOM_PORT)` | Real embedded HTTP server/client boundary | Does not verify external systems by itself |
| Contract/external integration | Protocol/DB/broker behavior with real services | Does not replace pure unit edge cases |

Maintain **the matrix across all layers**; never treat an increase in unit test counts as a justification to delete full-context seam tests.

### 5.1. Assign Ownership by Behavior, Not by Tool

For instance, `B08` (the 10,000 threshold) has the policy unit test as its primary owner. A full seam test also exercises real policy wiring from controller → service → JPA so we know it was not bypassed or mocked out. You do not need to run full Spring contexts for all three values 9,999/10,000/10,001 once unit coverage is solid and the seam proves real wiring.

### 5.2. What Is Lost If You Drop Full-Context `MockMvc`?

A `@WebMvcTest` with `@MockitoBean QuoteService` still proves HTTP status/JSON, yet **never proves** the real service bean exists, the repository injects cleanly, or Spring AOP transaction advice runs. As long as the matrix includes `B17`, some test must traverse the real beans.

### 5.3. What Happens If PostgreSQL Is Replaced With H2?

A query running on H2 only proves it works on H2. If production relies on JSONB, collations, custom indexes, locks, or vendor-specific SQL, add matrix rows for the real production database and test with Testcontainers/matching dialects. Never write "JPA tested" generically if that boundary is uncovered.

## 6. What Changes Easily When Upgrading Spring Boot and Test Libraries?

### 6.1. Upgrading Spring Boot 3.5 to 4.x

The Spring Boot 4.0 migration guide highlights **modularized modules and test starters**. Key examples:

| Item | Spring Boot 3.5 | What to Check When Moving to Boot 4.x |
|---|---|---|
| Web starter | `spring-boot-starter-web` | `spring-boot-starter-webmvc` is the recommended name |
| Test dependencies | `spring-boot-starter-test` often covers many stacks | Technology-specific test starters, e.g., `spring-boot-starter-webmvc-test`, `spring-boot-starter-data-jpa-test` |
| Test annotations | `org.springframework.boot.test.autoconfigure...` | Test auto-configuration packages relocated under new technology modules |
| MVC test in full context | `@AutoConfigureMockMvc` in demo | Verify corresponding module and annotation |
| Mock annotations | Boot `@MockBean` deprecated since Boot 3.4 | Prefer Spring Framework `@MockitoBean`; review migration |
| Plain Mockito `@Mock` | May have relied on legacy listener/harness in some tests | Use `MockitoExtension` for pure Mockito tests |
| JSON mapping | Jackson 2 commonly used in Boot 3.5 | Boot 4 defaults to Jackson 3; review serialization/migrations |
| Rest test clients | `MockMvc`/`TestRestTemplate` depending on setup | Client/auto-config APIs changed; check docs/guides |
| JPA/validation | Boot-managed Hibernate/Validator | Check schema/query/constraint behavior after dependency bumps |

**Never treat this table as an automated import-rewriting script.** Check each module/config against the migration guide for your exact target release; Spring Boot 4.0 provides "classic starters" to ease incremental migration as an intermediate step, not as the final standard.

Even if test code changes packages completely, **B01–B18 must keep the same expected behavior** unless the product changed requirements. Only approved changes update the matrix.

### 6.2. Jakarta, Mockito, JUnit, and Jackson Also Affect Contracts

Upgrading dependencies can alter:

- Constraint validation and exception wrappers.
- Default error JSON, timestamps, null serialization, enum naming, and date/time formatting.
- Mockito stubbing matching, mock reset behavior, and bean override qualifiers.
- Test engine discovery, parameterized test sources, and extension initialization.
- JDBC/Hibernate SQL generation, schema validation, and transaction semantics.
- Spring TestContext cache keys and context customizers.
- Assertion library APIs (while the **asserted contract** must stay intact).
- Minimum runtime Java baseline; use the matching JDK/toolchain for the target branch.

**Never stop at checking compilation.** A test adapter with updated imports can still drop a field/status assertion or accidentally replace a production bean with a mock.

### 6.3. Recording "Which Revision Is the Baseline?"

A project can record minimal metadata in a README or ADR:

```text
Behavior matrix revision: 2026-11
Production API contract revision: checkout-quotes-v1
Baseline runtime: Java 17 / Spring Boot 3.5.x
Target runtime: Java supported by target Boot 4.x release
Test tools: JUnit Jupiter + Spring TestContext + Mockito
Behavior decision: B01-B18 unchanged
Known exception: none (or approved change ID)
```

This is a **metadata template**, not a specific project's live status. Never use the upgraded test suite itself as the sole source of expected results; reference approved requirements and ADRs.

## 7. An Auditable Migration Workflow

### Step 1 — Capture the Behavior Baseline

Before changing annotations or dependencies, run **the entire original test suite** on a known commit, JDK, and runtime. Record:

- Which Behavior IDs are currently proven.
- JUnit executed/passed/failed/skipped counts.
- HTTP statuses, headers, body fields, and validation error codes.
- Database query/transaction expectations.
- Security/auth/error contracts.
- Tests that are disabled, flaky, or order-dependent.
- Toolchain versions and CI job names.
- Raw JUnit XML/HTML, redacted logs, and test artifact links.

If the baseline already has failures, **do not** fabricate a fake "100% pass" baseline. Document failures/exceptions explicitly to separate preexisting defects from upgrade regressions.

### Step 2 — Map the Matrix to Legacy Owners

Map each behavior `Bxx` to its current test methods/suites. Any row lacking a test must be marked `GAP` rather than `COVERED` based on someone's memory that "it was tested once".

### Step 3 — Write New Tests While Keeping Legacy Tests

Implement unit/slice/full-seam tests under the new owners. **Run both** in the same codebase where feasible. Across major framework upgrades, two branches/JDKs may be needed: run baseline on the old branch and target on the new branch against the **same expected behavior matrix revision**.

### Step 4 — Verify Behavioral Equivalence, Not Just Pass Counts

An old test and a new test can both pass while testing different inputs. Compare **ID by ID**: stimulus, boundary, negative state, expected observable, and whether the intended system boundary still executes. If fixtures or source data changed, justify why the case remains equivalent.

### Step 5 — Remove Legacy Tests Only After New Owners Cover the Matrix

When moving B01–B11 to unit tests, ensure all edge cases transferred completely. Keep B17 in full-context or replace it with an integration test proving the same seam. Deleting duplicate tests makes sense; dropping behaviors forfeits coverage.

### Step 6 — Run Proper CI Gates

Run compile + unit + MVC/JPA slices + full integration smoke + security/external jobs where applicable. Inspect **JUnit XML test counts**, not merely a green or cached Gradle task. Track mutation/coverage trends where useful, remembering high scores alone do not prove matrix completeness.

### Step 7 — Sign Off on the Migration Decision

Document:

- Which IDs are unchanged.
- Which IDs changed intentionally (linked to requirements/approvals).
- Which IDs are known `GAP`s with actions and owners.
- Version and build changes.
- Baseline and target evidence links.
- CI execution counts and durations.
- Review date and owner responsible for keeping the matrix current.

## 8. Runnable Example: Build, File Tree, and Environment

To keep this concrete, we build a small REST + domain rule + Spring Data JPA application with four test suites mapped to the matrix.

**Environment used to author the example:** Java 17+, Spring Boot 3.5.16, JUnit Jupiter, AssertJ, Mockito, H2. **Complete code for all listed files**, requiring no Kafka, Docker, or external HTTP server.

### 8.1. File Tree

```text
behavior-contract-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/contract/
    │   │   ├── ContractDemoApplication.java
    │   │   ├── PriceBreakdown.java
    │   │   ├── QuotePolicy.java
    │   │   ├── QuoteEntity.java
    │   │   ├── QuoteRepository.java
    │   │   ├── QuoteResult.java
    │   │   ├── QuoteService.java
    │   │   ├── QuoteRequest.java
    │   │   ├── QuoteController.java
    │   │   ├── QuoteNotFoundException.java
    │   │   ├── ApiError.java
    │   │   └── QuoteErrorHandler.java
    │   └── resources/application.properties
    └── test/java/com/example/contract/
        ├── QuotePolicyTest.java
        ├── QuoteControllerWebMvcTest.java
        ├── QuoteRepositoryDataJpaTest.java
        └── QuoteFlowSpringBootTest.java
```

### 8.2. Gradle Groovy DSL

**File `settings.gradle`:**

```groovy
rootProject.name = 'behavior-contract-demo'
```

**File `build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Easy to observe for the demo and avoids multiple JVM forks.
    maxParallelForks = 1
    forkEvery = 0
}
```

**File `src/main/resources/application.properties`:**

```properties
# Demo local only; do not deploy H2 credentials/settings to production.
spring.datasource.generate-unique-name=true
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
```

The H2 runtime dependency and embedded database auto-configuration let JPA and full-context tests run without Docker. `generate-unique-name=true` gives each new embedded `DataSource` a unique name, preventing cached test contexts from accidentally sharing one in-memory H2 DB. Hibernate creates/drops the schema for the demo; production should use real migrations tested against the target database engine where needed.

**Note:** `build.gradle` does not generate a Gradle Wrapper by itself; you need a compatible Gradle installation to run `gradle test` or generate the wrapper. In real projects, H2/`ddl-auto` settings belong in **test configuration** rather than production `application.properties`; they sit in main resources here strictly so the demo runs standalone.

### 8.3. Test Method Totals

| Class | `@Test` Methods | Test Boundary |
|---|---:|---|
| `QuotePolicyTest` | 12 | Pure Java unit |
| `QuoteControllerWebMvcTest` | 7 | MVC slice, mocked service |
| `QuoteRepositoryDataJpaTest` | 3 | JPA slice, embedded H2 |
| `QuoteFlowSpringBootTest` | 3 | Full Spring context + MockMvc + JPA |
| **Total** | **25** | B01–B18, with some IDs having multiple tests |

**One method does not always equal one case** when using `@ParameterizedTest`. This sample intentionally uses separate `@Test` methods so ID mapping and test reports stay clear; later you can convert them to parameterized tests without altering the behavior matrix.

## 9. Production Code: Application and Price Policy

### 9.1. Application Entrypoint

**File `src/main/java/com/example/contract/ContractDemoApplication.java`:**

```java
package com.example.contract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContractDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContractDemoApplication.class, args);
    }
}
```

### 9.2. Immutable Breakdown

**File `src/main/java/com/example/contract/PriceBreakdown.java`:**

```java
package com.example.contract;

public record PriceBreakdown(
        int subtotalCents,
        int shippingCents,
        int totalCents
) {}
```

Java records provide value-based `equals`/`hashCode`, letting unit tests compare all fields cleanly against expected records. They do not guarantee serialization contracts—MVC tests must still verify JSON.

### 9.3. Pure Policy Managed by Spring Yet Independently Testable

**File `src/main/java/com/example/contract/QuotePolicy.java`:**

```java
package com.example.contract;

import org.springframework.stereotype.Component;

@Component
public class QuotePolicy {

    public PriceBreakdown price(
            int subtotalCents, int itemCount, boolean member) {

        if (subtotalCents < 0) {
            throw new IllegalArgumentException(
                    "subtotalCents must be nonnegative");
        }

        if (itemCount <= 0) {
            throw new IllegalArgumentException(
                    "itemCount must be positive");
        }

        int shippingCents;

        if (member || subtotalCents >= 10_000) {
            shippingCents = 0;
        }
        else if (itemCount >= 3) {
            shippingCents = 300;
        }
        else {
            shippingCents = 500;
        }

        return new PriceBreakdown(
                subtotalCents,
                shippingCents,
                Math.addExact(subtotalCents, shippingCents));
    }
}
```

**Core behaviors:** B01–B11. The class is annotated `@Component` so the full context injects it into the service, while pure unit tests can call `new QuotePolicy()` directly because the rule **uses no Spring proxies or configuration**. Never apply that shortcut to classes whose contract relies on `@Transactional`, `@PreAuthorize`, `@Cacheable`, or environment injection.

### 9.4. Boundary Cases Are the Key to the Matrix

If a refactor changes `subtotalCents >= 10_000` to `subtotalCents > 10_000`, B07 and B09 still pass while **B08 must fail**. If `itemCount >= 3` becomes `itemCount > 3`, B05 must fail. If the `member` check flips, B10 must fail. If the 500 fee becomes 0, B03/B04/B07/B11 must fail.

The matrix does not care whether code uses ternaries, `if/else`, `switch`, or a lookup table; it only cares that **inputs and outcomes remain exact**.

## 10. Production Code: JPA Persistence and Service

### 10.1. Entity and Mapping

**File `src/main/java/com/example/contract/QuoteEntity.java`:**

```java
package com.example.contract;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "quote_records")
public class QuoteEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "subtotal_cents", nullable = false)
    private int subtotalCents;

    @Column(name = "shipping_cents", nullable = false)
    private int shippingCents;

    @Column(name = "total_cents", nullable = false)
    private int totalCents;

    protected QuoteEntity() {
        // JPA constructor.
    }

    public QuoteEntity(
            int subtotalCents,
            int shippingCents,
            int totalCents) {
        this.subtotalCents = subtotalCents;
        this.shippingCents = shippingCents;
        this.totalCents = totalCents;
    }

    public Long getId() {
        return id;
    }

    public int getSubtotalCents() {
        return subtotalCents;
    }

    public int getShippingCents() {
        return shippingCents;
    }

    public int getTotalCents() {
        return totalCents;
    }
}
```

Never hardcode generated IDs like `1` in assertions; verify the ID is non-null/positive and reuse the returned ID for `GET`. Avoid fixtures assuming `AUTO_INCREMENT` sequencing across tests.

### 10.2. Spring Data JPA Repository

**File `src/main/java/com/example/contract/QuoteRepository.java`:**

```java
package com.example.contract;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface QuoteRepository
        extends JpaRepository<QuoteEntity, Long> {

    List<QuoteEntity> findByTotalCentsGreaterThanEqual(
            int minTotalCents);
}
```

This method uses an **inclusive boundary**. Upgrading Spring Data/Hibernate versions can alter SQL generation; the JPA slice verifies behavior on H2 in this demo. If production uses another dialect, B16's owner must run against that engine to verify compatibility.

### 10.3. Response DTO and Missing-Entity Exception

**File `src/main/java/com/example/contract/QuoteResult.java`:**

```java
package com.example.contract;

public record QuoteResult(
        long id,
        int subtotalCents,
        int shippingCents,
        int totalCents
) {}
```

**File `src/main/java/com/example/contract/QuoteNotFoundException.java`:**

```java
package com.example.contract;

public class QuoteNotFoundException
        extends RuntimeException {

    public QuoteNotFoundException(long id) {
        super("Quote " + id + " not found");
    }
}
```

Do not force clients to match exact exception message wording, as that is an internal implementation detail. HTTP clients rely on the stable code `QUOTE_NOT_FOUND` and 404 from controller advice.

### 10.4. Real Spring Service

**File `src/main/java/com/example/contract/QuoteService.java`:**

```java
package com.example.contract;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class QuoteService {

    private final QuotePolicy policy;
    private final QuoteRepository repository;

    public QuoteService(
            QuotePolicy policy, QuoteRepository repository) {
        this.policy = policy;
        this.repository = repository;
    }

    @Transactional
    public QuoteResult create(
            int subtotalCents, int itemCount, boolean member) {

        PriceBreakdown amount =
                policy.price(subtotalCents, itemCount, member);

        QuoteEntity saved = repository.save(
                new QuoteEntity(
                        amount.subtotalCents(),
                        amount.shippingCents(),
                        amount.totalCents()));

        return fromEntity(saved);
    }

    @Transactional(readOnly = true)
    public QuoteResult get(long id) {
        if (id <= 0) {
            throw new QuoteNotFoundException(id);
        }
        return repository.findById(id)
                .map(QuoteService::fromEntity)
                .orElseThrow(() ->
                        new QuoteNotFoundException(id));
    }

    private static QuoteResult fromEntity(QuoteEntity e) {
        return new QuoteResult(
                e.getId(),
                e.getSubtotalCents(),
                e.getShippingCents(),
                e.getTotalCents());
    }
}
```

**Why not unit-test the service alone?** `@Transactional` operates via a Spring-managed proxy. `new QuoteService(...)` does not verify the transaction interceptor. B17 uses the full Spring context to verify wiring and persistence. Complex rollback/commit propagation needs dedicated tests rather than assuming B17 covers all transaction semantics.

## 11. Production Code: HTTP Contracts and Error Codes

### 11.1. Validated Request

**File `src/main/java/com/example/contract/QuoteRequest.java`:**

```java
package com.example.contract;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record QuoteRequest(
        @NotNull @Min(0) Integer subtotalCents,
        @NotNull @Min(1) Integer itemCount,
        boolean member
) {}
```

Using boxed `Integer` instead of primitive `int` for the two required fields lets `@NotNull` distinguish **a missing key** from `0`. With primitive `int`, a missing key defaults to `0`; since `0` is valid for `subtotalCents`, a request omitting `subtotalCents` would be accepted wrongly. Contract B13 requires missing `subtotalCents` to return 400.

### 11.2. API Error Response

**File `src/main/java/com/example/contract/ApiError.java`:**

```java
package com.example.contract;

public record ApiError(
        String code,
        String message
) {}
```

In matrix rows B13/B15/B18, **the error code and HTTP status** form the contract. Messages may change with localization, though the sample uses fixed English messages for clarity. Never assert full stack traces or localized Hibernate Validator messages.

### 11.3. REST Controller

**File `src/main/java/com/example/contract/QuoteController.java`:**

```java
package com.example.contract;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<QuoteResult> create(
            @Valid @RequestBody QuoteRequest request) {

        QuoteResult result = service.create(
                request.subtotalCents(),
                request.itemCount(),
                request.member());

        URI location = URI.create("/api/quotes/" + result.id());

        return ResponseEntity.created(location)
                .body(result);
    }

    @GetMapping("/{id}")
    public QuoteResult get(@PathVariable long id) {
        return service.get(id);
    }
}
```

Spring MVC uses Jackson to deserialize the request record and serialize the response record. The controller performs no pricing math; policy stays inside the service. HTTP tests B12/B14 must verify JSON fields, status, and `Location`—policy unit tests cannot verify routing or serialization.

### 11.4. Stable Exception Handling

**File `src/main/java/com/example/contract/QuoteErrorHandler.java`:**

```java
package com.example.contract;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class QuoteErrorHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> validationError(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_REQUEST",
                        "Request validation failed"));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> malformedJson(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "MALFORMED_JSON",
                        "Invalid JSON body"));
    }

    @ExceptionHandler(QuoteNotFoundException.class)
    ResponseEntity<ApiError> quoteMissing(
            QuoteNotFoundException exception) {

        return ResponseEntity.status(404).body(
                new ApiError(
                        "QUOTE_NOT_FOUND",
                        "Quote not found"));
    }
}
```

**Why does explicit advice matter across version upgrades?** Default error payloads, localization, and media-type negotiation can change between framework releases. When an app **publishes** stable error codes and HTTP statuses, verify those contracts explicitly. If the team decides to adopt RFC Problem Details, treat that as an intentional API change requiring versioning/review of B13/B15/B18 rather than updating snapshots unconditionally.

## 12. Unit Tests: B01–B11 Without a Spring Context

**File `src/test/java/com/example/contract/QuotePolicyTest.java`:**

```java
package com.example.contract;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Tag("contract")
class QuotePolicyTest {

    private final QuotePolicy policy = new QuotePolicy();

    @Test
    void b01_negativeSubtotalIsRejected() {
        assertThatThrownBy(() ->
                policy.price(-1, 1, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("subtotalCents");
    }

    @Test
    void b02_zeroCountIsRejected() {
        assertThatThrownBy(() ->
                policy.price(1_000, 0, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("itemCount");
    }

    @Test
    void b02_negativeCountIsRejected() {
        assertThatThrownBy(() ->
                policy.price(1_000, -1, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("itemCount");
    }

    @Test
    void b03_oneItemPaysFullShipping() {
        assertThat(policy.price(2_000, 1, false))
                .isEqualTo(
                        new PriceBreakdown(2_000, 500, 2_500));
    }

    @Test
    void b04_twoItemsPayFullShipping() {
        assertThat(policy.price(2_000, 2, false))
                .isEqualTo(
                        new PriceBreakdown(2_000, 500, 2_500));
    }

    @Test
    void b05_threeItemsGetReducedShipping() {
        assertThat(policy.price(2_000, 3, false))
                .isEqualTo(
                        new PriceBreakdown(2_000, 300, 2_300));
    }

    @Test
    void b06_fourItemsKeepReducedShipping() {
        assertThat(policy.price(2_000, 4, false))
                .isEqualTo(
                        new PriceBreakdown(2_000, 300, 2_300));
    }

    @Test
    void b07_justBelowThresholdStillPays() {
        assertThat(policy.price(9_999, 2, false))
                .isEqualTo(
                        new PriceBreakdown(9_999, 500, 10_499));
    }

    @Test
    void b08_exactThresholdIsFree() {
        assertThat(policy.price(10_000, 2, false))
                .isEqualTo(
                        new PriceBreakdown(10_000, 0, 10_000));
    }

    @Test
    void b09_aboveThresholdIsFree() {
        assertThat(policy.price(10_001, 2, false))
                .isEqualTo(
                        new PriceBreakdown(10_001, 0, 10_001));
    }

    @Test
    void b10_memberGetsFreeShippingOnSmallOrder() {
        assertThat(policy.price(1, 1, true))
                .isEqualTo(
                        new PriceBreakdown(1, 0, 1));
    }

    @Test
    void b11_zeroSubtotalIsAllowed() {
        assertThat(policy.price(0, 1, false))
                .isEqualTo(
                        new PriceBreakdown(0, 500, 500));
    }
}
```

### 12.1. Why Do 12 Methods Prove 11 IDs?

B02 has **two negative cases** (zero and negative count). Two methods guard the same rule while preventing ambiguity on failure. Converting to `@ParameterizedTest` would yield one method with two invocations, while matrix row B02 **stays unchanged**.

### 12.2. Which Assertions Supply Proof?

- Comparing the full `PriceBreakdown` record protects subtotal, shipping, and total together.
- Uses exact boundaries `9,999`/`10,000`/`10,001`.
- Never asserts random UUIDs, IDs, or timestamps.
- Negative tests actually assert thrown exceptions; `notNull` alone would not guard the rule.
- B10 uses a small subtotal so free shipping comes from `member`, not accidentally from `>= 10,000`.
- Never alter expected outputs to match a buggy implementation.

**Limitation:** as a pure unit test, it does not verify whether Spring creates a `QuotePolicy` bean. B17 holds that proof.

## 13. MVC Slice: B12–B15 and B18

**File `src/test/java/com/example/contract/QuoteControllerWebMvcTest.java`:**

```java
package com.example.contract;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@Tag("contract")
@WebMvcTest(QuoteController.class)
class QuoteControllerWebMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    QuoteService service;

    @Test
    void b12_postReturns201LocationAndFullJson()
            throws Exception {
        when(service.create(9_999, 2, false))
                .thenReturn(new QuoteResult(
                        41L, 9_999, 500, 10_499));

        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "subtotalCents": 9999,
                      "itemCount": 2,
                      "member": false
                    }
                    """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "Location", "/api/quotes/41"))
                .andExpect(jsonPath("$.id").value(41))
                .andExpect(jsonPath("$.subtotalCents")
                        .value(9_999))
                .andExpect(jsonPath("$.shippingCents")
                        .value(500))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_499));

        verify(service).create(9_999, 2, false);
    }

    @Test
    void b13_missingSubtotalReturns400()
            throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"itemCount":1,"member":false}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));

        verifyNoInteractions(service);
    }

    @Test
    void b13_missingItemCountReturns400()
            throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"subtotalCents":2000,"member":false}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));

        verifyNoInteractions(service);
    }

    @Test
    void b13_zeroCountReturns400()
            throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"subtotalCents":2000,"itemCount":0}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));

        verifyNoInteractions(service);
    }

    @Test
    void b14_getKnownQuoteReturns200WithJson()
            throws Exception {
        when(service.get(41L))
                .thenReturn(new QuoteResult(
                        41L, 2_000, 300, 2_300));

        mvc.perform(get("/api/quotes/{id}", 41L))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(41))
                .andExpect(jsonPath("$.shippingCents")
                        .value(300))
                .andExpect(jsonPath("$.totalCents")
                        .value(2_300));

        verify(service).get(41L);
    }

    @Test
    void b15_missingQuoteReturns404StableCode()
            throws Exception {
        when(service.get(404L))
                .thenThrow(
                        new QuoteNotFoundException(404L));

        mvc.perform(get("/api/quotes/{id}", 404L))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("QUOTE_NOT_FOUND"));
    }

    @Test
    void b18_malformedJsonReturns400StableCode()
            throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{broken-json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_JSON"));

        verifyNoInteractions(service);
    }
}
```

### 13.1. Boundary of These Assertions

These tests exercise real Spring MVC dispatch, Jackson mapping, Bean Validation, and `QuoteErrorHandler`. `QuoteService` is replaced via `@MockitoBean` to keep DB/service rules out of scope:

- B12 protects HTTP semantics and DTO mapping.
- B13 proves invalid requests are blocked **before reaching the service**.
- B15 protects exception-to-HTTP-404/code mapping.
- B18 protects malformed JSON error responses.

Yet **they do not prove** `QuoteService` can be created/injected or that the database persists rows. B17/full seam owns that proof. When upgrading to Boot 4, the `@WebMvcTest` import and test starter may change; inputs and expected HTTP contracts **must not be altered** just to make code compile.

### 13.2. `@MockitoBean` vs. `@MockBean`

Spring Boot 3.5 supports Spring Framework 6.2 `@MockitoBean`. Boot `@MockBean` was deprecated in 3.4 in favor of `@MockitoBean`. That is a **test harness change**, not a behavior change. After migrating, verify the test genuinely overrides the intended bean rather than silently creating an extra mock that hides broken real wiring.

### 13.3. What If Spring Security Is Present?

This sample omits the security starter. In real applications, `@WebMvcTest` may activate security filters depending on configuration. Never strip `SecurityFilterChain` or mechanically set `addFilters=false` to make tests green. Add matrix rows for anonymous/authorized/forbidden/CSRF scenarios and maintain scoped security integration proof.

## 14. JPA Slice: B16 Verifies Persistence and Query Semantics

**File `src/test/java/com/example/contract/QuoteRepositoryDataJpaTest.java`:**

```java
package com.example.contract;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("contract")
@DataJpaTest
class QuoteRepositoryDataJpaTest {

    @Autowired
    QuoteRepository repository;

    @Autowired
    EntityManager entityManager;

    @Test
    void b16_persistThenClearReloadsActualMappedColumns() {
        QuoteEntity saved = repository.saveAndFlush(
                new QuoteEntity(2_000, 500, 2_500));

        Long id = saved.getId();
        assertThat(id).isNotNull();

        // Do not read only the same managed entity instance.
        entityManager.clear();

        QuoteEntity reloaded =
                repository.findById(id).orElseThrow();

        assertThat(reloaded.getSubtotalCents())
                .isEqualTo(2_000);
        assertThat(reloaded.getShippingCents())
                .isEqualTo(500);
        assertThat(reloaded.getTotalCents())
                .isEqualTo(2_500);
    }

    @Test
    void b16_queryIncludesExactThreshold() {
        repository.saveAndFlush(
                new QuoteEntity(9_700, 300, 10_000));
        repository.saveAndFlush(
                new QuoteEntity(9_000, 500, 9_500));

        assertThat(repository
                .findByTotalCentsGreaterThanEqual(10_000))
                .extracting(QuoteEntity::getTotalCents)
                .containsExactly(10_000);
    }

    @Test
    void b16_queryAboveAllRowsReturnsEmpty() {
        repository.saveAndFlush(
                new QuoteEntity(9_700, 300, 10_000));

        assertThat(repository
                .findByTotalCentsGreaterThanEqual(10_001))
                .isEmpty();
    }
}
```

### 14.1. Why Clear the Persistence Context?

After `saveAndFlush`, `findById` can return the exact managed instance sitting in the JPA first-level cache. `entityManager.clear()` forces an actual reload, making mapping and DB-readback verification meaningful. This still does not replace DB-level integration tests when real commit/isolation behavior must be verified.

### 14.2. `@DataJpaTest` Transaction Rollback

Spring Boot 3.5 `@DataJpaTest` is transactional by default and rolls back after each method. Thus all three tests create independent data without needing `@DirtiesContext`. Within the JPA slice, rows do not bleed from one test method to the next under standard test transactions.

**Limitation:** H2 does not guarantee compatibility with PostgreSQL JSONB/collations/locks or production migration scripts. When B16 requires a production dialect, use Testcontainers matching the engine/version and configure tests accordingly.

## 15. Full-Context Seam: B12–B17 Connecting Real Layers

**File `src/test/java/com/example/contract/QuoteFlowSpringBootTest.java`:**

```java
package com.example.contract;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@Tag("contract")
@SpringBootTest(classes = ContractDemoApplication.class)
@AutoConfigureMockMvc
@Transactional
class QuoteFlowSpringBootTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    QuoteRepository repository;

    @Autowired
    ObjectMapper mapper;

    @Test
    void b17_postThenGetUsesRealSpringBeansAndJpa()
            throws Exception {
        MvcResult created = mvc.perform(
                post("/api/quotes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "subtotalCents": 9999,
                          "itemCount": 2,
                          "member": false
                        }
                        """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.subtotalCents")
                        .value(9_999))
                .andExpect(jsonPath("$.shippingCents")
                        .value(500))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_499))
                .andReturn();

        long id = mapper.readTree(
                created.getResponse().getContentAsString())
                .get("id").asLong();

        assertThat(id).isPositive();
        assertThat(repository.findById(id)).isPresent();

        mvc.perform(get("/api/quotes/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(id))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_499))
                .andExpect(header().doesNotExist("Location"));
    }

    @Test
    void b13_invalidPostDoesNotPersist()
            throws Exception {
        long before = repository.count();

        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"subtotalCents":100,"itemCount":0}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));

        assertThat(repository.count()).isEqualTo(before);
    }

    @Test
    void b15_notFoundSurvivesFullContextWiring()
            throws Exception {
        mvc.perform(get(
                "/api/quotes/{id}", Long.MAX_VALUE))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("QUOTE_NOT_FOUND"));
    }
}
```

### 15.1. Why Must the Full-Context Seam Test Exist?

The unit policy knows nothing about Spring bean injection. The MVC slice mocks the service. The JPA slice runs neither controller nor service. The first test in this class proves **the whole chain**:

```text
POST JSON
   -> MVC request binding/validation
   -> real QuoteController bean
   -> real QuoteService Spring bean
   -> real QuotePolicy bean
   -> real QuoteRepository JPA bean
   -> H2 persistence
   -> GET same generated ID
   -> JSON response through MVC
```

This is the proof for B17. Removing `@Service` from `QuoteService` breaks component scanning/wiring; breaking JPA mappings/queries causes failures here. Converting the full suite into **only** MVC slices with `@MockitoBean QuoteService` would erase B17's proof.

### 15.2. Why Does `@Transactional` Provide Isolation Here?

The test uses `@SpringBootTest`'s **mock web environment** with `@AutoConfigureMockMvc`. Standard `MockMvc` requests execute on the same test thread; repository calls participate in the test-managed transaction and roll back after the method. That works cleanly for this demo.

**Do not generalize this to `RANDOM_PORT`:** when a client sends real HTTP over a socket to an embedded server, client/test threads and server threads differ; `@Transactional` on the test does not roll back server-side writes. When upgrading from `MockMvc` to real HTTP, add explicit cleanup/isolation while preserving related matrix rows.

### 15.3. Why Not Assert Exact Generated ID?

Hibernate/DBs may change ID strategies or sequences across upgrades. B12/B17 only require a valid ID, a `Location` pointing to that ID, and `GET` returning the matching entity. Hardcoding `ID = 1` couples assertions to an implementation detail without a business requirement on ID sequencing.

### 15.4. Seam Test Limitations

It opens no real HTTP socket, uses H2 instead of production PostgreSQL, and runs no security policies or Kafka. You can expand the matrix to those tiers based on product risk; never mark something "end-to-end production verified" just because one `MockMvc` path is green.

## 16. Mapping Test Code to B01–B18

| IDs | Sample Test Owners | Type of Proof |
|---|---|---|
| B01–B11 | `QuotePolicyTest.b01...b11...` (12 methods) | Domain policy and boundaries |
| B12 | `QuoteControllerWebMvcTest.b12...` | HTTP status, `Location`, JSON |
| B13 | Three `b13...` methods in MVC + one full negative | Missing/invalid inputs and zero persistence |
| B14 | `QuoteControllerWebMvcTest.b14...` + full `GET` path | `GET` JSON payload |
| B15 | `QuoteControllerWebMvcTest.b15...` + full missing ID | 404/error code and real wiring |
| B16 | Three `b16...` methods in JPA | Persist/clear/inclusive query |
| B17 | `QuoteFlowSpringBootTest.b17...` | Real controller/service/JPA wiring |
| B18 | `QuoteControllerWebMvcTest.b18...` | Malformed JSON → stable 400 error |

**Total methods = 12 + 7 + 3 + 3 = 25.** Several IDs have secondary owners to prevent blind spots across mocks or framework upgrades. In this code, the full seam does not directly test B08's exact threshold; B08 has its unit owner while the seam proves the production policy is genuinely wired using input 9,999. If the team requires dedicated cross-layer proof for B08 (e.g., a historical threshold bug after serialization), add a full-seam threshold test rather than marking it covered across layers before it exists.

### 16.1. Fix the Matrix Instead of Fabricating Coverage

Never write "B08 has full seam coverage" just because you feel a test ought to cover it. Section 4.1's matrix lists **unit + seam as target coverage**; the current code covers B08 at unit level and **general wiring** at the seam. When formalizing as a CI gate, record honestly:

```text
B08 | unit=PASS | cross-layer=GAP
    | action=add exact-threshold full seam only if required
```

or adjust the target owner to unit + indirect B17 seam if your team policy accepts it. Status must reflect reality. That is the core lesson of a matrix: **never cosmeticize evidence**.

### 16.2. A Hypothetical Review Scenario

A developer removes `@Valid` from `QuoteController`. The policy unit tests still pass; the JPA slice still passes. Yet MVC B13 tests must fail because invalid `POST` requests are no longer blocked; even if the unstubbed mock service causes a different status or 201, the status/code assertions turn red. Full B13 must also fail because `count=0` hits the domain exception instead of a structured 400.

A developer changes the derived query from `GreaterThanEqual` to `GreaterThan`. JPA B16's test at exactly `10,000` must fail.

A developer changes the policy threshold from `10,000` to `10,001`. Unit B08 fails. That is what proves the behavior matrix actually works.

## 17. Run Commands and Verifying Test Discovery

Linux/macOS, with an appropriate Gradle Wrapper:

```bash
./gradlew clean test

# Run each layer:
./gradlew test --tests "com.example.contract.QuotePolicyTest"
./gradlew test --tests "com.example.contract.QuoteControllerWebMvcTest"
./gradlew test --tests "com.example.contract.QuoteRepositoryDataJpaTest"
./gradlew test --tests "com.example.contract.QuoteFlowSpringBootTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
.\gradlew.bat test --tests "com.example.contract.QuotePolicyTest"
.\gradlew.bat test --tests "com.example.contract.QuoteControllerWebMvcTest"
.\gradlew.bat test --tests "com.example.contract.QuoteRepositoryDataJpaTest"
.\gradlew.bat test --tests "com.example.contract.QuoteFlowSpringBootTest"
```

When a real project uses Maven, configure a `pom.xml` with the Spring Boot BOM/parent, Maven Surefire, and JUnit Platform; use `./mvnw test` only when Maven Wrapper exists. Do not mix Gradle and Maven instructions into a single build without good reason.

### 17.1. Expected Results vs. Actual Results

**Expected by design:** 25 JUnit methods discovered and passing when environment, versions, and code align. The material was reviewed against API docs yet **was not compiled or executed via Gradle or JUnit during authoring**.

After running for real, inspect `build/test-results/test` and `build/reports/tests/test`. Before flipping matrix statuses to `PASS`, verify:

- Executed test count matches expectations (none lost to filters).
- `Failed=0`, `Error=0`.
- `Skipped=0` for mandatory tests.
- No known flaky failures masked by retries.
- Evidence matches the exact commit, JDK, and versions.
- Test results are not merely `UP-TO-DATE`/`FROM-CACHE` without traceability to a valid run.

### 17.2. Generating a Matrix Report After a Test Run

Teams can store metadata in CSV/Markdown/JSON, for example:

```text
id,contract,owner,baseline,target,status,notes
B01,negative-subtotal,QuotePolicyTest,pass,pass,COVERED,
B08,free-at-10000,QuotePolicyTest,pass,pass,COVERED,
B13,invalid-http-input,QuoteControllerWebMvcTest,pass,pass,COVERED,
B16,jpa-inclusive-query,QuoteRepositoryDataJpaTest,pass,pass,COVERED,
B17,real-wiring,QuoteFlowSpringBootTest,pass,pass,COVERED,
```

This is an **illustrative CSV from a hypothetical run**, not an automatically generated artifact. In practice, if a baseline or target run has not executed, fill in `NOT_RUN`/`UNKNOWN`—**never mark `pass` prematurely**. Done this way, the matrix remains independent of legacy test naming.

## 18. Comparing Baseline and Target in a Repeatable Workflow

A Boot 3.5 → 4.x upgrade PR can be reviewed via a table:

| ID | Baseline 3.5 | Target 4.x | Conclusion |
|---|---|---|---|
| B01–B11 | Actual PASS | Actual PASS | Behavior preserved |
| B12 | `POST` 201/`Location`/JSON | Same contract | If only status 201 remains → `GAP` |
| B13 | Missing values → 400 code | Same contract | If default error changed unexpectedly → regression |
| B15 | 404 code | Same contract | If advice failed to load, block merge |
| B16 | Inclusive query | Inclusive query | If dialect/SQL semantics changed, investigate |
| B17 | Real bean path | Real bean path | If mock replaced service → `GAP` |
| B18 | Malformed JSON 400/code | Same contract | If Jackson migration changed mapping, review |

**Every `PASS` in this table is illustrative logic**, not a report executed on Boot 4. Signing off for real requires CI artifacts from both branches tied to the matching matrix revision.

### 18.1. When Both Branches Fail on the Same ID

Do not immediately blame the upgrade for a regression. It could be a **pre-existing defect** or a broken test/environment. Compare root causes, verify the requirement, and classify as `PRE_EXISTING`—still never delete the ID simply because the bug is old.

### 18.2. When Baseline Passes and Target Fails

Classify before fixing:

- **Product regression:** contract genuinely broke.
- **Test harness migration:** wrong import, test dependency, extension, or test discovery.
- **Brittle test assumption:** test depended on DB ID ordering, locale, timestamps, raw SQL strings, or implementation details.
- **Intentional change:** approved requirement/API update.
- **Infrastructure failure:** container unavailable, CI network, cache/fork mismatch.

Fix the right layer. Never modify production code to satisfy a brittle assertion, and never weaken HTTP contracts just to turn all tests green.

### 18.3. When Target Passes Yet Tests Were Skipped

A green run where B17 **never executed** is not equivalent proof. Enforce CI test report and discovery gates; whenever changing test engines, packages, tags, or filters, confirm tests are still discovered. In Gradle, inspect XML reports; in Maven, inspect Surefire/Failsafe output.

## 19. Handling Intentional Behavior Changes

If the product genuinely lowers the free-shipping threshold from 10,000 to 8,000, B08 is no longer "free at 10,000 is the boundary". Never merely edit B08's expected value and move on.

The workflow should be:

1. Link the approved requirement, ADR, or issue.
2. Update the business contract statement and effective date/version.
3. Assess compatibility: are existing API consumers or historical data affected?
4. Update negative boundaries as well: `7,999` / `8,000` / `8,001`.
5. Identify consumers needing updates (API docs, SDKs, DB migrations, dashboards).
6. Mark the old B08 `SUPERSEDED` or revisioned without erasing history.
7. Create `B08-v2` or a new row if cross-version traceability is needed.
8. Run the owning tests and the full seam if boundaries changed.
9. Check impacts on caches, serialization, configs, and CI artifacts.
10. Record the approver, effective date, and version compatibility.

### 19.1. Do Not Turn Snapshots Into the Sole Source of Truth

Golden snapshots work well for long, stable JSON or document outputs. However, running `updateSnapshots` after an upgrade and committing every diff without reviewing semantic changes can **rubber-stamp regressions**.

For critical HTTP contracts, prefer explicit assertions on fields, status, headers, and error codes. Where snapshots are necessary:

- Canonicalize field order when ordering is not part of the contract.
- Mask dynamic timestamps, IDs, and ports when they are not part of the contract.
- Never mask protected fields (amounts, user roles, statuses).
- Review diffs with the business owner or consumer.
- Keep baseline vs. target snapshot diffs with documented reasons.
- Version snapshots when the API version genuinely changes.
- Never rely on an opaque snapshot hash as the sole proof.

## 20. Stability: Input Fixtures and Outputs Must Be Deterministic

A matrix has value only when the same stimulus produces a stable expected observable.

### 20.1. Common Sources of Nondeterminism

| Source | Risk During Upgrade / Refactor | Remedy |
|---|---|---|
| Current time | Timestamps change every run | Inject `Clock` or fixed time |
| Random UUIDs | Snapshots differ | Assert format / referential consistency |
| Generated JPA IDs | Increments differ across contexts | Assert non-null, then reuse the returned ID |
| Locale/timezone | Error messages or date JSON differ | Pin locale/zone when part of the contract |
| Unordered DB queries | Lists return in arbitrary order | Explicit `ORDER BY` or order-insensitive assertions |
| Parallel tests | Shared DB/mock/singleton state | Isolated data, serial groups, or proper locks |
| Cached `ApplicationContext` | Bean state leaks across methods | Reset state/rollback; avoid mutable singletons |
| Testcontainers mapped ports | Random host ports | `@ServiceConnection` / `@DynamicPropertySource` |
| External HTTP calls | Changing data/latency | Controlled contract stubs + dedicated integration jobs |
| Spring Security defaults | Different 401/403/CSRF behavior | Security-enabled tests matching real policy |
| H2 vs. PostgreSQL | Differing collations/SQL dialects | Real-dialect integration tests |
| Retries/timeouts | Flaky under CI CPU load | Deterministic schedules; wait for readiness |

### 20.2. Is `@DirtiesContext` the Standard Isolation Mechanism?

No. Spring TestContext caches contexts by metadata in the JVM. `@DirtiesContext` closes/evicts contexts; widespread use slows down suites and can trigger races under parallelism. For JPA slices and full-context MockMvc tests, transaction rollback and data cleanup are usually better. For Mockito, mock reset is better. For mutable singleton state, use explicit clear/restore APIs or intentionally separated contexts.

### 20.3. Test-Only Configuration Can Also Falsify Proof

If you want to test `@ConfigurationProperties` binding, do not replace the entire config with a Mockito mock. If you want to test authentication, do not disable security filters for convenience. If you want to test a database query, do not stub repository results. **Place test doubles outside the boundary; never mock the exact behavior under proof.**

## 21. Using Mutation Testing to Audit the Matrix

Mutation testing (e.g., PIT) checks whether tests react to small changes in production code.

Examples:

- Mutation `>= 10_000` → `> 10_000` must be caught by B08.
- Mutation `itemCount >= 3` → `itemCount > 3` must be caught by B05.
- Mutation `shipping = 500` → `shipping = 0` must be caught by B03/B04/B07/B11.
- Removing `@Valid` from a controller is not always a bytecode mutation generated by default PIT mutators, so MVC B13 remains essential.
- Changing a JPA query from `GreaterThanEqual` to `GreaterThan` affects Spring Data semantics, requiring JPA B16.
- Replacing a real bean with a mock is invisible to pure policy tests, requiring B17.

**Mutation score does not replace a behavior matrix.** It evaluates assertion strength on mutated Java bytecode. Many regressions in Spring wiring, protocols, annotations, migrations, or external systems are never simulated by default mutators.

### 21.1. Evaluating Whether Removing a Test Loses Behavior

Before deleting an old test, describe the mutation or failure mode that test originally caught. If the new owners still catch it, removing the duplicate makes sense. If not, mark a `GAP` and add the missing test before deleting—never judge solely by whether the total method count went up or down.

## 22. Matrix-Driven CI Gates, Not Just Pass Rates

A reliable migration CI pipeline needs layered checks:

1. **Compile/build** on the exact target Java, Spring Boot, Gradle, or Maven.
2. **JUnit execution:** test classes discovered with zero unapproved skips.
3. **Behavior coverage:** every required ID has an owner at the right boundary.
4. **Results:** required tests pass in valid environments.
5. **Cross-layer integrity:** seam, security, and external contracts have not been mocked away.
6. **Data/source compatibility:** schema migrations and serializers checked where needed.
7. **Stability:** never abuse retries to paper over flakiness.
8. **Evidence preservation:** archive reports and baseline-vs-target diffs.
9. **Approved exceptions:** intentional changes record reasons and versions.
10. **Performance:** track suite duration and context startups once correctness is secured.

### 22.1. Suggested Pipeline

```text
PR refactor / framework upgrade
          |
          v
  compile + unit + MVC + JPA + full smoke
          |
          +--> JUnit XML: executed/failed/skipped
          |
          +--> behavior matrix validation
          |       required IDs with real owners?
          |       baseline vs target expectations?
          |
          +--> security/DB/container contract jobs (if needed)
          |
          +--> optional PIT/coverage trends
          |
          v
       approve / block

Periodic audit:
  inspect tests marked disabled, flaky and matrices with GAP
```

Basic command for the sample Gradle project:

```bash
./gradlew clean test
# Collect build/test-results/test and build/reports/tests/test
```

This is a **conceptual pipeline**, not prebuilt GitHub Actions/GitLab/Jenkins YAML. Matrix mapping checks in PRs can be manual or automated via test naming/metadata parsers—just make sure parsers do not mark `COVERED` merely because a method exists in source without actually executing.

### 22.2. Never Mark `PASS` From Source Code Alone

An article contains unexecuted sample code, so its actual state is `NOT_RUN`. Achieving `COVERED` in CI requires a verified run result, proper test selection, and matching expectations. Naming a method `b17_...` aids owner traceability, **not runtime certification**.

## 23. Common Mistakes When Migrating a Test Suite

| Anti-Pattern | Why Protection Is Lost | Proper Practice |
|---|---|---|
| Replacing all `@SpringBootTest` with unit tests | Drops Spring wiring proof | Keep full seam B17 |
| Asserting HTTP 200 while dropping JSON assertions | Serialization regressions slip through | B12/B14 assert exact fields |
| Mocking `QuoteService` in every test | Eliminates real policy/JPA path | Unit policy + full seam |
| JPA test saves and finds in the same persistence context | First-level cache hides DB readback | Flush + clear + reload |
| Green H2 test called PostgreSQL-compatible | SQL dialects differ | Testcontainers real DB where needed |
| Auto-updating snapshots on Jackson upgrade | Rubber-stamps response bugs | Review diffs per `Bxx` |
| Swapping `@MockBean` to `@MockitoBean` without checking target | May create mock hiding missing bean | Review override policy |
| Fixing only imports when upgrading to Boot 4 | Test engine/module/default behaviors may shift | Check matrix, test discovery, dependencies |
| Removing `@Valid` so MockMvc tests stop failing | Invalid requests leak through | Preserve B13 |
| Dropping `@Transactional` without checking data leakage | Order-dependent tests | Explicit cleanup/rollback |
| Running `RANDOM_PORT` assuming `@Transactional` rolls back server writes | Client/server threads differ | Separate cleanup |
| Asserting generated ID must equal `1` | Fragile across DB changes | Assert valid ID/referential consistency |
| Matching full localized exception messages | Locale/framework text is not a contract | Stable error codes |
| Putting `@DirtiesContext` on every class | Cache thrashing, slow/racy runs | Reset actual resources properly |
| Using unique inline properties on every test | Fragments context cache | Standardize equivalent configs |
| Counting skipped tests as PASS | False green | CI executed/skip gates |
| Tracking only total test counts | New tests may verify different behaviors | Map by ID |
| Deleting a retired ID without recording it | Loss of traceability | Mark `RETIRED`/`SUPERSEDED` with reason |
| Changing expected results to match unapproved new behavior | Test legitimizes regression | Review requirements first |
| Replacing semantic asserts with opaque snapshot hashes | Hard to see what changed | Assert status/fields/side effects |
| Chasing 100% code coverage | Coverage does not prove assertion strength | Behavioral negative/boundary + mutation |
| CI runs tests only on an older JDK instead of target | Upgrade target remains unverified | Explicit test toolchain matrix |
| Auto-retrying flaky tests and reporting green | Masks isolation bugs | Diagnose root causes |
| Leaving security out of the matrix | Zero proof of auth enforcement | Dedicated security integration tests |
| Skipping docs/API consumer updates after behavior changes | Contract drift | Versioning + compatibility plans |

## 24. Practice Exercises and Solutions

### A. Refactoring a Full Test Into a Unit Test

**Exercise:** After converting a controller→service→repository test into policy unit tests, B01–B11 all pass. Can the old full-context test be deleted?

**Answer:** Only if the wiring, persistence, and HTTP requirements guarded by the old test have a new owner. B17 still requires a seam test exercising real Spring-managed beans; policy unit tests cannot replace it.

### B. Upgrading Boot 3.5 to 4.x

**Exercise:** `@WebMvcTest` changed packages, so a developer deletes the MVC test class to make the build pass. Are B12/B13/B14/B15/B18 still `COVERED`?

**Answer:** No, unless another test proves those exact HTTP contracts. Add the matching test starter and updated import per the migration guide while keeping the same test inputs and expectations.

### C. Replacing JSON Assertions With Status Checks

**Exercise:** Old B12 asserted 201, `Location`, `id`, `shipping`, and `total`. The new test asserts only 201.

**Answer:** B12 lost proof. Any JSON or `Location` regression can slip through. Mark `GAP` for the dropped assertions or restore them.

### D. Modifying a Threshold Condition

**Exercise:** A developer changes `subtotal >= 10_000` to `subtotal > 10_000`. Which test must turn red?

**Answer:** B08 exact boundary; B07 and B09 may stay green.

### E. Modifying a JPA Query

**Exercise:** A derived query changes from `GreaterThanEqual` to `GreaterThan`. Will the policy unit tests catch it?

**Answer:** No. JPA B16's inclusive query test at `10,000` must catch it.

### F. Error JSON Changes After a Jackson Upgrade

**Exercise:** Previously the API returned `{"code":"INVALID_REQUEST"}`; after an upgrade it returns default HTML or Problem Details while keeping HTTP status 400.

**Answer:** If the stable error code is part of the contract, this is a B13 regression; restore the advice/content negotiation or approve an API version change rather than editing snapshots.

### G. More Test Methods Than Before

**Exercise:** Before refactoring there were 100 tests; afterward there are 160. Is coverage definitely better?

**Answer:** Not necessarily. What matters are contract IDs, test boundaries, and assertion strength. A hundred tests asserting `notNull` cannot replace 10 tests with negative and boundary proofs.

### H. `@DataJpaTest` Transaction Rollback

**Exercise:** Why isn't `@DirtiesContext` needed after each JPA slice method?

**Answer:** `@DataJpaTest` uses test-managed transaction rollback by default to isolate row mutations. However, do not assume rollback covers external systems, separate threads, or non-transactional schema modifications.

### I. `RANDOM_PORT` and Transactions

**Exercise:** A test sends a real HTTP `POST` creating a row while `@Transactional` is on the JUnit test. Does the row roll back automatically?

**Answer:** Not guaranteed, because the server runs its transaction on a separate thread. Use explicit cleanup or isolated DBs for live HTTP tests.

### J. Nondeterministic Data in Snapshots

**Exercise:** JSON includes a random generated ID, making snapshots fail on every run.

**Answer:** Do not strip the ID completely if referential consistency is part of the contract. Assert the ID is valid, reuse the returned ID in `GET` and verify it matches, and drop any brittle "`ID` must always be 1" rule.

### K. Test Name Changes

**Exercise:** `shouldWork()` is renamed to `b12_post...`. Does contract B12 need to change?

**Answer:** No. B12 is a business/API contract ID independent of method names; just update the owner mapping if needed.

### L. Known Failure in Baseline

**Exercise:** B15 was already failing before the upgrade. Should you say Boot 4 caused a B15 regression?

**Answer:** Not automatically. Mark it `PRE_EXISTING` and investigate; only if the root cause changed is it a target regression. Do not delete the ID.

### M. Batch Snapshot Updates

**Exercise:** Upgrading a JSON library causes 40 snapshot diffs, and a developer runs update-all.

**Answer:** Do not approve blindly. Classify diffs against public contracts, normalize non-contract fields, and review intentional changes. If B12/B13/B14/B15 changed semantics, formal approval is required.

### N. Mock Service in an MVC Test

**Exercise:** MVC B12 returns the expected JSON from a Mockito stub. Does that prove `QuotePolicy.price` is correct?

**Answer:** No. Policy unit tests B01–B11 and full seam B17 are still required. Stubbing only proves the controller maps requests and responses per contract.

### O. Full Seam Running on H2

**Exercise:** Production uses PostgreSQL, and the full seam passes on H2. Can you conclude transactions and SQL are production-compatible?

**Answer:** No. Real PostgreSQL migration/query tests are needed wherever contracts involve database-specific semantics.

### P. JUnit Tests Skipped After Upgrade

**Exercise:** Gradle reports `BUILD SUCCESSFUL` yet executed only 20/25 methods due to a tag filter.

**Answer:** Fails the gate if those 5 methods are mandatory. Fix test discovery/tags/job wiring and re-run; never mark `COVERED` without execution proof.

## 25. QA Checklist for Reviewing PRs or Framework Upgrades

- [ ] Does the matrix have stable IDs, contracts, inputs, expected results, owners, and requirement sources?
- [ ] Are historical bugs and key boundary/negative cases included?
- [ ] Are `COVERED`/`GAP`/`INTENTIONAL_CHANGE`/`RETIRED` states explicit?
- [ ] Are behavior contracts independent of test names and framework packages?
- [ ] Was a real baseline executed on an identified version, JDK, and source commit?
- [ ] Was a real target run executed on an identified version, JDK, and source commit?
- [ ] Were JUnit executed/passed/failed/skipped counts verified instead of checking only green status?
- [ ] Are zero unexecuted source tests marked `PASS`?
- [ ] Do all required IDs still have test owners at the right boundaries?
- [ ] Do unit tests preserve input boundaries and specific expected outputs?
- [ ] Do MVC tests preserve status, `Location`, headers, JSON fields, and error codes?
- [ ] Do invalid MVC tests verify the service was not called where appropriate?
- [ ] Do repository tests execute real SQL/JPA instead of mocking the repository?
- [ ] Is flush/clear/reload used where needed to prevent JPA first-level cache false positives?
- [ ] Are SQL dialect questions backed by real-DB tests if production differs from H2?
- [ ] Does the cross-layer seam still exercise real controller/service/repository beans?
- [ ] Are mocks kept out of the exact layer being proven?
- [ ] Are security/CSRF/filter tests retained when the product has security contracts?
- [ ] Are transaction/cache/AOP behaviors covered by Spring-managed integration tests where needed?
- [ ] Are real HTTP tests kept intact when TCP/container behavior is part of the contract?
- [ ] Is `@Transactional` rollback never misattributed to `RANDOM_PORT` server threads?
- [ ] Do migration guides, dependencies, test starters, and imports match the exact target Boot version?
- [ ] Are `@MockitoBean` declarations targeted accurately without silently hiding missing production beans?
- [ ] Are Jackson/validation error codes verified with semantic assertions?
- [ ] Are dynamic IDs, time, locales, and ordering handled so snapshots never flake?
- [ ] Are blind "update all" snapshot updates rejected without review?
- [ ] Do intentionally changed IDs have approvals, API versions, and compatibility notes?
- [ ] Are known pre-existing failures separated from target regressions?
- [ ] Are context cache keys, mock overrides, and test profiles controlled?
- [ ] Are test data, singletons, mocks, and static state cleaned up with zero order dependence?
- [ ] Do JUnit/Gradle/Maven fork and parallel configs preserve full test discovery?
- [ ] Does CI preserve evidence artifacts and baseline-target comparison links?
- [ ] Does mutation testing supplement rather than replace the behavior matrix?
- [ ] Are runtime/CI performance metrics measured after correctness is verified?
- [ ] Are fixtures, logs, and reports free of credentials and PII?
- [ ] Do all `GAP` rows have owners and plans to add tests?
- [ ] Are legacy tests never deleted before transferring all needed behavior ownership?
- [ ] Are Java 17+/Boot 3.5 samples and migrated Boot 4 code reviewed against their respective versions?

## 26. Conclusion

**A behavior matrix is the fixed anchor while testing tools and framework versions evolve.** It records what the application **must do**, without tying that contract permanently to a specific test class, annotation, or assertion library.

- Build the matrix from real requirements and historical bugs, not just existing test names.
- Give every row input, boundary, expected observable, owner, and evidence.
- Keep unit, slice, and full-context tests in their proper roles; never mock away a boundary that needs proof.
- When upgrading Spring Boot, JUnit, Jackson, or Mockito, update imports and test starters as needed, yet **never change expected business/API outcomes by default**.
- Compare baseline and target runs backed by JUnit XML/CI evidence; never let skipped or disabled tests masquerade as `PASS`.
- Distinguish product regressions, harness migrations, brittle assertions, intentional changes, and infrastructure failures.
- When behavior truly changes, version/review the matrix alongside API consumers instead of quietly deleting rows or regenerating snapshots.
- Protect negative/boundary cases, real wiring, persistence, and security contracts appropriately.

The Java 17+/Spring Boot 3.5.16 example provides **25 JUnit Jupiter methods**: 12 pure policy tests, 7 MVC slice tests, 3 JPA slice tests, and 3 full-context seam tests. Together they show how one `B01–B18` set distributes across layers while preserving traceability. **The code was reviewed against documentation and has not yet been compiled or executed with JUnit during authoring**; before using it as a real CI baseline, run it and archive the reports in your target environment.

## 27. Official References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, test slices, `MockMvc`, and rollback/real HTTP.
- [Spring Boot 3.5 — Test Slices Appendix](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): auto-configuration list per test slice.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): modular test starters, API/package changes, MockMVC/Mockito/Jackson migration notes.
- [Spring Framework 6.2 — TestContext Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): context key, reuse, LRU/default 32, and `@DirtiesContext`.
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): test-managed rollback, thread boundaries, `TestTransaction`.
- [Spring Framework 6.2 — `@MockitoBean`/`@MockitoSpyBean`](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): bean overrides, qualifiers, cache keys, and mocks.
- [Spring Boot 3.5 — MockBean API deprecation](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): migrating to `@MockitoBean`.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): derived queries and property method parsing.
- [JUnit 5 — User Guide](https://docs.junit.org/5.13.0/user-guide/): test discovery, annotations, parameterized tests, execution options.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): test task, filtering, JUnit Platform, and reports.
