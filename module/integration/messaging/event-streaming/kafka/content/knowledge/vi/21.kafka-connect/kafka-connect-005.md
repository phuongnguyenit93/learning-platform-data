# Các topic nội bộ lưu cấu hình, offset và trạng thái

## Kafka Connect Distributed cần lưu trạng thái ở Kafka

Kafka Connect có hai chế độ chạy phổ biến: **standalone** và **distributed**. Standalone worker thường lưu cấu hình/offset theo cơ chế file và phù hợp với tác vụ đơn giản hoặc thử nghiệm. Distributed worker phối hợp thành một cluster, có thể chạy trên nhiều máy và tự phân công connector/task khi worker tham gia hoặc rời đi.

Để nhiều worker cùng khôi phục và quản lý một cluster, Kafka Connect Distributed lưu metadata vận hành trong ba topic nội bộ:

- **Config topic** (`config.storage.topic`): lưu cấu hình connector và task.
- **Offset topic** (`offset.storage.topic`): lưu source offset do source connector ghi nhận.
- **Status topic** (`status.storage.topic`): lưu trạng thái connector, task và worker.

Ba topic này không phải topic event nghiệp vụ. Chúng là nền tảng để cluster Connect khôi phục cấu hình, tiếp tục source connector từ vị trí đã lưu và theo dõi trạng thái sau khi worker restart. Cấu hình sai partition, replication hoặc cleanup policy có thể khiến cluster không khởi động đúng, mất khả năng phục hồi hoặc làm connector chạy lại từ vị trí không mong muốn.

## 1. Vai trò của ba topic nội bộ

### 1.1 Config topic: cấu hình connector và task

Config topic được khai báo bằng `config.storage.topic`. Kafka Connect lưu cấu hình connector và cấu hình task vào đây để mọi worker trong cùng cluster có thể đọc cùng một trạng thái cấu hình.

Config topic phải có **đúng một partition**. Thứ tự cập nhật cấu hình là quan trọng: các worker cần nhìn thấy cùng một chuỗi thay đổi cấu hình theo thứ tự nhất quán. Vì vậy, không tăng partition count của config topic và không dùng topic này cho dữ liệu nghiệp vụ.

Topic này cần bật log compaction. Khi cấu hình connector được cập nhật, giá trị mới thay thế trạng thái cũ theo key; compaction giữ lại giá trị mới nhất cho mỗi key và dọn các phiên bản cũ theo chu kỳ.

### 1.2 Offset topic: vị trí đọc của source connector

Offset topic được khai báo bằng `offset.storage.topic`. Nó lưu offset do **source connector** ghi nhận khi đọc dữ liệu từ hệ thống bên ngoài rồi publish record vào Kafka.

Ví dụ source connector đọc bảng `orders` từ database. Sau khi phát các thay đổi tương ứng vào Kafka, connector lưu vị trí đã đọc như log sequence, binlog position, timestamp hoặc khóa phân vùng nguồn tùy connector. Khi task được khởi động lại hoặc chuyển sang worker khác, Connect có thể lấy source offset từ topic này để tiếp tục.

Offset topic có nhiều partition để phân tán các key offset của nhiều connector/source partition. Topic này cũng cần log compaction để giữ trạng thái offset mới nhất cho mỗi key.

**Lưu ý về sink connector:** sink connector đọc dữ liệu từ Kafka topic. Tiến độ consumer của sink connector được quản lý như Kafka consumer group và lưu trong `__consumer_offsets` theo `group.id`; `offset.storage.topic` chủ yếu lưu source offset của source connector. Không nhầm hai loại offset này.

### 1.3 Status topic: trạng thái connector và task

Status topic được khai báo bằng `status.storage.topic`. Nó lưu trạng thái vận hành như connector đang chạy, bị pause, task được khởi tạo, task thất bại hoặc worker sở hữu task.

Các worker sử dụng trạng thái này để quan sát và phối hợp quản lý connector/task trong cluster. Status topic thường có nhiều partition để phân phối dữ liệu và cũng cần log compaction để giữ trạng thái mới nhất theo key.

