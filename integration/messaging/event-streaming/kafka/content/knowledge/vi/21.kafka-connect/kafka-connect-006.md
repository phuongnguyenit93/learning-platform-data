# Cài plugin, cách ly classloader và quản lý phiên bản connector

Kafka Connect chạy connector bên trong tiến trình worker. Để worker nhận diện được một source connector hoặc sink connector, các JAR và dependency của plugin phải được cài đúng vị trí, được khai báo trong `plugin.path` và tương thích với phiên bản Kafka Connect đang chạy. Khi worker khởi động, Kafka Connect quét các plugin, tạo classloader phù hợp và công bố connector class mà REST API có thể sử dụng.

Trong cluster distributed, mọi worker có thể nhận task sau rebalance. Vì vậy, cài plugin trên một worker là chưa đủ: toàn bộ worker cần có bộ plugin và phiên bản tương thích như nhau. Classloader isolation giúp các plugin tránh xung đột dependency Java, nhưng không phải sandbox bảo mật; code connector vẫn chạy trong JVM và có quyền của tiến trình worker. Bài viết trình bày cách cài plugin, kiểm tra discovery, quản lý dependency/version và nâng cấp an toàn.

## 1. Phân biệt Kafka Connect worker, connector và task

Kafka Connect là runtime tích hợp dữ liệu giữa Kafka và hệ thống bên ngoài. Một deployment có thể chạy standalone hoặc distributed:

- **Worker:** tiến trình JVM chạy Kafka Connect runtime, quản lý REST API, plugin, connector và task.
- **Connector:** instance cấu hình của một plugin, ví dụ một JDBC source đọc từ database hoặc một S3 sink ghi dữ liệu ra object storage.
- **Task:** đơn vị công việc do connector tạo ra và được worker thực thi. Connector có thể tạo một hoặc nhiều task tùy khả năng chia nhỏ nguồn/đích và cấu hình `tasks.max`.
- **Plugin:** gói mã Java cung cấp connector class, converter, SMT hoặc thành phần mở rộng mà Kafka Connect có thể nạp.

Một connector class có thể được dùng để tạo nhiều connector instance với tên và cấu hình khác nhau. Ví dụ `io.confluent.connect.jdbc.JdbcSourceConnector` là class plugin; `orders-db-source` là tên một connector instance được tạo qua REST API.

Plugin được cài trên worker, không cài vào Kafka broker. Broker chỉ lưu và truyền dữ liệu Kafka; worker mới tải connector code và gọi database, object storage hoặc hệ thống bên ngoài.

## 2. Cấu trúc thư mục plugin

Mỗi plugin nên được đặt trong thư mục riêng để quản lý JAR và dependency rõ ràng. Ví dụ cài JDBC connector thủ công:

```text
/opt/kafka-connect/
  plugins/
    jdbc-source-sink/
      kafka-connect-jdbc-<version>.jar
      postgresql-<version>.jar
      dependency-a.jar
      dependency-b.jar
    s3-sink/
      kafka-connect-s3-<version>.jar
      dependency-c.jar
      dependency-d.jar
```

Các dependency cần thiết của connector thường được đóng gói cùng plugin theo hướng dẫn của nhà cung cấp. Một số gói cài đặt dùng thư mục con `lib/`, `etc/` hoặc manifest riêng; hãy giữ nguyên layout do gói phát hành quy định thay vì tự ý chuyển JAR.

Không gom tất cả connector và dependency của chúng vào một thư mục dùng chung. Ví dụ JDBC connector và S3 connector có thể yêu cầu hai phiên bản thư viện HTTP hoặc JSON khác nhau. Để chúng trong các plugin directory riêng giúp Kafka Connect tạo môi trường classloading tách biệt hơn.

## 3. Cấu hình `plugin.path`

`plugin.path` là thuộc tính của Kafka Connect worker, không phải thuộc tính của từng connector instance. Nó nhận danh sách đường dẫn phân cách bằng dấu phẩy, chỉ tới các thư mục chứa plugin.

Ví dụ trong worker properties:

```properties
bootstrap.servers=kafka-1:9092,kafka-2:9092
group.id=connect-cluster
config.storage.topic=connect-configs
offset.storage.topic=connect-offsets
status.storage.topic=connect-status

plugin.path=/opt/kafka-connect/plugins,/usr/local/share/kafka/plugins
```

Các đường dẫn nên là đường dẫn tuyệt đối, tồn tại trên từng worker và có quyền đọc cho user chạy Kafka Connect. Có thể khai báo nhiều path để tách plugin do tổ chức quản lý với plugin của nhà cung cấp.

Trong Docker image của Confluent Platform, biến môi trường `CONNECT_PLUGIN_PATH` thường được entrypoint ánh xạ vào cấu hình worker tương ứng. Với image Kafka Connect khác, cần kiểm tra quy ước biến môi trường của image; không mặc định mọi image đều hỗ trợ cùng tên biến.

Không đặt `plugin.path` trong JSON config gửi tới `POST /connectors` hoặc `PUT /connectors/{name}/config`. REST connector config chỉ cấu hình một connector instance; plugin path thuộc cấu hình khởi động của worker.

## 4. Cài plugin theo cách thủ công

Quy trình cài thủ công thường gồm:

1. Xác định phiên bản Kafka Connect và Java runtime trên worker.
2. Chọn bản connector được nhà cung cấp hỗ trợ cho runtime đó.
3. Tải gói phát hành từ nguồn đáng tin cậy.
4. Kiểm tra checksum/chữ ký và nguồn gốc artifact theo quy trình của tổ chức.
5. Giải nén toàn bộ JAR và dependency theo đúng layout của nhà cung cấp.
6. Đặt plugin vào thư mục nằm trong `plugin.path`.
7. Cấp quyền đọc cho user chạy worker.
8. Khởi động lại worker để plugin được discovery.
9. Kiểm tra plugin bằng REST API và log startup.

Ví dụ trên Linux:

```bash
sudo mkdir -p /opt/kafka-connect/plugins/jdbc-source-sink
sudo tar -xzf kafka-connect-jdbc-package.tar.gz \
  -C /opt/kafka-connect/plugins/jdbc-source-sink
sudo chown -R kafka:kafka /opt/kafka-connect/plugins/jdbc-source-sink
sudo find /opt/kafka-connect/plugins/jdbc-source-sink -type f -name '*.jar' -print
```

Lệnh giải nén phụ thuộc cấu trúc gói phát hành. Nếu archive đã chứa thư mục gốc, hãy kiểm tra để tránh tạo layout lồng nhau ngoài dự kiến như `jdbc/jdbc/lib/...` khiến plugin scanner không nhận diện được.

### Cài bằng Confluent Hub

Nếu môi trường sử dụng Confluent Hub Client và plugin có trên Hub, có thể cài một phiên bản được pin cụ thể:

```bash
confluent-hub install <publisher>/<connector-name>:<connector-version> \
  --component-dir /usr/share/confluent-hub-components
```

Sau đó thêm component directory vào `plugin.path` theo cấu hình của worker. Tránh dùng tag không pin version như `latest` trong production vì cùng một lệnh có thể cài ra artifact khác ở các lần build khác nhau.

Không phải mọi plugin đều có trên Confluent Hub. Với plugin khác, dùng gói chính thức hoặc quy trình build nội bộ có kiểm soát.

## 5. Cài plugin trong Docker/Kubernetes

Với container, nên đóng gói connector vào image bất biến thay vì tải JAR ngẫu nhiên mỗi lần container khởi động. Ví dụ Dockerfile khái niệm:

```dockerfile
FROM <kafka-connect-runtime-image>:<pinned-version>

COPY --chown=app:app plugins/jdbc-source-sink/ \
    /opt/kafka-connect/plugins/jdbc-source-sink/

COPY --chown=app:app plugins/s3-sink/ \
    /opt/kafka-connect/plugins/s3-sink/
```

Worker properties trong image hoặc config mount:

```properties
plugin.path=/opt/kafka-connect/plugins
```

Thay placeholder bằng image Kafka Connect runtime thực tế của tổ chức. Tên image, user và entrypoint cần điều chỉnh theo distribution đang dùng; không dùng image broker thuần thay cho image có Kafka Connect runtime.

