# Isolating Business Logic from @Scheduled for Independent Testing

A method annotated with **`@Scheduled`** that simultaneously reads system time, queries the database, decides who is overdue, sends emails, and catches all its own exceptions usually produces an uncontrollable test suite: you must wait for real schedule ticks, rely on the CI host's clock, depend on pre-existing DB data, struggle to test failure paths, and risk duplicate runs when multiple application instances run concurrently. A sustainable design treats **`@Scheduled` strictly as an inbound adapter/trigger**, while the business logic lives in a **directly callable use case** in Java receiving a **`Clock`** and **ports/interfaces** for external dependencies.

This lesson belongs to the **Async and Scheduling** group of **Spring Boot - testing**. Its goal is **separating business logic from `@Scheduled` for independent testing**. Examples use **Java 17, Spring Boot 3.4.5, Spring Framework 6.2, JUnit Jupiter, and Mockito**, centered on the use case **deactivating expired trial accounts**. All business rules are tested with `Clock.fixed` and an in-memory repository, without waiting for cron, starting a server, or sleeping for a single second. A separate test verifies that the `@Scheduled` adapter invokes the service exactly once; a Spring context test verifies the job can be **disabled in tests** via a property.

One crucial distinction to remember: **passing business tests do not prove cron/scheduler wiring works**, and **testing the `@Scheduled` annotation does not prove the business logic works**. Those are two distinct contracts requiring distinct tests with clear scopes.

## 1. What is @Scheduled actually responsible for?

Spring Framework reads **`@Scheduled`** on **Spring-managed beans** when scheduling is enabled (typically via **`@EnableScheduling`**) and registers the task with a **`TaskScheduler`**. At trigger time, the scheduler invokes the annotated method. A typical `@Scheduled` method:

- Accepts no method parameters.
- Normally returns **`void`**; normal return values from scheduled invocations are unused by the framework.
- Can configure `cron`, `fixedDelay`, or `fixedRate`; do not arbitrarily combine all three on one annotation.
- Runs on a scheduler thread; by default Spring Boot 3.4 uses a single-threaded `ThreadPoolTaskScheduler` when virtual threads are off and no custom `TaskScheduler` exists.
- Does not guarantee single execution across a cluster; **every JVM/application instance can register the same job**.
- Does not automatically provide business retries, idempotency, distributed locking, transactions, or exactly-once delivery.
- Does not solve business timezones or clock injection; cron trigger timezone is distinct from the business timestamp used to evaluate expiration.

A typical annotation:

~~~java
@Scheduled(cron = "0 0 * * * *", zone = "UTC")
public void run() {
    // invoke service, do not place long business logic here
}
~~~

**Spring cron has six fields: second, minute, hour, day of month, month, day of week**. The expression **`0 0 * * * *`** means **the top of every hour** in the configured timezone. It is **not** the five-field Unix cron syntax used by some other systems.

### Desired layered diagram

~~~text
Spring scheduler / cron / fixedDelay
                |
                v
        TrialExpirationJob
       [inbound scheduling adapter]
        - does not read database
        - does not compute expiration time
        - calls service, logs result
                |
                v
      TrialExpirationService
         [business use case]
        - obtains Instant.now(clock)
        - finds active expired accounts
        - applies expiration policy
        - calls repository conditional update
        - returns actual changed count
                |
                v
       TrialAccountRepository
          [outbound port]
                |
                v
      InMemory / JDBC / JPA adapter
~~~

When testing:
- **Service unit test:** invoke **`expireDueTrials()`** directly, passing **`Clock.fixed`** and a fake repository.
- **Job adapter test:** instantiate the job via constructor with a mocked service, invoke **`run()`** directly; assert proper delegation.
- **Spring wiring test:** boot context with job disabled via property, assert no job bean is registered in test mode.
- **Scheduler integration test (when needed):** enable scheduling in an isolated test environment, observe triggers and concurrency via synchronization/signals, without arbitrary `Thread.sleep`.

## 2. Anti-pattern: cramming business logic into @Scheduled

**Broken pattern, for analysis only:**

~~~java
@Component
class ExpirationJob {
    private final AccountRepository repository;
    private final EmailSender email;

    @Scheduled(cron = "0 0 * * * *")
    public void expireAndNotify() {
        Instant now = Instant.now();

        for (Account account : repository.findActiveAccounts()) {
            if (account.expiresAt().isBefore(now)) {
                account.disable();
                email.sendExpiredNotice(account.email());
                repository.save(account);
            }
        }
    }
}
~~~

This is a **counter-example snippet**, not a runnable file from the project below. Problems to point out:

1. **Hard-coded `Instant.now()`:** unit tests checking whether an account is due or overdue must rely on real time or sleep, easily failing at second/minute boundaries.
2. **Logic coupled to the scheduler:** to test expiration rules, people end up trying to wait for cron instead of calling a service.
3. **Too many responsibilities:** scheduling, querying, deadline policy, email, and persistence all in one class.
4. **No idempotency:** the same account could receive two emails when multiple nodes run in parallel.
5. **Side-effect ordering risk:** sending email before a failing DB save can send duplicates on retry; saving first then failing to send email can drop notifications.
6. **Unbounded batch:** `findActiveAccounts()` may scan the entire table.
7. **No timezone context:** default cron may follow runtime timezone while "expiration" relies on UTC `Instant`.
8. **Hard to diagnose:** when a test fails, you do not know whether the scheduler, timestamp, email adapter, or database broke.

**Architectural fix:** a thin scheduled method merely invokes the use case. The business service obtains time via `Clock`, the repository performs conditional updates, and external notifications (if any) use a port/outbox tested separately.

## 3. The @Scheduled adapter is an infrastructure detail, not a business API

Name, signature, and responsibility:

~~~java
@Component
public class TrialExpirationJob {
    private final TrialExpirationService service;

    public TrialExpirationJob(TrialExpirationService service) {
        this.service = service;
    }

    @Scheduled(cron = "0 0 * * * *", zone = "UTC")
    public void run() {
        service.expireDueTrials();
    }
}
~~~

This is a **structural snippet**; the full class with enablement condition and logger is in Section 6.10.

**The business service needs no knowledge of `@Scheduled`.** It can be invoked from:
- a scheduler on a periodic schedule;
- an admin endpoint needing a controlled manual rerun;
- a CLI maintenance command;
- an integration test or job test;
- a message consumer receiving a trigger.

That is the architectural payoff: **triggers can change while business policy remains independently testable**.

Do not put **`@Scheduled`** on the business method and call that method directly claiming you tested the scheduler. Calling it directly only proves the Java method body; the annotation is read by Spring when registering tasks on the bean. Likewise, `Mockito.verify(service).expireDueTrials()` only proves the adapter delegates, **not that it ran automatically on schedule**.

## 4. Defining business rules testable without real time

The sample lesson picks clear rules:
- A `TrialAccount` has **`id`, `expiresAt: Instant`, `active: boolean`**.
- At instant **`now`**, an account must be deactivated if **`active == true`** and **`expiresAt <= now`**.
- An account expiring **exactly at `now`** is also deactivated (inclusive boundary).
- Already inactive accounts are not counted again.
- Accounts not yet expired remain untouched.
- **Each run** processes at most **`batchSize`** accounts; remaining accounts are handled in subsequent runs.
- A conditional update call may return **`false`** because another worker already processed the account; the service counts only actual changes.
- Running the use case twice consecutively must not deactivate the same account twice.

