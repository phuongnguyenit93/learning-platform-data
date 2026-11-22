# Giới hạn của một consumer trong group

Trong Kafka, consumer group là cơ chế để nhiều consumer cùng chia nhau đọc các partition của topic. Một consumer có thể nhận một hoặc nhiều partition, nhưng trong cùng một group, mỗi partition tại một thời điểm chỉ được gán cho tối đa một consumer. Quy tắc này quyết định mức song song mà group có thể đạt được và tạo ra giới hạn tự nhiên khi mở rộng số consumer.

Vì vậy, tăng số instance consumer không phải lúc nào cũng làm tăng thông lượng. Nếu số consumer nhiều hơn số partition mà group đang đọc, một số consumer sẽ không được gán partition. Nếu số partition ít, group có thể không tận dụng hết tài nguyên xử lý; nếu số partition nhiều nhưng consumer xử lý chậm hoặc phụ thuộc downstream bị nghẽn, tăng consumer cũng chưa chắc giải quyết được lag.

Bài học thuộc chương **Consumer** của module **SPRING_KAFKA_MESSAGING**, tập trung vào giới hạn của một consumer trong group, mối quan hệ giữa partition và consumer, cách Spring Kafka tạo concurrency, ảnh hưởng của poll loop và rebalance, cùng cách đo đạc để mở rộng hệ thống có căn cứ.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa consumer group, consumer member và partition.
- Xác định số consumer tối đa có thể đọc song song một tập partition trong cùng group.
- Hiểu vì sao một consumer có thể nhận nhiều partition và vì sao consumer dư có thể ở trạng thái nhàn rỗi.
- Phân biệt khả năng song song ở cấp partition với khả năng xử lý đồng thời trong ứng dụng.
- Cấu hình concurrency của listener container trong Spring Kafka.
- Hiểu tác động của poll loop, max.poll.records, max.poll.interval.ms và rebalance.
- Bảo toàn thứ tự xử lý khi ứng dụng có nhiều partition hoặc xử lý bất đồng bộ.
- Đo consumer lag và các chỉ số để quyết định tăng consumer hay tăng partition.
- Thiết kế kiểm thử để xác minh partition assignment và giới hạn thực tế của group.

## 1. Consumer group chia partition như thế nào?

Kafka lưu record trong các partition. Consumer group gồm một hoặc nhiều consumer member có cùng group-id. Các member phối hợp để chia nhau đọc những partition mà group đã subscribe.

Quy tắc quan trọng: **một partition chỉ được gán cho tối đa một consumer member trong cùng group tại một thời điểm**. Điều này giúp các consumer trong group không cùng đọc và commit tiến độ cho một partition theo cách cạnh tranh. Một partition vẫn có thể được một consumer thuộc group khác đọc độc lập.

Ví dụ topic orders.created có sáu partition:

~~~mermaid
flowchart TB
    subgraph Topic["Topic: orders.created"]
        P0["Partition 0"]
        P1["Partition 1"]
        P2["Partition 2"]
        P3["Partition 3"]
        P4["Partition 4"]
        P5["Partition 5"]
    end
    subgraph Group["Consumer group: fulfillment"]
        C1["Consumer 1"]
        C2["Consumer 2"]
        C3["Consumer 3"]
    end
    P0 --> C1
    P1 --> C1
    P2 --> C2
    P3 --> C2
    P4 --> C3
    P5 --> C3
~~~

Với ba consumer và sáu partition, mỗi consumer có thể được gán hai partition. Một consumer không tương đương với một partition: một member có thể xử lý nhiều partition.

Nếu group có sáu consumer cho sáu partition, mỗi consumer có thể nhận một partition. Nếu group có tám consumer, tối đa sáu consumer có partition được gán; hai consumer còn lại không có partition của topic này trong assignment hiện tại.

## 2. Giới hạn song song theo số partition

Số partition là giới hạn trên của số consumer có thể đồng thời nhận partition của một topic trong cùng group. Với một topic có P partition, số consumer hữu ích tối đa cho riêng topic đó không vượt quá P.

| Số partition | Số consumer trong group | Consumer có partition | Consumer không có partition |
|---:|---:|---:|---:|
| 2 | 1 | 1 | 0 |
| 2 | 2 | 2 | 0 |
| 2 | 4 | Tối đa 2 | Tối thiểu 2 |
| 6 | 3 | Tối đa 3 | 0 |
| 6 | 6 | Tối đa 6 | 0 |
| 6 | 8 | Tối đa 6 | Tối thiểu 2 |