Status topic giúp Connect khôi phục trạng thái điều phối, nhưng không thay thế hệ thống monitoring. Vẫn cần theo dõi REST API, log worker, metric task, lỗi connector và trạng thái partition/replica của topic nội bộ.

### 1.4 Bảng so sánh

| Topic | Worker property | Dữ liệu lưu | Partition | Cleanup policy |
|---|---|---|---:|---|
| Config | `config.storage.topic` | Cấu hình connector/task | Chính xác 1 | `compact` |
| Offset | `offset.storage.topic` | Source offset của connector | Nhiều partition | `compact` |
| Status | `status.storage.topic` | Trạng thái connector/task/worker | Nhiều partition | `compact` |

Cả ba topic nên được replication đủ mạnh để chịu lỗi broker. Môi trường production thường dùng replication factor 3 khi cluster có đủ broker, đồng thời cân nhắc `min.insync.replicas` phù hợp với chính sách durability.

## 2. Vì sao các topic nội bộ phải dùng log compaction?

### 2.1 Chúng lưu trạng thái mới nhất, không phải lịch sử event

Config, source offset và status là dữ liệu dạng key-value thể hiện trạng thái hiện tại. Ví dụ một connector có thể được cập nhật cấu hình nhiều lần; Connect cần giá trị cấu hình mới nhất để khôi phục, không cần phát lại mọi phiên bản cũ như một event stream nghiệp vụ.

Log compaction giữ lại record mới nhất theo key sau khi compaction chạy. Các record cũ có thể còn tồn tại tạm thời cho đến khi cleaner xử lý segment. Vì vậy, compaction không xóa record ngay lập tức và cũng không bảo đảm log chỉ có đúng một record cho mỗi key tại mọi thời điểm.

### 2.2 Tombstone biểu thị việc xóa key

Trong compacted topic, record có key và value `null` được gọi là tombstone. Tombstone đánh dấu key đã bị xóa và được giữ trong một khoảng thời gian theo `delete.retention.ms`, sau đó có thể bị loại bỏ khi compaction dọn log.

Kafka Connect dùng semantics key-value và tombstone để quản lý việc cập nhật/xóa trạng thái. Không tự gửi record vào topic nội bộ hoặc xóa tombstone thủ công; việc đó có thể làm worker khôi phục trạng thái sai.

### 2.3 Không dùng `delete` làm cleanup policy duy nhất

Nếu config/offset/status topic chỉ dùng `cleanup.policy=delete`, Kafka có thể xóa các segment cũ theo retention mà không giữ lại đầy đủ trạng thái mới nhất của key. Worker mới khởi động có thể không khôi phục được cấu hình hoặc offset cần thiết.

Đối với các topic nội bộ này, cleanup policy phải có `compact`. Thông thường dùng `cleanup.policy=compact`; không tự thêm `delete` nếu chưa hiểu rõ tác động đến dữ liệu trạng thái và yêu cầu của phiên bản Connect.

## 3. Partition count và replication factor

### 3.1 Config topic chỉ có một partition

Config topic phải có một partition để giữ thứ tự cập nhật cấu hình. Nếu topic đã được tạo với nhiều partition, không chỉ đơn giản sửa `config.storage.topic` trong worker để tiếp tục sử dụng; cần tạo một cluster/topic nội bộ đúng chuẩn và thực hiện migration theo quy trình hỗ trợ.

Không tăng partition count của config topic sau khi đã sử dụng. Đây là yêu cầu cấu trúc, không phải tham số tuning thông thường.

### 3.2 Offset topic có nhiều partition

Offset topic cần nhiều partition để phân phối offset của các source connector. Số partition được cấu hình bằng `offset.storage.partitions` khi worker tự tạo topic hoặc được đặt trước khi khởi động cluster.

Hãy chọn số partition dựa trên số lượng connector/source partition, throughput cập nhật offset và khả năng broker. Quan trọng hơn, **không thay đổi partition count của offset topic sau khi đã có dữ liệu**. Kafka phân phối key vào partition dựa trên hash và số partition; khi số partition thay đổi, key có thể ánh xạ sang partition khác, khiến Connect không tìm thấy offset cũ và có thể khởi động source connector từ vị trí sai hoặc mặc định.

