# Health indicators, readiness, and liveness for cloud dependencies

## 1. Context and objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services from **AWS, Azure, and Google Cloud** using the corresponding Spring Cloud libraries and SDKs. Beyond configuring identity, access permissions, storage, messaging, and secret protection, a production application also needs to tell the platform **whether it is running properly and whether it can receive traffic**.

Consider a Spring Boot API that stores documents in object storage and sends jobs to a message queue. The application may still be running when a cloud service experiences an outage, even though some requests cannot be fulfilled. If the platform only checks whether the process is alive, it will keep routing traffic to an instance that cannot serve requests. Conversely, if it restarts the process every time a single cloud call fails, the entire cluster could restart together and make the incident worse.

Spring Boot Actuator provides **HealthIndicator**, **health groups**, **liveness/readiness** states, and endpoints for platforms such as Kubernetes to probe. This lesson focuses on how to classify cloud dependencies appropriately, implement health indicators with timeouts, and choose suitable readiness conditions.

After this lesson, you will be able to:

- Distinguish **health**, **liveness**, **readiness**, and **startup probe**.
- Configure Spring Boot Actuator to expose probe endpoints for Kubernetes.
- Write a HealthIndicator that checks a critical cloud resource using a lightweight, time-bounded operation.
- Decide which AWS, Azure, or Google Cloud dependencies should be included in readiness.
- Avoid restart storms, load-inducing health checks, and sensitive information leaks.
- Test health endpoints, simulate dependency failures, and verify Kubernetes behavior.

## 2. Four concepts to distinguish

The terms “healthy”, “live”, and “ready” are often used interchangeably, yet they trigger different operational actions.

| Concept | Question | When it fails, what should the platform do? |
|---|---|---|
| **Health** | What state are the components reported by the application in? | Display status, support monitoring and diagnostics |
| **Liveness** | Is the process still in a state where it can keep running or self-recover? | Restart the instance if the broken state cannot self-recover |
| **Readiness** | Can the instance currently accept and handle traffic? | Temporarily stop sending traffic to the instance |
| **Startup** | Has the application completed the required startup phase? | Do not run liveness/readiness until startup succeeds; restart if failures exceed the threshold |

Examples:

- The application is deadlocked on a critical thread and cannot process requests: **liveness may be DOWN**.
- The application has just started and is loading configuration or warming caches: **readiness is not yet ACCEPTING_TRAFFIC**.
- Azure Blob Storage is having an outage, while the JVM, thread pool, and Spring context remain operational: **liveness stays UP**; readiness depends on whether Blob is a required dependency for all requests.
- A cache is unavailable, but the application falls back to the database: the cache may be **DOWN in overall health**, without necessarily bringing readiness DOWN.

**Health alone does not dictate Kubernetes actions.** It is the probe configuration that maps HTTP results to container restarts or stopping traffic routing.

## 3. Liveness: checking the application's own vitality

Liveness answers the question: **can the instance keep running?** This signal tells Kubernetes whether the container needs to be restarted.

Situations that may cause liveness to fail:

- The application enters an unrecoverable internal state, such as a critical component being permanently broken.
- A deadlock or severe fault stops the process from making progress.
- An internal state has been explicitly determined by the application as BROKEN with no way to recover in place.

Situations that should not automatically fail liveness:

- AWS S3, Azure Blob Storage, Google Cloud Storage, or a message broker is temporarily unreachable.
- DNS, external cluster networking, or a third-party API encounters an error.
- A shared database experiences an outage while the process itself continues functioning normally.
- An individual request times out or a circuit breaker opens.

If a cloud dependency fails and liveness goes DOWN across all instances at once, Kubernetes may restart the entire workload. New instances immediately call the same failing dependency, generating extra load and prolonging the outage. This is a **restart storm / cascading failure**.

Spring Boot models liveness based on the application's internal state. Once the ApplicationContext has initialized successfully, Spring Boot treats the application as live by default; application components can update LivenessState when they detect an unrecoverable internal error.

## 4. Readiness: checking ability to receive traffic

Readiness answers the question: **should this instance receive new requests right now?**

