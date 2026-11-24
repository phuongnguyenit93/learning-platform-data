# Phân biệt Kafka Binder thông thường với Kafka Streams Binder

Spring Cloud Stream có hai binder thường được dùng khi xây dựng ứng dụng dựa trên Apache Kafka: **Kafka Binder thông thường** và **Kafka Streams Binder**. Cả hai đều kết nối ứng dụng với Kafka topic, dùng cấu hình function và binding của Spring Cloud Stream, nhưng chúng phục vụ hai mô hình lập trình khác nhau.

Kafka Binder thông thường tích hợp với Spring Kafka để gửi và nhận message qua producer, consumer và listener container. Ứng dụng thường xử lý từng payload hoặc `Message<?>` bằng `Supplier`, `Function` và `Consumer`. Kafka Streams Binder tích hợp Kafka Streams DSL để xây dựng topology xử lý luồng, với các kiểu `KStream`, `KTable` và `GlobalKTable`, hỗ trợ phép biến đổi liên tục, join, window, aggregation và state store.

Bài thuộc chương **Kafka Binder** của module `SPRING_CLOUD_STREAM`. Ta sẽ so sánh hai binder theo mô hình lập trình, runtime, cấu hình, consumer group, state, scaling, bảo đảm giao nhận và cách kiểm thử để chọn đúng công cụ cho từng bài toán.

## 1. Hai binder, hai mô hình xử lý

Kafka Binder thông thường coi Kafka là hệ thống vận chuyển message. Producer gửi record vào topic; consumer nhận record theo consumer group; Spring Cloud Stream chuyển payload thành kiểu Java rồi gọi function hoặc consumer của ứng dụng.

Kafka Streams Binder coi Kafka là nguồn và đích của một topology xử lý luồng. Ứng dụng mô tả các phép toán trên stream/table; Kafka Streams runtime xây dựng topology, quản lý task, state store, changelog, repartition và offset.

```text
Kafka Binder thông thường

Kafka topic
    |
    v
Spring Kafka listener container
    |
    v
Spring Message / Java payload
    |
    v
Supplier / Function / Consumer
    |
    v
Output binding -> Kafka topic


Kafka Streams Binder

Kafka topic(s)
    |
    v
Kafka Streams source node
    |
    v
KStream / KTable operations
    |
    +--> filter / map / join / window / aggregate
    |
    v
Kafka Streams sink node
    |
    v
Kafka topic(s)
```

Hai binder không phải hai tên gọi của cùng một chế độ. Việc chọn binder quyết định kiểu hàm, runtime, cách quản lý state và cách cấu hình xử lý message.

Hai dependency starter thường dùng có tên:

| Binder | Maven artifact |
|---|---|
| Kafka Binder thông thường | `spring-cloud-starter-stream-kafka` |
| Kafka Streams Binder | `spring-cloud-starter-stream-kafka-streams` |

Đặt dependency theo Spring Cloud release train/BOM của dự án để các phiên bản Spring Cloud Stream, Spring Kafka và Kafka Streams tương thích. Không tự nâng riêng một thư viện Kafka Streams vượt khỏi ma trận tương thích của release train.

## 2. So sánh tổng quan

| Tiêu chí | Kafka Binder thông thường | Kafka Streams Binder |
|---|---|---|
| Mục tiêu chính | Gửi/nhận message qua Kafka | Xây dựng topology xử lý stream trên Kafka |
| API xử lý | Payload Java, `Message<?>`, `Supplier`/`Function`/`Consumer` | Kafka Streams DSL: `KStream`, `KTable`, `GlobalKTable` |
| Runtime | Spring Kafka producer và listener container | Kafka Streams runtime, stream thread và task |
| Xử lý state | Ứng dụng tự quản lý state, thường qua database/cache | Có state store cục bộ và changelog topic được Kafka Streams quản lý |
| Join và window | Tự triển khai hoặc gọi hệ thống khác | Có operator join, window và aggregation trong DSL |
| Consumer identity | Consumer group của binding | `application.id` của Kafka Streams application |
| Scaling | Consumer group chia partition cho consumer | Kafka Streams chia task/partition cho instance và stream thread |
| Offset và phục hồi | Theo listener container, ack mode và cấu hình binder | Kafka Streams quản lý offset, task, state restoration và processing guarantee |
| Phù hợp | Event integration, command handler, message processing thông thường | Stateful stream processing, join, window, aggregation và topology phức tạp |

