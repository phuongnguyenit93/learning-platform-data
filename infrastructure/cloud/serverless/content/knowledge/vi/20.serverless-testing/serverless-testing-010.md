# Quản lý test data và dọn tài nguyên sau kiểm thử

Kiểm thử serverless thường tạo ra nhiều dữ liệu và tài nguyên hơn một bài unit test thông thường. Một kịch bản có thể tạo HTTP request, message trong queue, event trên bus, object trong storage, record trong database, function tạm thời, log, subscription và tài nguyên tích hợp. Nếu dữ liệu không được cô lập hoặc tài nguyên không được dọn sau khi chạy, các lần test sẽ ảnh hưởng lẫn nhau, kết quả khó tái lập, chi phí tăng và môi trường kiểm thử dần trở thành một hệ thống khó kiểm soát.

Quản lý test data và cleanup cần được thiết kế như một phần của test lifecycle: tạo dữ liệu có chủ đích, gắn định danh cho lần chạy, giữ isolation giữa test song song, đợi xử lý bất đồng bộ hoàn tất, dọn đúng phạm vi và xác minh không còn tài nguyên ngoài dự kiến. Với Java function kích hoạt bởi HTTP, message hoặc event, điều này đặc biệt quan trọng vì một test có thể tạo side effect ở nhiều service và một invocation có thể tiếp tục xử lý sau khi test method đã kết thúc.

## 1. Mục tiêu của test data management

Một chiến lược test data tốt cần đáp ứng các mục tiêu:

- **Deterministic:** cùng fixture, input và cấu hình phải tạo kết quả có thể dự đoán.
- **Isolated:** một test run không đọc, sửa hoặc xóa dữ liệu của test run khác.
- **Representative:** dữ liệu phản ánh các trường hợp nghiệp vụ quan trọng, gồm biên, lỗi và dữ liệu thiếu.
- **Safe:** không để lộ dữ liệu production, secret hoặc thông tin cá nhân không cần thiết.
- **Disposable:** dữ liệu và resource tạm có vòng đời, owner và cách xóa rõ ràng.
- **Traceable:** có thể tìm tất cả dữ liệu và tài nguyên do một test run tạo ra.
- **Cost-aware:** không để queue, database, log, function hoặc môi trường thử nghiệm tồn tại vô thời hạn.

Test data không chỉ là row trong database. Nó còn gồm queue message, event, object, file, secret giả, identity, webhook endpoint, API sandbox record, log và resource được tạo bởi Infrastructure as Code.

## 2. Phân loại test data

Chọn cách tạo dữ liệu dựa trên mục tiêu kiểm thử và độ nhạy:

| Loại dữ liệu | Mô tả | Trường hợp sử dụng | Lưu ý |
|---|---|---|---|
| Synthetic data | Dữ liệu được tạo mới, không đại diện cho người thật | Unit, integration, load và end-to-end test | Nên dùng mặc định |
| Fixture | Bộ dữ liệu cố định, có tên và phiên bản | Regression, contract và scenario test | Lưu cùng source hoặc test artifact |
| Generated data | Dữ liệu tạo theo seed, kích thước và quy tắc | Boundary, property-based và load test | Ghi seed để tái lập |
| Masked data | Dữ liệu thật đã che hoặc thay trường nhạy cảm | Test tương thích với phân bố dữ liệu thực | Cần kiểm tra khả năng tái nhận diện |
| Anonymized data | Dữ liệu đã được xử lý để không còn nhận diện cá nhân theo tiêu chuẩn áp dụng | Một số kiểm thử phân tích | Không tự mặc định masking đồng nghĩa anonymization |
| Snapshot/copy | Bản sao từ môi trường khác | Migration hoặc compatibility test | Kiểm soát nguồn, quyền, retention và xóa |

Ưu tiên synthetic data. Pseudonymized hoặc masked data vẫn có thể là dữ liệu cá nhân nếu có thể liên kết ngược hoặc tái nhận diện. Nếu buộc phải dùng bản sao dữ liệu thật, cần phê duyệt, giảm trường dữ liệu, tách quyền truy cập, mã hóa và có lịch xóa rõ ràng.

### Tạo fixture có ý nghĩa nghiệp vụ

Fixture nên mô tả scenario chứ không chỉ là một tập giá trị ngẫu nhiên. Ví dụ với quy trình đặt hàng:

| Fixture | Mục đích |
|---|---|
| `order-standard` | Đơn hàng hợp lệ, tồn kho đủ, thanh toán thành công |
| `order-no-stock` | Kiểm tra từ chối khi không đủ hàng |
| `order-payment-timeout` | Kiểm tra kết quả chưa xác định và retry idempotent |
| `order-duplicate-event` | Kiểm tra consumer nhận cùng event nhiều lần |
| `order-cross-tenant` | Kiểm tra cô lập dữ liệu tenant |
| `order-invalid-schema` | Kiểm tra xử lý message sai schema và DLQ |

