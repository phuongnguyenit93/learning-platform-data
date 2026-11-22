# Source connector và sink connector

Kafka Connect là runtime tích hợp dữ liệu giữa Kafka và các hệ thống bên ngoài. **Source connector** đọc dữ liệu từ hệ thống nguồn rồi ghi record vào Kafka; **sink connector** đọc record từ Kafka rồi ghi sang hệ thống đích. Hai loại connector tạo thành hai chiều của một pipeline dữ liệu, nhưng có cơ chế quản lý offset, lỗi, khả năng mở rộng và delivery semantics khác nhau.

Kafka Connect chuẩn hóa cách triển khai integration bằng worker, connector, task, converter, Single Message Transform (SMT) và REST API. Nó không tự biến mọi database hoặc API thành hệ thống exactly-once; guarantee thực tế phụ thuộc connector plugin, hệ thống nguồn/đích và cấu hình triển khai.

## 1. Phân biệt source connector và sink connector

| Thành phần | Source connector | Sink connector |
|---|---|---|
| Hướng dữ liệu | External system → Kafka | Kafka → External system |
| Đầu vào | Database, file, object storage, API, CDC log hoặc hệ thống khác | Kafka topic |
| Đầu ra | Kafka topic | Database, data lake, search index, object storage hoặc hệ thống khác |
| Task thực hiện | Poll/read dữ liệu nguồn và tạo SourceRecord | Nhận SinkRecord và ghi batch tới đích |
| Offset chính | Source offset do Connect lưu để tiếp tục đọc nguồn | Kafka consumer offset của sink connector |
| Vấn đề cần chú ý | Snapshot, incremental polling, CDC, source offset và duplicate khi restart | Consumer lag, batch write, upsert, retry, DLQ và duplicate khi ghi đích |

Ví dụ:

- Source connector đọc bảng orders trong PostgreSQL và phát record vào topic db.shop.orders.
- Sink connector đọc topic orders rồi ghi dữ liệu sang PostgreSQL reporting database hoặc OpenSearch.
- Một pipeline có thể dùng source connector để thu thập CDC, xử lý bằng Kafka Streams rồi dùng sink connector ghi projection sang hệ thống phục vụ truy vấn.

~~~mermaid
flowchart LR
    DB[("Database / Source system")] --> SC["Source connector"]
    SC --> ST["Source tasks"]
    ST --> K[("Kafka topics")]
    K --> KC["Sink connector"]
    KC --> KT["Sink tasks"]
    KT --> DW[("Database / Data lake / Search")]
~~~

Không nhầm source connector với Kafka producer do ứng dụng tự viết: connector sử dụng Kafka Connect Source API và runtime quản lý task, serialization, source offsets và lifecycle. Tương tự, sink connector không phải một consumer Java thông thường; runtime quản lý consumer group, chuyển record cho SinkTask và phối hợp offset commit.

## 2. Kiến trúc runtime Kafka Connect

Kafka Connect runtime gồm các thành phần:

- **Worker:** tiến trình chạy Kafka Connect. Worker có thể chạy standalone hoặc distributed.
- **Connector:** plugin định nghĩa cách kết nối với một hệ thống và tạo task.
- **Task:** đơn vị thực thi song song. SourceTask đọc một phần nguồn; SinkTask ghi một phần dữ liệu đích.
- **Converter:** chuyển đổi key/value giữa định dạng nội bộ của Connect và byte representation trong Kafka.
- **SMT:** biến đổi từng record đơn giản trước khi ghi hoặc sau khi đọc, ví dụ đổi tên field hoặc lọc record.
- **REST API:** tạo, cấu hình, pause/resume, restart, xóa connector và xem trạng thái.
- **Internal topics:** lưu cấu hình connector, source offsets và trạng thái task trong distributed mode.

