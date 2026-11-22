# MessageBuilder.withPayload

Trong chương `MessageBuilder` của module `SPRING_INTEGRATION_CORE`, `withPayload` là điểm khởi đầu để đưa dữ liệu nghiệp vụ vào một thông điệp. Khi nắm được cách tạo `Message<T>` đúng kiểu và gắn metadata phù hợp, bạn có thể đưa thông điệp vào channel, gateway và các endpoint như transformer, router, filter hoặc aggregator.

Bài này tập trung vào việc khởi tạo message, các giới hạn của thao tác đó và cách quan sát kết quả trong một luồng Java DSL. Ví dụ sử dụng mã đơn hàng để giữ trọng tâm ở cơ chế messaging, thay vì chi tiết nghiệp vụ.

## 1. Mục tiêu và điều kiện thực hành

Sau bài học, bạn có thể:

- Phân biệt payload, builder và message đã được tạo.
- Dùng `MessageBuilder.withPayload(payload).build()` với kiểu dữ liệu rõ ràng.
- Gắn header mà không làm thay đổi ý nghĩa hay kiểu của payload.
- Xử lý đầu vào `null` và tránh thay đổi dữ liệu dùng chung sau khi gửi message.
- Chọn giữa `withPayload`, `fromMessage` và việc sao chép header.
- Gửi message vào một `IntegrationFlow` và kiểm tra payload cùng header đầu ra.

Các ví dụ dùng Java 17 trở lên, Spring Integration 6.4.x và JUnit Jupiter. API `MessageBuilder` được đối chiếu với bản 6.4.9 để có một mốc tham chiếu cụ thể; đây không phải yêu cầu nâng cấp dự án. Cần có `spring-integration-core` trên classpath; khi chạy các ví dụ kiểm thử, cần thêm JUnit Jupiter và cấu hình chạy JUnit Platform. Với dự án Spring Boot đã quản lý dependency, dùng các phiên bản tương thích do dự án lựa chọn.

## 2. `withPayload` tạo builder, `build` tạo message

Import sử dụng xuyên suốt bài:

```java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;
```

Chữ ký factory method:

```java
public static <T> MessageBuilder<T> withPayload(T payload)
```

