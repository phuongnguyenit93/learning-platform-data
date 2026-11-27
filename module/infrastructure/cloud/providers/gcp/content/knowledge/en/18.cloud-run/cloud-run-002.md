# Container Runtime Contract and Application Requirements

A Java image that runs fine with `docker run` fails when deployed to Cloud Run with *container failed to start and listen on the port defined by PORT*. A data import batch created as a Cloud Run service does not open an HTTP port, so it fails to start. Both incidents stem from the application **violating the container runtime contract** of the chosen Cloud Run resource type.

The **container runtime contract** is the set of rules governing images, processes, networking, lifecycle, resources, and how Cloud Run dispatches work to a container. Understanding this contract helps you choose correctly between a **service**, **job**, and **worker pool**, while avoiding startup failures, ephemeral data loss, request timeouts, or unreliable background processing.

This lesson belongs to the **Cloud Run** chapter of the **CLOUD_PROVIDERS_GCP** module, connecting to project/IAM/VPC design, Java deployment, storage, databases, CI/CD, fault tolerance, and cost. The content focuses on the **execution contract and code requirements**, without repeating full Google Cloud architecture guides.

After this lesson, you can:

- Choose the right Cloud Run resource for the workload type.
- Package a Linux/AMD64 image and write an HTTP server listening on `0.0.0.0:$PORT`.
- Distinguish timeouts, concurrency, autoscaling, CPU allocation, ephemeral filesystems, and shutdown behavior.
- Build a minimal Java application, test it with Docker, and deploy a service/job using `gcloud`.
- Use service identities, secrets, logs, and health checks properly.
- Diagnose startup errors, `504`s, OOMs, retries, network connectivity issues, and costs.

## 1. The Contract Depends on the Resource Type

| Criterion | **Cloud Run service** | **Cloud Run job** | **Cloud Run worker pool** |
|---|---|---|---|
| How it starts | HTTP request or event converted into a request | Create a job execution via schedule/command/API | Worker runs continuously while instances are allocated |
| What must the process do? | Open an HTTP server on the exact ingress port | Do the work, **exit when finished**, and return an exit code | Run a consumer/daemon; opening HTTP ingress is not required |
| Work completion | Return an HTTP response within the request timeout | `exit 0` for success, nonzero for failure | Self-manage processing and checkpoints; may be terminated |
| Scaling | Automatic or manual per configuration | Execution's task count and parallelism | **Manual scaling**, does not auto-scale on backlog |
| CPU | Per billing setting and instance lifecycle | Allocated while tasks are running | Allocated for the entire time instances are active |
| Best suited for | REST APIs, webhooks, HTTP/gRPC handlers | ETL, batch jobs, migrations with a defined end | Long-running Pub/Sub/Kafka pull consumers |

Cloud Run also currently offers **Cloud Run instances** for applications that need direct instance lifecycle control. That is a separate resource; this lesson focuses on the three types above because they best illustrate contract differences.

~~~mermaid
flowchart TD
  A["Need to run a container on Cloud Run"] --> B{"HTTP request/response?"}
  B -- Yes --> C["Service: listen on PORT, return response"]
  B -- No --> D{"Has a finite end?"}
  D -- Yes --> E["Job: process then exit 0 / nonzero"]
  D -- No --> F["Worker pool: continuous consumer, manual scale"]
~~~

**Do not use a service to run an unbounded batch at startup.** A service must be ready to receive requests; a job does not need an HTTP listener; a worker pool must be designed to handle restarts and message reprocessing.

## 2. General Requirements for Container Images

Cloud Run executes 64-bit Linux containers supporting the **Linux x86_64 ABI**. Multi-platform images must include a **`linux/amd64`** variant. Google Cloud accepts compliant Docker manifests and OCI images; source code can be written in Java, Go, Python, Node.js, or other languages.

| Requirement | Practical consequence |
|---|---|
| Linux/AMD64 image, proper ENTRYPOINT/CMD | ARM-only binaries or Windows containers will not run |
| Native/JNI libraries compatible with Linux x86_64 | Java apps using native libraries may fail even if the JVM starts |
| Runtime process stays alive and reports errors properly | Immediate process exit prevents the service from serving |
| UTF-8 compatible filenames inside the image | Avoids deploy errors caused by unsupported filename encodings |
| Does not require privileged containers/host kernel access | No `sudo`, filesystem mounting via syscalls, eBPF, or privileged Docker-in-Docker |
| Maintained image and dependencies | Pin versions/digests, scan for vulnerabilities, and avoid embedding credentials |

