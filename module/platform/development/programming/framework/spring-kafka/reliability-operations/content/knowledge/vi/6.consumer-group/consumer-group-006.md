# Consumer group lag

Consumer group lag là lượng tiến độ mà một consumer group còn chậm so với dữ liệu hiện có trong Kafka. Với mỗi partition, lag thường được biểu diễn bằng hiệu giữa offset cuối của log và committed offset của group. Lag tăng kéo dài có thể cho thấy consumer không theo kịp tốc độ producer, xử lý bị chậm, partition phân phối tải không đều hoặc consumer liên tục gặp lỗi.

Lag là một tín hiệu quan trọng trong vận hành Kafka, nhưng không tự giải thích nguyên nhân. Một group có lag cao có thể đang xử lý ổn định và sẽ bắt kịp sau một đợt traffic tăng đột biến. Ngược lại, lag thấp không bảo đảm hệ thống khỏe nếu record đã được commit trước khi side effect hoàn tất hoặc ứng dụng đang bỏ qua dữ liệu theo một chính sách đặc biệt.

Để đọc lag đúng, cần hiểu offset nào đang được so sánh, lag được tính theo partition ra sao, tốc độ backlog thay đổi thế nào và consumer group đang ở trạng thái nào. Việc điều tra cần kết hợp lag với throughput, thời gian xử lý, commit, rebalance, lỗi và độ tuổi của record.

## 1. Consumer group lag là gì?

Kafka lưu record trong từng partition và đánh số offset theo vị trí trong log. Consumer group duy trì committed offset riêng cho từng partition mà group đã xử lý. Consumer group lag mô tả khoảng cách giữa vị trí dữ liệu mới nhất và vị trí group đã commit.

Ví dụ một partition có:

- Log end offset là 1.250.
- Committed offset của group là 1.200.

Theo cách tính offset thông dụng, group còn khoảng 50 offset cần tiến tới:

~~~text
Lag = Log end offset - Committed offset
    = 1.250 - 1.200
    = 50
~~~

Committed offset thường biểu thị offset tiếp theo mà consumer group sẽ đọc, không phải offset của record cuối cùng đã xử lý. Nếu consumer đã xử lý record offset 1.199 và commit offset 1.200, lần đọc tiếp theo bắt đầu từ 1.200.

Lag được tính riêng cho từng partition. Lag toàn group thường là tổng lag của các partition được theo dõi. Tuy nhiên, tổng lag có thể che giấu một partition nóng có backlog rất lớn trong khi các partition khác gần như không có lag. Khi điều tra, luôn xem cả tổng, giá trị lớn nhất và phân phối lag theo partition.

## 2. Những offset cần phân biệt

Để hiểu một con số lag, cần biết hệ thống đang lấy mốc cuối nào của log.

### 2.1. Consumer position

Consumer position là vị trí tiếp theo mà consumer sẽ đọc trong bộ nhớ của client. Sau khi poll trả về record, position có thể đã tiến lên dù ứng dụng chưa xử lý xong record và chưa commit offset.

Vì vậy, position không đồng nghĩa với committed offset. Nếu consumer bị dừng trước khi commit, lần khởi động sau có thể đọc lại từ committed offset cũ.

### 2.2. Committed offset

Committed offset là tiến độ được lưu bền vững cho consumer group. Nó có thể được ghi bằng auto commit, commit đồng bộ/bất đồng bộ của consumer hoặc cơ chế do Spring Kafka listener container quản lý.

Nếu ứng dụng commit offset sau khi xử lý thành công, committed offset là tín hiệu hữu ích để đo tiến độ đã ghi nhận. Nếu ứng dụng commit trước khi hoàn tất side effect, lag có thể giảm trong khi nghiệp vụ thực tế chưa hoàn thành. Vì vậy, cách chọn thời điểm commit ảnh hưởng trực tiếp đến ý nghĩa vận hành của lag.

### 2.3. Log end offset (LEO)

Log end offset là offset tiếp theo ở cuối log của partition leader. Nó phản ánh vị trí cuối mà leader đã ghi nhận, bao gồm dữ liệu có thể chưa được replicate đầy đủ tới mọi replica.

