# Tạo tài nguyên kiểm thử biệt lập và dọn dẹp sau mỗi lần chạy

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua Spring Cloud và client library tương ứng. Một integration test có thể tạo bucket, queue, topic, table, database, secret hoặc container để kiểm tra luồng ứng dụng. Nếu các test dùng chung tài nguyên và dữ liệu, kết quả dễ phụ thuộc thứ tự chạy, test song song có thể ghi đè lẫn nhau và tài nguyên cloud bị bỏ quên có thể tiếp tục phát sinh chi phí.

Kiểm thử đáng tin cậy cần hai thuộc tính:

- **Isolation:** mỗi test hoặc mỗi test run chỉ thao tác trên tài nguyên/dữ liệu thuộc phạm vi của nó.
- **Cleanup:** tài nguyên được tạo ra được xóa sau khi test hoàn tất, kể cả khi assertion thất bại hoặc setup chỉ hoàn thành một phần.

Container emulator như LocalStack, Pub/Sub emulator hoặc Azurite giúp cô lập tiến trình hạ tầng. Tuy nhiên, container không tự xóa bucket, queue hay database mà test đã tạo trên cloud thật. Vòng đời container và vòng đời cloud resource phải được quản lý riêng.

Sau bài này, bạn có thể:

- Chọn phạm vi cô lập theo test method, class, suite hoặc CI run.
- Tạo tên resource duy nhất, có thể truy vết và tuân thủ quy tắc từng provider.
- Quản lý cleanup bằng JUnit lifecycle, `AutoCloseable` và registry.
- Xóa resource theo thứ tự phụ thuộc và xác minh thao tác xóa hoàn tất.
- Cô lập dữ liệu khi dùng chung bucket, database, emulator hoặc container.
- Xử lý test song song và nhiều CI worker.
- Thiết kế cleanup an toàn cho AWS, Azure và Google Cloud.
- Thu hồi tài nguyên mồ côi khi CI bị hủy hoặc JVM bị kill.

## 2. Resource isolation khác với container isolation

Có hai lớp vòng đời:

1. **Infrastructure lifecycle:** Docker/Testcontainers/emulator được khởi động và dừng.
2. **Test resource lifecycle:** bucket, queue, topic, table, database, object, document hoặc record do test tạo.

Ví dụ, một LocalStack container có thể được chia sẻ cho toàn bộ test class. Mỗi test vẫn cần bucket và queue riêng, hoặc một namespace riêng bên trong resource dùng chung. Dừng LocalStack container không phải là chiến lược cleanup cho AWS resource thật.

~~~mermaid
flowchart TD
    R[CI test run] --> C[Shared emulator/container]
    R --> T1[Test method A]
    R --> T2[Test method B]
    R --> T3[Test method C]
    T1 --> A1[Resource namespace A]
    T2 --> A2[Resource namespace B]
    T3 --> A3[Resource namespace C]
    A1 --> X[Cleanup registry]
    A2 --> X
    A3 --> X
    X --> D[Delete and verify]
    C --> S[Stop after suite/class]
~~~

Container có thể dùng chung để tiết kiệm thời gian khởi động. Dữ liệu test vẫn phải độc lập để test có thể chạy theo bất kỳ thứ tự nào.

## 3. Chọn phạm vi cô lập

Không phải tài nguyên nào cũng cần tạo mới cho từng test method. Chọn phạm vi theo chi phí khởi tạo, mức độ chia sẻ state và khả năng xóa an toàn:

| Phạm vi | Ví dụ | Khi phù hợp |
|---|---|---|
| Per assertion | Một object hoặc record riêng | Test nhỏ, dữ liệu dễ tạo/xóa |
| Per test method | Queue, topic, bucket hoặc database riêng | Test có thể chạy song song, cần isolation mạnh |
| Per test class | Một emulator/container hoặc database schema | Nhiều test dùng chung hạ tầng, dữ liệu được reset mỗi method |
| Per test suite | Một container hoặc namespace | Chi phí khởi tạo cao, test data có prefix riêng |
| Per CI run | Project/resource group/namespace riêng | Nhiều test class hoặc worker chạy đồng thời |
| Shared environment | Một project/subscription/account chuyên dụng | Chỉ khi có quy tắc ownership, naming và cleanup chặt chẽ |

Mặc định nên tạo **dữ liệu riêng cho mỗi test method**. Có thể dùng chung emulator, database server hoặc cloud account; nhưng bucket prefix, queue, table, tenant key hoặc record ID phải phân biệt được.

