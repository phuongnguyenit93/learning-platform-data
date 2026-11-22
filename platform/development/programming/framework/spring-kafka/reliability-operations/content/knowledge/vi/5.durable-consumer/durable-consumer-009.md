# fetch.min.bytes và fetch.max.wait.ms

## 1. Vai trò trong quá trình consumer lấy dữ liệu

Kafka consumer không nhận từng record bằng một request riêng. Consumer gửi Fetch request tới broker đang giữ leader của các partition được gán, sau đó broker trả về các record có sẵn trong log. Consumer có thể lấy dữ liệu theo batch, giữ dữ liệu trong bộ đệm cục bộ và cung cấp cho ứng dụng qua lời gọi poll.

Hai cấu hình **fetch.min.bytes** và **fetch.max.wait.ms** quyết định broker nên chờ bao lâu để gom đủ dữ liệu trước khi trả lời một Fetch request:

- **fetch.min.bytes** là lượng dữ liệu tối thiểu mà consumer mong broker trả về trong một Fetch response.
- **fetch.max.wait.ms** là thời gian tối đa broker được phép chờ khi lượng dữ liệu hiện có chưa đạt mức tối thiểu đó.

Mục tiêu của hai cấu hình là cân bằng giữa độ trễ và hiệu quả batch. Nếu consumer nhận response ngay khi có ít dữ liệu, ứng dụng có thể xử lý event mới nhanh hơn nhưng phải gửi nhiều Fetch request nhỏ. Nếu consumer yêu cầu broker gom nhiều dữ liệu hơn, số request có thể giảm và batch lớn hơn, nhưng một số record phải chờ lâu hơn trước khi được trả về.

Trong Spring Kafka, đây là cấu hình của Kafka consumer. Chúng được áp dụng cho các consumer do ConsumerFactory tạo ra và được listener container sử dụng.

## 2. fetch.min.bytes hoạt động như thế nào?

**fetch.min.bytes** đặt ngưỡng byte tối thiểu mà broker cố gắng gom trước khi trả lời một Fetch request. Giá trị mặc định của Kafka consumer là 1 byte.

Ví dụ, consumer đặt fetch.min.bytes bằng 65.536 byte (64 KiB). Khi broker nhận Fetch request:

1. Broker kiểm tra lượng dữ liệu sẵn có cho các partition trong request.
2. Nếu lượng dữ liệu đủ đáp ứng ngưỡng, broker có thể trả response ngay.
3. Nếu chưa đủ, broker giữ request trong thời gian chờ dữ liệu mới.
4. Khi lượng dữ liệu đạt ngưỡng, broker trả response.
5. Nếu ngưỡng vẫn chưa đạt khi hết thời gian fetch.max.wait.ms, broker trả phần dữ liệu hiện có, kể cả khi tổng byte thấp hơn fetch.min.bytes.

Ngưỡng này được tính theo byte của dữ liệu fetch response cho request tại broker, không phải số record và cũng không phải ngưỡng riêng cho từng message. Một record lớn có thể chiếm phần lớn response; nhiều record nhỏ có thể cộng lại để đạt ngưỡng.

### 2.1. Tác động của giá trị thấp và cao

| Cấu hình | Hành vi thường thấy | Đánh đổi |
|---|---|---|
| fetch.min.bytes = 1 | Broker có thể trả dữ liệu ngay khi có dữ liệu sẵn sàng | Độ trễ thấp, nhưng có thể tạo nhiều response nhỏ |
| fetch.min.bytes = 16 KiB | Broker có cơ hội gom một batch vừa phải | Cân bằng cho workload có lưu lượng vừa |
| fetch.min.bytes = 64 KiB hoặc cao hơn | Broker chờ gom nhiều byte hơn trước khi trả | Batch lớn hơn, ít request hơn trong tải đủ cao; event có thể chờ lâu hơn |
| fetch.min.bytes quá lớn so với lưu lượng | Ngưỡng thường không đạt trước thời hạn chờ | Fetch request thường xuyên chờ đến giới hạn max wait, tăng độ trễ mà không cải thiện batch đáng kể |

Các giá trị trong bảng chỉ minh họa. Một consumer đọc topic có lưu lượng thấp có thể không bao giờ gom đủ 64 KiB trong thời gian ngắn. Ngược lại, consumer đọc nhiều partition có throughput cao có thể đạt ngưỡng này rất nhanh.

