# Spring Cloud Stream và mô hình binder

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của Spring Cloud Stream trong ứng dụng message-driven.
- Phân biệt function, binding, destination, binder và consumer group.
- Dùng Supplier, Function và Consumer để xây dựng source, processor và sink.
- Cấu hình binding, destination, group, content type và binder bằng application.yml.
- Hiểu binder ánh xạ abstraction của framework sang Kafka, RabbitMQ hoặc middleware khác.
- Thiết kế consumer group, partitioning, retry và dead-letter flow.
- Kết nối nhiều binder trong một ứng dụng.
- Kiểm thử function bằng Test Binder và biết khi nào cần broker thật.

Bài này thuộc chủ đề **Spring Framework - messaging**, nhánh **Hệ sinh thái**. Spring Cloud Stream là dự án thuộc hệ sinh thái Spring Cloud, xây dựng trên Spring Boot và sử dụng Spring Integration để kết nối với message broker. Nó bổ sung mô hình lập trình và lớp cấu hình thống nhất cho các ứng dụng message-driven.

## 1. Spring Cloud Stream giải quyết vấn đề gì?

Một ứng dụng messaging thường phải đọc message từ destination, chuyển payload thành kiểu dữ liệu ứng dụng, chạy logic nghiệp vụ, gửi kết quả tới destination khác và quản lý lỗi, retry, concurrency, partition.

Nếu mỗi service tự viết toàn bộ phần kết nối Kafka hoặc RabbitMQ, logic nghiệp vụ dễ bị gắn chặt với API của broker. Việc đổi middleware hoặc chạy cùng logic trên nhiều broker sẽ làm tăng chi phí thay đổi.

Spring Cloud Stream tạo một lớp abstraction ở giữa application code và middleware:

~~~text
Application functions
       |
       v
Spring Cloud Stream bindings
       |
       v
Binder abstraction
       |
       +-------------------+
       |                   |
       v                   v
Kafka binder          Rabbit binder
       |                   |
       v                   v
Kafka topics          Exchanges / queues
~~~

Application code làm việc với message và function. Binding kết nối đầu vào/đầu ra của function với destination. Binder chuyển binding thành consumer hoặc producer cụ thể của middleware.

Nhờ vậy, cùng một function có thể kết nối tới các broker khác nhau thông qua binder tương ứng. Tuy nhiên, abstraction không làm mọi broker có hành vi giống hệt nhau. Partition, acknowledgement, transaction, retry, DLQ, header và native serialization vẫn phụ thuộc binder cùng khả năng của broker.

## 2. Phân biệt các khái niệm cốt lõi

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Function | Logic xử lý message trong ứng dụng | Chuẩn hóa nội dung đơn hàng |
| Binding | Cầu nối giữa input/output của function và middleware | normalize-in-0 |
| Destination | Tên tài nguyên logic trên middleware | Topic orders.raw hoặc exchange orders |
| Binder | Adapter kết nối Spring Cloud Stream với middleware | Kafka binder, Rabbit binder |
| Consumer group | Nhóm consumer cùng chia sẻ công việc của một subscription | order-normalizers |

### 2.1. Function và binding

Function mô tả công việc ứng dụng cần làm. Binding gắn input/output của function với destination. Với function một input và một output tên normalize, binding mặc định là:

- normalize-in-0: input thứ nhất.
- normalize-out-0: output thứ nhất.

Tên binding dùng trong cấu hình Spring Cloud Stream. Nó không nhất thiết trùng tên topic, exchange hoặc queue.

### 2.2. Destination và binder

Destination là tên tài nguyên mà binder ánh xạ tới middleware. Kafka binder thường ánh xạ destination thành Kafka topic. Rabbit binder thường dùng destination làm exchange và tạo queue tương ứng cho consumer group. Cấu trúc vật lý phụ thuộc binder.

