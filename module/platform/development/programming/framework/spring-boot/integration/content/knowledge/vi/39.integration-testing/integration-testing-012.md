# Quản lý dữ liệu thử nghiệm và dọn tài nguyên sau kiểm thử

Một kiểm thử tích hợp có thể chạy thành công khi thực hiện riêng lẻ nhưng thất bại khi chạy cùng toàn bộ test suite. Nguyên nhân thường không nằm ở một câu lệnh assertion: dữ liệu còn sót trong cơ sở dữ liệu, khóa cache chưa xóa, message từ lần chạy trước, cổng HTTP còn bị chiếm, file tạm chưa dọn, hoặc tiến trình bất đồng bộ tiếp tục sửa dữ liệu sau khi test kết thúc. Vì vậy **chuẩn bị dữ liệu thử nghiệm** và **dọn tài nguyên** là một phần của hợp đồng kiểm thử, không phải công đoạn phụ.

Bài học thuộc chương **Kiểm thử tích hợp** của **SPRING_BOOT_INTEGRATION**. Trong hệ thống Spring Boot kết nối HTTP client, cơ sở dữ liệu, cache, broker thông điệp và adapter Spring Integration, mục tiêu là dựng trạng thái thử nghiệm đủ thực tế, kiểm soát giao dịch, lỗi, xử lý trùng lặp và bảo đảm các bài test có thể chạy lặp lại, song song, trong CI mà vẫn quan sát được nguyên nhân thất bại.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Xác định tài nguyên và trạng thái nào do từng integration test tạo ra hoặc sửa đổi.
2. Chọn giữa **rollback transaction**, **dọn dữ liệu có mục tiêu**, **reset schema**, **tạo tài nguyên riêng** và **huỷ môi trường dùng một lần**.
3. Tạo fixture có thể tái lập bằng SQL, builder/factory, API hoặc migration với khóa định danh ổn định.
4. Giải thích vì sao **@Transactional** trên test không hoàn tác được mọi tác động của HTTP server, message listener, cache hay external API.
5. Sử dụng JUnit Jupiter, Spring Test, **@Sql**, Testcontainers và các công cụ bổ trợ để thiết lập và dọn trạng thái đúng vòng đời.
6. Thiết kế test tránh đụng nhau khi chạy song song, bảo vệ dữ liệu dùng chung và phát hiện rò rỉ tài nguyên sau khi test kết thúc.
7. Kiểm tra một luồng tích hợp thực tế từ DB đến Redis/broker, bao gồm tác động bất đồng bộ và khả năng chạy lại.

## 2. Xác định ranh giới trạng thái của một integration test

Integration test thường khởi tạo ApplicationContext, kết nối database thực, truy cập Redis, phát message qua broker và gọi dịch vụ giả lập. Mỗi thành phần có vòng đời, quyền sở hữu và cách phục hồi khác nhau.

~~~mermaid
flowchart TD
    TEST["JUnit integration test"] --> APP["Spring Boot ApplicationContext"]
    TEST --> FIXTURE["Setup test fixtures"]
    APP --> DB[("SQL database")]
    APP --> CACHE[("Redis / cache")]
    APP --> BROKER[("Kafka / RabbitMQ")]
    APP --> HTTP["HTTP mock server / external stub"]
    APP --> FS["Filesystem / SFTP"]
    TEST --> VERIFY["Assert outcomes + no unwanted side effects"]
    VERIFY --> CLEAN["Cleanup / rollback / dispose"]
    CLEAN --> DB
    CLEAN --> CACHE
    CLEAN --> BROKER
    CLEAN --> HTTP
    CLEAN --> FS
~~~

| Tài nguyên | Trạng thái có thể còn sót | Cách quản lý thường gặp |
|---|---|---|
| **Cơ sở dữ liệu** | Rows, sequence, lock, bảng staging, outbox/inbox, transaction chưa kết thúc | Rollback nếu cùng transaction; cleanup theo business key; schema/container riêng |
| **Redis/cache** | Key, TTL, lock token, consumer state, counter | Prefix định danh test, danh sách key đã tạo, xóa có mục tiêu; TTL dự phòng |
| **Broker thông điệp** | Topic/queue, message pending, offset, consumer group, DLQ | Topic/queue hoặc group riêng, drain/ack đúng hợp đồng, môi trường dùng một lần |
| **Mock HTTP** | Stub mapping, request history, response queue, cổng đang mở | Reset stub/history mỗi test; shutdown server sau suite hoặc mỗi test |
| **File/SFTP/object storage** | File tải lên, file processed, marker, checksum, directory | Thư mục/bucket prefix riêng; xóa nội dung đúng phạm vi và đóng stream |
| **Spring context** | Bean singleton có state, scheduler, cache in-memory, thread pool | Reset state test-owned, đóng context đúng lifecycle, dùng @DirtiesContext khi thật sự cần |
| **Hạ tầng Docker/Testcontainers** | Container, volume, network, dữ liệu trong dịch vụ | Container dùng một lần; lifecycle do Testcontainers quản lý, không tái sử dụng khi cần sạch tuyệt đối |

Đầu tiên phải phân biệt **tài nguyên được sở hữu bởi bài test** và **tài nguyên dùng chung**. Chỉ test owner mới có quyền dọn tài nguyên của mình. Một lệnh xóa toàn bộ bảng hoặc xóa mọi Redis key có thể vô hại với database hoàn toàn dành riêng cho test đó, nhưng là lỗi nghiêm trọng nếu môi trường đang được các test khác sử dụng.

## 3. Những bất biến của dữ liệu thử nghiệm tốt

Một integration test đáng tin cậy cần thỏa các nguyên tắc sau:

