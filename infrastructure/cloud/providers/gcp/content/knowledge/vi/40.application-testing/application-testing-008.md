# Test fixtures, dữ liệu thử và dọn tài nguyên tự động

Một bài kiểm thử ứng dụng Java trên Google Cloud có thể cần người dùng, đơn hàng, message Pub/Sub, document Firestore, object Cloud Storage hoặc một cơ sở dữ liệu đã có schema. Nếu mỗi lần chạy test phải tạo các dữ liệu này bằng tay, kết quả sẽ chậm, thiếu nhất quán và khó lặp lại. Ngược lại, nếu test tự tạo tài nguyên nhưng không dọn dẹp, các lần chạy sau có thể bị ảnh hưởng, tài nguyên dùng chung có thể bị xóa nhầm và chi phí cloud tăng dần.

**Test fixture** là trạng thái đầu vào có chủ đích để kiểm thử một hành vi. Một quy trình fixture tốt phải làm rõ: tạo dữ liệu ở đâu, ai sở hữu dữ liệu đó, dữ liệu được dùng trong bao lâu, cách kiểm tra kết quả và cách dọn tài nguyên sau khi chạy. Với các dịch vụ Google Cloud, cần bổ sung project isolation, IAM và cơ chế thu gom tài nguyên bị bỏ lại khi runner mất kết nối.

Bài học nằm trong chương **Kiểm thử ứng dụng GCP** của module **CLOUD_PROVIDERS_GCP**. Module khám phá Google Cloud từ project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; người học thực hành lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong bài này, ta áp dụng các nguyên tắc đó để thiết kế test fixtures, dữ liệu thử và cơ chế cleanup đáng tin cậy cho ứng dụng Java/Spring.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt fixture, seed data, test factory, test double, teardown và môi trường thử nghiệm.
- Chọn nơi chạy phù hợp giữa unit test, container cục bộ, emulator và dự án GCP thử nghiệm.
- Tạo dữ liệu thử xác định, độc lập và không chứa dữ liệu người dùng thật.
- Dùng JUnit 5, Spring Boot và Testcontainers để chuẩn bị và dọn tài nguyên cục bộ.
- Tạo tài nguyên thử nghiệm trên Cloud Storage bằng một tiền tố riêng, rồi dọn đúng tài nguyên mình sở hữu.
- Thiết kế cleanup an toàn cho Pub/Sub, Firestore và tài nguyên GCP khác.
- Xử lý runner bị dừng, cleanup thất bại, thực thi song song và tài nguyên mồ côi.
- Kết hợp cleanup với IAM tối thiểu, thời hạn giữ dữ liệu, ngân sách và CI/CD.

## 1. Test fixture là gì?

Fixture có thể là dữ liệu, tài nguyên hoặc trạng thái cần có trước khi thực hiện assertion. Ví dụ, để kiểm tra API tạo hóa đơn, một test có thể cần khách hàng đã được kích hoạt, đơn hàng có ba sản phẩm và một cấu hình thuế.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Fixture | Trạng thái tiền đề phục vụ một test | Đơn hàng ở trạng thái PENDING |
| Seed data | Dữ liệu gốc nạp vào môi trường thử nghiệm | Bộ sản phẩm, mã vùng và loại tiền |
| Test data factory / builder | Hàm tạo dữ liệu thử theo tham số | OrderFixtures.pendingOrder(customerId) |
| Test double | Thành phần thay thế một dependency | Fake payment gateway hoặc mock HTTP client |
| Setup | Chuẩn bị điều kiện trước test | Tạo bucket object, tạo customer |
| Teardown / cleanup | Đưa tài nguyên về trạng thái không ảnh hưởng test khác | Xóa object thử hoặc đóng container |
| Ephemeral environment | Môi trường tồn tại cho một lần chạy | PostgreSQL container do Testcontainers tạo |

Fixture không nhất thiết phải là một object cố định lưu trong file JSON. Có thể dùng factory sinh bản ghi phù hợp từng test, môi trường giả lập hoặc resource tạm thực sự trên Google Cloud. Điều quan trọng là test tự làm chủ vòng đời và có thể chạy lại.

### Vòng đời lý tưởng của một fixture

~~~mermaid
flowchart LR
    A["Tạo run ID và phạm vi sở hữu"] --> B["Provision tài nguyên"]
    B --> C["Seed dữ liệu có kiểm soát"]
    C --> D["Thực hiện hành vi cần kiểm thử"]
    D --> E["Assert kết quả"]
    E --> F["Cleanup theo thứ tự phụ thuộc"]
    F --> G["Xác minh không còn tài nguyên tạm"]
~~~

Cleanup phải chạy cả khi assertion thất bại. Ngoài cleanup tại chỗ, cần một cơ chế thu gom dự phòng vì tiến trình có thể bị kill, máy CI mất kết nối hoặc quota khiến test dừng trước khi thực hiện teardown.

## 2. Chọn tầng kiểm thử phù hợp

Không nên dùng tài nguyên GCP thật cho mọi test. Các tầng kiểm thử có chi phí và mức độ trung thực khác nhau.

| Tầng | Ví dụ | Ưu điểm | Giới hạn |
|---|---|---|---|
| Unit test | JUnit và fake repository | Nhanh, xác định, không cần mạng | Không kiểm tra API/permission thật |
| Local integration | Testcontainers với PostgreSQL | Kiểm tra SQL, migration và transaction gần thực tế | Cần môi trường chạy container |
| Emulator | Firestore hoặc Pub/Sub emulator | Không tạo resource cloud thật, phù hợp CI | Không mô phỏng tất cả tính năng, IAM hoặc hành vi production |
| Integration trên GCP | Object Storage, Pub/Sub, Firestore thật trong test project | Kiểm tra API, IAM và quota thực | Mất thời gian, có chi phí và cần cleanup |
| End-to-end | Cloud Run/GKE cùng dependencies test | Kiểm tra đường đi nghiệp vụ xuyên hệ thống | Tốn kém, dễ bị ảnh hưởng bởi mạng và trạng thái chia sẻ |

Một chiến lược thực tế là để đa số test ở tầng unit/local, dành một nhóm nhỏ cho API cloud thực và một số bài E2E cho luồng quan trọng. Dùng emulator để kiểm tra logic tích hợp, nhưng vẫn có test kiểm chứng hành vi trên dịch vụ thật nếu tính đúng đắn phụ thuộc IAM, transaction, index, consistency hay cấu hình runtime.

### Quy tắc chọn phương án

- Nếu chỉ cần biết logic xử lý dữ liệu đúng, dùng unit test và factory.
- Nếu cần xác minh SQL/migration, dùng database container phù hợp.
- Nếu cần kiểm thử Pub/Sub hoặc Firestore API nhưng không cần kiểm tra IAM, cân nhắc emulator.
- Nếu cần kiểm tra service account, cấu hình mạng hoặc hành vi GCP thật, chạy integration test trên project được cấp riêng.
- Nếu cần xác minh toàn bộ đường đi user → API → queue → database, dùng E2E có giới hạn phạm vi và cơ chế khôi phục rõ.

Không coi emulator là bằng chứng đầy đủ cho quy tắc IAM hoặc khả năng chịu tải production; phạm vi hỗ trợ khác nhau theo từng emulator.

## 3. Năm thuộc tính của fixture tốt

