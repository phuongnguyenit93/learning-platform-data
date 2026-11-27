# Handling API Gateway, S3, and SQS Event Structures

A **Function<T, R>** bean in **SPRING_CLOUD_FUNCTION** can be reused across HTTP, events, or serverless. However, when that bean is invoked through **AWS Lambda**, the input is not always pure business JSON. **API Gateway** sends a *proxy event* containing method, route, headers, and body; **Amazon S3** sends a notification about an object in a bucket; **Amazon SQS** sends a batch of multiple messages with their own bodies and metadata. To handle them accurately, you must understand **event envelope structures**, choose suitable Java types, and establish conversion boundaries before invoking business logic.

This lesson belongs to the **AWS Lambda** chapter. We will analyze all three event types, implement Spring Cloud Function beans using **FunctionInvoker** and **FunctionCatalog**, handle API Gateway payloads 1.0/2.0, decode S3 object keys, process SQS batches and partial failures, configure AWS SAM, test, and troubleshoot errors. Examples use Java 17+ and the **Spring Boot 3.x/Jackson 2** approach; if using another library generation, align APIs/serializers with your project's compatible BOM.

## 1. Distinguishing Business Payload from AWS Event Envelopes

Suppose our business logic accepts a quote request:

~~~json
{
  "requestId": "REQ-101",
  "sku": "BOOK",
  "quantity": 2
}
~~~

This is the **business payload**. When passing through AWS, it can appear in different places:

| Trigger Source | Unit AWS Delivers to Lambda | Location of Business Payload | Response Behavior |
| --- | --- | --- | --- |
| **API Gateway proxy** | An HTTP request event | Typically the **body** string in the event | Lambda returns a response to the HTTP client matching the payload format |
| **S3 notification** | A notification with **Records** | No file contents; only bucket/key/metadata | Asynchronous invocation; output is not an HTTP response |
| **SQS trigger** | A batched **Records** event | Each **record.body** is typically a message string | Lambda/poller decides to delete or redeliver messages based on processing results |

~~~mermaid
flowchart TD
    A["AWS Source"] --> B{"Event type"}
    B --> C["API Gateway envelope"]
    B --> D["S3 notification"]
    B --> E["SQS batch"]
    C --> F["Extract/decode body"]
    D --> G["Read bucket + URL-decode key"]
    E --> H["Iterate Records, parse each body"]
    F --> I["Business DTO"]
    G --> J["Object reference / S3 client"]
    H --> K["Per-message DTO"]
    I --> L["Business Function"]
    J --> L
    K --> L
~~~

**FunctionInvoker is not a magic tool that automatically understands every envelope.** The AWS adapter reads the invocation stream and attempts to convert it into the declared type T, or passes the raw **InputStream** if the Function accepts that type. To unwrap an HTTP body, distinguish an S3 key from file bytes, or process individual SQS records, you often need an **application business adapter**.

## 2. Recommended Architecture with Spring Cloud Function

Keep the core receiving and returning AWS-independent Java types:

~~~java
public record QuoteRequest(
    String requestId,
    String sku,
    Integer quantity
) {}

public record QuoteResult(
    String requestId,
    String sku,
    int quantity,
    long subtotal
) {}
~~~

Example business service:

~~~java
public final class QuoteService {

    public QuoteResult quote(QuoteRequest request) {
        if (request == null
                || request.requestId() == null
                || request.requestId().isBlank()
                || request.sku() == null
                || request.sku().isBlank()
                || request.quantity() == null
                || request.quantity() < 1
                || request.quantity() > 1000) {
            throw new IllegalArgumentException(
                "Invalid quote request");
        }

        String sku = request.sku()
            .trim().toUpperCase(java.util.Locale.ROOT);

        // Illustrative price table: a single SKU.
        if (!"BOOK".equals(sku)) {
            throw new IllegalArgumentException("Unknown SKU");
        }

        long subtotal = Math.multiplyExact(
            85_000L, request.quantity());

        return new QuoteResult(
            request.requestId().trim(),
            sku,
            request.quantity(),
            subtotal);
    }
}
~~~

From here, each AWS source gets its own adapter layer:

~~~text
API Gateway event -> HTTP adapter -> QuoteRequest -> QuoteService
S3 event          -> S3 adapter   -> ObjectReference -> S3 processor
SQS batch         -> SQS adapter  -> each Message DTO -> Message processor
~~~

**Do not cram every event type into a single Function<Map<String, Object>, Object>** just to reduce bean count. Doing so loses schema clarity, complicates contract testing, and couples business logic to AWS-provided structures. When supporting multiple triggers, you can create multiple Lambda resources sharing one shaded JAR, each with its own **spring_cloud_function_definition**.

## 3. Commonly Involved Dependencies

A Spring Cloud Function AWS application needs the adapter and libraries matching its event types:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-adapter-aws</artifactId>
    </dependency>

    <!-- Declare explicitly only when code uses AWS event classes. -->
    <dependency>
        <groupId>com.amazonaws</groupId>
        <artifactId>aws-lambda-java-events</artifactId>
    </dependency>

    <!-- ObjectMapper used in the Spring Boot 3 / Jackson 2 example. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This is only a **dependencies snippet**, not a complete POM. Boot, Spring Cloud/Function, **aws-lambda-java-events**, and Jackson versions must be locked and managed compatibly in the build. Do not arbitrarily combine the latest versions outside a verified combination.

**aws-lambda-java-events** provides classes such as **S3Event**, **SQSEvent**, and **SQSBatchResponse**. It differs from **AWS SDK for Java v2**: the SDK is used when your application calls S3/SQS services, whereas the event classes only model the events Lambda receives. If you do not read S3 objects or call AWS APIs, you do not need the full AWS SDK.

**You do not need spring-cloud-starter-function-web just to handle API Gateway Lambda events.** The web starter adapts Spring Cloud Function to an HTTP server; API Gateway Lambda proxy and the Spring Cloud Function AWS adapter are a different deployment path. For a Spring MVC application keeping many controllers, Serverless Java Container can be considered, but that is not this lesson's model.

