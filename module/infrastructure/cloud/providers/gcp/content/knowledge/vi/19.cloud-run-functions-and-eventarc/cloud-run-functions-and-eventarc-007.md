# Xác thực, service identity và quyền của event trigger

> **Chương:** Cloud Run functions và Eventarc  
> **Bài học:** Xác thực, service identity và quyền của event trigger  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Với **Cloud Run functions** và **Eventarc**, một yêu cầu bảo mật cốt lõi là xác định **ai được tạo trigger, trigger dùng danh tính nào để gọi function và function dùng quyền gì sau khi chạy**.

Ví dụ: một object mới được upload lên Cloud Storage sẽ phát sự kiện `google.cloud.storage.object.v1.finalized`. Eventarc chuyển sự kiện đến function Java `invoice-event-handler`. Để luồng này hoạt động an toàn, phải kết hợp **quyền nhận sự kiện**, **quyền gọi Cloud Run**, **danh tính runtime của function**, **quyền của Google service agents** và **quyền người triển khai**. Thiếu một mắt xích có thể khiến trigger hiển thị trạng thái active nhưng function không nhận được sự kiện.

Bài sử dụng **Eventarc Standard** và Cloud Run functions triển khai theo mô hình Cloud Run hiện hành (tương đương Cloud Functions thế hệ 2 về nền tảng). Các tên project, bucket và tài khoản trong ví dụ chỉ là placeholder; thao tác IAM, triển khai function và tạo trigger có thể tạo chi phí và thay đổi quyền thật. Chỉ chạy trong project sandbox được phê duyệt. Nội dung ưu tiên **một mô hình IAM rõ ràng, ví dụ đầy đủ và cách chẩn đoán có thể áp dụng lại**.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **người triển khai**, **Eventarc trigger service account**, **Cloud Run function runtime service account** và **Google-managed service agents**.
2. Giải thích **authentication** (xác thực danh tính) và **authorization** (cấp quyền) trong luồng Eventarc → Cloud Run.
3. Cấp đúng `roles/eventarc.eventReceiver` và `roles/run.invoker` cho trigger, hiểu ngoại lệ của sự kiện **Pub/Sub trực tiếp**.
4. Giải thích vì sao Google Cloud Storage service agent có thể cần `roles/pubsub.publisher` khi phát sự kiện trực tiếp đến Eventarc.
5. Triển khai một Java CloudEvents function, thiết lập runtime identity và tạo Eventarc trigger riêng.
6. Dùng `gcloud` để kiểm tra trigger, service IAM, project IAM, logs và lỗi 401/403.
7. Nhận diện sai lầm giữa **service account key**, **ID token**, **access token**, **runtime ADC** và **event payload**.
8. Thiết kế least privilege, phân tách nhiệm vụ, chống lặp sự kiện, giám sát và chi phí.

## 2. Luồng sự kiện và bốn lớp danh tính

~~~mermaid
flowchart LR
    Dev["Người triển khai / CI"] -->|"Deploy và tạo trigger"| Ctrl["Cloud Run + Eventarc control plane"]
    Bucket["Cloud Storage bucket"] -->|"Object finalized"| StorageAgent["Cloud Storage service agent"]
    StorageAgent -->|"Publisher quyền nguồn"| Transport["Eventarc / Pub/Sub transport"]
    Transport -->|"Trigger identity + ID token"| Run["Cloud Run function<br/>private target"]
    TriggerSA["Trigger service account"] -. "Event Receiver + Run Invoker" .-> Transport
    TriggerSA -. "Xác thực khi gọi" .-> Run
    Run -->|"Runtime identity / ADC"| API["Cloud Storage, Pub/Sub, Secret Manager"]
    RuntimeSA["Function runtime service account"] -. "Quyền API tối thiểu" .-> API
~~~

**Bốn lớp cần tách biệt:**

| Danh tính | Đại diện cho ai? | Quyền điển hình |
|---|---|---|
| **Deployer / CI principal** | Người hoặc pipeline tạo function và trigger | Quyền deploy, tạo trigger và `iam.serviceAccounts.actAs` với account được gắn |
| **Trigger service account** (user-managed) | Danh tính mà Eventarc dùng khi chuyển sự kiện tới destination | `roles/eventarc.eventReceiver` khi cần; `roles/run.invoker` trên đúng Cloud Run target |
| **Function runtime service account** | Danh tính mà mã Java dùng khi gọi Google Cloud APIs | `roles/storage.objectViewer` trên bucket hoặc quyền API cụ thể nếu chức năng cần |
| **Google service agents** | Danh tính do Google quản lý để vận hành Eventarc/Cloud Storage/Pub/Sub/Cloud Run | Các service-agent roles và `pubsub.publisher`/`serviceAccountTokenCreator` theo loại nguồn |

**Không dùng một service account duy nhất cho cả deployer, trigger và runtime** chỉ để tiện cấu hình. Trigger chỉ cần **gọi function**; nó không cần đọc mọi object hay truy cập Secret Manager. Runtime của function chỉ cần **thực thi nghiệp vụ**, không cần tạo Eventarc triggers.

## 3. Xác thực, phân quyền và danh tính trong Cloud Run

### 3.1. Authentication khác authorization

- **Authentication:** yêu cầu mang thông tin xác thực hợp lệ, xác định principal đang gọi service.
- **Authorization:** principal được phép thực hiện hành động cụ thể trên tài nguyên đó hay không.
- **Cloud Run Invoker:** `roles/run.invoker` chứa quyền `run.routes.invoke` để gọi một Cloud Run service/function được bảo vệ.
- **Ingress policy:** giới hạn đường mạng được phép nhận request; khác với IAM Invoker.
- **Application authorization:** sau khi request đến Java handler, ứng dụng có thể cần xác thực và phân quyền bổ sung đối với nội dung nghiệp vụ.

