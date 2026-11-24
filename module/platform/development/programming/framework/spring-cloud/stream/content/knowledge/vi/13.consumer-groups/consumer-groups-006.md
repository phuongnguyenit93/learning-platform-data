# Phân biệt số instance, luồng nhận và số phân vùng

Khi tăng khả năng xử lý của một ứng dụng Spring Cloud Stream, ba con số thường bị nhầm lẫn là số instance ứng dụng, số luồng nhận và số partition của broker. Chúng liên quan đến khả năng chạy song song nhưng đại diện cho ba lớp khác nhau. Tăng số pod không tự tạo thêm partition; tăng concurrency không làm topic có thêm partition; và một consumer group có thể gồm nhiều consumer nhưng vẫn chỉ xử lý song song tối đa theo số partition mà broker có thể phân phối cho group đó.

Muốn thiết kế đúng, trước hết phải xác định ứng dụng đang chạy bao nhiêu bản sao, mỗi bản sao mở bao nhiêu consumer cho một input binding, broker chia dữ liệu thành bao nhiêu partition hoặc queue, và các consumer thuộc cùng group hay những group độc lập. Sau đó mới chọn cách scale và cấu hình phù hợp với Kafka, RabbitMQ hoặc Pulsar.

## 1. Bốn khái niệm cần tách biệt

### 1.1. Instance ứng dụng

Instance là một tiến trình hoặc bản triển khai đang chạy của ứng dụng. Trong Kubernetes, một pod chạy ứng dụng thường được tính là một instance. Trong một nền tảng triển khai khác, instance có thể là một container hoặc một bản sao dịch vụ.

Nếu dịch vụ order-worker chạy ba pod, ứng dụng có ba instance. Mỗi instance có cấu hình, bộ nhớ, thread và kết nối broker riêng. Khi một instance dừng, các instance còn lại tiếp tục hoạt động; cơ chế phân phối lại thông điệp phụ thuộc broker và binder.

Instance không đồng nghĩa với consumer. Một instance có thể mở một hoặc nhiều consumer cho cùng một input binding, tùy cấu hình concurrency và binder.

### 1.2. Input binding và luồng nhận

Input binding là cổng logic mà Spring Cloud Stream dùng để nhận thông điệp cho một Supplier, Function hoặc Consumer. Ví dụ bean processOrder có input binding mặc định processOrder-in-0.

Một input binding có thể tạo nhiều consumer nội bộ. Thuộc tính consumer.concurrency điều khiển mức concurrency của consumer trên mỗi instance theo khả năng binder. Giá trị mặc định của thuộc tính chung là 1.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-workers
          consumer:
            concurrency: 2
~~~

Với cấu hình trên, mỗi instance của ứng dụng có thể tạo hai consumer cho binding processOrder-in-0. Nếu triển khai ba instance, số consumer nội bộ dự kiến là:

\[
3\ \text{instance} \times 2\ \text{consumer/instance} = 6\ \text{consumer}
\]

Trong bài này, “luồng nhận” được dùng để chỉ một consumer slot hoặc consumer worker tham gia đọc dữ liệu cho input binding. Nó không phải một partition của broker và cũng không phải một application instance.

### 1.3. Consumer group hoặc subscription

Consumer group là danh tính logic của một nhóm consumer cùng nhận một destination. Với Kafka, các consumer dùng cùng group chia nhau partition của topic. Hai group khác nhau đọc cùng topic sẽ có vị trí đọc độc lập, vì vậy cả hai group đều có thể nhận toàn bộ sự kiện.

RabbitMQ binder tạo queue cho từng consumer group trên destination exchange. Các consumer instance trong cùng group đọc từ queue chung và cạnh tranh nhận thông điệp. Pulsar dùng subscription có tên để quản lý vị trí tiêu thụ và cách phân phối cho các consumer dùng cùng subscription name; subscription type quyết định cách chia tải hoặc dự phòng.

Group không phải là số luồng nhận. Một group có thể có một hoặc nhiều instance, mỗi instance có thể có nhiều consumer nội bộ. Nhiều group cũng không làm tăng khả năng chia tải của cùng một group; chúng tạo ra các luồng tiêu thụ độc lập.

