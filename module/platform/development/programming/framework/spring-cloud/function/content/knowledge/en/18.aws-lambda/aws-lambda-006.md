# Converting Events to POJOs and Accessing the Raw InputStream

When deploying **SPRING_CLOUD_FUNCTION** on **AWS Lambda**, an incoming event to Lambda begins as data received by the runtime from an invocation source: direct invoke, API Gateway, SQS, S3, or another trigger. **spring-cloud-function-adapter-aws** provides **FunctionInvoker**, which reads the invocation payload and **converts it into the Java type declared on the Function**. As a result, a **Function<OrderRequest, OrderResult>** bean can receive a well-structured POJO without manually parsing JSON. Conversely, when you need to inspect or process the event bytes before conversion, you can declare **Function<InputStream, R>** to receive the **raw InputStream**.

This lesson belongs to the **AWS Lambda** chapter and analyzes both input paths—**typed POJO** and **raw InputStream**—how to distinguish event envelopes from business payloads, complete Java 17+ examples, data type limitations, error handling, security, FunctionInvoker configuration, testing, and scenarios requiring manual JSON parsing. The goal is to keep **Supplier/Function/Consumer** logic reusable across HTTP, events, or serverless, while placing conversion responsibilities at the right boundary.

## 1. Two Input Paths in FunctionInvoker

**FunctionInvoker** is Spring Cloud Function's generic handler on AWS. It implements the AWS **RequestStreamHandler** interface: the runtime supplies an input stream containing the invocation payload, an output stream, and a context object. The adapter initializes the Spring context, retrieves the bean from **FunctionCatalog**, and prepares the input according to the declared type.

~~~mermaid
flowchart TD
    A["AWS Lambda event bytes"] --> B["FunctionInvoker"]
    B --> C{"Bean input type?"}
    C -- "OrderRequest / POJO" --> D["Convert JSON to POJO"]
    C -- "InputStream" --> E["Pass raw stream to function"]
    D --> F["Function<OrderRequest, R>"]
    E --> G["Function<InputStream, R>"]
    F --> H["Output R"]
    G --> H
    H --> I["Adapter serializes response"]
~~~

Two typical signatures:

~~~java
Function<OrderRequest, OrderResult> validateOrder;
Function<InputStream, RawEventDigest> rawEventDigest;
~~~

| Criterion | **Function<POJO, R>** | **Function<InputStream, R>** |
| --- | --- | --- |
| Input seen by application | A constructed Java object | Raw byte stream of the Lambda invocation |
| Who performs initial parsing? | Adapter/converter | Your code if needed |
| Business contract | Clear via type T and its fields | Must define how bytes/format are interpreted |
| JSON parsing errors | Usually occur before business logic runs | Occur in your code if parsed manually |
| Suitable tasks | Business DTOs, events with stable schemas | Inspecting raw envelopes, signatures, special formats, custom parsing |
| Main risks | Type conversion, schema, and nullability | Single-read stream, memory, encoding, raw data security |

According to the Spring Cloud Function AWS documentation, when the input is **InputStream**, the adapter **skips the input type conversion step** and passes the stream to the function. When the declared input is a specific type like **OrderRequest**, the adapter **attempts** to convert the event into that type. The word "attempts" matters: conversion depends on the schema, converters, Java types, and library versions.

## 2. Three Concepts Not to Confuse

Distinguish between:

1. **Lambda invocation payload:** the entire JSON document (or data passed into the stream by the runtime) of a single Lambda invocation.
2. **Event envelope:** the outer structure produced by an AWS source, such as API Gateway's **body** field, SQS's **Records**, or EventBridge's **detail**.
3. **Business payload:** the fields actually required by the Function, such as **requestId**, **sku**, **quantity**.

Example when invoking Lambda directly:

~~~json
{
  "requestId": "REQ-101",
  "sku": "book",
  "quantity": 2
}
~~~

Here the entire JSON document can be the business payload itself, so **Function<OrderRequest, OrderResult>** is a natural fit.

However, an API Gateway HTTP API can send a simplified event like this:

~~~json
{
  "version": "2.0",
  "routeKey": "POST /orders",
  "rawPath": "/orders",
  "headers": {
    "content-type": "application/json"
  },
  "body": "{\"requestId\":\"REQ-101\",\"sku\":\"book\",\"quantity\":2}",
  "isBase64Encoded": false
}
~~~

In this case, **body is a JSON string nested inside another JSON object**. A raw InputStream receives the **event envelope**, not the bytes of the body field by itself. Meanwhile, a Function taking **OrderRequest** needs an appropriate converter/adapter to extract and parse the right content. Do not assume all event sources and adapter versions unwrap envelopes identically.

~~~mermaid
flowchart LR
    A["API Gateway event"] --> B["Envelope with body, headers, metadata"]
    B --> C["Adapter reads/decodes body"]
    C --> D["OrderRequest"]
    D --> E["Business function"]
~~~

**Rule:** choose the input type based on **the data unit Lambda actually receives**, not solely on the JSON body you expect from a frontend.

## 3. What Is a POJO in Event Conversion?

