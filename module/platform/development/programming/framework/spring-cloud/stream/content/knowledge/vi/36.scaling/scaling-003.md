# Áp dụng ChannelInterceptor và GlobalChannelInterceptor đúng binding

## Mục tiêu

Trong ứng dụng Spring Cloud Stream, nhiều luồng message có thể dùng chung một binder nhưng đòi hỏi các quy tắc khác nhau: bổ sung correlation ID cho event đơn hàng, kiểm tra header của message từ đối tác, đếm throughput của một luồng thanh toán hoặc ghi nhận thời gian chuyển message vào channel. Nếu đưa tất cả logic đó vào từng hàm `Supplier`, `Function` hay `Consumer`, code nghiệp vụ bị lặp và khó kiểm soát phạm vi áp dụng.

Spring Messaging cung cấp `ChannelInterceptor` để can thiệp vào thao tác gửi/nhận trên `MessageChannel`. Spring Integration cung cấp `@GlobalChannelInterceptor` để đăng ký interceptor cho **những channel có tên khớp pattern**. Spring Cloud Stream dùng message channels trong mô hình binder thông thường, bao gồm output binding được tạo bởi `StreamBridge`. Vì vậy, interceptor có thể giúp triển khai một số quy tắc dùng chung, nhưng cấu hình pattern sai có thể khiến quy tắc áp dụng lên quá nhiều binding hoặc hoàn toàn không chạy.

Bài học trong chương **Mở rộng** của module **SPRING_CLOUD_STREAM** hướng dẫn cách áp dụng interceptor đúng phạm vi binding khi xây dựng hệ thống xử lý sự kiện bằng `Supplier`, `Function`, `Consumer`, Kafka, RabbitMQ và Pulsar. Nội dung tập trung vào khác biệt giữa channel, binding và destination; cấu hình toàn cục có chọn lọc; tương tác với `StreamBridge`; thứ tự callback; kiểm thử với test binder và giới hạn khi dùng Kafka Streams DSL.

Sau bài học, bạn có thể:

- Phân biệt `MessageChannel`, binding name, broker destination và consumer group.
- Giải thích vòng đời `preSend`, `postSend`, `afterSendCompletion`.
- Đăng ký interceptor cho một channel cụ thể hoặc theo pattern.
- Dùng `@GlobalChannelInterceptor(patterns = "...")` để chọn đúng binding.
- Hiểu vì sao `StreamBridge` cần interceptor được đăng ký theo cơ chế global.
- Điều chỉnh `order` khi nhiều interceptor cùng áp dụng.
- Tránh nuốt message ngoài ý muốn và tránh thực hiện side effect kéo dài.
- Phân biệt interception ở channel với Kafka/Pulsar/RabbitMQ client hoặc Kafka Streams DSL.
- Kiểm thử cả trường hợp interceptor phải chạy và trường hợp phải được loại trừ.
- Quan sát thay đổi header, lỗi và mức overhead khi hệ thống mở rộng.

## 1. Channel, binding và destination là ba khái niệm khác nhau

Trong Spring Cloud Stream, binding nối phần logic của ứng dụng với một destination trên middleware. Với mô hình function, binding mặc định có tên theo quy tắc:

- `<functionName>-in-0` cho input.
- `<functionName>-out-0` cho output.
- Chỉ số `0`, `1`... cho function có nhiều input/output.

Ví dụ:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> validateOrders() {
    return event -> new OrderAccepted(event.orderId(), "ACCEPTED");
}
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrders
    stream:
      bindings:
        validateOrders-in-0:
          destination: orders.created
          group: order-validation
        validateOrders-out-0:
          destination: orders.accepted
~~~

Có bốn định danh cần ghi nhớ:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Function bean | `validateOrders` | Xử lý logic nghiệp vụ |
| Binding name | `validateOrders-in-0` | Kết nối logic với binder |
| Broker destination | `orders.created` | Kafka topic, RabbitMQ exchange/queue hoặc Pulsar topic |
| Consumer group | `order-validation` | Nhóm consumer/subscription theo cơ chế binder |

`@GlobalChannelInterceptor` khớp theo **tên Spring Integration message channel**, không phải theo tên topic, tên RabbitMQ queue, Kafka consumer group hay tên class Java. Trong mô hình message-channel binder, các channel liên quan binding thường được đặt tên theo binding name; ứng dụng phải xác minh tên thực tế khi dùng alias, function composition hoặc binding động.

Ví dụ `patterns = "orders.created"` không tự khớp với channel `validateOrders-in-0` chỉ vì destination của binding là `orders.created`.

### Luồng xử lý khái quát

~~~mermaid
flowchart LR
    T[(Topic / Queue)] --> B[Binder input adapter]
    B --> IC[Input MessageChannel]
    IC --> F[Function bean]
    F --> OC[Output MessageChannel]
    OC --> P[Binder output adapter]
    P --> D[(Destination)]
~~~

Interceptor gắn với `IC` hoặc `OC` hoạt động trên lượt gửi message qua channel tương ứng. Nó không đứng độc lập tại broker và không tự theo dõi mọi thao tác Kafka, RabbitMQ hoặc Pulsar bên ngoài channel này.

## 2. ChannelInterceptor thực hiện những việc gì?