~~~mermaid
flowchart TD
    REST["Connect REST API"] --> W["Distributed Connect workers"]
    W --> C["Connector plugin"]
    C --> T1["Task 0"]
    C --> T2["Task 1"]
    T1 --> CONV["Converter / SMT"]
    T2 --> CONV
    CONV --> K[("Kafka data topics")]
    W <--> CFG[("connect-configs")]
    W <--> OFF[("connect-offsets")]
    W <--> STA[("connect-status")]
~~~

Trong distributed mode, các worker cùng group.id tạo thành một Connect cluster. Worker phối hợp phân phối connector task; khi một worker rời cluster, task có thể được phân công lại cho worker khác. REST request có thể gửi tới một worker bất kỳ trong cluster, vì vậy các endpoint cần truy cập được theo cách triển khai REST của cụm.

Standalone mode phù hợp cho thử nghiệm hoặc pipeline nhỏ: connector và offset thường được quản lý qua file cấu hình/local offset storage. Distributed mode phù hợp production vì có phối hợp worker, lưu trạng thái trong Kafka internal topics và hỗ trợ rebalance task.

### Internal topics trong distributed mode

Ba topic nội bộ quan trọng:

| Topic | Công dụng | Đặc điểm cần cấu hình |
|---|---|---|
| config.storage.topic | Lưu cấu hình connector và task | Phải có một partition; dùng compaction |
| offset.storage.topic | Lưu source offsets | Dùng compaction; số partition phù hợp quy mô cluster |
| status.storage.topic | Lưu trạng thái connector/task | Dùng compaction |

Ví dụ cấu hình worker rút gọn:

~~~properties
bootstrap.servers=broker-1:9092,broker-2:9092,broker-3:9092
group.id=connect-prod

config.storage.topic=connect-configs
offset.storage.topic=connect-offsets
status.storage.topic=connect-status

config.storage.replication.factor=3
offset.storage.replication.factor=3
status.storage.replication.factor=3

key.converter=org.apache.kafka.connect.json.JsonConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
plugin.path=/opt/kafka-connect/plugins
~~~

Các giá trị replication factor phải phù hợp số broker và chính sách cluster. Với production, nên dùng replication factor đủ cao, ACL riêng cho Connect và internal topics được bảo vệ. Không xóa hoặc tạo lại internal topics để reset connector nếu chưa hiểu hậu quả: mất source offsets có thể khiến source connector đọc lại dữ liệu, còn mất config/status topic có thể làm cluster không phục hồi được trạng thái mong muốn.

## 3. Source connector hoạt động như thế nào?

Source connector triển khai SourceConnector và tạo một hoặc nhiều SourceTask. Task đọc dữ liệu từ hệ thống nguồn rồi trả về SourceRecord chứa:

- Source partition: định danh phần dữ liệu nguồn mà task đang đọc, ví dụ database/table hoặc file partition.
- Source offset: vị trí tiếp tục đọc, ví dụ ID tăng dần, timestamp, binlog/LSN hoặc vị trí file.
- Topic đích và partition/key/value dự kiến.
- Schema và payload của key/value.

Connect runtime dùng source partition và source offset làm khóa tiến độ trong offset storage. Khi task restart hoặc được chuyển sang worker khác, connector có thể khôi phục vị trí đọc từ offset đã lưu nếu plugin hỗ trợ đúng semantics.

~~~mermaid
sequenceDiagram
    participant S as Source system
    participant T as SourceTask
    participant W as Connect worker
    participant K as Kafka
    participant O as Connect offset storage

    T->>S: Poll/read changes
    S-->>T: Rows / change records
    T->>W: SourceRecord + source offset
    W->>K: Serialize and produce
    K-->>W: Produce acknowledgement
    W->>O: Persist source progress
~~~

Đây là luồng khái quát; thứ tự và cơ chế ghi offset cụ thể phụ thuộc source connector, worker version và khả năng exactly-once source của connector. Khi kiểm tra một plugin, hãy đọc tài liệu của đúng phiên bản để biết offset được commit ở thời điểm nào và hành vi khi crash giữa produce với offset persistence.

### Polling source và CDC source

Có hai cách đọc thay đổi thường gặp:

**Polling** truy vấn nguồn theo chu kỳ. Ví dụ JDBC Source Connector có thể dùng cột tăng dần, timestamp hoặc kết hợp cả hai để tìm row mới/cập nhật.

- incrementing: dựa vào một cột ID tăng dần; phù hợp dữ liệu chỉ thêm mới theo ID.
- timestamp: dựa vào cột thời gian cập nhật; cần xử lý timestamp trùng, độ chính xác và bản ghi cập nhật muộn.
- timestamp+incrementing: dùng timestamp cùng cột tăng dần làm tie-breaker, thường phù hợp hơn khi nhiều row có cùng timestamp.

Polling phụ thuộc chất lượng cột theo dõi. Nó có thể không nhận biết delete nếu nguồn không phát dấu xóa; truy vấn có thể bỏ sót thay đổi nếu timestamp bị ghi sai hoặc không đủ độ chính xác. Cần thiết kế query, index và lịch polling phù hợp.

**Change Data Capture (CDC)** đọc transaction log hoặc change log của database, ví dụ PostgreSQL WAL hoặc MySQL binlog. CDC thường ghi nhận insert/update/delete ở mức thay đổi dữ liệu và có thể giữ thứ tự theo partition/log position. Connector CDC cần quyền replication, slot/binlog retention và cấu hình snapshot/recovery phù hợp.

JDBC polling không tương đương CDC. Nếu nghiệp vụ cần delete, transaction boundary hoặc lịch sử thay đổi đầy đủ, hãy chọn connector CDC tương thích với database thay vì giả định polling timestamp có thể cung cấp cùng guarantee.

### Ví dụ JDBC Source Connector

Ví dụ dưới đây dùng Confluent JDBC Source Connector để polling bảng orders. JDBC connector là plugin riêng; không giả định mọi bản phân phối Apache Kafka đều cài sẵn plugin này.

~~~json
{
  "name": "orders-jdbc-source",
  "config": {
    "connector.class": "io.confluent.connect.jdbc.JdbcSourceConnector",
    "tasks.max": "1",
    "connection.url": "jdbc:postgresql://db:5432/shop",
    "connection.user": "connect_reader",
    "connection.password": "<secret-from-secret-provider>",
    "mode": "timestamp+incrementing",
    "timestamp.column.name": "updated_at",
    "incrementing.column.name": "id",
    "table.whitelist": "orders",
    "topic.prefix": "db.shop.",
    "poll.interval.ms": "5000"
  }
}
~~~

Ví dụ dùng thuộc tính table.whitelist của Confluent JDBC Source Connector; một số plugin khác (đặc biệt connector CDC) dùng tên như table.include.list. Không thay tên thuộc tính giữa các plugin. Ví dụ giả định bảng orders có id tăng dần và updated_at được cập nhật đúng cho mọi thay đổi cần capture. Trước khi triển khai, kiểm tra tài liệu đúng phiên bản JDBC connector đang cài, kiểu timestamp, timezone, index, quyền SELECT và cách connector xử lý null/timestamp trùng.

Không ghi password thật vào file JSON hoặc source control. Dùng ConfigProvider/secret provider được worker hỗ trợ hoặc cơ chế secret management của nền tảng. Mỗi worker cần truy cập được plugin, JDBC driver và secret tương ứng.

## 4. Sink connector hoạt động như thế nào?

Sink connector tạo một hoặc nhiều SinkTask. Kafka Connect worker dùng consumer group để đọc các topic đã cấu hình, deserialize record thành SinkRecord, áp dụng SMT nếu có rồi chuyển batch cho SinkTask.

SinkTask thường triển khai các thao tác:

- start(): nhận cấu hình và khởi tạo kết nối tới hệ thống đích.
- put(Collection<SinkRecord>): ghi batch record vào đích.
- flush(...) hoặc preCommit(...): hỗ trợ phối hợp tiến độ và flush theo API/version connector.
- stop(): đóng kết nối và giải phóng tài nguyên.

