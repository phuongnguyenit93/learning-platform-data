# Cleaning Up Messages and Resources Between Tests

In **Spring Framework Mail integration tests**, the application typically sends emails through a test SMTP server such as GreenMail, Mailpit, or MailHog. Unlike unit tests that only use Mockito, integration tests can open sockets, send real SMTP commands, write emails into a fake server's mailbox, create attachment files, insert jobs into a database, and run asynchronous workers.

These resources have **lifecycles extending beyond a single assertion**. If the first test leaves behind an email or job, the second test may read stale results. If the SMTP server or network connections are not closed, the next test suite may fail to bind its port. If temporary files or executors are left running, CI can leak resources, slow down, or fail intermittently.

Therefore, beyond verifying that emails are sent properly, every integration test needs a **state isolation and cleanup strategy**: received messages, mailboxes, databases/outboxes, queues, async tasks, sockets/transports, files/streams, and components started for the test.

Example problem:

~~~text
Test A: send order confirmation
  -> SMTP inbox has 1 email
  -> Test A finishes yet inbox was not cleared

Test B: send password reset
  -> SMTP inbox has 2 emails
  -> assertEquals(1, receivedMessages.length) fails

Test B has no bug in its sending logic, yet fails due to leftover state from Test A.
~~~

The goal of this guide is making tests **independent, repeatable, and cleanly torn down even when assertions fail**, without accidentally deleting resources still in use by other tests.

## 1. Types of State Requiring Cleanup

An email integration test can touch multiple layers:

| Layer | Examples of Leftover State | Consequence If Not Cleaned Up |
| --- | --- | --- |
| Test SMTP server | Emails in the receiving mailbox | Later tests miscount messages |
| SMTP protocol/session | Unclosed connections or unstopped server | Port occupied, socket/resource leaks |
| Application mail job | Outbox rows in `PENDING`, `RETRY_WAIT` | Workers send again in a later test |
| Business database | Order/customer/notification state | Order-dependent tests |
| Queue/broker | Unconsumed messages, delayed/retry messages | Old events trigger new emails |
| Scheduler/async executor | Unfinished send tasks | Emails arrive after inbox was cleared |
| Filesystem | PDFs, inline images, upload folders, temp files | Disk leaks, wrong attachments |
| Streams | `InputStream`, `OutputStream` | File locks and descriptor leaks |
| Spring context | Singleton beans, caches, schedulers, connection pools | Unintended shared state |
| Test doubles | Mock invocation/state, stub HTTP server requests | Assertions skewed by previous runs |
| Provider sandbox | Remaining mailboxes/events/API requests | Cross-job result contamination |

Not every test involves all of these components. Identify **the resources actually created** and who owns their lifecycle.

### 1.1. Clean the Right Thing at the Right Scope

A helpful rule:

> Whichever component creates or owns a resource should provide the corresponding close/cleanup mechanism; tests must specify clearly which slice of resources belongs to their scope.

Examples:

- Test starts GreenMail itself -> test is responsible for stopping GreenMail.
- Tests share GreenMail per class -> each method clears the mailbox; the class stops the server.
- Test creates outbox rows keyed by `testRunId` -> delete/restore only that test's rows, never `TRUNCATE` a shared database.
- Test uses a Testcontainers container managed by a JUnit extension -> do not stop it between methods if the container is scoped to the class/suite.
- Test creates files via `@TempDir` -> let JUnit clean up after all file reads have finished.

**Never run bulk delete commands on an SMTP server or DB shared with real environments.** Purge/delete operations in this guide apply strictly to verified isolated test infrastructure.

## 2. Test Isolation: Fresh per Test or Shared and Cleaned?

Three common approaches:

| Strategy | SMTP Server | Mailbox Between Tests | Pros | Cons |
| --- | --- | --- | --- | --- |
| **Per-test instance** | Start/stop for each method | Completely fresh | High isolation, minimal order coupling | Startup overhead |
| **Per-class instance** | One server for the whole test class | Purge between methods | Balances speed and isolation | Requires handling parallelism/async |
| **Shared suite/container** | One server across multiple classes | Dedicated IDs/namespaces or locked purges | Fast for large suites | Race-prone if purged globally |

Choose based on startup cost and parallel execution needs:

- For a few small SMTP tests, **per-test** is usually simplest and most reliable.
- For many methods sharing one server inside one class, **per-class + purge** saves time.
- For a shared Mailpit/Testcontainers across classes, **test-specific correlation IDs and filters** are generally safer than wiping all messages while tests run concurrently.

### 2.1. "After-Test Cleanup" Differs from "Before-Test Cleanup"

- **Before-test cleanup** ensures a test starts from a known state, even if a previous run aborted abnormally.
- **After-test cleanup** frees resources right after the test, even if assertions throw, limiting spillover to later tests.

When using a shared sequential fixture, you can use both:

~~~text
@BeforeEach -> ensure mailbox is clean
run test    -> send and assert
@AfterEach  -> delete messages created by test
~~~

However, if **multiple tests run in parallel against the same server**, a global purge in Test A's `@BeforeEach` or `@AfterEach` can wipe Test B's messages. Cleanup must match **scope and concurrency**.

## 3. Resource Lifecycles with JUnit 5

JUnit Jupiter provides common lifecycle callbacks:

| Hook | Timing | Typical Use |
| --- | --- | --- |
| `@BeforeEach` | Before each test method | Create mailbox/session, reset state |
| `@AfterEach` | After each test method | Clean messages, files, reset fake state |
| `@BeforeAll` | Before methods in the class | Start shared SMTP server |
| `@AfterAll` | After methods in the class | Stop SMTP server, release pools |
| `@TempDir` | JUnit-provisioned temp directory | Hold test-owned attachments/files |
| `@TestInstance(PER_CLASS)` | Enables per-class instance lifecycle | Instance `@BeforeAll` and `@AfterAll` |
| `@ResourceLock` | Synchronizes tests sharing a named resource | Prevent concurrent purge/send on shared server |

A sequence diagram:

~~~mermaid
sequenceDiagram
    participant J as JUnit
    participant T as Test
    participant S as SMTP Test Server
    J->>T: BeforeEach
    T->>S: Start/prepare isolated mailbox
    J->>T: Execute test
    T->>S: Send + inspect messages
    J->>T: AfterEach
    T->>S: Purge/stop/close
    Note over J,S: Cleanup must also run when assertions fail
~~~

Teardown hooks prevent failed assertions from skipping cleanup code after the assertion. However, if the JVM is killed or the runner terminates forcibly, callbacks are not guaranteed to run; that is why environment isolation, container lifetimes, and fallback cleanup matter.

## 4. Complete Example: Dedicated GreenMail per Test

A clear pattern is using GreenMail as an in-memory test SMTP server. In this example:

- JUnit starts GreenMail before each test;
- the server binds to `127.0.0.1` on a dynamic port, avoiding fixed-port collisions;
- `JavaMailSenderImpl` sends real SMTP to GreenMail;
- the test inspects `getReceivedMessages()`;
- `@AfterEach` stops the server, even when the test fails.

### 4.1. Illustrative Dependencies

With Spring Boot 3 / Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // Choose a GreenMail version compatible with your project's Jakarta Mail/JDK.
    testImplementation 'com.icegreen:greenmail:<compatible-version>'
}
~~~

`<compatible-version>` is a placeholder to replace with a build-managed version. Never mix a `javax.mail`-based GreenMail release with `jakarta.mail` code if incompatible.

### 4.2. Test Class

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.*;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class SimpleMailIntegrationTest {
    private GreenMail greenMail;
    private JavaMailSenderImpl sender;

    @BeforeEach
    void setUp() {
        ServerSetup setup = new ServerSetup(
                0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP);

        greenMail = new GreenMail(setup);
        greenMail.start();

        sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(greenMail.getSmtp().getPort());
        sender.setProtocol("smtp");
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "false");
        props.put("mail.smtp.connectiontimeout", "3000");
        props.put("mail.smtp.timeout", "3000");
        props.put("mail.smtp.writetimeout", "3000");
    }

    @AfterEach
    void tearDown() {
        if (greenMail != null) {
            greenMail.stop();
        }
    }

    @Test
    void sendsOneMessageToIsolatedMailbox() throws Exception {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("notifications@example.test");
        mail.setTo("alice@example.test");
        mail.setSubject("Order A123");
        mail.setText("Order A123 confirmed");

        sender.send(mail);

        assertTrue(
                greenMail.waitForIncomingEmail(5_000L, 1),
                "Expected one SMTP message in test server");

        MimeMessage[] messages = greenMail.getReceivedMessages();
        assertEquals(1, messages.length);
        assertEquals("Order A123", messages[0].getSubject());
    }
}
~~~

**Key point of the example:** `JavaMailSenderImpl` is the real implementation, not a Mockito mock. The SMTP server is a local test component/process, not a production email provider. `greenMail.stop()` releases the listener/socket and mailbox bound to that instance after the test.

Port `0` asks the OS for an ephemeral free port. Reading the actual port via `getSmtp().getPort()` matches the GreenMail API used here; check your specific library version's accessor.

### 4.3. Why Per-Test Instances Resist State Contamination

~~~text
test A:
  GreenMail A -> 1 message -> stop A

test B:
  GreenMail B -> 0 messages at start -> stop B
~~~

Test B never needs to purge Test A's mailbox; it gets a fresh server. Even if JUnit runs both methods in parallel, each method uses its **own instance and port**. Other shared state such as a singleton database or shared queue still requires independent isolation.

### 4.4. Teardown Must Handle Every Created Resource

If a test also creates attachment files or a dedicated executor, `greenMail.stop()` alone is not enough. Close/stop everything in the proper order:

~~~text
Stop producing new mail
  -> wait/cancel background tasks
  -> release message/stream references
  -> stop SMTP server
  -> delete test files
~~~

The exact order may vary depending on resource dependencies; the rule is never deleting files or servers **while a task is still using them**.

## 5. Sharing One GreenMail Across a Test Class

If SMTP server startup is expensive, start the server once for all methods and **purge mailboxes between tests**.

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Execution(ExecutionMode.SAME_THREAD)
class SharedGreenMailIntegrationTest {
    private GreenMail greenMail;

    @BeforeAll
    void startServer() {
        greenMail = new GreenMail(new ServerSetup(
                0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP));
        greenMail.start();
    }

    @BeforeEach
    void clearBefore() {
        greenMail.purgeEmailFromAllMailboxes();
    }

    @AfterEach
    void clearAfter() {
        greenMail.purgeEmailFromAllMailboxes();
    }

    @AfterAll
    void stopServer() {
        if (greenMail != null) {
            greenMail.stop();
        }
    }
}
~~~

This is a **lifecycle template**; add test methods and `JavaMailSender` configured to the server port for your application. `purgeEmailFromAllMailboxes()` clears messages inside mailboxes managed by that GreenMail instance without stopping/restarting the SMTP server.

### 5.1. Caveats When Using Purge-All

Only call purge-all when:

1. The SMTP server belongs exclusively to a controlled class/suite.
2. No other test is running concurrently against the same mailbox/server.
3. No asynchronous worker from a prior test is still sending mail.
4. No stale job/queue entry can push mail into the inbox after the purge.

If condition 2 or 3 fails, the inbox may look clean during `@BeforeEach` only to receive stale mail a few milliseconds later.

### 5.2. Never Stop a Shared Server After Each Method

Wrong for a shared instance:

~~~java
@AfterEach
void tearDown() {
    greenMail.stop();
}
~~~

if `@BeforeAll` only started it once. Subsequent methods would connect to a stopped server. Distinguish **purging messages** from **stopping the server**:

~~~text
per-class server:
  BeforeAll -> start
  BeforeEach/AfterEach -> purge state
  AfterAll -> stop
~~~

### 5.3. Purge Clears Only the Mailbox, Not the Whole System

`purgeEmailFromAllMailboxes()` does not automatically:

- delete outbox jobs in the database;
- stop schedulers;
- remove messages from RabbitMQ/Kafka;
- close files/streams;
- wipe another Mailpit container;
- clear Spring singleton bean caches;
- cancel scheduled retries.