`org.springframework.messaging.support.ChannelInterceptor` là interface của Spring Messaging. Nó cung cấp các callback quanh thao tác `MessageChannel.send(...)` và, với channel kiểu pollable, quanh `receive(...)`.

| Callback | Thời điểm | Điểm cần lưu ý |
|---|---|---|
| `preSend` | Trước khi message được gửi vào channel | Có thể tạo message mới hoặc trả `null` để chặn send |
| `postSend` | Sau lời gọi send | Nhận boolean `sent` của thao tác send |
| `afterSendCompletion` | Khi thao tác send kết thúc, kể cả exception | Dọn tài nguyên; chỉ áp dụng khi `preSend` trả message hợp lệ |
| `preReceive` | Trước lời gọi receive | Chỉ cho `PollableChannel` |
| `postReceive` | Sau receive trả về message | Chỉ cho `PollableChannel` |
| `afterReceiveCompletion` | Sau receive hoàn tất | Dọn tài nguyên liên quan đến receive |

Trong regular function binding, `preSend` là callback thường dùng để thêm header, kiểm tra metadata hoặc đo lượt message qua channel. `postSend` và `afterSendCompletion` phù hợp để ghi nhận thành công/thất bại của thao tác channel, không phải xác nhận nghiệp vụ của broker.

### Ví dụ interceptor quan sát header

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public final class CorrelationObserver implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {
        Object correlationId =
                message.getHeaders().get("x-correlation-id");

        if (correlationId == null) {
            // Ghi metric thiếu header; tránh log toàn bộ payload.
        }

        return message;
    }
}
~~~

Kết quả `return message` cho phép message tiếp tục. Nếu chỉ muốn quan sát, không sửa payload hoặc headers mà không có yêu cầu rõ ràng.

### preSend trả null là thao tác chặn message

~~~java
@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    if (shouldReject(message)) {
        return null;
    }
    return message;
}
~~~

Theo contract của `ChannelInterceptor`, trả `null` nghĩa là thao tác send không tiếp tục. Điều này có thể khiến message bị lọc bỏ mà không qua DLQ theo cách bạn dự đoán. Đối với dữ liệu nghiệp vụ cần at-least-once, không dùng `return null` như một cơ chế xử lý lỗi mặc định. Hãy kiểm tra kết quả của binder, error handling và acknowledgment trong integration test; cân nhắc filter/router hoặc cơ chế reject/dead-letter thích hợp với broker.

## 3. Phân biệt interceptor cục bộ và global

Có hai cách đăng ký chính:

1. Gắn `ChannelInterceptor` trực tiếp vào một `InterceptableChannel` do ứng dụng quản lý.
2. Khai báo bean `ChannelInterceptor` với `@GlobalChannelInterceptor` để Spring Integration tìm các channel có tên khớp pattern và gắn interceptor.

So sánh:

| Đặc điểm | Đăng ký cục bộ | Global với pattern |
|---|---|---|
| Phạm vi | Một channel đã biết | Các channel có tên khớp pattern |
| Cách cấu hình | `channel.addInterceptor(...)` | `@GlobalChannelInterceptor(patterns = "...")` |
| Với channel do framework sinh | Phải lấy đúng channel instance và lifecycle | Thường dễ kiểm soát hơn bằng tên binding |
| Với `StreamBridge` | Khó dùng nếu channel tạo động | Cách được tài liệu Spring Cloud Stream hướng dẫn |
| Rủi ro | Gắn nhầm instance | Pattern quá rộng hoặc không khớp |

Đừng chỉ tạo một bean implements `ChannelInterceptor` rồi kỳ vọng `StreamBridge` tự thêm nó vào tất cả output binding. Spring Cloud Stream có cơ chế chọn interceptor theo `@GlobalChannelInterceptor`.

## 4. Đăng ký cục bộ khi sở hữu MessageChannel

Khi ứng dụng tự tạo một channel Spring Integration, có thể gắn interceptor ngay lúc khai báo:

~~~java
@Configuration(proxyBeanMethods = false)
class InternalChannelConfig {

    @Bean
    DirectChannel internalAuditChannel() {
        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(new CorrelationObserver());
        return channel;
    }
}
~~~

`DirectChannel` là một `InterceptableChannel`; `addInterceptor(...)` thêm interceptor vào danh sách của channel đó.

Cách này thích hợp với channel nội bộ mà ứng dụng tự quản lý. Với channel được Spring Cloud Stream tạo cho function binding, không nên tự tạo một `DirectChannel` mới cùng tên rồi giả định binder sẽ dùng instance đó. Nếu phải thao tác với framework-generated channel, hãy xác minh bean/channel thực tế và thứ tự khởi tạo của release đang dùng; trong đa số trường hợp, pattern của global interceptor rõ ràng hơn.

### Không nhầm một ChannelInterceptor bean với binding

Ví dụ sau chỉ tạo một bean:

~~~java
@Bean
ChannelInterceptor auditInterceptor() {
    return new CorrelationObserver();
}
~~~

Nó không diễn đạt channel nào cần dùng interceptor. Đối với `StreamBridge`, nếu cần chọn binding theo tên, hãy khai báo `@GlobalChannelInterceptor(patterns = "...")`.

