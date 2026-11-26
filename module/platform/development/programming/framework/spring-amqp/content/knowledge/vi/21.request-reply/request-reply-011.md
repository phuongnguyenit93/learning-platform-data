# `convertSendAndReceiveAsType()` cho kiểu phản hồi phức tạp

Trong kiến trúc bất đồng bộ với **RabbitMQ và Spring AMQP**, đa số message có thể xử lý theo kiểu gửi rồi tiếp tục công việc. Tuy nhiên, đôi khi một thành phần cần gửi yêu cầu và **chờ phản hồi** từ dịch vụ khác. Spring AMQP hỗ trợ mô hình *request–reply* này qua `RabbitTemplate` và `@RabbitListener`.

Với phản hồi đơn giản như `String` hoặc một DTO đơn, `convertSendAndReceive()` có thể đủ. Nhưng với phản hồi có **generic lồng nhau**, chẳng hạn `Reply<PageResult<OrderView>>`, `List<OrderView>` hoặc `Map<String, List<OrderView>>`, cần cung cấp thông tin kiểu đầy đủ cho bộ chuyển đổi message. Phương thức **`convertSendAndReceiveAsType()` kết hợp `ParameterizedTypeReference<T>`** giải quyết bài toán này.

Bài thuộc chương **Yêu cầu và phản hồi** của module **SPRING_AMQP**. Ngoài việc chuyển đổi kiểu, chúng ta sẽ theo dõi đường đi của request, cấu hình exchange–queue–binding, đọc đúng kết quả, xử lý timeout và xác định giới hạn tin cậy của RPC qua message broker.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt `convertSendAndReceive()` và `convertSendAndReceiveAsType()` khi phản hồi chứa generic.
- Khai báo `ParameterizedTypeReference<Reply<PageResult<OrderView>>>` đúng cách.
- Cấu hình JSON `MessageConverter` hỗ trợ chuyển đổi có thông tin kiểu cho `RabbitTemplate` và `@RabbitListener`.
- Gửi request đến exchange/routing key và nhận phản hồi đã chuyển thành đúng kiểu Java, không ép kiểu tùy tiện.
- Phân biệt phản hồi nghiệp vụ thất bại, lỗi convert message và tình huống không nhận được reply trước timeout.
- Thiết kế DTO, thời gian chờ, định tuyến và giám sát request–reply an toàn.

## 2. Request–reply hoạt động như thế nào?

Ứng dụng gọi một hàm Java nhưng phía xử lý thực tế là một consumer RabbitMQ. Về bản chất, đây vẫn là **hai message riêng biệt**: request gửi đến queue xử lý và reply gửi trở lại nơi người gọi đang chờ.

~~~mermaid
sequenceDiagram
    participant C as Client / RabbitTemplate
    participant X as Request exchange
    participant Q as orders.search.queue
    participant S as @RabbitListener
    participant R as Reply destination

    C->>X: publish SearchOrdersRequest
    X->>Q: route bằng orders.search
    Q->>S: giao request
    Note over C,S: Request có reply-to và correlation information
    S->>R: publish Reply<PageResult<OrderView>>
    R-->>C: tương ứng với request đang chờ
    C->>C: JSON -> kiểu generic đã khai báo
~~~

Thông thường `RabbitTemplate` quản lý thông tin **reply-to** và **correlation** cho lời gọi đồng bộ. Khi broker hỗ trợ, Spring AMQP có thể dùng cơ chế *direct reply-to* của RabbitMQ, nên ví dụ cơ bản không cần tạo một reply queue cố định. `@RabbitListener` trả về giá trị sẽ được listener adapter chuyển thành reply và gửi theo thông tin đi kèm request.

**Cần phân biệt:** request–reply là một **lời gọi đồng bộ từ góc nhìn thread gọi**. Dù bên dưới sử dụng broker, thread đang gọi `convertSendAndReceiveAsType()` vẫn chờ đến khi nhận reply hoặc hết thời gian chờ. Nếu không cần kết quả tức thì, publish sự kiện và xử lý bất đồng bộ thường phù hợp hơn.

