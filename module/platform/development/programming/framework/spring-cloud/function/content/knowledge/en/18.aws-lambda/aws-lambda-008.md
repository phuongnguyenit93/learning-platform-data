# Returning SQS Partial Batch Failure Responses When Appropriate

When **Amazon SQS** triggers **AWS Lambda**, each invocation can carry a **batch** of multiple messages. By default, if the function fails on any message and the invocation fails, **the entire batch can be redelivered**, including messages that already succeeded. In **SPRING_CLOUD_FUNCTION**, you can declare a **Function<SQSEvent, SQSBatchResponse>** bean and use the **FunctionInvoker** handler from **spring-cloud-function-adapter-aws** to return the exact list of messages that need to be retried. This mechanism is called **partial batch response** or **reporting batch item failures**.

This lesson belongs to the **AWS Lambda** chapter and dives into **when to use** partial batch failure responses, the **batchItemFailures** structure, the conditions for configuring **ReportBatchItemFailures**, differences between SQS Standard and FIFO, idempotency/retry/DLQ design, complete Java 17+ examples with Spring Cloud Function, AWS SAM configuration, testing, and dangerous pitfalls. This supports the module's broader goal: keeping business logic reusable via **Supplier**, **Function**, and **Consumer**, while handling SQS-specific integration at the serverless adapter boundary.

## 1. A Single Lambda Invocation Can Contain Multiple SQS Messages

SQS does not invoke a Java method directly. **Lambda event source mapping** polls the queue, groups messages into a batch, and invokes Lambda with an event containing a **Records** array.

Simplified example with three records:

~~~json
{
  "Records": [
    {
      "messageId": "msg-001",
      "receiptHandle": "sample-handle-001",
      "body": "{\"eventId\":\"evt-001\",\"orderId\":\"ORD-101\",\"action\":\"CREATE\"}",
      "attributes": {"ApproximateReceiveCount": "1"},
      "messageAttributes": {},
      "eventSource": "aws:sqs"
    },
    {
      "messageId": "msg-002",
      "receiptHandle": "sample-handle-002",
      "body": "{\"eventId\":\"evt-002\",\"orderId\":\"ORD-102\",\"action\":\"SIMULATE_RETRY\"}",
      "attributes": {"ApproximateReceiveCount": "1"},
      "messageAttributes": {},
      "eventSource": "aws:sqs"
    },
    {
      "messageId": "msg-003",
      "receiptHandle": "sample-handle-003",
      "body": "{\"eventId\":\"evt-003\",\"orderId\":\"ORD-103\",\"action\":\"CREATE\"}",
      "attributes": {"ApproximateReceiveCount": "1"},
      "messageAttributes": {},
      "eventSource": "aws:sqs"
    }
  ]
}
~~~

This is a **simplified illustrative event**, omitting common attributes such as **md5OfBody**, **eventSourceARN**, and **awsRegion**. The messageId/receiptHandle values are fictional for instructional purposes.

| Field | Meaning |
| --- | --- |
| **Records** | List of messages delivered in a single invocation |
| **messageId** | SQS message ID; used as **itemIdentifier** when reporting failures |
| **body** | Message content string; can be business JSON or a nested envelope |
| **receiptHandle** | Token to receive/delete the message via SQS APIs; **never** use in place of messageId in partial failures |
| **attributes** | System metadata such as receive count; FIFO adds group info |
| **messageAttributes** | Sender-supplied attributes, separate from body |
| **eventSourceARN** | Source queue ARN; useful to distinguish when one Lambda has multiple mappings |

**One SQS invocation does not equal one order or one business event.** The Function contract must iterate over each **SQSEvent.SQSMessage**, parse each **body**, and determine success or failure at the record level.

## 2. What Happens When Partial Batch Response Is Not Used?

Suppose the business processor handles:

- **msg-001**: succeeds, data persisted.
- **msg-002**: fails due to a dependency timeout.
- **msg-003**: succeeds or remains unprocessed, depending on where code stops.

If code **throws an exception out of the Lambda handler** without per-record reporting, AWS normally treats the **entire invocation/batch as failed**. After the visibility timeout, messages in the batch can reappear for redelivery. That can cause **msg-001** to be reprocessed even though its side effect already occurred.

~~~mermaid
flowchart LR
    A["Batch: 001, 002, 003"] --> B["Lambda"]
    B --> C["001 succeeds"]
    B --> D["002 fails"]
    D --> E["Whole-invocation exception"]
    E --> F["Batch may be retried"]
    F --> G["001 may run again"]
~~~

This is why Function authors need **idempotency** even without partial failures enabled: SQS and Lambda have **at-least-once** semantics and do not promise exactly-once execution.

If code swallows the exception and returns success for the whole batch, the opposite failure mode is even worse: **msg-002 can be deleted from the queue despite never being processed**. "Not throwing" does not automatically mean every message succeeded.

## 3. What Does Partial Batch Response Change?

When the **event source mapping** enables:

~~~text
FunctionResponseTypes = ReportBatchItemFailures
~~~

Lambda can return a response like:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "msg-002"
    }
  ]
}
~~~

Meaning:

- **msg-001** and **msg-003** are absent from the failure list: Lambda can delete them after processing a valid response.
- **msg-002** is reported as unsuccessful: it can be redelivered after the visibility timeout according to the queue's retry and retention settings.
- The list is keyed **at the SQS messageId level**, not business eventId, orderId, or receiptHandle.

~~~mermaid
flowchart TD
    A["SQS batch: 001, 002, 003"] --> B["Function<SQSEvent,SQSBatchResponse>"]
    B --> C["001: succeeds"]
    B --> D["002: fails"]
    B --> E["003: succeeds"]
    C --> F["Response"]
    D --> F
    E --> F
    F --> G["batchItemFailures: [msg-002]"]
    G --> H["AWS deletes successful records"]
    G --> I["msg-002 awaits retry"]
