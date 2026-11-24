# Giảm khóa lệch tải và xử lý phân vùng nóng

Phân vùng giúp một topic hoặc luồng message được xử lý song song. Tuy nhiên, tăng số partition không tự động làm tải cân bằng. Nếu phần lớn sự kiện mang cùng một key, producer sẽ liên tục gửi chúng tới cùng partition; consumer xử lý partition đó bị quá tải trong khi các partition khác còn rảnh. Hiện tượng này thường được gọi là **key skew**, **partition skew** hoặc **hot partition**.

Trong Spring Cloud Stream, lựa chọn key và cách binder ánh xạ key tới partition quyết định mức phân phối tải. Bài học này trình bày cách nhận diện skew, chọn key phù hợp, cấu hình partitioning với Kafka binder, xử lý hot key bằng sharding có kiểm soát và áp dụng cách phân vùng tương ứng cho RabbitMQ hoặc Pulsar.

## 1. Partition skew và hot partition là gì?

Một topic có nhiều partition nhưng lưu lượng không phân bố đều:

~~~text
Topic: orders

Partition 0  ############################  48% traffic
Partition 1  ########                      14% traffic
Partition 2  ######                         9% traffic
Partition 3  #####                          8% traffic
Partition 4  ####                           7% traffic
Partition 5  ####                           6% traffic
Partition 6  ###                            5% traffic
Partition 7  ##                             3% traffic
~~~

Partition 0 trở thành điểm nóng. Consumer được gán partition này có thể tăng lag liên tục, trong khi các consumer khác không sử dụng hết CPU hoặc I/O. Tổng throughput của hệ thống bị giới hạn bởi partition chậm nhất hoặc key nóng nhất.

Phân biệt ba khái niệm:

- **Key skew:** phân phối key không đồng đều. Một vài key xuất hiện thường xuyên hơn hẳn các key khác.
- **Partition skew:** số record, byte hoặc chi phí xử lý phân bố không đều giữa các partition.
- **Hot partition:** partition có tải hoặc độ trễ cao kéo dài, trở thành nút thắt của pipeline.

Key skew thường gây partition skew khi partition được chọn bằng hash(key). Tuy nhiên, partition skew cũng có thể xuất hiện do record có kích thước khác nhau, một nhóm message cần xử lý đắt hơn, partition assignment không cân bằng hoặc consumer có năng lực khác nhau.

### Ví dụ một tenant quá lớn

Giả sử hệ thống xử lý sự kiện đơn hàng của nhiều khách hàng doanh nghiệp:

| Tenant | Tỷ lệ message | Partition theo key tenant |
|---|---:|---|
| tenant-a | 52% | Partition 3 |
| tenant-b | 12% | Partition 5 |
| tenant-c | 9% | Partition 1 |
| tenant-d | 7% | Partition 6 |
| Các tenant còn lại | 20% | Các partition còn lại |

Nếu key là `tenantId`, mọi sự kiện của `tenant-a` đi cùng một partition để giữ thứ tự theo tenant. Đây là lựa chọn đúng về ngữ nghĩa nếu mọi cập nhật của tenant phải được xử lý tuần tự, nhưng nó tạo một giới hạn throughput cho tenant lớn.

Không nên vội đổi key trước khi xác định yêu cầu thứ tự. Câu hỏi đầu tiên là: hệ thống cần giữ thứ tự cho toàn bộ tenant, cho từng đơn hàng, cho từng tài khoản hay chỉ cho từng aggregate nghiệp vụ?

## 2. Vì sao một partition trở thành điểm nóng?

Các nguyên nhân phổ biến:

1. **Key có độ lệch tự nhiên:** một tenant, khách hàng, tài khoản hoặc thiết bị phát sinh phần lớn traffic.
2. **Chọn key có cardinality thấp:** dùng `eventType`, `country`, `status` hoặc một giá trị boolean làm key khiến nhiều message dồn vào một vài partition.
3. **Key mặc định hoặc key bị thiếu:** producer gửi null/constant key trong khi binder hoặc custom selector ánh xạ các giá trị đó vào cùng một partition. Lưu ý Kafka native producer không có key thường dùng sticky partitioning và chuyển partition theo batch; không nên mặc định mọi message không key đều bị dồn vào một partition cố định.
4. **Một nghiệp vụ phát nhiều event hơn phần còn lại:** ví dụ một cửa hàng lớn, một tài khoản tổng hoặc một chiến dịch tạo tải đột biến.
5. **Chi phí xử lý không đồng đều:** một số key cần gọi API ngoài, join dữ liệu lớn hoặc thực hiện phép tính tốn CPU.
6. **Thay đổi partition count:** số partition thay đổi có thể làm ánh xạ hash thay đổi, khiến phân phối và thứ tự quan sát được khác trước.
7. **Giới hạn phía consumer:** số partition có thể đủ nhưng consumer concurrency, CPU, I/O hoặc downstream connection pool không đủ năng lực.

Thêm partition chỉ tăng khả năng song song giữa các key khác nhau. Nếu tất cả message vẫn dùng một key và yêu cầu cùng key đi cùng partition, thêm partition không chia được key nóng đó.

## 3. Chọn key theo ranh giới thứ tự nghiệp vụ