### 2.1. Đường đi của một lời gọi

1. `RabbitTemplate` dùng converter để biến object request thành message RabbitMQ.
2. Request được publish tới **exchange** với **routing key**; binding đưa message vào queue của consumer.
3. Listener nhận request và xử lý nghiệp vụ.
4. Giá trị trả về từ listener được chuyển thành reply message; framework dùng thông tin reply-to/correlation để trả về client tương ứng.
5. `RabbitTemplate` nhận reply, dùng converter có hỗ trợ generic và `ParameterizedTypeReference<T>` để dựng đối tượng kiểu `T`.

Điểm mấu chốt của bài nằm ở **bước 5**: một message JSON không tự mang đầy đủ cấu trúc kiểu Java kiểu `Reply<PageResult<OrderView>>` theo cách an toàn, ổn định cho mọi trường hợp.

## 3. Vì sao `convertSendAndReceive()` chưa đủ với generic?

Giả sử JSON phản hồi có cấu trúc:

~~~json
{
  "success": true,
  "data": {
    "items": [
      {
        "orderId": "ORD-101",
        "total": 149000,
        "status": "PAID"
      }
    ],
    "page": 0,
    "size": 20,
    "totalElements": 1
  },
  "error": null
}
~~~

Ta muốn dữ liệu Java là:

~~~java
Reply<PageResult<OrderView>>
~~~

Nếu gọi:

~~~java
Object reply = rabbitTemplate.convertSendAndReceive(
        "orders.rpc.exchange",
        "orders.search",
        request);
~~~

kiểu trả về tĩnh chỉ là `Object`. Tùy converter, header kiểu trong message và cấu hình deserialization, giá trị có thể được tạo thành DTO, `Map`, hoặc object có các phần generic bị giải mã thành `LinkedHashMap`. Việc ép kiểu như dưới đây không bảo đảm phần tử ở trong `data.items` thật sự là `OrderView`:

~~~java
@SuppressWarnings("unchecked")
Reply<PageResult<OrderView>> typed =
        (Reply<PageResult<OrderView>>) reply; // Không chứng minh được kiểu lồng nhau
~~~

Lý do là **type erasure** của Java: ở runtime, `Reply<PageResult<OrderView>>` không thể biểu diễn đầy đủ chỉ bằng một `Class<Reply>`. Một tham chiếu dạng `Reply.class` thiếu thông tin của cả `PageResult<OrderView>`.

Spring cung cấp `ParameterizedTypeReference<T>` để lưu mô tả kiểu tổng quát, bao gồm các tham số kiểu lồng nhau:

~~~java
import org.springframework.core.ParameterizedTypeReference;

ParameterizedTypeReference<Reply<PageResult<OrderView>>> replyType =
        new ParameterizedTypeReference<>() {};
~~~

Cặp ngoặc nhọn `{}` tạo **anonymous subclass**, nhờ đó thông tin kiểu cụ thể được giữ lại trong khai báo lớp ẩn danh. Cùng một `replyType` có thể được tái sử dụng cho nhiều lời gọi RPC cùng hợp đồng dữ liệu.

> **Chú ý:** `ParameterizedTypeReference` giúp **converter phía nhận** biết kiểu đích. Nó không tự sửa JSON sai cấu trúc, không biến mọi converter thành JSON converter, không giải quyết việc mất message và không bảo đảm phía server trả về kiểu đã thỏa thuận.

## 4. API `convertSendAndReceiveAsType()`

Mẫu gọi phổ biến khi có exchange và routing key:

~~~java
T response = rabbitTemplate.convertSendAndReceiveAsType(
        exchange,
        routingKey,
        requestObject,
        parameterizedTypeReference);
~~~

Trong đó:

| Thành phần | Vai trò |
| --- | --- |
| `exchange` | Exchange nhận request, chẳng hạn `orders.rpc.exchange` |
| `routingKey` | Khóa định tuyến request, chẳng hạn `orders.search` |
| `requestObject` | DTO cần gửi; converter biến thành message |
| `parameterizedTypeReference` | Mô tả **toàn bộ** kiểu phản hồi mà client kỳ vọng |
| Giá trị trả về | `T` sau khi convert, hoặc `null` nếu không có reply trong thời gian chờ |

