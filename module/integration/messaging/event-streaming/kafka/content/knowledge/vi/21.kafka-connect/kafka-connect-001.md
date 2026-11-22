# Connect giải quyết bài toán tích hợp nguồn và đích dữ liệu

Trong một hệ thống event streaming, dữ liệu thường nằm ở nhiều nơi: database giao dịch, object storage, hệ thống tìm kiếm, data warehouse, ứng dụng nghiệp vụ và các nền tảng phân tích. Nếu mỗi ứng dụng tự viết producer để đọc nguồn và consumer để ghi đích, đội phát triển phải lặp lại nhiều công việc như kết nối, retry, quản lý offset, chuyển đổi định dạng, mở rộng tải và giám sát.

**Apache Kafka Connect** là framework tích hợp dữ liệu giữa Kafka và các hệ thống bên ngoài. Connect cung cấp runtime chung để chạy các plugin gọi là connector. Source connector đưa dữ liệu từ hệ thống ngoài vào Kafka; sink connector lấy dữ liệu từ Kafka và ghi sang hệ thống đích. Người vận hành cấu hình connector qua REST API, còn Connect quản lý worker, task, offset và trạng thái chạy.

Kafka Connect phù hợp với các luồng ingest/export dữ liệu có cấu trúc lặp lại. Nó giúp giảm lượng mã tích hợp phải tự duy trì, nhưng không tự thay thế logic nghiệp vụ phức tạp hoặc bảo đảm exactly-once cho mọi hệ thống đích.

## 1. Bài toán tích hợp nguồn và đích dữ liệu

Giả sử một doanh nghiệp có:

- PostgreSQL lưu đơn hàng và thanh toán.
- Kafka làm nền tảng event streaming trung tâm.
- Elasticsearch phục vụ tìm kiếm.
- Object storage lưu dữ liệu lịch sử.
- Data warehouse phục vụ báo cáo.

Nếu mỗi hệ thống tự xây dựng một tiến trình đồng bộ, đội vận hành phải duy trì nhiều kết nối và cơ chế retry riêng. Khi thêm một nguồn dữ liệu mới, có thể phải viết lại phần đọc, serialize, checkpoint và xử lý lỗi.

Kafka Connect chuẩn hóa cách tích hợp:

~~~mermaid
flowchart LR
    DB["Database"] --> SC["Source Connector"]
    FILE["File / Object Storage"] --> SC2["Source Connector"]
    SC --> K["Kafka Topics"]
    SC2 --> K
    K --> S1["Sink Connector"]
    K --> S2["Sink Connector"]
    S1 --> SEARCH["Search Engine"]
    S2 --> DW["Data Warehouse"]
~~~

Source connector gom dữ liệu từ một hoặc nhiều nguồn và ghi thành record trong Kafka. Sink connector đọc record từ topic và chuyển đến hệ thống đích. Kafka nằm giữa giúp tách thời điểm phát sinh dữ liệu khỏi thời điểm hệ thống đích tiếp nhận.

Ví dụ, database có thể tiếp tục ghi đơn hàng trong khi search engine tạm thời bảo trì. Kafka giữ record theo retention policy; sink connector tiếp tục tiêu thụ khi search engine hoạt động trở lại, miễn là dữ liệu chưa hết retention và connector có thể khôi phục tiến độ.

## 2. Kafka Connect giải quyết những phần việc nào?

Kafka Connect cung cấp một runtime chung cho các công việc tích hợp thường gặp:

| Nhu cầu | Connect hỗ trợ |
|---|---|
| Kết nối hệ thống ngoài | Connector plugin triển khai giao thức riêng của database, file system, search engine hoặc dịch vụ cloud |
| Đưa dữ liệu vào/ra Kafka | SourceRecord và SinkRecord cùng API chuẩn |
| Chia nhỏ công việc | Connector tạo các task có thể chạy song song |
| Theo dõi tiến độ | Lưu source offset và quản lý tiến độ sink consumer |
| Chuyển đổi dữ liệu | Converter chuyển đổi giữa Connect data model và byte format của Kafka |
| Biến đổi từng record | Single Message Transform (SMT) |
| Quản lý vòng đời | REST API tạo, cập nhật, pause, resume, restart và xem trạng thái connector |
| Mở rộng runtime | Distributed workers phân phối task và khôi phục khi worker rời cụm |
| Quan sát lỗi | Status, log, metrics và tùy chọn xử lý lỗi/DLQ |

