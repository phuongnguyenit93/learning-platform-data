# Building a Java function with Functions Framework

## Learning objectives

After this lesson, you will be able to:

- Explain the role of Functions Framework in writing Java functions that can run locally and be deployed to Google Cloud.
- Distinguish HTTP functions from event-driven functions based on CloudEvents.
- Create Java handlers using Functions Framework interfaces.
- Structure a Maven project, select an entry point, and run a function in a development environment.
- Deploy a function to Cloud Run functions (formerly commonly referred to as Cloud Functions 2nd gen) using the Google Cloud CLI.
- Connect a function to HTTP, Cloud Storage, Pub/Sub, and Eventarc with the appropriate trigger type.
- Design access permissions, idempotency, retries, logging, and testing for a function.

## 1. What is Functions Framework?

Functions Framework is an open-source framework that provides a programming contract for writing functions in a deployment-platform-independent way. For Java, the framework defines interfaces for HTTP functions and event-driven functions. The application implements an interface, while Functions Framework handles bootstrapping and dispatching requests or events into the handler.

A Java function can run via Functions Framework in a local environment or be packaged and deployed to a platform that supports the framework. On Google Cloud, the framework is used by Cloud Run functions. This allows developers to focus on processing logic without having to write an HTTP server or an event-receiving loop themselves.

Functions Framework is not a workflow engine, queue, or database. It provides an entry point for an invocation. Multi-step orchestration, durable state persistence, retries, and event delivery management depend on the deployment service and chosen trigger.

### 1.1. Position of the framework in the architecture

~~~mermaid
flowchart TD
    A[HTTP request or CloudEvent] --> B[Google Cloud trigger]
    B --> C[Cloud Run functions runtime]
    C --> D[Functions Framework]
    D --> E[Java function entry point]
    E --> F[Application service]
    F --> G[Database, Cloud Storage, or API]
~~~

High-level processing flow:

1. A client calls an HTTP endpoint or an event is emitted from a Google Cloud service.
2. The platform receives the request/event and creates an invocation for the function.
3. Functions Framework forwards the request/event to the Java class declared as the entry point.
4. The handler validates input, invokes the application service, and produces a result or business side effect.
5. The runtime returns an HTTP response or records event processing according to the trigger's semantics.

### 1.2. Functions Framework and Cloud Run functions

Cloud Run functions is Google Cloud's way of running source functions in a serverless model on top of Cloud Run. Product naming and management interfaces may vary across product generations; older documentation and CLI commands often use the name Cloud Functions gen2. When deploying, `gcloud functions deploy --gen2` remains a common way to create a 2nd-generation function.

Functions Framework is the handler contract that Java source implements. Cloud Run functions provides the execution environment, scaling, networking, service identity, logging, and trigger integration. Separating these two layers makes the application easy to run locally and avoids coupling business logic to a specific deployment API.

### 1.3. Two main function types

| Type | Java interface | Input | When to use |
|---|---|---|---|
| HTTP function | `HttpFunction` | HTTP request | REST endpoints, webhooks, health/status endpoints |
| Event function | `CloudEventsFunction` | CloudEvent | Cloud Storage, Pub/Sub, Eventarc, and CloudEvents-compatible events |

An HTTP function receives method, path, headers, query parameters, and body. An event function receives a CloudEvent envelope with standard attributes such as `id`, `source`, `type`, `subject`, and event data. The two handler types have different contracts; do not attempt to handle a CloudEvent as a plain HTTP request.

## 2. Creating a Maven project for Java Functions Framework

A minimal project can be organized as follows:

~~~text
hello-functions/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    ├── HelloHttp.java
                    └── StorageCreatedFunction.java
~~~

`pom.xml` declares the Functions Framework API so the compiler knows the interfaces and request/response types:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>hello-functions</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.google.cloud.functions</groupId>
      <artifactId>functions-framework-api</artifactId>
      <version>1.1.0</version>
      <scope>provided</scope>
    </dependency>
  </dependencies>
</project>
~~~

The dependency version here is an illustrative example. Choose an API version compatible with the runtime and plugins your project uses, and pin the version in Maven so builds are reproducible. Do not use dynamic versions like `LATEST` in production pipelines.

With Maven, source code lives in `src/main/java`; the entry point class must be public and implement the right interface. Builds typically use `mvn package`. The deployment artifact must contain application code and runtime dependencies in the format required by the buildpack or packaging workflow. If using a shaded JAR, carefully inspect service descriptors and resources so library metadata is not lost.

### 2.1. API dependencies and application dependencies

Separate dependencies into two groups:

- **Functions Framework API:** types like `HttpFunction`, `HttpRequest`, `HttpResponse`, `CloudEventsFunction`, and the CloudEvent contract.
- **Application dependencies:** JSON mappers, validation, database clients, Google Cloud client libraries, and business libraries.

Do not place hardcoded credentials in Maven resources or source code. When the function runs on Google Cloud, use the service account attached to the function and Application Default Credentials so client libraries acquire the runtime identity.

## 3. Building an HTTP function

An HTTP function implements `com.google.cloud.functions.HttpFunction`. Functions Framework invokes the `service` method for each request. The handler reads the request, validates conditions, and writes the status, headers, and body to the response.

### 3.1. Minimal HTTP function

~~~java
package com.example;

import com.google.cloud.functions.HttpFunction;
import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;

public final class HelloHttp implements HttpFunction {

    @Override
    public void service(
            HttpRequest request,
            HttpResponse response) throws Exception {

        if (!"GET".equals(request.getMethod())) {
            response.setStatusCode(405);
            response.appendHeader("Allow", "GET");
            response.getWriter().write("Method Not Allowed");
            return;
        }

        response.setStatusCode(200);
        response.appendHeader("Content-Type", "text/plain; charset=utf-8");
        response.getWriter().write("Hello from Java Functions Framework");
    }
}
~~~

Key points to note:

- The HTTP method must be validated against the endpoint contract.
- Status codes must reflect the processing outcome, e.g., `400` for invalid input, `401`/`403` for authentication/authorization issues, `404` when a resource is not found, and `500` for unexpected errors.
- Only write headers/body appropriate for the response. Do not return stack traces or internal details to the client.
- The handler should finish after writing the response; do not retain request/response objects for reuse across another invocation.

### 3.2. Reading query parameters, headers, and body

`HttpRequest` provides methods to read the method, URI, query parameters, headers, and input stream. Example:

~~~java
package com.example;

import com.google.cloud.functions.HttpFunction;
import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;

import java.util.List;

public final class SearchHttp implements HttpFunction {

    @Override
    public void service(
            HttpRequest request,
            HttpResponse response) throws Exception {

        if (!"GET".equals(request.getMethod())) {
            response.setStatusCode(405);
            response.appendHeader("Allow", "GET");
            return;
        }

        String query = request.getFirstQueryParameter("q").orElse("");
        List<String> tags = request.getQueryParameters().get("tag");

        if (query.isBlank()) {
            response.setStatusCode(400);
            response.getWriter().write("Missing query parameter: q");
            return;
        }

        response.setStatusCode(200);
        response.appendHeader("Content-Type", "text/plain; charset=utf-8");
        response.getWriter().write(
                "q=" + query + ", tags=" + (tags == null ? List.of() : tags));
    }
}
~~~

Specific API versions may provide `getFirstQueryParameter`, `getQueryParameters`, `getFirstHeader`, `getInputStream`, and `getReader`. Use the exact methods of the Functions Framework API version pinned by the project. Do not assume a query parameter is always present or appears only once.

For request bodies, enforce a size limit before reading the entire body into memory. Use a JSON mapper such as Jackson or Gson to deserialize into a DTO, check the schema, and validate required fields. For large payloads, consider streaming rather than reading the entire body into a single `String` or `byte[]`.

### 3.3. HTTP responses and error mapping

Standardize an error contract so clients know how to handle failures:

~~~json
{
  "error": {
    "code": "INVALID_ARGUMENT",
    "message": "The field 'email' is required",
    "requestId": "req-8f31"
  }
}
~~~

Some principles:

- Use `400 Bad Request` for invalid input.
- Use `401 Unauthorized` when authentication information is missing or invalid; `403 Forbidden` when the identity is valid but lacks permission.
- Use `404 Not Found` when a resource does not exist or security policy requires not disclosing existence.
- Use `409 Conflict` for business state conflicts.
- Use `429 Too Many Requests` when rate limiting is applied.
- Use `5xx` for server-side or dependency failures that the client can retry according to policy.

Do not map every exception to `200 OK`. At the same time, do not expose raw exceptions, SQL, tokens, secrets, or stack traces externally. Log detailed errors in controlled logs and return a safe message to the client.

### 3.4. Do not store request state in handler fields

A function class instance can be reused within the execution environment, and multiple requests can be handled concurrently depending on platform configuration. Therefore, do not put request data into shared mutable fields:

~~~java
// Avoid: request A can overwrite request B's data.
public final class UnsafeHandler implements HttpFunction {
    private String currentUser;

    @Override
    public void service(HttpRequest request, HttpResponse response) {
        currentUser = request.getFirstHeader("X-User").orElse("");
        // ...
    }
}
~~~

