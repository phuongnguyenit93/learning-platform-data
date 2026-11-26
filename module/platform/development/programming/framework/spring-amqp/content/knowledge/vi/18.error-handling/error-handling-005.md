# ConditionalRejectingErrorHandler và FatalExceptionStrategy

Một consumer RabbitMQ nhận message JSON nhưng không thể chuyển thành Java object vì JSON sai định dạng. Phương thức `@RabbitListener` **chưa kịp chạy**, vậy ai quyết định message đó phải được giao lại, bị loại hay chuyển sang dead-letter queue (DLQ)? Nếu cứ requeue, consumer sẽ nhận lại cùng dữ liệu sai và thất bại mãi.

Trong **Spring AMQP**, `ConditionalRejectingErrorHandler` là một error handler ở **tầng listener container**. Nó hỏi một **`FatalExceptionStrategy`** xem exception có phải lỗi *fatal* hay không. Khi được phân loại fatal, handler thường chuyển lỗi thành `AmqpRejectAndDontRequeueException` để container **reject delivery và không requeue**; nếu queue được cấu hình dead-letter exchange (DLX), broker có thể đưa message sang DLQ.

Đó là cơ chế rất hữu ích, nhưng cần hiểu rõ giới hạn: **fatal không đồng nghĩa mọi exception**, **không requeue không có nghĩa message luôn đến DLQ**, và **error handler không bảo đảm nghiệp vụ đã commit**. Bài thuộc chương **Xử lý lỗi** của module **SPRING_AMQP**. Ta sẽ kết hợp `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, acknowledgment, retry, dead-letter, giao dịch và giám sát để thiết kế consumer đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định vị trí của `ConditionalRejectingErrorHandler` trong đường xử lý message từ RabbitMQ tới `@RabbitListener`.
2. Phân biệt lỗi xảy ra **trước khi gọi listener** (chẳng hạn conversion) với lỗi phát sinh **trong phương thức nghiệp vụ**.
3. Giải thích `FatalExceptionStrategy`, `DefaultExceptionStrategy`, `AmqpRejectAndDontRequeueException` và cách chúng ảnh hưởng requeue.
4. Hiểu tại sao lỗi fatal thường cần reject không requeue, trong khi lỗi hạ tầng tạm thời cần retry có giới hạn/backoff.
5. Cấu hình Spring Boot listener với error handler tùy biến, JSON converter, queue/DLX/DLQ và kiểm thử message lỗi.
6. Nhận biết các trường hợp đặc biệt với `x-death`, `MANUAL` acknowledgment và recovery của listener container.
7. Quan sát, khắc phục lỗi và thiết kế idempotency/outbox khi message có thể được giao lại.

## 2. Error handler nằm ở đâu trong đường xử lý?

Một đường xử lý điển hình:

~~~mermaid
flowchart TD
    P["Producer / RabbitTemplate"] --> X["Exchange + binding"]
    X --> Q["Queue RabbitMQ"]
    Q --> C["Listener container<br/>SMLC hoặc DMLC"]
    C --> V["Message conversion<br/>và argument binding"]
    V --> L["@RabbitListener<br/>nghiệp vụ"]
    V -->|"Exception trước khi gọi listener"| H["ConditionalRejectingErrorHandler"]
    L -->|"Exception trong listener"| H
    H --> S{"FatalExceptionStrategy<br/>isFatal(exception)?"}
    S -->|"fatal=true"| R["AmqpRejectAndDontRequeueException<br/>không requeue"]
    S -->|"fatal=false"| N["Giữ exception<br/>container áp chính sách reject/requeue"]
    R --> DX["DLX nếu queue cấu hình<br/>hoặc loại message"]
    N --> T["Retry/requeue/reject<br/>theo container và advice"]
~~~

**Lưu ý:** sơ đồ là mô hình khái niệm, không mô tả mọi nhánh nội bộ. Spring có thể dùng listener adapter, advice chain, error handler riêng tại phương thức và các exception được wrap nhiều lớp. Quyết định cuối về ACK/NACK còn phụ thuộc loại container, chế độ acknowledgment và cấu hình retry.

### Hai nơi xử lý lỗi dễ bị nhầm

| Cơ chế | Ở tầng nào? | Thường xử lý gì? |
|---|---|---|
| `ConditionalRejectingErrorHandler` | **Listener container** | Phân loại exception và chuyển fatal thành yêu cầu reject không requeue |
| `FatalExceptionStrategy` | **Chiến lược được container error handler gọi** | Xác định exception nào được coi là fatal |
| `@RabbitListener(errorHandler = "...")` / `RabbitListenerErrorHandler` | **Listener adapter/endpoint** | Xử lý lỗi ở cấp phương thức listener; tùy đường lỗi, không thay thế đầy đủ container error handler |
| Retry interceptor / advice chain | Bao quanh invocation theo cấu hình | Thử lại với số lần, backoff và recoverer tùy thiết kế |
| `basicNack` / `basicReject` | AMQP consumer acknowledgment | Quyết định requeue hoặc không requeue ở broker |
| DLX/DLQ | **Broker topology** | Nhận message đã bị dead-letter nếu route thành công |

**`ConditionalRejectingErrorHandler` không xử lý lỗi của `RabbitTemplate` ở producer** (chẳng hạn publish tới exchange không tồn tại). Producer cần publisher confirms/returns và chính sách lỗi riêng. Nó cũng không quyết định một message nằm trong queue nào; nhiệm vụ đó thuộc exchange, binding và DLX của RabbitMQ.

## 3. Vì sao cần phân loại fatal?

Xét ba tình huống:

1. Producer gửi bytes `{"eventId":`, JSON bị cắt dở. Nếu lần nào cũng đưa lại vào queue, lỗi deserialization sẽ lặp lại.
2. Producer gửi JSON hợp lệ, nhưng schema thiếu trường bắt buộc. Có thể handler vẫn được gọi và phát hiện dữ liệu không thể xử lý. Thử lại nguyên message thường không làm dữ liệu tự đúng.
3. Message hoàn toàn hợp lệ, nhưng database đang timeout. Dữ liệu không sai; thử lại **sau một khoảng delay** có thể thành công.

| Nhóm lỗi | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| **Fatal ở tầng hạ tầng listener** | JSON conversion exception, listener argument conversion/type mismatch | Reject không requeue; DLQ để điều tra hoặc sửa/replay |
| **Fatal theo hợp đồng nghiệp vụ** | Phiên bản event không hỗ trợ, mã đơn không hợp lệ không thể sửa qua retry | Phân loại có chủ đích, reject không requeue hoặc ghi trạng thái nghiệp vụ phù hợp |
| **Lỗi tạm thời** | Database/network timeout, downstream trả 503 | Retry **có giới hạn và backoff**, rồi recovery/DLQ |
| **Kết quả chưa rõ** | DB đã commit nhưng channel mất trước ACK | Có thể redelivery; kiểm tra idempotency, không tự coi lỗi fatal |
| **Lỗi lập trình** | `NullPointerException` vì bug | Không mặc nhiên coi mọi bug là lỗi dữ liệu; cần phân loại, cảnh báo và chặn retry nóng |

Từ *fatal* ở đây là **cách chiến lược phân loại một exception trong đường nhận message**, không phải khẳng định quá trình JVM đã bị hủy hoặc toàn bộ broker gặp sự cố.

### Quyết định cuối phụ thuộc nhiều yếu tố

~~~text
Exception
   ├─ Error handler coi là fatal
   │    └─ AmqpRejectAndDontRequeueException
   │         └─ reject/nack requeue=false
   │              └─ DLQ nếu DLX/binding hợp lệ; nếu không có thể mất
   │
   └─ Không fatal
        └─ container/retry advice xử lý tiếp
             ├─ có thể requeue nếu chính sách cho phép
             └─ có thể reject không requeue nếu cấu hình yêu cầu
~~~

Vì vậy, **`isFatal(exception)==false` không có nghĩa chắc chắn broker sẽ requeue**, và `isFatal(exception)==true` cũng không tự bảo đảm message tới DLQ. Phải kiểm tra toàn bộ đường xử lý.

## 4. `ConditionalRejectingErrorHandler` hoạt động như thế nào?

### 4.1. Cơ chế tổng quát

Trong các container Spring AMQP hiện đại, `ConditionalRejectingErrorHandler` thường là error handler mặc định. Khi nhận một exception từ đường xử lý listener, handler:

1. Ghi nhận thông tin lỗi theo mức log phù hợp.
2. Kiểm tra xem chuỗi nguyên nhân đã chứa `AmqpRejectAndDontRequeueException` hay chưa, tránh bọc lặp không cần thiết.
3. Gọi chiến lược `FatalExceptionStrategy.isFatal(Throwable)`.
4. Nếu được phân loại fatal, tạo hoặc lan truyền tín hiệu **không requeue** đến container.
5. Nếu không fatal, cho container/retry infrastructure xử lý exception theo chính sách hiện hành.

Ở API Java, có thể hình dung:

~~~java
// Mô hình ý tưởng, KHÔNG phải toàn bộ mã nguồn thư viện:
if (exceptionStrategy.isFatal(exception)) {
    throw new AmqpRejectAndDontRequeueException(
            "Fatal listener exception", exception);
}
// Trường hợp khác được xử lý theo container configuration.
~~~

Thực tế còn có xử lý đặc biệt với header `x-death`, acknowledgment mode, exception chain và các cấu hình của phiên bản thư viện. Đừng dùng đoạn pseudocode này thay cho hạ tầng Spring.

### 4.2. Những exception thường được chiến lược mặc định coi là fatal

`ConditionalRejectingErrorHandler.DefaultExceptionStrategy` chủ yếu nhận diện một nhóm lỗi **không có khả năng tự được sửa chỉ bằng requeue cùng message**:

| Exception/nhóm lỗi | Thời điểm hay gặp | Vì sao thường fatal? |
|---|---|---|
| `org.springframework.amqp.support.converter.MessageConversionException` | Chuyển AMQP body sang dữ liệu ứng dụng | Body không giải mã/convert theo định dạng mong đợi |
| `org.springframework.messaging.converter.MessageConversionException` | Chuyển payload ở tầng Spring Messaging | Không thể chuyển nội dung vào dạng tham số listener |
| `org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException` | Kiểm tra/validate tham số listener | Dữ liệu không đáp ứng ràng buộc |
| `org.springframework.messaging.handler.annotation.support.MethodArgumentTypeMismatchException` | Ràng buộc kiểu tham số | Kiểu dữ liệu không hợp lệ |
| `NoSuchMethodException` | Tìm phương thức xử lý message | Không xác định được handler phù hợp |
| `ClassCastException` | Lỗi chuyển kiểu trong đường dispatch | Không thể thực hiện lời gọi theo kiểu mong đợi |

Danh sách trên phản ánh các nhóm fatal thường được tài liệu Spring AMQP mô tả cho `DefaultExceptionStrategy`; phiên bản cụ thể có thể có thay đổi. Chiến lược kiểm tra **exception và nguyên nhân bên trong**, không chỉ tên lớp của exception ngoài cùng.

**Đừng mặc định `IllegalArgumentException`, `IOException` hoặc mọi `RuntimeException` đều fatal theo chiến lược mặc định.** Nếu ứng dụng muốn một loại lỗi nghiệp vụ cụ thể là fatal, cần mô tả rõ điều đó trong chiến lược tùy chỉnh hoặc chủ động ném `AmqpRejectAndDontRequeueException`.

### 4.3. Lỗi conversion có thể xảy ra trước khi phương thức listener chạy

Ví dụ:

~~~java
@RabbitListener(queues = "orders.work")
public void receive(OrderCreatedEvent event) {
    // Nếu body không phải JSON hợp lệ, có thể không chạy tới dòng này.
    orderService.process(event);
}
~~~

Với JSON converter, Spring cần parse body và gán vào `OrderCreatedEvent` **trước** khi gọi `receive`. Nếu parse thất bại, `try/catch` đặt **bên trong** phương thức không thể bắt lỗi đó. Container error handler mới là nơi quan trọng để xử lý loại lỗi pre-listener như vậy.

## 5. `FatalExceptionStrategy` và mở rộng `DefaultExceptionStrategy`

`FatalExceptionStrategy` là giao diện dùng để hỏi: **exception đang xét có fatal hay không?** Việc implement trực tiếp toàn bộ `isFatal(Throwable)` là có thể, nhưng phải cẩn thận với exception wrapper (như `ListenerExecutionFailedException`) và những loại lỗi fatal mặc định.

Trong nhiều ứng dụng, cách an toàn hơn là **mở rộng `ConditionalRejectingErrorHandler.DefaultExceptionStrategy`**, giữ lại các phân loại có sẵn và bổ sung đúng lỗi nghiệp vụ bạn biết là không thể phục hồi bằng retry.

### 5.1. Định nghĩa exception nghiệp vụ

~~~java
public class InvalidOrderEventException extends RuntimeException {
    public InvalidOrderEventException(String message) {
        super(message);
    }
}
~~~

Exception này biểu thị **message sai hợp đồng dữ liệu** (ví dụ ID không hợp lệ), không dùng cho lỗi database/network tạm thời.

### 5.2. Mở rộng chiến lược mặc định

~~~java
import org.springframework.amqp.rabbit.listener.ConditionalRejectingErrorHandler;

public class OrderFatalExceptionStrategy extends
        ConditionalRejectingErrorHandler.DefaultExceptionStrategy {

    @Override
    protected boolean isUserCauseFatal(Throwable cause) {
        return cause instanceof InvalidOrderEventException
                || super.isUserCauseFatal(cause);
    }
}
~~~

Điểm cần nhớ:

- `isUserCauseFatal` là hook của `DefaultExceptionStrategy` trong các dòng Spring AMQP phù hợp. Nó giúp bổ sung **loại lỗi ứng dụng** mà vẫn giữ lại phân loại mặc định.
- Chỉ coi exception là fatal khi **retry nguyên event không thể biến nó thành hợp lệ**. Một lỗi đồng bộ hóa tạm thời hoặc dữ liệu phụ thuộc chưa đến không nhất thiết là fatal.
- Nếu dùng một chiến lược `FatalExceptionStrategy` tự viết hoàn toàn, phải tự xử lý wrapper và danh sách lỗi framework; nếu không, những lỗi conversion vốn fatal có thể vô tình bị coi là retryable.
- Xác minh API đúng phiên bản Spring AMQP của dự án. Không trộn class/import của các dòng thư viện khác nhau.

### 5.3. Hai phương án thay thế nhau

| Cách | Khi nào dùng | Đánh đổi |
|---|---|---|
| Mở rộng `DefaultExceptionStrategy` | Có một số exception nghiệp vụ cần thêm vào nhóm fatal | Giữ được xử lý fatal mặc định, ít code |
| Implement `FatalExceptionStrategy` trực tiếp | Có taxonomy phức tạp, muốn kiểm soát hoàn toàn | Phải xét đầy đủ chain of causes và lỗi conversion của framework |
| Ném `AmqpRejectAndDontRequeueException` trong handler | Mã nghiệp vụ biết chính xác trường hợp cần không requeue | Không giải quyết lỗi conversion xảy ra trước khi handler được gọi |
| Retry advice + recoverer | Muốn thử lại một lỗi tạm thời theo backoff/số lần | Cần cấu hình ranh giới retry, recovery và cách giữ dữ liệu không bị mất |

**Không nên gắn cả một kho exception tùy tiện vào nhóm fatal chỉ để “làm sạch queue”.** Việc đó có thể khiến message hợp lệ gặp sự cố DB nhất thời bị loại khỏi luồng xử lý mà không có retry cần thiết.

## 6. Những cấu hình dễ bị bỏ qua

### 6.1. `defaultRequeueRejected` không phải là `FatalExceptionStrategy`

Trong listener container, `defaultRequeueRejected` điều chỉnh chính sách requeue mặc định khi listener thất bại. Ví dụ trong Spring Boot:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        default-requeue-rejected: true
~~~

Với giá trị `true`, một exception thông thường chưa bị chuyển thành **không requeue** có thể khiến broker đưa message trở lại queue. Nhưng **`AmqpRejectAndDontRequeueException` có thể ghi đè quyết định này** để reject không requeue.

Nếu đặt `default-requeue-rejected: false`, **cả nhiều lỗi non-fatal cũng có thể bị reject không requeue**. Như vậy sẽ khó nhìn thấy sự khác biệt trong lab giữa “fatal theo strategy” và “không fatal”. Trong sản phẩm thật, không lấy `true` hoặc `false` làm giải pháp retry duy nhất: retry cần **giới hạn và backoff**.

### 6.2. `discardFatalsWithXDeath` và vòng lặp dead-letter

Khi một message đã từng được dead-letter, RabbitMQ có thể gắn lịch sử `x-death` vào headers. Nếu ứng dụng hoặc topology đưa message từ DLQ **trở lại queue gốc** mà vẫn giữ metadata này, rồi message tiếp tục gây một lỗi fatal, việc dead-letter qua lại có thể tạo vòng lặp.

`ConditionalRejectingErrorHandler` có lựa chọn **`discardFatalsWithXDeath`** (thường bật mặc định ở các phiên bản hiện đại): trong đường xử lý phù hợp, message **fatal và có header `x-death`** có thể được **bỏ qua/ACK để ngăn dead-letter lặp lại**, thay vì cứ đẩy nó qua lại không dứt.

**Hệ quả cần chú ý:** message đã quay về từ DLQ có thể **không được dead-letter thêm một lần nữa** nếu vẫn lỗi fatal và giữ `x-death`. Nếu quy trình replay cần giữ mọi message, phải thiết kế khu cách ly riêng, audit, replay có kiểm soát và lựa chọn cấu hình phù hợp. Không tùy tiện tắt cơ chế chặn vòng lặp khi chưa đánh giá topology.

~~~java
// Cấu hình khi có yêu cầu đặc biệt, không phải mặc định nên bật/tắt tùy ý.
ConditionalRejectingErrorHandler handler =
        new ConditionalRejectingErrorHandler(
                new OrderFatalExceptionStrategy());
// handler.setDiscardFatalsWithXDeath(false);
// Chỉ cân nhắc khi đã có cơ chế chặn dead-letter loop thay thế.
~~~

Header `x-death` là **lịch sử dead-letter**, không phải bộ đếm chính xác mọi lần `basicNack(..., requeue=true)`. Không sử dụng nó như idempotency key hoặc tự suy số lần retry ứng dụng từ đó.

### 6.3. `rejectManual` và lỗi trước `@RabbitListener`

Trong `AcknowledgeMode.MANUAL`, mã listener thông thường chịu trách nhiệm `basicAck`/`basicNack`. Nhưng nếu **JSON conversion thất bại trước khi phương thức chạy**, nó không có cơ hội ACK hoặc NACK.

Các phiên bản Spring AMQP hiện đại có cơ chế để `ConditionalRejectingErrorHandler` **reject cả message fatal trong manual mode**, qua lựa chọn `rejectManual` (thường mặc định là `true` trên các phiên bản hỗ trợ). Nếu đang dùng manual ack, phải kiểm tra phiên bản và cấu hình thực tế, tránh giả định mọi lỗi conversion sẽ được xử lý bởi một `catch` nằm trong listener.

~~~java
ConditionalRejectingErrorHandler handler =
        new ConditionalRejectingErrorHandler(
                new OrderFatalExceptionStrategy());
handler.setRejectManual(true);
~~~

**Không suy ra manual mode cho phép ACK hai lần.** Với các delivery mà listener **đã được gọi**, ứng dụng phải dùng channel/tag hiện tại và có đúng một quyết định xác nhận; không tự ACK nếu container đã xử lý fatal/reject ở đường lỗi trước khi vào listener.

## 7. Spring Boot lab: topology và cơ chế xử lý lỗi

Lab tiếp theo minh họa **cả lỗi conversion và lỗi nghiệp vụ được phân loại fatal**.

Chúng ta dùng:

- Direct exchange: `demo.error.events`.
- Queue công việc: `demo.error.work`.
- Routing key: `order.created`.
- Dead-letter exchange: `demo.error.dlx`.
- Dead-letter queue: `demo.error.dlq`.
- Consumer: `@RabbitListener` nhận DTO `OrderCreatedEvent`.
- JSON converter: chuyển UTF-8 JSON body sang record.
- Error handler: `ConditionalRejectingErrorHandler` với `OrderFatalExceptionStrategy`.

### 7.1. RabbitMQ và dependencies

Để chạy broker cục bộ:

~~~bash
docker run -d --name rabbitmq-error-handler-lab -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -e RABBITMQ_DEFAULT_USER=lab -e RABBITMQ_DEFAULT_PASS=lab123456 rabbitmq:4-management
~~~

Management: `http://localhost:15672`, tài khoản lab `lab/lab123456`. Dùng thông tin này **chỉ trong môi trường học tập**, không sử dụng trong production. Nếu đã có broker chiếm hai cổng này, dùng broker hiện tại hoặc đổi mapping.

Ví dụ dựa trên **Java 17+, Spring Boot 3.x / Spring AMQP 3.x** và Jackson 2:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>
</dependencies>
~~~

Các dependency trên cần nằm trong dự án Spring Boot có parent/BOM quản lý phiên bản. API cụ thể có thể thay đổi ở dòng Spring Boot/Spring AMQP mới dùng Jackson 3; chọn `MessageConverter` và Jackson imports phù hợp với phiên bản dự án đang dùng.

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: lab
    password: lab123456
    listener:
      type: simple
      simple:
        concurrency: 1
        max-concurrency: 1
        prefetch: 1
        acknowledge-mode: auto
        default-requeue-rejected: true
~~~

**`default-requeue-rejected: true` chỉ dùng để thể hiện rõ ý nghĩa của fatal strategy trong lab.** Không cố tình phát message gây exception non-fatal liên tục với cấu hình này, vì nó có thể tạo **vòng lặp requeue nóng**. Khi vận hành thật, cần bounded retry/backoff và recoverer.

### 7.2. Exchange, queue và DLX

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ErrorLabTopology {

    @Bean
    DirectExchange errorEventsExchange() {
        return new DirectExchange("demo.error.events", true, false);
    }

    @Bean
    DirectExchange errorDlx() {
        return new DirectExchange("demo.error.dlx", true, false);
    }

    @Bean
    Queue errorWorkQueue() {
        return QueueBuilder.durable("demo.error.work")
                .deadLetterExchange("demo.error.dlx")
                .deadLetterRoutingKey("order.invalid")
                .build();
    }

    @Bean
    Queue errorDlq() {
        return QueueBuilder.durable("demo.error.dlq").build();
    }

    @Bean
    Binding errorWorkBinding(Queue errorWorkQueue,
                             DirectExchange errorEventsExchange) {
        return BindingBuilder.bind(errorWorkQueue)
                .to(errorEventsExchange)
                .with("order.created");
    }

    @Bean
    Binding errorDeadBinding(Queue errorDlq,
                             DirectExchange errorDlx) {
        return BindingBuilder.bind(errorDlq)
                .to(errorDlx)
                .with("order.invalid");
    }
}
~~~

Spring Boot có thể tự cấu hình `RabbitAdmin` để khai báo các bean trên broker khi kết nối. Nếu một queue cùng tên đã tồn tại nhưng khác arguments, RabbitMQ có thể báo lỗi `PRECONDITION_FAILED - inequivalent arg`; không xóa queue có dữ liệu để sửa lỗi thiếu kiểm soát.

~~~mermaid
flowchart LR
    P["RabbitTemplate"] --> E["demo.error.events"]
    E -->|"order.created"| Q["demo.error.work"]
    Q --> C["@RabbitListener<br/>OrderCreatedEvent"]
    C -->|"Hợp lệ"| A["Container AUTO ACK"]
    C -->|"Fatal exception"| R["Reject, requeue=false"]
    R --> DX["demo.error.dlx"]
    DX -->|"order.invalid"| DLQ["demo.error.dlq"]
~~~

### 7.3. DTO và lỗi nghiệp vụ

~~~java
public record OrderCreatedEvent(
        int schemaVersion,
        String eventId,
        String orderId) {
}
~~~

Khi Jackson gặp JSON sai cú pháp, việc chuyển payload sang record có thể thất bại **trước khi vào listener**. Với JSON đúng cú pháp nhưng `orderId` bắt đầu bằng `BAD-`, chính listener ném `InvalidOrderEventException`.

~~~java
public class InvalidOrderEventException extends RuntimeException {
    public InvalidOrderEventException(String message) {
        super(message);
    }
}
~~~

Trong ứng dụng thật, cần validate đầy đủ `schemaVersion`, `eventId`, định dạng `orderId` và các trường bắt buộc. Một record với `String` có thể deserialize thành `null` nếu field bị thiếu; **deserialize thành công không chứng minh hợp đồng dữ liệu hợp lệ**.

### 7.4. Cấu hình JSON converter và error handler cho đúng factory

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.ConditionalRejectingErrorHandler;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ErrorLabListenerConfig {

    @Bean("errorOrdersFactory")
    SimpleRabbitListenerContainerFactory errorOrdersFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        // Kế thừa cài đặt Boot: connection, prefetch, ack mode, ...
        configurer.configure(factory, connectionFactory);

        // Chọn converter rõ ràng trên factory đang được dùng.
        factory.setMessageConverter(new Jackson2JsonMessageConverter());

        // Fatal = lỗi conversion mặc định + InvalidOrderEventException.
        ConditionalRejectingErrorHandler handler =
                new ConditionalRejectingErrorHandler(
                        new OrderFatalExceptionStrategy());

        factory.setErrorHandler(handler);
        return factory;
    }
}
~~~