Connect không tự biết ý nghĩa nghiệp vụ của một record. Connector có thể đọc cột database, object hoặc message theo cấu hình, nhưng việc quyết định một đơn hàng có hợp lệ về mặt kinh doanh hay không vẫn thuộc ứng dụng hoặc hệ thống xử lý chuyên biệt.

## 3. Các khái niệm cốt lõi: worker, connector và task

Kafka Connect có ba thành phần thường gặp:

| Thành phần | Vai trò |
|---|---|
| Worker | Tiến trình/runtime chạy Kafka Connect, giữ kết nối Kafka và thực thi connector/task |
| Connector | Plugin mô tả cách kết nối tới một hệ thống ngoài và xác định công việc cần thực hiện |
| Task | Đơn vị công việc thực tế do connector tạo ra; có thể được phân phối trên nhiều worker |

Connector chịu trách nhiệm xác định cấu hình và số task phù hợp. Task thực hiện đọc dữ liệu nguồn hoặc ghi dữ liệu đích. Worker cung cấp môi trường chạy task, quản lý cấu hình, offset, REST API và giao tiếp với Kafka.

~~~mermaid
flowchart TD
    W["Kafka Connect Worker"] --> C1["Connector instance"]
    C1 --> T1["Task 0"]
    C1 --> T2["Task 1"]
    C1 --> T3["Task 2"]
    T1 --> K["Kafka"]
    T2 --> K
    T3 --> K
~~~

Một connector có thể tạo một hoặc nhiều task. Số task thực tế phụ thuộc khả năng chia nhỏ của plugin, dữ liệu nguồn, cấu hình và số lượng partition/topic. tasks.max là giới hạn tối đa mà người vận hành yêu cầu, không bảo đảm connector luôn tạo đúng số task đó.

Ví dụ, một source connector đọc nhiều bảng database có thể chia từng bảng hoặc nhóm bảng cho các task. Một sink connector có thể phân phối việc ghi các partition Kafka cho nhiều task. Cách chia cụ thể do connector plugin quyết định.

## 4. Source connector và sink connector

### Source connector: đưa dữ liệu vào Kafka

Source connector đọc từ hệ thống bên ngoài và tạo các SourceRecord. Một record thường mang:

- Source partition: định danh phần dữ liệu nguồn mà record thuộc về, ví dụ database/table hoặc file.
- Source offset: vị trí đã đọc trong nguồn, ví dụ log sequence number, binlog position hoặc offset của file.
- Kafka topic đích.
- Key, value, schema và timestamp (tùy connector).
- Headers nếu connector cung cấp.

Connect ghi record vào Kafka và lưu source offset để connector có thể tiếp tục từ vị trí phù hợp sau restart. Cách tạo offset và mức bảo đảm không mất/trùng phụ thuộc connector cụ thể và khả năng checkpoint của hệ thống nguồn.

Các ví dụ source:

- CDC connector đọc change log của database.
- File source đọc dòng mới từ file.
- Connector đọc dữ liệu từ object storage hoặc dịch vụ cloud.
- Connector ingest dữ liệu từ hệ thống tìm kiếm hoặc message broker khác.

### Sink connector: đưa dữ liệu từ Kafka ra ngoài

Sink connector nhận SinkRecord từ Kafka consumer và ghi vào hệ thống đích. Nó thường cấu hình:

- Danh sách topic hoặc regex topic cần đọc.
- Hệ thống đích và thông tin xác thực.
- Cách ánh xạ topic/partition/key sang đối tượng đích.
- Chế độ insert, update, upsert hoặc ghi theo batch.
- Chính sách retry và xử lý lỗi.

Các ví dụ sink:

- Ghi topic đơn hàng vào Elasticsearch.
- Đẩy event vào object storage theo định dạng Parquet/Avro/JSON.
- Ghi dữ liệu Kafka vào data warehouse.
- Đồng bộ dữ liệu sang database hoặc dịch vụ bên ngoài.

