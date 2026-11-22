# Vai trò của Debezium trong pipeline CDC vào Kafka

Một ứng dụng nghiệp vụ thường ghi dữ liệu vào database trước khi hệ thống khác cần biết thay đổi đó. Nếu service vừa commit database vừa gửi một event riêng sang Kafka, hai thao tác có thể lệch nhau: database đã commit nhưng publish thất bại, hoặc Kafka đã nhận event trong khi transaction database rollback. Change Data Capture (CDC) giải quyết bài toán này bằng cách quan sát các thay đổi đã được database ghi nhận và chuyển chúng thành luồng sự kiện.

Debezium là nền tảng CDC mã nguồn mở, cung cấp các connector đọc transaction log hoặc cơ chế CDC của database rồi phát change event. Trong kiến trúc phổ biến, Debezium chạy như source connector trên Kafka Connect. Kafka Connect quản lý worker, connector, task, cấu hình và source offsets; Debezium hiểu định dạng log của từng database, tạo event có cấu trúc và ghi chúng vào Kafka topic.

Debezium không thay thế database, Kafka broker hay Kafka Connect. Vai trò của nó là biến thay đổi dữ liệu ở nguồn thành event stream có thể tiêu thụ, đồng thời theo dõi vị trí đã đọc để tiếp tục sau restart.

## 1. CDC giải quyết bài toán gì?

Giả sử Order Service tạo một đơn hàng trong database. Payment Service, Search Service và Analytics cần nhận biết đơn hàng mới.

Nếu Order Service tự ghi database rồi publish Kafka bằng hai thao tác riêng:

1. Database commit thành công.
2. Process dừng trước khi publish event.

Đơn hàng tồn tại nhưng downstream không nhận được event. Nếu đảo thứ tự, Kafka có thể nhận event trong khi transaction database thất bại. Transactional Outbox là một cách xử lý bằng cách ghi business row và outbox row trong cùng transaction; CDC có thể đọc outbox table và phát event.

CDC ở mức database rộng hơn Outbox: nó có thể ghi nhận insert, update và delete của các bảng được chọn, kể cả khi ứng dụng nguồn không phát domain event riêng. Tuy nhiên, thay đổi row không tự động mang đầy đủ ý nghĩa nghiệp vụ. Ví dụ một update cột status từ PENDING sang PAID cho biết dữ liệu thay đổi, nhưng không nhất thiết mô tả toàn bộ quy tắc nghiệp vụ của một sự kiện PaymentCaptured.

| Nhu cầu | CDC phù hợp khi | Cần cân nhắc |
|---|---|---|
| Đồng bộ dữ liệu giữa database và hệ thống khác | Muốn phát hiện thay đổi row mà không sửa từng service | Consumer phải hiểu schema và semantics của row |
| Xây dựng read model/search index | Cần cập nhật projection theo thay đổi nguồn | Phải xử lý snapshot, delete và thứ tự theo key |
| Replicate dữ liệu sang data lake | Muốn chuyển thay đổi liên tục thay vì quét toàn bảng | Cần quản lý schema, retention và backfill |
| Audit thay đổi | Cần lưu dấu thay đổi từ database | CDC không thay thế audit nghiệp vụ hoặc chính sách lưu trữ |
| Phát domain event | Muốn truyền ý nghĩa nghiệp vụ ổn định | Outbox/domain event thường phù hợp hơn việc suy diễn từ mọi row update |

## 2. Debezium nằm ở đâu trong kiến trúc?

Kiến trúc CDC vào Kafka thường gồm các thành phần:

~~~mermaid
flowchart LR
    A[Application transaction] --> B[(Source database)]
    B --> C[Transaction log / CDC mechanism]
    C --> D[Debezium source connector]
    D --> E[Kafka Connect worker]
    E --> F[Kafka topic]
    F --> G[Consumer group]
    G --> H[Search / cache / data platform]
    G --> I[Other services]
~~~

Vai trò từng thành phần:

| Thành phần | Vai trò |
|---|---|
| Source database | Lưu trạng thái nghiệp vụ và transaction log/CDC change records |
| Database log | Ghi lại thay đổi đã commit theo cơ chế riêng của database |
| Debezium connector | Đọc snapshot/log, diễn giải thay đổi và tạo SourceRecord |
| Kafka Connect worker | Chạy connector task, quản lý lifecycle, offset và cấu hình |
| Kafka topic | Lưu change event để nhiều consumer đọc độc lập |
| Consumer | Chuyển change event thành read model, cache, search document hoặc luồng xử lý khác |

Debezium có thể được triển khai theo nhiều cách. Phổ biến nhất khi đích là Kafka là Debezium connector chạy trên Kafka Connect distributed cluster. Debezium cũng có thể được nhúng qua Embedded Engine hoặc chạy qua Debezium Server để gửi dữ liệu tới một số đích khác. Bài này tập trung vào mô hình Kafka Connect source connector.

