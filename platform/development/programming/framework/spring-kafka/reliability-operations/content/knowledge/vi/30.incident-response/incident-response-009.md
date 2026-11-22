# Khoanh vùng theo topic và partition

Khi một hệ thống Spring Kafka gặp sự cố, câu hỏi “consumer có lag không?” thường chưa đủ để xác định nguyên nhân. Một consumer group có thể chỉ chậm ở một partition, toàn bộ partition của một topic có thể cùng tăng lag, hoặc nhiều consumer group cùng bị ảnh hưởng bởi một topic. Mỗi trường hợp gợi ý một vùng lỗi khác nhau.

Khoanh vùng theo topic và partition giúp đội vận hành thu hẹp sự cố từ một triệu chứng tổng quát thành một tập hợp cụ thể gồm cluster, topic, consumer group, partition, offset và instance đang xử lý. Đây là đơn vị điều tra quan trọng trong Kafka vì partition là nơi lưu trữ thứ tự message, được gán cho consumer và có leader chịu trách nhiệm đọc/ghi.

Mục tiêu của incident response là xác định phạm vi ảnh hưởng, thu thập bằng chứng trước khi thay đổi trạng thái, tìm điểm nghẽn, sau đó khôi phục có kiểm soát và xác nhận rằng dữ liệu đã được xử lý đúng.

## 1. Các khái niệm cần nắm khi điều tra

Một topic được chia thành nhiều partition. Mỗi partition là một log có thứ tự riêng và có thể được đặt trên các broker khác nhau. Kafka không tạo ra một thứ tự toàn cục giữa các partition của cùng topic. Nếu producer gửi record với key, Kafka thường dùng key để chọn partition, nhờ đó các record cùng key thường đi vào cùng partition và giữ thứ tự trong phạm vi partition đó.

Các khái niệm sau xuất hiện thường xuyên trong quá trình khoanh vùng:

| Thành phần | Ý nghĩa khi điều tra |
|---|---|
| Topic | Luồng dữ liệu logic, ví dụ `orders.created` hoặc `payments.completed` |
| Partition | Một log có thứ tự riêng; là đơn vị phân phối công việc và theo dõi offset |
| Offset | Vị trí của record trong một partition; không phải số thứ tự toàn cục của topic |
| Leader | Replica đang phục vụ đọc/ghi cho partition theo trạng thái metadata hiện tại |
| Follower | Replica sao chép dữ liệu từ leader |
| ISR | Tập replica đang được xem là đồng bộ với leader theo điều kiện Kafka |
| Consumer group | Nhóm consumer cùng chia sẻ việc đọc topic; mỗi partition được gán cho tối đa một consumer trong cùng group tại một thời điểm |
| Committed offset | Vị trí tiến độ mà consumer group đã commit cho một partition |
| Log end offset | Vị trí cuối log mà broker báo cáo cho partition; cách đo lag còn phụ thuộc trạng thái log và isolation level |
| Consumer lag | Chênh lệch giữa vị trí dữ liệu sẵn có và tiến độ đã commit của group trên từng partition |

Kafka chỉ bảo đảm thứ tự trong một partition. Khi một topic có nhiều partition, không nên so sánh offset giữa partition 0 và partition 1 như thể chúng thuộc cùng một dãy. Khi đọc số liệu lag, luôn giữ nguyên khóa `(cluster, topic, group, partition)`.

Lag thường được hiển thị theo công thức gần đúng:

```text
lag(topic, group, partition)
    = end offset được dùng để giám sát
      - committed offset của consumer group
```

Giá trị end offset dùng để tính lag có thể phụ thuộc công cụ giám sát, trạng thái transaction và cấu hình `isolation.level`. Với consumer dùng `read_committed`, dữ liệu chưa hoàn tất transaction có thể chưa đọc được dù log end offset đã tiến lên. Vì vậy, hãy so sánh số liệu từ cùng một công cụ và hiểu rõ định nghĩa metric trước khi kết luận.

## 2. Bắt đầu bằng việc xác định đúng phạm vi

Trước khi restart pod hoặc tăng số consumer, hãy xác định sự cố thuộc cluster và luồng nào. Một số hệ thống có nhiều môi trường, nhiều Kafka cluster, nhiều topic có tên gần giống nhau và nhiều consumer group dùng chung một topic. Lệnh chạy nhầm cluster có thể tạo ra kết luận sai hoặc thay đổi nhầm dữ liệu.