~~~

**Partial response reduces unnecessary retries**, yet **does not eliminate duplicates completely**. An invocation timeout, network error, concurrent delivery, or response failure can still cause a successful record to run again. Side effects such as DB writes, event publishing, or payments still require idempotent design.

## 4. Two Mandatory Conditions for AWS to Understand the Response

The mechanism works when **both configuration and application code** are right:

1. The SQS event source mapping has **FunctionResponseTypes: ReportBatchItemFailures**.
2. The Function returns a response matching the **batchItemFailures** schema and **does not throw an outer exception** for record failures you intend to report partially.

If you only write Java code returning **SQSBatchResponse** without enabling **ReportBatchItemFailures**, Lambda does not use the list to decide which messages to retry. Dangerously, **the handler may be treated as having succeeded**, while failed records listed in the body are not retried as expected.

Conversely, if the flag is enabled yet your code hits an error and **throws outward**, AWS still treats **the entire batch as failed**.

| Mapping Configuration | Handler Outcome | Behavior to Understand |
| --- | --- | --- |
| ReportBatchItemFailures not enabled | Returns object with failed IDs | AWS ignores partial report; do not assume per-record retries |
| Enabled | Returns valid failed IDs | Listed messages are retried; remaining messages may be deleted |
| Enabled | Returns empty list | Entire batch considered successful |
| Enabled | Returns null/empty response | AWS considers batch successful; may drop errors if code forgot failed IDs |
| Enabled | Throws exception outward | Entire batch fails |
| Enabled | Invalid response JSON/IDs | Entire batch may be considered failed |

**Test AWS configuration and Java responses together.** Unit tests only prove the code constructs a list of IDs, not that the Lambda event source mapping has the feature enabled.

## 5. Response Schema: Right Keys, Right Identifier

AWS expects a JSON object like this:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "msg-002"},
    {"itemIdentifier": "msg-004"}
  ]
}
~~~

The **camelCase** fields are part of the contract:

- **batchItemFailures** is an array.
- Each element is an object with key **itemIdentifier**.
- The value must be a **messageId present in the Records of the batch being processed**.

### Invalid Structures

Wrong key names:

~~~json
{
  "failedMessages": [
    {"messageId": "msg-002"}
  ]
}
~~~

Wrong identifier:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "ORDER-102"}
  ]
}
~~~

If **ORDER-102** is a business orderId rather than an SQS messageId in the batch, the response is invalid.

Null/empty identifier:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": ""}
  ]
}
~~~

AWS may treat the **entire batch as failed** when an identifier is empty, null, uses the wrong key name, or is absent from the batch. Do not assume AWS skips bad entries and accepts the remaining ones.

### Full Batch Success

~~~json
{
  "batchItemFailures": []
}
~~~

This is the clearest response when every record succeeds. AWS may also treat a **null response** or **null list** as success, but never use that to express "unsure whether all items were processed".

## 6. When SHOULD You Enable Partial Batch Responses?

This mechanism fits best when:

- The queue typically delivers **batch sizes greater than 1**.
- Messages in a **Standard queue** can be processed and acknowledged **independently**.
- A few malformed or timed-out messages should not force **the entire batch** to rerun.
- Side effects already have an **idempotency** strategy; reducing retries lowers cost and downstream load.
- Logging/metrics and a DLQ exist to monitor persistently failing messages.
- The application can classify errors **per record** and emit a contract-compliant response.

For example: in a batch of 10 email-sending requests, 9 emails succeed and 1 fails due to a transient error. If each request's outcome is independent, retrying only that one message makes sense.

Another operational benefit noted by AWS: with **ReportBatchItemFailures** enabled, Lambda **does not scale down polling due to invocations reporting record failures via this mechanism** the way it can for completely failed invocations. This keeps throughput from being dragged down by a few poison messages, though it can **increase pressure on downstream systems** if many messages fail continuously.

### When Does It Offer Little Benefit or Need Another Approach?

| Scenario | Consideration |
| --- | --- |
| **BatchSize=1** | Partial still works, yet saves no retries on other records |
| **Batch must commit atomically** | Cannot acknowledge messages independently if one error rolls back a shared transaction |
| **System-wide DB outage** | If every record depends on the same DB and all fail, per-ID reporting adds little value; circuit breaker/backoff may fit better |
| **Code bug or severe misconfiguration** | Do not turn every exception into a record-level failure and mask system failures |
| **FIFO with strict ordering** | Use only with a proper stop-and-report-remaining flow |
| **Permanent poison message** | Partial does not replace DLQ/quarantine; without a redrive policy, messages retry repeatedly |
| **Immediate HTTP response needed by client** | SQS partial reporting is not an HTTP response to a caller |
| **No event mapping tests** | Do not enable in production just because code compiles; verify the mapping actually has the flag |

**"When appropriate" means the business contract permits per-record success acknowledgment.** If messages in a batch form an indivisible transaction, partial responses can break consistency guarantees.

## 7. Standard SQS vs. FIFO SQS: Different Rules

### 7.1. Standard Queue — Independent Record Processing

Suppose three records:

| Receive Order | messageId | Outcome |
| --- | --- | --- |
| 1 | msg-001 | Succeeded |
| 2 | msg-002 | Failed |
| 3 | msg-003 | Succeeded |

You can continue processing **msg-003** after **msg-002** fails, provided tasks are independent and out-of-order execution is allowed. Return:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "msg-002"}
  ]
}
~~~

### 7.2. FIFO Queue — Stop at the First Failure

FIFO guarantees ordering per **MessageGroupId** under AWS-defined conditions. AWS recommends with **ReportBatchItemFailures**:

> Stop processing on the first failure; include the failed message and **all unprocessed messages** in the failure list.

Example:

| Receive Order | messageId | Action |
| --- | --- | --- |
| 1 | msg-001 | Processed successfully |
| 2 | msg-002 | Processing failed |
| 3 | msg-003 | **Not processed** |
| 4 | msg-004 | **Not processed** |