## 5. Áp dụng @GlobalChannelInterceptor cho một output binding

Giả sử hệ thống có hai output:

- `orders-out-0` gửi event đơn hàng.
- `audit-out-0` gửi event audit.

Yêu cầu: chỉ thêm header `x-source-binding` cho message trên `orders-out-0`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.GlobalChannelInterceptor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

@Configuration(proxyBeanMethods = false)
class InterceptorConfiguration {

    @Bean
    @GlobalChannelInterceptor(patterns = "orders-out-0")
    ChannelInterceptor ordersOutputMetadata() {
        return new ChannelInterceptor() {

            @Override
            public Message<?> preSend(
                    Message<?> message,
                    MessageChannel channel) {
                return MessageBuilder.fromMessage(message)
                        .setHeaderIfAbsent(
                                "x-source-binding", "orders-out-0")
                        .build();
            }
        };
    }
}
~~~

Điểm cần lưu ý:

- Pattern khớp **tên channel/binding** `orders-out-0`.
- `setHeaderIfAbsent` giữ giá trị header có sẵn; nếu cần bắt buộc nguồn tin cậy, phải định nghĩa chính sách ghi đè/kiểm tra riêng.
- `MessageBuilder.fromMessage(...)` tạo message mới, giữ payload và các header được copy theo API; không đột biến message gốc.
- `audit-out-0` không khớp, nên interceptor này không được gắn cho channel đó.
- Nếu tên binding thực tế được remap, pattern cần theo tên channel hiệu lực.

Một interceptor có thể được áp dụng cho nhiều channel khác nếu pattern lỡ khớp; hãy chọn pattern đủ chặt và viết test phủ cả chiều "không được áp dụng".

## 6. Áp dụng cho input binding

Interceptor cũng có thể được khai báo cho input channel của regular message-channel binder:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "validateOrders-in-0", order = -10)
ChannelInterceptor inboundCorrelationCheck() {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {

            Object id = message.getHeaders().get("x-correlation-id");

            if (!(id instanceof String value) || value.isBlank()) {
                throw new IllegalArgumentException(
                        "Missing x-correlation-id");
            }

            return message;
        }
    };
}
~~~

Mục đích ví dụ là cho thấy interceptor chỉ áp dụng với input binding được chỉ định. Việc ném exception ở `preSend` có thể làm lỗi phát sinh **trước khi function nghiệp vụ chạy**, và cách binder xử lý (retry, ack/nack, error channel, DLQ) phụ thuộc implementation. Trên production, cần kiểm thử đường lỗi với broker thật trước khi dùng interceptor để reject message.

Không giả định interceptor luôn thấy POJO đã deserialize giống tham số function. Thời điểm conversion của payload/header tùy luồng tích hợp, binder và content type. Khi chỉ kiểm tra correlation ID, nên xử lý trên metadata độc lập với payload class.

## 7. Global interceptor cho tất cả binding

Spring Cloud Stream hướng dẫn dùng `@GlobalChannelInterceptor(patterns = "*")` khi muốn interceptor áp dụng rộng cho các message channels, gồm những output `StreamBridge` đủ điều kiện.

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "*", order = 20)
ChannelInterceptor globalMetricsInterceptor(MeterRegistry registry) {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {
            registry.counter("stream.channel.sends").increment();
            return message;
        }
    };
}
~~~

Pattern `*` có phạm vi rất rộng. Nó có thể chạm tới cả channel phục vụ integration flow, error path hoặc các channel nội bộ khác, tùy Spring context. Nếu chỉ cần đo output của một dịch vụ, hãy dùng pattern `*-out-0` hoặc danh sách tên rõ ràng và kiểm tra channel được gắn thực tế.

### Không dùng wildcard cho logic có side effect

Interceptor global phù hợp với tác vụ nhẹ và an toàn như thống kê hoặc thêm metadata trung tính. Không nên:

- Gọi remote service đồng bộ ở mọi message.
- Thực thi thanh toán, gửi email hoặc cập nhật database trong `preSend`.
- Log toàn bộ payload có thể chứa dữ liệu nhạy cảm.
- Dùng `return null` làm bộ lọc mặc định.
- Áp chính sách validation chuyên biệt của một topic lên mọi channel.

Một interceptor trên đường nóng (hot path) chạy với tần suất tương ứng số message qua các channel khớp. Overhead vài millisecond mỗi message có thể làm throughput giảm mạnh khi tải lớn.

## 8. Áp dụng nhiều pattern và loại trừ channel

`@GlobalChannelInterceptor` cho phép một hoặc nhiều pattern:

~~~java
@Bean
@GlobalChannelInterceptor(
        patterns = {"orders-out-0", "returns-out-0"},
        order = 5)
ChannelInterceptor businessEventHeaders() {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {
            return MessageBuilder.fromMessage(message)
                    .setHeaderIfAbsent("x-event-source", "commerce")
                    .build();
        }
    };
}
~~~

Với Spring Integration hiện đại, pattern có thể có ký tự đại diện và pattern phủ định bắt đầu bằng dấu `!`. Ví dụ:

~~~java
@GlobalChannelInterceptor(
        patterns = {"orders-*", "!orders-debug*"})