~~~mermaid
flowchart LR
    subgraph Source["Source path"]
        EXT1["External System"] --> ST["Source Task"]
        ST --> TOPIC["Kafka Topic"]
    end
    subgraph Sink["Sink path"]
        TOPIC --> KT["Sink Task"]
        KT --> EXT2["External System"]
    end
~~~

Source offset và sink consumer offset là hai loại tiến độ khác nhau. Source offset chỉ vị trí connector đã đọc trong hệ thống nguồn. Sink offset là tiến độ consumer group đã đọc trong Kafka. Không nhầm source offset với Kafka record offset.

## 5. Standalone mode và distributed mode

Kafka Connect có hai chế độ triển khai chính.

| Tiêu chí | Standalone | Distributed |
|---|---|---|
| Runtime | Một worker process | Nhiều worker process cùng một Connect cluster |
| Phân phối task | Trong một tiến trình | Framework phân phối task giữa các worker |
| Lưu cấu hình/offset | Cấu hình local; source offset thường lưu vào file được chỉ định | Lưu trong các internal Kafka topics |
| Khả năng chịu lỗi | Tiến trình dừng thì connector dừng | Worker còn lại có thể nhận task sau khi worker lỗi/rời cụm |
| Mở rộng | Hạn chế | Thêm worker để tăng tài nguyên chạy task |
| Phù hợp | Học tập, thử nghiệm, luồng nhỏ | Staging và production cần mở rộng/khả năng phục hồi |

Standalone mode thường dùng để học connector hoặc kiểm tra plugin trên một máy. Ví dụ:

~~~bash
bin/connect-standalone.sh config/connect-standalone.properties config/source.properties
~~~

Trên Windows, dùng script .bat tương ứng trong bin/windows.

Distributed mode chạy nhiều worker với cùng cấu hình cluster và cùng các internal topic. Worker tham gia cùng group; Connect điều phối cấu hình connector và phân công task.

~~~bash
bin/connect-distributed.sh config/connect-distributed.properties
~~~

Khi một worker rời cụm, các task có thể được phân phối lại cho worker còn lại. Việc phân phối lại có thể tạo gián đoạn ngắn; connector và hệ thống đích cần xử lý được retry hoặc record replay.

## 6. Internal topics trong distributed mode

Distributed mode cần các Kafka topic nội bộ để lưu trạng thái của Connect:

| Topic cấu hình | Nội dung |
|---|---|
| config.storage.topic | Cấu hình connector và task được lưu theo cơ chế compacted |
| offset.storage.topic | Source offsets do connector ghi lại |
| status.storage.topic | Trạng thái connector và task |

Ví dụ cấu hình worker:

~~~properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
group.id=connect-prod

config.storage.topic=connect-configs
offset.storage.topic=connect-offsets
status.storage.topic=connect-status

config.storage.replication.factor=3
offset.storage.replication.factor=3
status.storage.replication.factor=3

key.converter=org.apache.kafka.connect.json.JsonConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
~~~

Các internal topic cần được tạo và cấu hình đúng theo hướng dẫn của phiên bản Kafka Connect đang chạy. config.storage.topic phải có đúng một partition vì Connect dùng topic này để lưu và đồng bộ cấu hình cluster. Các topic offset và status thường dùng log compaction để giữ trạng thái mới nhất theo key.

Replication factor phải phù hợp với số broker và yêu cầu độ bền. Ví dụ replication factor bằng 3 yêu cầu cluster có đủ broker phù hợp để tạo replica. Trong production, không nên dùng replication factor 1 cho internal topic nếu cần chịu lỗi broker.

group.id định danh nhóm worker của một Connect cluster. Các worker phải dùng cùng group.id và cùng tên internal topic để phối hợp. Không dùng chung các internal topic giữa hai Connect cluster độc lập.

## 7. Converter và định dạng dữ liệu

Kafka lưu record dưới dạng byte key/value. Kafka Connect có data model riêng để biểu diễn giá trị có schema hoặc không có schema. Converter chuyển đổi giữa Connect data model và byte format được ghi vào Kafka hoặc đọc từ Kafka.

