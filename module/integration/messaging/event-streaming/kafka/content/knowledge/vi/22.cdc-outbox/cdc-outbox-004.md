# Ánh xạ thao tác insert, update, delete và tombstone

CDC (Change Data Capture) đọc thay đổi đã xảy ra trong database và chuyển chúng thành record để hệ thống downstream xử lý. Khi một dòng được INSERT, UPDATE hoặc DELETE, connector CDC cần biểu diễn đúng thao tác, khóa bản ghi và trạng thái trước/sau thay đổi. Nếu ánh xạ sai, consumer có thể tạo dữ liệu trùng, giữ lại bản ghi đã bị xóa hoặc xóa nhầm dữ liệu.

Với Debezium, một change event thường có envelope gồm các phần before, after, source, op và timestamp. Thao tác DELETE còn có thể phát thêm một **tombstone record** có cùng key và value bằng null. Tombstone có ý nghĩa đặc biệt với topic dùng log compaction; nó khác với delete event mang đầy đủ thông tin thay đổi.

Bài này dùng Debezium làm ví dụ cụ thể cho cách ánh xạ CRUD, đồng thời giải thích snapshot, primary key, thứ tự event, SMT unwrap và cách phân biệt event nghiệp vụ trong Outbox với thao tác quản lý dòng outbox.

## 1. Từ thay đổi database đến CDC record

Giả sử bảng orders có các cột:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

Một transaction database có thể tạo ra các thay đổi:

- INSERT: thêm một đơn hàng mới.
- UPDATE: đổi trạng thái hoặc thông tin đơn hàng.
- DELETE: xóa một đơn hàng.

Connector CDC đọc transaction log của database, chẳng hạn PostgreSQL WAL hoặc MySQL binlog, rồi chuyển thay đổi thành record Kafka. Cách capture từ transaction log giúp connector quan sát thay đổi đã commit mà không cần ứng dụng tự gửi thêm một message cho từng câu SQL.

~~~mermaid
flowchart LR
    APP["Ứng dụng"] --> DB["Database transaction"]
    DB --> LOG["WAL / Binlog"]
    LOG --> CDC["CDC connector"]
    CDC --> TOPIC["Kafka topic"]
    TOPIC --> CONSUMER["Downstream consumer"]
~~~

Trong mô hình này, Kafka record là biểu diễn của thay đổi database. Một record CDC không nhất thiết tương đương một câu SQL nguyên văn: connector có thể chuẩn hóa dữ liệu, thêm metadata, gộp hoặc chia thay đổi theo transaction và cấu hình.

## 2. Debezium change event envelope

Với định dạng envelope mặc định, một Debezium change event thường có các thành phần:

| Trường | Ý nghĩa |
|---|---|
| before | Ảnh chụp dữ liệu trước thay đổi; có thể null tùy thao tác |
| after | Ảnh chụp dữ liệu sau thay đổi; có thể null tùy thao tác |
| source | Metadata về nguồn: connector, database, schema/table, vị trí log và thông tin snapshot/transaction tùy connector |
| op | Mã thao tác: c, u, d hoặc r trong các event CRUD/snapshot thông dụng |
| ts_ms | Thời điểm connector xử lý/ghi nhận event theo đồng hồ của connector |

Mức độ đầy đủ của before phụ thuộc database và cấu hình capture. Ví dụ với PostgreSQL, REPLICA IDENTITY mặc định thường chỉ cung cấp old key cho một số thay đổi; nếu cần toàn bộ ảnh chụp trước UPDATE/DELETE, có thể phải cấu hình REPLICA IDENTITY FULL cho bảng và đánh giá chi phí WAL. Không giả định before luôn có đầy đủ mọi cột.

Ví dụ dưới đây là payload minh họa đã lược bỏ nhiều trường source phụ thuộc database và phiên bản:

~~~json
{
  "before": null,
  "after": {
    "id": 501,
    "customer_id": 72,
    "status": "NEW",
    "total_amount": 1250000.00
  },
  "source": {
    "connector": "postgresql",
    "db": "commerce",
    "schema": "public",
    "table": "orders",
    "snapshot": "false"
  },
  "op": "c",
  "ts_ms": 1732000000000
}
~~~

Không phải connector CDC nào cũng dùng envelope hoặc các mã op giống Debezium. Nếu dùng connector khác, hãy đọc schema event và tài liệu của plugin thay vì mặc định suy ra op từ tên field.

