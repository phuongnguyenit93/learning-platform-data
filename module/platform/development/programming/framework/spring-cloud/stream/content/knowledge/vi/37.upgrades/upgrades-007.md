# Kiểm tra tình trạng hỗ trợ Reactive Kafka Binder và lựa chọn thay thế

**Reactive Kafka Binder** từng là thành phần Spring Cloud Stream kết nối các function dùng `Flux`/`Mono` với Apache Kafka thông qua **Reactor Kafka**. Nó sử dụng API reactive ở cả phía nhận và phát message, có khả năng backpressure xuyên qua chuỗi reactive. Tuy nhiên, trạng thái hỗ trợ của thành phần này đã thay đổi và không nên tiếp tục xem nó là lựa chọn mặc định cho dự án mới.

**Kết luận theo tài liệu chính thức được đối chiếu ngày 24/11/2026:** Spring Cloud Stream đánh dấu `spring-cloud-stream-binder-kafka-reactive` **deprecated từ phiên bản 4.3.0**, dự kiến **loại bỏ trong một release tương lai**. Tài liệu **Spring Cloud Stream 5.1.0** vẫn ghi trạng thái deprecated/planned for removal, **không** công bố rằng mọi phiên bản đều đã loại bỏ nó. Spring công bố ngày **20/05/2025** rằng Reactor Kafka sẽ ngừng được phát triển về sau, dòng 1.3 là dòng minor cuối; thông báo phát hành **Spring Cloud 2026.0.0 ngày 20/11/2026** tiếp tục ghi nhận deprecation của Reactive Kafka Binder.

Do đó, với ứng dụng hiện hữu, cần kiểm tra version và API đang dùng, xác định yêu cầu về backpressure, offset, retry/DLQ rồi chọn giải pháp được duy trì. **Lựa chọn được Spring Cloud Stream hướng dẫn** là Kafka binder thông thường kết hợp các kiểu reactive khi phù hợp, nhưng ứng dụng phải tự thiết kế các khía cạnh reactive nâng cao. Nếu mục tiêu là stateful processing với join/window/state store, cân nhắc Kafka Streams binder; nếu cần kiểm soát Kafka consumer/ack rất chi tiết, cân nhắc Spring for Apache Kafka.

Bài học thuộc chương **Nâng cấp** của module **SPRING_CLOUD_STREAM**. Mục tiêu là ra quyết định migration dựa trên bằng chứng thay vì chỉ xóa một dependency hoặc đổi một chữ `reactive` trong tên binder.

## 1. Vì sao cần đánh giá tình trạng hỗ trợ?

Các tài liệu cũ từng giới thiệu Reactive Kafka Binder như cách đạt reactive processing đầu-cuối trên Kafka. Một số trang hiện tại vẫn giữ lại đoạn mô tả lịch sử này và các ví dụ `KafkaReceiver`/`KafkaSender`. Tuy nhiên, cảnh báo ở đầu trang Spring Cloud Stream hiện hành cho biết thành phần đã deprecated.

Phải phân biệt:

| Thuật ngữ | Ý nghĩa |
|---|---|
| Supported | Có trong phạm vi hỗ trợ của một dòng phiên bản và chính sách hỗ trợ tương ứng |
| Deprecated | Không nên xây mới trên API; nhà phát triển có định hướng thay thế/loại bỏ |
| Maintenance discontinued | Không tiếp tục phát triển dài hạn; chỉ có thể còn fix trong thời hạn hỗ trợ đã công bố |
| Removed | Mã/khả năng đã thực sự bị loại khỏi một release cụ thể |
| Artifact tồn tại trên Maven Central | Chỉ chứng minh một bản đã được phát hành; **không** chứng minh hiện còn được khuyến nghị hoặc hỗ trợ |

**Không suy ra “đã bị xóa” chỉ từ từ deprecated; cũng không suy ra “còn an toàn” vì Maven vẫn tải được JAR cũ.** Với dự án production, cần gắn quyết định với đúng release và support policy của tổ chức.

## 2. Dòng thời gian chính thức

