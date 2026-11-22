# Message và Java object

Bài học thuộc chương **Message** của module **SPRING_INTEGRATION_CORE**. Trong phạm vi thiết kế luồng bằng Message, MessageChannel, endpoint, gateway và Java DSL, bài này làm rõ quan hệ giữa object nghiệp vụ và thông điệp. Đây là nền tảng để quyết định transformer thay đổi dữ liệu nào, router hoặc filter đọc thông tin ở đâu, aggregator nhận diện nhóm bằng gì và kiểm thử phải quan sát phần nào của thông điệp.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Phân biệt một Java object dùng làm dữ liệu nghiệp vụ với `Message<T>` bao bọc dữ liệu đó.
- Tạo và đọc message bằng đúng các lớp của Spring Messaging.
- Giải thích vì sao payload hoặc giá trị header vẫn có thể thay đổi dù dùng message bất biến.
- Chọn chữ ký phương thức nhận payload, header hoặc toàn bộ message.
- Theo dõi việc thay payload và truyền header qua một flow Java DSL.
- Phân biệt truyền tham chiếu trong bộ nhớ với chuyển đổi định dạng khi đi qua ranh giới hệ thống.

Bạn cần biết class, interface, generic, collection và bean trong Spring. Ví dụ dùng cú pháp Java 17; khi chọn phiên bản Spring cho dự án thực tế, cần đáp ứng yêu cầu JDK của phiên bản đó. Phần flow cần `spring-integration-core` và các dependency Spring tương ứng; phần kiểm thử dùng JUnit Jupiter. Các đoạn minh họa nhỏ là độc lập, còn ví dụ `MessageObjectDemo` là một lớp hoàn chỉnh.

## 2. Từ object nghiệp vụ đến thông điệp

Giả sử hệ thống tiếp nhận yêu cầu duyệt đơn hàng:

~~~java
import java.math.BigDecimal;

public record OrderRequest(String orderId, BigDecimal amount) {
}
~~~

`OrderRequest` mô tả dữ liệu nghiệp vụ. Nó chưa nói yêu cầu đến từ kênh bán hàng nào hay phản hồi phải được chuyển đến đâu.

`Message<T>` bổ sung một lớp bao gồm payload và headers. Interface nằm trong package `org.springframework.messaging`; `T` biểu diễn kiểu payload. Hai phương thức cốt lõi là `getPayload()` và `getHeaders()`. Xem [API Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html).

~~~java
import org.springframework.messaging.Message;

// Minh họa cách đọc; không phải tự định nghĩa lại interface của Spring.
OrderRequest order = message.getPayload();
String source = message.getHeaders().get("source", String.class);
~~~

Đoạn trên giả định `message` có kiểu `Message<OrderRequest>`. Có thể hình dung quan hệ như sau:

~~~mermaid
flowchart LR
    P["OrderRequest: dữ liệu nghiệp vụ"] --> M["Message&lt;OrderRequest&gt;"]
    H["Headers: source, operationId, replyChannel"] --> M
    M --> C["MessageChannel"]
    C --> E["Endpoint gọi phương thức xử lý"]
~~~

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Payload | Đang xử lý nội dung gì? | Đơn ORD-1001 trị giá 125000 |
| Headers | Luồng cần ngữ cảnh hoặc chỉ dẫn gì? | Nguồn WEB, mã thao tác, địa chỉ phản hồi |
| Message | Đơn vị dữ liệu được chuyển trong flow là gì? | Payload đi cùng headers |
| MessageChannel | Message được gửi đến đâu trong flow? | `orderInput` |
| Endpoint | Bước nào tiếp nhận và xử lý message? | Chuẩn hóa yêu cầu, gọi dịch vụ duyệt đơn |

Một Java object không cần kế thừa lớp nghiệp vụ đặc biệt chỉ để trở thành payload. Ngược lại, việc đặt object vào message cũng không tự biến nó thành một sự kiện nghiệp vụ: ý nghĩa command, event hay kết quả xử lý vẫn phải được thể hiện trong hợp đồng của ứng dụng.

Ví dụ, `OrderRequest` là yêu cầu thực hiện thao tác; `OrderAccepted` là kết quả đã chấp nhận đơn. Tên lớp và dữ liệu của hai kiểu này giúp người đọc flow hiểu rõ chuyển trạng thái nghiệp vụ.

