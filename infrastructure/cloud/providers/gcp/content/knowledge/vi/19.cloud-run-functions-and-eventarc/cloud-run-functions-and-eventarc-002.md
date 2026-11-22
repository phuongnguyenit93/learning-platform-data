# Lựa chọn functions, Cloud Run service hoặc Cloud Run job

Một hệ thống bán hàng trên Google Cloud có ba việc: tiếp nhận HTTP request tạo đơn hàng, tạo thumbnail khi ảnh mới xuất hiện trong Cloud Storage và chạy báo cáo doanh thu hằng đêm. Cả ba đều có thể thực hiện bằng container, nhưng **không nên ép chúng vào một kiểu thực thi**. HTTP API cần endpoint và trả response; xử lý sự kiện cần trigger và chống xử lý trùng; báo cáo theo lô cần chạy đến khi xong và trả kết quả thành công/thất bại.

Trong chương **Cloud Run functions và Eventarc** thuộc học phần **CLOUD_PROVIDERS_GCP**, bài này giúp chọn giữa **Cloud Run functions**, **Cloud Run service** và **Cloud Run job**, xét từ kiến trúc ứng dụng Java, IAM, Pub/Sub/Eventarc, Cloud Storage, CI/CD đến độ tin cậy và chi phí. Nội dung tập trung vào **quyết định chọn tài nguyên**, không lặp lại toàn bộ runtime contract của Cloud Run.

Sau bài học, bạn có thể:

- Hiểu vì sao **function được triển khai thành một Cloud Run service**, nhưng cách viết và phát hành khác service container tùy chỉnh.
- Chọn đúng tài nguyên dựa trên **request–response**, **event-driven** hay **run-to-completion**.
- Viết và deploy một Java HTTP function bằng Functions Framework; dùng Eventarc cho sự kiện.
- Tạo Cloud Run service từ image và Cloud Run job xử lý dữ liệu theo task index.
- Thiết kế trigger, quyền IAM, retry/idempotency và lưu trạng thái bền vững.
- So sánh cold start, concurrency, timeout, chi phí và các lỗi phổ biến.

> **Phạm vi thực hành:** tên project, image, bucket và service account đều là ví dụ; chỉ tạo tài nguyên trong project lab được phép. Cloud Build, Artifact Registry, Cloud Run, Eventarc, Pub/Sub và lưu trữ có thể phát sinh chi phí.

## 1. Function, service và job có quan hệ thế nào?

**Cloud Run service** là tài nguyên phục vụ **HTTP requests**, có HTTPS URL, revisions, traffic splitting, autoscaling và cấu hình runtime. Bạn có thể deploy service bằng **container image** tự xây hoặc từ **source code**.

**Cloud Run function** là cách viết **single-purpose handler** (HTTP hoặc CloudEvent), sau đó Google Cloud dùng Functions Framework và buildpacks/Cloud Build tạo image rồi **triển khai thành Cloud Run service**. Với mô hình hiện hành, function **không phải một loại máy chủ tách biệt** với Cloud Run service. Nó là **cách phát triển/triển khai** thuận tiện cho một đoạn xử lý nhỏ.

**Cloud Run job** là tài nguyên khác: mỗi lần **execution** khởi chạy một hoặc nhiều tasks; container làm việc rồi **thoát với exit code**. Job không cần HTTP listener hoặc URL để nhận request từ khách hàng.

~~~mermaid
flowchart TD
  A["Có công việc cần chạy?"] --> B{"Có request HTTP cần phản hồi?"}
  B -- Có --> C{"Chủ yếu là một handler nhỏ?"}
  C -- Có --> D["Cloud Run function<br/>tạo Cloud Run service từ mã nguồn"]
  C -- Không --> E["Cloud Run service<br/>framework/image tùy chỉnh"]
  B -- Không --> F{"Có sự kiện Cloud Storage/Pub/Sub?"}
  F -- Có --> G{"Xử lý ngắn theo từng event?"}
  G -- Có --> H["Function hoặc service + Eventarc"]
  G -- Không --> I["Queue/Workflows → job hoặc worker phù hợp"]
  F -- Không --> J{"Chạy đến khi hoàn tất?"}
  J -- Có --> K["Cloud Run job"]
  J -- Không --> L["Xem Cloud Run worker pool"]
~~~

Đây là **cây quyết định**, không phải ranh giới tuyệt đối. Một service có thể nhận Eventarc CloudEvents; function cũng có HTTPS endpoint; job có thể được bắt đầu bởi một HTTP API thông qua **Cloud Run Jobs API**, nhưng bản thân job không là HTTP handler.

### Ma trận so sánh

| Tiêu chí | **Function trên Cloud Run** | **Cloud Run service tùy chỉnh** | **Cloud Run job** |
|---|---|---|---|
| Mục tiêu | Một HTTP/CloudEvent handler | API, web app, gRPC hoặc event receiver phức tạp | Batch, import/export, ETL, migration |
| Đầu vào | HTTP request / CloudEvent do trigger đưa tới | HTTP request / CloudEvent qua HTTP | Execution theo lệnh, API, lịch hoặc workflow |
| Cách deploy điển hình | `--source . --function ENTRYPOINT` | Image hoặc source, có thể dùng Dockerfile | Image hoặc source/entrypoint chạy kết thúc |
| Container HTTP listener | Functions Framework quản lý | Ứng dụng tự quản và lắng nghe `PORT` | **Không cần** |
| Kết quả | HTTP response/CloudEvent handler trả kết quả | HTTP response/status | `exit 0` thành công, khác 0 thất bại |
| Mở rộng | Hạ tầng Cloud Run service autoscaling | Service autoscaling, concurrency | Task count, parallelism, retries |
| Phiên bản phát hành | Cloud Run revisions | Cloud Run revisions, traffic splitting | Job definition và các executions |
| Phù hợp với thao tác dài | Bị ràng buộc request/event delivery timeout | Bị ràng buộc request timeout | Task timeout dài hơn, checkpoint/retry |
| Tính phí | Theo Cloud Run service và tài nguyên liên quan | Theo Cloud Run service và tài nguyên liên quan | Theo tài nguyên trong lúc task chạy |

