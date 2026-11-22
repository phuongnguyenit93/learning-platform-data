# Triển khai, cập nhật và bảo mật worker Connect

## Mục tiêu bài học

Kafka Connect chạy các connector để di chuyển dữ liệu giữa Kafka và hệ thống bên ngoài. Trong môi trường production, worker cần được triển khai thành cụm, chia sẻ trạng thái qua các internal topic, nạp đúng plugin, nhận cấu hình connector qua REST API và kết nối Kafka bằng danh tính bảo mật phù hợp. Việc cập nhật worker hoặc plugin cũng cần được điều phối để task có thể chuyển sang worker khác mà không làm mất tiến độ ngoài ý muốn.

Sau bài học, bạn có thể:

- Phân biệt standalone mode và distributed mode, chọn mode phù hợp với môi trường.
- Cấu hình worker và các internal topic của distributed Connect cluster.
- Triển khai nhiều worker với cùng `group.id` và cấu hình tương thích.
- Quản lý connector qua REST API và hiểu tác động của thay đổi cấu hình.
- Cài đặt, cập nhật plugin đồng nhất trên mọi worker.
- Cấu hình bảo mật kết nối Kafka bằng TLS/SASL và ACL.
- Bảo vệ REST API của Connect bằng network policy, TLS và cơ chế xác thực phù hợp.
- Quản lý secret bằng ConfigProvider thay vì ghi credential trực tiếp vào connector config.
- Rolling restart, nâng cấp plugin/worker và theo dõi task sau khi triển khai.
- Xây dựng checklist vận hành và xử lý sự cố thường gặp.

## 1. Kiến trúc worker Kafka Connect

Kafka Connect là runtime chạy các connector. Một connector định nghĩa nguồn dữ liệu hoặc đích dữ liệu; connector có thể chia công việc thành nhiều task. Worker là tiến trình chạy runtime, quản lý connector/task và giao tiếp với Kafka cluster.

Hai loại connector phổ biến:

- **Source connector:** đọc dữ liệu từ hệ thống bên ngoài và ghi record vào Kafka.
- **Sink connector:** đọc record từ Kafka và ghi dữ liệu đến hệ thống bên ngoài.

Trong distributed mode, nhiều worker cùng tham gia một Connect cluster. Các worker phối hợp qua Kafka để lưu cấu hình, offset và trạng thái connector/task. Nếu một worker dừng, task có thể được phân phối lại cho worker còn hoạt động.

```text
                  Kafka Connect REST API
                           |
                           v
                 +-------------------+
                 | Connect cluster   |
                 | group.id=connect  |
                 +-------------------+
                    /      |      \
                   /       |       \
                  v        v        v
             Worker 1  Worker 2  Worker 3
              |  |      |  |      |  |
              |  +------|--+------|--+---- Connector tasks
              |         |         |
              +---------+---------+
                        |
                        v
              Kafka internal topics
        config / offsets / status (replicated)
                        |
                        v
                  Kafka cluster

Source systems <--- Source connectors
Sink systems   ---> Sink connectors
```

Worker không đồng nghĩa với connector. Một worker có thể chạy nhiều task từ nhiều connector; task của cùng connector có thể được phân phối trên nhiều worker tùy connector và cấu hình.

## 2. Standalone mode và distributed mode

### 2.1. Standalone mode

Standalone mode chạy một worker trong một tiến trình. Connector được khai báo qua file cấu hình khi khởi động. Offset thường được lưu trong file local thông qua `offset.storage.file.filename`.

Ví dụ:

```bash
bin/connect-standalone.sh config/connect-standalone.properties \
  config/source-file.properties \
  config/sink-file.properties
```

Ưu điểm:

- Dễ chạy local, lab và thử nghiệm connector.
- Không cần tạo các internal topic cho distributed coordination.
- Cấu hình đơn giản, dễ quan sát trong một process.

Giới hạn:

- Không có worker khác tiếp quản task khi process dừng.
- File offset local cần được bảo vệ và backup nếu muốn giữ tiến độ.
- Không phù hợp làm runtime production cần high availability và scale out.

### 2.2. Distributed mode

Distributed mode chạy nhiều worker trong cùng một Connect cluster. Các worker có cùng `group.id` và cùng cấu hình internal topic. Kafka lưu connector config, source offsets và trạng thái để worker có thể phối hợp và phục hồi sau restart.

Khởi động một worker:

```bash
bin/connect-distributed.sh config/connect-distributed.properties
```

Khởi động thêm worker khác bằng cấu hình tương ứng trong cùng cluster. Các worker cần kết nối được đến cùng Kafka cluster và có plugin tương thích.

Ưu điểm:

- Task có thể được phân phối lại khi worker dừng hoặc tham gia cluster.
- Có thể tăng số worker để tăng tài nguyên chạy task.
- Connector được quản lý qua REST API thay vì truyền file cấu hình ở mỗi lần khởi động.
- Cấu hình và offset được lưu trong Kafka internal topics.

Distributed mode không tự bảo đảm mọi connector có thể scale tuyến tính. Số task tối đa, giới hạn nguồn/đích, partition và khả năng song song của connector vẫn quyết định throughput.

### 2.3. Chọn mode

| Tiêu chí | Standalone | Distributed |
|---|---|---|
| Mục tiêu | Local, lab, kiểm thử đơn giản | Production, HA, nhiều connector/task |
| Số worker | Một process | Nhiều worker trong cùng cluster |
| Lưu connector config | File cấu hình khởi động | Kafka internal config topic |
| Lưu source offset | Thường là file local | Kafka internal offset topic |
| REST API | Có, nhưng quản lý trong một worker | Có, quản lý cluster qua REST API |
| Failover task | Không có worker thay thế | Có thể phân phối lại task |
| Scale out | Không | Có, tùy khả năng connector |