Một số công cụ lag dùng log end offset làm mốc. Đây là cách đo phổ biến, nhưng không phải mọi record phía cuối log đều nhất thiết đã sẵn sàng cho consumer đọc trong mọi cấu hình.

### 2.4. High watermark (HW)

High watermark là ranh giới mà các record phía trước đã được replicate theo điều kiện Kafka sử dụng để cho phép consumer đọc. Với consumer đọc theo chế độ thông thường, dữ liệu chưa vượt high watermark chưa được trả về như dữ liệu đã commit ở cấp replication.

Nếu lag được tính từ LEO, một phần khoảng cách có thể nằm trong vùng leader đã ghi nhưng chưa đạt high watermark. Vì vậy, lag tính theo LEO có thể cao hơn lượng dữ liệu mà consumer hiện có thể đọc.

### 2.5. Last stable offset (LSO)

Với consumer dùng isolation level read_committed, Kafka chỉ trả về record transactional đã commit và dữ liệu ổn định đến Last Stable Offset (LSO). Một transaction đang mở có thể giữ LSO phía sau LEO hoặc HW.

Do đó, consumer read_committed có thể có lag theo LEO dù phần dữ liệu phía sau LSO chưa thể được đọc cho tới khi transaction hoàn tất. Khi điều tra một group transactional, cần xem transaction mở lâu và trạng thái producer bên cạnh lag.

### 2.6. Tóm tắt các vị trí

| Vị trí | Ý nghĩa | Dùng để hiểu điều gì |
|---|---|---|
| Consumer position | Vị trí đọc tiếp theo trong client | Consumer đã poll đến đâu |
| Committed offset | Tiến độ group đã lưu | Lần khởi động lại sẽ tiếp tục từ đâu |
| LEO | Cuối log trên leader | Dữ liệu leader đã ghi nhận đến đâu |
| HW | Ranh giới dữ liệu đã replicate đủ điều kiện đọc | Consumer thông thường có thể đọc đến đâu |
| LSO | Ranh giới ổn định cho read_committed | Consumer transactional có thể đọc đến đâu |

Các công cụ khác nhau có thể chọn LEO, HW hoặc LSO làm mốc lag. Khi so sánh dashboard với lệnh CLI hoặc metric từ exporter, hãy kiểm tra định nghĩa metric và nguồn offset được dùng.

## 3. Cách tính lag theo partition

Với cách tính dựa trên log end offset:

~~~text
partition_lag = log_end_offset - committed_offset
~~~

Nếu group chưa có committed offset, công cụ có thể hiển thị trạng thái không xác định, giá trị đặc biệt hoặc tính từ offset reset policy tùy cách triển khai. Không nên tự coi committed offset bằng 0 trong mọi trường hợp.

Ví dụ:

| Partition | LEO | Committed offset | Lag |
|---|---:|---:|---:|
| 0 | 10.500 | 10.480 | 20 |
| 1 | 8.900 | 8.700 | 200 |
| 2 | 9.300 | 9.250 | 50 |
| 3 | 11.100 | 10.600 | 500 |
| **Tổng** | | | **770** |

Group có tổng lag 770, nhưng partition 3 chiếm phần lớn backlog. Nếu chỉ nhìn tổng, đội vận hành có thể tăng số consumer trong khi nguyên nhân thực sự là key phân phối lệch hoặc một nhóm record của partition 3 xử lý rất chậm.

Lag theo offset cũng không phải lúc nào bằng chính xác số record vật lý còn đọc được. Với log compaction, retention, transaction marker và offset không liên tục trong dữ liệu nhìn thấy, phép trừ offset biểu thị khoảng cách vị trí trong log. Công cụ có thể gọi nó là số record lag, nhưng cần hiểu đây là cách đo dựa trên offset.

## 4. Lag theo record và lag theo thời gian

Hai cách nhìn bổ sung cho nhau:

- **Offset lag:** khoảng cách offset giữa cuối log và committed offset.
- **Time lag:** độ tuổi của record chưa được xử lý hoặc chênh lệch thời gian giữa dữ liệu mới nhất và dữ liệu group đang xử lý.

Ví dụ, lag 10.000 record có thể rất nhỏ nếu topic nhận 100.000 record mỗi giây, nhưng nghiêm trọng nếu topic chỉ nhận 10 record mỗi phút và record đầu backlog đã chờ nhiều giờ.

