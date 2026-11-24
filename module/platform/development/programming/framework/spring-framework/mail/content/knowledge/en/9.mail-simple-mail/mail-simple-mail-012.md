# Ensuring a Message Is Not Modified After Being Queued

In **Spring Framework Mail**, sending a text email can start very simply: create a `SimpleMailMessage`, set `From`, `To`, `Subject`, `Text`, and then call `mailSender.send(message)`. When email volume grows or the business logic should not wait for an SMTP response, applications usually move to a pattern of **putting send requests into a queue** for a worker to process later.

The critical point is that **`SimpleMailMessage` is a mutable object**. Calling `setTo(...)`, `setSubject(...)`, or `setText(...)` modifies the data of that very object. If a thread puts a reference to the object into a queue and then keeps modifying it, the worker may receive **content different from what was intended at enqueue time**.

For example: request A is queued to be sent to Alice, yet later a method reuses the object and changes `To` to Bob. When the worker picks up the message, the mail may be sent to Bob with Alice's subject or body. This is a bug that is both hard to reproduce due to concurrency and capable of exposing personal data.

The goal of this lesson is to identify the **data-freezing boundary**, design a stable mail-send request after enqueuing, and understand why a thread-safe queue or a plain copy constructor alone is not the complete solution.

## 1. Distinguishing message, send request, and queue

First, separate three concepts:

| Concept | Java representation | Role | Mutable? |
| --- | --- | --- | --- |
| **Mail object being composed** | `SimpleMailMessage` | Holds sender, recipient, subject, and text for sending via Spring Mail | **Yes**, via setters |
| **Accepted send request** | Application-defined `MailJob` or `EmailCommand` | Captures the data the worker must use, along with job ID and metadata | **Should be immutable** |
| **Queue** | `BlockingQueue`, broker, or outbox table | Transfers requests from producer to worker | Has its own sync/storage mechanism; does not make objects immutable |

A clear architecture usually looks like:

~~~mermaid
flowchart LR
    A["Business logic emits email"] --> B["Create immutable MailJob"]
    B --> C["Queue / Outbox"]
    C --> D["Worker receives MailJob"]
    D --> E["Create new SimpleMailMessage"]
    E --> F["MailSender.send"]
    F --> G["SMTP provider"]
~~~

**The key milestone is when enqueuing succeeds:** all data the system has accepted to send must have a stable representation. The worker may run immediately, a few seconds later, or after an application restart. Any change to email content in the meantime must be an **intentional business decision**, not the consequence of a Java reference being mutated.

## 2. Why putting `SimpleMailMessage` directly into a queue can be wrong

Suppose an application has an in-memory queue:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import org.springframework.mail.SimpleMailMessage;

BlockingQueue<SimpleMailMessage> queue = new LinkedBlockingQueue<>();

SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("no-reply@example.com");
message.setTo("alice@example.net");
message.setSubject("Alice account notice");
message.setText("Content specifically for Alice.");

queue.add(message);

// Producer keeps mutating the very object that was enqueued.
message.setTo("bob@example.net");
message.setSubject("Bob account notice");
~~~

`queue.add(message)` **puts a reference** to `message` into the in-memory queue; it does not make a deep copy of the object. Therefore, a worker taking that reference after the `setTo` line may see `bob@example.net` as the recipient.

~~~text
T0  Producer: message.to = Alice
T1  Producer: queue.add(message)      # Queue holds reference M
T2  Producer: message.to = Bob        # Still object M
T3  Worker:   queue.take() -> M
T4  Worker:   sender.send(M)          # May send to Bob
~~~

If the worker takes and uses the message before the producer mutates it, the result may instead be Alice. Because thread scheduling varies, the bug becomes **timing-dependent (a race condition)**.

### 2.1. A thread-safe queue does not mean a thread-safe message

`LinkedBlockingQueue` provides synchronized add/take operations and appropriate *happens-before* guarantees: changes made **before** putting an element into the queue will be visible to the worker when taking that element.