## 4. API Gateway: Events Are More Than Just the HTTP Body

API Gateway proxy integration maps an HTTP request into a Lambda invocation event. Two common formats:

- **REST API proxy / payload 1.0**: typically has **httpMethod**, **path**, **headers**, **multiValueHeaders**, **queryStringParameters**, **multiValueQueryStringParameters**, **requestContext**, **body**, **isBase64Encoded**.
- **HTTP API / payload 2.0**: has **version=2.0**, **routeKey**, **rawPath**, **rawQueryString**, **requestContext.http.method**, **headers**, possibly **cookies**, **body**, **isBase64Encoded**. Does not use **multiValueHeaders** and **multiValueQueryStringParameters** like v1.

| Element | API Gateway 1.0 | API Gateway 2.0 |
| --- | --- | --- |
| HTTP method | **httpMethod** | **requestContext.http.method** |
| URL path | **path** | **rawPath** |
| Query string | **queryStringParameters** and possibly **multiValueQueryStringParameters** | **rawQueryString** + **queryStringParameters** |
| Repeated headers | May use **multiValueHeaders** | Duplicate values may be comma-joined |
| Cookies | Usually inside headers | Dedicated **cookies** field |
| HTTP body | **body** (String) | **body** (String) |
| Binary payload | **isBase64Encoded** | **isBase64Encoded** |
| Response | Proxy response with statusCode/body | Can return explicit proxy response or certain JSON outputs inferred by API Gateway |

**Using HTTP does not mean the same event schema.** You must know whether you are using REST API or HTTP API and which **payloadFormatVersion** applies. Do not guess the version solely from the API name or route path.

### 4.1. Simplified REST API 1.0 Event

~~~json
{
  "resource": "/quotes",
  "path": "/quotes",
  "httpMethod": "POST",
  "headers": {
    "content-type": "application/json"
  },
  "multiValueHeaders": {
    "x-request-tag": ["one", "two"]
  },
  "queryStringParameters": null,
  "requestContext": {
    "requestId": "api-req-001",
    "stage": "prod"
  },
  "body": "{\"requestId\":\"REQ-101\",\"sku\":\"BOOK\",\"quantity\":2}",
  "isBase64Encoded": false
}
~~~

**body is a JSON string nested inside the JSON event**. If Java code deserializes the entire object above into **QuoteRequest**, the requestId/sku/quantity fields are not at the root; conversion may fail or produce an empty object depending on the mapper.

### 4.2. Simplified HTTP API 2.0 Event

~~~json
{
  "version": "2.0",
  "routeKey": "POST /quotes",
  "rawPath": "/quotes",
  "rawQueryString": "",
  "headers": {
    "content-type": "application/json"
  },
  "requestContext": {
    "requestId": "api-req-002",
    "http": {
      "method": "POST",
      "path": "/quotes",
      "protocol": "HTTP/1.1"
    }
  },
  "body": "{\"requestId\":\"REQ-101\",\"sku\":\"BOOK\",\"quantity\":2}",
  "isBase64Encoded": false
}
~~~

In practice there can be many additional fields. Do not write a parser that only accepts the exact fields of one example; use DTOs declaring the needed fields and handling unknown fields gracefully.

### 4.3. Reading body and isBase64Encoded

Workflow for an HTTP API v2 adapter:

1. Check **version**, route/method against the registered contract.
2. Read **body** and check **isBase64Encoded**.
3. If true, Base64-decode body; if false, interpret the string using the supported encoding (typically UTF-8 for JSON).
4. Enforce size/content-type limits and parse JSON into a DTO.
5. Validate the DTO, then invoke the business core.
6. Build a **response envelope** with the properly formatted HTTP status and body.

~~~mermaid
flowchart LR
    A["HTTP API v2 event"] --> B["body + isBase64Encoded"]
    B --> C["Decode bytes"]
    C --> D["QuoteRequest"]
    D --> E["QuoteService.quote"]
    E --> F["QuoteResult"]
    F --> G["Proxy HTTP response"]
~~~

**HTTP status is not derived automatically from Java exceptions.** With Lambda proxy, the adapter layer must construct a response matching the payload format API Gateway expects. Returning only a **QuoteResult** DTO may let HTTP API v2 infer a response in some cases; with REST API proxy v1, an unexpected schema can cause API Gateway to return **502**.

## 5. Java Example: HTTP API 2.0 Adapter

File **src/main/java/example/lambda/HttpApiApplication.java**. This is a Java 17+ example using **Jackson 2**; if your project uses Jackson 3, update packages/APIs for your current version.

