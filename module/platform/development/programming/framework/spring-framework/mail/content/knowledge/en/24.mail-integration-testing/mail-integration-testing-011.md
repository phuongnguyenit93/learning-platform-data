# Avoiding Order-Dependent Tests and Shared Mailboxes

In **Spring Framework Mail** applications, integration tests typically create an email-sending request, let `JavaMailSender` communicate with a test SMTP server, and then read captured messages to verify recipients, subjects, and contents. This testing style is valuable because it traverses more real components than unit tests. However, if tests share a mailbox or rely on another test having sent or deleted emails beforehand, outcomes can shift depending on execution order and parallelism.

Familiar symptoms include: running a single test passes yet running the whole suite fails; seeing one email sometimes and three other times; confusing an order confirmation email with a password-reset email; or CI failing randomly because another test just wiped the whole inbox. This is a **test isolation** issue, not simply a slow SMTP server.

A reliable integration test must **set up its own preconditions, perform the action, observe its own exact message, and clean up the resources it owns**. It must never depend on method execution order, an uncontrolled shared mailbox, or fixed sleep durations.

This guide explains types of order dependencies, boundaries requiring isolation, JUnit 5 and Spring Boot examples, GreenMail/Mailpit test SMTP servers, correlation IDs, handling `@Async` and outboxes, Spring Test context caching, parallel tests, and how to build tests that run reliably in CI.

## 1. Goals of an Email Integration Test

Depending on scope, an integration test can verify:

- The application service translated a business event into the right email request.
- Spring configured `JavaMailSender` and related beans properly.
- `MimeMessageHelper` built the Unicode subject, recipients, and MIME parts accurately.
- The test SMTP server actually received the email.
- Workers processed the committed outbox and updated state.
- Connection errors, timeouts, or retries surface properly at the application layer.

Common flow:

~~~mermaid
flowchart LR
    A["JUnit test"] --> B["Application service"]
    B --> C["Mail gateway / worker"]
    C --> D["JavaMailSender"]
    D --> E["SMTP test server"]
    E --> F["Captured messages"]
    F --> G["Assert the test's message"]
~~~

Tests can verify the email was **accepted** by the test SMTP server. They do not prove the message reached a customer's Internet mailbox or was read; delivery is a separate contract.

Template-selection tests do not need SMTP; MIME unit tests can use a real in-memory `MimeMessage` and a fake sender. Only bring in a test SMTP server when genuinely testing the transport boundary or side-effecting integration flows.

## 2. What Does Order-Dependent Testing Mean?

A test is **order-dependent** if its outcome changes depending on whether other tests run before or after it.

Wrong example:

~~~java
@Test
void createOrderAndSendEmail() {
    orderService.createAndNotify();
}

@Test
void readMailAndVerify() {
    MimeMessage last =
            sharedInbox.getReceivedMessages()[0];

    assertEquals(
            "Order has been created",
            last.getSubject()
    );
}
~~~

The second test assumes the first test already ran and finished sending. It also assumes no other test sent or deleted messages, no retries ran, and index 0 always holds the expected email.

If you run the second test alone in your IDE, it fails because no email exists. If run in parallel, another test can inject a message into the same mailbox before the assertion runs.

**Better approach:** each test encapsulates one complete behavior:

~~~java
@Test
void sendsOrderConfirmation() {
    Order order = fixtures.createConfirmedOrder();

    orderMailService.requestConfirmation(
            order.getId()
    );

    MimeMessage actual =
            inbox.findConfirmationFor(order.getId());

    assertEquals(
            expectedSubject(order),
            actual.getSubject()
    );
}
~~~

The `fixtures` and `inbox` helpers here are illustrative abstractions that must be implemented so data and messages belong strictly to the current test.

## 3. Why @TestMethodOrder Is Not the Solution

JUnit 5 supports `@TestMethodOrder` and `@Order`:

~~~java
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class FragileMailIT {

    @Test
    @Order(1)
    void send() {
        // Create email.
    }

    @Test
    @Order(2)
    void verify() {
        // Read email created by previous test.
    }
}
~~~

Even with explicit ordering, tests remain brittle when:

- One method is executed individually.
- The first method is disabled or throws an exception.
- Other classes share the same mailbox.
- Another CI job runs on a separate JVM.
- An SMTP worker has not finished processing when the second test starts.
- Cleanup or schedulers mutate state.

`@TestMethodOrder` can fit special cases where ordering itself is under test, yet **should never be used to paper over tests sharing implicit state**.

When testing a multi-step workflow, place all steps inside **one test scenario** with explicit setup and assertions rather than splitting them into interdependent test methods.

## 4. How Shared Mailboxes Break Tests

Suppose the whole suite sends to:

~~~text
integration-test@example.test
~~~

And shares one SMTP catcher:

~~~text
Test A: sends "Order confirmed A"
Test B: sends "Password reset B"
Test C: asserts inbox has exactly 1 message
Test D: deletes the entire inbox
~~~

Test C's outcome depends on execution schedule. Test D can delete messages A and B are waiting for.

| Symptom | Common Cause |
| --- | --- |
| Passes alone yet fails in full suite | Leftover messages from earlier tests |
| Message count varies randomly | Tests sending concurrently |
| Email missing despite SMTP log showing accepted | Another test wiped the inbox |
| Wrong subject | Test read another test's email |
| Fails in CI, passes locally | Multiple runners sharing one server/mailbox |
| Reset-token test occasionally grabs stale token | Reading last message or fixed index |
| Passes after rerunning a few times | Race conditions, residual state, or timing |