Therefore, plan coordinated cleanup across the components that produce emails.

## 6. Using a Spring Boot Context with an SMTP Test Server

A `@SpringBootTest` integration test normally obtains `JavaMailSender` from the application context. Host/port configuration must point to **a test server already started before the context creates the sender**.

One way is combining `@DynamicPropertySource` with a class-scoped server:

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class SpringBootMailIntegrationTest {
    private static final GreenMail SMTP = new GreenMail(
            new ServerSetup(
                    0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP));

    static {
        SMTP.start(); // Before Spring requires dynamic properties.
    }

    @DynamicPropertySource
    static void mailProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.mail.host", () -> "127.0.0.1");
        registry.add("spring.mail.port",
                () -> SMTP.getSmtp().getPort());
        registry.add("spring.mail.properties[mail.smtp.auth]",
                () -> "false");
        registry.add(
                "spring.mail.properties[mail.smtp.starttls.enable]",
                () -> "false");
    }

    @Autowired
    InvoiceNotificationService invoiceNotifications;

    @BeforeEach
    void emptyMailboxes() {
        SMTP.purgeEmailFromAllMailboxes();
    }

    @Test
    void sendsInvoiceNotification() throws Exception {
        invoiceNotifications.sendTestInvoice(
                "alice@example.test", "INV-123");

        assertTrue(SMTP.waitForIncomingEmail(5_000L, 1));
        assertEquals(1, SMTP.getReceivedMessages().length);
    }

    @AfterAll
    static void stopSmtp() {
        SMTP.stop();
    }
}
~~~

`InvoiceNotificationService` and `sendTestInvoice(...)` are illustrative application code, not built-in Spring APIs. In projects with multiple sender beans or custom configuration profiles, map the corresponding properties to your actual setup.

### 6.1. Why Start the Server in a Static Initializer?

`@DynamicPropertySource` needs the real bound port when Spring builds the context. Waiting until `@BeforeEach` to start the server risks creating the context and binding the sender to a missing or stale port.

Libraries and versions vary in lifecycles; the invariant is that **the SMTP test server must be ready before properties are resolved and the SMTP bean is used**.

### 6.2. Why Is @DirtiesContext Used?

Spring Test caches application contexts for speed. If Class A's context points to GreenMail A's port and A stops its server in `@AfterAll`, a Class B reusing that cached context would still point to the closed port.

`@DirtiesContext(classMode = AFTER_CLASS)` marks the context so it is not reused after the class ends. This is one way to avoid cached contexts holding expired dynamic settings.

However, `@DirtiesContext` incurs context-restart overhead; do not slap it onto every test without reason. Structuring Testcontainers/Spring context lifecycles properly lets one server stay alive for the context's lifetime without dirtying contexts after every method.

### 6.3. Never Disable TLS in Production

In the example, `mail.smtp.starttls.enable=false` is only valid when the local test server runs plaintext SMTP on loopback by design. Production requires TLS/STARTTLS, authentication, and hostname verification per provider.

Never copy this test config into `application-prod.yml` just to make tests pass.

## 7. Mailpit/MailHog and Testcontainers

Some teams replace GreenMail with Mailpit or MailHog for a web UI and mailbox management API. When running via Testcontainers, state layers include:

1. Mailpit/MailHog **container/process**.
2. **Message store** inside the container.
3. Docker **host port mappings**.
4. **Spring application context** pointing to the SMTP host/port.
5. **Test messages** per scenario.

Architecture example:

~~~text
JUnit / Spring Test
      |
      +--> Testcontainers Mailpit
      |       SMTP listener (container port)
      |       HTTP API/UI (container port)
      |
      +--> Spring JavaMailSender
              -> mapped SMTP host/port

AfterEach:
  API delete messages owned by this test,
  or purge mailbox only if server is not shared concurrently

AfterAll / container lifecycle:
  Testcontainers stops container and releases ports
~~~

### 7.1. Testcontainers Pattern

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@Testcontainers
class MailpitContainerIntegrationTest {

    // Replace <approved-version> with a project-approved image tag.
    @Container
    static final GenericContainer<?> MAILPIT =
            new GenericContainer<>(
                    DockerImageName.parse(
                            "axllent/mailpit:<approved-version>"))
                    .withExposedPorts(1025, 8025);

    @DynamicPropertySource
    static void smtpProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.mail.host", MAILPIT::getHost);
        registry.add(
                "spring.mail.port", () -> MAILPIT.getMappedPort(1025));
    }

    @Test
    void testSendingToMailpit() {
        // Call service, inspect messages via Mailpit test client/API.
    }
}
~~~

This example illustrates container lifecycle and mapped ports; it omits HTTP API querying/purging since endpoints and authentication depend on your Mailpit version. With `@SpringBootTest`, configure that annotation and the matching auth/TLS properties for the test server.

`<approved-version>` is a placeholder, not a runnable image tag. In CI, **pin** a tested version instead of using `latest` to avoid sudden upstream changes.

### 7.2. Cleaning Messages via API

A test helper can expose an interface:

~~~java
public interface TestMailboxClient {
    void deleteMessagesOwnedBy(String testRunId);
    List<TestMailSummary> findMessagesByCorrelationId(
            String correlationId);
}
~~~

Implementations use the corresponding Mailpit/MailHog/provider sandbox API with test-environment authentication. **Never guess a universal delete-all URL** across tools: endpoints, permissions, filter syntax, and batch support vary by version.

If a tool only offers purge-all while a container is shared across tests, choose one of:

- run related tests sequentially using a resource lock;
- provision a dedicated container per test class;
- separate mailbox namespaces per test;
- store a test ID and delete only that test's messages if the API supports it.

### 7.3. Container Teardown Does Not Replace DB Cleanup

Testcontainers stops containers per lifecycle, yet the application's database/outbox may run in another container/service. If workers still hold `PENDING` jobs, later tests or restarts can send emails into the new container.

Clean up **the message producer**, not only the receiving inbox.

## 8. Using Correlation IDs to Isolate Messages

Purging the whole mailbox is not always safe. When sharing a test SMTP server, attach a **per-test ID** to messages or metadata.

