# Hands-on Java publisher and subscriber with deduplication in Pub/Sub

Suppose the `orders-api` service on Cloud Run publishes an **OrderPaid** event to Pub/Sub. A Java worker running on GKE receives the event to create a shipping task in Cloud SQL PostgreSQL. Two situations easily create duplicate tasks:

1. The publisher sent successfully yet lost the response, so it resends **the same business event** as a different Pub/Sub message.
2. The subscriber **COMMITted** to the database yet crashed before ACKing, so Pub/Sub can redeliver the old message.

This hands-on lesson builds a **publisher, pull subscriber, and deduplication tracker**. The goal is not merely printing "received message," but proving that **two messages sharing the same `eventId` create only one shipping task**.

This lesson belongs to the **Pub/Sub and Messaging** chapter, module `CLOUD_PROVIDERS_GCP`. The techniques apply to Java apps on Compute Engine, GKE, or Cloud Run combined with IAM, VPC, Cloud SQL, Cloud Storage, release automation, and reliability/cost monitoring. The hands-on uses a **lab** project and database without altering production resources.

## Learning objectives

After this lesson, you will be able to:

- Write a Java publisher sending `PubsubMessage` with a stable `eventId`.
- Write a Java subscriber receiving messages, executing a PostgreSQL transaction, **ACKing after COMMIT**, and NACKing on transient errors.
- Distinguish Pub/Sub's `messageId` from the application's `eventId`.
- Use a unique constraint to handle duplicates even across **multiple worker replicas**.
- Run two publishes of the same event and verify the database has only one shipping task.
- Analyze redelivery from ack deadline/crash, confirmed ACK, and limits of exactly-once delivery.
- Monitor backlog, retries, IAM, data security, and cost.

## 1. Architecture and guarantee boundaries

~~~mermaid
flowchart LR
    P["Java Publisher<br/>stable eventId"] -->|"publish"| TOPIC["Topic: orders-events-lab"]
    TOPIC --> SUB["Pull subscription<br/>orders-worker-lab"]
    SUB --> W["Java Subscriber<br/>transaction + ACK"]
    W --> DB[("PostgreSQL<br/>processed_events + shipping_tasks")]
    W -. "NACK / unACKed" .-> SUB
    DB --> OBS["Inspect row counts + metrics"]
~~~

**At-least-once** is the default: a Pub/Sub message can be redelivered. Pub/Sub **exactly-once delivery** can only be enabled for **pull/StreamingPull** within **the same region** guarantee scope; it does not merge distinct publishes and **does not create a transaction spanning Pub/Sub and PostgreSQL**.

| Identifier | Who assigns it? | What is it used for? |
| --- | --- | --- |
| `eventId=order-paid:LAB-1:v1` | Application, before the first publish | Identifies **the same business event** across publisher retries |
| `messageId` | Pub/Sub after each accepted publish | Identifies one Pub/Sub message, stable across redeliveries of that message |
| `ackId` | Pub/Sub for **each pull delivery** | ACK/NACK a single delivery; can change after redelivery |
| `orderId=LAB-1` | Business system | Identifies the order; not necessarily enough to deduplicate every event on the order |

**Design rule:** subscribers deduplicate by **`eventId`** or an appropriate business key, **not `messageId` alone**. Two separate publishes of the same event usually receive two different `messageId` values.

## 2. Lab prerequisites and IAM

Requires Java 21, Maven 3.9+, Google Cloud CLI, a project with billing/Pub/Sub API enabled, PostgreSQL 16 (local or authorized Cloud SQL), and permissions to create resources in the **lab project**. Shell snippets use **Bash**; on PowerShell, convert `export NAME=value` to `$env:NAME="value"`.

Identities:

| Person/process | Minimum permissions to consider |
| --- | --- |
| Lab setup user | Appropriate topic/subscription creation permissions |
| Publisher identity | `roles/pubsub.publisher` on the topic |
| Subscriber identity | `roles/pubsub.subscriber` on the subscription |
| Worker accessing Cloud SQL | Appropriate DB connection permissions, DB user/role scoped to read-write only required tables |
| Production deployer | Corresponding GKE/VM/Cloud Run deployment permissions, separate from runtime identity |

On a local machine, use **Application Default Credentials (ADC)**:

~~~bash
gcloud auth application-default login
gcloud auth application-default set-quota-project PROJECT_ID

gcloud services enable pubsub.googleapis.com --project=PROJECT_ID
~~~

