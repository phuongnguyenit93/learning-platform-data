# Java Microservice Lab on Container Apps with Service Bus

## 1. Problem Statement and Completion Criteria

Suppose a company develops an **Orders** application in Java. When a user places an order, the API must respond quickly; downstream tasks such as order confirmation, sending emails, inventory sync, and reconciliation can run asynchronously. If the REST API calls all dependencies synchronously, a single slow system can cause the entire request to time out.

In this capstone lab, we build an architecture on **Microsoft Azure**:

- **orders-api**: a Java/Spring Boot REST API running in **Azure Container Apps** (ACA) that receives HTTP requests and sends messages to Azure Service Bus.
- **orders-worker**: another Container App using the same Java image but running in worker mode, reading messages, processing them, and settling with the broker.
- **Azure Service Bus queue**: a buffer decoupling processing pace between the API and worker, supporting peek-lock, retries, and a dead-letter queue (DLQ).
- **Azure Container Registry (ACR)**: stores the image produced by the build process; Container Apps pulls images using granted permissions.
- **Managed identity / Microsoft Entra ID**: assigns Service Bus Data Sender/Receiver roles and image pull permissions instead of storing shared access keys.
- **Azure Monitor, Container Apps logs, Service Bus metrics**: observe success rates, backlog, DLQ, replicas, and connection errors.

This is an **isolated lab**. The worker only validates events and logs them; **it does not yet write orders to a real database**. For production, you must add durable transactions and idempotency, authentication/authorization, tracing, load testing, and a DR plan. Never treat a log line of success as completed business processing.

### Learning Objectives

After this lesson, you can:

1. Explain the **HTTP → Service Bus → worker** flow and distinguish HTTP 202 from final processing completion.
2. Build a Spring Boot 3 / Java 21 application packaged into a single image serving both API and worker roles.
3. Provision a Service Bus namespace/queue, ACR, Container Apps environment, and two Container Apps; enforce RBAC per managed identity.
4. Verify the send/receive path, diagnose delivery/retry/lock failures, and handle duplicates and DLQ messages.
5. Design worker scaling based on Service Bus backlog, monitor SLIs, and execute safe deployments/rollbacks.
6. Estimate costs, security, cleanup, and evaluate limitations of the lab model before production.

## 2. Architecture Diagram and Service Contract

~~~mermaid
flowchart LR
    U["Client"] -->|"POST /orders"| A["Container App: orders-api\nSpring Boot"]
    A -->|"Send AMQP/TLS"| Q[("Service Bus queue: orders")]
    Q -->|"PeekLock"| W["Container App: orders-worker\nSpring Boot"]
    W -. "Add in production" .-> D[("Orders DB + processed_message")]
    A -. "Logs / metrics" .-> O["Azure Monitor"]
    Q -. "Backlog / DLQ" .-> O
    W -. "Logs / metrics" .-> O
    ID["Managed identities"] -. "Sender role" .-> A
    ID -. "Receiver role" .-> W
~~~

| Component | What it does | What it does NOT guarantee |
| --- | --- | --- |
| REST API | Validates request, assigns stable message ID, enqueues, returns **202 Accepted** | Does not prove the worker finished business processing |
| Service Bus queue | Stores/delivers messages per tier capabilities, manages settlement and DLQ | Does not guarantee **exactly-once** consumer side effects |
| Worker | Receives, processes, completes on success or abandons on failure | Messages can still be redelivered |
| Container Apps | Runs containers/revisions, API ingress, worker scaling, managed identity | Does not replace application idempotency or transactions |
| ACR | Stores/serves images via RBAC | Images are unverified if CI lacks scanning and provenance |
| Monitoring | Collects telemetry when configured | A queue count of 0 does not prove orders were saved accurately |

**Why choose a queue?** A pool of workers competing to pull and process work from a queue fits this pipeline. If a single event must reach **multiple independent systems** (email, billing, analytics), evaluate a **Service Bus topic with separate subscriptions**. Multiple consumers reading **one queue** compete for messages; they do not each receive a copy.

## 3. Prerequisites and Cost Boundaries

- An **Azure subscription** with permissions to create resource groups, Service Bus, ACR, Container Apps environments, and apps; permission to create **role assignments** must be granted separately per RBAC policy.
- Logged-in Azure CLI with the appropriate `containerapp` extension; locally installed **Java 21**, Maven, and `curl` (or equivalent HTTP tool).
- Permission to use Azure Container Registry Tasks (`az acr build`) or an alternative container build workflow.
- A lab budget and ability to delete resources afterward. Service Bus Standard, ACR, Container Apps, networking, and logging can incur charges.
- Basic familiarity with Java records, Spring Boot, Dockerfiles, HTTP, JSON, and message queues.

Example naming convention:

| Variable | Illustrative value | Notes |
| --- | --- | --- |
| Resource group | `rg-orders-lab` | Contains only lab resources |
| Region | `southeastasia` | Verify support, quota, and pricing |
| Service Bus namespace | `sb-orders-<unique>` | Follows Service Bus naming rules, unique |
| Queue | `orders` | Event source entity |
| Registry | `acrorders<unique>` | Globally unique ACR name, alphanumeric |
| Environment | `cae-orders-lab` | Environment hosting both Container Apps |
| Apps | `ca-orders-api`, `ca-orders-worker` | Two separate identities and lifecycles |