Và lớp chiến lược đã giới thiệu ở mục 5:

~~~java
import org.springframework.amqp.rabbit.listener.ConditionalRejectingErrorHandler;

public class OrderFatalExceptionStrategy extends
        ConditionalRejectingErrorHandler.DefaultExceptionStrategy {

    @Override
    protected boolean isUserCauseFatal(Throwable cause) {
        return cause instanceof InvalidOrderEventException
                || super.isUserCauseFatal(cause);
    }
}
~~~

**Vì sao cấu hình riêng một factory?** Cách này cho phép kiểm tra chính xác listener nào dùng error handler này. Tạo một `@Bean` `ErrorHandler` đơn lẻ rồi giả định mọi container sẽ tự dùng nó là thiếu chắc chắn, đặc biệt khi ứng dụng có nhiều custom container factory. Trong ví dụ, handler được gắn **trực tiếp lên factory** và `@RabbitListener` phải chỉ định tên factory tương ứng.

Nếu dự án sử dụng Jackson 3, API converter có thể là `JacksonJsonMessageConverter` thay vì `Jackson2JsonMessageConverter`. Phải điều chỉnh tương ứng với thư viện được quản lý bởi dự án.

### 7.5. Listener xử lý dữ liệu hợp lệ và lỗi nghiệp vụ fatal

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ErrorLabOrderListener {
    private static final Logger log =
            LoggerFactory.getLogger(ErrorLabOrderListener.class);

    @RabbitListener(
            id = "errorLabOrderListener",
            queues = "demo.error.work",
            containerFactory = "errorOrdersFactory")
    public void receive(OrderCreatedEvent event) {

        // Nếu JSON malformed, Spring có thể thất bại trước khi gọi đây.
        log.info("LISTENER_INVOKED eventId={} orderId={}",
                event.eventId(), event.orderId());

        if (event.schemaVersion() != 1
                || event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()
                || event.orderId().startsWith("BAD-")) {
            throw new InvalidOrderEventException(
                    "Message không hợp lệ hoặc schema không hỗ trợ");
        }

        // Production: xử lý idempotent, commit DB, sau đó container AUTO ACK.
        log.info("PROCESSED eventId={}", event.eventId());
    }
}
~~~

