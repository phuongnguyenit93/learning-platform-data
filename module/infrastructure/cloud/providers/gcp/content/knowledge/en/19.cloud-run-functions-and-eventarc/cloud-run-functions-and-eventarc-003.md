# HTTP functions and event-driven functions in Cloud Run

A Java service may require two very different processing patterns: responding immediately when a partner calls an order-confirmation webhook, and automatically processing a newly uploaded file in Cloud Storage. The first pattern fits an **HTTP function**; the second fits an **event-driven function** triggered via **Eventarc**.

Both can be written with **Functions Framework for Java** and deployed as a **Cloud Run service**. The main differences lie in **who triggers execution**, **input format**, **how results are acknowledged**, and **error/duplication handling strategies**. This lesson belongs to the **Cloud Run functions and Eventarc** chapter in the `CLOUD_PROVIDERS_GCP` module, connecting application development with IAM, VPC, Cloud Run, Cloud Storage, Pub/Sub, CI/CD, reliability, and cost.

**Scope:** current Cloud Run functions, created and managed via **Cloud Run Admin API / `gcloud run`**, Java 21, Eventarc Standard. The `gcloud functions deploy` syntax under the **Cloud Functions v2 API** path remains supported for compatibility but is not the primary deployment path in these examples. Do not confuse with **Cloud Run functions (1st gen)** or **Cloud Run jobs**.

## Learning objectives

After this lesson, you will be able to:

1. Choose between HTTP and CloudEvents based on request or event characteristics.
2. Explain the relationship between Functions Framework, Cloud Build, Artifact Registry, Cloud Run, and Eventarc.
3. Write two Java classes: `HttpFunction` and `CloudEventsFunction`.
4. Deploy functions from source using `gcloud run deploy --function`, and inspect the service and logs.
5. Create an Eventarc trigger filtering Cloud Storage `object.v1.finalized` events and routing them to a private function.
6. Separate IAM permissions for the deployer, runtime service account, Eventarc trigger, and event source.
7. Handle **at-least-once delivery**, duplicate events, lack of ordering guarantees, and retries.
8. Design idempotency, concurrency/timeout limits, and monitoring prior to production.
9. Practice positive/negative testing and build a troubleshooting runbook.

## 1. How do HTTP functions and event-driven functions differ?

| Criterion | HTTP function | Event-driven / CloudEvents function |
| --- | --- | --- |
| Trigger source | HTTP(S) client, webhook, another service | Cloud Storage, Pub/Sub, Firestore, or another Eventarc-supported event source |
| Java interface | `HttpFunction` | `CloudEventsFunction` |
| Input | `HttpRequest`: method, path, headers, body | `CloudEvent`: id, type, source, time, data |
| Output | `HttpResponse`, status/body/headers | Finish processing or report an error so the delivery system decides on retry |
| Current deployment path | Deploy a Cloud Run function receiving HTTP | Deploy a Cloud Run function, **then** create an Eventarc trigger |
| Authentication | Cloud Run IAM; for public webhooks add source verification | Eventarc trigger service account invokes the Cloud Run service via IAM Invoker |
| Invocation characteristics | Synchronous with caller; client decides retries | Typically asynchronous; **may be redelivered** if retries are enabled |
| Best suited for | Lightweight APIs, webhooks, health/action endpoints | Processing new objects, reacting to infrastructure events, event pipelines |

**Every Cloud Run function is deployed as a Cloud Run service with an HTTP endpoint.** "Event-driven" means **Eventarc delivers a CloudEvent to that endpoint** over HTTP, not that the runtime avoids HTTP. Do not use `HttpFunction` to manually parse a CloudEvent body once you have chosen the CloudEvents signature unless there is a clear reason.

### 1.1. Do not confuse "event-driven" with unbounded background processing

A function should complete a unit of work within the **request processing duration** and return a result. Do not spawn a background thread and immediately return `2xx`, because the work may be terminated while Eventarc already considers the event acknowledged. For long-running jobs or large fan-outs, consider **Cloud Run jobs, Cloud Tasks, Pub/Sub, or Workflows** as appropriate.

## 2. Architecture from source to execution

~~~mermaid
flowchart LR
    SRC["Java source + pom.xml"] --> CB["Cloud Build + buildpacks"]
    CB --> AR["Artifact Registry"]
    AR --> RUN["Cloud Run function service"]
    HTTP["HTTP client / webhook"] -->|"HTTPS + auth"| RUN
    GCS["Cloud Storage"] --> EV["Eventarc trigger<br/>filter + identity"]
    EV -->|"HTTP CloudEvent"| RUN
    RUN --> DATA["Cloud SQL / Storage / Pub/Sub"]