Trong Kubernetes, mọi replica Connect phải dùng image/plugin set đồng nhất. Nếu dùng volume mount, đảm bảo volume được mount trên mọi pod, read-only nếu phù hợp, và không có pod nào nhìn thấy plugin directory khác. Image digest nên được pin để có thể tái tạo và rollback chính xác.

### Vì sao image bất biến hữu ích?

- Mỗi worker chạy cùng một bộ JAR và dependency.
- Có thể scan CVE và tạo SBOM trong pipeline build.
- Rollback bằng image digest đã biết.
- Tránh worker khởi động khác nhau vì tải plugin từ internet tại runtime.
- Dễ xác minh plugin version qua artifact và deployment manifest.

## 6. Kafka Connect discovery plugin khi nào?

Kafka Connect discovery plugin trong quá trình khởi động worker. Worker quét các thư mục trong `plugin.path`, tìm connector class và các plugin extension mà runtime hỗ trợ, sau đó đăng ký chúng với plugin discovery/classloader infrastructure.

Các điểm cần lưu ý:

- Thay đổi JAR hoặc `plugin.path` cần restart worker để discovery lại.
- Không giả định có thể chép JAR vào thư mục đang chạy rồi dùng ngay.
- Thư mục plugin phải đọc được bởi worker process.
- Gói phải chứa đầy đủ dependency theo layout được hỗ trợ.
- Plugin phải tương thích với Kafka Connect API/runtime và Java version.
- Quá nhiều JAR hoặc plugin directory lớn có thể làm thời gian startup và discovery tăng.

Log startup thường cho biết plugin nào được phát hiện và plugin nào không tải được. Khi plugin không xuất hiện trong REST API, hãy kiểm tra log worker trước khi tạo connector instance.

## 7. Kiểm tra plugin bằng REST API

Kafka Connect cung cấp endpoint:

```http
GET /connector-plugins
```

Ví dụ:

```bash
curl -s http://connect-1:8083/connector-plugins
```

Kết quả minh họa:

```json
[
  {
    "class": "io.confluent.connect.jdbc.JdbcSourceConnector",
    "type": "source",
    "version": "<connector-version>"
  },
  {
    "class": "io.confluent.connect.jdbc.JdbcSinkConnector",
    "type": "sink",
    "version": "<connector-version>"
  }
]
```

Endpoint trả danh sách connector plugin mà worker xử lý request đã phát hiện. Trong distributed cluster, hãy gửi request trực tiếp tới REST endpoint của **từng worker** để xác minh tất cả node có cùng plugin set/version. Đừng chỉ kiểm tra một địa chỉ load balancer vì request có thể luôn tới cùng một node hoặc không cho biết worker nào còn thiếu plugin.

REST API có thể được bảo vệ bởi TLS, authentication hoặc reverse proxy. Dùng URL và credential nội bộ theo chính sách cluster; không mở REST listener quản trị ra internet công khai.

## 8. Kiểm tra cấu hình connector trước khi tạo instance

Sau khi plugin được phát hiện, có thể kiểm tra cấu hình bằng endpoint validation:

```http
PUT /connector-plugins/{connector-type}/config/validate
```

Ví dụ với JDBC source connector:

```bash
curl -X PUT http://connect-1:8083/connector-plugins/io.confluent.connect.jdbc.JdbcSourceConnector/config/validate \
  -H 'Content-Type: application/json' \
  -d '{
    "connector.class": "io.confluent.connect.jdbc.JdbcSourceConnector",
    "connection.url": "jdbc:postgresql://db:5432/orders",
    "connection.user": "${file:/opt/connect-secrets/db.properties:username}",
    "connection.password": "${file:/opt/connect-secrets/db.properties:password}",
    "mode": "timestamp",
    "timestamp.column.name": "updated_at",
    "topic.prefix": "db-orders-",
    "tasks.max": "2"
  }'
```

