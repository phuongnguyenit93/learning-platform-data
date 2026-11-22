# Thực hành microservice Java trên Container Apps với Service Bus

## 1. Bài toán và tiêu chí hoàn thành

Giả sử doanh nghiệp phát triển ứng dụng đặt hàng **Orders** bằng Java. Khi người dùng tạo đơn, API cần phản hồi nhanh; các công việc như xác nhận đơn, gửi email, đồng bộ kho và đối soát có thể xử lý bất đồng bộ. Nếu REST API gọi đồng bộ tất cả các phụ thuộc, một hệ thống chậm có thể khiến toàn bộ yêu cầu bị timeout.

Trong bài thực hành tổng hợp, ta xây kiến trúc trên **Microsoft Azure**:

- **orders-api**: REST API Java/Spring Boot chạy trong **Azure Container Apps** (ACA), nhận HTTP request và gửi message vào Azure Service Bus.
- **orders-worker**: Container App khác, dùng cùng image Java nhưng chạy chế độ worker, đọc message, xử lý và xác nhận với broker.
- **Azure Service Bus queue**: bộ đệm tách nhịp xử lý giữa API và worker, hỗ trợ peek-lock, retry, dead-letter queue (DLQ).
- **Azure Container Registry (ACR)**: lưu image do quy trình build tạo; Container Apps kéo image theo quyền đã cấp.
- **Managed identity / Microsoft Entra ID**: cấp vai trò Service Bus Data Sender/Receiver và quyền kéo image thay vì lưu shared access key.
- **Azure Monitor, Container Apps logs, Service Bus metrics**: quan sát tỷ lệ thành công, backlog, DLQ, replica và lỗi kết nối.

Đây là **lab cô lập**. Worker chỉ xác thực event và ghi log, **chưa tạo đơn trong database thật**. Khi triển khai production, phải bổ sung transaction bền vững và idempotency, authentication/authorization, tracing, kiểm thử tải và kế hoạch DR. Không coi việc log thành công là hoàn tất nghiệp vụ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích luồng **HTTP → Service Bus → worker**, phân biệt HTTP 202 với kết quả xử lý cuối cùng.
2. Viết một ứng dụng Spring Boot 3/Java 21 đóng gói thành một image, có hai vai trò API và worker.
3. Tạo Service Bus namespace/queue, ACR, Container Apps environment và hai Container Apps; áp RBAC theo từng managed identity.
4. Kiểm chứng đường gửi/nhận, nhận diện lỗi delivery/retry/lock, xử lý duplicate và DLQ.
5. Thiết kế scale worker theo Service Bus backlog, giám sát SLI và triển khai/rollback an toàn.
6. Dự tính chi phí, bảo mật, cleanup và đánh giá những giới hạn của mô hình lab trước production.

## 2. Sơ đồ kiến trúc và contract giữa hai dịch vụ

~~~mermaid
flowchart LR
    U["Client"] -->|"POST /orders"| A["Container App: orders-api\nSpring Boot"]
    A -->|"Send AMQP/TLS"| Q[("Service Bus queue: orders")]
    Q -->|"PeekLock"| W["Container App: orders-worker\nSpring Boot"]
    W -. "Bổ sung ở production" .-> D[("Orders DB + processed_message")]
    A -. "Logs / metrics" .-> O["Azure Monitor"]
    Q -. "Backlog / DLQ" .-> O
    W -. "Logs / metrics" .-> O
    ID["Managed identities"] -. "Sender role" .-> A
    ID -. "Receiver role" .-> W
~~~

| Thành phần | Làm gì? | Không đảm bảo điều gì? |
| --- | --- | --- |
| REST API | Kiểm tra request, gán message ID ổn định, gửi queue, trả **202 Accepted** | Chưa chứng minh worker đã xử lý nghiệp vụ |
| Service Bus queue | Lưu/giao phát message theo khả năng của tier, quản lý settlement và DLQ | Không bảo đảm side effect của consumer **exactly-once** |
| Worker | Nhận, xử lý, complete sau thành công hoặc abandon khi lỗi | Message có thể được giao lại |
| Container Apps | Chạy container/revisions, ingress API, scale worker, quản lý identity | Không tự thay thế cơ chế idempotency hoặc transaction |
| ACR | Lưu/pull images theo RBAC | Image chưa được kiểm soát nếu CI thiếu scan và provenance |
| Monitoring | Thu thập telemetry khi đã cấu hình | Queue count bằng 0 không chứng minh đơn hàng đã lưu chính xác |

**Vì sao chọn queue?** Một nhóm worker cùng lấy và xử lý công việc từ queue phù hợp cho pipeline này. Nếu một event cần tới **nhiều hệ thống độc lập** (email, billing, analytics), hãy đánh giá **Service Bus topic với các subscriptions riêng**. Nhiều consumer cùng đọc **một queue** là cạnh tranh nhận việc, không phải mỗi consumer đều nhận bản sao.

## 3. Điều kiện tiên quyết và ranh giới chi phí

