# fetch.min.bytes và fetch.max.wait.ms

`fetch.min.bytes` và `fetch.max.wait.ms` là hai cấu hình của Kafka consumer điều khiển cách broker trả dữ liệu trong một fetch request. `fetch.min.bytes` đặt ngưỡng byte mong muốn cho một fetch response; `fetch.max.wait.ms` đặt thời gian tối đa broker chờ để gom đủ dữ liệu trước khi trả response. Kết hợp hai tham số này giúp cân bằng throughput, hiệu quả network và latency khi consumer đọc event từ Kafka.

Trong module `SPRING_KAFKA_MESSAGING`, consumer nhận event bằng `@KafkaListener`, còn Spring Kafka quản lý `KafkaConsumer` bên dưới listener container. Hai thuộc tính này thuộc cấu hình consumer; chúng ảnh hưởng đến lượng dữ liệu broker gửi trong một lần fetch và thời gian chờ phía broker, không quyết định số lần listener được gọi hay số record được commit.

## 1. Consumer fetch dữ liệu như thế nào?

Consumer không gửi một request riêng cho từng record. Kafka consumer gửi fetch request tới broker đang giữ leader của các partition được assign. Broker trả về record batches từ những partition trong request. Khi chưa có đủ dữ liệu, broker có thể giữ request trong thời gian giới hạn để gom thêm bytes.

~~~mermaid
sequenceDiagram
    participant C as Kafka consumer
    participant B as Partition leader broker
    C->>B: Fetch(minBytes, maxWaitMs)
    Note over B: Chờ dữ liệu được append
    alt Đủ fetch.min.bytes
        B-->>C: Fetch response với dữ liệu đã gom
    else Hết fetch.max.wait.ms
        B-->>C: Fetch response với lượng dữ liệu hiện có
    end
    C->>C: Đưa record vào buffer và trả qua poll()
~~~

Broker trả response khi đạt một trong hai điều kiện: lượng dữ liệu đủ ngưỡng `fetch.min.bytes`, hoặc thời gian chờ đạt `fetch.max.wait.ms`. Nếu traffic thấp, response có thể nhỏ hơn ngưỡng min khi thời gian chờ đã hết. Nếu traffic cao, ngưỡng min có thể đạt rất nhanh nên broker trả response trước khi hết max wait.

## 2. `fetch.min.bytes` là gì?

`fetch.min.bytes` là số byte dữ liệu tối thiểu mà consumer mong muốn broker trả về trong một fetch response. Giá trị mặc định thường là `1`, nghĩa là broker có thể trả ngay khi có dữ liệu. Đặt giá trị lớn hơn giúp broker gom nhiều dữ liệu hơn vào response, giảm số response nhỏ và có thể cải thiện hiệu quả network khi throughput cao.

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.min.bytes: 65536
~~~

Giá trị `65536` tương đương 64 KiB. Broker sẽ cố gắng đợi đến khi response có ít nhất khoảng 64 KiB dữ liệu hoặc đến giới hạn `fetch.max.wait.ms`. Đây là ngưỡng cho fetch response, không phải yêu cầu mỗi record hoặc mỗi partition phải có 64 KiB.

Nếu consumer được assign nhiều partition trên cùng broker, dữ liệu từ các partition đó có thể cùng đóng góp vào ngưỡng byte của fetch request tương ứng. Vì vậy, một partition riêng lẻ không cần tự tạo đủ `fetch.min.bytes`.

## 3. `fetch.max.wait.ms` là gì?

`fetch.max.wait.ms` là thời gian tối đa broker chờ để đáp ứng điều kiện `fetch.min.bytes`. Giá trị mặc định thường là `500` mili giây.

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.max.wait.ms: 100
~~~

Broker chờ tối đa 100 ms cho fetch request nếu chưa gom đủ `fetch.min.bytes`. Khi hết thời gian, broker trả lượng dữ liệu đang có, kể cả khi lượng byte thấp hơn ngưỡng min.

Đây là thời gian chờ ở phía broker cho fetch request. Nó không phải thời gian delay trước mỗi lần listener chạy, không phải `max.poll.interval.ms` và cũng không phải timeout của một lần gọi nghiệp vụ.

## 4. Hai tham số phối hợp với nhau

Hai cấu hình cần được đọc cùng nhau:

| `fetch.min.bytes` | `fetch.max.wait.ms` | Hành vi thường thấy |
|---:|---:|---|
| 1 | 500 | Có dữ liệu là broker có thể trả sớm; max wait chủ yếu là giới hạn khi chưa có dữ liệu |
| 65536 | 100 | Gom đến khoảng 64 KiB hoặc chờ tối đa 100 ms |
| 262144 | 250 | Cố gom khoảng 256 KiB; có thể tăng batching nhưng chấp nhận chờ lâu hơn |
| 1 | 50 | Ưu tiên response sớm, giảm thời gian chờ khi traffic thưa |

Ví dụ đặt `fetch.min.bytes` lớn nhưng `fetch.max.wait.ms` thấp: broker chỉ có một khoảng ngắn để gom dữ liệu, nên thường trả response nhỏ hơn ngưỡng khi traffic thấp. Ngược lại, min nhỏ và max wait lớn không buộc broker phải đợi đủ thời gian nếu đã có dữ liệu đáp ứng ngưỡng min.

Không có một cặp giá trị tối ưu cho mọi topic. Cần chọn theo lưu lượng, kích thước record, số partition consumer nhận, latency mục tiêu và khả năng downstream.

## 5. Cấu hình trong Spring Boot

Spring Boot chuyển các thuộc tính Kafka consumer qua map `spring.kafka.consumer.properties`. Ví dụ cấu hình chung:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.acme.orders.OrderCreatedEvent
        spring.json.trusted.packages: com.acme.orders
        fetch.min.bytes: 65536
        fetch.max.wait.ms: 100
        request.timeout.ms: 30000
~~~

Các key `fetch.min.bytes`, `fetch.max.wait.ms` và `request.timeout.ms` là tên cấu hình gốc của Kafka consumer. Chúng được đặt trong `properties` vì Spring Boot không tạo một field type-safe riêng cho mọi thuộc tính của Kafka client.

Giữ `request.timeout.ms` lớn hơn `fetch.max.wait.ms` và có đủ khoảng dư cho network/broker processing. Nếu request timeout ngắn hơn thời gian broker có thể giữ fetch request, consumer có thể timeout trước khi broker hoàn tất response.

## 6. Cấu hình trực tiếp qua `ConsumerFactory`

Nếu tạo `ConsumerFactory` thủ công, có thể đặt các Kafka consumer property trong map cấu hình:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;

@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    public ConsumerFactory<String, String> ordersConsumerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-service");
        properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        properties.put(ConsumerConfig.FETCH_MIN_BYTES_CONFIG, 65_536);
        properties.put(ConsumerConfig.FETCH_MAX_WAIT_MS_CONFIG, 100);
        properties.put(ConsumerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);

        return new DefaultKafkaConsumerFactory<>(properties);
    }
}
~~~

Không khai báo cùng một consumer property ở nhiều nơi với các giá trị khác nhau mà không biết thứ tự override. Khi Spring Boot auto-configure factory, custom `ConsumerFactory` có thể thay đổi hoặc bỏ qua một phần cấu hình Boot; cần kiểm tra factory thực tế mà listener container sử dụng.

## 7. Phân biệt với các giới hạn fetch khác

`fetch.min.bytes` và `fetch.max.wait.ms` không phải giới hạn kích thước tối đa của response. Các cấu hình liên quan khác:

| Cấu hình | Vai trò | Ảnh hưởng chính |
|---|---|---|
| `fetch.min.bytes` | Ngưỡng byte tối thiểu mong muốn | Broker có thể đợi để gom batch |
| `fetch.max.wait.ms` | Thời gian broker chờ tối đa | Giới hạn thời gian chờ gom batch |
| `fetch.max.bytes` | Giới hạn tổng byte mục tiêu cho một fetch response | Kiểm soát lượng dữ liệu một fetch có thể trả |
| `max.partition.fetch.bytes` | Giới hạn byte mục tiêu cho mỗi partition trong fetch | Kiểm soát lượng dữ liệu theo partition |
| `max.poll.records` | Số record tối đa trả về từ một lần `poll()` | Kiểm soát số record ứng dụng nhận mỗi poll |
| `max.poll.interval.ms` | Thời gian tối đa giữa các lần `poll()` | Kiểm soát liveness của consumer group |

Kafka có thể trả record batch đầu tiên lớn hơn `fetch.max.bytes` hoặc `max.partition.fetch.bytes` để consumer không bị kẹt khi batch đầu tiên trong partition vượt giới hạn. Vì vậy, hai cấu hình max là giới hạn mục tiêu cho fetch, không phải bảo đảm cứng rằng response không bao giờ vượt kích thước đó.

`max.poll.records` giới hạn số record trả từ `poll()`, không giới hạn byte broker gửi trong fetch response. Consumer có thể fetch và buffer dữ liệu trước khi ứng dụng lấy record qua poll.

