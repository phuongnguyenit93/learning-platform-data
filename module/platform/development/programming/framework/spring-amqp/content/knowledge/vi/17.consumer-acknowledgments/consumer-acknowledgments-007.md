# Exception trong listener và defaultRequeueRejected của Spring AMQP

Khi một `@RabbitListener` ném exception, điều gì xảy ra với message đang được xử lý? Nó có tự quay lại queue để thử lần nữa, bị loại bỏ, hay được chuyển đến dead-letter queue (DLQ)? Câu trả lời không chỉ nằm ở kiểu exception mà còn phụ thuộc **acknowledgement mode, `defaultRequeueRejected`, error handler, retry interceptor, transaction và cấu hình RabbitMQ broker**.

Đây là bài thuộc chương **Xác nhận tiêu thụ** của module **SPRING_AMQP**. Trong quá trình tích hợp RabbitMQ bằng `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding, hệ thống cần phân biệt lỗi định tuyến, lỗi deserialize, lỗi nghiệp vụ và lỗi hạ tầng để chọn cách xác nhận, gửi lại hoặc dead-letter phù hợp. Trọng tâm của bài là **exception trong listener và `defaultRequeueRejected`**: cờ này quyết định mặc định có yêu cầu broker đưa lại delivery vào queue sau một lần xử lý lỗi hay không, nhưng **không phải quy tắc duy nhất**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả luồng **delivery → listener → ack/reject/nack** trong `AcknowledgeMode.AUTO`.
2. Giải thích khi nào `defaultRequeueRejected=true` dẫn đến requeue và `false` dẫn đến reject không requeue.
3. Chủ động ghi đè hành vi với `AmqpRejectAndDontRequeueException` hoặc `ImmediateRequeueAmqpException`.
4. Hiểu vì sao `ConditionalRejectingErrorHandler` thường loại các lỗi chuyển đổi dữ liệu vĩnh viễn khỏi vòng redelivery.
5. Phân biệt requeue trực tiếp, retry có giới hạn, delayed retry và dead-letter; không tạo vòng lặp poison message.
6. Cấu hình Spring Boot/Spring AMQP, viết listener minh họa và kiểm thử trạng thái `ready`, `unacked`, redelivered, DLQ.
7. Nhận diện những trường hợp `MANUAL`, `NONE`, transaction hoặc async listener làm thay đổi cách điều khiển acknowledgement.

## 2. Hiểu đúng ba hành động: ack, reject và nack

RabbitMQ giao một message từ queue tới consumer. Khi dùng acknowledgement do consumer kiểm soát, delivery được coi là **chưa hoàn tất** cho đến khi broker nhận một tín hiệu settlement thích hợp.

| Tín hiệu AMQP 0-9-1 | Ý nghĩa | Sau đó chuyện gì xảy ra? |
|---|---|---|
| `basic.ack(deliveryTag, multiple)` | Consumer xác nhận delivery đã xử lý xong | Broker loại delivery khỏi tập đang chờ ack; không tự redeliver nó |
| `basic.reject(deliveryTag, requeue=true)` | Từ chối một delivery nhưng yêu cầu đưa lại queue | Message có thể được broker giao lại |
| `basic.reject(deliveryTag, requeue=false)` | Từ chối delivery và không đưa lại queue gốc | Có thể dead-letter nếu queue có DLX hợp lệ; nếu không, bị loại |
| `basic.nack(deliveryTag, multiple, requeue)` | Negative acknowledgement, có thể áp dụng nhiều delivery theo cờ `multiple` | Requeue hoặc reject không requeue theo tham số |

**Publisher confirm cũng có `ack/nack`, nhưng là giao thức khác.** Một `RabbitTemplate` nhận confirm `ack` từ broker không có nghĩa listener đã xử lý thành công. Trong bài này, khi nói `requeue`/consumer `basic.reject`, ta đang xét **delivery tới consumer**, không phải publish từ producer.

~~~mermaid
flowchart TD
    Q["RabbitMQ queue"] --> D["Delivery cho consumer"]
    D --> L["@RabbitListener"]
    L -->|"Xử lý thành công"| ACK["Consumer ack"]
    L -->|"Xử lý lỗi"| DEC{"Container chọn requeue?"}
    DEC -->|"Có"| R["Reject/nack requeue=true"]
    R --> Q
    DEC -->|"Không"| DL["Reject/nack requeue=false"]
    DL --> X{"Queue có DLX hợp lệ?"}
    X -->|"Có"| DLQ["Exchange DLX → DLQ"]
    X -->|"Không"| DROP["Message bị loại"]
~~~

Một delivery đã được consumer ack thì không còn nằm trong queue để broker tự retry sau đó. Nếu listener ghi database thành công nhưng ack bị thất lạc do mất connection, message vẫn **có thể được redeliver**; vì thế cần **idempotency** ngay cả trong luồng xử lý bình thường.

## 3. Ba chế độ AcknowledgeMode của listener container

Trong Spring AMQP, `defaultRequeueRejected` có ý nghĩa rõ nhất khi listener container đang chịu trách nhiệm settlement delivery. Trước khi thay cờ này, kiểm tra `AcknowledgeMode`:

| Acknowledge mode | Ai gửi consumer ack? | Khi listener ném exception? | Liên hệ với defaultRequeueRejected |
|---|---|---|---|
| **AUTO** | Container gửi ack khi handler hoàn tất thành công | Container/error handler quyết định reject hoặc nack, có thể requeue | **Trường hợp trọng tâm** của cờ này |
| **MANUAL** | Ứng dụng chủ động gọi `basicAck/basicNack/basicReject` trên channel | Không được giả định exception nào cũng khiến container tự giải quyết mọi delivery | Cần hiểu manual settlement và xử lý lỗi đặc biệt của container |
| **NONE** | Broker dùng auto-ack/no-ack khi giao message | Delivery đã được broker coi là hoàn tất; lỗi business không thể tạo broker requeue tự động | Cờ không tạo lại delivery đã auto-ack |

`AcknowledgeMode.AUTO` của Spring **không phải** RabbitMQ `autoAck=true`. Ở AUTO, Spring kiểm soát acknowledgement dựa vào kết quả method; ở NONE, broker coi delivery đã ack ngay từ lúc gửi.

Ví dụ một listener đồng bộ:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ExampleListener {

    @RabbitListener(queues = "orders.work.q")
    public void handle(String body) {
        if (body.startsWith("INVALID:")) {
            throw new IllegalArgumentException("Invalid order event");
        }
        // Công việc nghiệp vụ hoàn tất thì method return.
    }
}
~~~

Với container AUTO, khi method **trả về bình thường**, container có thể ack delivery theo quy tắc batch/transaction được cấu hình. Khi method **ném exception**, container phải đi qua error handler và chọn requeue/reject. Việc method bắt exception rồi chỉ log và return khiến container **có thể ack message**; đừng nuốt exception nếu nghiệp vụ chưa xử lý được.

## 4. defaultRequeueRejected quyết định điều gì?

`defaultRequeueRejected` là thuộc tính của Spring AMQP listener container (`SimpleMessageListenerContainer`, `DirectMessageListenerContainer`). **Mặc định là `true`** trong cơ chế container thông thường.

Khi listener thất bại và không có một quy tắc/exception đặc biệt ghi đè, nó quyết định **giá trị `requeue`** mà container sẽ dùng lúc reject/nack delivery.

| `defaultRequeueRejected` | Với business exception thông thường ở AUTO, không có override | Kết quả thường gặp |
|---|---|---|
| **true** (mặc định) | Container yêu cầu `requeue=true` | Broker đưa message lại queue, có thể giao lại ngay |
| **false** | Container yêu cầu `requeue=false` | Broker không đưa lại queue; có DLX phù hợp thì message có thể vào DLQ, không thì bị loại |

**Không hiểu nhầm “false nghĩa là tự động có DLQ”.** Queue phải có cấu hình dead-letter exchange và đường binding phù hợp. Nếu không, `requeue=false` có thể khiến message **bị mất khỏi luồng tiêu thụ**. Cũng không hiểu `true` là “retry có giới hạn”: bản thân cờ này **không đặt số lần thử tối đa hoặc backoff**.

### 4.1. Kịch bản default = true

~~~text
T1: broker giao msg-42 → @RabbitListener
T2: listener lỗi: IllegalStateException
T3: container xử lý exception, reject/nack requeue=true
T4: broker trả msg-42 về queue
T5: có thể giao lại msg-42 cho cùng hoặc consumer khác
T6: nếu vẫn lỗi, quá trình có thể lặp lại
~~~

RabbitMQ thường cố đưa message được requeue về vị trí gần vị trí cũ/đầu queue nếu có thể. Khi nhiều consumer hoặc giao đồng thời, thứ tự redelivery thực tế có thể thay đổi. Requeue liên tục **không phải một bộ lập lịch retry có delay**.

### 4.2. Kịch bản default = false

~~~text
T1: broker giao msg-42 → @RabbitListener
T2: listener lỗi: IllegalStateException
T3: container xử lý exception, reject/nack requeue=false
T4a: queue có DLX + binding hợp lệ → dead-letter
T4b: queue không có DLX/không route được ở DLX → có thể bị loại
~~~

Nếu default là false, một sự cố tạm thời của database cũng có thể khiến message đi thẳng vào DLQ sau **một lần** xử lý nếu chưa gắn retry phù hợp. Vì thế phải phân loại lỗi vĩnh viễn/tạm thời trước khi áp dụng chính sách cho toàn bộ listener.

## 5. Không phải mọi exception đều theo defaultRequeueRejected

Spring AMQP cho phép chỉ định hành vi settlement qua những exception đặc biệt:

| Exception từ listener hoặc chuỗi nguyên nhân | Tác dụng chính | Có thể ghi đè cờ? |
|---|---|---|
| `IllegalStateException`, `RuntimeException` nghiệp vụ thông thường | Chuyển xử lý lỗi về container | Có thể theo `defaultRequeueRejected`, trừ error handler/retry thay đổi |
| `AmqpRejectAndDontRequeueException` | Yêu cầu không requeue delivery | **Có:** không requeue dù default=true |
| `ImmediateRequeueAmqpException` | Yêu cầu requeue delivery | **Có:** requeue dù default=false |
| Exception fatal do conversion/method mapping | Error handler mặc định có thể biến thành reject không requeue | **Có**, tùy chiến lược nhận diện fatal |

Hai exception đặc biệt nằm trong package **`org.springframework.amqp`**:

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.ImmediateRequeueAmqpException;
~~~

`AmqpRejectAndDontRequeueException` thường dùng khi payload không thể xử lý thành công dù retry bao nhiêu lần, ví dụ schema không hỗ trợ. `ImmediateRequeueAmqpException` được đưa vào từ Spring AMQP 2.1, dùng khi chủ động muốn broker giao lại dù cấu hình chung không requeue.

**Cảnh báo:** ném `ImmediateRequeueAmqpException` liên tục trên một message lỗi cố định có thể tạo vòng redelivery cực nhanh. Chỉ dùng khi có điều kiện phục hồi, điều tiết hoặc cơ chế đếm lần giao lại phù hợp.

## 6. Đọc sơ đồ quyết định khi listener ném lỗi

~~~mermaid
flowchart TD
    A["@RabbitListener ném exception"] --> B["Listener container / ErrorHandler"]
    B --> E{"Fatal conversion/mapping<br/>hoặc chính sách đặc biệt?"}
    E -->|"AmqpRejectAndDontRequeue<br/>hoặc fatal được nhận diện"| NR["requeue=false"]
    E -->|"ImmediateRequeue"| R["requeue=true"]
    E -->|"Exception thông thường"| D{"defaultRequeueRejected"}
    D -->|"true"| R
    D -->|"false"| NR
    R --> Q["Broker requeue<br/>có thể redeliver"]
    NR --> X{"DLX/binding hoạt động?"}
    X -->|"Có"| DLQ["DLQ/queue khác"]
    X -->|"Không"| DROP["Discard"]
~~~

Sơ đồ thể hiện **lựa chọn chính** trong container xử lý listener AUTO, không liệt kê mọi tình huống giao thức. Chẳng hạn channel mất kết nối, transaction rollback, manual acknowledgement, consumer batching hoặc custom error handler có thể làm trình tự và kết quả cụ thể khác đi. Một handler custom cũng có thể trả về bình thường và khiến container ack, không có bước reject nào.

### 6.1. Exception có thể được bọc trong ListenerExecutionFailedException

Khi method listener ném lỗi, Spring AMQP thường bọc nó thành `ListenerExecutionFailedException`, giữ nguyên exception gốc trong cause chain. Vì vậy:

~~~text
ListenerExecutionFailedException:
  Caused by: IllegalStateException("Database temporarily unavailable")
~~~

Nếu có retry classifier hoặc custom error handler kiểm tra loại lỗi, cần **duyệt cause chain** khi thích hợp. Chỉ so sánh exception ở lớp ngoài có thể khiến rule cho `IllegalStateException` không được áp dụng.

### 6.2. Khi exception bị bắt và nuốt

~~~java
@RabbitListener(queues = "orders.work.q")
public void handle(String body) {
    try {
        paymentService.process(body);
    } catch (Exception exception) {
        System.err.println("Failed: " + exception.getMessage());
        // Method return bình thường!
    }
}
~~~

Đây là **anti-pattern** đối với công việc bắt buộc xử lý: Spring có thể xem listener thành công và ack, dù `paymentService.process` thất bại. Nếu muốn retry/reject, hãy **truyền lỗi ra đúng tầng** hoặc thực hiện settlement tường minh theo mode đã chọn. Đừng log toàn bộ payload hoặc dữ liệu nhạy cảm khi xử lý exception.

## 7. Cấu hình defaultRequeueRejected trong Spring Boot

Với Spring Boot dùng RabbitMQ AMQP 0-9-1 và các property được hỗ trợ ở nhánh 3.x, cấu hình listener kiểu Simple:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: simple
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false
        concurrency: 2
        prefetch: 10
~~~

Hoặc với listener kiểu Direct:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: direct
      direct:
        acknowledge-mode: auto
        default-requeue-rejected: false
        consumers-per-queue: 2
        prefetch: 10
~~~

Các ví dụ trên **là hai lựa chọn riêng**, không phải hai loại container đồng thời áp dụng lên mọi listener. `spring.rabbitmq.listener.type` chọn kiểu factory mặc định của Spring Boot; một listener dùng `containerFactory="customFactory"` có thể có cấu hình riêng không phụ thuộc những property này.

**Giá trị `false` có tính tác động cao:** mọi business exception thông thường ở listener chịu cấu hình này có thể dẫn đến reject không requeue. Cần đảm bảo DLX/đường xử lý lỗi đã có và lỗi tạm thời có chiến lược retry được kiểm soát.

Tên property có thể khác ở thế hệ Spring Boot/AMQP mới. Trước khi áp dụng production, hãy đọc application properties **của đúng phiên bản resolved** và xác minh trong runtime rằng listener factory mong muốn thực sự được dùng.

## 8. Cấu hình bằng SimpleRabbitListenerContainerFactory

Khi nhiều nhóm listener cần chính sách khác nhau, có thể tạo một factory riêng:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ConsumerFailureConfiguration {

    @Bean
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory,
            SimpleRabbitListenerContainerFactoryConfigurer configurer) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);
        factory.setConcurrentConsumers(2);
        factory.setPrefetchCount(10);
        return factory;
    }
}
~~~

Gắn chính xác factory vào listener:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersWorker {

    @RabbitListener(
        queues = "orders.work.q",
        containerFactory = "ordersListenerFactory")
    public void process(String body) {
        // Nếu ném exception thông thường, cờ mặc định của factory = false.
    }
}
~~~

Với ứng dụng dùng Spring Boot, `SimpleRabbitListenerContainerFactoryConfigurer` giúp áp dụng các thiết lập mà Boot hỗ trợ trước khi code ghi đè một số thuộc tính. Nếu tự tạo factory mà **không dùng configurer**, có thể vô tình mất converter, retry, transaction hoặc observation đã cấu hình. Nếu dự án sử dụng Spring AMQP trực tiếp không có Boot, có thể tự tạo factory nhưng cần thiết lập tất cả thuộc tính có liên quan.

**Cần phân biệt factory và container:** `setDefaultRequeueRejected(false)` trên factory được áp dụng cho những container nó tạo; nếu `@RabbitListener` đang dùng factory mặc định hoặc factory khác, hành vi có thể không đổi. Vì vậy hãy xem tên `containerFactory` và thông số runtime trước khi kết luận đã cấu hình thành công.

## 9. Topology thực hành: queue nguồn, DLX và DLQ

Để quan sát `requeue=false`, một queue test nên có dead-letter exchange được route đến DLQ. Ví dụ này cố ý dùng tên **`lab.ack.*`** để tách môi trường thực hành khỏi nghiệp vụ thật.

~~~mermaid
flowchart LR
    P["RabbitTemplate"] --> EX["lab.ack.x<br/>direct"]
    EX -->|"work"| Q["lab.ack.work.q"]
    Q -->|"Listener thành công"| ACK["ack"]
    Q -->|"requeue=true"| Q
    Q -->|"requeue=false"| DLX["lab.ack.dlx<br/>direct"]
    DLX -->|"failed"| DLQ["lab.ack.dlq"]
~~~

Code khai báo:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AckLabTopology {

    @Bean
    DirectExchange ackLabExchange() {
        return new DirectExchange("lab.ack.x", true, false);
    }

    @Bean
    DirectExchange ackLabDlx() {
        return new DirectExchange("lab.ack.dlx", true, false);
    }

    @Bean
    Queue ackLabWorkQueue() {
        return QueueBuilder.durable("lab.ack.work.q")
                .deadLetterExchange("lab.ack.dlx")
                .deadLetterRoutingKey("failed")
                .build();
    }

    @Bean
    Queue ackLabDeadLetterQueue() {
        return QueueBuilder.durable("lab.ack.dlq").build();
    }

    @Bean
    Binding ackLabWorkBinding(
            Queue ackLabWorkQueue, DirectExchange ackLabExchange) {
        return BindingBuilder.bind(ackLabWorkQueue)
                .to(ackLabExchange).with("work");
    }

    @Bean
    Binding ackLabDeadLetterBinding(
            Queue ackLabDeadLetterQueue, DirectExchange ackLabDlx) {
        return BindingBuilder.bind(ackLabDeadLetterQueue)
                .to(ackLabDlx).with("failed");
    }
}
~~~

Các bean `Queue`, `Exchange`, `Binding` chỉ được khai báo lên broker nếu có `RabbitAdmin`/cơ chế quản lý topology và quyền phù hợp. Đảm bảo producer và consumer kết nối **cùng virtual host**. Đừng đổi `x-dead-letter-exchange` trên một queue production đang có message mà không hiểu quy tắc khai báo lại và migration; ưu tiên quản lý bằng policy khi phù hợp.

Đường đi khi `requeue=false`:

~~~text
lab.ack.x --(work)--> lab.ack.work.q
     listener exception
     container basic.reject / basic.nack (requeue=false)
lab.ack.work.q --(dead letter)--> lab.ack.dlx --(failed)--> lab.ack.dlq
~~~

DLX **không tự tạo** queue đích. Nếu DLX/binding/permission không đúng, message có thể không đến DLQ. Với yêu cầu bảo đảm lưu message cao hơn, cần kiểm tra queue type và cơ chế dead-lettering của RabbitMQ, không xem `x-dead-letter-exchange` là cam kết delivery tuyệt đối.

## 10. Listener minh họa ba kết quả

Với container AUTO và `defaultRequeueRejected=false`, listener sau thể hiện ba trường hợp:

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class AckLabListener {

    @RabbitListener(
        queues = "lab.ack.work.q",
        containerFactory = "ordersListenerFactory")
    public void process(String command) {
        if (command.startsWith("INVALID:")) {
            // Lỗi dữ liệu vĩnh viễn: không đưa lại queue dù default=true.
            throw new AmqpRejectAndDontRequeueException(
                    "Invalid message contract");
        }

        if (command.startsWith("DOWNSTREAM_DOWN:")) {
            // Lỗi tạm thời minh họa: với default=false cũng không requeue.
            throw new IllegalStateException("External service unavailable");
        }

        // Chỉ return bình thường sau khi xử lý nghiệp vụ thực sự hoàn tất.
        System.out.println("Processed command");
    }
}
~~~

Với topology và factory của các mục trên:

| Body test | Listener làm gì? | Settlement dự kiến | Kết quả |
|---|---|---|---|
| `OK:1001` | Return bình thường | Ack | Message rời queue sau khi xử lý |
| `INVALID:1002` | Ném `AmqpRejectAndDontRequeueException` | Reject `requeue=false` | Dead-letter tới `lab.ack.dlq` nếu DLX hoạt động |
| `DOWNSTREAM_DOWN:1003` | Ném `IllegalStateException` | Với default=false: reject `requeue=false` | Cũng có thể vào DLQ **ngay**, chưa có retry |

Bảng này cho thấy vì sao `defaultRequeueRejected=false` **không tự phân loại lỗi**. Cấu hình giúp ngăn vòng lặp nhưng có thể loại hoặc DLQ cả message chỉ gặp lỗi database tạm thời.

Để thử cờ `true`, đổi factory trên môi trường test và phát message `DOWNSTREAM_DOWN:1003`. Nó có thể được redeliver nhiều lần. **Không để phép thử chạy vô hạn**: giới hạn thời gian thử, dừng listener hoặc dùng một retry strategy có giới hạn để tránh log storm và quá tải broker.

## 11. Dùng AmqpRejectAndDontRequeueException để từ chối có chủ đích

Trong nhiều dự án, không nên đặt toàn bộ listener ở `defaultRequeueRejected=false` nếu phần lớn lỗi là tạm thời. Một lựa chọn là giữ default=true nhưng chỉ từ chối **những lỗi không thể phục hồi**:

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;

@RabbitListener(queues = "orders.work.q")
public void onOrder(String json) {
    try {
        businessService.process(json);
    } catch (UnsupportedEventVersionException exception) {
        throw new AmqpRejectAndDontRequeueException(
                "Unsupported event schema version", exception);
    }
}
~~~

`UnsupportedEventVersionException` và `businessService` ở đây là thành phần **minh họa của ứng dụng**. Ý nghĩa là lỗi version đã biết không thể xử lý bằng việc lặp lại cùng payload với cùng phiên bản code thì nên **reject không requeue**. Các exception khác được chuyển tiếp/thoát khỏi method theo thiết kế sẽ đi qua error handler/container.

Một số lỗi vĩnh viễn khác:

- Schema message không hỗ trợ, thiếu trường bắt buộc và không thể khôi phục.
- Dữ liệu không hợp lệ theo hợp đồng bất biến của hệ thống.
- Message từ producer không được phép hoặc không có mapping hợp lệ.

Nhưng **không gán mọi `IllegalArgumentException` là vĩnh viễn** nếu thực tế hệ thống có thể thiếu dữ liệu tạm hoặc phụ thuộc service khác. Tốt nhất dùng exception nghiệp vụ phân loại rõ ràng và có alert/metric cho loại message bị reject.

## 12. ImmediateRequeueAmqpException: ghi đè để yêu cầu requeue

`ImmediateRequeueAmqpException` là hướng ngược lại: yêu cầu broker requeue message **dù `defaultRequeueRejected=false`**.

~~~java
import org.springframework.amqp.ImmediateRequeueAmqpException;

@RabbitListener(queues = "orders.work.q")
public void onTransient(String body) {
    if (isTemporarilyUnavailable()) {
        throw new ImmediateRequeueAmqpException(
                "Temporarily unavailable - request requeue");
    }
    process(body);
}
~~~

Hai method `isTemporarilyUnavailable()` và `process(...)` là logic ứng dụng minh họa. **Đây không phải mẫu retry production an toàn nếu tình trạng unavailable kéo dài.** Requeue trực tiếp có thể giao lại ngay, khiến cùng message lỗi lại ném exception trong thời gian rất ngắn.

### Tại sao không chỉ catch rồi requeue mãi?

~~~text
M1 được giao
  -> listener gọi database, lỗi
  -> requeue ngay
  -> M1 được giao lần nữa
  -> database vẫn lỗi
  -> requeue ngay ...
~~~

Vòng lặp tạo:

- CPU/log và network traffic tăng.
- Consumer thread bị chiếm, message khác bị trì hoãn.
- Dịch vụ đang lỗi nhận thêm áp lực.
- Có thể xuất hiện message trùng khi side effect đã thành công một phần nhưng ack thất lạc.

Nếu muốn retry lỗi tạm thời, **đặt số lần thử và khoảng backoff rõ ràng**; sau khi hết số lần, chuyển message sang DLQ/quarantine hoặc lịch xử lý lại riêng. Có thể dùng Spring Retry, delayed retry topology hoặc một cơ chế orchestration ở ứng dụng.

## 13. ConditionalRejectingErrorHandler: lỗi fatal có thể bỏ qua default

Spring AMQP mặc định sử dụng `ConditionalRejectingErrorHandler` trong nhiều listener containers. Mục tiêu của nó là ngăn các message **không thể xử lý về mặt kỹ thuật** bị redeliver vô hạn chỉ vì `defaultRequeueRejected=true`.

Một số exception được `DefaultExceptionStrategy` phân loại fatal trong các phiên bản Spring AMQP 3.x bao gồm:

- `org.springframework.amqp.support.converter.MessageConversionException` ở tầng AMQP converter.
- `org.springframework.messaging.converter.MessageConversionException` ở tầng Spring Messaging.
- `MethodArgumentNotValidException`, `MethodArgumentTypeMismatchException` khi bind tham số.
- `NoSuchMethodException` hoặc `ClassCastException` trong những tình huống mapping thích hợp.

Đây là nhóm lỗi có thể phát sinh **trước khi code `@RabbitListener` chạy**, vì framework không decode payload hoặc không xác định được method phù hợp.

### 13.1. Vì sao lỗi JSON sai không cứ lặp lại?

Giả sử queue chứa:

~~~text
{"eventId":"evt-1001","orderId":}
~~~

Nếu Jackson converter không thể parse JSON, việc broker đưa lại cùng bytes cho cùng converter sẽ tiếp tục thất bại. `ConditionalRejectingErrorHandler` có thể bọc lỗi fatal thành `AmqpRejectAndDontRequeueException` để container reject không requeue **ngay cả khi default=true**.

~~~mermaid
flowchart TD
    Q["Message JSON hỏng trong queue"] --> CV["MessageConverter"]
    CV -->|"Lỗi conversion"| EH["ConditionalRejectingErrorHandler"]
    EH --> F{"FatalExceptionStrategy xác định fatal?"}
    F -->|"Có"| NR["Reject without requeue"]
    F -->|"Không"| CFG["Áp dụng exception/cờ requeue phù hợp"]
    NR --> DLX["DLX / discard tùy topology"]
~~~

**Không nên viết:** “`defaultRequeueRejected=true` thì mọi exception luôn requeue”. Với các lỗi fatal, error handler có thể thay đổi quyết định. Ngược lại, không phải mọi validation error trong business code đều được default strategy nhận diện là fatal; đôi khi phải tự chuyển thành exception phù hợp hoặc cấu hình custom `FatalExceptionStrategy`.

### 13.2. Khi message có header x-death

Một số phiên bản Spring AMQP có cơ chế trong `ConditionalRejectingErrorHandler` **discard** message fatal đã có thông tin `x-death`, nhằm tránh chu trình dead-letter quay trở lại queue nguồn liên tục. Tính năng này có thay đổi qua phiên bản, ví dụ tham số `discardFatalsWithXDeath`.

Đừng tự giả định một message từ DLQ được đưa về queue nguồn rồi sẽ luôn đi tiếp DLQ lần nữa. Khi có dead-letter/retry topology, cần kiểm tra các headers `x-death`, chiến lược xử lý fatal và hành vi đúng của version đang chạy.

### 13.3. Manual mode và fatal conversion

Trong `MANUAL`, container thường không thay business code quyết định ack. Tuy nhiên, một số trường hợp **fatal conversion** có thể bị `ConditionalRejectingErrorHandler` từ chối ngay để tránh giữ delivery unacked không bao giờ đến được method. Các lựa chọn như `rejectManual` ảnh hưởng hành vi này trong những phiên bản hỗ trợ.

Vì vậy không nên phát biểu tuyệt đối rằng “MANUAL thì container không bao giờ reject”. Hãy kiểm tra error handler, phiên bản và test bằng một payload hỏng trong môi trường test.

## 14. Retry với giới hạn khác requeue tức thời như thế nào?

Hai thuật ngữ này nghe giống nhau nhưng vận hành khác:

| Phương án | Bản chất | Ưu điểm | Rủi ro |
|---|---|---|---|
| `defaultRequeueRejected=true` | Broker requeue khi listener lỗi | Đơn giản, không mất message ngay | Không có giới hạn/backoff mặc định, dễ poison loop |
| Spring Retry interceptor | Gọi lại listener theo retry policy ở phía ứng dụng | Có `maxAttempts`, backoff, phân loại lỗi | Chiếm listener thread trong quá trình retry; cần chọn stateful/stateless đúng transaction |
| Retry queue có TTL + DLX | Broker giữ message trong queue chờ rồi chuyển route | Tách thời gian chờ khỏi worker chính | Phức tạp topology, DLX/routing, có thể có vấn đề thứ tự/duplicate |
| RepublishMessageRecoverer | Publish message lỗi sang error exchange với metadata | Có ngữ cảnh lỗi phục vụ điều tra | Là publish mới, cần confirms/route/durability; không tự bảo đảm atomic |
| RejectAndDontRequeueRecoverer | Yêu cầu container reject không requeue sau khi retry exhausted | Dễ tận dụng DLX của queue nguồn | Nếu DLX không cấu hình đúng có thể mất message |

**Một cơ chế retry được thiết kế tốt** thường phân loại:

- **Transient**: network timeout, database quá tải ngắn hạn, downstream 503 → retry có backoff và giới hạn.
- **Permanent**: JSON lỗi, schema không hỗ trợ, validation bất biến → reject/quarantine/DLQ ngay, không thử lại mãi.
- **Unknown**: không chắc trạng thái external side effect → đánh dấu cần điều tra, giữ event ID và dùng idempotency để tránh duplicate business operation.

### 14.1. Spring Retry và recoverer

Spring AMQP có `RetryInterceptorBuilder` cho phép cấu hình advice chain của listener. Một ví dụ ý tưởng:

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.retry.interceptor.RetryOperationsInterceptor;

RetryOperationsInterceptor advice =
        RetryInterceptorBuilder.stateless()
                .maxRetries(3)
                .backOffOptions(1000, 2.0, 5000)
                .recoverer(new RejectAndDontRequeueRecoverer())
                .build();
~~~

Ví dụ cần thêm import `org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer` và tích hợp `advice` vào **factory thực tế** với `factory.setAdviceChain(advice)`. Tùy Spring AMQP/Spring Retry version, API builder và cách hiểu `maxRetries`/số lần gọi handler cần đối chiếu Javadoc. **Đừng đặt số lần retry dựa trên suy đoán** rồi đưa vào hợp đồng nghiệp vụ.

Chú ý `stateless` có thể phù hợp khi không có transaction bao ngoài cần rollback. Với transaction bên ngoài hoặc stateful retry, cần đánh giá lại cơ chế message identity (`messageId`) và transaction boundary. Sau khi retries cạn, `RejectAndDontRequeueRecoverer` thường báo container reject không requeue, cho phép queue DLX xử lý nếu topology đúng.

### 14.2. Recoverer nuốt exception có nghĩa gì?

Một `MessageRecoverer` có thể **xử lý lỗi rồi trả về bình thường**. Trong trường hợp đó, từ góc nhìn container, delivery có thể được ack vì đã được recoverer tiêu thụ, thay vì broker reject vào DLX. Ví dụ, `RepublishMessageRecoverer` chủ động publish một bản khác đến error exchange và kết thúc thành công.

Đây là điểm quan trọng khi debug “tại sao queue DLX rỗng dù listener lỗi?”: lỗi có thể đã được recoverer giải quyết bằng **ack nguồn sau khi republish**, không phải broker dead-letter. Khi muốn đảm bảo bản republish đã được broker nhận, cân nhắc confirms/returns của recoverer phù hợp phiên bản và yêu cầu của hệ thống.

## 15. MANUAL: khi ứng dụng trực tiếp kiểm soát ack/nack

Trong `AcknowledgeMode.MANUAL`, người viết listener phải định nghĩa khi nào ack, khi nào nack/reject; đừng dựa vào `defaultRequeueRejected` như giải pháp thay cho code acknowledgement.

Ví dụ factory:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;

@Bean
SimpleRabbitListenerContainerFactory manualAckFactory(
        ConnectionFactory connectionFactory) {

    SimpleRabbitListenerContainerFactory factory =
            new SimpleRabbitListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
    return factory;
}
~~~

Listener:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(
    queues = "lab.ack.work.q",
    containerFactory = "manualAckFactory")
public void receive(Message message, Channel channel) throws IOException {
    long deliveryTag = message.getMessageProperties().getDeliveryTag();
    String text = new String(
            message.getBody(), java.nio.charset.StandardCharsets.UTF_8);

    if (text.startsWith("INVALID:")) {
        channel.basicReject(deliveryTag, false); // Không requeue.
        return;
    }

    if (text.startsWith("TEMP:")) {
        // Minh họa thôi: requeue ngay có thể lặp vô hạn.
        channel.basicNack(deliveryTag, false, true);
        return;
    }

    // Business logic xử lý thành công trước khi ack.
    channel.basicAck(deliveryTag, false);
}
~~~

Trong manual mode, **delivery tag chỉ có nghĩa trên channel đã giao message**. Không lấy tag ở channel này rồi ack trên channel khác. Sau khi đã `basicAck` hoặc `basicNack`, không settlement lại cùng delivery tag; RabbitMQ có thể đóng channel với `PRECONDITION_FAILED - unknown delivery tag`.

Ví dụ minh họa cố ý đơn giản: không có database, transaction hay phân loại retry thực tế. Trong production:

1. Gọi business handler với timeout/circuit breaker/idempotency.
2. Chọn ack **chỉ sau khi kết quả nghiệp vụ đủ bền vững**.
3. Phân biệt lỗi vĩnh viễn và lỗi tạm thời với retry có giới hạn.
4. Xử lý sự cố mất channel khi ack: trạng thái có thể không chắc chắn, message có thể redeliver.
5. Theo dõi `messages_unacknowledged`; thiếu ack sẽ giữ prefetch credit và làm consumer đứng.

**Không dùng `AcknowledgeMode.NONE`** cho những luồng đòi hỏi retry sau listener exception: broker đã coi delivery hoàn tất khi giao, nên không còn cơ chế nack delivery từ consumer.

## 16. Transaction rollback và defaultRequeueRejected

Nếu listener chạy trong AMQP transaction hoặc transaction do framework đồng bộ, chuyện rollback phức tạp hơn một method ném exception thuần túy. Khi một message nhận được bị rollback, Spring AMQP có thể cần **reject message** sau thao tác rollback để broker biết nó nên được xử lý như thế nào.

Theo tài liệu Spring AMQP hiện đại, sau rollback, lựa chọn requeue/reject vẫn chịu ảnh hưởng của `defaultRequeueRejected` và các exception đặc biệt. Một số tùy chọn tương thích ngược như `alwaysRequeueWithTxManagerRollback` có thể thay đổi hành vi.

**Không giả định transaction JDBC và transaction RabbitMQ là một transaction phân tán atomic.** Ví dụ:

~~~text
T1: listener cập nhật database thành công
T2: commit database
T3: ack RabbitMQ bị mất do connection lỗi
T4: broker redeliver message
T5: handler có thể cố thực hiện side effect lần nữa
~~~

Giải pháp thường là idempotency key, lưu event ID đã xử lý trong cùng database transaction với tác động nghiệp vụ, và có chiến lược đối phó ack thất bại. Nếu publisher cần đảm bảo tạo sự kiện cùng thay đổi database, cân nhắc transactional outbox; `defaultRequeueRejected` của consumer không giải quyết vấn đề publisher transaction.

## 17. Nhận diện requeue, redelivery và x-death

Khi debug, ba tín hiệu này có ý nghĩa khác nhau:

| Dấu hiệu | Có nghĩa gì? | Không nói được gì? |
|---|---|---|
| `messageProperties.isRedelivered()` | Broker đánh dấu delivery đã từng được giao trước đó | Không cho biết chính xác số lần xử lý và không phải event ID |
| `messages_unacknowledged` | Các delivery đã giao nhưng chưa ack hiện tại | Không phải số lần retry |
| `x-death` header | Metadata lịch sử dead-letter của RabbitMQ | Không tự biểu thị mọi lần `requeue=true` |
| `x-delivery-count` (khi áp dụng) | Thống kê delivery/return của một số loại queue như quorum | Ngữ nghĩa và giới hạn phụ thuộc queue type/phiên bản |
| DLQ depth | Số message hiện còn trong queue xử lý lỗi | Không phải số message chưa từng thất bại |

Ví dụ lỗi phổ biến:

~~~text
redelivered=true → không có nghĩa "đã retry đúng 1 lần"
x-death count=2 → không có nghĩa "mọi lần listener exception đều được đếm"
DLQ empty → không có nghĩa "không có listener exception"
~~~

Với **quorum queue**, RabbitMQ có khả năng cấu hình giới hạn redelivery/delivery count ở broker. Hành vi theo `x-delivery-limit` và `x-delivery-count` còn phụ thuộc phiên bản RabbitMQ và cách reject/nack (đặc biệt cờ `multiple`). Đây là lớp bảo vệ bổ sung, **không thay thế** retry policy/error handler của ứng dụng. Kiểm tra chính xác queue type và version trước khi dựa vào giới hạn broker.

## 18. Quan sát để phát hiện poison-message loop

Một vòng requeue không giới hạn thường có các dấu hiệu:

- `@RabbitListener` log cùng một exception rất nhiều lần trong thời gian ngắn.
- Queue có thể không tăng dài vì cùng message được lấy ra rồi đưa lại liên tục.
- `redelivered` thường thành `true` ở những delivery sau.
- CPU, network, consumer callback rate và broker delivery rate tăng dù business throughput thấp.
- Một message lỗi vĩnh viễn gây nghẽn những message hợp lệ và tạo áp lực vào downstream đang suy yếu.

### Bộ chỉ số tối thiểu

| Metric | Mục đích |
|---|---|
| Listener success/failure count theo exception class | Phân biệt lỗi tạm thời/vĩnh viễn |
| Redelivery count/rate | Phát hiện requeue loop hoặc connection instability |
| DLQ depth và tuổi message | Biết message nào đã bị chuyển sang tuyến xử lý lỗi |
| Ready/unacked và consumer count | Phân biệt backlog với consumer bị nghẽn |
| Processing latency p95/p99 | Phát hiện downstream chậm |
| Retry attempts/exhausted | Đo retry policy có đủ/đang quá tải không |
| Broker alarms, channel/connection errors | Không đổ mọi lỗi cho nghiệp vụ |

Log nên chứa **eventId**, `messageId`, consumer role, routing key, exception category và số attempt của **cơ chế retry mà bạn tự quản lý**. Tránh log payload nhạy cảm. Việc `defaultRequeueRejected` bật hay tắt nên được ghi lại trong thông tin cấu hình vận hành để so sánh sự thay đổi.

### Kịch bản điều tra

Nếu DLQ tăng nhanh ngay sau khi đổi `defaultRequeueRejected=false`, đừng vội kết luận mọi message đều có schema lỗi. Có thể backend bị down và mọi message hợp lệ đều ném `IllegalStateException`. Kiểm tra exception phân loại, trạng thái downstream, đường DLX và retry policy trước khi chọn replay.

Ngược lại, nếu broker message rate tăng bất thường nhưng queue depth gần như không đổi, hãy xem có cùng event ID bị requeue liên tục hay không. Đưa một poison message vào quarantine có kiểm soát thường tốt hơn để nó lặp trên queue chính.

## 19. Phép thử integration với RabbitMQ

Để kiểm chứng chính xác `defaultRequeueRejected`, cần **broker thật ở môi trường test**, vì requeue/DLX/ack là hành vi phối hợp giữa container và RabbitMQ, không thể chứng minh đầy đủ bằng unit test của method Java đơn thuần.

### 19.1. Chuẩn bị

1. Tạo topology `lab.ack.x`, `lab.ack.work.q`, `lab.ack.dlx`, `lab.ack.dlq`.
2. Chỉ chạy **một listener test** trên queue nguồn để giảm nhiễu; xác nhận không có service khác cạnh tranh tiêu thụ.
3. Đặt `AcknowledgeMode.AUTO`; biết rõ factory đang dùng và effective value của `defaultRequeueRejected`.
4. Tắt retry interceptor cho các bài test cơ bản để không bị ảnh hưởng bởi retry nội bộ. Khi thử retry, bật lại một cách có chủ đích.
5. Đánh dấu message bằng ID riêng; sử dụng `RabbitTemplate` gửi tới exchange/routing key đúng.

### 19.2. Mẫu producer

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public void sendTestMessage(
        RabbitTemplate rabbitTemplate,
        String payload) {
    rabbitTemplate.convertAndSend(
            "lab.ack.x", "work", payload);
}
~~~

Ví dụ gửi:

~~~java
sendTestMessage(rabbitTemplate, "OK:1001");
sendTestMessage(rabbitTemplate, "INVALID:1002");
sendTestMessage(rabbitTemplate, "DOWNSTREAM_DOWN:1003");
~~~

Các publish phải được route vào queue nguồn; nếu thiếu binding/exchange hoặc consumer chạy trước khi topology sẵn sàng, kết quả sẽ không còn phản ánh đúng `defaultRequeueRejected\). Nếu cần xác minh producer, bật publisher confirms/returns riêng.

