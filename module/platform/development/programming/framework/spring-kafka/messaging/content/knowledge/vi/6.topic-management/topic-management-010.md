# Thay đổi partition và các giới hạn liên quan

## 1. Vì sao cần thay đổi số partition?

Partition là đơn vị lưu trữ và xử lý song song của một Kafka topic. Mỗi partition là một log có thứ tự riêng, được một consumer trong cùng consumer group xử lý tại một thời điểm. Số partition vì vậy ảnh hưởng trực tiếp đến khả năng phân phối tải, mức song song của consumer và cách Kafka lưu trữ dữ liệu.

Khi lưu lượng tăng, số consumer cần chạy song song nhiều hơn hoặc một partition trở thành điểm nóng, đội ngũ có thể cân nhắc tăng số partition. Ví dụ, topic `orders` ban đầu có 3 partition và consumer group có 3 consumer đang hoạt động. Nếu cần thêm consumer để tăng khả năng xử lý song song, topic có thể được mở rộng lên 6 partition.

Tuy nhiên, tăng partition là thay đổi kiến trúc của luồng dữ liệu. Nó ảnh hưởng đến phân vùng theo key, thứ tự sự kiện, consumer group, tài nguyên broker và cách vận hành. Cần đánh giá các tác động này trước khi thay đổi topic production.

## 2. Những gì thay đổi khi tăng partition?

Giả sử topic `orders` có 3 partition:

```text
Trước khi mở rộng

Topic: orders
  Partition 0  ── Consumer A
  Partition 1  ── Consumer B
  Partition 2  ── Consumer C

Sau khi tăng lên 6 partition

Topic: orders
  Partition 0  ──┐
  Partition 1  ──┤
  Partition 2  ──┼── Consumer group: order-service
  Partition 3  ──┤       Consumer A, B, C, D, E, F
  Partition 4  ──┤       được phân công lại sau rebalance
  Partition 5  ──┘
```

Khi tăng partition:

- Kafka tạo thêm các partition mới với log và offset riêng.
- Các record đã có vẫn nằm trong partition cũ; Kafka không tự phân phối lại dữ liệu lịch sử sang partition mới.
- Các partition mới thường bắt đầu chưa có record; producer sẽ ghi dữ liệu mới vào chúng theo partitioner hoặc partition được chỉ định.
- Consumer group có thể rebalance để phân công các partition mới cho consumer.
- Các offset đã commit của partition cũ vẫn gắn với partition đó; partition mới chưa có committed offset sẽ tuân theo chính sách khởi đầu như `auto.offset.reset`.

Tăng partition không đồng nghĩa với tăng replication factor. Mỗi partition mới được tạo theo cấu hình replication của topic và assignment trong cụm; số bản sao của partition là vấn đề riêng với số partition.

## 3. Giới hạn quan trọng: chỉ tăng, không giảm partition

Kafka hỗ trợ tăng số partition của một topic đã tồn tại. Không có thao tác alter topic thông thường để giảm số partition. Ví dụ topic có 12 partition không thể sửa trực tiếp thành 6 partition bằng `kafka-topics.sh --alter`.

Lý do là mỗi partition có log, offset và trạng thái phân phối riêng. Xóa bớt partition sẽ đòi hỏi quyết định dữ liệu nào bị loại bỏ, offset nào được giữ và cách xử lý các consumer group đang theo dõi partition đó. Vì vậy, Kafka không cung cấp thao tác giảm partition trực tiếp.

Nếu cần ít partition hơn, phương án an toàn thường là tạo topic mới với số partition mong muốn, sau đó lập kế hoạch chuyển producer và consumer sang topic mới. Việc chuyển đổi cần xác định cách copy hoặc phát lại dữ liệu cần giữ, thời điểm cutover, offset khởi đầu, khả năng xử lý trùng và thời gian lưu topic cũ. Không nên xóa rồi tạo lại topic cùng tên một cách tùy tiện vì có thể làm mất dữ liệu, thay đổi topic identity và khiến consumer group hoặc ứng dụng đang chạy gặp hành vi ngoài dự kiến.

## 4. Ảnh hưởng đến message key và thứ tự sự kiện

Đây là tác động quan trọng nhất khi tăng partition cho topic có sử dụng message key.

Với partitioner mặc định và record có key, Kafka thường chọn partition dựa trên hash của key và số partition hiện tại. Có thể hình dung đơn giản:

```text
partition = hash(key) % partitionCount
```

Giả sử `orderId=ORD-100` trước đây được đưa vào partition 1 khi topic có 3 partition. Sau khi topic tăng lên 6 partition, phép ánh xạ có thể đưa các record mới của `ORD-100` vào partition khác. Record cũ vẫn nằm ở partition 1, còn record mới có thể nằm ở partition mới.

