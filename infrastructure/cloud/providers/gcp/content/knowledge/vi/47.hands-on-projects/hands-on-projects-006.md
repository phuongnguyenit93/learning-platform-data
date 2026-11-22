# Dự án hàng đợi tác vụ và thông báo với Pub/Sub, Cloud Tasks

Một ứng dụng thương mại điện tử cần gửi thông báo sau khi đơn hàng được xác nhận. Nếu API đặt hàng đồng bộ gọi nhà cung cấp email, lỗi hoặc latency của nhà cung cấp có thể kéo dài HTTP request. Nếu chỉ mở một background thread trong Cloud Run và trả response ngay, công việc có thể mất khi instance dừng. Dự án này kết hợp **Pub/Sub** để phân phối sự kiện và **Cloud Tasks** để điều phối HTTP work với giới hạn tốc độ, retry và xử lý quá tải.

Đây là bài thực hành Google Cloud bằng Java 21, Spring Boot, Cloud Run, Artifact Registry, IAM và Cloud Monitoring. Người học xây dựng hai dịch vụ riêng từ **cùng một container image**:

- **event-router**: nhận Pub/Sub push, kiểm tra dữ liệu và tạo Cloud Task.
- **notification-worker**: nhận Cloud Tasks HTTP POST, mô phỏng gửi thông báo rồi trả trạng thái thành công hoặc thất bại.

Trong bài, Order Service được mô phỏng bằng lệnh publish. Production cần bổ sung transactional outbox, durable idempotency, tích hợp email/SMS provider, quản lý secret và giám sát end-to-end.

## 1. Mục tiêu và tiêu chí hoàn thành

Sau khi học, bạn có thể:

1. Phân biệt Pub/Sub fan-out events với Cloud Tasks directed HTTP work.
2. Tạo Pub/Sub topic, authenticated push subscription và dead-letter topic.
3. Tạo Cloud Tasks queue với max dispatch rate, concurrency và retry policy.
4. Cấu hình Cloud Run IAM để chỉ các workload identities phù hợp được gọi.
5. Viết Java/Spring Boot nhận Pub/Sub envelope và giải mã payload Base64.
6. Tạo Cloud Task có OIDC token, root service audience và task name ổn định.
7. Thiết kế acknowledgement, retry, poison message và xử lý trùng.
8. Kiểm thử happy path, lỗi auth, 503, redelivery và Cloud Tasks retry exhaustion.
9. Đọc logs, metrics, chi phí và dọn tài nguyên sau lab.

**Đầu ra:** sự kiện OrderCreated được Pub/Sub push vào event-router, router enqueue một Cloud Task, Cloud Tasks gọi notification-worker bằng OIDC, worker ghi log mô phỏng và trả HTTP 204.

Các lệnh trong tài liệu là ví dụ để người học thực hiện **trên project lab đã được phê duyệt**; không có lệnh nào được chạy trong bước tạo bài học này.

## 2. Kiến trúc và các lớp trách nhiệm

~~~text
        Order Service (giả lập bằng gcloud pubsub publish)
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

        Push thất bại -> Pub/Sub retry -> Pub/Sub DLQ
        Task thất bại -> Cloud Tasks retry -> xóa sau khi hết policy
                                          -> failure ledger cần thiết
~~~

| Thành phần | Trách nhiệm | Không bảo đảm |
|---|---|---|
| Pub/Sub topic | Fan-out sự kiện nghiệp vụ tới nhiều subscriptions | Exactly-once cho push |
| Push subscription | Gửi HTTP request, retry nếu chưa ACK | Hoàn tất side effect sau khi nhận 2xx |
| event-router | Validate và enqueue task | Gửi email thật, xử lý trùng vĩnh viễn |
| Cloud Tasks | Queue, rate limits, schedule và HTTP retries | Có Pub/Sub-style DLQ |
| notification-worker | Thực hiện side effect và ACK | Đúng một lần nếu không idempotent |
| Cloud Run IAM | Service-to-service authN/authZ cấp nền tảng | Quyền theo customer/tenant |
| Monitoring | Xem backlog, failures, retries | Tự khôi phục nghiệp vụ |