- Một **Azure subscription** có quyền tạo resource group, Service Bus, ACR, Container Apps environment và apps; quyền tạo **role assignment** cần được cấp riêng theo chính sách RBAC.
- Azure CLI đăng nhập, extension `containerapp` phù hợp; local có **Java 21**, Maven và `curl` (hoặc công cụ HTTP tương đương).
- Có quyền sử dụng Azure Container Registry Tasks (`az acr build`) hay một container build workflow khác.
- Có ngân sách lab và khả năng xóa tài nguyên sau thực hành. Service Bus Standard, ACR, Container Apps, network và logging có thể phát sinh chi phí.
- Hiểu cơ bản Java records, Spring Boot, Dockerfile, HTTP, JSON và message queues.

Ví dụ quy ước đặt tên:

| Biến | Giá trị minh họa | Lưu ý |
| --- | --- | --- |
| Resource group | `rg-orders-lab` | Chỉ chứa tài nguyên bài lab |
| Region | `southeastasia` | Cần xác minh hỗ trợ, quota và giá |
| Service Bus namespace | `sb-orders-<unique>` | Tên theo quy tắc Service Bus, duy nhất |
| Queue | `orders` | Entity nguồn sự kiện |
| Registry | `acrorders<unique>` | Tên ACR toàn cục, chữ và số |
| Environment | `cae-orders-lab` | Môi trường của hai Container Apps |
| Apps | `ca-orders-api`, `ca-orders-worker` | Hai identity và vòng đời riêng |

**Phải thay** mọi placeholder trước khi chạy lệnh, không nhập nguyên ký tự `<`/`>` vào tên resource thực. Bài dùng Bash/Cloud Shell; PowerShell cần đổi cú pháp gán biến.

~~~bash
az account show \
  --query "{name:name,id:id,tenant:tenantId}" -o table
az extension list --query "[].{name:name,version:version}" -o table

# Nếu CLI chưa có extension và được phép cài:
az extension add --name containerapp
~~~

Lệnh `az extension add` thay đổi CLI trên máy quản trị, không tạo Azure resource. Khi triển khai thật, kiểm tra cú pháp theo phiên bản đang dùng thay vì mặc định mọi command option không thay đổi theo thời gian.

## 4. Dự án Spring Boot dùng chung một image

Cấu trúc dự án lab người học sẽ tự tạo:

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

Một image chạy hai vai trò dựa vào biến `APP_ROLE`. Controller chỉ được tạo ở mode `api`; Service Bus processor chỉ chạy ở mode `worker`. Điều này giúp demo có hợp đồng event chung mà vẫn scale, cấp quyền và phát hành hai apps khác nhau.

### 4.1 Maven dependencies

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

**Version pin chỉ phục vụ ví dụ tự chứa.** Khi triển khai dự án mới phải kiểm tra phiên bản Spring Boot/Azure SDK còn được hỗ trợ, bản vá bảo mật, API compatibility và dependency constraints. Dự án có nhiều SDK nên cân nhắc Azure SDK BOM để quản lý phiên bản.

### 4.2 Cấu hình Spring

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

`SERVICEBUS_FQNS` có dạng `<namespace>.servicebus.windows.net`, **không** kèm `sb://`, `https://` hoặc tên queue. Đối với worker, đặt `SPRING_MAIN_WEB_APPLICATION_TYPE=none` để không khởi động web server chỉ để nhận message.

### 4.3 Entry point và managed identity

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

`DefaultAzureCredential` hỗ trợ nhiều nguồn danh tính: local developer có thể dùng Azure CLI đã đăng nhập; Container Apps production nên dùng **managed identity**. Ví dụ này gán **system-assigned identity** riêng cho API và worker. Nếu gắn nhiều identities, cần cấu hình identity cụ thể (client ID) theo cơ chế SDK hỗ trợ, không để việc chọn danh tính phụ thuộc may rủi.

### 4.4 Event schema

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

Đây là hợp đồng JSON đơn giản để thực hành. Production cần schema version, backward compatibility, payload size limit và chính sách dữ liệu cá nhân. **Không đưa thông tin thẻ hoặc secret vào message.**

## 5. Producer: nhận POST và gửi message

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

        // Nếu Service Bus send thất bại, không trả 202 thành công.
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

**Ý nghĩa:**

- `POST /orders` nhận JSON và `Idempotency-Key`. Key được dùng làm `MessageId`, giữ ổn định giữa các lần retry của client.
- `sender.sendMessage` chỉ xác nhận broker chấp nhận message. API trả **202 Accepted**, **không** khẳng định đơn đã hoàn tất.
- Nếu Service Bus unavailable hoặc thiếu quyền, SDK ném exception; không được trả 202 giả. Production nên phân loại lỗi (ví dụ trả 503 khi phụ thuộc ngừng hoạt động), retry có backoff, correlation ID và telemetry.
- Một key bị tái sử dụng với **payload khác** là xung đột nghiệp vụ. Production phải lưu/check hash payload gắn với key để ngăn việc coi hai yêu cầu khác nhau là một đơn.
- Endpoint `/health/ready` trong lab chỉ chứng minh HTTP handler chạy, **chưa kiểm chứng** kết nối Service Bus và dependency. Production cần readiness policy/observability phù hợp, tránh làm health probe gây áp lực không cần thiết lên broker.

