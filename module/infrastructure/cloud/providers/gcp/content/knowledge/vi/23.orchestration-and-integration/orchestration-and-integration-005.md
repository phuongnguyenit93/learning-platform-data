# Cloud Tasks và quản lý hàng đợi tác vụ HTTP trên Google Cloud

> **Chương:** Điều phối và tích hợp ứng dụng  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Khi một API đặt hàng phải gửi biên nhận, cập nhật hệ thống đối tác hoặc gọi một webhook có tốc độ giới hạn, xử lý ngay trong request của người dùng dễ làm tăng độ trễ và gây lỗi dây chuyền. **Cloud Tasks** tách thời điểm **đăng ký công việc** khỏi thời điểm **gọi HTTP worker**: producer đưa một task vào hàng đợi, Google Cloud điều tiết tốc độ, lên lịch, gọi endpoint và thử lại khi chưa nhận phản hồi thành công.

Bài học tập trung vào **HTTP target queues** gọi **Cloud Run**. Ví dụ dùng một ứng dụng **Java/Spring Boot** nhận lệnh chuẩn bị biên nhận; lab chứng minh enqueue, dispatch, xác thực OIDC, retry và quan sát. Phần cuối trình bày cách thêm **idempotency bền vững** trước khi biến ví dụ thành quy trình gửi email/thanh toán thực.

**Phạm vi an toàn:** lệnh tạo queue, IAM và Cloud Run có thể tạo tài nguyên tính phí; chỉ chạy trong project lab được cấp quyền. Không gửi thông tin thẻ, mật khẩu, access token hoặc PII vào task payload/log. Ví dụ worker chỉ ghi log sự kiện giả lập, **không gửi email thật**.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Cloud Tasks, Pub/Sub, Eventarc và Workflows** theo nhu cầu điều phối.
2. Hiểu queue, task, schedule time, HTTP target, attempt, retry, rate/concurrency limits và dispatch deadline.
3. Thiết lập một queue trong region, chọn giới hạn dispatch phù hợp năng lực Cloud Run worker.
4. Xác thực HTTP task bằng **OIDC ID token** và phân quyền **Enqueuer, Invoker, service agent**.
5. Viết handler Java/Spring Boot nhận JSON, kiểm tra đầu vào và trả mã HTTP theo mô hình ACK/retry.
6. Đưa task vào queue bằng **gcloud** hoặc Java Cloud Tasks SDK, kể cả lên lịch trì hoãn.
7. Thiết kế **idempotency key**, xử lý duplicate dispatch và sự cố timeout giữa worker với queue.
8. Kiểm tra backlog, lỗi 429/503, retry, logging, chi phí và quản trị vòng đời queue.
9. Thực hiện lab, bài tập và dọn đúng những tài nguyên mình sở hữu.

## 1. Kiến trúc: producer không phải worker

~~~mermaid
sequenceDiagram
    participant U as Client
    participant API as Orders API (producer)
    participant Q as Cloud Tasks queue
    participant W as Cloud Run Java worker
    participant DB as Durable job store (production)
    U->>API: POST /orders
    API->>Q: CreateTask(jobId, payload, target, OIDC)
    Q-->>API: Task resource accepted
    API-->>U: 202 Accepted / order received
    Q->>W: HTTPS POST /tasks/receipt
    W->>DB: Atomic idempotency/business outcome
    DB-->>W: Created or already processed
    W-->>Q: HTTP 2xx acknowledgment
    Note over Q,W: Non-2xx / no response → retry according to policy
~~~

**Cloud Tasks không tự chạy Java code.** Nó gửi request tới endpoint được cấu hình. Cloud Run, GKE, Compute Engine hoặc HTTP service khác mới là nơi xử lý nghiệp vụ.

| Thành phần | Vai trò | Trách nhiệm không thuộc nó |
|---|---|---|
| **Producer** | Xác nhận yêu cầu, tạo task với target/payload | Không chờ worker xử lý xong trước khi trả kết quả nếu muốn async |
| **Queue** | Lưu task, lên lịch, giới hạn dispatch và retry | Không hiểu nghiệp vụ, không có transaction với database của producer |
| **Task** | Một đơn vị công việc và HTTP request cụ thể | Không tự đảm bảo chỉ một lần gây side effect |
| **HTTP handler/worker** | Kiểm tra request, xử lý và trả HTTP status | Không nên dùng bộ nhớ instance để ghi trạng thái lâu dài |
| **Durable store** | Trạng thái nghiệp vụ, idempotency, kết quả job | Không do Cloud Tasks tự tạo |
| **Cloud Monitoring/Logging** | Theo dõi backlog, attempts, errors, latency | Không thay thế thiết kế khôi phục sau task bị loại |

### 1.1. Một task có vòng đời như thế nào?

~~~mermaid
flowchart TD
    NEW["Producer CreateTask"] --> WAIT["Task ở queue\nchờ scheduleTime & capacity"]
    WAIT --> SEND["HTTP dispatch attempt"]
    SEND --> RESP{"Worker trả gì?"}
    RESP -->|"HTTP 2xx"| DONE["ACK: Cloud Tasks xóa task"]
    RESP -->|"Non-2xx / timeout / network error"| RETRY{"Còn trong giới hạn retry/retention?"}
    RETRY -->|"Có"| BACK["Exponential backoff + throttling"]
    BACK --> SEND
    RETRY -->|"Không"| DROP["Task bị loại khỏi queue\ncần cơ chế audit/recovery riêng"]
~~~

**Mã HTTP 2xx có nghĩa task hoàn thành đối với Cloud Tasks**, nên task bị xóa khỏi queue. Các mã **khác 2xx** hoặc không có phản hồi được xem là attempt thất bại và có thể được retry theo policy. Đặc biệt, HTTP 400/401/403/404 không được “bỏ qua vĩnh viễn” theo mặc định: chúng cũng có thể dẫn tới lặp lại cho tới khi đạt giới hạn.

Nếu worker đã ghi dữ liệu thành công nhưng response bị mất do mạng hoặc dispatch deadline, Cloud Tasks **có thể gọi lại**. Vì vậy **retry và idempotency phải được thiết kế cùng nhau**.

## 2. Khi nào dùng Cloud Tasks thay vì Pub/Sub, Eventarc hoặc Workflows?

| Nhu cầu | Công cụ thường phù hợp | Lý do |
|---|---|---|
| Gọi **một HTTP endpoint đã biết** sau khi nhận đơn hàng | **Cloud Tasks** | Producer quyết định đích, lịch, rate, retries |
| Gửi webhook tới đối tác có giới hạn 5 request/s | **Cloud Tasks** | Điều tiết steady-state dispatch và concurrency |
| Chờ 10 phút rồi gọi endpoint xác nhận | **Cloud Tasks** | Hỗ trợ scheduleTime cho từng task |
| Phát một business event cho **nhiều** subscribers | **Pub/Sub** | Fan-out, implicit invocation và subscriptions |
| Bắt sự kiện Cloud Storage finalized rồi gọi service | **Eventarc** | Event routing từ sources được hỗ trợ |
| Điều phối **nhiều bước có điều kiện**, chờ, rẽ nhánh, gọi APIs | **Workflows** | State machine/orchestration có trace từng bước |
| Stream dữ liệu khối lượng lớn hoặc consumer chủ động pull | **Pub/Sub** | Subscription/flow-control, không giới hạn theo endpoint cụ thể của mỗi task |
| Job kéo dài ngoài HTTP dispatch deadline | **Cloud Run Jobs / Batch / Workflows** | Chạy tác vụ dài và theo dõi completion riêng |

Cloud Tasks và Pub/Sub đều có thể giao lặp. **Cloud Tasks không cung cấp ordering guarantee**: trình tự thêm task được giữ theo nỗ lực tối đa, nhưng retry, scheduling và concurrency có thể làm task sau hoàn tất trước task trước. Nếu nghiệp vụ cần thứ tự trên từng đơn hàng, hãy dùng **sequence/version checks** hoặc kiến trúc ordered processing.

**Khác biệt về DLQ:** Pub/Sub có dead-letter topic/policy ở subscription; **Cloud Tasks HTTP queue không có DLQ tích hợp tương đương**. Với công việc cần điều tra sau khi hết retry, ứng dụng phải lưu job state bền vững, phát cảnh báo và tổ chức replay/quarantine phù hợp. Không tuyên bố một task sẽ tự chuyển sang Pub/Sub DLQ chỉ vì cấu hình maxAttempts.

## 3. Khái niệm và giới hạn quan trọng

