# Distinguishing Intentional Fail-Fast from Infinite Retry During Startup

## Learning objectives

Starting a Spring Boot application is more than launching a JVM or binding a TCP port. The application may need to read configuration, build `ApplicationContext`, initialize singleton beans, open connections, validate dependencies, load baseline data, and run startup runners before becoming **ready to serve**. When a mandatory condition fails, the application needs a clear decision: **fail fast** intentionally, **bounded retry**, or run in **degraded mode** if the contract permits.

This lesson belongs to **Spring Boot Application Runtime -> Startup Failures**, focusing on the difference between **proper fail-fast** and **infinite retry during startup**. Technical context: Java 17+, Spring Boot 3.3.x, and Spring Framework 6.1.x.

After this lesson, you will be able to:

1. Explain why a startup failure with a **clear error signal** is usually better than a process that stays alive forever without ever becoming ready.
2. Classify **permanent** errors (bad configuration, invalid input, denied permissions) vs **transient** errors (connection refused, timeouts, 503, broker not ready yet).
3. Design retries with **max attempts, overall deadline, per-attempt timeout, backoff, jitter**, interrupt handling, and cleanup.
4. Understand `ApplicationStartedEvent`, `ApplicationRunner`, `ApplicationReadyEvent`, `ApplicationFailedEvent`, and availability states.
5. Know when to fail fast in `@Bean`/`@PostConstruct`, when to use runners, and when to delegate to runtime recovery.
6. Run a complete **Java 17+ / Spring Boot 3.3.13 / Gradle** project with three modes—`fatal`, `recover`, and `exhaust`—and exact output.
7. Distinguish infinite retries inside the JVM from **CrashLoopBackOff** caused by Kubernetes restarting exited JVMs.
8. Coordinate readiness/liveness/startup probes and shutdown budgets in deployment environments.
9. Test invocation counts, retry decisions, ready milestones, and process exit codes without using non-terminating loops.

**Rule:** Only retry when the error **can plausibly self-recover**; retries must have a **finite stopping condition**. A configuration mistake that cannot fix itself over time must be reported immediately instead of hidden behind endless reconnect attempts.

## 1. Four ways to respond to startup failures

| Approach | Mechanism | Observable outcome | When to use |
| --- | --- | --- | --- |
| **Fail fast** | Hit unrecoverable error, throw exception, stop startup | Failure/non-zero exit, never reaches ready | Bad configuration, incompatible schema, wrong credentials/permissions |
| **Bounded retry** | Retry within limits; continue on success; fail when budget runs out | Always reaches a finite success/failure conclusion if attempts have timeouts | Mandatory service starting slowly, brief network blip |
| **Infinite retry** | Keep retrying forever, usually lacking deadlines or error classification | JVM stays alive yet never ready and never reports a conclusion | Not recommended on startup paths |
| **Degraded startup** | Let system run when an auxiliary feature has a fallback | Core can become ready; auxiliary feature reports unavailable | Genuinely optional dependency whose fallback preserves business rules |

**Fail fast does not mean never retrying.** Policies can combine:

~~~text
Permanent error                → stop immediately
Transient error, within budget → retry with backoff
Transient error, budget spent  → report startup failure
Optional feature error         → degrade/reconnect, if permitted
~~~

Every choice must derive from the **business contract**. A payment service cannot mark itself "ready" without a required signing key just to log a clean startup. Conversely, a website can serve core content while a product recommendation engine is temporarily offline.

### Easy examples to classify

- `APP_SECRET` is a required property and missing: **fail fast**.
- Unparseable JDBC URL: **fail fast**.
- Database rejects a confirmed wrong password: usually **fail fast**; if the platform has an active secret-rotation step in progress, define a bounded wait policy.
- Database is booting and refuses connections for a few seconds: candidate for **bounded retry**.
- API returns temporary 429/503: can retry with `Retry-After`/backoff within budget.
- Optional analytics system unreachable: can degrade if core functions are unaffected.
- `NullPointerException` from a bug in setup logic: do **not** blindly retry 100 times.
- Old schema version incompatible with new binary: network retries will not fix it; fix migration/deployment.

## 2. Spring Boot startup lifecycle: started vs ready

Spring Boot 3.3 key milestones:

~~~text
main(String[] args)
   |
   +-- SpringApplication.run(args)
         |
         +-- Prepare Environment
         +-- Create ApplicationContext
         +-- refresh context
         |     +-- load bean definitions
         |     +-- instantiate non-lazy singletons
         |     +-- injection, @PostConstruct, init hooks
         |     +-- SmartLifecycle auto-start per contract
         |
         +-- ApplicationStartedEvent
         +-- LivenessState.CORRECT
         |
         +-- ApplicationRunner / CommandLineRunner
         |     +-- check conditions before ready
         |     +-- bounded retry when appropriate
         |     +-- throw exception if unable to proceed
         |
         +-- ApplicationReadyEvent
         +-- ReadinessState.ACCEPTING_TRAFFIC
         |
         +-- SpringApplication.run returns context
~~~

This diagram condenses key business milestones, not a full trace of every internal framework call.

**ApplicationStartedEvent** is published after refresh, **before** runners. **ApplicationReadyEvent** arrives after runners succeed. Thus, a "Started" log line or an `ApplicationStartedEvent` listener firing does not prove startup gates completed.

If a runner throws an unhandled exception, `SpringApplication.run(...)` enters the startup failure branch: Spring Boot reports the error, publishes `ApplicationFailedEvent` when applicable, and attempts to clean up the existing context. The success path **does not** reach `ApplicationReadyEvent`. If the failure occurs very early, a Spring-bean listener might not exist yet; never assume every listener receives every startup failure.