Adding `Thread.sleep` only shifts observation timing; it never solves mailbox ownership.

## 5. Levels of Isolation to Consider

| Boundary | State to Isolate | How to Handle |
| --- | --- | --- |
| Test method | Input ID, recipient, correlation | Unique ID per test |
| SMTP server | Captured messages, listener, port | Server per test / per class |
| Mailbox | Stored messages, read state | Dedicated mailbox, namespace, or filter |
| Database/outbox | Entities, jobs, idempotency keys | Dedicated fixtures, dedicated DB/schema |
| Spring context | Beans, mail host/port, schedulers | Consistent lifecycles and dynamic properties |
| JVM/CI runner | Ports, containers, test accounts | Ephemeral resources or per-run namespaces |

A correlation ID only helps **identify** messages; it does not prevent another test from wiping the inbox. A dedicated SMTP server isolates emails, yet does not automatically make a shared database order ID safe.

Think of isolation as the combination of **resource ownership**, **isolated data**, and **accurate observation conditions**.

## 6. Arrange -> Act -> Assert -> Cleanup Principle

An independent integration test should have clear phases:

**Arrange**

1. Create isolated business resources.
2. Generate a unique `testRunId` / `correlationId`.
3. Select the test's own SMTP server or namespace.
4. Ensure the Spring mail sender points to the right host/port.
5. Control background workers and committed data.

**Act**

Invoke the exact application use case or worker under test.

**Assert**

Wait for the message carrying the matching correlation ID, then assert subject, recipients, MIME parts, attachments, or outbox status as appropriate.

**Cleanup**

Release servers, containers, test data, and resources **owned by this test**. Never delete messages belonging to another test or runner.

A well-designed test can run solo, repeatedly, and before or after any other test with identical semantics.

## 7. Dedicated Test SMTP Server per Method

Strong isolation comes from starting a server in `@BeforeEach` and stopping it in `@AfterEach`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;

class MailTransportIsolationIT {

    private GreenMail greenMail;

    @BeforeEach
    void startSmtp() {
        greenMail = new GreenMail(
                new ServerSetup(
                        0,
                        "127.0.0.1",
                        ServerSetup.PROTOCOL_SMTP
                )
        );

        greenMail.start();
    }

    @AfterEach
    void stopSmtp() {
        if (greenMail != null) {
            greenMail.stop();
        }
    }

    @Test
    void sendsMail() {
        // Create JavaMailSender pointing to this GreenMail
        // instance's port, send, and assert.
    }
}
~~~

In this example, port `0` requests a dynamic port. Use a GreenMail version supporting that setup and read the actual bound port after starting. If your environment does not support it, use a test SMTP container with dynamic port mapping.

**Pros:** Test methods cannot read stale mail from another server. No global inbox cleanup is required.

**Trade-offs:** Every test starts an SMTP listener, slowing large suites. You can use a per-class server while keeping per-test correlation and proper lifecycles.

## 8. Integration Test Example with GreenMail and JavaMailSenderImpl

This template creates a dedicated SMTP server per test, uses a real `JavaMailSenderImpl` over loopback, and filters emails using a correlation header.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;
import java.util.Properties;
import java.util.UUID;

import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;

class SpringSmtpIntegrationTest {

    private GreenMail smtp;
    private JavaMailSenderImpl sender;

    @BeforeEach
    void setUp() {
        smtp = new GreenMail(
                new ServerSetup(
                        0, "127.0.0.1",
                        ServerSetup.PROTOCOL_SMTP
                )
        );

        smtp.start();

        sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(smtp.getSmtp().getPort());
        sender.setDefaultEncoding("UTF-8");

        Properties properties =
                sender.getJavaMailProperties();

        properties.put("mail.smtp.auth", "false");
        properties.put(
                "mail.smtp.connectiontimeout", "3000"
        );
        properties.put(
                "mail.smtp.timeout", "3000"
        );
        properties.put(
                "mail.smtp.writetimeout", "3000"
        );
    }

    @AfterEach
    void tearDown() {
        if (smtp != null) {
            smtp.stop();
        }
    }

    @Test
    void sendsMailForOwnCorrelationId()
            throws Exception {

        String id = UUID.randomUUID().toString();
        String recipient = "it-" + id + "@example.test";

        MimeMessage outgoing =
                sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        outgoing, false, "UTF-8"
                );

        helper.setFrom("orders@example.test");
        helper.setTo(recipient);
        helper.setSubject("Order confirmation " + id);
        helper.setText("Order for " + id);

        outgoing.setHeader(
                "X-Test-Correlation-Id", id
        );

        sender.send(outgoing);

        assertTrue(
                smtp.waitForIncomingEmail(5000, 1)
        );

        MimeMessage[] matches =
                Arrays.stream(smtp.getReceivedMessages())
                        .filter(message -> {
                            try {
                                return id.equals(
                                        message.getHeader(
                                            "X-Test-Correlation-Id",
                                            null
                                        )
                                );
                            } catch (MessagingException ex) {
                                throw new IllegalStateException(ex);
                            }
                        })
                        .toArray(MimeMessage[]::new);

        assertEquals(1, matches.length);