### 19.3. Ma trận kiểm chứng

| Phép thử | Cấu hình và lỗi | Điều dự đoán | Cần đối chiếu |
|---|---|---|---|
| **A** | AUTO, listener return bình thường | Ack, không redeliver | Queue nguồn giảm 1 |
| **B** | AUTO, default=true, exception thường | Requeue và có thể redeliver | `redelivered`, failure logs; dừng thử nhanh |
| **C** | AUTO, default=false, exception thường | Reject không requeue | DLQ tăng 1 nếu DLX hợp lệ |
| **D** | AUTO, default=true, `AmqpRejectAndDontRequeueException` | Không requeue | DLQ hoặc discard theo topology |
| **E** | AUTO, default=false, `ImmediateRequeueAmqpException` | Requeue dù default=false | Redelivery; tránh chạy vô hạn |
| **F** | AUTO, default=true, JSON lỗi fatal | `ConditionalRejectingErrorHandler` có thể reject không requeue | Container logs, DLQ và cause chain |
| **G** | MANUAL, app gọi `basicReject(tag,false)` | Không requeue | DLX/DLQ |
| **H** | NONE, business exception | Không thể yêu cầu broker requeue delivery đã auto-ack | Queue mất message, không có consumer nack |
| **I** | Retry có giới hạn, recoverer reject | Retry rồi reject sau khi exhausted | Attempts, backoff, DLQ |

