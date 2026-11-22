# Kiểm thử tích hợp trên project GCP dùng riêng

Unit test xác minh business logic khi các dependency được thay bằng mock hoặc fake. Kiểm thử tích hợp (integration testing) xác minh các thành phần Java/Spring có thực sự làm việc với API, xác thực, dữ liệu, mạng và hành vi của Google Cloud hay không. Một unit test có thể giả lập thao tác ghi object thành công, nhưng chỉ kiểm thử với Cloud Storage thật mới phát hiện một service account thiếu quyền, bucket không đúng hoặc Java client dùng sai credential.

Trong chương **Kiểm thử ứng dụng GCP** của module **CLOUD_PROVIDERS_GCP**, bài học hướng dẫn xây dựng môi trường kiểm thử tích hợp bằng **một Google Cloud project dành riêng cho kiểm thử**, tách biệt staging và production. Quy trình kết hợp tổ chức project, IAM, VPC, dịch vụ lưu trữ/cơ sở dữ liệu, CI/CD, Cloud Logging và Cloud Monitoring. Mục tiêu là kiểm thử phản ánh hành vi thực tế, lặp lại được, quan sát được và không ảnh hưởng tài nguyên sản xuất.

Sau bài học, người học có thể:

- Phân biệt mock/emulator, component test, integration test dùng tài nguyên GCP thật và end-to-end test.
- Thiết kế project kiểm thử riêng với ranh giới IAM, dữ liệu, mạng, quota và chi phí.
- Xác thực đúng project và tài nguyên trước khi test, tránh ghi nhầm production.
- Chọn Application Default Credentials (ADC) và cấp quyền tối thiểu cho test runner trong local/CI.
- Viết integration test bằng JUnit 5, Spring Boot và Google Cloud Java SDK.
- Kiểm thử Cloud Storage, Pub/Sub, Cloud SQL và ứng dụng Cloud Run.
- Cô lập fixture/test run, chống tranh chấp tài nguyên, xử lý bất đồng bộ và dọn dẹp an toàn.
- Tích hợp với Cloud Build hoặc CI bên ngoài; phân tích lỗi và thu thập bằng chứng kiểm thử.

## 1. Kiểm thử tích hợp trong chiến lược testing

Mỗi tầng kiểm thử có mục đích, tốc độ, chi phí và mức độ chân thực riêng.

| Tầng | Phạm vi | Phụ thuộc | Giá trị chính |
|---|---|---|---|
| Unit | Hàm/class, rule và validation | Mock/fake | Phản hồi nhanh, định vị lỗi logic |
| Component | Spring context, repository, controller | In-memory DB, Testcontainers, emulator | Kiểm tra wiring và hợp đồng nội bộ |
| Integration GCP | Java SDK, IAM, network, API thật | Project GCP dành cho test | Xác nhận tương tác dịch vụ cloud |
| Contract | Schema API/event và compatibility | Stub hoặc hợp đồng provider | Phát hiện sai lệch hợp đồng |
| End-to-end | Luồng từ HTTP request đến kết quả cuối | Nhiều dịch vụ cùng môi trường | Chứng minh hành trình nghiệp vụ |
| Load/resilience | Hiệu năng và hành vi khi xảy ra lỗi | Môi trường kiểm soát | Đánh giá SLO và giới hạn năng lực |

Ví dụ một API upload tài liệu có thể có các test:

1. Unit test kiểm tra tên file hợp lệ và giới hạn kích thước.
2. Component test xác nhận service gọi adapter lưu trữ đúng dữ liệu.
3. Integration test ghi/đọc lại object trên Cloud Storage thuộc project test.
4. End-to-end test gửi HTTP request vào Cloud Run, kiểm tra metadata trong database và object trên bucket.

Integration test phát hiện các vấn đề mà mock thường không kiểm tra đủ: IAM, API service enablement, cú pháp request SDK, network, quota và timeout. Tuy nhiên, test trên cloud thật đắt và chậm hơn; chỉ chọn các đường tích hợp có giá trị thay vì đưa mọi business rule lên cloud.

### 1.1. Emulator và dịch vụ thật

Pub/Sub emulator, Firestore emulator hoặc Testcontainers có thể chạy nhanh trên máy lập trình/CI. Chúng phù hợp kiểm tra serialization, transaction và basic workflow nhưng không nhất thiết tái hiện đầy đủ IAM, VPC, Cloud Logging, organization policy, retry policy hoặc quota của GCP thật.

Một chiến lược hợp lý:

- Mỗi pull request chạy unit, component, Testcontainers và emulator.
- Merge lên main chạy bộ integration test GCP ngắn, có kiểm soát.
- Theo lịch hoặc trước release chạy luồng cross-service và kiểm thử sâu hơn.
- Bài test tải lớn chỉ chạy khi có kế hoạch quota, kinh phí và điều kiện dọn dẹp.

## 2. Kiến trúc project GCP dùng riêng