Một function **private** không được gọi chỉ vì caller ở cùng VPC. Ngược lại, có `roles/run.invoker` không đảm bảo event đi qua được nếu nguồn event, đường vận chuyển, network policy hoặc trigger filters sai.

### 3.2. Eventarc dùng danh tính trigger để gọi authenticated function

Một Eventarc trigger gắn với **một service account**. Khi chuyển sự kiện tới Cloud Run function có yêu cầu xác thực, Eventarc dùng danh tính này theo cơ chế dịch vụ để tạo yêu cầu có **Google-signed ID token** phù hợp. Cloud Run kiểm tra xác thực và IAM **trước khi handler Java xử lý CloudEvent**.

~~~text
Cloud Storage phát event
  → Eventarc lọc event theo trigger
  → Eventarc gửi HTTP CloudEvent tới Cloud Run
  → Cloud Run xác thực danh tính trigger
  → IAM kiểm tra roles/run.invoker ở destination
  → Java CloudEventsFunction.accept(event)
~~~

**Sai lầm phổ biến:** trigger `ACTIVE` không chứng minh destination nhận được request. Nếu quên cấp `roles/run.invoker`, trigger có thể đã tạo thành công nhưng deliveries nhận lỗi authentication/authorization.

### 3.3. Runtime service identity là lớp thứ hai

Sau khi function chạy, mã Java có thể cần lấy nội dung object, ghi Pub/Sub, gọi Firestore hoặc đọc Secret Manager. Khi dùng **Google Cloud Client Libraries**, function thường lấy quyền qua **Application Default Credentials (ADC)** của **runtime service account đã được gắn vào Cloud Run revision**.

- **ID token**: thích hợp cho invocation của một Cloud Run target cần xác thực, với `aud` đúng.
- **OAuth 2.0 access token**: thường dùng để gọi Google APIs theo quyền IAM của service identity.
- **Service account JSON key**: private credential dài hạn, không nên nhúng vào container/source, thường không cần dùng trong Cloud Run.
- **CloudEvent payload**: dữ liệu nghiệp vụ như bucket/object name, **không phải credential** và không phải bằng chứng caller có quyền.

Không đặt `GOOGLE_APPLICATION_CREDENTIALS` trỏ tới JSON key trên Cloud Run chỉ để “cho SDK nhận account”; hãy cấu hình runtime service identity bằng `--service-account` và cấp IAM tối thiểu.

## 4. Các vai trò IAM và nơi cấp

| Principal nhận quyền | Role / permission | Scope hợp lý | Khi nào cần? |
|---|---|---|---|
| Người tạo trigger | `roles/eventarc.admin` hoặc custom role phù hợp | Project quản lý Eventarc | Tạo/sửa/xóa trigger |
| Người gắn service account | `roles/iam.serviceAccountUser` (quyền `iam.serviceAccounts.actAs`) | **Trên đúng service account** | Khi chỉ định trigger/runtime/build identity |
| Người deploy bằng Cloud Run source | `roles/run.sourceDeveloper` và `roles/serviceusage.serviceUsageConsumer`, cộng quyền build cần thiết | Project deploy | Tạo/cập nhật function từ source |
| Người deploy bằng Cloud Functions v2 API | `roles/cloudfunctions.developer` hoặc quyền tương ứng | Project deploy | Chỉ khi dùng `gcloud functions` / Functions v2 API |
| **Trigger SA** | `roles/eventarc.eventReceiver` | Project nguồn/trigger theo mô hình | Sự kiện từ provider hỗ trợ; **không cần cho Pub/Sub direct events** |
| **Trigger SA** | `roles/run.invoker` | **Cloud Run service đích** | Gọi function yêu cầu xác thực |
| **Runtime SA** | Ví dụ `roles/storage.objectViewer` | Bucket nguồn cần đọc | **Chỉ khi Java thực sự tải object data** |
| **Cloud Storage service agent** | `roles/pubsub.publisher` | Event source project theo hướng dẫn | Direct Cloud Storage events qua Eventarc |
| **Eventarc service agent** | `roles/eventarc.serviceAgent` | Project | Google quản lý transport/validation; thường tự cấp |
| **Pub/Sub service agent** (một số project cũ) | `roles/iam.serviceAccountTokenCreator` | Project/service account theo hướng dẫn | Khi project bật Pub/Sub service agent **trước 08/04/2021** |
| **Cloud Functions service agent** | `roles/cloudfunctions.serviceAgent` | Project | Khi triển khai bằng Cloud Functions v2 API |

**Quan trọng:** Role `roles/eventarc.serviceAgent` dành cho **Google-managed Eventarc service agent**, không dành cho trigger SA hay developer. Tương tự, việc cấp `roles/run.invoker` cho runtime SA của function **không sửa được** lỗi trigger không gọi được destination, vì **principal đang gọi chính là trigger SA**.

### 4.1. Ngoại lệ Pub/Sub trực tiếp

Khi Eventarc nhận **direct events từ Cloud Pub/Sub**, tài liệu không yêu cầu gán `roles/eventarc.eventReceiver` cho trigger SA; trigger vẫn cần quyền **invoke destination** nếu target private. Các permission để publisher gửi message lên Pub/Sub topic là **một vấn đề khác**, không tự động xuất hiện chỉ vì trigger có quyền Invoker.

### 4.2. Default Compute Engine service account không phải lựa chọn production