Time lag cũng cần được định nghĩa rõ. Có thể đo tuổi của record cũ nhất chưa xử lý, thời gian từ timestamp của record mới nhất đến record group đang đọc, hoặc chênh lệch timestamp giữa đầu log và vị trí committed. Các cách tính có ý nghĩa khác nhau và phụ thuộc timestamp của producer hay broker.

Nếu producer gửi timestamp sai, timestamp bị lệch clock hoặc record được replay từ nguồn cũ, time lag có thể gây hiểu nhầm. Hãy kết hợp offset lag với tuổi record, throughput và mục tiêu nghiệp vụ.

## 5. Vì sao consumer group lag tăng?

Lag tăng khi tốc độ dữ liệu đi vào vượt tốc độ group xử lý trong một khoảng thời gian, hoặc khi group không tiến triển. Các nguyên nhân thường gặp có thể được chia thành nhiều nhóm.

### 5.1. Producer gửi nhanh hơn consumer xử lý

Nếu producer tạo 20.000 record/giây nhưng toàn group chỉ xử lý 15.000 record/giây, backlog tăng khoảng 5.000 record mỗi giây trong điều kiện tốc độ ổn định.

Nguyên nhân có thể là traffic tăng, batch producer thay đổi, một job replay dữ liệu cũ hoặc nhiều producer cùng ghi vào topic. Trước khi tăng consumer, cần đo ingress rate và processing rate để biết khoảng thiếu hụt.

### 5.2. Xử lý từng record chậm

Listener có thể gọi database, HTTP API, dịch vụ thanh toán hoặc xử lý CPU nặng. Nếu dependency chậm, mỗi record mất lâu hơn và throughput consumer giảm.

Các tín hiệu cần xem:

- Thời gian xử lý mỗi record và mỗi batch.
- Database connection pool, lock wait và query latency.
- HTTP timeout, retry và lỗi từ downstream.
- CPU saturation, heap pressure và GC pause.
- Kích thước payload và thời gian deserialize.

### 5.3. Phân phối key không đều

Kafka chỉ gán một partition cho một consumer tại một thời điểm trong cùng group. Nếu key partitioning làm một partition nhận phần lớn traffic, consumer giữ partition đó có thể bị quá tải trong khi các consumer khác nhàn rỗi.

Tăng concurrency không thể chia một partition cho nhiều consumer trong cùng group. Cần kiểm tra phân phối key, partition count, throughput và lag riêng của từng partition. Nếu nghiệp vụ cho phép, có thể thay đổi key hoặc chiến lược partitioning, nhưng thay đổi này có thể ảnh hưởng ordering và cách dữ liệu cũ/mới được phân phối.

### 5.4. Consumer không hoạt động hoặc thiếu consumer

Consumer có thể bị crash, restart liên tục, mất kết nối broker, lỗi cấu hình hoặc không được gán partition. Nếu số consumer đang hoạt động thấp hơn dự kiến, tổng throughput giảm và lag tăng.

Kiểm tra group state, số member, partition assignment, log khởi động và lỗi kết nối. Một group có member tồn tại không có nghĩa mọi member đều đang xử lý partition.

### 5.5. Rebalance thường xuyên

Rebalance xảy ra khi member gia nhập/rời group, partition count thay đổi hoặc group cần phân phối lại partition. Trong lúc rebalance, consumer có thể tạm ngừng xử lý. Nếu rebalance lặp liên tục, thời gian hữu ích dành cho xử lý giảm đáng kể.

Nguyên nhân thường gặp:

- Consumer vượt max.poll.interval.ms vì xử lý batch quá lâu.
- Consumer mất heartbeat hoặc kết nối không ổn định.
- Deployment/restart liên tục.
- Thay đổi số partition hoặc thành viên group.
- Cấu hình timeout không phù hợp với thời gian xử lý.

Theo dõi rebalance count, thời lượng rebalance, member churn và thời gian giữa các lần poll để xác định nguyên nhân.

### 5.6. Retry và lỗi poison record