```text
Trước khi tăng partition:
  ORD-100 / OrderCreated  ──▶ Partition 1
  ORD-100 / OrderPaid     ──▶ Partition 1

Sau khi tăng partition (ví dụ key được ánh xạ sang partition 4):
  ORD-100 / OrderCreated  ──▶ Partition 1  (record lịch sử)
  ORD-100 / OrderPaid     ──▶ Partition 4  (record mới)
```

Kafka chỉ đảm bảo thứ tự trong một partition. Nếu các sự kiện của cùng một đơn hàng nằm ở hai partition, hai consumer có thể xử lý chúng đồng thời và thứ tự hoàn tất không còn được đảm bảo. Do đó, tăng partition có thể phá vỡ giả định “cùng key luôn được xử lý tuần tự” khi xét xuyên suốt thời điểm thay đổi.

Sự thay đổi ánh xạ phụ thuộc partitioner. Với partitioner tùy chỉnh, chiến lược có thể khác; với record không có key, partitioner có thể sử dụng cơ chế sticky batching. Dù dùng cách nào, cần kiểm tra hành vi định tuyến thực tế thay vì giả định mọi key luôn giữ partition cũ.

Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt cho cùng một entity, hãy đánh giá rủi ro trước khi tăng partition. Một số lựa chọn gồm:

- Chấp nhận cutover có kiểm soát: tạm dừng producer, chờ consumer xử lý hết dữ liệu cũ, thay đổi partition count rồi tiếp tục phát dữ liệu. Cách này vẫn cần xác minh ánh xạ key và thời điểm consumer bắt đầu lại.
- Tạo topic phiên bản mới với partition count đã thiết kế, chuyển dữ liệu và producer theo một quy trình có kiểm soát.
- Thiết kế routing ổn định dựa trên số shard logic cố định hoặc partitioner tùy chỉnh nếu có yêu cầu dài hạn; giải pháp này cần được thiết kế và kiểm thử ngay từ đầu.

Không thể khôi phục thứ tự toàn cục chỉ bằng cách tăng số consumer hoặc thay đổi concurrency.

## 5. Ảnh hưởng đến consumer group và concurrency

Trong một consumer group, mỗi partition tại một thời điểm được gán cho tối đa một consumer. Một consumer có thể nhận nhiều partition, nhưng một partition không được nhiều consumer trong cùng group cùng xử lý đồng thời.

Vì vậy, số partition đặt giới hạn trên cho số consumer có thể hoạt động song song trong một group đối với topic đó. Ví dụ:

| Số partition | Số consumer trong group | Kết quả |
|---:|---:|---|
| 3 | 2 | Hai consumer chia nhau 3 partition |
| 3 | 3 | Có thể có một partition cho mỗi consumer |
| 3 | 5 | Tối đa 3 consumer được gán partition; các consumer còn lại rảnh |
| 6 | 6 | Có thể phân phối 6 partition cho 6 consumer |
| 6 | 3 | Mỗi consumer có thể nhận nhiều partition |

Khi tăng partition, consumer group có thể thực hiện rebalance để phân phối lại assignment. Trong thời gian rebalance, việc đọc có thể tạm dừng hoặc giảm tốc tùy assignor và giao thức group. Các instance mới không nhất thiết nhận đúng số partition bằng nhau nếu subscription hoặc assignment có ràng buộc khác.

Với Spring Kafka, `concurrency` trên listener container factory hoặc `@KafkaListener` quyết định số consumer mà endpoint có thể tạo. Tăng `concurrency` vượt số partition được gán không làm tăng mức song song hữu ích. Cần phối hợp partition count, số instance ứng dụng, concurrency và thời gian xử lý từng record.

## 6. Tăng partition bằng Kafka CLI

Trước khi thay đổi, kiểm tra topic hiện tại:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Kết quả hiển thị số partition, replication factor, leader, replicas và ISR. Ghi nhận trạng thái trước khi thay đổi để đối chiếu sau thao tác.

Ví dụ tăng topic `orders` từ 3 lên 6 partition:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --topic orders \
  --partitions 6
```

Tham số `--partitions` là **tổng số partition sau thay đổi**, không phải số partition cần cộng thêm. Nếu topic hiện có 3 partition và muốn tăng thêm 3, truyền giá trị `6`, không phải `3` hay `9`.

Sau đó kiểm tra lại:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Xác nhận số partition mới, leader và replica assignment của từng partition. Theo dõi ISR để bảo đảm các replica bắt kịp. Tên script có thể là `kafka-topics.bat` trên Windows tùy gói Kafka được cài đặt.

## 7. Tăng partition bằng Admin API

Ứng dụng Java có thể dùng Kafka Admin API để tăng partition. `NewPartitions.increaseTo()` nhận số partition đích:

```java
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewPartitions;