**Khi nào không cần kết hợp?** Nếu chỉ cần một HTTP job cho một worker, Cloud Tasks đơn lẻ đơn giản hơn. Nếu chỉ cần phát events tới nhiều consumers và không có yêu cầu HTTP dispatch rate riêng, Pub/Sub đơn lẻ có thể đủ.

## 3. Giao nhận ít nhất một lần và hai thời điểm ACK

Pub/Sub push coi HTTP status 102, 200, 201, 202 hoặc 204 là acknowledgement. Các mã khác hoặc timeout có thể dẫn tới redelivery.

Cloud Tasks coi HTTP **2xx** từ handler là task hoàn tất. Mã non-2xx, timeout hoặc lỗi kết nối có thể khiến task được retry theo queue policy.

Trong thiết kế này:

- Router **chỉ ACK Pub/Sub sau khi Cloud Tasks xác nhận tạo task** hoặc khi Cloud Tasks báo task cùng business eventId vừa tồn tại.
- Worker **chỉ ACK Cloud Tasks sau khi xử lý thành công** theo định nghĩa nghiệp vụ.
- Trong bài lab, worker chỉ ghi log, nên ACK xác nhận **mô phỏng xử lý**, không phải email thật đã được gửi.

Một phản hồi 204 có thể bị mất trên mạng dù tác vụ đã hoàn tất. Pub/Sub hoặc Cloud Tasks vì thế có thể giao lại. Không có bảo đảm exactly-once side effects chỉ nhờ queue.

### Hai lớp chống trùng

1. **Enqueue dedup:** Cloud Tasks task name dựa trên eventId, giúp tránh tạo trùng trong cửa sổ ghi nhớ task name.
2. **Business idempotency:** Unique eventId trong Cloud SQL/Firestore hoặc idempotency key của email provider để tránh gửi lại dù HTTP request được dispatch lần nữa.

Cloud Tasks có cửa sổ task-name dedup hữu hạn (thường đến 24 giờ với queue dùng API); không dùng nó thay cho durable business ledger.

## 4. Chuẩn bị dự án và ngân sách

Điều kiện:

- Một Google Cloud project dùng riêng cho lab, đã bật billing.
- Người học có quyền bật API, tạo Cloud Run, Pub/Sub, Cloud Tasks, Artifact Registry và IAM resources.
- Cloud Shell Bash hoặc máy có gcloud CLI; Java 21 và Maven 3.9+ nếu build local.
- Region có các dịch vụ trên, ví dụ **asia-southeast1**.
- Ngân sách, cost alert và kế hoạch cleanup sau lab.

Các lệnh bên dưới theo **Bash trong Cloud Shell**; trên Windows PowerShell cần thay cách khai báo biến và quoting.

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

Kiểm tra project, account và project number trước khi tạo gì:

~~~bash
gcloud config set project "$PROJECT_ID"
gcloud auth list
gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)"
~~~

Không thực thi các lệnh thay đổi/xóa resource trong project production.

## 5. Bật APIs và tạo Artifact Registry repository

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

Nếu repository đã tồn tại, kiểm tra location và ownership. Cloud Build service account cần quyền Artifact Registry Writer phù hợp; cấp theo repository thay vì toàn bộ project nếu được.

## 6. Tạo identities và trách nhiệm IAM

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

| Identity | Quyền cần có |
|---|---|
| router-runtime | Cloud Tasks Enqueuer trên đúng queue |
| worker-runtime | Quyền gọi provider/Secret Manager khi tích hợp thật |
| pubsub-push | Cloud Run Invoker trên event-router |
| tasks-caller | Cloud Run Invoker trên notify-worker |
| Pub/Sub service agent | Mint token cho pubsub-push, forward tới DLQ |
| Cloud Tasks service agent | Mint OIDC token cho tasks-caller |
| Deployer | Quyền triển khai và iam.serviceAccounts.actAs theo phạm vi |

Không dùng một service account có Owner trên toàn project cho mọi bước. Người tạo push subscription hoặc tạo task với OIDC có thể cần quyền **iam.serviceAccounts.actAs** trên identity được chỉ định. Ngoài ra, Google-managed service agents cần quyền riêng để mint token.

## 7. Tạo Pub/Sub topics và Cloud Tasks queue

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