Một task HTTP có thể mô tả như sau:

~~~text
Queue:
projects/commerce-lab/locations/asia-southeast1/queues/receipt-http

Task:
projects/commerce-lab/locations/asia-southeast1/queues/receipt-http/tasks/JOB_HASH

HTTP:
POST https://receipt-worker-...run.app/tasks/receipt
Content-Type: application/json
Authorization: Bearer <OIDC token do Cloud Tasks phát>
Body: {"jobId":"demo-001","orderId":"ord-1001"}

scheduleTime: now hoặc một thời điểm tương lai
dispatchDeadline: thời hạn chờ phản hồi của một HTTP attempt
~~~

Các tên **commerce-lab** và URL worker ở trên chỉ minh họa, không phải tài nguyên thực.

| Thuộc tính | Quy tắc vận hành |
|---|---|
| Queue location | **Regional**; khai báo rõ project/region khi thao tác |
| Max task size | **1 MiB** bao gồm payload và phần metadata áp dụng |
| Max schedule time | **30 ngày** tính từ lúc tạo task |
| Max retention | **31 ngày** tính từ lúc task được thêm, kể cả retries |
| HTTP dispatch deadline | Mặc định **10 phút**; cấu hình từ **15 giây đến 30 phút** |
| Max HTTP queue rate | **500 task dispatches/giây/queue** ở giới hạn hệ thống hiện hành |
| Deduplication tên task | Có thể giữ dấu vết tên task đã xóa/thực thi **tới 24 giờ** ở queue API-created |
| Queue re-creation | Tên queue đã xóa có thể cần **3 ngày** mới tạo lại được |
| HTTP success | Bất kỳ **2xx** nào |
| HTTP failure | Non-2xx hoặc không có phản hồi trước deadline |
| Execution semantics | Hướng tới xử lý một lần nhưng **duplicate execution vẫn có thể xảy ra** |