Response:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "msg-002"},
    {"itemIdentifier": "msg-003"},
    {"itemIdentifier": "msg-004"}
  ]
}
~~~

~~~mermaid
flowchart TD
    A["FIFO batch 001,002,003,004"] --> B["001 succeeds"]
    B --> C["002 fails"]
    C --> D["STOP: do not process 003/004"]
    D --> E["Return failed: 002,003,004"]
~~~

**Do not mark msg-003/msg-004 as succeeded if they were not executed.** If omitted from the list, Lambda may delete them alongside successful records.

A FIFO batch can span different message groups; if per-group optimization is needed while preserving ordering, per-group policies must be designed and tested very carefully. **Stopping the whole batch at the first error** in the example is the conservative approach, easy to verify against AWS guidance.

## 8. Java Types to Use in Spring Cloud Function

The AWS adapter provides the handler:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker
~~~

or in the AWS Console using the syntax:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

Inside the application, declare:

~~~java
Function<SQSEvent, SQSBatchResponse>
~~~

AWS event classes:

~~~java
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;
~~~

and related dependencies:

~~~xml
<dependency>
    <groupId>com.amazonaws</groupId>
    <artifactId>aws-lambda-java-events</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

**This is a dependency snippet, not a complete pom.xml**. You need a BOM/parent managing compatible Spring Boot, Spring Cloud/Function, and AWS library versions. For the Jackson 2 and Java 17+ example, add the appropriate JSON dependency for your chosen Spring Boot version.

Do not use **Consumer<SQSEvent>** when you need to return an **SQSBatchResponse** with a list of item failures: **Consumer** has no return value. A **Function<SQSEvent,SQSBatchResponse>** bean states the contract explicitly. You also do not need to write a separate Java **RequestHandler<SQSEvent,SQSBatchResponse>** when FunctionInvoker meets the requirement.

## 9. Complete Java 17+ Example: Standard and FIFO Beans

The main example defines:

1. **OrderEvent**: DTO parsed from each **SQSMessage.body**.
2. **OrderEventProcessor**: contract for business logic.
3. **processStandardSqs**: continues across records, reporting failed records individually.
4. **processFifoSqs**: stops after the first failing record, reporting unprocessed records as well.
5. **SQSBatchResponse**: output formatted to AWS's schema.

The illustrative code **does not write to a DB or call real AWS services**. The sample processor only validates data and simulates an intentional retryable error so tests can verify semantics safely.

File **src/main/java/example/sqs/SqsPartialBatchApplication.java**:

~~~java
package example.sqs;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.function.Function;

import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SqsPartialBatchApplication {

    private static final Logger log =
        LoggerFactory.getLogger(SqsPartialBatchApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(
            SqsPartialBatchApplication.class, args);
    }

    public record OrderEvent(
        String eventId,
        String orderId,
        String action
    ) {}

    @FunctionalInterface
    public interface OrderEventProcessor {
        void process(OrderEvent event);
    }

    public static final class InvalidOrderMessage
            extends RuntimeException {
        public InvalidOrderMessage(String reason) {
            super(reason);
        }
    }

    public static final class RetryableOrderFailure
            extends RuntimeException {
        public RetryableOrderFailure(String reason) {
            super(reason);
        }
    }

    @Bean
    OrderEventProcessor demoProcessor() {
        return event -> {
            if (event == null
                    || event.eventId() == null
                    || event.eventId().isBlank()
                    || event.orderId() == null
                    || event.orderId().isBlank()
                    || event.action() == null) {
                throw new InvalidOrderMessage(
                    "Invalid order event");
            }

            if ("SIMULATE_RETRY".equals(event.action())) {
                throw new RetryableOrderFailure(
                    "Simulated temporary error");
            }

            if (!Set.of("CREATE", "CANCEL")
                    .contains(event.action())) {
                throw new InvalidOrderMessage(
                    "Unsupported order action");
            }

            // Demo: validation succeeded, NOT yet written to database.
            // Production: durable/idempotent processing must run here.
        };
    }

    @Bean("processStandardSqs")
    Function<SQSEvent, SQSBatchResponse> processStandardSqs(
            ObjectMapper mapper,
            OrderEventProcessor processor) {

        return event -> processBatch(
            event, mapper, processor, false);
    }

    @Bean("processFifoSqs")
    Function<SQSEvent, SQSBatchResponse> processFifoSqs(
            ObjectMapper mapper,
            OrderEventProcessor processor) {

        return event -> processBatch(
            event, mapper, processor, true);
    }

    private static SQSBatchResponse processBatch(
            SQSEvent event,
            ObjectMapper mapper,
            OrderEventProcessor processor,
            boolean fifo) {

        if (event == null || event.getRecords() == null) {
            throw new IllegalArgumentException(
                "Missing SQS Records");
        }

        List<SQSEvent.SQSMessage> records =
            event.getRecords();

        List<SQSBatchResponse.BatchItemFailure> failed =
            new ArrayList<>();

        for (int i = 0; i < records.size(); i++) {
            SQSEvent.SQSMessage message = records.get(i);

            // Invalid envelope: DO NOT fabricate a wrong itemIdentifier.
            String messageId = requireMessageId(message);

            try {
                if (message.getBody() == null
                        || message.getBody().isBlank()) {
                    throw new InvalidOrderMessage(
                        "Empty message body");
                }

                OrderEvent input = mapper.readValue(
                    message.getBody(),
                    OrderEvent.class);

                processor.process(input);

                // Consider successful only after real work completes.

            } catch (JsonProcessingException
                     | InvalidOrderMessage
                     | RetryableOrderFailure ex) {

                log.warn(
                    "SQS record failed: messageId={}, type={}",
                    messageId,
                    ex.getClass().getSimpleName());

                failed.add(
                    new SQSBatchResponse.BatchItemFailure(
                        messageId));

                if (fifo) {
                    // Do not continue processing messages after an error.
                    for (int j = i + 1;
                            j < records.size(); j++) {
                        String unprocessedId =
                            requireMessageId(records.get(j));
                        failed.add(
                            new SQSBatchResponse.BatchItemFailure(
                                unprocessedId));
                    }
                    break;
                }
            }
        }

        return new SQSBatchResponse(failed);
    }

    private static String requireMessageId(
            SQSEvent.SQSMessage message) {

        if (message == null
                || message.getMessageId() == null
                || message.getMessageId().isBlank()) {
            throw new IllegalStateException(
                "Invalid SQS envelope: missing messageId");
        }

        return message.getMessageId();
    }
}
~~~