Connect framework quản lý consumer offset và lifecycle task. Nếu sink ghi dữ liệu thành công nhưng worker chết trước khi Kafka offset được commit, batch có thể được giao lại. Vì vậy, sink connector cần chiến lược idempotency/upsert hoặc cơ chế transaction phù hợp để tránh duplicate.

~~~mermaid
sequenceDiagram
    participant K as Kafka topic
    participant W as Connect worker
    participant T as SinkTask
    participant D as Destination

    W->>K: Consume records
    K-->>W: SinkRecord batch
    W->>T: put(batch)
    T->>D: Write/upsert batch
    D-->>T: Write result
    T-->>W: Batch handled
    W->>K: Commit consumer offsets
~~~

Đây là luồng đơn giản hóa. Connector có thể dùng flush/preCommit và offset handling riêng theo Connect API version. Hãy kiểm tra connector có xác nhận batch chỉ sau khi đích đã durable hay không.

### Ví dụ JDBC Sink Connector

Ví dụ dùng Confluent JDBC Sink Connector để upsert record vào bảng orders. Giả định key Kafka là structured key có field order_id, value có các field tương ứng với cột đích và database có primary key phù hợp.

~~~json
{
  "name": "orders-jdbc-sink",
  "config": {
    "connector.class": "io.confluent.connect.jdbc.JdbcSinkConnector",
    "tasks.max": "3",
    "connection.url": "jdbc:postgresql://reporting-db:5432/warehouse",
    "connection.user": "connect_writer",
    "connection.password": "<secret-from-secret-provider>",
    "topics": "orders",
    "insert.mode": "upsert",
    "pk.mode": "record_key",
    "pk.fields": "order_id",
    "auto.create": "false",
    "auto.evolve": "false"
  }
}
~~~

insert.mode=upsert có thể làm thao tác ghi lặp trở nên idempotent theo primary key nếu connector/dialect và schema được hỗ trợ. Nó không tự bảo đảm các side effect khác như trigger gửi email hoặc append audit log không bị lặp. Với JDBC Sink Connector, kiểm tra hỗ trợ upsert của dialect và kiểu key/value theo phiên bản plugin. Key phải có schema/field order_id phù hợp với pk.fields; ví dụ dùng JSON không schema ở phần converter trước đó không đủ để suy ra key đã có Connect schema cho JDBC sink. Hãy cấu hình converter có schema hoặc chọn key format mà plugin hỗ trợ.

Nếu bật delete.enabled=true, JDBC Sink Connector yêu cầu cấu hình key mode phù hợp (thông thường pk.mode=record_key) và tombstone record để biểu diễn xóa. Hãy kiểm thử mapping tombstone, primary key và transaction của database đích trước khi bật.

## 5. Converter và Single Message Transform

Converter quyết định byte trong Kafka được chuyển thành Connect data như thế nào. Key và value có thể dùng converter riêng.

| Converter | Mục đích |
|---|---|
| StringConverter | Chuyển chuỗi trực tiếp thành byte/string |
| ByteArrayConverter | Giữ payload dạng byte array |
| JsonConverter | Serialize/deserialize JSON; có thể bật/tắt Connect schema envelope |
| Avro converter | Serialize/deserialize Avro thông qua Schema Registry |
| Protobuf converter | Serialize/deserialize Protobuf qua Schema Registry |

Ví dụ cấu hình JSON converter:

~~~properties
key.converter=org.apache.kafka.connect.json.JsonConverter
key.converter.schemas.enable=false
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=false
~~~

Khi schemas.enable=false, payload JSON không mang Connect schema envelope. Nếu dùng schema registry hoặc cần schema evolution có kiểm soát, cấu hình converter tương ứng và thống nhất format giữa producer/consumer/connector.

SMT biến đổi từng record đơn giản, ví dụ:

- Đổi tên field bằng ReplaceField.
- Thêm hoặc sửa header bằng InsertHeader.
- Đổi topic bằng RegexRouter.
- Lọc hoặc định tuyến record theo điều kiện với SMT/plugin phù hợp.

