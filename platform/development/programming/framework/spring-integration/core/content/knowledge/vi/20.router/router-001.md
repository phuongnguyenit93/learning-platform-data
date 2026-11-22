# Message router là gì

Message router là thành phần **chọn đường đi tiếp theo cho thông điệp**. Nó nhận một `Message<?>` từ channel đầu vào, áp dụng quy tắc định tuyến rồi chuyển thông điệp đến một hoặc nhiều channel đích. Quy tắc có thể dựa trên payload, header hoặc loại dữ liệu của payload. Đây là một mẫu tích hợp doanh nghiệp, giúp tách quyết định “đi đâu tiếp” khỏi nơi phát sinh thông điệp. [Spring Integration: Router Overview](https://docs.spring.io/spring-integration/reference/router/overview.html)

Trong module **SPRING_INTEGRATION_CORE**, router nối kiến thức về `Message`, `MessageChannel` và endpoint thành một luồng có nhánh. Bài học tập trung vào ý nghĩa của router, cách biểu diễn bằng Java DSL, chính sách khi không chọn được đích và cách kiểm tra thông điệp đã đi đúng nhánh.

Sau bài học, bạn có thể:

- Nhận ra tình huống cần router và phân biệt router với các thành phần lân cận.
- Giải thích quan hệ giữa dữ liệu đầu vào, khóa định tuyến và channel đích.
- Xây dựng luồng định tuyến đơn hàng có hai nhánh nghiệp vụ và một nhánh dự phòng.
- Kiểm tra nhánh được chọn, payload và header mà không cần kết nối hệ thống bên ngoài.

## 1. Bài toán: đơn hàng cần được chuyển đến đúng luồng xử lý

Giả sử hệ thống tiếp nhận đơn hàng từ nhiều nguồn. Đơn giao nhanh và đơn giao tiêu chuẩn cần đi qua hai quy trình khác nhau; những phương thức chưa được hỗ trợ cần được kiểm tra thủ công.

| Dữ liệu nghiệp vụ | Khóa sau khi chuẩn hóa | Channel đích | Ý nghĩa |
| --- | --- | --- | --- |
| `deliveryType = "EXPRESS"` | `EXPRESS` | `expressOrders` | Luồng giao nhanh |
| `deliveryType = "STANDARD"` | `STANDARD` | `standardOrders` | Luồng giao tiêu chuẩn |
| `deliveryType = "DRONE"` | `DRONE` | `manualReview` | Chưa có mapping, cần xem xét |
| `deliveryType = null` | `UNKNOWN` | `manualReview` | Thiếu thông tin định tuyến |

Luồng mong muốn:

~~~mermaid
flowchart LR
    P["Nơi tiếp nhận đơn hàng"] --> I["ordersInput"]
    I --> R{"Router: deliveryType"}
    R -->|"EXPRESS"| E["expressOrders"]
    R -->|"STANDARD"| S["standardOrders"]
    R -->|"Không có mapping"| M["manualReview"]
    E --> EF["Quy trình giao nhanh"]
    S --> SF["Quy trình giao tiêu chuẩn"]
    M --> MF["Kiểm tra thủ công"]
~~~

Nơi tiếp nhận chỉ gửi thông điệp vào `ordersInput`. Nó không phải gọi trực tiếp từng dịch vụ giao hàng. Khi bổ sung một phương thức giao mới, điểm thay đổi chủ yếu là quy tắc định tuyến và nhánh xử lý tương ứng.

Một phép `if/else` vẫn có thể biểu diễn quy tắc này. Giá trị của router là đưa phép chọn nhánh vào kiến trúc thông điệp: mỗi nhánh kết nối qua channel và có thể tiếp tục bằng transformer, filter, service activator hoặc luồng tích hợp khác.

Router ở đây hoạt động bên trong luồng Spring Integration. Nó không phải router mạng và cũng không phải cơ chế ánh xạ URL của Spring MVC.

## 2. Mô hình hoạt động: đọc thông điệp, chọn đích, chuyển tiếp

### 2.1. Router nằm ở đâu trong một endpoint?

Có thể hình dung cấu trúc như sau:

~~~text
MessageChannel đầu vào
        |
        v
Endpoint tiếp nhận thông điệp
        |
        v
Router handler
        |
        +--> MessageChannel đích A
        |
        +--> MessageChannel đích B
~~~

Về cấu hình, ta thường gọi cả vị trí xử lý này là “router endpoint”. Chính router handler quyết định đích; cơ chế endpoint kết nối handler với channel đầu vào. Với `DirectChannel`, handler được gọi khi có thông điệp được gửi đến. Nếu dùng channel đầu vào dạng polling, endpoint cần cơ chế poller để lấy thông điệp ra. [Spring Integration: Common Router Parameters](https://docs.spring.io/spring-integration/reference/router/common-parameters.html)

Nhờ vậy, bạn cần xác định riêng hai việc: **thông điệp được tiếp nhận như thế nào** và **nó được chuyển đến đâu**.

### 2.2. Phân biệt ba khái niệm dễ nhầm

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Dữ liệu dùng để quyết định | `order.deliveryType()` | Thông tin đọc từ thông điệp |
| Khóa định tuyến, hay routing key | `"EXPRESS"` | Kết quả của hàm chọn nhánh |
| Channel đích | Bean `expressOrders` | Nơi nhận thông điệp được chuyển tiếp |

Trong ví dụ này:

~~~text
payload.deliveryType() = " express "
             |
             v
chuẩn hóa khóa thành "EXPRESS"
             |
             v
mapping "EXPRESS" -> "expressOrders"
             |
             v
gửi Message<Order> đến channel expressOrders
~~~

`EXPRESS` là một khái niệm nghiệp vụ; `expressOrders` là tên channel trong cấu hình. Tách hai giá trị giúp quy tắc nghiệp vụ ít phụ thuộc tên bean.

Hàm định tuyến trả về `"EXPRESS"` không có nghĩa payload bị thay bằng chuỗi đó. Chuỗi được sử dụng để chọn đích, còn dữ liệu được chuyển tiếp vẫn là thông điệp đơn hàng. Java DSL hỗ trợ các cặp `channelMapping(key, channelName)` để biểu diễn mối liên hệ này. [Spring Integration: Message Routers trong Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-routers.html)

### 2.3. Router chuyển tiếp dữ liệu, không mặc nhiên biến đổi dữ liệu

Ở mức khái niệm:

~~~text
quyết định định tuyến: Message -> tập channel đích
chuyển tiếp:          Message -> gửi đến các đích đã chọn
~~~

Trong luồng minh họa, router không sửa payload hay header `traceId`. Việc chuẩn hóa chỉ tạo khóa tạm để tra mapping; nó không sửa trường `deliveryType` của đơn hàng.

Không nên suy rộng thành “mọi router luôn giữ nguyên mọi header trong mọi cấu hình”. Chẳng hạn, một cấu hình phục vụ việc ghép kết quả nhiều nhánh có thể yêu cầu thêm thông tin sequence. Nếu cần biến đổi nội dung nghiệp vụ, hãy biểu diễn bằng transformer riêng để mục đích của từng bước rõ ràng.

## 3. Router khác gì với những thành phần quen thuộc?

| Thành phần | Câu hỏi chính | Ví dụ với đơn hàng |
| --- | --- | --- |
| `MessageChannel` | Thông điệp đi qua đường truyền nào? | `ordersInput` nhận thông điệp từ bên gửi |
| Router | Thông điệp cần đi đến nhánh nào? | Giao nhanh hay giao tiêu chuẩn |
| Transformer | Dữ liệu cần đổi sang hình dạng nào? | Chuyển JSON thành `Order` |
| Filter | Thông điệp có được đi tiếp qua bước này không? | Loại đơn không đáp ứng điều kiện |
| Splitter | Một thông điệp cần tách thành những phần nào? | Tách đơn hàng thành từng dòng hàng |
| Aggregator | Những thông điệp nào cần được ghép lại? | Ghép kết quả xử lý các dòng hàng |
| Gateway | Mã gọi giao tiếp với luồng thông điệp qua giao diện nào? | Gọi `submitOrder(...)` trên giao diện Java |

Nếu cần chấp nhận hoặc loại thông điệp theo một điều kiện, filter thường diễn đạt trực tiếp hơn. Nếu cần phân luồng nhiều loại thông điệp đến các đích riêng, router phù hợp hơn.

Cũng cần phân biệt **chọn channel** với **phát cho các subscriber của channel**. `PublishSubscribeChannel` phân phối thông điệp cho các subscriber của nó. Router có thể chọn channel đó làm đích; hai cơ chế có thể xuất hiện cùng nhau. `DirectChannel` có nhiều subscriber lại không mang ý nghĩa phát bản sao đến tất cả subscriber. [Spring Integration: Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Một router cũng có thể chọn nhiều channel cho cùng thông điệp. Ví dụ, một sự kiện đơn hàng đồng thời cần đi đến nhánh cập nhật báo cáo và nhánh gửi thông báo. Vì vậy, “router luôn chỉ chọn đúng một nhánh” là cách hiểu quá hẹp. Riêng ví dụ trong bài được thiết kế để mỗi đơn hàng chỉ đến một trong ba channel.

## 4. Nên dựa vào thông tin nào để định tuyến?

Quy tắc nên phản ánh dữ liệu đã có và mục đích của luồng.

| Nguồn quyết định | Ví dụ | Điều cần thống nhất |
| --- | --- | --- |
| Trường trong payload | `Order.deliveryType` | Hợp đồng dữ liệu nghiệp vụ |
| Header | `tenantId`, `region`, `documentType` | Bước nào tạo header, giá trị có đáng tin cậy không |
| Kiểu payload | `OrderCreated` hoặc `OrderCancelled` | Mô hình sự kiện và cách deserialize |
| Kết quả phân loại trước đó | `riskLevel = HIGH` | Bước phân loại phải chạy trước router |

Spring Integration có các router chuyên biệt như `HeaderValueRouter`, `PayloadTypeRouter` và `RecipientListRouter`; cũng có thể dùng hàm Java hoặc biểu thức để quyết định đích. [Spring Integration: Router Overview](https://docs.spring.io/spring-integration/reference/router/overview.html)

Với bài toán đơn hàng, chọn trường `deliveryType` vì nó thể hiện trực tiếp loại quy trình cần thực hiện. Hàm chọn khóa chỉ chuẩn hóa chuỗi và đọc dữ liệu, nên có thể kiểm tra độc lập.

Một quy tắc định tuyến dễ bảo trì thường có các đặc điểm sau:

- Cùng một dữ liệu đầu vào cho cùng một quyết định, trừ khi nghiệp vụ chủ động phụ thuộc trạng thái bên ngoài.
- Không đồng thời trừ tiền, cập nhật đơn hàng hoặc gọi dịch vụ giao hàng ngay trong hàm chọn khóa.
- Có chính sách rõ ràng cho giá trị chưa biết, dữ liệu thiếu và lỗi cấu hình.
- Nếu cần tra cứu thông tin từ hệ thống khác, bước tra cứu được biểu diễn rõ trong luồng trước khi chọn nhánh.

Thiếu dữ liệu và dữ liệu không hợp lệ không nhất thiết có cùng chính sách. Bài này đưa `deliveryType = null` vào kiểm tra thủ công để dễ quan sát. Một hệ thống yêu cầu trường này bắt buộc có thể dùng bước kiểm tra dữ liệu ở trước router để từ chối sớm.

## 5. Ví dụ Java DSL: định tuyến đơn hàng

### 5.1. Điều kiện để dùng ví dụ

Ví dụ dùng Java 17 trở lên và cách khai báo `IntegrationFlow.from(...)` của Spring Integration 6.x. Dự án cần dependency `org.springframework.integration:spring-integration-core` cùng các dependency Spring tương thích. Nếu dùng Spring Boot, để cơ chế quản lý dependency của Boot chọn bộ phiên bản phù hợp.

Hai lớp dưới đây đặt trong cùng package `example.router`. Không cần HTTP server, Kafka hoặc RabbitMQ để quan sát hành vi.

Các channel đầu ra dùng `QueueChannel` nhằm giữ thông điệp cho chương trình đọc và kiểm tra. Trong ứng dụng thực tế, phía sau mỗi channel sẽ có consumer hoặc một flow xử lý tiếp. `QueueChannel` trong ví dụ là hàng đợi trong bộ nhớ, không phải cam kết lưu bền thông điệp.

### 5.2. Khai báo dữ liệu, channel và router

Lớp `OrderRoutingConfig.java`:

~~~java
package example.router;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderRoutingConfig {

    public record Order(String orderId, String deliveryType) {
    }

    @Bean
    public DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel expressOrders() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel standardOrders() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel manualReview() {
        return new QueueChannel(10);
    }

    static String routingKey(Order order) {
        String deliveryType = order.deliveryType();
        return deliveryType == null
                ? "UNKNOWN"
                : deliveryType.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public IntegrationFlow orderRoutingFlow() {
        return IntegrationFlow.from(ordersInput())
                .route(Order.class, OrderRoutingConfig::routingKey,
                        router -> router
                                .channelMapping("EXPRESS", "expressOrders")
                                .channelMapping("STANDARD", "standardOrders")
                                .defaultOutputChannel("manualReview")
                                .channelKeyFallback(false)
                                .resolutionRequired(true)
                                .sendTimeout(1_000))
                .get();
    }
}
~~~

Đọc cấu hình theo từng bước:

1. `ordersInput` là cửa vào của luồng.
2. `Order.class` xác định kiểu payload mà hàm định tuyến xử lý.
3. `routingKey` tạo khóa nghiệp vụ, chẳng hạn `EXPRESS`.
4. `channelMapping` nối khóa đó với tên bean channel.
5. `manualReview` nhận thông điệp khi không có đích từ mapping.
6. Các tùy chọn còn lại quy định cách phân giải tên channel và gửi thông điệp.

`Locale.ROOT` giúp việc chuyển chữ hoa không phụ thuộc locale mặc định của máy. Với đầu vào `" express "`, router chọn `expressOrders`, nhưng payload vẫn chứa giá trị gốc `" express "`.

Ba queue có sức chứa 10 để ví dụ có giới hạn rõ ràng. `sendTimeout(1_000)` đặt thời gian chờ gửi vào channel đích là 1.000 ms khi việc gửi cần chờ, chẳng hạn queue đã đầy. Nó không giới hạn thời gian thực thi toàn bộ nghiệp vụ phía sau router.

Các API `channelMapping`, `channelKeyFallback`, `resolutionRequired` và `sendTimeout` thuộc cấu hình router trong Java DSL. [Spring Integration: RouterSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/RouterSpec.html)

### 5.3. Gửi thông điệp và đọc từng nhánh

Lớp `RouterDemo.java`:

~~~java
package example.router;

import java.util.List;

import example.router.OrderRoutingConfig.Order;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class RouterDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(OrderRoutingConfig.class)) {

            MessageChannel input =
                    context.getBean("ordersInput", MessageChannel.class);

            List<Order> orders = List.of(
                    new Order("ORD-1", "EXPRESS"),
                    new Order("ORD-2", "STANDARD"),
                    new Order("ORD-3", "DRONE"));

            for (Order order : orders) {
                Message<Order> message = MessageBuilder.withPayload(order)
                        .setHeader("traceId", "trace-" + order.orderId())
                        .build();

                if (!input.send(message)) {
                    throw new IllegalStateException("Không gửi được đơn hàng");
                }
            }

            for (String channelName :
                    List.of("expressOrders", "standardOrders", "manualReview")) {
                QueueChannel channel =
                        context.getBean(channelName, QueueChannel.class);
                Message<?> received = channel.receive(0);
                System.out.println(channelName + " -> "
                        + (received == null ? "EMPTY" : received.getPayload()));
            }
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
expressOrders -> Order[orderId=ORD-1, deliveryType=EXPRESS]
standardOrders -> Order[orderId=ORD-2, deliveryType=STANDARD]
manualReview -> Order[orderId=ORD-3, deliveryType=DRONE]
~~~

Ở đây, `receive(0)` đọc ngay và trả `null` nếu queue rỗng. Chương trình không cần poller cho ba queue đầu ra vì chính mã demo gọi `receive`. Nếu muốn khai báo một endpoint tự lấy dữ liệu từ queue để xử lý liên tục, bạn cần cấu hình polling phù hợp. Hành vi gửi và nhận của `QueueChannel` được mô tả trong [tài liệu channel của Spring Integration](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Khi `send` trả thành công, thông điệp trong ví dụ đã được đặt vào queue đích. Điều đó chưa có nghĩa quy trình giao hàng đã hoàn thành.

## 6. Không có nhánh phù hợp và lỗi định tuyến là hai tình huống riêng

### 6.1. Khóa chưa được hỗ trợ

`DRONE` không xuất hiện trong bảng mapping. Cấu hình có `channelKeyFallback(false)`, nên router không thử dùng chuỗi `DRONE` như tên channel. Vì không có đích từ mapping, nó dùng `manualReview`.

Khi channel-key fallback được bật, một khóa không có mapping có thể được dùng làm tên channel để tiếp tục phân giải. Tắt cơ chế này giúp tập đích của ví dụ bám theo mapping được khai báo. Từ Spring Integration 6.0, việc đặt default output channel cũng làm channel-key fallback chuyển sang `false`; ví dụ vẫn ghi tùy chọn rõ ràng để người đọc thấy chủ ý. [Spring Integration: AbstractMappingMessageRouter API](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/AbstractMappingMessageRouter.html)

### 6.2. Mapping tồn tại nhưng tên channel bị sai

Giả sử vô tình sửa:

~~~java
.channelMapping("EXPRESS", "expressOrderTypo")
~~~

Nếu không có channel tên `expressOrderTypo`, đó là lỗi cấu hình. Với `resolutionRequired(true)`, router yêu cầu phân giải thành công tên channel và sẽ phát sinh lỗi khi không làm được. Không nên coi `manualReview` là cơ chế che mọi lỗi định tuyến. [Spring Integration: Common Router Parameters](https://docs.spring.io/spring-integration/reference/router/common-parameters.html)

Có thể dự đoán hành vi của cấu hình trong bài như sau:

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Khóa `EXPRESS`, mapping và channel hợp lệ | Gửi vào `expressOrders` |
| Khóa `DRONE`, không có mapping | Gửi vào `manualReview` |
| `deliveryType = null` | Tạo khóa `UNKNOWN`, gửi vào `manualReview` |
| Khóa `EXPRESS`, mapping trỏ đến tên channel không tồn tại | Phát sinh lỗi phân giải |
| Channel đích tồn tại nhưng không nhận được thông điệp | Xử lý như lỗi gửi, không tự đổi sang nhánh mặc định |
| Hàm định tuyến ném exception | Xử lý như lỗi thực thi hàm, không tự đổi sang nhánh mặc định |
| Payload có kiểu không phù hợp với hàm nhận `Order` | Lỗi xử lý đầu vào, không phải trường hợp khóa chưa được hỗ trợ |

Nếu bỏ default output channel, bạn phải chủ động xác định kết quả khi không có đích. Mặc định router không âm thầm bỏ thông điệp chỉ vì không tìm được nhánh. Việc chọn bỏ thông điệp cần được thiết kế rõ; với luồng đơn hàng của bài này, giữ lại ở `manualReview` giúp phát hiện các loại giao hàng chưa hỗ trợ. [Spring Integration: Router Overview](https://docs.spring.io/spring-integration/reference/router/overview.html)

## 7. Nhận diện cùng ý tưởng qua annotation `@Router`

Java DSL là cách biểu diễn chính trong bài. Khi đọc mã nguồn khác, bạn cũng có thể gặp một phương thức được gắn `@Router`.

Một phương thức router có thể trả về tên channel, đối tượng `MessageChannel` hoặc một collection các giá trị tương ứng để chọn nhiều đích. Phương thức cũng có thể nhận payload hoặc dữ liệu header. [Spring Integration: Configuring a Router with Annotations](https://docs.spring.io/spring-integration/reference/router/annotation.html)

Ví dụ phương án thay thế:

~~~java
package example.router;

import example.router.OrderRoutingConfig.Order;
import org.springframework.integration.annotation.Router;

public class OrderRouter {

    @Router(inputChannel = "ordersInput")
    public String selectChannel(Order order) {
        return switch (OrderRoutingConfig.routingKey(order)) {
            case "EXPRESS" -> "expressOrders";
            case "STANDARD" -> "standardOrders";
            default -> "manualReview";
        };
    }
}
~~~

Để dùng phương án này với các channel đã khai báo, bỏ bean flow `orderRoutingFlow` và đăng ký router như một bean trong lớp cấu hình đang có `@EnableIntegration`:

~~~java
@Bean
public OrderRouter orderRouter() {
    return new OrderRouter();
}
~~~

Trong phương án annotation này, phương thức trả về **tên channel trực tiếp**. Trong phương án DSL trước đó, phương thức `routingKey` trả về **khóa nghiệp vụ**, sau đó mapping mới chọn tên channel.

Chỉ giữ một phương án trên `ordersInput` cho bài thực hành. Nếu đăng ký đồng thời cả hai, bạn tạo hai endpoint cùng subscribe vào một `DirectChannel`; đó là một cấu trúc luồng khác với router duy nhất đang muốn quan sát.

## 8. Router không tự quyết định luồng đồng bộ hay bất đồng bộ

Đường đi và cách thực thi là hai quyết định khác nhau.

Trong ví dụ, `ordersInput` là `DirectChannel`, nên quyết định định tuyến chạy trong luồng gọi `input.send(...)`. Router sau đó đặt thông điệp vào một `QueueChannel`; việc xử lý nghiệp vụ tiếp theo chỉ diễn ra khi có consumer lấy thông điệp.

Với đường xử lý đồng bộ qua `DirectChannel`, exception có thể truyền trở lại người gửi. Với xử lý bất đồng bộ qua executor hoặc endpoint polling, lỗi không thể quay về call stack đã kết thúc; cơ chế xử lý lỗi của thành phần tương ứng thường chuyển lỗi thành `ErrorMessage` để đưa vào error channel. Không nên giả định mọi lỗi đều tự động xuất hiện ở global `errorChannel`, đặc biệt khi gọi trực tiếp `MessageChannel.send`. [Spring Integration: Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)

Khi thiết kế nhánh lỗi, hãy xác định rõ:

- Thành phần nào phát sinh lỗi và nó chạy trên thread nào.
- Ai chịu trách nhiệm bắt lỗi hoặc công bố `ErrorMessage`.
- Cần retry, giữ thông điệp để xử lý lại hay chuyển sang quy trình nghiệp vụ khác.

Ví dụ `manualReview` biểu diễn một quyết định nghiệp vụ về loại giao hàng chưa được hỗ trợ. Nó không thay thế cho cơ chế xử lý exception.

Nếu một router gửi đến nhiều đích, cũng không nên mặc định coi các lần gửi là một giao dịch “tất cả cùng thành công”. Một nhánh có thể đã nhận thông điệp trước khi nhánh khác lỗi. Nếu nghiệp vụ cần bảo đảm chặt hơn, phải thiết kế thêm transaction, lưu bền hoặc cơ chế xử lý lặp phù hợp với các tài nguyên thực tế.

## 9. Kiểm tra hành vi định tuyến

Một phép kiểm tra có ích cần xác nhận cả **đúng đích nhận** lẫn **các đích không được nhận**. Chỉ nhìn log của một handler có thể bỏ sót việc thông điệp bị gửi thêm sang nhánh khác.

Với cấu hình Java DSL, các trường hợp cần quan sát gồm:

| Đầu vào | Đích nhận duy nhất | Điều cần xác nhận thêm |
| --- | --- | --- |
| `EXPRESS` | `expressOrders` | Hai queue còn lại rỗng |
| `STANDARD` | `standardOrders` | Hai queue còn lại rỗng |
| `" express "` | `expressOrders` | Payload giữ giá trị gốc |
| `DRONE` | `manualReview` | Không rơi vào hai nhánh giao hàng |
| `null` | `manualReview` | Thiếu dữ liệu không gây lỗi trong chính sách của ví dụ |

Đoạn JUnit Jupiter dưới đây đặt cùng package và dùng lại `OrderRoutingConfig` ban đầu. Dự án cần dependency test `org.junit.jupiter:junit-jupiter` và cấu hình chạy JUnit phù hợp.

~~~java
package example.router;

import java.util.List;

import example.router.OrderRoutingConfig.Order;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderRoutingTest {

    @Test
    void routesEachOrderToExactlyOneDestination() {
        try (var context =
                     new AnnotationConfigApplicationContext(OrderRoutingConfig.class)) {
            assertRouted(context, new Order("ORD-1", "EXPRESS"), "expressOrders");
            assertRouted(context, new Order("ORD-2", "STANDARD"), "standardOrders");
            assertRouted(context, new Order("ORD-3", " express "), "expressOrders");
            assertRouted(context, new Order("ORD-4", "DRONE"), "manualReview");
            assertRouted(context, new Order("ORD-5", null), "manualReview");
        }
    }

    private static void assertRouted(
            AnnotationConfigApplicationContext context,
            Order order,
            String expectedChannel) {

        String traceId = "trace-" + order.orderId();
        Message<Order> sent = MessageBuilder.withPayload(order)
                .setHeader("traceId", traceId)
                .build();

        MessageChannel input =
                context.getBean("ordersInput", MessageChannel.class);
        assertTrue(input.send(sent));

        for (String channelName :
                List.of("expressOrders", "standardOrders", "manualReview")) {
            Message<?> received = context.getBean(channelName, QueueChannel.class)
                    .receive(0);

            if (channelName.equals(expectedChannel)) {
                assertNotNull(received, "Thiếu thông điệp ở " + channelName);
                assertEquals(order, received.getPayload());
                assertEquals(traceId, received.getHeaders().get("traceId"));
                assertNull(context.getBean(channelName, QueueChannel.class).receive(0),
                        "Có thông điệp thừa ở " + channelName);
            } else {
                assertNull(received, "Thông điệp đi nhầm sang " + channelName);
            }
        }
    }
}
~~~

Phép kiểm tra này quan sát luồng thật qua Spring context: chọn đúng đích, không gửi thêm thông điệp, giữ dữ liệu đơn hàng và header theo dõi. Nó không kiểm tra dịch vụ giao hàng hay hệ thống ngoài.

Không cần `Thread.sleep` ở đây vì quá trình định tuyến đến queue diễn ra trước khi `send` trả về. Nếu đổi sang một đoạn xử lý bằng executor, cách chờ kết quả cần thay đổi, chẳng hạn nhận với timeout có giới hạn.

Ngoài đường đi thông thường, nên kiểm tra lỗi cấu hình và exception khi bạn bổ sung các cơ chế xử lý lỗi tương ứng. Đặc biệt, một phép kiểm tra “giá trị chưa được hỗ trợ đi vào manual review” không thay thế cho phép kiểm tra “tên channel trong mapping bị sai”.

## 10. Những lỗi thiết kế thường gặp

### 10.1. Trả về khóa nghiệp vụ nhưng quên khai báo mapping

Một hàm trả về `"EXPRESS"` chưa đủ để nói đến channel `expressOrders`. Nếu không có mapping, hành vi còn phụ thuộc cách phân giải channel được cấu hình.

Hãy kiểm tra đủ chuỗi: dữ liệu đầu vào → khóa → mapping → bean channel.

### 10.2. Đưa mọi xử lý nghiệp vụ vào hàm chọn đích

Nếu hàm định tuyến vừa gọi API đánh giá rủi ro vừa ghi cơ sở dữ liệu vừa gửi email, việc thay đổi hoặc thử lại quyết định định tuyến có thể gây thêm tác dụng phụ.

Đặt bước thu thập dữ liệu và bước xử lý nghiệp vụ tại các endpoint riêng. Router sử dụng kết quả đã có để chọn đường đi.

### 10.3. Dùng default output như nơi nuốt mọi exception

Nhánh mặc định xử lý tình huống không có đích theo chính sách định tuyến. Nó không tự động bắt exception từ hàm chọn khóa, lỗi gửi hoặc lỗi của handler phía sau.

Giữ riêng chính sách cho “chưa biết chọn nhánh nào” và chính sách cho “xử lý thất bại”.

### 10.4. Cho nhiều nhánh cùng sửa một payload mutable

Gửi thông điệp đến nhiều đích không đồng nghĩa tạo một bản sao sâu độc lập của payload cho từng nhánh. Nếu các nhánh cùng sửa một đối tượng chia sẻ, kết quả dễ phụ thuộc thứ tự hoặc thời điểm xử lý.

Ưu tiên dữ liệu bất biến; nếu mỗi nhánh cần một biểu diễn riêng, tạo dữ liệu tương ứng bằng bước biến đổi rõ ràng. Record trong ví dụ chỉ chứa các trường `String`, phù hợp với mục đích minh họa dữ liệu không bị sửa giữa các nhánh.

### 10.5. Mong gateway trả lời dù nhánh chỉ lưu vào queue

Nếu caller gọi qua gateway theo kiểu request-reply, cần thiết kế đường tạo và chuyển trả kết quả. Việc router đưa thông điệp vào `manualReview` không tự tạo ra một phản hồi nghiệp vụ cho caller.

Phải thống nhất giao diện gọi là gửi một chiều hay chờ kết quả, rồi thiết kế các nhánh tương ứng. Router chỉ là một bước trong hợp đồng đó.

## 11. Thực hành mở rộng

Dùng cấu hình DSL làm điểm bắt đầu và thực hiện tuần tự:

1. Gửi đơn có `deliveryType = " standard "`; xác nhận nó đến `standardOrders` và payload vẫn giữ giá trị gốc.
2. Thêm channel `pickupOrders` và mapping cho khóa `PICKUP`; xác nhận thay đổi này không làm các loại đơn cũ chuyển nhánh.
3. Gửi `"expressOrders"` như một giá trị `deliveryType`; với quy tắc hiện tại nó không phải khóa `EXPRESS`, nên phải đến `manualReview`.
4. Trong một cấu hình thực hành riêng, cố ý trỏ mapping `EXPRESS` đến tên channel không tồn tại; quan sát sự khác biệt giữa lỗi cấu hình và khóa chưa được hỗ trợ.
5. Vẽ thêm một transformer trước router và một handler sau mỗi nhánh; ghi rõ dữ liệu nào được biến đổi và bước nào chỉ chọn đường đi.

Khi đọc một router bất kỳ, hãy lần lượt xác định: nó nhận từ đâu, đọc dữ liệu gì, tạo khóa nào, chọn những channel nào và làm gì khi không có đích. Trả lời được các điểm đó là bạn đã nắm được vai trò cốt lõi của message router trong một luồng Spring Integration.