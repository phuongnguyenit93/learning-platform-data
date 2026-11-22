# Outbox, tính lũy đẳng (idempotency) và đồng bộ dữ liệu theo sự kiện

Trong hệ thống phân tán, một nghiệp vụ thường cần cập nhật dữ liệu trong Oracle Database và đồng thời thông báo thay đổi đó cho hệ thống khác. Ví dụ, khi đơn hàng được xác nhận, dịch vụ Order phải cập nhật trạng thái đơn hàng và phát một sự kiện để dịch vụ Inventory giữ hàng, dịch vụ Billing tạo khoản phải thu hoặc hệ thống phân tích cập nhật dữ liệu.

Nếu ứng dụng thực hiện hai thao tác độc lập — commit vào database rồi gửi message lên broker — sẽ xuất hiện một khoảng thời gian mà một thao tác thành công còn thao tác kia thất bại. Database có thể đã commit nhưng message chưa được gửi; hoặc message đã gửi nhưng transaction database rollback. Đây là vấn đề dual write.

**Transactional Outbox** giải quyết dual write bằng cách ghi thay đổi nghiệp vụ và một bản ghi sự kiện vào cùng một transaction database. Một tiến trình relay đọc outbox đã commit rồi chuyển sự kiện tới message broker hoặc hệ thống đích. Do relay có thể gửi lại khi gặp lỗi, consumer cần xử lý sự kiện theo cách **idempotent**: nhận cùng một sự kiện nhiều lần vẫn chỉ tạo ra một hiệu ứng nghiệp vụ.

Ba ý tưởng này gắn chặt với nhau:

- **Outbox:** bảo đảm thay đổi nghiệp vụ và ý định phát sự kiện được commit hoặc rollback cùng nhau.
- **Idempotency:** bảo đảm xử lý lặp không nhân đôi hiệu ứng.
- **Event-based synchronization:** dùng các sự kiện nghiệp vụ đã commit để cập nhật những hệ thống khác một cách bất đồng bộ.

Outbox không tự bảo đảm message chỉ được gửi một lần, không thay thế transaction phân tán cho mọi nghiệp vụ và không làm các hệ thống nhất quán tức thời. Nó tạo nền tảng tin cậy cho mô hình giao nhận ít nhất một lần (at-least-once), sau đó dùng idempotency, ordering, retry và reconciliation để đạt kết quả nhất quán.

## 1. Bài toán dual write trong hệ thống phân tán

Giả sử dịch vụ Order lưu đơn hàng trong Oracle và gửi sự kiện OrderCreated tới Kafka hoặc một message broker khác.

Một luồng đơn giản thường được viết như sau:

~~~text
1. INSERT đơn hàng vào Oracle
2. COMMIT
3. Gửi OrderCreated lên broker
~~~

Nếu database commit thành công nhưng tiến trình ứng dụng dừng trước bước 3, đơn hàng tồn tại nhưng không hệ thống nào nhận được sự kiện. Inventory có thể không giữ hàng, Billing không tạo khoản phải thu và hệ thống tìm kiếm không hiển thị đơn hàng.

Nếu đổi thứ tự:

~~~text
1. Gửi OrderCreated lên broker
2. INSERT đơn hàng vào Oracle
3. COMMIT
~~~

Message có thể được consumer xử lý trong khi transaction database chưa commit hoặc cuối cùng rollback. Hệ thống đích tin rằng đơn hàng tồn tại dù database nguồn không có đơn hàng đó.

Một transaction local của Oracle chỉ kiểm soát các thay đổi thuộc transaction database đó. Nó không tự atomically commit cùng một message broker bên ngoài, trừ khi hệ thống dùng một cơ chế transaction phân tán được hỗ trợ và cấu hình đúng.

### 1.1 Các cửa sổ lỗi của dual write

| Thời điểm xảy ra lỗi | Trạng thái có thể còn lại |
|---|---|
| Trước khi database commit | Không có thay đổi nghiệp vụ; message chưa được gửi nếu gửi sau commit |
| Sau commit, trước khi gửi message | Dữ liệu đã lưu nhưng không có sự kiện |
| Trong lúc gửi, không biết broker đã nhận hay chưa | Ứng dụng không thể biết có nên gửi lại hay không |
| Broker nhận message, ứng dụng mất kết nối trước khi nhận ACK | Có thể gửi lại và tạo duplicate |
| Gửi message trước, database rollback | Consumer nhận sự kiện cho thay đổi không tồn tại |

Đặc biệt, timeout khi publish không chứng minh broker chưa nhận message. Broker có thể đã lưu message và gửi ACK nhưng ACK bị mất trên đường truyền. Retry là cần thiết để tránh mất message, nhưng retry có thể tạo duplicate.

### 1.2 Vì sao không chỉ dùng try/catch?

Mã xử lý lỗi có thể thử gửi lại khi gặp exception, nhưng không giải quyết được mọi tình huống:

- Process có thể bị kill ngay sau commit.
- Máy chủ có thể mất điện.
- Network timeout khiến kết quả publish không rõ.
- Broker có thể tạm thời không khả dụng trong thời gian dài.
- Deployment hoặc restart có thể làm mất trạng thái retry trong memory.
- Nhiều instance ứng dụng có thể cùng chạy và cần phối hợp.

Muốn phục hồi sau khi process biến mất, ý định phát sự kiện phải được lưu bền vững cùng transaction nghiệp vụ. Outbox cung cấp điểm lưu bền vững đó.

## 2. Transactional Outbox là gì?

Transactional Outbox là một bảng hoặc cấu trúc lưu các message cần phát đi. Ứng dụng ghi dữ liệu nghiệp vụ và ghi event vào outbox trong cùng một transaction Oracle.

Luồng cơ bản:

~~~text
Client
  |
  v
Order Service
  |
  | BEGIN TRANSACTION
  | UPDATE/INSERT business tables
  | INSERT event into OUTBOX
  | COMMIT
  v
Oracle Database
  |                    |
  | business data      | committed outbox event
  |                    |
  +--------------------+
             |
             v
       Outbox Relay
             |
             v
       Message Broker
             |
       +-----+------+
       |            |
       v            v
   Inventory      Billing
    Consumer      Consumer
       |            |
       v            v
   Local DB       Local DB
~~~

Nếu transaction rollback, cả dữ liệu nghiệp vụ và outbox event đều rollback. Nếu commit thành công, cả hai cùng tồn tại. Relay có thể dừng hoặc broker có thể tạm thời unavailable; event vẫn nằm trong outbox để được gửi sau.

### 2.1 Bảo đảm mà outbox cung cấp

Outbox giải quyết tính nguyên tử ở phía database:

- Business update thành công thì event record được lưu cùng transaction.
- Business update rollback thì event record cũng không tồn tại.
- Relay có thể tiếp tục sau restart vì event được lưu bền vững.
- Có thể theo dõi event chưa gửi, đang gửi, đã gửi hoặc cần xử lý lại.

Outbox không bảo đảm:

- Broker chỉ nhận một message duy nhất.
- Consumer chỉ chạy một lần.
- Các hệ thống đích cập nhật đồng thời với database nguồn.
- Message được xử lý đúng thứ tự nếu có nhiều relay worker.
- Sự kiện cũ luôn được giữ vô thời hạn.
- Một consumer lỗi sẽ tự động được sửa mà không cần vận hành.

### 2.2 Outbox và transaction database

Điều kiện quan trọng nhất là business data và outbox record phải được ghi trong **cùng một transaction trên cùng database transaction boundary**.

Ví dụ sai:

~~~text
Transaction A:
  UPDATE orders
  COMMIT

Transaction B:
  INSERT outbox_event
  COMMIT
~~~

Nếu process dừng giữa hai transaction, dual write vẫn còn.

Ví dụ đúng:

~~~text
Transaction:
  UPDATE orders
  INSERT outbox_event
  COMMIT
~~~

Không dùng autonomous transaction cho insert outbox nếu mục tiêu là atomicity với business update. Autonomous transaction commit độc lập; nó có thể ghi event ngay cả khi transaction nghiệp vụ rollback.

## 3. Thiết kế bảng Outbox trong Oracle

Một outbox table cần đủ thông tin để định danh sự kiện, xác định aggregate, mô tả loại event, giữ payload và theo dõi trạng thái phát.

Ví dụ DDL:

~~~sql
CREATE TABLE app_outbox (
    event_id          RAW(16) DEFAULT SYS_GUID() NOT NULL,
    aggregate_type    VARCHAR2(100) NOT NULL,
    aggregate_id      VARCHAR2(200) NOT NULL,
    aggregate_version NUMBER(19),
    event_type        VARCHAR2(200) NOT NULL,
    schema_version    NUMBER(10) DEFAULT 1 NOT NULL,
    occurred_at       TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    payload           CLOB NOT NULL,
    status            VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    attempt_count     NUMBER(10) DEFAULT 0 NOT NULL,
    next_attempt_at   TIMESTAMP WITH TIME ZONE,
    lease_owner       VARCHAR2(128),
    lease_until       TIMESTAMP WITH TIME ZONE,
    published_at      TIMESTAMP WITH TIME ZONE,
    last_error        VARCHAR2(2000),
    CONSTRAINT app_outbox_pk PRIMARY KEY (event_id),
    CONSTRAINT app_outbox_status_ck
      CHECK (status IN ('NEW', 'IN_PROGRESS', 'PUBLISHED', 'DEAD'))
);
~~~

Nếu phiên bản Oracle hỗ trợ JSON constraint trên CLOB, có thể thêm:

~~~sql
ALTER TABLE app_outbox
  ADD CONSTRAINT app_outbox_payload_json_ck
  CHECK (payload IS JSON);
~~~

Cần kiểm tra phiên bản và kiểu dữ liệu JSON được hỗ trợ. Các phiên bản Oracle mới có native JSON type; ví dụ trên dùng CLOB để minh họa tính tương thích rộng hơn.

### 3.1 Ý nghĩa các cột

| Cột | Mục đích |
|---|---|
| EVENT_ID | ID duy nhất của sự kiện, dùng làm idempotency key |
| AGGREGATE_TYPE | Loại thực thể phát sinh event, ví dụ ORDER |
| AGGREGATE_ID | ID của đơn hàng hoặc thực thể nghiệp vụ |
| AGGREGATE_VERSION | Phiên bản tăng dần của aggregate để phát hiện thứ tự/gap |
| EVENT_TYPE | Tên sự kiện, ví dụ OrderConfirmed |
| SCHEMA_VERSION | Phiên bản cấu trúc payload |
| OCCURRED_AT | Thời điểm nghiệp vụ phát sinh sự kiện |
| PAYLOAD | Dữ liệu sự kiện được serialize |
| STATUS | Trạng thái xử lý của relay |
| ATTEMPT_COUNT | Số lần relay đã thử gửi |
| NEXT_ATTEMPT_AT | Thời điểm sớm nhất được phép retry |
| LEASE_OWNER | Worker đang giữ quyền xử lý event |
| LEASE_UNTIL | Hạn lease để worker khác có thể thu hồi khi worker chết |
| PUBLISHED_AT | Thời điểm relay ghi nhận publish thành công |
| LAST_ERROR | Thông tin lỗi gần nhất đã được rút gọn/ẩn dữ liệu nhạy cảm |

Có thể bổ sung tenant ID, correlation ID, causation ID, trace ID, partition key, priority hoặc event source theo nhu cầu. Không nên nhét mọi thông tin ứng dụng vào payload nếu consumer không cần.

### 3.2 Chọn kiểu event ID

Event ID cần ổn định qua mọi lần retry. Có thể dùng:

- RAW(16) với SYS_GUID().
- UUID được ứng dụng tạo trước transaction.
- Một định danh nghiệp vụ duy nhất kết hợp version nếu có quy tắc rõ ràng.

Không tạo event ID mới mỗi lần relay retry. Nếu ID thay đổi theo lần gửi, consumer không thể nhận diện duplicate của cùng một event.

Sequence Oracle có thể tạo ID số, nhưng sequence không bảo đảm thứ tự commit transaction. Event ID dùng để định danh, không nên tự động xem nó là timestamp hoặc thứ tự nghiệp vụ.

### 3.3 Index cho relay

Các index cần hỗ trợ truy vấn event chưa gửi và tìm event theo aggregate:

~~~sql
CREATE INDEX app_outbox_poll_ix
    ON app_outbox (status, next_attempt_at, occurred_at);

CREATE INDEX app_outbox_aggregate_ix
    ON app_outbox (aggregate_type, aggregate_id, aggregate_version);
~~~

Index thực tế cần dựa trên predicate của relay, tần suất update status và lượng dữ liệu. Index quá nhiều làm tăng chi phí insert/update và dung lượng. Nếu bảng có lượng event lớn, cân nhắc partition theo thời gian, retention và chiến lược archive/purge.

Không tạo index một cách máy móc: trạng thái NEW/IN_PROGRESS/PUBLISHED có cardinality thấp; index có thể không hữu ích nếu query không chọn lọc. Hãy xem execution plan và đo workload thực tế.

## 4. Ghi business data và event trong cùng transaction

Giả sử đơn hàng được xác nhận. Ứng dụng cập nhật ORDERS và thêm event OrderConfirmed.

Ví dụ SQL minh họa:

~~~sql
UPDATE orders
   SET status = 'CONFIRMED',
       version_no = version_no + 1,
       updated_at = SYSTIMESTAMP
 WHERE order_id = :order_id
   AND status = 'PENDING'
RETURNING version_no INTO :new_version;
~~~

Sau đó trong cùng transaction:

~~~sql
INSERT INTO app_outbox (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    schema_version,
    occurred_at,
    payload,
    status
)
VALUES (
    SYS_GUID(),
    'ORDER',
    :order_id,
    :new_version,
    'OrderConfirmed',
    1,
    SYSTIMESTAMP,
    :payload_json,
    'NEW'
);
~~~

Cuối cùng commit một lần:

~~~sql
COMMIT;
~~~

Trong ứng dụng thực tế, transaction boundary thường được quản lý bởi framework hoặc connection. Cả UPDATE và INSERT phải sử dụng cùng connection và transaction. Nếu UPDATE không thay đổi dòng nào, ứng dụng cần xử lý trạng thái cạnh tranh hoặc đơn hàng không hợp lệ thay vì vẫn phát OrderConfirmed.

### 4.1 Ví dụ PL/SQL hoàn chỉnh

~~~sql
DECLARE
    l_version orders.version_no%TYPE;
