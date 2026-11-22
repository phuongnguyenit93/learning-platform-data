# Message filter là gì

Bài học thuộc chương **Filter** của module **Spring Integration Core (`SPRING_INTEGRATION_CORE`)**. Mục tiêu là hiểu cách một endpoint quyết định thông điệp nào được đi tiếp, rồi đặt quyết định đó vào luồng gồm `Message`, `MessageChannel`, gateway và Java DSL. Ví dụ dùng đơn hàng để kết nối filter với transformer, router, xử lý lỗi và kiểm thử các mẫu tích hợp doanh nghiệp.

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của kết quả `true`, `false` và exception trong bộ chọn thông điệp.
- Cấu hình nhánh đi tiếp và nhánh loại bằng Java DSL hoặc `@Filter`.
- Chọn chính sách phù hợp cho thông điệp bị loại.
- Kiểm thử kết quả ở các channel thay vì suy luận từ giá trị trả về của `send()`.

## 1. Bài toán mà Message Filter giải quyết

Giả sử dịch vụ tiếp nhận mọi sự kiện đơn hàng từ hệ thống bán hàng, nhưng công đoạn đặt chỗ kho chỉ xử lý đơn đã xác nhận. Các sự kiện `DRAFT`, `CANCELLED` hoặc đơn không đủ dữ liệu vẫn có thể xuất hiện trên luồng đầu vào.

Nếu mỗi thành phần phía sau đều tự kiểm tra điều kiện này, quy tắc sẽ bị lặp lại. Một **Message Filter** đặt tại ranh giới của công đoạn có thể kiểm tra một lần và chỉ cho những thông điệp phù hợp đi tiếp.

Trong Enterprise Integration Patterns, Message Filter chọn thông điệp dựa trên một tiêu chí; thông điệp không phù hợp không đi tới đầu ra được bảo vệ. Trong bài toán này, tiêu chí là “đơn hàng có đủ điều kiện đặt chỗ kho hay không”. [Nguồn: Enterprise Integration Patterns — Message Filter](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Filter.html).

~~~mermaid
flowchart LR
    A["orders.input"] --> F{"Đủ điều kiện?"}
    F -->|"true"| B["orders.accepted"]
    F -->|"false"| C["orders.rejected nếu cấu hình"]
    B --> D["Công đoạn đặt chỗ kho"]
~~~

Tên “filter” ở đây nói đến việc **chọn cả thông điệp**. Ví dụ, loại sự kiện của đơn `DRAFT` là lọc thông điệp; xóa trường số điện thoại khỏi JSON là thay đổi nội dung và nên được biểu diễn bằng bước biến đổi dữ liệu.

Một filter không mặc nhiên làm chậm luồng đến khi điều kiện trở thành đúng. Đơn `DRAFT` hôm nay không tự được giữ lại để chờ ngày mai chuyển thành `CONFIRMED`. Muốn xử lý sự thay đổi đó, hệ thống cần sự kiện mới hoặc một cơ chế lưu và xử lý lại được thiết kế riêng.

## 2. Filter đứng ở đâu trong Spring Integration?