**Never commit service account JSON keys to a repository.** On GKE use Workload Identity Federation for GKE; on Compute Engine use a VM-attached service account; on Cloud Run use a runtime service account. For production Cloud SQL, prefer Cloud SQL connectors/Auth Proxy, TLS, and Secret Manager/IAM database authentication as required.

### 2.1. Create topic and pull subscription

~~~bash
gcloud pubsub topics create orders-events-lab \
  --project=PROJECT_ID

gcloud pubsub subscriptions create orders-worker-lab \
  --topic=orders-events-lab \
  --ack-deadline=30 \
  --project=PROJECT_ID

gcloud pubsub subscriptions describe orders-worker-lab \
  --project=PROJECT_ID \
  --format="yaml(name,topic,ackDeadlineSeconds,enableExactlyOnceDelivery)"
~~~

**`create` commands make real changes and can incur charges.** If an identically named resource already exists, check ownership rather than deleting/overwriting it. The initial lab uses **at-least-once**, without needing exactly-once enabled to prove idempotency.

## 3. Maven project structure

To try this, create the following files **in a dedicated lab directory on the learner's machine**:

~~~text
pubsub-java-lab/
├── pom.xml
└── src/main/java/lab/pubsub/
    ├── PublishOrder.java
    └── ConsumeOrder.java
~~~

This lesson provides the full contents of both Java classes; the code uses plain JDBC for PostgreSQL instead of Spring Boot so learners clearly see the **COMMIT before ACK** boundary.

### 3.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab.pubsub</groupId>
  <artifactId>pubsub-java-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>libraries-bom</artifactId>
        <version>26.90.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-pubsub</artifactId>
    </dependency>
    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
      <version>42.7.14</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.4</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The Cloud Java BOM manages Pub/Sub and related Google library versions. Versions here are **verified example baselines**, not requirements to pin forever; production should update and scan dependencies per policy.

## 4. PostgreSQL: deduplication marker and business effect in one transaction

Create two tables:

~~~sql
CREATE TABLE IF NOT EXISTS processed_events (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE IF NOT EXISTS shipping_tasks (
    event_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    status TEXT NOT NULL
);
~~~

**Both tables live in the same database** so they can commit atomically:

1. Attempt `INSERT` into `processed_events` with key `(consumer_name, event_id)`.
2. If **inserted**, create a `shipping_tasks` row.
3. If **already present**, do not create the task again.
4. `COMMIT` both marker and task; **only afterward ACK Pub/Sub**.

The unique constraint works even when two subscribers process concurrently. An in-memory Java `HashSet` is **insufficient**, because each Pod/VM has private memory and restarts wipe the cache.

### 4.1. Local PostgreSQL for the lab

If Docker is available and you do not have a separate lab PostgreSQL:

~~~bash
docker run -d --rm --name orders-pg-lab \
  -e POSTGRES_PASSWORD=lab-only-change-me \
  -e POSTGRES_DB=orders_lab \
  -p 127.0.0.1:5432:5432 \
  postgres:16
~~~

Connect:

~~~bash
docker exec -it orders-pg-lab psql -U postgres -d orders_lab
~~~

At the `psql` prompt, run the two `CREATE TABLE` statements above, then type `\q`. The password `lab-only-change-me` is **strictly for a loopback test container**, not a production value.

Set environment variables in the terminal that will run the subscriber:

~~~bash
export JDBC_URL="jdbc:postgresql://127.0.0.1:5432/orders_lab"
export DB_USER="postgres"
export DB_PASSWORD="lab-only-change-me"
~~~

In production, never use the `postgres` superuser, never hardcode passwords in scripts, and never expose the database publicly; use a least-privilege DB principal with secret injection.

## 5. Java Publisher: eventId must remain stable across retries

File `src/main/java/lab/pubsub/PublishOrder.java`:

~~~java
package lab.pubsub;

import com.google.api.core.ApiFuture;
import com.google.cloud.pubsub.v1.Publisher;
import com.google.protobuf.ByteString;
import com.google.pubsub.v1.PubsubMessage;
import com.google.pubsub.v1.TopicName;
import java.util.concurrent.TimeUnit;

public class PublishOrder {
    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                "Usage: PROJECT_ID TOPIC_ID EVENT_ID ORDER_ID");
        }
        String eventId = args[2];
        String orderId = args[3];
        if (eventId.isBlank() || orderId.isBlank()) {
            throw new IllegalArgumentException("IDs must not be blank");
        }

        TopicName topic = TopicName.of(args[0], args[1]);
        Publisher publisher = Publisher.newBuilder(topic).build();
        try {
            PubsubMessage message = PubsubMessage.newBuilder()
                .setData(ByteString.copyFromUtf8("OrderPaid"))
                .putAttributes("eventId", eventId)
                .putAttributes("orderId", orderId)
                .build();

            ApiFuture<String> future = publisher.publish(message);
            String messageId = future.get(30, TimeUnit.SECONDS);
            System.out.println("publish confirmed, messageId=" + messageId
                + ", eventId=" + eventId);
        } finally {
            publisher.shutdown();
            publisher.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

**Key point:** `future.get()` reports the publish result received by the client. If the request reached Pub/Sub yet the response was lost, the publisher cannot know the message was accepted; re-running the program with the **same EVENT_ID** creates another publish yet remains **one business event** under dedupe logic.

The code puts `eventId` and `orderId` in message **attributes** to simplify the lab. When using JSON/Avro/Protobuf in real systems, define clear schemas, validation, and versions; never trust external attributes without authenticating the source.

## 6. Java Subscriber: commit once, then ACK

File `src/main/java/lab/pubsub/ConsumeOrder.java`:

~~~java
package lab.pubsub;

import com.google.cloud.pubsub.v1.AckReplyConsumerWithResponse;
import com.google.cloud.pubsub.v1.AckResponse;
import com.google.cloud.pubsub.v1.MessageReceiverWithAckResponse;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.PubsubMessage;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;

public class ConsumeOrder {
    private static final String CONSUMER = "shipping-worker";

    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: PROJECT_ID SUBSCRIPTION_ID");
        }

        String url = requiredEnv("JDBC_URL");
        String user = requiredEnv("DB_USER");
        String password = requiredEnv("DB_PASSWORD");

        MessageReceiverWithAckResponse receiver =
            (PubsubMessage msg, AckReplyConsumerWithResponse reply) -> {
                String eventId = msg.getAttributesOrDefault("eventId", "");
                String orderId = msg.getAttributesOrDefault("orderId", "");

                if (!"OrderPaid".equals(msg.getData().toStringUtf8())
                        || eventId.isBlank() || orderId.isBlank()) {
                    System.err.println("Invalid event, messageId="
                        + msg.getMessageId());
                    // Production: configure DLQ/quarantine for poison messages.
                    reply.nack();
                    return;
                }

                boolean created;
                try {
                    created = persistOnce(url, user, password, eventId, orderId);
                } catch (SQLException error) {
                    System.err.println("DB transaction failed, messageId="
                        + msg.getMessageId() + ", retry later");
                    reply.nack(); // Do not ACK if transaction failed.
                    return;
                }

                System.out.println((created ? "CREATED" : "DUPLICATE_SKIPPED")
                    + " eventId=" + eventId
                    + " messageId=" + msg.getMessageId());

                // At this point transaction has COMMITted. Do not NACK on ACK failure alone.
                try {
                    AckResponse result = reply.ack().get(30, TimeUnit.SECONDS);
                    System.out.println("ACK result=" + result
                        + " messageId=" + msg.getMessageId());
                    if (result != AckResponse.SUCCESSFUL) {
                        System.err.println("ACK not confirmed");
                    }
                } catch (Exception error) {
                    System.err.println("ACK outcome uncertain; dedupe"
                        + " will protect if message is redelivered");
                    if (error instanceof InterruptedException) {
                        Thread.currentThread().interrupt();
                    }
                }
            };

        ProjectSubscriptionName sub =
            ProjectSubscriptionName.of(args[0], args[1]);

        Subscriber.Builder builder = Subscriber.newBuilder(sub, receiver);
        // Optional: pin endpoint when using exactly-once in one region.
        String endpoint = System.getenv("PUBSUB_ENDPOINT");
        if (endpoint != null && !endpoint.isBlank()) {
            builder.setEndpoint(endpoint);
        }

        Subscriber subscriber = builder.build();
        Runtime.getRuntime().addShutdownHook(
            new Thread(() -> subscriber.stopAsync()));

        subscriber.startAsync().awaitRunning();
        System.out.println("Listening on " + sub);
        subscriber.awaitTerminated();
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + name);
        }
        return value;
    }

    private static boolean persistOnce(
        String url, String user, String password,
        String eventId, String orderId) throws SQLException {

        try (Connection db =
                 DriverManager.getConnection(url, user, password)) {
            db.setAutoCommit(false);
            try {
                int inserted;
                try (PreparedStatement p = db.prepareStatement(
                    "INSERT INTO processed_events "
                    + "(consumer_name, event_id, order_id) "
                    + "VALUES (?, ?, ?) ON CONFLICT DO NOTHING")) {
                    p.setString(1, CONSUMER);
                    p.setString(2, eventId);
                    p.setString(3, orderId);
                    inserted = p.executeUpdate();
                }

                if (inserted == 0) {
                    // Do not silently ignore if the same ID carries a different payload.
                    try (PreparedStatement p = db.prepareStatement(
                        "SELECT order_id FROM processed_events "
                        + "WHERE consumer_name=? AND event_id=?")) {
                        p.setString(1, CONSUMER);
                        p.setString(2, eventId);
                        try (ResultSet rs = p.executeQuery()) {
                            if (!rs.next() || !orderId.equals(rs.getString(1))) {
                                throw new SQLException(
                                    "Reused eventId with different orderId");
                            }
                        }
                    }
                    db.commit();
                    return false;
                }

                try (PreparedStatement p = db.prepareStatement(
                    "INSERT INTO shipping_tasks "
                    + "(event_id, order_id, status) VALUES (?, ?, ?)")) {
                    p.setString(1, eventId);
                    p.setString(2, orderId);
                    p.setString(3, "READY");
                    p.executeUpdate();
                }

                db.commit(); // Marker + shipping task COMMIT together.
                return true;
            } catch (SQLException error) {
                db.rollback();
                throw error;
            }
        }
    }
}
~~~