**Note on permissions:** running as user `root` inside an image **does not grant** root privileges on the Cloud Run host; the sandbox blocks host access and privilege escalation. For normal applications, you should still use a non-privileged user and a minimal image.

## 3. Service: Must Listen on `0.0.0.0:$PORT`

A Cloud Run **service** has one ingress container and optional **sidecar containers**. Cloud Run automatically injects the `PORT` environment variable into the **ingress container** (defaulting to 8080, configurable at deploy time). The ingress process must:

1. Read the port from `PORT` instead of hardcoding `8080`.
2. Bind to **`0.0.0.0`**, not only `127.0.0.1` or `localhost`.
3. Start listening within the allowed startup window after initializing required components.
4. Return an HTTP response within the request timeout limit.

~~~text
Client HTTPS
  → Google Cloud Run frontend (TLS termination)
  → HTTP/1 to ingress container: 0.0.0.0:$PORT
  → Java HTTP handler
  → response / status code / logs
~~~

Cloud Run **terminates TLS at the frontend layer** for HTTP/HTTPS and gRPC. The ingress container normally receives unencrypted HTTP; if **HTTP/2 end-to-end** is chosen, the application must handle **h2c** (HTTP/2 cleartext) rather than enabling HTTPS on the ingress port "for extra security." Between services, you still need **authentication/authorization** and appropriate ingress/network choices.

### Plain JDK Java: A Contract-Compliant HTTP Server