## 6. Consumer: PeekLock và settlement tường minh

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

            // LAB: chỉ ghi log, chưa phải xử lý bền vững.
            LOG.info("Processed LAB order id={}, sku={}, quantity={}",
                event.orderId(), event.sku(), event.quantity());

            // Chỉ complete sau khi công việc thực sự thành công.
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

### 6.1 Vì sao cần PeekLock?

Khi nhận một message ở chế độ **PeekLock**, worker có thời gian xử lý trong khoảng lock được cấp. Sau đó:

| Trạng thái | Cách xử lý |
| --- | --- |
| Nghiệp vụ hoàn tất | `complete` để broker loại message khỏi queue |
| Lỗi tạm thời | `abandon` để message có thể được giao lại |
| Payload/phiên bản không thể xử lý | Quyết định `dead-letter` có lý do và quy trình sửa/replay |
| Khóa hết hạn/worker chết | Message có thể được giao lại; worker phải **idempotent** |

`disableAutoComplete()` bắt worker chịu trách nhiệm settlement. `maxAutoLockRenewDuration` giúp SDK gia hạn lock trong phạm vi hỗ trợ, **không** bảo đảm công việc kéo dài vô hạn vẫn giữ lock. Callback có thể bị chạy lại nếu lock mất hoặc complete thất bại; `maxConcurrentCalls` tính **trên mỗi replica**.

Trong ví dụ, mọi exception được `abandon` để minh họa retry. **Production phải phân biệt** lỗi transient (database/network timeout) với lỗi cố định (schema sai, vi phạm business rules) và không retry poison message vô hạn. Service Bus có thể chuyển message vào **DLQ** sau khi vượt `MaxDeliveryCount`, hết TTL theo cấu hình dead-letter tương ứng hoặc do ứng dụng dead-letter chủ động.

### 6.2 Idempotency bền vững cho production

Nếu mở rộng worker để ghi Azure SQL Database, hãy có bảng `ProcessedMessages(message_id UNIQUE, payload_hash)` và bảng `Orders`. Cần thực hiện việc đánh dấu xử lý và cập nhật đơn **trong cùng một DB transaction**:

~~~text
BEGIN TRANSACTION
  INSERT ProcessedMessages(message_id, payload_hash) nếu chưa tồn tại;
  Nếu ID đã tồn tại và hash KHỚP:
    coi là event đã được xử lý, không ghi lại đơn;
  Nếu ID đã tồn tại nhưng hash KHÁC:
    báo xung đột, điều tra; không ghi đè;
  Nếu ID mới:
    INSERT/UPDATE Orders theo quy tắc nghiệp vụ;
COMMIT TRANSACTION
COMPLETE Service Bus message sau khi COMMIT thành công.
~~~

Đoạn trên là **pseudocode**, không phải SQL thực thi. Unique constraint và transaction giúp tránh hai replicas cùng xử lý một event tạo ra đơn trùng. Nếu worker crash **sau DB commit nhưng trước complete**, broker giao lại; worker phát hiện message ID đã xử lý và complete mà không tạo side effect mới.

Nếu side effect là email, thanh toán hay API đối tác **ngoài transaction DB**, cần thêm transactional outbox/inbox, idempotency key do đối tác hỗ trợ và reconciliation. Service Bus broker duplicate detection (nếu bật) không thể thay thế xử lý idempotent trong ứng dụng.

## 7. Đóng gói image để chạy API và worker

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

Đây là multi-stage build để không đưa Maven/toolchain vào runtime image. `-DskipTests` chỉ dùng trong ví dụ build; **CI production phải chạy tests, scan dependency/image/secret, kiểm tra SBOM và provenance**, pin base image/digest và sử dụng tag/digest không thể bị thay thế ngoài quy trình đã duyệt.

**Phân vai:** API dùng `APP_ROLE=api` và HTTP port 8080; worker dùng `APP_ROLE=worker`, `SPRING_MAIN_WEB_APPLICATION_TYPE=none` và **không cần ingress**. Mỗi Container App có thể scale, rollout và rollback độc lập mặc dù image giống nhau.

## 8. Tạo Azure Service Bus, Registry và Container Apps environment

**Các lệnh bên dưới tạo tài nguyên thật và có thể phát sinh phí. Chỉ chạy khi được phê duyệt, trên RG lab riêng.** Ví dụ dùng Azure CLI trong Bash/Cloud Shell:

### 8.1 Đặt biến và chọn subscription

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

Các placeholder cần thay bằng tên thật đúng quy tắc. Dùng **một RG lab không chia sẻ** để dễ kiểm soát cleanup.

### 8.2 Service Bus namespace và queue

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

Tại sao **Standard**? Lab cần queue và dự kiến mở rộng tính năng như duplicate detection hoặc topic/subscription. Tính năng, giới hạn, pricing, networking khác nhau giữa Basic, Standard và Premium; xác minh nhu cầu trước khi chọn tier.