~~~java
package example.lambda;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;
import java.util.function.Function;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HttpApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpApiApplication.class, args);
    }

    // Select only the needed fields of the HTTP API v2 envelope.
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record HttpApiV2Event(
        String version,
        String routeKey,
        String rawPath,
        String body,
        Boolean isBase64Encoded
    ) {}

    public record QuoteRequest(
        String requestId,
        String sku,
        Integer quantity
    ) {}

    public record QuoteResult(
        String requestId,
        String sku,
        int quantity,
        long subtotal
    ) {}

    public record ApiError(
        String code,
        String message
    ) {}

    // Response envelope for API Gateway proxy.
    public record ProxyResponse(
        int statusCode,
        Map<String, String> headers,
        String body,
        boolean isBase64Encoded
    ) {}

    public static final class QuoteService {

        public QuoteResult quote(QuoteRequest request) {
            if (request == null
                    || request.requestId() == null
                    || request.requestId().isBlank()
                    || request.sku() == null
                    || request.sku().isBlank()
                    || request.quantity() == null
                    || request.quantity() < 1
                    || request.quantity() > 1000) {
                throw new IllegalArgumentException(
                    "Invalid quote request");
            }

            String sku = request.sku()
                .trim().toUpperCase(java.util.Locale.ROOT);

            if (!"BOOK".equals(sku)) {
                throw new IllegalArgumentException(
                    "Unknown SKU");
            }

            return new QuoteResult(
                request.requestId().trim(),
                sku,
                request.quantity(),
                Math.multiplyExact(
                    85_000L,
                    request.quantity()));
        }
    }

    @Bean
    QuoteService quoteService() {
        return new QuoteService();
    }

    @Bean("httpQuoteV2")
    Function<HttpApiV2Event, ProxyResponse> httpQuoteV2(
            QuoteService service, ObjectMapper mapper) {

        return event -> {
            if (event == null
                    || !"2.0".equals(event.version())
                    || !"POST /quotes".equals(event.routeKey())
                    || event.body() == null) {
                return jsonResponse(mapper, 400,
                    new ApiError(
                        "BAD_ENVELOPE", "Invalid API event"));
            }

            try {
                byte[] body = Boolean.TRUE.equals(
                        event.isBase64Encoded())
                    ? Base64.getDecoder().decode(event.body())
                    : event.body().getBytes(StandardCharsets.UTF_8);

                // Illustrative application limit, not an AWS limit.
                if (body.length > 64 * 1024) {
                    return jsonResponse(mapper, 413,
                        new ApiError(
                            "PAYLOAD_TOO_LARGE", "Body too large"));
                }

                QuoteRequest request =
                    mapper.readValue(body, QuoteRequest.class);

                QuoteResult result = service.quote(request);
                return jsonResponse(mapper, 200, result);

            } catch (java.io.IOException
                     | IllegalArgumentException ex) {
                return jsonResponse(mapper, 400,
                    new ApiError(
                        "INVALID_REQUEST",
                        "Quote request is invalid"));
            }
        };
    }

    private static ProxyResponse jsonResponse(
            ObjectMapper mapper, int status, Object payload) {
        try {
            return new ProxyResponse(
                status,
                Map.of("content-type", "application/json"),
                mapper.writeValueAsString(payload),
                false
            );
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Could not serialize API response", ex);
        }
    }
}
~~~

This example only serves **POST /quotes** with HTTP API payload **2.0**. Do not assume this record deserializes REST API 1.0 events or integrations with custom mappings.

### Why Is Output body a String?

A well-formed proxy response:

~~~json
{
  "statusCode": 200,
  "headers": {
    "content-type": "application/json"
  },
  "body": "{\"requestId\":\"REQ-101\",\"sku\":\"BOOK\",\"quantity\":2,\"subtotal\":170000}",
  "isBase64Encoded": false
}
~~~

The **body** field is a **JSON string** containing the serialized business result. Returning a nested JSON object directly under body can violate the proxy v1 contract and behave inconsistently across integrations.

### Limitations of the Example

- No authentication/authorization. Production requires an authorizer/IAM at API Gateway or equivalent mechanism plus business permission checks.
- Do not treat HTTP headers as security proof unless verified at a trusted boundary.
- Parse/validation errors map to 400; 404/422 policies for business rejections depend on your API contract.
- Do not catch and convert every infrastructure exception into 400: unexpected failures should flow through controlled error/observability mechanisms or appropriate 5xx mappings.
- If multiple routes or REST API 1.0 are needed, build a dedicated adapter layer or use a framework supporting proxy integration appropriately.

## 6. API Gateway v1/v2: Responses and Common Pitfalls

| Scenario | Risk | Resolution |
| --- | --- | --- |
| Reading **httpMethod** from a v2 event | Field does not exist there | Use **requestContext.http.method** or routeKey |
| Handling repeated headers identically in v1/v2 | Loss of multi-value info | Check multiValueHeaders/cookies/combined values |
| Parsing entire envelope into QuoteRequest | DTO misses business fields | Read **body** before parsing |
| Ignoring isBase64Encoded | Body bytes misinterpreted | Decode per flag, check content type |
| Returning **QuoteResult** as a v1 response | API Gateway may return 502 | Build proper **statusCode/body** proxy response |
| Trusting client-supplied auth fields | Authorization bypass | Use verified authorizer output or IAM |
| Logging all headers/body | Leaks tokens, PII | Log only controlled minimal metadata |

With **HTTP API 2.0**, if Lambda returns valid JSON **without statusCode**, API Gateway can infer status 200 and JSON content-type. This is a capability of **payload format 2.0**, not something to copy blindly for REST API proxy 1.0. If the API needs 400/404/422/500 statuses, return an explicit proxy response and test via real HTTP integration.

## 7. S3: Understanding Records and Object References

When an object is created/deleted or matches a configured event type, Amazon S3 can send an **event notification** to Lambda. The event contains **information about the object event**, not the full bytes of the file in the bucket.

A simplified notification:

~~~json
{
  "Records": [
    {
      "eventVersion": "2.1",
      "eventSource": "aws:s3",
      "awsRegion": "ap-southeast-1",
      "eventTime": "2026-01-15T08:00:00.000Z",
      "eventName": "ObjectCreated:Put",
      "s3": {
        "bucket": {
          "name": "sample-input-bucket"
        },
        "object": {
          "key": "incoming%2Freport+nov%2Bfinal.csv",
          "size": 256,
          "eTag": "sample-etag",
          "sequencer": "0066AABBCCDDEEFF"
        }
      }
    }
  ]
}
~~~

Key fields from the event above:

| Field | Meaning |
| --- | --- |
| **Records** | List of records delivered in the notification |
| **eventSource** | Identifies source, e.g., **aws:s3** |
| **eventVersion** | Schema version of the S3 notification |
| **eventName** | Operation type, e.g., **ObjectCreated:Put** |
| **awsRegion** | Region of the event/bucket |
| **s3.bucket.name** | Bucket holding the object |
| **s3.object.key** | **URL-encoded** object key |
| **s3.object.size** | Object size when present |
| **s3.object.versionId** | May appear for versioned buckets |
| **s3.object.sequencer** | Used to compare event order for **the same object key** |

### 7.1. The Object Key Must Be Decoded Properly