Partition key nên thể hiện đơn vị mà ứng dụng cần giữ thứ tự hoặc trạng thái. Không chọn key chỉ vì trường đó luôn có sẵn trong payload.

| Key ứng viên | Phân phối dự kiến | Khi phù hợp | Rủi ro |
|---|---|---|---|
| `tenantId` | Một tenant luôn vào cùng partition. | Cần tuần tự hóa mọi thay đổi trong tenant. | Tenant lớn tạo hot partition. |
| `customerId` | Một khách hàng luôn vào cùng partition. | Cần thứ tự theo khách hàng. | Khách hàng có traffic rất cao làm skew. |
| `orderId` | Mỗi đơn hàng là một key riêng. | Cần thứ tự các sự kiện của từng đơn hàng. | Không giữ thứ tự toàn khách hàng nếu nghiệp vụ cần điều đó. |
| `accountId` | Mỗi tài khoản là một key riêng. | Cần tuần tự hóa số dư hoặc trạng thái tài khoản. | Tài khoản tổng hoặc tài khoản hệ thống có thể nóng. |
| `deviceId` | Mỗi thiết bị là một key riêng. | Cần thứ tự telemetry hoặc trạng thái thiết bị. | Gateway dùng chung làm nhiều message có cùng key. |
| `eventType` | Chỉ có ít nhóm key. | Chỉ khi cần gom theo loại event và tải từng loại cân bằng. | Cardinality thấp, dễ dồn tải. |
| Không có key | Phân phối theo chính sách producer/binder. | Khi không cần thứ tự theo key. | Không còn bảo đảm thứ tự theo thực thể nghiệp vụ. |

Quy tắc thực hành:

- Chọn key có cardinality đủ lớn và phân bố gần với khối lượng công việc.
- Chọn đúng aggregate mà nghiệp vụ cần tuần tự hóa.
- Tránh key có một vài giá trị chiếm phần lớn traffic.
- Giữ key ổn định giữa các producer và ngôn ngữ lập trình.
- Ghi rõ hợp đồng key trong schema hoặc tài liệu event.

Một key có cardinality cao vẫn có thể bị skew nếu một key cụ thể chiếm 40% traffic. Vì vậy, hãy đo tần suất key thực tế thay vì chỉ đếm số lượng key khác nhau.

## 4. Đo skew trước khi thay đổi partitioning

Không nên tối ưu chỉ dựa trên cảm giác hoặc tổng throughput. Hãy đo ít nhất các nhóm sau:

| Nhóm số liệu | Chỉ số nên thu thập | Câu hỏi |
|---|---|---|
| Lưu lượng partition | Record/sec và byte/sec theo partition | Partition nào nhận nhiều dữ liệu nhất? |
| Lag | Consumer lag theo topic/partition và thời gian lag tồn tại | Partition nào không theo kịp producer? |
| Độ trễ | Processing latency p50/p95/p99 theo partition hoặc key group | Một số key có xử lý lâu bất thường không? |
| Consumer | CPU, thread utilization, poll rate, commit rate, rebalance | Consumer có bị giới hạn tài nguyên hoặc assignment không? |
| Key distribution | Top key theo số record, byte và chi phí xử lý | Một key hoặc nhóm key nào chiếm tải lớn? |
| Downstream | API latency, database connection pool, rate limit, retry | Partition nóng là nguyên nhân hay chỉ là nơi thể hiện nút thắt downstream? |

### Tỷ lệ mất cân bằng

Có thể dùng một số tỷ lệ đơn giản để theo dõi:

\[
\text{SkewRatio} =
\frac{\text{Tải lớn nhất của một partition}}
{\text{Tải trung bình mỗi partition}}
\]

Ví dụ có 8 partition, tổng 80.000 record/phút:

- Tải trung bình: 10.000 record/phút.
- Partition lớn nhất: 42.000 record/phút.
- SkewRatio: 4,2.

Tỷ lệ 4,2 cho biết partition lớn nhất nhận tải gấp 4,2 lần mức trung bình. Đây là tín hiệu cần điều tra, nhưng chưa đủ để kết luận partition đã quá tải. Hãy đối chiếu lag, processing latency và tài nguyên consumer.

Nên đo cả record rate và byte rate. Một partition có ít record nhưng payload lớn hoặc xử lý nặng vẫn có thể là điểm nóng.

### Đọc lag theo từng partition

Với Kafka, consumer lag tổng có thể che giấu một partition đang tăng nhanh. Hãy quan sát lag của từng partition trong cùng consumer group. Nếu một partition liên tục tăng trong khi các partition khác gần 0, cần kiểm tra key distribution và thời gian xử lý của key được ánh xạ tới partition đó.

Không dùng một snapshot làm kết luận. So sánh theo cửa sổ thời gian, giờ cao điểm, ngày có chiến dịch và thời điểm rebalance. Phân biệt lag tăng do producer burst ngắn với lag tăng liên tục do năng lực consumer thấp hơn tốc độ đến.

## 5. Phân biệt partitioning của Spring Cloud Stream và Kafka native key

Spring Cloud Stream có cơ chế partitioning chung cho các binder. Kafka cũng có partitioning native dựa trên record key. Hai cơ chế liên quan nhưng không đồng nhất:

| Cơ chế | Thuộc tính chính | Mục đích |
|---|---|---|
| Spring Cloud Stream partitioning chung | `partitionKeyExpression`, `partitionKeyExtractorName`, `partitionSelectorExpression`, `partitionCount` | Tính partition theo cơ chế chung của binder, hữu ích với middleware không có partitioning native hoặc khi cần logic selector riêng. |
| Kafka native partitioning | `KafkaHeaders.KEY` hoặc Kafka producer `messageKeyExpression` | Gửi record key cho Kafka producer để broker/client chọn partition theo key. |

Với Kafka binder, tài liệu Spring Cloud Stream khuyến nghị dùng partitioning native của Kafka khi có thể. Chỉ cần binder partitioning chung khi cần custom partition key hoặc biểu thức đặc biệt. Đừng cấu hình cả hai cơ chế mà không hiểu key cuối cùng và partition selector nào đang quyết định partition.

### Cấu hình Kafka native key

Ví dụ producer dùng `customerId` làm Kafka record key:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              message-key-expression: payload.customerId
~~~

Ví dụ giả định payload có kiểu dữ liệu:

~~~java
record OrderEvent(String customerId, String orderId, String tenantId) {
}
~~~

Producer có thể tạo `Message` và đặt `KafkaHeaders.KEY` trực tiếp:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderEvent> toKafkaMessage(OrderEvent event) {
    return MessageBuilder
            .withPayload(event)
            .setHeader(KafkaHeaders.KEY, event.customerId())
            .build();
}
~~~

Khi record key được đặt, Kafka producer mặc định chọn partition dựa trên hash của key và số partition hiện có. Các record cùng key được đưa tới cùng partition, giúp giữ thứ tự theo key trong partition đó.

### Cấu hình partitioning chung của Spring Cloud Stream

Khi cần partition key lấy từ header tùy chỉnh hoặc logic chung của binder:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: headers['partitionKey']
            partition-count: 12
~~~

Spring Cloud Stream tính key từ `partition-key-expression`, sau đó dùng `partitionSelectorExpression` hoặc `PartitionSelectorStrategy` nếu có. Mặc định, partition được chọn bằng hash của key modulo partition count. `partitionCount` phải lớn hơn 1 để cơ chế partitioning chung có hiệu lực.

Đối với Kafka, hãy ưu tiên một cơ chế rõ ràng. Nếu muốn Kafka key được lưu cùng record để consumer khác cũng nhìn thấy và dùng lại, hãy dùng Kafka native key. Nếu dùng binder partitioning chung với custom header, xác minh partition cuối cùng và key được ghi trong record theo phiên bản binder thực tế.

## 6. Vì sao tăng partition count không tự chữa hot key?

Giả sử key `tenant-a` được hash tới partition 3 trong topic có 8 partition. Khi tăng topic lên 16 partition, key vẫn được hash thành một giá trị và ánh xạ tới một partition duy nhất. Partition ID có thể thay đổi, nhưng tải của key đó vẫn tập trung vào một partition.

Tăng partition có thể giúp:

- Phân tán nhiều key độc lập sang nhiều partition hơn.
- Tăng số consumer có thể xử lý song song.
- Tạo khoảng trống cho tăng trưởng trong tương lai.

Tăng partition không thể:

- Chia một key thành nhiều partition mà vẫn giữ thứ tự toàn key.
- Tăng tốc một consumer bị giới hạn CPU hoặc downstream.
- Cân bằng một key chiếm phần lớn traffic nếu key mapping không đổi về mặt ngữ nghĩa.

Ngoài ra, thay đổi số partition có thể thay đổi kết quả hash modulo. Những record cũ và mới của cùng key có thể nằm ở partition khác nhau sau khi mở rộng topic. Nếu nghiệp vụ dựa vào thứ tự theo key, hãy lập kế hoạch chuyển đổi và xử lý dữ liệu tồn đọng trước khi thay đổi partition count.

## 7. Các chiến lược giảm key skew

Không có một chiến lược phù hợp cho mọi workload. Hãy chọn theo yêu cầu thứ tự, tính nhất quán và khả năng tổng hợp trạng thái.

| Chiến lược | Cách làm | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Chọn lại key | Dùng order ID thay vì tenant ID nếu chỉ cần thứ tự theo đơn hàng. | Phân phối tốt hơn, thay đổi đơn giản. | Mất thứ tự toàn tenant. |
| Composite key | Ghép thực thể chính với một chiều độc lập, ví dụ `tenantId:orderId`. | Tạo nhiều key cho tenant lớn. | Cần xác định lại ranh giới state/order. |
| Key salting/sharding | Thêm shard suffix xác định vào key nóng. | Chia một hot key thành nhiều key con. | Mất thứ tự tổng thể; cần merge nếu cần kết quả chung. |
| Tách hot tenant | Đưa tenant lớn sang topic hoặc luồng riêng. | Cô lập ảnh hưởng lên tenant khác. | Tăng cấu hình, vận hành và chi phí. |
| Batching/aggregation phía producer | Gộp nhiều update nhỏ thành một event lớn theo cửa sổ ngắn. | Giảm số record và overhead. | Tăng độ trễ, cần xử lý duplicate và giới hạn batch. |
| Rate limit/backpressure | Điều tiết producer hoặc giới hạn tốc độ theo key. | Bảo vệ consumer và downstream. | Tăng thời gian hoàn tất nghiệp vụ hoặc queueing ở upstream. |
| Tăng năng lực xử lý | Tối ưu consumer, I/O, state store và downstream. | Giữ nguyên semantics key. | Không vượt được giới hạn tuần tự của một partition/key. |