Yet this **does not forbid the producer from mutating the element after enqueuing**, nor does it make the setters on `SimpleMailMessage` safe for concurrent access. When two threads read/write the same mutable object without a dedicated synchronization protocol, visibility of values and combinations of fields become unpredictable.

In particular, a message can end up with "mixed" data: `To` from request B, `Subject` from request A, and `Text` from another update. Merely ensuring the queue is thread-safe is not enough.

### 2.2. `@Async` can suffer from the same problem

Example to avoid:

~~~java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("alice@example.net");
mail.setSubject("Notice for Alice");
mail.setText("Alice's content");

asyncMailService.sendLater(mail); // Execution may not have started yet.
mail.setTo("bob@example.net");   // Still mutates the same object.
~~~

An asynchronous call only defers work to another executor/thread; it does not turn the passed object into a snapshot on its own. Even without a message broker, **any asynchronous boundary** requires considering data ownership.

## 3. Three principles to prevent messages from changing after enqueuing

1. **Snapshot data before enqueuing.** Clearly determine the recipients, subject, body, and values that must stay unchanged for this send.
2. **Enqueue only an immutable payload or independently serialized data.** Never pass a reference to `SimpleMailMessage` or a mutable DTO that the producer still holds for editing.
3. **The worker builds a new message from the payload.** Only the worker owns the `SimpleMailMessage` created for sending; never share that object across multiple jobs or threads.

In Java, you can use a **`record` with genuinely immutable fields**. `String` and `UUID` are suitable immutable values; for recipient lists, copy the `List` instead of keeping an external mutable list directly.

### 3.1. A record does not make its inner fields immutable automatically

Unsafe example:

~~~java
record UnsafeMailJob(String[] recipients, String subject, String body) {}

String[] recipients = {"alice@example.net"};
UnsafeMailJob job = new UnsafeMailJob(recipients, "Hello", "Content");

recipients[0] = "bob@example.net";
// job.recipients()[0] has also changed!
~~~

A `record` prevents reassigning a component of the object after construction, yet **does not automatically copy arrays, mutable lists, or nested objects**. If a record holds a `String[]` reference, someone else can still mutate that array.

Likewise, a record containing a `Date`, `StringBuilder`, mutable `Map`, or a `MimeMessage` can still be modified from outside. Therefore, immutability must be evaluated **recursively for every field the worker will use**.

## 4. Designing an immutable payload for text emails

A clean approach is declaring `TextMailJob` as the **job data**, separate from Spring's mail-sending API:

~~~java
package com.example.mail.queue;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

public record TextMailJob(
        UUID jobId,
        String from,
        List<String> to,
        List<String> cc,
        List<String> bcc,
        String replyTo,
        String subject,
        String body) {

    public TextMailJob {
        Objects.requireNonNull(jobId, "jobId");
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(subject, "subject");
        Objects.requireNonNull(body, "body");

        to = List.copyOf(Objects.requireNonNull(to, "to"));
        cc = List.copyOf(Objects.requireNonNull(cc, "cc"));
        bcc = List.copyOf(Objects.requireNonNull(bcc, "bcc"));

        if (to.isEmpty()) {
            throw new IllegalArgumentException(
                    "Mail job must have at least one To recipient");
        }
    }
}
~~~

Design choices:

- `jobId` is the identity of the send request, used for storing state, logging, and preventing duplicate jobs for the same event.
- `from`, `replyTo`, `subject`, and `body` are strings already determined at enqueue time. `replyTo` can be `null` if that header is not needed.
- `to`, `cc`, and `bcc` are lists; `List.copyOf(...)` creates an unmodifiable list that rejects ordinary mutation operations and **does not retain later changes to the source list**.
- List elements are immutable `String`s, so copying the container suffices for this example. If elements were mutable objects, they would need to be copied or converted to another immutable type.
- The constructor performs basic validation to avoid enqueuing incomplete jobs. Permission checks, recipient policy, content length, and sensitive-data checks remain the application's responsibility.

**Why not use `String[]`?** When an array is returned from an accessor, callers can directly modify elements. With a list created via `List.copyOf`, the accessor returns a value that rejects `add`, `set`, or `remove`. This makes the record a stable snapshot for the current set of fields.

