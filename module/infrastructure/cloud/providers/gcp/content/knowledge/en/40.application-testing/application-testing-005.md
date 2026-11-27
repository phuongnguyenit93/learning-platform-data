# Testing Cloud Run Functions with Functions Framework

Cloud Run functions let you deploy small functions that handle HTTP requests or CloudEvents from systems such as Pub/Sub and Cloud Storage. A function can be only a few dozen lines long and still fail due to input validation, event formatting, IAM permissions, external services, or event redelivery. **Functions Framework** lets you run functions locally with the same programming interface on a development machine to verify behavior before deploying to Google Cloud.

This lesson belongs to the **GCP Application Testing** chapter in the **CLOUD_PROVIDERS_GCP** module. Along the path exploring Google Cloud from projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, databases, and release workflows, function testing is the step that validates changes safely, reduces deployment risk, tracks reliability, and controls testing cost.

After this lesson, you will be able to:

- Distinguish unit tests, local integration tests, staging smoke tests, and end-to-end tests for Cloud Run functions.
- Write a Java HTTP function using the `HttpFunction` interface; mock `HttpRequest`/`HttpResponse` with JUnit and Mockito.
- Run an HTTP function via Functions Framework on localhost and send requests with `curl`.
- Write a `CloudEventsFunction` and test payloads/event metadata conforming to CloudEvents 1.0.
- Simulate Cloud Storage or Pub/Sub events with accurate headers, content types, and data envelopes.
- Integrate tests into CI/CD and verify IAM, retries, idempotency, logs, timeouts, and local environment limitations.

## 1. Where Does Functions Framework Fit in a Function's Lifecycle?

Functions Framework is an open-source library providing the function execution contract. In Java, you write a class implementing one of two interfaces:

| Signature | Java Interface | Entry Point | When to Use |
|---|---|---|---|
| HTTP | com.google.cloud.functions.HttpFunction | service(HttpRequest, HttpResponse) | API endpoints, webhooks, HTTP requests |
| CloudEvent | com.google.cloud.functions.CloudEventsFunction | accept(CloudEvent) | Eventarc, Cloud Storage, Pub/Sub, or other CloudEvents sources |

In Java, the **entry point is the fully-qualified class name including its package**, such as `com.example.functions.GreetingFunction`. Functions Framework detects the signature from the interface the class implements; Node.js/Python signature-type flags are not needed for Java.

~~~mermaid
flowchart TD
    SOURCE["Java source<br/>HttpFunction / CloudEventsFunction"]
    SOURCE --> UNIT["Unit test<br/>JUnit + Mockito"]
    SOURCE --> FF["Functions Framework<br/>local HTTP server"]
    FF --> LOCAL["Local integration test<br/>curl / HttpClient / CloudEvents"]
    LOCAL --> PIPE["CI validation<br/>build + tests"]
    PIPE --> STAGE["Cloud Run staging<br/>deploy + trigger"]
    STAGE --> E2E["E2E with Eventarc / IAM / services"]
    E2E --> PROD["Production release"]
~~~

When running locally, Functions Framework starts an HTTP server, typically on port 8080. The server receives HTTP requests and invokes the corresponding method on the function. For CloudEvents, the framework converts requests carrying CloudEvents metadata into a `CloudEvent` object.

**Limitation to understand:** local execution does not automatically reproduce Cloud Run, Eventarc, IAM, Cloud SQL, Secret Manager, VPC networking, autoscaling, or quotas. It simulates the **function invocation contract**; platform integration must be tested in a test environment on Google Cloud.

## 2. Layered Testing Strategy

Do not try to turn every test into a live deployment. Each layer guarantees a distinct property:

| Layer | What It Verifies | Where It Runs | Real Infrastructure Dependency? |
|---|---|---|---|
| Unit | Conditionals, mapping, validation, responses, and business logic | JVM in Maven test | No |
| Component | How the function invokes adapters for backing services | JVM with fakes/mocks | Usually no |
| Local integration | Functions Framework boots the right entry point, receives HTTP/CloudEvent, returns valid status | Localhost | No, if dependencies are mocked/faked |
| Staging integration | Auth, service accounts, secrets, networking, and real databases in a test project | Cloud Run staging | Yes |
| End-to-end | Chain producer → Pub/Sub/Eventarc → function → output | Google Cloud test project | Yes |
| Regression/contract | Schemas, required fields, bad-input handling, and event version compatibility | JVM, local, or staging | Depends on test level |

A practical pipeline runs unit tests on every pull request, local integration tests during build, and staging smoke tests and E2E on critical release branches. Because E2E is slower and costlier, focus it on high-value platform behaviors: invocation permissions, Eventarc triggers, live data, and retry behavior.

## 3. Maven Project for a Java Function

The hands-on example uses **Java 17**, Maven, and an independently testable HTTP function.

Project structure:

~~~text
functions-testing-demo/
  pom.xml
  src/
    main/
      java/
        com/example/functions/
          GreetingFunction.java
          StorageFinalizedFunction.java
    test/
      java/
        com/example/functions/
          GreetingFunctionTest.java
          GreetingHttpIT.java
          StorageFinalizedFunctionTest.java
~~~

Complete `pom.xml` example for the main snippets:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>functions-testing-demo</artifactId>
  <version>1.0.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.google.cloud.functions</groupId>
      <artifactId>functions-framework-api</artifactId>
      <version>1.1.2</version>
      <scope>provided</scope>
    </dependency>

    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
      <scope>test</scope>
    </dependency>

    <dependency>
      <groupId>org.mockito</groupId>
      <artifactId>mockito-core</artifactId>
      <version>5.10.0</version>
      <scope>test</scope>
    </dependency>

    <dependency>
      <groupId>io.cloudevents</groupId>
      <artifactId>cloudevents-core</artifactId>
      <version>2.5.0</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>

      <plugin>
        <groupId>com.google.cloud.functions</groupId>
        <artifactId>function-maven-plugin</artifactId>
        <version>0.11.0</version>
        <configuration>
          <functionTarget>com.example.functions.GreetingFunction</functionTarget>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

- `functions-framework-api` provides the Java interfaces. The `provided` scope matches the Cloud Run functions runtime; the local invoker supplies the required runtime.
- `function-maven-plugin` provides the `function:run` goal for local execution.
- JUnit and Mockito support unit tests; test-scoped `cloudevents-core` builds `CloudEvent` fixtures.
- The versions above form an illustrative set that you can cross-check against upstream documentation. Before upgrading or using in production, verify compatibility with your JDK, selected runtime, and project dependency tree.

Use Maven `test` to run standard tests:

~~~bash
mvn -B test
~~~

The `function:run` goal **runs the function locally**, whereas Maven `test` runs Java tests; they serve two different purposes.

## 4. Writing a Testable HTTP Function

The following function supports only `GET`. If the `name` parameter is missing, it responds with a default greeting. If the parameter is too long, it rejects the request. If the HTTP method is unsupported, it returns 405.

File `src/main/java/com/example/functions/GreetingFunction.java`:

~~~java
package com.example.functions;

import com.google.cloud.functions.HttpFunction;
import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;
import java.io.IOException;

public final class GreetingFunction implements HttpFunction {
    @Override
    public void service(HttpRequest request, HttpResponse response)
            throws IOException {
        response.appendHeader("Content-Type", "text/plain; charset=UTF-8");

        if (!"GET".equals(request.getMethod())) {
            response.setStatusCode(405);
            response.appendHeader("Allow", "GET");
            response.getWriter().write("Method not allowed");
            return;
        }

        String name = request.getFirstQueryParameter("name")
                .orElse("World").trim();

        if (name.isEmpty()) {
            name = "World";
        }

        if (name.length() > 60) {
            response.setStatusCode(400);
            response.getWriter().write("Invalid name");
            return;
        }

        response.getWriter().write("Hello, " + name + "!");
    }
}
~~~

Here, `HttpRequest` and `HttpResponse` are interfaces, so Mockito can stub them in unit tests. The business logic is also concise enough to clearly illustrate test cases, expected statuses, and response bodies.

For a production function, split responsibilities into two layers:

1. **Handler/adapter** receives `HttpRequest`, validates inputs, calls the service, and builds the response.
2. **Business service** enforces rules independently of Functions Framework.

This lets you unit test business logic without starting an HTTP server. The function does not need to instantiate SDK clients or database connections per request; shared clients can be initialized at instance startup when appropriate for concurrency and lifecycle requirements.

## 5. Unit Testing an HTTP Function with JUnit and Mockito

Unit tests call `service()` directly. Tests do not boot Functions Framework or touch the network.

File `src/test/java/com/example/functions/GreetingFunctionTest.java`:

~~~java
package com.example.functions;

import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;
import java.io.BufferedWriter;
import java.io.StringWriter;
import java.util.Optional;
import org.junit.Before;
import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.mockito.Mockito.*;

public class GreetingFunctionTest {
    private HttpRequest request;
    private HttpResponse response;
    private StringWriter output;
    private BufferedWriter writer;

    @Before
    public void setUp() throws Exception {
        request = mock(HttpRequest.class);
        response = mock(HttpResponse.class);
        output = new StringWriter();
        writer = new BufferedWriter(output);

        when(response.getWriter()).thenReturn(writer);
    }

    @Test
    public void returnsGreetingForQueryParameter() throws Exception {
        when(request.getMethod()).thenReturn("GET");
        when(request.getFirstQueryParameter("name"))
                .thenReturn(Optional.of("Lan"));

        new GreetingFunction().service(request, response);
        writer.flush();

        assertEquals("Hello, Lan!", output.toString());
        verify(response, never()).setStatusCode(400);
        verify(response, never()).setStatusCode(405);
    }

