# Schema change event trong Debezium

## 1. Khi cấu trúc bảng thay đổi, luồng CDC biết được gì?

Ứng dụng dùng **Spring Integration Adapters** để kết nối các hệ thống ngoài thông qua inbound/outbound adapter, gateway, poller và `MessageChannel`. Trong hệ thống đồng bộ dữ liệu từ MySQL hoặc PostgreSQL, Debezium có thể thu nhận thay đổi từ transaction log và gửi các sự kiện qua Kafka (hoặc cơ chế phát sự kiện khác) cho luồng Spring Integration. Ngoài những thay đổi **dữ liệu hàng** như thêm, sửa và xóa, cấu trúc bảng nguồn cũng có thể thay đổi:

~~~sql
ALTER TABLE sales.orders
    ADD COLUMN coupon_code VARCHAR(32) NULL;
~~~

Sau câu lệnh này, hàng của bảng `sales.orders` có thể có thêm thuộc tính `coupon_code`. Ứng dụng đích vẫn dùng DTO chỉ có `id`, `status` và `total` có thể:

- Bỏ qua trường mới nếu converter/logic cho phép.
- Không giải mã được message nếu kiểm tra schema quá chặt.
- Lưu thiếu dữ liệu mới, dù Debezium vẫn thu nhận thay đổi.
- Đọc sai bản ghi nếu một cột bị đổi tên, đổi kiểu hoặc loại bỏ mà hợp đồng downstream chưa cập nhật.

Đối với những connector hỗ trợ, **schema change event** là thông báo mô tả sự thay đổi cấu trúc nguồn, thường bắt nguồn từ thao tác DDL như `CREATE TABLE`, `ALTER TABLE` hoặc `DROP TABLE`. Nó giúp hệ thống quan sát schema evolution và chuẩn bị thay đổi ở downstream. Tuy nhiên, **không phải mọi Debezium connector đều phát thông báo DDL theo cùng cách**.

**Mục tiêu bài học:** sau khi học, bạn có thể phân biệt schema change event với row change event, schema của Kafka Connect và internal schema history; hiểu ví dụ cấu hình/sự kiện MySQL; đánh giá tương thích schema; và thiết kế nhánh xử lý an toàn khi đưa sự kiện vào Spring Integration.

## 2. Phân biệt bốn khái niệm hay bị gọi chung là “schema”

| Khái niệm | Nội dung chính | Ai sử dụng? | Điều cần nhớ |
|---|---|---|---|
| **Schema change event** | Thông báo một thay đổi cấu trúc nguồn, ví dụ câu DDL và metadata của bảng | Monitoring, schema governance, pipeline điều phối | Được phát ở những connector có hỗ trợ; định dạng không đồng nhất giữa mọi connector |
| **Row change event** | Sự kiện dữ liệu `c`, `u`, `d`, `r` với `before`, `after` và metadata `source` | Service xử lý CDC, data sink, cache, search index | Khi cấu trúc bảng đổi, hình dạng `before`/`after` có thể đổi theo |
| **Schema của bản ghi Kafka Connect** | Mô tả kiểu/field của message được converter sử dụng nếu bật hỗ trợ schema | Converter, deserializer, Schema Registry (tùy cấu hình) | Metadata kiểu dữ liệu **không đồng nghĩa** với một sự kiện DDL |
| **Internal schema history** | Trạng thái lịch sử schema mà một số Debezium connector cần để giải mã bản ghi log khi phục hồi | Bản thân Debezium connector | Là dữ liệu vận hành nội bộ; không sử dụng như topic nghiệp vụ |

Ví dụ, khi thêm cột `coupon_code`:

1. Database xử lý DDL, làm thay đổi schema nguồn.
2. Debezium connector phù hợp cập nhật hiểu biết về schema, có thể ghi vào **internal schema history**.
3. Nếu connector hỗ trợ và bật phát schema change event, nó có thể phát thông báo DDL riêng.
4. Những **row change event** sau đó có thể mang trường `coupon_code` trong `after`; schema của message cũng có thể thay đổi.

Những bước này có mục đích khác nhau. Không nên kỳ vọng chỉ cần subscribe schema change topic là downstream đã tự cập nhật bảng đích hoặc Java DTO. Cũng không nên xem việc không thấy schema change topic là bằng chứng database chưa có DDL.

### 2.1. Schema change event khác với `op = "u"`