Google Cloud project là ranh giới quản trị thuận tiện cho IAM, API, billing, quota, logs và tài nguyên. Không nên dùng project production chỉ để thuận tiện vì đã có sẵn bucket hoặc database.

~~~mermaid
flowchart LR
    Dev[Developer] -->|ADC| Runner[Test runner identity]
    CI[Cloud Build / CI] -->|Service account / WIF| Runner
    Runner --> Test[Project GCP integration-test]
    Test --> GCS[Cloud Storage test bucket]
    Test --> Pub[Pub/Sub test topic/subscription]
    Test --> SQL[Cloud SQL test database]
    Test --> Ops[Cloud Logging + Monitoring]
    Test --> Clean[Scoped cleanup + TTL]
    Prod[Production project] -.No test-runner permissions.-> Runner
~~~

| Project ví dụ | Mục đích | Danh tính được phép ghi |
|---|---|---|
| app-dev | Phát triển thủ công | Developer |
| app-it | Kiểm thử tích hợp với GCP thật | CI/test runner |
| app-staging | Kiểm tra release candidate | Staging pipeline |
| app-prod | Phục vụ người dùng | Production workload |

Đặt tên project là bước đầu, nhưng **IAM mới thực sự giới hạn tác động**. Nếu người chạy test vẫn có quyền ghi production thì sai sót trong cấu hình Java client có thể gây ảnh hưởng dù đã tạo project test.

### 2.1. Ranh giới cần tách

- **IAM:** runner chỉ có quyền cần thiết trên project test hoặc resource cụ thể.
- **Dữ liệu:** dữ liệu giả, tổng hợp hoặc đã làm sạch; không dùng dữ liệu khách hàng thật khi không có cơ sở.
- **Mạng:** test không được vô tình trỏ vào endpoint nội bộ production.
- **Secrets:** secret test và production tách biệt, vòng đời và quyền đọc riêng.
- **Billing/quota:** ngân sách và cảnh báo riêng; giới hạn tài nguyên có chi phí lớn.
- **Logging:** trace, metric, log ở project test để dễ truy vết và kiểm soát retention.
- **Quy trình phát hành:** test pass là bằng chứng chất lượng, không tự cấp quyền deploy production.

### 2.2. Project dùng chung hay project tạm cho từng run?

**Một project test dùng chung:** Provision bucket, topic, Cloud SQL instance một lần rồi phân tách object prefix, subscription, schema và database theo run ID. Phù hợp kiểm thử thường xuyên, chi phí tạo hạ tầng thấp. Đổi lại cần chống xung đột và cleanup orphan resources.

**Project tạm cho từng pipeline/nhánh:** Cách ly mạnh, có thể thu hồi trọn project sau test. Đổi lại, project creation, billing, organization policy, API enablement và quota provisioning phức tạp, chậm và đòi quyền cao.

Với CI chạy mỗi ngày, một project test riêng kết hợp tài nguyên phân vùng theo run ID thường là điểm khởi đầu. Với thử nghiệm hạ tầng/IAM có tính phá hủy, nên provision project tạm riêng để bảo vệ test suite khác.

## 3. Chuẩn bị project kiểm thử

Quản trị viên hoặc pipeline provision tạo project, liên kết billing, bật API và cấu hình tài nguyên nền; test runner thông thường không cần quyền tạo project.

### 3.1. Tên và metadata

Xác định tên project có dấu hiệu integration-test, owner, nhóm liên hệ, labels như environment=integration, application=orders và cost_center=engineering. Ghi thời hạn tồn tại, retention policy, quota, budget và quy trình xử lý tài nguyên bỏ quên. Label giúp tra cứu và phân loại, **không tự động xóa tài nguyên**.

### 3.2. Named configuration trong gcloud

~~~bash
gcloud config configurations create integration-tests
gcloud config set project "$GCP_TEST_PROJECT_ID"
gcloud config get-value project
gcloud projects describe "$GCP_TEST_PROJECT_ID" \
  --format="table(projectId,name,lifecycleState)"
~~~

Biến GCP_TEST_PROJECT_ID phải được truyền từ cấu hình môi trường đã được kiểm soát. Lệnh trên chỉ minh họa thao tác quản trị local; trong CI có thể đặt --project tường minh ở từng lệnh.

Chú ý: project trong gcloud configuration và project mà Java client dùng **có thể khác**. Java SDK thường lấy credential qua ADC, đồng thời một số client có thể tự suy project từ môi trường. Nên truyền project ID và resource name rõ ràng cho test, sau đó xác minh bằng IAM/preflight.

### 3.3. Bật API

Ví dụ cho integration test Cloud Storage và Pub/Sub:

~~~bash
gcloud services enable \
  storage.googleapis.com \
  pubsub.googleapis.com \
  --project="$GCP_TEST_PROJECT_ID"
~~~

Nếu test dùng Cloud SQL, Cloud Run, Secret Manager hoặc Cloud Build thì bật API tương ứng. Bật API cần Service Usage permissions; chạy ở giai đoạn provisioning, không cấp quyền đó thường trực cho mọi test runner.