## 3. Cấu hình distributed worker

Worker distributed được cấu hình bằng file properties, ví dụ `config/connect-distributed.properties`.

### 3.1. Cấu hình cơ bản

```properties
# Kafka cluster dùng làm bootstrap
bootstrap.servers=kafka-1.internal:9092,kafka-2.internal:9092,kafka-3.internal:9092

# Tên nhóm của Connect cluster; mọi worker cùng cluster dùng cùng giá trị
group.id=connect-prod

# Internal topics
config.storage.topic=connect-configs-prod
offset.storage.topic=connect-offsets-prod
status.storage.topic=connect-status-prod

# Replication cho internal topics
config.storage.replication.factor=3
offset.storage.replication.factor=3
status.storage.replication.factor=3

# Số partition cho offset và status topics
offset.storage.partitions=25
status.storage.partitions=5

# Converter cho key/value trên Kafka
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=false

# Plugin directories
plugin.path=/opt/kafka/plugins

# REST API
rest.port=8083
rest.advertised.host.name=connect-1.internal
rest.advertised.port=8083
```

Đây là ví dụ minh họa. Mỗi worker cần địa chỉ REST advertised phù hợp với hostname/port mà worker khác có thể truy cập. Không copy cùng `rest.advertised.host.name` sang mọi node nếu chúng có địa chỉ riêng.

### 3.2. Các thuộc tính quan trọng

| Property | Ý nghĩa |
|---|---|
| `bootstrap.servers` | Kafka brokers để worker lấy metadata và kết nối cluster |
| `group.id` | Định danh nhóm worker Connect; các worker cùng cluster phải giống nhau |
| `config.storage.topic` | Internal topic lưu connector và task configuration |
| `offset.storage.topic` | Internal topic lưu source connector offsets |
| `status.storage.topic` | Internal topic lưu trạng thái connector/task |
| `plugin.path` | Các thư mục chứa connector plugin và dependency |
| `key.converter` | Converter mặc định cho key của record |
| `value.converter` | Converter mặc định cho value của record |
| `rest.port` | Port REST API của worker trong các cấu hình dùng thuộc tính này |
| `rest.advertised.host.name` | Host worker công bố cho các worker khác |
| `rest.advertised.port` | Port worker công bố cho các worker khác |

Tên và khả năng cấu hình REST listener có thể thay đổi theo phiên bản Kafka. Một số phiên bản hỗ trợ thuộc tính `listeners` để khai báo URI HTTP/HTTPS; hãy đối chiếu tài liệu của đúng phiên bản Connect đang triển khai.

### 3.3. `group.id` phải nhất quán

Các worker thuộc cùng một Connect cluster phải dùng cùng `group.id`. Nếu hai nhóm worker dùng hai group ID khác nhau, chúng tạo thành hai Connect cluster độc lập, dù có thể cùng trỏ đến một Kafka broker.

Không dùng chung `group.id` cho các Connect cluster độc lập. Cũng không đặt `group.id` khác nhau trên từng worker dự định chạy cùng cluster.

### 3.4. Internal topics

Distributed Connect sử dụng ba internal topic chính:

| Topic | Mục đích | Đặc điểm cấu hình thường dùng |
|---|---|---|
| Config topic | Lưu cấu hình connector/task | Một partition, replication phù hợp, cleanup policy compact |
| Offset topic | Lưu source offsets | Nhiều partition để phân tán key, replication phù hợp, compact |
| Status topic | Lưu trạng thái connector/task | Có thể nhiều partition, replication phù hợp, compact |

Các internal topic nên được tạo trước bằng quy trình quản trị cluster trong production để kiểm soát partition, replication, min ISR và ACL. Nếu để worker tự tạo, cần chắc chắn broker auto topic creation và default topic configuration đáp ứng yêu cầu.

Ví dụ tạo topic bằng Kafka CLI:

```bash
kafka-topics.sh --bootstrap-server kafka-1.internal:9092 \
  --create --topic connect-configs-prod \
  --partitions 1 --replication-factor 3 \
  --config cleanup.policy=compact

kafka-topics.sh --bootstrap-server kafka-1.internal:9092 \
  --create --topic connect-offsets-prod \
  --partitions 25 --replication-factor 3 \
  --config cleanup.policy=compact

kafka-topics.sh --bootstrap-server kafka-1.internal:9092 \
  --create --topic connect-status-prod \
  --partitions 5 --replication-factor 3 \
  --config cleanup.policy=compact
```

Số partition và replication factor cần điều chỉnh theo kích thước cluster, số connector/task và yêu cầu availability. Config topic là nơi lưu trạng thái cấu hình quan trọng của Connect cluster; không xóa hoặc thay thế topic này khi cluster đang hoạt động.

### 3.5. Internal topics không phải topic dữ liệu nghiệp vụ

Không dùng `connect-configs-prod`, `connect-offsets-prod` hoặc `connect-status-prod` làm nơi chứa event nghiệp vụ. Không để consumer ứng dụng thông thường ghi hoặc sửa các topic này. Thay đổi trực tiếp dữ liệu internal có thể làm Connect mất cấu hình, offset hoặc trạng thái.

## 4. Triển khai nhiều worker

### 4.1. Chuẩn bị đồng nhất

Trước khi khởi động worker thứ hai, bảo đảm các worker có:

- Cùng Kafka cluster và cùng `group.id`.
- Cùng tên config/offset/status topics.
- Converter tương thích và cùng cách diễn giải dữ liệu.
- Cùng phiên bản Kafka Connect runtime tương thích.
- Cùng bộ connector plugin và dependency tương thích.
- Cấu hình security cho phép kết nối Kafka và internal topics.
- REST endpoint được công bố bằng hostname/port có thể truy cập giữa các worker.

