# Giữ, bổ sung và loại bỏ header khi biến đổi thông điệp

Trong Spring Cloud Stream, dữ liệu được truyền giữa các hàm dưới dạng message. Một message có payload chứa dữ liệu nghiệp vụ và headers chứa metadata như mã tương quan, loại sự kiện, phiên bản schema hoặc thông tin truy vết. Khi một Function biến đổi payload, ứng dụng cần quyết định metadata nào tiếp tục đi cùng message, metadata nào cần cập nhật và metadata nào phải loại bỏ.

Quyết định này ảnh hưởng trực tiếp đến khả năng truy vết, tương thích schema, bảo mật và định tuyến. Giữ tất cả header một cách máy móc có thể làm lộ dữ liệu nội bộ hoặc chuyển tiếp thông tin chỉ có ý nghĩa ở chặng trước. Loại bỏ tất cả header lại có thể làm mất correlation ID, trace context hoặc thông tin cần thiết cho consumer tiếp theo. Bài học này trình bày cách quản lý header có chủ đích khi biến đổi message bằng Supplier, Function và Consumer.

## 1. Payload và header có vai trò khác nhau

Payload là nội dung chính mà consumer cần xử lý. Với sự kiện đơn hàng, payload có thể chứa mã đơn, khách hàng và tổng tiền. Header bổ sung thông tin mô tả message hoặc quá trình vận chuyển:

| Thành phần | Ví dụ | Mục đích |
|---|---|---|
| Payload | orderId, customerId, total | Dữ liệu nghiệp vụ |
| Correlation header | correlationId | Liên kết các bước trong cùng một luồng xử lý |
| Trace header | traceparent, tracestate | Theo dõi request qua nhiều dịch vụ |
| Event header | eventType | Mô tả loại sự kiện |
| Schema header | schemaVersion | Cho biết phiên bản hợp đồng dữ liệu |
| Routing header | tenantId, region | Hỗ trợ định tuyến nếu kiến trúc cho phép |
| Header nội bộ | internal-debug, source-node | Thông tin chỉ dùng ở một chặng hoặc môi trường |

Spring biểu diễn message qua interface Message<T>. Payload có kiểu T; headers được truy cập qua MessageHeaders:

~~~java
import org.springframework.messaging.Message;

void inspect(Message<OrderCreated> message) {
    OrderCreated order = message.getPayload();
    String correlationId =
            (String) message.getHeaders().get("correlationId");

    System.out.println(order.orderId());
    System.out.println(correlationId);
}
~~~

MessageHeaders là cấu trúc bất biến. Không sửa trực tiếp map trả về từ getHeaders(). Để tạo message mới, dùng MessageBuilder; builder tạo tập header mới dựa trên những giá trị ta sao chép, bổ sung hoặc loại bỏ.

## 2. Giữ header khi chỉ bổ sung metadata

Nếu payload không thay đổi và cần thêm một header, có thể tạo message mới từ message hiện tại:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreated> addSourceHeader(Message<OrderCreated> message) {
    return MessageBuilder.fromMessage(message)
            .setHeader("source-service", "order-api")
            .setHeaderIfAbsent("eventType", "OrderCreated")
            .build();
}
~~~

MessageBuilder.fromMessage(message) khởi tạo builder từ message hiện có, giữ các header đang có. setHeader thêm header mới hoặc thay giá trị cũ; setHeaderIfAbsent chỉ đặt giá trị khi header chưa tồn tại. Sau khi gọi build(), kết quả là message mới; message đầu vào và headers của nó không bị sửa.

Chọn setHeader hay setHeaderIfAbsent tùy quyền sở hữu metadata. Nếu hàm hiện tại chịu trách nhiệm xác định eventType, dùng setHeader để đảm bảo giá trị phản ánh sự kiện đầu ra. Nếu muốn giữ thông tin do producer cung cấp khi đã có, setHeaderIfAbsent phù hợp hơn.

Không ghi đè tùy tiện correlationId hoặc trace context. Các giá trị này thường được tạo ở đầu luồng và cần được giữ nhất quán qua các bước để log và hệ thống quan sát có thể liên kết các lần xử lý.

## 3. Biến đổi payload và giữ các header cần thiết

Khi Function đổi kiểu payload, tạo message đầu ra bằng payload mới rồi sao chép header từ message đầu vào. Ví dụ, hàm xác thực đơn hàng nhận OrderCreated và phát OrderValidated:

~~~java
import java.time.Instant;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderCreated(String orderId, String customerId) {}