Bảng trên giả định các consumer trong cùng group subscribe cùng một topic và topic có số partition như đã nêu. Khi một group subscribe nhiều topic, cần xét tổng tập partition mà group có thể nhận theo subscription và partition assignment strategy; số consumer hữu ích vẫn bị giới hạn bởi số partition được phân công.

Có thể biểu diễn giới hạn lý tưởng cho một topic như sau:

\[
C_{active} \leq \min(C_{members}, P)
\]

Trong đó:

- C_active là số consumer thực sự nhận ít nhất một partition của topic.
- C_members là tổng số consumer member trong group.
- P là số partition của topic.

Công thức này chỉ mô tả giới hạn assignment. Nó không bảo đảm mọi consumer đều xử lý cùng lượng dữ liệu hoặc có thông lượng giống nhau. Partition có thể có lưu lượng không đồng đều, một consumer có thể nhận partition nặng hơn consumer khác và tốc độ xử lý còn phụ thuộc CPU, I/O, database cùng các dịch vụ downstream.

## 3. Điều gì xảy ra khi consumer ít hơn partition?

Khi số consumer ít hơn số partition, một member thường nhận nhiều partition. Consumer đó poll dữ liệu từ các partition được gán và quản lý offset riêng cho từng partition.

Ví dụ topic có sáu partition và group có hai consumer. Mỗi consumer có thể nhận ba partition. Điều này vẫn cho phép đọc song song giữa hai consumer, nhưng một consumer phải chia thời gian xử lý cho nhiều partition.

Các hệ quả cần lưu ý:

- Consumer có thể có nhiều partition đang tăng lag, dù bản thân process chỉ là một member.
- Một partition có lưu lượng cao có thể chiếm phần lớn thời gian xử lý của consumer.
- Một lần rebalance có thể thay đổi tập partition mà consumer sở hữu.
- Nếu listener xử lý tuần tự, một lần poll có thể trả record từ nhiều partition; container chuyển chúng tới listener theo cơ chế đã cấu hình, trong khi thứ tự record của từng partition vẫn được duy trì.

Một consumer nhận nhiều partition không có nghĩa Kafka gộp các partition thành một log. Mỗi partition vẫn có offset và thứ tự riêng.

## 4. Điều gì xảy ra khi consumer nhiều hơn partition?

Khi group có nhiều consumer member hơn số partition, các member dư có thể không được gán partition. Chúng vẫn có thể tham gia group, gửi heartbeat và chờ assignment mới, nhưng không đọc record từ topic đó khi không có partition được giao.

Ví dụ:

~~~mermaid
flowchart TB
    subgraph Topic["Topic: payments.authorized (3 partitions)"]
        P0["Partition 0"]
        P1["Partition 1"]
        P2["Partition 2"]
    end
    subgraph Group["Consumer group: billing"]
        C1["Consumer 1 - active"]
        C2["Consumer 2 - active"]
        C3["Consumer 3 - active"]
        C4["Consumer 4 - idle"]
        C5["Consumer 5 - idle"]
    end
    P0 --> C1
    P1 --> C2
    P2 --> C3
~~~

Hai consumer dư không làm topic xử lý nhanh hơn vì không có partition để đọc. Chúng vẫn tiêu thụ tài nguyên process, thread, kết nối và có thể làm tăng chi phí quản lý group.

Không nên mặc định triển khai số consumer bằng số CPU hoặc số pod mong muốn. Hãy đối chiếu concurrency với số partition và lưu lượng thực tế.

## 5. Thứ tự xử lý bị giới hạn theo partition

Kafka bảo đảm thứ tự record trong một partition. Kafka không cung cấp một thứ tự tổng thể giữa các partition của cùng topic.

Nếu các sự kiện của cùng một đơn hàng phải được xử lý theo thứ tự, producer thường dùng orderId làm key để các record liên quan được định tuyến nhất quán tới cùng partition theo partitioner mặc định.

Trong cùng consumer group:

- Một partition được gán cho một member tại một thời điểm.
- Consumer đọc record theo thứ tự offset của partition.
- Nếu listener xử lý đồng bộ từng record, thứ tự gọi listener trong partition được giữ theo thứ tự record được giao.
- Nếu ứng dụng chuyển xử lý sang nhiều thread hoặc nhiều future, thứ tự hoàn tất nghiệp vụ có thể khác thứ tự record được đọc.