~~~

Cấu hình này minh họa áp dụng cho nhóm `orders-` nhưng loại trừ nhóm debug theo quy tắc pattern matcher của Spring Integration. Hãy test cả positive và negative patterns; đừng chỉ kiểm tra annotation có mặt.

| Pattern | Ý định | Rủi ro |
|---|---|---|
| `orders-out-0` | Một output binding | Khi rename binding, không còn khớp |
| `orders-*` | Các channel thuộc nhóm orders | Có thể trúng cả input/error/internal cùng tiền tố |
| `*-out-0` | Nhiều output channel | Không đảm bảo mọi channel chỉ là output binding |
| `*` | Mọi channel phù hợp | Phạm vi rất rộng |
| `orders-*`, `!orders-debug*` | Bao gồm orders, trừ debug | Phụ thuộc semantics pattern của phiên bản |

Pattern được kiểm tra trên tên channel. `patterns = "payments.*"` không tự động lọc message theo event type, header, class payload hoặc topic routing. Nếu muốn định tuyến message theo nội dung, dùng router/filter ở tầng phù hợp.

## 9. Binding alias và channel name hiệu lực

Spring Cloud Stream cho phép ánh xạ tên binding mặc định thành tên mô tả hơn:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrders
    stream:
      function:
        bindings:
          validateOrders-in-0: orderInput
          validateOrders-out-0: orderOutput
      bindings:
        orderInput:
          destination: orders.created
          group: order-validation
        orderOutput:
          destination: orders.accepted
~~~

Với cách remap này, cấu hình binding dùng `orderInput` và `orderOutput`. Khi chọn pattern interceptor, cần xác minh channel bean names mà binder thực sự đăng ký trong application context và dùng tên phù hợp, thay vì sao chép `validateOrders-in-0` từ ví dụ khác.

### Cách tránh nhầm tên

1. Liệt kê các binding hiệu lực ở startup và `/actuator/bindings` nếu endpoint được bật.
2. Kiểm tra bean names của `MessageChannel` trong Spring context khi cần chẩn đoán.
3. Xem function definition, remapping ở `spring.cloud.stream.function.bindings` và dynamic binding names.
4. Chọn pattern theo channel names đã quan sát.
5. Viết integration test assert interceptor chạy đúng binding và không chạy trên binding khác.

Endpoint `bindings` phản ánh binding lifecycle; nó không nhất thiết liệt kê toàn bộ internal channels. Khi cần chứng minh pattern match, kiểm tra channel/interceptor list hoặc dùng test behavior, không chỉ kiểm tra broker destination.

## 10. StreamBridge và channel tạo động

`StreamBridge` hỗ trợ gửi message từ luồng imperative như REST request, scheduled job hoặc callback ngoài hệ thống sang output binding mà không cần `Supplier` cố định.

~~~java
@Service
class EventPublisher {

    private final StreamBridge bridge;

    EventPublisher(StreamBridge bridge) {
        this.bridge = bridge;
    }

    boolean sendOrder(OrderCreated event) {
        return bridge.send("orders-out-0", event);
    }

    boolean sendAudit(String event) {
        return bridge.send("audit-out-0", event);
    }
}
~~~

Lần gửi đầu có thể tạo output binding/channel động. Tài liệu Spring Cloud Stream nói rõ `StreamBridge` dùng `MessageChannel` và interceptor phải được chỉ rõ bằng `@GlobalChannelInterceptor`. Hai lựa chọn được tài liệu minh họa:

- `@GlobalChannelInterceptor(patterns = "*")`: áp dụng rộng cho các output `StreamBridge`.
- `@GlobalChannelInterceptor(patterns = "orders-*")`: chỉ áp dụng cho output channel có tên phù hợp.

Không giả định rằng mọi `ChannelInterceptor` bean độc lập sẽ được `StreamBridge` tự động đưa vào chuỗi interceptor. Đồng thời, không cần tự tạo channel bean chỉ để `StreamBridge` nhìn thấy interceptor; hãy chọn pattern global rõ ràng.

### Dynamic output cần test lần gửi đầu

Một điểm dễ bỏ sót là channel có thể chưa tồn tại khi application context vừa khởi động. Spring Integration hiện đại hỗ trợ global interceptor cho channel được đăng ký động. Tuy nhiên, cách `StreamBridge` tạo binding và tên channel có thể phụ thuộc phiên bản; kiểm thử lần gửi đầu và lần gửi tiếp theo trên đúng Spring Cloud Stream release.

Với ứng dụng có danh sách destination động lớn, cần quan tâm cả giới hạn cache dynamic binding. Interceptor là logic trên channel; nó không làm destination trở thành hợp lệ hoặc cấp quyền tạo topic.

## 11. Thứ tự interceptor khi có nhiều lớp

Khi nhiều interceptor cùng khớp một channel, thứ tự ảnh hưởng dữ liệu mà mỗi interceptor quan sát hoặc chỉnh sửa.

Ví dụ:

- Interceptor A thêm `x-correlation-id`.
- Interceptor B kiểm tra `x-correlation-id`.
- Interceptor C ghi metric.

Nếu B chạy trước A, B có thể từ chối message vì header chưa được bổ sung.