## 3. Ánh xạ INSERT

Khi database thêm một dòng mới, Debezium phát change event với:

- op = c (create).
- before = null vì dòng chưa có trạng thái trước đó.
- after chứa toàn bộ giá trị dòng sau khi INSERT.
- Kafka record key thường được tạo từ primary key của dòng.

Ví dụ SQL:

~~~sql
INSERT INTO orders (
    id, customer_id, status, total_amount, updated_at
)
VALUES (
    501, 72, 'NEW', 1250000.00, CURRENT_TIMESTAMP
);
~~~

Ví dụ key/value:

~~~text
Kafka key:
{"id": 501}

Kafka value:
{
  "before": null,
  "after": {
    "id": 501,
    "customer_id": 72,
    "status": "NEW",
    "total_amount": 1250000.00
  },
  "op": "c"
}
~~~

Consumer xây dựng projection có thể dùng after để tạo bản ghi mới trong read model. Nếu nhận lại cùng event do replay, consumer vẫn cần cơ chế idempotency hoặc upsert theo khóa ổn định.

INSERT không tạo tombstone. Tombstone không phải dấu hiệu chung cho mọi record mới; nó chủ yếu được dùng để biểu diễn việc xóa key trong log-compacted topic.

## 4. Ánh xạ UPDATE

Khi database cập nhật một dòng, Debezium phát event với:

- op = u (update).
- before chứa ảnh chụp trước thay đổi nếu connector/database cung cấp.
- after chứa ảnh chụp sau thay đổi.
- Key thường giữ nguyên nếu primary key không đổi.

Ví dụ SQL:

~~~sql
UPDATE orders
SET status = 'PAID',
    updated_at = CURRENT_TIMESTAMP
WHERE id = 501;
~~~

Ví dụ event:

~~~json
{
  "before": {
    "id": 501,
    "customer_id": 72,
    "status": "NEW",
    "total_amount": 1250000.00
  },
  "after": {
    "id": 501,
    "customer_id": 72,
    "status": "PAID",
    "total_amount": 1250000.00
  },
  "op": "u"
}
~~~

Consumer có thể chọn một trong hai cách:

- State projection: dùng after để ghi đè trạng thái hiện tại của order 501.
- Audit/history: lưu before, after và metadata để truy vết thay đổi.

Nếu chỉ cần trạng thái mới nhất, upsert theo primary key thường phù hợp. Nếu cần lịch sử, phải lưu từng event theo định danh/offset hoặc transaction metadata thay vì ghi đè dòng cũ.

UPDATE thông thường không tạo tombstone. Khi một trường chuyển thành null, đó là giá trị null của field trong after, không phải tombstone Kafka. Tombstone là record có toàn bộ value bằng null.

## 5. Ánh xạ DELETE

Khi database xóa một dòng, Debezium thường phát delete event:

- op = d (delete).
- before chứa các trường cũ mà database/connector cung cấp; có thể không phải toàn bộ cột.
- after = null vì dòng không còn trạng thái sau thao tác.
- Key giữ primary key của dòng bị xóa.

Ví dụ SQL:

~~~sql
DELETE FROM orders
WHERE id = 501;
~~~

Ví dụ delete event:

Payload dưới đây giả định database cung cấp đầy đủ before image:

~~~json
{
  "before": {
    "id": 501,
    "customer_id": 72,
    "status": "PAID",
    "total_amount": 1250000.00
  },
  "after": null,
  "op": "d"
}
~~~

Delete event vẫn có value là một envelope chứa before, after, source và op. Consumer đọc được event này có thể thực hiện nghiệp vụ như xóa order khỏi projection hoặc ghi audit record.

Sau delete event, Debezium thường phát thêm một tombstone record cho cùng key nếu cấu hình tombstone được bật. Hai record này có vai trò khác nhau:

1. Delete event: thông báo có thao tác DELETE và mang metadata/dữ liệu trước khi xóa.
2. Tombstone: record có cùng key nhưng value = null, báo cho log compaction rằng key này đã bị xóa khỏi trạng thái hiện tại.

Debezium có cấu hình tombstones.on.delete để điều khiển việc phát tombstone sau delete event. Hãy xác nhận giá trị hiệu lực và hành vi của connector/phiên bản đang dùng; nếu tắt tombstone, consumer vẫn có thể nhận delete envelope nhưng log compaction không nhận được marker null để loại bỏ key cũ.