Queue có steady-state dispatch limit tối đa 5 task/s và 10 tác vụ đồng thời, gồm cả retries. Cloud Tasks có thể ramp up dần khi queue mới/resume hoặc sau nhiều lỗi 429/5xx; các số này không phải throughput SLA.

Cấp quyền Enqueuer chỉ trên queue:

~~~bash
gcloud tasks queues add-iam-policy-binding "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --member="serviceAccount:$ROUTER_SA" \
  --role="roles/cloudtasks.enqueuer"
~~~

Xem lại:

~~~bash
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$REGION"
~~~

## 8. Một Maven project, hai Spring profiles

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

Dùng Spring Boot profile **router** hoặc **worker** để hai Cloud Run services chỉ tạo những controllers cần thiết dù cùng sử dụng một image.

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

Các version dùng để minh họa. Khi triển khai thực tế, pin phiên bản được tổ chức hỗ trợ, kiểm tra lỗ hổng và chạy tests.

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

Cloud Run đặt **SPRING_PROFILES_ACTIVE=router** hoặc **worker**. Biến queue/project/worker URL chỉ cần cho profile router.

## 9. Sự kiện OrderCreated và Pub/Sub push envelope

OrderCreated chỉ chứa dữ liệu cần thiết, không chứa access token, password hay thẻ thanh toán.

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

Event minh họa:

~~~json
{
  "eventId": "evt-order-1001",
  "orderId": "ORDER-1001",
  "recipientId": "customer-demo-42",
  "template": "ORDER_CONFIRMED"
}
~~~

### PubSubPushEnvelope.java

Pub/Sub push mặc định gửi **JSON envelope**, trong đó message.data là Base64 của payload, không phải JSON OrderCreated thô.

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

Các trường attributes, publishTime và deliveryAttempt có thể xuất hiện nhưng không bắt buộc cho demo. Nếu bật **no-wrapper push**, controller cần đổi hợp đồng request body.

## 10. Quản lý CloudTasksClient trong Spring

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

Client dùng Application Default Credentials (ADC) gắn với Cloud Run router-runtime identity. Không tạo client mới cho từng push request. Spring đóng client khi context kết thúc.

## 11. Java TaskEnqueuer: task name và OIDC

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

Giải thích:

- Router runtime dùng IAM **Cloud Tasks Enqueuer** để tạo task, còn tasks-caller service account được dùng tạo OIDC token khi task được dispatch.
- Target URL có path /tasks/send-notification, nhưng **audience là root URL của worker**.
- Tên task dựa vào hash của business eventId, không dùng ID tuần tự hoặc PII.
- Cloud Tasks trả ALREADY_EXISTS nếu task cùng tên còn tồn tại hoặc vừa thực thi; cơ chế này giúp giảm duplicate enqueue trong cửa sổ hữu hạn.
- Explicit task names tốn lookup hơn tên sinh tự động; cần benchmark nếu throughput lớn.

Không dùng event body để chọn target URL. Cho phép người gửi quyết định task URL tạo nguy cơ SSRF và gửi token tới đích không tin cậy.

## 12. Router chỉ ACK khi enqueue thành công

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
            // Payload sai: Pub/Sub retry và có thể chuyển DLQ.
            return ResponseEntity.badRequest().build();
        } catch (ApiException apiFailure) {
            // Chưa xác nhận tạo task: KHÔNG ACK Pub/Sub.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }
    }
}
~~~

Pub/Sub xem 204 là ACK. Khi Cloud Tasks API lỗi, router trả 503 để Pub/Sub redeliver. Với payload sai, mẫu đơn giản trả 400 và dựa vào Pub/Sub DLQ; production nên có quarantine rõ ràng và không retry vô hạn nếu schema không thể sửa.

Cách bắt ALREADY_EXISTS là dedup **trong cửa sổ task-name**, không bảo đảm chống trùng sau nhiều ngày hoặc khi upstream dùng eventId sai.

## 13. Worker mô phỏng gửi thông báo

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

        // Chỉ mô phỏng, KHÔNG gọi email/SMS provider thật.
        log.info("SIMULATED notification accepted eventId={}", event.eventId());
        return ResponseEntity.noContent().build();
    }
}
~~~

Cloud Tasks xóa task khi worker trả 2xx. Nếu worker trả 503, Cloud Tasks có thể retry theo max attempts/duration và backoff. HTTP 400 cũng là non-2xx nên không có hành vi tự động bỏ qua poison task. Với production, lưu trạng thái lỗi vĩnh viễn vào failure ledger rồi xử lý có chủ đích.