### 1.4. Partition

Partition là một phần dữ liệu của destination. Với Kafka và Pulsar, một topic có thể gồm nhiều partition để tăng khả năng ghi và đọc song song. Mỗi partition có thứ tự riêng; không có thứ tự toàn cục tự động giữa các partition.

RabbitMQ không có partition native theo mô hình Kafka. Spring Cloud Stream Rabbit binder có thể mô phỏng partitioning bằng cách định tuyến đến queue riêng cho từng partition. Vì vậy, khi dùng RabbitMQ cần phân biệt queue thông thường của consumer group với các queue partition do binder tạo.

## 2. Nhìn tổng thể mối quan hệ

Sơ đồ sau mô tả một topic có sáu partition được một group tiêu thụ bởi ba instance. Mỗi instance chạy hai consumer nội bộ:

~~~mermaid
flowchart TB
    T[("Topic orders.events<br/>6 partitions")]
    subgraph G["Consumer group: order-workers"]
      subgraph I0["Instance 0"]
        C00["Consumer 0"]
        C01["Consumer 1"]
      end
      subgraph I1["Instance 1"]
        C10["Consumer 0"]
        C11["Consumer 1"]
      end
      subgraph I2["Instance 2"]
        C20["Consumer 0"]
        C21["Consumer 1"]
      end
    end
    T --> G
~~~

Trong Kafka, sáu consumer member của cùng group có thể được gán sáu partition, mỗi consumer một partition trong ví dụ này. Nếu topic chỉ có bốn partition, tối đa bốn consumer member có thể nhận partition tại cùng thời điểm; hai consumer còn lại sẽ không có partition được gán. Nếu topic có tám partition, sáu consumer có thể nhận tổng cộng tám partition, một số consumer sẽ sở hữu nhiều hơn một partition.

Số instance, concurrency và partition count cần được chọn cùng nhau. Không có quy tắc bắt buộc ba con số phải bằng nhau.

## 3. Ví dụ tính mức song song với Kafka

Kafka phân phối partition giữa các consumer member thuộc cùng consumer group. Với một group và một topic, một partition tại một thời điểm chỉ được gán cho tối đa một consumer member trong group đó. Một consumer có thể đọc nhiều partition.

Nếu:

- Số instance ứng dụng là R.
- consumer.concurrency trên mỗi instance là C.
- Topic có P partition.

Thì số consumer member dự kiến là:

\[
N = R \times C
\]

Số consumer member có thể thực sự nhận ít nhất một partition bị giới hạn bởi:

\[
N_{\text{active}} \leq \min(N, P)
\]

Đây là cách ước lượng mức song song tối đa theo partition, không phải công thức dự đoán thông lượng. Tốc độ thực tế còn phụ thuộc thời gian xử lý, I/O, rebalance, phân bố key, batch size và năng lực broker.

### 3.1. Bốn tình huống thường gặp

| Instance | Concurrency mỗi instance | Consumer member | Partition | Kết quả có thể xảy ra |
|---:|---:|---:|---:|---|
| 3 | 2 | 6 | 6 | Có thể dùng đủ sáu consumer, mỗi consumer nhận một partition |
| 3 | 2 | 6 | 4 | Tối đa bốn consumer nhận partition; hai consumer còn lại idle |
| 2 | 2 | 4 | 8 | Cả bốn consumer đều hoạt động; mỗi consumer nhận trung bình hai partition |
| 5 | 1 | 5 | 1 | Chỉ một consumer nhận partition; bốn consumer còn lại idle |

Ví dụ topic có bốn partition, group có sáu consumer. Tăng số instance từ ba lên bốn trong khi giữ concurrency bằng hai sẽ tạo tám consumer member. Kafka vẫn chỉ có bốn partition để gán, vì vậy số consumer tăng không làm mức song song của topic tăng lên.

Ngược lại, nếu có tám partition và chỉ hai consumer, mỗi consumer có thể nhận nhiều partition. Điều này không sai; nó chỉ có nghĩa số luồng xử lý đang thấp hơn số phần dữ liệu có thể đọc song song.