**Replace** all placeholders before running commands; never pass literal `<`/`>` characters into real resource names. This lesson uses Bash/Cloud Shell; PowerShell requires different variable assignment syntax.

~~~bash
az account show \
  --query "{name:name,id:id,tenant:tenantId}" -o table
az extension list --query "[].{name:name,version:version}" -o table

# If the CLI lacks the extension and installation is permitted:
az extension add --name containerapp
~~~

`az extension add` updates the local admin CLI and creates no Azure resources. In real deployments, check syntax against your installed CLI version rather than assuming command flags never change.

## 4. Shared-Image Spring Boot Project

Lab project structure for the learner to create:

~~~text
orders-lab/
  pom.xml
  Dockerfile
  src/main/resources/application.yml
  src/main/java/com/example/orders/
    OrdersApplication.java
    OrderEvent.java
    OrdersApiController.java
    OrdersWorker.java
~~~

A single image runs two roles based on the `APP_ROLE` variable. The controller is instantiated only in `api` mode; the Service Bus processor runs only in `worker` mode. This demonstrates a shared event contract while allowing independent scaling, permissions, and releases for the two apps.

### 4.1 Maven Dependencies

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>orders-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-messaging-servicebus</artifactId>
      <version>7.17.0</version>
    </dependency>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-identity</artifactId>
      <version>1.13.0</version>
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

**Version pins are strictly for this self-contained example.** For new projects, verify Spring Boot and Azure SDK versions are still supported, patched, API-compatible, and aligned with dependency constraints. Projects using multiple Azure SDKs should consider the Azure SDK BOM.

### 4.2 Spring Configuration

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info

app:
  role: ${APP_ROLE:api}
  sb:
    fqns: ${SERVICEBUS_FQNS}
    queue: ${SERVICEBUS_QUEUE:orders}
~~~

`SERVICEBUS_FQNS` has the form `<namespace>.servicebus.windows.net`, **without** `sb://`, `https://`, or the queue name. For the worker, set `SPRING_MAIN_WEB_APPLICATION_TYPE=none` so it does not start a web server solely to process messages.

### 4.3 Entry Point and Managed Identity

File `src/main/java/com/example/orders/OrdersApplication.java`:

~~~java
package com.example.orders;

import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }

    @Bean
    TokenCredential azureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }
}
~~~

`DefaultAzureCredential` supports multiple credential sources: local developers can use an authenticated Azure CLI; production Container Apps should use a **managed identity**. This example assigns separate **system-assigned identities** to the API and worker. If multiple identities are attached, explicitly configure the target identity (client ID) per SDK guidance instead of leaving credential selection to chance.

### 4.4 Event Schema

File `src/main/java/com/example/orders/OrderEvent.java`:

~~~java
package com.example.orders;

public record OrderEvent(
    String orderId,
    String customerId,
    String sku,
    int quantity,
    String occurredAt
) {}
~~~

This is a minimal JSON contract for practice. Production requires schema versioning, backward compatibility, payload size limits, and personal-data handling rules. **Never put card details or secrets into messages.**

## 5. Producer: Accepting POST Requests and Sending Messages

File `src/main/java/com/example/orders/OrdersApiController.java`:

~~~java
package com.example.orders;

import com.azure.core.credential.TokenCredential;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.time.Instant;
import java.util.Map;

@RestController
@ConditionalOnProperty(name = "app.role", havingValue = "api")
public class OrdersApiController {
    public record CreateOrderRequest(String customerId, String sku, int quantity) {}

    private final ObjectMapper mapper;
    private final ServiceBusSenderClient sender;

    public OrdersApiController(
        ObjectMapper mapper,
        TokenCredential credential,
        @Value("${app.sb.fqns}") String fqns,
        @Value("${app.sb.queue}") String queue
    ) {
        this.mapper = mapper;
        this.sender = new ServiceBusClientBuilder()
            .fullyQualifiedNamespace(fqns)
            .credential(credential)
            .sender()
            .queueName(queue)
            .buildClient();
    }

    @GetMapping("/health/ready")
    public String ready() {
        return "ready";
    }

    @PostMapping("/orders")
    public ResponseEntity<Map<String, String>> createOrder(
        @RequestHeader("Idempotency-Key") String key,
        @RequestBody CreateOrderRequest request
    ) throws JsonProcessingException {
        if (key == null || !key.matches("[A-Za-z0-9._:-]{1,128}")
            || request == null
            || request.customerId() == null || request.customerId().isBlank()
            || request.sku() == null || request.sku().isBlank()
            || request.quantity() <= 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid request");
        }

        OrderEvent event = new OrderEvent(
            key, request.customerId(), request.sku(),
            request.quantity(), Instant.now().toString());
        ServiceBusMessage message = new ServiceBusMessage(
            mapper.writeValueAsString(event));
        message.setMessageId(key);
        message.setContentType("application/json");
        message.setSubject("orders.created.v1");

        // Do not return 202 Accepted if sending to Service Bus fails.
        sender.sendMessage(message);
        return ResponseEntity.accepted().body(
            Map.of("orderId", key, "status", "queued"));
    }

    @PreDestroy
    void close() {
        sender.close();
    }
}
~~~

**Key points:**

