# Idempotency khi phát lại CDC trong Debezium và Spring Integration

## 1. Vấn đề: nhận lại cùng một thay đổi có làm sai dữ liệu không?

Trong module **SPRING_INTEGRATION_ADAPTERS**, dữ liệu được trao đổi giữa các hệ thống thông qua inbound/outbound adapter, gateway, poller và `MessageChannel`. Một kiến trúc phổ biến dùng **Debezium** để thu nhận *Change Data Capture* (CDC) từ MySQL/PostgreSQL, xuất bản ghi lên Kafka, sau đó **Spring Integration Kafka inbound adapter** đưa chúng vào flow để cập nhật database báo cáo, bộ nhớ đệm, hệ thống tìm kiếm hoặc gọi dịch vụ ngoài.

Giả sử một đơn hàng được cập nhật thành `PAID`. Debezium gửi sự kiện vào Kafka, Spring Integration đọc sự kiện và ghi vào database đích. Ngay sau khi ghi xong, ứng dụng chết **trước khi consumer offset được commit**. Khi khởi động lại, consumer có thể đọc lại chính bản ghi Kafka đó.

Nếu handler chạy:

~~~text
SET orders.status = "PAID"
~~~

thì áp dụng lặp lại thường không đổi kết quả. Nhưng nếu handler chạy:

~~~text
account.balance = account.balance + 200000
sendPaymentConfirmationEmail()
~~~

thì cùng một sự kiện có thể **cộng tiền hai lần** và **gửi hai email**. Đó là lý do hệ thống CDC cần **idempotency**: xử lý lại một thay đổi không tạo thêm tác động nghiệp vụ ngoài kết quả mong muốn.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích tại sao CDC có thể phát lại ở Debezium, Kafka consumer, retry và dead-letter redrive.
2. Phân biệt *idempotent state update*, *deduplication* theo event ID và cơ chế giữ thứ tự/version.
3. Chọn khóa nhận diện phù hợp cho CDC row event, Debezium outbox event và các bản ghi đặc biệt như snapshot hoặc tombstone.
4. Viết mô hình **inbox/processed-event table** và cập nhật dữ liệu đích trong **cùng một database transaction**.
5. Thiết kế Spring Integration flow với acknowledgment đúng thời điểm, retry có giới hạn và side effect đáng tin cậy.
6. Kiểm thử crash, replay, duplicate với offset Kafka mới, out-of-order và delete để bảo đảm projection không sai.

## 2. Định nghĩa idempotency và hai lỗi thường bị đánh đồng

Một phép xử lý `f` là idempotent đối với sự kiện `e` nếu áp dụng `e` nhiều lần trên trạng thái đã xử lý `e` cho cùng kết quả như một lần:

\[
f(f(s, e), e) = f(s, e)
\]

Ví dụ cập nhật trạng thái:

~~~sql
UPDATE reporting.orders
SET status = 'PAID'
WHERE id = 42;
~~~

Nếu không có trigger/side effect khác, câu SQL này có **kết quả trạng thái** giống nhau khi chạy một hoặc nhiều lần. Tuy nhiên các phép xử lý sau thường **không idempotent**:

~~~sql
UPDATE reporting.accounts
SET balance = balance + 200000
WHERE id = 10;
~~~

~~~text
chargeCard(200000)
sendEmail("Payment received")
incrementMetric("completed_payment", 1)
~~~

Idempotency không chỉ là tránh **duplicate**; nó phải đi kèm cách xử lý **sự kiện cũ đến muộn**. Hai trường hợp khác nhau:

| Trường hợp | Ví dụ | Nguy cơ | Cơ chế phù hợp |
|---|---|---|---|
| **Duplicate**: cùng một thay đổi được xử lý hai lần | `E1: PAID`, sau đó lại `E1: PAID` | Ghi thừa, cộng dồn, gửi thông báo nhiều lần | Idempotent upsert, event ID và inbox/dedupe |
| **Out-of-order / stale replay**: thay đổi cũ đến sau thay đổi mới | `E1: PAID`, `E2: SHIPPED`, sau đó replay `E1` | Trạng thái bị lùi về `PAID` | Thứ tự theo key, version/sequence đáng tin cậy, reconciliation |

**Dedupe đúng một event ID không thay thế được thứ tự nghiệp vụ.** Ngược lại, chỉ dùng câu UPSERT để đạt idempotent state cũng chưa đủ nếu một bản ghi cũ được áp dụng sau bản ghi mới.

## 3. Vì sao Debezium và consumer có thể phát lại?

~~~mermaid
flowchart LR
    DB[(Database nguồn)] --> LOG[Transaction log]
    LOG --> DZ[Debezium connector]
    DZ --> K[(Kafka CDC topic)]
    K --> IN[Spring Integration<br/>Kafka inbound adapter]
    IN --> CH[MessageChannel]
    CH --> H[Service activator]
    H --> DEST[(Database đích)]
    DZ -. lưu source offset .-> OS[(Connect offset store)]
    IN -. commit consumer offset .-> CG[(Consumer group)]
~~~

Ba lớp tiến độ **độc lập**:

| Vị trí | Dùng để làm gì? | Khi chưa được ghi bền vững |
|---|---|---|
| Debezium **source offset** | Connector tiếp tục đọc database log từ checkpoint phù hợp | Connector có thể đọc lại và phát lại source change event |
| Kafka **topic-partition-offset** | Kafka định vị từng record đã được ghi vào partition | Bản ghi nguồn phát lại có thể trở thành **một Kafka record mới với offset khác** |
| Kafka **consumer group offset** | Consumer biết đã xác nhận tiêu thụ đến đâu | Consumer có thể nhận lại record Kafka đã xử lý |

### 3.1. Debezium source phát lại

Một luồng có thể xảy ra:

1. Kafka Connect lưu source offset ở vị trí `P100`.
2. Debezium đọc thay đổi `E101`, Kafka ghi record thành công ở offset `500`.
3. Connector chết trước khi checkpoint cho `E101` được flush.
4. Connector chạy lại từ trạng thái còn lưu và có thể phát `E101` lần nữa, lần này thành Kafka record offset `501`.

