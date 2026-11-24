# Key, value và envelope trong Debezium

## 1. Vì sao phải hiểu hợp đồng của một CDC message?

Trong module **SPRING_INTEGRATION_ADAPTERS**, các hệ thống ngoài được kết nối với Spring Integration thông qua inbound/outbound adapter, gateway, poller và `MessageChannel`. Với nguồn cơ sở dữ liệu, một kiến trúc phổ biến là **Debezium** đọc transaction log, phát các sự kiện CDC vào Kafka, còn **Spring Integration Kafka inbound adapter** nhận chúng và chuyển đến transformer, router hoặc service activator.

Khi nhận được một message, code xử lý cần trả lời được:

- **Bản ghi nào thay đổi?** Thường tìm trong Kafka message **key**.
- **Thay đổi gì và dữ liệu trước/sau là gì?** Tìm trong message **value**, thường là một **envelope** có `before`, `after`, `op` và `source`.
- **Nguồn thay đổi ở đâu, được ghi nhận khi nào?** Đọc metadata trong `source`, timestamp và thông tin transaction nếu có.
- **Khi nào được xóa hoặc bỏ qua?** Phân biệt CDC delete event với Kafka tombstone; xét trạng thái snapshot và SMT.
- **Có thể xử lý lặp lại không?** Dựa trên idempotency, thứ tự, checkpoint nguồn và consumer acknowledgment.

Nếu chỉ giải mã phần `after` và bỏ toàn bộ metadata, ứng dụng có thể đồng bộ được những hàng được insert nhưng xử lý sai DELETE, đọc nhầm dữ liệu snapshot thành giao dịch mới, hoặc mất thông tin khi cần phát lại.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **Kafka record key**, **Kafka record value** và **Debezium event envelope**.
2. Đọc các trường `before`, `after`, `source`, `op`, `ts_ms` và `transaction` theo ngữ cảnh.
3. Giải thích khác nhau giữa envelope logic và lớp bọc `schema/payload` của Kafka Connect JSON converter.
4. Xử lý đúng `r/c/u/d`, tombstone, key thay đổi, bảng không có primary key và SMT unwrap.
5. Thiết kế message contract, key mapping, idempotency và lỗi deserialization trong Spring Integration.

## 2. Cấu trúc một Kafka record do Debezium phát ra

Kafka record có các thành phần tách biệt: **topic**, **partition**, **offset**, **timestamp**, **headers**, **key** và **value**. Debezium xây dựng key/value theo hợp đồng của source connector; Kafka broker gán offset của record trong partition.

~~~mermaid
flowchart LR
    DB[(Database<br/>transaction log)] --> DZ[Debezium<br/>source connector]
    DZ --> K[(Kafka topic)]
    K --> AD[Spring Integration<br/>Kafka inbound adapter]
    AD --> CH[MessageChannel]
    CH --> MAP[Transformer<br/>giải mã contract]
    MAP --> ROUTE{op / loại record}
    ROUTE --> UPSERT[Upsert projection]
    ROUTE --> DEL[Delete / tombstone policy]
    ROUTE --> ERR[Error / retry policy]
~~~

Với bảng `sales.orders` có primary key `id = 42`, một record update có thể được hình dung như sau:

~~~text
Kafka record
  topic:     orders-cdc.sales.orders
  partition: 1
  offset:    2058                 <- offset Kafka, không phải binlog position
  key:       {"id":42}            <- định danh bản ghi
  value:     {                    <- Debezium change-event envelope
               "before": {...},
               "after": {...},
               "source": {...},
               "op": "u",
               "ts_ms": 1763892000000
             }
  headers:   ...                  <- Kafka headers, tùy cấu hình
~~~

Ví dụ trên giả định JSON converter **không kèm Kafka Connect schema trong payload**. Hình dạng thật còn phụ thuộc connector, phiên bản, converter, Single Message Transform (SMT) và cấu hình.

### Phân biệt record và envelope

| Thành phần | Ví dụ | Nằm ở đâu? | Dùng để làm gì? |
|---|---|---|---|
| Kafka record key | `{"id":42}` | Key của Kafka record | Partitioning, gom các thay đổi cùng đối tượng, upsert |
| Kafka record value | Object JSON hoặc bytes | Value của Kafka record | Mang nội dung CDC; có thể null với tombstone |
| Debezium envelope | `before`, `after`, `source`, `op`… | Thường là nội dung logic của value | Diễn tả loại thay đổi và metadata |
| Kafka record offset | `2058` | Metadata của topic partition | Theo dõi/commit tiến độ tiêu thụ Kafka |
| Debezium source position | `file/pos`, `lsn`… | Thường trong `value.source` và source offset | Theo dõi vị trí transaction log của database |
| Kafka headers | Các header theo adapter/SMT | Metadata ngoài value | Mang thông tin giao vận hoặc bổ sung theo pipeline |

