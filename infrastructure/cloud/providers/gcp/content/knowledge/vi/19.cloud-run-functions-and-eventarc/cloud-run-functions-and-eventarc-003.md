# HTTP functions và event-driven functions trong Cloud Run

Một dịch vụ Java có thể cần hai kiểu xử lý rất khác nhau: phản hồi ngay khi đối tác gọi webhook xác nhận đơn hàng, và tự động xử lý một tệp mới được tải lên Cloud Storage. Kiểu đầu phù hợp **HTTP function**; kiểu sau phù hợp **event-driven function** được kích hoạt qua **Eventarc**.

Cả hai đều có thể viết bằng **Functions Framework for Java** và triển khai dưới dạng **Cloud Run service**. Điểm khác biệt chủ yếu là **ai kích hoạt**, **định dạng đầu vào**, **cách xác nhận kết quả**, và **chiến lược xử lý lỗi/trùng lặp**. Bài thuộc chương **Cloud Run functions và Eventarc** trong mô-đun `CLOUD_PROVIDERS_GCP`, gắn việc xây dựng ứng dụng với IAM, VPC, Cloud Run, Cloud Storage, Pub/Sub, CI/CD, độ tin cậy và chi phí.

**Phạm vi:** Cloud Run functions hiện hành, tạo và quản lý bằng **Cloud Run Admin API / `gcloud run`**, Java 21, Eventarc Standard. Cú pháp `gcloud functions deploy` thuộc đường **Cloud Functions v2 API** vẫn được hỗ trợ để tương thích nhưng không phải đường triển khai chính của ví dụ. Không nhầm với **Cloud Run functions (1st gen)** hoặc **Cloud Run jobs**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chọn HTTP hay CloudEvents theo đặc điểm request hoặc sự kiện.
2. Giải thích mối quan hệ giữa Functions Framework, Cloud Build, Artifact Registry, Cloud Run và Eventarc.
3. Viết hai class Java: `HttpFunction` và `CloudEventsFunction`.
4. Deploy function từ source bằng `gcloud run deploy --function`, kiểm tra service và logs.
5. Tạo Eventarc trigger lọc sự kiện Cloud Storage `object.v1.finalized` và gửi tới function riêng tư.
6. Phân tách IAM cho người deploy, runtime service account, Eventarc trigger và event source.
7. Xử lý **at-least-once delivery**, event trùng, không có bảo đảm thứ tự và retries.
8. Thiết kế idempotency, giới hạn concurrency/timeout và giám sát trước production.
9. Thực hành kiểm thử tích cực/tiêu cực và xây runbook xử lý sự cố.

## 1. HTTP function và event-driven function khác nhau thế nào?

| Tiêu chí | HTTP function | Event-driven / CloudEvents function |
| --- | --- | --- |
| Nguồn kích hoạt | HTTP(S) client, webhook, service khác | Cloud Storage, Pub/Sub, Firestore hoặc nguồn sự kiện được Eventarc hỗ trợ |
| Java interface | `HttpFunction` | `CloudEventsFunction` |
| Đầu vào | `HttpRequest`: method, path, headers, body | `CloudEvent`: id, type, source, time, data |
| Đầu ra | `HttpResponse`, status/body/headers | Hoàn tất xử lý hoặc báo lỗi để hệ thống giao sự kiện quyết định retry |
| Cách triển khai hiện hành | Deploy Cloud Run function nhận HTTP | Deploy Cloud Run function, **sau đó** tạo Eventarc trigger |
| Xác thực | Cloud Run IAM; với public webhook thêm cơ chế xác minh nguồn | Eventarc trigger service account gọi Cloud Run service có IAM Invoker |
| Đặc tính gọi | Đồng bộ với caller; client quyết định retry | Thường không đồng bộ; **có thể giao lại** nếu retry được bật |
| Phù hợp | API nhẹ, webhook, health/action endpoint | Xử lý object mới, phản ứng sự kiện hạ tầng, event pipeline |

**Mọi Cloud Run function đều được triển khai thành Cloud Run service có HTTP endpoint.** “Event-driven” có nghĩa **Eventarc gửi CloudEvent đến endpoint đó** qua HTTP, chứ không phải runtime không dùng HTTP. Không dùng `HttpFunction` để tự parse body CloudEvent khi đã chọn CloudEvents signature nếu không có lý do rõ ràng.

### 1.1. Đừng nhầm “event-driven” với xử lý nền vô hạn

Function nên hoàn thành một đơn vị công việc trong **thời gian xử lý request** và trả kết quả. Không tạo thread nền rồi trả `2xx` ngay, vì công việc có thể bị dừng mà Eventarc đã coi sự kiện được xác nhận. Với job dài hoặc fan-out lớn, cân nhắc **Cloud Run jobs, Cloud Tasks, Pub/Sub hoặc Workflows** theo mục tiêu.