### Terms easily confused

- **JVM alive:** the process has not exited.
- **Context refreshed:** the bean factory/context passed the refresh phase.
- **Application started:** Spring Boot reached the Started milestone.
- **Application ready:** runners completed and Boot transitioned availability along the success path.
- **An endpoint works:** still depends on runtime dependencies, readiness policy, and feature health.

An infinite loop can trap the app between these milestones forever. Process survival is not a service-quality guarantee.

## 3. How is infinite retry during startup dangerous?

Example of a poorly written runner:

~~~java
@Override
public void run(ApplicationArguments args) {
    while (true) {
        try {
            checkMandatoryDatabase();
            return;
        }
        catch (Exception ignored) {
            // Retries immediately, with no logging and no deadline.
        }
    }
}
~~~

**This is an anti-pattern, not a runnable program**: `checkMandatoryDatabase()` is undefined. Never use this in production or run tests without timeouts.

Risks:

1. **Never-ready:** the runner never returns, so the app never reaches ready normally.
2. **Masks permanent errors:** wrong passwords or bad config loop identically to brief timeouts.
3. **CPU/network storms:** tight retries burn CPU and hammer databases/APIs.
4. **No conclusive status:** schedulers/CI never receive a process exit code signaling failure.
5. **Hard shutdowns:** an untimed blocking call or a loop ignoring interrupts pins threads when the process needs to exit.
6. **Silent hangs:** logs stall around "Starting ...", making hangs look like normal slow startup.
7. **More instances worsen the outage:** every replica retrying together prevents dependencies from recovering.
8. **Dragged-out rollouts:** deployment controllers wait until their pod deadline instead of failing fast to roll back.
9. **Breaks startup metrics:** startup duration has no clear upper bound.
10. **Leaks partial resources:** each attempt opening a new connection/thread without cleanup leaks proportionally to attempt count.

Adding `Thread.sleep(1000)` to the loop only slows it down; it does **not** turn infinite retry into a predictable startup policy.

## 4. First step: classifying permanent vs transient errors

### Permanent failure: errors unlikely to resolve by waiting alone

| Kind | Common signal | How to handle |
| --- | --- | --- |
| Missing required property | Binding/validation missing value | Name the key to fix and fail |
| Malformed config | Invalid port, URL, or duration | Fail before opening resources |
| Invalid credentials | Authentication explicitly rejected | Fail or trigger bounded secret-rotation check |
| Version mismatch | Unsupported schema or service API | Fail, block broken rollout |
| Missing artifact/class | Absent file, cert, or classpath entry | Fail, inspect packaging |
| Logic bug | `ClassCastException`, `NullPointerException` | Fail, fix code |
| Bad batch input | Unsupported input file format | Fail with non-retryable category |

### Transient failure: conditions that can change over a short window

| Kind | Scenario | Precondition to retry |
| --- | --- | --- |
| Connection refused | Dependency restarting | Right endpoint, connect timeout set |
| Network timeout | Network blip | Per-attempt timeout set |
| HTTP 503 | Service overloaded | Backoff+jitter, overall cap |
| HTTP 429 | Throttled | Honor `Retry-After` within budget |
| Broker rebalance | Consumer not yet assigned | Bounded wait and state check |
| Lock busy | Another instance setting up | Clear lock/lease contract |
| Transient DNS error | Resolver unresponsive | Capped retries, clear logging |

**No universal table fits every system.** HTTP 401 is usually permanent, yet in a system with a specific token-refresh contract there might be one valid refresh step before failing. Connection timeout may be transient, yet if the hostname has a typo, retrying for hours will never help.

### Exception taxonomy

Avoid:

~~~java
catch (Exception any) {
    retryAgain();
}
~~~

This is an anti-pattern snippet, not standalone. It retries validation errors and programming bugs alike.

Separate explicitly:

~~~java
try {
    client.verifyConnection();
}
catch (ConfigurationRejectedException permanent) {
    throw new StartupConfigurationException(permanent);
}
catch (TemporaryNetworkException temporary) {
    // Retry only if attempts and deadline remain.
}
~~~

This is an illustrative snippet requiring real classes/APIs. If an SDK throws only one broad exception, inspect status codes, error codes, or the cause chain to classify; avoid brittle parsing of `getMessage()` strings.

## 5. What boundaries does a bounded retry need?

### 5.1. Max attempts cap

Define `maxAttempts` as **total invocations**, including the initial try.

~~~text
maxAttempts = 3
Attempt 1 = initial try
Attempt 2 = first retry
Attempt 3 = second retry
After Attempt 3 fails → FAIL
~~~

Do not confuse "3 attempts" with "3 retries after the first try". In Spring Retry 2.0, `maxAttempts(3)` likewise means total attempts.

### 5.2. Overall deadline

If each attempt times out at 20 seconds, three attempts still take 60 seconds before even counting backoff. Pick a **max elapsed time** budget fitting the deployment.

~~~text
Startup budget: e.g., 20 seconds
Timeout per network attempt: e.g., max 3 seconds
Backoff: e.g., 200 ms → 400 ms → 800 ms, with jitter
Deadline exceeded before next attempt: FAIL
~~~

These numbers are **design examples**. Different services need different timeouts grounded in SLAs, cold-start times, OS limits, proxies, and orchestrators.

### 5.3. Per-attempt I/O timeout

`maxAttempts=3` **creates no time bound** if the first attempt can hang forever. HTTP connect timeouts, read timeouts, JDBC login timeouts, or broker client timeouts must be configured explicitly.