## 3. Kafka Connect, connector và task

Kafka Connect là runtime tích hợp dữ liệu giữa Kafka và các hệ thống khác:

- **Worker:** process chạy Kafka Connect. Distributed mode cho phép nhiều worker cùng tham gia một Connect cluster.
- **Connector:** cấu hình và điều phối một nguồn hoặc đích dữ liệu. Debezium MySQL Connector, Debezium PostgreSQL Connector là source connector.
- **Task:** đơn vị thực thi công việc do connector tạo ra. Task đọc dữ liệu từ nguồn và chuyển thành record cho Connect framework.
- **Converter:** chuyển key/value giữa Connect internal data model và format truyền trên Kafka, ví dụ JSON hoặc Avro.
- **Transformation (SMT):** biến đổi SourceRecord trước khi ghi topic, ví dụ đổi topic name hoặc unwrap envelope.

~~~mermaid
flowchart TD
    A[Kafka Connect distributed cluster] --> B[Worker 1]
    A --> C[Worker 2]
    B --> D[Debezium connector]
    D --> E[Task 0]
    D --> F[Task 1]
    E --> G[Read DB log]
    F --> H[Read assigned tables / partitions]
    G --> I[Connect SourceRecord]
    H --> I
    I --> J[Converter / SMT]
    J --> K[Kafka topic]
~~~

Một connector có thể tạo một hoặc nhiều task tùy connector và khả năng phân chia nguồn. Không phải cứ tăng tasks.max là Debezium sẽ đọc một database nhanh hơn theo tuyến tính. Một số connector có giới hạn về số task hoặc cách phân chia snapshot/log. Hãy kiểm tra tài liệu của connector cụ thể trước khi đặt tasks.max.

Trong distributed mode, worker phối hợp để phân công connector/task và khôi phục khi worker lỗi. Cấu hình connector được lưu trong Connect config topic; source offsets được lưu trong offset topic; trạng thái connector/task được lưu trong status topic. Các internal topic này thuộc Kafka Connect, không phải topic change event của Debezium.

### Ví dụ cấu hình worker distributed mode

~~~properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
group.id=inventory-connect-cluster

config.storage.topic=connect-configs
config.storage.replication.factor=3

offset.storage.topic=connect-offsets
offset.storage.partitions=25
offset.storage.replication.factor=3

status.storage.topic=connect-status
status.storage.partitions=5
status.storage.replication.factor=3

key.converter=org.apache.kafka.connect.json.JsonConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
key.converter.schemas.enable=false
value.converter.schemas.enable=false

plugin.path=/opt/kafka-connect/plugins
rest.port=8083
~~~

Đây là ví dụ để minh họa vai trò của worker properties; số partition và replication factor cần theo quy mô cluster. Connect config topic phải có đúng một partition và dùng compact cleanup policy; offsets và status topics cũng cần cleanup policy phù hợp với yêu cầu Kafka Connect (thường là compact). Nếu tự tạo internal topics trước, phải tạo đúng partition count, replication và cleanup policy thay vì chờ worker tạo mặc định. Tất cả worker trong cùng Connect cluster cần cùng plugin Debezium và phiên bản tương thích; cài plugin trên một worker không bảo đảm task có thể chạy ở worker khác sau rebalance.

## 4. Debezium đọc transaction log như thế nào?

Thay vì truy vấn bảng liên tục để tìm row mới, Debezium sử dụng cơ chế CDC của database. Tùy database, nguồn thay đổi có thể là:

| Database | Cơ chế thường dùng | Vị trí Debezium theo dõi |
|---|---|---|
| MySQL/MariaDB | Binary log (binlog) | File/position hoặc GTID và metadata liên quan |
| PostgreSQL | Logical decoding qua replication slot, thường dùng pgoutput | LSN và trạng thái replication slot |
| SQL Server | SQL Server CDC change tables | LSN và vị trí đọc CDC |
| Oracle | LogMiner hoặc adapter được hỗ trợ theo phiên bản | SCN và trạng thái mining |
| Db2 | Transaction log/CDC integration theo connector | Log position tương ứng |

Transaction log ghi lại thay đổi theo thứ tự mà database sử dụng để phục hồi và replication. Debezium đọc log để phát hiện thay đổi đã commit, tạo event rồi lưu tiến độ đọc vào Kafka Connect source offset storage.

### Vì sao đọc log tốt hơn polling bảng?

- Có thể phát hiện insert, update, delete mà không cần mỗi service tự query theo timestamp.
- Giảm phụ thuộc vào cột updated_at do ứng dụng quản lý.
- Tránh bỏ sót các thay đổi nhanh nếu nhiều lần update xảy ra giữa hai lần polling.
- Có thể giữ thứ tự thay đổi theo log trong phạm vi connector/database hỗ trợ.
- Có thể khôi phục từ log position sau restart nếu log nguồn vẫn còn.