Example:

~~~text
X-Test-Run-Id: it-20261112-7c3b
X-Correlation-Id: order-A123-test-7c3b
~~~

In an integration test:

1. Generate a fresh `testRunId`.
2. Invoke the use case so it tags the message with that ID.
3. Wait for messages matching `testRunId`.
4. Assert only on messages matching the ID.
5. Delete messages owned by the test if API and permissions allow.

This avoids assertions depending on the total email count across all tests:

~~~java
assertEquals(
        1,
        mailbox.findMessagesByCorrelationId(testRunId).size()
);
~~~

Instead of:

~~~java
assertEquals(
        1,
        mailbox.getAllMessages().size()
);
~~~

### 8.1. Should Test-Only Headers Be Placed in Production Messages?

A custom test header is helpful, yet production code must never emit test IDs or sensitive data in headers on its own. Options:

- inject a correlation ID that is already an approved product tracing feature;
- use a dedicated recipient mailbox generated per test or test tenant;
- use an internal message/job ID and query via the provider's test API;
- configure a decorator sender **active only under the test profile** to attach the marker.

Never put personal data, secrets, or tokens into headers like `X-Test-Run-Id`. If test IDs can appear in logs or SMTP messages, use short-lived opaque values only.

### 8.2. Filtering by Recipient Is Not Always Enough

Using `test@example.test` for every test still mixes messages together. When filtering by recipient, give each test or group its own address/alias supported by the test server, such as:

~~~text
order-7c3b@example.test
reset-9a4d@example.test
~~~

Never assume every mailbox server handles plus-addressing or wildcard mailboxes identically. Verify the test tool's API and configuration.

## 9. Async Trap: Emails Arriving After Cleanup

Example system with `@Async` or a background mail worker:

~~~text
T1 Test publishes OrderConfirmedEvent
T2 Test reads inbox: currently 0 emails
T3 Test @AfterEach purges mailbox
T4 Worker finally runs and sends email
T5 Next test starts, inbox already contains stale email
~~~

This is a very common cause of flaky tests. **Clearing the mailbox does not mean email producers have stopped.**

### 9.1. Wait for Concrete Events/Conditions Instead of Fixed Sleeps

Avoid:

~~~java
Thread.sleep(2000);
assertEquals(1, greenMail.getReceivedMessages().length);
~~~

Two seconds may be needlessly slow on fast machines or too short on slow CI. Use conditional waits with finite timeouts.

With GreenMail:

~~~java
assertTrue(greenMail.waitForIncomingEmail(5_000L, 1));
assertEquals(1, greenMail.getReceivedMessages().length);
~~~

With an async store/outbox and a condition-waiting library like Awaitility:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() -> {
        assertEquals(
                1,
                mailbox.findMessagesByCorrelationId(testRunId).size()
        );
    });
~~~

`await()` is Awaitility's API if your project includes that dependency. Import `org.awaitility.Awaitility.await` and `java.time.Duration`. This illustrates **condition-based** waiting, not a requirement to add Awaitility to every test.

### 9.2. Also Wait Until Producers Are Quiescent

Waiting for "1 email received" is not enough if a worker is still running and might send a second email.

For critical workflows, test completion conditions can include:

~~~text
Job belonging to testRunId:
  terminal status (SUBMITTED or FAILED_FINAL)

Worker:
  zero remaining active attempts for testRunId

Mailbox:
  received expected messages belonging to testRunId
~~~

Only then purge and tear down the server. If the application uses a retry queue, inspect any pending delayed retries and proactively cancel/clean them by `testRunId`.

### 9.3. Watch Out for @Async and the Spring Context

If `@Async` runs on an executor owned by the Spring context, stopping the SMTP server before the executor finishes can cause connection refused errors or noisy logs after the test.

Tests can:

- configure a dedicated test executor to track tasks;
- use latches or application-level test hooks to observe terminal job states;
- disable unrelated schedulers via the test profile;
- await completion with a timeout before cleaning up;
- avoid unmanaged global/static executors.

Never "fix" this with `Thread.sleep(...)` or by ignoring teardown errors.

## 10. Cleaning Up Outboxes and Databases Between Tests

In Spring Mail applications with a transactional outbox:

~~~text
Database transaction
  -> INSERT order
  -> INSERT mail_outbox
  -> COMMIT

MailWorker
  -> scan/claim outbox
  -> SMTP send
  -> update status
~~~

If a test clears the inbox without clearing `mail_outbox`, old jobs can keep getting picked up by workers. If it deletes outbox rows while a worker already claimed a message, the worker may still hold the payload in memory and send it afterwards.

### 10.1. Test Transaction Rollback Does Not Recall Sent Emails

Spring tests can annotate methods `@Transactional` to auto-roll back data at test end. However, SMTP submission is a side effect outside the database:

~~~text
BEGIN test transaction
UPDATE order
SMTP send (server already received email)
ROLLBACK database

Database: order no longer exists
Mailbox: email still exists
~~~

Therefore, **`@Transactional` test rollback does not replace SMTP mailbox cleanup**.

### 10.2. AFTER_COMMIT Does Not Run When Tests Roll Back

If the application sends email via `@TransactionalEventListener(phase = AFTER_COMMIT)`, a test rolled back by default by Spring Test may never trigger the listener.

To test commit behavior:

- use `TransactionTemplate` and let the transaction actually commit;
- or configure `@Commit` for the appropriate scenario;
- or invoke the use case outside a rolling-back test-level transaction.

Afterwards, clean up the **committed** data explicitly rather than expecting Spring to roll it back.

### 10.3. Choosing a Database Cleanup Mechanism

Common options:

| Option | Suitable For | Watch Out For |
| --- | --- | --- |
| Test transaction rollback | Data modified inside test transaction | Does not roll back SMTP/broker side effects |
| `@Sql` cleanup | Committed data with stable schemas | Foreign-key order, transaction mode |
| Repository delete by `testRunId` | Shared DB with test namespaces | Never delete another test's rows |
| Dedicated Testcontainers DB | Class/suite-level DB isolation | Startup time, context lifecycle |
| DB/schema per test | Strongest isolation | Requires migrations and dynamic datasource setup |
| Controlled database cleaner | Isolated test DB | Never run on shared/prod databases |