Để không tạo vòng lặp ở B/E, chạy test trong thời gian ngắn, dùng consumer có latch/đếm nhận hoặc cấu hình container tạm dừng sau một số lần thử. Nếu cần kiểm tra số lần, dùng bộ đếm của **test listener** thay vì cố đo bằng thời gian chờ cố định.

### 19.4. Cách assert kết quả đáng tin cậy

- Với AUTO và success, đợi listener xử lý xong thay vì kiểm tra queue ngay sau publish.
- Với DLQ, đợi đến khi message thực sự xuất hiện, rồi kiểm tra body và headers dead-letter.
- Với requeue, dùng test listener ghi event ID và delivery redelivered flag; không để cùng ID lặp vô hạn.
- Với MANUAL, kiểm tra đúng channel/delivery tag và chỉ gọi settlement một lần.
- Với retry, so sánh số handler attempts với cấu hình max attempts và bảo đảm cuối cùng message không còn quay lại queue chính liên tục.

## 20. Các lỗi thiết kế thường gặp

### 20.1. Mặc định true nên “cứ throw là sẽ retry có giới hạn”

**Sai.** `defaultRequeueRejected=true` yêu cầu requeue, không tự có backoff hoặc số lần tối đa. Một lỗi không thể phục hồi có thể làm broker giao lại vô hạn.

