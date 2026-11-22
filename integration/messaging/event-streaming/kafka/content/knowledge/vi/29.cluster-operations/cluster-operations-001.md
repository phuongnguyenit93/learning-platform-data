# Cấu hình broker tĩnh, động và cấu hình ghi đè ở topic

## Mục tiêu bài học

Kafka có nhiều lớp cấu hình: thuộc tính broker khai báo trong file cấu hình khi khởi động, dynamic broker config được thay đổi khi cluster đang chạy và cấu hình riêng của từng topic. Ba lớp này có phạm vi, cách lưu, thứ tự ưu tiên và tác động vận hành khác nhau. Nếu không hiểu precedence, người vận hành có thể sửa `server.properties` nhưng giá trị hiệu lực không đổi, hoặc đặt một topic override làm topic tiếp tục khác với broker mặc định.

Sau bài học, bạn có thể:

- Phân biệt static broker config, dynamic broker config và topic-level config.
- Hiểu cluster default, per-broker override và per-topic override.
- Đọc nguồn cấu hình hiệu lực bằng `kafka-configs.sh`.
- Thay đổi dynamic config mà không restart broker khi thuộc tính hỗ trợ cập nhật động.
- Xác định cấu hình nào yêu cầu rolling restart.
- Tạo, sửa, xóa và rollback topic config an toàn.
- Hiểu precedence giữa file cấu hình, dynamic override và topic override.
- Dùng Admin API để đọc và cập nhật cấu hình bằng Java.
- Quản lý ACL, audit, change record và quy trình vận hành production.
- Tránh các lỗi thường gặp khi chỉnh retention, replication, min ISR và giới hạn message.

## 1. Ba phạm vi cấu hình trong Kafka

Kafka có thể nhận cấu hình từ file broker, metadata động của cluster và metadata của topic. Cấu hình có phạm vi càng cụ thể thường càng có thể ghi đè giá trị mặc định ở phạm vi rộng hơn.

```text
                 Kafka cluster
                       |
           +-----------+-----------+
           |                       |
           v                       v
   Static broker config     Dynamic broker config
   server.properties        (cluster default / per broker)
           |                       |
           +-----------+-----------+
                       |
               Effective broker config
                       |
             +---------+---------+
             |                   |
             v                   v
          Topic A             Topic B
       Topic overrides     Topic overrides
             |                   |
             v                   v
      Effective config     Effective config
        for Topic A          for Topic B
```

### 1.1. Static broker configuration

Static config được khai báo trong file broker, thường là `server.properties` hoặc file được truyền vào startup script. Các thiết lập như listener, địa chỉ bind, thư mục log và một số thiết lập định danh/metadata cần được broker đọc khi khởi động.

Muốn thay đổi static config, người vận hành sửa file trên node tương ứng rồi restart broker theo rolling procedure. Thay file trên disk không làm process đang chạy tự đọc lại mọi property.

### 1.2. Dynamic broker configuration

Dynamic config được cập nhật khi cluster đang chạy bằng công cụ quản trị như `kafka-configs.sh` hoặc Admin API. Kafka lưu các override này trong metadata của cluster và áp dụng cho broker theo phạm vi của cấu hình. Các dynamic config được hỗ trợ có thể thay đổi mà không cần restart broker.

Dynamic config có thể là:

- **Cluster default:** giá trị động mặc định áp dụng cho broker không có override riêng.
- **Per-broker override:** giá trị riêng cho một broker.

Không phải mọi broker property đều hỗ trợ dynamic update. Kafka công bố update mode cho từng property trong broker config reference của phiên bản đang dùng.

### 1.3. Topic-level configuration

Topic config ghi đè một số giá trị mặc định của broker cho một topic cụ thể. Ví dụ topic A giữ dữ liệu 30 ngày, topic B chỉ giữ 3 ngày; hai topic vẫn chạy trên cùng cluster và dùng chung broker defaults cho những property không có override.

Topic config thường được quản lý bằng `kafka-configs.sh --entity-type topics` hoặc Admin API. Thay đổi topic config không yêu cầu restart broker, nhưng hiệu ứng dữ liệu có thể diễn ra dần theo chu kỳ segment/retention/compaction.

## 2. Cách chọn cấu hình hiệu lực

### 2.1. Precedence của broker config

Đối với broker property hỗ trợ dynamic cluster default và per-broker override, thứ tự ưu tiên thường là:

1. Dynamic per-broker override cho broker đó.
2. Dynamic cluster default nếu broker không có override riêng.
3. Static value trong file cấu hình broker.
4. Default value của Kafka nếu không có giá trị được khai báo.

Ví dụ:

| Nguồn | Một property có update mode `per-broker-cluster-wide` |
|---|---:|
| Kafka default | 7 đơn vị |
| Static trong `server.properties` | 4 đơn vị |
| Dynamic cluster default | 3 đơn vị |
| Dynamic override trên broker 2 | 2 đơn vị |

Kết quả:

- Broker 1 và broker 3 dùng 3 đơn vị.
- Broker 2 dùng 2 đơn vị.

Ví dụ chỉ minh họa precedence; hãy xác nhận property cụ thể có update mode phù hợp trong phiên bản Kafka đang chạy.

### 2.2. Precedence của topic config

Với property có hỗ trợ topic override, giá trị topic-level override được dùng cho topic đó. Nếu topic không có override, Kafka dùng broker-level default/effective config tương ứng.

Ví dụ:

| Phạm vi | `retention.ms` |
|---|---:|
| Broker effective default | 7 ngày |
| Topic `orders` override | 30 ngày |
| Topic `telemetry` override | 2 ngày |
| Topic `audit` không override | Dùng broker default 7 ngày |

Topic override không thay đổi broker default và không tác động đến topic khác.

### 2.3. Không phải mọi broker property đều có topic equivalent

Một số thuộc tính chỉ có ý nghĩa ở broker, ví dụ listener, thread pool, network, log directory hoặc controller settings. Không thể tạo topic override cho chúng.

Ngược lại, topic config như `retention.ms`, `cleanup.policy` hay `max.message.bytes` có phạm vi riêng cho log của topic. Đọc config reference để biết property hỗ trợ scope nào.

## 3. Static config: khai báo trong `server.properties`

### 3.1. Ví dụ cấu hình broker

```properties
node.id=1
listeners=PLAINTEXT://0.0.0.0:9092
advertised.listeners=PLAINTEXT://broker-1.internal:9092
log.dirs=/var/lib/kafka/data

num.network.threads=3
num.io.threads=8
socket.send.buffer.bytes=102400
socket.receive.buffer.bytes=102400

log.retention.ms=604800000
log.segment.bytes=1073741824
min.insync.replicas=2
```

Đây là ví dụ trích một số property, không phải file khởi động KRaft hoàn chỉnh. `node.id` dùng trong KRaft; cluster ZooKeeper đời cũ dùng `broker.id`. Cấu hình KRaft còn cần các property role/controller phù hợp. Không copy nguyên snippet này sang cluster production.

### 3.2. Các property thường cần restart

Những property cấu hình process hoặc hạ tầng khởi động thường cần restart để có hiệu lực, ví dụ:

- `log.dirs` hoặc cấu trúc lưu trữ broker.
- `process.roles`, `node.id` và một số thiết lập KRaft bootstrap/controller tùy version.
- JVM options như heap, GC, Java agent và system properties.
- Các property được config reference đánh dấu `read-only` hoặc chỉ đọc lúc khởi động.

`listeners`, `advertised.listeners` và một số listener/security setting có thể hỗ trợ dynamic update tùy Kafka version và listener type. Không tự xếp chúng vào nhóm static chỉ dựa trên tên; kiểm tra update mode và quy trình thay listener của đúng release.

### 3.3. Quy trình sửa static config

1. Xác định property và update mode của Kafka version.
2. Xác định broker/node bị ảnh hưởng và dependency của listener/storage.
3. Lưu bản cấu hình hiện tại và ghi lại giá trị mới.
4. Kiểm tra syntax, path, quyền filesystem, port và khả năng kết nối.
5. Chọn một broker để triển khai trước nếu thay đổi cho phép rolling restart.
6. Restart broker theo quy trình cluster, giữ đủ replica/ISR và controller quorum.
7. Xác minh broker trở lại, partition leader/replica khỏe và client kết nối được.
8. Lặp lại với broker tiếp theo.
9. Kiểm tra effective config và metric sau rollout.

Không restart đồng thời mọi broker chỉ để thay một property. Với controller-only hoặc thay đổi KRaft metadata/bootstrap, cần tuân theo quy trình upgrade/maintenance riêng của Kafka version.

## 4. Dynamic broker config

### 4.1. Vì sao dùng dynamic config?

Dynamic config cho phép thay đổi các property được hỗ trợ mà không phải restart broker. Điều này hữu ích khi điều chỉnh retention default, quota hoặc một số giới hạn/runtime behavior trong khi cluster đang phục vụ.

Dynamic config không có nghĩa thay đổi không rủi ro. Một số giá trị có thể tác động ngay đến throughput, disk usage, request admission hoặc replication. Cần đo, rollout có phạm vi và có rollback.