Tuy nhiên, CDC phụ thuộc transaction log. Nếu log bị xóa trước khi connector đọc tới, connector có thể không tiếp tục được từ offset cũ và cần snapshot/recovery. Debezium không thể đọc lại một transaction log đã bị database loại bỏ.

## 5. Snapshot và streaming phase

Khi connector mới được tạo, database có thể đã chứa hàng triệu row trước khi CDC bắt đầu. Chỉ đọc log từ thời điểm hiện tại sẽ không tạo được trạng thái ban đầu đầy đủ cho downstream. Debezium thường giải quyết bằng snapshot rồi chuyển sang streaming.

Quy trình phổ biến với snapshot ban đầu:

1. Kết nối database và kiểm tra quyền/CDC configuration.
2. Xác định vị trí log phù hợp với snapshot.
3. Đọc schema và dữ liệu các bảng được chọn trong snapshot consistency boundary.
4. Phát các row snapshot vào Kafka dưới dạng change event có operation chỉ thị snapshot, thường là r.
5. Tiếp tục đọc transaction log từ vị trí đã phối hợp với snapshot.
6. Phát insert/update/delete phát sinh sau snapshot.

~~~mermaid
sequenceDiagram
    participant DB as Source database
    participant D as Debezium connector
    participant K as Kafka
    D->>DB: Mở snapshot và xác định log position
    D->>DB: Đọc schema và rows
    D->>K: Phát snapshot records (op=r)
    D->>DB: Tiếp tục đọc transaction log
    DB-->>D: Insert / update / delete đã commit
    D->>K: Phát change events
    D->>K: Lưu source offset qua Connect
~~~

Snapshot phải phối hợp với log position để không tạo khoảng trống giữa dữ liệu đọc từ bảng và thay đổi phát sinh trong lúc snapshot. Cách khóa, isolation và xử lý concurrent write phụ thuộc database connector và snapshot mode.

### Snapshot mode

Các connector Debezium có cấu hình snapshot mode để chọn cách khởi tạo hoặc khôi phục. Ví dụ phổ biến là snapshot.mode=initial, yêu cầu snapshot dữ liệu ban đầu khi cần. Các mode khác có thể hỗ trợ luôn snapshot, chỉ snapshot schema, chỉ stream hoặc hành vi khi không còn log position hợp lệ. Tên mode và semantics thay đổi theo connector/phiên bản; cần dùng tài liệu đúng phiên bản.

Không đổi snapshot mode tùy tiện trên connector đang chạy. Một lần snapshot lại có thể phát lại rất nhiều row, làm downstream xử lý trùng hoặc tăng tải database/Kafka.

### Snapshot event khác change event

Envelope của Debezium thường có field op để phân biệt loại thay đổi:

| Operation | Ý nghĩa thường gặp |
|---|---|
| r | Row được đọc trong snapshot |
| c | Insert/create |
| u | Update |
| d | Delete |

Consumer cần xử lý snapshot event như trạng thái ban đầu, không mặc định rằng mỗi record đều là một hành động mới do người dùng vừa thực hiện. Với projection kiểu upsert, snapshot và insert có thể cùng cập nhật một row theo key; với analytics, cần phân biệt snapshot với sự kiện phát sinh sau thời điểm bắt đầu.

## 6. Cấu trúc change event của Debezium

Với relational connector dùng envelope mặc định, change event thường có các phần:

| Field | Nội dung |
|---|---|
| before | Trạng thái row trước thay đổi, nếu connector/database cung cấp |
| after | Trạng thái row sau thay đổi |
| source | Metadata nguồn như database, table, log position, transaction và snapshot marker |
| op | Loại thao tác: read, create, update hoặc delete |
| ts_ms | Timestamp liên quan đến xử lý event theo định nghĩa connector |
| transaction | Metadata transaction nếu connector bật và phiên bản hỗ trợ |

Ví dụ minh họa event update:

~~~json
{
  "before": {
    "id": 1042,
    "status": "PENDING",
    "total_amount": 125000
  },
  "after": {
    "id": 1042,
    "status": "PAID",
    "total_amount": 125000
  },
  "source": {
    "connector": "mysql",
    "db": "commerce",
    "table": "orders"
  },
  "op": "u",
  "ts_ms": 1795169700000
}
~~~

Payload trên là ví dụ rút gọn; metadata thực tế có thể chứa nhiều field connector-specific như server ID, binlog position, GTID, snapshot state hoặc transaction ID. Không nên phụ thuộc vào field metadata không có trong contract của connector/version đang sử dụng.

### Kafka record key

Debezium thường dùng primary key của row làm Kafka record key. Key ổn định giúp mọi thay đổi của cùng một row đi về cùng partition khi partitioning strategy không đổi. Điều này hỗ trợ ordering theo row và upsert downstream.

