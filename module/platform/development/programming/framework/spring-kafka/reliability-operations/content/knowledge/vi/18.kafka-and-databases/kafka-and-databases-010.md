# Inbox pattern

## 1. Inbox pattern giải quyết vấn đề gì?

Trong hệ thống dùng Spring Kafka và database, consumer thường nhận một sự kiện Kafka rồi ghi thay đổi vào database. Khó khăn xuất hiện khi **database transaction** và **Kafka offset commit** là hai thao tác độc lập.

Ví dụ một consumer xử lý `PaymentConfirmed`:

~~~text
Kafka topic: payments.confirmed
            |
            v
       @KafkaListener
            |
            v
      Ghi orders vào DB
            |
            v
      Commit Kafka offset
~~~

Nếu database đã commit thành công nhưng ứng dụng crash trước khi Kafka offset được commit, record có thể được giao lại sau khi consumer restart. Nếu xử lý lần nữa một cách ngây thơ, hệ thống có thể ghi nhận thanh toán hai lần, cộng doanh thu hai lần hoặc phát thêm sự kiện không cần thiết.

**Inbox pattern** giải quyết vấn đề này bằng cách ghi một dấu vết định danh sự kiện đã xử lý vào **cùng database transaction** với side effect nghiệp vụ. Khi record được giao lại, consumer kiểm tra dấu vết đó và bỏ qua phần side effect đã hoàn tất.

Nguyên tắc cốt lõi:

> Ghi nhận sự kiện đã xử lý và thay đổi dữ liệu nghiệp vụ phải commit hoặc rollback cùng nhau trong một database transaction.

Inbox không ngăn Kafka giao record nhiều lần. Nó làm cho nhiều lần giao cùng một sự kiện tạo ra **cùng một hiệu ứng nghiệp vụ** tại database, miễn là khóa idempotency và transaction boundary được thiết kế đúng.

## 2. Tại sao at-least-once cần inbox?

### 2.1. Hai hệ thống không commit nguyên tử

Một listener đơn giản:

~~~java
@KafkaListener(topics = "payments.confirmed", groupId = "billing-service")
public void onPayment(PaymentConfirmed event) {
    orderRepository.markAsPaid(event.orderId());
}
~~~

Nếu Spring Kafka commit offset sau khi listener trả về thành công, trình tự có thể là:

~~~mermaid
sequenceDiagram
    participant K as Kafka broker
    participant L as Spring Kafka listener
    participant D as Database
    K-->>L: Record offset 41
    L->>D: UPDATE orders
    D-->>L: DB commit thành công
    Note over L: Process crash tại đây
    Note over K: Offset 42 chưa commit
    K-->>L: Sau restart: giao lại offset 41
    L->>D: UPDATE orders một lần nữa
~~~

Đây là cửa sổ lỗi thông thường của **at-least-once delivery**. Kafka không hứa listener chỉ được chạy một lần. Nó ưu tiên không bỏ sót record chưa commit.

Nếu chọn commit offset **trước** database transaction để tránh duplicate, lại xuất hiện cửa sổ ngược: Kafka tiến qua record nhưng database chưa được cập nhật. Crash lúc đó làm mất xử lý nghiệp vụ.

Inbox giúp chấp nhận redelivery mà không lặp tác động trên database. Nó không biến hai thao tác commit thành XA transaction.

### 2.2. Các nguồn duplicate khác

Ngay cả khi listener ít crash, duplicate vẫn có thể xuất hiện do:

- Consumer bị rebalance trước khi commit offset.
- Kafka offset commit thất bại hoặc timeout.
- Listener ném exception sau khi side effect đã commit.
- Kafka producer gửi lại cùng business event sau timeout.
- Event được replay bằng group ID mới hoặc công cụ vận hành.
- Nhiều topic, dịch vụ hoặc consumer group cùng tiếp nhận một sự kiện logic.
- Một ứng dụng cũ và một ứng dụng mới cùng triển khai trong thời gian chuyển đổi.

Inbox vì vậy là cơ chế **idempotent consumer**, không chỉ là cách xử lý một trường hợp crash hiếm.

## 3. Cấu trúc của inbox

### 3.1. Inbox table tối thiểu

Với PostgreSQL, có thể tạo bảng:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ý nghĩa:

- `consumer_name`: tên consumer/handler logic. Nó phân biệt các luồng nghiệp vụ có thể xử lý cùng một event vì những mục đích khác nhau.
- `event_id`: định danh **ổn định** của event do producer cấp hoặc do hợp đồng tích hợp xác định.
- `event_type`: hỗ trợ truy vết và xử lý dữ liệu.
- `processed_at`: thời điểm database ghi nhận xử lý thành công.

**Primary key hoặc unique constraint là trung tâm của thiết kế**. Kiểm tra “có tồn tại chưa?” bằng một câu SELECT rồi mới INSERT **không đủ an toàn** khi có hai transaction đồng thời. Cả hai có thể cùng thấy “chưa có”. Unique constraint ở database mới là ranh giới chống ghi trùng đáng tin cậy.

### 3.2. Khóa idempotency phải có scope

Giả sử sự kiện `evt-123` có thể được xử lý bởi hai handler:

~~~text
billing-projection / evt-123 -> cập nhật trạng thái đơn hàng
loyalty-points     / evt-123 -> cộng điểm khách hàng
~~~

Nếu inbox chỉ có `event_id` là khóa duy nhất dùng chung cho hai nghiệp vụ, handler đầu tiên sẽ chặn handler còn lại. Đưa `consumer_name` vào unique key cho phép mỗi nghiệp vụ thực thi đúng một lần độc lập.

`consumer_name` không nhất thiết là Kafka `group.id`. Consumer group có thể thay đổi trong quá trình migration hoặc replay, trong khi ranh giới idempotency cần gắn với **mục đích nghiệp vụ**. Hãy chọn scope phù hợp và giữ ổn định qua các lần deploy.

### 3.3. Event ID khác offset

Kafka record có định danh vận chuyển gồm topic, partition và offset:

~~~text
topic=payments.confirmed, partition=2, offset=1045
~~~

Bộ ba này duy nhất cho vị trí record trong Kafka log, nhưng không đồng nhất với business event ID. Cùng một business event có thể được producer gửi hai lần ở các offset khác nhau; dùng chỉ `topic-partition-offset` để deduplicate sẽ không nhận ra chúng là cùng sự kiện nghiệp vụ.

Với event hợp đồng tốt, ưu tiên một `eventId` ổn định trong payload/header. Nếu nguồn hoàn toàn không cấp event ID, có thể dùng bộ ba Kafka như khóa chống **redelivery của cùng Kafka record**, nhưng phải ghi rõ giới hạn: nó không loại bỏ duplicate được publish ở offset khác, và cần xem xét namespace topic/cluster.

## 4. Hai bước ghi phải nằm trong cùng database transaction

### 4.1. Trình tự đúng

~~~mermaid
flowchart TD
    A[Kafka record đến listener] --> B[BEGIN DB transaction]
    B --> C{INSERT inbox thành công?}
    C -->|Đã tồn tại| D[Duplicate: không chạy side effect]
    D --> E[COMMIT DB transaction]
    C -->|Insert mới| F[Thực hiện thay đổi nghiệp vụ]
    F -->|Thành công| E
    F -->|Exception| G[ROLLBACK DB transaction]
    E --> H[Listener kết thúc thành công]
    H --> I[Container commit Kafka offset theo AckMode]
    G --> J[Ném exception để retry/recovery]
~~~

Nếu event mới:

1. Listener bắt đầu một database transaction thông qua service.
2. Service INSERT khóa inbox.
3. Nếu INSERT là mới, service áp dụng thay đổi nghiệp vụ.
4. Database commit **cả inbox và thay đổi nghiệp vụ**.
5. Listener trả về thành công.
6. Spring Kafka được phép tiến offset theo acknowledgment mode.

Nếu event đã được xử lý:

1. INSERT inbox báo conflict với khóa đã tồn tại.
2. Service không thực hiện side effect thêm lần nữa.
3. Listener trả về thành công.
4. Container có thể commit offset hiện tại để tiến qua bản ghi lặp.

Nếu side effect thất bại, **inbox INSERT phải rollback theo** để lần delivery tiếp theo có thể xử lý lại. Không được để inbox row tồn tại ở trạng thái “đã xử lý” khi thay đổi nghiệp vụ chưa bền vững.

### 4.2. Không chia thành hai transaction

Ví dụ sai:

~~~java
public void process(PaymentConfirmed event) {
    inboxRepository.markProcessed(event.eventId()); // Transaction riêng
    orderService.applyPayment(event);               // Transaction riêng
}
~~~

Nếu bước đầu commit thành công rồi bước thứ hai thất bại, lần giao lại sẽ thấy event đã nằm trong inbox và có thể bỏ qua, mặc dù đơn hàng chưa được cập nhật. Inbox lúc đó biến thành cơ chế **mất xử lý**.

Chiều ngược lại cũng không an toàn: cập nhật database trong transaction thứ nhất rồi ghi inbox trong transaction thứ hai. Crash giữa hai transaction vẫn gây duplicate effect.

## 5. Ví dụ hoàn chỉnh với PostgreSQL và Spring Kafka

### 5.1. Schema minh họa

Ví dụ một dịch vụ nhận `PaymentConfirmed` để cập nhật đơn hàng:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    paid_amount_cents BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

INSERT INTO orders(order_id, status)
VALUES ('order-42', 'PENDING');
~~~

Bảng `orders` là ví dụ tối giản. Production có thể có thêm các ràng buộc nghiệp vụ, audit fields và payment identifier.

### 5.2. Event có ID ổn định

~~~java
package com.example.events;

import java.util.UUID;

public record PaymentConfirmed(
    UUID eventId,
    String paymentId,
    String orderId,
    long amountCents
) {}
~~~

Producer phải giữ `eventId` không đổi khi gửi lại **cùng một sự kiện logic**. Nếu mỗi lần retry ở producer lại sinh UUID mới, inbox sẽ coi đó là một event khác và không thể deduplicate như mong muốn.

`paymentId` có thể được dùng làm business idempotency key bổ sung, ví dụ một payment chỉ được ghi nhận một lần ngay cả khi source phát ra hai event IDs. Hợp đồng idempotency cần được xác định theo nghiệp vụ chứ không dựa duy nhất vào lựa chọn kỹ thuật của producer.

### 5.3. Spring Boot consumer configuration

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-inbox
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
        spring.json.value.default.type: com.example.events.PaymentConfirmed
    listener:
      ack-mode: record
~~~

`enable-auto-commit: false` để Spring Kafka listener container điều phối commit theo kết quả xử lý. Với `ack-mode: record`, container commit sau khi record listener hoàn tất thành công.

Config chỉ là phần consumer. Database connection, pool và transaction manager cần cấu hình riêng theo Spring Boot/JDBC thực tế. Nếu cùng ứng dụng có cả KafkaTransactionManager và database transaction manager, hãy chỉ định rõ transaction manager dùng cho inbox.

### 5.4. Transaction manager của database

Nếu dùng JDBC với một `DataSource`, có thể tạo manager có tên tường minh:

~~~java
@Configuration
public class DatabaseTransactionConfiguration {

    @Bean("dbTransactionManager")
    public PlatformTransactionManager dbTransactionManager(
        DataSource dataSource
    ) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Bean này điều khiển transaction database. Không thay nó bằng `KafkaTransactionManager` rồi kỳ vọng thao tác INSERT/UPDATE SQL trở thành cùng một database transaction.

Nếu ứng dụng dùng JPA, có thể dùng `JpaTransactionManager`; cần bảo đảm mọi thao tác inbox và nghiệp vụ tham gia **cùng** database transaction manager.

### 5.5. Service thực hiện insert-if-absent và side effect

~~~java
@Service
public class PaymentInboxService {

    private static final String CONSUMER_NAME = "billing-projection";

    private final JdbcTemplate jdbc;