Nếu muốn bật **duplicate detection** theo message ID, kiểm tra tier hỗ trợ, cấu hình khi tạo queue và **history window**. Đây là chức năng giới hạn một số lần gửi trùng **trong cửa sổ broker**, không bảo đảm exactly-once ở DB/side effect. Không bật bằng cách xóa queue production đang có dữ liệu.

### 8.3 ACR và build

~~~bash
az acr create \
  --resource-group "$RG" \
  --name "$ACR" \
  --location "$LOCATION" \
  --sku Basic \
  --admin-enabled false

# Thực hiện trong thư mục orders-lab có Dockerfile và pom.xml.
az acr build --registry "$ACR" --image "$IMAGE_TAG" .
~~~

`az acr build` gửi build context cho ACR Tasks, có thể tính phí và cần đúng quyền. Không bật ACR admin account chỉ để đơn giản hóa xác thực pull; sẽ dùng managed identity. Trong production, chọn image digest bất biến thay vì chỉ tag dễ bị ghi đè.

### 8.4 Container Apps environment

~~~bash
az containerapp env create \
  --resource-group "$RG" \
  --name "$ENV" \
  --location "$LOCATION"
~~~

Kiểm tra Log Analytics destination, retention, quota, network mode và cấu hình môi trường. Environment là ranh giới tài nguyên chạy ứng dụng; **không phải** Service Bus namespace và cũng không tự cấu hình database/virtual network.

## 9. Triển khai hai Container Apps với quyền tối thiểu

### 9.1 Hai identities, hai vai trò dữ liệu

| Danh tính | Quyền Service Bus | Scope gợi ý | Quyền registry |
| --- | --- | --- | --- |
| Identity của API | **Azure Service Bus Data Sender** | Queue `orders` | AcrPull/role pull phù hợp ACR |
| Identity của worker | **Azure Service Bus Data Receiver** | Queue `orders` | AcrPull/role pull phù hợp ACR |

Quyền Azure RBAC để **tạo resource** (control plane) khác quyền **gửi/nhận message** (data plane). Không cấp Data Owner cho cả hai app. Managed identity system-assigned gắn với vòng đời của Container App; nếu xóa app sẽ ảnh hưởng danh tính đó.

### 9.2 Tạo app ban đầu bằng image public, sau đó gán identity

Để tránh dùng ACR admin credential khi app chưa có identity, ví dụ lab dùng một **public bootstrap image** trước khi chuyển sang Orders image. Cách khác cho production là tạo **user-assigned identity** trước, cấp quyền pull rồi đưa identity vào quy trình IaC ngay từ lúc create.

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

Bootstrap image **không phải** Java Orders image; cần xác minh phiên bản image công khai và chính sách registry của tổ chức. Worker không bật ingress vì nó chỉ xử lý queue. Nếu lệnh thay đổi theo phiên bản CLI, hãy đối chiếu `az containerapp create --help` hoặc dùng Portal/IaC tương đương.

### 9.3 Gán Data Sender, Data Receiver và ACR pull

~~~bash
API_PID=$(az containerapp show -g "$RG" -n "$API_APP" \
  --query identity.principalId -o tsv)
WORKER_PID=$(az containerapp show -g "$RG" -n "$WORKER_APP" \
  --query identity.principalId -o tsv)
ACR_ID=$(az acr show -g "$RG" -n "$ACR" --query id -o tsv)
QUEUE_ID=$(az servicebus queue show \
  -g "$RG" --namespace-name "$SB_NS" --name "$QUEUE" \
  --query id -o tsv)

# Kiểm tra các principal IDs và resource IDs không rỗng trước khi chạy.
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

Tạo role assignment cần vai trò quản trị RBAC được ủy quyền; không phải người có quyền deploy app nào cũng có quyền này. Đợi **role propagation** khi vừa cấp quyền. Nếu ACR bật chế độ ABAC/repository-level permissions, `AcrPull` có thể không phải quyền đúng; xác minh authorization mode và vai trò pull được hỗ trợ thay vì tự cấp quyền quản trị registry.

### 9.4 Chuyển sang Orders image

~~~bash
IMAGE="$ACR.azurecr.io/$IMAGE_TAG"

az containerapp registry set -g "$RG" -n "$API_APP" \
  --server "$ACR.azurecr.io" --identity system
az containerapp registry set -g "$RG" -n "$WORKER_APP" \
  --server "$ACR.azurecr.io" --identity system

az containerapp update -g "$RG" -n "$API_APP" --image "$IMAGE"
az containerapp update -g "$RG" -n "$WORKER_APP" --image "$IMAGE"

# Java HTTP API lắng nghe 8080, khác bootstrap image ở port 80.
az containerapp ingress update \
  -g "$RG" -n "$API_APP" --target-port 8080
~~~

Các lệnh trên **thay đổi revision, image và ingress thật**. Việc chuyển image và target port bằng nhiều lệnh riêng có thể gây gián đoạn ngắn trong lab. Production nên chuẩn bị revision phù hợp, kiểm tra readiness và chuyển traffic có điều kiện, không dựa vào một lần `update` rồi coi là zero-downtime.