Keep request data in local variables inside `service`. Shared clients such as HTTP clients or database pools can be reused if they are thread-safe and initialized safely. Do not store personal data, authorization contexts, or per-request business state in static variables.

## 4. Building an event function with CloudEvents

Events from Google Cloud are typically delivered to functions as a CloudEvent. CloudEvents is an open standard describing events with a uniform envelope, so handlers do not have to depend on each service's proprietary transport format.

A Java event function implements `com.google.cloud.functions.CloudEventsFunction` and processes an `io.cloudevents.CloudEvent` object.

### 4.1. CloudEvent envelope

A CloudEvent has these key attributes:

| Attribute | Meaning |
|---|---|
| `id` | Event identifier within the scope of the source |
| `source` | Source that produced the event |
| `type` | Event type, describing what happened |
| `subject` | Specific subject within the source, if any |
| `time` | Timestamp when the event was produced, if any |
| `datacontenttype` | Content type of the event data |
| `data` | Event-specific payload |

Illustrative example of a CloudEvent for an object created in Cloud Storage:

~~~json
{
  "specversion": "1.0",
  "id": "1234567890",
  "source": "//storage.googleapis.com/projects/_/buckets/product-images",
  "type": "google.cloud.storage.object.v1.finalized",
  "subject": "objects/catalog/item-01.jpg",
  "time": "2026-11-17T08:30:00Z",
  "datacontenttype": "application/json",
  "data": {
    "bucket": "product-images",
    "name": "catalog/item-01.jpg",
    "generation": "1731832200000000",
    "contentType": "image/jpeg",
    "size": "524288"
  }
}
~~~

The CloudEvent envelope is the shared metadata layer; the structure of `data` depends on the event type. The handler should check `type` before parsing `data` according to a specific schema. Do not assume all CloudEvents share the same payload fields.

### 4.2. Java handler for a Cloud Storage event

The example below uses Jackson to read the JSON payload. The project must add Jackson Databind to its Maven dependencies:

~~~java
package com.example;

import com.google.cloud.functions.CloudEventsFunction;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.cloudevents.CloudEvent;

public final class StorageCreatedFunction implements CloudEventsFunction {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!"google.cloud.storage.object.v1.finalized".equals(event.getType())) {
            System.out.println("Ignoring event type: " + event.getType());
            return;
        }

        if (event.getData() == null) {
            throw new IllegalArgumentException("CloudEvent data is missing");
        }

        JsonNode data = MAPPER.readTree(event.getData().toBytes());

        String bucket = data.path("bucket").asText();
        String objectName = data.path("name").asText();
        String generation = data.path("generation").asText();

        if (bucket.isBlank() || objectName.isBlank() || generation.isBlank()) {
            throw new IllegalArgumentException(
                    "Required Cloud Storage event fields are missing");
        }

        System.out.printf(
                "Object finalized: bucket=%s name=%s generation=%s eventId=%s%n",
                bucket, objectName, generation, event.getId());

        // Invoke application service to process the object.
    }
}
~~~

`ObjectMapper` is created once and reused because it is safe to share after configuration. Do not hold per-event data in mutable fields. In a real application, place object-processing logic in a separate service, keeping the handler focused on validating the envelope, converting DTOs, and calling the service.

When processing files, use `bucket`, `name`, and `generation` to identify the exact object version. An object may be overwritten after the event is emitted; if you need to process the exact version that triggered the event, read the object by generation or apply an equivalent version check.

### 4.3. Distinguishing event type and event data

An event handler should check at minimum:

- Whether `event.getType()` matches the expected event type.
- Whether `event.getId()` and `event.getSource()` are present for identification.
- Whether `event.getData()` exists and has the expected content type.
- Whether required business fields in the payload are valid.
- Whether the event belongs to a tenant, bucket, topic, or resource that the function is allowed to process.

Do not use `subject` alone as a unique identifier because the same object can emit multiple events at different times or generations. Combining `source`, `id`, and a business key such as object generation supports traceability and duplicate prevention.

## 5. CloudEvents, Pub/Sub, and Eventarc

Eventarc routes events from Google Cloud sources to supported targets such as Cloud Run functions. Pub/Sub can trigger a function through its corresponding trigger; Cloud Storage can emit object finalized, deleted, or metadata updated events depending on the source configuration.

### 5.1. Event flow through Eventarc

~~~mermaid
flowchart LR
    A[Cloud Storage or Pub/Sub] --> B[Eventarc trigger]
    B --> C[Cloud Run functions endpoint]
    C --> D[Functions Framework]
    D --> E[CloudEventsFunction]
    E --> F[Validate event]
    F --> G[Idempotent application service]
    G --> H[Database or Cloud Storage]