### 4.1. Snapshot data and then enqueue

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

BlockingQueue<TextMailJob> queue = new LinkedBlockingQueue<>();
List<String> recipients = new ArrayList<>(
        List.of("alice@example.net"));

TextMailJob job = new TextMailJob(
        UUID.randomUUID(),
        "no-reply@example.com",
        recipients,
        List.of(),
        List.of(),
        "support@example.com",
        "Confirmation for Alice",
        "Hello Alice, your account has been created."
);

queue.add(job);

// Mutate source list after enqueuing:
recipients.set(0, "bob@example.net");

// Payload in the queue still keeps Alice as the recipient.
System.out.println(job.to()); // [alice@example.net]
~~~

The producer can modify `recipients` without affecting data inside `job`. From `queue.add(job)` onward, there are no setters to alter the job's fields; the worker will receive a consistent request.

The example above uses an **in-memory queue to explain immutability**. `LinkedBlockingQueue` does not persist jobs across restarts, has no durable retry mechanism, does not launch workers on its own, and is insufficient as reliable mail infrastructure for every production application.

### 4.2. Building `SimpleMailMessage` inside the worker

The worker simply receives `TextMailJob`, creates a new message, and hands it to `JavaMailSender`:

~~~java
package com.example.mail.queue;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class TextMailWorker {
    private final JavaMailSender sender;

    public TextMailWorker(JavaMailSender sender) {
        this.sender = sender;
    }

    public void deliver(TextMailJob job) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom(job.from());
        mail.setTo(job.to().toArray(String[]::new));

        if (!job.cc().isEmpty()) {
            mail.setCc(job.cc().toArray(String[]::new));
        }
        if (!job.bcc().isEmpty()) {
            mail.setBcc(job.bcc().toArray(String[]::new));
        }
        if (job.replyTo() != null && !job.replyTo().isBlank()) {
            mail.setReplyTo(job.replyTo());
        }

        mail.setSubject(job.subject());
        mail.setText(job.body());
        sender.send(mail);
    }
}
~~~

Thus, the mutable `SimpleMailMessage` object exists only within the scope of **one worker execution**. The producer holds no reference to it. The worker does not keep and reuse the object for the next job. This simplifies controlling who is allowed to modify content right before sending.

In a system using a real queue, a callback or consumer calls `deliver(job)`. This code does not fetch jobs from a broker by itself and does not imply that Spring runs a worker automatically just because the class has `@Component`.

## 5. How does the copy constructor of `SimpleMailMessage` help?

Spring provides a way to create a message from another message:

~~~java
SimpleMailMessage template = new SimpleMailMessage();
template.setFrom("no-reply@example.com");
template.setReplyTo("support@example.com");
template.setSubject("Notification");

SimpleMailMessage message = new SimpleMailMessage(template);
message.setTo("alice@example.net");
message.setText("Content for Alice");
~~~

This is a useful way to **avoid directly mutating a shared template**, especially in applications creating many plain text emails that share `From` and `Reply-To`.

However, distinguish carefully:

- **The copy constructor** creates **a new `SimpleMailMessage`** with data from the source message at copy time.
- The copy **is still a mutable `SimpleMailMessage`**; code holding a reference to it can still call setters.
- If the copy is also put into a queue and the producer continues modifying that copy, the same risk appears.

Therefore, writing the following still does not guarantee a snapshot:

~~~java
SimpleMailMessage queuedMessage = new SimpleMailMessage(template);
queuedMessage.setTo("alice@example.net");
queue.add(queuedMessage);

queuedMessage.setTo("bob@example.net"); // Still mutates the object in the queue.
~~~

If a small project is forced to enqueue `SimpleMailMessage`, at minimum it must enforce an **ownership transfer**: the producer must not modify or read/write the object after enqueuing, the worker is the only place using it, and no other thread keeps a reference to mutate it. However, this convention is hard to enforce via Java types because the class still has setters. **An immutable payload or serialized data** provides a clearer, easier-to-maintain boundary.

## 6. Which values need to be "frozen" at enqueue time?

