# Task Queue and Notification Project with Pub/Sub and Cloud Tasks

An e-commerce application needs to send notifications after an order is confirmed. If the order API synchronously calls an email provider, provider errors or latency can stall the HTTP request. If it merely spawns a background thread inside Cloud Run and returns immediately, the work may be lost when the instance stops. This project combines **Pub/Sub** for event distribution and **Cloud Tasks** for dispatching HTTP work with rate limits, retries, and overload handling.

This is a Google Cloud hands-on lab using Java 21, Spring Boot, Cloud Run, Artifact Registry, IAM, and Cloud Monitoring. Learners build two separate services from **the exact same container image**:

- **event-router**: receives Pub/Sub push requests, validates data, and creates a Cloud Task.
- **notification-worker**: receives Cloud Tasks HTTP POST requests, simulates sending a notification, and returns success or failure status.

In this lesson, the Order Service is simulated via a publish command. Production systems need a transactional outbox, durable idempotency, real email/SMS provider integration, secret management, and end-to-end monitoring.

## 1. Objectives and Acceptance Criteria

After completing this lesson, you will be able to:

1. Distinguish Pub/Sub fan-out events from Cloud Tasks directed HTTP work.
2. Create a Pub/Sub topic, authenticated push subscription, and dead-letter topic.
3. Create a Cloud Tasks queue with max dispatch rate, concurrency, and retry policy.
4. Configure Cloud Run IAM so only authorized workload identities can invoke services.
5. Write Java/Spring Boot code to receive Pub/Sub envelopes and Base64-decode payloads.
6. Create Cloud Tasks with OIDC tokens, root service audience, and deterministic task names.
7. Design acknowledgements, retries, poison message handling, and deduplication.
8. Test the happy path, auth errors, 503s, redelivery, and Cloud Tasks retry exhaustion.
9. Read logs, metrics, costs, and clean up resources after the lab.

**Outcome:** an `OrderCreated` event is pushed by Pub/Sub into `event-router`, the router enqueues a Cloud Task, Cloud Tasks invokes `notification-worker` with OIDC, and the worker logs a simulated send and returns HTTP 204.

Commands in this document are examples for learners to execute **on an approved lab project**; no commands were executed while authoring this lesson.

## 2. Architecture and Responsibility Layers

~~~text
        Order Service (simulated via gcloud pubsub publish)
                             |
                             v
                   Pub/Sub order-events
                             |
                             v
           Authenticated push order-events-push
                             |
                  OIDC: pubsub-push SA
                             |
                             v
                Cloud Run: event-router
                  Spring profile=router
                             |
                   Cloud Tasks API call
                   identity=router-runtime
                             |
                             v
           Queue: notification-delivery
            max rate=5/s, concurrency=10
                             |
                   HTTP POST + OIDC token
                   identity=tasks-caller
                             |
                             v
                 Cloud Run: notify-worker
                  Spring profile=worker
                             |
                             v
                 SIMULATED notification
                             |
                            204

        Push failure -> Pub/Sub retry -> Pub/Sub DLQ
        Task failure -> Cloud Tasks retry -> deleted after policy exhaustion
                                          -> failure ledger required
~~~

| Component | Responsibility | Not Guaranteed |
|---|---|---|
| Pub/Sub topic | Fans out business events to multiple subscriptions | Exactly-once for push |
| Push subscription | Sends HTTP requests, retries if un-ACKed | Side-effect completion after receiving 2xx |
| event-router | Validates and enqueues tasks | Sending real emails, permanent deduplication |
| Cloud Tasks | Queues, rate limits, scheduling, and HTTP retries | Pub/Sub-style DLQ |
| notification-worker | Executes side effect and ACKs | Exactly-once without idempotency |
| Cloud Run IAM | Platform-level service-to-service AuthN/AuthZ | Per-customer/tenant permissions |
| Monitoring | Tracks backlog, failures, retries | Automatic business recovery |

**When is combining both unnecessary?** If you only need a single HTTP job targeting one worker, Cloud Tasks alone is simpler. If you only need to fan out events to multiple consumers without per-target HTTP dispatch rate limits, Pub/Sub alone may suffice.

## 3. At-Least-Once Delivery and Two ACK Points

Pub/Sub push treats HTTP status 102, 200, 201, 202, or 204 as an acknowledgement. Other status codes or timeouts can trigger redelivery.

Cloud Tasks treats HTTP **2xx** from the handler as task completion. Non-2xx codes, timeouts, or connection errors can cause the task to be retried according to the queue policy.

In this design:

- The router **ACKs Pub/Sub only after Cloud Tasks confirms task creation** or when Cloud Tasks reports a task with the same business `eventId` already exists.
- The worker **ACKs Cloud Tasks only after processing succeeds** per business rules.
- In this lab, the worker only writes logs, so ACK confirms **simulated processing**, not that a real email was sent.

A 204 response can be lost on the network even though the operation completed. Pub/Sub or Cloud Tasks may therefore redeliver. Queues alone never guarantee exactly-once side effects.

### Two Layers of Deduplication

1. **Enqueue dedup:** Cloud Tasks task names derived from `eventId` prevent duplicate creation within the task-name retention window.
2. **Business idempotency:** a unique `eventId` in Cloud SQL/Firestore or an email provider idempotency key prevents resending even if an HTTP request is dispatched again.