Với cấu hình `AUTO`:

- Listener hoàn tất không exception → container ACK delivery.
- JSON malformed → lỗi conversion phát sinh, strategy mặc định thường coi fatal → reject không requeue.
- JSON hợp lệ nhưng `InvalidOrderEventException` → strategy tùy chỉnh coi fatal → reject không requeue.

Trong hai nhánh fatal, **DLQ có thể nhận message** nếu DLX và binding hợp lệ. Lưu ý rằng một message bị reject có thể không tới DLQ khi DLX chưa tồn tại, routing sai, thiếu quyền hoặc gặp lỗi vận hành broker; cần theo dõi kết quả thực tế.

### 7.6. Publisher tạo ba trường hợp kiểm thử

Để chủ động gửi **JSON bytes thật** và mô phỏng body sai cú pháp, dùng `RabbitTemplate.send` với `Message`/`MessageProperties`. Cách này tránh phụ thuộc vào converter phía producer khi tạo malformed JSON.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lab/error-handler")
public class ErrorLabPublisher {
    private final RabbitTemplate rabbitTemplate;
    private final ObjectMapper objectMapper;

    public ErrorLabPublisher(RabbitTemplate rabbitTemplate,
                             ObjectMapper objectMapper) {
        this.rabbitTemplate = rabbitTemplate;
        this.objectMapper = objectMapper;
    }

