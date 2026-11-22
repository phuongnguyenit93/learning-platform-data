# Thiết kế bộ xử lý sự kiện có tính lặp an toàn trong Spring Data JPA

## 1. Vấn đề: một sự kiện có thể được giao nhiều lần

Trong hệ thống hướng sự kiện, broker, webhook hoặc tác vụ nền có thể giao lại cùng một sự kiện khi consumer mất kết nối, xử lý quá thời gian, khởi động lại hoặc đã `COMMIT` dữ liệu nhưng chưa kịp xác nhận (`ACK`) với nguồn phát. Vì vậy, một message được nhận hai lần không nhất thiết là hai hành động nghiệp vụ khác nhau.

Ví dụ: sự kiện `PointsEarned(eventId=E1, accountId=10, points=7)` yêu cầu cộng 7 điểm cho tài khoản. Nếu handler thực thi phép cộng hai lần, số điểm tăng 14 thay vì 7. Mục tiêu là: **cùng một sự kiện logic được xử lý lặp lại vẫn tạo ra một kết quả nghiệp vụ duy nhất**.

Tính lặp an toàn (*idempotency*) có thể diễn đạt bằng `apply(apply(state, E), E) = apply(state, E)`. Điều này **không có nghĩa** broker chỉ phát một lần; consumer vẫn có thể nhận nhiều bản sao, nhưng hiệu ứng đã cam kết trên cơ sở dữ liệu chỉ xuất hiện một lần cho mỗi khóa khử trùng lặp.

Cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| *At-least-once delivery* | Sự kiện có thể đến nhiều lần; không được giả định nhận đúng một lần. |
| *Deduplication* | Nhận ra rằng một `eventId` đã được consumer này xử lý. |
| *Idempotent effect* | Chạy lại cùng sự kiện không làm thay đổi kết quả đã cam kết. |
| *Exactly-once end-to-end* | Cam kết mạnh hơn, đòi hỏi xét toàn bộ hệ thống từ nguồn phát đến mọi hiệu ứng bên ngoài; một bảng dedup trong JPA không tự cung cấp bảo đảm này. |

## 2. Xác định ranh giới và khóa định danh

Trước khi viết code, trả lời bốn câu hỏi:

1. **Một sự kiện là gì?** Producer phải gán `eventId` ổn định khi tạo sự kiện logic. Mỗi lần giao lại/retry vẫn giữ nguyên ID; consumer không tạo UUID mới khi nhận.
2. **Ai thực hiện hiệu ứng?** Hai consumer nghiệp vụ độc lập có thể đều cần xử lý E1. Dùng khóa ghép `(consumer_name, event_id)`, thay vì chỉ `event_id` dùng chung toàn hệ thống.
3. **Hiệu ứng nào phải nguyên tử?** Bản ghi “đã xử lý” và thay đổi nghiệp vụ trong **cùng giao dịch database**. Nếu nghiệp vụ rollback, dấu đã xử lý cũng rollback.
4. **Khi nào xác nhận?** ACK/đánh dấu message thành công **sau khi giao dịch DB commit thành công**. Nếu handler ném lỗi, không ACK thành công; để cơ chế retry hoặc dead-letter xử lý theo chính sách.

Không sử dụng `existsBy...()` rồi `save()` như hai bước để bảo đảm duy nhất. Hai luồng đồng thời có thể cùng thấy “chưa tồn tại”. Cần **ràng buộc UNIQUE thật trong database** và thao tác nhận quyền xử lý nguyên tử. Cache/in-memory `Set` chỉ có thể là tối ưu phụ vì mất dữ liệu khi restart và không đồng bộ giữa nhiều instance.

Khóa nghiệp vụ và `eventId` cũng khác nhau: một đơn hàng có thể sinh nhiều sự kiện hợp lệ (đã tạo, đã thanh toán, đã hủy). Chỉ dùng `orderId` làm khóa dedup sẽ vô tình bỏ các sự kiện khác nhau. Ngược lại, nếu producer cấp ID mới cho cùng một giao dịch nghiệp vụ bị retry, chỉ dedup bằng `eventId` sẽ không phát hiện được trùng logic; khi cần, producer phải có ID giao dịch nghiệp vụ ổn định và quy tắc duy nhất tương ứng.

## 3. Luồng xử lý an toàn với một database

Với PostgreSQL và Spring Data JPA, một cách triển khai dễ kiểm chứng là:

1. Kiểm tra dữ liệu đầu vào, giữ nguyên `eventId`.
2. Bắt đầu giao dịch `@Transactional`.
3. Thử chèn dấu `(consumer_name, event_id)` bằng `INSERT ... ON CONFLICT DO NOTHING` dựa trên unique index.
4. Nếu số hàng chèn bằng `0`, đây là bản sao đã được một giao dịch khác cam kết: kết thúc không thay đổi nghiệp vụ.
5. Nếu số hàng chèn bằng `1`, cập nhật dữ liệu nghiệp vụ trong **giao dịch đó**.
6. Commit; chỉ sau khi method giao dịch trả về thành công mới ACK message.

Cạnh tranh cùng `eventId` được database phân xử thông qua unique constraint. Trên PostgreSQL, khi hai transaction thử chèn cùng khóa, transaction sau có thể phải đợi kết quả transaction trước: nếu transaction đầu commit, lần sau không chèn; nếu transaction đầu rollback, lần sau có thể chèn rồi thực hiện nghiệp vụ. Không cần dựa vào khóa Java trong một tiến trình.

| Điểm lỗi | Trạng thái và cách khôi phục |
| --- | --- |
| Lỗi trước khi chèn marker | Không có thay đổi; lần giao lại có thể thử tiếp. |
| Đã chèn marker nhưng cập nhật nghiệp vụ lỗi | Toàn bộ giao dịch rollback, gồm cả marker; retry không bị bỏ sót. |
| DB đã commit, ACK chưa gửi hoặc bị mất | Broker có thể giao lại; thao tác chèn trả `0` nên không cộng lần hai. |
| Hai bản sao đến đồng thời | Unique constraint bảo đảm tối đa một giao dịch giành quyền xử lý thành công cho khóa đó. |
| Sự kiện mới có ID khác | Được xử lý như một sự kiện mới; cần bảo vệ tính đồng thời của trạng thái nghiệp vụ. |

Điều kiện quan trọng: **marker và dữ liệu nghiệp vụ nằm trên cùng nguồn tài nguyên giao dịch**. Hai database riêng, API HTTP, email hoặc message gửi ra ngoài không tự rollback theo giao dịch JPA.

## 4. Ví dụ Spring Data JPA + PostgreSQL

Giả sử sự kiện `PointsEarned` cộng điểm cho một tài khoản. Dùng Java 17+, Spring Boot 3.x, `spring-boot-starter-data-jpa`, PostgreSQL JDBC driver và một migration SQL. Đoạn mã dưới đây là các file trong cùng package `com.example.events`; đây là phần xử lý nghiệp vụ, được ứng dụng Spring Boot và message adapter gọi, không phải một chương trình `javac` độc lập.

### 4.1. Schema có ràng buộc UNIQUE

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    points BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE processed_event (
    id BIGSERIAL PRIMARY KEY,
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_processed_event_consumer_event
        UNIQUE (consumer_name, event_id)
);

INSERT INTO accounts (id, points) VALUES (10, 100);
```

Quản lý DDL bằng Flyway hoặc Liquibase; trong môi trường triển khai, nên để Hibernate `ddl-auto=validate` thay vì tự ý cập nhật schema. Ràng buộc `UNIQUE` là lớp bảo đảm bắt buộc, kể cả khi ứng dụng chạy nhiều replica.

### 4.2. Entity và payload

File `Account.java`:

```java
package com.example.events;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    private Long id;

    @Column(nullable = false)
    private long points;

    protected Account() { }
}
```

File `ProcessedEvent.java`:

```java
package com.example.events;

import java.time.Instant;
import java.util.UUID;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "processed_event",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_processed_event_consumer_event",
        columnNames = {"consumer_name", "event_id"}
    )
)
public class ProcessedEvent {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "consumer_name", nullable = false, length = 100)
    private String consumerName;

    @Column(name = "event_id", nullable = false)
    private UUID eventId;

    @Column(name = "processed_at", nullable = false)
    private Instant processedAt;

    protected ProcessedEvent() { }
}
```

File `PointsEarnedEvent.java`:

```java
package com.example.events;

import java.util.UUID;