        MimeMessage actual = matches[0];

        assertEquals(
                "Order confirmation " + id,
                actual.getSubject()
        );

        InternetAddress to = (InternetAddress)
                actual.getRecipients(
                        Message.RecipientType.TO
                )[0];

        assertEquals(recipient, to.getAddress());
    }
}
~~~

This is an integration example using common GreenMail/Jakarta Mail APIs; align dependencies and dynamic port setup with your project's actual versions.

Key takeaways:

- SMTP server and captured inbox belong strictly to the test method.
- Recipient and correlation ID are freshly generated per run.
- No production credentials or real customer addresses.
- The test does not pick messages by fixed index.
- `waitForIncomingEmail` awaits SMTP capture; filtering by ID confirms **this test's exact message**.
- The test does not care whether other tests ran beforehand.

### Illustrative Test Dependency

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'com.icegreen:greenmail:<pinned-version>'
}
~~~

`<pinned-version>` is a placeholder to replace with a real, project-pinned version compatible with your Jakarta Mail/Spring Boot stack. Do not treat placeholders as ready-to-download coordinates.

## 9. Server per Class: Trading Off Speed and Isolation

If starting a server per method is too slow, start one server in `@BeforeAll` and stop it in `@AfterAll`. All methods in the class then share one captured inbox, while separate classes get separate servers.

~~~text
OrderMailIT:
  SMTP server A
  test #1 correlation X
  test #2 correlation Y

SecurityMailIT:
  SMTP server B
  test #1 correlation Z
~~~

Maintain these rules:

- Each method uses its own recipient/correlation.
- Never wipe the whole inbox while other methods might be sending.
- Never assert the entire inbox holds exactly one message.
- Never pick the "newest" message.
- Never stop the server while async tasks in the class are still sending.

| Server Lifecycle | Strengths | Risks |
| --- | --- | --- |
| Per method | Strong message isolation | Frequent startups |
| Per class | Fewer startups | Methods share captured inbox |
| Per suite/JVM | Resource-efficient | Multiple classes need namespaces and cleanup |
| External shared service | Easy to share | Risk across JVMs and CI pipelines |

No single scope fits every suite. When optimizing for speed, preserve test-scoped correlation and ownership rules.

## 10. Correlation IDs Matter More Than "Last Email"

A test can generate:

~~~java
String testRunId =
        UUID.randomUUID().toString();

String recipient =
        "it+" + testRunId + "@example.test";
~~~

Fields usable for filtering:

- Unique recipient.
- Header `X-Correlation-Id` or `X-Test-Correlation-Id`.
- Business event ID / outbox job ID.
- Event-linked template/purpose.
- Distinctive subject marker.
- Provider message reference when supported by contract.

Example:

~~~text
testRunId: run-72bc
orderId: ORD-IT-72bc
recipient: it+run-72bc@example.test
X-Correlation-Id: run-72bc
~~~

Tests must **filter before counting and asserting**:

~~~java
List<MimeMessage> own =
        inbox.findByCorrelationId(testRunId);

assertEquals(1, own.size());
~~~

Avoid:

~~~java
MimeMessage last =
        inbox.allMessages().getLast();
~~~

When multiple workers send concurrently, capture order does not necessarily match domain event order.

### Message-ID Does Not Fully Replace Correlation IDs

The `Message-ID` header may be generated or rewritten by libraries/providers during sending. It helps tracing, yet if tests must look up by an application-controlled ID, pass an explicit correlation ID via command/job/header or metadata.

Some real providers strip custom headers, so provider integration tests must rely on fields/mechanisms guaranteed by that provider.

## 11. Never Wipe an Entire Shared Mailbox

An anti-pattern:

~~~java
@BeforeEach
void clearInbox() {
    sharedSmtpServer.deleteAllMessages();
}
~~~

When running in parallel:

~~~text
Test A: sends message with ID A
Test B: @BeforeEach wipes entire inbox
Test A: cannot find message ID A
~~~

This is a **race condition that destroys another test's evidence**.

Safer options, in priority order:

1. Test owns a dedicated SMTP server and may reset its own server.
2. Test uses a dedicated mailbox/namespace and cleans only within that scope.
3. Test uses correlation IDs and deletes only its own messages if the API allows.
4. If a shared inbox is unavoidable, synchronize across all actors sharing it; better yet, eliminate sharing.

Never delete "all emails from the last 5 minutes" because another CI run may be using the mailbox simultaneously.

### Cleanup Is the Owner's Responsibility

`@AfterEach` or `try-finally` should clean up servers, containers, and fixtures created by that test itself:

~~~java
@AfterEach
void cleanup() {
    if (smtp != null) {
        smtp.stop();
    }
}
~~~

If async workers are still running, ensure related tasks finish or are cancelled per policy before closing the server. Premature cleanup can cause connection refused errors for in-flight sends.

## 12. Shared Static Inboxes Are Not Test Isolation

Example:

~~~java
public final class TestMailStore {
    static final List<MimeMessage> MESSAGES =
            new ArrayList<>();
}
~~~

Tests sharing a list can suffer from:

- State from earlier tests.
- Data races when multiple threads add/remove.
- One test deleting another test's data.
- Order-dependent counts.
- Tests passing falsely on stale emails.