1. **Lặp lại được:** chạy test hai lần với cùng điều kiện tạo cùng kết quả nghiệp vụ.
2. **Độc lập với thứ tự:** test B không cần test A tạo dữ liệu trước hoặc xóa dữ liệu sau.
3. **Cô lập:** dữ liệu của test A không bị test B đọc nhầm, kể cả khi chạy song song.
4. **Có chủ sở hữu:** mỗi hàng, key, topic, file hay stub được tạo có định danh và phạm vi cleanup rõ.
5. **Đủ thực tế:** fixture tuân thủ unique constraint, foreign key, schema, encoding, version và quy tắc nghiệp vụ giống production.
6. **Có bằng chứng:** khi setup/cleanup thất bại, test báo lỗi cụ thể; không nuốt exception để suite trông có vẻ xanh.
7. **Có đường phục hồi:** JVM crash, test timeout hoặc CI agent mất kết nối không khiến tài nguyên dùng chung bị ô nhiễm vĩnh viễn.

**Mục tiêu không nhất thiết là “mọi tài nguyên đều trống sau mỗi test”.** Với database riêng của một test suite, migration/schema cố định có thể được giữ lại để giảm thời gian; còn những hàng nghiệp vụ thay đổi phải sạch hoặc mang namespace đủ cô lập. Điều quan trọng là test tiếp theo nhìn thấy trạng thái đúng hợp đồng đã công bố.

## 4. Chọn chiến lược cô lập và cleanup

| Chiến lược | Phạm vi | Điểm mạnh | Rủi ro / giới hạn |
|---|---|---|---|
| **Rollback test transaction** | Dữ liệu trong cùng giao dịch kiểm thử | Nhanh, không cần xóa từng hàng | Không bao phủ thread/transaction khác, HTTP thật, broker, Redis hay side effect ngoài DB |
| **Cleanup theo business key / test ID** | Chỉ rows/keys thuộc test | Phù hợp DB dùng chung có điều kiện, rõ trách nhiệm | Phải xóa theo FK và xử lý tác động bất đồng bộ |
| **@Sql setup/teardown** | Fixture SQL xác định trước | Dễ đọc, tái lập được, chạy được theo lifecycle Spring Test | Script cần tương thích schema, transaction mode và phạm vi chạy |
| **Reset schema / truncate** | Toàn schema test | Sạch mạnh, hỗ trợ test nhiều bảng | Tốn chi phí, không dùng trong môi trường chung, liên quan FK/sequence |
| **Schema hoặc database riêng từng test** | Cách ly trong một server DB | Chạy song song tốt, giảm phụ thuộc cleanup chi tiết | Tốn tài nguyên, cần migration/cleanup schema sau |
| **Container dùng một lần** | Cả dịch vụ và trạng thái bên trong | Độc lập môi trường, thực tế hơn mock | Khởi động chậm hơn, vẫn cần quản lý external resources ngoài container |
| **Namespace có TTL** | Redis keys, object prefix, tên queue/topic | Dễ theo dõi và dọn có mục tiêu | TTL không thay thế cleanup chủ động khi cần kiểm tra rò rỉ |

**Quy tắc chọn:** với test đơn vị nhỏ và DB transaction cùng thread, rollback thường đủ. Với integration test qua HTTP thật, queue/broker hoặc scheduler, cần đối xử nó như một luồng nhiều giao dịch: setup có định danh, chờ side effect hoàn tất, verify và cleanup từng tài nguyên.

## 5. Thiết kế fixture: dữ liệu đầu vào phải có ý nghĩa

Fixture là dữ liệu và cấu hình cần tồn tại trước khi thao tác được kiểm thử bắt đầu. Một fixture tốt nhỏ nhưng thể hiện được hợp đồng quan trọng: quan hệ cha–con, unique key, trạng thái, version, timestamp và loại lỗi.

### 5.1. Nên ưu tiên cách tạo fixture nào?

| Cách tạo | Phù hợp khi | Cần chú ý |
|---|---|---|
| **SQL seed script / @Sql** | Cấu trúc DB ổn định, cần thấy rõ rows và FK | Không lệ thuộc ID sequence khó dự đoán; script có cleanup tương ứng |
| **Factory / builder trong Java** | Nhiều biến thể nghiệp vụ, dữ liệu khác nhau theo test | Default hợp lệ, không che các trường quan trọng bằng quá nhiều magic values |
| **Repository / DAO** | Test service hoặc integration endpoint, cần seed trạng thái nội bộ | Hãy quyết định có muốn đi qua validation/service hay không |
| **HTTP API setup** | Test theo contract công khai và cần đường tạo dữ liệu thật | Chậm hơn, side effect rộng hơn; không gọi API phụ để có fixture nếu có cách đơn giản hơn |
| **Snapshot/migration** | Schema chuẩn, dữ liệu tham chiếu ít thay đổi | Versioning rõ; không cho test sửa bản ghi tham chiếu chung |
| **Docker init script** | DB/broker/container có trạng thái nền xác định | Phải hiểu init script chạy khi container/volume được khởi tạo, không phải trước mỗi test |

Ví dụ một test đối soát đơn hàng nên tạo **customer**, **order**, **order_item** với business key cụ thể như **it-order-...**, và một bản ghi outbox nếu bài toán cần phát message. Không nên copy cả database production đã ẩn danh nhưng vẫn chứa hàng nghìn record không liên quan; fixture lớn làm test khó lý giải và dễ phụ thuộc dữ liệu vô tình.

### 5.2. Test ID và namespace

Sinh một định danh riêng cho từng test hoặc lần chạy:

~~~java
String testRunId = "it-" + java.util.UUID.randomUUID();
String externalOrderId = testRunId + "-order-1";
String redisKey = "it:order:" + testRunId;
~~~

Dùng cùng **testRunId** trong business key, header correlation, Redis prefix và tên file tạm. Khi thất bại, log theo testRunId cho phép truy ngược toàn bộ luồng. Không đưa giá trị UUID riêng mỗi test thành metric label vì làm tăng cardinality; chỉ dùng trong log/tracing hoặc dữ liệu test.