### 3.4. Provision tài nguyên nền

~~~bash
gcloud storage buckets create "gs://$GCP_TEST_BUCKET" \
  --project="$GCP_TEST_PROJECT_ID" \
  --location=asia-southeast1 \
  --uniform-bucket-level-access

gcloud pubsub topics create "$GCP_TEST_TOPIC" \
  --project="$GCP_TEST_PROJECT_ID"

gcloud pubsub subscriptions create "$GCP_TEST_SUBSCRIPTION" \
  --topic="$GCP_TEST_TOPIC" \
  --project="$GCP_TEST_PROJECT_ID"
~~~

Bucket name có phạm vi toàn cục nên phải duy nhất, không chứa dữ liệu nhạy cảm. Script provision nên idempotent: nếu tài nguyên đã tồn tại, kiểm tra project, labels và cấu hình trước khi sử dụng. Có thể quản lý bằng Terraform hoặc IaC của tổ chức để dễ audit và tái tạo.

### 3.5. Budget và quota

Test có thể gây chi phí từ Cloud SQL instance chạy khi không có request, Cloud Run minimum instances, lưu trữ, Pub/Sub backlog, network egress, Cloud Build và log ingest. Hãy cấu hình Cloud Billing budget và alert, owner theo dõi; **budget alert không phải hard cap** và không mặc nhiên dừng dịch vụ.

Quota có thể áp theo project, region hoặc API. Nếu nhiều test cùng chạy, giới hạn concurrency và theo dõi lỗi 429/RESOURCE_EXHAUSTED trước khi yêu cầu tăng quota. Hạn chế tạo các resource đắt tiền trong mỗi test method.

## 4. ADC, service account và IAM tối thiểu

Không để key JSON production trong source, JAR, container image hoặc CI secret nếu có phương án sử dụng danh tính ngắn hạn.

| Môi trường | Danh tính khuyến nghị | Cơ chế |
|---|---|---|
| Local | Developer ADC hoặc impersonated test service account | gcloud auth application-default |
| Cloud Build | User-managed CI/test service account | Build identity gắn với trigger |
| GitHub Actions/CI ngoài GCP | Federated identity tới service account test | Workload Identity Federation (OIDC) |
| GKE test runner | Kubernetes ServiceAccount | Workload Identity Federation for GKE |
| Compute Engine runner | VM service account | Metadata server/ADC |

### 4.1. ADC cho local

~~~bash
gcloud auth login
gcloud auth application-default login
gcloud auth application-default set-quota-project "$GCP_TEST_PROJECT_ID"
~~~

Credential gcloud CLI và ADC không luôn là một; lệnh auth application-default dành cho client library. Người chạy có thể cần Service Usage Consumer trên quota project. Nếu tổ chức dùng service account impersonation, hãy theo đúng chính sách để lấy short-lived credential và giới hạn quyền impersonation.

### 4.2. Vai trò IAM theo thao tác

| Thao tác | Role thường dùng | Nơi cấp |
|---|---|---|
| Upload/read/delete test object | roles/storage.objectUser | Một test bucket |
| Publish test message | roles/pubsub.publisher | Test topic |
| Pull/ack test message | roles/pubsub.subscriber | Test subscription |
| Tạo Pub/Sub resource khi provision | roles/pubsub.editor hoặc custom role | Project test, chỉ cho provisioner |
| Kết nối Cloud SQL connector | roles/cloudsql.client | Project/instance test |
| Đọc secret test | roles/secretmanager.secretAccessor | Một secret test |
| Ghi build logs khi cần | roles/logging.logWriter | Project log |

Cloud SQL Client cho phép kết nối qua connector/Auth Proxy, nhưng không cấp quyền SQL bên trong database; user/password hoặc IAM database authentication vẫn phải cấu hình riêng. Runner dùng Storage Object User không cần quyền xóa bucket.

Nên tách **provisioner**, **runner** và nếu cần **cleanup identity**. Provisioner tạo hạ tầng; runner chỉ kiểm tra dữ liệu; cleanup có thể xóa tài nguyên run-scoped được phê duyệt. Không cấp Owner/Editor cho runner chỉ để xử lý lỗi quyền.

### 4.3. Preflight chống nhầm môi trường

Trước test cần kiểm tra:

1. GCP_TEST_PROJECT_ID được cung cấp và nằm trong allowlist project test.
2. Project không trùng production/staging bị cấm ghi.
3. Bucket, topic, instance và endpoint thuộc inventory đã provision.
4. Danh tính thực tế có quyền giới hạn trên môi trường test.
5. Không có secret hoặc endpoint production trong test profile.

Ví dụ guardrail đơn giản:

~~~bash
set -euo pipefail
test -n "$GCP_TEST_PROJECT_ID" || exit 2
test -n "$GCP_TEST_BUCKET" || exit 2
test -n "$PROD_PROJECT_ID" || exit 2
if [ "$GCP_TEST_PROJECT_ID" = "$PROD_PROJECT_ID" ]; then
  echo "Refusing to run tests against production" >&2
  exit 2