Hai record Kafka có **offset khác nhau** nhưng biểu diễn **cùng một thay đổi nghiệp vụ nguồn**. Vì vậy **chỉ dedupe bằng Kafka topic/partition/offset không loại được mọi duplicate do source replay**.

### 3.2. Consumer đọc lại cùng Kafka record

Một tình huống khác:

1. Spring Integration nhận record Kafka offset `500`.
2. Handler ghi thành công dữ liệu đích.
3. Ứng dụng dừng trước khi consumer group commit vị trí tiếp theo.
4. Khi restart, consumer có thể đọc lại record offset `500`.

Trường hợp này, khóa `(topic, partition, offset)` xác định được **chính record Kafka** trong phạm vi topic/partition, nhưng không phân biệt nó với một bản sao của source event được ghi ở Kafka offset khác.

### 3.3. Retry, dead-letter và snapshot

Ngoài crash, bản ghi có thể được phát lại bởi:

- **Retry** khi transformer, JDBC, HTTP gateway, JMS/AMQP adapter hoặc outbound handler gặp lỗi tạm thời.
- **Kafka rebalance** khi một member mất quyền sở hữu partition, còn tác vụ ghi đích đang chạy.
- **DLT/DLQ redrive** khi record bị cách ly được đưa lại về tuyến xử lý sau khi sửa lỗi.
- **Initial/incremental snapshot** phát lại trạng thái hàng qua `op="r"`, có thể tái xuất hiện khi chụp lại hoặc phục hồi snapshot.
- **Chuyển đổi topology**: nhiều consumer group hoặc pipeline cùng ghi vào một đích, hoặc thay đổi routing/partitioning.

Không phải các hiện tượng trên đều là “cùng một Kafka message”. Hãy xác định rõ **đối tượng cần dedupe** là một record broker, một source change event hay một sự kiện nghiệp vụ.

## 4. Đọc Debezium envelope trước khi quyết định cách dedupe

Một CDC row event minh họa:

**Kafka record key**

~~~json
{"id": 42}
~~~

**Kafka record value** (đã rút gọn):

~~~json
{
  "before": {"id": 42, "status": "NEW"},
  "after": {"id": 42, "status": "PAID"},
  "source": {
    "connector": "mysql",
    "name": "shop-cdc",
    "db": "sales",
    "table": "orders",
    "file": "mysql-bin.000032",
    "pos": 18420,
    "row": 0,
    "snapshot": "false"
  },
  "op": "u",
  "ts_ms": 1763892000000
}
~~~

Các trường và cách biểu diễn có thể khác theo Debezium connector/version, converter và SMT. Ví dụ này **không phải cấu trúc bắt buộc** của mọi source.

| Thông tin | Công dụng | Có dùng một mình làm ID sự kiện không? |
|---|---|---|
| Kafka key `{"id":42}` | Định danh bản ghi nghiệp vụ | **Không**: cùng đơn có thể thay đổi nhiều lần |
| `op` | `r`/`c`/`u`/`d` và các operation khác tùy connector | Không |
| `before`, `after` | Trạng thái hàng trước/sau; phục vụ upsert/delete | Không: hai thay đổi có thể có payload giống nhau |
| `source.file/pos/row`, `lsn` | Vị trí nguồn hỗ trợ truy vết và khôi phục | **Không tự mặc định** đủ duy nhất cho mọi row event |
| `source.name`/`db`/`table` | Xác định scope nguồn | Cần kết hợp với identity/sequence phù hợp |
| `ts_ms` | Thời điểm connector hoặc nguồn ghi nhận | Không: có thể trùng hoặc lệch đồng hồ |
| `transaction` | Thông tin giao dịch và thứ tự nếu connector hỗ trợ | Có ích, nhưng cấu trúc và độ bao phủ không giống nhau |
| Kafka `topic/partition/offset` | Định danh record broker trong partition | Đủ nhận diện **record Kafka**, không đủ nhận diện source event phát lại ở offset khác |

### Không có một “universal event ID” cho mọi Debezium row event

Với nhiều raw row CDC stream, Debezium cung cấp metadata nguồn chứ **không tự bảo đảm** một trường `eventId` toàn cục, ổn định, duy nhất cho mọi connector, mọi operation và mọi snapshot.

Ở MySQL, chỉ dùng `file + pos` có thể thiếu thông tin để phân biệt nhiều row event tại cùng khu vực log; ở PostgreSQL, `lsn` đơn lẻ có thể không đủ phân biệt mọi thay đổi hàng trong một transaction. Nếu tự xây khóa dựa trên `sourcePartition + vị trí log + transaction order + table + key`, phải xác minh **đúng hợp đồng connector và phiên bản**, kể cả khi snapshot hoặc primary key thay đổi.

Nếu cần **ID bền vững của sự kiện nghiệp vụ**, một **transactional outbox** có cột `event_id` thường dễ kiểm soát hơn việc cố ghép những metadata phụ thuộc database.

## 5. Các chiến lược idempotency và lúc nên dùng

| Chiến lược | Đầu vào phù hợp | Bảo đảm chính | Hạn chế |
|---|---|---|---|
| **Idempotent UPSERT** | Row CDC biểu diễn trạng thái hiện tại | Lặp cùng trạng thái không tạo bản ghi kép | Event cũ đến muộn vẫn có thể ghi đè event mới |
| **Idempotent DELETE** | `op="d"` theo khóa ổn định | Xóa lặp không gây lỗi hoặc side effect thêm | Nếu bản ghi cũ được replay sau delete, có thể tái tạo row |
| **Inbox / processed-event table** | Event có ID ổn định, duy nhất | Chỉ áp dụng một event ID một lần đối với consumer cụ thể | Cần unique constraint, transaction và retention hợp lý |
| **Version/sequence gating** | Nguồn có thứ tự tăng tin cậy theo từng entity | Ngăn event cũ ghi đè event mới | Version phải có quy tắc rõ, delete cần lưu marker |
| **Transactional outbox ở sink** | Có side effect hoặc gửi tiếp sang hệ thống khác | Ghi state và ý định phát tác vụ trong cùng DB transaction | Cần relay và consumer downstream idempotent |
| **Reconciliation** | Không có ID/version đủ tin cậy hoặc đã mất log | Khôi phục trạng thái đúng từ nguồn | Tốn tài nguyên; không tự dựng lại side effect lịch sử |