    @Test
    public void usesDefaultNameWhenParameterMissing() throws Exception {
        when(request.getMethod()).thenReturn("GET");
        when(request.getFirstQueryParameter("name"))
                .thenReturn(Optional.empty());

        new GreetingFunction().service(request, response);
        writer.flush();

        assertEquals("Hello, World!", output.toString());
    }

    @Test
    public void rejectsUnsupportedMethod() throws Exception {
        when(request.getMethod()).thenReturn("POST");

        new GreetingFunction().service(request, response);
        writer.flush();

        verify(response).setStatusCode(405);
        verify(response).appendHeader("Allow", "GET");
        assertEquals("Method not allowed", output.toString());
    }

    @Test
    public void rejectsTooLongName() throws Exception {
        when(request.getMethod()).thenReturn("GET");
        when(request.getFirstQueryParameter("name"))
                .thenReturn(Optional.of("x".repeat(61)));

        new GreetingFunction().service(request, response);
        writer.flush();

        verify(response).setStatusCode(400);
        assertEquals("Invalid name", output.toString());
    }
}
~~~

**Why call `flush()` in tests?** `HttpResponse.getWriter()` is mocked with a test-owned `BufferedWriter`. Written characters may remain buffered until flushed, so the test calls `flush()` before reading `StringWriter`. When running under Functions Framework, the framework manages the real response lifecycle.

### Additional Test Cases to Include

| Category | Input | Expected Outcome |
|---|---|---|
| Happy path | GET ?name=Lan | 200, body `Hello, Lan!` |
| Default | GET without name | 200, `Hello, World!` |
| Validation | name exceeds limit | 400 |
| HTTP contract | POST | 405, `Allow` header |
| International characters | GET with UTF-8 URL-encoded value | Response uses proper charset |
| Dangerous input | HTML markup in name | Not interpreted as HTML when returned as `text/plain` |
| Fault injection | Backing service throws exception | Controlled error response, no secret leakage |
| Timeout | Dependency slower than budget | Aborts or returns error within limit |

Avoid writing tests that only assert a mock was called and treating that as proof the whole function works. Choose assertions reflecting the API contract or business outcome.

## 6. Running an HTTP Function with Functions Framework

### 6.1. Starting the Local Invoker

Run from the directory containing `pom.xml`:

~~~bash
mvn function:run \
  -Drun.functionTarget=com.example.functions.GreetingFunction \
  -Drun.port=8080
~~~

Once the command starts the server, open a second terminal on the same machine and send a request:

~~~bash
curl -i "http://localhost:8080/?name=Lan"
~~~

Expected result: HTTP 200 with body `Hello, Lan!`.

Test error branches:

~~~bash
curl -i -X POST "http://localhost:8080/"
curl -i "http://localhost:8080/?name=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
~~~

The first command must return 405. The second sends 61 `x` characters and must return 400.

On Windows PowerShell, use `curl.exe` to avoid the `Invoke-WebRequest` alias in older PowerShell versions:

~~~powershell
curl.exe -i "http://localhost:8080/?name=Lan"
~~~

Java Functions Framework accepts `run.functionTarget` and `run.port` via Maven properties; it automatically infers HTTP vs. CloudEvent from the entry point's implemented interface. When running multiple functions concurrently, assign distinct ports (e.g., 8080 and 8081).

### 6.2. Testing Coverage Achieved

Running locally catches errors such as:

- Wrong Java entry point package or class name.
- Class failing to implement the appropriate interface.
- Missing runtime dependency or misconfigured Maven plugin.
- Mismatched HTTP method, headers, encoding, response status, or body.
- Server failing to bind the port or throwing startup exceptions.

However, local runs do not prove `run.invoker` permissions, service account IAM, Eventarc triggers, Secret Manager access, or Cloud Run autoscaling are configured properly.

## 7. HTTP Integration Testing Over Localhost

You can automate HTTP requests using Java's `HttpClient`. This test requires **Functions Framework already running on localhost** before starting. Name it `*IT` to distinguish it from unit tests.

File `src/test/java/com/example/functions/GreetingHttpIT.java`:

~~~java
package com.example.functions;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class GreetingHttpIT {
    @Test
    public void frameworkDispatchesHttpRequest() throws Exception {
        String baseUrl = System.getenv()
                .getOrDefault("FUNCTION_TEST_URL", "http://localhost:8080");

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/?name=Lan"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> result = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, result.statusCode());
        assertEquals("Hello, Lan!", result.body());
    }
}
~~~

Execution order:

1. Terminal A: start `mvn function:run` with `GreetingFunction`.
2. Terminal B: run the targeted test command.
3. After testing, stop the local invoker (`Ctrl+C`).

~~~bash
mvn -B -Dtest=GreetingHttpIT test
~~~

