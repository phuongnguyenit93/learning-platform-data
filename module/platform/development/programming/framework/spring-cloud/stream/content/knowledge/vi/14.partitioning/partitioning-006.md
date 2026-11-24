# Khác biệt phân vùng trên Kafka và RabbitMQ

Phân vùng (partitioning) chia một luồng dữ liệu thành nhiều phần để tăng khả năng xử lý song song và giữ các sự kiện liên quan ở cùng một đơn vị xử lý. Trong Spring Cloud Stream, ứng dụng có thể khai báo khóa phân vùng và số partition theo một mô hình chung. Tuy nhiên, Kafka và RabbitMQ triển khai mô hình này theo hai cách khác nhau.

Kafka có partition như một cấu trúc lưu trữ và phân phối native của topic. Mỗi partition là một log có thứ tự riêng; consumer group phân chia các partition cho các consumer. RabbitMQ không có partition native theo nghĩa này. Rabbit binder của Spring Cloud Stream mô phỏng phân vùng bằng cách tạo một queue cho mỗi partition và bind các queue đó vào destination exchange. Vì vậy, cách mở rộng, phân phối tải, quản lý consumer và bảo đảm thứ tự giữa hai broker không giống nhau.

Bài học tập trung vào ngữ nghĩa partition của từng broker, cách Spring Cloud Stream chọn partition theo key, cấu hình producer và consumer, vận hành nhiều instance, thay đổi số partition, xử lý lỗi và kiểm thử. Mục tiêu là giúp chọn mô hình phù hợp với yêu cầu về thứ tự, throughput và khả năng mở rộng của ứng dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích partition trong Kafka và cách RabbitMQ binder mô phỏng partition.
- Phân biệt topic partition, consumer group, exchange, queue và routing.
- Chọn partition key ổn định để các sự kiện cùng thực thể được đưa về cùng partition.
- Cấu hình partition key, partition count và consumer instance trong Spring Cloud Stream.
- Hiểu cách Kafka rebalance partition và cách Rabbit binder gắn instance với queue.
- Phân tích tác động của số partition đến thứ tự, tải, độ trễ và khả năng scale.
- Kiểm thử việc phân phối key, thứ tự và hành vi khi một instance gặp sự cố.

## 1. Vì sao cần phân vùng?

Giả sử một hệ thống thương mại điện tử phát sự kiện đơn hàng. Một đơn hàng có thể phát sinh các sự kiện:

- OrderCreated: đơn hàng được tạo.
- PaymentAuthorized: thanh toán được xác nhận.
- OrderPacked: đơn hàng đã được đóng gói.
- OrderShipped: đơn hàng được bàn giao cho đơn vị vận chuyển.

Các sự kiện của cùng một đơn hàng thường cần được xử lý theo thứ tự nghiệp vụ. Nếu OrderShipped được xử lý trước OrderCreated, trạng thái đơn hàng có thể sai. Đồng thời, hệ thống có hàng nghìn đơn hàng mỗi giây nên một consumer đơn lẻ có thể không đủ khả năng xử lý.

Partitioning giải quyết hai yêu cầu:

1. **Song song hóa**: chia luồng dữ liệu thành nhiều partition để nhiều consumer xử lý đồng thời.
2. **Giữ affinity theo khóa**: các sự kiện có cùng khóa, ví dụ orderId, được đưa về cùng partition để có thể xử lý tuần tự trong phạm vi partition đó.

Partitioning không tự tạo ra thứ tự toàn cục. Nó tạo ra các miền thứ tự độc lập. Nếu hệ thống có sáu partition, thứ tự giữa các sự kiện trong cùng một partition có thể được giữ theo cơ chế của broker; không có một thứ tự tổng thể giữa cả sáu partition.

## 2. Mô hình partition chung của Spring Cloud Stream

Spring Cloud Stream cung cấp một trừu tượng chung cho partitioning, kể cả khi broker có hỗ trợ native hoặc không hỗ trợ native. Mô hình này có hai phía:

- **Producer** xác định partition key của mỗi message và tính partition đích.
- **Consumer** được cấu hình để nhận đúng partition hoặc nhóm partition tương ứng với instance của ứng dụng.

Một output binding có thể cấu hình partition key bằng một trong hai cách:

- partitionKeyExpression: biểu thức SpEL lấy khóa từ message.
- partitionKeyExtractorName: tên bean triển khai PartitionKeyExtractorStrategy.

