# Emulator Google Cloud và cấu hình endpoint theo từng dịch vụ

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua các thư viện Spring Cloud và client library tương ứng. Khi kiểm thử một ứng dụng Spring Boot dùng Pub/Sub, Firestore, Bigtable, Spanner hoặc Cloud Storage, không phải lúc nào cũng cần gọi dịch vụ production. Một số dịch vụ Google Cloud có emulator chạy cục bộ; các dịch vụ khác có test server hoặc công cụ giả lập do cộng đồng cung cấp.

Khác với một emulator dùng chung cho toàn bộ cloud, Google Cloud thường có **endpoint riêng cho từng dịch vụ**. Pub/Sub, Firestore, Bigtable và Spanner có emulator và cách cấu hình khác nhau. Cloud Storage không có emulator chính thức từ Google Cloud CLI; cần chọn một test server thay thế hoặc dùng bucket test trên cloud thật.

Bài học này giúp bạn:

- Phân biệt emulator chính thức, Firebase Emulator Suite và test server bên thứ ba.
- Chọn emulator phù hợp với API operation mà ứng dụng đang gọi.
- Cấu hình endpoint riêng cho Pub/Sub, Firestore, Datastore, Bigtable và Spanner.
- Kết nối Spring Boot qua Spring Framework on Google Cloud hoặc Google Cloud Java Client Libraries.
- Quản lý endpoint động bằng Testcontainers.
- Tách project ID, credentials và cấu hình emulator khỏi production.
- Hiểu giới hạn về IAM, TLS, consistency, index, transaction và performance.
- Thiết kế integration test cục bộ và smoke test trên Google Cloud thật.

## 2. Emulator Google Cloud là gì?

Emulator là một tiến trình mô phỏng một phần API của dịch vụ cloud. Ứng dụng vẫn gọi client library tương ứng, nhưng client được cấu hình để gửi request tới địa chỉ cục bộ thay vì endpoint production.

Ví dụ:

~~~mermaid
flowchart LR
    T[JUnit integration test] --> A[Spring Boot]
    A --> C[Google Cloud Java client]
    C --> R{Service endpoint}
    R --> P[Pub/Sub emulator]
    R --> F[Firestore emulator]
    R --> B[Bigtable emulator]
    R --> S[Spanner emulator]
    R --> G[Storage test server]
~~~

Emulator phù hợp để kiểm tra:

- Client được khởi tạo đúng project, host, port và credentials.
- Request/response mapping, serialization và xử lý lỗi.
- Luồng publish/subscribe, đọc/ghi document, row hoặc record.
- Spring auto-configuration và adapter của ứng dụng.
- Các thao tác API cơ bản được emulator hỗ trợ.

Emulator không phải bản sao đầy đủ của dịch vụ managed. Nó có thể bỏ qua IAM, TLS, quota, giới hạn kích thước, transaction concurrency, index hoặc behavior phân tán. Vì vậy, một integration test chạy xanh trên emulator chỉ chứng minh luồng API đã kiểm thử hoạt động trong phạm vi mô phỏng.

## 3. Bản đồ emulator và endpoint theo dịch vụ

| Dịch vụ | Công cụ local | Endpoint mặc định thường gặp | Cách client Java nhận endpoint |
|---|---|---|---|
| Pub/Sub | Google Cloud CLI Pub/Sub emulator | localhost:8085 | Spring property hoặc gRPC channel thủ công |
| Firestore Native mode | Firestore emulator / Firebase Local Emulator Suite | 127.0.0.1:8080 | FIRESTORE_EMULATOR_HOST hoặc Spring property |
| Firestore Datastore mode | Firestore emulator với datastore-mode | 127.0.0.1:8080 | DATASTORE_EMULATOR_HOST hoặc Spring Datastore property |
| Bigtable | Bigtable emulator | localhost:8086 | BIGTABLE_EMULATOR_HOST |
| Spanner | Spanner emulator | localhost:9010 gRPC, localhost:9020 REST | SPANNER_EMULATOR_HOST hoặc Spring property |
| Cloud Storage | Không có emulator chính thức của Google Cloud CLI | Tùy test server | StorageOptions.setHost hoặc endpoint tùy chỉnh |

Các port trên là mặc định phổ biến, không phải giá trị bắt buộc. Khi chạy emulator trong container, Testcontainers có thể map sang port động. Hãy đọc endpoint từ container thay vì giả định luôn là localhost và port mặc định.

## 4. Chọn đúng emulator trước khi viết test

Trước khi chọn công cụ, xác định:

1. Ứng dụng dùng API nào: Pub/Sub, Firestore Native, Firestore Datastore mode, Bigtable, Spanner hay Cloud Storage.
2. Client library nào tạo request: Spring starter, Google Cloud Java client hay Firebase SDK.
3. Operation nào thực sự được gọi: publish, pull, transaction, query, batch write, object upload, signed URL...
4. Test cần kiểm tra business flow, wiring, IAM, encryption, consistency hay performance.
5. Emulator có mô phỏng behavior cần kiểm tra hay chỉ hỗ trợ happy path.

Không dùng Firestore Native emulator để giả lập một API Datastore chỉ vì cả hai cùng dùng Firestore emulator. Cần bật đúng database mode. Tương tự, Firebase Storage Emulator là sản phẩm trong Firebase Local Emulator Suite; nó không phải emulator chính thức của Cloud Storage JSON API dành cho mọi server-side client.

## 5. Cài đặt Google Cloud CLI và lưu ý phiên bản Java

Các emulator chính thức được cài và khởi chạy bằng Google Cloud CLI. Ví dụ:

~~~bash
gcloud components update
gcloud components install pubsub-emulator
gcloud components install cloud-spanner-emulator
~~~

Một số emulator được tải tự động khi chạy lệnh start hoặc đi kèm component của Cloud SDK. Hãy kiểm tra hướng dẫn cài đặt của từng dịch vụ thay vì giả định mọi emulator đều có cùng cách cài.

**Lưu ý phiên bản tại ngày 24-11-2026:** Google Cloud CLI 592.0.0 phát hành ngày 03-11-2026 yêu cầu Java 25 trở lên cho Firestore emulator và Datastore emulator. Nếu môi trường phát triển chỉ cài Java 21, emulator có thể không khởi động với bản CLI mới nhất. Có hai hướng:

- Nâng JRE dùng để chạy emulator lên Java 25.
- Pin một phiên bản Cloud CLI/emulator cũ đã được kiểm thử và chấp nhận trong dự án.

Điều kiện Java của emulator không đồng nghĩa ứng dụng Spring Boot phải đổi JDK. Có thể chạy ứng dụng bằng JDK mà dự án hỗ trợ và chạy emulator trong container có JRE phù hợp.

## 6. Khởi chạy emulator từ Google Cloud CLI

### 6.1. Pub/Sub

Khởi chạy:

~~~bash
gcloud beta emulators pubsub start --project=local-test-project --host-port=0.0.0.0:8085
~~~

Emulator thường nghe trên port 8085. Có thể lấy địa chỉ do emulator chọn bằng:

~~~bash
gcloud beta emulators pubsub env-init
~~~

Tạo topic, subscription và publish/receive đều diễn ra trong phiên emulator. Resource chỉ tồn tại trong vòng đời của tiến trình emulator.

### 6.2. Firestore Native mode

Khởi chạy:

~~~bash
gcloud emulators firestore start --host-port=0.0.0.0:8080
~~~

Mặc định Firestore emulator dùng host 127.0.0.1 và port 8080. Có thể thay bằng host/port khác để tránh xung đột với ứng dụng Spring Boot hoặc một emulator khác.

Nếu cần kiểm thử Firestore Enterprise edition, CLI hỗ trợ tùy chọn edition:

~~~bash
gcloud emulators firestore start --edition=enterprise --host-port=0.0.0.0:8080
~~~

### 6.3. Firestore in Datastore mode

Dùng cùng Firestore emulator nhưng bật database mode:

~~~bash
gcloud emulators firestore start --database-mode=datastore-mode --host-port=0.0.0.0:8080
~~~

Client Datastore kết nối qua DATASTORE_EMULATOR_HOST. Đây là cách nên dùng khi kiểm thử ứng dụng đang dùng Firestore in Datastore mode; không nhầm với emulator Datastore legacy.

### 6.4. Bigtable

Khởi chạy:

~~~bash
gcloud beta emulators bigtable start --host-port=0.0.0.0:8086
~~~

Bigtable emulator mặc định chọn localhost:8086. Nếu chạy nhiều emulator hoặc container song song, chỉ định host/port rõ ràng để tránh xung đột.

### 6.5. Spanner

Khởi chạy:

~~~bash
gcloud emulators spanner start
~~~

Spanner emulator có hai endpoint:

- localhost:9010 cho gRPC.
- localhost:9020 cho REST.

Java Cloud Spanner client library sử dụng gRPC endpoint 9010 khi biến SPANNER_EMULATOR_HOST được đặt.

## 7. Biến môi trường và quy tắc endpoint

Các client library sử dụng tên biến môi trường riêng:

| Biến môi trường | Giá trị ví dụ | Ghi chú |
|---|---|---|
| PUBSUB_EMULATOR_HOST | localhost:8085 | Pub/Sub Java cần channel configuration tường minh |
| PUBSUB_PROJECT_ID | local-test-project | Project ID giả lập tùy chọn cho Pub/Sub |
| FIRESTORE_EMULATOR_HOST | localhost:8080 | Firestore server client libraries tự nhận diện |
| DATASTORE_EMULATOR_HOST | localhost:8080 | Datastore client libraries tự nhận diện |
| BIGTABLE_EMULATOR_HOST | localhost:8086 | Bigtable client libraries tự nhận diện |
| SPANNER_EMULATOR_HOST | localhost:9010 | Spanner client libraries tự nhận diện |
| STORAGE_EMULATOR_HOST | localhost:4443 | Không phải cơ chế emulator chính thức của Google Cloud Java SDK; dùng endpoint tùy chỉnh cho Java |

Với gRPC, nhiều biến chỉ nhận host:port, không có scheme. Ví dụ localhost:9010, không phải http://localhost:9010. Với HTTP API như test server Cloud Storage, endpoint thường là URL có scheme, ví dụ http://localhost:4443.

Nếu emulator và ứng dụng chạy trên hai container khác nhau, localhost trong container ứng dụng trỏ về chính container ứng dụng. Hãy dùng Docker network alias hoặc endpoint mà Testcontainers trả về. Không đưa host-mapped endpoint của máy chủ vào container khác nếu container đó không thể định tuyến tới host.

## 8. Cấu hình Pub/Sub trong Spring Boot

Spring Framework on Google Cloud cung cấp starter Pub/Sub:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
</dependency>
~~~

Dùng Spring Framework on Google Cloud BOM để quản lý version. Trong profile emulator:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: local-test-project
      pubsub:
        emulator-host: localhost:8085
~~~

Khi spring.cloud.gcp.pubsub.emulator-host được đặt, auto-configuration tạo transport channel plaintext và bỏ credentials để client gọi emulator. Nếu dùng Spring Cloud Stream Pub/Sub binder, cũng cấu hình host/port bằng property này.

### 8.1. Pub/Sub Java client thuần

Có một khác biệt quan trọng: Google Pub/Sub emulator hướng dẫn đặt PUBSUB_EMULATOR_HOST, nhưng Java Cloud Client Library không tự chuyển endpoint chỉ nhờ biến này. Code cần tạo plaintext gRPC channel và NoCredentialsProvider:

~~~java
import com.google.api.gax.core.NoCredentialsProvider;
import com.google.api.gax.grpc.GrpcTransportChannel;
import com.google.api.gax.rpc.FixedTransportChannelProvider;
import com.google.cloud.pubsub.v1.TopicAdminClient;
import com.google.cloud.pubsub.v1.TopicAdminSettings;
import com.google.pubsub.v1.TopicName;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

String host = System.getenv("PUBSUB_EMULATOR_HOST");
if (host == null || host.isBlank()) {
    throw new IllegalStateException("PUBSUB_EMULATOR_HOST is required");
}

ManagedChannel channel = ManagedChannelBuilder.forTarget(host)
        .usePlaintext()
        .build();

var transport = FixedTransportChannelProvider.create(
        GrpcTransportChannel.create(channel));

var credentials = NoCredentialsProvider.create();

TopicAdminSettings settings = TopicAdminSettings.newBuilder()
        .setTransportChannelProvider(transport)
        .setCredentialsProvider(credentials)
        .build();

try (TopicAdminClient client = TopicAdminClient.create(settings)) {
    TopicName topicName = TopicName.of("local-test-project", "documents");
    client.createTopic(topicName);
} finally {
    channel.shutdown();
}
~~~

Khi tạo Publisher, Subscriber hoặc SubscriptionAdminClient, truyền cùng transport và credentials provider. Trong ứng dụng Spring, ưu tiên để Spring starter quản lý channel và lifecycle nếu đã dùng auto-configuration.

## 9. Cấu hình Firestore trong Spring Boot

Spring Framework on Google Cloud cung cấp starter Spring Data Firestore:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-firestore</artifactId>
</dependency>
~~~

Cấu hình profile emulator:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: local-test-project
      firestore:
        emulator:
          enabled: true
        host-port: localhost:8080
~~~

spring.cloud.gcp.firestore.emulator.enabled bật chế độ emulator; host-port trỏ tới host/port của Firestore emulator. Với Spring Cloud GCP, đây là cách cấu hình rõ ràng, dễ tách khỏi production.

### 9.1. Firestore Java client

Firestore server client libraries cũng nhận diện FIRESTORE_EMULATOR_HOST:

~~~java
import com.google.auth.oauth2.NoCredentials;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;