## 3. Tạo message từ một object

`GenericMessage<T>` là một triển khai thông dụng của `Message<T>`. Có thể truyền payload trực tiếp hoặc truyền kèm một `Map` header; payload không được là `null`. Constructor nhận `Map` sao chép các cặp khóa–giá trị của map, không nhân bản sâu các object bên trong. Xem [API GenericMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/GenericMessage.html).

~~~java
import java.math.BigDecimal;
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

OrderRequest order =
        new OrderRequest("ORD-1001", new BigDecimal("125000"));

Message<OrderRequest> message = new GenericMessage<>(
        order,
        Map.of("source", "WEB", "operationId", "accept:ORD-1001")
);

OrderRequest payload = message.getPayload();

System.out.println(payload.orderId());                // ORD-1001
System.out.println(payload == order);                 // true
System.out.println(message.getHeaders().get("source")); // WEB
~~~

Trong ví dụ, `payload == order` đúng vì message giữ tham chiếu đến object đã truyền vào. Không có bước biến object thành JSON rồi dựng lại object.

Có thể dùng `MessageBuilder` khi cần mô tả headers rõ ràng hơn:

~~~java
import org.springframework.messaging.support.MessageBuilder;

Message<OrderRequest> message = MessageBuilder
        .withPayload(order)
        .setHeader("source", "WEB")
        .setHeader("operationId", "accept:ORD-1001")
        .build();
~~~

Bài này dùng nhất quán `org.springframework.messaging.support.MessageBuilder`. Spring Integration cũng có builder trong package hỗ trợ riêng; khi đọc ví dụ hoặc dùng IDE, hãy kiểm tra import thay vì chỉ nhìn tên ngắn của lớp.

Không cần tự tạo một lớp kiểu `OrderMessage extends GenericMessage<OrderRequest>` chỉ để biểu diễn từng loại đơn hàng. Giữ ý nghĩa nghiệp vụ trong kiểu payload thường giúp hợp đồng dễ đọc hơn và tránh nhân thêm lớp bao bọc không mang hành vi mới.

## 4. Đặt thông tin vào payload hay header?

Một cách phân chia hữu ích là xét người cần sử dụng thông tin.

- Payload chứa dữ liệu mà dịch vụ nghiệp vụ cần để hiểu và thực hiện thao tác.
- Header chứa ngữ cảnh mà cơ chế tích hợp dùng để vận chuyển, theo dõi, định tuyến hoặc trả lời.

Đây là quyết định thiết kế hợp đồng, không phải quy tắc cứng rằng một trường luôn phải nằm ở một vị trí.

| Thông tin | Vị trí phù hợp trong ví dụ | Lý do |
| --- | --- | --- |
| `orderId`, `amount` | Payload | Quyết định đơn nào được duyệt và giá trị bao nhiêu |
| `source` | Header | Phân biệt nguồn tiếp nhận để theo dõi hoặc chọn nhánh |
| `operationId` | Header theo hợp đồng ứng dụng | Nhận diện yêu cầu xử lý qua nhiều bước |
| `replyChannel` | Header của framework | Xác định đường phản hồi trong cơ chế request–reply |
| `tenantId` dùng để tính chính sách | Cần hợp đồng rõ ràng | Phải có mặt ở nơi kiểm tra quyền và thực thi chính sách cần nó |

Nếu quyết định `tenantId` chỉ nằm trong header, chữ ký dịch vụ hoặc lớp điều phối phải truyền nó tường minh đến phần nghiệp vụ cần dùng. Tránh để logic nghiệp vụ âm thầm phụ thuộc vào một header mà hợp đồng không nhắc tới.

`MessageHeaders` cung cấp hằng cho các header hệ thống như `ID`, `TIMESTAMP`, `REPLY_CHANNEL` và `ERROR_CHANNEL`. Getter có tham số kiểu hỗ trợ đọc theo kiểu kỳ vọng; nó không phải yêu cầu tự chuyển chuỗi thành số hay JSON thành DTO. Xem [API MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html).

~~~java
import java.util.UUID;

UUID messageId = message.getHeaders().getId();
Long createdAt = message.getHeaders().getTimestamp();
String source = message.getHeaders().get("source", String.class);
~~~