**Không đánh đồng** Kafka message key với cột `id` trong bảng khi bảng có khóa tổng hợp; cũng không đánh đồng Kafka offset với vị trí log của Debezium.

## 3. Key: bản ghi nào đang thay đổi?

### 3.1. Key mặc định thường xuất phát từ primary key

Với các bảng có primary key và connector hỗ trợ, Debezium thường dùng giá trị primary key để tạo key của change event.

Ví dụ:

~~~sql
CREATE TABLE sales.orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL
);
~~~

Một event cho đơn hàng `id = 42` có key logic:

~~~json
{"id": 42}
~~~

Nếu bảng `order_items` có primary key tổng hợp (`order_id`, `line_no`), key có thể là:

~~~json
{"order_id": 42, "line_no": 2}
~~~

**Key không phải bản sao của toàn bộ row.** `status`, `customer_id` hoặc `quantity` không tự xuất hiện trong key nếu không thuộc cấu hình key. Với các connector hỗ trợ, có thể chọn thêm cột định danh thông qua các tùy chọn như `message.key.columns`; điều kiện, cú pháp và hệ quả phụ thuộc connector.

### 3.2. Vì sao Kafka key quan trọng?

Kafka producer thường dùng key để xác định partition. Khi nhiều thay đổi của **cùng một khóa ổn định** được đưa vào cùng partition và producer giữ thứ tự theo log, Kafka giữ thứ tự các record trong partition đó. Điều này hỗ trợ projection áp dụng các update của cùng bản ghi theo đúng trình tự.

Tuy nhiên:

- **Không có thứ tự toàn cục** giữa các Kafka partition.
- Thay đổi số partition, strategy partitioner, cách serialize key hoặc routing topic có thể làm thay đổi cách phân bố record; cần đánh giá khi muốn giữ thứ tự xuyên suốt migration.
- Một transaction nguồn có thể thay đổi nhiều bảng/khóa và trở thành nhiều record nằm ở nhiều topic/partition.
- Consumer Spring Integration xử lý bất đồng bộ/đa luồng có thể làm đảo thứ tự *áp dụng* nếu không kiểm soát concurrency, dù Kafka đã đọc đúng thứ tự.

Key còn quan trọng với **compacted topic**. Kafka log compaction giữ lại bản ghi mới hơn theo key, chứ không theo các field trong `after`. Vì vậy dùng key thay đổi hoặc rỗng không đúng ý nghĩa nghiệp vụ sẽ ảnh hưởng khả năng dựng lại trạng thái.

### 3.3. Nếu bảng không có primary key?

Với bảng thiếu primary key, key mặc định có thể là **null** hoặc được xây theo cấu hình key bổ sung tùy connector. Hệ quả thường gặp:

1. Các thay đổi của một hàng khó được định danh ổn định.
2. Compacted topic không thể khôi phục trạng thái từng hàng đáng tin cậy chỉ từ key null.
3. Sink upsert/delete khó ánh xạ chính xác một hàng, đặc biệt khi có nhiều bản ghi giống nhau.
4. Không có bảo đảm cùng một thực thể luôn nằm trên cùng partition.

Nếu cần đồng bộ trạng thái, nên ưu tiên bảng có khóa nghiệp vụ/primary key ổn định hoặc thiết kế chiến lược identity rõ ràng và kiểm chứng được với connector.

### 3.4. Khi primary key thay đổi

Thay đổi primary key không phải update thông thường đối với dòng record theo khóa. Ở những connector Debezium có hỗ trợ mô hình này, một cập nhật key có thể được biểu diễn thành **DELETE cho khóa cũ**, tiếp theo **CREATE cho khóa mới**; tombstone và header mang old/new key có thể xuất hiện theo connector/cấu hình.

Ví dụ chuyển `id=42` sang `id=420`:

~~~text
Record 1: key={"id":42},  value=op:"d", after:null
Record 2: key={"id":42},  value=null       (tombstone nếu được bật)
Record 3: key={"id":420}, value=op:"c", after:{"id":420,...}
~~~

Đây là **mô hình minh họa**, không phải phát biểu rằng mọi connector đều xuất đúng ba record hay cùng thứ tự quan sát ở tất cả partition. Nếu sink chỉ thực hiện UPSERT theo key mới mà không xóa key cũ, sẽ còn bản ghi “ma”.

## 4. Value và envelope: bản ghi đã thay đổi như thế nào?

Trong dạng sự kiện Debezium thông thường, phần **value** mang một envelope với các trường cốt lõi sau:

| Trường | Nội dung | Ý nghĩa sử dụng |
|---|---|---|
| `before` | Trạng thái cũ của hàng, hoặc null/không đầy đủ tùy nguồn và cấu hình | So sánh, audit, xử lý delete/update |
| `after` | Trạng thái mới của hàng; null với delete event | Upsert/khởi tạo projection |
| `source` | Metadata như connector, logical name, database/table, snapshot, vị trí log, timestamp nguồn | Truy vết, phân biệt nguồn, hỗ trợ chẩn đoán |
| `op` | Loại thao tác: thường `r`, `c`, `u`, `d` | Định tuyến xử lý theo hành vi |
| `ts_ms` / `ts_us` / `ts_ns` | Thời điểm connector xử lý/phát sự kiện với độ phân giải tùy phiên bản | Phân tích độ trễ, quan sát |
| `transaction` | Metadata transaction nếu được cấu hình/hỗ trợ | Quan sát nhóm và thứ tự thay đổi trong transaction |

Một số connector/version có thêm trường khác, hoặc chỉ phát một tập con các trường trên. Giá trị `source.ts_ms`, khi có, thường liên quan tới thời điểm thay đổi ở nguồn; `ts_ms` cấp envelope thường do connector ghi nhận. **Không xem chúng là khóa định danh sự kiện**, và cần cân nhắc chênh lệch đồng hồ.

### 4.1. Ví dụ update envelope

Giả sử ứng dụng cập nhật đơn 42 từ `NEW` sang `PAID`:

~~~sql
UPDATE sales.orders
SET status = 'PAID'
WHERE id = 42;
~~~

Key và value minh họa **dạng logic, đã rút gọn**:

**Key**

~~~json
{"id": 42}
~~~

**Value**

~~~json
{
  "before": {
    "id": 42,
    "customer_id": 8001,
    "status": "NEW"
  },
  "after": {
    "id": 42,
    "customer_id": 8001,
    "status": "PAID"
  },
  "source": {
    "version": "example",
    "connector": "mysql",
    "name": "orders-cdc",
    "db": "sales",
    "table": "orders",
    "file": "mysql-bin.000008",
    "pos": 12034,
    "row": 0,
    "snapshot": "false"
  },
  "op": "u",
  "ts_ms": 1763892000000,
  "transaction": null
}
~~~

Các số, timestamp, file và metadata ở trên chỉ phục vụ ví dụ. `version` là placeholder để nhắc rằng source metadata tùy phiên bản; không dùng chuỗi `example` làm giá trị thực trong cấu hình. Trên PostgreSQL, `source` thường chứa `lsn` thay vì cặp binlog `file/pos`.

### 4.2. Ý nghĩa của `op`

| `op` | Tên | Dạng `before` / `after` thường gặp | Cách xử lý hay dùng |
|---|---|---|---|
| `r` | Read | `before=null`, `after` chứa hàng hiện tại | Upsert trạng thái đọc từ snapshot |
| `c` | Create | `before=null`, `after` chứa hàng mới | Insert hoặc idempotent upsert |
| `u` | Update | Có thể có `before`; `after` là hàng mới | Upsert/so sánh phiên bản tùy nghiệp vụ |
| `d` | Delete | `after=null`; `before` tùy khả năng nguồn | Delete hoặc đánh dấu xóa theo key |

Trong phạm vi nhất định, một số connector còn phát operation khác như **TRUNCATE** (ví dụ `op="t"`) hoặc message đặc biệt. Heartbeat, transaction metadata và schema notification cũng có thể đi qua những topic/record có contract riêng. **Handler chỉ hỗ trợ `r/c/u/d` cần chính sách rõ ràng** cho sự kiện không nhận diện, thay vì mặc định coi tất cả là INSERT.

### 4.3. Giá trị `before` không phải lúc nào cũng đầy đủ

Đừng giả định `before` của UPDATE luôn chứa mọi cột. Tùy database, connector, cấu hình log/replication identity và operation:

- `before` có thể có đủ old row, chỉ một số cột khóa, hoặc null;
- `after` thường phản ánh dữ liệu mới mà connector có thể tái dựng, nhưng trường không được capture/biểu diễn đặc biệt vẫn cần xem xét;
- Với PostgreSQL, **REPLICA IDENTITY** ảnh hưởng lượng thông tin old row có thể được phát trong logical replication;
- Với một số nguồn, cột lớn, kiểu nhạy cảm hoặc cấu hình chỉ một số cột có thể dẫn tới placeholder/giá trị không đầy đủ.

Nếu nghiệp vụ cần **giá trị trước khi thay đổi**, hãy kiểm chứng cấu hình source và dữ liệu sự kiện thực tế. Không dùng phép trừ giữa `after` và `before` khi chưa biết chắc cả hai biểu diễn đúng trạng thái cần tính.