## 6. Tombstone là gì?

Trong Kafka, tombstone là một record có key và value null:

~~~text
key   = {"id": 501}
value = null
~~~

Tombstone không có envelope before/after/op. Nó không phải JSON object có trường value bằng null; toàn bộ Kafka record value phải là null.

Với topic bật log compaction, Kafka giữ giá trị mới nhất theo key. Tombstone đánh dấu key không còn thuộc trạng thái hiện tại. Khi log cleaner xử lý segment, các giá trị cũ của key đó có thể bị loại bỏ; tombstone cũng được giữ trong một khoảng thời gian theo delete retention rồi có thể bị loại bỏ.

Cấu hình topic tối thiểu để bật compaction:

~~~properties
cleanup.policy=compact
delete.retention.ms=86400000
~~~

Giá trị delete.retention.ms ở trên chỉ là ví dụ một ngày, không phải khuyến nghị chung. Hãy chọn thời gian giữ tombstone theo tốc độ consumer cần khôi phục, thời gian gián đoạn tối đa và yêu cầu đồng bộ state. Topic có thể dùng cleanup.policy=compact,delete nếu cần vừa compaction vừa giới hạn retention theo thời gian/dung lượng.

~~~mermaid
sequenceDiagram
    participant DB as Database
    participant C as CDC Connector
    participant K as Compacted Topic
    participant R as Read Model
    DB->>C: DELETE orders id=501
    C->>K: Key 501, value = delete envelope
    K->>R: Delete event (op=d)
    C->>K: Key 501, value = null
    K->>R: Tombstone
    Note over K: Log compaction dùng tombstone<br/>để loại bỏ giá trị cũ của key
~~~

Tombstone hữu ích khi topic biểu diễn changelog hoặc trạng thái hiện tại theo key, ví dụ compacted topic dùng để khôi phục cache, table hoặc state store. Nó cho phép log compaction loại bỏ value cũ của key đã bị xóa.

### Delete event và tombstone không thay thế nhau

| Đặc điểm | Delete event | Tombstone |
|---|---|---|
| Key | Primary key của dòng bị xóa | Cùng key với delete event |
| Value | Envelope CDC, after = null, op = d | Null hoàn toàn |
| Mang dữ liệu before | Có thể có | Không |
| Mang metadata source/op | Có | Không |
| Mục đích | Thông báo thay đổi dữ liệu cho ứng dụng | Đánh dấu key bị xóa cho log compaction/state |
| Có thể ghi audit | Có | Không đủ thông tin để audit |

Nếu consumer chỉ xử lý event có JSON value, cần xử lý riêng record value null để tránh lỗi deserialize hoặc NullPointerException.

## 7. Vì sao tombstone quan trọng với log compaction?

Giả sử topic compacted có các record theo key 501:

~~~text
offset 10: key=501, value={status: "NEW"}
offset 18: key=501, value={status: "PAID"}
offset 25: key=501, value=null
~~~

Trước khi compaction chạy, consumer đọc từ đầu log có thể nhìn thấy cả ba record. Sau khi log cleaner xử lý, các value cũ của key 501 có thể bị loại bỏ; tombstone được giữ trong khoảng delete retention để consumer có thời gian quan sát việc xóa. Sau thời gian này, tombstone cũng có thể bị xóa khỏi log.

Vì vậy:

- Không giả định tombstone được lưu vĩnh viễn.
- Consumer cần bắt kịp log trong khoảng retention phù hợp nếu cần quan sát delete.
- Topic compacted không phải database backup đầy đủ hoặc audit log bất biến.
- Nếu cần lịch sử mọi thao tác, dùng topic/event store có retention phù hợp thay vì chỉ dựa vào compaction.

Compaction là tiến trình bất đồng bộ. Ngay sau khi producer ghi tombstone, record cũ chưa chắc đã bị loại khỏi segment vật lý.

## 8. Primary key quyết định key của Kafka record

Key có vai trò quan trọng vì Kafka chỉ bảo đảm thứ tự trong một partition. Nếu các thay đổi của cùng một entity dùng cùng key, chúng thường được định tuyến đến cùng partition theo partitioner, giúp consumer nhận đúng thứ tự của partition đó.