Ví dụ, consumer đọc OrderCreated rồi OrderPaid theo thứ tự, nhưng đẩy hai công việc sang hai thread riêng. Nếu OrderPaid hoàn tất trước OrderCreated, thứ tự tác động nghiệp vụ đã bị đảo dù Kafka giao record đúng thứ tự.

Nếu cần bảo toàn thứ tự nghiệp vụ, hãy xử lý tuần tự theo partition hoặc thiết kế hàng đợi xử lý theo key. Không dùng chung một thread pool không giới hạn cho mọi record rồi giả định thứ tự Kafka sẽ tự được giữ trong các thao tác downstream.

Việc tăng số partition cũng có thể ảnh hưởng tới định tuyến key theo partitioner mặc định. Nếu số partition thay đổi, cùng một key có thể được định tuyến sang partition khác đối với record mới. Vì vậy, thay đổi partition cần được đánh giá khi thứ tự của aggregate là yêu cầu bắt buộc.

## 6. Partition assignment và rebalance

Kafka group coordinator phối hợp các member và partition assignment. Khi consumer tham gia hoặc rời group, topic được tăng partition hoặc subscription thay đổi, group có thể thực hiện rebalance để phân phối lại partition.

Các chiến lược assignment phổ biến gồm:

- **RangeAssignor:** phân phối các partition theo phạm vi cho consumer.
- **RoundRobinAssignor:** phân phối lần lượt các partition cho member đủ điều kiện.
- **StickyAssignor:** cố gắng giữ assignment cũ nhiều nhất có thể trong khi cân bằng lại.
- **CooperativeStickyAssignor:** hỗ trợ chuyển assignment theo cách hợp tác, giảm việc thu hồi toàn bộ partition trong một lần rebalance ở các cấu hình tương thích.

Chiến lược thực tế phụ thuộc cấu hình consumer, phiên bản Kafka client và khả năng tương thích giữa các member trong group. Không nên chỉ dựa vào tên chiến lược để giả định mọi lần phân phối sẽ cân bằng hoàn hảo.

Rebalance có thể tạo ra khoảng thời gian một số partition tạm dừng xử lý trong lúc assignment thay đổi. Ứng dụng cần xử lý commit offset và trạng thái công việc đang thực hiện đúng cách. Nếu consumer bị thu hồi partition khi còn công việc bất đồng bộ chưa hoàn tất, ứng dụng có thể cần dừng nhận thêm việc, hoàn tất hoặc hủy công việc theo chính sách và tránh commit offset vượt quá record đã xử lý an toàn.

Một số nguyên nhân thường gây rebalance:

- Tăng hoặc giảm số instance ứng dụng.
- Thay đổi concurrency của listener.
- Consumer mất kết nối hoặc không poll trong thời gian cho phép.
- Thêm partition vào topic.
- Thay đổi danh sách topic subscription.
- Consumer bị dừng hoặc khởi động lại.

Rebalance là một phần bình thường của consumer group. Mục tiêu vận hành là giảm rebalance không cần thiết và bảo đảm listener có thể phục hồi đúng sau khi assignment thay đổi.

## 7. Concurrency trong Spring Kafka

Spring Kafka cung cấp concurrency cho listener container. Khi tăng concurrency, container factory tạo nhiều consumer worker cho một listener container. Mỗi consumer có KafkaConsumer riêng; KafkaConsumer không được thiết kế để nhiều thread gọi đồng thời trên cùng một instance.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: fulfillment-service
      enable-auto-commit: false
      properties:
        "max.poll.records": 100
        "max.poll.interval.ms": 300000
    listener:
      concurrency: 3
~~~

Trong cấu hình trên, listener container có concurrency bằng ba. Với một listener dùng group-id fulfillment-service, Spring Kafka tạo tối đa ba consumer member cho container đó. Nếu ứng dụng chạy hai replica giống nhau, tổng số member của group có thể là sáu, giả sử cả hai replica đều có listener container cùng cấu hình.

Listener minh họa:

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "fulfillment-service"
    )
    public void consume(OrderCreatedEvent event) {
        // Xử lý nghiệp vụ của một sự kiện.
    }
}
~~~

