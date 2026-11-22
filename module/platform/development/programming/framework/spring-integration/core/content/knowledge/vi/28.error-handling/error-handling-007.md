# MessagingException

## 1. Mục tiêu và phạm vi

Trong chương **Error handling** của module **SPRING_INTEGRATION_CORE**, `MessagingException` là kiểu exception cơ sở giúp mô tả lỗi liên quan đến xử lý và vận chuyển thông điệp. Điểm đáng chú ý là exception có thể giữ cả nguyên nhân lẫn `Message<?>` gắn với lần thất bại.

Sau bài học, bạn có thể:

- Phân biệt thông báo lỗi, nguyên nhân và thông điệp thất bại.
- Chọn constructor giữ đủ ngữ cảnh khi chuyển một lỗi nghiệp vụ sang tầng messaging.
- Đọc các lớp con như `MessageHandlingException` và `MessageDeliveryException`.
- Truy lại nguyên nhân qua nhiều lớp wrapper mà không đánh mất metadata nghiệp vụ.
- Giải thích đường lan truyền của exception và kiểm thử lỗi qua kênh đồng bộ hoặc poller.

Các ví dụ dùng Java 17, API Spring Framework/Spring Integration 6.x và JUnit Jupiter. Phiên bản dependency cần theo BOM hoặc nền tảng Spring Boot tương thích của dự án. Bài tập trung vào mô hình exception và ngữ cảnh lỗi; retry, giao dịch và error flow là những cơ chế được cấu hình quanh nó.

## 2. MessagingException nằm ở đâu?

Import cần dùng:

```java
import org.springframework.messaging.MessagingException;
```

Đây là lớp của **Spring Messaging**, được Spring Integration sử dụng trong nhiều thành phần:

```text
Throwable
  └── Exception
       └── RuntimeException
            └── NestedRuntimeException
                 └── MessagingException
```

Vì kế thừa `RuntimeException`, nó là unchecked exception. Phương thức không bắt buộc khai báo `throws MessagingException`, nhưng caller vẫn phải hiểu lỗi có thể xuất hiện khi gọi luồng tích hợp.

`MessagingException` không phải annotation, không phải `MessageChannel` và không phải một thông điệp được gửi trên kênh. Nó là một đối tượng exception Java có thêm thông tin liên quan tới messaging.

Định nghĩa lớp và các constructor nằm trong [Javadoc của MessagingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html).

### Vì sao một exception thông thường chưa đủ ngữ cảnh?

Giả sử nhiều đơn hàng đồng thời đi qua một transformer chuyển chuỗi tiền thành `BigDecimal`. Log chỉ có:

```text
NumberFormatException: Character N is neither ...
```

Bạn biết phép chuyển đổi thất bại, nhưng còn cần xác định:

- Thông điệp nào chứa dữ liệu sai?
- Sự kiện nghiệp vụ có mã gì?
- Lỗi xuất hiện ở bước nào?
- Có nguyên nhân bên trong nào cần phân loại riêng không?

Một `MessagingException` được tạo kèm message và cause cung cấp điểm truy cập có cấu trúc để trả lời các câu hỏi đó.

## 3. Ba loại thông tin phải đọc riêng

| Thành phần | Cách truy cập | Ý nghĩa |
| --- | --- | --- |
| Mô tả lỗi | `getMessage()` | Thông tin dạng văn bản để hiểu lỗi |
| Nguyên nhân trực tiếp | `getCause()` | Exception được bọc ở lớp ngay bên trong |
| Thông điệp thất bại | `getFailedMessage()` | Message được gắn trực tiếp vào exception này, nếu có |

Ví dụ:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

// Đặt bên trong một phương thức:
Message<String> request = MessageBuilder
    .withPayload("NOT-A-NUMBER")
    .setHeader("businessEventId", "event-1001")
    .build();

NumberFormatException cause =
    new NumberFormatException("Giá trị tiền không hợp lệ");

MessagingException failure = new MessagingException(
    request,
    "Không thể đọc số tiền của đơn hàng",
    cause
);
```

Trong ví dụ:

```text
failure
├── mô tả: Không thể đọc số tiền của đơn hàng
├── cause: NumberFormatException
└── failedMessage
    ├── payload: "NOT-A-NUMBER"
    └── headers["businessEventId"]: "event-1001"