BEGIN
    UPDATE orders
       SET status = 'CONFIRMED',
           version_no = version_no + 1,
           updated_at = SYSTIMESTAMP
     WHERE order_id = :p_order_id
       AND status = 'PENDING'
    RETURNING version_no INTO l_version;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Order is not pending or does not exist'
        );
    END IF;

    INSERT INTO app_outbox (
        event_id,
        aggregate_type,
        aggregate_id,
        aggregate_version,
        event_type,
        schema_version,
        occurred_at,
        payload,
        status
    )
    VALUES (
        SYS_GUID(),
        'ORDER',
        TO_CHAR(:p_order_id),
        l_version,
        'OrderConfirmed',
        1,
        SYSTIMESTAMP,
        :p_payload,
        'NEW'
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Ví dụ trên minh họa ranh giới transaction. Trong code ứng dụng, nên để tầng quản lý transaction chịu trách nhiệm commit/rollback nếu transaction chứa thêm nhiều bước. Không commit bên trong một procedure dùng chung khi caller cần kiểm soát transaction lớn hơn.

### 4.2 Payload nên chứa gì?

Một event envelope thường có các trường:

~~~json
{
  "eventId": "9d4d0d3e-...",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "aggregateType": "ORDER",
  "aggregateId": "ORD-10025",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-14T09:30:00Z",
  "source": "order-service",
  "correlationId": "req-8f21",
  "causationId": "cmd-39a2",
  "data": {
    "orderId": "ORD-10025",
    "customerId": "CUS-82",
    "currency": "VND",
    "totalAmount": 1250000
  }
}
~~~

Đây là JSON minh họa. Payload nên chứa đủ thông tin để consumer hiểu event mà không phải truy vấn ngược database nguồn trong mọi trường hợp.

### 4.3 Snapshot event và reference event

Có hai cách thiết kế payload:

- **Snapshot event:** chứa các giá trị cần thiết tại thời điểm sự kiện xảy ra.
- **Reference event:** chỉ chứa ID và yêu cầu consumer đọc dữ liệu hiện tại từ API/database nguồn.

Snapshot giúp consumer xử lý đúng sự kiện lịch sử, kể cả khi dữ liệu nguồn đã thay đổi tiếp. Reference giảm payload và tránh sao chép dữ liệu, nhưng consumer có thể đọc một trạng thái mới hơn sự kiện đang xử lý.

Ví dụ, OrderConfirmed tại version 7 cần gửi giá trị totalAmount đã được xác nhận. Nếu consumer chỉ đọc lại bảng ORDERS sau đó, đơn hàng có thể đã bị hủy hoặc sửa ở version 8. Consumer sẽ nhận dữ liệu hiện tại thay vì dữ liệu của event version 7.

Chọn snapshot hay reference theo yêu cầu nghiệp vụ, quyền riêng tư, dung lượng và mức coupling. Không đưa thông tin nhạy cảm vào event nếu consumer không cần.

## 5. Outbox relay: chuyển event đã commit ra ngoài

Relay là tiến trình đọc outbox và publish event tới broker. Relay có thể chạy:

- **Polling publisher:** định kỳ truy vấn các dòng chưa gửi.
- **Transaction log tailing / CDC:** đọc thay đổi đã commit từ redo log hoặc change stream rồi phát event.
- **Database queue:** dùng Oracle AQ/Transactional Event Queues hoặc cơ chế queue tích hợp nếu phù hợp kiến trúc.

Dù chọn cách nào, relay phải chỉ phát event đã commit. Nó cũng phải xử lý crash, retry, duplicate và khả năng nhiều worker cùng chạy.

### 5.1 Polling publisher

Polling relay định kỳ tìm các event có trạng thái NEW và đến hạn retry. Cách này dễ triển khai, ít phụ thuộc hạ tầng CDC và có thể vận hành trực tiếp trên bảng Oracle.

Luồng tổng quát:

1. Chọn một batch event chưa được xử lý.
2. Claim các event bằng lease hoặc row lock.
3. Commit trạng thái claim.
4. Publish ra broker ngoài transaction database.
5. Khi broker xác nhận, cập nhật event thành PUBLISHED.
6. Khi publish lỗi, tăng attempt_count và lên lịch retry.
7. Nếu lỗi kéo dài quá chính sách, chuyển event sang DEAD để điều tra.

Không giữ row lock trong khi chờ network broker. Network call có thể kéo dài, gây lock contention và làm transaction database mở quá lâu. Thường claim event trong transaction ngắn, commit lease, sau đó publish ngoài transaction.

### 5.2 Claim event với nhiều worker

Nếu nhiều relay worker cùng poll, cần tránh hai worker xử lý cùng một event đồng thời. Oracle hỗ trợ FOR UPDATE SKIP LOCKED cho mô hình queue-like workload.

Ví dụ cursor claim mang tính minh họa:

~~~sql
DECLARE
    CURSOR c_events IS
        SELECT event_id
          FROM app_outbox
         WHERE status = 'NEW'
            OR (status = 'IN_PROGRESS'
                AND lease_until < SYSTIMESTAMP)
         ORDER BY occurred_at, event_id
         FOR UPDATE SKIP LOCKED;

    l_event_id RAW(16);
    l_count    PLS_INTEGER := 0;
BEGIN
    OPEN c_events;

    LOOP
        FETCH c_events INTO l_event_id;
        EXIT WHEN c_events%NOTFOUND OR l_count >= 100;

        UPDATE app_outbox
           SET status = 'IN_PROGRESS',
               lease_owner = 'relay-01',
               lease_until = SYSTIMESTAMP
                             + INTERVAL '60' SECOND,
               attempt_count = attempt_count + 1
         WHERE CURRENT OF c_events;

        l_count := l_count + 1;
    END LOOP;

    CLOSE c_events;
    COMMIT;
END;
/
~~~

Đây là khung minh họa cần điều chỉnh theo phiên bản Oracle, cursor logic, giới hạn batch và trạng thái retry. Trong triển khai thật, điều kiện chọn cần bao gồm NEXT_ATTEMPT_AT IS NULL hoặc NEXT_ATTEMPT_AT <= SYSTIMESTAMP, đồng thời bảo đảm các trạng thái và lease được cập nhật nhất quán.

SKIP LOCKED cho phép worker bỏ qua dòng đang bị worker khác khóa. Nó giúp tăng concurrency, nhưng không tự bảo đảm thứ tự event theo aggregate và không thay thế lease expiry.

### 5.3 Lease owner và lease expiry

Lease giúp worker khác tiếp quản event nếu worker hiện tại bị kill sau khi claim.

Ví dụ:

- Worker A claim event E1 và đặt lease đến 10:01.
- Worker A bị dừng trước khi publish.
- Lease hết hạn.
- Worker B claim E1 và thử gửi lại.

Lease cần đủ dài cho batch và publish latency, nhưng không quá dài khiến event bị treo lâu sau crash. Worker nên gia hạn lease khi xử lý kéo dài hoặc dùng lease theo từng event.

Cần thêm lease token hoặc claim generation để ngăn worker cũ cập nhật trạng thái sau khi lease đã hết hạn và event được worker mới claim. Khi hoàn tất, UPDATE cần kiểm tra event_id, lease_owner/token và trạng thái hiện tại.

### 5.4 Publish rồi đánh dấu PUBLISHED

Sau khi broker xác nhận publish, relay cập nhật:

~~~sql
UPDATE app_outbox
   SET status = 'PUBLISHED',
       published_at = SYSTIMESTAMP,
       lease_owner = NULL,
       lease_until = NULL,
       last_error = NULL
 WHERE event_id = :event_id
   AND status = 'IN_PROGRESS'
   AND lease_owner = :worker_id;

COMMIT;
~~~

Nếu broker đã nhận event nhưng relay chết trước khi UPDATE/COMMIT, event vẫn ở trạng thái IN_PROGRESS hoặc lease sẽ hết hạn. Worker khác gửi lại event. Đây là duplicate có chủ đích để tránh mất event.

Nếu đánh dấu PUBLISHED trước khi publish, process có thể chết sau update nhưng trước publish, dẫn đến mất event. Vì vậy thứ tự phổ biến là publish trước, mark published sau; consumer phải idempotent.

### 5.5 Retry và backoff

Khi publish lỗi tạm thời, không nên retry liên tục không có khoảng nghỉ. Dùng exponential backoff có giới hạn và jitter để tránh tất cả worker đồng loạt retry sau khi broker phục hồi.

Một lịch minh họa:

| Attempt | Delay cơ sở |
|---:|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 16 giây |
| Sau đó | Giới hạn tối đa theo chính sách |

Có thể tính:

\[
delay = \min(maxDelay,\ baseDelay \times 2^{attempt})
\]

Thêm jitter ngẫu nhiên giúp phân tán tải. Phân biệt lỗi transient như timeout, broker unavailable, throttling với lỗi permanent như payload không hợp lệ hoặc schema không tương thích.

### 5.6 Dead-letter state

Sau số lần retry hoặc thời gian chờ vượt chính sách, event có thể chuyển sang DEAD. DEAD không có nghĩa event được bỏ quên. Nó cần:

- Alert cho đội vận hành.
- Lưu last_error đã làm sạch dữ liệu nhạy cảm.
- Có dashboard và quy trình điều tra.
- Hỗ trợ replay sau khi sửa nguyên nhân.
- Không tự động xóa hoặc thay đổi payload gốc.

Khi replay, giữ nguyên event_id nếu đây là cùng một event được gửi lại. Nếu tạo một event nghiệp vụ mới sau khi sửa dữ liệu, dùng event_id mới và liên kết causation/correlation phù hợp.

## 6. CDC và transaction log tailing

Thay vì polling outbox, relay có thể đọc thay đổi đã commit từ redo log hoặc change data capture (CDC). Một connector có thể theo dõi INSERT vào bảng outbox rồi phát record tới broker.

Với Oracle, các lựa chọn phụ thuộc phiên bản, edition, licensing và hạ tầng có thể gồm:

- Oracle GoldenGate.
- LogMiner-based CDC hoặc connector sử dụng redo.
- Oracle XStream trong môi trường có quyền và cấu hình phù hợp.
- Công cụ CDC bên thứ ba hỗ trợ Oracle.
- Oracle Advanced Queuing hoặc Transactional Event Queues cho kiến trúc queue trong database.

Cần kiểm tra điều kiện licensing và support của từng sản phẩm. Không mặc định một tính năng CDC có sẵn trong mọi edition hoặc được phép dùng mà không có license phù hợp.

### 6.1 CDC từ bảng outbox

~~~text
Oracle transaction
   |
   +-- UPDATE business table
   |
   +-- INSERT outbox row
   |
  COMMIT
   |
   v
Redo / transaction log
   |
   v
CDC connector
   |
   v
Broker topic
   |
   v
Consumers
~~~

CDC chỉ đọc thay đổi đã commit từ log. Điều này giúp không cần query liên tục trạng thái NEW. Connector lưu offset/SCN để tiếp tục đọc sau restart.

### 6.2 Polling so với CDC

| Tiêu chí | Polling relay | CDC / log tailing |
|---|---|---|
| Độ trễ | Phụ thuộc chu kỳ polling và batch | Có thể thấp hơn, gần thời gian thực |
| Độ phức tạp | Dễ hiểu, tự kiểm soát | Cần connector, log retention và vận hành CDC |
| Tải database | Query và update trạng thái outbox | Đọc redo/log và duy trì offset |
| Retry | Ứng dụng relay quản lý trực tiếp | Connector/broker có cơ chế retry riêng |
| Ordering | Cần thiết kế trong worker | Có thể dựa vào partition/log order nhưng vẫn cần key/version |
| Quan sát | Bảng trạng thái outbox dễ truy vấn | Cần theo dõi connector lag và offset |
| Phù hợp | Lưu lượng vừa phải, triển khai đơn giản | Lưu lượng lớn hoặc yêu cầu latency thấp |

CDC từ outbox vẫn có thể phát duplicate khi connector restart hoặc offset được xử lý lại. Consumer idempotency vẫn cần thiết.

### 6.3 Vì sao vẫn cần outbox nếu đã có CDC?

CDC trực tiếp từ bảng business có thể tạo sự kiện từ row change, nhưng thay đổi row không nhất thiết thể hiện ý nghĩa nghiệp vụ. Một UPDATE có thể do sửa lỗi, migration, batch hoặc trigger. Consumer phải suy luận event từ cấu trúc dữ liệu.

Outbox cho phép ứng dụng tạo một event nghiệp vụ rõ ràng như OrderConfirmed, PaymentCaptured hoặc CustomerAddressChanged. CDC chỉ là cơ chế vận chuyển các event đã được ghi vào outbox.

## 7. Idempotency là gì?

Một thao tác là idempotent nếu thực hiện một lần hay nhiều lần với cùng một định danh đầu vào vẫn tạo ra cùng một kết quả nghiệp vụ.

Ví dụ:

- Đặt trạng thái đơn hàng thành CONFIRMED có thể idempotent nếu cập nhật có điều kiện và không phát sinh hiệu ứng phụ lặp.
- Cộng thêm 100.000 đồng vào số dư không idempotent nếu cùng request chạy hai lần.
- Tạo payment mới không idempotent nếu mỗi lần retry tạo một payment khác.

Trong hệ thống message, duplicate có thể xuất hiện do broker redelivery, consumer restart, ACK bị mất hoặc relay publish lại. Idempotency giúp consumer xử lý an toàn các lần giao lặp.

### 7.1 At-least-once và duplicate

Mô hình outbox relay phổ biến là at-least-once:

- Relay sẽ tiếp tục thử cho đến khi broker nhận message hoặc event chuyển trạng thái lỗi.
- Có thể gửi một event nhiều lần nếu không chắc lần trước đã thành công.
- Consumer có thể nhận lại event đã xử lý.

At-least-once ưu tiên không mất event. Đổi lại, ứng dụng phải chấp nhận duplicate và xử lý chúng một cách có kiểm soát.

### 7.2 Exactly-once end-to-end là kỳ vọng khó

Một broker có thể hỗ trợ producer idempotence hoặc transaction trong phạm vi broker. Nhưng điều đó không tự làm transaction Oracle, publish, consumer database update và external API thành một transaction nguyên tử duy nhất.

Ví dụ consumer cập nhật database xong nhưng chết trước khi ACK broker. Broker gửi lại message. Nếu consumer không idempotent, business update sẽ lặp.

Vì vậy, thiết kế thực tế thường dùng at-least-once delivery kết hợp idempotent consumer. Có thể có exactly-once semantics trong một ranh giới hẹp của công nghệ cụ thể, nhưng cần mô tả rõ ranh giới đó thay vì tuyên bố toàn hệ thống exactly once.

## 8. Inbox pattern và bảng deduplication

Một cách phổ biến để bảo đảm consumer xử lý một event tối đa một lần về mặt hiệu ứng local database là lưu event ID vào bảng inbox/processed message trong cùng transaction với business update.

Ví dụ DDL:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR2(100) NOT NULL,
    event_id      RAW(16) NOT NULL,
    received_at   TIMESTAMP WITH TIME ZONE
                  DEFAULT SYSTIMESTAMP NOT NULL,
    processed_at  TIMESTAMP WITH TIME ZONE,
    CONSTRAINT consumer_inbox_pk
      PRIMARY KEY (consumer_name, event_id)
);
~~~