`Future.get(timeout)` bounds only how long **the calling thread waits**; it does not automatically stop underlying work or close sockets. Use proper API cancellation and cleanup.

### 5.4. Backoff and jitter

~~~text
Example escalating delay:
200ms → 400ms → 800ms → 1600ms, cap 2s
Jitter: spread delay across a bounded random window
Never sleep past the overall startup deadline
~~~

Backoff stops hundreds of replicas from hammering a database simultaneously right as it recovers. Setting a fixed 1 ms sleep across all replicas risks a **thundering herd**.

### 5.5. Handling interrupts

If shutdown sends an interrupt signal while sleeping between retries, never swallow it:

~~~java
try {
    Thread.sleep(delayMillis);
}
catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Startup retry interrupted", interrupted);
}
~~~

This is a method fragment needing `delayMillis`. Restore the interrupt flag and exit along the cancellation/failure path per contract rather than continuing `while(true)`.

## 6. Decision flow: fail fast vs retry

~~~text
Start startup validation
            |
            v
Mandatory to serve safely?
   |                       |
   NO                     YES
   |                       |
Fallback exists?      Classify error
  |     |             |            |
 YES    NO        Permanent    Transient
  |     |             |            |
  |  Revisit          v            v
  |  contract     FAIL FAST    Try connect
  |                                |
Degraded                       Succeeded?
+ metrics                       |      |
                               YES     NO
                                |       |
                              READY     v
                                    Attempts left?
                                    Deadline left?
                                    Error retryable?
                                      |        |
                                     YES       NO
                                      |        |
                                  backoff +   FAIL
                                  jitter,     WITH
                                  then retry  REASON
~~~

**Failing fast is a reasoned conditional choice**, not a knee-jerk reaction. It turns an unrecoverable error into a finite outcome so operators receive an alert and fix the cause.

For **optional** dependencies, startup may succeed in degraded mode only when the fallback is safe and accompanied by clear health/metrics. If falling back violates security, data integrity, or SLA guarantees, that dependency is no longer "optional".

## 7. Placing logic in the right Spring Boot phase

| Hook | Timing | Guidance |
| --- | --- | --- |
| Code in `main` before `run` | Before Spring context | Minimal argv/config checks, self-managed cleanup |
| `@Bean` factory method | Bean creation | Create resources; no infinite retries; roll back partial init |
| Constructor | Object instantiation | Avoid long I/O; never block indefinitely |
| `@PostConstruct` | Bean initialization | Local setup; do not turn into long startup retry loops |
| `SmartLifecycle.start()` | During context refresh | Start with bounded timeouts and clear rollback |
| `ApplicationRunner` | After refresh, before ready | Suitable for mandatory startup gates and bounded retries |
| `CommandLineRunner` | After refresh, before ready | Similar; receives raw `String...` |
| `ApplicationReadyEvent` listener | After runners | Observe ready; do not block indefinitely |
| HTTP/requests/consumers after ready | Runtime | Dedicated retries, circuit breakers, readiness |

Spring Boot 3.3 recommends placing startup tasks in `ApplicationRunner`/`CommandLineRunner` rather than overloading initialization callbacks like `@PostConstruct`. Conditions **needed for valid bean structure** (valid properties, constructor dependencies) should still validate early rather than deferring critical errors pointlessly.

### Loops inside runners affect ready

Runners execute after refresh and before `ApplicationReadyEvent`. If a runner loops forever, context refresh may have completed and `ApplicationStartedEvent` may have fired, yet ready never arrives. If the runner throws, Boot takes the startup failure path.

### Is retrying inside @PostConstruct different?

`@PostConstruct` runs while beans initialize, before context refresh finishes. Stalling here means **`ApplicationStartedEvent` has not even fired** and probes/observability may not be ready. Avoid heavy I/O or prolonged retries during bean creation.

### Lazy beans do not guarantee startup success

When `spring.main.lazy-initialization=true` is enabled, a misconfigured bean may not be instantiated until the first request. Thus reaching ready does not prove all lazy features are valid. For truly mandatory beans, enforce explicit startup validation or eager initialization per policy.

## 8. Runnable Java 17+ project: three startup handling paths

The project below uses **Spring Boot 3.3.13**, **Java 17+**, **Gradle**, with no network, database, or web starter. Its purpose is **illustrating policy**, not benchmarking real dependency latency.

Three modes:

- `fatal`: configuration error; zero retries.
- `recover`: simulated dependency fails on initial attempts then recovers; runner returns, Boot publishes ready.
- `exhaust`: simulated dependency fails all three attempts; runner throws, startup fails.

An extra variable `demo.succeed-at` controls which attempt succeeds in `recover` mode. The sample is strictly bounded, does no sleeping, and contains no infinite loops.

### 8.1. Project structure

~~~text
startup-policy-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/startup/
    └── StartupPolicyApplication.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'startup-policy-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.startup.StartupPolicyApplication'
}
~~~

Requires a Gradle version compatible with Spring Boot 3.3 and JDK 17+. If you have a Gradle Wrapper, you may use it; this sample does not pre-generate a wrapper.

### 8.2. Complete Java source

**`src/main/java/com/example/startup/StartupPolicyApplication.java`:**