Switching to `CopyOnWriteArrayList` or `ConcurrentLinkedQueue` only partially solves **thread safety**. It does not solve "whose message is this?". Give each test its own capturing store or filter by owner ID.

## 13. Spring Boot Context Caching and Dynamic SMTP Ports

`@SpringBootTest` can reuse a Spring `ApplicationContext` across tests with matching configurations. This optimizes speed yet fails when a sender bean still holds the SMTP port of a stopped server.

Example:

~~~text
Class A:
  SMTP server A runs on port 31021
  Spring context creates JavaMailSender(port 31021)
  Class A finishes and stops SMTP A

Class B:
  Server B runs on port 31055
  Spring reuses old context
  JavaMailSender still uses port 31021
  Connection refused
~~~

Keep **server lifecycles aligned with Spring context lifecycles**:

- Supply runtime host/port via `@DynamicPropertySource` during context creation.
- Never stop a test server before the last context using it finishes.
- Watch out for static servers shared across subclasses.
- Consider `@DirtiesContext` when differing dynamic endpoints or singleton states prevent safe context reuse.
- When an SMTP server per method is needed, do not share a singleton sender created with a previous method's port.

Never solve this by pinning one fixed SMTP port for all tests, as that causes collisions in parallel/CI runs.

## 14. Testcontainers and @DynamicPropertySource

With a containerized SMTP catcher, dynamic port mapping avoids collisions across CI runs on the same host.

Structural example using Mailpit:

~~~java
@Testcontainers
@SpringBootTest
class MailFlowIT {

    @Container
    static GenericContainer<?> mailpit =
            new GenericContainer<>(
                    DockerImageName.parse(
                            "axllent/mailpit:<pinned-version>"
                    )
            ).withExposedPorts(1025, 8025);

    @DynamicPropertySource
    static void configureSmtp(
            DynamicPropertyRegistry registry) {

        registry.add(
                "spring.mail.host",
                mailpit::getHost
        );

        registry.add(
                "spring.mail.port",
                () -> mailpit.getMappedPort(1025)
        );

        registry.add(
                "spring.mail.properties.mail.smtp.auth",
                () -> "false"
        );
    }

    @Autowired
    OrderMailService service;

    @Test
    void sendsOrderConfirmation() {
        // Create unique order/correlation ID.
        // Trigger service.
        // Use test HTTP client to query Mailpit API
        // at mapped port 8025, filtering by exact ID.
    }
}
~~~

`<pinned-version>` is a placeholder to replace with a project-managed real image version. Align container startup order and Spring context initialization with your Testcontainers/Spring Boot versions, and target the Mailpit API schema matching your pinned version.

This pattern emphasizes:

1. The SMTP service belongs to the test.
2. Ports are dynamically mapped.
3. The Spring sender receives the exact port.
4. Messages are located by correlation ID.
5. Zero dependency on any production mailbox.

### When Should @DirtiesContext Be Used?

If a test invalidates the context, `@DirtiesContext` forces Spring to build a fresh context. However, this annotation:

- Does not clear mailboxes outside the JVM.
- Does not roll back database commits made outside the test transaction.
- Does not stop other CI runners from sending.
- Can slow the suite down due to context rebuilds.

Use it strictly for context boundaries, not as a substitute for proper mail isolation design.

## 15. What Purpose Does Each SMTP Test Tool Serve?

| Tool | Common Usage |
| --- | --- |
| GreenMail | In-JVM embedded SMTP/IMAP/POP3 test server with Java API for reading messages |
| Mailpit | SMTP catcher with web UI/HTTP API, typically containerized |
| MailHog | SMTP catcher and API, fits systems already using it |
| Wiser / lightweight SMTP | Captures messages inside the test JVM |
| Fake `MailGateway` | Tests application layer without opening SMTP |
| Mock `JavaMailSender` | Tests gateway/MIME without network sends |
| Provider sandbox | Tests provider-specific behavior per contract |

Template/recipient mapping unit tests need no SMTP. MIME tests can use real `MimeMessage` + mocked sender. SMTP protocol tests need a server, while real AUTH/TLS tests with a vendor need a dedicated sandbox.

Avoid using a real provider for simple assertions because it slows tests, introduces flakiness, and consumes quota.

## 16. Asynchronous Sending: Wait on Conditions Instead of Thread.sleep

With `@Async`, outboxes, schedulers, or message consumers, emails may be sent **after** the application method returns.

Flaky approach:

~~~java
mailService.requestConfirmation(orderId);

Thread.sleep(1000);

assertEquals(
        1,
        sharedInbox.getReceivedMessages().length
);
~~~

One second may be wasted on fast machines yet insufficient under high CI load. A global inbox might also contain unrelated messages.

Use conditional waiting, such as Awaitility:

~~~java
String correlationId =
        UUID.randomUUID().toString();

mailService.requestConfirmation(
        orderId,
        correlationId
);

await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {

        List<CapturedMail> own =
                testInbox.findByCorrelationId(
                        correlationId
                );

        assertEquals(1, own.size());

        assertEquals(
                expectedSubject,
                own.get(0).subject()
        );
    });
~~~

`testInbox.findByCorrelationId` is a project-defined test helper/adapter; `await()` illustrates Awaitility's API.

Advantages:

- No fixed sleep duration.
- Exits as soon as the condition holds.
- Timeout surfaces a clear failure.
- Observes only this test's message.

### Conditional Waiting Differs from "Wait as Long as Possible"