### 4.2. Dynamic cluster default

Cluster default áp dụng cho broker không có per-broker override, đối với property hỗ trợ cluster-wide dynamic config. Ví dụ đặt retention default động:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type brokers --entity-default \
  --alter --add-config log.retention.ms=604800000
```

Lệnh trên minh họa cú pháp cluster default. Trước khi chạy, xác nhận `log.retention.ms` hỗ trợ dynamic update trên version đang triển khai và giá trị phù hợp với policy lưu trữ.

Đọc lại:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type brokers --entity-default --describe
```

### 4.3. Dynamic per-broker override

Đặt giá trị riêng cho broker có entity name là broker ID. `num.io.threads` là ví dụ thường được hỗ trợ dynamic reconfiguration theo từng broker; hãy xác nhận update mode trong đúng release trước khi chạy:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type brokers --entity-name 2 \
  --alter --add-config num.io.threads=12
```

Broker 2 dùng 12 I/O threads; broker khác giữ giá trị hiệu lực riêng. Đây là ví dụ minh họa phạm vi per-broker, không dùng nó để thay đổi retention. Property phải có update mode cho phép per-broker dynamic override.

Đọc lại:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type brokers --entity-name 2 --describe
```

### 4.4. Xóa per-broker override

Để broker bỏ giá trị riêng và dùng lớp cấu hình kế tiếp:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type brokers --entity-name 2 \
  --alter --delete-config num.io.threads
```

Xóa override không nhất thiết đưa property về Kafka default. Broker sẽ dùng lớp cấu hình kế tiếp trong precedence, ví dụ dynamic cluster default nếu property hỗ trợ scope đó, static file value hoặc Kafka default.

### 4.5. Xóa dynamic cluster default

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type brokers --entity-default \
  --alter --delete-config log.retention.ms
```

Sau khi xóa, broker dùng per-broker override nếu có; nếu không thì dùng static broker config hoặc default của Kafka.

### 4.6. Dynamic config được lưu ở đâu?

Dynamic config là metadata của cluster, không chỉ là nội dung trong file `server.properties`.

- Với KRaft, metadata cluster được quản lý trong metadata log/quorum.
- Với các cluster Kafka đời cũ dùng ZooKeeper, dynamic broker/topic config được lưu qua metadata trong ZooKeeper theo cơ chế của phiên bản đó.

Không sửa trực tiếp metadata log hoặc ZooKeeper znodes để thay config. Dùng CLI/Admin API để Kafka validate, lưu và phân phối thay đổi.

## 5. Đọc config source và giá trị hiệu lực

### 5.1. `--describe` và `--all`

Đọc các dynamic broker config:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type brokers --entity-name 1 --describe
```

Đọc cả config mặc định và nguồn cấu hình mà CLI hỗ trợ hiển thị:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type brokers --entity-name 1 --describe --all
```

Tùy Kafka version, output có thể cho biết config source như dynamic broker config, dynamic default broker config, static broker config hoặc default config. Đây là cách quan trọng để biết giá trị đến từ đâu.

### 5.2. Phân biệt configured value và effective value

Một dynamic override có thể chỉ xuất hiện trên broker 2. Broker 1 không có override nhưng vẫn có effective value do static config hoặc default. Khi điều tra, cần trả lời:

- Property được cấu hình ở scope nào?
- Giá trị nào đang có hiệu lực trên broker cụ thể?
- Giá trị đó có bị một scope ưu tiên cao hơn ghi đè không?
- Broker version có hỗ trợ dynamic update cho property đó không?

Đừng kết luận broker đang dùng Kafka default chỉ vì `--describe` không hiển thị dynamic override.

### 5.3. Kiểm tra cấu hình topic

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name orders --describe
```

Xem cả default/effective source khi phiên bản hỗ trợ:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name orders --describe --all
```

Nếu topic không có override cho `retention.ms`, nó dùng broker default tương ứng. Nếu có `DYNAMIC_TOPIC_CONFIG`, giá trị topic-level đang ghi đè mặc định rộng hơn.

## 6. Topic-level configuration

### 6.1. Tạo topic kèm override

Có thể đặt topic config khi tạo topic:

```bash
bin/kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create --topic audit-events \
  --partitions 12 --replication-factor 3 \
  --config retention.ms=2592000000 \
  --config cleanup.policy=delete
```

Topic `audit-events` có retention 30 ngày trong ví dụ. Cấu hình này chỉ áp dụng cho topic đó; các broker default không thay đổi.

### 6.2. Thay đổi topic config sau khi tạo

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name audit-events \
  --alter --add-config retention.ms=777600000
