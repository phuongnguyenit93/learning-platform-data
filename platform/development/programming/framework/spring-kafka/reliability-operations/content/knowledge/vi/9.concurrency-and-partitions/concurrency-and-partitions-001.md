# Chọn concurrency theo số partition

## 1. Concurrency trong Spring Kafka có ý nghĩa gì?

Trong Spring Kafka, concurrency của listener container xác định số Kafka consumer mà container tạo để đọc song song. Mỗi consumer thuộc cùng consumer group sẽ được Kafka gán một hoặc nhiều partition của các topic đã subscribe.

Ví dụ một listener container có concurrency bằng 3:

- Spring tạo ba consumer instance do container quản lý.
- Các consumer dùng chung group ID của listener.
- Kafka phân phối partition giữa ba consumer theo partition assignor.
- Mỗi consumer xử lý record từ các partition được gán cho nó.

Concurrency là mức song song ở phía consumer. Nó không tạo thêm partition và cũng không làm một partition được nhiều consumer trong cùng group xử lý đồng thời. Vì vậy, số partition là giới hạn quan trọng đối với mức song song của một consumer group.

Với một topic có P partition và tổng cộng C consumer trong cùng group:

- Nếu C nhỏ hơn P, một consumer thường được gán nhiều partition.
- Nếu C bằng P, group có thể có một consumer cho mỗi partition.
- Nếu C lớn hơn P, một số consumer không được gán partition và không đóng góp thêm khả năng đọc song song cho topic đó.

Số consumer thực tế phải tính trên toàn bộ các instance ứng dụng đang tham gia cùng group, không chỉ concurrency của một JVM.

## 2. Quan hệ giữa partition và consumer

### 2.1. Partition là đơn vị song song của Kafka

Một topic được chia thành các partition độc lập. Kafka đảm bảo thứ tự record trong một partition, nhưng không đảm bảo thứ tự tổng thể giữa nhiều partition.

Consumer group chia các partition cho các consumer member. Tại một thời điểm, một partition được gán cho tối đa một consumer trong cùng group. Các consumer group khác nhau có thể đọc cùng partition độc lập.

Ví dụ topic có 6 partition:

~~~text
Topic orders
  P0  P1  P2  P3  P4  P5

Consumer group orders-service
  Consumer A -> P0, P1
  Consumer B -> P2, P3
  Consumer C -> P4, P5
~~~

Ba consumer có thể đọc ba nhóm partition song song. Mỗi consumer có thể xử lý record từ partition được gán theo vòng poll của nó.

Nếu chỉ có một partition:

~~~text
Topic orders
  P0

Consumer group orders-service
  Consumer A -> P0
  Consumer B -> idle
  Consumer C -> idle
  Consumer D -> idle
~~~

Dù container tạo bốn consumer, chỉ một consumer nhận partition. Tăng concurrency lên 4 không làm P0 được xử lý bởi bốn consumer cùng lúc.

### 2.2. Một consumer có thể nhận nhiều partition

Partition không yêu cầu một consumer riêng. Một consumer có thể sở hữu nhiều partition và poll record từ tất cả partition đó.

Ví dụ topic có 8 partition, group có 2 consumer:

~~~text
Consumer A -> P0, P1, P2, P3
Consumer B -> P4, P5, P6, P7
~~~

Mức song song tối đa của group vẫn bị giới hạn bởi số partition, nhưng số consumer thấp hơn số partition không làm dữ liệu bị mất. Mỗi consumer chỉ chịu trách nhiệm cho nhiều partition hơn và cần đủ năng lực xử lý tổng tải được gán.

### 2.3. Consumer dư không làm tăng throughput

Nếu số consumer lớn hơn số partition, các consumer dư vẫn có thể kết nối broker, tham gia group coordination và gửi heartbeat, nhưng không có partition để đọc. Chúng không làm topic xử lý nhanh hơn.

Consumer dư còn tạo thêm chi phí:

- Thread, socket và buffer phía client.
- Heartbeat và group coordination.
- Tài nguyên heap, CPU và giám sát.
- Thời gian tham gia hoặc rời group khi deployment và rebalance.

Vì vậy, concurrency nên bắt đầu từ số partition và được điều chỉnh theo tải thực tế, không nên đặt một con số lớn chỉ với kỳ vọng nhiều thread sẽ luôn nhanh hơn.