### 3.2. Cấu hình concurrency cho Kafka

Với Kafka binder và cơ chế auto rebalance mặc định, Kafka quản lý việc gán partition khi consumer tham gia hoặc rời group. Có thể tăng concurrency trên từng input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-workers
          consumer:
            concurrency: 2
~~~

Khi triển khai ba instance cùng cấu hình, group có khoảng sáu consumer member. Nếu topic có sáu partition, đây là một cấu hình khởi đầu có thể khai thác sáu partition song song.

Với Kafka autoRebalanceEnabled=true (mặc định), không cần tự gán instanceIndex cho từng instance để Kafka phân phối partition. Nếu tắt auto rebalance và để binder gán partition theo instance, phải cấu hình spring.cloud.stream.instanceCount và spring.cloud.stream.instanceIndex nhất quán trên từng instance; số partition cần đủ để đáp ứng cách gán đã chọn.

## 4. InstanceCount và InstanceIndex có mục đích riêng

Spring Cloud Stream có hai thuộc tính cấp ứng dụng:

| Thuộc tính | Ý nghĩa |
|---|---|
| spring.cloud.stream.instanceCount | Tổng số instance tham gia một kịch bản partitioning có chỉ số instance |
| spring.cloud.stream.instanceIndex | Chỉ số duy nhất của instance hiện tại, nằm trong khoảng từ 0 đến instanceCount - 1 |

Ví dụ có ba instance:

| Instance | instanceCount | instanceIndex |
|---|---:|---:|
| Pod A | 3 | 0 |
| Pod B | 3 | 1 |
| Pod C | 3 | 2 |

instanceCount không phải concurrency. Nó mô tả tổng số instance trong một cách phân phối dữ liệu dựa trên chỉ số. instanceIndex cũng không phải số partition; nó giúp một instance xác định phần dữ liệu được giao cho mình.

Trong một số binder, consumer có thể override các giá trị cấp ứng dụng bằng consumer.instanceCount và consumer.instanceIndex của binding. Cần xem tài liệu binder và phiên bản Spring Cloud Stream đang sử dụng trước khi cấu hình.

Không nên gán cùng một instanceIndex cho nhiều instance trong kịch bản partitioning tĩnh. Các instance cần có chỉ số duy nhất và instanceCount phải phản ánh đúng tổng số instance được cấu hình. Nếu hệ thống tự scale mà không cấp chỉ số ổn định, mô hình partitioning tĩnh có thể bỏ sót hoặc phân phối chồng dữ liệu.

## 5. Partitioning ở phía producer và consumer

Để dữ liệu được chia theo khóa, producer và consumer phải được cấu hình tương ứng. Producer xác định khóa của từng thông điệp và partition đích. Consumer nhận dữ liệu từ partition được broker hoặc binder giao cho nó.

Ví dụ producer dùng customerId làm partition key:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.customerId
            partition-count: 6
~~~

Spring Cloud Stream tính partition key từ message theo biểu thức đã khai báo. Mặc định, partition selector thường dùng hash của key để chọn một giá trị từ 0 đến partitionCount - 1. Các thông điệp cùng key sẽ được đưa về cùng partition theo cùng thuật toán và số partition.

Khi chọn customerId, mọi sự kiện liên quan cùng khách hàng có cơ hội đi vào cùng partition, giúp giữ thứ tự tương đối theo khách hàng trong phạm vi partition. Nếu key phân bố lệch, một partition có thể nhận nhiều dữ liệu hơn phần còn lại và trở thành điểm nóng.

Số partition được cấu hình ở producer phải tương thích với topic thật. Với Kafka, binder có thể dùng partitionCount như một gợi ý khi provision topic; topic đã tồn tại vẫn cần có đủ partition. Với RabbitMQ, binder dùng số partition để tạo các queue và routing key tương ứng. Với Pulsar, partition count thuộc cấu hình partitioned topic và cần được tạo/provision theo hỗ trợ của binder.

## 6. Khác biệt giữa Kafka, RabbitMQ và Pulsar