    @PostMapping("/send")
    public ResponseEntity<Map<String, String>> send(
            @RequestParam(defaultValue = "valid") String mode)
            throws JsonProcessingException {

        if (!mode.equals("valid")
                && !mode.equals("malformed")
                && !mode.equals("invalid")) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "mode must be valid/malformed/invalid"));
        }

        String eventId = UUID.randomUUID().toString();
        byte[] body;

        if (mode.equals("malformed")) {
            // Cố tình thiếu phần giá trị và dấu đóng JSON.
            body = "{\"schemaVersion\":1,\"eventId\":"
                    .getBytes(StandardCharsets.UTF_8);
        } else {
            String orderId = mode.equals("invalid")
                    ? "BAD-1002" : "ORD-1001";
            OrderCreatedEvent event =
                    new OrderCreatedEvent(1, eventId, orderId);
            body = objectMapper.writeValueAsBytes(event);
        }

        MessageProperties properties = new MessageProperties();
        properties.setMessageId(eventId);
        properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        properties.setContentEncoding("utf-8");
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setHeader("eventId", eventId);

        rabbitTemplate.send(
                "demo.error.events",
                "order.created",
                new Message(body, properties));

        return ResponseEntity.accepted()
                .body(Map.of("eventId", eventId, "mode", mode));
    }
}
~~~