Row event `op = "u"` là **một hàng đã bị cập nhật**. DDL `ALTER TABLE` thay đổi **cấu trúc bảng**, không tương đương một bản ghi `u` cho mỗi hàng. Khi thêm cột có default, database có thể làm thay đổi cách các giá trị được nhìn thấy, nhưng không nên suy ra Debezium sẽ phát một event update cho toàn bộ các hàng cũ.

### 2.2. Schema change event khác với Schema Registry

Một connector phát thông báo DDL có thể hoạt động với Kafka JSON Converter, Avro Converter, Protobuf Converter hoặc định dạng khác. **Schema Registry** (khi có) quản lý schema serialization theo subject/version; schema change event của Debezium mô tả thao tác cấu trúc ở database. Một câu `ALTER TABLE` có thể kéo theo schema phiên bản mới trong Registry khi converter đăng ký schema mới, nhưng hai sự kiện không có quan hệ một-một bắt buộc. Registry cũng có thể thay schema do thay đổi cách biểu diễn event mà không có DDL tương ứng.

## 3. Luồng điển hình của MySQL schema change event

Với **Debezium MySQL connector**, DDL được ghi nhận từ binlog và được connector dùng để duy trì trạng thái schema. Tùy cấu hình, connector có thể phát schema change event tới một Kafka topic riêng.

~~~mermaid
flowchart LR
    DB[(MySQL)] -->|DDL trong binlog| DZ[Debezium MySQL connector]
    DZ -->|Cập nhật lịch sử nội bộ| HIST[(Internal schema history topic)]
    DZ -->|Schema change event| SC[(Schema change topic)]
    DZ -->|Data change events| ROW[(Row CDC topic)]
    SC --> SI1[Spring Integration<br/>schema monitoring flow]
    ROW --> SI2[Spring Integration<br/>row processing flow]
    SI1 --> AUDIT[(Audit / cảnh báo)]
    SI2 --> SINK[(Projection / hệ thống đích)]
~~~

Giả sử:

- `topic.prefix = shop-cdc`;
- database `sales`, bảng `orders`;
- MySQL connector xuất dữ liệu hàng vào topic dạng `shop-cdc.sales.orders`;
- connector phát thông báo schema vào topic mang tên logical server/topic prefix `shop-cdc`;
- internal schema history dùng topic **khác**, ví dụ `schemahistory.shop-cdc`.

Tên topic cụ thể còn phụ thuộc connector, cấu hình routing, phiên bản và bất kỳ Single Message Transform (SMT) nào đang được dùng. Ví dụ topic ở trên biểu thị **một cách triển khai MySQL điển hình**, không phải quy tắc chung cho PostgreSQL, SQL Server, Oracle hay mọi sink.

### 3.1. Cấu hình tham khảo

Các trường sau là **trích đoạn** cấu hình Debezium MySQL trên Kafka Connect; còn thiếu connection, credentials, quyền nguồn và nhiều thuộc tính cần thiết để chạy:

~~~json
{
  "name": "orders-mysql-cdc",
  "config": {
    "connector.class": "io.debezium.connector.mysql.MySqlConnector",
    "topic.prefix": "shop-cdc",
    "database.include.list": "sales",
    "table.include.list": "sales.orders",
    "include.schema.changes": "true",
    "schema.history.internal.kafka.bootstrap.servers": "kafka:9092",
    "schema.history.internal.kafka.topic": "schemahistory.shop-cdc"
  }
}
~~~

Hai nhóm cấu hình có vai trò khác nhau:

| Thuộc tính | Vai trò |
|---|---|
| `include.schema.changes` | Với connector hỗ trợ, điều khiển phát **thông báo schema change ra Kafka** |
| `schema.history.internal.kafka.bootstrap.servers`, `schema.history.internal.kafka.topic` | Chỉ định nơi lưu **lịch sử schema nội bộ** của connector |

Ở MySQL connector, đặt `include.schema.changes=false` thường chỉ tắt **schema change notification topic**; Debezium vẫn phải theo dõi schema để giải mã đúng các row event và vẫn cần cơ chế lịch sử schema nội bộ. **Không xóa internal schema history topic để tắt thông báo DDL.** Đó là trạng thái phục hồi của connector; mất trạng thái có thể khiến restart thất bại hoặc buộc phải thực hiện quy trình recovery.