When readiness fails, Kubernetes marks the Pod as not ready and removes the Pod's address from the corresponding Service's EndpointSlice. The container keeps running; kubelet continues executing the readiness probe to detect when the instance can serve traffic again.

Readiness typically transitions to REFUSING_TRAFFIC in these cases:

- The application is starting up and has not finished mandatory initialization tasks.
- A connection to an instance-specific dependency is not ready yet.
- The instance is undergoing maintenance or actively draining traffic.
- The application is overloaded and applies a policy to temporarily reject new requests.
- A cloud dependency essential for **every request routed to the instance** is unavailable.

Readiness is an **instance-level** decision, not a blanket rule for the entire system. If only one API endpoint needs a cloud service, including that service in application-wide readiness can pull the entire instance out of traffic even while other endpoints continue working normally.

Examples:

| Dependency | Role in the application | Include in readiness? |
|---|---|---|
| Blob holding every document the API must read to serve its primary request | Mandatory for all requests on this workload | Potentially yes, if failure prevents the instance from serving that traffic |
| Cache with database fallback | Optional | Usually no |
| Queue used only by a single job-creation endpoint | Affects only one subset of requests | Consider splitting workloads/routes or returning controlled errors on that endpoint |
| Secondary email notification service | Can be retried asynchronously | No |
| Mandatory secret/config not yet loaded at startup | Cannot serve properly if missing | Keep readiness unready until initialization finishes |

If a shared dependency fails across all replicas, all Pods may become NotReady. The Kubernetes Service can then end up with zero endpoints, causing connections to the Service to fail instead of returning a controlled HTTP 503 from the application. Therefore, weigh readiness alongside circuit breakers, fallbacks, retry limits, and degraded service capabilities.

## 5. Startup probe: protecting long startup phases

An application may need time to:

- Initialize the Spring context and connection pools.
- Load required configuration or data.
- Run migrations/schema checks according to the designed workflow.
- Warm caches or load large models/datasets.
- Verify mandatory resources before accepting traffic.

If liveness checks start too early, Kubernetes may repeatedly restart the application before it finishes starting up. **Startup probes** solve this: until the startup probe succeeds, Kubernetes does not run the container's liveness and readiness probes.

When the startup probe exceeds failureThreshold consecutive failures, kubelet stops the container according to its restart policy. Startup probes suit long or unpredictable startup times; do not inflate liveness initialDelaySeconds indefinitely to mask an unstable startup.

~~~mermaid
flowchart TD
    A[Container starts] --> B[Startup probe]
    B -->|Not yet succeeded| C[Wait and probe again]
    C --> B
    B -->|Succeeded| D[Start liveness and readiness]
    D --> E{Liveness}
    E -->|Failed past threshold| F[Restart container]
    E -->|Succeeded| G{Readiness}
    G -->|Failed| H[Stop routing traffic to Pod]
    G -->|Succeeded| I[Pod receives traffic]
    H -->|Probe again| G
~~~

Startup, liveness, and readiness serve distinct goals. Startup protects the initialization phase; liveness detects internal faults that require a restart; readiness coordinates traffic throughout the container lifecycle.

## 6. Spring Boot Actuator Health endpoint

Add the Actuator dependency to your Spring Boot application:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Choose a Spring Boot version compatible with your project's Spring Cloud release train and AWS/Azure/GCP starters. Do not upgrade Actuator independently to a different major version from Spring Boot.

Default health endpoint:

~~~text
GET /actuator/health
~~~

When running in Kubernetes, Spring Boot Actuator provides two health groups:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

In Spring Boot 3.x, probe health groups are automatically enabled when the application is detected as running in Kubernetes. You can enable them explicitly in any environment with `management.endpoint.health.probes.enabled=true`, which is useful for local testing or other deployment platforms.

Example minimal response:

~~~json
{
  "status": "UP"
}
~~~

If showing components/details is permitted, the response may include additional information:

~~~json
{
  "status": "UP",
  "components": {
    "livenessState": {
      "status": "UP"
    }
  }
}
~~~

Do not expose endpoint details, account names, buckets/containers, IAM errors, or exception messages to unauthorized users. Kubernetes probes only need a success/failure HTTP status code; operations teams can view details through secured monitoring channels.