Nếu tạo database hoặc cloud resource quá tốn kém, dùng một database/container chung và partition dữ liệu theo run ID. Khi đó test chỉ được đọc/xóa partition của chính nó, không gọi `deleteAll()` trên tài nguyên dùng chung.

## 4. Tạo run ID và tên resource duy nhất

Tên resource cần trả lời được:

- Resource thuộc CI run nào?
- Thuộc test class/method nào?
- Được tạo bởi ứng dụng hoặc team nào?
- Có thể tìm thấy và dọn dẹp bằng cách nào?

Một format dễ truy vết:

~~~text
<service>-<purpose>-<ci-run>-<test-id>-<random-suffix>
~~~

Ví dụ:

~~~text
provider-it-documents-run842-preview-7f29c1a4
provider-it-events-run842-queue-8a31d902
provider-it-storage-run842-6b3e18f1
~~~

Không chỉ dùng timestamp đến giây vì nhiều worker có thể tạo resource cùng lúc. Thêm UUID/random suffix để tránh collision. Giữ tên ngắn vì mỗi provider có giới hạn độ dài, ký tự, chữ hoa/thường và quy tắc global uniqueness khác nhau.

Ví dụ helper Java:

~~~java
import java.util.Locale;
import java.util.UUID;

public final class TestResourceNames {
    private TestResourceNames() {}

    public static String unique(String prefix, int maxLength) {
        String safePrefix = prefix.toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z0-9-]", "-")
                .replaceAll("-+", "-")
                .replaceAll("^-|-$", "");
        if (safePrefix.isBlank()) {
            throw new IllegalArgumentException("prefix must contain a letter or digit");
        }

        String suffix = UUID.randomUUID()
                .toString()
                .replace("-", "")
                .substring(0, 12);

        String candidate = safePrefix + "-" + suffix;
        if (candidate.length() <= maxLength) {
            return candidate;
        }
        int prefixLength = maxLength - suffix.length() - 1;
        if (prefixLength < 1) {
            throw new IllegalArgumentException("maxLength is too small");
        }
        return safePrefix.substring(0, Math.min(prefixLength, safePrefix.length()))
                + "-" + suffix;
    }
}
~~~

Helper chỉ minh họa cách tạo tên chữ thường, chữ số và dấu gạch ngang. Hãy kiểm tra quy tắc thực tế của resource type: tên S3 bucket và GCS bucket có quy tắc global namespace; Azure container có giới hạn riêng; Service Bus entity, DynamoDB table và Pub/Sub topic có giới hạn khác. Không dùng một giới hạn độ dài chung cho mọi dịch vụ.

## 5. Gắn ownership metadata vào resource

Tên duy nhất giúp tránh xung đột; metadata giúp truy tìm và cleanup resource mồ côi.

Nếu service hỗ trợ tag hoặc label, gắn các thuộc tính:

| Tag/label | Ví dụ | Mục đích |
|---|---|---|
| `managed-by` | `integration-tests` | Phân biệt resource do test tạo |
| `test-run-id` | `run-842` | Gom resource theo CI run |
| `test-class` | `PreviewQueueIT` | Xác định nguồn tạo |
| `test-method` | `publishesPreview` | Điều tra test cụ thể |
| `created-at` | ISO-8601 UTC | Tính tuổi resource |
| `expires-at` | ISO-8601 UTC | Phục vụ orphan janitor |
| `owner-team` | `document-platform` | Liên hệ nhóm chịu trách nhiệm |

Không đưa secret, token, customer data hoặc PII vào tên, tag hay label. Một số resource không hỗ trợ tag/label ở cấp resource; dùng naming convention và một cleanup registry bên ngoài để lưu ownership.

Trước khi xóa, kiểm tra ownership metadata và project/account/subscription đích. Không xóa chỉ vì tên bắt đầu bằng một prefix nếu test có thể chạy trong môi trường dùng chung.

## 6. Resource registry và cleanup theo thứ tự ngược

Một test có thể tạo nhiều resource phụ thuộc nhau: bucket, object, notification và queue nhận event. Khi cleanup, nên xóa theo thứ tự ngược: subscription/notification trước, object trước bucket, queue sau khi consumer dừng. Đây là nguyên tắc **last created, first deleted (LIFO)**.

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