Không cần áp dụng mọi chiến lược một lúc. Với **projection trạng thái** đơn giản, upsert idempotent + xử lý tuần tự theo key có thể đủ trong phạm vi rõ ràng. Với **thanh toán, gửi email, tạo giao dịch sổ cái**, nên có event ID và giao dịch/inbox hoặc outbox phù hợp.

## 6. Trường hợp 1: row CDC để dựng projection trạng thái

Giả sử database nguồn `sales.orders` có các cột `id`, `status` và `version`. Ứng dụng nguồn tăng `version` mỗi khi trạng thái đơn thay đổi, theo **quy tắc tăng đơn điệu cho từng `id`**.

~~~text
order=42, version=7, status=NEW
order=42, version=8, status=PAID
order=42, version=9, status=SHIPPED
~~~

Nếu chỉ quan tâm trạng thái cuối, có thể dùng `(id, version)` để từ chối cập nhật cũ. Đây là **business version được nguồn quản lý**, không phải phép so sánh tùy tiện từ timestamp hoặc Kafka offset.

### 6.1. SQL UPSERT có điều kiện phiên bản

Bảng projection PostgreSQL:

~~~sql
CREATE TABLE reporting.orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(32),
    last_version BIGINT NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

UPSERT:

~~~sql
INSERT INTO reporting.orders AS current_row
    (id, status, last_version, is_deleted)
VALUES
    (42, 'PAID', 8, FALSE)
ON CONFLICT (id) DO UPDATE
SET status = EXCLUDED.status,
    last_version = EXCLUDED.last_version,
    is_deleted = EXCLUDED.is_deleted
WHERE current_row.last_version < EXCLUDED.last_version;
~~~

Nếu đã lưu `version=9, status=SHIPPED` thì replay `version=8` không làm thay đổi row. Nếu nhận lại `version=8` lần nữa, điều kiện `<` cũng ngăn cập nhật thừa.

**Điều kiện bắt buộc:** nguồn thực sự tăng version cho **mọi thay đổi liên quan**, không reset khi chuyển hệ thống hoặc tái tạo row; mỗi entity có khóa ổn định. Nếu hai message có cùng version nhưng payload khác nhau, đó là **vi phạm hợp đồng**, cần phát hiện và điều tra, không âm thầm chọn theo thời gian nhận.

### 6.2. DELETE và sự kiện cũ làm hồi sinh bản ghi

Nếu chỉ chạy `DELETE FROM reporting.orders WHERE id = 42`, sau đó replay một update cũ có thể **tạo lại** row. Với model có version nguồn và delete event mang version thích hợp, có thể ghi **delete marker**:

~~~sql
INSERT INTO reporting.orders AS current_row
    (id, status, last_version, is_deleted)
VALUES
    (42, NULL, 10, TRUE)
ON CONFLICT (id) DO UPDATE
SET status = EXCLUDED.status,
    last_version = EXCLUDED.last_version,
    is_deleted = EXCLUDED.is_deleted
WHERE current_row.last_version < EXCLUDED.last_version;
~~~

Khi version 10 đánh dấu đã xóa, replay version 8 hoặc 9 không thể hồi sinh đơn. **Cần phân biệt row CDC delete và event nghiệp vụ delete có version**: trong nhiều nguồn, `after=null` và `before` không tự chứa một “delete version” mới. Nếu ứng dụng không có version đáng tin cậy cho thao tác xóa, hãy giữ thứ tự xử lý theo key hoặc bổ sung hợp đồng nghiệp vụ/outbox; **không tự lấy `before.version` làm delete version mới** nếu nguồn chưa cam kết điều đó.

### 6.3. Snapshot có thể đưa lại trạng thái cũ

`op="r"` khi snapshot có thể xuất hiện lần nữa khi resnapshot hoặc incremental snapshot. Thay vì xem `r` là “tạo đơn mới”, hãy coi nó là dữ liệu **đồng bộ trạng thái**. Nếu dùng version, cần bảo đảm version của hàng snapshot nằm cùng hệ quy chiếu với version streaming.

Nếu không có business version, hãy giữ ordering ở tầng Debezium/consumer, xử lý chunk/snapshot theo cơ chế connector và thiết kế reconciliation để tránh một snapshot cũ ghi đè cập nhật mới. Snapshot **không đảm bảo** mọi record có một event ID nghiệp vụ riêng.

## 7. Trường hợp 2: Inbox với event ID từ transactional outbox

Khi nguồn tạo **sự kiện nghiệp vụ** như `OrderPaid`, thay vì chỉ phát toàn bộ raw row update, có thể ghi một record vào **outbox table trong cùng transaction** cập nhật đơn hàng:

~~~sql
BEGIN;

UPDATE sales.orders
SET status = 'PAID'
WHERE id = 42;

INSERT INTO sales.outbox_events
    (id, aggregatetype, aggregateid, type, payload)
VALUES (
    'bc7042bc-56fb-498c-b7be-df6b0f35008f',
    'orders',
    '42',
    'OrderPaid',
    '{"orderId":42,"status":"PAID","version":8}'::jsonb
);

COMMIT;
~~~

*SQL trên là ví dụ kiểu dữ liệu PostgreSQL; cần tạo bảng, ràng buộc và transaction phù hợp trước khi chạy.* Debezium outbox event router SMT có thể đưa cột `id` thành **event ID ở Kafka header** và `aggregateid` thành Kafka key; cần kiểm tra cấu hình và converter thực tế. **Event ID được tạo một lần trong transaction nguồn** và tồn tại qua những lần Debezium/Kafka phát lại record tương ứng.

### 7.1. Inbox bền vững ở database đích

Nếu Spring Integration áp dụng event vào database `reporting`, ta có thể lưu **vết đã xử lý** trong bảng inbox:

~~~sql
CREATE TABLE reporting.processed_cdc_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khóa (`consumer_name`, `event_id`) cho phép nhiều ứng dụng/luồng độc lập xử lý cùng event theo chính sách riêng. `event_id` phải có tính duy nhất đúng như hợp đồng nguồn; Kafka offset **không thay thế** cho ID này.

Quy trình cho **một event**:

~~~mermaid
sequenceDiagram
    participant K as Kafka CDC / outbox topic
    participant SI as Spring Integration handler
    participant DB as Reporting database
    K->>SI: eventId=E42
    SI->>DB: BEGIN
    SI->>DB: INSERT inbox(E42) ON CONFLICT DO NOTHING
    alt ID mới
        DB-->>SI: inserted = 1
        SI->>DB: Update projection
        SI->>DB: COMMIT inbox + projection
    else ID đã có
        DB-->>SI: inserted = 0
        SI->>DB: COMMIT không đổi projection
    end
    SI->>SI: ACK/commit consumer theo container policy
    Note over SI,DB: Nếu DB transaction rollback, inbox và projection đều rollback
~~~

Điểm mấu chốt là **ghi inbox và thay đổi projection trong cùng database transaction**. Nếu đánh dấu event đã xử lý ở một database khác hoặc trước khi nghiệp vụ commit, crash có thể dẫn tới tình trạng inbox nói “DONE” nhưng projection chưa cập nhật.

### 7.2. Java minh họa với Spring JDBC

Model dưới đây giả định consumer đã đọc được **stable event ID** từ Kafka header/outbox contract và một **version tăng đơn điệu theo `orderId`** từ payload. Nó **không thể dùng nguyên xi cho mọi raw Debezium envelope** vì row CDC thường không sẵn `eventId`.

~~~java
import java.util.UUID;

public record OrderStateEvent(
        UUID eventId,
        long orderId,
        long version,
        String status,
        boolean deleted) {
}
~~~

Handler transaction ở database đích:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {
    private static final String CONSUMER_NAME = "order-reporting-projection";
    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderStateEvent event) {
        int inserted = jdbc.update("""
                INSERT INTO reporting.processed_cdc_events
                    (consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """, CONSUMER_NAME, event.eventId());

        if (inserted == 0) {
            // Event ID này đã được xử lý và commit trước đây.
            return;
        }

        jdbc.update("""
                INSERT INTO reporting.orders AS current_row
                    (id, status, last_version, is_deleted)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE
                SET status = EXCLUDED.status,
                    last_version = EXCLUDED.last_version,
                    is_deleted = EXCLUDED.is_deleted
                WHERE current_row.last_version < EXCLUDED.last_version
                """,
                event.orderId(),
                event.deleted() ? null : event.status(),
                event.version(),
                event.deleted());
    }
}
~~~

**Phạm vi ví dụ:**

- Dùng PostgreSQL `INSERT ... ON CONFLICT`, Spring JDBC và Java text block; cần tạo cả hai bảng theo schema minh họa.
- `@Transactional` phải được kích hoạt với **transaction manager đúng DataSource** và được gọi qua Spring proxy; method cần là một ranh giới transaction thật, không tự gọi nội bộ rồi nghĩ annotation đã có hiệu lực.
- Nếu insert inbox thành công nhưng ghi projection ném exception, **cả hai lệnh rollback**. Lần retry sau sẽ được xử lý lại.
- Nếu inbox đã có `eventId`, method trả về thành công và không tạo thêm side effect.
- Cặp event ID + version giải quyết hai vấn đề khác nhau: **duplicate của cùng event** và **stale event đến sau**. Một nguồn không cung cấp version đáng tin cậy thì bỏ tầng version gating và phải thiết kế thứ tự/đối soát khác.
- Ví dụ chưa xác thực payload, tên event, signature, khoảng version và quy tắc nghiệp vụ; thực tế cần validate và có xử lý lỗi/metric.
- Nếu cùng `eventId` xuất hiện với payload **khác nhau**, cần báo lỗi hợp đồng thay vì âm thầm bỏ; có thể lưu checksum/version của payload bên cạnh inbox để kiểm tra.

### 7.3. Vì sao phải dùng unique constraint?

Một ứng dụng có thể chạy nhiều instance, hoặc một event được xử lý cùng lúc bởi hai worker do retry/rebalance. Mã:

~~~text
if (!exists(eventId)) {
    applyBusinessChange();
    insertProcessed(eventId);
}
~~~

**không an toàn khi chạy song song**: hai worker có thể đều thấy `!exists` và cùng thực hiện side effect. `PRIMARY KEY (consumer_name,event_id)` cùng lệnh `INSERT ... ON CONFLICT DO NOTHING` dùng sự đồng bộ hóa ở **database**, được thực thi trong transaction với thay đổi nghiệp vụ, nên có bảo đảm tốt hơn một `HashSet` hoặc khóa local trong một JVM.

## 8. Khi không có event ID ổn định: chọn chiến lược thực tế

Raw Debezium CDC của `orders` không nhất thiết chứa `eventId`. Khi đó có các hướng:

1. **Đồng bộ trạng thái:** dùng upsert/delete idempotent theo primary key; không tạo side effect từ sự kiện snapshot và kiểm soát ordering.
2. **Có cột version từ ứng dụng nguồn:** so sánh version theo entity trong cùng transaction đích và giữ delete marker.
3. **Tự xây event identity từ metadata nguồn:** chỉ khi đã kiểm chứng chính xác từng connector/version, cách xử lý snapshot và phân biệt các row trong cùng transaction; ghi rõ scope của ID.
4. **Cần sự kiện nghiệp vụ có ý nghĩa duy nhất:** phát từ transactional outbox với event ID do ứng dụng nguồn tạo.
5. **Không có ID/version/ordering đủ tin cậy:** giữ tuyến xử lý tuần tự, chặn redrive gây đảo thứ tự hoặc dùng reconciliation từ trạng thái nguồn; không tuyên bố đã giải quyết duplicate bằng một hash tùy tiện.

### Vì sao hash toàn bộ payload không phải event ID?

