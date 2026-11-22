# Emulators cho Pub/Sub, Firestore, Bigtable và Spanner

Ứng dụng trên Google Cloud thường vừa phát sự kiện qua Pub/Sub, vừa lưu dữ liệu trong Firestore, Bigtable hoặc Spanner. Nếu mỗi lần chạy kiểm thử đều cần kết nối dịch vụ thật, đội phát triển sẽ phụ thuộc vào mạng, IAM, quota, trạng thái tài nguyên dùng chung và chi phí. Một test có thể thất bại vì project tạm thời không truy cập được, hoặc tệ hơn, ghi dữ liệu thử nghiệm vào môi trường production.

**Emulator** là tiến trình mô phỏng một phần API và hành vi của dịch vụ Google Cloud ngay trên máy phát triển hoặc trong môi trường CI. Các emulator cho Pub/Sub, Firestore, Bigtable và Spanner cho phép ứng dụng Java/Spring chạy những bài test tích hợp cơ bản mà không cần tạo tài nguyên cloud thật. Chúng đặc biệt hữu ích để kiểm tra mapping dữ liệu, câu lệnh truy vấn, quá trình publish/consume message và logic giao dịch.

Emulator không phải phiên bản thu nhỏ hoàn toàn giống production. Một số giới hạn về IAM, chỉ mục, transaction, hiệu năng, quota hoặc tính năng nâng cao không được mô phỏng. Vì vậy, kiểm thử tốt thường kết hợp unit test, emulator integration test và một lượng test có kiểm soát trên dịch vụ thật.

Trong module CLOUD_PROVIDERS_GCP, chủ đề này nối việc phát triển Java/Spring với các dịch vụ dữ liệu và messaging của GCP, cùng kiến thức về project, IAM, CI/CD, vận hành và độ tin cậy. Bài học tập trung vào cách khởi chạy, kết nối và tổ chức kiểm thử qua bốn emulator, đồng thời chỉ ra những hành vi vẫn phải xác minh trên môi trường Google Cloud thực tế.

Sau bài học này, bạn có thể:

- Chọn emulator phù hợp với loại test và hiểu giới hạn của từng dịch vụ.
- Chạy Pub/Sub, Firestore, Bigtable và Spanner emulator bằng Google Cloud CLI.
- Kết nối Java Cloud Client Libraries bằng biến môi trường hoặc cấu hình gRPC.
- Tạo dữ liệu thử nghiệm, chạy thao tác đọc/ghi và xác nhận kết quả.
- Thiết kế test độc lập, dễ lặp lại và phù hợp với JUnit/Spring Boot.
- Chạy emulator trong Docker hoặc CI, kiểm soát port, trạng thái và vòng đời.
- Phân biệt lỗi của emulator với những vấn đề chỉ xuất hiện trong production.

## 1. Emulator nằm ở đâu trong chiến lược kiểm thử?

Có ba cấp kiểm thử thường phối hợp với nhau:

| Cấp | Phụ thuộc | Giá trị chính | Hạn chế |
|---|---|---|---|
| Unit test với mock/fake | Không cần mạng hoặc server | Nhanh, kiểm tra nhánh logic và xử lý lỗi cụ thể | Không kiểm tra việc client thực sự gọi API và giải mã response |
| Integration test với emulator | Có tiến trình emulator trên localhost hoặc mạng test | Kiểm tra tương tác với API và dữ liệu thử nghiệm gần với dịch vụ thật | Không bảo đảm hành vi, quota và bảo mật giống production |
| Integration/E2E trên GCP thật | Project, API, IAM, network và tài nguyên thật | Kiểm tra integration, chính sách bảo mật, tính năng và giới hạn thật | Chậm hơn, tốn chi phí và cần quản lý tài nguyên |

Emulator phù hợp nhất với các câu hỏi như: ứng dụng có tạo đúng document không, consumer có xử lý message và acknowledge không, row key Bigtable có được ghi đúng không, transaction Spanner có cập nhật nhiều bản ghi như mong đợi không. Những câu hỏi về IAM, latency thực tế, khả năng mở rộng hoặc quy tắc index production phải được kiểm tra bằng cách khác.

~~~mermaid
flowchart LR
    A[Test runner JUnit / Spring] --> B[Ứng dụng và Cloud Client Libraries]
    B --> P[Pub/Sub emulator]
    B --> F[Firestore emulator]
    B --> T[Bigtable emulator]
    B --> S[Spanner emulator]
    C[CI pipeline] --> A
    D[Staging GCP thật] --> E[Test IAM / quota / indexing / performance]
~~~

Tất cả emulators đều chạy trên môi trường do bạn quản lý, không tự tạo project hay billing account thật. Dùng một project ID thử nghiệm như local-demo-project để đặt tên tài nguyên; đây là namespace logic trong emulator, không cần tồn tại trên Google Cloud, ngoại trừ các thao tác CLI hoặc SDK đặc thù đã nêu riêng.