Cloud Tasks has a finite task-name deduplication window (typically up to 24 hours for API queues); do not treat it as a substitute for a durable business ledger.

## 4. Preparing the Project and Budget

Prerequisites:

- A dedicated Google Cloud lab project with billing enabled.
- Permissions to enable APIs and create Cloud Run, Pub/Sub, Cloud Tasks, Artifact Registry, and IAM resources.
- Cloud Shell Bash or a machine with `gcloud` CLI; Java 21 and Maven 3.9+ if building locally.
- A region supporting these services, such as **asia-southeast1**.
- Budget, cost alerts, and a post-lab cleanup plan.

Commands below target **Bash in Cloud Shell**; on Windows PowerShell, adjust variable declarations and quoting.

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"

export REPO="notifications-lab"
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/notification-demo:v1"

export TOPIC="order-events"
export DLQ_TOPIC="order-events-dlq"
export PUSH_SUB="order-events-push"
export DLQ_SUB="order-events-dlq-read"
export QUEUE="notification-delivery"

export ROUTER_SA="router-runtime@$PROJECT_ID.iam.gserviceaccount.com"
export WORKER_SA="worker-runtime@$PROJECT_ID.iam.gserviceaccount.com"
export PUBSUB_PUSH_SA="pubsub-push@$PROJECT_ID.iam.gserviceaccount.com"
export TASKS_CALLER_SA="tasks-caller@$PROJECT_ID.iam.gserviceaccount.com"
~~~

Check the project, account, and project number before creating anything:

~~~bash
gcloud config set project "$PROJECT_ID"
gcloud auth list
gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)"
~~~

Never run commands that modify or delete resources in a production project.

## 5. Enabling APIs and Creating the Artifact Registry Repository

~~~bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  pubsub.googleapis.com \
  cloudtasks.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID"

gcloud artifacts repositories create "$REPO" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --repository-format=docker \
  --description="Docker images for notifications lab"
~~~

If the repository already exists, verify its location and ownership. The Cloud Build service account needs appropriate Artifact Registry Writer permissions; scope them to the repository rather than the whole project whenever possible.

## 6. Creating Identities and IAM Responsibilities

~~~bash
gcloud iam service-accounts create router-runtime \
  --project="$PROJECT_ID" \
  --display-name="Router Cloud Run runtime"

gcloud iam service-accounts create worker-runtime \
  --project="$PROJECT_ID" \
  --display-name="Worker Cloud Run runtime"

gcloud iam service-accounts create pubsub-push \
  --project="$PROJECT_ID" \
  --display-name="PubSub push invoker"

gcloud iam service-accounts create tasks-caller \
  --project="$PROJECT_ID" \
  --display-name="Cloud Tasks HTTP invoker"
~~~

| Identity | Required Permission |
|---|---|
| `router-runtime` | Cloud Tasks Enqueuer on the specific queue |
| `worker-runtime` | Permissions to call provider/Secret Manager when integrated for real |
| `pubsub-push` | Cloud Run Invoker on `event-router` |
| `tasks-caller` | Cloud Run Invoker on `notify-worker` |
| Pub/Sub service agent | Mint tokens for `pubsub-push`, forward to DLQ |
| Cloud Tasks service agent | Mint OIDC tokens for `tasks-caller` |
| Deployer | Deploy permissions and scoped `iam.serviceAccounts.actAs` |

Do not use a single service account with project-wide Owner across every step. Anyone creating a push subscription or enqueueing tasks with OIDC may need **`iam.serviceAccounts.actAs`** on the specified identity. Additionally, Google-managed service agents need their own permissions to mint tokens.

## 7. Creating Pub/Sub Topics and the Cloud Tasks Queue

~~~bash
gcloud pubsub topics create "$TOPIC" \
  --project="$PROJECT_ID"

gcloud pubsub topics create "$DLQ_TOPIC" \
  --project="$PROJECT_ID"

gcloud tasks queues create "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --max-dispatches-per-second=5 \
  --max-concurrent-dispatches=10 \
  --max-attempts=8 \
  --min-backoff=10s \
  --max-backoff=300s \
  --max-retry-duration=3600s
~~~

The queue enforces a steady-state dispatch limit of at most 5 tasks/s and 10 concurrent dispatches, including retries. Cloud Tasks may ramp up gradually when a queue is newly created/resumed or after many 429/5xx responses; these numbers are not a throughput SLA.

Grant Enqueuer solely on the queue:

~~~bash
gcloud tasks queues add-iam-policy-binding "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --member="serviceAccount:$ROUTER_SA" \
  --role="roles/cloudtasks.enqueuer"
~~~

Inspect:

~~~bash
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$REGION"
~~~

## 8. One Maven Project, Two Spring Profiles

~~~text
notification-demo/
  pom.xml
  Dockerfile
  src/main/resources/application.yml
  src/main/java/com/example/notifications/
    NotificationDemoApplication.java
    OrderCreated.java
    PubSubPushEnvelope.java
    CloudTasksConfig.java
    TaskEnqueuer.java
    EventRouterController.java
    NotificationWorkerController.java
~~~

Use Spring Boot profile **router** or **worker** so the two Cloud Run services instantiate only the controllers they need while sharing the same image.

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>notification-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>

  <properties>
    <java.version>21</java.version>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>libraries-bom</artifactId>
        <version>26.73.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-tasks</artifactId>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Versions are illustrative. In real deployments, pin versions supported by your organization, scan for vulnerabilities, and run tests.