Kafka Binder thông thường phù hợp với phần lớn luồng message nghiệp vụ. Kafka Streams Binder phù hợp khi bài toán thực sự cần các phép toán stream và state được quản lý theo topology.

## 3. Kafka Binder thông thường xử lý message như thế nào?

Với Kafka Binder thông thường, function nhận payload Java đã được message converter chuyển đổi. Ví dụ, một function làm giàu sự kiện đơn hàng:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String customerId, String status) {}

record EnrichedOrderEvent(
    String orderId,
    String customerId,
    String status,
    String source
) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderEvent, EnrichedOrderEvent> enrichOrder() {
        return event -> new EnrichedOrderEvent(
            event.orderId(),
            event.customerId(),
            event.status(),
            "order-service"
        );
    }
}
```

Cấu hình binding:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      kafka:
        binder:
          brokers: localhost:9092
      bindings:
        enrichOrder-in-0:
          destination: orders.created
          group: order-enrichment
          content-type: application/json
        enrichOrder-out-0:
          destination: orders.enriched
          content-type: application/json
```

Function nhận một `OrderEvent`, tạo `EnrichedOrderEvent`, rồi output binding gửi payload đến topic `orders.enriched`. Ứng dụng không cần biết Kafka `ConsumerRecord` hoặc Kafka Streams topology để thực hiện phép biến đổi đơn giản này.

Kafka Binder thông thường phù hợp khi logic là xử lý một message hoặc một sự kiện độc lập, gọi database/API, kiểm tra nghiệp vụ rồi tạo một message đầu ra. Ứng dụng có thể dùng `Message<T>` nếu cần đọc headers, correlation ID hoặc metadata vận chuyển.

## 4. Kafka Streams Binder dùng Kafka Streams DSL

Kafka Streams Binder đưa các kiểu dữ liệu của Kafka Streams vào chữ ký function. Ví dụ function nhận `KStream<String, String>` và chuẩn hóa nội dung:

```java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class StreamTopologyConfiguration {

    @Bean
    Function<KStream<String, String>, KStream<String, String>> normalizeOrders() {
        return input -> input
            .filter((key, value) -> value != null && !value.isBlank())
            .mapValues(String::trim)
            .mapValues(String::toUpperCase);
    }
}
```

Function này mô tả một topology: đọc record từ source topic, loại bỏ giá trị rỗng, chuẩn hóa payload rồi ghi kết quả qua output binding. Nó không được gọi một lần cho từng message như `Function<OrderEvent, Result>` của Kafka Binder thông thường. Kafka Streams Binder gọi function để xây dựng topology; Kafka Streams runtime thực thi topology đó liên tục khi record đến.

Cấu hình Kafka Streams Binder:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrders
    stream:
      bindings:
        normalizeOrders-in-0:
          destination: orders.raw
        normalizeOrders-out-0:
          destination: orders.normalized
      kafka:
        streams:
          binder:
            brokers: localhost:9092
            applicationId: order-normalizer
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
              default.value.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
