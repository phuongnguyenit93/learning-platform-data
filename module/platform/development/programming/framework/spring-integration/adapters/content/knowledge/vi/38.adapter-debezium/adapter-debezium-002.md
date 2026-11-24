# Change event payload trong Spring Integration Debezium

## 1. Bối cảnh: một thay đổi database đi qua Spring Message như thế nào?

Giả sử một bảng `public.orders` trong PostgreSQL đang có đơn hàng `ORD-101`. Ứng dụng cập nhật trạng thái đơn hàng từ `CREATED` thành `PAID`. Debezium đọc thay đổi từ log giao dịch và tạo **change event** có thể chứa khóa hàng, trạng thái trước/sau, loại thao tác và metadata nguồn. Spring Integration Debezium inbound adapter chuyển event này vào một `MessageChannel` để các thành phần downstream như transformer, router, gateway, JDBC/Kafka/JMS outbound adapter xử lý.

~~~mermaid
flowchart LR
    A["BEGIN / UPDATE orders / COMMIT"] --> B[("PostgreSQL WAL")]
    B --> C["Debezium connector"]
    C --> D["ChangeEvent KEY + VALUE"]
    D --> E["DebeziumMessageProducer"]
    E --> F["Message<byte[]> + headers"]
    F --> G["Parse → Normalize → Validate"]
    G --> H["Route c/u/d/r"]
    H --> I["JDBC read model / Inbox / Kafka / JMS"]
~~~

Điểm dễ nhầm là **`ChangeEvent` không chỉ có một JSON payload**. Nó thường chứa **key**, **value** và **destination** riêng; bên trong value còn có **envelope** chỉ rõ loại thay đổi và metadata nguồn. Sau khi Spring Integration ánh xạ, nhiều phần thông tin nằm trong **message headers**, không phải mọi thứ đều ở `message.payload`.

Bài **Change event payload** thuộc chương **Adapter Debezium** của module **SPRING_INTEGRATION_ADAPTERS**. Module tập trung kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành với file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, xử lý hợp đồng message, lỗi và vòng đời kết nối. Bài này đi sâu vào **hợp đồng dữ liệu CDC**, không phải hướng dẫn triển khai Kafka Connect cluster.

Sau bài học, bạn có thể đọc một change event chuẩn, phân biệt snapshot với streaming, DELETE với tombstone, cấu hình JSON/schema và parse an toàn trong Spring Integration; đồng thời xây hợp đồng idempotency, routing, kiểm thử và quan sát khi payload phát triển qua nhiều phiên bản.

## 2. Từ database row đến ChangeEvent, rồi đến Spring Message

Một row change event của Debezium có thể mô tả bằng ba thành phần:

| Thành phần Debezium Engine | Ý nghĩa | Vị trí thường thấy trong Spring Integration |
|---|---|---|
| `ChangeEvent.key()` | Khóa record theo bảng/connector, có thể null | Header `DebeziumHeaders.KEY`, thường là `byte[]` khi dùng JSON byte-array |
| `ChangeEvent.value()` | Envelope change-event đã serialize hoặc tombstone | `Message.getPayload()`, thường `byte[]` ở single-event mode |
| `ChangeEvent.destination()` | Destination/topic logic do connector đặt | Header `DebeziumHeaders.DESTINATION` |
| `ChangeEvent.headers()` | Các headers bổ sung do source/SMT tạo | Header mapper quyết định phần được map |
| `MessageHeaders.ID/TIMESTAMP` | Metadata do Spring Messaging tạo | **Không phải** DB LSN/txId/op mặc định |

~~~text
Debezium ChangeEvent<byte[],byte[]>
  key()         = {"schema": {...}, "payload": {"id": 101}}
  value()       = {"schema": {...}, "payload": {"before":..., "after":..., "op":"u"}}
  destination() = "orders_source.public.orders"
                   |
                   v
Spring Message:
  payload: byte[] chứa JSON VALUE
  headers:
    DebeziumHeaders.KEY         -> byte[] chứa JSON KEY
    DebeziumHeaders.DESTINATION -> "orders_source.public.orders"
    id, timestamp              -> Spring Message metadata
~~~

**Lưu ý:** dạng hiển thị trên là ví dụ JSON decoded để dễ đọc; trong Java, dữ liệu thực thường là bytes. Với converter/serializer khác, key/value có thể không phải bytes JSON. Nếu bảng không có primary/unique key hoặc một operation không có record key, header key có thể không tồn tại hoặc chứa giá trị rỗng. Không cast cưỡng bức mọi header thành `byte[]`.

## 3. Chọn API và phiên bản tương thích

Spring Integration cung cấp `DebeziumMessageProducer` và Java DSL `Debezium.inboundChannelAdapter(...)` từ **Spring Integration 6.2**. Trong ví dụ chuẩn dùng `DebeziumEngine.Builder<ChangeEvent<byte[],byte[]>>` khi Engine chọn định dạng `JsonByteArray`. Factory Java DSL cũng nhận `java.util.Properties` rồi cấu hình JSON serialization phù hợp.

| API | Package | Vai trò |
|---|---|---|
| `DebeziumMessageProducer` | `org.springframework.integration.debezium.inbound` | Chuyển Debezium events thành Spring messages |
| `Debezium.inboundChannelAdapter(...)` | `org.springframework.integration.debezium.dsl` | DSL factory tạo inbound endpoint |
| `DebeziumHeaders.KEY` | `org.springframework.integration.debezium.support` | Tên header key của CDC record |
| `DebeziumHeaders.DESTINATION` | Cùng `DebeziumHeaders` | Tên header destination logic |
| `ChangeEvent<K,V>` | `io.debezium.engine` | Event từ Debezium Engine |
| `DebeziumEngine.create(JsonByteArray.class)` | Debezium Engine | Chọn key/value ở dạng JSON `byte[]` |
| `ObjectMapper/JsonNode` | Jackson | Parse JSON value/key sau khi kiểm tra kiểu |

**Không áp dụng máy móc** ví dụ JDBC Java DSL được giới thiệu ở Spring Integration 7.0 vào Debezium. Các API có lịch sử phiên bản riêng. Đối chiếu BOM, Spring Integration, Debezium Engine và connector version tương thích trước khi chạy.

### 3.1. Dependencies minh họa

~~~groovy
// Đoạn Gradle: chọn Debezium connector version tương thích
// với Spring Integration/BOM đang chạy.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-debezium'
    implementation 'org.springframework.boot:spring-boot-starter-json'

    runtimeOnly 'io.debezium:debezium-connector-postgres:COMPATIBLE_VERSION'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`COMPATIBLE_VERSION` là placeholder phải được thay bằng version được chốt trong dependency management, **không** phải bản build chạy nguyên văn. Cần connector tương ứng với database; có `spring-integration-debezium` không có nghĩa đã mang theo mọi connector.

## 4. Key/value là hai tài liệu JSON khác nhau

Debezium với JSON converter có thể tạo schema wrapper cho **cả key và value**. Ví dụ một row có khóa chính `id=101`:

~~~json
{
  "schema": {
    "type": "struct",
    "name": "orders_source.public.orders.Key",
    "fields": [
      {"type": "int64", "field": "id", "optional": false}
    ]
  },
  "payload": {
    "id": 101
  }
}
~~~

Đây là **JSON của key**, không phải value của row.

Một event value CREATE rút gọn:

~~~json
{
  "schema": {
    "type": "struct",
    "name": "orders_source.public.orders.Envelope"
  },
  "payload": {
    "before": null,
    "after": {
      "id": 101,
      "status": "CREATED",
      "total_cents": 120000
    },
    "source": {
      "connector": "postgresql",
      "db": "appdb",
      "schema": "public",
      "table": "orders",
      "snapshot": "false",
      "lsn": 26504000
    },
    "op": "c",
    "ts_ms": 1730000000123
  }
}
~~~

Các `schema` trong JSON phía trên được **lược bớt fields**; chúng minh họa cấu trúc, không phải bản sao đầy đủ output của một Debezium version. Một envelope thực có thể chứa `ts_us`, `ts_ns`, `transaction`, `source.ts_ms` và nhiều fields khác.

**Không parse `message.payload` để lấy `key.id` theo cách mặc định**: event key nằm riêng và Spring Integration thường map nó vào header `DebeziumHeaders.KEY`. Khi có UPDATE thay đổi primary key, key cũ và key mới có thể xuất hiện ở các events khác nhau.

## 5. JSON schema wrapper có thể bật hoặc tắt

Một cách biểu diễn JSON thường có wrapper:

~~~json
{
  "schema": { "type": "struct", "name": "orders.Envelope" },
  "payload": {
    "before": null,
    "after": {"id": 101, "status": "CREATED"},
    "source": {"connector": "postgresql", "table": "orders"},
    "op": "c",
    "ts_ms": 1730000000123
  }
}
~~~

Khi cấu hình `value.converter.schemas.enable=false`, **đối với JSON converter hỗ trợ tùy chọn này**, dạng value có thể bỏ wrapper:

~~~json
{
  "before": null,
  "after": {"id": 101, "status": "CREATED"},
  "source": {"connector": "postgresql", "table": "orders"},
  "op": "c",
  "ts_ms": 1730000000123
}
~~~