**Sửa:** thêm retry policy có giới hạn, phân loại fatal, quarantine và DLQ.

### 20.2. Đặt false nghĩa là “mọi message lỗi an toàn trong DLQ”

**Sai.** Không có DLX/binding/permission tương ứng thì message không requeue có thể bị loại. Một số topology dead-letter còn có hạn chế độ tin cậy riêng.

**Sửa:** kiểm tra DLX end-to-end bằng integration test; có cảnh báo khi DLQ routing thất bại.

### 20.3. Throw exception sau khi manual ack

Nếu đã `basicAck` mà sau đó code lại ném exception, container không thể “undo” consumer acknowledgement. Trong `MANUAL`, settlement trùng còn có thể gây lỗi giao thức.

**Sửa:** xác định chính xác điểm commit nghiệp vụ, gọi ack **một lần** sau thành công, không tiếp tục công việc có thể thất bại quan trọng sau khi đã ack nếu yêu cầu retry ở broker.

### 20.4. Bắt exception rồi chỉ log

Nếu method return bình thường trong AUTO, container có thể ack; message đã thất bại nghiệp vụ nhưng broker không biết.

**Sửa:** tái ném lỗi đúng phân loại hoặc quản lý transaction/settlement có kiểm chứng.

### 20.5. Nghĩ lỗi JSON nào cũng vào @RabbitListener