## 3. Tính tổng concurrency của toàn consumer group

### 3.1. Concurrency trong một instance

Giả sử một ứng dụng có một listener container với concurrency là 3. Container tạo ba consumer trong cùng group.

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
~~~

Nếu topic có 6 partition, mỗi consumer có thể nhận khoảng 2 partition tùy assignor. Nếu topic chỉ có 2 partition, một consumer có thể nhận partition thứ nhất, một consumer nhận partition thứ hai và consumer còn lại idle.

### 3.2. Nhiều replica của ứng dụng

Trong production, một dịch vụ thường chạy nhiều pod hoặc instance. Mỗi instance tạo concurrency riêng cho listener container.

Công thức cần dùng cho một listener container cùng group:

~~~text
Tổng consumer trong group
    = số replica ứng dụng × concurrency mỗi replica

Số consumer có partition hoạt động tối đa
    <= min(tổng consumer trong group, số partition được assign)
~~~

Ví dụ có 3 replica, mỗi replica đặt concurrency là 2:

~~~text
Replica A: 2 consumer
Replica B: 2 consumer
Replica C: 2 consumer

Tổng consumer trong group = 3 × 2 = 6
~~~

Nếu topic có 6 partition, group có thể dùng cả 6 consumer. Nếu topic chỉ có 4 partition, tối đa 4 consumer có partition và ít nhất 2 consumer idle.

| Replica | Concurrency mỗi replica | Tổng consumer | Partition | Consumer có thể active tối đa |
|---:|---:|---:|---:|---:|
| 1 | 3 | 3 | 6 | 3 |
| 2 | 3 | 6 | 6 | 6 |
| 3 | 3 | 9 | 6 | 6 |
| 2 | 2 | 4 | 8 | 4 |
| 4 | 1 | 4 | 4 | 4 |

Bảng giả định một topic, một listener group và assignment có thể phân phối partition cho các consumer. Với nhiều topic, cần tính tổng partition được subscribe và xem thêm assignor.

### 3.3. Phân biệt concurrency và số group

Nếu hai ứng dụng dùng cùng group ID, consumer của chúng chia nhau partition. Tổng concurrency của cả hai ứng dụng cần được tính chung.

Nếu hai ứng dụng dùng group ID khác nhau, mỗi group có tiến độ độc lập và mỗi group có thể nhận toàn bộ partition của topic. Khi đó cả hai ứng dụng đều có thể đọc cùng record, nhưng chúng không làm tăng mức song song của một group; chúng tạo hai luồng tiêu thụ độc lập.

Điều này rất quan trọng khi triển khai service mới. Đổi group ID có thể khiến ứng dụng trở thành một consumer group mới, đọc lại lịch sử hoặc bắt đầu từ cuối log tùy `auto.offset.reset`.

## 4. Chọn concurrency theo số partition

### 4.1. Một topic, một listener group

Với một topic có P partition, đặt tổng consumer trong group gần với P là điểm bắt đầu hợp lý nếu mục tiêu là sử dụng hết khả năng song song ở cấp partition.

| Số partition | Tổng consumer gợi ý ban đầu | Cách phân phối điển hình |
|---:|---:|---|
| 1 | 1 | Một consumer đọc partition duy nhất |
| 2 | 2 | Một consumer mỗi partition |
| 4 | 2 | Hai partition mỗi consumer |
| 6 | 3 | Hai partition mỗi consumer |
| 8 | 4 | Hai partition mỗi consumer |
| 12 | 6 | Hai partition mỗi consumer |
| 12 | 12 | Một consumer mỗi partition |

Đây là điểm bắt đầu để thử nghiệm, không phải quy tắc bắt buộc. Nếu listener xử lý nhẹ và throughput thấp, ít consumer hơn partition có thể đủ. Nếu xử lý nặng và downstream chịu tải, tăng consumer đến gần số partition có thể tăng throughput.

Nếu tổng consumer vượt P, các consumer dư không tăng song song cho topic đó. Nếu tổng consumer thấp hơn P, mỗi consumer sở hữu nhiều partition hơn và tải phải được xử lý trên ít consumer hơn.

### 4.2. Mục tiêu không phải luôn là một consumer mỗi partition