```

`applicationId` là định danh của Kafka Streams application và được dùng trong việc quản lý consumer group, state và các tài nguyên nội bộ. Cấu hình `default.key.serde` và `default.value.serde` xác định cách serialize/deserialize key và value mặc định. Với kiểu dữ liệu phức tạp, cần cấu hình Serde tương thích hoặc chỉ định Serde cụ thể cho phép toán/topology.

Lưu ý: ví dụ dùng chuỗi để thể hiện rõ cấu hình Serde. Khi dùng JSON/Avro/Protobuf hoặc kiểu record Java, hãy cấu hình Serde tương ứng và kiểm thử schema thực tế; message converter của Kafka Binder thông thường không tự động thay thế Serde của Kafka Streams.

## 5. Khác biệt về function signature

Chữ ký hàm thường là dấu hiệu dễ nhận biết binder đang dùng:

| Chữ ký function | Binder phù hợp | Ý nghĩa |
|---|---|---|
| `Function<OrderEvent, OrderResult>` | Kafka Binder thông thường | Xử lý một payload rồi trả một payload |
| `Consumer<OrderEvent>` | Kafka Binder thông thường | Nhận một payload và thực hiện tác động |
| `Supplier<OrderEvent>` | Kafka Binder thông thường | Tạo message đầu ra theo cơ chế supplier/poller |
| `Function<KStream<K,V>, KStream<K2,V2>>` | Kafka Streams Binder | Xây dựng topology stream-to-stream |
| `Function<KStream<K,V>, KTable<K2,V2>>` | Kafka Streams Binder | Chuyển stream thành bảng trạng thái |
| `BiFunction<KStream<K,V>, KTable<K2,V2>, KStream<K3,V3>>` | Kafka Streams Binder | Kết hợp hai input stream/table |

Không chỉ nhìn tên bean để đoán binder. Cần xem dependency, binder được chọn và kiểu tham số. Một `Function<Flux<T>, Flux<R>>` thuộc mô hình reactive của Spring Cloud Stream thông thường, không phải Kafka Streams DSL chỉ vì nó xử lý nhiều phần tử.

## 6. KStream, KTable và GlobalKTable

Kafka Streams DSL cung cấp các abstraction khác nhau:

- **`KStream<K,V>`** biểu diễn một luồng record. Mỗi record là một sự kiện độc lập; các phép toán như `filter`, `map`, `flatMap`, `branch` và `merge` thường làm biến đổi luồng sự kiện.
- **`KTable<K,V>`** biểu diễn trạng thái mới nhất theo key. Một record cập nhật key có thể thay thế giá trị trước đó trong bảng. KTable phù hợp với dữ liệu dạng changelog hoặc projection theo khóa.
- **`GlobalKTable<K,V>`** biểu diễn một bảng được materialize trên mỗi instance của ứng dụng Kafka Streams. Nó hữu ích cho một số kiểu join cần bảng tham chiếu toàn cục, đổi lại mỗi instance phải duy trì bản sao trạng thái.

Ví dụ về ý nghĩa:

| Dữ liệu | Abstraction thường phù hợp |
|---|---|
| Các sự kiện `OrderPlaced`, `OrderShipped` | `KStream` |
| Trạng thái mới nhất của một tài khoản theo `accountId` | `KTable` |
| Bảng mã quốc gia nhỏ cần tra cứu trên từng instance | `GlobalKTable` |

Một KTable không đơn thuần là một collection trong bộ nhớ. Nó biểu diễn trạng thái có khóa và được cập nhật từ changelog stream. Các phép toán stateful cần key, partitioning và Serde phù hợp.

## 7. State store và phục hồi trạng thái

Một điểm khác biệt quan trọng là Kafka Streams hỗ trợ stateful processing. Các phép toán như `count`, `aggregate`, `reduce`, windowed aggregation hoặc join có thể cần state store.

State store thường được lưu cục bộ trên instance xử lý. Kafka Streams dùng changelog topic để ghi lại thay đổi trạng thái, nhờ đó state có thể được khôi phục khi task được chuyển sang instance khác hoặc tiến trình khởi động lại. Với các phép toán cần repartition, Kafka Streams có thể tạo repartition topic để đưa record cùng key về cùng partition trước khi tính toán.

```text
Input topic
    |
    v
Repartition (nếu cần)
    |
    v
Stateful operator
    |
    +----> Local state store
    |             |
    |             +----> Changelog topic
    |
    v
