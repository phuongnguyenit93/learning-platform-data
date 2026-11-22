# Tiến hóa schema của bảng nguồn và tác động đến consumer

Trong pipeline Change Data Capture (CDC), thay đổi cấu trúc bảng ở database nguồn có thể làm thay đổi schema của record Kafka mà connector phát ra. Thêm cột, xóa cột, đổi kiểu dữ liệu, đổi tên bảng hoặc thay primary key đều có thể ảnh hưởng đến key/value, topic, partition, Schema Registry và code consumer. Một migration SQL chạy thành công vì thế chưa đủ để kết luận pipeline CDC vẫn tương thích.

Với Outbox Pattern, cần kiểm tra thêm hai hợp đồng độc lập: cấu trúc bảng outbox mà connector hoặc SMT đọc, và schema của event payload mà consumer nhận. Thêm một cột metadata có thể an toàn, nhưng đổi tên cột mà Event Router đang dùng có thể làm connector không định tuyến được event.

Bài này giải thích cách thay đổi schema có kiểm soát từ database nguồn đến Kafka consumer, phân biệt schema history của connector với schema message trên Kafka, và rollout theo hướng expand-contract để tránh gián đoạn CDC.

## 1. Một thay đổi ở database đi qua những lớp nào?

Một pipeline CDC thường có các lớp:

1. Database nguồn thay đổi DDL hoặc dữ liệu.
2. CDC connector đọc transaction log hoặc cơ chế capture của database.
3. Connector xác định schema nguồn và chuyển row/change thành record.
4. Converter serialize key/value sang bytes; nếu dùng Schema Registry, schema được đăng ký hoặc tra cứu theo subject.
5. Kafka lưu record trong topic và partition.
6. Consumer deserialize record, ánh xạ vào model và thực hiện logic nghiệp vụ.

~~~mermaid
flowchart LR
    DDL["Database DDL / DML"] --> DB[("Source database")]
    DB --> CDC["CDC connector"]
    CDC --> SR["Source schema mapping"]
    SR --> CV["Converter / Schema Registry"]
    CV --> K[("Kafka topic")]
    K --> C["Consumer deserializer"]
    C --> M["Consumer model / business logic"]
~~~

Một migration có thể tác động ở nhiều lớp:

| Lớp | Ví dụ thay đổi | Hậu quả có thể xảy ra |
|---|---|---|
| Database schema | Thêm, xóa, đổi tên cột; đổi kiểu; đổi primary key | Query, CDC parser hoặc mapping thay đổi |
| Connector schema | Connect Schema/Struct của key và value thay đổi | Serializer hoặc task có thể lỗi |
| Schema Registry | Schema mới được đăng ký hoặc bị compatibility policy từ chối | Producer task có thể thất bại khi phát record |
| Kafka record | Field, key, topic hoặc tombstone thay đổi | Consumer cũ có thể deserialize sai hoặc xử lý sai |
| Consumer model | Generated class, DTO hoặc validation không theo schema mới | Lỗi runtime hoặc sai nghiệp vụ |

Không phải mọi connector đều phát DDL thành record dữ liệu. Một số connector duy trì schema history nội bộ để diễn giải log; một số có thể phát schema change event riêng; hành vi phụ thuộc database, plugin và phiên bản. Consumer không nên giả định chỉ cần subscribe topic dữ liệu là sẽ nhận được mọi thông tin DDL.

## 2. Phân biệt schema history, message schema và business contract

Ba khái niệm này có liên quan nhưng không thay thế cho nhau.

| Thành phần | Lưu hoặc định nghĩa điều gì? | Ai sử dụng? |
|---|---|---|
| Schema history của CDC connector | Thông tin schema/DDL cần thiết để diễn giải thay đổi trong transaction log và phục hồi connector, nếu connector sử dụng cơ chế này | CDC connector |
| Schema của Kafka message | Hình dạng key/value được serialize vào record, có thể được quản lý bởi Schema Registry | Producer, converter và consumer |
| Business data contract | Ý nghĩa field, đơn vị, null semantics, key, state transition và quy tắc nghiệp vụ | Producer owner và consumer owner |

