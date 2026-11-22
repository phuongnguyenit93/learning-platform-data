# Broadcast message cho nhiều subscriber

## 1. Bài toán: một sự kiện, nhiều trách nhiệm

Khi một đơn hàng được tạo, ứng dụng có thể cần ghi nhật ký kiểm toán, gửi thông báo cho khách hàng và cập nhật số liệu vận hành. Cả ba công việc cùng xuất phát từ một sự kiện `OrderCreated`, nhưng mỗi bên quan tâm đến sự kiện vì một lý do khác nhau.

Nếu producer gọi trực tiếp cả ba dịch vụ, nó phải biết danh sách consumer và cách gọi từng dịch vụ. Trong Spring Integration, producer có thể gửi một `Message` vào `PublishSubscribeChannel`; các endpoint đăng ký trên channel sẽ nhận thông điệp để thực hiện trách nhiệm của mình.

Bài học thuộc chương **PublishSubscribeChannel** của module **SPRING_INTEGRATION_CORE**, tập trung vào cách nối `Message`, `MessageChannel`, endpoint, gateway và Java DSL để phát một thông điệp tới nhiều nhánh xử lý. Sau bài học, bạn có thể:

- Phân biệt broadcast với chia tải giữa các consumer.
- Đăng ký nhiều subscriber bằng Java và Java DSL.
- Chọn cách thực thi đồng bộ hoặc dùng executor.
- Giải thích kết quả của `send()`, trường hợp không có subscriber và hành vi khi một nhánh lỗi.
- Nhận biết lúc cần `applySequence` và aggregator.
- Thiết kế ví dụ kiểm thử xác nhận mỗi nhánh nhận đúng thông điệp.

## 2. Broadcast thực sự có nghĩa gì?

### 2.1. Từ producer tới nhiều handler

~~~mermaid
flowchart LR
    P["Producer: OrderCreated"] --> C["PublishSubscribeChannel"]
    C --> A["Subscriber A: Audit"]
    C --> B["Subscriber B: Notification"]
    C --> D["Subscriber C: Metrics"]
~~~

`PublishSubscribeChannel` phát message tới các `MessageHandler` đã đăng ký. Đây là một `SubscribableChannel`: consumer nhận message qua lời gọi `handleMessage(...)`, không gọi `receive()` để lấy dữ liệu ra. API đăng ký gồm `subscribe(handler)` và `unsubscribe(handler)`. [Tham khảo giao diện channel của Spring Integration](https://docs.spring.io/spring-integration/reference/channel/interfaces.html).

Ví dụ, producer gửi `E1` và `E2`, trong lúc ba subscriber đều hoạt động và việc phân phối không gặp lỗi:

| Subscriber | Message nhận được | Trách nhiệm |
| --- | --- | --- |
| Audit | E1, E2 | Lưu dấu vết nghiệp vụ |
| Notification | E1, E2 | Chuẩn bị thông báo |
| Metrics | E1, E2 | Cập nhật số liệu |

Tổng cộng có sáu lượt giao message. Không có phép chia `E1` cho Audit rồi `E2` cho Notification.

“Gửi tới tất cả” mô tả mô hình phân phối. Nó không tạo ra một giao dịch nguyên tử bao trùm mọi subscriber: một nhánh có thể đã tạo tác động bên ngoài trước khi nhánh khác thất bại.

### 2.2. So sánh với các channel thường gặp

| Channel | Cách phân phối | Consumer nhận bằng cách nào? | Ý nghĩa khi có nhiều consumer |
| --- | --- | --- | --- |
| `DirectChannel` | Point-to-point | Handler được gọi trực tiếp | Một handler xử lý một message thành công; có thể có failover khi handler lỗi |
| `ExecutorChannel` | Point-to-point qua executor | Executor thực thi handler | Hỗ trợ chia tải, không tự biến thành broadcast |
| `QueueChannel` | Point-to-point, có hàng đợi | Polling bằng `receive()` hoặc poller | Các consumer cạnh tranh lấy từng message |
| `PublishSubscribeChannel` | Broadcast | Gọi các handler đã subscribe | Mỗi nhánh được đăng ký là một nơi nhận sự kiện |

Sự khác nhau giữa `DirectChannel` và `PublishSubscribeChannel` nằm ở số nơi nhận cho mỗi lần gửi, không phải ở việc “có subscriber hay không”. Cả hai đều có thể có nhiều subscriber. [Tham khảo các triển khai message channel](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### 2.3. Subscriber của channel là thành phần nào?

Trong một flow khai báo, thường có một endpoint đứng giữa channel và logic nghiệp vụ:

~~~text
PublishSubscribeChannel
    -> EventDrivenConsumer endpoint
        -> MessageHandler / service activator
            -> logic nghiệp vụ
~~~

Khi endpoint được start, nó đăng ký handler với channel; khi stop, nó hủy đăng ký. Vì vậy, số lớp service tồn tại trong source code không đồng nghĩa với số subscriber đang hoạt động.

Nếu một subscriber lại chuyển message vào một flow nhiều bước, channel chỉ thấy điểm nhận đầu tiên của nhánh đó. Nó không tự biết nhánh đã gửi email, ghi database hay hoàn tất một yêu cầu HTTP hay chưa.

## 3. Ví dụ Java tối thiểu

Các ví dụ sử dụng Java 17 trở lên để khai báo `record`. Phần channel cần dependency `org.springframework.integration:spring-integration-core`; Java DSL đã nằm trong dependency này. Trong dự án Spring Boot, có thể dùng `spring-boot-starter-integration` và để BOM của dự án quản lý phiên bản.

Các đoạn cấu hình Java DSL dưới đây sử dụng kiểu API `IntegrationFlow.from(...)` của Spring Integration 6 trở lên. Mỗi phương án cấu hình là một ví dụ riêng; không đăng ký đồng thời các phương án có cùng tên bean.

### 3.1. Payload sự kiện

Tạo kiểu dữ liệu dùng chung cho các ví dụ:

~~~java
package example;

import java.math.BigDecimal;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerEmail,
        BigDecimal total) {
}
~~~

`eventId` định danh sự kiện nghiệp vụ, còn `orderId` định danh đơn hàng. Hai giá trị này phục vụ các câu hỏi khác nhau: cùng một đơn hàng có thể phát sinh nhiều sự kiện qua thời gian.

### 3.2. Đăng ký ba subscriber

~~~java
package example;

import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

public class BroadcastDemo {

    public static void main(String[] args) {
        PublishSubscribeChannel orderEvents =
                new PublishSubscribeChannel(true);

        Set<String> observed = new HashSet<>();

        MessageHandler audit = message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            observed.add("audit:" + event.eventId());
        };

        MessageHandler notification = message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            observed.add("notification:" + event.eventId());
        };

        MessageHandler metrics = message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            observed.add("metrics:" + event.eventId());
        };

        orderEvents.subscribe(audit);
        orderEvents.subscribe(notification);
        orderEvents.subscribe(metrics);

        OrderCreated event = new OrderCreated(
                "evt-1001",
                "order-501",
                "customer@example.com",
                new BigDecimal("250000"));

        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader("source", "checkout")
                .build();

        boolean sent = orderEvents.send(message);

        System.out.println("sent=" + sent);
        System.out.println(observed.contains("audit:evt-1001"));
        System.out.println(observed.contains("notification:evt-1001"));
        System.out.println(observed.contains("metrics:evt-1001"));

        orderEvents.unsubscribe(notification);
    }
}
~~~