### application.yml

~~~yaml
server:
  port: ${PORT:8080}

spring:
  application:
    name: notification-demo

app:
  project-id: ${APP_PROJECT_ID:}
  queue-location: ${APP_QUEUE_LOCATION:asia-southeast1}
  queue-id: ${APP_QUEUE_ID:notification-delivery}
  worker-base-url: ${APP_WORKER_BASE_URL:}
  task-caller-service-account: ${APP_TASK_CALLER_SERVICE_ACCOUNT:}
~~~

### NotificationDemoApplication.java

~~~java
package com.example.notifications;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NotificationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(NotificationDemoApplication.class, args);
    }
}
~~~

Cloud Run sets **`SPRING_PROFILES_ACTIVE=router`** or **`worker`**. The queue/project/worker URL variables are only needed for the `router` profile.

## 9. OrderCreated Event and Pub/Sub Push Envelope

`OrderCreated` contains only essential fields—never access tokens, passwords, or payment cards.

### OrderCreated.java

~~~java
package com.example.notifications;

public record OrderCreated(
    String eventId,
    String orderId,
    String recipientId,
    String template
) {}
~~~

Illustrative event:

~~~json
{
  "eventId": "evt-order-1001",
  "orderId": "ORDER-1001",
  "recipientId": "customer-demo-42",
  "template": "ORDER_CONFIRMED"
}
~~~

### PubSubPushEnvelope.java

Pub/Sub push defaults to sending a **JSON envelope**, in which `message.data` is the Base64-encoded payload rather than raw `OrderCreated` JSON.

~~~java
package com.example.notifications;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PubSubPushEnvelope(
    PubSubMessage message,
    String subscription
) {
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record PubSubMessage(
        String data,
        String messageId
    ) {}
}
~~~

Fields such as `attributes`, `publishTime`, and `deliveryAttempt` may also be present but are not required for the demo. If **no-wrapper push** is enabled, the controller's request body contract must change.

## 10. Managing CloudTasksClient in Spring

### CloudTasksConfig.java

~~~java
package com.example.notifications;

import com.google.cloud.tasks.v2.CloudTasksClient;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class CloudTasksConfig {
    @Bean(destroyMethod = "close")
    @Profile("router")
    CloudTasksClient cloudTasksClient() throws IOException {
        return CloudTasksClient.create();
    }
}
~~~

The client uses Application Default Credentials (ADC) bound to Cloud Run's `router-runtime` identity. Do not create a new client per push request. Spring closes the client on context shutdown.

## 11. Java TaskEnqueuer: Task Name and OIDC

### TaskEnqueuer.java

~~~java
package com.example.notifications;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.tasks.v2.CloudTasksClient;
import com.google.cloud.tasks.v2.HttpMethod;
import com.google.cloud.tasks.v2.HttpRequest;
import com.google.cloud.tasks.v2.OidcToken;
import com.google.cloud.tasks.v2.QueueName;
import com.google.cloud.tasks.v2.Task;
import com.google.protobuf.ByteString;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

@Service
@Profile("router")
public class TaskEnqueuer {
    private final CloudTasksClient client;
    private final ObjectMapper mapper;
    private final String queuePath;
    private final String workerBaseUrl;
    private final String taskCallerServiceAccount;

    public TaskEnqueuer(
            CloudTasksClient client,
            ObjectMapper mapper,
            @Value("${app.project-id}") String project,
            @Value("${app.queue-location}") String location,
            @Value("${app.queue-id}") String queueId,
            @Value("${app.worker-base-url}") String workerBaseUrl,
            @Value("${app.task-caller-service-account}") String taskCallerServiceAccount) {
        this.client = client;
        this.mapper = mapper;
        this.queuePath = QueueName.of(project, location, queueId).toString();
        this.workerBaseUrl = workerBaseUrl;
        this.taskCallerServiceAccount = taskCallerServiceAccount;
    }

    public String enqueue(OrderCreated event) throws JsonProcessingException {
        String taskId = "notify-" + hashId(event.eventId());

        OidcToken oidc = OidcToken.newBuilder()
            .setServiceAccountEmail(taskCallerServiceAccount)
            .setAudience(workerBaseUrl)
            .build();

        HttpRequest request = HttpRequest.newBuilder()
            .setHttpMethod(HttpMethod.POST)
            .setUrl(workerBaseUrl + "/tasks/send-notification")
            .putHeaders("Content-Type", "application/json")
            .setBody(ByteString.copyFrom(mapper.writeValueAsBytes(event)))
            .setOidcToken(oidc)
            .build();

        Task task = Task.newBuilder()
            .setName(queuePath + "/tasks/" + taskId)
            .setHttpRequest(request)
            .build();

        return client.createTask(queuePath, task).getName();
    }