**Không phụ thuộc ID tự tăng**: hai test chạy song song không thể cùng kỳ vọng row kế tiếp có ID = 101. Dùng khóa nghiệp vụ riêng hoặc đọc giá trị ID được DB tạo rồi truyền vào bước tiếp theo.

### 5.3. Chuẩn bị dữ liệu theo trạng thái rõ ràng

Ví dụ với đơn hàng tích hợp:

~~~text
BEFORE:
  customer: ACTIVE
  order.externalId: it-xxx-order-1
  order.status: NEW
  outbox: không có event ORDER_CONFIRMED cho order này
  Redis: không có key cache của order này
  broker: consumer group riêng đã sẵn sàng

ACTION:
  POST /orders/{externalId}/confirm

AFTER:
  order.status = CONFIRMED
  outbox / broker chứa event đúng một lần theo business key
  Redis cache đã invalidate hoặc refresh theo hợp đồng
~~~

Viết rõ trạng thái **before/action/after** giúp tránh test chỉ kiểm tra mã HTTP 200 mà bỏ qua side effect quan trọng.

## 6. @Transactional trong Spring Test: dùng đúng ranh giới

Spring TestContext hỗ trợ **test-managed transaction** khi test dùng **@Transactional** và có transaction manager phù hợp. Với cách chạy thông thường, transaction của test được rollback khi kết thúc. Điều này rất hữu ích cho test repository/service cùng thread.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class OrderRepositoryIT {

    @Autowired OrderRepository orders;

    @Test
    void savesOrderInsideTestTransaction() {
        Order order = orders.save(new Order("it-order-123"));
        assertThat(orders.findByExternalId("it-order-123")).isPresent();
        // Theo mặc định, test-managed transaction sẽ rollback.
    }
}
~~~

Ở đây **OrderRepository** và **Order** chỉ minh họa domain của ứng dụng; khi dùng cần thay bằng entity/repository thực tế. Ví dụ chứng minh cơ chế rollback trong cùng transaction, không tự xác nhận hệ thống đã commit một giao dịch HTTP thật.

### 6.1. Vì sao rollback không đủ cho kiểm thử end-to-end?

Khi **@SpringBootTest(webEnvironment = RANDOM_PORT)** khởi chạy web server và test gửi HTTP thực tế, controller/service xử lý request trên thread khác với thread của test. Transaction của test **không bao quanh** transaction server; DB write bên server có thể commit bình thường.

Điều tương tự xảy ra với:

- Async listener chạy trên executor.
- Kafka/RabbitMQ consumer chạy trên consumer thread.
- Scheduler hoặc Spring Integration poller chạy độc lập.
- HTTP request tới hệ thống bên ngoài.
- Redis write hay file/object-storage write không tham gia transaction DB của test.
- Method dùng transaction độc lập như **REQUIRES_NEW** khi thực thi theo điều kiện phù hợp.

**Phản ví dụ thường gặp:** một test gắn **@Transactional**, gọi **TestRestTemplate.postForEntity(...)**, rồi tin rằng DB server tự rollback cuối test. Kết quả là dữ liệu từ endpoint vẫn còn sau khi test và làm test tiếp theo thất bại.

### 6.2. @Rollback và @Commit

**@Rollback(false)** hoặc **@Commit** khiến test-managed transaction được commit thay vì rollback. Chỉ dùng khi bài test thật sự cần xác minh hành vi sau commit và đã có kế hoạch cleanup. Đừng bật chúng để chữa việc test không thấy dữ liệu ở thread khác mà không hiểu isolation.

Các callback của JUnit và Spring TestContext có thứ tự lifecycle riêng; với test transaction, **@BeforeTransaction** và **@AfterTransaction** giúp xử lý thao tác trước/sau ranh giới giao dịch khi cần. Nếu một logic cleanup phải chạy sau commit/rollback, không suy đoán rằng bất kỳ **@AfterEach** nào cũng luôn nằm ngoài transaction test.

### 6.3. Khi nên chọn rollback?

Chọn rollback cho các test nhắm vào repository/DAO hoặc service đồng bộ trong một transaction có thể kiểm soát. Khi kiểm thử commit thực, retry, broker, HTTP hoặc polling, ưu tiên test với transaction thật rồi cleanup có mục tiêu hoặc môi trường riêng.

## 7. Dùng @Sql để seed và cleanup dữ liệu

Spring Test hỗ trợ **@Sql** để thực thi script trước hoặc sau test method. Ví dụ cho một test HTTP thật với PostgreSQL dùng Testcontainers:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers
@Sql(
    scripts = "/sql/order-seed.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED)
)
@Sql(
    scripts = "/sql/order-clean.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED)
)
class OrderHttpIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    TestRestTemplate http;

    @Test
    void readsSeededOrder() {
        ResponseEntity<String> response =
            http.getForEntity("/orders/it-order-fixture", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("it-order-fixture");
    }
}
~~~

Ví dụ giả định ứng dụng có endpoint **GET /orders/{externalId}**, bảng đơn hàng và hai SQL script trong **src/test/resources/sql**; các script được minh hoạ bên dưới, **không được tự tạo trong bài học này**. Khi triển khai, cần kiểm tra script có chạy đúng thứ tự với migration/Flyway/Liquibase, trỏ đúng datasource và có transaction manager phù hợp.

~~~sql
-- /sql/order-seed.sql (ví dụ, tên bảng/cột phải đổi theo schema thật)
INSERT INTO customers (id, external_code)
VALUES (910001, 'it-customer-fixture');

INSERT INTO orders (id, customer_id, external_id, status)
VALUES (920001, 910001, 'it-order-fixture', 'NEW');