```

Ví dụ thay retention thành 9 ngày. Sau đó kiểm tra:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name audit-events --describe
```

### 6.3. Xóa topic override

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name audit-events \
  --alter --delete-config retention.ms
```

Sau khi xóa, topic quay về dùng broker default cho property đó. Không có nghĩa dữ liệu cũ được khôi phục nếu trước đó retention ngắn đã xóa segment.

### 6.4. Các topic config thường gặp

| Property | Ý nghĩa | Cân nhắc khi thay đổi |
|---|---|---|
| `retention.ms` | Thời gian giữ log theo thời gian | Segment cũ được xóa theo chu kỳ; không phải deadline xóa chính xác từng record |
| `retention.bytes` | Giới hạn dung lượng log theo partition | Có thể xóa segment cũ khi vượt ngưỡng; hiểu rõ tính theo partition |
| `cleanup.policy` | `delete`, `compact` hoặc kết hợp | Thay đổi semantics lưu dữ liệu; cần kiểm tra consumer/replay contract |
| `min.insync.replicas` | ISR tối thiểu cho produce với `acks=all` | Tăng durability requirement nhưng có thể giảm write availability |
| `max.message.bytes` | Giới hạn kích thước record batch được chấp nhận cho topic | Producer, broker và consumer phải tương thích kích thước |
| `segment.bytes` | Kích thước segment log | Ảnh hưởng số segment, retention granularity và file count |
| `segment.ms` | Thời gian tối đa trước khi roll segment theo policy | Ảnh hưởng retention/compaction timing |
| `compression.type` | Codec lưu/đầu ra của topic theo cấu hình | Tác động CPU và network/storage; phụ thuộc codec producer gửi |
| `message.timestamp.type` | Chọn CreateTime hoặc LogAppendTime | Ảnh hưởng semantics timestamp và event-time consumer |
| `unclean.leader.election.enable` | Cho phép replica không thuộc ISR lên leader | Có thể mất dữ liệu đã xác nhận; chỉ bật khi hiểu trade-off |

Danh sách property hỗ trợ topic-level và giá trị hợp lệ phải theo topic config reference của đúng Kafka version. Không phải mọi broker property đều có thể đặt ở topic.

## 7. Ví dụ thiết kế config theo workload

### 7.1. Topic event nghiệp vụ cần giữ dữ liệu 30 ngày

Yêu cầu:

- Event cần replay trong thời gian dài.
- Replication factor 3.
- Producer dùng `acks=all`.
- Muốn ít nhất hai replica đồng bộ trước khi nhận write.

Ví dụ topic config:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name orders \
  --alter --add-config retention.ms=2592000000,min.insync.replicas=2
```

`min.insync.replicas=2` có ý nghĩa cùng với producer `acks=all`. Nếu ISR tụt dưới hai replica, write có thể bị từ chối thay vì chấp nhận durability thấp hơn.

### 7.2. Topic telemetry chỉ giữ 48 giờ

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name telemetry \
  --alter --add-config retention.ms=172800000
```

Topic này có thể dùng broker default cho các property khác. Trước khi rút ngắn retention, xác minh consumer outage window, replay requirement, Connect/Streams lag và audit policy.

### 7.3. Topic compacted lưu trạng thái mới nhất theo key

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name customer-state \
  --alter --add-config cleanup.policy=compact,delete.retention.ms=86400000
```

Ví dụ dùng compact; `delete.retention.ms` là property riêng. Nếu cần kết hợp `cleanup.policy=compact,delete`, hãy escape dấu phẩy trong value theo cú pháp `kafka-configs.sh` của phiên bản đang dùng hoặc dùng Admin API để tránh parser hiểu nhầm dấu phẩy là dấu phân tách config. Compaction giữ giá trị mới nhất theo key; delete policy có thể loại segment cũ theo thời gian. Cần hiểu semantics tombstone, `delete.retention.ms`, min cleanable ratio và yêu cầu consumer đọc từ đầu.

Không đổi một topic event log thuần append sang compact chỉ để tiết kiệm disk nếu downstream cần toàn bộ event history.

### 7.4. Giới hạn message lớn hơn cho một topic

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name media-metadata \
  --alter --add-config max.message.bytes=2097152