**Thường bị nhầm:** tài liệu và dự án cũ có tên **Cloud Functions (2nd gen)** hoặc dùng `gcloud functions deploy`. Cơ chế mới được gọi **Cloud Run functions**, ưu tiên deploy bằng **Cloud Run Admin API** và `gcloud run deploy --function`. Các functions tạo bằng Cloud Functions v2 API có thể được quản lý qua Cloud Run, nhưng không phải mọi thao tác Cloud Run mới đều tương thích ngược với API cũ; **1st gen** là thế hệ khác với giới hạn và pricing riêng.

## 2. Ba câu hỏi quyết định quan trọng nhất

### 2.1. Ai khởi tạo và phản hồi với ai?

- **Khách hàng chờ HTTP response:** dùng service hoặc HTTP function.
- **Object/event thay đổi và cần callback:** dùng **Eventarc → Cloud Run service/function**; consumer nhận một HTTP **CloudEvent**.
- **Hệ thống muốn hoàn tất một batch có kết quả:** chạy job qua CLI, scheduler, workflow hoặc API.

Không nhầm **nguồn kích hoạt** với **mô hình chạy**: Eventarc chuyển một event thành HTTP request tới destination service/function; không biến job thành server.

### 2.2. Ứng dụng có cần kiểm soát cấu trúc web server không?

Chọn **function** khi logic ngắn, ít endpoint, được hỗ trợ bởi runtime và Functions Framework; không cần tự quản main server, Dockerfile hoặc middleware phức tạp.

Chọn **service tùy chỉnh** khi có nhiều endpoints, REST/gRPC framework, routing/middleware, dependency native đặc thù, build container riêng, startup và probes do ứng dụng quyết định. **Service cũng có thể deploy từ source bằng buildpacks**; không bắt buộc tự viết Dockerfile.

### 2.3. Công việc kết thúc hay chạy liên tục?

Job phù hợp workload có điểm kết thúc rõ: xử lý N file, tạo báo cáo, cập nhật dữ liệu, xuất kết quả rồi exit. Một consumer kéo Pub/Sub **liên tục** nên đánh giá **Cloud Run worker pool** hoặc service nhận Pub/Sub push; không tạo job chạy vô hạn chỉ để giữ một tiến trình sống.

## 3. Functions: vòng đời từ source tới Cloud Run service

~~~text
Source Java + pom.xml + function entrypoint
        ↓ Cloud Run functions deployment
Cloud Storage (lưu source)
        ↓
Cloud Build + buildpacks + Functions Framework
        ↓
Artifact Registry (container image)
        ↓
Cloud Run service / revision / HTTPS URL
        ↑
HTTP caller hoặc Eventarc trigger (CloudEvent)
~~~

**Điểm mạnh:** phát hành nhanh những handler đơn mục đích, không cần viết HTTP server hay Dockerfile. **Giới hạn thực tế:** phải dùng runtime và Functions Framework được hỗ trợ, cấu hình hàm entrypoint hợp lệ, và vẫn phải quản IAM, logs, retry, database, concurrency.

Functions có thể là:

- **HTTP function:** implement một handler trả HTTP response, phù hợp webhook hoặc endpoint xử lý đơn giản.
- **CloudEvent function:** nhận object/event metadata có chuẩn CloudEvents khi Eventarc kích hoạt; phù hợp sự kiện Cloud Storage, Pub/Sub hoặc nguồn khác được hỗ trợ.

**CloudEvent khác payload Pub/Sub raw:** Eventarc dùng các trường envelope như `id`, `source`, `type`, `subject` cùng `data`; handler cần diễn giải đúng event type/nguồn. Không giả định một sự kiện Cloud Storage chứa toàn bộ bytes của ảnh; thường chỉ có metadata và cần đọc object bằng Storage API nếu cần.

## 4. Ví dụ A: Java HTTP function và deploy từ source

Mẫu nhỏ sau minh họa Java Functions Framework. Người học tạo thư mục lab độc lập:

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

**`pom.xml`** (Maven, tối giản):

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

Functions Framework gọi phương thức `service` của lớp có tên đầy đủ `example.HelloFunction`. Vì vậy không có `public static void main`, không cần đọc `PORT` và không cần tự mở socket; runtime quản phần HTTP listener cho function.

Chạy local bằng Maven/Functions Framework trong thư mục chứa `pom.xml`:

~~~bash
mvn function:run -Drun.functionTarget=example.HelloFunction

# Terminal khác:
curl -i http://localhost:8080/
~~~

Trước khi triển khai, chạy Maven với JDK 21 và kiểm tra handler trả về đúng nội dung. Nếu chạy từ máy/IDE dùng Java version khác với `maven.compiler.release`, build có thể lỗi; chọn cùng runtime như môi trường Cloud Run.

### Deploy HTTP function riêng tư

~~~bash
PROJECT_ID="my-functions-lab"
REGION="asia-southeast1"
FUNCTION_NAME="hello-java"
RUNTIME_SA="app-runtime@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com logging.googleapis.com