Không nhất thiết mọi property phải giống tuyệt đối: hostname REST, port bind, log directory và một số thuộc tính theo node có thể khác nhau. Nhưng các cấu hình ảnh hưởng đến contract, Kafka cluster, internal topics và plugin cần được quản lý đồng nhất.

### 4.2. Ví dụ ba worker

```text
connect-1.internal:8083  --+
connect-2.internal:8083  --+--> group.id=connect-prod
connect-3.internal:8083  --+    config topic=connect-configs-prod
                               offsets topic=connect-offsets-prod
                               status topic=connect-status-prod
```

Mỗi worker chạy một process riêng. Có thể dùng cùng file cấu hình mẫu rồi thay các giá trị node-specific như advertised host, REST port hoặc log directory bằng environment variables/template của hệ thống triển khai.

### 4.3. Chạy worker bằng systemd

Trong máy chủ Linux, có thể quản lý worker như service. Ví dụ unit file khái quát:

```ini
[Unit]
Description=Kafka Connect Distributed Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=kafka-connect
Group=kafka-connect
ExecStart=/opt/kafka/bin/connect-distributed.sh /etc/kafka/connect-distributed.properties
Restart=on-failure
RestartSec=10
LimitNOFILE=100000

[Install]
WantedBy=multi-user.target
```

Đường dẫn và user cần điều chỉnh theo hệ thống. Dùng user riêng với quyền filesystem tối thiểu; không chạy Connect bằng root nếu không có yêu cầu đặc biệt.

### 4.4. Container và Kubernetes

Trong container/Kubernetes:

- Dùng image có Kafka Connect runtime và plugin đã được đóng gói, hoặc mount plugin directory theo quy trình kiểm soát.
- Mỗi pod có identity/REST advertised address phù hợp với networking của cluster.
- Cấu hình worker được đưa qua ConfigMap hoặc secret/config injection phù hợp.
- Dùng readiness/liveness probe theo khả năng của image và API; HTTP 200 ở root endpoint không thay thế kiểm tra task health.
- Cấp CPU/memory đủ cho converter, connector và batch processing.
- Dùng rolling update với `maxUnavailable` phù hợp để không dừng toàn bộ worker cùng lúc.
- Bảo đảm pod mới có thể đọc secret, truststore, plugin và internal topics trước khi nhận task.

Không scale pod chỉ để tăng số lượng mà không kiểm tra connector có thể tăng task song song hay không. Với một số connector, một task duy nhất vẫn là giới hạn dù có nhiều worker.

## 5. Quản lý connector qua REST API

Trong distributed mode, REST API là giao diện quản trị connector. Có thể gửi request đến worker trong cluster; Connect điều phối cấu hình qua internal topics và xử lý chuyển tiếp request quản trị theo cơ chế của phiên bản.

### 5.1. Kiểm tra worker

```bash
curl http://connect-1.internal:8083/
```

Liệt kê connector:

```bash
curl http://connect-1.internal:8083/connectors
```

Liệt kê connector plugin mà worker nhận diện:

```bash
curl http://connect-1.internal:8083/connector-plugins
```

Endpoint plugin giúp kiểm tra plugin có được nạp trên worker được truy vấn. Trong distributed cluster, nên kiểm tra mọi worker vì plugin có thể bị thiếu hoặc khác version trên một node.

### 5.2. Tạo connector

Ví dụ tạo File Sink connector:

```bash
curl -X POST http://connect-1.internal:8083/connectors \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "orders-file-sink",
    "config": {
      "connector.class": "org.apache.kafka.connect.file.FileStreamSinkConnector",
      "tasks.max": "1",
      "topics": "orders",
      "file": "/var/lib/kafka-connect/orders.txt"
    }
  }'
```

Connector này chỉ dùng minh họa/lab. File path phải tồn tại hoặc user worker có quyền tạo/ghi file. Production thường dùng connector chuyên dụng cho database, object storage hoặc hệ thống đích.

### 5.3. Xem trạng thái

```bash
curl http://connect-1.internal:8083/connectors/orders-file-sink/status
```

Response cho biết trạng thái connector và từng task, cùng worker đang chạy chúng. Trạng thái `FAILED` cần xem `trace`/exception và log worker để xác định nguyên nhân.

### 5.4. Lấy và cập nhật config

Đọc config hiện tại:

```bash
curl http://connect-1.internal:8083/connectors/orders-file-sink/config
```

Cập nhật config bằng `PUT`:

```bash
curl -X PUT http://connect-1.internal:8083/connectors/orders-file-sink/config \
  -H 'Content-Type: application/json' \
  -d '{
    "connector.class": "org.apache.kafka.connect.file.FileStreamSinkConnector",
    "tasks.max": "2",
    "topics": "orders",
    "file": "/var/lib/kafka-connect/orders.txt"
  }'
```

`PUT` thay thế cấu hình connector hiện tại bằng cấu hình được gửi; nên gửi đầy đủ các thuộc tính cần thiết. Việc thay đổi config có thể làm connector/task được reconfigure và phân phối lại. Hãy kiểm tra trạng thái sau cập nhật.

### 5.5. Pause, resume, restart và delete

Các endpoint phổ biến:

```bash
# Tạm dừng connector
curl -X PUT http://connect-1.internal:8083/connectors/orders-file-sink/pause

# Tiếp tục connector
curl -X PUT http://connect-1.internal:8083/connectors/orders-file-sink/resume

# Restart connector
curl -X POST http://connect-1.internal:8083/connectors/orders-file-sink/restart

# Xóa connector
curl -X DELETE http://connect-1.internal:8083/connectors/orders-file-sink
```