Một số converter thường gặp:

| Converter | Trường hợp sử dụng |
|---|---|
| JsonConverter | JSON; có thể bật/tắt phần schema trong payload |
| AvroConverter | Avro, thường kết hợp Schema Registry |
| ProtobufConverter | Protocol Buffers, thường kết hợp Schema Registry |
| JsonSchemaConverter | JSON Schema, thường kết hợp Schema Registry |
| StringConverter | Giá trị chuỗi đơn giản |
| ByteArrayConverter | Payload byte không diễn giải cấu trúc |

Worker có thể đặt converter mặc định cho key/value; connector có thể ghi đè bằng cấu hình riêng nếu plugin/framework cho phép. Source và sink phải thống nhất cách diễn giải format. Ví dụ, nếu source ghi JSON có schema nhưng sink đọc JSON không có schema, dữ liệu có thể không được chuyển đổi như mong muốn.

Ví dụ JSON converter:

~~~properties
key.converter=org.apache.kafka.connect.json.JsonConverter
key.converter.schemas.enable=false

value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=true
~~~

Với Avro/Protobuf/JSON Schema, cần cấu hình converter plugin và địa chỉ Schema Registry tương ứng. Converter và Schema Registry client phải có mặt trên tất cả worker có thể chạy connector.

## 8. Single Message Transform (SMT)

SMT là các phép biến đổi nhẹ trên từng record trong pipeline Connect. Có thể dùng để:

- Đổi tên topic.
- Thêm, xóa hoặc đổi tên field.
- Chèn metadata vào header hoặc payload.
- Lọc record theo điều kiện hỗ trợ.
- Đổi kiểu hoặc định dạng timestamp trong phạm vi transform có sẵn.

Ví dụ cấu hình đổi tên topic:

~~~properties
transforms=renameTopic
transforms.renameTopic.type=org.apache.kafka.connect.transforms.RegexRouter
transforms.renameTopic.regex=raw-(.*)
transforms.renameTopic.replacement=clean-$1
~~~

SMT được cấu hình theo chuỗi và chạy theo thứ tự khai báo. Với sink connector, transform áp dụng trên record sau khi đọc từ Kafka và trước khi connector ghi đến đích; với source connector, transform áp dụng trước khi record được ghi vào Kafka.

SMT phù hợp với thao tác từng record đơn giản. Nếu cần join nhiều topic, giữ state, windowing, aggregation hoặc xử lý nghiệp vụ phức tạp, nên dùng Kafka Streams hoặc một ứng dụng stream processing chuyên biệt.

## 9. Cấu hình một connector

Connector được khai báo bằng JSON qua REST API. Các thuộc tính cụ thể phụ thuộc plugin, nhưng thường có:

- name: tên connector duy nhất trong Connect cluster.
- connector.class: class của plugin.
- tasks.max: giới hạn số task tối đa.
- Các thuộc tính kết nối nguồn/đích.
- Topic Kafka hoặc bảng/file nguồn liên quan.
- Converter, SMT và error handling nếu cần.

Ví dụ khung cấu hình source connector:

~~~json
{
  "name": "orders-source",
  "config": {
    "connector.class": "com.example.connect.OrdersSourceConnector",
    "tasks.max": "2",
    "topic.prefix": "raw-",
    "connection.url": "jdbc:postgresql://db:5432/orders",
    "connection.user": "CONFIG_PROVIDER_REFERENCE_DB_USER",
    "connection.password": "CONFIG_PROVIDER_REFERENCE_DB_PASSWORD"
  }
}
~~~

Đây là ví dụ minh họa cấu trúc; com.example.connect.OrdersSourceConnector và các thuộc tính topic.prefix, connection.url là cấu hình giả định của plugin mẫu, không phải connector có sẵn trong Apache Kafka. Hãy dùng đúng tên class và thuộc tính theo tài liệu plugin được cài đặt. Các giá trị user/password ở ví dụ chỉ là placeholder; production cần dùng ConfigProvider/secret store hoặc cơ chế bảo mật do nền tảng cung cấp.

