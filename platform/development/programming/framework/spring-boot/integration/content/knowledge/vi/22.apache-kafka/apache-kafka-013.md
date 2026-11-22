# Phân biệt giao dịch Kafka với giao dịch cơ sở dữ liệu

## 1. Bối cảnh của một luồng tích hợp Spring Boot

Trong một dịch vụ **Spring Boot Integration**, một yêu cầu HTTP có thể đồng thời tạo đơn hàng trong PostgreSQL, cập nhật cache và phát sự kiện `OrderCreated` qua Apache Kafka. Ở chiều ngược lại, một `@KafkaListener` có thể nhận sự kiện, ghi dữ liệu nghiệp vụ vào database, rồi xác nhận offset đã xử lý. Dù các bước diễn ra trong cùng một phương thức Java, chúng không mặc nhiên nằm trong **cùng một giao dịch nguyên tử**.

Ví dụ yêu cầu:

1. Nhận `POST /orders` với `orderId`.
2. Lưu đơn hàng vào bảng `purchase_orders`.
3. Phát sự kiện lên topic `orders.created` để dịch vụ khác xử lý.
4. Consumer của dịch vụ kho đọc sự kiện và trừ tồn kho.

Câu hỏi cần giải quyết không chỉ là “có `@Transactional` hay chưa”, mà là: **tài nguyên nào được transaction manager quản lý, thời điểm nào được commit, điều gì xảy ra nếu tiến trình chết giữa hai lần commit, và khi xử lý lại có gây trùng lặp không?**

~~~mermaid
flowchart LR
    HTTP["HTTP adapter"] --> Service["OrderService"]
    Service --> DB[("PostgreSQL")]
    Service --> Kafka[("Kafka topic")]
    Kafka --> Consumer["Inventory consumer"]
    Consumer --> Stock[("Inventory DB")]
    DB -. "DB transaction" .- Service
    Kafka -. "Kafka transaction" .- Service
~~~

**Phạm vi bài học:** phân biệt giao dịch database với giao dịch Kafka; hiểu giới hạn của bảo đảm exactly-once; chọn cách phối hợp giao dịch, xử lý lỗi và trùng lặp; kiểm thử và quan sát luồng tích hợp thực tế. Kafka và database có thể cùng tham gia một luồng nghiệp vụ, nhưng mỗi loại giao dịch có ranh giới riêng.

## 2. Giao dịch cơ sở dữ liệu bảo đảm điều gì?

Giao dịch của cơ sở dữ liệu quan hệ gom nhiều thao tác SQL thành một đơn vị nhất quán. Các thuộc tính **ACID** thường được hiểu như sau:

| Thuộc tính | Ý nghĩa đối với nghiệp vụ |
|---|---|
| **Atomicity** | Các thay đổi thuộc giao dịch cùng thành công hoặc bị rollback |
| **Consistency** | Ràng buộc dữ liệu và quy tắc database được duy trì qua commit |
| **Isolation** | Mức độ một giao dịch quan sát thay đổi chưa hoặc đã commit của giao dịch khác phụ thuộc mức isolation |
| **Durability** | Dữ liệu đã commit được database bảo tồn theo cam kết độ bền của hệ thống |

Ví dụ một giao dịch PostgreSQL:

~~~sql
BEGIN;

INSERT INTO purchase_orders (id, customer_id)
VALUES ('11111111-1111-1111-1111-111111111111', 'customer-42');

INSERT INTO outbox_events (event_id, aggregate_id, topic_name, payload)
VALUES (
    '22222222-2222-2222-2222-222222222222',
    '11111111-1111-1111-1111-111111111111',
    'orders.created',
    '{"eventId":"22222222-2222-2222-2222-222222222222","orderId":"11111111-1111-1111-1111-111111111111"}'
);

COMMIT;
~~~

Nếu lệnh thứ hai vi phạm một ràng buộc và giao dịch bị rollback, bản ghi đơn hàng cũng không được commit. Lợi ích của việc lưu `outbox_events` cùng transaction sẽ được giải thích ở phần sau.