Một record lỗi có thể được retry nhiều lần hoặc làm listener dừng xử lý partition. Nếu retry blocking có backoff dài, consumer giảm tốc độ poll. Nếu record không thể xử lý nhưng không có chính sách phục hồi, group có thể bị kẹt ở cùng vị trí.

Xác định retry count, exception, backoff, DLT và trạng thái offset. Một chính sách retry tốt cần phân biệt lỗi tạm thời với lỗi dữ liệu không thể phục hồi.

### 5.7. Consumer commit chậm hoặc không commit

Consumer có thể poll và xử lý dữ liệu nhưng committed offset không tiến lên vì commit lỗi, commit bị trì hoãn hoặc cấu hình acknowledgment không phù hợp. Khi đó lag dựa trên committed offset tăng dù consumer position có thể đã tiến xa hơn.

Kiểm tra commit latency, commit failure, AckMode, auto commit và transaction. Nếu ứng dụng xử lý bất đồng bộ rồi commit sai thời điểm, committed offset có thể phản ánh tiến độ không đúng với side effect thực tế.

### 5.8. Transaction mở lâu

Với consumer read_committed, một transaction producer mở lâu có thể giữ LSO phía sau và làm consumer không đọc được các record phía sau transaction đó trong partition. Lag theo LEO có thể tăng dù consumer đang đọc hết phần dữ liệu đã ổn định.

Kiểm tra transaction timeout, producer sở hữu transaction, lỗi commit/abort và transaction coordinator. Không nên chỉ tăng tốc consumer khi ranh giới đọc đang bị chặn bởi transaction chưa hoàn tất.

## 6. Cách xem consumer group lag

Kafka cung cấp công cụ dòng lệnh kafka-consumer-groups để xem group, member, partition assignment, committed offset và lag.

Ví dụ:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group billing-service
~~~

Kết quả thường có các cột tương tự:

~~~text
GROUP            TOPIC   PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG  CONSUMER-ID
billing-service  orders  0          1200            1250            50   consumer-a
billing-service  orders  1          900             1100            200  consumer-b
~~~

Tên cột và định dạng có thể thay đổi theo phiên bản Kafka. Các giá trị chính cần đọc:

- **CURRENT-OFFSET:** committed offset mà group đã lưu.
- **LOG-END-OFFSET:** mốc cuối log mà công cụ dùng để tính lag.
- **LAG:** khoảng cách offset theo cách tính của công cụ.
- **CONSUMER-ID / HOST / CLIENT-ID:** member đang giữ partition nếu có assignment.

Nếu group không có member, group có thể đang inactive hoặc consumer đã dừng. Lag vẫn có thể tồn tại vì committed offset được lưu độc lập với tiến trình consumer.

Có thể xem trạng thái group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group billing-service \
  --state
~~~

Và xem member/assignment:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group billing-service \
  --members \
  --verbose
~~~

Các tùy chọn có thể khác giữa bản phân phối Kafka. Dùng kafka-consumer-groups.sh --help trên đúng môi trường để xác nhận cú pháp.

Không dùng lệnh reset offset như --reset-offsets trong quá trình chẩn đoán thông thường. Reset offset thay đổi vị trí group và có thể bỏ qua dữ liệu hoặc phát lại lượng lớn record. Chỉ thực hiện khi đã xác định rõ mục tiêu nghiệp vụ, phạm vi partition, offset đích và kế hoạch phục hồi.

## 7. Đo lag bằng AdminClient

Ứng dụng giám sát nội bộ có thể dùng AdminClient để đọc committed offset của group và end offset của partition. Ví dụ dưới đây minh họa cách lấy hai mốc offset:

~~~java
Properties properties = new Properties();
properties.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, "broker1:9092");

try (Admin admin = Admin.create(properties)) {
    String groupId = "billing-service";

    Map<TopicPartition, OffsetAndMetadata> committed =
        admin.listConsumerGroupOffsets(groupId)
             .partitionsToOffsetAndMetadata()
             .get(10, TimeUnit.SECONDS);

    Set<TopicPartition> partitions = committed.keySet();
    Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> ends =
        admin.listOffsets(
            partitions.stream().collect(Collectors.toMap(
                tp -> tp,
                tp -> OffsetSpec.latest()
            ))
        ).all().get(10, TimeUnit.SECONDS);

    committed.forEach((partition, metadata) -> {
        long current = metadata.offset();
        long end = ends.get(partition).offset();
        long lag = Math.max(0L, end - current);

        System.out.printf(
            "%s-%d committed=%d end=%d lag=%d%n",
            partition.topic(),
            partition.partition(),
            current,
            end,
            lag
        );
    });
}
~~~