`RabbitTemplate` cũng cung cấp các overload phù hợp khi gửi qua routing key mặc định hoặc cần điều chỉnh message trước lúc publish. Khả năng chuyển đổi **theo kiểu `ParameterizedTypeReference`** phụ thuộc vào converter được cấu hình cho template; converter cần hỗ trợ kiểu dữ liệu thông minh, thường là một triển khai `SmartMessageConverter` như JSON converter của Spring AMQP. Nếu template vẫn dùng converter mặc định không hỗ trợ kiểu phản hồi phức tạp, lời gọi có thể thất bại khi chuyển đổi.

## 5. Ví dụ hoàn chỉnh: tìm đơn hàng và nhận `Reply<PageResult<OrderView>>`

Bài thực hành dùng Java 17+, Spring Boot 3.x và Spring AMQP 3.x với `Jackson2JsonMessageConverter`. Đặt các lớp trong cùng package (ví dụ `com.example.ordersrpc`). Với phiên bản Spring AMQP khác, kiểm tra lớp Jackson message converter và API tương ứng của phiên bản dự án; nguyên tắc `ParameterizedTypeReference` không thay đổi.

### 5.1. Xác định hợp đồng DTO

Thay vì trả về `Object` hoặc `Map<String, Object>`, hãy mô tả phản hồi nghiệp vụ rõ ràng. Ví dụ sau dùng `record` để tạo DTO ngắn gọn:

~~~java
package com.example.ordersrpc;

import java.math.BigDecimal;
import java.util.List;

public final class RpcDtos {

    private RpcDtos() {
    }

    public record SearchOrdersRequest(
            String customerId,
            int page,
            int size
    ) {}

    public record OrderView(
            String orderId,
            BigDecimal total,
            String status
    ) {}

    public record PageResult<T>(
            List<T> items,
            int page,
            int size,
            long totalElements
    ) {}

    public record RpcError(
            String code,
            String message
    ) {}

    public record Reply<T>(
            boolean success,
            T data,
            RpcError error
    ) {}
}
~~~

Kiểu đích ở phía client là:

~~~java
RpcDtos.Reply<RpcDtos.PageResult<RpcDtos.OrderView>>
~~~

Nhờ `PageResult<T>`, cùng mẫu phản hồi còn có thể dùng cho `ProductView`, `InvoiceView`, v.v. Nhưng với mỗi lời gọi, client phải khai báo đúng **kiểu cụ thể** mà nó mong nhận. Hợp đồng API nên quy định các trường bắt buộc, cách biểu diễn lỗi, tên trường JSON và chính sách tương thích khi DTO thay đổi.

### 5.2. Cấu hình exchange, queue, binding và JSON converter

~~~java
package com.example.ordersrpc;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class RpcMessagingConfig {

    public static final String EXCHANGE = "orders.rpc.exchange";
    public static final String REQUEST_QUEUE = "orders.search.queue";
    public static final String REQUEST_KEY = "orders.search";

    @Bean
    DirectExchange ordersRpcExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersSearchQueue() {
        return QueueBuilder.durable(REQUEST_QUEUE).build();
    }

    @Bean
    Binding ordersSearchBinding(
            Queue ordersSearchQueue,
            DirectExchange ordersRpcExchange) {
        return BindingBuilder.bind(ordersSearchQueue)
                .to(ordersRpcExchange)
                .with(REQUEST_KEY);
    }

    @Bean
    MessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    RabbitTemplate rabbitTemplate(
            ConnectionFactory connectionFactory,
            MessageConverter jsonMessageConverter) {
        var template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(jsonMessageConverter);
        template.setReplyTimeout(5_000); // 5 giây, đơn vị millisecond
        return template;
    }

    @Bean
    SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            ConnectionFactory connectionFactory,
            MessageConverter jsonMessageConverter) {
        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(jsonMessageConverter);
        return factory;
    }
}
~~~