## 7. Configuring health groups for Kubernetes

A basic Spring Boot 3.x configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: "readinessState,requiredBlobContainer"
~~~

Meaning:

- Only expose the health endpoint over HTTP.
- show-details and show-components avoid exposing internal data.
- probes.enabled explicitly enables the liveness/readiness health groups.
- add-additional-paths creates the /livez and /readyz endpoints on the **application's main HTTP port**.
- The readiness group includes readinessState and the requiredBlobContainer health indicator.

Spring Boot does not automatically include every external dependency in liveness/readiness. By default, these two groups focus on the application's availability state. Adding requiredBlobContainer is an intentional choice because this example assumes the Blob container is mandatory for the workload.

If you prefer not to use additional paths, Kubernetes can call /actuator/health/liveness and /actuator/health/readiness on the management port. However, if Actuator runs on a separate port/context, the health endpoint may still respond successfully even when the main web server cannot accept connections. Exposing probe paths on the main port checks closer to the actual traffic-serving path.

## 8. Writing a HealthIndicator for Azure Blob Storage

Spring Boot includes built-in health indicators for several components such as DataSource, MongoDB, Redis, RabbitMQ, and Elasticsearch. Do not assume every Azure/AWS/GCP SDK client automatically provides a suitable indicator. When you need to check a specific cloud resource, you can write a bean implementing HealthIndicator.

The example below uses Spring Boot 3.x and the Azure Blob SDK. It checks **a preconfigured container** using a time-bounded existence check:

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.BlobStorageException;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class RequiredBlobContainerHealthIndicator
        implements HealthIndicator {

    private final BlobContainerClient container;

    public RequiredBlobContainerHealthIndicator(
            BlobServiceClient blobServiceClient,
            @Value("${app.storage.required-container}") String containerName) {
        this.container =
                blobServiceClient.getBlobContainerClient(containerName);
    }

    @Override
    public Health health() {
        try {
boolean exists = container
                    .existsWithResponse(Duration.ofMillis(800), Context.NONE)
                    .getValue();

            if (!exists) {
                return Health.down()
                        .withDetail("dependency", "azure-blob")
                        .withDetail("reason", "required_container_missing")
                        .build();
            }

            return Health.up()
                    .withDetail("dependency", "azure-blob")
                    .build();
        } catch (BlobStorageException ex) {
            return Health.down()
                    .withDetail("dependency", "azure-blob")
                    .withDetail("reason", classify(ex.getStatusCode()))
                    .build();
        } catch (RuntimeException ex) {
            return Health.down()
                    .withDetail("dependency", "azure-blob")
                    .withDetail("reason", "request_failed")
                    .build();
        }
    }

    private String classify(int statusCode) {
        if (statusCode == 403) {
            return "authorization_failed";
        }
        if (statusCode == 404) {
            return "resource_not_found";
        }
        if (statusCode == 408 || statusCode == 429 || statusCode >= 500) {
            return "temporarily_unavailable";
        }
        return "storage_request_rejected";
    }
}
~~~

The default bean name is RequiredBlobContainerHealthIndicator. Spring Boot strips the HealthIndicator suffix to derive the ID requiredBlobContainer, so the YAML readiness group can include this exact ID.

This example assumes:

- BlobServiceClient has been configured with Spring Cloud Azure and Microsoft Entra ID / managed identity.
- The container has been pre-provisioned via IaC.
- The workload needs access to this container to serve its primary functionality.
- The identity holds sufficient data-plane permissions to read container status.

If the application uses a different Azure SDK version, check the timeout overloads of that SDK. Do not include exception messages, SAS URLs, account keys, or internal endpoints in Health details.

The imports in this example target **Spring Boot 3.x**. Spring Boot 4 moves health contributor types to the new package `org.springframework.boot.health.contributor`; when upgrading major versions, update imports and verify Spring Cloud release train compatibility before modifying code.

**Limitation of this check:** a successful existence/read-properties call proves the application can perform a metadata read operation with the current identity. It does not prove that uploads, downloads of every blob, or all business permissions work. Do not perform test writes/deletes on every probe just to prove write permission.