import java.util.Map;

public class TopicPartitionUpdater {

    public void increaseOrdersPartitions() throws Exception {
        Map<String, Object> config = Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");

        try (Admin admin = Admin.create(config)) {
            admin.createPartitions(Map.of(
                    "orders", NewPartitions.increaseTo(6)))
                    .all()
                    .get();
        }
    }
}
```

Lệnh chỉ hoàn tất khi Kafka xác nhận thao tác tạo partition. Trong ứng dụng thực tế, cần xử lý timeout, lỗi quyền truy cập, topic không tồn tại và trường hợp số partition đích không lớn hơn số hiện tại. Không nên chạy thao tác tăng partition trong mỗi lần khởi động ứng dụng nếu chưa có cơ chế migration hoặc quản trị idempotent rõ ràng.

`KafkaAdmin` của Spring Kafka hỗ trợ quản trị tài nguyên Kafka và khai báo topic ban đầu bằng `NewTopic`. Khi cần thay đổi topic đang chạy, có thể sử dụng Admin API một cách chủ động trong một quy trình quản trị riêng, đồng thời ghi log và kiểm tra kết quả thao tác.

## 8. Khai báo số partition khi tạo topic bằng Spring Kafka

Nếu đã biết nhu cầu song song từ đầu, hãy khai báo số partition phù hợp khi tạo topic. Ví dụ:

```java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
```

`partitions(6)` đặt số partition mong muốn khi tạo topic; `replicas(3)` đặt replication factor. Cụm cần có đủ broker để phân bố replica. Với topic đã tồn tại, cần xác minh hành vi của phiên bản Spring Kafka đang dùng; không nên cho rằng thay số trong bean sẽ tự động di chuyển dữ liệu cũ hoặc giảm partition.

Số partition nên được xem là quyết định thiết kế có ảnh hưởng dài hạn. Hãy dựa trên thông lượng đo được, mức song song mong muốn, số consumer dự kiến, số key, yêu cầu ordering và năng lực broker.

## 9. Các giới hạn tài nguyên khi tăng partition

Mỗi partition bổ sung tạo thêm log, metadata và công việc quản lý. Nếu replication factor là 3, một partition mới tạo ra ba replica trên cụm. Vì vậy, tăng partition làm tăng chi phí trên cả broker và hệ thống quản trị.

Các giới hạn cần đánh giá:

| Yếu tố | Tác động khi partition tăng | Cần kiểm tra |
|---|---|---|
| File và log segment | Nhiều partition tạo nhiều thư mục/log segment và file handle | Giới hạn file descriptor, dung lượng đĩa, số segment và chính sách retention |
| Bộ nhớ và metadata | Broker, controller và client phải theo dõi thêm partition/leader/replica | Heap, metadata size, thời gian cập nhật metadata và tải controller |
| Replication | Mỗi partition có follower cần fetch và duy trì ISR | Băng thông mạng, disk I/O, under-replicated partitions và ISR shrink |
| Leader và request handling | Nhiều leader/partition làm tăng hoạt động điều phối và request | Cân bằng leader, CPU, request rate và latency trên từng broker |
| Recovery và rebalance | Khởi động broker, phục hồi replica và phân phối partition có thể lâu hơn | Thời gian restart/recovery, thời gian rebalance và consumer lag |
| Consumer | Nhiều partition có thể tăng parallelism nhưng cũng tăng chi phí poll/assignment | Số consumer, concurrency, thời gian xử lý và lag theo partition |

Không có một con số partition tối đa phù hợp cho mọi cụm Kafka. Giới hạn thực tế phụ thuộc phiên bản Kafka, cấu hình broker, phần cứng, workload, replication factor và cách vận hành. Không nên tăng partition chỉ vì muốn tạo nhiều consumer hơn mà chưa đo bottleneck hiện tại.

## 10. Lập kế hoạch số partition

Khi thiết kế topic, hãy bắt đầu từ yêu cầu thông lượng và khả năng xử lý của từng partition trong môi trường thực tế.

Một cách ước lượng ban đầu:

```text
Số partition cần thiết ≈
    thông lượng mục tiêu của topic
    --------------------------------
    thông lượng an toàn đo được trên một partition
