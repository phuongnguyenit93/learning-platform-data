# Verifying Connection and Send/Receive Permissions with a Minimal Experiment

> **Topic:** Connection Setup – Spring Framework JMS. This lesson builds a standalone probe to confirm JMS connectivity, `send` permission, and `consume` permission on **a designated test queue**. The output consists of observable signals that distinguish network, authentication, authorization, routing, and timeout errors.

## 1. The Question That Needs Proof

Does a Spring Boot application starting up cleanly and creating a `ConnectionFactory` bean mean it can send and receive messages? **Not yet.** Each layer must be verified independently:

| Layer | Check action | Valid conclusion | What remains unproven |
| --- | --- | --- | --- |
| Network | TCP connect to broker host/port | Target port is reachable at test time | JMS protocol, TLS, user, permissions |
| JMS connection | `createConnection()`, `createSession()`, and `start()` | Client completed JMS setup with current config | `send` and `consume` permissions |
| Send | `MessageProducer.send(...)` throws no error | Send operation accepted by provider per contract | Whether a consumer can read it or business logic succeeds |
| Receive | `MessageConsumer.receive(timeout)` returns matching `TextMessage` | Current user received the message with test ID from the target queue | Database commit, exactly-once processing |
| Both permissions | One `send → receive` with matching ID | Test account can use both directions on this queue | Whether other users or environments have the same rights |

The end goal is **reproducible evidence** with identity, broker, queue, test ID, and per-stage outcomes. Never use a single successful probe to claim the system will stay healthy or that all permissions are configured correctly.

### Expected Signals

- `CONNECT_OK`: JMS setup completed.
- `SEND_OK`: sending the test message finished without error.
- `RECEIVE_OK`: received the **expected** message and body.
- `ROUNDTRIP_OK`: the same account both sent and received successfully.
- `RECEIVE_TIMEOUT`: no matching message received within 5 seconds; **does not automatically mean missing permission**.
- `JMS_FAIL phase=...`: a JMS error occurred in the recorded phase, printed with exception class and error code for correlation with broker logs.

## 2. Preparing the Test Environment

Uses **Java 17+, Spring Boot 3.3.x, Jakarta Messaging 3.1, and ActiveMQ Artemis**. Spring Boot auto-configures `ConnectionFactory` from `spring.artemis.*` properties; the probe uses raw JMS API calls on top of that factory so each failing step is clearly exposed.

### 2.1. Quick Local Broker Startup

If Docker is installed, you can use the Artemis image from the official docs:

~~~bash
docker run --detach --name jms-probe-broker --rm -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

This is a one-line command that works in both Bash and PowerShell. Wait until the broker is ready before running the client:

~~~bash
docker logs jms-probe-broker
~~~

- `61616`: messaging port for applications.
- `8161`: management console at `http://localhost:8161`.
- The demo image uses default admin credentials `artemis/artemis`. **Use only in an isolated local environment**; never keep default credentials on shared infrastructure.
- Afterward, run `docker stop jms-probe-broker` to stop the test container. Because `--rm` is set with no data volume mounted, the container is removed on stop.

If your organization already provides a test broker, no Docker is needed. Record its hostname, port, TLS settings, environment, and the granted user's roles; avoid accidentally targeting a production broker.

### 2.2. Dedicated Test Queue