Các binder cùng cung cấp abstraction Spring Cloud Stream nhưng cách broker phân phối dữ liệu khác nhau. Không nên lấy một công thức Kafka rồi áp dụng nguyên trạng cho RabbitMQ hoặc Pulsar.

### 6.1. Kafka: group chia partition

Kafka topic có một số partition xác định. Các consumer trong cùng group chia nhau partition; các group khác nhau có thể đọc cùng topic độc lập. Khi consumer tham gia hoặc rời group, Kafka thực hiện rebalance để gán lại partition.

- Tăng replica hoặc concurrency có thể tăng số consumer member.
- Consumer member vượt quá số partition sẽ có member idle.
- Một consumer member có thể nhận nhiều partition.
- Tăng số partition có thể tăng khả năng đọc song song, nhưng cần cân nhắc key routing, dung lượng metadata và thứ tự theo key.

Trong phần lớn trường hợp, hãy để Kafka auto rebalance xử lý phân phối giữa các consumer member. Chỉ dùng instanceCount/instanceIndex cho Kafka khi cấu hình binder yêu cầu gán partition tĩnh hoặc autoRebalanceEnabled được tắt.

### 6.2. RabbitMQ: queue và consumer cạnh tranh nhận

RabbitMQ binder mặc định ánh xạ destination thành exchange. Với mỗi consumer group, binder tạo một queue gắn với exchange đó. Mỗi consumer instance có consumer riêng đọc từ queue của group. Nhiều consumer trên cùng queue cạnh tranh nhận các message; broker phân phối message cho consumer có khả năng nhận theo trạng thái và cấu hình prefetch.

Trong luồng không partitioned, không có khái niệm “mỗi consumer một partition” như Kafka. Tăng số instance hoặc concurrency có thể tăng số consumer cùng đọc queue, nhưng throughput còn phụ thuộc prefetch, số message chưa acknowledge, thời gian xử lý và năng lực queue.

RabbitMQ không hỗ trợ partition native theo kiểu Kafka. Rabbit binder mô phỏng partitioning bằng cách tạo queue riêng cho từng partition và dùng routing key có chỉ số partition. Trong kịch bản này:

- Producer phải bật partitioning và chọn partition key.
- Consumer cần đánh dấu binding là partitioned.
- Mỗi instance phải có instanceIndex và instanceCount đúng.
- Mô hình partitioned queue của Rabbit binder không hỗ trợ dynamic scaling theo cách Kafka group tự rebalance; cần lập kế hoạch instance và partition trước.

Ví dụ minh họa ba partition cho RabbitMQ:

~~~yaml
spring:
  cloud:
    stream:
      instanceCount: 3
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.customerId
            partition-count: 3
        processOrder-in-0:
          destination: orders.events
          group: order-workers
          consumer:
            partitioned: true
~~~

Mỗi instance consumer dùng cùng instanceCount: 3 nhưng có instanceIndex riêng:

~~~yaml
spring:
  cloud:
    stream:
      instanceIndex: 0
      instanceCount: 3
~~~

Instance thứ hai đặt instanceIndex: 1, instance thứ ba đặt instanceIndex: 2. Không chạy ba bản sao với cùng index. Nếu cần scale động thường xuyên, hãy xem xét mô hình queue cạnh tranh thông thường hoặc một thiết kế phù hợp hơn với khả năng của binder thay vì dùng partition mapping tĩnh.

### 6.3. Pulsar: topic partition và subscription type

Pulsar phân biệt topic với subscription. Một topic có thể được partition thành nhiều phần; subscription lưu vị trí tiêu thụ và quyết định cách phân phối message cho các consumer dùng cùng subscription name.

Các subscription type phổ biến:

| Subscription type | Cách phân phối | Ghi chú về thứ tự |
|---|---|---|
| Exclusive | Chỉ một consumer được kết nối vào subscription | Một consumer nhận toàn bộ subscription |
| Failover | Có nhiều consumer nhưng một consumer active trên mỗi phạm vi phân phối; consumer khác dự phòng | Với topic partitioned, các partition có thể được phân cho consumer active khác nhau; thứ tự theo partition được duy trì theo quy tắc của Pulsar |
| Shared | Nhiều consumer nhận message luân phiên/cân bằng | Không bảo đảm thứ tự toàn luồng |
| Key_Shared | Nhiều consumer; message cùng key được giao cho cùng consumer tại một thời điểm | Hỗ trợ thứ tự theo key khi producer gửi key/ordering key phù hợp |

