# Test duplicate và idempotency trong Spring Kafka

## 1. Mục tiêu của bài kiểm thử tin cậy

Trong hệ thống dùng **Spring Kafka**, cùng một sự kiện nghiệp vụ có thể được consumer nhận **nhiều lần**. Nguyên nhân không nhất thiết là lỗi của Kafka: retry producer, retry consumer, rebalance, process crash hoặc replay từ dead-letter topic đều có thể khiến một tác động nghiệp vụ được thử lại.

Ví dụ consumer xử lý sự kiện **CreditEvent** để cộng tiền vào tài khoản:

~~~text
Sự kiện: eventId=credit-20261115-001
Tài khoản: ACC-001
Số tiền: +125.00

Kafka delivery lần 1  -> Consumer -> balance +125.00
Kafka delivery lần 2  -> Consumer -> balance +125.00  (SAI nếu cộng lại)
~~~

Nếu không có cơ chế chống trùng, sau hai lần nhận số dư tăng **250.00** thay vì **125.00**.

**Idempotency** nghĩa là thực hiện lại cùng một thao tác với cùng identity có **kết quả nghiệp vụ giống như thực hiện một lần**. Trong bài này, điều cần kiểm chứng không phải Kafka chỉ phát một record, mà là:

> Dù cùng một sự kiện được giao tới consumer nhiều lần, tác động cộng số dư chỉ được áp dụng một lần cho đúng phạm vi nghiệp vụ.

Bài thực hành hướng tới:

- Hiểu **duplicate delivery** khác **duplicate business event** như thế nào.
- Thiết kế **eventId ổn định**, bảng deduplication và transaction tại database.
- Viết test xác nhận nhận cùng event nhiều lần nhưng side effect chỉ xảy ra một lần.
- Kiểm tra lỗi giữa database commit và Kafka offset commit, retry và restart.
- Kiểm tra race condition khi hai consumer/worker xử lý duplicate đồng thời.
- Kiểm tra replay từ DLT, payload conflict, lỗi giữa transaction và thông điệp khác eventId.
- Sử dụng **PostgreSQL Testcontainers**, **Embedded Kafka** hoặc Kafka Testcontainers để có bài test đáng tin cậy.
- Tránh những assertion dễ gây false positive trong test bất đồng bộ.

Ví dụ áp dụng cho **Java 17, Spring Boot 3.x, Spring Kafka 3.x, Spring JDBC và PostgreSQL**. Phần mã có thể được tổ chức thành ứng dụng thực tế; các đoạn test sẽ nêu rõ tiền đề schema, fixture và cấu hình cần chuẩn bị.

## 2. Vì sao Kafka consumer có thể thấy duplicate?

Một Kafka record có **topic, partition, offset** riêng. Khi consumer thuộc một consumer group xử lý xong, nó cần commit offset tương ứng để Kafka biết tiến độ của group. **Tác động lên database** và **commit consumer offset** thường là hai thao tác độc lập.

~~~text
Topic credit-events / partition 0 / offset 115
              |
              v
        Kafka consumer
              |
              v
      Ghi vào database
              |
              v
      Commit Kafka offset
~~~

Giả sử:

1. Consumer nhận record ở offset 115.
2. Consumer ghi số dư thành công và database transaction commit.
3. JVM crash **trước khi** commit Kafka offset.
4. Sau restart, consumer group đọc lại offset 115.
5. Consumer cố áp dụng cùng nghiệp vụ lần nữa.

Kafka đã làm đúng cơ chế redelivery để tránh mất xử lý; nếu không có idempotency ở ứng dụng, số dư tăng hai lần.

Các tình huống khác:

| Nguồn duplicate | Điều gì xảy ra? | Có cùng Kafka offset? |
| --- | --- | --- |
| Crash sau DB commit, trước offset commit | Consumer đọc lại record cũ | Thường cùng offset |
| Consumer retry bằng error handler/seek | Record được xử lý lại | Có thể cùng offset |
| Consumer rebalance trước commit offset | Member khác nhận record chưa checkpoint | Có thể cùng offset |
| Producer hoặc upstream gửi lại business event | Có hai record mang cùng eventId | Thường offset khác nhau |
| DLT replay/re-drive | Event được xuất bản lại từ dead-letter topic | Topic/offset mới |
| Client gửi lại yêu cầu tạo event | Nhiều business messages cùng operation ID | Có thể khác topic/partition/offset |
| Operator reset offset để backfill | Consumer đọc lại lịch sử | Cùng topic/partition/offset cũ |

Do đó **topic + partition + offset** không phải luôn là khóa dedupe nghiệp vụ phù hợp. Hai Kafka records khác offset vẫn có thể mô tả **cùng giao dịch**.

### At-least-once và exactly-once

Với một quy trình thông thường, Kafka consumer được thiết kế theo **at-least-once**: record có thể xử lý lại nếu tiến độ offset chưa được xác nhận.

Kafka producer có tính năng **idempotent producer** giúp tránh một số duplicate do retry ở producer đối với log Kafka trong phạm vi cơ chế Kafka hỗ trợ. Kafka transactions/exactly-once semantics cũng hỗ trợ các pipeline Kafka-to-Kafka theo cách cấu hình phù hợp.

Tuy nhiên, **không được suy ra transaction Kafka bảo đảm exactly-once cho mọi side effect ở PostgreSQL, HTTP API hoặc email**. Nếu database và Kafka không tham gia một transaction nguyên tử chung, vẫn có cửa sổ failure khiến record được giao lại sau khi side effect đã commit.

Bảo đảm hiệu quả trong bài này là **at-least-once delivery + idempotent business processing**, chứ không phải cam kết mọi record chỉ được consumer nhìn thấy đúng một lần.

## 3. Xác định identity đúng để kiểm tra duplicate

Một event minh họa:

~~~java
import java.math.BigDecimal;

public record CreditEvent(
        String eventId,
        String accountId,
        BigDecimal amount) {
}
~~~

Ví dụ JSON:

~~~json
{
  "eventId": "credit-20261115-001",
  "accountId": "ACC-001",
  "amount": 125.00
}
~~~

**eventId** phải là định danh ổn định cho **một thao tác cộng tiền nghiệp vụ**. Khi producer retry hoặc re-publish cùng sự kiện, phải giữ **eventId cũ**, không sinh UUID khác cho mỗi lần gửi.

Một số giá trị không nên dùng làm deduplication key mặc định:

| Giá trị | Vấn đề |
| --- | --- |
| Kafka offset | Duplicate được publish lại sẽ có offset mới |
| Kafka partition | Nhiều event khác nhau cùng partition |
| Consumer instance ID | Thay đổi khi rebalance/restart |
| Thời điểm consumer nhận | Mỗi lần redelivery có thời điểm khác |
| UUID sinh trong consumer | Mỗi lần nhận có UUID khác, mất khả năng dedupe |
| Hash payload duy nhất | Hai giao dịch hợp lệ có thể có payload giống hệt |
| accountId duy nhất | Một tài khoản nhận nhiều khoản tiền hợp lệ |