SMT không thay thế Kafka Streams hoặc một pipeline ETL phức tạp. Khi cần join, aggregation, stateful processing, enrichment nhiều nguồn hoặc logic domain dài, hãy dùng Kafka Streams/Flink/application processor.

Converter xử lý serialization boundary; SMT xử lý record sau khi đã được converter tạo thành Connect data. Nhầm hai lớp này có thể dẫn đến lỗi deserialize trước khi SMT có cơ hội chạy.

## 6. Cài đặt và quản lý connector plugin

Connector plugin thường không nằm sẵn trong Apache Kafka distribution. Cần cài plugin và dependency/driver trên mọi worker có thể nhận task:

1. Chọn plugin và version tương thích với Kafka Connect runtime.
2. Tải package từ nguồn tin cậy, kiểm tra checksum/signature nếu nhà cung cấp cung cấp.
3. Cài plugin vào thư mục riêng, không ghi đè thư viện Kafka runtime tùy tiện.
4. Thêm thư mục vào plugin.path.
5. Triển khai cùng plugin version lên tất cả worker.
6. Restart worker theo rolling procedure nếu runtime yêu cầu.
7. Dùng endpoint plugin listing để xác nhận connector class đã được nhận diện.

Ví dụ:

~~~properties
plugin.path=/opt/kafka-connect/plugins,/opt/company/connectors
~~~

Nếu chỉ một worker có plugin, connector có thể chạy trên worker đó nhưng lỗi khi task được rebalance sang worker khác. Đảm bảo plugin version, JDBC driver và dependency giống nhau trên toàn cluster. Tránh đặt nhiều version class trùng nhau trong plugin path vì classloading có thể khó dự đoán.

## 7. Tạo và quản lý connector qua REST API

Distributed Connect cung cấp REST API để tạo connector. Ví dụ tạo JDBC source:

~~~http
PUT /connectors/orders-jdbc-source/config
Content-Type: application/json

{
  "connector.class": "io.confluent.connect.jdbc.JdbcSourceConnector",
  "tasks.max": "1",
  "connection.url": "jdbc:postgresql://db:5432/shop",
  "connection.user": "connect_reader",
  "connection.password": "<secret-reference>",
  "mode": "timestamp+incrementing",
  "timestamp.column.name": "updated_at",
  "incrementing.column.name": "id",
  "table.whitelist": "orders",
  "topic.prefix": "db.shop.",
  "poll.interval.ms": "5000"
}
~~~

REST endpoint thực tế có thể được bảo vệ bằng TLS, authentication, authorization hoặc reverse proxy. Không mở Connect REST API công khai nếu không có lớp kiểm soát truy cập phù hợp.

Một số endpoint quản trị thường dùng:

~~~text
GET    /connectors
GET    /connectors/{name}
GET    /connectors/{name}/config
GET    /connectors/{name}/status
PUT    /connectors/{name}/config
PUT    /connectors/{name}/pause
PUT    /connectors/{name}/resume
POST   /connectors/{name}/restart
DELETE /connectors/{name}
GET    /connector-plugins
~~~

PUT /connectors/{name}/config tạo connector nếu chưa có hoặc cập nhật cấu hình nếu đã tồn tại. GET .../status trả trạng thái connector và từng task, thường gồm state, worker ID và trace lỗi khi task thất bại. Endpoint restart có thể có query option theo phiên bản Connect; kiểm tra REST API version đang dùng.

Sau khi thay đổi config, không chỉ nhìn HTTP response. Hãy kiểm tra status connector/task, worker log, record thực tế trong topic hoặc hệ thống đích và metric lag/throughput.

## 8. Phân phối task và mở rộng throughput

tasks.max là giới hạn số task tối đa mà connector được phép tạo, không phải cam kết connector sẽ luôn chạy đúng số task đó. Số task thực tế phụ thuộc cách plugin chia nguồn, số partition/topic, bảng hoặc shard và khả năng song song của hệ thống đích.