Nếu cần tăng capacity, hãy đánh giá quy trình migration sang một bộ internal topic mới theo hướng dẫn của phiên bản Kafka Connect, sao lưu/đối chiếu source offsets và thử nghiệm phục hồi trước khi chuyển production.

### 3.3 Status topic cũng có nhiều partition

Status topic có nhiều partition để phân phối trạng thái của connector/task. Số partition được cấu hình bằng `status.storage.partitions`. Chọn số partition phù hợp với quy mô cluster và số lượng task; không dùng nó thay thế config topic một partition.

Tránh thay đổi partition count của bất kỳ internal topic nào tùy tiện sau khi Connect đã hoạt động. Với status topic, hãy kiểm tra yêu cầu và hành vi của phiên bản đang chạy trước khi thay đổi; ưu tiên lập kế hoạch từ lúc tạo cluster.

### 3.4 Replication factor

Mỗi topic nội bộ nên có replication factor đủ để chịu lỗi broker. Một cấu hình phổ biến trong production là RF=3 nếu cluster có ít nhất ba broker. Có thể đặt `min.insync.replicas=2` khi RF=3 để yêu cầu tối thiểu hai replica trong ISR cho các ghi cần `acks=all`.

Replication factor không được lớn hơn số broker có thể nhận replica. Nếu cluster chỉ có hai broker mà cấu hình RF=3, việc tạo topic có thể thất bại hoặc topic không đạt trạng thái mong muốn. Không nên dùng RF=1 cho dữ liệu trạng thái quan trọng trong production nếu cần khả năng chịu lỗi broker.

## 4. Cấu hình worker Distributed

### 4.1 Ba topic nội bộ phải thống nhất giữa các worker

Các worker thuộc cùng một Connect cluster phải dùng cùng:

- `group.id`
- `config.storage.topic`
- `offset.storage.topic`
- `status.storage.topic`

Ví dụ cấu hình worker:

```properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092

# Tất cả worker trong cùng Connect cluster dùng chung group ID
group.id=connect-prod-a

# Ba topic nội bộ của cluster này
config.storage.topic=connect-prod-a-configs
offset.storage.topic=connect-prod-a-offsets
status.storage.topic=connect-prod-a-status

# Replication cho các topic nội bộ
config.storage.replication.factor=3
offset.storage.replication.factor=3
status.storage.replication.factor=3

# Partition count cho offset và status topic
offset.storage.partitions=25
status.storage.partitions=5

key.converter=org.apache.kafka.connect.json.JsonConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
key.converter.schemas.enable=false
value.converter.schemas.enable=false
plugin.path=/opt/kafka/plugins
```

Các giá trị `25` và `5` là ví dụ cấu hình, không phải yêu cầu cố định cho mọi cluster. Hãy chọn số partition theo quy mô và phiên bản triển khai. Mọi worker trong cùng cluster phải dùng bộ giá trị giống nhau.

### 4.2 Không chia sẻ internal topics giữa các Connect cluster

Hai Connect cluster độc lập không được dùng chung config/offset/status topic. Nếu dùng chung, trạng thái connector/task và source offset có thể xung đột hoặc worker ở cluster này đọc trạng thái của cluster kia.

Mỗi cluster nên có group ID và ba topic nội bộ riêng, ví dụ:

| Cluster | `group.id` | Config topic | Offset topic | Status topic |
|---|---|---|---|---|
| Production A | `connect-prod-a` | `connect-prod-a-configs` | `connect-prod-a-offsets` | `connect-prod-a-status` |
| Production B | `connect-prod-b` | `connect-prod-b-configs` | `connect-prod-b-offsets` | `connect-prod-b-status` |
| Staging | `connect-staging` | `connect-staging-configs` | `connect-staging-offsets` | `connect-staging-status` |

Không chỉ đổi `group.id` mà vẫn giữ nguyên ba topic. Bộ internal topic là một phần identity và trạng thái bền vững của Connect cluster.

### 4.3 Mọi worker phải tương thích cấu hình