Ghi lại các thông tin ban đầu:

- Môi trường và Kafka cluster đang được kiểm tra.
- Topic bị ảnh hưởng và các topic phụ thuộc trong cùng luồng nghiệp vụ.
- Consumer group của ứng dụng Spring Kafka.
- Thời điểm bắt đầu, thời điểm cảnh báo và thời điểm deploy gần nhất.
- Triệu chứng người dùng nhìn thấy: dữ liệu đến chậm, thiếu dữ liệu, xử lý lặp, lỗi listener hay lỗi publish.
- Một hoặc nhiều partition có lag, và lag đang tăng, giảm hay đứng yên.

Tên topic và group ID cần lấy từ cấu hình runtime hoặc thông tin triển khai đang chạy. Đừng suy ra group ID chỉ từ tên class listener: `groupId`, `id`, `idIsGroup` và cấu hình mặc định có thể làm group thực tế khác với tên mà người đọc mã nguồn dự đoán.

Với Spring Kafka, hãy đối chiếu cấu hình như `spring.kafka.consumer.group-id`, thuộc tính `groupId` trên `@KafkaListener`, topic được khai báo trong listener và cấu hình environment-specific. Nếu listener dùng topic pattern, cần xác định tập topic thực tế mà pattern đang match.

## 3. Đọc lag theo từng partition

Tổng lag của một group hữu ích cho cảnh báo, nhưng có thể che khuất partition đang gặp vấn đề. Hãy xem lag theo từng partition và quan sát xu hướng qua nhiều thời điểm.

Ví dụ kết quả giả định:

| Topic | Partition | Committed offset | End offset | Lag |
|---|---:|---:|---:|---:|
| `orders.created` | 0 | 12,400 | 12,510 | 110 |
| `orders.created` | 1 | 8,100 | 8,220 | 120 |
| `orders.created` | 2 | 18,000 | 24,500 | 6,500 |
| `orders.created` | 3 | 9,700 | 9,820 | 120 |

Trong ví dụ này, tổng lag là 6,850 nhưng phần lớn nằm ở partition 2. Tăng số consumer có thể không giải quyết được vấn đề nếu partition 2 bị nghẽn bởi một key nóng, một record lỗi hoặc một dependency chỉ ảnh hưởng tới một luồng dữ liệu.

Không kết luận chỉ từ một ảnh chụp số liệu. Hãy ghi lại lag và tốc độ thay đổi theo thời gian:

- Lag tăng đều: tốc độ dữ liệu đến lớn hơn tốc độ xử lý, hoặc consumer không tiến offset.
- Lag giảm: consumer đang bắt kịp dữ liệu.
- Lag đứng yên ở mức cao: consumer có thể đã dừng, bị kẹt, không được gán partition hoặc đang chờ một dependency.
- Lag thấp nhưng lỗi listener tăng: có thể là lỗi từng record hoặc lỗi nghiệp vụ chưa tạo backlog lớn.
- Lag tăng rồi giảm theo từng đợt: có thể là tải burst, retry, rebalance hoặc dependency chập chờn.

Đối chiếu lag với throughput. Nếu end offset tăng nhanh còn committed offset gần như không đổi, consumer đang không theo kịp hoặc không commit tiến độ. Nếu cả hai cùng đứng yên, có thể producer không gửi dữ liệu, topic đang idle hoặc consumer không nhận dữ liệu mới. Nếu committed offset tăng nhưng lag vẫn tăng, consumer có làm việc nhưng năng lực xử lý thấp hơn tốc độ đầu vào.

## 4. Dùng Kafka CLI để xem topic, group và partition

Các lệnh dưới đây minh họa cách kiểm tra bằng script đi kèm Kafka distribution. Tên script có thể có hậu tố `.sh` hoặc `.bat` tùy hệ điều hành; tham số chi tiết thay đổi giữa các phiên bản Kafka. Thay bootstrap server, group và topic bằng giá trị của môi trường đang điều tra.

### Xem trạng thái consumer group

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-projection-v1
```

Kết quả thường có các cột group, topic, partition, current offset, log end offset, lag và consumer ID/host/client ID tùy phiên bản. Hãy tìm partition có lag lớn, partition không có consumer ID hoặc consumer ID thay đổi liên tục.

Xem thành viên và assignment của group nếu phiên bản Kafka hỗ trợ:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-projection-v1 \
  --members \
  --verbose
```