HTTP `202 Accepted` chỉ cho biết ứng dụng đã thực hiện lời gọi gửi mà không phát hiện lỗi đồng bộ trong endpoint; **không chứng minh broker đã publisher-confirm ACK**, message đã route hay listener đã ACK. Bật publisher confirms/mandatory returns khi nghiệp vụ cần giám sát những bước đó. Trong lab, đừng tự động chạy các yêu cầu malformed liên tục vì chúng tạo nhiều message cho DLQ.

## 8. Thực nghiệm: lỗi nào đi đâu?

Khởi động RabbitMQ trước, sau đó Spring Boot. Đảm bảo ứng dụng có `@SpringBootApplication` quét đúng package chứa các cấu hình/DTO/controller/listener.

### 8.1. Message hợp lệ

~~~bash
curl -X POST "http://localhost:8080/lab/error-handler/send?mode=valid"
~~~

Kỳ vọng log tương tự:

~~~text
LISTENER_INVOKED eventId=... orderId=ORD-1001
PROCESSED eventId=...
~~~

Khi container ACK thành công, message không còn ở trạng thái Unacked; không có lý do để vào DLQ.

### 8.2. JSON bị hỏng trước khi gọi listener

~~~bash
curl -X POST "http://localhost:8080/lab/error-handler/send?mode=malformed"
~~~

Kỳ vọng:

- JSON converter gặp lỗi parse/convert.
- Log có thể chứa exception conversion và thông tin handler coi lỗi là fatal.
- **Không có dòng `LISTENER_INVOKED` cho event này**, vì lỗi xảy ra trước khi phương thức nhận DTO được gọi.
- Handler dẫn tới **reject không requeue**; với topology đúng, message xuất hiện ở `demo.error.dlq`.

