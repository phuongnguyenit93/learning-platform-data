# Giao dịch trong chuỗi nhận, xử lý và phát thông điệp

Trong một ứng dụng xử lý sự kiện, một bản ghi thường đi qua ba bước: nhận sự kiện từ Kafka, thực hiện logic nghiệp vụ và phát sự kiện kết quả sang topic khác. Nếu ứng dụng chỉ commit offset đầu vào sau khi gửi đầu ra thành công, vẫn có một khoảng thời gian giữa hai thao tác mà tiến trình có thể dừng. Kafka transaction giải quyết khoảng trống này bằng cách gom bản ghi đầu ra và offset đầu vào vào cùng một giao dịch Kafka.

Khi giao dịch commit, Kafka công bố các bản ghi đầu ra và lưu offset đầu vào như một đơn vị nguyên tử. Khi giao dịch abort, các bản ghi đầu ra không được consumer ở chế độ read_committed nhìn thấy và offset đầu vào không được commit trong giao dịch đó. Broker có thể giao lại bản ghi đầu vào để ứng dụng xử lý lại.

Trong Spring Cloud Stream, Kafka binder hỗ trợ mô hình này bằng transaction của Spring for Apache Kafka. Khi bật transaction cho binder, producer binding gửi dữ liệu trong transaction; với luồng nhận-xử lý-phát, binder có thể gắn việc gửi kết quả và commit offset vào cùng ranh giới giao dịch.

## 1. Vì sao cần transaction trong chuỗi xử lý?

Giả sử dịch vụ order-processor nhận bản ghi từ topic orders.submitted, kiểm tra đơn hàng rồi phát kết quả sang orders.accepted. Nếu ứng dụng gửi kết quả và commit offset bằng hai thao tác độc lập, có hai tình huống lỗi:

| Thời điểm tiến trình dừng | Hậu quả có thể xảy ra |
|---|---|
| Sau khi gửi orders.accepted nhưng trước khi commit offset đầu vào | Bản ghi đầu vào được giao lại; ứng dụng có thể phát kết quả trùng |
| Sau khi commit offset đầu vào nhưng trước khi gửi orders.accepted | Bản ghi đầu vào đã được xác nhận; kết quả đầu ra có thể bị mất |

Kafka transaction cho phép ghi output record và offset đầu vào vào cùng một transaction:

~~~mermaid
flowchart TD
    A["Đọc record từ orders.submitted"] --> B["Bắt đầu Kafka transaction"]
    B --> C["Chạy logic xử lý"]
    C --> D["Gửi record sang orders.accepted"]
    D --> E["Đưa offset đầu vào vào transaction"]
    E --> F{"Commit transaction"}
    F -->|Thành công| G["Output và offset cùng được commit"]
    F -->|Lỗi| H["Abort transaction"]
    H --> I["Output bị ẩn với read_committed; input có thể được giao lại"]
~~~

Điểm quan trọng là offset đầu vào và các bản ghi đầu ra phải tham gia cùng một Kafka transaction. Chỉ bật idempotent producer hoặc chỉ đặt consumer isolation level không tạo ra tính nguyên tử cho cả chuỗi.

## 2. Kafka transaction bảo đảm điều gì?

Kafka transaction cung cấp tính nguyên tử cho các thao tác ghi thuộc cùng một transaction trên một Kafka cluster. Transaction có thể ghi nhiều record, kể cả trên nhiều topic và partition. Với consume-transform-produce, offset đã xử lý có thể được gửi vào chính transaction đó.

| Tình huống | Kết quả |
|---|---|
| Transaction commit | Các record đầu ra được công bố cùng offset đầu vào |
| Transaction abort | Record đầu ra của transaction không được đọc bởi consumer read_committed; offset đầu vào không được commit trong transaction |
| Consumer đọc với read_committed | Chỉ đọc các record thuộc transaction đã commit và các record không thuộc transaction |
| Consumer đọc với read_uncommitted | Có thể nhìn thấy record thuộc transaction chưa commit hoặc đã abort |

