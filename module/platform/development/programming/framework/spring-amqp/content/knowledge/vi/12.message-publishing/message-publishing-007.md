# Gửi nhiều thông điệp trong cùng phạm vi channel với Spring AMQP

Khi cần phát liên tiếp hàng chục hoặc hàng trăm event bằng `RabbitTemplate`, một vấn đề không dễ thấy là **mỗi lần gọi publish thông thường có thể lấy một channel khác nhau** từ `CachingConnectionFactory`. Điều đó thường hoàn toàn phù hợp, nhưng nếu bạn muốn gửi một nhóm message trên cùng AMQP channel và chờ broker xác nhận cả nhóm, cần một phạm vi thực thi rõ ràng. Spring AMQP cung cấp `RabbitTemplate.invoke(...)` với `OperationsCallback` để thực hiện điều đó.

Bài học thuộc chương **Gửi thông điệp** của module **SPRING_AMQP**: tích hợp RabbitMQ bằng `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding; thực hành định tuyến, xác nhận giao nhận, retry, dead-letter, giao dịch và quan sát hệ thống xử lý bất đồng bộ đáng tin cậy. Trọng tâm ở đây là **gửi nhiều message trong cùng phạm vi channel**, kết hợp publisher confirms đúng cách và hiểu giới hạn của phương pháp.

## 1. Bạn sẽ học được gì?

Sau bài này, bạn có thể:

1. Phân biệt AMQP **connection**, **channel**, **lệnh publish** và **phạm vi callback** của `RabbitTemplate`.
2. Giải thích sự khác biệt giữa nhiều lời gọi `convertAndSend(...)` thông thường và nhiều lời gọi trong `invoke(OperationsCallback)`.
3. Viết publisher gửi một nhóm message trên cùng channel và đợi xác nhận bằng `waitForConfirms(...)` hoặc `waitForConfirmsOrDie(...)`.
4. Nhận diện tín hiệu publisher confirm, publisher return và lỗi channel mà không nhầm chúng với consumer acknowledgement.
5. Phân biệt **cùng channel**, **batch publishing**, **giao dịch** và **bảo đảm xử lý đúng một lần**.
6. Tránh lỗi đa luồng, giữ channel quá lâu, tái gửi trùng và nghẽn channel cache; biết cách kiểm thử với RabbitMQ thật.

## 2. Mô hình connection → channel → nhiều lần publish

AMQP 0-9-1 cho phép một TCP/AMQP connection chứa nhiều channel logic. Một ứng dụng Spring thường sử dụng `CachingConnectionFactory` để cấp, cache và tái sử dụng channel cho `RabbitTemplate` cũng như listener containers.

~~~mermaid
flowchart LR
    APP["Service Java"] --> RT["RabbitTemplate"]
    RT --> CF["CachingConnectionFactory"]
    CF --> CON["AMQP connection<br/>TCP/TLS"]
    CON --> CH1["Channel #1"]
    CON --> CH2["Channel #2"]
    CH1 --> R["RabbitMQ broker"]
    CH2 --> R
    R --> E["Exchange"]
    E --> Q["Queue"]
    Q --> L["@RabbitListener"]
~~~

| Đơn vị | Có vai trò gì? | Điều không thể suy ra |
|---|---|---|
| **Connection** | Phiên mạng/AMQP giữa client và broker | Một connection không chỉ có một channel |
| **Channel** | Luồng giao thức logic để publish, consume và nhận confirms | Một channel không đồng nghĩa một queue hay một transaction |
| **Publish** | Gửi một message tới exchange với routing key | Không có nghĩa listener đã xử lý |
| **Phạm vi `invoke`** | Giữ các thao tác dùng cùng dedicated channel trong callback | Không tự gộp các message thành một message hay một commit |

Ví dụ:

~~~java
rabbitTemplate.convertAndSend("orders.events", "order.created", "A");
rabbitTemplate.convertAndSend("orders.events", "order.created", "B");
rabbitTemplate.convertAndSend("orders.events", "order.created", "C");
~~~

Ba lời gọi trên **có thể** dùng cùng channel nếu channel được trả về cache và được lấy lại, nhưng **không có cam kết** đó, nhất là khi ứng dụng có nhiều thread publish song song. Mỗi thao tác được framework quản lý phạm vi lấy/trả channel riêng.

Điều này thường không phải lỗi: các lời gọi độc lập không nhất thiết cần biết channel ID. Nhưng nếu bạn muốn chờ confirms cho **tất cả message của một nhóm trên chính channel đang publish**, cần thiết lập phạm vi thích hợp.

## 3. RabbitTemplate.invoke(...): phạm vi channel có kiểm soát

Từ Spring AMQP 2.0, `RabbitTemplate` cung cấp phương thức `invoke`, nhận một `RabbitOperations.OperationsCallback<T>`. Callback được truyền một đối tượng `RabbitOperations`; những lời gọi thực hiện **trên đối tượng đó, trong cùng thread và trong callback** sử dụng **cùng dedicated channel**.

~~~mermaid
sequenceDiagram
    participant S as Publisher service
    participant T as RabbitTemplate
    participant CH as Dedicated channel
    participant B as RabbitMQ broker
    S->>T: invoke(operations -> ...)
    T->>CH: Mở / nhận channel cho scope
    S->>T: operations.convertAndSend(M1)
    T->>CH: basic.publish(M1)
    CH->>B: Publish M1
    S->>T: operations.convertAndSend(M2)
    T->>CH: basic.publish(M2)
    CH->>B: Publish M2
    S->>T: operations.waitForConfirmsOrDie(timeout)
    T->>CH: Wait publisher confirms
    B-->>CH: Publisher ack/nack
    CH-->>T: Kết quả hoặc lỗi timeout
    T-->>S: Kết thúc invoke
    Note over T,CH: Scope kết thúc, channel được xử lý theo lifecycle framework
~~~

Giao diện callback có dạng:

~~~java
@FunctionalInterface
public interface OperationsCallback<T> {
    T doInRabbit(RabbitOperations operations);
}
~~~

Đây là **mô tả chữ ký** để hiểu API, không phải interface cần khai báo lại trong dự án. Khi sử dụng:

~~~java
Boolean result = rabbitTemplate.invoke(operations -> {
    operations.convertAndSend("orders.events", "order.created", "M1");
    operations.convertAndSend("orders.events", "order.created", "M2");
    return true;
});
~~~

Hai thao tác `convertAndSend` được thực hiện trên cùng channel trong scope này. Đối với `RabbitTemplate` thông thường, sau mỗi operation riêng lẻ channel có thể được trả về cache. Còn `invoke` dành một channel chuyên dụng trong thời gian callback; khi scope kết thúc, framework đóng channel chuyên dụng theo cơ chế của nó, ngoại trừ trường hợp `PublisherCallbackChannel` có thể được trả về cache sau khi nhận đủ confirms theo phiên bản/cấu hình. **Không giả định channel chắc chắn còn giữ nguyên cho lần `invoke` kế tiếp.**

Điểm cần nhớ: `invoke` có nghĩa **nhiều thao tác trong một scope sử dụng chung channel**; không có nghĩa `RabbitTemplate` sẽ giữ một channel riêng cố định cho cả vòng đời bean.

## 4. Ví dụ hoàn chỉnh: gửi một nhóm event

Giả sử publisher phát các event đơn hàng vào direct exchange `orders.events` với routing key `order.created`. Để tập trung vào channel, ví dụ gửi **String** (định dạng text); nếu muốn gửi DTO JSON, hãy cấu hình `MessageConverter` JSON phù hợp phiên bản Spring AMQP.

### 4.1. Khai báo topology dùng trong bài thực hành

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderRoutingConfiguration {

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange("orders.events", true, false);
    }

    @Bean
    Queue ordersCreatedQueue() {
        return QueueBuilder.durable("orders.created.q").build();
    }

    @Bean
    Binding ordersCreatedBinding(DirectExchange ordersExchange,
                                 Queue ordersCreatedQueue) {
        return BindingBuilder.bind(ordersCreatedQueue)
                .to(ordersExchange)
                .with("order.created");
    }
}
~~~

Khi có `RabbitAdmin` hoạt động và quyền cấu hình phù hợp, Spring có thể khai báo exchange, queue và binding cho broker. Nếu topology do hạ tầng quản lý, không nên tạo thêm định nghĩa trùng nhưng khác properties. Đảm bảo producer và consumer dùng cùng virtual host.

### 4.2. Gửi nhiều message trong scope

~~~java
import java.util.List;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderBatchPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrderBatchPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public int publishOrders(List<String> orderIds) {
        if (orderIds == null || orderIds.isEmpty()) {
            return 0;
        }

        return rabbitTemplate.invoke(operations -> {
            for (String orderId : orderIds) {
                operations.convertAndSend(
                        "orders.events",
                        "order.created",
                        "OrderCreated:" + orderId
                );
            }
            return orderIds.size();
        });
    }
}
~~~

Đọc ví dụ theo thứ tự:

1. `invoke` bắt đầu một scope với channel chuyên dụng.
2. Các lời gọi `operations.convertAndSend(...)` cùng nằm trong callback và chạy trên thread gọi.
3. `RabbitTemplate` sử dụng message converter để chuyển String thành body bytes và gửi từng message đến exchange.
4. `return orderIds.size()` chỉ trả số lần **đã gọi publish**, **không chứng minh** broker đã accept hay consumer đã xử lý.
5. Callback hoàn tất và framework giải phóng channel theo lifecycle tương ứng.

Đây là **nhiều lệnh publish AMQP**, không phải một message chứa cả List. Nếu business yêu cầu gửi một JSON array như một message duy nhất, đó là cách thiết kế payload khác.

### 4.3. Consumer nhận event

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @RabbitListener(queues = "orders.created.q")
    public void onOrderCreated(String body) {
        // Xử lý nghiệp vụ an toàn khi message có thể được giao lại.
        System.out.println("Received " + body);
    }
}
~~~

Việc listener nhận String phù hợp với payload text của ví dụ. `@RabbitListener` không sử dụng channel của publisher; consumer có channel riêng do listener container quản lý. **Cùng channel giữa các lệnh publish không đồng nghĩa publisher và consumer dùng chung channel.**

## 5. Gửi cả nhóm rồi đợi publisher confirms

Trường hợp sử dụng `invoke` rất quan trọng là **chờ tất cả publisher confirms** sau khi gửi một nhóm message. Để sử dụng `waitForConfirms(...)` và `waitForConfirmsOrDie(...)`, connection factory phải được bật publisher confirms và hai lời gọi phải nằm **trong scope `invoke`**.

Trong các phiên bản Spring Boot hỗ trợ cấu hình tương ứng:

~~~properties
spring.rabbitmq.publisher-confirm-type=simple
~~~

`ConfirmType.SIMPLE` là chế độ thuận tiện cho việc chờ confirms theo nhóm mà không cần hạ tầng tương quan mỗi message. Spring AMQP cũng có `ConfirmType.CORRELATED` để theo dõi confirms theo `CorrelationData`. Chọn cấu hình theo mục tiêu của publisher và xem tài liệu **đúng Spring Boot/Spring AMQP version**.

### 5.1. waitForConfirms(timeout): trả kết quả boolean

~~~java
import java.util.List;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ConfirmedOrderPublisher {

    private final RabbitTemplate rabbitTemplate;

    public ConfirmedOrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishAndConfirm(List<String> ids) {
        if (ids.isEmpty()) {
            return;
        }

        boolean allAcked = rabbitTemplate.invoke(operations -> {
            for (String id : ids) {
                operations.convertAndSend(
                        "orders.events", "order.created", "OrderCreated:" + id
                );
            }
            return operations.waitForConfirms(10_000);
        });

        if (!allAcked) {
            throw new IllegalStateException(
                    "At least one publish was negatively confirmed"
            );
        }
    }
}
~~~

Ở mức nhóm, `waitForConfirms(10_000)` chờ các publish đang chờ confirm trên **dedicated channel của scope** với timeout tính bằng mili giây. Nó trả `true` khi các publisher confirmations tương ứng đều là ack; có thể trả `false` nếu có nack và ném exception khi timeout/lỗi channel tùy tình huống.

`allAcked = true` không có nghĩa tất cả message đã tới queue **dự kiến** hoặc `@RabbitListener` đã chạy; cần xem **publisher returns** để phát hiện các publish không route được, và xử lý outcome nghiệp vụ riêng.

### 5.2. waitForConfirmsOrDie(timeout): báo lỗi nếu confirm không đạt

~~~java
public void publishAndRequireConfirms(
        RabbitTemplate rabbitTemplate, List<String> payloads) {

    rabbitTemplate.invoke(operations -> {
        for (String payload : payloads) {
            operations.convertAndSend(
                    "orders.events", "order.created", payload
            );
        }
        operations.waitForConfirmsOrDie(10_000);
        return null;
    });
}
~~~

`waitForConfirmsOrDie` phù hợp khi bạn muốn scope thất bại bằng exception nếu broker nack hoặc quá thời gian đợi. Đây là **lỗi kết quả publish ở cấp nhóm**, không tự chỉ ra ID nào đã được broker nhận thành công. Nếu kết quả không chắc chắn, việc gửi lại cả nhóm có thể tạo **message trùng**. Ví dụ production cần outbox hoặc danh sách trạng thái publish cùng khóa idempotency để quyết định retry.

**Không gọi**:

~~~java
// SAI: waitForConfirms ngoài một scope invoke thích hợp.
rabbitTemplate.convertAndSend(
        "orders.events", "order.created", "OrderCreated:O-1001");
rabbitTemplate.waitForConfirmsOrDie(10_000);
~~~

Do channel có thể được trả về cache sau lời gọi gửi bình thường, `waitForConfirmsOrDie` không có dedicated channel của scope để chờ. Spring AMQP quy định các API chờ confirm trên template phải được gọi trong `invoke`.

## 6. Scope là một channel, không phải một transaction nguyên tử

Đây là điểm quan trọng nhất về độ tin cậy. Giả sử bạn gửi M1, M2, M3 trong `invoke`:

~~~text
Channel A:
    basic.publish(M1)
    basic.publish(M2)
    basic.publish(M3)
    waitForConfirms(...)
~~~

Broker có thể đã nhận M1 và M2 rồi channel bị lỗi trước khi M3 được xác nhận. **Việc dùng cùng channel không tạo một đơn vị atomic commit cho ba publish**; không có cơ chế tự rollback M1/M2 nếu M3 gặp lỗi.

| Cơ chế | Cam kết chính | Không tự bảo đảm |
|---|---|---|
| `RabbitTemplate.invoke` | Các thao tác trong callback cùng thread dùng chung channel | Atomicity, tính đúng một lần |
| Publisher confirms | Broker thông báo kết quả xử lý publish ở cấp channel | Consumer hoàn tất, publish chắc chắn vào queue mục tiêu |
| Publisher returns | Message có thể được trả về nếu không route được khi `mandatory=true` | Consumer xử lý thành công |
| AMQP channel transaction | `txSelect/txCommit/txRollback` cho các operation hỗ trợ trong transaction | Một giao dịch phân tán ACID giữa RabbitMQ và database |
| Consumer acknowledgement | Consumer báo kết quả xử lý một delivery với broker | Producer biết trạng thái business end-to-end |
| Transactional outbox | Lưu ý định phát event cùng transaction database nghiệp vụ | Broker/consumer tự chống trùng nếu không có idempotency |

Không thể dùng publisher confirms và channel transactions **đồng thời trên cùng một channel**, vì đó là hai chế độ điều khiển khác nhau của AMQP. Nếu yêu cầu một nhóm publish có giao dịch AMQP, phải tìm hiểu `channelTransacted` hoặc quản lý transaction riêng đúng cách; nếu yêu cầu atomicity giữa database và RabbitMQ, thường cần outbox hay một cơ chế điều phối phù hợp.

### Khi code đã nằm trong transaction của listener

Spring AMQP có thể giữ một **transactional channel** gắn với listener container thread khi dùng template và container được cấu hình transacted. Lúc đó các thao tác phù hợp có thể vốn đã nằm trong cùng transactional context, không cần dùng thêm `invoke` chỉ để lấy cùng channel. Đây là trường hợp đặc biệt cần đọc rõ hướng dẫn transaction theo phiên bản.

Không bọc `invoke` và `@Transactional` một cách máy móc rồi mặc định nhóm publish vừa có confirms vừa được commit atomically. Phải chọn rõ **mục tiêu**: đảm bảo publish được broker xác nhận, hay đưa publish vào một giao dịch AMQP cục bộ.

## 7. Publisher confirm khác publisher return và lỗi exchange

Một nhóm message đã được broker **ack** vẫn có thể chứa message không định tuyến được. Ví dụ, cùng direct exchange `orders.events`:

- M1 có routing key `order.created` khớp binding.
- M2 có routing key `order.unknown` không khớp binding.
- M3 có routing key `order.created` khớp binding.

Nếu `mandatory=false`, M2 có thể bị drop mà publisher vẫn nhận confirm ack cho publish tương ứng. Nếu `mandatory=true` và publisher returns được bật, broker có thể trả M2 với `basic.return` / `312 NO_ROUTE` trong khi confirm vẫn ack. Vì thế `waitForConfirmsOrDie` không thay vai trò **returns**.

### 7.1. Bật returns nếu cần phát hiện unroutable

Với Spring Boot version hỗ trợ các properties:

~~~properties
spring.rabbitmq.publisher-confirm-type=simple
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
~~~

Để quan sát, đăng ký `ReturnsCallback` **trên chính `RabbitTemplate` dùng publish**:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

// Cấu hình tập trung trong bean/template của ứng dụng:
rabbitTemplate.setReturnsCallback(returned -> {
    System.err.printf(
            "NO_ROUTE? reply=%d reason=%s exchange=%s key=%s%n",
            returned.getReplyCode(),
            returned.getReplyText(),
            returned.getExchange(),
            returned.getRoutingKey()
    );
});
~~~

Trong snippet này, `rabbitTemplate` là bean đã cấu hình và đoạn code phải đặt ở nơi ứng dụng **sở hữu callback**. `RabbitTemplate` chỉ hỗ trợ một returns callback chính; nhiều component không nên tự ghi đè nhau. Ngoài ra, `mandatory` và `publisher-returns` cần thực sự được bật, và nếu tự tạo template/factory thì phải cấu hình trực tiếp thay vì kỳ vọng mọi property Boot tự áp dụng.

### 7.2. Exchange không tồn tại

Nếu bất kỳ publish nào gửi đến exchange không tồn tại, broker có thể đóng channel với lỗi `404 NOT_FOUND`. Điều này khác với `basic.return NO_ROUTE`. Khi một channel đóng lúc đang chờ confirms, toàn bộ scope có thể thất bại hoặc không xác định rõ message nào đã được broker nhận.

Hệ thống cần log exception/channel shutdown, đánh dấu trạng thái nhóm là **không chắc chắn** nếu thích hợp và dùng idempotency nếu retry. Đừng xem việc không thấy một callback return là bằng chứng các message đã được route vào queue.

## 8. Khi cần xác nhận từng message: CORRELATED thay cho kết quả cả nhóm

`waitForConfirms` trả một kết quả tổng hợp của các publish đang chờ trên channel. Khi cần biết **message ID nào ack/nack, message nào return**, `ConfirmType.CORRELATED` cùng `CorrelationData` thường phù hợp hơn.

Ví dụ gửi từng message với correlation ID:

~~~java
import org.springframework.amqp.rabbit.connection.CorrelationData;

CorrelationData correlation = new CorrelationData("event-1001");
rabbitTemplate.convertAndSend(
        "orders.events",
        "order.created",
        "OrderCreated:O-1001",
        correlation
);

// Với connection factory có ConfirmType.CORRELATED,
// có thể theo dõi correlation.getFuture() theo API đúng phiên bản.
~~~

Với `ConfirmType.CORRELATED`, bạn có thể đăng ký `ConfirmCallback` hoặc theo dõi `CorrelationData.getFuture()` theo API của phiên bản Spring AMQP sử dụng. Nếu `publisherReturns` và `mandatory` được bật, `CorrelationData` còn có thể giúp đối chiếu returned message trong những phiên bản hỗ trợ.

**Không chọn cấu hình `SIMPLE` và `CORRELATED` như thể hai công tắc độc lập trên cùng connection factory.** Chúng là các lựa chọn `ConfirmType`, phù hợp với hai cách xử lý confirms khác nhau. Khi cần kết quả **theo nhóm**, scoped `invoke` cùng `waitForConfirmsOrDie` đơn giản hơn; khi cần trạng thái **từng event**, dùng correlation ID/future/outbox.

### Callback của từng confirm trong invoke

Spring AMQP còn có overload:

~~~java
<T> T invoke(
    RabbitOperations.OperationsCallback<T> action,
    com.rabbitmq.client.ConfirmCallback acks,
    com.rabbitmq.client.ConfirmCallback nacks
);
~~~

Đây là **chữ ký API dạng minh họa**. Hai callback ở overload này là `com.rabbitmq.client.ConfirmCallback` của RabbitMQ Java client, nhận **delivery tag và cờ multiple** theo channel, **khác** `RabbitTemplate.ConfirmCallback` nhận `CorrelationData`.

~~~java
rabbitTemplate.invoke(operations -> {
    operations.convertAndSend("orders.events", "order.created", "M1");
    operations.convertAndSend("orders.events", "order.created", "M2");
    operations.waitForConfirmsOrDie(10_000);
    return null;
}, (deliveryTag, multiple) -> {
    System.out.println("Publisher ACK tag=" + deliveryTag);
}, (deliveryTag, multiple) -> {
    System.err.println("Publisher NACK tag=" + deliveryTag);
});
~~~

Delivery tag trong confirms có **phạm vi channel**, không phải message ID nghiệp vụ toàn cục. `multiple=true` cho biết confirm có thể bao phủ nhiều sequence numbers; đừng suy mỗi callback tương ứng đúng một message theo thứ tự log.

## 9. ChannelCallback và RabbitTemplate.execute(...): tầng API thấp hơn

Nếu cần thao tác trực tiếp với `com.rabbitmq.client.Channel`, `RabbitTemplate.execute(ChannelCallback<T>)` cho phép dùng **cùng channel trong một callback**:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.rabbit.core.ChannelCallback;

rabbitTemplate.execute((ChannelCallback<Void>) channel -> {
    byte[] first = "OrderCreated:O-1001"
            .getBytes(StandardCharsets.UTF_8);
    byte[] second = "OrderCreated:O-1002"
            .getBytes(StandardCharsets.UTF_8);

    channel.basicPublish("orders.events", "order.created", null, first);
    channel.basicPublish("orders.events", "order.created", null, second);
    return null;
});
~~~

Đoạn này có **hai lệnh `basic.publish` trực tiếp**, không đi qua `MessageConverter` của `RabbitTemplate`. Vì truyền `null` cho AMQP BasicProperties, đoạn ví dụ cũng không chủ động đặt content type, delivery mode, messageId hay headers. Trước khi áp dụng production, phải tự quản lý metadata tương ứng.

| Tiêu chí | `RabbitTemplate.invoke` | `RabbitTemplate.execute(ChannelCallback)` |
|---|---|---|
| Cấp API | `RabbitOperations` và các thao tác template | RabbitMQ Java client `Channel` |
| Cùng channel trong callback | Có | Có |
| `convertAndSend` / converter | Dùng được trực tiếp trên đối tượng `operations` | Phải tự serialize bytes khi gọi `basicPublish` |
| `waitForConfirms` cấp template | Được thiết kế cho scope `invoke` | Nếu cần low-level confirm phải quản lý đúng cơ chế channel |
| Phù hợp | Nhiều thao tác Spring AMQP và chờ confirms | Trường hợp cần API `Channel` mà abstraction chưa cung cấp |
| Rủi ro | Hiểu sai scope/confirm/transaction | Quên metadata, tự quản lý confirm/transaction và lỗi channel |

Không tự gọi `channel.close()` bên trong callback của template, vì framework quản lý lifecycle channel. Không lưu channel nhận được để sử dụng ngoài callback hoặc giao cho thread khác.

## 10. Một scope không phải một batch vật lý

Trong bài này, **nhóm message** nghĩa là nhiều lệnh publish liên tiếp trong một callback `invoke`. Điều đó khác với:

- **Một message có body là JSON array** chứa nhiều bản ghi.
- **BatchingRabbitTemplate** hoặc batching strategy ghép nhiều payload theo định dạng batch của framework.
- **RabbitMQ Streams** với mô hình producer/confirmation khác AMQP 0-9-1 queue thông thường.
- **AMQP transaction** gom các thao tác theo chế độ `txSelect/txCommit`.

| Phương án | Đơn vị gửi tới broker | Consumer thường nhìn thấy gì? | Trường hợp phù hợp |
|---|---|---|---|
| `invoke` + N `convertAndSend` | N message AMQP riêng | N delivery riêng nếu được route/tiêu thụ | Cần cùng channel, xác nhận nhóm |
| `convertAndSend` một List qua JSON | Một message với body là JSON array | Một delivery chứa N phần tử logic | Consumer có nghiệp vụ xử lý cả nhóm |
| Framework batching | Batch envelope/định dạng riêng tùy strategy | Có thể cần de-batch ở consumer | Tối ưu throughput khi hai phía thống nhất format |
| Local AMQP transaction | Các thao tác được bao trong transaction cấp channel | Message được commit theo transaction | Cần transaction tại broker và chấp nhận chi phí |

Không gọi `invoke` là “bulk API gửi 100 message trong một network frame” hoặc “batch commit”. Các lệnh publish vẫn tồn tại riêng, publisher confirms vẫn gắn với channel/sequence numbers và routing vẫn được broker thực hiện cho từng message.

## 11. Thứ tự message và ranh giới thread

Các thao tác trong một callback `invoke` diễn ra **trên cùng thread** và cùng channel, nên thứ tự gửi lệnh được duy trì trong phạm vi callback. Nhưng không có bảo đảm tổng quát rằng **mọi consumer trên mọi queue xử lý xong theo thứ tự đó**.

Ví dụ khó:

~~~text
Thread A: invoke(...publish M1, M2...)
Thread B: invoke(...publish M3, M4...)
~~~

Thread A và B có thể sử dụng **hai dedicated channels khác nhau**. `invoke` của mỗi thread không áp đặt thứ tự chung giữa hai scope. Khi nhiều consumer, retry/requeue, priority hay các queue khác nhau tham gia, thứ tự xử lý có thể khác thứ tự producer tạo event.

### Không chuyển công việc sang thread khác trong callback

~~~java
// SAI: không bảo đảm runnable trên executor tiếp tục cùng scope/channel.
rabbitTemplate.invoke(operations -> {
    executor.execute(() ->
            operations.convertAndSend(
                    "orders.events", "order.created", "M2"));
    operations.convertAndSend(
            "orders.events", "order.created", "M1");
    return null;
});
~~~

Ví dụ trên chỉ minh họa **anti-pattern**, không phải code cần sử dụng. Callback của `invoke` gắn với thread; runnable chạy sau đó có thể ngoài scope, dùng channel khác, hoặc gây race. Không chuyển `operations`/channel sang `CompletableFuture`, thread pool hay giữ làm field.

Nếu cần thứ tự nghiêm ngặt khi nhiều thread cùng publish tới một queue, phải thiết kế serialization hoặc áp giới hạn publisher channel phù hợp. Spring AMQP có hướng dẫn sử dụng **publisher connection factory riêng, channel cache size 1 và channel checkout timeout dương** cho một số bài toán strict ordering đa luồng; đánh đổi là throughput thấp hơn và nguy cơ nghẽn. Đừng cấu hình toàn bộ consumer dùng chung một channel chỉ để ép thứ tự publisher.

## 12. Channel cache, timeout và thời gian giữ scope

`invoke` chiếm một channel cho đến khi callback hoàn tất. Vì vậy callback quá dài có thể làm tăng số channel đang được sử dụng, gây chờ đợi hoặc lỗi timeout nếu channel checkout được giới hạn.

| Thiết lập | Điều cần hiểu |
|---|---|
| `spring.rabbitmq.cache.channel.size` | Số channel nhàn rỗi được cache; **không luôn là hard limit** nếu checkout timeout = 0 |
| `spring.rabbitmq.cache.channel.checkout-timeout` | Nếu dương, cache size có thể đóng vai trò giới hạn channel và người gọi chờ channel khả dụng |
| `spring.rabbitmq.publisher-confirm-type` | Chọn chế độ confirms (`simple`, `correlated`...) |
| `waitForConfirmsOrDie(timeout)` | Timeout chờ broker xác nhận nhóm publisher sequence đang chờ trên channel |
| `spring.rabbitmq.requested-heartbeat` | Phát hiện peer connection không còn phản hồi; **không** phải timeout cho từng publish |

Ví dụ Spring Boot cho phòng lab:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: simple
    cache:
      channel:
        size: 20
        checkout-timeout: 2s
~~~

Giá trị 20 channel và 2 giây chỉ là minh họa. Với `checkout-timeout` dương, số channel có thể bị giới hạn và các scope đồng thời cần cạnh tranh tài nguyên. Không đặt `size=1` cùng nhiều publisher/consumer trong production nếu chưa đánh giá đủ nhu cầu, đặc biệt khi dùng chung connection factory.

**Thực hành tốt:** giữ callback ngắn, chỉ làm các thao tác publish và xác nhận cần thiết. Tránh gọi API ngoài, truy vấn database chậm hoặc `Thread.sleep(...)` trong `invoke`. Nếu nhóm có hàng chục nghìn message, hãy chia thành các nhóm có giới hạn để tránh giữ channel quá lâu, timeout lớn và khó xác định partial success khi lỗi.

## 13. Thiết kế retry an toàn khi một nhóm bị lỗi

Giả sử nhóm gồm 3 event có `eventId` cố định:

~~~text
E1: evt-101
E2: evt-102
E3: evt-103
~~~

Producer publish E1 và E2; trước khi nhận confirms cho tất cả, connection đứt. Những trạng thái có thể xảy ra:

| E1 | E2 | E3 | Producer có thể biết chắc điều gì? |
|---|---|---|---|
| Broker đã nhận | Broker đã nhận | Chưa gửi | Nếu không có confirms tương ứng, kết quả publisher chỉ biết **không chắc chắn** |
| Broker đã nhận | Chưa nhận | Chưa gửi | Không thể suy toàn bộ nhóm đã thất bại |
| Chưa nhận | Chưa nhận | Chưa nhận | Có thể retry nhưng không được chỉ suy ra từ lỗi connection |

Vì vậy, **retry lại toàn bộ nhóm** khi timeout/exception có thể dẫn đến event trùng. Các nguyên tắc quan trọng:

1. Định danh sự kiện bằng **event ID ổn định**; retry giữ nguyên ID của logical event.
2. Với nghiệp vụ quan trọng, lưu trạng thái tạo event trong **transactional outbox** hoặc cơ chế đáng tin cậy tương tự.
3. Phân biệt lỗi kết nối tạm thời với lỗi routing cố định (`NO_ROUTE`, exchange thiếu) và lỗi dữ liệu.
4. Consumer thiết kế **idempotent** theo event ID, tránh xử lý thanh toán/hóa đơn nhiều lần.
5. Đo tần suất nhóm timeout, publisher nack, returns và số message trong DLQ; không chỉ đo `convertAndSend` không ném exception.
6. Không nghĩ một `waitForConfirmsOrDie` thành công là transaction giữa RabbitMQ và database.

Một quy trình outbox thường là lưu event và dữ liệu nghiệp vụ trong một transaction database, sau đó worker đọc outbox, publish với ID ổn định, xác nhận, rồi đánh dấu đã phát. Khi xác nhận mất nhưng broker đã nhận, worker có thể gửi lại; consumer vẫn phải xử lý trùng an toàn.

## 14. Quan sát channel và nhóm publish

Một nhóm xuất bản nên có:

- **batchId** do ứng dụng đặt để liên hệ một lần chạy `invoke`.
- **eventId** riêng cho từng logical event; không dùng channel number/delivery tag làm business ID.
- **exchange**, **routing key**, **virtual host** và số message gửi.
- Thời gian bắt đầu/kết thúc scope; thời gian đợi confirms; `ack/nack/timeout` của nhóm.
- Số message trả về vì `NO_ROUTE`, lỗi channel/connection và lần retry.

Ví dụ log **minh họa**:

~~~text
publish.scope.start batchId=batch-2026-01 count=3 exchange=orders.events
publish.scope.confirmed batchId=batch-2026-01 count=3 elapsedMs=37
publish.scope.start batchId=batch-2026-02 count=3 exchange=orders.events
publish.scope.failed batchId=batch-2026-02 reason=confirm-timeout
~~~

Không log toàn bộ body/headers khi chúng có dữ liệu cá nhân hoặc bí mật. Với RabbitMQ Management UI, theo dõi số connections/channels, channel churn, publish/confirm rates, queue depth và consumer ack rates; đừng suy channel “đang mở” đồng nghĩa nó đang publish thành công.

### Dấu hiệu quá tải scope

- Channel count tăng mạnh theo concurrency.
- Người gọi bị `AmqpTimeoutException` khi checkout channel với cache giới hạn.
- Thời gian chờ confirm tăng khi broker chậm hoặc chịu resource alarms.
- Publisher retry liên tục và làm tăng traffic, kéo theo backlog/consumer delay.

Hướng xử lý cần có số liệu: giới hạn số nhóm chạy đồng thời, cân chỉnh channel cache/executor, giảm kích thước nhóm, xử lý bottleneck ở broker/queue/consumer. **Chỉ tăng timeout** không giải quyết backlog tăng mãi.

## 15. Kịch bản kiểm thử thực hành

### Bước chuẩn bị

1. Dùng RabbitMQ test và topology `orders.events` → `orders.created.q` của mục 4.
2. Cấu hình publisher confirms dạng `simple`.
3. Đảm bảo một consumer `@RabbitListener` đọc message text hoặc tạm dừng listener nếu cần quan sát queue.
4. Thêm event ID hoặc batchId vào log và dùng tên message test riêng để tránh trùng dữ liệu thật.

### Phép thử A — Hai lời gọi cùng channel

Gửi M1 và M2 trong một `invoke`, thêm `waitForConfirmsOrDie` rồi quan sát logs. Kết quả mong đợi là không ném exception nếu broker xác nhận cả hai. Để chứng minh cùng channel, có thể dùng overload `invoke` nhận ack/nack callbacks và quan sát publisher sequence tags trong **scope**; không cần dựa vào channel number không ổn định giữa các scope.

### Phép thử B — Không dùng invoke

Gọi `convertAndSend` ba lần trực tiếp rồi thử dùng `RabbitTemplate.waitForConfirmsOrDie` ngoài callback. Hãy giải thích vì sao API này yêu cầu dedicated scope. Không triển khai anti-pattern vào code thật.

### Phép thử C — Routing sai

Đổi routing key từ `order.created` sang `order.unknown`. Với direct exchange chỉ có binding đầu tiên, nếu `mandatory=true` và publisher returns được bật thì nhận `NO_ROUTE`. Publisher confirms của nhóm vẫn có thể ack. Đây là minh chứng **confirm không tương đương routed-to-expected-queue**.

### Phép thử D — Exchange thiếu

Publish một message tới `orders.missing` chưa được khai báo trong vhost test. Quan sát lỗi `404 NOT_FOUND`/channel shutdown và kết quả của scope, đồng thời kiểm tra khả năng khôi phục. Đừng chạy trên broker dùng chung nếu không kiểm soát topology.

### Phép thử E — Mất connection khi đang chờ confirm

Chạy riêng môi trường test; mô phỏng gián đoạn kết nối sau khi gửi một vài event nhưng trước khi kết quả nhóm được biết đầy đủ. Kiểm tra producer lưu trạng thái **không chắc chắn** và consumer không xử lý trùng khi retry.

### Phép thử F — Scope chạy đồng thời

Cho hai thread gọi `invoke` cùng lúc, mỗi thread có batchId riêng. Quan sát channel usage và thứ tự message. Nêu vì sao hai scope không tạo thứ tự publish chung. Tăng concurrency chỉ khi broker, application executor và channel cache chịu được tải.

### Ma trận kết quả cần ghi

| Thử nghiệm | Cùng channel trong một scope | Publisher confirm | Điều phải xác minh thêm |
|---|---|---|---|
| A: `invoke` hai message | Có | Ack nhóm nếu broker xác nhận | Queue nhận và consumer xử lý riêng |
| B: Gửi độc lập | Không bảo đảm | Chờ confirm trên template ngoài scope không hợp lệ | Dùng correlated confirms nếu cần theo event |
| C: Routing sai | Có thể có | Vẫn có thể ack | Publisher return và binding |
| D: Exchange thiếu | Scope có thể lỗi vì channel đóng | Có thể thiếu confirm/exception | Lỗi channel 404 |
| E: Mất kết nối | Scope không hoàn tất bình thường | Kết quả có thể không rõ | Idempotency và outbox |
| F: Hai scope đa luồng | Mỗi scope có channel riêng | Kết quả từng scope | Không suy thứ tự toàn cục |

## 16. Bài tập tư duy và lời giải gợi ý

### Bài 1 — invoke có phải transaction?

Một developer nói: “Ba `convertAndSend` trong cùng `invoke` sẽ hoặc cùng thành công, hoặc cùng thất bại.” Nhận định đúng hay sai?

**Gợi ý:** sai. Các message vẫn là các publish riêng; cùng channel không tạo atomic commit/rollback. Một phần message có thể đã được broker nhận trước khi phần còn lại lỗi.

### Bài 2 — Nên chờ confirm ở đâu?

Bạn muốn chờ xác nhận cả 20 event trên cùng channel. Nên gọi `waitForConfirmsOrDie` sau callback hay bên trong callback?

**Đáp án:** bên trong callback `invoke`, sau khi gửi hết event. Phương thức trên template yêu cầu dedicated channel scope.

### Bài 3 — Ack nhưng message không đến queue

Broker confirm ack tất cả publish nhưng consumer không nhận một event vì routing key sai. Có mâu thuẫn không?

**Gợi ý:** không. Ack của publisher xác nhận broker xử lý publish, message có thể không route được. Bật `mandatory=true`, returns và kiểm tra `NO_ROUTE`.

### Bài 4 — Chạy async trong invoke

Một developer tạo `CompletableFuture.runAsync` bên trong `invoke`, dùng biến `operations` ở future để publish. Rủi ro gì?

**Gợi ý:** scope gắn với thread; future có thể chạy ngoài scope và không dùng cùng channel, gây vấn đề thứ tự/lifecycle. Giữ thao tác publish đồng bộ trong callback hoặc thiết kế riêng từng scope cho worker.

### Bài 5 — Kết quả theo nhóm hay theo event?

Một ứng dụng muốn biết event `evt-302` thất bại trong 500 event và chỉ retry đúng event đó. Dùng `waitForConfirmsOrDie` theo nhóm đã đủ chưa?

**Gợi ý:** chưa. Kết quả nhóm không cung cấp ánh xạ từng event. Dùng `ConfirmType.CORRELATED`, `CorrelationData` có ID ổn định hoặc quản lý publish state/outbox ở mức từng event.

### Bài 6 — Tối ưu tài nguyên

Publisher có 50 thread, mỗi thread giữ một scope `invoke` 30 giây để gọi API bên ngoài. Hệ quả gì?

**Gợi ý:** scope giữ channel lâu, có thể cạn channel khi cache bị giới hạn và làm tăng latency. Đưa I/O ngoài scope, chia nhóm vừa phải và theo dõi số channel, timeout và confirms.

### Bài 7 — Đảm bảo thứ tự khi nhiều thread

Nếu hai thread cùng gửi tới một queue và thứ tự là yêu cầu nghiệp vụ, chỉ bọc từng thread trong `invoke` có đủ không?

**Gợi ý:** không. Hai scope không dùng chung channel nên không có thứ tự liên thread. Cân nhắc serialization ở publisher hoặc cơ chế bounded channel trên dedicated publisher connection theo tài liệu; vẫn cần xét consumer concurrency/requeue.

## 17. Checklist áp dụng vào dự án

- [ ] Xác nhận `RabbitTemplate.invoke(OperationsCallback)` có trong phiên bản Spring AMQP đang dùng (API từ 2.0).
- [ ] Gửi trên đối tượng `operations` được cấp trong callback; không giữ đối tượng này ngoài scope hoặc chuyển qua thread khác.
- [ ] Phân biệt `RabbitTemplate.invoke` với `execute(ChannelCallback)` và batching payload/framework.
- [ ] Bật publisher confirms và chọn `ConfirmType.SIMPLE` cho chờ confirm theo nhóm, hoặc `CORRELATED` cho theo dõi từng event khi phù hợp.
- [ ] Gọi `waitForConfirms` hoặc `waitForConfirmsOrDie` **trong scope `invoke`**.
- [ ] Nếu cần phát hiện unroutable, bật mandatory + publisher returns, quan sát `NO_ROUTE` riêng với confirm ack.
- [ ] Xử lý exchange thiếu/channel close và kết quả không chắc chắn; không retry toàn nhóm một cách mù quáng.
- [ ] Không coi cùng channel là transaction nguyên tử, publisher ack là consumer ack hay confirms là exactly-once.
- [ ] Gắn eventId/batchId, giữ ID ổn định qua retry và triển khai idempotency tại consumer.
- [ ] Giữ scope ngắn, giới hạn số message/batch và số scope đồng thời; theo dõi channel cache/checkout timeout.
- [ ] Xem xét thứ tự giữa nhiều thread, nhiều channel và nhiều consumer nếu nghiệp vụ có yêu cầu ordering.
- [ ] Thử với RabbitMQ test: publish đúng, NO_ROUTE, exchange thiếu, broker reconnect, nack/timeout và consumer redelivery.

## 18. Nguồn tài liệu để đối chiếu phiên bản

- [Spring AMQP Reference — AmqpTemplate, Scoped Operations](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `invoke`, `waitForConfirms`, `waitForConfirmsOrDie`, callbacks theo channel và giới hạn đa luồng.
- [Spring AMQP 3.2 — Scoped Operations](https://docs.spring.io/spring-amqp/reference/3.2/amqp/template.html): tài liệu nhánh 3.2 cho dự án dùng Spring AMQP 3.x.
- [Spring AMQP Reference — Connections and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): `CachingConnectionFactory`, channel cache và publisher connection.
- [Spring AMQP API — RabbitTemplate / RabbitOperations](https://docs.spring.io/spring-amqp/api/): chữ ký `invoke`, `OperationsCallback`, xác nhận publisher theo đúng version.
- [RabbitMQ — Publisher Confirms and Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms): phân biệt `basic.ack` từ broker và acknowledgement của consumer.
- [RabbitMQ — Channels](https://www.rabbitmq.com/docs/channels): kênh logic, vòng đời, lỗi channel và giới hạn.

**Ghi nhớ:** `RabbitTemplate.invoke(...)` giúp **nhiều thao tác publish trong một callback cùng thread dùng một dedicated channel**, phù hợp khi cần chờ publisher confirms cho cả nhóm. Nhưng channel chung **không tự tạo transaction**, **không bảo đảm message đến queue mong đợi** và **không loại bỏ nguy cơ xử lý trùng**. Kết hợp confirms, returns, logging, retry có trạng thái và consumer idempotent mới giúp luồng publish Spring AMQP vận hành có thể kiểm chứng.