Use **`Instant`** (absolute point in time) for expiration; use **`Clock`** to obtain `now`. **Timezones are only for converting local schedules to `Instant` or interpreting cron**, never comparing timezone-less `LocalDateTime` values across users in different regions.

### Defining exact comparison boundaries

~~~text
now = 2026-05-01T10:00:00Z

Trial A: expiresAt=09:59:59Z, active=true   -> deactivate
Trial B: expiresAt=10:00:00Z, active=true   -> deactivate
Trial C: expiresAt=10:00:01Z, active=true   -> keep active
Trial D: expiresAt=09:00:00Z, active=false  -> unchanged

First run: changed = 2
Re-run at same now: changed = 0
~~~

These are static fixture values for reasoning, **not real observed stdout**. Cron might fire at 10:00:02 under scheduler load; the service still uses the timestamp supplied by `Clock` and a consistent business condition.

## 5. @Scheduled: are cron, fixedDelay, and fixedRate the same?

| Attribute | Meaning | Good fit | Common mistake |
| --- | --- | --- | --- |
| **`cron`** | Runs by calendar expression, with timezone | Top of every hour, daily, weekdays | Confusing 5-field cron with Spring's 6 fields |
| **`fixedDelay`** | Waits interval from **previous completion** to next start | Polling that must rest after each batch | Thinking it runs evenly from start times |
| **`fixedRate`** | Fires at cadence measured from planned start times | Lightweight tasks needing steady cadence | Assuming strict precision without drift or overlap |
| **`initialDelay`** | Delays first run for `fixedRate`/`fixedDelay` | Waiting for app warm-up | Using it to cure races instead of explicit readiness |
| **`zone`** | Time zone for cron | Schedules in business timezones | Confusing trigger timezone with business `Clock` |
| **`timeUnit`** | Unit for numeric `fixedDelay`/`fixedRate`/`initialDelay` | Avoiding millisecond mix-ups | Applying to cron even though cron ignores it |

**Illustrative** examples, not placed simultaneously on the same method:

~~~java
@Scheduled(fixedDelayString = "PT30S")
public void pollThirtySecondsAfterPreviousFinish() {
    service.expireDueTrials();
}
~~~

~~~java
@Scheduled(fixedRateString = "PT1M", initialDelayString = "PT10S")
public void pollByFixedCadence() {
    service.expireDueTrials();
}
~~~

~~~java
@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void runEveryLocalDayAtTwoAm() {
    service.expireDueTrials();
}
~~~

These snippets **only illustrate trigger options**; they are not in the runnable project, which uses a single UTC cron. **`PT30S`/`PT1M`/`PT10S`** are ISO-8601 duration strings supported by Spring. When using `fixedRate` across multiple scheduled tasks or `@Async`, inspect the scheduler pool, job duration, and concurrency; **never assume a `cron`/`fixedRate` automatically locks all cluster instances**.

### What happens if a job runs long?

- **`fixedDelay`:** starts counting the next delay only after the current invocation finishes.
- **`fixedRate`:** the framework attempts to keep the periodic cadence, yet busy scheduler threads/pools can cause delays; no strict real-time promise.
- **`cron`:** triggers by calendar schedule and timezone, without guaranteeing execution begins at the exact microsecond.
- **Tasks running across multiple replicas:** each replica has its own scheduler; two may process the same business object simultaneously.
- **Multiple `@Scheduled` annotations on the same method:** Spring registers each declaration independently, which can create overlapping triggers.

Designing **idempotent** rules, repository conditional updates, and metrics/alerts matters far more than trying to measure exact cron milliseconds in a unit test.

## 6. Complete Java 17 + Spring Boot 3.4.5 project

The project uses a **`ConcurrentHashMap` storage adapter solely for illustration**. It lets the example run without PostgreSQL, Docker, email, or external APIs. In production, swap in a JDBC/JPA repository with **atomic conditional `UPDATE`**, transactions, and durable state. The scheduler is **OFF** by default and enabled intentionally via an application property.

### 6.1. File tree

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/jobs/TrialJobsApplication.java
src/main/java/com/example/jobs/ClockConfig.java
src/main/java/com/example/jobs/TrialAccount.java
src/main/java/com/example/jobs/TrialAccountRepository.java
src/main/java/com/example/jobs/InMemoryTrialAccountRepository.java
src/main/java/com/example/jobs/TrialExpirationService.java
src/main/java/com/example/jobs/TrialExpirationJob.java
src/test/java/com/example/jobs/TrialExpirationServiceTest.java
src/test/java/com/example/jobs/TrialExpirationJobTest.java
src/test/java/com/example/jobs/SchedulerDisabledWiringTest.java
~~~

### 6.2. Gradle settings and dependencies

**settings.gradle**

~~~groovy
rootProject.name = 'scheduled-business-isolation'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**`spring-boot-starter`** suffices for `ApplicationContext`, scheduling infrastructure, and logging. No `starter-web` is needed without HTTP controllers; no `data-jpa` is needed since demo storage is in-memory. **`spring-boot-starter-test`** includes JUnit Jupiter/Mockito for unit and Spring context tests. The **Spring Boot BOM** manages compatible versions across dependencies.

### 6.3. Safe default configuration

**src/main/resources/application.yml**

~~~yaml
app:
  jobs:
    trial-expiration:
      enabled: false
      cron: "0 0 * * * *"
      zone: "UTC"
      batch-size: 100

spring:
  task:
    scheduling:
      thread-name-prefix: "trial-jobs-"
      pool:
        size: 1
~~~

**`enabled=false`** is intentional: creating the project or running tests will not mutate data on a background schedule. In a real deployment, enable the job via configuration or command-line args on authorized environments. Do not enable schedules across all profiles or on every replica without evaluating duplicates/concurrency.

**`cron`** and **`zone`** are injected into `@Scheduled` via placeholders. **`batch-size`** goes into the service via constructor; unit tests pass 100 or 2 directly without Spring `Environment`.

### 6.4. Application class enabling scheduling infrastructure

**src/main/java/com/example/jobs/TrialJobsApplication.java**

~~~java
package com.example.jobs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class TrialJobsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TrialJobsApplication.class, args);
    }
}
~~~

**`@EnableScheduling`** tells Spring to register `@Scheduled` processing. It **does not force the job bean to exist**: the job bean has **`@ConditionalOnProperty`**, so by default it is not created. Conversely, putting `@Scheduled` on a manually instantiated object (`new`) in a unit test **does not** make the scheduler invoke it automatically.

### 6.5. Injected Clock, no scattered Instant.now() calls

**src/main/java/com/example/jobs/ClockConfig.java**

~~~java
package com.example.jobs;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockConfig {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

**Production:** `Clock.systemUTC()` reflects system time.

**Tests:** `Clock.fixed(Instant.parse(...), ZoneOffset.UTC)` provides an immutable instant, letting unit tests verify an account expiring right at **`expiresAt == now`** without waiting on a clock. For domains tied to local dates/times, `Clock` makes DST/timezone testing explicit.

**Do not mock `Instant.now()` as a global static** when you can inject `Clock`; static mocks have complex scoping and easily leak state across test methods.

### 6.6. Domain record

**src/main/java/com/example/jobs/TrialAccount.java**

~~~java
package com.example.jobs;

import java.time.Instant;
import java.util.Objects;

public record TrialAccount(
        String id,
        Instant expiresAt,
        boolean active) {

    public TrialAccount {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException(
                    "id must not be blank");
        }
        Objects.requireNonNull(expiresAt, "expiresAt");
    }
}
~~~