Kết quả mong đợi:

~~~text
sent=true
true
true
true
~~~

Ví dụ dùng `HashSet` vì channel đang chạy đồng bộ trong thread gửi; không có thao tác ghi đồng thời trong đoạn này. Nếu đổi sang executor, cấu trúc lưu kết quả cũng phải phù hợp với truy cập đồng thời.

Tham số `true` trong constructor là `requireSubscribers`: yêu cầu có subscriber khi gửi. Đây không phải cờ bật xử lý bất đồng bộ.

Lệnh `unsubscribe(notification)` chỉ ảnh hưởng các lần gửi tiếp theo. Nó không thu hồi công việc mà subscriber đã thực hiện và cũng không tạo lịch sử để subscriber nhận lại khi đăng ký lần nữa.

## 4. Cấu hình endpoint bằng Spring

Trong ứng dụng thực tế, nên để Spring quản lý channel và vòng đời endpoint. Ví dụ sau tạo một channel cùng ba service activator:

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class OrderBroadcastConfiguration {

    @Bean
    public PublishSubscribeChannel orderEvents() {
        return new PublishSubscribeChannel(true);
    }

    @Bean
    @ServiceActivator(inputChannel = "orderEvents")
    public MessageHandler auditSubscriber() {
        return message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            System.out.println("audit: " + event.orderId());
        };
    }

    @Bean
    @ServiceActivator(inputChannel = "orderEvents")
    public MessageHandler notificationSubscriber() {
        return message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            System.out.println("notification: " + event.customerEmail());
        };
    }

    @Bean
    @ServiceActivator(inputChannel = "orderEvents")
    public MessageHandler metricsSubscriber() {
        return message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            System.out.println("metrics: " + event.total());
        };
    }
}
~~~

Các lệnh `println` chỉ giúp quan sát nhánh được gọi. Trong ứng dụng, chúng được thay bằng logic lưu audit, tạo yêu cầu thông báo và ghi nhận số liệu.

Có thể khởi động cấu hình và gửi sự kiện như sau:

~~~java
package example;

import java.math.BigDecimal;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class SpringBroadcastDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderBroadcastConfiguration.class)) {

            MessageChannel channel =
                    context.getBean("orderEvents", MessageChannel.class);

            channel.send(MessageBuilder.withPayload(
                    new OrderCreated(
                            "evt-1002",
                            "order-502",
                            "customer@example.com",
                            new BigDecimal("390000")))
                    .build());
        }
    }
}
~~~

Cả ba endpoint đều đăng ký vào `orderEvents`. Nếu thay channel này bằng `DirectChannel`, cấu trúc tên bean có thể vẫn hợp lệ nhưng ý nghĩa phân phối đã thay đổi: bạn không còn có ba bên cùng quan sát mỗi sự kiện.