## 8. Phân biệt với poll timeout và listener container

Spring Kafka listener container gọi `KafkaConsumer.poll()` theo vòng lặp. `pollTimeout` của container điều khiển thời gian truyền vào lời gọi poll; `fetch.max.wait.ms` điều khiển thời gian broker có thể giữ fetch request để gom đủ byte.

| Thành phần | Nằm ở đâu? | Điều khiển điều gì? |
|---|---|---|
| `fetch.max.wait.ms` | Kafka broker xử lý fetch request | Chờ dữ liệu trên broker |
| `pollTimeout` | Spring Kafka listener container | Thời gian một lần `poll()` chờ kết quả |
| `max.poll.interval.ms` | Kafka consumer group | Giới hạn thời gian giữa các lần poll |
| `max.poll.records` | Kafka consumer | Số record tối đa trả về từ poll |

Các thời gian này tương tác trong tổng latency nhưng không thay thế nhau. Tăng `pollTimeout` không làm broker gom nhiều byte hơn; tăng `fetch.max.wait.ms` cũng không làm listener xử lý nhanh hơn.

## 9. Chọn cấu hình cho workload latency thấp

Với event cần được xử lý sớm, thường giữ `fetch.min.bytes` thấp để broker trả response ngay khi có dữ liệu. Có thể giảm `fetch.max.wait.ms` để giới hạn thời gian broker chờ khi chưa có dữ liệu.

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.min.bytes: 1
        fetch.max.wait.ms: 50
~~~

Ví dụ này phù hợp để bắt đầu benchmark cho workload ít record, yêu cầu latency thấp. Nó có thể làm tăng số fetch response nhỏ và request rate khi traffic cao. Không nên giảm max wait quá thấp nếu broker/consumer ở xa nhau hoặc cluster đang chịu tải lớn mà chưa đo tác động.

## 10. Chọn cấu hình cho workload throughput cao

Với workload có lưu lượng ổn định và record nhỏ, có thể tăng `fetch.min.bytes` để gom nhiều dữ liệu trong một response và chọn `fetch.max.wait.ms` vừa đủ:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.min.bytes: 131072
        fetch.max.wait.ms: 100
        fetch.max.bytes: 52428800
        max.partition.fetch.bytes: 1048576
        max.poll.records: 500
~~~

Trong ví dụ, consumer mong muốn gom khoảng 128 KiB trước khi broker trả response, nhưng broker chỉ chờ tối đa 100 ms. Các giới hạn fetch max và poll records được giữ rõ ràng để có thể phân tích riêng lượng byte fetch với số record ứng dụng xử lý mỗi poll.

Nếu traffic thấp, broker vẫn trả response khi hết max wait, dù chưa đạt 128 KiB. Nếu downstream không xử lý kịp, tăng batch fetch có thể làm tăng lượng dữ liệu buffer và áp lực bộ nhớ; cần phối hợp với `max.poll.records`, concurrency và backpressure.

## 11. Ảnh hưởng đến latency và throughput

Tăng `fetch.min.bytes` thường có các tác động:

- Giảm số response nhỏ khi dữ liệu đến đều.
- Tăng số byte trung bình trong mỗi fetch response.
- Có thể cải thiện network efficiency và throughput.
- Có thể làm tăng thời gian chờ khi traffic thưa hoặc phân tán trên nhiều partition/broker.

Tăng `fetch.max.wait.ms` thường có các tác động:

- Cho broker thêm thời gian gom record vào một response.
- Có thể tăng batch size và giảm tần suất response nhỏ.
- Có thể tăng latency của record mới khi chưa đạt `fetch.min.bytes`.
- Có thể làm consumer cảm nhận chậm hơn khi topic có traffic thấp.

Giảm hai tham số có thể giúp record đến listener sớm hơn nhưng cũng có thể tăng request/response overhead. Hiệu quả thực tế phụ thuộc kích thước record, compression, số partition, số consumer, tốc độ producer và network.

## 12. Cách benchmark và điều chỉnh

Điều chỉnh theo quy trình có kiểm soát:

1. Ghi baseline với cấu hình hiện tại: throughput, p50/p95/p99 processing latency, consumer lag và fetch response size.
2. Dùng workload đại diện: tốc độ producer, phân bố key, số partition và kích thước payload gần production.
3. Thay đổi một tham số mỗi lần, ví dụ tăng `fetch.min.bytes` từ 1 lên 64 KiB.
4. Đo lại latency và throughput trong cả traffic cao lẫn traffic thấp.
5. Thử thay đổi `fetch.max.wait.ms` riêng để xác định ảnh hưởng của broker wait.
6. Kiểm tra memory/buffer, CPU, network, broker request rate và consumer lag.
7. Chọn cấu hình đáp ứng SLO latency và throughput, sau đó kiểm thử khi downstream chậm.