~~~

Eventarc is responsible for filtering/routing events according to the configured trigger. Functions Framework receives the CloudEvent at the entry point. The application service processes the business logic. Each layer should have clear responsibilities so the handler and business logic can be tested independently.

### 5.2. Cloud Storage trigger deployment example

A function can be deployed with the Google Cloud CLI:

~~~bash
gcloud functions deploy storageCreated \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.StorageCreatedFunction \
  --trigger-bucket=product-images \
  --memory=512Mi \
  --timeout=120s
~~~

This example illustrates a function receiving events when an object in a bucket is created/finalized. The deploying account needs the required permissions to create the function, build source, configure Eventarc, and attach the service account. The bucket and trigger must satisfy the service's location/region requirements.

### 5.3. Pub/Sub trigger deployment example

For a Pub/Sub topic:

~~~bash
gcloud functions deploy messageProcessor \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.PubSubFunction \
  --trigger-topic=orders \
  --memory=512Mi \
  --timeout=60s
~~~

In Pub/Sub CloudEvent data, the payload is usually JSON describing the message and subscription. The `message.data` field is Base64-encoded. The handler must decode Base64 before parsing the business content; do not parse the entire CloudEvent data directly as if it were the order JSON.

### 5.4. Event error handling and retries

An event-driven function can receive the same event again if delivery or processing fails. Retry behavior, event retention duration, and dead-letter capabilities depend on the event source, Eventarc, Pub/Sub, and trigger configuration. Do not assume all triggers share the same retry policy.

Some principles:

- Treat an event as successfully processed only after the business side effect has been durably written.
- For transient errors, let the invocation fail per the trigger contract if retries are configured.
- For permanent data errors, record an investigable error and apply an appropriate skip/quarantine policy.
- Do not catch an exception and return normally if you want the platform to retry; a normal return is typically treated as the handler having completed processing.
- Monitor event retries, expired events, and dead-letter paths if supported by the source service.
- Do not infinitely retry an event with an invalid payload; doing so can create loops and extra cost.

With Pub/Sub, review the ack deadline, retry policy, subscription, and dead-letter topic. With Eventarc, check the retry policy and event retention limits for the specific trigger. When a handler throws an exception, the final behavior also depends on the trigger type and deployed configuration.

## 6. Idempotency and handling duplicate events

Serverless event delivery typically favors redelivery when it is uncertain whether an event was processed. Therefore, handlers must be safe when the same event arrives multiple times.

### 6.1. Choosing an idempotency key

A key can be constructed from the CloudEvent's `source` and `id`:

~~~java
String eventKey = event.getSource().toString()
        + ":"
        + event.getId();
~~~

Store the event key in a database with a unique constraint. If the key already exists and its status is completed, the handler can skip duplicate side effects. If the event is in progress, the system needs a lease/lock or timed status to handle cases where a previous invocation stopped midway.

For Cloud Storage, if business logic needs to distinguish object versions, include `bucket`, `name`, and `generation` in the business key. Do not rely solely on the object name if an object with the same name can be overwritten multiple times.

### 6.2. Recording state and side effects in the same transaction

An idempotent workflow should:

1. Create or claim the event key via an atomic operation.
2. Check whether the event has already completed or is being processed by another worker.
3. Perform the business side effect.
4. Persist the result and mark the event complete within a transaction or consistent protocol.
5. Return success only after durable state has been written.

If the side effect occurs in an external system, a local database transaction cannot guarantee atomicity across both systems. In that case, you need an idempotency key on the target service, an outbox/inbox pattern, or a reconciliation step to handle indeterminate states.

### 6.3. Do not use instance memory for deduplication

Do not use a `static Set<String>` or an in-memory cache to track processed events. A function can run across multiple instances, instances can be reclaimed, and multiple invocations can process the same event concurrently. Use durable storage with a unique constraint or atomic claim mechanism.

## 7. Running functions locally and the development workflow

Functions Framework lets you run functions locally to test handlers before deploying. A Maven project can configure the Functions Framework Maven plugin with a compatible version; the plugin provides a goal to run a local server.

Example running an HTTP function:

~~~bash
mvn function:run -Drun.functionTarget=com.example.HelloHttp
~~~

The local server typically listens on a configured port, commonly `8080` by default. You can test with curl:

~~~bash
curl -i http://localhost:8080/
~~~

For an event function, you must send a CloudEvent with a valid envelope and data to the local server using the CloudEvents protocol. The test payload must include `specversion`, `id`, `source`, `type`, and `data` matching the handler. Do not send plain business JSON and expect the framework to infer it is a CloudEvent.

