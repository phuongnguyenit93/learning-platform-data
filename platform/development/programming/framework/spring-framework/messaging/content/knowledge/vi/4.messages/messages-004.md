# Tạo Message bằng MessageBuilder.withPayload và MessageBuilder.fromMessage

## 1. Message gồm payload và headers

Trong Spring Messaging, `Message<T>` là đơn vị dữ liệu được trao đổi giữa các thành phần. Một message có hai phần:

- **Payload**: nội dung chính, có kiểu `T`, ví dụ chuỗi, DTO, lệnh nghiệp vụ hoặc một đối tượng domain.
- **Headers**: metadata đi kèm, ví dụ `contentType`, `correlationId`, `replyChannel`, `errorChannel` hoặc các header tùy chỉnh.

Interface `Message<T>` cung cấp `getPayload()` và `getHeaders()`. Nó không có setter để thay payload hoặc sửa header tại chỗ. Spring cung cấp `MessageBuilder<T>` để tạo message và chuẩn bị headers trước khi gọi `build()`.

Hai factory method thường dùng là:

| Phương thức | Payload của message kết quả | Headers ban đầu |
| --- | --- | --- |
| `MessageBuilder.withPayload(payload)` | Payload được truyền vào | Bắt đầu với bộ headers mới |
| `MessageBuilder.fromMessage(message)` | Giữ payload của message nguồn | Sao chép headers từ message nguồn |

Cả hai trả về `MessageBuilder<T>`, cho phép nối nhiều thao tác rồi gọi `build()` để nhận `Message<T>`.

## 2. Tạo message mới bằng withPayload

`withPayload(T payload)` khởi tạo builder cho một message mới với payload đã cho. Đây là lựa chọn phù hợp khi dữ liệu phát sinh từ một nguồn mới hoặc khi bạn muốn thay payload bằng một giá trị khác.

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-42")
    .setHeader("eventType", "order.created")
    .setHeader("correlationId", "req-17")
    .build();
~~~

Kết quả có payload là `"order-42"` và hai header tùy chỉnh. `withPayload` không nhận `null`; payload phải tồn tại để tạo message.

Kiểu generic được suy luận từ payload. Ví dụ:

~~~java
record OrderCreated(long orderId, String customerId) {
}

Message<OrderCreated> event = MessageBuilder
    .withPayload(new OrderCreated(42L, "customer-7"))
    .setHeader("eventType", "order.created")
    .build();
~~~

Trong trường hợp này, biến `event` có kiểu `Message<OrderCreated>`. Consumer có thể nhận payload đúng kiểu mà không phải ép kiểu từ `Object`.

Nếu payload là một đối tượng `Throwable`, Spring tạo `ErrorMessage` thay cho `GenericMessage`. Đây là cách biểu diễn thông điệp lỗi trong Spring Messaging.

## 3. Tạo builder từ message có sẵn bằng fromMessage

`fromMessage(Message<T> message)` tạo builder từ một message nguồn. Payload và các header của message nguồn được đưa vào builder, nhờ đó có thể bổ sung hoặc điều chỉnh metadata mà không phải dựng lại từng header.

~~~java
Message<String> original = MessageBuilder
    .withPayload("order-42")
    .setHeader("eventType", "order.created")
    .setHeader("correlationId", "req-17")
    .build();

Message<String> validated = MessageBuilder
    .fromMessage(original)
    .setHeader("eventType", "order.validated")
    .setHeader("processingStage", "validation")
    .build();
~~~

Message `validated` giữ payload `"order-42"` và header `correlationId` của message gốc. Header `eventType` được cập nhật thành `order.validated`; header mới `processingStage` được bổ sung.

Đây là cách hữu ích khi một thành phần nhận message, kiểm tra hoặc enrich metadata, rồi chuyển tiếp đến thành phần kế tiếp. Builder tạo ra một message đã chuẩn bị headers; message nguồn không bị sửa trực tiếp.