Một consumer có thể đọc nhiều partition hiệu quả nếu listener xử lý nhanh, batch phù hợp và downstream đủ năng lực. Đặt một consumer cho mỗi partition làm tăng số thread và kết nối, đồng thời có thể tăng tải lên database.

Chỉ nên tăng concurrency khi có bằng chứng consumer đang là nút thắt. Nếu consumer lag thấp và listener xử lý nhanh, thêm consumer có thể không mang lại lợi ích.

Ngược lại, nếu lag tăng liên tục, CPU consumer cao và listener là phần xử lý giới hạn, tăng concurrency có thể giúp phân phối tải trên nhiều consumer. Nhưng cần kiểm tra downstream trước vì thêm consumer có thể chỉ làm database hoặc HTTP service quá tải nhanh hơn.

### 4.3. Khi partition count không đủ

Nếu một topic chỉ có 2 partition nhưng cần 8 consumer xử lý độc lập trong cùng group, tăng concurrency lên 8 không giải quyết được giới hạn. Cần đánh giá lại partition count của topic hoặc thiết kế luồng.

Tăng partition count là thay đổi ở topic, không phải chỉ thay đổi cấu hình ứng dụng. Cần cân nhắc:

- Key-to-partition mapping có thể thay đổi.
- Ordering theo key có thể bị ảnh hưởng giữa record cũ và mới.
- Broker cần thêm tài nguyên cho partition và replica.
- Consumer group sẽ phải rebalance khi metadata partition thay đổi.
- Số partition lớn hơn làm tăng metadata và chi phí vận hành.

Không nên tăng partition chỉ để khớp một con số concurrency nếu workload không cần mức song song đó.

## 5. Chọn concurrency khi listener subscribe nhiều topic

Khi một consumer subscribe nhiều topic, khả năng song song phụ thuộc tổng số partition của các topic và partition assignor.

Ví dụ listener subscribe ba topic:

~~~text
orders:       3 partitions
payments:     3 partitions
shipments:    3 partitions

Tổng:         9 partitions
~~~

Về lý thuyết, group có thể có tối đa 9 consumer được gán partition. Tuy nhiên, cách phân phối thực tế còn phụ thuộc assignor và số partition trên từng topic.

### 5.1. Tác động của RangeAssignor

Với `RangeAssignor`, việc phân phối được tính riêng theo từng topic. Khi số consumer lớn hơn số partition của từng topic, một số consumer có thể không nhận partition từ topic nào dù tổng số partition của tất cả topic lớn hơn số consumer.

Ví dụ ba topic đều có 5 partition và group có 15 consumer:

~~~text
orders:       5 partitions
payments:     5 partitions
shipments:    5 partitions
Tổng:        15 partitions

RangeAssignor có thể phân phối theo từng topic:
Consumer 0-4: nhận partition của từng topic
Consumer 5-14: không nhận partition
~~~

Do assignor chia từng topic cho các consumer theo phạm vi, không nên chỉ lấy tổng partition của nhiều topic rồi giả định mọi consumer đều active.

### 5.2. RoundRobinAssignor và CooperativeStickyAssignor

`RoundRobinAssignor` phân phối partition luân phiên giữa các consumer trên các topic đã subscribe, nên có thể tận dụng consumer tốt hơn trong một số topology nhiều topic.

`CooperativeStickyAssignor` kết hợp phân phối cân bằng với khả năng giữ assignment ổn định và cooperative rebalance. Nó cũng có thể giúp tránh việc một nhóm consumer bị idle do cách phân phối theo từng topic, tùy subscription và topology thực tế.

Không nên đổi assignor chỉ để giải quyết một biểu hiện idle mà chưa kiểm tra assignment thực tế. Hãy xem partition được gán cho từng member và thử nghiệm trên cùng topology trước khi thay đổi.

### 5.3. Khi các listener subscribe topic khác nhau

Nếu một ứng dụng có nhiều `@KafkaListener` với subscription khác nhau, mỗi listener container có concurrency riêng. Tổng số consumer và tài nguyên của ứng dụng là tổng của các container, nhưng partition assignment chỉ chia sẻ giữa những consumer có cùng group ID và subscription tương thích.

Ví dụ:

- Listener A đọc `orders` với group `billing-service`.
- Listener B đọc `payments` với group `payment-service`.

Hai group độc lập, mỗi group có tiến độ riêng. Không cộng partition của hai topic để suy ra một giới hạn concurrency chung cho hai group này.

