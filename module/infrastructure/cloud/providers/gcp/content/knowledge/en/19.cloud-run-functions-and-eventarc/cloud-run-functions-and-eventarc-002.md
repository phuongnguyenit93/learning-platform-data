# Choosing between functions, a Cloud Run service, or a Cloud Run job

An e-commerce system on Google Cloud has three workloads: handling HTTP requests to create orders, generating thumbnails when new images appear in Cloud Storage, and running a nightly revenue report. All three can run in containers, yet **they should not be forced into a single execution model**. An HTTP API needs an endpoint and returns responses; event processing needs triggers and duplicate protection; batch reporting needs to run to completion and report a success/failure status.

In the **Cloud Run functions and Eventarc** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson helps you choose between **Cloud Run functions**, a **Cloud Run service**, and a **Cloud Run job**, examining Java application architecture, IAM, Pub/Sub/Eventarc, Cloud Storage, CI/CD, reliability, and cost. The content focuses on **resource selection decisions**, rather than repeating the entire Cloud Run runtime contract.

After this lesson, you will be able to:

- Understand why a **function is deployed as a Cloud Run service**, while its authoring and release flow differs from a custom container service.
- Choose the right resource based on **request–response**, **event-driven**, or **run-to-completion** patterns.
- Write and deploy a Java HTTP function using Functions Framework, and use Eventarc for events.
- Create a Cloud Run service from an image and a Cloud Run job that partitions data by task index.
- Design triggers, IAM permissions, retry/idempotency logic, and durable state storage.
- Compare cold starts, concurrency, timeouts, costs, and common pitfalls.

> **Lab scope:** project names, images, buckets, and service accounts are examples only; create resources only in an approved lab project. Cloud Build, Artifact Registry, Cloud Run, Eventarc, Pub/Sub, and storage may incur charges.

## 1. How are functions, services, and jobs related?

A **Cloud Run service** is a resource that serves **HTTP requests**, with an HTTPS URL, revisions, traffic splitting, autoscaling, and runtime settings. You can deploy a service using a self-built **container image** or from **source code**.

A **Cloud Run function** is a way to write a **single-purpose handler** (HTTP or CloudEvent), after which Google Cloud uses Functions Framework and buildpacks/Cloud Build to build an image and **deploy it as a Cloud Run service**. Under the current model, a function is **not a separate server type** from a Cloud Run service. It is a convenient **development/deployment model** for a small piece of processing logic.

A **Cloud Run job** is a different resource: each **execution** launches one or more tasks; the container does its work and **exits with an exit code**. A job does not need an HTTP listener or a URL to receive client requests.

~~~mermaid
flowchart TD
  A["Have work to run?"] --> B{"Is there an HTTP request needing a response?"}
  B -- Yes --> C{"Mainly a single small handler?"}
  C -- Yes --> D["Cloud Run function<br/>creates a Cloud Run service from source"]
  C -- No --> E["Cloud Run service<br/>custom framework/image"]
  B -- No --> F{"Are there Cloud Storage/Pub/Sub events?"}
  F -- Yes --> G{"Short processing per event?"}
  G -- Yes --> H["Function or service + Eventarc"]
  G -- No --> I["Queue/Workflows → suitable job or worker"]
  F -- No --> J{"Runs to completion?"}
  J -- Yes --> K["Cloud Run job"]
  J -- No --> L["Consider Cloud Run worker pool"]
~~~

This is a **decision tree**, not an absolute boundary. A service can receive Eventarc CloudEvents; a function also has an HTTPS endpoint; a job can be started by an HTTP API via the **Cloud Run Jobs API**, though the job itself is not an HTTP handler.

### Comparison matrix

| Criterion | **Function on Cloud Run** | **Custom Cloud Run service** | **Cloud Run job** |
|---|---|---|---|
| Purpose | Single HTTP/CloudEvent handler | API, web app, gRPC, or complex event receiver | Batch, import/export, ETL, migration |
| Input | HTTP request / CloudEvent delivered by trigger | HTTP request / CloudEvent over HTTP | Execution via command, API, schedule, or workflow |
| Typical deploy method | `--source . --function ENTRYPOINT` | Image or source, optionally with Dockerfile | Image or source/entrypoint that runs to completion |
| Container HTTP listener | Managed by Functions Framework | Application-managed, listening on `PORT` | **Not needed** |
| Output | HTTP response / CloudEvent handler result | HTTP response/status | `exit 0` for success, non-zero for failure |
| Scaling | Cloud Run service autoscaling | Service autoscaling, concurrency | Task count, parallelism, retries |
| Release versioning | Cloud Run revisions | Cloud Run revisions, traffic splitting | Job definition and executions |
| Suitability for long operations | Constrained by request/event delivery timeout | Constrained by request timeout | Longer task timeouts, checkpoints/retries |
| Billing | Per Cloud Run service and related resources | Per Cloud Run service and related resources | Per resources consumed while tasks run |

**Common confusion:** older docs and projects refer to **Cloud Functions (2nd gen)** or use `gcloud functions deploy`. The current model is called **Cloud Run functions**, preferring deployment via the **Cloud Run Admin API** and `gcloud run deploy --function`. Functions created with the Cloud Functions v2 API can be managed via Cloud Run, though not every newer Cloud Run operation is backward-compatible with the old API; **1st gen** is a separate generation with different limits and pricing.