# Chạy trong thư mục hello-function/ có pom.xml và src/.
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

Trước khi deploy, runtime service account phải tồn tại; người deploy phải có quyền Cloud Run source deployment, quyền sử dụng service account, các quyền Cloud Build/Artifact Registry cần thiết theo mô hình build. **Không sửa `--allow-unauthenticated` để vượt lỗi IAM production**.

Để test endpoint private, sử dụng identity đã có `roles/run.invoker`:

~~~bash
URL="$(gcloud run services describe "$FUNCTION_NAME" \
  --region "$REGION" --format="value(status.url)")"

curl -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$URL"
~~~

Nếu không có quyền Invoker, server sẽ từ chối dù code Java đúng. Đọc Cloud Run revision logs khi lỗi build hoặc startup; test local với Functions Framework CLI/Maven plugin khi cần, không đánh giá toàn bộ bảo mật chỉ từ `curl` local.

## 5. Ví dụ B: Cloud Run service cho API nhiều endpoint

Một API Java/Spring Boot có nhiều route (`/orders`, `/products`, `/healthz`), cần request validation, exception filters, connection pooling và authentication middleware. Đây thường là **Cloud Run service** thay vì tách mọi endpoint thành một function.

Trong Spring Boot, application config tối thiểu:

~~~properties
server.address=0.0.0.0
server.port=${PORT:8080}
~~~

`PORT` do Cloud Run cung cấp (mặc định 8080); không chỉ bind localhost. Ví dụ handler:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrdersController {
    @GetMapping("/{id}")
    public ResponseEntity<String> getOrder(@PathVariable String id) {
        // Trong thực tế: đọc từ service/database với IAM và timeout.
        return ResponseEntity.ok("order=" + id);
    }
}
~~~

Đây là đoạn handler trong một **Spring Boot project đã có application class, web starter và build pipeline**, không phải dự án Maven hoàn chỉnh độc lập. Khác function trong mục 4, **chính ứng dụng Spring Boot** quản HTTP server và toàn bộ routing; vì vậy có quyền lựa chọn framework/filters/health endpoints riêng.

Sau khi CI đã build image `linux/amd64` và push lên Artifact Registry:

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

**Đừng dùng một service chỉ vì có nhiều dòng code.** Yếu tố quyết định là bạn có cần một web app/server và lifecycle tùy chỉnh hay không. Function cũng có thể được cấu hình revisions, CPU/memory, concurrency, VPC và nhiều tính năng của service; nó không nhất thiết là lựa chọn “đơn giản hơn nhưng kém mạnh hơn” về hạ tầng.

### Phát hành và mở rộng

- **Revisions** cho phép release image hoặc source mới và điều phối traffic/rollback theo Cloud Run.
- **Concurrency** là số request tối đa một instance có thể nhận đồng thời; phải thử tải để chọn hợp lý với Java heap, thread pool và Cloud SQL connections.
- **Min instances** giảm một phần cold start nhưng tăng chi phí; **max instances** hạn chế mở rộng song không thay giới hạn nghiệp vụ downstream.
- **Request timeout** mặc định 5 phút, tối đa 60 phút cho service; việc trả HTTP 504 **không bảo đảm xử lý phía server đã bị hủy ngay lập tức**.
- **CPU allocation** phụ thuộc request-based/instance-based billing, không nên chạy background thread quan trọng sau khi đã trả HTTP response rồi kỳ vọng nó luôn hoàn tất.

## 6. Ví dụ C: Cloud Run job chạy batch Java

Giả sử một ứng dụng phải tính báo cáo cho 1.000 khách hàng mỗi đêm. Công việc có điểm kết thúc, có thể chạy lại và không cần HTTP endpoint. **Cloud Run job** là lựa chọn tự nhiên.

### Chia việc bằng task index

File **`BatchMain.java`** mô phỏng phân vùng theo task index:

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
                // Thực tế: đọc DB, ghi báo cáo bằng khóa idempotency
                // (execution/customerId hoặc reportingDate/customerId).
                System.out.printf(
                    "task=%d/%d attempt=%d customer=%d%n",
                    taskIndex, taskCount, attempt, customerId);
            }
            // main kết thúc bình thường => exit code 0.
        } catch (Exception ex) {
            System.err.println("Batch failed: " + ex.getMessage());
            System.exit(1);
        }
    }
}
~~~

`CLOUD_RUN_TASK_INDEX` thuộc khoảng `0 .. CLOUD_RUN_TASK_COUNT - 1`; **job không tự chia các khách hàng** — code phải chọn subset. `CLOUD_RUN_TASK_ATTEMPT` tăng khi task retry, nhưng không nên chứa trong business idempotency key nếu muốn retry không tạo kết quả mới.

Dockerfile minh họa độc lập cho batch (lưu cùng `BatchMain.java` trong thư mục lab):

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

Build và push đến registry **đã có sẵn**:

~~~bash
PROJECT_ID="my-functions-lab"
REGION="asia-southeast1"
JOB_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/apps/report-batch:v1"

gcloud auth configure-docker "$REGION-docker.pkg.dev"
docker build --platform linux/amd64 -t "$JOB_IMAGE" .
docker push "$JOB_IMAGE"
~~~

Tạo job và chạy một execution:

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

Với bốn tasks và parallelism hai, có tối đa **hai tasks chạy đồng thời** theo cấu hình; thứ tự chạy không được bảo đảm. Nếu một task hết retries hoặc trả exit code khác 0, execution có thể thất bại.