Binder là adapter tạo producer hoặc consumer phù hợp, áp dụng cấu hình và chuyển message qua lại. Nó che giấu một phần chi tiết kết nối, không loại bỏ khác biệt nền tảng của broker.

### 2.3. Consumer group

Với cùng destination:

- Các group khác nhau nhận bản sao message độc lập theo publish-subscribe semantics.
- Nhiều instance cùng group chia sẻ message để tăng khả năng xử lý ngang.
- Trong cùng group, một message thường được giao cho một instance theo cơ chế phân phối của broker/binder.

Ví dụ:

~~~text
orders.created
      |
      +---- group billing ----> billing instance 1
      |                     \-> billing instance 2
      |
      +---- group analytics -> analytics instance 1
      |
      +---- group audit -----> audit instance 1
~~~

Billing và analytics là hai group khác nhau nên đều nhận message. Hai billing instance cùng group chia nhau xử lý. Nếu không khai báo group, consumer có thể là anonymous consumer; độ bền và tài nguyên subscription phụ thuộc binder. Với ứng dụng cần nhận message bền vững qua restart, hãy khai báo group có tên và kiểm tra retention/durable subscription của broker.

## 3. Mô hình lập trình hàm

Spring Cloud Stream khuyến nghị mô hình functional từ dòng 3.x. Ứng dụng khai báo bean theo java.util.function và framework kết nối chúng với binding.

| Kiểu | Vai trò | Hướng dữ liệu |
|---|---|---|
| Supplier<T> | Source tạo message | Không có input, tạo output |
| Function<T, R> | Processor | Nhận input, tạo output |
| Consumer<T> | Sink xử lý message | Nhận input, không tạo output |

### 3.1. Supplier: tạo message

Supplier không nhận message đầu vào. Nó tạo dữ liệu để gửi ra output binding. Với Supplier imperative, framework gọi supplier bằng poller; poller mặc định thường chạy mỗi giây và có thể điều chỉnh.

~~~java
@Bean
Supplier<String> heartbeat() {
    return () -> "service-alive";
}
~~~

Function bean tên heartbeat có output binding heartbeat-out-0. Supplier reactive có thể trả về Flux liên tục; framework thường khởi tạo stream một lần. Với một stream hữu hạn cần poll định kỳ, có thể dùng PollableBean theo hướng dẫn phiên bản đang dùng.

### 3.2. Function: nhận và phát message

~~~java
@Bean
Function<String, String> normalize() {
    return value -> value.trim().toLowerCase(Locale.ROOT);
}
~~~

Function tên normalize có binding normalize-in-0 và normalize-out-0. Message đi vào input, được function xử lý, sau đó kết quả được gửi tới output.

### 3.3. Consumer: chỉ nhận và xử lý

~~~java
@Bean
Consumer<String> audit() {
    return value -> System.out.println("AUDIT: " + value);
}
~~~

Consumer tên audit có binding audit-in-0. Nếu logic cần phát message kết quả, hãy dùng Function hoặc StreamBridge thay vì mong Consumer tự sinh output.

### 3.4. Imperative và reactive

Với một message xử lý độc lập, Supplier/Function/Consumer imperative thường dễ hiểu. Khi làm việc với stream, có thể dùng Reactor:

~~~java
@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    return input -> input.map(String::toUpperCase);
}
~~~

Reactive function làm việc với cả stream thay vì một message đơn lẻ. Cơ chế lỗi và retry của reactive function khác imperative message handler.

Reactive Consumer có kiểu trả về void nên không cung cấp publisher để framework subscribe. Thường nên biểu diễn xử lý stream bằng Function<Flux<T>, Mono<Void>> và kết thúc pipeline bằng then(), hoặc tuân thủ cách subscribe được tài liệu phiên bản quy định.

## 4. Binding names và function definition

Tên binding được sinh từ tên function và vị trí input/output:

| Function | Binding |
|---|---|
| normalize | normalize-in-0 |
| normalize | normalize-out-0 |
| Function có hai input | functionName-in-0, functionName-in-1 |
| Function có nhiều output | functionName-out-0, functionName-out-1 |