Khóa chính ghép (consumer_name, event_id) cho phép cùng một event được xử lý bởi các consumer độc lập, nhưng một consumer không thể ghi nhận cùng event hai lần.

### 8.1 Xử lý message trong một transaction

Luồng consumer:

1. Nhận message.
2. Bắt đầu transaction database.
3. Insert event ID vào inbox.
4. Nếu insert thành công, áp dụng business effect.
5. Đánh dấu inbox processed.
6. Commit.
7. Sau commit mới ACK message cho broker.

Ví dụ PL/SQL minh họa:

~~~sql
DECLARE
    l_duplicate EXCEPTION;
    PRAGMA EXCEPTION_INIT(l_duplicate, -1);
BEGIN
    INSERT INTO consumer_inbox (
        consumer_name,
        event_id,
        received_at
    )
    VALUES (
        'inventory-service',
        :event_id,
        SYSTIMESTAMP
    );

    UPDATE inventory
       SET reserved_quantity = reserved_quantity + :quantity,
           version_no = version_no + 1
     WHERE product_id = :product_id;

    UPDATE consumer_inbox
       SET processed_at = SYSTIMESTAMP
     WHERE consumer_name = 'inventory-service'
       AND event_id = :event_id;

    COMMIT;
EXCEPTION
    WHEN l_duplicate THEN
        ROLLBACK;
        -- Event đã được ghi nhận trước đó.
        -- Consumer có thể ACK duplicate theo chính sách.
        NULL;
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Ví dụ giả định update inventory hợp lệ và đã có validation riêng. Trong code thật, không nên nuốt mọi lỗi unique constraint nếu có thể đó là vi phạm constraint khác; hãy nhận diện chính xác constraint inbox hoặc thực hiện insert/dedup bằng API có kiểm soát.

ACK broker chỉ sau khi database commit thành công. Nếu ACK trước commit rồi process chết, broker có thể không gửi lại message trong khi business transaction đã rollback.

### 8.2 Vì sao insert inbox và business update phải cùng transaction?

Giả sử consumer commit inbox trước rồi mới cập nhật inventory. Nếu process chết giữa hai bước, lần giao lại thấy event ID đã tồn tại và bỏ qua; inventory không được cập nhật. Đó là mất hiệu ứng.

Ngược lại, nếu cập nhật inventory trước, commit, rồi mới ghi inbox trong transaction khác, process chết giữa hai transaction sẽ khiến message được xử lý lại và cộng quantity lần thứ hai.

Cùng transaction giúp hai kết quả xảy ra đồng thời: hoặc cả inbox và business effect commit, hoặc cả hai rollback.

### 8.3 Xử lý duplicate khi có concurrency

Hai consumer instance có thể cùng nhận một event gần như đồng thời. Cả hai thử insert cùng khóa chính:

- Một transaction insert thành công và giữ khóa.
- Transaction còn lại chờ kết quả.
- Nếu transaction đầu commit, transaction sau nhận duplicate key.
- Nếu transaction đầu rollback, transaction sau có thể insert thành công.

Unique constraint của Oracle là hàng rào cuối cùng chống hai worker cùng xử lý event. Chỉ kiểm tra SELECT trước INSERT không đủ vì hai worker có thể cùng thấy chưa tồn tại rồi cùng thực hiện.

### 8.4 Retention của inbox

Không thể xóa inbox record quá sớm nếu broker còn khả năng redeliver hoặc event có thể được replay. Retention phải dài hơn thời gian tối đa mà duplicate có thể xuất hiện theo chính sách broker và vận hành.