-- /sql/order-clean.sql: các DELETE chạy sau test
DELETE FROM order_items WHERE order_id = 920001;
DELETE FROM outbox_events WHERE aggregate_id = 'it-order-fixture';
DELETE FROM orders WHERE external_id = 'it-order-fixture';
DELETE FROM customers WHERE external_code = 'it-customer-fixture';
~~~

**Quan trọng:** SQL bên trên chỉ để học, không có schema thực tế được khẳng định. Các bảng liên quan khác phải được bổ sung theo FK. Nếu có hai test class đồng thời dùng cùng **it-order-fixture** trên một database chung, chúng vẫn đụng dữ liệu; trong ví dụ này container riêng theo class giúp cô lập, nhưng hai method cùng class chạy song song vẫn cần điều phối hoặc fixture riêng.

### 7.1. Vì sao dùng TransactionMode.ISOLATED?

Với **@SqlConfig(transactionMode = ISOLATED)**, Spring Test thực thi script trong transaction độc lập và commit trước khi test (setup) hoặc sau khi test (cleanup) khi có transaction manager phù hợp. Điều này hữu ích cho test gọi HTTP server khác thread: dữ liệu seed phải **được commit** để server có thể đọc dưới isolation bình thường.

Không nên mặc định dùng isolated trên tất cả test. Với repository test **@Transactional** cần rollback mọi thay đổi, script nằm trong transaction test có thể phù hợp hơn. Chọn dựa trên phạm vi transaction và mục tiêu của test, thay vì áp một annotation cho toàn suite.

### 7.2. Hạn chế của script cleanup

- Không biết trước mọi ID nếu application sinh chúng trong lúc xử lý.
- Không bao phủ side effect ở Redis, broker hay external API.
- Có thể vi phạm FK khi xóa sai thứ tự.
- Không tự giải quyết asynchronous handler vẫn tiếp tục ghi sau khi script đã xóa.
- Sẽ không chạy nếu JVM bị kill ngay lập tức hoặc CI agent mất điện.

Với dữ liệu được tạo động, cần theo dõi business key hoặc sử dụng schema/container riêng để cleanup an toàn. Khi test fail vì script, phải giữ log lỗi cleanup, không âm thầm coi test thành công.

## 8. Fixture động và cleanup theo business key

Khi test gọi endpoint tạo dữ liệu mới, không thể đoán primary key DB. Dùng một **externalId** ổn định trong phạm vi test để truy vết và xóa các bản ghi liên quan.

~~~java
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderFlowIT {

    @Autowired TestRestTemplate http;
    @Autowired JdbcTemplate jdbc;
    @Autowired StringRedisTemplate redis;

    private String orderKey;

    @BeforeEach
    void prepare() {
        orderKey = "it-" + UUID.randomUUID();
    }

    @Test
    void confirmsOrder() {
        // Ví dụ giả định endpoint sử dụng orderKey.
        http.postForEntity("/orders/" + orderKey + "/confirm",
                null, Void.class);
        // Assert DB/event/cache theo hợp đồng, không chỉ HTTP status.
    }

    @AfterEach
    void cleanup() {
        // Nếu Redis lỗi, vẫn cố xóa DB; cleanup thất bại sẽ làm test fail.
        try {
            redis.delete("order:summary:" + orderKey);
        } finally {
            jdbc.update(
                "DELETE FROM outbox_events WHERE aggregate_id = ?",
                orderKey
            );
            jdbc.update(
                "DELETE FROM order_items WHERE order_id IN "
                + "(SELECT id FROM orders WHERE external_id = ?)",
                orderKey
            );
            jdbc.update(
                "DELETE FROM orders WHERE external_id = ?",
                orderKey
            );
        }
    }
}
~~~

Đây là **mẫu cấu trúc** cần điều chỉnh theo schema và endpoint của ứng dụng; không nên coi ví dụ là test hoàn chỉnh vì chưa có assertion. Các **DELETE** chạy sau request thật; nếu listener bất đồng bộ vẫn đang chạy, nó có thể ghi lại rows sau cleanup. Vì vậy trước khi dọn phải chờ trạng thái hoàn tất/đã xác nhận hoặc kiểm soát consumer lifecycle theo quy trình rõ.

Cú pháp **try/finally** bảo đảm DB cleanup vẫn được thử nếu Redis delete ném exception. Nếu cần dọn nhiều tài nguyên độc lập, có thể dùng một utility cleanup tổng hợp lỗi: cố thực hiện từng bước, lưu mọi exception và cuối cùng fail test với các lỗi kèm theo. Không được nuốt lỗi cleanup để chỉ giữ kết quả assertion.

### 8.1. Không dùng TRUNCATE tuỳ tiện

Nếu toàn bộ database/container **chỉ thuộc test đó**, truncate hoặc drop schema có thể là cách đơn giản và chắc chắn. Nhưng trên database chung, **TRUNCATE orders CASCADE** có thể xóa dữ liệu của các test khác, làm mất thông tin cần thiết để debug và gây lỗi chạy song song khó tái hiện.

Với database chung, phải có namespace/schema hoặc xóa theo business key/tenant; với schema riêng, reset schema thường rõ ràng hơn việc xóa thủ công từng bảng.

## 9. Testcontainers: cô lập dịch vụ và quản lý vòng đời

**Testcontainers** cho phép khởi chạy PostgreSQL, Redis, Kafka, RabbitMQ hoặc các dịch vụ khác trong container để integration test sử dụng. Dữ liệu thật của dịch vụ và hành vi giao dịch được kiểm thử gần production hơn so với mock in-memory, đồng thời container có thể bị huỷ sau test suite.

### 9.1. Vòng đời phổ biến

~~~mermaid
sequenceDiagram
    participant J as JUnit / Testcontainers
    participant C as PostgreSQL container
    participant S as Spring ApplicationContext
    J->>C: Start container
    C-->>J: JDBC URL, port, credentials
    J->>S: Inject DynamicPropertySource
    S->>C: Run schema migration / connect
    J->>S: Execute tests
    S->>C: Queries + transactions
    J->>S: Close context at lifecycle boundary
    J->>C: Stop container