Nếu không chỉ định danh tính khi tạo trigger, Eventarc có thể dùng **Compute Engine default service account** `PROJECT_NUMBER-compute@developer.gserviceaccount.com`. Các project cũ có thể đã tự cấp role Editor cho account mặc định, trong khi tổ chức mới thường chặn auto-grant này bằng Organization Policy.

**Đừng dựa vào quyền mặc định.** Hãy tạo một **user-managed trigger SA** và cấp duy nhất các role cần dùng; runtime function cũng dùng user-managed SA tách biệt.

## 5. Chuẩn bị lab Eventarc → Java Cloud Run function

**Mô hình:** bucket `gs://BUCKET_NAME` ở `asia-southeast1` phát sự kiện object finalized; Eventarc trigger `invoice-finalized` gọi function Java `invoice-event-handler` trong cùng region. Mã mẫu chỉ ghi metadata sự kiện ra log, **không tải nội dung object**, vì vậy runtime không cần Storage Object Viewer.

| Thành phần | Giá trị ví dụ |
|---|---|
| Project | `PROJECT_ID` |
| Project number | `PROJECT_NUMBER` |
| Region | `asia-southeast1` |
| Source bucket | `BUCKET_NAME` đã tạo sẵn trong project/location tương thích |
| Function | `invoice-event-handler` |
| Trigger | `invoice-finalized` |
| Trigger SA | `evt-invoice@PROJECT_ID.iam.gserviceaccount.com` |
| Runtime SA | `fn-invoice@PROJECT_ID.iam.gserviceaccount.com` |
| Event type | `google.cloud.storage.object.v1.finalized` |

Điều kiện:

- Cloud Run, Eventarc, Eventarc Publishing, Cloud Build, Artifact Registry, Cloud Storage và API liên quan đã được bật/cho phép theo quy trình.
- Bucket trực tiếp cho Cloud Storage events nằm ở **project và region/multi-region tương thích** với trigger, theo yêu cầu Eventarc Standard.
- Người triển khai có quyền tạo function/trigger và `iam.serviceAccounts.actAs` trên accounts tương ứng.
- Build service account và Cloud Run service agent có các quyền triển khai và truy cập Artifact Registry phù hợp.
- IAM có thể cần thời gian để đồng bộ; kiểm tra lại sau khi cấp role.
- Không dùng bucket production chứa dữ liệu người dùng để làm thử event.

### 5.1. Các lệnh kiểm tra trước khi thay đổi

~~~bash
gcloud auth list
gcloud config get-value project
gcloud projects describe PROJECT_ID --format="value(projectNumber)"

gcloud services list --enabled \
  --project=PROJECT_ID \
  --filter="NAME:eventarc.googleapis.com OR NAME:run.googleapis.com"

gcloud storage buckets describe gs://BUCKET_NAME

gcloud eventarc triggers list \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

Đọc location của bucket thật, không suy từ tên. Trong bài này, tất cả lệnh ghi tài nguyên đều chứa `--project=PROJECT_ID` khi công cụ hỗ trợ.

## 6. Bước 1 — Tạo hai service accounts khác trách nhiệm

**Các lệnh phần 6–9 thay đổi IAM, function và trigger thật**, chỉ chạy khi được cấp quyền trên project sandbox.

~~~bash
# Danh tính Eventarc dùng để gọi function.
gcloud iam service-accounts create evt-invoice \
  --project=PROJECT_ID \
  --display-name="Eventarc invoice trigger identity"

# Danh tính Java function dùng khi chạy.
gcloud iam service-accounts create fn-invoice \
  --project=PROJECT_ID \
  --display-name="Invoice function runtime identity"
~~~

Sau đó xác minh:

~~~bash
gcloud iam service-accounts describe \
  evt-invoice@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID

gcloud iam service-accounts describe \
  fn-invoice@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID
~~~

**Không cấp `roles/editor` hoặc `roles/owner` cho cả hai tài khoản.** Trigger SA không cần Storage Object Viewer cho function này. Runtime SA chưa cần quyền Storage vì code chỉ đọc metadata đã nằm trong CloudEvent.

## 7. Bước 2 — Cấp đúng quyền trigger và nguồn Cloud Storage

### 7.1. Eventarc Event Receiver cho trigger SA

Với **Cloud Storage direct events**, cấp:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:evt-invoice@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/eventarc.eventReceiver"
~~~

Role này được cấp **trên project** theo tài liệu Eventarc. Nó **không** cho phép Java runtime đọc object hoặc tạo trigger mới.

### 7.2. Cloud Storage service agent cần Pub/Sub Publisher

Eventarc Standard dùng **Pub/Sub làm transport** cho nhiều nguồn. Với direct Cloud Storage events, **Cloud Storage service agent của project chứa bucket** cần quyền publish phục vụ vận chuyển event.

Lấy email service agent (lệnh có thể **khởi tạo agent** nếu chưa tồn tại):

~~~bash
gcloud storage service-agent --project=PROJECT_ID
~~~

Thay `STORAGE_AGENT_EMAIL` bằng email trả về, sau đó cấp:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:STORAGE_AGENT_EMAIL" \
  --role="roles/pubsub.publisher"
~~~

Đây là service agent của **Cloud Storage**, không phải `evt-invoice@...` và không phải `fn-invoice@...`. Đừng cấp Pub/Sub Publisher cho mọi service accounts chỉ để thử một trigger.

### 7.3. Các service agents còn lại