Hai cách lấy khóa này loại trừ lẫn nhau. Sau khi lấy được key, framework chọn partition trong khoảng từ 0 đến partitionCount - 1. Mặc định, Spring Cloud Stream sử dụng phép tính dựa trên hashCode của key và partitionCount. Có thể tùy chỉnh cách chọn partition bằng partitionSelectorExpression hoặc một bean PartitionSelectorStrategy.

Ví dụ cấu hình chung:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.partitioned
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
~~~

Trong ví dụ:

- publishOrder-out-0 là output binding của hàm phát sự kiện.
- destination là tên destination logic mà binder ánh xạ sang broker.
- partition-key-expression lấy orderId từ payload.
- partition-count khai báo số partition dự kiến cho luồng.

Với key orderId, các sự kiện cùng đơn hàng được ánh xạ về cùng partition nếu producer sử dụng cùng thuật toán và cùng số partition. Đây là nền tảng để duy trì thứ tự xử lý theo đơn hàng.

### 2.1. Chọn key và chọn partition là hai bước

Không nên nhầm partition key với partition ID:

1. **Partition key** là giá trị đại diện cho thực thể hoặc nhóm dữ liệu, ví dụ customerId hoặc orderId.
2. **Partition selector** biến key thành số partition cụ thể.

Ví dụ, key order-100 có thể được băm thành partition 3 trong cấu hình sáu partition. Key order-101 có thể được đưa vào partition 1. Kết quả chính xác phụ thuộc thuật toán selector và số partition.

Key nên có các đặc điểm:

- Ổn định trong toàn bộ vòng đời của thực thể.
- Được tạo giống nhau ở mọi producer phát cùng luồng.
- Có đủ độ phân tán để tránh một partition nhận quá nhiều tải.
- Có quan hệ với yêu cầu thứ tự nghiệp vụ.

Nếu cần thứ tự theo đơn hàng, dùng orderId. Nếu cần thứ tự theo khách hàng, dùng customerId. Không chọn key ngẫu nhiên cho từng message vì các sự kiện liên quan sẽ bị phân tán sang nhiều partition.

### 2.2. Cấu hình phía consumer

Một input binding nhận dữ liệu đã được partition có thể khai báo:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.partitioned
          group: order-processor
          consumer:
            partitioned: true
~~~

partitioned cho biết consumer nhận dữ liệu từ producer đã phân vùng. Các thuộc tính instanceIndex và instanceCount xác định vị trí của instance trong nhóm triển khai khi binder cần ánh xạ partition tới instance:

- instanceCount là tổng số instance của ứng dụng trong mô hình phân vùng.
- instanceIndex là chỉ số duy nhất của instance, bắt đầu từ 0 và nhỏ hơn instanceCount.

Ví dụ ba instance có instanceCount bằng 3 và lần lượt có instanceIndex là 0, 1, 2. Việc cấu hình chính xác rất quan trọng với binder không có cơ chế phân phối partition native.

## 3. Partition native trong Kafka

### 3.1. Topic và partition

Kafka tổ chức dữ liệu theo topic. Một topic có thể có một hoặc nhiều partition. Mỗi partition là một log append-only có thứ tự riêng. Record mới được ghi vào cuối log của partition và được định danh bằng offset trong partition đó.

Các đặc điểm quan trọng:

- Thứ tự được bảo đảm trong phạm vi một partition.
- Mỗi partition có offset độc lập.
- Một consumer group chia các partition của topic cho các consumer thành viên.
- Một partition trong cùng consumer group tại một thời điểm được gán cho tối đa một consumer.
- Nhiều consumer group có thể đọc cùng topic độc lập với offset riêng.

Ví dụ topic orders có sáu partition. Group order-processor chạy ba consumer. Kafka có thể gán hai partition cho mỗi consumer. Nếu tăng số consumer lên sáu, mỗi consumer có thể nhận một partition. Nếu chạy mười consumer, ít nhất bốn consumer sẽ không có partition nào để đọc trong group đó.

### 3.2. Producer chọn partition

Producer có thể chọn partition theo key. Với Spring Cloud Stream, partitionKeyExpression xác định key ở tầng trừu tượng của framework; partition selector quyết định partition index. Kafka binder sau đó gửi record tới partition tương ứng.

Ví dụ cấu hình đầy đủ:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
~~~

