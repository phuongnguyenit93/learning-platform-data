# Checklist thiết kế topic

Topic là hợp đồng lưu trữ và phân phối event giữa producer với các consumer group. Một topic được thiết kế tốt cần trả lời rõ dữ liệu nào được ghi vào, ai sở hữu dữ liệu, record được phân vùng theo khóa nào, cần giữ bao lâu, mức độ bền vững ra sao và cách xử lý khi consumer không theo kịp.

Checklist này dùng khi tạo topic mới hoặc review topic trước khi đưa một luồng Spring Kafka vào production. Các con số cấu hình phải được xác nhận bằng tải thực tế, dung lượng broker và yêu cầu nghiệp vụ; không có một số partition hay retention phù hợp cho mọi hệ thống.

## 1. Xác định mục đích và ranh giới của topic

Trước khi chọn partition hoặc retention, hãy mô tả vai trò của topic:

- Topic chứa event đã xảy ra, command yêu cầu một hành động, hay snapshot trạng thái?
- Một topic có đại diện cho một event family/domain stream rõ ràng không?
- Producer nào được phép ghi và consumer group nào cần đọc?
- Các consumer có cần cùng schema và cùng chính sách lưu trữ không?
- Có cần tách dữ liệu theo mức độ nhạy cảm, tenant hoặc vòng đời lưu trữ không?

Tránh tạo topic theo từng message, từng request hoặc từng consumer. Nhiều consumer group có thể đọc cùng một topic độc lập với offset riêng; không cần nhân bản topic chỉ vì có nhiều ứng dụng cùng quan tâm một event.

Tách topic khi các luồng có khác biệt thực chất về schema, quyền truy cập, retention, tải, thứ tự hoặc vòng đời. Nếu chỉ khác cách xử lý, một topic với nhiều consumer group thường dễ quản lý hơn.

## 2. Đặt tên topic nhất quán

Tên topic nên cho biết domain, loại dữ liệu và version của contract. Ví dụ:

| Tên | Mục đích |
| --- | --- |
| `orders.events.v1` | Event nghiệp vụ về đơn hàng |
| `payments.commands.v1` | Command yêu cầu xử lý thanh toán |
| `inventory.snapshot.v1` | Snapshot trạng thái tồn kho |
| `orders.events.retry-1000` | Retry topic có delay theo chính sách đã chọn |
| `orders.events.dlt` | Dead-letter topic của luồng orders |

Quy ước cần thống nhất:

- Dùng chữ thường và một kiểu phân cách nhất quán, chẳng hạn dấu chấm hoặc dấu gạch ngang.
- Tránh tên mơ hồ như `data`, `events`, `topic1` hoặc tên gắn với một implementation tạm thời.
- Không nhúng thông tin dễ thay đổi như hostname, pod ID hoặc ngày triển khai vào tên topic.
- Đặt tên retry/DLT theo topic nguồn và có thể truy ngược về luồng gốc.
- Kiểm tra giới hạn và quy ước tên của nền tảng Kafka đang vận hành.

Một số hệ thống metrics chuẩn hóa dấu chấm và dấu gạch dưới theo cách có thể gây trùng tên metric. Vì vậy, chọn quy ước dễ quan sát và kiểm tra cách exporter hiển thị tên topic.

## 3. Chốt event contract trước khi tạo topic

Topic chỉ là nơi lưu byte; producer và consumer vẫn cần thống nhất ý nghĩa của key, header và value. Một event envelope thường có các trường:

| Trường | Vai trò |
| --- | --- |
| `eventId` | Định danh ổn định để deduplicate và truy vết |
| `eventType` | Loại event, ví dụ `OrderPaid` |
| `schemaVersion` | Phiên bản cấu trúc payload |
| `aggregateId` | Định danh entity cần giữ thứ tự |
| `occurredAt` | Thời điểm nghiệp vụ xảy ra |
| `correlationId` | Liên kết các bước trong một luồng nghiệp vụ |
| `payload` | Dữ liệu nghiệp vụ của event |

Chọn JSON, Avro, Protobuf hoặc định dạng khác theo hệ sinh thái. Nếu dùng Schema Registry, xác định compatibility mode và quy trình đăng ký schema trước khi producer phát payload mới. Thay đổi schema cần được kiểm thử với consumer đang chạy phiên bản cũ.

Không dùng Kafka header để thay thế các trường nghiệp vụ mà consumer cần lưu trữ lâu dài. Header phù hợp cho metadata vận chuyển như trace context, nguồn replay hoặc thông tin DLT.

## 4. Chọn message key và chiến lược partition

Key quyết định record được định tuyến vào partition nào theo partitioner. Nếu các event của cùng một aggregate cần được đọc theo thứ tự, thường dùng ID ổn định của aggregate làm key:

```java
kafkaTemplate.send(
    "orders.events.v1",
    event.orderId(),
    event);
```

Với key `orderId`, các event của cùng đơn hàng được đưa vào cùng partition khi partition count và partitioner không thay đổi. Kafka duy trì thứ tự record trong một partition; Kafka không tạo thứ tự tổng thể giữa nhiều partition.

Checklist về key:

- Key có đại diện cho đơn vị cần giữ thứ tự, ví dụ `orderId`, `accountId` hoặc `deviceId` không?
- Phân bố key có đều không, hay một key nóng có thể làm một partition quá tải?
- Các event không có key có thực sự chấp nhận phân phối không gắn với aggregate không?
- Consumer có cần xử lý tuần tự theo key hoặc có thể xử lý song song?
- Có kiểm thử phân bố partition bằng dữ liệu gần thực tế không?

Tăng số partition có thể làm thay đổi kết quả hash-to-partition đối với key ở các lần publish sau. Các event cũ của một key có thể nằm ở partition cũ trong khi event mới đi vào partition khác. Nếu thứ tự theo aggregate là yêu cầu nghiêm ngặt, phải xem partition count là quyết định dài hạn và có kế hoạch migration/repartition riêng.

## 5. Ước lượng số partition

Số partition ảnh hưởng trực tiếp đến khả năng song song, số consumer hữu ích trong một group, phân bố tải và chi phí vận hành. Bắt đầu từ throughput mục tiêu và throughput an toàn đã đo được trên một partition:

\[P_{base} = \left\lceil \frac{R_{target}}{R_{partition}} \right\rceil\]

Trong đó `R_target` là số record/giây cần xử lý và `R_partition` là throughput/partition đã xác nhận qua load test với kích thước record, replication, consumer logic và broker tương tự production. Sau đó cộng headroom cho burst, tăng trưởng và rebalance.

Ví dụ, nếu tải mục tiêu là 1.200 record/giây và thử nghiệm cho thấy một partition xử lý ổn định 300 record/giây, mức cơ sở là 4 partition. Nếu cần khoảng 50% headroom, có thể đánh giá 6 partition rồi xác nhận lại bằng test. Đây là điểm khởi đầu, không phải con số mặc định.

Kiểm tra thêm:

- Số consumer/concurrency tối đa mà một group có thể tận dụng: không vượt số partition được assign.
- Tổng số partition trên cluster và giới hạn vận hành của broker.
- Thời gian rebalance, chi phí file segment, open file và metadata.
- Khả năng mở rộng consumer độc lập với producer.
- Mức độ skew giữa các key và partition.

Không tạo hàng trăm partition chỉ để dự phòng khi chưa có số liệu. Quá nhiều partition làm tăng chi phí metadata, file, recovery và vận hành, kể cả khi throughput không tăng tương ứng.

## 6. Chọn replication và durability

Replication factor (RF) xác định số bản sao partition. Với production cần chịu lỗi broker, thường đánh giá RF=3 và đặt replica trên các broker/rack/availability zone khác nhau. Môi trường local hoặc test một broker thường dùng RF=1.

Một cấu hình durability thường gặp:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
```

Và cấu hình topic/broker tương ứng:

```bash
kafka-topics.sh --bootstrap-server kafka.example.com:9092 \
  --create --topic orders.events.v1 \
  --partitions 6 --replication-factor 3

kafka-configs.sh --bootstrap-server kafka.example.com:9092 \
  --entity-type topics --entity-name orders.events.v1 \
  --alter --add-config min.insync.replicas=2,unclean.leader.election.enable=false