    private static String hashId(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest).substring(0, 32);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

Explanation:

- Router runtime uses IAM **Cloud Tasks Enqueuer** to create tasks, while the `tasks-caller` service account is used to mint OIDC tokens when tasks are dispatched.
- The target URL includes the `/tasks/send-notification` path, whereas the **audience is the worker's root URL**.
- The task name is based on a hash of the business `eventId`, avoiding sequential IDs or PII.
- Cloud Tasks returns `ALREADY_EXISTS` if a task with the same name still exists or recently executed; this reduces duplicate enqueues within a bounded window.
- Explicit task names incur more lookup overhead than auto-generated names; benchmark under high throughput.

Never use the event body to pick the target URL. Letting senders dictate task URLs introduces SSRF risk and leaks tokens to untrusted destinations.

## 12. Router ACKs Only After Enqueue Succeeds

### EventRouterController.java

~~~java
package com.example.notifications;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.api.gax.rpc.AlreadyExistsException;
import com.google.api.gax.rpc.ApiException;
import java.util.Base64;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("router")
public class EventRouterController {
    private final ObjectMapper mapper;
    private final TaskEnqueuer enqueuer;

    public EventRouterController(ObjectMapper mapper, TaskEnqueuer enqueuer) {
        this.mapper = mapper;
        this.enqueuer = enqueuer;
    }

    @PostMapping("/events/orders")
    public ResponseEntity<Void> receive(@RequestBody PubSubPushEnvelope body) {
        if (body == null || body.message() == null
                || body.message().data() == null) {
            return ResponseEntity.badRequest().build();
        }

        try {
            byte[] bytes = Base64.getDecoder().decode(body.message().data());
            OrderCreated event = mapper.readValue(bytes, OrderCreated.class);

            if (event == null || event.eventId() == null || event.eventId().isBlank()
                    || event.orderId() == null || event.orderId().isBlank()
                    || event.recipientId() == null || event.recipientId().isBlank()
                    || event.template() == null || event.template().isBlank()) {
                return ResponseEntity.badRequest().build();
            }

            enqueuer.enqueue(event);
            return ResponseEntity.noContent().build();
        } catch (AlreadyExistsException duplicate) {
            return ResponseEntity.noContent().build();
        } catch (JsonProcessingException | IllegalArgumentException invalid) {
            // Invalid payload: Pub/Sub retries and may move to DLQ.
            return ResponseEntity.badRequest().build();
        } catch (ApiException apiFailure) {
            // Task creation not confirmed: DO NOT ACK Pub/Sub.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }
    }
}
~~~

Pub/Sub treats 204 as an ACK. When the Cloud Tasks API fails, the router returns 503 so Pub/Sub redelivers. For invalid payloads, this simple sample returns 400 and relies on the Pub/Sub DLQ; production should quarantine explicitly instead of retrying unfixable schemas endlessly.

Catching `ALREADY_EXISTS` deduplicates **within the task-name window**, and does not guard against duplicates days later or when upstream assigns inconsistent `eventId` values.

## 13. Worker Simulates Sending Notifications

### NotificationWorkerController.java

~~~java
package com.example.notifications;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("worker")
public class NotificationWorkerController {
    private static final Logger log =
        LoggerFactory.getLogger(NotificationWorkerController.class);