S3 notifications encode object keys using **application/x-www-form-urlencoded**:

~~~text
Event key:
  incoming%2Freport+nov%2Bfinal.csv

Decoded key:
  incoming/report nov+final.csv
~~~

In Java:

~~~java
String decoded = java.net.URLDecoder.decode(
    encodedKey,
    java.nio.charset.StandardCharsets.UTF_8);
~~~

**URLDecoder** turns **+** into spaces and **%2B** into a literal plus sign. Do not decode twice, which can corrupt keys unexpectedly. Do not use a generic URI path decoder if it treats **+** differently from the form encoding used by S3 notifications.

### 7.2. S3 Test Events Have a Different Shape

When configuring event notifications, Amazon S3 can send a test message like:

~~~json
{
  "Service": "Amazon S3",
  "Event": "s3:TestEvent",
  "Time": "2026-01-15T08:00:00.000Z",
  "Bucket": "sample-input-bucket",
  "RequestId": "sample-request-id"
}
~~~

**s3:TestEvent has no Records** like object-created notifications. If a Function declares **Function<S3Event, R>** and immediately iterates Records, the test event may fail to map or be rejected. If your application must accept both forms, handle test events in an InputStream/JsonNode adapter or inspect the schema before using S3Event.

### 7.3. Schema Versions and Notification Ordering

S3 notification schemas have multiple **2.x** versions and may add new fields or event types. AWS documentation recommends checking the expected major version while accepting compatible newer minor versions; do not hard-code a parser to require the exact string **2.1**.

**S3 does not guarantee all notifications arrive in order or without duplicates**. For create/delete events with **sequencer**, only compare sequencers that refer to **the same object key**; never compare across different keys. VersionId or sequencer can support idempotency/ordering per business rules, provided you design durable state storage.

## 8. Spring Cloud Function Example with S3Event

**aws-lambda-java-events** provides **com.amazonaws.services.lambda.runtime.events.S3Event**. A Function can receive this type directly when the adapter converts it successfully.

File **src/main/java/example/lambda/S3EventFunctions.java**, placed in a package scanned by Spring Boot:

~~~java
package example.lambda;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.function.Function;

import com.amazonaws.services.lambda.runtime.events.S3Event;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class S3EventFunctions {

    public record S3ObjectReference(
        String bucket,
        String key,
        String eventName,
        String versionId
    ) {}

    @Bean("inspectS3Notifications")
    Function<S3Event, List<S3ObjectReference>>
            inspectS3Notifications() {

        return event -> {
            if (event == null || event.getRecords() == null) {
                throw new IllegalArgumentException(
                    "S3 notification Records are required");
            }

            return event.getRecords().stream()
                .map(record -> {
                    if (record.getS3() == null
                            || record.getS3().getBucket() == null
                            || record.getS3().getObject() == null) {
                        throw new IllegalArgumentException(
                            "S3 bucket/object is missing");
                    }

                    String bucket =
                        record.getS3().getBucket().getName();

                    String key = decodeS3Key(
                        record.getS3().getObject().getKey());

                    return new S3ObjectReference(
                        bucket,
                        key,
                        record.getEventName(),
                        record.getS3().getObject().getVersionId()
                    );
                })
                .toList();
        };
    }

    public static String decodeS3Key(String encodedKey) {
        if (encodedKey == null || encodedKey.isBlank()) {
            throw new IllegalArgumentException("S3 key is missing");
        }

        return URLDecoder.decode(
            encodedKey, StandardCharsets.UTF_8);
    }
}
~~~

This Function **only reads metadata**, does not download files, and causes no side effects. For events with multiple Records, the output is **List<S3ObjectReference>**; however, responses from asynchronously S3-triggered Lambdas are typically not consumed like HTTP client responses.

### What About Reading Object Contents?

Separate a dedicated S3-access interface:

~~~java
public interface ObjectContentReader {
    java.io.InputStream open(String bucket, String key);
}
~~~

Implementations can use **AWS SDK for Java v2 S3Client** or an appropriate async client, along with **s3:GetObject** permissions for the exact bucket/prefix. When consuming content streams from the SDK, manage stream closing and file sizes carefully. **FunctionInvoker's InputStream is the event stream**, not the S3 object content stream.

### Preventing Infinite Lambda Trigger Loops