fi
gcloud projects describe "$GCP_TEST_PROJECT_ID" \
  --format="value(projectId)"
~~~

So sánh project trong ví dụ chỉ là bước cơ bản; môi trường thực tế nên dùng allowlist ID và manifest resource do platform team quản lý. IAM mới là ranh giới bảo vệ cuối cùng.

## 5. Tạo fixture và test-run ID

Trên project dùng chung, hai pipeline có thể chạy cùng lúc. Nếu chúng sử dụng chung object key, database row hoặc Pub/Sub subscription, một test có thể ghi đè dữ liệu của test khác.

Mỗi run nên có ID duy nhất: CI BUILD_ID, commit SHA kết hợp run number hoặc UUID khi chạy local. Gắn ID vào object prefix, database/schema hoặc message attributes.

| Tài nguyên | Vòng đời | Cách cô lập |
|---|---|---|
| Bucket nền | Dùng chung | Prefix it/orders/<run-id>/ |
| Object | Mỗi test | UUID, precondition chống overwrite |
| Pub/Sub topic nền | Dùng chung hoặc suite | Message attributes + subscription thích hợp |
| Subscription | Suite/run | Tên độc nhất nếu cần tránh tranh message |
| Cloud SQL instance | Có thể dùng chung | Database/schema riêng hoặc namespace dữ liệu |
| Cloud Run test service | Theo deployment | URL/identity/traffic rõ ràng |
| Secret test | Quản trị bởi provisioner | Không chỉnh secret chung giữa test |

Fixture phải tự tạo được, không phụ thuộc thứ tự thực thi hoặc dữ liệu còn sót từ run trước. Với dữ liệu bất đồng bộ, chọn deadline và cách dò kết quả thay vì đặt thời gian sleep cố định.

## 6. Ví dụ Java và JUnit 5 với Cloud Storage thật

Giả sử ứng dụng Spring Boot lưu hóa đơn lên Cloud Storage. Mục tiêu integration test: Java SDK ghi một object vào bucket test, đọc lại đúng bytes và xóa đúng object đã tạo.

### 6.1. Dependency

Dùng Google Cloud Libraries BOM để nhất quán các client library. Mẫu Maven:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>libraries-bom</artifactId>
      <version>26.70.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-storage</artifactId>
  </dependency>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Phiên bản BOM ở đây chỉ minh họa cấu trúc, cần chọn bản đang được tổ chức phê duyệt và hỗ trợ tại thời điểm chạy. JUnit Jupiter phải được cấu hình qua Maven Surefire/Failsafe hoặc Gradle test task phù hợp.

### 6.2. Test round-trip

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("gcp-integration")
class CloudStorageRoundTripIT {
    private static String projectId;
    private static String bucket;
    private static Storage storage;
    private final List<BlobId> createdObjects = new ArrayList<>();

    @BeforeAll
    static void prepare() {
        projectId = requiredEnv("GCP_TEST_PROJECT_ID");
        bucket = requiredEnv("GCP_TEST_BUCKET");

        // CI preflight xác minh allowlist project và bucket.
        storage = StorageOptions.newBuilder()
                .setProjectId(projectId)
                .build()
                .getService();
        // Provisioner đã xác minh bucket; runner chỉ cần quyền object.
    }

    @Test
    void canWriteAndReadObject() {
        String name = "it/orders/" + UUID.randomUUID() + "/invoice.txt";
        byte[] expected = "integration-ok".getBytes(StandardCharsets.UTF_8);
        BlobInfo info = BlobInfo.newBuilder(BlobId.of(bucket, name)).build();

        Blob created = storage.create(
                info, expected, Storage.BlobTargetOption.doesNotExist());
        createdObjects.add(created.getBlobId());

        byte[] actual = storage.readAllBytes(created.getBlobId());
        assertArrayEquals(expected, actual);
    }

    @AfterEach
    void cleanObjects() {
        for (BlobId id : createdObjects) {
            storage.delete(id);
        }
        createdObjects.clear();
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing env: " + name);
        }
        return value;
    }
}
~~~

Test có một số biện pháp bảo vệ:

- Bắt buộc khai báo tên project và bucket rõ ràng.
- Object key ngẫu nhiên nên các run không ghi đè nhau.
- Điều kiện doesNotExist từ chối overwrite object đã tồn tại.
- AfterEach chỉ xóa object test đã lưu, không xóa bucket.
- Nếu process chết trước AfterEach, object có thể còn sót; cleanup ở cấp môi trường cần xử lý theo run ID hoặc TTL.

Cloud Storage bucket có tên toàn cục. StorageOptions với projectId rõ ràng **không tự chứng minh bucket thuộc project đó**. Provision manifest, allowlist bucket và IAM cấp trên bucket test là các kiểm soát cần thiết. Khi cần bảo vệ object theo generation, dùng precondition/generation của Storage API.

### 6.3. Spring Boot integration profile