**Xác định (deterministic):** cùng đầu vào và điều kiện sẽ cho cùng kết quả mong đợi. Dùng thời điểm được cố định và dữ liệu có nội dung rõ ràng, tránh phụ thuộc ngày hiện tại hoặc bản ghi tồn tại sẵn.

**Độc lập (isolated):** một test không sử dụng hoặc xóa dữ liệu của test khác. Dùng database/schema riêng, ID có namespace hoặc object prefix riêng cho từng run.

**Tối thiểu (minimal):** chỉ tạo các bản ghi cần thiết để kiểm chứng hành vi. Một fixture quá lớn làm test chậm và khó xác định nguyên nhân khi lỗi.

**Có thể lặp lại (repeatable):** test chạy được nhiều lần trên laptop, CI và môi trường thử nghiệm; dữ liệu cũ không gây xung đột.

**Có vòng đời rõ ràng:** tài nguyên được ghi nhận ngay khi tạo, có owner, phương án cleanup trong finally/AfterEach và cơ chế thu gom dự phòng.

Một điểm cần phân biệt: **nội dung fixture nên xác định**, nhưng **tên tài nguyên cần duy nhất** để các runner không va chạm. Ví dụ, đơn hàng luôn có ba sản phẩm với giá đã biết, còn khóa object trong Cloud Storage có thêm run ID ngẫu nhiên hoặc CI job ID.

## 4. Thiết kế dữ liệu thử không phụ thuộc production

Không sao chép tùy tiện dữ liệu khách hàng thật sang môi trường test. Dữ liệu thử nên được tạo tổng hợp, nhỏ, có cấu trúc phù hợp nghiệp vụ và không chứa thông tin nhạy cảm.

| Loại dữ liệu | Ví dụ tốt | Cần tránh |
|---|---|---|
| Người dùng | test-user-001@example.invalid | Email/điện thoại khách hàng thật |
| Đơn hàng | order-001, số lượng cố định | ID hoặc payload thực từ production |
| Thời gian | 2026-01-15T10:00:00Z cố định | Instant.now() trong assertion nhạy thời gian |
| Token | Test token của fake gateway | Production API token |
| Tệp | JSON nhỏ do test sinh | Tệp chứa dữ liệu nội bộ nhạy cảm |
| Lỗi | Mã lỗi giả định do fake trả về | Kích hoạt lỗi trên service production |

### Dùng Clock cố định

Java có lớp Clock cho phép thay thế thời gian hệ thống trong test. Ví dụ:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public final class TestClocks {
    public static final Clock FIXED = Clock.fixed(
            Instant.parse("2026-01-15T10:00:00Z"),
            ZoneOffset.UTC);

    private TestClocks() {
    }
}
~~~

Code nghiệp vụ nên nhận Clock qua constructor hoặc bean. Trong production, dùng Clock.systemUTC(); trong test, dùng TestClocks.FIXED. Nhờ đó, phép tính hết hạn, thời gian tạo đơn hàng và điều kiện thời gian không phụ thuộc tốc độ máy CI.

### Dùng factory để tạo dữ liệu có ý nghĩa

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;

public record OrderFixture(
        String orderId,
        String customerId,
        BigDecimal total,
        String status,
        Instant createdAt) {
}

public final class OrderFixtures {
    private OrderFixtures() {
    }

    public static OrderFixture pending(
            String orderId,
            Clock clock) {
        return new OrderFixture(
                orderId,
                "test-customer-001",
                new BigDecimal("125000.00"),
                "PENDING",
                Instant.now(clock));
    }
}
~~~

Test có thể gọi OrderFixtures.pending("order-001", TestClocks.FIXED). Nếu cần một tình huống mới, tạo factory method hoặc tham số nêu rõ biến thể, chẳng hạn expiredOrder hoặc paidOrder, thay vì sao chép nhiều JSON lớn rồi sửa thủ công.

### Dữ liệu biên

Không chỉ tạo happy path. Một bộ fixture hiệu quả thường có:

- Đơn hàng rỗng và đơn hàng có số lượng lớn vừa phải.
- Trường null, chuỗi Unicode, ký tự đặc biệt và giới hạn độ dài.
- Bản ghi trùng khóa hoặc message nhận hai lần.
- Thời điểm đúng trước và sau mốc hết hạn.
- Phân trang với tập dữ liệu lớn hơn page size một phần tử.
- Dependency trả lỗi timeout hoặc retryable error qua fake/stub.

Từng fixture nên nêu rõ vì sao nó tồn tại và assertion nào kiểm tra hành vi.

## 5. Đặt tên, gắn nhãn và xác định quyền sở hữu tài nguyên thử

Trong một project GCP dùng cho integration test, **không được cleanup theo tên service chung hoặc xóa mọi resource thuộc project**. Mỗi lần chạy phải có một namespace riêng và mỗi resource cần có dấu vết sở hữu.

Ví dụ namespace:

~~~text
it/orders-api/run-6241/test-create-order/
~~~

Với Cloud Storage, có thể tạo object ở:

~~~text
it/orders-api/run-6241/test-create-order/input.json
~~~

Với một số tài nguyên GCP, tên có giới hạn độ dài và ký tự. Hãy tạo run ID ngắn, chứa ký tự hợp lệ và kiểm tra quy tắc đặt tên của từng dịch vụ. Không dùng nguyên tên nhánh Git dài hoặc dữ liệu người dùng làm tên tài nguyên.

### Metadata nên có

| Trường | Mục đích |
|---|---|
| run_id | Nhóm tài nguyên thuộc một lần CI/test |
| test_id | Liên kết tài nguyên đến test case |
| owner | Team hoặc service chịu trách nhiệm |
| created_at | Hỗ trợ xác định tài nguyên quá hạn |
| expires_at | Mốc thời gian gợi ý cho sweeper |
| environment | Phân biệt test, staging, production |

Gắn labels khi dịch vụ hỗ trợ; khi không có labels ở cấp tài nguyên, lưu mapping vào fixture registry của run hoặc metadata phù hợp. Labels và expires_at là **thông tin để tìm và xử lý**, không tự động xóa tài nguyên. Muốn có cơ chế hết hạn thật, phải dùng lifecycle policy, TTL tính năng của dịch vụ hoặc cleanup job riêng.

### Quy tắc an toàn

1. Chỉ chạy test tạo/xóa tài nguyên ở project hoặc tenant đã được phê duyệt cho integration test.
2. Kiểm tra project ID và dấu nhận diện môi trường trước khi provision hoặc cleanup.
3. Sinh ID riêng cho mỗi run và sở hữu rõ từng resource.
4. Không cho cleanup xóa bucket, database, topic hoặc namespace dùng chung chỉ vì fixture nằm bên trong.
5. Giới hạn IAM để CI chỉ thao tác trên resource cần thiết khi dịch vụ hỗ trợ.
6. Không xóa tài nguyên dựa trên prefix quá rộng như prod/, orders/ hoặc một giá trị rỗng.

## 6. JUnit 5: setup và teardown có kiểm soát

JUnit 5 cung cấp các callback như BeforeEach, AfterEach, BeforeAll và AfterAll. Chọn scope fixture phù hợp:

| Scope | Khi nên dùng | Lưu ý |
|---|---|---|
| Mỗi test | Test có dữ liệu thay đổi | Độc lập cao, tốn thời gian tạo hơn |
| Mỗi class | Container/database dùng chung cho các method | Cần cleanup dữ liệu của từng method |
| Mỗi test suite/run | Emulator hoặc môi trường tích hợp được chia sẻ | Cần namespace riêng và quản lý chạy song song |

AfterEach thường được gọi sau test dù assertion ném lỗi. Tuy nhiên, callback không chạy khi tiến trình bị kill hoặc máy CI mất kết nối. Vì vậy, một pipeline có tài nguyên cloud phải có cả cleanup tại chỗ và cơ chế dự phòng.

### Dọn dữ liệu ngay trong finally

Nếu test tạo một resource tạm qua API:

~~~java
String resourceId = createTestResource();
try {
    assertExpectedBehavior(resourceId);
} finally {
    deleteTestResource(resourceId);
}
~~~

finally thực hiện cleanup khi test ném exception thông thường. Nếu cleanup cũng thất bại, có nguy cơ exception cleanup che khuất nguyên nhân lỗi gốc; với nhiều tài nguyên, một lớp fixture scope có thể gom lỗi và dùng try-with-resources để giữ các exception ở dạng suppressed.

### Quản lý nhiều cleanup action theo thứ tự ngược

Ví dụ Java độc lập không phụ thuộc Google Cloud SDK:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

public final class FixtureScope implements AutoCloseable {
    private final Deque<AutoCloseable> cleanup = new ArrayDeque<>();

    public void register(AutoCloseable action) {
        cleanup.push(action);
    }

    @Override
    public void close() throws Exception {
        Exception first = null;
        while (!cleanup.isEmpty()) {
            try {
                cleanup.pop().close();
            } catch (Exception error) {
                if (first == null) {
                    first = error;
                } else {
                    first.addSuppressed(error);
                }
            }
        }
        if (first != null) {
            throw first;
        }
    }
}
~~~

Các cleanup action được chạy theo LIFO: tài nguyên tạo sau được dọn trước. Điều này phù hợp khi subscription phụ thuộc topic, hoặc child record phụ thuộc parent record. Trong test:

~~~java
try (FixtureScope fixtures = new FixtureScope()) {
    String topicId = createTopicForTest();
    fixtures.register(() -> deleteTopicIfExists(topicId));

    String subscriptionId = createSubscriptionForTest(topicId);
    fixtures.register(() -> deleteSubscriptionIfExists(subscriptionId));

    // Chạy assertion với topic và subscription vừa tạo.
    assertMessagingBehavior(subscriptionId);
}
~~~

Hai hàm delete...IfExists là hàm giả định cần triển khai theo SDK của dịch vụ. Chúng nên xem resource không tồn tại là tình huống cleanup thành công. Nếu tạo resource thất bại trước khi đăng ký cleanup, hãy kiểm tra tài nguyên có thể đã được tạo một phần; với API tạo tài nguyên qua mạng, timeout không luôn có nghĩa request chưa thành công.

Đối với tài nguyên có thể bị tạo một phần, có thể đăng ký cleanup theo ID đã biết **trước** khi gọi create nếu deleteIfExists an toàn. Điều này giảm rủi ro rò rỉ tài nguyên khi request tạo thành công nhưng response bị mất.

## 7. Ví dụ Java/Spring: PostgreSQL fixture với Testcontainers

Testcontainers chạy PostgreSQL thật bên trong container và tự quản lý vòng đời container test. Nó thích hợp khi cần kiểm tra SQL, transaction, schema migration hoặc mapping JPA mà không dùng một database chia sẻ trên GCP.

Thêm những dependency phù hợp vào phạm vi test của Maven, ví dụ JUnit Jupiter, Testcontainers JUnit Jupiter và module PostgreSQL. Quản lý version bằng Testcontainers BOM tương thích với dự án. Ứng dụng cũng cần PostgreSQL JDBC driver và Spring JDBC hoặc Spring Data JPA theo lựa chọn đang dùng.

### Tạo database container và kết nối Spring

~~~java
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@SpringBootTest
class OrderDatabaseFixtureTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16.4")
                    .withDatabaseName("orders_it")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    @Autowired
    JdbcTemplate jdbc;

    private String runId;
    private String orderId;

    @BeforeEach
    void seedOrder() {
        runId = "it-" + UUID.randomUUID();
        orderId = runId + "-order";

        jdbc.update(
                "INSERT INTO orders (id, status, test_run_id) "
                        + "VALUES (?, ?, ?)",
                orderId, "PENDING", runId);
    }

    @Test
    void fixtureIsAvailableToTheTest() {
        String status = jdbc.queryForObject(
                "SELECT status FROM orders WHERE id = ?",
                String.class,
                orderId);
        assertEquals("PENDING", status);
    }

    @AfterEach
    void removeSeedData() {
        if (runId != null) {
            jdbc.update(
                    "DELETE FROM orders WHERE test_run_id = ?",
                    runId);
        }
    }
}
~~~

Ví dụ giả định project có migration tạo bảng orders với các cột id, status và test_run_id. Testcontainers chỉ cung cấp PostgreSQL; schema vẫn cần được tạo bởi Flyway, Liquibase hoặc cấu hình schema test phù hợp. Mật khẩu test trong ví dụ chỉ dùng cho container tạm trên máy/CI, **không phải credential production**.

Các điểm cần lưu ý:

1. Container dùng chung trong class để giảm thời gian khởi động; dữ liệu từng method vẫn có runId riêng.
2. DynamicPropertySource cung cấp JDBC URL và credential cho Spring trước khi tạo DataSource.
3. BeforeEach seed đúng bản ghi cần cho test; AfterEach xóa bản ghi có test_run_id tương ứng.
4. Nếu có foreign key, cleanup phải xóa child rows trước parent rows hoặc dùng transaction phù hợp.
5. Trong ứng dụng thực tế, nên gọi service/repository nghiệp vụ rồi assert trạng thái database, thay vì chỉ xác minh bản ghi vừa chèn.

### Có thể dùng @Transactional để rollback không?

Với Spring Test, một test method chạy trong transaction do test framework quản lý có thể rollback khi kết thúc. Đây là cách tốt khi toàn bộ thao tác cần kiểm tra nằm trong cùng ngữ cảnh transaction của test.

Tuy nhiên, rollback của test **không tự hoàn tác** các thao tác chạy qua HTTP server ở thread/process khác, message consumer, scheduler hoặc dịch vụ ngoài database. Vì vậy, với integration/E2E test có tác vụ bất đồng bộ, vẫn phải dùng run ID và cleanup tường minh. Không giả định @Transactional sẽ dọn object Cloud Storage, message Pub/Sub hoặc mọi thay đổi trong hệ thống.

### Tái sử dụng container

Testcontainers có thể tái sử dụng container giữa các lần chạy khi cấu hình riêng cho phép. Điều này giúp tăng tốc nhưng có thể giữ lại dữ liệu và trạng thái. Đối với CI cần tính độc lập cao, hãy ưu tiên container tạm có vòng đời gắn với test run, và chỉ bật tái sử dụng khi có chiến lược reset dữ liệu rõ ràng.

## 8. Emulator: fixture không tạo tài nguyên GCP thật

Google Cloud cung cấp emulator cho một số dịch vụ, ví dụ Firestore và Pub/Sub. Chúng thường phù hợp để kiểm thử logic tích hợp và quy trình xử lý dữ liệu mà không tạo resource trên project thật.