`@GlobalChannelInterceptor` có thuộc tính `order`:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders-out-0", order = -20)
ChannelInterceptor correlationEnricher() {
    return new CorrelationEnricher();
}

@Bean
@GlobalChannelInterceptor(patterns = "orders-out-0", order = 20)
ChannelInterceptor correlationValidator() {
    return new CorrelationValidator();
}
~~~

Theo Spring Integration, `order` âm đặt global interceptor trước interceptor cục bộ đã được cấu hình trên channel; `order` dương đặt sau interceptor cục bộ. Nhiều global interceptor khớp cùng channel được sắp xếp theo giá trị order. Giá trị mặc định là `0`.

Tuy nhiên, thứ tự toàn bộ interceptor chain còn phụ thuộc cách channel được xây dựng và interceptor nội bộ của framework. Nếu logic phụ thuộc nghiêm ngặt vào thứ tự, cần kiểm tra `getInterceptors()` trên channel thực tế và test case có dữ liệu đầu vào cần biến đổi.

### Callback hoàn tất có thứ tự riêng

`afterSendCompletion` được gọi khi `send` kết thúc, kể cả lúc xảy ra exception; thứ tự cleanup thường ngược với thứ tự pre-send đối với các interceptor đã tham gia. Không dựa vào `postSend` là dấu hiệu final broker ack. Để biết Kafka send được broker xác nhận hay RabbitMQ publish được confirm, dùng callback/confirm của producer/binder tương ứng.

## 12. Sửa header an toàn

Header là metadata có thể đi qua nhiều service. Thay đổi header trong interceptor có thể làm thay đổi routing, tracing và security behavior.

Ví dụ thêm correlation ID nếu chưa có:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders-out-0")
ChannelInterceptor correlationIdInterceptor() {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {

            Object existing =
                    message.getHeaders().get("x-correlation-id");

            if (existing instanceof String id && !id.isBlank()) {
                return message;
            }

            return MessageBuilder.fromMessage(message)
                    .setHeader(
                            "x-correlation-id",
                            UUID.randomUUID().toString()
                    )
                    .build();
        }
    };
}
~~~

Ý định là chỉ bổ sung khi không có ID hữu ích. Nhưng trong một luồng cần correlation ID ổn định xuyên suốt event chain, việc tự sinh ID mới ở mỗi lần retry hoặc mỗi service có thể phá vỡ truy vết. Tốt hơn là tạo ID tại ranh giới tin cậy và giữ nguyên theo contract.

Một số nguyên tắc:

- Dùng `MessageBuilder.fromMessage` để tạo message mới.
- Không thay payload trừ khi đã xác định rõ content type và kiểu đích.
- Không giả định mọi header đều được broker mapper truyền qua.
- Không ghi credential, PII hoặc dữ liệu nhạy cảm vào log/metrics label.
- Không tin tưởng header tenant/role do producer tùy ý cung cấp để quyết định quyền truy cập.
- Giới hạn kích thước, charset và kiểu header để tránh chi phí serialization bất thường.

## 13. Quan sát bằng postSend và afterSendCompletion

Có thể đo số lần channel nhận send request:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders-out-0")
ChannelInterceptor channelMetrics(MeterRegistry registry) {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {
            registry.counter(
                    "orders.channel.pre_send"
            ).increment();
            return message;
        }

        @Override
        public void postSend(
                Message<?> message,
                MessageChannel channel,
                boolean sent) {
            registry.counter(
                    "orders.channel.post_send",
                    "sent", Boolean.toString(sent)
            ).increment();
        }

        @Override
        public void afterSendCompletion(
                Message<?> message,
                MessageChannel channel,
                boolean sent,
                Exception ex) {
            if (ex != null) {
                registry.counter(
                        "orders.channel.errors"
                ).increment();
            }
        }
    };
}
~~~

Đây là metric của thao tác **channel send**. `sent = true` không đồng nghĩa Kafka broker đã commit record, RabbitMQ publisher confirm đã đến hoặc Pulsar producer đã nhận durable acknowledgment. Producer có thể gửi bất đồng bộ sau callback này.

Với throughput lớn, các metrics phải dùng tag có cardinality hữu hạn: tên binding hoặc trạng thái gửi, tránh dùng event ID, order ID hoặc correlation ID làm tag.

### Đo latency đúng giai đoạn

Nếu cần đo thời gian xử lý nghiệp vụ hoặc broker acknowledgment, hãy instrument đúng API ở function, producer callback hoặc Micrometer Observation. Thời gian `preSend` → `afterSendCompletion` chỉ phản ánh phạm vi thao tác channel; với asynchronous channel, nó có thể kết thúc trước khi handler nghiệp vụ hoàn tất.

## 14. Giới hạn theo loại binder và programming model

Không phải mọi binder đều định nghĩa cùng một `MessageChannel` cho dữ liệu bên trong.

