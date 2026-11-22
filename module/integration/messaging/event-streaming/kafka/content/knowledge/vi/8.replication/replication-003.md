# Cơ chế follower fetch và độ trễ nhân bản

## Mục tiêu bài học

Kafka sao chép dữ liệu của một partition từ leader sang các follower replica. Các follower chủ động gửi fetch request đến leader để lấy record mới, append chúng vào log cục bộ và cập nhật tiến độ nhân bản. Hiểu luồng follower fetch giúp giải thích ISR, high watermark, độ trễ replica và lý do một producer dùng `acks=all` đôi khi phải chờ lâu hoặc bị từ chối ghi.

Sau bài học, bạn có thể:

- Mô tả vòng đời một fetch request từ follower đến partition leader.
- Phân biệt log end offset (LEO), high watermark (HW) và replica lag.
- Giải thích cách follower bắt kịp leader và điều kiện duy trì ISR.
- Nhận diện tác động của follower chậm đến `acks=all`, `min.insync.replicas` và khả năng ghi.
- Hiểu các tham số fetch replication và cân nhắc điều chỉnh chúng.
- Quan sát trạng thái replica bằng CLI, broker metrics và log.
- Khoanh vùng nguyên nhân lag do mạng, disk, CPU, cấu hình hoặc tải không cân bằng.

## 1. Mô hình leader và follower của một partition

Mỗi partition có một replica leader và có thể có nhiều follower replica. Producer gửi record đến leader của partition; follower không nhận write trực tiếp từ producer mà sao chép record từ leader.

Ví dụ topic `orders` có replication factor bằng 3:

```text
Topic: orders, Partition: 0

Broker 1                 Broker 2                 Broker 3
LEADER                   FOLLOWER                 FOLLOWER
LEO = 120                LEO = 118                LEO = 120
   |                         ^                        ^
   |------ records ----------|------------------------|
             follower fetch
```

LEO là vị trí kế tiếp sẽ được ghi trong log. Ví dụ LEO=120 có nghĩa các offset đã append trong log có thể nằm trước vị trí 120; nó không có nghĩa record có offset 120 đã tồn tại. Trong hình, follower ở Broker 2 đang chậm hơn leader hai offset.

Các replica của cùng một partition lưu cùng chuỗi record và cùng offset logic. Việc replica nằm trên nhiều broker giúp partition tiếp tục hoạt động khi một broker gặp sự cố, tùy theo trạng thái ISR và chính sách bầu leader.

## 2. Follower fetch hoạt động như thế nào?

### 2.1. Follower chủ động kéo dữ liệu

Kafka dùng mô hình follower pull: replica follower gửi fetch request đến broker đang giữ leader. Leader trả về các record bắt đầu từ offset mà follower yêu cầu. Follower append record nhận được vào log cục bộ rồi tiếp tục fetch khi cần.

Luồng cơ bản:

```text
Producer                 Leader replica              Follower replica
   |                           |                            |
   |---- Produce records ----->|                            |
   |                           | append to local log         |
   |                           |                            |
   |                           |<---- Fetch(offset=LEO) -----|
   |                           |                            |
   |                           |----- records + HW --------->|
   |                           |                            | append records
   |                           |                            | advance local LEO
   |                           |<---- next Fetch ------------|
```

Follower fetcher chạy ở broker và quản lý việc lấy dữ liệu cho các partition mà broker đó đang giữ replica. Đây là luồng replication nội bộ giữa broker với broker; nó khác với fetch của consumer application.

### 2.2. Fetch offset cho biết follower đã có dữ liệu đến đâu

Follower thường yêu cầu dữ liệu từ log end offset cục bộ của nó. Nếu follower có LEO=118, fetch request tiếp theo sẽ yêu cầu dữ liệu bắt đầu tại offset 118. Leader trả các record còn thiếu từ vị trí đó nếu chúng có sẵn.

Sau khi follower nhận và append record, LEO của follower tăng lên. Ở lần fetch tiếp theo, follower gửi offset mới để leader biết tiến độ mà follower đã đạt được.

Ví dụ:

```text
Thời điểm A:
  Leader LEO   = 125
  Follower LEO = 120
  Follower fetch từ offset 120

Leader trả record ở các offset 120..124

Thời điểm B sau khi append:
  Leader LEO   = 125
  Follower LEO = 125
  Follower đã bắt kịp log tại thời điểm đó
```

Đây là ví dụ đơn giản, giả định không có record mới được append trong lúc follower xử lý response. Trong tải thực tế, leader vẫn có thể tiếp tục nhận record nên follower phải fetch lặp lại để theo kịp.

### 2.3. Fetch request có thể chờ dữ liệu

Follower không nhất thiết phải gửi request cho từng record. Fetch request có thể yêu cầu một lượng dữ liệu tối thiểu và chờ trong một khoảng thời gian tối đa. Cách này giảm số request nhỏ và giúp gom dữ liệu thành batch.

Một số tham số broker liên quan:

| Cấu hình | Vai trò |
|---|---|
| `replica.fetch.min.bytes` | Số byte tối thiểu follower muốn nhận trước khi leader trả response, nếu có thể |
| `replica.fetch.wait.max.ms` | Thời gian tối đa fetch request có thể chờ dữ liệu |
| `replica.fetch.max.bytes` | Giới hạn byte mục tiêu cho dữ liệu fetch theo partition |
| `replica.fetch.response.max.bytes` | Giới hạn tổng kích thước response fetch replication |
| `num.replica.fetchers` | Số thread fetcher dùng để sao chép dữ liệu trên mỗi broker |
| `replica.fetch.backoff.ms` | Thời gian chờ trước khi thử lại sau một số lỗi fetch |

Giá trị mặc định có thể khác theo phiên bản Kafka. Các giới hạn byte thường là mục tiêu/giới hạn batch chứ không phải lúc nào cũng là trần tuyệt đối cho một record batch hợp lệ; Kafka có quy tắc để xử lý batch đầu tiên lớn hơn giới hạn trong một số trường hợp. Cần đối chiếu tài liệu đúng phiên bản trước khi tinh chỉnh.

### 2.4. Fetcher không đồng nghĩa với số partition

Một broker có thể giữ follower replica của nhiều partition. Các replica fetcher thread chia sẻ công việc lấy dữ liệu từ nhiều leader broker. Tăng `num.replica.fetchers` có thể tăng khả năng fetch song song trong một số workload, nhưng cũng tăng số thread, kết nối, bộ nhớ đệm và tải CPU.

Nếu bottleneck là disk write hoặc network bandwidth, tăng fetcher thread không nhất thiết cải thiện lag; thậm chí có thể làm contention nặng hơn. Trước khi tăng thread, cần xác định fetcher thực sự đang bị giới hạn bởi mức song song hay bởi tài nguyên khác.

## 3. LEO, high watermark và replica lag

### 3.1. Log end offset (LEO)

LEO (Log End Offset) là offset kế tiếp mà replica sẽ append vào log. Nếu replica đã append các record có offset từ 0 đến 99, LEO thường là 100.

Mỗi replica có LEO riêng:

- Leader LEO phản ánh vị trí cuối log đã append trên leader.
- Follower LEO phản ánh vị trí cuối log đã append trên follower.
- LEO follower thấp hơn LEO leader cho thấy follower chưa nhận đủ dữ liệu mới nhất của leader.

### 3.2. High watermark (HW)

High watermark là ranh giới commit của partition. Theo cách diễn giải offset phổ biến, các record có offset nhỏ hơn HW đã được xác nhận theo quy tắc replication của Kafka; HW biểu thị offset kế tiếp sau vùng record đã commit.

Ví dụ:

```text
Leader LEO   = 105
Follower A   = 105
Follower B   = 103
High watermark = 103

Offsets < 103: đã qua high watermark
Offsets 103..104: chưa được xác nhận bởi mọi replica trong ISR
```

Trong mô hình đơn giản, leader tính tiến độ commit dựa trên LEO của các replica đang thuộc ISR. Khi follower chậm, HW có thể chưa tiến lên dù leader đã append record mới. Khi các follower trong ISR xác nhận tiến độ, HW mới có thể tăng.