Tên thuộc tính ví dụ phù hợp với các phiên bản Debezium MySQL dùng tiền tố `schema.history.internal.*`. Cần xác minh tài liệu tương ứng phiên bản thực tế; các bản Debezium cũ từng dùng tên cấu hình khác.

### 3.2. DDL và event minh họa

Một DBA thực thi:

~~~sql
ALTER TABLE sales.orders
    ADD COLUMN coupon_code VARCHAR(32) NULL;
~~~

Một schema change event **rút gọn để giải thích cấu trúc** có thể trông như sau (các trường trong `table` và metadata thực tế phong phú hơn, tùy connector/converter/version):

~~~json
{
  "source": {
    "connector": "mysql",
    "name": "shop-cdc",
    "db": "sales"
  },
  "ts_ms": 1763892000000,
  "databaseName": "sales",
  "schemaName": null,
  "ddl": "ALTER TABLE sales.orders ADD COLUMN coupon_code VARCHAR(32) NULL",
  "tableChanges": [
    {
      "type": "ALTER",
      "id": "sales.orders",
      "table": {
        "columns": [
          { "name": "id", "typeName": "BIGINT" },
          { "name": "status", "typeName": "VARCHAR" },
          { "name": "coupon_code", "typeName": "VARCHAR" }
        ]
      }
    }
  ]
}
~~~

Đây là **JSON minh họa có lược bỏ field**, không phải payload nguyên vẹn để dùng làm fixture tương thích với mọi converter. Trong thông báo thực tế:

- `source` cung cấp metadata nhận diện database/connector/vị trí log tùy nguồn.
- `databaseName` và `schemaName` cho biết phạm vi catalog/schema khi connector có thông tin tương ứng.
- `ddl` cung cấp câu DDL nguồn khi có sẵn; không nên dùng việc parse SQL bằng regex làm phương pháp duy nhất để hiểu mọi biến thể DDL.
- `tableChanges` mô tả danh sách thay đổi bảng ở dạng cấu trúc, có thể gồm `type` như `CREATE`, `ALTER`, `DROP`, định danh bảng và metadata cột/khóa.
- `ts_ms` thường là thời điểm được connector ghi nhận cho event; không dùng timestamp để thay cho source log position hoặc làm khóa duy nhất.

Nếu Kafka Connect JSON Converter bật `schemas.enable=true`, bản ghi có thể có vỏ ngoài `schema` và `payload`. Khi dùng Avro/Protobuf hoặc SMT, dạng dữ liệu đưa cho handler có thể hoàn toàn khác ví dụ JSON trên. **Cần quan sát message thực tế của hệ thống trước khi viết deserializer.**

## 4. DDL dẫn tới thay đổi cấu trúc row event như thế nào?

Giả sử bảng `sales.orders` ban đầu là:

~~~sql
CREATE TABLE sales.orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    total DECIMAL(12, 2) NOT NULL
);
~~~

Một event tạo đơn (row CDC) trước DDL có thể chứa:

~~~json
{
  "before": null,
  "after": { "id": 501, "status": "NEW", "total": "150.00" },
  "op": "c"
}
~~~

Sau câu `ALTER TABLE ... ADD COLUMN coupon_code ...`, một bản ghi thêm mới có thể chứa:

~~~json
{
  "before": null,
  "after": {
    "id": 502,
    "status": "NEW",
    "total": "240.00",
    "coupon_code": "SAVE10"
  },
  "op": "c"
}
~~~

Hai JSON trên chỉ nhằm thể hiện sự khác nhau về **tập field**. Giá trị số thập phân có thể được converter biểu diễn dưới dạng chuỗi, binary, số hoặc kiểu logical tùy cấu hình. Việc có schema change event riêng **không thay thế** việc xử lý schema mới ở row topic.

### 4.1. Dòng thời gian

~~~mermaid
sequenceDiagram
    participant DB as MySQL
    participant DZ as Debezium
    participant SC as Schema topic
    participant ROW as Row topic
    participant SI as Spring Integration
    DB->>DZ: DDL thêm cột coupon_code
    DZ->>DZ: Cập nhật cấu trúc + schema history
    DZ->>SC: Schema change event ALTER
    DB->>DZ: INSERT row có coupon_code
    DZ->>ROW: Row event op=c với schema mới
    SC-->>SI: Luồng metadata nhận event
    ROW-->>SI: Luồng dữ liệu nhận event
    Note over SC,ROW: Khác topic/partition: không có thứ tự quan sát toàn cục
