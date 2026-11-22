# Sao chép thông điệp khi cần thay đổi dữ liệu hoặc header trong Spring Messaging

Trong Spring Messaging, một message gồm **payload** (dữ liệu chính) và **headers** (metadata đi kèm). Khi cần đổi payload hoặc một header, cách làm an toàn là tạo một message mới dựa trên message cũ. Spring cung cấp `MessageBuilder` và `MessageHeaderAccessor` để thực hiện việc đó.

Nội dung này tập trung vào module `spring-messaging` của Spring Framework. Các ví dụ dùng Java 17+ và Spring Framework 7.0.10.

## 1. Vì sao cần tạo message mới?

`Message<T>` cung cấp hai thao tác đọc là `getPayload()` và `getHeaders()`. `MessageHeaders` là một map bất biến: gọi `put()`, `putAll()`, `remove()` hoặc `clear()` trên map này sẽ ném `UnsupportedOperationException`.

Ví dụ sau không phải cách cập nhật header hợp lệ:

```java
message.getHeaders().put("priority", 5); // UnsupportedOperationException
```

Thay vào đó, tạo message mới bằng builder. Message ban đầu tiếp tục giữ nguyên payload và headers của nó; message mới chứa các thay đổi mong muốn.

Cần phân biệt hai mức bất biến:

- **Vỏ message và map headers:** Spring cung cấp chúng theo cách bất biến sau khi được tạo.
- **Đối tượng payload và giá trị header:** các đối tượng này có thể vẫn mutable. Spring không tự deep-copy một DTO, danh sách hoặc map nằm bên trong message.

Vì vậy, tạo message mới không đồng nghĩa mọi đối tượng bên trong nó đã được sao chép sâu.

## 2. Chọn cách sao chép phù hợp

| Nhu cầu | Cách tạo message | Kết quả |
| --- | --- | --- |
| Giữ payload, đổi hoặc thêm header | `MessageBuilder.fromMessage(source)` | Builder bắt đầu với payload và headers của message nguồn |
| Thay payload, giữ metadata | `MessageBuilder.withPayload(newPayload).copyHeaders(source.getHeaders())` | Payload mới, headers được sao chép |
| Chỉ bổ sung header còn thiếu | `copyHeadersIfAbsent(...)` | Giá trị đã có trong builder được giữ nguyên |
| Xóa một header | `removeHeader(name)` | Header được loại khỏi message mới |
| Xóa nhóm header | `removeHeaders(patterns...)` | Các header khớp mẫu bị loại khỏi message mới |

### Giữ payload và thay đổi header

Dùng `fromMessage` khi payload vẫn đúng và chỉ cần thay metadata:

```java
Message<Order> updated = MessageBuilder
        .fromMessage(original)
        .setHeader("priority", 5)
        .setHeader("processedBy", "billing")
        .build();
```

`fromMessage` tạo builder cho một message mới, sao chép payload và headers từ message nguồn. Các lời gọi `setHeader` sau đó thay đổi bản dựng mới; chúng không cập nhật message gốc.

### Thay payload nhưng giữ headers

Khi kiểu hoặc nội dung payload thay đổi, tạo builder từ payload mới rồi sao chép headers:

```java
Message<OrderValidated> updated = MessageBuilder
        .withPayload(new OrderValidated("ORD-42", true))
        .copyHeaders(original.getHeaders())
        .build();
```

Cách này hữu ích khi một bước xử lý chuyển DTO đầu vào thành DTO đầu ra nhưng vẫn cần giữ trace ID, tenant ID hoặc metadata nghiệp vụ.

### Thay payload và điều chỉnh metadata

Có thể nối các thao tác trên cùng builder:

```java
Message<OrderValidated> updated = MessageBuilder
        .withPayload(new OrderValidated("ORD-42", true))
        .copyHeaders(original.getHeaders())
        .setHeader("stage", "validation")
        .removeHeader("temporaryFlag")
        .build();
```

Thứ tự thao tác rất quan trọng khi một header xuất hiện nhiều lần. `copyHeaders` ghi đè giá trị cùng tên đã có trong builder; `copyHeadersIfAbsent` chỉ điền giá trị nếu builder chưa có header đó.

Ví dụ, nếu muốn ưu tiên giá trị mặc định của bước hiện tại:

```java
Message<?> updated = MessageBuilder
        .withPayload(newPayload)
        .setHeader("source", "local")
        .copyHeadersIfAbsent(original.getHeaders())
        .build();
```

Nếu message nguồn có `source=checkout`, message mới vẫn giữ `source=local`, vì header đã được đặt trước khi sao chép.

### Xóa header

Có thể dùng `removeHeader` hoặc đặt giá trị `null`:

```java
Message<?> withoutPriority = MessageBuilder
        .fromMessage(original)
        .removeHeader("priority")
        .build();

Message<?> withoutTemporaryFlag = MessageBuilder
        .fromMessage(original)
        .setHeader("temporaryFlag", null)
        .build();
```

`setHeader(name, null)` có nghĩa là xóa header, không phải lưu một giá trị null. `removeHeaders` hỗ trợ mẫu tên như `trace*`, `*Token` hoặc `*internal*`; hãy dùng mẫu đủ hẹp để tránh xóa metadata cần thiết.

## 3. Ví dụ Java hoàn chỉnh

Ví dụ sau minh họa năm tình huống: thay header, thay payload và giữ headers, chỉ sao chép header còn thiếu, xóa header và dùng `MessageHeaderAccessor`. Payload là một Java record để dữ liệu minh họa bất biến.

Tạo file `src/main/java/MessageCopyDemo.java`:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.support.MessageHeaderAccessor;

public class MessageCopyDemo {

    private record OrderPayload(String orderId, String status) {}

    public static void main(String[] args) {
        Message<OrderPayload> original = MessageBuilder
                .withPayload(new OrderPayload("ORD-42", "CREATED"))
                .setHeader("traceId", "trace-42")
                .setHeader("priority", 3)
                .setHeader("source", "checkout")
                .build();

        // Giữ payload, thay priority và thêm processedBy.
        Message<OrderPayload> headerChanged = MessageBuilder
                .fromMessage(original)
                .setHeader("priority", 5)
                .setHeader("processedBy", "billing")
                .build();

        // Tạo payload mới, sao chép metadata rồi thêm stage.
        Message<OrderPayload> payloadChanged = MessageBuilder
                .withPayload(new OrderPayload(
                        original.getPayload().orderId(), "VALIDATED"))
                .copyHeaders(original.getHeaders())
                .setHeader("stage", "validation")
                .build();

        // Giá trị source=local được ưu tiên; chỉ sao chép header còn thiếu.
        Message<OrderPayload> localDefaults = MessageBuilder
                .withPayload(original.getPayload())
                .setHeader("source", "local")
                .copyHeadersIfAbsent(original.getHeaders())
                .build();

        // Xóa priority khỏi message mới.
        Message<OrderPayload> stripped = MessageBuilder
                .fromMessage(original)
                .removeHeader("priority")
                .build();

        // Dùng accessor mutable để sửa headers rồi tạo message mới.
        MessageHeaderAccessor accessor =
                MessageHeaderAccessor.getMutableAccessor(original);
        accessor.setHeader("auditedBy", "audit-service");

        Message<OrderPayload> accessorCopy = MessageBuilder
                .withPayload(original.getPayload())
                .setHeaders(accessor)
                .build();

        System.out.println("original status: " + original.getPayload().status());
        System.out.println("original priority: " + original.getHeaders().get("priority"));
        System.out.println("headerChanged status: " + headerChanged.getPayload().status());
        System.out.println("headerChanged priority: "
                + headerChanged.getHeaders().get("priority"));
        System.out.println("headerChanged processedBy: "
                + headerChanged.getHeaders().get("processedBy"));
        System.out.println("payloadChanged status: "
                + payloadChanged.getPayload().status());
        System.out.println("payloadChanged traceId: "
                + payloadChanged.getHeaders().get("traceId"));
        System.out.println("localDefaults source: "
                + localDefaults.getHeaders().get("source"));
        System.out.println("stripped priority: "
                + stripped.getHeaders().get("priority"));
        System.out.println("accessorCopy auditedBy: "
                + accessorCopy.getHeaders().get("auditedBy"));
        System.out.println("original priority after copies: "
                + original.getHeaders().get("priority"));
        System.out.println("same payload reference after fromMessage: "
                + (original.getPayload() == headerChanged.getPayload()));
    }
}
```

Tạo `pom.xml` ở thư mục gốc của project Maven:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>message-copy-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>MessageCopyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Kết quả stdout:

```text
original status: CREATED
original priority: 3
headerChanged status: CREATED
headerChanged priority: 5
headerChanged processedBy: billing
payloadChanged status: VALIDATED
payloadChanged traceId: trace-42
localDefaults source: local
stripped priority: null
accessorCopy auditedBy: audit-service
original priority after copies: 3
same payload reference after fromMessage: true
```

Dòng cuối cho thấy `fromMessage` giữ nguyên tham chiếu payload. Trong ví dụ, payload là record nên không thể sửa trạng thái tại chỗ. Nếu payload là một `ArrayList`, `HashMap` hoặc DTO mutable, hai message có thể cùng trỏ đến một đối tượng và nhìn thấy thay đổi của nhau.

## 4. Dùng MessageHeaderAccessor khi cần kiểm soát headers

`MessageHeaderAccessor` là lớp hỗ trợ đọc và thay đổi headers có kiểm soát. Nó hữu ích khi cần truy cập các header theo kiểu cụ thể hoặc làm việc với accessor chuyên biệt như `NativeMessageHeaderAccessor` và các accessor cho giao thức.

`MessageHeaderAccessor.getMutableAccessor(message)` tạo một accessor có thể sửa đổi headers của message. Sau khi cập nhật, có thể đưa accessor vào `MessageBuilder.setHeaders(accessor)` để xây dựng message mới:

```java
MessageHeaderAccessor accessor =
        MessageHeaderAccessor.getMutableAccessor(original);