Kiểm tra revision, identity và logs:

~~~bash
az containerapp show -g "$RG" -n "$API_APP" \
  --query "{fqdn:properties.configuration.ingress.fqdn,identity:identity.principalId}" \
  -o json
az containerapp revision list -g "$RG" -n "$WORKER_APP" -o table
az containerapp logs show -g "$RG" -n "$WORKER_APP" --follow
~~~

Phải xác nhận **revision đang chạy đã dùng Java Orders image và role worker**, không chỉ bootstrap image vẫn đang ở trạng thái healthy.

## 10. Kiểm thử end-to-end

### 10.1 Gửi request thật qua API của lab

~~~bash
API_FQDN=$(az containerapp show -g "$RG" -n "$API_APP" \
  --query properties.configuration.ingress.fqdn -o tsv)

curl -i -X POST "https://$API_FQDN/orders" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: lab-order-001" \
  -d '{"customerId":"demo-customer","sku":"BOOK-01","quantity":2}'
~~~

Response kỳ vọng sau khi broker chấp nhận message (không tự khẳng định môi trường thực của bạn đã chạy):

~~~json
{
  "orderId": "lab-order-001",
  "status": "queued"
}
~~~

**202 Accepted** có nghĩa message đã được gửi thành công theo contract API lab. Nó **không** xác nhận worker đã xử lý hoặc database đã commit. Production cần endpoint truy vấn trạng thái công việc bền vững (ví dụ `GET /orders/{id}`) hoặc cơ chế webhook/event để người dùng biết kết quả cuối cùng.

### 10.2 Đối chiếu worker và broker

Dùng `az containerapp logs show` tìm dòng mẫu:

~~~text
Processed LAB order id=lab-order-001, sku=BOOK-01, quantity=2
~~~

Kiểm tra queue metadata (chú ý một số trường CLI khác theo phiên bản):

~~~bash
az servicebus queue show \
  -g "$RG" --namespace-name "$SB_NS" --name "$QUEUE" \
  --query "{name:name,counts:countDetails,maxDeliveryCount:maxDeliveryCount}" \
  -o json
~~~

Quan sát Azure Service Bus metrics trong Portal: **Active Messages**, **Dead-lettered Messages**, Incoming/Outgoing Messages, errors và throughput. Metrics có độ trễ; số message đang active dao động là bình thường khi gửi và nhận liên tục. Nếu `countDetails` null, xem JSON đầy đủ và metrics của resource thực, không kết luận queue rỗng.

### 10.3 Thử duplicate và retry

1. Gửi lại cùng `Idempotency-Key` và payload. Nếu queue không bật duplicate detection, có thể xuất hiện hai log từ worker. Đây là **minh họa at-least-once**, không phải lỗi của SDK.
2. Trong một lab riêng, thử worker có exception tạm thời trước complete; quan sát delivery count và retry/abandon.
3. Sau nhiều lần lỗi theo `MaxDeliveryCount`, message có thể vào DLQ; kiểm tra lý do và không tự replay lên queue production.
4. Khôi phục worker, xác nhận không còn backlog ngoài dự tính và không có event thử gây side effect thật.

**Không dùng thanh toán, email thật hoặc dữ liệu khách hàng** khi thử lỗi. Muốn kiểm tra duplicate detection của broker, tạo entity lab đúng tier/cấu hình và lịch sử phát hiện thay vì tự thay đổi queue có dữ liệu production.

## 11. Delivery semantics, DLQ, ordering và idempotency

### 11.1 At-least-once là thực tế vận hành

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
    Note over W,SB: Worker crash trước Complete
    SB->>W: Redeliver id=42
    W->>DB: Check processed ID, skip duplicate
    W->>SB: Complete
~~~

Service Bus hỗ trợ duplicate detection khi được bật/tier hỗ trợ **trong một cửa sổ phát hiện giới hạn**, nhưng lỗi crash-after-commit-before-complete vẫn có thể dẫn tới xử lý lại. Side effect chính xác cần idempotency ở tầng ứng dụng/database.

### 11.2 Settlement và DLQ

| Hành động | Ý nghĩa | Sử dụng |
| --- | --- | --- |
| `complete` | Xác nhận đã xử lý, loại message | Sau commit/nghiệp vụ thành công |
| `abandon` | Bỏ lock, message có thể được nhận lại | Lỗi tạm thời; retry có giới hạn |
| `deadLetter` | Chuyển message vào DLQ để điều tra | Payload/schema độc hại hoặc không thể xử lý |
| `defer` | Hoãn message, cần logic nhận lại theo sequence number | Workflow có trạng thái đặc biệt |
| Lock hết hạn | Broker có thể giao lại message | Tăng độ bền và xử lý idempotent |

Nếu message bị lỗi liên tục, DLQ giúp cô lập **poison message** và tránh chặn cả queue. Nhưng **DLQ không tự sửa message**: cần owner, alert, nguyên nhân, chính sách replay và đối soát. Không replay tất cả vào production khi chưa biết side effects.

### 11.3 Ordering