Tên connector class, property và secret expression chỉ là ví dụ; cần thay bằng tài liệu đúng phiên bản connector và secret provider đang cấu hình. Kết quả validation cho biết property nào hợp lệ, thiếu hoặc sai kiểu. Nó không bảo đảm database đang truy cập được, credential có hiệu lực hoặc task sẽ chạy thành công trong production.

Sau khi validation pass, mới tạo connector instance qua `POST /connectors` hoặc cập nhật cấu hình qua `PUT /connectors/{name}/config`. Tên connector instance và `connector.class` là hai giá trị khác nhau.

## 9. Cách ly classloader hoạt động ra sao?

Kafka Connect chạy nhiều plugin trong cùng JVM. Mỗi plugin được nạp bằng classloader riêng theo cơ chế plugin isolation của runtime. Điều này giúp hai plugin sử dụng các phiên bản thư viện phụ thuộc khác nhau mà giảm nguy cơ xung đột class.

Ví dụ:

```text
Kafka Connect worker JVM
  ├── Connect runtime / shared API classes
  ├── Plugin classloader: JDBC connector
  │     ├── JDBC connector classes
  │     └── JDBC driver + dependency versions
  └── Plugin classloader: S3 connector
        ├── S3 connector classes
        └── AWS SDK + dependency versions
```

JDBC plugin có thể cần một phiên bản thư viện HTTP/JSON, trong khi S3 plugin cần phiên bản khác. Classloader isolation giúp giữ các dependency đó trong phạm vi plugin thay vì trộn tất cả vào classpath chung của worker.

Các class API mà connector cần giao tiếp với runtime, như Kafka Connect API và Java platform classes, phải được chia sẻ theo quy tắc của Kafka Connect. Vì vậy, plugin cần được build theo hướng dẫn packaging của nhà cung cấp và không tự ý đóng gói một bản Connect runtime khác vào thư mục plugin.

## 10. Classloader isolation không phải sandbox bảo mật

Classloader isolation giải quyết xung đột dependency và namespace class. Nó không chạy plugin trong process/container riêng và không tạo ranh giới bảo mật mạnh.

Connector code vẫn chạy với quyền của Kafka Connect worker. Nếu worker có thể truy cập file, network, environment variable hoặc secret nào, plugin độc hại hoặc bị xâm nhập có thể có khả năng sử dụng các quyền đó tùy cách runtime và hệ điều hành được cấu hình.

Do đó:

- Chỉ cài plugin từ nguồn tin cậy và đã review.
- Kiểm tra checksum/chữ ký, dependency và lỗ hổng bảo mật.
- Giới hạn quyền filesystem và network của worker.
- Không chạy worker bằng root nếu không cần.
- Không đặt secret plaintext trong connector config hoặc log.
- Dùng secret provider và workload identity theo nền tảng.
- Tách worker/cluster cho connector có mức độ tin cậy hoặc quyền truy cập rất khác nhau.
- Cập nhật plugin khi nhà cung cấp phát hành bản vá bảo mật.

Không coi việc đặt plugin vào thư mục riêng là đủ để cô lập quyền truy cập database hoặc secret. Nếu hai connector cần quyền hệ thống khác nhau đáng kể, tách worker cluster/process là biện pháp cách ly mạnh hơn.

## 11. Quản lý dependency của plugin

Một connector plugin thường gồm connector JAR và các dependency runtime. Khi cài, cần phân biệt:

| Loại dependency | Cách quản lý |
|---|---|
| Kafka Connect API/runtime | Thường do worker cung cấp; không tự đóng gói phiên bản khác trừ khi nhà cung cấp hướng dẫn rõ |
| Kafka client libraries | Phải tương thích với runtime; tránh đưa bản khác vào plugin directory nếu không có hướng dẫn cụ thể |
| Java platform classes | Do JDK cung cấp; không đóng gói lại |
| JDBC driver, AWS SDK, HTTP client, JSON libraries | Thường cần nằm trong gói plugin theo hướng dẫn connector |
| Thư viện được shade/relocate | Tuân theo cách đóng gói của nhà cung cấp; không tự giải nén và đổi tên class |