public final class TestResourceScope implements AutoCloseable {
    @FunctionalInterface
    public interface CleanupAction {
        void run() throws Exception;
    }

    private final Deque<CleanupAction> actions = new ArrayDeque<>();
    private boolean closed;

    public synchronized void onClose(CleanupAction action) {
        if (closed) {
            throw new IllegalStateException("Resource scope is already closed");
        }
        actions.push(action);
    }

    @Override
    public void close() throws Exception {
        Exception failure = null;
        synchronized (this) {
            if (closed) return;
            closed = true;
        }
        while (true) {
            CleanupAction action;
            synchronized (this) {
                action = actions.poll();
            }
            if (action == null) break;
            try {
                action.run();
            } catch (Exception ex) {
                if (failure == null) {
                    failure = new Exception("One or more test resources failed to clean up");
                }
                failure.addSuppressed(ex);
            }
        }
        if (failure != null) throw failure;
    }
}
~~~

Đăng ký cleanup ngay sau khi tạo thành công từng resource:

~~~java
try (TestResourceScope scope = new TestResourceScope()) {
    String bucket = createBucket();
    scope.onClose(() -> deleteBucketIfOwned(bucket));
    String objectKey = uploadObject(bucket);
    scope.onClose(() -> deleteObjectIfOwned(bucket, objectKey));
    assertObjectCanBeDownloaded(bucket, objectKey);
}
~~~

Vì registry dùng stack, object được xóa trước bucket. Nếu upload thất bại sau khi bucket đã tạo, bucket cleanup vẫn được chạy. Cleanup action phải idempotent hoặc xử lý riêng lỗi NotFound để lần chạy lặp lại không gây nhiễu.

## 7. Dùng JUnit lifecycle đúng cách

JUnit Jupiter cung cấp `@BeforeEach`, `@AfterEach`, `@BeforeAll` và `@AfterAll`:

- `@BeforeEach`: tạo dữ liệu riêng cho test method.
- `@AfterEach`: xóa dữ liệu của test method.
- `@BeforeAll`: khởi tạo hạ tầng dùng chung cho class.
- `@AfterAll`: dừng hạ tầng dùng chung sau class.

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class QueueIntegrationTest {
    private TestResourceScope resources;
    private String queueName;

    @BeforeEach
    void createIsolatedResources() {
        resources = new TestResourceScope();
        queueName = TestResourceNames.unique("provider-it-queue", 80);
        createQueue(queueName);
        resources.onClose(() -> deleteQueueIfOwned(queueName));
    }

    @AfterEach
    void cleanupResources() throws Exception {
        if (resources != null) resources.close();
    }

    @Test
    void sendsMessageToItsOwnQueue() {
        sendMessage(queueName, "test-payload");
        assertMessageAvailable(queueName);
    }
}
~~~

Nếu setup tạo nhiều resource và có thể thất bại giữa chừng, đăng ký cleanup sau từng lần tạo. Với setup phức tạp, dùng try/catch trong `@BeforeEach` để gọi cleanup trước khi ném lại exception; đừng giả định mọi callback teardown đều sẽ xử lý đúng một setup đã lỗi ở giữa. Try-with-resources trực tiếp trong test method cũng bảo đảm `close()` được gọi khi test body thoát bình thường hoặc ném exception.

## 8. Testcontainers: chia sẻ container nhưng cô lập dữ liệu

Với Testcontainers JUnit 5:

- Static `@Container` được khởi động một lần trước các test method trong class và dừng sau class.
- Instance `@Container` được khởi động/dừng cho từng test method; điều này tốn thời gian và tài nguyên hơn.
- JUnit extension đã được tài liệu Testcontainers ghi nhận là kiểm thử với chạy tuần tự; chạy song song có thể gây side effect ngoài dự kiến.

Trong nhiều suite, nên chia sẻ một emulator/container và tạo resource/data namespace riêng cho từng test. Không cần tạo lại cả container chỉ để có bucket hoặc queue mới.

~~~java
@Testcontainers
class StorageIntegrationTest {
    @Container
    static final LocalStackContainer LOCALSTACK =
            new LocalStackContainer(
                    DockerImageName.parse("localstack/localstack:stable"))
                    .withServices("s3");

    @Test
    void uploadsFirstDocument() {
        String bucket = TestResourceNames.unique("it-docs", 63);
        // Create bucket, test, then delete only this bucket.
    }
}
~~~