Thông tin này giúp xác định partition đang được giao cho consumer instance nào. Nếu group có trạng thái `Empty`, không có member hoạt động. Nếu group liên tục chuyển trạng thái hoặc assignment thay đổi, cần kiểm tra rebalance, heartbeat, session timeout và lỗi kết nối.

### Xem metadata của topic

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders.created
```

Kết quả cho biết số partition, replication factor, leader, replica và ISR của từng partition. Hãy chú ý:

- Leader là `-1` hoặc không có leader: partition không có leader khả dụng tại thời điểm kiểm tra.
- ISR ít hơn số replica mong đợi: partition có replica chưa theo kịp.
- Một broker liên tục xuất hiện là leader của các partition có vấn đề: kiểm tra sức khỏe broker đó.
- Partition có replica hoặc leader thay đổi bất thường: đối chiếu với sự kiện broker restart, rolling upgrade hoặc reassignment.

### Kiểm tra offset ở mức topic

Một số Kafka distribution có script `kafka-get-offsets.sh` để lấy offset theo partition:

```bash
kafka-get-offsets.sh \
  --bootstrap-server kafka-1:9092 \
  --topic orders.created \
  --time -1
```

Giá trị `-1` thường yêu cầu offset cuối log. Kiểm tra `--help` của đúng phiên bản để biết cách lấy earliest offset hoặc chỉ định partition. Để tính lag, cần ghép offset của cùng partition với committed offset của đúng consumer group. Không lấy offset của group khác hoặc cluster khác để so sánh.

Các lệnh trên là thao tác đọc trạng thái. Chúng không thay thế metric theo thời gian, log của ứng dụng và thông tin broker. Hãy lưu lại output kèm timestamp để có thể so sánh trước và sau khi khôi phục.

## 5. Nhận diện mẫu sự cố từ phân bố partition

Phân bố lỗi giữa partition và giữa consumer group là một tín hiệu định hướng rất mạnh.

| Mẫu quan sát | Hướng điều tra ưu tiên |
|---|---|
| Một partition lag tăng, các partition khác bình thường | Key nóng, record gây lỗi, partition leader/replica, assignment hoặc dependency gắn với nhóm record đó |
| Tất cả partition của một topic cùng tăng lag trong một group | Consumer group thiếu năng lực, listener chậm, dependency chung, retry hoặc rebalance |
| Nhiều group cùng lag trên một topic | Producer burst, broker/topic health, dữ liệu bất thường hoặc vấn đề hạ tầng chung |
| Chỉ một group bị ảnh hưởng, group khác đọc cùng topic bình thường | Logic ứng dụng, cấu hình group, database hoặc dependency riêng của service |
| Nhiều topic khác nhau cùng chậm trên một cluster | Broker, network, storage, controller hoặc tài nguyên cluster |
| Một consumer instance có nhiều partition chậm | Instance đó có thể thiếu CPU, memory, thread, network hoặc đang bị block |
| Lag thấp nhưng một số record liên tục lỗi | Poison message, schema incompatibility, lỗi validation hoặc lỗi nghiệp vụ |

Các mẫu này là giả thuyết ban đầu, không phải kết luận. Ví dụ, nhiều group cùng chậm có thể do một dependency bên ngoài được tất cả service dùng chung. Hãy kiểm tra metric và log để xác nhận.

### Chỉ một partition có lag cao

Kiểm tra lần lượt:

1. Partition có leader và ISR khỏe mạnh không?
2. Partition có được gán cho consumer đang hoạt động không?
3. Consumer được gán có lag hoặc lỗi tương tự ở partition khác không?
4. Tốc độ record đến partition này có cao bất thường không?
5. Một key có chiếm phần lớn record không?
6. Log listener có lặp lại cùng event ID, offset hoặc exception không?
7. Có một dependency hoặc dữ liệu nghiệp vụ chỉ xuất hiện trong partition này không?

Nếu chỉ một partition có lag cao và consumer liên tục retry cùng một record, hãy điều tra poison message trước khi scale group. Nếu record đó luôn thất bại do schema hoặc dữ liệu không hợp lệ, thêm consumer chỉ khiến nhiều tài nguyên chờ cùng partition hoặc làm tăng áp lực lên dependency.

### Tất cả partition của một topic cùng lag

Nếu leader và ISR khỏe, kiểm tra tốc độ xử lý listener, thời gian database query, connection pool, thread pool, CPU, garbage collection và network của toàn bộ instance. Đối chiếu thời điểm deploy để tìm thay đổi về concurrency, batch size, retry/backoff, serialization hoặc logic xử lý.

Nếu nhiều group cùng bị ảnh hưởng, kiểm tra broker và producer. Một producer có thể đột ngột tăng throughput, gửi record lớn hơn, thay đổi key distribution hoặc phát lại dữ liệu lịch sử.

## 6. Kiểm tra leader, replica và sức khỏe broker

Một partition chỉ có thể phục vụ hoạt động bình thường khi có leader khả dụng. Replica follower sao chép dữ liệu từ leader và ISR phản ánh tập replica đáp ứng điều kiện đồng bộ của Kafka. Khi broker chậm, mất kết nối hoặc storage gặp vấn đề, một số partition có thể bị ảnh hưởng rõ rệt hơn những partition khác.

Khi thấy partition có leader bất thường hoặc ISR co lại:

- Xác định broker đang giữ leader và các replica của partition.
- Kiểm tra broker log, thời gian restart, network, disk latency, dung lượng và file descriptor.
- Kiểm tra metric request latency, produce/fetch request rate, under-replicated partitions và offline partitions.
- Đối chiếu controller log hoặc sự kiện cluster nếu nhiều leader cùng thay đổi.
- Xác định sự cố nằm ở broker, network giữa broker hay tải từ client.

`UnderReplicatedPartitions` tăng cho thấy replica chưa theo kịp leader. `OfflinePartitionsCount` lớn hơn 0 cho thấy có partition không có leader khả dụng. Tên metric và cách expose phụ thuộc phiên bản Kafka và hệ thống giám sát, nhưng hai tín hiệu này cần được xem cùng trạng thái ISR và leader của từng partition.

Không bật unclean leader election chỉ để làm partition có leader trở lại nếu chưa hiểu nguy cơ mất dữ liệu. Unclean election có thể chọn replica không nằm trong ISR và làm mất các record chưa được replica đó nhận. Nếu cần reassignment hoặc thay đổi replication, hãy theo quy trình vận hành cluster và đánh giá tác động trước.

## 7. Kiểm tra consumer assignment, rebalance và năng lực xử lý

Trong một consumer group, một partition chỉ được gán cho tối đa một consumer tại một thời điểm. Một group có 12 partition và 20 consumer instance thì tối đa 12 instance có thể nhận partition; số instance còn lại sẽ idle đối với group đó. Ngược lại, nếu có ít consumer hơn partition, mỗi consumer có thể xử lý nhiều partition.

Kiểm tra:

- Số partition của topic và số consumer member đang hoạt động.
- Partition nào được gán cho từng consumer ID/host.
- Consumer instance có restart, mất heartbeat hoặc rời group liên tục không.
- Thời gian xử lý một record và số record xử lý mỗi giây.
- Listener có bị block bởi I/O đồng bộ, database lock hoặc thread pool cạn không.
- Có exception lặp khiến retry/backoff giữ partition không tiến offset không.

Rebalance liên tục có thể khiến consumer tạm ngừng nhận record trong khi partition được thu hồi và gán lại. Hãy kiểm tra log `Revoking`, `Assigned`, heartbeat/session timeout, thời gian xử lý dài và thay đổi số member. Với Spring Kafka, xem cấu hình concurrency của listener, `max.poll.interval.ms`, `session.timeout.ms`, `heartbeat.interval.ms` và các thiết lập poll liên quan. Không tăng timeout một cách máy móc: trước hết cần xác định listener chậm vì xử lý nghiệp vụ hay bị treo.

`concurrency` của `@KafkaListener` tạo số consumer container/thread theo cấu hình. Nó không làm một partition được xử lý song song bởi nhiều consumer trong cùng group. Nếu topic có 4 partition, tăng concurrency từ 4 lên 12 không tạo thêm khả năng song song cho một partition đang nóng; phần concurrency vượt số partition có thể không được sử dụng.

## 8. Tìm hot partition và key skew

Producer thường chọn partition dựa trên key để giữ thứ tự cho cùng một thực thể nghiệp vụ, chẳng hạn `orderId` hoặc `accountId`. Nếu một key xuất hiện với tần suất vượt trội, phần lớn record có thể dồn vào một partition. Các partition khác rảnh trong khi partition nóng tích lũy lag.

Hãy so sánh theo partition:

- Record rate và byte rate.
- Kích thước record trung bình và phân bố kích thước.
- Tỷ lệ key lặp lại hoặc top key theo cửa sổ thời gian.
- Thời gian xử lý theo loại event hoặc nhóm key.
- Producer instance và thay đổi partitioner/configuration gần thời điểm sự cố.

Không log toàn bộ payload để tìm hot key nếu payload có dữ liệu nhạy cảm. Có thể dùng metric có giới hạn cardinality, sampling hoặc công cụ phân tích dữ liệu được phê duyệt. Tránh tạo metric label theo từng event ID hoặc từng key tùy ý vì cardinality cao có thể làm hệ thống giám sát quá tải.

Nếu key nóng là một thực thể cần bảo đảm thứ tự, không thể đơn giản chia các record của key đó sang nhiều partition mà vẫn giữ cùng bảo đảm thứ tự. Cần xem lại mô hình nghiệp vụ: có thể tuần tự hóa riêng thực thể nóng, giảm số lần cập nhật, gom batch, dùng một luồng xử lý chuyên biệt hoặc thay đổi cách phân chia dữ liệu khi quy tắc nghiệp vụ cho phép.

Tăng số partition có thể tăng khả năng song song cho các key phân bố tốt, nhưng không bảo đảm chia nhỏ một key đang nóng. Khi số partition thay đổi, phép ánh xạ key sang partition có thể thay đổi đối với record mới; record cũ vẫn nằm ở partition trước. Điều này có thể làm thay đổi thứ tự quan sát giữa các record của cùng key trong giai đoạn chuyển tiếp. Chỉ tăng partition sau khi đánh giá semantics, consumer group, retention, quota và kế hoạch migration.

## 9. Khoanh vùng poison message và lỗi xử lý ở Spring Kafka

Một record lỗi lặp lại có thể làm partition không tiến offset nếu error handler retry record đó theo chính sách hiện tại. Các partition khác vẫn hoạt động bình thường, khiến sự cố trông giống hot partition.

Trong log ứng dụng, đối chiếu:

- Topic, partition và offset của record lỗi.
- Event ID hoặc business key nếu có thể ghi log an toàn.
- Exception class, root cause và stack trace đầu tiên.
- Số lần delivery/retry và thời gian backoff.
- Thời điểm lỗi bắt đầu so với deploy, schema change hoặc thay đổi dữ liệu.
- Consumer instance và listener ID đang xử lý record.

Spring Kafka có thể dùng `DefaultErrorHandler` cùng `BackOff` để retry; cấu hình cụ thể quyết định exception nào được retry, số lần thử và cách xử lý khi hết retry. Nếu dùng `DeadLetterPublishingRecoverer`, record có thể được gửi tới dead-letter topic sau khi phục hồi thất bại. Cần kiểm tra cấu hình thực tế thay vì giả định mọi exception đều được gửi DLT.

Một ví dụ cấu hình minh họa:

```java
@Configuration
public class KafkaErrorHandlingConfig {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            DeadLetterPublishingRecoverer recoverer) {