## 2. The three most important decision questions

### 2.1. Who initiates the work and who expects a response?

- **A client waits for an HTTP response:** use a service or an HTTP function.
- **An object/event changes and needs a callback:** use **Eventarc → Cloud Run service/function**; the consumer receives an HTTP **CloudEvent**.
- **The system needs to finish a batch with an outcome:** run a job via CLI, scheduler, workflow, or API.

Do not confuse the **trigger source** with the **execution model**: Eventarc turns an event into an HTTP request to a destination service/function; it does not turn a job into a server.

### 2.2. Does the application need control over web server structure?

Choose a **function** when the logic is short, has few endpoints, is supported by the runtime and Functions Framework, and does not require managing a main server, Dockerfile, or complex middleware.

Choose a **custom service** when you have many endpoints, a REST/gRPC framework, routing/middleware, specialized native dependencies, custom container builds, and application-controlled startup and probes. **A service can also be deployed from source using buildpacks**; writing a Dockerfile is not mandatory.

### 2.3. Does the work terminate or run continuously?

A job fits workloads with a clear completion point: process N files, generate a report, update data, export results, and exit. A consumer pulling Pub/Sub **continuously** should evaluate a **Cloud Run worker pool** or a service receiving Pub/Sub push; do not create an infinite-loop job just to keep a process alive.

## 3. Functions: lifecycle from source to Cloud Run service

~~~text
Java source + pom.xml + function entrypoint
        ↓ Cloud Run functions deployment
Cloud Storage (source storage)
        ↓
Cloud Build + buildpacks + Functions Framework
        ↓
Artifact Registry (container image)
        ↓
Cloud Run service / revision / HTTPS URL
        ↑
HTTP caller or Eventarc trigger (CloudEvent)
~~~

**Strengths:** fast delivery of single-purpose handlers without writing an HTTP server or Dockerfile. **Practical limits:** you must use a supported runtime and Functions Framework, configure a valid function entry point, and still manage IAM, logs, retries, databases, and concurrency.

Functions can be:

- **HTTP function:** implements a handler returning an HTTP response, suitable for webhooks or simple processing endpoints.
- **CloudEvent function:** receives standardized CloudEvents object/event metadata when triggered by Eventarc; suitable for Cloud Storage, Pub/Sub, or other supported sources.

**A CloudEvent differs from a raw Pub/Sub payload:** Eventarc uses envelope fields such as `id`, `source`, `type`, `subject` alongside `data`; the handler must interpret the event type and source properly. Do not assume a Cloud Storage event contains the full image bytes; it typically contains only metadata, so you must read the object via the Storage API if needed.

## 4. Example A: Java HTTP function and deploying from source

This small sample illustrates the Java Functions Framework. Learners should create an independent lab directory:

~~~text
hello-function/
├── pom.xml
└── src/main/java/example/HelloFunction.java
~~~

**`src/main/java/example/HelloFunction.java`**

~~~java
package example;

import com.google.cloud.functions.HttpFunction;
import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;
import java.io.BufferedWriter;

public class HelloFunction implements HttpFunction {
    @Override
    public void service(HttpRequest request, HttpResponse response)
            throws Exception {
        response.setStatusCode(200);
        BufferedWriter writer = response.getWriter();
        writer.write("Hello from a Java Cloud Run function");
    }
}
~~~

**`pom.xml`** (Maven, minimal):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>hello-function</artifactId>
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
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration><release>21</release></configuration>
      </plugin>
      <plugin>
        <groupId>com.google.cloud.functions</groupId>
        <artifactId>function-maven-plugin</artifactId>
        <version>0.11.0</version>
        <configuration>
          <functionTarget>example.HelloFunction</functionTarget>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Functions Framework invokes the `service` method of the class with the fully qualified name `example.HelloFunction`. Therefore, there is no `public static void main`, no need to read `PORT`, and no need to open sockets manually; the runtime manages the HTTP listener for the function.

Run locally using Maven/Functions Framework inside the directory containing `pom.xml`:

~~~bash
mvn function:run -Drun.functionTarget=example.HelloFunction

# In another terminal:
curl -i http://localhost:8080/
~~~

Before deploying, run Maven with JDK 21 and verify the handler returns the expected content. If you run from a machine/IDE using a Java version different from `maven.compiler.release`, the build may fail; select the same runtime as the Cloud Run environment.

### Deploying a private HTTP function

~~~bash
PROJECT_ID="my-functions-lab"
REGION="asia-southeast1"
FUNCTION_NAME="hello-java"
RUNTIME_SA="app-runtime@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com logging.googleapis.com

# Run inside the hello-function/ directory containing pom.xml and src/.
gcloud run deploy "$FUNCTION_NAME" \
  --source . \
  --function example.HelloFunction \
  --base-image java21 \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --no-allow-unauthenticated

gcloud run services describe "$FUNCTION_NAME" \
  --region "$REGION" \
  --format="yaml(status.url,status.conditions)"
~~~

Before deploying, the runtime service account must already exist; the deployer must have Cloud Run source deployment permissions, permission to use the service account, and the required Cloud Build/Artifact Registry permissions for the build model. **Do not switch to `--allow-unauthenticated` to bypass production IAM errors**.