Nếu xóa record cũ, cần biết replay có thể xảy ra đến đâu. Có thể lưu deduplication key trong bảng nghiệp vụ hoặc một kho idempotency lâu dài nếu nghiệp vụ yêu cầu.

## 9. Idempotency key cho API và command

Idempotency không chỉ áp dụng cho event consumer. API có thể nhận request retry do client timeout hoặc gateway retry.

Ví dụ client gửi POST /payments với header Idempotency-Key. Server lưu key, request hash và kết quả xử lý.

Một bảng minh họa:

~~~sql
CREATE TABLE api_idempotency (
    client_scope  VARCHAR2(100) NOT NULL,
    idempotency_key VARCHAR2(200) NOT NULL,
    request_hash  RAW(32) NOT NULL,
    response_code NUMBER(3),
    response_body CLOB,
    status        VARCHAR2(20) NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE
                  DEFAULT SYSTIMESTAMP NOT NULL,
    completed_at  TIMESTAMP WITH TIME ZONE,
    CONSTRAINT api_idempotency_pk
      PRIMARY KEY (client_scope, idempotency_key)
);
~~~

Khi nhận request:

- Nếu key chưa tồn tại, tạo bản ghi và thực hiện nghiệp vụ.
- Nếu key đã hoàn tất với cùng request hash, trả lại kết quả đã lưu.
- Nếu key đã tồn tại nhưng request hash khác, trả lỗi vì client tái sử dụng key cho nội dung khác.
- Nếu key đang xử lý, áp dụng chính sách chờ, trả trạng thái processing hoặc retry sau.

Idempotency key cần có scope như client/account/tenant để tránh va chạm giữa người dùng khác nhau. Không dùng key do server tạo mới sau mỗi retry.

### 9.1 Idempotency key không thay thế validation

Nếu cùng key nhưng payload khác, server cần phát hiện và từ chối. Nếu chỉ lưu key mà không lưu request hash hoặc thông tin tương đương, client có thể vô tình dùng lại key cho một nghiệp vụ khác và nhận kết quả cũ.

Cũng cần xác định thời hạn hiệu lực key. Nếu xóa key sau một ngày nhưng client retry sau hai ngày, thao tác có thể được thực hiện lần nữa. TTL phải phù hợp với hợp đồng API và thời gian retry của hệ thống.

### 9.2 Idempotent update bằng điều kiện trạng thái

Một số business command có thể được làm idempotent bằng trạng thái và version:

~~~sql
UPDATE orders
   SET status = 'CONFIRMED',
       version_no = version_no + 1
 WHERE order_id = :order_id
   AND status = 'PENDING';
~~~

Nếu lệnh chạy lại, dòng đã CONFIRMED sẽ không được cập nhật lần nữa. Nhưng cần phân biệt "đã hoàn thành trước đó" với "không tồn tại" hoặc "trạng thái không hợp lệ". Ứng dụng nên đọc lại trạng thái và trả kết quả tương ứng.

Với thao tác cộng/trừ số lượng hoặc số dư, điều kiện trạng thái đơn thuần có thể không đủ. Hãy dùng operation ID duy nhất, ledger entry có unique key hoặc transaction log nghiệp vụ để chống lặp.

## 10. Event ordering và aggregate version

Event-based synchronization thường cần thứ tự trong phạm vi một aggregate. Ví dụ OrderCreated phải được xử lý trước OrderConfirmed; OrderConfirmed phải trước OrderShipped.

Không phải lúc nào cũng cần thứ tự toàn hệ thống. Thứ tự toàn cục làm giảm throughput và tạo điểm nghẽn. Thường chỉ cần giữ thứ tự theo aggregate ID.

### 10.1 Timestamp không phải thứ tự tuyệt đối

OCCURRED_AT hữu ích để quan sát và sắp xếp gần đúng, nhưng timestamp không luôn đại diện cho thứ tự commit:

- Hai session có thể lấy timestamp ở thời điểm khác nhau rồi commit theo thứ tự khác.
- Đồng hồ giữa các máy có thể lệch.
- Timestamp có độ chính xác hữu hạn.
- Event có thể được relay sau nhiều phút.
- Sequence được cấp trước commit không đảm bảo thứ tự commit.

Nếu cần phát hiện thứ tự nghiệp vụ, dùng AGGREGATE_VERSION tăng trong cùng transaction cập nhật aggregate.

### 10.2 Aggregate version

Mỗi lần aggregate thay đổi, tăng version:

~~~sql
UPDATE orders
   SET status = :new_status,
       version_no = version_no + 1
 WHERE order_id = :order_id
   AND version_no = :expected_version
RETURNING version_no INTO :new_version;
~~~

Event được ghi với cùng new_version trong transaction. Optimistic concurrency qua expected_version giúp phát hiện hai command cạnh tranh.

Consumer lưu last_processed_version cho aggregate. Khi nhận version:

- Nếu version bằng last + 1, xử lý.
- Nếu version nhỏ hơn hoặc bằng last, có thể là duplicate hoặc event cũ.
- Nếu version lớn hơn last + 1, có thể thiếu event; giữ lại hoặc yêu cầu replay/reconciliation.

Cách xử lý gap tùy nghiệp vụ. Có consumer có thể áp dụng snapshot mới nhất; consumer khác cần từng event vì mỗi event tạo hiệu ứng riêng.

### 10.3 Ordering tại relay

Nhiều relay worker có thể publish event version 8 trước version 7 nếu chúng claim và gửi song song. Nếu ordering theo aggregate là bắt buộc, có thể:

- Partition event theo aggregate ID và chỉ một worker xử lý mỗi partition.
- Không claim event mới của aggregate khi event trước chưa published.
- Dùng broker partition key là aggregate ID để giữ thứ tự trong partition.
- Dùng aggregate version để consumer phát hiện out-of-order và gap.

Chỉ dùng ORDER BY occurred_at trong poll query không bảo đảm thứ tự khi có nhiều worker hoặc publish latency khác nhau.

### 10.4 Ordering tại broker

Một số broker giữ thứ tự trong một partition hoặc queue, nhưng không bảo đảm thứ tự toàn bộ topic khi nhiều partition. Dùng aggregate ID làm message key nếu broker hỗ trợ partitioning theo key.

Nếu event cùng aggregate được gửi tới các partition khác nhau, consumer có thể nhận sai thứ tự. Partition key và routing strategy phải ổn định qua thời gian; thay số partition có thể ảnh hưởng mapping key tùy broker.

## 11. Event contract và schema evolution

Event là hợp đồng giữa producer và consumer. Khi producer đổi payload, consumer cũ có thể chưa được deploy cùng lúc. Vì vậy, schema phải được thiết kế để tiến hóa an toàn.

Một event envelope nên xác định:

- eventId.
- eventType.
- schemaVersion.
- aggregateType và aggregateId.
- aggregateVersion nếu cần ordering.
- occurredAt.
- source.
- correlationId và causationId.
- data payload.

### 11.1 Thay đổi tương thích

Thường tương thích hơn khi:

- Thêm field optional với default rõ ràng.
- Consumer bỏ qua field chưa biết.
- Không đổi ý nghĩa field hiện có.
- Không đổi đơn vị hoặc timezone ngầm định.
- Không đổi kiểu dữ liệu một cách phá vỡ.
- Giữ eventType ổn định và tạo event type mới khi ý nghĩa nghiệp vụ thay đổi lớn.

Xóa field, đổi tên field, thay kiểu, đổi enum hoặc thay semantics có thể phá vỡ consumer. Dùng schema registry hoặc contract tests khi hệ sinh thái có nhiều producer/consumer.

### 11.2 Version payload

Có thể thêm schemaVersion vào envelope. Consumer có thể hỗ trợ nhiều version hoặc producer phát một event type mới.

Không dùng version để hợp thức hóa mọi thay đổi. Version chỉ hữu ích nếu có quy tắc migration, compatibility và thời gian hỗ trợ version cũ.

### 11.3 Event bất biến

Một event nên mô tả sự thật đã xảy ra trong quá khứ: OrderConfirmed, PaymentCaptured, InventoryReserved. Không sửa payload của event đã phát để phản ánh trạng thái hiện tại.

Nếu có correction, phát event mới như OrderCorrectionApplied hoặc PaymentRefunded. Event history cần giữ ý nghĩa lịch sử và có thể audit.