Đây là ví dụ nền tảng cho các partition đã có committed offset. Hệ thống thực tế cần xử lý partition chưa có commit, group đang rebalance, lỗi authorization, timeout và topic/partition thay đổi trong lúc lấy hai tập offset. Hai truy vấn cũng không tạo một snapshot nguyên tử: producer và consumer vẫn có thể tiến triển giữa thời điểm đọc committed offset và end offset.

Nếu cần đo lag cho read_committed, cần hiểu mốc end offset mà công cụ đang sử dụng. ListOffsets với OffsetSpec.latest thường lấy end offset theo semantics của API và phiên bản Kafka; nó không tự động cung cấp mọi góc nhìn LSO/HW trong mọi cấu hình. Không nên so sánh trực tiếp con số tự tính với một exporter dùng mốc khác mà không kiểm tra định nghĩa.

## 8. Đo tốc độ tăng và tốc độ giảm backlog

Một con số lag tại một thời điểm chỉ cho biết kích thước khoảng cách. Để biết group có đang bắt kịp hay không, cần quan sát tốc độ thay đổi lag theo thời gian.

Gọi:

- L là backlog hiện tại tính theo offset/record lag.
- λ là tốc độ record mới đi vào, tính bằng record/giây.
- μ là tốc độ consumer xử lý và commit, tính bằng record/giây.

Nếu tốc độ ổn định và μ lớn hơn λ, tốc độ giảm backlog xấp xỉ:

~~~text
net_drain_rate = μ - λ
~~~

Thời gian ước lượng để bắt kịp:

~~~text
catch_up_time = L / (μ - λ)
~~~

Ví dụ:

- Lag hiện tại là 600.000 record.
- Producer tạo 8.000 record/giây.
- Consumer xử lý và commit 10.000 record/giây.

Tốc độ giảm backlog là 2.000 record/giây:

~~~text
catch_up_time = 600.000 / 2.000
              = 300 giây
              = 5 phút
~~~

Nếu μ bằng hoặc nhỏ hơn λ, group không thể giảm backlog bền vững. Tăng consumer chỉ có tác dụng nếu nó thực sự làm tăng μ; nếu bottleneck nằm ở một partition nóng, database hoặc API downstream thì thêm consumer có thể không cải thiện.

Phép tính này là ước lượng. Throughput thay đổi theo thời gian, kích thước record, partition, batch, retry và dependency. Hãy tính riêng theo partition hoặc dùng cửa sổ đo đủ dài để tránh kết luận từ một burst ngắn.

## 9. Consumer lag và thời gian bắt kịp

Khi backlog tăng sau một đợt traffic cao, câu hỏi vận hành thường là group có thể bắt kịp trước một deadline hay không.

Quy trình ước lượng:

1. Đo lag hiện tại theo partition và tổng group.
2. Đo producer ingress rate theo cùng cửa sổ thời gian.
3. Đo tốc độ xử lý/commit của consumer khi hệ thống ở trạng thái ổn định.
4. Tính net drain rate.
5. So sánh thời gian bắt kịp với SLO hoặc thời điểm nghiệp vụ cần dữ liệu mới.
6. Xác nhận tốc độ consumer không làm quá tải database, API hoặc broker.

Ví dụ group có lag 1,2 triệu record, ingress 4.000 record/giây và processing 7.000 record/giây:

~~~text
net_drain_rate = 7.000 - 4.000 = 3.000 record/giây
catch_up_time  = 1.200.000 / 3.000 = 400 giây
~~~

Nếu mục tiêu bắt kịp trong 2 phút, throughput hiện tại không đủ. Hệ thống cần tăng khả năng xử lý hoặc giảm ingress trong thời gian phục hồi. Nếu chỉ tăng concurrency mà database đã ở mức bão hòa, thời gian xử lý mỗi record có thể tăng và μ thậm chí giảm.

## 10. Cách giảm lag an toàn