Trong Spring, `@Transactional` chọn một `PlatformTransactionManager` (với JDBC/JPA) hoặc `ReactiveTransactionManager` (với R2DBC) và quản lý **các thao tác tham gia manager đó**. Ví dụ `DataSourceTransactionManager`/`JdbcTransactionManager` điều phối các thao tác JDBC phù hợp trên cùng database; `JpaTransactionManager` điều phối persistence context JPA; `R2dbcTransactionManager` điều phối kết nối R2DBC bằng reactive context.

**Giao dịch database không tự bao gồm** một lệnh gửi Kafka, một HTTP request sang dịch vụ khác hoặc cập nhật Redis thông thường. Rollback SQL sau khi Kafka đã publish thành công không thể “thu hồi” message chỉ bằng `ROLLBACK` database.

## 3. Giao dịch Kafka bảo đảm điều gì?

Kafka hỗ trợ **transactional producer** để gom các bản ghi gửi lên nhiều partition/topic của **cùng cụm Kafka** và, trong kịch bản xử lý rồi phát tiếp, gom cả việc ghi nhận offset đã tiêu thụ. Producer dùng một `transactional.id` và API giao dịch của Kafka:

~~~text
initTransactions()
beginTransaction()
send(topic_A, record_1)
send(topic_B, record_2)
[sendOffsetsToTransaction(offsets, consumerGroupMetadata) nếu consume-process-produce]
commitTransaction() hoặc abortTransaction()
~~~

Trong Spring Kafka, `KafkaTemplate` và listener container có cơ chế tích hợp việc quản lý giao dịch này; người viết ứng dụng thường không phải tự gọi trực tiếp mọi API producer. Các ý chính:

- **Commit Kafka:** các bản ghi thuộc transaction được xem là đã commit và hiển thị cho consumer cấu hình `isolation.level=read_committed`.
- **Abort Kafka:** những bản ghi thuộc transaction bị abort không được đưa tới consumer `read_committed`. Log Kafka có thể vẫn chứa bản ghi và marker liên quan; đây không phải thao tác xóa vật lý từng message.
- **Offset trong transaction:** với mô hình *consume → process → produce*, offset input được commit như một phần của cùng Kafka transaction với output. Nếu giao dịch abort, output không được công bố với `read_committed` và offset input không được commit trong transaction đó, nên có thể xử lý lại.
- **Idempotent producer:** giảm bản ghi trùng do producer retry trong phạm vi cơ chế idempotence của Kafka. Tính năng này **không loại bỏ** tác dụng phụ bị lặp tại database hay HTTP downstream.
- **Producer fencing:** các producer sử dụng cùng định danh giao dịch sẽ có cơ chế ngăn producer cũ tiếp tục commit sau khi phiên mới đã thay thế nó. `transactional.id` cần được thiết kế để không xung đột giữa những instance đang hoạt động hợp lệ.

Consumer mặc định không nhất thiết chờ transaction commit. Để dựa vào tính nguyên tử của Kafka transaction khi đọc, **consumer cần `read_committed`**. Với `read_uncommitted`, consumer có thể đọc bản ghi của transaction về sau bị abort; vì vậy không thể suy ra bảo đảm exactly-once ở phía nhận nếu bỏ qua cấu hình isolation.

### Exactly-once trong Kafka có phạm vi cụ thể

Ví dụ một processor đọc topic `orders.raw`, chuẩn hóa dữ liệu rồi ghi `orders.normalized`. Nếu cả đầu ra và offset đầu vào được commit trong **cùng Kafka transaction**, việc đọc lại sau lỗi có thể tránh phát lặp đầu ra đã commit trong đường đi Kafka này, với các điều kiện phù hợp về producer, consumer và transaction.

Ngược lại, nếu processor còn gọi API thanh toán hoặc ghi PostgreSQL, Kafka transaction **không thể rollback** các tác dụng phụ bên ngoài Kafka. Cụm từ *exactly-once semantics* của Kafka không có nghĩa là mọi hệ thống được gọi trong luồng đều xử lý nghiệp vụ đúng một lần.

~~~mermaid
flowchart TD
    Input[("Kafka input topic")] --> Processor["Consume / transform / produce"]
    Processor --> Output[("Kafka output topic")]
    Processor --> Offsets["Input offsets"]
    Tx["Một Kafka transaction"] -.-> Output
    Tx -.-> Offsets
    Processor --> SQL[("External database")]
    Tx -. "Không bao phủ" .-> SQL