Ví dụ:

- Source connector đọc một bảng đơn giản có thể chỉ tạo một task dù tasks.max=8.
- Source connector hỗ trợ chia nhiều table hoặc partition có thể tạo nhiều task.
- Sink connector thường bị giới hạn song song hữu ích bởi số Kafka partition mà nó đọc.
- Tăng task có thể tăng kết nối đồng thời, query load, lock hoặc áp lực lên database đích.

Khi scale, kiểm tra:

- Số partition của topic và số task thực tế.
- Throughput/latency của hệ thống nguồn và đích.
- Batch size, poll interval, queue và memory.
- Số connection pool/transaction đồng thời.
- Key partitioning và ordering cần giữ.
- Rebalance và thời gian khởi động lại task.

Không tăng tasks.max chỉ để tăng tốc nếu connector không thể chia công việc hoặc hệ thống đích đã là bottleneck.

## 9. Delivery semantics và duplicate

Source và sink connector có hai ranh giới tiến độ riêng.

### Source connector

Source connector lưu source offsets trong Connect offset storage. Khi source task đọc dữ liệu rồi produce Kafka record, sự cố có thể xảy ra giữa produce và việc lưu source offset. Khi restart, connector có thể đọc lại vùng nguồn đó và produce duplicate.

Exactly-once source support có trong Kafka Connect ở các phiên bản hỗ trợ KIP-618. Với runtime phù hợp, worker distributed cần bật exactly.once.source.support=enabled và connector phải khai báo/triển khai khả năng hỗ trợ. Không phải source plugin nào cũng hỗ trợ; hãy xác nhận phiên bản runtime, connector và mode triển khai. Nếu không có guarantee đó, thiết kế consumer idempotent theo source key/event ID.

### Sink connector

Sink connector đọc Kafka record và ghi external system. Nếu external write thành công nhưng offset chưa commit, record có thể được giao lại. Mặc định nên giả định at-least-once trừ khi connector và destination có cơ chế exactly-once được tài liệu hóa, cấu hình và kiểm thử.

Các cách giảm tác động duplicate:

- Upsert theo primary key thay vì insert row mới mỗi lần.
- Dùng event ID với unique constraint/inbox table.
- Ghi batch trong transaction của database đích nếu connector hỗ trợ.
- Dùng destination API có idempotency key.
- Đối soát sau restart/rebalance và giữ log event ID.

Không đồng nhất producer idempotence với exactly-once end-to-end của connector. Idempotent producer bảo vệ retry protocol khi ghi Kafka; nó không tự chống duplicate khi sink ghi database hoặc HTTP API.

## 10. Retry, lỗi và Dead Letter Queue

Kafka Connect có cơ chế xử lý lỗi cho converter/SMT và một số lỗi record trong worker. Các cấu hình thường gặp gồm:

~~~properties
errors.tolerance=all
errors.retry.timeout=60000
errors.retry.delay.max.ms=10000
errors.deadletterqueue.topic.name=connect-errors
errors.deadletterqueue.context.headers.enable=true
errors.log.enable=true
errors.log.include.messages=false
~~~

Phạm vi cấu hình có thể đặt ở worker hoặc connector tùy thuộc property và version. errors.tolerance=all cho phép worker tiếp tục trong các trường hợp lỗi record mà framework có thể bỏ qua/đưa vào DLQ; nó không có nghĩa mọi lỗi hệ thống đích đều được bỏ qua an toàn. Lỗi kết nối database, authentication hoặc task lifecycle vẫn có thể làm task thất bại.

Khi dùng DLQ:

- Chọn topic DLQ có replication, retention và ACL phù hợp.
- Giữ metadata nguồn như topic, partition, offset và connector/task context.
- Không đưa payload nhạy cảm vào log hoặc header nếu không có kiểm soát.
- Theo dõi DLQ rate và có quy trình sửa dữ liệu/replay.
- Không commit hoặc bỏ qua record lỗi nếu nghiệp vụ yêu cầu phải xử lý; errors.tolerance=all cần được chọn có chủ đích.