### 2.2. Đơn vị và phạm vi

Kafka nhận giá trị fetch.min.bytes dưới dạng số byte. Khi cấu hình trực tiếp bằng Kafka client, giá trị là integer:

~~~java
props.put(ConsumerConfig.FETCH_MIN_BYTES_CONFIG, 65_536);
~~~

Nếu cấu hình qua Spring Boot, có thể dùng DataSize như 64KB. Hãy kiểm tra cách bind property của phiên bản Spring Boot đang chạy nếu ứng dụng dùng cấu hình tùy biến.

Giá trị được áp dụng cho từng Kafka consumer. Khi Spring Kafka tạo nhiều consumer do concurrency hoặc nhiều listener container, mỗi consumer có Fetch request và bộ đệm riêng. Tổng lưu lượng fetch tới broker vì thế còn phụ thuộc số consumer, số partition được gán và cách partition phân bố giữa broker.

## 3. fetch.max.wait.ms hoạt động như thế nào?

**fetch.max.wait.ms** đặt thời gian tối đa broker chờ để đáp ứng fetch.min.bytes khi chưa có đủ dữ liệu. Giá trị mặc định của Kafka consumer là 500 milliseconds.

Giả sử consumer cấu hình:

- fetch.min.bytes = 65.536
- fetch.max.wait.ms = 200

Nếu broker có đủ 64 KiB dữ liệu cho request, nó có thể trả ngay. Nếu mới có 8 KiB, broker có thể chờ thêm record. Nếu sau 70 ms dữ liệu đạt 64 KiB, response được trả tại thời điểm đó. Nếu sau 200 ms vẫn chỉ có 20 KiB, broker trả phần dữ liệu hiện có khi thời hạn chờ kết thúc.

Điều này có nghĩa fetch.max.wait.ms là giới hạn chờ ở phía broker, không phải thời gian cố định mà mỗi request luôn phải chờ. Khi đủ dữ liệu sớm, response có thể về sớm.

### 3.1. Giá trị thấp và cao

| Giá trị | Hành vi | Khi nào cân nhắc |
|---|---|---|
| 10–50 ms | Broker chỉ chờ ngắn khi chưa đủ dữ liệu | Luồng cần phản hồi nhanh, chấp nhận batch nhỏ |
| 100–200 ms | Cho thêm thời gian gom dữ liệu | Workload vừa, cần cân bằng latency và batch |
| 500 ms | Giá trị mặc định của Kafka consumer | Điểm xuất phát để đo baseline |
| 1.000 ms trở lên | Có thể gom batch lớn hơn trong luồng thưa | Chỉ cân nhắc khi độ trễ cho phép và có bằng chứng giảm request đáng kể |

Giá trị cao có thể tăng thời gian event chờ ở broker trong các giai đoạn lưu lượng thấp. Nó không làm tăng throughput một cách tự động; broker chỉ gom được nhiều dữ liệu nếu có record mới đến trong khoảng thời gian đó.

### 3.2. fetch.max.wait.ms không phải poll timeout

Hai cấu hình này thường bị nhầm lẫn:

- fetch.max.wait.ms được gửi trong Fetch request và quy định thời gian broker có thể chờ để gom đủ byte.
- poll(Duration) là thời gian ứng dụng KafkaConsumer chờ để trả dữ liệu hoặc kết quả poll.
- max.poll.interval.ms giới hạn thời gian tối đa giữa các lần gọi poll trước khi consumer có thể bị xem là không còn hoạt động trong group.

Một lời gọi poll có thể lấy record đã nằm trong bộ đệm cục bộ mà không cần đợi broker fetch mới. Ngược lại, fetch request có thể đang chờ ở broker trong khi ứng dụng tiếp tục làm việc theo cơ chế poll của Kafka client. Không nên tăng max.poll.interval.ms chỉ để bù cho fetch.max.wait.ms mà chưa xác định đúng nguyên nhân.

## 4. Hai cấu hình phối hợp với nhau

Hai property tạo thành một chính sách gom dữ liệu:

- fetch.min.bytes xác định lượng dữ liệu mong muốn cho một response.
- fetch.max.wait.ms giới hạn thời gian chờ để đạt lượng dữ liệu đó.