## 2. Kiến trúc từ source tới execution

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

Khi chạy `gcloud run deploy --source --function`, Google Cloud phối hợp **Cloud Build** để đóng gói source bằng buildpacks, lưu image tại **Artifact Registry** và tạo revision của Cloud Run service. Eventarc là phần **định tuyến sự kiện**, không phải container runtime. Khi dùng Console, trigger có thể được thêm trong luồng tạo function; với CLI, tài liệu khuyến nghị **deploy function trước, tạo trigger sau**.

Các tính năng Cloud Run như cấu hình CPU/memory, environment variables, secrets, networking, IAM, concurrency và traffic revisions vẫn có liên quan. Đường Cloud Functions v2 API có một số giới hạn/quy tắc khác với dịch vụ tạo trực tiếp bằng Cloud Run Admin API, vì vậy không sao chép cấu hình timeout/triggers giữa hai đường mà không kiểm tra.

## 3. Functions Framework và entry point trong Java

Một project Maven có thể chứa **nhiều class handler**, nhưng mỗi lệnh deploy chỉ định một **entry point** được chạy:

~~~text
functions-lab/
├── pom.xml
└── src/main/java/functions/
    ├── HelloHttp.java
    └── StorageFinalized.java
~~~

- `functions.HelloHttp` triển khai `HttpFunction` với phương thức `service(...)`.
- `functions.StorageFinalized` triển khai `CloudEventsFunction` với phương thức `accept(...)`.
- `--function=functions.HelloHttp` hoặc `--function=functions.StorageFinalized` chọn class qua **tên đầy đủ có package**, không phải tên Cloud Run service.

Ví dụ `pom.xml` tối thiểu cho Java 21:

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

Các phiên bản trên phục vụ **ví dụ có thể tái lập**; trước khi đưa vào production, cập nhật dependency/plugin theo phiên bản được hỗ trợ và chính sách security của dự án. Build phải dùng Java 21 tương thích. `functions-framework-api` được runtime cung cấp nên có scope `provided`.

## 4. Viết HTTP function bằng Java

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

Handler này minh họa **request/response** và HTTP status. Không phụ thuộc database nên phù hợp smoke test. Với webhook thật, cần kiểm tra **signature, timestamp, replay protection, request body size, content type và business authorization** trước khi ghi dữ liệu. Cloud Run IAM bảo vệ **ai được gọi endpoint**, còn chữ ký webhook bảo vệ danh tính thông điệp của đối tác khi endpoint được cấu hình nhận từ bên ngoài.

HTTP function có thể nhận request liên tiếp hoặc song song theo **concurrency** của Cloud Run; **không lưu trạng thái nghiệp vụ trong biến static hoặc local disk** rồi kỳ vọng mọi invocation thấy cùng một dữ liệu.

## 5. Viết event-driven function nhận Cloud Storage CloudEvent

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

        // Demo: log metadata, không log nội dung object hay secrets.
        LOG.info("eventId=" + event.getId()
                + " source=" + event.getSource()
                + " bucket=" + object.getBucket()
                + " generation=" + object.getGeneration());

        // Production: xử lý có idempotency và đánh dấu hoàn tất trong DB.
    }
}
~~~

Các trường chuẩn trong CloudEvent:

| Field | Ý nghĩa |
| --- | --- |
| `id` | ID của event trong phạm vi source |
| `source` | Nguồn phát event |
| `type` | Loại event, ví dụ `google.cloud.storage.object.v1.finalized` |
| `time` | Thời điểm event được ghi nhận khi được cung cấp |
| `subject` | Đối tượng cụ thể mà event mô tả, nếu có |
| `data` | Payload riêng của event type; trong ví dụ là metadata object |

Một ví dụ **CloudEvent dữ liệu minh họa**:

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

**Không coi JSON trên là toàn bộ HTTP wire format bắt buộc.** Eventarc có thể gửi CloudEvent ở HTTP binary content mode: attributes nằm ở các header `ce-*` và payload ở body; Functions Framework giải mã thành `CloudEvent` cho Java. Không cần tự parse headers khi dùng interface trên.

**Quan trọng:** `object.v1.finalized` xuất hiện khi tạo **generation mới**, bao gồm **upload lần đầu và overwrite**. Nếu xử lý tệp bằng tên đơn thuần, một bản overwrite có thể khiến handler đọc nhầm nội dung mới hơn; cần xét `bucket + name + generation` và API đọc một generation cụ thể.

## 6. Chuẩn bị project, API và IAM

Những lệnh trong bài là **mẫu chạy ở project lab**, có thể tạo tài nguyên tính phí. Chỉ triển khai nếu tổ chức cho phép. Thay `PROJECT_ID`, `BUCKET_NAME` và các service accounts bằng giá trị thật; tránh dùng dữ liệu khách hàng trong thử nghiệm.