~~~

Một static **@Container** trong **@Testcontainers** thường được dùng cho toàn test class; instance container không static thường thuộc vòng đời từng method. Cần xem lại lifecycle theo phiên bản Testcontainers và cách test framework khởi tạo ApplicationContext. **@DynamicPropertySource** cung cấp địa chỉ/credentials động từ container; không hardcode localhost:5432 nếu port được ánh xạ ngẫu nhiên.

Spring Boot 3.1+ có hỗ trợ **@ServiceConnection** khi dùng module tích hợp Testcontainers tương ứng; đây là lựa chọn thay cho việc đăng ký một số connection property thủ công. Không cần dùng cả hai cơ chế cho cùng một kết nối nếu chúng trùng chức năng.

### 9.2. Container riêng không miễn mọi cleanup

Nếu cả suite chia sẻ một container và nhiều test ghi vào đó, dữ liệu vẫn có thể ảnh hưởng lẫn nhau. Chọn một trong các cách:

- Container riêng theo class/test nếu chi phí phù hợp.
- Database hoặc schema riêng trên cùng container.
- Mỗi test có business key riêng và cleanup có mục tiêu.
- Reset toàn schema giữa các class khi thực sự là môi trường độc quyền.

Chỉ bật container reuse giữa các lần chạy phát triển khi chủ động chấp nhận trạng thái còn sót và đã có quy trình reset. CI cần môi trường có thể tái lập, không phụ thuộc volume cũ từ máy khác.

### 9.3. Không dùng @DirtiesContext để thay cleanup DB

**@DirtiesContext** yêu cầu Spring TestContext đánh dấu ApplicationContext không còn phù hợp để tái sử dụng, khiến context bị đóng và tạo lại khi cần. Nó hữu ích nếu test làm thay đổi cấu hình hoặc singleton state khó khôi phục.

Tuy nhiên **@DirtiesContext không đồng nghĩa xóa rows trong DB, Redis keys, broker messages hoặc files**. Dùng nó để “chữa” dữ liệu test còn sót vừa chậm vừa không giải quyết nguồn ô nhiễm. Chỉ dùng khi context thực sự đã bị thay đổi trạng thái cần rebuild.

## 10. Redis: dọn key, lock và dữ liệu cache

Redis nằm ngoài transaction SQL của test. Khi test ghi **order:summary:it-abc**, rollback test-managed transaction không xóa key đó.

Nên ưu tiên:

1. **Prefix riêng cho test:** ví dụ **it:<runId>:...** hoặc danh sách key được test tạo.
2. **Xóa theo danh sách key chính xác** được lưu khi tạo, tránh quét toàn Redis khi không cần.
3. **TTL dự phòng** cho dữ liệu ngắn hạn để giảm trạng thái tồn đọng khi process crash; TTL không thay cho cleanup chủ động.
4. **Container Redis riêng** nếu test cần thao tác xóa toàn dữ liệu, thay đổi eviction policy hoặc failover.
5. Với **distributed lock**, kết thúc đúng ownership/token thay vì xóa key của lock do tiến trình khác giữ.

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import org.junit.jupiter.api.AfterEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;

class RedisFixtureScope {

    @Autowired StringRedisTemplate redis;

    private final Set<String> keys = new LinkedHashSet<>();

    void putFixture(String key, String value) {
        redis.opsForValue().set(key, value);
        keys.add(key);
    }

    @AfterEach
    void deleteFixtureKeys() {
        if (!keys.isEmpty()) {
            redis.delete(keys);
            keys.clear();
        }
    }
}
~~~

**Giới hạn ví dụ:** lớp này minh hoạ một scope test và không phải test class đầy đủ. Dùng registry chỉ khi tất cả key của test được tạo qua helper hoặc được đăng ký; key do application/consumer tự phát sinh cũng phải được theo dõi theo hợp đồng. Đặt **keys.add(key)** trước hoặc trong quy trình xử lý lỗi ghi Redis để cleanup được cả trạng thái không rõ ràng nếu thao tác timeout.

Tránh **FLUSHALL**, **FLUSHDB** hoặc dùng **KEYS \*** trong Redis dùng chung. Nếu bắt buộc tìm key theo prefix, xem xét **SCAN** theo batch và chứng minh namespace thuộc riêng test; quét không nguyên tử, và key có thể xuất hiện mới trong lúc cleanup.

## 11. Broker: Kafka, RabbitMQ, JMS và message còn tồn đọng

Một integration test gửi event qua broker có thể để lại message chưa ACK, retry queue, dead-letter message, consumer offset hoặc subscription state. Việc khôi phục Spring ApplicationContext không mặc nhiên xóa những tài nguyên này.

| Thành phần | Cách cô lập / dọn |
|---|---|
| **Kafka topic** | Tạo topic riêng theo test suite khi phù hợp; hoặc event key/correlation ID riêng và consumer group riêng |
| **Kafka consumer group** | Group ID riêng để tránh test khác tranh partition; kiểm soát offset/lag và broker readiness |
| **RabbitMQ queue** | Queue riêng theo test, có thể auto-delete/exclusive khi đúng mô hình; bảo đảm consumer đã ACK và queue được dọn |
| **DLQ / retry topic** | Assert được tác động và dọn đúng nguồn, không chỉ queue chính |
| **JMS destination** | Queue/topic test riêng, consumer/session đóng đúng lifecycle |
| **Spring Integration adapter** | Stop/close adapter hoặc dùng lifecycle được quản lý, chờ message đang xử lý trước khi cleanup dữ liệu đích |

### 11.1. Consumer bất đồng bộ chưa chắc đã xong khi test return