Khi thêm worker mới, kiểm tra bootstrap servers, group ID, tên internal topic, converter, plugin path và các thuộc tính bảo mật. Nếu một worker dùng topic khác hoặc cấu hình converter/plugin không tương thích, connector có thể không được khôi phục đúng hoặc task có thể fail khi được chuyển sang worker đó.

Đường dẫn `plugin.path` cần chứa cùng bộ plugin/connector version phù hợp trên mọi worker. Internal topics lưu cấu hình connector, nhưng không lưu binary plugin; worker mới vẫn phải cài plugin tương ứng.

## 5. Tạo trước các internal topic

Trong production, nên tạo trước ba topic để kiểm soát partition count, replication factor và cleanup policy. Cách này giúp phát hiện sai cấu hình trước khi worker khởi động.

Ví dụ cluster có ít nhất ba broker, RF=3, min ISR=2:

```bash
# Config topic: bắt buộc đúng một partition
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create --topic connect-prod-a-configs \
  --partitions 1 --replication-factor 3 \
  --config cleanup.policy=compact \
  --config min.insync.replicas=2

# Offset topic: nhiều partition, compacted
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create --topic connect-prod-a-offsets \
  --partitions 25 --replication-factor 3 \
  --config cleanup.policy=compact \
  --config min.insync.replicas=2

# Status topic: nhiều partition, compacted
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create --topic connect-prod-a-status \
  --partitions 5 --replication-factor 3 \
  --config cleanup.policy=compact \
  --config min.insync.replicas=2
```

Tên topic và số partition phải khớp với worker properties. Nếu đã tạo trước topic, replication factor và partition count thực tế của topic mới là cấu hình có hiệu lực; các thuộc tính `*.replication.factor` chủ yếu được dùng khi worker tự tạo internal topic.

Nếu cluster không đủ broker, hãy điều chỉnh RF và min ISR theo chính sách durability thực tế. Không sao chép nguyên RF=3 vào môi trường một broker.

### 5.1 Kiểm tra topic sau khi tạo

```bash
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --describe --topic connect-prod-a-configs

kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --describe --topic connect-prod-a-offsets

kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --describe --topic connect-prod-a-status
```

Kiểm tra:

- Config topic có đúng một partition.
- Offset/status topic có đúng số partition đã định cấu hình.
- Replication factor đúng với mục tiêu.
- Mỗi partition có leader và đủ replica trong ISR.
- Không có offline partition hoặc under-replicated partition kéo dài.

Kiểm tra cleanup policy bằng config describe:

```bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name connect-prod-a-configs --describe
```

Lặp lại cho offset và status topic. Cả ba phải có `cleanup.policy=compact`.

## 6. Cách Connect sử dụng internal topics khi vận hành

### 6.1 Khi tạo hoặc cập nhật connector

Khi operator tạo connector qua REST API, Connect worker xác thực cấu hình, lưu cấu hình vào config topic và phối hợp với các worker khác để tạo/reconfigure task. Các worker theo dõi thay đổi cấu hình để hội tụ về trạng thái cluster.

Nếu config topic không khả dụng hoặc không thể ghi, thao tác tạo/cập nhật connector có thể thất bại. Nếu config topic bị mất hoặc cleanup policy sai, cluster có thể không khôi phục đúng cấu hình sau restart.

### 6.2 Khi source connector đọc hệ thống ngoài

Source connector đọc dữ liệu từ hệ thống nguồn và tạo Kafka record. Connector lưu source offset để lần chạy sau tiếp tục từ vị trí đã xử lý. Offset được ghi vào offset topic theo key đại diện cho connector và source partition.

Nếu offset topic bị mất, bị xóa dữ liệu hoặc thay đổi partition count làm key ánh xạ sang partition khác, source connector có thể không tìm được checkpoint cũ. Hành vi tiếp theo tùy connector: có thể đọc lại nhiều dữ liệu, bắt đầu từ vị trí mặc định hoặc cần cấu hình lại offset. Vì vậy, bảo vệ offset topic là yêu cầu quan trọng để tránh duplicate hoặc bỏ sót dữ liệu nguồn.