~~~

## 4. So sánh trực tiếp hai loại giao dịch

| Tiêu chí | Database transaction | Kafka transaction |
|---|---|---|
| Tài nguyên chính | Bảng, hàng, chỉ mục và các thay đổi thuộc phạm vi DB transaction | Record được producer gửi và offset được đưa vào transaction trong Kafka |
| Điểm bắt đầu | `BEGIN`, transaction manager hoặc reactive transaction operator | Transactional producer / Kafka transaction manager |
| Điểm kết thúc | `COMMIT` hoặc `ROLLBACK` | `commitTransaction` hoặc `abortTransaction` |
| Tính nguyên tử | Các thao tác SQL tham gia cùng DB transaction | Các bản ghi Kafka và offset có tham gia cùng Kafka transaction |
| Cách quan sát | Phụ thuộc isolation của database, ví dụ `READ COMMITTED` | Consumer phải dùng `read_committed` để tránh đọc record bị abort |
| Xử lý lỗi | DB rollback thay đổi SQL chưa commit | Abort giao dịch Kafka, output không hiện ra với consumer `read_committed` |
| Điều phối bởi Spring | `JdbcTransactionManager`, `JpaTransactionManager`, `R2dbcTransactionManager` | `KafkaTransactionManager`, listener container hoặc `KafkaTemplate` |
| Không tự bảo đảm | Publish Kafka, gọi HTTP, cập nhật hệ khác | Commit PostgreSQL, gọi HTTP, thay đổi Redis |
| Trường hợp dùng | Cập nhật dữ liệu nghiệp vụ và bảng outbox nhất quán | Ghi atomically nhiều Kafka record; consume-process-produce trong Kafka |

Điểm quan trọng nhất: **hai transaction manager không tự hợp nhất thành một distributed transaction**. Thêm `@Transactional` hoặc bật Kafka transaction không làm commit của PostgreSQL và commit của Kafka xảy ra nguyên tử trong một quyết định duy nhất.

## 5. Vì sao “ghi database rồi gửi Kafka” có khoảng lỗi?

### 5.1. Commit database trước, Kafka sau

~~~mermaid
sequenceDiagram
    participant S as Spring Boot Service
    participant D as Database
    participant K as Kafka
    S->>D: BEGIN / INSERT order
    S->>D: COMMIT
    D-->>S: OK
    Note over S,K: Service có thể crash tại đây
    S->>K: Send OrderCreated
    K-->>S: Ack
~~~

Nếu service chết sau khi database đã commit nhưng trước khi Kafka nhận message, đơn hàng tồn tại mà không có sự kiện tương ứng. Retry toàn bộ HTTP request cũng chưa chắc an toàn: nếu request không có idempotency key, có thể sinh thêm đơn hàng.

### 5.2. Commit Kafka trước, database sau

~~~mermaid
sequenceDiagram
    participant S as Spring Boot Service
    participant K as Kafka
    participant D as Database
    S->>K: BEGIN / Send OrderCreated / COMMIT
    K-->>S: OK
    Note over S,D: Service có thể crash tại đây
    S->>D: BEGIN / INSERT order / COMMIT
~~~

Nếu Kafka đã commit nhưng database không commit, consumer có thể xử lý một sự kiện mô tả đơn hàng không tồn tại. Dùng Kafka transaction cho bước gửi cũng không làm thay đổi kết luận.

### 5.3. Bảng tình huống hai hệ thống commit độc lập

| DB commit | Kafka commit | Hệ quả nghiệp vụ |
|---|---|---|
| Thành công | Thành công | Đường đi mong muốn, nhưng consumer vẫn phải xử lý được retry/phát lặp |
| Thành công | Thất bại/chưa gửi | Database đã đổi, thiếu sự kiện downstream |
| Thất bại | Thành công | Event đã công bố nhưng thay đổi DB không tồn tại |
| Thất bại | Thất bại | Không có thay đổi đã commit ở hai hệ thống |

Trong lỗi mạng, client cũng có thể **không biết chắc** Kafka đã commit hay chưa dù nhận timeout. Gửi lại mù quáng có thể làm event lặp. Không nên xây giải pháp chỉ dựa trên giả định mọi lỗi trả về đều có nghĩa là message chưa được ghi.