**`Instant`** is an absolute moment on the UTC timeline, not a timezone-less `LocalDateTime`. Validation in the compact constructor keeps input data consistent. **`active`** transitions from true to false when processed by the job, and never flips back to true inside this service.

### 6.7. Repository port: business logic independent of JDBC/JPA

**src/main/java/com/example/jobs/TrialAccountRepository.java**

~~~java
package com.example.jobs;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface TrialAccountRepository {

    void save(TrialAccount account);

    List<TrialAccount> findActiveDue(Instant now, int limit);

    boolean deactivateIfDue(String accountId, Instant now);

    Optional<TrialAccount> findById(String accountId);
}
~~~

**`findActiveDue`** queries a candidate list up to `limit`, containing only active expired accounts. **`deactivateIfDue`** must enforce the conditional state transition **`active=true AND expiresAt <= now`** at update time; returning **`true` when actually modified**, `false` otherwise. Conditioning the update is critical because another worker may intervene between the candidate query and the update.

A production repository adapter might use SQL:

~~~sql
UPDATE trial_accounts
SET active = false
WHERE id = :id
  AND active = true
  AND expires_at <= :now;
~~~

**Affected row count = 1** means this worker performed the transition; **0** means the row does not exist, is not due yet, or was already processed by another worker. With JPA, use transactions and watch for stale persistence contexts when running bulk updates. This is **illustrative SQL**, not a script run in the demo; `:id`/`:now` are named parameters matching Spring Data/`JdbcTemplate` named-parameter syntax, not positional JDBC `?` placeholders.

**Do not assume from `findActiveDue` alone that the update will succeed.** Always count based on the conditional update result.

### 6.8. In-memory storage adapter using ConcurrentHashMap

**src/main/java/com/example/jobs/InMemoryTrialAccountRepository.java**

~~~java
package com.example.jobs;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.stereotype.Repository;

@Repository
public class InMemoryTrialAccountRepository
        implements TrialAccountRepository {

    private final ConcurrentHashMap<String, TrialAccount> rows =
            new ConcurrentHashMap<>();

    @Override
    public void save(TrialAccount account) {
        rows.put(account.id(), account);
    }

    @Override
    public List<TrialAccount> findActiveDue(
            Instant now, int limit) {
        return rows.values().stream()
                .filter(TrialAccount::active)
                .filter(a -> !a.expiresAt().isAfter(now))
                .sorted(Comparator
                    .comparing(TrialAccount::expiresAt)
                    .thenComparing(TrialAccount::id))
                .limit(limit)
                .toList();
    }

    @Override
    public boolean deactivateIfDue(
            String accountId, Instant now) {
        AtomicBoolean changed = new AtomicBoolean(false);

        rows.computeIfPresent(accountId, (id, current) -> {
            if (current.active()
                    && !current.expiresAt().isAfter(now)) {
                changed.set(true);
                return new TrialAccount(
                    current.id(), current.expiresAt(), false);
            }
            return current;
        });

        return changed.get();
    }

    @Override
    public Optional<TrialAccount> findById(String accountId) {
        return Optional.ofNullable(rows.get(accountId));
    }
}
~~~

**`ConcurrentHashMap.computeIfPresent`** performs an atomic **per-key** update within a single JVM. The candidate query is a snapshot/iteration that can go stale in concurrent scenarios, so the **conditional update** must re-check the condition. The service's count reflects only the worker that actually flipped state, not the number of candidates read.

**Important:** The demo adapter is not durable, shares no state across replicas, runs no database transactions, and holds no distributed locks. It is sufficient to learn **architecture and deterministic tests**. In production, replace it with a PostgreSQL/MySQL/JPA adapter and conditional SQL updates; use database tests/Testcontainers to verify real concurrency and isolation.

### 6.9. Business service independent of scheduler

**src/main/java/com/example/jobs/TrialExpirationService.java**

~~~java
package com.example.jobs;

import java.time.Clock;
import java.time.Instant;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class TrialExpirationService {

    private final TrialAccountRepository repository;
    private final Clock clock;
    private final int batchSize;

    public TrialExpirationService(
            TrialAccountRepository repository,
            Clock clock,
            @Value("${app.jobs.trial-expiration.batch-size:100}")
            int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException(
                    "batchSize must be positive");
        }
        this.repository = repository;
        this.clock = clock;
        this.batchSize = batchSize;
    }

    public int expireDueTrials() {
        Instant now = Instant.now(clock);

        List<TrialAccount> candidates =
                repository.findActiveDue(now, batchSize);

        int changed = 0;
        for (TrialAccount candidate : candidates) {
            if (repository.deactivateIfDue(
                    candidate.id(), now)) {
                changed++;
            }
        }
        return changed;
    }
}
~~~

**Separation of concerns:**
- The service owns the business rules for `dueAt`/`expiresAt`, limits, and transitions.
- The service **does not import `@Scheduled`, never sleeps, spawns no threads, and never parses cron expressions**.
- **`Clock`** supplies the evaluation instant; captured **once at the start of the run** so all candidates share the same cutoff. Even if a batch runs for a few seconds, policy remains consistent as of run start.
- **`Repository` port** handles queries/updates, so it can be faked in unit tests or backed by JPA/JDBC in integration tests.
- Return value is the **count of successful state transitions**, not records scanned or notifications sent.

**Intentional limitation:** If due accounts exceed `batchSize` and cron runs hourly, clearing the backlog may take multiple runs. Production requires appropriate polling cadence, pagination/claiming strategies, and metrics. Do not alter business logic to depend on the scheduler period; the service must remain callable repeatedly or manually.

### 6.10. Conditional scheduled adapter with logging

**src/main/java/com/example/jobs/TrialExpirationJob.java**

~~~java
package com.example.jobs;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    prefix = "app.jobs.trial-expiration",
    name = "enabled",
    havingValue = "true")
public class TrialExpirationJob {

    private static final Logger log =
            LoggerFactory.getLogger(TrialExpirationJob.class);

    private final TrialExpirationService service;

    public TrialExpirationJob(TrialExpirationService service) {
        this.service = service;
    }

    @Scheduled(
        cron = "${app.jobs.trial-expiration.cron:0 0 * * * *}",
        zone = "${app.jobs.trial-expiration.zone:UTC}")
    public void run() {
        int changed = service.expireDueTrials();
        log.info("trial expiration completed changed={}", changed);
    }
}
~~~

**This is a "thin" method**: no SQL, no iterating accounts, no `Instant.now()`, no `dueAt` math or email calls. Business failures propagate out of `run()`; Spring's scheduler infrastructure logs/handles exceptions per configuration, without **implying immediate retries**. Production requires explicit metrics, alerts, and retry strategies.

**`@ConditionalOnProperty(... havingValue="true")`**: creates the bean only when **`app.jobs.trial-expiration.enabled=true`**. When absent or false (with `matchIfMissing` defaulting to false), the bean is not created, so no annotated method exists for scheduling infrastructure to register. This keeps all default unit/context tests **from automatically running schedules**.