accessor.setHeader("processedBy", "billing");

Message<?> updated = MessageBuilder
        .withPayload(original.getPayload())
        .setHeaders(accessor)
        .build();
```

Theo mặc định, khi gọi `getMessageHeaders()`, accessor khóa việc sửa đổi tiếp và trả về headers bất biến. `setLeaveMutable(true)` cho phép tiếp tục sửa headers sau khi lấy `MessageHeaders`, nhưng chỉ nên dùng trong giai đoạn khởi tạo message trên cùng một thread. Khi hoàn tất, gọi `setImmutable()` trước khi chuyển message sang thành phần hoặc thread khác.

Với các trường hợp thông thường, `MessageBuilder.fromMessage` và `withPayload(...).copyHeaders(...)` thường dễ đọc và ít trạng thái hơn. Dùng accessor khi cần khả năng đặc thù của nó, nhất là khi muốn giữ kiểu accessor của giao thức.

## 5. ID, timestamp và correlation ID

Một message có các header hệ thống như `MessageHeaders.ID` và `MessageHeaders.TIMESTAMP`.

- `ID` là UUID nhận diện một message instance. Spring tự sinh ID; không nên tự đặt giá trị này trong header.
- `TIMESTAMP` do cơ chế tạo headers của Spring quản lý. Việc tự sao chép headers không ghi đè các giá trị hệ thống read-only này.
- `copyHeaders` và `copyHeadersIfAbsent` không ghi đè `id` hoặc `timestamp`.

Khi tạo message mới từ message cũ, hãy xem đó là một message instance mới. Nếu cần liên kết nhiều message trong cùng một nghiệp vụ, dùng header riêng như `correlationId`, `traceId` hoặc `businessRequestId`. Ví dụ, message đầu tiên và message sau bước validation có thể có ID khác nhau nhưng cùng giữ `traceId=trace-42`.

Không dùng `MessageHeaders.ID` làm correlation ID nghiệp vụ. ID định danh message; correlation ID liên kết các message có quan hệ với nhau.

## 6. Sao chép headers không phải deep copy

Các phương thức `fromMessage`, `copyHeaders` và `copyHeadersIfAbsent` sao chép các cặp tên-giá trị của headers. Việc sao chép này không tự nhân bản sâu đối tượng được tham chiếu.

Ví dụ, nếu header chứa một danh sách mutable:

```java
List<String> tags = new ArrayList<>(List.of("priority"));
Message<?> source = MessageBuilder
        .withPayload("order")
        .setHeader("tags", tags)
        .build();

Message<?> copy = MessageBuilder
        .fromMessage(source)
        .build();