Illustrative `@Sql` example for an **isolated test database**:

~~~java
@Sql(
    statements = {
        "DELETE FROM mail_attempt WHERE test_run_id = 'test-344'",
        "DELETE FROM mail_outbox WHERE test_run_id = 'test-344'",
        "DELETE FROM orders WHERE test_run_id = 'test-344'"
    },
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
~~~

In practice, test IDs are usually generated dynamically; static `@Sql` as above works only with fixed fixture IDs or dedicated schemas. When `testRunId` is generated per test, use repository/`JdbcTemplate` prepared statements to delete exact matching rows. Understand your application's phase, transactions, and foreign-key constraints.

### 10.4. Cleanup Order When Workers Are Active

A safe sequence is usually:

1. Stop or block new jobs belonging to the test.
2. Await in-flight attempts or cancel them cleanly.
3. Delete retry/delayed tasks for the test.
4. Delete outbox/event/attempt rows for the test in proper FK order.
5. Delete test emails in the SMTP mailbox.
6. Release resources, connections, and files.

Never delete an outbox row while a worker still holds a reference without coordination. If the worker sends after cleanup, the next test gets polluted state.

## 11. Cleaning Up Queues and Brokers Between Tests

RabbitMQ, Kafka, Redis Streams, or internal queues can retain:

- unconsumed events;
- scheduled retry jobs;
- unacked/in-flight messages;
- dead-letter entries;
- consumer group offset/ack state;
- duplicate deliveries.

Clearing the mailbox alone does not clear any of these states.

### 11.1. Use Dedicated Queues or Namespaces per Test

During parallel tests, a strong strategy is:

~~~text
test A -> queue mail-test-A -> SMTP mailbox/tag A
test B -> queue mail-test-B -> SMTP mailbox/tag B
~~~

If per-test queues are impractical, embed `testRunId` in payloads and use scoped job lookup/deletion. Note that Kafka and some brokers do not support "arbitrarily deleting one event mid-stream" like a database; you may need separate topics, consumer groups, or containers.

### 11.2. Never Purge a Shared Queue During Parallel Tests

~~~text
Test A creates job A
Test B purges shared queue
Test A waits -> timeout
~~~

Purge-all is a **global** operation. Use it only when the queue is exclusively owned by that test or the entire suite guarantees no concurrent activity.

### 11.3. Retries and Dead Letters

A failing job may be rescheduled seconds or minutes later. Teardown must:

- know where retry schedulers live;
- cancel or mark terminal any jobs belonging to the test;
- clean delayed queues if the broker supports it and ownership is clear;
- prevent retries from firing after the test server stops.

In CI, tune long retry delays via a **test profile** or controllable test clock/scheduler so tests do not wait real minutes. Still preserve accurate semantics rather than accidentally stripping out the retry behavior under test.

## 12. Cleaning Up Attachments and I/O Resources

Emails with attachments often read from temporary files, `InputStream`s, or application-created resources.

Example:

~~~java
helper.addAttachment(
        "invoice-A123.pdf",
        new FileSystemResource(file)
);
~~~

In many implementations, attachment bytes are only read when the message is serialized/sent. If you delete the file **right after calling `addAttachment(...)`** yet before `sender.send(...)`, sending fails because the file is gone.

### 12.1. Using @TempDir

JUnit 5 provides `@TempDir`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class AttachmentMailIntegrationTest {
    @TempDir
    Path tempDir;

    @Test
    void sendsPdfAttachment() throws Exception {
        Path pdf = tempDir.resolve("invoice-A123.pdf");
        Files.write(pdf, fakePdfBytes());

        // Service uses this file to build MIME attachment and send over SMTP.
        invoiceMailer.sendInvoice(
                "alice@example.test", pdf);

        // Wait for sender/worker to complete before test finishes.
        // JUnit cleans up tempDir after test per @TempDir lifecycle.
    }
}
~~~

`fakePdfBytes()` and `invoiceMailer` are illustrative fixtures/services. Test directories must live on test filesystems; never reference production attachment paths.

**If emails send asynchronously**, tests must wait until the job finishes reading the attachment before exiting. Otherwise, JUnit may delete `tempDir` while the worker is still reading the file.

### 12.2. ByteArrayResource Helps for Small Attachments

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] bytes = fakePdfBytes();
helper.addAttachment(
        "invoice-A123.pdf",
        new ByteArrayResource(bytes),
        "application/pdf"
);
~~~

`ByteArrayResource` keeps bytes in memory and allows reopening streams, which is convenient for small MIME tests. Avoid this for very large files due to heap consumption.

### 12.3. InputStreamResource and Single-Use Streams

Some `InputStream`-wrapping resources are single-use. MIME/JavaMail may read the stream at send or serialization time; if code already closed or drained the stream, the email may miss its attachment.

When testing:

- use `ByteArrayResource` for small payloads;
- or use `FileSystemResource` and keep the file alive until sending completes;
- if using a custom `InputStreamSource`, obey the contract of opening a fresh stream on demand;
- close streams opened directly by tests using `try-with-resources`;
- never assume constructing a `MimeMessage` already finished reading all attachments.

### 12.4. Closing Streams Properly

~~~java
try (InputStream input =
        Files.newInputStream(tempFile)) {
    byte[] bytes = input.readAllBytes();
    // Use bytes to build fixtures or verification checksums.
}
~~~

For streams returned by `Part.getInputStream()`, also close them with `try-with-resources` after reading.

### 12.5. Never Delete Files Owned by Other Workers

A serious bug:

~~~java
@AfterEach
void cleanup() {
    deleteRecursively(sharedUploadDirectory);
}
~~~

if that directory holds attachments from multiple tests or services. Delete only **subdirectories scoped to `testRunId`** or use JUnit-isolated `@TempDir`.

## 13. Resource Leaks from Transports and Connection Pools

When sending via `JavaMailSenderImpl`, the library opens SMTP transports, streams, and sockets. If tests use Jakarta Mail `Transport` directly, manage object lifecycles carefully.

Example:

~~~java
Transport transport = session.getTransport("smtp");
try {
    transport.connect(host, port, user, password);
    transport.sendMessage(
            mimeMessage,
            mimeMessage.getAllRecipients()
    );
} finally {
    if (transport.isConnected()) {
        transport.close();
    }
}
~~~

This illustrates **low-level Jakarta Mail transport**; applications calling `JavaMailSender.send(...)` normally do not acquire/close `Transport` manually like this.

### 13.1. Things You Must Not Close Prematurely

- Never stop the test SMTP server before senders/workers finish.
- Never close a `DataSource` shared across the Spring context after each test method.
- Never stop a Testcontainers container still used by other classes/suites.
- Never call `ExecutorService.shutdownNow()` on a shared executor not owned by the test.
- Never delete attachment files before `MimeMessage` serialization/sending finishes.

The rule is **close by owner**, not closing every object in sight.

### 13.2. Server Port Collisions

Symptom:

~~~text
java.net.BindException: Address already in use
~~~

Common causes:

- previous test did not stop the SMTP server;
- multiple tests use the same fixed port;
- an external process occupies the port;
- shared-server classes have inconsistent start/stop lifecycles.

Mitigations:

- pick dynamic ports when supported by the library;
- use container mapped ports;
- guarantee `@AfterEach`/`@AfterAll` cleanup;
- avoid creating multiple servers via an unmanaged static singleton.

Do not probe for a random free port in custom code and bind much later: a race exists between probing and binding. Binding port `0` and reading the assigned port is preferable when supported.

## 14. Parallel Tests and Race Risks

JUnit 5 can run tests in parallel. A shared mailbox is **mutable global state**:

~~~text
Test A: send mail A
Test B: @BeforeEach purge inbox
Test A: assert mail A exists -> fail
~~~

If running in parallel, preferred options are:

1. Dedicated SMTP server/port per test.
2. Dedicated container/mailbox per class.
3. Shared server where each test uses a unique recipient/correlation ID and **never purges all**.
4. For un-isolatable shared servers, run sequentially using locks and consistent lifecycles.

### 14.1. ResourceLock

Example:

~~~java
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock(
        value = "shared-smtp-mailbox",
        mode = ResourceAccessMode.READ_WRITE)
class SharedMailboxIntegrationTest {
    // Other test classes using the same mailbox must also
    // declare ResourceLock with the same name to coordinate.
}
~~~

`@ResourceLock` only coordinates tests within JUnit's locking mechanism. It does not lock separate CI processes or tools outside JUnit. When multiple JVMs/test runners share an SMTP sandbox, isolate at the infrastructure level rather than relying solely on annotations.

### 14.2. Sequential Execution Does Not Prevent Late Async Mail

Even when methods run one by one:

~~~text
Test A ends before async job completes
Test B starts
Job A sends email while Test B is running
~~~

Thus, you still must wait for terminal job states or block stale tasks, rather than relying solely on `@Execution(SAME_THREAD)`.

## 15. Testing the Absence of Unintended Emails

A test may require **no email sent** when rollback or validation fails:

~~~text
Given invalid recipient
When application rejects request
Then no mail is sent
~~~

In synchronous tests, you can check an empty inbox right after the call returns. In async workflows, `inbox.isEmpty()` at one instant does not prove a task will not send late.

### 15.1. Negative Assertions Must Define an Observation Window

A strong test can:

1. Invoke the use case.
2. Wait for the application process/transaction to reach a terminal state.
3. Verify no send job was created or the job was marked canceled.
4. Verify no message belonging to `testRunId` exists in the mailbox.

Without a system completion signal, explicitly note the negative assertion's boundary and use a bounded wait window; never turn "not seen yet" into "will never be sent".

### 15.2. When Verifying Exactly One Send

If a test needs to assert exactly one message:

~~~java
assertEquals(
        1,
        mailbox.findMessagesByCorrelationId(testRunId).size()
);
~~~

ensure that:

- events/workers finished processing;
- retries and delayed queues for the job reached terminal state;
- the correlation ID represents a single logical request;
- the test never counts messages from other tests.

Only assert `getReceivedMessages().length == 1` when the mailbox is truly isolated or properly purged.

## 16. Controlling Time with Clock and Test Schedulers

Some emails are sent after a delay:

~~~text
Order placed
  -> 15 minutes later sends reminder
~~~

If an integration test checks cleanup, calling `Thread.sleep(15 minutes)` is impractical.

Design options:

- inject `Clock` so tests control time;
- use a controllable scheduler in tests;
- shorten delays via test config while preserving tested behavior;
- persist jobs with `nextAttemptAt` and trigger workers deterministically;
- await terminal state with a finite timeout.

Importantly, cleanup must account for **scheduled tasks that have not run yet**. If a test wipes the database before the scheduler fires, workers may error out or send obsolete messages.

### 16.1. Cancelling Retry Jobs by testRunId

An adapter can provide:

~~~java
public interface TestMailJobs {
    void cancelPendingJobsFor(String testRunId);
    void awaitNoActiveAttemptsFor(
            String testRunId, Duration timeout);
    void deleteTerminalJobsFor(String testRunId);
}
~~~

This is a project-defined **test support interface**, not a default Spring Mail API. It creates an explicit synchronization point between the application and cleanup instead of poking blindly at queues.

## 17. Teardown Must Be Safe When Setup Partially Fails

Suppose in `@BeforeEach`:

1. Starting the SMTP server succeeds.
2. Starting the queue consumer fails.
3. The mail sender was not created yet.

If `@AfterEach` assumes every resource was initialized, cleanup can throw `NullPointerException` and mask the root failure.

Example:

~~~java
private GreenMail smtp;
private ExecutorService executor;

@AfterEach
void tearDown() {
    if (executor != null) {
        executor.shutdownNow(); // Only the test-owned executor.
    }

    if (smtp != null) {
        smtp.stop();
    }
}
~~~

In practice, shut down executors gracefully with a deadline: stop accepting new tasks, await in-flight tasks, then force-stop if needed. `shutdownNow()` does not guarantee immediate task termination and may interrupt network operations; the example illustrates **null-safe teardown**.