Với lỗi transient của hệ thống đích, cần xem retry/backoff mà connector hỗ trợ. Retry lâu có thể làm sink consumer lag tăng. Nếu task dừng rồi restart, record chưa commit có thể được giao lại; sink vẫn phải idempotent.

## 11. Security và quyền truy cập

Connect worker có nhiều danh tính và kết nối:

- Worker cần quyền đọc/ghi internal topics và tham gia Connect worker group.
- Source connector cần quyền truy cập hệ thống nguồn và quyền produce vào topic đích.
- Sink connector cần quyền consume topic nguồn và ghi vào hệ thống đích.
- REST API cần authentication/authorization; chỉ operator được phép thay đổi connector config.
- Secret database/API phải được quản lý qua secret provider, không lưu plain text trong Git hoặc log.

Phân quyền Kafka theo nguyên tắc least privilege: source chỉ được ghi các topic cần thiết; sink chỉ được đọc topic và group cần thiết; worker internal access tách khỏi quyền của ứng dụng khác. Nếu connector dùng SASL/TLS, cấu hình truststore/keystore và secret trên tất cả worker có thể nhận task.

## 12. Monitoring và troubleshooting

Theo dõi cả trạng thái Connect và dữ liệu thực tế:

| Chỉ số | Ý nghĩa |
|---|---|
| Connector/task state | Connector hoặc task đang RUNNING, PAUSED hay FAILED |
| Source record poll/write rate | Tốc độ đọc nguồn và produce vào Kafka |
| Sink record read/write rate | Tốc độ tiêu thụ Kafka và ghi đích |
| Sink consumer lag | Khoảng cách giữa Kafka end offset và tiến độ sink |
| Source offset age/lag | Dữ liệu nguồn chậm được capture bao lâu, nếu connector cung cấp metric |
| Batch size và request latency | Kích thước batch, thời gian ghi tới hệ thống đích |
| Retry/DLQ rate | Lỗi transient và record không xử lý được |
| Worker rebalance/task restart | Task có thường xuyên chuyển worker hoặc crash không |
| External connection errors | Database/API có timeout, hết connection hoặc từ chối quyền không |

Các tình huống thường gặp:

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| Connector không tạo được | Plugin chưa cài, class sai, config validation lỗi |
| Task FAILED | Credential, schema, network, query hoặc destination write lỗi |
| Source không phát record mới | Source offset, polling mode, timestamp column, CDC slot/binlog hoặc quyền đọc |
| Sink lag tăng | Destination chậm, batch nhỏ, ít task/partition, retry hoặc connection pool thiếu |
| Duplicate record/row | Crash giữa write và offset commit, source offset chưa lưu, retry hoặc thiếu idempotency |
| Chỉ một worker chạy được task | Plugin/driver/secret không đồng nhất giữa workers |
| DLQ tăng | Schema mismatch, SMT lỗi, dữ liệu sai hoặc lỗi record ở sink |

Khi điều tra, lưu connector name, task ID, worker ID, topic/partition/offset, source offset và event ID. Kiểm tra trạng thái trước khi restart; restart không tự sửa cấu hình sai và có thể làm record được giao lại.

## 13. Quy trình triển khai connector an toàn

1. Xác định hướng dữ liệu, hệ thống sở hữu dữ liệu chuẩn và mục tiêu latency.
2. Chọn source/sink plugin đúng loại, kiểm tra version, license, driver và compatibility.
3. Thiết kế key, topic naming, partitioning, schema, converter và retention.
4. Cấu hình worker distributed, internal topics, security và plugin path.
5. Cấu hình connector bằng secret reference; validate config trước khi chạy nếu API/plugin hỗ trợ.
6. Tạo connector và kiểm tra status của connector lẫn từng task.
7. Kiểm tra record thực tế: key/value/schema/header, partition, timestamp và offset.
8. Kiểm tra hệ thống đích nhận đúng dữ liệu, upsert/delete và ordering.
9. Thử restart worker/task, mất kết nối nguồn/đích và lỗi giữa write với offset persistence.
10. Bật monitoring, alert, DLQ và runbook replay/reconciliation.

