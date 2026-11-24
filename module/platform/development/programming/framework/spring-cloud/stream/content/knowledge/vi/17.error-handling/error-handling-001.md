# Phân loại lỗi chuyển đổi, lỗi nghiệp vụ và lỗi hạ tầng

Một message không xử lý được có thể xuất phát từ nhiều nguyên nhân: payload không thể chuyển đổi thành kiểu Java, dữ liệu vi phạm quy tắc nghiệp vụ, hoặc một dependency như database, API hay broker tạm thời không sẵn sàng. Ba nhóm lỗi này cần cách phản ứng khác nhau. Nếu retry một payload sai schema, lỗi sẽ lặp lại; nếu bỏ qua timeout của database, event có thể bị mất; nếu đưa một quyết định nghiệp vụ hợp lệ như “đơn hàng bị từ chối” vào DLQ, hệ thống sẽ làm sai ý nghĩa của quy trình.

Trong Spring Cloud Stream, việc phân loại bắt đầu từ nơi lỗi phát sinh và khả năng phục hồi của nguyên nhân. Hãy xác định lỗi xảy ra ở bước chuyển đổi message, trong quy tắc nghiệp vụ hay khi giao tiếp với hạ tầng; sau đó quyết định có retry, từ chối nghiệp vụ, cách ly dữ liệu hay chuyển message vào DLQ.

## 1. Ba nhóm lỗi và cách nhận diện

| Nhóm lỗi | Nguyên nhân điển hình | Có thể tự phục hồi? | Hướng xử lý mặc định |
|---|---|---|---|
| Chuyển đổi (conversion) | JSON sai cú pháp, kiểu dữ liệu không khớp, schema không tương thích, thiếu trường bắt buộc ở tầng deserialize | Thường không, nếu payload cố định bị sai | Không retry lặp; cách ly/DLQ và điều tra contract |
| Nghiệp vụ (business) | Đơn hàng không đủ điều kiện, trạng thái không cho phép, vượt hạn mức, khách hàng không hợp lệ | Không tự phục hồi chỉ bằng retry | Trả kết quả từ chối hoặc phát event nghiệp vụ tương ứng |
| Hạ tầng (infrastructure) | Timeout, mất kết nối, broker/API/database quá tải, HTTP 5xx hoặc throttling | Thường có thể, tùy lỗi | Retry có giới hạn, backoff, circuit breaker; sau đó phục hồi/DLQ |

Không phân loại chỉ dựa trên tên exception. Cùng một exception tổng quát như `IllegalStateException` có thể được ném do lỗi lập trình, dữ liệu nghiệp vụ hoặc trạng thái dependency. Hãy tạo exception riêng theo ngữ nghĩa và giữ nguyên nguyên nhân gốc để log, metric và retry policy có thể đưa ra quyết định đúng.

### Một cây quyết định đơn giản

~~~text
Message không xử lý được
          |
          v
Có đọc/giải mã được payload?
    | Không
    +------> Lỗi chuyển đổi
    |          -> kiểm tra content-type/schema
    |          -> cách ly/DLQ, không retry vô ích
    |
    | Có
    v
Dữ liệu có vi phạm quy tắc nghiệp vụ?
    | Có
    +------> Lỗi nghiệp vụ
    |          -> kết quả từ chối / event rejected
    |          -> không retry như lỗi hạ tầng
    |
    | Không
    v
Dependency hoặc broker có lỗi tạm thời?
    | Có
    +------> Lỗi hạ tầng
    |          -> retry có giới hạn và backoff
    |          -> DLQ/alert nếu hết lần thử
    |
    | Không
    +------> Lỗi lập trình hoặc lỗi chưa phân loại
               -> ghi nhận, điều tra và xử lý rõ ràng
~~~

## 2. Lỗi chuyển đổi: message không khớp kiểu dữ liệu

Spring Cloud Stream nhận message từ binder rồi dùng message converter để chuyển payload thành kiểu mà function hoặc consumer khai báo. Lỗi có thể xảy ra trước khi function được gọi, ví dụ:

- Producer gửi JSON không hợp lệ hoặc payload bị cắt.
- Header `content-type` khai báo sai định dạng.
- Trường JSON có kiểu khác với DTO, ví dụ chuỗi được gửi vào trường số.
- Schema producer và consumer không tương thích.
- Consumer yêu cầu trường bắt buộc nhưng message cũ không có trường đó.
- Deserializer không thể đọc byte payload hoặc schema ID không tồn tại.

Ví dụ consumer khai báo DTO:

~~~java
import java.math.BigDecimal;

public record OrderCreated(
    String orderId,
    String customerId,
    BigDecimal total
) {}
~~~

Message phù hợp:

~~~json
{
  "orderId": "ord-1001",
  "customerId": "cus-2001",
  "total": 125000.00
}
~~~

Message lỗi kiểu:

~~~json
{
  "orderId": "ord-1001",
  "customerId": "cus-2001",
  "total": "one hundred"
}
~~~

Nếu converter không thể chuyển `total` thành `BigDecimal`, function có thể chưa được gọi. Vì vậy, đặt `try/catch` bên trong function không bắt được mọi lỗi chuyển đổi. Cần kiểm tra log/error handling của binding và cấu hình converter/schema ở ranh giới nhận message.

### Phân biệt lỗi chuyển đổi với validation

Payload có thể chuyển đổi thành DTO thành công nhưng vẫn không hợp lệ về nghiệp vụ. Ví dụ `total = -100` là số hợp lệ về kiểu `BigDecimal`, nhưng không hợp lệ theo quy tắc đơn hàng. Trường hợp này thuộc validation/nghiệp vụ, không phải lỗi deserialize.

Ngược lại, `total = "abc"` không thể chuyển thành số và là lỗi chuyển đổi. Sự phân biệt này quan trọng vì lỗi chuyển đổi thường được xử lý trước khi business handler chạy, trong khi lỗi nghiệp vụ cần một phản hồi có ý nghĩa cho quy trình.

### Cách xử lý lỗi chuyển đổi

1. Kiểm tra payload thô và header `content-type` từ producer.
2. Đối chiếu schema hoặc DTO contract của hai phía.
3. Xác định lỗi có phải do message cũ hợp lệ theo phiên bản schema trước hay không.
4. Cách ly message lỗi, giữ thông tin nguồn, offset/message ID và lý do lỗi.
5. Sửa producer, converter hoặc schema rồi replay có kiểm soát.

Không retry vô hạn một payload JSON sai cú pháp. Nếu cùng một byte payload được gửi lại, kết quả chuyển đổi thường vẫn thất bại. Retry chỉ có ý nghĩa khi lỗi chuyển đổi thực chất đến từ một dependency tạm thời, chẳng hạn schema registry tạm thời không truy cập được; lúc đó nguyên nhân là lỗi hạ tầng khi tra cứu schema, không phải payload sai.

## 3. Lỗi nghiệp vụ: dữ liệu hợp lệ về cấu trúc nhưng không được chấp nhận

Lỗi nghiệp vụ xảy ra khi ứng dụng hiểu được message nhưng quy tắc nghiệp vụ không cho phép thực hiện hành động. Ví dụ:

- Đơn hàng có tổng tiền bằng 0 hoặc âm.
- Trạng thái đơn hàng không cho phép xác nhận.
- Hạn mức tín dụng đã bị vượt.
- Kho không đủ số lượng để chấp nhận yêu cầu.
- Mã khách hàng không tồn tại trong miền nghiệp vụ.

Không phải mọi kết quả nghiệp vụ không thành công đều là exception. Nếu từ chối là kết quả dự kiến của quy trình, có thể biểu diễn bằng một kiểu kết quả rõ ràng hoặc phát event như `OrderRejected`. Dùng exception cho lỗi bất thường hoặc để tích hợp với error handling khi cần, nhưng không biến mọi quyết định nghiệp vụ thành lỗi kỹ thuật.