Không có một cách giảm lag phù hợp cho mọi nguyên nhân. Hãy chọn biện pháp dựa trên bottleneck.

### 10.1. Tăng khả năng xử lý song song

Nếu có đủ partition và downstream còn capacity, tăng concurrency hoặc số consumer trong group có thể tăng tổng throughput.

Trước khi tăng:

- Xác nhận topic có đủ partition để phân phối cho consumer mới.
- Kiểm tra database connection pool và giới hạn đồng thời của downstream.
- Kiểm tra key distribution để phát hiện partition nóng.
- Đo thời gian xử lý và commit sau khi tăng.
- Theo dõi rebalance trong quá trình scale.

Nếu số partition nhỏ hơn số consumer, consumer dư sẽ không xử lý được dữ liệu. Thêm partition là một thay đổi có ảnh hưởng đến partitioning và ordering; cần cân nhắc key mapping, dữ liệu cũ và consumer assignment.

### 10.2. Tối ưu xử lý từng record

Nếu thời gian xử lý record cao, tập trung vào dependency:

- Tối ưu query và index database.
- Dùng bulk insert/update khi phù hợp.
- Giảm số lần gọi HTTP hoặc gộp request.
- Đặt timeout và retry có giới hạn.
- Tránh tính toán lặp hoặc deserialize nhiều lần.
- Giới hạn payload và loại bỏ công việc không cần thiết trên consumer thread.

Đo p95/p99 để xác định record chậm. Average thấp có thể che giấu một số record làm cả partition bị nghẽn.

### 10.3. Điều chỉnh max.poll.records

max.poll.records ảnh hưởng lượng record trả về trong một poll. Batch lớn có thể tăng hiệu quả xử lý bulk nhưng kéo dài thời gian trước lần poll tiếp theo. Batch nhỏ hơn giúp giảm thời gian xử lý mỗi chu kỳ và giới hạn phạm vi công việc cần retry, đổi lại có thể tăng overhead.

Điều chỉnh dựa trên max.poll.interval.ms và thời gian xử lý batch ở p95/p99. Đừng tăng max.poll.records chỉ vì lag cao; nếu consumer đã mất nhịp poll, batch lớn hơn có thể gây thêm rebalance.

### 10.4. Điều chỉnh retry và DLT

Nếu lag do một record lỗi bị retry lâu:

- Phân loại lỗi có thể retry và lỗi dữ liệu không thể retry.
- Giới hạn số lần và tổng thời gian retry.
- Dùng backoff phù hợp.
- Chuyển record sang DLT khi đã vượt chính sách phục hồi.
- Bảo đảm publish DLT và commit offset gốc theo semantics đã chọn.

DLT giúp partition chính tiếp tục tiến triển khi record lỗi được phục hồi thành công theo chính sách. Tuy nhiên, cần theo dõi DLT riêng; nếu không, backlog chỉ chuyển từ topic chính sang topic lỗi.

### 10.5. Pause khi downstream quá tải

Spring Kafka container có thể pause/resume để giảm lượng công việc mới trong lúc downstream phục hồi. Pause cần được thực hiện qua API container phù hợp, giữ poll loop theo cơ chế của framework và có điều kiện resume rõ ràng.

Pause không làm backlog biến mất; nó ngăn consumer nhận thêm công việc trong lúc hệ thống đích đang quá tải. Trong thời gian pause, producer vẫn có thể tiếp tục ghi và lag có thể tăng. Cần có cảnh báo và kế hoạch phục hồi sau khi resume.

## 11. Rebalance và lag

Rebalance có thể làm lag tăng vì consumer tạm dừng xử lý, partition được thu hồi rồi gán lại và consumer có thể phải đọc lại từ committed offset. Một lần rebalance ngắn không nhất thiết là sự cố; rebalance liên tục mới là tín hiệu đáng chú ý.

Các yếu tố nên kiểm tra:

- Thời gian xử lý batch có gần hoặc vượt max.poll.interval.ms không?
- Consumer có restart, crash hoặc mất heartbeat không?
- Có deployment làm nhiều member rời group cùng lúc không?
- Có thay đổi partition hoặc subscription không?
- Assignment strategy có tạo phân phối tải lệch không?
- Consumer có hoàn tất side effect sau khi partition đã bị revoke không?