To test the private endpoint, use an identity that already holds `roles/run.invoker`:

~~~bash
URL="$(gcloud run services describe "$FUNCTION_NAME" \
  --region "$REGION" --format="value(status.url)")"

curl -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$URL"
~~~

Without Invoker permission, the server will reject requests even if the Java code is correct. Read Cloud Run revision logs on build or startup errors; test locally with the Functions Framework CLI/Maven plugin when needed, and do not judge full security posture from local `curl` alone.

## 5. Example B: Cloud Run service for a multi-endpoint API

A Java/Spring Boot API has multiple routes (`/orders`, `/products`, `/healthz`), requiring request validation, exception filters, connection pooling, and authentication middleware. This is usually a **Cloud Run service** rather than splitting every endpoint into a separate function.

In Spring Boot, minimal application configuration:

~~~properties
server.address=0.0.0.0
server.port=${PORT:8080}
~~~

`PORT` is provided by Cloud Run (default 8080); do not bind only to localhost. Example handler:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrdersController {
    @GetMapping("/{id}")
    public ResponseEntity<String> getOrder(@PathVariable String id) {
        // In production: read from service/database with IAM and timeouts.
        return ResponseEntity.ok("order=" + id);
    }
}
~~~

This is a handler snippet inside an **existing Spring Boot project with an application class, web starter, and build pipeline**, not a standalone complete Maven project. Unlike the function in section 4, **the Spring Boot application itself** manages the HTTP server and all routing; thus you have full choice over frameworks, filters, and custom health endpoints.

After CI has built a `linux/amd64` image and pushed it to Artifact Registry:

~~~bash
PROJECT_ID="my-functions-lab"
REGION="asia-southeast1"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/apps/orders-api:v1"
RUNTIME_SA="app-runtime@$PROJECT_ID.iam.gserviceaccount.com"

gcloud run deploy orders-api \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --concurrency 20 \
  --timeout 60s \
  --max-instances 10 \
  --no-allow-unauthenticated
~~~

**Do not choose a service just because there are many lines of code.** The deciding factor is whether you need a custom web app/server and lifecycle. A function can also be configured with revisions, CPU/memory, concurrency, VPC, and many service features; it is not necessarily a "simpler but weaker" infrastructure option.

### Releases and scaling

- **Revisions** let you release a new image or source and manage traffic splitting/rollback via Cloud Run.
- **Concurrency** is the maximum number of requests an instance can handle simultaneously; you must load-test to choose an appropriate value for the Java heap, thread pool, and Cloud SQL connections.
- **Min instances** partially reduce cold starts but increase cost; **max instances** limit scaling but do not replace downstream business-level rate limits.
- **Request timeout** defaults to 5 minutes, up to 60 minutes for a service; returning HTTP 504 **does not guarantee server-side processing is canceled immediately**.
- **CPU allocation** depends on request-based/instance-based billing; do not run critical background threads after returning an HTTP response and expect them to always finish.

## 6. Example C: Cloud Run job for a Java batch

Suppose an application must compute reports for 1,000 customers every night. The work has a clear end, can be re-run, and needs no HTTP endpoint. A **Cloud Run job** is the natural choice.

### Partitioning work with task index

The **`BatchMain.java`** file simulates partitioning by task index:

~~~java
public final class BatchMain {
    public static void main(String[] args) {
        int taskIndex = Integer.parseInt(
            System.getenv().getOrDefault("CLOUD_RUN_TASK_INDEX", "0"));
        int taskCount = Integer.parseInt(
            System.getenv().getOrDefault("CLOUD_RUN_TASK_COUNT", "1"));
        int attempt = Integer.parseInt(
            System.getenv().getOrDefault("CLOUD_RUN_TASK_ATTEMPT", "0"));

        try {
            for (int customerId = 0; customerId < 1000; customerId++) {
                if (customerId % taskCount != taskIndex) {
                    continue;
                }
                // Production: read DB, write report using an idempotency key
                // (execution/customerId or reportingDate/customerId).
                System.out.printf(
                    "task=%d/%d attempt=%d customer=%d%n",
                    taskIndex, taskCount, attempt, customerId);
            }
            // main finishes normally => exit code 0.
        } catch (Exception ex) {
            System.err.println("Batch failed: " + ex.getMessage());
            System.exit(1);
        }
    }
}
~~~

`CLOUD_RUN_TASK_INDEX` is in the range `0 .. CLOUD_RUN_TASK_COUNT - 1`; **the job does not partition customers automatically** — your code must select the subset. `CLOUD_RUN_TASK_ATTEMPT` increments when a task retries, but it should not be included in the business idempotency key if you want retries to avoid generating duplicate results.

Standalone illustrative Dockerfile for the batch job (save alongside `BatchMain.java` in a lab directory):

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY BatchMain.java .
RUN javac BatchMain.java

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/BatchMain.class .
ENTRYPOINT ["java", "BatchMain"]
~~~

Build and push to an **existing** registry:

~~~bash
PROJECT_ID="my-functions-lab"
REGION="asia-southeast1"
JOB_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/apps/report-batch:v1"