Subscription name khác nhau tạo các luồng tiêu thụ độc lập, tương tự mục đích fan-out giữa các ứng dụng. Nhiều consumer cùng subscription chia tải hoặc dự phòng tùy subscription type. Do đó, đếm consumer mà không xét subscription type có thể dẫn đến dự đoán sai khả năng song song.

Với Pulsar, partition count và subscription type là hai lựa chọn riêng: partitioning quyết định message được ghi vào phần nào của topic; subscription type quyết định message được giao cho consumer nào. Cần kiểm tra cấu hình của Spring Cloud Stream Pulsar binder và Spring for Apache Pulsar tương ứng với phiên bản đang dùng; không giả định mọi thuộc tính concurrency của binder Kafka có cùng ngữ nghĩa.

## 7. Một binding, nhiều binding và nhiều group

Một ứng dụng có thể có nhiều input binding. Mỗi binding là một luồng nhận logic riêng, có destination, group và concurrency riêng. Ví dụ một Function có thể nhận đơn hàng từ orders.events và một Function khác nhận số liệu từ metrics.events.

| Thành phần | Ý nghĩa |
|---|---|
| Hai input binding | Hai cổng nhận logic; mỗi cổng có thể đọc destination riêng |
| Một input binding, concurrency 4 | Một cổng nhận với bốn consumer nội bộ trên mỗi instance theo binder |
| Một group, ba instance | Ba bản sao cùng tham gia xử lý một luồng group |
| Ba group khác nhau | Ba luồng tiêu thụ độc lập; mỗi group có thể nhận toàn bộ message |

Ví dụ nếu ba dịch vụ inventory, analytics và notification đều cần xử lý mọi sự kiện đơn hàng, mỗi dịch vụ nên có group riêng. Nếu ba instance của cùng dịch vụ inventory chỉ cần chia nhau công việc, chúng dùng cùng group inventory-service.

Đừng tăng số group để tăng tốc một consumer group. Tăng group tạo thêm bản sao công việc cho mỗi group, có thể làm tăng tải đọc và xử lý trên hệ thống.

## 8. Chọn partition count và concurrency như thế nào?

Việc chọn số partition nên dựa trên tải dự kiến và giới hạn xử lý, không chỉ dựa trên số pod hiện tại.

### 8.1. Ước lượng nhu cầu song song

Giả sử hệ thống nhận 1.200 sự kiện mỗi giây. Một consumer worker xử lý ổn định 100 sự kiện mỗi giây trong điều kiện tải mục tiêu. Mức song song sơ bộ cần có là:

\[
\left\lceil \frac{1200}{100} \right\rceil = 12\ \text{worker}
\]

Nếu dùng Kafka và muốn một consumer member xử lý một partition trong cấu hình ban đầu, có thể cân nhắc 12 partition hoặc nhiều hơn để có dư địa tăng trưởng. Tuy nhiên, phép tính này chỉ là ước lượng; cần đo bằng tải thực tế vì xử lý I/O, batch, key skew và thời gian chờ broker có thể thay đổi throughput.

### 8.2. Chọn replica và concurrency

Giả sử mục tiêu có 12 consumer member:

| Phương án | Instance | Concurrency/instance | Tổng consumer |
|---|---:|---:|---:|
| A | 3 | 4 | 12 |
| B | 4 | 3 | 12 |
| C | 6 | 2 | 12 |
| D | 12 | 1 | 12 |

Các phương án có tổng số consumer giống nhau nhưng đặc tính vận hành khác nhau:

- Nhiều instance hơn giúp phân tán CPU, bộ nhớ và lỗi tiến trình; đổi lại tăng số kết nối và chi phí triển khai.
- Concurrency cao hơn trên một instance tận dụng nhiều thread trong cùng process; cần kiểm tra thread safety, connection pool và tài nguyên CPU.
- Nhiều consumer hơn partition sẽ tạo consumer idle với Kafka hoặc không tăng mức song song hữu ích.
- Một partition nóng có thể làm một consumer chậm dù các consumer khác còn rảnh.