```

Replication factor được chọn khi tạo topic bằng `--replication-factor` (hoặc qua cấu hình provisioning tương đương); `min.insync.replicas` là cấu hình topic. `unclean.leader.election.enable` có thể được quản lý ở cấp broker hoặc topic tùy phiên bản và chính sách cluster.

`acks=all` yêu cầu leader chờ các replica hiện nằm trong ISR xác nhận; nó không có nghĩa mọi replica đã cấu hình đều phải phản hồi. `min.insync.replicas=2` đặt ngưỡng ISR tối thiểu để broker chấp nhận write với `acks=all`. Nếu ISR thấp hơn ngưỡng, producer nhận lỗi thay vì chấp nhận một write có durability thấp hơn chính sách.

Idempotent producer giảm duplicate do retry ở tầng producer trong các điều kiện Kafka hỗ trợ. Nó không thay thế idempotency của nghiệp vụ khi consumer gọi database hoặc HTTP service.

Checklist durability:

- RF có phù hợp với số broker và yêu cầu chịu lỗi không?
- Replica có được phân bố qua rack/AZ theo failure domain không?
- `min.insync.replicas` có tương thích với `acks` của producer không?
- Có theo dõi under-replicated partition và ISR shrink không?
- Có quy trình xử lý khi broker mất và khi ISR thấp hơn ngưỡng không?

## 7. Chọn retention và cleanup policy

Retention phải xuất phát từ nhu cầu replay, điều tra, tuân thủ và dung lượng lưu trữ. Hai cleanup policy thường gặp là:

| Policy | Dùng khi |
| --- | --- |
| `delete` | Cần giữ event history trong một khoảng thời gian rồi xóa segment cũ |
| `compact` | Cần giữ giá trị mới nhất theo key, phù hợp changelog hoặc state topic |
| `compact,delete` | Cần compaction theo key nhưng vẫn giới hạn tuổi dữ liệu |

Ví dụ cấu hình topic event history:

```properties
cleanup.policy=delete
retention.ms=604800000
segment.bytes=1073741824
```

Ví dụ trên giữ dữ liệu theo chính sách bảy ngày. Với compacted topic, record cùng key cũ có thể bị loại sau compaction; tombstone dùng để biểu diễn xóa key và có thời hạn lưu riêng. Không dùng compaction nếu consumer cần replay toàn bộ lịch sử event.

Ước lượng dung lượng thô:

\[Storage \approx IngressBytesPerSecond \times RetentionSeconds \times ReplicationFactor\]

Ví dụ, 100 record/giây, kích thước trung bình 1 KiB và retention bảy ngày tạo khoảng 57,7 GiB dữ liệu trên một bản sao trước khi tính compression và overhead; RF=3 cần xấp xỉ 173 GiB tổng dung lượng replica. Thực tế còn phụ thuộc segment, index, compaction, compression, burst và headroom đĩa.

`retention.bytes` được áp dụng theo partition, không phải một giới hạn tổng duy nhất cho cả topic. Khi cấu hình theo byte, cần nhân với số partition để ước lượng dung lượng tổng.

## 8. Giới hạn kích thước record và compression

Record lớn có thể làm tăng latency, bộ nhớ và thời gian fetch. Trước khi tăng giới hạn, hãy kiểm tra payload có thể chia nhỏ hoặc lưu object ngoài Kafka rồi chỉ gửi reference hay không.

Các giới hạn liên quan cần thống nhất:

- `max.message.bytes` ở topic/broker.
- `max.request.size` ở producer.
- `max.partition.fetch.bytes` và `fetch.max.bytes` ở consumer.
- Giới hạn serializer, Schema Registry hoặc gateway trung gian nếu có.

Chọn compression phù hợp với dữ liệu và CPU: `lz4` hoặc `zstd` thường được đánh giá cho cân bằng throughput/ratio; `gzip` có thể nén mạnh hơn nhưng tốn CPU hơn. Load test bằng payload thực tế vì dữ liệu đã nén hoặc mã hóa có thể không giảm kích thước nhiều.

## 9. Thiết kế retry topic và DLT cùng topic nguồn

Nếu consumer có retry hoặc dead-letter recovery, hãy đưa các topic phụ trợ vào thiết kế ban đầu:

- Retry topic có tên, delay level, partition và retention rõ ràng.
- DLT có retention đủ dài để điều tra và replay có kiểm soát.
- ACL cho consumer, retry publisher và DLT operator được tách theo nhiệm vụ.
- Số partition của retry/DLT tương thích với destination resolver nếu cần giữ partition nguồn.
- Có dashboard cho retry rate, DLT rate và tuổi record cũ nhất.
- Replay có idempotency và quy trình ngăn vòng lặp lỗi vô hạn.

Non-blocking retry có thể làm event mới hơn được xử lý trước event đang chờ retry. Nếu nghiệp vụ cần thứ tự nghiêm ngặt theo aggregate, cân nhắc blocking retry hoặc cơ chế version/sequence để phát hiện event đến sai thứ tự.

## 10. Bảo mật và quyền truy cập

Thiết kế ACL cùng lúc với topic, không đợi đến khi ứng dụng gặp `TopicAuthorizationException` mới cấp quyền:

| Principal | Quyền tối thiểu thường cần |
| --- | --- |
| Producer của topic | `WRITE` trên topic; quyền mô tả nếu client/flow cần |
| Consumer principal | `READ` trên topic và `READ` trên group ID mà consumer tham gia |
| Retry publisher/recoverer | Quyền ghi vào retry/DLT topic tương ứng |
| DLT operator | Quyền đọc DLT; quyền replay chỉ cấp khi cần |
| Topic provisioning | Quyền tạo/cấu hình topic qua principal quản trị riêng |

Dùng SASL/TLS phù hợp với broker, lưu credential trong secret manager và tránh dùng principal quản trị cho runtime service. Prefix ACL chỉ nên dùng khi mọi topic có cùng tiền tố thuộc một ranh giới tin cậy.

## 11. Quản lý topic như hạ tầng có version

Topic production nên được provision có kiểm soát bằng IaC, Kafka Admin workflow hoặc quy trình triển khai riêng. Không phụ thuộc vào auto topic creation của broker trong production vì typo ở tên topic có thể tạo topic ngoài ý muốn với cấu hình mặc định.

Mỗi topic cần có owner chịu trách nhiệm về schema, partition, retention, ACL, quota và xử lý sự cố. Lưu cấu hình mong muốn trong source of truth của hạ tầng; kiểm tra drift giữa cấu hình mong muốn và cấu hình broker thực tế.

Các thay đổi như tăng partition, đổi cleanup policy, rút ngắn retention hoặc đổi key contract cần review như thay đổi API. Giảm partition không phải thao tác đơn giản; thường cần tạo topic mới và migrate dữ liệu/consumer.

## 12. Monitoring và cảnh báo trước production

Tối thiểu cần theo dõi:

- Ingress record/byte rate và request latency.
- Consumer group lag tổng và lag theo partition.
- Under-replicated/offline partition, ISR size và broker disk usage.
- Produce/fetch error, request timeout và quota throttle.
- Retry, recovery, DLT rate và tuổi DLT record.
- Partition skew, key nóng và phân bố tải giữa consumer.
- Retention headroom và tốc độ tăng dung lượng.

Đặt cảnh báo theo xu hướng và ngưỡng gắn với SLO. Ví dụ, lag tăng liên tục trong khi consumer processing rate thấp hơn ingress rate là tín hiệu backlog đang tích tụ; under-replicated partition kéo dài là rủi ro durability.

## 13. Ví dụ review thiết kế topic orders.events.v1

Giả sử hệ thống phát event đơn hàng, cần giữ thứ tự trong từng đơn hàng, có thể replay bảy ngày và chịu lỗi một broker:

| Thuộc tính | Quyết định minh họa | Lý do cần xác nhận |
| --- | --- | --- |
| Topic | `orders.events.v1` | Event contract theo domain và version |
| Key | `orderId` | Giữ event của cùng đơn hàng trên một partition |
| Partitions | 6 | Từ tải mục tiêu, benchmark và headroom; cần kiểm tra skew |
| Replication factor | 3 | Phân bố replica qua failure domain |
| `min.insync.replicas` | 2 | Cho phép write khi còn ít nhất hai ISR với `acks=all` |
| Producer | `acks=all`, idempotence bật | Tăng độ bền và tránh duplicate ở producer retry |
| Cleanup | `delete` | Cần lưu event history để replay |
| Retention | 7 ngày | Theo nhu cầu replay và dung lượng thực tế |
| Compression | `lz4` hoặc `zstd` sau benchmark | Cân bằng CPU, network và disk |
| Security | Producer WRITE; consumer READ topic/group | Least privilege theo principal |
| Operations | Lag, ISR, disk, throughput, DLT | Phát hiện backlog và rủi ro broker |

Các giá trị trên là ví dụ review. Trước khi áp dụng, phải thay bằng throughput benchmark, kích thước event, số broker, dung lượng khả dụng, failure domain và SLO thực tế.

## 14. Checklist trước khi tạo topic

Dùng checklist sau trong buổi review thiết kế và lưu quyết định cùng cấu hình hạ tầng:

- [ ] Mục đích topic, producer, consumer group và owner đã được xác định.
- [ ] Tên topic tuân thủ quy ước domain/event/version.
- [ ] Event schema, key, header và compatibility policy đã được thống nhất.
- [ ] Key giữ đúng thứ tự nghiệp vụ; rủi ro hot partition đã được đánh giá.
- [ ] Partition count dựa trên throughput benchmark, concurrency và headroom.
- [ ] Ảnh hưởng của tăng partition lên key ordering đã được chấp nhận.
- [ ] Replication factor, rack/AZ placement, `acks` và `min.insync.replicas` tương thích.
- [ ] Retention/compaction đáp ứng replay, compliance và dung lượng.
- [ ] Storage được ước lượng theo ingress, retention, replication và compression.
- [ ] Message size và giới hạn producer/broker/consumer đã được kiểm tra.
- [ ] Retry topic, DLT, retention và quy trình replay đã được thiết kế.
- [ ] ACL cho producer, consumer, retry, DLT và provisioning đã được xác định.
- [ ] Topic được tạo bằng IaC/quy trình có kiểm soát; auto-create được xem xét.
- [ ] Dashboard, alert, owner và runbook xử lý sự cố đã sẵn sàng.
- [ ] Load test, schema compatibility test và failure test đã có kết quả.

Chỉ tạo topic sau khi các quyết định về contract, key, partition, durability, retention, security và vận hành đã được review. Topic là một phần của API messaging lâu dài; thay đổi partition, key hoặc cleanup policy sau khi có dữ liệu production có thể ảnh hưởng consumer, thứ tự và khả năng replay.