        var backOff = new FixedBackOff(1_000L, 2L);
        var handler = new DefaultErrorHandler(recoverer, backOff);

        // Chỉ đánh dấu các lỗi dữ liệu đã xác định là không thể retry.
        handler.addNotRetryableExceptions(InvalidOrderEventException.class);
        return handler;
    }
}
```

Ví dụ trên chỉ minh họa cấu trúc; bean recoverer, serializer, DLT topic, quyền ghi và chính sách retry cần được cấu hình theo ứng dụng. Không đưa lỗi hạ tầng tạm thời như database unavailable vào danh sách non-retryable nếu hệ thống kỳ vọng phục hồi bằng retry.

Khi chuyển record sang DLT, cần giữ metadata đủ để điều tra, bao gồm topic nguồn, partition, offset, exception và timestamp theo cấu hình recoverer. DLT cũng là một topic có partition và consumer riêng; cần giám sát lag, retention và quy trình replay của nó.

Không tự ý bỏ qua record chỉ vì nó đang làm partition bị kẹt. Bỏ qua có thể làm mất một thay đổi nghiệp vụ. Trước khi skip hoặc replay, xác định tác động, sửa dữ liệu hoặc code, và lưu lại event/offset cần xử lý.

## 10. Quan sát bằng metric và log của Spring Kafka

Điều tra hiệu quả cần kết hợp ba lớp dữ liệu: metric Kafka client/broker, metric listener của ứng dụng và log có định danh message.

### Metric Kafka consumer

Các metric thường hữu ích gồm:

- `records-lag-max` và metric lag theo partition nếu được expose: mức lag lớn nhất mà consumer quan sát.
- `records-consumed-rate`: tốc độ consumer đọc record.
- `bytes-consumed-rate`: tốc độ byte được đọc.
- `fetch-latency-avg` và `fetch-rate`: độ trễ và tần suất fetch.
- `commit-latency-avg` và `commit-rate`: độ trễ và tần suất commit offset.
- `assigned-partitions`: số partition đang được consumer nắm giữ, nếu hệ thống metric cung cấp.

Tên metric, tag và mức chi tiết theo partition phụ thuộc Kafka client version, Micrometer registry và cấu hình export. Hãy kiểm tra metric thực tế trước khi xây dashboard hoặc alert. Không nên chỉ dùng `records-lag-max` của một consumer để đại diện cho toàn bộ group nếu có nhiều member.

### Metric ứng dụng và dependency

Đối chiếu thời gian xử lý listener với:

- Database connection pool: active, idle, pending và timeout.
- Database query latency, lock wait và transaction rollback.
- HTTP client latency, timeout và error rate.
- Thread pool queue, CPU, heap, garbage collection và container throttling.
- Retry count, DLT publish failure và số listener exception.

Nếu lag tăng cùng lúc database connection pool chạm giới hạn, điểm nghẽn có thể nằm ở database hoặc số lượng consumer tạo quá nhiều truy vấn đồng thời. Nếu listener duration tăng nhưng dependency bình thường, xem lại code, lock nội bộ, serialization và batch processing.

### Log có đủ ngữ cảnh

Log xử lý message nên có `topic`, `partition`, `offset`, `consumer group` hoặc listener ID, `clientId`/instance và event ID khi có. Đưa các giá trị này vào MDC hoặc log structured fields giúp truy vấn một partition xuyên suốt nhiều instance.

Không dùng event ID, order ID hoặc key không giới hạn làm label của metric. Những giá trị có cardinality lớn phù hợp hơn với log hoặc trace có kiểm soát. Với log, tránh ghi payload, token, thông tin cá nhân hoặc dữ liệu thanh toán không cần thiết.

## 11. Cô lập partition có kiểm soát trong Spring Kafka

Trong một số tình huống, cần tạm dừng việc nhận thêm record từ một partition để bảo vệ dependency hoặc chờ xử lý record lỗi. Spring Kafka cung cấp API pause/resume ở listener container trong các phiên bản hỗ trợ.

Ví dụ minh họa:

```java
@Component
@RequiredArgsConstructor
public class PartitionControl {

