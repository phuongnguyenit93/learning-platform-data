# Kiến thức tiên quyết và trình tự học từ ứng dụng đầu tiên đến vận hành

Spring Cloud Stream giúp xây dựng ứng dụng xử lý sự kiện trên Spring Boot bằng mô hình hàm Supplier, Function và Consumer. Ứng dụng làm việc với các binding; binder kết nối binding với hệ thống trung gian như Apache Kafka, RabbitMQ hoặc Apache Pulsar. Để sử dụng thành thạo, cần học theo thứ tự: hiểu luồng thông điệp, chạy một function nhỏ, cấu hình broker, thiết kế nhóm tiêu thụ và phân vùng, xử lý lỗi, kiểm thử, rồi mới tối ưu vận hành.

## 1. Kiến thức cần có trước khi bắt đầu

### Java và Spring Boot

Cần nắm vững các phần sau:

- Java cơ bản đến mức có thể viết lambda, method reference, generic, record hoặc POJO, exception và collection.
- Các interface trong java.util.function: Supplier<T>, Function<T, R> và Consumer<T>.
- Spring IoC, dependency injection, bean, cấu hình bằng application.yml, profile và biến môi trường.
- Spring Boot auto-configuration, cấu hình logging, health indicator và cách đóng gói ứng dụng.
- Maven hoặc Gradle, cách quản lý dependency và BOM.

Spring Cloud Stream chạy trong một ứng dụng Spring Boot. Vì vậy, người học cần biết cách khởi động, cấu hình và kiểm tra một ứng dụng Boot trước khi thêm broker.

### Nền tảng xử lý thông điệp

Cần phân biệt rõ các khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| Message / event | Dữ liệu được gửi giữa các thành phần; event thường mô tả một việc đã xảy ra |
| Producer | Thành phần tạo và gửi thông điệp |
| Consumer | Thành phần nhận và xử lý thông điệp |
| Destination | Tài nguyên nhận hoặc phát thông điệp ở broker, ví dụ topic, exchange hoặc queue |
| Binding | Cầu nối logic giữa code ứng dụng và destination |
| Binder | Adapter kết nối Spring Cloud Stream với một loại middleware |
| Consumer group | Nhóm các instance cùng chia sẻ công việc đọc một destination |
| Partition | Phần độc lập của luồng dữ liệu, thường dùng để mở rộng song song và giữ thứ tự theo khóa |

Cần hiểu thêm publish-subscribe, competing consumers, acknowledgment, offset, retention, redelivery, ordering và backpressure. Các khái niệm này quyết định thông điệp có được giữ lại, giao lại hay xử lý song song như thế nào.

### Kiến thức hệ thống phân tán

Một consumer có thể xử lý xong nghiệp vụ nhưng bị dừng trước khi xác nhận thông điệp. Khi đó broker có thể giao lại cùng thông điệp. Một producer có thể gửi thành công nhưng mất kết nối trước khi nhận xác nhận. Vì vậy, cần hiểu retry, timeout, duplicate, idempotency, eventual consistency, transaction boundary và dead-letter queue.

Đây là nền tảng để tránh giả định rằng một thông điệp luôn được xử lý đúng một lần chỉ vì ứng dụng dùng Spring Cloud Stream.

## 2. Hiểu mô hình lập trình và kiến trúc của Spring Cloud Stream

Spring Cloud Stream sử dụng Spring Cloud Function làm mô hình lập trình. Phần code nghiệp vụ được biểu diễn bằng các bean hàm; phần binding và binder đảm nhiệm kết nối với middleware.

~~~mermaid
flowchart LR
  A["Producer hoặc Supplier"] --> B["Destination đầu vào"]
  B --> C["Binder và input binding"]
  C --> D["Function hoặc Consumer"]
  D --> E["Output binding và binder"]
  E --> F["Destination đầu ra"]
~~~

Ba kiểu hàm chính có vai trò khác nhau:

| Kiểu hàm | Đầu vào | Đầu ra | Khi nào dùng |
|---|---|---|---|
| Supplier<T> | Không có | T | Tạo sự kiện từ nguồn chủ động hoặc theo lịch polling |
| Function<T, R> | T | R | Nhận sự kiện, xử lý và phát kết quả |
| Consumer<T> | T | Không có | Nhận sự kiện để thực hiện tác vụ hoặc ghi dữ liệu |

Một Supplier thông thường được framework gọi bằng poller. Poller mặc định chạy mỗi giây; có thể điều chỉnh bằng cấu hình spring.integration.poller.fixed-delay. Nếu sự kiện đến từ một nguồn chủ động bên ngoài, chẳng hạn webhook hoặc callback, có thể dùng StreamBridge để gửi dữ liệu vào output binding thay vì ép nguồn đó thành một Supplier polling.

Tên binding mặc định được tạo từ tên bean:

- Supplier tên orderSource có output binding orderSource-out-0.
- Function tên validateOrder có input binding validateOrder-in-0 và output binding validateOrder-out-0.
- Consumer tên saveOrder có input binding saveOrder-in-0.
- Với hàm có nhiều tham số đầu vào hoặc nhiều đầu ra, chỉ số binding tăng theo vị trí, bắt đầu từ 0.

Binding là tên logic trong ứng dụng; destination là tên tài nguyên trên broker. Ví dụ, validateOrder-in-0 có thể được ánh xạ tới topic orders.created. Nhờ vậy, code nghiệp vụ không phải chứa tên topic, exchange hay queue.

Khi ứng dụng có nhiều bean hàm, khai báo hàm cần kích hoạt bằng spring.cloud.function.definition. Dùng dấu chấm phẩy để kích hoạt nhiều hàm độc lập, ví dụ validateOrder;writeAudit. Dùng dấu | để nối các hàm có kiểu dữ liệu tương thích thành một pipeline, ví dụ validateOrder|enrichOrder.

## 3. Tạo ứng dụng đầu tiên

Bài tập đầu tiên nên xử lý một sự kiện đơn giản: nhận OrderCreated, kiểm tra tổng tiền và phát OrderValidated. Bài tập này giúp quan sát trọn luồng từ payload, function, binding đến destination.

### Khai báo sự kiện và function

~~~java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.util.function.Function;

@SpringBootApplication
public class OrderValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderValidationApplication.class, args);
    }

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return order -> {
            if (order.total().signum() <= 0) {
                throw new IllegalArgumentException("Order total must be positive");
            }

            return new OrderValidated(
                order.orderId(),
                order.customerId(),
                order.total(),
                Instant.now()
            );
        };
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total
    ) {}

    public record OrderValidated(
        String orderId,
        String customerId,
        BigDecimal total,
        Instant validatedAt
    ) {}
}
~~~

Function chỉ mô tả xử lý nghiệp vụ. Nó không cần biết message đang đi qua Kafka, RabbitMQ hay Pulsar.

### Khai báo binding

Ví dụ application.yml dưới đây ánh xạ input và output tới hai destination. Cấu hình kết nối broker được cung cấp riêng theo môi trường.

~~~yaml
spring:
  application:
    name: order-validation

  cloud:
    function:
      definition: validateOrder

    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validation-v1
          content-type: application/json

        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json
~~~

Ở đây:

- orders.created là destination đầu vào.
- order-validation-v1 là consumer group có tên ổn định.
- orders.validated là destination đầu ra.
- application/json cho biết cách chuyển đổi payload ở tầng Spring Messaging.

Khi chạy, gửi một JSON phù hợp vào orders.created và quan sát kết quả ở orders.validated. Hãy thử cả một sự kiện hợp lệ và một sự kiện có tổng tiền không hợp lệ để hiểu cách exception đi vào luồng xử lý lỗi.

### Chọn binder và dependency

Thêm binder tương ứng vào ứng dụng. Quản lý phiên bản bằng Spring Cloud BOM tương thích với phiên bản Spring Boot đang dùng; không tự ghép các phiên bản Spring Cloud Stream khác dòng.