Nếu hai listener cùng dùng `billing-service` và cùng subscribe `orders`, chúng tham gia cùng group; tổng consumer từ cả hai container cần được tính chung. Việc dùng nhiều container cho cùng group cần có chủ đích vì có thể làm assignment và concurrency khó dự đoán hơn.

## 6. Cấu hình concurrency trong Spring Kafka

Có nhiều cách thiết lập concurrency. Chọn một cách phù hợp với cấu trúc ứng dụng và bảo đảm service đang dùng đúng listener container factory.

### 6.1. Spring Boot application.yml

Cấu hình mặc định cho các listener container do Boot tạo:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-service
      enable-auto-commit: false
    listener:
      concurrency: 3
      ack-mode: record
~~~

`spring.kafka.listener.concurrency` đặt concurrency mặc định cho listener container factory do Spring Boot cấu hình. Nó không tự thay đổi số partition của topic.

Nếu có listener cần concurrency khác, có thể khai báo riêng trong annotation hoặc tạo factory riêng.

### 6.2. Khai báo concurrency trong @KafkaListener

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    concurrency = "3"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Thuộc tính `concurrency` của annotation là chuỗi. Giá trị này yêu cầu container tạo số consumer tương ứng cho listener endpoint. Nếu ứng dụng chạy nhiều replica, mỗi replica tạo số consumer theo cấu hình của endpoint đó.

Không nên đồng thời đặt các giá trị khác nhau ở Boot default, factory và annotation mà không hiểu thứ tự ưu tiên. Hãy xác nhận concurrency hiệu lực trong log/container khi khởi động.

### 6.3. Cấu hình qua ConcurrentKafkaListenerContainerFactory

Khi cần một factory riêng cho một nhóm listener:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    return factory;
}
~~~

Gắn factory vào listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Factory này cho phép tách cấu hình concurrency, acknowledgment mode, error handler và các container properties theo loại listener.

Nếu có nhiều listener dùng factory khác nhau nhưng cùng group ID, tổng consumer của group là tổng concurrency thực tế của tất cả container trên mọi replica. Tránh vô tình tạo ra concurrency lớn hơn partition count chỉ vì mỗi factory được cấu hình độc lập.

## 7. Concurrency và số partition khi chạy nhiều replica

Giả sử topic `orders` có 12 partition. Ứng dụng chạy trên 3 pod và mỗi pod cấu hình concurrency là 2.

~~~text
Topic: 12 partitions
Pods:  3
Per-pod concurrency: 2

Total consumers = 3 × 2 = 6
Average partitions per active consumer = 12 / 6 = 2
~~~

Mỗi consumer có thể nhận khoảng hai partition nếu assignor phân phối đều. Nếu tăng mỗi pod lên concurrency 4:

~~~text
Pods: 3
Per-pod concurrency: 4

Total consumers = 3 × 4 = 12
Average partitions per active consumer = 12 / 12 = 1
~~~

Lúc này group có thể dùng một consumer cho mỗi partition. Nếu tăng lên concurrency 6 mỗi pod:

~~~text
Pods: 3
Per-pod concurrency: 6

Total consumers = 3 × 6 = 18
Partitions = 12

At most 12 consumers receive a partition.
At least 6 consumers remain idle.
~~~

Bảng lựa chọn cho topology này:

| Replica | Concurrency mỗi replica | Tổng consumer | Consumer idle tối thiểu |
|---:|---:|---:|---:|
| 3 | 1 | 3 | 0 |
| 3 | 2 | 6 | 0 |
| 3 | 4 | 12 | 0 |
| 3 | 6 | 18 | 6 |

Con số idle tối thiểu giả định một topic có 12 partition và mọi consumer cùng subscribe topic. Nếu subscription nhiều topic hoặc assignor có ràng buộc, cần quan sát assignment thực tế.

Khi autoscaling, số consumer thay đổi theo số replica. Nếu concurrency mỗi pod đã bằng partition count, phần lớn consumer mới sẽ idle và group vẫn phải rebalance. Có thể đặt concurrency mỗi pod theo ngân sách consumer toàn group và giới hạn replica phù hợp.

## 8. Các yếu tố ngoài số partition cần cân nhắc

Partition count đặt giới hạn trên cho song song trong một group, nhưng không tự quyết định concurrency tối ưu. Cần xem tải xử lý và tài nguyên của consumer.