~~~java
package com.example.startup;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class StartupPolicyApplication {

    private static final int MAX_ATTEMPTS = 3;

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StartupPolicyApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner startupGate(
            @Value("${demo.mode:recover}") String mode,
            @Value("${demo.succeed-at:3}") int succeedAt) {

        return args -> {
            System.out.println("GATE: mode=" + mode);

            if ("fatal".equals(mode)) {
                System.out.println("GATE: invalid configuration");
                throw new FatalStartupException(
                        "Required configuration is invalid");
            }

            if (!"recover".equals(mode) && !"exhaust".equals(mode)) {
                System.out.println("GATE: unknown mode");
                throw new FatalStartupException(
                        "Unknown demo.mode: " + mode);
            }

            if (succeedAt < 1 || succeedAt > MAX_ATTEMPTS) {
                System.out.println("GATE: invalid succeed-at");
                throw new FatalStartupException(
                        "demo.succeed-at must be between 1 and 3");
            }

            for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {

                boolean ready = "recover".equals(mode)
                        && attempt >= succeedAt;

                System.out.println(
                        "CHECK: attempt=" + attempt
                        + " result="
                        + (ready ? "SUCCESS" : "TRANSIENT_FAILURE"));

                if (ready) {
                    System.out.println("GATE: dependency ready");
                    return;
                }
            }

            System.out.println("GATE: retry budget exhausted");
            throw new DependencyUnavailableException(
                    "Required dependency unavailable after 3 attempts");
        };
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("EVENT: ApplicationReadyEvent");
    }

    public static final class FatalStartupException
            extends IllegalStateException implements ExitCodeGenerator {

        public FatalStartupException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 20;
        }
    }

    public static final class DependencyUnavailableException
            extends IllegalStateException implements ExitCodeGenerator {

        public DependencyUnavailableException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 30;
        }
    }
}
~~~

### 8.3. Code walkthrough

- `ApplicationRunner` is a bean invoked by Boot after context refresh and before ready.
- In `fatal`, the `for` loop does not run; invalid config is rejected immediately.
- In `recover`, attempt `succeedAt` and subsequent attempts simulate success. Once successful, the runner returns without spending the rest of the budget.
- In `exhaust`, all three attempts fail; after the final attempt, the program **throws an exception** rather than looping back to attempt 1.
- Unknown modes and `succeedAt` outside 1..3 are configuration errors, not worth retrying.
- Both exceptions implement `ExitCodeGenerator`, letting Spring Boot obtain exit code 20 (config error) or 30 (retry exhausted) on startup failure. This is a **demo-specific exit table**.
- `ApplicationReadyEvent` prints only when Boot successfully reaches ready.
- `try-with-resources` in `main` runs only when `SpringApplication.run` returns a context. On startup failure, Boot runs its own failure/cleanup path.
- Never call `System.exit(...)` inside the runner, avoiding cutting off cleanup and error reporting.

### 8.4. Build

Inside `startup-policy-demo`:

~~~bash
gradle bootJar
~~~

You can use `./gradlew bootJar` (Linux/macOS) or `.\gradlew.bat bootJar` (Windows) if the project has a wrapper.

Default executable JAR name:

~~~text
build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar
~~~

If you change `rootProject.name` or `version`, check `build/libs` for the actual filename rather than assuming the sample name.

### 8.5. Successful recovery on attempt 3

~~~bash
java -jar build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=recover --demo.succeed-at=3
echo $?
~~~

**Lines printed by the example's Java code** (excluding Spring Boot or Gradle logs):

~~~text
GATE: mode=recover
CHECK: attempt=1 result=TRANSIENT_FAILURE
CHECK: attempt=2 result=TRANSIENT_FAILURE
CHECK: attempt=3 result=SUCCESS
GATE: dependency ready
EVENT: ApplicationReadyEvent
MAIN: run returned
MAIN: context closed
~~~

Expected JVM exit code: **0**. Runner returns, Boot publishes ready, `run` returns the context, and `main` closes it cleanly.

### 8.6. Early recovery on attempt 2

~~~bash
java -jar build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=recover --demo.succeed-at=2
echo $?
~~~

Java output:

~~~text
GATE: mode=recover
CHECK: attempt=1 result=TRANSIENT_FAILURE
CHECK: attempt=2 result=SUCCESS
GATE: dependency ready
EVENT: ApplicationReadyEvent
MAIN: run returned
MAIN: context closed
~~~

There is no attempt 3 because the loop returns immediately on success.

### 8.7. Fail fast on invalid configuration

~~~bash
java -jar build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=fatal
echo $?
~~~

Java lines:

~~~text
GATE: mode=fatal
GATE: invalid configuration
~~~

**There is no** `EVENT: ApplicationReadyEvent` or `MAIN` lines after `run` returns, because the runner threw an exception. Besides these lines, Spring Boot may print an error report and stack trace.

When running the executable JAR via the standard Spring Boot launcher, expected JVM exit code is **20** from `FatalStartupException.getExitCode()`.

### 8.8. Retry budget exhausted

~~~bash
java -jar build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=exhaust
echo $?
~~~

Java output:

~~~text
GATE: mode=exhaust
CHECK: attempt=1 result=TRANSIENT_FAILURE
CHECK: attempt=2 result=TRANSIENT_FAILURE
CHECK: attempt=3 result=TRANSIENT_FAILURE
GATE: retry budget exhausted
~~~

This path has **no** ready event. `DependencyUnavailableException` supplies code **30** per the demo's policy. When run via the executable JAR/standard launcher, expected JVM exit code is 30.

### 8.9. Unsupported mode

~~~bash
java -jar build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=typo
echo $?
~~~

Java output:

~~~text
GATE: mode=typo
GATE: unknown mode
~~~

Zero attempts run. This is a fail-fast decision because **invalid input cannot fix itself after sleeping**.

### 8.10. Checking status on PowerShell

~~~powershell
java -jar .\build\libs\startup-policy-demo-0.0.1-SNAPSHOT.jar --demo.mode=exhaust
$LASTEXITCODE
~~~