```

Không ép `failure.getCause()` thành message và không xem `failure.getFailedMessage()` là exception.

Mô tả lỗi phục vụ con người, không phải hợp đồng ổn định để phân nhánh bằng cách tìm chuỗi. Nếu cần phân loại, hãy dựa vào kiểu exception, mã lỗi nghiệp vụ hoặc dữ liệu có cấu trúc đã thiết kế.

### Các constructor thường gặp

| Constructor | Có thể giữ message? | Có thể giữ cause? |
| --- | --- | --- |
| `MessagingException(description)` | Không | Không truyền cause |
| `MessagingException(description, cause)` | Không | Có |
| `MessagingException(message, description)` | Có | Không truyền cause |
| `MessagingException(message, cause)` | Có | Có |
| `MessagingException(message, description, cause)` | Có | Có |

Lớp cũng có constructor chỉ nhận `Message<?>`. Trong mã ứng dụng, một mô tả đủ rõ cùng cause thường giúp việc điều tra hiệu quả hơn.

Chọn overload phù hợp với thông tin thực sự có ở thời điểm lỗi. Không dựng một message giả chỉ để làm cho `getFailedMessage()` luôn khác `null`.

## 4. failedMessage có thể null và không tự tìm trong cause

Đoạn này không truyền message:

```java
MessagingException failure = new MessagingException(
    "Không thể khởi tạo thao tác đọc nguồn"
);

Message<?> failed = failure.getFailedMessage(); // null
```

Đó có thể là trạng thái hợp lệ: nguồn thất bại trước khi tạo được message, hoặc code chỉ có thông tin lỗi.

Một trường hợp khác dễ nhầm:

```java
Message<String> request = MessageBuilder
    .withPayload("ORDER-1001")
    .build();

MessagingException inner = new MessagingException(
    request,
    "Lỗi ở bước xử lý đơn hàng"
);

MessagingException outer = new MessagingException(
    "Lỗi ở tầng điều phối",
    inner
);
```

Kết quả:

```text
outer.getFailedMessage() -> null
outer.getCause()         -> inner
inner.getFailedMessage() -> request
```

Accessor `getFailedMessage()` trả ngữ cảnh gắn với **chính exception đang được gọi**. Nó không tự duyệt chuỗi cause để tìm message ở một exception bên trong.

### Message tại điểm thất bại có thể khác đầu vào ban đầu

Trong luồng:

```text
M0: chuỗi JSON
  -> transformer
M1: đối tượng Order
  -> handler
  -> thất bại
```

Exception tại handler có thể giữ `failedMessage = M1`. Không mặc định ép payload về `String` chỉ vì dữ liệu đầu tiên của luồng là JSON.

Tương tự, khi một splitter tạo nhiều phần, message thất bại có thể là một phần được tách ra. Muốn đối chiếu với yêu cầu ban đầu, cần metadata tương quan hoặc ngữ cảnh khác được giữ rõ ràng.

`failedMessage` cũng không phải ảnh chụp sâu của payload. Nếu payload là đối tượng có thể thay đổi, tham chiếu message không tự cung cấp bản lưu trạng thái trước mọi thay đổi.

## 5. Đọc chuỗi nguyên nhân bằng NestedRuntimeException

`MessagingException` kế thừa các hàm hỗ trợ từ `NestedRuntimeException`:

| Phương thức | Kết quả |
| --- | --- |
| `getCause()` | Cause ngay bên trong; có thể `null` |
| `getRootCause()` | Cause sâu nhất nếu có; có thể `null` |
| `getMostSpecificCause()` | Cause sâu nhất, hoặc chính exception hiện tại nếu không có cause |
| `contains(SomeException.class)` | Kiểm tra exception hiện tại và chuỗi cause có kiểu đó không |

Ví dụ:

```java
NumberFormatException root =
    new NumberFormatException("Sai định dạng tiền");

IllegalArgumentException middle =
    new IllegalArgumentException("Dữ liệu đơn hàng không hợp lệ", root);

MessagingException failure = new MessagingException(
    request,
    "Không thể xử lý thông điệp",
    middle
);

Throwable immediate = failure.getCause();             // middle
Throwable deepest = failure.getRootCause();           // root
Throwable mostSpecific = failure.getMostSpecificCause(); // root
boolean containsFormatError =
    failure.contains(NumberFormatException.class);    // true