Output topic
```

Kafka Binder thông thường không tự tạo state store cho function. Nếu consumer thông thường cần state, ứng dụng thường quản lý state trong database, cache hoặc một hệ thống khác. Đây là lựa chọn hợp lý khi state là dữ liệu nghiệp vụ cần truy vấn độc lập, dùng chung nhiều dịch vụ hoặc có vòng đời riêng.

State store của Kafka Streams phù hợp với state gắn chặt với topology và key/partition. Cần thiết kế dung lượng local disk, changelog retention, restore time và cách truy vấn state trước khi đưa vào production.

## 8. Join, window và aggregation

Kafka Streams Binder có lợi thế khi cần xử lý quan hệ giữa các luồng sự kiện:

- Join hai `KStream` theo key và trong một cửa sổ thời gian.
- Join `KStream` với `KTable` để bổ sung dữ liệu tham chiếu theo trạng thái mới nhất.
- Dùng `GlobalKTable` cho bảng tra cứu được sao chép trên các instance.
- Windowed aggregation để đếm hoặc tổng hợp sự kiện trong tumbling, hopping hoặc session window.
- Materialize kết quả thành state store để truy vấn hoặc tiếp tục xử lý.

Ví dụ bài toán: tính tổng giá trị đơn hàng theo khách hàng trong mỗi cửa sổ 5 phút. Với Kafka Streams DSL, có thể group theo `customerId`, dùng windowed aggregation và xuất kết quả. Nếu làm bằng Kafka Binder thông thường, ứng dụng phải tự quản lý trạng thái, thời gian cửa sổ, xử lý sự kiện đến muộn và tính nhất quán của cập nhật.

Kafka Streams không tự giải quyết mọi vấn đề nghiệp vụ của window. Cần quy định timestamp extractor, grace period, retention, key, Serde và cách xử lý record đến muộn. Cấu hình sai có thể làm kết quả bị loại hoặc state store giữ dữ liệu lâu hơn dự kiến.

## 9. Consumer group và application.id

Kafka Binder thông thường sử dụng `group` trên input binding để tạo consumer group. Các consumer thuộc cùng group phối hợp chia partition của topic. Nếu `group` khác nhau, các nhóm thường đọc độc lập và duy trì offset riêng.

Kafka Streams Binder dùng `application.id` để xác định Kafka Streams application. Các instance có cùng `application.id` tham gia cùng một ứng dụng logic; Kafka Streams phân phối task giữa các instance. Một ứng dụng logic khác cần `application.id` khác để xử lý độc lập.

| Khái niệm | Kafka Binder thông thường | Kafka Streams Binder |
|---|---|---|
| Danh tính nhóm xử lý | `group` của input binding | `application.id` |
| Chia tải | Kafka consumer group gán partition cho consumer | Kafka Streams gán task/partition cho instance và stream thread |
| State nội bộ | Không tự có state store của Kafka Streams | State store và changelog gắn với application |
| Đọc độc lập | Dùng group khác | Dùng application ID khác |

Không dùng `application.id` mới cho mỗi replica. Nếu mỗi replica dùng ID khác nhau, mỗi replica có thể trở thành một ứng dụng độc lập và đọc toàn bộ dữ liệu thay vì chia tải. Ngược lại, hai topology độc lập không nên dùng chung application ID nếu chúng cần offset và state riêng.

## 10. Scaling và số lượng xử lý song song

Với Kafka Binder thông thường, mức song song bị giới hạn bởi số partition và số consumer trong group. Nếu topic có sáu partition và group có ba consumer, mỗi consumer có thể được gán nhiều partition. Nếu có mười consumer, một số consumer có thể không được gán partition.

Với Kafka Streams, Kafka chia topology thành task dựa trên partition của source topic. Mỗi instance có thể chạy nhiều stream thread; task được phân phối giữa các thread và instance. Số stream thread không tạo thêm partition. Mức song song vẫn phụ thuộc partition topology và các bước repartition.

Khi scale Kafka Streams application:

1. Giữ nguyên `application.id` giữa các replica của cùng topology.
2. Tăng hoặc giảm số instance/stream thread theo năng lực CPU và I/O.
3. Kiểm tra partition count của source và repartition topics.
4. Theo dõi rebalance, task assignment và state restoration.
5. Đánh giá local state store và thời gian restore khi task chuyển instance.

Thêm instance không luôn tăng throughput nếu số partition ít, một key quá nóng hoặc state store bị giới hạn I/O. Nếu cần tăng song song, có thể phải thiết kế lại partition key và topology, nhưng thay đổi partition count cũng có thể ảnh hưởng thứ tự và phân phối dữ liệu.

## 11. Serde và MessageConverter không giống nhau

Kafka Binder thông thường thường dùng message conversion của Spring để chuyển payload giữa byte/message và kiểu Java. Content type như `application/json` giúp framework chọn converter.

Kafka Streams dùng Kafka `Serde` (serializer/deserializer) cho key và value của record trong topology. Serde phải được xác định phù hợp với từng kiểu dữ liệu và phép toán. Việc khai báo `content-type: application/json` trên binding không tự thay thế Serde của Kafka Streams.

| Thành phần | Vai trò |
|---|---|
| Spring MessageConverter | Chuyển payload của message Spring, ví dụ JSON sang DTO |
| Kafka Serializer/Deserializer | Chuyển key/value Kafka thành bytes và ngược lại |
| Kafka Streams `Serde<T>` | Kết hợp serializer và deserializer cho kiểu `T` trong topology |

Với String, có thể dùng `Serdes.String()`. Với JSON, Avro hoặc Protobuf, cần cấu hình Serde tương ứng, schema registry nếu dùng và chính sách tương thích schema. Nếu key hoặc value bị deserialize sai, lỗi thường xuất hiện khi Kafka Streams xử lý topology hoặc khôi phục state.

## 12. Delivery semantics và transaction

Kafka Binder thông thường có các tùy chọn producer transaction, acknowledgement, offset commit và error handling theo Spring Kafka/Kafka binder. Cách cấu hình cụ thể phụ thuộc phiên bản và loại binding. Kafka Streams có cấu hình processing guarantee của Kafka Streams, ví dụ `at_least_once` hoặc `exactly_once_v2` ở các phiên bản Kafka hỗ trợ.

Với Kafka Streams, `exactly_once_v2` có thể phối hợp việc đọc offset, xử lý topology và ghi output/state changelog trong phạm vi transaction Kafka. Nó không tự bao trùm một database bên ngoài, HTTP API hoặc email provider. Nếu function gọi hệ thống ngoài, cần idempotency, outbox hoặc saga phù hợp.

Ví dụ khai báo processing guarantee trong Kafka Streams Binder:

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              processing.guarantee: exactly_once_v2
```