Với `PublishSubscribeChannel`, không cấu hình poller cho các endpoint nhận trực tiếp từ nó. Poller phù hợp ở ranh giới nhận từ một `PollableChannel`, chẳng hạn `QueueChannel`.

## 5. Tạo các nhánh bằng Java DSL

Java DSL thể hiện rõ ba nhánh nằm cùng sau một điểm broadcast. Phương án dưới đây thay thế cấu hình annotation ở phần trước:

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderDslConfiguration {

    @Bean
    public IntegrationFlow orderBroadcastFlow() {
        return IntegrationFlow.from("orderIngress")
                .publishSubscribeChannel(fanout -> fanout
                        .subscribe(branch -> branch
                                .handle(message -> {
                                    OrderCreated event =
                                            (OrderCreated) message.getPayload();
                                    System.out.println(
                                            "audit: " + event.orderId());
                                }))
                        .subscribe(branch -> branch
                                .filter(OrderCreated.class,
                                        event -> event.customerEmail() != null
                                                && !event.customerEmail()
                                                        .isBlank())
                                .<OrderCreated, String>transform(event ->
                                        "Thông báo đơn hàng "
                                                + event.orderId()
                                                + " tới "
                                                + event.customerEmail())
                                .handle(message ->
                                        System.out.println(
                                                message.getPayload())))
                        .subscribe(branch -> branch
                                .handle(message -> {
                                    OrderCreated event =
                                            (OrderCreated) message.getPayload();
                                    System.out.println(
                                            "metrics: " + event.total());
                                })))
                .get();
    }
}
~~~

Producer gửi `Message<OrderCreated>` vào bean channel `orderIngress`. DSL tạo các subscriber cho channel broadcast bên trong flow.

Trong ví dụ:

- Nhánh audit nhận sự kiện và quan sát `orderId`.
- Nhánh notification tự lọc sự kiện thiếu email, rồi biến payload thành nội dung thông báo.
- Nhánh metrics vẫn nhận sự kiện dù bộ lọc của notification loại message khỏi nhánh notification.

Transformer của nhánh notification tạo kết quả cho chính nhánh đó. Nó không thay payload `OrderCreated` mà các nhánh khác đã nhận bằng một chuỗi.

Có một điểm dễ đọc nhầm: bước đặt tiếp sau `publishSubscribeChannel(...)` trong flow chính có thể trở thành một subscriber bổ sung của điểm broadcast. Nó không phải thao tác tự động đợi và hợp nhất kết quả của tất cả các `subscribe(...)`. [Tài liệu Java DSL về subflow](https://docs.spring.io/spring-integration/reference/dsl/java-subflows.html).

Nếu cần “ba nhánh chạy xong rồi mới xử lý bước cuối”, phải thiết kế đường gom kết quả rõ ràng; chỉ nối thêm một `handle(...)` không tạo ra cơ chế chờ đó.

### 5.1. Đưa gateway vào phía producer

Với cấu hình DSL trên, producer có thể dùng gateway để tránh tự tạo `Message`:

~~~java
package example;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "orderIngress")
public interface OrderEventsGateway {

    void publish(OrderCreated event);
}
~~~

Đăng ký gateway bằng cách thêm annotation sau vào lớp cấu hình được Spring nạp:

~~~java
@IntegrationComponentScan(basePackageClasses = OrderEventsGateway.class)
~~~

Annotation này thuộc package `org.springframework.integration.annotation`. Sau đó, một service có thể inject `OrderEventsGateway` và gọi `publish(event)`.

Kiểu trả về `void` phù hợp với hành vi phát sự kiện một chiều. Tuy nhiên, `void` không có nghĩa là chạy nền: nếu flow phía sau đang đồng bộ, lời gọi gateway vẫn chờ các handler đồng bộ chạy hoặc gặp lỗi.

Không nên để nhiều nhánh tự trả kết quả trực tiếp về cùng một lời gọi gateway rồi coi đó là phép gom kết quả. Hãy xác định một nơi tập hợp các phản hồi trước khi tạo câu trả lời duy nhất.

## 6. Đồng bộ và bất đồng bộ

### 6.1. Mặc định: chạy trong thread gửi

Với constructor không nhận executor:

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
~~~

Các subscriber được gọi trong thread đang thực hiện `send()`. Khi không phát sinh lỗi và các handler không tự chuyển việc sang nơi khác, thời gian gửi bao gồm thời gian thực thi các handler đó.

Giả sử ba handler lần lượt mất khoảng 20 ms, 200 ms và 15 ms:

~~~text
send()
  -> audit:        20 ms
  -> notification: 200 ms
  -> metrics:      15 ms
  -> return
~~~

Thời gian minh họa xấp xỉ 235 ms cộng chi phí phân phối. Subscriber chậm làm producer chậm theo.

Nếu một handler chỉ đẩy việc vào một hàng đợi khác rồi trả về, `send()` chỉ chờ thao tác đẩy đó. Nó không biết công việc cuối hàng đợi đã hoàn tất hay chưa.

### 6.2. Cấp executor để chuyển việc sang worker

Có thể thay bean `orderEvents` ở cấu hình annotation bằng phương án sau, đồng thời bổ sung bean executor:

~~~java
@Bean
public ThreadPoolTaskExecutor broadcastExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(256);
    executor.setThreadNamePrefix("order-broadcast-");
    return executor;
}

@Bean
public PublishSubscribeChannel orderEvents(
        @Qualifier("broadcastExecutor")
        ThreadPoolTaskExecutor executor) {

    return new PublishSubscribeChannel(executor, true);
}
~~~

Các import bổ sung:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
~~~

Spring quản lý khởi tạo và đóng `ThreadPoolTaskExecutor` khi nó là bean. Không cần tự gọi `initialize()` trong phương thức `@Bean` này.

Với thread pool trên, các lời gọi handler được giao cho worker. Các nhánh có thể chạy chồng lấp, tùy số worker rảnh và công việc đang chờ. Cấu hình executor và cách xử lý lỗi của channel được mô tả trong [hướng dẫn cấu hình PublishSubscribeChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

Cần phân biệt:

| Điều quan sát được | Điều có thể kết luận |
| --- | --- |
| `send()` trả về thành công | Lần gửi đáp ứng điều kiện phân phối của channel |
| Executor chấp nhận task | Task được chấp nhận để thực thi |
| Handler kết thúc thành công | Công việc trong lần gọi handler đó đã hoàn thành |
| Email đã được hệ thống đích chấp nhận | Cần kết quả hoặc bằng chứng riêng từ hệ thống gửi email |

Không suy ra dòng cuối chỉ từ dòng đầu.

Một executor có thể thực thi task ngay trên thread gọi; một rejection policy cũng có thể đưa task trở lại thread gửi. Vì vậy, “có tham số executor” chưa đủ để khẳng định lời gọi luôn không chặn hoặc mọi handler luôn ở thread khác.

### 6.3. Chi phí fan-out và giới hạn tài nguyên

Nếu có 100 sự kiện mỗi giây và ba nhánh, executor có thể cần xử lý khoảng 300 lượt gọi handler mỗi giây. Thêm một subscriber làm tăng công việc trên mọi sự kiện tiếp theo.

Với ba nhánh, mỗi lượt tốn trung bình 50 ms, nhu cầu xử lý thô là:

~~~text
100 event/s × 3 nhánh × 0,05 s = 15 worker-second/s
~~~

Đây là phép ước lượng tải, chưa bao gồm thời gian chờ I/O và sự biến động. Nó cho thấy pool bốn worker có thể không theo kịp nếu mỗi worker bị chiếm dụng liên tục trong toàn bộ khoảng thời gian đó.

Đặt giới hạn hàng đợi executor, theo dõi thời gian chờ và xử lý task bị từ chối. Hàng đợi task trong bộ nhớ không cung cấp khả năng phát lại sau khi ứng dụng bị dừng đột ngột.

Nếu executor từ chối một task trong lúc broadcast, một số nhánh trước đó có thể đã được giao việc. Đừng coi việc producer nhận exception là bằng chứng rằng không nhánh nào đã chạy.

## 7. Khi một subscriber lỗi

### 7.1. Đồng bộ: lỗi có thể chặn các subscriber còn lại

Giả sử thứ tự gọi trong một lần gửi là Audit, Notification, Metrics và `ignoreFailures=false`:

~~~text
Audit:        thành công
Notification: ném exception
Metrics:      có thể chưa được gọi
Producer:     nhận exception từ send()
~~~

`ignoreFailures` mặc định là `false`. Với phân phối đồng bộ, dispatcher dừng sớm khi handler ném lỗi; lỗi có thể được bọc trong exception của tầng messaging. Nếu đặt `ignoreFailures=true`, dispatcher cố gắng tiếp tục tới các handler khác và ghi cảnh báo cho lỗi bị bỏ qua. [Javadoc của BroadcastingDispatcher](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/BroadcastingDispatcher.html).

Không nên bật `ignoreFailures` chỉ để producer luôn nhận kết quả đẹp. Ví dụ, nếu Audit là yêu cầu bắt buộc, việc bỏ qua lỗi Audit khiến yêu cầu nghiệp vụ chưa được đáp ứng dù các nhánh khác tiếp tục chạy.

### 7.2. Bất đồng bộ: producer không bắt được lỗi xử lý về sau bằng try/catch thông thường

Khi handler chạy trên worker sau khi producer đã rời `send()`, exception của handler không thể tự quay về call stack cũ.

Spring Integration hỗ trợ phát `ErrorMessage`, với payload là lỗi, tới channel trong header `errorChannel` của message hoặc channel toàn cục tên `errorChannel`. Cơ chế mặc định này liên quan đến task do framework thực thi; nó không tự áp dụng cho mọi lời gọi đồng bộ chỉ vì message có header `errorChannel`. [Tài liệu xử lý lỗi](https://docs.spring.io/spring-integration/reference/error-handling.html).

Có thể gửi message tới channel broadcast dùng executor với header lỗi riêng:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(
                org.springframework.messaging.MessageHeaders.ERROR_CHANNEL,
                "broadcastErrors")
        .build();

orderEvents.send(message);
~~~

Và thêm endpoint quan sát lỗi vào cùng application context:

~~~java
@Bean
public MessageChannel broadcastErrors() {
    return new DirectChannel();
}

@Bean
@ServiceActivator(inputChannel = "broadcastErrors")
public MessageHandler broadcastErrorHandler() {
    return message -> {
        Throwable failure = (Throwable) message.getPayload();
        System.err.println("Broadcast failed: " + failure.getMessage());
    };
}
~~~

Import bổ sung cho đoạn cấu hình:

~~~java
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;
~~~

Trong hệ thống thực tế, handler lỗi cần ghi được định danh sự kiện, nhánh thất bại và thông tin hỗ trợ xử lý tiếp. Một `MessagingException` có thể cung cấp `failedMessage`; hãy kiểm tra giá trị trước khi truy cập.

Nếu tự cấu hình `ErrorHandler` cho `PublishSubscribeChannel`, phải xác định rõ nó ghi nhận lỗi hay chuyển lỗi đi đâu. Chiến lược `ErrorHandler` của channel dành cho trường hợp channel có executor; nó không biến exception đồng bộ thành thông báo lỗi một cách tự động.

### 7.3. Retry cả broadcast có thể lặp tác động đã thành công

Xét tình huống:

1. Audit lưu thành công.
2. Notification gọi dịch vụ ngoài và thất bại.
3. Producer gửi lại toàn bộ sự kiện.
4. Audit nhận lại sự kiện đã xử lý.

Nếu audit chỉ thêm dòng mới mỗi lần nhận, bạn có thể có bản ghi trùng. Nếu một email thực tế đã gửi nhưng phản hồi bị mất, gửi lại còn có thể làm khách nhận hai email.

Một thiết kế thường dễ kiểm soát hơn là retry tại nhánh thất bại, đồng thời làm các tác động quan trọng có khả năng chống xử lý trùng.

Ví dụ khóa nghiệp vụ cho một bản ghi xử lý:

~~~text
(eventId, subscriberName)
("evt-1001", "audit")
("evt-1001", "notification")
~~~

Mỗi subscriber có tiến độ riêng. Định danh `MessageHeaders.ID` phục vụ message instance; khi xây lại message hoặc tạo thông điệp mới, không nên mặc nhiên coi ID đó là định danh ổn định của sự kiện nghiệp vụ.

`PublishSubscribeChannel` tự nó không cung cấp retry bền vững, giao hàng đúng một lần hoặc rollback email đã gửi.

## 8. Không có subscriber và ý nghĩa của send()

Bốn lựa chọn thường cần đọc rõ trong cấu hình:

| Lựa chọn | Mặc định | Mục đích |
| --- | --- | --- |
| `requireSubscribers` | `false` với constructor mặc định | Từ chối lần gửi khi không có subscriber nếu đặt `true` |
| `minSubscribers` | `0` | Ngưỡng tối thiểu dùng để đánh giá kết quả phân phối |
| `ignoreFailures` | `false` | Quyết định có bỏ qua lỗi handler để tiếp tục cố gắng phân phối hay không |
| `applySequence` | `false` | Bổ sung thông tin sequence cho các bản message đi tới subscriber |

Có thể tạo các channel với yêu cầu khác nhau:

~~~java
PublishSubscribeChannel optionalEvents =
        new PublishSubscribeChannel();

PublishSubscribeChannel requiredEvents =
        new PublishSubscribeChannel(true);

PublishSubscribeChannel needsTwoSubscribers =
        new PublishSubscribeChannel(true);
needsTwoSubscribers.setMinSubscribers(2);
~~~

Với channel mặc định không có subscriber, `send()` có thể trả về `true` vì ngưỡng tối thiểu là 0. Message không được giữ lại để giao khi một subscriber xuất hiện sau đó.

Với `requireSubscribers=true`, không có subscriber là một lỗi phân phối. Constructor nhận executor cũng có biến thể `new PublishSubscribeChannel(executor, true)`. Chi tiết các constructor và lựa chọn nằm trong [Javadoc PublishSubscribeChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html).

`minSubscribers` không phải cam kết có đúng các subscriber nghiệp vụ mà bạn mong muốn. Có hai subscriber cũng chưa chắc đó là Audit và Notification; chúng có thể là hai endpoint cấu hình nhầm.

Ở chế độ có executor, kết quả phân phối không phải kết quả xử lý cuối cùng của các nhánh. Đừng dùng `minSubscribers` như một cơ chế chờ “ít nhất hai email gửi thành công”. Nếu cần kết quả như vậy, hãy thu thập phản hồi hoặc lưu trạng thái nghiệp vụ.

Lưu ý thêm: timeout truyền vào `send(message, timeout)` không phải deadline cưỡng chế dừng tất cả subscriber. Một handler đồng bộ gọi HTTP quá lâu vẫn cần timeout tại HTTP client; công việc bất đồng bộ cần chính sách thời hạn riêng.

## 9. applySequence và đường gom kết quả

### 9.1. Broadcast không tự tổng hợp phản hồi

Có hai bài toán khác nhau:

- Phát sự kiện cho Audit, Notification và Metrics: mỗi bên thực hiện trách nhiệm của mình.
- Gửi yêu cầu tới ba nhà cung cấp giá rồi chọn kết quả: producer cần một kết quả tổng hợp.

Bài toán thứ hai cần thêm đường trả kết quả và một thành phần gom, chẳng hạn aggregator hoặc cấu hình scatter-gather. `PublishSubscribeChannel` chỉ đảm nhiệm phần phát tới các nhánh. [Tài liệu Scatter-Gather](https://docs.spring.io/spring-integration/reference/scatter-gather.html).

~~~mermaid
flowchart LR
    P["Yêu cầu báo giá"] --> C["Broadcast"]
    C --> A["Nhánh A"]
    C --> B["Nhánh B"]
    C --> D["Nhánh C"]
    A --> G["Channel gom kết quả"]
    B --> G
    D --> G
    G --> AG["Aggregator"]
    AG --> R["Một kết quả tổng hợp"]
~~~

### 9.2. Bật metadata sequence khi thiết kế cần nó

~~~java
@Bean
public PublishSubscribeChannel quoteRequests() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel(true);
    channel.setApplySequence(true);
    return channel;
}
~~~

Với một lượt fan-out ba subscriber, thông tin minh họa có dạng:

| Bản gửi tới | `correlationId` | `sequenceNumber` | `sequenceSize` |
| --- | --- | --- | --- |
| Nhánh thứ nhất | Cùng nhóm | 1 | 3 |
| Nhánh thứ hai | Cùng nhóm | 2 | 3 |
| Nhánh thứ ba | Cùng nhóm | 3 | 3 |

`sequenceNumber` thể hiện vị trí trong sequence được tạo cho lượt phân phối; nó không phải số thứ tự hoàn tất công việc.

Aggregator mặc định sử dụng thông tin tương quan và sequence để nhận biết nhóm có đủ thành viên. Khi dùng chiến lược này, mỗi nhánh cần đưa kết quả phù hợp vào cùng đường gom và giữ lại metadata cần thiết. [Tài liệu Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html).

Một lỗi thiết kế điển hình:

~~~text
Broadcast có 3 subscriber
  -> A trả kết quả
  -> B bị filter loại bỏ nên không trả gì
  -> C trả kết quả

Aggregator chờ nhóm đủ 3 kết quả.
~~~

Nhóm có thể không đủ điều kiện release. Cần thiết kế rõ cách biểu diễn kết quả bị từ chối, timeout nhóm hoặc chiến lược release khác.

Tương tự, thêm một subscriber chỉ để logging vào điểm broadcast có `applySequence=true` có thể làm tăng `sequenceSize`, trong khi subscriber đó không đưa kết quả về aggregator. Việc thêm một nhánh quan sát cũng có thể thay đổi điều kiện hoàn tất nếu bạn dùng số subscriber làm số thành viên mong đợi.

Không cần bật `applySequence` cho mọi luồng sự kiện. Nếu Audit, Notification và Metrics độc lập, metadata sequence thường không phục vụ yêu cầu gom nào.

## 10. Message bất biến không đồng nghĩa payload bất biến sâu

Theo mô hình message của Spring, không thay trực tiếp cấu trúc headers và không gán lại payload reference của một message đã tạo. Tuy nhiên, đối tượng nằm trong payload hoặc trong một giá trị header vẫn có thể là đối tượng mutable. [Tài liệu Message và MessageHeaders](https://docs.spring.io/spring-integration/reference/message.html).

Ví dụ nguy hiểm:

~~~java
Map<String, Object> payload = new HashMap<>();
payload.put("status", "CREATED");

// Subscriber A:
payload.put("status", "NOTIFIED");

// Subscriber B cũng có thể đang đọc chính Map này.
~~~

Khi các nhánh chia sẻ cùng đối tượng, A có thể làm B quan sát dữ liệu khác với sự kiện ban đầu. Với nhiều thread, đây còn là rủi ro tranh chấp dữ liệu.

Khi `applySequence=false`, channel có thể giao cùng message instance cho các subscriber. Khi bật sequence, các message bao có headers khác nhau vẫn có thể dùng cùng payload reference; không có phép deep copy payload tự động.

Các cách thiết kế phù hợp:

- Phát event DTO với trạng thái đã chốt tại thời điểm xảy ra sự kiện.
- Dùng kiểu dữ liệu bất biến cho các trường; sao chép collection khi dựng event nếu cần.
- Tạo đối tượng kết quả riêng tại mỗi nhánh.
- Không chia sẻ một entity đang được quản lý bởi persistence context giữa các worker.

`record` ở ví dụ `OrderCreated` có các trường `String` và `BigDecimal` nên phù hợp cho việc chia sẻ này. Một `record` chứa `List` vẫn cần quan tâm nội dung list có thể bị sửa hay không.

## 11. Thứ tự, transaction và phạm vi triển khai

### 11.1. Thứ tự gọi không phải thứ tự hoàn thành

Trong chế độ đồng bộ, có thể cấu hình thứ tự endpoint khi cần kiểm soát thứ tự dispatch. Khi dùng executor, nhánh được giao trước vẫn có thể hoàn thành sau.

Đừng biểu diễn quan hệ phụ thuộc nghiệp vụ bằng hai subscriber riêng rồi kỳ vọng subscriber sau luôn nhìn thấy kết quả subscriber trước:

~~~text
Sai về mô hình phụ thuộc:
    broadcast -> trừ tồn kho
              -> xác nhận đã trừ tồn kho
~~~

Nếu xác nhận chỉ được phép sau khi trừ tồn kho thành công, hãy nối thành chuỗi hoặc tạo sự kiện mới sau bước trừ tồn kho:

~~~text
Yêu cầu -> trừ tồn kho thành công -> InventoryReserved
                                      -> broadcast cho các bên quan tâm
~~~

Broadcast phù hợp khi các bên cùng quan sát một sự kiện đã được xác lập.

### 11.2. Channel không tự mở transaction bao trùm các subscriber

Nếu producer đang có transaction gắn với thread và các handler chạy đồng bộ, thao tác hỗ trợ transaction ở phía sau có thể tham gia transaction đó tùy cấu hình của chúng.

Khi chuyển sang worker thread, transaction gắn với thread của producer không tự đi theo task. Muốn nhánh có transaction thì phải thiết kế transaction tại nhánh đó hoặc dùng cơ chế bàn giao phù hợp. [Tài liệu transaction và ranh giới thread](https://docs.spring.io/spring-integration/reference/transactions.html).

Ngay cả khi các thao tác database cùng rollback được, email đã gửi hoặc yêu cầu HTTP đã tạo tác động bên ngoài thường không thể bị “thu hồi” bằng rollback database.

Nếu nghiệp vụ yêu cầu chỉ phát sự kiện sau khi đơn hàng commit, cần chọn cơ chế phát sau commit hoặc mô hình như outbox kết hợp nơi chuyển tiếp sự kiện. `PublishSubscribeChannel` không tự giải quyết tính nhất quán giữa database và thông báo bên ngoài.

### 11.3. Channel này nằm trong ứng dụng đang chạy

`org.springframework.integration.channel.PublishSubscribeChannel` là channel trong tiến trình ứng dụng. Nó không tự phát tới những JVM khác.

Nếu ứng dụng có ba instance và message được gửi vào channel của instance thứ nhất, chỉ các subscriber gắn với channel đó nhận message. Subscriber ở instance thứ hai không trở thành nơi nhận chỉ vì bean có cùng tên.

Nếu cần phân phối giữa các tiến trình, phát lại sau restart hoặc lưu đệm bền vững, hãy đưa một transport hay message store phù hợp vào thiết kế. Một topic, một consumer group và một hàng đợi có thể có mô hình phân phối khác nhau; phải kiểm tra yêu cầu “mỗi dịch vụ đều nhận” ở tầng đó.

## 12. Kiểm thử hành vi broadcast

Các ví dụ kiểm thử dùng JUnit Jupiter và dependency core. Chúng tập trung vào hợp đồng phân phối, không kiểm tra việc gửi email thật.

### 12.1. Hai subscriber phải cùng nhận message

~~~java
package example;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class PublishSubscribeChannelTest {

    @Test
    void broadcastsToEverySubscriber() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel(true);

        QueueChannel audit = new QueueChannel();
        QueueChannel notification = new QueueChannel();

        channel.subscribe(message -> audit.send(message));
        channel.subscribe(message -> notification.send(message));

        Message<OrderCreated> original = MessageBuilder.withPayload(
                new OrderCreated(
                        "evt-test-1",
                        "order-test-1",
                        "customer@example.com",
                        new BigDecimal("100000")))
                .build();

        assertTrue(channel.send(original));

        assertSame(original, audit.receive(0));
        assertSame(original, notification.receive(0));

        assertNull(audit.receive(0));
        assertNull(notification.receive(0));
    }

    @Test
    void defaultChannelDoesNotRequireSubscribers() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel();

        assertTrue(channel.send(
                MessageBuilder.withPayload("event").build()));
    }

    @Test
    void requiredChannelRejectsWhenThereAreNoSubscribers() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel(true);

        assertThrows(MessagingException.class, () ->
                channel.send(
                        MessageBuilder.withPayload("event").build()));
    }
}
~~~

`receive(0)` giúp phép kiểm tra không chờ vô hạn nếu không có dữ liệu. Hai channel đích trong test chỉ là nơi giữ message để quan sát kết quả; chúng không làm thay đổi mô hình broadcast của channel nguồn.

Phép kiểm tra `assertSame` phù hợp với cấu hình mặc định chưa bật sequence và không có interceptor thay message. Nếu bật `applySequence`, hãy kiểm tra payload và các header cần thiết thay vì bắt buộc cùng message instance.

### 12.2. Xác nhận send() không đợi handler trên worker hoàn tất

Dùng latch để giữ hai handler trong lúc xác nhận lời gọi gửi đã trở về. Cách này không phụ thuộc một khoảng `sleep` đoán trước.

~~~java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

import static java.util.concurrent.TimeUnit.SECONDS;
import static org.junit.jupiter.api.Assertions.*;

class AsyncBroadcastTest {

    @Test
    void sendReturnsBeforeSubscribersComplete() throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(2);

        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(2);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        try {
            PublishSubscribeChannel channel =
                    new PublishSubscribeChannel(workers, true);

            channel.setErrorHandler(failure::set);
            channel.afterPropertiesSet();

            channel.subscribe(message -> {
                started.countDown();
                awaitRelease(release);
                finished.countDown();
            });

            channel.subscribe(message -> {
                started.countDown();
                awaitRelease(release);
                finished.countDown();
            });

            assertTrue(channel.send(
                    MessageBuilder.withPayload("event").build()));

            assertTrue(started.await(5, SECONDS));
            assertEquals(2L, finished.getCount());

            release.countDown();

            assertTrue(finished.await(5, SECONDS));
            assertNull(failure.get());
        } finally {
            release.countDown();
            workers.shutdownNow();
            workers.awaitTermination(5, SECONDS);
        }
    }

    private static void awaitRelease(CountDownLatch release) {
        try {
            if (!release.await(10, SECONDS)) {
                throw new IllegalStateException(
                        "Subscriber did not receive release signal");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(exception);
        }
    }
}
~~~

Đây là channel tạo ngoài Spring context, nên test gọi `afterPropertiesSet()` và cung cấp `ErrorHandler` tường minh. Trong ứng dụng có bean channel, Spring thực hiện bước khởi tạo vòng đời tương ứng.

Điều quan trọng của test là: hai handler đã bắt đầu, cả hai đang bị giữ ở latch, nhưng `send()` đã trả về. Điều đó chứng minh kết quả gửi và kết quả hoàn tất subscriber là hai mốc khác nhau.

### 12.3. Những tình huống nên kiểm tra khi áp dụng vào nghiệp vụ

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Một nhánh ném lỗi trong chế độ đồng bộ | Producer thấy lỗi và các tác động đã xảy ra được nhận diện |
| Một nhánh trên worker thất bại | Lỗi đi đến nơi quan sát hoặc xử lý được cấu hình |
| Filter loại message tại một nhánh | Nhánh khác vẫn nhận; đường gom không bị chờ thiếu kết quả ngoài ý muốn |
| Subscriber bị stop | Hành vi không có subscriber hoặc thiếu subscriber đúng với yêu cầu |
| Producer gửi lại cùng `eventId` | Các tác động cần chống trùng được bảo vệ |
| Executor đầy | Task bị từ chối được phát hiện; không giả định mọi nhánh đều chưa chạy |
| Bật `applySequence` | Metadata nhóm có mặt và được bảo toàn qua các bước trả kết quả |

Khi kiểm thử thứ tự lỗi đồng bộ, hãy cấu hình thứ tự handler hoặc endpoint tường minh. Khi kiểm thử nhiều thread, dùng latch hay cơ chế chờ có timeout; không suy luận thứ tự hoàn tất từ thứ tự khai báo nhánh.

## 13. Bài tập thực hành

Xây dựng luồng `OrderCreated` có ba nhánh Audit, Notification và Metrics theo các bước:

1. Dùng channel đồng bộ, lưu kết quả từng nhánh vào nơi quan sát riêng. Gửi một sự kiện và xác nhận cả ba nơi đều nhận.
2. Thêm filter cho Notification để bỏ qua đơn hàng không có email. Xác nhận Audit và Metrics vẫn hoạt động.
3. Cho Notification ném lỗi có chủ đích. Quan sát kết quả gửi và xác định các nhánh đã chạy trong thứ tự được cấu hình.
4. Dùng executor có giới hạn hàng đợi. Ghi tên thread ở producer và từng handler để nhận diện ranh giới thực thi.
5. Đưa lỗi bất đồng bộ vào `broadcastErrors`, kèm khả năng truy tìm `eventId` thất bại.
6. Gửi lại cùng sự kiện và bổ sung cơ chế chống ghi audit trùng theo khóa nghiệp vụ.
7. Với một luồng báo giá riêng, bật `applySequence` rồi gom kết quả. Thử để một nhánh không trả về và quyết định cách timeout hoặc trả kết quả từ chối.

Kết quả cần giải thích được bằng hành vi channel: bên nào nhận, xử lý trên thread nào, lỗi đi đâu và producer đang biết đến mốc nào của quá trình xử lý.

## 14. Các nguyên tắc cần nhớ

- `PublishSubscribeChannel` dùng để nhiều nhánh cùng quan sát một message; channel chia tải có mục tiêu khác.
- Broadcast mặc định chạy đồng bộ. Muốn chuyển công việc sang worker phải cấp executor phù hợp.
- Kết quả `send()` không chứng minh tác động nghiệp vụ cuối cùng của mọi nhánh đã hoàn tất.
- Lỗi một nhánh không tự rollback tác động bên ngoài của những nhánh đã chạy.
- Giữ payload an toàn để chia sẻ; message bao bất biến không tạo ra deep copy.
- Chỉ dùng `applySequence` khi thiết kế cần metadata nhóm, và phải xử lý cả trường hợp thiếu kết quả.
- Nếu bước sau phụ thuộc bước trước, hãy biểu diễn bằng chuỗi hoặc bằng sự kiện sau khi bước trước thành công.
- Chọn cơ chế bền vững và retry riêng khi yêu cầu cần sống qua restart hoặc cần khôi phục từng subscriber.