```

Đoạn này giả định `request` là message đã tạo trước đó. Các hàm kiểm tra chuỗi cause không thay thế việc đọc message ở từng lớp wrapper.

Nếu exception không có cause:

```java
MessagingException failure =
    new MessagingException("Lỗi messaging chưa có nguyên nhân lồng");

failure.getRootCause();         // null
failure.getMostSpecificCause(); // chính failure
```

Hợp đồng các phương thức được mô tả trong [Javadoc của NestedRuntimeException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/NestedRuntimeException.html).

### Nguyên nhân sâu nhất chưa phải toàn bộ câu chuyện

Một `NumberFormatException` giải thích lỗi chuyển đổi. Lớp `MessageTransformationException` bên ngoài cho biết lỗi xuất hiện trong vai trò transformer. `failedMessage` cho biết dữ liệu nào đang được chuyển đổi.

Khi điều tra, hãy giữ cả ba chiều thông tin: **vị trí/vai trò xử lý**, **nguyên nhân** và **message liên quan**. Chỉ ghi lại lớp exception sâu nhất sẽ làm mất ngữ cảnh của luồng tích hợp.

## 6. Các lớp con giúp xác định vai trò xảy ra lỗi

Một phần cây kế thừa thường gặp:

```text
MessagingException
├── MessageDeliveryException
├── MessageHandlingException
│   └── MessageRejectedException
├── MessageConversionException
└── MessageTransformationException
```

Trong sơ đồ, `MessageRejectedException` và `MessageTransformationException` thuộc Spring Integration; các lớp còn lại được liệt kê ở đây thuộc Spring Messaging.

| Kiểu lỗi | Vai trò mô tả | Điều không nên tự suy ra |
| --- | --- | --- |
| `MessageDeliveryException` | Lỗi trong quá trình chuyển/giao thông điệp | Không tự chứng minh toàn bộ nghiệp vụ chưa tạo tác dụng phụ |
| `MessageHandlingException` | Lỗi khi xử lý thông điệp | Không có nghĩa lỗi luôn là dữ liệu đầu vào không hợp lệ |
| `MessageConversionException` | Lỗi từ cơ chế `MessageConverter` | Không đồng nghĩa với mọi lỗi của một transformer |
| `MessageTransformationException` | Lỗi chuyển đổi trong vai trò transformer của Integration | Không mặc định payload luôn là chuỗi JSON |
| `MessageRejectedException` | Message bị selector từ chối theo cơ chế của component | Không có nghĩa mọi message bị bỏ qua đều phải ném exception |

Các package cần phân biệt:

```java
org.springframework.messaging.MessageDeliveryException
org.springframework.messaging.MessageHandlingException
org.springframework.messaging.converter.MessageConversionException

org.springframework.integration.transformer.MessageTransformationException
org.springframework.integration.MessageRejectedException
```

`MessageTransformationException` không phải lớp con của `MessageConversionException`. Hai kiểu mô tả những abstraction khác nhau dù đều có thể xuất hiện trong một quy trình đổi dữ liệu.

Tài liệu API: [MessageDeliveryException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageDeliveryException.html), [MessageHandlingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandlingException.html), [MessageConversionException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConversionException.html), [MessageTransformationException](https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/MessageTransformationException.html) và [MessageRejectedException](https://docs.spring.io/spring-integration/api/org/springframework/integration/MessageRejectedException.html).

### Chọn kiểu bắt lỗi theo mục tiêu

- Bắt `MessagingException` khi cần một điểm xử lý chung cho lỗi messaging tại ranh giới gọi luồng.
- Kiểm tra subtype khi vai trò xảy ra lỗi quyết định hành vi xử lý.
- Xem cause hoặc mã lỗi nghiệp vụ khi cần phân biệt lỗi tạm thời với lỗi dữ liệu.
- Giữ message và metadata để đối chiếu sự kiện cụ thể.

Không cấu hình “mọi `MessagingException` đều retry”. Sai định dạng số, lỗi cấu hình kênh và sự cố kết nối tạm thời có cách phục hồi khác nhau.

## 7. Tạo exception ở đúng ranh giới và giữ cause

Khi viết component custom làm việc trực tiếp với `Message<?>`, bạn có thể bọc lỗi bằng subtype phù hợp để giữ message và nguyên nhân.

Ví dụ handler chỉ kiểm tra chuỗi số tiền:

```java
import java.math.BigDecimal;

import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessageHandlingException;