### 8.1. Thời gian xử lý mỗi record

Nếu một listener mất 5 ms để xử lý record, một consumer có thể xử lý nhiều record mỗi giây. Nếu listener mất 500 ms vì truy vấn database hoặc gọi API, một consumer có throughput thấp hơn đáng kể.

Đo các chỉ số:

- Processing duration trung bình, p95 và p99.
- Record rate vào topic.
- Record rate được consumer xử lý.
- Consumer lag theo partition.
- Thời gian chờ database và service ngoài.

Nếu CPU còn dư nhưng listener chờ I/O nhiều, thêm concurrency có thể tăng throughput đến giới hạn downstream. Nếu CPU đã bão hòa, thêm consumer có thể làm context switching và contention tăng.

### 8.2. Năng lực database và downstream

Mỗi consumer có thể tạo thêm yêu cầu đến database, HTTP service, cache hoặc hệ thống khác. Trước khi tăng concurrency, kiểm tra:

- Database connection pool có đủ kết nối không.
- Downstream có giới hạn request hoặc rate limit không.
- Transaction database có giữ lock lâu không.
- API ngoài có tăng latency hoặc trả 429/5xx khi tải tăng không.
- Có đủ thread và connection cho các phần khác của ứng dụng không.

Nếu database chỉ chịu được 10 transaction đồng thời, cấu hình 30 consumer có thể tạo queue và timeout thay vì tăng tốc độ. Concurrency cần phù hợp với năng lực xử lý đầu cuối, không chỉ với số partition.

### 8.3. CPU, heap và thread

Một consumer thường có thread xử lý riêng trong concurrent container và tài nguyên client như network buffer, metadata và heartbeat. Tăng concurrency làm tăng số thread và chi phí quản lý.

Đánh giá:

- Số core CPU và tỷ lệ CPU sử dụng.
- Heap, garbage collection và số object tạo ra.
- Số kết nối broker.
- Thread pool và connection pool của ứng dụng.
- Tài nguyên dành cho web request hoặc scheduler cùng JVM.

Không có quy tắc cố định rằng concurrency phải bằng số core CPU. Listener I/O-bound có thể dùng nhiều consumer hơn số core; listener CPU-bound có thể đạt tối ưu ở mức gần số core hoặc thấp hơn. Cần đo trong tải thật.

### 8.4. Kích thước poll và thời gian xử lý

`max.poll.records` giới hạn số record trả về trong một lần poll. Nó không tạo thêm consumer và không thay thế concurrency.

Nếu mỗi poll trả quá nhiều record, listener có thể xử lý lâu và vượt `max.poll.interval.ms`, dẫn đến rebalance. Nếu giảm quá thấp, overhead poll và commit có thể tăng.

Hãy điều chỉnh đồng thời:

- Concurrency.
- `max.poll.records`.
- Thời gian xử lý record/batch.
- `max.poll.interval.ms`.
- Batch listener hay record listener.
- Acknowledgment mode và error handler.

Mục tiêu là giữ consumer tiếp tục poll trong giới hạn và không để batch quá lớn so với thời gian xử lý cho phép.

## 9. Concurrency, ordering và key distribution

### 9.1. Ordering chỉ được đảm bảo trong một partition

Nếu các event của cùng order ID dùng order ID làm key, Kafka thường định tuyến chúng vào cùng partition. Một consumer trong group xử lý partition đó và thứ tự record được giữ theo offset.

Tăng concurrency không làm các event cùng partition được xử lý đồng thời bởi nhiều consumer trong cùng group. Đây là điều cần thiết để giữ thứ tự cơ bản của partition.

~~~text
orders partition P2:
Order-42 Created -> Order-42 Paid -> Order-42 Shipped

Một consumer sở hữu P2
        |
        v
Xử lý theo thứ tự offset
~~~

Nếu listener chuyển công việc sang thread pool rồi xử lý bất đồng bộ, thứ tự side effect có thể bị phá vỡ dù Kafka vẫn giao record theo thứ tự. Khi ordering nghiệp vụ quan trọng, phải quản lý thứ tự hoàn tất trong ứng dụng hoặc giữ xử lý tuần tự theo partition/key.

### 9.2. Hot partition và key skew

Số partition nhiều không bảo đảm tải được phân phối đều. Nếu phần lớn record có cùng key hoặc một vài key nóng, chúng có thể tập trung vào một partition.