- **Eventarc service agent:** thường có `roles/eventarc.serviceAgent` tự động khi Eventarc tạo tài nguyên đầu tiên. Nếu bị thu hồi, khôi phục role trên đúng principal `service-PROJECT_NUMBER@gcp-sa-eventarc.iam.gserviceaccount.com` theo người quản trị IAM.
- **Pub/Sub service agent:** nếu được enable **trước ngày 08/04/2021**, đôi khi cần `roles/iam.serviceAccountTokenCreator` cho luồng authenticated push. Không cấp role này rộng rãi theo thói quen ở mọi project mới.
- **Cloud Functions service agent:** khi triển khai bằng `gcloud functions` hoặc Functions v2 API có `roles/cloudfunctions.serviceAgent`. Với `gcloud run deploy` hiện đại, cần xem bộ quyền Cloud Run source deploy và build tương ứng.

**Phân biệt:** Google service agents được Google tạo/quản lý, còn `evt-invoice` là user-managed SA do bạn tạo. Một số agent chỉ xuất hiện sau khi API được bật và sử dụng lần đầu.

## 8. Bước 3 — Viết Java CloudEvents function tối giản

Dự án giả định:

~~~text
invoice-event-handler/
├── pom.xml
└── src/main/java/functions/InvoiceEventHandler.java
~~~

### 8.1. Mã Java không nhận dữ liệu nhạy cảm từ caller

~~~java
package functions;

import com.google.cloud.functions.CloudEventsFunction;
import io.cloudevents.CloudEvent;
import java.util.logging.Logger;

public final class InvoiceEventHandler implements CloudEventsFunction {
    private static final Logger log =
            Logger.getLogger(InvoiceEventHandler.class.getName());

    @Override
    public void accept(CloudEvent event) {
        if (event == null || event.getId() == null
                || event.getType() == null || event.getSource() == null) {
            throw new IllegalArgumentException("Missing CloudEvent metadata");
        }

        String eventId = event.getId();
        String eventType = event.getType();
        String source = event.getSource().toString();

        // Demo: log metadata, không log toàn bộ payload hoặc secret.
        log.info(() -> "eventId=" + eventId
                + " type=" + eventType + " source=" + source);
    }
}
~~~

Mẫu dùng **Functions Framework for Java** và CloudEvents. Handler chỉ đọc **CloudEvent metadata**, không tự chứng minh event payload là “mã lệnh đáng tin”. Khi ứng dụng thật đọc object bằng bucket/name từ event, phải kiểm tra allowlist bucket, loại sự kiện, object generation và idempotency; không cho event tùy ý làm ứng dụng đọc tài nguyên ngoài phạm vi.

### 8.2. Maven POM cho Java 21

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>invoice-event-handler</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.google.cloud.functions</groupId>
      <artifactId>functions-framework-api</artifactId>
      <version>1.0.4</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

`1.0.4` là phiên bản Functions Framework API trong ví dụ tài liệu; cần đối chiếu version hiện hành và dependency compatibility khi áp dụng thật. Mã chỉ có hiệu lực khi `--function` trỏ đúng lớp `functions.InvoiceEventHandler`. Build thử trước:

~~~bash
mvn -version
mvn clean package
~~~

Không cần JSON service account key trong POM. Nếu doanh nghiệp dùng Artifact Registry Maven repository cho dependencies, Maven còn cần **Reader IAM** và credential helper phù hợp ở môi trường build.

## 9. Bước 4 — Deploy function private và cấp Invoker

### 9.1. Chọn runtime service identity tại deploy

Trong thư mục dự án Java, thực hiện (lệnh **thay đổi tài nguyên**):

~~~bash
gcloud run deploy invoice-event-handler \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --source=. \
  --function=functions.InvoiceEventHandler \
  --base-image=java21 \
  --service-account=fn-invoice@PROJECT_ID.iam.gserviceaccount.com
~~~

Đây là cú pháp **Cloud Run functions** triển khai trực tiếp từ source theo hướng dẫn hiện hành. Không thêm `--allow-unauthenticated`; tạo function **private**. Nếu chạy qua `gcloud functions deploy` / Functions v2 API, dùng tập flags/quyền khác; không trộn các ví dụ.

**Người deploy** cần quyền `iam.serviceAccounts.actAs` trên runtime SA và quyền build/deploy phù hợp. Service account `fn-invoice` chỉ cần quyền nghiệp vụ thực sự sử dụng. Quyền deploy **không tự đồng nghĩa** quyền gọi function khi chạy.

### 9.2. Cấp `roles/run.invoker` trên đúng Cloud Run service

~~~bash
gcloud run services add-iam-policy-binding invoice-event-handler \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --member="serviceAccount:evt-invoice@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

**Đây là bước bắt buộc trong mẫu private destination.** Cấp quyền trên **Cloud Run service bên dưới function**, không cấp `roles/cloudfunctions.invoker` theo mô hình Cloud Functions thế hệ 1. Dùng project-wide Invoker chỉ khi yêu cầu và rủi ro được phê duyệt; scope service giúp tránh một trigger gọi được các function khác.

Xác minh:

~~~bash
gcloud run services get-iam-policy invoice-event-handler \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud run services describe invoice-event-handler \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Đọc runtime service account, ingress, URI của Cloud Run target và IAM binding cho `evt-invoice`. Không chỉ xem function đã `Ready` rồi suy trigger có quyền gọi.

### 9.3. Một lỗi dễ mắc

Nếu bạn cấp `roles/run.invoker` cho `fn-invoice@...` (runtime SA) thay vì `evt-invoice@...` (trigger SA), sự kiện vẫn có thể bị chặn ngay ở Cloud Run authentication. **Runtime SA không phải caller của Eventarc delivery**.

## 10. Bước 5 — Tạo Eventarc trigger với identity riêng