Không tải một JAR dependency bất kỳ vào plugin directory chỉ để chữa `ClassNotFoundException`. Cần xác định connector cần phiên bản nào, dependency có xung đột không và artifact đó có được nhà cung cấp hỗ trợ hay không.

### Lỗi dependency thường gặp

- `ClassNotFoundException`: thiếu JAR hoặc layout cài đặt sai.
- `NoClassDefFoundError`: class có lúc discovery nhưng không có khi runtime cần nạp, hoặc dependency bị thiếu.
- `NoSuchMethodError`: class được nạp nhưng phiên bản dependency không có method mà connector mong đợi.
- `LinkageError`: xung đột binary/class definition giữa các thư viện.
- `ClassCastException` dù hai class có cùng tên: cùng tên class được nạp bởi hai classloader khác nhau nên không tương thích về identity.

Không chữa lỗi bằng cách chép mọi JAR vào thư mục `libs/` chung của worker. Cách đó có thể làm xung đột lan sang toàn bộ connector.

## 12. Tương thích phiên bản connector và Kafka Connect

Khi chọn connector, cần kiểm tra ít nhất các thành phần:

| Thành phần | Câu hỏi cần xác minh |
|---|---|
| Kafka Connect runtime | Connector hỗ trợ Kafka Connect API/runtime version nào? |
| Kafka distribution | Connector có được nhà cung cấp kiểm thử với distribution đang chạy không? |
| Java runtime | Connector yêu cầu Java version nào và có tương thích JDK của worker không? |
| Connector version | Có hỗ trợ tính năng, cấu hình và source/sink semantics đang cần không? |
| Dependency | Các JAR đi kèm có đúng phiên bản và không xung đột với worker/plugin khác không? |
| Converter/SMT | Connector có giả định kiểu dữ liệu, converter hoặc Single Message Transform cụ thể không? |
| External system | JDBC driver/API của database, cloud service hoặc storage có được hỗ trợ không? |

Không chỉ nhìn số version của connector. Một connector mới có thể yêu cầu Java mới hơn hoặc Connect API mới hơn; một connector cũ có thể chạy được nhưng không hỗ trợ protocol/configuration hiện tại. Kiểm tra release notes, support matrix và yêu cầu Java/Kafka Connect của đúng bản phát hành.

### Không dùng version mới nhất một cách tự động

Production nên pin phiên bản connector và dependency. Dùng `latest` hoặc tải artifact không cố định khiến cùng một cấu hình triển khai có thể tạo ra plugin khác nhau giữa hai lần build. Pin version giúp reproducibility, rollback và điều tra sự cố.

## 13. Đồng nhất plugin trên mọi worker trong distributed mode

Trong distributed mode, connector/task có thể được phân phối lại giữa các worker khi có worker mới, worker dừng hoặc task được restart. Nếu một worker thiếu plugin hoặc có version khác, task được chuyển tới worker đó có thể thất bại hoặc chạy với hành vi khác.

Ví dụ cluster ba worker:

| Worker | JDBC plugin | S3 plugin | Trạng thái |
|---|---|---|---|
| `connect-1` | 10.8.x | 10.5.x | Đủ plugin |
| `connect-2` | 10.8.x | 10.5.x | Đủ plugin |
| `connect-3` | 10.7.x | Thiếu | Không đồng nhất |

Nếu task JDBC được chuyển sang `connect-3`, nó có thể chạy bằng version cũ; task S3 được chuyển sang đó có thể không tìm thấy connector class. Điều này có thể chỉ xuất hiện khi rebalance, dù connector đang hoạt động bình thường trước đó.

Quy tắc vận hành:

- Cài cùng plugin class và version trên mọi worker có thể nhận task.
- Giữ layout và dependency giống nhau.
- Kiểm tra từng worker bằng `GET /connector-plugins` trực tiếp.
- Dùng cùng image digest/configuration trong cluster.
- Không để một worker mới gia nhập cluster với plugin set chưa hoàn chỉnh.
- Sau khi thay plugin, xác minh task assignment và trạng thái connector.

## 14. Quy trình nâng cấp connector an toàn

Nâng cấp plugin có thể thay đổi class, dependency, default config, source offset behavior hoặc cách serialize record. Không nên thay JAR trực tiếp trong thư mục đang chạy.