If a Lambda receives **ObjectCreated** on prefix **incoming/** and writes output back into the same prefix, the new object can trigger the Lambda again endlessly. Solution: use a separate bucket or configure distinct notification filters for input and output prefixes, alongside idempotency.

## 9. SQS: One Invocation Contains Multiple Records

Lambda uses an **event source mapping** to poll an SQS queue. When messages arrive, AWS batches one or more messages into **a single invocation event**.

Simplified example:

~~~json
{
  "Records": [
    {
      "messageId": "msg-001",
      "receiptHandle": "sample-receipt-handle-1",
      "body": "{\"eventId\":\"EVT-001\",\"orderId\":\"ORD-101\"}",
      "attributes": {
        "ApproximateReceiveCount": "1"
      },
      "messageAttributes": {},
      "md5OfBody": "sample-md5",
      "eventSource": "aws:sqs",
      "eventSourceARN": "arn:aws:sqs:ap-southeast-1:123456789012:order-events",
      "awsRegion": "ap-southeast-1"
    },
    {
      "messageId": "msg-002",
      "receiptHandle": "sample-receipt-handle-2",
      "body": "{\"eventId\":\"EVT-002\",\"orderId\":\"ORD-102\"}",
      "attributes": {
        "ApproximateReceiveCount": "1"
      },
      "messageAttributes": {},
      "md5OfBody": "sample-md5",
      "eventSource": "aws:sqs",
      "eventSourceARN": "arn:aws:sqs:ap-southeast-1:123456789012:order-events",
      "awsRegion": "ap-southeast-1"
    }
  ]
}
~~~

Some fields are abbreviated or sample values; real events contain metadata depending on queue type and configuration.

| Field | What to Remember |
| --- | --- |
| **Records** | A batch; do not treat as a single message |
| **messageId** | ID of the SQS message; used to report partial batch failures |
| **body** | String carrying application content, JSON or otherwise |
| **attributes** | System metadata, e.g., receive count; FIFO includes group info |
| **messageAttributes** | Producer-supplied attributes, distinct from JSON inside body |
| **eventSourceARN** | ARN of the source queue |
| **receiptHandle** | Used by receive/delete APIs, not a substitute for messageId in batch failure responses |

**If a producer sends an OrderEvent JSON to SQS, it lives inside each record.body as a String**. Do not deserialize the entire SQS event into a single OrderEvent.

### 9.1. Batching and Visibility Timeout

When the poller hands a batch to Lambda, messages in the batch are hidden for the **visibility timeout**. If the batch succeeds, Lambda normally deletes the processed messages. If the invocation fails, messages can reappear after the timeout and be redelivered.

Consequently, the system must tolerate **at-least-once processing** rather than assuming every message runs only once.

### 9.2. Standard and FIFO Queues Differ

- **Standard SQS**: can deliver many messages concurrently with no strict ordering guarantee; process records independently when appropriate.
- **FIFO SQS**: supports ordering per **MessageGroupId**; when reporting partial failures, AWS recommends stopping at the first failure and reporting all remaining unprocessed messages as failed to preserve order.
- **BatchSize** and batching windows have different limits between Standard and FIFO. Do not copy a large Standard batch config to FIFO without checking limits.

## 10. SQS Partial Batch Response: Exact Structure

Suppose a batch has three messages: **msg-001** valid, **msg-002** invalid, **msg-003** valid. If the Function **throws an exception** to the Lambda runtime, by default **the entire batch** can be considered failed and already-processed messages may be redelivered.

If **ReportBatchItemFailures** is enabled, the Function can return:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "msg-002"
    }
  ]
}
~~~

**itemIdentifier must be the SQS messageId**, not a business eventId, orderId, receiptHandle, or S3 sequencer. Return failures using the exact messageIds present in the batch.

~~~mermaid
flowchart TD
    A["SQS batch: 001, 002, 003"] --> B["Process each record"]
    B --> C["001 succeeds"]
    B --> D["002 fails"]
    B --> E["003 succeeds"]
    C --> F["Partial batch response"]
    D --> F
    E --> F
    F --> G["batchItemFailures = [002]"]
    G --> H["AWS can retry 002"]
~~~

**Three conditions for partial responses to take effect:**

1. Event source mapping is configured with **FunctionResponseTypes: ReportBatchItemFailures**.
2. The Function returns the exact **batchItemFailures** schema without throwing an unhandled exception for the whole invocation.
3. Successful records have genuinely completed per the business contract; silently swallowing an exception without reporting failure can cause AWS to consider the message done.

With FIFO, upon encountering an error, stop processing further and include **the failed message plus all unprocessed messages** in **batchItemFailures**. Failing to follow this rule can break ordering guarantees within the message group.

## 11. Spring Cloud Function Example with SQSEvent and SQSBatchResponse

File **src/main/java/example/lambda/SqsEventFunctions.java**:

~~~java
package example.lambda;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class SqsEventFunctions {

    public record OrderEvent(
        String eventId,
        String orderId
    ) {}

    @Bean("validateSqsBatch")
    Function<SQSEvent, SQSBatchResponse> validateSqsBatch(
            ObjectMapper mapper) {

        return event -> {
            if (event == null || event.getRecords() == null) {
                throw new IllegalArgumentException(
                    "SQS Records are required");
            }

            List<SQSBatchResponse.BatchItemFailure> failures =
                new ArrayList<>();

            // Example: validates only each record's JSON/schema.
            // Production must invoke durable business processing here.
            for (SQSEvent.SQSMessage message : event.getRecords()) {
                try {
                    OrderEvent input = mapper.readValue(
                        message.getBody(),
                        OrderEvent.class);

                    validateOrderEvent(input);

                } catch (JsonProcessingException
                         | IllegalArgumentException ex) {
                    failures.add(
                        new SQSBatchResponse.BatchItemFailure(
                            message.getMessageId()));
                }
            }

            return new SQSBatchResponse(failures);
        };
    }

    private static void validateOrderEvent(OrderEvent input) {
        if (input == null
                || input.eventId() == null
                || input.eventId().isBlank()
                || input.orderId() == null
                || input.orderId().isBlank()) {
            throw new IllegalArgumentException(
                "Invalid order event");
        }
    }
}
~~~

In this example, **success** only means **the message JSON has a valid structure**. This is a **data-contract validation Lambda**, not a complete consumer for payments or order updates. For real business processing, invoke the repository/service and complete side effects **before considering a record successful**.

### Where Business Processing Goes in Production

~~~java
OrderEvent input = mapper.readValue(
    message.getBody(), OrderEvent.class);
validateOrderEvent(input);

// Requires a real transactional/idempotent service implementation:
orderEventProcessor.applyOnce(input.eventId(), input.orderId());
~~~

The line **orderEventProcessor.applyOnce(...)** here is a **design pattern**, not yet defined in the Java example above. It needs an implementation backed by appropriate storage/transactions; do not replace it with a singleton HashSet if deduplication must hold across restarts and multiple Lambda execution environments.

Do not catch every **Throwable** just to mark a single record as failed: severe system or infrastructure failures may need to fail the whole invocation per incident policies. In production, clearly distinguish permanent parse errors, business rejections, and transient service errors; report recoverable record failures for proper retry.

## 12. SQS FIFO: Stop at the First Error

The **validateSqsBatch** example above fits independent records on a **Standard queue** where you want to list every invalid record. With FIFO, change the loop to preserve ordering:

~~~java
// Replacement snippet for the loop in a FIFO-processing Function.
List<SQSBatchResponse.BatchItemFailure> failures =
    new java.util.ArrayList<>();

List<SQSEvent.SQSMessage> records = event.getRecords();

for (int i = 0; i < records.size(); i++) {
    SQSEvent.SQSMessage message = records.get(i);

    try {
        SqsEventFunctions.OrderEvent input =
            mapper.readValue(
                message.getBody(),
                SqsEventFunctions.OrderEvent.class);

        // Validation/business processing must have an explicit contract.
        if (input == null
                || input.eventId() == null
                || input.eventId().isBlank()
                || input.orderId() == null
                || input.orderId().isBlank()) {
            throw new IllegalArgumentException("Invalid event");
        }

    } catch (com.fasterxml.jackson.core.JsonProcessingException
             | IllegalArgumentException ex) {

        // Report the failed record and ALL UNPROCESSED records.
        for (int j = i; j < records.size(); j++) {
            failures.add(
                new SQSBatchResponse.BatchItemFailure(
                    records.get(j).getMessageId()));
        }
        break;
    }
}

return new SQSBatchResponse(failures);
~~~

This is a **replacement snippet inside a context that already has event, mapper, and Function**, not a standalone Java file. The key rule is **not processing subsequent records after the first failure**; unprocessed IDs are returned so Lambda does not delete them.

If a FIFO queue has multiple message groups, implementers must still review ordering/parallelism semantics per **MessageGroupId**, event source mapping, and business requirements. Partial response configuration **does not replace idempotency**.

## 13. Special Case: S3 Events Delivered via SQS

Some systems send S3 notifications to SQS instead of invoking Lambda directly. In that case, Lambda receives an **SQS event**, not an **S3Event** at the outer layer:

~~~mermaid
flowchart LR
    A["S3 ObjectCreated"] --> B["SQS message body = S3 notification JSON"]
    B --> C["Lambda SQSEvent"]
    C --> D["record.body"]
    D --> E["Parse S3 notification"]
    E --> F["S3 object reference"]
~~~

Fundamentally, there are **two layers of envelopes**:

~~~text
SQS batch Records
  -> SQSMessage.body (String)
      -> S3 notification JSON
          -> S3 Records
              -> bucket/key/eventName
~~~

Therefore:

- The outer Function signature is typically **Function<SQSEvent, SQSBatchResponse>**.
- When processing each record, parse **message.getBody()** into S3 notification JSON or the corresponding event type.
- If an S3 notification contains multiple Records, iterate through those S3 Records as well.
- **The partial failure ID remains the SQS messageId**, not an S3 event ID or object sequencer.
- An S3 test event has no Records, so the adapter must handle it if the queue can receive one.

If SNS sits between S3 and SQS, the body may also contain an **SNS envelope** (when raw message delivery is disabled). Confirm the exact event source topology instead of parsing one JSON layer as another.

## 14. AWS SAM: Three Lambdas with Three Separate Triggers

A practical setup is often easier to manage when API Gateway, S3, and SQS use **three Lambda resources** with **separate function definitions**, even while sharing one shaded JAR.

Illustrative **template.yaml** example:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  InputBucket:
    Type: AWS::S3::Bucket

  OrderQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 180

  QuoteApiLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/event-app-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.HttpApiApplication
          spring_cloud_function_definition: httpQuoteV2
      Events:
        QuotesHttp:
          Type: HttpApi
          Properties:
            Path: /quotes
            Method: POST
            PayloadFormatVersion: "2.0"

  S3NotificationLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/event-app-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.HttpApiApplication
          spring_cloud_function_definition: inspectS3Notifications
      Events:
        ObjectCreated:
          Type: S3
          Properties:
            Bucket: !Ref InputBucket
            Events: s3:ObjectCreated:*
            Filter:
              S3Key:
                Rules:
                  - Name: prefix
                    Value: incoming/

  SqsBatchLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/event-app-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.HttpApiApplication
          spring_cloud_function_definition: validateSqsBatch
      Policies:
        - SQSPollerPolicy:
            QueueName: !GetAtt OrderQueue.QueueName
      Events:
        QueueEvents:
          Type: SQS
          Properties:
            Queue: !GetAtt OrderQueue.Arn
            BatchSize: 10
            FunctionResponseTypes:
              - ReportBatchItemFailures
~~~

**This configuration is illustrative** and assumes **S3EventFunctions** and **SqsEventFunctions** are scanned by Spring from the **HttpApiApplication** package. **CodeUri must point to an actual built shaded JAR**, while Java runtime, Boot/Cloud versions, artifact resource transformers, and IAM policies must be verified for your project.

Points to note:

1. The **SAM S3 event** in this example uses a bucket defined **in the same template**; when using a pre-existing bucket, notification/permission configuration can differ.
2. **SQS event mapping** requires queue polling permissions for the Lambda execution role; the example uses **SQSPollerPolicy**. If processing messages calls other AWS services, add least-privilege permissions accordingly.
3. **FunctionResponseTypes** is required if you want AWS to interpret the **batchItemFailures** list.
4. **VisibilityTimeout=180** is only illustrative to exceed Lambda's maximum runtime; in production, follow AWS guidance on timeouts, batching windows, retries, and DLQs.
5. S3 notifications are asynchronous invocations and use dedicated resource-based permissions; SAM can generate parts of the integration, yet post-deployment settings should still be verified.
6. Do not expose API Gateway publicly without authorization if the business API requires protection.
7. In the sample, all three Lambdas share the Spring main class **HttpApiApplication** because the S3/SQS configuration classes live in the scanned package. If you split them into separate applications, update **MAIN_CLASS** to match actual code.

## 15. Testing FunctionCatalog and Bean Names

FunctionCatalog lets Spring Cloud Function look up beans by name. Lambdas sharing the same JAR can use:

~~~text
spring_cloud_function_definition=httpQuoteV2
spring_cloud_function_definition=inspectS3Notifications
spring_cloud_function_definition=validateSqsBatch
~~~

When using **FunctionInvoker** as the handler, **MAIN_CLASS/Start-Class** locates the Spring application, while **definition** picks a bean or composition. Do not confuse bean names with the Lambda handler or AWS resource names.

Context test example:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = HttpApiApplication.class)
class AwsEventCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void findsAllThreeAdapters() {
        assertNotNull(catalog.lookup("httpQuoteV2"));
        assertNotNull(catalog.lookup("inspectS3Notifications"));
        assertNotNull(catalog.lookup("validateSqsBatch"));
    }
}
~~~

This test requires all configuration classes to be within component scan. It verifies **bean registration**, not that API Gateway/S3/SQS events are deserialized properly by FunctionInvoker in a real runtime.

## 16. Unit Testing the API Gateway Adapter

Because **httpQuoteV2** is a Java Function, you can test JSON requests/responses without running AWS:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

class HttpApiAdapterTest {

    private final HttpApiApplication app =
        new HttpApiApplication();

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void handlesValidHttpApiV2Body() throws Exception {
        String body = """
            {"requestId":"REQ-101","sku":"BOOK","quantity":2}
            """;

        var event = new HttpApiApplication.HttpApiV2Event(
            "2.0", "POST /quotes", "/quotes",
            body, false);

        var reply = app.httpQuoteV2(
            app.quoteService(), mapper).apply(event);

        assertEquals(200, reply.statusCode());
        assertEquals(
            "application/json",
            reply.headers().get("content-type"));
        assertTrue(reply.body().contains("170000"));
    }

    @Test
    void rejectsWrongRoute() {
        var event = new HttpApiApplication.HttpApiV2Event(
            "2.0", "GET /quotes", "/quotes",
            "{}", false);

        var reply = app.httpQuoteV2(
            app.quoteService(), mapper).apply(event);

        assertEquals(400, reply.statusCode());
    }
}
~~~

This test verifies logic **after HttpApiV2Event has already been constructed**. Add integration tests deserializing **full JSON events** (including requestContext and headers) into the record, testing base64 bodies, malformed JSON, and status/headers outside API Gateway.

## 17. Unit Testing S3 Key Decoding

Even without connecting to real S3, key decoding must be tested:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class S3KeyDecodingTest {

    @Test
    void decodesFormEncodedObjectKey() {
        String key = S3EventFunctions.decodeS3Key(
            "incoming%2Freport+nov%2Bfinal.csv");

        assertEquals(
            "incoming/report nov+final.csv",
            key);
    }
}
~~~

An integration test using real S3 events should verify **S3Event.getRecords()**, eventVersion, eventName, and versionId when present. Add a dedicated test for **s3:TestEvent** because its schema differs.

If adding AWS SDK **GetObject**, mock the client in unit tests and run integration tests only against a test-configured bucket/role, never a production bucket.

## 18. Unit Testing SQS Partial Failures

You can construct **SQSEvent** and **SQSMessage** instances directly in unit tests of the Function:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class SqsBatchTest {

    @Test
    void returnsOnlyInvalidMessageIds() {
        var valid = new SQSEvent.SQSMessage();
        valid.setMessageId("msg-001");
        valid.setBody("""
            {"eventId":"EVT-001","orderId":"ORD-101"}
            """);

        var invalid = new SQSEvent.SQSMessage();
        invalid.setMessageId("msg-002");
        invalid.setBody("""
            {"eventId":"","orderId":"ORD-102"}
            """);

        var batch = new SQSEvent();
        batch.setRecords(List.of(valid, invalid));

        var fn = new SqsEventFunctions()
            .validateSqsBatch(new ObjectMapper());

        var response = fn.apply(batch);

        assertEquals(1, response.getBatchItemFailures().size());
        assertEquals(
            "msg-002",
            response.getBatchItemFailures()
                .get(0).getItemIdentifier());
    }
}
~~~

This test verifies that Java code builds **batchItemFailures** by message ID. However, **it does not prove AWS will retry only that record** if the event source mapping has not enabled **ReportBatchItemFailures**. Add integration tests or verify the actual Lambda's SAM/CloudFormation configuration.

## 19. Three Error Categories: Do Not Handle Them All the Same

| Error Type | Example | Appropriate Policy |
| --- | --- | --- |
| **Conversion / schema** | Malformed API Gateway JSON body; SQS body missing fields | Reject per error contract, quarantine/DLQ as needed |
| **Business rejection** | Unknown SKU; already-processed event; unsuitable object | Decide idempotent/no-op vs. explicit rejection result |
| **Transient infrastructure** | S3 GetObject timeout; lost database connection | Bounded retries, backoff, observability |

### API Gateway

A malformed payload should normally lead to HTTP **400**; system failures can map to **5xx**. When using proxy integration, Lambda must return a response with the right **statusCode/body** instead of simply throwing an exception and hoping the client receives a normalized error.

### S3

S3 usually invokes Lambda **asynchronously**. If processing fails, retries/destinations/DLQs and retry counts depend on the configured AWS asynchronous invocation settings. S3 notifications can arrive duplicated or out of order; processors need idempotency and loop-prevention strategies.

### SQS

SQS triggers use an event source mapping polling the queue; messages can be redelivered. When using partial batch responses, report each failure by **messageId**. For FIFO, account for ordering; for permanently invalid data, define DLQ/quarantine policies to avoid endless retries.

## 20. Security and Observability

- **Do not trust requestContext/headers from JSON sent via direct invoke** as authenticated proof. Only trust metadata after verifying the source and trust boundary.
- **Do not log full API headers or bodies**; they can contain Authorization tokens, cookies, or PII.
- **Do not decode S3 keys twice**; a key is an object identifier, not an arbitrary URL path you assemble.
- **Do not grant s3:GetObject to every Lambda** when only the S3-processing Lambda needs it.
- **Do not use receiptHandle as a business idempotency key**; choose a stable eventId/business key in storage.
- **Do not log unbounded failing SQS payloads**; use error codes, messageId, and correlation IDs for tracing.
- **Bound JSON size and parser nesting**, especially when unwrapping API Gateway or SQS bodies.
- **Do not assume S3 eTag is always the MD5 of file contents**; multipart uploads and encryption break that assumption.
- **Do not treat a singleton Function bean as cross-Lambda state storage**; each execution environment has isolated memory.

Useful logs/metrics should distinguish **eventSource**, **Lambda function/version**, **record/message ID**, **outcome**, **duration**, and error codes without leaking sensitive information.

## 21. Common Deployment Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| **FunctionInvoker ClassNotFound** | Wrong JAR layout or missing adapter | Check shaded JAR, handler |
| FunctionCatalog cannot find bean | Wrong definition or package scan | Check @Bean, MAIN_CLASS, catalog |
| API v2 reports null **httpMethod** field | Reading v1 shape on a v2 event | Use requestContext.http.method/routeKey |
| API returns **502 Bad Gateway** | Response does not match proxy format | Check statusCode/body, payload version |
| JSON body fails to parse | Body not extracted/decoded or schema mismatch | Check isBase64Encoded, parse right class |
| S3 key has unexpected **+** characters | Missing form URL-decoding | URLDecoder UTF-8 once |
| S3 notification has no Records | Received **s3:TestEvent** | Branch by schema |
| Lambda expects S3 event to hold file bytes | Confused notification with object | Use S3 GetObject and IAM |
| S3 output writes trigger endless loops | Notification bucket/prefix overlaps output | Use separate prefix/bucket |
| S3 events arrive out of order | At-least-once/out-of-order delivery | Idempotency and per-object sequencer |
| SQS processes only one message | Did not iterate Records | Iterate the entire batch |
| SQS body stays a raw string | JSON inside body not parsed | Deserialize each message.body |
| Partial failure has no effect | ReportBatchItemFailures not enabled | Check event source mapping |
| Partial response treats batch as failed | Empty/wrong itemIdentifier or wrong output | Use batch messageIds |
| FIFO processes messages out of order | Continued processing after a failed record | Stop and report all remaining unprocessed records |
| Redelivery causes duplicate writes | Missing idempotency | Unique key, transaction/outbox |
| SQS body holds S3 event but code expects OrderEvent | Multi-layer nested envelopes | Parse SQS body into S3 notification first |

## 22. Hands-on Exercises

**Exercise 1 — Comparing envelopes.** Given three payloads—API Gateway 2.0, S3 ObjectCreated, and an SQS batch—identify for each payload which parts are AWS metadata, which parts are business payload, and what type the Function bean should accept.

**Exercise 2 — API Gateway v1/v2.** Write a mapping table for method/path/headers/body between REST API proxy v1 and HTTP API v2. Design two adapter DTOs or a branching strategy with version tests.

**Exercise 3 — HTTP error responses.** Extend **httpQuoteV2** to handle missing body, invalid Base64, quantity 0, unknown SKU, and infrastructure errors. Each case must return contract-compliant status/error codes.

**Exercise 4 — S3 URL encoding.** Compute the decoded result of key **a+b%2Bc%2Fd.csv**. Write unit tests covering plus signs, spaces, Unicode, and percent signs; explain why decoding must run only once.

**Exercise 5 — S3 test event.** Design an adapter that distinguishes **s3:TestEvent** from **Records** notifications. For test events, decide whether to log and ignore or return an error, and explain the impact on retries.

**Exercise 6 — S3 versions and idempotency.** When two create/delete events for the same object key arrive out of order, propose a state store and how to use **sequencer** per object key. Never compare sequencers across different keys.

**Exercise 7 — SQS partial failures.** A batch has messageIds **a**, **b**, **c**; **b** is invalid. Write the JSON response for a Standard queue when only b fails, then the response for a FIFO queue stopping from b onward.

**Exercise 8 — S3 → SQS.** Diagram the two-layer structure **SQS Records → SQS body → S3 Records**. Point out which ID goes into **batchItemFailures** when parsing an S3 body fails.

**Exercise 9 — SAM deployment.** Create three Lambdas sharing one shaded JAR with different definitions; add an HTTP API v2 trigger, an S3 ObjectCreated prefix trigger, and an SQS trigger with ReportBatchItemFailures. Explain the separate IAM permissions for each resource.

**Exercise 10 — Testing boundaries.** Separate unit tests for QuoteService, the S3 key decoder, and the SQS batch processor from integration tests for FunctionInvoker, API Gateway, S3 event conversion, and SQS event source mapping.

### Key Takeaways

- **API Gateway, S3, and SQS deliver distinct event envelopes**. Do not assume the incoming event is always the business DTO.
- **API Gateway v1/v2** differ in method/path locations, headers, and response rules; body may be a JSON string or Base64-encoded.
- **S3 notifications contain only object metadata**. URL-decode the key exactly once; do not treat the invocation stream as file contents; account for test events, duplicates, and ordering.
- **SQS triggers deliver batched Records**. Parse **each body**, design idempotency, and use **messageId** in **batchItemFailures** after enabling ReportBatchItemFailures.
- **FIFO must preserve ordering**: on error, stop processing and report all unprocessed messages per AWS guidance.
- **FunctionInvoker + FunctionCatalog** keep business logic protocol-independent; adapters handle data extraction, conversion, and responses matching each source's contract.

### References

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, S3Event, SQSEvent, SQSBatchResponse, and conversion.
- [API Gateway — HTTP API Lambda proxy integrations](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html): payload format 1.0/2.0 and response mapping.
- [API Gateway — REST API Lambda proxy integration](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html): request envelope and proxy response format.
- [Amazon S3 — Event notification message structure](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html): Records, key encoding, version, sequencer, and test events.
- [AWS Lambda — S3 trigger](https://docs.aws.amazon.com/lambda/latest/dg/with-s3.html): S3 event delivery, IAM, and same-bucket write loops.
- [AWS Lambda — SQS integration](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html): batches, visibility timeout, retries, and idempotency.
- [AWS Lambda — SQS partial batch responses](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html): ReportBatchItemFailures, FIFO, and itemIdentifier.
- [AWS SAM — SQS event](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-sqs.html): BatchSize and FunctionResponseTypes.