Firestore firestore = FirestoreOptions.getDefaultInstance()
        .toBuilder()
        .setProjectId("local-test-project")
        .setHost("localhost:8080")
        .setCredentials(NoCredentials.getInstance())
        .build()
        .getService();
~~~

Đặt endpoint và NoCredentials tường minh trong test giúp tránh client dùng nhầm Application Default Credentials. Nếu dựa vào FIRESTORE_EMULATOR_HOST, đặt biến trước khi tạo client.

Firestore emulator mặc định xóa dữ liệu khi tiến trình dừng. Có REST endpoint để xóa dữ liệu theo project/database giữa các test; cần chờ phản hồi xóa hoàn tất trước khi tiếp tục.

## 10. Cấu hình Datastore và Firestore Datastore mode

Spring Framework on Google Cloud có starter Datastore:

~~~xml
<dependency>
    <group>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-datastore</artifactId>
</dependency>
~~~

Nếu emulator đã được khởi chạy riêng, đặt host:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: local-test-project
      datastore:
        host: localhost:8080
~~~

Spring Framework on Google Cloud cũng có thể tự khởi chạy Datastore emulator trong integration test:

~~~yaml
spring:
  cloud:
    gcp:
      datastore:
        emulator:
          enabled: true
          port: 8081
          firestore-in-datastore-mode: true
~~~

Khi auto-start emulator được bật, host property bị bỏ qua vì auto-configuration tự kết nối tới emulator do Spring quản lý. Dữ liệu có thể được lưu trên đĩa bằng các property store-on-disk và data-dir nếu emulator mode/version hỗ trợ.

Nếu đang kiểm thử Firestore in Datastore mode, nên dùng Firestore emulator với --database-mode=datastore-mode. Legacy Datastore emulator có một số behavior khác production, ví dụ eventual consistency mặc định và giới hạn truy vấn. Không dùng một emulator legacy để kết luận Firestore Datastore mode đã được kiểm thử đầy đủ.

## 11. Cấu hình Bigtable

Google Cloud Bigtable Java client library nhận diện BIGTABLE_EMULATOR_HOST. Ví dụ:

~~~powershell
$env:BIGTABLE_EMULATOR_HOST = "localhost:8086"
~~~

Khi ứng dụng tạo Bigtable client, library dùng endpoint emulator. Có thể cấu hình trực tiếp bằng builder:

~~~java
import com.google.cloud.bigtable.data.v2.BigtableDataClient;
import com.google.cloud.bigtable.data.v2.BigtableDataSettings;

BigtableDataSettings settings =
        BigtableDataSettings.newBuilderForEmulator("localhost", 8086)
                .setProjectId("local-test-project")
                .setInstanceId("local-instance")
                .build();

BigtableDataClient client = BigtableDataClient.create(settings);
~~~

Bigtable emulator không có administrative API để tạo hoặc quản lý instance/cluster. Test có thể dùng tên project và instance tùy ý, tạo table rồi đọc/ghi row. Không cần tạo Bigtable instance trên Google Cloud chỉ để chạy emulator test.

Spring Framework on Google Cloud không cung cấp cùng kiểu auto-configuration Bigtable như Pub/Sub, Firestore và Spanner trong các starter được đề cập ở bài này. Với Bigtable, thường cấu hình Google Cloud Java client trực tiếp trong một @Configuration class và inject client vào adapter.

## 12. Cấu hình Spanner

Spring Framework on Google Cloud có starter Spring Data Spanner:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-spanner</artifactId>
</dependency>
~~~

Cấu hình emulator:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: local-test-project
      spanner:
        instance-id: local-instance
        database: local-database
        emulator:
          enabled: true
        emulator-host: localhost:9010
~~~

spring.cloud.gcp.spanner.emulator.enabled bật chế độ emulator. emulator-host trỏ tới gRPC endpoint. Endpoint REST 9020 dành cho REST client hoặc gcloud CLI; Java Spanner client library dùng gRPC 9010.

### 12.1. Spanner Java client

Có thể dùng SPANNER_EMULATOR_HOST hoặc cấu hình trực tiếp:

~~~java
import com.google.auth.oauth2.NoCredentials;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;

SpannerOptions options = SpannerOptions.newBuilder()
        .setProjectId("local-test-project")
        .setEmulatorHost("localhost:9010")
        .setCredentials(NoCredentials.getInstance())
        .build();

Spanner spanner = options.getService();
~~~

Spanner emulator hỗ trợ GoogleSQL và PostgreSQL dialect. Dữ liệu, schema và cấu hình mất khi emulator khởi động lại. Test nên tạo instance/database/table riêng trong mỗi run hoặc có script khởi tạo schema lặp lại được.