| Mốc | Sự kiện | Tác động |
|---|---|---|
| Trước Spring Cloud Stream 4.3 | Có binder reactive riêng dựa trên Reactor Kafka | Có thể gặp trong ứng dụng legacy |
| 20/05/2025 | Spring thông báo Reactor Kafka sẽ ngừng bảo trì trong tương lai; 1.3 là minor cuối | Chuẩn bị rời khỏi dependency cho thiết kế mới |
| Spring Cloud Stream 4.3.0 | Reactive Kafka Binder bị deprecate | Nên lập kế hoạch migration |
| 20/11/2026 | Spring Cloud 2026.0.0 GA; Spring Cloud Stream 5.1.0 và ghi chú deprecation | Khuyến nghị tiếp tục chuyển đổi |
| 24/11/2026 | Tài liệu Spring Cloud Stream 5.1.0 vẫn ghi “deprecated and will be completely removed in a future release” | Không tuyên bố đã loại bỏ hoàn toàn ở 5.1.0 |

Những trang hướng dẫn ví dụ có thể không được biên tập lại toàn bộ sau thông báo deprecation. Ưu tiên cảnh báo hiện hành và release announcement hơn câu “recommended” còn sót trong đoạn mô tả chức năng cũ.

## 3. Phân biệt các thư viện thường bị nhầm

| Công nghệ/artifact | Vai trò | Khi nâng cấp |
|---|---|---|
| `spring-cloud-stream-binder-kafka-reactive` | Binder dùng Reactor Kafka | **Deprecated từ 4.3.0** |
| `reactor-kafka` | Thư viện `KafkaReceiver`, `KafkaSender`, `ReceiverOffset` | Được Spring thông báo ngừng phát triển tương lai |
| `spring-cloud-stream-binder-kafka` | Kafka binder message-channel thông thường | Hướng thay thế chính cho Spring Cloud Stream |
| `spring-cloud-stream-binder-kafka-streams` | Tích hợp Kafka Streams DSL, KStream/KTable | Cho stateful topology, không thay thế một-một |
| `spring-kafka` | `@KafkaListener`, `KafkaTemplate`, listener container | Điều khiển ack/commit/retry chuyên sâu |
| `reactor-core` | API `Flux`, `Mono` và operators | **Không** đồng nghĩa Reactor Kafka; vẫn được dùng rộng rãi |
| `spring-cloud-stream-reactive` | Module reactive đời cũ | Ngừng phân phối từ Spring Cloud Stream 3.0; là artifact **khác** |

Lịch sử có hai thay đổi độc lập: module `spring-cloud-stream-reactive` cũ được thay bởi functional programming model từ 3.0; Reactive Kafka Binder dựa trên Reactor Kafka bị deprecated từ 4.3.0. Đừng nhập hai sự kiện làm một.

## 4. Reactive Kafka Binder từng mang lại gì?

Binder reactive cũ sử dụng `KafkaReceiver` và `KafkaSender` của Reactor Kafka. Nó gắn Kafka vào mô hình demand/backpressure của Reactive Streams.

~~~text
Reactive Kafka Binder (legacy)
Kafka broker
   |
   v
KafkaReceiver -> Flux -> Reactor operators -> KafkaSender
                  |             |
               demand        reactive flow
                  |             |
                  +-- backpressure --+
   |
   v
Kafka broker output
~~~

Function nghiệp vụ có thể đơn giản:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import reactor.core.publisher.Flux;

@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    return input -> input.map(String::toUpperCase);
}
~~~

Cùng chữ ký này **có thể** dùng với Kafka binder thông thường. Nhưng việc một function dùng `Flux` không đủ để bảo đảm cơ chế backpressure đầy đủ qua Kafka client.

## 5. Kafka binder thông thường với Flux khác ở đâu?

~~~text
Regular Kafka Binder + Flux:
Kafka -> Spring Kafka listener -> message channel -> Flux pipeline
                                                -> output channel -> producer
           Poll/dispatch và broker boundary không phải
           Reactor Kafka receiver/sender reactive end-to-end.
~~~

Điều còn giữ được:

- Mô hình hàm `Supplier`, `Function`, `Consumer`.
- Reactor operators như `map`, `filter`, `flatMap`.
- Binding name, destination, group và nhiều cấu hình broker thông thường.
- Spring Cloud Stream test binder để kiểm tra business transformation.

Điều **không** được coi là tương đương tự động:

- Backpressure xuyên Kafka receiver → function → Kafka sender.
- `ReceiverOffset` và cách commit offset của Reactor Kafka.
- `reactiveAutoCommit` và `reactiveAtmostOnce` của binder cũ.
- Listener/binder retry và DLQ hoạt động với reactive function giống imperative function.
- Giới hạn lượng message in-flight, thread scheduling và thứ tự hoàn tất.

Phải thiết kế lại các điểm này khi có yêu cầu về tính đúng hoặc hiệu năng.

## 6. Kiểm kê dependency và các phiên bản

Chốt các thông tin trước khi sửa code:

~~~text
Spring Boot                 <actual version>
Spring Cloud train          <actual version>
Spring Cloud Stream         <actual version>
Reactive Kafka Binder       <actual version, if present>
Reactor Kafka               <actual version, if present>
Reactor BOM                 <actual version>
Spring Kafka                <actual version>
Kafka client / broker       <actual versions>
JDK                         <actual version>
~~~

Lệnh kiểm tra dự án Maven:

~~~bash
mvn dependency:tree

mvn dependency:tree \
  -Dincludes=org.springframework.cloud:spring-cloud-stream-binder-kafka-reactive

mvn dependency:tree \
  -Dincludes=io.projectreactor.kafka:reactor-kafka
~~~

Với dự án Gradle, có thể xem runtime dependency graph bằng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Các lệnh là hướng dẫn để người học tự kiểm kê dự án; không suy ra phiên bản thực tế từ ví dụ này. Phải xem cả dependency trực tiếp và bắc cầu (transitive). Một JAR còn trong local Maven cache vẫn có thể build offline dù phiên bản mục tiêu không còn có dependency management tương ứng.

## 7. Kiểm tra code có dùng API legacy không

Tìm trong code và cấu hình:

~~~text
spring-cloud-stream-binder-kafka-reactive
reactor-kafka
KafkaReceiver
KafkaSender
ReceiverOffset
ReceiverOptionsCustomizer
SenderOptionsCustomizer
reactiveAutoCommit
reactiveAtmostOnce
KafkaHeaders.ACKNOWLEDGMENT
Function<Flux<...>, Flux<...>>
Consumer<Flux<...>>
~~~

Phân loại:

| Dấu hiệu | Ý nghĩa |
|---|---|
| Dependency reactive binder hoặc KafkaReceiver | Có phụ thuộc nền tảng deprecated |
| `Flux`/`Mono` đơn thuần | **Chưa đủ** xác định đang dùng binder reactive |
| `ReceiverOffset` | Logic commit phụ thuộc Reactor Kafka |
| `reactiveAutoCommit` | Có semantics xử lý batch/commit riêng |
| `reactiveAtmostOnce` | Có thể commit trước khi xử lý |
| `ReceiverOptionsCustomizer` | Đã tùy biến receiver ở API cũ |
| `KafkaStreams`/KStream/KTable | Đây là hệ Kafka Streams, không phải Reactor Kafka |

Đặc biệt, không bỏ sót các class thuộc thư viện dùng chung đã import `ReceiverOffset`, dù function chính trông như code Spring Cloud Stream bình thường.

## 8. Đặt câu hỏi theo nhu cầu nghiệp vụ

Trước khi chọn replacement, xác định:

1. Chỉ map/filter event hay cần join/window/aggregate?
2. Có yêu cầu xử lý state nhiều giờ/ngày với changelog và restore không?
3. Có thật sự cần Kafka-level reactive backpressure hay chỉ muốn cú pháp `Flux`?
4. Khi xử lý thành công, offset được commit vào lúc nào?
5. Có thể xử lý trùng event sau crash không?
6. Cần retry/DLT theo từng message hay error strategy trên một pipeline?
7. Có cần thứ tự theo key/partition không?
8. Tải ổn định, burst, độ trễ và giới hạn RAM là bao nhiêu?
9. Có dùng WebClient/reactive database để xử lý bất đồng bộ không?
10. Có hỗ trợ vận hành và tích hợp broker thật cho stack mới không?

Không chọn Kafka Streams chỉ vì tên chứa “Streams”. Đó là topology API khác `Flux`. Cũng không dùng Reactor Kafka trực tiếp làm “giải pháp thay thế” nếu chính Reactor Kafka đang trên lộ trình ngừng bảo trì.

## 9. Bảng lựa chọn thay thế

| Lựa chọn | Nên dùng khi | Điều cần kiểm chứng |
|---|---|---|
| **A. Regular Kafka Binder + imperative Function/Consumer** | Transform, validate, persistence, retry/DLT từng event | Ack sau xử lý, idempotency, lag |
| **B. Regular Kafka Binder + Flux/Mono Function** | Có Reactor operators hữu ích, muốn giữ business pipeline | Error strategy, in-flight bound, ack boundary |
| **C. Kafka Streams Binder** | KStream/KTable, window, join, aggregate, state store | Serde, app ID, internal topic/state migration |
| **D. Spring for Apache Kafka** | Cần kiểm soát consumer container, ack/rebalance/batch sâu | Manual ack, error handler, config cụ thể |