**eventId** phù hợp nếu domain đảm bảo một eventId đại diện đúng một thao tác. Nếu một upstream có thể sinh hai eventId cho cùng yêu cầu chuyển tiền, cần một **operationId/paymentId** ổn định hơn từ nguồn nghiệp vụ, hoặc kết hợp unique constraint ở domain table.

Với multi-tenant, scope có thể là **tenantId + operationId** thay vì eventId toàn cục. Quy tắc uniqueness phải được xác định theo domain.

### Duplicate cùng ID nhưng payload khác

Giả sử nhận:

~~~text
Event A: eventId=credit-001, accountId=ACC-001, amount=125.00
Event B: eventId=credit-001, accountId=ACC-001, amount=999.00
~~~

Không nên âm thầm bỏ qua B như một duplicate hợp lệ. Đây có thể là **vi phạm identity contract**, bug upstream hoặc tình huống cần điều tra. Một cơ chế tốt lưu đủ thông tin để phát hiện **cùng eventId nhưng payload nghiệp vụ khác**.

## 4. Các điều kiện cần xác minh trong test

Với một event hợp lệ **E**:

**Idempotency cơ bản**

~~~text
apply(E)
apply(E)

Final balance = Initial balance + E.amount
processed event count for E = 1
~~~

**Hai event hợp lệ khác nhau**

~~~text
apply(E1)
apply(E2)   // E1.eventId != E2.eventId

Final balance = Initial + E1.amount + E2.amount
~~~

**Failure trước database commit**

~~~text
apply(E) -> database error -> rollback
retry apply(E) -> success

Final balance = Initial + E.amount
processed event count for E = 1
~~~

**Failure sau database commit nhưng trước offset commit**

~~~text
DB commit for E succeeds
Consumer crashes before Kafka offset commit
Kafka redelivers E
apply(E) detects existing marker and does not reapply

Final balance = Initial + E.amount
~~~

**Payload conflict**

~~~text
apply(E1: eventId=X, amount=125)
apply(E2: eventId=X, amount=999)

Second operation must not silently change balance.
Conflict must be surfaced and investigated.
~~~

**Concurrent duplicate**

~~~text
Worker A -> apply(E)
Worker B -> apply(E) at nearly the same time

Exactly one committed application to balance.
~~~

Những trường hợp này nên là một bộ test riêng, không chỉ một test gửi hai message rồi chờ vài giây.

## 5. Tại sao dùng dedupe trong RAM là chưa đủ?

Một cách viết dễ mắc lỗi:

~~~java
private final Set<String> seenEventIds =
        ConcurrentHashMap.newKeySet();

public void handle(CreditEvent event) {
    if (!seenEventIds.add(event.eventId())) {
        return;
    }

    updateBalance(event);
}
~~~

Nó có ba vấn đề cơ bản:

1. **Process restart làm mất Set**, nên redelivery sau crash có thể cộng tiền lần nữa.
2. **Hai consumer instance** không chia sẻ cùng Set, nên mỗi instance có thể áp dụng cùng event.
3. Nếu **seenEventIds.add** thành công nhưng **updateBalance** thất bại, event bị đánh dấu đã xử lý trong RAM dù nghiệp vụ chưa thành công.

Ngay cả khi dùng Redis để lưu dedupe key, nếu ghi marker và ghi database ở hai hệ thống không có transaction chung, vẫn tồn tại cửa sổ lỗi. Redis/cache có thể hữu ích như tầng giảm tải, nhưng với tác động tài chính, nguồn quyết định thường cần một **unique constraint bền vững** gắn transaction với business update.

## 6. Thiết kế bảng deduplication trong PostgreSQL

Ta dùng hai bảng:

~~~sql
CREATE TABLE account_balance (
    account_id VARCHAR(80) PRIMARY KEY,
    balance NUMERIC(18, 2) NOT NULL
);

CREATE TABLE processed_event (
    consumer_scope VARCHAR(80) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    account_id VARCHAR(80) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_scope, event_id)
);
~~~

Ý nghĩa:

- **account_balance** lưu tác động nghiệp vụ đã được commit.
- **processed_event** lưu một marker cho event đã được áp dụng.
- **PRIMARY KEY (consumer_scope, event_id)** bảo đảm chỉ một transaction có thể chèn marker cho cùng identity đã chọn.
- **account_id** và **amount** lưu dấu vết giúp phát hiện trường hợp eventId bị dùng lại cho payload khác.
- **consumer_scope** là danh tính **logic ổn định** của loại xử lý, không phải pod ID. Nếu nhiều consumer business khác nhau cần xử lý cùng event, chúng có thể dùng scope khác nhau.

Ví dụ, scope **credit-ledger-v1** xác định một phép cộng tiền của service ledger. Không nên đổi scope tùy tiện sau mỗi deploy, bởi đổi scope có thể khiến các message cũ không còn được phát hiện là duplicate.

### Dedupe marker và tác động nghiệp vụ phải chung transaction

Cả hai thao tác sau phải cùng database transaction:

~~~text
BEGIN TRANSACTION
    INSERT processed_event marker
    UPDATE account_balance
COMMIT TRANSACTION
~~~

Nếu update balance thất bại, transaction phải **rollback cả marker**. Nếu không, lần retry sẽ thấy marker tồn tại và bỏ qua một thao tác chưa bao giờ thành công.

Một anti-pattern:

~~~text
1. INSERT marker -> COMMIT
2. UPDATE balance -> ERROR

Retry thấy marker, skip.
Số dư không được cập nhật.           (MẤT XỬ LÝ)
~~~

Ngược lại, cập nhật balance rồi commit trước khi lưu marker cũng có rủi ro: crash giữa hai transaction khiến retry cộng thêm lần nữa.

## 7. Implement CreditService idempotent bằng Spring JDBC

Ví dụ dùng **JdbcTemplate** và **@Transactional** với một transaction manager thực sự điều khiển cả hai bảng PostgreSQL.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CreditService {

    private static final String SCOPE = "credit-ledger-v1";

    private final JdbcTemplate jdbc;

    public CreditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(CreditEvent event) {
        validate(event);

        int inserted = jdbc.update("""
            INSERT INTO processed_event (
                consumer_scope, event_id, account_id, amount
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT (consumer_scope, event_id) DO NOTHING
            """,
            SCOPE,
            event.eventId(),
            event.accountId(),
            event.amount());

        if (inserted == 0) {
            // Marker đã tồn tại. Xác minh payload nghiệp vụ không đổi.
            EventFingerprint original = jdbc.queryForObject("""
                SELECT account_id, amount
                FROM processed_event
                WHERE consumer_scope = ? AND event_id = ?
                """,
                (rs, rowNum) -> new EventFingerprint(
                        rs.getString("account_id"),
                        rs.getBigDecimal("amount")),
                SCOPE,
                event.eventId());

            if (original == null
                    || !original.accountId().equals(event.accountId())
                    || original.amount().compareTo(event.amount()) != 0) {

                throw new IllegalStateException(
                        "Conflicting payload for eventId="
                        + event.eventId());
            }

            // Duplicate hợp lệ: không cập nhật số dư lần nữa.
            return;
        }

        int updated = jdbc.update("""
            UPDATE account_balance
            SET balance = balance + ?
            WHERE account_id = ?
            """,
            event.amount(),
            event.accountId());

        if (updated != 1) {
            // RuntimeException làm transaction rollback cả marker.
            throw new IllegalStateException(
                    "Account not found for eventId="
                    + event.eventId());
        }
    }

    private static void validate(CreditEvent event) {
        Objects.requireNonNull(event, "event");

        if (event.eventId() == null
                || event.eventId().isBlank()
                || event.accountId() == null
                || event.accountId().isBlank()
                || event.amount() == null
                || event.amount().signum() <= 0) {

            throw new IllegalArgumentException(
                    "Invalid CreditEvent");
        }
    }

    private record EventFingerprint(
            String accountId,
            BigDecimal amount) {
    }
}
~~~