Nếu bảng không có primary key hoặc unique key phù hợp, connector có thể tạo key khác hoặc record không có key theo cấu hình/connector. Với compacted topic, key ổn định đặc biệt quan trọng vì Kafka compaction dựa trên key.

Không đổi primary key chỉ vì muốn đổi cách partition mà chưa đánh giá downstream. Thay key có thể khiến các event cùng entity nằm ở partition khác nhau và mất ordering theo entity.

## 7. Topic naming và luồng dữ liệu

Debezium relational connector thường đặt tên topic theo prefix đã cấu hình và tên database/schema/table. Ví dụ:

~~~text
fulfillment.inventory.orders
fulfillment.inventory.order_items
fulfillment.inventory.customers
~~~

topic.prefix (hoặc thuộc tính tương đương trong connector/version cũ) tạo namespace cho dữ liệu của connector. Dùng prefix riêng theo môi trường và nguồn giúp tránh đụng tên topic khi nhiều database cùng phát dữ liệu.

Topic naming cần được xem là một phần contract cho consumer. Nếu đổi prefix hoặc topic routing, consumer, ACL, retention policy, schema subject và monitoring dashboard đều có thể cần cập nhật.

### Một bảng thường tương ứng một topic

Với relational connector, thay đổi của từng table thường được phát vào topic riêng. Điều này giúp consumer chỉ subscribe bảng cần thiết, nhưng không có nghĩa topic đó là domain event đã được chuẩn hóa. Nó vẫn phản ánh row-level change của database.

Một consumer có thể subscribe nhiều topic để xây dựng read model. Nếu cần join dữ liệu từ nhiều bảng, consumer phải xử lý quan hệ và thứ tự event; không giả định một transaction cập nhật nhiều bảng sẽ luôn xuất hiện như một record duy nhất.

## 8. Ví dụ cấu hình Debezium MySQL source connector

Trước khi tạo connector, database phải bật binlog và lưu log đủ lâu cho connector phục hồi. Cấu hình điển hình của MySQL gồm:

- Binary logging được bật.
- binlog_format=ROW.
- binlog_row_image=FULL nếu connector/kiểu capture cần toàn bộ row image.
- Server ID của MySQL instance duy nhất trong replication topology.
- Tài khoản Debezium có quyền đọc metadata/snapshot và quyền replication cần thiết.
- Binlog retention đủ dài để vượt qua thời gian outage dự kiến của connector.

Ví dụ cấu hình connector rút gọn:

~~~json
{
  "name": "inventory-mysql-cdc",
  "config": {
    "connector.class": "io.debezium.connector.mysql.MySqlConnector",
    "tasks.max": "1",
    "database.hostname": "mysql",
    "database.port": "3306",
    "database.user": "debezium",
    "database.password": "INJECT_FROM_SECRET_STORE",
    "database.server.id": "5401",
    "topic.prefix": "fulfillment",
    "database.include.list": "inventory",
    "table.include.list": "inventory.orders,inventory.order_items",
    "snapshot.mode": "initial",
    "schema.history.internal.kafka.bootstrap.servers": "kafka-1:9092,kafka-2:9092",
    "schema.history.internal.kafka.topic": "schema-history.inventory"
  }
}
~~~

Đây là ví dụ minh họa, không phải cấu hình production hoàn chỉnh. Tên property và yêu cầu privilege phụ thuộc Debezium connector version. Không ghi password thật trong file JSON; dùng secret provider hoặc cơ chế cấu hình bảo mật của Kafka Connect. Tài khoản database chỉ nên có quyền cần thiết cho snapshot, metadata và replication.

Gửi cấu hình tới Kafka Connect REST API:

~~~bash
curl -X POST http://connect-1:8083/connectors \
  -H "Content-Type: application/json" \
  --data @inventory-mysql-cdc.json
~~~

Sau khi tạo, kiểm tra trạng thái connector/task và log của worker:

~~~bash
curl http://connect-1:8083/connectors/inventory-mysql-cdc/status
~~~

Không chỉ nhìn HTTP 201 khi tạo connector. Connector có thể được tạo thành công nhưng task chuyển sang FAILED vì sai quyền database, không đọc được binlog hoặc không ghi được Kafka topic.

## 9. Ví dụ cấu hình Debezium PostgreSQL

PostgreSQL dùng logical decoding. Debezium thường sử dụng logical replication slot và publication để nhận các thay đổi của bảng được chọn.

Điều kiện thường cần kiểm tra:

- wal_level=logical.
- Đủ max_replication_slots và max_wal_senders.
- Tài khoản connector có quyền replication và quyền đọc schema/table phù hợp.
- Logical replication slot và publication được tạo theo chính sách DBA/connector.
- Theo dõi WAL retention vì slot không được tiêu thụ có thể giữ WAL và làm đầy disk.