Pin image theo version/digest đã được kiểm thử; tag `stable` chỉ minh họa. Lấy endpoint/port từ container, không hardcode port host.

Spring TestContext có thể cache ApplicationContext giữa các test class. Nếu Testcontainers JUnit extension dừng static container ở cuối class nhưng Spring vẫn tái sử dụng context chứa client trỏ tới container đó, test class tiếp theo có thể dùng một endpoint đã dừng. Khi cần container singleton cho nhiều class, quản lý container bằng lifecycle phù hợp, giữ resource cleanup theo từng test method và kiểm soát cache key/context.

## 9. Cô lập khi chạy test song song

Test song song làm lộ những giả định ẩn về dữ liệu dùng chung. Hai test có thể cùng:

- Xóa một queue trong khi test kia đang nhận message.
- Ghi cùng một object key.
- Reset một bảng database.
- Xóa collection mà test khác đang truy vấn.
- Tạo resource cùng tên trong cùng project.

Các nguyên tắc:

1. Tạo resource name riêng theo test ID.
2. Dùng partition key/tenant/run ID cho dữ liệu trong resource dùng chung.
3. Không dùng `deleteAll()` trên database/table/queue dùng chung.
4. Không giả định test chạy theo thứ tự khai báo.
5. Không chia sẻ mutable fixture giữa các test thread.
6. Giới hạn concurrency nếu emulator hoặc cloud quota không chịu được tải.
7. Dùng CI run ID và worker ID để phân biệt các process chạy đồng thời.

Nếu dùng một bucket chung, prefix phải được giới hạn theo test run, ví dụ `runs/<run-id>/<test-id>/`. Cleanup chỉ liệt kê và xóa prefix đó. Không dùng wildcard rộng hoặc xóa cả bucket dùng chung.

## 10. AWS: S3, SQS, SNS và DynamoDB

### 10.1. S3

Tạo bucket riêng cho test khi cần kiểm tra bucket policy, versioning hoặc lifecycle. Nếu chỉ kiểm tra upload/download, có thể dùng bucket dùng chung và object key có prefix run/test riêng.

Cleanup theo thứ tự:

1. Dừng producer/consumer hoặc notification test.
2. Xóa object do test tạo.
3. Nếu bucket bật versioning, xóa mọi object version và delete marker.
4. Abort multipart upload còn dang dở.
5. Xóa bucket sau khi bucket đã rỗng.

S3 không cho xóa bucket còn object/version. Với bucket versioned, xóa object hiện hành bằng DeleteObject có thể chỉ tạo delete marker; cần liệt kê và xóa các version/delete marker nếu muốn bucket rỗng.

### 10.2. SQS và SNS

- Tạo queue với tên duy nhất cho test.
- Dừng listener trước khi xóa queue.
- Xử lý message còn tồn đọng theo fixture; không để consumer khác nhận message của test.
- Xóa subscription và topic do test tạo.
- Không xóa queue/topic dùng chung của môi trường khác.

Với SNS fan-out sang SQS, cleanup subscription và queue trước, rồi mới xóa topic. Lưu ARN/URL do API trả về thay vì tự ghép chuỗi endpoint.

### 10.3. DynamoDB

Có thể tạo table riêng cho test hoặc dùng một table chung với partition key chứa run ID. Table riêng cho phép test schema/index/TTL config; partition riêng rẻ hơn nhưng cleanup cần query đúng partition và xóa từng item.

Nếu xóa table, chờ table chuyển sang trạng thái không còn tồn tại trước khi tạo lại tên đó. Không dựa vào tên cố định khi nhiều CI worker chạy đồng thời.

## 11. Azure: Blob Storage, Service Bus và Cosmos DB

### 11.1. Blob Storage

Tạo container riêng cho test hoặc dùng prefix trong một container test chuyên dụng. Cleanup phải xóa blob/snapshot/version do test tạo và sau đó xóa container nếu container thuộc test.

Azure Blob container có thể cần thời gian để xóa hoàn toàn. Sau khi delete được chấp nhận, container cùng tên có thể chưa tạo lại được trong ít nhất khoảng 30 giây; thao tác trên blob có thể còn thành công trong một khoảng ngắn. Dùng tên duy nhất thay vì xóa rồi tạo lại cùng tên ngay trong test.

Nếu bật soft delete hoặc versioning, dữ liệu đã xóa có thể vẫn được giữ trong thời gian retention. Điều này ảnh hưởng dung lượng/chi phí và khả năng khôi phục, dù resource đã không còn xuất hiện như dữ liệu hiện hành.