    public PaymentInboxService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void apply(PaymentConfirmed event) {
        int inserted = jdbc.update(
            """
            INSERT INTO consumer_inbox (
                consumer_name, event_id, event_type
            )
            VALUES (?, ?, ?)
            ON CONFLICT (consumer_name, event_id)
            DO NOTHING
            """,
            CONSUMER_NAME,
            event.eventId(),
            "PaymentConfirmed"
        );

        if (inserted == 0) {
            // Event này đã hoàn tất tại consumer logic này.
            return;
        }

        int updated = jdbc.update(
            """
            UPDATE orders
            SET status = 'PAID',
                paid_amount_cents = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND status = 'PENDING'
            """,
            event.amountCents(),
            event.orderId()
        );

        if (updated != 1) {
            throw new IllegalStateException(
                "Order cannot transition to PAID: " + event.orderId()
            );
        }
    }
}
~~~

Đây là PostgreSQL SQL với `ON CONFLICT ... DO NOTHING` và Java text blocks; dự án cần Java version hỗ trợ cú pháp đó. Ý nghĩa quan trọng:

- Unique constraint quyết định event đã được xử lý hay chưa.
- INSERT inbox và UPDATE order nằm trong **cùng transaction** bởi `@Transactional`.
- Duplicate event trả về sớm mà không cập nhật đơn hàng lần hai.
- Nếu UPDATE không thành công, exception khiến transaction rollback cả inbox row vừa INSERT.
- Nếu UPDATE và transaction commit thành công, inbox record trở thành dấu vết đã xử lý bền vững.

Điều kiện `status = 'PENDING'` chỉ là quy tắc minh họa. Một hệ thống thực tế phải phân biệt đơn hàng đã thanh toán bằng **cùng payment** với trạng thái bất hợp lệ do một event khác. Không mặc định mọi `updated == 0` đều là duplicate.

### 5.6. Listener nên mỏng

~~~java
@Component
public class PaymentListener {

    private final PaymentInboxService service;

    public PaymentListener(PaymentInboxService service) {
        this.service = service;
    }

    @KafkaListener(
        topics = "payments.confirmed",
        groupId = "billing-inbox"
    )
    public void onPayment(PaymentConfirmed event) {
        service.apply(event);
    }
}
~~~

Listener gọi một Spring bean khác để `@Transactional` chạy qua proxy. Khi `apply()` trả về thành công, database transaction đã commit trong đường gọi đồng bộ bình thường; listener mới kết thúc để container tiến Kafka offset.

Nếu database bị lỗi, exception được truyền qua listener đến Spring Kafka error handler. Không bắt exception rồi chỉ ghi log và trả về, vì container có thể hiểu record đã xử lý thành công và commit offset.

### 5.7. Luồng hoạt động thực tế

~~~text
Kafka: PaymentConfirmed(eventId = e1, orderId = order-42)
      |
      v
Listener -> PaymentInboxService.apply()
      |
      v
BEGIN DB transaction
  INSERT inbox(billing-projection, e1) -> inserted 1
  UPDATE orders(order-42) -> PAID
COMMIT DB
      |
      v
Listener returns
      |
      v
Spring Kafka commits offset
~~~

Nếu record được giao lại:

~~~text
Kafka: PaymentConfirmed(eventId = e1)
      |
      v
BEGIN DB transaction
  INSERT inbox(billing-projection, e1)
    ON CONFLICT DO NOTHING -> inserted 0
  Skip business update
COMMIT DB
      |
      v
Listener returns -> offset can advance
~~~

## 6. Vì sao INSERT trước UPDATE vẫn an toàn?

Có thể lo ngại rằng “INSERT inbox trước UPDATE” nghĩa là event bị đánh dấu đã xử lý trước khi side effect thành công. Điều đó chỉ nguy hiểm nếu hai thao tác **commit riêng**.

Trong một database transaction, cả hai thay đổi chưa được commit ra ngoài cho đến khi transaction hoàn tất. Nếu UPDATE thất bại rồi transaction rollback, inbox row cũng biến mất.

~~~text
Transaction T1:
  INSERT inbox e1    (chưa commit)
  UPDATE orders      (exception)
  ROLLBACK T1
       |
       +-- inbox e1 không tồn tại
       +-- orders không bị cập nhật một nửa
~~~

Vì thế, điểm đảm bảo là **atomic database commit**, không phải thứ tự INSERT/UPDATE tự thân.

Nếu service gọi một thao tác ngoài database như HTTP charge tiền giữa hai câu SQL, database rollback không thể hoàn tác HTTP request đã thực hiện. Inbox đơn thuần chưa đảm bảo exactly-once cho side effect ngoài transaction đó; cần idempotency key phía dịch vụ ngoài, workflow/saga hoặc thiết kế riêng.

## 7. Concurrent duplicate và unique constraint

### 7.1. Tại sao SELECT trước INSERT không đủ?

Mẫu sai về mặt concurrency:

~~~java
if (!inboxRepository.existsById(eventId)) {
    orderService.apply(event);
    inboxRepository.save(eventId);
}
~~~

Hai listener ở các consumer group khác nhau hoặc hai luồng xử lý cùng event có thể cùng đọc “chưa tồn tại”, cùng thực hiện side effect rồi mới ghi inbox.

~~~text
T1: SELECT inbox e1 -> not found
T2: SELECT inbox e1 -> not found
T1: UPDATE order
T2: UPDATE order
T1: INSERT inbox e1
T2: INSERT inbox e1 -> conflict (quá muộn)
~~~

Nếu side effect nằm ngoài transaction hoặc transaction boundary bị chia nhỏ, dữ liệu có thể đã bị cập nhật trùng.

### 7.2. INSERT atomically có uniqueness

Với `INSERT ... ON CONFLICT DO NOTHING`, database kiểm soát tranh chấp khóa unique. Nếu T1 đã INSERT e1 nhưng chưa commit, T2 cần chờ hoặc giải quyết conflict theo transaction outcome của T1:

- T1 commit: T2 không insert thêm, nhận kết quả duplicate.
- T1 rollback: T2 có thể insert e1 và tự thực hiện xử lý.
- Nếu transaction bị deadlock/timeout hoặc database trả lỗi khác, listener phải ném exception để retry; không coi mọi SQL error là duplicate.

Mẫu này an toàn hơn “SELECT rồi INSERT” vì quyết định first processing do database thực hiện nguyên tử.

### 7.3. Cần thêm khóa nghiệp vụ nếu producer có thể phát duplicate event ID khác nhau

Giả sử một payment `pay-99` được gửi thành hai event có ID e1 và e2:

~~~text
eventId = e1, paymentId = pay-99
eventId = e2, paymentId = pay-99
~~~

Inbox theo event ID sẽ xử lý cả e1 và e2 như hai sự kiện khác nhau. Nếu nghiệp vụ yêu cầu “một payment chỉ được ghi nhận một lần”, nên có thêm ràng buộc unique cho `payment_id` hoặc ledger transaction ID phù hợp, hoặc thiết kế producer giữ event ID ổn định.

**Inbox chống duplicate theo khóa được chọn.** Nó không tự nhận biết hai payload khác ID là cùng một hành động nghiệp vụ.

## 8. Kafka offset commit đến sau database commit

Một cấu hình phổ biến là `enable-auto-commit=false` và container ack mode phù hợp, chẳng hạn `RECORD`.

Trình tự:

~~~mermaid
sequenceDiagram
    participant B as Kafka broker
    participant L as Listener container
    participant S as Inbox service
    participant D as Database