| Mô hình | Đường xử lý chính | Nên dùng ChannelInterceptor? |
|---|---|---|
| Regular Kafka binder với `Function<T,R>` | Spring MessageChannel + Kafka adapter | Có thể, ở channel khớp binding |
| RabbitMQ binder với function imperative | Spring MessageChannel + AMQP adapter | Có thể, ở channel khớp binding |
| Pulsar binder với function message-channel | Phụ thuộc adapter của binder/version | Xác minh channel interception trong integration test |
| `StreamBridge` output | Tạo/gửi qua MessageChannel | Có, khi đăng ký global interceptor theo pattern |
| Kafka Streams binder `KStream/KTable` | Kafka Streams DSL/topology | Không giả định ChannelInterceptor bắt được từng record |
| Kafka client chạy trực tiếp ngoài binder | Kafka client API | Cần producer/consumer interceptor của Kafka hoặc instrument riêng |

Kafka Streams binder sử dụng `KStream`, `KTable`, Kafka Streams Serde và processor topology. `ChannelInterceptor` của Spring Messaging không phải một Kafka Streams `Processor`. Nếu cần xử lý headers hoặc ghi metric cho từng record trong topology, dùng Kafka Streams DSL/Processor API hoặc metrics của Kafka Streams theo tính năng phù hợp.

Tương tự, Kafka `ProducerInterceptor`/`ConsumerInterceptor` là interface của Kafka client, có phạm vi khác `ChannelInterceptor`. Đừng đăng ký một loại rồi khẳng định đã chặn được mọi giai đoạn của loại còn lại.

## 15. Interceptor và consumer group/partition

Interceptor không tự tăng throughput hoặc số partition. Khi hệ thống scale nhiều replica, mỗi replica có interceptor chain riêng trên các channels được tạo trong process đó.

Ví dụ:

- Ba replica cùng đọc group `order-validation`.
- Mỗi replica đăng ký interceptor cho `validateOrders-in-0`.
- Message được chia theo semantics của binder/consumer group.
- Interceptor chỉ chạy ở replica thực sự nhận message qua channel đó.

Do đó, không nhân một metric local của interceptor với số replica mà chưa xét cách load được phân phối. Nếu tăng concurrency hoặc số partition, số thread gọi interceptor có thể tăng; interceptor cần thread-safe.

Không lưu trạng thái mutable per-message trong field dùng chung của interceptor nếu không đồng bộ. Ví dụ `HashMap` không an toàn dưới nhiều consumer thread. Dùng metrics registry, immutable config hoặc cơ chế concurrent thích hợp; lưu dữ liệu event theo key trong state store/broker nếu cần độ bền qua restart.

## 16. Thread safety và chi phí của interceptor

Một bean interceptor có thể được dùng đồng thời bởi nhiều channel hoặc nhiều consumer thread. Các thao tác trong `preSend` nên:

- Thực hiện nhanh, không block I/O kéo dài.
- Không giữ reference tới payload lớn sau callback.
- Không tạo thread mới cho mỗi message.
- Không dùng synchronized lock rộng cho mỗi lần gửi.
- Không truy cập database trong đường nóng nếu không thực sự cần.
- Hạn chế log payload; ưu tiên message count, elapsed time và error class.
- Dùng message builder an toàn khi cần thêm header.
- Xử lý trường hợp header null, sai kiểu hoặc giá trị không hợp lệ.

Một interceptor global được gọi với tần suất bằng tổng message của các channel khớp. Ví dụ bốn binding mỗi binding xử lý 1.500 message/giây tạo khoảng 6.000 `preSend` mỗi giây. Nếu mỗi callback mất 2 ms CPU trung bình, tổng tải CPU lý thuyết là khoảng 12 CPU-seconds trên một giây đồng hồ ở quy mô đó; vì vậy ngay cả logic nhỏ cũng đáng benchmark.

### Tránh tự tạo vòng lặp ghi message

Nếu interceptor gửi event audit bằng `StreamBridge`, output audit có thể cũng khớp pattern global và tiếp tục kích hoạt interceptor. Điều này có thể tạo recursion hoặc storm.

Ví dụ sai về ý tưởng:

~~~java
@GlobalChannelInterceptor(patterns = "*")
ChannelInterceptor auditEveryMessage(StreamBridge bridge) {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {
            bridge.send("audit-out-0", "message seen");
            return message;
        }
    };
}
~~~

Đừng dùng cách này. Đối với audit, dùng pattern loại trừ audit channel, tích hợp observation không gửi đồng bộ vào cùng chain, hoặc dùng outbox/audit flow được thiết kế riêng.

## 17. Test đúng binding với StreamBridge và Test Binder

Spring Cloud Stream Test Binder hỗ trợ `InputDestination`/`OutputDestination` để kiểm thử wiring trong JVM. Với `StreamBridge`, test nên chứng minh hai chiều: binding mục tiêu có header mới, binding khác không bị ảnh hưởng.

Dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Một integration test minh họa:

~~~java
@SpringBootTest(properties = {
        "spring.cloud.stream.output-bindings=orders-out-0;audit-out-0"
})
@EnableTestBinder
class ScopedInterceptorTest {

    @Autowired
    StreamBridge bridge;

    @Autowired
    OutputDestination output;

    @Test
    void appliesOnlyToOrdersOutput() {
        bridge.send("orders-out-0", "order-event");
        bridge.send("audit-out-0", "audit-event");

        Message<byte[]> orders =
                output.receive(2_000, "orders-out-0");
        Message<byte[]> audit =
                output.receive(2_000, "audit-out-0");

        assertThat(orders).isNotNull();
        assertThat(audit).isNotNull();

        assertThat(
                orders.getHeaders().get("x-source-binding"))
                .isEqualTo("orders-out-0");

        assertThat(
                audit.getHeaders().get("x-source-binding"))
                .isNull();
    }
}
~~~