### 11.2. Service Bus

Dùng `ServiceBusAdministrationClient` để tạo/xóa queue, topic và subscription trong namespace test:

~~~java
ServiceBusAdministrationClient admin = new ServiceBusClientBuilder()
        .connectionString(testNamespaceConnectionString)
        .buildAdministrationClient();

String queueName = TestResourceNames.unique("it-queue", 50);
admin.createQueue(queueName);

try {
    // Send and receive messages using the test queue.
} finally {
    admin.deleteQueue(queueName);
}
~~~

Nếu test tạo topic/subscription/rule, xóa rule và subscription trước topic. Namespace thường là hạ tầng dùng chung; không xóa namespace trong `@AfterEach` nếu nhiều test đang sử dụng nó.

### 11.3. Cosmos DB

Có thể dùng database/container riêng cho test method hoặc partition key riêng trong container dùng chung. Xóa đúng database/container do test tạo; nếu chỉ tạo item trong container chung, xóa item theo ID và partition key. Không quét rồi xóa toàn bộ container trong cleanup.

## 12. Google Cloud: Pub/Sub, Cloud Storage, Firestore và Spanner

### 12.1. Pub/Sub

Tạo topic và subscription với tên riêng. Khi cleanup:

1. Dừng subscriber/pull worker.
2. Xóa subscription.
3. Xóa topic.

Xóa topic **không tự xóa các subscription** đã gắn vào topic. Sau khi topic bị xóa, tên topic có thể chưa dùng lại được ngay trong một khoảng ngắn. Vì vậy, dùng tên duy nhất cho mỗi run/test và lưu chính xác resource name.

### 12.2. Cloud Storage

Bucket phải rỗng trước khi xóa. Xóa object do test tạo trước bucket; nếu dùng versioning, xử lý noncurrent versions theo policy. Nếu dùng bucket chung, xóa đúng prefix của test run, không xóa các object khác.

Soft delete/retention có thể giữ dữ liệu sau khi lệnh delete hoàn tất. Phân biệt object không còn live với object đã được soft-delete và vẫn còn trong thời gian retention.

### 12.3. Firestore

Xóa document cha không tự động xóa mọi subcollection. Cleanup collection phải duyệt và xóa document/subcollection theo cách đệ quy hoặc dùng công cụ server-side phù hợp. Với test, ưu tiên đặt root path theo run ID để có thể liệt kê và dọn đúng namespace.

### 12.4. Spanner và Bigtable

- Tạo database/table riêng nếu test cần schema isolation.
- Nếu dùng database chung, thêm test run ID vào primary key hoặc namespace dữ liệu.
- Xóa row/record do test tạo trước khi xóa table/database.
- Chờ thao tác drop/delete hoàn tất trước khi tạo lại cùng tên.

Không xóa instance, cluster hoặc project dùng chung chỉ để cleanup một test method.

## 13. Ví dụ cleanup S3 theo try-with-resources

Ví dụ sau tạo bucket và đăng ký cleanup ngay sau khi tạo. Helper xóa object trước bucket:

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.CreateBucketRequest;
import software.amazon.awssdk.services.s3.model.DeleteBucketRequest;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;

@SpringBootTest
class S3ResourceLifecycleIT {
    @Autowired
    S3Client s3;

    @Test
    void createsAndRemovesIsolatedBucket() throws Exception {
        try (TestResourceScope scope = new TestResourceScope()) {
            String bucket = "it-" + UUID.randomUUID()
                    .toString().replace("-", "").substring(0, 16);
            s3.createBucket(CreateBucketRequest.builder()
                    .bucket(bucket)
                    .build());

            scope.onClose(() -> {
                // This example assumes an unversioned test bucket.
                s3.deleteObject(DeleteObjectRequest.builder()
                        .bucket(bucket)
                        .key("fixture.txt")
                        .build());
                s3.deleteBucket(DeleteBucketRequest.builder()
                        .bucket(bucket)
                        .build());
            });

            uploadFixture(s3, bucket, "fixture.txt");
            assertFixtureCanBeRead(s3, bucket, "fixture.txt");
        }
    }
}
~~~

Ví dụ giả định bucket test không bật versioning và chỉ có một object fixture. Helper dùng cho bucket versioned phải xóa tất cả versions/delete markers và abort multipart uploads trước khi gọi DeleteBucket. Trong test thực tế, đăng ký cleanup object ngay sau khi upload thành công để registry phản ánh chính xác resource đã tạo.