~~~bash
gcloud eventarc triggers create invoice-finalized \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --destination-run-service=invoice-event-handler \
  --destination-run-region=asia-southeast1 \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=BUCKET_NAME" \
  --service-account=evt-invoice@PROJECT_ID.iam.gserviceaccount.com
~~~

**Điều kiện của ví dụ:**

- `BUCKET_NAME` chỉ là tên bucket **không có `gs://`** trong event filter.
- Bucket nguồn ở location tương thích với Eventarc trigger; Cloud Storage direct events có ràng buộc project/location.
- `evt-invoice` có Event Receiver cho provider GCS và Invoker trên function.
- Cloud Storage service agent có Publisher, Eventarc agent còn quyền vận hành.
- Chưa có trigger trùng tên ở cùng project/location.

Kiểm tra:

~~~bash
gcloud eventarc triggers describe invoice-finalized \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud eventarc triggers list \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

Chú ý `serviceAccount`, `eventFilters`, destination, transport và trạng thái/conditions. Trigger tạo thành công có thể cần **thời gian propagation** để hoạt động; kiểm tra logs/metrics nếu chưa có event, không thay IAM liên tục.

## 11. Bước 6 — Tạo event và kiểm tra kết quả

**Thao tác dưới đây upload object thử lên Cloud Storage và có thể phát sinh phí:**

~~~bash
printf "invoice event lab\n" > invoice-test.txt

gcloud storage cp invoice-test.txt \
  gs://BUCKET_NAME/lab/invoice-test.txt
~~~

Theo dõi log function:

~~~bash
gcloud run services logs read invoice-event-handler \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --limit=100
~~~

Kỳ vọng thấy metadata tương tự:

~~~text
eventId=... type=google.cloud.storage.object.v1.finalized
source=//storage.googleapis.com/projects/_/buckets/...
~~~

Nếu function nhận nhiều event, không xem đó là lỗi chắc chắn của IAM. Eventarc/Pub/Sub thường có semantics **at-least-once** và retry tùy cơ chế/cấu hình; handler phải có **idempotency**. Với event Cloud Storage, dùng `event.source + event.id` hoặc kết hợp bucket/object/generation để xác định công việc đã xử lý. Không dùng object name đơn lẻ nếu cùng tên có nhiều generations.

### 11.1. HTTP function invocation không phải Pub/Sub publish

- Khi **Eventarc** gọi private Cloud Run function, cần `roles/run.invoker` của **trigger SA**.
- Khi **người dùng muốn gọi HTTP trực tiếp**, người gọi đó cũng cần auth/Invoker phù hợp và một **ID token có audience đúng**. Có thể kiểm tra bằng công cụ `gcloud run services proxy` hoặc luồng được hướng dẫn riêng.
- Khi **mã Java function** tự gọi Google Cloud API, nó dùng **runtime SA + ADC**.

Đừng mở `allUsers` Invoker chỉ để kiểm thử khi trigger còn bị 403; cần xác định principal sai hoặc IAM chưa đúng.

## 12. Event source, trigger và runtime: chọn quyền theo tình huống

| Tình huống | Trigger SA | Source service agent | Runtime SA |
|---|---|---|---|
| **Cloud Storage finalized → private function** | Event Receiver + Run Invoker | Storage SA cần Pub/Sub Publisher | Chỉ cần Storage Object Viewer nếu code tải object |
| **Pub/Sub direct event → private function** | Run Invoker; Event Receiver **không bắt buộc** cho nguồn này | Publisher cần quyền publish lên Pub/Sub topic | Chỉ quyền nghiệp vụ, không cần Pub/Sub Subscriber nếu event đã được giao qua handler |
| **Cloud Audit Logs event → private function** | Event Receiver + Run Invoker | Eventarc agents/đường vận chuyển theo provider | Chỉ quyền nghiệp vụ |
| **Function A gọi HTTP function B** | Không cần Eventarc nếu gọi trực tiếp | Không áp dụng | Runtime SA của A phải có Run Invoker trên B và gửi ID token hợp lệ |
| **HTTP webhook công khai** | Không có Eventarc trigger | Không áp dụng | Runtime SA vẫn tối thiểu; auth/signature và app-level authorization cần thiết |

**Chỉ role cần thiết mới được cấp.** Nếu consumer Java chỉ log CloudEvent metadata như lab, không cấp `roles/storage.admin` hoặc `roles/pubsub.admin`. Nếu handler cần đọc nội dung object, cấp `roles/storage.objectViewer` trên **đúng bucket**, không trên toàn tổ chức.

## 13. Sai cấu hình thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Bước xác minh |
|---|---|---|
| Trigger `ACTIVE` nhưng function không nhận event; HTTP 403 | Thiếu `roles/run.invoker` cho **trigger SA** | `gcloud run services get-iam-policy` |
| Tạo trigger bị permission denied | Deployer thiếu quyền Eventarc/`iam.serviceAccounts.actAs` | IAM của principal tạo trigger và service account |
| Tạo trigger lỗi Eventarc service agent | Agent mới chưa sẵn sàng hoặc mất `roles/eventarc.serviceAgent` | Kiểm tra project number, Eventarc agent và policy |
| GCS direct event không xuất hiện | Cloud Storage service agent thiếu `roles/pubsub.publisher`; bucket/filters sai | Storage service agent, project IAM, trigger filters |
| Chỉ Pub/Sub direct event, vẫn bị lỗi invoke | Chưa cấp Invoker, không phải Event Receiver | Trigger SA IAM trên target |
| Function bị 403 khi đọc object | Runtime SA thiếu Storage Viewer hoặc object IAM/chính sách | Logs ứng dụng, bucket IAM, runtime identity |
| Console Test HTTP trả 403 | Caller không có ID token/Run Invoker | Phân biệt user test và Eventarc caller |
| Event đã nhận nhưng Java lỗi 500 | Code, dependency, Secret, API quota hoặc input | Cloud Run request/application logs |
| Có event trùng | Delivery at-least-once hoặc retries | Deduplication theo event ID/source/generation |
| Lỗi khi deploy source | Build SA thiếu Artifact Registry, Cloud Build hoặc quyền `actAs` | Build logs + deployer/build SA IAM |
| `404` hoặc sai destination | Trigger nhắm sai service/region/path | `eventarc triggers describe` và `run services describe` |
| Trigger tạo nhưng chậm có event | IAM propagation, trigger initialization hoặc source delay | Eventarc/Cloud Run metrics, kiểm tra theo thời điểm |
| Cross-project service account bị từ chối | Thiếu cấu hình cross-project identity/org policy | Tài liệu cross-project SA, IAM và audit |