Hai cập nhật khác nhau có thể tạo **cùng trạng thái `after`**; chẳng hạn đổi `PAID → NEW → PAID` hoặc cập nhật cột ngoài phạm vi capture. Hash của `after` có thể giống nhau dù là hai sự kiện khác nhau. Ngược lại, cùng source event được serialize qua hai converter/schema version có thể có bytes khác nhau. Hash payload có thể hữu ích cho kiểm tra nhưng **không mặc định đại diện cho identity nghiệp vụ**.

### Vì sao `updated_at` không thay được version?

Timestamp có thể trùng nhau, dùng độ phân giải không đủ, lệch múi giờ/đồng hồ, hoặc bị cập nhật thủ công. Nếu nguồn cam kết timestamp tăng đơn điệu nghiêm ngặt theo từng entity thì có thể dùng trong phạm vi đã chứng minh, nhưng phần lớn hệ thống nên ưu tiên **sequence/version nguyên** được cập nhật trong cùng transaction.

## 9. Spring Integration: ranh giới ACK nằm ở đâu?

Một flow tham khảo:

~~~text
Debezium -> Kafka CDC/outbox topic
    -> Kafka message-driven inbound adapter
    -> cdcInboundChannel (DirectChannel)
    -> deserialize/normalize contract
    -> validate key, event ID, version, op
    -> @Transactional OrderProjectionService.apply(...)
    -> khi transaction DB đã commit
    -> xác nhận Kafka record theo ack mode của listener container
~~~

**Ý tưởng chính:** nếu handler ném exception và transaction rollback, adapter/container phải nhận được thông tin lỗi để retry hoặc xử lý theo chính sách; không được xác nhận tiêu thụ thành công chỉ vì message đã vào memory.

| Thành phần | Mối liên hệ với idempotency |
|---|---|
| `DirectChannel` | Flow đồng bộ trên caller thread; dễ ràng buộc việc hoàn tất DB trước khi listener xử lý record tiếp theo |
| `ExecutorChannel` hoặc `QueueChannel` | Bàn giao async có thể trả về trước khi DB commit; cần durability, ack protocol và ordering riêng |
| Service activator / transformer | Không được nuốt exception rồi báo thành công nếu nghiệp vụ chưa ghi an toàn |
| Spring Kafka listener container | Quản lý retry, ack, offset và DLT tùy chế độ; phải gắn đúng handler vào container mà adapter dùng |
| `errorChannel` | Mang `ErrorMessage` cho lỗi Spring Integration; không tự bảo đảm Kafka record đã lưu vào DLT |
| Outbound adapter/gateway | Gửi HTTP/JMS/AMQP có thể thành công rồi timeout; retry phải xét duplicate phía hệ thống nhận |

### 9.1. Manual ack và auto ack

Trong Spring Integration Kafka, cách lấy acknowledgment và thời điểm commit phụ thuộc **listener mode, ack mode, phiên bản adapter/container**. Không phải mọi `Message<?>` đều có sẵn header ACK để gọi bằng một dòng code cố định.

Ví dụ luồng logic:

~~~text
onMessage(record):
    try:
        event = decodeAndValidate(record)
        projectionService.apply(event)  # transaction phải kết thúc thành công
        acknowledgeAccordingToContainerPolicy(record)
    catch error:
        propagateToContainerOrDurableRecovery(record, error)
        # Không xác nhận record như đã xử lý thành công
~~~

Nếu adapter đang sử dụng auto/batch commit, cần xác minh rằng một handler đã hoàn tất nghĩa là gì; việc `@Transactional` kết thúc chỉ bảo đảm **transaction của DataSource**, không tự ràng buộc Kafka consumer offset với database commit thành một distributed transaction.

### 9.2. Đừng dựa vào exactly-once của Kafka cho database đích

Kafka transaction có thể phối hợp **record Kafka được xuất** và **offset Kafka được commit** trong một giao dịch Kafka. Nhưng một transaction Kafka không tự bao trùm JDBC write, HTTP call, email hoặc các hệ thống ngoài khác.

Khi xử lý Kafka → Spring Integration → SQL, idempotency tại database đích vẫn quan trọng, kể cả khi source/sink dùng các tùy chọn exactly-once trong phạm vi Kafka. Sự cố nằm giữa DB commit và Kafka commit vẫn dẫn tới khả năng đọc lại; **inbox trong cùng DB transaction** là giải pháp thường dùng để biến replay thành no-op về nghiệp vụ.

## 10. Side effect ngoài database: email, HTTP, JMS và AMQP

Nếu handler vừa cập nhật projection vừa gọi API thanh toán, gửi email hoặc phát message sang hệ thống thứ ba, hai việc này **không tự thuộc cùng một transaction**.

Ví dụ nguy hiểm:

~~~text
1. DB: markOrderPaid()       -> thành công
2. HTTP: sendInvoiceEmail()  -> server đã nhận và gửi
3. Mất kết nối trước response
4. Consumer retry toàn bộ
5. sendInvoiceEmail() lần 2
~~~

Ngay cả khi `sendInvoiceEmail()` trả timeout, không thể suy ra dịch vụ ngoài chưa xử lý. Với những API hỗ trợ, nên truyền **idempotency key** ổn định (ví dụ event ID được kiểm soát bởi nguồn) và yêu cầu phía nhận ghi nhớ kết quả theo key đó.

### 10.1. Transactional outbox ở hệ thống đích

Một mô hình khác là **ghi ý định phát tác vụ trong cùng DB transaction với inbox/projection**:

~~~mermaid
flowchart LR
    K[(Kafka CDC topic)] --> SI[Spring Integration handler]
    SI --> TX[(Một DB transaction<br/>inbox + projection + outbound outbox)]
    TX --> RELAY[Outbox relay / publisher]
    RELAY --> Q[(Kafka / JMS / AMQP)]
    Q --> CON[Downstream consumer<br/>idempotent]
    CON --> EXT[Email / HTTP / payment service]
~~~

Giả sử trong transaction áp dụng `OrderPaid`:

~~~sql
BEGIN;

-- 1. Ghi inbox theo event ID với unique constraint.
-- 2. Nếu event ID mới: cập nhật projection.
-- 3. Nếu event ID mới: ghi một hàng vào outbound_outbox
--    với business event ID / idempotency key ổn định.