- `POST /orders` accepts JSON and an `Idempotency-Key` header. That key is used as `MessageId`, remaining consistent across client retries.
- `sender.sendMessage` only confirms the broker accepted the message. The API returns **202 Accepted**, **not** confirmation that the order is finished.
- If Service Bus is unavailable or lacks permissions, the SDK throws an exception; never return a fake 202. Production should classify errors (e.g., 503 when a dependency is down), use bounded retries with backoff, correlation IDs, and telemetry.
- Reusing the same key with a **different payload** is a business conflict. Production must store and verify a payload hash tied to the key so two different requests are not treated as the same order.
- The lab's `/health/ready` endpoint only proves the HTTP handler is up; **it does not verify** Service Bus connectivity or dependencies. Production needs a thoughtful readiness policy and observability that avoids putting unnecessary load on the broker.

## 6. Consumer: PeekLock and Explicit Settlement

File `src/main/java/com/example/orders/OrdersWorker.java`:

~~~java
package com.example.orders;

import com.azure.core.credential.TokenCredential;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusProcessorClient;
import com.azure.messaging.servicebus.ServiceBusReceivedMessageContext;
import com.azure.messaging.servicebus.models.ServiceBusReceiveMode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.time.Duration;

@Component
@ConditionalOnProperty(name = "app.role", havingValue = "worker")
public class OrdersWorker {
    private static final Logger LOG =
        LoggerFactory.getLogger(OrdersWorker.class);

    private final ObjectMapper mapper;
    private final ServiceBusProcessorClient processor;

    public OrdersWorker(
        ObjectMapper mapper,
        TokenCredential credential,
        @Value("${app.sb.fqns}") String fqns,
        @Value("${app.sb.queue}") String queue
    ) {
        this.mapper = mapper;
        this.processor = new ServiceBusClientBuilder()
            .fullyQualifiedNamespace(fqns)
            .credential(credential)
            .processor()
            .queueName(queue)
            .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
            .disableAutoComplete()
            .maxConcurrentCalls(2)
            .maxAutoLockRenewDuration(Duration.ofMinutes(5))
            .processMessage(this::handle)
            .processError(ctx ->
                LOG.error("Processor failed", ctx.getException()))
            .buildProcessorClient();
    }

    @PostConstruct
    void start() {
        processor.start();
    }

    private void handle(ServiceBusReceivedMessageContext context) {
        String messageId = context.getMessage().getMessageId();
        try {
            OrderEvent event = mapper.readValue(
                context.getMessage().getBody().toBytes(),
                OrderEvent.class);
            if (event.orderId() == null || event.orderId().isBlank()
                || event.quantity() <= 0) {
                throw new IllegalArgumentException("Invalid event");
            }

            // LAB: log only, not durable processing yet.
            LOG.info("Processed LAB order id={}, sku={}, quantity={}",
                event.orderId(), event.sku(), event.quantity());

            // Complete only after work genuinely succeeds.
            context.complete();
        } catch (Exception ex) {
            LOG.error("Processing failed for messageId={}", messageId, ex);
            context.abandon();
        }
    }

    @PreDestroy
    void stop() {
        processor.close();
    }
}
~~~

### 6.1 Why Is PeekLock Needed?

When receiving a message in **PeekLock** mode, the worker gets a processing window within the granted lock duration. Afterward:

| Outcome | Action |
| --- | --- |
| Business work succeeded | `complete` so the broker removes the message from the queue |
| Transient error | `abandon` so the message can be redelivered |
| Unprocessable payload/version | Explicitly `dead-letter` with a reason and a fix/replay process |
| Lock expired / worker crashed | The message may be redelivered; the worker must be **idempotent** |

`disableAutoComplete()` makes the worker explicitly responsible for settlement. `maxAutoLockRenewDuration` lets the SDK renew locks within supported bounds, **without** guaranteeing infinite lock retention for unbounded work. Callbacks can re-run if a lock is lost or `complete` fails; `maxConcurrentCalls` applies **per replica**.

In this example, every exception calls `abandon` to demonstrate retries. **Production must distinguish** transient errors (database/network timeouts) from permanent errors (invalid schema, business-rule violations) and never retry poison messages indefinitely. Service Bus moves messages to the **DLQ** after exceeding `MaxDeliveryCount`, upon TTL expiration if configured, or when the app explicitly dead-letters them.

### 6.2 Durable Idempotency for Production

When extending the worker to write to Azure SQL Database, maintain a `ProcessedMessages(message_id UNIQUE, payload_hash)` table alongside `Orders`. Record processing and update the order **within the same DB transaction**:

~~~text
BEGIN TRANSACTION
  INSERT ProcessedMessages(message_id, payload_hash) if not present;
  If ID exists and hash MATCHES:
    treat as already processed, do not write order again;
  If ID exists and hash DIFFERS:
    flag conflict, investigate; do not overwrite;
  If ID is new:
    INSERT/UPDATE Orders per business rules;
COMMIT TRANSACTION
COMPLETE Service Bus message after COMMIT succeeds.
~~~

The snippet above is **pseudocode**, not executable SQL. A unique constraint and transaction prevent two replicas processing the same event from creating duplicate orders. If the worker crashes **after DB commit but before complete**, the broker redelivers the message; the worker sees the message ID is already processed and calls `complete` with no new side effect.