Test trên cần import cấu hình `InterceptorConfiguration` ở phần 5. Cấu hình `spring.cloud.stream.output-bindings` tạo output binding tường minh cho mục đích kiểm thử; khi dùng dynamic creation thuần, có thể bỏ property đó và xác minh ngay lần `StreamBridge.send` đầu tiên.

Khi test, lưu ý:

- Test Binder không cần Kafka/Rabbit/Pulsar broker.
- Dùng tên output binding thực tế khi gọi `OutputDestination.receive(...)`.
- Timeout phải hữu hạn.
- Nếu cùng test context chứa nhiều function/binding, cấu hình output names rõ ràng.
- Không suy ra header chắc chắn được map qua broker thật chỉ vì test in-memory pass.
- Nên kiểm tra cả binding không khớp và negative pattern nếu có.

### Kiểm tra số lần interceptor được gọi

Có thể dùng counter thread-safe (ví dụ `AtomicInteger`) hoặc spy bean để xác minh:

- Một message trên `orders-out-0` kích hoạt đúng interceptor.
- Message trên `audit-out-0` không kích hoạt.
- Gửi lần đầu qua dynamic `StreamBridge` cũng được áp dụng.
- Sau nhiều lần gửi, interceptor không bị đăng ký trùng.
- Nếu `order` quan trọng, các interceptor chạy đúng chuỗi.

Đừng đòi số callback phải đúng bằng số business event nếu cùng message đi qua nhiều channel khớp pattern. Count các lần `preSend` trên channel khác nhau có thể cao hơn số event được publish.

## 18. Broker integration test cho header mapping và lỗi

Test Binder chứng minh interceptor được gắn đúng trong application context nhưng không chứng minh header/payload đi qua Kafka, RabbitMQ hoặc Pulsar đúng wire format.

Với Kafka, RabbitMQ hoặc Pulsar, cần chạy test có middleware thật:

1. Gửi message qua `StreamBridge` hoặc function output.
2. Consume record ở phía bên kia bằng binder/client phù hợp.
3. Kiểm tra `x-source-binding` và content type có được truyền qua header mapper không.
4. Kiểm tra serializer/deserializer nhận payload đúng kiểu.
5. Xác minh interceptor không đổi message key, partition key hoặc routing header ngoài dự kiến.
6. Làm handler/interceptor ném exception để quan sát retry/ack/DLQ.
7. Gửi lại cùng message sau restart và kiểm tra idempotency.
8. Tăng concurrency để phát hiện race condition.
9. Đo throughput/latency khi bật và tắt interceptor.

Với Kafka Streams binder, hãy test bằng Kafka Streams topology/integration test riêng, không dựa vào `ChannelInterceptor` để chứng minh per-record interception.

### Interceptor lỗi không mặc định đồng nghĩa DLQ

Nếu `preSend` ném exception, `MessageChannel.send` có thể thất bại trước khi message tới function hoặc broker. Binder quyết định có retry/nack/DLQ hay không theo đường lỗi của nó. Chỉ một callback không định nghĩa được bảo đảm delivery.

Không che exception và trả message hợp lệ khi công việc yêu cầu đã thất bại. Nếu cần validation dữ liệu, cân nhắc đặt ở function để có contract/error policy dễ kiểm thử hơn.

## 19. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Bean interceptor tồn tại nhưng StreamBridge không gọi | Không dùng `@GlobalChannelInterceptor` hoặc pattern không khớp | Thêm annotation và kiểm tra binding/channel name |
| Pattern là tên Kafka topic nhưng không chạy | Global interceptor match channel name, không match broker destination | Dùng tên channel hiệu lực |
| Interceptor chạy trên mọi luồng | `patterns = "*"` quá rộng | Dùng pattern cụ thể hoặc danh sách binding |
| Interceptor không chạy sau rename binding | Alias thay đổi tên cấu hình/channel | Kiểm tra `function.bindings` và channel bean |
| Header có trong test binder nhưng mất ở broker | Header mapper/binder không truyền | Broker integration test và cấu hình mapping |
| Message biến mất không có DLQ | `preSend` trả `null` | Thiết kế reject/filter có chủ đích; xác minh ack |
| Interceptor xuất hiện hai lần | Cấu hình global và gắn cục bộ cùng bean, hoặc đăng ký lặp | Kiểm tra `getInterceptors()` |
| postSend sent=true nhưng broker không có record | Channel send chưa phản ánh broker acknowledgment | Dùng producer send result/confirm và broker metrics |
| Kafka Streams record không đi qua interceptor | KStream xử lý bằng Kafka Streams DSL | Dùng Processor API, transform hoặc interceptor Kafka client thích hợp |
| CPU cao sau khi thêm metrics | Global interceptor block/log nhiều hoặc tag cardinality cao | Giảm chi phí và pattern scope |
| Lỗi trùng audit event | Interceptor audit lại kích hoạt chính audit output | Loại trừ audit channel hoặc tách luồng |
| Exception làm retry nhiều lần | Validation nằm trước function và binder retry | Phân loại lỗi, thiết kế retry budget và DLQ |
| Test flaky ở dynamic binding | Test không kiểm tra lần gửi đầu, context/channel tạo theo thời điểm | Test dynamic binding creation và lifecycle |
| Thread safety bug khi scale | Interceptor giữ mutable state không đồng bộ | Dùng state thread-safe hoặc không giữ state |