~~~

Ngay cả khi DDL xảy ra **trước** INSERT trong transaction log nguồn, hai topic Kafka có thể có consumer và partition độc lập. **Không giả định** Spring Integration sẽ xử lý schema change event xong trước khi nhận row event schema mới. Ứng dụng cần tương thích đa phiên bản schema hoặc thiết kế cơ chế điều phối có kiểm chứng, thay vì chỉ hy vọng thứ tự đến từ hai topic là đủ.

### 4.2. Nếu DDL gồm nhiều thay đổi

Một câu `ALTER TABLE` có thể thêm, xóa, đổi tên hoặc thay kiểu nhiều cột; một lệnh `RENAME TABLE` có thể tác động nhiều bảng. Vì vậy parser phía sink không nên giả định `tableChanges` luôn có đúng một phần tử. Ngoài ra, một số connector chỉ cung cấp phần metadata nhất định, không nhất thiết tái hiện được toàn bộ SQL gốc dưới dạng đầy đủ và thống nhất.

## 5. Mức hỗ trợ schema change event tùy connector

Đừng áp dụng máy móc cách làm của MySQL cho mọi nguồn:

| Nguồn | Hành vi cần hiểu |
|---|---|
| **Debezium MySQL** | Có cơ chế nhận diện DDL/binlog, duy trì lịch sử schema và có thể phát schema change event ra Kafka khi được cấu hình hỗ trợ |
| **Debezium PostgreSQL** | Logical decoding/`pgoutput` phục vụ thay đổi dữ liệu; **không nên chờ một topic thông báo DDL giống MySQL**. Thay đổi schema có thể được phản ánh qua schema của row event tiếp theo; khả năng bắt DDL phụ thuộc giải pháp bổ sung |
| **Debezium SQL Server / Oracle** | Cơ chế lấy schema và các khả năng liên quan DDL khác MySQL; phải kiểm tra tài liệu và cấu hình connector/phiên bản đang dùng |
| **Debezium Engine / Debezium Server** | Cách nhận message, lưu offset và xuất thông báo tùy phiên bản, connector và sink; không mặc định có Kafka schema topic riêng |

**Điểm cần kiểm chứng trước thiết kế:** connector đang chạy có thực sự phát DDL notification không; tên topic/kênh của event là gì; định dạng payload ra sao; có lọc sự kiện theo database/table không; và cách xử lý schema history như thế nào. Nếu PostgreSQL cần audit toàn bộ DDL, có thể phải kết hợp database event trigger hoặc cơ chế audit schema ngoài Debezium, tuân theo khả năng và chính sách database.

## 6. Phân loại schema evolution và ảnh hưởng tới consumer

Không phải thay đổi DDL nào cũng nguy hiểm như nhau. Độ tương thích còn phụ thuộc cách mã hóa message, kiểu mapping Java, schema registry, hợp đồng API và logic nghiệp vụ.

| DDL ví dụ | Hệ quả thường gặp với CDC consumer | Hướng ứng phó |
|---|---|---|
| `ADD COLUMN coupon_code VARCHAR(32) NULL` | Message mới có field tùy chọn; message cũ không có field | Cho phép field thiếu/null, deploy consumer tương thích trước khi dùng field mới |
| `ADD COLUMN priority INT NOT NULL DEFAULT 0` | Field mới xuất hiện; semantics của default cần kiểm tra | Kiểm tra converter/default values, đồng bộ model đích |
| `DROP COLUMN legacy_code` | Consumer đọc field cũ có thể lỗi hoặc nhận null/thiếu | Loại phụ thuộc trước khi drop; version contract rõ ràng |
| `RENAME COLUMN status TO order_status` | Contract đổi tên field, không phải cập nhật giá trị | Cho phép giai đoạn chuyển đổi, hỗ trợ cả tên cũ và mới khi cần |
| `MODIFY total DECIMAL(12,2) -> DECIMAL(18,4)` | Precision/scale hoặc kiểu serialization thay đổi | Kiểm thử mapping, database đích, validator và tính toán tiền |
| `ALTER PRIMARY KEY` | Khóa Kafka/message có thể thay đổi; mapping sink/dedupe bị ảnh hưởng | Lập kế hoạch migration khóa, kiểm tra upsert/delete và phân vùng |
| `DROP TABLE` / `RENAME TABLE` | Topic, filter, routing, projection có thể không còn khớp | Cập nhật routing, lifecycle dữ liệu đích và cấu hình connector |