Ví dụ:

~~~text
key={"id":501}, value=INSERT event
key={"id":501}, value=UPDATE event
key={"id":501}, value=DELETE event
key={"id":501}, value=null
~~~

Nếu key không ổn định hoặc bị bỏ trống, các thay đổi của cùng order có thể rơi vào nhiều partition khác nhau. Khi đó consumer không thể dựa vào thứ tự partition để tái dựng trạng thái entity.

Với bảng không có primary key, connector có thể yêu cầu cấu hình khóa thay thế hoặc tạo key từ unique columns. Cần bảo đảm key ổn định và duy nhất theo vòng đời entity. Không dùng một trường dễ thay đổi như status làm key.

Đặc biệt, Kafka log compaction cần key không null. Nếu record CDC không có key ổn định, tombstone không thể xác định chính xác value cũ cần loại bỏ. Với bảng không có primary key, hãy chọn khóa thay thế có tính duy nhất và cấu hình connector tạo record key phù hợp trước khi dùng topic như changelog compacted.

### Khi primary key thay đổi

Thay đổi primary key không đơn giản là update value dưới cùng một key. Với Debezium, tùy connector/database, thay đổi khóa thường được biểu diễn như xóa key cũ (delete event và có thể tombstone) rồi tạo key mới. Downstream cần xử lý cả hai phía để không giữ bản ghi cũ và không bỏ qua bản ghi mới.

Không giả định mọi connector biểu diễn primary-key update giống hệt nhau. Hãy kiểm tra event thực tế của database và connector đang sử dụng.

### Khi cần before image đầy đủ

Nếu downstream cần so sánh toàn bộ giá trị trước/sau, hãy kiểm tra khả năng database ghi old row vào transaction log:

- PostgreSQL: kiểm tra REPLICA IDENTITY của bảng; FULL ghi nhận ảnh chụp đầy đủ hơn nhưng làm tăng lượng dữ liệu WAL.

~~~sql
ALTER TABLE orders REPLICA IDENTITY FULL;
~~~

- MySQL: kiểm tra binlog format và row image; row image FULL thường cung cấp đủ cột hơn MINIMAL.

~~~ini
binlog_format=ROW
binlog_row_image=FULL
~~~

- Database khác: kiểm tra chế độ supplemental logging hoặc cấu hình log capture tương ứng.

Nếu connector chỉ nhận được primary key trong before, không thể tự suy ra giá trị cũ của các cột còn lại nếu không truy vấn nguồn bổ sung. Truy vấn bổ sung có thể trả về trạng thái hiện tại sau thay đổi, không phải before image tại thời điểm event.

## 9. Snapshot và mã thao tác r

Khi connector bắt đầu capture, database có thể đã chứa nhiều dòng trước khi CDC được bật. Connector cần snapshot để đưa trạng thái hiện tại ban đầu vào Kafka, sau đó tiếp tục đọc transaction log.

Với Debezium, snapshot record thường có:

- op = r (read).
- before = null.
- after chứa dữ liệu hiện tại của dòng được đọc từ snapshot.
- source metadata đánh dấu event thuộc snapshot theo cách phụ thuộc connector/phiên bản.

Ví dụ:

~~~json
{
  "before": null,
  "after": {
    "id": 501,
    "customer_id": 72,
    "status": "PAID",
    "total_amount": 1250000.00
  },
  "op": "r"
}
~~~

op = r không có nghĩa database vừa INSERT dòng đó. Đây là record được đọc trong snapshot để khởi tạo trạng thái downstream. Consumer xây dựng read model thường xử lý snapshot event gần giống upsert, nhưng có thể phân biệt nó với thay đổi mới phát sinh từ transaction log.

Snapshot và streaming phase phải phối hợp để không bỏ sót hoặc nhân đôi thay đổi xảy ra trong lúc snapshot. Debezium quản lý ranh giới này theo cơ chế snapshot và offset của từng connector; không tự ghép snapshot bằng cách query database tùy ý rồi bật CDC sau đó mà không có điểm đồng bộ.

## 10. Ánh xạ CRUD vào read model

Một consumer xây dựng bảng orders_current có thể ánh xạ như sau:

| CDC operation | before | after | Hành động read model |
|---|---|---|---|
| c (create) | null | Dòng mới | INSERT hoặc UPSERT theo key |
| u (update) | Dòng cũ | Dòng mới | UPSERT trạng thái mới |
| d (delete) | Dòng trước xóa | null | DELETE theo key |
| r (snapshot read) | null | Dòng hiện tại | INSERT hoặc UPSERT để khởi tạo state |
| Tombstone | Không có envelope | Value null | Xóa key khỏi state nếu consumer dùng semantics compacted changelog |

Ví dụ logic xử lý:

~~~java
switch (event.op()) {
    case "c", "u", "r" -> repository.upsert(event.after());
    case "d" -> repository.deleteById(event.before().id());
    default -> throw new IllegalArgumentException(
        "Unsupported CDC operation: " + event.op()
    );
}
~~~

Đoạn code giả định đã deserialize envelope và value không phải tombstone. Consumer thực tế phải kiểm tra record value null trước khi truy cập event.op(); tombstone không có trường op.

Ví dụ kiểm tra tombstone trước khi deserialize envelope:

~~~java
public void handle(ConsumerRecord<OrderKey, byte[]> record) {
    if (record.value() == null) {
        if (record.key() != null) {
            repository.deleteById(record.key().id());
        }
        return;
    }

    DebeziumOrderEvent event = deserialize(record.value());
    switch (event.op()) {
        case "c", "u", "r" -> repository.upsert(event.after());
        case "d" -> repository.deleteById(record.key().id());
        default -> throw new IllegalArgumentException(
            "Unsupported CDC operation: " + event.op()
        );
    }
}
~~~

Mẫu này giả định topic chỉ chứa Debezium CDC record theo key OrderKey và consumer muốn duy trì trạng thái hiện tại. Nếu ứng dụng cần audit, không nên bỏ qua delete envelope chỉ vì tombstone đến sau; hãy xử lý envelope trước để lưu thông tin before và metadata, rồi xử lý tombstone theo yêu cầu state/compaction.

Nếu dùng ExtractNewRecordState để unwrap envelope, consumer có thể chỉ nhận row state thay vì before/after/op đầy đủ. Khi đó cần cấu hình rõ cách giữ metadata và xử lý delete/tombstone; nếu transform loại bỏ delete marker, downstream có thể không biết phải xóa dòng nào.

## 11. Unwrap envelope bằng Debezium SMT

Một số sink connector mong muốn nhận row data trực tiếp thay vì envelope Debezium. Debezium cung cấp transform ExtractNewRecordState để lấy nội dung after và chuyển record sang dạng phẳng hơn.

Tên class:

~~~properties
transforms=unwrap
transforms.unwrap.type=io.debezium.transforms.ExtractNewRecordState
~~~

Khi dùng unwrap:

- INSERT và UPDATE thường trở thành record chứa row sau thay đổi.
- Snapshot read cũng thường trở thành row state.
- DELETE và tombstone cần được xử lý theo chế độ delete handling của phiên bản Debezium đang dùng.
- Metadata như op, source table hoặc transaction ID có thể cần được thêm vào record/header trước khi envelope bị loại.

Các phiên bản Debezium có các lựa chọn cấu hình delete handling khác nhau. Một số chế độ có thể drop tombstone, rewrite delete thành record có marker, hoặc giữ tombstone. Hãy kiểm tra tài liệu đúng phiên bản và thử cả delete envelope lẫn tombstone trước khi đưa transform vào production.

Nếu downstream cần audit, before/after hoặc phân biệt c/u/d/r, giữ envelope thường phù hợp hơn. Nếu downstream chỉ cần trạng thái mới nhất của row, unwrap có thể đơn giản hóa tích hợp nhưng cần bảo toàn delete semantics.

## 12. Ánh xạ Outbox event khác với CDC CRUD thông thường

Transactional Outbox dùng một bảng riêng để lưu event nghiệp vụ trong cùng transaction database với thay đổi dữ liệu chính.

Ví dụ:

~~~sql
CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregatetype VARCHAR(100) NOT NULL,
    aggregateid VARCHAR(100) NOT NULL,
    type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Một transaction nghiệp vụ có thể vừa cập nhật đơn hàng vừa thêm event vào outbox:

~~~sql
BEGIN;

UPDATE orders
SET status = 'PAID',
    updated_at = CURRENT_TIMESTAMP
WHERE id = 501;