record OrderValidated(
        String orderId,
        String customerId,
        String status,
        Instant validatedAt) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<Message<OrderCreated>, Message<OrderValidated>> validateOrder() {
        return message -> {
            OrderCreated input = message.getPayload();
            OrderValidated output = new OrderValidated(
                    input.orderId(),
                    input.customerId(),
                    "VALIDATED",
                    Instant.now());

            return MessageBuilder.withPayload(output)
                    .copyHeaders(message.getHeaders())
                    .setHeader("eventType", "OrderValidated")
                    .setHeader("schemaVersion", 2)
                    .removeHeader("internal-debug")
                    .build();
        };
    }
}
~~~

Trong ví dụ:

- withPayload(output) tạo message với payload mới.
- copyHeaders(message.getHeaders()) sao chép các header đầu vào sang message đầu ra.
- setHeader cập nhật eventType và schemaVersion để khớp payload mới.
- removeHeader loại bỏ header nội bộ không còn cần thiết ở chặng tiếp theo.

Đây là cách giữ toàn bộ header rồi loại bỏ những trường đã biết. Cách này phù hợp khi message đầu vào được kiểm soát và danh sách header hợp lệ rõ ràng. Với luồng nhận dữ liệu từ nhiều producer hoặc từ broker bên ngoài, nên cân nhắc allowlist: chỉ sao chép các header được phép truyền tiếp.

## 4. Chỉ giữ header được cho phép

Một message có thể chứa header do producer, framework, binder hoặc broker thêm vào. Không phải header nào cũng có ý nghĩa ở chặng sau. Khi biến đổi payload và chuyển sang một ranh giới dịch vụ khác, allowlist giúp kiểm soát metadata đầu ra:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
class AllowlistFunctions {

    @Bean
    Function<Message<OrderCreated>, Message<OrderValidated>> validateWithAllowlist() {
        return message -> {
            OrderCreated input = message.getPayload();
            OrderValidated output = new OrderValidated(
                    input.orderId(),
                    input.customerId(),
                    "VALIDATED",
                    java.time.Instant.now());

            Object correlationId = message.getHeaders().get("correlationId");
            Object traceparent = message.getHeaders().get("traceparent");

            var builder = MessageBuilder.withPayload(output)
                    .setHeader("eventType", "OrderValidated")
                    .setHeader("schemaVersion", 2);

            if (correlationId != null) {
                builder.setHeader("correlationId", correlationId);
            }
            if (traceparent != null) {
                builder.setHeader("traceparent", traceparent);
            }

            return builder.build();
        };
    }
}
~~~

Ở đây, message đầu ra chỉ mang correlationId, traceparent và metadata mới được tạo. Các header khác không được sao chép. Nếu ứng dụng dùng W3C tracing, cần bảo đảm cơ chế tracing đang dùng chịu trách nhiệm truyền trace context; ví dụ trên chỉ minh họa việc giữ một header khi nó hiện diện.

Allowlist hữu ích khi:

- Message đến từ producer bên ngoài hoặc nguồn không hoàn toàn đáng tin cậy.
- Một chặng cần loại bỏ header nội bộ, thông tin debug hoặc dữ liệu nhạy cảm.
- Payload được phát sang broker khác, nơi header gốc không có cùng ngữ nghĩa.
- Hợp đồng message quy định rõ metadata được phép đi qua ranh giới dịch vụ.

Không nên sao chép header xác thực, cookie, token, thông tin cá nhân hoặc thông tin hạ tầng sang destination khác nếu consumer không có nhu cầu và quyền sử dụng rõ ràng. Metadata không cần thiết làm tăng rủi ro lộ dữ liệu và có thể khiến message vượt giới hạn kích thước header của broker.

## 5. Loại bỏ header không còn phù hợp

Khi một header chỉ có ý nghĩa trong một bước xử lý, hãy loại bỏ nó trước khi phát message sang bước tiếp theo:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreated> removeInternalHeaders(Message<OrderCreated> message) {
    return MessageBuilder.fromMessage(message)
            .removeHeader("internal-debug")
            .removeHeader("temporary-route")
            .removeHeader("legacy-source")
            .build();
}
~~~

removeHeader(name) xóa header có tên tương ứng khỏi message được tạo. Có thể gọi nhiều lần để loại bỏ nhiều header. Việc xóa không thay đổi message đầu vào.

Nên loại bỏ header khi:

- Header chỉ phục vụ debug hoặc xử lý nội bộ ở một chặng.
- Giá trị không còn đúng sau khi payload được biến đổi.
- Header chứa thông tin nhạy cảm không được chuyển đến consumer tiếp theo.
- Header của broker cũ không có ý nghĩa ở broker mới.
- Header trùng lặp hoặc mâu thuẫn với metadata đầu ra đã được chuẩn hóa.