### 6.1. Expand–migrate–contract

Với hệ thống chạy liên tục, một quy trình thường an toàn hơn là:

1. **Expand:** thêm cột mới theo cách tương thích, triển khai converter/DTO có thể hiểu cả event cũ lẫn mới.
2. **Migrate:** cập nhật code ghi/đọc dữ liệu, kiểm tra topic và cập nhật projection/backfill nếu cần.
3. **Contract:** chỉ loại bỏ cột/field cũ sau khi tất cả consumer liên quan đã chuyển đổi và dữ liệu tồn đọng được xử lý.

Ví dụ muốn đổi `status` thành `order_status`, có thể thêm `order_status` trước, chuyển producer và consumer qua giai đoạn hai field, sau đó mới loại `status`. Độ dài giai đoạn tương thích phải tính tới Kafka retention, retry topic, batch tồn đọng và khả năng replay.

### 6.2. Phân biệt schema compatibility và data compatibility

Một sự thay đổi được Schema Registry chấp nhận theo quy tắc `BACKWARD` hoặc `FULL` (nếu dùng) **chưa chắc** an toàn về nghiệp vụ. Ví dụ đổi ý nghĩa cột `total` từ đơn vị VND sang đơn vị nghìn VND vẫn có thể giữ kiểu decimal, nhưng giá trị ở downstream sẽ sai. Ngược lại, handler dùng map linh hoạt có thể giải mã được JSON mới nhưng âm thầm bỏ qua một field bắt buộc về nghiệp vụ.

Cần đánh giá cả:

- **Wire compatibility:** consumer có giải mã được message không?
- **Structural compatibility:** field, kiểu, nullability và key có còn hợp lệ không?
- **Semantic compatibility:** đơn vị, ý nghĩa, quy tắc tính toán có thay đổi không?
- **Operational compatibility:** reprocess, retry, snapshot, routing và historical event có còn an toàn không?

## 7. Thiết kế hai nhánh Spring Integration: metadata và dữ liệu

Khi dùng Kafka làm trung gian, một thiết kế dễ kiểm soát là tách inbound adapter cho **schema topic** và **row topic**, đưa vào hai `MessageChannel` với hợp đồng xử lý khác nhau:

~~~text
MySQL -- Debezium --> Kafka: shop-cdc
                         |
                         +--> schemaChangeInboundAdapter
                         |      -> schemaChangeChannel
                         |      -> validate metadata
                         |      -> audit / alert / compatibility check
                         |
                         +--> row CDC topics: shop-cdc.sales.orders
                                -> rowChangeInboundAdapter
                                -> rowChangesChannel
                                -> transformer
                                -> service activator / projection writer
~~~

Trong **SPRING_INTEGRATION_ADAPTERS**, inbound adapter tiếp nhận message rồi gửi lên `MessageChannel`; transformer có thể chuẩn hóa message contract, filter bỏ event ngoài phạm vi, router phân tuyến; service activator xử lý nghiệp vụ và error channel/DLQ phục vụ lỗi theo thiết kế.

| Nhánh | Đầu vào | Công việc thích hợp | Điều không nên làm |
|---|---|---|---|
| `schemaChangeChannel` | DDL notification | Ghi audit, cảnh báo breaking change, mở ticket, kiểm tra tương thích, kích hoạt quy trình migration được duyệt | Tự thực thi mọi SQL DDL nhận được lên database đích |
| `rowChangesChannel` | `before/after` + `op` | Upsert, delete, cập nhật cache/search/projection, phát sự kiện nghiệp vụ đã lọc | Coi mọi event đều có cùng field cố định hoặc thực thi side effect trực tiếp từ snapshot/replay |

**Không tự động chạy câu `ddl` lấy từ event trên database đích.** DDL có thể không tương thích dialect, quyền, topology hoặc chính sách migration; việc đồng bộ schema cần kế hoạch migration, kiểm soát thứ tự và khả năng rollback riêng.

### 7.1. Ví dụ handler quan sát schema change event