    B-->>L: Record offset 70
    L->>S: apply(event)
    S->>D: BEGIN + INSERT inbox
    S->>D: UPDATE business data
    S->>D: COMMIT DB
    D-->>S: Commit OK
    S-->>L: Service returns
    L->>B: Commit next offset 71
    B-->>L: Commit result
~~~

**Offset được commit là vị trí tiếp theo sẽ đọc**. Sau khi xử lý record offset 70, Kafka commit thường dùng offset 71.

Nếu DB commit thành công nhưng Kafka commit thất bại, record 70 có thể được giao lại. Inbox row đã tồn tại nên business update không chạy lại.

Nếu DB commit thất bại, service ném exception, listener không được báo thành công. Error handler có thể retry hoặc recover theo policy.

Không tự gọi `Acknowledgment.acknowledge()` trước khi database transaction commit. Nếu làm vậy, Kafka offset có thể tiến trước khi side effect được lưu bền vững.

## 9. Bảng crash window quan trọng

| Điểm xảy ra lỗi | Trạng thái inbox | Trạng thái nghiệp vụ | Khi redelivery |
|---|---|---|---|
| Trước khi bắt đầu DB transaction | Chưa có | Chưa thay đổi | Xử lý như mới |
| Sau inbox INSERT nhưng trước UPDATE | Rollback cùng DB transaction | Chưa commit | INSERT và xử lý lại |
| Sau UPDATE nhưng trước DB COMMIT | Rollback cùng DB transaction | Chưa commit | Xử lý lại |
| Sau DB COMMIT nhưng trước Kafka offset COMMIT | Đã có | Đã commit | Duplicate được bỏ qua |
| Sau Kafka offset COMMIT | Đã có | Đã commit | Thường không redeliver cùng group, trừ replay chủ đích |
| Kafka commit timeout không rõ kết quả | Đã có | Đã commit | Nếu redelivery, bỏ qua qua inbox |
| Producer phát lại event ID ổn định ở offset khác | Đã có | Đã commit | Bỏ qua lần gửi lặp |

Điểm mấu chốt: Kafka vẫn có thể gọi listener nhiều lần. Với cùng event ID và consumer logic, chỉ lần đầu được phép thực hiện database side effect; lần sau chỉ xác nhận nó đã hoàn tất.

## 10. Inbox khác Outbox thế nào?

Tên gần giống nhau nhưng hướng dữ liệu khác nhau.

| Mẫu | Hướng | Bài toán chính | Transaction boundary |
|---|---|---|---|
| **Inbox** | Kafka → consumer → DB | Chống side effect lặp khi nhận record nhiều lần | Inbox row + business update cùng DB transaction |
| **Outbox** | DB → Kafka | Không làm mất event cần publish khi nghiệp vụ đã commit DB | Business update + outbox row cùng DB transaction |

### 10.1. Inbox nhận từ Kafka

~~~text
Kafka -> Listener -> DB transaction
                      |
                      +-- INSERT inbox(eventId)
                      +-- UPDATE domain table
~~~

Nếu database commit nhưng Kafka offset chưa commit, redelivery được inbox chống duplicate.

### 10.2. Outbox phát lên Kafka

~~~text
Business API -> DB transaction
                  |
                  +-- UPDATE domain table
                  +-- INSERT outbox(event)
                         |
                         v
                  Outbox publisher -> Kafka
~~~

Nếu outbox publisher gửi event rồi crash trước khi đánh dấu sent, nó có thể phát lại. Vì vậy consumer downstream thường cần inbox/idempotency.

### 10.3. Dùng cả hai trong cùng một service

Khi consumer vừa cập nhật database vừa cần phát một Kafka event tiếp theo, có thể sử dụng:

~~~mermaid
flowchart LR
    K[Kafka input] --> L[Listener]
    L --> T[Database transaction]
    T --> I[Inbox]
    T --> D[Domain tables]
    T --> O[Outbox]
    O --> P[Outbox publisher]
    P --> Q[Kafka output]
~~~

Trong **cùng DB transaction**, service INSERT inbox, thay đổi domain và INSERT outbox. Nếu transaction rollback, cả ba cùng rollback. Outbox publisher gửi record sau đó; nếu gửi lặp, downstream dùng event ID để deduplicate.

Mẫu kết hợp này giúp chuyển từ một message Kafka vào database rồi phát message khác mà không dựa vào giao dịch XA giữa Kafka và SQL. Nó vẫn mang tính at-least-once ở các ranh giới vận chuyển, nên idempotency vẫn thiết yếu.

## 11. Thiết kế inbox có trạng thái PENDING / PROCESSED

Một số ứng dụng có công việc xử lý dài hoặc nhiều giai đoạn. Có thể thiết kế inbox table với trạng thái:

~~~sql
CREATE TABLE consumer_inbox_jobs (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,
    error_message TEXT,
    PRIMARY KEY (consumer_name, event_id),
    CHECK (status IN ('PENDING', 'PROCESSING', 'PROCESSED', 'FAILED'))
);
~~~

Trong trường hợp này, **không được coi “row đã tồn tại” đồng nghĩa “nghiệp vụ đã xử lý xong”**.

Nếu listener ghi PENDING rồi commit offset và một worker khác xử lý sau, inbox đóng vai trò một **durable work queue**, không còn là dấu vết PROCESSED đơn giản. Cần bổ sung:

- Worker claim/lease hoặc khóa để tránh xử lý cùng job đồng thời.
- Retry, timeout và cơ chế khôi phục job PROCESSING bị treo.
- Tính bền vững trước khi commit Kafka offset.
- Phân biệt PENDING/PROCESSING/PROCESSED khi duplicate xuất hiện.
- Giới hạn số job và backpressure khi worker không theo kịp.

Nếu chỉ cần idempotent database update ngắn, schema inbox chỉ lưu các event đã hoàn tất trong **một transaction** thường đơn giản hơn.

## 12. Lựa chọn khóa deduplication

Không có một khóa phù hợp cho mọi luồng. Cần xác định một business event được coi là “cùng” khi nào.

### 12.1. Event ID

Phù hợp khi producer có hợp đồng `eventId` duy nhất và giữ nguyên qua retry của cùng event.

~~~text
consumer_name = billing-projection
event_id      = 3fef7c3a-...
~~~

### 12.2. Business operation ID

Nếu nghiệp vụ là ghi nhận thanh toán, `paymentId` hoặc `transactionId` từ payment provider có thể là ràng buộc bổ sung. Một operation ID có thể đại diện cho một thao tác không được áp dụng hai lần, ngay cả khi nhà cung cấp tạo hai message IDs khác nhau.

### 12.3. Source topic-partition-offset

Có thể dùng:

~~~text
source_cluster + topic + partition + offset
~~~

Nó hữu ích khi source chưa có event ID và mục tiêu là deduplicate **cùng record Kafka** sau redelivery. Nhưng nếu cùng business event được publish lại ở offset mới, khóa này thay đổi nên không chống được duplicate logic.

### 12.4. Event version và cập nhật liên tiếp

Một aggregate có thể có nhiều event hợp lệ:

~~~text
Order-42 Created, version 1
Order-42 Paid,    version 2
Order-42 Shipped, version 3
~~~

Không dùng riêng `orderId` làm khóa inbox chung, vì nó sẽ chặn các event hợp lệ tiếp theo. Có thể dùng event ID hoặc cặp `aggregateId + eventVersion` nếu producer bảo đảm semantics version phù hợp.

Nếu cần strict ordering và xử lý event đến trễ, inbox đơn thuần chưa đủ; cần kiểm soát version/state transition trong database.

## 13. Transaction isolation và cạnh tranh ghi

### 13.1. READ COMMITTED thường đủ cho unique insert

Trong PostgreSQL, unique constraint và `INSERT ... ON CONFLICT DO NOTHING` cung cấp ranh giới nguyên tử chống cùng một khóa được insert hai lần. Không nhất thiết phải dùng `SERIALIZABLE` chỉ để bảo đảm uniqueness của inbox.

Tuy nhiên, logic cập nhật domain phức tạp có thể cần isolation, optimistic locking, row locking hoặc business constraint riêng. Inbox chỉ bảo đảm một event ID không chạy side effect lặp; nó không tự giải quyết mọi race giữa **hai event khác nhau** cùng cập nhật một order.

### 13.2. Deadlock và transient SQL error

Nếu database trả deadlock, serialization failure hoặc timeout, transaction có thể bị rollback. Listener cần ném exception để Spring Kafka retry khi phù hợp.

Không nên bắt mọi `DataAccessException` rồi coi đó là duplicate. Duplicate hợp lệ được xác định bằng kết quả của atomic insert/unique constraint; các lỗi database còn lại cần phân loại và xử lý.

### 13.3. Một event được consumer khác nhìn thấy cùng lúc

Trong một group Kafka, một partition thường chỉ được một consumer sở hữu tại một thời điểm. Nhưng một event logic vẫn có thể đến qua nhiều group, retry topic, replay hoặc duplicate publish. Unique constraint bảo vệ database kể cả khi hai transaction độc lập cố xử lý cùng event đồng thời.

## 14. Bẫy Spring @Transactional

### 14.1. Self-invocation

Với proxy-based Spring transactions, phương thức có `@Transactional` được gọi từ một phương thức khác **trên chính object đó** có thể không đi qua proxy, khiến transaction advice không chạy.

Ví dụ không nên dựa vào:

~~~java
@Service
public class InboxHandler {