## 5. Vòng đời INSERT, UPDATE, DELETE và snapshot

Giả sử bảng chỉ có `id` và `status`. Cùng key `{"id":42}` có thể trải qua:

~~~mermaid
sequenceDiagram
    participant DB as Database
    participant D as Debezium
    participant K as Kafka
    participant SI as Spring Integration
    DB->>D: INSERT id=42, NEW
    D->>K: key=42, op=c, after=NEW
    K->>SI: UPSERT (NEW)
    DB->>D: UPDATE id=42, PAID
    D->>K: key=42, op=u, before=NEW, after=PAID
    K->>SI: UPSERT (PAID)
    DB->>D: DELETE id=42
    D->>K: key=42, op=d, after=null
    K->>SI: DELETE (42)
    opt Tombstone được bật
        D->>K: key=42, value=null
        K->>SI: Áp dụng tombstone policy
    end
~~~

Nếu Debezium bắt đầu bằng **initial snapshot**, một hàng đã có trước đó thường được phát như `op="r"`. Vì vậy:

- `op="r"` không có nghĩa người dùng vừa tạo đơn hàng mới;
- cập nhật reporting projection từ `r` có thể phù hợp, nhưng gửi email “đơn vừa tạo” từ `r` có thể gây hậu quả;
- khi snapshot và streaming nối tiếp, trạng thái cuối phụ thuộc việc áp dụng đúng các message và kiểm soát thứ tự/đồng bộ.

## 6. Delete event khác với Kafka tombstone

Đây là điểm quan trọng nhất khi xử lý value null.

**Delete event** là một CDC change event có **value vẫn là envelope** với `op="d"` và `after=null`. Nó mang ý nghĩa “hàng đã bị xóa khỏi bảng nguồn”.

**Tombstone** là một **Kafka record riêng có cùng key nhưng value ở mức Kafka bằng null**. Với compacted topic, tombstone thông báo rằng giá trị mới nhất của key đã bị xóa, cho phép compaction loại bỏ trạng thái trước đó theo cơ chế và chính sách lưu giữ của Kafka.

~~~text
DELETE record:
  key:   {"id":42}
  value: {"before":{"id":42,...},"after":null,"op":"d",...}

TOMBSTONE record (nếu connector/config phát):
  key:   {"id":42}
  value: null
~~~

Tombstone không phải chuỗi JSON `"null"`, không phải object `{"after":null}`, và không tự có `op="d"` để đọc.

### 6.1. Tránh xử lý xóa hai lần

Nếu handler nhận `d` rồi xóa bản ghi projection, tombstone đến sau có thể:

- được bỏ qua có kiểm soát vì projection đã xóa;
- được sử dụng như một tín hiệu dọn cache;
- được chuyển tới nhánh chính sách riêng cho compacted topic.

Chỉ nên làm thêm side effect khi đã xác định ý nghĩa nghiệp vụ. Xóa lặp cần idempotent, nhất là khi message bị replay.

### 6.2. Lưu ý khi dùng Spring Integration Kafka inbound adapter

Kafka value null có thể được deserializer/adapter biểu diễn bằng **đối tượng sentinel** như `KafkaNull` hoặc cơ chế khác tùy phiên bản và cấu hình, vì Spring `Message` thường không cho payload Java null. Vì vậy không nên chỉ viết `if (payload == null)` rồi cho rằng đã bắt được mọi tombstone. Cần kiểm tra contract của Kafka adapter, converter và cách nó biểu diễn tombstone trong Spring Integration.

Một số SMT có thể **loại tombstone**, **viết lại delete thành record có cờ xóa**, hoặc chuyển đổi envelope. Nếu downstream không thấy event `d` như mong đợi, hãy xác định pipeline có thực hiện SMT nào không.

## 7. Envelope và lớp bọc `schema/payload` của JSON converter

Một nhầm lẫn phổ biến là cho rằng mọi Kafka JSON value của Debezium đều có trường top-level `before`. Điều này chỉ đúng khi converter/pipeline đưa ra dạng JSON phẳng tương ứng.

Với Kafka Connect **JsonConverter** và `schemas.enable=false`, dữ liệu logic có thể hiện ra trực tiếp:

~~~json
{
  "before": null,
  "after": {"id": 42, "status": "NEW"},
  "source": {"connector": "mysql", "db": "sales", "table": "orders"},
  "op": "c",
  "ts_ms": 1763892000000
}
~~~

Với `schemas.enable=true`, JsonConverter có thể tạo một lớp ngoài:

~~~json
{
  "schema": {
    "type": "struct",
    "name": "orders-cdc.sales.orders.Envelope",
    "fields": [
      {"type": "struct", "field": "before", "optional": true},
      {"type": "struct", "field": "after", "optional": true},
      {"type": "struct", "field": "source", "optional": false},
      {"type": "string", "field": "op", "optional": false}
    ]
  },
  "payload": {
    "before": null,
    "after": {"id": 42, "status": "NEW"},
    "source": {"connector": "mysql", "db": "sales", "table": "orders"},
    "op": "c",
    "ts_ms": 1763892000000
  }
}
~~~

Đây là ví dụ **rút gọn, không phải schema Connect hợp lệ hoàn chỉnh để đem dùng trực tiếp**: trong thực tế schema của `before`, `after`, `source` có các field con cùng thông tin kiểu cụ thể. Key cũng có thể có cặp `schema/payload` nếu `key.converter.schemas.enable=true`.

| Dạng truyền | Consumer cần hiểu gì? |
|---|---|
| JSON converter, tắt schema | Đọc envelope trực tiếp từ value sau khi giải mã JSON |
| JSON converter, bật schema | Đọc envelope trong `payload` và có thể dùng `schema` để xác thực |
| Avro / Protobuf / JSON Schema + registry | Dùng converter/deserializer tương ứng; không kỳ vọng bytes là JSON text |
| Debezium SMT unwrap | Value có thể chỉ còn row state + metadata thêm vào; `before/after/op` có thể không còn ở vị trí ban đầu |
| Tombstone | Kafka value null, không có JSON envelope |

**Schema của Kafka Connect** mô tả cấu trúc serialization. Nó **khác** schema change event thông báo DDL và **khác** internal schema history mà một số connector dùng để giải mã transaction log.

## 8. Single Message Transform: khi envelope được unwrap

Debezium cung cấp SMT **ExtractNewRecordState** (thường gọi là *unwrap*), dùng khi downstream muốn nhận “trạng thái hàng” thay vì toàn bộ envelope.

**Trước unwrap:**

~~~json
{
  "before": {"id": 42, "status": "NEW"},
  "after": {"id": 42, "status": "PAID"},
  "op": "u",
  "source": {"db": "sales", "table": "orders"}
}
~~~

**Sau unwrap (minh họa khi giữ trạng thái hàng mới):**

~~~json
{"id": 42, "status": "PAID"}
~~~

Lợi ích là giảm độ phức tạp của sink chỉ cần upsert. Đổi lại, **không còn thông tin before/op/source trong value mặc định** nếu cấu hình không giữ hoặc bổ sung metadata. Hệ quả:

- Không thể suy ra DELETE chỉ từ việc không thấy `after` nếu SMT đã loại event;
- không còn dữ liệu trước update để so sánh nếu chưa lưu nơi khác;
- cần xử lý snapshot, delete và tombstone theo cấu hình SMT;
- hệ thống audit có thể cần giữ envelope gốc ở nhánh khác;
- có thể chọn bổ sung metadata như operation/source field bằng các tùy chọn của SMT (phụ thuộc phiên bản).

Trích đoạn cấu hình Kafka Connect chỉ để chỉ ra **vị trí áp dụng SMT**, không phải cấu hình đầy đủ:

~~~properties
transforms=unwrap
transforms.unwrap.type=io.debezium.transforms.ExtractNewRecordState
~~~

Các tùy chọn delete/tombstone và metadata bổ sung đã có thay đổi qua các phiên bản Debezium; cần đọc đúng tài liệu phiên bản triển khai, nhất là khi thay đổi cấu hình nhằm giữ tombstone hoặc viết lại delete.

**Quy tắc thiết kế:** xác định chính xác consumer Spring Integration nhận **raw envelope**, **envelope nằm trong payload**, hay **row đã unwrap**. Không viết một transformer kỳ vọng cả ba dạng mà không có hợp đồng nhận diện rõ ràng.

## 9. Source metadata và transaction: truy vết thay đổi đến từ đâu?

Trường `source` thường mô tả:

| Nhóm thông tin | Trường ví dụ | Cách sử dụng |
|---|---|---|
| Định danh nguồn | `connector`, `name` | Xác định loại và logical source |
| Phạm vi dữ liệu | `db`, `schema`, `table`, `collection` | Phân luồng, audit, xác thực |
| Vị trí log | MySQL `file`/`pos`/`row`/`gtid`, PostgreSQL `lsn` | Điều tra sự cố, resume ở tầng connector |
| Snapshot | `snapshot` | Phân biệt snapshot read với event streaming |
| Thời gian | `source.ts_ms` khi có, envelope `ts_ms` | Theo dõi lag tương đối và sự chênh lệch |
| Transaction | `transaction.id`, `total_order`, `data_collection_order` khi có | Liên kết và phân tích thứ tự sự kiện trong giao dịch |