Tên fixture nên ổn định, dữ liệu có thể đọc hiểu và không phụ thuộc vào thứ tự test chạy. Tránh dùng một record mutable chung cho nhiều test; test này có thể thay đổi dữ liệu mà test khác đang giả định.

## 3. Thiết kế test data theo từng cấp kiểm thử

Không phải mọi loại test đều cần tạo resource cloud thật.

| Cấp test | Test data phù hợp | Resource nên dùng |
|---|---|---|
| Unit test | Object/fixture trong bộ nhớ | Fake, stub hoặc mock dependency |
| Component test | Dataset nhỏ, schema thật | Database local/container hoặc emulator |
| Integration test | Dữ liệu cô lập theo test run | Resource cloud test riêng hoặc container |
| Contract test | Event/request mẫu có version | Schema registry hoặc contract artifact |
| End-to-end test | Scenario xuyên nhiều service | Stack/môi trường tạm có namespace riêng |
| Load test | Dataset lớn, có thể sinh theo seed | Môi trường load test riêng, quota được giới hạn |
| Resilience test | Dữ liệu lỗi, duplicate, poison và timeout | Queue/DLQ và dependency sandbox |

Unit test không nên tạo queue cloud thật chỉ để kiểm tra một hàm Java. Ngược lại, test event source mapping, IAM permission, retry và DLQ cần integration test trên AWS/Azure/GCP hoặc môi trường mô phỏng có giới hạn rõ. Emulator giúp tăng tốc nhưng không bảo đảm giống hoàn toàn dịch vụ thật; vẫn cần một bộ kiểm thử cloud thực tế.

## 4. Namespace cho mỗi test run

Khi CI chạy nhiều job hoặc nhiều test song song, dùng một namespace duy nhất cho mỗi run. Namespace có thể là UUID, CI run ID kết hợp attempt ID, hoặc một mã ngắn được tạo từ build và worker.

Ví dụ:

```text
testRunId = ci-4821-attempt-2
tenantId  = test-ci-4821-attempt-2
orderId   = test-ci-4821-attempt-2-order-001
queue     = orders-test-ci-4821-attempt-2
bucketKey = test/ci-4821-attempt-2/orders/order-001.json
```

Mọi tài nguyên và dữ liệu do test tạo ra cần mang định danh này theo cách phù hợp:

- Database record có `testRunId`, tenant test hoặc partition/prefix riêng.
- S3/object storage dùng prefix theo test run.
- Event body có metadata test run hoặc correlation ID dành cho kiểm thử.
- Queue/topic/rule/resource tạm có tên hoặc tag chứa test run ID.
- Log và trace ghi `testRunId` để lọc được hoạt động của một lần test.
- Secret/config giả dùng tên và scope riêng, không ghi giá trị thật vào tag.

`testRunId` chỉ phục vụ isolation và cleanup, không phải credential hoặc bằng chứng authorization. Không cho phép caller chỉ cần gửi một `testRunId` bất kỳ là có thể xóa dữ liệu của người khác. Cleanup service phải kiểm tra ownership và scope được tạo bởi chính test run.

### Đặt tên và tag tài nguyên

Một bộ tag/label phổ biến:

| Key | Giá trị ví dụ | Mục đích |
|---|---|---|
| `managed-by` | `integration-test` | Phân biệt resource do test tạo |
| `test-run-id` | `ci-4821-attempt-2` | Nhóm resource theo run |
| `owner` | `orders-platform-ci` | Xác định nhóm chịu trách nhiệm |
| `created-at` | timestamp UTC | Điều tra resource tồn đọng |
| `expires-at` | timestamp UTC | Cho janitor biết thời điểm có thể xóa |
| `environment` | `ephemeral-test` | Phân biệt với staging/production |

Không phải mọi resource cloud đều hỗ trợ tag/label giống nhau. Với resource không tag được, lưu resource ID/ARN/URL vào manifest của test run hoặc đặt tên resource có prefix riêng. Manifest cũng giúp cleanup theo đúng danh sách đã tạo, thay vì tìm và xóa theo một điều kiện quá rộng.

## 5. Tạo dữ liệu deterministic

Test cần tái lập được khi thất bại trên CI. Ghi nhận các yếu tố ảnh hưởng kết quả:

- Fixture version hoặc commit SHA.
- Random seed dùng để sinh dữ liệu.
- Thời điểm cố định hoặc `Clock` được inject.
- Locale, timezone, currency và định dạng số.
- Event schema version và serialization options.
- Feature flags và app configuration.
- Phiên bản dependency/emulator/runtime.

