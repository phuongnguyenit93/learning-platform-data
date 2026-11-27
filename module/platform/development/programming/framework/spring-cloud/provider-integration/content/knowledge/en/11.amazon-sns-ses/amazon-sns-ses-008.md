# Choosing SNS, SQS, or SES by Communication Purpose

## 1. Problem Statement and Learning Objectives

An e-commerce application written in Spring Boot needs to perform three tasks after a customer places an order:

- Emit an **ORDER_CREATED** event to inventory, analytics, and customer care services.
- Store the confirmation-email job for a worker to process when capacity is available.
- Send transactional emails with HTML bodies, templates, attachments, and bounce/complaint tracking.

**Amazon Simple Notification Service (SNS)**, **Amazon Simple Queue Service (SQS)**, and **Amazon Simple Email Service (SES)** can all appear in this system, yet they solve different problems:

- **SNS** distributes notifications from a publisher to one or more subscribers under the publish/subscribe model.
- **SQS** stores messages in a queue so one or more consumers actively pull and process them asynchronously.
- **SES** sends emails to recipients over AWS's email infrastructure, supporting sender identities, domain authentication, and delivery feedback.

This lesson belongs to the **Amazon SNS and SES** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via their respective Spring Cloud libraries; learners must know how to select services, configure identity/permissions, protect secrets, test, and evaluate trade-offs across providers.

After this lesson, you will be able to:

1. Choose SNS, SQS, or SES according to communication purpose.
2. Distinguish broadcast/fan-out, work queues, email delivery, and operational guarantees.
3. Design architectures combining SNS + SQS + SES instead of forcing one service to handle every job.
4. Integrate publishers, queue consumers, and mail senders in Spring Boot.
5. Determine where to place retries, DLQs, idempotency, IAM policies, and observability.
6. Avoid anti-patterns such as using SNS as a job queue, using SES as a message broker, or sending emails synchronously inside the order transaction.

## 2. The Nature of SNS, SQS, and SES

~~~mermaid
flowchart TD
    APP["Spring Boot application"]
    SNS(("Amazon SNS<br/>Publish / Subscribe"))
    SQS["Amazon SQS<br/>Durable queue"]
    SES(("Amazon SES<br/>Email delivery"))
    SYS["Services / subscribers"]
    WORKER["Queue workers"]
    MAIL["Recipient mailboxes"]

    APP -->|"Publish event"| SNS
    SNS -->|"Push notification"| SYS
    SNS -->|"Fan-out"| SQS
    APP -->|"Send work item"| SQS
    SQS -->|"Poll / consume"| WORKER
    WORKER -->|"Send email"| SES
    SES -->|"SMTP delivery"| MAIL
~~~

| Property | **SNS** | **SQS** | **SES** |
| --- | --- | --- | --- |
| Primary purpose | Distribute notifications | Buffer and queue work items | Send emails |
| Model | Publisher → topic → subscribers | Producer → queue → consumers | Sender → SES → mail servers |
| Reception mechanism | SNS actively delivers to endpoints (push) | Consumers actively fetch messages (poll/pull; optionally assisted by Lambda event source mapping) | Recipients receive via email systems |
| Consumer cardinality | One topic has multiple independent subscriptions | Multiple workers share one queue as competing consumers | Multiple email recipients, supporting To/Cc/Bcc |
| Retention | Not long-term storage for consumers to replay at will | Retains messages for the retention period, up to 14 days | Not an application email-task queue |
| Filtering | Filter policies on subscriptions | Consumers decide after reading; can split into separate queues/logic | No SNS-style business message routing |
| Typical workloads | Event publishing, fan-out, alerts | Buffering, load leveling, job retries | Transactional email, consent-based marketing email |
| Error handling | Delivery retries per subscription; optional subscription DLQ | Visibility timeout, redrive policy, SQS DLQ | Bounces, complaints, rejects, delivery delays, and suppression |

**A quick rule of thumb:**

- Need to **broadcast one notification to multiple systems** → think **SNS**.
- Need to **hold a job for workers to process when ready** → think **SQS**.
- Need to **send emails to humans** → think **SES**.