    @PostMapping("/tasks/send-notification")
    public ResponseEntity<Void> deliver(@RequestBody OrderCreated event) {
        if (event == null || event.eventId() == null
                || event.orderId() == null || event.recipientId() == null) {
            return ResponseEntity.badRequest().build();
        }

        if ("FAIL-DEMO".equals(event.orderId())) {
            log.warn("Simulated transient notification failure");
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }

        // Simulation only, DO NOT call a real email/SMS provider.
        log.info("SIMULATED notification accepted eventId={}", event.eventId());
        return ResponseEntity.noContent().build();
    }
}
~~~

Cloud Tasks deletes the task when the worker returns 2xx. If the worker returns 503, Cloud Tasks retries according to max attempts/duration and backoff. HTTP 400 is also non-2xx, so poison tasks are not automatically skipped. In production, record permanent failure states in a failure ledger and handle them deliberately.

Never trust `X-CloudTasks-TaskName` or `RetryCount` headers as proof of authentication. Cloud Run IAM/OIDC authenticates the caller; the application still needs business authorization.

## 14. Packaging a Single Container Image

### Dockerfile

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml ./
COPY src/ ./src/
RUN mvn -B -ntp -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/target/notification-demo-0.0.1-SNAPSHOT.jar /app/app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

`-DskipTests` is used here only to focus on lab deployment; production CI must run tests, security scans, and record image digests. Never put credentials inside Dockerfiles.

From the `notification-demo` directory:

~~~bash
gcloud builds submit --project="$PROJECT_ID" --tag="$IMAGE"
~~~

The image is stored in Artifact Registry. The same image can be deployed as either `router` or `worker` with different profiles and service accounts.

## 15. Deploying notify-worker First and Retrieving Its Root URL

The worker is deployed first so the router knows the endpoint to embed into Cloud Tasks:

~~~bash
gcloud run deploy notify-worker \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$IMAGE" \
  --service-account="$WORKER_SA" \
  --no-allow-unauthenticated \
  --ingress=all \
  --set-env-vars="SPRING_PROFILES_ACTIVE=worker"
~~~

Retrieve URL:

~~~bash
export WORKER_URL="$(gcloud run services describe notify-worker \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format='value(status.url)')"

echo "$WORKER_URL"
~~~

Setting `ingress=all` permits network routing to the Cloud Run service URL, **not unauthenticated invocation**. IAM Invoker is still enforced. Choosing internal ingress requires designing an appropriate topology for Cloud Tasks, not merely toggling one flag.

Grant Invoker to `tasks-caller` on the exact receiving service:

~~~bash
gcloud run services add-iam-policy-binding notify-worker \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$TASKS_CALLER_SA" \
  --role="roles/run.invoker"
~~~

Never grant `allUsers` or `allAuthenticatedUsers` on `notify-worker`.

## 16. Granting Cloud Tasks Service Agent Permission to Mint Tokens

Cloud Tasks has a Google-managed service agent:

~~~text
service-PROJECT_NUMBER@gcp-sa-cloudtasks.iam.gserviceaccount.com
~~~

Verify the agent holds the Cloud Tasks Service Agent role and works per project documentation. When needed, authenticated HTTP task guidance specifies granting Service Account User on the `tasks-caller` service account so the agent can mint the corresponding tokens:

~~~bash
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" \
  --format='value(projectNumber)')"

gcloud iam service-accounts add-iam-policy-binding "$TASKS_CALLER_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-cloudtasks.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
~~~

Do not re-grant permissions if IAM policies are already sufficient. The caller or runtime creating tasks with an OIDC identity must also satisfy `iam.serviceAccounts.actAs` permissions per Cloud Tasks requirements. Cloud Run deployers need `actAs` on `router-runtime` and `worker-runtime` per Cloud Run requirements.

## 17. Deploying event-router with Cloud Tasks Configuration

~~~bash
gcloud run deploy event-router \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$IMAGE" \
  --service-account="$ROUTER_SA" \
  --no-allow-unauthenticated \
  --ingress=all \
  --set-env-vars="SPRING_PROFILES_ACTIVE=router,APP_PROJECT_ID=$PROJECT_ID,APP_QUEUE_LOCATION=$REGION,APP_QUEUE_ID=$QUEUE,APP_WORKER_BASE_URL=$WORKER_URL,APP_TASK_CALLER_SERVICE_ACCOUNT=$TASKS_CALLER_SA"
~~~

Retrieve URL to configure Pub/Sub push:

~~~bash
export ROUTER_URL="$(gcloud run services describe event-router \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format='value(status.url)')"

echo "$ROUTER_URL"
~~~

Never let event payloads dictate the Cloud Tasks URL or OIDC audience. URLs must come from controlled deployment configuration to prevent server-side request forgery and token leakage.

## 18. Granting Pub/Sub Push Permissions and Creating the Subscription

Grant `pubsub-push` SA permission to invoke the router:

~~~bash
gcloud run services add-iam-policy-binding event-router \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$PUBSUB_PUSH_SA" \
  --role="roles/run.invoker"
~~~

The Pub/Sub service agent has the form:

~~~text
service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com
~~~

The agent must be allowed to mint OIDC tokens for `pubsub-push`. Newer projects usually include the Pub/Sub Service Agent role with the needed permission. If the current policy lacks it, after review grant Token Creator on that specific SA:

~~~bash
gcloud iam service-accounts add-iam-policy-binding "$PUBSUB_PUSH_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
~~~

The person creating the subscription also needs `iam.serviceAccounts.actAs` on the `pubsub-push` identity. Never fix IAM errors by making `event-router` unauthenticated.

### Creating the Authenticated Push Subscription

~~~bash
gcloud pubsub subscriptions create "$PUSH_SUB" \
  --project="$PROJECT_ID" \
  --topic="$TOPIC" \
  --push-endpoint="$ROUTER_URL/events/orders" \
  --push-auth-service-account="$PUBSUB_PUSH_SA" \
  --push-auth-token-audience="$ROUTER_URL" \
  --min-retry-delay=10s \
  --max-retry-delay=300s
~~~

Pub/Sub sends HTTP requests to the URL with path `/events/orders`. The token's OIDC audience is set to the **root URL** of the receiving Cloud Run service. If the audience is wrong, Cloud Run may reject the request even if the SA holds Invoker.

The push subscription here uses the default JSON wrapper; `no-wrapper` is disabled. Exponential backoff retry policy does not override other push backoff limits when an endpoint fails repeatedly.

## 19. Configuring the Pub/Sub Dead-Letter Topic

Cloud Tasks lacks a built-in Pub/Sub-style DLQ, whereas a Pub/Sub subscription can forward failing messages to a dead-letter topic after a best-effort number of delivery attempts.

Create a pull subscription so operators can inspect the DLQ:

~~~bash
gcloud pubsub subscriptions create "$DLQ_SUB" \
  --project="$PROJECT_ID" \
  --topic="$DLQ_TOPIC"
~~~

Grant the Pub/Sub service agent permission to publish to the dead-letter topic and subscribe to the source:

~~~bash
export PUBSUB_AGENT="service-$PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com"

gcloud pubsub topics add-iam-policy-binding "$DLQ_TOPIC" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$PUBSUB_AGENT" \
  --role="roles/pubsub.publisher"

gcloud pubsub subscriptions add-iam-policy-binding "$PUSH_SUB" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$PUBSUB_AGENT" \
  --role="roles/pubsub.subscriber"
~~~

Enable DLQ and cap attempts:

~~~bash
gcloud pubsub subscriptions update "$PUSH_SUB" \
  --project="$PROJECT_ID" \
  --dead-letter-topic="$DLQ_TOPIC" \
  --max-delivery-attempts=10
~~~

Verify:

~~~bash
gcloud pubsub subscriptions describe "$PUSH_SUB" \
  --project="$PROJECT_ID"
~~~

Pub/Sub may forward to the DLQ after slightly more or fewer attempts than configured due to best-effort mechanics. DLQ messages are re-wrapped with additional source metadata; do not treat a DLQ payload as an exact copy of the raw input event without unwrapping it first.

## 20. Testing the Happy Path: OrderCreated

Publish a simulated event via Cloud Shell:

~~~bash
gcloud pubsub topics publish "$TOPIC" \
  --project="$PROJECT_ID" \
  --message='{"eventId":"evt-order-1001","orderId":"ORDER-1001","recipientId":"customer-demo-42","template":"ORDER_CONFIRMED"}'
~~~

Expected flow:

1. Pub/Sub receives the event and sends a push envelope with an OIDC token.
2. Cloud Run IAM verifies `pubsub-push` SA holds Invoker on `event-router`.
3. Router Base64-decodes, validates fields, and calls the Cloud Tasks API.
4. Cloud Tasks accepts the task whose name hashes `eventId`.
5. Router returns 204; Pub/Sub ACKs the message.
6. Cloud Tasks dispatches a POST to the worker with `tasks-caller`'s OIDC token.
7. Cloud Run IAM verifies `tasks-caller` SA holds Invoker on `notify-worker`.
8. Worker writes the simulated log and returns 204; the task completes and is removed from the queue.

Check Cloud Run logs:

~~~bash
gcloud run services logs read event-router \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=30

gcloud run services logs read notify-worker \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=30
~~~

Simulated logs prove the handler ran, **not that a real email was sent**. Production should add trace/event correlation tying together `eventId`, task name, and provider response without logging tokens or PII.

## 21. Testing Duplicate Publish

Re-send an event with the **same `eventId`**:

~~~bash
gcloud pubsub topics publish "$TOPIC" \
  --project="$PROJECT_ID" \
  --message='{"eventId":"evt-order-1001","orderId":"ORDER-1001","recipientId":"customer-demo-42","template":"ORDER_CONFIRMED"}'
~~~

If the task was created or completed within Cloud Tasks' task-name retention window, `createTask` may return `ALREADY_EXISTS`. The router treats it as a duplicate task already created and ACKs Pub/Sub.

This mechanism **does not protect once the deduplication window expires**, nor does it stop Cloud Tasks from re-dispatching the same task if a worker response is lost. A real email-sending system needs a durable ledger keyed by business `eventId` and a provider idempotency key where supported.

### Why Choose Business eventId Over Pub/Sub messageId?

A Pub/Sub `messageId` stays constant when the same message is redelivered, whereas each publisher call re-emitting an event gets a new `messageId`. A business `eventId` enables deduplication across separate publishes of the same business event.

## 22. Testing Poison Messages and the Pub/Sub DLQ

Send an invalid message:

~~~bash
gcloud pubsub topics publish "$TOPIC" \
  --project="$PROJECT_ID" \
  --message='not-json'
~~~

The router fails to parse it and returns 400. Pub/Sub retries and, if DLQ/IAM are configured properly, moves it to the dead-letter topic near the attempt threshold.

Read the DLQ:

~~~bash
gcloud pubsub subscriptions pull "$DLQ_SUB" \
  --project="$PROJECT_ID" \
  --limit=5
~~~

Do not auto-ACK while investigating. Once root cause is recorded and a quarantine/replay plan is ready, acknowledge according to your runbook.

### Handling Guidelines

- If the schema is permanently invalid, never replay blindly.
- If the error stems from version incompatibility, upgrade the consumer and test before replaying.
- If payloads may contain secrets or sensitive data, restrict access to the DLQ.
- Track DLQ message count and oldest message age on dashboards.
- Assign an owner and a periodic triage/quarantine workflow.

## 23. Testing Cloud Tasks HTTP Retries

The worker returns HTTP 503 when `orderId` is `FAIL-DEMO`. Publish this event:

~~~bash
gcloud pubsub topics publish "$TOPIC" \
  --project="$PROJECT_ID" \
  --message='{"eventId":"evt-fail-demo-1","orderId":"FAIL-DEMO","recipientId":"customer-demo-42","template":"ORDER_CONFIRMED"}'
~~~

The router still creates the task and ACKs Pub/Sub. Cloud Tasks receives 503 from the worker and then retries per the queue's `max-attempts`/`max-retry-duration` and backoff settings.

Inspect the queue:

~~~bash
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$REGION"

gcloud tasks list \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --queue="$QUEUE"
~~~

`gcloud tasks list` requires `--queue` and `--location` as shown. Succeeded tasks disappear quickly from the list because Cloud Tasks deletes them upon completion.

### When Retries Are Exhausted

Cloud Tasks stops retrying and deletes the task once it hits max attempts, max retry duration, or retention limits. There is no automatic dead-letter topic equivalent to Pub/Sub DLQ. To avoid losing track of failures, the worker must record durable status and trigger alerts/a failure ledger outside the queue.

## 24. Designing Idempotency and a Failure Ledger for Production

A state machine model:

~~~text
OrderCreated
     |
     v
NotificationIntent(eventId unique)
     |
     v
   PENDING
     |
  claim/lease
     |
     v
   SENDING
    /    \
   v      v
 SENT   RETRYABLE_ERROR
           |
           v
         PENDING
           |
     retry budget exhausted
           |
           v
      PERMANENT_FAILED
~~~

Options:

| Option | Benefit | Limitation |
|---|---|---|
| Cloud Tasks task name | Short-term dedup at enqueue time | Does not stop duplicate dispatch or long-term replay |
| SQL unique index | Prevents multiple rows per `eventId` | Must handle leases/crashes between steps |
| Firestore document ID | Convenient durable ledger | Needs transactions and conditional updates |
| Provider idempotency key | Reduces duplicate external sends | Depends on provider API support |
| Transactional outbox | Avoids committing order while missing publish | Still needs an idempotent consumer |

Never write `SENT` before calling the provider and assume the email went out. If a crash happens between writing and calling the provider, the notification is lost. Conversely, the provider may finish sending while the response is lost, causing a retry to send twice. Good design pairs reconciliation with provider-side idempotency where available.

## 25. Service-to-Service Security

~~~text
Pub/Sub agent ---> OIDC token for pubsub-push SA
pubsub-push SA ---> Invoker event-router
router-runtime SA ---> Enqueuer notification-delivery queue
Cloud Tasks agent ---> OIDC token for tasks-caller SA
tasks-caller SA ---> Invoker notify-worker
worker-runtime SA ---> scoped secrets/provider API
~~~

Tests:

| Scenario | Expected |
|---|---|
| Call router from internet without token | Rejected by Cloud Run IAM |
| Use `tasks-caller` to call router | Rejected without Invoker |
| Use `pubsub-push` to call worker | Rejected without Invoker |
| Token with another service's audience | Rejected |
| Router loses `createTask` permission | Pub/Sub push is not ACKed |
| Task body contains foreign URL | Does not alter worker target |
| Spoofed `X-CloudTasks-TaskName` header | Does not bypass IAM authentication |

Use Secret Manager when integrating an email provider. Never place API keys inside Pub/Sub payloads or task bodies. Separate the runtime identity from the identity used to invoke Cloud Run.

## 26. Monitoring and SLOs for Queues

| Source | Metric | Question Answered |
|---|---|---|
| Pub/Sub | Undelivered messages | Is the router keeping up with producers? |
| Pub/Sub | Oldest unacked message age | Is a message stuck? |
| Pub/Sub | Push errors, DLQ count | Are there persistent IAM/schema failures? |
| Cloud Tasks | Queue depth, attempts, dispatch rate | Is the worker bottlenecked? |
| Cloud Tasks | 429/503, retry count | Is downstream overloaded? |
| Cloud Run | 5xx and p95/p99 request latency | Are router/worker stable? |
| Java | Heap, GC, thread/connection pools | Is there resource saturation? |
| Ledger | PENDING/SENT/FAILED | Are business notifications completing? |
| Billing | Pub/Sub/Tasks/Run/Logging | How much is a retry storm costing? |

Illustrative SLOs:

- Over 99.9% of valid events are enqueued successfully over the measurement window.
- Event-to-task enqueue p95 is under 3 seconds when healthy.
- Task processing p95 is under 60 seconds when the provider is available.
- Permanent notification failures stay below the threshold approved by the business owner.

These figures are for this exercise only, not automatic SLAs of Pub/Sub/Cloud Tasks. Correlate logs/traces with `eventId` and task name, while never using tokens or PII as metric labels.

## 27. Cost and FinOps

Potential cost sources include:

- Pub/Sub publish, delivery, retention, and dead-letter traffic.
- Cloud Tasks operations, retry attempts, and queue logging.
- Cloud Run CPU/memory/requests, plus min instances if configured.
- Artifact Registry images and Cloud Build.
- Logging/Monitoring retention.
- Database ledger, email provider, and egress when integrated for real.

~~~text
Cost per successful notification
  = (Pub/Sub + Cloud Tasks + Cloud Run + Logs
     + Ledger + Provider + Egress)
    / number of notifications actually delivered successfully
~~~

A task failing with 503 and retrying repeatedly generates extra HTTP requests and logs with zero business value. Optimize via rate limits, backoff, idempotency, DLQ/quarantine, and error monitoring instead of blindly adding worker instances.

Do not rely on fixed prices in articles; check the Google Cloud Pricing Calculator and current billing SKUs for your project and region.

## 28. Troubleshooting

| Symptom | Possible Cause | Check |
|---|---|---|
| Pub/Sub push 401/403 | SA missing Invoker or wrong token/audience | Pub/Sub push config, Cloud Run IAM, service agent |
| Router 503 | Cloud Tasks API/IAM/quota error | Queue policy, runtime identity, logs |
| Task HTTP 401/403 | `tasks-caller` missing Invoker or wrong audience | OIDC config and worker service URL |
| Task not dispatching | Queue paused, backoff, rate limit, `scheduleTime` | Queue state, tasks, metrics |
| Event redelivered repeatedly | Router returned non-2xx or 204 lost | HTTP logs, task-name dedup |
| Duplicate notifications sent | Missing durable idempotency | Business ledger and provider request ID |
| DLQ receives no messages | Pub/Sub agent lacks required IAM | Dead-letter policy, topic/subscription permissions |
| Task vanishes unsent | Retries exhausted or worker returned 2xx too early | Failure ledger, worker semantics |
| Rising 429s | Rate limit/worker/provider mismatch | Queue rate and retry budget |
| Worker fails to start | Wrong profile, `PORT`, JDK, or env vars | Cloud Run revision logs |
| Rising costs | Retry storm, logs, or provider requests | Billing and task attempts |

## 29. Cleaning Up Lab Resources

The commands below **delete real resources**; run them only in the lab project after checking with the owner and confirming no data needs to be kept.

Delete subscriptions to stop push deliveries:

~~~bash
gcloud pubsub subscriptions delete "$PUSH_SUB" "$DLQ_SUB" \
  --project="$PROJECT_ID"
~~~

Delete the queue (pending tasks will be lost):

~~~bash
gcloud tasks queues delete "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$REGION"
~~~

Delete the Cloud Run services:

~~~bash
gcloud run services delete event-router \
  --project="$PROJECT_ID" \
  --region="$REGION"

gcloud run services delete notify-worker \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

Delete topics and repository belonging strictly to this lab:

~~~bash
gcloud pubsub topics delete "$TOPIC" "$DLQ_TOPIC" \
  --project="$PROJECT_ID"

gcloud artifacts repositories delete "$REPO" \
  --project="$PROJECT_ID" \
  --location="$REGION"
~~~

Delete the four service accounts only if no other workloads depend on them. **Never delete Google-managed Pub/Sub or Cloud Tasks service agents.** After cleanup, inspect Cloud Billing and remaining resources.

## 30. Extension Exercises

### Exercise A — Scheduled Notifications

Use Cloud Tasks `scheduleTime` to send a notification 30 minutes later without calling `Thread.sleep` inside an HTTP handler. Verify the task does not run ahead of schedule.

### Exercise B — Sandbox Email Provider

Integrate a sandbox API and Secret Manager with an idempotency key, timeouts, retry classification, and safeguards so nothing is sent to recipients outside the lab scope.

### Exercise C — Durable Ledger

Use Firestore or Cloud SQL to store `PENDING`/`SENT`/`FAILED` states, design leases and crash recovery, and test two dispatches with the same `eventId`.

### Exercise D — Additional Fan-Out for Analytics

Create a second Pub/Sub subscription for Analytics. Verify a single event is received independently by multiple consumers.

### Exercise E — IAM Outage Drill

In staging, temporarily alter the Invoker permission, observe 401/403 errors and backlog buildup, then roll back IAM and verify recovery per runbook.

## 31. Acceptance Criteria

| Criterion | Evidence |
|---|---|
| Topics/queue | Exact describe/list outputs for created resources |
| Identity | Four separate SAs with properly scoped IAM |
| Event routing | Router enqueues a task after receiving push |
| Worker dispatch | Simulated log includes `eventId` |
| Authentication | Negative tests rejected appropriately |
| Pub/Sub DLQ | Invalid JSON retried and forwarded when eligible |
| Cloud Tasks retry | `FAIL-DEMO` returns 503 and triggers retries |
| Duplicate | One `eventId` does not create two tasks within dedup window |
| Observability | Metrics for queue, errors, backlog, and latency |
| FinOps | Explanation of how retries impact cost |
| Cleanup | Lab resources deleted or assigned a retention owner |

## Conclusion

**Pub/Sub** solves asynchronous event distribution and fan-out; **Cloud Tasks** dispatches HTTP tasks to a handler with rate limits, concurrency, scheduling, and retries. The `OrderCreated` → Pub/Sub push → `event-router` → Cloud Tasks → `notification-worker` pattern prevents checkout from blocking on an email provider. However, end-to-end reliability requires **timely ACKs, IAM/OIDC with the right audience, idempotency, a Pub/Sub DLQ, a Cloud Tasks failure ledger, and monitoring**. When operated well, this pattern scales across notifications, report exports, data synchronization, and other post-processing workflows.

## References

- [Pub/Sub overview](https://docs.cloud.google.com/pubsub/docs/overview)
- [Pub/Sub push subscriptions](https://docs.cloud.google.com/pubsub/docs/push)
- [Pub/Sub authenticated push](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions)
- [Pub/Sub subscription retry policy](https://docs.cloud.google.com/pubsub/docs/subscription-retry-policy)
- [Pub/Sub dead-letter topics](https://docs.cloud.google.com/pubsub/docs/dead-letter-topics)
- [Pub/Sub subscription properties](https://docs.cloud.google.com/pubsub/docs/subscription-properties)
- [Cloud Tasks overview](https://docs.cloud.google.com/tasks/docs/dual-overview)
- [Cloud Tasks create HTTP tasks](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks)
- [Cloud Tasks authenticated Java example](https://docs.cloud.google.com/tasks/docs/samples/cloud-tasks-create-http-task-with-token)
- [Cloud Tasks queue configuration](https://docs.cloud.google.com/tasks/docs/configuring-queues)
- [Cloud Tasks quotas](https://docs.cloud.google.com/tasks/docs/quotas)
- [Cloud Tasks troubleshooting](https://docs.cloud.google.com/tasks/docs/common-pitfalls)
- [Cloud Run with Pub/Sub](https://docs.cloud.google.com/run/docs/tutorials/pubsub)
- [Cloud Run service-to-service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)
- [Cloud Tasks Java client reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-tasks/latest/overview)
- [Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Cloud Billing cost management](https://docs.cloud.google.com/billing/docs/how-to/cost-management)