If a worker cannot send because the job is in `RETRY` or rejected by recipient policy, the test should fail with clear diagnostics rather than sleeping for minutes. When testing "never sends", rely on a trustworthy terminal state rather than merely seeing an empty inbox immediately.

## 17. Correlation IDs Across Request -> Outbox -> MIME

An ID can originate in the test and flow through the pipeline:

~~~mermaid
flowchart LR
    A["Test creates correlation ID"] --> B["Command"]
    B --> C["Outbox job"]
    C --> D["Worker"]
    D --> E["MIME X-Correlation-Id"]
    E --> F["SMTP capture"]
    F --> G["Test finds exact message"]
~~~

Illustrative command:

~~~java
public record RequestConfirmationMail(
        UUID orderId,
        String correlationId) {
}
~~~

In the gateway, after building the message:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message, true, "UTF-8"
        );

// Set To, From, Subject, plain text, and HTML.

message.setHeader(
        "X-Correlation-Id",
        correlationId
);

mailSender.send(message);
~~~

Tests can inspect this header if the SMTP capture server preserves it. In production, the correlation ID can be an application-generated `requestId` or `outboxJobId` rather than something controlled by HTTP clients. Never stuff tokens, secret addresses, or PII into headers just for debugging.

**Correlation is not authorization:** recipients must still be validated per application policy.

## 18. Never Use "Last Message" or Captured Array Ordering

Wrong approach:

~~~java
MimeMessage latest =
        mailbox.getAll().get(
                mailbox.getAll().size() - 1
        );
~~~

This assumption breaks when:

- Other tests send emails simultaneously.
- Schedulers emit background notifications.
- Retries generate extra messages.
- The SMTP capture API does not guarantee ordering.
- Workers process jobs concurrently.

Prefer:

~~~java
List<CapturedMail> own =
        mailbox.findByCorrelationId(
                correlationId
        );

assertEquals(1, own.size());

CapturedMail actual = own.get(0);
~~~

If a use case legitimately sends **two emails to two recipients**, assert a **set of messages** matching recipients and purposes rather than asserting index 0 must be the customer and index 1 must be the manager. Async tasks can finish in either order and still be correct.

## 19. Database Fixtures Must Also Be Order-Independent

Mail workflows often read order/customer/tenant data from a database. If Test A creates a record and Test B consumes it, order dependency enters before SMTP even runs.

Wrong example:

~~~java
static UUID orderId;

@Test
void createOrder() {
    orderId = orderRepository.save(...).getId();
}

@Test
void sendMail() {
    mailService.send(orderId);
}
~~~

Safe approach:

~~~java
@Test
void sendsMailForOwnOrder() {
    Order order = orderFixtures.createConfirmedOrder(
            "it-" + UUID.randomUUID()
    );

    mailService.send(order.getId());

    // Find the exact message for this test's order.
}
~~~

With `@Sql` or seed data, use non-colliding keys/namespaces; avoid fixed IDs mutated by multiple tests. Cleanup should remove only records owned by that test.

### @Transactional on Tests and Worker Threads

A subtle bug: a test method annotated `@Transactional` creates an uncommitted order and triggers an `@Async` worker on another thread. The worker cannot see the order because the test thread's transaction has not committed.

Do not fix this with a longer sleep. Instead:

- Commit the fixture before triggering the worker.
- Use `TestTransaction` to control boundaries when appropriate.
- Do not wrap the whole test in a rolling-back transaction when the workflow requires workers to observe committed data.
- Use an isolated database/schema for post-test cleanup.
- For outboxes, ensure workers read only committed jobs.

This is a transaction-visibility issue, not a mailbox bug.

## 20. Outbox Tests Must Identify the Exact Job

When a worker polls `mail_outbox`, never pick an arbitrary record:

~~~java
MailOutbox job = repository.findFirstPending();
worker.process(job);

assertEquals(1, inbox.allMessages().size());
~~~

When another test creates jobs, `findFirstPending` can return a job belonging to another test.

A good test has:

- A unique `outboxJobId`.
- A unique `idempotencyKey` per new send intent.
- A unique recipient/correlation ID.
- DB fixtures committed before the worker reads.
- `SENT` or `RETRY` status queried by job ID.
- SMTP messages filtered by correlation ID.

Conceptual example:

~~~java
UUID jobId = fixtures.insertPendingMail(
        "it-" + UUID.randomUUID(),
        recipient
);

worker.processJob(jobId);

await().atMost(Duration.ofSeconds(10))
    .untilAsserted(() -> {

        assertEquals(
                MailStatus.SENT,
                repository.getStatus(jobId)
        );

        assertEquals(
                1,
                inbox.findByJobId(jobId).size()
        );
    });
~~~

`processJob`, `getStatus`, and `findByJobId` are illustrative helpers/test seams. If the production worker has no API to process one specific job, run the real scheduler against an isolated DB rather than altering production semantics purely for test convenience.

## 21. Idempotency and Retries Do Not Mean "Always One SMTP Message"

An outbox record with a unique key may still be re-read by a worker after a crash. Scenario:

~~~text
Worker A claims job
SMTP relay accepts mail
Worker A crashes before UPDATE SENT
Worker B reclaims after lease
SMTP may receive another message
~~~

Unique constraints prevent **creating multiple logical jobs**, yet cannot guarantee SMTP receives only one message across a crash window. Tests must reflect the real contract.