Một số cấu hình Spring Kafka có thể đồng bộ việc thực thi giao dịch Kafka với giao dịch database theo thứ tự commit. Đây là cách phối hợp *best-effort one-phase commit*: vẫn có khoảng lỗi giữa hai resource, nên không đem lại tính nguyên tử tương đương một giao dịch duy nhất. Nếu một resource commit rồi resource thứ hai thất bại, phải thiết kế xử lý khôi phục.

## 6. Tình huống chỉ cần Kafka transaction: consume → process → produce

Giả sử một ứng dụng đọc `invoice.input` và ghi hai topic `invoice.validated`, `audit.events`. Nếu toàn bộ thao tác và offset cùng nằm trong Kafka transaction thì khi lỗi, consumer `read_committed` sẽ không thấy output bị abort.

Ví dụ cấu hình Spring Boot (đặt `INSTANCE_ID` duy nhất cho mỗi instance đang chạy đồng thời; giá trị `local` chỉ phù hợp một instance local):

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      acks: all
      transaction-id-prefix: "invoice-${INSTANCE_ID:local}-tx-"
      properties:
        enable.idempotence: true
    consumer:
      group-id: invoice-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Với Spring Boot/Spring Kafka có hỗ trợ transaction cho Kafka, cấu hình prefix này cho phép `KafkaTemplate` lấy transactional producer. Để mô phỏng **hai bản ghi output trong cùng Kafka transaction** từ một producer:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoiceEventPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;

    public InvoiceEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishPair(String invoiceId, String validatedJson, String auditJson) {
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send("invoice.validated", invoiceId, validatedJson);
            operations.send("audit.events", invoiceId, auditJson);
            return null;
        });
    }
}
~~~

Hai `send` được đưa vào cùng một Kafka transaction. Đây là ví dụ **produce → produce**. Nếu phương thức này được gọi từ một `@KafkaListener`, việc đưa **offset của record đã nhận** vào transaction còn phụ thuộc cấu hình listener container và Kafka transaction manager; chỉ gọi `executeInTransaction` riêng lẻ **không tự động** gom offset của consumer. Dùng cơ chế listener container transactional của Spring Kafka khi muốn đường đi consume-process-produce theo đúng bảo đảm EOS trong Kafka.

Cần phân biệt **producer idempotence** (ngăn trùng khi retry một số thao tác gửi ở producer) với **business idempotency** (không trừ tồn kho/hạch toán hai lần khi cùng một `eventId` được xử lý lại).

## 7. Khi cần nhất quán giữa database và Kafka: Transactional Outbox

**Transactional outbox** là giải pháp thường dùng khi một nghiệp vụ phải vừa commit database, vừa cuối cùng công bố sự kiện. Thay vì phụ thuộc vào hai commit độc lập trên đường request, service ghi **bản ghi nghiệp vụ và ý định phát sự kiện** vào **cùng một DB transaction**; tiến trình riêng chuyển bản ghi outbox sang Kafka.

~~~mermaid
flowchart LR
    HTTP["HTTP request"] --> S["OrderService"]
    S --> TX["DB transaction"]
    TX --> O[("purchase_orders")]
    TX --> X[("outbox_events")]
    X --> Relay["Outbox relay / CDC"]
    Relay --> Kafka[("Kafka")]
    Kafka --> C["Consumer"]
    C --> I[("Processed event ID + business change")]
~~~

### 7.1. Schema minh họa trên PostgreSQL

~~~sql
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    customer_id VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL REFERENCES purchase_orders(id),
    topic_name VARCHAR(180) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_events (created_at, event_id)
    WHERE published_at IS NULL;
~~~

`event_id` là định danh bất biến để consumer nhận biết sự kiện đã xử lý. `aggregate_id` có thể được dùng làm Kafka message key để giữ thứ tự trong cùng partition khi chiến lược partitioning nhất quán. Với nhiều producer và nhiều thay đổi đồng thời trên cùng aggregate, muốn bảo đảm thứ tự nghiệp vụ còn cần version/sequence và cơ chế đồng bộ ghi phù hợp; chỉ chọn cùng key chưa đủ.

### 7.2. Ghi đơn hàng và outbox trong cùng database transaction