A **POJO (Plain Old Java Object)** is a regular Java object that does not have to extend AWS or Spring classes. With Jackson-based JSON mappers, a JavaBean with a no-arg constructor and getters/setters is an easy-to-understand form for illustrating conversion.

Example:

~~~java
public static final class OrderRequest {
    private String requestId;
    private String sku;
    private Integer quantity;

    public OrderRequest() {
    }

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

**Java record** is also a valid DTO style when your serializer version supports records. However, not every POJO must be a record, and not every mapper version handles constructors, records, and immutable classes identically.

Why use **Integer quantity** instead of **int**? Because a missing JSON field can leave **null**, allowing the function to distinguish **missing field** from **quantity = 0**. This is a contract design decision; it does not replace business validation checks.

### Constraints Belong to the Contract, Not the Parser

| Field | Java Type | Required Checks |
| --- | --- | --- |
| **requestId** | String | Present, non-blank, length limit |
| **sku** | String | Non-blank, consistent normalization, allowed format |
| **quantity** | Integer | Non-null, within valid business range |
| **result.status** | String/enum | Clear status meaning, unambiguous from AWS invocation status |

Converters help construct Java objects; **they do not automatically verify all business invariants**. Adding validation annotations also does not guarantee every adapter triggers a validator before calling **apply(...)**. For mandatory invariants, validation must be enforced at the business layer or a consistently invoked validation layer.

## 4. Java 17+ Application: Two Beans, Two Ways of Receiving Events

The following example uses Spring Boot to create two Functions:

- **validateOrder** receives an **OrderRequest** POJO converted from the event.
- **rawEventDigest** receives the raw **InputStream** and returns the byte count and SHA-256 digest of the invocation payload.

Both beans share the same context to illustrate AWS paths, yet **have different input contracts**. The example does not actually persist orders to a database.

File **src/main/java/example/lambda/LambdaEventApplication.java**:

~~~java
package example.lambda;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LambdaEventApplication {

    private static final int MAX_EVENT_BYTES = 1_048_576;

    public static void main(String[] args) {
        SpringApplication.run(LambdaEventApplication.class, args);
    }

    // JavaBean POJO used for JSON input.
    public static final class OrderRequest {
        private String requestId;
        private String sku;
        private Integer quantity;

        public OrderRequest() {
        }

        public String getRequestId() {
            return requestId;
        }

        public void setRequestId(String requestId) {
            this.requestId = requestId;
        }

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    // Validation result, not confirmation that an order was saved.
    public record OrderValidation(
        String requestId,
        String sku,
        int quantity,
        String status
    ) {}

    // Output omits raw event to avoid leaking payload.
    public record RawEventDigest(
        int byteCount,
        String sha256
    ) {}

    @Bean("validateOrder")
    Function<OrderRequest, OrderValidation> validateOrder() {
        return request -> {
            if (request == null
                    || request.getRequestId() == null
                    || request.getRequestId().isBlank()
                    || request.getSku() == null
                    || request.getSku().isBlank()
                    || request.getQuantity() == null
                    || request.getQuantity() < 1
                    || request.getQuantity() > 1000) {
                throw new IllegalArgumentException(
                    "Invalid order request");
            }

            String requestId = request.getRequestId().trim();
            String sku = request.getSku()
                .trim().toUpperCase(Locale.ROOT);

            return new OrderValidation(
                requestId, sku, request.getQuantity(), "VALID");
        };
    }

    @Bean("rawEventDigest")
    Function<InputStream, RawEventDigest> rawEventDigest() {
        return input -> {
            // Bounded read: prevent unbounded reading into memory.
            byte[] bytes;
            try {
                bytes = input.readNBytes(MAX_EVENT_BYTES + 1);
            } catch (IOException ex) {
                throw new UncheckedIOException(
                    "Unable to read invocation input", ex);
            }

            if (bytes.length > MAX_EVENT_BYTES) {
                throw new IllegalArgumentException(
                    "Invocation payload exceeds demo limit");
            }

            try {
                MessageDigest sha256 =
                    MessageDigest.getInstance("SHA-256");

                String hex = HexFormat.of().formatHex(
                    sha256.digest(bytes));

                return new RawEventDigest(bytes.length, hex);
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException(
                    "SHA-256 provider unavailable", ex);
            }
        };
    }
}
~~~

**Important points when copying:**

- **InputStream** comes from **java.io**, not an interface defined by Spring Cloud Function.
- **readNBytes(MAX + 1)** reads at most **1 MiB + 1 byte**, then rejects payloads exceeding the demo limit. This avoids using unbounded **readAllBytes()** on untrusted payloads.
- The SHA-256 digest here identifies bytes in a **demo**, not an authentication signature or tamper protection against an adversary. A plain hash does not prove who sent the event.
- **rawEventDigest** does not store the stream in a field, retain it for subsequent invocations, log raw bytes, or close the stream owned by the runtime adapter.
- The **validateOrder** example returns **VALID**, not **ORDER_CREATED**: it only validates data without writing to a database or causing side effects.
- Output record types require serializer support and must be tested on your actual Spring/Jackson version.

If payloads need to be rejected earlier to save cost, combine size limits at the caller, API Gateway, or an appropriate ingestion layer. A limit inside the Function is an **additional defense layer**, not a substitute for infrastructure limits.

## 5. POJO Invocation: How Does JSON Map Into OrderRequest?

In the example, the **validateOrder** bean declares:

~~~java
@Bean("validateOrder")
Function<OrderRequest, OrderValidation> validateOrder() { ... }
~~~

When AWS Lambda uses **FunctionInvoker** and the selected definition is **validateOrder**, the adapter inspects the **OrderRequest** input type and attempts to convert the invocation JSON payload into an object.

~~~text
Lambda invocation JSON
  -> FunctionInvoker InputStream
  -> message/conversion layer
  -> OrderRequest POJO
  -> validateOrder.apply(request)
  -> OrderValidation
  -> serialized Lambda output
~~~

With direct invocation:

~~~json
{
  "requestId": "REQ-101",
  "sku": "book",
  "quantity": 2
}
~~~

Expected business output:

~~~json
{
  "requestId": "REQ-101",
  "sku": "BOOK",
  "quantity": 2,
  "status": "VALID"
}
~~~

**You do not need to call ObjectMapper manually inside validateOrder** once the adapter constructs OrderRequest properly. This keeps business code easy to unit test and easy to reuse with another adapter that also supplies OrderRequest.

However, if the event is not a JSON object matching the schema, the parser may fail **before** the Function runs. For instance, sending a JSON array or a quantity field that is an object:

~~~json
{
  "requestId": "REQ-102",
  "sku": "BOOK",
  "quantity": { "value": 2 }
}
~~~

This is a **deserialization/type conversion** failure, distinct from JSON with **quantity = 0** (valid Integer type, yet violates a business rule).

## 6. InputStream Invocation: Receiving Raw Bytes

The **rawEventDigest** bean declares:

~~~java
@Bean("rawEventDigest")
Function<InputStream, RawEventDigest> rawEventDigest() { ... }
~~~

In the AWS Lambda path described by the documentation, Spring Cloud Function **skips the input conversion step** and passes the stream directly into the function.

~~~text
Lambda event JSON bytes
  -> FunctionInvoker's RequestStreamHandler
  -> original InputStream
  -> rawEventDigest.apply(stream)
  -> bounded read + SHA-256
  -> RawEventDigest
  -> output serialization
~~~

**Observation example:** a caller sends the exact UTF-8 byte sequence of the document:

~~~json
{"requestId":"REQ-101","sku":"book","quantity":2}
~~~

The function computes the byte count and SHA-256 over that exact document, including **{**, **}**, quotes, colons, and whitespace **if present in the actual payload**.

If the caller adds a trailing newline, reorders JSON keys, or inserts whitespace without altering business meaning, **the raw-byte SHA-256 still changes**. This is a key distinction between **raw-byte equivalence** and **semantic JSON equivalence**.

### What Raw InputStream Is Not

- **It is not** the contents of an S3 file referenced by an event. S3 events typically carry bucket/key; reading the file requires the S3 API and IAM.
- **It is not by default** the HTTP body sent by a user through API Gateway. It is usually the full Lambda event envelope containing a **body** field.
- **It is not** an unbounded stream of a TCP connection; it is the stream of **a single Lambda invocation**.
- **It does not automatically** Base64-decode if an API Gateway event has a body with **isBase64Encoded=true**; interpreting the envelope and decoding are responsibilities of the adapter/handler layer.
- **It is not** the runtime's output stream. A **Function<InputStream, R>** returns **R**; **FunctionInvoker** remains responsible for serializing R and writing to AWS's **OutputStream**.

If you need direct control over output bytes, that is a different architectural decision: implement **RequestStreamHandler** directly or use a specialized adapter mechanism. Do not confuse receiving a raw InputStream in a Function with owning both input and output streams of the AWS handler.

## 7. When Should You Use InputStream Instead of a POJO?

Reasonable use cases:

| Requirement | Suitable Choice | Explanation |
| --- | --- | --- |
| JSON event with fixed schema | **Function<POJO, R>** | Framework handles conversion, business code stays typed |
| Need to inspect raw payload bytes | **Function<InputStream, R>** | Preserves exact incoming byte representation |
| Event sources with differing schemas | InputStream/Map or envelope adapter | Determine version/source, then map to DTOs |
| Need to verify HMAC/signature over raw payload | InputStream at adapter layer | Raw bytes can matter; also need keys and constant-time comparison |
| Input format is not standard JSON | InputStream with suitable parser | Code owns format, limits, and errors |
| SQS/S3 events with standard AWS Java types | **SQSEvent / S3Event** | Use types from the AWS events library |
| Only need HTTP body from API Gateway | Event adapter extracting body | No need to turn every business Function into InputStream |

**Do not pick InputStream assuming it is always faster than a POJO.** Bypassing adapter conversion means you must handle parsing, encoding, size limits, and errors yourself. Performance should be measured on real workloads; contract clarity is often more valuable than unmeasured micro-optimization.

## 8. Manually Deserializing InputStream to a POJO When Needed

Sometimes you must read or validate raw bytes first and then convert to a POJO. Split the code into two steps:

~~~mermaid
flowchart LR
    A["InputStream"] --> B["Adapter bounds/checks raw bytes"]
    B --> C["JSON parser"]
    C --> D["OrderRequest POJO"]
    D --> E["Business validation"]
    E --> F["OrderValidation"]
~~~

Example using the **Jackson 2 API** (suited for Spring Boot 3.x projects using **com.fasterxml.jackson.databind.ObjectMapper**). When using another Spring Boot/Jackson generation, verify packages and APIs against your pinned dependencies:

~~~java
package example.lambda;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.function.Function;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ManualParsingConfiguration {

    @Bean("parseRawOrder")
    Function<InputStream, LambdaEventApplication.OrderValidation>
            parseRawOrder(
                ObjectMapper mapper,
                @Qualifier("validateOrder")
                Function<LambdaEventApplication.OrderRequest,
                         LambdaEventApplication.OrderValidation>
                    validator) {

        return input -> {
            try {
                LambdaEventApplication.OrderRequest request =
                    mapper.readValue(
                        input,
                        LambdaEventApplication.OrderRequest.class);

                return validator.apply(request);
            } catch (JsonProcessingException ex) {
                throw new IllegalArgumentException(
                    "Invalid JSON for OrderRequest", ex);
            } catch (IOException ex) {
                throw new UncheckedIOException(
                    "Unable to read invocation input", ex);
            }
        };
    }
}
~~~

This example assumes Spring has registered an appropriate **ObjectMapper**, matching Jackson dependencies are present, and **ManualParsingConfiguration** is covered by component scan. **parseRawOrder** is an **optional additional bean**, not built in if you only copy LambdaEventApplication from Section 4.

Here the raw stream is read **once** by Jackson, and the business validator processes the POJO. If you need to compute a hash and parse JSON from **the same input**, do not read the whole stream twice: perform a bounded read into a byte array and reuse that array for both hashing and parsing. Do not assume **InputStream.reset()** is always supported.

**Snippet limitation:** this illustration does not enforce a size limit before Jackson; in production, apply bounded reads, parser constraints, and event-source limits. For non-JSON formats, replace Jackson with the appropriate parser while preserving the separation between adaptation and business logic.

## 9. Stream Ownership, Single-Read Semantics, and Memory Control

InputStream is normally **one-way**: reading advances toward the end of the stream. Do not treat it like an immutable String that can be reprocessed endlessly.

### Common Mistakes

~~~java
@Bean("brokenRawReader")
Function<InputStream, String> brokenRawReader() {
    return stream -> {
        // First read consumes the entire input.
        String first;
        try {
            first = new String(
                stream.readAllBytes(),
                java.nio.charset.StandardCharsets.UTF_8);
        } catch (java.io.IOException ex) {
            throw new java.io.UncheckedIOException(ex);
        }

        // Subsequent reads normally have zero bytes left.
        // This does NOT mean the original event was empty!
        try {
            return first + " / remaining=" + stream.readAllBytes().length;
        } catch (java.io.IOException ex) {
            throw new java.io.UncheckedIOException(ex);
        }
    };
}
~~~

The issue is not just performance: once input has been drained, a downstream parser receives an empty stream and throws confusing errors. To inspect and parse within one invocation, use **a single bounded read**, or a stream tee/mark where supported by contract.

### Size Limits

Avoid calling **readAllBytes()** on unbounded payloads:

~~~java
byte[] event = stream.readAllBytes();
~~~

This can allocate excessive memory if payloads are large or untrusted. Illustrative solution:

~~~java
int limit = 1_048_576;
byte[] payload = stream.readNBytes(limit + 1);

if (payload.length > limit) {
    throw new IllegalArgumentException("Event too large");
}
~~~

Place this snippet inside a **try/catch IOException** block or a method declaring **throws IOException**. The 1 MiB cap is an **illustrative application policy**, not the maximum limit of AWS Lambda. For large data, consider a streaming parser or storing the payload externally (such as in S3) and passing a pointer instead.

### Who Closes the Stream?

**RequestStreamHandler** belongs to the runtime/adapter managing the invocation stream. Business functions should read within the invocation scope without storing the stream in a field or processing it asynchronously after the invocation finishes. Whether to call **close()** on an adapter-provided stream must follow ownership contracts; the example in Section 4 does not explicitly close input.

If you open a **FileInputStream** yourself in business code, ownership rules differ: the code opening the file is normally responsible for closing it.

## 10. Character Encoding and Binary Content

To turn raw bytes into text when the format is **known for certain** to be UTF-8:

~~~java
byte[] bytes = input.readNBytes(limit + 1);
String text = new String(
    bytes,
    java.nio.charset.StandardCharsets.UTF_8);
~~~

This is **decoding text from bytes**, not a JSON parser. If the string is:

~~~json
{"name":"Lan"}
~~~

then the **text** variable still contains JSON braces, quotes, and escape characters; it does not automatically become a Java object with a **name** field.

For binary data, do not decode into a UTF-8 String and re-encode assuming bytes are preserved. Use **byte[]**, **InputStream**, checksums, or a format-specific binary parser.

API Gateway proxy events include **isBase64Encoded**; if the body is base64-encoded, the adapter must:

1. Read the **body** string from the event envelope.
2. Check **isBase64Encoded** and decode properly when true.
3. Verify the actual content type/format.
4. Parse those bytes into business data.

A Function receiving a raw InputStream **does not automatically perform those four steps**. Depending on the proxy event model and adapter version, test the binary payload path as well.

## 11. What Happens When the Generic Input Type Cannot Be Determined?

Spring Cloud Function relies on the Function's type information to pick conversions. The AWS documentation states that if the type is unknown or indeterminate—for example, **Function<?, ?>**—the adapter may attempt to convert the event into a generic **Map**.

Compare:

~~~java
Function<OrderRequest, OrderValidation>
Function<java.util.Map<String, Object>, String>
Function<Object, Object>
Function<InputStream, RawEventDigest>
~~~

| Input Type | Specificity | Consequence |
| --- | --- | --- |
| **OrderRequest** | Clear schema | Conversion targets the POJO |
| **Map<String,Object>** | Flexible | Author manually checks field types |
| **Object / raw Function** | Missing schema | Converter may produce a Map or generic representation |
| **InputStream** | Explicit intent for bytes | Adapter skips input conversion and passes raw stream |

**Map is not automatically safe.** For instance, a JSON number can become Integer, Long, or another numeric type depending on the mapper, JSON arrays become Lists, and nested objects become Maps. Direct casts like **(Integer) map.get("quantity")** can break when clients or mappers change.

When schemas are stable, **typed POJOs** catch contract mismatches earlier, simplify testing, and ease API versioning. When events vary widely, consider an envelope adapter with **type/version** fields that maps to dedicated typed DTOs instead of passing an arbitrary Map throughout the system.

## 12. AWS Sources with Dedicated Event Envelopes

### 12.1. API Gateway

Proxy events typically include **body**, headers, request context, and routing metadata. A raw InputStream gives you the entire JSON event. If business logic only wants **OrderRequest**, extract and parse **body** appropriately while constructing responses matching the API Gateway contract.

With API Gateway proxy integration v1.0, responses usually need a structure like:

~~~json
{
  "statusCode": 200,
  "headers": {
    "content-type": "application/json"
  },
  "isBase64Encoded": false,
  "body": "{\"status\":\"VALID\"}"
}
~~~

**Body is a string** containing serialized JSON. With HTTP API payload v2.0, response inference rules can differ and certain raw JSON outputs are supported. Never assume every API Gateway event requires the exact same wrapper; check your **integration type and payload version**.

### 12.2. SQS

SQS delivers an event containing multiple **Records**. Each record typically contains a **body** string, messageId, and attributes. A raw InputStream receives the JSON of **the entire batch event**, not just one message body.

To use standard AWS event classes, you can write:

~~~java
Function<
    com.amazonaws.services.lambda.runtime.events.SQSEvent,
    com.amazonaws.services.lambda.runtime.events.SQSBatchResponse>
        processSqs;
~~~

This is a **design signature**, not a registered bean by variable declaration alone. The project needs the matching **aws-lambda-java-events** dependency, per-record processing logic, and SQS event source mapping configuration.

**Partial batch failure** does not work automatically just by returning an arbitrary DTO: the SQS trigger must enable **ReportBatchItemFailures**, and the output must match the AWS-required schema. If the Function throws an exception, the entire batch may be treated as failed. Design idempotency, retries, and DLQs for messages.

### 12.3. S3

An S3 event typically describes bucket, key, and action. It **does not contain the bytes of the uploaded file itself**. To process file contents, code must call S3 **GetObject** using an appropriate SDK/client and IAM permissions. The InputStream from FunctionInvoker still contains only the **event notification payload**.

### 12.4. EventBridge and Other Sources

EventBridge typically sends metadata such as **source**, **detail-type**, **detail**, and **id**. Decide whether the Function should receive the entire envelope or only the **detail** extracted by an adapter. Either way, document schema, validation, versioning, and error contracts explicitly.

## 13. Selecting the Right Bean on Lambda

Because the Java example has **two Function beans**, set the function definition explicitly to avoid ambiguity:

~~~text
spring_cloud_function_definition=validateOrder
~~~

or:

~~~text
spring_cloud_function_definition=rawEventDigest
~~~

The AWS handler remains:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

Application class:

~~~text
MAIN_CLASS=example.lambda.LambdaEventApplication
~~~

~~~mermaid
flowchart TD
    A["One shaded JAR containing both beans"] --> B["Lambda validate-order"]
    A --> C["Lambda inspect-raw"]
    B --> D["definition = validateOrder"]
    C --> E["definition = rawEventDigest"]
    D --> F["FunctionInvoker + FunctionCatalog"]
    E --> F
~~~

One JAR can serve **two distinct Lambda resources**, each picking one bean and having separate IAM permissions, memory/timeout settings, or triggers. You do not need to write two custom **RequestStreamHandler** classes when **FunctionInvoker** meets your needs.

**Do not confuse FunctionCatalog lookup with the handler.** The handler is AWS's entry point; **FunctionCatalog** resolves the function name in the Spring context. A bean named **validateOrder** is not a Java handler that AWS loads directly.

## 14. Illustrative AWS SAM for POJO and Raw Stream

Example **template.yaml**:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  ValidateOrderLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/lambda-event-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.LambdaEventApplication
          spring_cloud_function_definition: validateOrder

  RawEventLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/lambda-event-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.LambdaEventApplication
          spring_cloud_function_definition: rawEventDigest
~~~

**CodeUri** is an illustrative artifact name: replace it with the **actual shaded JAR produced by your build**. **java21** is only an example runtime; the classes use Java 17 APIs and can be compiled for Java 17 if your Spring Boot/Cloud Function versions and Lambda runtime are compatible. Memory/Timeout are not fixed optimal values.

Per the AWS adapter documentation, SAM examples may use the class name **FunctionInvoker** as the handler; the AWS Console also supports **FunctionInvoker::handleRequest**. Stay consistent with the configuration and runtime version you tested.

### Dependencies and Packaging

The application requires:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

Along with compatible Spring Boot and Spring Cloud/Function versions, and a build setup producing a shaded JAR containing **FunctionInvoker.class**, application classes, and Spring metadata.

**Do not upload a Boot executable JAR using the BOOT-INF layout without verifying the runtime classpath**. For standard Java Lambda JAR deployments, Spring Cloud Function AWS samples use a shaded JAR. Having the dependency does not mean the artifact is packaged properly.

## 15. Invoking Both Lambdas with AWS CLI

Assuming the artifact is deployed and credentials/IAM are configured, direct invocation commands via AWS CLI v2:

### 15.1. POJO Conversion

~~~bash
aws lambda invoke --function-name validate-order --cli-binary-format raw-in-base64-out --payload '{"requestId":"REQ-101","sku":"book","quantity":2}' validation.json

cat validation.json
~~~

Expected business result is **OrderValidation** with **status=VALID**. Check JSON output, CLI metadata such as **FunctionError**, and CloudWatch logs.

### 15.2. Raw InputStream

~~~bash
aws lambda invoke --function-name inspect-raw --cli-binary-format raw-in-base64-out --payload '{"requestId":"REQ-101","sku":"book","quantity":2}' digest.json

cat digest.json
~~~

Business result is **RawEventDigest**:

~~~json
{
  "byteCount": 49,
  "sha256": "64 hex characters generated by SHA-256"
}
~~~

**Note:** for the exact ASCII JSON string in the direct invoke command—with no extra spaces or newlines—the payload is **49 UTF-8 bytes**. The **sha256** field in the JSON above is only a descriptive placeholder, **not a real SHA-256 digest**. During hands-on practice, read the byte count and hash computed by the real Lambda; whitespace or encoding differences change the hash. Do not copy the descriptive placeholder string into test assertions.

The commands above are instructions for a real AWS environment, not operations executed while authoring this document.

## 16. Unit Testing a POJO-Receiving Function

POJO unit tests do not require a Spring context, Lambda runtime, or JSON converter:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class LambdaEventPojoTest {

    private final LambdaEventApplication app =
        new LambdaEventApplication();

    @Test
    void acceptsValidOrder() {
        var input = new LambdaEventApplication.OrderRequest();
        input.setRequestId("REQ-101");
        input.setSku(" book ");
        input.setQuantity(2);

        var result = app.validateOrder().apply(input);

        assertEquals("REQ-101", result.requestId());
        assertEquals("BOOK", result.sku());
        assertEquals(2, result.quantity());
        assertEquals("VALID", result.status());
    }

    @Test
    void rejectsMissingQuantity() {
        var input = new LambdaEventApplication.OrderRequest();
        input.setRequestId("REQ-102");
        input.setSku("BOOK");

        assertThrows(IllegalArgumentException.class,
            () -> app.validateOrder().apply(input));
    }

    @Test
    void rejectsNullRequest() {
        assertThrows(IllegalArgumentException.class,
            () -> app.validateOrder().apply(null));
    }
}
~~~

This test verifies **validation logic and output**. It **does not prove** that a JSON Lambda event converts properly into OrderRequest because the test constructs the POJO directly. To verify the converter, run an adapter integration test or direct invocation with a real JSON event.

## 17. Unit Testing Function<InputStream, R>

You can create a **ByteArrayInputStream** in tests to simulate the byte payload of an invocation:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

class RawEventDigestTest {

    private final LambdaEventApplication app =
        new LambdaEventApplication();

    @Test
    void rawFunctionReadsBytesWithoutJsonConversion() {
        byte[] payload =
            "{\"requestId\":\"REQ-101\",\"sku\":\"BOOK\",\"quantity\":2}"
                .getBytes(StandardCharsets.UTF_8);

        var result = app.rawEventDigest().apply(
            new ByteArrayInputStream(payload));

        assertEquals(payload.length, result.byteCount());
        assertTrue(result.sha256().matches("[0-9a-f]{64}"));
    }

    @Test
    void rejectsPayloadLargerThanDemoLimit() {
        byte[] oversized = new byte[1_048_577];

        assertThrows(IllegalArgumentException.class,
            () -> app.rawEventDigest().apply(
                new ByteArrayInputStream(oversized)));
    }
}
~~~

This test proves **the Function processes the stream**. It does not by itself prove that the AWS adapter actually passes the stream unconverted in a Lambda runtime. That part must be verified via FunctionInvoker or staging Lambda tests.

### Hash Changes with Bytes, Not JSON Semantics

You can add a test with two byte arrays representing:

~~~json
{"x":1}
~~~

and:

~~~json
{ "x": 1 }
~~~

Both JSON objects have the same value for **x**, yet different bytes, so their raw SHA-256 digests differ. Keep this property in mind if using raw bytes for signatures or checksums.

## 18. FunctionCatalog Integration Test

Spring context test verifying both beans are registered under the right names:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import java.util.function.Function;

@SpringBootTest(classes = LambdaEventApplication.class)
class LambdaEventCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void bothFunctionsAreRegistered() {
        assertNotNull(catalog.lookup("validateOrder"));
        assertNotNull(catalog.lookup("rawEventDigest"));
    }

    @Test
    void typedFunctionAcceptsPojo() {
        Function<
            LambdaEventApplication.OrderRequest,
            LambdaEventApplication.OrderValidation> fn =
                catalog.lookup("validateOrder");

        assertNotNull(fn);

        var request = new LambdaEventApplication.OrderRequest();
        request.setRequestId("REQ-101");
        request.setSku("book");
        request.setQuantity(2);

        var result = fn.apply(request);

        assertEquals("BOOK", result.sku());
    }
}
~~~

**Do not use assertSame between a FunctionCatalog wrapper and the original bean** to assert singleton behavior. Catalog can return wrappers for conversion and composition. Also do not treat this test as proof that AWS API Gateway or SQS event envelopes are unwrapped properly.

If running tests with **ManualParsingConfiguration** added, the application context must have an ObjectMapper bean and matching Jackson dependencies. If using only the two original beans of **LambdaEventApplication**, no extra configuration is needed.

## 19. Classifying Errors in the POJO and InputStream Paths

| Symptom | Error Layer | Cause and Resolution |
| --- | --- | --- |
| **ClassNotFoundException: FunctionInvoker** | Lambda packaging | Adapter missing from shaded JAR or wrong handler |
| Main class not found | Spring bootstrap | Check **MAIN_CLASS/Start-Class** and classes in JAR |
| Bean not found | FunctionCatalog | Wrong **spring_cloud_function_definition** or bean not registered |
| JSON fails to parse into POJO | Conversion | Schema, root type, field type, or mapper mismatch |
| POJO created but rejected | Validation | Null, blank, or out-of-range fields |
| **ClassCastException** with Map | Generic type | Unclear input type, unsafe cast in code |
| Raw stream yields 0 bytes | Stream lifecycle | Already read earlier or payload genuinely empty |
| OutOfMemoryError reading raw input | Memory | **readAllBytes()** on unbounded payload |
| Corrupted UTF-8 text | Encoding | Wrong encoding or treating binary as text |
| Signature/hash mismatch | Raw-byte contract | Key order, whitespace, newline, or encoding changed |
| API Gateway event does not become OrderRequest | Event envelope | Nested/base64 body or different payload version mapping |
| SQS processes only one message | Batch semantics | Event contains Records; process each record |
| S3 raw stream is not the file | Wrong source assumption | Stream is notification; use S3 GetObject to read contents |
| InputStream cannot be re-read | Ownership | Stream already consumed; use bounded buffer if needed |
| Handler returns error yet CLI invoke succeeds | AWS invocation | Check **FunctionError**, response body, and logs |

The troubleshooting sequence should be: **does the handler load → does the Spring context initialize → does the catalog pick the right function → was the input converted/read properly → does business validation succeed**.

## 20. Changing Protocols Without Changing Business Logic

Spring Cloud Function aims to keep business beans independent of the caller transport. With **OrderRequest**, a clean design is:

~~~mermaid
flowchart TB
    A["HTTP / API Gateway adapter"] --> D["OrderRequest"]
    B["SQS adapter"] --> D
    C["Serverless direct invoke"] --> D
    D --> E["validateOrder"]
    E --> F["OrderValidation"]
~~~

If events from different sources have distinct envelopes, create an **adapter** that extracts the data and calls **validateOrder**. Avoid mixing **APIGatewayProxyRequestEvent**, **SQSEvent**, and **InputStream** parsing into the same business function unless truly necessary.

When raw bytes are needed for signature verification, decoding, or custom parsing, handle that at the **adapter layer** and pass a typed DTO to the service. If the product requirement is to inspect or store the raw invocation itself, **Function<InputStream, R>** can be a direct choice, provided format, size limits, and safety constraints are clearly documented.

### Sharing POJOs Across Multiple Adapters

An **OrderRequest** type can be used by an HTTP controller, a Spring Cloud Stream mapper, or a Lambda wrapper. However, details like **HTTP status**, **API Gateway response envelopes**, **SQS partial batch failures**, or **IAM** do not belong in the business DTO.

**Protocol independence does not mean ignoring delivery differences.** Side effects can repeat due to retries; database-writing Consumers need idempotency keys and proper transactions. A read-only validation Function like the one in this example is simpler, yet still requires strict data error handling.

## 21. Security and Observability When Reading Raw Events

A raw stream can contain sensitive data, authorization tokens, identifying information, or business payloads that must never appear in logs.

Principles to follow:

- **Never log entire raw payloads** in production merely to debug conversion.
- **Never blindly trust caller-supplied content types or headers**. Enforce authentication and authorization at a trusted boundary.
- **Enforce size limits** before allocating buffers and parsing; apply parser constraints for deeply nested structures.
- **Do not treat binary data as UTF-8 text** without confirming the format.
- **Do not treat a SHA-256 hash as authentication**: verifying signatures requires proper keys/secrets, a signing algorithm, and constant-time comparison.
- **Never store InputStream or request data in singleton fields**; a Lambda execution environment may be reused across invocations.
- **Classify permanent vs. transient errors** and configure retries/dead-letter queues per trigger.
- **Log only minimal metadata** for observability (request ID, type, size, outcome); never use client-supplied correlation IDs for authorization decisions.

When working with SQS events, messages can be redelivered even if code already wrote to a database before response/ack failed. Proper POJO conversion alone does not grant exactly-once delivery; idempotency at the storage/infrastructure layer is essential.

## 22. Hands-on Exercises

**Exercise 1 — POJO.** Write **Function<PaymentRequest, PaymentValidation>** with a JavaBean POJO containing **requestId**, **currency**, and **amount**. Use nullable input types to detect missing fields, state currency/precision rules, and write validation tests.

**Exercise 2 — Raw hash.** Modify rawEventDigest to reject payloads larger than 64 KiB. Write unit tests at the exact 64 KiB boundary and one byte over, and verify SHA-256 changes when trailing whitespace is added to JSON.

**Exercise 3 — Manual parsing.** Write **Function<InputStream, OrderValidation>** using an ObjectMapper compatible with your project version. Perform a bounded read, parse JSON into OrderRequest, and call the validator. Explain why InputStream is not read twice.

**Exercise 4 — Comparing two Lambdas.** Deploy both **validateOrder** and **rawEventDigest** beans using the same shaded JAR with different **spring_cloud_function_definition** values. Send a direct invoke JSON object and compare the typed validation output with the byte digest.

**Exercise 5 — API Gateway.** An API Gateway HTTP API sends an event whose **body** is a JSON string along with **isBase64Encoded**. Design an adapter converting the envelope into OrderRequest, handling encoded bodies, and returning a response matching the payload version.

**Exercise 6 — SQS.** A Lambda receives an SQS batch with three Records. Explain why **Function<OrderRequest,R>** does not automatically represent the entire batch, and propose an event type or adapter handling each record along with a partial batch failure policy.

**Exercise 7 — S3.** An S3 notification contains only bucket/key. Explain why FunctionInvoker's InputStream does not contain the object's bytes, and which layer needs IAM permissions to fetch content from S3.

**Exercise 8 — Generic types.** Compare **Function<OrderRequest,R>**, **Function<Map<String,Object>,R>**, and **Function<InputStream,R>** in terms of conversion, type safety, versioning, and testability. Point out bugs that can occur with quantity in a Map.

**Exercise 9 — Debugging.** A direct invoke JSON has quantity as a string or nested object; the catalog picked the right bean, yet no logs appear from apply(). Identify the cause at conversion, how to inspect the actual payload, and which tests to add.

### Key Takeaways

- **FunctionInvoker** receives the invocation payload as a stream. For **Function<POJO,R>**, the adapter attempts to convert data into the POJO type; for **Function<InputStream,R>**, it **passes the stream straight to the function** without input conversion.
- **The raw InputStream is the Lambda event stream**, not automatically an HTTP body, SQS message body, or S3 file.
- **Typed POJOs** clarify the schema and aid business logic reuse; validation still must be performed rather than relying solely on converters.
- When reading the stream manually, **read once**, enforce size bounds, specify encoding, classify I/O/parsing errors, and never retain raw input beyond the invocation.
- **spring_cloud_function_definition** selects the right bean; the **FunctionInvoker** handler and **MAIN_CLASS** belong to the Lambda/Spring initialization layer.
- Testing should separate **Java logic**, **FunctionCatalog**, **conversion/event envelopes**, and **AWS invocation**. Errors at each layer must be handled at the proper boundary.

### References

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, Type Conversion, Raw Input, AWS request handlers, and events.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): FunctionCatalog, types, message handling, and composition.
- [AWS Lambda — Java handler](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html): RequestHandler, RequestStreamHandler, InputStream, and event types.
- [AWS API Gateway — Lambda proxy integration](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html): proxy event/response envelopes.
- [AWS Lambda — SQS error handling](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html): retries and partial batch responses.