## 9. Resource configuration for the Azure example

Set the container name in application configuration:

~~~yaml
app:
  storage:
    required-container: documents
~~~

For Azure environments:

- Use managed identity instead of account keys whenever the service and operation support it.
- Assign the minimum required data-plane role to the application principal.
- Provision the container before deployment.
- Verify firewalls, private endpoints, and DNS from the workload's network.
- Configure Azure SDK timeouts/retries so total health check duration stays below the Kubernetes probe timeout.

The health indicator does not create the container if it is missing. If a mandatory container does not exist yet, returning DOWN keeps readiness from routing traffic to the instance until infrastructure is fixed. Creating resources inside a health check introduces side effects, risks races across multiple replicas, and hides deployment errors.

## 10. Check patterns for AWS and Google Cloud

The same principle applies across providers: **check a known resource using a lightweight, least-privilege, time-bounded operation**. Avoid calling APIs that list all resources just to prove credentials still work.

| Provider | Illustrative storage check | What it verifies |
|---|---|---|
| **AWS S3** | HeadBucket on a configured bucket | Bucket exists/is accessible with current permissions; IAM, region, or network errors |
| **Azure Blob** | BlobContainerClient.existsWithResponse | Whether the container exists and the identity can read metadata |
| **Google Cloud Storage** | Storage.get(bucketName) | Whether bucket metadata can be read with current credentials |
| **AWS SQS** | GetQueueAttributes on a configured queue | Queue exists and identity has permission to read attributes |
| **Azure Queue Storage** | QueueClient.getProperties() | Queue exists and client can read properties |
| **Google Pub/Sub** | Read subscription metadata via admin client | Subscription exists and identity has permission to access metadata |

Example metadata operation with AWS SDK for Java 2.x:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadBucketRequest;

public void checkBucket(S3Client s3, String bucketName) {
    s3.headBucket(HeadBucketRequest.builder()
            .bucket(bucketName)
            .build());
}
~~~

The client needs timeouts configured for both an entire API call and each attempt, such as `apiCallTimeout` and `apiCallAttemptTimeout` in ClientOverrideConfiguration. Calling the API without bounding duration can let a probe hang past kubelet's timeout.

Example reading bucket metadata with the Google Cloud Storage Java client:

~~~java
import com.google.cloud.storage.Bucket;
import com.google.cloud.storage.Storage;

public void checkBucket(Storage storage, String bucketName) {
    Bucket bucket = storage.get(bucketName);
    if (bucket == null) {
        throw new IllegalStateException("Required bucket is missing");
    }
}
~~~

The examples above show **SDK operations**, not complete production HealthIndicators. Wrap them in an indicator or adapter with timeouts and error classification, and include them in readiness only if that bucket/queue is genuinely mandatory for the workload.

## 11. Designing health checks for multiple cloud dependencies

An application may connect to multiple services: object storage, queues, databases, secret managers, and third-party APIs. Do not lump all of them into a single check where any failure makes the entire instance NotReady.

| Dependency category | Example | Appropriate placement |
|---|---|---|
| Mandatory for all primary requests | Transactional database or core object store | Readiness, if no viable fallback exists |
| Mandatory for a single route/job group | Queue serving only a job-creation endpoint | Separate health or workload-specific readiness; consider route-level failure |
| Has fallback/circuit breaker | Cache, auxiliary API | Overall health/metrics/alerts; usually excluded from readiness |
| Does not affect current requests | Email, background reports, analytics | Worker health and separate monitoring |
| Process internals | Stuck thread pool, corrupted local state | Liveness if unrecoverable |

If an application handles distinct workloads, consider splitting deployments:

- Document-reading API depending on Blob.
- Background processing worker depending on Queue and Blob.
- Notification worker depending on an email provider.

Each workload has its own readiness reflecting only the dependencies needed for its work. This prevents an email provider outage from stopping the document-reading API from receiving all traffic.

### 11.1. Do not probe the entire cloud account

A good health check should not:

- Call ListBuckets, list all containers, or list all queues every few seconds.
- Download a large blob or read all messages.
- Send a dummy message to a queue and immediately delete it.
- Create/delete resources to test permissions.
- Chain multiple API calls without timeout bounds.