Không tin X-CloudTasks-TaskName hay RetryCount headers như bằng chứng authentication. Cloud Run IAM/OIDC mới là lớp xác thực caller; application còn cần business authorization.

## 14. Đóng gói một container image

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

-DskipTests chỉ được dùng để tập trung vào lab deploy; CI production phải chạy test, security scan và ghi nhận image digest. Không đưa credentials vào Dockerfile.

Từ thư mục notification-demo:

~~~bash
gcloud builds submit --project="$PROJECT_ID" --tag="$IMAGE"
~~~

Image được lưu trong Artifact Registry. Cùng image có thể triển khai thành router/worker với profiles và service accounts khác nhau.

## 15. Deploy notify-worker trước và lấy root URL

Worker được triển khai trước để router biết endpoint cần đưa vào Cloud Task:

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

Lấy URL:

~~~bash
export WORKER_URL="$(gcloud run services describe notify-worker \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format='value(status.url)')"

echo "$WORKER_URL"
~~~

Cấu hình ingress=all cho phép đường mạng tới Cloud Run service URL nhưng **không mở unauthenticated invocation**. IAM Invoker vẫn được kiểm tra. Nếu chọn internal ingress cần thiết kế topology phù hợp cho Cloud Tasks, không chỉ đổi một flag.

Cấp Invoker cho tasks-caller trên đúng receiving service:

~~~bash
gcloud run services add-iam-policy-binding notify-worker \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$TASKS_CALLER_SA" \
  --role="roles/run.invoker"
~~~

Không cấp allUsers hoặc allAuthenticatedUsers cho notify-worker.

## 16. Cho Cloud Tasks service agent quyền mint token

Cloud Tasks có Google-managed service agent:

~~~text
service-PROJECT_NUMBER@gcp-sa-cloudtasks.iam.gserviceaccount.com
~~~

Kiểm tra agent có Cloud Tasks Service Agent role và quyền hoạt động theo tài liệu của dự án. Khi cần, tài liệu authenticated HTTP tasks hướng dẫn cấp Service Account User trên tasks-caller service account để agent tạo token tương ứng:

~~~bash
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" \
  --format='value(projectNumber)')"

gcloud iam service-accounts add-iam-policy-binding "$TASKS_CALLER_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-cloudtasks.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
~~~

Không cấp lại quyền nếu IAM policy đã đủ. Người hoặc runtime tạo task có OIDC identity cũng phải thỏa các quyền iam.serviceAccounts.actAs theo cơ chế Cloud Tasks. Người deploy Cloud Run cần actAs trên router-runtime và worker-runtime theo yêu cầu của Cloud Run.

## 17. Deploy event-router với cấu hình Cloud Tasks

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

Lấy URL để cấu hình Pub/Sub push:

~~~bash
export ROUTER_URL="$(gcloud run services describe event-router \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format='value(status.url)')"

echo "$ROUTER_URL"
~~~

Không để event payload tự xác định Cloud Tasks URL hoặc OIDC audience. URL phải đến từ deployment configuration được kiểm soát, tránh server-side request forgery và token leakage.

## 18. Cấp quyền Pub/Sub push và tạo subscription

Cho pubsub-push SA quyền gọi router:

~~~bash
gcloud run services add-iam-policy-binding event-router \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$PUBSUB_PUSH_SA" \
  --role="roles/run.invoker"
~~~

Pub/Sub service agent có dạng:

~~~text
service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com
~~~

Agent phải có quyền tạo OIDC token cho pubsub-push. Các project mới thường có Pub/Sub Service Agent role với permission tương ứng. Nếu policy hiện tại thiếu quyền, sau khi review có thể grant Token Creator trên đúng SA:

~~~bash
gcloud iam service-accounts add-iam-policy-binding "$PUBSUB_PUSH_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
~~~

Người tạo subscription cũng cần iam.serviceAccounts.actAs trên pubsub-push identity. Không chữa lỗi IAM bằng cách mở event-router unauthenticated.

### Tạo authenticated push subscription

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