INSERT INTO outbox_event (
    id, aggregatetype, aggregateid, type, payload
)
VALUES (
    '2f5d8a20-9b77-4c0a-ae31-0d67f2f0a501',
    'Order',
    '501',
    'OrderPaid',
    '{"orderId":501,"status":"PAID"}'
);

COMMIT;
~~~

Nếu transaction commit, cả thay đổi orders và outbox event cùng tồn tại. Nếu rollback, cả hai cùng rollback. CDC connector đọc transaction log rồi đưa bản ghi outbox mới vào Kafka; ứng dụng không cần tự dual-write database và Kafka trong hai thao tác độc lập.

Với Debezium Outbox Event Router, cấu hình thường ánh xạ:

| Cột outbox | Vai trò thường dùng |
|---|---|
| id | Định danh duy nhất của event |
| aggregatetype | Loại aggregate và cơ sở định tuyến topic |
| aggregateid | Khóa aggregate, thường dùng làm Kafka key |
| type | Loại event nghiệp vụ |
| payload | Nội dung event được phát ra |

Chi tiết tên cột và cách định tuyến có thể tùy chỉnh trong Outbox Event Router. Cần kiểm tra cấu hình thực tế của SMT và schema outbox.

### Insert, update, delete trên bảng outbox

Trong thiết kế outbox phổ biến, INSERT một dòng outbox biểu diễn một event nghiệp vụ mới. Ví dụ insert OrderPaid tạo event OrderPaid.

UPDATE hoặc DELETE dòng outbox thường là thao tác quản trị/retention, ví dụ đánh dấu đã xử lý hoặc dọn bản ghi cũ. Chúng không mặc nhiên là event nghiệp vụ mới và không nên bị ánh xạ thành OrderUpdated hay OrderDeleted nếu domain không định nghĩa như vậy.

Nếu cần phát event OrderCancelled, ứng dụng nên INSERT một dòng outbox mới có type OrderCancelled trong cùng transaction với cập nhật trạng thái đơn hàng. Không dùng DELETE dòng outbox cũ để biểu diễn hủy đơn hàng.

Khi dọn dẹp outbox, cần bảo đảm connector đã capture các INSERT cần thiết và offset đã được lưu an toàn trước khi xóa dữ liệu nguồn. Cấu hình filter/routing phải loại các thao tác housekeeping khỏi luồng domain event nếu không muốn downstream nhận chúng.

Nếu connector bắt đầu bằng initial snapshot trên một outbox table đã có dữ liệu, cần xác định rõ các dòng cũ có phải phát lại như event hay không. Hành vi snapshot và Outbox Event Router phụ thuộc cấu hình/phiên bản; dùng event ID ổn định để deduplicate và chọn snapshot policy phù hợp để tránh phát lại nghiệp vụ ngoài ý muốn.

## 13. Ordering và transaction metadata

Kafka bảo đảm thứ tự trong từng partition, không bảo đảm thứ tự toàn cục giữa mọi partition. Để giữ thứ tự thay đổi của một entity:

- Dùng primary key hoặc aggregate ID làm Kafka key.
- Đảm bảo mọi event của cùng entity đi vào cùng topic/partition.
- Không thay key tùy tiện giữa các lần update.
- Tránh tăng partition hoặc thay partitioner mà không đánh giá ảnh hưởng đến mapping key-partition.

Ví dụ order 501 có chuỗi:

~~~text
OrderCreated -> OrderPaid -> OrderShipped -> OrderDelivered
~~~

Nếu tất cả event dùng key 501, chúng được đưa về cùng partition theo partitioner thông thường và giữ thứ tự append trong partition. Event của order 502 có thể nằm ở partition khác và được xử lý song song.

CDC connector có thể bổ sung transaction metadata hoặc source log position để hỗ trợ xác định thứ tự/ranh giới transaction. Tên trường và độ chính xác phụ thuộc connector/database. Nếu cần bảo toàn quan hệ giữa nhiều row thay đổi trong cùng một database transaction, hãy bật và sử dụng transaction metadata theo tài liệu connector; chỉ dựa vào ts_ms có thể không đủ vì timestamp có thể trùng và không phải thứ tự commit duy nhất.

## 14. Kiểm thử ánh xạ insert, update, delete và tombstone

Trước khi tích hợp sink hoặc read model, hãy tạo bộ kiểm thử có thể tái lập:

1. INSERT một dòng và xác nhận op=c, key và after.
2. UPDATE một vài cột và xác nhận op=u, before/after.
3. UPDATE một cột thành null và xác nhận đó là field null trong after, không phải tombstone.
4. DELETE dòng và xác nhận op=d, before, after=null.
5. Xác nhận tombstone có cùng key và value=null nếu connector được cấu hình phát tombstone.
6. Bật log compaction trên topic thử nghiệm và quan sát hành vi sau khi cleaner chạy.
7. Chạy snapshot lần đầu và xác nhận event op=r không bị hiểu nhầm là INSERT mới.
8. Thử thay đổi primary key nếu schema cho phép và quan sát chuỗi event của connector.
9. Thử unwrap SMT với cả delete envelope và tombstone.
10. Với outbox, insert event nghiệp vụ rồi dọn record cũ; xác nhận thao tác cleanup không phát nhầm domain event.

Không chỉ kiểm tra JSON value. Hãy kiểm tra cả Kafka key, partition, offset, headers, timestamp và value null. Một tombstone có thể bị bỏ qua nếu công cụ xem record chỉ in value hoặc deserialize null không đúng cách.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Consumer không biết record bị xóa | Chỉ xử lý after và bỏ qua op=d | Xử lý delete envelope hoặc cấu hình unwrap giữ delete marker |
| Deserialize lỗi khi gặp delete | Consumer giả định mọi value đều là JSON | Kiểm tra value null trước khi parse |
| Bản ghi cũ vẫn còn trong compacted topic | Tombstone chưa được log cleaner xử lý hoặc delete retention chưa hết | Kiểm tra cleanup policy, cleaner và delete retention |
| Read model giữ dữ liệu đã xóa | Sink không xử lý tombstone hoặc delete event | Kiểm tra semantics của sink và key mapping |
| Event cùng entity đến sai thứ tự | Key không ổn định hoặc event nằm ở nhiều partition | Dùng primary key/aggregate ID làm Kafka key |
| Snapshot bị coi là insert mới | Consumer không phân biệt op=r với op=c | Xử lý snapshot như upsert/initial state |
| Outbox cleanup bị hiểu là domain delete | Route mọi thao tác CDC của bảng outbox | Chỉ phát event nghiệp vụ theo thiết kế, thường là INSERT; lọc thao tác housekeeping |
| Primary-key update để lại row cũ | Consumer chỉ xử lý key mới | Kiểm tra chuỗi delete key cũ/tombstone và create key mới |

## 16. Bài tập tự kiểm tra

1. Debezium dùng những mã op nào cho create, update, delete và snapshot read?
2. Với DELETE, vì sao before có dữ liệu nhưng after là null?
3. Tombstone khác delete envelope ở key, value và mục đích như thế nào?
4. Vì sao tombstone cần cùng key với record đã bị xóa?
5. Tombstone được log compaction sử dụng ra sao và vì sao nó không tồn tại vĩnh viễn?
6. Vì sao UPDATE một field thành null không đồng nghĩa tombstone?
7. Vì sao primary key nên được dùng làm Kafka key cho CDC event?
8. Snapshot event op=r nên được áp dụng vào read model như thế nào?
9. ExtractNewRecordState có thể làm mất thông tin nào nếu cấu hình delete handling không phù hợp?
10. Vì sao xóa một dòng outbox để cleanup không nên tự động trở thành domain event?

## Kết luận

Ánh xạ CDC cần giữ đúng ý nghĩa của thao tác database và khóa entity. Với Debezium, INSERT thường có op=c, before=null và after là dòng mới; UPDATE có op=u cùng before/after; DELETE có op=d, before là dòng cũ và after=null; snapshot read có op=r để khởi tạo trạng thái.

Sau delete event, tombstone có thể được phát với cùng key và value=null. Delete envelope thông báo thay đổi cho ứng dụng; tombstone đánh dấu key bị xóa để log compaction loại bỏ value cũ. Khi dùng unwrap SMT hoặc Outbox Event Router, cần bảo toàn delete semantics và phân biệt event nghiệp vụ được INSERT vào outbox với thao tác UPDATE/DELETE dùng cho quản trị, cleanup. Hãy kiểm thử key, value null, partition, offset và thứ tự event trước khi đưa luồng CDC vào production.