`fromMessage` giữ nguyên kiểu payload `T`. Nếu nguồn là `Message<String>`, builder tạo ra message có payload kiểu `String`. Khi cần chuyển payload sang kiểu khác, hãy dùng `withPayload(newPayload)` và sao chép các header cần thiết từ message nguồn.

Nếu đầu vào là `ErrorMessage`, `fromMessage` cũng chuyển tiếp `originalMessage` gắn với error message sang error message mới khi được tạo.

## 4. Điều chỉnh headers trong builder

Các phương thức header trả về chính builder, vì vậy có thể nối chúng theo thứ tự dễ đọc:

| Phương thức | Hành vi |
| --- | --- |
| `setHeader(name, value)` | Đặt hoặc thay giá trị header. Nếu `value` là `null`, header đó bị xóa. |
| `setHeaderIfAbsent(name, value)` | Chỉ đặt giá trị nếu header chưa có. |
| `copyHeaders(map)` | Sao chép các cặp tên/giá trị và ghi đè header cùng tên đã có. |
| `copyHeadersIfAbsent(map)` | Chỉ sao chép header chưa có, không ghi đè giá trị hiện tại. |
| `removeHeader(name)` | Xóa một header theo tên. |
| `removeHeaders(patterns...)` | Xóa các header khớp mẫu tên được truyền vào. |

Ví dụ dùng `setHeaderIfAbsent`:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-43")
    .setHeader("source", "checkout")
    .setHeaderIfAbsent("source", "fallback")
    .build();
~~~

Header `source` vẫn có giá trị `checkout`, vì nó đã được đặt trước khi gọi `setHeaderIfAbsent`.

### 4.1. copyHeaders và copyHeadersIfAbsent

Hai phương thức này đặc biệt hữu ích khi kết hợp `withPayload` với headers của message cũ:

~~~java
Message<String> original = MessageBuilder
    .withPayload("order-42")
    .setHeader("eventType", "order.created")
    .setHeader("correlationId", "req-17")
    .build();

Message<String> transformed = MessageBuilder
    .withPayload("Đơn hàng order-42 đã được tạo")
    .copyHeaders(original.getHeaders())
    .setHeader("representation", "text")
    .build();
~~~

Payload mới là một chuỗi mô tả, còn các header nghiệp vụ như `eventType` và `correlationId` được giữ lại. Sau đó, builder thêm header `representation`.

Thứ tự gọi phương thức ảnh hưởng đến kết quả:

~~~java
Message<String> keepLocalValue = MessageBuilder
    .withPayload("order-44")
    .setHeader("eventType", "local.event")
    .copyHeadersIfAbsent(original.getHeaders())
    .build();
~~~

Nếu message nguồn cũng có `eventType`, giá trị `local.event` vẫn được giữ vì `copyHeadersIfAbsent` không ghi đè header đã tồn tại.

Ngược lại, `copyHeaders` ghi đè giá trị header thông thường đã đặt trước đó. Nếu muốn giá trị riêng của builder thắng, hãy gọi `copyHeaders` trước rồi mới gọi `setHeader`.

## 5. Tính bất biến và các header hệ thống

### 5.1. Không sửa MessageHeaders trực tiếp

`MessageHeaders` là cấu trúc bất biến. Các thao tác như `put`, `putAll`, `remove` hoặc `clear` sẽ ném `UnsupportedOperationException`.

Đoạn code sau không hợp lệ:

~~~java
message.getHeaders().put("status", "validated");
~~~

Hãy tạo message mới qua builder:

~~~java
Message<String> updated = MessageBuilder
    .fromMessage(message)
    .setHeader("status", "validated")
    .build();
~~~

Sau khi gọi `build()`, headers của message được tạo theo cơ chế mặc định là bất biến. Không dùng builder để kỳ vọng có thể sửa lại headers của message đã phát đi.

### 5.2. Message bất biến không có nghĩa payload được sao chép sâu