## 12. Event-based synchronization giữa nhiều hệ thống

Khi consumer nhận event, nó cập nhật read model hoặc database cục bộ. Đây là cách phổ biến để đồng bộ dữ liệu mà không cho các dịch vụ truy vấn trực tiếp database của nhau.

~~~text
                 Oracle Order DB
                       |
                 Transactional
                    Outbox
                       |
                  Outbox relay
                       |
                 Event broker
             /         |         \
            /          |          \
           v           v           v
    Inventory DB   Billing DB   Search Index
       Consumer      Consumer     Consumer
~~~

Mỗi consumer sở hữu dữ liệu cục bộ của mình. Order service không cần biết cấu trúc bảng Inventory hay Search Index. Nó chỉ phát event contract đã công bố.

### 12.1 Event notification và event-carried state transfer

Có hai kiểu payload phổ biến:

- **Event notification:** báo rằng có thay đổi, consumer gọi API để lấy chi tiết.
- **Event-carried state transfer:** mang đủ dữ liệu để consumer cập nhật local model mà không cần gọi ngược producer.

Event notification giảm kích thước payload nhưng tăng coupling runtime và có nguy cơ đọc trạng thái mới hơn event. Event-carried state transfer giảm phụ thuộc đồng bộ nhưng cần quản lý schema, bảo mật và dữ liệu sao chép.

### 12.2 Eventual consistency

Sau khi Order service commit, event cần thời gian để relay, broker và consumer xử lý. Trong khoảng đó, Inventory hoặc Search có thể chưa phản ánh thay đổi.

Đây là eventual consistency. Ứng dụng cần thể hiện trạng thái trung gian nếu người dùng đọc ngay sau khi ghi, ví dụ "đang xử lý", "đang đồng bộ" hoặc dùng read-your-writes qua nguồn dữ liệu chính.

Không nên giả định tất cả service cập nhật cùng thời điểm. Hãy xác định SLA propagation: 95% event trong 2 giây, 99.9% trong 30 giây chẳng hạn, dựa trên đo đạc thật.

### 12.3 Reconciliation

Event processing có thể gặp lỗi kéo dài hoặc consumer bug. Cần có cơ chế đối soát giữa source of truth và projection:

- So sánh count hoặc checksum theo partition/time range.
- Đọc lại aggregate version.
- Replay event từ offset hoặc archive.
- Rebuild read model từ snapshot và event history.
- Phát correction event khi phát hiện lệch.
- Ghi lại reconciliation result và thời điểm hoàn tất.

Eventual consistency không có nghĩa chấp nhận sai lệch vĩnh viễn. Reconciliation giúp phát hiện và sửa các sai lệch không tự phục hồi.

## 13. Saga và outbox trong quy trình nhiều dịch vụ

Một nghiệp vụ có thể trải qua nhiều service và nhiều database. Không thể dùng một local Oracle transaction để commit tất cả.

Ví dụ đặt hàng:

1. Order service tạo đơn.
2. Inventory service giữ hàng.
3. Payment service thu tiền.
4. Shipping service tạo vận đơn.

Nếu payment thất bại sau khi inventory đã giữ hàng, hệ thống cần giải phóng hàng. Đây là một distributed workflow thường được mô hình hóa bằng Saga.

~~~text
OrderCreated
    |
    v
ReserveInventory
    |
    +---- InventoryReserved ----> AuthorizePayment
    |                                  |
    |                                  +---- PaymentAuthorized
    |                                  |           |
    |                                  |           v
    |                                  |       CreateShipment
    |                                  |
    |                                  +---- PaymentRejected
    |                                              |
    v                                              v
OrderCancelled <---- ReleaseInventory <---- Compensation
~~~

Mỗi service thực hiện local transaction và phát event/command qua outbox. Khi bước sau thất bại, saga phát compensating action.

### 13.1 Forward recovery và compensation

Khi một bước tạm thời lỗi, có thể retry cùng bước. Khi lỗi không thể phục hồi hoặc nghiệp vụ quyết định hủy, saga chạy compensation.

Compensation không phải rollback database theo nghĩa kỹ thuật. Nó là một nghiệp vụ mới nhằm đảo ngược hiệu ứng trước đó. Ví dụ không xóa lịch sử giữ hàng mà phát InventoryReservationReleased.

### 13.2 Idempotent compensation

Compensation cũng có thể được giao nhiều lần. Cần idempotency key cho từng action, ví dụ sagaId + stepName + actionVersion. Nếu ReleaseInventory được nhận lại, consumer không được trừ hoặc cộng tồn kho nhiều lần.

### 13.3 Outbox trong mỗi service

Mỗi service có database riêng và outbox riêng. Không ghi trực tiếp vào database của service khác. Saga coordinator hoặc choreography nhận event, lưu trạng thái saga và phát command tiếp theo bằng outbox của chính nó.

## 14. Oracle Advanced Queuing và Transactional Event Queues

Oracle cung cấp các công nghệ queue tích hợp với database như Advanced Queuing (AQ) và Transactional Event Queues (TxEventQ, tên gọi/khả năng tùy release). Chúng có thể phù hợp khi muốn message được quản lý trong cùng hệ sinh thái Oracle.

AQ hỗ trợ enqueue/dequeue có thể tham gia transaction database. Điều này có thể loại bỏ một số dual-write boundary nếu ứng dụng và consumer dùng queue tích hợp đúng cách.

Tuy nhiên, cần phân biệt:

- Outbox là một pattern thiết kế dựa trên bảng và relay.
- AQ/TxEventQ là hạ tầng messaging do Oracle cung cấp.
- CDC là cơ chế đọc thay đổi từ transaction log.
- Kafka/RabbitMQ hoặc broker khác là hệ thống messaging bên ngoài database.

Chọn giải pháp theo yêu cầu throughput, latency, retention, routing, operational skill, integration ecosystem và licensing. Không nên thêm bảng outbox nếu một queue transactional đã đáp ứng tốt và hệ thống chấp nhận coupling với Oracle; ngược lại, không nên ép mọi consumer phụ thuộc trực tiếp vào Oracle queue nếu kiến trúc cần broker trung tâm.

## 15. Trigger có nên tự ghi outbox không?

Có thể dùng trigger để ghi outbox khi bảng thay đổi, nhưng cần cân nhắc.

Ưu điểm:

- Ghi nhận thay đổi kể cả khi nhiều ứng dụng cùng sửa bảng.
- Logic audit/event được đặt gần database.
- Business application không thể quên insert event nếu trigger bao phủ đúng thao tác.

Rủi ro:

- Trigger che giấu side effect khỏi code ứng dụng.
- Dễ phát event cho thay đổi kỹ thuật, migration hoặc batch không mang ý nghĩa nghiệp vụ.
- Khó xây dựng payload giàu ngữ cảnh.
- Trigger có thể làm tăng chi phí DML và gây lỗi ngoài dự kiến.
- Trigger phức tạp dễ tạo recursion hoặc phụ thuộc thứ tự trigger.
- Thay đổi schema có thể làm hỏng trigger.

Nếu dùng trigger, chỉ nên làm công việc nhỏ, xác định rõ event semantics và không gọi broker/network trong trigger. Trigger phải insert outbox trong cùng transaction, không autonomous transaction. Đối với event nghiệp vụ như OrderConfirmed, thường ứng dụng/service layer có ngữ cảnh rõ hơn để quyết định khi nào phát event.

## 16. Bảo mật và quyền riêng tư của event

Event có thể được lưu lâu hơn row nguồn hoặc được gửi tới nhiều hệ thống. Vì vậy, payload cần được xem như một bản sao dữ liệu có chính sách bảo vệ riêng.

Nguyên tắc:

- Chỉ đưa field consumer thực sự cần.
- Không đưa password, token, secret hoặc dữ liệu xác thực.
- Mã hóa đường truyền và broker storage theo chính sách.
- Giới hạn quyền đọc topic/queue.
- Xem xét masking dữ liệu trong log và dead-letter record.
- Định nghĩa retention và quyền replay.
- Có quy trình xóa/ẩn dữ liệu cá nhân theo yêu cầu pháp lý.
- Bảo vệ correlation ID và metadata có thể tiết lộ người dùng.

Nếu event chứa dữ liệu cá nhân, việc xóa row ở database nguồn không tự động xóa mọi bản sao event trong broker, data lake, search index và consumer database. Cần có chính sách data lifecycle và cơ chế correction/deletion event.