| Middleware | Dependency Maven | Ánh xạ destination thường gặp |
|---|---|---|
| Apache Kafka | org.springframework.cloud:spring-cloud-starter-stream-kafka | Topic |
| RabbitMQ | org.springframework.cloud:spring-cloud-starter-stream-rabbit | Exchange và queue |
| Apache Pulsar | org.springframework.pulsar:spring-pulsar-spring-cloud-stream-binder | Topic và subscription |
| Kafka Streams | org.springframework.cloud:spring-cloud-stream-binder-kafka-streams | KStream, KTable và GlobalKTable |

Kafka binder ánh xạ destination tới Kafka topic; consumer group và partition gắn trực tiếp với khái niệm tương ứng của Kafka. Rabbit binder làm việc với exchange và queue; mỗi group có cơ chế queue riêng để các consumer trong cùng nhóm cạnh tranh nhận thông điệp. Pulsar binder kết nối tới topic và subscription của Pulsar. Cùng một mô hình hàm có thể được giữ lại, nhưng cấu hình, khả năng và semantics ở tầng broker vẫn có khác biệt.

Với Kafka, cấu hình kết nối thường được đặt qua spring.kafka.bootstrap-servers hoặc thuộc tính binder tương ứng. RabbitMQ thường dùng spring.rabbitmq.addresses. Pulsar thường dùng spring.pulsar.client.service-url. Giá trị thực tế phải được cấp từ môi trường triển khai. Khi đóng gói nhiều binder trong cùng một ứng dụng, cần chỉ rõ binder cho từng binding nếu framework không thể tự chọn duy nhất.

## 4. Consumer group và khả năng mở rộng

Consumer group quyết định cách nhiều instance chia sẻ một luồng sự kiện. Cấu hình group nằm ở binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        saveOrder-in-0:
          destination: orders.created
          group: order-storage
~~~

Có hai cách tổ chức thường gặp:

- Nhiều instance cùng group: các instance chia nhau xử lý thông điệp. Mỗi thông điệp được giao cho một thành viên của nhóm theo cơ chế của broker.
- Nhiều group khác nhau: mỗi group nhận một bản sao logic của luồng sự kiện. Ví dụ order-storage lưu dữ liệu, order-notification gửi thông báo và order-analytics cập nhật thống kê.

Trong Kafka, group ID gắn với cơ chế quản lý offset và phân phối partition. Trong RabbitMQ, binder tạo queue tương ứng với destination và group. Trong Pulsar, subscription quyết định chế độ tiêu thụ; cần chọn loại subscription phù hợp với yêu cầu chia tải hoặc phát dữ liệu cho nhiều consumer.

Đặt tên group ổn định cho ứng dụng cần tiếp tục đọc sau khi restart. Thay group có thể khiến ứng dụng trở thành một nhóm tiêu thụ độc lập và đọc lại hoặc bỏ qua dữ liệu tùy theo vị trí bắt đầu được cấu hình. Không dùng group ẩn danh cho luồng nghiệp vụ cần quản lý offset, replay hoặc DLQ.

Khi tăng số instance, cần theo dõi số partition, số consumer và tốc độ xử lý. Với Kafka, một group không thể sử dụng nhiều consumer hoạt động song song hơn số partition đang được gán; consumer dư có thể ở trạng thái nhàn rỗi. Tăng instance mà không tăng khả năng phân vùng không nhất thiết làm tăng throughput.

## 5. Partition, khóa và thứ tự xử lý

Partition cho phép chia luồng dữ liệu thành nhiều phần để xử lý song song. Nếu các sự kiện của cùng một đơn hàng phải được xử lý theo thứ tự, hãy dùng orderId làm partition key. Nếu cần gom dữ liệu theo khách hàng, có thể dùng customerId.

Ví dụ cấu hình partition key ở output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          producer:
            partition-key-expression: payload.customerId
            partition-count: 12
~~~

Framework tính partition từ khóa đã chọn. Phía consumer phải được cấu hình tương thích với số partition và cách phân phối instance. Với các binder cần cơ chế partitioning chung, có thể cần cấu hình consumer.partitioned, spring.cloud.stream.instance-count và spring.cloud.stream.instance-index. Kafka mặc định dùng cơ chế rebalance native của Kafka; không cần đặt các giá trị instance này trong trường hợp thông thường, trừ khi chủ động tắt auto rebalance hoặc dùng chế độ phân bổ riêng.