If side effects include emails, payments, or partner APIs **outside the DB transaction**, add a transactional outbox/inbox, partner-supported idempotency keys, and reconciliation. Broker duplicate detection on Service Bus (even when enabled) never replaces application-level idempotent handling.

## 7. Packaging One Image to Run API and Worker

File `Dockerfile`:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS builder
WORKDIR /build
COPY pom.xml .
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
RUN useradd --system --uid 10001 appuser
COPY --from=builder /build/target/orders-lab-1.0.0.jar /app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This multi-stage build keeps Maven and the build toolchain out of the runtime image. `-DskipTests` is only for this build example; **production CI must run tests, scan dependencies/images/secrets, verify SBOM and provenance**, pin base images/digests, and use immutable tags/digests.

**Role split:** API sets `APP_ROLE=api` and HTTP port 8080; worker sets `APP_ROLE=worker`, `SPRING_MAIN_WEB_APPLICATION_TYPE=none`, and **needs no ingress**. Each Container App scales, rolls out, and rolls back independently even though they share the same image.

## 8. Provisioning Azure Service Bus, Registry, and Container Apps Environment

**The commands below create real resources and can incur charges. Run only when approved, in a dedicated lab RG.** Examples use Azure CLI in Bash/Cloud Shell:

### 8.1 Set Variables and Select Subscription

~~~bash
SUBSCRIPTION_ID="<subscription-id>"
RG="rg-orders-lab"
LOCATION="southeastasia"
ENV="cae-orders-lab"
QUEUE="orders"
SB_NS="sb-orders-<unique-suffix>"
ACR="acrorders<unique-suffix>"
API_APP="ca-orders-api"
WORKER_APP="ca-orders-worker"
IMAGE_TAG="orders-lab:v1"

az account set --subscription "$SUBSCRIPTION_ID"
az group create --name "$RG" --location "$LOCATION"
~~~

Replace all placeholders with valid names following naming rules. Use a **dedicated, unshared lab RG** to keep cleanup safe and clear.

### 8.2 Service Bus Namespace and Queue

~~~bash
az servicebus namespace create \
  --resource-group "$RG" \
  --name "$SB_NS" \
  --location "$LOCATION" \
  --sku Standard

az servicebus queue create \
  --resource-group "$RG" \
  --namespace-name "$SB_NS" \
  --name "$QUEUE" \
  --max-delivery-count 5

az servicebus queue show \
  --resource-group "$RG" \
  --namespace-name "$SB_NS" \
  --name "$QUEUE" -o json
~~~

Why **Standard**? The lab uses queues and anticipates expanding to features like duplicate detection or topics/subscriptions. Features, limits, pricing, and networking differ across Basic, Standard, and Premium; verify requirements before choosing a tier.

If you want **duplicate detection** by message ID, verify tier support and configure it at queue creation along with the **history window**. It limits duplicate submissions **within the broker window** and does not guarantee exactly-once DB or side-effect processing. Never toggle it by deleting a live production queue with data.

### 8.3 ACR and Image Build

~~~bash
az acr create \
  --resource-group "$RG" \
  --name "$ACR" \
  --location "$LOCATION" \
  --sku Basic \
  --admin-enabled false

# Run inside the orders-lab directory containing Dockerfile and pom.xml.
az acr build --registry "$ACR" --image "$IMAGE_TAG" .
~~~

`az acr build` sends the build context to ACR Tasks, which can incur charges and requires appropriate permissions. Do not enable the ACR admin account just to simplify pulls; we will use managed identities. In production, reference immutable image digests rather than mutable tags.

### 8.4 Container Apps Environment

~~~bash
az containerapp env create \
  --resource-group "$RG" \
  --name "$ENV" \
  --location "$LOCATION"
~~~

Check the Log Analytics destination, retention, quotas, network mode, and environment settings. The environment is a compute/hosting boundary; **it is not** a Service Bus namespace and does not automatically configure databases or virtual networks.

## 9. Deploying Both Container Apps with Least Privilege

### 9.1 Two Identities, Two Data Roles

| Identity | Service Bus permission | Recommended scope | Registry permission |
| --- | --- | --- | --- |
| API identity | **Azure Service Bus Data Sender** | `orders` queue | AcrPull / appropriate ACR pull role |
| Worker identity | **Azure Service Bus Data Receiver** | `orders` queue | AcrPull / appropriate ACR pull role |

Azure RBAC permissions to **create resources** (control plane) differ from permissions to **send/receive messages** (data plane). Do not grant Data Owner to either app. A system-assigned managed identity is tied to the Container App's lifecycle; deleting the app removes that identity.

### 9.2 Create Apps Initially with a Public Image, Then Assign Identities

To avoid enabling ACR admin credentials before the apps have identities, this lab creates them with a **public bootstrap image** before switching to the Orders image. An alternative for production is creating **user-assigned identities** upfront, granting pull rights, and passing those identities into IaC at creation time.

~~~bash
az containerapp create \
  --resource-group "$RG" --name "$API_APP" \
  --environment "$ENV" \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --ingress external --target-port 80 \
  --min-replicas 1 --max-replicas 2 \
  --env-vars APP_ROLE=api SERVICEBUS_FQNS="$SB_NS.servicebus.windows.net" \
             SERVICEBUS_QUEUE="$QUEUE"