Ví dụ với Debezium:

- MySQL connector dùng schema history topic để lưu DDL cần thiết cho việc diễn giải binlog và phục hồi schema tại vị trí log tương ứng.
- Connector có thể phát schema change event tới topic riêng nếu tính năng đó được bật và connector/database hỗ trợ.
- Record dữ liệu trong topic bảng vẫn có envelope CDC như key, before, after, source, op và timestamp; đây là message schema mà consumer đọc.

Không áp dụng chi tiết của MySQL connector cho mọi connector. PostgreSQL, SQL Server, MongoDB và connector của nhà cung cấp khác có cách lấy metadata, ghi schema history và phát schema change khác nhau. Hãy kiểm tra tài liệu đúng connector/version trước khi thiết kế DDL rollout.

Schema history topic không phải bản backup database, không phải topic event nghiệp vụ và không nên bị xóa tùy tiện. Schema Registry cũng không thay thế schema history nội bộ của connector: Registry quản lý schema serialization, còn connector history phục vụ khả năng đọc/khôi phục source log theo cơ chế riêng.

## 3. CDC record thường thay đổi ra sao khi bảng nguồn đổi schema?

Với Debezium relational connector, record change thường có key xác định row và value dạng envelope. Envelope phổ biến gồm:

| Field | Vai trò |
|---|---|
| before | Trạng thái row trước thay đổi, nếu có |
| after | Trạng thái row sau thay đổi, nếu có |
| source | Metadata về database, table, log position và snapshot |
| op | Loại thao tác, ví dụ create, update, delete hoặc snapshot read |
| ts_ms / timestamp fields | Thời điểm liên quan đến capture theo định nghĩa connector |
| transaction | Metadata transaction nếu connector/configuration cung cấp |

Các operation thường gặp trong Debezium relational event:

| op | Ý nghĩa khái quát |
|---|---|
| c | Insert/create |
| u | Update |
| d | Delete |
| r | Read trong snapshot |

Tên field và chi tiết envelope có thể thay đổi theo Debezium version, connector và cấu hình. Consumer nên dùng đúng schema/serializer và tài liệu phiên bản triển khai.

Khi thêm cột, các event sau DDL có thể chứa field mới trong schema và trong after. Event lịch sử đã ghi trước DDL vẫn mang schema cũ. Consumer replay topic vì vậy có thể gặp nhiều schema version trong cùng một luồng.

Khi xóa cột, event mới có thể không còn field đó, nhưng record lịch sử vẫn giữ field cũ. Khi đổi kiểu, schema mới có thể khác kiểu cũ và serializer/Registry có thể từ chối nếu policy không cho phép. Consumer phải đọc được cả tập schema còn trong retention hoặc có chiến lược migration tương ứng.

## 4. Thêm cột: thay đổi thường dễ rollout nhất nhưng vẫn cần kiểm tra

Giả sử bảng orders hiện có:

~~~sql
CREATE TABLE orders (
    id           BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    total_minor  BIGINT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL
);
~~~

Nghiệp vụ cần thêm nguồn đơn hàng:

~~~sql
ALTER TABLE orders
ADD COLUMN sales_channel VARCHAR(30);
~~~

Ở database, cột mới có thể null đối với row cũ. CDC connector có thể phát schema mới cho các event sau thay đổi; row cũ được đọc trong snapshot/replay có thể có null hoặc giá trị default tùy DDL, database và connector.

Consumer cũ có thể:

- Bỏ qua field không biết nếu deserializer/model hỗ trợ unknown field.
- Deserialize thất bại nếu generated model hoặc schema reader yêu cầu cấu trúc cố định.
- Deserialize thành công nhưng logic mặc định sai nếu coi null là một channel cụ thể.