**Do not use `Thread.sleep` waiting for `@Scheduled` to fire** when all you want to verify is "run delegates once". Simply call **`new TrialExpirationJob(serviceMock).run()`** directly and verify. Direct invocation does not prove Spring registered the trigger — that is a separate contract.

## 7. Business unit tests with Clock.fixed and real in-memory repository

**src/test/java/com/example/jobs/TrialExpirationServiceTest.java**

~~~java
package com.example.jobs;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class TrialExpirationServiceTest {

    private static final Instant NOW =
            Instant.parse("2026-05-01T10:00:00Z");

    private InMemoryTrialAccountRepository repository;
    private Clock clock;
    private TrialExpirationService service;

    @BeforeEach
    void setUp() {
        repository = new InMemoryTrialAccountRepository();
        clock = Clock.fixed(NOW, ZoneOffset.UTC);
        service = new TrialExpirationService(
                repository, clock, 100);
    }

    @Test
    void expiresPastAndExactlyDueButNotFutureOrInactive() {
        repository.save(new TrialAccount(
                "past", NOW.minusSeconds(60), true));
        repository.save(new TrialAccount(
                "exact", NOW, true));
        repository.save(new TrialAccount(
                "future", NOW.plusSeconds(1), true));
        repository.save(new TrialAccount(
                "already-inactive", NOW.minusSeconds(3600), false));

        assertEquals(2, service.expireDueTrials());

        assertFalse(repository.findById("past")
                .orElseThrow().active());
        assertFalse(repository.findById("exact")
                .orElseThrow().active());
        assertTrue(repository.findById("future")
                .orElseThrow().active());
        assertFalse(repository.findById("already-inactive")
                .orElseThrow().active());

        // Re-running with the same Clock: no second transition.
        assertEquals(0, service.expireDueTrials());
    }

    @Test
    void usesInjectedClockWithoutSleep() {
        repository.save(new TrialAccount(
                "soon", NOW.plusSeconds(10), true));

        assertEquals(0, service.expireDueTrials());
        assertTrue(repository.findById("soon")
                .orElseThrow().active());

        Clock laterClock = Clock.fixed(
                NOW.plusSeconds(11), ZoneOffset.UTC);
        TrialExpirationService later =
                new TrialExpirationService(
                    repository, laterClock, 100);

        assertEquals(1, later.expireDueTrials());
        assertFalse(repository.findById("soon")
                .orElseThrow().active());
    }

    @Test
    void appliesBatchSizeAndCanProcessBacklogInNextRun() {
        repository.save(new TrialAccount(
                "a", NOW.minusSeconds(30), true));
        repository.save(new TrialAccount(
                "b", NOW.minusSeconds(20), true));
        repository.save(new TrialAccount(
                "c", NOW.minusSeconds(10), true));

        TrialExpirationService batched =
                new TrialExpirationService(
                    repository, clock, 2);

        assertEquals(2, batched.expireDueTrials());
        assertFalse(repository.findById("a")
                .orElseThrow().active());
        assertFalse(repository.findById("b")
                .orElseThrow().active());
        assertTrue(repository.findById("c")
                .orElseThrow().active());

        assertEquals(1, batched.expireDueTrials());
        assertFalse(repository.findById("c")
                .orElseThrow().active());
        assertEquals(0, batched.expireDueTrials());
    }

    @Test
    void countsOnlySuccessfulConditionalUpdates() {
        TrialAccountRepository contended =
                mock(TrialAccountRepository.class);

        when(contended.findActiveDue(NOW, 100))
            .thenReturn(List.of(
                new TrialAccount(
                    "claimed-elsewhere", NOW, true)));

        when(contended.deactivateIfDue(
                "claimed-elsewhere", NOW))
            .thenReturn(false);

        TrialExpirationService underTest =
                new TrialExpirationService(
                    contended, clock, 100);

        assertEquals(0, underTest.expireDueTrials());
        verify(contended).deactivateIfDue(
                "claimed-elsewhere", NOW);
    }

    @Test
    void repositoryFailureIsNotSilentlyReportedAsSuccess() {
        TrialAccountRepository failing =
                mock(TrialAccountRepository.class);

        IllegalStateException outage =
                new IllegalStateException("database unavailable");

        when(failing.findActiveDue(NOW, 100))
            .thenThrow(outage);

        TrialExpirationService underTest =
                new TrialExpirationService(
                    failing, clock, 100);

        IllegalStateException actual = assertThrows(
                IllegalStateException.class,
                underTest::expireDueTrials);
        assertSame(outage, actual);
    }

    @Test
    void rejectsZeroOrNegativeBatchSize() {
        assertThrows(IllegalArgumentException.class,
                () -> new TrialExpirationService(
                    repository, clock, 0));

        assertThrows(IllegalArgumentException.class,
                () -> new TrialExpirationService(
                    repository, clock, -5));
    }
}
~~~

### Value of each test

**`expiresPastAndExactlyDueButNotFutureOrInactive`** proves all four boundary zones (past, exact, future, inactive) and that re-running causes no duplicate effect. This is business policy, requiring no real cron.

**`usesInjectedClockWithoutSleep`** uses two `Clock.fixed` instances for two different instants without waiting 11 seconds. Had the project called `Instant.now()` directly, this test would depend on machine wall time; `Clock` injection eliminates the root cause.

**`appliesBatchSizeAndCanProcessBacklogInNextRun`** proves a single run processes at most two rows and the next run drains the backlog. It does not wait for the next scheduled trigger.

**`countsOnlySuccessfulConditionalUpdates`** simulates a race: the query sees the row, yet another worker flipped the state before update, so the repository returns `false`. The service returns `changed=0` instead of counting a phantom candidate.

**`repositoryFailureIsNotSilentlyReportedAsSuccess`** proves infrastructure outages are not swallowed and falsely reported as `count=0`. Schedulers can log/alert per policy. **`@Scheduled` by itself does not provide business retries**.

**`rejectsZeroOrNegativeBatchSize`** proves invalid config is caught early. All tests are plain JUnit; **no `@SpringBootTest`**, no Docker, database, mail server, or scheduler threads.

## 8. Unit testing the scheduled adapter: no waiting for cron

**src/test/java/com/example/jobs/TrialExpirationJobTest.java**

~~~java
package com.example.jobs;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class TrialExpirationJobTest {

    @Mock
    private TrialExpirationService service;

    private TrialExpirationJob job;

    @BeforeEach
    void setUp() {
        job = new TrialExpirationJob(service);
    }

    @Test
    void delegatesOneRunToBusinessServiceOnce() {
        when(service.expireDueTrials()).thenReturn(3);

        job.run();

        verify(service, times(1)).expireDueTrials();
    }

    @Test
    void doesNotSwallowBusinessFailure() {
        IllegalStateException failure =
                new IllegalStateException("database unavailable");

        when(service.expireDueTrials()).thenThrow(failure);

        IllegalStateException thrown = assertThrows(
                IllegalStateException.class, job::run);

        assertSame(failure, thrown);
        verify(service, times(1)).expireDueTrials();
    }
}
~~~