### Firestore emulator

Ví dụ khởi chạy emulator trong môi trường phát triển có Google Cloud CLI:

~~~bash
gcloud beta emulators firestore start \
  --host-port=127.0.0.1:8081
~~~

Trong terminal khác, đặt biến môi trường cho tiến trình test:

~~~bash
export FIRESTORE_EMULATOR_HOST="127.0.0.1:8081"
export GOOGLE_CLOUD_PROJECT="demo-orders-test"
~~~

Google Cloud Firestore Java client có hỗ trợ kết nối emulator theo cách cấu hình của thư viện. Hãy kiểm tra client/phiên bản đang dùng và môi trường test để chắc chắn requests đi đến emulator, không đi nhầm production. Đặt project ID giả hoặc project dành cho test; không dùng project production trong test local.

Fixture có thể tạo document trong collection run-scoped:

~~~text
test-runs/run-6241/orders/order-001
~~~

Sau test, dọn các document được tạo. Firestore không tự xóa toàn bộ subcollection khi xóa parent document. Nếu fixture có document lồng nhau, cleanup cần duyệt hoặc ghi nhận các đường dẫn con và xóa đúng thứ tự.

### Pub/Sub emulator

~~~bash
gcloud beta emulators pubsub start \
  --project="demo-orders-test" \
  --host-port=127.0.0.1:8085
~~~

Trong tiến trình test:

~~~bash
export PUBSUB_EMULATOR_HOST="127.0.0.1:8085"
export PUBSUB_PROJECT_ID="demo-orders-test"
~~~

Tùy Java client library, cần cấu hình emulator channel và credentials provider không dùng thông tin xác thực cloud thực. Đừng giả định mọi thư viện hoặc framework Spring sẽ tự phát hiện emulator chỉ vì biến môi trường đã được đặt; hãy kiểm tra kết nối, port và cơ chế injection tại lớp client.

Một fixture Pub/Sub có thể tạo topic và subscription có run ID riêng, publish message và assert consumer xử lý. Khi dọn:

1. Dừng publisher và subscriber, chờ tác vụ còn chạy hoàn tất theo deadline.
2. Xóa subscription do test tạo.
3. Xóa topic do test tạo.
4. Đảm bảo client/channel được đóng.

Không sử dụng topic hoặc subscription production trong emulator test. Emulator cũng không tái hiện đầy đủ IAM, quota, retention và mọi hành vi thời gian của Pub/Sub thật; các trường hợp này cần integration test riêng trên GCP.

## 9. Integration fixture trên Cloud Storage thật

Một số test cần kiểm tra IAM, SDK và object metadata thực tế. Khi đó có thể dùng một **bucket test đã được quản lý sẵn**, còn mỗi test chỉ tạo các object dưới prefix duy nhất. Đây thường là lựa chọn an toàn và nhanh hơn việc tạo/xóa bucket mới cho từng test.

### Quy tắc trước khi chạy

- Dùng project/bucket dành riêng cho integration test, có tên nằm trong allowlist của CI.
- Dùng service account chỉ được tạo/đọc/xóa object trong phạm vi test cho phép.
- Không dùng bucket chứa dữ liệu nghiệp vụ hoặc backup production.
- Mỗi run có prefix riêng, ví dụ integration/orders-api/ci-6241/.
- Cleanup chỉ được xóa object đã tạo; không xóa bucket.
- Ghi lại object name/generation để cleanup chính xác.

### Java SDK: tạo và xóa đúng object

Ví dụ dùng JUnit 5 và Google Cloud Storage client library. Test chỉ chạy khi biến RUN_GCP_IT được bật rõ ràng và GCP_IT_PROJECT/GCP_IT_BUCKET được cấu hình:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@EnabledIfEnvironmentVariable(
        named = "RUN_GCP_IT",
        matches = "true")
class CloudStorageFixtureTest {

    @Test
    void readsTheObjectCreatedByThisTest() {
        String projectId = requiredEnv("GCP_IT_PROJECT");
        String bucket = requiredEnv("GCP_IT_BUCKET");
        String runId = UUID.randomUUID().toString();
        String objectName =
                "integration/orders-api/" + runId + "/input.json";

        Storage storage = StorageOptions.newBuilder()
                .setProjectId(projectId)
                .build()
                .getService();

        byte[] payload = "{\"orderId\":\"order-001\"}"
                .getBytes(StandardCharsets.UTF_8);
        BlobId plannedId = BlobId.of(bucket, objectName);
        Blob created = null;

        try {
            created = storage.create(
                    BlobInfo.newBuilder(plannedId)
                            .setContentType("application/json")
                            .build(),
                    payload);

            Blob loaded = storage.get(created.getBlobId());
            assertNotNull(loaded);
            assertArrayEquals(payload, loaded.getContent());
        } finally {
            if (created != null) {
                // BlobId có generation của object vừa tạo.
                storage.delete(created.getBlobId());
            }
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing required test configuration: " + name);
        }
        return value;
    }
}
~~~

Điểm quan trọng là test ghi object name dưới prefix riêng, dùng BlobId của object đã tạo và không gọi xóa toàn bucket. BlobId có generation giúp nhắm đến đúng thế hệ object khi thao tác với hệ thống có versioning hoặc ghi đè. Nếu create request thành công nhưng response bị mất do timeout, biến created có thể vẫn null và cleanup tại chỗ chưa biết generation để xóa; sweeper dự phòng sẽ xử lý object dưới prefix run sau khi hết hạn.

Ví dụ kiểm tra đúng thao tác create/read/delete. Với bài kiểm thử ứng dụng thật, hãy thay phần create bằng việc gọi API upload của ứng dụng, rồi assert object xuất hiện ở bucket test; cleanup vẫn cần dựa vào run ID, object ID hoặc metadata mà test kiểm soát.

### Nếu một test tạo nhiều object

Ghi danh sách object đã tạo vào fixture registry và dọn từng object ở finally/AfterEach. Có thể list theo prefix, nhưng chỉ khi prefix **thuộc riêng run hiện tại và không rỗng**. Với bucket versioning, cần xét cả noncurrent versions nếu chính sách test yêu cầu loại bỏ hoàn toàn; quyền và cơ chế xóa phiên bản phải được kiểm soát.

Không chạy một script generic liệt kê rồi xóa mọi object trong bucket chỉ vì bucket mang tên test. Bucket test có thể được dùng đồng thời bởi nhiều pipeline hoặc team khác nhau.

## 10. Cleanup theo đặc điểm từng dịch vụ GCP

Không có một cách xóa tài nguyên chung an toàn cho mọi dịch vụ. Cleanup cần hiểu quan hệ phụ thuộc, quyền truy cập và quy tắc xóa của resource type.