~~~bash
gcloud auth list
gcloud config get-value project

# Nếu đã bật API thì không cần bật lại.
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com eventarc.googleapis.com \
  pubsub.googleapis.com storage.googleapis.com \
  --project=PROJECT_ID
~~~

Cần Cloud Billing, quota và quyền triển khai nguồn Cloud Run (thường gồm **Cloud Run Source Developer**, **Service Usage Consumer**, quyền **actAs** với runtime service account). Build identity cần quyền liên quan Cloud Build/Artifact Registry; runtime identity chỉ cần quyền API nghiệp vụ.

**Tách ba danh tính:**

1. **Deployer/build identity:** biên dịch, push và tạo revision.
2. **Runtime service account:** code Java dùng để truy cập Cloud Storage, Cloud SQL, Pub/Sub hoặc Secret Manager.
3. **Eventarc trigger service account:** danh tính **gọi Cloud Run service** khi có event, không phải identity xử lý nội dung trong Java.

Không cấp Editor/Owner rộng để sửa nhanh lỗi `403`. Với service riêng tư, Eventarc trigger identity cần **`roles/run.invoker`** trên service, và với những sự kiện trực tiếp như Cloud Storage cần **`roles/eventarc.eventReceiver`** ở phạm vi phù hợp. **Cloud Storage service agent** có thể cần **`roles/pubsub.publisher`** để Eventarc nhận thông báo nguồn.

## 7. Deploy HTTP function từ source

Từ thư mục chứa `pom.xml` và source:

~~~bash
gcloud run deploy orders-http-lab \
  --source=. \
  --function=functions.HelloHttp \
  --base-image=java21 \
  --region=asia-southeast1 \
  --no-allow-unauthenticated \
  --project=PROJECT_ID
~~~

Hướng triển khai trên dùng **Cloud Run Admin API**. `--no-allow-unauthenticated` yêu cầu xác thực, tránh công khai endpoint demo. Nếu gặp lỗi build, kiểm tra Maven source layout, compile target, plugin dependencies, build logs, quyền build identity và Artifact Registry.

Xem service:

~~~bash
gcloud run services describe orders-http-lab \
  --region=asia-southeast1 \
  --project=PROJECT_ID

gcloud run services logs read orders-http-lab \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --limit=20
~~~

### 7.1. Kiểm thử HTTP service riêng tư

Để tránh đặt ID token vào command history, dùng **Cloud Run local proxy** (CLI identity phải có quyền gọi service):

~~~bash
# Terminal thứ nhất: để tiến trình proxy tiếp tục chạy
gcloud run services proxy orders-http-lab \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --port=8080

# Terminal thứ hai:
curl -i http://127.0.0.1:8080/
curl -i -X POST http://127.0.0.1:8080/
~~~

Kỳ vọng `GET` trả `200` và JSON; `POST` trả `405 Method Not Allowed`. Đây là hành vi **ứng dụng demo**, không phải một hệ thống authentication/authorization hoàn chỉnh.

Với production webhook công khai, `--allow-unauthenticated` chỉ nên dùng sau khi đã xác minh yêu cầu thực sự cần public ingress, có kiểm tra chữ ký nguồn và cơ chế bảo vệ abuse; phương án phù hợp hơn có thể là API Gateway hoặc service-to-service IAM.

## 8. Deploy CloudEvents function và tạo Eventarc trigger

### 8.1. Deploy service nhận sự kiện

~~~bash
gcloud run deploy orders-storage-events \
  --source=. \
  --function=functions.StorageFinalized \
  --base-image=java21 \
  --region=asia-southeast1 \
  --no-allow-unauthenticated \
  --project=PROJECT_ID
~~~

Event handler vẫn được triển khai thành **Cloud Run service**. Chưa có trigger thì **upload một tệp lên bucket chưa tự gọi handler**. Trong Cloud Run Admin API flow, tạo Eventarc trigger sau deploy.

### 8.2. Chuẩn bị nguồn sự kiện và trigger identity

Giả định **bucket `BUCKET_NAME` đã tồn tại**, thuộc project/region hỗ trợ Eventarc direct Cloud Storage events; trong lab nên chọn **regional bucket ở `asia-southeast1`** để khớp trigger location. Không tự tạo hoặc xóa bucket production.

~~~bash
# Chỉ đọc vị trí bucket và project:
gcloud storage buckets describe gs://BUCKET_NAME \
  --project=PROJECT_ID

# Danh tính dành riêng cho Eventarc, không dùng default SA quá rộng:
gcloud iam service-accounts create eventarc-delivery-lab \
  --project=PROJECT_ID
~~~

Cấp quyền theo tổ chức đã phê duyệt, ví dụ:

~~~bash
# Trigger SA có quyền nhận event trực tiếp (Cloud Storage).
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:eventarc-delivery-lab@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/eventarc.eventReceiver"

# Trigger SA có quyền gọi Cloud Run service riêng tư.
gcloud run services add-iam-policy-binding orders-storage-events \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --member="serviceAccount:eventarc-delivery-lab@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

Đối với direct events từ Cloud Storage, Cloud Storage **service agent** thường cần quyền **Pub/Sub Publisher**. Lấy email service agent từ `gcloud storage service-agent --project=PROJECT_ID`, sau đó quản trị viên cấp `roles/pubsub.publisher` trên phạm vi thích hợp; đừng cấp quyền cho **runtime service account** thay vì service agent. Nếu project đã được cấu hình, không tạo thêm các bindings trùng lặp.

### 8.3. Tạo trigger lọc sự kiện object finalized

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

- `type` chỉ nhận loại event khi object được tạo/overwrite thành generation mới.
- `bucket` chọn bucket cụ thể; filter phải dùng **tên bucket**, không phải `gs://` URL.
- `--location` là vị trí của trigger; với direct Cloud Storage events phải tương thích với **location của bucket**. Destination service có thể ở region khác theo giới hạn hỗ trợ, nhưng nên gần nguồn khi phù hợp.
- `--service-account` xác định identity dùng để giao event; Eventarc **không mượn IAM của người deploy** lúc runtime.
- Trigger có thể cần **vài phút để hoạt động** sau khi tạo; không kết luận lỗi chỉ vì upload ngay lập tức chưa thấy invocation.

Xác minh:

~~~bash
gcloud eventarc triggers describe orders-file-finalized \
  --location=asia-southeast1 \
  --project=PROJECT_ID

gcloud eventarc triggers list \
  --location=asia-southeast1 \
  --project=PROJECT_ID
~~~

### 8.4. Kích hoạt event và xem logs

~~~bash
# Dùng một tệp văn bản vô hại đã tạo tại máy lab:
printf 'hello from lab\n' > sample-event.txt

gcloud storage cp sample-event.txt \
  gs://BUCKET_NAME/incoming/sample-event.txt

gcloud run services logs read orders-storage-events \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --limit=50
~~~

Handler demo ghi `eventId`, `source`, `bucket` và `generation`. Nếu muốn tái kích hoạt event, upload lại sẽ tạo **generation mới**, không chắc cùng event ID. Đọc logs sau khi trigger đã healthy và cho phép độ trễ giao sự kiện.

## 9. Eventarc Standard: at-least-once và thứ tự sự kiện

**Một event có thể được giao nhiều lần** khi retry được bật. Eventarc Standard không cam kết FIFO; các events từ cùng đối tượng cũng có thể đến **khác thứ tự** so với thứ tự tạo.

~~~mermaid
sequenceDiagram
    participant G as Cloud Storage
    participant E as Eventarc / PubSub transport
    participant F as Cloud Run function
    participant D as Dedupe store
    G->>E: Event E1 (generation 100)
    E->>F: Giao E1
    F->>D: Lưu kết quả idempotent
    Note over E,F: Response bị mất hoặc handler lỗi
    E->>F: Giao lại E1
    F->>D: Thấy E1 đã xử lý
    F-->>E: 2xx, không nhân đôi side effect
~~~

### 9.1. Chọn idempotency key

Theo CloudEvents, cặp **`source + id`** phân biệt một event cụ thể. Với sự kiện Cloud Storage finalized, cũng có thể dùng **`bucket + objectName + generation`** để nhận diện một phiên bản object cần xử lý.

Ví dụ:

~~~text
idempotencyKey = event.source + "|" + event.id

Hoặc cho workload xử lý từng generation:
workKey = bucket + "/" + objectName + "#" + generation
~~~

Lưu key trong **Cloud SQL (unique constraint), Firestore transaction**, hoặc tạo object output theo tên bất biến với **Cloud Storage generation precondition**. Bộ nhớ static, instance cache hoặc filesystem tạm không phù hợp làm dedupe toàn hệ thống vì Cloud Run scale nhiều instances.

**Đừng chỉ log ID rồi coi là idempotent.** Trước khi gửi email, tính tiền, tạo output hoặc publish Pub/Sub message, phải bảo đảm side effect không bị nhân đôi. Nếu thao tác có nhiều hệ thống, dùng transactional/outbox và idempotency key tương ứng.

### 9.2. Khi event đến không đúng thứ tự

Nếu object `orders/state.json` được overwrite thành generation G2 rồi G3, một handler của G2 có thể chạy sau handler G3. Đừng dựa vào **thời điểm nhận event** hoặc so số generation như một đồng hồ nghiệp vụ toàn cục.

Tùy yêu cầu:

- **Xử lý từng generation:** đọc nội dung bằng **generation chỉ định** và lưu output riêng; lưu ý generation cũ có thể không còn khả dụng nếu không giữ versioning/soft delete thích hợp.
- **Chỉ xử lý live version mới nhất:** đọc metadata object hiện tại và kiểm tra nó còn là version mong muốn trước khi commit; thiết kế để tránh overwrite kết quả của event mới hơn.
- **Cần transaction và thứ tự nghiệp vụ:** dùng database/event store phù hợp; Eventarc một mình không đảm bảo ordered processing.

## 10. Retry, xác nhận thành công và lỗi vĩnh viễn

Với Eventarc Standard, retry thường dựa trên Pub/Sub transport. **Không giả định trigger nào cũng tự retry**:

- Trigger tạo bằng **gcloud CLI/Terraform** thông thường bật retry mặc định.
- Trigger tạo từ **Cloud Run Console** có thể mặc định **chỉ một lần giao, không retry** nếu không chọn bật retry.
- Retention, backoff và dead-letter handling được cấu hình trên **Pub/Sub subscription** gắn với trigger theo tính năng hỗ trợ.
- Khi response `2xx` được chấp nhận, hệ thống giao sự kiện coi đã xử lý; nếu xử lý thật còn chạy nền, dữ liệu có thể mất khi instance kết thúc.

| Tình huống | Hành động handler |
| --- | --- |
| Event đã được xử lý (duplicate) | Bỏ qua side effect, trả thành công |
| Lỗi mạng/Cloud SQL tạm thời | Báo lỗi để hệ thống giao sự kiện retry nếu được bật |
| Payload thiếu hoặc không hợp lệ | Log metadata an toàn, đưa vào xử lý lỗi/DLQ theo policy; không retry vô hạn |
| Quyền IAM thiếu | Sửa IAM/identity trước; retry vô hạn không tự sửa quyền |
| Downstream bị quá tải | Backoff/rate limiting, hạn mức instances/concurrency |
| Đã commit nhưng response mất | Dedupe bền vững phát hiện khi giao lại |

**Giới hạn retry:** retry kéo dài có thể phát sinh phí Cloud Run, Eventarc và Pub/Sub; event có thể hết retention rồi mất. Với production, cấu hình **dead-letter topic/queue** khi phù hợp và alert để không bỏ qua events thất bại.

## 11. Security: HTTP caller khác Eventarc trigger

Một lỗi phổ biến là mở function ra `allUsers` chỉ để Eventarc gọi được. Điều này không cần thiết nếu **trigger service account có `roles/run.invoker`** và ingress policy cho phép Eventarc đến service.

~~~mermaid
flowchart TD
    DEP["Deployer"] -->|"Source deployment quyền phù hợp"| RUN["Cloud Run service"]
    EVT["Eventarc trigger SA"] -->|"run.invoker"| RUN
    RUN -->|"Runtime SA quyền app"| STORAGE["Storage / DB / PubSub"]
    SRC["Cloud Storage service agent"] -->|"pubsub.publisher khi cần"| TRANS["Eventarc transport"]
    TRANS --> EVT
~~~

Phân biệt:

- **HTTP function riêng tư:** client phải có IAM Invoker/identity token hợp lệ. Webhook công khai cần thêm kiểm tra chữ ký nguồn và chống replay.
- **Event-driven function:** giữ private; Eventarc trigger identity nhận quyền Invoker riêng.
- **Runtime service account:** có quyền đọc object hoặc ghi kết quả nhưng **không nên dùng làm Eventarc trigger SA** chỉ vì tiện.
- **Event source và transport service agents:** có vai trò kỹ thuật riêng; không trộn với danh tính ứng dụng.
- **IAM policy/VPC Service Controls/ingress restrictions:** có thể chặn event delivery ngay cả khi code Java đúng.

Không log authorization headers, access tokens, object payload chứa PII, thông tin thanh toán hoặc secrets khi debug.

## 12. Event filtering, fan-out và tránh vòng lặp

Eventarc trigger filter theo **event type** và các attributes được nguồn hỗ trợ (ví dụ bucket). Filters không thay thế business validation trong handler.

**Các mẫu cần lưu ý:**

1. Tạo nhiều triggers có filter giống nhau tới các services khác nhau có thể **fan-out**; mỗi destination có thể nhận cùng event.
2. Một function chỉ gắn một trigger theo mô hình “function trigger” cụ thể, nhưng một Cloud Run service có thể được nhiều Eventarc triggers định tuyến tới theo khả năng cấu hình.
3. Nếu handler đọc `incoming/file.txt` rồi ghi `incoming/processed.txt` vào cùng bucket mà trigger lọc mọi finalized event, **đầu ra có thể kích hoạt chính function**, tạo vòng lặp.
4. Nên dùng **bucket đầu ra riêng** hoặc xử lý prefix và metadata trong code; không giả định Eventarc direct event hỗ trợ mọi cách lọc object path.
5. Bản overwrite cũng phát finalized event. Nếu muốn xử lý một lần theo object name, cần quy tắc dedupe/version rõ ràng.