Pub/Sub đẩy HTTP request vào URL có path /events/orders. OIDC audience của token được đặt thành **root URL** của receiving Cloud Run service. Nếu audience sai, Cloud Run có thể từ chối ngay cả khi SA có Invoker.

Push subscription ở đây dùng JSON wrapper mặc định; không bật no-wrapper. Retry policy exponential backoff không loại trừ các giới hạn push backoff khác khi endpoint nhiều lỗi.

## 19. Cấu hình Pub/Sub dead-letter topic

Cloud Tasks không có Pub/Sub-style DLQ mặc định, nhưng Pub/Sub subscription có thể chuyển message hỏng sang dead-letter topic sau một số delivery attempts best effort.

Tạo pull subscription để người vận hành có thể kiểm tra DLQ:

~~~bash
gcloud pubsub subscriptions create "$DLQ_SUB" \
  --project="$PROJECT_ID" \
  --topic="$DLQ_TOPIC"
~~~

Cấp Pub/Sub service agent quyền publish vào dead-letter topic và subscribe nguồn:

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

Bật DLQ và giới hạn attempts:

~~~bash
gcloud pubsub subscriptions update "$PUSH_SUB" \
  --project="$PROJECT_ID" \
  --dead-letter-topic="$DLQ_TOPIC" \
  --max-delivery-attempts=10
~~~

Kiểm tra:

~~~bash
gcloud pubsub subscriptions describe "$PUSH_SUB" \
  --project="$PROJECT_ID"
~~~

Pub/Sub có thể chuyển DLQ sau số attempts hơi khác cấu hình do cơ chế best effort. Message DLQ được gói lại và có thêm metadata nguồn; không xem DLQ như một copy chính xác của event đầu vào nếu chưa parse wrapper.

## 20. Kiểm thử happy path: OrderCreated

Publish một sự kiện giả bằng Cloud Shell:

~~~bash
gcloud pubsub topics publish "$TOPIC" \
  --project="$PROJECT_ID" \
  --message='{"eventId":"evt-order-1001","orderId":"ORDER-1001","recipientId":"customer-demo-42","template":"ORDER_CONFIRMED"}'
~~~

Luồng mong đợi:

1. Pub/Sub nhận event và gửi push envelope kèm OIDC token.
2. Cloud Run IAM xác thực pubsub-push SA có Invoker trên event-router.
3. Router decode Base64, kiểm tra các trường và gọi Cloud Tasks API.
4. Cloud Tasks xác nhận task có tên hash từ eventId.
5. Router trả 204; Pub/Sub ACK message.
6. Cloud Tasks dispatch POST tới worker với OIDC token của tasks-caller.
7. Cloud Run IAM xác thực tasks-caller SA có Invoker trên notify-worker.
8. Worker ghi log mô phỏng rồi trả 204; task hoàn tất và bị xóa khỏi queue.

Xem Cloud Run logs:

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

Log mô phỏng chứng minh handler đã xử lý, **không chứng minh đã gửi email thật**. Nên bổ sung trace/event correlation trong production để liên kết eventId, task name và provider response mà không ghi token hoặc PII.

## 21. Kiểm thử duplicate publish

Gửi lại một event với **cùng eventId**:

~~~bash
gcloud pubsub topics publish "$TOPIC" \
  --project="$PROJECT_ID" \
  --message='{"eventId":"evt-order-1001","orderId":"ORDER-1001","recipientId":"customer-demo-42","template":"ORDER_CONFIRMED"}'
~~~

Nếu task vừa được tạo/hoàn tất trong cửa sổ Cloud Tasks ghi nhớ task name, createTask có thể trả ALREADY_EXISTS. Router coi đó là task trùng đã tạo và ACK Pub/Sub.

Cơ chế này **không bảo vệ sau khi cửa sổ dedup hết hạn**, cũng không ngăn Cloud Tasks dispatch lặp cùng task khi worker response bị mất. Một hệ thống gửi email thật cần durable ledger theo business eventId và provider idempotency key nếu được hỗ trợ.

### Vì sao chọn business eventId thay vì Pub/Sub messageId?

Pub/Sub messageId ổn định khi cùng message bị redeliver nhưng mỗi lần publisher phát lại event có thể nhận messageId mới. Business eventId cho phép khử trùng giữa những lần publish khác nhau của cùng một sự kiện nghiệp vụ.