Một số connector hỗ trợ transaction metadata riêng khi bật cấu hình thích hợp (ví dụ `provide.transaction.metadata` đối với connector hỗ trợ). Việc metadata tồn tại, kiểu dữ liệu và khả năng kết nối transaction qua nhiều bảng phải được kiểm tra cho phiên bản thực tế.

### Source offset khác metadata vị trí trong một event

Debezium quản lý **source offset** để xác định checkpoint an toàn cần lưu trong offset store; đó có thể là tập nhiều trường gồm cả trạng thái snapshot hoặc vị trí bên trong giao dịch. `value.source.pos` hay `value.source.lsn` là metadata hữu ích cho một event, **không phải toàn bộ trạng thái checkpoint có thể tự ghi đè bằng tay**.

Khi một event đã được phát lên Kafka nhưng source offset chưa flush thì Debezium có thể phát lại event sau restart. Ngược lại, Spring Integration còn có **consumer group offset** riêng và có thể đọc lại record Kafka nếu chưa commit.

Do đó, để thiết kế dedupe ở downstream, đừng giả định mọi event có một khóa duy nhất toàn cục bằng `ts_ms` hoặc `lsn`. Có thể cần source identity, table, record key, metadata thứ tự trong transaction và cách connector bảo đảm phát sự kiện; nhiều ứng dụng chỉ cần idempotent upsert theo phiên bản hợp lệ của bản ghi.

## 10. Ánh xạ Debezium record sang Spring Integration Message

Khi dùng **Spring Integration Kafka inbound adapter**, Kafka record được chuyển thành Spring `Message<?>`. Adapter, deserializer và message converter quyết định dạng payload/headers.

| Kafka / Debezium | Có thể được biểu diễn ở Spring Integration | Vai trò |
|---|---|---|
| Kafka record value | `Message.payload`: bytes, String, JSON tree, POJO, Avro… | Dữ liệu để transformer xử lý |
| Kafka record key | Header liên quan received key hoặc field do converter cung cấp | Định danh nghiệp vụ, partition key |
| Topic / partition / offset | Các Kafka metadata headers tùy adapter/version | Debug, observability, retry/ack |
| Debezium `op`, `before`, `after` | Field trong payload khi còn envelope | Xác định update/insert/delete |
| Debezium `source` | Field trong payload khi còn envelope | Truy vết và phân luồng |
| Kafka record value null | Null sentinel/cơ chế biểu diễn tombstone của adapter | Chính sách xóa/compaction |

**Lưu ý:** Kafka headers, Spring Message headers, key và Debezium `value.source` là những lớp thông tin khác nhau. Một số converter hoặc SMT chuyển metadata từ value sang header; khi đó mapping phải tuân theo cấu hình cụ thể.

### 10.1. Luồng xử lý đề xuất

~~~text
Kafka Debezium topic
    -> messageDrivenChannelAdapter
    -> cdcRawChannel
    -> deserialize + normalize envelope/unwrap/tombstone
    -> validate key, op, before, after, source
    -> route:
         r/c/u    -> upsert service activator
         d        -> delete service activator
         tombstone-> compacted-topic handling
         unknown  -> error channel / quarantine
    -> update projection trong transaction
    -> acknowledge/commit Kafka offset theo chính sách an toàn
~~~

Đây là **luồng logic**, không phải Java DSL cấu hình hoàn chỉnh. Mỗi adapter mode có chính sách ack, retry, transaction và lỗi khác nhau; việc chuyển một message qua `MessageChannel` bất đồng bộ không luôn có nghĩa transaction ở hệ thống đích đã commit.

### 10.2. Giả mã handler định hướng trạng thái

~~~text
onKafkaMessage(record):
    identity = decodeKey(record.key)

    if isTombstone(record.value):
        handleTombstone(identity)
        acknowledgeWhenSafe()
        return

    envelope = decodeEnvelopeOrRecognizedUnwrappedContract(record.value)
    validateKnownSource(envelope.source, record.topic)

    switch envelope.op:
      case "r":
      case "c":
      case "u":
        assert envelope.after != null
        transaction:
            upsertProjection(identity, envelope.after)
            recordIdempotencyStateIfNeeded(...)
        break

      case "d":
        transaction:
            deleteProjectionIdempotently(identity)
            recordIdempotencyStateIfNeeded(...)
        break

      default:
        routeToErrorChannelWithContext(...)
        return

    acknowledgeWhenSafe()
~~~