COMMIT;
~~~

Relay có thể retry phát bản ghi outbox nên **người nhận tiếp theo vẫn phải idempotent**; transactional outbox giải quyết khoảng trống giữa **DB commit** và **ý định phát message**, không tự tạo lời hứa gửi HTTP/email đúng một lần nếu bên ngoài không hỗ trợ.

### 10.2. Nếu consumer làm phép cộng dồn

Với sự kiện nghiệp vụ `PaymentCaptured(amount=200000)`, không nên trực tiếp cộng:

~~~sql
UPDATE reporting.accounts
SET balance = balance + 200000
WHERE id = 10;
~~~

cho mỗi lần callback được gọi. Hãy đảm bảo thao tác cộng tiền chỉ chạy khi **claim một stable event ID mới** trong cùng transaction. Nếu ứng dụng ghi sổ cái, có thể dùng constraint `UNIQUE (payment_event_id)` trên bút toán và tạo tổng từ bút toán hợp lệ; cách này dễ kiểm tra và đối soát hơn việc chỉ thay đổi một số dư cộng dồn.

## 11. Ordering, DLT và replay: idempotent vẫn có thể sai

Giả sử:

~~~text
Kafka P1 offset 100: E1 -> order 42 = PAID
Kafka P1 offset 101: E2 -> order 42 = SHIPPED

E1 lỗi -> chuyển vào DLT
E2 xử lý xong -> projection = SHIPPED
Sau đó redrive E1 -> projection có thể về PAID
~~~

Nếu handler chỉ làm UPSERT theo key, lặp lại `E1` có thể không sinh thêm row nhưng vẫn **ghi đè trạng thái mới bằng trạng thái cũ**. Đây là lỗi **ordering**, khác với duplicate.

Các biện pháp:

- **Giữ thứ tự theo key/partition:** Kafka key ổn định, partitioner ổn định, handler không đẩy các event cùng key vào worker async không được điều phối.
- **Từ chối event cũ:** dùng version tăng đơn điệu từ nguồn; kiểm tra và cập nhật nguyên tử trong database.
- **Kiểm soát DLT redrive:** trước replay, xác định các event mới hơn đã được áp dụng chưa; có thể sửa lỗi cũ bằng reconciliation thay vì ghi lại state cũ.
- **Giữ delete marker:** một update cũ được replay không được hồi sinh một entity đã bị xóa ở version mới.
- **Tính tới rebalance:** worker cũ không được ghi đè sau khi partition chuyển cho worker mới; cần quản lý in-flight tasks/fencing/version.

Kafka bảo đảm thứ tự **trong một topic-partition**, không có thứ tự tổng quát giữa nhiều partition/topic. Thêm partition, đổi serialized key, thay partitioner hoặc routing có thể chuyển cùng entity sang partition khác, khiến các giả định cũ không còn đúng.

## 12. Delete event và Kafka tombstone

Một Debezium DELETE thường có envelope `op="d"`, `after=null`; connector còn có thể phát Kafka tombstone với **value thật sự là null**:

~~~text
DELETE:
  key   = {"id":42}
  value = {"op":"d","before":{"id":42,...},"after":null,...}

TOMBSTONE:
  key   = {"id":42}
  value = null
~~~

**Delete event** báo rằng hàng nguồn đã bị xóa. **Tombstone** phục vụ ngữ nghĩa xóa khóa trên compacted Kafka topic; nó không phải một envelope chứa `op="d"` và không tự được áp dụng như lệnh xóa nghiệp vụ thứ hai.

Trong Spring Integration Kafka, deserializer/converter có thể biểu diễn value null bằng sentinel như `KafkaNull`. Do đó phải nhận diện tombstone **trước khi parse JSON**, theo đúng API/adapter version.

Các trường hợp idempotency cần kiểm tra:

1. DELETE nhận hai lần: xóa lại phải an toàn, không gửi hai tác vụ hủy đơn.
2. Tombstone theo sau DELETE: không xử lý thành hai lệnh hoàn tiền.
3. Event update cũ phát lại **sau** DELETE: cần thứ tự/version hoặc reconciliation, nhất là khi projection đã xóa vật lý và mất dấu version.
4. Primary key đổi: connector có thể phát delete theo key cũ và create theo key mới; hai key có thể thuộc hai partition khác nhau, cần xử lý hợp đồng của connector.

## 13. Lỗi, retry và redrive nên gắn với chiến lược dedupe

Một pipeline có thể dùng `DefaultErrorHandler`/`DeadLetterPublishingRecoverer` của Spring Kafka hoặc error channel/adapter tương ứng để đưa record hỏng vào DLT. Nhưng **đưa vào DLT không có nghĩa ứng dụng đã áp dụng nghiệp vụ**.

| Tình huống | Cách xử lý khuyến nghị |
|---|---|
| DB đích timeout khi ghi inbox/projection | Rollback transaction; retry có backoff; cùng event ID sẽ xử lý lại an toàn |
| DB commit thành công nhưng ACK Kafka thất bại | Consumer đọc lại; inbox unique constraint phát hiện event ID đã xử lý |
| DLT chứa record cũ hơn state hiện tại | Kiểm tra version/ordering, không replay mù; có thể reconciliation |
| Một consumer gửi email xong rồi timeout | Phía nhận phải hỗ trợ idempotency key hoặc có outbox/dedupe riêng |
| Debezium source offset cũ, sự kiện được phát lần hai với Kafka offset khác | Dedupe theo event ID nguồn, hoặc dùng cập nhật state idempotent và thứ tự đúng; Kafka offset không đủ |
| Schema thay đổi, payload cũ được replay | Consumer phải hỗ trợ old/new event contract hoặc có migration/converter phiên bản |
| Source log không còn, connector không resume được | Không thể sửa chỉ bằng inbox/DLT; cần quy trình resnapshot và đối soát |
| Bảng thiếu primary key | Không có identity ổn định để upsert/delete đơn giản; cần thiết kế khóa nguồn phù hợp |

### Retention của inbox