Ví dụ Spring JDBC dưới đây cho thấy ranh giới DB rõ ràng. Giả định service đã cấu hình `JdbcTemplate` và một transaction manager JDBC có tên `dbTransactionManager` (có thể khai báo `JdbcTransactionManager` cho `DataSource`); tên bean cần khớp cấu hình thực tế.

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final JdbcTemplate jdbc;

    public OrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void createOrder(UUID orderId, UUID eventId,
                            String customerId, String eventJson) {
        jdbc.update("""
            INSERT INTO purchase_orders (id, customer_id)
            VALUES (?, ?)
            """, orderId, customerId);

        jdbc.update("""
            INSERT INTO outbox_events
                (event_id, aggregate_id, topic_name, payload)
            VALUES (?, ?, ?, ?)
            """, eventId, orderId, "orders.created", eventJson);
    }
}
~~~

Nếu thao tác insert outbox lỗi, transaction database rollback cả việc tạo đơn hàng. Nếu commit thành công, ý định gửi event đã được lưu bền vững cùng đơn hàng. `eventJson` nên bao gồm `eventId`, `aggregateId`, `eventType`, `schemaVersion` và dữ liệu nghiệp vụ phù hợp hợp đồng message; không lấy đối tượng entity tùy ý làm hợp đồng công khai.

Ranh giới trong ví dụ là **JDBC transaction**. Với một service dùng Spring Data R2DBC, cùng ý tưởng outbox vẫn áp dụng được, nhưng phải lưu hai bản ghi qua **cùng một reactive transaction** (ví dụ `TransactionalOperator` với `R2dbcTransactionManager`). Không trộn JDBC và R2DBC rồi giả định hai thao tác dùng chung transaction chỉ vì trỏ tới cùng database.

### 7.3. Outbox relay gửi message và đánh dấu đã phát

Một relay định kỳ hoặc công cụ change data capture (CDC) đọc các bản ghi outbox chưa phát:

~~~java
// Minh họa logic relay; phần lấy/claim batch được tách ra.
void publish(OutboxRow row) {
    kafkaTemplate
        .send(row.topicName(), row.aggregateId().toString(), row.payload())
        .join(); // Chờ broker xác nhận; chạy ở worker phù hợp.

    jdbcTemplate.update("""
        UPDATE outbox_events
           SET published_at = CURRENT_TIMESTAMP
         WHERE event_id = ?
           AND published_at IS NULL
        """, row.eventId());
}
~~~

`OutboxRow` là DTO của ứng dụng. Đoạn này minh họa trình tự **gửi thành công rồi đánh dấu**, không phải nguyên một relay production có thể copy để chạy. `KafkaTemplate.send(...)` ở Spring Kafka 3.x trở lên trả `CompletableFuture`; gọi `join()` là blocking, chỉ phù hợp worker/scheduler đã được bố trí cho I/O này, không gọi trên WebFlux event loop.

Nếu relay chết **sau khi Kafka xác nhận nhưng trước khi cập nhật `published_at`**, cùng event sẽ được gửi lại. Điều này **được dự kiến** trong mô hình outbox, nên consumer phải idempotent. Nếu đánh dấu đã phát trước khi gửi, lỗi ở Kafka sẽ khiến mất event.

Trong nhiều replica, relay còn phải xử lý cạnh tranh đọc một outbox row. Các lựa chọn thường gặp là claim bằng giao dịch ngắn với `FOR UPDATE SKIP LOCKED`, trạng thái lease có hạn sử dụng, hoặc dùng CDC như Debezium. Không giữ khóa SQL lâu trong lúc chờ broker nếu có thể thiết kế bước claim và publish tách riêng. Cần retry có backoff, giới hạn số lần thử, cảnh báo backlog và quy trình xử lý poison event.

Transactional outbox bảo đảm **đơn hàng và bản ghi ý định phát được ghi atomically trong database**. Relay thường mang ngữ nghĩa *at-least-once delivery* ra Kafka; nó **không** biến commit DB và Kafka thành một transaction chung.

## 8. Idempotent Consumer: chịu được phát lặp và xử lý lại

Ở phía nhận, Kafka có thể giao lại record sau rebalance, crash, timeout, retry hoặc relay gửi trùng. Nếu consumer đã trừ kho thành công nhưng chết trước khi offset được commit, record đó sẽ xuất hiện lại khi consumer chạy tiếp.