Nếu pipeline đã unwrap và bỏ `op`, handler không thể dùng `switch envelope.op`; cần hợp đồng riêng có metadata giữ lại hoặc quy ước row-state + delete policy. Với dữ liệu cần giữ thứ tự version, `upsertProjection` còn phải từ chối update cũ bị phát lại sau update mới, theo cách so sánh version hợp lệ cho nguồn.

### 10.3. Ví dụ Java: trích envelope ra khỏi JSON converter

Giả sử payload **đã được deserializer chuyển thành String JSON**, không phải bytes Avro/Protobuf. Đoạn code dưới minh họa khâu kiểm tra envelope; nó không phải bộ xử lý Kafka tombstone hoặc connector hoàn chỉnh:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class DebeziumEnvelopeRouter {
    private final ObjectMapper mapper = new ObjectMapper();

    @ServiceActivator(inputChannel = "cdcRawChannel")
    public void handle(Message<String> message) throws Exception {
        JsonNode outer = mapper.readTree(message.getPayload());
        JsonNode envelope = outer.hasNonNull("payload")
                ? outer.get("payload") : outer;
        String operation = envelope.path("op").asText("");
        JsonNode after = envelope.path("after");

        switch (operation) {
            case "r", "c", "u" -> {
                if (after.isMissingNode() || after.isNull()) {
                    throw new IllegalArgumentException("Missing after for " + operation);
                }
                // Đưa vào service idempotent upsert với key từ Kafka metadata.
            }
            case "d" -> {
                // Xóa theo Kafka key, không theo after (vì after = null).
            }
            default -> throw new IllegalArgumentException(
                    "Unsupported Debezium operation: " + operation);
        }
    }
}
~~~

Đoạn code minh họa **Java 17+**. Để dùng trong production cần cấu hình inbound adapter, xử lý `KafkaNull`/tombstone trước khi parse JSON, chuẩn hóa key và converter, transaction/ack/retry, observability và error channel. Nó cũng không chấp nhận payload đã unwrap, bởi vì contract đó không chứa `op`. Dùng lỗi rõ ràng và DLQ phù hợp khi không nhận diện được format.

## 11. Idempotency, checkpoint và lỗi khi ánh xạ key/value

| Tình huống | Rủi ro | Nguyên tắc xử lý |
|---|---|---|
| Debezium phát lại sau restart | Cùng thay đổi được đưa lên Kafka nhiều lần | Idempotent upsert/delete, dedupe nếu có side effect |
| Kafka consumer retry record | Cùng record được xử lý lại | Chỉ commit sau khi ghi đích an toàn |
| `op="r"` từ snapshot | Coi một đơn cũ là đơn vừa tạo | Dùng `r` để dựng trạng thái, không tự phát nghiệp vụ “đơn mới” |
| `before` không đầy đủ | Tính delta sai | Dựa trên `after` hoặc hợp đồng nguồn đã kiểm chứng |
| Key null hoặc thay đổi | Dựng projection sai hàng, compaction sai | Chọn khóa ổn định; xử lý key migration rõ ràng |
| Kafka tombstone | Deserialize JSON thất bại hoặc xóa hai lần | Phát hiện sentinel/value null trước parser; xử lý idempotent |
| SMT unwrap bỏ `op` | Không biết delete/update/snapshot | Quy định metadata còn lại hoặc chặn cấu hình không phù hợp |
| Schema evolution thêm/đổi field | DTO cứng giải mã lỗi | Converter và model hỗ trợ cả event cũ/mới |
| Nhiều partition/concurrent handlers | Update đến sau có thể bị ghi trước | Kiểm soát concurrency, version/order theo từng key |
| Consumer commit trước DB transaction | Mất event ở projection sau crash | Transaction đích an toàn trước ack/commit theo thiết kế |

**Exactly-once end-to-end không tự có** chỉ vì Debezium đọc log có thứ tự. Để ngăn side effect lặp, ứng dụng thường kết hợp transactional outbox, idempotency key, ràng buộc unique, xử lý version hoặc transaction phối hợp phù hợp.

### Một chiến lược upsert thực tế

Giả sử projection `reporting.orders` chỉ cần **trạng thái mới nhất** cho từng `id`, handler có thể dùng một câu SQL UPSERT (cú pháp dưới là ví dụ PostgreSQL):

~~~sql
INSERT INTO reporting.orders (id, status)
VALUES (42, 'PAID')
ON CONFLICT (id)
DO UPDATE SET status = EXCLUDED.status;
~~~

UPSERT này an toàn khi nhận lại **cùng trạng thái** nhưng chưa tự bảo vệ khỏi việc một event **cũ hơn** đến sau và ghi đè trạng thái mới. Nếu có nhiều consumer song song hoặc replay chồng lên dữ liệu mới, cần quy tắc version/order đáng tin cậy, hoặc thiết kế xử lý tuần tự theo key.