Maven Surefire picks up `*Test` names by default, but does not automatically run all `*IT` names. Passing `-Dtest=GreetingHttpIT` forces running the specific integration test. In a more standard pipeline, use Maven Failsafe in the `integration-test`/`verify` phases and manage the local server lifecycle within the same job.

### Essential Checks for HTTP Integration Tests

- Correct response codes for HTTP GET and POST.
- `Content-Type` header, encoding, and parameter parsing.
- JSON body parsing when the function accepts POST payloads.
- Responses for missing or invalid bodies.
- Timeouts when endpoints are slow.
- Sequential requests do not leak state across invocations.

Unit tests verify logic; this integration test confirms the framework actually dispatches the right class and handles serialization/requests cleanly.

## 8. CloudEvent Function: Receiving Events from Cloud Storage

Event-driven functions use the `CloudEvent` signature. Eventarc delivers events conforming to CloudEvents 1.0; a `CloudEvent` object carries common attributes and a payload.

Core attributes:

| Attribute | Meaning |
|---|---|
| id | Event ID assigned by the producer |
| source | Event-emitting source |
| type | Event type, such as object finalized |
| specversion | CloudEvents specification version |
| time | Event timestamp, if supplied by the producer |
| data | Payload matching the event source's schema |

Example function handling Cloud Storage object creation events. To stay focused on testability, the handler forwards metadata and payload to an injected `EventSink`. The default constructor merely logs the event ID; in a real system, replace it with a controlled storage/processing service.

File `src/main/java/com/example/functions/StorageFinalizedFunction.java`:

~~~java
package com.example.functions;

import com.google.cloud.functions.CloudEventsFunction;
import io.cloudevents.CloudEvent;
import java.nio.charset.StandardCharsets;
import java.util.logging.Logger;

public final class StorageFinalizedFunction implements CloudEventsFunction {
    private static final Logger LOGGER =
            Logger.getLogger(StorageFinalizedFunction.class.getName());
    private static final String EVENT_TYPE =
            "google.cloud.storage.object.v1.finalized";

    @FunctionalInterface
    interface EventSink {
        void record(String eventKey, String payload) throws Exception;
    }

    private final EventSink sink;

    // This constructor is invoked by Functions Framework via reflection.
    public StorageFinalizedFunction() {
        this((key, payload) -> LOGGER.info("Processed event: " + key));
    }

    // Constructor for unit tests or dependency injection.
    StorageFinalizedFunction(EventSink sink) {
        this.sink = sink;
    }

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!EVENT_TYPE.equals(event.getType())) {
            return;
        }

        if (event.getData() == null) {
            throw new IllegalArgumentException("Missing CloudEvent data");
        }

        String eventKey = event.getSource() + "#" + event.getId();
        String json = new String(
                event.getData().toBytes(), StandardCharsets.UTF_8);

        sink.record(eventKey, json);
    }
}
~~~

In production code, parse the JSON according to the Cloud Storage schema, validate bucket/name/generation, and back the sink with durable idempotency. The sample proves routing and testability without writing files or updating a database.

**Distinction:** Pub/Sub and Cloud Storage events use different payload structures. Never reuse one generic dummy JSON payload for all sources; test fixtures must accurately reflect the event type and schema emitted by the actual trigger.

## 9. Unit Testing CloudEvents with CloudEventBuilder

The CloudEvents Java SDK supports building spec 1.0 event fixtures. You do not need to start Functions Framework to invoke `accept()` directly.

File `src/test/java/com/example/functions/StorageFinalizedFunctionTest.java`:

~~~java
package com.example.functions;

import io.cloudevents.CloudEvent;
import io.cloudevents.core.builder.CloudEventBuilder;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.junit.Test;

import static org.junit.Assert.assertThrows;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class StorageFinalizedFunctionTest {
    @Test
    public void forwardsFinalizedEventToSink() throws Exception {
        StorageFinalizedFunction.EventSink sink =
                mock(StorageFinalizedFunction.EventSink.class);

        String payload = "{\"bucket\":\"test-bucket\",\"name\":\"a.txt\"}";
        CloudEvent event = CloudEventBuilder.v1()
                .withId("evt-123")
                .withSource(URI.create(
                        "//storage.googleapis.com/projects/_/buckets/test-bucket"))
                .withType("google.cloud.storage.object.v1.finalized")
                .withData("application/json",
                        payload.getBytes(StandardCharsets.UTF_8))
                .build();

        new StorageFinalizedFunction(sink).accept(event);

        verify(sink).record(
                contains("evt-123"),
                eq(payload));
    }

    @Test
    public void ignoresUnexpectedEventType() throws Exception {
        StorageFinalizedFunction.EventSink sink =
                mock(StorageFinalizedFunction.EventSink.class);

        CloudEvent event = CloudEventBuilder.v1()
                .withId("evt-999")
                .withSource(URI.create("https://example.com"))
                .withType("com.example.other")
                .build();

        new StorageFinalizedFunction(sink).accept(event);
        verifyNoInteractions(sink);
    }

    @Test
    public void rejectsMissingPayload() {
        StorageFinalizedFunction.EventSink sink =
                mock(StorageFinalizedFunction.EventSink.class);

        CloudEvent event = CloudEventBuilder.v1()
                .withId("evt-empty")
                .withSource(URI.create("https://example.com"))
                .withType("google.cloud.storage.object.v1.finalized")
                .build();

        assertThrows(IllegalArgumentException.class,
                () -> new StorageFinalizedFunction(sink).accept(event));
        verifyNoInteractions(sink);
    }
}
~~~