**This is an adapter test, not a trigger timing test.** The job is instantiated directly without a Spring context, so `@Scheduled` is not registered with a scheduler. Calling `job.run()` and verifying the service once proves the thin adapter does its job. Mocking the service needs no `Clock` or repository since those belong to `TrialExpirationServiceTest`.

**Do not use `@MockBean`/`@MockitoBean` to spin up an entire `ApplicationContext` just to verify a single call**. When you genuinely need to check Spring bean wiring, a separate test fits better (Section 9).

### Distinguishing service outcomes from triggers

If cron changes from hourly to every minute while business logic stays the same, **`TrialExpirationServiceTest` must still PASS** because expiration rules do not depend on the schedule. If the service changes from `expiresAt <= now` to `expiresAt < now`, the exact-boundary unit test must FAIL. If the scheduled adapter forgets to call the service, **`TrialExpirationJobTest` FAILS**. Each test group guards the exact layer it owns.

## 9. Spring context test: disabling the job to prevent side effects in the suite

**src/test/java/com/example/jobs/SchedulerDisabledWiringTest.java**

~~~java
package com.example.jobs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(properties = {
    "app.jobs.trial-expiration.enabled=false",
    "app.jobs.trial-expiration.batch-size=2"
})
class SchedulerDisabledWiringTest {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private TrialExpirationService service;

    @Test
    void businessBeanIsWiredButScheduledAdapterAbsent() {
        assertNotNull(service);
        assertEquals(
            0,
            context.getBeanNamesForType(
                TrialExpirationJob.class).length);
    }
}
~~~

**What this proves:** the application still creates the business service and its dependencies, while the job adapter **is not created** because the property is false. Thus the test suite can run without a background job unexpectedly deactivating test data.

**Do not try to prove the annotation runs on schedule using `Thread.sleep` in `@SpringBootTest`.** When real trigger wiring must be tested, create a separate integration test context with `enabled=true`, scheduler-aware assertions, and deterministic synchronization, while isolating DB/resources so it does not interfere with other tests.

### Why is a property guard better than a far-future cron?

A cron like "Jan 1 at 00:00" can still fire if CI runs right at that boundary, especially in different timezones. **`@ConditionalOnProperty`** ensures the job bean does not exist when disabled; that is explicit and proactive proof. The special cron value **`"-"`** can also disable a trigger via property, yet with it **the bean still exists**; the two mechanisms serve different purposes.

## 10. Running tests without starting a real scheduler

With JDK 17+, a compatible Gradle Wrapper, and dependencies matching `build.gradle`:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.jobs.TrialExpirationServiceTest
./gradlew test --tests com.example.jobs.TrialExpirationJobTest
./gradlew test --tests com.example.jobs.SchedulerDisabledWiringTest
./gradlew test --tests com.example.jobs.TrialExpirationServiceTest.expiresPastAndExactlyDueButNotFutureOrInactive
~~~

On Windows, use **`gradlew.bat`** with the corresponding arguments. The tests are designed to PASS per the code when files/packages/dependencies match the lesson; **an actual Gradle execution run is not claimed to have been observed**.

### Table of expected outcomes

| Test | Contract proven |
| --- | --- |
| `expiresPastAndExactlyDueButNotFutureOrInactive` | past/exact due become inactive, future stays active, inactive unchanged, second run `changed=0` |
| `usesInjectedClockWithoutSleep` | Different `Clock` changes result without sleep |
| `appliesBatchSizeAndCanProcessBacklogInNextRun` | Each run ≤2; backlog processed 2+1; final run 0 |
| `countsOnlySuccessfulConditionalUpdates` | Race `update=false` is not counted |
| `repositoryFailureIsNotSilentlyReportedAsSuccess` | Dependency exception propagates |
| `rejectsZeroOrNegativeBatchSize` | Invalid configuration is rejected |
| `delegatesOneRunToBusinessServiceOnce` | Job delegates exactly once |
| `doesNotSwallowBusinessFailure` | Job does not turn error into fake success |
| `businessBeanIsWiredButScheduledAdapterAbsent` | Spring wires business bean, omits scheduled bean when disabled |

**You do not need to run the application and wait for the top of the hour** to test business logic. If a test can only pass by waiting for cron, that signals mixed responsibilities or a scheduling integration test lacking proper synchronization.

## 11. Running the real application and enabling the schedule safely

Default configuration keeps the job disabled. To enable it in a safe environment with test data:

~~~bash
./gradlew bootRun --args='--app.jobs.trial-expiration.enabled=true'
~~~

When enabled, the `@Scheduled` trigger registers on the Spring-managed bean and runs per cron/zone. **By default there are no accounts in the in-memory repository** because the demo seeds no startup data, so the job only logs `changed=0` until logic adds accounts. That is intentional: the example focuses on architecture and testability rather than generating fake production data.

You can override the cron property via argument:

~~~bash
./gradlew bootRun --args='--app.jobs.trial-expiration.enabled=true --app.jobs.trial-expiration.cron=0 */5 * * * *'
~~~

**Note shell and Spring Boot Gradle plugin quoting:** for cron expressions containing spaces, shells and command-line parsers may require different escaping/quoting. In production projects, configure cron via controlled YAML/environment config rather than complex shell commands. To avoid ambiguity, the demo uses the default cron from `application.yml`.

**Do not switch the business clock from UTC to local timezone just because cron uses a local timezone.** The business clock uses `Instant` and the UTC timeline; if a rule says "expires at 00:00 in the user's timezone", convert the user's `LocalDate` + `ZoneId` into an `Instant` explicitly in the business layer and unit-test DST boundaries.

## 12. @Scheduled and @Async are not the same mechanism

**`@Scheduled`** selects **when to trigger** a method. **`@Async`** (when enabled via `@EnableAsync`) runs a method on an **async executor**. The two annotations have distinct roles:

| Concern | `@Scheduled` | `@Async` |
| --- | --- | --- |
| Time-based trigger | Yes | No |
| Runs on a thread other than caller | `TaskScheduler` thread | Executor thread |
| Automatic business retry | No | No |
| Automatic transaction propagation across threads | Not by default | Not by default |
| Easy to unit-test business logic in plain JUnit | When separated into a service | When separated into a service |
| Can run concurrently across multiple instances | Yes | Yes |
| Requires observing completion/errors | Yes | Yes |

Putting both `@Scheduled` and `@Async` on the same method easily complicates lifecycle control, overlapping invocations, and exception propagation. The demo avoids doing so. If a job must run concurrently, use a **queue/claim strategy**, durable state, and bounded concurrency rather than treating `@Async` as a fix for race conditions.

Spring Boot configures **`spring.task.scheduling`** for `TaskScheduler` and **`spring.task.execution`** for `AsyncTaskExecutor`. The two namespaces are not interchangeable. In Java 21+ with virtual threads, Boot may pick a different scheduler implementation; this lesson uses **Java 17** without virtual-thread mode enabled.

## 13. Why should unit tests not sleep?

A test like:

~~~java
awaitSomeSeconds();
verify(notificationService, times(1)).send(...);
~~~

is an anti-pattern when the real goal is computing "has it expired?". It:
- runs slowly every time;
- depends on CI load and machine wall time;
- fails easily when cron hasn't ticked yet;
- can be affected by timezones/DST;
- cannot distinguish whether the scheduler failed to fire or the service computed wrongly.