Endpoint restart có thể hỗ trợ query parameters để restart task hoặc xử lý task đang failed tùy phiên bản Kafka. Hãy kiểm tra REST API documentation của phiên bản thực tế trước khi tự động hóa.

Pause connector không giống delete connector. Pause giữ cấu hình connector và cho phép resume; delete loại bỏ cấu hình connector khỏi Connect cluster. Xóa connector không tự xóa topic Kafka hoặc dữ liệu đã ghi vào hệ thống đích.

## 6. Cập nhật worker và connector an toàn

### 6.1. Phân biệt worker config và connector config

| Loại cấu hình | Ví dụ | Cách thay đổi thường dùng |
|---|---|---|
| Worker config | `group.id`, `bootstrap.servers`, `plugin.path`, security, REST listener | Cập nhật file/env rồi restart worker theo kế hoạch |
| Connector config | `connector.class`, `tasks.max`, `topics`, endpoint nguồn/đích | REST API `PUT /connectors/{name}/config` |
| Task config | Cấu hình task do connector tạo/phân phối | Thường do framework quản lý từ connector config; không sửa trực tiếp internal topic |
| Plugin code/dependency | JAR, connector library, JDBC driver | Cập nhật plugin trên mọi worker và restart để nạp plugin |

Không cập nhật worker properties bằng REST API connector. Ngược lại, không restart toàn bộ cluster chỉ để thay một thuộc tính connector nếu REST API có thể cập nhật an toàn.

### 6.2. Rolling restart worker

Quy trình khái quát:

1. Kiểm tra cluster có đủ worker khỏe và task có thể chuyển sang node còn lại.
2. Kiểm tra internal topics có replication/ISR khỏe.
3. Cập nhật config hoặc plugin trên một worker.
4. Restart worker đó.
5. Chờ worker tham gia lại group và task được phân phối ổn định.
6. Kiểm tra connector/task status, log và throughput.
7. Lặp lại với worker tiếp theo.
8. Sau cùng, xác nhận mọi worker dùng cùng cấu hình/plugin version mong muốn.

Không restart đồng thời toàn bộ worker nếu mục tiêu là duy trì khả năng chạy connector. Với thay đổi protocol/version lớn, kiểm tra hướng dẫn upgrade của Kafka và plugin trước khi chạy mixed-version cluster.

### 6.3. Cập nhật connector config

Trước khi `PUT` config:

- Lưu bản config hiện tại vào hệ thống quản lý cấu hình an toàn.
- Kiểm tra schema/config validation của plugin.
- Xác định thay đổi có làm connector restart hoặc task rebalance không.
- Xác định offset có được giữ lại không; không xóa offset topic để ép connector chạy lại.
- Thử trên staging với dữ liệu đại diện.
- Cập nhật connector rồi đọc lại config/status để xác minh.

Một số thuộc tính có thể yêu cầu connector restart hoặc task reconfiguration. Hành vi cụ thể tùy connector implementation.

### 6.4. Nâng cấp plugin

Plugin cần có trên mọi worker có thể nhận task. Quy trình:

1. Xác định phiên bản connector, Kafka Connect runtime, Kafka client và dependency tương thích.
2. Kiểm tra release notes, breaking changes và yêu cầu Java.
3. Đóng gói artifact cùng dependency vào plugin directory riêng.
4. Triển khai cùng một bộ artifact lên tất cả worker.
5. Restart worker theo rolling plan để Connect nạp plugin mới.
6. Gọi `/connector-plugins` trên từng worker để xác minh class/version được nhận diện.
7. Kiểm tra connector config validation, task startup và log.
8. Theo dõi lag, error rate và kết quả dữ liệu sau nâng cấp.

Không thay JAR đang được classloader sử dụng trong process đang chạy và kỳ vọng Connect tự nạp lại. Plugin discovery thường diễn ra khi worker khởi động; restart là cách an toàn để nạp plugin mới trừ khi tài liệu phiên bản/triển khai có cơ chế khác.

## 7. Plugin path và classloader isolation

### 7.1. `plugin.path`

`plugin.path` khai báo một hoặc nhiều thư mục chứa plugin. Ví dụ:

```properties
plugin.path=/opt/kafka/plugins,/opt/company/connect-plugins
```

Mỗi connector plugin nên được đặt trong thư mục riêng có dependency cần thiết:

```text
/opt/kafka/plugins/
  jdbc-source/
    kafka-connect-jdbc-<version>.jar
    dependency-a.jar
    dependency-b.jar
  object-storage-sink/
    connector.jar
    dependency-c.jar
```

Không giả định chỉ copy một connector JAR là đủ. Một số plugin cần JDBC driver, cloud SDK hoặc thư viện bổ trợ. Dùng package/container image có version cố định để tránh worker này có dependency khác worker kia.

### 7.2. Classloader isolation

Kafka Connect sử dụng plugin classloader để cô lập dependency của connector với runtime và plugin khác. Điều này giảm xung đột thư viện nhưng không loại bỏ mọi xung đột, đặc biệt khi plugin dùng thư viện hệ thống hoặc API nội bộ không tương thích.

Nguyên tắc:

- Không đặt nhiều version của cùng connector trong cùng một plugin directory nếu không có chiến lược isolation rõ ràng.
- Không copy dependency của plugin vào thư mục `libs` của Kafka Connect một cách tùy tiện.
- Giữ dependency của từng plugin trong đúng thư mục plugin.
- Dùng version pinning và checksum để triển khai cùng artifact.
- Kiểm tra log class loading khi gặp `ClassNotFoundException`, `NoSuchMethodError` hoặc `LinkageError`.