Một `Message<T>` gồm payload và headers. Payload mang dữ liệu như đơn hàng; headers mang ngữ cảnh như nguồn gửi hoặc mã liên kết. Cấu trúc headers của message không cho phép sửa trực tiếp, nhưng đối tượng payload có thể vẫn mutable tùy thiết kế của ứng dụng. Vì vậy, predicate nên chỉ đọc dữ liệu. [Nguồn: Spring Integration — Message](https://docs.spring.io/spring-integration/reference/message.html).

Các vai trò trong luồng:

| Thành phần | Trách nhiệm trong ví dụ |
| --- | --- |
| `Message<Order>` | Mang đơn hàng và ngữ cảnh xử lý. |
| Input channel | Đưa message vào endpoint filter. |
| Endpoint filter | Nhận message và thực hiện việc chọn, gửi tiếp hoặc xử lý nhánh loại. |
| Selector | Chứa điều kiện chấp nhận, trả về boolean. |
| Output channel | Nhận message được chấp nhận. |
| Discard channel | Nhận message bị loại khi có cấu hình. |
| Gateway | Cung cấp giao diện Java để bên gọi tương tác với flow; cần xác định hợp đồng phản hồi. |

Trong cấu hình thông thường, `MessageFilter` là handler thực hiện việc lọc bên trong endpoint. Selector chỉ quyết định; nó không phải channel và cũng không tự gửi message tới một đích. [Nguồn: API MessageFilter](https://docs.spring.io/spring-integration/api/org/springframework/integration/filter/MessageFilter.html).

Java DSL mô tả sự kết hợp các channel và endpoint; framework đăng ký các thành phần thực hiện luồng trong application context. Lệnh `.filter(...)` thể hiện bước lọc trong mô tả đó. [Nguồn: Spring Integration 6.5 — DSL Basics](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-basics.html).

### So sánh với những bước gần nhau

| Thành phần | Câu hỏi thiết kế | Ví dụ |
| --- | --- | --- |
| Filter | Message này có được qua công đoạn không? | Chỉ nhận đơn đã xác nhận. |
| Router | Message này nên tới đích nào? | Đơn quốc tế tới luồng hải quan, đơn nội địa tới luồng giao hàng trong nước. |
| Transformer | Dữ liệu cần đổi thành dạng nào? | Chuyển JSON đơn hàng thành `Order`. |
| Service activator | Cần thực hiện hành động nào? | Gọi dịch vụ giữ hàng. |
| Aggregator | Khi nào một nhóm message đủ điều kiện để gộp? | Gộp các kết quả kiểm tra tồn kho của một đơn. |

Đọc thêm về các vai trò tương ứng tại [Router](https://docs.spring.io/spring-integration/reference/router.html), [Transformer](https://docs.spring.io/spring-integration/reference/transformer.html) và [Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html).

Filter có discard channel có thể biểu diễn một lựa chọn hai nhánh. Khi nghiệp vụ đã có nhiều loại kết quả như “đủ điều kiện”, “cần duyệt”, “hủy” và “thiếu dữ liệu”, router thường làm cấu trúc đó dễ đọc hơn một chuỗi filter lồng nhau.

## 3. Hợp đồng của selector: chấp nhận, từ chối và lỗi

`MessageSelector` là functional interface có phương thức `boolean accept(Message<?> message)`. Có thể viết implementation riêng, lambda hoặc method reference. [Nguồn: API MessageSelector](https://docs.spring.io/spring-integration/api/org/springframework/integration/core/MessageSelector.html).

Ví dụ chỉ chọn message có header `trusted` là boolean `true`:

~~~java
import org.springframework.integration.core.MessageSelector;

MessageSelector trustedSource = message ->
        Boolean.TRUE.equals(message.getHeaders().get("trusted"));
~~~

Trong quy ước của ví dụ, header không có hoặc có giá trị chuỗi `"true"` đều không được chấp nhận. Quy ước kiểu dữ liệu cần được thống nhất với bên tạo message; selector không tự hiểu mọi giá trị có vẻ tương đương.

Ba kết quả cần phân biệt:

| Kết quả khi đánh giá | Ý nghĩa |
| --- | --- |
| `true` | Chấp nhận message và chuyển tới bước tiếp theo. |
| `false` | Từ chối theo quy tắc chọn; áp dụng chính sách rejection. |
| Ném exception | Không đánh giá bình thường được; flow gặp lỗi thực thi. |

Ví dụ, trạng thái `DRAFT` có thể là một kết quả nghiệp vụ hợp lệ dẫn tới `false`. Ngược lại, dịch vụ tra cứu bị mất kết nối không chứng minh rằng đơn hàng không đủ điều kiện.

Đoạn sau làm mất sự phân biệt đó:

~~~java
// Tránh biến mọi sự cố thành một kết quả loại hợp lệ.
try {
    return eligibilityService.isEligible(order);
} catch (Exception exception) {
    return false;
}
~~~

Nếu quy tắc phải gọi dịch vụ ngoài, hãy quyết định rõ lỗi tạm thời được retry, đưa tới luồng lỗi hay được phản hồi như thế nào. Đừng che lỗi bằng `false` chỉ để luồng tiếp tục chạy.

Một selector dễ kiểm thử thường có các đặc điểm:

- Điều kiện có tên gắn với nghiệp vụ.
- Cùng dữ liệu và cùng ngữ cảnh cho cùng kết quả.
- Không sửa payload, không đặt chỗ kho, không gửi email.
- Xử lý rõ trường hợp thiếu dữ liệu thay vì vô tình ném `NullPointerException`.

## 4. Điều gì xảy ra khi selector trả về false?

Spring Integration có hai tùy chọn quan trọng:

- `discardChannel`: nơi nhận message bị loại.
- `throwExceptionOnRejection`: có phát sinh `MessageRejectedException` khi bị loại hay không.

Bảng hành vi dưới đây giả sử selector trả về `false` và việc gửi tới discard channel, nếu có, hoàn tất bình thường:

| Discard channel | `throwExceptionOnRejection` | Hành vi |
| --- | --- | --- |
| Không cấu hình | `false` | Không gửi tới output channel; message bị loại khỏi nhánh chính. |
| Có cấu hình | `false` | Gửi tới discard channel; không tạo exception chỉ vì bị loại. |
| Không cấu hình | `true` | Phát sinh `MessageRejectedException`. |
| Có cấu hình | `true` | Gửi tới discard channel rồi phát sinh `MessageRejectedException`. |

Giá trị mặc định của `throwExceptionOnRejection` là `false`. Việc cấu hình discard channel không vô hiệu hóa tùy chọn này. [Nguồn: API FilterEndpointSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/FilterEndpointSpec.html).

Từ Spring Integration 6.1, loại message khi không có discard channel và không bật exception được ghi cảnh báo. Muốn chủ động bỏ message mà không có cảnh báo mặc định này, có thể trỏ discard channel tới `nullChannel`. Đây là lựa chọn bỏ thông điệp có chủ đích. [Nguồn: Spring Integration — Filter](https://docs.spring.io/spring-integration/reference/filter.html).

Ví dụ một đoạn DSL dùng chính sách đó:

~~~java
.filter(Order.class,
        OrderFilterConfiguration::eligible,
        endpoint -> endpoint
                .discardChannel("nullChannel")
                .throwExceptionOnRejection(false))
~~~

Với thông điệp quan trọng, một nhánh lưu vết hoặc phản hồi rõ ràng thường có ích hơn việc bỏ ngay. Trong ví dụ đơn hàng bên dưới, ta giữ các message bị loại trong một queue để quan sát.

Lưu ý thêm:

- Discard channel nhận message bị loại, không mặc nhiên nhận `ErrorMessage`.
- Predicate trả `false` không tự động đưa message vào global `errorChannel`.
- Nếu chính việc gửi tới discard channel bị lỗi, đó là lỗi của nhánh xử lý loại.
- Tên “discard” không chứng minh rằng dữ liệu đã được lưu bền hoặc đã vào hàng đợi lỗi của broker.

## 5. Ví dụ đầy đủ: chỉ nhận đơn hàng đủ điều kiện

### 5.1. Quy tắc của bài thực hành

Trong ví dụ này, các message hợp lệ cho công đoạn tiếp theo phải có:

1. Payload đúng kiểu `Order`.
2. Mã đơn hàng không rỗng.
3. Trạng thái chính xác là `CONFIRMED`.
4. Tổng tiền lớn hơn `0` và không vượt `10.000.000` đơn vị tiền.

Đơn vị tiền được giả định thống nhất trong bài tập. Giới hạn trên là quy tắc minh họa của công đoạn tự động; đơn vượt giới hạn được đưa sang nhánh loại để xử lý riêng.

| Dữ liệu đầu vào | Kết quả mong đợi |
| --- | --- |
| `O-101`, `CONFIRMED`, `250000` | Đi tiếp. |
| `O-102`, `DRAFT`, `250000` | Bị loại. |
| `O-103`, `CONFIRMED`, `0` | Bị loại. |
| `O-104`, `CONFIRMED`, `10000000` | Đi tiếp tại biên trên. |
| `O-105`, `CONFIRMED`, `10000000.01` | Bị loại. |
| Mã đơn là chuỗi trắng | Bị loại. |
| Payload là chuỗi thay vì `Order` | Bị loại bởi kiểm tra kiểu. |

### 5.2. Điều kiện sử dụng ví dụ

Cấu hình dưới đây dùng cú pháp Java 17 và Java DSL của Spring Integration 6.x. Dự án cần dependency `org.springframework.integration:spring-integration-core` cùng các dependency Spring tương thích; nếu dùng Spring Boot, để BOM của Boot quản lý phiên bản và có thể dùng `spring-boot-starter-integration`.

Ví dụ dùng application context thuần để làm rõ endpoint và channel. Không cần broker hoặc dịch vụ ngoài. Phần kiểm thử dùng JUnit Jupiter.

Toàn bộ lớp sau có thể đặt trong tệp `OrderFilterConfiguration.java` của dự án thực hành:

~~~java
package example.integration.filter;

import java.math.BigDecimal;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSelector;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderFilterConfiguration {

    private static final BigDecimal MAX_TOTAL =
            new BigDecimal("10000000");

    public record Order(
            String id,
            String status,
            BigDecimal total) {
    }

    public static boolean eligible(Order order) {
        return order != null
                && order.id() != null
                && !order.id().isBlank()
                && "CONFIRMED".equals(order.status())
                && order.total() != null
                && order.total().compareTo(BigDecimal.ZERO) > 0
                && order.total().compareTo(MAX_TOTAL) <= 0;
    }

    @Bean(name = "orders.input")
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.accepted")
    public QueueChannel ordersAccepted() {
        return new QueueChannel();
    }

    @Bean(name = "orders.rejected")
    public QueueChannel ordersRejected() {
        return new QueueChannel();
    }

    @Bean
    public MessageSelector eligibleOrderSelector() {
        return message ->
                message.getPayload() instanceof Order order
                        && eligible(order);
    }

    @Bean
    public IntegrationFlow orderEligibilityFlow(
            @Qualifier("eligibleOrderSelector")
            MessageSelector selector) {

        return IntegrationFlow.from("orders.input")
                .filter(Message.class, selector::accept,
                        endpoint -> endpoint
                                .id("orderEligibilityFilter")
                                .discardChannel("orders.rejected")
                                .throwExceptionOnRejection(false))
                .channel("orders.accepted")
                .get();
    }
}
~~~

Trong ví dụ này, truyền `Message.class` cho overload của `filter` để selector nhận toàn bộ message. Nếu truyền một lớp payload như `Order.class`, đối số của lambda là payload thuộc kiểu đó; framework có thể thử chuyển kiểu khi cần. Vì vậy, overload có kiểu không nên được hiểu là cơ chế tự động trả `false` cho mọi payload sai kiểu. [Nguồn: API BaseIntegrationFlowDefinition — filter](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html).

### 5.3. Giải thích các lựa chọn

`eligible(Order)` chỉ chứa quy tắc nghiệp vụ nên có thể kiểm thử độc lập. `eligibleOrderSelector` bổ sung việc kiểm tra kiểu payload ở ranh giới messaging. Trong bài này, sai kiểu được coi là một trường hợp cần đưa tới `orders.rejected`; ứng dụng thực tế có thể chọn báo lỗi nếu đây là vi phạm hợp đồng nghiêm trọng.

`BigDecimal.compareTo(...)` phù hợp để so sánh giá trị tiền trong quy tắc. Không dùng `equals` để kiểm tra lớn hơn/nhỏ hơn và không tạo số tiền từ literal `double`.

`orders.input` là `DirectChannel`: với cấu hình này, endpoint filter được gọi trong thread gửi. Hai channel đầu ra là `QueueChannel` để bài thực hành chủ động lấy kết quả bằng `receive(...)`. Queue ở đây lưu trong bộ nhớ theo cấu hình mặc định; không phải kho lưu bền. [Nguồn: Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Flow kết thúc ở hai queue để dễ quan sát. Chưa có công đoạn nào tự lấy đơn hàng ra đặt chỗ kho. Nếu đổi một đầu ra thành `DirectChannel`, phải có subscriber phù hợp cho nó; khi dùng queue làm đầu vào của một endpoint tiếp theo, cần cấu hình cơ chế polling.

### 5.4. Gửi message và quan sát

Đoạn sau là mã đặt trong một phương thức thử nghiệm, dùng lớp cấu hình phía trên:

~~~java
try (var context =
        new org.springframework.context.annotation
                .AnnotationConfigApplicationContext(
                        OrderFilterConfiguration.class)) {

    var input = context.getBean(
            "orders.input",
            org.springframework.messaging.MessageChannel.class);

    var accepted = context.getBean(
            "orders.accepted",
            org.springframework.integration.channel.QueueChannel.class);

    var rejected = context.getBean(
            "orders.rejected",
            org.springframework.integration.channel.QueueChannel.class);

    var order = new OrderFilterConfiguration.Order(
            "O-101",
            "CONFIRMED",
            new java.math.BigDecimal("250000"));

    var message = org.springframework.messaging.support.MessageBuilder
            .withPayload(order)
            .setHeader("correlationId", "checkout-101")
            .build();

    boolean sent = input.send(message);

    System.out.println("send = " + sent);
    System.out.println("accepted = " + accepted.receive(0));
    System.out.println("rejected = " + rejected.receive(0));
}
~~~

Với dữ liệu trên, queue accepted có một message và queue rejected rỗng. Nếu đổi trạng thái thành `DRAFT`, kết quả đảo lại.

`send` vẫn có thể là `true` trong cả hai tình huống: message đã được giao và endpoint đã xử lý bình thường, kể cả khi quyết định là loại message. Giá trị này không phải kết quả của `selector.accept(...)`. Kết luận “đơn đã được chấp nhận” phải dựa trên hợp đồng phản hồi hoặc kết quả tại đầu ra nghiệp vụ.

`receive(0)` lấy ngay message nếu có; queue rỗng trả `null`. Trong ví dụ đồng bộ, sau khi `send` kết thúc thì bước lọc và gửi vào queue đã hoàn tất. Khi chuyển sang luồng bất đồng bộ, kiểm thử phải có thời hạn chờ thích hợp.

## 6. Các cách biểu diễn điều kiện lọc

Các đoạn trong phần này là **phương án thay thế**, không đăng ký thêm tất cả lên cùng `orders.input`. Nhiều consumer trên một point-to-point channel sẽ làm thay đổi cách phân phối message.

### 6.1. Lambda chỉ cần payload

Khi hợp đồng đầu vào đã bảo đảm payload là `Order`, có thể rút gọn bước lọc:

~~~java
return IntegrationFlow.from("orders.input")
        .filter(OrderFilterConfiguration.Order.class,
                OrderFilterConfiguration::eligible,
                endpoint -> endpoint
                        .discardChannel("orders.rejected")
                        .throwExceptionOnRejection(false))
        .channel("orders.accepted")
        .get();
~~~

Cách này thể hiện quy tắc về đơn hàng rõ ràng. Nếu cần kiểm tra header hoặc tự xử lý payload khác kiểu, dùng toàn bộ `Message` như cấu hình chính.

### 6.2. Điều kiện dựa trên header

Một cổng tiếp nhận có thể chỉ cho sự kiện từ nguồn đã xác thực đi tiếp:

~~~java
return IntegrationFlow.from("trusted.input")
        .filter(Message.class,
                message -> Boolean.TRUE.equals(
                        message.getHeaders().get("trusted")),
                endpoint -> endpoint
                        .discardChannel("trusted.rejected"))
        .channel("trusted.accepted")
        .get();
~~~

Các channel `trusted.*` cần được khai báo trong cấu hình tương ứng. Header `trusted` phải được thiết lập tại một ranh giới đáng tin cậy, chẳng hạn sau bước kiểm tra danh tính nguồn gửi; dữ liệu do bên gửi tùy ý gắn vào không đủ làm bằng chứng.

Nếu cùng lúc lọc theo header và payload, đặt tên quy tắc như `eligibleTrustedOrder` hoặc tách thành hai bước có tên, tùy nhu cầu quan sát. Hai filter nối tiếp mang ý nghĩa cả hai điều kiện đều phải đạt; message bị loại ở bước đầu không tới bước thứ hai.

### 6.3. Biểu thức SpEL ngắn

Ví dụ chỉ chấp nhận nguồn có header boolean:

~~~java
return IntegrationFlow.from("trusted.input")
        .filter("headers['trusted'] == true",
                endpoint -> endpoint
                        .discardChannel("trusted.rejected"))
        .channel("trusted.accepted")
        .get();
~~~

Biểu thức này là cấu hình tĩnh do ứng dụng quản lý. Với điều kiện có nhiều trường, nhiều nhánh hoặc cần giải thích lý do, một phương thức Java có tên thường dễ kiểm thử và bảo trì hơn một biểu thức dài. Spring Integration hỗ trợ cấu hình filter bằng biểu thức. [Nguồn: Spring Integration — Filter](https://docs.spring.io/spring-integration/reference/filter.html).

### 6.4. Annotation @Filter

Một phương án khác là đăng ký bean có phương thức boolean được đánh dấu `@Filter`:

~~~java
package example.integration.filter;

import org.springframework.integration.annotation.Filter;

public class OrderPolicy {

    @Filter(
            inputChannel = "orders.input",
            outputChannel = "orders.accepted",
            discardChannel = "orders.rejected",
            throwExceptionOnRejection = "false")
    public boolean accept(OrderFilterConfiguration.Order order) {
        return OrderFilterConfiguration.eligible(order);
    }
}
~~~

Để phương án này hoạt động, đăng ký `OrderPolicy` thành Spring bean, giữ các bean channel và `@EnableIntegration`, đồng thời bỏ bean `orderEligibilityFlow` của phương án Java DSL. Không đăng ký đồng thời hai endpoint cho cùng bài thử.

Thuộc tính `throwExceptionOnRejection` trên annotation nhận chuỗi, còn trong Java DSL nhận boolean. Phương thức annotation trong ví dụ nhận payload `Order`, nên không giữ chính sách xử lý mọi payload khác kiểu như selector của cấu hình chính. [Nguồn: API @Filter](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Filter.html).

## 7. Rejection, error handling và gateway

### 7.1. Từ chối nghiệp vụ không nhất thiết là lỗi kỹ thuật

Với hệ thống đơn hàng, có thể chọn:

| Tình huống | Chính sách minh họa |
| --- | --- |
| Sự kiện `DRAFT` không thuộc công đoạn hiện tại | Đưa sang nhánh loại có lưu vết. |
| Tổng tiền vượt giới hạn tự động | Đưa sang công đoạn duyệt thủ công. |
| Thiếu mã đơn hàng | Phản hồi hoặc ghi nhận vi phạm hợp đồng dữ liệu. |
| Dịch vụ tra cứu không truy cập được | Luồng lỗi kỹ thuật, có chính sách retry nếu phù hợp. |

Đây là quyết định thiết kế của ứng dụng. Không có một quy tắc chung rằng mọi message bị filter loại đều cần retry hoặc đều có thể bỏ.

Nếu bật `throwExceptionOnRejection(true)`, exception được dùng để báo rằng selector đã từ chối message. `MessageRejectedException` thuộc hệ thống exception của Spring Messaging. [Nguồn: API MessageRejectedException](https://docs.spring.io/spring-integration/api/org/springframework/integration/MessageRejectedException.html).

Với điều kiện thuần túy và dữ liệu không thay đổi, retry ngay cùng một message `DRAFT` sẽ tiếp tục bị loại. Retry chỉ có ích khi nguyên nhân có khả năng thay đổi và chính sách của hệ thống cho phép.

### 7.2. Exception đi đâu phụ thuộc cách flow được thực thi

Trong luồng đồng bộ qua `DirectChannel`, lỗi có thể truyền về bên gửi. Không nên mặc định rằng chỉ cần tồn tại bean `errorChannel` là mọi exception đồng bộ đều được chuyển tới đó.

Trong luồng do poller hoặc cơ chế bất đồng bộ của framework thực thi, error handler có thể tạo `ErrorMessage` và gửi tới header `errorChannel` hoặc channel lỗi mặc định. Hành vi cụ thể còn tùy thành phần khởi chạy và cấu hình error handler. [Nguồn: Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Đặc biệt, nếu vừa gửi message bị loại vào discard channel vừa ném exception, cơ chế retry bên ngoài có thể khiến nhánh discard chạy lại. Nhánh ghi audit, gửi email hoặc tạo yêu cầu duyệt cần tính đến khả năng lặp.

### 7.3. Gateway cần một hợp đồng phản hồi đầy đủ

Giả sử gateway có phương thức:

~~~java
OrderResult submit(Order order);
~~~

Nếu flow lọc bỏ message mà không tạo reply hay ném exception, bên gọi vẫn đang chờ `OrderResult`. Việc không có reply có thể dẫn tới hết thời gian chờ, trả `null` hoặc hành vi báo lỗi tùy cấu hình; không nên dùng nó làm tín hiệu nghiệp vụ ngầm. [Nguồn: Spring Integration — Messaging Gateways, phần không có phản hồi](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-no-response).

Với một API cần trả kết quả cho mọi yêu cầu, có thể chọn một trong các hướng:

- Dùng router để cả nhánh chấp nhận lẫn nhánh từ chối đều tạo một `OrderResult` rõ ràng.
- Cho rejection phát sinh exception và ánh xạ lỗi phù hợp tại ranh giới gọi.
- Dùng hợp đồng gửi một chiều khi bên gọi thực sự không cần kết quả xử lý nghiệp vụ.

Chỉ đặt discard channel thành một queue không tự trả lời gateway. Nếu chọn nhánh từ chối có phản hồi, phải nối nhánh đó tới bước tạo reply và kiểm tra đường quay về của reply.

Cấu hình ở phần 5 là bài thực hành gửi message trực tiếp và đọc queue; nó chưa phải một flow request–reply hoàn chỉnh.

## 8. Những tương tác dễ gây hiểu nhầm

### 8.1. Point-to-point không phải broadcast

Giả sử hai filter cùng đăng ký trên một `DirectChannel`:

- Filter A chọn đơn nội địa.
- Filter B chọn đơn quốc tế.

Không được suy luận rằng mọi message sẽ được cả A và B đánh giá. `DirectChannel` có ngữ nghĩa point-to-point và việc dispatch có thể có load balancing/failover. Nếu cần phân nhánh theo loại đơn, dùng router; nếu mỗi subscriber cần nhìn thấy sự kiện, xem xét `PublishSubscribeChannel` và quy tắc xử lý lỗi của nó. [Nguồn: Spring Integration — Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Việc A trả `false` và kết thúc bình thường cũng không tương đương một exception để dispatcher tự thử B. Cấu hình selective consumer dựa trên failover là một cơ chế khác và không cần thiết cho bài thực hành này.

### 8.2. Filter sau splitter có thể làm aggregator thiếu phần tử

Ví dụ một splitter tạo ba message với `sequenceSize = 3`. Nếu filter loại một message trước aggregator, aggregator dùng điều kiện mặc định theo kích thước sequence có thể chỉ nhận hai message và chưa giải phóng nhóm.

Đây là hệ quả của việc thay đổi số lượng message trên đường đi. Cần thiết kế điều kiện release, timeout hoặc cách thể hiện kết quả bị loại cho phù hợp; đừng tự ý sửa sequence header chỉ để nhóm thoát chờ. [Nguồn: Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html).

### 8.3. Boolean không mang lý do từ chối

`false` không phân biệt “thiếu mã”, “chưa xác nhận” hay “vượt giới hạn”. Discard channel cũng không tự được thêm trường lý do tương ứng.

Nếu hệ thống cần lý do chi tiết, hãy tính một kết quả đánh giá có cấu trúc, ví dụ:

~~~java
public record EligibilityDecision(
        boolean accepted,
        String reasonCode) {
}
~~~

Một bước đánh giá có thể tạo kết quả đó trước khi router quyết định nhánh. Tránh tính lại cùng điều kiện có gọi dịch vụ ngoài ở cả filter lẫn discard handler, vì hai lần đánh giá có thể tốn kém và cho kết quả khác nhau.

### 8.4. Filter không tự cung cấp lưu bền hoặc xác nhận broker

Lọc ở application flow chưa quyết định toàn bộ vòng đời message tại Kafka, AMQP hay JMS. Commit offset, acknowledgement, rollback và redelivery còn phụ thuộc adapter, transaction và cấu hình xử lý lỗi của giao thức.

Vì thế, cần mô tả rõ “bị loại khỏi công đoạn này” khác với “đã được xác nhận tại nguồn” hoặc “đã được lưu để xử lý lại”. Trong bài thực hành, chỉ có các channel trong bộ nhớ và không có broker.

## 9. Kiểm thử filter bằng kết quả quan sát được

Nên kiểm tra hai lớp:

1. **Quy tắc**: `eligible(Order)` trả về đúng ở các giá trị biên.
2. **Wiring của flow**: message đi vào đúng channel, nhánh còn lại không nhận và headers cần thiết vẫn được giữ.

Spring Integration có các module hỗ trợ kiểm thử cho những flow phức tạp. Ví dụ dưới đây dùng application context và queue thật trong bộ nhớ, nên chỉ cần JUnit Jupiter cho phần test; chưa cần mocking endpoint. [Nguồn: Spring Integration — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html).

Lớp kiểm thử tương ứng với cấu hình Java DSL ở phần 5:

~~~java
package example.integration.filter;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class OrderFilterFlowTest {

    @Test
    void acceptedOrderGoesOnlyToAcceptedChannel() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFilterConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "orders.input", MessageChannel.class);
            QueueChannel accepted = context.getBean(
                    "orders.accepted", QueueChannel.class);
            QueueChannel rejected = context.getBean(
                    "orders.rejected", QueueChannel.class);

            var order = new OrderFilterConfiguration.Order(
                    "O-101", "CONFIRMED", new BigDecimal("250000"));

            Message<?> original = MessageBuilder.withPayload(order)
                    .setHeader("correlationId", "checkout-101")
                    .build();

            assertTrue(input.send(original));

            Message<?> result = accepted.receive(0);
            assertNotNull(result);
            assertEquals(order, result.getPayload());
            assertEquals("checkout-101",
                    result.getHeaders().get("correlationId"));
            assertNull(rejected.receive(0));
        }
    }

    @Test
    void draftOrderGoesOnlyToRejectedChannelEvenWhenSendSucceeds() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFilterConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "orders.input", MessageChannel.class);
            QueueChannel accepted = context.getBean(
                    "orders.accepted", QueueChannel.class);
            QueueChannel rejected = context.getBean(
                    "orders.rejected", QueueChannel.class);

            var order = new OrderFilterConfiguration.Order(
                    "O-102", "DRAFT", new BigDecimal("250000"));

            Message<?> original = MessageBuilder.withPayload(order)
                    .setHeader("correlationId", "checkout-102")
                    .build();

            assertTrue(input.send(original));
            assertNull(accepted.receive(0));

            Message<?> result = rejected.receive(0);
            assertNotNull(result);
            assertEquals(order, result.getPayload());
            assertEquals("checkout-102",
                    result.getHeaders().get("correlationId"));
        }
    }

    @Test
    void unexpectedPayloadTypeIsRejectedByTheMessageSelector() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFilterConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "orders.input", MessageChannel.class);
            QueueChannel accepted = context.getBean(
                    "orders.accepted", QueueChannel.class);
            QueueChannel rejected = context.getBean(
                    "orders.rejected", QueueChannel.class);

            input.send(MessageBuilder.withPayload("not-an-order").build());

            assertNull(accepted.receive(0));
            Message<?> result = rejected.receive(0);
            assertNotNull(result);
            assertEquals("not-an-order", result.getPayload());
        }
    }
}
~~~

Mỗi test mở một context riêng để tránh message của test trước còn trong queue. Test đầu kiểm tra dữ liệu và header nghiệp vụ; không ràng buộc vào việc output có cùng object identity với message đầu vào.

Để bổ sung độ phủ cho quy tắc, dùng các dữ liệu sau khi kiểm thử trực tiếp `eligible(Order)`:

| Biến thể so với đơn hợp lệ | Kết quả |
| --- | --- |
| `total = 0` | `false` |
| `total < 0` | `false` |
| `total = 10000000` | `true` |
| `total = 10000000.01` | `false` |
| `total = null` | `false` |
| `id = null` hoặc chuỗi trắng | `false` |
| `status = null` hoặc `"confirmed"` | `false` |
| Tham số `order = null` | `false` |

Trường hợp `order = null` thuộc kiểm thử hàm thuần; không tạo message có payload null để giả lập nó.

Khi thay đổi chính sách rejection, bổ sung kiểm thử tương ứng:

- Bật exception và dùng một subscriber duy nhất trên `DirectChannel`: kiểm tra lỗi mà bên gửi quan sát được.
- Dùng cả discard channel và exception: kiểm tra message vào discard channel trước khi lỗi được báo.
- Selector chủ động ném lỗi kỹ thuật: kiểm tra không bị hiểu thành rejection bình thường.
- Chuyển sang async: chờ kết quả trong thời hạn xác định, không dựa vào `Thread.sleep` tùy ý.
- Gắn gateway request–reply: kiểm tra cả kết quả chấp nhận và từ chối đều hoàn tất theo hợp đồng.

Các đoạn kiểm thử trong bài là mã thực hành để chạy trong dự án có dependency phù hợp; bài viết không thay thế kết quả chạy test của dự án.

## 10. Chọn filter và đặt nó đúng chỗ

Một cách ra quyết định cho luồng đơn hàng:

1. Xác định công đoạn được bảo vệ, chẳng hạn đặt chỗ kho.
2. Chuẩn hóa dữ liệu cần thiết trước khi đánh giá nếu đầu vào đang là JSON hoặc định dạng bên ngoài.
3. Đặt tên điều kiện như `eligibleForReservation`.
4. Quy định riêng dữ liệu không phù hợp và lỗi không thể đánh giá.
5. Chọn đích xử lý message bị loại, cùng nhu cầu lưu vết hoặc phản hồi.
6. Kiểm tra ảnh hưởng tới gateway, sequence và transaction.
7. Quan sát tỷ lệ chấp nhận, tỷ lệ loại và lỗi kỹ thuật bằng các chỉ số riêng.

Không đưa mã đơn hàng làm nhãn metric có số lượng giá trị không giới hạn. Khi cần tra cứu từng trường hợp, dùng log có mã liên kết và mã lý do phù hợp, tránh ghi toàn bộ payload một cách máy móc.

Một vài lựa chọn cụ thể:

| Nhu cầu | Hướng triển khai |
| --- | --- |
| Bỏ qua sự kiện không thuộc công đoạn, đã có chính sách rõ | Filter với chính sách discard phù hợp. |
| Chọn một trong nhiều công đoạn nghiệp vụ | Router. |
| Đổi schema hoặc che trường dữ liệu | Transformer hoặc bước xử lý nội dung. |
| Cần kết quả đánh giá gồm nhiều lỗi | Bước đánh giá riêng trả dữ liệu có cấu trúc. |
| Chống xử lý lặp qua nhiều lần giao message | Thiết kế idempotency với trạng thái và ranh giới xử lý rõ. |
| Chờ một điều kiện có thể đúng trong tương lai | Cơ chế lưu, lập lịch hoặc xử lý lại. |

## 11. Thực hành mở rộng

Bắt đầu với cấu hình Java DSL và các test ở phần 9, sau đó thực hiện lần lượt:

1. Đổi trạng thái của `O-101` thành `DRAFT`; xác nhận chỉ nhánh rejected có dữ liệu.
2. Thử đúng giá trị biên `10000000` và giá trị vượt biên `10000000.01`.
3. Thêm điều kiện header `trusted` bằng kiểu boolean, kiểm tra trường hợp thiếu header và header dạng chuỗi.
4. Trong một cấu hình thử riêng, bật `throwExceptionOnRejection(true)` và quan sát bên gửi cùng queue rejected.
5. Thiết kế hợp đồng `OrderResult` nếu muốn chuyển bài thực hành thành một gateway có phản hồi cho mọi yêu cầu.

Điểm cần giữ xuyên suốt là: **selector quyết định chấp nhận hay từ chối; cấu hình endpoint và các nhánh của flow quyết định điều gì xảy ra tiếp theo**. Một filter hoàn chỉnh trong ứng dụng cần cả quy tắc đúng lẫn chính sách rõ ràng cho message không được đi tiếp.