~~~

When you run `gcloud run deploy --source --function`, Google Cloud coordinates **Cloud Build** to package the source with buildpacks, stores the image in **Artifact Registry**, and creates a Cloud Run service revision. Eventarc handles **event routing**, not the container runtime. In the Console, a trigger can be added during function creation; with the CLI, the documentation recommends **deploying the function first, then creating the trigger**.

Cloud Run features such as CPU/memory configuration, environment variables, secrets, networking, IAM, concurrency, and traffic revisions remain relevant. The Cloud Functions v2 API path has some different limits/rules compared to services created directly via the Cloud Run Admin API, so do not copy timeout/trigger configurations between the two paths without checking.

## 3. Functions Framework and entry points in Java

A single Maven project can contain **multiple handler classes**, while each deploy command specifies one **entry point** to run:

~~~text
functions-lab/
├── pom.xml
└── src/main/java/functions/
    ├── HelloHttp.java
    └── StorageFinalized.java
~~~

- `functions.HelloHttp` implements `HttpFunction` with the `service(...)` method.
- `functions.StorageFinalized` implements `CloudEventsFunction` with the `accept(...)` method.
- `--function=functions.HelloHttp` or `--function=functions.StorageFinalized` selects the class by its **fully qualified class name with package**, not the Cloud Run service name.

Minimal `pom.xml` example for Java 21:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example.gcp</groupId>
  <artifactId>functions-lab</artifactId>
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
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloudevent-types</artifactId>
      <version>0.14.0</version>
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
        <groupId>com.google.cloud.functions</groupId>
        <artifactId>function-maven-plugin</artifactId>
        <version>0.11.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The versions above serve as a **reproducible example**; before going to production, update dependencies/plugins to supported versions per your project's security policy. The build must use a compatible Java 21 toolchain. `functions-framework-api` is provided by the runtime and therefore has `provided` scope.

## 4. Writing an HTTP function in Java

File `src/main/java/functions/HelloHttp.java`:

~~~java
package functions;

import com.google.cloud.functions.HttpFunction;
import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;
import java.io.IOException;

public class HelloHttp implements HttpFunction {
    @Override
    public void service(HttpRequest request, HttpResponse response)
            throws IOException {
        if (!"GET".equals(request.getMethod())) {
            response.setStatusCode(405);
            response.appendHeader("Allow", "GET");
            response.getWriter().write("Method not allowed");
            return;
        }

        response.setStatusCode(200);
        response.appendHeader("Content-Type", "application/json; charset=utf-8");
        response.getWriter().write("{\"status\":\"ok\",\"handler\":\"http\"}");
    }
}
~~~

This handler demonstrates **request/response** handling and HTTP status codes. It has no database dependency, making it suitable for smoke tests. For a real webhook, verify **signature, timestamp, replay protection, request body size, content type, and business authorization** before writing data. Cloud Run IAM controls **who can invoke the endpoint**, while webhook signatures verify the partner message authenticity when the endpoint is configured to accept external traffic.

An HTTP function may receive sequential or parallel requests based on Cloud Run **concurrency**; **do not store business state in static variables or on local disk** expecting all invocations to see the same data.

## 5. Writing an event-driven function for Cloud Storage CloudEvents

File `src/main/java/functions/StorageFinalized.java`:

~~~java
package functions;

import com.google.cloud.functions.CloudEventsFunction;
import com.google.events.cloud.storage.v1.StorageObjectData;
import com.google.protobuf.util.JsonFormat;
import io.cloudevents.CloudEvent;
import java.nio.charset.StandardCharsets;
import java.util.logging.Logger;

public class StorageFinalized implements CloudEventsFunction {
    private static final Logger LOG =
            Logger.getLogger(StorageFinalized.class.getName());

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!"google.cloud.storage.object.v1.finalized".equals(event.getType())) {
            throw new IllegalArgumentException("Unexpected event type");
        }
        if (event.getData() == null) {
            throw new IllegalArgumentException("Missing CloudEvent data");
        }

        String json = new String(
                event.getData().toBytes(), StandardCharsets.UTF_8);
        StorageObjectData.Builder builder = StorageObjectData.newBuilder();
        JsonFormat.parser().ignoringUnknownFields().merge(json, builder);
        StorageObjectData object = builder.build();

        // Demo: log metadata; do not log object contents or secrets.
        LOG.info("eventId=" + event.getId()
                + " source=" + event.getSource()
                + " bucket=" + object.getBucket()
                + " generation=" + object.getGeneration());

        // Production: process idempotently and mark completion in the DB.
    }
}
~~~

Standard fields in a CloudEvent:

| Field | Meaning |
| --- | --- |
| `id` | Event ID within the scope of the source |
| `source` | Source that emitted the event |
| `type` | Event type, e.g., `google.cloud.storage.object.v1.finalized` |
| `time` | Timestamp when the event was recorded, when provided |
| `subject` | Specific subject described by the event, if present |
| `data` | Event-type-specific payload; in this example, object metadata |

An illustrative **CloudEvent data example**:

~~~json
{
  "specversion": "1.0",
  "id": "event-123",
  "source": "//storage.googleapis.com/projects/_/buckets/commerce-uploads",
  "type": "google.cloud.storage.object.v1.finalized",
  "subject": "objects/incoming/order-A100.json",
  "data": {
    "bucket": "commerce-uploads",
    "name": "incoming/order-A100.json",
    "generation": "1735000000000123"
  }
}
~~~

**Do not treat the JSON above as the only required HTTP wire format.** Eventarc may send CloudEvents in HTTP binary content mode: attributes sit in `ce-*` headers and the payload sits in the body; Functions Framework decodes this into a `CloudEvent` for Java. You do not need to parse headers manually when using the interface above.

**Important:** `object.v1.finalized` fires whenever a **new generation** is created, including **initial uploads and overwrites**. If you process files solely by name, an overwrite may cause the handler to read newer content by mistake; you must account for `bucket + name + generation` and use the API to read a specific generation.

## 6. Preparing the project, APIs, and IAM

The commands in this lesson are **lab-project examples** that may create billable resources. Deploy only if permitted by your organization. Replace `PROJECT_ID`, `BUCKET_NAME`, and service accounts with real values; avoid using customer data during experiments.

~~~bash
gcloud auth list
gcloud config get-value project

# If APIs are already enabled, there is no need to re-enable them.
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com eventarc.googleapis.com \
  pubsub.googleapis.com storage.googleapis.com \
  --project=PROJECT_ID
~~~

You need Cloud Billing, quota, and Cloud Run source deployment permissions (typically **Cloud Run Source Developer**, **Service Usage Consumer**, and **actAs** permission on the runtime service account). The build identity needs Cloud Build/Artifact Registry permissions; the runtime identity only needs permissions for business APIs.

**Separate three identities:**

1. **Deployer/build identity:** compiles, pushes, and creates revisions.
2. **Runtime service account:** used by Java code to access Cloud Storage, Cloud SQL, Pub/Sub, or Secret Manager.
3. **Eventarc trigger service account:** the identity that **invokes the Cloud Run service** when an event fires, not the identity processing business logic in Java.

Do not grant broad Editor/Owner roles as a quick fix for `403` errors. For a private service, the Eventarc trigger identity needs **`roles/run.invoker`** on the service, and for direct events like Cloud Storage it needs **`roles/eventarc.eventReceiver`** at the appropriate scope. The **Cloud Storage service agent** may need **`roles/pubsub.publisher`** so Eventarc can receive source notifications.

## 7. Deploying the HTTP function from source

From the directory containing `pom.xml` and source:

~~~bash
gcloud run deploy orders-http-lab \
  --source=. \
  --function=functions.HelloHttp \
  --base-image=java21 \
  --region=asia-southeast1 \
  --no-allow-unauthenticated \
  --project=PROJECT_ID
~~~

This deployment path uses the **Cloud Run Admin API**. `--no-allow-unauthenticated` requires authentication, avoiding exposing a demo endpoint publicly. If a build fails, check Maven source layout, compile target, plugin dependencies, build logs, build identity permissions, and Artifact Registry.

Inspect the service:

~~~bash
gcloud run services describe orders-http-lab \
  --region=asia-southeast1 \
  --project=PROJECT_ID

gcloud run services logs read orders-http-lab \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --limit=20
~~~

### 7.1. Testing the private HTTP service

To avoid putting ID tokens in shell history, use the **Cloud Run local proxy** (the CLI identity must have permission to invoke the service):

~~~bash
# First terminal: keep the proxy process running
gcloud run services proxy orders-http-lab \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --port=8080

# Second terminal:
curl -i http://127.0.0.1:8080/
curl -i -X POST http://127.0.0.1:8080/
~~~

Expected behavior: `GET` returns `200` with JSON; `POST` returns `405 Method Not Allowed`. This is **demo application behavior**, not a complete authentication/authorization system.

For a public production webhook, `--allow-unauthenticated` should only be used after verifying that public ingress is genuinely required, with source signature verification and abuse protection in place; API Gateway or service-to-service IAM may be a better fit.

## 8. Deploying the CloudEvents function and creating an Eventarc trigger

### 8.1. Deploying the event-receiving service