In Bash/Zsh, `$?` is the status of the **most recent command**. Read it immediately after `java -jar` without inserting `echo hi` or another command in between.

**Why not test solely with `gradle bootRun`?** Gradle is a build tool/launcher. When the child JVM returns non-zero, Gradle may report a task failure code without necessarily preserving 20/30. When your contract covers Java process exit codes, run the JAR directly.

## 9. Real-world deadlines with I/O operations

The demo uses simulated flags to verify attempt counts. Production needs **max attempts**, an overall **deadline**, and per-attempt timeouts.

### Bounded logic pattern

~~~java
static void checkRequiredDependency(
        CheckedOperation operation,
        int maxAttempts,
        long budgetMillis) throws Exception {

    long start = System.nanoTime();
    long budgetNanos = TimeUnit.MILLISECONDS.toNanos(budgetMillis);

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {

        try {
            operation.run(); // Must enforce its own I/O timeout.
            return;
        }
        catch (TransientStartupException temporary) {

            long elapsed = System.nanoTime() - start;

            if (attempt == maxAttempts || elapsed >= budgetNanos) {
                throw temporary;
            }

            long remaining = budgetNanos - elapsed;
            long delayMillis = Math.min(
                    200L * attempt,
                    TimeUnit.NANOSECONDS.toMillis(remaining));

            try {
                Thread.sleep(delayMillis);
            }
            catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Startup interrupted", interrupted);
            }
        }
    }
}
~~~

**This is an illustrative method**, not a standalone runnable file: it requires `java.util.concurrent.TimeUnit`, a functional interface `CheckedOperation` with `void run() throws Exception`, and `TransientStartupException`.

It demonstrates:

1. Attempt count is capped.
2. After transient failures, exceeding attempts or deadline throws.
3. Sleep never exceeds the remaining budget calculated **when sleep begins**.
4. Interrupts end waiting rather than being ignored.
5. `System.nanoTime()` measures monotonic elapsed time, independent of wall-clock jumps.

**Not a hard preemption deadline:** if `operation.run()` can hang forever, `budgetMillis` will not interrupt it by itself. Configure timeouts on HTTP/JDBC/broker clients and close/cancel via their APIs.

### Backoff with jitter

An illustrative formula:

~~~java
long base = 200L;
long cap = 2_000L;
int shift = Math.min(attempt - 1, 4);

long backoff = Math.min(cap, base * (1L << shift));
long half = Math.max(1L, backoff / 2L);
long jittered = ThreadLocalRandom.current()
        .nextLong(half, backoff + half + 1L);
~~~

Requires `attempt >= 1` and importing `java.util.concurrent.ThreadLocalRandom`; still cap `jittered` against the remaining deadline before sleeping. Capping the shift avoids overflow in small examples. When an API returns `Retry-After`, factor in provider policy and remaining budget.

### Retries do not create idempotency

If a call merely **reads state**, retrying is usually lower risk. If a call **creates records, places orders, or sends emails**, a timeout can arrive **after the remote side effect already committed**. To retry safely, use idempotency keys, operation IDs, status queries, or transaction/outbox patterns as appropriate.

## 10. Spring Retry: helpful, yet not a replacement for startup policy

Spring Retry is a separate library, not included in full just by adding `spring-boot-starter`. It provides `RetryTemplate` and `@Retryable` when configured with the right version and dependencies.