Để xác định đúng event, dùng `messageId`/header `eventId` trong producer, log và message DLQ. Đừng dựa vào thứ tự log giữa các luồng hoặc các message khác nhau.

### 8.3. JSON hợp lệ, lỗi nghiệp vụ được định nghĩa là fatal

~~~bash
curl -X POST "http://localhost:8080/lab/error-handler/send?mode=invalid"
~~~

Kỳ vọng:

- DTO được converter tạo thành công.
- Listener **được gọi** và log `LISTENER_INVOKED` có `BAD-1002`.
- Listener ném `InvalidOrderEventException`.
- `OrderFatalExceptionStrategy` coi loại exception này là fatal; error handler chuyển thành reject không requeue.
- Message có thể sang `demo.error.dlq`.

Nếu thay bằng một exception non-fatal với `default-requeue-rejected: true` và không có retry/backoff, message có thể bị giao lại liên tục. **Không tạo thử nghiệm vòng lặp đó trên hệ thống có tải quan trọng**.

### 8.4. Ma trận quan sát

| Mode | Có vào `@RabbitListener` không? | Nguyên nhân lỗi | Quyết định kỳ vọng | Kết quả queue |
|---|---|---|---|---|
| `valid` | Có | Không lỗi | Container ACK | Không vào DLQ |
| `malformed` | **Không** | Jackson/message conversion | Fatal mặc định → reject không requeue | DLQ nếu routing đúng |
| `invalid` | Có | `InvalidOrderEventException` | Fatal tùy chỉnh → reject không requeue | DLQ nếu routing đúng |

Trên Windows PowerShell, dùng `curl.exe` thay cho alias `curl` nếu cần. Các trường kết quả trong bảng giả định chỉ có **một** listener consumer trên queue lab, broker/topology hoạt động và không có policy khác can thiệp.

## 9. Vì sao không dùng `default-requeue-rejected=false` thay chiến lược fatal?

Cấu hình `default-requeue-rejected: false` thực sự có thể làm nhiều exception được reject không requeue. Nhưng nó **không thay thế** công việc phân loại lỗi:

| Lựa chọn | Ưu điểm | Hạn chế |
|---|---|---|
| Chỉ đặt `default-requeue-rejected=false` | Dễ tránh requeue vòng lặp cho các lỗi không được xử lý | Cả lỗi DB/network tạm thời cũng dễ bị đẩy DLQ ngay nếu không có retry riêng |
| Dùng `ConditionalRejectingErrorHandler` mặc định | Phân loại nhiều lỗi pre-listener mà retry không có ích | Không biết hết lỗi nghiệp vụ của ứng dụng |
| Mở rộng `DefaultExceptionStrategy` | Bổ sung lỗi nghiệp vụ fatal nhưng giữ nhận diện conversion/type mismatch | Cần định nghĩa exception taxonomy rõ ràng |
| Retry interceptor có backoff + recoverer | Thử lại lỗi tạm thời có giới hạn trước khi xử lý cuối | Cần chọn đúng phạm vi exception, số lần, delay và recovery |

Thiết kế đáng tin cậy thường là **kết hợp phân loại fatal với chính sách retry/recovery có giới hạn**, không phải chọn một giá trị boolean rồi bỏ qua loại lỗi.

### Chính sách retry có giới hạn, mang tính gợi ý

~~~text
Nếu lỗi conversion hoặc sự kiện không hợp lệ:
    -> fatal, reject không requeue, DLQ/quarantine

Nếu lỗi mạng/DB tạm thời:
    -> retry hữu hạn, backoff
    -> nếu hết ngưỡng: recoverer, DLQ hoặc trạng thái chờ can thiệp

Nếu đã commit nghiệp vụ nhưng ACK thất lạc:
    -> redelivery có thể xảy ra
    -> kiểm tra eventId đã xử lý và ACK delivery mới
~~~

Một số phương án là Spring Retry advice chain, delay queue/TTL+DLX, delayed-message exchange (nếu có plugin phù hợp) hoặc ứng dụng điều phối retry. Chọn cơ chế dựa trên version broker, bảo đảm thứ tự, tải, observability và cách ngăn lặp.

**Không tự động retry lỗi conversion mãi**: cùng bytes JSON sai sẽ tiếp tục sai. Cũng không coi message vào DLQ là “đã xử lý nghiệp vụ thành công”; DLQ cần điều tra, sửa hoặc cơ chế replay an toàn.

## 10. Cần chú ý gì với `MANUAL` acknowledgment?

Trong `MANUAL`, listener sử dụng `com.rabbitmq.client.Channel` và `deliveryTag` của delivery:

~~~java
@RabbitListener(queues = "demo.error.work", ackMode = "MANUAL")
public void receive(Message message, Channel channel) throws IOException {
    long tag = message.getMessageProperties().getDeliveryTag();

    try {
        orderService.processIdempotently(message);
        channel.basicAck(tag, false);
    } catch (InvalidOrderEventException e) {
        channel.basicReject(tag, false);
    } catch (TemporaryProcessingException e) {
        // Chỉ minh họa. Production phải giới hạn retry/backoff.
        channel.basicNack(tag, false, true);
    }
}
~~~

**Đây là mẫu thuật toán thay thế**, không chạy đồng thời với listener `AUTO` của lab trên cùng queue. `orderService`, `TemporaryProcessingException` là các loại ứng dụng tự định nghĩa.

Với lỗi xảy ra **trong handler**, bạn có thể quyết định ACK/NACK chủ động. Nhưng với lỗi **conversion trước listener**, phương thức `receive` không chạy, nên cần container error handler xử lý delivery fatal; đây là lý do `rejectManual` quan trọng.

Không ACK bằng `deliveryTag` trên channel khác hoặc ACK hai lần. Tag có phạm vi **một channel**; ACK sai có thể làm RabbitMQ đóng channel vì `unknown delivery tag`. Nếu application đã tự reject/ACK, đừng để logic khác tiếp tục xác nhận cùng delivery.

## 11. `x-death`, DLQ replay và tình huống “message biến mất”

Một quy trình DLQ có thể như sau:

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer
    participant Q as Work queue
    participant C as Consumer
    participant D as DLQ
    P->>Q: Publish message không hợp lệ
    Q->>C: Deliver
    C-->>Q: Fatal → reject requeue=false
    Q->>D: Dead-letter (x-death metadata)
    Note over D: Nhân viên kiểm tra/sửa dữ liệu
    D->>Q: Replay message chưa sửa, vẫn giữ x-death
    Q->>C: Deliver lần nữa
    C-->>Q: Fatal + x-death → có thể bị discard theo cấu hình