gcloud auth configure-docker "$REGION-docker.pkg.dev"
docker build --platform linux/amd64 -t "$JOB_IMAGE" .
docker push "$JOB_IMAGE"
~~~

Create the job and run an execution:

~~~bash
RUNTIME_SA="app-runtime@$PROJECT_ID.iam.gserviceaccount.com"

gcloud run jobs create daily-report \
  --image "$JOB_IMAGE" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --tasks 4 \
  --parallelism 2 \
  --task-timeout 900s \
  --max-retries 2

gcloud run jobs execute daily-report \
  --region "$REGION" \
  --wait
~~~

With four tasks and parallelism of two, at most **two tasks run concurrently** as configured; execution order is not guaranteed. If a task exhausts retries or returns a non-zero exit code, the execution may fail.

**Limits:** default task timeout is **10 minutes**, configurable up to **168 hours** (GPUs have separate limits). The timeout applies **per task attempt**, not across the entire execution; the job can retry. A job **does not automatically run every night** just because it is named `daily-report` — you need Cloud Scheduler or Workflows/API.

### Running on a schedule without turning a job into an HTTP server

~~~text
Cloud Scheduler (on business timezone)
      ↓ authenticated HTTP API call
Cloud Run Jobs API :run
      ↓
Job execution (4 tasks, parallelism 2)
      ↓
Database / Cloud Storage reports
~~~

The Scheduler identity must have permission to **run the job** (for example, `run.jobs.run` permission via a supported role), and an appropriate OAuth token when calling Google Cloud APIs. For multi-step workflows needing branching or waiting on a job, consider **Workflows → Cloud Run job**. Do not grant job admin/deploy permissions just so Scheduler can execute it.

## 7. Eventarc: invoking a function or service on events

**Eventarc** filters and routes events from Cloud Storage, Pub/Sub, Audit Logs, and other supported sources to a **Cloud Run service**. When the destination is a **Cloud Run function**, Eventarc still sends an **HTTP CloudEvent** to the service deployed from the function source code.

~~~mermaid
flowchart LR
  U["App uploads image"] --> B["Cloud Storage bucket"]
  B --> E["Eventarc trigger: finalized + bucket filter"]
  E --> F["Cloud Run function / service"]
  F --> S["Cloud Storage thumbnail + DB status"]
  I["Trigger service account"] --> E
~~~

To receive Cloud Storage finalized events, use the event type:

~~~text
google.cloud.storage.object.v1.finalized
~~~

Do not confuse this with the `OBJECT_FINALIZE` name in **Pub/Sub notification attributes**. With Eventarc direct events, an object may be delivered more than once; delivery order is not guaranteed. Handlers should use `source + id` or `bucket + object + generation + operation` as a deduplication key depending on business semantics.

### Java CloudEvent function

This is a separate handler added to the Java function source using the Functions Framework declared in `pom.xml`:

~~~java
package example;

import com.google.cloud.functions.CloudEventsFunction;
import io.cloudevents.CloudEvent;
import java.nio.charset.StandardCharsets;
import java.util.logging.Logger;

public class StorageEventFunction implements CloudEventsFunction {
    private static final Logger LOG =
        Logger.getLogger(StorageEventFunction.class.getName());

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!"google.cloud.storage.object.v1.finalized".equals(
                event.getType())) {
            return;
        }
        if (event.getData() == null) {
            throw new IllegalArgumentException("Missing object event data");
        }
        String metadataJson = new String(
            event.getData().toBytes(), StandardCharsets.UTF_8);
        LOG.info("eventId=" + event.getId()
            + " source=" + event.getSource()
            + " payloadBytes=" + metadataJson.length());

        // Production: parse metadata JSON with validation,
        // extract bucket, object name, generation;
        // claim job atomically, read exact generation,
        // write thumbnail and commit before returning.
    }
}
~~~

This snippet is a **CloudEvent receiver skeleton** and does not perform resizing yet. Do not merely log an event and consider it processed in production. With metadata JSON, avoid logging the entire payload because object names and custom metadata may be sensitive.

Deploy the separate Java entry point from source:

~~~bash
gcloud run deploy image-finalized-handler \
  --source . \
  --function example.StorageEventFunction \
  --base-image java21 \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --no-allow-unauthenticated
~~~

**Note:** the CloudEvent function and HTTP function are **two separate entry points** deployed as **two Cloud Run services** when using the two service names in the example. A CloudEvent function does not have a trigger automatically upon deployment; the next step is creating an Eventarc trigger.

### Creating an Eventarc trigger for Cloud Storage

Assume the bucket is in the **same project** and has a location compatible with the `asia-southeast1` Eventarc trigger; the project already has billing and service accounts configured per procedure. The commands below illustrate essential IAM requirements; additional service agent permissions or APIs may be needed depending on organization policies.

~~~bash
PROJECT_ID="my-functions-lab"
REGION="asia-southeast1"
BUCKET="my-image-events-lab-unique"
TRIGGER_SA="eventarc-trigger@$PROJECT_ID.iam.gserviceaccount.com"

gcloud services enable \
  eventarc.googleapis.com eventarcpublishing.googleapis.com \
  pubsub.googleapis.com storage.googleapis.com \
  run.googleapis.com

# Dedicated trigger identity; create only if it does not already exist.
gcloud iam service-accounts create eventarc-trigger \
  --display-name="Invoke image-finalized-handler from Eventarc"