Framework có thể tự phát hiện một functional bean. Dù vậy, nên khai báo rõ function cần bind bằng thuộc tính spring.cloud.function.definition:

~~~yaml
spring:
  cloud:
    function:
      definition: normalize
~~~

Việc khai báo tường minh tránh trường hợp một bean Supplier/Function/Consumer khác trong context bị tự động bind ngoài ý muốn.

### 4.1. Function composition

Có thể ghép function bằng dấu pipe:

~~~yaml
spring:
  cloud:
    function:
      definition: normalize|validate|enrich
~~~

Dữ liệu đi qua normalize, validate rồi enrich. Kiểu input/output của các function phải tương thích. Composition giúp chia pipeline thành phần nhỏ, dễ kiểm thử và tái sử dụng.

Tên binding mặc định của composition có thể dài. Có thể ánh xạ tên binding được sinh sang tên dễ đọc bằng thuộc tính spring.cloud.stream.function.bindings. Khi đổi tên binding, các thuộc tính destination/group phải tham chiếu đúng tên mới.

## 5. Cấu hình binding và destination

Binding properties dùng prefix:

~~~text
spring.cloud.stream.bindings.<bindingName>.<property>
~~~

Các thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| destination | Destination trên broker |
| group | Consumer group của input binding |
| contentType | Content type để chuyển đổi payload |
| binder | Binder cụ thể dùng cho binding |
| consumer.concurrency | Mức concurrency theo hỗ trợ của binder |
| consumer.maxAttempts | Số lần xử lý tối đa, gồm lần đầu |
| producer.partitionKeyExpression | Biểu thức lấy partition key |
| producer.partitionCount | Số partition mục tiêu hoặc giá trị gợi ý tùy binder |

Nếu không cấu hình destination, tên binding có thể được dùng làm destination mặc định. Trong hệ thống thực tế, nên cấu hình destination rõ ràng để tên function có thể thay đổi mà không làm thay đổi tên tài nguyên trên broker.

### 5.1. Ví dụ application.yml với Kafka binder

~~~yaml
spring:
  cloud:
    function:
      definition: normalize
    stream:
      bindings:
        normalize-in-0:
          destination: orders.raw
          group: order-normalizers
          content-type: text/plain
        normalize-out-0:
          destination: orders.normalized
          content-type: text/plain
    kafka:
      binder:
        brokers: localhost:9092
~~~

Function normalize được bind vào messaging. Input đọc từ orders.raw, thuộc group order-normalizers; output được gửi tới orders.normalized. Kafka binder kết nối broker tại localhost:9092.

Với Rabbit binder, destination được ánh xạ theo mô hình exchange/queue của RabbitMQ và cần dependency/configuration của Rabbit binder. Không giữ nguyên giả định rằng topic, queue và exchange có cùng cấu trúc vật lý.

### 5.2. Dependency và quản lý phiên bản

Ví dụ dependency Kafka binder cho Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-kafka</artifactId>
</dependency>
~~~

Có thể dùng artifact binder trực tiếp nếu cần:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka</artifactId>
</dependency>
~~~

Chọn Spring Cloud release train tương thích với Spring Boot và để BOM quản lý phiên bản. Không tự ghép một phiên bản Spring Cloud Stream mới nhất với bất kỳ phiên bản Boot nào. Rabbit binder có artifact tương ứng cho RabbitMQ.

## 6. Binder abstraction và Binder SPI

Binder abstraction là ranh giới giữa Spring Cloud Stream và middleware. Một binder cung cấp cơ chế bind producer và consumer tới destination cụ thể.

~~~text
Application output
       |
       v
Producer binding
       |
       v
Binder implementation
       |
       v
Broker destination

Broker destination
       |
       v
Binder implementation
       |
       v
Consumer binding
       |
       v
Application input
~~~