Tương tự, `key.converter.schemas.enable=false` có thể làm key JSON chỉ còn object chứa cột khóa:

~~~json
{"id": 101}
~~~

**Không suy luận rằng tất cả serializers đều áp dụng hai properties này giống nhau.** Với `JsonByteArray`, `Json`, Kafka Connect `JsonConverter`, Avro/Protobuf/JSON Schema converter và các major versions, phải kiểm tra chính xác cấu hình và bytes thực. Bài sử dụng parser chịu được **cả wrapper và dạng bỏ wrapper**; nhưng nếu input không phải JSON, cần deserializer khác.

## 6. Envelope của row change: hợp đồng tối thiểu

Sau khi tách wrapper, row-change envelope thường chứa:

| Trường | Ý nghĩa | Có thể thiếu/null? |
|---|---|---|
| `before` | Ảnh của row trước sự kiện | Có; CREATE/SNAPSHOT null, UPDATE phụ thuộc DB |
| `after` | Ảnh của row sau sự kiện | Có; DELETE null, TRUNCATE không là row change |
| `op` | Mã thao tác `r/c/u/d`; thêm `t/m` khi connector hỗ trợ | Bắt buộc cho row change envelope, không phải mọi control record |
| `source` | Metadata về nguồn DB/schema/table/log | Các fields bên trong phụ thuộc connector |
| `ts_ms` | Timestamp xử lý event (milliseconds) | Có thể null/thiếu tùy event |
| `ts_us/ts_ns` | Timestamp độ phân giải cao hơn | Tùy Debezium/connector version |
| `transaction` | Metadata transaction khi bật | Thường null nếu chưa bật |
| `source.snapshot` | Thông tin snapshot từ connector | Có thể boolean, chuỗi hoặc null theo output/serializer |

Ví dụ UPDATE:

~~~json
{
  "before": {"id": 101},
  "after": {"id": 101, "status": "PAID", "total_cents": 120000},
  "source": {
    "connector": "postgresql",
    "db": "appdb",
    "schema": "public",
    "table": "orders",
    "lsn": 26504123,
    "txId": 712
  },
  "op": "u",
  "ts_ms": 1730000054000
}
~~~

Đừng mặc định `before.status` luôn tồn tại. PostgreSQL `REPLICA IDENTITY DEFAULT` thường chỉ cung cấp khóa chính trong before image của UPDATE/DELETE; để có full before image có thể cần `REPLICA IDENTITY FULL` với đánh đổi lưu lượng WAL. Debezium connector cũng có quy tắc theo loại cột và version.

## 7. Mã op: r, c, u, d, t và m

| `op` | Tình huống | Cách xử lý thông thường | Cảnh báo |
|---|---|---|---|
| `r` | READ trong snapshot | Upsert read model | Không phải một INSERT business mới |
| `c` | CREATE/INSERT | Upsert/projection hoặc domain logic | Có thể replay |
| `u` | UPDATE | Áp dụng `after`, version check | `before` không nhất thiết full |
| `d` | DELETE | Xóa theo key/before | Có thể kèm tombstone kế tiếp |
| `t` | TRUNCATE (connector hỗ trợ) | Xử lý xóa toàn bảng hoặc invalidate cache có kiểm soát | Thường không có row key |
| `m` | Logical message (PostgreSQL, nếu bật) | Route xử lý control/metadata riêng | Không có shape row before/after |

`op="r"` thường liên quan initial/incremental snapshot; nó biểu diễn row hiện hữu được đọc. Khi một snapshot chạy lại vì offset bị mất, các events `r` có thể phát lại nhiều lần. Projection phải có logic upsert/idempotency tương ứng.

`op="t"` thường **không** có key và `after.id`. Nếu consumer chỉ nhận `r/c/u/d`, nó phải **từ chối/route rõ** một `t`, không truy cập `after.id` dẫn đến null pointer rồi retry vô hạn. `op="m"` cũng là loại đặc thù; kiểm tra config và connector version.

## 8. CREATE: key mới và after image

~~~sql
INSERT INTO public.orders(id, status, total_cents)
VALUES (101, 'CREATED', 120000);
~~~

Value (đã bỏ schema wrapper để dễ đọc):

~~~json
{
  "before": null,
  "after": {"id": 101, "status": "CREATED", "total_cents": 120000},
  "source": {"connector": "postgresql", "table": "orders"},
  "op": "c",
  "ts_ms": 1730000000123
}
~~~

**Hợp đồng:** key từ `DebeziumHeaders.KEY` chỉ ra row identity; `after` là ảnh hiện tại; `before` null. Khi downstream ghi `order_projection`, có thể dùng UPSERT theo `order_id` hoặc checked insert tùy business policy. Không sử dụng `ts_ms` như global sequence duy nhất.

## 9. UPDATE: before không phải bản sao đầy đủ

~~~sql
UPDATE public.orders
SET status='PAID'
WHERE id=101;
~~~

Value minh họa:

~~~json
{
  "before": {"id": 101},
  "after": {"id": 101, "status": "PAID", "total_cents": 120000},
  "source": {
    "connector": "postgresql",
    "table": "orders",
    "snapshot": "false",
    "lsn": 26504123
  },
  "op": "u",
  "ts_ms": 1730000054000
}
~~~

**Một lỗi kinh điển:** kiểm tra `before.status == "CREATED"` rồi thất bại khi `REPLICA IDENTITY DEFAULT` không cung cấp cột `status` trong `before`. Consumer có thể chỉ dùng `after` để upsert read model và dùng version/LSN/business sequence để chặn dữ liệu cũ ghi đè dữ liệu mới.

Nếu business bắt buộc tính delta từ ảnh trước/sau, phải xác nhận nguồn thực sự cung cấp đầy đủ `before`; hoặc tạo business event trong transactional outbox thay vì cố suy đoán từ CDC row update.

## 10. DELETE: before có thể chỉ chứa key, after null

~~~sql
DELETE FROM public.orders WHERE id=101;
~~~

Delete envelope minh họa:

~~~json
{
  "before": {"id": 101},
  "after": null,
  "source": {"connector": "postgresql", "table": "orders"},
  "op": "d",
  "ts_ms": 1730000099000
}
~~~

DELETE event có **value envelope** (vẫn có `op="d"`). Khi muốn xóa row trong read model, có thể lấy key từ header key JSON hoặc `before.id`; nếu thiếu cả hai, **không** tự suy ID từ timestamp/destination.

Sau DELETE, Debezium có thể phát tiếp một **tombstone** với cùng key nhưng **value null**. Tombstone không phải `op="d"` và không có `after`; phần 12 đi sâu hơn.

## 11. Snapshot READ: source.snapshot không luôn là boolean

Trong snapshot, `op="r"`; một vài output có `source.snapshot=true`, những output khác thể hiện thành chuỗi `"true"` hoặc `"last"` khi đánh dấu record cuối tùy phiên bản/connector. Consumer cần diễn giải snapshot theo version contract, không ép một kiểu duy nhất.

~~~json
{
  "before": null,
  "after": {"id": 102, "status": "CREATED", "total_cents": 89000},
  "source": {
    "connector": "postgresql",
    "table": "orders",
    "snapshot": "true"
  },
  "op": "r",
  "ts_ms": 1730000150000
}
~~~

**Đừng biến snapshot READ thành business event “OrderCreated” mới**. Một snapshot chỉ giúp dựng trạng thái; nếu cần phát sự kiện nghiệp vụ cho CREATE thực sự, sử dụng `op="c"` của streaming hoặc outbox business events có event ID.

## 12. Tombstone: value rỗng, khác DELETE envelope

Một dòng có thể tạo chuỗi sau (tùy connector/tombstone configuration):

~~~text
DELETE event:
  key   = {"id":101}
  value = {"before":{"id":101},"after":null,"op":"d",...}

Tombstone event:
  key   = {"id":101}
  value = null
~~~

Tombstone phục vụ **log compaction** và chính sách xóa ở những sink cần một null-value event cùng key. Với Spring Integration Debezium adapter, `enableEmptyPayload` mặc định là `false`. Khi bật `enableEmptyPayload(true)`, tài liệu adapter mô tả tombstone value dưới dạng `Optional.empty()` — không phải một JSON string `"null"`.

~~~java
import java.util.Optional;
import org.springframework.messaging.Message;

void inspect(Message<?> message) {
    Object payload = message.getPayload();

    if (payload instanceof Optional<?> option && option.isEmpty()) {
        // Tombstone: cần key từ DebeziumHeaders.KEY.
    } else if (payload instanceof byte[] jsonBytes) {
        // JSON envelope: có thể là c/u/d/r/t/m.
    } else {
        // Payload format/batch chưa hỗ trợ: không cast bừa.
    }
}
~~~

**Mảnh code trên là phương pháp kiểm tra kiểu**, không phải nguyên một Spring bean. Không coi mọi tombstone là DELETE business mới: nếu đã xử lý `op="d"`, tombstone có thể chỉ cần được forward xuống compacted Kafka topic; ứng dụng cần tránh gọi service xóa hai lần nếu side effect không idempotent.

## 13. UPDATE thay đổi primary key: một cập nhật có thể thành nhiều records