Consumer mới cần định nghĩa rõ sales_channel null có nghĩa là dữ liệu lịch sử chưa biết, channel không áp dụng hay producer chưa gửi. Không tự động gán giá trị BUSINESS nếu nguồn không chứng minh điều đó.

Quy trình an toàn:

1. Thêm cột nullable hoặc có default được xác định rõ.
2. Kiểm tra connector đọc được DDL và phát schema mới trong môi trường thử nghiệm.
3. Deploy consumer chấp nhận cả event cũ thiếu field và event mới có field.
4. Deploy ứng dụng ghi giá trị sales_channel.
5. Backfill row cũ nếu nghiệp vụ cần; đánh giá tải database và cách CDC ghi nhận backfill.
6. Theo dõi tỷ lệ null, giá trị không hợp lệ và lỗi deserialize.

Không thêm cột NOT NULL không có default vào bảng đang có dữ liệu nếu chưa đánh giá hành vi DDL của database, lock và thời gian migration. Một số database/version có thể rewrite table hoặc giữ lock đáng kể.

## 5. Xóa cột: consumer có thể còn cần dữ liệu trong lịch sử

Giả sử cột legacy_code không còn được ứng dụng ghi. Xóa cột ngay có thể làm:

- Consumer cũ không deserialize được event schema mới.
- Consumer vẫn deserialize nhưng logic đọc legacy_code bị lỗi.
- Một consumer replay dữ liệu lịch sử gặp cả record cũ có field và record mới không có field.
- Outbox/SMT hoặc query phụ thuộc cột đó bị lỗi.

Trước khi drop column:

1. Tìm mọi consumer và connector đang phụ thuộc cột.
2. Deploy consumer bỏ phụ thuộc nhưng vẫn đọc được schema cũ.
3. Dừng producer ghi cột hoặc ngừng sử dụng cột trong logic.
4. Chờ qua khoảng thời gian cần thiết cho rollback/replay và xác nhận không còn consumer cũ.
5. Drop column trong migration riêng.
6. Kiểm tra CDC task, schema Registry và consumer sau DDL.

Không xóa field khỏi consumer model ngay nếu topic còn giữ record cũ và consumer có thể replay. Với generated class, cần giữ khả năng đọc schema lịch sử theo cách serializer/deserializer hỗ trợ.

## 6. Đổi tên cột thường không phải rename semantics an toàn

Một lệnh rename trong database có thể được connector biểu diễn như thay đổi schema không tương thích. Không phải mọi CDC connector đều hiểu rename như một thao tác giữ nguyên identity của field; một số log chỉ thể hiện metadata DDL, hoặc connector có thể biểu diễn kết quả như field cũ biến mất và field mới xuất hiện.

Ví dụ:

~~~sql
ALTER TABLE orders
RENAME COLUMN customer_id TO buyer_id;
~~~

Consumer cũ mong đợi customer_id có thể thất bại ngay khi nhận event mới. Consumer mới chỉ đọc buyer_id có thể không đọc được record lịch sử cũ. Schema Registry compatibility cũng có thể từ chối đổi tên tùy format và policy.

### Dùng expand-contract thay cho rename trực tiếp

Một chiến lược an toàn hơn:

1. Thêm buyer_id nullable, giữ customer_id.
2. Cập nhật ứng dụng ghi đồng nhất cả hai field trong giai đoạn chuyển tiếp hoặc dùng cơ chế đồng bộ ở database.
3. Backfill buyer_id từ customer_id cho row cũ.
4. Deploy consumer đọc buyer_id trước, fallback customer_id khi xử lý record lịch sử.
5. Chuyển producer và các truy vấn sang buyer_id.
6. Xác nhận không còn consumer/producer phụ thuộc customer_id.
7. Drop customer_id trong một release sau.

Nếu dual-write hai cột, phải bảo đảm chúng không mâu thuẫn. Có thể dùng một migration có kiểm soát, trigger tạm thời hoặc application write path thống nhất; tránh hai nguồn ghi độc lập tạo giá trị khác nhau.