### 6.3 Khi sink connector ghi ra hệ thống đích

Sink connector đọc Kafka topic và ghi sang database, object store hoặc API. Kafka consumer group lưu tiến độ đọc sink trong `__consumer_offsets`, không phải `offset.storage.topic` của Connect source.

Nếu sink task chuyển worker hoặc restart, nó tiếp tục theo consumer group offset. Side effect ở hệ thống đích vẫn cần idempotency hoặc cơ chế upsert/deduplication vì có thể có record được đọc lại tùy thời điểm commit và lỗi.

### 6.4 Khi worker restart hoặc rời cluster

Các worker trong cùng group chia sẻ trạng thái qua internal topics. Khi một worker dừng, task có thể được phân công lại cho worker khác. Worker mới đọc config và status để biết connector/task cần khôi phục, rồi source connector đọc source offset đã lưu để tiếp tục.

Khả năng phục hồi chỉ tốt khi ba topic nội bộ có replication, ISR và retention/compaction đúng. Nếu broker chứa replica duy nhất của một partition nội bộ bị mất, Connect có thể không truy cập được trạng thái tương ứng.

## 7. Bảo mật và ACL cho internal topics

Connect worker cần quyền đọc/ghi các topic nội bộ và quyền tham gia consumer group. Nếu worker tự tạo topic, nó còn cần quyền tạo topic theo policy cluster. Trong môi trường production, có thể pre-create topic bằng quy trình platform rồi chỉ cấp quyền sử dụng cần thiết cho Connect worker.

Các quyền thường cần xem xét:

- `READ`, `WRITE` và `DESCRIBE` trên config, offset và status topic theo hoạt động của worker.
- `READ`/`WRITE` trên topic nghiệp vụ tùy source/sink connector.
- Quyền group phù hợp với `group.id` của Connect worker và sink connector.
- `CREATE` nếu worker được phép tự tạo internal topic hoặc connector topic.

Quyền cụ thể phụ thuộc authorizer, connector và cách triển khai. Dùng ACL tối thiểu, tách principal cho Connect worker với ứng dụng nghiệp vụ, bật TLS/SASL và không cấp superuser cho worker nếu không cần.

## 8. Monitoring các topic nội bộ

### 8.1 Kafka-level health

Theo dõi cho cả ba topic:

- Partition có leader hay không.
- ISR count và under-replicated partition.
- Offline partition.
- Bytes in/out và log size.
- Request latency, disk usage và broker availability.
- Lỗi authorization hoặc lỗi produce/fetch từ worker.

Offset topic có thể có throughput ghi đều do source connector cập nhật checkpoint. Config topic thường có tốc độ ghi thấp hơn nhưng rất quan trọng khi cập nhật connector. Status topic có thể thay đổi khi task restart, rebalance hoặc chuyển trạng thái.

### 8.2 Connect-level health

Theo dõi REST API của Connect để kiểm tra trạng thái connector/task:

```bash
curl http://connect-1:8083/connectors

curl http://connect-1:8083/connectors/orders-source/status
```

REST API cho biết connector/task đang `RUNNING`, `PAUSED`, `FAILED` hoặc trạng thái tương ứng theo phiên bản. Kết hợp với worker log và metric để phân biệt lỗi connector, lỗi task, lỗi internal topic và lỗi downstream.

### 8.3 Không xóa internal topic để “reset” connector

Xóa config topic, offset topic hoặc status topic không phải cách thông thường để restart connector. Việc này có thể làm mất cấu hình, checkpoint và trạng thái cluster. Muốn reset source offset, dùng cơ chế offset management được connector hỗ trợ hoặc quy trình quản trị cụ thể; muốn xóa connector, dùng REST API hoặc công cụ quản trị Connect.