~~~bash
gcloud run deploy orders-storage-events \
  --source=. \
  --function=functions.StorageFinalized \
  --base-image=java21 \
  --region=asia-southeast1 \
  --no-allow-unauthenticated \
  --project=PROJECT_ID
~~~

An event handler is still deployed as a **Cloud Run service**. Without a trigger, **uploading a file to the bucket will not automatically invoke the handler**. In the Cloud Run Admin API flow, create the Eventarc trigger after deployment.

### 8.2. Preparing the event source and trigger identity

Assume **bucket `BUCKET_NAME` already exists** in a project/region that supports Eventarc direct Cloud Storage events; in a lab, choose a **regional bucket in `asia-southeast1`** to match the trigger location. Never create or delete production buckets casually.

~~~bash
# Read-only check of bucket location and project:
gcloud storage buckets describe gs://BUCKET_NAME \
  --project=PROJECT_ID

# Dedicated identity for Eventarc; avoid overly broad default SAs:
gcloud iam service-accounts create eventarc-delivery-lab \
  --project=PROJECT_ID
~~~

Grant permissions as approved by your organization, for example:

~~~bash
# Trigger SA has permission to receive direct events (Cloud Storage).
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:eventarc-delivery-lab@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/eventarc.eventReceiver"

# Trigger SA has permission to invoke the private Cloud Run service.
gcloud run services add-iam-policy-binding orders-storage-events \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --member="serviceAccount:eventarc-delivery-lab@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

For direct events from Cloud Storage, the Cloud Storage **service agent** typically requires **Pub/Sub Publisher** permission. Retrieve the service agent email via `gcloud storage service-agent --project=PROJECT_ID`, and have an administrator grant `roles/pubsub.publisher` at the appropriate scope; do not grant this permission to the **runtime service account** instead of the service agent. If the project is already configured, do not add duplicate bindings.

### 8.3. Creating a trigger filtering object finalized events

~~~bash
gcloud eventarc triggers create orders-file-finalized \
  --location=asia-southeast1 \
  --destination-run-service=orders-storage-events \
  --destination-run-region=asia-southeast1 \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=BUCKET_NAME" \
  --service-account=eventarc-delivery-lab@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID
~~~

- `type` filters for events when an object is created/overwritten as a new generation.
- `bucket` selects the specific bucket; the filter must use the **bucket name**, not a `gs://` URL.
- `--location` is the trigger location; for direct Cloud Storage events, it must be compatible with the **bucket location**. The destination service may reside in another region within supported limits, though keeping it close to the source is preferable when appropriate.
- `--service-account` specifies the identity used to deliver events; Eventarc **does not borrow the deployer's IAM permissions** at runtime.
- A trigger may take **a few minutes to become active** after creation; do not conclude it is broken simply because an immediate upload shows no invocation yet.

Verification:

~~~bash
gcloud eventarc triggers describe orders-file-finalized \
  --location=asia-southeast1 \
  --project=PROJECT_ID

gcloud eventarc triggers list \
  --location=asia-southeast1 \
  --project=PROJECT_ID
~~~

### 8.4. Triggering an event and viewing logs

~~~bash
# Use a harmless text file created on the lab machine:
printf 'hello from lab\n' > sample-event.txt

gcloud storage cp sample-event.txt \
  gs://BUCKET_NAME/incoming/sample-event.txt

gcloud run services logs read orders-storage-events \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --limit=50
~~~

The demo handler logs `eventId`, `source`, `bucket`, and `generation`. To re-trigger an event, re-uploading creates a **new generation**, not necessarily the same event ID. Read logs after the trigger is healthy and allow for event delivery latency.

## 9. Eventarc Standard: at-least-once delivery and event ordering

**An event may be delivered multiple times** when retries are enabled. Eventarc Standard does not guarantee FIFO; events from the same object can also arrive **out of order** relative to creation order.

~~~mermaid
sequenceDiagram
    participant G as Cloud Storage
    participant E as Eventarc / PubSub transport
    participant F as Cloud Run function
    participant D as Dedupe store
    G->>E: Event E1 (generation 100)
    E->>F: Deliver E1
    F->>D: Save idempotent result
    Note over E,F: Response lost or handler failed
    E->>F: Redeliver E1
    F->>D: See E1 already processed
    F-->>E: 2xx, no duplicate side effects
~~~

### 9.1. Choosing an idempotency key

Under CloudEvents, the **`source + id`** pair distinguishes a specific event. For Cloud Storage finalized events, you can also use **`bucket + objectName + generation`** to identify a specific object version to process.

Example:

~~~text
idempotencyKey = event.source + "|" + event.id

Or for per-generation workloads:
workKey = bucket + "/" + objectName + "#" + generation
~~~