Check a specific resource that the workload actually needs. Health checks should be **read-only, lightweight, low-side-effect, and safely repeatable**.

### 11.2. Readiness is not an all-permissions test

A successful metadata read does not prove the identity has write or delete permissions. If the workload needs to upload blobs, the actual write operation exercises write permission and returns an error if permissions are wrong. Do not create and delete a test file on every probe because that causes side effects and requires extra permissions.

Permissions should be verified separately via:

- Integration tests using principals/roles matching production.
- Verifying role assignments and scopes during deployment workflows.
- Metrics/logs from real operations.
- Scheduled synthetic tests if end-to-end verification is needed.

## 12. Timeouts, retries, caching, and probe-induced load

Kubernetes typically invokes readiness/liveness periodically. If each probe calls multiple cloud APIs, total request volume scales with replica count and probe frequency.

For example, with 40 replicas, each probing readiness every 5 seconds and checking 3 dependencies per probe: the system can generate roughly **24 dependency calls per second**, before counting retries and liveness. When the cloud slows down, retries can amplify load right when the service is already struggling.

Guidelines:

1. **Short, explicit timeouts:** SDK operations must finish before the probe's timeoutSeconds, leaving headroom for Spring to build the response.
2. **Limit retries:** health checks should not perform long retry loops; a check can use fewer attempts than business operations.
3. **Cache results briefly when needed:** a background sampler can refresh status every few seconds while probes read the latest state. Record the last check timestamp and avoid overly stale caches.
4. **Jitter:** avoid having all replicas call the dependency at the exact same moment after a deployment.
5. **Limit dependency count:** only check services that directly affect the workload's ability to serve.
6. **Decouple alerts from probes:** a dependency failure warrants alerting/observability, without necessarily restarting or removing instances.

If a health indicator is invoked directly, configure timeouts on the SDK client. For example, AWS SDK for Java 2.x supports overall API call timeout and per-attempt timeout; Azure SDK offers timeout overloads on many operations; Google Cloud clients use per-client/API timeout and retry settings. Do not rely on a single generic timeout while ignoring HTTP client timeouts and retry pipelines.

## 13. Updating readiness state from inside the application

Beyond health indicators, Spring Boot provides ApplicationAvailability and AvailabilityChangeEvent so the application can proactively update its state.