### 7.1. Configuring the Maven plugin

The local run plugin must be declared in `pom.xml` with a pinned version. Choose a plugin version verified to be compatible with the Functions Framework API and Maven project; do not use dynamic versions in CI/CD. If the project has multiple function classes, pass `run.functionTarget` to specify which class to run.

### 7.2. Separating handlers from business logic

The handler should be thin:

- Convert the request/event into a command or DTO.
- Validate the contract, required fields, and payload limits.
- Call the application service.
- Translate the result or exception into an HTTP response or event outcome.

The business service should not depend directly on `HttpRequest`, `HttpResponse`, or `CloudEvent`. This allows testing business logic with unit tests without starting Functions Framework.

~~~mermaid
flowchart TD
    A[HttpFunction or CloudEventsFunction] --> B[Adapter / DTO mapping]
    B --> C[Application service]
    C --> D[Domain logic]
    C --> E[Repository interface]
    E --> F[Cloud SQL, Firestore, or API]
~~~

## 8. Deploying HTTP functions and securing endpoints

Example deploying an HTTP function on Cloud Run functions:

~~~bash
gcloud functions deploy helloHttp \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.HelloHttp \
  --trigger-http \
  --memory=512Mi \
  --timeout=30s \
  --max-instances=10
~~~

To expose an endpoint publicly for a demo, you can configure unauthenticated invocation according to project policy. For real APIs, require IAM authentication or place an API Gateway/authenticated entry layer in front. Do not enable public access just to curl-test if the endpoint can mutate data or access internal resources.

### 8.1. IAM and service accounts

Distinguish two identity roles:

- **Invoker identity:** the identity allowed to call the function/endpoint.
- **Runtime service account:** the identity the function uses when calling Cloud Storage, Pub/Sub, Secret Manager, databases, or other services.

Do not grant Owner/Editor to the runtime service account just to make the function work. Grant least-privilege permissions on the exact resources needed. If the function reads one bucket, grant read permission only on that bucket; if it publishes to one topic, grant publish permission on that topic.

For internal HTTP endpoints, clients need a token or appropriate authentication mechanism. For event triggers, Eventarc/Pub/Sub needs an identity and permissions to deliver events to the target. Granting trigger permissions and runtime service account permissions are two separate concerns.

### 8.2. Secrets and environment configuration

Do not hardcode API keys, passwords, or private keys in source code, Maven resources, or image layers. Use Secret Manager and grant secret access to the runtime service account. Non-sensitive parameters can be passed via environment variables or deployment configuration.

Logs must not contain secrets, bearer tokens, personal data, or full sensitive request bodies. When logging errors, prioritize error codes, request IDs, event IDs, and correlation IDs.

## 9. Example: reading a Pub/Sub message in a CloudEvent

Pub/Sub CloudEvent data usually contains a `message` object; the message's `data` field is a Base64 string. The handler must decode it before converting to JSON or a business DTO.

~~~java
package com.example;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.functions.CloudEventsFunction;
import io.cloudevents.CloudEvent;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class PubSubFunction implements CloudEventsFunction {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!"google.cloud.pubsub.topic.v1.messagePublished"
                .equals(event.getType())) {
            return;
        }

        if (event.getData() == null) {
            throw new IllegalArgumentException("Missing Pub/Sub event data");
        }

        JsonNode envelope = MAPPER.readTree(event.getData().toBytes());
        String encoded = envelope.path("message").path("data").asText();

        if (encoded.isBlank()) {
            throw new IllegalArgumentException("Pub/Sub message data is empty");
        }

        byte[] decoded = Base64.getDecoder().decode(encoded);
        String payload = new String(decoded, StandardCharsets.UTF_8);

        System.out.printf(
                "Received Pub/Sub event id=%s source=%s payloadBytes=%d%n",
                event.getId(), event.getSource(), decoded.length);

        // Parse payload and invoke application service.
    }
}
~~~

The actual payload may be JSON, text, or binary. Convert to a UTF-8 string only when the producer has defined message data as UTF-8 text. If the payload is binary, pass the byte array to the appropriate service. Validate size before deserializing to avoid unbounded memory consumption.

## 10. Configuring and deploying functions

Cloud Run functions supports source builds, selecting a runtime, entry point, trigger, and resource limits. Configuration should be managed alongside source code or deployment templates so it can be reviewed and reproduced.

### 10.1. Deploying an HTTP function

Example:

~~~bash
gcloud functions deploy helloHttp \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.HelloHttp \
  --trigger-http \
  --memory=512Mi \
  --timeout=30s \
  --max-instances=10
~~~

Key flags:

- `--gen2`: deploys a 2nd-generation function on Cloud Run.
- `--runtime=java21`: selects the Java 21 runtime supported in the example.
- `--region`: selects the region aligned with users, data, and dependent services.
- `--source`: directory containing source code and `pom.xml`.
- `--entry-point`: fully qualified name of the Java class implementing the function interface.
- `--trigger-http`: creates an HTTP trigger.
- `--memory` and `--timeout`: set resource limits and invocation timeout.
- `--max-instances`: limits maximum instances to control scaling and load on dependencies.

This example does not enable public access. If the endpoint needs to be public for a demo, configure unauthenticated permissions intentionally and only for handlers that do not expose sensitive data or operations. For internal endpoints, keep IAM authentication required and grant the invoker role to the proper principal.

### 10.2. Deploying an event function

A function receiving Cloud Storage events can use this command:

~~~bash
gcloud functions deploy storageCreated \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.StorageCreatedFunction \
  --trigger-bucket=product-images \
  --memory=512Mi \
  --timeout=120s
~~~

For Pub/Sub, replace the bucket trigger with a topic trigger:

~~~bash
gcloud functions deploy messageProcessor \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.PubSubFunction \
  --trigger-topic=orders \
  --memory=512Mi \
  --timeout=60s
~~~

These commands are examples; verify runtimes, flags, and trigger region requirements in the Google Cloud CLI version you are using. Eventarc may require enabled APIs, service agents, and appropriate IAM permissions. For Cloud Storage, the bucket and trigger must satisfy location requirements. For Pub/Sub, the topic and function must be configured in a region/path that meets service requirements.

### 10.3. Build, deploy, and verify

A baseline deployment workflow:

1. Build the project and inspect the artifact.
2. Verify the entry point class implements the right interface.
3. Verify dependencies and compatible Java runtime.
4. Ensure relevant APIs are enabled and the deploying account has permissions.
5. Deploy the function to the chosen region.
6. Check build/deploy status and trigger status.
7. Send a test HTTP request or emit a test event.
8. Inspect logs, status, business outcome, and access permissions.
9. Test duplicates/retries and verify idempotency before sending production traffic.

If the build fails, read Cloud Build logs to identify Maven, dependency, or runtime errors. If the build succeeds but invocations fail, check the entry point, function signature, runtime logs, service account, and permissions to dependent services.

### 10.4. Region and data locality

Choose a region based on where users and data are served, latency to databases, data residency requirements, and trigger support. Placing a function in one region while the database or bucket is in a distant region increases latency, data transfer costs, and operational risk.

Do not simply pick the region closest to users if data is required to reside in another location. With Cloud Storage/Eventarc, verify location constraints across the bucket, trigger, and function before deploying.

## 11. Concurrency, autoscaling, and cold starts

Cloud Run functions can spin up additional instances when load increases and scale down when load drops. The number of instances and concurrent requests per instance depend on configuration, runtime, and platform limits.

### 11.1. Designing concurrency-safe handlers

Do not assume each instance handles only one request at a time. An instance may receive multiple concurrent requests depending on the concurrency setting. Therefore:

- Method-local variables are appropriate for holding per-request data.
- Immutable fields and thread-safe clients can be shared if supported by the library.
- Do not store user ID, tenant ID, request body, or transaction state in mutable static fields.
- Database pools must be bounded and sized appropriately for concurrent requests.
- Temporary files must have unique names; do not use a single fixed filename for all requests.
- Use locks or transactions in durable storage when multiple requests can update the same resource.

### 11.2. Limiting concurrency and instance count

High concurrency can increase throughput but can also overload databases, external APIs, or memory. Setting max instances caps instance count, but does not replace rate limits or downstream connection limits.

For example, if each instance opens a pool of up to 10 connections and the function can scale to 20 instances, the database may face up to around 200 connections from this function alone. Size according to concurrency, pool size, and other services sharing the database.

For bursty workloads, use a queue to absorb spikes and have workers process at capacity. Set max instances or concurrency in line with dependency quotas and SLAs.

### 11.3. Cold starts and Java initialization

Cold starts occur when the platform needs to create a new execution environment, start the JVM, load classes, and initialize dependencies before serving the first request. Large frameworks, bloated classpaths, database client initialization, or synchronous configuration loading can increase startup time.

Ways to reduce initialization time:

- Trim unnecessary dependencies and reduce artifact size.
- Initialize shared clients once when appropriate, avoiding re-creation on every request.
- Do not run database queries or external API calls inside static initializers.
- Load required configuration in a controlled manner; do not bootstrap an entire application if the function uses only a small slice.
- Measure cold starts separately from warm durations.
- Consider minimum instances when latency requirements are strict and the cost of keeping instances warm is acceptable.