Các giới hạn nêu theo tài liệu Cloud Tasks hiện hành; khi triển khai phải đối chiếu quota/project/region và [Quotas and limits](https://docs.cloud.google.com/tasks/docs/quotas).

### 3.1. Đừng nhầm ba loại thời gian

- **scheduleTime:** thời điểm sớm nhất task đủ điều kiện dispatch; **không phải hứa sẽ chạy đúng từng mili-giây**.
- **dispatchDeadline:** Cloud Tasks chờ một HTTP attempt bao lâu trước khi coi attempt hết hạn. Worker vẫn có thể tiếp tục xử lý side effect sau khi client hết chờ: phải thiết kế idempotency.
- **maxRetryDuration/maxAttempts:** giới hạn retry của task. Theo mô hình Cloud Tasks, task chỉ bị loại theo retry limits khi **cả hai điều kiện giới hạn áp dụng đều đạt**, hoặc do retention; tránh hiểu chỉ chạm maxAttempts là nhất thiết bị xóa tức thì.

**Khác với timeout Cloud Run:** request timeout của Cloud Run và dispatchDeadline của Cloud Tasks là hai cài đặt. Nếu worker có thể mất 90 giây, cả hai phải cho phép thời gian hợp lý và vẫn cần timeout cho downstream calls.

### 3.2. Task name không thay database uniqueness

Khi producer chỉ định **task ID** cố định, Cloud Tasks có thể trả **ALREADY_EXISTS** nếu cùng ID đang chờ hoặc mới được xử lý/xóa gần đây. Đây là biện pháp giảm tạo trùng **ở cửa vào queue**, không phải khóa idempotency vĩnh viễn.

Với task IDs, dùng định danh hash hoặc phân bố đều, tránh ID tuần tự dài vì có thể làm tăng độ trễ lookup. Cần ổn định **jobId theo yêu cầu nghiệp vụ**, còn task ID có thể là hash của jobId và operation/version.

## 4. Kịch bản thực hành: chuẩn bị biên nhận đơn hàng

Ta tạo hai thành phần:

- **Cloud Run worker receipt-worker-lab**, private, nhận **POST /tasks/receipt** với JSON nhỏ.
- **Cloud Tasks queue receipt-http-lab**, giới hạn 2 dispatch/s và tối đa 3 attempts đồng thời.

Producer dùng **gcloud tasks create-http-task** hoặc Java Cloud Tasks client. Worker lab **chỉ ghi log giả lập**, nhằm chứng minh giao task và HTTP acknowledgment; production phải thay bằng thao tác nghiệp vụ **bền vững, chống trùng** rồi mới trả 2xx.

| Thông số | Giá trị ví dụ | Ý nghĩa |
|---|---|---|
| PROJECT_ID | YOUR_PROJECT_ID | Project được phép dùng |
| LOCATION | asia-southeast1 | Region hỗ trợ Cloud Tasks và Cloud Run |
| QUEUE | receipt-http-lab | Queue HTTP |
| SERVICE | receipt-worker-lab | Cloud Run private worker |
| DISPATCH_SA | receipt-dispatcher@PROJECT_ID.iam.gserviceaccount.com | Identity được dùng tạo OIDC token gọi worker |
| RUNTIME_SA | receipt-runtime@PROJECT_ID.iam.gserviceaccount.com | Identity của code worker khi gọi Google APIs |
| POST endpoint | SERVICE_URL/tasks/receipt | Target URL, không có public invocation |
| Payload | {"jobId":"demo-001","orderId":"ord-1001"} | Không chứa dữ liệu nhạy cảm |

**Trình tự an toàn:** kiểm tra project/context → tạo service accounts và IAM → deploy worker private → tạo queue và rate/retry policy → enqueue task → xem logs/metrics → dọn lab. Không tạo Cloud Tasks queue cho production để chạy bài học.

## 5. Preflight: API, project, identity và mạng

### 5.1. Xác minh project trước mọi thay đổi

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"
QUEUE="receipt-http-lab"
SERVICE="receipt-worker-lab"

gcloud auth list
gcloud config list
gcloud projects describe "$PROJECT_ID"

# CHỈ ĐỌC — liệt kê queue/Cloud Run trong region.
gcloud tasks queues list --location="$LOCATION" --project="$PROJECT_ID"
gcloud run services list --region="$LOCATION" --project="$PROJECT_ID"

# CHỈ ĐỌC — kiểm tra các API đang bật.
gcloud services list --enabled --project="$PROJECT_ID"
~~~

Đảm bảo region hỗ trợ **Cloud Tasks** và **Cloud Run**; queue là tài nguyên theo vùng, không dùng vùng gần đúng khi đặt task. Khi có nhiều project, luôn truyền **--project** và **--location/--region** trên các lệnh thay đổi để tránh sửa tài nguyên khác.

### 5.2. Bật APIs nếu được phê duyệt

~~~bash
# THAY ĐỔI PROJECT, có thể phát sinh phí khi sử dụng.
gcloud services enable \
  cloudtasks.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="$PROJECT_ID"
~~~

Cloud Run source deployment sẽ dùng **Cloud Build/buildpacks** và lưu image trong Artifact Registry. Build identity cần quyền **Cloud Run Builder** hoặc quyền phù hợp theo Cloud Run source build; deployer có thể cần **roles/run.sourceDeveloper**, **roles/serviceusage.serviceUsageConsumer** và **roles/iam.serviceAccountUser** trên runtime service account.

### 5.3. Bốn danh tính độc lập

| Danh tính | Quyền tối thiểu | Giai đoạn |
|---|---|---|
| **Producer identity** | **roles/cloudtasks.enqueuer** trên queue; **iam.serviceAccounts.actAs** trên DISPATCH_SA khi cấu hình OIDC | Tạo task |
| **Dispatch identity (DISPATCH_SA)** | **roles/run.invoker** trên đúng Cloud Run service | Đại diện cho request Cloud Tasks gửi |
| **Cloud Tasks service agent** | **roles/cloudtasks.serviceAgent** do Google Cloud quản lý | Phát hành token và dispatch |
| **Runtime identity (RUNTIME_SA)** | Quyền trên database/Storage/Google APIs mà worker thực sự cần | Xử lý nghiệp vụ |

Service account dùng tạo OIDC token **phải thuộc cùng project với queue**. Cloud Tasks service agent phát hành token thay mặt DISPATCH_SA. Đừng cấp **roles/cloudtasks.serviceAgent** cho người dùng hoặc runtime account. Lỗi mint token cần kiểm tra service agent và chính sách IAM, không cấp Owner bừa bãi.

### 5.4. Tạo service accounts riêng cho lab

~~~bash
# THAY ĐỔI IAM — chỉ khi chưa có và được owner cho phép.
gcloud iam service-accounts create receipt-dispatcher \
  --project="$PROJECT_ID" \
  --display-name="Cloud Tasks HTTP dispatch identity"

gcloud iam service-accounts create receipt-runtime \
  --project="$PROJECT_ID" \
  --display-name="Cloud Run receipt worker identity"

DISPATCH_SA="receipt-dispatcher@$PROJECT_ID.iam.gserviceaccount.com"
RUNTIME_SA="receipt-runtime@$PROJECT_ID.iam.gserviceaccount.com"

gcloud iam service-accounts describe "$DISPATCH_SA" --project="$PROJECT_ID"
gcloud iam service-accounts describe "$RUNTIME_SA" --project="$PROJECT_ID"
~~~

Deployer cần quyền **Service Account User** trên runtime SA; principal enqueue cần **Service Account User** trên dispatch SA khi gắn OIDC. Cấp trên từng service account, không ban Editor/Owner toàn project để thử.

### 5.5. Đường mạng và bảo vệ endpoint

Với Cloud Run, dùng **URL mặc định run.app** làm HTTP target. Bài dùng private Cloud Run service: request có OIDC token được **Cloud Run IAM** xác minh trước khi vào Java controller.

- Không bật **--allow-unauthenticated** chỉ để chữa lỗi 403.
- Nếu service đặt **ingress internal** hoặc network policy hạn chế, phải xác minh đường Cloud Tasks → Cloud Run thực sự được hỗ trợ.
- IAM không thay authorization nghiệp vụ: handler vẫn phải xác thực order/job ownership theo kiến trúc.
- Tránh một shared account có quyền trên mọi queues, database và Cloud Run services.

## 6. Worker Java/Spring Boot trên Cloud Run

Worker lab chỉ **kiểm tra JSON và ghi log job ID**, sau đó trả **204**. Đây là thực hành về giao nhận HTTP; chưa phải quy trình gửi email hay lưu kết quả nghiệp vụ. Mục 11 mô tả yêu cầu idempotency trước khi dùng trong production.

Tạo thư mục **receipt-worker-lab/** riêng ở môi trường học tập:

~~~text
receipt-worker-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── lab/
        │       └── ReceiptWorkerApplication.java
        └── resources/
            └── application.properties
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>lab.example</groupId>
  <artifactId>receipt-worker</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
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

Phiên bản Spring Boot là mốc cố định cho lab, không phải khuyến nghị dùng mãi trong production. Cần kiểm tra JDK compatibility, updates và lỗ hổng dependencies khi đưa vào hệ thống thật.

### 6.2. ReceiptWorkerApplication.java

~~~java
package lab;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReceiptWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReceiptWorkerApplication.class, args);
    }

    @RestController
    public static class ReceiptHandler {
        private static final Logger LOG =
                LoggerFactory.getLogger(ReceiptHandler.class);
        private final ObjectMapper json;

        public ReceiptHandler(ObjectMapper json) {
            this.json = json;
        }

        public record ReceiptJob(String jobId, String orderId) {}

        @PostMapping(path = "/tasks/receipt",
                     consumes = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Void> process(
                @RequestBody byte[] body,
                @RequestHeader(
                    value = "X-CloudTasks-TaskName", required = false)
                    String taskName,
                @RequestHeader(
                    value = "X-CloudTasks-TaskRetryCount", required = false)
                    String retryCount) {

            if (body.length > 4096) {
                LOG.warn("Permanent reject: payload too large");
                return ResponseEntity.noContent().build();
            }

            ReceiptJob job;
            try {
                job = json.readValue(body, ReceiptJob.class);
            } catch (JsonProcessingException ex) {
                LOG.warn("Permanent reject: invalid JSON");
                return ResponseEntity.noContent().build();
            }

            if (job == null ||
                job.jobId() == null ||
                !job.jobId().matches("[A-Za-z0-9_-]{1,64}") ||
                job.orderId() == null ||
                !job.orderId().matches("[A-Za-z0-9_-]{1,64}")) {
                LOG.warn("Permanent reject: invalid task fields");
                return ResponseEntity.noContent().build();
            }

            // DEMO: không gửi email, không ghi database.
            // Production: chỉ trả 2xx sau khi business outcome được persist.
            LOG.info("receipt job observed jobId={} task={} retries={}",
                     job.jobId(), taskName, retryCount);
            return ResponseEntity.noContent().build();
        }
    }
}
~~~

**Phân biệt các loại phản hồi:**

- **204 No Content:** Cloud Tasks coi attempt thành công và xóa task. Trong lab điều này chỉ có nghĩa dữ liệu đã được nhận/ghi log, **không xác nhận email đã được gửi**.
- **Input sai vĩnh viễn:** ví dụ log cảnh báo rồi ACK để tránh retry vòng lặp. Production cần **lưu trạng thái rejected/quarantine bền vững trước khi ACK** nếu cần audit.
- **Lỗi tạm thời:** khi thay demo bằng I/O thật, ném exception hoặc trả **503** nếu downstream tạm lỗi để Cloud Tasks thử lại.
- **X-CloudTasks-* headers:** hữu ích để điều tra nhưng **không phải bằng chứng xác thực độc lập**; bảo vệ request bằng Cloud Run IAM/OIDC, không tin header do client tự gửi.

### 6.3. application.properties

~~~properties
server.port=${PORT:8080}
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

Cloud Run cấp biến môi trường **PORT**; giá trị cấu hình trên cần là biểu thức Spring Boot đọc biến đó, với mặc định 8080. Build và thử trên máy học tập:

~~~bash
java -version
mvn -version
mvn -B clean package

# Nếu đã build thành công:
PORT=8080 java -jar target/receipt-worker-1.0.0.jar
~~~

Terminal khác:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/tasks/receipt" \
  -H "Content-Type: application/json" \
  --data '{"jobId":"demo-001","orderId":"ord-1001"}'
~~~

Kỳ vọng **204** và log chứa **jobId=demo-001**. Kiểm thử local chưa xác minh đường IAM/OIDC của Cloud Tasks.

## 7. Deploy Cloud Run worker private

Trong thư mục **receipt-worker-lab/**, nếu đã kiểm tra đúng context và đủ quyền:

~~~bash
# THAY ĐỔI: Cloud Build tạo image, Cloud Run triển khai service.
gcloud run deploy "$SERVICE" \
  --source . \
  --project="$PROJECT_ID" \
  --region="$LOCATION" \
  --service-account="$RUNTIME_SA" \
  --no-allow-unauthenticated \
  --timeout=60s \
  --max-instances=3 \
  --concurrency=10

# CHỈ ĐỌC — URL gốc và revision Ready.
SERVICE_URL="$(gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION" \
  --format="value(status.url)")"

printf 'Cloud Run service URL: %s\n' "$SERVICE_URL"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION" \
  --format="yaml(status.url,status.latestReadyRevisionName,spec.template)"
~~~

Sử dụng **SERVICE_URL mặc định run.app** làm OIDC audience. Nếu task URL là **SERVICE_URL/tasks/receipt**, audience vẫn là **SERVICE_URL**, không thêm path. Việc dùng custom domain, route redirect hoặc endpoint proxy yêu cầu kiểm tra lại xác thực token và chính sách mạng.

Cấp Invoker cho dispatch identity, không cấp cho allUsers:

~~~bash
# THAY ĐỔI IAM — chỉ trên service lab.
gcloud run services add-iam-policy-binding "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$LOCATION" \
  --member="serviceAccount:$DISPATCH_SA" \
  --role="roles/run.invoker"

# CHỈ ĐỌC.
gcloud run services get-iam-policy "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION"
~~~

Một service Ready chỉ chứng minh container có thể chạy theo Cloud Run. Nó **chưa chứng minh Cloud Tasks có quyền enqueue, mint OIDC token hoặc dispatch**; các bước đó phải kiểm thử riêng.

## 8. Tạo HTTP queue với rate limit và retry

~~~bash
QUEUE="receipt-http-lab"

# THAY ĐỔI CLOUD TASKS — project lab, không dùng queue production.
gcloud tasks queues create "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --max-dispatches-per-second=2 \
  --max-concurrent-dispatches=3 \
  --max-attempts=5 \
  --min-backoff=10s \
  --max-backoff=300s \
  --max-doublings=3 \
  --max-retry-duration=3600s \
  --log-sampling-ratio=1.0

# CHỈ ĐỌC — queue state/rate/retry.
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --format=yaml
~~~

Nếu queue đã có, không tạo lại: dùng **queues describe** và **queues update** theo change review. Giá trị 2 dispatch/s và 3 đồng thời chỉ để lab dễ quan sát, không phải thông số production. **log-sampling-ratio=1.0** tăng log volume/cost khi có nhiều attempts, nên production thường cần sampling phù hợp.

### 8.1. Rate và concurrency khác nhau

| Cài đặt | Ý nghĩa | Đánh đổi |
|---|---|---|
| **maxDispatchesPerSecond=2** | Tốc độ dispatch steady-state mục tiêu | Bảo vệ API bị giới hạn request/s |
| **maxConcurrentDispatches=3** | Tối đa 3 attempts đang chờ kết thúc | Bảo vệ worker/DB chậm |
| **maxAttempts=5** | Giới hạn số attempts, gồm attempt đầu | Giảm retries vô ích |
| **minBackoff=10s** | Khoảng chờ retry ban đầu/tối thiểu | Cho downstream phục hồi |
| **maxBackoff=300s** | Giới hạn delay tăng dần | Không để retries quá thưa |
| **maxRetryDuration=3600s** | Khoảng retry từ attempt đầu | Không kéo dài vô hạn |
| **logSamplingRatio=1** | Ghi log nhiều operations/attempts | Dễ debug nhưng tốn phí |

Cloud Tasks dùng **token bucket**; active queue có thể dispatch theo **burst** trong khoảng ngắn vượt steady-state limit. Queue mới tạo, vừa resume hoặc idle lâu có thể **ramp-up dần**, không lập tức đạt max rate.

Khi worker trả **429/503** hoặc tỷ lệ 5xx cao, Cloud Tasks có thể giảm dispatch mạnh hơn cấu hình và xét **Retry-After**. Tăng rate khi backend đang quá tải thường làm backlog tệ hơn.

### 8.2. Cấp IAM Enqueuer tại queue

Thay **PRODUCER_EMAIL** bằng người thực hành đã được duyệt hoặc service account thật của Orders API. Không cấp vai trò project-wide nếu chỉ cần enqueue vào queue này.

~~~bash
PRODUCER_EMAIL="REPLACE_WITH_AUTHORIZED_USER_EMAIL"

# THAY ĐỔI IAM trên đúng queue lab.
gcloud tasks queues add-iam-policy-binding "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --member="user:$PRODUCER_EMAIL" \
  --role="roles/cloudtasks.enqueuer"

# CHỈ ĐỌC — xác minh queue IAM.
gcloud tasks queues get-iam-policy "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

Principal tạo task có OIDC cần thêm **iam.serviceAccounts.actAs** trên DISPATCH_SA. Quản trị viên có thể cấp **roles/iam.serviceAccountUser** trên đúng SA:

~~~bash
# THAY ĐỔI IAM — chỉ khi đã được phê duyệt.
gcloud iam service-accounts add-iam-policy-binding "$DISPATCH_SA" \
  --project="$PROJECT_ID" \
  --member="user:$PRODUCER_EMAIL" \
  --role="roles/iam.serviceAccountUser"
~~~

Ở production, **producer thường là một service account** gắn với Cloud Run/GKE app, không phải user đăng nhập tương tác. Khi ấy thay principal user bằng serviceAccount ở queue IAM và actAs binding. Không dùng shared long-lived JSON keys khi có Workload Identity Federation hoặc Google Cloud runtime identity.

## 9. Enqueue và kiểm thử HTTP task bằng gcloud

### 9.1. Tạo task gửi ngay

Bài dùng HTTP method POST, JSON body không chứa dữ liệu thật, OIDC token được cấp cho DISPATCH_SA:

~~~bash
TASK_ID="receipt-demo-001"

# THAY ĐỔI: tạo task, Cloud Tasks sẽ gọi Cloud Run worker.
gcloud tasks create-http-task "$TASK_ID" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --queue="$QUEUE" \
  --url="$SERVICE_URL/tasks/receipt" \
  --method=POST \
  --header="Content-Type:application/json" \
  --body-content='{"jobId":"demo-001","orderId":"ord-1001"}' \
  --oidc-service-account-email="$DISPATCH_SA" \
  --oidc-token-audience="$SERVICE_URL"
~~~

Sau khi tạo thành công, API trả resource name của task. Nếu thử tạo lại **cùng TASK_ID**, Cloud Tasks có thể trả **ALREADY_EXISTS** khi task đang chờ hoặc nằm trong deduplication window. Để thử một task mới có payload mới, đặt **task ID mới và jobId mới**; không sửa task production đang xếp hàng.

### 9.2. Đọc logs và trạng thái

~~~bash
# CHỈ ĐỌC — danh sách tasks chưa hoàn tất.
gcloud tasks list \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --queue="$QUEUE"

# CHỈ ĐỌC — log worker.
gcloud run services logs read "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION" \
  --limit=50

# CHỈ ĐỌC — attempt logs khi logging đã bật.
gcloud logging read \
  'resource.type="cloud_tasks_queue" AND resource.labels.queue_id="receipt-http-lab"' \
  --project="$PROJECT_ID" --limit=30
~~~

**Task biến mất khỏi danh sách chưa phải bằng chứng business outcome thành công.** Nó có thể đã được ACK **2xx**, bị xóa vì hết retry/retention, hoặc do thao tác quản trị. Đối chiếu worker logs, task attempt logs, trạng thái job bền vững và metrics. Trong lab, log **receipt job observed** chứng minh worker đã nhận payload, không phải đã gửi email.

Khi log sampling bật, Cloud Tasks status codes có thể xuất hiện theo **canonical gRPC status** (ví dụ HTTP 429 → RESOURCE_EXHAUSTED, 503 → UNAVAILABLE), không phải trường số HTTP nguyên dạng. Giải nghĩa metrics/log schema theo tài liệu và phiên bản hiện hành.

### 9.3. Lên lịch một task sau 5 phút

Trên **Google Cloud Shell hoặc Linux có GNU date**:

~~~bash
SCHEDULE_TIME="$(date -u -d '+5 minutes' '+%Y-%m-%dT%H:%M:%SZ')"

# THAY ĐỔI: lịch trong tương lai, tối đa 30 ngày.
gcloud tasks create-http-task "receipt-demo-later-001" \
  --project="$PROJECT_ID" --location="$LOCATION" --queue="$QUEUE" \
  --url="$SERVICE_URL/tasks/receipt" \
  --method=POST \
  --header="Content-Type:application/json" \
  --body-content='{"jobId":"demo-later-001","orderId":"ord-1002"}' \
  --oidc-service-account-email="$DISPATCH_SA" \
  --oidc-token-audience="$SERVICE_URL" \
  --schedule-time="$SCHEDULE_TIME"
~~~

Trên Windows PowerShell/macOS, tạo timestamp RFC3339 UTC bằng công cụ tương ứng rồi truyền vào **--schedule-time**. Task đủ điều kiện dispatch vào hoặc sau giờ đã hẹn; Cloud Tasks không bảo đảm thời điểm chạy chính xác tuyệt đối khi queue bị pause, quá tải hoặc đang ramp-up.

### 9.4. Xem và điều chỉnh queue

~~~bash
# CHỈ ĐỌC.
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"

# THAY ĐỔI — giảm rate để bảo vệ worker, phải có review.
gcloud tasks queues update "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --max-dispatches-per-second=1 \
  --max-concurrent-dispatches=2
~~~

**Pause** ngừng dispatch nhưng vẫn có thể tiếp tục enqueue; **resume** đưa queue hoạt động lại, không bảo đảm FIFO. Chỉ dùng với queue lab được sở hữu:

~~~bash
# THAY ĐỔI, chỉ trong lab:
gcloud tasks queues pause "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"

# Sau khi hoàn tất bảo trì:
gcloud tasks queues resume "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

Nếu pause trong nhiều ngày, backlog có thể tích tụ và task có thể chạm retention. Khi resume, tăng rate từ từ, không xả toàn bộ vào backend yếu. **Purge** xóa không thể hoàn tác tất cả tasks trong queue; không dùng nó như thao tác thử nghiệm trên queue chung.

## 10. Producer Java tạo HTTP task bằng Cloud Tasks SDK

Trong ứng dụng Orders API Java, producer có thể gọi **CloudTasksClient** để enqueue task mà không phải chạy gcloud. SDK dùng **Application Default Credentials** từ runtime identity; không nhúng JSON key. Ví dụ dưới đây có thể đặt trong một **project Java riêng**, hoặc bổ sung dependency vào pom.xml Spring Boot đã có.

### 10.1. Maven dependency

Thêm Google Cloud Libraries BOM vào **dependencyManagement**, và thêm **google-cloud-tasks** vào **dependencies** của project. Nếu dự án đã có BOM, chỉ thêm dependency, không khai báo BOM trùng:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>libraries-bom</artifactId>
      <version>26.90.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-tasks</artifactId>
  </dependency>
</dependencies>
~~~

Phiên bản BOM nêu theo ví dụ thư viện Google Cloud Java tại thời điểm viết, không phải phiên bản bắt buộc vĩnh viễn. Production cần phối hợp BOM với dependency management hiện có và kiểm tra binary compatibility. **Không copy nguyên cả block dependencies nếu pom đã chứa block đó**; hãy hợp nhất đúng cấu trúc Maven.

### 10.2. ReceiptEnqueuer.java

~~~java
package lab;

import com.google.cloud.tasks.v2.CloudTasksClient;
import com.google.cloud.tasks.v2.HttpMethod;
import com.google.cloud.tasks.v2.HttpRequest;
import com.google.cloud.tasks.v2.OidcToken;
import com.google.cloud.tasks.v2.QueueName;
import com.google.cloud.tasks.v2.Task;
import com.google.cloud.tasks.v2.TaskName;
import com.google.protobuf.ByteString;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;

public final class ReceiptEnqueuer {
    public static void main(String[] args) throws Exception {
        String project = required("PROJECT_ID");
        String location = required("LOCATION");
        String queueId = required("QUEUE");
        String serviceUrl = required("SERVICE_URL");
        String dispatchSa = required("DISPATCH_SA");

        // Trong production, lấy job ID từ database/business request.
        String jobId = args.length > 0 ? args[0] : "demo-002";
        String orderId = args.length > 1 ? args[1] : "ord-1002";
        if (!jobId.matches("[A-Za-z0-9_-]{1,64}") ||
            !orderId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid job or order ID");
        }

        // Task ID phân bố đều theo SHA-256; jobId là key nghiệp vụ bền vững.
        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(("receipt:" + jobId)
                .getBytes(StandardCharsets.UTF_8));
        String taskId = "receipt-" + HexFormat.of().formatHex(hash);
        String taskName = TaskName.of(
                project, location, queueId, taskId).toString();

        byte[] body = new ObjectMapper()
                .writeValueAsBytes(Map.of(
                    "jobId", jobId,
                    "orderId", orderId
                ));

        String cleanServiceUrl = serviceUrl.replaceAll("/+$", "");
        HttpRequest http = HttpRequest.newBuilder()
                .setUrl(cleanServiceUrl + "/tasks/receipt")
                .setHttpMethod(HttpMethod.POST)
                .putHeaders("Content-Type", "application/json")
                .setBody(ByteString.copyFrom(body))
                .setOidcToken(OidcToken.newBuilder()
                        .setServiceAccountEmail(dispatchSa)
                        .setAudience(cleanServiceUrl)
                        .build())
                .build();

        Task task = Task.newBuilder()
                .setName(taskName)
                .setHttpRequest(http)
                .build();

        try (CloudTasksClient client = CloudTasksClient.create()) {
            String parent = QueueName.of(
                    project, location, queueId).toString();
            Task created = client.createTask(parent, task);
            System.out.println("Task accepted: " + created.getName());
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return value;
    }
}
~~~

Các bước chuẩn bị:

- Biến môi trường **PROJECT_ID, LOCATION, QUEUE, SERVICE_URL, DISPATCH_SA** đã đặt đúng theo tài nguyên lab.
- Producer principal được cấp **roles/cloudtasks.enqueuer** trên queue và **iam.serviceAccounts.actAs** trên DISPATCH_SA.
- Dùng ADC gắn service account khi chạy trên Cloud Run/GKE; máy học tập có thể cấu hình **gcloud auth application-default login** theo chính sách của tổ chức.
- Build project với Maven và chạy class bằng IDE/exec plugin của dự án. **Không thêm quyền Cloud Tasks Administrator** cho producer nếu nó chỉ tạo task.

### 10.3. Tên task và tên job phải tách biệt

Với **jobId=demo-002**, hàm tạo task ID ổn định dạng **receipt-[sha256]**, nên enqueue lại cùng job trong dedup window có thể trả **ALREADY_EXISTS**. Điều này ngăn tạo lặp ngắn hạn ở đầu vào queue, nhưng **không bảo đảm database hoặc email không bị xử lý lại sau 24 giờ**. Nghiệp vụ vẫn cần idempotency key bền vững.

**Lưu ý kiến trúc:** nếu Orders API ghi order vào database rồi enqueue task, có thể xảy ra lỗi giữa hai bước: order đã commit nhưng task chưa tạo. Khi yêu cầu không được mất việc, hãy dùng **transactional outbox** hoặc cơ chế reconciliation để tạo task từ bản ghi trạng thái cần gửi, thay vì giả định hai dịch vụ có chung transaction.

## 11. Idempotency, lỗi vĩnh viễn và mô hình ACK

### 11.1. Vì sao phải có khóa bền vững?

Giả sử worker gọi database thành công ở giây 40, nhưng response 204 không tới Cloud Tasks trước dispatchDeadline. Queue sẽ retry, worker mới có thể lặp lại thao tác.

~~~mermaid
sequenceDiagram
    participant Q as Cloud Tasks
    participant W as Worker A
    participant DB as Durable store
    participant W2 as Worker B
    Q->>W: POST jobId=demo-001
    W->>DB: Commit result for demo-001
    DB-->>W: COMMIT OK
    Note over Q,W: HTTP response bị mất/hết deadline
    Q->>W2: Retry same jobId
    W2->>DB: Atomic create with unique jobId
    DB-->>W2: Already exists
    W2-->>Q: 204 ACK duplicate safely
~~~

Đối với kết quả đơn giản được lưu vào database, mẫu xử lý đúng là **atomic create-if-absent**:

~~~text
BEGIN durable transaction
  IF result(jobId) đã tồn tại và COMPLETED:
    COMMIT -> ACK 2xx
  ELSE:
    validate ownership/payload/business constraints
    INSERT result(jobId, outcome) với UNIQUE(jobId)
    COMMIT -> ACK 2xx
END

Nếu database lỗi tạm thời: không ACK, trả 503 để retry.
Nếu input sai vĩnh viễn: ghi REJECTED vào durable store rồi ACK.
~~~

Ví dụ với Firestore, **document ID = jobId** và **DocumentReference.create(data)** là thao tác create-only. Với Cloud SQL, dùng unique constraint và transaction; với Redis cache TTL đơn thuần chưa chắc đủ cho lifetime nghiệp vụ. Hãy hiểu mức cô lập, race condition và mọi side effects trước khi chọn cách triển khai.

### 11.2. Nếu nghiệp vụ là gửi email hoặc thanh toán?

Tạo một record COMPLETED **trước** khi gửi email có thể dẫn tới mất email nếu process crash sau commit; gửi email **trước** khi tạo record có thể gửi hai lần khi retry. Không giải quyết bài toán này bằng cách chuyển vị trí của một lệnh ghi.

Cách an toàn hơn:

1. Ghi **outbox/job record** cùng transaction với business event ban đầu.
2. Worker claim job bằng **lease/atomic state transition**.
3. Gọi downstream với **idempotency key** do đối tác hỗ trợ; lưu provider message/transaction ID.
4. Ghi completion state bền vững và ACK.
5. Có reconciliation cho trường hợp provider đã nhận request nhưng worker không biết kết quả.
6. Nếu provider không hỗ trợ idempotency, công bố giới hạn **at-least-once** và thiết kế kiểm tra trùng ở bước sau.

**Không hứa exactly-once external side effects** chỉ dựa trên Cloud Tasks, task naming hoặc một cờ retry.

### 11.3. Các trường hợp HTTP và hành động đúng

| Tình huống | Worker response | Hệ quả Cloud Tasks | Điều kiện nghiệp vụ |
|---|---|---|---|
| Commit thành công | **200/204** | ACK và xóa task | Đã lưu outcome thật |
| Job đã xử lý | **204** | ACK | Có idempotency record |
| Input sai vĩnh viễn | **2xx** sau khi ghi rejected/quarantine | Không retry payload vô ích | Có audit/notification |
| DB/network lỗi tạm thời | **503** | Backoff/retry | Không giả ACK |
| Downstream rate limited | **429** + Retry-After nếu phù hợp | Throttling/backoff | Bảo vệ upstream |
| OIDC thiếu/sai | **401/403** từ Cloud Run | Retry có thể lặp | Sửa IAM/audience |
| Request quá lâu | Timeout/DEADLINE_EXCEEDED | Có thể retry | Giới hạn xử lý, idempotency |
| Worker crash sau side effect | Không có response | Có thể retry | Atomic unique key/outbox |

Spring Boot có thể trả 400 cho JSON không giải mã được trước khi handler chạy. Cloud Tasks xem 400 là non-2xx; production cần chọn **cơ chế ghi rejected bền vững** trong error handler hoặc tiền xử lý để tránh retry kéo dài. Không đổ lỗi queue khi việc phân loại permanent/transient nằm ở ứng dụng.

### 11.4. Không có dead-letter queue tích hợp

Cloud Tasks **không tự gửi task lỗi tới Pub/Sub DLQ** sau maxAttempts. Vì thế, với job quan trọng:

- Tạo **job record trước/sau enqueue** với trạng thái PENDING/PROCESSING/COMPLETED/FAILED.
- Gắn jobId vào logs/metrics, quan sát queue backlog và errors.
- Xác định một **retry horizon** ngắn hơn thời gian retention để có thể cảnh báo.
- Khi hết retry, dùng reconciler tìm các job chưa completed, ghi trạng thái FAILED, lưu lỗi và quyết định **re-enqueue với task ID mới** theo policy.
- Đừng enqueue vô hạn một payload vĩnh viễn sai; cần manual review/quarantine hoặc kế hoạch sửa dữ liệu.

Đối với pipeline nhiều subscribers hoặc yêu cầu DLQ tích hợp theo message subscriptions, cân nhắc Pub/Sub. Với chuỗi nhiều bước có trạng thái và nhánh điều kiện, cân nhắc Workflows kết hợp Cloud Tasks khi thích hợp.

## 12. Quan sát, backlog và troubleshooting

### 12.1. Những tín hiệu vận hành quan trọng

| Tín hiệu | Nguồn | Khi nào cảnh báo? |
|---|---|---|
| **Queue depth / tasks pending** | Cloud Tasks metrics/console | Backlog tăng liên tục |
| **Oldest task age / schedule delay** | Cloud Tasks + job timestamps | Độ trễ vượt SLA |
| **Task attempts theo response code** | Cloud Monitoring/Cloud Tasks logs | 429, 503, 401/403 hoặc timeout tăng |
| **Dispatch rate/concurrency** | Queue settings + metrics | Worker bị quá tải hoặc throughput thấp |
| **Cloud Run 5xx, p95 latency, instance count** | Cloud Run Monitoring/Logging | Không đạt SLO xử lý |
| **Business job status** | Database/application telemetry | Job chưa COMPLETED dù queue đã hết |
| **Job duplicate/rejected counts** | Structured application logs | Dữ liệu trùng hoặc permanent errors tăng |
| **Cloud Billing per SKU** | Cloud Billing | Retry storms và tăng phí bất thường |

Trong Cloud Monitoring, metric **cloudtasks.googleapis.com/queue/task_attempt_count** hỗ trợ phân tích attempts và nhãn **response_code**; tên các trạng thái có thể theo **canonical gRPC code**. Ví dụ HTTP 429 thường ánh xạ RESOURCE_EXHAUSTED; HTTP 503 ánh xạ UNAVAILABLE.

Cloud Tasks logs không nhất thiết bật đầy đủ trên queue: mặc định log sampling có thể bằng 0. Với project production, cần bật tỷ lệ phù hợp để cân bằng điều tra lỗi và chi phí log.

### 12.2. Bộ lệnh chỉ đọc

~~~bash
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --format=yaml

gcloud tasks list \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --queue="$QUEUE"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION" \
  --format="yaml(status.url,status.latestReadyRevisionName,status.traffic)"

gcloud run services logs read "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION" --limit=100

gcloud logging read \
  'resource.type="cloud_tasks_queue" AND resource.labels.queue_id="receipt-http-lab" AND jsonPayload.attemptResponseLog.status!="OK"' \
  --project="$PROJECT_ID" --limit=50
~~~

Không đưa raw task payload, ID tokens, API keys hoặc thông tin đơn hàng vào báo cáo/ticket. Mỗi task nên có **jobId**, correlation ID, queue ID, task ID, attempt count và outcome state, nhưng cần hạn chế PII.

### 12.3. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/khắc phục |
|---|---|---|
| **CreateTask 403** | Producer thiếu Enqueuer hoặc quyền actAs DISPATCH_SA | Queue IAM, service account IAM |
| **Dispatch 401/403** | OIDC audience sai, Invoker thiếu, service agent không mint được token | Cloud Run IAM, audience, Cloud Tasks service agent |
| **Task được tạo nhưng không chạy** | scheduleTime tương lai, queue PAUSED, ramp-up hoặc task chưa đủ điều kiện | describe queue/task, scheduleTime |
| **HTTP 404** | Sai path **/tasks/receipt**, deploy nhầm service/region | URL, Cloud Run revision, handler mapping |
| **HTTP 400 lặp** | Payload/syntax sai, worker trả non-2xx | Validate, ghi rejected và ACK nếu permanent |
| **HTTP 429/503 tăng** | Backend/DB quá tải, quota hoặc downstream limit | Giảm dispatch/concurrency, tăng capacity đúng cách |
| **DEADLINE_EXCEEDED** | Handler chậm hơn dispatchDeadline/Cloud Run timeout | Đo p95 task duration, giảm công việc trong request |
| **Queue có backlog dù CPU thấp** | Slow downstream, per-request latency, cold ramp-up, scheduler constraints | Task attempts, Cloud Run concurrency, network |
| **Duplicate business side effects** | Retry sau timeout hoặc task mới cùng job | Persistent idempotency, external API idempotency keys |
| **Task biến mất nhưng order chưa hoàn tất** | Worker ACK quá sớm hoặc hết retry/retention | Job state + logs, reconciler |
| **Lỗi sau resume queue** | Nhiều backlog tasks gây thắt cổ chai | Tăng rate chậm, giám sát 429/503 |
| **Queue delete rồi tạo lại tên cũ lỗi** | Queue re-creation waiting period | Chọn tên mới hoặc tránh delete/recreate |
| **Cloud Run chưa Ready** | Java build/startup, PORT, memory, IAM | Build logs, revision conditions, container logs |

### 12.4. Quy trình điều tra 403 theo đúng lớp

~~~mermaid
flowchart TD
    ERR["403 khi tạo/giao task"] --> WHEN{"Lỗi ở giai đoạn nào?"}
    WHEN -- "CreateTask" --> ENQ["Kiểm tra Enqueuer + iam.serviceAccounts.actAs"]
    WHEN -- "Dispatch" --> OIDC["Kiểm tra DISPATCH_SA + OIDC audience"]
    OIDC --> INV["Cloud Run Invoker trên đúng service"]
    INV --> AGENT["Cloud Tasks service agent được quản lý đúng"]
    AGENT --> NET["Kiểm tra ingress/routing nếu IAM đúng"]
    ENQ --> RECHECK["Thử lại bằng principal/queue của lab"]
    NET --> RECHECK
~~~

Không sửa bằng cách cấp **roles/owner** cho tất cả service accounts. Nếu queue gọi **Google APIs ở *.googleapis.com**, dùng **OAuth access token** khi API đòi token kiểu đó; với **Cloud Run service**, mặc định ưu tiên **OIDC ID token** và audience đúng.

## 13. Thiết kế capacity, độ tin cậy và chi phí

### 13.1. Tính throughput có headroom

Giả sử một đối tác chịu tối đa **20 requests/giây** và mỗi request trung bình mất **0,5 giây**. Một mức concurrency tối thiểu theo Little's Law ở steady-state là:

\[
L \approx \lambda \times W
= 20\ \mathrm{requests/s} \times 0.5\ \mathrm{s}
= 10\ \mathrm{in\ flight}
\]

Tuy nhiên không nên đặt queue ngay bằng mức giới hạn 20/10 mà không tính spike và SLO. Một cấu hình thử nghiệm có thể là **15 dispatch/s, 8 concurrent attempts**, sau load test điều chỉnh theo p95/timeout, rate limits của đối tác, số Cloud Run instances và DB connections.

**Đừng nhầm các tầng concurrency:** queue maxConcurrentDispatches giới hạn toàn queue; Cloud Run **--concurrency** giới hạn requests đồng thời trên **mỗi instance**; max-instances giới hạn phạm vi scale worker nhưng không phải công cụ chặn mọi chi phí. Có thể còn giới hạn của Cloud SQL connection pool, đối tác hoặc NAT.

### 13.2. Dự báo thời gian rút backlog

Nếu queue có **6.000 tasks**, producer ngừng tạo mới và worker duy trì **10 successful tasks/s**, thời gian lý thuyết tối thiểu là:

\[
T = 6000/10 = 600\ \mathrm{s} = 10\ \mathrm{phút}
\]

Nhưng thực tế có retries, rate ramp-up, burst, request latency và khả năng downstream từ chối; muốn đo chính xác phải xem **successful tasks/s**, không dùng queue maxDispatchesPerSecond làm tốc độ hoàn tất bảo đảm.

### 13.3. Phí và rủi ro tài nguyên

| Nhóm phí | Khi nào phát sinh? | Cách kiểm soát |
|---|---|---|
| **Cloud Tasks** | Operations/task requests theo bảng giá/quota | Tránh task quá nhỏ, retry storms |
| **Cloud Run** | Request/compute/instance theo cấu hình | Rightsize CPU/RAM/concurrency, min/max instances |
| **Cloud Build + Artifact Registry** | Build từ source, lưu image | Quản lý builds/artifact retention |
| **Cloud Logging/Monitoring** | Log ingestion, metrics/retention | Sampling phù hợp, tránh log PII |
| **Database/third-party APIs** | Ghi trạng thái, email/webhook/quota | Batch hợp lý, idempotency, rate control |
| **Network egress** | Gọi endpoint ngoài region/Internet | Region/topology, đo egress SKU |

Task retry thất bại nhiều lần có thể làm **số HTTP attempts lớn hơn nhiều so với số jobs thành công**. Khi cần đánh giá hiệu quả, tính **cost per successfully completed job**, không chỉ cost per enqueue.

### 13.4. Runbook thay đổi queue có kiểm soát

1. Ghi baseline: queue depth, oldest job age, dispatch rate, 429/503, Cloud Run p95 và DB metrics.
2. Chọn **một** thay đổi: maxDispatchesPerSecond hoặc maxConcurrentDispatches hoặc worker capacity.
3. Review target throughput, quota, IAM và rủi ro với đối tác.
4. Thử nghiệm ở lab/staging, theo dõi backlog và request failures.
5. Áp dần ở production nếu được phép; tránh pause/resume liên tục làm thay đổi ramp-up.
6. Nếu 429/503 tăng, giảm rate hoặc xử lý bottleneck downstream; không tăng rate mù quáng.
7. Lưu cấu hình trong IaC/GitOps hoặc change record; tránh trộn quản lý bằng **queue.yaml** và **Cloud Tasks API** cho cùng queue.
8. Xác minh cải thiện bằng throughput thành công, độ trễ và Cloud Billing sau kỳ ghi nhận.

## 14. Case study: webhook xác nhận đơn hàng

**Bối cảnh giả định:** một Orders API viết bằng Java nhận 300 đơn hàng/phút vào giờ cao điểm. Đối tác vận chuyển chỉ nhận **2 webhook requests/giây**, có lúc trả HTTP 429. Yêu cầu nghiệp vụ: không gửi hai lần cùng trạng thái đơn, có thể retry khi đối tác lỗi, và cung cấp trạng thái để CSKH tra cứu.

### 14.1. Thiết kế

~~~mermaid
flowchart LR
    USER["Order API"] --> DB["Orders DB + outbox"]
    DB --> P["Outbox publisher\nCloud Tasks Enqueuer"]
    P --> Q["HTTP queue\n2 dispatch/s, 3 concurrent"]
    Q --> W["Cloud Run webhook worker"]
    W --> EXT["Carrier HTTPS API"]
    W --> STATE["Delivery job state\nidempotency + audit"]
    MON["Monitoring + alert"] -. "Backlog, 429, 503" .-> Q
~~~

**Quyết định:**

- Orders transaction ghi **outbox record**; dispatcher tạo task với **jobId** bền vững.
- Target Cloud Run private dùng OIDC dispatch identity; runtime account chỉ có quyền cần cho outbox/secret/downstream.
- Worker dùng jobId để chống gửi trùng và gửi **external idempotency key** nếu carrier API hỗ trợ.
- 429/503 được retry với backoff, kiểm tra Retry-After; lỗi permanent được lưu trạng thái/đưa vào manual review và ACK đúng chính sách.
- Dashboard quan sát jobs chưa hoàn tất theo tuổi, không chỉ queue count.

### 14.2. Sự cố

Đối tác trả 429 liên tục, queue bắt đầu tăng từ 100 lên 5.000 tasks. Nhóm phát triển nghĩ “nâng rate lên 10/s sẽ xóa backlog nhanh hơn”.

**Phân tích:** đây là điều ngược mong muốn. Carrier đã yêu cầu giảm tải; Cloud Tasks còn có thể tự congestion backoff. Cần xác minh nguyên nhân 429 (quota, token, per-customer limit), giữ tốc độ <= giới hạn thực, phân chia queue nếu có những đối tác với capacity khác nhau, và điều chỉnh SLO/wait-time trước khi nhận thêm công việc.

### 14.3. Tiêu chí nghiệm thu

- Producer ghi task/job state mà không mất việc khi crash giữa các bước.
- Không có double charge/double send khi retry một jobId.
- HTTP 429/503 được xử lý với backoff và có cảnh báo.
- Oldest job age không vượt ngưỡng đã thỏa thuận.
- Cloud Run private, OIDC đúng identity/audience.
- Có kế hoạch dừng/replay công việc theo owner, retention và support process.
- Chi phí Cloud Tasks + Cloud Run + network được đo theo job thành công.

## 15. Bài tập và đáp án định hướng

### 15.1. Bài tập A — Phân biệt Cloud Tasks và Pub/Sub

Chọn công cụ cho từng nhu cầu:

| Yêu cầu | Đáp án định hướng |
|---|---|
| Gọi webhook cụ thể sau 5 phút, 3 req/s | **Cloud Tasks** |
| Phát sự kiện payment.created cho 5 microservices | **Pub/Sub** |
| Trigger khi GCS object finalized | **Eventarc** |
| Điều phối xác minh KYC → chờ callback → cập nhật hồ sơ | **Workflows** |
| Chạy batch video 4 giờ | **Cloud Run Jobs/Batch** |
| Đảm bảo một API không bị gọi quá đồng thời | **Cloud Tasks maxConcurrentDispatches** |

Giải thích vì sao yêu cầu về **đích gọi cụ thể**, lịch và rate phù hợp Cloud Tasks hơn Pub/Sub, còn fan-out/ordering keys và DLQ tích hợp là thế mạnh của Pub/Sub theo subscription model.

### 15.2. Bài tập B — Đọc cấu hình queue

~~~yaml
rateLimits:
  maxDispatchesPerSecond: 5
  maxConcurrentDispatches: 10
retryConfig:
  maxAttempts: 7
  minBackoff: 5s
  maxBackoff: 120s
  maxDoublings: 3
  maxRetryDuration: 1800s
~~~

**Câu hỏi:**

1. Có thể có 10 HTTP attempts đang chờ kết quả cùng lúc không?
2. Có bảo đảm thực hiện đúng 5 requests trong **mọi** cửa sổ 1 giây không?
3. Một task trả 503 sau attempt đầu, Cloud Tasks làm gì?
4. Nếu hết maxAttempts nhưng maxRetryDuration chưa tới, có nhất thiết bị xóa ngay không?
5. Queue có đảm bảo xử lý theo đúng thứ tự thêm không?

**Đáp án:** (1) Có, nếu còn tasks và capacity. (2) Không, token bucket có burst/ramp-up. (3) Backoff/retry theo policy, có thể congestion throttling. (4) Không, phải xét logic cả hai giới hạn và retention. (5) Không, best-effort order.

### 15.3. Bài tập C — Idempotency

Giả sử cùng **jobId=receipt-123** được Cloud Tasks gửi ba lần vì hai attempts trước timeout:

- Worker gửi email ba lần rồi mới ghi COMPLETED vào database. Kết quả có an toàn không?
- Nếu producer chỉ dùng task name có hash, khi tạo lại job sau 25 giờ thì sao?
- Nếu xử lý nghiệp vụ chỉ là **create-one-document** theo jobId trong Firestore, nên dùng operation nào?
- Nếu downstream email provider không hỗ trợ idempotency key, cần bổ sung gì?

**Đáp án:** gửi ba email không an toàn; task name deduplication không bảo đảm sau thời gian giữ tên; dùng **atomic create-if-absent** cho tài liệu kết quả; email cần outbox/reconciliation, audit và cơ chế phát hiện gửi trùng, không tuyên bố exactly-once.

### 15.4. Bài tập D — Tính công suất

Queue được cấu hình **10 dispatch/s** và **maxConcurrentDispatches=4**. Worker mất trung bình **1 giây/attempt** để đáp ứng. Hỏi throughput thành công tối đa gần đúng nếu không có lỗi, mỗi request xử lý độc lập và không có bottleneck khác?

\[
\min(10,\ 4 / 1\ \mathrm{s}) = 4\ \mathrm{tasks/s}
\]

**Bài mở rộng:** nếu thời gian xử lý tăng lên **2 giây**, throughput giảm gần **2 tasks/s**. Vì vậy tăng maxDispatchesPerSecond không giải quyết được giới hạn maxConcurrentDispatches hoặc worker latency.

### 15.5. Bài tập E — Kiểm thử có điều kiện

Trong project lab đã được cấp quyền:

1. Deploy worker private và xác minh không có allUsers Invoker.
2. Enqueue task hợp lệ, quan sát response 204 và log jobId.
3. Enqueue một task khác có lịch sau 5 phút, đọc scheduleTime.
4. Cố tạo lại cùng task ID và ghi kết quả **ALREADY_EXISTS** nếu gặp.
5. Thử tạo task với DISPATCH_SA chưa được cấp Invoker trong một lab tách biệt; xác định lỗi dispatch 401/403, khôi phục quyền đúng.
6. Thử endpoint giả lập trả 503 trong môi trường kiểm soát; quan sát retries/backoff và Cloud Tasks logs.
7. Pause rồi resume queue, ghi ảnh hưởng tới queued tasks và tốc độ ramp-up.
8. Ghi lại metrics, chi phí phát sinh và dọn tài nguyên mình sở hữu.

Chỉ thay IAM hoặc tạo 503 test **trong lab**; không cố tình gây lỗi trên queue/webhook production.

### 15.6. Mẫu báo cáo nghiệm thu

~~~text
PROJECT_ID / LOCATION / OWNER:
QUEUE_NAME / STATE / RATE_LIMIT / CONCURRENCY:
RETRY_CONFIG / DISPATCH_DEADLINE:
CLOUD_RUN_SERVICE / URL / REVISION:
PRODUCER_PRINCIPAL / DISPATCH_SA / RUNTIME_SA:
ENQUEUER / ACT_AS / INVOKER / SERVICE_AGENT:
TASK_ID / JOB_ID / SCHEDULE_TIME:
HTTP_STATUS / WORKER_LOG / RETRY_COUNT:
BUSINESS_OUTCOME_PERSISTED?:
DUPLICATE_REPLAY_RESULT:
QUEUE_BACKLOG / OLDEST_TASK_AGE:
429 / 503 / DEADLINE_EXCEEDED:
COST_AND_LOG_SAMPLING:
CLEANUP_RESULT / OPEN_ISSUES:
~~~

Điền **PASS** chỉ khi đã kiểm chứng thực tế. Nếu bài lab chỉ log giả lập, mục **BUSINESS_OUTCOME_PERSISTED** phải là **NO/NOT APPLICABLE**, không đánh dấu COMPLETED cho biên nhận thật.

## 16. Dọn tài nguyên lab an toàn

### 16.1. Kiểm kê trước khi xóa

~~~bash
# CHỈ ĐỌC — xác minh project và queue.
gcloud config list project

gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"

gcloud tasks list \
  --project="$PROJECT_ID" --location="$LOCATION" --queue="$QUEUE"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION"
~~~

**Không xóa queue đang có jobs nghiệp vụ chưa xử lý.** Task đã bị ACK thành công thường không còn hiện trong queue; với jobs cần audit, kết quả phải được lưu tại durable store theo mục 11.

### 16.2. Dừng dispatch trước khi xem xét xóa

~~~bash
# THAY ĐỔI — chỉ khi queue lab được sở hữu hoàn toàn.
gcloud tasks queues pause "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"

# CHỈ ĐỌC — kiểm tra state và pending tasks.
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

Sau khi xác nhận không còn công việc cần giữ hoặc đã lưu/reconcile jobs, quản trị viên có thể xóa **đúng queue lab**:

~~~bash
# XÓA TÀI NGUYÊN — irreversible, chỉ sau owner approval.
gcloud tasks queues delete "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

**Hậu quả:** toàn bộ tasks còn trong queue bị mất; việc tạo lại queue cùng tên có thể bị chặn trong **3 ngày**. Nếu mục tiêu chỉ là tạm ngừng, dùng **pause**; nếu điều chỉnh rate, dùng **update**. **Purge** cũng không thể hoàn tác và không phải bước cleanup mặc định.

### 16.3. Xóa Cloud Run worker và thu hồi IAM

~~~bash
# XÓA TÀI NGUYÊN — chỉ khi service thật sự do lab tạo ra.
gcloud run services delete "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION"
~~~

Cuối cùng, xem lại các IAM bindings được thêm trên queue/service và hai service accounts **receipt-dispatcher**, **receipt-runtime**; chỉ thu hồi/xóa chúng khi không còn workload nào dùng. **Không xóa Cloud Tasks service agent**, Cloud Build service account hoặc shared Artifact Registry repository. Xóa Cloud Run service không tự dọn Cloud Build logs, Artifact Registry images và các tài nguyên ngoài service; kiểm tra Cloud Billing sau độ trễ ghi nhận.

## 17. Tài liệu chính thức và checklist

- [Cloud Tasks overview](https://docs.cloud.google.com/tasks/docs/dual-overview)
- [Choose Cloud Tasks or Pub/Sub](https://docs.cloud.google.com/tasks/docs/comp-pub-sub)
- [Quickstart: Add a task to an HTTP queue](https://docs.cloud.google.com/tasks/docs/add-task-queue)
- [Create Cloud Tasks queues](https://docs.cloud.google.com/tasks/docs/creating-queues)
- [Create HTTP target tasks programmatically](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks)
- [Use Cloud Tasks with authenticated HTTP targets](https://docs.cloud.google.com/tasks/docs/authentication)
- [Configure queue rate limits and retries](https://docs.cloud.google.com/tasks/docs/configuring-queues)
- [Set retry parameters for a task](https://docs.cloud.google.com/tasks/docs/configure-retry-task)
- [Manage queues and tasks](https://docs.cloud.google.com/tasks/docs/manage-queues-and-tasks)
- [Cloud Tasks quotas and limits](https://docs.cloud.google.com/tasks/docs/quotas)
- [Common pitfalls](https://docs.cloud.google.com/tasks/docs/common-pitfalls)
- [Manage Cloud Tasks scaling risks](https://docs.cloud.google.com/tasks/docs/manage-cloud-task-scaling)
- [Cloud Tasks IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/cloudtasks)
- [Java Cloud Tasks client library](https://docs.cloud.google.com/java/docs/reference/google-cloud-tasks/latest/overview)
- [gcloud tasks create-http-task reference](https://docs.cloud.google.com/sdk/gcloud/reference/tasks/create-http-task)
- [Cloud Run deploy from source](https://docs.cloud.google.com/run/docs/deploying-source-code)
- [Cloud Tasks pricing](https://cloud.google.com/tasks/pricing)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)

**Checklist áp dụng:** đúng project/region → phân tách Producer/Dispatch/Runtime identities → private Cloud Run OIDC audience đúng → queue rate/concurrency/retry phù hợp → task có stable jobId → handler chỉ ACK sau durable outcome → có idempotency/outbox/reconciliation → theo dõi 429/503/backlog/oldest age → Billing và logging phù hợp → quản trị pause/resume/delete đúng ownership.

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** Cloud Tasks bổ sung khả năng **điều tiết và trì hoãn HTTP work** giữa các ứng dụng chạy trên **Cloud Run, GKE hoặc Compute Engine**. Kết hợp **IAM/OIDC, Cloud Logging/Monitoring, Cloud Billing, Firestore/Cloud SQL, Pub/Sub và Workflows** theo mục đích: **Cloud Tasks quản lý dispatch**, còn ứng dụng chịu trách nhiệm **đúng nghiệp vụ, dữ liệu bền vững và phục hồi sau retry**.