These services can be combined: SNS broadcasts events, SQS holds independent job backlogs for each consumer group, and workers call SES to send emails. This is usually the cleanest design for separation of concerns and operability.

## 3. When to Choose SNS?

### 3.1. SNS as the Notification Distribution Layer

A publisher sends a message to a **topic**. SNS evaluates subscriptions and forwards the message to matching endpoints. One topic can have many subscriptions, such as an SQS queue for email workers, an SQS queue for analytics, Lambda for cache invalidation, an HTTPS endpoint for a partner webhook, or email/SMS for simple alerts to confirmed/configured endpoints.

SNS fits when the publisher should not know the recipient list and new subscribers must be added without changing event-publishing logic.

~~~mermaid
flowchart LR
    P["Order Service"] --> T(("SNS topic<br/>order-events"))
    T --> Q1["SQS<br/>inventory-jobs"]
    T --> Q2["SQS<br/>analytics-jobs"]
    T --> Q3["SQS<br/>notification-jobs"]
    T --> L["Lambda<br/>cache invalidation"]
~~~

### 3.2. Characteristics to Consider

**SNS Standard** fits high throughput and independent notifications. Design consumers to handle **at-least-once delivery**, where messages may duplicate and ordering is not strictly guaranteed.

**SNS FIFO** fits when ordering per message group and deduplication within supported service bounds are needed. On an SQS FIFO branch, set **MessageGroupId** by aggregate (e.g., orderId) and a stable **MessageDeduplicationId**. FIFO does not eliminate the need for idempotency in business side effects.

**Subscription filter policies** let each subscriber receive only the message types it needs. For example, the email queue receives ORDER_CREATED while the refund queue receives ORDER_CANCELLED. Filters reduce unnecessary processing but do not replace authorization.

### 3.3. When Not to Use SNS Alone

Do not use SNS as a job store expecting workers to pause for hours and replay messages at will. SNS has protocol retries and subscription DLQs, yet lacks SQS's retention/visibility/consumer acknowledgment semantics. If endpoints are workers needing rate control and reprocessing, combine **SNS → SQS**.

Direct SNS email subscriptions suit simple notifications, such as operational alerts. They do not replace a transactional email service requiring templates, MIME, identity management, suppression, bounces, and complaints. For those requirements, use **SES**.

## 4. When to Choose SQS?

### 4.1. SQS as a Work Queue

A producer sends a message to a queue. A worker retrieves the message, processes it, and deletes it upon completion. If the worker crashes or fails to delete it, the message can reappear after the **visibility timeout**.

~~~mermaid
sequenceDiagram
    participant P as "Spring Boot Producer"
    participant Q as "SQS queue"
    participant W1 as "Worker A"
    participant W2 as "Worker B"

    P->>Q: SendMessage(job)
    W1->>Q: ReceiveMessage
    Q-->>W1: Job + receipt handle
    Note over W1: Process job
    W1->>Q: DeleteMessage
    W2->>Q: ReceiveMessage (another job)
~~~

Multiple workers reading the same queue follow the **competing consumers** pattern: each message is normally delivered to one consumer at a time rather than broadcast to every worker. SQS Standard can still deliver duplicates, so consumers must be idempotent.

### 4.2. Why Queues Help Level Load

Suppose the system receives 500 orders in one minute, while the email service can only send 100 emails/minute. Calling SES synchronously inside the order request lets email latency and errors degrade the ordering flow.

With SQS:

1. The API records the order and enqueues an email job.
2. Workers pull jobs according to available capacity.
3. When SES throttles or hits transient errors, workers retry under a bounded strategy.
4. Messages failing past the max receive count move to an **SQS DLQ**.
5. The ordering API does not block waiting for email completion.

SQS Standard retains messages for up to **14 days**; configure retention, visibility timeout, long polling, and redrive policies according to job SLAs. Visibility timeout must cover normal processing duration; if a job runs long, workers can extend it via **ChangeMessageVisibility**.

### 4.3. Standard vs. FIFO