Binder implementation tạo adapter producer/consumer, áp dụng cấu hình và chuyển message. Framework cung cấp Binder SPI để các implementation tích hợp middleware khác.

Các binder phổ biến gồm Kafka và RabbitMQ. Hệ sinh thái còn có binder do đối tác hoặc cộng đồng duy trì. Khả năng, phiên bản hỗ trợ và mức độ bảo trì của từng binder cần được kiểm tra riêng.

### 6.1. Binder không xóa khác biệt của broker

- Kafka có topic, partition, offset và consumer group.
- RabbitMQ có exchange, queue, binding key, acknowledgement và prefetch.
- Broker khác có subscription, ordering, transaction và retention model riêng.

Application code có thể giữ logic nghiệp vụ tương đối độc lập, nhưng vận hành vẫn phải hiểu broker được chọn.

### 6.2. Chọn binder

Nếu chỉ có một binder phù hợp trên classpath, Spring Cloud Stream có thể tự phát hiện và sử dụng. Khi ứng dụng có nhiều binder, có thể khai báo binder instances và chọn binder cho từng binding.

Phân biệt:

- binder type: loại adapter, ví dụ kafka hoặc rabbit.
- binder name: tên instance cấu hình trong ứng dụng.
- binding name: tên input/output của function.
- destination: tên tài nguyên trên middleware.

## 7. Kết nối nhiều binder

Một ứng dụng có thể nhận message từ Kafka và phát thông báo sang RabbitMQ. Có thể khai báo hai binder instances:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-main:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: localhost:9092
        rabbit-notify:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: localhost
                port: 5672
      bindings:
        process-in-0:
          destination: orders.created
          group: order-processors
          binder: kafka-main
        process-out-0:
          destination: notifications
          binder: rabbit-notify
~~~

Ví dụ yêu cầu dependency cho cả hai binder và cấu hình kết nối phù hợp với môi trường.

Khi dùng nhiều binder:

- Mỗi binder có thể có extended properties riêng.
- Security, credentials, TLS và client configuration phải cấu hình riêng.
- Nếu input và output nằm trên hai broker, cần hiểu ranh giới transaction.
- Transaction ở broker này không tự động commit nguyên tử ở broker kia.
- Nên chỉ rõ binder cho binding quan trọng để tránh phụ thuộc default binder.

## 8. Consumer group và khả năng mở rộng

Giả sử destination orders.created có ba consumer instance:

- Instance A và B cùng group billing.
- Instance C thuộc group analytics.

A và B chia nhau message; C nhận bản sao độc lập. Điều này cho phép một event phục vụ nhiều mục đích nghiệp vụ: billing xử lý thanh toán, analytics cập nhật thống kê. Mỗi group có thể mở rộng độc lập.

Khi scale instance trong cùng group:

- Throughput có thể tăng nếu broker và partition/queue cho phép.
- Một số broker giới hạn mức song song bởi số partition.
- Ordering thường chỉ được đảm bảo trong phạm vi partition hoặc queue theo broker semantics.
- Nhiều instance không đồng nghĩa mọi message đều được xử lý đồng thời; partition assignment và concurrency quyết định mức song song.

Không dùng cùng group cho hai ứng dụng cần nhận mọi bản sao message độc lập. Không dùng group khác nhau cho các instance chỉ muốn chia tải cùng một công việc, vì mỗi group có thể nhận bản sao riêng.

## 9. Partitioning và partition key

Partitioning chia dữ liệu thành nhiều phần để xử lý song song. Với stateful processing, các message có cùng khóa nghiệp vụ thường cần tới cùng partition/consumer để giữ thứ tự tương đối và trạng thái cục bộ.

Ví dụ mọi sự kiện của cùng orderId được gửi vào cùng partition:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalize-out-0:
          producer:
            partition-key-expression: headers.orderId
            partition-count: 6
~~~

Partition key được tính từ message. Binder chọn partition theo thuật toán mặc định hoặc selector tùy cấu hình.