Kafka dùng transaction coordinator để quản lý trạng thái transaction và marker commit/abort. Consumer read_committed dựa vào trạng thái đó để xác định record nào được phép nhìn thấy.

### 2.1. Transaction khác idempotent producer

Idempotent producer ngăn một lần gửi bị retry ở tầng producer tạo ra nhiều bản ghi trùng do retry mạng trong phạm vi producer session/sequence mà Kafka quản lý. Nó không tự gom nhiều lần gửi và offset consumer thành một đơn vị nguyên tử.

Kafka transaction bổ sung:

- Nhóm nhiều lần gửi vào một ranh giới commit hoặc abort.
- Cho phép gửi offset consumer vào cùng transaction với output record.
- Cho phép downstream consumer read_committed loại bỏ dữ liệu thuộc transaction bị abort.

Idempotence là nền tảng quan trọng cho transactional producer, nhưng idempotence đơn lẻ không tương đương consume-process-produce exactly-once.

### 2.2. Phạm vi của exactly-once

Trong chuỗi Kafka-to-Kafka, transaction có thể bảo đảm kết quả đầu ra và offset đầu vào được commit cùng nhau. Điều đó thường được gọi là exactly-once processing trong phạm vi Kafka.

Nó không có nghĩa:

- Hàm nghiệp vụ chỉ được gọi đúng một lần. Khi transaction abort, hàm có thể được chạy lại.
- Mọi side effect bên ngoài Kafka đều được rollback.
- Ghi database, gọi HTTP, gửi email hoặc thanh toán tự động trở thành một phần của Kafka transaction.
- Hai Kafka cluster khác nhau cùng tham gia một transaction nguyên tử.
- Ứng dụng không cần idempotency hoặc xử lý duplicate ở các hệ thống ngoài Kafka.

Vì vậy, cần xác định rõ ranh giới của bảo đảm giao dịch trước khi gọi một luồng xử lý là exactly-once.

## 3. Bật transaction cho Kafka binder

Kafka binder bật transaction khi cấu hình transaction ID prefix. Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-processor
        processOrder-out-0:
          destination: orders.accepted
      kafka:
        binder:
          brokers: kafka-1:9092
          transaction:
            transactionIdPrefix: order-processor-pod-01-
~~~

Thuộc tính quan trọng là:

~~~text
spring.cloud.stream.kafka.binder.transaction.transactionIdPrefix
~~~

Khi transaction ID prefix được cấu hình, Kafka binder sử dụng transactional producer cho các output binding. Trong luồng consumer-initiated transaction, listener container bắt đầu transaction khi nhận bản ghi; kết quả gửi ra Kafka và offset đầu vào được xử lý trong cùng transaction theo cơ chế binder.

Ví dụ trên dùng prefix minh họa cho một instance. Trong production, mỗi instance đang hoạt động đồng thời cần prefix duy nhất. Có thể lấy danh tính pod hoặc instance từ hệ thống triển khai và đưa vào cấu hình. Không dùng cùng một prefix cho nhiều instance hoạt động song song vì Kafka có thể fencing producer cũ khi phát hiện transactional ID bị dùng trùng.

### 3.1. Transaction ID prefix và transactional.id

Kafka producer cần một transactional.id ổn định và duy nhất trong phạm vi các producer đang hoạt động. Kafka binder nhận prefix rồi tạo các transactional ID cụ thể cho producer được quản lý.

| Thành phần | Vai trò |
|---|---|
| transactionIdPrefix | Prefix cấu hình ở binder để tạo transactional producer |
| transactional.id | Danh tính transaction thực tế của Kafka producer |
| consumer group | Danh tính nhóm consumer chia partition và lưu offset |
| topic/partition | Nơi chứa record đầu vào và đầu ra |

Prefix không phải consumer group và không phải tên topic. Mỗi replica cần prefix khác nhau; các producer trong cùng instance có thể được binder quản lý suffix riêng.

Nếu hai instance dùng cùng transactional ID, broker có thể tăng producer epoch và fencing một producer. Lỗi ProducerFencedException thường cho thấy một producer khác đang dùng cùng transactional ID hoặc một producer cũ vẫn còn hoạt động.