Chỉ bật chế độ này khi broker và phiên bản Kafka Streams hỗ trợ, cluster đã cấu hình transaction phù hợp và ứng dụng chấp nhận chi phí vận hành tương ứng. Hãy kiểm thử failover, transaction timeout và phục hồi state trên môi trường tương thích với production.

Với Kafka Binder thông thường, producer transaction và cơ chế commit offset cũng có phạm vi riêng. Không nên diễn giải `send()` thành bằng chứng consumer đã xử lý thành công hoặc cho rằng mọi tác động ngoài Kafka đều exactly-once.

Trong cả hai mô hình, consumer/processor cần tính đến restart, rebalance, retry, duplicate và poison message. Hãy chọn delivery semantics dựa trên yêu cầu nghiệp vụ và kiểm thử với đúng cấu hình broker.

## 13. Error handling và DLQ

Kafka Binder thông thường hỗ trợ cấu hình consumer retry và dead-letter topic thông qua các thuộc tính của Kafka binder, ví dụ `enableDlq` và tên DLQ trong các phiên bản hỗ trợ. Khi handler message thất bại, framework có thể retry rồi chuyển message lỗi sang DLQ theo cấu hình.

Kafka Streams xử lý lỗi trong topology và có các cơ chế riêng cho deserialization, production, processing và uncaught exception. Không nên giả định cấu hình DLQ của Kafka Binder thông thường tự động áp dụng cho Kafka Streams Binder. Với Kafka Streams, cần xem xét `DeserializationExceptionHandler`, `ProductionExceptionHandler`, `StreamsUncaughtExceptionHandler` hoặc cơ chế error handling mà phiên bản binder/Kafka Streams hỗ trợ.