When testing duplicate enqueues:

~~~java
String key = "it-" + UUID.randomUUID();

service.requestMail(key);
service.requestMail(key);

assertEquals(
        1,
        outboxRepository.countByKey(key)
);
~~~

This is the right assertion for idempotent **enqueueing**. Testing "do not re-send an already `SENT` job" is separate. Crash tests after SMTP acceptance must acknowledge side effects may repeat unless the provider offers a defined deduplication mechanism.

Never delete duplicate messages before asserting just to make tests pass.

## 22. Negative Tests: Verifying "No Email Sent" Also Needs Clear Boundaries

Example:

~~~java
service.rejectUnauthorizedRequest(...);

assertEquals(
        0,
        sharedInbox.getReceivedMessages().length
);
~~~

This assertion can fail because the inbox holds another test's email, or pass falsely because another test just wiped the inbox. With async flows, seeing an empty inbox immediately does not prove nothing will send later.

Better choices:

1. Test application policy with a dedicated fake `MailGateway`, asserting zero `send` calls.
2. Integration-test using an isolated SMTP server and wait for the workflow to reach a terminal state.
3. Or verify zero messages carry the rejected request's correlation ID over a bounded observation window, paired with job/policy state.

A negative test must never rely on "the suite-wide mailbox is completely empty".

## 23. Parallel Tests and JUnit 5

When JUnit parallel execution is enabled, inspect every piece of shared mutable state:

- Static mutable collections.
- Shared SMTP servers with inbox resets.
- Shared database rows.
- Spring singletons mutable by tests.
- Background schedulers competing for jobs.
- Static fields used as correlation or order IDs.
- Overlapping test server lifecycles/ports.

### @Execution(SAME_THREAD)

You can temporarily force a class's methods to run sequentially:

~~~java
@Execution(ExecutionMode.SAME_THREAD)
class SharedMailboxIT {
    // Temporarily limits contention within JUnit scope.
}
~~~

This does not stop other classes or other JVMs from touching the mailbox concurrently. It is a mitigation, not a durable isolation solution.

### @ResourceLock

When multiple tests in the same JUnit engine must share a named resource:

~~~java
@ResourceLock(
        value = "smtp-shared-mailbox",
        mode = ResourceAccessMode.READ_WRITE
)
class SharedMailboxIT {
    // Tests sharing the same lock name are
    // coordinated by JUnit within the appropriate scope.
}
~~~

`@ResourceLock` **is not a distributed lock**. It does not synchronize across two JVM forks, two CI pipelines, or two machines.

Whenever possible, **per-test servers or namespaces** beat suite-wide locking.

## 24. TestInstance(PER_CLASS) and Mutable State

With:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class MailIT {

    private final List<String> subjects =
            new ArrayList<>();
}
~~~

methods on the same instance share the `subjects` list. Without resets, later tests see earlier data; under parallel execution, data races occur.

Never use `PER_CLASS` merely to share email result variables across tests. If you want a per-class server, keep the server reference at class scope while giving every test its own fixtures and correlation IDs.

Thread-safe collections alone do not solve data ownership.

## 25. Multi-Process and Multi-Job CI

A test suite can run safely inside one JVM yet collide in CI:

~~~text
CI job A: runner 1 -> qa-mailbox@example.test
CI job B: runner 2 -> qa-mailbox@example.test
CI job C: runner 3 -> qa-mailbox@example.test
~~~

All JUnit locks operate only inside the managed engine/process; external mailboxes remain shared.

Options:

- Dedicated Mailpit/GreenMail container per CI job.
- Dedicated SMTP test account per pipeline.
- Email namespaces keyed by build ID + test ID.
- Dynamic port mapping to prevent collisions.
- Dedicated schema/database per job.
- Cleanup scoped to run ownership.
- Never use production credentials.
- Never wipe an entire mailbox while another build is running.

If an external mailbox must be shared, partition ownership regions or use genuine cross-process coordination rather than adding `@Execution(SAME_THREAD)`.

## 26. Plus Addressing Does Not Mean Independent Mailboxes

A provider may allow addresses like:

~~~text
qa+run-a@example.test
qa+run-b@example.test
~~~

Yet both addresses can land in **one physical mailbox**. Some providers disallow plus addressing or normalize local-parts differently.

Aliases help distinguish recipients on messages, yet you still need:

- Correlation IDs.
- Accurate querying/filtering.
- Deleting only messages belonging to the run.
- Preventing other tests from calling "delete all".
- Managing provider quotas.

Never assume email aliases provide the strict isolation of separate mailbox accounts.

## 27. Waiting for the Right Message and Avoiding Busy Polling

A test adapter can expose:

~~~java
public interface TestInbox {

    List<CapturedMail> findByCorrelationId(
            String correlationId);

    List<CapturedMail> findByRecipient(
            String recipient);
}
~~~

Test usage:

~~~java
String id = UUID.randomUUID().toString();

service.sendWithCorrelationId(id);

await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {

        List<CapturedMail> captured =
                testInbox.findByCorrelationId(id);

        assertEquals(1, captured.size());
        assertEquals(
                "ORDER_CONFIRMED",
                captured.get(0).purpose()
        );
    });
~~~