These tests verify event type filtering, payload forwarding, ID extraction, and error handling. Because the sink is mocked, they do not prove the event actually wrote to Cloud Storage, Firestore, or a database; that requires separate component or integration tests.

**Do not blindly throw errors on every invalid payload in production without a strategy.** With Eventarc, throwing an exception can cause redelivery depending on the retry policy. Distinguish transient retryable failures from permanently malformed payloads that should be logged or routed to dead-letter handling.

## 10. Running a CloudEventsFunction Locally and Sending Fixtures

Start the Cloud Storage function on a separate port:

~~~bash
mvn function:run \
  -Drun.functionTarget=com.example.functions.StorageFinalizedFunction \
  -Drun.port=8081
~~~

CloudEvents supports HTTP binary content mode. In this mode, CloudEvents attributes travel in `ce-*` headers while the request body holds the event data JSON.

Send a Cloud Storage finalized event from another terminal:

~~~bash
curl -i "http://localhost:8081/" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "ce-specversion: 1.0" \
  -H "ce-id: evt-123" \
  -H "ce-type: google.cloud.storage.object.v1.finalized" \
  -H "ce-source: //storage.googleapis.com/projects/_/buckets/test-bucket" \
  -H "ce-subject: objects/a.txt" \
  --data-binary '{"bucket":"test-bucket","name":"a.txt","generation":"1"}'
~~~

Expected result: HTTP 2xx and logs containing `evt-123`. Because `CloudEventsFunction` returns `void`, successful responses typically have an empty body; check the HTTP status code and side effects/log output rather than expecting a response string.

To test missing-header handling, omit `ce-id` or `ce-type`. The framework should reject the malformed CloudEvent at the parsing layer; this is a **framework contract test**, distinct from business logic tests inside `accept()`.

### Pub/Sub CloudEvent with Base64 Data

For Pub/Sub triggers via Eventarc, the CloudEvent type is typically `google.cloud.pubsub.topic.v1.messagePublished`. The `data` payload is a JSON envelope containing `message`, where `message.data` is a Base64-encoded string. Example:

~~~json
{
  "message": {
    "messageId": "10001",
    "data": "SGVsbG8gZnVuY3Rpb24=",
    "attributes": {
      "source": "orders"
    }
  },
  "subscription": "projects/demo-project/subscriptions/orders-sub"
}
~~~

A Pub/Sub handler function must read `event.getData()`, parse the JSON envelope, extract `message.data`, and Base64-decode it; never pass the raw Base64 string straight into business logic as plain text.

Example HTTP fixture for a Pub/Sub handler **when the project has a dedicated `CloudEventsFunction` for this event type**:

~~~bash
curl -i "http://localhost:8081/" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "ce-specversion: 1.0" \
  -H "ce-id: pubsub-123" \
  -H "ce-type: google.cloud.pubsub.topic.v1.messagePublished" \
  -H "ce-source: //pubsub.googleapis.com/projects/demo-project/topics/orders" \
  --data-binary '{"message":{"messageId":"10001","data":"SGVsbG8="}}'
~~~

This fixture is not a valid business input for `StorageFinalizedFunction` because that sample class filters for Cloud Storage event types. When testing Pub/Sub, switch the target to a function implementing the handler for Pub/Sub events.

## 11. Designing Test Doubles for External Services

Functions may call Secret Manager, Cloud Storage, Pub/Sub, Firestore, Cloud SQL, or partner HTTP APIs. Good unit tests verify logic without contacting production.

### 11.1. Adapters and Dependency Injection

Define interfaces expressing business operations, such as `OrderPublisher` or `FileMetadataStore`. The function accepts the interface in a test constructor; the default no-arg constructor can wire the official adapter using ADC.

~~~mermaid
flowchart LR
    H["Function handler"] --> S["Business service"]
    S --> I["Storage / PubSub interface"]
    I --> F["Fake or Mockito<br/>unit/component test"]
    I --> REAL["Google Cloud SDK client<br/>staging/production"]
~~~

This creates a clean seam to swap dependencies in tests. You do not need to deeply mock internal Google Cloud SDK classes if you can fake at the business interface boundary. Unit tests can verify operation names, payloads, idempotency keys, and retry classification.