// Bên trong phương thức:
MessageHandler validateAmount = message -> {
    Object payload = message.getPayload();

    if (!(payload instanceof String text)) {
        throw new MessageHandlingException(
            message,
            "Payload kiểm tra số tiền phải là String"
        );
    }

    try {
        new BigDecimal(text);
    }
    catch (NumberFormatException cause) {
        throw new MessageHandlingException(
            message,
            "Không thể kiểm tra số tiền",
            cause
        );
    }
};
```

Đây là handler kiểm tra, không phải transformer phát `BigDecimal` ra kênh khác. Nó minh họa việc chuyển một lỗi chuyển đổi cụ thể thành lỗi xử lý kèm message.

### Tránh làm mất thông tin

Cách sau bỏ nguyên nhân và ngữ cảnh message:

```java
catch (NumberFormatException cause) {
    throw new MessagingException(cause.getMessage());
}
```

Giữ cả hai khi có sẵn:

```java
catch (NumberFormatException cause) {
    throw new MessageHandlingException(
        message,
        "Không thể kiểm tra số tiền",
        cause
    );
}
```

Đồng thời, không bọc thêm một lớp chỉ để đổi câu chữ ở mọi tầng. Nếu một `MessagingException` đã mô tả đúng bước thất bại, việc truyền tiếp có thể giữ subtype cùng ngữ cảnh tốt hơn việc thay bằng một exception chung.

Khi thật sự cần thêm lớp điều phối, giữ exception cũ làm cause và xác định message của lớp mới là gì. Một wrapper ngoài cùng gắn message khác với lớp trong phải phản ánh đúng ranh giới xử lý.

### Không ép tầng nghiệp vụ phụ thuộc messaging chỉ để báo lỗi

Một dịch vụ thuần có thể nhận `Order` và ném exception nghiệp vụ của nó. Endpoint hoặc adapter ở ranh giới thông điệp chịu trách nhiệm gắn lỗi đó với `Message<?>`.

Ngược lại, custom `MessageHandler` đã biết message có thể chủ động tạo `MessageHandlingException`. Chọn ranh giới này giúp ngữ cảnh rõ ràng mà không cần truyền `Message` qua mọi lớp trong ứng dụng.

## 8. Ví dụ hoàn chỉnh: transformer đọc số tiền

Cấu hình dưới đây có hai đầu vào:

- `directAmountRequests` là `DirectChannel`, để caller quan sát lỗi đồng bộ.
- `queuedAmountRequests` là `QueueChannel`, để poller xử lý và báo lỗi qua kênh riêng.

Cả hai transformer chuyển `String` thành `BigDecimal`. Chuỗi không đúng định dạng làm constructor `BigDecimal` ném `NumberFormatException`.

Tạo `MessagingFailureConfiguration.java`:

```java
package example.integration;

import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class MessagingFailureConfiguration {

    @Bean
    public DirectChannel directAmountRequests() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel queuedAmountRequests() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel parsedAmounts() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel amountErrors() {
        return new QueueChannel(20);
    }

    @Bean
    public AmountParser amountParser() {
        return new AmountParser();
    }

    public static class AmountParser {

        @Transformer(
            inputChannel = "directAmountRequests",
            outputChannel = "parsedAmounts"
        )
        public BigDecimal parseDirect(String text) {
            return new BigDecimal(text);
        }

        @Transformer(
            inputChannel = "queuedAmountRequests",
            outputChannel = "parsedAmounts",
            poller = @Poller(
                fixedDelay = "100",
                maxMessagesPerPoll = "1",
                receiveTimeout = "0",
                errorChannel = "amountErrors"
            )
        )
        public BigDecimal parseQueued(String text) {
            return new BigDecimal(text);
        }
    }
}
```

`AmountParser` được quản lý bởi Spring thông qua `@Bean` nên các phương thức annotation có thể được xử lý. `@EnableIntegration` bật hạ tầng Integration khi chạy Java Configuration thuần.

Dependency chính là `org.springframework.integration:spring-integration-core`. Ví dụ chỉ chuyển đổi định dạng số, chưa kiểm tra quy tắc nghiệp vụ như đơn vị tiền, giới hạn giá trị hay số chữ số thập phân.

### Khi dữ liệu hợp lệ

```text
Message<String>("125000.50")
        |
        v
transformer
        |
        v
Message<BigDecimal>(125000.50)
        |
        v
parsedAmounts
```

### Khi dữ liệu không hợp lệ

```text
Message<String>("NOT-A-NUMBER")
        |
        v