Không chọn giá trị chỉ dựa vào throughput tối đa. Nếu p99 latency vượt SLO hoặc consumer lag tăng liên tục, cấu hình có thể không phù hợp dù bytes/response tăng.

## 13. Metrics và dấu hiệu cấu hình chưa phù hợp

Theo dõi các chỉ số từ consumer, Spring Kafka và broker:

| Chỉ số | Dấu hiệu cần chú ý |
|---|---|
| Consumer fetch rate | Quá nhiều fetch request nhỏ hoặc fetch rate giảm bất thường |
| Fetch size / bytes consumed rate | Response nhỏ hơn mong đợi hoặc dữ liệu fetch không theo kịp producer |
| Fetch latency | Thời gian fetch tăng khi tăng max wait |
| Records consumed rate | Throughput thực tế của consumer |
| Consumer lag theo partition | Backlog tăng dù fetch response lớn |
| Listener processing time | Downstream chậm khiến consumer không xử lý kịp |
| Rebalance count | Có thể tăng khi xử lý/poll bị chậm |
| Heap, GC và network throughput | Phát hiện buffer hoặc fetch batch gây áp lực tài nguyên |

Tên metric cụ thể phụ thuộc Kafka client version, Spring Kafka Micrometer integration và hệ thống monitoring. Hãy xác minh metric đang được export thay vì giả định mọi tên trong dashboard đều có sẵn.

## 14. Những lỗi thường gặp

- **Đặt `fetch.min.bytes` quá cao cho topic ít traffic:** broker thường phải chờ gần hết max wait rồi mới trả response nhỏ.
- **Đặt `fetch.max.wait.ms` quá lớn:** tăng thời gian chờ khi chưa đủ byte, làm latency tăng.
- **Nghĩ rằng max wait là delay cố định:** broker trả sớm khi đạt min bytes.
- **Nhầm min bytes là ngưỡng trên từng partition:** đó là ngưỡng cho fetch response, không phải từng record/partition.
- **Nhầm `max.poll.records` với fetch size:** một tham số giới hạn record trả qua poll, tham số kia điều khiển byte fetch.
- **Nhầm `pollTimeout` với broker wait:** chúng nằm ở hai lớp khác nhau.
- **Đặt `request.timeout.ms` thấp hơn fetch wait:** client có thể timeout trước khi fetch response được trả.
- **Tăng fetch batch mà không theo dõi memory:** dữ liệu buffer lớn hơn có thể tăng heap pressure.
- **Chỉ benchmark traffic cao:** cấu hình gom batch tốt khi tải cao có thể làm latency xấu khi tải thấp.
- **Giả định fetch max là giới hạn cứng:** Kafka có ngoại lệ cho record batch đầu tiên để bảo đảm consumer tiến triển.

## 15. Checklist cấu hình

- [ ] `fetch.min.bytes` được chọn theo traffic và latency SLO.
- [ ] `fetch.max.wait.ms` giới hạn thời gian gom batch phù hợp.
- [ ] Đã phân biệt hai thuộc tính với `fetch.max.bytes` và `max.partition.fetch.bytes`.
- [ ] `max.poll.records` được tune độc lập theo thời gian xử lý listener.
- [ ] `pollTimeout` và `max.poll.interval.ms` được hiểu đúng ở lớp container/consumer.
- [ ] `request.timeout.ms` lớn hơn fetch wait và có network margin.
- [ ] Đã benchmark cả traffic cao và traffic thấp.
- [ ] Đã theo dõi fetch size, fetch latency, consumer lag và listener processing time.
- [ ] Đã kiểm tra heap/network khi tăng batch size.
- [ ] Đã kiểm thử với số partition, concurrency và payload gần production.

`fetch.min.bytes` quyết định lượng dữ liệu consumer mong muốn gom trong một fetch response, còn `fetch.max.wait.ms` giới hạn thời gian broker chờ để gom lượng dữ liệu đó. Tăng chúng có thể cải thiện batching và throughput nhưng phải đánh đổi latency, đặc biệt khi traffic thấp. Cấu hình tốt cần được chọn bằng benchmark thực tế và đánh giá cùng các giới hạn fetch, poll, memory và năng lực downstream.