Conversion có thể thất bại trước khi method được gọi, khiến catch bên trong method hoàn toàn không chạy.

**Sửa:** cấu hình `ConditionalRejectingErrorHandler`, converter/type mapping và DLQ phù hợp; kiểm tra log listener container.

### 20.6. Nhầm publisher nack với consumer nack

Publisher confirm `nack` báo kết quả publish từ broker, còn consumer `basic.nack` là hành động settlement delivery. Hai phía không có cùng ý nghĩa hoặc phạm vi.

**Sửa:** đặt tên metrics/log theo phía publisher/consumer; dùng correlation ID/event ID để đối chiếu.

### 20.7. Retry lỗi tạm thời bằng ImmediateRequeue vô hạn

Một database đang down có thể tiếp tục down trong nhiều phút. Requeue trực tiếp chỉ tạo áp lực lên database và broker.

**Sửa:** exponential backoff, retry queue có delay, circuit breaker và DLQ sau ngưỡng; giữ idempotency khi consumer redeliver.

## 21. Bài tập tự kiểm tra

### Bài 1 — Mặc định true

`@RabbitListener` chạy trong `AcknowledgeMode.AUTO`, ném `IllegalStateException`, `defaultRequeueRejected=true` và không có error handler/retry đặc biệt. Chuyện gì thường xảy ra?