new BigDecimal(...)
        |
        v
NumberFormatException
        |
        v
lỗi messaging do hạ tầng transformer biểu diễn
        |
        v
failedMessage giữ thông điệp liên quan
```

Tầng messaging có thể thêm wrapper để mô tả lỗi của transformer hoặc lời gọi phương thức. Vì thế, bài kiểm thử phía dưới kiểm tra quan hệ `contains(NumberFormatException.class)` và ngữ cảnh message thay vì chốt một chuỗi wrapper duy nhất.

## 9. Đường đồng bộ và đường qua poller khác nhau ở đâu?

### 9.1. DirectChannel: exception có thể về caller

```text
caller -> directAmountRequests -> transformer -> thất bại
   ^                                             |
   └──────────── exception theo call stack ──────┘
```

Trong cấu hình này, gọi `send(...)` trên nguồn direct thực thi transformer trên thread caller. Một lỗi có thể lan ngược về lời gọi gửi.

Có thể xử lý tại ranh giới gọi:

```java
try {
    input.send(request);
}
catch (MessagingException failure) {
    Message<?> failed = failure.getFailedMessage();
    Throwable cause = failure.getMostSpecificCause();

    // Ghi nhận hoặc chuyển tiếp lỗi theo hợp đồng của ứng dụng.
}
```

Đây là đoạn minh họa ranh giới catch; `input` và `request` phải là kênh cùng message đang gửi. Nếu chỉ ghi nhận rồi thoát khỏi catch, caller có thể không còn biết thao tác thất bại. Hãy quy định rõ cần ném tiếp, trả kết quả lỗi hay đưa lỗi sang cơ chế khác.

### 9.2. QueueChannel và poller: caller đã gửi xong trước khi xử lý lỗi

```text
caller -> queuedAmountRequests -> send hoàn tất
                    |
                    v
              polling task
                    |
                    v
                transformer
                    |
                    v
              MessagingException
                    |
                    v
              ErrorMessage
                    |
                    v
                amountErrors
```

Producer chỉ biết queue đã nhận message. Exception xuất hiện khi poller xử lý về sau không thể quay ngược vào một lời gọi `send(...)` đã hoàn tất.

Hạ tầng polling chuẩn bắt lỗi và có thể phát `ErrorMessage`; payload của message lỗi là `Throwable`, thường là một exception messaging giữ thông điệp thất bại.

`@Poller(errorChannel = "amountErrors")` đặt kênh mặc định cho error handler của poller trong ví dụ. Header `errorChannel` trên message thất bại có thể chọn đích khác khi hạ tầng tìm được header đó.

### 9.3. MessagingException và ErrorMessage không hoán đổi vai trò

| Kiểu | Vai trò |
| --- | --- |
| `MessagingException` | Được ném trong Java; có thể giữ `failedMessage` và cause |
| `ErrorMessage` | Được gửi trên kênh; payload là `Throwable` |
| Error channel | Điểm nhận thông điệp lỗi để endpoint xử lý |

```java
MessagingException failure = new MessagingException(
    request,
    "Không thể xử lý thông điệp"
);

ErrorMessage error = new ErrorMessage(failure);
```

Đoạn này tạo thông điệp lỗi nhưng chưa gửi nó. `error.getPayload()` là `failure`; message nghiệp vụ được truy lại qua `failure.getFailedMessage()`.

Đặt header `errorChannel` cũng không tự bắt mọi exception đồng bộ. Gateway có thể có cơ chế ánh xạ hoặc phát lỗi riêng theo cấu hình; không nên suy rộng hành vi của lời gọi `MessageChannel.send(...)` thành hợp đồng của mọi gateway.

Xem [Error Handling của Spring Integration](https://docs.spring.io/spring-integration/reference/error-handling.html).

## 10. Tìm message qua chuỗi wrapper một cách có chủ đích

Khi nhận một `Throwable` bất kỳ từ error flow, lớp ngoài có thể không phải `MessagingException` hoặc không có `failedMessage`. Nếu yêu cầu là tìm message gần lớp ngoài nhất có ngữ cảnh, có thể dùng một hàm hỗ trợ.

Tạo `FailureContexts.java`:

```java
package example.integration;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;

public final class FailureContexts {

    private FailureContexts() {
    }