Với nhiều worker replicas/concurrency, **không giả định** queue xử lý theo thứ tự nghiệp vụ. Nếu cần thứ tự theo một đơn hoặc account, tìm hiểu **Service Bus sessions** và session-enabled entity/session processor phù hợp. Quyết định đó tác động tới throughput, parallelism và thiết kế khóa; chỉ thêm `messageId` không bật session.

## 12. Scale worker theo queue backlog

**Container Apps** có thể scale theo event qua KEDA/scaler được hỗ trợ. Với Service Bus, số **active messages** thường được dùng làm tín hiệu tăng số worker replicas.

| Workload | Ingress | Tín hiệu scale | Rủi ro |
| --- | --- | --- | --- |
| API | External HTTPS trong lab | HTTP concurrent requests, CPU/memory | Timeout, tải đột biến, rate limit |
| Worker | **Không ingress** | Queue backlog / Service Bus scaler | Scale quá lớn làm nghẽn SQL hoặc đối tác |

Lab để `min-replicas 1` để dễ kiểm chứng. Khi muốn scale-to-zero, cần có **event-driven scale rule hoạt động đúng**; worker đặt min 0 mà không có scaler có thể không bao giờ chạy lại để xử lý message.

Ví dụ minh họa cú pháp CLI **phụ thuộc phiên bản extension hỗ trợ identity-based scale rules**:

~~~bash
# THAY ĐỔI cấu hình scaling thật; chỉ thử trên lab đã kiểm tra.
az containerapp update \
  -g "$RG" -n "$WORKER_APP" \
  --min-replicas 0 --max-replicas 5 \
  --scale-rule-name orders-backlog \
  --scale-rule-type azure-servicebus \
  --scale-rule-metadata "queueName=$QUEUE" "namespace=$SB_NS" "messageCount=5" \
  --scale-rule-identity system
~~~

Các metadata keys `queueName`, `namespace`, `messageCount`, cờ `--scale-rule-identity` cần đối chiếu `az containerapp update --help` và schema của Container Apps/KEDA ở môi trường đang dùng. **Không đảm bảo** mọi CLI/region/plan đều hỗ trợ cùng cú pháp. Scaler identity cần quyền đọc backlog theo cơ chế xác thực được hỗ trợ; worker Java SDK cần quyền **Data Receiver** để xử lý message. Không tự cấp quyền Owner chỉ để scaler hoạt động.

Nếu scaler không dùng được managed identity trong cấu hình cụ thể, dùng cách xác thực hỗ trợ với secret management của Container Apps/KEDA; không ghi Service Bus connection string vào Git hoặc terminal history.

**Backpressure:** 5 replicas × `maxConcurrentCalls=2` có thể tạo tối đa khoảng **10 callbacks xử lý song song**. Nếu database chỉ cho phép 6 giao dịch đồng thời, tăng replicas có thể làm queue nhanh đầy **hơn** do retry storm. Điều chỉnh max replicas, concurrency, timeout, connection pool, circuit breaker và message age SLO cùng nhau. KEDA có polling/cooldown/cold start nên scaling không tức thời.

## 13. Giám sát và SLO thực tế

### 13.1 Bộ chỉ số tối thiểu

| Nguồn | Chỉ số/tín hiệu | Dùng để |
| --- | --- | --- |
| API | HTTP 2xx/5xx, send failures, p95/p99 latency | Biết API có nhận và enqueue công việc |
| Service Bus | Active Messages, Dead-lettered Messages, incoming/outgoing, throttling | Xem backlog/poison/giới hạn broker |
| Worker | Processed/failed, delivery count, handling duration, complete/abandon failure | Quan sát hành vi consumer |
| ACA | Replica count, restarts, CPU/memory, revision health | Phát hiện scale và runtime lỗi |
| Identity/network | Unauthorized, DNS/TLS, connection timeout, image pull | Khoanh vùng RBAC và kết nối |
| Business (nếu thêm DB) | Order state, duplicate count, end-to-end age | Xác minh tính đúng nghiệp vụ |

**SLO minh họa, không phải SLA Azure:** trong một cửa sổ thử, ≥99,5% `POST /orders` hợp lệ được broker chấp nhận và trả 202. Với production có DB, thêm completion SLO: ≥99% đơn accepted được commit thành công trong 2 phút. **Lab log-only chưa có đủ nguồn dữ liệu để khẳng định completion SLO.**

### 13.2 Logs và KQL

Dùng log stream:

~~~bash
az containerapp logs show -g "$RG" -n "$API_APP" --follow
az containerapp logs show -g "$RG" -n "$WORKER_APP" --follow
~~~

Nếu Container Apps environment cấu hình Log Analytics và workspace có bảng `ContainerAppConsoleLogs_CL`, một ví dụ KQL để đếm **dòng log** worker là:

~~~kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(30m)
| where ContainerAppName_s == "ca-orders-worker"
| where Log_s contains "Processed LAB order"
| summarize ProcessedLogLines = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Tên bảng/cột **phụ thuộc phương thức thu thập và schema workspace**; kiểm tra thực tế trước khi dùng. Một message có thể tạo nhiều log do retry, còn ingestion có thể trễ. Không tính `ProcessedLogLines` thành số order bền vững; nên phát custom metrics/traces có correlation ID và có bảng trạng thái đơn trong production.