```

Đây chỉ là ước lượng ban đầu. Cần thử tải để xác định thông lượng an toàn theo kích thước record, số producer, số consumer, replication, disk và network. Sau đó cộng headroom cho tăng trưởng, bảo trì và dao động tải.

Ngoài thông lượng, cần trả lời các câu hỏi:

1. Có bao nhiêu consumer cần xử lý song song trong một group?
2. Key có phân bố đều hay một vài key chiếm phần lớn lưu lượng?
3. Nghiệp vụ có cần thứ tự theo `orderId`, `accountId` hoặc entity key khác không?
4. Có đủ broker và rack để phân bố replica không?
5. Số partition mới có làm tăng chi phí metadata, recovery và monitoring vượt khả năng cụm không?
6. Có kế hoạch tăng partition trong tương lai và quy trình xử lý thay đổi key mapping chưa?

Nếu một key tạo ra phần lớn lưu lượng, tăng partition có thể không giải quyết được điểm nóng vì mọi record cùng key vẫn được định tuyến theo cùng quy tắc. Cần xem xét lại key, mô hình phân vùng hoặc tách luồng nghiệp vụ phù hợp; không nên phá vỡ ordering chỉ để phân tán tải.

## 11. Tăng partition khác với reassignment partition

Hai thao tác thường bị nhầm:

| Thao tác | Mục đích | Dữ liệu cũ có di chuyển không? |
|---|---|---|
| Tăng partition count | Thêm partition mới vào topic để mở rộng khả năng song song và phân phối key | Không; record lịch sử vẫn ở partition cũ |
| Partition reassignment | Chuyển replica của các partition hiện có sang broker khác hoặc thay đổi vị trí replica | Có thể sao chép dữ liệu replica giữa broker; không làm thay đổi số partition |

Nếu vấn đề là một broker đang giữ quá nhiều replica hoặc leader, tăng partition không nhất thiết giải quyết được. Cần xem xét reassignment và cân bằng leader. Ngược lại, nếu cần thêm khả năng song song cho consumer group, reassignment không làm tăng số partition.

Sau khi tăng partition, Kafka có thể phân bố replica của partition mới theo assignment được tạo. Các partition cũ vẫn giữ assignment hiện tại trừ khi có thao tác reassignment riêng.

## 12. Quy trình thay đổi partition an toàn

Trước khi thực hiện ở production, nên chuẩn bị một thay đổi có thể quan sát và kiểm soát:

1. **Đánh giá nhu cầu:** đo producer throughput, consumer lag, thời gian xử lý, partition nóng và số consumer đang hoạt động.
2. **Kiểm tra ordering:** xác định key nào cần giữ thứ tự; đánh giá việc tăng partition có thay đổi ánh xạ key hay không.
3. **Kiểm tra sức khỏe cụm:** xác minh broker online, leader ổn định, ISR đầy đủ, đĩa và network còn headroom.
4. **Chọn số partition đích:** tính theo thông lượng và concurrency dự kiến, cộng headroom hợp lý.
5. **Lập kế hoạch thay đổi:** xác định thời gian thao tác, tác động rebalance, thông báo cho các consumer và phương án xử lý nếu phát hiện lỗi.
6. **Thực hiện tăng partition:** dùng CLI hoặc Admin API với số partition đích.
7. **Xác minh:** mô tả topic, kiểm tra leader/replica/ISR, quan sát consumer group và producer routing.
8. **Theo dõi sau thay đổi:** kiểm tra consumer lag, throughput, latency, rebalance, under-replicated partitions và phân bố tải.

Nếu yêu cầu thứ tự theo key là bắt buộc, cần có kế hoạch cutover riêng trước khi cho producer ghi vào partition mới. Việc tăng partition trực tiếp trong lúc producer tiếp tục phát có thể khiến sự kiện cùng key xuất hiện ở các partition khác nhau.

## 13. Tổng kết

- Partition là đơn vị log có thứ tự và là đơn vị song song cơ bản của consumer group.
- Kafka hỗ trợ tăng partition count nhưng không hỗ trợ giảm trực tiếp.
- Tăng partition tạo log mới; dữ liệu lịch sử không được tự phân phối lại.
- Với partitioner mặc định, thay đổi số partition có thể thay đổi ánh xạ key, làm ảnh hưởng thứ tự sự kiện cùng key qua thời điểm mở rộng.
- Trong một consumer group, một partition chỉ được gán cho tối đa một consumer tại một thời điểm; số partition giới hạn mức song song hữu ích.
- Partition count tăng làm tăng chi phí metadata, log, file handle, replication, recovery và rebalance.
- Tăng partition khác với reassignment; hãy chọn đúng thao tác theo bottleneck cần giải quyết.
- Cần đo tải, kiểm tra ordering, sức khỏe broker và theo dõi sau thay đổi trước khi mở rộng production.

Trong Spring Kafka, `KafkaTemplate` tiếp tục gửi record theo partitioner và key đã cấu hình, còn listener container nhận partition được consumer group gán. Hiểu rõ tác động của việc thay đổi partition giúp thiết kế topic có khả năng mở rộng mà vẫn giữ được tính đúng đắn của luồng sự kiện.