### 9.1. Notable Points in the Code

- **Bean names** are explicit: **processStandardSqs** and **processFifoSqs**. Lambda picks only one via **spring_cloud_function_definition**.
- Each record is parsed from **message.getBody()**, rather than parsing the entire **Records** array as one OrderEvent.
- **JsonProcessingException** is a JSON parse failure; **InvalidOrderMessage** and **RetryableOrderFailure** are intentional failures the system reports per record.
- Every failure uses the exact **message.getMessageId()** as **itemIdentifier**.
- If the envelope lacks messageId, the code throws at the invocation level instead of returning an invalid **SQSBatchResponse**.
- With **FIFO**, the loop stops after the first failure and records all unprocessed IDs.
- The example **does not catch every RuntimeException or Error**. If a code bug or infrastructure failure occurs outside the record-level policy, the invocation can fail the whole batch; this is an intentional design choice and requires monitoring.

**Warning:** when extending the code to call a database, S3, downstream HTTP services, or publish messages, a failure may be transient even if it is not one of the classes above. Establish sensible exception boundaries, decide whether to fail individual records or the whole batch, and never accidentally "acknowledge success" by swallowing errors.

### 9.2. The Demo Processor Is Not a Production Business Consumer

In the example, **demoProcessor** does not persist data, so a record with a valid CREATE action counts as "validation succeeded". This is **not** proof that an order was created.

In production, replace the processor with an idempotent implementation:

~~~java
// Design sketch, NOT an already-declared class.
processor.process(event);

// Inside a production processor you can:
// 1. Use event.eventId() as the idempotency key.
// 2. Check/record the key with a transaction or unique constraint.
// 3. Execute the side effect, or write a transactional outbox.
// 4. Return normally only once the outcome is durable.
~~~

If the side effect commits successfully yet the response is lost, the message can be redelivered. The processor must recognize an already-processed event and return a safe success/no-op. Never use an in-JVM singleton **HashSet** as a durable deduplication store across Lambda execution environments.

## 10. Input/Output by Scenario

Consider a Standard batch of three messages:

~~~text
msg-001 body.action=CREATE
msg-002 body.action=SIMULATE_RETRY
msg-003 body.action=CANCEL
~~~

Result:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "msg-002"}
  ]
}
~~~

With a FIFO batch in the same order:

~~~text
msg-001: processed successfully
msg-002: failed
msg-003: not processed
~~~

Result:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "msg-002"},
    {"itemIdentifier": "msg-003"}
  ]
}
~~~

If all three succeed:

~~~json
{
  "batchItemFailures": []
}
~~~

If **messageId is missing in a record**—for example due to a malformed test event or envelope parsing failure—the function throws **IllegalStateException** at the batch level. Never return:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": null}
  ]
}
~~~

because AWS treats this as an invalid response. An explicit error model prevents "false success" when the event shape is already broken.

## 11. Do Not Turn Every Error Into Infinite Retries

Three error categories must be distinguished:

| Error Group | Example | Strategy to Consider |
| --- | --- | --- |
| **Permanently invalid data** | Missing eventId, invalid JSON schema | Report failure so DLQ/quarantine takes over after retry limit; or durably record rejection and ack per contract |
| **Transient errors** | Downstream timeout, throttling, DB unavailable | Report failure for retry/backoff or fail the batch on global outage |
| **Severe code/infra bugs** | Serializer bug, misconfigured Spring, missing class | Let invocation fail, alert, and fix deployment; do not pretend records succeeded |

Never catch every exception and return **batchItemFailures: []**. Also never catch every exception to retry permanently broken data endlessly without a DLQ.

For authentication or IAM permission errors, repeated retries rarely fix the root cause. Alert by error category, fix permissions/configuration, or move messages to an inspection store after a reasonable number of attempts.

### Deciding to ACK an Invalid Message

Some systems treat an invalid message as **handled** after writing it to a durable **quarantine store**. In that case, you may **omit it from batchItemFailures**, because the handling responsibility shifted to "persist error and stop retrying". Only do so after the quarantine write succeeds and when the contract permits deleting the original message. If writing to the error store fails, you must still report failure.

## 12. AWS SAM Standard Queue Configuration with DLQ

Example **template.yaml** describing a Lambda consuming a Standard SQS queue and returning partial responses.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  OrdersDlq:
    Type: AWS::SQS::Queue

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 180
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrdersDlq.Arn
        maxReceiveCount: 5

  ProcessOrdersLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/sqs-partial-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.sqs.SqsPartialBatchApplication
          spring_cloud_function_definition: processStandardSqs
      Policies:
        - SQSPollerPolicy:
            QueueName: !GetAtt OrdersQueue.QueueName
      Events:
        OrdersEvents:
          Type: SQS
          Properties:
            Queue: !GetAtt OrdersQueue.Arn
            BatchSize: 10
            FunctionResponseTypes:
              - ReportBatchItemFailures
~~~

### Configuration Explanation