### 6.1. Why does this code prevent duplicates?

| Failure point | Database state | When Pub/Sub redelivers |
| --- | --- | --- |
| Crash before transaction | Nothing written | Processes normally |
| Crash after inserting marker but before COMMIT | PostgreSQL rolls back transaction | Processes normally |
| Crash after COMMIT, before ACK | Both marker and shipping task exist | `DUPLICATE_SKIPPED`, then ACKs |
| Publisher sends two Pub/Sub messages with same `eventId` | Only first transaction inserts marker | Second message skips business effect |
| Two workers process the same event concurrently | Unique constraint serializes in DB | One transaction wins, the other sees duplicate |

**Limitation:** this transaction only protects **two tables inside the same PostgreSQL database**. When calling payment APIs, sending emails, or writing to external systems, you need a **target idempotency key**, transactional outbox/saga, or reconciliation step; PostgreSQL `COMMIT` cannot make external HTTP calls atomic.

### 6.2. What does the ACK response mean?

`AckReplyConsumerWithResponse.ack()` returns a future containing `AckResponse`. When a subscription has **exactly-once enabled** and the ACK is confirmed successful, Pub/Sub guarantees the message will not be redelivered **within the supported regional scope**. On a default at-least-once subscription, the future can succeed immediately without carrying the same server-confirmed ACK guarantee.

Even when an ACK is confirmed, **two separate publishes** carrying the same business event can still arrive. Therefore the dedupe table is mandatory, not merely a fallback for when exactly-once is off.

## 7. Running end-to-end

Open three terminals: **PostgreSQL**, **subscriber**, and **publisher**. Ensure the database has both tables from Section 4 and the app has ADC credentials. Inside `pubsub-java-lab`:

~~~bash
mvn -B -ntp -DskipTests compile
~~~

**Subscriber terminal** (after setting `JDBC_URL`, `DB_USER`, `DB_PASSWORD`):

~~~bash
mvn -q exec:java \
  -Dexec.mainClass=lab.pubsub.ConsumeOrder \
  -Dexec.args="PROJECT_ID orders-worker-lab"
~~~

**Publisher terminal**:

~~~bash
mvn -q exec:java \
  -Dexec.mainClass=lab.pubsub.PublishOrder \
  -Dexec.args="PROJECT_ID orders-events-lab order-paid:LAB-1:v1 LAB-1"
~~~

Output should look similar to:

~~~text
Publisher: publish confirmed, messageId=123456789, eventId=order-paid:LAB-1:v1

Subscriber: CREATED eventId=order-paid:LAB-1:v1 messageId=123456789
Subscriber: ACK result=SUCCESSFUL messageId=123456789
~~~