Ví dụ cấu hình rút gọn:

~~~json
{
  "name": "inventory-postgres-cdc",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "tasks.max": "1",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "INJECT_FROM_SECRET_STORE",
    "database.dbname": "inventory",
    "topic.prefix": "fulfillment-pg",
    "plugin.name": "pgoutput",
    "slot.name": "debezium_inventory",
    "publication.name": "debezium_inventory_publication",
    "publication.autocreate.mode": "filtered",
    "table.include.list": "public.orders,public.order_items",
    "snapshot.mode": "initial"
  }
}
~~~

Tên và semantics property có thể khác theo phiên bản Debezium. Cần thống nhất với DBA về quyền tạo publication/slot, cách quản lý slot khi connector bị xóa và quy trình failover database. Không xóa replication slot đang giữ WAL nếu chưa xác định connector có thể tạo lại snapshot hay tiếp tục từ vị trí nào.

## 10. Source offsets và schema history

Hai loại metadata này có mục đích khác nhau và không được nhầm với topic chứa row change event.

### Kafka Connect source offsets

Kafka Connect lưu source offset để connector biết đã đọc tới đâu ở database. Ví dụ vị trí binlog/GTID của MySQL hoặc LSN của PostgreSQL. Khi connector restart, nó dùng offset đã lưu để tiếp tục.

Offset storage topic thuộc Connect cluster và được cấu hình qua offset.storage.topic trong worker distributed configuration. Đây không phải consumer offset trong __consumer_offsets: consumer group downstream quản lý tiến độ đọc change event của chính nó.

### Debezium schema history

Một số relational connector, đặc biệt MySQL và SQL Server, cần lưu lịch sử thay đổi schema để diễn giải đúng transaction log cũ. Schema history topic giữ các DDL/schema changes theo thứ tự cần thiết cho connector. Nó khác source offsets và khác data topic.

Các lưu ý:

- Không xóa schema history topic khi connector còn cần đọc log position cũ.
- Không dùng chung schema history topic cho các connector không cùng phạm vi.
- Bảo đảm replication, retention và quyền truy cập phù hợp.
- Một số connector yêu cầu schema history topic có đúng số partition/cleanup policy cụ thể; làm theo tài liệu của connector/version.
- Không đổi tên hoặc tạo lại topic schema history chỉ để dọn cluster khi chưa có kế hoạch snapshot/recovery.

### Bảng phân biệt

| Metadata | Ai dùng? | Mục đích |
|---|---|---|
| Connect config topic | Kafka Connect workers | Lưu cấu hình connector |
| Connect offsets topic | Kafka Connect source runtime | Lưu vị trí đọc từ database |
| Connect status topic | Kafka Connect workers/API | Lưu trạng thái connector/task |
| Debezium schema history topic | Connector có yêu cầu schema history | Khôi phục schema tại log position |
| Debezium data topic | Consumer downstream | Chứa row change event |
| __consumer_offsets | Kafka consumer group coordinator | Lưu committed offsets của consumer downstream |

Không reset consumer group offset để sửa source connector offset. Hai tiến độ thuộc hai hệ thống khác nhau.

## 11. Delete, tombstone và log compaction

Khi một row bị xóa, Debezium thường phát delete event với operation d, trong đó before có thể chứa trạng thái row trước khi xóa và after là null. Sau đó connector có thể phát tombstone record có cùng key và value null để Kafka log compaction biết rằng key đó đã bị xóa.

Consumer cần phân biệt:

1. Delete event: record có envelope Debezium và op=d, mang metadata về thao tác xóa.
2. Tombstone: Kafka record có key nhưng value null, không có envelope change event.

Nếu consumer chỉ muốn xóa document trong search index, có thể xử lý delete event và bỏ qua tombstone theo contract. Nếu consumer dùng compacted topic để tái tạo trạng thái mới nhất, tombstone là tín hiệu quan trọng để xóa key khỏi state.

Không cấu hình SMT unwrap hoặc converter theo cách làm mất tín hiệu delete/tombstone nếu downstream cần biết row đã bị xóa.

## 12. Transaction và thứ tự event

Một transaction database có thể thay đổi nhiều row hoặc nhiều bảng. Debezium có thể phát nhiều change event tương ứng. Consumer không nên giả định một transaction database luôn được đưa vào Kafka như một record duy nhất.

Một số connector/version có thể phát transaction metadata và boundary event khi được cấu hình. Metadata có thể cung cấp transaction ID, tổng số event hoặc thứ tự event trong transaction. Tuy nhiên:

- Event thường được phân phối theo topic/table, không nhất thiết nằm cùng một partition.
- Kafka chỉ bảo đảm thứ tự trong một partition.
- Consumer subscribe nhiều topic không tự nhận được một thứ tự toàn cục theo transaction.
- Nếu nghiệp vụ cần áp dụng transaction nhiều bảng như một đơn vị, cần thiết kế transaction metadata, buffering hoặc một domain event/outbox riêng.