- **FunctionResponseTypes: ReportBatchItemFailures** is the property that tells AWS Lambda to inspect the failed IDs list.
- **BatchSize: 10** fits the Standard queue example, not an optimal value for all workloads.
- **VisibilityTimeout: 180** relative to **Timeout: 30** follows AWS's baseline guidance: set visibility timeout to at least roughly **6x** the Lambda timeout to leave room for throttling retries. If a batching window is used, add that window per AWS recommendations.
- **RedrivePolicy** moves repeatedly failing messages to **OrdersDlq** once receive counts exceed the threshold under SQS mechanics.
- **SQSPollerPolicy** grants least-privilege permissions for Lambda to poll/delete SQS messages; if the queue uses a customer-managed KMS key, **kms:Decrypt** and proper queue/key policies may be needed.
- **CodeUri** is an example JAR. The project must build an **actual shaded JAR** containing **FunctionInvoker**, application classes, dependencies, and Spring metadata.
- **MAIN_CLASS** is the Spring Boot application class; **spring_cloud_function_definition** selects the **processStandardSqs** bean.
- **IAM**, networking, log retention, tags, encryption, alarms, and other permissions must be added for real environments.

This is a **structural illustration template**, not a full production deployment. The Java runtime must be compatible with your bytecode and Spring Boot/Spring Cloud Function combination.

### Why Does a DLQ Matter?

If a "poison-pill" message always fails schema validation, partial responses repeatedly return its messageId and the message is redelivered. Without a DLQ/quarantine, the message can loop until retention expires, wasting cost and creating backlog. AWS Prescriptive Guidance refers to this accumulating failure phenomenon as the **snowball anti-pattern**.

Verify the **redrive policy** (e.g., maxReceiveCount), DLQ retention, alarms, and a controlled replay workflow. Never automatically replay unfixed data back into the same queue infinitely.

## 13. FIFO Queue Configuration: What Else Changes?

With FIFO, you do more than switch **definition** to processFifoSqs. Both the queue and DLQ must also be **FIFO queues**, with queue names ending in **.fifo**.

Resources-only example:

~~~yaml
OrdersFifoDlq:
  Type: AWS::SQS::Queue
  Properties:
    QueueName: orders-dead-letter.fifo
    FifoQueue: true

OrdersFifoQueue:
  Type: AWS::SQS::Queue
  Properties:
    QueueName: orders-source.fifo
    FifoQueue: true
    VisibilityTimeout: 180
    RedrivePolicy:
      deadLetterTargetArn: !GetAtt OrdersFifoDlq.Arn
      maxReceiveCount: 5
~~~

On the corresponding Lambda:

~~~yaml
Environment:
  Variables:
    MAIN_CLASS: example.sqs.SqsPartialBatchApplication
    spring_cloud_function_definition: processFifoSqs
Events:
  FifoOrders:
    Type: SQS
    Properties:
      Queue: !GetAtt OrdersFifoQueue.Arn
      BatchSize: 10
      FunctionResponseTypes:
        - ReportBatchItemFailures
~~~

These two snippets are **only parts of a template**, not a complete Lambda resource. Add Runtime, Handler, CodeUri, IAM, and memory/timeout on the real resource.

**FIFO ordering:** stop at the first failure and return unprocessed IDs as in Section 9's code. When publishers send messages to FIFO, they must satisfy **MessageGroupId** and deduplication rules (MessageDeduplicationId or content-based deduplication depending on configuration). Partial batch responses do not alter FIFO message-group semantics.

BatchSize and batching window limits can differ between Standard and FIFO, especially when using provisioned event polling. Choose values from the Lambda event source mapping docs for your feature version rather than hard-coding assumptions across all setups.

## 14. AWS CLI: Inspecting the Real Event Source Mapping Configuration

To list mappings configured for a Lambda:

~~~bash
aws lambda list-event-source-mappings --function-name process-orders-lambda
~~~

To inspect a specific mapping:

~~~bash
aws lambda get-event-source-mapping --uuid YOUR_MAPPING_UUID
~~~

In the output, verify:

~~~text
EventSourceArn
FunctionArn
BatchSize
FunctionResponseTypes
State
LastProcessingResult
~~~

To enable partial failures on an existing mapping:

~~~bash
aws lambda update-event-source-mapping --uuid YOUR_MAPPING_UUID --function-response-types ReportBatchItemFailures
~~~

**YOUR_MAPPING_UUID** is a placeholder replaced by the operator with the UUID from the real mapping. Do not run these commands without an existing Lambda/queue and appropriate AWS credentials/permissions.

### Verifying After Updating

1. Mapping has an appropriate **State**, and the update has completed.
2. **FunctionResponseTypes** actually contains **ReportBatchItemFailures**.
3. The function code version/alias invoked by the mapping is the one deploying the SQSBatchResponse logic.
4. Queue ARN, BatchSize, visibility timeout, and redrive policy are correct.
5. A test batch containing a failing message triggers retries on the intended message.

**FunctionResponseTypes belongs to the event source mapping**, not the **spring_cloud_function_definition** environment variable. Those two settings solve two different concerns.

If your project manages infrastructure with **SAM/CloudFormation/Terraform**, update the IaC source and redeploy instead of making manual CLI edits that drift and get overwritten on the next deploy.

## 15. Testing Standard Batches with JUnit 5

To test pure logic, you need neither AWS credentials, nor a running Lambda runtime, nor real messages sent to SQS.

File **src/test/java/example/sqs/StandardBatchTest.java**:

~~~java
package example.sqs;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Arrays;
import java.util.List;