The `messageId` above is illustrative. On a default subscription without exactly-once enabled, a client `SUCCESSFUL` result **does not imply the same confirmed-ACK guarantee as exactly-once**.

### 7.1. Inspect the database

~~~sql
SELECT event_id, order_id, status
FROM shipping_tasks
ORDER BY event_id;

SELECT consumer_name, event_id, order_id, processed_at
FROM processed_events
ORDER BY processed_at;
~~~

Expect **one row** for `order-paid:LAB-1:v1` in each table.

## 8. Reproducible publisher duplicate test

**Re-run the exact same publisher command**, keeping the same `eventId` and `orderId`:

~~~bash
mvn -q exec:java \
  -Dexec.mainClass=lab.pubsub.PublishOrder \
  -Dexec.args="PROJECT_ID orders-events-lab order-paid:LAB-1:v1 LAB-1"
~~~

Pub/Sub assigns a **new messageId** because this is a **second publish**. The subscriber will show:

~~~text
DUPLICATE_SKIPPED eventId=order-paid:LAB-1:v1 messageId=987654321
ACK result=SUCCESSFUL messageId=987654321
~~~

Run SQL to verify row counts:

~~~sql
SELECT count(*) AS tasks
FROM shipping_tasks
WHERE event_id = 'order-paid:LAB-1:v1';

SELECT count(*) AS markers
FROM processed_events
WHERE consumer_name = 'shipping-worker'
  AND event_id = 'order-paid:LAB-1:v1';
~~~

**Expected result:** `tasks=1` and `markers=1` after **both publishes**. This is a much more deterministic test than waiting for Pub/Sub to randomly redeliver.

### 8.1. Do not change content while reusing the same ID

If the same `eventId` arrives with a different `orderId`, the code throws an SQL error and NACKs (never silently drops the event). In a real system, this could indicate a publisher bug or payload tampering: log safely, investigate, and route to quarantine/DLQ per policy. Do not create infinite retries by continuously publishing mismatched payloads.

## 9. Testing redelivery when unACKed

To observe **at-least-once redelivery**, **stop the Java subscriber first** (Ctrl+C) and publish a new `eventId`. Use a test pull command **without `--auto-ack`**:

~~~bash
gcloud pubsub topics publish orders-events-lab \
  --message="OrderPaid" \
  --attribute="eventId=order-paid:LAB-2:v1,orderId=LAB-2" \
  --project=PROJECT_ID

gcloud pubsub subscriptions pull orders-worker-lab \
  --limit=1 --project=PROJECT_ID
~~~

Do not send an ACK. After the **ack deadline expires**, pull again to observe the message being redelivered:

~~~bash
gcloud pubsub subscriptions pull orders-worker-lab \
  --limit=1 --project=PROJECT_ID
~~~

Redelivery timing is **not an exact 30-second stopwatch**: retry policy, backoff, and subscription state can shift it. Afterward, restart the Java subscriber to process and ACK it. Never pass `--auto-ack` when testing redelivery.

**Testing a crash after COMMIT before ACK** requires fault injection in an isolated environment. If you intentionally kill the process right after COMMIT, the durable marker is already saved, so the next delivery simply ACKs without creating another task. Never inject faults against production workloads or kill pods handling live transactions.

## 10. When should you enable exactly-once?

You can create **another pull subscription** for the lab to compare (without altering the running subscription):

~~~bash
gcloud pubsub subscriptions create orders-worker-exactly-lab \
  --topic=orders-events-lab \
  --enable-exactly-once-delivery \
  --ack-deadline=60 \
  --project=PROJECT_ID
~~~

Run the same Java subscriber with the new subscription ID and pin **one region** for all subscribers:

~~~bash
export PUBSUB_ENDPOINT="asia-southeast1-pubsub.googleapis.com:443"

mvn -q exec:java \
  -Dexec.mainClass=lab.pubsub.ConsumeOrder \
  -Dexec.args="PROJECT_ID orders-worker-exactly-lab"
~~~

**Guarantee scope:** exactly-once applies only to **pull/StreamingPull** with subscribers connecting in the **same region**. Legitimate redeliveries can still occur on NACK or deadline expiration; stale ACK IDs may be rejected. Exactly-once does **not** support Pub/Sub push subscriptions to Cloud Run HTTP services and does **not** stop publishers from publishing two differently-ID'd messages for the same business event.