~~~mermaid
sequenceDiagram
    participant T as Test
    participant B as Broker
    participant C as Consumer
    participant D as Database
    T->>B: Publish event X
    B-->>T: ACK publish
    T->>D: Query state immediately
    D-->>T: Not updated yet
    Note over T,D: Producer ACK không bằng consumer đã commit
    B->>C: Deliver X
    C->>D: Commit business state
    T->>D: Await eventual expected state
    D-->>T: Updated
~~~

Dùng cơ chế chờ có **deadline rõ** như Awaitility hoặc polling assertion có thời gian giới hạn, thay vì **Thread.sleep(2000)** cố định. Đối với hệ thống event-driven, điều cần assert là business effect đã commit, số message trùng, queue/DLQ trạng thái phù hợp và consumer không còn pending tác vụ test-owned trước cleanup.

Không xóa queue/topic dùng chung để làm test sạch. Với broker dùng riêng trong Testcontainers, dừng/huỷ container là một biện pháp reset đáng tin cậy ở phạm vi suite; vẫn cần kiểm tra consumer/event contract trong lúc test chạy.

### 11.2. Đảm bảo idempotency trong kiểm thử

Event có thể bị phát lại khi test retry hoặc broker re-deliver. Gắn eventId/businessId duy nhất và kiểm tra rằng hai lần nhận cùng ID chỉ tạo **một tác động nghiệp vụ** khi hợp đồng đòi hỏi. Không đánh giá tính đúng bằng cách đếm chính xác số lần handler được gọi; handler có thể chạy nhiều lần mà kết quả nghiệp vụ vẫn đúng nhờ idempotency.

## 12. Mock HTTP và external service

Khi test dùng **WireMock**, **MockWebServer**, mock OAuth server hoặc stub dịch vụ đối tác, phải quản lý ba loại trạng thái: cấu hình phản hồi, nhật ký request và tài nguyên mạng (port/socket/thread).

- Stub mỗi test nên mô tả rõ URL, method, header, request body cần thiết; tránh stub khớp tất cả và vô tình che lỗi hợp đồng.
- Reset **request journal/history** và **stub mappings** ở scope thích hợp; tránh assertion nhìn nhầm request từ test trước.
- Không bắt buộc một port cố định khi có thể chọn port động; cung cấp base URL cho Spring Boot bằng properties tương ứng.
- Shutdown server đúng lifecycle, đóng stream/body và client connection nếu tự quản lý.
- Với test retry HTTP, kiểm tra cả số request đã phát và nội dung idempotency key trong các request; test không chỉ nhìn response cuối.

Ví dụ ý tưởng lifecycle:

~~~text
@BeforeAll:
  khởi chạy mock HTTP server (port động)
  cấu hình base URL của HTTP client cần kiểm thử

@BeforeEach:
  reset request history + stub mappings
  đăng ký response cho đúng test scenario

@Test:
  gọi integration flow
  assert request contract, retry count, business result

@AfterAll:
  shutdown mock server và giải phóng port/thread
~~~

**Lưu ý:** trong Spring Test, việc đăng ký dynamic properties và khởi động mock server phải được sắp xếp sao cho server đã sẵn sàng trước khi ứng dụng cần base URL. Nếu dùng static **@DynamicPropertySource** và static mock server, cần kiểm soát chính xác thứ tự khởi tạo; không giả định @BeforeAll luôn chạy trước ApplicationContext creation trong mọi kiểu cấu hình.

## 13. File tạm, SFTP và object storage

JUnit Jupiter hỗ trợ **@TempDir** để cấp thư mục tạm cho từng test hoặc scope theo khai báo. Điều này hữu ích với file adapter, batch import, parser CSV và xử lý file staging.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FileImportIT {

    @TempDir
    Path workDir;

    @Test
    void writesFixtureToOwnedDirectory() throws Exception {
        Path input = workDir.resolve("orders.csv");

        Files.writeString(input,
                "externalId,status\nit-order-1,NEW\n",
                StandardCharsets.UTF_8);

        assertThat(Files.readString(input)).contains("it-order-1");
        // Integration adapter sẽ được cấu hình đọc từ workDir.
    }
}
~~~

**@TempDir** quản lý dọn thư mục theo vòng đời JUnit tương ứng; nếu một process con hay adapter vẫn đang giữ file handle, cleanup có thể thất bại tùy hệ điều hành. Cần đóng streams, stop file watcher/poller và chờ xử lý xong trước khi kết thúc test.

Với SFTP hoặc object storage:

- Tạo thư mục/prefix riêng theo testRunId, ví dụ **/it/<runId>/inbound/**.
- Ghi file theo quy ước producer dùng trong production: tên tạm rồi rename, marker **.done**, checksum nếu có.
- Kiểm tra cả file **processed**, **archive**, **error** và marker để cleanup đầy đủ.
- Không xóa nguyên bucket/thư mục root dùng chung; không dùng wildcard rộng trên endpoint thật.
- Với object storage có khả năng nhất quán cuối cùng ở một số thao tác/hệ thống, chờ trạng thái xóa phù hợp khi kiểm thử phụ thuộc vào điều đó.

Nếu chỉ kiểm thử CSV parser, không cần khởi chạy SFTP thật; dùng @TempDir và input fixture là đủ. Nếu kiểm thử SFTP adapter, cần một SFTP server giả lập hoặc container để kiểm tra đúng handshake, permission, file listing/filter và reconnect.

## 14. Thread, scheduler, connection và resource leak

Một test có thể dọn sạch dữ liệu nhưng vẫn giữ connection, thread hoặc socket:

- **ExecutorService** tạo trong test mà không shutdown.
- **ScheduledExecutorService** vẫn chạy polling sau khi test kết thúc.
- **CloseableHttpClient**, WebClient connection resource hoặc MockWebServer không được đóng theo lifecycle.
- JDBC **ResultSet/Statement/Connection** tự mở không dùng try-with-resources.
- File watcher, InputStream hoặc NIO channel còn giữ file.
- Broker consumer còn hoạt động và có thể nhận message của test sau.

Với tài nguyên do test trực tiếp tạo, dùng **try-with-resources** khi interface hỗ trợ **AutoCloseable**, hoặc quản lý shutdown trong @AfterEach/@AfterAll:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class BackgroundTaskFixture {

    private ExecutorService executor;

    @BeforeEach
    void setup() {
        executor = Executors.newFixedThreadPool(2);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        executor.shutdown();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor chưa dừng");
            }
        }
    }
}
~~~

Ví dụ chỉ mô tả lifecycle executor do test tạo. Với thread pool do Spring quản lý, ưu tiên để ApplicationContext quản lý hoặc dùng cơ chế **Lifecycle/SmartLifecycle** phù hợp; không tự shutdown một bean dùng chung cho nhiều test khi các test khác còn phụ thuộc vào nó.

### 14.1. Dọn theo thứ tự phụ thuộc

Trong một luồng adapter bất đồng bộ, thứ tự dọn nên là:

1. Ngừng tạo thêm event hoặc yêu cầu mới thuộc test.
2. Chờ tác vụ test-owned hoàn tất, ACK hoặc chuyển trạng thái đã xác định.
3. Stop consumer/poller/adapter do test quản lý nếu cần tránh ghi muộn.
4. Assert kết quả nghiệp vụ và trạng thái lỗi/dlq theo hợp đồng.
5. Xóa dữ liệu có mục tiêu ở broker/cache/DB/files, theo thứ tự phụ thuộc.
6. Đóng HTTP mock, connection, thread và container ở đúng scope.

Không xóa DB trước khi consumer xử lý xong: consumer có thể ghi lại row sau cleanup và gây nhiễm test tiếp theo.

## 15. Chạy test song song và tránh “flaky test”

Khi Maven/Gradle hoặc JUnit cho phép các test chạy song song, việc dùng chung một database/Redis/topic mà không phân vùng dữ liệu thường gây lỗi không lặp lại được.

### 15.1. Các mẫu xung đột

| Xung đột | Triệu chứng | Cách khắc phục |
|---|---|---|
| Hai test cùng dùng externalId cố định | Unique violation hoặc assert nhầm row | ID riêng, DB/schema riêng |
| Test A TRUNCATE bảng khi B đang chạy | Test B mất dữ liệu | Không truncate resource chung; cô lập schema/container |
| Hai consumer cùng group ID | Chia partition bất ngờ, test không thấy message | Group/topic riêng hoặc điều phối |
| Mock server request journal dùng chung | Sai số request được đếm | Reset theo scope hoặc server riêng |
| Redis key cố định | Kết quả cache hit từ test trước | Key prefix riêng và cleanup |
| Scheduler tiếp tục hoạt động | Row xuất hiện sau khi teardown | Stop/drain job hoặc kiểm soát thời điểm kích hoạt |
| Test phụ thuộc wall-clock/timezone | Hết TTL quá sớm, lệch ngày | Inject Clock/fake time, cấu hình timezone |
| Test dùng sleep cố định | Fail trên CI chậm | Await điều kiện với deadline và thông báo lỗi rõ |

### 15.2. Khi nào nên tắt song song?

Có thể dùng cơ chế điều phối của JUnit như **@ResourceLock** cho tài nguyên dùng chung trong cùng một execution engine hoặc cấu hình test suite không chạy song song. Tuy nhiên giải pháp bền vững hơn là test-owned namespace/schema/container, để test vẫn độc lập khi CI shard test class ra nhiều tiến trình/JVM khác nhau. Lock của JUnit trong một tiến trình không bảo vệ được database chung trước process CI khác.

## 16. Dữ liệu bí mật và giới hạn môi trường test

Dữ liệu kiểm thử nên là **synthetic data**. Không dùng trực tiếp thông tin cá nhân, credentials, API token hoặc bản sao production không được xử lý theo quy định. Một số nguyên tắc:

- Password/token trong test chỉ có quyền trên môi trường test, lấy từ secret management khi cần; không commit bí mật thật vào repository.
- Endpoint external client phải trỏ vào sandbox/stub được kiểm soát; test không được vô tình tạo đơn, gửi email hoặc chuyển tiền thật.
- Với dữ liệu đại diện cho PII, dùng giá trị giả và masking trong log/metric.
- Khi dọn tài nguyên, xác minh **test environment marker** hoặc danh sách tài nguyên được phép; thao tác nguy hiểm như DROP schema/FLUSHALL chỉ thực hiện trong môi trường độc quyền đã xác định.
- Không tạo fixture bằng cách tải dữ liệu nhạy cảm thực từ production nếu không có quy trình bảo vệ và chấp thuận phù hợp.

Lỗi cấu hình environment là một trong những nguyên nhân nguy hiểm nhất của automated cleanup: một hostname sai có thể khiến script dọn đúng câu lệnh nhưng nhầm hệ thống.

## 17. Kiểm thử quá trình cleanup, không chỉ nghiệp vụ

Một test có thể pass khi dữ liệu rác chưa ảnh hưởng tới nó, nhưng đêm hôm sau suite bắt đầu fail. Kiểm thử chất lượng cleanup như một bất biến:

1. Chạy cùng một class ít nhất hai lần trên môi trường có thể tái sử dụng.
2. Đổi thứ tự test method hoặc chạy mỗi test riêng lẻ.
3. Kiểm tra số row/keys/files test-owned bằng **testRunId** trước và sau cleanup.
4. Nếu test tạo message asynchronous, đợi trạng thái hoàn tất hoặc DLQ trước khi cleanup.
5. Tiêm lỗi vào giữa luồng: API timeout, listener crash, DB rollback, container restart; xác nhận tài nguyên không bị ghi trùng.
6. Chạy một nhóm test song song trong cùng điều kiện CI khi các nguồn được phép chia sẻ.
7. Khi cleanup thất bại, đánh dấu test FAILED và xuất danh sách tài nguyên còn sót để điều tra.

### 17.1. Một phép kiểm tra sau teardown

~~~text
Resource scope: testRunId = it-27ac...
DB:
  orders with external_id prefix: 0
  outbox_events for testRunId: 0
Redis:
  keys explicitly registered by test: 0
Broker:
  pending messages/consumer state for testRunId: resolved
Filesystem:
  files under owned prefix: 0
HTTP mock:
  server closed or reset within documented scope

Nếu một điều kiện không đạt:
  báo FAILED (cleanup/teardown),
  ghi tên resource + testRunId + nguyên nhân,
  không nuốt exception.
~~~

Tình huống có hệ thống eventual consistency cần một **deadline** hữu hạn để kiểm tra trạng thái cuối; không kiểm tra ngay rồi gán lỗi giả khi consumer chưa kịp commit. Ngược lại, chờ vô hạn vì “có thể sẽ xong” khiến CI treo.

## 18. Tình huống tổng hợp: HTTP → DB → outbox → broker → Redis

Một endpoint Spring Boot nhận lệnh tạo đơn hàng, lưu DB và outbox, sau đó publisher phát event lên broker. Consumer cập nhật Redis cache. Integration test cần chứng minh đúng hợp đồng và không để dữ liệu sót lại sau khi chạy.

~~~mermaid
flowchart TD
    FIX["Test fixture: customer + testRunId"] --> HTTP["POST /orders"]
    HTTP --> TX["DB transaction: order + outbox"]
    TX --> PUB["Outbox publisher"]
    PUB --> BROKER[("Broker test topic / queue")]
    BROKER --> CONS["Consumer idempotent"]
    CONS --> REDIS[("Redis test key")]
    TEST["JUnit assertions"] -.-> TX
    TEST -.-> BROKER
    TEST -.-> REDIS
    TEST --> DRAIN["Await completion / stop test work"]
    DRAIN --> CLEAN["Cleanup by testRunId"]
    CLEAN --> TX
    CLEAN --> REDIS
    CLEAN --> BROKER
~~~

**Thiết kế test:**

1. **Setup:** tạo customer và testRunId riêng; khởi động PostgreSQL, Redis và broker bằng container test (hoặc môi trường cô lập tương đương); cấu hình endpoint/credentials bằng property test.
2. **Action:** gửi HTTP POST với **idempotency key** và **externalOrderId** riêng.
3. **Assert đồng bộ:** HTTP status theo contract, row order và outbox được commit; không dựa vào @Transactional trên test để hoàn tác HTTP thật.
4. **Assert bất đồng bộ:** chờ event được consumer xử lý trong timeout; kiểm tra event ID, số tác động nghiệp vụ, cache key/value, trạng thái outbox và DLQ.
5. **Kiểm tra lặp:** gửi lại cùng idempotency key để chứng minh không tạo đơn mới hay phát sự kiện trùng ngoài hợp đồng.
6. **Teardown:** ngừng producer/consumer thử nghiệm nếu cần, đợi tác vụ hoàn tất, xóa Redis key và DB rows theo business key, hủy topic/queue riêng hoặc để container test chuyên dụng bị huỷ.
7. **Kiểm chứng sau cleanup:** không còn resource sở hữu bởi test; nếu còn, ghi lỗi với ID để điều tra.

**Bẫy thực tế:** nếu cleanup xóa outbox ngay sau HTTP 201 nhưng trước khi publisher đọc nó, test có thể pass phần HTTP và fail phần message; hoặc publisher vẫn xử lý sau cleanup, tạo message/Redis key mới. Thứ tự **await completion → verify → cleanup** là một phần của tính đúng.

## 19. Checklist trước khi đưa integration test vào CI

- [ ] Mỗi test công bố rõ dữ liệu đầu vào, trạng thái mong đợi và tài nguyên có side effect.
- [ ] Fixture có khóa riêng, hợp đồng schema/FK và khả năng tái lập.
- [ ] Chọn rollback, targeted cleanup, reset schema hoặc container đúng với phạm vi tài nguyên.
- [ ] Không giả định @Transactional ở test rollback request HTTP, async listener hoặc Redis/broker.
- [ ] @Sql setup/cleanup có transaction mode và thứ tự FK phù hợp.
- [ ] Testcontainers/connection properties có vòng đời khớp với ApplicationContext và không phụ thuộc port cố định.
- [ ] Redis keys, broker groups/topics/queues, file prefix và mock server được quản lý theo owner.
- [ ] Không sử dụng FLUSHALL, TRUNCATE CASCADE hay xóa wildcard trên resource dùng chung.
- [ ] Consumer/poller/scheduler được drain hoặc stop trước khi cleanup để tránh ghi muộn.
- [ ] Test có idempotency key và kiểm tra được việc nhận lại HTTP/message khi cần.
- [ ] Test bất đồng bộ có await với deadline, không dựa vào sleep cố định.
- [ ] Cleanup failure khiến test thất bại và có log chẩn đoán tài nguyên còn sót.
- [ ] Test chạy được độc lập, lặp lại, đổi thứ tự và song song trong phạm vi cho phép.
- [ ] Dữ liệu thử nghiệm là synthetic, không chứa bí mật production hoặc endpoint nguy hiểm.

**Điểm cần nhớ:** kiểm thử tích hợp chỉ đáng tin khi **trạng thái trước test được kiểm soát**, **tác động của luồng tích hợp được xác nhận**, và **tài nguyên sau test không làm sai lệch lần chạy tiếp theo**. Trong Spring Boot, transaction, cache, broker, file và các adapter có ranh giới riêng; chiến lược cleanup phải phản ánh những ranh giới ấy để kết quả test có thể tái lập và đáng tin cậy.