**A** là ứng viên ban đầu phù hợp cho phần lớn event processing imperative. **B** giảm sửa code khi có nhiều Reactor transformation nhưng không thể tự nhận là fully reactive broker stack. **C** và **D** giải quyết những nhu cầu chuyên biệt. Chọn theo tính đúng và SLO, không chỉ độ ít dòng code.

## 10. Phương án A: thay dependency, giữ functional model

Maven với Kafka binder thông thường:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-stream-binder-kafka</artifactId>
</dependency>
~~~

Không thêm lại artifact `spring-cloud-stream-binder-kafka-reactive` chỉ để giữ API cũ. Dùng Spring Cloud BOM tương thích với Spring Boot; không tự ghim các version xung đột.

Ví dụ function nhận từng event:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    public record OrderCreated(String eventId, String orderId) {}

    public record OrderValidated(
        String eventId,
        String orderId,
        boolean valid
    ) {}

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return event -> new OrderValidated(
            event.eventId(),
            event.orderId(),
            event.orderId() != null && !event.orderId().isBlank()
        );
    }
}
~~~

Binding:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder

    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validator-v2
          content-type: application/json
          consumer:
            max-attempts: 3

        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json

      kafka:
        binder:
          brokers: ${KAFKA_BROKERS:localhost:9092}
~~~

`max-attempts` là generic retry property cho imperative consumer message handler theo chính sách binder. Nếu logic có database side effect, yêu cầu xử lý trùng lặp và retry phải được thiết kế chi tiết thay vì chỉ trả ra DTO.

## 11. Phương án B: giữ Flux bên trong regular Kafka binder

Spring Cloud Function hỗ trợ `Function<Flux<T>, Flux<R>>` cùng regular binder:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;

@Configuration
public class ReactiveTransformFunctions {

    @Bean
    Function<Flux<String>, Flux<String>> uppercase() {
        return input -> input
            .filter(value -> !value.isBlank())
            .map(String::toUpperCase);
    }
}
~~~

Cấu hình input/output:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase

    stream:
      bindings:
        uppercase-in-0:
          destination: text.input
          group: uppercase-v2

        uppercase-out-0:
          destination: text.output

      kafka:
        binder:
          brokers: ${KAFKA_BROKERS:localhost:9092}
~~~

Cảnh báo vận hành:

- Reactive pipeline hoạt động ở tầng function, không phải `KafkaReceiver`/`KafkaSender` xuyên broker.
- Không có automatic Kafka demand/backpressure tương đương binder cũ.
- Bộ đệm nội bộ và số tác vụ đồng thời phải giới hạn; đo heap, p99, lag.
- Nếu một operator ném exception không được xử lý, pipeline có thể terminate.
- Generic binder retry/DLQ của message handler imperative không tự trở thành retry theo từng element.
- Không xem việc function trả Publisher là xác nhận đã commit output/side effect.

Nếu chỉ dùng `map`/`filter` đơn giản, một imperative Function thường dễ xác minh retry và ack hơn.

## 12. Error handling của reactive function khác imperative

Trong imperative function, Spring Cloud Stream gọi handler theo từng message, nên binder có cơ hội bao bọc từng invocation bằng retry/error handling.

Trong reactive function, framework thường gọi function một lần để nối các publisher; nhiều message sau đó đi qua cùng pipeline. Vì vậy các `maxAttempts`, retry template và DLT behavior của imperative handler không thể áp dụng mặc định theo cùng cách.

~~~text
Imperative:
message1 -> function invocation -> success/exception
message2 -> function invocation -> success/exception

Reactive:
publisher -> function xây dựng pipeline -> subscriber
                   N message dùng chung pipeline
~~~

Các lỗi cần tránh:

- `retryWhen` ở cuối toàn stream có thể resubscribe ngoài phạm vi một record.
- `onErrorResume(error -> Mono.empty())` có thể biến record lỗi thành record bị bỏ qua.
- `onErrorContinue` không phải một chiến lược DLQ có thể quan sát, recover hoặc audit.
- `flatMap` song song có thể làm thay đổi thứ tự hoàn thành.
- Buffer vô hạn có thể làm đầy heap thay vì đẩy backpressure về broker.

Nếu cần xử lý lỗi theo từng message, chọn giải pháp hỗ trợ per-message ack/retry/DLT, hoặc xây dựng error path Reactor có kiểm soát đầy đủ và kiểm thử khi broker/downstream lỗi.

## 13. Reactive Consumer và subscription

Với `Consumer<Flux<T>>`, return type là void nên framework không có Publisher kết quả để tự subscribe theo một số trường hợp. Ví dụ này **không kích hoạt** pipeline:

~~~java
@Bean
Consumer<Flux<String>> brokenConsumer() {
    return input -> input
        .map(String::toUpperCase)
        .doOnNext(System.out::println);
}
~~~

Nếu dùng reactive Consumer tường minh, cần subscription chủ động:

~~~java
@Bean
Consumer<Flux<String>> loggingConsumer() {
    return input -> input
        .map(String::toUpperCase)
        .doOnNext(System.out::println)
        .subscribe();
}
~~~

Nhưng `subscribe()` một mình **không** xác định ack, retry, resource disposal và shutdown. Phải quản lý lifetime và error handler. Spring Cloud Stream cũng mô tả cách dùng `Function<Flux<T>, Mono<Void>>` ở một số trường hợp để framework thấy Publisher kết quả; với nghiệp vụ đòi hỏi ack sau mỗi database commit, một imperative Consumer thường rõ nghĩa hơn.

## 14. Phương án C: Kafka Streams binder

Nếu yêu cầu join, window, aggregation, KTable hoặc stateful topology, đánh giá Kafka Streams binder:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
~~~

Ví dụ API:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;

@Bean
Function<KStream<String, String>, KStream<String, String>>
        normalizeOrders() {
    return stream -> stream.mapValues(
        value -> value == null ? null : value.trim()
    );
}
~~~

Đây không phải thay thế 1:1 của `Function<Flux,Flux>`. Khi áp dụng Kafka Streams, cần:

- `application.id` ổn định.
- Group/task assignment và partition topology.
- Serde cho key/value và schema evolution.
- State stores, RocksDB, changelog/repartition topics nếu có state.
- Grace/retention của window và khả năng restore sau restart.
- Kế hoạch upgrade/reset state nếu đổi topology hay application ID.

Chọn Kafka Streams vì khả năng xử lý state theo thời gian, không chỉ vì tên có “Streams”.

## 15. Phương án D: Spring for Apache Kafka

Nếu cần kiểm soát listener container/offset/ack sâu, dùng Spring Kafka trực tiếp:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderProcessor processor;

    public OrderListener(OrderProcessor processor) {
        this.processor = processor;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-projection-v2"
    )
    public void receive(
            String payload,
            Acknowledgment acknowledgment) {

        processor.processAndCommit(payload);
        acknowledgment.acknowledge();
    }
}
~~~

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BROKERS:localhost:9092}
    listener:
      ack-mode: manual
    consumer:
      auto-offset-reset: earliest
~~~

Giả định `OrderProcessor.processAndCommit` là phương thức nghiệp vụ chỉ return sau khi đã commit side effect bền vững. `Acknowledgment` cần listener container ở manual ack mode. Cấu hình `DefaultErrorHandler`, DLT và backoff nếu cần; đừng tự nuốt lỗi rồi ack.

Điểm yếu là code ràng buộc trực tiếp Spring Kafka nhiều hơn, nhưng đổi lại kiểm soát được những cơ chế mà migration cần xác minh. Nếu dùng WebClient/Mono bất đồng bộ, không ack trước khi Mono hoàn thành thành công.

## 16. ReceiverOffset cũ không bằng Acknowledgment mới

Legacy Reactive Kafka Binder từ 4.0.2 mô tả header `KafkaHeaders.ACKNOWLEDGMENT` có kiểu Reactor Kafka `ReceiverOffset`. Trong regular Kafka binder với manual ack, phần tương ứng là `org.springframework.kafka.support.Acknowledgment`.

| Khía cạnh | Reactive binder cũ | Regular binder |
|---|---|---|
| Consumer foundation | Reactor Kafka `KafkaReceiver` | Spring Kafka listener container |
| Ack object | `ReceiverOffset` | `Acknowledgment` |
| Reactive auto-commit options | `reactiveAutoCommit`, `reactiveAtmostOnce` | Không có mapping trực tiếp |
| Xử lý lỗi | Reactor pipeline và option riêng | Imperative listener/binder error handler hoặc Reactor theo function |
| Mốc commit | Theo ReceiverOffset/option cũ | Theo listener ack mode và error handling |

Không chỉ sửa import mà giữ nguyên logic. Cùng tên header có thể mang object và semantics khác. Phải định nghĩa chính xác “đã xử lý thành công” so với thời điểm commit offset.

## 17. Hai lựa chọn commit reactive legacy cần kiểm toán

Theo tài liệu legacy:

- `reactiveAtmostOnce=true`: commit trước khi xử lý record, chấp nhận rủi ro mất record khi xảy ra lỗi.
- `reactiveAutoCommit=true`: xử lý theo Reactor Kafka auto commit batch semantics, có thể dùng `Flux<Flux<ConsumerRecord<...>>>` và native deserializer.
- Tài liệu ghi nhận `reactiveAutoCommit` trong bản 4.0.2 từng có implementation chưa đúng, gần giống at-most-once; behavior thay đổi ở các bản sau.
- Trong các auto-commit mode này, header manual acknowledgment có thể không hiện diện.

Hãy rà soát giá trị option thực tế trong YAML và test các trường hợp:

1. Consumer crash trước xử lý.
2. Database commit thành công, nhưng offset chưa commit.
3. Offset đã commit, nhưng side effect chưa durable.
4. Broker output trả lỗi.
5. Poison record trong một batch.
6. Retry xảy ra sau rebalance.

Đổi binder có thể làm giảm data loss hoặc tạo thêm duplicate tùy mốc commit mới. Đây là thay đổi semantics, không phải rename API.

## 18. Retry và DLT khi chuyển sang imperative binder

Ví dụ generic retry kết hợp Kafka DLT:

~~~yaml
spring:
  cloud:
    function:
      definition: storeOrder

    stream:
      bindings:
        storeOrder-in-0:
          destination: orders.created
          group: order-projection-v2
          consumer:
            max-attempts: 3

      kafka:
        bindings:
          storeOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.dlt
~~~

Ví dụ giả định topic/ACL/Serde cần thiết đã được cấu hình, và `storeOrder` là imperative message handler. Hãy thử lỗi deserialize, lỗi business và lỗi publish DLT riêng vì chúng có đường xử lý khác nhau.

Nếu giữ reactive function, không suy luận `max-attempts` ở trên tự retry từng element. Reactor `retryWhen`/error operators cần đặt ở tầng phù hợp, bảo đảm không bỏ record âm thầm hoặc retry vô hạn.

## 19. Kiểm soát in-flight/backpressure sau migration

Khi bỏ reactive Kafka client, phải kiểm soát tải ở nhiều tầng:

| Ranh giới | Thông số/cơ chế | Số đo |
|---|---|---|
| Kafka → consumer | Partition, concurrency, `max.poll.records` | Lag per partition, poll latency |
| Consumer → business | Bounded queue, executor, semaphore | In-flight, queue depth, reject |
| Business → DB/API | Connection pool, timeout, rate limit | p95/p99, waiting, errors |
| Function → producer | Batch, acks, buffer memory | Send latency, error rate |
| Downstream overload | Pause/resume consumer, backoff | Lag, recovery, rebalance |

Tránh để `flatMap` chạy với concurrency lớn hơn tài nguyên downstream có thể đáp ứng. `onBackpressureBuffer` không giới hạn có thể chỉ chuyển backlog từ Kafka sang heap JVM, không phải giải pháp bảo đảm backpressure đầu-cuối.

Nếu một record cần giữ ordering theo `orderId`, kiểm tra partition key và thứ tự xử lý khi dùng concurrency hoặc Reactor operators song song.

## 20. Migration nên làm theo bốn pha

### Pha A — Kiểm kê

1. Ghi các phiên bản Spring Boot, Cloud, Stream, Reactor Kafka và broker.
2. Xác định cả dependency trực tiếp và transitive.
3. Tìm API ReceiverOffset/customizers/reactive commit flags.
4. Liệt kê input/output topics, group, schema, keys và headers.
5. Ghi lại behavior cũ: when ack/commit, retry/DLT, ordering, throughput.

### Pha B — Prototype

1. Thay dependency trên một nhánh độc lập.
2. Chọn regular Kafka binder và imperative Function hoặc Flux Function theo nhu cầu.
3. Giữ contract đầu vào/ra; tránh thay schema và binder cùng lúc.
4. Viết test happy path và error path với Testcontainers Kafka.
5. Đo lag, throughput, p99, heap, retry và DLT.

### Pha C — Shadow comparison

1. Dùng consumer group **khác** nếu cần hai app nhận cùng input.
2. Cô lập output của app shadow hoặc chạy dry-run để tránh side effect kép.
3. Ghi lại chênh lệch theo event ID.
4. Test restart, rebalance, broker timeout và downstream chậm.
5. Xác định offset cutover point và dữ liệu cần replay/backfill.

### Pha D — Cutover/rollback