### 11.2. Emulators and Test Resources

| Dependency | Testing Approach |
|---|---|
| Pub/Sub | Pub/Sub emulator for publish/subscribe/ack; E2E with staging topic/subscription for IAM/Eventarc |
| Firestore | Firestore emulator for partial read/write/query behavior; check differences against live staging |
| Cloud SQL | Database container or Cloud SQL test instance; verify real transactions/migrations |
| Secret Manager | Fake adapter in unit tests; live staging Secret Manager for IAM/secret versions |
| Cloud Storage | Fake SDK adapter for unit tests; staging bucket for signed URLs, IAM, notifications, and lifecycle |
| Partner HTTP service | Stub server testing statuses/headers/timeouts and simulated faults |

Emulators generally do not replicate full IAM, audit logging, regional routing, or quotas. Therefore, supplement unit/component tests with clearly scoped integration tests.

In CI, append random suffixes to test resource names and tear them down in a finally/cleanup step even when tests fail. Never use production buckets/topics for tests.

## 12. Testing Retries, Duplicate Events, and Idempotency

Event-driven systems can deliver the same event multiple times. Eventarc/Pub/Sub triggers typically provide **at-least-once delivery**. A message may be redelivered if the function returns an error, times out, or its acknowledgment is lost. Never assume every event is processed exactly once.

Important scenarios:

1. Same event `source` + `id` delivered twice: business effect executes only once.
2. Two events with different IDs for the same resource: version/generation checks prevent stale data from overwriting newer data.
3. Dependency returns transient 503: retries apply appropriate backoff.
4. Permanently malformed payload: record evidence and avoid infinite retries.
5. Function succeeds but response/ack is lost: redelivery does not produce duplicate side effects.
6. Concurrent invocations: idempotency enforcement is free of race conditions.

**Deduplication key example:** combine CloudEvent `source` and `id`; for Cloud Storage, include `generation` or `metageneration` depending on business requirements.

A resilient design usually records the key via an atomic insert/create-if-absent operation in Firestore/SQL. Checking "key does not exist" and then writing in two non-atomic steps risks race conditions when two instances execute concurrently.

In unit tests, a fake store can simulate an already-seen key; in integration tests, fire two concurrent invocations and assert that only one side effect commits.

## 13. Testing Timeouts, Concurrency, and Memory

Cloud Run functions execute on Cloud Run infrastructure and are bound by configured timeouts, CPU, memory, concurrency, and autoscaling limits. Local Functions Framework does not faithfully enforce these limits.

Scenarios to design for:

| Scenario | What to Verify |
|---|---|
| Slow dependency | Timeout stays within request budget and emits useful logs |
| Dependency failure | Exceptions are classified without leaking secrets |
| Two concurrent invocations | No unsynchronized mutable static variables |
| Cold start | Client and connection initialization stays within bounds |
| Memory pressure | Large files are streamed rather than loaded whole into heap |
| HTTP function spawning background thread | Work completes or is handed off to durable infrastructure before responding |
| Retries triggered by handler error | Side effects are idempotent and retries are bounded by count/duration |

Do not return HTTP 200 and continue async processing on a background thread as a reliable pattern. Cloud Run may throttle CPU or terminate instances once no active request remains; for long-running work, hand off to Cloud Tasks, Pub/Sub, or Cloud Run Jobs/workers.

## 14. Integrating Tests into CI/CD

A clean pipeline can be split into three gates:

| Gate | Contents | When |
|---|---|---|
| Pull request | Maven compile, JUnit/Mockito, static analysis | Every change |
| Build artifact | Functions Framework local smoke, dependency scan, entry point check | After merge or pre-release |
| Staging | Deploy Cloud Run function, invoke authenticated endpoint or emit test Eventarc event, verify output | Before production |

Example Cloud Build step running Maven unit tests:

~~~yaml
steps:
  - name: 'maven:3.9-eclipse-temurin-17'
    entrypoint: 'mvn'
    args: ['-B', '-ntp', 'test']
timeout: '600s'
~~~

This is a **minimal CI example**. To run local integration tests in Cloud Build, start the function server and execute HTTP assertions within the same step/job managing its lifecycle. Do not assume a background process launched in one step remains alive in the next step.

In a real workflow:

1. Run unit/component tests independently of Google Cloud.
2. Start Functions Framework in the CI job and wait for readiness on the local port.
3. Send HTTP/CloudEvents fixtures and verify results.
4. Always stop the local process and capture logs upon completion.
5. Build the artifact, run dependency/vulnerability scans, and capture provenance if required.
6. Deploy to staging, run smoke/E2E checks; promote only verified builds.
7. Touch production credentials/traffic only under an approved release process.

Attach the commit SHA, entry point, test results, and Java/runtime versions to test artifacts so failures can be reproduced.