### 13.1. Luồng xử lý lỗi 403 theo lớp

~~~mermaid
flowchart TD
    Start["Không nhận CloudEvent"] --> Source{"Có event nguồn đúng filter?"}
    Source -->|"Không"| S["Kiểm tra bucket/topic, event type, region"]
    Source -->|"Có"| Agent{"Service agents và Event Receiver hợp lệ?"}
    Agent -->|"Không"| A["GCS Publisher + Eventarc SA + trigger Receiver"]
    Agent -->|"Có"| Invoke{"Cloud Run logs có 401/403?"}
    Invoke -->|"Có"| I["Kiểm tra đúng trigger SA + roles/run.invoker"]
    Invoke -->|"Không"| Code{"Handler log 5xx/timeout?"}
    Code -->|"Có"| R["Kiểm tra runtime SA, code, secret, dependency"]
    Code -->|"Không"| O["Kiểm tra delivery logs, latency, idempotency"]
~~~

**Đừng giải quyết mọi lỗi bằng cách cấp Owner/Editor hoặc mở function public.** Làm vậy có thể che sai thiết kế, tạo lỗ hổng và khiến việc chẩn đoán lần sau khó hơn.

### 13.2. Các lệnh đọc trạng thái hữu ích

~~~bash
gcloud eventarc triggers describe invoice-finalized \
  --project=PROJECT_ID --location=asia-southeast1

gcloud run services describe invoice-event-handler \
  --project=PROJECT_ID --region=asia-southeast1

gcloud run services get-iam-policy invoice-event-handler \
  --project=PROJECT_ID --region=asia-southeast1

gcloud projects get-iam-policy PROJECT_ID \
  --format=yaml

gcloud run services logs read invoice-event-handler \
  --project=PROJECT_ID --region=asia-southeast1 --limit=100
~~~

Khi truy xuất Cloud Audit Logs hoặc Pub/Sub metrics, cần quyền quan sát phù hợp; **không ghi bearer token, service account JSON, payload chứa PII hay signed URLs vào log**.

## 14. Bảo mật ứng dụng event-driven ngoài IAM

### 14.1. Nội dung CloudEvent vẫn là dữ liệu không tin cậy

Cloud Run kiểm tra **danh tính người gửi** khi private, nhưng dữ liệu sự kiện vẫn cần validation:

- Kiểm tra `event.type`, `source`, bucket allowlist và object generation.
- Giới hạn kích thước input, không log nguyên payload chứa dữ liệu nhạy cảm.
- Không dùng object name để truy cập filesystem tùy ý.
- Không thực hiện các hành động có side effect nếu chưa xác định **idempotency key**.
- Với webhook public hay event nguồn ngoài, cần kiểm tra chữ ký và chính sách xác thực riêng của provider.
- Nếu thao tác xuống database, ưu tiên transaction/idempotent upsert thay vì chỉ tin vào “chỉ nhận một lần”.

### 14.2. Retry và dead-letter handling

Event delivery có thể lặp hoặc thất bại do function timeout, 429, 5xx, network hoặc IAM. Kiểm tra **retry policy** của trigger/transport và cấu hình **dead-letter topic** khi phù hợp; không giả định mọi trigger luôn retry vô hạn hay luôn retry một lần.

Một handler tốt:

1. Nhận event, kiểm tra schema và source.
2. Xác định deduplication key.
3. Ghi nhận “đang xử lý/đã xử lý” vào storage có tính bền vững theo giao dịch.
4. Thực hiện nghiệp vụ idempotent.
5. Trả thành công chỉ khi công việc đã được chấp nhận/xử lý đúng chính sách.
6. Với lỗi tạm thời, dùng retry/backoff và cơ chế DLQ để tránh mất event hoặc vòng lặp vô hạn.

### 14.3. Cross-project và org policies

Nếu source bucket, Eventarc trigger, service account và function nằm ở các project khác nhau, cần kiểm tra:

- **Eventarc supported cross-project routing** và cấu hình dự án theo loại event.
- Organization Policy liên quan **cross-project service account usage**.
- Quyền `iam.serviceAccounts.actAs` của deployer trên SA thuộc project khác.
- Invoker IAM ở **target project/service**.
- Quyền nguồn event/agents trong **source project**.
- VPC Service Controls và data residency khi môi trường áp chính sách.

Không lấy ví dụ “một project, một region” rồi tự suy rằng có thể thay mọi `PROJECT_ID` bằng các giá trị khác nhau mà không bổ sung IAM.

## 15. Vận hành, quan sát và chi phí