Không dùng `Instant.now()` rải rác trong domain logic nếu test cần kết quả ổn định. Inject `Clock` để kiểm soát thời gian. Với dữ liệu random, tạo seed từ test case hoặc nhận seed từ CI; khi test fail, ghi seed vào log để tái chạy.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock testClock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC);
```

Tránh phụ thuộc thứ tự tạo ID, thứ tự record trả về hoặc thứ tự message đến nếu nghiệp vụ không đảm bảo những điều đó. Khi cần sắp xếp, khai báo sort key rõ ràng trong query hoặc assertion.

## 6. Cô lập dữ liệu trong database

Có một số cách cô lập thường dùng:

1. **Database/schema riêng:** tốt cho integration/E2E test có quyền tạo và xóa schema.
2. **Tenant hoặc partition riêng:** phù hợp khi test nhiều run cùng dùng một database; mọi query phải ràng buộc namespace.
3. **Table/prefix riêng:** dùng cho dữ liệu tạm hoặc object storage.
4. **Transaction rollback:** phù hợp với test đồng bộ trong cùng transaction; không đủ cho side effect ngoài database hoặc worker bất đồng bộ.
5. **Ephemeral database/container:** tạo mới cho test suite rồi hủy sau khi hoàn tất.

Không dựa vào cleanup để bù cho isolation yếu. Nếu test run A và B có thể đọc hoặc xóa record của nhau, một cleanup sai điều kiện có thể phá dữ liệu của run đang hoạt động.

### Cleanup theo testRunId

Mọi insert trong integration test nên gắn namespace. Repository cleanup cần dùng điều kiện chính xác, giới hạn batch và có thể chạy lại an toàn.

```java
public interface TestDataRepository {
    void deleteByTestRunId(String testRunId);
    long countByTestRunId(String testRunId);
}

public final class TestDataCleanup {
    private final TestDataRepository repository;

    public TestDataCleanup(TestDataRepository repository) {
        this.repository = repository;
    }

    public void cleanup(String testRunId) {
        if (testRunId == null
                || !testRunId.matches("(ci|it)-[A-Za-z0-9-]{1,80}")) {
            throw new IllegalArgumentException("Invalid test run namespace");
        }
        repository.deleteByTestRunId(testRunId);
    }
}
```

Đoạn code chỉ minh họa contract. Trong triển khai thực tế, repository cần giới hạn quyền xóa vào bảng/schema test, dùng parameterized query, xử lý pagination/batch và xác minh tenant/owner. Prefix kiểm tra không phải biện pháp authorization; quyền xóa phải được giới hạn bằng database role và resource scope.

### Dùng TTL đúng cách

TTL hữu ích để tự động xóa dữ liệu tạm khi cleanup chủ động không chạy. Tuy nhiên, TTL ở nhiều dịch vụ là eventual cleanup, không phải timer chính xác. Ví dụ DynamoDB TTL xóa item bất đồng bộ sau khi hết hạn; item có thể còn tồn tại và vẫn được đọc trong một khoảng thời gian.

Vì vậy:

- Dùng cleanup chủ động sau test để giữ môi trường sạch nhanh.
- Dùng TTL làm lớp bảo vệ thứ hai cho dữ liệu bị bỏ sót.
- Không viết assertion yêu cầu record biến mất đúng giây TTL hết hạn.
- Không dùng TTL làm cơ chế authorization hoặc xóa dữ liệu nhạy cảm theo deadline chính xác.
- Nếu dữ liệu có quan hệ, kiểm tra thứ tự xóa hoặc thiết kế cascade/cleanup job phù hợp.

## 7. Quản lý dữ liệu cho queue và event

Message bất đồng bộ có vòng đời riêng. Test có thể kết thúc trong khi message vẫn nằm trong queue hoặc consumer đang xử lý. Nếu dùng queue chung, message cũ có thể bị test tiếp theo nhận hoặc cleanup có thể xóa message của run khác.

Các nguyên tắc:

- Dùng queue/topic/event bus hoặc subscription riêng cho test run khi có thể.
- Nếu buộc dùng broker chung, gắn `testRunId` và lọc consumer theo namespace; không dựa vào filter như cơ chế bảo mật.
- Dùng event ID ổn định để kiểm tra duplicate và idempotency.
- Đợi consumer hoàn tất bằng trạng thái/ack quan sát được, không dùng `Thread.sleep` cố định.
- Giới hạn thời gian chờ và khi hết hạn ghi lại message ID, correlation ID, queue depth và trạng thái worker.
- Xử lý message lỗi trong DLQ theo test run; cleanup DLQ chỉ khi chắc chắn message thuộc run đó.
- Dọn subscription, rule và event source mapping tạm sau khi producer đã ngừng gửi.

### Không purge queue dùng chung

Purge toàn bộ SQS queue có thể xóa message của test khác hoặc workload khác và không thể chọn chỉ message theo `testRunId`. Không dùng `PurgeQueue` trên queue dùng chung để cleanup một test. Dùng queue riêng cho test run hoặc thiết kế consumer/drain có điều kiện. Nếu cần purge, chỉ thực hiện trên queue ephemeral do test sở hữu và sau khi đã xác minh không có consumer/test khác dùng nó.

Tương tự, không xóa toàn bộ topic, event bus hoặc subscription shared chỉ vì một test hoàn tất. Hãy xóa đúng resource tạm do run tạo và giữ các resource dùng chung.

## 8. Quản lý object storage và file test

Object storage thường chứa file upload, payload event, export và artifact. Dùng prefix riêng theo run, ví dụ:

```text
test-data/<testRunId>/input/
test-data/<testRunId>/expected/
test-data/<testRunId>/output/
```

Cleanup chỉ xóa prefix của run. Với bucket versioning, xóa object hiện tại có thể tạo delete marker trong khi các version cũ vẫn còn; muốn xóa hoàn toàn cần xử lý object versions và delete markers theo đúng retention policy. Với object lock hoặc legal hold, không được bỏ qua chính sách lưu giữ để dọn test.

Nếu test tạo multipart upload, đảm bảo abort upload còn dang dở. Dùng lifecycle rule làm lớp dọn tự động cho multipart upload hoặc prefix test nếu phù hợp, nhưng không thay thế cleanup chủ động khi cần xác nhận môi trường đã sạch.

## 9. Dọn resource cloud theo cấp sở hữu

Có hai chiến lược chính:

### Ephemeral stack/project/resource group

Tạo một đơn vị hạ tầng tạm cho mỗi test suite hoặc test run, rồi xóa đơn vị đó sau khi kiểm thử. Ví dụ:

- AWS: CloudFormation/SAM stack riêng với tên chứa run ID.
- Azure: Resource Group riêng cho một suite hoặc run.
- Google Cloud: project riêng khi nhu cầu isolation đủ lớn và quota/quy trình tổ chức cho phép.

Ưu điểm là cleanup theo ownership boundary, dễ phát hiện tài nguyên bị bỏ sót. Nhược điểm là tạo/xóa stack có thể chậm, tốn quota và có tài nguyên không thể tạo nhanh cho mỗi test case. Thường nên tạo stack cho integration suite hoặc pipeline job, không tạo toàn bộ cloud environment cho từng unit test.

### Shared test environment với namespace

Một số tài nguyên tốn thời gian hoặc chi phí có thể được dùng chung, nhưng dữ liệu cần namespace riêng. Ví dụ một database test dùng nhiều schema/tenant test, hoặc một queue test chuyên dụng dùng nhiều message có run ID. Cần giới hạn quyền xóa theo namespace và có janitor dọn những run hết hạn.

Không đặt production resource trong cùng cleanup scope với test. Một lệnh xóa resource group/stack/project có thể xóa tất cả tài nguyên bên trong; chỉ dùng đơn vị ephemeral khi ownership đã rõ và không chứa resource dùng chung.

## 10. AWS: stack tạm, tags, SQS và storage

Với AWS SAM, có thể triển khai một stack cho mỗi CI run:

```bash
sam build
sam deploy \
  --stack-name orders-it-ci-4821-attempt-2 \
  --parameter-overrides EnvironmentName=test \
  --no-confirm-changeset