## 15. Post-Deployment Testing on Cloud Run Staging

### 15.1. Deploying a Tested HTTP Function

Cloud Run supports deploying from source with `--function` specifying the entry point and `--base-image` selecting the Java runtime.

Example:

~~~bash
gcloud run deploy greeting-function-staging \
  --source . \
  --function com.example.functions.GreetingFunction \
  --base-image java21 \
  --region asia-southeast1 \
  --no-allow-unauthenticated
~~~

The JDK used to compile must be compatible with the deployment runtime. When building with Java 17 as in the Maven example, Java 21 can run Java 17 bytecode; validate dependencies against the chosen runtime.

Cloud Run source deployments require appropriate APIs and build/deploy permissions (Cloud Run, Cloud Build, Artifact Registry). Use a dedicated runtime service account scoped to least-privilege IAM.

### 15.2. Invoking an Authenticated Function

Retrieve the service's live URL:

~~~bash
gcloud run services describe greeting-function-staging \
  --region asia-southeast1 \
  --format="value(status.url)"
~~~

Assuming that URL is stored in `SERVICE_URL`:

~~~bash
SERVICE_URL="https://YOUR-STAGING-SERVICE-URL"
curl -i \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$SERVICE_URL/?name=Lan"
~~~

The calling principal must hold the Cloud Run Invoker role on the service. The ID token must also have the matching audience. When an API requires authentication, a 401/403 does not automatically mean function code failed; inspect the token and IAM first.

Never pass `--allow-unauthenticated` simply to work around a permission error in staging or production. If an endpoint genuinely needs public access, implement abuse prevention, input validation, rate limiting, and application-level authentication as appropriate.

### 15.3. Staging for `CloudEventsFunction`

To test live Eventarc delivery, create a staging trigger with the right event type, region, event source, and trigger service account. Then emit a test event to the staging bucket/topic.

Verify end-to-end:

- Does the trigger match the expected event type and filters?
- Does the trigger service account have permission to invoke the Cloud Run service?
- Does the function receive the expected schema and emit valid logs?
- Does the business side effect occur only once even when events are redelivered?
- Do retries, dead-letter/alerting, and downstream service permissions work?

None of these properties can be proved by curling localhost. Local `curl` checks the CloudEvent contract; staging checks Eventarc and live Google Cloud IAM/networking.

## 16. Observability, Reliability, and Testing Cost

When running locally, logs from Functions Framework and the function appear in the terminal. When deployed, Cloud Logging captures request logs and application logs according to Cloud Run configuration. Cloud Monitoring lets you chart requests, latency, error rates, and container resource usage.

Metrics to monitor in staging:

- 2xx/4xx/5xx response ratios by entry point.
- P50/P95/P99 latency and cold starts where relevant.
- Dependency call durations, retries, and timeouts.
- Eventarc redelivery counts and event processing success rates.
- Memory, CPU, and active instance counts.
- Quotas and costs across Cloud Run, Cloud Build, Pub/Sub, Cloud Storage, and backing services.

Correlate logs with request IDs or CloudEvent `source`/`id` for fast lookup. Never log tokens, passwords, secrets, or sensitive payloads directly. When fixtures resemble personal data, substitute synthetic data.

Control testing costs by running thorough unit/local tests before deploying, sizing staging resources appropriately, bounding retries, and cleaning up test buckets/topics/databases when finished. Avoid attaching permanent triggers to production topics solely for smoke tests.

## 17. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `ClassNotFound` or no function found | Wrong package/entry point or missing class in build output | Supply the fully-qualified class name and verify `src/main/java` structure |
| `mvn function:run` goal unrecognized | Missing Maven plugin declaration or dependency/plugin resolution error | Check `pom.xml`, Maven repository, and `function-maven-plugin` |
| Port 8080 already in use | Another service is listening | Pass `-Drun.port=8081` and update test URL |
| HTTP handler runs but test response body is empty | Mock `BufferedWriter` not flushed | Flush in the unit test before reading `StringWriter` |
| HTTP POST returns 405 | Handler only accepts GET | Send GET per contract or implement and test a POST branch |
| CloudEvent returns 400 before entering `accept` | Missing `ce-id`, `ce-source`, `ce-type`, `ce-specversion`, or wrong content type | Check CloudEvents 1.0 binary headers and payload |
| Pub/Sub event message unreadable | Confused `event.data` JSON with Base64 `message.data` | Parse the envelope first, then Base64-decode |
| Event processed multiple times | Eventarc/Pub/Sub at-least-once delivery and retries | Add atomic deduplication keyed by event key |
| Local test PASSES but Cloud Run returns 403 | Caller lacks `run.invoker` or ID token has wrong audience | Verify caller IAM and `Authorization: Bearer` token |
| Local test PASSES but staging fails | Missing service permissions, secrets, VPC route, or Eventarc trigger | Run staging integration tests and check audit logs |
| Unit tests depend on Internet/production | Code instantiates live SDK clients in constructor | Abstract dependencies behind interfaces and use fakes/mocks in unit tests |
| Flaky time-dependent tests | Fixed sleeps, timezone drift, or uncontrolled external state | Inject `Clock`, use deterministic fixtures, and poll with bounded timeouts |
| Request timeout | Slow downstream dependency or function takes too long | Set downstream timeouts and offload long tasks to queues/jobs |
| Tests consume excessive resources | Uncleaned triggers/topics/buckets or infinite retries | Clean up resources, cap staging scale, and configure cost alerts |