| Tín hiệu | Cần theo dõi |
|---|---|
| Trigger health/conditions | Trigger có tạo được, route đúng destination, service account không sai |
| Event delivery success/failure | Số event nhận, retry, 4xx/5xx, delay |
| Function logs và latency | Thời gian xử lý, lỗi Java, memory/CPU, timeout |
| IAM changes | Thêm/xóa Invoker, Event Receiver, service agent roles |
| Quota và Pub/Sub transport | Đường event không bị quota/permission chặn |
| Idempotency/DLQ | Event bị lặp, backlog, dead-letter và quy trình replay |
| Billing | Eventarc, Pub/Sub transport, Cloud Run invocation/CPU/memory, build, logs, Cloud Storage operations |

Chi phí không chỉ là Cloud Run runtime; Pub/Sub transport, logging và storage requests có thể tính phí theo mức sử dụng/retention. Dùng **Billing Reports** và **Google Cloud Pricing Calculator**, không tự khẳng định mọi sự kiện có cùng giá hoặc mọi tài nguyên đều nằm trong free tier.

**Rollback:** giữ release trước của function, kiểm tra trigger destination/path và event filters; rollback code bằng revision/CI khi cần. Trước khi xóa trigger hoặc SA, xem còn consumer nào dùng. Xóa SA hoặc thu hồi Invoker quá sớm có thể khiến một luồng event khác ngừng hoạt động.

## 16. Case study: hóa đơn được xử lý bằng Java function

**Bối cảnh:** hệ thống bán lẻ có Orders API Java ghi hóa đơn PDF vào Cloud Storage. Khi object finalized, Eventarc gọi function xử lý metadata; function sau này có thể lưu trạng thái vào Firestore hoặc gửi Pub/Sub event downstream.

**Thiết kế quyền tối thiểu:**

| Thành phần | Principal | Quyền |
|---|---|---|
| Người phát hành function/trigger | CI deployer SA | Deploy/Eventarc create + `actAs` trên đúng service accounts |
| Eventarc trigger | `evt-invoice@...` | Event Receiver và Run Invoker trên `invoice-event-handler` |
| Cloud Storage event source | Cloud Storage service agent | Pub/Sub Publisher ở project theo hướng dẫn |
| Java function | `fn-invoice@...` | Không cần Storage Viewer nếu chỉ đọc metadata; thêm quyền bucket nếu phải download |
| Cloud Run target | Function private | Chỉ trigger SA và caller được phép có Invoker |
| Service agents | Eventarc/Cloud Run/Cloud Functions/PubSub khi áp dụng | Google-managed roles đúng principal và API |

Quy trình phát hành:

1. Tạo user-managed SAs với scope rõ.
2. Deploy function private bằng runtime SA.
3. Cấp đúng Invoker cho trigger SA.
4. Tạo trigger với filters chính xác.
5. Upload file test không nhạy cảm, quan sát event ID/type và logs.
6. Test negative: bỏ Invoker trong **sandbox** và xác minh lỗi authentication; cấp lại và xác minh phục hồi.
7. Bổ sung deduplication, retry/DLQ và alert trước khi production.
8. Ghi role bindings, key decisions và chi phí vào runbook.

**Không đồng nhất success HTTP với transaction success.** Nếu function chỉ log metadata nhưng nhiệm vụ thật phải xử lý hóa đơn vào database, cần kiểm thử side effects, idempotency và quyền DB.

## 17. Bài tập thực hành và câu hỏi tự đánh giá

### Bài 1 — Phân biệt bốn danh tính

Một kỹ sư cấp `roles/storage.objectViewer` cho trigger SA và `roles/run.invoker` cho runtime SA. Trigger có status active nhưng Cloud Run báo unauthorized.

**Hỏi:** đâu là hai lỗi cấp quyền? Cần chuyển role nào sang principal nào?

**Gợi ý:** Trigger SA cần Run Invoker trên function; runtime SA chỉ cần Storage Viewer khi code phải tải object.

### Bài 2 — Cloud Storage direct event

Eventarc nhận `google.cloud.storage.object.v1.finalized` nhưng không thấy Cloud Run log, dù target Invoker đúng.

**Hỏi:** kiểm tra service agent nào và role gì? Cần xem event filters/project/location không?

**Gợi ý:** Cloud Storage service agent cần Pub/Sub Publisher; kiểm tra filter type/bucket và Eventarc agent.

### Bài 3 — Pub/Sub direct event

Một Pub/Sub direct trigger đã có `roles/run.invoker` trên private function nhưng chưa có Event Receiver.

**Hỏi:** đây có phải luôn là lỗi? Vì sao?

**Gợi ý:** Với direct Pub/Sub events, Event Receiver không bắt buộc; kiểm tra delivery thực tế và các quyền khác.

### Bài 4 — Runtime API 403

Cloud Run nhận CloudEvent thành công, nhưng Java code gọi `Storage.get(bucket, object)` trả 403.

**Hỏi:** cần kiểm tra principal nào và IAM scope ở đâu? Tại sao thêm Event Receiver không sửa được?

**Gợi ý:** runtime SA có Storage Object Viewer trên bucket/permission cần thiết; lỗi xảy ra **sau invocation**.

### Bài 5 — Manual HTTP caller

Developer mở function URL bằng browser và thấy 403, nhưng Eventarc hoạt động bình thường.

**Hỏi:** browser có tự gửi đúng ID token không? Có nên bật unauthenticated access?

**Gợi ý:** cần caller identity, Run Invoker và ID token có audience phù hợp; đừng public function chỉ để test.

### Bài 6 — CI không triển khai được

Cloud Build deployer dùng runtime SA và trigger SA riêng, nhưng nhận lỗi `iam.serviceAccounts.actAs`.