Ví dụ:

~~~text
P0: 80% traffic
P1:  5% traffic
P2:  5% traffic
P3:  5% traffic
P4:  5% traffic
~~~

Tăng concurrency từ 5 lên 10 không giúp chia P0 cho hai consumer trong cùng group. Một consumer vẫn chịu phần lớn tải của partition nóng.

Cần xem record rate và lag theo partition. Nếu key distribution lệch, cân nhắc thay đổi key strategy, tách workload hoặc tăng partition theo thiết kế phù hợp. Không đổi key tùy tiện nếu ordering theo aggregate là yêu cầu.

### 9.3. Một partition có thể là giới hạn throughput

Nếu một partition nóng đã dùng hết năng lực xử lý của một consumer, tăng concurrency không thể làm partition đó nhanh hơn. Các giải pháp có thể gồm:

- Tối ưu thời gian xử lý listener.
- Giảm round trip đến database/downstream.
- Batch thao tác phù hợp.
- Thiết kế lại key nếu nghiệp vụ cho phép phân tán một aggregate.
- Chia luồng dữ liệu thành các topic/partition khác nhau khi có thể thay đổi semantics.

Việc chia một key thành nhiều partition có thể phá vỡ ordering của key đó. Cần quyết định dựa trên yêu cầu nghiệp vụ, không chỉ dựa trên throughput.

## 10. Batch listener và concurrency

Spring Kafka hỗ trợ record listener và batch listener. Concurrency xác định số consumer; listener type xác định cách record được chuyển đến phương thức xử lý.

### 10.1. Record listener

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    concurrency = "4"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Mỗi lần gọi listener xử lý một record. Một consumer có thể nhận record từ nhiều partition được gán. Concurrency tạo nhiều consumer để các partition được xử lý song song.

### 10.2. Batch listener

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    concurrency = "4"
)
public void onOrders(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

Với batch listener, một lần gọi phương thức nhận một nhóm record từ poll. Batch có thể chứa record từ nhiều partition. Cần kiểm soát xử lý lỗi, commit và thứ tự theo từng partition trong batch.

Batch listener có thể giảm overhead khi downstream hỗ trợ thao tác hàng loạt. Nhưng batch lớn cũng làm thời gian xử lý mỗi poll dài hơn, tăng nguy cơ vượt `max.poll.interval.ms` và làm tăng phạm vi retry khi có lỗi.

Concurrency và batch size giải quyết hai khía cạnh khác nhau:

- Concurrency tăng số consumer xử lý partition song song.
- Batch size điều chỉnh số record được xử lý trong một lần poll hoặc một lần gọi listener.

Không nên tăng cả hai cùng lúc nếu chưa đo, vì khó biết thay đổi nào giúp throughput hoặc gây ra lỗi.

## 11. Chọn concurrency khi dùng nhiều listener container

Một ứng dụng có thể có nhiều `@KafkaListener`, mỗi listener dùng một topic, group ID hoặc container factory riêng.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    concurrency = "3"
)
public void onOrder(OrderCreated event) {
    billingService.process(event);
}

@KafkaListener(
    topics = "payments",
    groupId = "payment-service",
    concurrency = "2"
)
public void onPayment(PaymentCompleted event) {
    paymentService.process(event);
}
~~~

Hai listener có group ID khác nhau, do đó concurrency của chúng độc lập. Ứng dụng tạo tổng cộng 5 consumer cho hai container trên mỗi replica. Khi chạy nhiều replica, nhân concurrency của từng container với số replica tương ứng.

Nếu cùng group ID và cùng subscription, consumer từ nhiều listener container có thể cùng tham gia một group. Cần tính tổng consumer và kiểm tra assignment, không chỉ nhìn từng annotation.

Nếu các listener có workload khác nhau, nên dùng container factory riêng để điều chỉnh concurrency, ack mode, error handler và các thuộc tính consumer độc lập. Một listener xử lý I/O nặng có thể cần concurrency khác listener xử lý CPU-bound.

## 12. Quy trình xác định concurrency phù hợp

Thực hiện theo từng bước để tránh cấu hình dư consumer hoặc làm quá tải downstream.

### Bước 1: Xác định topology

Ghi lại:

- Topic mà listener subscribe.
- Số partition của từng topic.
- Group ID của listener.
- Số replica ứng dụng.
- Concurrency mỗi replica.
- Partition assignor đang sử dụng.
- Các listener container khác dùng chung group ID.

Tính tổng consumer dự kiến trên toàn group trước khi chỉnh cấu hình.

### Bước 2: Đo tải hiện tại

Theo dõi:

- Producer record rate.
- Consumer record rate.
- Consumer lag tổng và theo partition.
- Processing duration p50/p95/p99.
- CPU, heap và GC.
- Database connection usage và query latency.
- Downstream latency, error và rate limit.
- Rebalance count và thời gian rebalance.

Nếu lag thấp và processing duration ổn định, chưa có lý do rõ ràng để tăng concurrency.

### Bước 3: Tìm partition nóng

So sánh record rate và lag của từng partition. Nếu một partition có lag cao trong khi các partition khác thấp, tăng concurrency tổng thể có thể không giải quyết được. Kiểm tra key distribution và thời gian xử lý partition nóng.

### Bước 4: Tăng từng mức có kiểm soát

Tăng concurrency theo bước nhỏ, ví dụ từ 2 lên 3 hoặc 4, rồi quan sát cùng một khoảng thời gian tải. Không nhảy thẳng từ 2 lên 20 nếu chưa biết giới hạn của database và JVM.

Nếu chạy nhiều replica, điều chỉnh concurrency mỗi replica hoặc replica count sao cho tổng consumer trong group không vượt quá mức hữu ích.

### Bước 5: So sánh kết quả

Một lần tăng concurrency có ích khi:

- Consumer throughput tăng.
- Consumer lag giảm hoặc ổn định ở mức chấp nhận được.
- Processing duration không tăng đáng kể.
- Database và downstream vẫn nằm trong giới hạn.
- CPU, heap và thread vẫn có headroom.
- Rebalance không tăng bất thường.

Nếu consumer count tăng nhưng throughput không đổi, tìm bottleneck ở partition skew, downstream hoặc listener trước khi tiếp tục tăng.

### Bước 6: Ghi lại giới hạn vận hành

Lưu lại concurrency hiệu quả, số replica tối đa, partition count và các metric tại tải cao. Khi partition count hoặc workload thay đổi, đánh giá lại thay vì giữ nguyên một giá trị mãi mãi.

## 13. Bảng quyết định nhanh

| Quan sát | Điều nên cân nhắc |
|---|---|
| Tổng consumer nhỏ hơn partition, lag tăng, downstream còn headroom | Tăng concurrency hoặc replica để tận dụng partition |
| Tổng consumer bằng partition, lag vẫn tăng | Tìm bottleneck ở listener, key skew, CPU hoặc downstream |
| Tổng consumer lớn hơn partition, nhiều member idle | Giảm concurrency hoặc replica nếu không có workload khác cần chúng |
| Một partition lag cao, partition khác thấp | Điều tra hot key và phân phối tải; tăng consumer chung thường không giúp |
| Database pool cạn sau khi tăng concurrency | Giảm consumer hoặc tăng năng lực database có kiểm soát |
| CPU cao và listener CPU-bound | Tối ưu code; tăng concurrency có thể làm contention nặng hơn |
| Listener I/O-bound, CPU còn dư và downstream chịu được | Thử tăng concurrency từng bước |
| Rebalance tăng sau autoscaling | Kiểm soát số replica, rollout và thời gian khởi động |
| Nhiều topic nhưng một số consumer idle với RangeAssignor | Xem assignment theo từng topic và thử assignor phù hợp |

## 14. Ví dụ tính toán thực tế

### Trường hợp A: 8 partition, 2 replica

Topic `orders` có 8 partition. Ứng dụng chạy 2 replica.

Nếu mỗi replica đặt concurrency là 2:

~~~text
Total consumers = 2 × 2 = 4
Partitions = 8
Average = 2 partitions / consumer
~~~

Đây là điểm bắt đầu hợp lý nếu mỗi consumer xử lý được hai partition và lag không tăng.

Nếu tăng concurrency lên 4 mỗi replica:

~~~text
Total consumers = 2 × 4 = 8
Partitions = 8
Average = 1 partition / consumer
~~~

Có thể tăng song song, nhưng phải đo database và listener throughput.

### Trường hợp B: 4 partition, 4 replica

