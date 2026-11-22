# setHeaderIfAbsent: bổ sung header mặc định bằng MessageBuilder

Trong chương **MessageBuilder** của module **SPRING_INTEGRATION_CORE**, `setHeaderIfAbsent` giúp bổ sung metadata còn thiếu cho thông điệp trước khi đi vào các endpoint xử lý. Cách làm này hữu ích khi nhiều gateway hoặc adapter cùng gửi dữ liệu vào một luồng: bên gửi được phép cung cấp một số tùy chọn, còn luồng tích hợp bổ sung các giá trị mặc định cần thiết.

Bài học tập trung vào quy tắc giữ giá trị đã có, thứ tự gọi API, cách đưa thao tác này vào Java DSL và cách kiểm thử hành vi. Các ví dụ sử dụng `MessageBuilder` của Spring Integration, API trên nhánh 6.5 và Java 17 trở lên. Phần kiểm thử minh họa dùng JUnit Jupiter 5; dự án cần có `spring-integration-core` và cấu hình JUnit tương ứng để chạy mã.

## 1. Bài toán: thêm mặc định nhưng giữ lựa chọn của bên gửi

Giả sử một luồng tiếp nhận đơn hàng sử dụng hai header tùy biến:

- `locale`: ngôn ngữ dùng khi tạo thông báo, mặc định là `vi-VN`.
- `maxAttempts`: số lần thử tối đa mà thành phần xử lý nghiệp vụ sẽ đọc, mặc định là số nguyên `3`.

Đơn hàng từ website có thể đã mang `locale=en-US`, trong khi đơn hàng từ một tác vụ nội bộ chưa có header này. Quy tắc mong muốn là:

| Message đầu vào | Header sau bước bổ sung mặc định |
| --- | --- |
| Chưa có `locale` | `locale=vi-VN` |
| Đã có `locale=en-US` | Giữ `locale=en-US` |
| Đã có `maxAttempts=5` | Giữ số nguyên `5` |
| Chưa có `maxAttempts` | `maxAttempts` là số nguyên `3` |

`maxAttempts` ở đây là tên header do ứng dụng tự quy ước. Việc thêm header chưa tự cấu hình retry của Spring Integration; một thành phần khác phải chủ động đọc và áp dụng giá trị đó.

Quy tắc bổ sung này phù hợp với bước chuẩn bị dữ liệu trước transformer, filter hoặc router. Nó cũng giúp gateway sử dụng chung một luồng mà vẫn truyền được tùy chọn riêng cho từng yêu cầu.

## 2. API và ý nghĩa của “absent”

Cách gọi trên một `MessageBuilder<T>`:

```java
builder.setHeaderIfAbsent(String headerName, Object headerValue);
```