# Eventarc requires permission to receive events for the source/trigger type.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/eventarc.eventReceiver"

# The trigger uses this identity to invoke the PRIVATE Cloud Run service.
gcloud run services add-iam-policy-binding image-finalized-handler \
  --region="$REGION" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/run.invoker"

# Cloud Storage service agent needs permission to publish via the Pub/Sub layer.
STORAGE_AGENT="$(gcloud storage service-agent --project="$PROJECT_ID")"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$STORAGE_AGENT" \
  --role="roles/pubsub.publisher"

gcloud eventarc triggers create image-finalized-trigger \
  --location="$REGION" \
  --destination-run-service=image-finalized-handler \
  --destination-run-region="$REGION" \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=$BUCKET" \
  --service-account="$TRIGGER_SA"
~~~

**Do not copy these IAM bindings verbatim to production**: for instance, granting `roles/pubsub.publisher` to the Cloud Storage service agent at the **project level** for Eventarc direct events requires security review. If a trigger identity or binding already exists, use IaC/import/verify before creating to avoid overlapping ownership. In organizations with strict IAM controls, a platform team may need to perform part of the setup.

Verification:

~~~bash
gcloud eventarc triggers describe image-finalized-trigger \
  --location="$REGION"

# Upload only to the lab bucket, never to production data.
printf 'demo' > image-test.txt
gcloud storage cp image-test.txt "gs://$BUCKET/image-test.txt"

gcloud run services logs read image-finalized-handler \
  --region="$REGION" --limit=30
~~~

The example function only logs **eventId/source/payload length**; it does not generate thumbnails. The expected result is that the event is routed to the destination after the trigger and IAM take effect. If no logs appear, check the location, event filters, Cloud Storage service agent, Eventarc trigger SA, and Pub/Sub transport; do not immediately assume the Java code is broken.

**Location rules:** for Eventarc direct events from Cloud Storage, the bucket must be in the **same project** and a location compatible with the trigger. The destination Cloud Run service must be in the **same project** as the trigger, and may be in another supported region. Created event types/filters should not be treated as mutable in place: to change the event type or source filter, you typically need to **create a new trigger, verify it, and then delete the old trigger**.

## 8. Reliability: retries, idempotency, and asynchronous errors

Eventarc delivers events via a managed Pub/Sub transport, so you must design for **at-least-once delivery** and **no ordering guarantees**. Never assume "each object is processed only once" or "an older object version always arrives before a newer version."

### Example: re-uploading the same object name

~~~text
Upload incoming/photo.jpg (generation 100)
Upload incoming/photo.jpg (generation 101)
           ↓
Eventarc may deliver 101 before 100 and redeliver event 100
           ↓
Consumer must use generation and idempotent operations
~~~

Reference deduplication keys:

~~~text
event dedupe key = cloudEvent.source + "|" + cloudEvent.id
business key     = bucket + "|" + objectName + "|" + generation + "|thumbnail"
~~~

`source+id` helps recognize a redelivered CloudEvent; the business key reduces the chance of two different events/triggers generating duplicate thumbnails for the same generation. When writing to Cloud Storage, use a **generation precondition** or include the generation in the output name; when writing to a database, use a unique constraint/transaction.

| Issue | Correct behavior |
|---|---|
| Consumer hits a transient network error | Return an error so the transport retries per policy |
| File has an invalid format | Record an audit error status, consider a DLQ; avoid infinite retries |
| Object generation was already deleted | Apply a stale-event policy; do not silently read a newer generation |
| Processing finished but response/ack was lost | Retry sees committed result and finishes idempotently |
| Older event arrives after a newer event | Do not allow the older event to overwrite current state |
| Event missed due to misconfiguration | Reconcile using object inventory and a processing registry |

**Cloud Run services/functions handling events over HTTP**: report success only when work is **durably committed** or **safely enqueued** to another system. Do not return HTTP 2xx before launching a long-running background thread; the instance may lose CPU or be terminated.

### Avoiding retry storms

If the Cloud SQL backend has a transient outage and every event retries continuously, the database can become even more overloaded. You need:

- Retries with **backoff/jitter**, capped total attempts, and deadlines.
- **Dead-letter handling** when supported by the transport; inspect the retry policy and underlying Pub/Sub subscription of the trigger.
- Alerts on oldest-unacked age, DLQ, and function/service errors.
- Max instances/concurrency limits to keep downstream pressure within capacity; do not rely on max instances as a guarantee that will never be exceeded in all scenarios.
- Business integrity tracking via reconciliation, not just HTTP success rates.

**Do not assume a trigger can directly invoke a job**. To process events with a job, an intermediary service/function can validate the event and call the **Jobs API :run**, or use Workflows to orchestrate; that invocation is a separate operation with its own IAM and duplicate-execution risks. For small files, creating a job execution may incur more startup time and cost than processing directly inside an event function.

## 9. Timeouts, scaling, and billing when choosing a platform