**Đáp án gợi ý:** container yêu cầu broker requeue message. Nó có thể redeliver ngay; không có giới hạn retry hoặc backoff chỉ do cờ này.

### Bài 2 — False nhưng không có DLX

Queue `orders.work.q` không khai báo DLX. Container AUTO đặt `defaultRequeueRejected=false`, listener lỗi. Message có nằm trong một DLQ mặc định không?

**Đáp án:** không. Không có DLX và route hợp lệ, message bị reject không requeue có thể bị loại; Spring không tự tạo DLQ.

### Bài 3 — Exception override

Container default=true, listener ném `AmqpRejectAndDontRequeueException`. Có bắt buộc requeue theo cấu hình không?

**Đáp án:** không. Exception này yêu cầu không requeue, ghi đè default.

### Bài 4 — ImmediateRequeue

Container default=false, listener ném `ImmediateRequeueAmqpException`. Điều gì xảy ra và cần lưu ý gì?

**Đáp án:** message được yêu cầu requeue dù default=false. Nếu tiếp tục lỗi thì có thể lặp vô hạn; cần retry có giới hạn và điều tiết.

### Bài 5 — Conversion fatal

Producer gửi JSON sai cú pháp khiến converter ném `MessageConversionException`, mặc dù listener business chưa chạy. Vì sao `defaultRequeueRejected=true` không nhất thiết tạo redelivery vô hạn?