import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class StandardBatchTest {

    private final SqsPartialBatchApplication app =
        new SqsPartialBatchApplication();

    private static SQSEvent.SQSMessage msg(
            String messageId, String body) {
        var message = new SQSEvent.SQSMessage();
        message.setMessageId(messageId);
        message.setBody(body);
        return message;
    }

    private static SQSEvent batch(
            SQSEvent.SQSMessage... messages) {
        var event = new SQSEvent();
        event.setRecords(Arrays.asList(messages));
        return event;
    }

    @Test
    void reportsOnlyFailedRecordForStandardQueue() {
        var event = batch(
            msg("msg-001",
                "{\"eventId\":\"evt-001\",\"orderId\":\"ORD-101\",\"action\":\"CREATE\"}"),
            msg("msg-002",
                "{\"eventId\":\"evt-002\",\"orderId\":\"ORD-102\",\"action\":\"SIMULATE_RETRY\"}"),
            msg("msg-003",
                "{\"eventId\":\"evt-003\",\"orderId\":\"ORD-103\",\"action\":\"CANCEL\"}")
        );

        var fn = app.processStandardSqs(
            new ObjectMapper(), app.demoProcessor());

        var result = fn.apply(event);

        List<String> failedIds =
            result.getBatchItemFailures().stream()
                .map(item -> item.getItemIdentifier())
                .toList();

        assertEquals(List.of("msg-002"), failedIds);
    }

    @Test
    void reportsEmptyListWhenAllSucceed() {
        var event = batch(
            msg("msg-001",
                "{\"eventId\":\"evt-001\",\"orderId\":\"ORD-101\",\"action\":\"CREATE\"}")
        );

        var result = app.processStandardSqs(
            new ObjectMapper(), app.demoProcessor()
        ).apply(event);

        assertEquals(0,
            result.getBatchItemFailures().size());
    }

    @Test
    void marksMalformedJsonAsFailedRecord() {
        var event = batch(
            msg("msg-bad", "{\"eventId\":")
        );

        var result = app.processStandardSqs(
            new ObjectMapper(), app.demoProcessor()
        ).apply(event);

        assertEquals("msg-bad",
            result.getBatchItemFailures()
                .get(0).getItemIdentifier());
    }
}
~~~

This test verifies that the Java code puts only **msg-002** in the failure list, succeeds when all records are valid, and flags malformed JSON messages.

**It is not enough to conclude AWS will retry the right record**: an integration test must confirm the event source mapping has ReportBatchItemFailures enabled and FunctionInvoker serializes the output according to schema.

## 16. Testing FIFO: Never Process Records After a Failure

FIFO tests should verify **two things**: the failed IDs list contains the failing record and subsequent records, and the processor **was never called** for unprocessed records.

File **src/test/java/example/sqs/FifoBatchTest.java**:

~~~java
package example.sqs;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;

import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class FifoBatchTest {

    @Test
    void stopsAfterFirstFailureAndReportsRemaining() {
        var app = new SqsPartialBatchApplication();

        List<String> processedEventIds =
            new ArrayList<>();

        SqsPartialBatchApplication.OrderEventProcessor processor =
            event -> {
                processedEventIds.add(event.eventId());

                if ("evt-002".equals(event.eventId())) {
                    throw new SqsPartialBatchApplication.RetryableOrderFailure(
                        "Temporary error");
                }
            };

        SQSEvent input = new SQSEvent();
        input.setRecords(List.of(
            msg("msg-001", "evt-001"),
            msg("msg-002", "evt-002"),
            msg("msg-003", "evt-003"),
            msg("msg-004", "evt-004")
        ));

        var fn = app.processFifoSqs(
            new ObjectMapper(), processor);

        var response = fn.apply(input);

        List<String> failedIds =
            response.getBatchItemFailures().stream()
                .map(item -> item.getItemIdentifier())
                .toList();

        assertEquals(
            List.of("msg-002", "msg-003", "msg-004"),
            failedIds);

        assertEquals(
            List.of("evt-001", "evt-002"),
            processedEventIds);
    }

    private static SQSEvent.SQSMessage msg(
            String messageId, String eventId) {
        var message = new SQSEvent.SQSMessage();
        message.setMessageId(messageId);

        message.setBody(
            "{\"eventId\":\"" + eventId
                + "\",\"orderId\":\"ORD-101\",\"action\":\"CREATE\"}");

        return message;
    }
}
~~~

If the test finds **evt-003** in **processedEventIds** after evt-002 failed, the loop is violating the committed policy. Checking only the returned ID list without verifying which side effects ran can miss ordering bugs.

This test uses a mock processor to record which items were called; in production, also verify ordering at the **MessageGroupId** level, event source mapping, and idempotency.

## 17. Testing Response JSON and FunctionCatalog

Alongside batch-processing tests, verify serialization to catch key or output-wrapper issues.

### 17.1. JSON Serialization of SQSBatchResponse

~~~java
package example.sqs;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class SqsBatchResponseJsonTest {

    @Test
    void emitsAwsExpectedJsonKeys() throws Exception {
        var response = new SQSBatchResponse(
            List.of(
                new SQSBatchResponse.BatchItemFailure(
                    "msg-002")
            )
        );

        var mapper = new ObjectMapper();
        var json = mapper.readTree(
            mapper.writeValueAsString(response));

        assertEquals(
            "msg-002",
            json.path("batchItemFailures")
                .get(0).path("itemIdentifier").asText());
    }
}
~~~

This test catches serializer issues in the current Java context. You still need a Lambda invocation **with the actual shaded JAR** to verify FunctionInvoker and event source mapping work end to end.

### 17.2. FunctionCatalog Integration Test

~~~java
package example.sqs;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = SqsPartialBatchApplication.class)
class SqsCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void findsBothBatchFunctions() {
        assertNotNull(
            catalog.lookup("processStandardSqs"));
        assertNotNull(
            catalog.lookup("processFifoSqs"));
    }
}
~~~

The Spring context must register an ObjectMapper matching the project's JSON dependency and AWS event types. The catalog test only proves the bean names exist, not that the Lambda trigger and response format are right.

### 17.3. Testing on Staging Lambda

A minimal integration test plan:

1. Provision a staging Standard queue, Lambda, and DLQ.
2. Enable **ReportBatchItemFailures**.
3. Send three messages, with one engineered to fail in a controlled way.
4. Verify successful messages do not reappear due to **whole-batch failure** under test conditions, while the failed message is redelivered.
5. Verify ApproximateReceiveCount and the DLQ after the redrive threshold.
6. Repeat for FIFO with the same message group, confirming records after the error are not processed.
7. Inspect logs/metrics and stop/tear down the staging consumer after testing.

**Never promise absolutely that successful messages will never be redelivered**: SQS is at-least-once, so duplicates can occur even when partial responses work properly.

## 18. Differences Among SQS, Kinesis, and DynamoDB Streams

**ReportBatchItemFailures** exists across multiple event source types, yet **identifiers and retry semantics differ**.

| Source | Identifier in Partial Failure | Characteristics |
| --- | --- | --- |
| **SQS** | **messageId** | Returns unprocessed SQS messages for retry |
| **Kinesis Data Streams** | **sequenceNumber** | Checkpoints by sequence; retries records from checkpoint |
| **DynamoDB Streams** | **sequenceNumber** | Similar stream checkpoint; not an SQS messageId |

**Do not copy SQSBatchResponse and messageId code to Kinesis/DynamoDB Streams**. Those sources use different event/response types and batch splitting/retry rules. This lesson only addresses **SQS triggers via Lambda event source mapping**.

Similarly, **API Gateway** and **S3 asynchronous notifications** do not read **SQSBatchResponse** to determine HTTP responses or retry object notifications. If the architecture is **S3 → SQS → Lambda**, the outer invocation is still **SQSEvent**; each SQS body may contain S3 notification JSON. When reporting failures, **itemIdentifier remains the SQS messageId**.

## 19. Idempotency: The Non-Negotiable Part

Suppose the processor handles **CREATE** by writing to a database. The hard scenario:

1. Lambda receives a message with eventId **evt-101**.
2. DB commit succeeds.
3. Lambda times out or the response is lost before AWS acknowledges it.
4. SQS redelivers the same message or the producer resends the same business event.
5. The processor runs again and risks creating a duplicate record.

Partial batch responses do not close the gap between **side effect commit** and **batch outcome acknowledgment**. Storage-level idempotency is required:

~~~mermaid
flowchart TD
    A["OrderEvent eventId"] --> B{"eventId already processed?"}
    B -- "Yes" --> C["Return success/no-op"]
    B -- "No" --> D["Transaction"]
    D --> E["Apply business change"]
    E --> F["Record processed eventId"]
    F --> G["Commit"]
    G --> H["Record success"]
~~~

Common strategies:

- **Unique constraint** on eventId or business operation key.
- **Transactional inbox** or deduplication table within the same business transaction.
- **Outbox** when both updating a DB and publishing messages.
- **Idempotency token** for external APIs when supported downstream.
- **Conditional write** in databases such as DynamoDB when appropriate.

**Do not assume SQS messageId is always the optimal business idempotency key**. A producer may resend the same business event as a new SQS message with a different messageId. When the contract has a stable producer-controlled **eventId**, use eventId/business key for deduplication.

An already-processed record can be treated as a **success** if durable state proves the side effect already completed. Do not report it as an infinite failure merely because a duplicate was detected.

## 20. Monitoring: Invocation Success Does Not Tell the Whole Story

When code catches per-record failures and returns a valid **SQSBatchResponse**, the Lambda invocation may **count as successful at the function level** even while containing many item failures.

Therefore, watching only Lambda's **Errors** metric can miss thousands of retrying messages. Add record-level metrics:

| Metric / Signal | What You Want to Detect |
| --- | --- |
| **RecordsReceived** | Number of records received from the batch |
| **RecordsSucceeded** | Number of records that completed work |
| **RecordsFailed** | Number of records reported in batchItemFailures |
| **FailureByReason** | Validation, transient, dependency, unknown |
| **SQS ApproximateAgeOfOldestMessage** | Growing backlog |
| **SQS ApproximateNumberOfMessagesVisible** | Unprocessed volume |
| **DLQ message count** | Poison messages exceeding retry threshold |
| **Lambda Duration/Throttles** | Abnormal processing speed or capacity |
| **EventSourceMapping state** | Poller is active and configured properly |

The names **RecordsReceived/RecordsFailed** here are **suggested custom metrics**, not built-in AWS metrics with those exact names.

**Do not log full message bodies**, as they may contain personal data, tokens, or order details. Log minimal fields such as **messageId**, error type, approximate receive count, controlled correlation ID, and processing outcome.

AWS also recommends tracking SQS metrics such as **NumberOfMessagesDeleted** and **ApproximateAgeOfOldestMessage** to catch abnormal processing after enabling partial responses.

## 21. What Role Does AWS Powertools Batch Processing Play?

If a production application processes large batches with multiple failure strategies, you do not have to write the entire loop manually. **Powertools for AWS Lambda (Java)** provides a **Batch Processing** utility supporting per-record logic and building partial batch responses per AWS's contract.

Potential benefits:

- Reduces boilerplate for collecting failures.
- Standardizes part of Standard/FIFO processing structure.
- Integrates logging, metrics/tracing, and idempotency utilities where appropriate.
- Simplifies testing retry/record-error policies when using supported APIs.

However, the utility does not automatically decide **whether a business operation is safe to retry**, provision IAM permissions, or turn a non-idempotent side effect into exactly-once.

When using it, **pin a Powertools version compatible with your project's Java/build setup** and read the API docs for that exact version. This lesson writes a plain Java implementation so learners clearly see every piece of the contract before adopting a utility.