Một số nguyên tắc quan trọng:

- Các sự kiện có cùng key thường đi vào cùng partition, nhờ đó giữ thứ tự trong phạm vi partition.
- Không có bảo đảm thứ tự toàn cục giữa nhiều partition.
- Key phân bố lệch có thể tạo hot partition, khiến một consumer trở thành nút thắt.
- Thay đổi số partition có thể làm thay đổi cách ánh xạ key sang partition; cần đánh giá tác động tới thứ tự và trạng thái trước khi mở rộng.
- Partitioning cần được thiết kế theo khóa nghiệp vụ và mức độ song song mong muốn, không chỉ dựa vào số instance hiện tại.

## 6. Thiết kế message và quản lý schema

Message contract là thỏa thuận giữa producer và consumer. Không nên gửi trực tiếp entity của cơ sở dữ liệu hoặc một đối tượng nội bộ có thể thay đổi tùy ý. Hãy định nghĩa event độc lập với mô hình lưu trữ.

Một event có thể mang các trường sau:

~~~json
{
  "eventId": "evt-10001",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T10:15:30Z",
  "orderId": "ord-9001",
  "customerId": "cus-2001",
  "total": 125000
}
~~~

eventId hỗ trợ chống xử lý trùng; eventType mô tả loại sự kiện; schemaVersion giúp nhận diện phiên bản hợp đồng; occurredAt ghi thời điểm nghiệp vụ xảy ra. Correlation ID và trace context có thể được truyền qua header để liên kết log và trace giữa các dịch vụ.

Ở giai đoạn đầu, application/json và message converter của Spring Cloud Stream thường đủ dùng. Khi nhiều ứng dụng hoặc nhiều ngôn ngữ cùng trao đổi dữ liệu, hãy quản lý schema rõ ràng. Schema Registry hỗ trợ đăng ký và tra cứu schema; Avro converter có thể đối chiếu writer schema của producer với reader schema của consumer. Với Pulsar, có thể dùng schema native của Pulsar thông qua use-native-encoding và use-native-decoding, cùng schema-type và message-type ở extended binding properties.

Khi thay đổi schema:

- Ưu tiên thêm trường tùy chọn có giá trị mặc định.
- Tránh đổi tên, xóa trường hoặc thay đổi ý nghĩa của trường đang được consumer sử dụng.
- Định nghĩa quy tắc tương thích backward, forward hoặc full theo chiến lược triển khai.
- Kiểm thử producer mới với consumer cũ và ngược lại trước khi phát hành.
- Không dựa riêng vào tên class Java để làm hợp đồng liên dịch vụ.

## 7. Retry, lỗi và Dead Letter Queue

Không phải lỗi nào cũng nên retry. Lỗi mạng tạm thời, broker gián đoạn hoặc dịch vụ phụ thuộc quá tải có thể tự hồi phục. Dữ liệu sai định dạng, vi phạm quy tắc nghiệp vụ hoặc thiếu trường bắt buộc thường không thể khắc phục bằng cách gửi lại ngay.

Cấu hình retry chung cho consumer binding có thể bắt đầu như sau:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
~~~

max-attempts là tổng số lần thử, bao gồm lần xử lý đầu tiên. Backoff tăng thời gian chờ giữa các lần thử để tránh tạo áp lực liên tục lên dịch vụ đang lỗi. Cần đặt giới hạn phù hợp với timeout của hệ thống phụ thuộc và thời gian xử lý tối đa mà broker cho phép.

Sau khi hết retry, Dead Letter Queue hoặc Dead Letter Topic giữ lại thông điệp lỗi để điều tra và xử lý lại. Cấu hình DLQ phụ thuộc binder.

Với Kafka, phải đặt group rõ ràng và bật DLQ ở extended binding properties:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          group: order-validation-v1
      kafka:
        bindings:
          validateOrder-in-0:
            consumer:
              enable-dlq: true