Không nhầm HW với LEO: LEO nói log của một replica đã append đến đâu; HW nói đến ranh giới nào của partition đã được commit theo replication. Consumer ở chế độ đọc thông thường không đọc vượt qua HW; với transaction, `read_committed` còn có ranh giới Last Stable Offset (LSO), có thể thấp hơn HW khi transaction chưa kết thúc.

### 3.3. Replica lag theo offset

Một cách nhìn đơn giản về replica lag là chênh lệch giữa leader LEO và follower LEO:

\[
Lag_{offset} = LEO_{leader} - LEO_{follower}
\]

Ví dụ leader LEO=50.000 và follower LEO=49.700 thì follower đang chậm khoảng 300 offset tại thời điểm quan sát.

Đây là chênh lệch vị trí log, không phải thời gian trễ tính bằng mili giây. Nếu producer phát sinh ít record, 300 offset có thể tương ứng thời gian dài; nếu producer phát sinh hàng chục nghìn record mỗi giây, 300 offset có thể chỉ là một khoảng rất ngắn.

Khoảng cách offset cũng không phải lúc nào bằng chính xác số record nghiệp vụ còn thiếu, vì log có thể có offset gap do control record, transaction hoặc các cơ chế quản lý log khác. Hãy dùng nó như chỉ số khoảng cách vị trí và kết hợp với fetch progress, ISR cùng metric thời gian.

Một số hệ thống giám sát còn đo thời gian kể từ lần fetch thành công cuối, thời gian follower không tiến triển LEO hoặc độ trễ theo timestamp record. Các đại lượng đó khác nhau và không nên gọi chung là “lag” mà không ghi rõ cách tính.

### 3.4. ISR và điều kiện follower còn đồng bộ

ISR (In-Sync Replicas) là tập replica được Kafka xem là đang theo kịp leader theo tiêu chí của hệ thống. ISR có thể bao gồm leader và các follower đủ điều kiện.

Follower có thể có LEO thấp hơn leader trong một khoảng ngắn nhưng vẫn nằm trong ISR khi nó tiếp tục fetch và bắt kịp theo tiêu chí Kafka. Ngược lại, follower ngừng fetch quá lâu hoặc không tiến triển phù hợp có thể bị loại khỏi ISR. `replica.lag.time.max.ms` là broker configuration quan trọng liên quan đến thời gian follower có thể tụt lại trước khi bị xem là out of sync.

Không nên hiểu ISR là tập replica có LEO bằng nhau ở mọi mili giây. Đây là tập replica đủ điều kiện tham gia các bảo đảm replication tại thời điểm đó. Việc follower gia nhập lại ISR thường đòi hỏi nó bắt kịp leader theo quy tắc của Kafka.

## 4. Follower lag ảnh hưởng đến producer như thế nào?

### 4.1. Producer với `acks=all`

Khi producer dùng `acks=all`, leader chỉ xác nhận ghi sau khi record được sao chép theo yêu cầu của tập ISR hiện tại. Nếu follower trong ISR chậm, leader có thể phải chờ follower fetch và append record trước khi xác nhận.

Ví dụ RF=3, cả ba replica đang ở ISR:

```text
Leader LEO:      201
Follower A LEO:  201
Follower B LEO:  198

Producer gửi record mới
       |
       v
Leader append record
       |
       v
Chờ follower B bắt kịp tiến độ cần thiết
       |
       v
Đủ điều kiện ACK theo acks=all
```

Follower lag có thể làm tăng produce latency. Nếu follower phục hồi nhanh, độ trễ chỉ tạm thời. Nếu follower thường xuyên chậm, producer có thể chạm `delivery.timeout.ms` hoặc nhận lỗi timeout tùy tình huống.

### 4.2. `min.insync.replicas`

`min.insync.replicas` đặt số replica đồng bộ tối thiểu để broker chấp nhận ghi khi producer dùng `acks=all`. Ví dụ RF=3 và `min.insync.replicas=2`:

- ISR có 3 replica: ghi có thể được chấp nhận và xác nhận theo ISR.
- ISR còn 2 replica: ghi vẫn có thể được chấp nhận.
- ISR chỉ còn 1 replica: ghi với `acks=all` bị từ chối do không đạt ngưỡng min ISR.

Điều này tạo một lựa chọn có chủ đích: khi replication không đủ, hệ thống có thể từ chối ghi để bảo vệ durability thay vì tiếp tục ghi với ít bản sao hơn mức nghiệp vụ chấp nhận.

`acks=all` không có nghĩa chờ tất cả replica từng được khai báo trong replication factor trong mọi trường hợp. Nó áp dụng cho ISR hiện tại, trong khi `min.insync.replicas` đặt ngưỡng thấp nhất mà broker chấp nhận cho ghi.

### 4.3. Follower bị loại khỏi ISR

Nếu follower bị loại khỏi ISR vì lag quá lâu, follower đó không còn tham gia ngưỡng xác nhận hiện tại. Điều này có thể giúp leader tiếp tục ghi nếu ISR còn đủ `min.insync.replicas`, nhưng số bản sao đang đồng bộ giảm và mức dự phòng cũng giảm.

Khi follower bắt kịp và được thêm lại ISR, mức dự phòng được khôi phục. Cần theo dõi ISR shrink/expand; nếu liên tục co lại và mở rộng, cluster có thể đang gặp vấn đề mạng, disk hoặc tải.

## 5. Các cấu hình fetch replication quan trọng

### 5.1. `replica.fetch.min.bytes` và `replica.fetch.wait.max.ms`

Hai tham số này phối hợp để cân bằng giữa số lượng request và thời gian chờ dữ liệu:

- Tăng `replica.fetch.min.bytes` có thể tạo batch lớn hơn, giảm request nhỏ, nhưng follower có thể chờ lâu hơn khi lưu lượng thấp.
- Tăng `replica.fetch.wait.max.ms` cho phép leader chờ lâu hơn để tích lũy dữ liệu, nhưng có thể tăng độ trễ replication trong workload ít dữ liệu.

Không nên tăng cả hai chỉ để giảm CPU. Hãy đo request rate, response size, replication lag và produce latency trước khi điều chỉnh.

### 5.2. `replica.fetch.max.bytes` và `replica.fetch.response.max.bytes`

Hai cấu hình kiểm soát kích thước dữ liệu replication được fetch. Nếu giới hạn quá thấp so với kích thước batch và tốc độ dữ liệu, follower có thể cần nhiều vòng fetch hơn để bắt kịp. Nếu đặt quá cao, fetch response có thể tạo áp lực lên bộ nhớ và mạng.

Khi thay đổi giới hạn, cần kiểm tra tính tương thích với kích thước message/batch, `message.max.bytes` ở broker, `max.message.bytes` ở topic và giới hạn producer. Một record batch hợp lệ lớn hơn giới hạn fetch mục tiêu có thể vẫn được trả trong một số trường hợp để follower không bị kẹt vĩnh viễn; không dùng điều đó làm lý do bỏ qua việc đồng bộ các giới hạn message.

### 5.3. `num.replica.fetchers`

`num.replica.fetchers` điều khiển số replica fetcher thread trên broker. Tăng giá trị có thể hữu ích khi một thread không đủ xử lý nhiều partition có throughput cao và CPU/network còn dư.

Tuy nhiên, mỗi fetcher tăng concurrency và có thể tăng:

- Số kết nối hoặc request đồng thời đến leader broker.
- Áp lực CPU khi giải mã, xử lý và append batch.
- Áp lực disk I/O và page cache.
- Cạnh tranh lock hoặc contention trong broker.

Hãy thay đổi từng bước, đo trước/sau và theo dõi cả broker leader lẫn follower. Nếu leader bị quá tải do phải phục vụ nhiều follower fetch request, tăng fetcher ở follower có thể làm tình hình tệ hơn.

### 5.4. `replica.lag.time.max.ms`