Kafka binder sử dụng partitionCount như một gợi ý khi xác định partitioning; số partition thực tế của topic cũng được tính đến. Nếu topic đã có số partition lớn hơn partitionCount cấu hình, binder sử dụng số lớn hơn. Vì vậy, hãy tạo topic với số partition phù hợp và kiểm tra metadata topic khi triển khai.

Partition key ở tầng Spring Cloud Stream và record key của Kafka có liên quan đến việc định tuyến nhưng không nên tự động coi chúng là cùng một khái niệm trong mọi cấu hình. Nếu ứng dụng cần Kafka record key để compact topic hoặc phục vụ consumer khác, hãy cấu hình và kiểm thử record key riêng theo khả năng của Kafka binder.

### 3.3. Consumer group và rebalance

Trong chế độ mặc định, Kafka quản lý việc phân phối partition giữa các consumer cùng group thông qua cơ chế group coordination và rebalance. Khi một consumer tham gia, rời đi hoặc mất kết nối, Kafka có thể phân phối lại partition.

Ví dụ:

~~~text
Topic orders: P0 P1 P2 P3 P4 P5

Group order-processor, 3 consumer:
Consumer A <- P0, P1
Consumer B <- P2, P3
Consumer C <- P4, P5
~~~

Khi Consumer B dừng, Kafka sẽ thực hiện rebalance và gán lại P2, P3 cho các consumer còn lại theo assignor và trạng thái group.

Với Kafka binder, autoRebalanceEnabled mặc định là true. Khi bật cơ chế này, Kafka tự phân phối partition và thường không cần cấu hình instanceIndex/instanceCount cho consumer. Nếu tắt autoRebalanceEnabled, binder có thể dùng instanceCount và instanceIndex để xác định partition nào thuộc về từng instance; khi đó phải có ít nhất số partition tương ứng với số instance và cấu hình chỉ số chính xác.

Rebalance có thể tạm dừng việc tiêu thụ trong một khoảng thời gian. Ứng dụng cần xử lý shutdown, commit offset và tác vụ đang chạy cẩn thận để tránh xử lý trùng hoặc kéo dài thời gian phục hồi.

### 3.4. Giới hạn song song và thứ tự

Trong một consumer group, số consumer đang thực sự nhận dữ liệu không thể vượt số partition được gán. Số partition vì thế đặt ra giới hạn song song ở cấp group.

Nếu sáu partition được chia cho ba consumer, mỗi consumer có thể xử lý hai partition. Tuy nhiên, nếu mỗi consumer xử lý message đồng thời bằng nhiều thread, thứ tự hoàn tất tác vụ có thể khác thứ tự đọc. Khi cần giữ thứ tự nghiệp vụ, hãy giới hạn concurrency xử lý trên cùng partition hoặc dùng cơ chế tuần tự hóa phù hợp.

Không có thứ tự tổng thể giữa các partition. Nếu một đơn hàng có các sự kiện cần tuần tự, tất cả sự kiện của đơn hàng phải dùng cùng orderId làm key và cùng quy tắc phân vùng.

## 4. RabbitMQ không có partition native

### 4.1. Exchange và queue

RabbitMQ sử dụng exchange để định tuyến message tới queue. Queue lưu message đang chờ consumer nhận và xác nhận. Exchange không phải một log được chia partition như topic của Kafka.

RabbitMQ không hỗ trợ partitioning native theo nghĩa topic partition. RabbitMQ binder của Spring Cloud Stream cung cấp partitioning bằng cách tạo một queue cho mỗi partition và bind các queue này vào destination exchange.

Có thể hình dung:

~~~text
Producer
   |
   v
Topic exchange: orders.partitioned
   |             |             |
   v             v             v
Queue P0       Queue P1       Queue P2
   |             |             |
Consumer 0    Consumer 1    Consumer 2
~~~

Producer tính partition từ key. Binder định tuyến message tới queue tương ứng với partition đó. Consumer instance được cấu hình để đọc queue của partition được gán.

Điểm quan trọng là partition trong Rabbit binder là cấu trúc được tạo bởi binder trên các queue và binding. Nó không biến RabbitMQ thành Kafka; semantics lưu trữ, acknowledgement, redelivery và scale vẫn là semantics của RabbitMQ.

### 4.2. Cấu hình producer RabbitMQ

Ví dụ cấu hình producer phân vùng:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.partitioned
          producer:
            partitioned: true
            partition-key-expression: payload.orderId
            partition-count: 3
            required-groups:
              - order-processor
~~~

Trong Rabbit binder:

- partitioned: true bật cơ chế phân vùng của binder.
- partition-key-expression lấy khóa từ message.
- partition-count xác định số queue phân vùng cần tạo.
- required-groups khai báo consumer group cần được provision ngay cả khi consumer chưa triển khai.

required-groups có ý nghĩa quan trọng với RabbitMQ. Nếu producer gửi message vào một partition exchange nhưng queue của group tương ứng chưa được tạo, message có thể không được giữ lại cho consumer triển khai sau. Khai báo required-groups giúp binder tạo trước các queue cần thiết khi producer được triển khai.

### 4.3. Cấu hình consumer RabbitMQ

Consumer cần bật partitioned và xác định instance index:

~~~yaml
spring:
  cloud:
    stream:
      instance-count: 3
      instance-index: 0
      bindings:
        processOrder-in-0:
          destination: orders.partitioned
          group: order-processor
          consumer:
            partitioned: true
            instance-index: 0
~~~

Với ba partition, các instance cần được triển khai với chỉ số riêng:

| Instance | instance-count | instance-index | Queue phân vùng được nhận |
|---|---:|---:|---|
| A | 3 | 0 | P0 |
| B | 3 | 1 | P1 |
| C | 3 | 2 | P2 |

Giá trị instance-index phải duy nhất trong tập instance và nằm trong khoảng từ 0 đến instance-count - 1. Với Rabbit binder, cấu hình này giúp binder xác định queue phân vùng mà instance sẽ tiêu thụ.

Rabbit binder không hỗ trợ dynamic scaling cho mô hình partitioned consumer theo cách Kafka group rebalance thực hiện. Cần có ít nhất một consumer cho mỗi partition và phải triển khai các instance với index tương ứng. Nếu thay đổi số instance hoặc partition, cần lập kế hoạch thay đổi topology và cấu hình đồng bộ.

## 5. So sánh Kafka và RabbitMQ

| Khía cạnh | Kafka | RabbitMQ binder |
|---|---|---|
| Partition native | Có, nằm trong topic | Không; binder mô phỏng bằng queue |
| Cấu trúc chính | Topic, partition, log, offset | Exchange, queue, binding, acknowledgement |
| Định tuyến theo key | Chọn partition của topic | Chọn queue phân vùng gắn với exchange |
| Tiến độ consumer | Offset theo partition và group | Trạng thái message trong queue và acknowledgement |
| Phân phối consumer | Kafka group coordinator và rebalance | Instance index ánh xạ tới queue phân vùng |
| Scale consumer | Có thể thêm/bớt consumer; Kafka rebalance | Không hỗ trợ dynamic scaling của partitioned consumer; cần instance theo partition |
| Đọc lại | Có thể seek/đọc lại offset trong thời gian retention | Message đã ack thường bị loại khỏi queue; không có offset log tương đương |
| Thứ tự | Trong một partition | Theo queue; xử lý đồng thời/redelivery có thể ảnh hưởng thứ tự hoàn tất |
| Provisioning | Topic và partition | Exchange, queue và binding |
| Cấu hình đặc biệt | autoRebalanceEnabled, consumer group và topic | partitioned, instanceIndex, requiredGroups |

Spring Cloud Stream giúp dùng chung cách khai báo key và partition count, nhưng không làm cho các broker có cùng hành vi. Khi chuyển binder, cần xem lại topology, khả năng đọc lại, consumer lifecycle và cách vận hành.

## 6. Chọn partition key đúng

### 6.1. Key theo thực thể nghiệp vụ

Nếu cần thứ tự theo đơn hàng, chọn orderId:

~~~java
@Bean
Function<OrderCommand, OrderEvent> toOrderEvent() {
    return command -> new OrderEvent(
            command.orderId(), command.type(), command.createdAt());
}
~~~

Với binding output, dùng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        toOrderEvent-out-0:
          destination: orders.partitioned
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
~~~

Nếu yêu cầu thứ tự theo khách hàng, thay key bằng customerId. Key phải đại diện cho miền thứ tự cần bảo vệ. Một hệ thống có thể cần hai luồng khác nhau nếu vừa cần thứ tự theo orderId vừa cần thứ tự theo customerId; một partition key duy nhất không thể bảo đảm đồng thời mọi thứ tự độc lập.

### 6.2. Tránh hot partition

Nếu một key chiếm phần lớn lưu lượng, mọi message của key đó tập trung vào một partition. Ví dụ, nếu tất cả sự kiện của một khách hàng lớn đều dùng cùng customerId, partition tương ứng có thể quá tải trong khi partition khác nhàn rỗi.