az containerapp create \
  --resource-group "$RG" --name "$WORKER_APP" \
  --environment "$ENV" \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --min-replicas 1 --max-replicas 1 \
  --env-vars APP_ROLE=worker SPRING_MAIN_WEB_APPLICATION_TYPE=none \
             SERVICEBUS_FQNS="$SB_NS.servicebus.windows.net" \
             SERVICEBUS_QUEUE="$QUEUE"

az containerapp identity assign \
  --resource-group "$RG" --name "$API_APP" --system-assigned
az containerapp identity assign \
  --resource-group "$RG" --name "$WORKER_APP" --system-assigned
~~~

The bootstrap image **is not** the Java Orders image; verify public image versions and organizational registry policies. The worker has no ingress because it only consumes from the queue. If CLI syntax differs in your version, check `az containerapp create --help` or use Portal/IaC equivalents.

### 9.3 Assign Data Sender, Data Receiver, and ACR Pull

~~~bash
API_PID=$(az containerapp show -g "$RG" -n "$API_APP" \
  --query identity.principalId -o tsv)
WORKER_PID=$(az containerapp show -g "$RG" -n "$WORKER_APP" \
  --query identity.principalId -o tsv)
ACR_ID=$(az acr show -g "$RG" -n "$ACR" --query id -o tsv)
QUEUE_ID=$(az servicebus queue show \
  -g "$RG" --namespace-name "$SB_NS" --name "$QUEUE" \
  --query id -o tsv)

# Verify principal IDs and resource IDs are non-empty before running.
az role assignment create --assignee-object-id "$API_PID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull --scope "$ACR_ID"
az role assignment create --assignee-object-id "$WORKER_PID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull --scope "$ACR_ID"

az role assignment create --assignee-object-id "$API_PID" \
  --assignee-principal-type ServicePrincipal \
  --role "Azure Service Bus Data Sender" --scope "$QUEUE_ID"
az role assignment create --assignee-object-id "$WORKER_PID" \
  --assignee-principal-type ServicePrincipal \
  --role "Azure Service Bus Data Receiver" --scope "$QUEUE_ID"
~~~

Creating role assignments requires an authorized RBAC administrator role; not everyone who can deploy apps can assign roles. Wait for **role propagation** after granting permissions. If ACR uses ABAC/repository-level permissions, `AcrPull` may not be the right role; verify the registry's authorization mode and supported pull role rather than granting registry admin rights.

### 9.4 Switch to the Orders Image

~~~bash
IMAGE="$ACR.azurecr.io/$IMAGE_TAG"

az containerapp registry set -g "$RG" -n "$API_APP" \
  --server "$ACR.azurecr.io" --identity system
az containerapp registry set -g "$RG" -n "$WORKER_APP" \
  --server "$ACR.azurecr.io" --identity system

az containerapp update -g "$RG" -n "$API_APP" --image "$IMAGE"
az containerapp update -g "$RG" -n "$WORKER_APP" --image "$IMAGE"

# Java HTTP API listens on 8080, unlike the bootstrap image on port 80.
az containerapp ingress update \
  -g "$RG" -n "$API_APP" --target-port 8080
~~~

These commands **modify live revisions, images, and ingress**. Updating the image and target port in separate commands can cause brief downtime in the lab. Production should prepare revisions cleanly, verify readiness, and shift traffic deliberately rather than assuming a single `update` is zero-downtime.

Check revisions, identity, and logs:

~~~bash
az containerapp show -g "$RG" -n "$API_APP" \
  --query "{fqdn:properties.configuration.ingress.fqdn,identity:identity.principalId}" \
  -o json
az containerapp revision list -g "$RG" -n "$WORKER_APP" -o table
az containerapp logs show -g "$RG" -n "$WORKER_APP" --follow
~~~

Confirm **the active revision runs the Java Orders image in the worker role**, not just the bootstrap image still reporting healthy.

## 10. End-to-End Testing

### 10.1 Send a Real Request to the Lab API

~~~bash
API_FQDN=$(az containerapp show -g "$RG" -n "$API_APP" \
  --query properties.configuration.ingress.fqdn -o tsv)

curl -i -X POST "https://$API_FQDN/orders" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: lab-order-001" \
  -d '{"customerId":"demo-customer","sku":"BOOK-01","quantity":2}'
~~~

Expected response once the broker accepts the message (never assume your live environment succeeded without checking):

~~~json
{
  "orderId": "lab-order-001",
  "status": "queued"
}
~~~

**202 Accepted** means the message was accepted under the lab API contract. It **does not** confirm the worker processed it or a database committed it. Production needs a durable status query endpoint (such as `GET /orders/{id}`) or webhook/event notifications so clients learn the final outcome.

### 10.2 Cross-Check Worker and Broker

Use `az containerapp logs show` to find a log line like:

~~~text
Processed LAB order id=lab-order-001, sku=BOOK-01, quantity=2
~~~

Inspect queue metadata (note some CLI fields vary by version):

~~~bash
az servicebus queue show \
  -g "$RG" --namespace-name "$SB_NS" --name "$QUEUE" \
  --query "{name:name,counts:countDetails,maxDeliveryCount:maxDeliveryCount}" \
  -o json
~~~