Giả định adapter đã nhận schema topic, deserializer đã tạo payload JSON dạng `String`, và converter có thể trả object gốc hoặc bọc bằng `payload`. Java minh họa xử lý **metadata** (thay vì chạy DDL):

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class SchemaChangeObserver {
    private final ObjectMapper mapper = new ObjectMapper();

    @ServiceActivator(inputChannel = "schemaChangeChannel")
    public void observe(Message<String> message) throws Exception {
        JsonNode root = mapper.readTree(message.getPayload());
        JsonNode body = root.hasNonNull("payload")
                ? root.get("payload")
                : root;

        String database = body.path("databaseName").asText("");
        String ddl = body.path("ddl").asText("");
        JsonNode changes = body.path("tableChanges");

        if (!changes.isArray()) {
            throw new IllegalArgumentException("Missing tableChanges");
        }

        for (JsonNode change : changes) {
            String type = change.path("type").asText("");
            String tableId = change.path("id").asText("");
            // Thay bằng audit service, metrics hoặc compatibility check.
            // Không thực thi ddl trực tiếp trên database đích.
            System.out.printf("DDL event: db=%s table=%s type=%s%n",
                    database, tableId, type);
        }
    }
}
~~~

Đây là ví dụ **lược giản để học cách đọc event**, chưa có cấu hình Kafka inbound adapter, error handling, bảo mật audit log hoặc converter thực tế. Trong hệ thống production, có thể phải:

- Xử lý null và object dạng `byte[]`, `GenericRecord`, JSON tree hoặc POJO theo deserializer.
- Thực hiện validation với các event không có `tableChanges` hoặc có định dạng khác theo connector/version thay vì luôn ném lỗi.
- Gắn correlation metadata (source partition/offset, Kafka topic/partition/offset, connector, table) vào audit để điều tra và chống ghi trùng.
- Quy định cách retry/DLQ và cơ chế ack sao cho audit không bị mất khi handler lỗi.
- Hạn chế log toàn bộ SQL DDL nếu câu lệnh có dữ liệu nhạy cảm hoặc gây lộ cấu trúc hệ thống.

### 7.2. Vì sao cần chuẩn bị cho event mới trước khi deploy DDL?

Ví dụ consumer Java giải mã Kafka message với DTO:

~~~java
// Mã minh họa một DTO được dùng trước khi schema thay đổi.
public record OrderChange(Long id, String status, java.math.BigDecimal total) {}
~~~

Nếu converter/dữ liệu mới thêm `coupon_code`, cùng một DTO trên có thể tương thích hoặc thất bại tùy cấu hình object mapper và schema handling. Không thể suy ra chỉ từ kiểu `record`. Cách an toàn là kiểm thử với **cả event trước và sau DDL**, bao gồm event cũ được replay từ Kafka.

Khi thay schema, đặc biệt là drop/rename column, thêm phiên bản schema hoặc mapping tương thích sẽ đáng tin cậy hơn việc dùng một thay đổi DDL làm tín hiệu “từ lúc này mọi message đều theo schema mới”; các partition và consumer có thể còn message cũ chưa xử lý.

## 8. Offset, schema history, thứ tự và khả năng phục hồi

Schema thay đổi làm việc phục hồi CDC phức tạp hơn vì connector không chỉ cần vị trí log, mà còn cần biết **schema nào đúng với mỗi đoạn log đã đọc**.

### 8.1. Internal schema history phục vụ đọc lại log

Ví dụ:

1. Ở log position `P10`, bảng `orders` có 3 cột.
2. Ở `P20`, một DDL thêm cột `coupon_code`.
3. Ở `P30`, một INSERT ghi dữ liệu theo schema 4 cột.
4. Debezium crash sau `P30` nhưng offset bền vững vẫn ở `P15`.

Khi khởi động lại từ `P15`, connector phải giải mã đúng dữ liệu trước và sau `P20`. Với những connector có internal schema history như MySQL, lịch sử này hỗ trợ tái dựng schema phù hợp khi phát lại log. **Không chỉnh sửa hoặc thay thế internal schema history topic bằng những event DDL dùng cho monitoring.**

Thời điểm flush source offset và schema history có vòng đời riêng; cấu hình retention của log/database và độ bền của schema history đều ảnh hưởng tới khả năng resume.

### 8.2. Phát lại schema change event

Một sự kiện DDL được gửi thành công nhưng source offset chưa được flush có thể được phát lại sau restart tùy cơ chế và mức bảo đảm của connector. Vì vậy hệ thống audit nên ghi nhận idempotently khi có thể, ví dụ dùng khóa dựa trên **source identity, vị trí log và thông tin sự kiện phù hợp**. Một mình timestamp hoặc chỉ câu SQL text không phải khóa duy nhất đáng tin cậy cho mọi hệ quản trị.