Never poll a DB/SMTP API every 1 ms without good reason; it adds load and alters timing. Pick deadlines and intervals suited to CI while still failing early on permanent errors via terminal statuses/reason codes when available.

### Timeout/Retry Tests Should Control Time

If a workflow retries after 5 minutes, do not make tests sleep 5 real minutes. Inject `Clock`, run a scheduler seam, or set `nextAttemptAt` deliberately in fixtures. Controlling time keeps tests independent and deterministic.

## 28. Diagnostics When a Test Fails

When an email fails to appear before timeout, report details **belonging to the current test**:

~~~text
testCase: sendsInvoiceMail
correlationId: it-931a
expectedMatchingMessages: 1
actualMatchingMessages: 0
outboxStatus: RETRY
failureCategory: SMTP_TIMEOUT
~~~

Never dump the entire suite's inbox or all email tokens/passwords because:

- Data may belong to other tests.
- Output becomes noisy, hiding the real error.
- Security tokens could leak.
- Test cleanup wipes context if diagnostics were not captured first.

A per-method test server simplifies scoped diagnostics. Capture summary info before `@AfterEach` stops the server.

## 29. MIME and Unicode: Assert Only After Finding the Right Message

After locating the test's email by correlation ID:

~~~java
MimeMessage actual =
        inbox.findOneByCorrelationId(id);

assertEquals(
        "Hóa đơn tháng 11 – Đơn hàng ORD-2048",
        actual.getSubject()
);

InternetAddress recipient = (InternetAddress)
        actual.getRecipients(
                Message.RecipientType.TO
        )[0];

assertEquals(
        "buyer@example.test",
        recipient.getAddress()
);
~~~

For multipart MIME with HTML/plain text and attachments, multiple levels of `multipart/alternative` / `multipart/mixed` may exist. Never assume part 0 is always plain text and part 1 is always HTML.

Locate parts by MIME type and verify decoded content. Never assert raw MIME boundaries, random `Message-ID`s, or captured message order unless part of the tested contract.

## 30. Sending Multiple Emails in One Use Case

A workflow may email both a customer and a manager. Assert the result set rather than array positions:

~~~java
List<CapturedMail> own =
        inbox.findByRequestId(requestId);

assertEquals(2, own.size());

assertTrue(
        own.stream().anyMatch(mail ->
                mail.recipient().equals(customerEmail)
                && mail.purpose() == MailPurpose.CUSTOMER
        )
);

assertTrue(
        own.stream().anyMatch(mail ->
                mail.recipient().equals(managerEmail)
                && mail.purpose() == MailPurpose.MANAGER
        )
);
~~~

If delivery order is not designed as a business invariant, never assert the customer email must appear before the manager email. Two async tasks can finish in either order and still be valid.

## 31. Common Mistakes and Fixes

### 31.1. Test A Sends, Test B Verifies

**Mistake:** Test B depends on Test A.

**Fix:** each test creates and asserts its own message, or combine the scenario into one test.

### 31.2. Using @Order to Fix Flaky Tests

**Mistake:** order is forced while shared state lacks ownership.

**Fix:** isolate servers/fixtures; eliminate order dependencies.

### 31.3. Reading getReceivedMessages()[0]

**Mistake:** may return an old email or another test's email.

**Fix:** filter by correlation/recipient before asserting.

### 31.4. Asserting the Suite-Wide Inbox Holds Exactly One Email

**Mistake:** other tests may send concurrently.

**Fix:** count only messages owned by the test, or own the entire server.

### 31.5. Wiping All Emails in @BeforeEach

**Mistake:** deletes emails from tests running in parallel.

**Fix:** reset only a dedicated server or run scoped cleanup.

### 31.6. Using a Static Mutable List as an Inbox

**Mistake:** shared state and data races.

**Fix:** per-test capturing stores with clear ownership.

### 31.7. Fixed Thread.sleep with @Async

**Mistake:** environment-dependent timing.

**Fix:** Awaitility/latches/futures with proper completion conditions.

### 31.8. Spring Context Cache Holding a Sender Pointing to a Stopped Server

**Mistake:** context and SMTP lifecycles mismatch.

**Fix:** aligned dynamic properties and server lifecycles; `@DirtiesContext` when genuinely needed.

### 31.9. Using a Fixed SMTP Port

**Mistake:** parallel port collisions in CI.

**Fix:** ephemeral host ports and injecting runtime config into the sender.

### 31.10. @Transactional Test Uncommitted While Worker Reads

**Mistake:** another thread cannot see uncommitted data.

**Fix:** commit fixtures at the right time and clean up separately.

### 31.11. Negative Test Checking the Inbox Only Immediately

**Mistake:** email might still be sent later.

**Fix:** await terminal workflow state or use a fake gateway to assert policy.

### 31.12. Reusing the Same Idempotency Key Across Multiple Tests

**Mistake:** later tests get deduplicated by stale jobs.

**Fix:** generate a unique key per test send intent.

### 31.13. Retry Test Demanding Exactly-Once SMTP Across Crashes

**Mistake:** incompatible with database/SMTP boundaries.

**Fix:** verify real contracts for enqueueing, claiming, and uncertain outcomes.

### 31.14. Cleaning Up by Time Window

**Mistake:** may delete emails from another build.

**Fix:** clean up by test run/correlation.

### 31.15. Using Production SMTP Credentials

**Mistake:** risks sending real mail and consuming quota.