Không đưa password thật vào JSON gửi qua terminal history, source control hoặc log.

## 10. REST API quản lý connector

Distributed worker cung cấp REST API để quản lý connector. Cổng mặc định thường là 8083; địa chỉ và listener có thể thay đổi theo cấu hình worker.

Các endpoint thường dùng:

| Endpoint | Mục đích |
|---|---|
| GET /connectors | Liệt kê connector |
| POST /connectors | Tạo connector |
| GET /connectors/{name} | Đọc cấu hình connector |
| GET /connectors/{name}/status | Xem trạng thái connector và task |
| GET /connectors/{name}/tasks | Liệt kê task |
| GET /connectors/{name}/tasks/{taskId}/status | Xem trạng thái một task |
| PUT /connectors/{name}/config | Cập nhật cấu hình connector |
| PUT /connectors/{name}/pause | Tạm dừng connector |
| PUT /connectors/{name}/resume | Tiếp tục connector |
| POST /connectors/{name}/restart | Restart connector |
| DELETE /connectors/{name} | Xóa connector |

Có thể liệt kê các plugin mà worker đã phát hiện bằng GET /connector-plugins. Endpoint này hữu ích khi xác minh plugin.path và phiên bản connector đã được cài trên worker.

Tạo connector bằng curl:

~~~bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  --data @orders-source.json
~~~

Kiểm tra trạng thái:

~~~bash
curl http://localhost:8083/connectors/orders-source/status
~~~

Tạm dừng và tiếp tục:

~~~bash
curl -X PUT http://localhost:8083/connectors/orders-source/pause
curl -X PUT http://localhost:8083/connectors/orders-source/resume
~~~

REST API có thể được expose qua network. Production cần giới hạn truy cập bằng network policy, authentication/authorization hoặc reverse proxy phù hợp; không mở endpoint quản trị công khai.

## 11. Plugin path và cài đặt connector

Kafka Connect runtime chỉ tải được plugin có mặt trên classpath/plugin path của worker. Worker thường dùng cấu hình plugin.path để chỉ định thư mục chứa connector plugin và dependency.

Ví dụ:

~~~properties
plugin.path=/opt/kafka/plugins,/opt/connect/custom
~~~

Với distributed mode:

- Cài cùng phiên bản plugin và dependency tương thích trên mọi worker có thể nhận task.
- Giữ cấu hình plugin.path nhất quán giữa các worker.
- Khởi động lại worker theo quy trình rollout sau khi cài plugin.
- Kiểm tra plugin đã được phát hiện qua endpoint plugin hoặc log worker.
- Tránh đặt nhiều phiên bản thư viện xung đột trong cùng classloader/plugin directory.

Nếu connector xuất hiện ở một worker nhưng không xuất hiện ở worker khác, task có thể fail khi được phân phối sang worker thiếu plugin. Hãy coi việc triển khai plugin là một phần của quy trình release Connect cluster.

## 12. Offset, retry và khả năng giao lại record

Kafka Connect quản lý tiến độ khác nhau cho source và sink:

**Source connector**

- Connector tạo source partition và source offset.
- Worker lưu source offset vào offset store.
- Sau restart, connector dùng offset đã lưu để tiếp tục đọc nguồn.
- Nếu nguồn không cung cấp offset ổn định hoặc connector không checkpoint đúng, có thể mất hoặc đọc lại dữ liệu.

**Sink connector**

- Sink connector đọc topic bằng consumer.
- Tiến độ đọc Kafka được lưu dưới consumer group offset.
- Nếu ghi vào hệ thống đích thành công nhưng offset Kafka chưa commit, record có thể được gửi lại.
- Nếu commit offset quá sớm trước khi đích ghi bền vững, có nguy cơ bỏ sót dữ liệu.

Do đó, sink connector và hệ thống đích cần được thiết kế để chịu được replay. Ví dụ, ghi theo upsert với khóa ổn định hoặc dùng idempotency key sẽ an toàn hơn thao tác insert không kiểm soát trùng lặp.