public record PointsEarnedEvent(
    UUID eventId,
    Long accountId,
    long points
) { }
```

`eventId` được tạo ở bên phát và không đổi giữa các lần phát lại. Giá trị `points` phải dương theo quy tắc của loại sự kiện này.

### 4.3. Repository: đăng ký xử lý và cập nhật nguyên tử

File `ProcessedEventRepository.java`:

```java
package com.example.events;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProcessedEventRepository
        extends JpaRepository<ProcessedEvent, Long> {

    @Modifying
    @Query(value = """
        INSERT INTO processed_event (consumer_name, event_id, processed_at)
        VALUES (:consumer, :eventId, CURRENT_TIMESTAMP)
        ON CONFLICT (consumer_name, event_id) DO NOTHING
        """, nativeQuery = true)
    int insertIfAbsent(
        @Param("consumer") String consumer,
        @Param("eventId") UUID eventId
    );
}
```

File `AccountRepository.java`:

```java
package com.example.events;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AccountRepository extends JpaRepository<Account, Long> {

    @Modifying
    @Query("""
        update Account a
           set a.points = a.points + :delta
         where a.id = :accountId
        """)
    int addPoints(
        @Param("accountId") Long accountId,
        @Param("delta") long delta
    );
}
```

`insertIfAbsent()` dựa trên cú pháp **PostgreSQL**, trả về `1` nếu chèn thành công và `0` nếu khóa đã tồn tại. Đối với DB khác, dùng cơ chế insert-if-absent/unique constraint tương đương và kiểm tra hành vi thật của driver.

`addPoints()` dùng một lệnh UPDATE dạng `points = points + delta` để các sự kiện **khác nhau** cùng cộng điểm không bị *lost update*. Đây là JPQL bulk update: nó bỏ qua trạng thái entity `Account` đang được quản lý trong persistence context; mẫu này không tải `Account` rồi sửa tiếp trong cùng transaction. Nếu nghiệp vụ cần invariant phức tạp hơn hoặc xử lý entity đã load, sử dụng khóa hàng hay `@Version` cùng chiến lược retry tương ứng.

### 4.4. Handler: marker và nghiệp vụ trong cùng transaction

File `PointsEarnedHandler.java`:

```java
package com.example.events;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PointsEarnedHandler {
    private static final String CONSUMER = "points-ledger";

    private final ProcessedEventRepository processedEvents;
    private final AccountRepository accounts;

    public PointsEarnedHandler(
            ProcessedEventRepository processedEvents,
            AccountRepository accounts) {
        this.processedEvents = processedEvents;
        this.accounts = accounts;
    }

    @Transactional
    public void handle(PointsEarnedEvent event) {
        if (event == null || event.eventId() == null
                || event.accountId() == null || event.points() <= 0) {
            throw new IllegalArgumentException("Invalid PointsEarnedEvent");
        }

        int inserted = processedEvents.insertIfAbsent(
                CONSUMER, event.eventId());

        if (inserted == 0) {
            return; // Bản sao đã được xử lý: không cộng điểm nữa.
        }
        if (inserted != 1) {
            throw new IllegalStateException("Unexpected insert count");
        }

        int updated = accounts.addPoints(
                event.accountId(), event.points());

        if (updated != 1) {
            // Lỗi unchecked làm rollback cả marker lẫn thay đổi nghiệp vụ.
            throw new IllegalStateException("Account not found");
        }
    }
}
```

`@Transactional` mặc định rollback khi có `RuntimeException` chưa bị nuốt. Method `handle` phải được gọi qua Spring proxy (ví dụ từ một listener bean khác); tự gọi `this.handle(...)` trong cùng class không kích hoạt transaction proxy. Trong mô hình này, mã chỉ trả về khi Spring đã hoàn tất commit hoặc báo lỗi. Không nuốt lỗi nghiệp vụ rồi vẫn trả thành công.

Phương thức repository `@Modifying` chạy trong transaction mà service mở. Nếu gọi trực tiếp repository không có transaction phù hợp, thao tác ghi sẽ thất bại hoặc không bảo đảm nguyên tử.

### 4.5. Kết nối với message adapter và thời điểm ACK

Một adapter (Kafka, RabbitMQ, webhook worker hoặc job polling) gọi `handler.handle(event)`. Với cơ chế ACK thủ công, trình tự là:

```java
// Pseudocode bên trong adapter, không phải class Spring Kafka hoàn chỉnh:
try {
    handler.handle(event);   // Transaction được commit trước khi trả về.
    acknowledgeMessage();    // Chỉ xác nhận sau khi handle thành công.
} catch (Exception ex) {
    triggerRetryOrDeadLetterAccordingToPolicy(ex);
}
```

Hàm `acknowledgeMessage` và `triggerRetryOrDeadLetterAccordingToPolicy` chỉ biểu diễn thao tác của adapter; phải ánh xạ vào API và cấu hình ACK/retry thực tế của broker. Không ACK ngay lúc nhận và không ACK trong một giao dịch DB chưa commit. Nếu listener có thể bị redeliver giữa commit và ACK, marker sẽ biến lần giao lại thành no-op.

## 5. Diễn giải kết quả trên ví dụ

Ban đầu `accounts.id=10` có `points=100`. Producer phát một sự kiện:

```text
eventId   = 00000000-0000-0000-0000-000000000357
accountId = 10
points    = 7
consumer  = points-ledger
```

- Lần 1: chèn marker thành công (`1`), UPDATE cộng 7, COMMIT. `points=107`; marker có một dòng.
- Lần 2 và lần 3 với **cùng `eventId`**: chèn trả `0`, handler thoát. `points` vẫn là `107`.
- Nếu account không tồn tại, `addPoints` trả `0` và ném lỗi; rollback xóa luôn marker vừa chèn. Sau khi sửa nguyên nhân, một lần giao lại có thể xử lý.
- Cùng ID nhưng `consumer_name` khác là một tiến trình nghiệp vụ độc lập; unique key cho phép nó thực hiện hiệu ứng riêng. Tên consumer phải **ổn định theo nghĩa nghiệp vụ**; đổi tên tùy tiện sau deploy có thể làm các event cũ được áp dụng lại.

Có thể xác minh bằng:

```sql
SELECT points FROM accounts WHERE id = 10;
-- Kỳ vọng sau ba lần nhận cùng event: 107