Not every piece of information in the sending process belongs to email content. To determine the right snapshot, classify them:

| Data | Example | Snapshot at enqueue? |
| --- | --- | --- |
| Recipients | `To`, `Cc`, `Bcc` | **Yes**, unless the business deliberately resolves recipients at send time |
| Subject | `Subject` | **Yes** if the request was accepted with a specific subject |
| Text content | `Body`, language, links | **Yes** if the message requested at that moment must stay intact |
| Sender addresses | `From`, `Reply-To` | Pick a clear policy: snapshot now or look up from config at send time |
| Business IDs | `orderId`, `userId`, `eventId` | **Yes** for tracing and preventing duplicate jobs |
| Template version | `welcome-v3` | **Yes** if the worker will render the template at another time |
| Request creation time | `createdAt` as `Instant` | Recommended for auditing and measuring queue wait time |
| SMTP host/port/credentials | `spring.mail.*` | **Do not put secrets in payload**; let sender layer read runtime config |
| Retry count and status | `attempts`, `PENDING`, `FAILED` | Manage in separate metadata/job state that can update over time |

Depending on requirements, there are two models:

**Model A — snapshot complete content:** the producer builds the final `subject` and `body` and then enqueues. The worker only constructs and sends. Fits the requirement "the message must keep the exact content from when it was queued."

**Model B — snapshot input data + template version:** the producer stores `templateId`, `templateVersion`, and immutable variables; the worker renders later. Fits when rendering must happen in the worker, yet requires ensuring that the template version, referenced resources, and variable data do not change unexpectedly.

For example, if you store only:

~~~json
{
  "userId": "U42",
  "templateName": "welcome"
}
~~~

and then the worker **reads the latest display name** from the database and uses the **current template** at send time, the mail content may differ from enqueue time. This may be a valid requirement in some domains, yet does not satisfy the condition of **preserving the message** if the content was approved beforehand.

### 6.1. With verification codes, expiring links, and time-sensitive data

A content snapshot does not mean the content remains valid when sent. For instance, a password reset email contains a link valid for 10 minutes, yet the queue gets stuck for 30 minutes. The worker might send the exact snapshotted content after the link has already expired.

The design should also store an expiration or pre-send check rule:

~~~text
jobId: ...
createdAt: 2026-11-12T08:00:00Z
expiresAt: 2026-11-12T08:10:00Z
subject: "Reset password"
body: "..."
~~~

Once expired, the worker can mark the job invalid per business policy instead of silently editing the link or swapping tokens on its own. If resending with a new token is requested, create a **new request** with a new identity and content.

### 6.2. Runtime configuration can still change legitimately

An enqueued message may be sent through SMTP provider A or B depending on configuration when the worker runs. Rotating the SMTP password or host is **not modifying mail content**, but changing the transport channel.

For `From`, decide clearly: if this address is part of the approved content, store it in the job. If the address must always follow the latest sender policy, the worker can read it from configuration, provided that rule is documented. Do not silently change policies after the system promised to preserve the message.

## 7. How do in-memory queues and durable queues differ?

### 7.1. Queue within the same JVM

~~~text
Producer thread          Shared JVM heap        Worker thread
     |                         |                      |
     |--- enqueue(job) ------->|                      |
     |                         |---- take(job) ------>|
~~~

`BlockingQueue<TextMailJob>` transfers data between threads in the same process. With an immutable job, data cannot be altered by mutating source lists after enqueuing. However:

- Unprocessed jobs can be **lost when the process stops**.
- There is no durable retry/ack mechanism unless you build one yourself.
- A job can be taken and fail to send; without persisted state, it is hard to know what must rerun.

Therefore, an in-memory queue fits illustrating concurrency principles or work the organization accepts losing on restart; do not use it by default for mandatory transactional emails.

### 7.2. Message brokers or queues with serialization

When sending data through a broker, applications usually convert the payload into **JSON, Avro, Protobuf, or a byte stream**. Normal serialization creates a data copy independent of the source object:

~~~text
Producer TextMailJob
       |
       v
Serialize to bytes
       |
       v
Broker stores/transfers bytes
       |
       v