### 7.3. Kiểm tra plugin đã được nạp

```bash
curl http://connect-1.internal:8083/connector-plugins
curl http://connect-2.internal:8083/connector-plugins
curl http://connect-3.internal:8083/connector-plugins
```

So sánh kết quả trên mọi worker. Một connector có thể được tạo thành công nhưng task được phân phối đến worker thiếu plugin sẽ thất bại khi khởi chạy.

### 7.4. Plugin discovery và version

Các phiên bản Kafka Connect mới có thể cung cấp thêm cấu hình discovery và cơ chế plugin scanning. Không dùng property chỉ có ở phiên bản mới trên worker cũ. Kiểm tra documentation của đúng Kafka Connect runtime để xác định cách scan, whitelist và classloader behavior.

## 8. Bảo mật kết nối worker đến Kafka

Worker phải xác thực và được cấp quyền để truy cập Kafka cluster. Tùy môi trường, dùng TLS, SASL/SCRAM, SASL/PLAIN qua TLS, SASL/GSSAPI hoặc cơ chế được tổ chức hỗ trợ.

### 8.1. TLS

Ví dụ cấu hình client worker dùng TLS:

```properties
security.protocol=SSL
ssl.truststore.location=/etc/kafka/secrets/connect.truststore.jks
ssl.truststore.password=<injected-truststore-password>
ssl.keystore.location=/etc/kafka/secrets/connect.keystore.jks
ssl.keystore.password=<injected-keystore-password>
ssl.key.password=<injected-key-password>
```

Các giá trị placeholder trong ví dụ phải được hệ thống triển khai thay bằng secret lúc khởi động worker; Kafka Connect không tự nội suy biến môi trường trong file properties theo cú pháp tùy ý. ConfigProvider được mô tả ở phần sau chủ yếu dùng để resolve connector configuration; không giả định placeholder ConfigProvider trong worker properties sẽ được xử lý giống connector config ở mọi version.

TLS mã hóa đường truyền và có thể xác thực broker/client bằng certificate. Kiểm tra trust chain, hostname verification, thời hạn certificate và quyền đọc keystore/truststore của user chạy worker.

### 8.2. SASL/SCRAM

Ví dụ cấu hình SASL/SCRAM:

```properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="connect-worker" password="<injected-scram-password>";
```

Secret placeholder phải được hệ thống triển khai thay bằng credential thật khi tạo worker properties; không commit password vào file. Tên mechanism và JAAS module phải khớp cấu hình broker. Khi dùng `SASL_SSL`, TLS bảo vệ thông tin xác thực trên đường truyền. Tránh dùng SASL/PLAIN trên kết nối không mã hóa.

### 8.3. ACL cho internal topics

Worker cần quyền truy cập các internal topic và group tương ứng. Tối thiểu cần xác định quyền cho:

- Đọc/ghi config topic.
- Đọc/ghi offset topic.
- Đọc/ghi status topic.
- Tham gia Connect worker group.
- Tạo/đọc/ghi topic dữ liệu tùy connector và converter.
- Transactional ID nếu worker/connector sử dụng Kafka transactions.

Không cấp quyền `superuser` cho worker chỉ để tránh lỗi ACL. Dùng principal riêng cho Connect cluster và cấp quyền theo đúng topic/group/transactional ID. Lệnh ACL cụ thể phụ thuộc authorizer và security model của Kafka cluster.

### 8.4. Tách quyền worker và connector

Worker sử dụng Kafka clients để quản lý internal topics. Source/sink connector cũng có thể dùng producer/consumer để đọc hoặc ghi topic dữ liệu. Một số connector hỗ trợ cấu hình client riêng hoặc override; khả năng này phụ thuộc `connector.client.config.override.policy` và connector implementation.

Không cho connector tùy ý override security properties nếu chưa có policy rõ ràng. Nếu cần tách principal theo connector, cấu hình allowlist override có kiểm soát và xác minh connector plugin thực sự dùng client properties đó.

## 9. Bảo vệ REST API của Connect

REST API cho phép tạo, sửa, restart và xóa connector; vì vậy người truy cập có thể thay đổi luồng dữ liệu và credential. Không để API quản trị mở công khai hoặc chỉ dựa vào việc đổi port.

### 9.1. Network isolation

- Chỉ cho phép network quản trị và worker trong cluster truy cập REST listener.
- Dùng firewall, security group hoặc Kubernetes NetworkPolicy.
- Đặt REST API sau private load balancer/reverse proxy khi cần quản trị tập trung.
- Không publish port REST ra Internet nếu không có lớp xác thực và bảo vệ phù hợp.
- Giới hạn quyền truy cập từ CI/CD runner và bastion host.

### 9.2. HTTPS/TLS cho REST listener

Các phiên bản Kafka Connect hỗ trợ cấu hình REST listener HTTP/HTTPS với thuộc tính `listeners` và SSL settings theo listener. Ví dụ minh họa dạng URI:

```properties
listeners=http://connect-1.internal:8083,https://connect-1.internal:8443
```

Cấu hình keystore/truststore cho HTTPS theo naming convention của Kafka Connect version đang dùng. Tên property cho listener-scoped SSL có thể khác với `ssl.*` dùng cho kết nối Kafka broker; không copy nguyên cấu hình broker client sang REST server.

Nếu phiên bản Connect cũ chưa hỗ trợ listener HTTPS theo cách mong muốn, đặt reverse proxy nội bộ có TLS phía trước REST API và chặn truy cập trực tiếp vào HTTP port. Xác minh worker-to-worker REST forwarding vẫn hoạt động sau khi đổi listener/advertised address.

### 9.3. Authentication và authorization