SELECT COUNT(*)
FROM processed_event
WHERE consumer_name = 'points-ledger'
  AND event_id = '00000000-0000-0000-0000-000000000357';
-- Kỳ vọng: 1
```

Các kết quả trên là kỳ vọng cho kịch bản đã mô tả, không phải output của một lần chạy thực tế.

## 6. Đồng thời, thứ tự sự kiện và lỗi thường gặp

**Trùng lặp cùng ID:** unique constraint bảo vệ cả khi có nhiều JVM/replica. Đừng dùng synchronized, khóa JVM hoặc cache làm nguồn bảo đảm duy nhất.

**Sự kiện khác ID nhưng cùng cập nhật một hàng:** dedup không tự ngăn lost update. Với phép cộng, UPDATE nguyên tử như trên phù hợp. Với thao tác đọc–kiểm tra–ghi (ví dụ trừ tiền nếu đủ số dư), cần ràng buộc DB, UPDATE có điều kiện, row lock (`PESSIMISTIC_WRITE`) hoặc optimistic locking (`@Version`), cộng retry cho xung đột thích hợp.

**Sự kiện đến sai thứ tự:** idempotency không tạo ra ordering. Nếu `OrderShipped` đến trước `OrderPaid`, phải có trạng thái hợp lệ, version/sequence hoặc quy tắc chuyển trạng thái; không được đồng nhất “chưa từng xử lý” với “được phép áp dụng”. Với projection có version, cân nhắc câu UPDATE có điều kiện như `WHERE last_version < :incomingVersion` và kiểm tra quy tắc domain.

**Cùng eventId nhưng payload khác:** mẫu đơn giản sẽ coi lần sau là bản sao. Trong hệ thống cần kiểm toán, lưu thêm `payload_hash`/`schema_version` và đối chiếu; cùng ID mà nội dung không khớp phải được phát hiện như lỗi hợp đồng producer, thay vì lặng lẽ chấp nhận.

**Giữ marker bao lâu?** Xóa quá sớm sẽ khiến event cũ từ DLQ, backup hoặc replay được xử lý lần nữa. Retention phải phủ toàn bộ cửa sổ redelivery/replay; thao tác tiền tệ có thể cần lịch sử bất biến hoặc khóa nghiệp vụ vĩnh viễn. Nếu partition/archiving, vẫn cần duy trì khả năng phát hiện trùng trên dữ liệu đã lưu trữ.

**Bắt lỗi unique trong transaction JPA:** mô hình `find → save` không đủ an toàn. Việc bắt `DataIntegrityViolationException` rồi tiếp tục trong cùng `@Transactional` có thể khiến transaction đã bị đánh dấu rollback-only hoặc connection đang ở trạng thái lỗi (đặc biệt PostgreSQL). `ON CONFLICT DO NOTHING` tránh dùng exception như nhánh xử lý trùng; nếu dùng phương án insert và bắt exception, xử lý exception ở **ranh giới transaction riêng** và phân biệt chính xác constraint gây lỗi.

**Retry và poison event:** lỗi tạm thời (deadlock, mất DB, timeout) nên retry với backoff/jitter và giới hạn số lần; lỗi dữ liệu không thể sửa nên chuyển DLQ/cảnh báo theo chính sách. Không đánh dấu “processed” cho sự kiện mà nghiệp vụ chưa commit. Theo dõi số lần duplicate, retry, lỗi không thể khôi phục, độ trễ và kích thước ledger.

## 7. Side effect ngoài database: transactional outbox

Giả sử sau khi cộng điểm còn phải gửi email hoặc phát sự kiện `PointsUpdated`. Gọi HTTP, gửi email hay publish message trực tiếp trong `@Transactional` không thể được rollback bởi JPA nếu bên ngoài đã nhận. Sau commit cũng có “khoảng hở” nếu process chết trước khi gửi.

Thiết kế **transactional outbox** phù hợp hơn:

1. Trong **cùng transaction** với marker và thay đổi điểm, lưu một hàng `outbox_event` chứa payload và ID ổn định.
2. Một publisher riêng đọc outbox, gửi tới broker rồi đánh dấu đã gửi. Publisher có thể gửi lặp nếu crash giữa gửi và đánh dấu.
3. Consumer downstream cũng cần idempotency theo ID tương ứng; nếu gọi dịch vụ ngoài hỗ trợ idempotency key, chuyển khóa ổn định đó cho dịch vụ.

Outbox xử lý tính nguyên tử giữa **ghi state DB** và **ghi ý định phát message**, không chứng minh toàn chuỗi chỉ giao đúng một lần. Với provider ngoài không hỗ trợ idempotency key, cần thiết kế riêng cho việc đối soát, bù trừ hoặc workflow trạng thái; không thể dùng riêng bảng `processed_event` để bảo đảm side effect ngoài DB đúng một lần.

## 8. Kế hoạch kiểm thử bắt buộc

Chạy integration test với **PostgreSQL thật** (ví dụ Testcontainers); H2 không chứng minh được cú pháp `ON CONFLICT` và hành vi khóa tương tranh của PostgreSQL. Các ca quan trọng:

| Ca | Thực hiện | Bất biến cần kiểm |
| --- | --- | --- |
| Một sự kiện | Gọi `handle(E1)` một lần | Điểm +7, một marker. |
| Giao lặp tuần tự | Gọi `handle(E1)` ba lần | Điểm chỉ +7, một marker. |
| Giao lặp đồng thời | Hai transaction/thread dùng đúng E1, chờ cùng bắt đầu | Cả hai hoàn tất hoặc được retry theo lỗi tạm thời; tổng điểm chỉ +7, một marker. |
| Rollback nghiệp vụ | Gọi E2 với account không tồn tại | Không còn marker E2, không có tăng điểm. |
| Retry sau rollback | Tạo account hợp lệ rồi giao lại chính E2 | Xử lý thành công đúng một lần. |
| Hai sự kiện hợp lệ khác nhau | E3 và E4 cùng account, ID khác nhau | Cộng tổng cả hai, không lost update. |
| Crash giữa commit và ACK | Commit E5 rồi giả lập không ACK, giao lại E5 | Không cộng điểm lần thứ hai. |
| Sai thứ tự/payload | Event version cũ hoặc cùng ID nhưng payload khác | Hệ thống áp dụng quy tắc domain/kiểm toán rõ ràng; không âm thầm ghi sai. |

Đối với test đồng thời, dùng barrier để các luồng bắt đầu gần nhau; mỗi lần gọi handler phải chạy trong transaction độc lập thông qua Spring proxy. Sau đó đọc **DB đã commit** để khẳng định điểm và số marker. Test exception cần bảo đảm transaction đã rollback trước khi đếm marker.

## 9. Checklist khi đưa vào production

- Producer dùng ID sự kiện ổn định; có hợp đồng rõ về eventId, consumer scope, schema version và replay.
- Database có UNIQUE thật trên khóa dedup; marker và business write commit/rollback cùng nhau.
- ACK sau commit; retry/DLQ phân biệt lỗi tạm thời với lỗi đầu vào, có giám sát.
- Thao tác trên state chung chịu được concurrency của **những event khác nhau** và có quy tắc ordering nếu cần.
- Side effect ra ngoài dùng outbox/idempotency key hoặc cơ chế bù trừ thích hợp.
- Retention, migration và các integration test crash/replay được duy trì.

**Kết luận:** Trong Spring Data JPA, một handler nhận sự kiện lặp an toàn cần kết hợp **ID ổn định + UNIQUE ở DB + thao tác nhận quyền xử lý nguyên tử + transaction chứa cả marker và business change + ACK sau commit**. Mỗi thành phần giải quyết một cửa sổ lỗi khác nhau; thiếu một thành phần có thể khiến duplicate được áp dụng lại hoặc làm mất một sự kiện hợp lệ.