Trong Spring Kafka, listener container và rebalance listener cung cấp điểm tích hợp để xử lý partition assignment/revocation. Khi partition bị revoke, ứng dụng cần hoàn tất hoặc dừng các công việc đang chạy theo cách an toàn và commit tiến độ hợp lệ trước khi mất quyền sở hữu, nếu cấu hình cho phép.

Không nên cố giảm lag bằng cách liên tục restart consumer. Restart hàng loạt thường tạo thêm rebalance và khiến throughput giảm trong thời gian phục hồi.

## 12. Lag và delivery semantics

Lag phản ánh tiến độ commit của consumer group, vì vậy phải được đọc cùng delivery semantics.

### 12.1. At-least-once

Nếu consumer chỉ commit offset sau khi xử lý thành công, lỗi xảy ra sau side effect nhưng trước commit có thể khiến record được đọc lại. Lag có thể tăng hoặc không tiến triển trong lúc retry. Consumer cần idempotent để duplicate không làm thay đổi kết quả nghiệp vụ nhiều lần.

### 12.2. At-most-once

Nếu consumer commit offset trước khi xử lý, lag có thể giảm ngay cả khi side effect chưa thành công. Khi ứng dụng lỗi sau commit, record có thể bị bỏ qua. Một dashboard lag thấp không thể phát hiện trực tiếp dữ liệu nghiệp vụ bị mất do commit quá sớm.

### 12.3. Exactly-once trong Kafka

Với Kafka transaction, ứng dụng có thể commit output records và offset input trong cùng transaction. Consumer downstream dùng read_committed để chỉ nhìn thấy output đã commit. Khi transaction abort, offset và output không được commit cùng nhau.

Lag trong mô hình transactional vẫn cần được hiểu theo committed offset và mốc log phù hợp. Transaction mở lâu có thể giữ LSO và làm record chưa đọc được. EOS trong Kafka không tự bao gồm database hoặc HTTP API ngoài Kafka.

## 13. Cảnh báo lag có ý nghĩa

Không nên đặt một ngưỡng lag cố định duy nhất cho mọi topic. Ngưỡng phù hợp phụ thuộc ingress rate, SLO, retention, kích thước record và thời gian xử lý nghiệp vụ.

Một bộ cảnh báo hữu ích có thể gồm:

| Cảnh báo | Mục đích |
|---|---|
| Total lag vượt ngưỡng trong nhiều cửa sổ liên tiếp | Phát hiện backlog kéo dài |
| Max partition lag tăng nhanh | Phát hiện partition nóng hoặc consumer member bị nghẽn |
| Lag growth rate dương kéo dài | Consumer không bắt kịp ingress |
| Oldest unprocessed record age vượt SLO | Phát hiện độ trễ nghiệp vụ thực tế |
| Group không có member nhưng lag còn tồn tại | Phát hiện consumer group ngừng hoạt động |
| Rebalance tăng bất thường | Phát hiện consumer không giữ được nhịp |
| Commit failure hoặc committed offset đứng yên | Phát hiện tiến độ không được ghi nhận |
| DLT lag tăng | Phát hiện lỗi đang tích tụ ở luồng phục hồi |

Nên dùng cửa sổ thời gian và điều kiện kéo dài để tránh cảnh báo khi traffic tăng ngắn hạn rồi tự phục hồi. Đồng thời, đặt cảnh báo theo từng group/topic quan trọng thay vì chỉ theo toàn cluster.

## 14. Runbook khi lag tăng đột biến

Khi nhận cảnh báo, điều tra theo thứ tự để xác định backlog nằm ở đâu.

### Bước 1: Xác nhận phạm vi

- Group nào bị ảnh hưởng?
- Topic và partition nào có lag?
- Lag tăng ở tất cả partition hay chỉ một vài partition?
- Group có member và assignment đang hoạt động không?
- Lag bắt đầu tăng từ thời điểm nào?

### Bước 2: Xác định backlog có đang tiếp tục tăng không

So sánh lag ở nhiều thời điểm, producer ingress rate và consumer processing/commit rate. Nếu lag đang giảm, group có thể đang tự phục hồi. Nếu lag tiếp tục tăng, cần tìm chênh lệch throughput.