## 8. Chọn lại key khi nghiệp vụ cho phép

Giả sử hệ thống dùng `tenantId` làm key vì muốn giữ thứ tự cho mọi sự kiện của tenant. Sau khi phân tích, nhóm phát triển xác định các sự kiện độc lập theo `orderId`; không có quy tắc nào yêu cầu hai đơn hàng khác nhau phải xử lý tuần tự.

Có thể đổi key thành `orderId`:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              message-key-expression: payload.orderId
~~~

Các sự kiện của cùng đơn hàng vẫn vào cùng partition, còn những đơn hàng khác nhau có thể được phân tán. Đây thường là cách giảm skew ít phức tạp nhất khi ranh giới thứ tự đã được xác định chính xác.

Trước khi đổi key, kiểm tra:

- Có consumer nào đang giả định mọi event của tenant nằm trong cùng partition không?
- Có phép aggregate hoặc join nào dùng tenant ID làm state key không?
- Có cần giữ thứ tự giữa `OrderCreated`, `PaymentAuthorized` và `OrderShipped` của cùng đơn hàng không?
- Các producer cũ và mới có thể cùng chạy trong giai đoạn chuyển đổi không?
- Dữ liệu cũ và mới có thể được đọc/ghép theo cùng hợp đồng không?

## 9. Composite key và phân tách theo thực thể con

Composite key tạo key từ nhiều trường:

~~~text
tenant-a:order-101
tenant-a:order-102
tenant-a:order-103
tenant-b:order-201
~~~

Ví dụ:

~~~java
String partitionKey(OrderEvent event) {
    return event.tenantId() + ":" + event.orderId();
}
~~~

Composite key hữu ích khi trạng thái được quản lý độc lập theo cặp thực thể. Tuy nhiên, nếu mọi phép xử lý cuối cùng vẫn cần cập nhật một aggregate duy nhất theo tenant, điểm nóng có thể xuất hiện trở lại ở bước tổng hợp.

Không ghép ngẫu nhiên một trường chỉ để tạo nhiều key. Trường bổ sung phải có ý nghĩa nghiệp vụ và cho phép consumer xử lý độc lập. Nếu key được ghép từ trường không ổn định, các event của cùng aggregate có thể bị phân tán ngoài ý muốn.

## 10. Key salting: chia một hot key thành nhiều shard

Khi một key bắt buộc phải đại diện cho một tenant hoặc tài khoản lớn, có thể thêm shard suffix để tạo nhiều key con:

~~~text
tenant-a#0
tenant-a#1
tenant-a#2
tenant-a#3
tenant-a#4
tenant-a#5
tenant-a#6
tenant-a#7
~~~

Thay vì mọi event dùng `tenant-a`, producer chọn một shard xác định dựa trên một trường phân tán tốt, ví dụ `orderId`:

~~~java
int shardFor(String orderId, int shardCount) {
    return Math.floorMod(orderId.hashCode(), shardCount);
}

String partitionKey(OrderEvent event) {
    int shard = shardFor(event.orderId(), 8);
    return event.tenantId() + "#" + shard;
}
~~~

Với cùng `orderId`, shard luôn giống nhau nên các event của một đơn hàng vẫn đi cùng key con. Những đơn hàng khác nhau của cùng tenant có thể đi vào các shard khác nhau.

Để các producer viết bằng nhiều ngôn ngữ tính cùng shard, phải định nghĩa thuật toán hash, encoding và cách xử lý giá trị null trong hợp đồng. `String.hashCode()` phù hợp khi mọi producer đều chạy theo cùng quy tắc Java; hệ thống đa ngôn ngữ nên chọn một hash ổn định được đặc tả rõ, ví dụ Murmur3 với encoding UTF-8.

### Giới hạn quan trọng của salting

Salting thay đổi thứ tự:

- Trước salting, tất cả event của `tenant-a` được xử lý theo thứ tự trong một partition.
- Sau salting, các shard xử lý song song; chỉ còn thứ tự trong từng shard/key con.
- Không thể suy ra thứ tự toàn tenant từ thứ tự của nhiều partition độc lập.

Chỉ dùng salting khi nghiệp vụ cho phép xử lý song song giữa các shard. Nếu cần thứ tự toàn tenant hoặc cập nhật một trạng thái không thể chia nhỏ, salting có thể làm sai kết quả nghiệp vụ.

## 11. Hai giai đoạn aggregate khi đã chia shard

Với phép đếm hoặc tổng hợp có thể kết hợp, một mô hình thường dùng là aggregate cục bộ theo shard rồi gộp các kết quả:

~~~mermaid
flowchart TD
    A[Order events for tenant-a] --> B[Partition by tenant-a#shard]
    B --> C1[Shard 0 aggregate]
    B --> C2[Shard 1 aggregate]
    B --> C3[Shard 2 aggregate]
    B --> C4[Shard 3 aggregate]
    C1 --> D[Partial aggregate events]
    C2 --> D
    C3 --> D
    C4 --> D
    D --> E[Merge by original tenant ID]
    E --> F[Tenant summary]
~~~

Ví dụ mỗi shard phát tổng số đơn hàng theo cửa sổ 1 phút:

| Shard | Tenant | Window | Partial count |
|---|---|---|---:|
| 0 | tenant-a | 10:00 | 1.250 |
| 1 | tenant-a | 10:00 | 1.110 |
| 2 | tenant-a | 10:00 | 1.390 |
| 3 | tenant-a | 10:00 | 1.180 |

Giai đoạn merge cộng các partial count để tạo tổng tenant. Mô hình này giảm số lượng update cần xử lý ở giai đoạn tổng hợp nếu shard gộp nhiều event thành một partial result.

Tuy nhiên, nếu giai đoạn merge nhận mọi event nhỏ rồi cập nhật cùng một state key liên tục, hot key chỉ chuyển sang bước cuối. Hãy gộp theo cửa sổ hoặc batch trước khi merge, và đo tải ở cả hai giai đoạn.

Salting không phù hợp với mọi phép toán. Sum và count có thể kết hợp dễ dàng; median, distinct count chính xác, thứ tự sự kiện và một số phép tính phụ thuộc trạng thái cần thuật toán merge riêng hoặc cấu trúc dữ liệu khác.

## 12. Tách hot tenant thành luồng riêng

Nếu một tenant có tải vượt xa các tenant còn lại và cần chính sách vận hành riêng, có thể định tuyến tenant đó tới destination chuyên biệt:

~~~text
orders.standard  <- phần lớn tenant
orders.large     <- tenant tải rất lớn
~~~

Spring Cloud Stream có thể dùng function hoặc `StreamBridge` để định tuyến theo thuộc tính nghiệp vụ:

~~~java
String destinationFor(OrderEvent event) {
    return event.tenantId().equals("tenant-a")
            ? "orders-large"
            : "orders-standard";
}
~~~

Trong hệ thống thực tế, danh sách hot tenant nên nằm trong cấu hình hoặc routing service có kiểm soát, không hard-code ID trong function. Hãy bảo đảm consumer, schema, retry và DLQ được cấu hình cho cả hai destination.

Tách luồng giúp tenant lớn không làm tăng lag của tenant khác. Tuy nhiên, nếu luồng riêng vẫn dùng một key duy nhất và yêu cầu tuần tự, partition đó vẫn có giới hạn throughput. Khi đó có thể tăng năng lực consumer trong phạm vi thứ tự cho phép, batching, hoặc chia shard nếu nghiệp vụ hỗ trợ.

## 13. Custom partition selector trong Spring Cloud Stream

Spring Cloud Stream cho phép thay cách chọn partition chung bằng `PartitionSelectorStrategy` hoặc SpEL `partitionSelectorExpression`. Điều này hữu ích khi hash mặc định không phân phối tốt với tập key cụ thể.

Ví dụ selector nhận key đã được chuẩn hóa:

~~~java
import org.springframework.cloud.stream.binder.PartitionSelectorStrategy;
import org.springframework.stereotype.Component;

@Component("balancedPartitionSelector")
public class BalancedPartitionSelector
        implements PartitionSelectorStrategy {

    @Override
    public int selectPartition(Object key, int partitionCount) {
        String normalized = String.valueOf(key).toLowerCase();
        return Math.floorMod(normalized.hashCode(), partitionCount);
    }
}
~~~

Khai báo binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          producer:
            partition-key-expression: payload.tenantId
            partition-count: 12
            partition-selector-name: balancedPartitionSelector
~~~

Selector phải trả về một partition index hợp lệ từ `0` tới `partitionCount - 1`. Cách chuẩn hóa phải giống nhau giữa các producer; nếu không, cùng một key có thể đi tới partition khác nhau.

Custom selector không thể chia một key thành nhiều partition nếu đầu vào key vẫn giống nhau và selector phải ổn định theo key. Muốn chia hot key, cần thay đổi key contract bằng shard suffix hoặc dùng một chiến lược định tuyến khác có hiểu biết về nghiệp vụ.

Với Kafka binder, hãy nhớ Kafka native partitioning đã có thuật toán riêng. Spring Cloud Stream partition selector chung không tự động thay thế Kafka native partitioner trong mọi cấu hình. Xác minh binder đang dùng cơ chế nào và kiểm tra partition thực tế bằng record metadata.

## 14. Cấu hình consumer và số lượng partition

Số consumer xử lý song song trong một consumer group bị giới hạn bởi số partition được gán. Nếu có 6 partition và chạy 10 consumer instance với concurrency 1, ít nhất 4 consumer không nhận partition nào. Tăng consumer vượt partition count không tăng throughput.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: consumeOrder
    stream:
      bindings:
        consumeOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 2
~~~

Trong ví dụ trên, concurrency tạo nhiều consumer thread trong cùng ứng dụng. Hãy tính tổng năng lực theo số instance nhân concurrency và so với số partition. Tuy nhiên, thêm consumer chỉ hữu ích khi có đủ partition độc lập và downstream đủ năng lực.

Đối với partitioning chung của Spring Cloud Stream, consumer có các thuộc tính `partitioned`, `instanceIndex` và `instanceCount`. Với Kafka binder, Kafka consumer group tự phân phối native partitions giữa các instance; không bật partitioned consumer chung chỉ vì topic Kafka đã có partition.

Khi lập kế hoạch partition count, cân nhắc:

- Mức song song cần có ở thời điểm hiện tại và tương lai.
- Tốc độ tăng trưởng traffic và kích thước message.
- Số lượng key độc lập và phân phối key.
- Số consumer instance/concurrency có thể vận hành.
- Chi phí file, replica, metadata và rebalance khi có nhiều partition.
- Khả năng thay đổi partition count mà không phá vỡ thứ tự hoặc state.

## 15. Theo dõi và xử lý hot partition với Kafka Streams

Kafka Streams tạo task dựa trên input partitions. Một key nóng vẫn đi vào cùng task/partition sau khi group hoặc repartition theo key đó. Tăng `num.stream.threads` không chia một task thành nhiều partition.

Với topology có `groupByKey`, `groupBy`, join hoặc aggregate, hãy kiểm tra key trước bước repartition. Nếu mọi record của một tenant đều group theo tenant ID, state store cho tenant đó vẫn nhận tải tập trung.

Các lựa chọn:

- Chọn lại key theo entity độc lập nếu nghiệp vụ cho phép.
- Salting key trước bước repartition và dùng aggregate hai giai đoạn nếu phép toán có thể kết hợp.
- Tách hot tenant thành topology hoặc application ID riêng để cô lập tài nguyên.
- Tối ưu processor, RocksDB, serialization và downstream để giảm chi phí trên mỗi record.
- Dùng windowed aggregation hoặc batching khi có thể giảm số lần cập nhật state.

Không đổi key giữa một stateful topology đang chạy mà không có kế hoạch state migration. Changelog topic, repartition topic và local state store phản ánh key semantics cũ; thay đổi có thể yêu cầu khởi tạo lại hoặc phục hồi state theo quy trình riêng.

## 16. RabbitMQ: một queue nóng và cách mở rộng

RabbitMQ queue truyền thống không tương đương Kafka partition. Một queue là một luồng FIFO; nhiều consumer có thể cùng nhận message từ queue, nhưng hot queue vẫn có giới hạn xử lý ở queue replica.

RabbitMQ ghi rõ một queue replica bị giới hạn bởi một CPU core trên hot code path. Vì vậy, một queue duy nhất có thể trở thành nút thắt khi throughput rất cao. Các hướng xử lý:

- Chia workload thành nhiều queue theo tenant, nhóm key hoặc loại nghiệp vụ.
- Dùng exchange và routing key để định tuyến tới các queue độc lập.
- Chỉ chia queue khi các message có thể xử lý độc lập; nếu cần thứ tự toàn queue, phải chấp nhận giới hạn đó.
- Với workload dạng log/stream cần scale-out, đánh giá RabbitMQ Streams hoặc Super Streams.

### Chia queue theo shard

Ví dụ:

~~~text
orders.exchange
  routing key orders.shard.0 -> orders.0
  routing key orders.shard.1 -> orders.1
  routing key orders.shard.2 -> orders.2
  routing key orders.shard.3 -> orders.3
~~~

Producer tính shard từ key nghiệp vụ và publish với routing key tương ứng. Mỗi queue có thể có consumer riêng. Giữ mapping ổn định để cùng entity luôn đi vào cùng queue nếu cần thứ tự theo entity.

Nếu dùng Spring Cloud Stream Rabbit binder, có thể cấu hình destination, group, routing key expression và queue binding theo phiên bản binder. Xác minh queue/exchange được provision và routing key thực tế bằng RabbitMQ Management UI hoặc HTTP API; không giả định một queue group tự động tạo nhiều shard.

### RabbitMQ Streams và Super Streams

RabbitMQ Streams là cấu trúc dữ liệu dạng append-only log, có semantics khác queue truyền thống. Super Streams chia một logical stream thành nhiều partition streams, có thể kết hợp single active consumer để giữ thứ tự trong từng partition.

Super Streams phù hợp khi đã xác định workload cần stream semantics và đạt giới hạn của một stream. Chúng tăng độ phức tạp vận hành; không nên chuyển sang Super Streams chỉ để xử lý một queue có cấu hình consumer chưa hợp lý.

## 17. Pulsar: partitioned topic và key routing

Pulsar partitioned topic được triển khai thành nhiều internal topics phân bố qua broker. Producer chọn partition bằng routing mode; subscription type quyết định message được phân phối tới consumer nào.

Các routing mode chính:

| Mode | Khi message có key | Khi không có key |
|---|---|---|
| `RoundRobinPartition` | Hash key tới partition tương ứng. | Phân phối round-robin theo ranh giới batching. |
| `SinglePartition` | Hash key tới partition tương ứng. | Chọn một partition và gửi toàn bộ message tới partition đó. |
| `CustomPartition` | Dùng custom message router. | Router quyết định partition. |

Nếu muốn tăng throughput và vẫn giữ thứ tự theo key, cung cấp key ổn định cho message để cùng key được đưa vào cùng partition. Không dùng `SinglePartition` không key cho workload cần phân tán, vì mọi message của producer có thể dồn vào một partition.

### Subscription Shared và Key_Shared

- `Shared` phân phối message round-robin giữa các consumer nhưng không bảo đảm ordering.
- `Key_Shared` phân phối theo key/ordering key; cùng key được giao tới một consumer, hỗ trợ xử lý song song giữa các key trong khi giữ thứ tự theo key.

Khi dùng Key_Shared, producer cần tắt batching hoặc dùng key-based batching để batch không chứa nhiều key khác nhau. Nếu batch gom nhiều key nhưng broker định tuyến theo key đầu tiên, message có thể được giao sai consumer theo semantics mong đợi.

Partitioning và subscription là hai quyết định khác nhau. Tăng partition count giải quyết phân bố ở phía topic/broker; chọn subscription type giải quyết cách consumer chia message. Cần kiểm tra cả hai để tránh một partition nóng hoặc một consumer nóng.

## 18. Đo lường trước và sau khi thay đổi

Một thay đổi key hoặc shard count cần được đánh giá bằng cùng bộ dữ liệu và cùng cửa sổ thời gian.

| Chỉ số | Trước thay đổi | Sau thay đổi | Điều cần xác nhận |
|---|---|---|---|
| Max/average records per partition | Baseline | Đo lại | Skew ratio giảm. |
| Max/average bytes per partition | Baseline | Đo lại | Byte distribution cân bằng hơn. |
| Max consumer lag | Baseline | Đo lại | Partition chậm nhất giảm lag. |
| p95/p99 processing latency | Baseline | Đo lại | Độ trễ không tăng do merge hoặc routing. |
| Duplicate/retry rate | Baseline | Đo lại | Không phát sinh duplicate bất thường. |
| Out-of-order business events | Baseline | Đo lại | Thứ tự vẫn đáp ứng hợp đồng. |
| Downstream saturation | Baseline | Đo lại | Nút thắt không chỉ chuyển sang database/API. |

Đừng chỉ nhìn trung bình. Một phân phối có trung bình đẹp vẫn có thể chứa một partition nóng nếu top 1 key chiếm tỷ trọng lớn.

## 19. Kế hoạch chuyển đổi key hoặc shard

Thay đổi key có thể ảnh hưởng thứ tự, state và consumer. Một quy trình chuyển đổi có kiểm soát:

1. Xác định entity cần giữ thứ tự và xác nhận với chủ sở hữu nghiệp vụ.
2. Đo top key, traffic theo partition, lag và latency để xác định mức skew.
3. Chọn chiến lược: đổi key, composite key, salting, tách tenant hoặc tăng năng lực consumer.
4. Viết hợp đồng key mới, hash algorithm, shard count và cách xử lý event cũ.
5. Kiểm thử với dữ liệu phân phối thực tế, bao gồm hot key và burst.
6. Nếu cần, phát dữ liệu sang topic/version mới thay vì đổi semantics âm thầm trên topic hiện tại.
7. Chạy song song hoặc shadow consumer để so sánh kết quả, nhưng tránh để hai consumer cùng tạo side effect nghiệp vụ.
8. Chuyển producer/consumer theo kế hoạch, theo dõi lag và thứ tự.
9. Giữ khả năng rollback trong thời gian chuyển tiếp.
10. Chỉ xóa luồng cũ sau khi đã xử lý hết dữ liệu tồn và xác nhận không còn consumer phụ thuộc.

Nếu đổi số partition của Kafka, hãy kiểm tra tác động tới key-to-partition mapping và ordering. Nếu dùng Kafka Streams, cần đánh giá state store/changelog và topology migration riêng.

## 20. Kiểm thử phân phối và tính đúng đắn

Unit test cho hàm tạo partition key:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class OrderPartitionKeyTest {

    @Test
    void sameOrderAlwaysMapsToSameShard() {
        assertThat(shardFor("order-101", 8))
                .isEqualTo(shardFor("order-101", 8));
    }

    @Test
    void shardIsWithinConfiguredRange() {
        int shard = shardFor("order-202", 8);
        assertThat(shard).isBetween(0, 7);
    }

    @Test
    void differentOrdersCanUseDifferentShards() {
        var shards = java.util.stream.IntStream.range(0, 100)
                .mapToObj(i -> shardFor("order-" + i, 8))
                .distinct()
                .count();

        assertThat(shards).isGreaterThan(1);
    }

    private int shardFor(String orderId, int shardCount) {
        return Math.floorMod(orderId.hashCode(), shardCount);
    }
}
~~~

Test trên xác nhận tính xác định và miền giá trị, nhưng không chứng minh phân phối thực tế cân bằng. Cần thêm test với tập dữ liệu đại diện:

- Tạo nhiều key theo phân phối gần production.
- Thêm một hoặc nhiều hot key có tỷ trọng lớn.
- Tính số record và byte giả lập theo từng shard.
- So sánh skew ratio trước và sau chiến lược mới.
- Xác nhận cùng entity không đổi shard giữa các lần chạy.
- Xác nhận các event cần thứ tự vẫn cùng key/partition.
- Xác nhận merge stage cho kết quả đúng với dữ liệu gốc.

### Kiểm thử tích hợp với Kafka

Với Kafka broker thử nghiệm:

1. Tạo topic với partition count dự kiến.
2. Gửi tập record có key thực tế qua Spring Cloud Stream Kafka binder.
3. Đọc `KafkaHeaders.RECEIVED_PARTITION` ở consumer hoặc dùng record metadata của producer.
4. Đếm record và byte theo partition.
5. Xác nhận cùng key được định tuyến ổn định.
6. Tạo hot key và quan sát lag theo partition.
7. Chạy thử chiến lược shard và so sánh phân phối.

Nếu kiểm tra consumer group, chạy nhiều instance hoặc concurrency và xác nhận assignment. Không chỉ kiểm tra producer partition ID; mục tiêu cuối cùng là consumer xử lý được tải với độ trễ và thứ tự đúng.

## 21. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tăng partition nhưng một partition vẫn nóng | Một key chiếm phần lớn traffic. | Chọn lại key hoặc shard hot key nếu thứ tự cho phép. |
| Tăng consumer nhưng lag không giảm | Consumer group có ít partition hơn số consumer hoặc một partition bị nóng. | Kiểm tra assignment và lag từng partition. |
| Cùng customer bị xử lý sai thứ tự sau đổi key | Key mới không còn giữ ranh giới thứ tự cần thiết. | Khôi phục key theo aggregate hoặc thiết kế workflow có sequence/version. |
| Cùng key vào partition khác nhau giữa các producer | Hash/encoding/selector không thống nhất hoặc binder và native Kafka partitioning bị trộn. | Chuẩn hóa key và thuật toán; kiểm tra partition thực tế. |
| Salting làm tổng hợp sai | Giai đoạn merge không kết hợp đúng partial state hoặc mất event. | Thiết kế merge có idempotency, window và semantics rõ ràng. |
| Hot partition chuyển sang merge stage | Merge vẫn cập nhật một key gốc cho từng event. | Gộp partial result theo cửa sổ/batch trước merge. |
| Mở rộng Kafka topic làm thay đổi thứ tự | Hash modulo partition count thay đổi mapping. | Lập kế hoạch migration, drain dữ liệu và kiểm tra ordering. |
| RabbitMQ có nhiều consumer nhưng queue vẫn nóng | Nút thắt nằm ở một queue replica hoặc consumer prefetch/downstream. | Chia queue theo shard hoặc đánh giá RabbitMQ Streams/Super Streams. |
| Pulsar Key_Shared phân phối không như mong đợi | Producer batch chứa nhiều key hoặc key không được đặt. | Tắt batching hoặc dùng key-based batching; kiểm tra key. |
| Một consumer Pulsar nhận phần lớn tải | Key distribution skew hoặc mapping key-to-consumer không đều. | Đo top key, shard key nóng khi semantics cho phép và kiểm tra mapping algorithm. |
| Hash test phân phối đẹp nhưng production vẫn lệch | Phân phối dữ liệu thực khác giả định hoặc một số key có chi phí xử lý lớn. | Đo traffic, byte và processing cost thực tế. |

## 22. Checklist trước khi triển khai

- [ ] Đã xác định chính xác aggregate nghiệp vụ cần giữ thứ tự.
- [ ] Đã đo key distribution và top key theo record, byte và processing cost.
- [ ] Đã đo lag và throughput theo từng partition hoặc queue.
- [ ] Đã phân biệt key skew với consumer/downstream bottleneck.
- [ ] Key có cardinality và phân phối phù hợp với workload.
- [ ] Kafka native key và Spring Cloud Stream partitioning chung không bị cấu hình chồng chéo ngoài ý muốn.
- [ ] Partition count đủ cho consumer concurrency dự kiến.
- [ ] Không kỳ vọng tăng partition sẽ tự chia một hot key.
- [ ] Salting/sharding chỉ được dùng khi có thể nới lỏng thứ tự toàn key.
- [ ] Có merge strategy đúng cho aggregate đã chia shard.
- [ ] Hash algorithm và encoding được chuẩn hóa giữa các producer.
- [ ] Có phương án cô lập hot tenant nếu cần.
- [ ] RabbitMQ queue topology hoặc Pulsar partition/subscription phù hợp với semantics.
- [ ] Đã kiểm thử phân phối bằng dữ liệu đại diện và hot-key scenario.
- [ ] Đã kiểm tra thứ tự, duplicate, retry, state migration và rollback.
- [ ] Có dashboard theo dõi skew ratio, lag, processing latency và downstream saturation.

Giảm khóa lệch tải bắt đầu từ việc hiểu key đại diện cho ranh giới thứ tự nào. Nếu key quá tập trung, partition tương ứng sẽ nóng dù topic có nhiều partition. Spring Cloud Stream cho phép cấu hình key và partition selection; Kafka, RabbitMQ và Pulsar có semantics phân vùng riêng cần được tôn trọng. Chọn lại key khi nghiệp vụ cho phép, dùng composite key hoặc salting khi có thể chia nhỏ aggregate, và tách hot tenant khi cần cô lập. Mọi thay đổi phải được đo bằng dữ liệu thực tế và kiểm thử cả phân phối lẫn tính đúng đắn của thứ tự.

## Tài liệu tham khảo

- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Partitioning with the Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/42/generated/producer_config.html)
- [Apache Kafka — Monitoring](https://kafka.apache.org/42/operations/monitoring/)
- [RabbitMQ — Queues and Parallelism](https://www.rabbitmq.com/docs/queues)
- [RabbitMQ — Streams and Super Streams](https://www.rabbitmq.com/docs/streams)
- [Apache Pulsar — Partitioned Topics and Routing Modes](https://pulsar.apache.org/docs/next/concepts-messaging/)
- [Apache Pulsar — Producer Routing](https://pulsar.apache.org/docs/client-libraries/producers/)