### 8.3. Chừa dư địa mở rộng

Trong Kafka, số partition thường khó giảm sau khi tạo. Có thể tăng partition, nhưng thay đổi này có thể ảnh hưởng cách key được ánh xạ sang partition và thứ tự tương đối của một key khi partition count thay đổi. Hãy dự trù tăng trưởng, nhưng không tạo số partition quá lớn nếu không cần vì mỗi partition cũng tiêu tốn tài nguyên broker và metadata.

Trong RabbitMQ partitioned mode, thay đổi số partition và số instance cần được phối hợp với queue topology và instance index. Trong Pulsar, việc tạo partitioned topic và thay đổi partition count cần theo quy trình quản trị topic của Pulsar và binder.

## 9. Ảnh hưởng đến thứ tự và tính nhất quán

Partitioning thường được dùng để xử lý song song mà vẫn giữ thứ tự cho các bản ghi liên quan. Điều đó chỉ đúng trong phạm vi mà broker bảo đảm:

- Kafka giữ thứ tự trong từng partition, không bảo đảm thứ tự toàn topic giữa nhiều partition.
- RabbitMQ giữ thứ tự enqueue/delivery trong các điều kiện queue và consumer nhất định, nhưng nhiều consumer xử lý song song có thể hoàn tất theo thứ tự khác nhau. Partitioned queues có thể dùng routing key để gom dữ liệu theo khóa.
- Pulsar có các subscription type với bảo đảm thứ tự khác nhau; Shared ưu tiên chia tải và không bảo đảm thứ tự, trong khi Key_Shared gom message cùng key vào một consumer theo quy tắc của nó.

Nếu mọi cập nhật của cùng một tài khoản phải được xử lý tuần tự, hãy chọn accountId làm key và đảm bảo producer, broker và consumer cùng sử dụng cách định tuyến nhất quán. Nếu chỉ cần xử lý song song và không có yêu cầu thứ tự theo key, có thể chọn cơ chế chia tải đơn giản hơn.

Không nên giả định rằng một partition tương đương một thread hoặc một instance. Một partition có thể được xử lý bởi consumer khác sau rebalance; một consumer có thể sở hữu nhiều partition; và một instance có thể chứa nhiều consumer thread.

## 10. Theo dõi để biết đang thiếu partition hay thiếu consumer

Chỉ nhìn số pod không đủ để đánh giá khả năng xử lý. Cần theo dõi chỉ số của ứng dụng và broker:

| Chỉ số | Ý nghĩa khi chẩn đoán |
|---|---|
| Số application instance | Xác nhận số replica đang chạy |
| Consumer concurrency | Xác nhận số consumer nội bộ được cấu hình trên mỗi binding |
| Consumer group members | Số consumer thực tế đang tham gia group |
| Partition assignment | Partition nào được giao cho consumer nào; có consumer idle không |
| Consumer lag theo partition | Partition nào bị đọc chậm hoặc tồn đọng |
| Processing latency và throughput | Consumer xử lý nhanh hay chậm so với tốc độ đến |
| Rebalance count/time | Tần suất group phải phân phối lại partition |
| Rabbit queue depth và unacked messages | Queue có backlog hay consumer nhận nhưng xử lý chưa xong |
| Pulsar subscription backlog và consumer count | Subscription có tồn đọng và có bao nhiêu consumer tham gia |

Một số cách nhận biết:

- Lag tăng trên tất cả partition: tổng năng lực consumer có thể thấp hơn tốc độ phát.
- Lag chỉ tăng ở một partition: có thể do key skew, một consumer chậm hoặc dữ liệu của partition đó nặng hơn.
- Có consumer member nhưng không được gán partition: số consumer đang vượt số partition hoặc group assignment chưa ổn định.
- Queue RabbitMQ dài nhưng consumer ít: kiểm tra concurrency, prefetch, lỗi kết nối và tốc độ xử lý.
- Pulsar backlog tăng dù có nhiều consumer: kiểm tra subscription type, partition count, key distribution và acknowledgement.