Ví dụ phân biệt kết quả:

~~~java
public sealed interface OrderDecision
    permits OrderAccepted, OrderRejected {}

public record OrderAccepted(String orderId)
    implements OrderDecision {}

public record OrderRejected(
    String orderId,
    String reasonCode
) implements OrderDecision {}
~~~

Function có thể trả về một trong hai kết quả:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderDecisionFunctions {

    @Bean
    Function<OrderCommand, OrderDecision> decideOrder() {
        return command -> {
            if (command.total().signum() <= 0) {
                return new OrderRejected(
                    command.orderId(),
                    "TOTAL_MUST_BE_POSITIVE"
                );
            }

            return new OrderAccepted(command.orderId());
        };
    }

    public record OrderCommand(
        String orderId,
        java.math.BigDecimal total
    ) {}
}
~~~

Đặt `OrderDecision`, `OrderAccepted`, `OrderRejected` và `OrderDecisionFunctions` trong các file Java riêng cùng package (mỗi kiểu `public` top-level nằm trong file cùng tên). Trong ví dụ, `OrderCommand` là record lồng bên trong `OrderDecisionFunctions`.

Kết quả từ chối vẫn là một kết quả xử lý bình thường. Có thể route `OrderAccepted` và `OrderRejected` sang các output hoặc consumer tương ứng bằng logic ứng dụng. Không retry một yêu cầu có tổng tiền âm nếu dữ liệu không thay đổi; retry chỉ lặp lại cùng quyết định.

### Khi nào dùng exception cho lỗi nghiệp vụ?

Một số lỗi nghiệp vụ cần dừng handler và được chuyển tới luồng xử lý riêng, ví dụ dữ liệu tham chiếu không tồn tại do thứ tự event chưa đồng bộ. Cần phân biệt:

- **Từ chối cuối cùng:** quy tắc không thể thay đổi bằng cách thử lại; trả kết quả rejected.
- **Chưa thể quyết định:** dữ liệu phụ thuộc chưa đến hoặc trạng thái đang được cập nhật; có thể retry có giới hạn, trì hoãn hoặc đưa vào luồng chờ.
- **Vi phạm hợp đồng:** producer gửi trạng thái không thể xảy ra; ghi nhận và cách ly để điều tra.

Không gọi tất cả trường hợp trên là “business exception” rồi áp dụng cùng một chính sách. Mã lý do và khả năng phục hồi cần được thể hiện rõ.

## 4. Lỗi hạ tầng: dependency tạm thời không sẵn sàng

Lỗi hạ tầng thường xảy ra khi function đã nhận payload hợp lệ nhưng không thể hoàn thành thao tác do dependency:

- Database timeout, connection pool cạn hoặc failover.
- API đối tác trả HTTP 429, 502, 503 hoặc 504.
- DNS, TLS hoặc kết nối mạng gặp sự cố.
- Broker tạm thời không khả dụng hoặc từ chối publish.
- Dịch vụ schema registry không truy cập được.
- Hệ thống lưu trữ bị quá tải.

Ví dụ service lưu đơn hàng:

~~~java
public class OrderPersistenceService {

    private final OrderRepository repository;

    public OrderPersistenceService(OrderRepository repository) {
        this.repository = repository;
    }

    public void save(OrderCreated event) {
        try {
            repository.save(toEntity(event));
        } catch (org.springframework.dao.TransientDataAccessException ex) {
            throw new TransientDependencyException(
                "Temporary database failure while saving order",
                ex
            );
        }
    }

    private OrderEntity toEntity(OrderCreated event) {
        return new OrderEntity(event.orderId(), event.total());
    }
}
~~~

Chỉ bọc những lỗi đã xác định là tạm thời. Không biến mọi `DataAccessException` thành lỗi retryable: lỗi constraint, SQL sai hoặc dữ liệu không hợp lệ có thể là lỗi vĩnh viễn. Phân loại dựa trên exception cụ thể của driver/framework và nguyên nhân gốc.