Một chiến lược là lưu định danh event đã xử lý trong **cùng database transaction** với thay đổi nghiệp vụ:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Thuật toán trong service nhận:

1. Parse và kiểm tra contract của message, lấy `eventId` ổn định.
2. Bắt đầu DB transaction.
3. Thử `INSERT INTO processed_events(consumer_name, event_id) VALUES (?, ?) ON CONFLICT DO NOTHING` (PostgreSQL).
4. Nếu số dòng được chèn bằng **1**, thực hiện thay đổi nghiệp vụ trong **cùng DB transaction**; nếu bằng **0**, coi đây là event đã xử lý và bỏ qua tác dụng phụ.
5. Commit database; **sau đó** mới cho listener container commit/ack offset tương ứng theo chế độ đã cấu hình.

Nếu thay đổi nghiệp vụ thất bại, transaction phải rollback cả bản ghi `processed_events`, để lần thử tiếp theo có thể xử lý lại. Nếu DB commit thành công nhưng offset chưa commit, Kafka phát lại và bản ghi `processed_events` ngăn trừ kho lần hai.

**Lưu ý với Spring:** nếu phương thức `@KafkaListener` vừa có `@Transactional` database vừa tự gọi `ack.acknowledge()` **bên trong phương thức**, ack có thể diễn ra trước khi interceptor transaction thực sự commit ở lúc phương thức trả về. Một mẫu rõ ràng hơn là listener gọi **một service khác** có `@Transactional`, đợi lời gọi service kết thúc thành công (đã commit), rồi mới ack. Nếu listener container có giao dịch Kafka riêng thì phải hiểu chính xác cơ chế commit offset của container; không coi một lời gọi `ack()` là DB/Kafka atomic commit.

Trong Spring Kafka, `@RetryableTopic`, dead-letter topic (DLT), error handler và retry policy giải quyết đường đi lỗi khác nhau; chúng không thay thế được idempotency trong database. Hãy phân biệt lỗi tạm thời (database unavailable), lỗi dữ liệu vĩnh viễn (sai schema) và lỗi nghiệp vụ (ví dụ giao dịch bị từ chối) để có chính sách retry/DLT phù hợp.

## 9. Chọn chiến lược theo yêu cầu tích hợp

| Nhu cầu | Hướng thiết kế phù hợp | Điều còn phải xử lý |
|---|---|---|
| Ghi atomically nhiều topic/partition Kafka | Kafka producer transaction | Consumer `read_committed`, lỗi/abort, instance fencing |
| Đọc Kafka, biến đổi, ghi lại Kafka, commit input offset | Kafka transaction với offset nằm trong transaction | Cấu hình listener container, retry và xử lý nguồn ngoài |
| Ghi database rồi chắc chắn có cơ hội phát event Kafka | Transactional outbox + relay/CDC | Publish lặp, backlog, claim đa worker, idempotent consumer |
| Đọc Kafka rồi cập nhật database | DB transaction + dedup `eventId`, commit offset sau DB commit | Replay khi crash, retry/DLT, offset và thứ tự |
| Nhiều dịch vụ và nhiều database cùng một quy trình | Saga/orchestration/choreography với bước bù trừ | Idempotency, timeout, trạng thái trung gian, quan sát liên dịch vụ |
| Tất cả nằm trong một database | DB transaction duy nhất | Isolation, khóa, deadlock, consistency |

Một số hệ thống đơn giản chấp nhận “ghi DB rồi publish trực tiếp và retry” với rủi ro rất thấp, nhưng cần **ghi nhận rõ** khoảng mất event sau DB commit và cách đối soát/khôi phục. Khi sự kiện là đầu vào quan trọng cho thanh toán, tồn kho, vận chuyển hoặc đồng bộ dữ liệu, outbox thường đáng giá vì loại bỏ khoảng mất ý định phát event ở phía service tạo dữ liệu.

### Giao dịch Kafka có thay thế outbox không?

Không. Kafka transaction có thể bảo đảm các bước **nội bộ Kafka**; outbox bảo đảm ghi **dữ liệu nghiệp vụ và ý định phát** vào cùng DB transaction. Hai cơ chế giải quyết hai phạm vi khác nhau và có thể cùng được dùng, tùy kiến trúc.