## 13. Cloud Storage: chọn test server thay thế

Google Cloud CLI hiện không cung cấp emulator chính thức cho Cloud Storage. Có một số lựa chọn:

| Công cụ | Phạm vi | Cách dùng phù hợp |
|---|---|---|
| fake-gcs-server | Server bên thứ ba giả lập một phần Cloud Storage JSON API | Kiểm thử upload/download/list và adapter |
| storage-testbench | Testbench của Googleapis cho Cloud Storage client libraries | Kiểm thử hành vi client và các tình huống request/error chuyên biệt |
| Firebase Storage Emulator | Emulator thuộc Firebase Local Emulator Suite | Kiểm thử ứng dụng dùng Firebase Storage SDK và Firebase rules |
| Bucket test trên Google Cloud | Dịch vụ Cloud Storage thật | Smoke test IAM, signed URL, lifecycle, versioning và behavior production |

Không gọi fake-gcs-server hoặc Firebase Storage Emulator là emulator chính thức của Google Cloud Storage. Mỗi công cụ có API coverage và semantics riêng.

### 13.1. Chạy fake-gcs-server

Ví dụ Docker:

~~~bash
docker run --rm -p 4443:4443 fsouza/fake-gcs-server -scheme http
~~~

Server mặc định dùng HTTPS ở port 4443; tùy chọn -scheme http bật HTTP để test local đơn giản. Pin image version/digest đã được kiểm thử trong CI, không phụ thuộc tag mutable.

### 13.2. Cấu hình Cloud Storage Java client

Cloud Storage Java client hỗ trợ custom endpoint qua StorageOptions.Builder.setHost:

~~~java
import com.google.auth.oauth2.NoCredentials;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

Storage storage = StorageOptions.newBuilder()
        .setProjectId("local-test-project")
        .setHost("http://localhost:4443")
        .setCredentials(NoCredentials.getInstance())
        .build()
        .getService();
~~~

Với server chạy trong container khác, thay localhost bằng hostname trên Docker network hoặc endpoint do Testcontainers trả về. Không giả định biến STORAGE_EMULATOR_HOST được Google Cloud Java Storage client xử lý tự động như một số client Go.

## 14. Cấu hình endpoint theo profile Spring

Không ghi endpoint emulator trong application.yml dùng chung cho production. Tạo profile local hoặc integration-test:

~~~yaml
# application-integration-test.yml
spring:
  config:
    activate:
      on-profile: integration-test
  cloud:
    gcp:
      project-id: local-test-project
      pubsub:
        emulator-host: localhost:8085
      firestore:
        emulator:
          enabled: true
        host-port: localhost:8080
      spanner:
        instance-id: local-instance
        database: local-database
        emulator:
          enabled: true
        emulator-host: localhost:9010
~~~

Datastore, Bigtable và Storage có thể cần cấu hình riêng theo client/adapter. Nếu Spring Cloud GCP auto-start Datastore emulator, bật property emulator.enabled và đặt port/data-dir phù hợp. Với Bigtable, tạo client từ BIGTABLE_EMULATOR_HOST hoặc BigtableDataSettings.newBuilderForEmulator. Với Storage test server, tạo Storage bean bằng setHost.

Trong production, không nạp profile integration-test. Không để endpoint local có thể được override từ một biến môi trường không được kiểm soát.

## 15. Testcontainers GCloud module

Testcontainers for Java có module GCloud để chạy các emulator BigQuery, Bigtable, Datastore, Firestore, Spanner và Pub/Sub. Module hiện được đánh dấu **INCUBATING**, vì vậy API/package có thể thay đổi giữa các bản.

Thêm dependency test:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-gcloud</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>
~~~

Pin Testcontainers version theo BOM của dự án. Với Google Cloud CLI image, pin tag/digest đã được xác minh. Firestore và Datastore emulator trong Cloud CLI 592 yêu cầu Java 25; image phải có JRE tương ứng.

### 15.1. Ví dụ Pub/Sub emulator container

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.gcloud.PubSubEmulatorContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class PubSubIntegrationTest {
    @Container
    static final PubSubEmulatorContainer PUBSUB =
            new PubSubEmulatorContainer(
                    DockerImageName.parse(
                            System.getProperty(
                                    "gcloud.emulator.image",
                                    "gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators")));

    @DynamicPropertySource
    static void emulatorProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.gcp.pubsub.emulator-host",
                PUBSUB::getEmulatorEndpoint);
        registry.add(
                "spring.cloud.gcp.pubsub.project-id",
                () -> "local-test-project");
    }

    @Test
    void applicationCanUsePubSubEmulator() {
        // Exercise the application's Pub/Sub adapter or PubSubTemplate.
    }
}
~~~