Đây là trade-off giữa thứ tự và phân tán tải:

- Key quá rộng có thể phân tán sự kiện liên quan, làm mất thứ tự theo thực thể.
- Key quá tập trung có thể tạo hot partition.
- Key ngẫu nhiên phân tán tải tốt hơn nhưng không giữ affinity.

Hãy đo phân phối key thực tế, throughput theo partition, consumer lag hoặc queue depth trước khi chọn chiến lược. Nếu một thực thể có lưu lượng quá lớn, cần xem lại yêu cầu thứ tự hoặc chia nhỏ miền xử lý bằng một mô hình nghiệp vụ khác.

### 6.3. Hash và tính ổn định

Spring Cloud Stream mặc định chọn partition bằng phép tính dựa trên hashCode của key và partitionCount. Nếu producer chạy ở nhiều ứng dụng hoặc ngôn ngữ, cần bảo đảm cách tạo key và selector thống nhất. Không dùng object Java có hashCode dựa trên identity hoặc giá trị không ổn định giữa tiến trình.

Với khóa dạng String, UUID hoặc số nguyên đã chuẩn hóa, hành vi hash dễ kiểm soát hơn. Nếu cần thuật toán khác, dùng partitionSelectorExpression hoặc PartitionSelectorStrategy và triển khai nhất quán cho tất cả producer.

## 7. Chọn partition count và thay đổi topology

Partition count ảnh hưởng đến throughput, song song, bộ nhớ, file handle, metadata và chi phí vận hành. Số partition lớn hơn không luôn làm hệ thống nhanh hơn.

Khi chọn số partition, cân nhắc:

- Throughput ghi và đọc dự kiến.
- Số consumer instance có thể chạy đồng thời.
- Số lượng key và mức phân bố dữ liệu.
- Yêu cầu thứ tự và kích thước trạng thái của mỗi consumer.
- Khả năng tài nguyên của broker và thời gian rebalance.
- Số partition cần thiết trong tương lai gần.

### 7.1. Tác động khi tăng partition

Với cách chọn partition mặc định theo hashCode(key) % partitionCount, thay đổi partitionCount có thể làm nhiều key được ánh xạ sang partition khác. Điều này có thể phá vỡ giả định rằng mọi sự kiện của một thực thể luôn đi qua cùng một partition trong suốt vòng đời.

Ví dụ một key trước đây được đưa vào partition 1 khi có bốn partition. Sau khi tăng lên sáu partition, cùng key có thể được đưa vào partition khác. Nếu các sự kiện cũ còn nằm trong partition cũ và sự kiện mới đi vào partition mới, hai luồng có thể được xử lý song song và hoàn tất sai thứ tự.

Với Kafka, việc tăng số partition của topic không tự động di chuyển các record cũ. Với Rabbit binder, thay đổi số partition có thể yêu cầu tạo hoặc thay đổi các queue và binding phân vùng. Vì vậy, thay đổi partition count cần kế hoạch migration, kiểm soát producer, consumer và dữ liệu đang tồn tại.

### 7.2. Chiến lược thay đổi an toàn

Một số lựa chọn:

1. Tạo destination phiên bản mới với số partition mới, chuyển producer theo giai đoạn và cho consumer xử lý cả hai luồng trong khoảng chuyển tiếp.
2. Dừng hoặc điều tiết producer, chờ backlog cũ được xử lý, sau đó thay đổi topology và khởi động lại theo cấu hình mới.
3. Dùng một thuật toán phân vùng ổn định có khả năng giảm remapping, nếu hệ thống có yêu cầu và đã kiểm thử.

Không thay partition count trực tiếp trong môi trường production mà không đánh giá key mapping, dữ liệu còn tồn đọng và thứ tự xử lý.

## 8. Consumer concurrency và khả năng mở rộng

### 8.1. Kafka

Trong một Kafka consumer group, mỗi partition được gán cho một consumer tại một thời điểm. Nếu topic có sáu partition:

- Một consumer có thể đọc cả sáu partition.
- Ba consumer có thể chia nhau hai partition mỗi consumer.
- Sáu consumer có thể nhận một partition mỗi consumer.
- Mười consumer sẽ có consumer dư không được gán partition.

Kafka có thể rebalance khi số consumer thay đổi. Điều này hỗ trợ scale động, nhưng rebalance có thể làm gián đoạn tạm thời và cần theo dõi.