Xóa dấu `processed_cdc_events` quá sớm có thể khiến một event lâu ngày bị redrive rồi **được xử lý lại như mới**. Thời gian giữ inbox phải phù hợp với Kafka retention, DLT retention, thời gian downtime, snapshot/replay và chính sách lưu trữ của nghiệp vụ.

Nếu muốn dọn inbox, cần một chiến lược thay thế: snapshot/reconciliation, TTL có tính toán, version watermark theo entity hoặc chính sách chỉ replay trong cửa sổ đã biết. Với sự kiện có side effect tài chính, nhiều trường hợp cần giữ identity giao dịch lâu dài theo chính sách kế toán/thanh toán.

### Lỗi sau khi đã commit

Tránh gọi một hệ thống ngoài **sau DB commit nhưng trong cùng handler** rồi ném exception trở lại như thể toàn bộ nghiệp vụ có thể rollback. DB đã commit không thể tự động rollback vì SMTP/HTTP timeout. Tách side effect qua outbound outbox hoặc kiểm soát idempotency key ở hệ thống đích.

## 14. Kiểm thử theo failure timeline

Để đánh giá đúng idempotency, hãy kiểm tra **tác động tới database** và **side effect**, không chỉ xem Kafka consumer đã tăng offset.

| Thử nghiệm | Điểm gây lỗi | Kết quả mong muốn |
|---|---|---|
| 1. Duplicate Kafka record | Gửi lại đúng `(topic,partition,offset)` | Projection và side effect giữ nguyên |
| 2. Duplicate Debezium source | Cùng source event có Kafka offset **mới** | Không ghi thêm nghiệp vụ nhờ event ID/state idempotency |
| 3. Crash trước DB commit | Inbox/projection transaction chưa commit | Không có partial effect; retry xử lý được |
| 4. Crash sau DB commit, trước ACK | Đã ghi đích nhưng chưa commit consumer offset | Retry nhận lại, inbox cho no-op |
| 5. Parallel duplicate | Hai worker cùng nhận một `eventId` | Unique constraint bảo vệ; chỉ một transaction áp dụng |
| 6. Out-of-order | `version=9` trước `version=8` | Giữ trạng thái version 9, không bị lùi |
| 7. Delete rồi replay update | Delete version 10, update cũ version 8 | Không hồi sinh entity |
| 8. Snapshot/re-snapshot | `op="r"` được nhận lại | Chỉ đồng bộ trạng thái, không gửi thông báo tạo mới |
| 9. DLT redrive | Sự kiện cũ có state mới hơn đã áp dụng | Không ghi đè dữ liệu mới; có audit kết quả redrive |
| 10. HTTP/email timeout sau thành công | Downstream đã xử lý nhưng response mất | Idempotency key hoặc outbound outbox ngăn side effect kép |
| 11. Đổi schema | Event trước/sau DDL cùng tồn tại | Handler nhận đúng cả hai contract theo chính sách |
| 12. Mất source log | Không thể đọc lại đoạn thay đổi | Cảnh báo và quy trình đối soát/resnapshot; không giả định inbox sửa được |

### 14.1. Diễn tập crash giữa hai bước

Với inbox transaction:

~~~text
BEGIN
  INSERT processed_cdc_events(event_id = E42) -> thành công
  UPDATE reporting.orders                 -> exception
ROLLBACK
~~~

Sau rollback, inbox **không có E42**, projection chưa ghi; retry E42 sẽ chạy lại an toàn.

Nếu đặt `INSERT processed_cdc_events` trong transaction độc lập và commit trước, retry có thể thấy E42 đã xử lý và **bỏ qua UPDATE chưa từng thành công**. Đây là lỗi thiết kế nghiêm trọng.

### 14.2. Những chỉ số nên quan sát

- Số **duplicate event ID** phát hiện bởi unique constraint, phân loại theo source/consumer.
- Tốc độ Kafka CDC, consumer lag theo partition và số lần retry/rebalance.
- Số lần event stale bị version gating từ chối.
- Thời gian xử lý, rollback, database deadlock và lỗi commit.
- DLQ/DLT volume, tuổi record lâu nhất, số lần redrive và số record chưa đối soát.
- Sai lệch giữa database nguồn và projection về số lượng, khóa và trạng thái.
- Số side effect gửi email/payment/API theo event ID để phát hiện xử lý lặp.

Đừng coi `duplicate_count = 0` là điều kiện duy nhất để đánh giá an toàn. Có thể chưa có duplicate được phát hiện vì consumer đã **bỏ mất record** hoặc do hệ thống không có event ID. Luôn kết hợp đối soát dữ liệu nghiệp vụ.

## 15. Tình huống tổng hợp: đơn hàng thanh toán và gửi hóa đơn

Hệ thống nguồn MySQL lưu đơn hàng và transactional outbox. Debezium phát `OrderPaid(eventId=E42, orderId=42, version=8)` ra Kafka. Spring Integration nhận rồi cần cập nhật projection và phát yêu cầu gửi hóa đơn.

**Thiết kế được đề xuất:**

1. Producer nguồn ghi thay đổi `orders` và outbox `E42` trong cùng transaction.
2. Debezium outbox event router phát event với key `orderId` và stable ID `E42` (thường ở header khi dùng SMT mặc định).
3. Spring Integration inbound adapter nhận record, validate event ID, key, version và đưa tới `DirectChannel` với handler transaction.
4. Handler insert inbox `E42`, cập nhật projection nếu version mới hơn và ghi **outbound outbox** để yêu cầu gửi hóa đơn, tất cả trong **một database transaction**.
5. Sau DB transaction commit, consumer xác nhận record theo chính sách listener container.
6. Relay phát yêu cầu hóa đơn từ outbound outbox; consumer gửi hóa đơn dedupe theo `E42` hoặc theo khóa yêu cầu hóa đơn ổn định.
7. Nếu bị crash ở bất kỳ đoạn nào, retry có thể xảy ra nhưng không tạo nhiều invoice/payment operation cho cùng event nghiệp vụ.

Nếu `OrderPaid` bị redrive sau `OrderShipped`, version gating bảo đảm projection không bị lùi, còn inbox ngăn gửi lại hóa đơn của `E42`. Hai tầng bảo vệ xử lý **hai tình huống khác nhau**.