**Giới hạn:** task timeout mặc định **10 phút**, có thể cấu hình tới **168 giờ** (GPU có giới hạn riêng). Timeout là **mỗi task attempt**, không phải timeout chung của cả execution; job có thể retry. Job **không tự được kích hoạt mỗi đêm** chỉ vì tên `daily-report` — cần Cloud Scheduler hoặc Workflows/API.

### Chạy theo lịch, không biến job thành HTTP server

~~~text
Cloud Scheduler (theo múi giờ nghiệp vụ)
      ↓ authenticated HTTP API call
Cloud Run Jobs API :run
      ↓
Job execution (4 tasks, parallelism 2)
      ↓
Database / Cloud Storage báo cáo
~~~

Scheduler identity phải có quyền **chạy job** (chẳng hạn permission `run.jobs.run` theo vai trò được hỗ trợ), và token OAuth thích hợp khi gọi Google Cloud API. Với nghiệp vụ nhiều bước, cần rẽ nhánh hoặc chờ job, cân nhắc **Workflows → Cloud Run job**. Không cấp quyền quản trị/deploy job chỉ để Scheduler được phép execute.

## 7. Eventarc: cách gọi function hoặc service khi có sự kiện

**Eventarc** giúp lọc và định tuyến sự kiện từ Cloud Storage, Pub/Sub, Audit Logs và các nguồn được hỗ trợ đến một **Cloud Run service**. Nếu destination là một **Cloud Run function**, Eventarc vẫn gửi **HTTP CloudEvent** tới service được triển khai từ mã nguồn function.

~~~mermaid
flowchart LR
  U["Ứng dụng upload ảnh"] --> B["Cloud Storage bucket"]
  B --> E["Eventarc trigger: finalized + bucket filter"]
  E --> F["Cloud Run function / service"]
  F --> S["Cloud Storage thumbnail + DB status"]
  I["Trigger service account"] --> E
~~~

Để nhận Cloud Storage finalized events, dùng event type:

~~~text
google.cloud.storage.object.v1.finalized
~~~

Không nhầm với tên `OBJECT_FINALIZE` trong **Pub/Sub notification attributes**. Với Eventarc direct event, một object có thể được gửi lại; thứ tự nhận không được bảo đảm. Handler nên dùng `source + id` hoặc `bucket + object + generation + operation` làm khóa chống trùng tùy nghiệp vụ.

### Java CloudEvent function

Đây là một handler riêng, thêm vào Java function source và sử dụng Functions Framework đã khai báo trong `pom.xml`:

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

        // Production: parse metadata JSON có validation,
        // lấy bucket, object name, generation;
        // claim job atomically, đọc đúng generation,
        // ghi thumbnail và commit trước khi return.
    }
}
~~~

Đoạn code là **khung CloudEvent nhận event**, chưa thực hiện resizing. Không chỉ log event rồi coi đã xử lý xong trong production. Với metadata JSON, tránh log toàn payload vì object name và custom metadata có thể nhạy cảm.

Deploy entrypoint Java riêng từ source:

~~~bash
gcloud run deploy image-finalized-handler \
  --source . \
  --function example.StorageEventFunction \
  --base-image java21 \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --no-allow-unauthenticated
~~~

**Chú ý:** CloudEvent function và HTTP function là **hai entrypoints** được triển khai thành **hai Cloud Run services** nếu dùng hai tên service trong ví dụ. Hàm CloudEvent không tự có trigger khi mới deploy; bước tiếp theo phải tạo Eventarc trigger.

### Tạo Eventarc trigger cho Cloud Storage

Giả sử bucket **cùng project** và có location tương thích với Eventarc trigger `asia-southeast1`; project đã có billing và service accounts theo quy trình. Các lệnh sau minh họa điều kiện IAM thiết yếu; có thể phải bổ sung quyền service agents/bật API theo thiết lập organization.

~~~bash
PROJECT_ID="my-functions-lab"
REGION="asia-southeast1"
BUCKET="my-image-events-lab-unique"
TRIGGER_SA="eventarc-trigger@$PROJECT_ID.iam.gserviceaccount.com"

gcloud services enable \
  eventarc.googleapis.com eventarcpublishing.googleapis.com \
  pubsub.googleapis.com storage.googleapis.com \
  run.googleapis.com

# Danh tính riêng của trigger; chỉ tạo nếu chưa có.
gcloud iam service-accounts create eventarc-trigger \
  --display-name="Invoke image-finalized-handler from Eventarc"

# Eventarc cần quyền nhận sự kiện theo nguồn/loại trigger.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/eventarc.eventReceiver"

# Trigger dùng danh tính này để gọi Cloud Run service PRIVATE.
gcloud run services add-iam-policy-binding image-finalized-handler \
  --region="$REGION" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/run.invoker"

# Cloud Storage service agent cần quyền publish qua tầng Pub/Sub.
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

**Không áp nguyên xi các IAM bindings lên production**: ví dụ cấp `roles/pubsub.publisher` cho Cloud Storage service agent ở **cấp project** theo quy trình Eventarc direct events, nên cần security review. Nếu đã có trigger identity hoặc binding, dùng IaC/import/kiểm tra trước khi tạo, tránh sở hữu chồng chéo. Trong tổ chức khóa chặt IAM, platform team có thể phải thực hiện một phần setup.

Kiểm tra:

~~~bash
gcloud eventarc triggers describe image-finalized-trigger \
  --location="$REGION"

# Chỉ upload vào bucket lab, không làm với dữ liệu production.
printf 'demo' > image-test.txt
gcloud storage cp image-test.txt "gs://$BUCKET/image-test.txt"

gcloud run services logs read image-finalized-handler \
  --region="$REGION" --limit=30