Đặt system property gcloud.emulator.image trong build để pin image theo tag/digest đã kiểm thử; giá trị mặc định minh họa dùng tag emulators. @Testcontainers/@Container giúp JUnit khởi động và dừng container theo lifecycle của test class. Nếu dùng Spring context cache, cần bảo đảm container sống lâu hơn ApplicationContext đang giữ client.

Ví dụ với FirestoreEmulatorContainer, Testcontainers trả endpoint qua getEmulatorEndpoint(); cấu hình FirestoreOptions.setHost hoặc Spring property host-port bằng giá trị đó. SpannerEmulatorContainer cung cấp gRPC endpoint để gán cho SpannerOptions.setEmulatorHost. BigtableEmulatorContainer có host/port để tạo BigtableDataSettings.newBuilderForEmulator.

## 16. Project ID, credentials và ranh giới bảo mật

Emulator thường không thực thi đầy đủ IAM hoặc authentication production. Vì vậy:

- Dùng project ID giả lập riêng, ví dụ local-test-project.
- Dùng NoCredentials hoặc credentials provider không xác thực theo yêu cầu của emulator.
- Không dùng service account production JSON trong test local.
- Không cho test container truy cập ADC của developer nếu không cần.
- Không dùng endpoint emulator trong production profile.
- Không truyền dữ liệu production hoặc secret thật vào emulator fixture.
- Đảm bảo host/port emulator chỉ truy cập từ máy hoặc Docker network dành cho test.

Đặc biệt với Pub/Sub Java, cấu hình plaintext channel và NoCredentialsProvider là một phần của emulator setup. Spanner emulator không hỗ trợ authentication, IAM, permission hoặc TLS. Bigtable emulator cũng không hỗ trợ secure connection. Các test này không thể xác minh IAM role, service account permissions, TLS certificate hoặc VPC Service Controls.

## 17. Giới hạn và khác biệt so với Google Cloud thật

| Dịch vụ | Giới hạn đáng chú ý | Cần test trên cloud thật khi |
|---|---|---|
| Pub/Sub | Không hỗ trợ IAM operations; message retention cấu hình được không hỗ trợ; subscription không expire; một số RPC/SMT/BigQuery subscription còn giới hạn | Cần IAM, retention, schema protobuf, BigQuery subscription, seek hoặc retry semantics production |
| Firestore | Transaction concurrency khác production; composite index không được kiểm tra; không thực thi đầy đủ limits; search stage chưa hỗ trợ | Cần xác minh transaction contention, index deployment, query limit, text search hoặc production limits |
| Datastore mode | Legacy emulator có behavior khác Firestore Datastore mode; query operators/aggregation và consistency có giới hạn tùy chế độ | Cần kiểm tra consistency, transaction, query/index và behavior đúng database mode |
| Bigtable | In-memory; không có admin API tạo/quản lý instance/cluster; không hỗ trợ TLS | Cần kiểm tra instance topology, IAM, TLS, replication, performance và cluster behavior |
| Spanner | In-memory; không hỗ trợ TLS, auth, IAM, permission, audit/monitoring; transaction/schema change khóa database rộng hơn production | Cần xác minh IAM, query plan, transaction concurrency, partitionability, latency và performance |
| Cloud Storage test server | API coverage và behavior tùy dự án bên thứ ba; không phản ánh IAM, retention, lifecycle, versioning đầy đủ | Cần xác minh signed URL, IAM, retention, lifecycle, versioning, object holds và consistency |

### 17.1. Pub/Sub

Pub/Sub emulator hỗ trợ publish, pull/push delivery, ordering, replay, dead-letter forwarding, retry policy, Avro schema và filtering. Các giới hạn gồm IAM operations không được hỗ trợ; retention cấu hình không hoạt động và message được giữ trong phiên emulator; subscription expiration không được mô phỏng; một số RPC như UpdateTopic/UpdateSnapshot chưa hỗ trợ; BigQuery subscription có thể tạo nhưng không gửi message tới BigQuery.

### 17.2. Firestore

Firestore emulator lưu dữ liệu trong bộ nhớ và xóa dữ liệu khi dừng. Transaction sử dụng cơ chế khóa đơn giản, không mô phỏng đầy đủ concurrency mode production. Emulator không kiểm tra composite indexes và không thực thi mọi production limits. Vì vậy, query có thể chạy trong emulator nhưng lỗi trên Firestore thật do thiếu index.

### 17.3. Bigtable và Spanner