| Dịch vụ | Fixture thường tạo | Chiến lược cleanup | Lưu ý |
|---|---|---|---|
| Cloud Storage | Object trong test bucket | Xóa đúng object/generation hoặc prefix riêng | Không xóa bucket dùng chung |
| Pub/Sub | Topic, subscription và message | Dừng subscriber, xóa subscription rồi topic test | Không xóa topic dùng chung |
| Firestore | Document trong collection test | Xóa document/subcollection theo danh sách đã tạo | Xóa parent không tự xóa subcollection |
| Bigtable | Row với prefix riêng | Xóa đúng các row thuộc prefix test | Không xóa table/instance chia sẻ |
| Spanner | Bản ghi trong database test | Dùng transaction delete theo khóa/test ID | Cleanup phải tôn trọng foreign key và transaction |
| BigQuery | Dataset/table tạm hoặc row thử | Dùng dataset riêng cho run hoặc xóa table rõ ID | Query job và tài nguyên có thể còn chạy |
| Cloud SQL | Database/schema hoặc bản ghi thử | Rollback hoặc dọn theo test_run_id | Tránh xóa instance dùng chung |
| Cloud Run | Service/revision thử | Chỉ xóa service được provision riêng cho run | Không động vào service staging/production dùng chung |
| GKE | Pod/Job/namespace thử | Xóa resource bằng tên/label và namespace test riêng | Kiểm tra owner, finalizer và trạng thái Terminating |

Ví dụ: nếu test Pub/Sub dùng một topic dùng chung và tạo một subscription tạm, cleanup chỉ được xóa subscription đó; xóa cả topic sẽ làm hỏng test khác. Nếu test Firestore tạo document và subcollection lồng nhau, cần ghi rõ các path đã tạo và dọn cả document con, không chỉ document cha.

### Quy tắc xử lý tài nguyên có phụ thuộc

- Xóa resource con hoặc consumer trước khi xóa resource cha mà nó phụ thuộc.
- Chờ tác vụ bất đồng bộ hoàn thành hoặc hủy theo deadline trước khi xóa nguồn.
- Nếu resource đã không tồn tại, cleanup nên thành công theo tính idempotent.
- Nếu thiếu quyền xóa, báo lỗi và giữ lại thông tin ID cho sweeper hoặc người vận hành.
- Với tài nguyên dùng chung, chỉ xóa dữ liệu mang run ID; không delete/drop tài nguyên nền.
- Với dữ liệu quan trọng, không dùng câu lệnh xóa hàng loạt chỉ dựa vào môi trường mặc định.

## 11. Dọn tài nguyên khi test hoặc CI bị ngắt

AfterEach, AfterAll và finally không chạy được trong mọi tình huống. Runner có thể mất mạng, container bị kill, máy hết tài nguyên hoặc job vượt timeout. Tài nguyên thử nghiệm trên GCP có thể còn tồn tại sau khi CI đã kết thúc. Vì vậy, cleanup tốt thường có **hai lớp**:

1. **Primary cleanup:** test thực hiện ngay khi hoàn tất hoặc thất bại.
2. **Fallback cleanup:** một job độc lập tìm và dọn resource thử nghiệm đã quá hạn, có kiểm tra quyền sở hữu.

### Thiết kế fallback sweeper

Có thể dùng Cloud Scheduler để kích hoạt Cloud Run Job hoặc một quy trình định kỳ tương đương. Sweeper nên:

- Chỉ hoạt động trên project test có trong allowlist cấu hình.
- Chỉ xét resource có dấu hiệu do automation tạo, ví dụ label owner=integration-tests và run_id cụ thể.
- Kiểm tra created_at/expires_at hoặc tuổi tối thiểu trước khi xóa.
- Loại trừ run còn hoạt động hoặc đang giữ lease.
- In danh sách resource dự kiến dọn trong dry-run trước khi áp dụng thật.
- Giới hạn số resource được xóa trong một lần chạy và cảnh báo nếu vượt ngưỡng.
- Xóa theo thứ tự phụ thuộc, dùng retry có giới hạn cho lỗi tạm thời.
- Ghi log ID, loại tài nguyên, kết quả cleanup và lý do bỏ qua; không ghi secret.
- Giữ audit log và cảnh báo khi sweeper gặp lỗi quyền hoặc không thể hoàn tất cleanup.

Một sơ đồ hai lớp:

~~~mermaid
flowchart TD
    A["CI chạy integration test"]
    B["Tạo resource theo run_id"]
    C{"Runner còn hoạt động?"}
    D["finally / AfterEach cleanup"]
    E["Job sweeper theo lịch"]
    F{"Đúng project + owner + đã quá hạn?"}
    G["Xóa đúng resource thử và ghi audit"]
    H["Bỏ qua, giữ dữ liệu để kiểm tra"]
    A --> B --> C
    C -->|"Có"| D
    C -->|"Không"| E
    E --> F
    F -->|"Có"| G
    F -->|"Không"| H
~~~

Labels và TTL metadata không tự vận hành sweeper. Nếu dùng tính năng TTL hoặc lifecycle của dịch vụ, hãy kiểm tra phạm vi áp dụng, thời điểm xóa thực tế và ảnh hưởng đến resource dùng chung. Ví dụ, lifecycle policy tại bucket có thể phù hợp cho bucket riêng của test; áp dụng chính sách xóa quá rộng lên bucket chia sẻ có thể gây mất dữ liệu khác.

### Nên dùng lease hoặc trạng thái run

Nếu một integration test kéo dài, chỉ dựa vào created_at có thể khiến sweeper xóa resource đang được test sử dụng. Có thể lưu trạng thái run với owner, started_at, heartbeat_at và expires_at trong một nơi dành riêng cho điều phối. Khi sweeper chạy, nó cần kiểm tra run còn hoạt động hay không và chỉ xóa khi lease hết hạn, quá thời gian an toàn và resource nằm trong allowlist.

Nếu cần manual override, yêu cầu cung cấp run ID và danh sách resource cụ thể để tránh vô tình cleanup một nhóm đang chạy.

## 12. Cleanup idempotent, retry và xử lý lỗi

Cleanup nên idempotent: gọi nhiều lần có kết quả an toàn như nhau. Nếu resource đã được xóa bởi test hoặc sweeper, lần cleanup tiếp theo không nên làm hỏng resource khác.

Ví dụ hàm xóa object:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public final class StorageCleanup {
    private StorageCleanup() {
    }

    public static void deleteIfExists(
            Storage storage,
            BlobId ownedBlobId) {
        // false nghĩa là object không còn; đây là kết quả cleanup hợp lệ.
        storage.delete(ownedBlobId);
    }
}
~~~

Hàm này chỉ an toàn nếu ownedBlobId được tạo trong phạm vi test và đã được xác minh trước khi truyền vào. Không cho phép caller tạo BlobId từ đường dẫn tùy ý của người dùng rồi xóa.

### Phân loại lỗi

| Tình huống | Cách xử lý |
|---|---|
| Resource không còn tồn tại | Xem cleanup thành công |
| 429/quota hoặc 503 tạm thời | Retry có exponential backoff, jitter và deadline |
| 403 PermissionDenied | Dừng retry vô ích; ghi nhận thiếu quyền và báo blocker |
| Precondition failed/generation mismatch | Không xóa thế hệ khác; ghi nhận sự thay đổi |
| Timeout của delete | Truy vấn trạng thái rồi thử lại idempotent nếu an toàn |
| Resource đang được sử dụng | Dừng consumer/job, chờ theo deadline và retry phù hợp |
| Cleanup làm phát sinh lỗi mới | Giữ nguyên lỗi kiểm thử chính, ghi thêm lỗi cleanup |

Tránh retry vô hạn. Nếu test đã hoàn tất nhưng cleanup liên tục gặp 403, vấn đề là IAM hoặc phạm vi quyền, không phải độ trễ mạng. Hãy giới hạn số lần retry, ghi resource ID và chuyển sang quy trình xử lý dự phòng.