1. Dừng/drain app cũ theo cách hỗ trợ.
2. Xác minh committed offset tương ứng side effect durable.
3. Khởi động app mới với group và initial offset đã quyết định.
4. Theo dõi end-to-end success, duplicate, retry, DLT, lag.
5. Có rollback plan và event deduplication để chịu được reprocessing.

Không chạy hai app trong **cùng consumer group** rồi mong cả hai nhận đủ mọi record; Kafka phân chia partition cho các member trong group đó.

## 21. Offset và group: rủi ro khi chuyển

Nếu giữ group ID của ứng dụng cũ, ứng dụng mới có thể tiếp tục từ committed offset hiện tại, nhưng điều đó chỉ đúng với ý nghĩa “không bỏ qua công việc” nếu offset cũ phản ánh các side effect đã thành công.

Nếu tạo group mới, `auto.offset.reset` chỉ áp dụng khi chưa có offset commit hợp lệ; `earliest` có thể replay, `latest` có thể bỏ qua lịch sử.

| Cutover | Lợi ích | Rủi ro |
|---|---|---|
| Giữ group | Tiếp tục từ offset đã commit | Mốc commit cũ có thể đi trước side effect |
| Group mới từ earliest | Soát lại lịch sử | Duplicate và output lặp |
| Group mới từ latest | Không replay phần cũ | Mất sự kiện xảy ra trước subscription |
| Hai group song song | So sánh độc lập | Phải cô lập sink và chi phí gấp đôi |
| Cùng group chạy đồng thời | Kafka tự chia tải | Không phải shadow/mirror dữ liệu |

Không reset offset production chỉ để “thử lại” nếu chưa có backup, data reconciliation và kế hoạch deduplication.

## 22. Integration test với broker thật

Test binder trong JVM dùng để kiểm tra function transformation, không mô phỏng đầy đủ Kafka commit/rebalance/producer acknowledgments. Với migration liên quan Reactor Kafka, phải kiểm thử trên Kafka broker thật.

| Kịch bản | Kỳ vọng |
|---|---|
| 100 event hợp lệ | 100 output/side effect theo contract |
| Một poison record ở giữa | Không mất các record sau; DLT/retry đúng |
| DB lỗi tạm thời | Retry có giới hạn; không ack sớm |
| DB commit rồi JVM crash | Có redelivery; idempotency ngăn duplicate effect |
| Broker output lỗi | Không cam kết input thành công khi sink chưa durable |
| Rebalance khi tải cao | Không bỏ quên offset và không làm gián đoạn vô hạn |
| Downstream chậm | In-flight/buffer có giới hạn; lag có thể đo |
| Restart với group cũ | Tiếp tục theo offset thực |
| Shadow group | Không gửi output lặp vào production sink |
| DLT publish lỗi | Có hành vi recovery được test, không âm thầm drop |

Mỗi record nên có `eventId` để đối soát input, output, pending, duplicate, retry, DLT. Không chỉ test “Spring context started”.

## 23. Đo hiệu năng trước và sau

Bộ chỉ số tối thiểu:

- Số event nghiệp vụ được xử lý **thành công** mỗi giây.
- p50/p95/p99 end-to-end latency, bao gồm thời gian ở broker.
- Consumer lag theo partition.
- CPU, heap, GC pause và memory của queue/buffer.
- Concurrent downstream requests/connection pool waiting.
- Retry, redelivery, DLT và error ratio.
- Producer send/ack latency.
- Rebalance count và thời gian phục hồi.
- Chi phí/triệu event hợp lệ.

Regular binder với `Flux` có thể có throughput tốt trong một benchmark, nhưng vẫn cần test burst/slow downstream để phát hiện việc mất backpressure gây tăng RAM hoặc p99. Không dùng số lượng thread thấp làm bằng chứng non-blocking end-to-end.

## 24. Các sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Cho rằng binder đã bị xóa khỏi mọi bản | Sai với ngôn ngữ deprecation của tài liệu 5.1.0 | Ghi rõ phiên bản và ngày kiểm tra |
| Tiếp tục dùng cho dự án mới | Đặt dự án trên thành phần không còn hướng phát triển dài hạn | Dùng binder thường hoặc stack phù hợp |
| Thấy Flux là coi fully reactive | Không có end-to-end backpressure với regular binder | Đo ranh giới broker và giới hạn in-flight |
| Đổi ReceiverOffset thành Acknowledgment máy móc | Ack timing khác | Thiết kế lại commit/side-effect boundary |
| Chỉ thay dependency rồi build | Bỏ sót retry, DLT, ordering, schema | Contract test và failure injection |
| Reactive function không retry từng record | Binder handler retry chỉ dành cho imperative | Reactor error strategy hoặc imperative Function |
| Consumer<Flux> không subscribe | Pipeline không xử lý | Quản lý subscription hoặc đổi kiểu function |
| Chạy shadow cùng group | Hai app chia partition | Group riêng, cô lập output |
| Tăng concurrency vô hạn | Downstream/heap quá tải | Giới hạn theo pool/partition |
| Dùng Kafka Streams vì tên giống | Sai abstraction, có state/app ID riêng | Chọn theo yêu cầu topology |
| Tăng throughput bằng ack sớm | Có thể mất record | Chỉ ack theo successful durable boundary |
| Không dự phòng rollback | Không thể hồi phục nhanh | Cutover/offset/runbook rõ ràng |