This example uses `com.sun.net.httpserver.HttpServer` (built into the JDK) to learn the contract without any framework. Filename **`App.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class App {
    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(
            System.getenv().getOrDefault("PORT", "8080")
        );

        HttpServer server = HttpServer.create(
            new InetSocketAddress("0.0.0.0", port), 0
        );
        ExecutorService pool = Executors.newFixedThreadPool(8);
        server.setExecutor(pool);

        server.createContext("/healthz", exchange -> {
            respond(exchange, 200, "ok");
        });
        server.createContext("/", exchange -> {
            respond(exchange, 200, "hello from Cloud Run");
        });

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("SIGTERM: stopping HTTP server");
            server.stop(1);
            pool.shutdown();
        }));

        server.start();
        System.out.println("Listening on 0.0.0.0:" + port);
    }

    private static void respond(
        HttpExchange exchange, int status, String body
    ) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=utf-8"
        );
        exchange.sendResponseHeaders(status, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }
}
~~~

The example specifies a **default for `PORT`** for local runs, while on Cloud Run it must use the injected value. With Spring Boot, you can typically configure `server.address=0.0.0.0` and `server.port=${PORT:8080}` in `application.properties`; for Quarkus, Micronaut, or other frameworks, verify the exact config property names.

**Common mistake:** the Dockerfile includes `EXPOSE 8080`, yet the app binds to `localhost:8080` or `8081`. `EXPOSE` only documents the port in the image; it does not make a process listen automatically and does not replace reading `PORT`.

## 4. Packaging with Docker and Testing Locally

A multi-stage Dockerfile keeps the runtime image containing only the JRE and bytecode. Example building `App.java` from Section 3 and `BatchApp.java` from Section 9:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY App.java BatchApp.java ./
RUN javac --add-modules jdk.httpserver -d /app App.java BatchApp.java

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app /app
USER 65532:65532
EXPOSE 8080
CMD ["java", "--add-modules", "jdk.httpserver", "-cp", "/app", "App"]
~~~

In the lab, save the two Java files and the Dockerfile in a **dedicated test directory**. If only testing the service, you can omit `BatchApp.java` from `COPY`/`javac`. For production, pin base image digests, verify dependencies/JDK, and run CVE scanning and provenance checks.

~~~bash
docker build --platform linux/amd64 -t cloudrun-contract:lab .

# Use port 9090 to prove the application reads PORT instead of hardcoding 8080.
docker run --rm -e PORT=9090 -p 9090:9090 cloudrun-contract:lab

# In another terminal:
curl -i http://localhost:9090/healthz
curl -i http://localhost:9090/
~~~

Expect both endpoints to return HTTP 200. Stop the container with `docker stop` and inspect the shutdown logs. **Local success does not prove that IAM, ingress, quotas, or VPC on Cloud Run are configured properly**; you must test after deploying.

## 5. Startup, Health Checks, and Shutdown

A Cloud Run service requires the ingress container to **start listening within 4 minutes** of instance startup; all containers in the instance must be healthy. If a Java app takes too long to download dependencies, connect to a database, or run migrations at startup, the revision may fail to become ready.

| Phase | What does Cloud Run do? | What must the application do? |
|---|---|---|
| **Startup** | Allocates CPU during startup; checks port or startup probe | Read config, open the right port, perform bounded warmup |
| **Serve** | Forwards HTTP requests, potentially concurrently | Handle concurrency safely, timeouts, cancellation |
| **Idle** | May scale down per configuration | Never treat local state as persistent |
| **Shutdown** | Sends `SIGTERM`, followed about **10 seconds** later by potential `SIGKILL` | Stop accepting new work, flush/checkpoint within limits |

Probes serve different purposes:

- **Startup probe** checks the startup process (TCP, HTTP, or gRPC depending on config). If unconfigured, a service defaults to a TCP port check.
- **Liveness probe** detects hung containers and can restart them. Do not turn a transient Cloud SQL failure into "every container must restart."
- **Readiness probe** tells Cloud Run to stop sending **new requests** to an unready instance and resume once the probe passes; distinct from liveness.

Health endpoints like `/healthz` must return quickly and safely; do not run migrations or heavy tasks inside them. For apps with sidecars (proxies/agents), configure **container startup order** and startup probes so the ingress container does not open its port before dependencies are ready.

**`SIGTERM` does not guarantee all requests finish processing.** Instances can be terminated due to scaling, rollouts, maintenance, or failures. For operations with side effects, use durable state, idempotency keys, and retries rather than relying solely on `shutdownHook`.

## 6. Service Request Timeout and Concurrency

### Request Timeout vs. Startup Timeout

A Cloud Run service has a **default request timeout of 5 minutes (300 seconds)**, configurable up to **60 minutes (3,600 seconds)**. This limit includes the time spent waiting for an instance to start up to serve the request. If exceeded, the frontend closes the connection and returns **HTTP 504**, but the container **may continue processing** the aborted request. That is a key reason to enforce idempotency and downstream timeouts.

~~~text
HTTP request → container processes → returns response before timeout
                     │
                     └── exceeded → Cloud Run 504 to client
                                        (process may still be running)
~~~

Do not design a client to retry a payment operation without an idempotency key after a `504`: the first attempt may have already written data. Use Cloud Tasks, Pub/Sub, or a job for long-running/asynchronous work instead of holding HTTP connections open too long; for connections longer than 15 minutes, documentation recommends designing clients capable of reconnecting/retrying.

### Concurrency Is **Per Instance**, Not Service-Wide

`--concurrency=20` allows at most **20 simultaneous requests per instance**. When traffic increases, Cloud Run can spin up additional instances within scaling settings and quotas. Default concurrency depends on deployment tooling and CPU configuration; set a deliberate value and verify it on the actual revision rather than relying on a memorized number.

| Concurrency | Common trade-off |
|---|---|
| **1** | Isolates requests and reduces RAM/CPU contention, but may require more instances |
| **10–40** | Reasonable starting point for typical Java APIs if thread pools and DB have capacity |
| **High** | Reduces instance count but increases pressure on heap, CPU, threads, and DB connections |

For example, a Java API with 2 GiB RAM where each request can allocate 50 MiB temporarily: at concurrency 40, **request data alone** can require around 2 GiB (not counting JVM heap, metaspace, thread stacks, and the writable filesystem). Therefore, you must measure heap, memory, and P95/P99 latency under realistic load.

Limits that should be tuned together:

- Application server thread pool and maximum active HTTP connections.
- HikariCP/DB pool size, Cloud SQL connection quotas, and request deadlines.
- Per-instance CPU/memory, `max-instances`, min instances, and client retries.
- Cold start speed and startup CPU boost for Java.

## 7. CPU, Background Work, and Ephemeral Filesystem

### CPU Allocation Differs Across Billing Settings

For Cloud Run services:

- **Request-based billing** (default): CPU is allocated primarily during request processing, startup, and shutdown. Once requests finish, background work may have its CPU heavily throttled.
- **Instance-based billing:** CPU is allocated for the entire instance lifecycle; suitable for some short out-of-request tasks, though instances can still be scaled down/restarted and are billed while idle.
- **Jobs** and **worker pools** receive CPU while tasks/instances are active according to each resource type's billing model.

**Anti-pattern:** an HTTP handler returns `202 Accepted` and spawns a Java thread that runs for hours processing a file. On a request-based service, that background thread may be CPU-throttled or killed when the instance disappears. The right approach is to **enqueue** the work into Pub/Sub/Cloud Tasks or trigger a Cloud Run job and let an independent worker process it.

### Writable Filesystem Is In-Memory and Ephemeral

Cloud Run allows writing to the container filesystem, but that data:

- Consumes **instance memory** and can cause container OOMs.
- May persist across requests on the **same instance**, but **vanishes** when the instance stops.
- Is **not synchronized** across instances or revisions.

For example, an app receiving a 300 MiB file, writing a 600 MiB temp file to `/tmp`, and using 500 MiB of heap can exceed memory limits even if the image is only tens of MiB. Clean up temp files in `try/finally` or use an **in-memory volume with a size limit**; for files needing durable storage, use Cloud Storage. When mounting Filestore/Cloud Storage is needed, use **Cloud Run managed volume mounts** rather than running `mount -t nfs` in a privileged container process.

| Data | Appropriate location |
|---|---|
| Small, regenerable temp files | `/tmp` with memory bounds and cleanup |
| User-uploaded images/PDFs | Cloud Storage with object access controls |
| Transactional data, locks, shared sessions | Cloud SQL/Firestore/Memorystore as required |
| Shared POSIX files | Filestore via volume integration when compatible |
| Secrets | Secret Manager via API or managed secret mounts |

**Never store user sessions or transaction counters solely in Java static variables.** A service can have multiple instances and scale to zero; shared state must live in external storage outside the container.

## 8. Environment Variables, IAM, and Networking

Cloud Run automatically injects certain environment variables; do not override runtime-reserved variables.

| Resource | Key auto-injected variables | Meaning |
|---|---|---|
| **Service (ingress container)** | `PORT` | Required port for the HTTP server |
| **Service** | `K_SERVICE`, `K_REVISION`, `K_CONFIGURATION` | Identifies the service/revision |
| **Job** | `CLOUD_RUN_JOB`, `CLOUD_RUN_EXECUTION` | Current job and execution |
| **Job** | `CLOUD_RUN_TASK_INDEX`, `CLOUD_RUN_TASK_COUNT`, `CLOUD_RUN_TASK_ATTEMPT` | Work partitioning and retry tracking |
| **Worker pool** | `CLOUD_RUN_WORKER_POOL`, `CLOUD_RUN_REVISION` | Identifies the worker pool/revision |

**Service access permissions:** every Cloud Run revision/job has a **runtime service account**. Use **Application Default Credentials (ADC)** in Google Cloud client libraries (e.g., `StorageOptions.getDefaultInstance()` in Java) to call Cloud Storage, Pub/Sub, Secret Manager, or Cloud SQL connectors; **never embed JSON keys in the image**.

- The **deployer** needs IAM permissions to update Cloud Run plus `iam.serviceAccounts.actAs` on the runtime service account.
- A user/system **calling** a private service needs `roles/run.invoker` (or equivalent permission) and an **ID token** with a valid audience.
- The **runtime service account** should only receive specific business permissions, such as Object Viewer on a bucket or Pub/Sub Publisher on a topic; `roles/run.invoker` does not substitute for data read permissions.
- Secrets are passed via **Secret Manager integration** or API; plain environment variables are generally unsuitable for storing sensitive passwords.

For Cloud SQL/private API connectivity, verify **two independent conditions**: (1) IAM/DB authentication and (2) networking/DNS/egress. Cloud Run **services/jobs** support **Direct VPC egress** per configuration; newer resource types may differ in Direct VPC ingress/egress support, so do not extrapolate from worker pool to service. Outbound TCP connections can be reset when underlying infrastructure changes; use timeouts, connection pools that validate stale connections, and bounded retries.

## 9. Job: Complete the Work and Exit with an Exit Code

A **Cloud Run job** does not serve HTTP requests. The container runs a command, processes work, and **terminates with `exit 0` on success** or **nonzero** on failure. There is no need to open `PORT` or run a web server. An execution can consist of multiple parallel tasks; **Cloud Run does not automatically split data** across tasks.

Job environment variables help partition datasets. The following example file **`BatchApp.java`** prints task information; a real application must process its assigned partition using idempotency keys and durable checkpoints:

~~~java
public class BatchApp {
    public static void main(String[] args) {
        int index = Integer.parseInt(
            System.getenv().getOrDefault("CLOUD_RUN_TASK_INDEX", "0")
        );
        int count = Integer.parseInt(
            System.getenv().getOrDefault("CLOUD_RUN_TASK_COUNT", "1")
        );
        int attempt = Integer.parseInt(
            System.getenv().getOrDefault("CLOUD_RUN_TASK_ATTEMPT", "0")
        );

        try {
            System.out.printf(
                "Processing partition %d/%d, attempt=%d%n",
                index, count, attempt
            );
            // In practice: read partition index; write results idempotently.
            // Do not rely solely on attempt to prevent duplicate writes.
        } catch (Exception ex) {
            System.err.println("Batch failed: " + ex.getMessage());
            System.exit(1);
        }
        // Successful completion of main -> exit code 0.
    }
}
~~~

Jobs have a **default task timeout of 10 minutes**; per current documentation it can be configured up to **168 hours**, though GPU tasks have separate limits (up to 12 hours in preview at the time of writing). **Task timeout applies per attempt**, not to the entire execution; failed tasks can be retried according to `max-retries`. Multi-hour jobs can be interrupted by maintenance or connection drops, so you must checkpoint and recover cleanly.

**For critical data:** use `CLOUD_RUN_TASK_INDEX` to partition work; store processed state in a database/object storage; avoid writing results only to `/tmp` before exiting. When `max-retries` is enabled, the same task index can re-run and must not create duplicate payments or records.

## 10. Worker Pool: Continuously Running Consumer

A **worker pool** suits applications pulling messages from Pub/Sub/Kafka or handling long-lived event streams **without HTTP request/response as the primary input**. The container runs its entrypoint as a consumer loop; probes can be configured to ensure worker/auxiliary containers remain healthy.

Unlike a service: **worker pools do not autoscale automatically on message count**. You must adjust instance counts manually or build external operational automation; by default there is one instance, and it can be set to 0 to stop. While instances are active, CPU is always allocated and **billed for the entire running duration**.

~~~text
Pub/Sub subscription / Kafka topic
            ↓ pull / poll
   Cloud Run worker pool (N instances)
            ↓
  Deserialize → process → durable commit → ACK
~~~

Consumers need **flow control**, retry/backoff, dead-letter handling, and idempotency. Upon receiving `SIGTERM`, stop polling new messages, prioritize acking already-committed messages, and let the queue reclaim unfinished work; the shutdown grace period is not a license to run an unbounded job.

If the workflow actually originates from an HTTP webhook, a service is usually simpler. If it needs to finish and exit or run on a schedule, use a job instead of a worker pool; if you need event delivery over HTTP to Cloud Run, you can use Pub/Sub push or Eventarc.

## 11. Build and Deploy a Service and Job in a Lab Project

The examples below build on `App.java`, `BatchApp.java`, and the Dockerfile from earlier sections. Assume an Artifact Registry repository **already exists**, along with billing, Cloud Run/Artifact Registry APIs, and a runtime service account with required permissions. Run only in an authorized test project.

~~~bash
PROJECT_ID="my-cloudrun-lab-project"
REGION="asia-southeast1"
REPO="apps"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/cloudrun-contract:v1"
RUNTIME_SA="run-app@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com

# Repository $REPO must be pre-created by platform/CI.
gcloud auth configure-docker "$REGION-docker.pkg.dev"
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"
~~~

### Deploy a Private Service

~~~bash
gcloud run deploy contract-api \
  --image="$IMAGE" \
  --region="$REGION" \
  --port=8080 \
  --cpu=1 \
  --memory=512Mi \
  --concurrency=20 \
  --timeout=60s \
  --max-instances=5 \
  --service-account="$RUNTIME_SA" \
  --no-allow-unauthenticated

gcloud run services describe contract-api \
  --region="$REGION" \
  --format="yaml(status.url,status.conditions,spec.template)"
~~~

Here `--port=8080` configures **the port Cloud Run sends requests to**, and Cloud Run injects `PORT=8080` into the ingress container. With the Java image above, if you change `--port=9090`, the app listens on 9090 without rebuilding.

Assuming the user has been granted `roles/run.invoker` on the service and is permitted to call the endpoint:

~~~bash
URL="$(gcloud run services describe contract-api \
  --region="$REGION" --format='value(status.url)')"

curl -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$URL/healthz"
~~~

If you get `401/403`, check Invoker IAM, the actual identity used to call, ID token audience, and ingress settings; **do not switch to `--allow-unauthenticated` to work around production IAM errors**.

### Deploy a Job from the Same Image

~~~bash
gcloud run jobs create contract-batch \
  --image="$IMAGE" \
  --region="$REGION" \
  --command=java \
  --args="-cp,/app,BatchApp" \
  --tasks=3 \
  --parallelism=2 \
  --max-retries=2 \
  --task-timeout=900s \
  --service-account="$RUNTIME_SA"

gcloud run jobs execute contract-batch \
  --region="$REGION" --wait

gcloud run jobs describe contract-batch --region="$REGION"
~~~

The command override makes the job run **`BatchApp`** instead of starting the `App` web server. Three tasks have indexes 0, 1, 2; at most two run simultaneously per `--parallelism=2`, and execution order is not guaranteed. Read logs by execution/task to verify `exit code`; `gcloud run jobs execute --wait` waits for the execution in the CLI and does not turn the job into an HTTP endpoint.

**Cost impact:** each deploy command creates appropriate revisions/resources; `--max-instances` caps service scaling but does not limit all costs incurred from storage, networking, or databases. Once the lab is done, check with the owner and clean up the service/job along with images/Artifact Registry resources properly.

## 12. Observing and Troubleshooting by Contract

Do not start by increasing CPU/RAM for every error. Identify whether the failure lies in the **image/process**, **HTTP contract**, **IAM**, **networking**, or **resources**.

| Symptom | Common cause | Correct check |
|---|---|---|
| Container fails to listen on `PORT` | Bound to `127.0.0.1`, hardcoded port, app crash, wrong JAR entrypoint | Startup logs; test `PORT=9090` locally |
| `exec format error` | Image/binary does not support `linux/amd64` | `docker build --platform linux/amd64`, inspect image manifest |
| Revision unhealthy | Slow startup, wrong probe path/port, sidecar not ready | Startup/liveness/readiness, dependency initialization |
| HTTP `504` | Request exceeded `--timeout`; slow DB/API or deadlock | Request latency, downstream timeouts, idempotency |
| HTTP `500` and instance disappears | OOM, application crash, process killed | Cloud Run logs, memory, heap, `/tmp` files |
| High CPU/P95 rises at high concurrency | Too many requests sharing one instance | Tune concurrency, JVM heap, thread/DB pools |
| `401/403` calling service | Missing valid ID token, missing Invoker, blocked by ingress | Caller IAM, audience, and ingress |
| `403` calling Cloud Storage | Runtime service account lacks bucket permissions | Resource IAM, ADC, audit logs |
| Cloud SQL timeout | Wrong VPC/connector/DNS, exhausted DB pool or stale connections | VPC egress, auth, DB metrics, connection pooling |
| Java background task incomplete | CPU throttled after HTTP response, instance scaled down | Billing mode; use queue/job/worker pool |
| Job execution failed | Nonzero exit, timeout, OOM, or task retries exhausted | Execution/task logs, exit code, `TASK_ATTEMPT` |
| Worker pool backlog growing | Manual scaling too low, consumer not acking, slow downstream | Subscription backlog, retry/DLQ, worker instance count |

### Investigation Commands

~~~bash
gcloud run services describe contract-api --region="$REGION"
gcloud run services logs read contract-api \
  --region="$REGION" --limit=50

gcloud run jobs describe contract-batch --region="$REGION"

# Cloud Logging / Monitoring Console:
# filter by service, revision, execution, error code, and deploy time.
~~~

Application logs should write to **stdout/stderr**, using structured JSON if correlating request ID, revision, latency, and errors. Never log full access tokens, secrets, or sensitive payloads. On `504`, verify whether downstream already committed successfully before retrying.

**Outbound connections also have a lifecycle:** per the runtime contract, idle outbound connections to a VPC can time out after **10 minutes**, to the Internet after **20 minutes**, and can be reset due to infrastructure updates. Java HTTP/DB clients must validate live connections, reconnect, and perform bounded retries; never assume an unverified TCP connection lives forever.

## 13. Cost, Safety, and Production Deployment

| Decision | Impact | Control |
|---|---|---|
| Request-based service | Suitable for discrete requests; background work after response is unreliable | Enqueue work before returning the response |
| Instance-based service | CPU can run outside requests, still terminated and billed per instance | Use only when truly needed; monitor idle time |
| Min instances | Reduces cold starts but keeps instances warm at a cost | Measure P95 latency; do not set needlessly high |
| High concurrency | Fewer instances but higher heap/thread/DB pressure | Load test and use circuit breakers |
| Jobs with retries | Recovers from transient errors, can repeat business actions | Idempotency and checkpoints |
| Worker pool | Fits continuous consumers; CPU/instances billed over running time | Manual scaling, monitor backlog |
| Large temp files | Consumes RAM, prone to OOM | Stream to Cloud Storage or bound temp usage |
| VPC, LB, logs, database | Incurs costs outside the container | Billing budgets, labels, quotas, and monitoring |

Several principles apply to **all** resource types:

- **Least-privilege runtime identity**, secrets via Secret Manager; never use long-lived service account keys.
- **Ingress as needed**: expose publicly only when genuinely required; otherwise use Invoker/IAM and appropriate network restrictions.
- **Never assume stable instances**: do not rely on local disk, process singletons, or static variables to hold business state.
- **Automate releases**: pin image tags/digests, scan for vulnerabilities, deploy revisions, verify health/SLOs, then shift traffic or roll back as needed.
- **Bound backend load**: size service max instances, concurrency, and application pools based on Cloud SQL/Redis capacity; autoscaling cannot fix a database bottleneck.
- **Track costs**: Cloud Billing budget alerts do not automatically stop all usage; consider capacity limits, quotas, and service-level cost controls.

## 14. Applied Scenario: Document Upload API and Asynchronous Processing

A Java application allows users to upload PDFs. Requirements: **fast API response**, large files need several minutes of OCR, and results must survive instance restarts.

~~~mermaid
flowchart LR
  U["Client"] --> S["Cloud Run service: upload API"]
  S --> O["Cloud Storage: raw documents"]
  S --> Q["Pub/Sub / Cloud Tasks"]
  Q --> W["Worker pool or push service"]
  W --> R["Cloud Storage: results + Cloud SQL status"]
  J["Scheduled Cloud Run job"] --> R
~~~

**Design:**

1. The service binds to `0.0.0.0:$PORT`, authenticates callers, enforces upload limits, and streams bytes into Cloud Storage; it returns `202` with a job ID **after successfully enqueueing**.
2. An independent consumer handles OCR. If choosing a **worker pool**, manage pull/ack/manual scaling yourself. If using **Pub/Sub push to a service**, the handler must finish within the request timeout and handle retries. If batch processing with a finite end, choose a **job**.
3. Outputs are written to Cloud Storage; status and idempotency keys are stored in Cloud SQL/Firestore. When a request or task is retried, the same job ID does not produce duplicate results.
4. Monitor API response latency on the service, processing delay/backlog on the queue, and per-task success/failure; do not treat "API returned 202" as OCR completion.
5. If using Cloud SQL private IP, configure Direct VPC egress, IAM/DB credentials, and connection pooling; do not just grant a role and assume networking works.

For these requirements, **do not** spawn a Java background thread to run OCR after the service returns `202` and write results to `/tmp`: neither CPU nor local state is guaranteed to survive until completion.

## 15. Checklist and Hands-On Exercises

### Deployment Checklist

- [ ] Select the right **service, job, or worker pool** for the workload.
- [ ] Image includes a `linux/amd64` variant, proper entrypoint, and requires no host privileges.
- [ ] Service reads `PORT` and binds `0.0.0.0`; job exits with proper codes; worker pool handles shutdown.
- [ ] Tested locally on a port **other than 8080** and verified `/healthz`.
- [ ] Timeouts, concurrency, CPU, memory, startup probes, and max/min instances chosen via measurement.
- [ ] No critical state stored in RAM or writable filesystem; temp files cleaned up.
- [ ] No long background work after response under request-based billing.
- [ ] Uses runtime service account + ADC; caller IAM and resource IAM verified separately.
- [ ] Secret Manager, VPC egress/ingress, and database connectivity verified.
- [ ] Logging and alerts configured for startup failures, `5xx`, P95, OOM, retries, backlog, and cost.
- [ ] Rollout, rollback, `SIGTERM` handling, idempotency, and cleanup have clear owners.

### Exercises

**Exercise 1 — Fix a startup error.** A Java app uses `new InetSocketAddress("127.0.0.1", 8080)`. Cloud Run deploys with `--port=9090` and the revision never becomes ready. Fix the code, rebuild a `linux/amd64` image, and list two local tests verifying contract compliance.

**Exercise 2 — Choose the resource.** Classify three workloads: an e-commerce REST API, a nightly report aggregation job, and a continuous Pub/Sub consumer. State the process lifecycle, scaling model, and completion condition for each.

**Exercise 3 — Calculate concurrency.** A service is configured with `--concurrency=20`, `--max-instances=5`. Compute the **nominal concurrent capacity** from these two parameters (20 × 5), then explain why it is **not** a throughput SLA, an absolute hard cap at all times, or a guarantee of always having 5 instances.

**Exercise 4 — `504` error and duplicate data.** A request finishes inserting an order into Cloud SQL but times out before returning the response. The client retries. Design an idempotency key/transaction so two orders are not created; state whether to adjust the request timeout or move to a queue when processing runs long.

**Exercise 5 — Memory and background work.** A container has 512 MiB RAM, the JVM uses 300 MiB, and a 350 MiB temp file is downloaded to `/tmp`. Describe the likely outcome, how to process via streaming, and why raising min instances does not solve temp data loss across restarts.

**Exercise 6 — Job retry.** Three Cloud Run job tasks process three data partitions. Task index 1 hits a network error and is retried. Choose an idempotency key, checkpoint location, and exit codes to use; explain the role of `CLOUD_RUN_TASK_INDEX` versus `CLOUD_RUN_TASK_ATTEMPT`.

## Official References

- [Cloud Run container runtime contract](https://cloud.google.com/run/docs/container-contract) — image, `PORT`, TLS, lifecycle, filesystem, signals, and resource differences.
- [Configure container port for services](https://cloud.google.com/run/docs/configuring/services/containers) — ingress port, sidecars, and runtime settings.
- [Request timeout for services](https://cloud.google.com/run/docs/configuring/request-timeout) — defaults, limits, and HTTP 504.
- [Concurrency for services](https://cloud.google.com/run/docs/about-concurrency) — multiple requests per instance and autoscaling.
- [Configure health checks](https://cloud.google.com/run/docs/configuring/healthchecks) — startup, liveness, and readiness probes.
- [Billing settings for services](https://cloud.google.com/run/docs/configuring/billing-settings) — request-based/instance-based CPU.
- [General development tips](https://cloud.google.com/run/docs/tips/general) — avoiding background tasks and managing temp files.
- [Create Cloud Run jobs](https://cloud.google.com/run/docs/create-jobs) — tasks, parallelism, and retries.
- [Set task timeout for jobs](https://cloud.google.com/run/docs/configuring/task-timeout) — maximum duration per task attempt.
- [Cloud Run worker pools](https://cloud.google.com/run/docs/worker-pools) — continuous consumers and manual scaling.
- [Cloud Run service identity](https://cloud.google.com/run/docs/securing/service-identity) — ADC and permissions to access Google Cloud APIs.
- [Cloud Run pricing](https://cloud.google.com/run/pricing) — service, job, worker pool, and related configuration costs.