**Warning when using two subscriptions on the same topic:** each subscription has independent delivery state. Running **two Java consumers writing to the same tables** will cause the second consumer to log `DUPLICATE_SKIPPED`; that is expected end-to-end dedupe behavior, not a subscription bug. To benchmark throughput/ACK semantics separately, use independent tables/data or clean up the lab carefully.

## 11. Failure scenarios requiring distinct handling

| Scenario | Correct outcome | What NOT to do |
| --- | --- | --- |
| Database timeout before COMMIT | Rollback; NACK/allow retry | ACK before DB finishes |
| Commit succeeded yet ACK future fails | Log uncertain ACK; redelivery uses marker | Delete marker or re-run business effect |
| Two publishes with same `eventId` | One row; second message skipped | Dedupe by `messageId` alone |
| Payload missing `eventId` | Quarantine/DLQ, alert event source | NACK infinitely without limit |
| Same `eventId`, different `orderId` | Reject and investigate conflict | Silently drop anomalous payload |
| Subscriber lacks permission | Fix IAM, then retry | Grant project-wide Editor |
| Prolonged database outage | Alert backlog/oldest age, throttle receive | Scale workers infinitely |
| Scale Pods from 1 to 10 | Unique index still prevents duplicates | Rely on local Java `HashSet` |
| Pub/Sub messages replayed via `seek` | Dedupe relies on marker retention/business rules | Assume old ACKs block all replays |
| External email/payment API beyond DB | Outbox/idempotency key/reconciliation | Claim JDBC transaction wraps external APIs |

### 11.1. Note on publisher-side outbox

If Orders API updates an order to `PAID` in Cloud SQL and crashes **before publishing**, the event can be lost. The **transactional outbox** pattern writes the order change and an outbox event row in the same transaction, then a relay publishes with a stable `eventId`. The relay may republish if it loses the response; the idempotent consumer in this lesson handles that case.

~~~mermaid
flowchart LR
    TX["DB transaction: order PAID + outbox row"]
    TX --> RELAY["Publisher relay<br/>retry with same eventId"]
    RELAY --> PUB["Pub/Sub"]
    PUB --> INBOX["Consumer DB transaction<br/>unique processed_events"]
    INBOX --> TASK["One shipping task"]
~~~

## 12. Concurrency and tuning for GKE/VM deployments

This example opens **one JDBC connection per message** to keep the transaction clear. Production should use a bounded connection pool (such as HikariCP) with validation and timeouts so autoscaling does not exhaust Cloud SQL connections.

Some Subscriber Builder settings you can tune:

~~~java
// Optional snippet while building the Subscriber.
import com.google.api.gax.batching.FlowControlSettings;

FlowControlSettings flow = FlowControlSettings.newBuilder()
    .setMaxOutstandingElementCount(100L)
    .setMaxOutstandingRequestBytes(10L * 1024 * 1024)
    .build();

Subscriber subscriber = Subscriber.newBuilder(sub, receiver)
    .setFlowControlSettings(flow)
    .build();
~~~

**This replaces part of the builder inside the class**—do not paste it as a third Java class. To set both `PUBSUB_ENDPOINT` and flow control, chain **both setters on the same builder** and call `build()` once.

| Parameter | What to balance |
| --- | --- |
| `maxOutstandingElementCount/Bytes` | Caps in-flight messages, preventing memory/DB overload |
| ACK deadline/lease extension | Reduces redeliveries when valid processing takes longer |
| Workers/Pod replicas | Processing capacity vs. connection pool and quotas |
| Batch sizes/publisher flow control | Throughput vs. latency, memory, and publish retries |
| Retry policy / dead-letter topic | Prevents poison messages from stalling the subscription |
| Exactly-once | Trades extra coordination/latency for confirmed ACK semantics |

**Never treat scale-out as a universal cure for backlogs.** If the bottleneck is the Cloud SQL connection pool, adding Pods can increase timeouts, NACKs, and cost.

## 13. Monitoring the right signals and cost

Track in **Cloud Monitoring** and logs:

| Signal | Interpretation |
| --- | --- |
| `subscription/num_undelivered_messages` | Pending backlog |
| `subscription/oldest_unacked_message_age` | Lag of the oldest unacked message |
| `subscription/expired_ack_deadlines_count` | Processing or lease management issues |
| `subscription/exactly_once_warning_count` | ACK/ModifyAckDeadline warnings; does not prove duplicates |
| Counts of `CREATED` vs. `DUPLICATE_SKIPPED` logs | Measures new work vs. dedupe hits |
| `processed_events` count / `shipping_tasks` count | Proof of accurate business effects |
| JDBC connection errors, transaction latency | Cloud SQL health and downstream limits |
| Pub/Sub data volume, retention, retries, and egress | Delivery, storage, and network costs |