Store the key in **Cloud SQL (unique constraint), a Firestore transaction**, or create an output object with an immutable name using a **Cloud Storage generation precondition**. Static memory, instance caches, or temporary local filesystems are unsuitable for system-wide deduplication because Cloud Run scales across multiple instances.

**Do not merely log the ID and assume idempotency.** Before sending emails, charging payments, writing outputs, or publishing Pub/Sub messages, ensure side effects cannot be duplicated. When an operation spans multiple systems, use transactional/outbox patterns and matching idempotency keys.

### 9.2. When events arrive out of order

If `orders/state.json` is overwritten to generation G2 and then G3, a handler for G2 may execute after G3's handler. Do not rely on **event arrival time** or compare generation numbers as a global business clock.

Depending on requirements:

- **Process every generation:** read content using the **specified generation** and store separate outputs; note that older generations may no longer be available without appropriate versioning/soft delete.
- **Process only the latest live version:** read current object metadata and verify it is still the expected version before committing; design to avoid overwriting results from newer events.
- **Need transactions and business ordering:** use an appropriate database/event store; Eventarc alone does not guarantee ordered processing.

## 10. Retries, success acknowledgments, and permanent errors

In Eventarc Standard, retries typically rely on the Pub/Sub transport. **Do not assume every trigger automatically retries**:

- Triggers created via **gcloud CLI/Terraform** generally enable retries by default.
- Triggers created from the **Cloud Run Console** may default to **single-attempt delivery with no retries** unless retries are explicitly enabled.
- Retention, backoff, and dead-letter handling are configured on the **Pub/Sub subscription** attached to the trigger where supported.
- Once a `2xx` response is accepted, the delivery system considers the event processed; if actual work is still running in the background, data may be lost when the instance terminates.

| Scenario | Handler action |
| --- | --- |
| Event already processed (duplicate) | Skip side effects, return success |
| Transient network/Cloud SQL error | Return error so the delivery system retries if enabled |
| Missing or invalid payload | Safely log metadata, route to error handling/DLQ per policy; do not retry indefinitely |
| Missing IAM permissions | Fix IAM/identity first; infinite retries will not fix missing permissions |
| Downstream overloaded | Backoff/rate limiting, instance/concurrency limits |
| Committed but response lost | Durable dedupe store detects redelivery |

**Retry limits:** prolonged retries can incur Cloud Run, Eventarc, and Pub/Sub charges; events may also expire past retention and be lost. For production, configure a **dead-letter topic/queue** when appropriate and set up alerts so failed events are not silently dropped.

## 11. Security: HTTP callers vs. Eventarc triggers

A common mistake is opening a function to `allUsers` just so Eventarc can invoke it. This is unnecessary if the **trigger service account holds `roles/run.invoker`** and the ingress policy allows Eventarc to reach the service.

~~~mermaid
flowchart TD
    DEP["Deployer"] -->|"Source deployment with proper roles"| RUN["Cloud Run service"]
    EVT["Eventarc trigger SA"] -->|"run.invoker"| RUN
    RUN -->|"Runtime SA app roles"| STORAGE["Storage / DB / PubSub"]
    SRC["Cloud Storage service agent"] -->|"pubsub.publisher when needed"| TRANS["Eventarc transport"]
    TRANS --> EVT
~~~

Key distinctions:

- **Private HTTP function:** clients must have IAM Invoker and a valid identity token. Public webhooks additionally require source signature checks and replay protection.
- **Event-driven function:** keep private; grant Invoker permission specifically to the Eventarc trigger identity.
- **Runtime service account:** holds permissions to read objects or write results, but **should not be reused as the Eventarc trigger SA** merely for convenience.
- **Event source and transport service agents:** have distinct technical roles; do not mix them with application identities.
- **IAM policies/VPC Service Controls/ingress restrictions:** can block event delivery even when Java code is completely correct.

Never log authorization headers, access tokens, object payloads containing PII, payment details, or secrets when debugging.

## 12. Event filtering, fan-out, and avoiding loops

Eventarc triggers filter by **event type** and source-supported attributes (such as bucket). Filters do not replace business validation inside the handler.

**Patterns to watch out for:**

1. Creating multiple triggers with identical filters pointing to different services creates **fan-out**; each destination can receive the same event.
2. A single function attaches one trigger under the specific "function trigger" model, whereas a Cloud Run service can receive events from multiple Eventarc triggers as configurable.
3. If a handler reads `incoming/file.txt` and writes `incoming/processed.txt` back to the same bucket where a trigger listens to all finalized events, **the output can re-trigger the same function**, creating an infinite loop.
4. Use a **separate output bucket** or handle prefixes and metadata in code; do not assume Eventarc direct events support arbitrary object-path filtering.
5. Overwrites also emit finalized events. If you want once-per-object-name processing, enforce clear deduplication/versioning rules.