~~~

Nếu sau replay người vận hành thấy message **không quay lại DLQ lần thứ hai**, kiểm tra:

1. Message có header `x-death` từ vòng dead-letter trước không?
2. `ConditionalRejectingErrorHandler` có đang bật `discardFatalsWithXDeath` không?
3. Exception ở lần nhận mới có tiếp tục được phân loại fatal không?
4. Broker đã chuyển message sang queue/vhost khác hay ứng dụng đã ACK nó chưa?

Đây không phải lý do để mặc định tắt `discardFatalsWithXDeath`. Nếu replay mang lại cùng payload sai mà không có sửa chữa, một vòng lặp DLQ → work queue → DLQ sẽ tiêu tốn tài nguyên và che giấu lỗi. Thiết kế tốt thường có **quarantine queue**, lịch sử xử lý, công cụ sửa event, số lần replay tối đa, phê duyệt và audit.

Khi phải duy trì bằng chứng message lỗi, hãy **lưu/ghi nhận nội dung và metadata theo chính sách bảo mật phù hợp** ở tầng điều tra, không trông chờ một vòng chuyển DLQ vô hạn.

## 12. Error handler không thể bảo đảm exactly-once

Giả sử consumer:

1. Nhận event `E-101`.
2. Cập nhật database và commit thành công.
3. Connection tới RabbitMQ đứt **trước khi broker nhận consumer ACK**.
4. Broker giao lại event, có thể với `redelivered=true`.

Trường hợp này **không phải lỗi conversion fatal**. `ConditionalRejectingErrorHandler` không thể tự suy ra database đã commit. Consumer phải lưu trạng thái xử lý theo **`eventId` hoặc khóa nghiệp vụ** và kiểm tra trùng một cách bền vững, thường bằng transaction/ràng buộc duy nhất.

~~~text
BEGIN DATABASE TRANSACTION
    if eventId already processed:
        skip side effects
    else:
        apply business changes
        insert processed_event(eventId)
COMMIT
ACK current RabbitMQ delivery
~~~

Nếu ACK thất lạc, lần giao lại nhìn thấy `processed_event(eventId)` rồi bỏ qua side effect và ACK delivery mới. Đây là **idempotent processing**, không phải exactly-once delivery của RabbitMQ.

Khi producer vừa lưu DB vừa publish event, cân nhắc **transactional outbox** để giảm nguy cơ “commit xong nhưng event chưa gửi”. Publisher confirms/returns xử lý quan sát phía producer; consumer acknowledgment/error handler xử lý delivery phía consumer. Hai nhóm cơ chế bổ sung nhau nhưng không thay thế nhau.

## 13. Theo dõi qua RabbitMQ Management

Mở RabbitMQ Management tại `http://localhost:15672` (nếu bật plugin), chọn **Queues and Streams / Queues**, rồi xem `demo.error.work` và `demo.error.dlq`.

| Chỉ số / dấu hiệu | Diễn giải | Điều cần cảnh giác |
|---|---|---|
| `Ready` ở work queue | Message đang chờ được giao | Tăng có thể do không có consumer hoặc consumer không theo kịp |
| `Unacked` | Delivery broker đã giao nhưng chưa nhận xác nhận kết thúc | Lâu không giảm có thể do listener treo, quên ACK hoặc lỗi connection |
| `Consumers` | Số consumer hiện đăng ký vào queue | 0 có thể do listener chưa chạy, sai vhost/queue hoặc lỗi kết nối |
| `demo.error.dlq` Ready | Message đang chờ điều tra | DLQ tăng là cảnh báo, **không phải trạng thái xử lý thành công** |
| `Redeliver rate` | Mức độ message bị giao lại | Cao liên tục có thể do vòng lặp requeue hoặc mất kết nối |
| `x-death` trên message DLQ | Lịch sử dead-letter | Không đồng nghĩa tổng số lần delivery hoặc retry trong listener |

Đối với mỗi lỗi, nên log:

~~~text
time, eventId/messageId, queue, consumerTag, deliveryTag,
redelivered, exceptionClass, fatalClassification,
ackDecision, requeueFlag, xDeathPresent, traceId
~~~

**Bảo mật:** không log toàn bộ body/token nhạy cảm theo mặc định. Dùng event ID và trích dẫn nguyên nhân lỗi đã được làm sạch để truy vết. Nếu exception chứa PII, chuẩn hóa log và giới hạn quyền xem.

### Quan sát có hạn chế

Management không lưu lịch sử mọi lần ACK/NACK theo từng event. Snapshot `Ready=0, Unacked=0` **không chứng minh** event đã xử lý nghiệp vụ thành công: nó có thể bị ACK, reject và dead-letter, bị discard, hoặc đã đi sang queue khác. Phải kết hợp log/error metrics, trạng thái database và DLQ.

## 14. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| JSON malformed cứ được giao lại | Chưa dùng handler/strategy đúng, config requeue, hoặc lỗi được wrap/classify khác dự kiến | Xác minh exception chain, listener factory và chính sách reject |
| Lỗi nghiệp vụ `InvalidOrderEventException` vẫn requeue | Default strategy không biết exception tùy chỉnh | Mở rộng `isUserCauseFatal` hoặc ném reject-specific exception khi phù hợp |
| Lỗi DB timeout bị đẩy thẳng DLQ | `default-requeue-rejected=false` mà không có bounded retry/recoverer | Thiết kế lại retry cho lỗi tạm thời, không phân loại timeout là fatal |
| Message lỗi biến mất, không thấy ở DLQ | DLX/binding sai, DLQ không có, hoặc fatal có `x-death` bị discard theo cấu hình | Kiểm tra topology, `x-death`, `discardFatalsWithXDeath` |
| Không thấy log listener cho message JSON lỗi | Lỗi conversion xảy ra **trước** lời gọi `@RabbitListener` | Kiểm tra container error handler, converter và DLQ |
| Custom handler dường như không có tác dụng | Listener đang dùng factory mặc định, không phải `errorOrdersFactory` | Kiểm tra `containerFactory`, tên bean và factory thực tế |
| `rejectManual` dường như không xử lý poison message | Phiên bản khác, error handler không được gắn vào container, ACK mode sai | Xem phiên bản, `setRejectManual`, container logs |
| `unknown delivery tag` | Manual ACK hai lần, ACK sai channel hoặc trộn AUTO và MANUAL | Dùng đúng channel/tag, xác nhận một lần trên mỗi delivery |
| DLQ tăng liên tục dù deploy bản sửa | Event cũ vẫn sai, producer tiếp tục gửi lỗi, replay không sửa | Phân loại theo eventId/schemaVersion, dừng nguồn lỗi, kiểm tra pipeline |
| Đã có publisher confirm ACK nhưng consumer fail | Confirms chỉ nói về broker nhận publication | Theo dõi consumer ACK/error/DLQ và trạng thái nghiệp vụ riêng |
| Error handler ghi quá nhiều log | Poison message requeue nóng hoặc log body lớn | Chặn loop, giới hạn retry/backoff và chuẩn hóa log |