For example, when starting maintenance on an instance:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class MaintenanceReadiness {
    private final ApplicationEventPublisher publisher;

    public MaintenanceReadiness(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void stopAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    public void resumeTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

When readiness transitions to REFUSING_TRAFFIC, the readiness health group reflects that state and Kubernetes stops routing traffic to the Pod. Once maintenance finishes and the instance can handle requests again, publish ACCEPTING_TRAFFIC.

Only update readiness for conditions where the application truly should not receive requests. If a cloud API temporarily times out, it is usually better handled at the call site with timeouts/circuit breakers and controlled responses rather than marking the entire application NotReady.

Liveness state can also be updated via AvailabilityChangeEvent with LivenessState.BROKEN, but use this only when an unrecoverable internal error is detected. Do not set liveness to BROKEN because a single call to S3, Blob Storage, or Pub/Sub failed.

## 14. Configuring Kubernetes probes

Example Deployment using the paths exposed by Spring Boot Actuator on the main application port:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: document-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: document-api
  template:
    metadata:
      labels:
        app: document-api
    spec:
      containers:
        - name: app
          image: example/document-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 1
~~~

Explanation:

- The startup probe gives the application up to roughly 5 minutes in this example (30 attempts × 10 seconds, excluding per-request duration) to finish starting.
- The liveness probe checks /livez; three consecutive failures cause kubelet to restart the container.
- The readiness probe checks /readyz; two consecutive failures mark the Pod NotReady without restarting the container.
- When readiness recovers and the probe succeeds, the Pod can receive traffic again.

These numbers are starting examples and must be tuned to actual startup times, latency, and SLAs. Kubernetes defaults timeoutSeconds to 1 second; set it explicitly if the health endpoint has higher latency. Ensure the total processing time of the health group stays below the probe timeout budget.

### 14.1. If Actuator runs on a separate management port

If `management.server.port` is configured, probes can target that port. However, the health endpoint on the management server can still succeed even if the main server cannot accept connections or its traffic-serving thread pool is broken. For web applications, consider `management.endpoint.health.probes.add-additional-paths=true` so /livez and /readyz are served on the main port.

### 14.2. Securing endpoints

Probes must be reachable by kubelet. If Spring Security protects all endpoints, allow the probe paths within the appropriate network scope, without exposing the entire Actuator surface to the Internet. Expose only health—do not expose env, beans, configprops, or unnecessary administrative endpoints.

Do not return account info, subscriptions, buckets/containers, IAM principals, or detailed exceptions in public health endpoint bodies.

## 15. Testing health indicators and probes

Testing should cover both healthy operation and dependency failures.

| Scenario | Expected result |
|---|---|
| Spring context starts successfully | Liveness UP; readiness transitions to UP after startup tasks complete |
| Mandatory Blob container exists and metadata read succeeds | requiredBlobContainer indicator is UP |
| Mandatory container does not exist | Indicator DOWN; readiness DOWN if included |
| Identity lacks permission to read metadata | Indicator DOWN with classified reason; no exception/credential leak |
| Azure/AWS/GCP endpoint times out | Health check finishes within timeout; probe does not hang |
| Optional cache fails but has fallback | Readiness remains UP if cache is not a mandatory dependency |
| External dependency is down | Liveness remains UP |
| Application enters maintenance | Readiness transitions to REFUSING_TRAFFIC |
| Application performs graceful shutdown | Readiness stops receiving traffic before process exits |
| Health group runs on separate management port | Also verify main server path to avoid false-positive probes |

### 15.1. Unit testing the indicator

You can mock BlobContainerClient to verify mapping from SDK results to Health:

~~~java
import com.azure.core.http.rest.Response;
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class RequiredBlobContainerHealthIndicatorTest {
    @Test
    void reportsDownWhenContainerIsMissing() {
        BlobServiceClient service = mock(BlobServiceClient.class);
        BlobContainerClient container = mock(BlobContainerClient.class);
        @SuppressWarnings("unchecked")
        Response<Boolean> response = mock(Response.class);

        when(service.getBlobContainerClient("documents"))
                .thenReturn(container);
        when(container.existsWithResponse(any(Duration.class), any(Context.class)))
                .thenReturn(response);
        when(response.getValue()).thenReturn(false);

        RequiredBlobContainerHealthIndicator indicator =
                new RequiredBlobContainerHealthIndicator(service, "documents");

        assertEquals(Status.DOWN, indicator.health().getStatus());
    }
}
~~~

To let tests call the constructor directly as shown, the indicator's constructor accepts BlobServiceClient and the container name; the Value annotation is only for Spring injection. In full tests, also check the required_container_missing detail, UP status when the container exists, and DOWN when the SDK throws an exception.

### 15.2. Integration testing on real cloud

Azurite does not fully verify managed identity, RBAC, private endpoints, DNS, throttling, or production cloud behavior. For these requirements, use a test account and dedicated principal:

- Run tests with a managed identity or workload identity that has production-like roles.
- Verify a metadata/read operation against the real resource.
- Revoke or reduce the role in the test environment to confirm the indicator returns the expected failure.
- Verify the probe endpoint from inside the Pod/container via the main server port.
- Verify readiness when the dependency is temporarily blocked and then restored.

For AWS and Google Cloud, perform equivalent tests in a test account/project using a real IAM role/service account. Do not rely on emulators to conclude that cloud authorization is configured correctly.

## 16. Common design mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Putting all cloud dependencies in liveness | Shared dependency outage restarts all Pods | Liveness should reflect only unrecoverable internal faults |
| Putting every indicator in readiness | An auxiliary service outage blocks all API traffic | Include only dependencies truly mandatory for the workload |
| Health check listing all buckets/containers | Increases IAM permissions, cost, and latency | Check a known resource with a lightweight metadata API |
| Not configuring SDK timeouts | Probes hang or exceed kubelet timeout | Set appropriate total call and attempt timeouts |
| Too many retries in health indicator | Amplifies load while cloud is failing | Keep retries minimal; handle business retries in service layer |
| show-details: always on a public endpoint | Leaks endpoints, resource names, and security errors | Show details only to authorized users |
| Using a separate management port without checking main server | Probe UP while main port cannot serve requests | Use additional paths on the main port when appropriate |
| Using readiness instead of alerts | Operations unaware of dependency degradation | Create separate metrics/logs/alerts for dependencies |
| Putting a single route's dependency in Pod-wide readiness | Unrelated routes stop receiving traffic too | Split workloads or handle errors per route/circuit breaker |
| Not testing when all replicas are NotReady | Service may lose all endpoints and clients get no HTTP response | Design degraded mode and test cluster-wide outages |

## 17. Hands-on exercises and self-check questions

**Scenario A — Blob Storage outage:** An API has three replicas, all reading from Azure Blob Storage. Azure temporarily times out for 2 minutes. Determine which of liveness/readiness should fail, set SDK timeouts, and explain how to avoid a restart storm.

**Scenario B — Cache with fallback:** Redis/ElastiCache/Memorystore fails, but the application can read from the database. Decide whether to include the cache in readiness and design alerts/circuit breakers.

**Scenario C — Worker and API:** The API only sends messages to a queue; the worker consumes from the queue. Identify which dependencies belong in the readiness of the API versus the worker, avoiding unnecessary checks.

**Scenario D — Slow startup:** An application needs 150 seconds to warm caches and load configuration. Configure a startup probe so liveness does not restart the container too early, while keeping readiness refusing traffic until initialization completes.

**Scenario E — Misconfigured permissions:** The Azure Blob indicator returns 403 in production even though local runs succeeded using an account key. Verify managed identity, data-plane roles, scope, and networking; explain why local testing does not prove production RBAC.

**Scenario F — Shared dependency failure:** All replicas depend on a single cloud service experiencing an outage. Evaluate the impact when readiness removes every Pod from the Service, and propose degraded responses/circuit breakers or workload separation.

### Self-check questions

1. **What does liveness answer?** Whether the instance is still in a state where it can keep running or self-recover.
2. **What does readiness answer?** Whether the instance should currently receive new traffic.
3. **What does a startup probe protect?** A long startup phase before liveness/readiness probes begin.
4. **Why shouldn't cloud dependencies be in liveness by default?** A dependency failure can cause Kubernetes to restart all replicas and trigger a cascading failure.
5. **Must every dependency be in readiness?** No; only dependencies mandatory for the workload without a suitable fallback.
6. **What should a HealthIndicator check?** A lightweight operation on a known resource, with timeouts and least-privilege permissions.
7. **Does a HealthIndicator prove all upload/download permissions?** No; it only proves the specific checked operation works.
8. **What does Kubernetes do when readiness fails?** Marks the Pod NotReady and stops sending traffic through the Service; the container keeps running.
9. **What happens when liveness fails past the threshold?** Kubelet restarts the container according to its restart policy.
10. **Why are separate alerts needed?** Probes coordinate instances; alerts inform humans that a dependency or system is degrading.

## 18. Summary

Spring Boot Actuator provides HealthIndicator, health groups, and application availability states so platforms can orchestrate instances. **Liveness** must reflect unrecoverable internal faults; **readiness** reflects ability to receive traffic; **startup probes** protect applications during long startup phases.

When integrating AWS, Azure, and Google Cloud, check only dependencies genuinely required by the workload, using a lightweight metadata operation, short timeouts, and least privilege. Do not let a single cloud service failure trigger a restart of the entire application. Combine readiness with circuit breakers, fallbacks, metrics, alerts, and real cloud integration tests so the system both recovers properly and provides reliable operational signals.

### Official references

- [Spring Boot 3.5 — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Application Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot 3.5 — HealthIndicator API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/health/HealthIndicator.html)
- [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Microsoft Learn — BlobContainerClient Java API](https://learn.microsoft.com/java/api/com.azure.storage.blob.blobcontainerclient)
- [AWS SDK for Java 2.x — Configure client timeouts](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html)
- [Google Cloud Storage Java — Storage API](https://cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