Không mặc định mọi connector đều có exactly-once. Mức bảo đảm phụ thuộc loại connector, API nguồn/đích, cách checkpoint, transaction support và cấu hình. Hãy đọc tài liệu của plugin và kiểm thử crash/restart tại các điểm giữa đọc, ghi và commit.

## 13. Xử lý lỗi và Dead Letter Queue

Connector có thể gặp lỗi khi parse record, chuyển đổi schema, thực hiện SMT hoặc ghi dữ liệu đích. Worker hỗ trợ các cấu hình xử lý lỗi như:

~~~properties
errors.tolerance=all
errors.log.enable=true
errors.log.include.messages=false
errors.deadletterqueue.topic.name=connect-errors
errors.deadletterqueue.context.headers.enable=true
~~~

Ý nghĩa khái quát:

- errors.tolerance=none: dừng task/connector khi gặp lỗi được framework xem là không thể tiếp tục.
- errors.tolerance=all: cho phép bỏ qua lỗi được hỗ trợ và tiếp tục; nên kết hợp DLQ để không mất dấu record lỗi.
- errors.deadletterqueue.topic.name: topic nhận record lỗi khi loại lỗi và connector path hỗ trợ DLQ.
- errors.log.enable: ghi log lỗi.
- errors.log.include.messages: có đưa nội dung record vào log hay không; cần cân nhắc dữ liệu nhạy cảm.

Không phải mọi lỗi đều được chuyển DLQ. Lỗi kết nối database, mất quyền truy cập, worker crash hoặc lỗi hệ thống nghiêm trọng có thể khiến task dừng thay vì chuyển từng record. Retry và DLQ cần được thiết kế theo loại lỗi, không bật tolerance all một cách máy móc.

## 14. Theo dõi trạng thái và hiệu năng

Khi vận hành Connect, cần quan sát cả connector, task, worker và hệ thống nguồn/đích:

- Connector state: RUNNING, PAUSED, FAILED hoặc trạng thái tương ứng phiên bản.
- Task state: task nào đang chạy, task nào fail và stack trace.
- Source record poll/write rate.
- Sink record read/write rate.
- Source offset commit và sink consumer lag.
- Retry count, DLQ record count và lỗi conversion.
- Batch size, task duration và request latency đến hệ thống ngoài.
- Worker CPU, heap, GC, network và số lần rebalance.
- Trạng thái database, API hoặc storage đích.

REST status giúp kiểm tra nhanh:

~~~bash
curl http://localhost:8083/connectors/orders-source/status
curl http://localhost:8083/connectors/orders-sink/status
~~~

REST status không thay thế metrics. Với production, xuất Connect worker metrics sang hệ thống giám sát, đặt cảnh báo cho task FAILED, connector không tiến triển, sink lag tăng liên tục và DLQ tăng đột biến.

Khi worker gia nhập hoặc rời distributed Connect cluster, framework có thể thực hiện rebalance để phân công lại task. Vì vậy, số worker đang sống không đồng nghĩa mọi task đều RUNNING ngay lập tức; cần theo dõi trạng thái task sau khi rollout hoặc restart.

## 15. Khi nào nên dùng Kafka Connect?

Kafka Connect phù hợp khi:

- Cần ingest dữ liệu từ database, file, object storage hoặc dịch vụ ngoài vào Kafka.
- Cần chuyển dữ liệu từ Kafka sang search engine, data lake hoặc warehouse.
- Plugin hiện có đáp ứng giao thức và mô hình dữ liệu.
- Muốn quản lý connector/task qua REST API và mở rộng worker.
- Muốn chuẩn hóa offset, retry, converter, transform và monitoring.

Nên cân nhắc ứng dụng Java/Spring Kafka hoặc Kafka Streams khi:

- Logic nghiệp vụ cần nhiều bước và kiểm soát luồng chi tiết.
- Cần join, aggregate, window hoặc xử lý stateful phức tạp.
- Cần giao tiếp request/response đồng bộ với hệ thống ngoài.
- Cần transaction xuyên nhiều hệ thống có yêu cầu riêng.
- Không có plugin phù hợp và connector tùy chỉnh trở nên phức tạp như một ứng dụng riêng.

