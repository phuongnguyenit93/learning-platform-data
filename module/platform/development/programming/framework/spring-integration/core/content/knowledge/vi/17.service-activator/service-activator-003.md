# Input channel của service activator

Trong module **SPRING_INTEGRATION_CORE**, chương **Service activator**, bài này giải thích cách nối một service vào luồng thông điệp qua input channel. Việc chọn channel ảnh hưởng trực tiếp đến cách endpoint nhận message, thread thực thi, khả năng chờ, phân phối công việc và đường đi của lỗi.

Sau bài học, bạn có thể:

- Xác định input channel của một service activator trong annotation và Java DSL.
- Phân biệt cơ chế subscribe với polling.
- Chọn channel theo nhu cầu gọi đồng bộ, đệm công việc hoặc phát sự kiện.
- Cấu hình poller khi đầu vào là `QueueChannel`.
- Kiểm thử đường vào, kết quả và lỗi mà không dựa vào thời gian ngủ cố định.

## 1. Input channel là điểm nhận message của endpoint

Service activator nối một đối tượng do Spring quản lý với hệ thống messaging. Input channel cung cấp message cho endpoint; handler bên trong endpoint chuyển message thành lời gọi phương thức nghiệp vụ. Kết quả trả về có thể tiếp tục được gửi ra luồng thông điệp. Xem [Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html).

~~~mermaid
flowchart LR
    P["Producer hoặc gateway"] -->|"send(Message)"| C["Input channel"]
    C --> E["Consumer endpoint"]
    E --> H["Handler của service activator"]
    H --> S["Phương thức nghiệp vụ"]
    S -->|"Nếu có kết quả"| O["Output channel hoặc replyChannel"]
~~~

Ví dụ với yêu cầu xác nhận đơn hàng:

~~~text
OrderCommand
    -> orderInput
    -> service activator
    -> OrderService.confirm(...)
    -> confirmations
~~~

Ở đây:

| Thành phần | Trách nhiệm |
| --- | --- |
| Producer | Tạo message và gửi vào `orderInput` |
| `orderInput` | Cung cấp cơ chế chuyển giao hoặc lưu đệm message |
| Consumer endpoint | Kết nối channel với handler và quản lý việc tiêu thụ |
| Handler | Ánh xạ message sang lời gọi `confirm(...)` |
| `OrderService` | Thực hiện nghiệp vụ xác nhận đơn hàng |
| `confirmations` | Nhận kết quả do service trả về |

Tên input channel là tên đích messaging trong `ApplicationContext`, không phải URL và cũng không phải tên phương thức Java.

Chữ “input” mang tính tương đối: cùng một channel có thể là output của router ở bước trước và input của service activator ở bước sau. Vì vậy, khi đọc flow, hãy xác định cả thành phần gửi vào channel và endpoint tiêu thụ channel đó.

## 2. Loại channel quyết định cách endpoint nhận message

`MessageChannel` cung cấp thao tác `send(...)`. Hai interface quan trọng cho phía nhận là:

- `SubscribableChannel`: quản lý các handler đăng ký nhận thông điệp bằng `subscribe(...)`.
- `PollableChannel`: cung cấp `receive(...)` để phía tiêu thụ chủ động lấy thông điệp.