## 9. Các lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Config topic có nhiều hơn một partition | Vi phạm yêu cầu ordering cấu hình của Connect | Tạo config topic mới với đúng một partition và migrate theo quy trình |
| Internal topic không bật compaction | Trạng thái mới nhất có thể bị xóa theo retention | Đặt `cleanup.policy=compact` |
| Offset topic quá ít partition | Tăng tải lên một số partition, giảm khả năng mở rộng | Chọn partition count phù hợp ngay từ đầu |
| Tăng partition count offset topic sau khi đã dùng | Key có thể ánh xạ sang partition khác, Connect không tìm thấy offset cũ | Không resize trực tiếp; lập kế hoạch migration |
| RF lớn hơn số broker | Topic không tạo được hoặc không đạt replica assignment mong muốn | Chọn RF phù hợp số broker và durability |
| Worker cùng cluster dùng topic/group khác nhau | Worker không chia sẻ trạng thái đúng cách | Đồng bộ group ID và ba topic trên mọi worker |
| Hai Connect cluster dùng chung internal topic | Trạng thái và offset có thể xung đột | Dùng bộ topic riêng cho từng cluster |
| Xóa internal topic để reset | Mất cấu hình, offset hoặc trạng thái | Dùng REST/API offset management phù hợp |
| Sink offset bị nhầm với source offset | Reset sai topic, khó phục hồi consumer | Sink dùng `__consumer_offsets`; source dùng offset storage topic |
| Worker mới thiếu plugin | Task fail khi được chuyển sang worker mới | Đồng bộ plugin/version trên mọi worker |

## 10. Quy trình triển khai cluster Connect mới

1. Xác định một cluster Connect độc lập và cấp `group.id` riêng.
2. Đặt tên riêng cho config, offset và status topic của cluster.
3. Chọn partition count: config đúng 1; offset/status theo quy mô và workload.
4. Chọn replication factor theo số broker và durability target.
5. Tạo trước ba topic với `cleanup.policy=compact` và min ISR phù hợp.
6. Describe topic để xác minh partition, replica, ISR và cleanup policy.
7. Cấu hình mọi worker dùng cùng group ID và ba topic.
8. Đồng bộ plugin, converter, TLS/SASL và ACL trên tất cả worker.
9. Khởi động worker, kiểm tra REST API và log để xác nhận cluster hình thành.
10. Tạo connector thử nghiệm, restart một worker và xác minh connector/task phục hồi.
11. Kiểm tra source offset tiếp tục đúng vị trí; kiểm tra sink consumer group offset riêng.
12. Thiết lập alert cho internal topic health và connector/task failure.

## 11. Checklist production

- Mỗi Connect cluster có `group.id` và ba internal topic riêng.
- Config topic có đúng một partition.
- Offset/status topic có partition count phù hợp và được chốt trước khi chạy production.
- Cả ba topic dùng `cleanup.policy=compact`.
- Replication factor và `min.insync.replicas` đáp ứng mục tiêu chịu lỗi.
- Mọi partition có leader và ISR khỏe mạnh.
- Worker properties nhất quán trên mọi worker.
- Không thay đổi partition count của config/offset topic sau khi đã có dữ liệu.
- Plugin và converter tương thích trên tất cả worker.
- ACL tối thiểu cho internal topic, group và topic nghiệp vụ.
- Source offset được bảo vệ; sink group offset được giám sát trong `__consumer_offsets`.
- Có backup/quy trình phục hồi cấu hình connector và source offset phù hợp.
- Đã thử nghiệm worker restart, broker failover và task reassignment.

## Kết luận

Kafka Connect Distributed dùng ba topic nội bộ để chia sẻ trạng thái giữa các worker: config topic lưu cấu hình connector/task, offset topic lưu source offset và status topic lưu trạng thái connector/task/worker. Cả ba cần log compaction và replication phù hợp. Config topic phải có đúng một partition; offset topic có nhiều partition nhưng không nên thay đổi partition count sau khi đã sử dụng vì key offset có thể ánh xạ sang partition khác.

Khi triển khai KAFKA Connect, hãy tạo bộ internal topic riêng cho từng cluster, chốt partition/replication từ đầu, đồng bộ worker properties, kiểm tra ACL và giám sát ISR. Cần phân biệt source offset trong Connect offset topic với sink consumer offset trong `__consumer_offsets`. Bảo vệ đúng ba topic nội bộ là điều kiện để cluster khôi phục cấu hình, tiếp tục source connector và điều phối task ổn định sau restart hoặc broker failure.