### Có nên dùng `@Transactional` trên toàn bộ listener?

Chỉ khi xác định **transaction manager nào** được chọn và **offset được commit lúc nào**. Với nhiều transaction manager, nên cấu hình tên rõ ràng. Một annotation không tự mở distributed transaction qua JDBC/JPA/R2DBC, Kafka, Redis và HTTP.

### Có thể có exactly-once cho thay đổi database không?

Có thể đạt **hiệu ứng nghiệp vụ đúng một lần** đối với một `eventId` bằng khóa unique, ghi nhận đã xử lý trong cùng DB transaction và xử lý lại an toàn. Tuy nhiên cơ chế truyền message vẫn có thể gửi/nhận lặp. Đối với tác dụng phụ ngoài database như gửi email hoặc gọi API thanh toán, cần idempotency key ở phía đối tác, trạng thái điều phối hoặc quy trình bù trừ tương ứng.

## 10. Kiểm thử các ranh giới giao dịch

Nên dùng **Testcontainers PostgreSQL + Kafka** hoặc môi trường tích hợp tương đương để chủ động gây lỗi, quan sát offset và dữ liệu thực thay vì chỉ mock `KafkaTemplate` và repository.

| Ca thử | Tình huống gây lỗi | Kết quả mong đợi |
|---|---|---|
| Kafka transaction commit | Gửi hai output record và commit | Consumer `read_committed` đọc được cả hai |
| Kafka transaction abort | Gửi output rồi abort | Consumer `read_committed` không nhận output bị abort |
| Kafka input offset | Xử lý input và output trong transaction, ép abort | Offset input chưa commit trong transaction; đọc lại được |
| DB rollback | Insert đơn hàng thành công, insert outbox thất bại | Cả đơn hàng và outbox đều rollback |
| Relay crash trước send | DB có outbox, relay chết trước khi publish | Sau restart vẫn có bản ghi chưa phát để retry |
| Relay crash sau Kafka ack | Message đã lên Kafka, DB chưa đánh dấu | Relay có thể phát lặp; consumer idempotent bảo vệ nghiệp vụ |
| Consumer crash sau DB commit | Đã thay đổi DB, offset chưa commit | Rebalance/retry không nhân đôi tác dụng phụ |
| Trùng eventId đồng thời | Hai consumer xử lý cùng event vào cùng DB | Unique constraint đảm bảo chỉ một DB transaction thực thi tác dụng phụ |
| Sai schema message | Thiếu field bắt buộc hoặc version không hỗ trợ | Không ghi dữ liệu sai; chuyển DLT/quarantine theo policy |
| Nhiều replica relay | Cùng quét bảng outbox | Claim/lease tránh gửi cạnh tranh không cần thiết; vẫn chấp nhận retry an toàn |

Trong test cho `read_committed`, không chỉ xác minh giá trị nhận được mà còn kiểm tra giao dịch bị abort **không hiển thị** với consumer thích hợp. Test consume-process-produce cần kiểm tra cả **offset đầu vào**; nếu chỉ kiểm tra output topic, chưa đủ khẳng định offset được đưa vào cùng Kafka transaction.

Không nên viết test mô phỏng hai commit bằng mock rồi kết luận hệ thống đã có atomic commit giữa PostgreSQL và Kafka; cần gây lỗi ở ranh giới thực và xác nhận khả năng khôi phục.

## 11. Quan sát và vận hành production

Để nhận biết một luồng tích hợp đang mắc lỗi giữa DB và Kafka, nên theo dõi đồng thời:

- **Database:** lỗi commit/rollback, deadlock, timeout, số row outbox chưa phát, tuổi bản ghi outbox cũ nhất và số lần retry.
- **Kafka producer:** lỗi send, timeout, transaction abort, lỗi fencing, độ trễ gửi/commit, retry, throughput theo topic.
- **Kafka consumer:** consumer lag, số lần rebalance, lỗi deserialize/validate contract, retry, DLT, tỉ lệ event trùng được loại bỏ.
- **Luồng nghiệp vụ:** `eventId`, `aggregateId`, `correlationId`/`traceId`, trạng thái order và thời gian từ DB commit đến Kafka publish.