~~~

Function ở ví dụ chỉ log **eventId/source/payload length**; không tạo thumbnail. Kết quả mong đợi là sự kiện được route tới destination sau khi trigger/IAM có hiệu lực. Nếu không thấy log, kiểm tra location, event filters, Cloud Storage service agent, Eventarc trigger SA và Pub/Sub transport; không kết luận Java sai ngay.

**Quy tắc location:** với Eventarc direct events từ Cloud Storage, bucket phải ở **cùng project** và location tương thích với trigger. Destination Cloud Run ở **cùng project** với trigger, có thể ở region được hỗ trợ khác. Event type/filter đã tạo không nên coi là có thể sửa tại chỗ: để đổi loại event hoặc bộ lọc nguồn, thường cần **tạo trigger mới, xác minh rồi xóa trigger cũ**.

## 8. Reliability: retry, idempotency và lỗi không đồng bộ

Eventarc chuyển sự kiện qua transport Pub/Sub được quản lý, vì thế cần thiết kế cho **at-least-once delivery** và **không có bảo đảm thứ tự**. Không giả định “mỗi object chỉ được xử lý một lần” hoặc “event version cũ luôn tới trước version mới”.

### Ví dụ upload lại cùng object name

~~~text
Upload incoming/photo.jpg (generation 100)
Upload incoming/photo.jpg (generation 101)
           ↓
Eventarc có thể giao 101 trước 100 và giao trùng event 100
           ↓
Consumer phải dùng generation và idempotent operations
~~~

Khóa dedupe tham khảo:

~~~text
event dedupe key = cloudEvent.source + "|" + cloudEvent.id
business key     = bucket + "|" + objectName + "|" + generation + "|thumbnail"
~~~

`source+id` giúp nhận ra một CloudEvent đã giao lại; business key giúp giảm khả năng hai event/trigger khác nhau cùng tạo một thumbnail cho một generation. Khi ghi sang Cloud Storage, dùng **generation precondition** hoặc tên output gắn generation; khi ghi database, dùng unique constraint/transaction.

| Vấn đề | Hành vi đúng |
|---|---|
| Consumer gặp lỗi mạng tạm thời | Return lỗi để transport retry theo policy |
| File không đúng định dạng | Ghi trạng thái lỗi kiểm toán, cân nhắc DLQ; tránh retry vô hạn |
| Object generation đã bị xóa | Áp chính sách stale event, không lặng lẽ đọc generation mới |
| Xử lý xong nhưng response/ack thất lạc | Retry nhìn thấy kết quả đã commit và kết thúc idempotently |
| Event tới muộn sau sự kiện mới | Không cho event cũ ghi đè trạng thái current |
| Event bị bỏ lỡ vì cấu hình sai | Reconciliation bằng danh mục object và processing registry |

**Cloud Run service/function xử lý event qua HTTP**: chỉ báo thành công khi công việc **đã commit bền vững** hoặc **đã được enqueue an toàn** sang hệ thống khác. Không trả HTTP 2xx trước khi bắt đầu một background thread kéo dài; instance có thể mất CPU hoặc bị dừng.

### Tránh retry storm

Nếu backend Cloud SQL tạm lỗi và mọi event retry liên tục, database có thể càng quá tải. Cần:

- Retry có **backoff/jitter**, giới hạn tổng attempts và deadline.
- **Dead-letter handling** khi transport hỗ trợ; kiểm tra retry policy/underlying Pub/Sub subscription của trigger.
- Alert theo oldest-unacked age, DLQ và lỗi function/service.
- Giới hạn max instances/concurrency để giữ áp lực downstream trong khả năng; không dùng max instances như một guarantee không bao giờ vượt trong mọi tình huống.
- Theo dõi tính toàn vẹn nghiệp vụ bằng reconciliation, không chỉ HTTP success rate.

**Không mặc định trigger có thể gọi trực tiếp job**. Để xử lý event bằng job, một service/function trung gian có thể xác thực event và gọi **Jobs API :run**, hoặc dùng Workflows để điều phối; việc gọi là một thao tác riêng với IAM/duplicate-execution risk riêng. Đối với mỗi file nhỏ, tạo một job execution có thể tốn thời gian và chi phí khởi động hơn việc xử lý ngay tại event function.

## 9. Timeout, scaling và tính phí khi chọn nền tảng

| Yếu tố | HTTP function / service | Event-driven function / service | Job |
|---|---|---|---|
| Thời lượng | Ràng buộc request timeout | Ràng buộc HTTP delivery/trigger và cách deploy | Ràng buộc task timeout |
| Mặc định đáng nhớ | Service request timeout 5 phút | Theo request timeout và cơ chế trigger được dùng | Task timeout 10 phút |
| Giới hạn tham khảo | Service tối đa 60 phút | **Cloud Functions v2 API event-driven** có thể bị giới hạn 9 phút; đường Cloud Run Admin API cần xét chính sách service/trigger | Task tối đa 168 giờ, GPU có giới hạn riêng |
| Concurrency | Có thể nhận nhiều request mỗi instance | Có thể nhận nhiều event request mỗi instance khi cấu hình | Parallelism giới hạn số tasks đồng thời |
| Mở rộng | Autoscaling theo request/concurrency và config | Autoscaling theo lượng event requests tới service | `tasks` và `parallelism` tại execution |
| Billing | Cloud Run service: request-based/instance-based theo cấu hình | **Cũng là Cloud Run service**, cộng Eventarc/transport | CPU/memory trong thời gian chạy task |
| Phụ thuộc bên ngoài | DB/API/network latency | Eventarc/Pub/Sub + DB/API + retries | Job startup, partitioning, DB/API, retries |