Nếu consumer concurrency bên trong một instance lớn hơn số partition được gán, không phải thread nào cũng nhận được partition riêng. Đồng thời, xử lý song song trong một partition có thể làm thay đổi thứ tự hoàn tất. Hãy phân biệt số consumer, số thread xử lý và số partition.

### 8.2. RabbitMQ

Với Rabbit binder partitioned, mỗi partition là một queue. Mỗi consumer instance được gắn với queue theo instance index. Binder không tự phân phối lại queue phân vùng sang instance mới theo cơ chế dynamic rebalance của Kafka.

Nếu có ba partition, nên triển khai ba instance có index 0, 1, 2. Nếu instance 1 dừng, queue P1 có thể tích lũy message cho đến khi consumer phù hợp hoạt động trở lại. Cần giám sát queue depth và có kế hoạch phục hồi instance đúng index.

RabbitMQ cho phép nhiều consumer đọc một queue trong các mô hình thông thường, nhưng với partitioning cần kiểm soát concurrency để bảo toàn thứ tự nghiệp vụ. Nếu nhiều consumer đồng thời xử lý cùng queue, thứ tự nhận và thứ tự hoàn tất có thể khác nhau, đặc biệt khi có prefetch, redelivery hoặc thời gian xử lý không đồng đều.

### 8.3. Chọn broker theo mô hình scale

Kafka thường phù hợp khi cần log sự kiện có retention, replay theo offset và scale consumer group theo partition. RabbitMQ thường phù hợp với định tuyến message qua exchange/queue, acknowledgement và queue work distribution. Rabbit binder vẫn có thể cung cấp partition affinity, nhưng cần quản lý instance index và topology queue chặt chẽ hơn.

Không nên chọn RabbitMQ chỉ vì có thể cấu hình partitioned rồi giả định khả năng scale tương đương Kafka. Hãy chọn theo semantics lưu trữ, giao nhận và cách vận hành mà hệ thống thực sự cần.

## 9. Thứ tự xử lý và bảo đảm giao nhận

Partition key chỉ đưa các message liên quan về cùng partition. Nó không bảo đảm mọi side effect hoàn tất theo thứ tự nếu consumer xử lý bất đồng bộ hoặc có nhiều luồng song song.

Để giữ thứ tự:

- Dùng key ổn định theo thực thể.
- Không thay đổi partition selector giữa các producer.
- Giới hạn xử lý song song trong cùng partition hoặc queue khi cần thứ tự nghiêm ngặt.
- Chỉ xác nhận message sau khi xử lý đạt điều kiện nghiệp vụ.
- Thiết kế consumer idempotent để xử lý redelivery.
- Không dựa vào thứ tự toàn cục giữa các partition.

### 9.1. Kafka offset

Kafka theo dõi tiến độ tiêu thụ bằng offset của từng partition. Consumer group commit offset để ghi nhận vị trí đã xử lý. Nếu commit trước khi tác vụ nghiệp vụ hoàn tất, có nguy cơ mất xử lý sau khi consumer gặp lỗi. Nếu commit sau khi hoàn tất nhưng bị crash trước khi commit, message có thể được đọc lại.

Vì vậy, cần phối hợp commit mode, acknowledgement và transaction theo cấu hình binder. Idempotency vẫn quan trọng khi cùng record có thể được xử lý lại.

### 9.2. RabbitMQ acknowledgement

RabbitMQ consumer xác nhận message sau khi xử lý. Nếu consumer chết trước acknowledgement, message có thể được requeue và giao lại. Nếu xử lý song song hoặc nhiều consumer cùng đọc queue, thứ tự hoàn tất có thể thay đổi.

Không coi queue partition là một log có offset để seek lại tùy ý. Khi message đã được xác nhận và loại khỏi queue, khả năng phát lại phụ thuộc vào dead-letter, publisher hoặc cơ chế lưu trữ riêng của ứng dụng.

### 9.3. Exactly-once và idempotency

Không có partition nào tự tạo ra bảo đảm exactly-once cho toàn bộ nghiệp vụ. Kafka có thể hỗ trợ transaction và cơ chế xử lý chính xác trong phạm vi Kafka được cấu hình phù hợp; RabbitMQ có acknowledgement và publisher confirms nhưng vẫn có tình huống gửi lại. Khi consumer cập nhật database hoặc gọi dịch vụ ngoài broker, cần thiết kế idempotency, inbox/outbox hoặc cơ chế bù trừ.