Do not put all initialization work into static blocks if it can fail due to transient network or credential issues. An initialization failure can prevent the instance from becoming ready and cause multiple requests to fail. Separate safe, reusable dependency initialization from operations that depend on a request or user state.

## 12. Logging, monitoring, and tracing

A function needs observability across both requests and events. Logs containing only "function started" and "function finished" are insufficient for investigating retries or duplicate events.

### 12.1. Recommended log fields

- `requestId` or trace ID for HTTP requests.
- `eventId`, `source`, and `type` for CloudEvents.
- `functionName`, `revision`, or version when distinguishing deployments.
- `operation` and business outcome code.
- `durationMs`, retry count if available, and error code.
- Allowed `tenantId` or an obfuscated identifier.

Do not log secrets, bearer tokens, session cookies, personal data, or sensitive file contents. Use structured logging to filter by field and correlate with traces. If logging JSON, keep the schema stable so Cloud Logging parses it accurately.

### 12.2. Key metrics

| Metric | Question to answer |
|---|---|
| Request count | How many requests/events is the function receiving? |
| Request latency p50/p95/p99 | How does latency change with load? |
| Error rate | How many invocations are failing? |
| Instance count/concurrency | Is autoscaling keeping up with load? |
| Cold start/initialization duration | Is Java initialization impacting latency? |
| Memory utilization | Is there a risk of OOM or memory pressure? |
| Event retry/dead-letter count | Which events are being retried repeatedly or failing persistently? |
| Downstream latency | Which database or API is the bottleneck? |

Cloud Monitoring/Cloud Logging provides platform metrics and runtime logs. You can add custom metrics for business outcomes such as orders processed successfully, objects skipped, or duplicate events. Avoid high-cardinality metric labels like request ID or object name.

### 12.3. Tracing across services

If the function calls Cloud SQL, Firestore, Pub/Sub, or HTTP APIs, tracing helps identify whether time is spent in the handler or a dependency. Propagate trace/correlation IDs across internal calls whenever possible. For asynchronous events, attach event ID and source to logs to link producer and consumer steps.

## 13. Testing Java functions

Testing can be performed across multiple layers:

- **Unit tests:** verify the application service, validation, and mapping with normal inputs/outputs.
- **Handler tests:** construct simulated requests/events or use appropriate test utilities to verify the handler.
- **Local integration:** run Functions Framework locally and send HTTP requests or CloudEvents.
- **Cloud integration:** deploy to a test project and trigger via HTTP, Cloud Storage, or Pub/Sub.
- **Resilience tests:** send duplicate events, malformed schemas, dependency timeouts, and concurrent requests.

For example, unit tests for the business service should not require Google Cloud credentials or deploying the function. You can mock repositories and assert business results. Handler tests focus on status codes, response bodies, or how the handler reacts to invalid events.

When testing events, include:

- Unsupported event types.
- Missing `id`, `source`, or required data.
- Malformed JSON payloads or wrong encoding.
- Events redelivered multiple times.
- Two invocations processing the same event nearly concurrently.
- A dependency failing transiently and then recovering.
- Events with invalid object generation or tenant.

When testing HTTP, include unsupported methods, repeated/missing query parameters, oversized bodies, invalid JSON schemas, unauthorized callers, and dependency timeouts.

## 14. Security and access control

A function is an execution boundary that can be invoked from the internet or from internal services. Security must be enforced at both the invocation layer and the resource access layer.

- Enable public invocation only when the endpoint is designed to be public.
- Use IAM invoker permissions or an authentication layer in front of internal endpoints.
- Grant the runtime service account only the minimum permissions required.
- Do not trust client-supplied tenant/user data without authentication and authorization checks.
- Validate bucket, object, topic, and resource IDs before accessing them.
- Use Secret Manager for secrets; do not log credentials.
- Bound request size, execution time, and concurrency to reduce abuse risk.
- Use appropriate network/VPC configuration if accessing private resources.
- Validate event source and event type; do not treat every CloudEvent as trusted data.

An event that is valid according to the CloudEvents specification can still contain a business-invalid payload. Verify signatures/provenance at the trigger layer if receiving external events, and still validate data inside the handler.

## 15. Common mistakes when building Java functions