### Bước 3: Kiểm tra consumer health

Xem restart, crash, rebalance, max.poll.interval.ms, thời gian xử lý batch, commit failure, thread pool và GC. Nếu consumer không có assignment, kiểm tra group state và partition count.

### Bước 4: Kiểm tra dependency

Đo database latency, connection pool, HTTP timeout, downstream error rate, CPU và network. Nếu dependency là bottleneck, scale consumer có thể làm tình hình tệ hơn.

### Bước 5: Chọn biện pháp

- Tăng concurrency khi có partition và downstream capacity.
- Tối ưu xử lý khi latency từng record cao.
- Điều chỉnh batch khi poll cycle quá dài.
- Sửa key/partitioning nếu có partition nóng.
- Điều chỉnh retry/DLT nếu poison record làm nghẽn.
- Khôi phục broker/ISR hoặc xử lý transaction mở lâu nếu nguyên nhân nằm ở Kafka.

### Bước 6: Xác nhận phục hồi

Theo dõi lag giảm, oldest record age trở lại mục tiêu, processing rate vượt ingress rate trong thời gian cần thiết, rebalance ổn định và downstream không bị quá tải. Ghi nhận nguyên nhân gốc và thay đổi cấu hình để tránh lặp lại.

## 15. Các lỗi vận hành thường gặp

| Cách làm | Rủi ro | Hướng xử lý |
|---|---|---|
| Chỉ nhìn tổng lag | Bỏ sót partition nóng | Theo dõi lag lớn nhất và phân phối theo partition |
| Xem lag offset như số record chính xác trong mọi trường hợp | Hiểu sai log compaction, transaction hoặc offset gap | Xác nhận cách công cụ tính lag và mốc LEO/HW/LSO |
| Tăng consumer khi downstream đã bão hòa | Database/API chậm hơn và lag tăng | Đo bottleneck trước khi scale |
| Reset offset để làm lag về 0 | Bỏ qua dữ liệu hoặc phát lại lượng lớn record | Chỉ reset khi có quyết định nghiệp vụ và kế hoạch kiểm soát |
| Restart liên tục khi lag tăng | Rebalance nhiều hơn và giảm throughput | Điều tra poll, dependency và lỗi consumer |
| Commit offset trước side effect | Lag thấp giả tạo nhưng có thể mất nghiệp vụ | Chọn commit sau xử lý hoặc transaction phù hợp |
| Không theo dõi DLT | Backlog chỉ chuyển sang luồng lỗi | Giám sát DLT và quy trình replay |
| Dùng một ngưỡng lag cho mọi topic | Alert nhiễu hoặc bỏ lỡ sự cố | Đặt ngưỡng theo ingress, SLO và retention |

## 16. Checklist thiết kế và vận hành consumer group lag

Trước khi đưa dashboard và alert vào production, hãy trả lời:

1. Lag được tính từ committed offset đến LEO, HW hay một mốc khác?
2. Metric là tổng group, theo partition hay theo member?
3. Group có committed offset cho tất cả partition không?
4. Lag offset và tuổi record chưa xử lý có được theo dõi riêng không?
5. Producer ingress rate và consumer processing/commit rate có cùng đơn vị và cùng cửa sổ đo không?
6. Có thể tính net drain rate và thời gian bắt kịp sau một đợt backlog không?
7. Partition nóng, key skew và assignment imbalance có được phát hiện không?
8. Dashboard có rebalance, poll interval, commit failure, retry và dependency latency không?
9. Có chính sách idempotency khi record được đọc lại sau lỗi hoặc rebalance không?
10. Có runbook rõ ràng trước khi tăng concurrency, tăng partition hoặc reset offset không?

Consumer group lag là chỉ báo tiến độ, không phải chẩn đoán nguyên nhân. Đọc đúng committed offset, mốc cuối log và phân phối lag theo partition sẽ giúp xác định group đang chậm ở đâu. Khi kết hợp lag với ingress/processing rate, thời gian xử lý, rebalance và tuổi record, đội vận hành có thể dự báo thời gian bắt kịp và chọn biện pháp phục hồi phù hợp mà không làm tăng tải hoặc gây mất dữ liệu ngoài ý muốn.