Concurrency không tạo thêm partition. Nếu topic có hai partition mà concurrency là năm, chỉ tối đa hai consumer của container có partition được gán cho topic đó. Nếu topic có sáu partition và concurrency là ba, mỗi consumer có thể nhận nhiều partition.

Có thể cấu hình concurrency riêng cho từng listener thông qua thuộc tính của @KafkaListener hoặc listener container factory tùy thiết kế. Hãy bảo đảm số consumer được tạo ra là có chủ đích, đặc biệt khi có nhiều listener cùng group hoặc nhiều replica ứng dụng.

## 8. Poll loop và giới hạn thời gian xử lý

Kafka consumer đọc dữ liệu bằng poll loop. Trong mỗi vòng, consumer gọi poll để lấy record từ các partition được gán, xử lý dữ liệu theo listener và tiếp tục poll để duy trì tiến độ đọc cùng membership của group.

Hai thuộc tính quan trọng:

- **max.poll.records:** giới hạn số record tối đa mà một lần poll trả về cho ứng dụng. Nó giúp kiểm soát kích thước batch xử lý.
- **max.poll.interval.ms:** giới hạn khoảng thời gian tối đa giữa các lần gọi poll. Nếu ứng dụng không poll lại trong thời gian này, consumer có thể bị xem là không còn tiến triển và bị loại khỏi group, dẫn tới rebalance.

Không nên nhầm max.poll.records với số partition hoặc concurrency. Giảm số record mỗi poll có thể giúp listener hoàn thành một batch nhanh hơn, nhưng cũng có thể làm giảm throughput nếu batch quá nhỏ. Tăng max.poll.interval.ms có thể phù hợp với xử lý lâu, nhưng không thay thế việc tối ưu listener hoặc kiểm soát công việc đang chờ.

Với listener xử lý đồng bộ, thời gian xử lý batch cần đủ ngắn để container tiếp tục poll đúng hạn. Nếu xử lý mỗi record quá lâu, hãy xem xét:

1. Giảm max.poll.records để giới hạn số record trong một lần poll.
2. Tối ưu thao tác database hoặc dịch vụ phụ thuộc.
3. Tăng concurrency nếu còn partition chưa được khai thác và tài nguyên cho phép.
4. Tách công việc nặng sang một cơ chế xử lý bất đồng bộ có giới hạn, đồng thời thiết kế ack/offset và xử lý rebalance cẩn thận.
5. Điều chỉnh max.poll.interval.ms khi đã đo được thời gian xử lý thực tế và hiểu tác động tới phục hồi group.

Consumer hiện đại có cơ chế heartbeat riêng, nhưng điều đó không có nghĩa ứng dụng có thể bỏ qua max.poll.interval.ms. Consumer vẫn cần tiếp tục poll trong khoảng thời gian cấu hình để chứng minh tiến trình xử lý đang hoạt động.

## 9. Một consumer xử lý nhiều partition có thể bị nghẽn ra sao?

Giả sử một consumer nhận ba partition. Partition 0 có 100 record mỗi giây, partition 1 có 10 record mỗi giây và partition 2 có 5 record mỗi giây. Nếu listener xử lý mỗi record mất nhiều thời gian, partition có lưu lượng lớn có thể làm tổng thời gian xử lý của consumer tăng và khiến lag tích tụ.

Consumer lag là chênh lệch giữa vị trí record mới nhất và tiến độ consumer group đã xử lý/commit theo cách đo của hệ thống giám sát. Lag cần được xem theo từng partition và theo thời gian, không chỉ nhìn một con số tổng.

Các chỉ số nên quan sát:

- Lag theo từng partition và tổng lag của group.
- Tốc độ record vào topic và tốc độ record được xử lý.
- Thời gian xử lý trung bình, p95 và p99 của listener.
- Số lần rebalance và nguyên nhân.
- Thời gian giữa các lần poll.
- Số record trong một poll và thời gian xử lý batch.
- CPU, heap, garbage collection và số thread.
- Thời gian phản hồi, connection pool và lỗi của database hoặc dịch vụ downstream.

Nếu chỉ một partition có lag cao, nguyên nhân có thể là key skew hoặc một nhóm sự kiện có xử lý nặng. Nếu tất cả partition đều tăng lag, có thể tổng năng lực xử lý của group thấp hơn tốc độ đầu vào hoặc dependency downstream đang nghẽn.

