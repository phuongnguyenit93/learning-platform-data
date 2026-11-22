# Channel là điểm tách các component

Trong chương **Message channel** của module **SPRING_INTEGRATION_CORE**, channel được xem là ranh giới giao tiếp giữa các thành phần của luồng thông điệp. Producer gửi một `Message` đến channel; endpoint phía nhận tiếp tục xử lý mà producer không cần gọi trực tiếp lớp triển khai của consumer.

Ranh giới này giúp ghép các bước transformer, filter, router, service activator hoặc aggregator thành luồng có thể thay đổi. Để thiết kế đúng, cần phân biệt việc tách phụ thuộc giữa các component với việc tách thời gian thực thi, luồng xử lý và transaction.

Sau bài học, bạn có thể:

- Giải thích channel loại bỏ phụ thuộc nào và giữ lại những hợp đồng nào.
- Tách producer khỏi consumer bằng một channel có tên rõ nghĩa.
- Xây dựng ví dụ Java DSL với các component có thể kiểm thử độc lập.
- Đánh giá ảnh hưởng của việc chuyển từ xử lý đồng bộ sang xử lý qua hàng đợi.
- Nhận diện các lỗi thiết kế khiến hai component vẫn phụ thuộc chặt dù đã dùng message.

## 1. Từ lời gọi trực tiếp đến ranh giới thông điệp

Giả sử một ứng dụng nhận yêu cầu chuẩn bị đơn hàng. Với lời gọi trực tiếp, thành phần tiếp nhận có thể giữ tham chiếu đến dịch vụ xử lý:

~~~java
public final class OrderSubmission {
    private final OrderPreparationService preparation;

    public OrderSubmission(OrderPreparationService preparation) {
        this.preparation = preparation;
    }

    public PreparedOrder submit(PrepareOrder command) {
        return preparation.prepare(command);
    }
}
~~~

Thiết kế này phù hợp khi quan hệ gọi và nhận kết quả đơn giản. Tuy nhiên, nếu thành phần tiếp nhận còn tự gọi kiểm tra gian lận, ghi nhật ký và gửi thông báo, nó sẽ đồng thời biết nhiều chi tiết về cách tổ chức quy trình.

Với channel, producer giao một thông điệp cho một điểm vào:

~~~mermaid
flowchart LR
    P["Producer: tiếp nhận yêu cầu"] --> C["Channel: orders.prepare"]
    C --> E["Endpoint: transformer"]
    E --> S["POJO: chuẩn bị đơn hàng"]
    E --> O["Channel: orders.prepared"]
~~~