## 22. Kiểm thử poison message và Pub/Sub DLQ

Gửi message không hợp lệ:

~~~bash
gcloud pubsub topics publish "$TOPIC" \
  --project="$PROJECT_ID" \
  --message='not-json'
~~~

Router không parse được và trả 400. Pub/Sub retry và, nếu DLQ/IAM đúng, chuyển tới dead-letter topic sau số attempts gần ngưỡng.

Đọc DLQ:

~~~bash
gcloud pubsub subscriptions pull "$DLQ_SUB" \
  --project="$PROJECT_ID" \
  --limit=5
~~~

Không tự động ACK khi đang điều tra. Sau khi ghi nhận nguyên nhân và có kế hoạch quarantine/replay, xử lý acknowledgement theo runbook.

### Hướng xử lý

- Nếu schema sai vĩnh viễn, không replay mù quáng.
- Nếu lỗi là do version incompatibility, nâng cấp consumer và kiểm thử trước khi replay.
- Nếu dữ liệu chứa bí mật hoặc thông tin nhạy cảm, kiểm soát quyền truy cập DLQ.
- Ghi số lượng DLQ messages và tuổi message vào dashboard.
- Có owner và quy trình xử lý/quarantine định kỳ.

## 23. Kiểm thử Cloud Tasks HTTP retry

Worker trả HTTP 503 khi orderId là FAIL-DEMO. Publish event sau:

~~~bash
gcloud pubsub topics publish "$TOPIC" \
  --project="$PROJECT_ID" \
  --message='{"eventId":"evt-fail-demo-1","orderId":"FAIL-DEMO","recipientId":"customer-demo-42","template":"ORDER_CONFIRMED"}'
~~~

Router vẫn tạo task và ACK Pub/Sub. Cloud Tasks nhận 503 từ worker, sau đó retry theo max-attempts/max-retry-duration và backoff của queue.

Quan sát queue:

~~~bash
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$REGION"

gcloud tasks list \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --queue="$QUEUE"
~~~

Lệnh gcloud tasks list yêu cầu queue và location như ví dụ. Task đã thành công có thể biến mất nhanh khỏi danh sách vì Cloud Tasks xóa sau khi hoàn tất.

### Khi hết retry

Cloud Tasks có thể dừng retry và xóa task khi chạm max attempts/duration hoặc giới hạn retention. Không có dead-letter topic tự động tương đương Pub/Sub DLQ. Để không mất dấu lỗi, worker phải ghi trạng thái bền và có alert/failure ledger ngoài queue.

## 24. Thiết kế idempotency và failure ledger cho production

Một mô hình trạng thái:

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
      retry budget hết
           |
           v
      PERMANENT_FAILED
~~~

Các phương án:

| Phương án | Lợi ích | Giới hạn |
|---|---|---|
| Cloud Tasks task name | Dedup ngắn hạn khi enqueue | Không ngăn duplicate dispatch hoặc replay dài hạn |
| SQL unique index | Ngăn nhiều records cùng eventId | Phải xử lý lease/crash giữa các bước |
| Firestore document ID | Durable ledger thuận tiện | Cần transaction và conditional update |
| Provider idempotency key | Giảm gửi trùng bên ngoài | Phụ thuộc API của provider |
| Transactional outbox | Tránh commit order rồi bỏ lỡ publish | Vẫn cần idempotent consumer |

Không ghi SENT trước khi gửi rồi nghĩ rằng đã có email. Nếu crash giữa bước ghi và gọi provider, thông báo bị mất. Ngược lại, provider có thể xử lý xong nhưng response mất, khiến retry gửi trùng. Thiết kế tốt cần reconciliation và idempotency support ở provider nếu có.

## 25. Bảo mật service-to-service

~~~text
Pub/Sub agent ---> OIDC token cho pubsub-push SA
pubsub-push SA ---> Invoker event-router
router-runtime SA ---> Enqueuer notification-delivery queue
Cloud Tasks agent ---> OIDC token cho tasks-caller SA
tasks-caller SA ---> Invoker notify-worker
worker-runtime SA ---> secrets/provider API theo phạm vi
~~~

Kiểm thử:

| Tình huống | Kỳ vọng |
|---|---|
| Gọi router từ internet không có token | Bị Cloud Run IAM từ chối |
| Dùng tasks-caller để gọi router | Bị từ chối nếu không có Invoker |
| Dùng pubsub-push để gọi worker | Bị từ chối nếu không có Invoker |
| Token với audience của service khác | Bị từ chối |
| Router mất quyền createTask | Pub/Sub push không được ACK |
| Task body chứa URL lạ | Không đổi worker target |
| Header X-CloudTasks-TaskName bị giả mạo | Không thay IAM authentication |

Dùng Secret Manager nếu tích hợp email provider. Không đưa API keys vào Pub/Sub payload hoặc task body. Phân tách identity runtime và identity dùng để invoke Cloud Run.

## 26. Monitoring và SLO cho hàng đợi

| Nguồn | Chỉ số | Điều cần biết |
|---|---|---|
| Pub/Sub | Undelivered messages | Router có theo kịp producer? |
| Pub/Sub | Oldest unacked message age | Có message đang bị kẹt? |
| Pub/Sub | Push errors, DLQ count | Có lỗi IAM/schema kéo dài? |
| Cloud Tasks | Queue depth, attempts, dispatch rate | Worker có nghẽn? |
| Cloud Tasks | 429/503, retry count | Downstream có quá tải? |
| Cloud Run | 5xx và p95/p99 request latency | Router/worker có ổn định? |
| Java | Heap, GC, thread/connection pools | Có resource saturation? |
| Ledger | PENDING/SENT/FAILED | Business notification hoàn tất chưa? |
| Billing | Pub/Sub/Tasks/Run/Logging | Retry storm tạo chi phí bao nhiêu? |

Các SLO minh họa:

- Trên 99,9% valid events được enqueue thành công theo cửa sổ đo.
- Event-to-task enqueue p95 dưới 3 giây khi hệ thống khỏe.
- Task processing p95 dưới 60 giây khi provider sẵn sàng.
- Permanent notification failures dưới ngưỡng được business owner phê duyệt.

Những con số này chỉ dùng cho bài tập, không phải SLA tự động của Pub/Sub/Cloud Tasks. Gắn logs/traces với eventId và task name nhưng không dùng token hoặc PII làm metrics labels.

## 27. Chi phí và FinOps

Nguồn chi phí có thể gồm:

- Pub/Sub publish, delivery, retention và dead-letter traffic.
- Cloud Tasks operations, retry attempts và queue logging.
- Cloud Run CPU/memory/requests, min instances nếu cấu hình.
- Artifact Registry images và Cloud Build.
- Logging/Monitoring retention.
- Database ledger, email provider và egress khi tích hợp thật.

~~~text
Cost per successful notification
  = (Pub/Sub + Cloud Tasks + Cloud Run + Logs
     + Ledger + Provider + Egress)
    / số thông báo thực sự gửi thành công
~~~

Một task lỗi 503 bị retry nhiều lần tạo thêm HTTP requests và logs dù không đem lại giá trị nghiệp vụ. Tối ưu bằng rate limits, backoff, idempotency, DLQ/quarantine và monitoring lỗi thay vì chỉ tăng worker instances.

Không dùng giá cố định trong bài; kiểm tra Google Cloud Pricing Calculator và billing SKUs theo project/region hiện hành.

## 28. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Pub/Sub push 401/403 | SA thiếu Invoker hoặc token/audience sai | Pub/Sub push config, Cloud Run IAM, service agent |
| Router 503 | Cloud Tasks API/IAM/quota lỗi | Queue policy, runtime identity, logs |
| Task HTTP 401/403 | tasks-caller thiếu Invoker hoặc audience sai | OIDC config và worker service URL |
| Task không dispatch | Queue paused, backoff, rate limit, scheduleTime | Queue state, tasks, metrics |
| Event bị giao lại nhiều lần | Router trả non-2xx hoặc 204 bị mất | HTTP logs, task-name dedup |
| Notification gửi trùng | Thiếu durable idempotency | Business ledger và provider request ID |
| DLQ không nhận message | Pub/Sub agent chưa có IAM phù hợp | Dead-letter policy, topic/subscription permissions |
| Task biến mất dù chưa gửi | Retry exhausted hoặc worker trả 2xx quá sớm | Failure ledger, worker semantics |
| 429 tăng | Rate limit/worker/provider không phù hợp | Queue rate và retry budget |
| Worker không start | Profile, PORT, JDK hoặc env sai | Cloud Run revision logs |
| Chi phí tăng | Retry storm, logs hoặc provider requests | Billing và task attempts |