Một số Debezium connectors, bao gồm PostgreSQL, biểu diễn việc thay đổi primary key bằng chuỗi change events thay vì coi đó là một UPDATE thông thường với một record key giữ nguyên:

~~~text
Row cũ: id=101, status=PAID
SQL: UPDATE orders SET id=205 WHERE id=101

Record 1: DELETE envelope cho key cũ id=101
Record 2: Tombstone value=null với key cũ id=101 (nếu được bật)
Record 3: CREATE envelope cho key mới id=205
~~~

Tùy connector và version, có thể có thêm headers để liên kết old key/new key. Vì vậy:
- **Không giả định một SQL statement luôn tạo đúng một CDC message.**
- Không group tất cả records theo một giá trị primary key cố định nếu key có thể đổi.
- Projection với foreign-key references cần policy rekey phù hợp hoặc business event rõ.
- Consumer idempotency phải xét từng record/aggregate version, không xóa/INSERT mù nếu các events tới khác thứ tự.

Nếu yêu cầu atomic rekey across multiple target tables, một sequence CDC đơn thuần không tự cho transaction atomic ở downstream. Cân nhắc transactional outbox/domain command với logic transaction phù hợp.

## 14. TRUNCATE và logical message: không phải một row có id

PostgreSQL connector có thể phát `op="t"` khi nhận `TRUNCATE`. Truncate event thường **không có record key**, `before`/`after` không có shape row như CREATE/UPDATE. Nó biểu diễn tác động lên **một bảng**, không phải DELETE riêng lẻ từng hàng.

~~~json
{
  "source": {
    "connector": "postgresql",
    "db": "appdb",
    "schema": "public",
    "table": "orders"
  },
  "op": "t",
  "ts_ms": 1730000160000
}
~~~

Với nhiều partitions hoặc nhiều consumers, thứ tự TRUNCATE so với các row updates có thể là vấn đề. Đừng tự động map `t` thành hàng nghìn `DELETE` bất đồng bộ mà chưa có sequencing policy. Hệ thống cache/read model có thể cần “clear projection” có transaction/generation ID riêng.

PostgreSQL cũng có logical messages (`op="m"`) khi connector bật khả năng capture tương ứng. Những event đó có thể chứa `message` metadata như prefix và content, **không** chứa `after.id`. Nên route sang một handler control-message riêng hoặc quarantine nếu không thuộc business contract.

## 15. Timestamp: source event time khác processing time

Value có thể chứa:
- `payload.ts_ms`: thời điểm Debezium **xử lý event** ở JVM của connector.
- `payload.ts_us`/`payload.ts_ns`: độ phân giải cao hơn nếu được cung cấp.
- `payload.source.ts_ms`: thời điểm thay đổi tại **database nguồn** nếu connector có thông tin.
- `MessageHeaders.TIMESTAMP`: thời điểm **Spring Message** được tạo, không phải DB commit timestamp.

Ví dụ:

~~~json
{
  "op": "u",
  "source": {
    "connector": "postgresql",
    "table": "orders",
    "ts_ms": 1730000100000
  },
  "ts_ms": 1730000102400,
  "ts_us": 1730000102400123
}
~~~

Phép đo lag gần đúng:

\[
\mathrm{lag}_{CDC} = \mathrm{payload.ts\_ms} - \mathrm{payload.source.ts\_ms}
\]

Không xem chênh lệch này là latency end-to-end đã ACK Kafka/JMS hoặc consumer cập nhật xong read model. Có thể thiếu timestamps hoặc clocks có sai lệch; hãy thu riêng `cdc_capture_lag`, `inbox_commit_lag`, `publish_lag` và `consumer_apply_lag`.

**Không dùng timestamp làm ID event duy nhất hoặc order key tuyệt đối.** Nhiều events có thể cùng millisecond; timestamp có thể không monotonic giữa connections, DB transactions hoặc clocks.

## 16. Source metadata: PostgreSQL, MySQL và các connectors khác

`source` là cấu trúc do connector nguồn cung cấp, không phải hợp đồng tất cả DBs có chung mọi field:

| Field minh họa | PostgreSQL | MySQL | Lưu ý |
|---|---|---|---|
| `connector` | `postgresql` | `mysql` | Dùng phân biệt nguồn |
| `db` | Tên database | Tên database | Không tự có tenant |
| `schema` | `public` | Thường không giống PostgreSQL | Có thể null/vắng |
| `table` | Tên bảng | Tên bảng | Không phải một business topic |
| `lsn` | WAL log sequence number | Không dùng LSN PostgreSQL | Chỉ có ở PG |
| `txId` | Có thể có | Có thể khác | Không là global event ID |
| `file/pos/row` | Không phải PG LSN | Binlog position/row | Cần xét theo MySQL version |
| `snapshot` | Boolean/string/marker | Boolean/string/marker | Không ép kiểu cứng |
| `ts_ms` | Source event time | Source event time | Có thể null |

Tương ứng, source offset của PostgreSQL liên quan WAL/LSN; MySQL dùng binlog filename/position và metadata. **Không viết một method `Long.parseLong(source.lsn)` bắt buộc cho mọi database adapter**.

### 16.1. Cần những gì để xác định event identity?

`(database, table, primaryKey)` nhận diện row, không nhận diện từng UPDATE. `(source.lsn)` có thể góp phần xác định vị trí log trong PostgreSQL, nhưng **không mặc định là một event ID duy nhất** nếu một transaction/LSN có nhiều record hoặc Debezium thay đổi granularity. Nếu cần dedupe source-level, thiết kế một tuple theo connector/version có đủ log position, transaction, collection và record ordering.

Đơn giản và bền hơn cho domain events là ghi **business `event_id` duy nhất trong transactional outbox**, để downstream dedupe không phụ thuộc cú pháp offset của DB.

## 17. Transaction metadata: grouping và ordering có điều kiện

Khi bật transaction metadata, Debezium có thể phát các transaction boundary records (BEGIN/END) cùng metadata `transaction` trong từng data envelope.

~~~json
{
  "before": null,
  "after": {"id": 101, "status": "PAID"},
  "source": {
    "connector": "postgresql",
    "table": "orders",
    "lsn": 26504123
  },
  "op": "c",
  "transaction": {
    "id": "712:26504123",
    "total_order": 2,
    "data_collection_order": 1
  }
}
~~~

Đây là **hình dạng minh họa**, không phải cam kết mọi connector đều dùng đúng `id` format. `transaction.total_order` mô tả vị trí event trong transaction, còn `data_collection_order` là thứ tự theo collection/table; chúng thường **không có** nếu metadata transaction chưa được bật hoặc transactions xảy ra trước khi connector theo dõi.

Ví dụ một boundary event:

~~~json
{
  "status": "END",
  "id": "712:26504123",
  "event_count": 2,
  "data_collections": [
    {"data_collection": "public.orders", "event_count": 2}
  ]
}
~~~

**BEGIN/END boundary records không phải row change envelopes.** Nếu muốn consume chúng, cần chọn destination/handler phù hợp; không mặc định route chúng vào parser yêu cầu `before/after/op`.

**Không đồng nhất Engine batch với một database transaction.** Một Debezium batch có thể chứa records từ nhiều transactions hoặc chỉ một phần của transaction lớn; transaction grouping phải dựa vào metadata thực, không chỉ số events trong callback.

## 18. Serialization format: JSON bytes, Avro, Protobuf và Schema Registry

Trong Spring Integration Debezium inbound:
- Java DSL `Debezium.inboundChannelAdapter(Properties)` thuận tiện cho JSON serialization.
- Một `DebeziumEngine.Builder<ChangeEvent<byte[],byte[]>>` cấu hình sẵn dùng `JsonByteArray` cho JSON bytes.
- `DebeziumMessageProducer#setContentType(...)` gắn hợp đồng content type; phải **khớp format thực**.
- Bật Avro/Protobuf cần serializer/deserializer và schema handling phù hợp; không thể parse Avro bytes bằng Jackson JSON tree.

~~~java
import io.debezium.engine.ChangeEvent;
import io.debezium.engine.DebeziumEngine;
import io.debezium.engine.format.JsonByteArray;

// Builder minh họa: config Properties phải có connector, offset,
// database và security settings hợp lệ.
DebeziumEngine.Builder<ChangeEvent<byte[], byte[]>> builder =
    DebeziumEngine.create(JsonByteArray.class).using(config);
~~~

Đừng tự viết `new String(bytes)` bằng default charset; JSON nên decode UTF-8. Với Avro/Protobuf và registry, payload có thể mang schema identifier/wire format; phải dùng deserializer tương thích, lưu ý schema evolution và message size.

## 19. Single-event vs batch-mode payload của adapter

`DebeziumMessageProducer` có `enableBatch`:

| Mode | Payload gửi vào Spring Message | Phân tích |
|---|---|---|
| `enableBatch(false)` (mặc định) | Thường `byte[]` cho mỗi `ChangeEvent` (JSON byte-array) | Phù hợp mỗi event đi vào parser/route |
| `enableBatch(true)` | `List<ChangeEvent>` theo batch Engine | **Không serializable** theo tài liệu adapter; phải chuyển thành DTO nếu qua persistent channel |

~~~text
Engine callbacks: [E1, E2, E3]