Trong thực tế nên bổ sung giới hạn độ dài, authorization/scope tenant, kiểm tra overflow hoặc decimal precision, kiểm soát amount theo currency và quy tắc rate limiting. Ví dụ chỉ tập trung vào idempotency.

### Vì sao INSERT trước rồi UPDATE?

PostgreSQL **PRIMARY KEY** kết hợp **ON CONFLICT DO NOTHING** quyết định transaction nào được phép áp dụng tác động cho cùng eventId. Hai request đồng thời cùng chèn một key sẽ được database điều phối ở ràng buộc unique. Nếu transaction đầu rollback, transaction khác có thể tiếp tục chèn; nếu transaction đầu commit, transaction khác nhận kết quả conflict.

Khi **inserted = 1**, transaction hiện tại là bên được phép thực hiện update. Khi **inserted = 0**, event đã có marker và phải kiểm tra payload trước khi bỏ qua.

Với PostgreSQL mặc định **READ COMMITTED**, cách này có hành vi dễ hiểu cho duplicate concurrent. Khi dự án thay isolation level, dùng R2DBC/Reactive hoặc tách marker và balance ra các database khác nhau, cần đánh giá lại tính nguyên tử và các trường hợp race.

### Vì sao không chỉ dựa vào synchronized?

**synchronized** chỉ bảo vệ các thread trong cùng JVM trên cùng object. Kafka consumer có thể chạy ở nhiều pod hoặc nhiều process; khóa bền vững ở database là nơi tất cả instance cùng nhìn thấy.

### Tại sao dùng BigDecimal?

Tiền không nên cộng bằng float/double. **NUMERIC** ở PostgreSQL và **BigDecimal** ở Java cho phép xử lý số thập phân chính xác theo giới hạn kiểu dữ liệu và quy tắc nghiệp vụ.

## 8. Kafka listener: commit database trước khi hoàn tất xử lý record

Listener nhận JSON, chuyển thành CreditEvent rồi gọi service:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class CreditListener {

    private final ObjectMapper mapper;
    private final CreditService creditService;

    public CreditListener(
            ObjectMapper mapper,
            CreditService creditService) {

        this.mapper = mapper;
        this.creditService = creditService;
    }

    @KafkaListener(
            topics = "credit-events",
            groupId = "credit-ledger-v1")
    public void onMessage(ConsumerRecord<String, String> record)
            throws JsonProcessingException {

        CreditEvent event =
                mapper.readValue(record.value(), CreditEvent.class);

        // Gọi qua Spring-managed service bean, bảo đảm @Transactional
        // có hiệu lực. Khi phương thức trả về bình thường,
        // database transaction của service đã commit.
        creditService.apply(event);
    }
}
~~~

Cấu hình minh họa:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      properties:
        enable.idempotence: true
    listener:
      ack-mode: record
~~~

Với **AckMode.RECORD** và **enable-auto-commit=false**, listener container quản lý việc commit offset sau khi record được xử lý thành công theo cấu hình. Trường hợp **service.apply** trả về bình thường, database transaction đã hoàn tất trước khi listener trả về.

Tuy nhiên, **database commit và Kafka offset commit không phải một transaction nguyên tử**. Nếu JVM crash sau khi database commit nhưng trước offset commit, record có thể được giao lại. Bảng **processed_event** là phần giúp replay không cộng tiền lần hai.

**Không commit/ack offset trước khi tác động nghiệp vụ đã được xác nhận**. Nếu ack trước, sau đó database update thất bại, Kafka có thể xem record đã xử lý và bỏ qua lần retry, gây mất tác động.

### Cần phân biệt lỗi dữ liệu và lỗi tạm thời

- **Database timeout/deadlock:** thường cần retry có backoff phù hợp.
- **Account không tồn tại:** cần policy domain; không tự coi là duplicate.
- **JSON không parse được:** không thể đi vào service, cần recoverer/DLT hoặc workflow xử lý lỗi phù hợp.
- **Cùng eventId nhưng amount khác:** đây là **payload conflict**, cần cảnh báo hoặc cách ly; không tự cộng thêm và cũng không coi là thành công hợp lệ.
- **Duplicate cùng eventId và payload:** service trả về bình thường, container có thể tiếp tục commit tiến độ.

## 9. Ranh giới failure và hành vi kỳ vọng

Tạo một bảng failure window trước khi viết test:

| Thời điểm xảy ra lỗi | Trạng thái DB | Trạng thái offset | Khi replay |
| --- | --- | --- | --- |
| Trước INSERT marker | Chưa thay đổi | Chưa commit | Xử lý lần đầu |
| Sau INSERT nhưng trước UPDATE, transaction rollback | Marker và balance đều rollback | Chưa commit | Xử lý lần đầu |
| Sau UPDATE, trước DB commit, transaction rollback | Marker và balance đều rollback | Chưa commit | Xử lý lần đầu |
| Sau DB commit, trước offset commit | Marker và balance đã commit | Chưa commit | Thấy duplicate, không cộng nữa |
| Sau offset commit | Marker và balance đã commit | Đã commit | Thông thường không replay tự động |
| Offset commit trước DB commit | Có thể chưa có tác động | Đã commit | Có nguy cơ mất xử lý; cần tránh thiết kế này |

**At-least-once + idempotency** chủ yếu bảo vệ cửa sổ **DB đã commit nhưng offset chưa commit**. Cơ chế này không thay thế kiểm thử việc transaction DB thực sự rollback khi business operation bị lỗi.

Đặc biệt với event có tác dụng bên ngoài database (email, HTTP, chuyển khoản sang hệ thống khác), một transaction JDBC không tự rollback các tác dụng đó. Phải dùng idempotency key ở hệ thống nhận, outbox hoặc state machine phù hợp.

## 10. Xây test pyramid: kiểm tra ở tầng nào?

Bộ test tin cậy không chỉ có một kiểu test:

| Tầng | Thành phần thật | Điều kiểm chứng |
| --- | --- | --- |
| **Unit test** | Logic thuần, fake repository nếu phù hợp | Quyết định xử lý duplicate/conflict |
| **Database integration test** | PostgreSQL thật hoặc Testcontainers | Unique constraint, transaction rollback, concurrent insert |
| **Kafka integration test** | Broker test + database | Hai Kafka records cùng eventId, offset và listener |
| **Failure/recovery test** | Kafka, database, process restart | Replay sau crash, rebalance, offset chưa commit |
| **DLT/re-drive test** | Error handler, DLT, replay workflow | Xử lý lại record đã thành công hoặc đã bị cách ly |
| **Load/soak test** | Môi trường tương đương production | Race, lag, chi phí lưu marker và retention |

**Mock KafkaTemplate không chứng minh broker đã lưu hai records**. **Mock repository không chứng minh PostgreSQL unique constraint giữ được khi hai transaction chạy đồng thời**. Với idempotency, hai tầng quan trọng nhất thường là **database integration** và **Kafka integration**.

## 11. Test tích hợp service bằng PostgreSQL Testcontainers

Test trực tiếp CreditService giúp phân biệt lỗi logic idempotency với các vấn đề Kafka listener, offset hoặc serializer.