```

Sau khi test hoàn tất, xóa stack bằng:

```bash
sam delete --stack-name orders-it-ci-4821-attempt-2
```

Trong CI, luôn truyền stack name duy nhất. Kiểm tra CloudFormation deletion policy, retain policy và tài nguyên có dữ liệu cần giữ trước khi xóa. `sam delete` không đảm bảo mọi resource ngoài stack hoặc resource được retain sẽ tự biến mất.

Các tài nguyên AWS cần chú ý:

- **SQS:** queue riêng cho run; xóa queue sau khi consumer dừng và message đã được xử lý/được chủ động loại bỏ.
- **SNS:** xóa subscription/topic do run tạo; không xóa topic shared.
- **EventBridge:** xóa rule, target và event bus tạm theo đúng thứ tự; archive/replay có retention riêng.
- **S3:** dùng prefix; xử lý versioning/delete markers và multipart upload.
- **DynamoDB:** gắn test run ID, cleanup bằng batch delete hoặc TTL; TTL không tức thời.
- **Lambda:** function, layer/version/alias và event source mapping do stack tạo; xem xét log group có thể còn lại tùy cấu hình.
- **CloudWatch Logs:** đặt retention ngắn cho test; xóa log group chỉ khi thuộc stack/run và không cần điều tra.

Tag resource bằng `test-run-id`, `owner`, `expires-at` và stack name khi loại resource hỗ trợ tagging. Với tài nguyên không có tag hoặc không thuộc stack, lưu ARN/ID trong manifest.

## 11. Azure và Google Cloud: cleanup theo resource group/project

### Azure

Một Resource Group riêng có thể gom Function App, Storage Account, Service Bus namespace, Application Insights và các resource phụ trợ của một test suite. Khi test hoàn tất, xóa resource group nếu toàn bộ resource bên trong đều thuộc suite đó.

Nếu resource được chia sẻ, đặt nó ở resource group riêng và chỉ tạo resource tạm trong group ephemeral. Dùng tags như `testRunId`, `owner`, `expiresAt` khi resource hỗ trợ. Không giả định xóa Resource Group sẽ xóa tài nguyên ngoài group như role assignment, DNS record hoặc external resource đã được tham chiếu.

### Google Cloud

Project riêng cung cấp ranh giới mạnh cho API, IAM, billing và quota, nhưng tạo/xóa project có quy trình và thời gian riêng. Chỉ dùng project ephemeral cho test suite hoặc pipeline cần isolation cao. Với test thường xuyên, có thể dùng project test chuyên dụng và namespace dữ liệu/queue riêng.

Dùng labels như `test_run`, `owner` và `environment` trên resource hỗ trợ. Khi xóa project, kiểm tra resource có được chia sẻ hoặc export ra project khác không. Cloud Storage, Pub/Sub, Cloud Run/Functions, Eventarc và log sink có thể có lifecycle khác nhau; manifest và cleanup verification vẫn cần thiết.

## 12. Java/JUnit: quản lý lifecycle bằng setup và teardown

JUnit cung cấp `@BeforeEach`, `@AfterEach`, `@BeforeAll` và `@AfterAll` để quản lý dữ liệu và resource. `@AfterEach` hữu ích cho cleanup thông thường, nhưng không đủ khi JVM bị kill, runner mất kết nối hoặc pipeline bị hủy. Vì vậy cần kết hợp cleanup trong test process với TTL/janitor bên ngoài.

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import java.util.UUID;

class OrderIntegrationTest {
    private String testRunId;
    private TestDataFixture fixture;

    @BeforeEach
    void setUp() {
        testRunId = "ci-" + UUID.randomUUID();
        fixture = new TestDataFixture(testRunId);
        fixture.createCustomerAndInventory();
    }

    @AfterEach
    void tearDown() {
        if (fixture != null) {
            fixture.cleanup();
        }
    }
}
```