**Replace with `Clock.fixed` + direct service invocation**. For real scheduling integration tests, use Awaitility, `CountDownLatch`, or test-specific trigger instrumentation to wait for an **observable condition** with a bounded timeout. Even then, those are infrastructure tests — fewer cases, not every business scenario.

### Testing an on-time run without waiting for the scheduler

~~~java
Instant target = Instant.parse("2026-05-01T10:00:00Z");
Clock fixedClock = Clock.fixed(target, ZoneOffset.UTC);

TrialExpirationService service =
    new TrialExpirationService(repository, fixedClock, 100);

assertEquals(2, service.expireDueTrials());
~~~

This is a **snippet** fully realized in `TrialExpirationServiceTest`. Results depend on fixture data and the injected `Clock`, **not the OS clock**.

## 14. Do not confuse unit tests with Spring registration tests

A test:

~~~java
TrialExpirationJob job = new TrialExpirationJob(mockService);
job.run();
verify(mockService).expireDueTrials();
~~~

only tests the **adapter method**. Spring does not manage that object, and `@Scheduled` is not registered. Conversely, a `@SpringBootTest` enabling cron and seeing a log that the job ran does not prove the **`expiresAt <= now`** policy or idempotency is correct.

### When is a schedule registration integration test needed?

When a change involves:
- cron placeholder binding and syntax;
- timezone/cron DST behavior;
- `@ConditionalOnProperty` enable/disable;
- custom `TaskScheduler` bean or scheduler pool;
- bean scanning, `@EnableScheduling`, `@Profile`;
- distributed lock/leader election integration;
- task exceptions, metrics, actuator/observability;
- concurrency/backpressure when multiple schedules run together.

One strategy:
1. Boot an isolated context with `enabled=true` and a scheduling test-only configuration.
2. Use a test service/fake event recorder, or `@MockitoBean` if overriding a Spring bean is necessary.
3. Configure a short trigger **only in that test context**, not in the default app.
4. Wait for an observable event with a finite timeout via Awaitility/latch and assert the invocation.
5. Close the context/stop the scheduler and clean up data so other tests are unaffected.

**Do not require every unit test to enable the scheduler** just to check an annotation. Design one or a few controlled integration tests instead of dozens of sleep-based tests.

## 15. Contention across multiple instances and idempotency

An `@Scheduled` method runs in **every application instance** that enables the config. Suppose three pods all run the 10:00 UTC cron:

~~~text
pod A: SELECT accounts due -> account-7
pod B: SELECT accounts due -> account-7
pod C: SELECT accounts due -> account-7

pod A: UPDATE ... WHERE active=true AND expires_at<=now -> 1 row
pod B: UPDATE ... WHERE active=true AND expires_at<=now -> 0 rows
pod C: UPDATE ... WHERE active=true AND expires_at<=now -> 0 rows
~~~

**Conditional updates** ensure only one worker actually transitions `account-7`'s state. That is why the service counts **boolean update success** rather than counting candidates. In the demo, `ConcurrentHashMap`'s atomic `computeIfPresent` simulates atomic transitions **within a single JVM**, while a conditional `UPDATE` with a `WHERE` clause is the design for a shared DB.

**However, conditional updates are not enough for every side effect.** If deactivating also requires sending an email or payment event, send/commit ordering and retries can cause duplicates or loss. When reliable event publishing is required, use a **transactional outbox**, unique business event IDs, and idempotent consumers; test concurrency/failures against a real database + message broker.

### Distributed locks differ from idempotency

Distributed locks (ShedLock, Quartz clustered scheduler, DB leases, or leader election) reduce how many workers run the same job concurrently. Yet locks can expire, workers can crash, network partitions can occur, or retries can happen. **Do not treat a lock as sole proof that side effects happen exactly once.** Business data still needs unique constraints/conditional transitions and durable retry semantics.

### Batch processing and pagination

A large `batchSize` can hold a transaction open too long; a tiny batch can build up backlog. When querying candidate lists and updating in DB:
- filter directly on **`active=true AND expires_at<=now`**;
- use deterministic ordering and an appropriate limit;
- use conditional updates/optimistic locking;
- record metrics for candidates, changed, skipped, failed, and duration;
- consider locks/claims/`SKIP LOCKED` with multiple workers;
- avoid offset pagination on a continuously mutating dataset since rows may be skipped.

**The use case service owns the batching strategy**, not the `@Scheduled` method knowing SQL pagination details. The adapter only triggers the use case.

## 16. Transaction boundaries and retries

An `@Scheduled` method runs on a scheduler thread and does not inherit transactions from an HTTP request or JUnit test thread. If the business service or repository writes to a DB, it needs clear transaction semantics via Spring transaction management.

A production Spring Data adapter might use:

~~~java
@Transactional
public int processBatch() {
    // load due rows, apply updates, commit
}
~~~

This is a **snippet**, not part of the runnable project since the demo uses `ConcurrentHashMap`. `@Transactional` takes effect when the method is called through an appropriate Spring-managed proxy; **self-invocation** bypassing the proxy can prevent transactions from applying as expected.

### If a job fails, does the next schedule run?

In Spring `TaskScheduler`, periodic task errors may be logged and handled by the error handler, and scheduling continues depending on implementation/error handler. **Do not assume Spring will immediately retry the business operation** or that every exception stops the whole application. Production responsibilities:
- log structured `jobId`/`runId`, duration, and changed/failed counts;
- alert on consecutive failures;
- retry with backoff for controlled transient errors;
- ensure partial progress is safe to re-run;
- do not swallow errors and report a success metric;
- avoid infinite retries on poison records;
- provide a safe manual rerun playbook.

In the demo, the service and job let exceptions propagate; **unit tests check propagation**, while infrastructure handles/logs per config. This is far easier to diagnose than catching `Exception` and returning a fake `0` meaning "no overdue accounts".

### Testing partial failure

If in a batch of 100 records, 20 transition and the 21st throws an exception, changes are not guaranteed to roll back without a transaction. The in-memory demo has no atomic batch transaction; re-running the service remains safe for already inactive accounts. A production DB adapter must choose:
- one transaction for the entire batch (all-or-nothing);
- per-item transactions and retries;
- atomic claim + outbox;
- appropriate snapshots/pagination.

Unit tests of idempotent logic do not prove production transaction rollbacks; when requirements depend on a DB, add **`@DataJpaTest` or Testcontainers database integration** with the real repository adapter and transaction policy.

## 17. Business time, cron timezone, and DST

A proper clock test distinguishes:

**`Instant`:** absolute point in time; e.g., `expiresAt="2026-05-01T10:00:00Z"`. Comparing against `Instant.now(clock)` is right when policy is based on absolute expiry.

**`LocalDate`/`LocalDateTime`:** represents dates or times without an inherent timezone. If the rule is "expires at the end of the user's local day", you need `ZoneId` and DST rules to convert to `Instant`.

**Cron zone:** chooses when the scheduler triggers. Cron **`0 0 2 * * *`** in a DST zone may hit days missing 02:00 or repeating an hour; do not anchor business policy on "how many times cron ran" if the requirement is "process each expired account once".

**`Clock.systemUTC` vs `Clock.fixed`:** one is for runtime, one is for tests. Inject `Clock` at the boundary; do not alter CI's global system clock or timezone to create edge cases.