Với consumer partitioned:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalize-in-0:
          consumer:
            partitioned: true
      instance-index: 0
      instance-count: 3
~~~

Instance index phải duy nhất trong phạm vi instance count. Cách phân phối partition phụ thuộc binder. Kafka có thể tự rebalance partition trong consumer group; instanceIndex/instanceCount không phải lúc nào cũng cần. Với binder không có partitioning native, các giá trị này có thể cần thiết để phân chia tập dữ liệu.

Chọn partition key có ý nghĩa ordering và đủ phân bố, thường là customerId, accountId hoặc orderId. Tránh key có cardinality thấp nếu nó làm dữ liệu dồn vào một partition. Tăng partition count có thể ảnh hưởng mapping key-partition và ordering sau thay đổi; cần lập kế hoạch trước.

## 10. Retry, lỗi và dead-letter destination

Spring Cloud Stream có cơ chế xử lý lỗi chung, nhưng tính năng thực tế phụ thuộc binder và broker.

Với imperative message handler, lỗi có thể được chuyển về binder để retry theo cấu hình consumer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalize-in-0:
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
~~~

max-attempts tính cả lần xử lý đầu tiên. Đặt bằng 1 để tắt retry binder-level. Giá trị mặc định và exception classification có thể khác theo phiên bản; kiểm tra tài liệu phiên bản đang sử dụng.

Sau khi retry hết, có thể ghi log và bỏ message, gửi ErrorMessage tới custom error handler, requeue/redeliver nếu hỗ trợ, hoặc đưa message vào Dead Letter Queue/Dead Letter Topic.

DLQ là tính năng binder-specific. Ví dụ Kafka binder dùng enableDlq trên consumer binding; Rabbit binder có autoBindDlq cùng các thuộc tính riêng. Không sao chép property của Rabbit sang Kafka hoặc ngược lại.

Message trong DLQ cần quy trình replay, sửa dữ liệu hoặc reconciliation. Không replay mù quáng vì side effect có thể đã xảy ra một phần trước khi lỗi.

### 10.1. Reactive function có cơ chế lỗi riêng

Reactive function nhận Flux và trả Flux/Mono. Retry trong pipeline thường dùng Reactor operator như retryWhen. Thuộc tính binder-level RetryTemplate cho imperative handler không tự động áp dụng cùng cách cho reactive function.

Cần phân biệt retry một message với resubscribe cả stream. Retry toàn stream có thể phát lại nhiều phần tử đã xử lý, vì vậy cần idempotency hoặc checkpoint phù hợp.

## 11. StreamBridge: gửi message từ nguồn khác

Không phải mọi message đều bắt đầu từ Supplier. Ví dụ REST controller nhận request HTTP và cần phát event ra broker. StreamBridge cho phép gửi message tới output binding:

~~~java
@RestController
class OrderController {

    private final StreamBridge streamBridge;