Một số loại lỗi cần được phân biệt:

- Lỗi deserialize: bytes không thể chuyển thành key/value theo Serde.
- Lỗi xử lý: exception trong operator hoặc user function.
- Lỗi publish: broker từ chối hoặc producer không gửi được output.
- Lỗi state store: local state hoặc changelog không thể khôi phục/ghi.
- Lỗi nghiệp vụ: dữ liệu hợp lệ về cấu trúc nhưng không thỏa quy tắc nghiệp vụ.

DLQ là một phần của chiến lược xử lý lỗi, không thay thế việc xác định loại lỗi và cách replay. Cần lưu event ID, source topic, partition, offset và exception metadata khi có thể để điều tra.

## 14. Cấu hình nào thuộc binder nào?

Hai binder có namespace cấu hình riêng. Trộn nhầm các thuộc tính là nguyên nhân thường gặp khiến ứng dụng khởi động nhưng hành vi không như mong muốn.

| Cấu hình | Kafka Binder thông thường | Kafka Streams Binder |
|---|---|---|
| Broker | `spring.cloud.stream.kafka.binder.brokers` | `spring.cloud.stream.kafka.streams.binder.brokers` |
| Consumer identity | `spring.cloud.stream.bindings.<name>.group` | `spring.cloud.stream.kafka.streams.binder.applicationId` |
| Producer/consumer options | `spring.cloud.stream.kafka.bindings.<name>...` | `spring.cloud.stream.kafka.streams.bindings.<name>...` và Kafka Streams configuration |
| Key/value conversion | Spring message conversion và Kafka serializer/deserializer | Kafka Streams Serde |
| Runtime processing config | Spring Kafka listener/producer properties | `spring.cloud.stream.kafka.streams.binder.configuration` |

Ví dụ, `spring.cloud.stream.kafka.binder.brokers` cấu hình Kafka Binder thông thường. Nó không thay thế cấu hình broker cho Kafka Streams Binder. Khi ứng dụng dùng cả hai binder, cần chỉ định binder phù hợp cho binding hoặc function và tránh cấu hình mặc định mơ hồ.

Tên thuộc tính và khả năng cấu hình chi tiết có thể thay đổi giữa các release train. Hãy dùng cấu hình tương ứng với phiên bản Spring Cloud Stream, Spring Kafka và Kafka Streams đang chạy; không sao chép thuộc tính của binder này sang binder kia.

## 15. Khi nào nên chọn Kafka Binder thông thường?

Chọn Kafka Binder thông thường khi:

- Mỗi message là một yêu cầu hoặc sự kiện nghiệp vụ độc lập.
- Function nhận DTO Java, kiểm tra nghiệp vụ, gọi database/API rồi phát output.
- Cần tích hợp Kafka với các hệ thống message khác qua mô hình binding.
- State được quản lý trong database hoặc dịch vụ lưu trữ riêng.
- Không cần Kafka Streams DSL cho join, window hoặc stateful aggregation.
- Muốn dùng Spring Kafka listener, producer và cơ chế message handling quen thuộc.

Ví dụ: nhận `PaymentRequested`, gọi payment service, lưu kết quả và phát `PaymentAuthorized`. Đây là một message workflow; Kafka Binder thông thường thường là lựa chọn tự nhiên.

## 16. Khi nào nên chọn Kafka Streams Binder?

Chọn Kafka Streams Binder khi:

- Cần join nhiều topic theo key hoặc theo cửa sổ thời gian.
- Cần aggregate sự kiện liên tục, ví dụ tổng đơn hàng theo khách hàng mỗi 5 phút.
- Cần KTable/GlobalKTable để tra cứu hoặc duy trì trạng thái theo key.
- Cần state store cục bộ có changelog và phục hồi theo topology.
- Cần xử lý event time, window, late-arriving records hoặc repartition.
- Logic phù hợp với Kafka Streams DSL và có thể được biểu diễn thành topology.

Ví dụ: kết hợp `orders` và `customers`, tính tổng giá trị đơn hàng theo khách hàng, rồi phát `customer-sales-summary`. Kafka Streams Binder cung cấp abstraction và runtime phù hợp hơn việc tự viết stateful consumer bằng listener thông thường.

## 17. Kiểm thử hai binder

Hai binder cần bộ kiểm thử khác nhau vì runtime và semantics khác nhau.

| Loại kiểm thử | Kafka Binder thông thường | Kafka Streams Binder |
|---|---|---|
| Unit test logic | Gọi function/consumer với DTO | Kiểm thử các phép biến đổi hoặc topology logic |
| Test binding | Spring Cloud Stream Test Binder hoặc broker test | Kiểm tra function binding và topology với cấu hình Streams |
| Test broker | Topic, group, offset, retry, DLQ | Topic, application ID, task assignment, state store, changelog |
| Test phục hồi | Consumer restart, rebalance và redelivery | Task migration, state restoration và rebalance |
| Test serialization | MessageConverter và Kafka serializer/deserializer | Serde cho key/value, state store và changelog |
| Test delivery guarantee | Ack/commit/producer transaction theo cấu hình | `processing.guarantee` và transaction Kafka Streams |

Với Kafka Streams, `TopologyTestDriver` hữu ích để kiểm tra topology trong môi trường test mà không cần broker. Tuy nhiên, nó không thay thế integration test với Kafka thật khi cần xác minh partition assignment, transaction, changelog restore hoặc rebalance.

Với Kafka Binder thông thường, test binder giúp kiểm tra function binding và message flow; integration test với broker phù hợp mới xác nhận consumer group, offset, retry/DLQ và producer configuration.

## 18. Các lỗi chọn nhầm binder thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Function nhận DTO nhưng ứng dụng mong `KStream` | Đang dùng Kafka Binder thông thường | Chọn Kafka Streams Binder và dependency phù hợp |
| `KStream` không được tạo binding như mong muốn | Function definition hoặc Kafka Streams Binder chưa được cấu hình | Kiểm tra binder, function signature và binding names |
| Kafka Streams báo lỗi Serde | Key/value Serde không tương thích với dữ liệu | Cấu hình Serde đúng cho input, output và stateful operator |
| Hai replica cùng xử lý toàn bộ topic | `application.id` khác nhau giữa replica | Dùng cùng application ID cho cùng một topology logic |
| Hai topology độc lập chia sẻ offset/state | Dùng chung `application.id` không đúng ý định | Cấp application ID riêng cho từng ứng dụng logic |
| Topic/changelog/repartition tăng ngoài dự kiến | Topology hoặc stateful operation tạo tài nguyên nội bộ | Kiểm tra topology, naming, retention và cleanup policy |
| Không thấy DLQ theo cấu hình Kafka Binder | Đang dùng Kafka Streams Binder hoặc cấu hình sai namespace | Dùng error handling phù hợp với Kafka Streams |
| State restore lâu sau restart | State store lớn hoặc changelog restore chậm | Theo dõi restore, tối ưu state và hạ tầng broker |
| `content-type` không sửa được lỗi deserialize | Đang xử lý bằng Kafka Streams Serde | Cấu hình Serde thay vì chỉ thay MessageConverter |

## 19. Có thể dùng cả hai binder trong một hệ thống không?

Một hệ thống có thể có dịch vụ dùng Kafka Binder thông thường và dịch vụ khác dùng Kafka Streams Binder. Mỗi dịch vụ chọn mô hình phù hợp với yêu cầu xử lý. Trong một ứng dụng Spring Cloud Stream có nhiều binder, framework hỗ trợ cơ chế multiple binders, nhưng cần cấu hình rõ binder cho từng binding và kiểm tra function nào được liên kết với binder nào.