Để dùng `convertSendAndReceiveAsType()`, **reply converter của `RabbitTemplate` phải hiểu kiểu tổng quát** được truyền vào. `Jackson2JsonMessageConverter` xử lý JSON và hỗ trợ chuyển đổi có thông tin kiểu. Nếu một bên dùng JSON còn bên kia dùng Java serialization hoặc converter tùy biến không hỗ trợ cấu trúc này, phản hồi có thể lỗi convert hoặc có hình dạng dữ liệu không mong muốn.

Trong ví dụ, `setReplyTimeout(5_000)` giới hạn thời gian mà thread caller chờ. Timeout này **không** hủy tự động công việc mà listener phía server đã bắt đầu.

### 5.3. Listener nhận request và trả DTO generic

~~~java
package com.example.ordersrpc;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderSearchListener {

    @RabbitListener(queues = RpcMessagingConfig.REQUEST_QUEUE)
    public RpcDtos.Reply<RpcDtos.PageResult<RpcDtos.OrderView>> search(
            RpcDtos.SearchOrdersRequest request) {

        if (request.customerId() == null
                || request.customerId().isBlank()
                || request.page() < 0
                || request.size() < 1
                || request.size() > 100) {
            return new RpcDtos.Reply<>(
                    false,
                    null,
                    new RpcDtos.RpcError(
                            "INVALID_REQUEST",
                            "customerId, page hoặc size không hợp lệ"));
        }

        // Dữ liệu giả để minh họa; thực tế lấy từ service/repository.
        var order = new RpcDtos.OrderView(
                "ORD-101",
                new BigDecimal("149000"),
                "PAID");

        var page = new RpcDtos.PageResult<>(
                List.of(order),
                request.page(),
                request.size(),
                1L);

        return new RpcDtos.Reply<>(true, page, null);
    }
}
~~~

Trong mô hình `@RabbitListener` trả về object, listener adapter của Spring AMQP sẽ chuyển giá trị trả về thành reply message và gửi về địa chỉ reply do caller cung cấp. Không cần tự `basicPublish` cho từng lời gọi khi dùng cơ chế request–reply mặc định này.

Ở đây ta **chủ động trả lỗi nghiệp vụ bằng DTO `Reply`**. Nếu listener ném exception mà không có cơ chế xử lý thành phản hồi tương ứng, không nên mặc định client sẽ nhận được exception Java dưới dạng `Reply<RpcError>`. Tùy cách cấu hình listener và xử lý message lỗi, client có thể chỉ thấy timeout.

### 5.4. Client gọi với `ParameterizedTypeReference`

~~~java
package com.example.ordersrpc;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Service;

@Service
public class OrderSearchClient {

    private static final ParameterizedTypeReference<
            RpcDtos.Reply<RpcDtos.PageResult<RpcDtos.OrderView>>>
            RESPONSE_TYPE = new ParameterizedTypeReference<>() {};

    private final RabbitTemplate rabbitTemplate;