Đây là hai hợp đồng khác nhau; không phải mọi channel đều có thể được đọc bằng `receive()`. Xem [MessageChannel interfaces](https://docs.spring.io/spring-integration/reference/channel/interfaces.html).

Spring Integration tổ chức consumer endpoint tương ứng:

| Input channel | Cách tiêu thụ | Endpoint thông thường |
| --- | --- | --- |
| `SubscribableChannel` | Đăng ký handler; channel dispatch khi có message | `EventDrivenConsumer` |
| `PollableChannel` | Lên lịch lấy message rồi gọi handler | `PollingConsumer` |

Với channel có thể subscribe, endpoint không cần một poller chỉ để nhận message. Với channel có thể poll, phải có cơ chế lập lịch cho việc nhận. Cơ chế đó thuộc endpoint; business service vẫn tập trung vào phương thức xử lý. Xem [Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html).

Cần tách riêng hai câu hỏi:

1. Endpoint nhận message bằng subscribe hay polling?
2. Handler thực thi trên thread nào?

Subscribe không đồng nghĩa với chạy trên thread của producer. Chẳng hạn, `ExecutorChannel` vẫn có thể subscribe nhưng giao việc cho executor.

## 3. Ví dụ hoàn chỉnh với DirectChannel và annotation

Ví dụ dưới đây dùng Java 17 trở lên để khai báo `record`. Ứng dụng cần dependency `spring-integration-core`; phần kiểm thử cần JUnit Jupiter. Phiên bản Spring và Spring Integration cần được quản lý đồng bộ bằng cấu hình dependency của dự án.

Đây là cấu hình Java thuần, khởi tạo được bằng `AnnotationConfigApplicationContext`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.handler.annotation.Header;

@Configuration
@EnableIntegration
public class OrderInputConfiguration {

    public record OrderCommand(String orderId, int quantity) {
    }

    @Bean
    public DirectChannel orderInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel confirmations() {
        return new QueueChannel(20);
    }

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    public static class OrderService {

        @ServiceActivator(
                inputChannel = "orderInput",
                outputChannel = "confirmations")
        public String confirm(
                OrderCommand command,
                @Header(value = "tenantId", required = false)
                String tenantId) {

            if (command.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity phải lớn hơn 0");
            }

            return "CONFIRMED:" + command.orderId();
        }
    }
}
~~~

`@EnableIntegration` đăng ký hạ tầng xử lý các endpoint. `OrderService` được tạo thành Spring bean qua `@Bean` nên annotation trên phương thức của nó được xử lý. Nếu chỉ tạo `new OrderService()` rồi giữ ở ngoài Spring context, sẽ không có endpoint tự đăng ký vào channel. Cách nhận payload và header được mô tả trong [Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html).

Producer gửi vào channel như sau:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

try (var context =
        new AnnotationConfigApplicationContext(
                OrderInputConfiguration.class)) {

    var input = context.getBean("orderInput", DirectChannel.class);
    var output = context.getBean("confirmations", QueueChannel.class);

    Message<?> request = MessageBuilder
            .withPayload(
                    new OrderInputConfiguration.OrderCommand(
                            "OD-001", 2))
            .setHeader("tenantId", "tenant-a")
            .build();

    boolean sent = input.send(request);
    Message<?> reply = output.receive(0);

    System.out.println(sent);               // true
    System.out.println(reply.getPayload()); // CONFIRMED:OD-001
}
~~~

Đoạn trên là mã sử dụng bên trong một phương thức hoặc một phép thử.

### 3.1. Đường thực thi qua DirectChannel

Với cấu hình này, đường gọi là:

~~~text
Thread producer
    -> orderInput.send(message)
    -> handler của service activator
    -> OrderService.confirm(...)
    -> confirmations.send(reply)
    -> send(message) trả về
~~~

`DirectChannel` gọi một subscriber trên thread đang gửi. Trong ví dụ, khi `send(...)` trả về bình thường, `confirm(...)` đã hoàn tất và reply đã được đưa vào `confirmations`. Nếu phương thức ném lỗi, lời gọi gửi có thể nhận exception. Xem [DirectChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html).

Điều này cũng cho thấy một hệ quả thực tế: nếu `confirm(...)` gọi dịch vụ ngoài mất hai giây, producer có thể bị giữ trong khoảng thời gian đó. Tham số timeout của thao tác gửi vào channel không tự đặt thời hạn hai giây cho nghiệp vụ đang chạy.

### 3.2. Input channel và output channel có vai trò độc lập

Trong ví dụ, input là `DirectChannel` còn output là `QueueChannel`. Endpoint tiêu thụ `orderInput` nên không cần poller; `confirmations` được đọc trực tiếp bởi mã sử dụng.

Nếu bổ sung một endpoint khác để tự động tiêu thụ `confirmations`, endpoint mới đó cần poller vì đầu vào của chính nó là `QueueChannel`.

Việc service trả về `String` không biến `send(...)` thành phương thức trả kết quả nghiệp vụ. `send(...)` vẫn trả `boolean`; reply đi qua channel. Nếu không cấu hình output channel, service activator có thể dùng header `replyChannel` của request. Một gateway là lựa chọn phù hợp khi mã gọi muốn nhận kết quả qua hợp đồng phương thức. Xem [cơ chế reply của Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html).

## 4. Chuyển input sang QueueChannel: thêm bộ đệm và poller

Giả sử yêu cầu mới là tiếp nhận một đợt đơn hàng rồi xử lý nền. Có thể thay bean `orderInput` trong ví dụ trước bằng:

~~~java
@Bean
public QueueChannel orderInput() {
    return new QueueChannel(100);
}
~~~

Đồng thời thay annotation trên phương thức `confirm(...)` bằng:

~~~java
import org.springframework.integration.annotation.Poller;

@ServiceActivator(
        inputChannel = "orderInput",
        outputChannel = "confirmations",
        poller = @Poller(
                fixedDelay = "100",
                maxMessagesPerPoll = "5",
                receiveTimeout = "0"))
public String confirm(
        OrderCommand command,
        @Header(value = "tenantId", required = false)
        String tenantId) {

    if (command.quantity() <= 0) {
        throw new IllegalArgumentException(
                "quantity phải lớn hơn 0");
    }

    return "CONFIRMED:" + command.orderId();
}
~~~

Đây là các phần thay thế của `OrderInputConfiguration`, không phải các bean và endpoint bổ sung. Mã producer cũng phải lấy bean theo kiểu `QueueChannel` hoặc `MessageChannel` thay vì `DirectChannel`.

### 4.1. Điều gì thay đổi khi gửi message?

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as orderInput: QueueChannel
    participant W as PollingConsumer
    participant S as OrderService
    participant O as confirmations
    P->>Q: send(message)
    Q-->>P: true nếu đã enqueue
    Note over P,Q: Producer có thể tiếp tục công việc
    W->>Q: receive(...)
    Q-->>W: message
    W->>S: confirm(command)
    S-->>W: kết quả
    W->>O: send(reply)
~~~

`QueueChannel` dùng hàng đợi có thể đặt capacity. Với `new QueueChannel(100)`, 100 là số message tối đa đang chờ trong queue, không phải số thread xử lý. Có thể quan sát `getQueueSize()` và `getRemainingCapacity()` để theo dõi lượng việc còn đợi. Xem [QueueChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html).

Trong cấu hình polling thông thường, producer enqueue còn consumer xử lý trên thread của hạ tầng poller. `send(...)` trả `true` không chứng minh đơn hàng đã được xác nhận; cần nhận reply hoặc một sự kiện kết quả riêng.

### 4.2. Hiểu chính xác các tham số poller

| Tham số | Ý nghĩa trong ví dụ |
| --- | --- |
| `fixedDelay = "100"` | Chờ 100 ms sau khi lượt poll trước kết thúc, với cấu hình không giao lượt poll sang executor riêng |
| `maxMessagesPerPoll = "5"` | Giới hạn số message tiêu thụ trong một lượt poll |
| `receiveTimeout = "0"` | Không chờ thêm khi một lần nhận thấy queue rỗng |

`maxMessagesPerPoll` không cấu hình số worker và không đảm bảo thông lượng cố định. `receiveTimeout` giới hạn thời gian chờ message tại đầu vào, không giới hạn thời gian chạy của `confirm(...)`. Xem [Poller API](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Poller.html).

Trong ví dụ, năm message không có nghĩa là năm message chạy đồng thời. Với một consumer và không bổ sung executor, chúng được xử lý lần lượt trong lượt poll.

Ví dụ tính toán: giả sử một message cần 40 ms, queue luôn có sẵn việc, và mỗi lượt xử lý đủ năm message. Một lượt cần khoảng 200 ms, sau đó chờ thêm 100 ms. Thông lượng ước tính là `5 / 0,3 ≈ 16,7 message/giây`, chưa tính chi phí hạ tầng. Đây là phép ước lượng từ giả định của ví dụ, không phải cam kết hiệu năng của framework.

### 4.3. Queue đầy và timeout gửi

Producer nên quyết định rõ cách phản ứng khi hết chỗ:

~~~java
boolean accepted = input.send(request, 200);

if (!accepted) {
    throw new IllegalStateException(
            "Không đưa được yêu cầu vào queue trong thời gian chờ");
}
~~~

Với queue có capacity, thời gian chờ trên cho phép đợi chỗ trống tối đa 200 ms. Gửi không có timeout có thể chờ vô hạn khi queue đầy. Ngoài kết quả `false`, mã gọi vẫn phải xử lý các exception phát sinh trong quá trình gửi. Xem [hành vi QueueChannel](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Đối với một producer HTTP, quyết định đó có thể dẫn tới phản hồi từ chối tạm thời. Đối với một tác vụ nội bộ, nó có thể dẫn tới cơ chế thử lại do ứng dụng thiết kế. Đặt capacity lớn hơn chỉ kéo dài khả năng tích đệm; nó không làm service xử lý nhanh hơn.

### 4.4. Poller nằm ở consumer endpoint

Một `QueueChannel` không tự tạo tác vụ chạy nền. Endpoint tiêu thụ queue cần poller riêng hoặc global default poller.

Global default poller là cấu hình `PollerMetadata` mang tên `PollerMetadata.DEFAULT_POLLER`. Nó được dùng cho các endpoint polling không khai báo poller riêng trong cùng context. Trong ví dụ học tập này, khai báo poller ngay trên service activator giúp nhìn thấy đầy đủ quan hệ giữa queue và consumer. Xem [Global Default Poller](https://docs.spring.io/spring-integration/reference/endpoint.html#global-default-poller).

Không thêm poller vào một service activator có đầu vào `DirectChannel` với mong muốn tự động làm nó bất đồng bộ. Hãy chọn channel và mô hình thực thi đúng với nhu cầu.

## 5. Cùng ý tưởng bằng Java DSL

Java DSL mô tả luồng bằng chuỗi thao tác. Khi đầu vào là một channel có sẵn, `IntegrationFlow.from(...)` xác định điểm vào; `.handle(...)` ở đây tạo bước service activator.

Ví dụ sau là một cấu hình độc lập. Mỗi cách triển khai cần được thử trong context riêng; không đăng ký đồng thời nhiều ví dụ rồi vô tình tạo các consumer ngoài ý muốn.

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
public class DslOrderConfiguration {

    public record OrderCommand(String orderId, int quantity) {
    }

    @Bean
    public QueueChannel dslOrderInput() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel dslConfirmations() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel dslOrderErrors() {
        return new QueueChannel(20);
    }

    @Bean
    public PlainOrderService plainOrderService() {
        return new PlainOrderService();
    }

    @Bean
    public IntegrationFlow queuedOrderFlow(
            PlainOrderService plainOrderService) {

        return IntegrationFlow.from("dslOrderInput")
                .handle(
                        plainOrderService,
                        "confirm",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(
                                                Duration.ofMillis(100))
                                        .maxMessagesPerPoll(5)
                                        .receiveTimeout(0)
                                        .errorChannel("dslOrderErrors")))
                .channel("dslConfirmations")
                .get();
    }

    public static class PlainOrderService {

        public String confirm(OrderCommand command) {
            if (command.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity phải lớn hơn 0");
            }

            return "CONFIRMED:" + command.orderId();
        }
    }
}
~~~

Trong cấu hình này:

- `dslOrderInput` là queue được producer gửi vào.
- Poller gắn trên endpoint của bước `.handle(...)` vì chính endpoint đó tiêu thụ queue.
- `dslConfirmations` nhận kết quả thành công.
- `dslOrderErrors` nhận lỗi do cơ chế xử lý lỗi của poller công bố khi request không chỉ định error channel khác.
- `PlainOrderService.confirm(...)` là phương thức Java thông thường.

`Pollers` cung cấp builder tạo cấu hình poller cho các endpoint trong DSL. Xem [Java DSL Pollers](https://docs.spring.io/spring-integration/reference/dsl/java-pollers.html) và [Pollers API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/Pollers.html).

Nếu chuyển luồng này sang input `DirectChannel`, cần thay bean channel và bỏ cấu hình `endpoint.poller(...)`. Không chỉ đổi tên biến Java: loại bean được tham chiếu mới quyết định mô hình tiêu thụ.

Không giữ `@ServiceActivator(inputChannel = "...")` trên cùng phương thức nếu đã dùng DSL để tạo endpoint thay thế cho nó. Mỗi khai báo endpoint có thể dẫn đến một consumer riêng.

## 6. Chọn input channel theo hành vi mong muốn

| Channel | Cách nhận | Thread xử lý điển hình | Nhu cầu phù hợp |
| --- | --- | --- | --- |
| `DirectChannel` | Subscribe | Thread producer | Một bước xử lý đồng bộ |
| `ExecutorChannel` | Subscribe | Thread executor | Giao công việc sang executor |
| `QueueChannel` | Poll | Thread consumer/poller | Đệm công việc, kiểm soát nhịp lấy |
| `PublishSubscribeChannel` | Subscribe | Thread producer hoặc executor tùy cấu hình | Phát sự kiện đến nhiều subscriber |

### 6.1. ExecutorChannel: chuyển giao qua executor

`ExecutorChannel` dispatch bằng một `Executor`, thường cho phép producer tiếp tục trước khi handler kết thúc. Nó không cần poller. Việc chuyển thread cũng làm transaction gắn với thread producer không tự đi cùng lời gọi handler. Xem [ExecutorChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/ExecutorChannel.html).

Khi chọn loại này, cần định nghĩa kích thước pool, hàng đợi của executor và chính sách từ chối tác vụ. Khi executor quá tải, thao tác gửi vẫn có thể lỗi. Nếu dùng executor đồng bộ hoặc chính sách chạy tác vụ trên caller, không thể giả định handler luôn chạy trên thread khác.

Đây là lựa chọn hợp lý cho tình huống “giao tác vụ cho pool ngay khi nhận”, còn queue cùng poller thể hiện thêm nhu cầu chủ động lấy và điều tiết công việc.

### 6.2. Một consumer được chọn hay nhiều subscriber cùng nhận?

`DirectChannel` và `QueueChannel` có ngữ nghĩa point-to-point. Nếu hai service activator dùng chung đầu vào, không nên kỳ vọng cả hai đều xử lý mỗi message. Với `DirectChannel`, dispatcher chọn handler; cơ chế failover có thể thử handler khác khi một handler lỗi. Vì thế, point-to-point cũng không phải cam kết xử lý nghiệp vụ đúng một lần. Xem [phân phối và failover của channel](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Nếu yêu cầu là thông báo cho nhiều nơi, `PublishSubscribeChannel` gửi đến các subscriber. Loại không cấu hình executor gọi subscriber trên thread gửi; loại có executor giao việc qua executor. Xem [PublishSubscribeChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html).

Ví dụ thiết kế:

~~~text
orderCommands: point-to-point
    -> một consumer xác nhận đơn

orderConfirmedEvents: publish-subscribe
    -> subscriber gửi email
    -> subscriber cập nhật báo cáo
~~~

Broadcast không tự đảm bảo mọi subscriber đều hoàn thành khi một nhánh lỗi. Nếu từng nhánh cần cơ chế lỗi và thử lại độc lập, nên biểu diễn rõ các nhánh cùng channel riêng trong thiết kế.

## 7. Hợp đồng message tại input channel

Input channel quyết định cách chuyển giao; phương thức nghiệp vụ vẫn cần payload và header phù hợp.

Ví dụ phương thức:

~~~java
public String confirm(
        OrderCommand command,
        @Header("tenantId") String tenantId) {
    // Xử lý nghiệp vụ.
    return "CONFIRMED:" + command.orderId();
}
~~~

Ở chữ ký này, `tenantId` là header bắt buộc. Nếu muốn chấp nhận thiếu header như ví dụ cấu hình đầu tiên, dùng `required = false`.

Nếu nguồn ngoài gửi chuỗi JSON, việc đưa chuỗi đó vào `orderInput` không mặc nhiên chứng minh nó sẽ được chuyển thành `OrderCommand` theo đúng hợp đồng nghiệp vụ. Cần cấu hình việc chuyển đổi một cách rõ ràng và kiểm thử bằng dữ liệu đầu vào thực tế. Cơ chế ánh xạ tham số được mô tả tại [ServiceActivator API](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/ServiceActivator.html).

Một flow có thể sắp xếp như sau:

~~~text
JSON từ adapter
    -> transformer tạo OrderCommand
    -> filter kiểm tra điều kiện tiếp nhận
    -> router chọn luồng theo loại đơn
    -> orderInput
    -> service activator gọi nghiệp vụ
~~~

Nếu bước trước là aggregator, phải xác định payload sau gom nhóm là một đơn, danh sách đơn hay đối tượng tổng hợp. Ví dụ, payload `List<OrderCommand>` cần phương thức tương ứng hoặc một bước chuyển đổi trước khi đến handler nhận `OrderCommand`.

Trong luồng nhiều tenant, nên ghi rõ contract: kiểu payload, header tenant, mã yêu cầu để đối chiếu, và mã nghiệp vụ dùng phát hiện xử lý lặp. Điều này giúp producer và service được phát triển độc lập mà vẫn thống nhất đầu vào.

## 8. Ranh giới lỗi và transaction

### 8.1. Gửi đồng bộ qua DirectChannel

Với `DirectChannel` trong ví dụ annotation, lỗi phát sinh khi xử lý có thể truyền ngược về caller của `send(...)`, thường được bọc thành exception thuộc Spring Messaging. Việc chỉ gắn header `errorChannel` không tự chuyển mọi lỗi của lời gọi gửi trực tiếp vào channel đó.

### 8.2. Tiêu thụ queue trên thread poller

Trong flow queue, producer có thể đã rời khỏi lời gọi gửi trước khi lỗi nghiệp vụ xuất hiện. Khi dùng cơ chế lỗi mặc định của hạ tầng polling, lỗi được công bố dưới dạng `ErrorMessage`. Header `errorChannel` trên request được ưu tiên; nếu không có, hệ thống dùng error channel mặc định của error handler.

DSL ở trên đặt mặc định của poller thành `dslOrderErrors`. Ứng dụng cần tiêu thụ channel đó để ghi nhận hoặc xử lý lỗi; kiểm thử có thể đọc trực tiếp bằng `receive(timeout)`. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

### 8.3. Queue không tự tạo độ bền hoặc cơ chế redelivery

`new QueueChannel(100)` lưu message trong bộ nhớ. Nó không tự trở thành một hàng đợi bền vững qua lần khởi động lại ứng dụng. Khi cần lưu bền, phải chọn cơ chế message store hoặc hạ tầng messaging phù hợp. Xem [lưu trữ của queue-based channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Đối với queue trong bộ nhớ ở ví dụ, không nên giả định message đã được lấy ra sẽ tự quay lại queue nếu `confirm(...)` lỗi. Đường lỗi, retry và hành vi giao lại cần được thiết kế riêng. Một lần thử lại cũng có thể lặp side effect đã thực hiện trước khi lỗi xuất hiện; nghiệp vụ nên có khóa chống xử lý lặp, chẳng hạn `orderId`.

Một `DirectChannel` giữ cùng thread nên có thể duy trì transaction của caller khi các tài nguyên và transaction manager được cấu hình phù hợp. Khi chuyển sang executor hoặc poller, không nên giả định transaction gắn với thread caller được truyền sang consumer. Việc cần transaction quanh lượt poll phải được cấu hình tại ranh giới polling. Xem [transaction trên channel](https://docs.spring.io/spring-integration/reference/channel/implementations.html) và [Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html).

## 9. Kiểm thử đường vào của service activator

Các phép thử sau dùng hai cấu hình độc lập đã trình bày. Đây là mã minh họa để đưa vào bộ test của dự án; chúng không yêu cầu gọi adapter HTTP hay broker.

### 9.1. DirectChannel: kết quả xuất hiện trong cùng lời gọi gửi

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class DirectOrderInputTest {

    @Test
    void shouldInvokeServiceAndProduceReply() {
        try (var context =
                new AnnotationConfigApplicationContext(
                        OrderInputConfiguration.class)) {

            var input =
                    context.getBean("orderInput", DirectChannel.class);
            var output =
                    context.getBean("confirmations", QueueChannel.class);

            var request = MessageBuilder
                    .withPayload(
                            new OrderInputConfiguration.OrderCommand(
                                    "OD-001", 2))
                    .setHeader("tenantId", "tenant-a")
                    .build();

            assertTrue(input.send(request));

            var reply = output.receive(0);
            assertNotNull(reply);
            assertEquals("CONFIRMED:OD-001", reply.getPayload());
        }
    }

    @Test
    void shouldPropagateFailureToSender() {
        try (var context =
                new AnnotationConfigApplicationContext(
                        OrderInputConfiguration.class)) {

            var input =
                    context.getBean("orderInput", DirectChannel.class);
            var output =
                    context.getBean("confirmations", QueueChannel.class);

            var request = MessageBuilder
                    .withPayload(
                            new OrderInputConfiguration.OrderCommand(
                                    "OD-INVALID", 0))
                    .build();

            assertThrows(
                    MessagingException.class,
                    () -> input.send(request));

            assertNull(output.receive(0));
        }
    }
}
~~~

`receive(0)` phù hợp ở đây vì đường xử lý đến output chưa chuyển thread. Phép thử thứ hai kiểm tra cả việc caller nhận lỗi và việc không sinh reply thành công.

### 9.2. QueueChannel: chờ kết quả và kiểm tra ErrorMessage

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class QueuedOrderInputTest {

    @Test
    void shouldProcessQueuedCommand() {
        try (var context =
                new AnnotationConfigApplicationContext(
                        DslOrderConfiguration.class)) {

            var input =
                    context.getBean("dslOrderInput", QueueChannel.class);
            var output =
                    context.getBean("dslConfirmations", QueueChannel.class);

            var request = MessageBuilder
                    .withPayload(
                            new DslOrderConfiguration.OrderCommand(
                                    "OD-002", 3))
                    .build();

            assertTrue(input.send(request, 200));

            var reply = output.receive(3000);
            assertNotNull(reply);
            assertEquals("CONFIRMED:OD-002", reply.getPayload());
        }
    }

    @Test
    void shouldPublishFailureFromPoller() {
        try (var context =
                new AnnotationConfigApplicationContext(
                        DslOrderConfiguration.class)) {

            var input =
                    context.getBean("dslOrderInput", QueueChannel.class);
            var output =
                    context.getBean("dslConfirmations", QueueChannel.class);
            var errors =
                    context.getBean("dslOrderErrors", QueueChannel.class);

            var request = MessageBuilder
                    .withPayload(
                            new DslOrderConfiguration.OrderCommand(
                                    "OD-INVALID", 0))
                    .build();

            assertTrue(input.send(request, 200));

            var error = assertInstanceOf(
                    ErrorMessage.class,
                    errors.receive(3000));

            var failure = assertInstanceOf(
                    MessagingException.class,
                    error.getPayload());

            assertNotNull(failure.getFailedMessage());
            assertEquals(
                    request.getPayload(),
                    failure.getFailedMessage().getPayload());

            assertNull(output.receive(0));
        }
    }
}
~~~

Thời hạn 3000 ms là giới hạn chờ của phép thử, không phải cam kết thời gian xử lý của ứng dụng. Trong môi trường tải cao, cần chọn thời hạn phù hợp. Việc chờ message trên channel giúp phép thử tiến tiếp ngay khi kết quả đến, thay vì luôn ngủ hết một khoảng cố định.

Để kiểm tra thêm đặc tính bộ đệm, có thể dùng một `QueueChannel(1)` không có consumer: lần gửi đầu với timeout 0 thành công, lần gửi thứ hai với timeout 0 thất bại. Đó là kiểm tra hành vi tiếp nhận; kết quả nghiệp vụ vẫn phải được kiểm tra qua endpoint thực.

## 10. Chẩn đoán lỗi cấu hình input channel

| Hiện tượng | Điều cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Gửi vào `DirectChannel` báo không có subscriber | Endpoint đã được tạo và khởi động chưa; producer có dùng đúng channel instance không | Kiểm tra bean service, hạ tầng Integration, tên channel và vòng đời endpoint |
| Queue có message nhưng service không chạy | Poller có tồn tại, đang chạy và có lịch hợp lệ không | Khai báo poller riêng hoặc default poller; kiểm tra lỗi khi khởi tạo |
| Producer chờ lâu | Direct handler chậm, queue đầy hoặc executor quá tải | Đo thời gian xử lý và lượng việc chờ; kiểm tra capacity cùng timeout |
| Hai handler không cùng nhận mọi message | Channel có ngữ nghĩa point-to-point | Dùng publish-subscribe hoặc tách nhánh khi cần phát sự kiện |
| `send()` thành công nhưng nghiệp vụ lỗi | Input dùng queue hoặc executor | Quan sát reply/error channel cùng mã yêu cầu |
| Đổi sang queue rồi lỗi không về caller | Consumer đã chạy sau ranh giới chuyển giao | Tiêu thụ `ErrorMessage` và thiết kế phản hồi thất bại |
| Handler không khớp tham số | Payload hoặc header không đúng hợp đồng | Kiểm tra transformer, kiểu payload thực tế và header bắt buộc |
| Service trả kết quả nhưng luồng lỗi ở bước reply | Thiếu đích nhận reply hoặc output bị đầy | Kiểm tra output channel, `replyChannel` và consumer phía sau |

Với `@ServiceActivator`, tên input channel chưa tồn tại có thể được framework đăng ký thành một `DirectChannel`. Do đó, lỗi gõ tên không nhất thiết biểu hiện bằng lỗi “không tìm thấy bean”; endpoint có thể đang nghe ở một channel khác với producer. Khai báo channel tường minh và kiểm thử đường gửi thực tế giúp phát hiện trường hợp này. Xem [ServiceActivator.inputChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/ServiceActivator.html#inputChannel()).

## 11. Áp dụng vào một luồng xử lý đơn hàng

Giả sử hệ thống nhận đơn hàng theo đợt và cần xác nhận từng đơn:

1. Adapter chuyển dữ liệu ngoài vào hệ thống dưới dạng `Message`.
2. Transformer tạo payload `OrderCommand` có hợp đồng rõ ràng.
3. Filter loại yêu cầu không được tiếp nhận; router chọn nhóm xử lý khi cần.
4. `orderInput` là queue có capacity phù hợp với mức tích đệm cho phép.
5. Service activator lấy message qua poller và gọi service xác nhận.
6. Kết quả thành công đi tới channel kết quả; lỗi đi tới nhánh xử lý lỗi.
7. Nếu cần gom nhiều kết quả theo lô, aggregator được đặt ở bước sau với chiến lược correlation và release riêng.

Khi chọn đầu vào cho bước 5, hãy ghi lại ba quyết định cụ thể: producer có cần chờ xử lý hoàn tất không, lượng công việc được phép chờ là bao nhiêu, và hệ thống xác nhận thất bại bằng cách nào. Những quyết định đó giúp chọn đúng channel, cấu hình endpoint và viết phép thử sát với yêu cầu nghiệp vụ.