Phương thức trả về chính builder để tiếp tục nối lời gọi. Nó gán giá trị khi tên header chưa gắn với một giá trị; nếu đã có giá trị thì giữ nguyên. Hành vi này được mô tả trong [Javadoc của BaseMessageBuilder](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/BaseMessageBuilder.html#setHeaderIfAbsent(java.lang.String,java.lang.Object)).

Về mặt quyết định, có thể hình dung như sau; đây là mã giả, không phải đoạn mã nguồn được chép lại:

```text
Đọc giá trị hiện tại của header.
Nếu chưa có giá trị:
    Gán giá trị mặc định.
Nếu đã có giá trị:
    Giữ nguyên.
```

Không có bước đánh giá một giá trị có phù hợp với nghiệp vụ hay không. Bởi vậy, với một header tùy biến thông thường:

| Giá trị đang có | Gọi với mặc định `vi-VN` | Kết quả |
| --- | --- | --- |
| Không có giá trị | `setHeaderIfAbsent("locale", "vi-VN")` | `vi-VN` |
| `en-US` | Như trên | `en-US` |
| Chuỗi rỗng `""` | Như trên | Giữ chuỗi rỗng |
| Chuỗi chỉ có khoảng trắng `"   "` | Như trên | Giữ khoảng trắng |
| Số `0` | Như trên | Giữ số `0` |
| Boolean `false` | Như trên | Giữ `false` |

Cơ chế accessor kiểm tra giá trị hiện tại có phải `null` hay không; nó không dùng quy tắc “falsy” như một số ngôn ngữ khác. Đây là căn cứ cho các trường hợp rỗng, `0` và `false` trong bảng. Xem [MessageHeaderAccessor của Spring Framework 6.2.11](https://github.com/spring-projects/spring-framework/blob/v6.2.11/spring-messaging/src/main/java/org/springframework/messaging/support/MessageHeaderAccessor.java).

Hãy truyền một giá trị mặc định khác `null`. API công bố `headerValue` là tham số không nullable; không nên dùng `null` làm một giá trị đánh dấu “đã có header”. Khi muốn xóa header, hãy dùng `removeHeader` hoặc `setHeader` với giá trị `null`.

Tên header cũng cần thống nhất: `locale` và `Locale` là hai khóa khác nhau. Dùng hằng số trong ứng dụng giúp tránh việc vô tình tạo hai header có cùng ý nghĩa.

### Chọn đúng lớp MessageBuilder

Các ví dụ trong bài dùng:

```java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;
```

Spring Framework cũng cung cấp `org.springframework.messaging.support.MessageBuilder` với phương thức cùng tên. Khi đọc mã hoặc tra tài liệu, cần xem import để xác định builder đang sử dụng; các API mở rộng phục vụ Integration không hoàn toàn giống nhau. Có thể đối chiếu với [Javadoc MessageBuilder của Spring Framework](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html).

## 3. Ví dụ cơ bản: xử lý message mới và message đã tồn tại

Đoạn mã sau tạo một message có lựa chọn riêng của bên gửi, rồi bổ sung những header còn thiếu:

```java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

public class HeaderDefaultsExample {

    public static void main(String[] args) {
        Message<String> incoming = MessageBuilder
                .withPayload("ORDER-1001")
                .setHeader("locale", "en-US")
                .setHeader("source", "website")
                .build();

        Message<String> prepared = MessageBuilder
                .fromMessage(incoming)
                .setHeaderIfAbsent("locale", "vi-VN")
                .setHeaderIfAbsent("maxAttempts", 3)
                .build();

        System.out.println(prepared.getPayload());
        System.out.println(prepared.getHeaders().get("locale"));
        System.out.println(prepared.getHeaders().get("maxAttempts"));
        System.out.println(prepared.getHeaders().get("source"));
        System.out.println(incoming.getHeaders().get("maxAttempts"));
    }
}
```

Kết quả:

```text
ORDER-1001
en-US
3
website
null
```

Trong ví dụ này:

1. `fromMessage(incoming)` khởi tạo builder từ payload và các header của message đầu vào.
2. `locale` đã có nên lựa chọn `en-US` được giữ lại.
3. `maxAttempts` còn thiếu nên được bổ sung với giá trị kiểu `Integer`.
4. Header tùy biến `source` vẫn đi cùng message.
5. Message đầu vào vẫn chưa có `maxAttempts`.

Nếu tạo message mới hoàn toàn, có thể dùng trực tiếp:

```java
Message<String> created = MessageBuilder
        .withPayload("ORDER-1002")
        .setHeaderIfAbsent("locale", "vi-VN")
        .setHeaderIfAbsent("maxAttempts", 3)
        .build();
```

Với message đã tồn tại, `withPayload(incoming.getPayload())` chỉ lấy payload và không tự lấy các header đầu vào. Nếu mục tiêu là bổ sung metadata mà vẫn giữ ngữ cảnh hiện có, `fromMessage` thể hiện đúng ý định. Xem [mã nguồn MessageBuilder 6.5.4](https://github.com/spring-projects/spring-integration/blob/v6.5.4/spring-integration-core/src/main/java/org/springframework/integration/support/MessageBuilder.java).

## 4. So sánh với setHeader và các phương thức copy

Với các header tùy biến được phép ghi, có thể chọn API theo mục đích:

| API | Khi header đã có | Khi header chưa có | Tình huống phù hợp |
| --- | --- | --- | --- |
| `setHeader(name, value)` | Thay bằng giá trị truyền vào | Thêm giá trị | Áp dụng giá trị bắt buộc hoặc kết quả chuẩn hóa |
| `setHeaderIfAbsent(name, value)` | Giữ giá trị hiện có | Thêm giá trị | Bổ sung một mặc định |
| `copyHeaders(map)` | Có thể ghi đè bằng giá trị trong map | Thêm các khóa tương ứng | Áp dụng một tập giá trị có ưu tiên cao hơn |
| `copyHeadersIfAbsent(map)` | Giữ giá trị hiện có | Thêm các khóa còn thiếu | Bổ sung một tập mặc định |

Nếu giá trị truyền cho `setHeader` là `null`, header đó được xóa. Các header hệ thống chỉ đọc có quy tắc riêng và không thuộc trường hợp ghi đè thông thường trong bảng. Các phương thức này được trình bày trong [Javadoc MessageBuilder của Spring Integration 6.1.x](https://docs.spring.io/spring-integration/docs/6.1.x/api/org/springframework/integration/support/MessageBuilder.html).

Ví dụ cùng một đầu vào:

```java
Message<String> incoming = MessageBuilder
        .withPayload("ORDER-1003")
        .setHeader("locale", "en-US")
        .build();

Message<String> forced = MessageBuilder.fromMessage(incoming)
        .setHeader("locale", "vi-VN")
        .build();

Message<String> defaulted = MessageBuilder.fromMessage(incoming)
        .setHeaderIfAbsent("locale", "vi-VN")
        .build();

// forced:    locale = vi-VN
// defaulted: locale = en-US
```

Chọn `setHeaderIfAbsent` khi bên gửi được quyền lựa chọn. Nếu luồng bắt buộc dùng `vi-VN` sau một bước xác định chính sách, `setHeader` thể hiện quy tắc đó rõ hơn.

### Bổ sung nhiều mặc định

```java
import java.util.Map;

Map<String, Object> defaults = Map.of(
        "locale", "vi-VN",
        "maxAttempts", 3,
        "notificationMode", "EMAIL"
);

Message<String> prepared = MessageBuilder
        .fromMessage(incoming)
        .copyHeadersIfAbsent(defaults)
        .build();
```

Tập mặc định nên chứa các header mà bước xử lý này có trách nhiệm quản lý. Ví dụ, nếu một endpoint chỉ chuẩn bị thông báo, việc thêm `locale` và `notificationMode` dễ giải thích hơn việc cùng lúc quyết định các thông tin nhóm của aggregator.

## 5. Thứ tự lời gọi quyết định độ ưu tiên

`setHeaderIfAbsent` xét trạng thái của builder ngay tại thời điểm được gọi. Nó không tạo quy tắc bảo vệ header khỏi những lời gọi ghi đè về sau.

### Giá trị mặc định được gán trước sẽ được giữ

```java
Message<String> firstDefaultWins = MessageBuilder
        .withPayload("ORDER-1004")
        .setHeaderIfAbsent("locale", "vi-VN")
        .setHeaderIfAbsent("locale", "en-US")
        .build();

// locale = vi-VN
```

### setHeader có thể thay giá trị đã được bổ sung

```java
Message<String> overridden = MessageBuilder
        .withPayload("ORDER-1005")
        .setHeaderIfAbsent("locale", "vi-VN")
        .setHeader("locale", "ja-JP")
        .build();

// locale = ja-JP
```

### Các tập mặc định cần được xếp từ ưu tiên cao đến thấp

Giả sử một đơn vị kinh doanh muốn mặc định `locale=th-TH`, còn mặc định chung của hệ thống là `vi-VN`:

```java
Map<String, Object> businessDefaults = Map.of(
        "locale", "th-TH"
);

Map<String, Object> systemDefaults = Map.of(
        "locale", "vi-VN",
        "maxAttempts", 3
);

Message<String> prepared = MessageBuilder
        .fromMessage(incoming)
        .copyHeadersIfAbsent(businessDefaults)
        .copyHeadersIfAbsent(systemDefaults)
        .build();
```

Độ ưu tiên trong ví dụ này là: **giá trị đầu vào → mặc định đơn vị kinh doanh → mặc định hệ thống**. Nếu đầu vào là message `incoming` có `locale=en-US` ở phần trước, kết quả vẫn là `en-US`. Nếu đầu vào không có `locale`, kết quả là `th-TH`.

Một lần `copyHeaders` xuất hiện phía sau có thể thay đổi thứ tự ưu tiên này bằng cách ghi đè header tùy biến. Khi kết quả khác dự kiến, hãy xem toàn bộ chuỗi thao tác trên builder.

## 6. Phân biệt thiếu header với header không hợp lệ

Giả sử quy tắc nghiệp vụ yêu cầu `locale` phải là chuỗi không trắng và chỉ chấp nhận một tập ngôn ngữ nhất định. `setHeaderIfAbsent` chỉ xử lý phần thiếu giá trị; nó không thay thế bước kiểm tra đó.

```java
Message<String> incoming = MessageBuilder
        .withPayload("ORDER-1006")
        .setHeader("locale", "   ")
        .build();

Message<String> prepared = MessageBuilder.fromMessage(incoming)
        .setHeaderIfAbsent("locale", "vi-VN")
        .build();

// locale vẫn là "   ".
```

Ứng dụng cần chọn chính sách cho giá trị không hợp lệ. Ví dụ, nếu chuỗi trắng được coi là chưa chọn ngôn ngữ, có thể chuẩn hóa trước:

```java
import org.springframework.util.StringUtils;

Object rawLocale = incoming.getHeaders().get("locale");
MessageBuilder<String> builder = MessageBuilder.fromMessage(incoming);

if (rawLocale instanceof String text && !StringUtils.hasText(text)) {
    builder.removeHeader("locale");
}

Message<String> prepared = builder
        .setHeaderIfAbsent("locale", "vi-VN")
        .build();
```

Đoạn mã này chỉ xử lý chuỗi trắng. Nếu giá trị là một số hoặc một mã ngôn ngữ ngoài danh sách hỗ trợ, ứng dụng vẫn cần quyết định từ chối hay chuẩn hóa. Trong luồng tích hợp, có thể đặt filter hoặc validator trước bước bổ sung mặc định để thực hiện quyết định đó.

### Kiểu dữ liệu của header tùy biến

```java
Message<String> incoming = MessageBuilder
        .withPayload("ORDER-1007")
        .setHeader("maxAttempts", "5")
        .build();

Message<String> prepared = MessageBuilder.fromMessage(incoming)
        .setHeaderIfAbsent("maxAttempts", 3)
        .build();

Object actual = prepared.getHeaders().get("maxAttempts");
// actual vẫn là String "5", không được chuyển thành Integer.
```

Khi consumer yêu cầu `Integer`, việc đọc một giá trị đang là `String` bằng `get("maxAttempts", Integer.class)` sẽ không tự chuyển đổi và có thể báo `IllegalArgumentException`. Hãy thống nhất hợp đồng kiểu dữ liệu giữa gateway, adapter và endpoint tiêu thụ. Một số header chuẩn còn được accessor kiểm tra kiểu khi gán, chẳng hạn `priority` cần giá trị dạng số; xem [IntegrationMessageHeaderAccessor 6.5.4](https://github.com/spring-projects/spring-integration/blob/v6.5.4/spring-integration-core/src/main/java/org/springframework/integration/IntegrationMessageHeaderAccessor.java).

## 7. Không nhầm với cơ chế tính mặc định khi cần

Trong Java, đối số của lời gọi phương thức được tính trước khi phương thức chạy:

```java
builder.setHeaderIfAbsent("requestId", createRequestId());
```

`createRequestId()` vẫn được gọi dù builder đã có `requestId`. `setHeaderIfAbsent` nhận một `Object`; API này không nhận một `Supplier` để tự trì hoãn việc tạo giá trị.

Nếu việc tính mặc định có chi phí hoặc có tác dụng phụ, hãy kiểm tra trước. Ví dụ sau chỉ gọi bộ sinh mã khi đầu vào thiếu `requestId`:

```java
import java.util.Objects;
import java.util.function.Supplier;

import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

public final class RequestIdDefaults {

    private RequestIdDefaults() {
    }

    public static <T> Message<T> apply(
            Message<T> input, Supplier<String> generator) {

        MessageBuilder<T> builder = MessageBuilder.fromMessage(input);

        if (input.getHeaders().get("requestId") == null) {
            String generated = Objects.requireNonNull(
                    generator.get(), "requestId mặc định phải khác null");
            builder.setHeaderIfAbsent("requestId", generated);
        }

        return builder.build();
    }
}
```

Hàm này áp dụng quy tắc thiếu giá trị cho `requestId`; nếu chuỗi rỗng cũng không hợp lệ thì cần kiểm tra bổ sung. Việc truyền trực tiếp một `Supplier` vào `setHeaderIfAbsent` không yêu cầu framework gọi supplier: đó chỉ là một đối tượng làm giá trị header.

## 8. Đưa bước bổ sung mặc định vào Java DSL

Có thể tách quy tắc chung thành một hàm nhỏ. Các lớp minh họa ở phần này được đặt trong cùng một package của ứng dụng.

```java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

public final class MessageDefaults {

    private MessageDefaults() {
    }

    public static <T> Message<T> apply(Message<T> input) {
        return MessageBuilder.fromMessage(input)
                .setHeaderIfAbsent("locale", "vi-VN")
                .setHeaderIfAbsent("maxAttempts", 3)
                .build();
    }
}
```

Cấu hình luồng tiếp nhận message qua một channel và chuyển kết quả vào `QueueChannel`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.transformer.Transformer;

@Configuration
@EnableIntegration
public class OrderDefaultsConfiguration {

    @Bean
    public QueueChannel orderDefaultsOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow orderDefaultsFlow(
            QueueChannel orderDefaultsOutput) {

        Transformer addDefaults = message -> MessageDefaults.apply(message);

        return IntegrationFlow.from("orderDefaultsInput")
                .transform(addDefaults)
                .channel(orderDefaultsOutput)
                .get();
    }
}
```

Ở đây lambda được khai báo kiểu `Transformer`, nên nhận toàn bộ `Message<?>` theo hợp đồng của interface. Với các overload lambda thông thường của DSL, đầu vào thường là payload; nếu dùng overload nhận `Class`, cần truyền `Message.class` khi muốn xử lý cả message. Xem hướng dẫn [DSL Basics: lambda và Message](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html).

Luồng có thể được kiểm tra thủ công bằng một chương trình nhỏ:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

public class OrderDefaultsDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderDefaultsConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "orderDefaultsInput", MessageChannel.class);
            QueueChannel output = context.getBean(
                    "orderDefaultsOutput", QueueChannel.class);

            input.send(MessageBuilder.withPayload("ORDER-1008")
                    .setHeader("locale", "en-US")
                    .build());

            Message<?> result = output.receive(1_000);
            if (result == null) {
                throw new IllegalStateException("Không nhận được kết quả");
            }

            System.out.println(result.getHeaders().get("locale"));
            System.out.println(result.getHeaders().get("maxAttempts"));
        }
    }
}
```

Kết quả nghiệp vụ mong đợi là `en-US` và `3`. Có thể chèn router sau bước bổ sung mặc định để chọn nhánh theo `locale`, hoặc đặt bước này trước transformer tạo nội dung thông báo.

Khi transformer trả về toàn bộ message, mã ứng dụng phải chịu trách nhiệm chuẩn bị header cho kết quả. Việc dùng `fromMessage` trong `MessageDefaults` giữ ngữ cảnh đầu vào trong phạm vi các header được phép sao chép, thay vì chỉ tạo message từ payload. Quy tắc propagation và header chỉ đọc được mô tả trong [Spring Integration: Message](https://docs.spring.io/spring-integration/reference/message.html).

### Cách khai báo bằng Header Enricher

Nếu chỉ cần bổ sung một tập giá trị tĩnh, Java DSL có cách khai báo trực tiếp:

```java
@Bean
public IntegrationFlow declarativeDefaultsFlow() {
    return IntegrationFlow.from("declarativeDefaultsInput")
            .enrichHeaders(headers -> headers
                    .header("locale", "vi-VN", false)
                    .header("maxAttempts", 3, false))
            .channel("declarativeDefaultsOutput")
            .get();
}
```

Đây là phương án cấu hình thay thế; cần khai báo channel đầu ra và consumer phù hợp trong ứng dụng. Tham số thứ ba `false` của `header` quy định không ghi đè header đã tồn tại. Với hai header tùy biến và giá trị khác `null` này, kết quả nghiệp vụ tương ứng với việc bổ sung mặc định bằng builder. Header Enricher còn có tùy chọn biểu thức và xử lý `null`, nên không nên suy ra rằng mọi cấu hình của nó đều đồng nhất với một lời gọi builder. Xem [HeaderEnricherSpec 6.5.4](https://github.com/spring-projects/spring-integration/blob/v6.5.4/spring-integration-core/src/main/java/org/springframework/integration/dsl/HeaderEnricherSpec.java).

## 9. Message, payload và vòng đời của builder

Việc bổ sung header qua builder không có nghĩa là sửa trực tiếp map của message đầu vào. Tránh cách viết:

```java
// Không hợp lệ với MessageHeaders thông thường của message đã tạo.
incoming.getHeaders().put("locale", "vi-VN");
```

Với message bất biến thông thường, thao tác trên sẽ báo `UnsupportedOperationException`. Quy trình phù hợp là khởi tạo builder từ message rồi nhận kết quả qua `build()`.

Cần phân biệt cấu trúc message với các đối tượng được nó tham chiếu. Nếu payload hoặc một giá trị header là `List` có thể thay đổi, `fromMessage` không tự sao chép sâu danh sách đó. Việc sửa danh sách vẫn có thể ảnh hưởng những nơi cùng giữ tham chiếu. Các ví dụ trong bài dùng chuỗi và số nguyên để tập trung vào quy tắc bổ sung header.

Không nên dùng builder chung cho nhiều yêu cầu hoặc nhiều luồng thực thi. Builder giữ trạng thái trong quá trình xây dựng message; hãy tạo builder riêng cho từng lần xử lý.

Cũng không nên dùng phép so sánh tham chiếu để kết luận bước xử lý có đúng hay không. Khi không có thay đổi, builder có thể trả lại message gốc; ứng dụng nên kiểm tra payload và các header thuộc hợp đồng nghiệp vụ. Đây là hành vi được thể hiện trong [BaseMessageBuilder 6.5.4](https://github.com/spring-projects/spring-integration/blob/v6.5.4/spring-integration-core/src/main/java/org/springframework/integration/support/BaseMessageBuilder.java).

### Header hệ thống và ngữ cảnh tích hợp

`MessageHeaders.ID` và `MessageHeaders.TIMESTAMP` là các header hệ thống chỉ đọc. Không dùng `setHeaderIfAbsent` để cố áp đặt `id` hoặc `timestamp`; nếu cần mã hay thời gian nghiệp vụ, hãy tạo header riêng như `requestId` hoặc `businessCreatedAt`.

Với luồng có gateway, việc giữ các header điều khiển còn giúp duy trì ngữ cảnh trả lời và xử lý lỗi. Nếu chủ động bổ sung mặc định cho `replyChannel` hoặc `errorChannel`, cần có đích nhận tương ứng và hiểu đường đi của luồng; tên channel trong header không tự tạo ra một consumer.

Với aggregator, mặc định của `correlationId` phải phản ánh khóa nhóm đúng. Nếu các message con của cùng đơn hàng đều thiếu khóa mà mỗi message được gán một UUID mới, chúng sẽ vào các nhóm khác nhau. Hãy quyết định khóa nhóm ở nơi biết quan hệ nghiệp vụ và giữ lại khi đi qua các bước bổ sung mặc định.

Các lưu ý này giúp chọn đúng header để áp dụng chính sách mặc định, không mở rộng chức năng của `setHeaderIfAbsent` thành định tuyến, retry hoặc gom nhóm.

## 10. Kiểm thử hợp đồng bổ sung mặc định

Các kiểm thử dưới đây dùng lớp `MessageDefaults` đã khai báo ở phần Java DSL. Chúng kiểm tra kết quả nghiệp vụ mà không phụ thuộc vào `id`, `timestamp` hoặc việc builder tạo đối tượng message mới.

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MessageDefaultsTest {

    @Test
    void addsMissingDefaultsAndKeepsInputUnchanged() {
        Message<String> input = MessageBuilder
                .withPayload("ORDER-2001")
                .setHeader("source", "batch")
                .build();

        Message<String> output = MessageDefaults.apply(input);

        assertEquals("ORDER-2001", output.getPayload());
        assertEquals("batch", output.getHeaders().get("source"));
        assertEquals("vi-VN", output.getHeaders().get("locale"));
        assertEquals(Integer.valueOf(3),
                output.getHeaders().get("maxAttempts", Integer.class));
        assertNull(input.getHeaders().get("locale"));
        assertNull(input.getHeaders().get("maxAttempts"));
    }

    @Test
    void preservesValuesChosenBySender() {
        Message<String> input = MessageBuilder
                .withPayload("ORDER-2002")
                .setHeader("locale", "en-US")
                .setHeader("maxAttempts", 5)
                .build();

        Message<String> output = MessageDefaults.apply(input);

        assertEquals("en-US", output.getHeaders().get("locale"));
        assertEquals(Integer.valueOf(5),
                output.getHeaders().get("maxAttempts", Integer.class));
    }

    @Test
    void existingEmptyZeroAndFalseValuesAreStillPresent() {
        for (Object existing : List.of("", "   ", 0, false)) {
            Message<String> input = MessageBuilder
                    .withPayload("ORDER-2003")
                    .setHeader("locale", existing)
                    .build();

            Message<String> output = MessageDefaults.apply(input);

            assertEquals(existing, output.getHeaders().get("locale"));
        }
    }

    @Test
    void doesNotConvertAnExistingCustomHeader() {
        Message<String> input = MessageBuilder
                .withPayload("ORDER-2004")
                .setHeader("maxAttempts", "5")
                .build();

        Message<String> output = MessageDefaults.apply(input);

        assertEquals("5", output.getHeaders().get("maxAttempts"));
        assertThrows(IllegalArgumentException.class,
                () -> output.getHeaders().get("maxAttempts", Integer.class));
    }

    @Test
    void firstDefaultWinsUntilExplicitlyOverridden() {
        MessageBuilder<String> builder = MessageBuilder
                .withPayload("ORDER-2005")
                .setHeaderIfAbsent("locale", "vi-VN")
                .setHeaderIfAbsent("locale", "en-US");

        assertEquals("vi-VN", builder.build().getHeaders().get("locale"));

        builder.setHeader("locale", "ja-JP");

        assertEquals("ja-JP", builder.build().getHeaders().get("locale"));
    }
}
```

Giá trị số và boolean trong kiểm thử thứ ba được dùng có chủ ý để làm rõ ý nghĩa “đã có giá trị” của một header tùy biến. Trong luồng thật, bước kiểm tra hợp đồng có thể từ chối các giá trị đó vì `locale` phải là chuỗi ngôn ngữ.

Ở mức kiểm thử luồng, nên gửi ít nhất hai message qua channel đầu vào: một thiếu mặc định và một đã có lựa chọn riêng. Sau đó xác nhận endpoint phía sau nhận đúng header, đồng thời xác nhận các header ngữ cảnh cần thiết vẫn còn.

## 11. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Header đã có bị thay giá trị | Dùng `setHeader`, `copyHeaders` hoặc bước ghi đè phía sau | Xem thứ tự các thao tác và cấu hình overwrite |
| Chuỗi rỗng không được thay bằng mặc định | Chuỗi rỗng vẫn là một giá trị | Chuẩn hóa hoặc kiểm tra nghiệp vụ trước bước bổ sung |
| Đọc header bằng `Integer.class` bị lỗi | Bên gửi truyền chuỗi, builder giữ nguyên | Thống nhất kiểu hoặc thêm bước chuyển đổi có kiểm soát |
| Mất header nguồn hoặc ngữ cảnh trả lời | Tạo builder từ payload nhưng chưa sao chép header | Dùng `fromMessage` khi đang bổ sung vào message hiện có |
| Hàm tạo mặc định vẫn chạy khi header đã có | Đối số Java được tính trước lời gọi | Chỉ tính giá trị sau khi kiểm tra header còn thiếu |
| Mặc định khác nhau giữa các nhánh | Các bước bổ sung hoặc ghi đè có thứ tự khác nhau | Xác định một chính sách ưu tiên thống nhất |
| Aggregator gom sai nhóm | Tự sinh khóa nhóm riêng cho từng message con | Lấy khóa nhóm từ quan hệ nghiệp vụ dùng chung |

Khi áp dụng vào luồng đơn hàng, hãy xác định rõ header nào được bên gửi lựa chọn, header nào phải được chuẩn hóa và endpoint nào có quyền ghi đè. Sau đó dùng `setHeaderIfAbsent` cho các giá trị mặc định cần bổ sung theo đúng thứ tự ưu tiên đã chọn.