Safe design example:

~~~text
Input:   gs://commerce-incoming/orders/order-123.json
Trigger: google.cloud.storage.object.v1.finalized (bucket commerce-incoming)
Handler: read exact generation, validate, process idempotently
Output:  gs://commerce-processed/orders/order-123.json
~~~

If the target is Pub/Sub, manage retries, ordering, delivery attempts, and subscription lifecycles per Pub/Sub guidance. Do not use a Cloud Run function as a makeshift message broker.

## 13. Concurrency, timeouts, and Java cold starts

Functions deployed directly on Cloud Run use **Cloud Run autoscaling infrastructure**, capable of handling multiple concurrent requests per instance according to configured concurrency. The Cloud Functions v2 API path and 1st gen have different limits; do not assume every function handles only **one event per instance**.

**For Java:**

- Both HTTP handlers and CloudEvent handlers may execute across multiple threads or multiple instances: shared client objects must be thread-safe.
- Cloud SQL/HTTP connection pools need limits; `max-instances` bounds instance count under conditions, not as a substitute for rate limiting at the event source.
- Cold starts depend on JVM startup, dependency initialization, CPU/memory, min instances, and concurrent load.
- Request timeout differs from total event retention/retry duration; do not spawn long-lived threads after returning success.
- Use Cloud Run jobs/Workflows/Cloud Tasks when processing exceeds a short request, has multi-step workflows, or requires independent deadlines.

Sample command to cap resources **after sizing via load testing**:

~~~bash
gcloud run services update orders-storage-events \
  --concurrency=10 \
  --max-instances=5 \
  --timeout=120s \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

This **modifies real runtime configuration**, which may create a new revision or affect event ingestion capacity. The numbers 10/5/120 are illustrative only, not universal defaults for every Java function. Setting limits too low when events arrive rapidly can increase backlog and latency.

## 14. Testing properly: happy path, failure path, and duplicates

### 14.1. HTTP tests

| Case | Expected outcome |
| --- | --- |
| `GET` to private service with valid caller | `200` and demo JSON |
| `POST` with valid caller | `405` from handler |
| Missing Invoker identity | Blocked by Cloud Run before reaching handler |
| Oversized or invalid JSON body (in a real API) | Appropriate `4xx` and no side effects |

### 14.2. Event tests

| Case | Expected outcome |
| --- | --- |
| Upload new file to filtered bucket | Finalized CloudEvent delivered to handler |
| Overwrite file with same name | Finalized event emitted with **new generation** |
| Upload to a different bucket | Does not match trigger bucket filter |
| Redelivery of same `source + id` | Idempotent handling, no duplicate output |
| Transient processing error with retries enabled | Redelivery occurs per backoff/retention |
| Handler writes output to same source bucket | Risk of self-triggering unless controlled |
| Trigger missing Invoker/Event Receiver | Delivery fails; inspect IAM and delivery logs |

**Intentional redelivery testing:** in a lab environment, configure the handler to intentionally fail temporarily for **one isolated test event**, observe retries, and verify that upon recovery no duplicate output is created. Never induce failure loops on production data sources or without cost guardrails.

### 14.3. Cleaning up lab resources

Only after confirming **no other system depends on them**:

~~~bash
gcloud eventarc triggers delete orders-file-finalized \
  --location=asia-southeast1 \
  --project=PROJECT_ID

gcloud run services delete orders-storage-events \
  --region=asia-southeast1 \
  --project=PROJECT_ID

gcloud run services delete orders-http-lab \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

These are **destructive deletion commands**. Separately inspect **test buckets/files, Artifact Registry images, build artifacts, logs, IAM bindings, and service accounts** per cleanup procedure. Avoid deleting shared buckets or identities used by other applications.

## 15. Observability and troubleshooting

### 15.1. Signals to monitor

| Signal | What it tells you |
| --- | --- |
| Cloud Run requests, p95 latency, 4xx/5xx | Whether the handler is failing or timing out |
| Instance count, CPU/memory/concurrency | Whether autoscaling and resource sizing are appropriate |
| Eventarc trigger health/delivery metrics | Whether events are being routed to the service |
| Pub/Sub transport backlog/retry/dead-letter | Whether events are stuck or retrying excessively |
| Event ID/source, object generation | Whether duplicates or out-of-order deliveries occur |
| Cloud Build/Registry/Run/Eventarc/PubSub costs | Whether retries/cold starts/logs are exceeding budget |

In Logs Explorer:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-storage-events"
severity>=ERROR
~~~