Spring bảo vệ cấu trúc message và map headers, nhưng không tự sao chép sâu payload hoặc từng đối tượng được lưu trong header. Nếu payload là một `ArrayList` hoặc header chứa một đối tượng mutable, các message được tạo từ cùng tham chiếu vẫn có thể nhìn thấy thay đổi trên đối tượng đó.

Vì vậy:
- Ưu tiên payload là record, value object hoặc cấu trúc bất biến.
- Tránh đặt collection mutable dùng chung vào headers.
- Nếu phải biến đổi dữ liệu, tạo payload mới rồi xây dựng message mới.

### 5.3. ID và timestamp là header do framework quản lý

`MessageHeaders.ID` và `MessageHeaders.TIMESTAMP` là các header hệ thống. ID mặc định được sinh tự động; không đặt ID hoặc timestamp nghiệp vụ bằng `setHeader` hay cố ghi đè chúng qua `copyHeaders`.

Nếu cần liên kết nhiều message trong cùng một luồng xử lý, hãy tạo header nghiệp vụ riêng như `correlationId`, `traceId` hoặc `causationId`. Các giá trị này do ứng dụng quản lý và có ý nghĩa rõ ràng trong nghiệp vụ.

## 6. Ví dụ hoàn chỉnh chạy với Java 17+

Ví dụ sau minh họa ba tình huống:

1. `withPayload` tạo message ban đầu.
2. `fromMessage` giữ payload, kế thừa headers và bổ sung thông tin xử lý.
3. `withPayload` tạo payload mới và `copyHeaders` mang metadata từ message nguồn sang.

Cấu trúc dự án:

~~~text
message-builder-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── MessageBuilderDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>message-builder-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>MessageBuilderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/MessageBuilderDemo.java**

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class MessageBuilderDemo {

    public static void main(String[] args) {
        Message<String> original = MessageBuilder
            .withPayload("order-42")
            .setHeader("eventType", "order.created")
            .setHeader("correlationId", "req-17")
            .build();

        Message<String> validated = MessageBuilder
            .fromMessage(original)
            .setHeader("eventType", "order.validated")
            .setHeader("processingStage", "validation")
            .build();

        Message<String> description = MessageBuilder
            .withPayload("Đơn hàng order-42 đã được tạo")
            .copyHeaders(original.getHeaders())
            .setHeader("representation", "text")
            .build();

        Message<String> localEvent = MessageBuilder
            .withPayload("order-44")
            .setHeader("eventType", "local.event")
            .copyHeadersIfAbsent(original.getHeaders())
            .build();

        System.out.println("original.payload=" + original.getPayload());
        System.out.println("validated.payload=" + validated.getPayload());
        System.out.println("validated.eventType="
            + validated.getHeaders().get("eventType"));
        System.out.println("validated.correlationId="
            + validated.getHeaders().get("correlationId"));
        System.out.println("validated.processingStage="
            + validated.getHeaders().get("processingStage"));
        System.out.println("original.processingStage="
            + original.getHeaders().get("processingStage"));
        System.out.println("description.payload=" + description.getPayload());
        System.out.println("description.eventType="
            + description.getHeaders().get("eventType"));
        System.out.println("description.representation="
            + description.getHeaders().get("representation"));
        System.out.println("localEvent.eventType="
            + localEvent.getHeaders().get("eventType"));
    }
}
~~~