## 2. So sánh nhanh bốn emulator

| Dịch vụ | Lệnh khởi chạy | Endpoint mặc định | Biến môi trường | Điểm cần nhớ |
|---|---|---|---|---|
| Pub/Sub | gcloud beta emulators pubsub start | Port 8085 (thường là IPv6 localhost) | PUBSUB_EMULATOR_HOST | **Java cần cấu hình gRPC channel và no-credentials trong code** |
| Firestore | gcloud emulators firestore start | 127.0.0.1:8080 | FIRESTORE_EMULATOR_HOST | Java server library tự nhận biến môi trường |
| Bigtable | gcloud beta emulators bigtable start | localhost:8086 | BIGTABLE_EMULATOR_HOST | Java client tự nhận; không có instance/cluster admin API |
| Spanner | gcloud emulators spanner start | gRPC 9010; REST 9020 | SPANNER_EMULATOR_HOST | Java client tự nhận; gcloud CLI dùng override REST endpoint |

Khi dùng các ví dụ bên dưới, chỉ định host-port rõ ràng để tránh xung đột và giúp CI dễ kết nối. Giá trị localhost là địa chỉ nhìn từ tiến trình ứng dụng. Nếu ứng dụng chạy trong container khác, localhost trỏ tới chính container ứng dụng, không trỏ tới emulator container.

### Chuẩn bị môi trường

Bạn cần Google Cloud CLI có quyền cài components, JDK phù hợp với phiên bản emulator và phiên bản Java Cloud Client Libraries đang dùng, cùng Maven hoặc Gradle để chạy test. Firestore emulator bản mới có yêu cầu Java runtime riêng; hãy kiểm tra ghi chú phiên bản Google Cloud CLI và cài JDK được hỗ trợ. Google Cloud CLI cung cấp gcloud commands, còn Java app kết nối qua Cloud Client Libraries.

Ví dụ cài các thành phần:

~~~bash
gcloud components update
gcloud components install pubsub-emulator
gcloud components install cloud-spanner-emulator
~~~

Bigtable emulator thường được tải khi gọi lệnh start lần đầu nếu component chưa có. Firestore emulator đi kèm bản cập nhật CLI thích hợp. Nếu cài CLI bằng package manager khiến lệnh components bị vô hiệu hóa, hãy dùng cách cài và cập nhật được tài liệu Google Cloud hỗ trợ cho nền tảng đó.

Trong dự án Java, sử dụng các dependency tương ứng với các dịch vụ cần test:

- Pub/Sub: com.google.cloud:google-cloud-pubsub
- Firestore: com.google.cloud:google-cloud-firestore
- Bigtable: com.google.cloud:google-cloud-bigtable
- Spanner: com.google.cloud:google-cloud-spanner

Nên dùng Google Cloud Libraries BOM để đồng bộ phiên bản thư viện, nhưng chọn phiên bản hiện hành đã được kiểm tra trong dự án. Không hard-code một phiên bản cũ chỉ vì emulator đang chạy được.

## 3. Chạy bốn emulator cục bộ

Mở bốn terminal riêng, mỗi terminal giữ một tiến trình emulator đang chạy.

### Terminal 1: Pub/Sub

~~~bash
gcloud beta emulators pubsub start \
  --project=local-demo-project \
  --host-port=127.0.0.1:8085
~~~

### Terminal 2: Firestore

~~~bash
gcloud emulators firestore start \
  --host-port=127.0.0.1:8080
~~~

### Terminal 3: Bigtable

~~~bash
gcloud beta emulators bigtable start \
  --host-port=127.0.0.1:8086
~~~

### Terminal 4: Spanner

~~~bash
gcloud emulators spanner start
~~~

Spanner mặc định mở gRPC trên localhost:9010 và REST trên localhost:9020. Những port khác nhau phục vụ các client khác nhau; Java Cloud Spanner client kết nối qua gRPC 9010, còn gcloud CLI dùng REST endpoint 9020 khi được cấu hình.

Đợi log xác nhận emulator đã lắng nghe trước khi chạy test. Dừng bằng Ctrl+C. Phần lớn dữ liệu emulator nằm trong bộ nhớ và mất khi tiến trình kết thúc; Pub/Sub cũng giữ tài nguyên và message cho thời gian sống của phiên emulator. Hãy tạo fixture ở đầu mỗi suite thay vì phụ thuộc vào dữ liệu còn lại từ lần chạy trước.

### Đặt biến môi trường cho ứng dụng

Trên Linux/macOS:

~~~bash
export PUBSUB_EMULATOR_HOST=127.0.0.1:8085
export PUBSUB_PROJECT_ID=local-demo-project
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
export BIGTABLE_EMULATOR_HOST=127.0.0.1:8086
export SPANNER_EMULATOR_HOST=127.0.0.1:9010
~~~

Trên Windows PowerShell:

~~~powershell
$env:PUBSUB_EMULATOR_HOST = "127.0.0.1:8085"
$env:PUBSUB_PROJECT_ID = "local-demo-project"
$env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:8080"
$env:BIGTABLE_EMULATOR_HOST = "127.0.0.1:8086"
$env:SPANNER_EMULATOR_HOST = "127.0.0.1:9010"
~~~

Các biến môi trường phải được thiết lập trong môi trường của tiến trình Java **trước khi** khởi tạo Cloud Client Library. Khi chạy trong IDE hoặc Gradle/Maven, cấu hình biến môi trường cho test runner tương ứng. Nếu test chạy trong Docker container, thay 127.0.0.1 bằng hostname service của emulator trên cùng Docker network.

Không thêm http:// hoặc https:// vào giá trị của các biến HOST trên. Mỗi emulator dùng địa chỉ host:port. Đặt tên biến đúng từng dịch vụ; dùng FIRESTORE_EMULATOR_HOST không khiến Pub/Sub chuyển endpoint.

## 4. Pub/Sub emulator: kiểm tra publish, pull và ack

Pub/Sub là dịch vụ messaging bất đồng bộ. Một test tích hợp thường kiểm tra ứng dụng có tạo topic/subscription, publish message, consumer nhận message đúng dữ liệu và gọi acknowledge không. Có thể mở rộng test sang nack, redelivery, ordering key, filter hoặc dead-letter topic trong phạm vi emulator hỗ trợ.

### Lưu ý riêng cho Java

**Pub/Sub Java client không tự chuyển sang emulator chỉ nhờ PUBSUB_EMULATOR_HOST.** Bạn phải tạo gRPC channel plaintext tới emulator và cung cấp NoCredentialsProvider cho các client dùng trong test. Nếu quên cấu hình này, Java client có thể thử gọi endpoint Pub/Sub thật và yêu cầu Google Cloud credentials.

Ví dụ cấu hình TopicAdminClient và tạo topic:

~~~java
import com.google.api.gax.core.NoCredentialsProvider;
import com.google.api.gax.grpc.GrpcTransportChannel;
import com.google.api.gax.rpc.FixedTransportChannelProvider;
import com.google.api.gax.rpc.TransportChannelProvider;
import com.google.cloud.pubsub.v1.TopicAdminClient;
import com.google.cloud.pubsub.v1.TopicAdminSettings;
import com.google.pubsub.v1.TopicName;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.concurrent.TimeUnit;

String host = System.getenv("PUBSUB_EMULATOR_HOST");
if (host == null || host.isBlank()) {
    throw new IllegalStateException("PUBSUB_EMULATOR_HOST is required for this test");
}

ManagedChannel channel =
    ManagedChannelBuilder.forTarget(host).usePlaintext().build();