Bigtable emulator không có admin API cho instance/cluster; có thể tạo table và đọc/ghi row bằng tên instance/project tùy ý. Spanner emulator hỗ trợ GoogleSQL và PostgreSQL dialect, nhưng không hỗ trợ TLS, IAM, authentication và monitoring/audit tools. Performance và scalability của emulator không thể đại diện production.

## 18. Quản lý dữ liệu, cleanup và CI

Emulator có vòng đời dữ liệu khác nhau:

- Pub/Sub: resource và message tồn tại trong phiên emulator.
- Firestore Native mode: dữ liệu mất khi emulator dừng; có REST endpoint để xóa database giữa test.
- Bigtable: dữ liệu trong memory, mất khi emulator dừng.
- Spanner: dữ liệu, schema và config mất khi emulator restart.
- Datastore: khả năng lưu dữ liệu phụ thuộc emulator mode và cấu hình store-on-disk.
- fake-gcs-server: persistence phụ thuộc backend/volume mà server được cấu hình.

Các nguyên tắc:

1. Tạo topic, subscription, collection, table, database và bucket với tên riêng cho test run.
2. Seed schema/data bằng script idempotent.
3. Xóa dữ liệu hoặc dùng project/namespace riêng sau mỗi test suite.
4. Không để test phụ thuộc thứ tự chạy.
5. Dùng port động và endpoint từ Testcontainers.
6. Pin Cloud CLI image, Testcontainers module và client library.
7. Lưu container logs khi test thất bại.
8. Không để credential production trong CI job chạy emulator.

Pipeline có thể chia thành unit test, integration test với emulator và smoke test trên Google Cloud account test. Smoke test nên giới hạn project, quota, service account và resource; dọn tài nguyên sau khi chạy.

## 19. Troubleshooting và bài tập thực hành

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Client vẫn gọi production endpoint | Biến môi trường/property chưa được nạp trước khi tạo client | Kiểm tra profile, host/port và thời điểm khởi tạo bean |
| Pub/Sub Java báo authentication/channel error | Chỉ đặt PUBSUB_EMULATOR_HOST mà chưa tạo plaintext channel | Dùng Spring emulator-host hoặc channel provider + NoCredentialsProvider |
| Firestore không kết nối | Thiếu FIRESTORE_EMULATOR_HOST hoặc host-port sai | Xác minh endpoint và database mode |
| Firestore query pass local nhưng fail cloud | Composite index chưa được tạo hoặc limit khác | Deploy index và chạy smoke test thật |
| Spanner client báo TLS/auth | Emulator endpoint hoặc client credentials chưa đúng | Dùng SPANNER_EMULATOR_HOST, emulator mode và NoCredentials |
| Bigtable admin operation không hoạt động | Emulator không cung cấp instance/cluster admin APIs | Dùng project/instance ID giả lập và chỉ tạo table/data |
| Emulator container chạy nhưng app container không kết nối | Dùng localhost từ container khác | Dùng Docker network alias hoặc endpoint Testcontainers |
| Firestore/Datastore emulator không khởi động | Cloud CLI 592 cần Java 25 | Nâng JRE emulator hoặc pin CLI cũ đã được kiểm thử |
| Storage test server trả 404 | Endpoint scheme/path hoặc API behavior không khớp | Kiểm tra setHost, scheme, port và loại test server |
| Test pass riêng nhưng fail cả suite | Shared emulator state hoặc tên resource trùng | Cô lập project/resource và cleanup |

### Bài tập A — Pub/Sub

Khởi chạy emulator, tạo topic/subscription, publish message và pull message. Chạy cùng test qua Spring Pub/Sub starter bằng emulator-host, sau đó chạy client Java thuần với plaintext channel và NoCredentialsProvider.

### Bài tập B — Firestore

Khởi chạy Firestore emulator, cấu hình Spring Data Firestore, ghi và truy vấn document. Tạo một truy vấn cần composite index và so sánh hành vi emulator với database test thật.

### Bài tập C — Datastore mode

Khởi chạy Firestore emulator với --database-mode=datastore-mode. Cấu hình DATASTORE_EMULATOR_HOST và kiểm thử một repository Spring Data Datastore. Xác nhận test đang dùng đúng mode.

### Bài tập D — Bigtable

Khởi chạy Bigtable emulator, tạo table/family, ghi một row và đọc lại cell. Ghi rõ vì sao bài test này không kiểm tra việc tạo instance/cluster hoặc IAM.

### Bài tập E — Spanner

Khởi chạy Spanner emulator, tạo instance/database/table, insert và query dữ liệu bằng SpannerTemplate hoặc DatabaseClient. Bổ sung smoke test để kiểm tra IAM và transaction behavior trên account test.

### Bài tập F — Cloud Storage