**Offset/time synchronization:** across multiple nodes, system clock skew can shift cutoffs by seconds. If critical, use an authoritative time source or DB current timestamp per contract and test accordingly. The demo injects `Clock` into the use case because it is easy to test and fits separating business logic from schedules.

## 18. Other options: disabled cron, profiles, scheduler beans

### Option A: `@ConditionalOnProperty` on the job bean

~~~java
@ConditionalOnProperty(
    prefix = "app.jobs.trial-expiration",
    name = "enabled",
    havingValue = "true")
~~~

When disabled, **the job bean does not exist**; this is the approach used by the demo project. It stops the scheduler from registering the job in normal unit/integration test contexts.

### Option B: cron expression `"-"` to disable the trigger

Spring Framework `@Scheduled` accepts the cron value **`"-"`** to represent a disabled trigger:

~~~java
@Scheduled(cron = "${jobs.some-cron:-}")
public void runScheduled() {
    service.expireDueTrials();
}
~~~

This is a **snippet**, not in the project. **The bean may still exist**, while annotation registration skips the disabled cron. Useful when keeping the bean for manual invocation without a trigger, though tests must distinguish **bean present** from **task registered**.

### Option C: Spring `@Profile`

A job exists only when a matching profile is active, e.g., `@Profile("production-jobs")`. Profiles are convenient yet can tie test behavior to a config matrix. **An explicit `enabled` property** is usually easier to observe; avoid tying jobs to every production profile if only certain nodes should run jobs.

### Option D: separate `@EnableScheduling` configuration

You can move `@EnableScheduling` into a `@Configuration` gated by property/profile so contexts not needing scheduling never build its infrastructure. This is helpful when disabling many jobs at once. The demo always enables `@EnableScheduling` while gating the job bean conditionally.

**Do not use `@DirtiesContext` to turn off schedules**: it only rebuilds the context, and the job in the new context will still run if `enabled=true`. Disable it in configuration before context creation.

## 19. When there are multiple scheduled methods

An application might have:
- trial expiry;
- invoice payment reminders;
- cache cleanup;
- email digests;
- inventory reconciliation;
- report generation.

Do not cram all logic into one class with many `@Scheduled` methods and test them all with one `SpringBootTest` waiting on thread timing. Have one use case per job or explicit domain orchestration:

~~~text
ExpiryScheduledAdapter -> ExpireTrialAccountsUseCase
ReminderScheduledAdapter -> PrepareInvoiceRemindersUseCase
CacheCleanupAdapter    -> EvictExpiredCacheEntriesUseCase
ReportScheduledAdapter -> GenerateReportUseCase
~~~

Adapters hold only scheduling metadata, logging, and delegation; each service has independent **`Clock`/ports/test fixtures**. If execution order between two jobs must be guaranteed, **that is a workflow dependency**, not something solved by hoping cron A finishes a few minutes before cron B. Use orchestration, queues/events, a workflow engine, or a state machine, and test the explicit ordering contract.

### Do not overuse `@Async` on `@Scheduled` methods

`@Async` can cause the scheduled trigger to return immediately while work continues on an executor, leading to overlapping invocations if the period is shorter than work duration. You need bounded queues, backpressure, idempotency, cancellation/shutdown policies, and metrics. A thin scheduled adapter calling a synchronous service is much simpler to reason about and test.

## 20. Observability distinguishes "did not run" from "nothing to do"

When a job simply logs `changed=0`, you must distinguish:
- scheduler trigger not registered (bean/property disabled);
- trigger registered but not yet due;
- trigger ran yet repository found 0 candidates;
- repository found candidates yet conditional update returned 0 because another worker handled them;
- execution failed mid-run and the error was swallowed;
- job stopped by shutdown;
- logs delayed/dropped in the pipeline.

Useful metadata to emit:
- **job name** and **run ID**;
- **trigger source**: scheduled/manual/retry;
- **`startedAt`**, **`duration`**;
- **`candidateCount`**, **`changedCount`**, **`skippedCount`**, **`errorCount`**;
- **success/failure status**;
- **instance ID** with multiple replicas;
- **backlog age** (age of oldest unprocessed overdue account).

The demo logs **`changed`** to keep the adapter thin. Production can use Micrometer Observation/metrics and tracing; place metrics in the adapter/orchestrator while the business service returns a structured result instead of letting the scheduler query internals.

**Do not test exact log timestamps or `Thread.sleep` to verify business success.** Unit tests already assert domain state and counts directly; observability integration tests are only needed when metric/log contracts carry product value.

## 21. Common mistakes table

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Test takes minutes waiting for cron | Business logic lives inside `@Scheduled` | Move to a service and call directly |
| Test fails occasionally near midnight | Hard-coded `Instant.now()`/`LocalDate.now()` | Inject `Clock.fixed` |
| Passes alone, fails in suite | Background `@Scheduled` running in `@SpringBootTest` | Disable job via property/conditional bean |
| `@Scheduled` does not run after app starts | Missing `@EnableScheduling`, bean not scanned, property disabled | Check config and scheduled bean registration |
| Unit test instantiates `new Job` and cron doesn't run | Object is not a Spring-managed bean | Expected; test delegation only, integration separately |
| Test only verifies service call while business is wrong | Mocked the subject itself | Unit-test the real service with a fake repository |
| `count=3` even though workers raced and only 1 updated | Counted candidates instead of affected rows | Count conditional update results |
| Two pods deactivate the same account twice | Each instance runs its own scheduler | DB atomic update/idempotency, locks if needed |
| Email sent twice on retry | Send and mark are not atomic | Outbox, unique event ID, idempotent consumer |
| Job errors yet logs success `changed=0` | Catch-all `Exception` swallowed it | Propagate/report failure, metrics |
| 0 candidates despite expired records in DB | Wrong timezone/`Instant` conversion or query filter | `Clock`/DB query integration tests |
| Test simulates time via `Thread.sleep` | Nondeterministic timing | `Clock.fixed`, manual invocation |
| `@DirtiesContext` yet job keeps running | New context still enables scheduling | Disable job via property before context creation |
| Cron fires at wrong hour | Unexpected default zone | `@Scheduled(zone=...)` and cron parse tests |
| Same task invoked repeatedly | Repeatable `@Scheduled` / multiple instances / multiple beans | Audit registrations/replicas |
| `@Async` causes overlapping jobs | Work exceeds period, unbounded executor | Control concurrency/backpressure |
| Batch of 1,000 rows holds resources too long | No limit or oversized transaction | Bounded batch / query order / claim strategy |
| Fake DB test passes, production JDBC fails | In-memory does not model locking/transactions | Testcontainers DB integration |
| Scheduled job test uses static `Clock` mock | State leaks across tests | Inject `Clock` per test |
| Test verifies cron by asserting annotation presence | Metadata does not prove registration/execution | Dedicated context/scheduler integration test |
| 1s `fixedRate` test fails on loaded CI | OS/scheduler is not real-time | Assert eventual trigger with timeout, not exact ms |
| Multiple CI jobs share one DB | Fixture data collisions | Isolated DB/schema/unique keys/cleanup |

## 22. Choosing the test method by layer