| Factor | HTTP function / service | Event-driven function / service | Job |
|---|---|---|---|
| Duration | Constrained by request timeout | Constrained by HTTP delivery/trigger and deployment method | Constrained by task timeout |
| Notable defaults | Service request timeout 5 minutes | Follows request timeout and trigger mechanism used | Task timeout 10 minutes |
| Reference limits | Service up to 60 minutes | **Cloud Functions v2 API event-driven** may be limited to 9 minutes; Cloud Run Admin API path requires checking service/trigger policy | Task up to 168 hours, GPUs have separate limits |
| Concurrency | Can handle multiple requests per instance | Can handle multiple event requests per instance when configured | Parallelism limits concurrent tasks |
| Scaling | Autoscaling by request/concurrency and config | Autoscaling by event request volume to the service | `tasks` and `parallelism` per execution |
| Billing | Cloud Run service: request-based/instance-based per config | **Also a Cloud Run service**, plus Eventarc/transport | CPU/memory during task runtime |
| External dependencies | DB/API/network latency | Eventarc/Pub/Sub + DB/API + retries | Job startup, partitioning, DB/API, retries |

**Limits vary by API generation, configuration, and workload type.** Do not take the 9-minute timeout of the Cloud Functions v2 API and claim every Cloud Run function is capped at 9 minutes; likewise, do not take the 60-minute max of an HTTP service and assume an event trigger will always wait 60 minutes. Check the exact documentation and deployment method used.

### Cost estimation

~~~text
Function / service:
  Cloud Run CPU + memory + request/instance time per billing mode
  + source build/Artifact Registry (when deploying from source)
  + Eventarc/PubSub (if receiving events)
  + network, storage, logging, database...

Job:
  total task execution CPU/memory time
  + image registry, network, storage, logging, database...
  + Scheduler/Workflows (if used)
~~~

A function is **not automatically cheaper** than a service just because it has less code: they run on the same Cloud Run platform. A job can be cost-effective when batches run on schedule and **do not hold resources continuously between executions**; however, long-running tasks, retries, high parallelism, and downstream access still incur significant costs.

### Cold starts and processing capacity

Java apps can take time for class loading, JIT warmup, and creating DB pools. **Function/source deployment does not eliminate cold starts**; services also experience cold starts. Min instances, startup CPU boost, optimizing images/dependencies, and avoiding slow synchronous connections during startup can improve latency but carry cost implications.

If a batch must finish before a cutoff time, do not just raise `--parallelism`; benchmark actual throughput, Cloud SQL limits, Pub/Sub, networking, and quotas. Excessive parallelism can slow down the database or increase errors.

## 10. IAM: distinguishing deployer, invoker, trigger, and runtime

Many `403` errors come from **granting the right role to the wrong identity**. Four roles in a pipeline may map to four different service accounts:

| Identity | What does it do? | Typical required permissions |
|---|---|---|
| **Deployer/CI/CD** | Builds and deploys source/image, updates service/job | Cloud Run deployment, Service Account User, and required build/registry permissions |
| **Trigger identity** | Eventarc invokes a private destination | `roles/run.invoker` on the exact Cloud Run service; `roles/eventarc.eventReceiver` when required by source |
| **Runtime service account** | Code inside the container calls Cloud Storage, Pub/Sub, Cloud SQL | Business role **on specific resources**, not Editor |
| **Scheduler/Workflow identity** | Calls Jobs API to start an execution | `run.jobs.run` permission or appropriate executor role |

For direct Cloud Storage events, the **Cloud Storage service agent** also needs permission to publish events to the Pub/Sub transport managed by Eventarc. Granting roles to the runtime service account **does not automatically grant them** to the storage service agent or trigger service account.

### Separated authentication flows

~~~text
Event delivery:
  Cloud Storage service agent → Pub/Sub transport (Publisher)
  Eventarc trigger identity → Cloud Run service (Invoker)

Data processing:
  Function / service runtime SA → Cloud Storage object (Object Viewer)
  Function / service runtime SA → Cloud SQL (Cloud SQL Client + DB auth)

Batch execution:
  Cloud Scheduler SA → Cloud Run Jobs API (run.jobs.run)
  Job runtime SA → Cloud Storage / database (business roles)
~~~

For Java, use **Application Default Credentials (ADC)** from the Cloud Run service identity to call Google Cloud APIs; **do not** embed JSON service account keys in the image or source code. To read files from Cloud Storage, the runtime SA needs read permission on the appropriate bucket/object **and** a working network path/API access.

### Security practices

- Only expose a public HTTP function/service when a real webhook/public API requires it; otherwise use a private service and IAM Invoker.
- For external webhooks, verify the **sender's signature**; Cloud Run IAM does not replace application-level signature verification when an endpoint must be public.
- Never place secrets in images, URLs, or event payloads; use Secret Manager and narrow IAM scopes.
- Check IAM Conditions, Organization Policies, VPC Service Controls, and IAM Deny rules when Allow roles look right yet 403 persists.
- Restrict permissions for Pub/Sub subscribers, Eventarc trigger admins, and destination editors: modifying a trigger/endpoint can redirect sensitive events.
- Keep Cloud Logging/Audit Logs appropriately scoped; do not log full payloads or bearer tokens.

## 11. Enterprise scenario: three workloads, three decisions

An e-commerce team runs applications on Google Cloud and needs:

| Need | Recommended design | Why |
|---|---|---|
| **Java ordering API**, ~12 endpoints, multiple middleware layers, Cloud SQL | **Cloud Run service** from CI image | Control over Spring Boot/routing, releases, concurrency, DB pooling |
| **Product image upload**, thumbnail creation, publish metadata to Pub/Sub | **Cloud Run function** receiving Cloud Storage Eventarc finalized | Single small handler, built from source, easy event-driven fit |
| **Nightly revenue report** for millions of orders, partitionable | **Cloud Run job** triggered by Cloud Scheduler/Workflows | Provides executions, task count, parallelism, and exit codes |

~~~mermaid
flowchart TD
  C["Mobile/Web client"] --> API["Cloud Run service: orders-api"]
  API --> SQL["Cloud SQL"]
  API --> GCS["Cloud Storage: images"]
  GCS --> EVT["Eventarc: finalized"]
  EVT --> FN["Cloud Run function: thumbnail"]
  FN --> GCS
  SCH["Cloud Scheduler"] --> J["Cloud Run job: daily-report"]
  J --> SQL
  J --> OUT["Cloud Storage: report artifacts"]
~~~

**Why not use a function for everything?** Multi-route APIs with middleware are more natural to build as a web service; batch workloads can exceed request timeouts and benefit from task completion semantics; event functions cleanly handle a single job with idempotent semantics.

**Can a service replace the function?** Yes. If the image pipeline grows to need multiple routes, custom native libraries, complex media processing, or a unified framework, you can deploy a container Cloud Run service and attach **the same Eventarc trigger**. Triggers do not require the destination to be deployed with `--function`.

**Can a function replace the job?** For a very small report finishing under the timeout and triggered per event, possibly. However, when it must run for hours, split across partitions, retry per task, and keep execution history, a job is much clearer.

### A fourth case: always-connected consumer

A Java `KafkaConsumer.poll()` application runs continuously, has no HTTP requests, and never terminates. Do not force it into a job that never exits. Consider a **Cloud Run worker pool** (manual scaling), or an architecture that turns Kafka/Pub/Sub into HTTP push to a service when suitable. This is an important exception to the decision tree in section 1.

## 12. Layered troubleshooting

| Symptom | Common causes | Verification steps |
|---|---|---|
| Function build fails | Missing `pom.xml`/dependency, wrong function entry point or runtime | Cloud Build logs and `--function` FQCN |
| Java function deploys but returns 404 | Handler path/method mismatch, wrong service URL called | `gcloud run services describe`, request logs |
| Function/service startup port error | Custom container does not read `PORT`, entrypoint/JVM error | Revision logs; for functions, check Functions Framework build |
| HTTP 401/403 calling URL | Missing Invoker, wrong ID token audience, ingress restrictions | Caller identity and Cloud Run IAM |
| Missing Cloud Storage events | Wrong bucket/trigger location, non-matching event filter, missing Publisher/Invoker IAM | `eventarc triggers describe`, Pub/Sub transport, IAM |
| Event runs twice | At-least-once delivery or retry after timeout | Idempotency key, durable processing registry |
| Function returns 2xx but no thumbnail | Code spawned a background thread and returned, downstream failure unawaited | Return only after commit/enqueue |
| Job does not run nightly | Missing Cloud Scheduler/Workflow or missing `run.jobs.run` | Scheduler job logs, OAuth, Job executions |
| Job execution FAILED | Non-zero task exit, timeout, OOM, or retries exhausted | Execution/task logs and task index/attempt |
| HTTP 504 yet DB was written | Client timed out before handler returned response | Request deadline, DB transaction, idempotency |
| Bill increases | High min instances, retries, low concurrency, high log/event volume | Billing by SKU, Cloud Run/Artifact Registry/Eventarc |

Suggested observability commands:

~~~bash
gcloud run services describe image-finalized-handler \
  --region="$REGION"
gcloud run services logs read image-finalized-handler \
  --region="$REGION" --limit=50
gcloud eventarc triggers describe image-finalized-trigger \
  --location="$REGION"
gcloud run jobs describe daily-report --region="$REGION"

# Check Cloud Logging / Monitoring for executions,
# Pub/Sub backlog, Cloud Run request count, and 5xx errors.
~~~

For delayed events, do not conclude "Cloud Run didn't run" solely because request logs are empty; verify the event **was emitted** and the trigger routed it. For a failed job, inspect **individual task attempts**, not just the overall execution status.

### Essential SRE metrics

| Type | Priority metrics |
|---|---|
| HTTP function/service | Request rate, error rate, P95/P99 latency, cold starts, instance count |
| Eventarc pipeline | Event delivery failures, duplicate/stale count, processing lag, DLQ |
| Job | Success rate, execution/task duration, attempts, unprocessed backlog |
| Dependencies | Cloud SQL connections/latency, Storage read/write failures, API quotas |
| Cost | Cloud Run CPU/memory time, source-build/image storage, event routing, egress/logging |

A metric saying "HTTP function returned 200" does not prove the business transaction/thumbnail was written properly. Measure **completed tasks** via processing status or output object counts and reconcile against the source.

## 13. Selection and deployment checklist