Một quy trình có kiểm soát:

1. **Inventory:** liệt kê connector instance, connector class, task, config, worker assignment và plugin version hiện tại.
2. **Compatibility review:** đọc release notes, support matrix, thay đổi config, dependency và migration notes.
3. **Build artifact:** tạo image/plugin package mới với version pin và checksum/SBOM.
4. **Staging:** chạy thử với dữ liệu đại diện, xác minh source offset, sink behavior, converter, SMT và lỗi kết nối.
5. **Plan pause/maintenance:** xác định connector nào cần pause để tránh cùng logical connector chạy hỗn hợp plugin version.
6. **Deploy workers:** cập nhật plugin set đồng nhất trên toàn bộ worker theo chiến lược rolling có kiểm soát hoặc thay cluster.
7. **Verify discovery:** gọi `GET /connector-plugins` trên từng worker và so sánh class/version.
8. **Resume:** tiếp tục connector sau khi toàn bộ worker đã sẵn sàng.
9. **Observe:** theo dõi connector/task state, lag, error rate, throughput và external system.
10. **Rollback:** giữ image/plugin package cũ và cấu hình trước nâng cấp để có thể quay lại theo runbook.

### Pause connector trước khi rollout

Kafka Connect REST API hỗ trợ pause/resume connector:

```bash
curl -X PUT http://connect-1:8083/connectors/orders-db-source/pause
curl -s http://connect-1:8083/connectors/orders-db-source/status
```

Chờ trạng thái connector/task chuyển sang `PAUSED` theo phiên bản runtime và xác minh không còn task đang xử lý. Sau khi tất cả worker đã cập nhật và plugin được discovery đúng, resume:

```bash
curl -X PUT http://connect-1:8083/connectors/orders-db-source/resume
```

Pause có thể làm source ngừng đọc hoặc sink ngừng ghi trong thời gian bảo trì; lag hoặc backlog có thể tăng. Với yêu cầu không gián đoạn, cân nhắc triển khai Connect cluster mới (blue/green) và chuyển connector có kế hoạch, nhưng phải xử lý riêng source offsets, consumer group, sink idempotency và khả năng hai cluster cùng đọc/ghi trùng.

### Không trộn hai version cùng connector class một cách tùy tiện

Nếu cùng một fully-qualified connector class xuất hiện ở hai plugin directory với hai version khác nhau, discovery có thể tạo kết quả khó dự đoán hoặc chọn plugin không như mong muốn tùy runtime/version. Không dùng cách đặt cả bản cũ và mới cạnh nhau để hy vọng Connect tự chọn đúng. Chỉ để một version được chủ đích sử dụng trên mỗi worker trong một giai đoạn rollout.

## 15. Rollback plugin

Trước khi nâng cấp, lưu:

- Image digest hoặc archive plugin version cũ.
- Checksum và SBOM của plugin/dependency.
- Connector config đã triển khai.
- Worker properties và `plugin.path`.
- Trạng thái connector/task và source offsets cần theo dõi.
- Các thay đổi schema hoặc external system đi kèm.

Nếu bản mới lỗi:

1. Pause connector bị ảnh hưởng nếu còn hoạt động.
2. Đưa toàn bộ worker về image/plugin set cũ thống nhất.
3. Restart worker theo kế hoạch và kiểm tra plugin discovery.
4. Xác minh connector config tương thích với version cũ.
5. Resume connector và theo dõi source/sink offset, lag, duplicate và data consistency.

Không xóa plugin cũ hoặc config backup cho tới khi thời gian quan sát sau nâng cấp đã đạt yêu cầu. Nếu bản mới đã thay đổi định dạng offset, schema hoặc dữ liệu đích, rollback binary đơn thuần có thể chưa đủ; cần theo migration/rollback notes của connector.

## 16. Thêm connector instance sau khi plugin đã cài

Sau khi plugin được discovery, có thể tạo connector instance qua REST API. Ví dụ cấu hình source connector:

```bash
curl -X POST http://connect-1:8083/connectors \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "orders-db-source",
    "config": {
      "connector.class": "io.confluent.connect.jdbc.JdbcSourceConnector",
      "connection.url": "jdbc:postgresql://db:5432/orders",
      "connection.user": "${file:/opt/connect-secrets/db.properties:username}",
      "connection.password": "${file:/opt/connect-secrets/db.properties:password}",
      "mode": "timestamp",
      "timestamp.column.name": "updated_at",
      "topic.prefix": "db-orders-",
      "tasks.max": "2"
    }
  }'
```

Connector class phải tồn tại trên worker và cấu hình phải phù hợp với plugin version. Secret expression chỉ hoạt động nếu ConfigProvider tương ứng đã được cài và khai báo trong worker config. Không gửi password thật trong shell history hoặc lưu connector config chứa secret plaintext nếu cluster không có cơ chế bảo vệ phù hợp.

Kiểm tra trạng thái:

```bash
curl -s http://connect-1:8083/connectors/orders-db-source/status
```

REST API tạo connector instance không cài plugin. Nếu class chưa được discovery, request có thể báo lỗi không tìm thấy connector class.

## 17. Quản lý plugin ngoài connector class

Kafka Connect có thể mở rộng bằng các loại plugin khác nhau, không chỉ source/sink connector:

| Plugin type | Vai trò |
|---|---|
| Source/Sink Connector | Đọc dữ liệu từ hệ thống ngoài vào Kafka hoặc ghi từ Kafka ra hệ thống ngoài |
| Converter | Chuyển đổi key/value giữa bytes và representation như JSON/Avro |
| Single Message Transform (SMT) | Biến đổi từng record trong luồng Connect |
| ConfigProvider | Lấy cấu hình/secret từ nguồn bên ngoài theo cơ chế được hỗ trợ |
| Predicate/extension khác | Bổ sung điều kiện hoặc chức năng theo Kafka Connect version/plugin API |

Không phải mọi plugin type đều xuất hiện trong `GET /connector-plugins`; endpoint này tập trung liệt kê connector plugins. Cách kiểm tra converter, SMT hoặc ConfigProvider có thể phụ thuộc log startup, worker configuration và cách thành phần được sử dụng.

Plugin path có thể chứa nhiều loại plugin được runtime hỗ trợ. Cần kiểm soát version và dependency của tất cả thành phần mở rộng, không chỉ connector class.

## 18. Troubleshooting plugin không được nhận diện

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `GET /connector-plugins` không có connector class | Plugin không nằm trong `plugin.path`, sai layout hoặc chưa restart worker | Kiểm tra worker config, filesystem, quyền đọc và restart |
| Chỉ một worker nhìn thấy plugin | Plugin chỉ được cài trên một node hoặc image/volume không đồng nhất | Kiểm tra trực tiếp từng worker và đồng bộ deployment artifact |
| `ClassNotFoundException` | Thiếu JAR/dependency hoặc archive giải nén sai | Cài đủ dependency đúng layout theo vendor package |
| `NoClassDefFoundError` | Dependency có thể thiếu khi class được sử dụng runtime | Kiểm tra JAR, classpath/plugin logs và version matrix |
| `NoSuchMethodError` | Connector và dependency không tương thích binary | Dùng dependency version được nhà cung cấp hỗ trợ; loại bỏ JAR trùng/xung đột |
| `LinkageError` hoặc `ClassCastException` | Trùng class giữa classloader hoặc đóng gói Connect API không đúng | Tách plugin directory, không bundle API/runtime không phù hợp |
| Connector class được tìm thấy nhưng task FAILED | Plugin đã discovery nhưng config, credentials hoặc external system lỗi | Xem connector/task trace, validate config và kiểm tra hệ thống ngoài |
| Worker startup lâu sau khi thêm plugin | Quá nhiều JAR, scan path rộng hoặc dependency initialization chậm | Thu hẹp plugin.path, bỏ artifact thừa và xem startup log |
| Nâng cấp xong task chạy không nhất quán | Worker đang có plugin version khác nhau | Pause connector, đồng bộ tất cả worker và xác minh lại plugin list |
| REST validation pass nhưng task vẫn fail | Validation chỉ kiểm tra cấu hình, không bảo đảm runtime dependency/network | Kiểm tra credential, DNS, firewall, driver và external system |