Không thử connector mới trực tiếp trên topic production hoặc database production mà không có phạm vi dữ liệu và quyền ghi được kiểm soát. Với sink có thể thay đổi/xóa dữ liệu đích, chạy thử trên schema/table riêng trước.

## 14. Những hiểu nhầm thường gặp

- **“Source connector và sink connector chỉ khác tên.”** Source đọc hệ thống ngoài rồi produce Kafka; sink consume Kafka rồi ghi hệ thống ngoài.
- **“tasks.max là số task chắc chắn chạy.”** Đây chỉ là giới hạn; plugin quyết định số task thực tế.
- **“Tăng task luôn tăng throughput.”** Source/destination hoặc số partition có thể giới hạn khả năng song song.
- **“JDBC polling tương đương CDC.”** Polling theo cột không tự cung cấp đầy đủ delete và transaction-log semantics.
- **“Connect lưu mọi offset trong consumer group.”** Source offset nằm trong Connect offset storage; sink dùng Kafka consumer group offset.
- **“REST API trả 201/200 nghĩa là dữ liệu đã được đồng bộ.”** Cần kiểm tra task state và record/row thực tế.
- **“errors.tolerance=all sẽ chữa mọi lỗi.”** Nó không xử lý mọi lỗi hệ thống hoặc lỗi lifecycle task.
- **“DLQ là nơi có thể bỏ record mãi mãi.”** DLQ cần owner, alert, sửa lỗi và replay.
- **“Kafka Connect mặc định exactly-once với mọi connector.”** Guarantee phụ thuộc source/sink plugin, runtime version và hệ thống đích.
- **“Cài plugin trên một worker là đủ.”** Task có thể được rebalance sang worker khác; plugin và dependency phải đồng nhất.

## 15. Checklist production

- [ ] Phân biệt rõ source và sink; xác định owner của dữ liệu nguồn/đích.
- [ ] Chọn plugin và version tương thích; cài đồng nhất trên mọi worker.
- [ ] Distributed worker có group.id và internal topics với compaction/replication phù hợp.
- [ ] Internal topics được bảo vệ và không bị xóa/reset tùy tiện.
- [ ] Converter key/value khớp producer, schema format và consumer.
- [ ] SMT chỉ xử lý biến đổi đơn giản; logic phức tạp chuyển sang stream processor.
- [ ] Source offset, snapshot/polling/CDC semantics và delete behavior đã được kiểm tra.
- [ ] Sink có upsert/idempotency hoặc transaction phù hợp để chịu được replay.
- [ ] tasks.max được chọn theo khả năng chia task, partition và capacity của nguồn/đích.
- [ ] Secret không nằm plain text trong source control hoặc log.
- [ ] ACL tách riêng cho worker, source connector, sink connector và REST operator.
- [ ] Retry, DLQ, retention và replay procedure có owner rõ ràng.
- [ ] Có metric connector/task state, throughput, lag, error, retry và DLQ.
- [ ] Đã thử restart worker, rebalance task, source outage, sink outage và duplicate.

Source connector đưa dữ liệu từ hệ thống ngoài vào Kafka và lưu tiến độ đọc nguồn trong Connect; sink connector tiêu thụ Kafka rồi ghi dữ liệu ra hệ thống đích và quản lý tiến độ consumer. Khi hiểu đúng hai hướng này, kết hợp worker/task, converter, SMT, offset, retry và idempotency, Kafka Connect trở thành nền tảng tích hợp có thể mở rộng và vận hành được. Hãy luôn xác minh guarantee theo plugin và destination cụ thể, vì runtime không thể tự tạo exactly-once cho một hệ thống ngoài không hỗ trợ cơ chế tương ứng.