### 8.3. Không suy ra đồng bộ từ việc nhận notification

Consumer schema topic nhận `ALTER TABLE` không chứng minh các consumer row topic đã nhận hết bản ghi schema cũ hay đã bắt đầu nhận schema mới. Tương tự, group offset của Kafka schema topic không phản ánh tình trạng cập nhật projection. Cần theo dõi riêng:

- Source offset và trạng thái Debezium connector.
- Độ bền/khả dụng của schema history.
- Kafka lag và lỗi deserialization theo từng consumer group/topic.
- Phiên bản schema mà code transformer/handler và database đích thực sự hỗ trợ.
- Trạng thái các migration liên quan.

## 9. Các lỗi thực tế và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xác minh |
|---|---|---|
| Đã chạy `ALTER TABLE` nhưng schema topic không có event | Connector không hỗ trợ notification, cấu hình tắt, lọc database/table, sai topic hoặc DDL không được capture | Xác minh loại connector, `include.schema.changes`, log và topic thực tế |
| Row topic có field mới nhưng schema topic không có thông báo | Connector chỉ phản ánh schema qua row event, hoặc topic notification bị tắt/bị bỏ qua | Kiểm tra converter/schema của row message và khả năng connector |
| Consumer lỗi khi giải mã sau DDL | DTO/schema Registry/mapping không chấp nhận field hoặc kiểu mới | So sánh message trước/sau DDL, chế độ converter, compatibility rule |
| Dữ liệu đích bị thiếu cột mới | Transformer/projection mapping không cập nhật | Kiểm tra mapping, bảng đích và kế hoạch backfill |
| Debezium không start được sau mất internal history | Connector không dựng lại được schema cũ để đọc offset/log cần thiết | Kiểm tra log lỗi, snapshot/recovery được hỗ trợ, backup và lịch sử schema |
| Schema event được ghi audit hai lần | Retry, source offset chưa flush hoặc consumer chưa commit | Dùng idempotency và lưu Kafka/source metadata |
| Event dữ liệu tới trước khi migration hoàn thành | Không có thứ tự toàn cục giữa các topic; triển khai lệch nhịp | Deploy consumer tương thích trước, dùng kiểm soát migration và kế hoạch rollback |
| Thay đổi primary key làm trùng bản ghi đích | Dedupe/partition/routing phụ thuộc key cũ | Kiểm tra key encoding, upsert/delete và tiến trình chuyển khóa |

**Nguyên tắc vận hành:** không chủ động xóa offset hoặc internal schema history để “đồng bộ nhanh” khi gặp lỗi schema. Việc mất lịch sử có thể khiến connector không giải mã được log cũ hoặc cần resnapshot. Phải đối soát khả năng phục hồi trước khi can thiệp.

## 10. Tình huống tổng hợp: thêm cột cho hệ thống đơn hàng

Giả sử MySQL `sales.orders` đang xuất CDC qua Debezium. Spring Integration đọc topic `shop-cdc.sales.orders` và cập nhật bảng `reporting.orders`. Product team yêu cầu thêm mã ưu đãi `coupon_code`.

**Bước chuẩn bị**

1. Xác định connector MySQL đang phát schema change event và có internal schema history bền vững.
2. Xác định converter và schema của row event; lấy event mẫu để kiểm tra handler có chấp nhận field mới.
3. Mở rộng bảng `reporting.orders`, cập nhật projection handler theo nguyên tắc field mới có thể null/không có ở event cũ.
4. Triển khai consumer tương thích và test replay event cũ **trước** khi thực thi DDL.

**Bước thay đổi schema nguồn**

~~~sql
ALTER TABLE sales.orders
    ADD COLUMN coupon_code VARCHAR(32) NULL;
~~~

**Bước xác minh**

- Quan sát schema change notification nếu connector hỗ trợ và bật tính năng; xác minh `tableChanges` thể hiện bảng và cột dự kiến.
- Tạo đơn mới có `coupon_code`, kiểm tra row event mang trường mới và handler ghi đúng projection.
- Xác nhận event cũ không có `coupon_code` vẫn được giải mã khi replay.
- Theo dõi lỗi converter, DLQ, consumer lag và số bản ghi đích.
- Ghi nhận migration hoàn tất sau đối soát; không dùng việc nhận một DDL notification duy nhất như bằng chứng kết thúc toàn bộ rollout.