Ví dụ trên minh họa lifecycle. `fixture.cleanup()` phải idempotent, giới hạn vào namespace của test và không ném lỗi che mất assertion failure ban đầu. Nếu cleanup thất bại, ghi rõ test run ID và resource còn sót để janitor xử lý.

### Cleanup không được che lỗi gốc

Nếu test fail và cleanup cũng fail, giữ cả hai thông tin. Có thể gắn cleanup exception làm suppressed exception hoặc log nó như lỗi phụ, nhưng không được biến một test fail thành pass. Dùng timeout cho cleanup để pipeline không treo vô hạn.

```java
@Test
void processesOrderAndCleansFixture() throws Exception {
    try (TestFixtureScope ignored = fixture.openScope()) {
        runAssertions();
    }
}
```

`TestFixtureScope` triển khai `AutoCloseable` và `close()` gọi cleanup có giới hạn theo test run. Java try-with-resources tự giữ exception từ assertion làm lỗi chính và gắn exception phát sinh khi `close()` thất bại vào danh sách suppressed. Nhờ vậy cleanup failure không âm thầm biến test fail thành pass hoặc che mất nguyên nhân ban đầu.

## 13. Java: test fixture với test run namespace

Tạo một context nhỏ để mọi repository, event publisher và resource helper dùng chung test run ID:

```java
import java.util.UUID;

public record TestRunContext(String id) {
    public static TestRunContext create() {
        return new TestRunContext("it-" + UUID.randomUUID());
    }

    public String resourceName(String base) {
        return base + "-" + id;
    }

    public String objectPrefix() {
        return "test-data/" + id + "/";
    }
}
```

Các test chạy song song sẽ có namespace khác nhau. Nếu cần tên resource cloud tuân theo giới hạn ký tự, chuẩn hóa và rút gọn ID nhưng vẫn giữ một mapping về test run ID đầy đủ trong manifest.

Fixture nên cung cấp các thao tác rõ như `createOrder`, `publishOrderCreated`, `awaitOrderStatus` và `cleanup`. Tránh một `TestUtils` khổng lồ có thể xóa database hoặc queue tùy ý; helper càng rộng càng dễ gây cleanup nhầm.

## 14. Dọn dữ liệu và tài nguyên theo thứ tự phụ thuộc

Cleanup cần tôn trọng dependency graph. Với một test order flow:

1. Ngừng producer hoặc trigger để không tạo thêm event mới.
2. Đợi worker hoàn tất hoặc dừng event source mapping/consumer tạm theo thiết kế.
3. Thu thập kết quả cuối, log, trace và DLQ cần điều tra.
4. Xóa message/event test còn lại trong queue riêng của run.
5. Xóa record database, object và file tạm.
6. Xóa subscription, rule, mapping và resource phụ thuộc.
7. Xóa function, queue, topic, storage và stack ephemeral.
8. Xác minh resource đã xóa hoặc ghi lại phần được retain có chủ đích.