Có thể hình dung broker quyết định trả Fetch response khi một trong hai điều kiện xảy ra:

~~~text
                    Fetch request
                          |
                          v
             Đã có đủ fetch.min.bytes?
                    /           \
                  Có             Chưa
                  |                |
                  v                v
             Trả response     Tiếp tục chờ record
                                  |
                                  v
                       Đã hết fetch.max.wait.ms?
                              /          \
                            Chưa          Có
                             |             |
                             v             v
                         Tiếp tục       Trả phần dữ liệu
                           chờ           hiện có
~~~

Thời gian chờ thực tế phụ thuộc vào tốc độ record đến broker và cách các partition được phân bố. Nếu lưu lượng đủ cao, ngưỡng byte đạt nhanh. Nếu lưu lượng thấp hoặc không đều, broker có thể thường xuyên phải đợi tới max wait.

### 4.1. Ví dụ ước lượng lượng dữ liệu có thể gom

Giả sử một broker nhận dữ liệu cho các partition mà consumer đang fetch với tốc độ trung bình khoảng 1 MiB/giây. Trong 100 ms, lượng dữ liệu kỳ vọng xấp xỉ:

\[
1\ \text{MiB/s} \times 0,1\ \text{s} \approx 0,1\ \text{MiB} \approx 102\ \text{KiB}
\]

Trong điều kiện tải tương đối đều, ngưỡng 64 KiB có thể đạt trước khi hết 100 ms. Nếu tốc độ chỉ khoảng 100 KiB/giây, trong cùng 100 ms chỉ có khoảng 10 KiB dữ liệu; broker có thể phải chờ gần hết thời hạn hoặc trả response nhỏ hơn ngưỡng.

Đây chỉ là phép ước lượng. Lưu lượng thực tế có thể đến theo burst, partition có thể nằm trên broker khác nhau, record có kích thước khác nhau và response còn chịu các giới hạn fetch khác.

### 4.2. Chọn một cặp giá trị

Không nên chọn hai giá trị độc lập. Ví dụ:

- fetch.min.bytes cao cùng fetch.max.wait.ms rất thấp: broker có ít thời gian để đạt ngưỡng, nên thường trả response dưới ngưỡng.
- fetch.min.bytes thấp cùng fetch.max.wait.ms cao: ngưỡng dễ đạt, nên max wait có thể ít ảnh hưởng khi có dữ liệu; khi không có dữ liệu, hành vi còn phụ thuộc cách broker xử lý request.
- fetch.min.bytes vừa phải cùng fetch.max.wait.ms vừa phải: cho broker thời gian gom batch nhưng vẫn giới hạn độ trễ thêm vào.

Khi bắt đầu điều chỉnh, thay đổi một cặp giá trị có chủ đích, đo kết quả và so sánh với baseline. Không nên tăng đồng thời nhiều giới hạn consumer nếu chưa biết thay đổi nào tạo ra tác động.

## 5. Cấu hình trong Spring Boot và Spring Kafka

Spring Boot cung cấp property cho hai thiết lập này trong nhóm consumer. Ví dụ sau đặt ngưỡng 64 KiB và thời gian chờ tối đa 200 ms:

~~~yaml
spring:
  kafka:
    consumer:
      fetch-min-size: 64KB
      fetch-max-wait: 200ms
      max-poll-records: 500
~~~

Trong Spring Boot, fetch-min-size được bind thành kích thước dữ liệu và fetch-max-wait thành thời lượng. Các property này được chuyển tới Kafka consumer do consumer factory tạo ra.

Nếu cần đặt các Kafka property trực tiếp trong map properties, có thể khai báo:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[fetch.min.bytes]": 65536
        "[fetch.max.wait.ms]": 200
~~~

Chỉ dùng một cách cấu hình cho mỗi property để tránh giá trị trùng lặp hoặc khó xác định nguồn cấu hình cuối cùng. Nếu ứng dụng có custom ConsumerFactory, hãy xác nhận factory đó thực sự nhận property từ Spring Boot hoặc tự đặt giá trị tương ứng.

### 5.1. Cấu hình bằng Java