**Fix:** use fakes, GreenMail/Mailpit, or an isolated sandbox.

### 31.16. Treating @ResourceLock as a Distributed Lock

**Mistake:** lock does not cover other CI runners.

**Fix:** isolate accounts/servers or use external coordination.

## 32. Test Design Matrix

| Testing Question | How to Structure | Avoid |
| --- | --- | --- |
| Single synchronous email | Dedicated server, dedicated correlation | Reading newest message |
| Asynchronous email | Await by ID and deadline | Fixed sleep |
| Multiple emails in one request | Assert message set per request | Asserting array indices |
| Send-rejection policy | Fake gateway or isolated server | Counting whole inbox |
| Outbox worker | Unique job ID and fixtures | Claiming arbitrary `PENDING` job |
| Retries | Stable job ID, attempt ID when needed | Counting all global emails |
| Parallel methods | Namespace/server per method | Delete-all mailbox |
| Parallel classes | Server per class and filtering | Static mutable store |
| Multiple CI runners | Container/account per run | JUnit-only locks |
| Dynamic SMTP port | `@DynamicPropertySource`, aligned lifecycle | Bean holding stale port |
| Unicode subject | Decode MIME properly then assert text | Comparing full raw MIME file |
| Provider sandbox | Dedicated test account/recipients | Production recipients |

## 33. Reasoning Exercises

**Q1.** Test A sends an email, Test B asserts the subject. When run alone, B fails. Why?

Test B depends on Test A's state. An independent test must set up and verify its own behavior.

**Q2.** Two tests send to one mailbox and both read index 0. What is the risk?

They may read each other's emails or stale messages. Use correlation IDs and dedicated SMTP servers/namespaces.

**Q3.** Should we call `deleteAllMessages` on a shared server in `@BeforeEach`?

No. It can wipe emails another test just sent. Reset a whole server only when that test owns it exclusively.

**Q4.** Does `@TestMethodOrder` guarantee test independence across multi-fork CI runs?

No. It neither removes state dependencies nor coordinates across multiple runners.

**Q5.** Does `@ResourceLock("mailbox")` protect two separate CI machines?

No, it is not a distributed lock.

**Q6.** An async worker takes 3 seconds in CI; the test sleeps 1 second and fails. What should be fixed?

Await by message/correlation and deadline instead of a fixed sleep.

**Q7.** Spring's `JavaMailSender` points to a stopped test server's port. Where should you look?

Spring context caching, dynamic properties, and server lifecycles.

**Q8.** An email exists in the inbox yet its correlation ID does not match. Should the test pass?

No. That email may belong to another test.

**Q9.** A test inserts an outbox row inside `@Transactional` and the async worker cannot see it. Should we increase sleep?

No. Fix commit and transaction visibility.

**Q10.** A "no-send" test sees an empty inbox immediately. Does that prove the async branch will not send?

Not yet. Observe a terminal state or use a controlled gateway check.

**Q11.** Two emails from the same request arrive at SMTP in differing orders. Is that a bug?

Not unless ordering is a business invariant. Assert the matching set of messages.

**Q12.** Does a unique constraint on the outbox guarantee a single SMTP message if a crash happens after relay acceptance?

No. DB and SMTP share no atomic commit.

## 34. Mental Model

~~~mermaid
flowchart TD
    A["JUnit test"] --> B["Create isolated fixture + correlation ID"]
    B --> C["Test-owned SMTP server/namespace"]
    C --> D["Invoke application use case"]
    D --> E["SMTP capture / outbox worker"]
    E --> F["Poll by correlation ID"]
    F --> G{"Expected outcome found?"}
    G -->|"Not yet, not timed out"| F
    G -->|"Match"| H["Assert recipient, subject, MIME"]
    G -->|"Timeout"| I["Fail + diagnostic scoped"]
    H --> J["Clean up test's resources"]
    I --> J
~~~

Key principles:

1. **Each integration test prepares and verifies its own data**, never relying on prior tests.
2. **Never use `@Order` as a default workaround** for shared mail state.
3. **Prefer dedicated test SMTP servers** per method, per class, or per container where appropriate.
4. **When sharing a server is unavoidable, correlation IDs/recipient namespaces are mandatory**, and never delete another test's mail.
5. **Never assert whole-inbox counts or the newest element** when multiple tests can send.
6. **Async tests must wait on conditions**, never fixed durations.
7. **Spring contexts and SMTP servers must have matching lifecycles**, especially with dynamic ports.
8. **Database/outbox fixtures must also be isolated**, and workers must read only committed data.
9. **JUnit resource locks protect only the managed scope**, not multiple CI processes.
10. **Negative tests need trustworthy terminal states**, since an immediately empty inbox does not prove nothing will send.
11. **Test retries/idempotency against the real contract**, never demanding exactly-once SMTP where no mechanism supports it.
12. **Use sandboxes/fake servers**, avoiding real customer emails in automated tests.
13. **Scope cleanup and diagnostics by ownership/correlation**, without dumping or wiping the whole mailbox.

In Spring Framework Mail, `JavaMailSender` only handles sending to the configured transport. **The integration test is responsible for knowing which mailbox it owns, which messages belong to it, and when sufficient evidence exists to assert.** When resources are isolated and tests do not rely on execution order, the same suite runs reliably solo, as a full suite, or in parallel in CI without interference from unrelated emails or leftover state.