| Criterion | **SQS Standard** | **SQS FIFO** |
| --- | --- | --- |
| Ordering | Best effort; may arrive out of order | Ordered per MessageGroupId |
| Delivery | At-least-once; duplicates possible | Deduplication within bounded window, ordered per group |
| Throughput | High throughput, flexible scaling | Bounded and follows configured throughput modes |
| Use when | Independent tasks, idempotent consumers | Operations on the same aggregate must be sequential |

FIFO's **exactly-once processing** must be understood accurately: the service supports deduplication and receive/delete semantics within documented bounds, yet it does not form an atomic transaction with your database, SES, or external APIs. If a worker calls SES and crashes before deleting the message, the job can run again. Use idempotency keys, status tables, or an outbox to prevent duplicate emails.

### 4.4. When Not to Use SQS Alone

If three independent systems each need to receive **every** event, sharing a single queue among three consumers causes them to compete instead of broadcasting. There are two alternatives:

- Create three separate queues and have the publisher send to each queue, which forces the publisher to know all queues and manage fan-out itself.
- Use an **SNS topic → three SQS queues**, letting SNS handle distribution while each queue holds an independent copy for its consumer.

If the goal is purely sending email to customers, SQS only holds the tasks; it does not deliver emails. Workers must call **SES** or another email provider.

## 5. When to Choose SES?

### 5.1. SES Is an Email Service, Not a Broker

SES specializes in email: domain/email identity verification, DKIM, SMTP/API sending, configuration sets, event publishing, bounces, complaints, suppression, and quotas. It does not offer queue semantics for applications to poll and acknowledge tasks.

Suitable scenarios: order confirmation emails and receipts; password resets, OTPs, and security emails; account status notifications; marketing emails with consent, unsubscribe handling, and proper reputation management; MIME/HTML, templates, and attachments per business needs.

### 5.2. Prerequisites for Sending Email

The application needs a verified identity in the exact SES region, an authorized From address, IAM permissions for the SES API or SES SMTP credentials for SMTP, account permission to send to target recipients (sandbox/production), sufficient quota/rate limits, and workflows for bounces, complaints, and suppression.

The **SES API** integrates with Spring Cloud AWS via **MailSender/JavaMailSender** or directly via the SDK. **SES SMTP** can use Spring Boot Mail. Authentication differs: the API uses the AWS credentials provider chain/IAM roles; SMTP uses dedicated SES SMTP username/password credentials.

### 5.3. Send Success Is Not Delivery

A successful send call usually indicates only that SES accepted the request. Afterward, the destination mail server may accept, reject, or delay the message, or the recipient may report spam. The application must monitor events:

| Event | Meaning |
| --- | --- |
| **Send** | SES recorded the send request |
| **Delivery** | Destination mail server accepted the email |
| **Bounce** | Email could not be delivered to the recipient |
| **Complaint** | Recipient reported spam |
| **Reject** | SES rejected the message |
| **DeliveryDelay** | Delivery delayed due to a temporary issue |

**Delivery does not prove the recipient read the message or that it landed in the primary inbox.** Bounces/complaints must update suppression and preferences; hard bounces must not be retried like transient network errors.

## 6. Choosing a Service by Scenario

| Requirement | Choice | Reason |
| --- | --- | --- |
| One event must notify multiple independent services | **SNS** | One topic with multiple subscriptions |
| One job must be stored for later worker processing | **SQS** | Retention, visibility timeout, ack/delete, DLQ |
| Multiple services need a copy of the event and independent processing | **SNS + one SQS queue per subscriber** | Fan-out plus isolated per-consumer buffering |
| Send confirmation emails to customers | **SES** | Email identities, MIME content, delivery feedback |
| Send emails without blocking the ordering API | **SQS + worker + SES** | Decouple order intake from email sending |
| Capture email bounces/complaints back into the system | **SES + SNS/EventBridge + SQS** | SES emits feedback events; queue lets workers process them |
| Send simple operational alerts via email | **SNS email subscription** may suffice | Quick endpoint confirmation; limited content/features |
| Worker must process messages in order per order | **SQS FIFO**, optionally paired with SNS FIFO | MessageGroupId and deduplication |
| Three workers must all process every message | **SNS + three SQS queues** | A single shared queue creates competing consumers, not broadcast |