## 20. Quy trình chọn interceptor cho hệ thống nhiều binding

Khi muốn áp một chính sách cross-cutting, làm theo thứ tự:

1. Liệt kê các function, binding names, destination và group trong ứng dụng.
2. Xác định đường dữ liệu dùng regular message channel hay Kafka Streams DSL.
3. Chọn chính sách: metadata enrichment, validation, metrics hay tracing.
4. Xác định chính xác input/output channel cần áp dụng.
5. Nếu channel do ứng dụng sở hữu, cân nhắc `addInterceptor`.
6. Với binding của Spring Cloud Stream, ưu tiên `@GlobalChannelInterceptor` có pattern cụ thể.
7. Với `StreamBridge`, dùng annotation global để interceptor được nhận diện khi tạo output channel.
8. Viết test "phải chạy" và test "không được chạy".
9. Xác định thứ tự interceptor và test khi order quan trọng.
10. Nếu thay headers, xác minh broker header mapping và backward compatibility.
11. Nếu interceptor có thể ném exception, test retry/ack/DLQ trên broker.
12. Đo overhead, thread safety và callback count ở tải thực.
13. Đặt chính sách bảo mật cho headers, logs và metrics.
14. Ghi lại pattern và tên binding trong runbook; cập nhật test khi rename function/binding.

### Quy tắc lựa chọn ngắn

| Nhu cầu | Công cụ ưu tiên |
|---|---|
| Thêm header cho một output `StreamBridge` | `@GlobalChannelInterceptor(patterns = "orders-out-0")` |
| Theo dõi mọi message channel trong app | Global interceptor `patterns = "*"`, cân nhắc scope và chi phí |
| Intercept một channel nội bộ tự tạo | `InterceptableChannel.addInterceptor` |
| Validate payload nghiệp vụ có kiểu | Function/validator rõ ràng, test contract |
| Thay đổi Kafka record trong KStream | Kafka Streams DSL/Processor API |
| Theo dõi producer send ack | Kafka producer callbacks, Rabbit confirms hoặc Pulsar send acknowledgment |
| Thống kê delivery/retry/DLQ | Binder/broker metrics và error handling |
| Theo dõi HTTP request trước khi publish | HTTP filter/interceptor hoặc controller instrumentation |

## Kết luận

`ChannelInterceptor` can thiệp vào các thao tác gửi/nhận trên `MessageChannel`; `@GlobalChannelInterceptor` gắn một interceptor vào những channel có tên khớp pattern. Trong Spring Cloud Stream, hãy phân biệt **binding name** với **broker destination** và **consumer group** để không chọn nhầm phạm vi. Với `StreamBridge`, interceptor cần được khai báo theo cơ chế global mà tài liệu framework hỗ trợ; dùng pattern cụ thể khi chỉ muốn một hoặc một nhóm binding.

Một interceptor nên làm việc nhẹ, thread-safe và không chứa side effect nghiệp vụ khó rollback. `preSend` có thể sửa message hoặc chặn gửi khi trả `null`; `postSend` chỉ cho biết kết quả send vào channel, không bảo đảm broker đã xác nhận. Đừng giả định `ChannelInterceptor` chạy cho từng record trong Kafka Streams DSL.

Hãy kiểm thử trên đúng binding bằng Test Binder, bao gồm cả binding cần loại trừ; sau đó dùng Kafka/RabbitMQ/Pulsar integration test để xác minh headers, retry, ack và wire behavior. Khi mở rộng nhiều instance và nhiều binding, giữ pattern chính xác, callback rẻ và trạng thái interceptor an toàn dưới concurrency.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream — Producing and Consuming Messages, Using Channel Interceptors with StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): cơ chế `StreamBridge` và ví dụ `@GlobalChannelInterceptor(patterns = "*")` hoặc scoped patterns.
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html): tên binding theo function và alias.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): destination, group và cấu hình theo binding name.
- [Spring Integration — Global Channel Interceptor Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html): patterns, negative patterns, order và các channel được gắn interceptor.
- [Spring Integration — GlobalChannelInterceptor API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/config/GlobalChannelInterceptor.html): annotation và semantics của `patterns`/`order`.
- [Spring Framework — ChannelInterceptor API](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html): callback `preSend`, `postSend`, `afterSendCompletion` và hành vi `return null`.
- [Spring Cloud Stream — Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html): mô hình cấu hình Kafka Streams topology khác regular message channel.
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): Test Binder và `InputDestination`/`OutputDestination`.

Khi triển khai, đối chiếu version Spring Cloud Stream, Spring Integration, Spring Boot và binder đang dùng. Tên channel của dynamic binding, alias mapping và callback/lifecycle nên được xác minh bằng test trên chính tổ hợp dependency production.

