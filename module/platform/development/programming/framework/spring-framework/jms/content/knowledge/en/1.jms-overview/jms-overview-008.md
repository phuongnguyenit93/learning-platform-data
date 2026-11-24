# End-to-End Flow: Submitting Requests, Processing, and Recording Results with Spring JMS

## 1. Overall Picture and Goal

Suppose a user submits a request to produce a result that takes time to process: rendering a report, converting a document, or preparing data. An HTTP request does not have to hold the connection open until the job finishes. Spring JMS helps separate **where requests are accepted** from **where work is executed** by passing messages through a message broker.

A complete flow must answer six questions:

1. Who accepts the request and assigns a unique identifier to the job?
2. Which queue is the request sent to; how does the broker hold and deliver the message?
3. Which consumer receives the message; how does it process the business logic?
4. When is the message considered successfully processed and acknowledged/committed?
5. Where is the final result stored and how does the requester view it?
6. If the application, broker, or database fails, how do we prevent lost work and duplicate processing?

In this lesson, a **request** is a job with a `jobId`; the **result** is persisted in a database and queried back over HTTP. This is the **asynchronous request + status lookup** pattern: the initial HTTP response only confirms the request was accepted/dispatched, while the business result appears later.

## 2. Components and Responsibilities

| Component | Responsibility |
| --- | --- |
| Client | Submits requests, receives `jobId`, queries status/results. |
| API/Producer | Validates input, issues `jobId`, saves initial record, and sends a message via `JmsTemplate`. |
| Broker and Queue | Accepts, stores/forwards messages per broker configuration; delivers to consumers. |
| Listener container | Manages connections/sessions, receives messages, invokes methods annotated with `@JmsListener`, and enforces ack/transaction rules. |
| Consumer/Service | Checks `jobId`, runs business logic, guards against duplicate processing, and saves results. |
| Result store | Stores `PENDING`, `COMPLETED`, or error states; allows queries independent of the JMS message lifecycle. |

For a point-to-point **queue**, each message delivery normally goes to one consumer in a competing group; if multiple instances listen, they share the workload. A **topic** is used when multiple subscriptions need to receive the same event; do not confuse a topic with a single-job processing queue.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Client
    participant API as HTTP API / Producer
    participant DB as Result DB
    participant MQ as JMS Broker / Queue
    participant Worker as @JmsListener
    User->>API: POST /jobs, input
    API->>DB: INSERT jobId + PENDING
    API->>MQ: convertAndSend(jobId)
    API-->>User: HTTP 202 + jobId
    MQ->>Worker: deliver message
    Worker->>DB: SELECT job + check duplicates
    Worker->>Worker: process business logic
    Worker->>DB: UPDATE result + COMPLETED
    Worker-->>MQ: return success / commit session
    User->>API: GET /jobs/{jobId}
    API->>DB: SELECT status + result
    API-->>User: COMPLETED + result
~~~

The diagram shows the **happy path**. Consumer steps execute after the broker delivers the message; the moment HTTP 202 is returned does not mean the consumer has finished processing. The message broker neither creates a results table on its own nor knows whether a job succeeded at the business level: the application must record that explicitly.

## 3. Detailed Walkthrough of Each Stage

### Stage A — Request Acceptance and Dispatch

1. The API validates input data and issues a unique `jobId`, such as a UUID.
2. The API persists a record with `jobId`, the payload to process, and status `PENDING`. This record serves as the lookup reference and also as the basis for detecting an already-completed job if the message is redelivered.
3. The producer sends a message to a queue, e.g., `jobs.requests`, via `JmsTemplate.convertAndSend(...)`.
4. Once the send call completes under the provider's contract, the API can return HTTP 202 Accepted with `jobId`. **202 only means the request was accepted for asynchronous processing**, not that it has succeeded.

Distinguish three identifiers: **`jobId`** is the application-assigned business key; **`JMSMessageID`** is assigned by the provider to a JMS message; **`JMSCorrelationID`** can be attached to link messages within an exchange. Do not use `JMSMessageID` in place of a business key if the system must deduplicate across redeliveries or newly created messages.

### Stage B — Broker and Consumer

The broker manages the queue, accepts messages from producers, and delivers them to consumers when a session/consumer is ready. Durable storage, TTL, priority, queue limits, redelivery, and dead-letter addresses/queues (DLQ) depend on the provider and actual configuration. Do not assume every message is retained indefinitely or arrives in global order when multiple consumers exist.

Spring creates a listener container for the `@JmsListener` method. The container handles connecting, receiving, and dispatching; the service focuses on business logic. The consumer receives `jobId`, reads the persisted input, processes it, and updates `result` and `status`. With multiple instances or redelivery, processing must be **idempotent**: receiving the same `jobId` again must produce no extra side effects.