Sử dụng cấu trúc log có định danh xuyên suốt các adapter, nhưng tránh ghi payload chứa dữ liệu nhạy cảm hoặc secret. Đặt cảnh báo khi **outbox backlog tăng liên tục** hay message ở DLT không được xử lý, vì HTTP request có thể đã thành công trong lúc sự kiện vẫn chưa tới downstream.

Giới hạn thời gian Kafka transaction thích hợp, hiểu cách Kafka fence producer cũ khi restart, và đặt transaction ID prefix tránh xung đột giữa các instance đang chạy đồng thời. Các quyền cần thiết trên topic, consumer group và transactional ID cũng phải được cấp tương ứng. Tác vụ publish từ outbox nên có cơ chế dừng an toàn và retry sau sự cố broker.

## 12. Những sai lầm cần tránh

1. **“Có `@Transactional` là DB và Kafka rollback cùng nhau.”** Sai: phải xác định transaction manager và resource thực sự tham gia.
2. **“Kafka exactly-once giúp consumer không bao giờ cập nhật DB hai lần.”** Sai: external DB không thuộc Kafka transaction; dùng dedup/idempotency tại DB.
3. **“Producer bật idempotence là mọi retry nghiệp vụ đều không trùng.”** Sai: producer idempotence không thay thế event ID và business idempotency.
4. **“Gửi Kafka thành công nghĩa là consumer đã xử lý.”** Sai: producer ack xác nhận kết quả ghi vào Kafka theo cấu hình; consumer xử lý và commit offset là bước khác.
5. **“Outbox bảo đảm Kafka nhận chính xác một lần.”** Sai: relay có thể publish lại sau crash; consumer phải chịu được ít nhất một lần giao.
6. **“Ack offset trong `@Transactional` database chắc chắn diễn ra sau DB commit.”** Không thể suy ra điều đó nếu ack thực hiện trước khi interceptor DB transaction commit.
7. **“Kafka commit rồi rollback SQL có thể xóa sự kiện Kafka.”** Sai: hai hệ thống có log và transaction manager riêng; cần quy trình khắc phục/bù trừ.

## 13. Câu hỏi tự kiểm tra

1. Nếu DB commit thành công rồi tiến trình chết ngay trước `KafkaTemplate.send`, hệ thống sẽ phục hồi event bằng cách nào?
2. Nếu Kafka transaction abort, consumer dùng `read_uncommitted` và `read_committed` có thể quan sát khác nhau ra sao?
3. Để đạt exactly-once trong luồng Kafka → Kafka, vì sao phải đưa offset input vào Kafka transaction?
4. Vì sao một outbox relay vẫn có thể gửi trùng, dù bản ghi outbox và đơn hàng đã được lưu atomically?
5. Nếu consumer đã giảm tồn kho rồi chết trước khi commit offset, cần bảng/khóa nào để tránh giảm lần hai?
6. Nếu ứng dụng có cả `KafkaTransactionManager` và `JpaTransactionManager`, phải xác định gì trước khi dùng `@Transactional`?
7. Khi thiết kế nhiều replica relay, làm sao tránh hai instance cùng claim một bản ghi và vẫn khôi phục sau khi một instance chết?

**Điểm cần nắm:** Giao dịch database bảo vệ các cập nhật dữ liệu trong database; giao dịch Kafka bảo vệ các record và offset được đưa vào cùng Kafka transaction. Phối hợp hai hệ thống đòi hỏi lựa chọn mô hình giao tiếp, giải quyết lỗi ở ranh giới commit, thiết kế idempotency và kiểm thử khả năng replay. Với luồng cần phát sự kiện sau commit database, **transactional outbox + idempotent consumer** là một lựa chọn phổ biến và dễ kiểm chứng hơn việc giả định có một transaction duy nhất cho cả hai.

### Tài liệu tham khảo

- [Apache Kafka — Design: Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-most-once, at-least-once và phạm vi exactly-once.
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs): `transactional.id`, `enable.idempotence`, `acks` và các thiết lập liên quan.
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): `KafkaTemplate`, listener container transactions, `KafkaTransactionManager` và phối hợp với transaction manager khác.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): phạm vi transaction manager và cơ chế `@Transactional`.