Với ordering theo row/aggregate, giữ key ổn định và partitioning strategy nhất quán. Nếu cần ordering theo một aggregate lớn hơn row, hãy dùng aggregate ID làm key hoặc tạo domain event ở tầng ứng dụng.

## 13. Converter, schema và Single Message Transform

Connect converter quyết định cách Connect internal data model được serialize vào Kafka:

| Converter | Trường hợp dùng |
|---|---|
| JSON converter | Dễ quan sát và tích hợp hệ thống JSON; cần quyết định schema envelope |
| Avro converter | Schema Registry và contract có version |
| Protobuf converter | Contract typed, field number và schema evolution |
| String/ByteArray converter | Payload đặc thù hoặc xử lý bytes trực tiếp |

Debezium event envelope thường chứa before, after, source, op và metadata. Consumer có thể cần envelope đầy đủ để phân biệt snapshot/update/delete và truy vết nguồn.

Single Message Transform (SMT) có thể đổi topic, lọc field, thêm header hoặc unwrap envelope. Ví dụ unwrap giúp consumer nhận trực tiếp row state trong after, nhưng có thể làm mất op, before và một số metadata nếu không giữ lại header phù hợp.

Chỉ unwrap khi consumer không cần thông tin change type hoặc đã chuyển các metadata cần thiết sang header/field khác. Đối với delete, cần kiểm thử hành vi tombstone và null value sau transform.

## 14. Từ row-level CDC tới domain event và Outbox

Debezium phát hiện thay đổi database, nhưng row change không luôn tương đương domain event.

Ví dụ:

- CDC event: bảng orders có status đổi từ PENDING sang PAID.
- Domain event: PaymentCaptured với payment ID, số tiền, currency, phương thức và ý nghĩa nghiệp vụ đã được xác nhận.

Nếu downstream cần tích hợp theo nghiệp vụ, Transactional Outbox thường phù hợp:

1. Ứng dụng thực hiện business transaction.
2. Trong cùng transaction, ghi một outbox row chứa event đã được định nghĩa.
3. Debezium đọc outbox table qua transaction log.
4. Event Router SMT định tuyến outbox row thành topic/domain event phù hợp.
5. Consumer nhận event có event ID ổn định và xử lý idempotent.

Debezium EventRouter SMT hỗ trợ chuyển đổi record từ outbox table thành event theo cấu hình. Cần cấu hình đúng tên bảng, cột ID, aggregate key, event type, payload và routing topic. Không áp dụng EventRouter cho mọi bảng CDC; các bảng dữ liệu thông thường có thể vẫn dùng envelope mặc định.

Outbox giúp giữ ý định phát event cùng transaction database. Tuy vậy, connector có thể phát lại event sau restart hoặc khi offset chưa được lưu; downstream vẫn nên deduplicate theo event ID.

## 15. Độ tin cậy, duplicate và recovery

Khi connector đọc log và ghi event vào Kafka, lỗi có thể xảy ra ở nhiều điểm:

- Connector đọc log nhưng chưa ghi event vào Kafka.
- Kafka đã ghi event nhưng connector chưa lưu source offset.
- Worker dừng giữa lúc publish và lưu offset.
- Database log bị purge trước khi connector bắt kịp.
- Worker mất quyền truy cập database hoặc Kafka.

Vì vậy, không nên mặc định CDC luôn exactly-once end-to-end. Với cấu hình và chế độ phổ biến, consumer nên chịu được event giao lặp. Nếu event đã được publish nhưng source offset chưa được commit, connector có thể đọc lại cùng thay đổi sau restart.

Các biện pháp:

- Giữ primary key hoặc event ID ổn định.
- Consumer dùng upsert hoặc inbox/unique constraint để chống duplicate.
- Theo dõi source lag và log retention/WAL usage.
- Không xóa Connect offset topic hoặc Debezium schema history topic tùy tiện.
- Có snapshot/recovery plan khi log position không còn tồn tại.
- Kiểm thử restart worker và connector trước production.

### MySQL: binlog retention

Nếu connector ngừng quá lâu và MySQL đã purge binlog chứa vị trí cần đọc, connector không thể tiếp tục từ log cũ. Cần xác định có thể snapshot lại hay phải phục hồi từ backup/archive. Đặt binlog retention dựa trên outage tối đa, tốc độ phát sinh log và thời gian xử lý backlog.

### PostgreSQL: replication slot và WAL

Logical replication slot giữ WAL cần thiết cho consumer. Nếu Debezium không đọc được, WAL có thể tích tụ và làm tăng dung lượng đĩa. Giám sát slot lag, retained WAL và disk headroom. Không xóa slot để giải phóng disk mà chưa xác định tác động; xóa slot có thể làm mất khả năng tiếp tục từ LSN cũ và buộc snapshot lại.