Đừng xóa correlationId hoặc trace context chỉ để làm message gọn hơn nếu hệ thống cần chúng cho truy vết. Cũng không nên xóa tùy tiện các header mà binder hoặc framework dùng cho định tuyến, xác nhận hoặc chuyển đổi. Trước khi loại bỏ một header đặc thù, hãy kiểm tra nguồn tạo ra và nơi tiêu thụ nó.

## 6. Cập nhật content type khi payload thay đổi

Header content type mô tả định dạng payload. Nếu Function thay đổi payload từ JSON object sang chuỗi văn bản, metadata định dạng đầu ra cần phản ánh nội dung mới. Ví dụ:

~~~java
import org.springframework.http.MediaType;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<String> toText(Message<OrderCreated> input) {
    OrderCreated order = input.getPayload();
    String text = "Order " + order.orderId()
            + " belongs to " + order.customerId();

    return MessageBuilder.withPayload(text)
            .copyHeaders(input.getHeaders())
            .setHeader(MessageHeaders.CONTENT_TYPE, MediaType.TEXT_PLAIN)
            .setHeader("eventType", "OrderSummary")
            .build();
}
~~~

Nếu payload vẫn là JSON nhưng schema đã thay đổi, content type vẫn có thể là application/json; khi đó cần cập nhật eventType hoặc schemaVersion theo hợp đồng. Đừng chỉ đổi header schemaVersion để che giấu một thay đổi không tương thích. Producer và consumer phải thống nhất cấu trúc dữ liệu thực tế.

Spring sử dụng message converter dựa trên content type và kiểu payload để chuyển đổi dữ liệu. Nếu header khai báo sai định dạng, consumer có thể giải mã sai hoặc gặp lỗi chuyển đổi. Với dữ liệu JSON, có thể dùng MediaType.APPLICATION_JSON; với nội dung văn bản thuần, dùng MediaType.TEXT_PLAIN.

## 7. Header chuẩn và header do ứng dụng định nghĩa

Không phải mọi header đều do ứng dụng tự do quản lý. Spring Messaging có một số header chuẩn, ví dụ:

| Header | Ý nghĩa | Lưu ý |
|---|---|---|
| id | Định danh message do framework quản lý | Không tự đặt lại |
| timestamp | Thời điểm tạo message | Không dùng thay thời điểm nghiệp vụ |
| contentType | Kiểu nội dung payload | Cập nhật khi định dạng payload thay đổi |
| correlationId | Metadata tương quan do ứng dụng hoặc hạ tầng quy ước | Giữ ổn định qua các bước liên quan |

id và timestamp là header do Spring quản lý và thuộc nhóm chỉ đọc. Không cố gắng ghi đè chúng bằng setHeader. Nếu cần mã sự kiện ổn định hoặc thời điểm nghiệp vụ, hãy tạo header riêng như eventId và occurredAt, hoặc đặt thông tin đó trong payload theo hợp đồng sự kiện.

Header do ứng dụng định nghĩa nên có tên rõ ràng và giá trị đơn giản, có thể tuần tự hóa. Ví dụ eventType, schemaVersion, correlationId, tenantId hoặc traceparent. Tránh đặt tên trùng với header chuẩn hay header riêng của binder.

## 8. Header và giới hạn của broker

MessageHeaders của Spring có thể chứa nhiều kiểu giá trị, nhưng broker không nhất thiết truyền được mọi kiểu đó. Binder thường chuyển đổi header sang dạng mà broker hỗ trợ. Khả năng ánh xạ, danh sách header được phép và cách mã hóa khác nhau theo Kafka, RabbitMQ và Pulsar.

Một số điểm cần kiểm tra:

- Kafka lưu header dưới dạng cặp key/value byte; binder có thể chuyển đổi giá trị và áp dụng chính sách ánh xạ header.
- RabbitMQ hỗ trợ bảng thuộc tính header với các kiểu dữ liệu được AMQP hỗ trợ; một số kiểu Java tùy chỉnh không thể chuyển trực tiếp.
- Pulsar có message properties dạng key/value; giá trị thường cần biểu diễn dưới dạng chuỗi hoặc dạng mà binder hỗ trợ.
- Broker và hạ tầng có giới hạn kích thước message hoặc metadata. Header lớn làm tăng chi phí lưu trữ, truyền tải và có thể khiến publish thất bại.
- Header nội bộ của framework hoặc binder có thể phục vụ định tuyến và giao nhận. Không tự ý đổi tên hay xóa nếu chưa xác nhận tác động.

Không dùng header để chuyển một payload nghiệp vụ lớn. Dữ liệu chính nên nằm trong payload; header chỉ chứa metadata ngắn, cần thiết để định danh, truy vết, phân loại hoặc định tuyến.

## 9. Kết hợp với Supplier, Function và Consumer

Supplier thường tạo message mới nên có thể gắn metadata ngay khi phát. Ví dụ dưới đây dùng lại record OrderCreated đã khai báo ở phần trước:

~~~java
import java.util.UUID;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
class OrderSourceConfiguration {

    @Bean
    Supplier<Message<OrderCreated>> orderSource() {
        return () -> MessageBuilder.withPayload(
                        new OrderCreated("ORD-2001", "CUST-02"))
                .setHeader("eventId", UUID.randomUUID().toString())
                .setHeader("eventType", "OrderCreated")
                .setHeader("schemaVersion", 1)
                .build();
    }
}
~~~

Function có thể đọc và biến đổi payload, đồng thời giữ hoặc cập nhật metadata như các ví dụ trước. Consumer thường chỉ đọc payload và các header cần cho xử lý:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class AuditConfiguration {

    @Bean
    Consumer<Message<OrderValidated>> auditOrder() {
        return message -> {
            String eventId = (String) message.getHeaders().get("eventId");
            String correlationId =
                    (String) message.getHeaders().get("correlationId");

            System.out.printf(
                    "event=%s correlation=%s order=%s%n",
                    eventId,
                    correlationId,
                    message.getPayload().orderId());
        };
    }
}
~~~

Khi Consumer không phát message mới, nó không cần xây dựng lại header. Nếu Consumer gửi tiếp message qua một producer khác, hãy tạo message đầu ra với chính sách giữ header rõ ràng thay vì truyền nguyên toàn bộ metadata của message đầu vào.

## 10. Kiểm thử chính sách header

Kiểm thử nên xác nhận cả header được giữ, header được cập nhật và header bị loại bỏ. Có thể kiểm tra trực tiếp Function bằng JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class OrderHeaderTransformationTest {

    @Test
    void keepsUpdatesAndRemovesExpectedHeaders() {
        Message<OrderCreated> input = MessageBuilder
                .withPayload(new OrderCreated("ORD-3001", "CUST-03"))
                .setHeader("correlationId", "corr-123")
                .setHeader("eventType", "OrderCreated")
                .setHeader("internal-debug", "temporary")
                .build();

        OrderValidated payload = new OrderValidated(
                input.getPayload().orderId(),
                input.getPayload().customerId(),
                "VALIDATED",
                Instant.parse("2025-01-01T10:00:00Z"));

        Message<OrderValidated> output = MessageBuilder
                .withPayload(payload)
                .copyHeaders(input.getHeaders())
                .setHeader("eventType", "OrderValidated")
                .setHeader("schemaVersion", 2)
                .removeHeader("internal-debug")
                .build();

        assertEquals("corr-123", output.getHeaders().get("correlationId"));
        assertEquals("OrderValidated", output.getHeaders().get("eventType"));
        assertEquals(2, output.getHeaders().get("schemaVersion"));
        assertFalse(output.getHeaders().containsKey("internal-debug"));
        assertNull(input.getHeaders().get("schemaVersion"));
    }
}
~~~

Ví dụ tập trung kiểm tra chính sách header. Trong dự án thực tế, có thể đưa logic biến đổi vào một bean Function rồi kiểm tra bean đó hoặc dùng Spring Cloud Stream test binder để xác nhận message qua binding. Kiểm thử tích hợp với broker thật vẫn cần thiết nếu ứng dụng dựa vào header mapping, native header hoặc thuộc tính định tuyến riêng của binder.

## 11. Quy trình quyết định header nào được truyền tiếp

Trước khi phát message sau biến đổi, có thể áp dụng quy trình sau:

1. Liệt kê header hiện có và xác định thành phần nào tạo ra từng header: ứng dụng, Spring, binder hay broker.
2. Giữ correlation ID và trace context nếu chúng vẫn mô tả cùng một luồng xử lý.
3. Cập nhật eventType, schemaVersion và contentType để khớp payload đầu ra.
4. Loại bỏ header tạm thời, header nhạy cảm hoặc header chỉ có ý nghĩa ở chặng trước.
5. Với message đến từ nguồn không tin cậy hoặc chuyển qua ranh giới dịch vụ, dùng allowlist các header được phép.
6. Kiểm tra khả năng tuần tự hóa, giới hạn kích thước và chính sách ánh xạ của binder.
7. Viết kiểm thử xác nhận header cần giữ, header cần cập nhật và header cần loại bỏ.

Header là metadata đi kèm payload, nhưng mỗi header đều có chủ sở hữu và phạm vi sử dụng. Giữ header giúp bảo toàn ngữ cảnh; bổ sung hoặc cập nhật header giúp mô tả chính xác sự kiện mới; loại bỏ header giúp tránh mang theo thông tin lỗi thời hoặc không được phép. Quản lý ba thao tác này một cách có chủ đích làm cho luồng message trong Spring Cloud Stream dễ truy vết, an toàn và nhất quán hơn.