### Giữ nguyên nguyên nhân lỗi test

Khi test thất bại và cleanup cũng thất bại, cần báo cáo cả hai sự kiện. try-with-resources sẽ giữ exception phát sinh trong thân try là lỗi chính, đồng thời gắn lỗi close() vào danh sách suppressed exceptions. Cơ chế FixtureScope ở phần trước có thể giúp bảo toàn các lỗi cleanup khi có nhiều resource.

Trong CI, lỗi cleanup có thể được coi là thất bại của build dù assertion thành công nếu nó để lại tài nguyên có chi phí hoặc rủi ro. Tuy nhiên, báo cáo nên nói rõ test logic đã pass hay fail và cleanup đã pass hay fail, thay vì gộp thành thông báo chung.

## 13. Chạy test song song không gây va chạm

CI thường chạy nhiều worker, shard hoặc pull request đồng thời. Các test cùng ghi vào một key như test-order-001 có thể làm dữ liệu của nhau bị ghi đè hoặc xóa nhầm.

### Chiến lược isolation

- **Theo run:** dùng CI build ID kết hợp retry attempt hoặc UUID cho tất cả resource trong một lần chạy.
- **Theo test:** thêm test case ID hoặc hash ổn định để phân tách dữ liệu của từng method.
- **Theo worker:** thêm worker/shard ID nếu nhiều process cùng tạo dữ liệu trong run.
- **Theo loại tài nguyên:** dùng tên tuân thủ quy tắc của dịch vụ, không nhét trực tiếp mọi thành phần vào tên nếu vượt giới hạn.
- **Theo môi trường:** đảm bảo production, staging và integration dùng resource khác nhau.

Ví dụ:

~~~text
it/orders-api/run-6241/shard-02/create-order/order-001.json
it/orders-api/run-6241/shard-03/cancel-order/order-001.json
~~~

Hai test có thể dùng cùng nội dung order-001 nhưng đặt trong không gian riêng. Khi test tạo dữ liệu qua một API dùng ID toàn cục, factory phải sinh ID duy nhất phù hợp, còn các trường nghiệp vụ cần assert vẫn giữ giá trị xác định.

### Tránh static mutable fixture

Không để các test sửa chung một singleton hoặc static collection có trạng thái nếu framework chạy song song. Có thể dùng dữ liệu bất biến và factory cho mỗi method, hoặc khóa tài nguyên khi thật sự cần dùng chung một hệ thống không hỗ trợ isolation. Cách dùng khóa thường làm test chậm và có thể che giấu lỗi race, nên ưu tiên thiết kế fixture độc lập.

### Test message bất đồng bộ

Với Pub/Sub hoặc worker chạy nền, test không nên dùng Thread.sleep với một thời gian cố định rồi giả định dữ liệu đã sẵn sàng. Thay vào đó:

1. Publish message có correlation ID thuộc run.
2. Poll trạng thái xử lý theo deadline rõ ràng.
3. Assert đúng event/result tương ứng với correlation ID.
4. Dừng consumer hoặc chờ tác vụ hoàn tất.
5. Cleanup message-related resources và dữ liệu test.

Nếu đến deadline mà assertion không thành công, ghi lại logs, request ID và resource ID để điều tra. Polling nên có khoảng nghỉ hợp lý, không tạo tight loop làm tăng tải.

## 14. Quyền IAM và giới hạn tác động của fixture

Runtime identity của CI chỉ nên có quyền cần thiết để tạo, đọc và xóa resource test trong phạm vi được phép. Quyền test và production phải tách riêng.

Ví dụ:

| Thành phần | Quyền cần cân nhắc | Giới hạn |
|---|---|---|
| Test đọc/ghi object | Storage object permissions | Bucket test cụ thể nếu có thể |
| Test Pub/Sub | Topic/subscription permissions | Topic và subscription thuộc test project |
| Test Firestore | Quyền document/database phù hợp | Database test tách biệt |
| Cloud Build test runner | Quyền gọi API test cần thiết | Service account riêng cho integration |
| Cleanup sweeper | Quyền list/delete tài nguyên thử | Project test và allowlist resource |
| Application runtime | Quyền truy cập nghiệp vụ | Không được quyền quản trị fixture tùy tiện |

Không đưa service account JSON vào repository, fixture file hoặc image. Với Cloud Build, Cloud Run và GKE, ưu tiên danh tính workload; với CI bên ngoài Google Cloud, cân nhắc Workload Identity Federation.

Một số API không hỗ trợ IAM giới hạn chính xác theo prefix của object hoặc label tùy tình huống. Khi không thể giới hạn quyền đủ hẹp, hãy dùng **bucket, database hoặc project dành riêng cho integration test**, thay vì kỳ vọng code cleanup tự tạo ra ranh giới bảo mật.

### Bảo vệ dữ liệu thử

- Không đưa thông tin người dùng thật hoặc credential production vào fixture.
- Đặt cấu hình retention phù hợp để dữ liệu thử không tồn tại vô thời hạn.
- Mã hóa và giới hạn quyền truy cập theo yêu cầu của tổ chức.
- Không in payload bí mật trong test failure output hoặc snapshot assertion.
- Nếu cần tải dữ liệu production để phân tích lỗi, phải có quy trình phê duyệt, ẩn danh và xử lý dữ liệu phù hợp; không tự động sao chép vào test project.

## 15. Fixture trong CI/CD với Cloud Build

Một pipeline có thể chạy unit tests và integration tests bằng các bước riêng. Bước integration chỉ được kích hoạt khi có test project, runner identity và dependency đã chuẩn bị.

Ví dụ cấu hình ở mức minh họa:

~~~yaml
substitutions:
  _TEST_PROJECT: example-integration-project

steps:
  - id: unit-tests
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - test

  - id: cloud-integration-tests
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: bash
    args:
      - -ceu
      - |
        export RUN_GCP_IT=true
        export GCP_IT_PROJECT="$_TEST_PROJECT"
        export TEST_RUN_ID="$BUILD_ID"
        mvn -B -Pintegration verify
    waitFor:
      - unit-tests

options:
  logging: CLOUD_LOGGING_ONLY
timeout: 1200s
~~~

Ví dụ giả định project có Maven profile integration, các thư viện cần thiết và cách cấu hình test bucket riêng. RUN_GCP_IT là cờ kích hoạt integration tests; GCP_IT_PROJECT chọn project; TEST_RUN_ID cho phép đặt namespace và ghi log. Cần cấp danh tính của build đúng quyền trên test project. Để chạy test Storage trong ví dụ trước, còn cần khai báo GCP_IT_BUCKET qua cấu hình CI của môi trường test.

Trong một pipeline thực tế, các bước build được phép dùng cùng workspace, nhưng runtime của step có thể khác nhau. Đảm bảo cờ test và credential chỉ tồn tại trong step cần dùng. Với kiểm thử E2E tạo cluster hoặc service tạm, nên dùng job/stage riêng có timeout và cơ chế cleanup độc lập.

### Hành vi khi bước test thất bại

Nếu assertion thất bại, JUnit có thể chạy AfterEach và try-with-resources, nhưng Cloud Build có thể dừng các bước phụ thuộc. Đừng thiết kế cleanup bắt buộc thành step chạy sau một bước fail mà không kiểm tra semantics thực thi của pipeline.