## 14. Cleanup an toàn khi setup thất bại

Setup có thể thất bại sau khi đã tạo một phần tài nguyên. Ví dụ bucket đã tạo nhưng upload fixture lỗi; topic đã tạo nhưng subscription chưa tạo. Nếu chỉ cleanup ở cuối test body, resource có thể bị bỏ quên.

Quy trình an toàn:

1. Tạo một resource.
2. Nhận ID/name/ARN/URL chính xác từ provider.
3. Ghi ownership metadata.
4. Đăng ký cleanup action ngay lập tức.
5. Tạo resource phụ thuộc tiếp theo.
6. Khi test kết thúc, chạy cleanup theo LIFO.
7. Ghi nhận tất cả lỗi cleanup, không dừng ở lỗi đầu tiên.

Không đăng ký một hành động “xóa toàn bộ resource có prefix” nếu prefix có thể chứa resource do test khác tạo. Registry nên lưu ID cụ thể của từng resource.

## 15. Idempotent cleanup và thứ tự phụ thuộc

Cleanup cần có thể chạy nhiều lần mà không gây lỗi khó hiểu:

- Resource đã không tồn tại: coi là đã sạch nếu API trả NotFound.
- Resource đang được xóa: chờ trạng thái terminal trong deadline.
- Dependency chưa được tạo: không cố xóa bằng ID chưa có.
- Một cleanup action thất bại: tiếp tục chạy các action còn lại, sau đó báo lỗi tổng hợp.

Thứ tự cleanup thường là reverse dependency:

| Thứ tự tạo | Resource | Thứ tự xóa |
|---:|---|---:|
| 1 | Bucket/topic/database cha | Sau cùng |
| 2 | Object/subscription/table | Trước resource cha |
| 3 | Event/message/record | Trước object hoặc subscription |
| 4 | Listener/consumer đang chạy | Dừng trước khi xóa queue/subscription |

Không phải provider nào cũng cho xóa theo cùng một thứ tự. Đọc API cụ thể của resource và xử lý dependency như subscription, object version, child collection hoặc active consumer.

## 16. Xác minh cleanup đã hoàn tất

Lệnh delete được chấp nhận chưa chắc resource đã biến mất ngay. Một số dịch vụ có trạng thái deleting/deprovisioning hoặc có khoảng trễ nhất quán.

Sau khi gọi delete:

- Poll API get/describe/list với deadline hữu hạn.
- Xác minh resource không còn tồn tại hoặc ở trạng thái terminal.
- Với container/blob, xác minh không còn object/child resource trước khi xóa cha.
- Với queue/topic, dừng consumer và xác minh không còn subscription cần giữ.
- Với database, chờ trạng thái deleted trước khi tái sử dụng tên.

Ví dụ chờ resource không còn tồn tại bằng Awaitility:

~~~java
await()
        .alias("test queue deleted")
        .pollInterval(Duration.ofMillis(250))
        .atMost(Duration.ofSeconds(30))
        .until(() -> !queueExists(queueName));
~~~

Không dùng polling để che giấu permission error hoặc lỗi mạng. Nếu API trả lỗi không phải transient/NotFound, hãy báo cleanup thất bại và lưu resource ID để điều tra.

## 17. CI cancellation, orphan resources và janitor

`@AfterEach` và `finally` không thể đảm bảo chạy khi process bị kill -9, runner mất máy, JVM crash hoặc job bị hủy đột ngột. Cloud resource có thể còn tồn tại sau khi pipeline kết thúc.

Thiết kế hai lớp bảo vệ:

1. **Immediate cleanup:** JUnit callback/try-with-resources xóa resource trong luồng chạy bình thường.
2. **Orphan janitor:** scheduled job tìm resource test đã hết hạn và xóa theo ownership metadata.

Janitor nên:

- Chỉ quét account/project/subscription chuyên dụng cho test.
- Chỉ xóa resource có `managed-by=integration-tests` hoặc registry ownership hợp lệ.
- Kiểm tra `expires-at` đã qua và resource không được gia hạn.
- Có dry-run mode và log đầy đủ trước khi bật delete.
- Xóa theo dependency order và giới hạn concurrency.
- Báo cáo resource không xóa được để người sở hữu xử lý.