Or via CLI:

~~~bash
gcloud run services logs read orders-storage-events \
  --region=asia-southeast1 --project=PROJECT_ID --limit=50

gcloud eventarc triggers describe orders-file-finalized \
  --location=asia-southeast1 --project=PROJECT_ID
~~~

**Do not look only at function logs.** If Eventarc fails to deliver the request due to IAM or an incorrect trigger filter, the handler will have **no logs at all**; inspect trigger status, service agent permissions, and Pub/Sub transport.

### 15.2. Common errors table

| Symptom | Likely causes to check |
| --- | --- |
| Java build fails with `Class not found` | Incorrect `--function` package/class, Maven compiler/plugin |
| Deploy returns `403` | Source deploy roles, build SA, Artifact Registry permissions, actAs |
| HTTP `401/403` | Private service, caller lacks Invoker, invalid identity token/audience |
| GCS upload does not trigger | Missing trigger, wrong location/filter, or trigger not yet active |
| Eventarc `PERMISSION_DENIED` | Trigger SA lacks Receiver/Invoker, service agents lack permissions |
| Function logs show duplicates | At-least-once redelivery or multiple events for multiple generations |
| Infinite event processing loop | Function writes output back into the same source bucket |
| No second event arrives | Trigger filter mismatch, quota, IAM, or source did not emit an event |
| High latency during bursts | Cold starts, low max instances, slow downstream, or retry backlog |
| HTTP 500 with repeated retries | Handler throws exception, dependency failure, retry policy active |
| Event processes wrong file version | Reading object by name after overwrite instead of pinning generation |
| Cost rises despite low traffic | Retry loops, min instances, excessive logs, or build/Artifact Registry storage |

## 16. Cost and reliability

There is no "free function" for arbitrary traffic. Factors to review: **Cloud Build and Artifact Registry** for source deployments, **Cloud Run** compute/requests, **Eventarc and Pub/Sub transport**, Cloud Storage operations, network egress, Logging/Monitoring, and dependencies like Cloud SQL.

**Practical trade-offs:**

- Low-traffic HTTP webhook → prefer a private endpoint or signature verification if public; check whether cold starts are acceptable.
- High event volume with zero data-loss tolerance → enable retries/idempotency, backlog metrics, and dead-letter queues where appropriate; budget for retry costs.
- Multi-step or long-running ETL → consider Cloud Run jobs or Workflows instead of long request handlers.
- High RTO/RPO targets → add backups, replay strategies, data versioning, and disaster recovery tests; Eventarc does not retain business data indefinitely.

## 17. End-to-end scenario: order file processing

Company Commerce has two components:

1. A partner calls webhook `POST /orders/confirm` → an HTTP function verifies the signature and event ID, then calls the backend to update status.
2. Operations uploads `incoming/orders-2026-11.json` to Cloud Storage → Eventarc `finalized` invokes a CloudEvents function to validate the file and write results to a **different bucket**.

Suggested design:

~~~mermaid
flowchart LR
    PARTNER["Partner"] -->|"HTTPS webhook"| HTTP["HTTP function<br/>signature + validation"]
    HTTP --> DB[("Cloud SQL<br/>idempotency + order state")]
    INPUT["Input bucket"] -->|"finalized event"| ARC["Eventarc"]
    ARC --> CE["CloudEvents function<br/>generation + dedupe"]
    CE --> DB
    CE --> OUTPUT["Output bucket"]
    DB --> OBS["Cloud Monitoring / Logging"]
    CE --> OBS
    HTTP --> OBS
~~~

**Production constraints:** the HTTP webhook must verify partner identity; the CloudEvent may be redelivered or arrive out of order; both must be **idempotent** and must never execute payments or send emails twice. Separate source and output buckets prevent self-triggering loops. All database/storage access belongs to least-privilege **runtime service accounts**.

## 18. Self-check exercises

**Question 1.** Does a Cloud Run event-driven function run "without HTTP"?

*Answer:* No. Eventarc delivers CloudEvents over HTTP to the Cloud Run service; Functions Framework processes the payload according to the CloudEvents signature.

**Question 2.** In Java, do HTTP and CloudEvents functions use the same interface?

*Answer:* No. `HttpFunction.service` differs from `CloudEventsFunction.accept`.

**Question 3.** You deploy `functions.StorageFinalized` with `gcloud run deploy` without creating a trigger. Does uploading to GCS invoke the function?

*Answer:* Not automatically; you must create an Eventarc trigger with the matching filter, source, and destination.

**Question 4.** If you select only event type `google.cloud.storage.object.v1.finalized`, does an overwrite emit an event?

*Answer:* Yes. Overwriting creates a new generation, which emits a new finalized event.