Một skeleton Spring Boot Test:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class CreditServiceIntegrationTest {

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
    JdbcTemplate jdbc;

    @Autowired
    CreditService creditService;

    @Test
    void applyingSameEventTwiceChangesBalanceOnce() {
        String accountId = "acc-" + UUID.randomUUID();
        String eventId = "evt-" + UUID.randomUUID();

        jdbc.update(
                "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
                accountId,
                new BigDecimal("100.00"));

        CreditEvent event = new CreditEvent(
                eventId,
                accountId,
                new BigDecimal("25.00"));

        creditService.apply(event);
        creditService.apply(event);

        BigDecimal balance = jdbc.queryForObject(
                "SELECT balance FROM account_balance WHERE account_id = ?",
                BigDecimal.class,
                accountId);

        Integer markers = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM processed_event
                WHERE consumer_scope = ? AND event_id = ?
                """,
                Integer.class,
                "credit-ledger-v1",
                eventId);

        assertThat(balance)
                .isEqualByComparingTo("125.00");
        assertThat(markers).isEqualTo(1);
    }
}
~~~

**Điều kiện để chạy:** database test phải được tạo hai bảng theo schema ở phần 6, chẳng hạn bằng Flyway, Liquibase hoặc migration fixture. Các phụ thuộc Spring Boot Test, Testcontainers PostgreSQL/JUnit Jupiter và PostgreSQL JDBC driver phải có trong dự án.

Nên dùng **eventId/accountId ngẫu nhiên cho mỗi test** để tránh trùng fixture. Không phải xóa toàn bộ bảng dùng chung khi các test đang chạy song song; việc dọn toàn bộ có thể ảnh hưởng những test khác.

### Vì sao không đặt @Transactional trên chính test rồi coi kết quả là chắc chắn?

Nếu test method có @Transactional mặc định rollback khi kết thúc, nó có thể che giấu việc commit thực tế của service hoặc tạo transaction khác với đường chạy consumer ngoài production. Cần thiết kế test đọc state **đã được commit**, và khi kiểm tra nhiều giao dịch hoặc concurrent requests, tránh một test-wide transaction làm sai ranh giới.

## 12. Test hai eventId khác nhau có được áp dụng hai lần?

Idempotency không được nhầm **hai event hợp lệ có cùng amount/account** thành một duplicate.

~~~java
@Test
void differentEventIdsApplyIndependently() {
    String accountId = "acc-" + UUID.randomUUID();

    jdbc.update(
            "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
            accountId,
            new BigDecimal("100.00"));

    CreditEvent first = new CreditEvent(
            "evt-" + UUID.randomUUID(),
            accountId,
            new BigDecimal("25.00"));

    CreditEvent second = new CreditEvent(
            "evt-" + UUID.randomUUID(),
            accountId,
            new BigDecimal("25.00"));

    creditService.apply(first);
    creditService.apply(second);

    BigDecimal balance = jdbc.queryForObject(
            "SELECT balance FROM account_balance WHERE account_id = ?",
            BigDecimal.class,
            accountId);

    assertThat(balance).isEqualByComparingTo("150.00");
}
~~~

Nếu một hệ thống chỉ dùng **accountId + amount** hoặc hash của payload làm dedupe key, test này có thể thất bại vì hai giao dịch thực bị xem là một. Test cần xác minh **không bỏ nhầm event hợp lệ**.

Trong domain thanh toán, nên làm rõ thêm nếu hai eventId khác nhau nhưng cùng paymentId có phải hai event hợp lệ hay là duplicate upstream. Nếu chúng chỉ là hai bản phát cùng một payment, dedupe phải dựa vào **paymentId/operationId**, không chỉ eventId kỹ thuật.

## 13. Test rollback: marker không được sống sót khi business update thất bại

Một ca lỗi nguy hiểm là ghi marker trước khi update số dư, nhưng tài khoản đích không tồn tại.

~~~java
@Test
void rollsBackMarkerWhenBalanceUpdateFails() {
    String eventId = "evt-" + UUID.randomUUID();
    String missingAccount = "missing-" + UUID.randomUUID();

    CreditEvent event = new CreditEvent(
            eventId,
            missingAccount,
            new BigDecimal("25.00"));

    assertThatThrownBy(() -> creditService.apply(event))
            .isInstanceOf(IllegalStateException.class);

    Integer markerCount = jdbc.queryForObject("""
            SELECT COUNT(*)
            FROM processed_event
            WHERE consumer_scope = ? AND event_id = ?
            """,
            Integer.class,
            "credit-ledger-v1",
            eventId);

    assertThat(markerCount).isZero();

    // Sửa điều kiện hạ tầng/nghiệp vụ rồi retry.
    jdbc.update(
            "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
            missingAccount,
            new BigDecimal("100.00"));

    creditService.apply(event);

    BigDecimal balance = jdbc.queryForObject(
            "SELECT balance FROM account_balance WHERE account_id = ?",
            BigDecimal.class,
            missingAccount);

    assertThat(balance).isEqualByComparingTo("125.00");
}
~~~

Test này chứng minh **marker và business update có chung transaction** trong cấu hình test. Nếu marker được lưu ở transaction riêng, markerCount có thể là 1 sau lỗi và lần retry bị bỏ qua, dẫn đến mất xử lý.

Với Spring, @Transactional có hiệu lực khi lời gọi đi qua **Spring proxy** và transaction manager phù hợp. Trong ví dụ CreditListener gọi một bean service khác nên không gặp self-invocation. Đừng mặc định một phương thức @Transactional gọi nội bộ từ cùng object sẽ được proxy intercept.

## 14. Test cùng eventId nhưng dữ liệu khác

Một idempotent consumer tốt cần phát hiện **ID collision có payload bất đồng**:

~~~java
@Test
void rejectsChangedPayloadWithSameEventId() {
    String accountId = "acc-" + UUID.randomUUID();
    String eventId = "evt-" + UUID.randomUUID();

    jdbc.update(
            "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
            accountId,
            new BigDecimal("100.00"));

    creditService.apply(new CreditEvent(
            eventId, accountId, new BigDecimal("25.00")));

    assertThatThrownBy(() -> creditService.apply(
            new CreditEvent(
                    eventId,
                    accountId,
                    new BigDecimal("999.00"))))
            .isInstanceOf(IllegalStateException.class);

    BigDecimal balance = jdbc.queryForObject(
            "SELECT balance FROM account_balance WHERE account_id = ?",
            BigDecimal.class,
            accountId);

    assertThat(balance).isEqualByComparingTo("125.00");
}
~~~

Khi consumer nhận conflict ở Kafka, cần chính sách phù hợp: đưa tới DLT/quarantine, báo động dữ liệu không nhất quán và không tự retry mãi nếu lỗi không thể tự khắc phục. **Không nuốt exception rồi chỉ log “duplicate ignored”** vì điều đó che giấu event có cùng ID nhưng dữ liệu khác.

Nếu payload có nhiều trường nghiệp vụ, có thể lưu **payload fingerprint/canonical hash** cùng marker, nhưng cần chuẩn hóa format/field và hiểu giới hạn collision. Tối thiểu phải so những trường quyết định side effect.

## 15. Test concurrent duplicate bằng hai thread

Một lỗi hay gặp của dedupe không có transaction là mô hình kiểm tra trước rồi mới ghi:

~~~text
Thread A: SELECT marker -> không có
Thread B: SELECT marker -> không có
Thread A: UPDATE balance
Thread B: UPDATE balance
Thread A: INSERT marker
Thread B: INSERT marker (lỗi unique)
~~~

Dù B bị lỗi unique ở bước cuối, số dư có thể đã bị cộng hai lần nếu update tách transaction. Vì vậy phải dùng **atomic marker claim + business update cùng transaction**.

Test có thể dùng CountDownLatch để hai thread cùng gọi service:

~~~java
@Test
void concurrentDuplicatesApplyOnlyOnce() throws Exception {
    String accountId = "acc-" + UUID.randomUUID();
    String eventId = "evt-" + UUID.randomUUID();

    jdbc.update(
            "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
            accountId,
            new BigDecimal("100.00"));

    CreditEvent event = new CreditEvent(
            eventId, accountId, new BigDecimal("25.00"));

    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch go = new CountDownLatch(1);

    try {
        Callable<Void> call = () -> {
            go.await();
            creditService.apply(event);
            return null;
        };

        Future<Void> first = pool.submit(call);
        Future<Void> second = pool.submit(call);

        go.countDown();

        first.get(15, TimeUnit.SECONDS);
        second.get(15, TimeUnit.SECONDS);

        BigDecimal balance = jdbc.queryForObject(
                "SELECT balance FROM account_balance WHERE account_id = ?",
                BigDecimal.class,
                accountId);

        Integer markers = jdbc.queryForObject("""
                SELECT COUNT(*) FROM processed_event
                WHERE consumer_scope = ? AND event_id = ?
                """,
                Integer.class,
                "credit-ledger-v1",
                eventId);

        assertThat(balance).isEqualByComparingTo("125.00");
        assertThat(markers).isEqualTo(1);
    } finally {
        pool.shutdownNow();
    }
}
~~~

Trong file test cần import các class **java.util.concurrent** và **UUID**. Đây là integration test trên PostgreSQL thực để unique constraint và transaction cạnh tranh được kiểm chứng.

**Không đặt @Transactional trên toàn test** theo cách làm hai worker chạy trong transaction riêng nhưng dữ liệu fixture chưa commit, vì worker có thể không thấy tài khoản vừa tạo. Hãy commit fixture trước khi hai thread bắt đầu.

Với một hệ thống nhiều JVM/pod, nên có thêm test ở môi trường tương đương production bằng hai consumer processes hoặc nhiều listener instances. Thread-level test không kiểm chứng toàn bộ hành vi rebalance và consumer group, nhưng đã kiểm tra được điểm cốt lõi ở database.

## 16. Embedded Kafka + PostgreSQL: test hai Kafka records cùng eventId

Test service ở các phần trước chứng minh database logic. Để kiểm tra **listener thực sự nhận duplicate từ Kafka**, có thể dùng **@EmbeddedKafka** cho broker và PostgreSQL Testcontainers cho DB.

Cấu hình tích hợp minh họa:

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.common.TopicPartition;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@Testcontainers
@EmbeddedKafka(
        partitions = 1,
        topics = "credit-events",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@SpringBootTest(properties = {
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.listener.ack-mode=record"
})
class CreditListenerKafkaIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void duplicateKafkaRecordsApplyCreditOnce() throws Exception {
        String accountId = "acc-" + UUID.randomUUID();
        String eventId = "evt-" + UUID.randomUUID();

        jdbc.update(
                "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
                accountId,
                new BigDecimal("100.00"));

        CreditEvent event = new CreditEvent(
                eventId, accountId, new BigDecimal("25.00"));

        String json = mapper.writeValueAsString(event);

        kafkaTemplate.send(
                "credit-events", accountId, json)
                .get(10, TimeUnit.SECONDS);

        long secondOffset = kafkaTemplate.send(
                "credit-events", accountId, json)
                .get(10, TimeUnit.SECONDS)
                .getRecordMetadata()
                .offset();

        // Không chỉ đợi số dư = 125: điều đó có thể đúng
        // ngay sau record 1, trước khi record 2 được xử lý.
        // Đợi consumer group commit vượt offset của record 2.
        TopicPartition partition =
                new TopicPartition("credit-events", 0);

        await().atMost(Duration.ofSeconds(30))
                .untilAsserted(() -> {
                    try (AdminClient admin = AdminClient.create(
                            Map.of(
                                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                                embeddedKafka.getBrokersAsString()))) {

                        var offsets = admin.listConsumerGroupOffsets(
                                "credit-ledger-v1")
                                .partitionsToOffsetAndMetadata()
                                .get(5, TimeUnit.SECONDS);

                        var committed = offsets.get(partition);
                        assertThat(committed).isNotNull();
                        assertThat(committed.offset())
                                .isGreaterThan(secondOffset);
                    }
                });

        BigDecimal balance = jdbc.queryForObject(
                "SELECT balance FROM account_balance WHERE account_id = ?",
                BigDecimal.class,
                accountId);

        Integer markers = jdbc.queryForObject("""
                SELECT COUNT(*) FROM processed_event
                WHERE consumer_scope = ? AND event_id = ?
                """,
                Integer.class,
                "credit-ledger-v1",
                eventId);

        assertThat(balance).isEqualByComparingTo("125.00");
        assertThat(markers).isEqualTo(1);
    }
}
~~~

Đây là bài test minh họa có các điều kiện triển khai:

1. Cần dependencies **spring-kafka-test**, **Testcontainers PostgreSQL/JUnit**, **Awaitility**, Jackson, PostgreSQL driver và Spring Boot Test.
2. Hai bảng phải được tạo qua migration/fixture trên database test.
3. Topic test có **một partition** để minh họa việc quan sát offset 0; với nhiều partition, phải dùng đúng partition do **RecordMetadata** của record thứ hai trả về.
4. Listener phải dùng đúng **groupId=credit-ledger-v1**, cùng topic và value deserializer String.
5. Test tránh dùng consumer group/topic có sẵn từ suite khác, vì offset đã commit có thể thuộc records cũ. Có thể cô lập context/broker/topic cho suite.
6. Nếu dự án đã cấu hình một KafkaListenerContainerFactory tùy biến với ack mode/error handler khác, test phải dùng cấu hình tương ứng với đường chạy thật.

### Vì sao đợi committed offset thay vì chỉ đợi balance?

Một assertion kiểu:

~~~java
await().untilAsserted(() ->
        assertThat(readBalance(accountId))
                .isEqualByComparingTo("125.00"));
~~~

có thể pass sau record thứ nhất. Record thứ hai có thể **chưa được consumer xử lý**; test kết thúc sớm và không chứng minh idempotency.

Khi đã thấy group offset commit **vượt offset của record thứ hai** trong trường hợp hai records cùng partition, ta biết consumer group đã tiến qua hai messages theo cơ chế cấu hình. Sau đó mới đọc state cuối ở database. Với error handler có thể recover/skip records, cũng cần kiểm tra dấu hiệu xử lý và recovery policy để tránh test pass do record bị bỏ qua mà không được áp dụng đúng logic.

Một lựa chọn khác là cài **test probe** tại điểm listener xử lý xong từng attempt, kết hợp CountDownLatch có key theo eventId. Probe chỉ nên dùng trong test hoặc observability có semantics rõ ràng, không lẫn với số event đã commit nghiệp vụ.

## 17. Test cửa sổ crash sau DB commit, trước offset commit

Đây là kịch bản quan trọng nhất đối với at-least-once processing.

### Mức 1: mô phỏng ranh giới dễ kiểm soát

Có thể tạo precondition bằng service trước khi gửi Kafka record:

~~~java
CreditEvent event = new CreditEvent(
        eventId, accountId, new BigDecimal("25.00"));

creditService.apply(event); // Giả lập DB đã commit trước crash.

// Sau đó publish cùng event vào Kafka như lần redelivery.
kafkaTemplate.send("credit-events", accountId, json);
~~~

Khi listener nhận message, nó phải thấy marker cũ và không cộng số dư lần nữa. Cần chờ listener thực sự xử lý xong record như phần 16 rồi assert balance và marker.

**Đây là mô phỏng trạng thái sau crash**, không phải test thực sự kill process. Nó chứng minh service an toàn khi database đã ghi nhận event trước một lần Kafka delivery bổ sung.

### Mức 2: fault injection trong listener

Có thể chèn một điểm lỗi **sau khi creditService.apply đã return**, nhưng trước khi listener trả về bình thường:

~~~java
public void onMessage(ConsumerRecord<String, String> record)
        throws Exception {

    CreditEvent event =
            mapper.readValue(record.value(), CreditEvent.class);

    creditService.apply(event); // DB transaction đã commit.

    if (faultInjector.failAfterDatabaseCommit(event.eventId())) {
        throw new SimulatedCrashGapException(
                "Injected after DB commit");
    }
}
~~~

Trong test, fault injector chỉ thất bại **một lần**, sau đó error handler phải giao lại record. Kiểm tra số lần listener được gọi, marker count = 1 và số dư chỉ tăng một lần.

Đây cũng là **mô phỏng**, không phải actual JVM crash; Spring Kafka error handler retry có thể có lifecycle khác process restart, nhưng tác động idempotency cần chứng minh là giống nhau.

### Mức 3: crash/restart thực

Với Testcontainers hoặc môi trường tích hợp:

1. Chạy consumer ở một process/container riêng.
2. Publish event.
3. Dùng hook có kiểm soát để tạm dừng sau khi DB commit.
4. Kill consumer process **trước khi Kafka offset commit**.
5. Restart consumer cùng groupId và repository DB.
6. Chờ record được giao lại và xử lý hoàn tất.
7. Xác minh số dư chỉ cộng một lần và marker tồn tại một lần.

Test phải có cơ chế đồng bộ xác nhận **DB đã commit và offset chưa commit**, không dựa vào Thread.sleep rồi kill ở thời điểm ngẫu nhiên. Đây là bài integration/failure test nặng, phù hợp chạy theo lịch hoặc môi trường CI chuyên biệt.

## 18. Test producer gửi hai record cùng eventId nhưng khác offset

Hai lần gọi **KafkaTemplate.send** với cùng payload có thể tạo hai records ở các offset khác nhau. Test ở phần 16 đã cố ý thực hiện điều này.

Đây là trường hợp khác **redelivery cùng offset**:

~~~text
Kafka partition 0:
  offset 100 -> eventId=credit-001
  offset 101 -> eventId=credit-001

Consumer nhận offset 100: áp dụng nghiệp vụ.
Consumer nhận offset 101: dedupe, không áp dụng.
~~~

Producer idempotence không nhất thiết ngăn hai lần gửi có chủ đích cùng business event, vì hai lệnh send có thể là hai bản ghi hợp lệ theo Kafka log. Business idempotency phải dựa vào **eventId hoặc operationId ổn định**.

Nên có test riêng cho cùng eventId được phát qua **hai lần producer publish**, không chỉ seek đọc lại một offset. Nếu hệ thống dùng nhiều topic biểu diễn cùng event, scope dedupe cũng cần được thống nhất theo contract nghiệp vụ.

## 19. Test retry, DefaultErrorHandler và DLT replay

Spring Kafka có cơ chế xử lý lỗi như **DefaultErrorHandler**, retry/backoff và **DeadLetterPublishingRecoverer**. Test idempotency cần tương thích với chính sách đó.

Một cấu hình minh họa:

~~~java
@Bean
DefaultErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> recovererTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(recovererTemplate);

    // Ví dụ tối đa ba lần thử lại theo backoff cấu hình.
    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 3L));

    // Những lỗi payload không thể tự sửa thường không nên
    // retry vô hạn. Cần có policy phân loại exception.
    return handler;
}
~~~

Ví dụ yêu cầu Spring Kafka, Apache Kafka client và các import phù hợp. **FixedBackOff(1_000L, 3L)** nghĩa là ba lần retry sau lần xử lý ban đầu theo backoff một giây, tùy lifecycle handler. Tên DLT mặc định và phân vùng đích của recoverer phụ thuộc cấu hình/topic; cần bảo đảm DLT topic tồn tại và partition tương ứng hợp lệ.

### Các trường hợp test

**Lỗi database tạm thời**

- Khi update bị timeout/deadlock, transaction rollback cả marker và business effect.
- DefaultErrorHandler retry record.
- Khi lỗi được gỡ, service áp dụng đúng một lần.
- Không tạo marker thành công nếu transaction chưa commit.

**Lỗi payload không hợp lệ**

- JSON không parse được hoặc thiếu eventId.
- Không gọi business service.
- Policy chuyển DLT/quarantine hoặc xử lý theo contract.
- Không được commit offset thành công âm thầm nếu record chưa được recover phù hợp.

**Payload conflict**

- EventId đã xử lý nhưng payload khác.
- Consumer báo conflict; policy đưa vào DLT/audit hoặc điều tra.
- Dữ liệu đã ghi lần đầu không đổi.

**Replay từ DLT**

- Nếu event chưa hề áp dụng, sau khi sửa lỗi nó có thể được xử lý một lần.
- Nếu event từng áp dụng rồi nhưng bị re-drive, marker khiến side effect không lặp.
- Re-drive cần giữ **eventId/operationId gốc**, không sinh eventId mới trừ khi nghiệp vụ xác định đó thật sự là thao tác mới.

**DLT là cơ chế giữ và xử lý message thất bại, không phải bằng chứng idempotency**. Nếu một record được publish lại từ DLT và có khóa mới do replay tool sinh ngẫu nhiên, các bảo vệ dựa vào eventId có thể bị vô hiệu.

## 20. Test khi offset bị reset, rebalance hoặc restart

Một consumer group có thể đọc lại nhiều record sau khi offset được reset hoặc thay đổi cấu hình/recovery. Mục tiêu là không lặp tác động nghiệp vụ.

Các kịch bản gợi ý:

| Kịch bản | Hành động test | Kỳ vọng |
| --- | --- | --- |
| Reset offset về bản ghi đã xử lý | Seek/reset consumer trong môi trường test | Balance không tăng lần nữa |
| Restart cùng consumer group | Dừng và chạy lại consumer | Marker vẫn có và output đúng |
| Rebalance giữa hai instance | Thêm/bớt consumer lúc đang xử lý | Không mất/trùng business effect |
| Replay trên topic mới | Re-publish cùng eventId vào replay topic có consumer cùng scope | Không áp dụng trùng |
| Group ID bị thay đổi | Consumer mới đọc lịch sử | Nếu cùng business scope, vẫn dedupe |
| Retention marker quá ngắn | Xóa marker rồi replay event cũ | Test phải phát hiện nguy cơ duplicate |

**GroupId và consumer_scope không nhất thiết là cùng một khái niệm.** Group ID điều khiển Kafka consumption; business consumer scope xác định side effect nào đã thực hiện. Nếu đổi groupId để reprocess mà vẫn cùng side effect, marker scope cần ổn định.

Không chỉnh consumer group offset trong production chỉ để chạy test. Dùng topic/group test được cô lập và kiểm soát thời điểm dừng consumer khi reset.

## 21. Test thứ tự và nghiệp vụ không giao hoán

Idempotency không tự giải quyết **out-of-order processing**.

Ví dụ hai sự kiện hợp lệ:

~~~text
E1: Set account status = ACTIVE, version 3
E2: Set account status = CLOSED, version 4

Consumer nhận E2 rồi E1.
Hai eventId khác nhau nên dedupe không ngăn E1 ghi đè E2.
~~~

Nếu nghiệp vụ yêu cầu trạng thái mới nhất theo version, cần thêm bảo vệ:

- Event có **aggregateId** và **sequence/version**.
- Cập nhật target với điều kiện version tăng.
- Quản lý thứ tự theo Kafka key và partition khi phù hợp.
- Thiết kế xử lý late event rõ ràng.

Với sự kiện cộng tiền, hai amount khác eventId có thể cộng theo thứ tự nào cũng cho cùng tổng trong điều kiện phù hợp. Nhưng với **set status, replace balance hoặc workflow state**, thứ tự và version thường quan trọng.

Bộ test tin cậy nên tách:

- **Duplicate test:** cùng logical operation không tạo tác động lặp.
- **Ordering/version test:** event mới không bị event cũ ghi đè.
- **Concurrency test:** hai worker cùng update aggregate giữ invariant.
- **Reconciliation test:** số liệu cuối đúng theo source of truth.

## 22. Marker retention: test replay ngoài cửa sổ lưu trữ

Bảng processed_event sẽ lớn theo thời gian. Nếu một sự kiện đã xử lý bị xóa marker sau 7 ngày nhưng được re-drive vào ngày thứ 30, consumer có thể coi đó là event mới.

~~~text
Ngày 1:  E1 áp dụng, lưu marker.
Ngày 7:  Cleanup xóa marker.
Ngày 30: DLT re-drive E1.
         Không còn marker -> cộng tiền lần 2.   (SAI)
~~~

Chính sách retention phải gắn với **thời hạn tối đa có thể replay** của Kafka topic, DLT, backup, quy trình backfill và yêu cầu nghiệp vụ. Một hệ thống có thể giữ marker lâu dài cho sự kiện tài chính, hoặc dùng một bảng domain mang unique business operation ID không phụ thuộc việc xóa marker kỹ thuật.

Test retention cần xác minh:

1. Marker chưa được purge khi còn trong cửa sổ replay.
2. Nếu marker bị archive, cơ chế dedupe vẫn nhận diện duplicate từ kho lâu dài hoặc unique business key.
3. Cleanup không xóa marker của transaction còn hoạt động.
4. Backfill lịch sử không vô tình coi toàn bộ event là mới.

Một cache Bloom filter hoặc TTL Redis có thể giảm số lần truy vấn DB, nhưng **không thay thế nguồn dedupe chính xác** khi yêu cầu không được áp dụng trùng.

## 23. Quan sát duplicate và retry trong production

Các metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| **kafka_consumer_record_attempts_total** | Số lần listener thử xử lý record |
| **business_event_applied_total** | Số event mới được áp dụng |
| **business_event_duplicate_total** | Số event trùng được nhận diện |
| **business_event_payload_conflict_total** | Số eventId bị dùng lại với payload khác |
| **business_event_processing_failure_total** | Số lần lỗi trước khi hoàn tất |
| **kafka_consumer_lag** | Tồn đọng consumption của group |
| **kafka_dlt_records_total** | Số record đưa vào DLT |
| **database_transaction_rollback_total** | Rollback liên quan xử lý |

Điểm quan trọng là định nghĩa rõ **attempt** và **applied**. Một record được retry 3 lần có thể tạo 3 attempts nhưng chỉ 1 business application. Nếu đưa số attempts vào chỉ số sản lượng nghiệp vụ, dashboard sẽ bị thổi phồng.

Không dùng **eventId**, accountId hay UUID làm tag metric thường trực vì chúng tạo cardinality rất lớn. Có thể log **eventId, topic, partition, offset, consumer scope** với cơ chế bảo vệ thông tin, rồi dùng correlation ID để điều tra.

Khi duplicate tăng, nên tìm nguyên nhân:

- Producer đang gửi lại event vì timeout?
- Consumer group rebalance quá nhiều?
- DB xử lý chậm khiến poll/commit offset bị trì hoãn?
- Error handler retry liên tục?
- Operator đang re-drive DLT?
- Một client đang gửi lại cùng yêu cầu nghiệp vụ?

**Một số duplicate là hành vi bình thường của kiến trúc at-least-once**, nhưng tỷ lệ tăng đột biến có thể cho thấy sự cố vận hành.

## 24. Checklist các trường hợp cần có trong bộ test

| # | Kịch bản | Kết quả tối thiểu cần assert |
| ---: | --- | --- |
| 1 | Cùng eventId, cùng payload, gọi service hai lần | Balance tăng một lần; marker = 1 |
| 2 | Hai eventId khác nhau, cùng account/amount | Balance tăng hai lần |
| 3 | Same eventId, amount khác | Conflict, không cập nhật lần hai |
| 4 | Same eventId, accountId khác | Conflict, không chuyển tiền sang account khác |
| 5 | Lỗi sau marker INSERT nhưng trước commit | Marker rollback; retry xử lý được |
| 6 | Hai thread áp dụng cùng event đồng thời | Một marker, một business effect |
| 7 | Hai Kafka records khác offset nhưng cùng eventId | Đợi cả hai được xử lý; balance tăng một lần |
| 8 | DB đã commit, offset chưa commit rồi redelivery | Không cộng lần hai |
| 9 | Consumer restart/rebalance và đọc lại | Dữ liệu cuối không trùng |
| 10 | DLT replay record đã từng áp dụng | Không lặp side effect |
| 11 | DLT replay event chưa áp dụng sau khi sửa lỗi | Áp dụng đúng một lần |
| 12 | JSON lỗi/thiếu eventId | Không tạo marker hoặc business effect |
| 13 | Event hợp lệ bị xử lý out-of-order | Không phá version/invariant nghiệp vụ |
| 14 | Hai instance/process tiêu thụ duplicate | Database unique constraint giữ đúng |
| 15 | Marker retention rồi replay lịch sử | Không làm mất bảo vệ idempotency |
| 16 | Lỗi hạ tầng Kafka hoặc DB | Không ack offset sớm trước business commit |

Với bài test dùng broker, cần quan sát **đã xử lý đủ records** trước khi assert dữ liệu cuối. Với bài test database, cần xác minh **transaction thật và unique constraints thật**, không chỉ mock method return.

## 25. Những lỗi kiểm thử rất thường gặp

### Chỉ gửi duplicate rồi chờ Thread.sleep

~~~java
kafkaTemplate.send(topic, key, payload);
kafkaTemplate.send(topic, key, payload);
Thread.sleep(2000L);

assertBalance(...);
~~~

Thời gian xử lý phụ thuộc CPU, broker, network, rebalance và CI. Sleep cố định có thể quá ngắn hoặc che giấu test chạy lâu. Dùng **Awaitility**, CountDownLatch hoặc kiểm tra committed offset/probe theo điều kiện quan sát được.

### Assert quá sớm sau record thứ nhất

Balance đã đúng sau một delivery, nhưng delivery thứ hai chưa chạy. Test pass giả. Cần đợi cả hai records được xử lý/commit theo đường test.

### Chỉ đếm marker mà không kiểm tra balance

Marker = 1 có thể vẫn đi cùng balance sai nếu marker commit độc lập với business effect. Phải assert **cả marker và side effect**.

### Chỉ kiểm tra balance mà không kiểm tra marker

Balance đúng tạm thời nhưng marker không được lưu có thể khiến lần restart tiếp theo cộng trùng. Cần assert marker bền vững.

### Dùng mock database để chứng minh concurrency

Mock không tái hiện unique constraint, lock và transaction PostgreSQL. Với race cần DB thật.

### Đặt test method @Transactional làm tất cả fixture chưa commit

Listener/worker trên thread khác không thấy fixture chưa commit, gây test flaky hoặc sai mô hình transaction. Commit fixture trước khi kích hoạt consumer.

### Tạo eventId ngẫu nhiên mỗi lần resend

Như vậy đó không còn cùng logical event. Duplicate test phải giữ **eventId cố định** giữa các lần gửi.

### Xóa marker giữa hai assertions

Test có thể vô tình dọn chính cơ chế dedupe. Cô lập bằng eventId/accountId riêng, không TRUNCATE bảng chung khi consumer vẫn xử lý.

### Chỉ test cùng một JVM

Một ConcurrentHashMap có thể “pass” trong JVM đơn nhưng fail khi chạy nhiều pod. Dùng unique constraint bền vững và test cross-instance theo mức độ quan trọng.

### Tin rằng producer idempotence đủ cho database

Producer idempotence và Kafka transactions không tự bảo đảm exactly-once cho tác động JDBC hay API ngoài. Test phải có tình huống DB commit trước Kafka offset.

## 26. Quy trình triển khai thực tế

Có thể áp dụng các bước sau cho một consumer mới:

**Bước 1 — Xác định logical operation.** Chốt eventId hoặc business operationId ổn định qua retry, re-publish và DLT replay.

**Bước 2 — Xác định side effect cần bảo vệ.** Ví dụ cộng số dư, tạo invoice, gửi email hay gọi API đối tác. Mỗi loại side effect có ranh giới transaction khác nhau.

**Bước 3 — Chọn nguồn dedupe bền vững.** Với side effect trong PostgreSQL, dùng unique constraint trên scope + event ID hoặc business key phù hợp.

**Bước 4 — Gắn marker và business effect trong cùng transaction.** Bất kỳ lỗi nào trước commit phải rollback cả hai.

**Bước 5 — Cho listener hoàn tất sau khi business commit.** Offset commit có thể xảy ra sau đó; chấp nhận khả năng replay và để service xử lý idempotent.

**Bước 6 — Viết test service trước.** Kiểm tra duplicate, hai event khác ID, payload conflict, rollback và concurrent inserts.

**Bước 7 — Viết test Kafka tích hợp.** Publish hai Kafka records cùng eventId, đợi cả hai được consumer group xử lý, assert marker và dữ liệu.

**Bước 8 — Kiểm tra failure window.** Mô phỏng DB commit trước offset, sau đó chạy thử crash/restart thực ở môi trường phù hợp.

**Bước 9 — Kiểm tra retry/DLT và retention.** Re-drive phải giữ original event ID, còn marker phải tồn tại đủ lâu để chống xử lý trùng.

**Bước 10 — Theo dõi production.** Ghi metrics attempts/applied/duplicates/conflicts, Kafka lag và DB rollback; điều tra khi duplicate rate tăng bất thường.

## 27. Kết luận

Một hệ thống Spring Kafka tin cậy **không nên dựa vào giả định rằng mỗi event chỉ đến consumer đúng một lần**. Với at-least-once delivery, retry hoặc crash sau DB commit trước offset commit là các tình huống phải được thiết kế ngay từ đầu.

Giải pháp của bài thực hành là dùng **eventId/operationId ổn định**, **unique constraint bền vững** và **transaction nguyên tử giữa marker dedupe với business update**. Khi cùng sự kiện được nhận lần hai, consumer xác nhận payload giống và bỏ qua side effect; khi hai event khác nhau, chúng vẫn được xử lý độc lập; khi transaction lỗi, cả marker lẫn tác động đều rollback để retry có thể tiếp tục.

Bộ test cần bao phủ **cùng event gửi hai lần, redelivery, payload conflict, rollback, race condition, DLT replay và restart**. Một test tốt không chỉ kiểm tra Kafka listener đã được gọi, mà phải xác nhận **đúng số lần tác động nghiệp vụ đã commit** và **không bỏ nhầm những event hợp lệ**. Đó là ý nghĩa thực tế của **test duplicate và idempotency** trong vận hành Spring Kafka.