Thứ tự chính xác phụ thuộc resource. Ví dụ, phải xóa EventBridge target trước rule; dừng producer trước khi xóa queue; không xóa database trước khi worker đã ngừng ghi. Lưu manifest resource ID để cleanup không phải dò tìm mù.

### Cleanup là một thao tác idempotent

Cleanup có thể chạy nhiều lần do retry của CI hoặc janitor. Nếu resource đã bị xóa, thao tác nên xem đó là kết quả thành công khi phù hợp. Nếu resource vẫn tồn tại nhưng không thuộc test run, cleanup phải dừng và báo lỗi.

Không dùng wildcard xóa như `DELETE FROM orders` hoặc `aws sqs purge-queue` trên resource shared. Luôn yêu cầu namespace và scope cụ thể; kiểm tra ownership trước khi xóa.

## 15. Asynchronous test và chờ điều kiện hoàn tất

Một HTTP function có thể trả `202 Accepted` ngay sau khi enqueue message. Test phải chờ worker xử lý xong trước khi assert database hoặc cleanup. Dùng polling theo điều kiện với deadline, không dùng sleep cố định dài.

Ví dụ helper chờ trạng thái:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.function.Supplier;

public final class Await {
    public static <T> T until(
            Supplier<T> read,
            java.util.function.Predicate<T> condition,
            Duration timeout,
            Duration interval) throws InterruptedException {

        Instant deadline = Instant.now().plus(timeout);
        T last = null;
        while (Instant.now().isBefore(deadline)) {
            last = read.get();
            if (condition.test(last)) {
                return last;
            }
            Thread.sleep(interval.toMillis());
        }
        throw new AssertionError("Condition not met before timeout; last=" + last);
    }