Chạy lệnh sau tại thư mục chứa `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

Kết quả stdout:

~~~text
original.payload=order-42
validated.payload=order-42
validated.eventType=order.validated
validated.correlationId=req-17
validated.processingStage=validation
original.processingStage=null
description.payload=Đơn hàng order-42 đã được tạo
description.eventType=order.created
description.representation=text
localEvent.eventType=local.event
~~~

Kết quả cho thấy:
- `validated` giữ payload và correlation ID từ message nguồn, đồng thời có header riêng cho bước xử lý.
- `original.processingStage` vẫn là `null`; builder không thêm header vào message nguồn.
- `description` có payload mới nhưng vẫn mang các header được sao chép từ `original`.
- `localEvent.eventType` giữ `local.event` vì `copyHeadersIfAbsent` không ghi đè header đã tồn tại.

## 7. Khi nào chọn mỗi factory method?

| Nhu cầu | Cách viết |
| --- | --- |
| Tạo message từ dữ liệu mới | `MessageBuilder.withPayload(payload).build()` |
| Tạo message và thêm metadata | `withPayload(payload).setHeader(...).build()` |
| Giữ nguyên payload, bổ sung hoặc sửa headers | `MessageBuilder.fromMessage(source).setHeader(...).build()` |
| Đổi payload nhưng giữ metadata | `MessageBuilder.withPayload(newPayload).copyHeaders(source.getHeaders()).build()` |
| Chỉ nhận headers chưa có trong builder | `withPayload(payload).copyHeadersIfAbsent(source.getHeaders()).build()` |
| Xóa header trước khi chuyển tiếp | `MessageBuilder.fromMessage(source).removeHeader("internalNote").build()` |

Không dùng `fromMessage` để thay payload; phương thức đó lấy payload từ message nguồn. Cũng không sửa map trả về từ `getHeaders()`; hãy tạo message mới bằng builder.

Trong implementation Spring Framework 7.0.10, nếu builder từ `fromMessage` không bị thay đổi, `build()` có thể trả lại chính message nguồn như một tối ưu. Nếu builder đã thay đổi headers, `build()` tạo message phù hợp với payload và headers đã chuẩn bị. Không nên dùng phép so sánh object identity để suy luận ý nghĩa nghiệp vụ; hãy kiểm tra payload và headers cần thiết.

## 8. Lỗi thường gặp

| Lỗi | Vì sao xảy ra | Cách sửa |
| --- | --- | --- |
| Gọi `message.getHeaders().put(...)` | `MessageHeaders` bất biến | Dùng `MessageBuilder.fromMessage(message).setHeader(...).build()` |
| Dùng `fromMessage` nhưng mong payload mới | `fromMessage` giữ payload nguồn | Dùng `withPayload(newPayload)` |
| Header bị ghi đè ngoài dự kiến | `copyHeaders` ghi đè giá trị đã có | Đổi thứ tự gọi hoặc dùng `copyHeadersIfAbsent` |
| Gọi `setHeader(name, null)` để lưu giá trị null | Giá trị null có nghĩa xóa header | Dùng một giá trị biểu diễn rõ ràng nếu nghiệp vụ cần trạng thái rỗng |
| Cố đặt `id` hoặc `timestamp` tùy ý | Đây là header hệ thống do Spring quản lý | Dùng `correlationId` hoặc header nghiệp vụ riêng |
| Cho rằng payload được clone khi gọi `fromMessage` | Builder tái sử dụng tham chiếu payload | Tạo payload bất biến hoặc tạo đối tượng mới khi cần biến đổi |
| Dùng chung header value mutable | Việc sao chép headers không clone sâu từng giá trị | Ưu tiên value object bất biến và collection không thể sửa |

## 9. Checklist sử dụng

- [ ] Chọn `withPayload` khi bắt đầu từ payload mới.
- [ ] Chọn `fromMessage` khi muốn giữ payload và kế thừa headers.
- [ ] Dùng `withPayload(newPayload).copyHeaders(source.getHeaders())` khi cần thay payload nhưng giữ metadata.
- [ ] Xác định rõ thứ tự giữa `setHeader`, `copyHeaders` và `copyHeadersIfAbsent`.
- [ ] Dùng header nghiệp vụ riêng cho correlation và tracing.
- [ ] Không sửa trực tiếp `MessageHeaders`.
- [ ] Tránh chia sẻ payload hoặc header value có thể bị thay đổi.
- [ ] Kiểm tra cả payload và headers sau khi gọi `build()`.

## 10. Tài liệu tham khảo

- [Spring Framework API — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework API — Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html)
- [Spring Framework API — MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework API — MessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Framework API — GenericMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/GenericMessage.html)