Ví dụ thiết kế an toàn:

~~~text
Input:  gs://commerce-incoming/orders/order-123.json
Trigger: google.cloud.storage.object.v1.finalized (bucket commerce-incoming)
Handler: đọc đúng generation, validate, xử lý idempotent
Output: gs://commerce-processed/orders/order-123.json
~~~

Nếu đích là Pub/Sub, kiểm soát retries, ordering, delivery attempts và lifecycle của subscriptions theo hướng dẫn riêng. Đừng dùng Cloud Run function làm một message broker tự chế.

## 13. Concurrency, timeout và cold start Java

Functions triển khai trực tiếp trên Cloud Run dùng **hạ tầng autoscaling của Cloud Run**, có thể xử lý nhiều requests đồng thời trên một instance theo concurrency cấu hình. Đường Cloud Functions v2 API và 1st gen có giới hạn khác nhau; không mặc định mọi function chỉ xử lý **một event/instance**.

**Với Java:**

- HTTP handler và CloudEvent handler có thể chạy trên nhiều threads hoặc nhiều instances: client objects dùng chung phải thread-safe.
- Connection pool Cloud SQL/HTTP cần limits; `max-instances` giới hạn số instances theo điều kiện, không thay thế rate limiting ở event source.
- Cold start phụ thuộc JVM startup, dependency initialization, CPU/memory, min instances và tải đồng thời.
- Timeout của request khác với tổng thời gian event retention/retry; không tạo thread chạy dài sau khi trả thành công.
- Dùng Cloud Run jobs/Workflows/Cloud Tasks nếu xử lý cần hơn một request ngắn, có tiến trình nhiều bước hoặc deadline riêng.

Một cấu hình mẫu để giới hạn tài nguyên **khi đã sizing bằng load test**:

~~~bash
gcloud run services update orders-storage-events \
  --concurrency=10 \
  --max-instances=5 \
  --timeout=120s \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

Đây là **lệnh thay đổi cấu hình runtime thật**, có thể tạo revision mới hoặc ảnh hưởng khả năng nhận event. Các số 10/5/120 chỉ để minh họa, không phải khuyến nghị mặc định cho mọi Java function. Nếu giới hạn quá thấp và event đến nhanh, backlog/latency có thể tăng.

## 14. Kiểm thử đúng: happy path, failure path và duplicate

### 14.1. HTTP tests

| Trường hợp | Kỳ vọng |
| --- | --- |
| `GET` tới service riêng tư với caller hợp lệ | `200` và JSON của demo |
| `POST` với caller hợp lệ | `405` do handler |
| Không có danh tính Invoker | Bị Cloud Run chặn trước handler |
| JSON body quá lớn hoặc invalid (khi có API thật) | `4xx` phù hợp và không có side effect |

### 14.2. Event tests

| Trường hợp | Kỳ vọng |
| --- | --- |
| Upload file mới vào bucket được filter | Có CloudEvent finalized gửi tới handler |
| Overwrite file cùng tên | Có finalized event với **generation mới** |
| Upload tới bucket khác | Không match trigger bucket filter |
| Giao lại cùng `source + id` | Xử lý idempotent, không nhân đôi output |
| Xử lý tạm lỗi với retry bật | Có redelivery theo backoff/retention |
| Handler ghi output cùng bucket nguồn | Có nguy cơ self-trigger nếu không kiểm soát |
| Trigger thiếu Invoker/Event Receiver | Không giao thành công; xem IAM và delivery logs |

**Thử nghiệm redelivery có chủ đích:** tại môi trường lab, cấu hình handler cố tình thất bại tạm thời cho **một event test riêng**, xem retry và xác nhận khi phục hồi không tạo output trùng. Không tạo failure loop trên nguồn dữ liệu production hoặc khi chưa có cost guardrails.

### 14.3. Dọn tài nguyên lab

Chỉ sau khi xác nhận **không có hệ thống khác đang dùng**:

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

Đây là **lệnh xóa thật**. Kiểm tra separately **bucket/tệp thử, Artifact Registry images, build artifacts, logs, IAM bindings và service accounts** theo quy trình dọn. Tránh xóa chung bucket hoặc identity của ứng dụng khác.

## 15. Quan sát và khắc phục sự cố