## 18. Pre-Release Checklist

- [ ] Entry point is the fully-qualified Java class name implementing the proper HTTP or CloudEvents interface.
- [ ] Functions Framework dependencies and Maven plugin are declared with controlled versions.
- [ ] Unit tests cover happy paths, missing inputs, invalid inputs, and dependency failures.
- [ ] No production services are called during unit tests.
- [ ] Functions Framework starts on localhost and handles real HTTP requests.
- [ ] HTTP tests assert status codes, headers, body, and timeouts.
- [ ] CloudEvent fixtures have valid `type`, `id`, `source`, `specversion`, and `data`.
- [ ] Pub/Sub `message.data` is Base64-decoded where required.
- [ ] Event handlers implement explicit idempotency and retry strategies.
- [ ] CI runs Maven tests and local smoke tests prior to deployment.
- [ ] Staging verifies Cloud Run Invoker, Eventarc triggers, and live runtime permissions.
- [ ] Logs/metrics track errors, latency, and event processing.
- [ ] Secrets are never logged and sensitive production data is never used in fixtures.
- [ ] Rollback procedures and test resource cleanup are in place.
- [ ] Runtime version, timeout, concurrency, and region settings are verified.

## 19. Self-Check Questions

**1. What does Functions Framework help you test on a local machine?**

It provides an HTTP server and dispatcher for Java `HttpFunction` or `CloudEventsFunction` implementations so you can test entry points, request/response handling, and CloudEvents contracts without deploying on every change.

**2. Why don't unit tests need to run `mvn function:run`?**

Unit tests invoke `service()` or `accept()` directly using mocked/faked inputs and dependencies. The local invoker is mainly for integration tests to confirm the framework receives HTTP requests and dispatches the class properly.

**3. In Java, is the function target a method name or a class name?**

It is the fully-qualified class name including package, e.g., `com.example.functions.GreetingFunction`. Java Functions Framework infers the signature from the implemented interface.

**4. How do HTTP function and CloudEvent function inputs differ?**

An HTTP function receives `HttpRequest` and `HttpResponse`. A CloudEvent function receives a `CloudEvent` carrying `id`, `source`, `type`, and `data`, parsed by the framework from the HTTP CloudEvents envelope.

**5. Why does a Pub/Sub fixture contain Base64?**

In a Pub/Sub CloudEvent, `message.data` is Base64-encoded inside the JSON envelope. The function must parse the envelope and decode that payload.

**6. Why must event-driven functions handle duplicate deliveries?**

Eventarc/Pub/Sub can redeliver the same event on retries or lost acknowledgments. Side effects must be idempotent, typically enforced via an atomic record keyed by `source`/`id`.

**7. Does a passing local test guarantee Eventarc triggers the function in production?**

No. Local tests do not verify triggers, IAM, VPCs, secrets, or live service accounts. Those properties require staging integration/E2E tests.

## 20. References

- [Google Cloud: Write Cloud Run functions](https://cloud.google.com/run/docs/write-functions)
- [Google Cloud: Develop functions locally](https://cloud.google.com/run/docs/local-dev-functions)
- [Google Cloud: Java dependencies for Cloud Run functions](https://cloud.google.com/run/docs/runtimes/java-dependencies)
- [Google Cloud: Deploy a Cloud Run function](https://cloud.google.com/run/docs/deploy-functions)
- [Google Cloud: Function triggers](https://cloud.google.com/run/docs/function-triggers)
- [Functions Framework for Java: GitHub](https://github.com/GoogleCloudPlatform/functions-framework-java)
- [Google Cloud Java sample: HTTP method types](https://cloud.google.com/functions/docs/samples/functions-http-method)
- [Google Cloud Java sample: Cloud Storage CloudEvent unit test](https://cloud.google.com/functions/docs/samples/functions-cloudevent-storage-unit-test)
- [Google Cloud Java sample: Pub/Sub CloudEvent unit test](https://cloud.google.com/functions/docs/samples/functions-cloudevent-pubsub-unit-test)
- [Google Cloud: Eventarc triggers for Cloud Run functions](https://cloud.google.com/run/docs/tutorials/pubsub-eventdriven)
- [CloudEvents specification](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md)
- [CloudEvents Java SDK](https://github.com/cloudevents/sdk-java)