## 29. Dọn tài nguyên bài lab

Các lệnh sau **xóa resource thật**, chỉ chạy trong project lab sau khi kiểm tra owner và xác nhận không còn dữ liệu cần giữ.

Xóa subscriptions để ngừng push:

~~~bash
gcloud pubsub subscriptions delete "$PUSH_SUB" "$DLQ_SUB" \
  --project="$PROJECT_ID"
~~~

Xóa queue (pending tasks sẽ mất):

~~~bash
gcloud tasks queues delete "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$REGION"
~~~

Xóa Cloud Run services:

~~~bash
gcloud run services delete event-router \
  --project="$PROJECT_ID" \
  --region="$REGION"

gcloud run services delete notify-worker \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

Xóa topics và repository chỉ thuộc bài lab:

~~~bash
gcloud pubsub topics delete "$TOPIC" "$DLQ_TOPIC" \
  --project="$PROJECT_ID"

gcloud artifacts repositories delete "$REPO" \
  --project="$PROJECT_ID" \
  --location="$REGION"
~~~

Chỉ xóa bốn service accounts nếu không có workload khác phụ thuộc. **Không xóa Google-managed Pub/Sub/Cloud Tasks service agents.** Sau cleanup kiểm tra Cloud Billing và các resource còn tồn tại.

## 30. Bài tập mở rộng

### Bài A — Lập lịch thông báo

Dùng Cloud Tasks scheduleTime để gửi thông báo sau 30 phút, không dùng Thread.sleep trong HTTP handler. Kiểm tra task không chạy trước lịch.

### Bài B — Sandbox email provider

Tích hợp API sandbox và Secret Manager, có idempotency key, timeout, retry classification và không gửi tới người nhận ngoài phạm vi lab.

### Bài C — Durable ledger

Sử dụng Firestore hoặc Cloud SQL để lưu trạng thái PENDING/SENT/FAILED, thiết kế lease và recovery sau crash; thử hai dispatch cùng eventId.

### Bài D — Fan-out thêm Analytics

Tạo subscription thứ hai của Pub/Sub cho Analytics. Kiểm tra một event được nhiều consumers nhận độc lập.

### Bài E — Diễn tập IAM outage

Trong staging, tạm thay đổi Invoker permission rồi xác minh 401/403 và backlog; rollback IAM và kiểm tra recovery theo runbook.

## 31. Tiêu chí nghiệm thu

| Tiêu chí | Bằng chứng |
|---|---|
| Topics/queue | Describe/list chính xác các resources đã tạo |
| Identity | Bốn SA riêng, IAM scope đúng |
| Event routing | Router enqueue task sau khi nhận push |
| Worker dispatch | Log mô phỏng chứa eventId |
| Authentication | Các negative tests bị từ chối đúng |
| Pub/Sub DLQ | Invalid JSON được retry rồi forward khi đủ điều kiện |
| Cloud Tasks retry | FAIL-DEMO trả 503 và có retries |
| Duplicate | Một eventId không tạo hai tasks trong dedup window |
| Observability | Metrics cho queue, errors, backlog và latency |
| FinOps | Giải thích ảnh hưởng retry tới chi phí |
| Cleanup | Resources lab được xóa hoặc có retention owner |

## Kết luận

**Pub/Sub** giải quyết bài toán phân phối sự kiện bất đồng bộ và fan-out; **Cloud Tasks** điều phối HTTP tasks tới một handler với rate, concurrency, scheduling và retry. Mô hình OrderCreated → Pub/Sub push → event-router → Cloud Tasks → notification-worker giúp checkout không phải chờ nhà cung cấp email. Nhưng độ tin cậy end-to-end cần **ACK đúng lúc, IAM/OIDC đúng audience, idempotency, Pub/Sub DLQ, Cloud Tasks failure ledger và monitoring**. Khi vận hành tốt, mẫu kiến trúc có thể mở rộng cho thông báo, xuất báo cáo, đồng bộ dữ liệu và các công việc hậu xử lý khác.

## Tài liệu tham khảo

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