## 4. Xử lý một message bằng Function imperative

Ví dụ một Function nhận đơn hàng và trả về sự kiện đã chấp nhận:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderSubmitted(
    String orderId,
    String customerId,
    int quantity
) {}

record OrderAccepted(
    String orderId,
    String customerId,
    int quantity,
    String status
) {}

@Configuration
class OrderConfiguration {

    @Bean
    Function<OrderSubmitted, OrderAccepted> processOrder() {
        return order -> {
            if (order.quantity() <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }

            return new OrderAccepted(
                order.orderId(),
                order.customerId(),
                order.quantity(),
                "ACCEPTED"
            );
        };
    }
}
~~~

Khi chạy với Kafka binder đã bật transaction, output của Function được gửi qua output binding thuộc transaction được binder quản lý. Offset của input record chỉ được commit cùng transaction khi quá trình xử lý và gửi output hoàn tất.

Một Function imperative phù hợp với mô hình consumer-initiated transaction vì binder có thể bao quanh lần gọi message handler bằng ranh giới transaction. Với reactive Function, không nên mặc định transaction thread-bound của listener tự bao phủ toàn bộ pipeline bất đồng bộ; cần kiểm tra hỗ trợ của phiên bản binder và mô hình thực thi đang dùng.

## 5. Transaction bao phủ nhiều output binding

Một lần xử lý có thể phát nhiều sự kiện ra các topic khác nhau. Khi các output binding dùng cùng Kafka binder và cùng transaction đang hoạt động, các record được gửi trong transaction đó có thể commit hoặc abort cùng nhau.

Ví dụ một đơn hàng được chấp nhận cần phát hai sự kiện:

- orders.accepted để dịch vụ đơn hàng tiếp tục xử lý.
- inventory.reservations để dịch vụ kho giữ hàng.

Function có thể dùng các output binding tường minh qua StreamBridge hoặc một thiết kế function trả về nhiều output theo mô hình ứng dụng. Khi dùng StreamBridge, việc gửi phải tham gia đúng transaction đang hoạt động; không tự tạo producer/transaction độc lập rồi kỳ vọng chúng được gộp vào transaction của input binding.

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    void publish(OrderAccepted accepted) {
        Message<OrderAccepted> message = MessageBuilder
            .withPayload(accepted)
            .setHeader("eventType", "OrderAccepted")
            .build();

        if (!streamBridge.send("accepted-out-0", message)) {
            throw new IllegalStateException("Could not send OrderAccepted");
        }
    }
}
~~~

Khai báo output binding cho StreamBridge:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: accepted-out-0
      bindings:
        accepted-out-0:
          destination: orders.accepted
~~~

Nếu dùng StreamBridge thay cho giá trị trả về của Function, có thể gọi publisher đồng bộ từ một Consumer đang được binder xử lý:

~~~java
@Bean
Consumer<OrderSubmitted> processOrder(OrderEventPublisher publisher) {
    return order -> {
        if (order.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        publisher.publish(new OrderAccepted(
            order.orderId(),
            order.customerId(),
            order.quantity(),
            "ACCEPTED"
        ));
    };
}
~~~

Tên binding và cách gọi phải khớp cấu hình ứng dụng. Khi gửi qua StreamBridge bên trong consumer-initiated transaction, hãy xác nhận producer binding sử dụng cùng binder và transaction context. Nếu một output binding trỏ sang binder hoặc cluster khác, Kafka transaction hiện tại không thể làm cho cả hai cluster commit nguyên tử.

Nếu một trong các lần gửi thất bại và exception được truyền ra ngoài trước commit, transaction có thể abort cả các record đã gửi trước đó trong cùng transaction. Đừng bắt exception rồi bỏ qua nếu muốn transaction rollback; bắt và xử lý lỗi im lặng có thể khiến transaction commit trong khi nghiệp vụ chưa hoàn tất.

## 6. Consumer đọc dữ liệu transactional bằng read_committed

Kafka consumer có isolation level:

| Isolation level | Dữ liệu có thể đọc |
|---|---|
| read_uncommitted | Record transactional chưa commit, đã commit hoặc đã abort; không chờ transaction hoàn tất để lọc |
| read_committed | Record không thuộc transaction và record thuộc transaction đã commit; bỏ qua record thuộc transaction abort/chưa hoàn tất |

Downstream consumer cần read_committed nếu chỉ được xử lý dữ liệu đã commit. Có thể cấu hình cho binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          auditOrders-in-0:
            consumer:
              configuration:
                isolation.level: read_committed
~~~

Đây là cấu hình Kafka consumer riêng cho binding auditOrders-in-0. Hãy kiểm tra tên binding sau khi ánh xạ và cấu hình binder thực tế. Không đặt isolation.level vào cấu hình producer vì đây là thuộc tính của consumer.

Consumer đọc read_committed có thể bị chậm nhìn thấy dữ liệu nếu một transaction trước đó trên partition vẫn đang mở. Kafka chỉ cho phép đọc đến Last Stable Offset (LSO), tức vị trí an toàn trước transaction chưa hoàn tất. Vì vậy, transaction quá dài có thể làm tăng độ trễ của consumer downstream dù record đã được append vào log.

## 7. Điều gì xảy ra khi transaction abort?

Giả sử Function nhận order-501, gửi OrderAccepted rồi gặp lỗi trước khi transaction commit. Kafka transaction abort sẽ đánh dấu các record đầu ra thuộc transaction là không được commit. Consumer read_committed không nhìn thấy OrderAccepted đó.

Offset của order-501 cũng không được commit trong transaction bị abort. Khi consumer tiếp tục, bản ghi đầu vào có thể được giao lại và logic xử lý được chạy lần nữa.

Các bước cần phân biệt:

1. Exception xảy ra trong logic xử lý hoặc khi gửi output.
2. Transaction hiện tại bị rollback/abort.
3. Record output đã gửi trong transaction không được công bố cho read_committed.
4. Offset input chưa được commit trong transaction.
5. Consumer có thể xử lý lại input record.

Đây là lý do logic nghiệp vụ cần an toàn khi chạy lại. Kafka transaction bảo vệ tính nguyên tử của dữ liệu Kafka; nó không ngăn code được gọi lại sau rollback.

### 7.1. Retry và poison message

Một message lỗi tạm thời có thể được retry sau rollback. Tuy nhiên, message không hợp lệ có thể khiến transaction abort lặp lại. Cần có chính sách:

- Retry có giới hạn và backoff cho lỗi tạm thời.
- Phân loại lỗi dữ liệu không thể phục hồi để tránh retry vô hạn.
- Cơ chế recovery hoặc DLQ phù hợp với transaction mode của binder.
- Theo dõi số lần rollback, retry và message tồn đọng.

Khi bật transaction, không nên giả định mọi thuộc tính retry/DLQ của binder imperative không transactional vẫn có hành vi giống hệt. Kiểm tra tài liệu và API của phiên bản Spring Cloud Stream/Spring Kafka đang chạy, đặc biệt cách binder cấu hình AfterRollbackProcessor, error handler và gửi DLQ. Nếu cần chuyển message thất bại sang DLQ, xác nhận việc gửi DLQ có tham gia transaction phù hợp và offset chỉ được commit theo chính sách mong muốn.

## 8. Ranh giới transaction với database và dịch vụ ngoài

Kafka transaction không tự động tham gia vào transaction của PostgreSQL, MySQL, Redis hoặc HTTP service. Ví dụ:

1. Function ghi đơn hàng vào database.
2. Function gửi OrderAccepted vào Kafka.
3. Kafka transaction abort.

Database không tự rollback chỉ vì Kafka transaction abort. Lần giao lại message có thể ghi đơn hàng lần nữa hoặc lặp một side effect bên ngoài Kafka.

### 8.1. Dùng idempotency cho thao tác database

Nếu xử lý một sự kiện Kafka làm thay đổi database, có thể dùng inbox/deduplication table với event ID duy nhất. Trong một database transaction:

1. Thử ghi event ID vào bảng inbox có unique constraint.
2. Nếu ID đã tồn tại, xác định đây là sự kiện đã xử lý và không lặp side effect.
3. Nếu ID mới, thực hiện thay đổi nghiệp vụ trong cùng transaction database.
4. Commit database transaction.
5. Để binder commit offset Kafka theo quy trình nhận message.

Nếu ứng dụng dừng sau khi database commit nhưng trước khi offset Kafka commit, Kafka có thể giao lại message. Unique constraint trong inbox giúp lần xử lý sau nhận diện duplicate và không lặp thay đổi nghiệp vụ.

### 8.2. Dùng transactional outbox khi database là nguồn sự thật

Nếu nghiệp vụ cập nhật database rồi cần phát sự kiện Kafka, transactional outbox là một lựa chọn:

- Trong cùng database transaction, cập nhật dữ liệu nghiệp vụ và thêm một hàng vào bảng outbox.
- Một publisher riêng đọc outbox và gửi sự kiện lên Kafka.
- Sau khi gửi thành công, publisher đánh dấu hoặc xóa hàng outbox theo chính sách.
- Publisher cần idempotency vì có thể gửi lại nếu dừng giữa bước gửi và bước đánh dấu.

Outbox không tạo transaction phân tán giữa database và Kafka. Nó bảo đảm dữ liệu nghiệp vụ và ý định phát sự kiện được lưu cùng nhau trong database, rồi publisher chuyển tiếp một cách có thể phục hồi.

## 9. Thời hạn và cấu hình transaction

Transaction cần hoàn tất trong khoảng thời gian mà broker và client cho phép. Nếu transaction kéo dài quá lâu, coordinator có thể hết hạn transaction hoặc producer gặp timeout.

| Thành phần | Ảnh hưởng |
|---|---|
| transaction.timeout.ms | Thời gian tối đa broker cho phép transaction mở |
| max.poll.interval.ms | Thời gian tối đa giữa các lần poll của consumer trước khi group xem consumer là không còn tiến triển |
| max.poll.records | Số record tối đa một lần poll trả về; ảnh hưởng thời gian xử lý batch |
| request.timeout.ms / delivery.timeout.ms | Giới hạn thời gian request và gửi record ở producer |
| thời gian xử lý nghiệp vụ | Thời gian Function/Consumer cần để xử lý message và phát output |
| transaction coordinator availability | Khả năng bắt đầu, commit hoặc abort transaction |

Không tăng transaction timeout một cách tùy tiện. Transaction mở lâu làm consumer read_committed chờ LSO và có thể ảnh hưởng throughput, độ trễ, rebalance hoặc khả năng phục hồi.

Nếu mỗi lần xử lý một batch có nhiều record, thời gian hoàn tất toàn bộ batch phải nằm trong giới hạn poll và transaction. Có thể giảm max.poll.records, tối ưu logic hoặc chia nhỏ công việc nếu thời gian xử lý quá dài.

## 10. Tính duy nhất của prefix khi chạy nhiều instance

Trong môi trường có nhiều replica, mỗi instance phải có transaction ID prefix riêng. Ví dụ:

| Instance | transactionIdPrefix |
|---|---|
| Pod A | order-processor-pod-a- |
| Pod B | order-processor-pod-b- |
| Pod C | order-processor-pod-c- |

Không đặt cùng một prefix cố định cho cả deployment nếu các instance hoạt động đồng thời. Nếu prefix bị trùng, producer có thể bị fencing và transaction đang chạy có thể thất bại.

Hệ thống triển khai có thể cấp danh tính instance từ pod name hoặc một định danh duy nhất khác. Cần bảo đảm danh tính đó không trùng giữa các instance đang chạy. Khi restart cùng một instance identity, Kafka có thể dùng fencing để vô hiệu hóa producer cũ; đây là một phần của cơ chế phục hồi producer transaction.

## 11. Cấu hình bảo đảm đọc dữ liệu đã commit

Một ứng dụng xử lý chuỗi Kafka có thể có input binding đọc sự kiện từ một dịch vụ khác và output binding phát kết quả transactional. Mẫu cấu hình tổng hợp:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-processor
        processOrder-out-0:
          destination: orders.accepted
      kafka:
        binder:
          brokers: kafka-1:9092
          transaction:
            transactionIdPrefix: order-processor-pod-a-
~~~

Consumer khác cần chỉ đọc dữ liệu đã commit có thể cấu hình isolation level riêng:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          auditOrders-in-0:
            consumer:
              configuration:
                isolation.level: read_committed
~~~

Chỉ khai báo auditOrders-in-0 nếu ứng dụng thực sự có function/binding tương ứng. Cấu hình consumer isolation cho một binding không tự tạo binding mới.

## 12. Transaction với KafkaTemplate và StreamBridge

Spring Cloud Stream Kafka binder quản lý transaction cho các binding được cấu hình theo binder. Nếu ứng dụng dùng KafkaTemplate trực tiếp, cần hiểu transaction manager nào đang sở hữu transaction và bảo đảm template tham gia đúng transaction.

Một KafkaTemplate có thể tham gia transaction đang được KafkaTransactionManager quản lý khi dùng cùng producer factory tương ứng. Nếu gọi API bắt đầu transaction độc lập như executeInTransaction bên trong một consumer transaction khác, ứng dụng có thể tạo transaction độc lập hoặc không đạt được tính nguyên tử mong muốn.

Với Spring Cloud Stream:

- Ưu tiên output binding/StreamBridge được cấu hình với cùng Kafka binder và transaction context.
- Không tạo một producer thủ công với transactional.id tùy ý rồi gửi song song với binder.
- Không dùng binder khác hoặc Kafka cluster khác nếu cần một transaction nguyên tử chung.
- Kiểm thử rằng output và offset cùng commit/abort trong trường hợp lỗi.

@Transactional chung không tự động có nghĩa Kafka transaction. Cần xác định transaction manager được chọn, thứ tự transaction manager và tài nguyên mà method đang tham gia. Nếu đồng thời có database transaction và Kafka transaction, không giả định một annotation làm hai hệ thống commit nguyên tử.

## 13. Kiểm thử transaction bằng Kafka broker

Unit test cho Function có thể kiểm tra logic nghiệp vụ nhưng không kiểm chứng transaction của broker. Để kiểm thử semantics commit/abort, cần integration test với Kafka broker thật hoặc Kafka Testcontainers.

Một kịch bản kiểm thử nên:

1. Tạo topic đầu vào và đầu ra.
2. Khởi chạy ứng dụng với transaction ID prefix duy nhất.
3. Gửi một record vào topic đầu vào.
4. Xác minh output record xuất hiện với consumer read_committed.
5. Xác minh offset của consumer group đã tiến lên sau transaction commit.
6. Gửi một record làm Function ném exception sau khi có thao tác chuẩn bị gửi output.
7. Xác minh output của transaction bị abort không xuất hiện với read_committed.
8. Xác minh input chưa được commit và có thể được retry/re-deliver theo cấu hình.
9. Khởi động nhiều instance và xác minh prefix không gây ProducerFencedException.

Để phân biệt read_committed với read_uncommitted, có thể dùng hai consumer cấu hình isolation khác nhau và kiểm tra record thuộc transaction bị abort. Consumer read_committed không được nhận record đó; consumer read_uncommitted có thể nhìn thấy record đã append nhưng transaction bị abort.

Ngoài ra, cần kiểm thử:

- Producer fencing khi cố tình tạo hai instance trùng transactional ID.
- Transaction timeout khi logic xử lý kéo dài.
- Consumer rebalance khi instance dừng giữa lúc transaction mở.
- Retry và DLQ sau rollback.
- Nhiều output record trên nhiều topic cùng commit hoặc abort.
- Lỗi kết nối trong giai đoạn commit và hành vi phục hồi.

## 14. Theo dõi transaction trong production

Transaction làm tăng thêm trạng thái cần quan sát ngoài consumer lag thông thường:

| Chỉ số hoặc log | Điều cần tìm |
|---|---|
| Transaction commit rate | Số transaction hoàn tất thành công |
| Transaction abort rate | Tần suất rollback do lỗi nghiệp vụ, timeout hoặc broker |
| Transaction duration | Transaction mở bao lâu |
| Producer fencing errors | Prefix/transactional ID trùng hoặc producer cũ bị fencing |
| Consumer lag | Độ trễ đọc của input binding |
| Last Stable Offset và read_committed lag | Transaction mở lâu đang chặn dữ liệu downstream hay không |
| Retry/rollback count | Message nào liên tục làm transaction thất bại |
| Coordinator errors/timeouts | Broker transaction coordinator có vấn đề hay không |

Khi abort tăng đột biến, tìm nguyên nhân gốc ở exception xử lý, timeout, rebalance, lỗi gửi output hoặc transaction coordinator. Không chỉ tăng timeout hay retry mà không xem xét thời gian xử lý và trạng thái broker.

## 15. Những hiểu lầm thường gặp

**Bật idempotence là đã có consume-process-produce exactly-once.** Idempotence giảm duplicate do retry producer; cần Kafka transaction để gắn output record với offset đầu vào.

**Chỉ cần transactionIdPrefix là mọi hệ thống đều atomic.** Prefix bật transactional producer trong binder. Database, HTTP service và cluster khác vẫn nằm ngoài Kafka transaction.

**Consumer nào cũng tự ẩn record abort.** Consumer phải dùng isolation.level=read_committed nếu cần chỉ nhìn thấy dữ liệu đã commit.

**Function chỉ chạy một lần.** Khi transaction abort và input offset chưa commit, Function có thể chạy lại.

**Một prefix dùng chung cho toàn bộ replica là đủ.** Các instance hoạt động đồng thời cần transactional ID riêng để tránh producer fencing.

**Transaction càng dài càng an toàn.** Transaction mở lâu có thể chặn LSO, tăng độ trễ downstream và gây timeout hoặc rebalance.

**Bắt exception rồi tiếp tục là tương đương rollback.** Nếu exception bị nuốt và handler trả về thành công, transaction có thể commit. Muốn abort, lỗi phải được truyền đến ranh giới transaction hoặc ứng dụng phải đánh dấu rollback theo cơ chế được hỗ trợ.

**Kafka transaction thay thế outbox.** Transaction Kafka không bao phủ database. Outbox giải quyết việc ghi dữ liệu nghiệp vụ và ý định phát sự kiện trong cùng database transaction.

## 16. Quy trình thiết kế giao dịch cho một luồng Spring Cloud Stream

1. Xác định input topic, output topic và consumer group của dịch vụ.
2. Xác định toàn bộ output record nào phải commit cùng offset input.
3. Bật transaction ở Kafka binder bằng transactionIdPrefix.
4. Cấp prefix duy nhất cho từng instance đang chạy.
5. Dùng cùng Kafka binder/cluster cho các output cần tham gia transaction.
6. Cấu hình consumer downstream dùng read_committed nếu chỉ xử lý record đã commit.
7. Đặt giới hạn thời gian xử lý phù hợp với transaction.timeout.ms và max.poll.interval.ms.
8. Thiết kế rollback, retry, recovery và DLQ cho message lỗi.
9. Đưa side effect database/API vào mẫu idempotency hoặc outbox phù hợp.
10. Kiểm thử cả commit, abort, redelivery, producer fencing và nhiều output.
11. Theo dõi transaction duration, abort rate, consumer lag và coordinator error.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream - Kafka Binder Transactions](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/transactional.html): bật transaction bằng transaction ID prefix và cách binder quản lý transaction.
- [Spring Cloud Stream - Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html): cấu hình Kafka binder, producer, consumer và binding.
- [Spring for Apache Kafka - Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): KafkaTransactionManager, transactional producer, transaction synchronization và fencing.
- [Apache Kafka - Design: Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-most-once, at-least-once và exactly-once trong Kafka.
- [Apache Kafka - Consumer Configurations](https://kafka.apache.org/40/configuration/consumer-configs/): isolation.level và read_committed.