**Hỏi:** `roles/iam.serviceAccountUser` nên cấp cho ai và trên tài nguyên nào?

**Gợi ý:** grant deployer/CI principal trên **đúng SAs** được attach; không cấp Owner toàn project.

### Bài 7 — Sự kiện đến hai lần

Hai event có cùng `source` và `id` làm function ghi hai bản invoice trong Firestore.

**Hỏi:** thiết kế cơ chế idempotency/deduplication thế nào? Khi nào trả thành công?

**Gợi ý:** lưu key xử lý bền vững và dùng conditional write/transaction; ack khi nghiệp vụ đạt kết quả theo hợp đồng.

### Bài 8 — Cross-project trigger

Bucket ở project A, function ở project B, trigger SA ở project C. Một engineer chỉ cấp quyền tại B và báo còn 403.

**Hỏi:** cần xác minh những lớp nào trước khi cho phép sản xuất?

**Gợi ý:** product support cross-project, Eventarc trigger/source projects, service account policy/actAs, target Invoker và service agents.

### Bài 9 — Chẩn đoán có thứ tự

Một luồng không có event sau upload. Hãy xếp chuỗi kiểm tra:

- Source bucket và type filter;
- Eventarc trigger identity/conditions;
- Cloud Storage Publisher và Eventarc agent;
- Target Cloud Run Invoker;
- Runtime Java logs và quyền đọc object;
- Retry/DLQ và idempotency.

**Yêu cầu:** nêu dấu hiệu phân biệt lỗi **trước invocation** với lỗi **trong function**.

## 18. Checklist trước khi dùng production

- [ ] Đã xác định loại event, source project/location và destination service đúng.
- [ ] Đã phân biệt **deployer**, **trigger SA**, **runtime SA** và **Google service agents**.
- [ ] Trigger dùng user-managed SA, không dựa vào Editor của default compute SA.
- [ ] `roles/eventarc.eventReceiver` được cấp khi provider yêu cầu; nhớ ngoại lệ **Pub/Sub direct events**.
- [ ] `roles/run.invoker` nằm trên đúng **Cloud Run service đích** và thuộc đúng trigger SA.
- [ ] Function private; ingress, IAM Invoker và app-level authorization được xem riêng.
- [ ] Cloud Storage direct event có quyền Publisher cho đúng **Cloud Storage service agent**.
- [ ] Eventarc service agent còn role được quản lý; legacy Pub/Sub token creator chỉ cấp khi cần.
- [ ] Runtime SA có quyền Google APIs tối thiểu; không lưu private key JSON trong source/image.
- [ ] Người deploy có role deploy/trigger create và `iam.serviceAccounts.actAs` trên SA liên quan.
- [ ] CloudEvent input được kiểm tra source/type/ID, không coi payload là credential.
- [ ] Handler idempotent; retries, timeout, dead-letter và replay được quản trị.
- [ ] Đã có logs/metrics/alerts cho 401/403/5xx, event delay và IAM drift.
- [ ] Đã kiểm tra cross-project, VPC Service Controls, org policies và data residency nếu áp dụng.
- [ ] Đã thử negative-case 403 an toàn trong sandbox, xác minh sửa bằng IAM đúng principal.
- [ ] Đã tính chi phí Cloud Run, Pub/Sub transport, Eventarc, logs, build và source operations.
- [ ] Có runbook, owner, rollback và kiểm soát thu hồi service accounts/triggers.

## 19. Tài liệu chính thức

Các role, service agents, cách deploy và event providers có thể thay đổi theo thời gian. Đối chiếu trước khi thao tác trên project thật:

- [Eventarc Standard — Roles and permissions for Cloud Run functions targets](https://docs.cloud.google.com/eventarc/standard/docs/functions/roles-permissions)
- [Eventarc Standard — Roles and permissions for Cloud Run targets](https://docs.cloud.google.com/eventarc/docs/roles-permissions)
- [Cloud Run — Deploy a function from source](https://docs.cloud.google.com/run/docs/deploy-functions)
- [Cloud Run — Write functions](https://docs.cloud.google.com/run/docs/write-functions)
- [Cloud Run — Java runtime](https://docs.cloud.google.com/run/docs/runtimes/java)
- [Cloud Run — Introduction to service identity](https://docs.cloud.google.com/run/docs/securing/service-identity)
- [Cloud Run — Configure service identity](https://docs.cloud.google.com/run/docs/configuring/services/service-identity)
- [Eventarc — Receive Cloud Storage direct events using gcloud](https://docs.cloud.google.com/eventarc/standard/docs/run/create-trigger-storage-gcloud)
- [Cloud Run — Trigger functions from Cloud Storage using Eventarc](https://docs.cloud.google.com/run/docs/tutorials/trigger-functions-storage)
- [Cloud Run — Troubleshooting](https://docs.cloud.google.com/run/docs/troubleshooting)
- [Cloud Functions v2 — Function identity](https://docs.cloud.google.com/functions/docs/securing/function-identity)
- [Eventarc — IAM roles reference](https://docs.cloud.google.com/iam/docs/roles-permissions/eventarc)

**Điểm cần nhớ:** Với **Eventarc → private Cloud Run function**, **trigger service account** phải có **quyền nhận event phù hợp** và **`roles/run.invoker` trên đúng function**; **runtime service account** chỉ được cấp các quyền mà mã Java cần khi chạy. **Cloud Storage/Pub/Sub/Eventarc service agents** có nhiệm vụ riêng, không được nhầm với hai tài khoản đó. Cấu hình bảo mật đúng phải được kiểm thử bằng **event thật, logging, negative-case 403, idempotency và chi phí**, không chỉ bằng trạng thái trigger “Active”.