**Nếu cần quay lui:** trước hết rollback phiên bản ứng dụng tương thích; việc `DROP COLUMN` để “undo nhanh” có thể gây mất dữ liệu và lại phát sinh một schema change khác. Cần lựa chọn rollback database theo quy trình migration đã thiết kế.

## 11. Bài tập thực hành

### Bài 1 — Phân loại event

Bạn nhận được hai message:

**Message A**

~~~json
{
  "ddl": "ALTER TABLE sales.orders ADD COLUMN coupon_code VARCHAR(32)",
  "tableChanges": [{ "type": "ALTER", "id": "sales.orders" }]
}
~~~

**Message B**

~~~json
{
  "before": { "id": 42, "status": "NEW" },
  "after": { "id": 42, "status": "PAID" },
  "op": "u"
}
~~~

Hãy xác định message nào thuộc nhánh metadata, message nào thuộc nhánh cập nhật projection; tại sao không đưa A vào cùng service activator vốn xử lý `op`?

### Bài 2 — Thay đổi breaking

Đội database muốn chạy:

~~~sql
ALTER TABLE sales.orders DROP COLUMN status;
~~~

Tại sao có thể phá vỡ consumer ngay cả khi schema change event đã được phát thành công? Hãy đề xuất thứ tự triển khai code, migration và xác minh phù hợp.

### Bài 3 — Không thấy topic schema ở PostgreSQL

Một nhóm sử dụng Debezium PostgreSQL với `pgoutput` và thấy row event có thêm field mới sau DDL, nhưng không thấy Kafka topic DDL giống MySQL. Hãy giải thích vì sao không nên kết luận connector đã bỏ sót row change, và cần theo dõi schema bằng cơ chế nào.

<details>
<summary>Gợi ý đáp án</summary>

1. Message A là **schema change notification** nên được đưa vào audit/compatibility flow; B là **row event update** và được xử lý ở projection flow. A không có ý nghĩa `before/after/op` như row CDC.
2. Những consumer còn đọc `status` sẽ gặp lỗi hoặc mất dữ liệu nghiệp vụ; phải sửa và triển khai bản tương thích, backfill/chuyển đổi dữ liệu cần thiết, kiểm tra message cũ trong Kafka rồi mới loại cột cũ.
3. PostgreSQL logical decoding không cung cấp cơ chế DDL notification tương đương MySQL trong mô hình phổ biến. Cần dựa trên schema của row event, quy trình migration và khi cần có audit DDL riêng của database; xác minh khả năng cụ thể của connector/version.

</details>

## 12. Checklist thiết kế và vận hành schema evolution

- [ ] Xác minh connector/version có hỗ trợ schema change event, topic/kênh nào và cấu trúc payload thực tế.
- [ ] Phân biệt rõ thông báo DDL, row event, Kafka Connect schema và Debezium internal schema history.
- [ ] Tách nhánh Spring Integration `schemaChangeChannel` và `rowChangesChannel` với hợp đồng message, retry và DLQ phù hợp.
- [ ] Không thực thi `ddl` tự động ở database đích chỉ vì nhận được notification.
- [ ] Kiểm tra tương thích field, kiểu, nullability, key, semantics và schema của các event cũ đang tồn tại.
- [ ] Thiết kế consumer chịu được thông báo lặp lại, thứ tự khác nhau giữa topic và restart.
- [ ] Giữ source offset, internal schema history và transaction log theo chính sách bền vững/retention đã kiểm chứng.
- [ ] Quan sát lỗi deserialization, event/schema version, consumer lag, audit và đối soát dữ liệu đích.
- [ ] Thực hành quy trình expand–migrate–contract cho đổi tên, bỏ cột hoặc đổi khóa.
- [ ] Có kịch bản kiểm thử replay trước/sau DDL và khôi phục khi connector không đọc được schema lịch sử.

**Ghi nhớ:** *Schema change event* thông báo thay đổi **cấu trúc dữ liệu nguồn**; *row change event* truyền thay đổi **giá trị bản ghi**. Đối với module Spring Integration Adapters, nhánh metadata giúp phát hiện và điều phối thay đổi hợp đồng, còn nhánh dữ liệu tiếp tục cập nhật hệ thống đích qua `MessageChannel`. Một pipeline CDC ổn định cần xử lý đồng thời schema evolution, message contract, log/offset recovery và tính tương thích của consumer.