Kafka Connect không loại bỏ nhu cầu thiết kế schema, idempotency, bảo mật, retention, retry và khả năng chịu lỗi của hệ thống nguồn/đích.

## 16. Quy trình triển khai một luồng tích hợp

1. Xác định nguồn, đích, dữ liệu cần đồng bộ và độ trễ chấp nhận được.
2. Chọn source/sink connector phù hợp; kiểm tra phiên bản Kafka, plugin và hệ thống ngoài.
3. Chọn standalone để thử plugin hoặc distributed cho môi trường cần khả năng phục hồi.
4. Cấu hình worker, internal topics, replication factor và security.
5. Cài plugin giống nhau trên mọi worker.
6. Chọn converter và schema strategy thống nhất giữa producer/consumer/connector.
7. Cấu hình connector, tasks.max, topic mapping, credentials và SMT.
8. Tạo connector qua REST API và kiểm tra trạng thái từng task.
9. Tạo dữ liệu thử, kiểm tra record ở Kafka hoặc hệ thống đích.
10. Thử restart worker, mất kết nối nguồn/đích và record lỗi để xác nhận offset/retry/DLQ.
11. Thiết lập dashboard, cảnh báo và runbook trước khi đưa vào production.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Connector không tạo được | Sai connector.class hoặc plugin chưa được cài | Kiểm tra plugin list và worker log |
| Task FAILED sau khi phân phối lại | Một worker thiếu plugin/dependency | So sánh plugin.path và plugin version trên mọi worker |
| Source đọc lại dữ liệu | Source offset chưa commit hoặc nguồn replay | Kiểm tra offset store và semantics connector |
| Sink ghi trùng | Đích đã ghi nhưng Kafka offset chưa commit | Dùng upsert/idempotency key và kiểm tra sink connector |
| Sink lag tăng | Đích chậm, ít task, lỗi retry hoặc thiếu worker | Kiểm tra task throughput, destination latency và consumer lag |
| Dữ liệu sai format | Converter/schema không tương thích | Kiểm tra key/value converter và schema registry |
| Record bị bỏ qua | errors.tolerance hoặc SMT filter | Kiểm tra worker config, DLQ và transform chain |
| REST API không truy cập được | Listener, firewall hoặc authentication | Kiểm tra REST listener và network policy |
| Connector không tiến triển | Task bị treo, nguồn không có dữ liệu hoặc lỗi kết nối | Kiểm tra status, log, source offset và metrics |

## 18. Bài tập tự kiểm tra

1. Kafka Connect khác với việc tự viết một Kafka consumer/producer cho từng hệ thống ở điểm nào?
2. Phân biệt worker, connector và task.
3. Source offset khác Kafka record offset và sink consumer offset như thế nào?
4. Vì sao distributed mode cần config, offset và status internal topics?
5. Tại sao config.storage.topic phải có một partition?
6. Converter khác SMT ở vai trò nào?
7. Vì sao sink connector có thể ghi trùng record sau restart?
8. Khi nào nên dùng Kafka Streams thay cho SMT?
9. Vì sao mọi worker cần có cùng phiên bản plugin?
10. Khi bật DLQ, những loại lỗi nào vẫn có thể làm task dừng?

## Kết luận

Kafka Connect cung cấp runtime chuẩn để tích hợp dữ liệu giữa Kafka và hệ thống bên ngoài. Source connector đưa dữ liệu vào Kafka; sink connector đưa dữ liệu từ Kafka ra đích. Worker chạy connector và task, converter xử lý định dạng, SMT thực hiện biến đổi từng record, còn REST API giúp quản lý vòng đời và trạng thái.

Standalone phù hợp thử nghiệm; distributed mode hỗ trợ mở rộng và phục hồi bằng nhiều worker cùng internal topics. Khi triển khai thực tế, cần thiết kế source offset, sink consumer offset, retry, DLQ, converter, plugin version và idempotency theo khả năng của connector và hệ thống đích. Connect giảm công việc tích hợp lặp lại, nhưng chất lượng và độ tin cậy của luồng vẫn phụ thuộc vào cấu hình và semantics của từng plugin.