### 13.3 Alert và runbook

Cần có alert cho: API 5xx/send failures tăng, queue backlog/oldest message age tăng, DLQ count khác 0/tăng, worker CrashLoop hoặc thiếu replicas, Service Bus auth/throttling và mất log đúng lúc có traffic. Gán người trực, cửa sổ/thời gian quan sát và ngưỡng; phân biệt **không có dữ liệu** với đạt SLO.

Trước production, thử alert delivery, runbook sửa poison message và phân quyền đọc DLQ; không cho phép replay tùy ý dữ liệu thực.

## 14. Bảo mật, CI/CD và rollback

### 14.1 Bảo vệ các đường truy cập

Lab mở external ingress cho API để dễ gọi `curl`; production cần authentication/authorization, validation, rate limiting, secret scanning và có thể dùng private ingress/gateway/WAF theo kiến trúc. Service Bus và ACR nên dùng **managed identity** và quyền tối thiểu; cân nhắc Private Endpoint/VNet/DNS theo **SKU và khả năng hỗ trợ**. Không suy ra mọi tier Service Bus đều có lựa chọn mạng giống nhau.

Không gửi secret/PII vào log, không cấp chung quyền sender+receiver nếu không cần, không mở egress vô hạn để “chữa” DNS/RBAC. Với workload phụ thuộc Azure SQL/Key Vault/Entra ID, kiểm tra endpoint, DNS, network, token và timeout từ revision đang chạy.

### 14.2 Release cùng image digest

~~~mermaid
flowchart LR
    B["CI: build/test/scan"] --> I["ACR image digest"]
    I --> W["Update worker (đọc old/new schema)"]
    W --> P["Update producer/API"]
    P --> T{"SLI, DLQ, backlog đạt?"}
    T -->|Có| O["Promote/quan sát"]
    T -->|Không| R["Dừng + rollback an toàn"]
~~~

Container Apps hỗ trợ **revisions**, nhưng rollback traffic HTTP **không** tự rollback queue schema hay message đã tồn tại. Nếu API v2 phát event trường `currency`, worker v1 phải đọc được event v2 trước khi chuyển ngược; chuẩn bị worker tương thích cả v1/v2, rollout worker trước, rồi producer. Giữ schema version và chính sách tiến hóa **expand–migrate–contract**; không xóa khả năng đọc message cũ khi queue vẫn còn backlog.

### 14.3 Chi phí

| Hạng mục | Yếu tố chi phí |
| --- | --- |
| Container Apps | CPU/memory, request và min/max replicas theo plan |
| Service Bus | Tier, operations/messages/throughput và tính năng |
| ACR | Registry tier, image storage, build tasks |
| Log Analytics / Azure Monitor | Data ingestion, retention, query, alerts |
| Networking | Ingress/egress, private connectivity và load balancing khi áp dụng |
| Database (nếu thêm) | Compute, storage, backup, replication và transaction |

Worker `min-replicas 1` dễ debug nhưng có chi phí idle; scale-to-zero giảm chi phí khi không tải nhưng có cold start và yêu cầu scaler chính xác. Dùng **Cost Management và Pricing Calculator** theo region/tier thật thay vì suy giá từ ví dụ.

### 14.4 Cleanup

Sau lab, kiểm tra resource group **chỉ chứa tài nguyên của bài thực hành** và dữ liệu cần giữ đã được xuất/retention đúng. Nếu được phê duyệt, có thể xóa RG lab:

~~~bash
# NGUY HIỂM: xóa TẤT CẢ tài nguyên trong RG, không phải chỉ hai apps.
az group delete --name "$RG" --yes --no-wait
~~~

Không thực hiện trên RG chia sẻ/production. Theo dõi billing sau cleanup vì Cost Management có độ trễ đồng bộ.

## 15. Troubleshooting thực tế

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| API trả 500/503 khi gửi | Sai FQNS/queue, RBAC Sender, DNS/TLS/AMQP, Service Bus quota | API logs, Service Bus metrics, identity/principal |
| `Unauthorized` | Identity sai, role scope không khớp, role assignment chưa propagate | `principalId`, Data Sender/Receiver, thời gian cấp quyền |
| Pull ACR thất bại | Identity/AcrPull, registry hostname, image tag/digest, network | Revision events và registry settings |
| API chưa ready | Sai target port 8080, Java lỗi, thiếu env vars | Ingress target, revision logs, role API |
| Worker chạy nhưng queue không giảm | `APP_ROLE` sai, processor chưa start, RBAC Receiver, lock/settlement lỗi | Worker logs, counts và callback exceptions |
| Có message trùng | Client retry, lock expired, crash sau DB commit | MessageId, delivery count, unique constraint |
| DLQ tăng | Poison payload, MaxDeliveryCount, TTL, lỗi schema | DLQ reason, schema version, replay có kiểm soát |
| Worker min=0 không thức dậy | Scaler thiếu/sai namespace, queue, identity hoặc quyền | Scale rules, scaler logs, Active Messages |
| Worker scale quá nhiều | max replicas cao, per-replica concurrency lớn, downstream chậm | Throttle worker, DB pool, queues, retries |
| Không thấy logs | Thiếu Log Analytics, ingestion delay, sai schema/query | Log stream, environment destination, workspace |
| Rollback producer nhưng vẫn lỗi | Event đã gửi không tương thích consumer cũ | Dùng schema backward compatible, kiểm tra DLQ |