### 15.1. Những tín hiệu cần theo dõi

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Cloud Run requests, p95 latency, 4xx/5xx | Handler có lỗi/timeout không |
| Instance count, CPU/memory/concurrency | Autoscaling và tài nguyên phù hợp không |
| Eventarc trigger health/delivery metrics | Events có được định tuyến tới service không |
| Pub/Sub transport backlog/retry/dead-letter | Có event kẹt hoặc retry lâu không |
| Event ID/source, object generation | Có duplicate hoặc out-of-order không |
| Chi phí Cloud Build/Registry/Run/Eventarc/PubSub | Retry/cold start/logs có làm vượt ngân sách không |

Trong Logs Explorer:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-storage-events"
severity>=ERROR
~~~

Hoặc dùng:

~~~bash
gcloud run services logs read orders-storage-events \
  --region=asia-southeast1 --project=PROJECT_ID --limit=50

gcloud eventarc triggers describe orders-file-finalized \
  --location=asia-southeast1 --project=PROJECT_ID
~~~

**Đừng chỉ nhìn log của function.** Nếu Eventarc chưa giao được request vì IAM hoặc trigger filter sai, handler **không có log**; phải xem trigger status, service agent permissions và vận chuyển Pub/Sub.

### 15.2. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra |
| --- | --- |
| Build Java lỗi `Class not found` | `--function` không đúng package/class, Maven compiler/plugin |
| Deploy trả `403` | Source deploy roles, build SA, Artifact Registry permissions, actAs |
| HTTP `401/403` | Service private, caller thiếu Invoker, identity token/audience không hợp lệ |
| Upload GCS không kích hoạt | Chưa có trigger, location/filter sai hoặc trigger chưa active |
| Eventarc `PERMISSION_DENIED` | Trigger SA thiếu Receiver/Invoker, service agents thiếu quyền |
| Function có log duplicate | At-least-once redelivery hoặc nhiều events cho nhiều generations |
| Xử lý event lặp vô hạn | Function ghi output trùng bucket nguồn |
| Không có event thứ hai | Trigger filter không match, quota, IAM hoặc nguồn chưa tạo event |
| Latency cao khi burst | Cold starts, max instances thấp, slow downstream hoặc retry backlog |
| HTTP 500 và retried nhiều lần | Handler throw, dependency lỗi, retry policy đang bật |
| Event xử lý sai phiên bản file | Đọc object theo name sau overwrite thay vì pin generation |
| Cost tăng dù traffic thấp | Retry loop, min instances, logs hoặc build/Artifact Registry storage |

## 16. Chi phí và độ tin cậy

Không có “function miễn phí” cho mọi lưu lượng. Những khoản cần xem: **Cloud Build và Artifact Registry** khi deploy source, **Cloud Run** compute/requests, **Eventarc và Pub/Sub transport**, Cloud Storage operations, network egress, Logging/Monitoring và các dependencies như Cloud SQL.

**Lựa chọn thực tế:**

- HTTP webhook ít request → ưu tiên private endpoint hoặc xác minh chữ ký nếu public; kiểm tra cold-start có chấp nhận được không.
- Event volume lớn và không được mất dữ liệu → bật retry/idempotency, metrics backlog, dead-letter khi phù hợp; dự báo chi phí cho retries.
- ETL nhiều bước/chạy lâu → cân nhắc Cloud Run jobs hoặc Workflows thay vì request handler dài.
- Mục tiêu RTO/RPO cao → thêm backup, replay strategy, data versioning và kiểm thử disaster recovery; Eventarc không tự lưu dữ liệu nghiệp vụ vô hạn.

## 17. Tình huống tổng hợp: xử lý tệp đơn hàng

Công ty Commerce có hai thành phần:

1. Đối tác gọi webhook `POST /orders/confirm` → HTTP function xác minh signature, event ID và gọi backend để cập nhật trạng thái.
2. Bộ phận vận hành upload `incoming/orders-2026-11.json` vào Cloud Storage → Eventarc `finalized` gọi CloudEvents function để validate tệp và ghi kết quả ra **bucket khác**.

Thiết kế gợi ý:

~~~mermaid
flowchart LR
    PARTNER["Đối tác"] -->|"HTTPS webhook"| HTTP["HTTP function<br/>signature + validation"]
    HTTP --> DB[("Cloud SQL<br/>idempotency + order state")]
    INPUT["Input bucket"] -->|"finalized event"| ARC["Eventarc"]
    ARC --> CE["CloudEvents function<br/>generation + dedupe"]
    CE --> DB
    CE --> OUTPUT["Output bucket"]
    DB --> OBS["Cloud Monitoring / Logging"]
    CE --> OBS
    HTTP --> OBS
~~~

**Ràng buộc sản xuất:** HTTP webhook cần xác minh danh tính đối tác; CloudEvent có thể được giao lại hoặc không theo thứ tự; cả hai phải **idempotent** và không được thực hiện thanh toán/email hai lần. Source và output buckets khác nhau tránh tự kích hoạt lặp. Mọi quyền truy cập database/storage nằm ở **runtime service accounts** có phạm vi tối thiểu.