**Quy trình chẩn đoán đề xuất:** tìm đúng event ID → xem topology/queue/vhost → xác định listener factory và converter → đọc exception root cause → kiểm tra fatal strategy → kiểm tra ACK/requeue policy → xem DLQ và `x-death` → đối chiếu trạng thái nghiệp vụ.

## 15. Bài tập thực hành

**Bài A — So sánh lỗi conversion và lỗi trong handler.** Gửi ba mode `valid`, `malformed`, `invalid`. Ghi lại mode nào có `LISTENER_INVOKED`, exception tương ứng và trạng thái `demo.error.dlq`. Giải thích vì sao `try/catch` trong listener không bắt được lỗi JSON malformed.

**Bài B — Tắt phân loại nghiệp vụ fatal.** Trong một bản lab độc lập, bỏ nhánh nhận diện `InvalidOrderEventException` khỏi custom strategy. Với `default-requeue-rejected=true`, dự đoán hậu quả nếu không có bounded retry. **Không tạo vòng lặp requeue kéo dài trên broker đang phục vụ ứng dụng thật.**

**Bài C — Thử DLQ không có binding.** Trong môi trường thử nghiệm riêng, đổi DLX routing key sang một key không có queue đích. Gửi malformed message. Vì sao `reject không requeue` không bảo đảm message sẽ được lưu trong DLQ?

**Bài D — Khôi phục message từ DLQ.** Mô phỏng một message đã có `x-death`, thử replay khi dữ liệu chưa được sửa. Phác thảo các chính sách ngăn vòng lặp, audit và kiểm soát replay; giải thích vai trò của `discardFatalsWithXDeath`.

**Bài E — MANUAL acknowledgment.** Thiết kế listener manual ack nhận raw `Message`, xử lý idempotent và chỉ ACK sau database commit. Phân tích trường hợp conversion lỗi trước listener, lỗi ACK do channel đóng và trách nhiệm của container error handler.

**Bài F — Thiết kế retry.** Với database timeout 5 giây nhưng JSON hợp lệ, đề xuất backoff, số lần thử tối đa, DLQ/cảnh báo và idempotency. So sánh cách này với `basicNack(requeue=true)` vô hạn.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `ConditionalRejectingErrorHandler` có chạy bên trong phương thức `@RabbitListener` không?

**Đáp án:** Không. Nó là error handler ở **tầng listener container**, nên có thể xử lý cả exception xảy ra trong quá trình conversion/argument binding **trước** khi listener được gọi.

**Câu 2.** Fatal exception có tự động tạo DLQ không?

**Đáp án:** Không. Fatal thường dẫn đến reject không requeue. **DLX và binding của queue** phải được cấu hình hợp lệ thì message mới có thể vào DLQ.

**Câu 3.** `isFatal(exception)==false` có chắc chắn dẫn tới requeue không?

**Đáp án:** Không. Hành vi cuối còn phụ thuộc `defaultRequeueRejected`, retry advice, loại exception đặc biệt và chế độ ACK của container.

**Câu 4.** Vì sao không nên gắn mọi `RuntimeException` là fatal?

**Đáp án:** Vì có thể bao gồm lỗi hạ tầng tạm thời. Không phân loại có chủ đích sẽ khiến message hợp lệ bị reject không requeue trước khi có cơ hội retry.

**Câu 5.** Khi JSON lỗi, vì sao `catch (Exception e)` trong listener không chạy?

**Đáp án:** Bởi converter thường thất bại trước khi framework gọi phương thức. Lỗi đi theo đường container/adapter error handling.

**Câu 6.** `x-death` chứng minh message đã được NACK requeue bao nhiêu lần?

**Đáp án:** Không. Nó mô tả lịch sử **dead-letter**, không đếm mọi lần requeue của một delivery tại queue.

**Câu 7.** Vì sao message fatal có `x-death` đôi khi bị discard thay vì vào DLQ lần nữa?

**Đáp án:** `ConditionalRejectingErrorHandler` có tùy chọn `discardFatalsWithXDeath` nhằm chặn vòng lặp DLQ↔work queue. Phải xem cấu hình và đường replay thực tế.

**Câu 8.** Có thể dùng handler này để sửa trường hợp producer publish sai routing key không?

**Đáp án:** Không. Lỗi đó thuộc producer routing/exchange/binding và publisher returns; handler của consumer chỉ xử lý message **đã được broker giao** tới listener container.

**Câu 9.** Nếu consumer đã commit DB nhưng mất kết nối trước ACK, `FatalExceptionStrategy` có ngăn việc xử lý trùng không?

**Đáp án:** Không. Broker có thể redeliver. Cần lưu event ID đã xử lý và thực hiện idempotency bền vững.

## 17. Ghi nhớ

- **`ConditionalRejectingErrorHandler` phân loại lỗi ở tầng listener container**, kể cả lỗi conversion có thể xảy ra trước `@RabbitListener`; `FatalExceptionStrategy` quyết định exception nào fatal.
- **`DefaultExceptionStrategy` biết nhiều lỗi conversion/argument binding**, nhưng không mặc định hiểu mọi exception nghiệp vụ. Mở rộng `isUserCauseFatal` hoặc dùng exception reject rõ ràng cho dữ liệu không thể phục hồi.
- **Fatal thường dẫn tới reject không requeue, không đồng nghĩa được lưu vào DLQ.** Cần đúng DLX/binding và kiểm tra cơ chế `discardFatalsWithXDeath` khi replay.
- **`defaultRequeueRejected`, MANUAL ACK, retry interceptor và error handler là những lớp chính sách khác nhau**. Lỗi tạm thời cần retry có giới hạn/backoff; lỗi cố định cần quarantine/DLQ có giám sát.
- **Xử lý đáng tin cậy vẫn cần đúng exchange/queue/binding, publisher confirms/returns, consumer ACK, idempotency, giao dịch/outbox và quan sát hệ thống**; một error handler không tự tạo exactly-once processing.