    private Await() {}
}
```

Trong code production test, nên inject `Clock` hoặc dùng thư viện polling để kiểm soát thời gian và ghi lại số lần poll. `Thread.sleep` trong ví dụ chỉ là khoảng nghỉ ngắn giữa các lần đọc; không dùng nó thay cho việc kiểm tra trạng thái. Khi timeout, ghi correlation ID, test run ID, queue depth, message ID và trạng thái function để điều tra.

Không cleanup ngay sau khi gửi message. Trước tiên xác nhận consumer đã commit side effect hoặc đã chuyển message sang DLQ theo kịch bản đang kiểm thử. Nếu test cố ý kiểm tra timeout/retry, cleanup cần dừng hoặc cô lập worker trước khi xóa dữ liệu liên quan.

## 16. Testcontainers và emulator

Testcontainers giúp tạo dependency như PostgreSQL, Redis hoặc local broker trong container cho integration test Java. Container thường được khởi động trước suite và dừng sau suite; dữ liệu được cô lập bằng database/schema riêng hoặc container riêng.

Emulator/local service có thể hữu ích cho:

- Kiểm thử serialization và application logic.
- Kiểm tra query/repository với database thật cùng loại.
- Kiểm tra message contract, routing logic hoặc event handler.
- Tăng tốc test chạy trên mỗi commit.

Nhưng emulator không chứng minh IAM/resource policy, managed identity, network routing, quota, retry semantics hoặc service-specific edge case của cloud thật. Duy trì một integration suite nhỏ trên account/project/subscription test để kiểm tra hành vi thực tế.

Không dùng credential production trong emulator hoặc local test. Dùng profile riêng, fake credential và endpoint local rõ ràng; fail fast nếu test vô tình trỏ đến production account/resource.

## 17. Dọn tài nguyên khi CI bị hủy hoặc runner gặp sự cố

`@AfterEach` không chạy nếu process bị kill, máy runner mất điện hoặc job bị hủy cứng. Vì vậy, cleanup cần có cơ chế ngoài test process.

### TTL và janitor job

Một janitor chạy định kỳ tìm resource có `managed-by=integration-test` và `expires-at` đã quá hạn. Trước khi xóa, janitor xác minh:

- Resource thuộc account/project/subscription test được cho phép.
- Owner và test run ID tồn tại trong manifest hoặc metadata.
- Resource không được đánh dấu `retain=true` hoặc đang được job khác gia hạn lease.
- Resource không chứa dữ liệu cần giữ để điều tra incident.
- Thời gian hết hạn đã qua một grace period để tránh xóa job đang chạy chậm.

Janitor cần quyền xóa hẹp, audit log và chế độ dry-run. Không cấp quyền xóa mọi resource trong production organization chỉ để dọn test. Có thể bắt đầu bằng báo cáo resource quá hạn, sau đó bật auto-delete trong account/project riêng.

### Lease/heartbeat cho test run dài

Test suite có thể gia hạn `expires-at` trong lúc hoạt động. Janitor chỉ xóa khi lease hết hạn và không có heartbeat gần đây. Dùng thời gian UTC và đồng bộ clock. Lease không thay thế ownership check; nó chỉ giúp phân biệt run đang hoạt động với run bị bỏ dở.

### CI cleanup stage

Pipeline nên có bước cleanup chạy cả khi test pass hoặc fail. Dùng cơ chế `always()`/post-job/finally của CI provider phù hợp. Cleanup stage cần nhận stack name và manifest từ bước setup, đồng thời lưu log/diagnostic trước khi xóa resource.

## 18. Tài nguyên cần kiểm kê trước khi xóa

Checklist resource serverless thường bị bỏ sót:

| Nhóm | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Compute | Lambda, Function App, Cloud Run/Functions | Version, alias, revision, deployment slot và trigger |
| API | API Gateway route, Function URL, HTTP endpoint | Stage, mapping, authorizer, custom domain association |
| Messaging | SQS, SNS, Pub/Sub, Service Bus, Event Grid | Queue/subscription, backlog, DLQ, retention và policy |
| Event routing | EventBridge rule/bus/archive, Eventarc trigger | Target, permission, replay và event source mapping |
| Storage | S3, Blob Storage, Cloud Storage | Object, version, delete marker, multipart upload, lifecycle |
| Database | DynamoDB, Cosmos DB, Cloud SQL, RDS | Test record, table/schema, snapshot và backup retention |
| Security | IAM role, service account, managed identity, secret | Role assignment, trust, access policy, secret version và key |
| Observability | Log group, dashboard, alarm, trace | Retention, subscription filter, metric alarm và export |
| Network | Security group, endpoint, VPC connector, DNS record | Resource shared, attachment, route và private zone |
| Build/test | Artifact bucket, image, temporary registry tag | Artifact retention và image cleanup |

Không xóa security/audit log trước khi hoàn thành điều tra. Một số resource có deletion protection, retention lock hoặc soft delete; cần tuân theo policy thay vì cố vượt qua.

## 19. Cleanup an toàn cho external side effects

Một số side effect không thể xóa bằng cách xóa resource test:

- Email/SMS đã gửi đến người nhận thật.
- Payment đã authorize/capture.
- Webhook đã được gửi đến đối tác.
- File đã được tải xuống hoặc sao chép ra hệ thống khác.
- Event đã được consumer ngoài test nhận.

Dùng sandbox account, test recipient, fake provider hoặc stub server. Nếu bắt buộc gọi sandbox payment, dùng token/test card của provider và xác nhận không tạo giao dịch thật. Gắn metadata test run vào request khi provider hỗ trợ. Với webhook, gửi đến endpoint giả hoặc allowlist host test.

Không coi cleanup database là rollback cho side effect bên ngoài. Nếu test tạo side effect có thể đảo ngược, định nghĩa compensation rõ (void authorization, refund sandbox, revoke token). Nếu không thể đảo ngược, thiết kế test để chỉ dùng dữ liệu và destination giả.

## 20. Bảo mật và phân quyền cho test data

Test environment không phải nơi được phép bỏ qua bảo mật. Dữ liệu test có thể chứa token, email giả nhưng hợp lệ, secret sandbox hoặc thông tin nội bộ.

- Dùng IAM role/service account riêng cho CI test và cleanup.
- Test runner chỉ có quyền tạo/xóa resource trong account/project/resource group test.
- Tách quyền chạy test khỏi quyền dọn shared environment.
- Không cho test job từ fork hoặc untrusted branch truy cập secret cloud.
- Không lưu production credential trong fixture, snapshot hoặc artifact.
- Mã hóa test data và giới hạn người có quyền đọc log/queue/DLQ.
- Mask hoặc loại bỏ dữ liệu nhạy cảm trong report và failure output.
- Audit cleanup và redrive; giữ manifest resource ID để truy vết.
- Chặn test nếu account ID, project ID hoặc subscription ID không thuộc allowlist test.

Trước thao tác xóa, kiểm tra môi trường đích bằng cấu hình được cấp từ pipeline và một allowlist tin cậy. Không dựa vào biến `ENV=dev` do test code tự đặt để quyết định có được xóa resource hay không.

## 21. Chi phí và retention

Resource test có thể phát sinh chi phí ngay cả khi không có invocation:

- Queue, topic, event bus và archive có request, storage hoặc retention cost.
- Database, cache, NAT, private endpoint và provisioned capacity có thể tính phí theo thời gian tồn tại.
- Lambda/function invocation, log, trace và metric tăng theo số lần retry.
- Object version, snapshot, backup và artifact có thể giữ dữ liệu lâu sau khi test kết thúc.
- Resource orphan không còn owner vẫn tiếp tục tiêu thụ quota hoặc tiền.

Đặt TTL/retention phù hợp cho log, object, queue, test record và artifact. Dùng budget/alert theo account/project test; theo dõi số resource ephemeral đang tồn tại, tuổi resource lâu nhất và cleanup failure rate. Đo chi phí theo pipeline run hoặc test suite để tìm nơi tạo tài nguyên không cần thiết.

Không đặt retention quá ngắn đến mức xóa bằng chứng trước khi điều tra test fail. Một chiến lược tốt giữ diagnostic artifact trong thời gian ngắn có chủ đích, rồi xóa theo lịch.

## 22. Kiểm chứng cleanup

Cleanup thành công không chỉ có nghĩa lệnh delete trả exit code 0. Cần xác minh trạng thái thực tế:

1. Resource ephemeral không còn tồn tại hoặc đã chuyển trạng thái xóa theo API provider.
2. Không còn message test trong queue/DLQ thuộc run đã kết thúc.
3. Không còn record/object test ngoài retention có chủ đích.
4. Không còn subscription, rule, mapping hoặc identity tạm không cần thiết.
5. Manifest được đánh dấu `CLEANED` hoặc ghi rõ resource retained và lý do.
6. Cleanup failure có alert hoặc được đưa vào báo cáo CI.

Một số API xóa bất đồng bộ; cần polling trạng thái với timeout. Không báo sạch ngay khi nhận HTTP 202 từ API xóa resource. Nếu provider có eventual consistency, xác minh sau một khoảng chờ có giới hạn và ghi rõ trạng thái pending khi hết deadline.

### Cleanup report

Một báo cáo cho mỗi run có thể ghi:

```json
{
  "testRunId": "ci-4821-attempt-2",
  "status": "CLEANED",
  "createdResources": 12,
  "deletedResources": 12,
  "retainedResources": [],
  "failedResources": [],
  "completedAt": "2026-11-17T12:30:00Z"
}
```

Không ghi secret hoặc payload nhạy cảm trong manifest. Manifest cần lưu resource ID, owner, creation time và cleanup result; giữ manifest theo retention để điều tra orphan.

## 23. Checklist triển khai

### Test data

- [ ] Dùng synthetic data hoặc fixture đã được phê duyệt; không sao chép PII production tùy tiện.
- [ ] Fixture có tên, version và mục tiêu nghiệp vụ rõ.
- [ ] Random seed, clock, timezone và cấu hình được cố định để tái lập.
- [ ] Mỗi test run có namespace duy nhất và được truyền qua record, event, object và log.
- [ ] Database query/cleanup luôn giới hạn theo test run hoặc schema riêng.
- [ ] Test song song không chia sẻ mutable fixture hoặc resource có thể xóa lẫn nhau.
- [ ] TTL chỉ là lớp dọn dự phòng, không dùng làm deadline xóa chính xác.

### Serverless resource

- [ ] Queue/topic/event bus và subscription được cô lập hoặc có cơ chế lọc theo namespace.
- [ ] Không purge queue hoặc xóa topic/resource dùng chung.
- [ ] Đã xử lý backlog, DLQ, retry và consumer đang chạy trước cleanup.
- [ ] Object prefix, versioning, delete marker và multipart upload được xử lý.
- [ ] Ephemeral stack/project/resource group không chứa tài nguyên shared.
- [ ] Resource manifest có ID, owner, testRunId và expiresAt.

### Lifecycle và cleanup

- [ ] Setup và teardown có scope rõ, cleanup idempotent.
- [ ] Cleanup chạy khi pass/fail và có janitor xử lý job bị hủy.
- [ ] Có lease/expiry để tránh janitor xóa run còn hoạt động.
- [ ] Cleanup theo thứ tự dependency và dừng producer trước khi xóa consumer/resource.
- [ ] External side effect dùng sandbox/fake hoặc có compensation.
- [ ] Cleanup report xác minh resource đã xóa hoặc ghi rõ retained/failed.
- [ ] Lỗi cleanup không che lỗi test gốc.

### Security và cost

- [ ] CI role chỉ có quyền trên môi trường test và resource do run sở hữu.
- [ ] Test fail fast nếu target account/project/subscription không nằm trong allowlist.
- [ ] Không có production secret trong fixture, log, artifact hoặc local settings.
- [ ] Có retention cho log, object, snapshot và artifact.
- [ ] Có budget/alert và dashboard cho resource orphan, cleanup failure và chi phí test.

Quản lý test data và cleanup là một phần của độ tin cậy của hệ thống serverless. Namespace riêng giúp test chạy song song mà không va chạm; fixture deterministic giúp tái lập lỗi; cleanup idempotent và janitor giúp xử lý cả trường hợp CI bị hủy; manifest và xác minh sau xóa giúp phát hiện tài nguyên mồ côi. Với Java function xử lý HTTP, message và event, hãy quản lý cả dữ liệu lẫn side effect bất đồng bộ theo cùng một test run lifecycle, đồng thời giới hạn quyền dọn dẹp để test không thể xóa nhầm tài nguyên dùng chung hoặc production.