| What you want to protect | Recommended test | Not needed |
| --- | --- | --- |
| Expires at right time | Plain JUnit + `Clock.fixed` + fake repo | `@SpringBootTest`, cron |
| Exactly-at-now boundary | Fixed `Clock` and `Instant <=` comparison | Altering system clock |
| Batch size/retry idempotency | Plain JUnit + fixture data | Waiting for a second scheduler tick |
| Job delegation | Mockito mock service, call `job.run()` | Scheduler thread |
| Job `enabled=false` | `@SpringBootTest` + `getBeanNamesForType` | `Thread.sleep` |
| Cron expression/zone binding | Spring context/cron parser test | Large business dataset |
| Service SQL conditional update | `@DataJpaTest`/JDBC integration, H2 or production DB | Kafka/HTTP |
| Multi-pod concurrent processing | DB concurrency integration, unique/atomic conditions | Mockito call counts |
| Distributed lock/leader election | Multi-instance integration | Single business unit test |
| Email/outbox reliability | DB+broker/message integration test | Claiming from a mocked service |
| Scheduler invocation reliability | `TaskScheduler` integration with latch/Awaitility | Guessing `Thread.sleep` |

### Question before adding `@SpringBootTest`

**Does this test need a Spring container to prove something?** If the answer is "just calculating `expiredAt <= now`", no. If it needs to verify conditional bean properties, scheduler registrars, task executors, or transaction proxies, yes.

## 23. Self-check exercises

**1.** The goal is verifying an account expires right at `now`. Do you need to wait for cron? **No.** Inject `Clock.fixed` and call the service directly.

**2.** Should an `@Scheduled` method query the DB and send emails itself? **No**, when you can separate use cases and outbound adapters; the schedule is just a trigger.

**3.** Does `new TrialExpirationJob(serviceMock).run()` prove Spring registered the cron? **No**, it only tests Java method delegation.

**4.** When does Spring cron `"0 0 * * * *"` fire? **Top of every hour**, because the expression has six fields.

**5.** How do `fixedDelay` and `fixedRate` differ? **`fixedDelay` measures after the previous execution completes; `fixedRate` aims to keep cadence from start times**.

**6.** What is the effect of `enabled=false` in the demo? **The `TrialExpirationJob` bean is not created**, even though `@EnableScheduling` is still present.

**7.** Can cron `"-"` disable a trigger? **Yes**, though the bean can still exist; different from `@ConditionalOnProperty`.

**8.** Where is `Clock.systemUTC` used? **Production wiring**; `Clock.fixed` is used in tests to control business `now`.

**9.** Does an account with `expiresAt` equal to `now` expire under this lesson's rule? **Yes**, inclusive policy **`expiresAt <= now`**.

**10.** Why does the service call `Instant.now(clock)` once per run? To apply the **same cutoff** across the entire batch, avoiding micro-time drift between records.

**11.** Does running the service twice at the same `now` deactivate the same account twice? **No**, when the repository's conditional update is idempotent.

**12.** A query finds 2 candidates, yet another node processed one row before the update. Does `changed` count equal 2? **No**, it counts only successful updates.

**13.** Does `@Scheduled` across three pods automatically run once cluster-wide? **No**, each pod has its own scheduler.

**14.** Is a distributed lock sufficient to guarantee exactly-once emails? **No**, you still need idempotency/atomicity/outbox when external side effects exist.

**15.** Does `@Transactional` on a JUnit test roll back a job running on a scheduler thread? **Not automatically**; transactions on other threads are separate.

**16.** Is a test verifying cron timezone a business unit test? **No**, that is a scheduling/config integration test.

**17.** What is the risk of `@SpringBootTest` enabling a job unnecessarily? The background job mutates state, causing flakiness and order dependence.

**18.** Why is `Thread.sleep` usually unsuitable? Slow, flaky, and offers no precise control over schedulers/clocks.

**19.** When the DB is unavailable, should the service return 0 so the job stays green? **No**, propagate/report the error for observability and retry policies.

**20.** Does the demo's in-memory `ConcurrentHashMap` guarantee cluster idempotency? **No**, only within one JVM and one key; shared DB/atomic updates are needed.

**21.** Batch limit=2 and three due accounts. How many should `changed` be on the first run? **2**, then on the next run without races another **1**.

**22.** Does `@DirtiesContext` guarantee stopping all jobs forever? **No**, a new context with the same `enabled` property will re-register tasks.

**23.** Which namespace normally configures the scheduler pool in Spring Boot 3.4? **`spring.task.scheduling`**; distinct from `spring.task.execution` for async executors.

**24.** If a scheduled task must send a Kafka event after a DB update, what should you watch out for? **Atomicity and retries**, considering transactional outbox + idempotent consumers.

**25.** Should you test for an annotation's presence via reflection and conclude the schedule runs accurately? **No**, write an integration test for registration and execution when that is the contract.

### QA checklist before finalizing

- Does business logic live in **`TrialExpirationService`**, not in the `@Scheduled` method?
- Is there a repository port instead of SQL inside the scheduler?
- Does business logic read `now` from an injected **`Clock`**, not calling `Instant.now()` directly?
- Are **`expiresAt <= now`**, active flag, batch size, and idempotency clearly defined?
- Do service unit tests use `Clock.fixed` with no `Thread.sleep`?
- Are overdue, exact-due, not-yet-due, already-inactive, and rerun cases tested?
- Are batch boundaries, conditional update races, and dependency failures tested?
- Does the job adapter test only check delegation without pretending real cron ran?
- Are the app's `@EnableScheduling` and job's `@ConditionalOnProperty` properly understood?
- In test contexts, is the job **`enabled=false`** with no background side effects?
- Do you distinguish `cron`, `fixedDelay`, `fixedRate`, `initialDelay`, and `zone`?
- Do you understand cron timezone/DST differs from injected business time?
- Is there a plan for multiple replicas, DB atomic updates, and external side effects?
- Are in-memory fakes never treated as durable production DBs?
- When SQL/transaction correctness matters, are DB integration tests added?
- Are `@Async`/`@Transactional` not misused to "cure" races without understanding thread boundaries?
- Are job runs, changed counts, failures, and backlog measured instead of just one log line?
- Are `@DirtiesContext` or random cron disables not used to mask flaky tests?
- Is Gradle/cron execution never claimed without actual execution evidence?

**Conclusion:** **`@Scheduled` should decide when to run, not what business logic to execute.** Moving rules into an independent use case with **`Clock`**, a repository port, and conditional updates lets JUnit test every boundary precisely in milliseconds, independent of scheduler threads or CI clocks. The scheduled adapter merely delegates and is tested with Mockito; enablement and cron wiring are tested separately when genuinely needed. When deploying multiple instances, you still must ensure idempotency, transactions, retries/observability, and data isolation — problems `@Scheduled` does not solve on its own.

## Official documentation

- Spring Framework 6.2 — Annotation `@Scheduled` Javadoc (6-field cron, zone, fixedRate, fixedDelay, `CRON_DISABLED`): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
- Spring Framework 6.2 — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Boot 3.4 — Task Execution and Scheduling, `spring.task.scheduling.pool.size`: https://docs.spring.io/spring-boot/3.4/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.4 — `ConditionalOnProperty` Javadoc: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Framework 6.2 — Spring TestContext Framework: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework.html
- Spring Framework — Transaction Propagation and AOP proxies: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Java SE 17 — `Clock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html