~~~

Với RabbitMQ, binder có thuộc tính auto-bind-dlq để tạo hạ tầng dead-letter tương ứng:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          validateOrder-in-0:
            consumer:
              auto-bind-dlq: true
~~~

Với Pulsar, cần cấu hình dead-letter policy theo khả năng của Pulsar consumer và phiên bản binder đang dùng. Không sao chép thuộc tính DLQ của Kafka hoặc RabbitMQ sang Pulsar vì tên và semantics không giống nhau.

DLQ cần có người hoặc quy trình chịu trách nhiệm. Hãy lưu lại nguyên nhân lỗi, destination gốc, thời điểm, eventId và số lần thử; đặt retention phù hợp; cảnh báo khi DLQ tăng; xây dựng quy trình kiểm tra, sửa dữ liệu hoặc code rồi redrive có kiểm soát. Redrive vẫn phải an toàn khi một event đã từng được xử lý một phần.

## 8. Xử lý trạng thái bằng Kafka Streams

Kafka binder thông thường đưa message payload vào Supplier, Function hoặc Consumer. Khi cần xử lý luồng có trạng thái như đếm theo khách hàng, tổng hợp theo cửa sổ thời gian, join hai luồng hoặc duy trì bảng dữ liệu cập nhật, hãy học Kafka Streams binder.

Kafka Streams binder hỗ trợ các kiểu dữ liệu chính:

- KStream biểu diễn chuỗi bản ghi sự kiện; mỗi bản ghi là một sự kiện độc lập.
- KTable biểu diễn trạng thái mới nhất theo key; bản ghi mới cập nhật giá trị của key đó.
- GlobalKTable là bảng trạng thái được sao chép tới các instance để tra cứu toàn cục.

Ví dụ sau đếm số sự kiện đơn hàng theo customerId. Producer phải đặt customerId làm record key để groupByKey gom đúng các sự kiện:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Configuration;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.springframework.context.annotation.Bean;

@Configuration
public class CustomerOrderCountTopology {

    @Bean
    Function<KStream<String, String>, KStream<String, Long>> countOrdersByCustomer() {
        return orders -> orders
            .groupByKey()
            .count(Materialized.as("orders-by-customer"))
            .toStream();
    }
}
~~~

Cấu hình binding và application ID:

~~~yaml
spring:
  cloud:
    function:
      definition: countOrdersByCustomer
    stream:
      bindings:
        countOrdersByCustomer-in-0:
          destination: orders.created
        countOrdersByCustomer-out-0:
          destination: orders.by-customer
      kafka:
        streams:
          binder:
            application-id: customer-order-counts
~~~

State store có tên orders-by-customer lưu trạng thái đã materialize. Kafka Streams binder có thể tự tạo state store khi dùng DSL phù hợp; với Processor API hoặc nhu cầu tùy chỉnh, cần khai báo store rõ ràng. State store cục bộ được khôi phục từ changelog topic khi instance khởi động lại, vì vậy cần quản lý application ID, quyền truy cập topic nội bộ, dung lượng đĩa và thời gian restore.

Có thể truy vấn store trong ứng dụng qua InteractiveQueryService. Khi ứng dụng chạy nhiều instance, key cần truy vấn có thể nằm trên instance khác; hệ thống gọi phải xác định host sở hữu key và định tuyến yêu cầu đến instance đó. Store cũng có thể chưa sẵn sàng ngay lúc ứng dụng vừa khởi động, do đó truy vấn cần có retry hoặc cơ chế báo trạng thái chưa sẵn sàng.

## 9. Kiểm thử theo từng lớp

Không nên chỉ kiểm thử bằng cách chạy ứng dụng và gửi thử một message. Nên xây dựng các lớp kiểm thử sau:

1. Unit test cho logic function: đầu vào hợp lệ, đầu vào sai, biên dữ liệu và exception.
2. Test binder cho luồng binding trong JVM: gửi message vào InputDestination, nhận message ở OutputDestination và kiểm tra payload.
3. Integration test với broker thật: dùng Kafka, RabbitMQ hoặc Pulsar trong môi trường kiểm thử, chẳng hạn qua Testcontainers.
4. Kiểm thử hợp đồng: xác nhận schema, content type, header và khả năng tương thích giữa producer với consumer.
5. Kiểm thử lỗi: broker ngắt kết nối, consumer xử lý chậm, exception lặp lại, DLQ, redelivery và redrive.
6. Kiểm thử tải: đo throughput, latency, consumer lag, mức sử dụng CPU, bộ nhớ và khả năng mở rộng partition.

Test binder không cần broker thật và rất phù hợp để kiểm tra kết nối input/output trong ứng dụng. Tuy nhiên, nó không chứng minh cấu hình Kafka, RabbitMQ hoặc Pulsar hoạt động chính xác. Các hành vi phụ thuộc broker như partition assignment, acknowledgment, transaction, retry và DLQ phải được kiểm tra bằng integration test.

## 10. Bảo đảm giao nhận và tính đúng đắn của nghiệp vụ

Trong hệ thống phân tán, xử lý trùng là tình huống bình thường cần được thiết kế trước. Một consumer có thể ghi dữ liệu thành công rồi bị dừng trước khi acknowledgment hoặc offset commit hoàn tất. Broker giao lại message và nghiệp vụ có thể chạy lần nữa.

Hãy thiết kế consumer theo hướng idempotent: cùng một eventId được xử lý nhiều lần vẫn cho ra kết quả cuối cùng như một lần. Có thể lưu eventId đã xử lý trong cùng transaction với thay đổi nghiệp vụ, dùng unique constraint hoặc thực hiện upsert theo khóa nghiệp vụ. Với thao tác gọi dịch vụ bên ngoài, cần có idempotency key hoặc cơ chế đối soát tương ứng.

Nếu ứng dụng vừa cập nhật cơ sở dữ liệu vừa phát event, tránh thực hiện hai thao tác độc lập mà không có cơ chế phối hợp. Transactional outbox ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction cơ sở dữ liệu; một tiến trình khác phát các event trong outbox lên broker. Phía consumer có thể dùng inbox hoặc bảng deduplication để chống xử lý lặp.

Kafka binder hỗ trợ transaction cho luồng đọc, xử lý và ghi lại Kafka trong cùng ranh giới transaction của Kafka. Cấu hình transaction cần transaction ID prefix duy nhất cho từng instance. Cơ chế này không tự động tạo transaction phân tán với cơ sở dữ liệu hoặc REST service. Khi có side effect bên ngoài Kafka, vẫn cần outbox, inbox, idempotency hoặc quy trình bù trừ phù hợp.

Không nên tuyên bố hệ thống có exactly-once end-to-end chỉ vì đã bật transaction ở broker. Hãy ghi rõ phạm vi bảo đảm: producer gửi bền vững đến đâu, broker lưu dữ liệu thế nào, consumer xác nhận ở thời điểm nào, side effect nghiệp vụ có chống trùng hay không và DLQ được phục hồi ra sao.

## 11. Đưa ứng dụng vào vận hành

Trước khi triển khai production, cần hoàn thiện các nhóm việc sau:

### Cấu hình và bảo mật

- Tách cấu hình theo môi trường; destination, group, broker URL và concurrency không nên bị cố định trong code.
- Lấy mật khẩu, token, certificate và credential từ secret manager hoặc cơ chế quản lý secret của nền tảng.
- Bật TLS và cơ chế xác thực của broker; cấp quyền tối thiểu cho producer, consumer và thao tác quản trị topic/queue.
- Xác định rõ ai được phép tạo destination tự động. Ở production, việc provision topic, queue, partition và retention thường cần được kiểm soát theo quy trình hạ tầng.

### Khả năng quan sát

Theo dõi tối thiểu:

- Số message vào/ra và tốc độ xử lý.
- Consumer lag hoặc backlog, thời gian chờ trong queue và processing latency.
- Số lần retry, số message vào DLQ, số lần redelivery và tuổi của message cũ nhất.
- Trạng thái kết nối broker, rebalance, lỗi serialization và lỗi xử lý.
- Với Kafka Streams: trạng thái processor, thời gian restore state store, dung lượng state và tình trạng truy vấn store.

Log nên có eventId, eventType, correlation ID, tên function, binding, group và thông tin partition/offset khi broker cung cấp. Tránh ghi toàn bộ payload nếu chứa dữ liệu nhạy cảm. Dùng distributed tracing để theo dấu một event qua nhiều dịch vụ.

### Triển khai và mở rộng

- Giữ group ID ổn định giữa các lần deploy nếu muốn tiếp tục đọc cùng luồng offset hoặc subscription.
- Dùng application ID ổn định cho từng Kafka Streams topology; các ứng dụng logic khác nhau cần ID riêng.
- Đảm bảo số partition, số instance và concurrency phù hợp với throughput mục tiêu.
- Có readiness check để tránh nhận traffic trước khi kết nối broker và các dependency cần thiết đã sẵn sàng.
- Cho ứng dụng thời gian shutdown phù hợp để hoàn tất xử lý đang chạy và đóng consumer/producer đúng cách.
- Với Kafka Streams, tính đến thời gian khôi phục state store sau restart và dung lượng lưu trữ cục bộ.
- Kiểm thử rolling deployment, scale up/down, mất kết nối broker và khôi phục sau sự cố trước khi phát hành.

## 12. Trình tự học và tiêu chí hoàn thành

Có thể triển khai lộ trình theo các mốc sau:

| Mốc | Nội dung thực hành | Tiêu chí hoàn thành |
|---|---|---|
| 1. Nền tảng | Java function, Spring Boot, message, topic/queue, group và acknowledgment | Giải thích được producer, consumer, destination, binding và binder |
| 2. Ứng dụng đầu tiên | Viết Function<OrderCreated, OrderValidated>, chạy với một binder | Gửi message vào input và nhận kết quả ở output |
| 3. Supplier và Consumer | Tạo nguồn polling, consumer chỉ có input, composition các function | Phân biệt đúng trigger và binding của từng kiểu hàm |
| 4. Broker | Chạy cùng nghiệp vụ với Kafka, RabbitMQ hoặc Pulsar | Biết cấu hình connection, destination, group và binder |
| 5. Scale và ordering | Chạy nhiều instance, đặt key và phân vùng | Giải thích được giới hạn song song và thứ tự theo partition |
| 6. Contract và lỗi | Thiết kế schema, retry, DLQ và redrive | Kiểm thử được schema compatibility và đường đi của message lỗi |
| 7. Kafka Streams | Viết KStream/KTable, materialize state store và truy vấn | Khôi phục được state sau restart và hiểu cách định tuyến interactive query |
| 8. Kiểm thử và vận hành | Test binder, broker thật, metrics, tracing, bảo mật và triển khai | Có thể chẩn đoán lag, retry, DLQ, lỗi kết nối và duplicate trong môi trường staging |

Nên hoàn thành từng mốc bằng một ứng dụng nhỏ có thể chạy lại và một bộ kiểm thử tự động. Chỉ chuyển sang mốc tiếp theo khi đã giải thích được cấu hình hiện tại và quan sát được hành vi của message trong broker.

## 13. Tài liệu tham khảo chính thức

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — kiến trúc, binding, binder và cấu hình chung.
- [Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — quy tắc đặt tên binding theo Supplier, Function và Consumer.
- [Consumer groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html) và [Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html) — chia tải, group và phân vùng.
- [Error handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html) — retry và xử lý message lỗi.
- [Kafka binder DLQ](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html) và [RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html) — cấu hình riêng theo broker.
- [Pulsar binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — dependency, message conversion, schema và topic provisioning.
- [Schema Registry](https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html) — quản lý schema và schema evolution.
- [Kafka Streams binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/usage.html), [State Store](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/state-store.html) và [Interactive Queries](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/interactive-queries.html) — xử lý luồng có trạng thái.
- [Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html) — test binder và kiểm thử luồng binding.