## 18. Bài tập tự kiểm tra

**Câu 1.** Cloud Run event-driven function có chạy “không qua HTTP” không?

*Đáp án:* Không. Eventarc gửi CloudEvent bằng HTTP tới Cloud Run service; Functions Framework xử lý payload theo CloudEvents signature.

**Câu 2.** Khi viết Java, HTTP và CloudEvents dùng cùng interface?

*Đáp án:* Không. `HttpFunction.service` khác `CloudEventsFunction.accept`.

**Câu 3.** Deploy `functions.StorageFinalized` bằng `gcloud run deploy` nhưng không có trigger. Upload lên GCS có gọi function không?

*Đáp án:* Không tự động; cần tạo Eventarc trigger với filter/source/destination.

**Câu 4.** Chỉ chọn event type `google.cloud.storage.object.v1.finalized` thì overwrite có tạo event không?

*Đáp án:* Có. Overwrite tạo generation mới nên có finalized event mới.

**Câu 5.** Event được giao hai lần và handler gửi hai email. Vấn đề và cách xử lý?

*Đáp án:* Thiếu idempotency. Dùng `source+id` hoặc business key và lưu dedupe bền vững trước side effect.

**Câu 6.** Tại sao không nên lấy `generation` như đồng hồ thứ tự sự kiện toàn hệ thống?

*Đáp án:* Không có ordered delivery; generation chỉ định danh phiên bản object, không thay logic thứ tự nghiệp vụ đa object.

**Câu 7.** Eventarc trigger đã được tạo nhưng service private trả `403`. Cần kiểm tra gì?

*Đáp án:* Trigger SA có `roles/run.invoker`, Event Receiver, source service agent và ingress/IAM.

**Câu 8.** Trigger tạo bằng Cloud Run Console luôn retry tự động như CLI?

*Đáp án:* Không. Default retry có thể khác theo giao diện/cách tạo; cần kiểm tra policy thực tế.

**Câu 9.** Vì sao không nên xử lý ở thread nền rồi trả HTTP 200 ngay?

*Đáp án:* Hệ thống coi event đã xác nhận dù xử lý nền có thể bị dừng/mất dữ liệu.

**Câu 10.** Một function ghi output vào chính bucket có trigger `finalized` sẽ có nguy cơ gì?

*Đáp án:* Output phát sinh event tiếp theo, có thể tạo vòng lặp/chi phí nếu không lọc.

**Câu 11.** CloudEvents handler dùng runtime SA có quyền đọc bucket. Eventarc trigger SA tự có quyền đọc bucket không?

*Đáp án:* Không. Hai danh tính khác mục đích; trigger SA cần giao event, runtime SA cần quyền nghiệp vụ.

**Câu 12.** HTTP webhook và CloudEvent cùng cần điều gì khi có retries?

*Đáp án:* Idempotency, business validation, giới hạn attempts và logging/metrics đủ để reconcile.

## 19. Checklist production

- [ ] Chọn đúng **HTTP** hay **CloudEvents** theo nguồn và kiểu trả kết quả.
- [ ] Entry point Java, Functions Framework và Maven dependencies đúng.
- [ ] Dùng Cloud Run Admin API/`gcloud run` cho function mới; phân biệt với Cloud Functions v2 API.
- [ ] Trigger Eventarc có **type, source filter và location** đúng; xác minh healthy.
- [ ] IAM của deployer, build, runtime, trigger và service agents tách rõ.
- [ ] Private service được gọi bằng Invoker identity; public webhook có signature/replay validation.
- [ ] Handler xử lý duplicates và out-of-order bằng dedupe store bền vững.
- [ ] Không phụ thuộc in-memory cache/local disk cho trạng thái business.
- [ ] Không có self-trigger khi ghi kết quả lên Cloud Storage.
- [ ] Retry/retention/dead-letter được thiết kế và kiểm thử; phân biệt lỗi tạm/vĩnh viễn.
- [ ] Timeout, concurrency, max instances và downstream limits được sizing.
- [ ] Logs/metrics theo service, trigger, backlog và business outcome; không lộ secrets.
- [ ] CI tests, image/build metadata, IAM review và rollback có owner.
- [ ] Có budget, cost alert và cleanup an toàn cho lab/resources.

## 20. Kết luận

**HTTP functions nhận request do client chủ động gửi; event-driven functions nhận CloudEvents do Eventarc định tuyến.** Cả hai dùng Cloud Run infrastructure và Functions Framework, nhưng khác ở authentication, input contract, retry và idempotency. Với production, không chỉ “deploy chạy được”: cần chứng minh **đúng identity gọi được, sự kiện được lọc đúng, lỗi có thể phục hồi, duplicate không làm nhân đôi tác vụ, và chi phí được kiểm soát**.

## Tài liệu tham khảo chính thức

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