### 6.1. Decision Tree

~~~mermaid
flowchart TD
    A{"Who are you communicating with?"}
    A -->|"Email recipients"| E["SES"]
    A -->|"One or more systems"| B{"One job or notify multiple consumers?"}
    B -->|"One worker pool sharing work"| Q["SQS"]
    B -->|"Multiple independent consumers"| N["SNS topic"]
    N --> C{"Do consumers need independent buffering/retries?"}
    C -->|"Yes"| F["SNS → one SQS queue per consumer"]
    C -->|"No"| D["SNS → appropriate endpoint"]
    E --> G{"Send immediately or buffer?"}
    G -->|"Send immediately, low volume"| H["Spring Mail → SES"]
    G -->|"Async / rate control"| I["SQS → mail worker → SES"]
~~~

The decision tree is a starting guide. The final choice also depends on delivery guarantees, throughput, ordering, cost, retention duration, endpoint types, security, and operational capacity.

## 7. Common Combined Architectures

### 7.1. Work Queue: SQS for a Pool of Workers

~~~mermaid
flowchart LR
    API["Order API"] -->|"SendMessage"| Q["SQS<br/>invoice-jobs"]
    Q --> W1["Invoice worker A"]
    Q --> W2["Invoice worker B"]
    W1 --> DB[("Database")]
    W2 --> DB
~~~

Used when each job should be processed by one worker in the pool. Multiple workers polling the queue increase throughput; messages are not broadcast to every worker. If a worker fails, visibility timeout and the redrive policy govern retries and DLQ routing.

### 7.2. Fan-Out: SNS + SQS per Consumer

~~~mermaid
flowchart LR
    P["Order Service"] --> T(("SNS<br/>order-events"))
    T --> Q1["SQS<br/>inventory"]
    T --> Q2["SQS<br/>analytics"]
    T --> Q3["SQS<br/>email-jobs"]
    Q1 --> W1["Inventory worker"]
    Q2 --> W2["Analytics worker"]
    Q3 --> W3["Email worker"]
~~~

Used when each service needs to receive and process independently. If analytics goes down, the analytics queue retains messages within its retention window while the inventory worker continues processing its own queue. The publisher does not call each worker individually.

### 7.3. Sending Transactional Emails via Queue

~~~mermaid
flowchart LR
    O["Order Service"] -->|"Create notification job"| Q["SQS<br/>email-jobs"]
    Q --> W["Spring Boot<br/>Mail Worker"]
    W --> SES(("Amazon SES"))
    SES --> M["Customer mailbox"]
    SES -->|"Bounce / Complaint"| FB(("SNS / EventBridge"))
    FB --> FQ["SQS<br/>email-feedback"]
    FQ --> FW["Feedback worker"]
    FW --> DB[("Suppression / consent")]
~~~

This is the standard pattern for transactional emails:

1. Order Service creates a notification job and persists state in a DB/outbox.
2. Email worker pulls the job from SQS, checks idempotency, and sends via SES.
3. Worker updates state from the API result, recording SES MessageId if available.
4. SES emits delivery/bounce/complaint events to the configured destination.
5. Feedback worker updates status, suppression, or preferences.
6. DLQs and dashboards highlight jobs that cannot be processed.

If an email must be sent after an order commits, use a **transactional outbox** to record the event in the same transaction. Avoid calling SES inside a database transaction; network latency or throttling can prolong transactions and degrade checkout experience.

### 7.4. SNS Direct to Email vs. SES?

| Need | SNS Email Subscription | SES |
| --- | --- | --- |
| Simple alerts to a confirmed group of recipients | Suitable | Usable, though likely over-configured |
| Order-personalized transactional emails | Limited | Suitable |
| HTML templates, MIME, attachments | Not the primary goal | Suitable |
| Domain identity, DKIM, custom MAIL FROM | Not a dedicated email suite | Yes |
| Email-level bounce/complaint/suppression tracking | Does not replace SES feedback | Yes |
| Broadcast text notifications to an email endpoint | Suitable | Can build a worker if email logic is needed |