enableBatch(false):
    Message<byte[]>(E1.value)
    Message<byte[]>(E2.value)
    Message<byte[]>(E3.value)

enableBatch(true):
    Message<List<ChangeEvent>>(E1, E2, E3)
~~~

Ở batch mode, **không** cast list thành `List<byte[]>`; từng phần tử là `ChangeEvent` có `key()`, `value()`, `destination()`. Trước khi dùng JDBC outbound batch, phải chuyển đổi thành `List<DomainCommand>` có SQL parameter semantics riêng; một list raw CDC events chưa phải command list.

### 19.1. Vấn đề serialized persistence

Một `QueueChannel` in-memory hoặc `ExecutorChannel` có thể giữ reference đến danh sách `ChangeEvent`, nhưng điều đó không bảo đảm có thể serialize nó vào `JdbcMessageStore` hoặc JMS. Với workload cần durable retry: normalize/validate rồi stage serializable DTO/inbox row trước async boundary.

## 20. Java DSL: tạo Debezium inbound source và channel parse

Ví dụ này dùng một PostgreSQL connector đã được cấu hình theo database/snapshot/offset phù hợp. Các properties được đưa từ bên ngoài, không hardcode DB secrets:

~~~java
package com.example.cdc.payload;

import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.debezium.dsl.Debezium;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class CdcInputConfiguration {

    @Bean
    public IntegrationFlow ordersCdcInputFlow(
            Properties debeziumConfiguration) {
        return IntegrationFlow
            .from(Debezium.inboundChannelAdapter(
                    debeziumConfiguration)
                .contentType("application/json")
                .enableBatch(false)
                .enableEmptyPayload(true))
            .channel("rawOrderChanges")
            .get();
    }
}
~~~

`debeziumConfiguration` ở đây là **bean Spring `Properties` do ứng dụng tạo**, có tên riêng/`@Qualifier` nếu nhiều Properties beans. Nó phải chứa `connector.class`, PostgreSQL credentials, `topic.prefix`, `table.include.list`, replication/offset store settings. Đây là skeleton của tầng message; chưa tự tạo database hay parser/downstream.

Nếu không cần tombstones, bỏ `enableEmptyPayload(true)` và tập trung xử lý `op="d"`; nhưng nếu muốn forward null-value vào compacted Kafka topic, giữ tombstone với key đúng.

## 21. DTO chuẩn hóa: tách event kỹ thuật khỏi business command

Không nên để mọi handler biết trực tiếp cấu trúc `schema/payload/source/op`. Một tầng **Normalization** giúp tạo hợp đồng nội bộ ổn định:

~~~java
package com.example.cdc.payload;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;

// Immutable DTO; key/source/rows có thể null tùy operation.
public record NormalizedCdcEvent(
        CdcOp op,
        String destination,
        JsonNode key,
        JsonNode before,
        JsonNode after,
        String database,
        String schema,
        String table,
        Long sourceLsn,
        Instant capturedAt,
        Instant processedAt,
        boolean fromSnapshot) {

    public enum CdcOp {
        READ, CREATE, UPDATE, DELETE, TRUNCATE, MESSAGE, TOMBSTONE
    }
}
~~~

Phân biệt:
- `destination`: route logic của Debezium, không mặc nhiên trusted tenant.
- `key`: decoded record key (có thể null ở TRUNCATE/no-PK).
- `before/after`: giữ dưới dạng JsonNode trước khi map sang business entity để kiểm tra schema.
- `sourceLsn`: nullable vì nguồn có thể không phải PostgreSQL.
- `capturedAt/processedAt`: nullable khi timestamp không có.
- `fromSnapshot`: cần parse theo version contract, không ép `source.snapshot` về Boolean ở mọi connector.
- `TOMBSTONE`: một loại nội bộ riêng, **không có JSON row envelope**.

**Không tự thêm field `eventId` bằng cách dùng row PK làm ID cho mọi UPDATE.** Nếu downstream yêu cầu exactly-once business effects, identity phải lấy từ outbox `event_id` hoặc tuple/sequence nguồn được thiết kế và xác minh.

## 22. Parser Jackson: chấp nhận schema wrapper và dạng bỏ wrapper

Một parser nên:
1. Kiểm tra bytes không null/rỗng.
2. Parse JSON bằng `ObjectMapper` (có giới hạn kích thước theo boundary).
3. Nếu root chứa `payload` là object, lấy object đó làm envelope; nếu root trực tiếp chứa `op`, lấy root.
4. Validate `op`; không đoán `op="c"` nếu thiếu.
5. Chỉ bắt buộc `after` cho `r/c/u` của row change.
6. Không ép `before` tồn tại với `u/d`; cần record key/DB contract riêng để xóa.
7. Parse `source`/timestamps có điều kiện và không nhầm `source.ts_ms` với `envelope.ts_ms`.

~~~java
package com.example.cdc.payload;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.time.Instant;
import org.springframework.stereotype.Component;

@Component
public final class DebeziumEnvelopeDecoder {

    private final ObjectMapper mapper;

    public DebeziumEnvelopeDecoder(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public DecodedEnvelope decode(byte[] json) throws IOException {
        if (json == null || json.length == 0) {
            throw new IllegalArgumentException("Empty CDC value");
        }

        JsonNode root = mapper.readTree(json);
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("CDC JSON root must be object");
        }

        JsonNode candidate = root.path("payload");
        JsonNode envelope = candidate.isObject() && root.has("schema")
            ? candidate : root;
        // Cấu hình schemas=false có thể tạo root envelope trực tiếp.
        // Nếu có wrapper không kèm schema, nên nhận diện
        // bằng contract đã khai báo, không tự đoán mọi JSON object.
        if (!envelope.isObject()) {
            throw new IllegalArgumentException("Missing CDC envelope");
        }

        String op = envelope.path("op").asText("");
        if (!op.equals("r") && !op.equals("c")
                && !op.equals("u") && !op.equals("d")
                && !op.equals("t") && !op.equals("m")) {
            throw new IllegalArgumentException("Unsupported op: " + op);
        }

        JsonNode before = nullable(envelope.path("before"));
        JsonNode after = nullable(envelope.path("after"));
        JsonNode source = nullable(envelope.path("source"));

        if ((op.equals("r") || op.equals("c") || op.equals("u"))
                && (after == null || !after.isObject())) {
            throw new IllegalArgumentException(
                "Missing after for row change: " + op);
        }

        return new DecodedEnvelope(
            op, before, after, source,
            millis(envelope.path("ts_ms")));
    }

    private static JsonNode nullable(JsonNode node) {
        return node == null || node.isMissingNode() || node.isNull()
            ? null : node;
    }

    private static Instant millis(JsonNode node) {
        if (node == null || !node.canConvertToLong()) {
            return null;
        }
        return Instant.ofEpochMilli(node.longValue());
    }

    public record DecodedEnvelope(
        String op,
        JsonNode before,
        JsonNode after,
        JsonNode source,
        Instant processedAt) { }
}
~~~

**Đây là parser cho row envelopes JSON đã khai báo**, không phải parser cho mọi loại Debezium control event hoặc Avro/Protobuf. Nếu một converter tùy chỉnh tạo `{"payload": {...}}` **mà không có `schema`**, cần mở rộng bằng một contract/config flag rõ ràng. Tránh suy đoán schema wrapper theo tên field nghiệp vụ không đủ chắc chắn.

### 22.1. Không phân biệt null và missing bằng `asText("")` ở tất cả fields

Một field JSON có thể có ba trạng thái:
- Không xuất hiện (`MissingNode`);
- Có `null`;
- Có giá trị thực, kể cả chuỗi rỗng `""` hoặc số `0`.

Trong CDC, **thiếu `before.status` không có nghĩa `status=""`**, và `after=null` ở DELETE không giống việc parser thất bại. Hãy dùng `isMissingNode()`/`isNull()`/`isObject()` để phân biệt trước khi áp business logic.

## 23. Decode key từ DebeziumHeaders.KEY theo định dạng thật