TTL tag/label không phải dịch vụ tự xóa trên mọi provider. Cần một scheduled cleanup process hoặc policy lifecycle cụ thể. Không đặt TTL rồi giả định cloud tự động xóa nếu resource type không hỗ trợ.

## 18. Bảo mật, chi phí và giới hạn tài nguyên

Test resource vẫn là cloud resource thật, có thể phát sinh chi phí hoặc mở quyền truy cập. Áp dụng:

- Dùng account/project/subscription riêng cho integration test khi có thể.
- Dùng role/service principal/service account giới hạn quyền tạo và xóa đúng loại resource.
- Không cấp quyền xóa resource production cho CI.
- Dùng network boundary và secret store cho credential.
- Không lưu dữ liệu production hoặc PII vào test fixture.
- Đặt quota/concurrency limit để nhiều test không tạo hàng nghìn resource đồng thời.
- Đặt expiration metadata và có orphan cleanup.
- Theo dõi chi phí và số resource còn tồn tại sau mỗi CI run.

Nếu test cần kiểm tra IAM/policy, dùng một account/project test với policy riêng và kiểm tra cả positive lẫn negative permission. Cleanup identity phải có đủ quyền xóa resource test, nhưng không nên có quyền quản trị toàn subscription/account.

## 19. Troubleshooting và bài tập thực hành

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test chạy riêng pass nhưng suite fail | Resource name hoặc dữ liệu bị chia sẻ | Dùng run/test ID riêng và cleanup từng method |
| CI có resource trùng tên | Nhiều worker dùng cùng prefix cố định | Thêm run ID, worker ID và random suffix |
| S3 bucket không xóa được | Còn object, version, delete marker hoặc multipart upload | Dọn child resource trước bucket |
| Azure container cùng tên tạo lại bị 409 | Delete chưa hoàn tất hoặc tên đang trong cooldown | Dùng tên mới và poll trạng thái |
| Pub/Sub topic đã xóa nhưng subscription còn | Xóa topic không xóa subscription | Xóa subscription độc lập trước topic |
| GCS bucket delete thất bại | Bucket còn live/noncurrent object | Liệt kê và xóa object/version đúng prefix |
| Firestore document cha đã xóa nhưng dữ liệu còn | Subcollection không tự bị xóa theo document cha | Cleanup đệ quy subcollection |
| Cleanup fail làm mất lỗi assertion gốc | Teardown ném exception thay thế test failure | Gắn cleanup error dạng suppressed và lưu log |
| Resource còn sau khi CI bị hủy | Lifecycle callback không chạy | Dùng tag/label expires-at và orphan janitor |
| Testcontainers dừng giữa các class | Extension kết thúc container nhưng Spring context được cache | Dùng singleton lifecycle phù hợp hoặc context riêng |
| Test song song xóa nhầm resource | Cleanup dùng prefix/wildcard rộng | Lưu resource ID cụ thể và kiểm tra ownership |

### Bài tập A — Resource name

Viết helper tạo bucket/container/queue name từ CI run ID, test method và UUID. Kiểm tra tên đầu ra theo quy tắc của S3, Azure Blob Container và Pub/Sub topic.

### Bài tập B — Cleanup registry

Viết `TestResourceScope` hỗ trợ đăng ký cleanup action, chạy theo LIFO và gom exception bằng suppressed exceptions. Kiểm tra cleanup vẫn chạy các action còn lại khi một action thất bại.

### Bài tập C — S3

Tạo bucket riêng, upload nhiều object, kiểm tra dữ liệu và cleanup. Thêm case versioning để xóa mọi object version/delete marker trước khi xóa bucket.

### Bài tập D — Messaging

Tạo SQS queue hoặc Pub/Sub topic/subscription. Dừng consumer, xóa subscription/queue theo dependency order và xác minh resource không còn tồn tại.

### Bài tập E — Azure

Tạo Blob container và Service Bus queue riêng. Cleanup container/queue sau test; quan sát việc tạo lại Blob container cùng tên trong khoảng thời gian delete đang được xử lý.

### Bài tập F — Orphan janitor

Tạo resource có `managed-by`, `test-run-id` và `expires-at`. Viết chế độ dry-run liệt kê resource hết hạn, sau đó thêm delete có kiểm tra project/account allowlist.

### Câu hỏi tự kiểm tra