Tăng số consumer chỉ giúp khi có partition chưa được gán và bottleneck nằm ở khả năng xử lý consumer. Nếu đã có một consumer cho mỗi partition mà lag vẫn tăng, hãy tìm bottleneck khác hoặc đánh giá tăng partition.

## 10. Chiến lược mở rộng consumer group

Khi cần tăng throughput, hãy xem xét theo trình tự:

1. Đo lag và tốc độ xử lý hiện tại.
2. Kiểm tra số partition và số consumer member đang hoạt động.
3. Nếu số consumer nhỏ hơn số partition, tăng concurrency hoặc thêm instance để khai thác partition còn trống.
4. Nếu số consumer đã bằng hoặc vượt số partition, tăng consumer thường không tăng song song cho topic đó.
5. Nếu cần nhiều mức song song hơn, cân nhắc tăng partition sau khi đánh giá key ordering và chi phí broker.
6. Kiểm tra database, API downstream và tài nguyên ứng dụng có chịu được tải tăng thêm không.
7. Theo dõi rebalance và lag sau mỗi thay đổi.

Ví dụ topic có sáu partition:

| Cấu hình | Khả năng song song tối đa theo partition | Nhận xét |
|---|---:|---|
| 1 replica, concurrency 1 | 1 | Một consumer xử lý sáu partition. |
| 1 replica, concurrency 3 | 3 | Ba consumer chia sáu partition. |
| 2 replica, concurrency 3 mỗi replica | 6 | Sáu consumer member có thể xử lý sáu partition. |
| 3 replica, concurrency 3 mỗi replica | 6 | Chín member nhưng tối đa sáu member có partition; ba member có thể nhàn rỗi. |

Bảng giả định mỗi replica tạo một listener container cùng group và tất cả cùng subscribe topic sáu partition. Các member khác trong group hoặc subscription khác có thể làm assignment thực tế thay đổi.

Tăng partition không phải thao tác không có hệ quả. Nó có thể thay đổi phân phối key, tăng tài nguyên broker, làm thay đổi assignment và ảnh hưởng cách consumer xử lý các sự kiện cùng aggregate. Hãy coi tăng partition là thay đổi kiến trúc cần kế hoạch và kiểm thử.

## 11. Giới hạn của việc xử lý bất đồng bộ trong một consumer

Một KafkaConsumer không thread-safe. Không nên lấy một consumer rồi gọi poll, commit hoặc seek từ nhiều thread tùy ý. Spring Kafka quản lý consumer trên các thread của listener container; ứng dụng nên làm việc qua các abstraction và cơ chế ack được hỗ trợ.

Nếu listener nhận record rồi đẩy công việc sang thread pool, consumer có thể tiếp tục poll trong khi công việc cũ chưa hoàn tất. Điều này tạo khả năng xử lý song song cao hơn, nhưng cần kiểm soát:

- Giới hạn số công việc đang chạy để không làm đầy heap.
- Ghi nhận partition và offset của từng công việc.
- Chỉ commit offset khi các record trước đó trong partition đã xử lý an toàn.
- Xử lý trường hợp rebalance thu hồi partition khi công việc đang chạy.
- Không để record sau commit vượt qua record trước còn đang thất bại.
- Bảo đảm idempotency nếu record được giao lại sau khi consumer dừng.

Một cách đơn giản và dễ kiểm soát là giữ xử lý đồng bộ trong listener, sau đó tăng concurrency ở cấp container khi số partition cho phép. Chỉ chuyển sang xử lý bất đồng bộ khi có yêu cầu throughput rõ ràng và đã thiết kế cơ chế ack, thứ tự, backpressure và phục hồi.

## 12. Kiểm thử giới hạn consumer và partition assignment

Không nên chỉ kiểm tra số thread được tạo. Cần kiểm tra assignment thực tế và hành vi khi số member thay đổi.

Một số kịch bản kiểm thử:

| Kịch bản | Điều cần xác minh |
|---|---|
| 1 consumer, nhiều partition | Một member có thể nhận nhiều partition. |
| Số consumer bằng số partition | Các partition được phân phối cho các member. |
| Số consumer lớn hơn partition | Một số member không có partition. |
| Thêm consumer trong lúc chạy | Group rebalance và phân phối lại partition. |
| Dừng một consumer | Partition được giao lại cho member còn hoạt động. |
| Tăng partition | Assignment thay đổi và consumer tiếp tục đọc. |
| Listener xử lý chậm | max.poll.interval.ms và rebalance hoạt động như dự kiến. |
| Xử lý bất đồng bộ | Offset không commit vượt quá công việc chưa hoàn tất. |