Do not treat SNS email subscriptions as a substitute for SES for all application emails. SNS suits simple notification content; SES suits cases where email is an official product feature.

## 8. Spring Boot Integration: Examples by Role

Examples use **Spring Cloud AWS 3.x** (**io.awspring.cloud** package) and **Spring Boot 3**. Pick a BOM version compatible with your Spring Boot version; do not mix legacy-generation APIs.

### 8.1. Publisher: Spring Boot → SNS

Dependencies:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
}
~~~

Configuration:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}
app:
  sns:
    order-topic-arn: ${ORDER_EVENTS_TOPIC_ARN}
~~~

Example POJO publisher:

~~~java
import io.awspring.cloud.sns.core.SnsTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final SnsTemplate snsTemplate;
    private final String topicArn;

    public OrderEventPublisher(
            SnsTemplate snsTemplate,
            @Value("${app.sns.order-topic-arn}") String topicArn) {
        this.snsTemplate = snsTemplate;
        this.topicArn = topicArn;
    }

    public void publish(OrderCreated event) {
        snsTemplate.sendNotification(topicArn, event, "Order created");
    }

    public record OrderCreated(
            String eventId, String orderId, String eventType) {}
}
~~~

The application needs an IAM role with **sns:Publish** on the topic ARN. The publisher does not need **sqs:SendMessage** if it only publishes to SNS. Topic subscriptions and queue policies are managed in infrastructure.

### 8.2. Consumer: Spring Boot ← SQS

Dependencies:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sqs")
}
~~~

Listener:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class EmailJobListener {
    private final EmailJobProcessor processor;

    public EmailJobListener(EmailJobProcessor processor) {
        this.processor = processor;
    }

    @SqsListener("email-jobs")
    public void receive(EmailJob job) {
        processor.processIdempotently(job);
    }
}
~~~

**EmailJobProcessor** must process idempotently by eventId/job ID. With the container's appropriate default acknowledgement mode, the message is acknowledged on successful processing; if processing fails, the message can be retried as configured. Check listener/acknowledgement settings for your AWSpring version before customizing.

The worker needs IAM permissions **sqs:ReceiveMessage**, **sqs:DeleteMessage**, and **sqs:GetQueueAttributes** on its assigned queue; retention, visibility timeout, and redrive policy are configured on SQS.

### 8.3. Email Worker: Spring Boot → SES

SES API dependency via Spring Cloud AWS:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-ses")
}
~~~

MailSender example:

~~~java
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class TransactionalEmailSender {
    private final MailSender mailSender;

    public TransactionalEmailSender(MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String from, String recipient, String subject, String text) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject(subject);
        message.setText(text);
        mailSender.send(message);
    }
}
~~~

The SES identity must be verified in the right region, the account must have appropriate sending access, and the IAM role needs matching SES actions (e.g., **ses:SendEmail**). If sending MIME/attachments via AWSpring's JavaMailSender, also verify **ses:SendRawEmail** and Jakarta Mail dependencies.

### 8.4. IAM Permissions by Role

| Workload | Typical Least-Privilege Permissions | Not Needed When Scoped to Role |
| --- | --- | --- |
| Order publisher | **sns:Publish** on specific topic | SQS Receive/Delete, SES Send |
| Email worker | **sqs:ReceiveMessage**, **sqs:DeleteMessage**, **sqs:GetQueueAttributes**; **ses:SendEmail** if sending via SES | SNS CreateTopic/Subscribe |
| Analytics worker | Read/delete permissions on analytics queue | SES Send, SNS Publish |
| Feedback worker | Read/delete permissions on feedback queue and DB write permissions | SNS Publish business events |

For SNS → SQS, the queue resource policy must allow **sns.amazonaws.com** to perform **sqs:SendMessage** constrained by the topic's **aws:SourceArn**. The publisher's IAM role does not replace the queue policy. With KMS encryption, add required key permissions/policies for each principal.

## 9. Reliability: Retries, DLQs, and Idempotency in the Right Place