`T` là kiểu của payload. Lời gọi trả về `MessageBuilder<T>`, cho phép tiếp tục gắn header trước khi gọi `build()` để nhận `Message<T>`. Đây là factory method tĩnh, có thể dùng ngoài Spring ApplicationContext. [Javadoc MessageBuilder của Spring Integration](https://docs.spring.io/spring-integration/docs/6.4.9/api/org/springframework/integration/support/MessageBuilder.html).

Ví dụ sau có thể đặt trong một phương thức Java với hai import trên:

```java
MessageBuilder<String> builder = MessageBuilder.withPayload("ord-2026-001");

Message<String> message = builder
        .setHeader("sourceSystem", "web-checkout")
        .setHeader("traceId", "trace-001")
        .build();

String orderCode = message.getPayload();
String source = message.getHeaders().get("sourceSystem", String.class);

System.out.println(orderCode); // ord-2026-001
System.out.println(source);    // web-checkout
```

Có thể viết gọn khi không cần giữ biến builder:

```java
Message<String> message = MessageBuilder
        .withPayload("ord-2026-001")
        .setHeader("sourceSystem", "web-checkout")
        .build();
```

Quá trình gồm ba bước riêng:

```mermaid
flowchart LR
    A["Dữ liệu: ord-2026-001"] -->|withPayload| B["MessageBuilder&lt;String&gt;"]
    B -->|setHeader| C["Builder có metadata"]
    C -->|build| D["Message&lt;String&gt;"]
    D -->|channel.send| E["Endpoint trong luồng tích hợp"]
```

Tạo message chưa có nghĩa là đã gửi message. Builder không chọn channel, không gọi endpoint và không thực thi nghiệp vụ của consumer.

Trong hệ sinh thái Spring có hai lớp cùng tên:

| Tên đầy đủ | Vai trò trong phạm vi bài |
| --- | --- |
| `org.springframework.integration.support.MessageBuilder` | Builder dùng cho các ví dụ Spring Integration ở đây; có các tiện ích header đặc thù của Integration. |
| `org.springframework.messaging.support.MessageBuilder` | Builder thuộc Spring Framework, cũng có `withPayload`, nhưng tập phương thức không hoàn toàn giống lớp trên. |

IDE có thể tự thêm import thứ hai khi bạn gõ tên lớp. Hãy kiểm tra package trước khi dùng các phương thức như `setCorrelationId` hoặc `setSequenceNumber`. `Message` trong cả hai trường hợp là interface thuộc `org.springframework.messaging`. [Javadoc builder của Spring Framework](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/MessageBuilder.html).

## 3. Payload giữ kiểu dữ liệu bạn truyền vào

### 3.1. Kiểu đơn giản và đối tượng nghiệp vụ

Payload có thể là chuỗi, số, mảng byte hoặc một đối tượng nghiệp vụ:

```java
Message<String> textMessage = MessageBuilder.withPayload("ord-2026-001").build();
Message<Integer> countMessage = MessageBuilder.withPayload(3).build();
Message<byte[]> binaryMessage = MessageBuilder.withPayload(new byte[] {10, 20}).build();
```

Ví dụ với một kiểu nghiệp vụ, đặt record sau trong class hoặc trong phạm vi phù hợp:

```java
record OrderRequest(String orderCode, int quantity) {
}
```

Khi đó:

```java
OrderRequest request = new OrderRequest("ord-2026-001", 3);

Message<OrderRequest> message = MessageBuilder.withPayload(request)
        .setHeader("sourceSystem", "web-checkout")
        .build();

int quantity = message.getPayload().quantity(); // 3
```

Builder không kiểm tra các quy tắc như `quantity > 0` hay định dạng mã đơn. Những ràng buộc đó cần được thực hiện ở bước xác thực nghiệp vụ phù hợp.

### 3.2. Kiểu biến đầu vào ảnh hưởng đến suy luận generic

Nếu khai báo biến payload là `Object`, compiler chỉ biết kiểu tĩnh đó:

```java
Object rawPayload = "ord-2026-001";

Message<Object> message = MessageBuilder.withPayload(rawPayload).build();
```

Payload thực tế vẫn là một `String`, nhưng kiểu biến message là `Message<Object>`. Giữ kiểu cụ thể khi bạn đã biết hợp đồng dữ liệu:

```java
String orderCode = "ord-2026-001";
Message<String> message = MessageBuilder.withPayload(orderCode).build();
```

Generic giúp kiểm tra code ở thời điểm biên dịch. Nó không cấu hình cơ chế chuyển đổi dữ liệu cho toàn bộ integration flow. Ngoài ra, `Message<String>` không phải kiểu con của `Message<Object>`; dùng `Message<?>` khi chỉ cần đọc một message có payload chưa biết kiểu.

### 3.3. `null` khác dữ liệu rỗng

`withPayload(null)` bị từ chối bằng `IllegalArgumentException` ngay khi tạo builder trong triển khai mặc định được tham chiếu. Lỗi xảy ra trước `build()` và trước khi gửi vào channel. [Mã nguồn BaseMessageBuilder 6.4.9](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.4.9/spring-integration-core/src/main/java/org/springframework/integration/support/BaseMessageBuilder.java).

```java
// Không hợp lệ: phát sinh IllegalArgumentException.
MessageBuilder.<String>withPayload(null);
```

Một chuỗi rỗng hoặc danh sách rỗng vẫn là một đối tượng khác `null`:

```java
Message<String> emptyText = MessageBuilder.withPayload("").build();

Message<java.util.List<String>> emptyItems = MessageBuilder
        .withPayload(java.util.List.<String>of())
        .build();
```

Việc chấp nhận dữ liệu rỗng là quyết định nghiệp vụ. Ví dụ, hệ thống tìm kiếm có thể cho phép kết quả là danh sách rỗng, nhưng luồng tiếp nhận đơn hàng có thể yêu cầu danh sách mặt hàng phải có phần tử. Không thay `null` bằng chuỗi rỗng chỉ để vượt qua điều kiện của builder khi điều đó làm sai ý nghĩa dữ liệu.

## 4. Payload và header có nhiệm vụ khác nhau

Payload chứa dữ liệu mà endpoint xử lý; header cung cấp ngữ cảnh phục vụ việc xử lý hoặc chuyển tiếp. Ví dụ dưới đây đặt mã đơn trong payload và thông tin nguồn gửi trong header:

```java
Message<String> message = MessageBuilder.withPayload("ord-2026-001")
        .setHeader("sourceSystem", "web-checkout")
        .setHeader("traceId", "trace-001")
        .setHeader("schemaVersion", 1)
        .build();

String traceId = message.getHeaders().get("traceId", String.class);
Integer schemaVersion = message.getHeaders().get("schemaVersion", Integer.class);
```

| Dữ liệu | Vị trí trong ví dụ | Lý do |
| --- | --- | --- |
| Mã đơn cần chuẩn hóa | Payload | Là đối tượng xử lý chính của transformer. |
| Hệ thống nguồn | Header `sourceSystem` | Cung cấp ngữ cảnh tiếp nhận. |
| Mã theo dõi | Header `traceId` | Giúp liên kết log qua nhiều bước. |
| Phiên bản hợp đồng | Header `schemaVersion` | Giúp consumer hiểu phiên bản dữ liệu. |

Dùng cách đọc header có tham số kiểu giúp phát hiện sai hợp đồng rõ hơn việc ép kiểu rải rác. Header không tồn tại sẽ cho kết quả `null`; nếu tên tồn tại nhưng giá trị không đúng kiểu yêu cầu, lời gọi đọc có kiểu sẽ báo lỗi. [Javadoc MessageHeaders](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/MessageHeaders.html).

Việc đặt `contentType` chỉ thêm metadata. Chẳng hạn, đoạn sau vẫn tạo payload là `OrderRequest`, không tạo JSON:

```java
Message<OrderRequest> message = MessageBuilder
        .withPayload(new OrderRequest("ord-2026-001", 3))
        .setHeader(org.springframework.messaging.MessageHeaders.CONTENT_TYPE,
                org.springframework.util.MimeTypeUtils.APPLICATION_JSON)
        .build();
```

Chỉ dùng metadata như vậy khi nó đúng với hợp đồng tại điểm sử dụng. Nếu phía nhận cần JSON dạng chuỗi hoặc byte, phải có bước serialize/transform thực sự. Việc chuyển đổi dữ liệu thuộc trách nhiệm của transformer hoặc thành phần chuyển đổi được cấu hình, không nằm trong factory method `withPayload`. [Tài liệu Transformer](https://docs.spring.io/spring-integration/reference/transformer.html).

## 5. Tính bất biến của message không phải sao chép sâu

### 5.1. Không sửa trực tiếp cấu trúc header sau khi build

`Message` cung cấp cách đọc payload và headers. Với message mặc định, không thể thay payload bằng một setter hay sửa map header qua `put`:

```java
Message<String> message = MessageBuilder.withPayload("ord-2026-001")
        .setHeader("sourceSystem", "web-checkout")
        .build();

// Phát sinh UnsupportedOperationException:
message.getHeaders().put("sourceSystem", "batch-import");
```

Nếu cần một phiên bản với header khác, tạo message qua builder thay vì sửa map đang được chia sẻ. [Javadoc GenericMessage](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/GenericMessage.html).

### 5.2. Đối tượng payload vẫn có thể thay đổi

Builder giữ tham chiếu đến payload, không tự clone toàn bộ đồ thị đối tượng. Ví dụ sau dùng tên lớp đầy đủ để thấy rõ cấu trúc dữ liệu:

```java
java.util.List<String> items = new java.util.ArrayList<>();
items.add("book");

Message<java.util.List<String>> message = MessageBuilder
        .withPayload(items)
        .build();

items.add("pen");

System.out.println(message.getPayload()); // [book, pen]
```

Message vẫn trỏ tới cùng danh sách. Điều này cần được chú ý khi có nhiều consumer hoặc khi việc xử lý diễn ra trên thread khác. Tương tự, một header có giá trị là danh sách hay đối tượng có setter vẫn có thể bị sửa từ bên ngoài. [Tài liệu Message và giới hạn của tính bất biến](https://docs.spring.io/spring-integration/reference/message.html).

Với danh sách chuỗi trong ví dụ, có thể chụp dữ liệu trước khi build:

```java
java.util.List<String> snapshot = java.util.List.copyOf(items);

Message<java.util.List<String>> message = MessageBuilder
        .withPayload(snapshot)
        .build();
```

`List.copyOf` tạo danh sách không cho phép thêm hoặc xóa phần tử, nhưng không sao chép sâu các phần tử. Nếu phần tử là đối tượng mutable, bạn vẫn phải quyết định cách tạo bản sao hoặc dùng kiểu bất biến. Record cũng không tự làm mọi đối tượng bên trong nó trở nên bất biến.

### 5.3. Builder là đối tượng đang được cấu hình

Các lời gọi như `setHeader` thay đổi trạng thái builder. Nên tạo builder cục bộ cho mỗi lần tạo message, thay vì giữ một builder dùng chung trong service singleton rồi thay header qua nhiều request. Cách dùng cục bộ giúp tránh lẫn metadata giữa các lần gửi và tránh việc nhiều thread cùng sửa trạng thái đang xây dựng.

## 6. Khi nào chọn `withPayload` thay cho `fromMessage`?

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Tạo thông điệp từ dữ liệu đầu vào mới | `withPayload(payload)` rồi thêm các header cần thiết. |
| Giữ payload của message có sẵn và điều chỉnh header | `fromMessage(existingMessage)` rồi cấu hình header. |
| Tạo payload mới trong khi cần tiếp nối ngữ cảnh | `withPayload(newPayload)` rồi chọn và sao chép header phù hợp. |

`withPayload(existingMessage.getPayload())` chỉ nhận đối tượng payload; nó không có tham số message nguồn nên không tự biết các header của message đó. [Mã nguồn MessageBuilder 6.4.9](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.4.9/spring-integration-core/src/main/java/org/springframework/integration/support/MessageBuilder.java).

Ví dụ thay payload nhưng giữ header ứng dụng:

```java
Message<String> original = MessageBuilder.withPayload("  ord-2026-001  ")
        .setHeader("sourceSystem", "web-checkout")
        .setHeader("traceId", "trace-001")
        .build();

String normalizedCode = original.getPayload()
        .strip()
        .toUpperCase(java.util.Locale.ROOT);

Message<String> normalized = MessageBuilder.withPayload(normalizedCode)
        .copyHeaders(original.getHeaders())
        .build();
```

Ở đây, kết quả nghiệp vụ dự kiến là:

```text
payload      = ORD-2026-001
sourceSystem = web-checkout
traceId      = trace-001
```

Sao chép toàn bộ header có thể phù hợp cho một bước tiếp nối trong cùng luồng. Khi phát sinh một sự kiện nghiệp vụ mới, hãy chủ động chọn những metadata cần giữ; không sao chép header điều phối một cách máy móc. Một ví dụ chọn rõ header:

```java
Message<String> event = MessageBuilder.withPayload("order-code-normalized")
        .setHeader("traceId", original.getHeaders().get("traceId"))
        .setHeader("orderCode", normalizedCode)
        .build();
```

Nếu cần giữ giá trị đã đặt trên builder trước khi bổ sung header từ nguồn, dùng `copyHeadersIfAbsent`. Chi tiết chính sách ghi đè thuộc các thao tác header; điểm cần nhớ ở đây là lựa chọn payload mới và lựa chọn metadata là hai quyết định riêng.

### Header hệ thống và định danh nghiệp vụ

Với cấu hình mặc định, message mới có `id` kiểu UUID và `timestamp` kiểu Long. Hai header hệ thống này chỉ đọc; việc sao chép header qua builder không dùng chúng để ép message mới mang định danh cũ. Không dùng timestamp để khẳng định hai message chắc chắn khác thời điểm: chúng có thể được tạo trong cùng một mili giây. [Quy tắc header hệ thống trong Spring Integration](https://docs.spring.io/spring-integration/reference/7.0/message.html).

Nếu cần liên kết nhiều bước theo cùng một yêu cầu, dùng header ứng dụng như `traceId` hoặc một correlation key theo hợp đồng của luồng. Đừng đồng nhất `MessageHeaders.ID` với mã đơn hàng hay khóa chống xử lý trùng.

Riêng `fromMessage(message).build()` có thể trả lại chính đối tượng nguồn khi không có thay đổi cần áp dụng. Vì vậy, không dựa vào thao tác này để buộc tạo một message có ID mới. Trong luồng tùy biến cách tạo message, cũng cần xem cấu hình factory thay vì giả định mọi lời gọi builder đều có cùng chính sách. [Triển khai build trong BaseMessageBuilder](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.4.9/spring-integration-core/src/main/java/org/springframework/integration/support/BaseMessageBuilder.java).

## 7. Message được tạo ra chưa quyết định cách giao nhận

`withPayload` hỗ trợ bước đóng gói dữ liệu. Loại channel và cấu hình endpoint mới quyết định message được xử lý trực tiếp, lưu vào hàng đợi hay chuyển sang thread khác.

Ví dụ gửi trực tiếp vào `DirectChannel` có subscriber sẽ gọi handler trên thread gửi. `QueueChannel` mặc định giữ message trong hàng đợi bộ nhớ để bên nhận lấy ra. Không thể suy ra từ `build()` rằng thông điệp đã được lưu bền vững hoặc hoàn tất nghiệp vụ. [Các triển khai MessageChannel](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Trong ví dụ chuẩn hóa mã đơn ở phần tiếp theo, các trách nhiệm được chia như sau:

| Thành phần | Trách nhiệm |
| --- | --- |
| Producer và `MessageBuilder` | Tạo message có payload ban đầu và header nguồn. |
| Channel đầu vào | Đưa message đến endpoint của flow. |
| Transformer | Chuẩn hóa giá trị payload. |
| Channel đầu ra | Giữ kết quả để kiểm tra bằng `receive`. |

Gateway có thể giúp gọi luồng bằng phương thức Java và che bớt thao tác message/channel khỏi phía gọi. Tuy nhiên, biết cách tạo message tường minh vẫn cần thiết khi kiểm thử hoặc khi producer phải thiết lập metadata cụ thể. Bài này dùng channel trực tiếp để có thể quan sát từng bước.

## 8. Ví dụ Java DSL: chuẩn hóa mã đơn và giữ ngữ cảnh

Cấu hình dưới đây là một class hoàn chỉnh, có thể lưu thành `PayloadFlowConfig.java` trong dự án thực hành. Nếu dự án có package, thêm cùng khai báo package vào class cấu hình và class kiểm thử ở phần sau.

```java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class PayloadFlowConfig {

    @Bean
    public DirectChannel orderCodesIn() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel orderCodesOut() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow normalizeOrderCodeFlow(
            DirectChannel orderCodesIn,
            QueueChannel orderCodesOut) {

        return IntegrationFlow.from(orderCodesIn)
                .<String, String>transform(code ->
                        code.strip().toUpperCase(Locale.ROOT))
                .channel(orderCodesOut)
                .get();
    }
}
```

`IntegrationFlow` là bean mô tả các thành phần cần đăng ký trong ApplicationContext; nó khác với builder dùng để tạo từng message dữ liệu. `.transform(...)` ở đây là một endpoint xử lý payload. [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html).

Để gửi thử, đặt đoạn sau trong một phương thức với các import tương ứng; class kiểm thử ở phần 9 cung cấp đầy đủ import và cách mở context:

```java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(PayloadFlowConfig.class)) {

    DirectChannel input = context.getBean("orderCodesIn", DirectChannel.class);
    QueueChannel output = context.getBean("orderCodesOut", QueueChannel.class);

    Message<String> request = MessageBuilder.withPayload("  ord-2026-001  ")
            .setHeader("sourceSystem", "web-checkout")
            .setHeader("traceId", "trace-001")
            .build();

    boolean sent = input.send(request);
    if (!sent) {
        throw new IllegalStateException("Channel không nhận message");
    }

    Message<?> reply = output.receive(1_000);
    if (reply == null) {
        throw new IllegalStateException("Không có kết quả trong thời gian chờ");
    }

    System.out.println(reply.getPayload());
    System.out.println(reply.getHeaders().get("traceId", String.class));
}
```

Kết quả mong đợi:

```text
ORD-2026-001
trace-001
```

Trong flow này, producer tạo message bằng `withPayload`; việc chuẩn hóa do transformer thực hiện. Với xử lý trả về payload như trên và cấu hình mặc định, header ứng dụng được tiếp nối sang message kết quả. Hãy kiểm tra hành vi đó qua header có ý nghĩa đối với ứng dụng, thay vì so sánh toàn bộ đối tượng message hoặc ID.

Đặt timeout khi lấy dữ liệu ra khỏi queue giúp ví dụ không chờ vô hạn nếu cấu hình không tạo được kết quả. Không dùng `Thread.sleep` để đoán lúc flow đã xử lý xong.

## 9. Kiểm thử hợp đồng của producer và flow

Class sau sử dụng `PayloadFlowConfig` ở phần 8. Đây là mã kiểm thử minh họa để đưa vào dự án thực hành; bài viết không kèm kết quả biên dịch hay chạy test trong repository hiện tại.

```java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MessageBuilderWithPayloadTest {

    @Test
    void buildsTypedPayloadWithApplicationHeaders() {
        Message<String> message = MessageBuilder.withPayload("ord-2026-001")
                .setHeader("sourceSystem", "web-checkout")
                .build();

        assertEquals("ord-2026-001", message.getPayload());
        assertEquals("web-checkout",
                message.getHeaders().get("sourceSystem", String.class));
    }

    @Test
    void rejectsNullBeforeSendingToChannel() {
        assertThrows(IllegalArgumentException.class,
                () -> MessageBuilder.<String>withPayload(null));
    }

    @Test
    void retainsMutablePayloadReference() {
        List<String> items = new ArrayList<>(List.of("book"));
        Message<List<String>> message = MessageBuilder.withPayload(items).build();

        items.add("pen");

        assertSame(items, message.getPayload());
        assertEquals(List.of("book", "pen"), message.getPayload());
    }

    @Test
    void copiedListSeparatesLaterChangesToOriginalCollection() {
        List<String> items = new ArrayList<>(List.of("book"));
        Message<List<String>> message = MessageBuilder
                .withPayload(List.copyOf(items))
                .build();

        items.add("pen");

        assertEquals(List.of("book"), message.getPayload());
    }

    @Test
    void normalizesPayloadAndKeepsTraceIdThroughFlow() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(PayloadFlowConfig.class)) {

            DirectChannel input = context.getBean("orderCodesIn", DirectChannel.class);
            QueueChannel output = context.getBean("orderCodesOut", QueueChannel.class);

            Message<String> request = MessageBuilder.withPayload("  ord-2026-001  ")
                    .setHeader("sourceSystem", "web-checkout")
                    .setHeader("traceId", "trace-001")
                    .build();

            assertTrue(input.send(request));

            Message<?> reply = output.receive(1_000);
            assertNotNull(reply);
            assertEquals("ORD-2026-001", reply.getPayload());
            assertEquals("trace-001", reply.getHeaders().get("traceId", String.class));
            assertEquals("web-checkout",
                    reply.getHeaders().get("sourceSystem", String.class));
            assertEquals("  ord-2026-001  ", request.getPayload());
        }
    }
}
```

Các test quan sát những hành vi khác nhau: dữ liệu đầu vào đúng kiểu, từ chối `null`, giới hạn của tính bất biến, tác dụng của việc chụp danh sách và ngữ cảnh được giữ qua flow. Trong test tích hợp, kiểm tra lại payload ban đầu còn giúp thể hiện rằng transformer tạo kết quả chuẩn hóa mà không thay giá trị payload của request nguồn.

Không kiểm tra UUID cụ thể, thời gian tạo chính xác hoặc chuỗi `toString()` của message. Những giá trị đó không phải hợp đồng nghiệp vụ của ví dụ này.

## 10. Lỗi thường gặp và hướng xử lý

| Hiện tượng hoặc cách viết | Nguyên nhân cần xem xét | Cách xử lý |
| --- | --- | --- |
| Không gán được kết quả `withPayload` vào `Message<T>` | Factory trả về builder. | Gọi `.build()` sau khi cấu hình xong. |
| `IllegalArgumentException` ngay khi tạo builder | Payload là `null`. | Xác thực hoặc biểu diễn trạng thái không có dữ liệu theo hợp đồng nghiệp vụ. |
| Consumer nhận POJO khi đang chờ JSON | Chỉ đặt `contentType`, chưa serialize. | Thêm bước chuyển đổi thực sự và kiểm tra kiểu đầu ra. |
| Không tìm thấy phương thức header đặc thù Integration | Import một lớp `MessageBuilder` khác. | Kiểm tra package import. |
| Không còn `traceId` trong message mới tự tạo | Chỉ đưa payload nguồn vào `withPayload`. | Chọn và sao chép header cần tiếp nối. |
| Payload đổi sau khi gửi | Còn tham chiếu mutable bị sửa từ producer hoặc consumer khác. | Dùng dữ liệu bất biến hoặc tạo bản sao theo hợp đồng. |
| `UnsupportedOperationException` khi thêm header | Đang sửa `message.getHeaders()` của message mặc định. | Tạo message qua builder với header mong muốn. |
| Luồng không tự chạy sau khi build | Chưa gửi vào channel hoặc thiếu cấu hình consumer. | Kiểm tra thao tác gửi và việc đăng ký endpoint. |
| Kiểm thử treo khi nhận kết quả | Gọi `receive()` không giới hạn chờ. | Dùng timeout và kiểm tra trường hợp trả về `null`. |

Lỗi tạo builder nằm ở phía producer, trước khi có message được gửi vào flow. Chỉ đặt một header `errorChannel` không làm lỗi `withPayload(null)` tự trở thành thông điệp lỗi. Xử lý lỗi khi giao nhận còn phụ thuộc channel, gateway và endpoint được sử dụng; cần kiểm tra ở ranh giới thực sự phát sinh lỗi.

Với payload là một `Throwable`, builder mặc định trong bản tham chiếu tạo `ErrorMessage` khi build. Điều này không tự gửi lỗi đến một channel. Trong bài thực hành thông điệp nghiệp vụ, nên dùng DTO hoặc một kiểu kết quả có ý nghĩa rõ ràng thay vì dùng ngoại lệ làm dữ liệu thông thường. [Triển khai nhánh tạo ErrorMessage](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.4.9/spring-integration-core/src/main/java/org/springframework/integration/support/BaseMessageBuilder.java).

## 11. Áp dụng vào các mẫu tích hợp

Khi mở rộng ví dụ từ một transformer sang luồng nhiều bước, hãy quyết định hợp đồng message trước khi viết builder:

- Producer tiếp nhận dữ liệu nào, và kiểu payload consumer cần là gì?
- Header nào theo yêu cầu nghiệp vụ phải tồn tại qua các bước?
- Dữ liệu có còn bị sửa sau khi producer gửi đi không?
- Kết quả mới là một bước tiếp nối của yêu cầu hiện tại hay một sự kiện độc lập?

Ví dụ, router có thể chọn nhánh theo `sourceSystem`; filter có thể loại mã đơn không hợp lệ; aggregator có thể cần một khóa nhóm được giữ nhất quán qua các message liên quan. Các hành vi đó đến từ cấu hình endpoint. Việc đặt header trên một builder chỉ cung cấp dữ liệu đầu vào cho hợp đồng đã thiết kế, không tự tạo các hành vi định tuyến, lọc hay gom nhóm.

Mẫu sử dụng cốt lõi là:

```java
Message<String> request = MessageBuilder.withPayload("ord-2026-001")
        .setHeader("sourceSystem", "web-checkout")
        .setHeader("traceId", "trace-001")
        .build();
```

Một message như vậy sẵn sàng được gửi vào channel khi producer đã xác thực dữ liệu và hiểu rõ cách chia sẻ payload. Việc quan sát cả payload lẫn header trong kiểm thử sẽ giúp phát hiện lỗi hợp đồng sớm hơn việc chỉ nhìn kết quả nghiệp vụ cuối luồng.