    public OrderSearchClient(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public RpcDtos.PageResult<RpcDtos.OrderView> searchOrders(
            String customerId, int page, int size) {

        var request = new RpcDtos.SearchOrdersRequest(
                customerId, page, size);

        RpcDtos.Reply<RpcDtos.PageResult<RpcDtos.OrderView>> reply =
                rabbitTemplate.convertSendAndReceiveAsType(
                        RpcMessagingConfig.EXCHANGE,
                        RpcMessagingConfig.REQUEST_KEY,
                        request,
                        RESPONSE_TYPE);

        if (reply == null) {
            throw new IllegalStateException(
                    "RPC timeout: không nhận được phản hồi tìm đơn hàng");
        }

        if (!reply.success()) {
            String code = reply.error() != null
                    ? reply.error().code() : "UNKNOWN_ERROR";
            throw new IllegalArgumentException(
                    "RPC business error: " + code);
        }

        if (reply.data() == null) {
            throw new IllegalStateException(
                    "RPC response thiếu trường data");
        }

        return reply.data();
    }
}
~~~

Giờ đây compiler biết `reply.data()` là `PageResult<OrderView>` và mỗi phần tử trong `reply.data().items()` được kỳ vọng là `OrderView` sau khi converter đọc JSON với toàn bộ kiểu đích:

~~~java
RpcDtos.PageResult<RpcDtos.OrderView> page =
        orderSearchClient.searchOrders("CUS-001", 0, 20);

for (RpcDtos.OrderView order : page.items()) {
    System.out.println(order.orderId());
    System.out.println(order.total());
}
~~~

Không cần `(OrderView) map.get(...)`, `@SuppressWarnings("unchecked")` hoặc parse JSON bằng tay.

## 6. Các kiểu phản hồi phức tạp khác

`ParameterizedTypeReference` hữu ích mỗi khi kiểu đích chứa parameterized type. Các mẫu thường gặp:

| Kiểu phản hồi | Ví dụ type reference |
| --- | --- |
| Danh sách DTO | `new ParameterizedTypeReference<List<OrderView>>() {}` |
| Kết quả phân trang | `new ParameterizedTypeReference<PageResult<OrderView>>() {}` |
| Wrapper nhiều tầng | `new ParameterizedTypeReference<Reply<PageResult<OrderView>>>() {}` |
| Map chứa danh sách | `new ParameterizedTypeReference<Map<String, List<OrderView>>>() {}` |
| Danh sách wrapper | `new ParameterizedTypeReference<List<Reply<OrderView>>>() {}` |

Ví dụ với map:

~~~java
ParameterizedTypeReference<
        java.util.Map<String, java.util.List<RpcDtos.OrderView>>> type =
        new ParameterizedTypeReference<>() {};

java.util.Map<String, java.util.List<RpcDtos.OrderView>> result =
        rabbitTemplate.convertSendAndReceiveAsType(
                "reports.rpc.exchange",
                "orders.by-status",
                new RpcDtos.SearchOrdersRequest("CUS-001", 0, 20),
                type);
~~~

Đoạn này chỉ minh họa cách khai báo type reference; muốn chạy thật, cần có exchange, binding và consumer trả về đúng hợp đồng `Map<String, List<OrderView>>` tương ứng.

**Tránh sai lầm khi viết helper generic:** đoạn mã `new ParameterizedTypeReference<List<T>>() {}` trong một phương thức có type parameter `T` chưa được ràng buộc ở runtime không tự biến `T` thành `OrderView`. Type reference tốt nhất được tạo tại nơi **kiểu cụ thể đã xác định**, hoặc được tạo từ một `Type` đầy đủ do caller truyền vào.

### 6.1. `Optional<T>`, interface và đa hình

Không phải mọi kiểu Java đều ánh xạ sang JSON theo cách rõ ràng:

- `Optional<T>` cần lựa chọn converter/Jackson module và hợp đồng JSON nhất quán; với RPC, giá trị thiếu thường dễ quản lý hơn bằng `data: null` cộng trạng thái nghiệp vụ rõ ràng.
- Interface, abstract class hoặc nhiều subtype có thể cần cấu hình Jackson polymorphism có kiểm soát hoặc chuyển về một DTO cụ thể.
- Không bật cơ chế nhận tên class tùy ý từ JSON/headers không đáng tin cậy chỉ để có kết quả đa hình; ưu tiên DTO và danh sách subtype được cho phép.
- `Page<T>` của Spring Data là interface có hành vi/metadata riêng; `PageResult<T>` là DTO wire format rõ ràng và dễ tương thích hơn.

## 7. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Kết quả là `Map`/`LinkedHashMap`, ép sang DTO lỗi | Dùng API không khai báo generic đầy đủ; converter/headers suy kiểu khác | Dùng `AsType` với `ParameterizedTypeReference`, rà soát JSON converter |
| Exception khi gọi `convertSendAndReceiveAsType` | Converter không hỗ trợ chuyển đổi theo parameterized type | Dùng `SmartMessageConverter` phù hợp, ví dụ JSON converter của Spring AMQP |
| `null` sau khi chờ | Không có reply trước `replyTimeout` | Kiểm tra route, listener, reply-to, thời gian xử lý, log broker |
| Nhận reply nhưng field lồng nhau bằng `null` | JSON thiếu field, không khớp DTO hoặc phiên bản hợp đồng | Kiểm tra JSON thực tế, schema và mapping của Jackson |
| Server báo lỗi nhưng client chỉ timeout | Listener ném exception mà không tạo reply nghiệp vụ | Quy định wrapper `Reply<T>` cho lỗi dự kiến; giám sát exception |
| Sai người nhận hoặc không thấy request | Exchange, routing key, binding, virtual host không khớp | Kiểm tra topology và đường routing thực tế |
| Dùng cùng DTO nhưng deserialize lỗi sau deploy | Thay đổi tên field, enum, kiểu số hoặc định dạng ngày | Version hóa contract, kiểm tra tương thích giữa client/server |

**Không đánh đồng các loại thất bại:**

1. **Lỗi nghiệp vụ có reply:** client nhận `Reply.success=false`, trong đó `error.code` được xác định rõ.
2. **Timeout:** `convertSendAndReceiveAsType()` trả `null` do không nhận được reply trong thời gian chờ; không khẳng định server chưa xử lý.
3. **Lỗi kết nối, publish hoặc chuyển đổi:** lời gọi có thể ném exception; phải giám sát nguyên nhân riêng, không tự quy mọi lỗi thành timeout.

Nếu không có reply, hãy theo vết **request ID → exchange → binding → queue → listener → reply-to/correlation → client**. Chỉ thấy request đã tới queue là chưa đủ để khẳng định phản hồi đã được gửi và ghép đúng.

## 8. Timeout, retry và tính đúng đắn của RPC

### 8.1. Timeout không hủy công việc phía server

Giả sử client chờ 5 giây, nhưng truy vấn phía server mất 8 giây:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server listener
    C->>S: requestId=REQ-42
    Note over S: Đang xử lý lâu
    Note over C: Hết 5 giây: timeout
    S-->>C: Reply đến muộn
    Note over C: Caller đã hết chờ
~~~

Một reply đến muộn có thể không còn consumer nào chờ lời gọi tương ứng. Vì thế, timeout phải phù hợp với thời gian xử lý thực tế và SLA. Ghi nhận `requestId`, `correlationId`, tổng thời gian xử lý và số lần timeout để điều tra.

### 8.2. Retry có thể tạo request trùng

Nếu timeout rồi gọi lại, request đầu tiên **có thể đã xử lý thành công**. Với tác vụ có side effect (đặt hàng, ghi tiền, trừ tồn kho), client cần gửi **idempotency key** và server phải bảo đảm một yêu cầu nghiệp vụ không bị áp dụng hai lần.

Ví dụ thay vì:

~~~java
record ChargeRequest(String accountId, long amount) {}
~~~

hãy cân nhắc:

~~~java
record ChargeRequest(
        String requestId,
        String accountId,
        long amount
) {}
~~~

Server lưu trạng thái xử lý theo `requestId` hoặc khóa nghiệp vụ tương đương trong cơ chế đáng tin cậy. Việc có một trường `requestId` **chưa đủ** nếu server không kiểm tra trùng lặp và bảo vệ thao tác ghi bằng cơ chế đồng bộ/giao dịch phù hợp.

### 8.3. Tin cậy khi publish không đồng nghĩa đã xử lý

- **Publisher confirm** giúp biết broker đã xác nhận publish; nó không có nghĩa listener đã hoàn tất nghiệp vụ.
- **Publisher return** khi mandatory routing được cấu hình giúp nhận biết message không route được; không thay thế reply từ server.
- **Consumer ack** liên quan việc xử lý request ở queue; nó khác với việc caller đã nhận reply.
- `replyTimeout` giới hạn thời gian caller đợi; không phải cơ chế retry bền vững hay bảo đảm phản hồi luôn đến.

Với thao tác quan trọng cần truy vết trạng thái, hãy cân nhắc mô hình command + event hoặc job bất đồng bộ với trạng thái có thể truy vấn, thay vì giữ nhiều thread chờ RPC dài.

## 9. Thực hành và kiểm thử

Có thể thực hành với một RabbitMQ instance, module Spring Boot dùng starter AMQP và mã ví dụ ở phần 5. Khởi động ứng dụng, đảm bảo đã khai báo exchange `orders.rpc.exchange`, queue `orders.search.queue` và binding `orders.search`.

### Kịch bản A — nhận phản hồi có kiểu lồng nhau

Gọi:

~~~java
var page = orderSearchClient.searchOrders("CUS-001", 0, 20);
System.out.println(page.items().get(0).orderId());
~~~

Kỳ vọng in `ORD-101` và `page.items().get(0)` là `OrderView`. Đặt breakpoint để kiểm chứng kiểu runtime của phần tử thay vì chỉ xem kiểu biến được compiler suy luận.

### Kịch bản B — lỗi nghiệp vụ vẫn có reply

Gọi request với `page=-1`. Listener tạo `Reply.success=false`, `error.code=INVALID_REQUEST`. Client nhận phản hồi hợp lệ về mặt truyền thông rồi chuyển thành lỗi nghiệp vụ theo chính sách ứng dụng.

### Kịch bản C — timeout

Tạm thời cho listener xử lý lâu hơn `replyTimeout` trong môi trường kiểm thử. Xác minh `RabbitTemplate` không có reply đúng hạn, client xử lý `null`, và log cho thấy server có thể tiếp tục xử lý. Khôi phục thời gian xử lý sau khi kiểm thử.

### Kịch bản D — thiếu binding hoặc sai routing key

Trong môi trường kiểm thử, gửi request tới routing key không có binding phù hợp và quan sát hiện tượng không nhận được reply. Phân biệt **request không route được** với **request đã tới listener nhưng listener không reply** bằng thống kê và log. Nếu cần phát hiện publish không route được chủ động, cấu hình thêm mandatory routing, publisher returns và xử lý kết quả thích hợp.

### Kịch bản E — khác phiên bản contract

Thay đổi thử kiểu của một trường phản hồi trong môi trường kiểm thử (ví dụ gửi chuỗi tại vị trí client mong số nguyên) và xem converter xử lý thế nào. Dùng kiểm thử tương thích JSON và version hóa hợp đồng trước khi deploy client/server độc lập.

### Checklist trước production

- [ ] Server và client thống nhất định dạng JSON, DTO, kiểu generic và phiên bản contract.
- [ ] `RabbitTemplate` dùng converter hỗ trợ `ParameterizedTypeReference`.
- [ ] Exchange, queue, binding, routing key và virtual host được kiểm chứng.
- [ ] Client có timeout, phân biệt lỗi nghiệp vụ với lỗi truyền thông/deserialize.
- [ ] Có request ID/correlation để theo dõi request–reply; không log dữ liệu nhạy cảm.
- [ ] Retry nếu cần được giới hạn; thao tác có side effect bảo đảm idempotency.
- [ ] Có metric về thời gian đáp ứng, timeout, lỗi chuyển đổi, lỗi định tuyến và số lượng request tồn đọng.

## 10. Những điểm cần ghi nhớ

`convertSendAndReceiveAsType()` là lựa chọn phù hợp khi client Spring AMQP **cần chờ một phản hồi có kiểu tổng quát nhiều tầng**. Kết hợp với `ParameterizedTypeReference<Reply<PageResult<OrderView>>>`, nó giúp JSON converter tái tạo đúng cấu trúc DTO và tránh ép kiểu không an toàn ở các collection lồng nhau.

Tuy nhiên, **kiểu dữ liệu đúng chỉ là một phần** của request–reply đáng tin cậy. Hệ thống còn cần JSON converter đồng nhất, exchange–queue–binding chính xác, hợp đồng phản hồi lỗi rõ ràng, timeout có chủ đích, giám sát correlation và idempotency nếu client có thể gửi lại yêu cầu. Trong module **SPRING_AMQP**, đó là cách kết hợp `RabbitTemplate`, `@RabbitListener` và RabbitMQ để xử lý request–reply có thể kiểm soát trong môi trường thực tế.