try {
    TransportChannelProvider provider =
        FixedTransportChannelProvider.create(
            GrpcTransportChannel.create(channel));

    TopicAdminSettings settings = TopicAdminSettings.newBuilder()
        .setTransportChannelProvider(provider)
        .setCredentialsProvider(NoCredentialsProvider.create())
        .build();

    try (TopicAdminClient topics = TopicAdminClient.create(settings)) {
        TopicName topic = TopicName.of("local-demo-project", "orders-test");
        topics.createTopic(topic);
    }
} finally {
    channel.shutdownNow();
    channel.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

Để test publish/subscribe, dùng cùng TransportChannelProvider và NoCredentialsProvider khi tạo Publisher, Subscriber hoặc SubscriptionAdminClient. Chỉ tạo topic chưa chứng minh consumer xử lý thành công; bài test đầy đủ phải phát message, nhận message, xác minh payload và ack.

### Kịch bản integration test gợi ý

1. Tạo topic orders-test và pull subscription orders-test-sub trong emulator.
2. Bắt đầu subscriber hoặc gọi Pull API.
3. Publish một message với orderId giả và eventType ORDER_CREATED.
4. Chờ message có timeout có giới hạn.
5. Kiểm tra message attributes và payload sau khi deserialize.
6. Acknowledge, sau đó xác minh trạng thái xử lý của ứng dụng.
7. Dọn topic và subscription hoặc kết thúc emulator session.

Tạo ID riêng cho mỗi test để tránh trùng tên và ảnh hưởng lẫn nhau. Không đưa assertion phụ thuộc vào tốc độ giao message quá chặt; dùng thời gian chờ hợp lý, nhưng không dùng sleep cố định dài thay cho điều kiện hoàn tất.

### Những khác biệt cần nhớ

Pub/Sub emulator hỗ trợ các chức năng phổ biến như publish/receive, ordering, replay, filter và một số retry policy, nhưng không hỗ trợ IAM operations. Không hỗ trợ mọi loại schema và cập nhật tài nguyên; một số tính năng như BigQuery subscription có thể tạo được nhưng không chuyển message sang BigQuery. Retention trong emulator cũng khác dịch vụ thật.

Push subscription có thể gọi HTTP endpoint không dùng TLS khi chạy cục bộ; production yêu cầu HTTPS. Vì vậy, test với push emulator không thay thế kiểm thử xác thực, TLS và chính sách endpoint thật.

## 5. Firestore emulator: document, query và transaction

Firestore emulator mô phỏng cơ sở dữ liệu document. Đây là công cụ phù hợp để kiểm tra repository layer trong Spring Boot: mapping Java object, tạo document, truy vấn collection, cập nhật field, batch write và logic transaction thông thường.

### Kết nối Java tự động qua biến môi trường

Với Java server client library, khi FIRESTORE_EMULATOR_HOST được đặt trước lúc tạo client, thư viện tự kết nối tới emulator. Có thể tạo Firestore client bằng project ID thử nghiệm:

~~~java
import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import java.util.Map;

try (Firestore firestore = FirestoreOptions.newBuilder()
        .setProjectId("local-demo-project")
        .build()
        .getService()) {

    DocumentReference order = firestore
        .collection("orders")
        .document("order-001");

    order.set(Map.of("status", "CREATED", "total", 1250)).get();

    DocumentSnapshot snapshot = order.get().get();
    if (!snapshot.exists()) {
        throw new AssertionError("Order document is missing");
    }
    if (!"CREATED".equals(snapshot.getString("status"))) {
        throw new AssertionError("Unexpected order status");
    }
}
~~~

Đây là dạng smoke test cho client và repository; trong test JUnit thật, dùng assertions của JUnit/AssertJ thay cho việc tự ném AssertionError.

### Cô lập dữ liệu

Vì dữ liệu sống trong bộ nhớ của emulator, test có thể nhanh và không bị giới hạn quota như production. Tuy nhiên, nếu nhiều test chạy trên cùng tiến trình và cùng collection, dữ liệu của test trước vẫn có thể xuất hiện ở test sau.

Các cách cô lập:

- Dùng collection prefix hoặc document ID duy nhất theo test.
- Xóa fixture đã tạo trong afterEach/afterAll.
- Chạy emulator riêng cho mỗi test suite khi cần cô lập mạnh hơn.
- Không phụ thuộc vào thứ tự test hoặc dữ liệu từ suite khác.

### Giới hạn đáng chú ý

- Emulator không quản lý composite indexes giống production. Query hợp lệ có thể chạy cục bộ dù khi chạy thực cần tạo composite index.
- Transaction không mô phỏng đầy đủ concurrency mode, lock và timeouts của production; write cạnh tranh vào cùng document có thể bị chặn lâu.
- Một số giới hạn kích thước hoặc tài nguyên không được thực thi giống dịch vụ thật.
- Một số tính năng, ví dụ text search stage search(...), có thể chưa được hỗ trợ.

Hãy có một bước test trên Firestore thật để xác minh index, security rules hoặc IAM phù hợp với loại client, transaction contention và giới hạn sản phẩm.

## 6. Bigtable emulator: row key, column family và filter

Bigtable là cơ sở dữ liệu wide-column phù hợp dữ liệu có lưu lượng lớn, row key rõ ràng và truy vấn theo key/range. Emulator giúp kiểm tra schema của table, cách encode row key, việc ghi cell, read row và dùng filter mà không tạo Bigtable instance thật.

### Khởi tạo table và column family

Bigtable emulator **không hỗ trợ các API quản trị instance và cluster**; không cần tạo instance thật trong project. Bạn vẫn có thể dùng tên project và instance giả để tạo table rồi đọc/ghi dữ liệu bằng client library.

Ví dụ Java:

~~~java
import com.google.cloud.bigtable.admin.v2.BigtableTableAdminClient;
import com.google.cloud.bigtable.admin.v2.BigtableTableAdminSettings;
import com.google.cloud.bigtable.admin.v2.models.CreateTableRequest;

BigtableTableAdminSettings adminSettings =
    BigtableTableAdminSettings.newBuilder()
        .setProjectId("local-demo-project")
        .setInstanceId("local-instance")
        .build();

try (BigtableTableAdminClient admin =
         BigtableTableAdminClient.create(adminSettings)) {
    if (!admin.exists("order-events")) {
        admin.createTable(
            CreateTableRequest.of("order-events").addFamily("event"));
    }
}
~~~

BIGTABLE_EMULATOR_HOST được Java Cloud Bigtable client nhận biết tự động. Không cần service account hoặc instance cloud thật cho ví dụ emulator này.

### Ghi và đọc một row

~~~java
import com.google.cloud.bigtable.data.v2.BigtableDataClient;
import com.google.cloud.bigtable.data.v2.BigtableDataSettings;
import com.google.cloud.bigtable.data.v2.models.Row;
import com.google.cloud.bigtable.data.v2.models.RowMutation;

BigtableDataSettings dataSettings = BigtableDataSettings.newBuilder()
    .setProjectId("local-demo-project")
    .setInstanceId("local-instance")
    .build();

try (BigtableDataClient data = BigtableDataClient.create(dataSettings)) {
    RowMutation mutation = RowMutation.create("order-events", "order#001")
        .setCell("event", "type", "ORDER_CREATED");

    data.mutateRow(mutation);
    Row row = data.readRow("order-events", "order#001");
    if (row == null) {
        throw new AssertionError("Missing Bigtable row");
    }
}
~~~

Trong test thật, nên assert giá trị cell và timestamp nếu ứng dụng phụ thuộc vào các trường đó. Cũng nên kiểm tra cách row key được tổ chức vì row key quyết định cách ứng dụng đọc theo dải dữ liệu và ảnh hưởng hiệu năng khi chạy production.

### Giới hạn đáng chú ý

- Emulator dùng bộ nhớ và không giữ dữ liệu qua lần restart.
- Không hỗ trợ tạo hoặc quản lý instance và cluster.
- Không dùng kết nối bảo mật TLS như dịch vụ thật.
- Có hỗ trợ nhiều filter phổ biến, nhưng một số filter như Sink limiting filter không được hỗ trợ.
- Không phản ánh chính xác độ trễ, phân vùng, throughput, replication hoặc chi phí production.

Không dùng Bigtable emulator làm phép đo hiệu năng hoặc kiểm thử capacity. Những nội dung này phải dùng workload đại diện và Bigtable thật với cấu hình instance/cluster phù hợp.

## 7. Spanner emulator: schema, SQL và giao dịch

Spanner cung cấp SQL, transaction và khả năng mở rộng cho workload quan hệ. Emulator hỗ trợ kiểm tra logic truy vấn GoogleSQL hoặc PostgreSQL dialect, thao tác dữ liệu và transaction ở mức chức năng.

### Hai endpoint của Spanner emulator

- localhost:9010: endpoint gRPC cho Java Cloud Spanner client.
- localhost:9020: endpoint REST cho gcloud CLI và các REST client.

Đặt SPANNER_EMULATOR_HOST=127.0.0.1:9010 cho tiến trình Java. Cloud Spanner Java client sẽ tự sử dụng emulator khi biến này được thiết lập.

### Tạo cấu hình gcloud riêng cho Spanner emulator

Nếu muốn chạy gcloud spanner commands với emulator, cần cấu hình riêng để tránh gửi lệnh tới project thật:

~~~bash
gcloud config configurations create spanner-local
gcloud config set auth/disable_credentials true
gcloud config set project local-demo-project
gcloud config set api_endpoint_overrides/spanner http://localhost:9020/
~~~

Sau đó tạo instance và database trong emulator:

~~~bash
gcloud spanner instances create local-instance \
  --config=emulator-config \
  --description="Local integration test" \
  --nodes=1

gcloud spanner databases create local-db \
  --instance=local-instance \
  --ddl="CREATE TABLE Orders (Id STRING(36) NOT NULL, Status STRING(20)) PRIMARY KEY (Id)"
~~~

Các tài nguyên này nằm trong Spanner emulator. Khi dùng cấu hình gcloud khác (đặc biệt là default), các lệnh tương tự có thể tác động đến dịch vụ thật. Sau khi thử nghiệm, chuyển lại cấu hình bình thường bằng lệnh gcloud config configurations activate default nếu đó là cấu hình đã sử dụng trước đó.

### Kết nối bằng Java Cloud Spanner client

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.DatabaseId;
import com.google.cloud.spanner.Mutation;
import com.google.cloud.spanner.ResultSet;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;
import com.google.cloud.spanner.Statement;
import java.util.List;

try (Spanner spanner = SpannerOptions.newBuilder()
        .setProjectId("local-demo-project")
        .build()
        .getService()) {

    DatabaseId databaseId =
        DatabaseId.of("local-demo-project", "local-instance", "local-db");
    DatabaseClient database = spanner.getDatabaseClient(databaseId);

    database.write(List.of(
        Mutation.newInsertBuilder("Orders")
            .set("Id").to("order-001")
            .set("Status").to("CREATED")
            .build()));

    try (ResultSet results = database.singleUse()
            .executeQuery(Statement.of(
                "SELECT Status FROM Orders WHERE Id = 'order-001'"))) {
        if (!results.next()
                || !"CREATED".equals(results.getString("Status"))) {
            throw new AssertionError("Unexpected Spanner result");
        }
    }
}
~~~

Ví dụ này giả định DDL GoogleSQL đã được tạo bằng gcloud ở bước trước. Với PostgreSQL dialect, cú pháp DDL và một số cấu trúc SQL khác; hãy chọn đúng dialect từ đầu và kiểm thử theo contract của ứng dụng.

### Những khác biệt lớn với production

- Emulator không hỗ trợ TLS/HTTPS, authentication, IAM, quyền và role.
- Không có audit logging và monitoring như dịch vụ thật.
- Query PLAN/PROFILE trả về kế hoạch rỗng; ANALYZE được chấp nhận nhưng không thực hiện phân tích thật.
- Read-write transaction và schema change khóa toàn database, khác cơ chế concurrency của production.
- Partitioned DML hoặc partitionQuery có thể được emulator chấp nhận dù trên dịch vụ thật bị từ chối vì không partitionable.
- Không phản ánh throughput, latency hoặc khả năng mở rộng thực tế.

Vì vậy, emulator phù hợp với correctness của logic truy vấn và transaction cơ bản; không dùng để xác nhận isolation/contention, query plan, optimizer, IAM hoặc độ tin cậy của Spanner production.

## 8. Thiết kế integration test với Java, JUnit và Spring Boot

### Tách cấu hình môi trường

Một nguyên tắc quan trọng là test phải bật emulator một cách rõ ràng. Có thể dùng Spring profile test-emulator và yêu cầu các biến môi trường có mặt trước khi khởi tạo bean:

~~~java
import java.util.Map;

class EmulatorEnvironment {
    static void verifyRequiredHosts() {
        for (String name : new String[] {
                "PUBSUB_EMULATOR_HOST",
                "FIRESTORE_EMULATOR_HOST",
                "BIGTABLE_EMULATOR_HOST",
                "SPANNER_EMULATOR_HOST"
        }) {
            if (System.getenv(name) == null || System.getenv(name).isBlank()) {
                throw new IllegalStateException(
                    "Emulator environment is missing: " + name);
            }
        }
    }
}
~~~

Đối với test chỉ dùng một hoặc hai dịch vụ, chỉ kiểm tra biến của các dịch vụ đó. Với Spring Boot, có thể đặt check trong test setup hoặc bean dành riêng cho profile test-emulator. Không dùng cấu hình emulator mặc định trong profile production.

### Fixture và vòng đời

Một suite có thể:

1. Chờ emulator sẵn sàng.
2. Tạo topic/subscription, collection/document, Bigtable table hoặc Spanner schema.
3. Đặt ID riêng cho test và ghi dữ liệu fixture.
4. Khởi động ứng dụng Spring với các biến emulator.
5. Gọi use case và assert dữ liệu đầu ra.
6. Dọn fixture và đóng client.
7. Dừng emulator khi toàn bộ suite hoàn tất.

Ví dụ JUnit 5 cho Firestore repository:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import java.util.Map;
import org.junit.jupiter.api.Test;

class OrderRepositoryIntegrationTest {

    @Test
    void canPersistAndLoadOrder() throws Exception {
        String host = System.getenv("FIRESTORE_EMULATOR_HOST");
        assertTrue(host != null && !host.isBlank(),
            "This test must use Firestore emulator");

        try (Firestore db = FirestoreOptions.newBuilder()
                .setProjectId("local-demo-project")
                .build()
                .getService()) {
            String id = "order-" + java.util.UUID.randomUUID();
            DocumentReference ref = db.collection("orders").document(id);
            ref.set(Map.of("status", "CREATED")).get();
            DocumentSnapshot saved = ref.get().get();

            assertTrue(saved.exists());
            assertEquals("CREATED", saved.getString("status"));
            ref.delete().get();
        }
    }
}
~~~

Test này vẫn cần emulator Firestore đang chạy ở địa chỉ FIRESTORE_EMULATOR_HOST. Trong CI, nên để bước khởi động emulator và chờ readiness nằm trước bước chạy test.

### Kiểm thử hành vi thay vì implementation

Hãy assert kết quả mà nghiệp vụ quan tâm: số message được xử lý, document được lưu đúng, row key được ghi, transaction thay đổi đúng dữ liệu. Tránh viết test chỉ xác nhận method client đã được gọi, vì loại test đó có thể làm tốt hơn bằng mock và không tận dụng được emulator.

### Timeout và độ ổn định

Các emulator vẫn chạy qua mạng cục bộ; một tiến trình mới khởi động có thể chưa sẵn sàng. Dùng readiness check có timeout hữu hạn. Với message bất đồng bộ, chờ điều kiện bằng polling ngắn có deadline thay vì sleep cố định vài giây cho mọi test.

Nếu chạy test song song, mỗi test nên có namespace riêng hoặc mỗi worker có emulator riêng. Dữ liệu dùng chung và port cố định là nguồn gây flaky test thường gặp.

## 9. Docker và CI pipeline

Emulator có thể chạy trên máy host, trong Docker hoặc dưới dạng service container trong CI. Lợi ích của container là có môi trường nhất quán, tạo mới và hủy được sau mỗi job. Tuy nhiên, cấu hình mạng phải chính xác.

### Khi ứng dụng và emulator cùng một container hoặc cùng host

Sử dụng 127.0.0.1:PORT nếu ứng dụng chạy cùng network namespace với emulator. Nếu ứng dụng ở container riêng, dùng hostname service, ví dụ pubsub:8085 hoặc firestore:8080. Một biến PUBSUB_EMULATOR_HOST trỏ tới localhost trong container ứng dụng sẽ gây connection refused nếu Pub/Sub chạy ở container khác.

### Ví dụ Docker Compose ý tưởng

~~~yaml
services:
  pubsub:
    image: gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators
    command:
      - gcloud
      - beta
      - emulators
      - pubsub
      - start
      - --project=local-demo-project
      - --host-port=0.0.0.0:8085
    ports:
      - "127.0.0.1:8085:8085"

  firestore:
    image: gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators
    command:
      - gcloud
      - emulators
      - firestore
      - start
      - --host-port=0.0.0.0:8080
    ports:
      - "127.0.0.1:8080:8080"
~~~

Ví dụ minh họa hai service; cần xác minh image và thành phần emulator có sẵn trong image tại thời điểm triển khai. Những thành phần khác có thể cần image riêng hoặc cài thêm component. Không tự động coi container đã chạy là service đã sẵn sàng; thêm health check/readiness tương ứng trước khi chạy test.

Khi Java test chạy trong cùng Compose network, cấu hình:

~~~text
PUBSUB_EMULATOR_HOST=pubsub:8085
FIRESTORE_EMULATOR_HOST=firestore:8080
~~~

Nếu test chạy trên host, dùng 127.0.0.1:8085 và 127.0.0.1:8080 như port được publish.

### CI chạy emulators như thế nào?

Một job CI thường có các bước:

1. Cài JDK, Java build tool và các emulator binaries hoặc khởi tạo service container.
2. Chạy emulators trên port riêng và chỉ mở trong mạng test.
3. Chờ readiness, kiểm tra port/API trả lời.
4. Export biến môi trường cho test runner.
5. Tạo fixture bằng client library.
6. Chạy các bài integration test.
7. Thu thập log emulator và test report khi có lỗi.
8. Dừng tiến trình/container, xóa tài nguyên test và thông tin tạm.

Không đặt service account production credentials vào CI job chỉ chạy emulator. Các emulator không cần quyền truy cập project production để phục vụ những phép thử cục bộ. Nếu cùng job còn có bước test staging, hãy tách profile, biến môi trường và danh tính rõ ràng.

## 10. Phân biệt emulator và môi trường staging

Không nên dùng emulator để kết luận rằng ứng dụng đã tuân thủ mọi quy tắc GCP. Bảng sau gợi ý nơi nên kiểm thử:

| Tình huống | Emulator | Staging GCP thật |
|---|---|---|
| Mapping dữ liệu, encode/decode | Phù hợp | Có thể kiểm tra bổ sung |
| Publish/subscribe và xử lý message cơ bản | Phù hợp | Kiểm tra delivery, IAM và quota |
| Firestore query và transaction logic | Phù hợp | Kiểm tra composite indexes, security/IAM, transaction limit |
| Bigtable row key, cell và filter thông thường | Phù hợp | Kiểm tra performance, cluster replication, quota, IAM |
| Spanner SQL và transaction chức năng | Phù hợp | Kiểm tra query plan, concurrency, IAM, latency |
| Service account, IAM, VPC, firewall | Không xác minh được | Bắt buộc |
| Load test và capacity planning | Không phù hợp | Bắt buộc bằng môi trường có quy mô đại diện |
| Chi phí vận hành | Không phản ánh | Ước lượng và kiểm chứng trên GCP |

Một pipeline hợp lý có thể chạy unit test và emulator test ở mỗi pull request, rồi chạy staging test cho tính năng mới, thay đổi schema hoặc thay đổi tích hợp quan trọng. Với hệ thống nhạy cảm, bổ sung contract test và kiểm thử failure modes trên dịch vụ thật.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Java Pub/Sub client vẫn hỏi credentials | Chỉ đặt PUBSUB_EMULATOR_HOST nhưng chưa cấu hình channel/NoCredentialsProvider | Dùng FixedTransportChannelProvider, plaintext gRPC và NoCredentialsProvider |
| Connection refused ở localhost | Emulator chưa chạy, port sai hoặc Java ở container khác | Kiểm tra process, port, Docker hostname và readiness |
| Test vô tình gọi Google Cloud thật | Biến môi trường chưa được truyền vào runner hoặc test profile sai | Fail-fast khi thiếu biến; kiểm tra endpoint, tách cấu hình production |
| Firestore test chạy nhưng production thiếu index | Emulator không theo dõi composite index giống production | Chạy thêm staging test và quản lý index |
| Firestore transaction bị chờ lâu | Locking đơn giản của emulator | Tránh contention trong test hoặc điều chỉnh deadline cục bộ |
| Bigtable báo không hỗ trợ tạo instance | Emulator chỉ hỗ trợ phần table/data API | Dùng instance ID giả; tạo table và family trực tiếp |
| Bigtable test mất dữ liệu sau restart | Dữ liệu trong memory | Tạo fixture mỗi lần suite chạy |
| Spanner Java kết nối port 9020 bị lỗi | Dùng REST port cho gRPC client | Dùng SPANNER_EMULATOR_HOST trỏ 9010 |
| Spanner gcloud thao tác lên project thật | Chưa override endpoint hoặc đang dùng sai gcloud configuration | Tạo cấu hình emulator tách biệt và kiểm tra active config |
| Test pass nhưng lỗi IAM/TLS khi deploy | Emulator không kiểm tra đầy đủ bảo mật | Chạy staging test với IAM và endpoint thật |
| Test song song có lỗi trùng dữ liệu | Chung project ID, table, topic hoặc document ID | Dùng namespace riêng, cleanup hoặc emulator per worker |

## 12. Bài thực hành tổng hợp

Giả sử ứng dụng Spring xử lý đơn hàng theo mô hình event-driven:

1. API nhận đơn hàng và ghi thông tin vào Firestore hoặc Spanner.
2. Ứng dụng phát ORDER_CREATED tới Pub/Sub.
3. Consumer đọc message và ghi một dòng event log vào Bigtable.
4. Một endpoint kiểm tra trạng thái đơn hàng.

Kịch bản integration test dùng bốn emulator:

- Tạo database/table/topic/subscription trước khi chạy test.
- Gửi request tạo đơn hàng bằng dữ liệu giả và idempotency key.
- Xác minh đơn hàng được ghi đúng vào Firestore hoặc Spanner.
- Chờ Pub/Sub consumer xử lý message có timeout.
- Xác minh row tương ứng xuất hiện trong Bigtable.
- Gửi lại cùng idempotency key và bảo đảm không tạo bản ghi nghiệp vụ trùng.
- Kiểm tra retry hoặc redelivery bằng cách làm consumer thất bại một lần có kiểm soát.
- Dọn fixture để test khác không phụ thuộc vào kết quả.

Đây là phép thử **luồng chức năng**. Sau khi pass, bạn vẫn cần test trên staging để xác nhận IAM của các service account, quota Pub/Sub, indexing Firestore, hiệu năng Bigtable và hành vi transaction Spanner dưới tải thật.

## 13. Checklist trước khi đưa emulator test vào CI

- [ ] Đã chọn emulator đúng dịch vụ và kiểm tra phiên bản CLI/Java cần dùng.
- [ ] Port được cấu hình rõ và không trùng với service khác.
- [ ] Java test runner nhận đúng các biến EMULATOR_HOST.
- [ ] Pub/Sub Java client dùng explicit gRPC channel và NoCredentialsProvider.
- [ ] Các client Firestore, Bigtable, Spanner được khởi tạo sau khi đặt biến môi trường.
- [ ] Test không tải production credentials hoặc gọi production endpoint.
- [ ] Có readiness check và timeout hợp lý trước khi chạy test.
- [ ] Fixture được tạo và dọn rõ ràng; test không phụ thuộc thứ tự.
- [ ] Test song song dùng namespace hoặc emulator riêng.
- [ ] Có đủ assertion trên dữ liệu và tác động nghiệp vụ.
- [ ] Có log và test report để điều tra khi thất bại.
- [ ] Các tính năng thiếu trong emulator đã có test bổ sung trên staging.

## 14. Kết luận

Pub/Sub, Firestore, Bigtable và Spanner emulator giúp kiểm thử tích hợp ứng dụng GCP nhanh và độc lập hơn. Chúng hỗ trợ những phần quan trọng của API dữ liệu và messaging, nhưng khác nhau ở cách kết nối: Pub/Sub Java cần khai báo gRPC channel không dùng credentials, trong khi Java server clients của Firestore, Bigtable và Spanner tự nhận địa chỉ emulator từ biến môi trường.

Để có test đáng tin cậy, hãy quản lý rõ vòng đời emulator, tạo dữ liệu fixture độc lập, cấu hình endpoint fail-fast và tránh phụ thuộc vào thứ tự thực thi. Sau đó dùng staging GCP thật để xác minh IAM, index, concurrency, quota, performance và các tính năng emulator không mô phỏng. Cách kết hợp này giúp đội Java/Spring phát hiện lỗi tích hợp sớm mà vẫn kiểm soát được rủi ro khi triển khai.

## Tài liệu tham khảo

- [Pub/Sub: Testing apps locally with the emulator](https://docs.cloud.google.com/pubsub/docs/emulator)
- [Firestore: Use Firestore emulator locally](https://docs.cloud.google.com/firestore/native/docs/emulator)
- [Firebase Local Emulator Suite: Connect to Firestore emulator](https://firebase.google.com/docs/emulator-suite/connect_firestore)
- [Bigtable: Test using the emulator](https://docs.cloud.google.com/bigtable/docs/emulator)
- [Spanner: Emulate Spanner locally](https://docs.cloud.google.com/spanner/docs/emulator)
- [Spanner: Create and manage databases](https://docs.cloud.google.com/spanner/docs/create-manage-databases)
- [Google Cloud Client Libraries for Java](https://cloud.google.com/java/docs/reference)
- [Firebase Local Emulator Suite](https://firebase.google.com/docs/emulator-suite)