**Spring Retry 2.0.x** example (illustrative, not in Section 8's project):

~~~java
RetryTemplate retry = RetryTemplate.builder()
        .maxAttempts(3)
        .exponentialBackoff(200, 2.0, 2_000)
        .retryOn(TransientStartupException.class)
        .build();

retry.execute(context -> {
    client.ping();
    return null;
});
~~~

This snippet needs compatible Spring Retry dependencies, imports, `TransientStartupException`, and a defined `client`. `maxAttempts(3)` includes the initial call plus up to two retries.

### Limitations of the @Retryable annotation

When using AOP proxies:

- Self-invocation usually **bypasses** the proxy and may not apply retries.
- `@PostConstruct` may execute before the target is proxied as expected; do not rely on annotations on init methods for guaranteed retries.
- Exceptions thrown on a background thread after the method returned do not propagate back to the caller.
- Configuring retry on every exception risks retrying programming bugs and permanent config mistakes.
- A startup gate needing a final outcome should invoke `RetryTemplate` or an explicit retry helper from the runner and throw once policy is exhausted.

**Version note:** Spring Framework 7 introduces different resilience APIs. Do not copy Framework 7 annotations/APIs into Boot 3.3 / Framework 6.1 without compatible dependencies.

## 11. Readiness, liveness, and startup probes

In web apps with Spring Boot Actuator, availability states relate to probes yet are not synonymous.

| Signal | Question answered | Typical Kubernetes reaction |
| --- | --- | --- |
| **Liveness** | Is the app still functioning internally and able to recover? | Consecutive failures past threshold -> restart container |
| **Readiness** | Can the instance accept traffic right now? | NotReady -> stop routing new requests to this instance |
| **Startup probe** | Did startup complete within budget? | Until passing, hold off liveness/readiness checks; past threshold -> kill/restart |

### Why shouldn't DB health decide liveness for every replica?

If the DB goes down briefly and every pod treats that as a liveness failure, Kubernetes can restart **all** pods simultaneously, slamming the DB right as it recovers. Per Spring Boot/Kubernetes guidance, liveness should normally reflect **internal application health**, not direct coupling to every external system.

Readiness can check conditions vital for serving requests; still, **do not blindly** wire every external health indicator into readiness without assessing blast radius when an auxiliary system fails.

### Actuator probe paths

In apps with a web starter and `spring-boot-starter-actuator`:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Typical URLs when configured properly:

~~~text
/actuator/health/liveness
/actuator/health/readiness
/livez
/readyz
~~~

These are **not endpoints of Section 8's CLI project**, which has no web server or Actuator. Spring Boot 3.3 automatically enables liveness/readiness health groups in Kubernetes environments; the properties above help enable them explicitly in other environments.

### Illustrative Kubernetes fragment

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 24

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
~~~

This is a **container spec fragment**, not a complete Kubernetes Deployment. Match endpoints and ports to reality. A startup probe helps avoid killing valid slow-starting apps; it **does not fix** wrong config or down dependencies.

### Readiness must not hide permanent failures silently

For a mandatory dependency that is temporarily starting up, an instance may stay unready during bounded retries. For a permanently wrong URL, keeping a pod NotReady forever prevents rollbacks. Failing fast with a clear error/exit signal is usually better.

## 12. Infinite retry in the JVM vs CrashLoopBackOff

Distinguish two distinct loops:

### A. JVM stays running and retries infinitely

~~~text
JVM #1
  |
  +-- SpringApplication.run
        |
        +-- runner while(true)
              |
              +-- retry retry retry...
              |
              +-- Never returns, never throws
~~~

Here the process never terminates, may stay unready, and the platform can intervene only via timeouts, probes, or monitoring.

### B. JVM fails, platform restarts repeatedly

~~~text
JVM #1 → startup fail, exit non-zero
restartPolicy → JVM #2 → startup fail, exit non-zero
backoff → JVM #3 → startup fail, exit non-zero
...
CrashLoopBackOff
~~~

This is container restart/backoff behavior, **not** proof of a `while(true)` loop in code. `CrashLoopBackOff` indicates an instance repeatedly failing and being restarted by policy.

**Operational consequence:** if one startup retries 50 times internally and the orchestrator restarts the process multiple times, total calls to the dependency multiply dramatically. Account for retry budgets at **both layers**.

When you see `CrashLoopBackOff`, inspect previous-container logs, pod events, exit codes, probes, resource limits, and configuration rather than simply raising retry counts to mask the error.

## 13. Fail fast and degraded mode can coexist

### Mandatory conditions: do not degrade arbitrarily

If a service cannot verify JWTs without a signing key, or cannot persist orders when a required database is down, do **not** mark ready just because controllers initialized. Options:

- Fail fast on invalid configuration.
- Bounded retry for booting dependencies.
- Fail explicitly once budget is exhausted.
- Or remain not-ready under a dedicated recovery architecture, still with a proper deadline and conclusive state.

### Optional features: intentional degraded startup

Example recommendation service:

~~~text
Core checkout: READY
Recommendation: UNAVAILABLE
Fallback: hide recommendations / show default list
Background reconnect: timeout, backoff, circuit breaker
Monitoring: degraded count, reconnect failures
~~~

If core checkout works safely, there is no need to block startup because recommendations are down. If your SLA mandates recommendations on every request, the contract changes.

### Difference between startup gates and runtime recovery

- **Startup gate:** verifies essential preconditions before ready.
- **Runtime recovery:** handles post-ready errors via timeouts, per-operation retries, circuit breakers, and feature/readiness updates.
- **Reconciliation:** once a dependency recovers, restores connections, caches, or checkpoints per contract.

One passing startup check does not guarantee dependencies stay healthy forever. Do not cram all retry logic into a single runner.

## 14. Fail fast still requires cleanup

Failing fast **does not** mean calling `Runtime.halt(...)` or `System.exit(...)` inside constructors or `@PostConstruct`.

When a resource-allocation step fails:

1. Preserve the original exception and cause chain.
2. Clean up resources acquired in that step in proper order.
3. Let Boot handle startup failure to destroy managed context/beans when possible.
4. Report a clear exit category; never swallow failures as ready.
5. Keep passwords, tokens, and PII out of logs.

Illustrative example:

~~~java
Connection connection = openConnection();

try {
    Subscription subscription = openSubscription(connection);
    return new ManagedClient(connection, subscription);
}
catch (RuntimeException original) {
    try {
        connection.close();
    }
    catch (RuntimeException cleanupFailure) {
        original.addSuppressed(cleanupFailure);
    }
    throw original;
}
~~~

This is a **non-standalone snippet** requiring matching classes/helpers. If an error can occur **after `subscription` is already opened**, cleanup must close `subscription` before `connection` too. Do not expect `@PreDestroy` on an uninitialized bean to clean up local factory variables.

### Exit codes do not replace resource cleanup

The demo uses exceptions implementing `ExitCodeGenerator`. Spring Boot extracts exit codes from exceptions on startup failures. Even so, an exit code is only an **outcome signal** to the OS, not a cleanup strategy.

`SpringApplication.exit(context)` computes codes and closes an existing context, distinct from when `SpringApplication.run` fails before returning a context. Never call `SpringApplication.exit(null)` in a `catch` block trying to "save" a nonexistent context.

## 15. Startup budgets and the deployment pipeline

If a pod has a ~60-second startup probe budget while the app retries for 5 minutes, kubelet may kill the pod **before** the app finishes its retries. If the app fails fast in 2 seconds yet the orchestrator restarts repeatedly, you get a loop **at the platform layer**.

Account for:

~~~text
Deployment-level startup budget
    = JVM/class loading + Spring context refresh
    + sum of required startup checks
    + bounded retry/backoff
    + buffer for scheduling, probes, shutdown
~~~

Milestones do not always add linearly, yet this formula helps avoid conflicting timeouts.

### Rolling deployments

- **Bad config/schema:** failing fast helps deployments catch errors early and roll back per policy.
- **DB slow to boot by a few seconds:** bounded retries avoid unnecessary restarts.
- **Many pods retrying together:** jitter/backoff prevents overwhelming the recovering DB.
- **Never-ready apps:** rollouts stall until timeout and emit vague failure errors.
- **Graceful stop:** if the process receives `SIGTERM` mid-retry, handle interruption/cancellation and release resources.

Startup probes are **monitoring/timing guards**, not auto-fixers for broken URLs or missing migrations.

## 16. Logs and metrics to distinguish decisions

Success after retry log pattern:

~~~text
startup_gate_started
dependency_check attempt=1 outcome=transient_failure
dependency_check attempt=2 outcome=transient_failure
dependency_check attempt=3 outcome=success
startup_gate_passed
application_ready
~~~

Fail-fast pattern:

~~~text
startup_gate_started
startup_validation_failed category=permanent key=DB_URL
startup_aborted exit_category=configuration
~~~

Budget-exhausted pattern:

~~~text
startup_gate_started
dependency_check attempt=3 outcome=transient_failure
startup_retry_exhausted max_attempts=3 elapsed_ms=8200
startup_aborted category=dependency_unavailable
~~~

These are **business log patterns**, not real output from the network-free demo. Never log raw credentials, password-bearing connection URIs, or sensitive payloads.

### Useful metrics

- `startup.validation.failure.total` by category.
- `startup.dependency.attempts` and retry counts.
- `startup.retry.exhausted.total`.
- `startup.retry.duration`, `startup.total.duration`.
- Elapsed time from process start to `ApplicationReadyEvent`.
- Pod restart count, startup probe failures, readiness status.
- Runtime reconnect attempts when degraded mode applies.

**Never place raw exception messages or request IDs into metric labels**, as that causes high cardinality. Use bounded categories and record details in structured logs under data-protection policies.

## 17. Testing startup policies

### Matrix

| Case | Dependency attempts | Ready event? | Outcome |
| --- | ---: | --- | --- |
| `fatal` | 0 | No | Fail fast |
| `recover, succeed-at=1` | 1 | Yes | Success |
| `recover, succeed-at=2` | 2 | Yes | Success |
| `recover, succeed-at=3` | 3 | Yes | Success |
| `exhaust` | 3 | No | Retry exhausted |
| Unknown mode | 0 | No | Invalid configuration |
| `succeed-at=0` | 0 | No | Invalid configuration |
| Permanent error on attempt 2 | 2 | No | Stop immediately |
| Interrupted during backoff | Stop immediately | No | Cancel/failure |
| Hung network call | Must have per-attempt timeout | No once budget spent | Bounded failure |

### Testing with a fake dependency

A fake operation:

~~~java
AtomicInteger attempts = new AtomicInteger();

Runnable probe = () -> {
    if (attempts.incrementAndGet() < 3) {
        throw new TemporaryNetworkException("Not ready");
    }
};
~~~

This is an **illustrative snippet** requiring `AtomicInteger`, a definition of `TemporaryNetworkException`, and a retry executor invoking `probe`. After bounded retries, assert `attempts.get() == 3`. For permanent exceptions, assert no second attempt occurs.

### Process-level integration tests

To verify **actual exit codes**, launch the Spring Boot JAR in a child JVM via `ProcessBuilder` or a shell:

1. Build the JAR.
2. Run `recover`, `fatal`, `exhaust` in turn.
3. Capture stdout/stderr and exit codes.
4. Set a child-JVM timeout to catch regressions into infinite loops.
5. Verify `ApplicationReadyEvent` appears only in success modes.
6. If the test process exceeds its deadline, kill the child process and fail the test rather than hanging CI forever.

Never call `System.exit` inside the JUnit runner JVM. Never use repeated real `Thread.sleep(1000)` calls to test retry timing; inject a clock/sleeper or fake operation.

### ApplicationFailedEvent

Spring Boot can publish `ApplicationFailedEvent` when startup fails. To observe **very early errors** before context refresh, register an `ApplicationListener` on `SpringApplication` at bootstrap start. An uncreated `@EventListener` bean will not reliably receive pre-BeanFactory events.

## 18. Common mistakes

**1. "Keep retrying forever until ready."** Wrong; if a URL or password is wrong, time will not fix it.

**2. "Fail fast means ignoring all transient errors."** Wrong; you can run short bounded retries and then fail when budget runs out.

**3. "`catch(Exception)` is a fine retry policy."** Wrong; classify permanent vs transient errors.

**4. "`maxAttempts=3` means three retries plus the first attempt."** Wrong when the contract is total calls; Spring Retry 2.0 also counts the first try in `maxAttempts`.

**5. "`maxAttempts` alone is enough."** Wrong if a single attempt can block forever; enforce I/O timeouts and an overall deadline.

**6. "Backoff doesn't matter if timeouts are short."** Many pods retrying together create request storms; use jitter.

**7. "Swallow `InterruptedException` and keep retrying."** Can prevent startup from responding to shutdown signals.

**8. "`@PostConstruct` is great for multi-minute network retries."** Usually wrong; it stalls bean initialization and context refresh.

**9. "`@Retryable` always runs on self-invocation."** Not with standard proxy-based retries.

**10. "`spring-boot-starter` alone includes Spring Retry."** Wrong; add the right dependencies and configuration.

**11. "`ApplicationStartedEvent` is `ApplicationReadyEvent`."** Wrong; runners execute in between.

**12. "An open listening port means ready."** Wrong; startup gates may still be running.

**13. "`ApplicationReadyEvent` always fires even if a runner throws."** Wrong on normal startup paths.

**14. "Liveness should check every dependency."** Can restart every pod simultaneously when an external DB goes down.

**15. "Failing readiness forever fixes bad config."** Wrong; for permanent errors, fail fast is much clearer.

**16. "Startup probes solve every start failure."** Wrong; they only govern how the platform waits/restarts.

**17. "`CrashLoopBackOff` proves there is a `while(true)` in code."** Wrong; it is the platform restarting a repeatedly failing process.

**18. "Internal retries and Kubernetes restarts are independent so no coordination is needed."** Wrong; total request load multiplies across both layers.

**19. "`System.exit()` inside `@Bean` is proper fail-fast."** Discouraged; it can truncate error reporting and cleanup.

**20. "`gradle bootRun` always returns the Java app's exact exit code."** Not guaranteed; test with the direct JAR.

**21. "Enabling lazy init always surfaces errors early."** Wrong; lazy bean failures may surface only on the first request.

**22. "Having a fallback makes any dependency optional."** Wrong when the fallback breaks correctness or security.

**23. "Retrying writes is just as safe as retrying reads."** Wrong; side effects may have committed before the client timed out.

**24. "A Future timeout means the underlying task died."** Wrong; explicitly cancel and clean up cooperative workers.

**25. "Startup succeeding means dependencies stay healthy forever."** Wrong; runtime recovery is a separate concern.

**26. "Infinite retries don't need metrics since the process is still alive."** Wrong; that can become a silent never-ready outage.

## 19. Practice exercises

1. Contrast fail fast, bounded retry, infinite retry, and degraded startup using four scenarios.
2. Why should a missing required signing key fail fast rather than retry connections?
3. Propose `maxAttempts`/deadline/backoff values for a DB taking 5 seconds to boot.
4. If one attempt can block for 60 seconds, do three attempts keep you within a 10-second deadline?
5. Run `recover / succeed-at=3`. Why are there three attempts yet only one ready event?
6. Run `recover / succeed-at=1`. Why is there no second attempt?
7. Run `fatal`. Why is `MAIN: run returned` not printed?
8. Run `exhaust`. Why must it throw instead of restarting from attempt 1?
9. Run mode `typo`. Why is this not a transient error?
10. Add a `fatal` mode for denied permissions; define an appropriate exit code and log.
11. Why can `ApplicationStartedEvent` have already fired even when a runner later fails?
12. Compare placing retries in a constructor vs inside a runner.
13. Why might `@Retryable` fail to trigger on self-invocation?
14. Use a fake operation that fails twice then succeeds; assert call count is three.
15. Give a fake operation that always fails; assert it stops after `maxAttempts` without swallowing the original exception.
16. Use a fake clock/sleeper to test the overall deadline without real sleeping.
17. When a thread is interrupted during backoff, what must the code do?
18. For HTTP 429/503, design retries honoring `Retry-After`, jitter, and max elapsed time.
19. A resource-creating POST succeeded yet the client timed out. How do you retry without creating duplicates?
20. If all pods restart when the DB goes down, what might be wrong with your liveness probe?
21. When the startup probe budget is 60 seconds yet retry budget is 5 minutes, what happens?
22. Why doesn't `CrashLoopBackOff` mean there is an infinite loop inside the JVM?
23. An optional recommendation feature fails; how do you design degraded mode and readiness?
24. Write an integration test running the JAR and reading exit codes for `fatal`/`exhaust`/`recover`.
25. When `SIGTERM` arrives mid-retry, how must timeouts and cleanup coordinate?
26. In rolling deployments, why can failing fast on schema mismatches speed up rollbacks?
27. List three signals to monitor to distinguish "valid slow startup" from "startup incapable of finishing".
28. If a misconfigured lazy bean is instantiated only on the first request, is that still a `SpringApplication.run` startup failure?
29. Use `ExitCodeGenerator` for three error types and describe a scheduler's retry policy based on those codes.
30. Build a code-review checklist for a startup gate connecting to a DB, verifying migrations, and starting a broker consumer.

## Key takeaways

- **Fail fast** is intentional termination when an essential precondition cannot self-recover; it gives a clear failure signal, not a design flaw.
- **Bounded retry** suits transient errors only, paired with **max attempts, overall deadline, per-attempt timeouts, backoff+jitter, interrupt handling, and cleanup**.
- **Infinite retry during startup** can prevent `ApplicationReadyEvent` from ever arriving while hiding the root cause.
- In Spring Boot 3.3, `ApplicationStartedEvent` comes **before** runners; `ApplicationReadyEvent` comes **after** runners succeed.
- `ApplicationRunner` is usually the right place for startup tasks needed before ready; constructors/`@PostConstruct` must never block indefinitely.
- **Liveness** reflects internal health; **readiness** controls traffic routing; **startup probes** allow valid startup time.
- **CrashLoopBackOff** is the platform's restart/backoff mechanism for repeatedly failing processes, distinct from infinite retries inside one JVM.
- Retries do not replace validation, idempotency, health checks, circuit breakers, or runtime recovery.
- A good startup policy aims for **a finite end, a clear reason, logs/metrics, and a recovery path**.

### References

- Spring Boot 3.3 — SpringApplication, Startup Failure, Application Events and Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Actuator, Health Groups and Probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — ApplicationRunner Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3 — ApplicationReadyEvent Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3 — ExitCodeGenerator Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Retry 2.0.x — RetryTemplateBuilder: https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html
- Kubernetes — Liveness, Readiness and Startup Probes: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#container-probes
- Kubernetes — Pod Lifecycle and CrashLoopBackOff: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Java SE 17 — System.nanoTime and System.exit: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