## 11. Các hiểu lầm thường gặp

**Tăng instance sẽ luôn tăng throughput.** Với Kafka, nếu số partition ít hơn số consumer member, các consumer dư không nhận được partition. Cần xem partition assignment trước khi tăng replica.

**Concurrency chính là partition count.** Concurrency tạo thêm consumer nội bộ trên mỗi instance. Partition count là cấu trúc dữ liệu của broker. Hai giá trị có thể khác nhau.

**Một instance chỉ có một consumer.** Một instance có thể mở nhiều consumer nhờ consumer.concurrency, nếu binder hỗ trợ.

**Mỗi consumer chỉ đọc một partition.** Trong Kafka, một consumer có thể được gán nhiều partition. Quy tắc quan trọng là một partition không được gán cho hai consumer member cùng group tại cùng thời điểm.

**Mỗi consumer group là một partition.** Group là danh tính tiêu thụ; partition là phần dữ liệu. Một group có thể đọc nhiều partition.

**Nhiều group làm chia tải cho cùng một công việc.** Các group độc lập thường nhận bản sao luồng dữ liệu. Muốn chia tải giữa các instance của một dịch vụ, hãy cho chúng dùng cùng group.

**RabbitMQ có partition native như Kafka.** Rabbit binder mô phỏng partition bằng queue và routing key riêng; cách scale và gán instance khác Kafka.

**Pulsar Shared luôn giữ thứ tự theo key.** Shared không bảo đảm thứ tự. Nếu cần phân phối song song đồng thời giữ thứ tự theo key, xem xét Key_Shared và cấu hình key phù hợp.

## 12. Quy trình thiết kế số instance, consumer và partition

Khi triển khai một input binding mới hoặc cần tăng năng lực xử lý, có thể đi theo quy trình:

1. Xác định destination và consumer group. Làm rõ có bao nhiêu dịch vụ độc lập cần nhận cùng sự kiện.
2. Đo tốc độ message đến, thời gian xử lý trung bình và mức tải mục tiêu của một consumer.
3. Ước lượng số consumer worker cần thiết cho throughput mục tiêu.
4. Chọn số instance và consumer.concurrency để đạt số consumer mong muốn.
5. Kiểm tra số partition thực tế và khả năng phân phối của binder.
6. Với Kafka, xem partition assignment và auto rebalance; với RabbitMQ, phân biệt queue thường với partitioned queue; với Pulsar, chọn subscription type phù hợp.
7. Chọn partition key nếu cần giữ thứ tự theo thực thể hoặc gom dữ liệu có liên quan.
8. Chạy tải thử và quan sát lag, queue depth, processing latency, rebalance và mức sử dụng tài nguyên.
9. Điều chỉnh replica, concurrency hoặc partition count dựa trên số đo thực tế.
10. Ghi lại quy tắc scale và các giới hạn của binder để tránh tăng instance vượt quá mức song song hữu ích.

Ví dụ, một dịch vụ Kafka có sáu partition và đang chạy ba instance với concurrency bằng hai đã có sáu consumer member trong một group. Nếu lag tăng đều, có thể cần tăng năng lực xử lý từng consumer, tối ưu logic hoặc tăng partition trước khi thêm replica. Nếu lag chỉ tập trung ở một partition, hãy kiểm tra key distribution và thời gian xử lý của dữ liệu thuộc partition đó.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream - Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html): cấu hình partition key, partition count, instance index và instance count.
- [Spring Cloud Stream - Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): thuộc tính consumer.concurrency, partitioned, instanceCount và instanceIndex.
- [Spring Cloud Stream - Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder.html): cấu hình consumer và cơ chế phân phối partition của Kafka binder.
- [Spring Cloud Stream - RabbitMQ Binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html): ánh xạ destination/group thành exchange/queue và partitioning qua queue riêng.
- [Spring Cloud Stream - Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html): kết nối topic, binder và cấu hình Pulsar.
- [Apache Pulsar - Messaging Concepts](https://pulsar.apache.org/docs/4.0.x/concepts-messaging/): subscription type, partitioned topic và phân phối message cho consumer.