**Never log raw payloads containing PII, tokens, payment data, or `DB_PASSWORD`.** In production, structured logs should carry verified `eventId`, `messageId`, service/instance, error code, and trace/correlation ID; ensure metrics never use `eventId` as an unbounded-cardinality label.

## 14. Security and correctness beyond the lab

- **IAM:** Publisher and subscriber use distinct service identities; grant `pubsub.publisher` or `pubsub.subscriber` only on required resources.
- **Auth:** ADC locally, Workload Identity Federation for GKE or VM service accounts in production; never hardcode service-account keys.
- **Cloud SQL:** private connectivity/TLS, least-privilege DB roles, bounded pools/timeouts, and controlled migrations.
- **Schema:** versioned payloads; validate types, `eventId`/`orderId`, source authorization, and business state transitions.
- **Exactly-once:** guarantees delivery per Pub/Sub message ID/region, does not cover DB + Pub/Sub + email atomically.
- **Durable dedupe:** retain markers long enough for retention, publisher retries, seek/replay, and business requirements.
- **Observability:** alerts for backlog, age, timeouts, DLQ, transaction failures, and row-count mismatches.
- **Cost:** Cloud Billing budget alerts, sensible subscription retention, bounded workers, no infinite retries.

## 15. Lab troubleshooting

| Symptom | Check |
| --- | --- |
| `NOT_FOUND` topic/subscription | Project ID, topic/subscription name, regional endpoint |
| `PERMISSION_DENIED` Pub/Sub | ADC principal and roles on topic/subscription |
| `JDBC_URL` missing | Were variables set in the **subscriber terminal**? |
| `Connection refused` PostgreSQL | Container running, port 127.0.0.1, database/user/password |
| Publisher logs success, subscriber receives nothing | Subscription created before publish? right subscription? worker running? |
| Subscriber receives yet SQL has no row | Transaction exception, rollback, DB connection and permissions |
| Two Pub/Sub message IDs, yet only one SQL row | **Expected** when `eventId` is identical |
| Two SQL rows for the same event | Missing unique key/transaction or two different dedupe namespaces |
| `ACK outcome uncertain` | Inspect deadline/ACK ID/region; DB marker prevents duplicate effect |
| Continuous NACKs | Poison message, DB unreachable, DLQ/retry policy |
| Backlog grows after scale-out | DB pool, quotas, CPU/memory/flow control, ack deadlines |
| Java compile errors | JDK 21, Maven dependencies, package/class/file paths |

**Never "fix" issues by ACKing immediately upon receipt.** That risks losing business work if DB commit fails. When needing a pause, shut down consumers gracefully and inspect the backlog before replaying.

## 16. Hands-on exercises and self-check

**Exercise 1 — Two publishes, one task.** Run `PublishOrder` twice with `order-paid:LAB-1:v1`; run both count queries.

*Expected:* Pub/Sub assigns two different message IDs; PostgreSQL has only one marker and one shipping task.

**Exercise 2 — Same eventId with different payload.** Test the same `eventId` with a new `orderId` in an isolated lab environment.

*Explanation:* Consumer detects inconsistent key reuse and rolls back/NACKs; fix the publisher or quarantine.

**Exercise 3 — Publish a new event.** Change `eventId` to `order-paid:LAB-1:v2` while keeping the same `orderId`.

*Explanation:* This is a new event; current design creates a new task because deduplication is by `eventId`. If business rules allow only **one task per order**, add a unique constraint/business rule on `order_id` rather than assuming `eventId` dedupe suffices.

**Exercise 4 — Crash window.** In an isolated test environment with fault injection, stop the worker after COMMIT and before ACK.

*Expected:* Pub/Sub may redeliver; the marker prevents creating a second shipping task.

**Exercise 5 — Two subscribers.** Run two `ConsumeOrder` processes against the same subscription and database, and publish one event.

*Expected:* The unique constraint protects under concurrency; never two tasks for the same `eventId`.

**Question 6.** Why is `messageId` insufficient to deduplicate publisher retries?

*Answer:* Two publishes of the same event can receive two different `messageId` values.

**Question 7.** Why must ACK follow COMMIT?