- **Choosing the wrong entry point:** the class does not implement the right interface or the class name in the deploy command is incomplete.
- **Confusing HTTP functions with event functions:** HTTP requests and CloudEvents have different contracts; handlers must implement the right interface.
- **Putting business logic inside the handler:** makes logic hard to test and tightly couples it to the framework.
- **Reading unbounded request bodies:** large payloads can cause memory pressure or timeouts.
- **Not checking the event type:** parses data with the wrong schema and causes runtime errors.
- **Not decoding Pub/Sub Base64:** the handler receives an encoded string instead of the business payload.
- **Missing idempotency:** event redelivery creates duplicate side effects.
- **Catching exceptions and returning normally:** the trigger may consider the event processed successfully and skip retries.
- **Storing request state in static fields:** concurrent requests can overwrite each other's data.
- **Over-provisioning service account permissions:** a bug in the function can impact many resources.
- **Ignoring region/location constraints:** triggers fail to create or data has to traverse long distances.
- **Not checking logs after deployment:** a successful build does not guarantee invocation and access permissions are correct.

## 16. Deployment checklist

- [ ] Entry point class properly implements `HttpFunction` or `CloudEventsFunction`.
- [ ] Functions Framework API and Java runtime versions are pinned and compatible.
- [ ] Maven build produces the proper artifact with complete runtime dependencies.
- [ ] Local HTTP/Event tests pass with representative payloads.
- [ ] HTTP methods, status codes, headers, and bodies follow the contract.
- [ ] CloudEvent handler checks type, source, id, and data.
- [ ] Pub/Sub payloads are properly Base64-decoded when applicable.
- [ ] Event handler has an idempotency key and handles duplicates.
- [ ] Retry policy fits the trigger type and business error semantics.
- [ ] Entry point, trigger, region, memory, and timeout are verified.
- [ ] Runtime service account has least-privilege permissions.
- [ ] Endpoint is public only intentionally; IAM invoker is configured properly.
- [ ] Secrets are retrieved from Secret Manager or an appropriate secret management mechanism.
- [ ] Logs include request/event IDs and contain no sensitive data.
- [ ] Concurrency, cold starts, and load on dependencies have been checked.
- [ ] Dashboards/alerts exist for error rate, latency, retries, and dead-letter queues.

## 17. Self-check

**Question 1.** What problem does Functions Framework solve in Java serverless development?

**Suggested answer:** It provides the contract and runtime adapter for HTTP functions or CloudEvents functions, allowing handlers to run locally and deploy to platforms that support the framework without writing an HTTP server or event loop manually.

**Question 2.** How do HTTP functions and CloudEvents functions differ?

**Suggested answer:** An HTTP function implements `HttpFunction` and receives `HttpRequest`/`HttpResponse`. An event function implements `CloudEventsFunction` and receives a CloudEvent envelope containing source, id, type, and data.

**Question 3.** Why must an event handler be idempotent?

**Suggested answer:** Events may be redelivered when delivery or processing is uncertain. Idempotency ensures the same event does not create duplicate business side effects, even if an invocation reruns on another instance.

**Question 4.** Why should you avoid storing user IDs or request state in static fields?

**Suggested answer:** Instances can be reused and process multiple requests concurrently. Mutable shared state can be overwritten by another request and leak data across users.

**Question 5.** Why can a function still fail at runtime/deployment even if the build succeeds?

**Suggested answer:** You might have specified the wrong entry point, lacked IAM permissions, misconfigured the trigger/region, missed runtime dependencies, lacked permissions on the service account, or received real payloads that do not match the schema.

**Scenario exercise:** Build an image-processing function triggered when a user uploads an object to Cloud Storage. The function needs to read metadata, generate a thumbnail, and save the result to another bucket. Design the entry point class, CloudEvent fields to inspect, service account permissions, idempotency key, event retry handling, and required logs. Then propose how to run locally, deploy to Cloud Run functions, and verify with a test object.

**Hint:** Use a class implementing `CloudEventsFunction`; accept only finalized event types; read `bucket`, `name`, and `generation`; validate the bucket against an allowlist. The idempotency key can combine CloudEvent `source/id` or bucket/object/generation depending on business rules. The runtime service account needs only read permission on the source bucket and write permission on the thumbnail destination bucket. Use a deterministic object key based on generation so retries do not create uncontrolled duplicate files. Run locally with a sample CloudEvent, deploy gen2 in an appropriate region, and create a test object; verify logs, output object, permissions, and behavior when replaying the event.

## Conclusion

Functions Framework provides the Java contract for HTTP functions and CloudEvents-based event functions. Handlers should focus on adapting inputs, validating requests/events, and invoking application services; business logic, state, and idempotency must be managed independently. When deploying Cloud Run functions, choose the right entry point, runtime, trigger, region, and service account. HTTP endpoints require IAM or appropriate authentication; event handlers must check event types, prevent duplicate processing, and understand trigger retry semantics. Running locally, testing realistic payloads, monitoring logs/metrics, and verifying permissions after deployment help Java functions operate safely in a serverless environment.