| Service / Path | Where Error Handling Lives | What to Design |
| --- | --- | --- |
| Publisher → SNS | Publisher-side retries, outbox if needed | Timeouts do not prove a request was missed; use stable event IDs |
| SNS → endpoint subscription | SNS delivery retries and **subscription DLQ** where supported | Check endpoint policies, delivery status, and permanent failures |
| SNS → SQS | SNS delivery retries, SQS queue policy, subscription DLQ | Ensure SNS is permitted to SendMessage; do not confuse filter mismatch with delivery failure |
| SQS → worker | Visibility timeout, redrive policy, **SQS DLQ** | Idempotency, maxReceiveCount, poison-message handling |
| Worker → SES | Bounded retries, quota/rate control, outbox/job state | Prevent duplicate emails on timeouts or worker crashes after SES acceptance |

**Two DLQ types to distinguish:**

- **SNS subscription DLQ:** receives messages SNS could not deliver to an endpoint.
- **SQS consumer DLQ:** receives messages that reached the main queue but failed worker processing repeatedly.

A message dropped by a **filter policy** is not a delivery failure; do not expect a subscription DLQ to capture messages that failed to match a filter.

**Idempotency** matters in both the SQS worker and the email sender. Standard queues/topics carry at-least-once semantics; FIFO deduplication likewise does not create a shared transaction with SES or your database. A business key such as **orderId + emailType + templateVersion** helps guard against duplicate sends, alongside persisting send state and handling ambiguous timeouts.

## 10. Anti-Patterns and How to Improve Them

| Anti-Pattern | Why It Is Problematic | Appropriate Design |
| --- | --- | --- |
| Using SNS as a queue for workers to replay hours later | SNS lacks SQS retention/visibility/ack semantics | SNS → SQS subscription |
| Using one SQS queue to broadcast to multiple services | Workers compete; each message is not delivered to all | One dedicated queue per consumer, fanned out via SNS |
| Using SES as an email job backlog store | SES sends mail; it does not manage application job backlogs | SQS holds jobs, worker sends via SES |
| Calling SES synchronously inside the order transaction | Network latency/throttling prolongs transactions and increases failures | Outbox/SQS + email worker |
| Concluding an email was delivered solely from API success | SES may accept a request then later bounce/delay/suppress | Event publishing, feedback worker, and dashboards |
| Infinitely retrying all errors | Permission, identity, or hard bounce errors never self-heal | Classify permanent vs. transient errors and use backoff |
| Granting Administrator permissions to all workers | Expands blast radius and increases risk | Role/resource-scoped IAM least privilege |
| Using SNS email subscriptions for complex transactional emails | Lacks required identity/template/feedback workflows | SES |

## 11. Selecting Services Across Real-World Scenarios

### Scenario A: Notifying Three Services About One Event

**Requirement:** after payment completes, inventory, analytics, and notifications each need independent processing.

**Choice:** SNS topic **payment-events** with three SQS subscriptions.

**Reason:** the publisher publishes once; each queue keeps its own copy with its own workers and DLQ. Analytics downtime does not force inventory processing to halt.

### Scenario B: Background Image Processing

**Requirement:** users upload images that need resizing; multiple workers can resize different images, but each image only needs one worker to process it.

**Choice:** SQS queue **image-resize-jobs**.

**Reason:** this is a work queue where workers compete for jobs. If multiple services need notifying after resizing finishes, publish a result event to SNS.

### Scenario C: Sending Order Confirmation Emails

**Requirement:** send personalized HTML emails with receipts and handle bounces.

**Choice:** SQS **email-jobs** + worker + SES.

**Reason:** SQS smooths load and retries jobs; SES handles email delivery, identities, and feedback. SNS can fan out feedback events to SQS or other systems.

### Scenario D: Operational Alerts to an Email Group

**Requirement:** send a simple notification when a metric threshold is breached.

**Choice:** an SNS email subscription may suffice if the endpoint is confirmed and rich customization is unnecessary. If templates, custom sending domains, tracking, bounces/complaints, or personalization are needed, use SES.

### Scenario E: Ordered Work Items for a Single Order

**Requirement:** ORDER_CREATED → ORDER_PAID → ORDER_SHIPPED must be processed sequentially within the same aggregate.

**Choice:** SQS FIFO or SNS FIFO → SQS FIFO depending on subscriber count.