```

Header map của `source` và `copy` là hai bộ headers của message, nhưng giá trị `tags` vẫn có thể là cùng một đối tượng danh sách. Sửa danh sách đó có thể ảnh hưởng đến cả hai message. Nếu cần cách ly dữ liệu, hãy tạo bản sao của danh sách hoặc đối tượng header trước khi gắn nó vào builder.

Điều tương tự áp dụng cho payload. Nếu payload mutable và bước xử lý sau cần thay đổi nội dung, hãy tạo DTO mới hoặc defensive copy thay vì sửa payload đang được chia sẻ giữa các thành phần.

## 7. Chú ý khi sao chép toàn bộ headers

`copyHeaders(original.getHeaders())` tiện lợi nhưng sao chép mọi header có thể sao chép được. Một số header mang ngữ cảnh định tuyến hoặc giao thức, ví dụ:

- `contentType`: có thể không còn đúng nếu payload đổi định dạng.
- `replyChannel` và `errorChannel`: có thể không còn phù hợp nếu message chuyển sang một luồng khác.
- Header riêng của broker, WebSocket/STOMP hoặc adapter: có thể chỉ có ý nghĩa trong ngữ cảnh nguồn.
- Header tạm dùng trong một bước xử lý: có thể không nên truyền tiếp sang bước sau.

Khi tạo message cho một destination hoặc payload mới, kiểm tra header nào còn hợp lệ. Nếu chỉ cần một vài metadata, hãy sao chép có chọn lọc:

```java
Message<?> outbound = MessageBuilder
        .withPayload(newPayload)
        .setHeader("traceId", original.getHeaders().get("traceId"))
        .setHeader("tenantId", original.getHeaders().get("tenantId"))
        .setHeader("contentType", "application/json")
        .build();
```

Ví dụ này giữ lại hai header cần thiết và đặt lại content type theo payload mới. Trong ứng dụng thực tế, nên khai báo tên custom header thành hằng số để tránh sai chính tả giữa producer và consumer.

## 8. Lỗi thường gặp

1. **Gọi `put` hoặc `remove` trực tiếp trên `MessageHeaders`.** Map headers bất biến; dùng builder hoặc accessor.
2. **Dùng `fromMessage` rồi nghĩ rằng payload đã được clone.** Builder vẫn dùng tham chiếu payload cũ.
3. **Dùng `withPayload(newPayload)` mà quên sao chép metadata cần thiết.** Trace ID hoặc tenant ID có thể bị mất.
4. **Dùng `copyHeaders` sau khi đặt giá trị ưu tiên.** Header nguồn sẽ ghi đè header cùng tên trong builder. Nếu muốn giữ giá trị hiện có, dùng `copyHeadersIfAbsent`.
5. **Sao chép tất cả headers sang một luồng khác.** Có thể giữ lại content type, reply channel hoặc metadata giao thức đã lỗi thời.
6. **Cố ghi đè ID hoặc timestamp.** Đây là các header hệ thống read-only.
7. **Dùng message ID làm ID xuyên suốt một nghiệp vụ.** Tạo message mới có thể tạo ID mới; dùng correlation ID riêng.
8. **Giữ payload hoặc giá trị header mutable dùng chung giữa nhiều message.** Thay đổi một đối tượng có thể ảnh hưởng đến các message khác đang tham chiếu nó.

## 9. Checklist trước khi gửi message mới

- Xác định cần đổi payload, header hay cả hai.
- Dùng `fromMessage` khi giữ payload; dùng `withPayload` khi thay payload.
- Dùng `copyHeaders` để ưu tiên metadata nguồn; dùng `copyHeadersIfAbsent` để giữ các giá trị đã đặt trong builder.
- Xóa hoặc cập nhật content type, reply/error channel và metadata giao thức nếu chúng không còn đúng.
- Giữ correlation ID hoặc trace ID bằng header nghiệp vụ riêng.
- Defensive-copy payload và giá trị header mutable nếu cần tách biệt dữ liệu.
- Tạo message hoàn chỉnh trước khi gửi sang channel hoặc thread khác.

## 10. Tài liệu tham khảo

- [Spring Framework – MessageBuilder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework – MessageHeaders Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework – MessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Framework – Message Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html)