Kafka Connect REST API không nên được coi là đã có authentication/authorization đầy đủ chỉ vì Kafka broker dùng SASL. Bảo mật REST cần được triển khai riêng, ví dụ:

- REST extension phù hợp với version Connect để tích hợp authentication/authorization.
- Reverse proxy/API gateway xác thực danh tính và phân quyền endpoint.
- Network policy giới hạn nguồn truy cập, kết hợp TLS.
- Tách quyền read-only quan sát trạng thái khỏi quyền tạo/sửa/xóa connector nếu lớp gateway hỗ trợ.

Kiểm tra kỹ cách bảo vệ request forwarding giữa các worker; chỉ bảo vệ load balancer bên ngoài nhưng để worker REST port truy cập tự do vẫn tạo ra lỗ hổng.

### 9.4. Không xem CORS là cơ chế bảo mật

CORS là chính sách trình duyệt về cross-origin request, không phải cơ chế xác thực hoặc phân quyền cho REST API. Cấu hình CORS không thay thế TLS, authentication, authorization hoặc network isolation.

## 10. Quản lý secret bằng ConfigProvider

### 10.1. Vì sao không ghi password trực tiếp vào connector config?

Connector config có thể chứa password database, token cloud, API key hoặc SASL credential. Nếu ghi plaintext vào file, REST request, log hoặc hệ thống quản lý cấu hình, secret có thể bị lộ qua nhiều kênh.

Kafka Connect hỗ trợ ConfigProvider để thay thế placeholder bằng giá trị từ nguồn cấu hình bên ngoài. Worker cần bật provider và connector config tham chiếu secret bằng cú pháp phù hợp.

### 10.2. FileConfigProvider

Khai báo trong worker config:

```properties
config.providers=file
config.providers.file.class=org.apache.kafka.common.config.provider.FileConfigProvider
config.providers.file.param.allowed.paths=/etc/kafka/secrets
```

File `/etc/kafka/secrets/db.properties`:

```properties
db.username=connect_reader
db.password=replace-with-secret-from-secret-manager
```

Connector config tham chiếu:

```json
{
  "connector.class": "com.example.DatabaseSinkConnector",
  "connection.url": "jdbc:postgresql://db.internal:5432/orders",
  "connection.user": "${file:/etc/kafka/secrets/db.properties:db.username}",
  "connection.password": "${file:/etc/kafka/secrets/db.properties:db.password}"
}
```

Placeholder được resolve bởi worker khi connector config được xử lý. Tất cả worker có thể chạy connector đó cần truy cập được file/provider tương ứng. Nếu một worker thiếu file, task được chuyển sang worker đó có thể fail khi resolve secret.

`allowed.paths` và tên tham số provider phụ thuộc version Kafka. Nếu dùng thuộc tính này, kiểm tra nó có được hỗ trợ trong runtime đang chạy.

### 10.3. EnvironmentConfigProvider và provider ngoài

Có thể cấu hình provider môi trường hoặc provider do tổ chức triển khai:

```properties
config.providers=env,file
config.providers.env.class=org.apache.kafka.common.config.provider.EnvVarConfigProvider
config.providers.file.class=org.apache.kafka.common.config.provider.FileConfigProvider
```

Environment variable tiện cho container, nhưng secret trong environment có thể bị lộ qua process inspection, crash dump hoặc công cụ debug tùy nền tảng. Với secret nhạy cảm, cân nhắc secret volume có permission chặt hoặc provider tích hợp Vault/secret manager.

### 10.4. Secret rotation

Khi thay password hoặc certificate:

1. Cập nhật secret ở nguồn quản lý.
2. Bảo đảm mọi worker có thể đọc version mới.
3. Xác định connector có tự reload secret hay cần restart/reconfigure.
4. Cập nhật connector config/restart task theo yêu cầu của provider và plugin.
5. Kiểm tra kết nối mới thành công.
6. Thu hồi credential cũ sau khi xác nhận không còn task sử dụng.

Không giả định ConfigProvider luôn tự refresh secret đang được connector giữ trong memory. Hành vi reload phụ thuộc provider, connector và cách connector tạo connection pool.

## 11. Cập nhật connector plugin và worker version

### 11.1. Tương thích runtime

Trước khi nâng cấp, xác định:

- Kafka Connect runtime và Kafka broker version.
- Java runtime version.
- Connector plugin version.
- Dependency như JDBC driver, cloud SDK hoặc serializer.
- Converter và Schema Registry client version.
- Config schema và default behavior có thay đổi không.
- Source offset format có tương thích với phiên bản plugin mới không.

Connector upgrade có thể thay đổi cách serialize record, lưu source offset, xử lý retry hoặc tạo task. Đọc release notes và thử trên staging với dữ liệu/offset đại diện.

### 11.2. Rolling worker upgrade

Một chiến lược phổ biến:

1. Sao lưu worker config và connector config theo quy trình an toàn.
2. Kiểm tra internal topics, ISR và worker health.
3. Nâng một worker theo hướng dẫn version upgrade của Kafka.
4. Chờ worker gia nhập cluster, kiểm tra task assignment và connector status.
5. Tiếp tục từng worker còn lại.
6. Sau khi mọi worker đã nâng cấp, nâng plugin hoặc bật config mới theo kế hoạch riêng nếu cần.
7. Kiểm tra end-to-end dữ liệu nguồn/đích và offset.

Không mặc định mọi phiên bản Kafka hỗ trợ rolling upgrade tùy ý giữa mọi version. Với major/minor upgrade, thực hiện đúng thứ tự protocol/feature version và compatibility window được tài liệu Kafka quy định.

### 11.3. Rollback plugin