**Runbook khi có lỗi:** kiểm tra HTTP status → revision/API logs → namespace/queue & Service Bus metrics → worker role/logs → RBAC/identity/network → schema & DB idempotency → rollback/replay an toàn. Thiếu telemetry là **INCONCLUSIVE**, không tự tuyên bố hệ thống khỏe.

## 16. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1: Tính SLI acceptance

Trong 10.000 request hợp lệ, API enqueue thành công 9.980 message, 20 request gặp lỗi. Worker có 9.950 dòng log xử lý nhưng không có database.

**Đáp án:** Acceptance SLI = 9.980 / 10.000 × 100% = **99,8%**. Không thể khẳng định 9.950 đơn đã được tạo bền vững; có thể có duplicate log, retry và ingestion delay. Cần lưu trạng thái đơn trong database và đo end-to-end completion.

### Bài tập 2: Crash sau commit trước complete

Worker xử lý ID `order-42`, commit vào SQL rồi chết trước khi complete. Message được giao lại.

**Đáp án:** Worker phải kiểm tra unique message ID trong cùng transaction tạo/cập nhật đơn. Khi nhận lại, xác nhận payload phù hợp và complete, không tạo order thứ hai. Nếu có gọi payment/email ngoài transaction, cần idempotency của đối tác/outbox và đối soát riêng.

### Bài tập 3: Giới hạn concurrency

Worker có `maxConcurrentCalls=2`, KEDA `max-replicas=5`. Nếu lên đủ 5 replicas có tối đa khoảng **5 × 2 = 10 callbacks** đồng thời, còn database chỉ chịu an toàn 6 giao dịch.

**Đáp án:** Giảm per-replica concurrency hoặc max replicas, cấu hình connection pool/backpressure, đo throughput/latency, tăng database capacity nếu phù hợp. Không scale worker lên vô hạn khi downstream đang quá tải.

### Bài tập 4: Event schema thay đổi

Producer v2 gửi một trường mới bắt buộc nhưng worker v1 không đọc được.

**Đáp án:** Version event contract, triển khai worker đọc cả v1/v2 trước khi chuyển producer, canary theo message queue/DLQ, chỉ bỏ hỗ trợ v1 khi không còn event cũ. Rollback image phải tính cả **event tồn trong queue**, không chỉ bản Container App revision.

### Câu hỏi tự kiểm tra

1. Vì sao API và worker nên có Container Apps và managed identities riêng?
2. HTTP 202 xác nhận điều gì và chưa xác nhận điều gì?
3. Khác biệt giữa Service Bus **Data Sender/Receiver** và Azure quyền tạo resource?
4. `PeekLock` khác `ReceiveAndDelete` như thế nào?
5. Vì sao phải complete **sau** transaction commit?
6. Duplicate detection có tạo exactly-once cho nghiệp vụ hay không?
7. Vì sao worker không cần external ingress? Min replicas bằng 0 cần tính năng nào?
8. Vì sao queue count bằng 0 chưa chứng minh các order đã hoàn tất?
9. Khi nào dùng Service Bus **topic/subscriptions** thay vì một queue?
10. Vì sao rollback producer cần xét version event đã có sẵn trong queue?

### Checklist kết thúc lab

| Hạng mục | Bằng chứng |
| --- | --- |
| Hai Container Apps | API và worker đúng image digest, APP_ROLE |
| Quyền tối thiểu | API Sender, worker Receiver, quyền ACR pull đúng scope |
| Enqueue | POST hợp lệ trả 202, message ID nhất quán |
| Receive | Worker log có ID tương ứng và không có processor lỗi kéo dài |
| Retry/idempotency | Hiểu và mô phỏng delivery lặp; production có kế hoạch transaction |
| DLQ | Biết xem, cảnh báo, xử lý và replay có kiểm soát |
| Scale | Có lựa chọn min/max replicas và backlog rule khi scale-to-zero |
| Monitor | API SLI, queue backlog, worker health, log và chi phí |
| Security | Không lộ token/secret, network và ingress được kiểm soát |
| Cleanup | Xác nhận owner, tài nguyên lab và retention/budget |

**Điểm cần ghi nhớ:** Với microservice Java trên **Azure Container Apps + Service Bus**, bài toán không dừng ở việc hai container gửi/nhận được JSON. Kiến trúc cần tách **chấp nhận yêu cầu** khỏi **hoàn thành nghiệp vụ**, dùng **managed identity và RBAC tối thiểu**, xử lý **at-least-once** bằng idempotency, scale theo backlog có giới hạn, giám sát cả API lẫn queue/worker và có kế hoạch rollback an toàn trước khi nâng cấp event schema.