Có thể dùng EmbeddedKafka để kiểm tra listener và assignment trong các kịch bản đơn giản. Testcontainers phù hợp hơn khi cần mô phỏng nhiều broker hoặc cấu hình gần môi trường triển khai.

Để quan sát assignment, có thể dùng ConsumerRebalanceListener hoặc các event của Spring Kafka listener container. Test nên chờ một điều kiện cụ thể với timeout, ví dụ tất cả partition đã được assign, thay vì dùng Thread.sleep cố định.

Khi test số consumer lớn hơn số partition, hãy kiểm tra tập member có assignment rỗng hoặc số partition được gán cho từng member. Cần nhớ rằng assignment cụ thể phụ thuộc assignor, subscription và thời điểm group ổn định.

## 13. Bài tập tổng hợp: tối ưu consumer group cho orders.created

Hãy xây dựng topic orders.created có sáu partition và một listener Spring Kafka thuộc group fulfillment-service.

Yêu cầu:

1. Chạy một replica với concurrency bằng một và quan sát một consumer nhận nhiều partition.
2. Tăng concurrency lên ba, quan sát cách partition được phân phối lại.
3. Chạy hai replica với concurrency bằng ba, xác minh tối đa sáu member có partition.
4. Tăng tổng số member lên chín và xác định member không được gán partition.
5. Gửi nhiều record với orderId làm key và xác minh các sự kiện cùng key nằm trong cùng partition khi cấu hình partition không đổi.
6. Tạo một listener xử lý chậm để quan sát lag và thời gian giữa các lần poll.
7. Điều chỉnh max.poll.records và đo ảnh hưởng tới thời gian xử lý batch.
8. Thử một tình huống vượt max.poll.interval.ms trong môi trường test và quan sát rebalance.
9. Dừng một consumer rồi xác minh partition được giao lại cho member còn lại.
10. Viết integration test kiểm tra assignment và khả năng đọc record sau rebalance.
11. Theo dõi lag theo partition để xác định có key skew hay không.
12. Đề xuất cấu hình concurrency và số partition dựa trên số liệu đo được.

Sau bài tập, hãy ghi lại số partition, số replica, concurrency mỗi replica, tổng số consumer member, lag, throughput và thời gian xử lý. Không chọn concurrency chỉ dựa trên số CPU; hãy chọn dựa trên partition và bottleneck đã đo.

## 14. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Group model | Consumer member và partition | Giải thích được một partition chỉ thuộc tối đa một member trong group tại một thời điểm. |
| 2. Assignment | Consumer ít hơn, bằng hoặc nhiều hơn partition | Tính được số consumer có thể hoạt động và số member nhàn rỗi. |
| 3. Ordering | Thứ tự trong partition và key | Giải thích được vì sao xử lý async có thể làm đảo thứ tự hoàn tất. |
| 4. Rebalance | Assignment strategy và group membership | Hiểu khi nào partition bị thu hồi và gán lại. |
| 5. Spring concurrency | Listener container concurrency | Tính được tổng consumer member từ số replica và concurrency. |
| 6. Poll loop | max.poll.records và max.poll.interval.ms | Chẩn đoán được listener chậm và nguy cơ rebalance. |
| 7. Scaling | Lag, throughput và dependency | Quyết định tăng consumer hay partition dựa trên số liệu. |
| 8. Testing | EmbeddedKafka và Testcontainers | Kiểm thử được assignment, consumer dư và rebalance. |

Bài học hoàn thành khi bạn có thể tính giới hạn song song của một consumer group theo số partition, cấu hình concurrency trong Spring Kafka, giải thích tác động của poll loop và rebalance, đồng thời dùng consumer lag để xác định nút thắt.

Một consumer không đại diện cho một partition. Nó có thể đọc nhiều partition, nhưng một partition chỉ được giao cho tối đa một consumer trong cùng group tại một thời điểm. Số partition đặt giới hạn cho mức song song của group; concurrency, thời gian xử lý, poll loop và năng lực downstream quyết định group có khai thác được giới hạn đó hay không.