Watch Azure Service Bus metrics in Portal: **Active Messages**, **Dead-lettered Messages**, Incoming/Outgoing Messages, errors, and throughput. Metrics have ingestion latency; active message counts fluctuating during continuous send/receive is normal. If `countDetails` is null, inspect the full JSON and live resource metrics rather than assuming the queue is empty.

### 10.3 Test Duplicates and Retries

1. Resend the same `Idempotency-Key` and payload. If duplicate detection is off on the queue, you may see two worker log entries. This demonstrates **at-least-once delivery**, not an SDK bug.
2. In an isolated lab test, simulate a transient worker exception before `complete`; observe delivery count and retry/abandon behavior.
3. After failing `MaxDeliveryCount` times, the message can move to the DLQ; inspect its reason and never replay blindly onto a production queue.
4. Restore normal worker behavior and confirm no unexpected backlog remains and no test events caused real side effects.

**Never use real payments, real emails, or customer data** when testing failures. To test broker duplicate detection, create a lab entity with the required tier/settings and detection history rather than altering a queue holding production data.

## 11. Delivery Semantics, DLQ, Ordering, and Idempotency

### 11.1 At-Least-Once Is Operational Reality

~~~mermaid
sequenceDiagram
    participant API as API
    participant SB as Service Bus
    participant W as Worker
    participant DB as Database
    API->>SB: Send message id=42
    SB-->>API: Accepted
    API-->>API: HTTP 202
    SB->>W: Deliver id=42, lock
    W->>DB: Transaction with unique message ID
    DB-->>W: Commit
    Note over W,SB: Worker crashes before Complete
    SB->>W: Redeliver id=42
    W->>DB: Check processed ID, skip duplicate
    W->>SB: Complete
~~~

Service Bus supports duplicate detection when enabled on supported tiers **within a bounded detection window**, yet crashing after DB commit and before `complete` still causes reprocessing. True business accuracy requires idempotency at the application/database layer.

### 11.2 Settlement and DLQ

| Action | Meaning | When to use |
| --- | --- | --- |
| `complete` | Confirms processing succeeded, removes message | After DB commit / business step succeeds |
| `abandon` | Releases lock, message becomes eligible for redelivery | Transient failure; bounded retries |
| `deadLetter` | Moves message to DLQ for investigation | Poison or unprocessable payload/schema |
| `defer` | Defers message, requires retrieving by sequence number | Special stateful workflows |
| Lock expiration | Broker can redeliver the message | Ensure durability and idempotent handling |

If a message repeatedly fails, the DLQ isolates the **poison message** so it does not stall the entire queue. However, **the DLQ does not fix messages automatically**: you need an owner, alerts, root-cause diagnostics, replay policies, and reconciliation. Never replay everything into production without knowing the side effects.

### 11.3 Ordering

With multiple worker replicas or concurrency, **do not assume** a queue processes messages in strict business order. If strict ordering per order or account is required, investigate **Service Bus sessions** with a session-enabled entity and session processor. That choice affects throughput, parallelism, and locking design; simply setting `messageId` does not enable sessions.

## 12. Scaling the Worker on Queue Backlog

**Container Apps** can scale on events via KEDA/supported scalers. For Service Bus, **active message count** is commonly used as the signal to add worker replicas.

| Workload | Ingress | Scale signal | Risk |
| --- | --- | --- | --- |
| API | External HTTPS in lab | Concurrent HTTP requests, CPU/memory | Timeouts, traffic spikes, rate limits |
| Worker | **No ingress** | Queue backlog / Service Bus scaler | Overscaling overwhelms SQL or partners |

The lab uses `min-replicas 1` for easy verification. For scale-to-zero, you must configure a **working event-driven scale rule**; a worker set to min 0 without a scaler may never wake up to consume messages.

Illustrative CLI syntax (**depends on CLI extension versions supporting identity-based scale rules**):

~~~bash
# MODIFIES live scaling config; test only on a verified lab.
az containerapp update \
  -g "$RG" -n "$WORKER_APP" \
  --min-replicas 0 --max-replicas 5 \
  --scale-rule-name orders-backlog \
  --scale-rule-type azure-servicebus \
  --scale-rule-metadata "queueName=$QUEUE" "namespace=$SB_NS" "messageCount=5" \
  --scale-rule-identity system
~~~

Metadata keys (`queueName`, `namespace`, `messageCount`) and `--scale-rule-identity` must be checked against `az containerapp update --help` and the Container Apps/KEDA schema in your environment. **Do not assume** every CLI version, region, or plan supports the exact same syntax. The scaler identity needs supported permissions to read backlog metrics; the worker Java SDK needs **Data Receiver** to process messages. Never grant Owner just to make the scaler work.

If the scaler cannot use managed identity in your configuration, use a supported authentication method with Container Apps/KEDA secrets; never put Service Bus connection strings into Git or shell history.

**Backpressure:** 5 replicas × `maxConcurrentCalls=2` can run up to roughly **10 concurrent processing callbacks**. If the database safely handles only 6 concurrent transactions, adding replicas can fill the queue **faster** via a retry storm. Tune max replicas, concurrency, timeouts, connection pools, circuit breakers, and message-age SLOs together. KEDA also has polling intervals, cooldowns, and cold starts, so scaling is not instantaneous.

## 13. Practical Monitoring and SLOs

### 13.1 Minimum Metric Set