### Stage C — Recording Results and Acknowledging the Message

To inspect results after the JMS message has been consumed, persist data to durable storage such as a jobs table, object storage, or a result service. A minimal state set:

| Status | Meaning |
| --- | --- |
| `PENDING` | Request saved; queued or in-progress in the simple example. |
| `COMPLETED` | Task successfully wrote the business result. |
| `DISPATCH_FAILED` | Producer failed to send the message based on the observed error. |
| `FAILED` (extended) | Task permanently failed; requires saving the reason and an explicit error-handling workflow. |

If the listener runs in a **transacted JMS session**, normal listener completion allows the session to commit; an unhandled exception rolls back the session so the broker can redeliver the message. Do not equate **JMS commit** with **DB commit**: a local JMS transaction does not automatically combine a JDBC update and message acknowledgment into one atomic transaction across two resources.

An important case: the DB saved `COMPLETED` but the process stopped right before the JMS commit. The broker may redeliver. The consumer checks that `jobId` is already `COMPLETED` and returns normally, thereby avoiding repeating the result or side effects. The opposite case—producer saves `PENDING` and stops before sending to JMS—will leave the job stuck unless an outbox/reconciliation mechanism exists.

### Stage D — Caller Retrieves the Result

The client can send `GET /jobs/{jobId}` after receiving HTTP 202, poll at an appropriate interval, or receive a callback/WebSocket/event if the architecture supports it. The status resource should clearly report **pending**, **completed**, **dispatch failed**, or **processing failed**; HTTP 200 on the status lookup API merely reflects that the read request succeeded, not the job's own status.

## 4. Runnable Example: Spring Boot 3.3.x + Artemis + H2

This example uses Java 17+, Spring Boot 3.3.13, a running ActiveMQ Artemis broker, and H2 persisting records to a local file. The sample job converts text to uppercase so the focus stays on the JMS mechanism. Every file below belongs to the same Maven project and the same `example.jmsflow` package; you cannot compile a single Spring class standalone with `javac` without dependencies.

Structure:

~~~text
jms-flow/
├── pom.xml
└── src/main/
    ├── java/example/jmsflow/
    │   ├── JmsFlowApplication.java
    │   ├── JobController.java
    │   └── JobWorker.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 4.1. Dependencies (pom.xml)

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>jms-flow</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-artemis` brings in the JMS client/integration; Spring Boot auto-configures `ConnectionFactory`, `JmsTemplate`, and listener containers when the matching dependencies are present. H2 serves the local demo here; production systems choose a database, retention, and backups based on business requirements.

### 4.2. Configuration (src/main/resources/application.properties)

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

spring.datasource.url=jdbc:h2:file:./data/jms-flow;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

The `artemis/artemis` credentials are the defaults of the test broker command below; use secrets and dedicated accounts in real environments. The `jdbc:h2:file` URL keeps records from disappearing simply because the Spring Boot app restarts, though it does not make H2 a distributed database.

### 4.3. Result Schema (src/main/resources/schema.sql)

~~~sql
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(36) PRIMARY KEY,
    request_text VARCHAR(1000) NOT NULL,
    status VARCHAR(32) NOT NULL,
    result_text VARCHAR(1000)
);
~~~

The primary key `id` keeps one record per `jobId`. The row stores both input and output, so the message on the queue only needs to carry `jobId`; this approach is convenient for retries and duplicate prevention. In larger systems, the message may carry a versioned payload or a reference to object storage depending on coupling and data goals.

### 4.4. Application Bootstrap (JmsFlowApplication.java)

~~~java
package example.jmsflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class JmsFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(JmsFlowApplication.class, args);
    }
}
~~~

### 4.5. Producer and Status Query API (JobController.java)

~~~java
package example.jmsflow;

import java.util.List;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.JmsException;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/jobs")
public class JobController {
    private final JdbcTemplate jdbc;
    private final JmsTemplate jms;

    public JobController(JdbcTemplate jdbc, JmsTemplate jms) {
        this.jdbc = jdbc;
        this.jms = jms;
    }

    public record NewJob(String text) {}
    public record Accepted(String id, String status) {}
    public record JobStatus(String id, String status, String result) {}

    @PostMapping
    public ResponseEntity<Accepted> submit(@RequestBody NewJob request) {
        if (request.text() == null || request.text().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "text must not be blank");
        }

        String id = UUID.randomUUID().toString();
        jdbc.update(
                "INSERT INTO jobs(id, request_text, status) VALUES (?, ?, ?)",
                id, request.text(), "PENDING");

        try {
            jms.convertAndSend("jobs.requests", id);
        } catch (JmsException ex) {
            jdbc.update(
                    "UPDATE jobs SET status = 'DISPATCH_FAILED' WHERE id = ?",
                    id);
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE, "JMS send failed", ex);
        }
        return ResponseEntity.accepted().body(new Accepted(id, "PENDING"));
    }

    @GetMapping("/{id}")
    public JobStatus get(@PathVariable String id) {
        List<JobStatus> rows = jdbc.query(
                "SELECT id, status, result_text FROM jobs WHERE id = ?",
                (rs, rowNum) -> new JobStatus(
                        rs.getString("id"),
                        rs.getString("status"),
                        rs.getString("result_text")),
                id);
        if (rows.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Unknown job");
        }
        return rows.get(0);
    }
}
~~~

The JDBC statements are separate DB operations. Because `INSERT` finishes before `convertAndSend`, the consumer can find `jobId` when it receives the message. However, the "INSERT then send message" pair still has a gap on crash; Section 6 explains how to solve this in production.

### 4.6. Consumer and Result Recording (JobWorker.java)

~~~java
package example.jmsflow;

import java.util.List;
import java.util.Locale;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class JobWorker {
    private final JdbcTemplate jdbc;

    public JobWorker(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private record JobRow(String requestText, String status) {}

    @JmsListener(destination = "jobs.requests")
    public void handle(String id) {
        List<JobRow> rows = jdbc.query(
                "SELECT request_text, status FROM jobs WHERE id = ?",
                (rs, rowNum) -> new JobRow(
                        rs.getString("request_text"),
                        rs.getString("status")),
                id);

        if (rows.isEmpty()) {
            throw new IllegalStateException("Unknown job: " + id);
        }

        JobRow job = rows.get(0);
        if ("COMPLETED".equals(job.status())) {
            return; // Redelivered message: job already has a result.
        }

        String result = job.requestText().trim().toUpperCase(Locale.ROOT);
        jdbc.update(
                "UPDATE jobs SET result_text = ?, status = 'COMPLETED' " +
                "WHERE id = ? AND status <> 'COMPLETED'",
                result, id);
    }
}
~~~

The `String` received by the listener is the text body inside the JMS message converted by `JmsTemplate`. If a JDBC error or uncaught business error occurs, the method throws an exception; with a container using JMS transactions, the session rolls back so the broker has a chance to redeliver. The demo uses a pure transformation and a conditional `UPDATE`, making redelivery low-risk. If a real task sends emails, calls a payment API, or mutates another system, merely checking `COMPLETED` beforehand is not enough to guarantee once-only effects in all cases: an idempotency key and outcome-confirmation mechanism from the target system are required.

### 4.7. Running and Observing

Java 17+, Maven, running Docker, and available ports 61616/8080 are required. Use the official Apache Artemis image:

~~~bash
docker run --detach --rm --name jms-flow-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Run the following command in the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Once the broker is ready, send an HTTP request:

~~~http
POST /jobs HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"text":"hello jms"}
~~~

The API returns **HTTP 202** with JSON containing `id` (a runtime-generated UUID) and an initial status of `PENDING`. Use the returned `id` to call:

~~~http
GET /jobs/{id} HTTP/1.1
Host: localhost:8080
~~~

In a successful run, the final status is `COMPLETED` and `result` is `HELLO JMS`. Do not rely on log order to deduce exact timing: the worker may process very quickly, even before the client finishes reading HTTP 202. If `GET` is called before the worker finishes, `PENDING` will be seen; this is valid behavior.

The Docker command above only illustrates a learning environment, removing the container on stop and mounting no broker data volume. When testing recovery across broker restarts, configure persistence/volumes properly. If the broker disables destination auto-creation, create the `jobs.requests` queue per Artemis configuration. The H2 file also resides only on the machine running the application.

## 5. What Happens on Errors or Duplicate Deliveries?

| Failure Point | Possible Symptom | Design / Check Approach |
| --- | --- | --- |
| API receives invalid data | No job created or message sent | Return 400 with input validation details. |
| DB INSERT fails | No job record exists | Stop before JMS send; return an appropriate error. |
| DB INSERT succeeds, app crashes before JMS send | `PENDING` may remain stuck forever | Transactional outbox and dispatcher/reconciliation. |
| Broker unreachable during send | Producer throws exception; send outcome may be unknown if network fails around confirmation | Persist status, controlled retries, and `jobId`/idempotency key. |
| Consumer hits transient error | JMS session rolls back; broker may redeliver | Limit retry attempts, backoff, DLQ, and alerting. |
| DB writes `COMPLETED`, listener crashes before JMS commit | Broker may redeliver the same job | Check `jobId` and perform idempotent updates. |
| Permanently malformed input | Infinite retries can clog the queue | Classify errors, route to DLQ, or record `FAILED` per explicit policy. |
| Client calls GET too early | Sees only `PENDING` | Poll again with backoff; never declare completion from HTTP 202. |
| Multiple consumers run in parallel | Global ordering is not guaranteed | Use business keys, conditional updates/locking, and message grouping when needed. |

**Ack is not proof that all side effects are safe.** With a transacted listener, JMS commit acknowledges message consumption within the JMS resource. Databases, external HTTP calls, and the broker can commit at different times. Therefore practical designs usually accept **at-least-once processing** and make handlers idempotent, rather than assuming "exactly once end-to-end".

**Do not swallow exceptions improperly.** If a consumer catches every exception, logs it, and returns normally, the container may treat the message as successfully processed and commit; the job loses its retry opportunity. Only return normally when a result or permanent failure has been handled per policy. Transient errors must be thrown so rollback triggers when configured.

**DLQ does not automatically update job status.** Moving a message to the DLQ on the broker still does not change the DB record to `FAILED`. For the API to reflect status accurately, a process/handler must read the DLQ, record the error, and surface the incident per policy.

## 6. Upgrades Needed for Production Use

### 6.1. Transactional Outbox to Close the Gap Between DB and JMS

The demo executes **INSERT jobs** and then **JMS send** as two separate operations. If the application stops between them, the job exists in the DB without a message.

A transactional outbox solves this by writing, inside **the same DB transaction**, both the job record and an outbox record containing a "JobRequested" event. A separate dispatcher reads the outbox, sends to JMS, and marks it sent. The dispatcher can still re-send if it fails after sending and before marking, so the consumer must still be idempotent. An outbox prevents losing the intent to send; it does not magically create exactly-once across two independent resources.

### 6.2. JMS Transactions, DB Transactions, and XA

- **JMS local transaction:** receptions/responses on a JMS session can roll back or commit together; does not include DB transactions by default.
- **DB transaction:** protects multiple JDBC statements on the same DB resource, such as conditional status checks/transitions.
- **XA/JTA:** can coordinate multiple compatible resources in one distributed transaction, at the cost of more complex configuration, coordinator logs, and operational overhead.
- **Outbox + idempotency:** usually the right path when avoiding distributed transactions; requires designing retries, deduplication, and reconciliation explicitly.

With Spring Boot 3.3 and the default JMS listener container, Spring Boot configures a transacted session when no JTA manager is present. However, when defining a custom factory or changing versions/configurations, re-verify actual acknowledgment and transaction behavior. Putting `@Transactional` on JDBC **does not automatically turn two resources into one atomic transaction**.

### 6.3. Monitoring, Security, and Performance

- Monitor pending message count in the queue, oldest message age, redelivery count, DLQ, producer errors, processing duration, and `COMPLETED`/`FAILED` ratios.
- Propagate correlation by `jobId` across logs/APIs/DB; do not log payloads containing sensitive data.
- Limit message size, TTL, retries/backoff, concurrency, and queue access permissions; use TLS and secure credentials in deployment.
- For long-running jobs, avoid holding a DB transaction open across heavy computation or network calls; define maximum processing times and cancellation support.
- Design explicit states for timeout/`FAILED` and data cleanup policies; do not leave `PENDING` lingering indefinitely without monitoring.
- When scaling multiple workers, ensure safe duplicate handling and consider ordering per business key rather than expecting whole-queue ordering.

## 7. Self-Check Questions

1. **Why doesn't HTTP 202 prove a job is finished?** Because 202 is returned right after request acceptance/dispatch; business processing runs asynchronously.
2. **Why still save results in a DB if JMS already has a queue?** A queue is for handing off work; after a message is consumed, the result must exist independently for clients to query and audit.
3. **What if the DB already saved `COMPLETED` but JMS has not committed yet?** The broker may redeliver; the consumer must recognize the job is already complete and avoid repeating side effects.
4. **Where is the message-loss gap in the demo?** DB `INSERT` succeeds and then the app crashes before send; solved via outbox/reconciliation.
5. **What happens if every error is caught and then returned normally?** The container may commit/ack even though the job failed; transient and permanent errors must be distinguished.
6. **When are `JMSReplyTo`/`JMSCorrelationID` used?** When a response message travels back over JMS; in this pattern the client queries results over HTTP using `jobId`, so no JMS reply queue is needed. Synchronous request–reply over JMS is a different design requiring explicit timeouts and correlation.

A worthwhile hands-on exercise: submit a job, temporarily stop the consumer to observe the message sitting in the queue, restart it to see the status change; next, make the listener throw an exception before `UPDATE` and observe redelivery; finally, simulate an error after `UPDATE` and verify deduplication. Cross-check logs, queue metrics, and the `jobs` table rather than relying only on HTTP responses.

## 8. Authoritative References for Deeper Study

- Spring Framework — Receiving a Message: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework — Using Spring JMS/Transaction Management: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot — JMS (3.3): https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Apache Artemis — Official Docker image: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