Worker deserializes to TextMailJob
       |
       v
Create SimpleMailMessage and send
~~~

If the producer mutates an `ArrayList` after **serialization finishes and the broker accepted the bytes**, the sent bytes do not change. However, if the application still holds a mutable object and serialization actually happens **after** calling an async API, mutations before serialization can affect the payload. Understand the boundaries of your queue library, especially when producers use buffers, callbacks, batching, or async sends.

Thus, using an **immutable payload before calling publish** remains the safest and easiest-to-reason-about choice. The object deserialized in the worker should also be treated as read-only data; retry/status metadata should live in the job-management layer.

### 7.3. Outbox and business transactions

Example of an order-creation and confirmation-sending workflow:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT order ...
  INSERT email_outbox(
      job_id, order_id, payload_snapshot, status='PENDING'
  )
COMMIT
~~~

Instead of updating the order and publishing to a queue immediately in an operation with no shared transaction guarantee, a **transactional outbox** stores the send request in the same transaction as the business data. Afterward, a worker/relay reads the outbox and publishes the job or sends the email.

`payload_snapshot` should contain data determined at commit time (or a reference to an immutable content version). On retry, the worker reads the **same snapshot** instead of querying current mutable order data and accidentally sending different content.

An outbox reduces the chance of "order saved successfully yet mail request lost." It **does not by itself guarantee the email is sent exactly once**, because the SMTP handoff is an external system outside the database transaction.

## 8. Ensuring a message is not modified differs from preventing duplicate sends

Two independent problems:

| Problem | Example | Main mitigation |
| --- | --- | --- |
| **Message modified after enqueue** | Alice's job has To changed to Bob | Immutable payload, snapshot, clear data ownership |
| **Same message sent multiple times** | Worker sends then crashes before ack | Job ID, retry rules, processing state, and deduplication |

A durable queue typically implements **at-least-once delivery**: if processing confirmation is not received, the same job may be redelivered. For example:

~~~text
T1 Worker receives job-123
T2 SMTP returns 250: message accepted
T3 Worker crashes before marking job-123 completed
T4 Broker redelivers job-123
T5 Worker may send the message a second time
~~~

An immutable payload ensures both sends have identical data, yet **does not prevent two emails from being produced**. To reduce duplicate sends:

- Attach a stable **`jobId`** or business event ID right when creating the request.
- Prevent creating two jobs for the same event if business logic requires it (unique constraint/idempotency key).
- Manage `PENDING`, `PROCESSING`, `SUBMITTED`, `FAILED` states per job, along with attempt count and processing timestamps.
- If the provider supports an idempotency key or message status queries, use them according to the provider's contract.
- With plain SMTP, recognize that a timeout after sending data can leave an **unknown outcome**; never claim absolute exactly-once solely through locks or a database.

For important transactional mail, prioritize **reliability, traceability, and duplicate-send control** alongside payload immutability.

## 9. Relationship between immutable data and object ownership

In a multi-threaded system, you can apply the convention:

~~~text
Producer owns MutableBuilder
    |
    | validate + snapshot
    v
Producer/Queue owns immutable MailJob
    |
    | handoff
    v
Worker owns newly constructed SimpleMailMessage
    |
    | send
    v
Sender / SMTP provider
~~~

At each boundary:

1. **The producer's mutable builder** can be edited while the request has not been accepted.
2. **MailJob** becomes fixed information upon enqueuing; there are no setters or mutable references allowing edits.
3. **The worker** creates a dedicated `SimpleMailMessage`, optionally fills in fields per finalized policy, and calls `send`.
4. After calling `send`, the worker does not edit or share `SimpleMailMessage` with another job.

This rule avoids "shared ownership" of one message among producer, queue, and worker. In Java, it is easier to enforce than placing `synchronized` everywhere around setters, especially when tasks span multiple machines.

## 10. What about attachments or HTML?

In the **Simple mail** section, we mostly use `SimpleMailMessage` with `String`. If later switching to `MimeMessage` to send HTML, file attachments, or inline images, mutable-data risks are even broader:

- `MimeMessage` and `MimeBodyPart` can be edited after creation.
- An attached `byte[]` can be mutated if the job retains the original reference.
- An `InputStream` can be consumed or closed before the worker reads it.
- A `File` or path pointing to a file can change contents before the worker sends.
- An HTML template can be updated between enqueue and dequeue times.

For attachments that must remain unchanged, pick one of these controls:

- Capture the file's **bytes** and defensively copy the array, with an appropriate size limit.
- Store in **object storage with an immutable key/version**, and have the worker fetch that exact version.
- Store a **content hash** to detect unintended changes to attached data.
- Never keep only a path to a temporary file that another process could overwrite or delete.

For example, a record with only `byte[]` such as:

~~~java
record AttachmentJob(byte[] pdfBytes) {}
~~~

is **not yet immutable**, because callers outside can modify `pdfBytes`. If an array is required, copy it in the constructor and when returning to callers, or use an appropriate immutable wrapper:

~~~java
public final class PdfSnapshot {
    private final byte[] bytes;

    public PdfSnapshot(byte[] source) {
        this.bytes = source.clone();
    }

    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

For text messages, choosing immutable `String` and `List<String>` makes the problem significantly simpler.

## 11. Enqueued data still needs sensitive-information protection

An immutable payload may contain personal data. If a queue or outbox stores the whole body, that data may outlive the original HTTP request lifecycle.

Consider:

- **Authorization** for producers, consumers, and queue administrators.
- **Encryption in transit and at rest** per broker/database capabilities and data requirements.
- **Retention** of queues, dead-letter queues, outboxes, and backups.
- **Logs** recording only job ID, message type, status, or error codes whenever possible; avoid printing raw `body`, tokens, or full recipient lists.
- **Never put SMTP passwords/API keys into job payloads**; workers obtain credentials from runtime config/secret managers.
- **Accessing user data** for legitimate mail-sending purposes, restricting endpoints that allow arbitrary email sending.

Storing snapshots keeps messages intact, yet does not mean storing OTP codes or password reset tokens forever. For expiring data, combine expirations with deleting/redacting content once no longer needed.

## 12. Testing the idea "do not modify after enqueuing"

A small unit test can verify that the payload constructor **does not retain an external mutable list**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class TextMailJobTest {
    @Test
    void recipientsRemainStableWhenInputListChanges() {
        List<String> mutableRecipients =
                new ArrayList<>(List.of("alice@example.net"));

        TextMailJob job = new TextMailJob(
                UUID.randomUUID(),
                "no-reply@example.com",
                mutableRecipients,
                List.of(),
                List.of(),
                null,
                "Notice for Alice",
                "Content for Alice"
        );

        // Mutate the data used to create the job.
        mutableRecipients.set(0, "bob@example.net");

        assertEquals("alice@example.net", job.to().get(0));
        assertThrows(
                UnsupportedOperationException.class,
                () -> job.to().set(0, "eve@example.net"));
    }
}
~~~

The test above targets **snapshot preservation**, without trying to send real email. It illustrates what must be verified in the design: the created job does not change when the producer edits the source list, and others cannot modify the list through the accessor.

### 12.1. Verifying at the worker boundary

For the mail service, you can use a mock `JavaMailSender` to capture the `SimpleMailMessage` passed into `send`, and compare `To`, `Subject`, and `Text` against the job data. The fields to verify are the ones frozen at enqueue time.

An integration test can run the worker with a simulated SMTP server such as Mailpit or GreenMail and inspect the received message. If there is a message broker/outbox, observe the **serialized payload before and after the producer mutates source data**. These are boundary tests and require neither production SMTP nor real recipients.

### 12.2. Edge cases to consider

| Situation | What should happen |
| --- | --- |
| Producer mutates `ArrayList` after enqueue | Job in queue keeps the old recipient intact |
| Producer changes user values in database | Worker uses finalized snapshot if business requires preserving it |
| Two workers process two jobs concurrently | Each worker creates its own `SimpleMailMessage` |
| Job retry after temporary failure | Reuses finalized payload content unless business creates a new job |
| Job expired | Worker drops or marks failed per policy without silently altering tokens |
| New template version deployed | Old job uses pre-rendered content or pinned template version |
| SMTP credentials rotated | Worker reads new configured secret; does not alter job content |
| Service restarts with RAM queue | Unprocessed jobs may be lost; use a durable queue if needed |

## 13. Common mistakes

| Mistake | Consequence | Appropriate design |
| --- | --- | --- |
| Enqueuing `SimpleMailMessage` directly and continuing to call setters | Message in queue can change content | Snapshot into an immutable job before enqueuing |
| Assuming `BlockingQueue` copies objects | In-memory queue holds references only | Copy data or build an immutable payload |
| Using a `record` containing a mutable `String[]` | Array can be mutated through reference | Use `List.copyOf` with `String` or defensive copying |
| Calling `new SimpleMailMessage(old)` and treating the copy as permanently immutable | The copy still has setters | Do not share the copy after enqueuing; better to enqueue an immutable job |
| Sharing one `SimpleMailMessage` across all jobs | Request data can overwrite each other | Worker creates a new message on each send |
| Storing only user ID and reading all fields at send time | Name, email, content can change with the database | Choose and document snapshot policy explicitly |
| Storing template ID without version | After deploy, queued mail may change content | Render early or pin template version |
| Storing temp file path and sending later | Attachment may be overwritten/deleted | Snapshot file or use versioned storage |
| Treating an immutable queue as an exactly-once guarantee | Job can still send duplicates after crash/retry | Job ID, status, and idempotency mechanisms |
| Putting SMTP password into payload | Secret gets replicated across broker, logs, and backups | Secrets stay only in runtime configuration |

## 14. Combined scenario: sending order notifications through a queue

Suppose a user places an order and the system needs to send a confirmation email. Data when the order completes:

~~~text
Order ID:  A-2048
Email:     alice@example.net
Subject:   Order A-2048 has been confirmed
Text:      Hello Alice, order A-2048 has been recorded.
~~~

A design following the snapshot principle:

1. **Order service** confirms the business work and obtains the final recipient, subject, and body at event time.
2. **Mail producer** validates inputs and builds a `TextMailJob` with `jobId`, copied recipient list, and `String` content.
3. **Queue/outbox** receives the immutable payload or its serialized form, detached from mutable producer objects.
4. If the application updates Alice's display name to another value, **the enqueued job does not change**.
5. **Worker** picks up the job, builds a new `SimpleMailMessage` from the snapshot, and calls `JavaMailSender.send(...)`.
6. **Job processor** records status and handles retries when needed. If SMTP result is unknown due to connection loss, the system evaluates duplicate-send risk before retrying.

Here is the difference between the two representations:

~~~text
Unsafe:
  Queue<SimpleMailMessage> --> shared mutable object --> send

More stable:
  Queue<immutable TextMailJob> --> worker builds new message --> send
~~~

This principle does not apply only to email. Any asynchronous system receiving a mutable object from a producer must define the **snapshot moment**, **who owns the data**, and **which changes are allowed after work has been accepted**.

With Spring Framework Mail, the clearest choice for **Simple mail** is: **put the message content into an immutable job, keep that job in the queue, and create `SimpleMailMessage` only in the worker right before sending**. This design prevents a major cause of sending to the wrong recipient or with the wrong content, while making it easier to add retries, outbox, and status tracking without relying on a shared mutable Java object.

### References

- **Spring Framework API — `SimpleMailMessage`:** setters, copy constructor, and role of the text-based mail object.
- **Spring Framework API — `MailSender` / `JavaMailSender`:** interface for sending messages with Spring Mail.
- **Java Platform API — `BlockingQueue` and `LinkedBlockingQueue`:** element enqueue/dequeue mechanisms and thread synchronization guarantees.
- **Java Platform API — Records, `List.copyOf`, and `String`:** building snapshot data with immutable fields.
- **Spring Framework — Task Execution and Scheduling:** asynchronous boundaries via executors/`@Async`.
- **Transactional Outbox Architectural Pattern:** persisting events/send requests in the same business transaction for durable processing.