    private final KafkaListenerEndpointRegistry registry;

    public void pauseOrdersPartition(int partition) {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container == null) {
            throw new IllegalStateException("Listener container not found");
        }

        container.pausePartition(
            new TopicPartition("orders.created", partition)
        );
    }

    public void resumeOrdersPartition(int partition) {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container == null) {
            throw new IllegalStateException("Listener container not found");
        }

        container.resumePartition(
            new TopicPartition("orders.created", partition)
        );
    }
}
```

Listener cần có ID tương ứng, ví dụ `@KafkaListener(id = "orders-listener", topics = "orders.created")`. API cụ thể và hành vi pause partition cần được kiểm tra theo phiên bản Spring Kafka đang dùng. Pause là yêu cầu điều khiển container; nó không xóa record, không commit offset thay cho ứng dụng và không sửa dữ liệu lỗi. Partition có thể tiếp tục tích lũy lag trong thời gian tạm dừng.

Trước khi pause, xác định partition hiện được container quản lý, mục tiêu và thời hạn tạm dừng. Sau khi khắc phục nguyên nhân, resume và theo dõi tốc độ bắt kịp. Với listener concurrency lớn, hãy xác nhận container nào đang giữ partition và API điều khiển có tác động đúng assignment hiện tại.

Không dùng pause như biện pháp chữa cháy mặc định cho mọi lag. Nếu toàn bộ group đang chậm vì database, pause một partition có thể làm backlog tập trung hơn và kéo dài thời gian khôi phục.

## 12. Quy trình incident response theo từng bước

Một quy trình nhất quán giúp nhiều người cùng điều tra mà không vô tình làm thay đổi bằng chứng hoặc tạo thêm rủi ro.

### Bước 1: Xác nhận cluster, topic và group

Lấy tên cluster, topic, consumer group, môi trường và thời điểm bắt đầu. Xác minh ứng dụng đang kết nối đúng bootstrap server và đúng cấu hình runtime. Ghi lại phiên bản Kafka client, broker và Spring Kafka nếu sự cố có liên quan tới thay đổi phiên bản.

### Bước 2: Chụp trạng thái ban đầu

Lưu output `kafka-consumer-groups --describe`, `kafka-topics --describe`, metric lag theo partition, danh sách member và log lỗi. Ghi timestamp, deploy version và số lượng replica ứng dụng. Đây là baseline để so sánh sau khi xử lý.

### Bước 3: Xác định hình dạng ảnh hưởng

Phân loại sự cố: một partition, một topic, một group, nhiều group hay toàn cluster. So sánh lag, end offset, committed offset, record rate và consumer assignment. Đừng gộp số liệu từ các partition thành một kết luận duy nhất.

### Bước 4: Chọn nhánh điều tra

- Một partition: kiểm tra leader/ISR, key skew, poison message và consumer được gán.
- Mọi partition của một topic: kiểm tra năng lực group, dependency chung và producer throughput.
- Nhiều group trên cùng topic: kiểm tra producer, broker, schema và dữ liệu nguồn.
- Nhiều topic trên cùng cluster: kiểm tra broker, controller, network, disk và cluster capacity.

### Bước 5: Đề xuất thay đổi nhỏ nhất có thể kiểm chứng

Ví dụ: rollback phiên bản gây lỗi, khôi phục database dependency, sửa schema mapping, đưa record không hợp lệ sang DLT theo quy trình hoặc điều chỉnh consumer capacity khi đã chứng minh thiếu năng lực. Nêu rõ thay đổi tác động tới topic, group và partition nào.

### Bước 6: Theo dõi phục hồi

Sau thay đổi, quan sát lag từng partition, tốc độ end offset/committed offset, retry, DLT, lỗi listener, rebalance và độ trễ nghiệp vụ. Xác nhận lag đang giảm và không có partition mới bắt đầu tăng bất thường. Một dashboard tổng lag giảm chưa đủ nếu partition quan trọng vẫn bị kẹt.

### Bước 7: Ghi lại kết quả

Ghi nguyên nhân gốc, partition bị ảnh hưởng, khoảng thời gian, event/offset liên quan, thay đổi đã thực hiện, số liệu trước/sau và hành động phòng ngừa. Nếu chưa xác định được nguyên nhân gốc, ghi rõ giả thuyết còn mở và bằng chứng còn thiếu.

## 13. Những thao tác cần đánh giá kỹ trước khi thực hiện

Một số thao tác có thể thay đổi tiến độ đọc hoặc semantics của luồng dữ liệu. Chỉ thực hiện khi có kế hoạch, người chịu trách nhiệm và khả năng xác minh kết quả.

### Reset consumer offset

`kafka-consumer-groups --reset-offsets` có thể đưa group về earliest, latest, timestamp hoặc offset cụ thể tùy phiên bản. Đây là thao tác có thể khiến ứng dụng bỏ qua dữ liệu hoặc xử lý lại dữ liệu cũ. Thông thường group phải không có consumer hoạt động khi reset.

Trước khi reset:

1. Lưu committed offset hiện tại của từng partition.
2. Xác định chính xác partition cần thay đổi và offset đích.
3. Ước lượng số record sẽ bị bỏ qua hoặc phát lại.
4. Kiểm tra tính idempotent của consumer và tác động tới side effect.
5. Dùng chế độ dry-run nếu phiên bản hỗ trợ, rồi review kết quả.
6. Thực hiện trong cửa sổ đã thống nhất và xác minh offset sau thao tác.

Không dùng `--to-latest` chỉ để làm dashboard hết đỏ. Nó có thể bỏ qua toàn bộ backlog chưa xử lý. Reset về earliest có thể phát lại lượng lớn event, gây tải database hoặc lặp side effect nếu consumer không idempotent.

### Tăng partition hoặc thay đổi key

Tăng partition có thể giúp phân phối nhiều key hơn, nhưng thay đổi ánh xạ key và có thể ảnh hưởng thứ tự trong giai đoạn chuyển tiếp. Cần đánh giá consumer group, downstream, retention, quota, replication và kế hoạch xử lý record đang tồn tại trước khi thay đổi.

### Tăng consumer concurrency hoặc số pod

Scale chỉ có ích khi có partition chưa được khai thác và dependency còn năng lực. Nếu một partition nóng là điểm nghẽn, tăng pod không làm partition đó được nhiều consumer xử lý đồng thời trong cùng group. Scale quá mức có thể làm database quá tải và khiến incident lan rộng.

### Reassign replica hoặc thay đổi cấu hình broker

Reassignment có thể tiêu tốn network và disk I/O trong thời gian dài. Thay đổi replication, leader election hoặc cấu hình broker cần được thực hiện theo quy trình quản trị Kafka cluster. Không dùng unclean election hoặc xóa dữ liệu log như một thao tác thử nghiệm trong incident.

## 14. Ví dụ điều tra một partition bị nghẽn

Giả sử alert báo consumer group `order-projection-v1` có lag tăng. Lệnh describe cho thấy partition 0, 1 và 3 có lag thấp, trong khi partition 2 tăng từ vài trăm lên hàng chục nghìn record. Group có đủ member và partition 2 được gán cho một consumer đang hoạt động.

Tiếp theo, metadata topic cho thấy partition 2 có leader và ISR bình thường. Broker không có offline partition hay under-replicated partition. Consumer log cho thấy cùng một offset của partition 2 liên tục phát sinh `InvalidOrderEventException`; các partition khác xử lý bình thường.

Đội vận hành xác định đây là lỗi dữ liệu của một event, không phải thiếu consumer capacity. Họ kiểm tra payload trong công cụ được phê duyệt, xác nhận trường bắt buộc bị thiếu do producer vừa deploy schema mới, sau đó phối hợp sửa hợp đồng dữ liệu. Theo chính sách đã thống nhất, record lỗi được chuyển sang DLT kèm metadata nguồn và offset; consumer tiếp tục xử lý các record còn lại. Sau khi producer được sửa, nhóm replay record đã hiệu chỉnh theo quy trình idempotent.

Kết quả được xác nhận bằng việc lag partition 2 giảm, committed offset tiến đều, DLT có bản ghi được theo dõi và không có duplicate nghiệp vụ. Nếu chỉ scale thêm pod ngay từ đầu, partition 2 vẫn chỉ được một consumer trong group xử lý và lỗi dữ liệu vẫn tồn tại.

## 15. Checklist bàn giao khi incident chưa kết thúc

Khi cần chuyển ca hoặc bàn giao cho đội Kafka/platform, ghi đủ thông tin để người tiếp nhận không phải điều tra lại từ đầu:

- Cluster, môi trường, topic và consumer group chính xác.
- Partition bị ảnh hưởng và consumer instance đang được gán.
- Committed offset, end offset và lag tại thời điểm bàn giao.
- Xu hướng lag và throughput trong khoảng thời gian quan sát.
- Leader, replica và ISR của partition liên quan.
- Consumer member, rebalance và restart gần nhất.
- Exception, event ID/offset và retry/DLT status nếu có.
- Dependency metric như database, HTTP client, thread pool và tài nguyên pod.
- Các thay đổi đã thực hiện, người thực hiện và kết quả đo được.
- Giả thuyết còn mở, rủi ro và bước tiếp theo có người chịu trách nhiệm.

Khoanh vùng theo topic và partition tạo ra một đường điều tra có thể kiểm chứng: bắt đầu từ phạm vi cluster và luồng nghiệp vụ, xem tiến độ từng partition, đối chiếu assignment và broker health, rồi liên hệ lag với lỗi listener, key distribution và dependency. Khi mọi kết luận đều gắn với topic, partition, offset và timestamp cụ thể, đội vận hành có thể khôi phục chính xác hơn và tránh những thao tác làm mất dữ liệu hoặc thay đổi thứ tự xử lý ngoài dự kiến.