Đây là ngưỡng thời gian liên quan đến việc leader xem follower có còn theo kịp để nằm trong ISR hay không. Giá trị quá thấp có thể làm follower bị loại khỏi ISR khi mạng hoặc disk có những đợt chậm ngắn. Giá trị quá cao có thể giữ một follower không thực sự theo kịp trong ISR lâu hơn, làm tăng thời gian chờ xác nhận ghi hoặc che khuất lỗi kéo dài.

Không dùng tham số này để che giấu vấn đề disk/network. Trước tiên, xác định vì sao follower không fetch hoặc không append đủ nhanh; sau đó mới cân nhắc ngưỡng thời gian dựa trên latency bình thường và mục tiêu chịu lỗi.

## 6. Nguyên nhân follower fetch bị chậm

### 6.1. Mạng giữa broker

Follower phải nhận dữ liệu từ leader qua mạng. Các nguyên nhân thường gặp:

- Băng thông giữa rack/availability zone không đủ.
- Packet loss, retransmission hoặc network congestion.
- Firewall, NAT hoặc route không ổn định.
- Leader phân phối nhiều replica cho một follower broker khiến đường truyền tập trung.
- TLS hoặc CPU xử lý network làm tăng chi phí trên broker có tài nguyên hạn chế.

Kiểm tra network throughput, packet retransmission, latency, lỗi socket và phân bố traffic theo broker. Không chỉ kiểm tra kết nối client từ ứng dụng đến bootstrap listener; replication dùng kết nối broker-to-broker và cần đường mạng giữa các broker.

### 6.2. Disk I/O của follower

Follower nhận dữ liệu nhưng vẫn phải append vào log cục bộ. Nếu disk latency cao, volume đầy, IOPS bị giới hạn hoặc filesystem gặp vấn đề, LEO follower có thể tiến chậm dù network fetch vẫn hoạt động.

Kiểm tra:

- Disk utilization, await/latency và queue depth.
- Dung lượng còn trống và tốc độ tăng log.
- Page cache pressure và hoạt động flush.
- Phân bố partition replica trên các disk/volume.
- Các tác vụ compaction, retention cleanup hoặc recovery đang chạy.

### 6.3. Leader quá tải

Leader phải nhận produce request, append log, phục vụ consumer fetch và phục vụ follower fetch. Một broker giữ nhiều partition leader hoặc nhiều follower fetch có thể bị CPU, network hoặc disk quá tải.

Nếu leader quá tải, cả producer và follower đều có thể chậm. Kiểm tra phân bố leader, request handler idle percent, network processor idle percent, request queue, disk latency và throughput theo broker.

### 6.4. CPU, GC và thread contention

JVM pause dài, CPU saturation hoặc thiếu thread xử lý request có thể làm follower không gửi fetch đúng hạn hoặc không xử lý response kịp. Kiểm tra GC pause, CPU, số thread, request queue và log của broker trong cùng khoảng thời gian lag tăng.

### 6.5. Phân bố replica không cân bằng

Nếu nhiều partition nóng có leader tập trung trên một broker, broker đó phải phục vụ lượng produce và follower fetch lớn. Nếu replica follower của nhiều partition cùng dồn vào một broker, broker follower đó có thể trở thành nút thắt disk/network.

Cần xem cả leader distribution và replica distribution, không chỉ số partition tổng trên mỗi broker. Reassignment có thể giúp cân bằng, nhưng phải thực hiện có kế hoạch vì nó tạo thêm replication traffic và I/O trong lúc di chuyển replica.

## 7. Quan sát trạng thái replication

### 7.1. Kiểm tra leader, replicas và ISR bằng CLI

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Kết quả cho biết partition leader, danh sách replicas và ISR. Ví dụ:

```text
Topic: orders  Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
Topic: orders  Partition: 1  Leader: 2  Replicas: 2,3,1  Isr: 2,3
```

Partition 1 có ba replica được phân bổ nhưng ISR hiện chỉ có hai. Điều đó cho thấy một replica đang không thuộc ISR; cần xác định broker nào và vì sao nó bị loại.

### 7.2. Phân biệt consumer lag và replica lag