Giữ lại artifact plugin version cũ và cấu hình connector tương ứng. Nếu plugin mới làm task fail:

- Dừng hoặc rollback thay đổi theo runbook.
- Khôi phục plugin cũ đồng nhất trên mọi worker.
- Restart worker để nạp plugin version cũ.
- Xác minh source offset/connector config còn tương thích.
- Kiểm tra task status và dữ liệu đích để phát hiện duplicate hoặc gap.

Không xóa source offset topic để “làm sạch” sau rollback; việc đó có thể khiến source connector đọc lại dữ liệu lớn hoặc mất khả năng tiếp tục từ vị trí trước.

## 12. Monitoring và health check

Connect có REST status và JMX metrics. Cần theo dõi cả worker, connector, task và kết quả dữ liệu.

### 12.1. REST status

```bash
curl http://connect-1.internal:8083/connectors
curl http://connect-1.internal:8083/connectors/orders-file-sink/status
```

Trạng thái connector có thể là `RUNNING`, `PAUSED`, `FAILED` hoặc trạng thái vòng đời khác theo version. Mỗi task có status riêng; connector `RUNNING` không có nghĩa mọi task đều khỏe.

### 12.2. JMX metrics

Các nhóm metric thường hữu ích gồm:

- Worker metrics: trạng thái worker, rebalance, connector/task count và request.
- Connector metrics: số record được poll/write/read, error và thời gian xử lý.
- Task metrics: task state, batch size, poll/write rate và task error.
- Sink metrics: `sink-record-read-rate`, `sink-record-send-rate`, `sink-record-lag-max` hoặc metric tương đương theo version.
- Source metrics: `source-record-poll-rate`, `source-record-write-rate`, offset commit và record error.

Tên metric chính xác thay đổi theo Kafka Connect version và plugin. Kiểm tra JMX MBean thực tế trước khi xây dashboard.

### 12.3. Alert nên có

- Worker rời group hoặc cluster thiếu worker trong thời gian dài.
- Connector/task ở trạng thái `FAILED`.
- Task restart/rebalance lặp lại.
- Sink lag tăng liên tục hoặc source poll không tiến triển.
- Error rate hoặc DLT tăng đột biến.
- Internal topic thiếu ISR hoặc coordinator gặp lỗi.
- REST API không truy cập được hoặc latency tăng cao.
- Disk, heap, GC pause, CPU và network bất thường.
- Plugin discovery khác nhau giữa các worker.

Không dùng một health endpoint đơn giản làm tín hiệu duy nhất. Kết hợp REST status, JMX, log, lag và kiểm tra dữ liệu đầu ra.

## 13. Troubleshooting worker và connector

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Worker không tham gia cluster | `group.id`, broker, security hoặc internal topics sai | Kiểm tra log worker, bootstrap, ACL và topic state |
| Hai worker không nhìn thấy nhau | REST advertised host/port hoặc firewall | Kiểm tra DNS, port và REST forwarding |
| Connector class không tìm thấy | Plugin thiếu hoặc `plugin.path` sai | Gọi `/connector-plugins`, kiểm tra log plugin scan |
| Task fail trên một worker | Plugin/dependency không đồng nhất | So sánh artifact và version trên mọi node |
| Worker restart làm task phân phối lại liên tục | Crash loop, GC, network hoặc deployment quá dồn dập | Kiểm tra process, heap, log và rolling policy |
| Connector config không cập nhật như mong muốn | `PUT` thiếu property hoặc validation lỗi | GET config, validate config và xem response REST |
| Secret placeholder không resolve | Provider chưa khai báo, alias/path/key sai hoặc file thiếu | Kiểm tra worker config và quyền đọc secret |
| TLS handshake failure | Trust chain, hostname hoặc certificate sai | Kiểm tra SAN, truststore, expiry và protocol |
| SASL authentication failure | Mechanism/JAAS/credential không khớp | Kiểm tra broker listener và secret đã resolve |
| REST API bị truy cập trái phép | Listener mở rộng hoặc thiếu auth layer | Kiểm tra firewall, gateway, REST extension và worker-to-worker access |
| Sink lag tăng | Sink chậm, batch nhỏ, external system throttle | Kiểm tra task metrics, destination latency và task count |
| Source connector tạo duplicate sau restart | Offset chưa commit hoặc connector semantics | Kiểm tra source offset, connector guarantee và idempotency phía sink |
| Internal topic unavailable | Replication/ISR hoặc ACL không đủ | Kiểm tra leader, ISR và quyền principal Connect |

Khi điều tra, lưu lại connector config đã che secret, connector/task status, worker log theo cùng khoảng thời gian, internal topic health và metric. Không gửi credential hoặc payload nhạy cảm vào log/ticket.

## 14. Quy trình triển khai production mẫu

1. **Chuẩn bị cluster:** chọn distributed mode, Kafka cluster, `group.id` và tên internal topics riêng cho môi trường.
2. **Tạo internal topics:** config topic một partition, offset/status partition theo tải, replication/min ISR phù hợp và cleanup compact.
3. **Cấp ACL:** tạo principal worker, cấp quyền internal topics/group và quyền topic dữ liệu cần thiết.
4. **Chuẩn bị plugin:** đóng gói connector cùng dependency, pin version và triển khai giống nhau lên mọi node.
5. **Cấu hình worker:** bootstrap, group, internal topics, converters, plugin path, REST endpoint, TLS/SASL và ConfigProvider.
6. **Khởi động worker đầu tiên:** xác minh log, REST API và internal topics.
7. **Tham gia worker còn lại:** kiểm tra worker membership và plugin list trên từng node.
8. **Tạo connector:** validate config, gửi POST/PUT qua REST API và kiểm tra connector/task status.
9. **Kiểm thử dữ liệu:** xác minh source/sink record, key/value converter, offset và lỗi.
10. **Bật monitoring:** REST status, JMX, lag, worker/task health và alert.
11. **Diễn tập restart:** dừng một worker, xác minh task chuyển sang worker còn lại và tiếp tục đúng tiến độ.
12. **Ghi runbook:** lưu quy trình deploy, rotate secret, update plugin, rollback và incident response.