## 22. Common Deployment Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Failed messages vanish despite being in failures | Mapping lacks **ReportBatchItemFailures** | Inspect FunctionResponseTypes |
| Entire batch is retried | Handler throws exception or invalid response schema | Inspect logs, itemIdentifier, JSON |
| AWS rejects response as invalid | Empty/null/wrong itemIdentifier | Use exact batch messageIds |
| FIFO breaks ordering | Continued processing records after a failure | Stop and return unprocessed IDs too |
| All records acked despite not running | Caught exception and returned empty/null failures | Audit per-record failure tracking |
| Poison message retries endlessly | Missing DLQ/RedrivePolicy | Check maxReceiveCount, retention |
| Processed message runs repeatedly | At-least-once, timeout/lost response | Design storage-level idempotency |
| SQS body JSON parse error | Confused Records with business body | Parse each message.getBody() |
| Lambda fails with ClassNotFound | Missing adapter or bad shaded JAR | Check FunctionInvoker.class |
| Spring fails to pick Function | Wrong definition or bean name | Check FunctionCatalog.lookup and env |
| EventSourceMapping does not poll queue | Missing IAM/KMS policy or wrong ARN/region | Check mapping state/LastProcessingResult |
| Many failures while Lambda Errors stay low | Partial response still counts as function success | Add custom record metrics + SQS/DLQ metrics |
| Wrong FIFO policy | Standard processing reused for FIFO | Pick processFifoSqs and test ordering |
| Prolonged infra outage keeps polling high | ReportBatchItemFailures does not slow polling automatically | Limit concurrency/backoff, alert downstream |
| Side effect committed then response failed | No atomic commit with ack | Idempotency key and transaction/outbox |
| Consumer cannot return failed IDs | Used Consumer<SQSEvent> | Switch to Function<SQSEvent,SQSBatchResponse> |
| Lambda retries wrong S3 eventId | S3 message nested in SQS body | ItemIdentifier remains SQS messageId |

## 23. Hands-on Exercises

**Exercise 1 — Default vs. partial response.** A Standard batch has message IDs **a**, **b**, **c**; b fails after a completes. Explain the outcome if the handler throws an exception, if it catches the error and returns an empty response, and if it returns the proper failure list.

**Exercise 2 — JSON contract.** Build a response reporting only **b** and **d** as failed in batch **a,b,c,d,e**. Write a test proving **messageId** is used rather than a business eventId or receiptHandle.

**Exercise 3 — FIFO.** For batch **a,b,c,d** in the same message group, a succeeds and b fails. Write the output and a test verifying the processor was never invoked for c/d.

**Exercise 4 — Picking the right policy.** In a system where a batch is processed in a single monolithic database transaction, would acknowledging individual records violate the contract? Analyze failing the whole batch versus redesigning per-record transactions.

**Exercise 5 — AWS wiring.** Deploy a SAM Standard SQS setup with a DLQ, 30-second Lambda timeout, suitable visibility timeout, BatchSize 10, and FunctionResponseTypes. Read back the event source mapping via CLI after deployment.

**Exercise 6 — Poison pill.** A message always contains malformed JSON. Propose maxReceiveCount, DLQ retention, alarms, an inspect/replay workflow, and how to prevent the snowball effect.

**Exercise 7 — Idempotency.** After committing to the database, Lambda times out so the message is redelivered. Design a unique constraint/transaction or conditional write keyed by eventId to ensure side effects do not repeat.

**Exercise 8 — Mixed errors.** A batch contains one message with a permanent validation error and one with a transient API timeout. Design per-type handling policies, logging, and actions once messages reach the DLQ.

**Exercise 9 — Configuration bug.** Java unit tests return the right batchItemFailures, yet Lambda deletes every message. Outline the inspection order across Handler, FunctionCatalog, event source mapping, FunctionResponseTypes, output serialization, and version/alias.

**Exercise 10 — Observability.** Lambda Errors sit near zero while the DLQ grows steadily. Propose custom record metrics, SQS queue metrics, and alarms based on failed-record rates instead of relying solely on invocation-level errors.

### Key Takeaways

- **SQS event source mapping delivers batched Records**. If an invocation fails, by default the entire batch can be redelivered, including records that already succeeded.
- **Partial batch responses work properly only when ReportBatchItemFailures is enabled and valid batchItemFailures are returned**. Returning failed IDs without enabling the flag is a dangerous deployment mistake.
- **itemIdentifier must be an SQS messageId from the batch**. Empty IDs, wrong keys, or nonexistent IDs can cause the entire batch to be treated as failed.
- **Standard** queues can report failed records independently. **FIFO** queues must stop on failure and report both the failed record and unprocessed records to preserve ordering.
- **Function<SQSEvent,SQSBatchResponse>** is the right contract when using Spring Cloud Function + FunctionInvoker. A Consumer cannot return partial responses on its own.
- **DLQ, idempotency, retries, visibility timeout, IAM, and record-level metrics** remain essential. Partial responses reduce unnecessary retries yet do not guarantee exactly-once.
- **Not every workload should enable it**: atomic batches, global system outages, or complex FIFO ordering require another strategy or additional testing.

### References

- [Spring Cloud Function — AWS Lambda adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker and Function<SQSEvent,SQSBatchResponse> types.
- [AWS Lambda — Handling errors for an SQS event source](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html): ReportBatchItemFailures, success/failure conditions, FIFO, and scaling behavior.
- [AWS Lambda — SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html): visibility timeout, IAM, batch window, and DLQ.
- [AWS Lambda — Using Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html): at-least-once, polling, visibility timeout, Standard/FIFO.
- [AWS Lambda — Java partial batch example](https://docs.aws.amazon.com/lambda/latest/dg/example_serverless_SQS_Lambda_batch_item_failures_section.html): SQSBatchResponse Java API and BatchItemFailure.
- [AWS SAM — SQS event source](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-sqs.html): FunctionResponseTypes, BatchSize, and source properties.
- [AWS Prescriptive Guidance — Partial batch response best practices](https://docs.aws.amazon.com/prescriptive-guidance/latest/lambda-event-filtering-partial-batch-responses-for-sqs/best-practices-partial-batch-responses.html): DLQ, idempotency, monitoring, and avoiding the snowball pattern.