**Reason:** MessageGroupId keyed by orderId preserves ordering within the group. Consumers still need idempotency and side-effect controls.

## 12. Pre-Decision Checklist

Before choosing services, answer these questions:

- **Communication target:** service, worker, or human email recipient?
- **Delivery pattern:** broadcast to multiple subscribers or one worker from a pool?
- **Storage:** must a backlog be retained and consumed over hours/days?
- **Load:** are buffering, rate control, and load leveling required?
- **Ordering:** is best effort acceptable, or is per-aggregate ordering required?
- **Delivery:** what level of at-least-once, duplicates, and retries is acceptable?
- **Fan-out:** does each consumer need its own queue, retention, and DLQ?
- **Email:** are verified identities, HTML/MIME, attachments, templates, and bounce/complaint handling needed?
- **Security:** which IAM roles publish/consume/send, and what queue policy grants access to SNS?
- **Observability:** are SNS delivery, SQS age/depth/DLQ, and SES bounce/complaint metrics tracked?
- **Operations:** who owns replays, redrives, suppression, and poison-message handling?

There is no single best service for every problem. Choose based on the **semantics consumers need**, then pick the matching Spring abstractions and AWS configurations.

## 13. Exercise and Review Questions

**Exercise:** design an order placement flow with three workflows: inventory, analytics, and email confirmation. Diagram the architecture and deploy in a sandbox:

1. Order Service publishes **ORDER_CREATED** to an SNS topic.
2. Create three independent SQS queues for inventory, analytics, and email.
3. Add filter policies if individual branches only consume specific event types.
4. Write a Spring Boot listener for each queue; each listener logs the event ID and processes idempotently.
5. The email worker calls SES via Spring **MailSender** or **JavaMailSender**.
6. Enable SES event publishing to capture bounces/complaints and update status.
7. Simulate worker downtime, SES throttling, and duplicate events; observe queue depth, retries, and DLQs.
8. Compare this design against having the publisher call all three services directly.

**Self-check questions:**

1. Why does SNS fit broadcasting while SQS fits competing consumers?
2. Under what circumstances can a message in SQS Standard be received more than once?
3. Why is SNS → one SQS queue per consumer better than one shared queue when fan-out is required?
4. In what capabilities does SES differ from an SNS email subscription?
5. When the email worker is unavailable, how does SQS help the SES workflow?
6. Why does SES API success not prove the destination mail server delivered the message?
7. At which stages do an SNS subscription DLQ and an SQS worker DLQ handle failures?
8. When should FIFO be chosen, and why is idempotency still necessary?
9. Which roles require **sns:Publish**, **sqs:ReceiveMessage**, and **ses:SendEmail**?
10. If you need to both broadcast events and send emails, why should SES not replace SNS?

## 14. References

- [Amazon SNS — What is Amazon SNS?](https://docs.aws.amazon.com/sns/latest/dg/welcome.html): publish/subscribe model, topics, and subscribers.
- [Amazon SQS — What is Amazon SQS?](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html): queues, consumers, and message retention.
- [Amazon SQS — Visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html): mechanism hiding messages during processing.
- [Amazon SQS — Dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html): redrive and failed message handling.
- [Amazon SNS — Message filtering](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html): per-subscription filter policies.
- [Amazon SNS — SNS to SQS fan-out](https://docs.aws.amazon.com/sns/latest/dg/sns-sqs-as-subscriber.html): delivering messages from topics to queues.
- [Amazon SES — Getting started with sending email](https://docs.aws.amazon.com/ses/latest/dg/getting-started-sending.html): identities, sandbox, and sending email.
- [Amazon SES — Event publishing](https://docs.aws.amazon.com/ses/latest/dg/monitor-using-event-publishing.html): delivery, bounce, complaint, and event destinations.
- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html): SNS, SQS, and SES integration for Spring Boot.

**Expected outcome:** learners choose the right service for each purpose—**SNS to distribute events, SQS to buffer and coordinate work, SES to send emails**—and combine them into an asynchronous Spring Boot architecture with proper permissions, retries, DLQs, and feedback handling.