1. **Container lifecycle có thay thế cloud resource cleanup không?** Không; container và resource cloud có vòng đời độc lập.
2. **Vì sao resource cần tên duy nhất?** Để tránh collision và hỗ trợ truy vết giữa test/CI worker.
3. **Tại sao cleanup nên chạy theo LIFO?** Resource con thường phụ thuộc resource cha; xóa con trước giúp tránh lỗi dependency.
4. **Khi nào dùng static `@Container`?** Khi hạ tầng có thể dùng chung cho test class; dữ liệu vẫn phải được cô lập.
5. **Testcontainers JUnit 5 có bảo đảm chạy song song không?** Tài liệu hiện hành nói extension đã được kiểm thử với execution tuần tự; parallel có thể gây side effect.
6. **S3 bucket có thể xóa khi còn object không?** Không; phải xóa object và các version/delete marker trước.
7. **Xóa Pub/Sub topic có xóa subscription không?** Không; subscription cần được xóa riêng.
8. **GCS bucket cần điều kiện gì trước khi xóa?** Bucket phải rỗng đối với live/noncurrent objects theo API delete.
9. **Vì sao `@AfterEach` chưa đủ?** Process có thể bị kill hoặc runner mất trước khi callback chạy.
10. **Orphan janitor cần kiểm tra gì?** Ownership, project/account allowlist, expiration và dependency trước khi xóa.
11. **Làm sao tránh cleanup nhầm resource khác?** Lưu ID cụ thể, kiểm tra tag/label ownership và giới hạn phạm vi account/project.
12. **Vì sao phải xác minh sau delete?** Một số dịch vụ xóa bất đồng bộ hoặc có khoảng trễ trước khi resource không còn được nhìn thấy.

## 20. Tổng kết

Tạo tài nguyên biệt lập và cleanup có kiểm soát là điều kiện để integration test có thể chạy lặp lại, song song và trên CI mà không làm nhiễu lẫn nhau. Hãy chọn phạm vi cô lập phù hợp, tạo resource name từ run/test ID, gắn ownership metadata và đăng ký cleanup ngay sau khi resource được tạo.

JUnit lifecycle và Testcontainers quản lý vòng đời test/container; registry `AutoCloseable` giúp cleanup theo LIFO và vẫn chạy các action còn lại khi có lỗi. Với AWS cần xóa object/version trước bucket; với Azure cần xử lý blob/container và Service Bus entity theo dependency; với Google Cloud cần xóa subscription trước topic, làm rỗng bucket và dọn document/subcollection đúng cách.

Cleanup tức thời cần được bổ sung bằng orphan janitor vì process có thể bị hủy đột ngột. Chỉ xóa resource thuộc test run, kiểm tra account/project/subscription đích, xác minh delete hoàn tất và dùng quyền tối thiểu. Cách làm này giữ test data độc lập, giảm chi phí tài nguyên bị bỏ quên và giúp kết quả kiểm thử đáng tin cậy hơn.

### Tài liệu tham khảo chính thức

- [Testcontainers for Java — JUnit 5 lifecycle](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [JUnit 5 — BeforeEach](https://docs.junit.org/5.11.4/api/org.junit.jupiter.api/org/junit/jupiter/api/BeforeEach.html)
- [AWS SDK for Java 2.x — S3 delete bucket behavior](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/s3/S3AsyncClient.html)
- [AWS SDK for Java 2.x — SQS examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sqs_code_examples.html)
- [Microsoft Learn — Azure Blob Storage Java quickstart](https://learn.microsoft.com/en-us/azure/storage/storage-java-how-to-use-blob-storage)
- [Microsoft Learn — Delete Blob Container](https://learn.microsoft.com/en-us/rest/api/storageservices/delete-container)
- [Azure SDK for Java — Service Bus administration client](https://learn.microsoft.com/en-us/java/api/com.azure.messaging.servicebus.administration?view=azure-java-stable)
- [Google Cloud — Delete Pub/Sub subscriptions](https://docs.cloud.google.com/pubsub/docs/delete-subscriptions)
- [Google Cloud — Delete Pub/Sub topics](https://docs.cloud.google.com/pubsub/docs/delete-topic)
- [Google Cloud — Delete Cloud Storage buckets](https://docs.cloud.google.com/storage/docs/deleting-buckets)
- [Google Cloud — Delete Cloud Storage objects](https://docs.cloud.google.com/storage/docs/deleting-objects)
- [Firebase — Delete Cloud Firestore data](https://firebase.google.com/docs/firestore/manage-data/delete-data)