## 10. Kiểm thử partitioning

Kiểm thử nên chứng minh ba đặc tính:

1. Cùng key được ánh xạ tới cùng partition.
2. Key khác nhau có thể được phân tán qua nhiều partition.
3. Consumer nhận đúng phần dữ liệu được gán và hành vi khi scale hoặc lỗi là dự kiến.

### 10.1. Kiểm thử logic chọn partition

Nếu dùng selector tùy chỉnh, kiểm thử riêng thuật toán:

~~~java
class CustomerPartitionSelector implements PartitionSelectorStrategy {

    @Override
    public int selectPartition(Object key, int partitionCount) {
        String customerId = String.valueOf(key);
        return Math.floorMod(customerId.hashCode(), partitionCount);
    }
}
~~~

Ví dụ dùng floorMod để kết quả luôn nằm trong khoảng hợp lệ kể cả khi hashCode âm. Nếu dùng selector mặc định của framework, hãy kiểm tra kết quả theo phiên bản thư viện và tránh tự giả định rằng selector tùy chỉnh đang được kích hoạt.

Kiểm thử:

~~~java
@Test
void sameCustomerUsesSamePartition() {
    CustomerPartitionSelector selector = new CustomerPartitionSelector();

    int first = selector.selectPartition("customer-10", 6);
    int second = selector.selectPartition("customer-10", 6);

    assertThat(first).isEqualTo(second);
}
~~~

### 10.2. Kiểm thử Kafka

Integration test với Kafka nên xác minh:

- Topic có đúng số partition.
- Record cùng key được ghi vào cùng partition.
- Consumer group chia partition như mong đợi.
- Rebalance khi instance tham gia hoặc rời đi.
- Offset và xử lý lại sau khi consumer dừng đột ngột.
- Thứ tự của record trong cùng partition.

Test binder có thể kiểm tra một phần logic binding và partition header ở tầng Spring, nhưng không thay thế kiểm thử Kafka broker thật cho partition assignment, offset và rebalance.

### 10.3. Kiểm thử RabbitMQ

Integration test với RabbitMQ nên xác minh:

- Exchange destination được tạo đúng loại.
- Có queue riêng cho từng partition và group cần thiết.
- Routing key/partition key đưa message đến queue đúng.
- Instance index nhận đúng queue.
- required-groups tạo trước queue khi consumer chưa triển khai.
- Queue tích lũy message và phục hồi khi instance dừng.
- Acknowledgement, redelivery và thứ tự với concurrency thực tế.

Không chỉ kiểm tra rằng message xuất hiện ở một queue. Hãy gửi nhiều key khác nhau và xác nhận phân phối, đồng thời gửi nhiều message cùng key để kiểm tra affinity.

## 11. Vận hành và quan sát

### 11.1. Chỉ số Kafka

Theo dõi:

- Số partition và trạng thái leader/replica.
- Consumer lag theo group và partition.
- Tốc độ ghi/đọc của từng partition.
- Rebalance count và thời gian rebalance.
- Lỗi producer, retry và lỗi commit offset.
- Chênh lệch tải giữa các partition để phát hiện hot partition.

Nếu một partition có lag tăng liên tục trong khi các partition khác ổn định, kiểm tra phân phối key, dữ liệu bất thường hoặc consumer xử lý chậm.

### 11.2. Chỉ số RabbitMQ

Theo dõi:

- Số queue phân vùng được tạo cho mỗi destination/group.
- Queue depth và tuổi message cũ nhất.
- Consumer count theo queue.
- Unacknowledged message và redelivery.
- Tốc độ publish/consume và publisher confirm.
- Queue không có consumer do instance index bị thiếu.

Nếu queue P2 có backlog lớn nhưng P0 và P1 trống, có thể key phân phối không đều hoặc consumer tương ứng không hoạt động. Kiểm tra instance index và mapping key trước khi tăng số consumer tùy ý.

### 11.3. Triển khai nhiều instance

Với Kafka, triển khai nhiều consumer cùng group và để Kafka rebalance nếu dùng chế độ mặc định. Với Rabbit binder partitioned, cung cấp instance count và index đúng cho từng instance; tránh hai instance dùng cùng index khi chúng được kỳ vọng xử lý partition độc lập.

Khi triển khai rolling update, cần tính đến thời gian consumer rời group, rebalance, queue backlog và khả năng xử lý message đang dở. Có health check, graceful shutdown và cảnh báo cho partition/queue không có consumer.