Header tùy biến không có thì getter có thể trả về `null`; ứng dụng cần xác định header đó bắt buộc hay có giá trị mặc định.

`operationId` trong bài là header do ứng dụng tự đặt, không phải chức năng chống xử lý trùng tự động của Spring. Muốn chống trùng, cần dùng giá trị đó cùng một cơ chế lưu và kiểm tra trạng thái phù hợp.

## 5. Bất biến của message và khả năng thay đổi của object

### 5.1. Vỏ bất biến không đồng nghĩa toàn bộ đồ thị object bất biến

Với `GenericMessage` và cách xây message thông thường, không có setter để gán lại payload. Map headers công khai cũng không cho `put`, `remove` hay `clear`. Tuy vậy, payload và object làm giá trị header có thể vẫn thay đổi được. Tài liệu [Message của Spring Integration](https://docs.spring.io/spring-integration/reference/message.html) nêu rõ ranh giới này.

Ví dụ sau không thay payload bằng object khác; nó sửa chính object mà message đang tham chiếu:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

List<String> orderIds = new ArrayList<>();
orderIds.add("ORD-1001");

Message<List<String>> message = new GenericMessage<>(orderIds);

orderIds.add("ORD-1002");

System.out.println(message.getPayload());
// [ORD-1001, ORD-1002]
~~~

Người đọc message nhận được hai mã đơn. Nếu mục đích là lưu ảnh chụp dữ liệu tại thời điểm gửi, đoạn code trên chưa đáp ứng hợp đồng đó.

### 5.2. Sao chép map header cũng chưa sao chép object trong header

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

List<String> stages = new ArrayList<>();
Map<String, Object> rawHeaders = new HashMap<>();
rawHeaders.put("source", "WEB");
rawHeaders.put("stages", stages);

Message<String> message = new GenericMessage<>("ORD-1001", rawHeaders);

rawHeaders.put("source", "BATCH");
stages.add("RECEIVED");

System.out.println(message.getHeaders().get("source")); // WEB
System.out.println(message.getHeaders().get("stages")); // [RECEIVED]
~~~

Đổi entry `source` trong map gốc không đổi map của message. Nhưng `stages` ở hai nơi cùng trỏ đến một danh sách, nên nội dung danh sách vẫn thay đổi.

Đưa một object có setter vào payload hoặc header tạo ra cùng kiểu vấn đề. Cần xem cả object lồng nhau, không chỉ modifier `final` của biến ngoài cùng.

### 5.3. Record và collection cần được thiết kế cùng nhau

Java record là kiểu mang dữ liệu bất biến ở mức nông: trường thành phần là `final` nhưng object được tham chiếu chưa chắc bất biến. Có thể dùng constructor để kiểm tra dữ liệu và sao chép phòng vệ. Xem [API Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).

~~~java
import java.util.List;

public record OrderBatch(List<String> orderIds) {

    public OrderBatch {
        orderIds = List.copyOf(orderIds);
    }
}
~~~

Với `List<String>`, cách này phù hợp để giữ danh sách không thay đổi qua API thông thường. `List.copyOf` tạo danh sách không cho sửa cấu trúc và không phản ánh thay đổi cấu trúc về sau của collection nguồn; nó không nhân bản từng phần tử. Xem [API List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

Nếu thay `String` bằng `MutableOrder`, mỗi phần tử vẫn cần một chính sách riêng: chuyển thành DTO bất biến, sao chép dữ liệu cần thiết hoặc bảo đảm quyền sở hữu độc quyền.

### 5.4. Hậu quả khi nhiều nhánh dùng chung payload

Giả sử một nhánh gửi email và nhánh khác ghi lịch sử. Nếu cả hai sửa cùng `Order`, lịch sử có thể phản ánh trạng thái do nhánh email vừa thay đổi, thay vì dữ liệu ban đầu.

Thiết kế nên chọn một trong những hướng rõ ràng:

1. Dùng payload và giá trị header bất biến.
2. Tạo object đầu ra mới khi thay đổi dữ liệu.
3. Tạo bản sao đủ sâu tại ranh giới cần độc lập dữ liệu.
4. Chỉ dùng object mutable khi hợp đồng sở hữu và thứ tự xử lý đã được kiểm soát.

Khóa một danh sách để tránh race condition không tự giải quyết yêu cầu “mỗi nhánh nhìn thấy dữ liệu ban đầu”. Đồng bộ hóa và tính độc lập của dữ liệu là hai yêu cầu khác nhau.

## 6. Tạo thông điệp tiếp theo mà không sửa thông điệp đầu vào

Giả sử bước tiếp nhận bổ sung header `validated`:

~~~java
Message<OrderRequest> validated = MessageBuilder
        .fromMessage(message)
        .setHeader("validated", true)
        .build();
~~~

Builder lấy payload và headers làm dữ liệu khởi đầu rồi xây message theo thay đổi yêu cầu. Khi muốn đổi kiểu payload, bắt đầu bằng `withPayload` và lựa chọn headers cần giữ:

~~~java
public record OrderAccepted(String orderId, String status) {
}

OrderAccepted accepted =
        new OrderAccepted(message.getPayload().orderId(), "ACCEPTED");

Message<OrderAccepted> reply = MessageBuilder
        .withPayload(accepted)
        .copyHeaders(message.getHeaders())
        .setHeader("processedBy", "order-service")
        .build();
~~~

`copyHeaders` sao chép các cặp khóa–giá trị và có thể ghi đè header thông thường đã đặt trong builder; `copyHeadersIfAbsent` giữ giá trị đã có. `id` và `timestamp` không bị ghi đè bởi thao tác sao chép. Xem [API MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html).

Hệ quả thiết kế trong ví dụ:

- Object `OrderRequest` không bị sửa.
- Payload đầu ra là một `OrderAccepted` mới.
- Header `operationId` có thể đi tiếp để nối các bước của cùng yêu cầu.
- ID của message do framework quản lý; không dùng nó thay cho khóa nghiệp vụ ổn định qua việc dựng lại message.

Không suy ra hai timestamp phải khác nhau: hai message có thể được tạo trong cùng một mili giây. Cũng không dùng việc gọi `build()` mà không thay đổi gì làm bằng chứng rằng object đã được sao chép sâu.

Đoạn dùng `copyHeaders` minh họa một flow nội bộ có chủ đích giữ ngữ cảnh. Khi xây hợp đồng ra hệ thống ngoài, hãy chọn các header được phép truyền thay vì mặc nhiên chuyển tất cả.

## 7. Endpoint nối message với phương thức Java như thế nào?

Dịch vụ nghiệp vụ có thể chỉ nhận dữ liệu mà nó cần:

~~~java
public OrderAccepted accept(OrderRequest request) {
    return new OrderAccepted(request.orderId(), "ACCEPTED");
}
~~~

Khi endpoint service activator gọi phương thức này, Spring Integration lấy payload từ message để làm đối số. Nếu phương thức trả về object thông thường, endpoint tạo phản hồi dạng message. Với nhu cầu đọc ngữ cảnh, có thể dùng `@Header` hoặc nhận `Message<?>`. Xem [Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html).

| Chữ ký | Phù hợp khi | Mức phụ thuộc vào messaging |
| --- | --- | --- |
| `accept(OrderRequest request)` | Chỉ cần dữ liệu nghiệp vụ | Thấp |
| `accept(OrderRequest request, @Header("source") String source)` | Cần một header được chỉ rõ | Phụ thuộc annotation messaging |
| `accept(Message<OrderRequest> message)` | Cần toàn bộ envelope | Phụ thuộc trực tiếp `Message` |

Ví dụ nhận một header:

~~~java
import org.springframework.messaging.handler.annotation.Header;

public OrderAccepted accept(
        OrderRequest request,
        @Header("source") String source) {

    return new OrderAccepted(
            request.orderId(),
            "ACCEPTED_FROM_" + source
    );
}
~~~

Đây là các lựa chọn chữ ký thay thế. Không cần khai báo tất cả thành các overload cùng tên rồi để framework đoán phương thức nghiệp vụ mong muốn.

Một gateway cho phép phía gọi làm việc với interface nhận và trả Java object; proxy xử lý việc vào flow và nhận phản hồi. Trong request–reply thông thường, gateway có thể đặt kênh phản hồi tạm vào header `replyChannel`. Xem [Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html).

Vì vậy, cả đầu vào lẫn dịch vụ nghiệp vụ đều có thể dùng DTO, còn message là mô hình trao đổi giữa các thành phần tích hợp. Nếu flow kết thúc bằng một output channel được chỉ rõ, phải thiết kế đường phản hồi tương ứng; không mặc định mọi DTO trả về đều tự đến được gateway.

## 8. Ví dụ đầy đủ: Java object đi qua một flow Java DSL

Ví dụ nhận `OrderRequest`, loại khoảng trắng ở mã đơn, gọi một dịch vụ Java và đưa `OrderAccepted` vào kênh kết quả.

`IntegrationFlow` phải được đăng ký làm bean; Java DSL mô tả channel và endpoint trong cấu hình Spring. Xem [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html).

~~~mermaid
flowchart LR
    A["Message&lt;OrderRequest&gt;"] --> B["orderInput: DirectChannel"]
    B --> C["Transformer: chuẩn hóa orderId"]
    C --> D["Service Activator: OrderService.accept"]
    D --> E["orderOutput: QueueChannel"]
    E --> F["Message&lt;OrderAccepted&gt;"]
~~~

Đặt lớp dưới đây trong một tệp tên `MessageObjectDemo.java` của dự án học tập đã có dependency. Các record được lồng trong lớp để ví dụ không cần thêm tệp Java khác.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class MessageObjectDemo {

    public record OrderRequest(String orderId, BigDecimal amount) {
        public OrderRequest {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(amount, "amount");
        }
    }

    public record OrderAccepted(String orderId, String status) {
    }

    public static class OrderService {

        public OrderAccepted accept(OrderRequest request) {
            if (request.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId must not be blank");
            }
            if (request.amount().signum() <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            return new OrderAccepted(request.orderId(), "ACCEPTED");
        }
    }

    @Bean
    public MessageChannel orderInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel orderOutput() {
        return new QueueChannel(10);
    }

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public IntegrationFlow orderFlow(OrderService orderService) {
        return IntegrationFlow
                .from("orderInput")
                .transform(
                        OrderRequest.class,
                        request -> new OrderRequest(
                                request.orderId().strip(),
                                request.amount()
                        )
                )
                .handle(orderService, "accept")
                .channel("orderOutput")
                .get();
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(MessageObjectDemo.class)) {

            MessageChannel input =
                    context.getBean("orderInput", MessageChannel.class);
            QueueChannel output =
                    context.getBean("orderOutput", QueueChannel.class);

            OrderRequest original =
                    new OrderRequest(" ORD-1001 ", new BigDecimal("125000"));

            Message<OrderRequest> request = MessageBuilder
                    .withPayload(original)
                    .setHeader("source", "WEB")
                    .setHeader("operationId", "accept:ORD-1001")
                    .build();

            if (!input.send(request)) {
                throw new IllegalStateException("Request was not accepted");
            }

            Message<?> reply = output.receive(1_000);

            if (reply == null) {
                throw new IllegalStateException("No result received");
            }
            if (!(reply.getPayload() instanceof OrderAccepted accepted)) {
                throw new IllegalStateException("Unexpected payload type");
            }

            System.out.println(accepted);
            System.out.println(reply.getHeaders().get("source"));
            System.out.println(reply.getHeaders().get("operationId"));
            System.out.println("Original unchanged: "
                    + original.orderId().equals(" ORD-1001 "));
        }
    }
}
~~~

Kết quả dự kiến của bốn lệnh in do ví dụ thực hiện, bỏ qua log khởi động Spring:

~~~text
OrderAccepted[orderId=ORD-1001, status=ACCEPTED]
WEB
accept:ORD-1001
Original unchanged: true
~~~

### 8.1. Điểm cần quan sát

1. `original` vẫn giữ mã có khoảng trắng. Transformer tạo `OrderRequest` khác thay vì sửa object đầu vào.
2. Dịch vụ chỉ nhận `OrderRequest` và trả `OrderAccepted`; nó không đọc channel hay tạo message.
3. Channel kết quả chứa message có payload là `OrderAccepted`.
4. Hai header tùy biến tiếp tục có mặt theo cấu hình truyền header mặc định của các endpoint trong ví dụ.

Transformer có thể nhận/trả payload hoặc toàn bộ message. Khi trả payload, framework giữ ngữ cảnh header theo quy tắc của endpoint. Khi transformer trả một `Message` hoàn chỉnh, code transformer chịu trách nhiệm xây đầy đủ message đầu ra. Xem [Transformer](https://docs.spring.io/spring-integration/reference/transformer.html).

Đó là lý do cần phân biệt “phương thức trả DTO mới” với “phương thức tự xây envelope mới”. Nếu tự xây message trong transformer mà quên `operationId` hoặc `replyChannel` cần thiết, flow có thể mất ngữ cảnh dù payload vẫn đúng.

### 8.2. Vì sao ví dụ chưa cần poller?

`DirectChannel` gọi subscriber theo luồng xử lý đồng bộ thông thường. `QueueChannel` giữ kết quả để `main` chủ động gọi `receive`. Ví dụ không cấu hình endpoint tự tiêu thụ queue, nên không cần thêm poller cho bước đọc này. Đặc điểm channel được mô tả tại [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Đưa một message vào queue không tự tạo consumer hoặc tác vụ nghiệp vụ chạy nền. Muốn một endpoint xử lý message lấy từ queue, cần cấu hình cơ chế tiêu thụ tương ứng.

Trong ví dụ này, `send` chỉ trở về bình thường sau khi các bước đồng bộ đã đưa kết quả vào queue. Với flow có executor, poller hoặc broker, việc gửi thành công không tự chứng minh toàn bộ nghiệp vụ về sau đã hoàn tất.

## 9. Kiểu Java, chuyển đổi dữ liệu và ranh giới hệ thống

### 9.1. Generic giúp đọc hợp đồng nhưng không thay thế hợp đồng runtime

`Message<OrderRequest>` giúp trình biên dịch biết kiểu mà code đang thao tác. Tuy nhiên, `MessageChannel` là abstraction nhận message, không phải một `MessageChannel<OrderRequest>` đảm bảo mọi producer đều gửi đúng DTO.

Một producer khác vẫn có thể gửi `Message<String>` vào cùng một channel nếu ứng dụng không áp dụng ràng buộc thêm. Vì thế, cần thống nhất hợp đồng payload của từng channel và có kiểm thử cho đầu vào sai.

Khi đang giữ `Message<?>`, có thể kiểm tra kiểu tường minh:

~~~java
Object payload = incoming.getPayload();

if (!(payload instanceof OrderRequest request)) {
    throw new IllegalArgumentException("Expected OrderRequest");
}

// Từ đây dùng request theo kiểu OrderRequest.
~~~

Không ép kiểu message để “chuyển” dữ liệu:

~~~java
// Ép kiểu như vậy không phân tích JSON hay tạo OrderRequest.
// Message<OrderRequest> typed = (Message<OrderRequest>) rawMessage;
~~~

Với collection, kiểm tra payload là `List` cũng chưa chứng minh từng phần tử là `OrderRequest`. Hợp đồng dữ liệu phải mô tả cả kiểu phần tử khi điều đó quan trọng.

### 9.2. Chuyển đổi kiểu phải có cơ chế cụ thể

Phương thức nhận `OrderRequest` không có nghĩa mọi chuỗi JSON đưa vào channel đều tự trở thành `OrderRequest`. Nếu đầu vào là JSON, cần adapter, converter hoặc transformer phù hợp đã được cấu hình.

Một pipeline có chủ đích có thể là:

~~~text
HTTP body hoặc byte[]
    -> giải mã và ánh xạ dữ liệu
    -> OrderRequest
    -> kiểm tra dữ liệu
    -> flow xử lý nghiệp vụ
~~~

Ranh giới này nên kiểm tra ít nhất: trường bắt buộc, kiểu dữ liệu, giá trị hợp lệ và cách phản hồi khi dữ liệu sai. Đừng dùng việc ép kiểu thành công làm tiêu chí rằng nghiệp vụ đã hợp lệ.

### 9.3. Object trong JVM khác dữ liệu truyền ra ngoài

| Bối cảnh | Điều cần hiểu về payload |
| --- | --- |
| Tạo `GenericMessage` trong bộ nhớ | Object đã truyền vào được giữ bằng tham chiếu |
| Chuyển qua các bước nội bộ của ví dụ | Không có bước tuần tự hóa chỉ vì đi qua channel |
| Chủ động gọi transformer JSON | Payload có thể đổi thành chuỗi hoặc cấu trúc JSON |
| Gửi qua adapter ra broker hoặc HTTP | Dạng dữ liệu phụ thuộc adapter và converter |
| Lưu message bằng cơ chế lưu trữ có mã hóa | Cần đáp ứng hợp đồng lưu và khôi phục dữ liệu |

Một payload không nhất thiết phải `implements Serializable` chỉ để được bọc trong `GenericMessage`. Khi cơ chế lưu hoặc truyền sử dụng Java serialization, các object liên quan phải đáp ứng yêu cầu của chính cơ chế đó. Khi dùng JSON hoặc định dạng khác, cần đáp ứng hợp đồng của bộ chuyển đổi tương ứng.

Header nội bộ có thể chứa tham chiếu channel hoặc object phục vụ runtime. Những giá trị đó không đương nhiên có ý nghĩa ở JVM khác. Hãy xác định schema và chính sách ánh xạ header tại ranh giới, thay vì coi toàn bộ envelope nội bộ là hợp đồng liên hệ thống.

## 10. Lỗi thường gặp khi đồng nhất Message với Java object

| Cách hiểu hoặc cách làm | Hậu quả có thể thấy | Cách xử lý |
| --- | --- | --- |
| Sửa DTO sau khi gửi rồi coi message là bản chụp cũ | Consumer đọc giá trị vừa bị đổi | Tạo snapshot hoặc dùng DTO bất biến |
| Đặt `ArrayList` vào header và sửa ở nhiều nhánh | Nhánh khác thấy dữ liệu ngoài dự kiến | Dùng giá trị bất biến hoặc bản sao phù hợp |
| `getHeaders().put(...)` | `UnsupportedOperationException` với headers thông thường | Xây message đầu ra bằng builder |
| Dùng message ID làm khóa ổn định của đơn hàng | Mất liên hệ khi dựng message mới | Dùng `orderId` hoặc khóa thao tác theo hợp đồng |
| Nghĩ chữ ký `OrderRequest` tự giải mã mọi JSON | Không khớp kiểu hoặc chuyển đổi thất bại | Cấu hình bước ánh xạ và kiểm tra dữ liệu |
| Trả `null` từ transformer để bỏ message | Lỗi chuyển đổi thay vì kết quả lọc rõ ràng | Dùng filter cho quyết định giữ/bỏ |
| Tự xây message trong transformer nhưng quên header | Mất theo dõi hoặc đường phản hồi | Xác định rõ headers đầu ra phải có |

Đặc biệt, lỗi đồng bộ trong flow minh họa thường đi ngược về phía gọi `send` dưới dạng exception của cơ chế messaging, có thể bao bọc lỗi gốc. Chỉ đặt header `errorChannel` không tự chuyển mọi exception đồng bộ sang một flow khác. Cơ chế báo lỗi của tác vụ bất đồng bộ và poller cần được xét theo cấu hình chạy thực tế. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Khi điều tra, hãy quan sát kiểu payload thực tế, header nghiệp vụ nối các bước, endpoint lỗi và nguyên nhân gốc. Không cần ghi toàn bộ payload ra log để biết một DTO đã bị gửi sai kiểu; trong ví dụ đơn hàng, ghi `orderId`, `operationId` và tên kiểu thường đã đủ để bắt đầu lần theo flow.

## 11. Kiểm thử các đặc tính quan trọng

Các kiểm thử dưới đây là nội dung thực hành để đặt trong dự án học tập. Chúng kiểm tra dữ liệu chia sẻ và hợp đồng của flow; việc có mã kiểm thử trong tài liệu không đồng nghĩa chúng đã được thực thi.

Lớp kiểm thử dùng cùng package với `MessageObjectDemo` ở phần 8 và cần dependency `org.junit.jupiter:junit-jupiter` ở phạm vi test.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class MessageObjectDemoTest {

    @Test
    void wrappingDoesNotCreatePayloadSnapshot() {
        List<String> ids = new ArrayList<>(List.of("ORD-1001"));
        Message<List<String>> message = new GenericMessage<>(ids);

        ids.add("ORD-1002");

        assertSame(ids, message.getPayload());
        assertEquals(
                List.of("ORD-1001", "ORD-1002"),
                message.getPayload()
        );
    }

    @Test
    void readOnlyHeadersCanStillContainMutableValues() {
        List<String> stages = new ArrayList<>();

        Message<String> message = MessageBuilder
                .withPayload("ORD-1001")
                .setHeader("stages", stages)
                .build();

        assertThrows(
                UnsupportedOperationException.class,
                () -> message.getHeaders().put("source", "WEB")
        );

        stages.add("RECEIVED");

        assertSame(stages, message.getHeaders().get("stages"));
        assertEquals(
                List.of("RECEIVED"),
                message.getHeaders().get("stages")
        );
    }

    @Test
    void flowChangesPayloadAndPreservesBusinessContext() {
        try (var context =
                     new AnnotationConfigApplicationContext(MessageObjectDemo.class)) {

            MessageChannel input =
                    context.getBean("orderInput", MessageChannel.class);
            QueueChannel output =
                    context.getBean("orderOutput", QueueChannel.class);

            var original = new MessageObjectDemo.OrderRequest(
                    " ORD-1001 ",
                    new BigDecimal("125000")
            );

            Message<?> request = MessageBuilder
                    .withPayload(original)
                    .setHeader("source", "WEB")
                    .setHeader("operationId", "accept:ORD-1001")
                    .build();

            assertTrue(input.send(request));

            Message<?> reply = output.receive(1_000);
            assertNotNull(reply);

            var accepted = assertInstanceOf(
                    MessageObjectDemo.OrderAccepted.class,
                    reply.getPayload()
            );

            assertEquals("ORD-1001", accepted.orderId());
            assertEquals("ACCEPTED", accepted.status());
            assertEquals("WEB", reply.getHeaders().get("source"));
            assertEquals(
                    "accept:ORD-1001",
                    reply.getHeaders().get("operationId")
            );
            assertEquals(" ORD-1001 ", original.orderId());
        }
    }
}
~~~

Kiểm thử thứ nhất cố ý chứng minh tình huống dễ gây hiểu nhầm: bọc một collection mutable không tạo snapshot. Kiểm thử thứ hai tách hai thuộc tính độc lập: map header không cho sửa và object làm giá trị header vẫn mutable. Kiểm thử thứ ba quan sát kết quả thật ở ranh giới flow, bao gồm kiểu payload, dữ liệu đã chuẩn hóa, header cần giữ và object đầu vào.

Với ứng dụng thực tế, bổ sung ca kiểm thử cho hợp đồng riêng: đầu vào sai kiểu, header bắt buộc bị thiếu, dữ liệu không hợp lệ hoặc converter không đọc được dữ liệu bên ngoài. Khi flow có nhiều nhánh hoặc xử lý bất đồng bộ, cần kiểm tra thêm tính độc lập của dữ liệu theo thiết kế.

## 12. Áp dụng khi phát triển các mẫu tích hợp

Sự phân biệt giữa object và message dẫn tới những quyết định cụ thể:

- **Transformer:** tạo biểu diễn payload phù hợp cho bước kế tiếp và xác định headers phải đi cùng.
- **Router:** chọn nhánh dựa trên payload hoặc header đã được ghi rõ trong hợp đồng.
- **Filter:** quyết định giữ hoặc loại message; tránh dùng giá trị `null` của transformer thay cho chính sách lọc.
- **Aggregator:** thống nhất khóa nhóm và dữ liệu đầu vào; tránh đổi object đã giao cho bước gom nhóm.
- **Gateway:** cho phía gọi dùng interface Java thuận tiện nhưng vẫn phải thiết kế đường trả kết quả.
- **Xử lý lỗi:** giữ đủ mã nghiệp vụ và ngữ cảnh để liên hệ lỗi với yêu cầu đã gửi.

Ví dụ, nếu sau này đơn hàng được chia thành nhiều yêu cầu giữ hàng, `orderId` có thể là dữ liệu nghiệp vụ chung, còn khóa tương quan của các message con phải được thiết kế để gom đúng nhóm. Message ID của từng thông điệp riêng lẻ không tự biểu diễn quan hệ đó.

Khi viết một bước mới trong flow, hãy xác định bốn điều: kiểu payload đầu vào, kiểu payload đầu ra, headers cần giữ và quyền được thay đổi object. Trả lời rõ bốn điều này giúp việc nối endpoint và kiểm thử trở nên cụ thể, thay vì chỉ dựa vào việc các phương thức đều nhận một `Object`.