Consumer lag đo khoảng cách giữa vị trí consumer group đã xử lý/commit và log end offset của partition. Replica lag đo tiến độ follower replica so với leader. Hai metric này trả lời hai câu hỏi khác nhau:

| Loại lag | So sánh | Thành phần liên quan |
|---|---|---|
| Consumer lag | Consumer group offset với log end offset | Consumer application và broker |
| Replica lag | Follower LEO với leader LEO | Broker leader và follower replication fetcher |

Một consumer có thể lag nhiều dù mọi replica đều đồng bộ. Ngược lại, consumer có thể đọc kịp trong khi một follower replica đang tụt lại. Dùng `kafka-consumer-groups.sh` để quan sát consumer group lag không thay thế được việc kiểm tra ISR và replica metrics.

### 7.3. Theo dõi metric broker

Các metric hữu ích gồm:

- `UnderReplicatedPartitions`: số partition có replica chưa theo kịp theo tiêu chí Kafka.
- `UnderMinIsrPartitionCount`: số partition có ISR thấp hơn `min.insync.replicas` (nếu phiên bản và metric exporter cung cấp).
- `IsrShrinksPerSec` và `IsrExpandsPerSec`: tốc độ ISR co lại và mở rộng.
- Produce request latency và request queue time.
- Bytes in/out, network processor idle percent và request handler idle percent.
- Disk latency, disk utilization và dung lượng trống.
- Replica fetch request rate, response size và lỗi fetch nếu broker/exporter cung cấp.

Tên MBean, nhãn metric và cách export phụ thuộc phiên bản Kafka cùng hệ thống giám sát. Hãy xác minh tên thực tế trong JMX/exporter đang dùng trước khi viết alert.

### 7.4. Đọc log broker

Khi ISR thay đổi hoặc follower fetch thất bại, broker log thường có thông tin về partition, replica ID, leader epoch và nguyên nhân. Đối chiếu log của leader và follower trong cùng khoảng thời gian giúp phân biệt lỗi kết nối, lỗi disk và election/reassignment.

Không chỉ nhìn một dòng `Replica not available` rồi kết luận broker đã chết. Kiểm tra thời điểm, trạng thái broker, ISR trước/sau, fetcher error và khả năng kết nối giữa hai node.

## 8. Quy trình xử lý follower lag

Khi một partition có replica chậm hoặc ISR liên tục shrink, có thể điều tra theo trình tự:

1. **Xác định phạm vi:** partition nào bị ảnh hưởng, follower broker nào, lag bắt đầu lúc nào và có nhiều partition cùng bị không?
2. **Kiểm tra ISR:** dùng `kafka-topics --describe` để xác định replica nào đang ngoài ISR và leader hiện tại.
3. **Kiểm tra leader/follower broker:** so sánh CPU, GC, request queue, network throughput, disk latency và dung lượng.
4. **Kiểm tra đường mạng broker-to-broker:** xác minh controller/broker listener, route, packet loss, firewall và TLS nếu có.
5. **Kiểm tra fetcher:** xem fetch error, request rate, response size, số fetcher và tiến độ LEO nếu metric có sẵn.
6. **Kiểm tra phân bố tải:** xác định leader nóng hoặc replica dồn trên một broker.
7. **Điều chỉnh có kiểm soát:** thay đổi fetcher/concurrency hoặc fetch byte/wait chỉ sau khi đã xác định bottleneck.
8. **Xác minh phục hồi:** ISR ổn định, UnderReplicatedPartitions giảm, produce latency trở về mức bình thường và disk/network không còn quá tải.

Không nên đồng thời tăng `num.replica.fetchers`, `replica.fetch.max.bytes`, `replica.fetch.wait.max.ms` và `replica.lag.time.max.ms`. Nếu thay đổi nhiều biến cùng lúc, khó biết yếu tố nào thực sự cải thiện hoặc làm xấu tình hình.

## 9. Ví dụ tình huống

Giả sử topic `payments` có RF=3, `min.insync.replicas=2`, producer dùng `acks=all`. Partition 4 có:

```text
Leader: Broker 1, LEO=8,000
Follower Broker 2, LEO=8,000
Follower Broker 3, LEO=7,600
ISR: [1, 2, 3]
```

Producer latency tăng khi Broker 3 fetch chậm. Điều tra cho thấy Broker 3 có disk latency cao và follower fetcher append chậm.

Các bước suy luận:

- Broker 3 vẫn thuộc ISR trong tình huống ban đầu, nên tiến độ của nó có thể ảnh hưởng đến việc HW tăng và xác nhận `acks=all`.
- Khi Broker 3 bị loại khỏi ISR, ISR còn Broker 1 và 2. Với `min.insync.replicas=2`, ghi vẫn có thể tiếp tục nếu các điều kiện khác đáp ứng, nhưng cluster chỉ còn hai replica đồng bộ.
- Nếu Broker 2 cũng rời ISR, ISR chỉ còn leader. Ghi với `acks=all` bị từ chối vì không đạt min ISR bằng 2.
- Khi disk Broker 3 phục hồi, replica cần fetch/catch up và được đưa lại ISR theo quy tắc Kafka.

Tình huống này cho thấy `min.insync.replicas` là ngưỡng bảo vệ durability, còn việc follower fetch nhanh hay chậm ảnh hưởng đến thời gian duy trì ISR và độ trễ xác nhận ghi.

## 10. Checklist vận hành replication fetch

Trước và sau khi điều chỉnh replication, hãy kiểm tra:

- Broker leader và follower có đường mạng ổn định hai chiều.
- Follower fetcher có đủ CPU và thread để xử lý partition được gán.
- Disk của follower có đủ IOPS, throughput và dung lượng.
- Leader không quá tải bởi produce, consumer fetch và replica fetch đồng thời.
- `replica.fetch.min.bytes`, `replica.fetch.wait.max.ms` và giới hạn byte phù hợp với kích thước batch/tốc độ dữ liệu.
- `num.replica.fetchers` được điều chỉnh dựa trên metric, không dựa trên phỏng đoán.
- `replica.lag.time.max.ms` đủ dung sai cho latency bình thường nhưng không che giấu lỗi kéo dài.
- RF, ISR và `min.insync.replicas` phù hợp mục tiêu durability.
- Có alert cho UnderReplicatedPartitions, ISR shrink, produce latency và disk/network saturation.
- Có thể xác định rõ replica lag khác consumer lag trong dashboard và runbook.

## 11. Câu hỏi tự kiểm tra

1. Vì sao Kafka dùng follower pull thay vì để leader chủ động đẩy từng record đến từng follower?
2. Follower gửi offset nào trong fetch request tiếp theo sau khi append record thành công?
3. LEO khác high watermark ở điểm nào?
4. Vì sao replica lag theo offset không đồng nghĩa với lag theo thời gian?
5. Follower có thể có LEO thấp hơn leader nhưng vẫn ở trong ISR không?
6. `replica.lag.time.max.ms` ảnh hưởng như thế nào đến việc follower bị loại khỏi ISR?
7. Vì sao follower chậm có thể làm producer `acks=all` tăng latency?
8. RF=3, min ISR=2: điều gì xảy ra khi ISR giảm từ ba xuống hai rồi xuống một?
9. `num.replica.fetchers` tăng có thể cải thiện throughput trong trường hợp nào và gây tác dụng phụ gì?
10. Consumer lag và replica lag cần được đo và xử lý khác nhau như thế nào?

## Kết luận

Follower fetch là cơ chế broker follower chủ động lấy record từ partition leader, append vào log cục bộ và báo tiến độ qua fetch offset. LEO phản ánh vị trí append của từng replica; high watermark phản ánh ranh giới record đã commit theo replication; replica lag là chênh lệch tiến độ giữa follower và leader. Follower fetch chậm có thể làm ISR co lại, HW chậm tiến và producer `acks=all` tăng latency hoặc bị từ chối khi ISR thấp hơn `min.insync.replicas`. Quan sát đồng thời fetcher, ISR, network, disk và tải broker giúp tìm đúng nguyên nhân trước khi thay đổi cấu hình.