Chạy fake-gcs-server, cấu hình StorageOptions.setHost và kiểm thử upload/download. Sau đó chạy một smoke test trên bucket test thật để xác minh IAM, signed URL và lifecycle.

### Câu hỏi tự kiểm tra

1. **Vì sao Google Cloud dùng endpoint theo từng dịch vụ?** Mỗi client library gọi API endpoint riêng và emulator có host/port/protocol khác nhau.
2. **Pub/Sub Java có tự dùng PUBSUB_EMULATOR_HOST không?** Không; cần cấu hình channel plaintext và NoCredentialsProvider hoặc dùng Spring emulator-host.
3. **Firestore server client dùng biến nào?** FIRESTORE_EMULATOR_HOST.
4. **Datastore mode dùng biến nào?** DATASTORE_EMULATOR_HOST; có thể dùng Firestore emulator ở datastore-mode.
5. **Bigtable emulator dùng biến nào?** BIGTABLE_EMULATOR_HOST.
6. **Spanner Java emulator endpoint mặc định là gì?** localhost:9010 cho gRPC; 9020 cho REST.
7. **Cloud Storage có emulator chính thức từ gcloud CLI không?** Không; cần test server thay thế hoặc bucket test thật.
8. **Testcontainers GCloud module hỗ trợ những emulator nào?** BigQuery, Bigtable, Datastore, Firestore, Spanner và Pub/Sub; module đang incubating.
9. **Vì sao cần Java 25 cho Firestore/Datastore emulator mới nhất?** Google Cloud CLI 592.0.0 yêu cầu Java 25 cho các emulator này.
10. **Firestore emulator có kiểm tra composite index production không?** Không; phải kiểm thử index trên Firestore thật.
11. **Spanner emulator có xác minh IAM/TLS không?** Không; cần smoke test trên cloud thật.
12. **Vì sao không dùng localhost khi app chạy trong container khác?** localhost trỏ tới chính container ứng dụng, không phải emulator container.

## 20. Tổng kết

Emulator giúp kiểm thử tích hợp Google Cloud nhanh và có thể lặp lại, nhưng endpoint và behavior phải được cấu hình theo từng dịch vụ. Pub/Sub dùng PUBSUB_EMULATOR_HOST hoặc Spring emulator-host; Firestore dùng FIRESTORE_EMULATOR_HOST hoặc host-port; Datastore dùng DATASTORE_EMULATOR_HOST; Bigtable dùng BIGTABLE_EMULATOR_HOST; Spanner dùng SPANNER_EMULATOR_HOST với gRPC port 9010. Cloud Storage không có emulator chính thức của Google Cloud CLI, nên phải chọn test server thay thế hoặc bucket test thật.

Trong Spring Boot, Spring Framework on Google Cloud cung cấp property riêng cho Pub/Sub, Firestore, Datastore và Spanner. Bigtable thường dùng Google Cloud Java client trực tiếp; Storage có thể dùng StorageOptions.setHost khi kết nối test server. Testcontainers GCloud module giúp quản lý lifecycle emulator, nhưng module đang incubating và image cần được pin theo phiên bản phù hợp.

Không xem emulator là bằng chứng cho IAM, TLS, quota, consistency, index, transaction concurrency hoặc performance production. Kết hợp unit test, emulator integration test và smoke test trên Google Cloud account test để kiểm tra cả wiring lẫn những behavior mà emulator không mô phỏng.

### Tài liệu tham khảo chính thức

- [Google Cloud — Pub/Sub emulator](https://docs.cloud.google.com/pubsub/docs/emulator)
- [Google Cloud — Firestore emulator](https://docs.cloud.google.com/firestore/native/docs/emulator)
- [Google Cloud — Firestore in Datastore mode emulator](https://docs.cloud.google.com/datastore/docs/emulator)
- [Google Cloud — Bigtable emulator](https://docs.cloud.google.com/bigtable/docs/emulator)
- [Google Cloud — Spanner emulator](https://docs.cloud.google.com/spanner/docs/emulator)
- [Google Cloud — Java client library endpoints](https://docs.cloud.google.com/java/docs/endpoints)
- [Google Cloud — Cloud Storage request endpoints](https://docs.cloud.google.com/storage/docs/request-endpoints)
- [Google Cloud CLI — Release notes](https://docs.cloud.google.com/sdk/docs/release-notes)
- [Spring Framework on Google Cloud — Reference](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/)
- [Testcontainers for Java — GCloud module](https://java.testcontainers.org/modules/gcloud/)
- [fake-gcs-server — project documentation](https://github.com/fsouza/fake-gcs-server)
- [Googleapis — Cloud Storage testbench](https://github.com/googleapis/storage-testbench)