~~~java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("integration")
@Tag("gcp-integration")
class OrderStorageIntegrationIT {
    @Test
    void contextLoadsWithTestProfile() {
        // Chỉ là bước kiểm tra cấu hình, chưa chứng minh hành vi I/O.
    }
}
~~~

Trong application-integration.yaml chỉ đặt project, endpoint và cấu hình không nhạy cảm. Secret lấy từ Secret Manager hoặc CI environment được kiểm soát. Dùng @DynamicPropertySource nếu muốn truyền endpoint/database name được provision động.

Một test contextLoads chỉ xác nhận Spring context khởi động. Bài tích hợp thực sự phải có thao tác ghi/đọc hoặc publish/consume và assertion kết quả cụ thể.

## 7. Kiểm thử Pub/Sub

Pub/Sub dùng mô hình asynchronous nên cần kiểm tra serialization, message attributes, retry, ack/nack, idempotency và deadline.

### 7.1. Kịch bản OrderCreated

1. Test tạo run ID và order ID độc nhất.
2. Publish OrderCreated vào **test topic**, đặt message attribute testRunId.
3. Application consumer trong môi trường test nhận message từ **test subscription**.
4. Consumer ghi kết quả vào test database hoặc test bucket.
5. JUnit poll kết quả đến một deadline rõ ràng và assert nội dung.
6. Cleanup subscription/object/row theo run ID.

~~~mermaid
sequenceDiagram
    participant T as JUnit test
    participant P as Pub/Sub topic
    participant S as Test subscription
    participant W as Spring consumer
    participant D as Test database
    T->>P: Publish OrderCreated + testRunId
    P-->>S: Deliver
    S-->>W: Receive
    W->>D: Persist result
    W-->>S: Ack
    loop Poll until deadline
      T->>D: Query by testRunId + orderId
    end
    D-->>T: Expected result
~~~

Trong các cấu hình thông dụng, Pub/Sub có thể deliver message nhiều lần. Consumer phải idempotent theo event ID hoặc business key. Test không nên assert rằng một message chắc chắn được xử lý duy nhất một lần khi hệ thống không bảo đảm điều đó.

### 7.2. Subscription dùng chung có thể gây tranh chấp

Nếu hai runner cùng pull một subscription, message có thể được nhận bởi runner khác. Message attribute testRunId có ích để lọc logic nhưng **không ngăn một subscriber khác nhận message** trên cùng subscription. Tạo subscription riêng cho suite/run hoặc thiết kế topology rõ ràng.

Không dùng Thread.sleep cố định làm tiêu chí đồng bộ. Dùng polling có timeout (ví dụ deadline 30 giây tùy SLO), backoff hợp lý và ghi message ID, subscription, testRunId khi thất bại.

### 7.3. Các trường hợp lỗi nên có

- Payload thiếu field hoặc schema version không hỗ trợ.
- Consumer thất bại và message được retry.
- Duplicate message nhưng database không tạo record trùng.
- Message đến khác thứ tự; hệ thống vẫn xử lý đúng.
- Subscription backlog gây trễ vượt mức cho phép.
- Publisher đủ quyền nhưng subscriber thiếu quyền pull/ack.

## 8. Kiểm thử Cloud SQL và dữ liệu có trạng thái

Cloud SQL integration test xác minh kết nối, migration, constraint, transaction và query trên database thật.

### 8.1. Tách dữ liệu

- Chỉ dùng Cloud SQL instance/database cho test.
- Database user được cấp quyền nhỏ nhất trên schema/database test.
- Có schema hoặc database riêng theo run khi cần chạy song song.
- Dùng Cloud SQL connector/Auth Proxy hoặc network path phù hợp, kiểm tra private IP/firewall/DNS.
- Chạy Flyway/Liquibase migration trong môi trường test theo đúng version của ứng dụng.
- Giới hạn HikariCP connection pool và số run đồng thời theo max connections.

Role roles/cloudsql.client cần cho một số cơ chế kết nối qua Cloud SQL connector/Auth Proxy, nhưng không thay thế user/password hoặc IAM database authentication và quyền SQL bên trong database.

### 8.2. Rollback transaction có giới hạn

Spring Test với @Transactional có thể rollback thao tác trong transaction của test method. Nó không tự rollback dữ liệu:

- Được ghi ở process/service khác.
- Được ghi bởi asynchronous Pub/Sub consumer.
- Được ghi qua HTTP request sang Cloud Run.
- Được publish ra Pub/Sub hoặc ghi vào Cloud Storage.

Với các luồng xuyên dịch vụ, cleanup phải dùng run ID/ownership hoặc tạo database/schema tạm riêng có thể thu hồi sau suite.

### 8.3. Testcontainers và Cloud SQL thực

Testcontainers chạy PostgreSQL/MySQL rất hữu ích để xác minh schema, SQL query và transaction nhanh. Tuy nhiên, nó không kiểm tra Cloud SQL IAM, connector, network, instance setting, failover, quota. Nên kết hợp Testcontainers cho PR và một nhóm integration test Cloud SQL ít nhưng có giá trị trên project test.