| Source | Metrics / signals | Purpose |
| --- | --- | --- |
| API | HTTP 2xx/5xx, send failures, p95/p99 latency | Shows if API accepts and enqueues work |
| Service Bus | Active Messages, Dead-lettered Messages, incoming/outgoing, throttling | Reveals backlog, poison messages, broker limits |
| Worker | Processed/failed, delivery count, handling duration, complete/abandon failures | Observes consumer behavior |
| ACA | Replica count, restarts, CPU/memory, revision health | Detects scaling and runtime failures |
| Identity/network | Unauthorized, DNS/TLS, connection timeouts, image pulls | Isolates RBAC and connectivity issues |
| Business (if DB added) | Order state, duplicate count, end-to-end age | Verifies business correctness |

**Illustrative SLO, not an Azure SLA:** within a test window, ≥99.5% of valid `POST /orders` requests are accepted by the broker and return 202. In production with a DB, add a completion SLO: ≥99% of accepted orders commit successfully within 2 minutes. **A log-only lab lacks the data sources needed to claim a completion SLO.**

### 13.2 Logs and KQL

Using log streaming:

~~~bash
az containerapp logs show -g "$RG" -n "$API_APP" --follow
az containerapp logs show -g "$RG" -n "$WORKER_APP" --follow
~~~

If the Container Apps environment sends logs to Log Analytics and the workspace has the `ContainerAppConsoleLogs_CL` table, an example KQL query counting worker **log lines** is:

~~~kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(30m)
| where ContainerAppName_s == "ca-orders-worker"
| where Log_s contains "Processed LAB order"
| summarize ProcessedLogLines = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Table and column names **depend on your collection method and workspace schema**; verify them in your live workspace before running. One message can generate multiple log lines due to retries, and ingestion has latency. Never treat `ProcessedLogLines` as a durable order count; emit custom metrics/traces with correlation IDs and query an order-status table in production.

### 13.3 Alerts and Runbooks

Configure alerts for: rising API 5xx/send failures, growing queue backlog/oldest message age, non-zero/rising DLQ counts, worker CrashLoops or missing replicas, Service Bus auth/throttling errors, and missing logs during active traffic. Assign an on-call owner, evaluation window, and thresholds; distinguish **missing telemetry** from meeting an SLO.

Before production, test alert delivery, poison-message runbooks, and DLQ read permissions; never allow unguarded replays on live data.

## 14. Security, CI/CD, and Rollback

### 14.1 Securing Access Paths

The lab opens external ingress on the API for easy `curl` testing; production needs authentication/authorization, validation, rate limiting, secret scanning, and potentially private ingress/gateway/WAF depending on architecture. Service Bus and ACR should use **managed identities** and least privilege; evaluate Private Endpoints/VNet/DNS according to **SKU capabilities**. Never assume every Service Bus tier offers the same networking options.

Never log secrets or PII, avoid granting combined sender+receiver roles unnecessarily, and never open unrestricted egress just to "fix" DNS/RBAC issues. When workloads depend on Azure SQL, Key Vault, or Entra ID, test endpoints, DNS, network paths, tokens, and timeouts from the running revision.

### 14.2 Releasing with Image Digests

~~~mermaid
flowchart LR
    B["CI: build/test/scan"] --> I["ACR image digest"]
    I --> W["Update worker (reads old/new schema)"]
    W --> P["Update producer/API"]
    P --> T{"SLI, DLQ, backlog healthy?"}
    T -->|Yes| O["Promote/observe"]
    T -->|No| R["Stop + safe rollback"]
~~~

Container Apps supports **revisions**, yet rolling back HTTP traffic **does not** automatically roll back queue schemas or queued messages. If API v2 emits a new `currency` field, worker v1 must tolerate or read v2 events before switching traffic back; deploy workers compatible with both v1/v2 first, then the producer. Maintain schema versioning and an **expand–migrate–contract** evolution policy; never drop support for old messages while backlog remains in the queue.

### 14.3 Costs

| Item | Cost factors |
| --- | --- |
| Container Apps | CPU/memory, requests, and min/max replicas per plan |
| Service Bus | Tier, operations/messages/throughput, and features |
| ACR | Registry tier, image storage, build tasks |
| Log Analytics / Azure Monitor | Data ingestion, retention, queries, alerts |
| Networking | Ingress/egress, private connectivity, and load balancing where applicable |
| Database (if added) | Compute, storage, backups, replication, and transactions |

Running the worker at `min-replicas 1` is easy to debug but incurs idle charges; scale-to-zero saves money when idle but introduces cold starts and requires accurate scaler config. Use **Cost Management and the Pricing Calculator** for your real region/tier instead of estimating from examples.

### 14.4 Cleanup

After the lab, confirm the resource group **holds only lab resources** and any needed data has been exported/retained. Once approved, you can delete the lab RG:

~~~bash
# DANGEROUS: deletes ALL resources in the RG, not just the two apps.
az group delete --name "$RG" --yes --no-wait
~~~

Never run this on a shared or production RG. Monitor billing after cleanup since Cost Management updates with latency.

## 15. Practical Troubleshooting