- [ ] Identified whether the workload is **request-driven**, **event-driven**, or **run-to-completion**.
- [ ] If a function, understood that it is built from source into a **Cloud Run service**.
- [ ] If a service, ensured the application opens an HTTP server on the right `PORT` and supports graceful shutdown.
- [ ] If a job, ensured the command completes with proper exit codes and tasks partition data cleanly.
- [ ] Selected the right trigger: HTTP caller, Eventarc, or Cloud Scheduler/Workflows.
- [ ] Avoided confusing **Eventarc CloudEvent type** with Pub/Sub notification attribute names.
- [ ] Implemented idempotency/preconditions and retries/DLQ for events or job tasks.
- [ ] Validated timeouts/concurrency/parallelism with load tests and business SLA/SLOs.
- [ ] Granted **separate permissions** to deployer, trigger identity, runtime SA, and scheduler identity.
- [ ] Avoided embedding JSON service account keys; used Secret Manager for secrets.
- [ ] Confirmed Cloud Storage/Cloud SQL/network permissions, regions, and quotas.
- [ ] Configured logs/metrics/alerts for HTTP errors, event lag, job failures, and costs.
- [ ] Prepared a release/trigger rollback plan and scoped cleanup of test resources to the right owner.

## 14. Applied exercises

**Exercise 1 — Resource selection.** Classify and explain four workloads: (a) payment webhook requiring signature verification; (b) thumbnail processing on object finalized; (c) 40-minute nightly data aggregation; (d) never-ending Kafka consumer. For each workload, state the resource, how it is triggered, and its completion condition.

**Exercise 2 — Java function.** Starting from `HelloFunction` in section 4, add headers to return JSON and read a `GREETING` environment variable; describe how to test locally with Functions Framework and deploy with `--function example.HelloFunction` on the Java 21 runtime. Why doesn't the function need to manage `PORT` manually?

**Exercise 3 — Eventarc and IAM.** A Cloud Storage bucket `images-lab` emits finalized events to private `image-finalized-handler`. Diagram the three identities — **Storage service agent**, **Eventarc trigger SA**, and **runtime SA** — and assign minimal roles for each step. Explain why granting Object Viewer to the runtime SA is **not enough** for Eventarc to deliver events.

**Exercise 4 — Handling duplicates.** Object `incoming/photo.jpg` is uploaded twice, generations 100 and 101. The event for 101 arrives before 100, and later event 100 is redelivered. Write the idempotency key, output naming strategy, and database condition so the newer thumbnail is not overwritten by the older event.

**Exercise 5 — Parallel job.** You need to process 1,000 customers with `--tasks=4 --parallelism=2 --max-retries=2`. Based on the code in section 6, which customer IDs does task index 2 process? If this task retries, why must `attempt` not generate a new set of results? Which exit code should be used for transient failures?

**Exercise 6 — Cost and operational decisions.** Compare an HTTP function and a Spring Boot service at the same 100,000 requests/day with identical CPU/memory/concurrency. List shared costs and additional source-build costs, identify when min instances are worth the expense, and explain why you cannot conclude "a function is always cheaper than a service."

**Exercise 7 — Extended architecture.** An API must accept a 2 GiB file, run OCR that can take 90 minutes, and return the result upon completion. Design a Cloud Run service receiving requests, Cloud Storage storing files, and Pub/Sub/Cloud Tasks or Workflows orchestrating a Cloud Run job; describe idempotency, checkpointing, callback/status polling, and SLOs.

## Official reference documentation

- [What is Cloud Run](https://cloud.google.com/run/docs/overview/what-is-cloud-run) — services, jobs, worker pools, and instances.
- [Cloud Run deployment options and resource model](https://cloud.google.com/run/docs/resource-model) — source, image, functions, and resources.
- [Cloud Run functions overview](https://cloud.google.com/run/docs/functions/overview) — how functions are built/deployed as services.
- [Compare Cloud Run functions](https://cloud.google.com/run/docs/functions/comparison) — Cloud Run Admin API, Cloud Functions v2 API, and 1st gen.
- [Write Cloud Run functions](https://cloud.google.com/run/docs/write-functions) — HTTP/CloudEvents handlers, Java Functions Framework.
- [Deploy a Cloud Run function](https://cloud.google.com/run/docs/deploy-functions) — `gcloud run deploy --function`.
- [Java runtime](https://cloud.google.com/run/docs/runtimes/java) — runtime IDs and base images.
- [Deploy a Cloud Run service](https://cloud.google.com/run/docs/deploying) — image/source, revisions.
- [Create Cloud Run jobs](https://cloud.google.com/run/docs/create-jobs) — tasks, retries, and executions.
- [Set a task timeout for jobs](https://cloud.google.com/run/docs/configuring/task-timeout) — execution duration limits.
- [Eventarc triggers for Cloud Run](https://cloud.google.com/run/docs/triggering/trigger-with-events) — CloudEvents, filters, and trigger IAM.
- [Route Cloud Storage events with Eventarc](https://cloud.google.com/eventarc/standard/docs/run/route-trigger-cloud-storage) — locations, Eventarc roles, Cloud Storage service agent.
- [Cloud Run service identity](https://cloud.google.com/run/docs/securing/service-identity) — ADC and IAM.
- [Cloud Run pricing](https://cloud.google.com/run/pricing) — billing for functions/services/jobs.
- [Eventarc pricing](https://cloud.google.com/eventarc/pricing) — event routing.