### 17.1. Using try/finally for Local Resources

When a resource is needed only inside one method:

~~~java
GreenMail smtp = createAndStartTestSmtp();
try {
    // Arrange, act, assert.
} finally {
    smtp.stop();
}
~~~

`try/finally` is clear when fixture reuse is unnecessary. For multiple resources, prefer `AutoCloseable` or a JUnit extension where appropriate.

### 17.2. Avoid Deleting Data Before Collecting Diagnostics

When a test fails, we often want to inspect:

- how many messages were received;
- message subject/recipients;
- worker/job state;
- SMTP replies or error codes;
- related correlation IDs.

If `@AfterEach` purges immediately, debugging gets harder. You can:

1. Use a `TestWatcher` or extension callback to capture **safe metadata** on failure.
2. Purge/stop the server afterwards.
3. Never store full raw messages containing PII/OTPs/secrets in CI artifacts.

Never keep resources alive indefinitely just because a test failed; clean up on failures too.

## 18. A Test Utility to Manage Lifecycles

Across multiple test classes, wrap start/cleanup/stop logic in a reusable fixture.

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class TestSmtpFixture implements AutoCloseable {
    private final GreenMail greenMail;
    private final JavaMailSenderImpl sender;

    public TestSmtpFixture() {
        greenMail = new GreenMail(new ServerSetup(
                0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP));
        greenMail.start();

        sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(greenMail.getSmtp().getPort());
        sender.setProtocol("smtp");
        sender.getJavaMailProperties()
                .put("mail.smtp.auth", "false");
    }

    public JavaMailSenderImpl sender() {
        return sender;
    }

    public GreenMail server() {
        return greenMail;
    }

    @Override
    public void close() {
        greenMail.stop();
    }
}
~~~

Usage:

~~~java
@Test
void sendsOneMessage() throws Exception {
    try (TestSmtpFixture smtp = new TestSmtpFixture()) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("sender@example.test");
        mail.setTo("alice@example.test");
        mail.setSubject("Hello");
        mail.setText("Integration test");

        smtp.sender().send(mail);

        assertTrue(
                smtp.server().waitForIncomingEmail(5_000L, 1));
        assertEquals(
                1,
                smtp.server().getReceivedMessages().length);
    }
}
~~~

The fixture centralizes ownership of the server and sender. When the block exits, `close()` runs even if assertions fail. If tests create extra DB/broker/file resources, include them in the fixture or another extension with an explicit teardown order.

### 18.1. Fixtures Must Not Hold Unscoped Static State

Never store a `static GreenMail` and let all tests call `purgeEmailFromAllMailboxes()` if suites run in parallel or across multiple JVMs.

If sharing for speed, scope fixtures to classes/suites, lock access, or partition state. **A singleton is not automatically a safe fixture.**

## 19. Integration Test Scenarios Requiring Different Cleanup

| Scenario | Key State | Primary Cleanup |
| --- | --- | --- |
| Single plain-text send | SMTP mailbox | Stop dedicated server or purge |
| HTML send with inline images | MIME + resources/streams | Wait for send; close I/O; clean files |
| PDF send from `@TempDir` | Temp file + mailbox | Wait for completion, let JUnit clean |
| `@TransactionalEventListener` send | Transaction + event + mailbox | Intentionally commit test; clean DB/mailbox |
| `@Async` send | Executor + mailbox | Wait for terminal task, then purge |
| Transactional outbox send | Outbox + worker + mailbox | Cancel/drain jobs; clean DB; purge |
| Retry after SMTP 4xx | Retry queue/delayed jobs | Cancel pending retries by test ID |
| SMTP auth failure test | SMTP connections and logs | Stop server; never persist credentials |
| Bounce webhook test | Provider event + DB status | Clean webhook fixtures/DB, not just inbox |
| Multiple parallel tests | Shared mailbox/queue | Namespaces, dedicated servers, or locks |
| Testcontainers SMTP | Container + HTTP inbox | Clean scoped messages, stop per lifecycle |
| Mid-test failure | Partially created resources | Null-safe teardown, minimal diagnostics |

## 20. Common Failures and Root Causes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Second test sees 2 emails instead of 1 | Mailbox retained email from prior test | Per-test server or scoped purge |
| Test passes sometimes, fails others | Async worker sent late after cleanup | Await terminal state, isolate jobs |
| `Address already in use` | Unstopped server or fixed port | Teardown + dynamic ports |
| Passes locally, fails in CI | Slower timing, races, port collisions | Bounded waits, test isolation |
| Test A loses messages in parallel runs | Test B purged shared mailbox | Server/recipient namespaces or resource locks |
| SMTP connects to wrong port | Context cache holds stale dynamic port | Align context and server lifecycles |
| Attachment file not found | File deleted before sending | Wait for send completion, use `@TempDir` |
| Windows cannot delete temp file | Unclosed stream/file handle | `try-with-resources` |
| Test rolled back DB yet inbox has mail | SMTP is outside DB transaction | Clean mailbox separately |
| `AFTER_COMMIT` did not send in test | Test transaction rolls back by default | Commit in scenarios requiring it |
| Old mail reappears after purge | Uncleaned retry/outbox job | Stop producers, cancel/drain retries |
| `@AfterEach` throws NPE | Setup failed mid-way | Null-safe cleanup |
| Stopping container breaks other tests | Shared container | Only owner stops it, match scope |
| Another test's email gets deleted | Purge-all on shared server | Delete by ID or isolate inboxes |
| Negative assertion fails randomly | No async completion signal | Wait for terminal workflow state |
| Raw email/OTP appears in CI logs | Dumping `MimeMessage` for debugging | Log metadata only, synthetic fixtures |

## 21. End-to-End Scenario: Order Confirmation Test via Outbox

Suppose the application runs:

~~~text
POST /orders/A123/confirm
   |
   v
Database transaction
   -> update order
   -> insert mail_outbox(key=order-confirmed:A123:evt-1)
   -> COMMIT
   |
   v
MailWorker
   -> create MimeMessage
   -> SMTP to GreenMail/Mailpit
   -> update job SUBMITTED
~~~