## 7. Thay đổi kiểu dữ liệu và giới hạn tương thích

Thay đổi kiểu có thể làm schema message đổi theo. Mức độ an toàn phụ thuộc hướng thay đổi, format, connector mapping và kiểu mà consumer sử dụng.

| Thay đổi | Rủi ro cần đánh giá |
|---|---|
| INT → BIGINT | Giá trị mới có thể vượt miền int; consumer cũ có thể overflow hoặc không đọc schema mới |
| BIGINT → INT | Có nguy cơ mất dữ liệu nếu giá trị vượt giới hạn int; thường là thay đổi nguy hiểm |
| VARCHAR(30) → VARCHAR(100) | Schema message có thể vẫn là string nhưng constraint/validation của consumer có thể khác |
| DECIMAL precision/scale | Thay đổi độ chính xác hoặc scale có thể đổi biểu diễn và gây rounding |
| DATE → TIMESTAMP | Ý nghĩa thời điểm và timezone có thể thay đổi, không chỉ là kiểu |
| TIMESTAMP local → TIMESTAMPTZ | Cần quy định timezone và cách chuyển đổi dữ liệu hiện hữu |
| Nullable → NOT NULL | Consumer và producer phải xử lý row cũ/null trong giai đoạn chuyển tiếp |
| NOT NULL → Nullable | Consumer vốn giả định luôn có giá trị có thể lỗi hoặc áp dụng default sai |

Ví dụ đổi số tiền:

~~~sql
ALTER TABLE orders
ALTER COLUMN total_minor TYPE NUMERIC(20, 0);
~~~

Mặc dù mục đích là tăng miền giá trị, Connect schema có thể chuyển từ int64 sang decimal logical type tùy connector/converter. Consumer Java dùng Long có thể không ánh xạ trực tiếp được kiểu mới. Cần kiểm tra schema thực tế do connector phát ra thay vì suy luận chỉ từ DDL.

Đặc biệt với DECIMAL, kiểm tra precision, scale, rounding mode, byte encoding và cấu hình decimal handling của connector. Không chuyển số tiền sang floating point chỉ để dễ deserialize; floating point có thể làm mất độ chính xác tài chính.

## 8. Thay đổi primary key tác động đến Kafka key và partition

CDC connector thường dùng primary key hoặc cấu hình key columns để tạo Kafka record key. Thay đổi primary key có thể làm schema key thay đổi, không chỉ schema value.

Ví dụ trước đây key là order_id; sau migration, key được đổi thành composite key gồm tenant_id và order_id. Consumer có thể nhận key schema mới, còn record lịch sử giữ key cũ.

Tác động:

- Partitioning có thể thay đổi vì serialized key hoặc hash input thay đổi.
- Ordering theo entity có thể bị phân tán sang partition khác.
- Compacted topic có thể giữ hai key khác nhau cho cùng entity logic.
- Consumer state store hoặc cache theo key cũ không tự migrate.
- Sink connector dùng record key làm primary key có thể ghi sang row khác hoặc lỗi schema.

Nếu key là identity của row, không thay đổi key semantics tùy tiện trên cùng topic. Đánh giá topic mới, mapping key kép, migration state và cách xử lý tombstone. Với database hỗ trợ update primary key, CDC có thể biểu diễn như delete key cũ và create key mới; hành vi cụ thể cần kiểm thử theo connector.

## 9. Đổi tên bảng hoặc chuyển schema/database

Tên bảng thường góp phần tạo topic name trong CDC connector. Đổi tên bảng hoặc chuyển schema có thể làm connector phát dữ liệu vào topic mới, thay đổi routing hoặc yêu cầu cập nhật include/exclude list.

Trước khi đổi:

- Kiểm tra quy tắc topic naming và topic prefix của connector.
- Xác định consumer có subscribe theo tên topic cụ thể hay regex.
- Kiểm tra quyền truy cập và ACL cho topic mới.
- Kiểm tra snapshot, source partition/offset và schema history.
- Lập kế hoạch migrate consumer state và retention của topic cũ.
- Xác nhận connector có hỗ trợ rename/transfer table hay cần cấu hình mới.

Không giả định topic cũ sẽ tự chuyển thành topic mới hoặc consumer group tự hiểu hai topic là cùng một entity.

## 10. Schema Registry và các schema version của CDC event

Khi converter sử dụng Schema Registry, key và value thường có subject riêng. Với TopicNameStrategy phổ biến, subject mặc định có dạng topic-key và topic-value; naming strategy khác có thể tổ chức subject theo record name hoặc topic/record.

Khi DDL thay đổi, connector có thể tạo schema mới. Serializer đăng ký schema mới theo subject; Registry kiểm tra compatibility policy. Nếu schema không tương thích, record mới có thể không serialize được và source task thất bại hoặc retry tùy lỗi/runtime.

Các policy thường gặp:

| Policy | Hướng kiểm tra |
|---|---|
| BACKWARD | Consumer schema mới đọc được dữ liệu cũ |
| FORWARD | Consumer schema cũ đọc được dữ liệu mới |
| FULL | Cả hai hướng |
| *_TRANSITIVE | Kiểm tra với nhiều phiên bản lịch sử, không chỉ version liền trước |

Hướng rollout cần được chọn có chủ đích:

- Consumer mới triển khai trước producer/connector: thường cần backward compatibility để đọc record cũ.
- Producer/connector phát schema mới trước consumer: cần đánh giá forward compatibility để consumer cũ đọc record mới.
- Topic có retention dài hoặc replay nhiều tháng: cân nhắc transitive compatibility và test với toàn bộ schema còn có thể xuất hiện.

Schema Registry chỉ kiểm tra structural compatibility theo format và policy. Registry không biết đổi customer_id sang buyer_id có giữ nguyên identity hay amount đổi từ dollar sang cent. Semantic contract vẫn cần review và test riêng.

Nếu dùng JSON converter không Schema Registry, consumer vẫn phải xử lý schema evolution nhưng không có compatibility gate tự động. Cần versioning, validation và contract tests ở CI.

## 11. Snapshot và replay sau khi schema nguồn thay đổi

CDC connector có thể thực hiện snapshot ban đầu hoặc incremental snapshot rồi chuyển sang streaming log. Snapshot record thường được đánh dấu bằng operation riêng (ví dụ op=r trong Debezium relational event), không phải insert mới do ứng dụng tạo.

Khi schema nguồn đổi:

- Snapshot mới có thể đọc row theo schema hiện tại.
- Topic vẫn có record lịch sử theo schema trước migration.
- Consumer group reset offset có thể replay record cũ rồi mới đến record mới.
- Schema Registry cần giữ schema version tương ứng với record còn tồn tại.
- Connector schema history/offset storage phải đủ để phục hồi đúng vị trí log theo cơ chế connector.

Không xóa schema history topic hoặc reset source offsets chỉ để “làm mới schema” khi chưa có runbook. Việc đó có thể làm connector mất khả năng diễn giải log hoặc đọc lại lượng dữ liệu lớn, tạo duplicate và tăng tải database.

Trước một snapshot lớn, đánh giá tải nguồn, lock/isolation, thời gian chạy, topic retention, consumer lag và khả năng downstream xử lý snapshot event. Kiểm thử incremental snapshot và restart/rebalance theo đúng connector version.

## 12. Tiến hóa schema của bảng Outbox

Outbox table là một phần của hợp đồng giữa ứng dụng ghi database và CDC connector/SMT. Một schema phổ biến có các cột:

~~~sql
CREATE TABLE outbox_events (
    id             UUID PRIMARY KEY,
    aggregatetype  VARCHAR(100) NOT NULL,
    aggregateid    VARCHAR(200) NOT NULL,
    type           VARCHAR(150) NOT NULL,
    payload        JSONB NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong Debezium Outbox Event Router, các cột thường được ánh xạ theo vai trò:

| Cột | Vai trò thường dùng |
|---|---|
| id | Event ID, có thể được dùng để trace/deduplicate |
| aggregatetype | Loại aggregate, thường tham gia route topic |
| aggregateid | Event key, giúp giữ ordering theo aggregate |
| type | Event type, có thể được đưa vào header |
| payload | Nội dung event được phát ra |
| created_at | Metadata thời gian nếu cấu hình SMT sử dụng |

Tên cột và mapping có thể cấu hình. Phải kiểm tra cấu hình Event Router thực tế thay vì giả định mọi outbox table đều dùng tên mặc định.

### Thay đổi an toàn trong Outbox table

Thêm cột metadata không được SMT sử dụng, ví dụ trace_id nullable, thường ít ảnh hưởng hơn nếu connector và converter xử lý schema mới. Tuy nhiên, vẫn phải kiểm tra schema Registry và consumer nếu record CDC thô của bảng outbox được phát ra topic.

Đổi tên hoặc xóa các cột mà SMT phụ thuộc có thể làm:

- Connector không khởi tạo được SMT hoặc task fail khi xử lý record.
- Event không được route sang topic đúng.
- Key bị null hoặc đổi identity, làm mất ordering theo aggregate.
- Header event type bị thiếu hoặc đổi tên.
- Payload không còn được trích xuất đúng.

Vì vậy, thay đổi cột id, aggregatetype, aggregateid, type hoặc payload cần được coi là migration contract của Outbox, không chỉ là DDL thông thường.

### Payload schema là hợp đồng riêng

Payload JSON/Avro/Protobuf có schema riêng với schema bảng outbox. Có thể giữ cấu trúc bảng outbox ổn định trong thời gian dài trong khi payload event version tiến hóa độc lập.

Ví dụ:

- Outbox table giữ cột payload JSONB.
- Event OrderCreated v1 có customerId và totalMinor.
- Event OrderCreated v2 bổ sung salesChannel.
- Consumer mới đọc được cả v1 và v2; consumer cũ tiếp tục đọc v1 trong giai đoạn rollout.

Không dùng việc đổi kiểu cột payload hoặc đổi SMT để âm thầm thay nghĩa event. Hãy version payload contract, kiểm tra Schema Registry nếu dùng schema-aware converter và kiểm thử consumer với event lịch sử.

## 13. Rollout expand-contract cho thay đổi nguồn

Một quy trình tổng quát:

### Giai đoạn 1 — Discover

1. Liệt kê bảng, cột, primary key và topic CDC liên quan.
2. Liệt kê connector, plugin version, converter, SMT và schema subject.
3. Xác định consumer owner, consumer version và retention/replay window.
4. Ghi lại semantics của field, key, nullability, đơn vị và timestamp.

### Giai đoạn 2 — Expand

1. Thêm cột mới theo cách tương thích, thường là nullable hoặc có default được định nghĩa rõ.
2. Giữ cột cũ để consumer cũ tiếp tục hoạt động.
3. Kiểm thử DDL trên database cùng loại/version và connector giống production.
4. Kiểm tra schema mới được serialize và đăng ký Registry thành công.
5. Deploy consumer tolerant trước khi producer bắt đầu phát giá trị mới.

### Giai đoạn 3 — Migrate

1. Cập nhật producer/application ghi cột mới.
2. Dual-write hoặc đồng bộ cột cũ/mới nếu cần.
3. Backfill dữ liệu cũ có kiểm soát.
4. Theo dõi CDC throughput, schema errors, consumer lag và null/error rate.
5. Đối soát số row và event theo khóa nghiệp vụ.

### Giai đoạn 4 — Contract

1. Xác nhận mọi consumer đã ngừng phụ thuộc cột cũ.
2. Chờ qua thời gian rollback và replay cần thiết.
3. Dừng dual-write và xóa cột cũ trong migration riêng.
4. Kiểm tra connector/task sau DDL và consumer sau khi schema mới xuất hiện.
5. Lưu schema/contract history và runbook phục hồi.

~~~mermaid
flowchart TD
    A["Discover consumers, topics, keys and schemas"] --> B["Expand: add new nullable column"]
    B --> C["Deploy tolerant consumers"]
    C --> D["Deploy writers: populate new column"]
    D --> E["Backfill and reconcile"]
    E --> F{"All consumers migrated and replay window passed?"}
    F -->|No| E
    F -->|Yes| G["Contract: stop old field and drop later"]
    G --> H["Verify CDC, Registry and consumers"]
~~~

Không phải mọi migration đều phù hợp dual-write. Nếu hai field có thể lệch nhau, cần xác định nguồn chuẩn và quy tắc đồng bộ rõ ràng. Với thay đổi primary key hoặc table routing, có thể cần topic mới và migration consumer state thay vì expand-contract trên cùng topic.

## 14. Kiểm thử trước khi chạy DDL production

Một bộ kiểm thử tốt phải chạy qua database, connector, converter/Registry và consumer, không chỉ kiểm tra SQL migration.

| Nhóm kiểm thử | Nội dung |
|---|---|
| Database migration | DDL thành công, lock/downtime, default, null và backfill |
| Connector capture | Task không fail, đọc đúng DDL/DML và source offset |
| Schema evolution | Schema mới đăng ký được; schema lịch sử vẫn deserialize |
| Key evolution | Key schema, partition và ordering có đúng mong đợi |
| Consumer compatibility | Consumer cũ/mới xử lý record cũ và mới |
| Snapshot/replay | Snapshot event, replay và restart không làm mất hoặc nhân đôi nghiệp vụ ngoài ý muốn |
| Outbox routing | Event Router vẫn lấy đúng key, topic, type, payload và headers |
| Failure recovery | Restart task/worker trong lúc DDL hoặc capture; kiểm tra offset/schema history |

Một kịch bản thử nghiệm cụ thể:

1. Tạo bảng orders với schema v1 và chạy connector.
2. Ghi insert/update/delete và lưu fixture record.
3. Thêm một cột nullable; kiểm tra schema của record mới.
4. Chạy consumer v1 và v2 trên fixture cũ/mới.
5. Đổi kiểu hoặc rename trong môi trường test để xác định lỗi thực tế.
6. Kiểm tra Schema Registry compatibility và lỗi serialization.
7. Restart connector tại các thời điểm khác nhau; kiểm tra duplicate và source offset.
8. Nếu dùng Outbox SMT, thêm/đổi cột metadata và xác nhận route/payload.

Không chỉ kiểm tra task ở trạng thái RUNNING. Hãy xác nhận record đúng key/value, đúng topic, đúng schema và đúng kết quả nghiệp vụ ở consumer.

## 15. Monitoring và xử lý sự cố sau DDL

Sau migration, theo dõi:

- Connector/task state và lỗi schema/serialization.
- Source log position hoặc source offset lag.
- Kafka topic throughput, partition distribution và consumer lag.
- Schema Registry registration/compatibility errors.
- Deserialize exception và unknown/nullable field rate ở consumer.
- Tỷ lệ event thiếu field, giá trị default hoặc dữ liệu không hợp lệ.
- Outbox backlog, tuổi row chưa được capture và số event route lỗi.
- Duplicate theo event ID và lỗi idempotency ở consumer.

| Triệu chứng | Hướng điều tra |
|---|---|
| CDC task FAILED sau DDL | Đọc trace connector, kiểm tra kiểu cột, DDL support, converter và schema history |
| Schema Registry từ chối schema | Kiểm tra subject, compatibility policy, writer/reader direction và schema diff |
| Consumer lỗi deserialize | Kiểm tra schema ID/version, generated class, nullable/default và enum |
| Consumer chạy nhưng dữ liệu sai | Kiểm tra unit, timezone, null semantics, key và state transition |
| Event sang topic khác | Kiểm tra table/topic naming, route SMT và thay đổi schema/table |
| Sink ghi sai row | Kiểm tra key schema, primary key mapping và upsert |
| Outbox không phát event | Kiểm tra cột SMT, connector status, transaction commit và outbox cleanup |

Khi rollback DDL, nhớ rằng event mới có thể đã được ghi vào Kafka. Rollback database không tự xóa record Kafka đã phát. Consumer phải có khả năng xử lý event đã phát hoặc cần một event bù trừ/forward fix; không xóa topic để che sai lệch dữ liệu.

## 16. Những hiểu nhầm thường gặp

- **“ALTER TABLE thành công nghĩa là CDC không bị ảnh hưởng.”** Connector, converter, Registry và consumer đều có thể bị tác động.
- **“Schema history topic là Schema Registry.”** Một số connector dùng history nội bộ để đọc log; Registry quản lý schema serialization cho message.
- **“Mọi connector đều phát DDL event.”** Hành vi phụ thuộc connector, database và cấu hình.
- **“Rename column luôn được hiểu là rename field.”** Connector có thể biểu diễn thành field cũ mất đi và field mới xuất hiện.
- **“Thêm cột nullable chắc chắn an toàn.”** Consumer strict, SMT hoặc Registry policy vẫn có thể từ chối schema mới.
- **“Đổi primary key chỉ ảnh hưởng database.”** Kafka key, partition, ordering, compaction và sink upsert có thể thay đổi.
- **“Xóa cột rồi replay vẫn có schema cũ.”** Record lịch sử có schema cũ, nhưng consumer phải còn khả năng đọc schema đó.
- **“Outbox payload và outbox table là một schema.”** Cấu trúc bảng và payload event là hai hợp đồng khác nhau.
- **“Rollback DDL sẽ rollback event đã vào Kafka.”** Kafka record đã commit không tự biến mất khi database rollback.
- **“Connector RUNNING chứng minh consumer xử lý đúng.”** Cần đối soát record và kết quả nghiệp vụ.

## 17. Checklist production

- [ ] Có inventory bảng nguồn, topic CDC, schema subject, connector/SMT và consumer owner.
- [ ] Đã phân biệt schema history nội bộ, Kafka message schema và business contract.
- [ ] Đã kiểm tra khả năng capture DDL theo đúng database, connector và version.
- [ ] Đã đánh giá thay đổi field, type, nullability, default, timestamp và primary key.
- [ ] Không rename/drop/đổi key trực tiếp khi consumer còn phụ thuộc.
- [ ] Schema Registry policy phù hợp rollout direction và replay window.
- [ ] Consumer mới đọc được record cũ; consumer cũ chỉ được giữ lại khi có forward compatibility cần thiết.
- [ ] Outbox SMT vẫn ánh xạ đúng id, aggregatetype, aggregateid, type và payload.
- [ ] Payload contract được version độc lập với bảng outbox.
- [ ] Đã thử DDL, snapshot, streaming, restart và replay trên môi trường tương đương production.
- [ ] Có kế hoạch expand-contract, backfill, dual-write và rollback/forward-fix.
- [ ] Có monitoring connector, Registry, consumer lag, deserialize error và dữ liệu nghiệp vụ.
- [ ] Không xóa schema history, source offsets hoặc topic lịch sử để xử lý sự cố một cách tùy tiện.

Tiến hóa schema của bảng nguồn là thay đổi xuyên suốt từ database đến consumer. Cần kiểm tra riêng DDL capture của connector, schema key/value trên Kafka, compatibility của Registry và ý nghĩa mà consumer áp dụng. Với Outbox, giữ ổn định các cột mà SMT phụ thuộc và version payload độc lập. Triển khai theo expand-contract, kiểm thử cả record lịch sử lẫn record mới, rồi chỉ loại bỏ field cũ khi toàn bộ consumer và replay window đã được xử lý.