## 25. Checklist ra quyết định

| Câu hỏi | Kết quả phải ghi |
|---|---|
| Đúng release Spring Cloud/Stream nào? | Version, BOM và link changelog |
| Có binder reactive trên classpath? | Dependency tree |
| Dùng Reactor Kafka trực tiếp không? | KafkaReceiver/KafkaSender/ReceiverOffset |
| Trạng thái support của bản mục tiêu? | Deprecated/removed/support end theo nguồn chính thức |
| Cần backpressure xuyên Kafka thật không? | SLO và test chứng minh |
| Logic có state window/join không? | Kafka Streams phù hợp hay không |
| Có thể dùng imperative per-message handler? | Retry/ack/throughput kiểm chứng |
| Đang dùng reactive commit option nào? | Mô tả lúc commit và rủi ro |
| Có yêu cầu DLQ và idempotency? | Policy và test |
| Group/cutover offset đã quyết định? | Runbook |
| Có shadow test không tạo output kép? | Group/destination riêng |
| Đã thử crash/rebalance/timeout? | Kết quả integration test |
| Có rollback plan không? | Trigger, owner, timeline |

## 26. Bài thực hành

Dự án mẫu đang dùng `spring-cloud-stream-binder-kafka-reactive` với function `Function<Flux<String>,Flux<String>>` đọc `orders.raw`, chuẩn hóa payload và phát `orders.normalized`.

1. Ghi phiên bản framework, Reactor Kafka và Kafka broker.
2. Đọc cảnh báo deprecated từ tài liệu Spring Cloud Stream 5.1.0 và thông báo Spring 2025/2026.
3. Ghi config commit/ack, retry/DLT, group, partition, headers và serializer của bản cũ.
4. Tạo bản thử dùng `spring-cloud-stream-binder-kafka`.
5. Giữ Flux function ở vòng thử đầu, sau đó viết thêm imperative Function.
6. Chạy Testcontainers Kafka; đo output count và dữ liệu đúng.
7. Gây lỗi downstream, poison record, crash trước/sau side effect.
8. Dùng consumer group shadow với output riêng.
9. So sánh lag, throughput, p99, heap, retry và DLT.
10. Chọn phương án dựa trên correctness và SLO; lập cutover/rollback plan.

**Tiêu chí hoàn thành:** giải thích chính xác trạng thái deprecated, phân biệt Flux API với reactive binder nền, chọn đúng phương án thay thế, thiết kế lại ack/retry/DLT và chứng minh việc migration không làm mất dữ liệu hoặc phá ordering đã cam kết.

## 27. Tài liệu tham khảo chính thức

- [Spring Cloud Stream 5.1.0 — Reactive Kafka Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/overview.html) — deprecated từ 4.3.0; removal trong tương lai.
- [Spring Blog — Reactor Kafka Project Will Be Discontinued (20/05/2025)](https://spring.io/blog/2025/05/20/reactor-kafka-discontinued/) — Reactor Kafka 1.3 là minor cuối, lộ trình ngừng maintenance và integration.
- [Spring Cloud 2026.0.0 GA (20/11/2026)](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/) — Spring Cloud Stream 5.1.0 và deprecation note.
- [Spring Cloud Stream — Reactive Kafka Binder Examples](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/examples.html) — backpressure, ReceiverOffset, reactiveAutoCommit.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — functional model, Flux/Mono, reactive Consumer và error handling.
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html) — generic retry/DLQ của imperative handlers.
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html) — consumer/producer settings.
- [Spring Cloud Stream — Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/) — KStream, KTable và topology.
- [Spring for Apache Kafka — @KafkaListener](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html) — annotation consumer.
- [Spring for Apache Kafka — Message Listener Container](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html) — ack modes, offsets.
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html) — phạm vi test binder trong JVM.