## 9. Kiểm thử Cloud Run, IAM và network

Nếu deploy ứng dụng Java/Spring lên Cloud Run thuộc project test, có thể test HTTP endpoint với token của danh tính test.

Các assertion đáng có:

- Service trả response/schema đúng.
- Endpoint yêu cầu authentication từ chối request thiếu token.
- Test runner có quyền invoke; identity không được cấp quyền bị từ chối.
- Runtime identity kết nối đúng Cloud SQL, Storage, Pub/Sub test.
- Timeout, retry và error response được xử lý theo hợp đồng.
- Log có correlation ID/trace ID nhưng không lộ secret.

Nếu Cloud Run ingress chỉ cho internal traffic, test runner phải nằm trên đường network hợp lệ. HTTP 403 có thể do IAM/token, 404 do URL/ingress, 503 do startup/instance/dependency; nên xem request logs và application logs trước khi suy đoán.

Không đổi service thành public chỉ để test pass. Dùng đúng token audience, roles/run.invoker, ingress và danh tính CI.

### 9.1. Negative IAM tests

Có thể dùng một test identity riêng không có quyền Storage Object User hoặc Cloud Run Invoker, sau đó xác nhận API từ chối thao tác. Không thay IAM policy của runner đang được các test khác sử dụng vì sẽ gây race condition. Không tháo policy production để kiểm thử quyền.

## 10. Tổ chức test bằng JUnit/Maven/Gradle

Tách integration tests khỏi unit tests giúp CI có thể chọn đúng thời điểm chạy và credential tương ứng.

### 10.1. Tags và naming convention

~~~java
@Tag("gcp-integration")
@Tag("storage")
class StorageRoundTripIT {
    // Calls a real, dedicated Google Cloud test bucket.
}
~~~

JUnit tag chỉ có tác dụng nếu build tool được cấu hình include/exclude tags. Maven Failsafe thường dùng class name *IT và chạy ở phases integration-test/verify; Gradle có thể tạo test suite/task riêng.