Với ứng dụng tự tạo ConsumerFactory, có thể dùng ConsumerConfig:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Bean
public ConsumerFactory<String, OrderCreated> consumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-fulfillment");
    props.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class
    );

    props.put(ConsumerConfig.FETCH_MIN_BYTES_CONFIG, 65_536);
    props.put(ConsumerConfig.FETCH_MAX_WAIT_MS_CONFIG, 200);
    props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 500);

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

Đây là ví dụ minh họa phần cấu hình fetch. Ứng dụng thực tế cần bổ sung value deserializer phù hợp, trusted packages hoặc type mapping, security, group và các thiết lập offset theo môi trường. Nếu Spring Boot đã tự cấu hình consumer factory, không cần tạo factory riêng chỉ để thay hai property này.

### 5.2. Áp dụng cho @KafkaListener

Listener container lấy consumer từ ConsumerFactory. Do đó, cấu hình ở consumer factory sẽ được áp dụng cho listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment"
)
public void handle(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Nếu listener container có concurrency lớn hơn 1, mỗi consumer chạy trong container sẽ sử dụng cấu hình fetch tương ứng. Tăng concurrency có thể tăng khả năng đọc song song, nhưng cũng làm tăng số consumer và mức tải fetch lên broker. fetch.min.bytes và fetch.max.wait.ms vẫn cần được đánh giá trong bối cảnh tổng số consumer đang hoạt động.

## 6. Các giới hạn fetch liên quan

fetch.min.bytes và fetch.max.wait.ms không phải hai giới hạn duy nhất quyết định kích thước dữ liệu trả về. Khi tuning, cần hiểu các cấu hình liên quan:

| Property | Phạm vi | Tác dụng |
|---|---|---|
| fetch.min.bytes | Consumer request | Lượng byte tối thiểu broker cố gắng gom trước khi trả response |
| fetch.max.wait.ms | Consumer request | Thời gian tối đa broker chờ để đạt ngưỡng tối thiểu |
| fetch.max.bytes | Consumer | Giới hạn tổng dữ liệu broker trả về cho một Fetch response |
| max.partition.fetch.bytes | Consumer | Giới hạn dữ liệu trả về cho mỗi partition trong một Fetch response |
| max.poll.records | Consumer | Số record tối đa ứng dụng nhận từ một lần poll |
| max.poll.interval.ms | Consumer group | Thời gian tối đa giữa các lần poll |

Hai giới hạn fetch.max.bytes và max.partition.fetch.bytes có thể khiến response nhỏ hơn fetch.min.bytes. Nếu broker không thể gom đủ ngưỡng trước max wait, nó vẫn trả phần dữ liệu sẵn có. Kafka cũng có ngoại lệ cho batch đầu tiên của partition để bảo đảm consumer có thể tiến lên khi một record batch lớn hơn giới hạn cấu hình; do đó các giới hạn kích thước không phải lúc nào cũng là giới hạn cứng tuyệt đối.

### 6.1. fetch.max.bytes

fetch.max.bytes giới hạn tổng dữ liệu mà broker trả về trong một Fetch response. Nếu đặt giới hạn tổng quá thấp trong khi consumer đọc nhiều partition hoặc record batch lớn, consumer có thể cần nhiều request hơn để lấy hết dữ liệu.

Không nên tăng fetch.max.bytes chỉ vì fetch.min.bytes được tăng. Hãy xem kích thước batch thực tế, số partition trên mỗi broker và bộ nhớ consumer trước khi điều chỉnh.

### 6.2. max.partition.fetch.bytes

max.partition.fetch.bytes giới hạn dữ liệu trả về cho mỗi partition trong một fetch. Nếu consumer có nhiều partition được gán, tổng response có thể lớn hơn giá trị của một partition vì response chứa dữ liệu từ nhiều partition.

Giá trị này cần đủ lớn để consumer đọc được record batch lớn nhất mà producer có thể tạo ra. Kafka có cơ chế cho phép trả batch đầu tiên vượt giới hạn để tránh consumer bị kẹt ở một batch không thể đọc.

### 6.3. max.poll.records

max.poll.records giới hạn số record mà một lần poll trả về cho ứng dụng. Nó không giới hạn trực tiếp số byte broker fetch được và không thay thế fetch.min.bytes.

Ví dụ consumer có thể fetch nhiều dữ liệu vào bộ đệm, nhưng mỗi lần poll chỉ trả tối đa 500 record cho listener. Điều này ảnh hưởng cách ứng dụng tiêu thụ và xử lý batch, còn fetch.min.bytes điều khiển việc broker gom byte cho response.

### 6.4. Phân biệt fetch của consumer với replication fetch

Kafka broker cũng có cơ chế follower replica fetch dữ liệu từ leader. Các cấu hình broker như replica.fetch.min.bytes và replica.fetch.wait.max.ms điều khiển hoạt động replication giữa broker.

Chúng có mục tiêu khác với fetch.min.bytes và fetch.max.wait.ms của consumer. Khi thay đổi hai consumer property, không cần sửa broker replication property. Khi điều tra ISR hoặc under-replicated partitions, cần xem nhóm cấu hình replication riêng.

## 7. Tác động đến latency, throughput và tài nguyên

### 7.1. Độ trễ event

Khi fetch.min.bytes cao, consumer có thể phải đợi broker gom thêm record. fetch.max.wait.ms giới hạn thời gian chờ thêm này. Vì vậy, hai property có thể làm tăng thời gian từ lúc record được ghi vào Kafka đến lúc consumer nhận được record.

Tác động dễ thấy nhất ở topic lưu lượng thấp hoặc partition ít hoạt động. Với topic lưu lượng cao, ngưỡng có thể đạt nhanh nên thời gian chờ thường ngắn hơn.

Nếu SLO yêu cầu event được xử lý trong vài trăm milliseconds, không nên đặt max wait gần bằng toàn bộ latency budget. Cần dành ngân sách cho network, consumer scheduling, xử lý listener và downstream call.

### 7.2. Throughput và hiệu quả batch

Ngưỡng fetch lớn hơn có thể giúp consumer nhận nhiều byte trong một response. Điều này có thể giảm số request, giảm overhead network và tăng hiệu quả xử lý batch.

Tuy nhiên, batch lớn hơn chỉ có ích nếu ứng dụng có thể xử lý kịp. Nếu listener xử lý chậm, dữ liệu lớn hơn có thể làm bộ đệm và thời gian xử lý tăng, khiến consumer lag tiếp tục tăng.

### 7.3. Network và broker load

fetch.min.bytes thấp trong môi trường lưu lượng cao có thể tạo nhiều response nhỏ. Tăng ngưỡng vừa phải có thể giảm request rate và overhead.

Ngược lại, mỗi consumer có thể phát Fetch request tới nhiều broker. Khi số consumer tăng, tổng request vẫn có thể lớn ngay cả khi từng request chứa nhiều dữ liệu. Cần đo request rate và network bytes thay vì suy luận chỉ từ một property.

### 7.4. Bộ nhớ consumer

Fetch response được lưu trong bộ đệm của client. Khi tăng kích thước fetch, số byte giữ trong bộ nhớ có thể tăng, đặc biệt khi consumer đọc nhiều partition và nhiều broker.

Cần quan sát heap, memory pressure, số record trong buffer và thời gian listener xử lý. Đừng tăng fetch.max.bytes, max.partition.fetch.bytes và concurrency cùng lúc nếu chưa ước lượng được tổng bộ nhớ có thể cần.

## 8. Chọn cấu hình theo loại workload

Không có một cặp giá trị tối ưu cho mọi consumer. Hãy bắt đầu từ mục tiêu dịch vụ, lưu lượng và kích thước record.

| Loại workload | Điểm bắt đầu minh họa | Lý do |
|---|---|---|
| Event cần phản hồi nhanh | fetch.min.bytes = 1; fetch.max.wait.ms = 50–100 | Hạn chế thời gian broker chờ để gom batch |
| Workload vừa, lưu lượng khá đều | fetch.min.bytes = 16–64 KiB; fetch.max.wait.ms = 100–200 | Tạo cơ hội gom batch vừa phải |
| Consumer throughput cao | fetch.min.bytes = 64–256 KiB; fetch.max.wait.ms = 200–500 | Có thể giảm response nhỏ nếu lưu lượng đủ |
| Topic ít event, xử lý nền | fetch.min.bytes thấp hoặc vừa; fetch.max.wait.ms theo độ trễ cho phép | Tránh chờ lâu để đạt ngưỡng byte khó đạt |
| Consumer đọc nhiều partition | Thử ngưỡng theo throughput trên từng broker và kích thước fetch thực tế | Tổng byte có thể đến từ nhiều partition, nhưng phân bố tải không đều |

Các giá trị trên là điểm khởi đầu cho thử nghiệm, không phải cấu hình khuyến nghị chung. Đặc biệt, không nên tăng fetch.min.bytes lên mức megabyte chỉ vì muốn batch lớn hơn nếu throughput của từng broker không đủ để đạt ngưỡng trong thời gian chờ.

### 8.1. Luồng cần latency thấp

Với luồng xử lý đơn hàng, thanh toán hoặc thông báo gần thời gian thực, độ trễ event có thể quan trọng hơn việc giảm số Fetch request.

Có thể bắt đầu với fetch.min.bytes bằng 1 và fetch.max.wait.ms khoảng 50–100 ms. Sau đó đo event freshness và request rate. Nếu consumer vẫn có độ trễ thấp nhưng tạo quá nhiều response nhỏ, thử tăng ngưỡng từng bước.

Không nên chỉ nhìn fetch.max.wait.ms để kết luận độ trễ. Event còn có thể chờ do consumer không được poll, listener đang xử lý batch trước, rebalance hoặc downstream chậm.

### 8.2. Luồng throughput cao

Với luồng telemetry, clickstream hoặc đồng bộ dữ liệu có lưu lượng lớn, mục tiêu có thể là tăng bytes consumed rate và giảm overhead request.

Có thể thử fetch.min.bytes 64 KiB hoặc 128 KiB, fetch.max.wait.ms 100–300 ms. Nếu broker nhận dữ liệu đều, ngưỡng sẽ đạt sớm. Nếu tải bursty, max wait cho broker thời gian gom record trong burst tiếp theo.

Theo dõi thêm max.partition.fetch.bytes và fetch.max.bytes để bảo đảm response có thể chứa kích thước batch mong muốn.

### 8.3. Topic ít lưu lượng

Với topic chỉ nhận vài event mỗi giây, ngưỡng fetch 64 KiB có thể hiếm khi đạt. Broker sẽ thường xuyên trả response sau khi hết thời gian chờ, làm tăng độ trễ của event đầu tiên trong mỗi đợt.

Trong trường hợp này, giảm fetch.min.bytes thường hữu ích hơn tăng fetch.max.wait.ms. Nếu yêu cầu latency cho phép, max wait có thể giữ ở mức vừa phải; nếu cần event tới consumer nhanh, hãy giảm thời gian chờ và xác nhận bằng phép đo end-to-end.

## 9. Đo lường và quan sát sau khi thay đổi

Không đánh giá tuning chỉ bằng consumer lag. Cần kết hợp dữ liệu fetch, latency nghiệp vụ, throughput và tài nguyên.

| Chỉ số | Điều cần quan sát |
|---|---|
| Fetch size average/max | Kích thước response có tăng sau khi nâng fetch.min.bytes không? |
| Fetch latency average | Broker mất bao lâu để trả Fetch response? |
| Fetch rate | Số Fetch request mỗi giây có giảm không? |
| Records per request | Mỗi request mang về trung bình bao nhiêu record? |
| Bytes consumed rate | Consumer đọc được bao nhiêu byte mỗi giây? |
| Records consumed rate | Tốc độ record consumer nhận |
| Consumer lag | Consumer có theo kịp tốc độ producer không? |
| Event freshness | Event chờ bao lâu từ lúc ghi vào Kafka đến lúc hoàn tất xử lý? |
| Consumer heap/GC | Bộ đệm và batch lớn có làm tăng áp lực bộ nhớ không? |
| Broker network/request metrics | Thay đổi có giảm overhead hay gây thêm áp lực broker? |

Tên metric cụ thể phụ thuộc Kafka client, JMX exporter, Micrometer và phiên bản Spring Kafka. Hãy kiểm tra các metric đang được export trong môi trường của ứng dụng trước khi tạo alert.

### 9.1. Đọc các dấu hiệu kết hợp

- Fetch size tăng, fetch rate giảm, bytes consumed rate giữ ổn định hoặc tăng: batching có thể hiệu quả hơn.
- Fetch size vẫn nhỏ và fetch latency thường gần max wait: ngưỡng min bytes có thể quá cao so với lưu lượng.
- Fetch size tăng nhưng consumer lag và event freshness xấu đi: batch lớn có thể làm ứng dụng xử lý chậm hoặc downstream không theo kịp.
- Fetch rate giảm nhưng broker network bytes không giảm: response có thể lớn hơn, nên tổng byte truyền vẫn tương đương.
- Consumer lag tăng cùng fetch rate thấp: kiểm tra assignment, poll loop, pause state, rebalance và downstream trước khi kết luận fetch settings là nguyên nhân.

### 9.2. Đo event freshness

Để đo thời gian event thực sự chờ trong pipeline, ghi timestamp ở producer hoặc trong payload/header và so sánh với thời điểm consumer hoàn tất xử lý. Đồng bộ clock giữa các máy và dùng cùng một định nghĩa timestamp.

Một consumer có lag bằng 0 vẫn có thể có event freshness cao nếu listener xử lý chậm hoặc event chờ trong bộ đệm ứng dụng. Ngược lại, lag vài trăm record có thể chấp nhận được nếu throughput cao và tuổi event vẫn nằm trong SLO.

## 10. Quy trình tuning có kiểm soát

Có thể áp dụng theo trình tự:

1. Ghi lại baseline: fetch rate, fetch size, fetch latency, bytes consumed rate, consumer lag, event freshness, heap và broker load.
2. Chọn mục tiêu chính: giảm latency, tăng throughput hay giảm request overhead.
3. Xác định lưu lượng trung bình và burst theo broker, không chỉ tổng lưu lượng toàn cluster.
4. Thay đổi fetch.min.bytes trước hoặc theo cặp với fetch.max.wait.ms bằng một bước nhỏ.
5. Chạy workload đại diện trong giờ cao điểm và thấp điểm.
6. So sánh p50/p95/p99 event freshness, throughput, request rate và tài nguyên.
7. Giữ cấu hình nếu cải thiện mục tiêu mà không làm SLO khác suy giảm; nếu không, hoàn nguyên và thử bước khác.
8. Ghi lại giá trị, lý do và kết quả để lần tuning sau có baseline đáng tin cậy.

Khi thử nghiệm, giữ ổn định các yếu tố như producer throughput, số consumer, partition assignment và kích thước record nếu có thể. Nếu thay đổi tất cả cùng lúc, sẽ khó xác định nguyên nhân tạo ra kết quả.

## 11. Các lỗi cấu hình và chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Event đến consumer chậm hơn sau tuning | fetch.min.bytes quá cao hoặc fetch.max.wait.ms quá dài | Kiểm tra fetch latency, event freshness và tốc độ record đến |
| Fetch response thường nhỏ hơn fetch.min.bytes | Không đủ dữ liệu trước khi hết max wait | So sánh throughput thực tế với ngưỡng byte |
| Fetch request rate rất cao | Ngưỡng byte thấp, nhiều consumer hoặc nhiều partition/broker | Xem fetch rate theo client và broker |
| Consumer lag tăng dù fetch size lớn | Listener/downstream xử lý chậm, poll không đều hoặc rebalance | So sánh records consumed rate với processing rate |
| Heap tăng sau khi nâng fetch limits | Fetch response và buffer lớn hơn | Kiểm tra fetch.max.bytes, max.partition.fetch.bytes, concurrency và GC |
| Chỉ một số partition bị trễ | Lưu lượng hoặc phân bố partition không đều | Xem lag và event age theo partition, broker leader và key distribution |
| Tuning không thay đổi hành vi | Property không được áp dụng cho ConsumerFactory thực tế hoặc listener dùng factory khác | Kiểm tra cấu hình effective của từng consumer |

Nếu nghi ngờ cấu hình chưa được áp dụng, xác định consumer client ID và factory tạo ra nó. Ứng dụng có thể có nhiều listener container hoặc nhiều ConsumerFactory với cấu hình riêng. Việc sửa application.yml không có tác dụng với factory tự tạo nếu factory không nhận các property đó.

## 12. Những nhầm lẫn cần tránh

**Cho rằng fetch.min.bytes là số record tối thiểu.** Đây là số byte, nên kích thước record ảnh hưởng trực tiếp đến số record có trong response.

**Cho rằng broker luôn phải trả đủ fetch.min.bytes.** Đây là ngưỡng broker cố gắng đạt; fetch.max.wait.ms giới hạn thời gian chờ. Khi hết thời hạn, broker có thể trả ít byte hơn.

**Cho rằng fetch.max.wait.ms là độ trễ tối đa end-to-end.** Nó chỉ giới hạn thời gian broker chờ cho Fetch request trong điều kiện chưa đủ dữ liệu. Network, poll, listener và downstream vẫn tạo thêm độ trễ.

**Cho rằng tăng fetch.min.bytes luôn tăng throughput.** Nếu lưu lượng thấp, broker không thể gom đủ dữ liệu và consumer chỉ chờ lâu hơn. Throughput còn phụ thuộc producer, partition, broker và tốc độ xử lý của ứng dụng.

**Nhầm max.poll.records với kích thước fetch.** max.poll.records giới hạn số record trả cho ứng dụng trong một lần poll; fetch limits điều khiển dữ liệu broker trả về.

**Nhầm consumer fetch với broker replication fetch.** fetch.min.bytes và fetch.max.wait.ms là consumer properties. replica.fetch.min.bytes và replica.fetch.wait.max.ms thuộc cơ chế follower lấy dữ liệu từ leader.

**Tăng concurrency để bù cho fetch tuning chưa phù hợp.** Nhiều consumer hơn có thể tăng request và áp lực broker, đồng thời không giải quyết listener hoặc downstream chậm.

## 13. Ví dụ tổng hợp cho consumer đơn hàng

Giả sử Order Service ghi event OrderCreated vào topic orders.created. Consumer fulfillment cần xử lý event trong vòng 2 giây. Mỗi event trung bình khoảng 1 KiB, lưu lượng bình thường khoảng 200 record/giây trên các broker mà consumer đọc.

Nếu consumer đặt fetch.min.bytes bằng 64 KiB, cần khoảng 64 record cỡ 1 KiB để đạt ngưỡng trên một response. Với tốc độ 200 record/giây phân bố đều, có thể gom lượng dữ liệu này trong khoảng 320 ms nếu toàn bộ lưu lượng tập trung trên cùng broker. Trên thực tế, partition phân bố qua nhiều broker nên mỗi broker có thể nhận tốc độ thấp hơn và thời gian gom sẽ khác.

Một điểm bắt đầu thử nghiệm có thể là:

~~~yaml
spring:
  kafka:
    consumer:
      fetch-min-size: 16KB
      fetch-max-wait: 100ms
      max-poll-records: 200
~~~

Sau khi triển khai thử, đội vận hành đo:

- p95/p99 từ lúc event được ghi vào Kafka đến lúc fulfillment hoàn tất.
- Fetch size average và fetch rate.
- Records consumed rate và consumer lag theo partition.
- Thời gian xử lý listener và latency của downstream fulfillment.
- Heap và GC khi consumer nhận batch lớn hơn.

Nếu event freshness còn dư nhiều nhưng fetch rate cao và response nhỏ, có thể thử nâng fetch.min.bytes lên 32 KiB hoặc 64 KiB. Nếu p99 event freshness tiến gần SLO 2 giây, giảm ngưỡng hoặc max wait để giảm thời gian gom dữ liệu. Nếu lag tăng do fulfillment API chậm, cần xử lý downstream trước; giảm fetch wait không thể làm listener xử lý nhanh hơn.

Các con số trên chỉ là ví dụ minh họa cách suy luận từ throughput và kích thước record. Cấu hình cuối cùng phải dựa trên số liệu thực tế theo broker, partition và consumer group.

## 14. Ghi nhớ

fetch.min.bytes quyết định lượng byte tối thiểu broker cố gắng gom cho Fetch response; fetch.max.wait.ms giới hạn thời gian broker chờ để đạt ngưỡng đó. Giá trị thấp thường ưu tiên độ trễ, giá trị cao hơn có thể cải thiện batch và giảm request overhead khi lưu lượng đủ lớn.

Trong Spring Kafka, cấu hình hai property này trên consumer factory được listener container sử dụng. Khi tuning, hãy xem cả fetch.max.bytes, max.partition.fetch.bytes, max.poll.records, concurrency, consumer lag và event freshness. Đo workload thực tế trước và sau thay đổi để cân bằng độ trễ, throughput và tài nguyên broker/consumer.