    public static Message<?> firstFailedMessage(Throwable failure) {
        Set<Throwable> visited = Collections.newSetFromMap(
            new IdentityHashMap<Throwable, Boolean>()
        );

        Throwable current = failure;

        while (current != null && visited.add(current)) {
            if (current instanceof MessagingException messagingException) {
                Message<?> failed =
                    messagingException.getFailedMessage();

                if (failed != null) {
                    return failed;
                }
            }

            current = current.getCause();
        }

        return null;
    }
}
```

Hợp đồng của hàm:

- Duyệt từ exception ngoài cùng vào chuỗi cause.
- Trả message đầu tiên khác `null` được tìm thấy.
- Trả `null` nếu không có ngữ cảnh message.
- Theo dõi các đối tượng đã đi qua để không lặp vô hạn nếu gặp chuỗi cause có vòng.

Đây là helper do bài học định nghĩa, không phải phương thức có sẵn của Spring. Nó không duyệt suppressed exceptions và không chọn “message ban đầu nhất” của hệ thống.

Nếu mỗi lớp exception giữ một message ở giai đoạn khác nhau, message tìm thấy đầu tiên có thể khác message của cause sâu nhất. Với mục tiêu điều tra khác, hãy thu thập từng ngữ cảnh và đọc theo ranh giới xử lý tương ứng.

## 11. Kiểm thử hợp đồng exception và luồng tích hợp

Các đoạn dưới dùng cùng package `example.integration` với cấu hình ở phần 8 và helper ở phần 10.

### 11.1. Kiểm thử message, cause và trường hợp thiếu ngữ cảnh

Tạo `MessagingExceptionContractTest.java`:

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MessagingExceptionContractTest {

    @Test
    void preservesProvidedMessageAndCause() {
        Message<String> request = MessageBuilder
            .withPayload("BAD-AMOUNT")
            .setHeader("businessEventId", "event-contract")
            .build();

        NumberFormatException cause =
            new NumberFormatException("Sai định dạng");

        MessagingException failure = new MessagingException(
            request,
            "Đọc số tiền thất bại",
            cause
        );

        assertSame(request, failure.getFailedMessage());
        assertSame(cause, failure.getCause());
        assertSame(cause, failure.getRootCause());
        assertSame(cause, failure.getMostSpecificCause());
        assertTrue(failure.contains(NumberFormatException.class));
    }

    @Test
    void outerWrapperDoesNotAutomaticallyExposeInnerFailedMessage() {
        Message<String> request = MessageBuilder
            .withPayload("ORDER-1001")
            .build();

        MessageHandlingException inner =
            new MessageHandlingException(
                request,
                "Lỗi trong handler",
                new IllegalStateException("Dịch vụ phụ trợ chưa sẵn sàng")
            );

        MessagingException outer = new MessagingException(
            "Lỗi ở tầng điều phối",
            inner
        );

        assertNull(outer.getFailedMessage());
        assertSame(request, inner.getFailedMessage());
        assertSame(
            request,
            FailureContexts.firstFailedMessage(outer)
        );
        assertTrue(outer.contains(IllegalStateException.class));
    }

    @Test
    void exceptionWithoutCauseHasNoRootCause() {
        MessagingException failure =
            new MessagingException("Lỗi không có cause");

        assertNull(failure.getFailedMessage());
        assertNull(failure.getRootCause());
        assertSame(failure, failure.getMostSpecificCause());
    }
}
```

Các assertion trên kiểm tra hợp đồng đối tượng được tạo trong bài, không suy ra rằng mọi component của framework luôn tạo cùng một subtype hoặc số lớp wrapper.

### 11.2. Kiểm thử transformer với dữ liệu đúng và sai

Tạo `MessagingFailureFlowTest.java`:

```java
package example.integration;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MessagingFailureFlowTest {

    @Test
    void validAmountIsTransformed() {
        try (var context = new AnnotationConfigApplicationContext(
                MessagingFailureConfiguration.class)) {

            MessageChannel input = context.getBean(
                "directAmountRequests", MessageChannel.class);
            QueueChannel output = context.getBean(
                "parsedAmounts", QueueChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("125000.50")
                .build();

            assertTrue(input.send(request));

            Message<?> result = output.receive(0);
            assertNotNull(result);
            assertEquals(
                new BigDecimal("125000.50"),
                result.getPayload()
            );
        }
    }

    @Test
    void directFailureRetainsCauseAndBusinessContext() {
        try (var context = new AnnotationConfigApplicationContext(
                MessagingFailureConfiguration.class)) {

            MessageChannel input = context.getBean(
                "directAmountRequests", MessageChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("NOT-A-NUMBER")
                .setHeader("businessEventId", "event-direct")
                .build();

            MessagingException failure = assertThrows(
                MessagingException.class,
                () -> input.send(request)
            );

            assertTrue(failure.contains(NumberFormatException.class));

            Message<?> failed =
                FailureContexts.firstFailedMessage(failure);

            assertNotNull(failed);
            assertEquals("NOT-A-NUMBER", failed.getPayload());
            assertEquals(
                "event-direct",
                failed.getHeaders().get("businessEventId")
            );
        }
    }

    @Test
    void polledFailureIsReportedThroughErrorMessage() {
        try (var context = new AnnotationConfigApplicationContext(
                MessagingFailureConfiguration.class)) {

            MessageChannel input = context.getBean(
                "queuedAmountRequests", MessageChannel.class);
            QueueChannel errors = context.getBean(
                "amountErrors", QueueChannel.class);
            QueueChannel output = context.getBean(
                "parsedAmounts", QueueChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("INVALID")
                .setHeader("businessEventId", "event-polled")
                .build();

            assertTrue(input.send(request, 1_000));

            Message<?> received = errors.receive(3_000);
            assertNotNull(received);
            assertTrue(received instanceof ErrorMessage);

            ErrorMessage error = (ErrorMessage) received;
            assertTrue(error.getPayload() instanceof MessagingException);

            MessagingException failure =
                (MessagingException) error.getPayload();

            assertTrue(failure.contains(NumberFormatException.class));

            Message<?> failed =
                FailureContexts.firstFailedMessage(failure);

            assertNotNull(failed);
            assertEquals("INVALID", failed.getPayload());
            assertEquals(
                "event-polled",
                failed.getHeaders().get("businessEventId")
            );
            assertNull(output.receive(0));
        }
    }
}
```

Bài kiểm thử thành công đọc bằng `receive(0)` vì transformer chạy đồng bộ và đã gửi kết quả trước khi `send(...)` trả về. Bài kiểm thử polling dùng `receive(3_000)` để chờ kết quả từ tác vụ lập lịch.

Không dùng `Thread.sleep(...)` để đoán thời điểm xử lý hoàn tất. Đóng context bằng `try-with-resources` giúp dừng các tài nguyên polling sau mỗi bài.

Các kiểm thử thể hiện hợp đồng cần quan tâm: dữ liệu hợp lệ được chuyển đổi; dữ liệu sai giữ được nguyên nhân và ngữ cảnh nghiệp vụ; lỗi polling xuất hiện trên kênh lỗi. Chúng không đo năng lực chịu tải, cơ chế retry, transaction hoặc khả năng phục hồi sau khi tiến trình dừng.

## 12. Dùng thông tin exception để chẩn đoán

Khi gặp một `MessagingException`, có thể đọc theo trình tự:

1. Xác định thao tác vừa thực hiện: gửi message, gọi gateway, chuyển đổi hay xử lý nghiệp vụ.
2. Xem subtype và các wrapper để hiểu ranh giới thất bại.
3. Xem cause trực tiếp, cause sâu nhất và loại lỗi cần phân loại.
4. Tìm `failedMessage` ở lớp exception phù hợp.
5. Trích xuất khóa nghiệp vụ, trace ID và thông tin bước xử lý.
6. Xác định lỗi được trả về caller hay đi qua error flow.

Ví dụ thông tin cần giữ cho một lần lỗi:

```text
businessEventId = event-polled
step            = parse-amount
messagingType   = lớp exception messaging quan sát được
causeType       = NumberFormatException
failedPayload   = giá trị đang được chuyển đổi
```

`step` là metadata do ứng dụng hoặc công cụ quan sát cung cấp; nó không phải field mặc định có trên mọi `MessagingException`.

Một số lỗi do framework tạo có thêm thông tin nguồn cấu hình, chẳng hạn phương thức bean hoặc tài nguyên XML. Dùng thông tin đó để xác định endpoint, nhưng không xây parser phụ thuộc vào định dạng câu chữ của stack trace.

### Chọn metadata thay vì dựa vào toString()

`toString()` hoặc log exception có thể hiển thị message và payload liên quan. Tuy nhiên, chuỗi đó không phải cấu trúc dữ liệu có phiên bản để ứng dụng khác đọc.