**Đáp án:** default `ConditionalRejectingErrorHandler` có thể nhận diện conversion fatal và chuyển thành reject không requeue để tránh poison-message loop.

### Bài 6 — Nuốt exception

Trong AUTO, listener catch exception, log rồi return. Có thể mong đợi message tự redeliver không?

**Đáp án:** không. Container nhìn thấy handler kết thúc bình thường và có thể ack. Cần đưa lỗi ra tầng phù hợp nếu chưa xử lý xong.

### Bài 7 — MANUAL

Listener đã `basicAck(tag,false)` rồi code ném exception. Có thể gọi `basicNack(tag,false,true)` để quay lại message không?

**Đáp án:** không. Delivery đã settled; settlement lần hai là lỗi và có thể đóng channel.

### Bài 8 — Retry và recoverer

Ứng dụng muốn thử tối đa một số lần với backoff, rồi dead-letter message lỗi. Chỉ dùng `defaultRequeueRejected=true` có đủ không?

**Gợi ý:** không. Dùng Spring Retry có giới hạn, recoverer reject không requeue và DLX phù hợp; test số attempts, DLQ và khả năng xử lý duplicate.

### Bài 9 — DLQ trống nhưng listener lỗi

Listener lỗi và có `RepublishMessageRecoverer` đang chuyển bản lỗi sang một exchange khác. Vì sao DLQ theo `x-dead-letter-exchange` của queue nguồn không tăng?