**Question 5.** An event is delivered twice and the handler sends two emails. What is the issue and how do you fix it?

*Answer:* Missing idempotency. Use `source+id` or a business key and persist a durable dedupe record before executing side effects.

**Question 6.** Why shouldn't `generation` be used as a global event-ordering clock across the system?

*Answer:* Ordered delivery is not guaranteed; generation only identifies an object version and cannot replace cross-object business ordering logic.

**Question 7.** An Eventarc trigger was created, yet the private service returns `403`. What should you check?

*Answer:* Check that the trigger SA has `roles/run.invoker`, Event Receiver, source service agent permissions, and ingress/IAM settings.

**Question 8.** Do triggers created in the Cloud Run Console always auto-retry the same way as CLI-created triggers?

*Answer:* No. Default retry settings can differ by UI/creation method; always verify the actual policy.

**Question 9.** Why shouldn't you process work on a background thread and return HTTP 200 immediately?

*Answer:* The delivery system considers the event acknowledged even though the background work may be terminated or lose data.

**Question 10.** What risk arises if a function writes output to the same bucket that has a `finalized` trigger?

*Answer:* The output emits another event, risking infinite loops and unexpected costs if unfiltered.

**Question 11.** A CloudEvents handler uses a runtime SA with bucket read access. Does the Eventarc trigger SA automatically inherit bucket read access?

*Answer:* No. The two identities serve different purposes; the trigger SA needs permission to deliver events, while the runtime SA needs business data permissions.

**Question 12.** What do both HTTP webhooks and CloudEvents need when retries occur?

*Answer:* Idempotency, business validation, capped retry attempts, and sufficient logging/metrics for reconciliation.

## 19. Production checklist

- [ ] Chosen **HTTP** vs. **CloudEvents** appropriately based on source and response model.
- [ ] Java entry point, Functions Framework, and Maven dependencies are correct.
- [ ] Using Cloud Run Admin API/`gcloud run` for new functions; distinguished from Cloud Functions v2 API.
- [ ] Eventarc trigger has correct **type, source filter, and location**; verified healthy.
- [ ] IAM for deployer, build, runtime, trigger, and service agents is cleanly separated.
- [ ] Private services are invoked via Invoker identity; public webhooks validate signatures and prevent replay.
- [ ] Handler handles duplicates and out-of-order delivery using a durable dedupe store.
- [ ] No reliance on in-memory caches or local disk for business state.
- [ ] No self-trigger loops when writing results to Cloud Storage.
- [ ] Retries, retention, and dead-letter handling are designed and tested; transient vs. permanent errors are distinguished.
- [ ] Timeout, concurrency, max instances, and downstream limits are properly sized.
- [ ] Logs/metrics cover service, trigger, backlog, and business outcomes without leaking secrets.
- [ ] CI tests, image/build metadata, IAM review, and rollback have clear owners.
- [ ] Budgets, cost alerts, and safe cleanup are in place for lab/resources.

## 20. Conclusion

**HTTP functions receive requests initiated by clients; event-driven functions receive CloudEvents routed by Eventarc.** Both share Cloud Run infrastructure and Functions Framework, yet differ in authentication, input contracts, retries, and idempotency. For production readiness, it is not enough to "deploy and see it run": you must verify that **the right identity can invoke it, events are filtered accurately, errors are recoverable, duplicates do not double-execute work, and costs stay under control**.

## Official reference documentation

- [Cloud Run functions overview](https://cloud.google.com/run/docs/functions/overview)
- [Compare Cloud Run functions](https://cloud.google.com/run/docs/functions/comparison)
- [Write Cloud Run functions](https://cloud.google.com/run/docs/write-functions)
- [Deploy Cloud Run functions](https://cloud.google.com/run/docs/deploy-functions)
- [Cloud Run function triggers](https://cloud.google.com/run/docs/function-triggers)
- [Java runtime for Cloud Run functions](https://cloud.google.com/run/docs/runtimes/java)
- [Trigger Cloud Run functions from Cloud Storage](https://cloud.google.com/run/docs/tutorials/trigger-functions-storage)
- [Create Eventarc triggers](https://cloud.google.com/run/docs/triggering/trigger-with-events)
- [Eventarc Standard overview](https://cloud.google.com/eventarc/standard/docs/overview)
- [Eventarc Standard retry events](https://cloud.google.com/eventarc/docs/retry-events)
- [Eventarc roles and permissions](https://cloud.google.com/eventarc/docs/roles-permissions)
- [Cloud Run services IAM](https://cloud.google.com/run/docs/securing/managing-access)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Eventarc pricing](https://cloud.google.com/eventarc/pricing)