### Một điều kiện kinh doanh cần xác định

Nếu ở source có thể phát **hai sự kiện `OrderPaid` khác nhau cùng `orderId`** (ví dụ thanh toán chia đợt), không được dedupe bằng duy nhất `orderId`: như vậy có thể bỏ mất nghiệp vụ hợp lệ. Mỗi lần thanh toán cần identity cụ thể của **payment capture/transaction**, còn `orderId` có thể tiếp tục làm khóa partition để bảo đảm thứ tự theo đơn.

## 16. Bài tập thực hành

### Bài 1 — Phân biệt duplicate và stale

Một projection lưu `orders.id=42, version=9, status=SHIPPED`. Consumer nhận:

~~~text
A: eventId=E8, orderId=42, version=8, status=PAID
B: eventId=E9, orderId=42, version=9, status=SHIPPED
C: eventId=E9, orderId=42, version=9, status=SHIPPED
~~~

Hãy chỉ ra record nào là stale, record nào là duplicate nếu B đã được xử lý, và vì sao chỉ dùng `WHERE id=42` là chưa đủ.

### Bài 2 — Điểm commit

Hai phương án:

**A**

~~~text
INSERT inbox -> COMMIT
UPDATE projection -> COMMIT
ACK Kafka
~~~

**B**

~~~text
BEGIN
INSERT inbox
UPDATE projection
COMMIT
ACK Kafka
~~~

Phương án nào an toàn hơn trước crash giữa hai lệnh SQL? Giải thích kết quả khi UPDATE thất bại.

### Bài 3 — Email bị gửi hai lần

Handler đã dùng inbox transaction và lưu `OrderPaid` đúng một lần nhưng gọi email service sau DB commit. Email service thực sự đã gửi, nhưng response bị timeout khiến job retry. Hãy đề xuất cách xử lý để hóa đơn không phát hai lần.

### Bài 4 — Chọn khóa dedupe

Một hệ thống nhìn thấy hai CDC record cùng business key `orders.id=42` nhưng có hai transaction riêng: một cập nhật `status=PAID`, một cập nhật `status=SHIPPED`. Có nên dùng `orders.id` làm inbox key? Nếu không, làm sao để ghi nhận cả hai lần thay đổi?

<details>
<summary>Gợi ý lời giải</summary>

1. A là sự kiện cũ (`version=8`), B là event version 9, C là duplicate của B theo `eventId=E9`. UPSERT thiếu version có thể làm trạng thái lùi về PAID khi áp dụng A.
2. B an toàn hơn: inbox và projection commit hoặc rollback cùng nhau. Với A, crash sau inbox commit nhưng trước projection có thể làm retry tưởng event đã được xử lý.
3. Dùng outbound outbox, mỗi yêu cầu email có idempotency key ổn định; email worker/provider dedupe theo key đó và giữ kết quả bền vững. Trường hợp provider không hỗ trợ dedupe vẫn cần chính sách kiểm tra trạng thái gửi và chấp nhận giới hạn của tích hợp.
4. Không. `orderId` định danh entity chứ không định danh **mỗi thay đổi**. Cần event ID riêng từ transactional outbox hoặc identity sự kiện nguồn được thiết kế/chứng minh đúng; giữ `orderId` làm partition/upsert key.

</details>

## 17. Checklist triển khai

- [ ] Xác định rõ cần bảo vệ **projection state**, **sổ cái giao dịch**, **email/API side effect** hay cả ba.
- [ ] Hiểu source offset Debezium, Kafka topic offset và consumer group offset có vai trò khác nhau.
- [ ] Xác định **event ID ổn định** nếu cần dedupe event; không mặc định raw Debezium row event có sẵn global event ID.
- [ ] Phân biệt entity key, event ID, version/order và Kafka topic-partition-offset.
- [ ] Với inbox, dùng unique constraint và thay đổi dữ liệu đích **trong cùng DB transaction**.
- [ ] Với UPSERT, xác minh replay event cũ không ghi đè state mới; có version tin cậy hoặc ordering rõ ràng.
- [ ] Với DELETE, xem xét delete marker, primary-key change và Kafka tombstone.
- [ ] Với snapshot `op="r"`, không chạy side effect tạo mới không phù hợp.
- [ ] Thiết kế Spring Integration channel và handler để ACK/commit sau khi đã ghi đích an toàn.
- [ ] Khi dùng async channel, thiết kế bàn giao bền vững và cơ chế checkpoint riêng trước khi ACK.
- [ ] Có retry, DLT/redrive, idempotency key cho HTTP/JMS/AMQP/email và outbound outbox khi cần.
- [ ] Đánh giá retention của inbox, Kafka topic, DLT và thời gian có thể replay.
- [ ] Kiểm thử duplicate Kafka record, source replay với offset Kafka mới, crash trước/sau DB commit và stale event.
- [ ] Đối soát dữ liệu nguồn/đích và quan sát duplicate/stale/retry/DLT bằng metric.

## 18. Tài liệu tham khảo

- [Debezium Frequently Asked Questions](https://debezium.io/documentation/faq/): giải thích tình huống source và consumer phát lại sau crash, lý do consumer phải chịu duplicate.
- [Debezium Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): cấu trúc outbox, event ID, aggregate key và điều hướng topic.
- [Spring Integration — Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): message-driven adapter, listener configuration, retry/recovery và MessageChannel.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): phạm vi transaction Kafka trong đọc–xử lý–xuất record Kafka và offset.
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): phối hợp Kafka transaction với Spring transaction management và database transaction.

**Ghi nhớ:** Debezium và Kafka consumer có thể phát lại thay đổi sau crash, timeout hoặc retry. **Idempotency của state**, **dedupe theo event ID** và **kiểm soát version/thứ tự** giải quyết các rủi ro khác nhau. Trong Spring Integration, hãy đặt ranh giới transaction tại thao tác nghiệp vụ thật, commit offset sau khi có kết quả bền vững, và bảo vệ cả side effect ngoài database. Chỉ khi đó cùng một CDC event xuất hiện nhiều lần mới không khiến dữ liệu hoặc tác động nghiệp vụ bị nhân đôi.