## 12. Những lỗi thiết kế thường gặp

1. **Chọn key ngẫu nhiên cho từng message**: các sự kiện cùng thực thể bị phân tán và mất affinity. Hãy dùng khóa ổn định như orderId.
2. **Dùng key quá tập trung**: một partition trở thành hot partition. Hãy đo phân phối key và xem lại miền thứ tự cần bảo vệ.
3. **Nghĩ partition tạo thứ tự toàn cục**: thứ tự chỉ được bảo đảm trong phạm vi partition/queue theo điều kiện xử lý. Hãy thiết kế thứ tự theo thực thể.
4. **Scale consumer Kafka vượt số partition mà mong tất cả đều hoạt động**: consumer dư không nhận partition. Hãy xác định số partition và concurrency phù hợp.
5. **Dùng Rabbit binder như Kafka**: RabbitMQ không có log partition native. Hãy hiểu queue-per-partition và quản lý topology tương ứng.
6. **Thiếu instanceIndex hoặc instanceCount trên RabbitMQ**: consumer có thể không nhận đúng queue phân vùng. Hãy cấu hình chỉ số duy nhất cho từng instance.
7. **Không provision required groups**: message có thể bị mất trước khi queue consumer được tạo. Hãy khai báo required-groups khi cần consumer queue tồn tại trước.
8. **Cho rằng Rabbit partitioned consumer tự scale động**: binder yêu cầu quản lý instance index và tối thiểu một consumer cho mỗi partition. Hãy lập kế hoạch triển khai đồng bộ.
9. **Tăng partition count tùy tiện**: key có thể ánh xạ sang partition mới và làm gián đoạn thứ tự theo thực thể. Hãy có kế hoạch migration.
10. **Xử lý song song trong cùng partition mà không kiểm soát**: thứ tự hoàn tất tác vụ có thể khác thứ tự nhận. Hãy giới hạn concurrency khi nghiệp vụ yêu cầu.
11. **Chỉ kiểm thử test binder**: không xác minh được mọi đặc tính của broker. Hãy bổ sung integration test với Kafka hoặc RabbitMQ thật.
12. **Coi partitioning là bảo đảm exactly-once**: redelivery và crash vẫn có thể tạo xử lý trùng. Hãy dùng event ID và idempotency.

## 13. Quy trình lựa chọn và triển khai

Khi thiết kế partitioning cho một luồng sự kiện, thực hiện theo trình tự:

1. Xác định thực thể cần giữ thứ tự: đơn hàng, khách hàng, tài khoản hay thiết bị.
2. Chọn partition key ổn định tương ứng với thực thể.
3. Ước lượng throughput, số consumer và số partition cần thiết.
4. Xác định broker có partition native hay cần binder mô phỏng bằng queue.
5. Cấu hình partitionKeyExpression hoặc extractor và partitionCount.
6. Cấu hình consumer group, partitioned, instanceIndex và instanceCount theo binder.
7. Với RabbitMQ, quyết định required-groups và kiểm tra queue/binding được provision.
8. Với Kafka, kiểm tra topic partition count, auto rebalance và group assignment.
9. Kiểm thử key affinity, phân phối tải, thứ tự, redelivery và tình huống instance dừng.
10. Thiết lập dashboard và cảnh báo cho lag, queue depth, rebalance và hot partition.
11. Lập kế hoạch trước khi thay đổi partition count hoặc selector.

## Kết luận

Kafka có partition native trong topic: mỗi partition là một log có thứ tự riêng, consumer group phân chia partition cho các consumer và Kafka có thể rebalance khi số consumer thay đổi. RabbitMQ không có partition native; Rabbit binder mô phỏng partition bằng queue riêng cho từng partition được bind vào destination exchange. Consumer RabbitMQ cần được ánh xạ tới queue theo instance index và topology này không hỗ trợ dynamic scaling giống Kafka.

Spring Cloud Stream cung cấp cách khai báo partition key và partition count chung, nhưng ứng dụng vẫn phải hiểu semantics của broker. Chọn key ổn định, kiểm soát hot partition, số instance, thứ tự xử lý và kế hoạch thay đổi topology là điều kiện để phân vùng thực sự cải thiện throughput mà không làm sai dữ liệu nghiệp vụ.

## Tài liệu tham khảo

- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — RabbitMQ Binder: Partitioning](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