**Các giới hạn thay đổi theo API generation, cấu hình và loại workload.** Đừng lấy timeout 9 phút của Cloud Functions v2 API rồi khẳng định mọi Cloud Run function đều chỉ chạy tối đa 9 phút; cũng đừng lấy tối đa 60 phút của HTTP service rồi cho rằng một event trigger luôn chờ được 60 phút. Xem đúng tài liệu và cách deploy thực tế.

### Chi phí dự toán

~~~text
Function / service:
  Cloud Run CPU + memory + request/instance time theo billing
  + source build/Artifact Registry (khi deploy từ source)
  + Eventarc/PubSub (nếu nhận events)
  + network, storage, logging, database...

Job:
  tổng task execution CPU/memory time
  + image registry, network, storage, logging, database...
  + Scheduler/Workflows (nếu dùng)
~~~

Function **không tự rẻ hơn** service chỉ vì có ít code: chúng dùng cùng nền tảng Cloud Run. Job có thể tối ưu khi batch chạy đúng lịch và **không chiếm tài nguyên liên tục giữa các executions**; nhưng task kéo dài, retries, parallelism lớn và downstream access vẫn gây chi phí đáng kể.

### Cold start và năng lực xử lý

Java app có thể mất thời gian tải class, warmup JIT, tạo DB pool. **Function/source deployment không xóa hiện tượng cold start**; service cũng có cold start. Min instances, startup CPU boost, tối ưu image/dependencies và tránh kết nối đồng bộ chậm trong startup có thể cải thiện latency nhưng cần tính phí.

Nếu batch phải xong trước giờ đóng sổ, không chỉ tăng `--parallelism`; phải thử throughput thực, giới hạn Cloud SQL, Pub/Sub, networking và quota. Parallelism quá cao có thể làm database chậm hơn hoặc tăng lỗi.

## 10. IAM: phân biệt deployer, invoker, trigger và runtime

Nhiều lỗi `403` đến từ việc **cấp đúng role nhưng cho sai danh tính**. Bốn vai trò trong một pipeline có thể là bốn service accounts khác nhau:

| Danh tính | Thực hiện gì? | Quyền thường cần |
|---|---|---|
| **Deployer/CI/CD** | Build và deploy source/image, update service/job | Cloud Run deployment, Service Account User và quyền build/registry cần thiết |
| **Trigger identity** | Eventarc gọi destination private | `roles/run.invoker` trên đúng Cloud Run service; `roles/eventarc.eventReceiver` khi nguồn yêu cầu |
| **Runtime service account** | Code trong container gọi Cloud Storage, Pub/Sub, Cloud SQL | Role nghiệp vụ **trên resource cụ thể**, không phải Editor |
| **Scheduler/Workflow identity** | Gọi Jobs API để bắt đầu execution | Quyền `run.jobs.run` hoặc vai trò executor phù hợp |

Với direct Cloud Storage event, **Cloud Storage service agent** còn cần quyền publish sự kiện sang Pub/Sub transport do Eventarc quản lý. Cấp role cho runtime service account **không tự cấp** cho storage service agent hoặc trigger service account.

### Luồng xác thực tách biệt

~~~text
Gửi event:
  Cloud Storage service agent → Pub/Sub transport (Publisher)
  Eventarc trigger identity → Cloud Run service (Invoker)

Xử lý dữ liệu:
  Function / service runtime SA → Cloud Storage object (Object Viewer)
  Function / service runtime SA → Cloud SQL (Cloud SQL Client + DB auth)

Chạy batch:
  Cloud Scheduler SA → Cloud Run Jobs API (run.jobs.run)
  Job runtime SA → Cloud Storage / database (role nghiệp vụ)
~~~

Đối với Java, dùng **Application Default Credentials (ADC)** của Cloud Run service identity để gọi Google Cloud APIs; **không** nhúng service account key JSON vào image hoặc mã nguồn. Để đọc file từ Cloud Storage, runtime SA cần quyền đọc trên bucket/object phù hợp **và** network path/API hoạt động.

### Thực hành bảo mật

- Chỉ mở public HTTP function/service nếu cần webhook/public API thật sự; còn lại dùng private service và IAM Invoker.
- Với webhook từ bên ngoài, xác minh **chữ ký của bên gửi**; Cloud Run IAM không thay kiểm tra chữ ký ứng dụng khi endpoint phải public.
- Không đặt secrets trong image, URL hoặc event payload; dùng Secret Manager và IAM scope hẹp.
- Kiểm tra IAM Conditions, Organization Policy, VPC Service Controls và IAM Deny khi role Allow có vẻ đúng nhưng vẫn 403.
- Hạn chế quyền Pub/Sub subscribers, Eventarc trigger admin và người sửa destination: sửa trigger/endpoint có thể chuyển sự kiện nhạy cảm.
- Giữ Cloud Logging/Audit Logs ở phạm vi hợp lý, không ghi toàn payload hay bearer token.

## 11. Tình huống doanh nghiệp: ba công việc, ba quyết định

Một nhóm thương mại điện tử chạy ứng dụng trên Google Cloud, cần:

| Nhu cầu | Thiết kế khuyến nghị | Vì sao |
|---|---|---|
| **API đặt hàng Java**, khoảng 12 endpoint, nhiều lớp middleware, Cloud SQL | **Cloud Run service** từ image CI | Kiểm soát Spring Boot/routing, release, concurrency, DB pooling |
| **Upload ảnh sản phẩm**, tạo thumbnail, gửi metadata vào Pub/Sub | **Cloud Run function** nhận Cloud Storage Eventarc finalized | Một handler nhỏ, được build từ source, dễ theo event |
| **Báo cáo doanh thu hằng đêm** cho hàng triệu đơn, có thể chia partition | **Cloud Run job** chạy theo Cloud Scheduler/Workflows | Có execution, task count, parallelism và exit code |

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

**Vì sao không dùng một function cho mọi thứ?** API nhiều route và middleware tự nhiên hơn khi phát triển như web service; batch có thể vượt request timeout và nên có cơ chế hoàn tất task; function event xử lý gọn một việc có ngữ nghĩa idempotent.

**Có thể thay function bằng service không?** Có. Nếu pipeline ảnh cần nhiều route, thư viện native riêng, media processing phức tạp hoặc framework thống nhất, có thể deploy Cloud Run service container và gắn **cùng Eventarc trigger**. Trigger không yêu cầu destination phải được triển khai bằng `--function`.

**Có thể thay job bằng function không?** Với báo cáo rất nhỏ hoàn tất dưới timeout và cần phản hồi từng event, có thể. Nhưng khi phải chạy hàng giờ, chia nhiều partition, retry theo task và lưu execution history, job rõ ràng hơn.

### Một trường hợp thứ tư: consumer luôn mở kết nối

Ứng dụng Java `KafkaConsumer.poll()` chạy liên tục, không có HTTP request và không có điểm kết thúc. Đừng cố làm job không bao giờ exit. Cân nhắc **Cloud Run worker pool** (manual scaling), hoặc kiến trúc chuyển Kafka/Pub/Sub thành push HTTP vào service khi phù hợp. Đây là ngoại lệ quan trọng của cây quyết định ở mục 1.

## 12. Xử lý sự cố theo đúng lớp

| Triệu chứng | Nguyên nhân thường gặp | Bước xác minh |
|---|---|---|
| Function build thất bại | Thiếu `pom.xml`/dependency, sai function entrypoint hoặc runtime | Cloud Build logs và `--function` FQCN |
| Java function deploy xong nhưng trả 404 | Handler path/method không phù hợp, gọi sai service URL | `gcloud run services describe`, request logs |
| Function/cloud service startup lỗi cổng | Container tự quản không đọc `PORT`, lỗi entrypoint/JVM | Revision logs; nếu function thì kiểm tra Functions Framework build |
| HTTP 401/403 khi gọi URL | Thiếu Invoker, ID token audience sai, ingress restrictions | Caller identity và Cloud Run IAM |
| Không có Cloud Storage event | Bucket/trigger location sai, event filter không match, IAM Publisher/Invoker thiếu | `eventarc triggers describe`, Pub/Sub transport, IAM |
| Event chạy hai lần | At-least-once hoặc retry sau timeout | Idempotency key, durable processing registry |
| Function trả 2xx nhưng thumbnail không có | Code tạo background thread rồi return, downstream lỗi không được đợi | Chỉ return sau commit/enqueue |
| Job không chạy mỗi đêm | Chưa có Cloud Scheduler/Workflow hoặc thiếu run.jobs.run | Scheduler job logs, OAuth, Job executions |
| Job execution FAILED | Task nonzero, timeout, OOM hoặc retries hết | Execution/task logs và task index/attempt |
| HTTP 504 nhưng DB đã ghi | Client timeout trước khi handler trả response | Request deadline, DB transaction, idempotency |
| Hóa đơn tăng | Min instances cao, retries, concurrency thấp, logs/event volume cao | Billing theo SKU, Cloud Run/Artifact Registry/Eventarc |

Lệnh quan sát gợi ý:

~~~bash
gcloud run services describe image-finalized-handler \
  --region="$REGION"
gcloud run services logs read image-finalized-handler \
  --region="$REGION" --limit=50

gcloud eventarc triggers describe image-finalized-trigger \
  --location="$REGION"
gcloud run jobs describe daily-report --region="$REGION"

# Tham khảo Cloud Logging / Monitoring cho executions,
# Pub/Sub backlog, Cloud Run request count và 5xx.
~~~

Với event bị trễ, không kết luận “Cloud Run không chạy” chỉ vì request logs vắng; xác minh event **đã được phát** và trigger đã định tuyến. Với job failed, xem **từng task attempt** chứ không chỉ trạng thái tổng thể.

### Chỉ số SRE cần có

| Loại | Chỉ số ưu tiên |
|---|---|
| HTTP function/service | Request rate, error rate, P95/P99 latency, cold start, instance count |
| Eventarc pipeline | Event delivery failure, duplicate/stale count, processing lag, DLQ |
| Job | Success rate, execution/task duration, attempts, backlog việc chưa làm |
| Dependencies | Cloud SQL connections/latency, Storage read/write failures, API quota |
| Chi phí | Cloud Run CPU/memory time, source-build/image storage, event routing, egress/logging |

Một chỉ số “HTTP function trả 200” không chứng minh business transaction/thumbnail đã ghi đúng. Nên đo **tác vụ hoàn tất** bằng processing status hoặc số object kết quả và đối soát với nguồn.

## 13. Checklist lựa chọn và triển khai