Có thể đưa setup/test/cleanup vào cùng một script với trap hoặc finally, hoặc dùng một cleanup job độc lập dựa trên run ID. Dù dùng cách nào, phải có fallback cho tình huống process bị kill trước khi trap được thực thi.

### Ghi nhận artifact kiểm thử

Nên lưu báo cáo JUnit/Surefire, mã lỗi, tên test, run ID, tên resource và liên kết đến Logs Explorer theo chính sách. Tránh đưa snapshot dữ liệu nhạy cảm vào artifact. Khi cần giữ lại fixture để điều tra, phải có lựa chọn có kiểm soát, thời hạn hết hạn và người chịu trách nhiệm; không mặc định giữ vô thời hạn sau mỗi test thất bại.

## 16. Tình huống thực tế: kiểm thử luồng tạo đơn hàng

Giả sử hệ thống Orders gồm Spring Boot API chạy trên Cloud Run, PostgreSQL, Pub/Sub và một worker ghi biên nhận lên Cloud Storage. Nhóm cần kiểm tra rằng một yêu cầu tạo đơn hàng hợp lệ sẽ dẫn đến message được publish và file biên nhận được tạo.

### Thiết kế fixture

| Bước | Fixture | Ownership | Cleanup |
|---|---|---|---|
| Chuẩn bị database | Customer và product thử, schema sẵn có | test_run_id | Xóa order, item, customer theo thứ tự |
| Tạo message topic | Topic riêng cho run hoặc topic test dùng chung | Topic riêng mới được xóa | Xóa subscription test trước topic |
| Tạo subscription | Subscription có run ID | Subscription riêng | Stop subscriber, delete subscription |
| Storage output | Prefix riêng trong bucket test | run ID và object ID | Xóa các object do run tạo |
| Trigger nghiệp vụ | HTTP request kèm correlation ID | run ID | Chờ các side effects hoàn tất |
| Assertion | Order status, event ID, object payload | Không tạo thêm resource | Không áp dụng |

Nếu hệ thống đang dùng topic test chung, test **chỉ nên tạo subscription riêng** để nhận message cho mình và lọc theo correlation ID phù hợp. Tuy nhiên, subscriber khác có thể nhận message của hệ thống cùng lúc; cần hiểu đúng semantics fan-out của Pub/Sub và thiết kế test tránh giả định mọi message đều chỉ đến test này.

### Quy trình đề xuất

1. Sinh run ID và correlation ID riêng.
2. Xác nhận đang ở test project, không phải production.
3. Tạo hoặc chọn các fixture trong database test; ghi nhận mọi ID.
4. Tạo subscription test và thiết lập consumer.
5. Gửi HTTP request tạo đơn hàng có dữ liệu tổng hợp.
6. Chờ đến deadline để quan sát message và object dưới prefix riêng.
7. Assert chính xác customer ID, order total, event type và object metadata cần thiết.
8. Dừng consumer và xóa subscription; sau đó xóa topic nếu thuộc riêng run.
9. Xóa các object trong bucket test và bản ghi database có test_run_id.
10. Xác minh cleanup, lưu trạng thái PASS/FAIL của từng hạng mục.

Để tránh flaky test, assertion nên dựa trên điều kiện cuối cùng có thể quan sát được, không dựa vào một khoảng ngủ cố định. Ví dụ, poll đến khi object xuất hiện hoặc hết 30 giây rồi báo timeout cùng correlation ID để điều tra. Khoảng timeout phải dựa trên đặc điểm môi trường test, không chọn tùy tiện cho production.

### Nếu test thất bại giữa chừng

Giả sử API đã tạo đơn hàng nhưng worker không sinh được biên nhận. Test sẽ thất bại vì không thấy object sau deadline. Cleanup vẫn phải xóa subscription test và bản ghi test. Nếu cần giữ lại log hoặc trace để điều tra, ghi tên tài nguyên và correlation ID vào báo cáo; **không giữ resource có chi phí mãi mãi chỉ vì test fail**.

Nếu một lệnh cleanup gặp lỗi tạm thời, retry theo deadline. Nếu vẫn thất bại, ghi resource vào danh sách cleanup pending để sweeper xử lý và cảnh báo cho nhóm sở hữu.

## 17. Những lỗi thiết kế fixture thường gặp

| Cách làm | Rủi ro | Cách cải thiện |
|---|---|---|
| Dùng cùng orderId cho mọi lần chạy | Trùng khóa và test tác động lẫn nhau | Sinh namespace/run ID riêng |
| Test dựa vào dữ liệu đã có trong môi trường | Test không thể lặp lại khi dữ liệu đổi | Tự seed fixture tối thiểu |
| Gọi production để lấy dữ liệu thử | Rò rỉ dữ liệu và ảnh hưởng hệ thống thật | Sinh dữ liệu tổng hợp hoặc dùng mock/emulator |
| Dùng một bucket test rồi xóa sạch sau mỗi test | Xóa dữ liệu của run khác | Xóa object của đúng prefix/run |
| Xóa Firestore parent rồi cho rằng đã sạch | Subcollection có thể còn tồn tại | Cleanup document con rõ ràng |
| Chỉ dọn ở AfterAll | Runner bị kill vẫn để lại resource | Thêm sweeper dự phòng |
| Dùng Thread.sleep cố định cho message async | Test flaky khi hệ thống chậm | Poll theo điều kiện với deadline |
| Dùng quyền Editor/Owner cho CI | Có thể tác động tài nguyên ngoài test | IAM tối thiểu và project test riêng |
| In toàn bộ fixture khi test fail | Có thể lộ token hoặc dữ liệu nhạy cảm | Log ID và trường không nhạy cảm |
| Giữ lại resource không giới hạn để debug | Tăng chi phí và xung đột về sau | TTL, người sở hữu và thời hạn xử lý |
| Cleanup retry vô hạn | CI treo hoặc tăng tải API | Backoff có giới hạn và báo lỗi rõ |
| Coi emulator giống production hoàn toàn | Bỏ sót lỗi IAM hoặc semantics khác | Có nhóm integration test trên dịch vụ thật |

## 18. Bài tập thực hành

Hãy thiết kế và triển khai một bộ integration tests cho ứng dụng **orders-api** có PostgreSQL và Cloud Storage. Mục tiêu là test có thể chạy song song trong CI, thất bại đúng khi hành vi sai và không để lại dữ liệu cloud quá hạn.

### Phần A: dữ liệu và database

1. Tạo OrderFixtures factory cho hai trạng thái PENDING và PAID, dùng Clock cố định.
2. Tạo PostgreSQL container bằng Testcontainers và kết nối qua DynamicPropertySource.
3. Khởi tạo schema test bằng migration của ứng dụng.
4. Seed một customer và một order có test_run_id.
5. Gọi service nghiệp vụ để chuyển trạng thái đơn hàng, rồi assert kết quả.
6. Cleanup đúng các bản ghi theo thứ tự phụ thuộc.

### Phần B: Cloud Storage integration