**Đáp án gợi ý:** recoverer có thể publish message sang tuyến khác rồi kết thúc thành công, khiến nguồn được ack thay vì broker reject/dead-letter. Cần xem error exchange và xác nhận publish.

## 22. Checklist áp dụng production

- [ ] Xác nhận listener container dùng `AcknowledgeMode.AUTO`, `MANUAL` hay `NONE`.
- [ ] Xác định **effective `defaultRequeueRejected`** của đúng listener container/factory, không suy từ một property không được áp dụng.
- [ ] Hiểu default=true là **requeue có thể lặp**, không phải retry hữu hạn có backoff.
- [ ] Trước khi bật default=false, kiểm tra đường DLX/DLQ và chính sách xử lý message bị reject.
- [ ] Phân loại lỗi **permanent**, **transient** và **unknown outcome**; có exception/error handler phù hợp.
- [ ] Dùng `AmqpRejectAndDontRequeueException` chỉ khi có chủ đích không requeue.
- [ ] Tránh lạm dụng `ImmediateRequeueAmqpException` cho lỗi có thể kéo dài.
- [ ] Kiểm tra `ConditionalRejectingErrorHandler` và hành vi fatal conversion/validation theo phiên bản.
- [ ] Nếu dùng Spring Retry, đặt max attempts, backoff, recoverer và cách đếm attempts rõ ràng.
- [ ] Nếu dùng manual ack, settle **một lần trên đúng channel**, không để message unacked vô hạn.
- [ ] Đảm bảo transaction và async listener không ack trước khi xử lý quan trọng hoàn tất.
- [ ] Dùng event ID ổn định và consumer idempotent để xử lý redelivery/duplicate.
- [ ] Theo dõi ready/unacked, redelivery rate, consumer error, retry exhausted và DLQ.
- [ ] Thử RabbitMQ thật các trường hợp normal exception, fatal conversion, special exceptions, DLX thiếu và broker reconnect.
- [ ] Đối chiếu Spring Boot/Spring AMQP/RabbitMQ version, loại queue và cách dead-letter trước khi dùng production.

## 23. Tài liệu tham khảo chính thức

- [Spring AMQP — Resilience: Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): business exception, `defaultRequeueRejected`, `AmqpRejectAndDontRequeueException`, `ImmediateRequeueAmqpException`, retry/recoverer.
- [Spring AMQP 3.2 — Resilience](https://docs.spring.io/spring-amqp/reference/3.2/amqp/resilience-recovering-from-errors-and-broker-failures.html): phiên bản 3.x có thể dùng để đối chiếu.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): `ConditionalRejectingErrorHandler` và fatal exception strategy.
- [Spring AMQP — Listener Container Attributes](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): `defaultRequeueRejected`, `errorHandler` và các ack modes.
- [Spring AMQP — Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html): rollback nhận message và tương tác với requeue.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): các property listener simple/direct theo version.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): settlement semantics, ack/nack/reject và publisher confirm.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): điều kiện dead-letter, cấu hình queue/policies và các hạn chế.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): tác động của unacked deliveries tới QoS/throughput.

**Ghi nhớ:** Với listener AUTO, `defaultRequeueRejected=true` thường khiến exception nghiệp vụ làm **message quay lại queue**; đặt `false` thường khiến **reject không requeue** và chỉ vào DLQ khi queue có tuyến dead-letter hợp lệ. Hai exception đặc biệt có thể ghi đè lựa chọn đó, và `ConditionalRejectingErrorHandler` có thể chặn redelivery cho lỗi fatal trước khi đến listener. Để xử lý bất đồng bộ đáng tin cậy, hãy kết hợp retry có giới hạn, DLX/DLQ được kiểm chứng, acknowledgement đúng mode và consumer idempotent — không dựa vào một cờ duy nhất.