    OrderController(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @PostMapping("/orders")
    ResponseEntity<Void> create(@RequestBody OrderCreated event) {
        boolean sent = streamBridge.send("orders-out-0", event);

        if (!sent) {
            return ResponseEntity.status(503).build();
        }

        return ResponseEntity.accepted().build();
    }
}
~~~

Ví dụ minh họa gửi tới binding orders-out-0. Cần cấu hình output binding/destination và hiểu ý nghĩa return value theo binder. Send trả true không chứng minh consumer đã xử lý message hoặc side effect downstream đã commit.

StreamBridge hữu ích khi nguồn dữ liệu là REST, scheduler hoặc hệ thống event-driven khác không phải binder. Nếu dữ liệu đã đi vào input binding và cần xử lý theo stream, hãy ưu tiên function pipeline rõ ràng.

## 12. Content type, serialization và headers

Binding có thuộc tính contentType, thường mặc định là application/json trong cấu hình chuẩn. Nó tham gia content type negotiation giữa message payload và converter.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalize-in-0:
          content-type: application/json
~~~

Nếu producer gửi JSON, consumer phải có kiểu dữ liệu và converter phù hợp. Với String hoặc text/plain, cần thống nhất encoding và content type.

Một số middleware hỗ trợ header native. Một số cần nhúng header vào payload theo chế độ embeddedHeaders. Binding có headerMode để điều khiển hành vi này tùy binder.

Khi bật useNativeEncoding hoặc useNativeDecoding, serialization có thể được chuyển cho client library của broker. Khi đó contentType của Spring Cloud Stream không còn là cơ chế marshal chính; producer/consumer phải cấu hình serializer/deserializer native tương ứng.

Không thay đổi content type hoặc native encoding một phía mà không kiểm tra consumer. Message có thể tới đúng destination nhưng decode thất bại vì hai bên dùng format khác nhau.

## 13. Test Binder: kiểm thử không cần broker thật

Spring Cloud Stream cung cấp Test Binder dựa trên Spring Integration, hoạt động trong JVM và không cần broker thật. Nó phù hợp để kiểm tra function, binding và luồng message cơ bản.

Thêm dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Test dùng InputDestination để gửi message vào input binding và OutputDestination để nhận output:

~~~java
@SpringBootTest
@EnableTestBinder
class NormalizeFunctionTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void normalizesMessage() {
        input.send(
            new GenericMessage<byte[]>("  ORDER-42  ".getBytes()),
            "normalize-in-0"
        );

        Message<byte[]> result = output.receive(0, "normalize-out-0");

        assertThat(new String(result.getPayload()))
            .isEqualTo("order-42");
    }
}
~~~

Test giả định function normalize có trong application context và binding được kích hoạt. Với nhiều binding, chỉ rõ binding name để test không phụ thuộc thứ tự.

Test Binder hữu ích để kiểm tra function, binding name, payload, headers/content type cơ bản và composition. Nó không mô phỏng đầy đủ broker thật, nên không chứng minh partition assignment, consumer group rebalancing, persistence, acknowledgement, native transaction, DLQ routing, security, TLS hoặc performance. Những phần này cần integration test với broker thực tế hoặc môi trường tương đương production.

## 14. Transaction và delivery guarantees

Spring Cloud Stream không tạo ra một bảo đảm exactly-once chung cho mọi binder. Delivery semantics phụ thuộc broker, binder, acknowledgement/offset policy, transaction và cách application xử lý side effect.

- Producer publish thành công không đồng nghĩa consumer đã xử lý.
- Consumer handler hoàn tất không tự động có nghĩa database và broker cùng commit nguyên tử.
- Retry hoặc redelivery có thể làm handler nhận cùng message nhiều lần.
- Kafka binder có hỗ trợ transaction khi cấu hình transactional binder; điều đó gắn với transaction semantics của Kafka và không tự bao gồm database hoặc RabbitMQ.
- Một transaction ở broker A không tạo transaction phân tán với broker B.

Với side effect database, thường cần idempotency, transaction và inbox/outbox phù hợp. Khi kết nối nhiều broker, thiết kế Saga hoặc compensation nếu nghiệp vụ trải qua nhiều hệ thống mà không có transaction chung.

## 15. Ví dụ hoàn chỉnh: function normalize

### Source code

Lưu thành NormalizeApplication.java:

~~~java
package example.stream;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NormalizeApplication {

    public static void main(String[] args) {
        SpringApplication.run(NormalizeApplication.class, args);
    }

    @Bean
    Function<String, String> normalize() {
        return value -> value.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

### application.yml

~~~yaml
spring:
  cloud:
    function:
      definition: normalize
    stream:
      bindings:
        normalize-in-0:
          destination: orders.raw
          group: order-normalizers
          content-type: text/plain
        normalize-out-0:
          destination: orders.normalized
          content-type: text/plain
    kafka:
      binder:
        brokers: localhost:9092
~~~

Ứng dụng cần Spring Boot starter phù hợp, Kafka binder starter và Spring Cloud BOM tương thích với phiên bản Boot.

### Luồng hoạt động

1. Ứng dụng khởi động và phát hiện function normalize.
2. Binding normalize-in-0 được nối với destination orders.raw.
3. Binder tạo consumer thuộc group order-normalizers.
4. Khi message đến, payload được decode thành String.
5. Function trim khoảng trắng và chuyển chữ thường bằng Locale.ROOT.
6. Kết quả được gửi qua normalize-out-0 tới orders.normalized.

Với input:

~~~text
  ORDER-42
~~~

Payload output:

~~~text
order-42
~~~

Ví dụ thể hiện application logic độc lập với Kafka API. Khi đổi sang binder khác, có thể giữ function và thay dependency/cấu hình binder; tuy nhiên phải kiểm tra lại semantics destination, group, partition, error handling và serialization.

## 16. Lỗi thiết kế thường gặp

- Nhầm binding name với destination name.
- Nhầm binder type với binder instance name.
- Dùng cùng consumer group cho hai ứng dụng cần nhận bản sao độc lập.
- Dùng group khác nhau cho các instance chỉ muốn chia tải cùng công việc.
- Cho rằng mọi broker ánh xạ destination thành cùng loại tài nguyên.
- Coi binder abstraction là bảo đảm mọi broker có cùng transaction, ordering hoặc acknowledgement.
- Quên khai báo function definition khi context có nhiều functional bean.
- Dùng reactive Consumer mà không quản lý subscription đúng cách.
- Áp dụng retry binder-level cho reactive stream như thể nó là imperative handler.
- Bật DLQ bằng property của binder khác.
- Dùng partition key không ổn định hoặc làm dữ liệu dồn vào một partition.
- Cho rằng Test Binder chứng minh broker thật đã cấu hình đúng.
- Dùng StreamBridge.send thành công như acknowledgement rằng consumer đã xử lý.
- Đổi content type hoặc native encoding một phía mà không cập nhật consumer.
- Ghép nhiều broker rồi giả định một transaction bao trùm tất cả.

## 17. Checklist triển khai

- [ ] Đã xác định source, processor và sink trong functional model.
- [ ] Function definition được khai báo rõ nếu có nhiều functional bean.
- [ ] Input/output binding names đã được xác định.
- [ ] Destination và consumer group có ý nghĩa nghiệp vụ rõ.
- [ ] Binder type và binder instance được phân biệt.
- [ ] Spring Cloud release train tương thích với Spring Boot.
- [ ] Content type, serialization và header mode được thống nhất.
- [ ] Consumer group được chọn đúng cho broadcast hay load balancing.
- [ ] Partition key và partition count phù hợp với ordering/scaling.
- [ ] Retry và DLQ được cấu hình theo đúng binder.
- [ ] Side effect có idempotency hoặc cơ chế xử lý trùng.
- [ ] Test Binder kiểm tra logic application và binding.
- [ ] Broker integration test kiểm tra group, partition, ack, transaction, DLQ và security.
- [ ] Dashboard/health/alert quan sát được lỗi và trạng thái binding.

## Kết luận

Spring Cloud Stream tách logic message-driven khỏi chi tiết kết nối middleware thông qua functional model, binding và binder. Function mô tả xử lý nghiệp vụ; binding nối input/output với destination; consumer group điều khiển cách các instance chia sẻ message; binder chuyển các abstraction đó thành producer/consumer cụ thể của broker. Abstraction giúp tái sử dụng application logic, nhưng partition, retry, DLQ, transaction và acknowledgement vẫn cần được hiểu theo binder và broker thực tế.

## Tài liệu tham khảo

- [Spring Cloud Stream Reference Documentation](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream.html)
- [Spring Cloud Stream - Binder Abstraction](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binders.html)
- [Spring Cloud Stream - Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream - Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream - Consumer Groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html)
- [Spring Cloud Stream - Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream - Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream - Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