1. Tạo bucket test đã được phê duyệt hoặc nhận bucket test có sẵn từ nhóm quản trị.
2. Dùng service account có quyền đọc/ghi/xóa object trong phạm vi test.
3. Sinh prefix integration/orders-api/RUN_ID/ duy nhất cho mỗi run.
4. Upload JSON nhỏ có nội dung xác định và kiểm tra nội dung, content type.
5. Dọn object vừa tạo bằng BlobId có generation.
6. Chạy test hai lần và xác minh lần thứ hai không bị ảnh hưởng bởi lần thứ nhất.
7. Chạy hai job song song để kiểm tra không xảy ra va chạm dữ liệu.

### Phần C: cleanup khi bị ngắt

1. Tạo một fixture test trong project thử nghiệm, ghi metadata owner/run ID/createdAt.
2. Mô phỏng runner bị dừng **trong môi trường thử nghiệm** trước khi cleanup.
3. Chạy sweeper ở chế độ dry-run và xác nhận chỉ liệt kê resource của run đã quá hạn.
4. Kiểm tra allowlist project, prefix khác rỗng, giới hạn số resource và lease.
5. Bật cleanup thật cho đúng run trong phạm vi test, sau đó xác minh resource đã được dọn.
6. Lưu báo cáo tạo/xóa resource cùng trạng thái thành công hoặc lỗi.

### Tiêu chí hoàn thành

- Dữ liệu thử tổng hợp, có nội dung xác định và không chứa credential thật.
- Mỗi test và mỗi run có tên tài nguyên độc lập.
- Test logic và cleanup đều có assertion hoặc bằng chứng riêng.
- Test thất bại vẫn kích hoạt cleanup tại chỗ khi runner còn hoạt động.
- Sweeper chỉ xử lý resource thử quá hạn và không động vào resource dùng chung.
- Có kiểm tra IAM, deadline, retry và giới hạn số tài nguyên dọn.
- Hai lần chạy liên tiếp và hai lần chạy song song không ảnh hưởng lẫn nhau.

## 19. Checklist trước khi chạy integration test trên GCP

- [ ] Test dùng project và service account dành riêng cho môi trường thử nghiệm.
- [ ] Fixture tự tạo dữ liệu cần thiết, không phụ thuộc bản ghi có sẵn.
- [ ] Nội dung dữ liệu xác định, clock được kiểm soát khi cần.
- [ ] Tên resource có run ID/test ID duy nhất và đúng quy tắc đặt tên.
- [ ] Test không sử dụng dữ liệu người dùng hoặc token production.
- [ ] Teardown nằm trong finally/AfterEach/try-with-resources phù hợp.
- [ ] Cleanup chỉ nhắm vào tài nguyên hoặc dữ liệu do test sở hữu.
- [ ] Cleanup chịu được thao tác lặp và resource đã bị xóa.
- [ ] Các dependency được dọn theo thứ tự an toàn.
- [ ] Lỗi cleanup không làm mất nguyên nhân thất bại của assertion.
- [ ] Test async dùng polling có deadline, không sleep tùy ý.
- [ ] CI có timeout và cơ chế thu gom tài nguyên mồ côi.
- [ ] Sweeper có allowlist, kiểm tra owner/age/lease và dry-run.
- [ ] Quyền IAM của test runner và sweeper là tối thiểu.
- [ ] Log chứa run ID/resource ID, không chứa dữ liệu nhạy cảm.
- [ ] Test có thể chạy lại và chạy song song mà không va chạm.
- [ ] Tần suất tạo resource, quota và ngân sách đã được tính đến.

## Câu hỏi tự kiểm tra

**1. Fixture khác seed data như thế nào?**

Fixture là toàn bộ trạng thái hoặc tài nguyên cần cho một test; seed data là một phần dữ liệu đầu vào được nạp vào hệ thống. Fixture có thể bao gồm database container, mock dependency và cơ chế cleanup.

**2. Vì sao dữ liệu fixture nên xác định nhưng resource name phải duy nhất?**

Nội dung xác định giúp assertion lặp lại đáng tin cậy. Tên duy nhất giúp các test và runner chạy song song không ghi đè hoặc xóa tài nguyên của nhau.

**3. @AfterEach có bảo đảm dọn được mọi tài nguyên cloud không?**

Không. Callback có thể không chạy nếu runner bị kill hoặc máy CI mất kết nối. Cần cleanup dự phòng như sweeper có kiểm soát.

**4. Vì sao không nên xóa bucket hoặc topic dùng chung sau test?**

Vì resource dùng chung có thể chứa dữ liệu hoặc dependency của test khác. Cleanup phải giới hạn theo object, subscription hoặc resource thuộc quyền sở hữu của run hiện tại.

**5. Khi nào nên dùng Testcontainers thay vì emulator?**

Testcontainers phù hợp cho dịch vụ có image container như PostgreSQL khi cần kiểm tra hành vi thực của database. Emulator phù hợp với dịch vụ GCP hỗ trợ giả lập như Firestore/Pub/Sub và không yêu cầu mọi đặc tính của môi trường cloud thật.

**6. Nếu xóa một Firestore document cha thì subcollection có tự biến mất không?**

Không. Cần thiết kế cleanup cho các document con hoặc dùng cơ chế xóa đệ quy phù hợp với phạm vi được phép.

**7. Điều gì cần xảy ra nếu cleanup gặp 403 PermissionDenied?**

Không retry vô hạn. Báo lỗi quyền, ghi lại resource ID và chuyển cho sweeper hoặc người vận hành có quyền phù hợp; không cấp Owner cho runner để chữa cháy.

**8. Vì sao integration tests không nên chạy bằng cùng service account với production runtime?**

Test có nhu cầu tạo và xóa dữ liệu, trong khi runtime production thường chỉ cần quyền nghiệp vụ. Tách danh tính giảm nguy cơ test tác động nhầm vào production và giúp audit rõ ràng.

## Tài liệu tham khảo

- [JUnit 5 User Guide – Test Lifecycle](https://junit.org/junit5/docs/current/user-guide/)
- [Testcontainers Java](https://java.testcontainers.org/)
- [Spring Boot Testing – Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Framework – DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Google Cloud Firestore emulator](https://cloud.google.com/firestore/native/docs/emulator)
- [Google Cloud Pub/Sub emulator](https://cloud.google.com/pubsub/docs/emulator)
- [Cloud Storage Java client libraries](https://cloud.google.com/storage/docs/reference/libraries)
- [Cloud Storage object versioning](https://cloud.google.com/storage/docs/object-versioning)
- [Cloud Scheduler documentation](https://cloud.google.com/scheduler/docs)
- [IAM best practices](https://cloud.google.com/iam/docs/using-iam-securely)

## Kết luận

Test fixtures giúp ứng dụng Java có dữ liệu và trạng thái đầu vào rõ ràng để kiểm thử lặp lại. Với Google Cloud, thiết kế fixture còn phải bao gồm quyền sở hữu resource, tên duy nhất theo run, IAM, chi phí và cleanup. Testcontainers và emulator giúp kiểm thử tích hợp mà không cần tạo mọi tài nguyên cloud; những trường hợp cần xác minh hành vi thật nên chạy trên test project được kiểm soát. Một bộ test đáng tin cậy luôn có cleanup tại chỗ, xử lý lỗi idempotent và sweeper dự phòng cho resource mồ côi. Khi kết hợp các cơ chế này, nhóm có thể tăng tần suất CI/CD mà vẫn hạn chế flaky test, rò rỉ dữ liệu và tài nguyên thử bị bỏ lại.