Với HTTP, timeout hoặc 5xx thường có thể retry; 429 cần tôn trọng `Retry-After` nếu có; 400 do payload sai thường không nên retry; 401/403 thường cần sửa credential hoặc quyền. Mỗi API có thể có semantics riêng, nên cần kiểm tra hợp đồng của dependency.

## 5. Định nghĩa exception theo khả năng phục hồi

Một quy ước exception rõ ràng giúp retry policy dễ đọc:

~~~java
public class InvalidEventException extends RuntimeException {
    public InvalidEventException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class BusinessRuleViolationException extends RuntimeException {
    public BusinessRuleViolationException(String message) {
        super(message);
    }
}

public class TransientDependencyException extends RuntimeException {
    public TransientDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class PermanentDependencyException extends RuntimeException {
    public PermanentDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đặt mỗi exception `public` trong một file Java riêng cùng package. Dùng thống nhất `TransientDependencyException` cho lỗi dependency có thể phục hồi; tên lớp này cũng được tham chiếu trong cấu hình retry ở phần tiếp theo.

Tên exception nên mô tả nguyên nhân và khả năng phục hồi, không chỉ là tầng kỹ thuật. Ví dụ `TransientDependencyException` cho biết có thể thử lại; `InvalidEventException` cho biết payload cần sửa hoặc cách ly; `BusinessRuleViolationException` cho biết quy tắc nghiệp vụ đã từ chối.

Giữ nguyên cause để log và điều tra. Không chỉ ném `new RuntimeException("failed")` vì sẽ mất thông tin về HTTP status, SQL state, converter hoặc broker exception ban đầu.

## 6. Thiết lập retry theo loại lỗi trong Spring Cloud Stream

Spring Cloud Stream hỗ trợ retry cho consumer binding. Có thể giới hạn số lần thử và cấu hình backoff:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
            default-retryable: false
            retryable-exceptions:
              com.example.TransientDependencyException: true
              com.example.InvalidEventException: false
              com.example.BusinessRuleViolationException: false
              com.example.PermanentDependencyException: false
~~~

Ý nghĩa:

- `max-attempts: 4` là tổng số lần xử lý tối đa, bao gồm lần đầu.
- `back-off-initial-interval` là khoảng chờ ban đầu.
- `back-off-max-interval` giới hạn thời gian chờ giữa các lần thử.
- `back-off-multiplier` điều chỉnh mức tăng thời gian chờ.
- `default-retryable: false` yêu cầu chỉ retry các exception được khai báo rõ.
- `retryable-exceptions` ánh xạ tên lớp exception tới quyết định retry.

Cấu hình này là ví dụ cho consumer binding dùng cơ chế retry của Spring Cloud Stream. Kiểm tra property và semantics theo phiên bản Spring Cloud Stream/binder đang triển khai. Với reactive function, retry có thể cần đặt ở Reactor pipeline và ranh giới retry của binding có thể khác; không mặc định cấu hình imperative retry sẽ bao phủ mọi lỗi reactive.

### Chọn backoff và giới hạn

Retry quá nhanh có thể tạo retry storm: nhiều consumer cùng gọi lại dependency đang quá tải, khiến dịch vụ càng khó phục hồi. Backoff tăng dần và jitter giúp phân tán thời điểm retry. Nếu dependency trả `Retry-After`, hãy cân nhắc tuân thủ hướng dẫn đó.

Đặt tổng thời gian retry phù hợp với timeout nghiệp vụ và thời gian message có thể chờ. Sau số lần thử tối đa, cần một hành động rõ ràng: DLQ, quarantine, alert hoặc quy trình xử lý thủ công. Không retry vô hạn trong thread consumer vì có thể giữ partition/queue và làm các message khác bị chặn.

## 7. Lỗi ở producer, function và consumer có đường đi khác nhau

Một ứng dụng Spring Cloud Stream có thể gặp lỗi tại nhiều ranh giới:

| Vị trí | Ví dụ | Cần quan sát |
|---|---|---|
| Producer tạo payload | Mapping hoặc validation lỗi | Log ứng dụng, metric tạo event |
| Producer gửi binding | Broker không nhận publish | Kết quả send/confirm, binder error |
| Consumer chuyển đổi | JSON/schema không đọc được | Converter/deserializer, error channel/binder log |
| Function xử lý | Business handler hoặc dependency ném exception | Retry policy, error handling |
| Consumer commit/ack | Instance dừng trước khi xác nhận | Redelivery, offset, duplicate |
| Consumer phát output | Broker đích không khả dụng | Producer error của output binding |

Không dùng một error handler duy nhất để che giấu tất cả lỗi. Lỗi tạo event có thể cần rollback nghiệp vụ hoặc outbox; lỗi publish cần giữ event để gửi lại; lỗi deserialize cần cách ly payload; lỗi nghiệp vụ cần kết quả rejected; lỗi database tạm thời cần retry.

Đặc biệt, `StreamBridge.send(...)` trả về kết quả cho việc gửi vào binding/channel theo semantics của API và binder. Không nên xem giá trị trả về đó là bằng chứng chung rằng message đã được broker lưu bền vững và consumer đã xử lý. Nếu cần xác nhận publish, dùng cơ chế producer confirmation/acknowledgment của binder phù hợp và kiểm thử failure window.

## 8. Error channel và xử lý lỗi ở tầng Spring

Spring Integration và Spring Cloud Stream cung cấp cơ chế error message để lỗi phát sinh trong quá trình xử lý có thể được quan sát hoặc xử lý tại error channel. Error message thường chứa payload là exception và header tham chiếu message gốc, nếu có.

Một handler có thể ghi nhận lỗi và chuyển thông tin cần thiết tới hệ thống quan sát:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.stereotype.Component;

@Component
public class StreamErrorLogger {

    @ServiceActivator(inputChannel = "errorChannel")
    public void handle(Message<?> errorMessage) {
        Object payload = errorMessage.getPayload();

        if (payload instanceof MessagingException exception) {
            Throwable cause = exception.getCause();

            // Ghi log cause, message gốc và binding context.
            // Không log toàn bộ payload nếu có dữ liệu nhạy cảm.
        }
    }
}
~~~

Ví dụ trên minh họa cách nhận error message ở global Spring Integration error channel. Nó không thay thế retry, DLQ hoặc error handling riêng của binder. Một số lỗi xảy ra trước khi message được chuyển vào function, lỗi producer và lỗi reactive có đường xử lý khác nhau. Cần xác định channel thực tế của binding theo cấu hình và phiên bản trước khi triển khai handler.

Không nuốt exception sau khi ghi log nếu message chưa được xử lý hoặc lưu bền vững. Nếu handler trả về bình thường nhưng không có hành động phục hồi, framework có thể coi lỗi đã được xử lý trong khi event bị mất khỏi luồng xử lý dự kiến.

## 9. DLQ và quarantine dành cho message không thể xử lý

Dead Letter Queue/Topic giữ message đã hết số lần retry hoặc không thể xử lý theo chính sách. Quarantine có thể dùng cho payload sai contract hoặc dữ liệu cần điều tra. Chúng có mục đích gần nhau nhưng không hoàn toàn đồng nhất:

- DLQ thường là cơ chế gắn với broker/binder và consumer failure.
- Quarantine là vùng lưu dữ liệu lỗi theo quy trình ứng dụng, có thể giữ cả payload thô và chẩn đoán.
- Rejected event là kết quả nghiệp vụ; nó không nhất thiết là message lỗi.

Với Kafka binder, DLQ cần consumer group rõ ràng và cấu hình riêng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor

      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
~~~

Với RabbitMQ binder, có thể bật tự động bind DLQ:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
~~~

Tên property, routing key, quyền tạo queue/topic và chính sách dead-letter phụ thuộc binder version. Với Pulsar, cấu hình dead-letter policy theo extended consumer properties và semantics của Pulsar subscription; không sao chép thuộc tính Kafka/RabbitMQ sang Pulsar.

Message trong DLQ cần giữ đủ metadata để điều tra: event ID, source/destination gốc, group/subscription, thời điểm, số lần giao lại, exception class và nguyên nhân. Không ghi bí mật hoặc toàn bộ dữ liệu nhạy cảm vào log lỗi.

### Quy trình xử lý DLQ

1. Đếm và cảnh báo khi DLQ có message mới hoặc tuổi message cũ nhất vượt ngưỡng.
2. Phân loại lỗi: conversion, business hay infrastructure.
3. Xác định nguyên nhân gốc và phạm vi ảnh hưởng.
4. Sửa schema, dữ liệu, code hoặc dependency.
5. Chọn replay, sửa dữ liệu rồi replay, phát event bù hoặc giữ lại nếu không thể xử lý.
6. Replay với event ID ổn định và consumer idempotent.
7. Xác nhận backlog DLQ giảm và event được xử lý thành công.

Không tự động replay toàn bộ DLQ liên tục. Nếu nguyên nhân chưa được sửa, replay chỉ tạo thêm lỗi và có thể gây quá tải.

## 10. Reactive function: phân loại lỗi trong pipeline

Với reactive function, lỗi có thể xuất hiện trong một toán tử hoặc publisher con. Cần phân biệt lỗi của một phần tử với lỗi làm kết thúc cả publisher.

Ví dụ gọi dịch vụ tham chiếu:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class ReactiveOrderFunctions {

    @Bean
    Function<Flux<OrderCreated>, Flux<OrderDecision>> processOrders(
            CustomerClient client) {

        return orders -> orders.flatMap(order ->
            client.findCustomer(order.customerId())
                .map(customer -> validate(order, customer))
                .switchIfEmpty(Mono.just(
                    new OrderRejected(
                        order.orderId(),
                        "CUSTOMER_NOT_FOUND"
                    )
                ))
                .onErrorMap(
                    TimeoutException.class,
                    ex -> new TransientDependencyException(
                        "Customer lookup timed out",
                        ex
                    )
                )
        );
    }

    private OrderDecision validate(
            OrderCreated order,
            Customer customer) {
        if (order.total().signum() <= 0) {
            return new OrderRejected(
                order.orderId(),
                "INVALID_TOTAL"
            );
        }
        return new OrderAccepted(order.orderId());
    }

    public interface CustomerClient {
        Mono<Customer> findCustomer(String customerId);
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        java.math.BigDecimal total
    ) {}

    public record Customer(String customerId) {}

    public sealed interface OrderDecision
        permits OrderAccepted, OrderRejected {}

    public record OrderAccepted(String orderId)
        implements OrderDecision {}

    public record OrderRejected(String orderId, String reason)
        implements OrderDecision {}
}
~~~

Ví dụ dùng `flatMap` để mỗi event có publisher con riêng. Không tìm thấy khách hàng là kết quả nghiệp vụ được biểu diễn bằng `OrderRejected`; timeout được ánh xạ thành exception tạm thời. Trong code thật cần import `java.util.concurrent.TimeoutException` nếu client dùng exception đó, hoặc ánh xạ exception cụ thể của HTTP client.

Có thể dùng `retryWhen` cho lời gọi phụ thuộc tạm thời:

~~~java
return client.findCustomer(order.customerId())
    .retryWhen(
        reactor.util.retry.Retry.backoff(3, Duration.ofMillis(200))
            .filter(this::isTransient)
    );
~~~

Đặt retry quanh publisher con của thao tác cần thử lại, thay vì retry toàn bộ `Flux` nếu không muốn xử lý lại các event đã hoàn tất trước đó. Nếu publisher được subscribe lại, side effect bên trong có thể chạy lần nữa; chỉ retry thao tác idempotent hoặc dùng idempotency key.

Không chuyển mọi lỗi thành `Mono.empty()`. Làm vậy có thể biến timeout hoặc lỗi serialization thành “không tìm thấy dữ liệu”, che giấu sự cố và tạo kết quả nghiệp vụ sai.

## 11. Kiểm thử theo từng nhóm lỗi

Kiểm thử cần chứng minh lỗi được phân loại và xử lý đúng, không chỉ chứng minh exception được ném ra.

| Kịch bản | Nhóm lỗi | Kết quả cần xác nhận |
|---|---|---|
| JSON sai cú pháp | Chuyển đổi | Function không được gọi; message được quan sát/cách ly theo binder |
| Trường total là chuỗi không chuyển được | Chuyển đổi | Không retry vô ích; lưu chẩn đoán contract |
| total âm | Nghiệp vụ | Trả rejected hoặc xử lý theo business policy |
| Khách hàng không tồn tại | Nghiệp vụ | Kết quả từ chối hoặc chờ theo quy tắc rõ ràng |
| Database timeout | Hạ tầng | Retry có giới hạn, backoff và cuối cùng phục hồi/DLQ |
| API trả 429 | Hạ tầng/throttling | Tôn trọng Retry-After hoặc giảm tốc |
| Sai credential | Hạ tầng/cấu hình | Không retry dày đặc; cảnh báo vận hành |
| Broker mất kết nối khi publish | Hạ tầng | Publish failure được quan sát; event có thể phát lại |
| Consumer dừng trước ack/commit | Giao nhận | Redelivery không lặp side effect nhờ idempotency |

Unit test cho business rule:

~~~java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class OrderDecisionFunctionsTest {

    @Test
    void rejectsNonPositiveTotal() {
        OrderDecisionFunctions functions =
            new OrderDecisionFunctions();

        OrderDecision result = functions.decideOrder().apply(
            new OrderDecisionFunctions.OrderCommand(
                "ord-1001",
                new BigDecimal("-1")
            )
        );

        assertInstanceOf(OrderRejected.class, result);
    }
}
~~~

Test binder giúp kiểm tra function, binding và error flow trong ứng dụng mà không cần broker thật. Tuy nhiên, cần integration test riêng với Kafka, RabbitMQ hoặc Pulsar để xác nhận retry, acknowledgment, DLQ, redelivery và serialization theo đúng binder.

Với lỗi conversion, hãy gửi payload thô sai schema qua broker thật hoặc test adapter tương ứng. Một unit test gọi trực tiếp function không thể kiểm tra lỗi xảy ra trước khi function được gọi.

## 12. Quan sát và cảnh báo lỗi trong production

Mỗi nhóm lỗi cần metric riêng để đội vận hành biết phải hành động ở đâu:

| Metric/log field | Mục đích |
|---|---|
| `conversion_error_total` | Phát hiện producer/consumer contract không khớp |
| `business_rejection_total` | Theo dõi số lượng quyết định từ chối theo reason code |
| `infrastructure_error_total` | Theo dõi lỗi dependency và broker |
| `retry_attempt_total` | Phát hiện dependency chập chờn hoặc retry storm |
| `dlq_message_count` | Theo dõi message không xử lý được |
| `oldest_dlq_message_age` | Xác định lỗi tồn đọng lâu |
| `consumer_lag` / queue backlog | Theo dõi khả năng bắt kịp dữ liệu |
| `eventId`, `correlationId`, `causationId` | Tra cứu một event và hành trình nghiệp vụ trong log/trace |

Dùng reason code có số lượng hữu hạn cho metric label; không dùng event ID, order ID hoặc customer ID làm label vì cardinality rất lớn. ID chi tiết nên được ghi trong log có cấu trúc và trace. Khi log lỗi, ghi exception class, cause, binding, group, destination và event ID nếu có; tránh log token, password hoặc payload nhạy cảm.

Cảnh báo nên phản ánh điều cần hành động: conversion error tăng đột biến, business rejection vượt ngưỡng, infrastructure error kéo dài, retry liên tục, DLQ có message hoặc consumer lag tăng. Một số business rejection là kết quả bình thường; cần đặt ngưỡng theo nghiệp vụ thay vì cảnh báo mọi lần từ chối.

## 13. Nguyên tắc chọn chính sách xử lý

| Câu hỏi | Nếu câu trả lời là “có” | Chính sách gợi ý |
|---|---|---|
| Cùng payload và cùng code chạy lại có tiếp tục lỗi không? | Có | Không retry; cách ly hoặc từ chối |
| Người dùng có thể sửa dữ liệu để yêu cầu lại không? | Có | Trả kết quả rejected có reason code |
| Dependency có thể tự phục hồi trong thời gian ngắn không? | Có | Retry hữu hạn, backoff và jitter |
| Không biết publish đã thành công hay chưa? | Có | Giữ event ID, kiểm tra confirmation và chống trùng |
| Message đã hết retry nhưng chưa xử lý được? | Có | DLQ/quarantine, alert và replay có kiểm soát |
| Lỗi chưa xác định được nhóm? | Có | Ghi nhận nguyên nhân gốc, không tự động bỏ qua |

Một chính sách tốt phải trả lời được bốn điều: message có được thử lại không, tối đa bao nhiêu lần, sau cùng được lưu ở đâu, và ai chịu trách nhiệm phục hồi. Nếu thiếu một trong các câu trả lời đó, lỗi có thể biến thành mất dữ liệu hoặc backlog không được xử lý.

## 14. Trình tự thực hành và tiêu chí hoàn thành

Tạo consumer `processOrder` nhận event từ `orders.created` và thực hiện các thử nghiệm:

1. Gửi JSON hợp lệ để xác nhận đường xử lý bình thường.
2. Gửi JSON sai cú pháp và JSON sai kiểu trường để quan sát conversion error.
3. Gửi payload đúng cấu trúc nhưng total âm để xác nhận business rejection.
4. Làm Customer API timeout để tạo transient infrastructure error.
5. Cấu hình retry có giới hạn và backoff; xác nhận chỉ lỗi tạm thời được retry.
6. Làm dependency không khả dụng quá số lần thử để xác nhận message được chuyển tới DLQ hoặc quy trình phục hồi.
7. Gửi message có credential sai hoặc destination thiếu quyền để xác nhận lỗi cấu hình không retry dày đặc.
8. Dừng consumer trước ack/commit để quan sát redelivery.
9. Replay một message đã sửa và xác nhận idempotency không lặp side effect.
10. Theo dõi metric riêng cho conversion, rejection, infrastructure, retry và DLQ.

Hoàn thành bài khi có thể xác định lỗi xảy ra ở bước nào; phân biệt payload không thể giải mã với dữ liệu bị từ chối theo nghiệp vụ; phân biệt cả hai với dependency tạm thời; và cấu hình được retry, DLQ, quarantine, logging cùng kiểm thử tương ứng cho từng loại.

## 15. Tài liệu tham khảo chính thức

- [Spring Cloud Stream — Error handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html) — error channel, retry và xử lý lỗi trong stream.
- [Spring Cloud Stream — Consumer properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — cấu hình retry của consumer binding.
- [Spring Cloud Stream — Kafka binder DLQ](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html) — dead-letter topic của Kafka binder.
- [Spring Cloud Stream — RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html) — retry, republish và dead-letter queue của Rabbit binder.
- [Spring Cloud Stream — Pulsar binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — consumer properties và dead-letter policy của Pulsar.
- [Spring Messaging — Message conversion](https://docs.spring.io/spring-framework/reference/integration/spring-integration/message.html) — message abstraction, payload và headers.
- [Project Reactor — Error handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — xử lý tín hiệu lỗi trong reactive pipeline.