Pick queue `demo.probe` using point-to-point/**anycast** routing. Under some Artemis configs, addresses/queues auto-create when clients send. To **test permissions accurately**, ask an administrator to **pre-create** the address and queue:

~~~text
Artemis broker
  address: demo.probe
  routing: ANYCAST
  queue:   demo.probe
~~~

This policy separates missing `send`/`consume` permissions from missing `createAddress` or `createDurableQueue` permissions. `session.createQueue("demo.probe")` in code creates a client-side JMS `Queue` object; it is not conclusive proof that the physical resource exists and is accessible on the broker.

**Operate only on the test queue.** Running `receive()` on a real queue can acknowledge and consume business messages. A test queue should have clear access controls, capacity limits, and cleanup policies.

### 2.3. Identities and Broker Permissions

In Artemis, key permissions are `send` on the address and `consume` on the queue, plus permissions to create/delete addresses/queues. Exact role configurations, wildcards, and policies vary by broker.

| Illustrative identity | Expected rights on `demo.probe` | How to verify |
| --- | --- | --- |
| `probe-both` | `send`, `consume` | `roundtrip` must PASS |
| `probe-writer` | `send` only | `send` PASS; `receive` must be denied per policy |
| `probe-reader` | `consume` only | `receive` PASS when a message exists; `send` must be denied |
| `probe-none` | No destination rights | Can connect if auth is valid; send/receive must be denied |
| Invalid username/password | Unauthenticated | Connection/session setup must fail |

These accounts are **examples of roles an admin must provision beforehand**, not built-in users in the Docker image. Testing successfully with an admin account only proves the admin can send/receive—**not** the permissions of the two real application accounts.

## 3. Experiment Design

The program supports four modes:

~~~text
connect:
  ConnectionFactory -> Connection -> Session -> start()
  -> CONNECT_OK

send (with probeId):
  Connection -> Session -> MessageProducer
  -> TextMessage with property probeId
  -> demo.probe -> SEND_OK

receive (using the same probeId):
  Connection -> Session -> MessageConsumer
  -> selector: probeId = '...'
  -> receive(5000 ms)
  -> RECEIVE_OK or RECEIVE_TIMEOUT/JMS_FAIL

roundtrip:
  connect -> send -> receive matching probeId + body -> ROUNDTRIP_OK
~~~

**Why use `probeId` and a JMS selector?** The test queue might hold leftover messages from earlier checks. Each run generates a unique ID, attaches it as a string property, and filters via `probeId = 'id'`. Only when a message has the exact ID and body does the program print `RECEIVE_OK`. This reduces accidental cross-reads, though you should still use a **dedicated queue** and avoid sharing it casually across jobs.

**Why a 5-second timeout?** The experiment must finish in bounded time. Calling `receive()` without a timeout on an empty queue blocks forever. Five seconds works well for local illustration; WAN links or heavily loaded brokers may need a different value.

**Why separate the modes?** To test `send` and `consume` with **two different users**, send with the writer user and then run receive with the reader user using the same ID. A single-user round-trip cannot substitute for testing another user's permissions.

## 4. Creating the Java 17 + Spring Boot Project

Standalone project structure:

~~~text
jms-permission-probe/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/JmsProbeApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-permission-probe'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "artemis"
    password: "artemis"
  jms:
    cache:
      enabled: false
~~~

The credentials here are **the Docker image's default demo credentials**, not production secrets. When testing restricted accounts, set `SPRING_ARTEMIS_USER` and `SPRING_ARTEMIS_PASSWORD` environment variables to override them (Spring Boot supports externalized configuration). To test a broker on another host, override `SPRING_ARTEMIS_BROKER_URL`. Never commit shared environment passwords into source code/YAML. Setting `mode: native` avoids accidentally starting an embedded broker; disabling `spring.jms.cache` isolates raw connection checks in this demo and is not a production performance setting.

### 4.1. Complete Java File

`src/main/java/demo/JmsProbeApplication.java`:

~~~java
package demo;

import java.util.List;
import java.util.UUID;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmsProbeApplication implements ApplicationRunner {

    private static final String QUEUE_NAME = "demo.probe";
    private static final long RECEIVE_TIMEOUT_MS = 5_000L;
    private static final long TTL_MS = 300_000L;

    private final ConnectionFactory connectionFactory;

    public JmsProbeApplication(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public static void main(String[] args) {
        SpringApplication.run(JmsProbeApplication.class, args);
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        String mode = option(args, "probe.mode", "roundtrip");
        if (!List.of("connect", "send", "receive", "roundtrip")
                .contains(mode)) {
            throw new IllegalArgumentException(
                    "Unsupported probe.mode: " + mode);
        }

        if ("receive".equals(mode)
                && !hasValue(args, "probe.id")) {
            throw new IllegalArgumentException(
                    "receive mode requires --probe.id=<id>");
        }

        String probeId = option(
                args, "probe.id", UUID.randomUUID().toString());
        if (!probeId.matches("[A-Za-z0-9._-]{1,80}")) {
            throw new IllegalArgumentException(
                    "probe.id must contain 1..80 safe characters");
        }

        System.out.println("MODE=" + mode);
        System.out.println("PROBE_ID=" + probeId);

        String phase = "CONNECT";

        try (Connection connection =
                     connectionFactory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

            // Classic JMS: start lets the broker deliver messages to consumers.
            connection.start();
            System.out.println("CONNECT_OK");

            if ("connect".equals(mode)) {
                return;
            }

            Queue queue = session.createQueue(QUEUE_NAME);

            if ("send".equals(mode) || "roundtrip".equals(mode)) {
                phase = "SEND";
                try (MessageProducer sender =
                             session.createProducer(queue)) {
                    TextMessage message = session.createTextMessage(
                            "probe:" + probeId);
                    message.setStringProperty("probeId", probeId);
                    sender.send(message, DeliveryMode.PERSISTENT, 4, TTL_MS);
                    System.out.println("SEND_OK");
                }
            }

            if ("receive".equals(mode) || "roundtrip".equals(mode)) {
                phase = "RECEIVE";
                String selector = "probeId = '" + probeId + "'";

                try (MessageConsumer receiver =
                             session.createConsumer(queue, selector)) {
                    Message received =
                            receiver.receive(RECEIVE_TIMEOUT_MS);
                    if (received == null) {
                        System.out.println("RECEIVE_TIMEOUT");
                        throw new IllegalStateException(
                                "No matching message within 5000 ms");
                    }
                    if (!(received instanceof TextMessage text)) {
                        throw new IllegalStateException(
                                "Expected TextMessage");
                    }
                    String body = text.getText();
                    if (!("probe:" + probeId).equals(body)) {
                        throw new IllegalStateException(
                                "Unexpected body for probeId");
                    }
                    System.out.println("RECEIVE_OK body=" + body);
                }
            }

            if ("roundtrip".equals(mode)) {
                System.out.println("ROUNDTRIP_OK");
            }

        } catch (JMSException failure) {
            System.err.println(
                    "JMS_FAIL phase=" + phase
                    + " type=" + failure.getClass().getSimpleName()
                    + " errorCode=" + failure.getErrorCode());
            throw failure;
        }
    }

    private static boolean hasValue(
            ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);
        return values != null && !values.isEmpty()
                && values.get(0) != null
                && !values.get(0).isBlank();
    }

    private static String option(
            ApplicationArguments args,
            String name,
            String fallback) {
        List<String> values = args.getOptionValues(name);
        return values == null || values.isEmpty()
                ? fallback : values.get(0);
    }
}
~~~

**Exact explanation of each part:**

1. `SpringApplication.run` initializes the Spring context; Spring Boot injects Artemis's `ConnectionFactory` into the constructor. Even if the broker is not yet connected, the bean being created does not guarantee any JMS permissions have been checked.
2. Inside `try-with-resources`, the code creates `Connection` and `Session.AUTO_ACKNOWLEDGE`. If any step fails, the exception is tagged with `phase`. `connection.start()` only affects message delivery to consumers; sending in JMS does not require a started connection, yet we call `start` here to check setup/receiving readiness.
3. `connect` stops after `CONNECT_OK` and **creates neither producer nor consumer**. Thus it does not verify destination permissions.
4. `send` creates a `TextMessage` with body `probe:<ID>` and property `probeId`. `DeliveryMode.PERSISTENT`, priority `4`, and TTL `300_000 ms` are passed explicitly on that send.
5. `receive` builds a JMS selector from an ID validated to contain only letters/digits/dots/underscores/hyphens, rejecting quotes or characters that could alter selector syntax.
6. `receive(RECEIVE_TIMEOUT_MS)` returns a message or `null` on timeout. Once received, the code verifies **both `TextMessage` type and body**, rather than trusting any arbitrary message on the queue.
7. `roundtrip` executes both phases on the same connection and session and prints `ROUNDTRIP_OK` after both succeed.
8. `try-with-resources` closes producer, consumer, session, and connection after each run, even on errors. Do not share this `Session` concurrently across threads.

This example is **a runnable program**, not pseudocode. The public class `JmsProbeApplication` matches `JmsProbeApplication.java`. Gradle, dependencies, and a broker are needed to run it; standalone `javac JmsProbeApplication.java` without the Spring/JMS classpath will fail.

## 5. Running Each Check Sequentially

Use an installed Gradle or the project's Gradle wrapper if present. Working directory is the `jms-permission-probe` root.

### 5.1. Connection Check

~~~bash
gradle bootRun --args="--probe.mode=connect --probe.id=connect-001"
~~~

If authentication/setup succeeds, the **application output** contains:

~~~text
MODE=connect
PROBE_ID=connect-001
CONNECT_OK
~~~

Spring Boot and Artemis log lines may also appear. If the broker is not running or credentials are wrong, instead of `CONNECT_OK`, you will see a setup error. Some providers defer network operations lazily; therefore `CONNECT_OK` marks only that the invoked setup operations passed, not destination permissions.

### 5.2. Same-Account Round-Trip Check

~~~bash
gradle bootRun --args="--probe.mode=roundtrip --probe.id=trial-001"
~~~

With a clean/empty queue, a running broker, and send + receive rights for the user, the application lines are:

~~~text
MODE=roundtrip
PROBE_ID=trial-001
CONNECT_OK
SEND_OK
RECEIVE_OK body=probe:trial-001
ROUNDTRIP_OK
~~~

This example output uses a fixed ID for easy comparison. In real runs, change `trial-001` to a fresh ID or omit `probe.id` in `roundtrip` mode so the program generates a UUID. Give each run a unique ID to avoid colliding with old messages.

If you get `SEND_OK` followed by `RECEIVE_TIMEOUT`, do not jump straight to "missing permissions": check routing, consumers, selector, queue depth, message expiry, and broker audit logs.

### 5.3. Verifying Send Permission with a Dedicated User

Set `probe-writer` user/password from your secret source, for example in Windows PowerShell:

~~~powershell
$env:SPRING_ARTEMIS_USER = "probe-writer"
$env:SPRING_ARTEMIS_PASSWORD = "<secret-from-secure-store>"
gradle bootRun --args="--probe.mode=send --probe.id=acl-001"
~~~

When `send` is permitted and the queue exists:

~~~text
MODE=send
PROBE_ID=acl-001
CONNECT_OK
SEND_OK
~~~

This output proves **the writer account** can invoke send. It does not prove consume rights. If sending succeeds while the receiver has not run yet, the message remains in the queue until received or its TTL (5 minutes) expires. Do not reuse the same ID across separate runs.

### 5.4. Verifying Receive Permission with a Separate User

Switch credentials to `probe-reader` in the same or another shell, then receive within 5 minutes of the send step:

~~~powershell
$env:SPRING_ARTEMIS_USER = "probe-reader"
$env:SPRING_ARTEMIS_PASSWORD = "<secret-from-secure-store>"
gradle bootRun --args="--probe.mode=receive --probe.id=acl-001"
~~~

If the user has `consume` rights and the message with that ID is still present:

~~~text
MODE=receive
PROBE_ID=acl-001
CONNECT_OK
RECEIVE_OK body=probe:acl-001
~~~

Do not run `receive` multiple times with the same ID expecting all of them to PASS: the first successful receive acknowledges and consumes the message. A timeout on the second receive is normal behavior for a queue once the matching message is gone.

### 5.5. Testing Cases That Must Be Denied

On a test broker with explicit authorization configured, verify:
- `probe-writer` runs `receive` for an ID with a waiting message: policy must deny consume, typically via an exception or broker audit event.
- `probe-reader` runs `send`: policy must deny send rights.
- A valid user with no destination permissions runs both `send` and `receive`: verify the broker's actual enforcement.
- Wrong username/password runs `connect`: authentication must fail.

Negative tests may throw `JMSSecurityException` or a provider-wrapped `JMSException` with a custom error code. **Do not hardcode expectations on a single exception message string.** Check broker security logs to confirm which permission caused the denial. `RECEIVE_TIMEOUT` can result from a missing message, wrong ID, or slow network; a timeout by itself **does not prove** policy denial.

## 6. Interpreting Results with Discipline

~~~text
             +-----------------------+
             | TCP to broker open?   |
             +-----------+-----------+
                         |
          NO: check host, port, firewall, Docker
                         |
                        YES
                         v
             +-----------------------+
             | CONNECT_OK ?          |
             +-----------+-----------+
                         |
          NO: check TLS, credentials, protocol, logs
                         |
                        YES
                         v
             +-----------------------+
             | SEND_OK ?             |
             +-----------+-----------+
                         |
          NO: check send role, address/queue provisioning
                         |
                        YES
                         v
             +-----------------------+
             | RECEIVE_OK ?          |
             +-----------+-----------+
                         |
          NO: selector, TTL, queue depth, consume role,
              competing consumer, auth log, timeout
                         |
                        YES
                         v
             +-----------------------+
             | ROUNDTRIP_OK          |
             +-----------------------+
~~~

Run a TCP check (Windows PowerShell):

~~~powershell
Test-NetConnection localhost -Port 61616
~~~

`TcpTestSucceeded: True` only proves TCP routing can connect; it does not perform a JMS handshake or authentication/authorization. If the broker runs inside a container, also check port mappings and Docker logs. If the broker uses TLS, a client misconfigured with `tcp://` must fix its transport before testing permissions.

### Analyzing Tricky Cases

**`CONNECT_OK` yet `SEND` fails:** Check address security-settings, `send` role, broker queue provisioning, and namespace. If the address/queue does not exist yet and auto-create is blocked, missing `createAddress` or `createDurableQueue` rights can fail before sending. Pre-create the queue to isolate the check.

**`SEND_OK` yet `receive(timeout)` returns `null`:** Verify the message actually routed into `demo.probe`, carries the right `probeId` String/value, has not expired past TTL, was not consumed by another consumer, and that the connection was started. Then inspect broker logs to establish permissions. Never crank timeout up indefinitely.

**`RECEIVE_OK` as admin, yet the real app receives nothing:** Compare principal, destination, selector, listener container startup, concurrency, transaction manager, broker URL, and Spring profiles of **the real application**. Two different login sessions do not imply equal permissions.

**`JMSSecurityException` when creating a consumer:** Strong signal of an auth/authorization issue; inspect applied policies and the principal sent to the broker, especially with login modules or wildcards. Some providers raise the error at different calls (consumer creation vs. receive), so do not assume one universal failure point.

**Multiple brokers/clusters:** Correct host/port is not enough if a load balancer routes to another node or HA/failover is active; note the target instance and inspect queues in the broker admin view. The same name `demo.probe` on two separate instances is still two separate destinations.

**Using `@JmsListener`:** Listeners are Spring-managed, auto-started, and carry their own transaction/concurrency settings. The raw probe isolates JMS-level permissions first; once it PASSES while the listener still fails, shift focus to container/converter/handler configuration. Never manually close Spring's shared connection to "reset" while testing.

## 7. Artemis Permissions and Least Privilege

Apache ActiveMQ Artemis authorizes per address/queue. Permissions to distinguish:

| Artemis permission | Meaning in testing |
| --- | --- |
| `send` | Allows sending messages to an address |
| `consume` | Allows receiving from a queue bound to an address |
| `createAddress` | Creates an address if it does not exist |
| `createDurableQueue` | Creates a durable queue |
| `createNonDurableQueue` | Creates a non-durable queue |
| `browse` | Allows browsing messages without consuming; does not replace `consume` |
| `manage` | Administrative tasks; should not be granted broadly to apps that only send/receive |

An account with `send` **does not automatically** have `consume`. A role with `browse` likewise cannot consume. Policies support wildcards and specific rules; Artemis applies the most specific matching rule, so do not assume wildcard permissions accumulate additively. Administrators must match security-settings accurately against address `demo.probe`.

For apps separating producers and consumers, grant permissions by function. If service A only emits events, A does not need `consume` across every queue. If worker B only reads a queue, B does not need `send` to every address. This keeps testing crisp and limits blast radius if one service is compromised.

**Never weaken broker security policies just to make a probe PASS** before verifying intended behavior. Sometimes the correct result is `ACCESS_DENIED` for an unauthorized user.

## 8. Limitations of This Experiment

This is a **smoke test** for connectivity and authorization, not a full reliability test:

- `SEND_OK` does not prove a business handler received the message or updated a database.
- `RECEIVE_OK` does not prove retries, transactions, DLQ, idempotency, or exactly-once side effects.
- `DeliveryMode.PERSISTENT` does not prove the broker survives every failure; storage, retention, TTL, transactions, and broker HA also matter.
- A 5-minute TTL avoids leaving test messages around too long, though providers may enforce custom expiry policies; expired messages may move to an expiry address rather than disappearing immediately.
- A 5-second timeout fits quick checks; heavily loaded systems or WAN links may need different measurement parameters.
- One passing run does not test failover/reconnect, TLS rotation, connection pooling, competing consumers, or production SLAs.
- `AUTO_ACKNOWLEDGE` is used for the demo; when message handling and database updates must stay consistent, test transactions/acks and duplicate-prevention separately.

Continuously running smoke tests against a live customer-facing queue can also cause side effects: injecting dummy messages, consuming quotas, and polluting monitoring. For recurring synthetic monitoring, use a **dedicated synthetic queue** with bounded frequency, retention, and tightly scoped permissions.

## 9. Auditable Acceptance Checklist

- [ ] Confirmed exact broker name/host/port, environment, and protocol/TLS.
- [ ] Used dedicated queue `demo.probe` or an admin-approved test queue.
- [ ] Pre-created the queue when isolating send/receive rights from destination-creation rights.
- [ ] Recorded the principal/role for every run without printing passwords.
- [ ] `CONNECT_OK` appeared after creating connection/session and calling `start`.
- [ ] `SEND_OK` appeared after sending a message with a unique `probeId`.
- [ ] `RECEIVE_OK` appeared after receiving the matching `TextMessage` and body.
- [ ] Verified permissions separately with distinct **writer** and **reader** identities.
- [ ] Denial results are backed by exceptions/broker audit logs rather than inferred from timeouts.
- [ ] Test messages carry a TTL and do not accumulate indefinitely; cleanup procedure for the test queue is known.
- [ ] Archived run ID, timestamp, environment, destination, per-step status, and errors (if any).

### Self-Check Questions

1. Why does a successful `Test-NetConnection` still not prove the app can send JMS messages?
2. A user creates a `Connection` successfully yet gets rejected on `send`: is that necessarily a password error?
3. Why does a missing queue make measuring `send` permission harder to interpret?
4. How does `RECEIVE_TIMEOUT` differ from `JMSSecurityException`?
5. Why is `connection.start()` needed when using the classic JMS `MessageConsumer` API?
6. If `probe-writer` and `probe-reader` are two separate accounts, what is the sensible test order?
7. Does `ROUNDTRIP_OK` prove all `@JmsListener` endpoints in the real app work? Why or why not?

**Takeaway:** The best probe draws **conclusions strictly proportional to the evidence**. TCP reachability does not mean JMS works; connecting does not mean send rights exist; sending does not mean receive rights exist; receiving a test message does not mean business processing succeeded.

## References

- Jakarta Messaging 3.1 Specification – Connections, Sessions, Message Producers/Consumers: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Boot 3.3 – JMS and Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Spring Framework – JMS integration: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Apache ActiveMQ Artemis – Docker quickstart: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
- Apache ActiveMQ Artemis – Authentication and Authorization: https://artemis.apache.org/components/artemis/documentation/latest/security.html