```

Ví dụ cho phép batch tối đa khoảng 2 MiB ở topic. Cần đồng bộ giới hạn phía producer như `max.request.size`, broker request limits và consumer fetch limits (`max.partition.fetch.bytes`, `fetch.max.bytes`) để record có thể đi trọn đường. Message lớn làm tăng memory footprint, latency, retry cost và nguy cơ head-of-line blocking.

## 8. Broker default và topic override phối hợp thế nào?

Giả sử cluster có broker default `min.insync.replicas=2` và topic `telemetry` có override bằng 1:

| Topic | Topic override | Effective value |
|---|---:|---:|
| `orders` | Không có | 2 |
| `payments` | 3 | 3 |
| `telemetry` | 1 | 1 |

Thay broker default từ 2 lên 3 sẽ tác động đến topic không có override. `payments` vẫn dùng 3 do topic override trùng giá trị; `telemetry` vẫn dùng 1. Xóa override của `telemetry` sẽ khiến topic dùng broker default mới là 3.

Đây là lý do cần quản lý topic config như một phần của contract vận hành. Một thay đổi broker default có thể không tác động đến topic đã có override, dẫn tới các topic có semantics khác nhau dù cùng cluster.

## 9. Dynamic config qua Admin API

CLI phù hợp thao tác thủ công. Với automation, có thể dùng Kafka Admin API để đọc và cập nhật config.

### 9.1. Đọc config bằng Java

```java
try (Admin admin = Admin.create(Map.of(
        AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"))) {

    ConfigResource resource = new ConfigResource(
        ConfigResource.Type.TOPIC,
        "orders"
    );

    Config config = admin.describeConfigs(List.of(resource))
        .all()
        .get()
        .get(resource);

    for (ConfigEntry entry : config.entries()) {
        System.out.printf("%s=%s source=%s sensitive=%s%n",
            entry.name(),
            entry.value(),
            entry.source(),
            entry.isSensitive());
    }
}
```

Đoạn code minh họa đọc topic config. Với broker resource, dùng `ConfigResource.Type.BROKER` và broker ID tương ứng; để đọc cluster default, API/resource support phụ thuộc Kafka client version. Kiểm tra API docs trước khi tự động hóa.

### 9.2. IncrementalAlterConfigs

Kafka Admin API hỗ trợ `incrementalAlterConfigs()` để SET, DELETE, APPEND hoặc SUBTRACT config entry tùy loại property. Ví dụ đặt retention cho topic:

```java
ConfigResource resource = new ConfigResource(
    ConfigResource.Type.TOPIC,
    "orders"
);

Map<ConfigResource, Collection<AlterConfigOp>> changes = Map.of(
    resource,
    List.of(new AlterConfigOp(
        new ConfigEntry("retention.ms", "2592000000"),
        AlterConfigOp.OpType.SET
    ))
);

admin.incrementalAlterConfigs(changes).all().get();
```

`SET` thay giá trị override. `DELETE` xóa override để quay về lớp cấu hình kế tiếp. APPEND/SUBTRACT chỉ phù hợp với config có semantics list/set được Kafka hỗ trợ; không dùng chúng cho mọi scalar property.

### 9.3. Vì sao ưu tiên incremental API?

IncrementalAlterConfigs thay đổi entry được chỉ định mà không phải gửi lại toàn bộ config. API cũ `alterConfigs()` có semantics thay thế cấu hình và dễ vô tình xóa các override khác nếu caller không gửi đầy đủ. Dùng incremental API khi Kafka client/broker version hỗ trợ.

### 9.4. Xử lý kết quả từng resource

Một request alter nhiều resource có thể có kết quả riêng theo resource. Automation cần:

- Chờ future hoàn tất.
- Kiểm tra lỗi của từng resource.
- Đọc lại config sau thay đổi.
- Không coi request gửi thành công là bằng chứng mọi broker/topic đã áp dụng.
- Ghi lại old value, new value, actor, timestamp và change ID.

## 10. Cách xác định property có dynamic update hay không

### 10.1. Đọc config reference đúng phiên bản

Kafka documentation mô tả update mode cho từng broker property. Các mode thường gặp:

- **read-only:** chỉ đọc sau khi broker khởi động; thay đổi yêu cầu restart hoặc không được phép thay đổi runtime.
- **per-broker:** dynamic update riêng cho một broker.
- **cluster-wide:** dynamic update ở phạm vi cluster.
- **per-broker-cluster-wide:** có cluster default và per-broker override.

Tên và cách diễn giải update mode cần đối chiếu với documentation của release cụ thể. Không suy ra property dynamic chỉ vì `kafka-configs.sh` chấp nhận cú pháp.

### 10.2. Thử trong staging

Trước khi thay config production:

1. Dùng cùng Kafka version và mode metadata.
2. Đọc current config/source.
3. Thay một property có update mode đã xác minh.
4. Quan sát log broker và effective config.
5. Xác minh hành vi thực tế trên topic/request.
6. Thử rollback bằng DELETE hoặc restore old value.

### 10.3. Một số property dễ nhầm

`log.retention.ms` và một số log/topic defaults có thể hỗ trợ dynamic update theo scope được tài liệu quy định. Các property listener, log directory, node identity và JVM thường cần restart. `num.io.threads`/`num.network.threads` có update mode thay đổi theo version; không dùng chúng làm ví dụ dynamic chung nếu chưa kiểm tra config reference.

## 11. Tác động vận hành của một số topic config

### 11.1. `retention.ms` và `retention.bytes`

Retention áp dụng trên log segment, không xóa chính xác từng record tại thời điểm timestamp hết hạn. Segment cần được đóng/đủ điều kiện và retention check chạy theo chu kỳ. Vì vậy dữ liệu có thể tồn tại lâu hơn retention threshold một khoảng thời gian.

Rút ngắn retention có thể làm segment đủ điều kiện xóa, khiến consumer offline lâu hoặc pipeline replay không còn dữ liệu. Trước khi giảm, kiểm tra:

- Consumer group lag và thời gian outage tối đa.
- Kafka Connect source/sink và Kafka Streams restore/replay requirement.
- Mirror/replication pipeline.
- Audit/compliance và backup.
- Disk usage hiện tại và tốc độ ingress.

Tăng retention làm tăng storage requirement. Tính dung lượng theo ingress sau nén, retention và replication factor, cộng headroom.

### 11.2. `cleanup.policy`

- `delete`: xóa segment cũ theo retention time/size.
- `compact`: giữ bản ghi mới nhất theo key qua log compaction; tombstone được dùng để biểu diễn xóa key.
- `compact,delete`: kết hợp compaction với giới hạn retention.

Đổi cleanup policy có thể thay đổi semantics dữ liệu. Topic compacted không phải event archive đầy đủ; các phiên bản cũ của cùng key có thể bị loại sau compaction.

### 11.3. `min.insync.replicas`

`min.insync.replicas` đặt mức ISR tối thiểu cho produce request dùng `acks=all`. Giá trị cao tăng yêu cầu replication trước khi chấp nhận ghi nhưng giảm write availability khi replica lỗi.

Ví dụ RF=3, min ISR=2:

- Khi ISR có 3 replica, produce `acks=all` có thể thành công.
- Khi ISR còn 2 replica, produce vẫn có thể thành công.
- Khi ISR còn 1 replica, produce bị từ chối với lỗi không đủ ISR.

Không giảm min ISR trong incident chỉ để producer gửi được nếu chưa đánh giá durability trade-off và được owner dữ liệu chấp thuận.

### 11.4. `max.message.bytes`

Giới hạn topic cần tương thích với producer request và consumer fetch. Record batch lớn làm tăng memory, network burst và thời gian xử lý. Trước khi tăng, kiểm tra giới hạn ở mọi chặng, compression, retry và downstream parser.

### 11.5. `compression.type`

Topic config có thể định nghĩa codec cuối cùng cho dữ liệu lưu/replicate. Với `compression.type=producer`, broker giữ codec producer đã dùng; nếu đặt codec cụ thể như `lz4` hoặc `zstd`, broker có thể giải nén và nén lại batch theo codec topic. Producer cũng có `compression.type`; đo CPU, byte ingress/egress, storage và consumer decompression trước khi đổi.

## 12. Rollout, rollback và quản lý thay đổi

### 12.1. Trước khi thay đổi

- Xác định property, scope và update mode.
- Ghi lại current value và config source.
- Xác định topic/broker/client chịu tác động.
- Tính storage, availability, throughput và latency impact.
- Xác định rollback value/command.
- Có owner và change window nếu thay đổi rủi ro cao.
- Kiểm tra ACL và quyền quản trị.

### 12.2. Thay đổi dynamic broker config

1. Thử một broker hoặc cluster default theo phạm vi nhỏ nhất phù hợp.
2. Chạy `kafka-configs.sh --alter` hoặc Admin API.
3. Đọc lại config source và value.
4. Kiểm tra broker log/metric và hành vi runtime.
5. Mở rộng phạm vi nếu kết quả đạt yêu cầu.
6. Ghi lại config change và thời gian áp dụng.

Nếu thay đổi cluster default, xác minh broker có per-broker override không; override có thể làm một số node không nhận giá trị mới.

### 12.3. Thay đổi topic config

1. Kiểm tra topic config hiện tại bằng `--describe --all`.
2. Xác định topic owner và consumer/downstream phụ thuộc.
3. Thay một nhóm config liên quan trong cùng change record.
4. Đọc lại effective topic config.
5. Theo dõi disk, retention, ISR, producer error và consumer lag.
6. Đánh giá dữ liệu đã bị xóa hoặc semantics đã thay đổi chưa.

### 12.4. Rollback

Rollback phải quay về đúng lớp cấu hình ban đầu:

- Nếu trước đó có dynamic per-broker override, khôi phục giá trị cũ hoặc DELETE override theo kế hoạch.
- Nếu trước đó dùng cluster default, khôi phục cluster default cũ.
- Nếu topic có override, khôi phục giá trị cũ hoặc DELETE để kế thừa broker default.
- Nếu sửa static file, khôi phục file và rolling restart.

Không dùng DELETE một cách máy móc nếu trước thay đổi đã tồn tại override. Xóa override có thể làm giá trị rơi xuống static/default khác với giá trị ban đầu.

### 12.5. Audit và drift detection

Nên lưu desired config trong Git/IaC và định kỳ so sánh với actual config của cluster. Ghi nhận:

- Resource type và resource name.
- Property name.
- Desired value và actual value.
- Config source.
- Người/automation thực hiện.
- Timestamp, ticket/change ID.
- Kết quả xác minh và rollback.

Không đưa secret vào Git hoặc log audit ở dạng plaintext. Với config nhạy cảm, chỉ ghi metadata và trạng thái đã được bảo vệ.

## 13. ACL và quyền thay đổi config

Đọc config và thay config là hai quyền khác nhau. Cần cấp quyền tối thiểu theo resource type và operation được Kafka authorizer hỗ trợ.

Người vận hành có thể cần quyền:

- Describe cluster/broker/topic để đọc config.
- Alter configs trên cluster/broker/topic tương ứng để thay đổi.
- Create topic nếu quy trình tạo topic thuộc cùng automation.
- Các quyền quản trị khác theo quy trình của tổ chức.

Không cấp quyền cluster-wide alter config cho mọi application principal. Tách principal ứng dụng khỏi principal vận hành và dùng audit trail cho thay đổi cấu hình.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Sửa `server.properties` nhưng giá trị không đổi | Dynamic override có precedence cao hơn; broker chưa restart | `kafka-configs --describe --all`, kiểm tra config source |
| `kafka-configs --alter` báo config không hợp lệ | Property sai tên, sai scope hoặc không hỗ trợ dynamic update | Đối chiếu broker/topic config reference đúng version |
| Broker không nhận cluster default mới | Có per-broker override | Describe từng broker và xóa override nếu phù hợp |
| Topic không dùng broker default mới | Topic có dynamic override | Describe topic config và kiểm tra source |
| Xóa override nhưng value không về Kafka default | Có static config hoặc cluster default ở lớp kế tiếp | Kiểm tra precedence và config source |
| Topic retention thay đổi nhưng disk chưa giảm | Retention xóa theo segment/cleanup cycle; consumer/segment còn active | Kiểm tra segment age, log cleaner và retention check |
| Producer bắt đầu lỗi sau khi tăng min ISR | ISR thấp hơn ngưỡng mới | Kiểm tra RF, ISR và replica health |
| Producer gửi message lớn bị lỗi | Producer/broker/topic/consumer limits không tương thích | Kiểm tra `max.request.size`, `max.message.bytes`, fetch limits |
| Cluster default áp dụng không đồng đều | Per-broker overrides hoặc broker version/config khác nhau | So sánh effective config từng broker |
| Dynamic config mất sau migration | Migration metadata/cluster identity không đúng hoặc quy trình import chưa hoàn tất | Kiểm tra metadata và migration runbook; không sửa trực tiếp metadata |
| Không đủ quyền alter config | ACL thiếu quyền ở đúng resource scope | Kiểm tra principal và authorizer audit log |

Khi điều tra, lưu output `--describe --all`, broker version, command đã chạy và broker log liên quan. Không chia sẻ credential hoặc secret config trong ticket.

## 15. Anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Nghĩ mọi broker config đều dynamic | Thay đổi không áp dụng hoặc CLI từ chối | Kiểm tra update mode từng property |
| Chỉ sửa file nhưng không restart | Process vẫn dùng giá trị đã load | Rolling restart nếu property static |
| Đặt cluster default mà quên per-broker override | Một số broker không nhận giá trị mới | Audit effective config trên mọi broker |
| Xóa override mà không lưu giá trị cũ | Broker/topic kế thừa giá trị khác ngoài dự kiến | Ghi current config/source trước change |
| Dùng topic override thay cho broker policy chung | Nhiều topic drift, khó quản trị | Đặt broker default trước, override chỉ khi có lý do |
| Rút ngắn retention để giải phóng disk ngay | Consumer/replay có thể mất dữ liệu | Tính recovery window và xác minh owner dữ liệu |
| Giảm min ISR khi replication lỗi | Producer có thể ghi với durability thấp hơn | Khôi phục replica trước hoặc chấp thuận trade-off có kiểm soát |
| Tăng max message bytes đồng loạt | Tăng memory/network và rủi ro OOM/latency | Chỉ tăng topic cần thiết, tune toàn đường đi |
| Chỉnh dynamic config trực tiếp ngoài IaC | Desired/actual drift, khó audit | Quản lý qua change pipeline và reconcile |
| Sửa ZooKeeper/KRaft metadata bằng tay | Có thể làm hỏng cluster metadata | Dùng Kafka CLI/Admin API |
| Coi topic config thay đổi có hiệu lực xóa dữ liệu ngay | Hiểu sai retention/compaction timing | Theo dõi segment và cleaner behavior |

## 16. Checklist production

- Đã xác định Kafka version và config reference tương ứng.
- Đã biết property có update mode nào và hỗ trợ scope nào.
- Static config được quản lý trong file/IaC và có rolling restart plan.
- Dynamic cluster default và per-broker override được phân biệt rõ.
- Topic override chỉ được dùng khi topic cần semantics khác broker default.
- Có output `--describe --all` trước và sau thay đổi.
- Đã kiểm tra config source và precedence.
- Đã lưu current value, desired value và rollback command.
- ACL chỉ cấp cho principal vận hành có trách nhiệm.
- Thay retention có đánh giá consumer lag, replay, audit và disk capacity.
- Thay min ISR có đánh giá RF, ISR và producer `acks`.
- Thay max message bytes có đánh giá producer/broker/consumer limits.
- Có monitoring sau thay đổi: request latency, error rate, ISR, disk và consumer freshness.
- Có audit log/change ID và drift detection.
- Không sửa trực tiếp KRaft metadata log hoặc ZooKeeper znodes.
- Có staging validation cho thay đổi rủi ro cao.

## 17. Câu hỏi tự kiểm tra

1. Static broker config, dynamic broker config và topic config khác nhau ở scope nào?
2. Khi nào phải restart broker để thay đổi config?
3. Dynamic cluster default và per-broker override khác nhau thế nào?
4. Thứ tự precedence của broker config gồm những lớp nào?
5. Vì sao xóa dynamic override không nhất thiết trả về Kafka default?
6. Topic override ảnh hưởng broker default và topic khác như thế nào?
7. Dùng lệnh nào để đọc config source và giá trị hiệu lực?
8. Vì sao không nên sửa trực tiếp KRaft metadata hoặc ZooKeeper znodes?
9. `retention.ms` thay đổi có xóa segment ngay lập tức không?
10. `cleanup.policy=compact` khác `delete` như thế nào?
11. `min.insync.replicas` kết hợp với `acks=all` ảnh hưởng write availability ra sao?
12. Vì sao tăng `max.message.bytes` cần kiểm tra cả producer và consumer?
13. Khi nào nên dùng `incrementalAlterConfigs()`?
14. Cần ghi lại thông tin gì trước khi thay đổi config production?
15. Làm thế nào phát hiện broker config drift?

## 18. Tài liệu tham khảo

- Apache Kafka — [Broker Configs](https://kafka.apache.org/documentation/#brokerconfigs)
- Apache Kafka — [Topic Configs](https://kafka.apache.org/documentation/#topicconfigs)
- Apache Kafka — [Dynamic Broker Configuration](https://kafka.apache.org/documentation/#dynamicbrokerconfigs)
- Apache Kafka — [kafka-configs.sh](https://kafka.apache.org/documentation/#operations_basic_kafka_operations)
- Apache Kafka Java API — [Admin](https://kafka.apache.org/documentation/#adminapi)
- Apache Kafka Java API — [IncrementalAlterConfigs](https://kafka.apache.org/documentation/#adminapi_incrementalalterconfigs)

## Kết luận

Kafka có ba lớp cấu hình cần quản lý riêng: static broker config trong file khởi động, dynamic broker config ở phạm vi cluster hoặc broker và topic-level override cho từng log. Giá trị hiệu lực phụ thuộc precedence và update mode của từng property. Static property cần rolling restart; dynamic property chỉ thay đổi nóng khi Kafka version hỗ trợ; topic override không tác động broker default. Dùng `kafka-configs.sh` hoặc Admin API để thay đổi, `--describe --all` để kiểm tra config source, và lưu old value/rollback/audit trước mỗi thay đổi. Đặc biệt, thay retention, cleanup policy, min ISR hoặc message size có thể tác động trực tiếp đến dữ liệu, durability và availability nên phải được đánh giá cùng consumer, producer và downstream.