## 16. Bảo mật và quyền truy cập

Debezium connector cần quyền ở cả database nguồn và Kafka:

| Hệ thống | Quyền cần xem xét |
|---|---|
| MySQL | Đọc metadata/snapshot, replication client và quyền cần thiết để đọc binlog |
| PostgreSQL | Replication/logical decoding, SELECT trên bảng được capture, quyền publication/slot theo cách quản trị |
| Kafka | Ghi data topics, đọc/ghi Connect internal topics, truy cập schema history topic nếu connector dùng |
| Kafka Connect REST | Authentication/authorization để tạo, sửa, pause, resume hoặc xóa connector |
| Secret manager | Đọc credential database và Kafka ở runtime |

Không dùng DBA/superuser cho connector nếu có thể tạo account CDC chuyên dụng. Tách principal Kafka Connect worker khỏi principal ứng dụng downstream; cấp ACL theo topic prefix và internal topic đúng phạm vi.

Connector config có thể chứa password hoặc secret. Cần dùng ConfigProvider/secret manager phù hợp, hạn chế quyền REST API và không log cấu hình đã giải mã. Ai có quyền tạo/sửa connector có thể thay đổi nơi connector đọc hoặc ghi dữ liệu, nên REST API của Connect là control plane nhạy cảm.

## 17. Theo dõi Debezium và Kafka Connect

Không chỉ theo dõi trạng thái RUNNING. Connector có thể chạy nhưng đã tụt xa so với database log.

Các tín hiệu nên giám sát:

| Tín hiệu | Ý nghĩa |
|---|---|
| Connector/task state | Connector và task đang RUNNING, PAUSED hay FAILED |
| Source lag | Khoảng cách giữa database log position và vị trí connector đã đọc |
| Snapshot progress | Snapshot đã hoàn tất bao nhiêu bảng/row hoặc còn kéo dài không |
| Queue remaining capacity | Queue nội bộ của connector có bị đầy không |
| Batch processing time | Connector có xử lý chậm hơn tốc độ log phát sinh không |
| Error/retry count | Lỗi database, Kafka, schema hoặc converter có tăng không |
| MySQL binlog age/retention | Log cần đọc còn tồn tại không |
| PostgreSQL replication slot lag/WAL retained | Slot có giữ WAL quá nhiều không |
| Kafka topic throughput/partition lag | Event có được publish và downstream tiêu thụ không |
| Connect worker rebalance/restart | Task có thường xuyên chuyển worker hoặc fail không |

Debezium connector thường phát JMX metrics; Kafka Connect cũng có REST API để xem connector/task status. Cần kết hợp metric của database, Connect worker, Kafka broker và consumer downstream để nhìn toàn pipeline.

## 18. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Connector task FAILED khi start | Sai database credential, privilege hoặc CDC chưa bật | Kiểm tra worker log và database config/permissions |
| Snapshot chạy rất lâu | Bảng lớn, lock/isolation, tải DB hoặc fetch chậm | Đánh giá snapshot mode, table scope, DB capacity và thời gian snapshot |
| Không thấy change event | Sai database/table include list hoặc topic prefix | Kiểm tra connector config và topic được tạo |
| Connector không tiếp tục sau downtime | Binlog/WAL position đã bị purge hoặc slot không còn hợp lệ | Đánh giá snapshot/recovery từ backup theo runbook |
| Kafka topic có event lặp | Connector restart trước khi source offset được lưu hoặc downstream replay | Deduplicate theo primary key/event ID và xử lý idempotent |
| PostgreSQL disk tăng liên tục | Replication slot giữ WAL vì connector không consume | Kiểm tra slot lag, connector health và disk headroom |
| Consumer không xóa row khi source delete | Consumer bỏ qua op=d hoặc tombstone | Kiểm tra envelope, SMT và delete handling |
| Schema history error | Topic bị xóa, sai ACL hoặc history không đầy đủ | Khôi phục metadata theo hướng dẫn connector; tránh tự tạo topic rỗng thay thế |
| Task liên tục restart | Lỗi transient, timeout, worker instability hoặc cấu hình không hợp lệ | Phân loại exception, kiểm tra Connect status/log và dependency |

Khi điều tra, luôn ghi lại connector name, task ID, database/table, source offset/LSN/binlog position, topic đích và timestamp. Không reset source offsets hoặc xóa replication slot chỉ để làm connector chuyển sang RUNNING; thao tác đó có thể gây mất thay đổi hoặc snapshot toàn bộ dữ liệu.

## 19. Bài thực hành: triển khai MySQL CDC vào Kafka

Tạo môi trường lab gồm MySQL, Kafka KRaft và Kafka Connect distributed có plugin Debezium MySQL:

1. Bật binlog với ROW format và FULL row image; đặt server ID duy nhất.
2. Tạo database inventory và bảng orders có primary key.
3. Tạo user Debezium với quyền tối thiểu cho snapshot và replication.
4. Khởi động Kafka Connect worker với config, offset và status internal topics riêng.
5. Đăng ký Debezium MySQL source connector với snapshot mode initial và table include list giới hạn.
6. Kiểm tra connector/task status và chờ snapshot hoàn tất.
7. Đọc topic fulfillment.inventory.orders, quan sát event snapshot có op=r.
8. Insert một order mới, update status và delete row; quan sát op=c/u/d và tombstone nếu được phát.
9. Dừng worker, tạo một số thay đổi ở MySQL, khởi động lại và xác minh connector tiếp tục từ source offset.
10. Thử dừng connector đủ lâu trong lab để quan sát source lag; không purge binlog khi chưa có recovery plan.
11. Dùng consumer idempotent để tạo projection theo primary key và xác minh replay không tạo row trùng.
12. Thử thay đổi schema theo hướng tương thích và kiểm tra consumer đọc được cả record cũ/mới.

Có thể mở rộng bài lab bằng PostgreSQL logical replication slot, so sánh cách theo dõi LSN và tác động WAL retention. Chỉ thực hiện fault injection trên môi trường lab.

## 20. Checklist trước khi đưa Debezium vào production

- Xác định CDC row-level hay Outbox domain event phù hợp với nhu cầu downstream.
- Chọn connector đúng database và kiểm tra phiên bản hỗ trợ.
- Bật transaction log/CDC đúng định dạng và cấu hình retention đủ dài.
- Tạo database principal chuyên dụng với quyền tối thiểu.
- Chọn snapshot mode và giới hạn schema/table cần capture.
- Cấp Kafka ACL cho data topics, Connect internal topics và schema history topic.
- Tạo Connect config/offset/status topics với replication và cleanup policy theo yêu cầu runtime.
- Với connector dùng schema history, bảo vệ topic và giữ đủ lịch sử cần thiết.
- Đặt topic prefix ổn định, key và partitioning phù hợp ordering.
- Quy định schema compatibility, delete/tombstone semantics và event envelope.
- Thiết kế consumer idempotent và xử lý snapshot/replay.
- Giám sát connector/task, source lag, log retention, WAL/binlog và Kafka throughput.
- Có runbook restart, snapshot lại, khôi phục offset và xử lý log position đã hết hạn.
- Bảo vệ Kafka Connect REST API và secret cấu hình connector.

## 21. Những nhầm lẫn thường gặp

- **Debezium là Kafka broker:** Debezium là nền tảng CDC; khi dùng Kafka, connector thường chạy trên Kafka Connect và ghi vào broker.
- **Debezium chỉ polling bảng:** nhiều connector đọc transaction log hoặc CDC mechanism của database.
- **Snapshot là change event mới phát sinh:** snapshot mô tả trạng thái đã tồn tại tại thời điểm khởi tạo, thường có op=r.
- **Source offset giống consumer group offset:** source offset do Kafka Connect lưu; consumer group offset do downstream consumer quản lý.
- **Schema history topic chứa row data:** schema history phục vụ diễn giải log/schema cho connector; data topic chứa change event.
- **Mỗi transaction database thành một Kafka record:** một transaction có thể tạo nhiều record, có thể nằm ở nhiều topic/partition.
- **CDC event luôn là domain event:** row change phản ánh dữ liệu; domain event cần ý nghĩa nghiệp vụ rõ ràng.
- **Delete event và tombstone giống nhau:** delete envelope mang op=d; tombstone có key và value null.
- **Connector RUNNING nghĩa là không lag:** task có thể chạy nhưng vẫn tụt xa log nguồn.
- **Restart luôn tiếp tục được:** log position có thể đã bị purge; PostgreSQL slot/WAL hoặc MySQL binlog retention cần được giám sát.
- **Debezium bảo đảm không duplicate end-to-end:** restart/recovery có thể phát lại; consumer cần idempotency.
- **Xóa Connect offset/schema history để reset nhanh:** có thể gây snapshot lại, mất tiến độ hoặc không diễn giải được log cũ.

Debezium đóng vai trò cầu nối giữa transaction log của database và event stream trong Kafka. Kafka Connect cung cấp runtime quản lý connector/task, cấu hình và source offsets; Debezium đọc snapshot cùng log thay đổi, chuẩn hóa chúng thành change event và ghi vào topic. Để pipeline vận hành bền vững, cần quản lý log retention, schema history, delete/tombstone, key/ordering, quyền truy cập và khả năng replay. Với tích hợp nghiệp vụ, hãy chọn row-level CDC hay Transactional Outbox theo ý nghĩa event mà downstream thực sự cần.