*Answer:* ACKing before commit followed by a crash can lose work that Pub/Sub already considers finished.

**Question 8.** Does Pub/Sub exactly-once support push to a Cloud Run HTTP endpoint?

*Answer:* No. Only pull/StreamingPull under supported conditions.

**Question 9.** Does enabling exactly-once eliminate duplicates caused by a publisher resending an event?

*Answer:* No. You still need a stable `eventId` and consumer-side deduplication.

**Question 10.** Why avoid a static `HashSet` to store processed event IDs?

*Answer:* Not shared across instances and lost on restart; use a shared durable store.

**Question 11.** When the DB has COMMITted and the ACK future times out, should you immediately NACK to "re-run" business logic?

*Answer:* No. Keep the marker and log the uncertain outcome; if redelivery occurs, the consumer ACKs upon seeing the duplicate.

**Question 12.** Does a unique `eventId` guarantee at most one shipping task per order?

*Answer:* Not if one order can have multiple event IDs; enforce business invariants with dedicated constraints when required.

## 17. Pre-production checklist

- [ ] Business `eventId` is generated once and stays stable across publish retries.
- [ ] Publisher awaits publish results, applies retry/backoff, and uses an outbox if DB + publish must stay atomic.
- [ ] Subscriber validates payloads, runs transactions, and ACKs **after COMMIT**.
- [ ] Deduplication resides in the same DB as the side effect or uses an equivalent atomic design.
- [ ] Unique keys enforce **both event identity and business invariants**.
- [ ] If using exactly-once: pull/StreamingPull, compatible client, single region/endpoint, confirmed ACK.
- [ ] Timeouts, flow control, lease extensions, and max concurrent DB connections are bounded.
- [ ] Poison events, invalid payloads, and downstream outages have clear retry/DLQ paths.
- [ ] Tested duplicate publishes, crashes before/after COMMIT, and multiple replicas.
- [ ] Dashboards track backlog, expired ACK deadlines, retries, DB errors, and business row counts.
- [ ] Least-privilege IAM, ADC/WIF, TLS, secret management, and PII-free logging are enforced.
- [ ] Budgets, retention/cleanup policies, and replay/rollback runbooks are in place.

## 18. Lab cleanup and conclusion

After finishing and **confirming no other consumer/workload uses them**:

~~~bash
# Stop the Java subscriber first; delete lab resources individually.
gcloud pubsub subscriptions delete orders-worker-lab \
  --project=PROJECT_ID

# If you created the extra subscription in Section 10:
gcloud pubsub subscriptions delete orders-worker-exactly-lab \
  --project=PROJECT_ID

gcloud pubsub topics delete orders-events-lab \
  --project=PROJECT_ID

# If using the dedicated lab Docker PostgreSQL:
docker stop orders-pg-lab
~~~

These are **real deletion commands** that can discard message backlogs and lab data; never run them if resources are shared. Clean up IAM bindings, DB data, billing alerts, and artifacts per organization policy.

**Conclusion:** Pub/Sub reliably moves events between services, yet **delivery guarantees do not automatically become business transaction guarantees**. With Java publishers/subscribers, the reliable pattern is **publish with durable eventId → subscriber validates → unique dedupe + business update in transaction → COMMIT → ACK → monitor on retries**. Observing **two publishes, one shipping task** directly proves the system deduplicates within the required scope.

## Official references

- [Pub/Sub publish and receive messages with client libraries](https://cloud.google.com/pubsub/docs/publish-receive-messages-client-library)
- [Java sample: publish custom attributes](https://cloud.google.com/pubsub/docs/samples/pubsub-publish-custom-attributes)
- [Java sample: pull subscriber](https://cloud.google.com/pubsub/docs/samples/pubsub-quickstart-subscriber)
- [Exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Java sample: confirmed ACK](https://cloud.google.com/pubsub/docs/samples/pubsub-subscriber-exactly-once)
- [Subscriber best practices](https://cloud.google.com/pubsub/docs/subscribe-best-practices)
- [Troubleshoot pull subscriptions](https://cloud.google.com/pubsub/docs/pull-troubleshooting)
- [Retry policy](https://cloud.google.com/pubsub/docs/subscription-retry-policy)
- [Dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics)
- [Pub/Sub Monitoring](https://cloud.google.com/pubsub/docs/monitoring)
- [Cloud Java libraries BOM](https://cloud.google.com/java/docs/bom)
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing)