    public void onEvent(PaymentConfirmed event) {
        applyInTransaction(event); // Gọi nội bộ cùng object
    }

    @Transactional
    public void applyInTransaction(PaymentConfirmed event) {
        // INSERT inbox + UPDATE business
    }
}
~~~

Nên tách service xử lý transaction thành bean riêng và để listener gọi qua Spring proxy, hoặc dùng `TransactionTemplate` khi cần boundary tường minh.

### 14.2. Chọn nhầm transaction manager

Một ứng dụng có thể có `KafkaTransactionManager` cùng `JpaTransactionManager` hoặc `DataSourceTransactionManager`.

Nếu `@Transactional` không chỉ rõ manager, nó có thể chọn default manager khác với mong muốn. Inbox và domain update cần nằm trong **cùng database transaction**; dùng KafkaTransactionManager không tự quản lý JDBC/JPA transaction.

Chỉ định rõ manager trong service hoặc cấu hình transaction manager mặc định một cách có chủ đích.

### 14.3. Checked exception và rollback rule

Mặc định, Spring `@Transactional` thường rollback với unchecked exception và `Error`. Với checked exception, cần cấu hình `rollbackFor` nếu muốn transaction rollback.

~~~java
@Transactional(
    transactionManager = "dbTransactionManager",
    rollbackFor = Exception.class
)
public void applyWithCheckedException(PaymentConfirmed event)
        throws Exception {
    // INSERT inbox + UPDATE domain
}
~~~

Không bắt exception rồi trả về thành công trước khi Spring quyết định rollback. Nếu cố ý recover lỗi, phải bảo đảm dữ liệu vẫn nhất quán và không đánh dấu sự kiện PROCESSED khi side effect còn dang dở.

### 14.4. Async thread

Spring transaction synchronization thường gắn với thread. Nếu service bắt đầu database transaction rồi đưa side effect sang executor thread, không nên giả định task đó tham gia cùng transaction.

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void unsafe(PaymentConfirmed event) {
    inboxRepository.insert(event.eventId());
    executor.execute(() -> orderRepository.markPaid(event.orderId()));
}
~~~

Transaction của thread listener có thể commit inbox row trước khi task nền thực hiện UPDATE. Nếu task lỗi hoặc process dừng, lần redelivery sẽ bị coi là duplicate và bỏ qua.

Nếu bắt buộc xử lý async, dùng durable queue/job state có lease, retry và recovery đúng semantics thay vì một task nền duy nhất trong RAM.

## 15. Error handling, retry và DLT

### 15.1. Database exception cần đi ra listener

Khi service ném exception, container chuyển record cho error handler. `DefaultErrorHandler` có thể retry theo BackOff hoặc recover record sau khi hết retry.

Ví dụ cơ bản:

~~~java
@Bean
public DefaultErrorHandler defaultErrorHandler(
    KafkaTemplate<Object, Object> kafkaTemplate
) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Ví dụ này tạo một chính sách retry có giới hạn và recoverer publish DLT. Cần gắn error handler vào listener container factory thực tế và cấu hình serializer/ACL/DLT topic tương ứng.

Nếu record lỗi vì database tạm thời không khả dụng, retry có thể phù hợp. Nếu payload vi phạm schema hoặc domain rule vĩnh viễn, retry vô hạn không giúp ích; cần phân loại non-retryable và đưa vào recovery.

### 15.2. Inbox khi record được gửi DLT

Nếu thay đổi database thất bại và transaction rollback, inbox row `PROCESSED` cũng không tồn tại. Sau khi hết retry, error handler có thể publish record sang DLT rồi cho container tiến offset nguồn theo policy.

Đừng nhầm:

- Record **đã được xử lý nghiệp vụ thành công**: inbox có dấu vết PROCESSED cùng side effect.
- Record **đã được chuyển DLT**: không nhất thiết có inbox PROCESSED; cần quy trình điều tra/replay riêng.

Nếu DLT được replay sau khi sửa lỗi, event có thể được xử lý lại bằng cùng event ID. Nếu trước đó database side effect đã thực sự commit, inbox ngăn duplicate. Nếu trước đó DB rollback, inbox cho phép xử lý mới.

### 15.3. DLT publisher cũng có thể thất bại

Nếu publish DLT thất bại, không được âm thầm coi record đã recover an toàn. Cần kiểm tra send result, timeout, recoverer behavior và commit offset nguồn.

Không nên thêm inbox row để “ngăn record lỗi quay lại” nếu chưa có nơi lưu lỗi bền vững và được vận hành đúng. Điều đó có thể khiến sự kiện biến mất khỏi pipeline.

### 15.4. Retry topic và ordering

Nếu dùng non-blocking retry, record lỗi chuyển sang retry topic, còn record phía sau tại topic nguồn có thể tiếp tục. Điều này có thể thay đổi thứ tự hoàn tất nghiệp vụ.

Inbox chống xử lý trùng theo event ID, **không bảo đảm event ordering**. Nếu hai event khác nhau cần áp dụng theo version, state machine hoặc aggregate ordering, phải có điều kiện cập nhật/domain constraints riêng.

## 16. Inbox với batch listener

Batch listener nhận nhiều record trong một lần gọi và có thể ghi database theo lô. Inbox vẫn có giá trị, nhưng xử lý lỗi partial success cần rõ ràng.

Giả sử batch gồm:

~~~text
A: eventId=e1
B: eventId=e2
C: eventId=e3
~~~

Có hai hướng:

**Một database transaction cho cả batch**: INSERT inbox và cập nhật domain cho cả A, B, C rồi commit cùng nhau. Nếu một phần tử lỗi, rollback toàn batch và retry. Các side effect trong database không bị commit một phần; kích thước batch có thể làm tăng lock và thời gian transaction.

**Một database transaction cho từng record**: xử lý từng item bằng service transactional riêng. Khi item B lỗi, A có thể đã commit, C chưa xử lý. Error handler phải biết item lỗi, ví dụ qua `BatchListenerFailedException` để quản lý tiến độ đúng. A có thể được giao lại nhưng inbox sẽ bỏ qua duplicate.

Không giả định một batch có một offset duy nhất: batch có thể chứa nhiều partition, và committed offset phải được quản lý riêng từng topic-partition. Nếu xử lý song song trong batch, không commit vượt qua record chưa hoàn tất.

## 17. Kết hợp với Kafka transaction và Exactly-once

Kafka có producer transaction và tính năng phối hợp output Kafka records với source consumer offsets trong consume–process–produce. Điều đó hỗ trợ exactly-once semantics **trong phạm vi Kafka** khi transaction và consumer isolation được cấu hình đúng.

Inbox giải quyết bài toán khác: **idempotent database side effect** khi Kafka record được giao lại.

~~~text
Kafka input
    |
    v
Spring Kafka listener
    |
    +--- Database transaction:
    |       INSERT inbox
    |       UPDATE business state
    |
    +--- Kafka offset commit
~~~

Đường đi này không có một transaction bao gồm cả SQL và Kafka, nhưng inbox cho phép xử lý at-least-once mà không lặp database side effect theo khóa đã chọn.

Nếu consumer vừa cập nhật SQL vừa gửi Kafka output, có thể dùng inbox + outbox trong cùng DB transaction. Không nên chỉ bật `KafkaTransactionManager` rồi tuyên bố database và Kafka được commit nguyên tử theo XA.

## 18. Retention và dọn dẹp inbox

Inbox tăng dần khi số event đã xử lý lớn. Cần chính sách lưu trữ nhưng **xóa inbox quá sớm có thể làm mất bảo vệ idempotency**.

Ví dụ:

~~~text
Ngày 1: e1 được xử lý và inbox ghi e1
Ngày 7: cleanup xóa e1
Ngày 8: replay e1 từ Kafka / DLT
Ngày 8: inbox không còn e1 -> nghiệp vụ có thể chạy lần hai
~~~

Retention phải dựa trên:

- Kafka topic retention và khả năng replay thực tế.
- Thời hạn lưu record DLT/retry topic.
- Khả năng producer gửi lại event cũ.
- Thời hạn mà nghiệp vụ cần chống duplicate.
- Quy định audit, storage cost và dữ liệu cá nhân.
- Các quy trình migration hoặc import dữ liệu lịch sử.

Nếu hệ thống cho phép replay nhiều năm, không thể chỉ giữ inbox một tuần mà vẫn hứa deduplication vô hạn. Có thể cần lưu khóa idempotency dài hạn, archive searchable hoặc dùng domain-level unique constraint bền vững.

### 18.1. Tránh lưu payload nhạy cảm không cần thiết

Inbox thường chỉ cần consumer scope, event ID, type và processed timestamp. Không nhất thiết lưu đầy đủ payload hoặc thông tin nhạy cảm vào bảng này.

Nếu cần audit/reconciliation, lưu metadata tối thiểu và đặt retention/access control theo yêu cầu bảo mật. Một bảng inbox chứa payload của mọi event có thể tạo thêm bề mặt rủi ro bảo mật và chi phí storage.

### 18.2. Tối ưu bảng lớn

Với throughput cao:

- Dùng primary key/unique index đúng thứ tự khóa query.
- Theo dõi thời gian INSERT, index size và lock contention.
- Tách workload báo cáo khỏi bảng inbox phục vụ transaction nóng.
- Dọn dẹp/partition table khi volume thực sự đòi hỏi.
- Cẩn thận với partitioning database vì một số hệ quản trị giới hạn uniqueness xuyên partitions.
- Đặt threshold cảnh báo khi dung lượng tăng bất thường.

Không bỏ unique constraint để tăng tốc vì nó chính là cơ chế chống duplicate quan trọng nhất của inbox.

## 19. Observability cho inbox

Theo dõi cả Kafka và database giúp xác định record được xử lý mới, bị bỏ qua do duplicate hay thất bại.

| Tín hiệu | Ý nghĩa |
|---|---|
| Inbox insert success | Số event lần đầu được nhận và xử lý |
| Inbox conflict / duplicate count | Số lần event đã xử lý được giao lại |
| DB transaction commit/rollback | Kết quả atomic inbox + domain update |
| Business processing duration | Độ trễ side effect |
| Inbox insert latency | Index/lock/contention |
| Consumer lag theo partition | Tiến độ xử lý Kafka |
| Kafka offset commit errors | Phát hiện redelivery tiềm năng |
| Listener retries | Lỗi DB/downstream tạm thời |
| DLT publication success/failure | Recovery khi event không xử lý được |
| Replay count | Số event được đọc lại có chủ đích |

Để truy vết, nên log `eventId`, consumer name, topic, partition, offset, outcome (processed/duplicate/failed) và correlation ID.

Tránh dùng event ID làm metric label vì cardinality rất lớn. Hãy dùng event ID trong structured log hoặc tracing, metric label chỉ giữ tập giá trị nhỏ như consumer, event type và outcome.

Nếu duplicate count tăng đột ngột, cần kiểm tra Kafka commit failures, consumer restarts, rebalance, producer replay và thay đổi offset policy; không mặc định mọi duplicate đều xuất phát từ lỗi Inbox.

## 20. Những lỗi thiết kế thường gặp

**INSERT inbox và UPDATE business ở hai transactions:** nếu một bước commit, bước kia rollback, hệ thống có thể mất xử lý hoặc lặp side effect.

**SELECT trước INSERT mà không có unique constraint:** bị race khi hai transaction đồng thời xử lý cùng event.

**Dùng event ID không ổn định:** producer sinh UUID mới mỗi lần retry nên inbox không deduplicate được business event.

**Khóa inbox chỉ gồm orderId:** chặn cả những event hợp lệ tiếp theo của cùng order.

**Dùng Kafka offset làm business event ID:** không chống được duplicate publish ở offset khác.

**Acknowledge Kafka trước DB commit:** crash sau ack làm group có thể bỏ qua record chưa được lưu bền vững.

**Bắt exception và trả về bình thường:** Spring Kafka có thể commit offset khi database thất bại.

**Gọi @Transactional bằng self-invocation:** transaction database có thể không được mở theo kỳ vọng.

**Đặt @Transactional nhưng chọn KafkaTransactionManager:** không làm cho JDBC/JPA update thành database transaction.

**Bắt lỗi unique constraint rồi rollback sai:** nên dùng cách INSERT atomic trả về duplicate một cách tường minh; không coi mọi SQL exception là duplicate.

**Đưa side effect sang async executor sau khi ghi inbox:** inbox commit trước khi side effect bền vững làm tăng nguy cơ mất xử lý.

**Inbox row tồn tại nhưng status chưa PROCESSED vẫn coi là duplicate:** dễ bỏ qua job dang dở trong mô hình inbox có nhiều trạng thái.

**Xóa inbox trước thời hạn replay:** record cũ được giao lại có thể chạy side effect lần nữa.

**Tin rằng inbox bảo vệ HTTP side effect không hỗ trợ idempotency:** database rollback không rollback một API ngoài đã thực hiện.

**Cho rằng inbox tự bảo đảm ordering:** cùng aggregate có thể có nhiều event ID và xử lý sai thứ tự nếu không kiểm soát version/state.

## 21. Quy trình kiểm thử Inbox pattern

Không chỉ kiểm thử happy path. Cần chủ động tạo lỗi đúng các ranh giới commit.

### 21.1. Lần xử lý đầu

1. Tạo một event ID chưa từng có.
2. Gửi record lên topic thử nghiệm.
3. Xác nhận domain row được cập nhật đúng.
4. Xác nhận inbox row có đúng consumer name và event ID.
5. Xác nhận Kafka offset được commit sau khi listener hoàn tất.

### 21.2. Redelivery cùng event ID

1. Gửi lại event với cùng event ID nhưng ở offset khác.
2. Xác nhận inbox INSERT trả duplicate.
3. Xác nhận business side effect không chạy lần hai.
4. Xác nhận consumer vẫn tiến qua record trùng thành công.

### 21.3. Database rollback

1. Tạo lỗi sau inbox INSERT nhưng trước business UPDATE/commit.
2. Xác nhận database transaction rollback.
3. Xác nhận không còn inbox row PROCESSED cho event đó.
4. Xác nhận domain state chưa bị cập nhật.
5. Cho retry thành công; xác nhận inbox và domain commit cùng nhau.

### 21.4. Crash sau DB COMMIT, trước offset commit

1. Cho listener hoàn tất DB transaction.
2. Dừng process có kiểm soát trước khi offset nguồn được commit.
3. Khởi động lại consumer cùng group ID.
4. Xác nhận event được giao lại.
5. Xác nhận inbox bỏ qua duplicate và domain không bị cập nhật hai lần.

### 21.5. Hai consumer xử lý duplicate đồng thời

1. Phát cùng event ID qua hai đường consumer test độc lập.
2. Cho hai DB transactions tranh cùng unique key.
3. Xác nhận chỉ một transaction thực hiện business update.
4. Xác nhận transaction còn lại nhận duplicate hoặc lỗi retryable phù hợp, không tạo effect kép.

### 21.6. DLT và replay

1. Cho event lỗi vĩnh viễn và hết retry.
2. Xác nhận record đến DLT theo policy.
3. Sửa dữ liệu/nguyên nhân trong môi trường thử nghiệm.
4. Replay event với cùng event ID.
5. Nếu nghiệp vụ trước đó chưa commit, xác nhận xử lý thành công.
6. Nếu side effect đã commit, xác nhận inbox không lặp effect.

Các kiểm thử tích hợp có thể dùng Testcontainers Kafka và PostgreSQL, hoặc hạ tầng thử nghiệm tương đương. Mục tiêu là xác nhận **trạng thái database và offset Kafka**, không chỉ số lần listener được gọi.

## 22. Khi nào Inbox pattern phù hợp?

Inbox đặc biệt phù hợp khi:

- Spring Kafka consumer cập nhật SQL database.
- Record có event ID ổn định.
- Nghiệp vụ không chấp nhận lặp side effect khi Kafka redeliver.
- Database có thể bảo đảm transaction và unique constraint.
- Ứng dụng cần replay/recovery từ Kafka hoặc DLT.
- Có thể xác định phạm vi deduplication theo consumer logic.

Inbox đơn giản có thể chưa đủ khi:

- Side effect chính là một HTTP call hoặc hệ thống không hỗ trợ idempotency.
- Một event cần điều phối nhiều resource không thể commit chung.
- Nghiệp vụ yêu cầu xử lý nghiêm ngặt theo version và có event đến sai thứ tự.
- Cần retry qua nhiều ngày nhưng không muốn giữ tất cả công việc trong listener container.
- Consumer xử lý task nền kéo dài và cần lease/recovery riêng.
- Inbox retention ngắn hơn mọi đường replay có thể xảy ra.

Trong những trường hợp đó, dùng inbox như một thành phần của kiến trúc rộng hơn: durable job queue, outbox, saga, business idempotency keys, state machine hoặc reconciliation, tùy yêu cầu.

## 23. Nguyên tắc triển khai production

1. **Mỗi event có ID ổn định**; xác định rõ scope của consumer.
2. **Dùng unique constraint trong database**, không chỉ kiểm tra tồn tại bằng SELECT.
3. **INSERT inbox và thay đổi domain trong cùng database transaction**.
4. Chỉ coi event đã PROCESSED khi transaction đó commit thành công.
5. Để listener trả về thành công **sau database commit**, rồi container mới commit offset.
6. Không acknowledge sớm và không nuốt exception khiến Kafka tiến offset sai.
7. Giữ service transactional ở Spring bean được gọi qua proxy và chọn đúng database transaction manager.
8. Thiết kế thêm business key nếu hai event IDs khác nhau có thể biểu thị cùng operation.
9. Tách xử lý lỗi vĩnh viễn sang DLT/recovery có xác nhận; không ghi inbox PROCESSED cho thất bại chưa được xử lý.
10. Nếu phát Kafka output sau DB update, cân nhắc kết hợp **inbox + outbox**.
11. Lưu inbox đủ lâu cho replay horizon, DLT và yêu cầu nghiệp vụ.
12. Theo dõi duplicate count, DB rollback, Kafka commit failures và consumer lag.
13. Kiểm thử crash sau DB commit nhưng trước Kafka offset commit và kiểm thử concurrent duplicate.

**Kết luận:** Inbox pattern không cố ngăn Kafka giao event nhiều lần. Nó khiến một event có định danh ổn định chỉ tạo side effect nghiệp vụ một lần trong phạm vi database transaction được bảo vệ bởi unique constraint. Trong Spring Kafka, thiết kế chuẩn là **commit database trước, commit offset sau**, chấp nhận redelivery và dùng inbox để biến redelivery thành thao tác an toàn. Khi có thêm Kafka output, HTTP side effect, replay dài hạn hoặc xử lý bất đồng bộ, cần mở rộng kiến trúc bằng outbox, idempotency và cơ chế recovery tương ứng.