- [ ] Đã xác định **request-driven**, **event-driven** hay **run-to-completion**.
- [ ] Nếu function, hiểu nó được build từ source thành một **Cloud Run service**.
- [ ] Nếu service, application mở HTTP server trên đúng `PORT` và hỗ trợ graceful shutdown.
- [ ] Nếu job, command hoàn thành và trả đúng exit code; tasks phân vùng dữ liệu rõ.
- [ ] Đã chọn trigger thích hợp: HTTP caller, Eventarc, Cloud Scheduler/Workflows.
- [ ] Không lẫn **Eventarc CloudEvent type** với Pub/Sub notification attribute name.
- [ ] Có idempotency/preconditions và retry/DLQ cho event hoặc job task.
- [ ] Đã kiểm tra timeout/concurrency/parallelism bằng load test và SLA/SLO nghiệp vụ.
- [ ] Deployer, trigger identity, runtime SA và scheduler identity được cấp **quyền riêng**.
- [ ] Không nhúng JSON service account key; secrets qua Secret Manager.
- [ ] Cloud Storage/Cloud SQL/network permissions, region và quotas được xác nhận.
- [ ] Có logs/metrics/alerts cho HTTP errors, event lag, job failures, chi phí.
- [ ] Có kế hoạch rollback release/trigger và xóa tài nguyên thử nghiệm đúng owner.

## 14. Bài tập vận dụng

**Bài 1 — Chọn tài nguyên.** Phân loại và giải thích bốn workload: (a) webhook thanh toán cần kiểm tra chữ ký; (b) xử lý thumbnail khi object finalized; (c) tổng hợp dữ liệu hằng đêm 40 phút; (d) Kafka consumer chạy mãi. Với mỗi workload, nêu tài nguyên, cách kích hoạt và điều kiện được coi là hoàn tất.

**Bài 2 — Java function.** Từ `HelloFunction` ở mục 4, thêm header trả về JSON và biến môi trường `GREETING`; mô tả cách chạy kiểm thử local bằng Functions Framework rồi deploy với `--function example.HelloFunction` và runtime Java 21. Vì sao function không cần tự quản `PORT`?

**Bài 3 — Eventarc và IAM.** Một Cloud Storage bucket `images-lab` phát finalized events vào private `image-finalized-handler`. Vẽ ba danh tính **Storage service agent**, **Eventarc trigger SA**, **runtime SA** và cấp role tối thiểu cho từng bước. Giải thích vì sao cấp Object Viewer cho runtime SA **không đủ** để Eventarc gửi event.

**Bài 4 — Xử lý trùng.** Object `incoming/photo.jpg` được upload hai lần, generations 100 và 101. Event của 101 đến trước 100, sau đó event 100 bị giao lại. Viết khóa idempotency, chiến lược output name và database condition để thumbnail mới không bị event cũ ghi đè.

**Bài 5 — Job song song.** Cần xử lý 1.000 khách hàng với `--tasks=4 --parallelism=2 --max-retries=2`. Theo code ở mục 6, task index 2 xử lý những customer ID nào? Nếu task này bị retry, vì sao `attempt` không được tạo một bộ kết quả mới? Dùng exit code nào cho lỗi tạm thời?

**Bài 6 — Quyết định chi phí và vận hành.** So sánh một HTTP function và một service Spring Boot ở cùng mức 100.000 request/ngày, cùng CPU/memory/concurrency. Liệt kê chi phí chung và phần phát sinh do build từ source, xác định khi nào min instances đáng chi phí, và nêu vì sao không thể kết luận “function luôn rẻ hơn service”.

**Bài 7 — Kiến trúc mở rộng.** API cần nhận file 2 GiB, tạo OCR có thể mất 90 phút và trả kết quả khi xong. Thiết kế Cloud Run service nhận request, Cloud Storage lưu file, Pub/Sub/Cloud Tasks hoặc Workflows điều phối Cloud Run job; trình bày idempotency, checkpoint, callback/status polling và SLO.

## Tài liệu tham khảo chính thức

- [What is Cloud Run](https://cloud.google.com/run/docs/overview/what-is-cloud-run) — services, jobs, worker pools và instances.
- [Cloud Run deployment options and resource model](https://cloud.google.com/run/docs/resource-model) — source, image, functions và các tài nguyên.
- [Cloud Run functions overview](https://cloud.google.com/run/docs/functions/overview) — function được build/deploy thành service.
- [Compare Cloud Run functions](https://cloud.google.com/run/docs/functions/comparison) — Cloud Run Admin API, Cloud Functions v2 API và 1st gen.
- [Write Cloud Run functions](https://cloud.google.com/run/docs/write-functions) — HTTP/CloudEvents handlers, Java Functions Framework.
- [Deploy a Cloud Run function](https://cloud.google.com/run/docs/deploy-functions) — `gcloud run deploy --function`.
- [Java runtime](https://cloud.google.com/run/docs/runtimes/java) — runtime IDs và base image.
- [Deploy a Cloud Run service](https://cloud.google.com/run/docs/deploying) — image/source, revisions.
- [Create Cloud Run jobs](https://cloud.google.com/run/docs/create-jobs) — tasks, retries và execution.
- [Set a task timeout for jobs](https://cloud.google.com/run/docs/configuring/task-timeout) — giới hạn thời gian chạy.
- [Eventarc triggers for Cloud Run](https://cloud.google.com/run/docs/triggering/trigger-with-events) — CloudEvents, filters và trigger IAM.
- [Route Cloud Storage events with Eventarc](https://cloud.google.com/eventarc/standard/docs/run/route-trigger-cloud-storage) — location, Eventarc roles, Cloud Storage service agent.
- [Cloud Run service identity](https://cloud.google.com/run/docs/securing/service-identity) — ADC và IAM.
- [Cloud Run pricing](https://cloud.google.com/run/pricing) — billing cho functions/services/jobs.
- [Eventarc pricing](https://cloud.google.com/eventarc/pricing) — event routing.