## 15. Các lỗi và anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Dùng standalone cho runtime cần HA | Worker dừng làm connector ngừng | Dùng distributed mode và nhiều worker |
| Mỗi worker dùng `group.id` khác nhau | Tạo nhiều Connect cluster độc lập | Dùng cùng group ID trong một cluster |
| Đổi tên internal topic khi worker đang chạy | Mất khả năng đọc config/offset/status cũ | Giữ tên topic ổn định và migration có kế hoạch |
| Xóa internal topics để reset connector | Mất cấu hình/offset/status của cluster | Dùng REST API và quy trình offset reset có kiểm soát |
| Plugin chỉ cài trên một worker | Task chuyển node có thể fail | Đồng bộ plugin/dependency trên mọi worker |
| Cập nhật JAR trong process đang chạy | Classloader vẫn giữ code cũ hoặc trạng thái không nhất quán | Deploy artifact rồi rolling restart |
| Mở REST API ra Internet không auth | Kẻ tấn công có thể tạo/sửa/xóa connector | Private network, TLS và auth/authorization |
| Nghĩ SASL Kafka tự bảo vệ REST API | REST có thể vẫn mở không xác thực | Bảo vệ REST riêng |
| Ghi password plaintext vào connector config | Secret lộ trong REST/config/log | ConfigProvider và secret manager |
| Dùng cùng REST advertised host cho mọi worker | Worker không gọi đúng node | Cấu hình địa chỉ advertised riêng có thể truy cập |
| Restart tất cả worker cùng lúc | Toàn bộ task có thể gián đoạn | Rolling restart và xác minh từng bước |
| Nâng plugin không kiểm tra offset compatibility | Connector có thể replay hoặc bỏ qua dữ liệu | Test upgrade/rollback với offset đại diện |
| Tăng worker nhưng không tăng task | Không tăng throughput | Đánh giá `tasks.max`, partition và giới hạn connector |

## 16. Checklist bảo mật và vận hành

Trước khi đưa Connect vào production, xác nhận:

- Dùng distributed mode cho cluster cần HA.
- `group.id` và internal topic names nhất quán, riêng theo môi trường.
- Config/offset/status topics có partition, replication, cleanup policy và ACL phù hợp.
- Worker chạy bằng user hệ điều hành riêng, quyền filesystem tối thiểu.
- Plugin và dependency có version pin, checksum và đồng nhất trên mọi worker.
- `plugin.path` không chứa artifact không được kiểm soát.
- Kafka connection dùng TLS/SASL theo chính sách tổ chức.
- ACL giới hạn quyền trên internal topics, group và data topics.
- Connector client override bị giới hạn bằng policy phù hợp.
- REST API chỉ truy cập qua private network, TLS và authentication/authorization.
- REST worker-to-worker forwarding hoạt động sau khi bật security.
- Không ghi plaintext secret vào connector config hoặc log.
- ConfigProvider được khai báo và secret có trên mọi worker có thể chạy task.
- Có quy trình secret rotation và plugin upgrade.
- Rolling restart được kiểm thử, không dừng toàn bộ worker ngoài kế hoạch.
- Monitoring có connector/task status, worker health, lag, errors và internal topic ISR.
- Có runbook cho task fail, worker fail, plugin mismatch, TLS/SASL và offset recovery.

## 17. Câu hỏi tự kiểm tra

1. Standalone mode khác distributed mode ở cách lưu config và offset như thế nào?
2. Vì sao các worker cùng Connect cluster phải dùng chung `group.id`?
3. Ba internal topic của distributed Connect lưu những loại trạng thái nào?
4. Vì sao config topic thường chỉ có một partition và dùng compact cleanup policy?
5. `plugin.path` có vai trò gì và vì sao plugin cần đồng nhất trên mọi worker?
6. `GET /connector-plugins` giúp phát hiện loại sự cố nào?
7. Khác biệt giữa cập nhật worker config và connector config là gì?
8. Vì sao `PUT /connectors/{name}/config` cần gửi đầy đủ cấu hình mong muốn?
9. Rolling restart giúp giảm gián đoạn như thế nào?
10. Worker kết nối Kafka bằng SASL/TLS có đồng nghĩa REST API được bảo vệ không?
11. Cần bảo vệ REST API bằng những lớp nào?
12. ConfigProvider giải quyết rủi ro nào khi lưu credential trong connector config?
13. Vì sao secret rotation có thể cần restart/reconfigure connector?
14. Khi nâng plugin, cần kiểm tra compatibility với source offsets và dependency ra sao?
15. Những metric nào giúp phát hiện worker khỏe nhưng task đang lỗi hoặc sink bị lag?

## Kết luận

Distributed Kafka Connect dùng nhiều worker cùng chia sẻ config, offset và status qua internal topics để phân phối task và phục hồi khi một worker dừng. Một triển khai production cần đồng nhất runtime/plugin, cấu hình REST advertised address, quản lý connector qua REST API và cập nhật worker theo rolling plan. Bảo mật phải bao gồm cả kết nối worker đến Kafka, ACL cho internal/data topics, REST API và secret của connector. Kết hợp ConfigProvider, plugin versioning, monitoring và runbook giúp Connect cluster dễ nâng cấp, kiểm soát quyền truy cập và phục hồi có dự đoán.