| Symptom | Common causes | Where to check |
| --- | --- | --- |
| API returns 500/503 on send | Wrong FQNS/queue, Sender RBAC, DNS/TLS/AMQP, Service Bus quota | API logs, Service Bus metrics, identity/principal |
| `Unauthorized` | Wrong identity, scope mismatch, role assignment not yet propagated | `principalId`, Data Sender/Receiver role, propagation delay |
| ACR pull fails | Identity/AcrPull, registry hostname, image tag/digest, network | Revision events and registry settings |
| API never ready | Wrong target port 8080, Java crash, missing env vars | Ingress target, revision logs, API role |
| Worker runs yet queue doesn't drain | Wrong `APP_ROLE`, processor not started, Receiver RBAC, lock/settlement error | Worker logs, queue counts, callback exceptions |
| Duplicate messages | Client retry, lock expired, crash after DB commit | MessageId, delivery count, unique constraint |
| DLQ growing | Poison payload, MaxDeliveryCount, TTL, schema mismatch | DLQ reason, schema version, controlled replay |
| Worker at min=0 never wakes up | Missing/misconfigured scaler namespace, queue, identity, or rights | Scale rules, scaler logs, Active Messages |
| Worker scales excessively | High max replicas, high per-replica concurrency, slow downstream | Throttle worker, DB pool, queues, retries |
| No logs visible | Missing Log Analytics, ingestion delay, wrong schema/query | Log stream, environment destination, workspace |
| Rollback of producer still fails | Queued events incompatible with old consumer | Use backward-compatible schema, inspect DLQ |

**Incident runbook:** check HTTP status → revision/API logs → namespace/queue & Service Bus metrics → worker role/logs → RBAC/identity/network → schema & DB idempotency → safe rollback/replay. Missing telemetry is **INCONCLUSIVE**—never assume the system is healthy without evidence.

## 16. Exercises and Self-Check Questions

### Exercise 1: Calculate Acceptance SLI

Out of 10,000 valid requests, the API successfully enqueues 9,980 messages and 20 fail. The worker shows 9,950 processed log lines, with no database attached.

**Answer:** Acceptance SLI = 9,980 / 10,000 × 100% = **99.8%**. You cannot claim 9,950 orders were durably created; there may be duplicate logs, retries, and log ingestion lag. Persist order state in a database and measure end-to-end completion.

### Exercise 2: Crash After Commit Before Complete

The worker processes ID `order-42`, commits to SQL, and crashes before calling `complete`. The message is redelivered.

**Answer:** The worker must check the unique message ID within the same transaction that creates/updates the order. Upon redelivery, verify the payload matches and call `complete` without creating a second order. If external payment/email calls occur outside the transaction, use partner idempotency/outbox patterns and reconciliation.

### Exercise 3: Concurrency Limits

The worker sets `maxConcurrentCalls=2` and KEDA `max-replicas=5`. At 5 replicas, there are up to roughly **5 × 2 = 10 concurrent callbacks**, while the database safely handles only 6 concurrent transactions.

**Answer:** Lower per-replica concurrency or max replicas, tune connection pools/backpressure, measure throughput/latency, and increase database capacity if warranted. Never scale workers unboundedly into an overloaded downstream dependency.

### Exercise 4: Event Schema Evolution

Producer v2 sends a new required field that worker v1 cannot parse.

**Answer:** Version the event contract, deploy a worker supporting both v1 and v2 before updating the producer, canary via queue/DLQ monitoring, and drop v1 support only after old events drain. Image rollback plans must account for **events still sitting in the queue**, not just Container App revisions.

### Self-Check Questions

1. Why should the API and worker have separate Container Apps and managed identities?
2. What does HTTP 202 confirm, and what does it NOT confirm?
3. How do Service Bus **Data Sender/Receiver** roles differ from Azure resource creation permissions?
4. How does `PeekLock` differ from `ReceiveAndDelete`?
5. Why must `complete` happen **after** the transaction commits?
6. Does broker duplicate detection guarantee business-level exactly-once processing?
7. Why does the worker need no external ingress? What is required for `min-replicas 0`?
8. Why does a queue count of 0 not prove all orders completed successfully?
9. When should you use a Service Bus **topic/subscriptions** instead of a single queue?
10. Why must rolling back a producer consider event versions already sitting in the queue?

### Lab Completion Checklist

| Item | Evidence |
| --- | --- |
| Two Container Apps | API and worker running the right image digest and `APP_ROLE` |
| Least privilege | API has Sender, worker has Receiver, scoped ACR pull access |
| Enqueue | Valid POST returns 202 with consistent message ID |
| Receive | Worker logs show matching ID with no sustained processor errors |
| Retry/idempotency | Understands and simulates redelivery; production transaction plan documented |
| DLQ | Knows how to inspect, alert on, handle, and safely replay |
| Scaling | Min/max replicas chosen and backlog rule configured if scale-to-zero |
| Monitoring | API SLIs, queue backlog, worker health, logs, and cost tracked |
| Security | No leaked tokens/secrets; network and ingress controlled |
| Cleanup | Owner confirmed, lab resources removed, retention/budget checked |

**Key takeaway:** With Java microservices on **Azure Container Apps + Service Bus**, the challenge does not end when two containers exchange JSON. Your architecture must separate **request acceptance** from **business completion**, apply **managed identities and least-privilege RBAC**, handle **at-least-once delivery** via idempotency, bound backlog scaling, monitor both the API and queue/worker, and plan safe rollbacks before upgrading event schemas.