Khi cần lưu hoặc gửi báo cáo lỗi, chọn các trường như mã sự kiện, bước thất bại, loại lỗi, mã lỗi nghiệp vụ và tham chiếu dữ liệu. Giữ cause cho chẩn đoán kỹ thuật và dùng dữ liệu có cấu trúc cho quy trình vận hành.

### Bảng chẩn đoán nhanh

| Biểu hiện | Điểm cần kiểm tra |
| --- | --- |
| `getFailedMessage()` là `null` | Constructor có nhận message không, hay message nằm ở cause bên trong? |
| Chỉ thấy `MessageHandlingException` | Nguyên nhân phía trong là gì, có wrapper từ lời gọi phương thức không? |
| Sai kiểu khi đọc payload thất bại | Message đã qua transformer/splitter trước khi lỗi chưa? |
| Không tìm thấy header nghiệp vụ | Đang đọc headers của đúng failed message hay của error envelope? |
| Lỗi không về caller sau khi gửi vào queue | Công việc đã chuyển sang poller hoặc một thread khác chưa? |
| Có header `errorChannel` nhưng exception vẫn bị ném | Có đang gửi trên đường đồng bộ và chưa có cơ chế phát lỗi không? |
| Bắt exception rồi hệ thống báo thành công | Catch có đang nuốt lỗi hoặc trả kết quả thành công mặc định không? |
| Log không còn nguyên nhân ban đầu | Có lớp nào bọc lại chỉ bằng `cause.getMessage()` không? |
| Cùng lỗi xuất hiện liên tục | Dữ liệu sai được retry, nguồn gửi lại hay error flow có vòng lặp? |

## 13. MessagingException chưa quyết định retry, rollback hay gửi lại

Kiểu exception cung cấp thông tin về lỗi. Chính sách xử lý cần được xác định riêng.

### Retry cần xem nguyên nhân và tác dụng phụ

Trong ví dụ, gửi lại đúng chuỗi `"NOT-A-NUMBER"` vào cùng parser sẽ tiếp tục lỗi nếu không thay dữ liệu hoặc logic. Một retry chung cho mọi `MessagingException` chỉ làm công việc lặp lại.

Với lỗi kết nối, cũng cần biết thao tác có thể đã hoàn tất ở hệ thống bên ngoài trước khi kết nối đứt hay chưa. Khóa nghiệp vụ ổn định và cơ chế chống xử lý trùng có thể quan trọng hơn việc chỉ tăng số lượt thử.

`contains(SomeException.class)` hỗ trợ kiểm tra loại trong cause chain, nhưng tự nó chưa phải chính sách retry hoàn chỉnh. Tầng retry còn cần giới hạn lượt, khoảng nghỉ, điều kiện phục hồi và điểm kết thúc.

### Unchecked exception không tự bảo đảm rollback

Transaction chỉ có hiệu lực khi được cấu hình và bao đúng ranh giới tài nguyên. Một `MessagingException` được ném có thể làm transaction tương ứng rollback theo quy tắc đang dùng, nhưng không tự tạo transaction mới hoặc giao dịch phân tán.

Nếu code bắt lỗi và không ném tiếp, ranh giới transaction có thể không quan sát được thất bại theo cách bạn kỳ vọng. Tương tự, đưa công việc qua queue hay executor không tự truyền transaction gắn với thread producer.

### failedMessage không phải cơ chế requeue

Accessor chỉ trả một tham chiếu message được giữ trong exception. Nó không tự:

- Đưa message trở lại nguồn.
- Khôi phục phần tử đã lấy khỏi queue trong bộ nhớ.
- Hoàn tác một cuộc gọi tới hệ thống bên ngoài.
- Lưu dữ liệu qua lần khởi động lại.
- Đánh dấu sự kiện đã được xử lý hoặc đã vượt số lần thử.

Nếu cần gửi lại, phải chọn đúng điểm vào: message tại bước thất bại có thể đã được chuyển đổi nên không phù hợp với kênh nhận dữ liệu ban đầu.

Trong một luồng có filter, transformer, router và aggregator, cùng một mã sự kiện có thể xuất hiện dưới nhiều dạng message. `MessagingException` hữu ích nhất khi bạn giữ đúng ngữ cảnh tại ranh giới lỗi và dùng metadata nghiệp vụ để liên kết các bước đó.