~~~java
package com.example.cdc.payload;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import org.springframework.integration.debezium.support.DebeziumHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public final class DebeziumKeyDecoder {

    private final ObjectMapper mapper;

    public DebeziumKeyDecoder(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public JsonNode decode(Message<?> message) throws IOException {
        Object raw = message.getHeaders().get(DebeziumHeaders.KEY);

        if (raw == null) {
            return null;
        }
        if (!(raw instanceof byte[] bytes)) {
            throw new IllegalArgumentException(
                "Unsupported Debezium KEY type: "
                + raw.getClass().getName());
        }
        JsonNode root = mapper.readTree(bytes);
        if (root == null || root.isNull()) {
            return null;
        }
        JsonNode wrapped = root.path("payload");
        if (root.has("schema") && wrapped.isObject()) {
            return wrapped;
        }
        return root;
    }
}
~~~

Trong PostgreSQL connector, bảng có primary key `id` thường tạo key JSON có `id`. Bảng không có key, TRUNCATE và vài record control có thể cho key null. Nếu application contract yêu cầu key, hãy kiểm tra ở route tương ứng — **không ép tất cả events phải có key**.

Đối với payload mode Avro/Protobuf, header key có thể phải được decode bằng schema-aware deserializer riêng. Việc dùng `new String((byte[]) header)` chỉ hợp để debug JSON bytes, không phải cách parse key phổ quát.

## 24. Handler Spring Integration: phân loại tombstone trước khi parse

~~~java
package com.example.cdc.payload;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.util.Optional;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.debezium.support.DebeziumHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public final class OrdersChangeDispatcher {

    private final DebeziumEnvelopeDecoder envelopes;
    private final DebeziumKeyDecoder keys;
    private final CdcApplicationService service;

    public OrdersChangeDispatcher(
            DebeziumEnvelopeDecoder envelopes,
            DebeziumKeyDecoder keys,
            CdcApplicationService service) {
        this.envelopes = envelopes;
        this.keys = keys;
        this.service = service;
    }

    @ServiceActivator(inputChannel = "rawOrderChanges")
    public void onChange(Message<?> message) throws IOException {
        Object rawDestination =
            message.getHeaders().get(DebeziumHeaders.DESTINATION);
        if (!(rawDestination instanceof String destination)
                || destination.isBlank()) {
            throw new IllegalArgumentException(
                "Missing or invalid Debezium destination");
        }
        JsonNode key = keys.decode(message);
        Object value = message.getPayload();

        if (value instanceof Optional<?> option && option.isEmpty()) {
            service.onTombstone(destination, key);
            return;
        }
        if (!(value instanceof byte[] bytes)) {
            throw new IllegalArgumentException(
                "Unexpected CDC payload type: "
                + value.getClass().getName());
        }

        DebeziumEnvelopeDecoder.DecodedEnvelope decoded =
            envelopes.decode(bytes);

        switch (decoded.op()) {
            case "r", "c", "u" ->
                service.upsert(destination, key, decoded.after(), decoded);
            case "d" ->
                service.delete(destination, key, decoded.before(), decoded);
            case "t" ->
                service.truncate(destination, decoded);
            case "m" ->
                service.onLogicalMessage(destination, decoded);
            default -> throw new IllegalStateException("Unexpected op");
        }
    }
}
~~~

`CdcApplicationService` là **interface ứng dụng phải tự định nghĩa** với các methods minh họa `onTombstone`/`upsert`/`delete`/`truncate`/`onLogicalMessage`. Nó phải validate destination, key, schema và authorization; ghi business state/inbox/outbox bền vững; có idempotency/version check. Đây là ví dụ **cách tổ chức code**, không phải triển khai đầy đủ cho production.

**Không log nguyên `message.payload` khi có customer PII**. Khi handler gặp format lạ, đưa record vào quarantine có kiểm soát thay vì gọi `toString()` của event nhiều megabytes trong log.

## 25. Kiểu dữ liệu CDC: decimal, timestamp, UUID, binary và JSON

Một value `after` có các trường dạng JSON, nhưng **kiểu DB ban đầu không nhất thiết trùng kiểu Java/Jackson mặc định**. Debezium và Kafka Connect có logical types; cách serialize phụ thuộc connector, precision và converter:

| Nguồn | Biểu diễn có thể thấy | Quy tắc an toàn |
|---|---|---|
| PostgreSQL `BIGINT` | JSON integer | Dùng `long` khi có kiểm tra range; không ép sang `int` |
| `NUMERIC/DECIMAL` | String decimal, binary/Base64 hoặc number tùy mode | Dùng `BigDecimal`, không tự dùng `double` cho tiền |
| `TIMESTAMP/TIMESTAMPTZ` | Epoch integer với đơn vị ms/us/ns hoặc ISO string | Chốt `time.precision.mode`/formatter và timezone |
| `UUID` | Chuỗi UUID hoặc logical type cụ thể | Validate `UUID.fromString` nếu contract là UUID text |
| `BYTEA/BLOB` | Base64/byte-array theo converter và binary mode | Không log base64 nhạy cảm |
| PostgreSQL `JSON/JSONB` | Có thể là string chứa JSON hoặc một mapped JSON structure | Parse theo connector/serialization contract |
| SQL `NULL` | JSON null | Khác với field không có do schema/mask |
| Enum/array/geography | Converter-specific representation | Dùng mapping versioned và tests theo DB |

Ví dụ JSON bytes đã decode:

~~~json
{
  "after": {
    "id": 101,
    "total_cents": 120000,
    "exchange_rate": "1.234567890123456789",
    "placed_at": 1730000000123456,
    "customer_ref": "b7a91944-30ac-4f30-8cd2-5d8dbaf1db72"
  },
  "op": "u",
  "source": {"connector": "postgresql"}
}
~~~

Đây là **format minh họa**, không phải mặc định bắt buộc cho tất cả converters. `placed_at` có thể là epoch **microseconds**, không phải milliseconds. `Instant.ofEpochMilli(1730000000123456L)` sẽ cho kết quả sai hàng nghìn năm nếu giá trị thực là microseconds.

### 25.1. Decimal không nên đi qua double

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;

BigDecimal readDecimal(JsonNode row, String field) {
    JsonNode value = row.path(field);
    if (value.isMissingNode() || value.isNull()) {
        return null;
    }
    if (!value.isTextual() && !value.isNumber()) {
        throw new IllegalArgumentException(
            "Unsupported decimal representation");
    }
    return new BigDecimal(value.asText());
}
~~~

Mảnh code chỉ xử lý **decimal dạng string hoặc JSON number**. Nếu converter xuất binary logical decimal trong base64, cần decode scale/precision đúng; không tự coi base64 là chuỗi thập phân.

### 25.2. Timestamp phải biết đơn vị và timezone

~~~java
import java.time.Instant;

// Chỉ khi contract nguồn đã xác nhận giá trị là epoch MICROSECONDS.
long micros = 1730000000123456L;
Instant instant = Instant.ofEpochSecond(
    Math.floorDiv(micros, 1_000_000L),
    Math.floorMod(micros, 1_000_000L) * 1_000L);
~~~

Không tự đoán đơn vị bằng số chữ số của timestamp khi DB/connector có độ phân giải thay đổi. Đưa `capturedAt`, `processedAt` và `businessOccurredAt` vào các trường tách biệt nếu contract cần cả ba.

## 26. Schema evolution: consumer phải chịu được thay đổi có kiểm soát

Giả sử schema ban đầu:

~~~json
{"after":{"id":101,"status":"CREATED","total_cents":120000},"op":"c"}
~~~

Sau migration thêm `discount_cents` và đổi tên `total_cents` thành `gross_total_cents`:

~~~json
{
  "after": {
    "id": 101,
    "status": "CREATED",
    "gross_total_cents": 120000,
    "discount_cents": 5000
  },
  "op": "u"
}
~~~

Consumer cũ chỉ đọc `after.total_cents` có thể trả 0/null sai nếu dùng `asLong(0)` mà không kiểm tra missing. Các chiến lược:

1. **Additive changes:** thêm trường có default/null, consumer bỏ qua trường không dùng.
2. **Breaking rename:** chạy dual-read/dual-write trong thời kỳ migration hoặc version DTO.
3. **Type changes:** kiểm tra range/precision, không ép số chuỗi không rõ.
4. **Schema Registry:** khi dùng Avro/Protobuf, kiểm tra compatibility mode và subject/key/value schema version.
5. **Contract tests:** dùng golden CDC events từ cả trước và sau migration.
6. **Control events:** xử lý hoặc route rõ heartbeat, transaction, truncate, schema control messages; không ném NPE do thiếu `after`.
7. **EventRouter/SMT:** có thể biến đổi envelope trước khi tới ứng dụng; hợp đồng downstream phải dựa trên format **sau** SMT.

**Không tự coi Debezium schema field name là business API ổn định vĩnh viễn.** CDC phản ánh bảng nguồn; business event contract nên version độc lập khi có nhiều consumers quan trọng.

### 26.1. Replica identity và tác động của migration

PostgreSQL:

~~~sql
-- Ví dụ cho lab; cần cân nhắc chi phí và quyền DBA.
ALTER TABLE public.orders REPLICA IDENTITY FULL;
~~~

`REPLICA IDENTITY FULL` giúp tăng thông tin `before` của UPDATE/DELETE, nhưng có thể tăng WAL và overhead. Đừng áp dụng cho toàn bộ bảng chỉ để consumer debug dễ hơn; ưu tiên business outbox nếu cần event đầy đủ, cân nhắc dữ liệu nhạy cảm trong before image.

## 27. Debezium Single Message Transforms có thể thay đổi payload

Debezium có các **Single Message Transforms (SMT)**. Ví dụ `ExtractNewRecordState` có thể “unwrap” một envelope và chỉ giữ row `after`, tùy cấu hình handle DELETE và metadata fields. Sau SMT, payload có thể giống:

~~~json
{"id": 101, "status": "PAID", "total_cents": 120000}
~~~

Đây **không còn** envelope có `op`, `source`, `before/after` theo cấu trúc gốc. Consumer dùng `DebeziumEnvelopeDecoder` sẽ báo `Missing op` — đúng, vì contract đã thay.

**Quy tắc:** ghi rõ pipeline được áp dụng `SMT` ở đâu (connector/Engine/Kafka Connect), output format nào được phép tới Spring Integration, có giữ header `op`/`table`/`source` hay không. Không viết một parser vừa im lặng suy đoán envelope gốc, vừa im lặng chấp nhận đã unwrap nếu không có version/config.

Các SMT như outbox EventRouter có thể thay key, route, payload và headers thành business event. Khi đó `DebeziumHeaders.KEY` vẫn phản ánh event key của **format sau transform**, không mặc định là primary key `orders.id` gốc.

## 28. Routing theo destination và operation một cách an toàn

Một flow có thể nhận thay đổi của nhiều bảng. Nên định nghĩa allowlist:

~~~text
orders_source.public.orders
    + op in [r,c,u] -> order projection upsert
    + op=d          -> order projection delete
    + tombstone     -> compacted Kafka forwarding policy
    + op=t          -> controlled full-invalidation handler

orders_source.public.customers
    + op in [r,c,u] -> customer projection
    + op=d          -> customer delete
    + unrecognized  -> quarantine
~~~

**Đừng** lấy `DebeziumHeaders.DESTINATION` làm SQL table name bằng nối chuỗi:

~~~java
// Không làm thế này với untrusted destination:
// jdbc.execute("DELETE FROM " + destination);
~~~

Dù destination do connector tạo, schema có thể đổi, header mapper có thể được custom và messages có thể đến từ một endpoint khác. Dùng allowlist cố định ánh xạ destination → handler/repository đã cấu hình và validate quyền của tenant.

### 28.1. Router theo event data thay vì thao tác JSON tùy tiện

Một `@ServiceActivator` như mục 24 có thể gọi `CdcApplicationService`; service nên tách:
- `OrderProjectionService` cho `r/c/u`;
- `DeleteProjectionService` cho `d`;
- `TruncateControlService` khi được cho phép;
- `TombstoneForwarder` nếu cần Kafka compaction;
- `QuarantineService` cho schema/operation không hỗ trợ.

Không gọi `DELETE FROM orders` trên nguồn nghiệp vụ ngay khi nhận một CDC DELETE; handler phải cập nhật **sink/read model tương ứng**, tránh vòng lặp CDC vô hạn.

## 29. Ordering: Spring Message thứ tự không phải source commit order mặc định

Đối với một row key, application có thể mong nhận `CREATED → PAID → SHIPPED`. Nhưng:
- Engine có thể phát tuần tự cho một connector task, song các versions có async execution;
- `ExecutorChannel` có nhiều threads có thể làm đảo thứ tự xử lý;
- Kafka nhiều partitions giữ order **trong một partition**, không có global order;
- Một record key thay đổi tạo nhiều events;
- Snapshot và streaming có semantics riêng;
- Retries và replays có thể đưa event cũ trở lại sau khi sink đã ở version mới.

**Một giải pháp thực tế:** downstream update có điều kiện theo `aggregate_version` được tạo tại database nguồn:

~~~sql
-- Ví dụ read model, các source events có monotonic version.
UPDATE order_read_model
SET status = :newStatus, version = :newVersion
WHERE id = :orderId
  AND version < :newVersion;
~~~

Đây là ví dụ optimistic check đơn giản; với bản ghi chưa tồn tại cần **UPSERT có version guard** theo DB vendor. `version` phải do nguồn tăng theo từng business mutation; không lấy `MessageHeaders.TIMESTAMP` làm version.

Nếu event sequence có chỗ trống và business không chấp nhận bỏ qua trung gian, phải có queue/partition per aggregate, gap detection và reconciliation. Không chỉ dùng `version < newVersion` rồi tự coi mọi missing event là vô hại.

## 30. Idempotency và replay: một row key không phải event ID

Khả năng mất mạng/offset flush khiến Debezium có thể phát lại một event đã được downstream xử lý. Với raw row changes:

~~~text
E1: row id=101, op=u, status=PAID
E2: row id=101, op=u, status=SHIPPED
Replay E1 xảy ra sau E2
~~~

Nếu consumer chỉ dùng `rowId=101` để dedupe, E2 có thể bị bỏ như duplicate. Nếu cứ apply E1 khi replay sau E2, trạng thái lại lùi từ SHIPPED về PAID. Cần một định danh/version hợp đồng rõ.

| Trường hợp | Lựa chọn thường dùng |
|---|---|
| Đọc model hiện trạng | UPSERT theo aggregate version |
| Business event immutable | Outbox table có `event_id` ổn định/UNIQUE |
| Raw CDC offset dedupe | Event identity tuple theo connector và record position đã xác minh |
| Kafka/JMS redelivery | Durable processed-event table + unique event ID |
| Side effect HTTP | Idempotency key ở remote hoặc reconciliation |
| DELETE/rekey | Tombstone/key semantics và version/order policy |

Ví dụ outbox table:

~~~sql
CREATE TABLE order_outbox (
    event_id       UUID PRIMARY KEY,
    aggregate_id   BIGINT NOT NULL,
    aggregate_ver  BIGINT NOT NULL,
    event_type     VARCHAR(80) NOT NULL,
    payload_json   JSONB NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (aggregate_id, aggregate_ver)
);
~~~

Business transaction **UPDATE orders và INSERT order_outbox** trong cùng local DB transaction. Debezium capture outbox và downstream dùng `event_id` để dedupe. Không coi việc Debezium publish qua Spring channel là database+Kafka distributed XA transaction.

## 31. Offset, commit và downstream transaction là các ranh giới riêng

~~~mermaid
sequenceDiagram
    participant DB as PostgreSQL
    participant Eng as Debezium Engine
    participant SI as Spring Integration
    participant Inbox as Inbox database
    participant K as Kafka/JMS
    DB-->>Eng: ChangeEvent E1
    Eng->>SI: Message E1
    SI->>Inbox: INSERT inbox(eventId) + COMMIT
    Note over SI,Inbox: Work bền trong local DB
    Eng->>Eng: Mark/flush source offset theo Engine
    Inbox->>K: Publisher retry gửi E1
    K-->>Inbox: Broker ACK (có thể redelivery)
~~~

Một lời gọi `MessageChannel.send()` thành công không phải một transaction commit receipt. Spring Integration `DirectChannel` giúp handler đồng bộ với callback thread, nhưng không tự mở JDBC transaction; `ExecutorChannel`/`QueueChannel` tạo async boundary, nên callback Engine có thể kết thúc trước khi worker thực sự stage dữ liệu.

Các tình huống:
- **Crash sau inbox COMMIT trước offset flush:** event có thể replay; unique event ID cần làm dedupe.
- **Offset tiến trước khi async job bền:** job có nguy cơ mất khi process crash.
- **Kafka đã ACK nhưng chưa đánh dấu outbox published:** publisher có thể gửi lại; consumer phải idempotent.
- **External HTTP effect hoàn tất nhưng response mất:** cần idempotency token/reconciliation, không retry mù.

**Với raw CDC event không có stable business event ID, muốn tạo inbox phải thiết kế khóa dedupe đúng nguồn/connector.** Không tự ghép `db.table + rowPK` rồi cho rằng mỗi update duy nhất. Khi chưa có hợp đồng dedupe đủ mạnh, áp dụng snapshot rebuild/version-based materialized view hoặc transactional outbox từ nguồn.

## 32. Security: payload CDC có thể chứa PII và bí mật

Một change event có thể chứa **toàn bộ ảnh mới và ảnh cũ** của row. Nếu bảng có `email`, `phone`, token, địa chỉ hay payment metadata, CDC làm chúng xuất hiện ở sink, logs, dead-letter queues, traces và backup.

Checklist:
- Chỉ capture bảng cần thiết qua `table.include.list` và chọn lọc cột theo connector capability.
- Áp dụng column masking/tokenization/transform đúng điểm trong pipeline, **trước khi gửi ra hệ thống khác**.
- Không log raw `key`/`payload` chứa PII khi parser lỗi.
- Hạn chế quyền xem raw CDC events, dead-letter storage và sample snapshots.
- Validate JSON max bytes, nesting depth, schema/field types và destination allowlist.
- Dùng TLS cho DB/broker, secret manager cho credentials và kiểm soát replication role.
- Kiểm tra field mới khi migration: nếu consumer tự serialize toàn bộ `after`, cột mới nhạy cảm có thể bị phát tán ngoài dự kiến.
- Có chính sách DELETE/tombstone cho downstream caches, search indexes và retention compliance.
- Dùng correlation ID/log source position để debug mà không phải lưu nguyên payload.

**Không** dùng Java serialization cho `ChangeEvent` raw trong persistent MessageStore chỉ vì nó là một Java object; batch `List<ChangeEvent>` được tài liệu Spring Integration mô tả **không serializable** theo mặc định.

## 33. Metrics, backpressure và kiểm soát payload size

| Metric | Dùng để phát hiện |
|---|---|
| `cdc_value_bytes` và `cdc_key_bytes` | Event quá lớn/JSON schema wrapper overhead |
| `cdc_envelope_parse_failures` | Format/schema drift |
| `cdc_unknown_op` | Truncate/logical message/sai route |
| `cdc_tombstones_received` | Delete compaction stream behavior |
| `cdc_snapshot_records` | Snapshot tiến độ/bất thường |
| `cdc_capture_lag_ms` | Chênh lệch source/process timestamps khi có |
| `cdc_messages_per_second` | CDC ingest throughput |
| `cdc_inbox_oldest_age` | Downstream backlog |
| `cdc_idempotent_replay_count` | Offset/ACK retry |
| `cdc_wal_retained_bytes` | PostgreSQL replication slot giữ WAL |
| `cdc_dispatch_queue_depth` | Async channel/worker quá tải |
| `cdc_quarantine_pending` | Poison event cần sửa contract |

Nếu sink chậm, đừng chuyển vô hạn payload bytes vào executor không bounded. Dùng bounded concurrency và **durable inbox/outbox**; chọn retry/backoff phù hợp để tránh memory OOM và WAL retention tăng.

Một payload 2MB có thể thành 10MB+ khi parse thành tree, copy qua nhiều channels, thêm schema và log. Chọn max payload size và memory budget dựa trên thực đo; thông báo rõ nếu event hợp lệ quá lớn cần blob/object-store reference thay vì raw JSON.

## 34. Xử lý lỗi payload theo lớp

| Lỗi | Cách phản ứng đúng | Sai lầm cần tránh |
|---|---|---|
| Không phải JSON bytes | Route theo format/serializer đã đăng ký | Cast `byte[]` tất cả |
| JSON parse hỏng | Quarantine kèm source metadata, alert | Retry vô hạn |
| Mất `op` trên row envelope | Báo contract violation/SMT mismatch | Mặc định coi CREATE |
| `before` null ở UPDATE | Dùng `after`, hoặc điều chỉnh replica identity | `before.status` dereference |
| `after` null khi DELETE | Lấy key/before theo contract | Parse thành DTO row mới |
| Tombstone `Optional.empty()` | Route compaction/tombstone policy | Parse Jackson trên Optional |
| `op=t`/`m` | Control handler hoặc explicit reject | Lấy `after.id` |
| Decimal/timestamp sai | Validate types/precision và reprocess sau fix | Âm thầm dùng default 0 |
| Unknown destination | Quarantine/allowlist reject | Nối vào SQL table name |
| Schema đổi cột | Version migration/dual read | Đọc missing thành empty string |
| Downstream DB outage | Retry transactional unit, backoff | Drop event sau log |
| Kafka ACK timeout | Outbox/remote dedupe | Tin rằng lỗi = chưa gửi |

Mọi `catch (Exception)` trong synchronous handler phải tôn trọng failure policy: nếu đã ghi partial DB state mà bỏ qua exception, transaction có thể commit không mong muốn. Nếu chỉ throw exception mà Engine có policy retry/advance offset khác, vẫn cần test **redelivery và dead-letter persistence** theo adapter/Engine version.

## 35. Unit test parser với nhiều hình dạng payload

Một số unit tests dùng `ObjectMapper` thuần; không cần kết nối PostgreSQL.

~~~java
package com.example.cdc.payload;

import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class DebeziumEnvelopeDecoderTest {

    private final DebeziumEnvelopeDecoder decoder =
        new DebeziumEnvelopeDecoder(new ObjectMapper());

    @Test
    void parsesWrappedUpdateWithMissingBeforeFields() throws Exception {
        String json = """
            {
              "schema":{"type":"struct"},
              "payload":{
                "before":{"id":101},
                "after":{"id":101,"status":"PAID"},
                "op":"u",
                "source":{"connector":"postgresql","lsn":1001},
                "ts_ms":1730000054000
              }
            }
            """;

        var event = decoder.decode(
            json.getBytes(StandardCharsets.UTF_8));

        assertEquals("u", event.op());
        assertEquals(101, event.before().path("id").asInt());
        assertTrue(event.before().path("status").isMissingNode());
        assertEquals("PAID", event.after().path("status").asText());
        assertNotNull(event.processedAt());
    }

    @Test
    void acceptsUnwrappedSnapshotRead() throws Exception {
        String json = """
            {
              "before":null,
              "after":{"id":102,"status":"CREATED"},
              "source":{"snapshot":"true"},
              "op":"r"
            }
            """;

        var event = decoder.decode(
            json.getBytes(StandardCharsets.UTF_8));
        assertEquals("r", event.op());
        assertNull(event.before());
        assertEquals(102, event.after().path("id").asInt());
    }

    @Test
    void deleteHasNullAfter() throws Exception {
        String json = """
            {"before":{"id":101},"after":null,"op":"d"}
            """;

        var event = decoder.decode(
            json.getBytes(StandardCharsets.UTF_8));
        assertEquals("d", event.op());
        assertNull(event.after());
    }

    @Test
    void refusesUnknownOperation() {
        byte[] invalid =
            "{\"op\":\"unexpected\",\"after\":{}}"
                .getBytes(StandardCharsets.UTF_8);

        assertThrows(IllegalArgumentException.class,
            () -> decoder.decode(invalid));
    }
}
~~~

Đây là một **unit test parser**, không chứng minh Event value do PostgreSQL Debezium connector thật phát có đúng format đó. Tại integration test, nên lấy golden events từ Debezium connector tương thích, test cùng config schema wrapper/SMT đang deploy.

### 35.1. Test key decoder và tombstone

Test thêm:
1. Header key bytes `{"schema":{...},"payload":{"id":101}}` → `id=101`.
2. Header key bytes `{"id":101}` → `id=101`.
3. Header key vắng ở TRUNCATE → chấp nhận theo operation route.
4. Value tombstone `Optional.empty()` → handler gọi `onTombstone`, **không** gọi `envelopes.decode`.
5. Payload một `String` khi handler chỉ hỗ trợ JSON bytes → báo loại không hỗ trợ.
6. `enableBatch(true)` → payload `List<ChangeEvent>` cần batch-specific handler.

Không kiểm thử bằng cách cứ tạo `new Message<>(null)`: Spring Messaging không chấp nhận payload null thông thường. Dùng loại payload mà adapter thực tế cung cấp và thiết lập message headers đúng.

## 36. Integration test PostgreSQL CDC và schema evolution

Kiểm thử end-to-end trên PostgreSQL với logical replication và Debezium connector tương thích (Testcontainers hoặc test DB cùng vendor). Cấu hình:
- Bảng `orders` có PK, `REPLICA IDENTITY` theo test.
- Connector `table.include.list=public.orders`, `plugin.name=pgoutput`, publication/slot riêng cho test.
- File/JDBC offset backing store dùng nơi lưu cô lập.
- Spring Integration inbound source bật `enableBatch(false)`; handler capture bytes/headers trong test.
- Tối đa **một Engine** trên cùng slot/offset khi test, trừ khi chủ ý kiểm tra collision.
- Test không dùng sleep cố định; dùng `CountDownLatch`/await condition với timeout.

Ma trận:

| Thao tác | Điều cần assert |
|---|---|
| Snapshot initial | `op=r` và `after.id` khớp row hiện hữu |
| INSERT | `op=c`, key.id và after.id khớp |
| UPDATE | `op=u`, `before` theo replica identity, after mới |
| DELETE | `op=d` và after null; tombstone riêng nếu bật |
| TRUNCATE | Nếu capture và hỗ trợ, `op=t` không giả định key/after |
| PK update | Có chuỗi delete/tombstone/create theo connector |
| Wrapper bật/tắt | Parser đọc đúng cả hai config đã cho |
| Schema add column | Consumer bỏ qua trường mới không dùng |
| Rename column | Contract test fail có chủ đích/dual-read |
| DECIMAL/TIMESTAMP | Scale, precision, timezone đúng |
| Batch mode | Payload list raw events, không cast `byte[]` |
| Restart offset | Có thể replay; projection idempotent |
| Kafka/JMS sink outage | Retry/đối soát không mất durable work |
| Event quá lớn | Giới hạn bytes và quarantine theo policy |
| Unknown destination | Không sinh SQL dynamic |
| Engine slot collision | Không chạy hai producers vô tình cùng slot |

**Phân biệt test parser và test delivery:** unit test kiểm tra cú pháp/logic normalization; integration test kiểm tra representation thật; fault-injection test kiểm tra offset/transaction/replay. Chỉ khi cả ba có bằng chứng mới khẳng định mức bảo đảm phù hợp.

## 37. Checklist áp dụng thực tế cho change event payload

Khi thiết kế một consumer Spring Integration nhận Debezium CDC, hãy trả lời rõ:

1. **Source connector:** PostgreSQL, MySQL, SQL Server, Oracle hay MongoDB? Dữ liệu `source` khác nhau.
2. **Serialization:** JSON `byte[]`, JSON `String`, Avro, Protobuf hay `SourceRecord`? Phải có decoder đúng.
3. **Schema wrapper:** `schema/payload` có tồn tại không? Version và SMT nào tác động?
4. **Key:** được lưu ở `DebeziumHeaders.KEY` với định dạng gì? Bảng có PK không?
5. **Destination:** header `DebeziumHeaders.DESTINATION` được allowlist/route thế nào?
6. **Operation:** có xử lý `r/c/u/d/t/m`, tombstones và transaction control events không?
7. **Before image:** DB cung cấp cột nào? `REPLICA IDENTITY`/binlog row image đủ chưa?
8. **After image:** có thể null/thiếu khi nào? Consumer có làm field validation không?
9. **Timestamp:** đơn vị ms/us/ns và nguồn thời gian đã chốt chưa?
10. **Data types:** DECIMAL/UUID/TIMESTAMP/BINARY/JSON được parse đúng precision không?
11. **Schema evolution:** có golden tests cho thêm/đổi field và nâng connector version không?
12. **SMT:** có unwrap, mask, route hay outbox transform trước adapter không?
13. **Transaction:** metadata `transaction` có bật và được dùng đúng scope không?
14. **Ordering:** có version/partition ownership để chống event cũ ghi đè event mới không?
15. **Dedupe:** business event ID hoặc source position tuple có đủ uniqueness không?
16. **Delivery:** callback/offset flush có liên hệ gì với inbox/outbox COMMIT và ACK broker?
17. **Backpressure:** payload/queues có bounded không, nếu sink chậm thì sự kiện được giữ ở đâu?
18. **Security:** payload cũ/mới chứa PII đã được lọc, masked, log/retention đúng chưa?
19. **Observability:** đo parse errors, tombstones, lag, slot WAL và redelivery chưa?
20. **Recovery:** có runbook khi offset mất, schema đổi, truncate hoặc source slot bị xóa chưa?

Nếu bất kỳ mục **serialization, key, operation, idempotency** nào chưa xác định, không nên coi pipeline đã an toàn chỉ vì handler nhận được `Message<?>`.

## 38. Bài thực hành

1. Tạo bảng PostgreSQL `public.orders` với `id`, `status`, `total_cents`; bật CDC bằng Debezium Engine.
2. Tạo Java DSL `Debezium.inboundChannelAdapter(Properties)` với `enableBatch(false)` và output `rawOrderChanges`.
3. In kiểu payload/header **không in raw PII**, xác minh `byte[]`, `DebeziumHeaders.KEY` và `DESTINATION`.
4. Capture JSON của **key** và **value** riêng; chỉ ra `schema/payload` của mỗi phần.
5. Tắt JSON schema wrapper qua converter đúng version, xác minh decoder đọc được cả wrapped/unwrapped.
6. Thực hiện INSERT và xác minh `op=c`, `before=null`, `after.id` khớp.
7. UPDATE status, xác minh `op=u` và thiếu một số `before` fields khi `REPLICA IDENTITY DEFAULT`.
8. Chuyển `REPLICA IDENTITY FULL` trong lab; so sánh before image và WAL overhead.
9. DELETE row, xác minh `op=d` với `after=null`; xử lý riêng tombstone khi bật.
10. Bật `enableEmptyPayload(true)`, viết handler nhận `Optional.empty()` mà không ném ClassCastException.
11. Khởi động initial snapshot, xác minh `op=r`; không phát nhầm business OrderCreated.
12. Thử `TRUNCATE` trên bảng thử nghiệm, xác minh nếu connector hỗ trợ thì không có row key/after.
13. Tạo thay đổi primary key, quan sát delete/tombstone/create sequence (nếu connector hỗ trợ như tài liệu).
14. Viết `DebeziumEnvelopeDecoder` dùng Jackson, unit test JSON có và không có wrapper.
15. Viết `DebeziumKeyDecoder` cho JSON key, xử lý null key theo từng operation.
16. Xây `NormalizedCdcEvent` tách operation, key, before, after, source, event times.
17. Route events theo allowlist destination; cố tình gửi unknown destination để kiểm tra quarantine.
18. Parse số decimal lớn bằng `BigDecimal`; so sánh với double và chỉ ra mất precision.
19. Parse timestamp microseconds theo `Instant.ofEpochSecond`, không dùng `ofEpochMilli` sai đơn vị.
20. Tạo schema migration thêm cột, kiểm tra consumer bỏ qua field không dùng.
21. Tạo migration rename column, thêm golden test xác nhận contract break được phát hiện.
22. Bật transaction metadata, quan sát `transaction.total_order` và transaction boundary records.
23. Gắn `ExecutorChannel` trước handler có delay; phân tích vì sao message handoff không đồng nghĩa durable work.
24. Tạo inbox table có unique business `event_id`, mô phỏng offset replay và kiểm tra không lặp business effect.
25. Tạo read-model update với aggregate `version`, phát lại event cũ sau event mới và xác minh không ghi đè.
26. Gắn outbox publisher Kafka/JMS; mô phỏng broker ACK thành công nhưng app chết trước khi ghi `published`.
27. Bật `enableBatch(true)` trên flow thử nghiệm riêng, xác minh `List<ChangeEvent>` không phải `List<byte[]>`.
28. Viết transformer batch chuyển raw change events thành serializable DTOs trước persistent store.
29. Thử SMT unwrap `ExtractNewRecordState`, xác nhận parser envelope gốc không còn áp dụng mà phải chọn contract mới.
30. Viết integration tests với PostgreSQL Testcontainers có logical replication, kiểm tra `r/c/u/d` và tombstone.
31. Dùng lỗi JSON malformed, event thiếu `op` và converter sai format; phân biệt quarantine với transient retry.
32. Thêm giới hạn kích thước payload/JSON depth và metrics parse failure.
33. Đo lag `source.ts_ms` vs `ts_ms`, so sánh với thời gian inbox COMMIT để tránh nhầm các loại latency.
34. Chạy hai pods với `ExecutorChannel` và Kafka partitions, kiểm tra ordering per aggregate.
35. Xây dashboard CDC rate, payload bytes, tombstones, parse failures, inbox backlog, slot WAL retention.
36. Viết runbook phục hồi khi schema drift, offset file mất hoặc PostgreSQL replication slot không còn phù hợp.

**Tình huống tổng hợp:** một ứng dụng nhận Debezium CDC của đơn hàng qua Spring Integration. Nó bật `enableBatch(false)`, map key JSON vào header, chuyển value byte-array thành read model rồi gửi Kafka. DBA thay đổi `REPLICA IDENTITY`, một giao dịch đổi primary key và source phát DELETE + tombstone + CREATE. Sau khi Kafka nhận CREATE, ứng dụng chết trước khi lưu offset; một pod mới đọc lại event cũ, trong khi `after.total_cents` vừa đổi tên. Hãy trình bày **hợp đồng parser, version/ordering, tombstone handling, schema migration, durable inbox/outbox, offset replay, idempotency và các tests** để read model không bị xóa nhầm hoặc lùi trạng thái.

## 39. Tài liệu tham khảo

- [Spring Integration Reference — Debezium Support](https://docs.spring.io/spring-integration/reference/debezium.html): `DebeziumMessageProducer`, Java DSL, `Message<byte[]>`, key/destination headers, `enableBatch`, `enableEmptyPayload`, JSON schema wrapper.
- [Spring Integration API — DebeziumHeaders](https://docs.spring.io/spring-integration/api/org/springframework/integration/debezium/support/DebeziumHeaders.html): hằng `KEY`, `DESTINATION` và `PREFIX`.
- [Spring Integration API — DebeziumMessageProducer](https://docs.spring.io/spring-integration/api/org/springframework/integration/debezium/inbound/DebeziumMessageProducer.html): constructor và các cấu hình producer.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `ExecutorChannel`, `QueueChannel` và thread boundaries.
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): transaction synchronization và giới hạn local transaction.
- [Debezium Documentation — PostgreSQL Connector](https://debezium.io/documentation/reference/stable/connectors/postgresql.html): change event key/value, before/after, op, snapshot, replica identity, transaction metadata, truncate, logical messages, key updates.
- [Debezium Documentation — Debezium Engine](https://debezium.io/documentation/reference/stable/development/engine.html): `ChangeEvent`, JSON/JsonByteArray, ChangeConsumer, offset và Engine lifecycle.
- [Debezium Documentation — Outbox Event Router SMT](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): chuyển raw outbox row thành business event contract.
- [Debezium Documentation — Event Flattening SMT](https://debezium.io/documentation/reference/stable/transformations/event-flattening.html): `ExtractNewRecordState` và ảnh hưởng của unwrap với envelope.
- [Debezium Documentation — Data Type Handling](https://debezium.io/documentation/reference/stable/connectors/postgresql.html#postgresql-data-types): cách Debezium map logical types theo PostgreSQL converter.
- [PostgreSQL Documentation — Replica Identity](https://www.postgresql.org/docs/current/sql-altertable.html): `REPLICA IDENTITY` và ảnh hưởng tới thông tin row cũ.
- [Spring Framework — Jackson JSON Support](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): nền tảng JSON binding/decoding tùy Spring stack.
- [Java API — BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html): số thập phân chính xác cho tiền và DECIMAL.
- [Java API — Instant](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html): biểu diễn timestamp độc lập timezone trong Java.

> **Ghi nhớ:** một **Debezium change event payload** không chỉ là JSON `after`. Spring Integration thường nhận **value bytes** ở `Message.payload`, còn **record key** và **destination** ở headers; value có thể có `schema/payload` wrapper và envelope `before/after/source/op/ts_ms/transaction`. Phải phân biệt **snapshot r, CREATE c, UPDATE u, DELETE d, tombstone value rỗng, TRUNCATE t** và các control records. Normalization cần kiểm tra kiểu/shape, schema evolution, precision, key/ordering/idempotency; offset Debezium, JDBC transaction và broker ACK là các ranh giới khác nhau, không tự bảo đảm exactly-once business effects.