### 16.1 Không log toàn bộ payload tùy tiện

Khi publish thất bại, không nên ghi nguyên payload vào application log nếu nó chứa thông tin nhạy cảm. Lưu event ID, type, aggregate ID đã được kiểm soát và error code đủ để điều tra.

### 16.2 Quyền trên bảng outbox

Tách quyền:

- Business service được INSERT outbox.
- Relay được SELECT/UPDATE các cột trạng thái cần thiết.
- Auditor được đọc metadata theo phạm vi.
- Không cấp quyền DELETE rộng cho relay.
- Purge job có quyền riêng và retention rõ ràng.

Nếu relay chỉ cần cập nhật status, không cần cấp quyền sửa payload. Có thể dùng view hoặc package để giới hạn thao tác.

## 17. Quản lý dung lượng và retention của outbox

Outbox có thể tăng rất nhanh nếu mỗi business transaction phát nhiều event. Cần xác định vòng đời record:

- NEW: đang chờ publish.
- IN_PROGRESS: đang được relay giữ lease.
- PUBLISHED: đã được broker xác nhận.
- DEAD: vượt retry policy hoặc lỗi permanent.

PUBLISHED record không nhất thiết phải giữ mãi trong bảng nóng. Có thể archive rồi purge theo retention. Tuy nhiên, nếu dùng outbox làm audit/event history, yêu cầu retention có thể dài hơn và cần kho lưu trữ riêng.

### 17.1 Purge an toàn

Không xóa event đang IN_PROGRESS hoặc NEW. Chỉ purge event PUBLISHED đủ cũ theo policy và event DEAD sau khi đã được xử lý/đối soát.

Ví dụ predicate purge minh họa:

~~~sql
DELETE FROM app_outbox
 WHERE status = 'PUBLISHED'
   AND published_at < SYSTIMESTAMP - INTERVAL '30' DAY;
~~~

30 ngày chỉ là giá trị minh họa. Production cần batch delete để tránh transaction quá lớn, undo/redo tăng đột biến và lock kéo dài.

### 17.2 Partitioning

Với bảng lớn, partition theo thời gian tạo có thể giúp purge và archive hiệu quả. Tuy nhiên, unique constraint và partition key có ảnh hưởng đến thiết kế primary key; Oracle có quy tắc riêng cho local/global index. Hãy thiết kế partition cùng với cách định danh event và yêu cầu truy vấn.

### 17.3 Retention phải khớp replay window

Nếu broker có thể replay event 90 ngày nhưng inbox chỉ giữ 7 ngày, consumer có thể xử lý lại event cũ sau khi dedup record bị xóa. Retention của inbox, outbox, broker và event archive phải được thiết kế thống nhất.

## 18. Quan sát và vận hành event pipeline

Một pipeline event cần được giám sát từ transaction nguồn đến consumer cuối.

### 18.1 Chỉ số ở outbox

- Số event NEW.
- Tuổi event NEW lâu nhất.
- Số event IN_PROGRESS và lease đã hết hạn.
- Số event PUBLISHED theo phút.
- Số event DEAD.
- Attempt count trung bình và lớn nhất.
- Thời gian từ occurred_at đến published_at.
- Kích thước bảng và tốc độ tăng.
- Tỷ lệ lỗi publish.

Một chỉ số quan trọng là **outbox age**: thời gian event cũ nhất còn chờ được publish. Queue depth thấp nhưng một event bị treo lâu vẫn có thể là sự cố nghiệp vụ.

### 18.2 Chỉ số broker và consumer

- Producer publish latency và error rate.
- Broker queue/topic lag.
- Consumer lag/offset.
- Số lần redelivery.
- Số duplicate bị deduplicate.
- Processing latency.
- Retry count và dead-letter count.
- Gap/out-of-order version.
- Tỷ lệ event thành công theo event type.

### 18.3 Correlation và tracing

Gắn correlationId xuyên suốt:

~~~text
HTTP request
  -> Order transaction
  -> Outbox event
  -> Broker message
  -> Inventory consumer
  -> Inventory database
~~~

Cần giữ eventId, correlationId, causationId, aggregateId và trace context. Điều này giúp truy vấn một nghiệp vụ xuyên nhiều service mà không cần ghi toàn bộ payload vào log.

### 18.4 Alert có ý nghĩa

Alert nên phản ánh tác động nghiệp vụ, không chỉ số kỹ thuật:

- Event OrderConfirmed bị chậm quá SLA.
- Outbox backlog tăng liên tục.
- Consumer Inventory không xử lý được event.
- Event DEAD tăng.
- Version gap xuất hiện.
- Deduplication rate tăng bất thường.
- Relay lease hết hạn liên tục.
- Database outbox segment hoặc FRA/storage gần đầy.

## 19. Kiểm thử failure scenario

Outbox và idempotency chỉ đáng tin khi đã thử các điểm crash thực tế.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Business transaction rollback | Không có business update và không có outbox event |
| Commit thành công, relay dừng | Event còn trong outbox và được gửi sau restart |
| Broker nhận event, ACK bị mất | Relay có thể gửi duplicate; consumer chỉ tạo một hiệu ứng |
| Relay chết sau publish, trước mark PUBLISHED | Event được gửi lại sau lease expiry; consumer dedupe |
| Consumer chết trước commit | Inbox và business update rollback; broker redeliver |
| Consumer commit, ACK bị mất | Message redeliver; inbox phát hiện duplicate |
| Hai consumer cùng nhận một event | Unique key chỉ cho một transaction xử lý |
| Event đến sai thứ tự | Version check phát hiện out-of-order/gap |
| Broker unavailable lâu | Retry/backoff, backlog tăng và alert |
| Payload không hợp lệ | Event vào DEAD/quarantine, không retry vô hạn |
| Purge chạy trong lúc relay xử lý | Chỉ purge trạng thái đủ điều kiện, không xóa lease active |

### 19.1 Kiểm thử crash window của relay

Đặc biệt kiểm tra hai cửa sổ:

1. Broker đã nhận event, relay chưa mark PUBLISHED.
2. Relay đã mark PUBLISHED nhưng broker chưa nhận event.

Thiết kế đúng sẽ chấp nhận duplicate ở cửa sổ thứ nhất. Cửa sổ thứ hai phải được loại bỏ bằng thứ tự thao tác publish trước rồi mark published.

### 19.2 Kiểm thử consumer ACK

Consumer chỉ ACK sau khi transaction local commit. Cần kiểm thử process bị dừng ngay sau commit và trước ACK. Message sẽ được giao lại; inbox phải phát hiện duplicate.

### 19.3 Kiểm thử replay

Replay có thể xảy ra khi:

- Consumer được rebuild.
- Broker offset được reset.
- Dead-letter event được phát lại.
- Connector CDC đọc lại từ checkpoint cũ.
- Event archive được dùng để tái tạo projection.

Replay cần cùng event ID để dedup. Nếu cố ý tái thực hiện một nghiệp vụ mới, tạo command/event mới với idempotency key mới và ghi quan hệ causation.

## 20. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Commit business trước, insert outbox sau | Có dữ liệu nhưng mất event | Ghi trong cùng transaction |
| Gửi broker trong trigger | Transaction database phụ thuộc network và broker | Chỉ ghi outbox trong transaction |
| Dùng autonomous transaction cho outbox | Event có thể tồn tại dù business rollback | Dùng cùng transaction |
| Mark PUBLISHED trước khi publish | Có thể mất event | Publish rồi mới mark |
| Không có event ID ổn định | Không dedupe được duplicate | Dùng event ID giữ nguyên qua retry |
| Consumer ACK trước commit | Có thể mất business effect | Commit rồi ACK |
| Inbox commit riêng | Inbox tồn tại nhưng business update rollback | Cùng transaction |
| Chỉ SELECT kiểm tra duplicate | Race condition giữa worker | Unique constraint |
| Retry vô hạn không backoff | Tạo tải và log storm | Exponential backoff, jitter, DLQ |
| Nhiều worker không kiểm soát ordering | Event cùng aggregate đảo thứ tự | Partition/serialize theo aggregate và version |
| Dùng timestamp làm version | Không bảo đảm thứ tự commit | Aggregate version |
| Payload chỉ có ID nhưng consumer đọc current row | Consumer thấy trạng thái mới hơn event | Snapshot hoặc API có version |
| Xóa outbox quá sớm | Không thể replay/đối soát | Retention theo replay window |
| Không có reconciliation | Sai lệch kéo dài không được phát hiện | Đối soát định kỳ |
| Ghi payload nhạy cảm vào log | Rò rỉ dữ liệu | Log metadata tối thiểu và masking |