Không nên thêm cả hai starter chỉ vì muốn “có đầy đủ tính năng”. Mỗi runtime mang theo cấu hình, lifecycle, dependency và semantics riêng. Nếu một service chỉ nhận một message rồi gọi API, Kafka Binder thông thường thường đơn giản hơn. Nếu service cần stateful stream topology, Kafka Streams Binder mới cung cấp abstraction cần thiết.

Một kiến trúc thường gặp là:

```text
Order service
  Kafka Binder thông thường
       |
       v
orders.events topic
       |
       v
Analytics service
  Kafka Streams Binder
       |
       +--> join / window / aggregate
       |
       v
sales.summary topic
       |
       v
Reporting service
  Kafka Binder thông thường
```

Các dịch vụ dùng chung Kafka nhưng mỗi dịch vụ chọn runtime theo loại công việc.

## 20. Quy trình lựa chọn và triển khai

Khi bắt đầu một luồng xử lý Kafka trong Spring Cloud Stream:

1. Xác định bài toán là xử lý từng message hay xử lý topology của một luồng dữ liệu.
2. Nếu chỉ cần nhận DTO, áp dụng nghiệp vụ và phát output, cân nhắc Kafka Binder thông thường.
3. Nếu cần join, window, aggregation hoặc state store gắn với Kafka topology, cân nhắc Kafka Streams Binder.
4. Chọn dependency/starter đúng với binder; không dựa vào tên function để suy ra runtime.
5. Cấu hình broker trong namespace của binder tương ứng.
6. Với Kafka Binder, cấu hình destination, group, content type, producer/consumer và error handling.
7. Với Kafka Streams Binder, cấu hình `application.id`, Serde, topology và state store.
8. Xác định partition key, partition count, concurrency hoặc stream threads phù hợp.
9. Thiết kế delivery semantics, retry, DLQ và idempotency cho cả hai mô hình.
10. Kiểm thử logic, binding, serialization, restart, rebalance và broker thật.
11. Theo dõi consumer lag hoặc Streams task/state restoration theo runtime.

## 21. Tự kiểm tra

- [ ] Giải thích được Kafka Binder thông thường dùng Spring Kafka để gửi/nhận message.
- [ ] Giải thích được Kafka Streams Binder dùng Kafka Streams DSL để xây dựng topology.
- [ ] Phân biệt `Function<OrderEvent, Result>` với `Function<KStream<K,V>, KStream<K2,V2>>`.
- [ ] Phân biệt `group` với `application.id`.
- [ ] Mô tả được vai trò của `KStream`, `KTable` và `GlobalKTable`.
- [ ] Giải thích được state store, changelog và repartition topic.
- [ ] Phân biệt MessageConverter với Kafka Streams Serde.
- [ ] Hiểu cách scaling consumer group khác với scaling Kafka Streams tasks.
- [ ] Biết phạm vi của Kafka Streams exactly-once và giới hạn với hệ thống ngoài Kafka.
- [ ] Chọn được binder phù hợp cho message workflow và stateful stream processing.
- [ ] Thiết kế được kiểm thử và monitoring riêng cho từng runtime.

## Kết luận

Kafka Binder thông thường dùng Spring Kafka để gửi và nhận message theo binding, phù hợp với function xử lý payload Java, consumer group và các workflow nghiệp vụ. Kafka Streams Binder dùng Kafka Streams DSL với `KStream`, `KTable`, state store, join, window và aggregation để xây dựng topology xử lý luồng có trạng thái. Hai binder khác nhau về function signature, runtime, cấu hình broker, identity, Serde, scaling và delivery semantics. Hãy chọn Kafka Binder cho xử lý message thông thường; chọn Kafka Streams Binder khi bài toán cần các phép toán stream và state gắn với Kafka topology. Cả hai vẫn cần thiết kế idempotency, error handling, kiểm thử broker và quan sát vận hành phù hợp.