Producer biết nơi gửi và ý nghĩa thông điệp. Cấu hình integration quyết định endpoint nào tiếp nhận, gọi dịch vụ nào và đưa kết quả đi đâu. Đây là cách áp dụng khả năng ghép luồng qua channel mà Spring Integration hỗ trợ. [Tài liệu Integration Flows Composition](https://docs.spring.io/spring-integration/reference/dsl/integration-flows-composition.html).

Ví dụ, bạn có thể thay dịch vụ chuẩn bị đơn hàng hoặc thêm bước kiểm tra trước khi gọi dịch vụ mà không thêm phụ thuộc đến dịch vụ mới trong producer. Việc thay đổi vẫn phải bảo toàn hợp đồng đầu vào của channel.

Channel phù hợp khi ranh giới này phục vụ nhu cầu tích hợp cụ thể. Nếu chỉ cần gọi một hàm tính toán nội bộ, lời gọi Java thông thường vẫn là lựa chọn dễ hiểu.

## 2. Message, channel và endpoint đảm nhiệm những việc khác nhau

| Thành phần | Trách nhiệm | Ví dụ trong bài |
| --- | --- | --- |
| Producer | Tạo và gửi thông điệp | `OrderPublisher` |
| Message | Mang payload và metadata | `PrepareOrder` cùng `requestId` |
| Channel | Cung cấp điểm giao nhận | `orders.prepare` |
| Endpoint | Kết nối channel với hoạt động xử lý | Endpoint do `.transform(...)` tạo |
| POJO nghiệp vụ | Thực hiện phép xử lý dữ liệu | `OrderPreparationService` |
| Cấu hình luồng | Ghép các thành phần với nhau | `OrderFlowConfig` |

`MessageChannel` cung cấp các phương thức `send(...)`. `SubscribableChannel` bổ sung khả năng đăng ký handler; `PollableChannel` bổ sung `receive(...)`. Vì vậy, producer có thể chỉ phụ thuộc `MessageChannel`, trong khi thành phần chủ động lấy message cần `PollableChannel`. [Tài liệu các interface channel](https://docs.spring.io/spring-integration/reference/channel/interfaces.html).

Một phép biến đổi như chuẩn hóa mã khách hàng thuộc transformer hoặc POJO được transformer gọi. Việc quyết định nhánh xử lý theo nội dung thuộc router. Điều kiện chấp nhận hoặc loại bỏ message thuộc filter. Channel cung cấp ranh giới để những hoạt động đó nối với nhau.

Sự phân chia này giúp đọc luồng theo hai câu hỏi:

1. Thông điệp đang ở ranh giới nào?
2. Thành phần nào chịu trách nhiệm xử lý tại ranh giới đó?

Không nên đặt toàn bộ quy tắc nghiệp vụ vào interceptor của channel chỉ vì interceptor có thể nhìn thấy message. Khi đó hành vi nghiệp vụ bị ẩn khỏi cấu trúc luồng.

## 3. Channel tách được những loại phụ thuộc nào?

### 3.1. Phụ thuộc đến đối tượng nhận cụ thể

Nếu producer giữ `OrderPreparationService`, nó biết đối tượng nhận theo mô hình gọi hàm. Nếu producer giữ `MessageChannel`, cấu hình Spring sẽ nối điểm gửi với phía nhận.

Thay đổi lớp triển khai consumer có thể chỉ ảnh hưởng phần cấu hình và consumer. Producer vẫn gửi cùng kiểu yêu cầu.

### 3.2. Phụ thuộc đến cách ghép quy trình

Sau channel, bạn có thể bổ sung một transformer, filter hoặc router trước consumer hiện tại. Producer không phải tự quyết định thứ tự gọi từng bước.

Tuy nhiên, nếu bước mới loại bỏ một số yêu cầu hoặc làm thay đổi cách báo lỗi, hành vi quan sát từ producer có thể thay đổi. Tách cấu hình không miễn trừ việc đánh giá hợp đồng.

### 3.3. Phụ thuộc về thời điểm và tài nguyên

Một channel xử lý trực tiếp có thể vẫn buộc producer chờ consumer. Một hàng đợi có thể cho phép gửi trước, xử lý sau trong giới hạn dung lượng. Một executor có thể đưa công việc sang worker thread.

Đây là các quyết định thực thi riêng, cần được lựa chọn theo nhu cầu của ranh giới.

| Loại phụ thuộc | Channel có thể giúp như thế nào? | Điều vẫn phải thống nhất |
| --- | --- | --- |
| Đối tượng nhận | Producer không giữ consumer cụ thể | Tên hoặc tham chiếu channel |
| Cấu trúc quy trình | Cấu hình quyết định các bước tiếp theo | Ý nghĩa đầu vào và đầu ra |
| Dữ liệu | Message đóng gói payload và headers | Schema, kiểu dữ liệu, đơn vị |
| Thời điểm | Có thể bố trí hàng đợi | Dung lượng, độ trễ và timeout |
| Luồng thực thi | Có thể sử dụng executor | Lỗi, thứ tự và context |
| Triển khai | Có thể đặt adapter ở ranh giới hệ thống | Giao thức, serialization, độ tin cậy |

Một channel trong bộ nhớ của ứng dụng không tự tạo ra kết nối giữa hai tiến trình. Nếu tách producer và consumer thành hai dịch vụ triển khai độc lập, bạn còn cần hạ tầng truyền thông, adapter và hợp đồng dữ liệu phù hợp.

## 4. Hợp đồng channel phải rõ hơn một tên bean

Giả sử producer gửi vào `orders.prepare`. Một hợp đồng hữu ích nên trả lời được các câu hỏi sau.

| Nội dung | Quy ước minh họa |
| --- | --- |
| Mục đích | Yêu cầu chuẩn bị dữ liệu đơn hàng |
| Payload | `PrepareOrder` |
| Trường bắt buộc | `orderId`, `customerCode`, `total` |
| Quy tắc dữ liệu | Mã không rỗng, `total > 0` |
| Header bắt buộc | `requestId` kiểu `String`, `schemaVersion` kiểu `Integer` |
| Mô hình giao tiếp | Một yêu cầu được một luồng nghiệp vụ xử lý |
| Kết quả | Message `PreparedOrder` tại `orders.prepared` |
| Ý nghĩa thành công | Dữ liệu đã được chuẩn bị và đưa đến channel kết quả trong ví dụ đồng bộ |
| Tác dụng bên ngoài | Ví dụ không ghi database hoặc gọi hệ thống thanh toán |

Các tên và quy ước trên là thiết kế của ví dụ. Trong dự án thực tế, cần chọn tên phù hợp ngôn ngữ nghiệp vụ và ghi lại ý nghĩa của chúng.

### 4.1. Payload vẫn là một dạng phụ thuộc

Dùng message không xóa phụ thuộc dữ liệu. Nếu producer gửi `String` nhưng consumer đòi `PrepareOrder`, hoặc cùng dùng số tiền nhưng khác đơn vị, ranh giới vẫn hỏng.

Với luồng trong cùng ứng dụng, record Java là một lựa chọn đơn giản cho hợp đồng. Khi chuyển qua mạng, cần thêm quy tắc biểu diễn, phiên bản schema và tương thích giữa hai phía.

Tránh đưa JPA entity đang gắn với persistence context, HTTP request hoặc service bean vào payload để consumer gọi ngược. Hãy gửi dữ liệu mà phía nhận cần để thực hiện trách nhiệm đã thỏa thuận.

### 4.2. Headers cũng thuộc hợp đồng

`requestId` trong bài là header do ứng dụng quy định để nối các bước của cùng một yêu cầu. Nó không tự mang ý nghĩa khử trùng lặp. Nếu muốn dùng làm khóa idempotency, phải xác định thêm phạm vi duy nhất, thời gian lưu và hành vi khi nhận lại.

`schemaVersion` cũng chỉ là metadata nếu không có component kiểm tra nó. Gắn giá trị `1` không tự tạo cơ chế quản lý phiên bản.

### 4.3. Không chia sẻ trạng thái có thể bị sửa tùy ý

`Message` đóng gói payload cùng headers; việc không thể thay payload trên message không có nghĩa đối tượng payload tự trở thành bất biến sâu. Giá trị header cũng có thể là đối tượng mutable. [Tài liệu Message](https://docs.spring.io/spring-integration/reference/message.html).

Vì vậy, với payload có `List` hoặc `Map`, hãy cân nhắc tạo bản sao và giới hạn khả năng sửa đổi. Nếu nhiều nhánh cùng nhìn thấy một đối tượng có thể bị sửa, thay đổi trong một nhánh có thể làm nhánh khác khó dự đoán.

Hai record của ví dụ chỉ chứa `String` và `BigDecimal`, giúp tránh vấn đề chia sẻ đối tượng mutable trong phạm vi dữ liệu minh họa.

## 5. Chọn channel cũng là chọn một phần hành vi

Các lựa chọn dưới đây phục vụ những ranh giới khác nhau:

| Channel | Cách giao nhận chính | Ý nghĩa thiết kế cần chú ý |
| --- | --- | --- |
| `DirectChannel` | Gọi handler trong thread gửi | Tách component nhưng producer vẫn chờ việc xử lý trực tiếp |
| `QueueChannel` | Lưu message để phía nhận lấy ra | Có bộ đệm; cần consumer lấy message |
| `ExecutorChannel` | Giao việc cho executor | Cần thiết kế worker, hàng công việc và xử lý từ chối |
| `PublishSubscribeChannel` | Phân phát đến các subscriber | Phù hợp nhu cầu nhiều bên nhận cùng thông báo |

`DirectChannel` dùng cơ chế phân phát đến một subscriber cho mỗi lần xử lý thông thường. `ExecutorChannel` dùng executor cho việc phân phát. Hai loại này không cung cấp cùng mô hình transaction xuyên qua phía gửi và phía nhận. [API DirectChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html), [API ExecutorChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/ExecutorChannel.html).

`QueueChannel` có ngữ nghĩa point-to-point; message được lấy khỏi hàng đợi bởi một consumer. `PublishSubscribeChannel` phân phát message đến các handler đã đăng ký. [Tài liệu Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Ví dụ, “chuẩn bị một đơn hàng” thường là công việc cần một luồng chịu trách nhiệm. “Đơn hàng đã được chuẩn bị” có thể là sự kiện để nhiều bên quan sát. Cần quyết định rõ ý nghĩa này trước khi nối thêm consumer.

Đăng ký hai consumer vào một `DirectChannel` để một bên ghi đơn và một bên gửi email sẽ không tạo ra quy trình chắc chắn chạy cả hai bước. Nếu muốn tuần tự, hãy ghép hai endpoint theo thứ tự. Nếu muốn nhiều bên nhận cùng thông báo, hãy thiết kế một điểm phát sự kiện phù hợp.

## 6. Ví dụ hoàn chỉnh: producer chỉ biết điểm gửi

Ví dụ sử dụng Java record và Java DSL với `IntegrationFlow.from(...)`, phù hợp API Spring Integration 6 trở lên. Dự án cần dependency `org.springframework.integration:spring-integration-core`; phần kiểm thử phía sau cần JUnit Jupiter. Hãy dùng các phiên bản đồng bộ với BOM hoặc cấu hình dependency của dự án.

Mỗi khối mã có tên lớp public được đặt trong một file Java cùng tên, thuộc package `example.channels`.

Luồng minh họa:

~~~text
OrderPublisher
    -> orders.prepare (DirectChannel)
    -> transformer gọi OrderPreparationService
    -> orders.prepared (QueueChannel, capacity = 10)
    -> Demo hoặc kiểm thử lấy kết quả
~~~

Queue kết quả là điểm quan sát của ví dụ. Nó chưa phải một cơ chế phát sự kiện bền vững cho hệ thống thật.

### 6.1. Định nghĩa dữ liệu tại ranh giới

File `OrderContracts.java`:

~~~java
package example.channels;

import java.math.BigDecimal;

public final class OrderContracts {

    private OrderContracts() {
    }

    public record PrepareOrder(
            String orderId,
            String customerCode,
            BigDecimal total) {
    }

    public record PreparedOrder(
            String orderId,
            String normalizedCustomerCode,
            BigDecimal total) {
    }
}
~~~

Tên `PrepareOrder` diễn đạt yêu cầu; `PreparedOrder` diễn đạt kết quả chuẩn bị. Hai kiểu không mang theo tham chiếu đến consumer hay hạ tầng xử lý.

### 6.2. Giữ nghiệp vụ trong POJO

File `OrderPreparationService.java`:

~~~java
package example.channels;

import java.util.Locale;
import java.util.Objects;

import example.channels.OrderContracts.PrepareOrder;
import example.channels.OrderContracts.PreparedOrder;

public final class OrderPreparationService {

    public PreparedOrder prepare(PrepareOrder command) {
        Objects.requireNonNull(command, "command");

        if (command.orderId() == null
                || command.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        if (command.customerCode() == null
                || command.customerCode().isBlank()) {
            throw new IllegalArgumentException("customerCode is required");
        }

        if (command.total() == null
                || command.total().signum() <= 0) {
            throw new IllegalArgumentException("total must be positive");
        }

        return new PreparedOrder(
                command.orderId(),
                command.customerCode().trim().toUpperCase(Locale.ROOT),
                command.total());
    }
}
~~~

POJO này chỉ biết dữ liệu yêu cầu và dữ liệu kết quả. Có thể gọi và kiểm thử nó như một đối tượng Java bình thường.

Quy tắc chuẩn hóa mã trong ví dụ là giả định nghiệp vụ. Không nên tự động áp dụng quy tắc đổi hoa cho mọi loại mã trong dự án.

### 6.3. Producer gửi message mà không giữ consumer

File `OrderPublisher.java`:

~~~java
package example.channels;

import java.util.Objects;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import example.channels.OrderContracts.PrepareOrder;

public final class OrderPublisher {

    private final MessageChannel output;

    public OrderPublisher(MessageChannel output) {
        this.output = Objects.requireNonNull(output, "output");
    }

    public void publish(PrepareOrder command, String requestId) {
        Objects.requireNonNull(command, "command");
        Objects.requireNonNull(requestId, "requestId");

        if (requestId.isBlank()) {
            throw new IllegalArgumentException("requestId is required");
        }

        Message<PrepareOrder> message = MessageBuilder
                .withPayload(command)
                .setHeader("requestId", requestId)
                .setHeader("schemaVersion", 1)
                .build();

        boolean sent = output.send(message, 250);

        if (!sent) {
            throw new IllegalStateException(
                    "Could not send order preparation request");
        }
    }
}
~~~

`OrderPublisher` không import hoặc giữ `OrderPreparationService`. Nó biết cách tạo message theo hợp đồng và biết xử lý trường hợp channel trả về `false`.

`send(...)` còn có thể ném exception. Vì vậy, nhánh `if (!sent)` không thay thế việc thiết kế xử lý lỗi phía gọi. Giá trị timeout dùng đơn vị millisecond. [Javadoc MessageChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html).

Trong ví dụ, `250` không phải thời hạn hoàn tất toàn bộ nghiệp vụ. Với `DirectChannel`, handler vẫn chạy trong lời gọi gửi; send timeout không tự ngắt handler sau 250 ms.

### 6.4. Cấu hình đảm nhiệm việc ghép các component

File `OrderFlowConfig.java`:

~~~java
package example.channels;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

import example.channels.OrderContracts.PrepareOrder;

@Configuration
@EnableIntegration
public class OrderFlowConfig {

    @Bean(name = "orders.prepare")
    public MessageChannel orderPreparationRequests() {
        return new DirectChannel();
    }

    @Bean(name = "orders.prepared")
    public PollableChannel preparedOrders() {
        return new QueueChannel(10);
    }

    @Bean
    public OrderPreparationService preparationService() {
        return new OrderPreparationService();
    }

    @Bean
    public OrderPublisher orderPublisher(
            @Qualifier("orders.prepare") MessageChannel requests) {
        return new OrderPublisher(requests);
    }

    @Bean
    public IntegrationFlow prepareOrderFlow(
            @Qualifier("orders.prepare") MessageChannel requests,
            @Qualifier("orders.prepared") PollableChannel results,
            OrderPreparationService preparation) {

        return IntegrationFlow.from(requests)
                .transform(PrepareOrder.class, preparation::prepare)
                .channel(results)
                .get();
    }
}
~~~

Ở đây, `@Qualifier` xác định đúng channel khi application context có nhiều bean cùng kiểu. Channel có tên được khai báo rõ vì nó là ranh giới mà thành phần khác sử dụng.

Cấu hình Spring biết cả điểm gửi lẫn component xử lý; điều đó là cần thiết để ghép luồng. Việc tách component được đánh giá ở producer và consumer, không đòi hỏi phần cấu hình phải “không biết” các thành phần mà nó nối.

### 6.5. Gửi một yêu cầu và đọc kết quả

File `Demo.java`:

~~~java
package example.channels;

import java.math.BigDecimal;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;

import example.channels.OrderContracts.PrepareOrder;

public final class Demo {

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(OrderFlowConfig.class)) {

            OrderPublisher publisher =
                    context.getBean(OrderPublisher.class);

            PollableChannel results =
                    context.getBean("orders.prepared", PollableChannel.class);

            publisher.publish(
                    new PrepareOrder(
                            "ORD-101",
                            "  customer-a  ",
                            new BigDecimal("125000")),
                    "REQ-101");

            Message<?> result = results.receive(1_000);

            if (result == null) {
                throw new IllegalStateException("No prepared order received");
            }

            System.out.println(result.getPayload());
            System.out.println(result.getHeaders().get("requestId"));
        }
    }
}
~~~

Kết quả mong đợi chứa `orderId=ORD-101`, `normalizedCustomerCode=CUSTOMER-A`, số tiền `125000` và header `requestId=REQ-101`.

Transformer thông thường chuyển kết quả payload thành message đầu ra và giữ các header ứng dụng theo cơ chế xử lý message của framework. Nếu sau này tự tạo mới message trong một component, cần kiểm tra lại các header phải được truyền tiếp.

### 6.6. Điểm tách nằm ở đâu?

Trong ví dụ này:

- Producer phụ thuộc `MessageChannel` và `PrepareOrder`.
- POJO xử lý phụ thuộc `PrepareOrder` và `PreparedOrder`.
- Cấu hình integration biết channel nào nối với transformer.
- Thành phần đọc kết quả biết `orders.prepared` và hợp đồng kết quả.

Bạn có thể đổi cách chuẩn bị dữ liệu trong POJO mà không sửa producer. Bạn cũng có thể thay producer bằng một inbound adapter miễn adapter tạo ra message đáp ứng hợp đồng.

Producer và POJO vẫn cùng sử dụng hợp đồng dữ liệu. Khi đổi ý nghĩa `total` hoặc đổi kiểu payload, cần đánh giá cả hai phía.

## 7. Thay bằng QueueChannel: thay đổi hành vi của ranh giới

Giả sử việc chuẩn bị đơn hàng trở nên chậm. Bạn muốn tiếp nhận một số yêu cầu rồi xử lý sau.

Chỉ thay bean `orders.prepare` thành `QueueChannel` sẽ làm phía nhận phải lấy message theo mô hình polling. Nếu giữ endpoint mà không có poller cục bộ hoặc poller mặc định phù hợp, cấu hình không đáp ứng cách tiêu thụ channel mới.

Trong `OrderFlowConfig`, thay bean đầu vào bằng:

~~~java
@Bean(name = "orders.prepare")
public PollableChannel orderPreparationRequests() {
    return new QueueChannel(100);
}
~~~

Sau đó thay phương thức `prepareOrderFlow` bằng biến thể sau; bổ sung import `java.time.Duration` và `org.springframework.integration.dsl.Pollers`:

~~~java
@Bean
public IntegrationFlow prepareOrderFlow(
        @Qualifier("orders.prepare") PollableChannel requests,
        @Qualifier("orders.prepared") PollableChannel results,
        OrderPreparationService preparation) {

    return IntegrationFlow.from(requests)
            .bridge(endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofMillis(100))
                            .maxMessagesPerPoll(10)))
            .transform(PrepareOrder.class, preparation::prepare)
            .channel(results)
            .get();
}
~~~

Đây là phiên bản thay thế cho luồng cũ. Không đăng ký đồng thời hai phương thức cùng tên hoặc giữ cả hai consumer nếu bạn chỉ muốn một luồng chuẩn bị đơn hàng.

Bridge là endpoint nhận từ queue bằng poller rồi chuyển tiếp đến bước biến đổi. Cấu hình `maxMessagesPerPoll(10)` giới hạn số message nhận trong một lượt poll; nó không tạo mười worker chạy đồng thời. Java DSL cung cấp `Pollers` để cấu hình các polling endpoint. [Tài liệu Pollers](https://docs.spring.io/spring-integration/reference/dsl/java-pollers.html).

Producer vẫn được inject qua kiểu `MessageChannel`, nên không cần đổi `OrderPublisher`. Tuy nhiên, các đặc tính vận hành đã thay đổi:

| Khía cạnh | Bản dùng DirectChannel | Bản dùng QueueChannel và poller |
| --- | --- | --- |
| Lúc producer có thể trả về | Sau khi chuỗi xử lý trực tiếp trả về hoặc lỗi | Sau khi message được đưa vào queue |
| Lúc nghiệp vụ chạy | Trong thread gửi | Khi poller lấy message |
| Thông tin từ `send() == true` | Gửi thành công qua đường xử lý trực tiếp | Đã được queue tiếp nhận |
| Consumer chậm | Thời gian gửi kéo dài | Message có thể tích lại |
| Consumer thất bại | Lỗi có thể truyền về phía gửi | Cần quan sát lỗi của tác vụ polling |
| Hoàn tất nghiệp vụ | Suy luận theo luồng đồng bộ cụ thể | Cần kết quả, trạng thái hoặc thông báo riêng |

Hàng đợi có giới hạn có thể buộc phía gửi chờ khi đầy. `QueueChannel` mặc định lưu trong bộ nhớ; muốn tồn tại qua sự cố cần cấu hình lưu trữ phù hợp. Spring khuyến nghị đặt dung lượng rõ ràng để tránh queue tăng ngoài kiểm soát. [Tài liệu cấu hình QueueChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

Trong ví dụ, cả queue đầu vào lẫn queue kết quả đều có giới hạn. Nếu không ai lấy kết quả, queue kết quả có thể đầy và chặn bước gửi đầu ra. Vì vậy, thêm bộ đệm phải đi cùng thiết kế consumer cho mọi đầu ra.

## 8. Tách thread cần xét lại transaction và context

`DirectChannel` cho phép phía gửi và handler chạy trong cùng thread. Nếu đã có transaction hợp lệ bao quanh lời gọi, các thao tác có tham gia cùng transaction có thể chịu ảnh hưởng từ kết quả handler. Channel không tự mở transaction hoặc tự làm mọi tài nguyên cùng rollback. [Tài liệu DirectChannel](https://docs.spring.io/spring-integration/reference/6.3/channel/implementations.html).

Với `ExecutorChannel`, executor thường thực thi handler ở thread khác. Không nên dựa vào việc transaction gắn với thread gọi tự truyền sang worker. Chính sách executor còn có thể làm phía gửi bị chặn hoặc chạy công việc ngay trên thread gửi trong một số tình huống. [Tài liệu ExecutorChannel](https://docs.spring.io/spring-integration/reference/7.0/channel/implementations.html).

Ví dụ, xét quy trình:

~~~text
1. Ghi trạng thái đơn hàng trong database.
2. Gửi yêu cầu thanh toán qua một ranh giới bất đồng bộ.
3. Worker thực hiện yêu cầu thanh toán.
~~~

Nếu bước 1 commit nhưng ứng dụng dừng trước khi thông điệp được lưu an toàn, bước 3 có thể không xảy ra. Nếu bước 3 gọi dịch vụ bên ngoài thành công rồi worker dừng trước khi cập nhật trạng thái, lần xử lý lại có thể tạo tác dụng lặp.

Từ yêu cầu nghiệp vụ cụ thể, nhóm phát triển phải quyết định cách lưu message, theo dõi trạng thái, khử trùng lặp hoặc dùng outbox. Đổi channel không tự giải quyết các tình huống đó.

Các dữ liệu như thông tin truy vết hoặc tenant cũng cần được truyền một cách có chủ đích khi qua thread khác. Không nên giả định mọi giá trị trong `ThreadLocal` của producer sẽ có mặt ở consumer.

## 9. Lỗi thuộc hợp đồng của điểm tách

### 9.1. Với đường xử lý đồng bộ

Ở bản dùng `DirectChannel`, nếu `OrderPreparationService` phát hiện tổng tiền không hợp lệ, exception có thể truyền về từ lời gọi `publish(...)`, thường qua exception messaging bao ngoài.

Do đó, phía gọi có thể nhận lỗi ngay trong lần gửi. Tuy nhiên, các tác dụng đã xảy ra trước điểm lỗi có được hoàn tác hay không còn phụ thuộc transaction và loại tài nguyên.

### 9.2. Với đường xử lý bất đồng bộ

Ở bản queue, producer có thể đã gửi thành công trước khi POJO chạy. Exception tại thời điểm poller xử lý không thể tự quay lại stack Java của lần gọi producer đã kết thúc.

Spring Integration có cơ chế phát `ErrorMessage` cho các tác vụ do framework quản lý. Error handler sử dụng `errorChannel` trong header khi có, hoặc channel lỗi toàn cục theo cấu hình. Lỗi từ poller cũng có đường xử lý riêng của tác vụ scheduling. [Tài liệu Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Đối với ranh giới bất đồng bộ, hãy xác định:

- Nơi ghi nhận yêu cầu chưa xử lý thành công.
- Định danh để liên hệ lỗi với yêu cầu ban đầu.
- Lỗi nào có thể thử lại và giới hạn thử lại.
- Nơi chuyển yêu cầu không thể xử lý sau các lần thử.
- Cách bên gọi biết trạng thái cuối cùng nếu nghiệp vụ cần thông tin đó.

Một log lỗi có thể giúp chẩn đoán nhưng không tự tạo quy trình phục hồi. Tương tự, tên `errorChannel` không bảo đảm việc lưu lỗi bền vững hoặc tự động gửi lại.

Nếu ứng dụng tự lấy message bằng `receive(...)` rồi tự gọi POJO ngoài endpoint của framework, ứng dụng phải chủ động xử lý exception của đoạn mã đó.

## 10. Gateway có thể tiếp tục che API messaging khỏi bên gọi

Trong ví dụ chính, `OrderPublisher` trực tiếp dùng `MessageChannel` và `MessageBuilder`. Bạn có thể đưa ranh giới này sau một interface gateway để code nghiệp vụ chỉ gọi một phương thức Java.

Ví dụ interface thay thế cho phía tiếp nhận:

~~~java
package example.channels;

import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

import example.channels.OrderContracts.PrepareOrder;

@MessagingGateway(defaultRequestChannel = "orders.prepare")
public interface OrderGateway {

    void submit(
            PrepareOrder command,
            @Header("requestId") String requestId,
            @Header("schemaVersion") int schemaVersion);
}
~~~

Để framework đăng ký interface có annotation này, bật `@IntegrationComponentScan` trong cấu hình phù hợp, ví dụ:

~~~java
@IntegrationComponentScan(basePackageClasses = OrderGateway.class)
~~~

Annotation trên thuộc package `org.springframework.integration.annotation`; thêm nó vào lớp cấu hình có `@EnableIntegration` của ví dụ.

Code nghiệp vụ inject `OrderGateway` rồi gọi `submit(command, requestId, 1)`. Gateway proxy tạo message và gửi đến channel đã cấu hình. Gateway là cách framework che API messaging sau interface của ứng dụng. [Tài liệu Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html).

Kiểu trả về `void` mô tả việc không chờ một giá trị phản hồi qua hợp đồng phương thức. Với đường `DirectChannel`, lời gọi vẫn thực thi handler đồng bộ.

Nếu đổi gateway sang trả về `PreparedOrder`, phải thiết kế đường request-reply tương ứng. Queue `orders.prepared` trong ví dụ đang là đầu ra được đọc riêng; không nên chỉ sửa kiểu trả về rồi giả định gateway tự lấy kết quả từ queue đó.

## 11. Kiểm thử điểm tách mà không buộc mọi component chạy cùng nhau

Kiểm thử hữu ích ở ranh giới channel cần chứng minh producer tạo đúng message và cấu hình nối đúng quá trình xử lý.

Các ví dụ sau dùng JUnit Jupiter. Chúng là mã minh họa cho dự án có dependency phù hợp.

### 11.1. Kiểm thử producer bằng channel thay thế

Không cần khởi tạo consumer để biết producer có tuân thủ hợp đồng hay không.

~~~java
package example.channels;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import example.channels.OrderContracts.PrepareOrder;

import static org.junit.jupiter.api.Assertions.*;

class OrderPublisherTest {

    @Test
    void publishesTheAgreedPayloadAndHeaders() {
        QueueChannel capture = new QueueChannel(1);
        OrderPublisher publisher = new OrderPublisher(capture);

        PrepareOrder command = new PrepareOrder(
                "ORD-201",
                "customer-b",
                new BigDecimal("50000"));

        publisher.publish(command, "REQ-201");

        Message<?> message = capture.receive(0);

        assertNotNull(message);
        assertEquals(command, message.getPayload());
        assertEquals("REQ-201", message.getHeaders().get("requestId"));
        assertEquals(1, message.getHeaders().get("schemaVersion"));
        assertNull(capture.receive(0));
    }

    @Test
    void reportsWhenTheBoundaryCannotAcceptAnotherMessage() {
        QueueChannel capture = new QueueChannel(1);
        OrderPublisher publisher = new OrderPublisher(capture);

        PrepareOrder command = new PrepareOrder(
                "ORD-202",
                "customer-c",
                new BigDecimal("60000"));

        publisher.publish(command, "REQ-202");

        assertThrows(
                IllegalStateException.class,
                () -> publisher.publish(command, "REQ-203"));
    }
}
~~~

Kiểm thử thứ nhất dùng một queue làm nơi thu message. Nó chứng minh producer không cần lớp xử lý thật để thực hiện trách nhiệm của mình.

Kiểm thử thứ hai làm đầy queue một cách xác định để kiểm tra nhánh gửi không thành công. Nó không chứng minh hành vi khi consumer ném exception; đó là tình huống khác.

### 11.2. Kiểm thử cấu hình nối luồng

~~~java
package example.channels;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;

import example.channels.OrderContracts.PrepareOrder;
import example.channels.OrderContracts.PreparedOrder;

import static org.junit.jupiter.api.Assertions.*;

class OrderFlowTest {

    @Test
    void connectsThePublisherToPreparationAndResult() {
        try (var context =
                new AnnotationConfigApplicationContext(OrderFlowConfig.class)) {

            OrderPublisher publisher =
                    context.getBean(OrderPublisher.class);

            PollableChannel results =
                    context.getBean("orders.prepared", PollableChannel.class);

            publisher.publish(
                    new PrepareOrder(
                            "ORD-301",
                            "  customer-d  ",
                            new BigDecimal("99000")),
                    "REQ-301");

            Message<?> message = results.receive(1_000);

            assertNotNull(message);

            PreparedOrder result =
                    assertInstanceOf(PreparedOrder.class, message.getPayload());

            assertEquals("ORD-301", result.orderId());
            assertEquals("CUSTOMER-D", result.normalizedCustomerCode());
            assertEquals(new BigDecimal("99000"), result.total());
            assertEquals("REQ-301", message.getHeaders().get("requestId"));
            assertEquals(1, message.getHeaders().get("schemaVersion"));
        }
    }
}
~~~

Kiểm thử lấy kết quả với thời hạn rõ ràng. Nó kiểm tra tên bean, kết nối endpoint, phép biến đổi và metadata đi qua ranh giới.

Nếu đổi sang biến thể queue, kiểm thử này vẫn có thể chờ kết quả trong thời hạn, nhưng cần bổ sung trường hợp xử lý lỗi bất đồng bộ theo cơ chế lỗi đã chọn.

### 11.3. Những kết luận kiểm thử chưa cung cấp

Các kiểm thử trên không chứng minh:

- Message tồn tại sau khi ứng dụng khởi động lại.
- Thứ tự hoàn tất khi nhiều worker chạy đồng thời.
- Consumer không tạo tác dụng lặp sau retry.
- Throughput hoặc độ trễ đạt yêu cầu vận hành.
- Mọi header đều tương thích khi truyền qua broker.

Chỉ bổ sung các phép kiểm tra đó khi ranh giới thực tế có yêu cầu tương ứng. Việc thay consumer bằng test double đủ để kiểm tra một hợp đồng producer đơn giản.

## 12. Tổ chức ranh giới để luồng vẫn dễ bảo trì

### 12.1. Đặt tên theo ý nghĩa nghiệp vụ

Các tên như `orders.prepare`, `orders.prepared`, `orders.rejected` thể hiện mục đích tốt hơn `channel1` hoặc `toServiceB`.

Nếu producer phải đổi tên channel mỗi khi consumer đổi tên lớp, tên channel đang phản ánh chi tiết triển khai quá sát.

Tên rõ nghĩa cũng giúp người vận hành hiểu metric và log. Tuy nhiên, một tên chứa từ “prepared” chưa chứng minh đơn hàng đã được ghi bền vững; ý nghĩa đó phải nằm trong hợp đồng.

### 12.2. Công khai những channel cần được tái sử dụng

Không cần đặt tên và công khai mọi kết nối nội bộ do DSL tạo. Hãy xác định ranh giới nào thực sự được module khác, gateway, adapter hoặc kiểm thử sử dụng.

Một module có thể công khai một channel đầu vào và một hợp đồng kết quả, trong khi giữ chi tiết transformer và endpoint bên trong cấu hình của nó.

### 12.3. Giữ phần nối luồng ngoài POJO nghiệp vụ

Nếu `OrderPreparationService` lại inject `FraudChannel`, tự chọn tên channel theo lớp consumer rồi chờ kết quả bằng cơ chế riêng, POJO bắt đầu gánh cả điều phối integration.

Khi cần tách nhánh hoặc ghép kết quả, cân nhắc diễn đạt chúng bằng router, gateway nội bộ hoặc aggregator trong cấu hình integration. Quyết định cụ thể phải theo yêu cầu của luồng.

### 12.4. Quan sát đúng điều mình muốn biết

Tại ranh giới nhận yêu cầu, số lần gửi thành công phản ánh việc giao message theo ngữ nghĩa của channel. Để đo hoàn tất nghiệp vụ, cần quan sát một điểm có ý nghĩa hoàn tất tương ứng.

Với queue, có thể cần theo dõi số message chờ, thời gian chờ, tốc độ tiêu thụ và số lỗi. Với executor, cần quan sát worker và công việc bị từ chối. Các chỉ số này giúp phân biệt lỗi xử lý với việc ranh giới bị quá tải.

## 13. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu cần điều chỉnh |
| --- | --- |
| Có channel thì mọi bước đều bất đồng bộ | Phải xét implementation và endpoint thực tế |
| Producer không biết consumer nên không còn phụ thuộc | Hai phía vẫn chia sẻ hợp đồng dữ liệu và hành vi |
| `send() == true` nghĩa là đơn hàng đã hoàn tất | Phải xác định thành công tại ranh giới nào |
| Timeout gửi là timeout của nghiệp vụ | Timeout gửi không tự giới hạn thời gian mọi handler |
| Đổi `DirectChannel` thành queue là xong | Cần poller, dung lượng, đường lỗi và cách theo dõi hoàn tất |
| Nhiều subscriber vào channel nào cũng nhận đủ message | Phải phân biệt phân phát công việc và phát thông báo |
| Có hàng đợi là có lưu trữ bền vững | Cần cơ chế persistence được cấu hình rõ |
| Queue luôn giữ thứ tự hoàn tất nghiệp vụ | Thứ tự lấy message khác với thứ tự hoàn tất khi xử lý song song |
| Thêm retry bảo đảm không mất hoặc lặp tác dụng | Cần đánh giá điểm lỗi, lưu trữ và idempotency |
| Mọi exception đều tự đi vào `errorChannel` | Phải xét đường đồng bộ, tác vụ framework và cấu hình lỗi |

Khi một thay đổi tưởng như chỉ là “thay channel” làm transaction, lỗi hoặc độ trễ khác đi, hãy cập nhật hợp đồng và kiểm thử cho chính thay đổi đó.

## 14. Bài thực hành củng cố

Thực hiện lần lượt trên một dự án học tập có Spring Integration:

1. Tạo các lớp của ví dụ và kiểm thử producer bằng queue thu message.
2. Chạy luồng dùng `DirectChannel`, xác nhận payload và `requestId` tại đầu ra.
3. Ghi lại thread hiện tại trong producer và POJO để quan sát cách thực thi.
4. Thay đầu vào bằng queue có giới hạn và thêm poller như biến thể đã trình bày.
5. Quan sát sự khác nhau giữa thời điểm producer trả về và thời điểm có kết quả.
6. Gửi yêu cầu với `total <= 0`; so sánh cách quan sát lỗi giữa hai biến thể.
7. Dừng việc lấy kết quả, gửi nhiều yêu cầu và phân tích tác động của queue đầu ra đầy.
8. Viết lại hợp đồng channel bằng các câu rõ nghĩa về tiếp nhận, hoàn tất và lỗi.

Các câu hỏi cần tự trả lời sau thực hành:

- Nếu thay `OrderPreparationService` bằng implementation khác nhưng giữ nguyên hợp đồng, producer cần sửa gì?
- Nếu chuyển consumer sang một dịch vụ khác, ngoài tên channel còn thiếu những phần nào?
- Nếu thêm một bên gửi email, bạn muốn thực thi tuần tự hay phát một sự kiện cho nhiều bên?
- Nếu producer đã trả về nhưng consumer thất bại, ai chịu trách nhiệm biết và phục hồi yêu cầu?
- Bạn đang dùng dữ liệu nào để chứng minh một đơn hàng đã hoàn tất xử lý?

Khả năng trả lời rõ những câu hỏi này cho thấy bạn đã xác định được ranh giới giao tiếp của các component, cùng trách nhiệm dữ liệu và vận hành tại ranh giới đó.