## 21. So sánh Outbox với các lựa chọn khác

| Giải pháp | Ưu điểm | Giới hạn |
|---|---|---|
| Transactional Outbox | Dễ hiểu, atomic với local DB, event nghiệp vụ rõ | Cần relay, retry, cleanup và idempotency |
| Distributed transaction / 2PC | Có thể phối hợp commit nhiều resource được hỗ trợ | Tăng coupling, operational complexity, không phải broker nào cũng tham gia |
| Oracle AQ/TxEventQ | Messaging tích hợp database, transaction-aware | Coupling với Oracle và điều kiện release/licensing |
| CDC trực tiếp từ business table | Gần real-time, đọc log thay vì poll | Row change không luôn mang nghĩa nghiệp vụ |
| CDC từ outbox | Event semantics rõ, không cần poll status | Cần CDC connector và log retention |
| Periodic batch sync | Đơn giản cho dữ liệu ít thay đổi | Độ trễ cao, khó xử lý incremental và delete |
| API call đồng bộ giữa service | Kết quả tức thời khi thành công | Runtime coupling, timeout và cascade failure |

Không có một lựa chọn đúng cho mọi hệ thống. Outbox phù hợp khi cần phát event nghiệp vụ đáng tin cậy từ local transaction và chấp nhận eventual consistency.

## 22. Ví dụ end-to-end: Order và Inventory

Giả sử Order service sở hữu bảng ORDERS trong Oracle. Inventory service sở hữu bảng INVENTORY ở database riêng.

Khi xác nhận đơn hàng:

1. Order service kiểm tra đơn hàng PENDING.
2. Cập nhật trạng thái CONFIRMED và tăng version.
3. Insert OrderConfirmed vào APP_OUTBOX.
4. Commit.
5. Relay publish event.
6. Inventory consumer nhận event.
7. Consumer insert event ID vào INBOX.
8. Consumer tăng reserved quantity và ghi version.
9. Consumer commit.
10. Consumer ACK broker.

Nếu consumer nhận lại event, insert inbox bị duplicate key và business effect không chạy lần nữa.

### 22.1 Bảng consumer theo dõi version

Có thể lưu version đã áp dụng:

~~~sql
CREATE TABLE inventory_order_state (
    order_id           VARCHAR2(200) PRIMARY KEY,
    last_event_version NUMBER(19) NOT NULL,
    status             VARCHAR2(30) NOT NULL,
    updated_at         TIMESTAMP WITH TIME ZONE
                       DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

Consumer kiểm tra version trước khi áp dụng event. Nếu version bị nhảy, cần giữ event và xử lý gap theo chính sách. Nếu event cũ hơn version đã áp dụng, có thể đánh dấu duplicate/stale mà không chạy lại hiệu ứng.

### 22.2 Consumer cần transaction logic rõ

Inbox và cập nhật inventory phải nằm cùng transaction. Nếu cần gọi thêm dịch vụ bên ngoài, không thực hiện HTTP call trong transaction database dài. Ghi một outbox event mới từ transaction consumer rồi dùng relay riêng để phát yêu cầu tiếp theo.

Đó là cách mỗi service tiếp tục duy trì atomicity local mà không tạo một transaction phân tán kéo dài qua network.

## 23. Quy trình triển khai trong Oracle

Một lộ trình triển khai có kiểm soát:

1. Xác định event nghiệp vụ và source of truth.
2. Thiết kế event envelope, event ID, aggregate ID/version và schema version.
3. Tạo bảng outbox, constraint và index cần thiết.
4. Sửa transaction nghiệp vụ để insert outbox cùng commit.
5. Viết relay polling hoặc cấu hình CDC.
6. Thiết kế retry, lease, dead-letter và replay.
7. Tạo inbox/deduplication ở consumer.
8. Bảo đảm inbox và business effect cùng transaction.
9. Thiết kế partition/order theo aggregate nếu cần.
10. Định nghĩa schema evolution và compatibility.
11. Cấu hình retention, purge và archive.
12. Bổ sung metrics, tracing, alert và reconciliation.
13. Kiểm thử crash window, duplicate, ordering và replay.
14. Triển khai theo từng consumer và theo dõi propagation lag.

### 23.1 Phân tách trách nhiệm

- Business service quyết định event nào có ý nghĩa nghiệp vụ.
- Oracle transaction lưu business state và outbox atomically.
- Relay chỉ vận chuyển event, không tự sửa nội dung nghiệp vụ.
- Broker lưu và phân phối message theo delivery semantics của nó.
- Consumer xác thực event, deduplicate và cập nhật local state.
- Reconciliation phát hiện sai lệch giữa source và projection.
- Operations quản lý backlog, retry, retention và incident.

Phân tách trách nhiệm giúp tránh việc relay chứa business logic hoặc consumer phải truy cập trực tiếp bảng nội bộ của producer.

## 24. Checklist thiết kế và vận hành

### Producer và outbox

- [ ] Business update và outbox insert nằm trong cùng transaction.
- [ ] Không dùng autonomous transaction cho event cần atomicity.
- [ ] Event ID ổn định qua mọi lần retry.
- [ ] Payload có event type và schema version.
- [ ] Aggregate ID/version có nếu cần ordering.
- [ ] Payload không chứa dữ liệu không cần thiết hoặc secret.
- [ ] Index và partition được thiết kế theo workload.
- [ ] Retention của outbox phù hợp replay window.

### Relay

- [ ] Chỉ phát event đã commit.
- [ ] Có cơ chế claim an toàn khi nhiều worker.
- [ ] Có lease expiry và cách thu hồi event bị treo.
- [ ] Không giữ row lock trong lúc gọi network.
- [ ] Publish trước, mark PUBLISHED sau.
- [ ] Retry có backoff và jitter.
- [ ] Có dead-letter/quarantine và quy trình replay.
- [ ] Theo dõi outbox age và backlog.
- [ ] Kiểm soát thứ tự theo aggregate nếu nghiệp vụ yêu cầu.

### Consumer

- [ ] Có idempotency key ổn định.
- [ ] Inbox và business effect cùng transaction.
- [ ] ACK broker sau commit.
- [ ] Unique constraint chống race condition.
- [ ] Phát hiện event cũ, duplicate và version gap.
- [ ] External side effect có idempotency riêng hoặc outbox tiếp theo.
- [ ] Inbox retention dài hơn replay window.

### Toàn hệ thống

- [ ] Event contract tương thích khi producer/consumer deploy lệch thời điểm.
- [ ] Có correlation/causation ID và tracing.
- [ ] Có metrics cho producer, broker và consumer.
- [ ] Có reconciliation và quy trình rebuild projection.
- [ ] Có quy trình xử lý dữ liệu nhạy cảm và retention.
- [ ] Đã thử crash sau publish, trước mark published.
- [ ] Đã thử crash sau consumer commit, trước ACK.
- [ ] Đã thử duplicate, out-of-order, broker outage và replay.

## 25. Kết luận

Transactional Outbox giải quyết dual write bằng cách lưu business update và event record trong cùng một transaction Oracle. Relay đọc các event đã commit rồi publish ra broker bằng polling hoặc CDC. Vì publish có thể được lặp lại khi timeout hoặc crash, hệ thống nên thiết kế theo at-least-once delivery và dùng idempotency để ngăn hiệu ứng nghiệp vụ bị lặp.

Inbox pattern, unique constraint và transaction local giúp consumer xử lý duplicate an toàn. Aggregate version, partition key và gap detection hỗ trợ ordering. Retry/backoff, dead-letter, retention, reconciliation, schema evolution và observability giúp pipeline vận hành được trong điều kiện lỗi thật.

Outbox không tạo ra consistency tức thời hoặc exactly-once end-to-end. Nó cung cấp một ranh giới bền vững giữa transaction nguồn và việc phát sự kiện. Khi mỗi service sở hữu transaction local, phát event có định danh ổn định và xử lý message theo cách idempotent, dữ liệu có thể được đồng bộ đáng tin cậy giữa các hệ thống mà không cần một transaction phân tán kéo dài qua mọi service.