Tests can use a unique `testRunId`:

~~~text
testRunId = it-344-7c3b
orderId   = order-it-344-7c3b
mailKey   = order-confirmed:it-344-7c3b
recipient = order-it-344-7c3b@example.test
~~~

### 21.1. Arrange

1. Start an isolated SMTP server (or pick an isolated mailbox namespace).
2. Point the Spring Mail sender to the test SMTP server.
3. Insert database fixtures tagged with `testRunId`.
4. Ensure the scheduler/worker can process the test's job.
5. Confirm no stale jobs/messages exist for `testRunId`.

### 21.2. Act

Invoke the order-confirmation use case, allowing the database transaction to genuinely **commit** when testing outbox/`AFTER_COMMIT` flows.

### 21.3. Assert

Wait for:

~~~text
outbox job:
  status = SUBMITTED

SMTP mailbox:
  1 message belonging to testRunId

MimeMessage:
  To, From, Subject, and body are accurate
~~~

Do not count every message in a shared mailbox across multiple tests. Use correlation IDs, unique recipients, or an exclusively purged fixture.

### 21.4. Cleanup

1. Stop or await workers processing `testRunId`.
2. Cancel any remaining retry/delayed jobs for the test.
3. Clean up attempt/outbox/order rows belonging to the test.
4. Delete the test's SMTP messages or stop the dedicated SMTP instance.
5. Close I/O and clean `@TempDir` after sending finishes.
6. Stop containers/servers per owner lifecycle.

### 21.5. Why Does Ordering Matter?

Wrong:

~~~text
purge mailbox
delete order
worker still running
worker submits email
Test B reads Test A's message
~~~

Better:

~~~text
await/cancel worker A
ensure zero retries remain for A
cleanup DB for A
purge mailbox for A
stop server if A owns the server
~~~

Exact sequencing varies by architecture, yet you must ensure **no old producers remain active** before declaring the inbox clean.

## 22. Message and Resource Cleanup Checklist

### Isolation

- [ ] SMTP server/mailbox has clear ownership scope (per test/class/suite).
- [ ] Mailboxes are never shared with production or other environments.
- [ ] Test SMTP ports are dynamic or exclusively managed.
- [ ] When running in parallel, proper namespaces or locks are applied.

### Message

- [ ] Before-test state is deterministic: empty mailbox or filtered strictly by `testRunId`.
- [ ] Assertions never accidentally count emails from other tests.
- [ ] After-test purges stay strictly within authorized scope.
- [ ] Messages are never deleted before all assertions finish inspecting them.

### Async and Data

- [ ] Wait for terminal job/attempt states before cleanup.
- [ ] Cancel delayed retries and clean test outbox rows.
- [ ] DB test rollbacks are never mistaken for SMTP rollbacks.
- [ ] For `AFTER_COMMIT`, scenarios genuinely commit when required.
- [ ] Never purge queues/brokers shared with other tests.

### Resources

- [ ] SMTP listeners/containers are stopped by their rightful owner.
- [ ] Stream/file handles are closed.
- [ ] Attachment files stay intact until MIME is sent/serialized.
- [ ] Use `@TempDir` or per-test isolated directories.
- [ ] Test-created executors/schedulers shut down per lifecycle.

### Stability and Safety

- [ ] Wait on conditions with timeouts rather than arbitrary `Thread.sleep`.
- [ ] Teardown runs even when tests fail or setup is incomplete.
- [ ] Never log passwords, tokens, OTPs, or unnecessary PII.
- [ ] Dynamic ports and Spring context caches have aligned lifecycles.
- [ ] Never infer real delivery from test SMTP server results.

## 23. Key Takeaways

- **SMTP mailboxes are state that persists across tests**, requiring proper isolation or purging.
- **Per-test servers** are simplest and cleanest; **per-class servers** can be faster yet require cleanup and concurrency controls.
- Use `@AfterEach`/`@AfterAll` or `try/finally`/`AutoCloseable` to release resources even when assertions fail.
- `@Transactional` rollbacks apply only to DB transactions, never deleting sent emails.
- Async workers, schedulers, and retry queues can send emails **after the inbox was cleared**.
- Clean up email producers (outbox/queues/tasks) before declaring a mailbox clean.
- `@TempDir` manages attachment files, though only clean up after workers finish reading them.
- Parallel tests need dedicated servers/recipient namespaces or resource locks; purge-all on shared servers breaks other tests.
- `@DynamicPropertySource` and Spring context caches must stay synchronized with test SMTP server/container lifecycles.
- Integration tests with GreenMail/Mailpit verify **submission and received contents at the test server**, not delivery to real user Inboxes.

Cleaning up messages and resources between tests is more than calling `clearInbox()`. A reliable Spring Framework Mail integration suite must define **who owns each state, when producers have stopped, and what scope may be deleted**. When SMTP servers, mailboxes, outboxes, queues, workers, and attachment files have well-designed lifecycles, tests stay independent, CI-friendly, and free from order- or timing-dependent flakiness.

### References

- **Spring Framework Reference - Testing:** managing test contexts, transactions, SQL scripts, and lifecycles.
- **Spring Boot Reference - Testing and Sending Email:** configuring mail senders in integration tests.
- **Spring Framework API - JavaMailSender / JavaMailSenderImpl:** SMTP submission and sending methods.
- **JUnit 5 User Guide:** `@BeforeEach`, `@AfterEach`, `@BeforeAll`, `@AfterAll`, `@TempDir`, parallel execution, and `@ResourceLock`.
- **GreenMail documentation:** embedded SMTP server, `getReceivedMessages`, `purgeEmailFromAllMailboxes`, and server lifecycles.
- **Mailpit/MailHog documentation:** SMTP test inboxes, search/delete message APIs, and container configuration.
- **Testcontainers for Java documentation:** container lifecycles, mapped ports, JUnit Jupiter integration.
- **Spring Test - DynamicPropertySource and DirtiesContext:** dynamic port configuration and application context caching.
- **Jakarta Mail API - MimeMessage, Multipart, Transport:** MIME messages and mail resource management.
- **Awaitility documentation:** bounded waiting when testing asynchronous workflows.