Nếu mỗi replica đặt concurrency là 2:

~~~text
Total consumers = 4 × 2 = 8
Partitions = 4
Active consumers <= 4
Idle consumers >= 4
~~~

Nếu không có lý do khác để giữ 8 consumer trong group, giảm concurrency xuống 1 mỗi replica sẽ tránh tạo consumer dư.

### Trường hợp C: 12 partition, 1 replica

Một JVM có concurrency 12 có thể tạo một consumer cho mỗi partition. Nhưng nếu listener CPU-bound và máy chỉ có 4 core, 12 thread xử lý đồng thời có thể tạo contention.

Thử concurrency 4, 6 và 12 dưới cùng tải, so sánh throughput, lag, CPU, GC và downstream. Mức tối ưu là mức đáp ứng SLA với chi phí tài nguyên chấp nhận được, không nhất thiết là 12.

### Trường hợp D: 1 partition nóng trong topic 8 partition

Topic có 8 partition nhưng P3 nhận phần lớn traffic do key skew. Concurrency 8 vẫn không chia P3 cho nhiều consumer trong cùng group.

Cần phân tích key, record size và processing time trên P3. Nếu nghiệp vụ cho phép, có thể thay đổi key design hoặc tách luồng. Nếu không, tối ưu listener và downstream cho partition nóng.

## 15. Những lỗi cấu hình thường gặp

**Đặt concurrency lớn hơn partition count:** tạo consumer idle, tăng tài nguyên và group coordination mà không tăng throughput cho topic.

**Chỉ tính concurrency trong một pod:** bỏ qua số replica và tổng consumer của group. Khi autoscaling, tổng consumer có thể vượt partition count.

**Nhầm concurrency với partition count:** concurrency không tự tạo partition và không tăng giới hạn song song của một partition.

**Tăng concurrency để chữa hot partition:** partition nóng vẫn chỉ được một consumer trong group sở hữu tại một thời điểm.

**Bỏ qua downstream:** thêm consumer có thể làm database connection pool cạn hoặc service ngoài bị rate limit.

**Dùng một concurrency cho mọi listener:** workload khác nhau có thể cần mức song song khác nhau; dùng container factory riêng khi cần.

**Nhầm max.poll.records với concurrency:** max.poll.records điều chỉnh số record trả về mỗi poll, không tạo thêm consumer.

**Không theo dõi rebalance:** tăng số consumer làm thay đổi assignment, có thể gây gián đoạn trong rollout hoặc autoscaling.

**Xử lý bất đồng bộ không kiểm soát:** listener trả về hoặc commit offset khi task nền chưa hoàn tất có thể gây mất ordering hoặc xử lý trùng.

**Cho rằng một consumer chỉ đọc một partition:** một consumer có thể sở hữu nhiều partition; điều này bình thường khi số consumer thấp hơn số partition.

## 16. Nguyên tắc vận hành trong production

- Tính tổng consumer trên toàn group bằng replica nhân concurrency của từng listener container.
- Với một topic, dùng partition count làm giới hạn trên cho số consumer có thể active trong group.
- Bắt đầu với concurrency phù hợp số partition và tải thực tế; không mặc định một consumer cho mỗi partition là tối ưu.
- Nếu subscribe nhiều topic, kiểm tra assignment theo từng topic và assignor đang dùng.
- Theo dõi lag theo partition để nhận diện hot partition.
- Đo processing duration, CPU, heap, database pool và downstream trước khi tăng concurrency.
- Điều chỉnh concurrency theo bước nhỏ và so sánh throughput trong cùng điều kiện tải.
- Phối hợp concurrency với replica count, `max.poll.records`, `max.poll.interval.ms` và acknowledgment mode.
- Giữ ordering theo partition/key; quản lý cẩn thận nếu listener xử lý bất đồng bộ.
- Khi cần thêm mức song song vượt partition count, đánh giá việc tăng partition hoặc thay đổi thiết kế key với tác động ordering và vận hành.

Concurrency nên được chọn dựa trên số partition, số replica và năng lực xử lý đầu cuối. Partition đặt giới hạn song song trong consumer group; concurrency quyết định có bao nhiêu consumer cạnh tranh để nhận các partition đó. Chọn đúng mức giúp tận dụng partition, kiểm soát tài nguyên và tránh tạo consumer dư mà không tăng throughput.