## 12. Bài thực hành: đọc ba record và suy luận kết quả

Một topic Kafka dạng compacted lưu sự kiện cho bảng `sales.orders`. Giả sử contract chuẩn là Debezium envelope (chưa unwrap), key lấy từ `orders.id` và consumer áp dụng đúng thứ tự theo key.

**Record A**

~~~text
key:   {"id":7}
value: {"before":null,
        "after":{"id":7,"status":"NEW"},
        "op":"r",
        "source":{"snapshot":"true"}}
~~~

**Record B**

~~~text
key:   {"id":7}
value: {"before":{"id":7,"status":"NEW"},
        "after":{"id":7,"status":"SHIPPED"},
        "op":"u",
        "source":{"snapshot":"false"}}
~~~

**Record C**

~~~text
key:   {"id":7}
value: {"before":{"id":7,"status":"SHIPPED"},
        "after":null,
        "op":"d"}
~~~

Sau C, connector có thể phát thêm record **D** với cùng key và Kafka value **null**.

**Câu hỏi:**

1. `op="r"` ở A cho biết điều gì? Có nên gửi email “đơn hàng mới tạo” không?
2. Sau khi xử lý A và B, projection của `id=7` có trạng thái gì?
3. Vì sao xử lý C cần lấy `id` từ key hoặc `before`, không lấy `after.id`?
4. D khác gì C và đóng vai trò gì trên compacted topic?
5. Nếu dùng `ExtractNewRecordState`, thiếu thông tin gì để code `switch(op)` vẫn hoạt động?
6. Nếu B được phát lại sau khi C đã xử lý và được ghi đích, làm sao tránh khôi phục nhầm bản ghi đã xóa?

<details>
<summary>Gợi ý đáp án</summary>

1. A là bản đọc từ snapshot. Dùng để khởi tạo/upsert projection; không đồng nghĩa đơn vừa được tạo ở thời điểm nhận message.
2. B là update: projection lưu `id=7, status=SHIPPED`.
3. Delete envelope có `after=null`; Kafka key là định danh ổn định cho record cần xóa.
4. D có Kafka value null, không chứa envelope hay `op`; nó giúp Kafka log compaction xử lý khóa bị xóa theo cơ chế lưu giữ của broker.
5. Sau unwrap, `op`/`before`/`source` có thể mất khỏi value; phải giữ metadata phù hợp hoặc thay đổi contract handler.
6. Dùng thứ tự xử lý theo key và version/metadata đủ tin cậy hoặc trạng thái dedupe/tombstone bền vững, không chỉ UPSERT vô điều kiện. Replay nguồn/consumer phải được tính tới.

</details>

## 13. Checklist chuẩn hóa key/value trước khi triển khai

- [ ] Xác định **connector, phiên bản, converter và SMT** của topic đang dùng.
- [ ] Chụp ví dụ record thực tế: Kafka key, value, headers, topic, partition, offset và dạng JSON/Avro/Protobuf.
- [ ] Xác nhận key được lấy từ primary key hay các cột cấu hình thêm; xử lý khóa tổng hợp và bảng thiếu PK.
- [ ] Xác định consumer nhận envelope trực tiếp, `schema/payload` hay row đã unwrap.
- [ ] Xử lý `r/c/u/d` và chính sách operation khác, snapshot, transaction metadata nếu có.
- [ ] Xử lý riêng `after=null` của delete event và Kafka value null của tombstone.
- [ ] Không giả định `before`, `source.ts_ms` hoặc `transaction` luôn đầy đủ.
- [ ] Kiểm tra hỗ trợ schema evolution, field mới/thiếu và thay đổi kiểu serialization.
- [ ] Đảm bảo Kafka key/partition và xử lý song song phù hợp yêu cầu thứ tự theo thực thể.
- [ ] Commit Kafka consumer offset sau khi xử lý đích thành công theo cơ chế adapter đã chọn.
- [ ] Thiết kế idempotency, error channel/DLQ, retry và khả năng replay từ Kafka hoặc nguồn.
- [ ] Kiểm thử insert → update → delete → tombstone, restart giữa xử lý và khóa đổi giá trị.

**Ghi nhớ:** **key** cho biết *bản ghi nào* là đối tượng của sự kiện; **value** mang *nội dung thay đổi*; còn **envelope** của Debezium giải thích *thay đổi diễn ra thế nào, tại nguồn nào và trong hoàn cảnh nào*. Trong Spring Integration, một hợp đồng chuyển đổi rõ ràng giữa Kafka record và `MessageChannel` là nền tảng để định tuyến chính xác, xử lý xóa đúng nghĩa và phục hồi an toàn khi có phát lại.