### 10.2. Maven Failsafe

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-failsafe-plugin</artifactId>
  <version>3.5.4</version>
  <executions>
    <execution>
      <goals>
        <goal>integration-test</goal>
        <goal>verify</goal>
      </goals>
    </execution>
  </executions>
  <configuration>
    <includes>
      <include>**/*IT.java</include>
    </includes>
    <groups>gcp-integration</groups>
  </configuration>
</plugin>
~~~

Phiên bản plugin chỉ minh họa; cần chọn bản tương thích với toolchain dự án. Chạy Maven phase verify để Failsafe đánh giá kết quả và trả exit code nếu test fail, không chỉ chạy integration-test rồi bỏ verify.

Với Gradle, sử dụng JUnit Platform tags trong một task/suite riêng, tách khỏi test task chạy unit test. Cần bảo đảm CI không vô tình bỏ qua toàn bộ nhóm integration khi có cấu hình profile mới.

## 11. Cloud Build và pipeline kiểm thử tích hợp

~~~mermaid
flowchart LR
    PR[Pull request] --> Unit[Unit + emulator tests]
    Unit --> Merge[Merge main / schedule]
    Merge --> Prep[Preflight project + resources]
    Prep --> IT[GCP integration suite]
    IT --> Report[Assertions + JUnit XML]
    Report --> Clean[Scoped cleanup]
    Clean --> Done[Build result + evidence]
~~~

Một lựa chọn vận hành:

- PR: unit/component tests, không cấp secret production.
- Main: integration test GCP trên project riêng.
- Theo lịch: test chậm, cross-service, quota/resilience có kiểm soát.
- Trước release: smoke test artifact và runtime đã chọn.

### 11.1. Service account riêng

Cloud Build trigger cần dùng test service account chỉ có quyền trên resource test. Nếu project chứa Cloud Build khác project chứa test resources, cấp cross-project IAM tường minh ở scope hẹp. Tránh mặc định cấp Editor và tránh sử dụng runtime identity production.

Với GitHub Actions hoặc CI ngoài GCP, dùng Workload Identity Federation kết hợp OIDC và test service account. Giới hạn trust theo repository, branch, workflow và audience; không cho PR từ fork không tin cậy nhận credential có thể ghi cloud.

### 11.2. Ví dụ cloudbuild.yaml

~~~yaml
steps:
  - name: maven:3.9-eclipse-temurin-21
    entrypoint: bash
    args:
      - -euc
      - |
        mvn -B -Pcloud-integration verify
    env:
      - GCP_TEST_PROJECT_ID=$_TEST_PROJECT_ID
      - GCP_TEST_BUCKET=$_TEST_BUCKET

substitutions:
  _TEST_PROJECT_ID: myapp-it
  _TEST_BUCKET: myapp-it-bucket-example

options:
  logging: CLOUD_LOGGING_ONLY

timeout: 1200s
~~~

Đây là skeleton: profile cloud-integration và test dependencies phải có trong repository. Java SDK trong build step phải lấy được ADC từ môi trường Cloud Build/service account mà tổ chức đã cấu hình. Xác minh quyền và cách cấp ADC trong worker image đang dùng; không đưa JSON key, password vào substitutions.

### 11.3. Bằng chứng và audit

Mỗi test run nên lưu commit SHA, build ID, project test ID, run ID, test group/version, JUnit report, error log, trace ID và kết quả cleanup. Không đưa token, connection string có password hoặc payload nhạy cảm vào artifact và log. Liên kết từ build failure đến GCP resource của run đó giúp điều tra hiệu quả.

## 12. Kiểm soát flaky tests và concurrency

| Triệu chứng | Nguyên nhân có thể | Biện pháp |
|---|---|---|
| Test A đọc message của B | Chung subscription | Subscription riêng theo run |
| Object bị ghi đè | Trùng tên | UUID/prefix và precondition |
| Trùng primary key | Fixture hoặc cleanup lỗi | Unique keys, schema riêng |
| 429/quota exceeded | Nhiều suite chạy song song | Giới hạn concurrency, backoff |
| Timeout provisioning | Resource chưa sẵn sàng | Poll readiness có deadline |
| Local pass, CI fail | ADC/network/IAM khác | Preflight và role rõ ràng |
| Test fail ngẫu nhiên | Asynchronous outcome chưa hoàn thành | Poll theo điều kiện thay vì sleep |
| Chi phí tăng | Orphan resources | Inventory, TTL, cleanup job |

### 12.1. Timeout và retry

Thiết lập client API timeout, test-level deadline và polling/backoff với giới hạn. Phân biệt lỗi tạm như unavailable/429 với lỗi cấu hình kéo dài như permission denied. Không retry vô hạn; request có side effect phải có idempotency key hoặc cách chống tạo dữ liệu trùng.

### 12.2. Không quy mọi lỗi cho eventual consistency

Cloud Storage có strong consistency cho nhiều thao tác object và listing như tài liệu Google Cloud công bố. Nếu vừa ghi object nhưng đọc không thấy, hãy kiểm tra bucket, object key, generation, credential và response error trước khi thêm sleep. Ngược lại, Pub/Sub consumer xử lý bất đồng bộ, cần đợi kết quả từ process khác theo deadline.

## 13. Cleanup theo hai cấp

**Cấp method/run:** dùng try/finally, AfterEach hoặc AfterAll để xóa object, row và subscription/database tạm do chính run tạo. Không xóa bucket, topic hay project nền từ teardown thông thường.

**Cấp môi trường:** cleanup workflow quét orphan resource qua run ID, label, inventory và TTL; xử lý resource còn sót khi runner chết, CI bị hủy hoặc mất mạng. Quyền cleanup có thể tách riêng khỏi runner.

Các bước kiểm tra trước xóa:

1. Project ID nằm trong allowlist test.
2. Resource có owner/run ID khớp.
3. Scope không bao trùm resource của run khác.
4. Có inventory hoặc dry-run nếu công cụ hỗ trợ.
5. Xóa theo thứ tự dependency phù hợp.
6. Xác nhận xóa thành công và cập nhật inventory.
7. Giữ lại log cần thiết theo retention policy.

Nếu cleanup thất bại, report cả lỗi test gốc và lỗi cleanup, kèm resource ID bị bỏ lại. Cleanup failure không được âm thầm coi là PASS nếu gây rủi ro chi phí hoặc ảnh hưởng lần chạy tiếp theo.

## 14. Thực hành tổng hợp: Java API đơn hàng

Giả sử Spring Boot API nhận đơn hàng, lưu Cloud SQL, phát OrderCreated tới Pub/Sub; consumer tạo hóa đơn PDF trong Cloud Storage.

**Mục tiêu:** xác nhận HTTP API, database, publish/consume và lưu trữ trên một project GCP test riêng.

### Bước 1. Provision

Tạo project test có Cloud SQL, Pub/Sub, Cloud Storage, Cloud Run test service và service accounts. Thiết lập IAM, VPC/private connectivity, budget alerts và retention. Ghi lại resource inventory đã được provision.

### Bước 2. Tạo fixture

Sinh run ID, order ID và dữ liệu khách hàng giả. Tạo schema/database hoặc prefix object dành cho run nếu cần chạy song song. Xác nhận tất cả endpoint/secret đều thuộc môi trường test.

### Bước 3. Thực thi

1. Gửi HTTP POST đến TEST_BASE_URL với order ID ngẫu nhiên.
2. Assert HTTP status, response schema và correlation ID.
3. Poll database để xác nhận order được ghi đúng.
4. Poll kết quả consumer để xác nhận hóa đơn được tạo.
5. Đọc object từ Cloud Storage test bucket, kiểm tra metadata/nội dung.
6. Xem log/trace trên project test khi có lỗi.

### Bước 4. Negative paths

Kiểm tra request thiếu field, duplicate idempotency key, message redelivery, quyền invoke không hợp lệ và dependency timeout trong môi trường kiểm soát. Kết quả phải rõ ràng và không tạo dữ liệu không thể dọn.

### Bước 5. Cleanup và báo cáo

Xóa dữ liệu run-scoped đã tạo, xác minh không còn orphan resource. Lưu report với commit SHA, build ID, run ID, project ID, kết quả assertion và cleanup. Nếu không dọn được, tạo incident/task rõ owner và tài nguyên cần xử lý.

## 15. Troubleshooting theo triệu chứng

**Could not find default credentials.** ADC chưa được thiết lập hoặc runner không có runtime identity đúng. Kiểm tra gcloud auth application-default local, service account của Cloud Build hoặc WIF cho CI ngoài.

**403 PERMISSION_DENIED.** Xác định identity thực tế, quyền trên resource, IAM conditions, org policy, Service Usage và API enablement. Không sửa bằng quyền Owner.

**404 resource not found.** Kiểm tra project, bucket toàn cục, full topic/subscription path, database, region và provisioning. Không tự tạo dưới production khi lookup thất bại.

**429 RESOURCE_EXHAUSTED.** Xem quota/region, concurrency của test suite và pipeline khác; hạn chế parallelism, dùng backoff trước khi nâng quota.

**Cloud SQL timeout.** Kiểm tra instance state, private/public IP, VPC egress, firewall, DNS, connector, database auth và số kết nối.

**Không nhận Pub/Sub event.** Kiểm tra subscription, publisher log, filter, ack state, permissions và có consumer khác tranh message không.

**Cloud Run 401/403.** Kiểm tra ID token audience, Invoker role, ingress và URL. Không mở endpoint public chỉ để test pass.

**Local pass, CI fail.** Kiểm tra khác biệt JDK, build tool, ADC, region, network, test env vars và execution identity.

**Test ngẫu nhiên fail khi chạy song song.** Kiểm tra object key, DB fixture, subscription, shared state và cleanup; ưu tiên cách ly thay vì thêm sleep.

**Cleanup thất bại.** Báo resource còn sót, kiểm tra quyền cleanup identity và TTL; không che test failure ban đầu.

## 16. Checklist triển khai và vận hành

### Project và security

- [ ] Project test tách biệt production/staging.
- [ ] Owner, billing, budget alerts, labels và retention rõ ràng.
- [ ] APIs được bật bởi provisioner.
- [ ] Test runner không có quyền ghi production.
- [ ] ADC/WIF, không cần static JSON key.
- [ ] IAM được cấp theo bucket/topic/subscription/secret khi có thể.
- [ ] Có preflight project/resource allowlist.

### Dữ liệu và test design

- [ ] Test dùng dữ liệu giả, không lộ dữ liệu nhạy cảm.
- [ ] Mỗi run có ID độc nhất.
- [ ] Object, row, subscription/schema được cô lập.
- [ ] Assertions xác nhận hành vi thật, không chỉ contextLoads.
- [ ] Có deadline, retry/backoff và idempotency cho async workflow.
- [ ] Test không phụ thuộc run trước hoặc thứ tự chạy.
- [ ] Unit/component tests vẫn là vòng phản hồi nhanh.

### CI và vận hành

- [ ] Cloud integration test có trigger và danh tính riêng.
- [ ] Có JUnit report, build ID, commit SHA và correlation IDs.
- [ ] Theo dõi quota, concurrency và chi phí.
- [ ] Cleanup sau test và cleanup orphan theo TTL.
- [ ] Cleanup failure có owner xử lý.
- [ ] Có quy trình tái tạo hạ tầng test từ IaC.

## 17. Tài liệu chính thức

- [Google Cloud project overview](https://cloud.google.com/resource-manager/docs/creating-managing-projects)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
- [ADC for local development](https://cloud.google.com/docs/authentication/set-up-adc-local-dev-environment)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Cloud Build service account](https://cloud.google.com/build/docs/cloud-build-service-account)
- [Cloud Billing budgets and alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [Quotas and limits](https://cloud.google.com/docs/quotas/view-manage)
- [Cloud Storage Java SDK](https://cloud.google.com/storage/docs/reference/libraries)
- [Cloud Storage consistency](https://cloud.google.com/storage/docs/consistency)
- [Pub/Sub emulator](https://cloud.google.com/pubsub/docs/emulator)
- [Pub/Sub subscriber guide](https://cloud.google.com/pubsub/docs/subscriber)
- [Cloud SQL Java connectors](https://cloud.google.com/sql/docs/mysql/connect-connectors)
- [Cloud Run authentication](https://cloud.google.com/run/docs/authenticating/overview)
- [Spring Boot testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)

Kiểm thử tích hợp trên project GCP dùng riêng cung cấp bằng chứng rằng ứng dụng Java/Spring hoạt động với dịch vụ cloud thật và vẫn giữ được ranh giới môi trường. Ngoài việc test pass, một quy trình tốt còn xác định đúng project và identity, cô lập dữ liệu, lưu bằng chứng, giới hạn chi phí/thời gian và thu hồi tài nguyên an toàn sau mỗi lần chạy.