## 19. Quy trình chẩn đoán theo thứ tự

Khi connector class không xuất hiện hoặc task thất bại, kiểm tra theo thứ tự:

1. Xác định worker đang xử lý request/task và địa chỉ REST tương ứng.
2. Đọc `plugin.path` hiệu lực của worker.
3. Kiểm tra thư mục plugin có tồn tại, user worker có quyền đọc và có JAR cần thiết.
4. Kiểm tra layout archive, manifest và dependency theo tài liệu plugin.
5. Đọc log startup để tìm discovery error, classloading error hoặc version mismatch.
6. Gọi `GET /connector-plugins` trực tiếp trên từng worker và so sánh class/version.
7. Gọi endpoint config validation cho connector class.
8. Kiểm tra connector/task status và trace lỗi runtime.
9. Xác minh kết nối external system, driver, secret provider và ACL Kafka.
10. Nếu vừa thay plugin, xác nhận mọi worker đã restart và chạy cùng plugin set.

Phân biệt lỗi discovery với lỗi task runtime. Nếu class không có trong plugin list, tập trung vào cài đặt, path và classloader. Nếu class đã có nhưng task fail, tập trung vào cấu hình connector, dependency runtime, external system và quyền truy cập.

## 20. Checklist production

**Cài đặt:**

- Xác định Kafka Connect runtime, Java version và connector support matrix.
- Pin connector version và dependency; xác minh checksum/chữ ký.
- Đặt mỗi plugin trong thư mục riêng, giữ đúng layout vendor package.
- Khai báo `plugin.path` ở worker config và dùng path tuyệt đối.
- Bảo đảm user worker đọc được toàn bộ JAR/dependency.
- Restart worker sau khi cài hoặc thay plugin.

**Classloader và bảo mật:**

- Không trộn dependency của nhiều plugin vào classpath chung.
- Không đóng gói Kafka Connect API/runtime khác với runtime worker.
- Chỉ dùng plugin từ nguồn tin cậy, có scan lỗ hổng/SBOM.
- Nhớ classloader isolation không phải security sandbox.
- Giới hạn quyền filesystem, network, secret và hệ điều hành của worker.
- Tách Connect cluster nếu cần ranh giới bảo mật mạnh hơn.

**Distributed cluster:**

- Cài cùng plugin class/version trên mọi worker.
- Dùng image digest hoặc artifact manifest đồng nhất.
- Gọi `GET /connector-plugins` trực tiếp trên từng worker.
- Kiểm tra plugin set trước khi cho worker mới gia nhập cluster.
- Không để cùng connector class có nhiều version cạnh tranh trên một worker.

**Upgrade/rollback:**

- Review release notes, API compatibility, Java và dependency.
- Test source/sink offsets, converters, SMT và external system trong staging.
- Pause connector hoặc dùng blue/green theo yêu cầu availability.
- Cập nhật toàn bộ worker có kiểm soát.
- Validate config và kiểm tra connector/task status sau deploy.
- Giữ image/plugin version cũ và runbook rollback.

## 21. Ghi nhớ

Kafka Connect plugin được cài trên worker và được discovery khi worker khởi động thông qua `plugin.path`. Mỗi plugin nên có thư mục và dependency riêng. Classloader isolation giúp giảm xung đột thư viện nhưng không phải sandbox bảo mật: connector code vẫn chạy trong JVM với quyền của worker.

Trong distributed mode, mọi worker có thể nhận task nên phải có plugin set và version tương thích như nhau. Dùng `GET /connector-plugins` trực tiếp trên từng worker để xác minh; dùng endpoint config validation trước khi tạo connector instance. Khi nâng cấp, pin version, kiểm thử staging, pause hoặc chuyển cluster theo kế hoạch, đồng bộ plugin trên toàn bộ worker và giữ artifact cũ để rollback. Quản lý plugin như một phần của worker image và quy trình phát hành giúp tránh lỗi discovery, dependency conflict và task failure sau rebalance.
