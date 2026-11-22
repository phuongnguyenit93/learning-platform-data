# ErrorMessage

## 1. Mục tiêu và phạm vi

Trong chương **Error handling** của module **SPRING_INTEGRATION_CORE**, `ErrorMessage` là cấu trúc dùng để biểu diễn một lỗi dưới dạng thông điệp. Nhờ đó, một luồng tích hợp có thể chuyển lỗi tới kênh riêng, phân loại lỗi bằng router và giao cho endpoint xử lý tiếp.

Sau bài học, bạn có thể:

- Đọc đúng payload, headers và thông điệp gốc của một `ErrorMessage`.
- Phân biệt exception đang được ném với thông điệp mô tả exception đó.
- Tìm thông điệp tại điểm thất bại qua `MessagingException.getFailedMessage()`.
- Giải thích khi nào lỗi lan về caller và khi nào hạ tầng phát thông điệp lỗi.
- Cấu hình kênh lỗi, kiểm thử đường đi của lỗi và thiết kế bước xử lý tiếp.

Các ví dụ dùng Java 17, API Spring Framework/Spring Integration 6.x và JUnit Jupiter. Phiên bản dependency nên theo BOM hoặc nền tảng Spring Boot tương thích của dự án. `ErrorMessage` nằm trong Spring Messaging; Spring Integration cung cấp hạ tầng phát, định tuyến và xử lý nó trong luồng tích hợp.

## 2. ErrorMessage là một Message có payload Throwable

Kiểu cần import:

```java
import org.springframework.messaging.support.ErrorMessage;
```

Mô hình khái quát:

```text
ErrorMessage
├── payload: Throwable
│   ├── loại exception và thông báo lỗi
│   ├── cause
│   └── failedMessage nếu payload là MessagingException phù hợp
├── headers: metadata của thông điệp lỗi
└── originalMessage: Message<?> tùy chọn
```

`ErrorMessage` kế thừa `GenericMessage<Throwable>`. Vì vậy, nó vẫn đi qua `MessageChannel` và được endpoint tiêu thụ như những thông điệp khác.

Tuy nhiên, nội dung payload có vai trò riêng:

```java
Throwable failure = errorMessage.getPayload();
```

Đó là đối tượng lỗi, không phải đơn hàng bị xử lý thất bại. Không ép payload của `ErrorMessage` thành `Order` hoặc `String` chỉ vì payload nghiệp vụ ban đầu có kiểu đó.

Payload được khai báo là `Throwable`, nên cũng không ép thành `Exception` nếu chưa kiểm tra kiểu. Khi phân tích lỗi, bắt đầu từ hợp đồng `Throwable` rồi xem loại cụ thể và chuỗi nguyên nhân.

Cấu trúc và các constructor được mô tả trong [Javadoc của ErrorMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html).

### Exception và thông điệp lỗi là hai đối tượng khác nhau

| Khái niệm | Ý nghĩa |
| --- | --- |
| Exception được ném | Làm gián đoạn đường thực thi hiện tại theo cơ chế Java |
| `ErrorMessage` | Một đối tượng message mang thông tin về lỗi |
| Error channel | Kênh nhận message lỗi để endpoint khác xử lý |

Gọi `new ErrorMessage(exception)` chỉ tạo đối tượng. Nó không tự gửi vào `errorChannel`, không tự ghi log và không tự retry nghiệp vụ.

Ngược lại, đặt một header `errorChannel` trên message không khiến mọi lệnh `throw` trong ứng dụng được chuyển thành message. Phải có thành phần bắt lỗi và phát thông điệp theo cơ chế tương ứng.

Một `GenericMessage<Throwable>` cũng có thể mang một exception, nhưng không phải instance của `ErrorMessage` và không có thuộc tính `originalMessage` của lớp này. Khi một API yêu cầu `ErrorMessage`, hãy giữ đúng kiểu và hợp đồng đó.

## 3. Phân biệt failedMessage, originalMessage và headers

Ba nơi dễ bị nhầm nhất:

| Vị trí | Câu hỏi nó giúp trả lời |
| --- | --- |
| `((MessagingException) error.getPayload()).getFailedMessage()` | Thông điệp nào gắn với exception tại điểm thất bại? |
| `error.getOriginalMessage()` | Thông điệp nào được cung cấp làm ngữ cảnh gốc khi tạo thông điệp lỗi? |
| `error.getHeaders()` | Metadata nào thuộc chính thông điệp lỗi đang được gửi? |

### failedMessage nằm trên MessagingException

`MessagingException` là lớp cơ sở cho nhiều lỗi liên quan tới messaging. Một exception thuộc nhóm này có thể giữ tham chiếu tới `Message<?>` bị lỗi.

Ví dụ, `MessageHandlingException` có thể giữ thông điệp mà handler đang xử lý cùng nguyên nhân nghiệp vụ phía dưới. Nhưng không phải mọi `Throwable` đều là `MessagingException`, và `getFailedMessage()` cũng có thể trả `null`.

Cách đọc cơ bản:

```java
Throwable failure = error.getPayload();

Message<?> failedMessage = null;
if (failure instanceof MessagingException messagingException) {
    failedMessage = messagingException.getFailedMessage();
}
```

Các import:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
```

Nếu có lớp wrapper khác bao bên ngoài, cần xem cả chuỗi `getCause()` thay vì chỉ kiểm tra lớp ngoài cùng. Khi có nhiều `MessagingException` trong chuỗi, chọn ngữ cảnh phù hợp với công việc điều tra thay vì mặc định chúng chứa cùng một message.

Hợp đồng nullable của `failedMessage` nằm trong [Javadoc của MessagingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html).

### originalMessage không đồng nghĩa với failedMessage

Xét luồng:

```text
M0: dữ liệu đầu vào
    |
    v
transformer
    |
    v
M1: dữ liệu sau chuyển đổi
    |
    v
handler thất bại
```

Exception tại handler có thể gắn `failedMessage = M1`. Thành phần phát lỗi có thể cung cấp `originalMessage = M0` nếu nó đã giữ được ngữ cảnh M0.

Điều này hữu ích khi muốn đối chiếu dữ liệu trước và sau chuyển đổi. Tuy nhiên, `originalMessage` không phải lúc nào cũng có, và không được bảo đảm là thông điệp đầu tiên của toàn hệ thống. Nó là message được cung cấp tại phạm vi tạo thông điệp lỗi.

Việc một exception có `failedMessage` cũng không tự làm `getOriginalMessage()` khác `null`.

### Headers không tự trở thành bản sao của message nghiệp vụ

Header `id` của thông điệp lỗi nhận diện chính message lỗi. Nó không mặc nhiên là mã đơn hàng hay ID của message nghiệp vụ thất bại.

Tương tự, muốn tìm `businessEventId` hoặc `traceId`, cần xem nó được đặt ở đâu:

- Trong headers của `failedMessage`.
- Trong headers của `originalMessage`.
- Hoặc được chiến lược phát lỗi sao chép/chọn lọc vào headers của `ErrorMessage`.

Không dùng `error.getHeaders().get("orderId")` rồi giả định mọi error publisher đều đã copy header nghiệp vụ sang lớp bao ngoài.

## 4. Tạo một ErrorMessage có hai ngữ cảnh khác nhau

Đoạn mã dưới đây có thể đặt trong một phương thức Java để minh họa cấu trúc:

```java
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

// Bên trong phương thức:
Message<String> original = MessageBuilder
    .withPayload("  order-1001  ")
    .setHeader("businessEventId", "event-1001")
    .build();

Message<String> normalized = MessageBuilder
    .withPayload("ORDER-1001")
    .copyHeaders(original.getHeaders())
    .build();

MessageHandlingException failure =
    new MessageHandlingException(
        normalized,
        "Không thể xử lý đơn hàng đã chuẩn hóa",
        new IllegalArgumentException("Trạng thái đơn hàng không hợp lệ")
    );

ErrorMessage error = new ErrorMessage(
    failure,
    Map.<String, Object>of("errorCategory", "VALIDATION"),
    original
);
```

Kết quả cần đọc:

```text
error.payload                         -> failure
failure.failedMessage.payload         -> "ORDER-1001"
error.originalMessage.payload         -> "  order-1001  "
error.headers["errorCategory"]         -> "VALIDATION"
```

Header nghiệp vụ `businessEventId` có trên hai message nghiệp vụ vì đoạn mã đã chủ động tạo và sao chép nó. Ví dụ chỉ đưa `errorCategory` vào bản đồ headers của thông điệp lỗi.

Các constructor thường dùng:

| Cách tạo | Khi dùng |
| --- | --- |
| `new ErrorMessage(failure)` | Chỉ có lỗi |
| `new ErrorMessage(failure, originalMessage)` | Có thêm message làm ngữ cảnh gốc |
| `new ErrorMessage(failure, headers, originalMessage)` | Cần đặt metadata riêng cho đường lỗi |

Đối tượng `Throwable` không được là `null`. Với các overload khác nhau, dùng biến có kiểu rõ ràng thay vì truyền `null` ở vị trí có thể khiến compiler không chọn được overload.

Các message giữ tham chiếu tới payload. `originalMessage` không tự tạo ảnh chụp sâu của một đối tượng nghiệp vụ có thể thay đổi. Nếu cần một bản ghi phục vụ đối soát lâu dài, hãy thiết kế dữ liệu lưu trữ phù hợp thay vì coi tham chiếu Java là bản lưu bền.

## 5. Khi nào lỗi được phát thành ErrorMessage?

### Đường thực thi đồng bộ

```text
caller thread
  -> DirectChannel
  -> handler
  -> ném exception
  -> exception lan về caller
```

Khi caller trực tiếp gọi `send(...)` qua một chuỗi `DirectChannel` đồng bộ, lỗi của handler có thể lan về theo call stack. Một header `errorChannel` không tự thay đổi cơ chế này.

Nếu muốn bắt lỗi tại tầng gọi và phát thành message, đó phải là một bước xử lý được thiết kế rõ ràng. Gateway hoặc advice cũng có thể cung cấp cơ chế riêng khi được cấu hình.

### Đường có polling hoặc thực thi bất đồng bộ

```text
caller -> QueueChannel -> caller tiếp tục
                |
                v
           poller task
                |
                v
             handler
                |
                v
        error handler / publisher
                |
                v
           ErrorMessage
                |
                v
           kênh xử lý lỗi
```

Lỗi xảy ra sau khi producer đã hoàn tất việc đưa message vào queue không thể quay ngược về một lời gọi `send(...)` đã kết thúc. Hạ tầng polling chuẩn có thể bắt exception và phát `ErrorMessage`.

`ExecutorChannel` cũng tạo ranh giới thực thi khi sử dụng executor bất đồng bộ phù hợp. Một đối tượng thread hoặc executor Java tùy ý nằm ngoài hạ tầng Integration không mặc nhiên có cùng cơ chế phát lỗi.

Các khác biệt về luồng thực thi được giải thích trong [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

## 6. Chọn kênh nhận thông điệp lỗi

Trong cơ chế `MessagePublishingErrorHandler` thông thường, việc chọn kênh có thể hình dung theo thứ tự:

1. Header `errorChannel` của message thất bại, khi exception cung cấp được message đó.
2. Kênh lỗi mặc định được cấu hình cho error handler.
3. Kênh toàn cục `errorChannel` khi dùng mặc định của framework.

Với poller, `@Poller(errorChannel = "orderErrors")` đặt tên kênh mặc định cho error handler của poller. Nó không phải một lệnh vô điều kiện gửi mọi lỗi của toàn ứng dụng vào `orderErrors`.

Header có thể chứa tham chiếu tới một `MessageChannel` hoặc tên kênh được hạ tầng phân giải. Với tên kênh, cần bảo đảm bean tương ứng tồn tại.

Ví dụ đặt đích lỗi theo từng yêu cầu:

```java
Message<String> request = MessageBuilder
    .withPayload("ORDER-2001")
    .setHeader("businessEventId", "event-2001")
    .setErrorChannelName("requestErrors")
    .build();
```

Nếu message này thất bại trong poller của ví dụ phía dưới, `requestErrors` được ưu tiên trước kênh mặc định `orderErrors`. Nếu nguồn ném lỗi trước khi có message hoặc exception không giữ được message cần thiết, không nên mặc định header này có thể được tìm thấy.

API error handler nằm trong [Javadoc của MessagePublishingErrorHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/MessagePublishingErrorHandler.html), còn thuộc tính của poller nằm trong [Javadoc của Poller](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Poller.html).

### Kênh lỗi toàn cục

Hạ tầng Integration mặc định tạo bean `errorChannel` nếu ứng dụng chưa định nghĩa. Kênh mặc định là `PublishSubscribeChannel` và có một `LoggingHandler` đăng ký để ghi lỗi.

Nếu ứng dụng tự khai báo một bean `QueueChannel` mang tên `errorChannel`, nó đã thay đổi đặc tính phân phối. Queue giữ message để consumer đọc; bản thân queue không phải logger.

Trong các phiên bản đang dùng cơ chế mặc định này, kênh lỗi mặc định yêu cầu có subscriber để tránh lặng lẽ bỏ qua lỗi khi không có nơi nhận. Do đó, cần tính cả giai đoạn endpoint dừng hoặc context đang đóng khi thiết kế đường lỗi.

Không dùng `errorChannel` toàn cục như nơi “bắt mọi exception Java”. Một lỗi ở controller, một thread tự tạo hoặc một phương thức dịch vụ thông thường chỉ đi vào đó khi có cơ chế nối tương ứng.

## 7. Ví dụ hoàn chỉnh: cùng lỗi, hai đường thực thi

Cấu hình sau cố ý từ chối mọi đơn hàng. Mục tiêu là quan sát exception và thông điệp lỗi, nên không có logic lưu đơn hàng thật.

Tạo `ErrorMessageConfiguration.java`:

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessageHandlingException;

@Configuration
@EnableIntegration
public class ErrorMessageConfiguration {

    @Bean
    public DirectChannel synchronousOrders() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel queuedOrders() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel orderErrors() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel requestErrors() {
        return new QueueChannel(20);
    }

    @Bean
    @ServiceActivator(inputChannel = "synchronousOrders")
    public MessageHandler synchronousOrderHandler() {
        return ErrorMessageConfiguration::reject;
    }

    @Bean
    @ServiceActivator(
        inputChannel = "queuedOrders",
        poller = @Poller(
            fixedDelay = "100",
            maxMessagesPerPoll = "1",
            receiveTimeout = "0",
            errorChannel = "orderErrors"
        )
    )
    public MessageHandler queuedOrderHandler() {
        return ErrorMessageConfiguration::reject;
    }

    private static void reject(Message<?> message) {
        throw new MessageHandlingException(
            message,
            "Không thể xử lý đơn hàng",
            new IllegalArgumentException("Đơn hàng không hợp lệ")
        );
    }
}
```

Handler chủ động tạo `MessageHandlingException` chứa message để ví dụ có hợp đồng `failedMessage` rõ ràng. Các handler của framework cũng thường bọc lỗi nghiệp vụ bằng exception messaging phù hợp, nhưng không cần dựa vào một chuỗi wrapper cụ thể để hiểu ví dụ này.

Dependency chính là `org.springframework.integration:spring-integration-core`. `@EnableIntegration` cho phép chạy cấu hình bằng `AnnotationConfigApplicationContext` trong môi trường Spring Java Configuration thuần.

Đường thứ nhất:

```text
send -> synchronousOrders -> reject -> exception về caller
```

Đường thứ hai:

```text
send -> queuedOrders -> nhận vào queue
                           |
                      polling task
                           |
                         reject
                           |
                       ErrorMessage
                           |
               requestErrors hoặc orderErrors
```

Không có consumer nghiệp vụ trên hai kênh lỗi vì bài kiểm thử sẽ đọc trực tiếp từ queue. Khi ứng dụng thực có consumer tự động, không đồng thời kỳ vọng bài kiểm thử cũng nhận cùng một message từ chính queue đó.

## 8. Kiểm thử ErrorMessage

Các bài kiểm thử dùng JUnit Jupiter và nằm trong cùng package với cấu hình trên.

### 8.1. Xác minh originalMessage và failedMessage độc lập

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

class ErrorMessageStructureTest {

    @Test
    void keepsOriginalAndFailedMessagesAsSeparateContexts() {
        Message<String> original = MessageBuilder
            .withPayload(" raw-order ")
            .setHeader("businessEventId", "event-structure")
            .build();

        Message<String> failed = MessageBuilder
            .withPayload("NORMALIZED-ORDER")
            .copyHeaders(original.getHeaders())
            .build();

        MessageHandlingException failure =
            new MessageHandlingException(
                failed,
                "Xử lý thất bại",
                new IllegalStateException("Nguồn phụ trợ chưa sẵn sàng")
            );

        ErrorMessage error = new ErrorMessage(failure, original);

        assertSame(failure, error.getPayload());
        assertSame(original, error.getOriginalMessage());
        assertSame(failed, failure.getFailedMessage());
        assertEquals(
            "NORMALIZED-ORDER",
            failure.getFailedMessage().getPayload()
        );

        ErrorMessage withoutOriginal = new ErrorMessage(failure);

        assertNull(withoutOriginal.getOriginalMessage());
        assertSame(
            failed,
            ((MessageHandlingException) withoutOriginal.getPayload())
                .getFailedMessage()
        );
    }
}
```

Bài kiểm thử cho thấy chỉ cần bỏ đối số `original` khi tạo `ErrorMessage` là `getOriginalMessage()` có thể rỗng, trong khi `failedMessage` trên exception vẫn tồn tại.

Không dùng phép kiểm tra tham chiếu `assertSame` để suy ra dữ liệu nghiệp vụ đã được sao chép sâu. Nó chỉ xác nhận những đối tượng được truyền vào constructor trong ví dụ.

### 8.2. Xác minh đường đi của lỗi đồng bộ và lỗi polling

Tạo `ErrorMessageFlowTest.java`:

```java
package example.integration;

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

class ErrorMessageFlowTest {

    @Test
    void synchronousExceptionStillReturnsToCaller() {
        try (var context = new AnnotationConfigApplicationContext(
                ErrorMessageConfiguration.class)) {

            MessageChannel input = context.getBean(
                "synchronousOrders", MessageChannel.class);
            QueueChannel errors = context.getBean(
                "requestErrors", QueueChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("ORDER-SYNC")
                .setErrorChannelName("requestErrors")
                .build();

            MessagingException failure = assertThrows(
                MessagingException.class,
                () -> input.send(request)
            );

            assertNotNull(failure.getFailedMessage());
            assertEquals(
                "ORDER-SYNC",
                failure.getFailedMessage().getPayload()
            );
            assertNull(errors.receive(0));
        }
    }

    @Test
    void polledFailureUsesConfiguredDefaultErrorChannel() {
        try (var context = new AnnotationConfigApplicationContext(
                ErrorMessageConfiguration.class)) {

            MessageChannel input = context.getBean(
                "queuedOrders", MessageChannel.class);
            QueueChannel errors = context.getBean(
                "orderErrors", QueueChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("ORDER-ASYNC")
                .setHeader("businessEventId", "event-async")
                .build();

            assertTrue(input.send(request, 1_000));

            Message<?> received = errors.receive(3_000);
            assertNotNull(received);
            assertTrue(received instanceof ErrorMessage);

            ErrorMessage error = (ErrorMessage) received;
            assertTrue(error.getPayload() instanceof MessagingException);

            MessagingException failure =
                (MessagingException) error.getPayload();
            Message<?> failed = failure.getFailedMessage();

            assertNotNull(failed);
            assertEquals("ORDER-ASYNC", failed.getPayload());
            assertEquals(
                "event-async",
                failed.getHeaders().get("businessEventId")
            );
            assertTrue(
                failure.getCause() instanceof IllegalArgumentException
            );
        }
    }

    @Test
    void requestErrorHeaderOverridesPollerDefault() {
        try (var context = new AnnotationConfigApplicationContext(
                ErrorMessageConfiguration.class)) {

            MessageChannel input = context.getBean(
                "queuedOrders", MessageChannel.class);
            QueueChannel requestErrors = context.getBean(
                "requestErrors", QueueChannel.class);
            QueueChannel defaultErrors = context.getBean(
                "orderErrors", QueueChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("ORDER-OVERRIDE")
                .setErrorChannelName("requestErrors")
                .build();

            assertTrue(input.send(request, 1_000));

            Message<?> received = requestErrors.receive(3_000);
            assertNotNull(received);
            assertTrue(received instanceof ErrorMessage);
            assertNull(defaultErrors.receive(0));
        }
    }
}
```

Những điều được xác minh:

- Header lỗi không tự biến một lời gọi đồng bộ thành phát message lỗi.
- Poller phát `ErrorMessage` tới kênh mặc định khi không có header ghi đè.
- Header theo yêu cầu có thể chọn kênh khác trước kênh mặc định của poller.
- Payload nghiệp vụ và metadata được truy lại từ `failedMessage`.

Các bài kiểm thử không buộc `getOriginalMessage()` phải khác `null` vì ngữ cảnh đó phụ thuộc cách tạo lỗi. Chúng dùng `receive(timeout)` để chờ message, không dùng `Thread.sleep(...)` để đoán thời điểm polling hoàn tất.

Mỗi bài đóng context bằng `try-with-resources` nhằm dừng tài nguyên polling sau kiểm thử. Giới hạn ba giây là thời gian chờ của ví dụ, không phải cam kết độ trễ của ứng dụng.

Đây là kiểm thử hợp đồng truyền lỗi trong cấu hình tối giản. Chúng chưa chứng minh retry, transaction, lưu bền hay khả năng chịu tải của hệ thống.

## 9. Xử lý và định tuyến thông điệp lỗi

Một error handler có thể cần:

1. Đọc loại lỗi và nguyên nhân.
2. Tìm message nghiệp vụ liên quan, nếu có.
3. Trích xuất khóa sự kiện và metadata phục vụ đối soát.
4. Chọn đường xử lý: từ chối nghiệp vụ, xem xét retry hoặc chuyển người vận hành.

Không chỉ dùng `failure.getMessage()` để quyết định hành vi. Chuỗi thông báo có thể thay đổi và không thay thế được loại exception hay mã lỗi nghiệp vụ.

### Đọc thông tin theo hợp đồng rõ ràng

Một hàm hỗ trợ tối giản:

```java
public static Message<?> failedMessageOf(ErrorMessage error) {
    Throwable failure = error.getPayload();

    if (failure instanceof MessagingException messagingException) {
        return messagingException.getFailedMessage();
    }

    return null;
}
```

Hàm này chỉ kiểm tra lớp exception ngoài cùng. Nếu ứng dụng có nhiều lớp wrapper, hãy mở rộng việc duyệt nguyên nhân theo hợp đồng thực tế.

Sau khi lấy được message, vẫn phải kiểm tra giá trị rỗng:

```java
Message<?> failed = failedMessageOf(error);
Message<?> original = error.getOriginalMessage();

Object businessEventId = null;

if (failed != null) {
    businessEventId = failed.getHeaders().get("businessEventId");
}

if (businessEventId == null && original != null) {
    businessEventId =
        original.getHeaders().get("businessEventId");
}
```

Đoạn fallback trên chỉ tìm một trường metadata. Nó không tuyên bố rằng `failed` và `original` có cùng payload hoặc có thể được dùng thay thế nhau để gửi lại nghiệp vụ.

### Định tuyến dựa trên loại exception

`ErrorMessageExceptionTypeRouter` tìm kênh theo loại nguyên nhân phù hợp nhất có mapping, kể cả trong chuỗi cause. Điều này hữu ích khi lớp ngoài là `MessageHandlingException` nhưng nguyên nhân nghiệp vụ nằm bên trong.

Ví dụ cấu hình độc lập:

```java
package example.integration;

import java.io.IOException;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.router.ErrorMessageExceptionTypeRouter;

@Configuration
@EnableIntegration
public class ErrorRoutingConfiguration {

    @Bean
    public DirectChannel errorEvents() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel invalidOrderErrors() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel retryCandidates() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel unclassifiedErrors() {
        return new QueueChannel(20);
    }

    @Bean
    @ServiceActivator(inputChannel = "errorEvents")
    public ErrorMessageExceptionTypeRouter errorClassifier() {
        ErrorMessageExceptionTypeRouter router =
            new ErrorMessageExceptionTypeRouter();

        router.setChannelMapping(
            IllegalArgumentException.class.getName(),
            "invalidOrderErrors"
        );
        router.setChannelMapping(
            IOException.class.getName(),
            "retryCandidates"
        );
        router.setDefaultOutputChannelName("unclassifiedErrors");

        return router;
    }
}
```

Một publisher hoặc đoạn xử lý lỗi phải gửi `ErrorMessage` vào `errorEvents` thì router mới hoạt động. Cấu hình này không tự nối vào poller ở phần 7.

Sơ đồ:

```text
ErrorMessage -> errorEvents -> router
                              ├── IllegalArgumentException -> invalidOrderErrors
                              ├── IOException              -> retryCandidates
                              └── chưa phân loại            -> unclassifiedErrors
```

Router chuyển tiếp thông điệp lỗi; nó không biến payload thành đơn hàng và không thực hiện retry. `retryCandidates` chỉ là nơi tập hợp lỗi cần đánh giá. Không phải mọi `IOException` đều an toàn để thử lại một thao tác có tác dụng phụ.

Ngữ nghĩa chọn mapping được mô tả tại [Javadoc của ErrorMessageExceptionTypeRouter](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/ErrorMessageExceptionTypeRouter.html).

## 10. Chiến lược tạo thông điệp lỗi

`ErrorMessageStrategy` tách việc tạo `ErrorMessage` khỏi thành phần phát lỗi. Nó nhận `Throwable` và một ngữ cảnh `AttributeAccessor` có thể rỗng.

`DefaultErrorMessageStrategy` lấy message từ thuộc tính `ErrorMessageUtils.INPUT_MESSAGE_CONTEXT_KEY` của ngữ cảnh khi thuộc tính đó có mặt để đặt `originalMessage`. Nếu không có thông tin này, nó tạo message lỗi chỉ mang throwable.

Đây là lý do một lỗi có `failedMessage` vẫn có thể không có `originalMessage`. Hai dữ liệu được cung cấp qua hai cơ chế khác nhau.

Một strategy tùy chỉnh có thể thêm metadata của chính đường lỗi:

```java
import java.util.Map;

import org.springframework.integration.support.ErrorMessageStrategy;
import org.springframework.integration.support.ErrorMessageUtils;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

// Biến cục bộ hoặc phần khởi tạo strategy:
ErrorMessageStrategy strategy = (failure, attributes) -> {
    Message<?> original = null;

    if (attributes != null) {
        Object candidate = attributes.getAttribute(
            ErrorMessageUtils.INPUT_MESSAGE_CONTEXT_KEY
        );

        if (candidate instanceof Message<?> message) {
            original = message;
        }
    }

    return new ErrorMessage(
        failure,
        Map.<String, Object>of("errorOrigin", "order-flow"),
        original
    );
};
```

Đoạn mã tạo strategy, chưa gắn nó vào publisher. Muốn có hiệu lực, phải cấu hình strategy trên component hỗ trợ, chẳng hạn qua `setErrorMessageStrategy(...)` của publisher phù hợp.

Chỉ đăng ký một bean `ErrorMessageStrategy` không có nghĩa mọi thành phần phát lỗi trong ứng dụng tự động sử dụng nó. Một số adapter có strategy chuyên dụng để giữ thêm ngữ cảnh transport; cần xem hợp đồng của adapter trước khi thay thế.

Xem [ErrorMessageStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/ErrorMessageStrategy.html) và [DefaultErrorMessageStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/DefaultErrorMessageStrategy.html).

## 11. ErrorMessage không tự cung cấp retry hoặc rollback

### Phân biệt các bước

```text
thất bại
   |
   v
retry theo chính sách, nếu được cấu hình
   |
   v
hết lượt thử
   |
   v
recovery / phát ErrorMessage
   |
   v
xử lý lỗi cuối cùng hoặc lưu để xem xét tiếp
```

Một `ErrorMessage` có thể xuất hiện ngay khi lỗi xảy ra hoặc sau khi retry hết lượt, tùy vị trí và cấu hình phát lỗi. Không suy ra số lần thử chỉ từ việc thấy một message lỗi.

`ErrorMessageSendingRecoverer` là một cơ chế gửi lỗi cuối cùng thành `ErrorMessage` sau khi retry cạn. Cần gắn recoverer và retry advice theo thiết kế; tạo bean recoverer riêng lẻ chưa làm mọi handler có retry. Xem [Javadoc của ErrorMessageSendingRecoverer](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.html).

### Phát lỗi không khôi phục thông điệp nguồn

Trong ví dụ `queuedOrders`, poller đã lấy message khỏi queue trước khi handler thất bại. Việc tạo `ErrorMessage` không tự đưa message cũ trở lại hàng đợi.

Nếu muốn gửi lại, phải quyết định rõ:

- Gửi lại message ở điểm thất bại hay dựng lại đầu vào ban đầu.
- Giới hạn số lần và thời gian giữa các lần thử.
- Ngăn xử lý trùng khi lần trước đã tạo một phần tác dụng phụ.
- Chuyển lỗi sang đâu khi không còn khả năng phục hồi tự động.

Nếu đã có request header `errorChannel` trỏ về một đường cũ, cũng cần xem xét hợp đồng header khi phát lại để tránh vô tình quay lại cùng chu trình lỗi.

### ErrorMessage không phải chỉ thị transaction

Rollback phụ thuộc transaction manager, tài nguyên tham gia và vị trí exception được truyền hoặc xử lý. Một message lỗi được gửi thành công không tự chứng minh transaction nghiệp vụ đã rollback.

Tương tự, chuyển công việc qua queue hoặc executor không tự truyền transaction gắn với thread producer sang thread consumer.

Đặc biệt, khi recovery bắt và xử lý lỗi, cần hiểu cơ chế đó có còn truyền exception về ranh giới transaction hay không. Thiết kế theo hợp đồng của transaction và advice cụ thể, thay vì dùng sự có mặt của `ErrorMessage` làm tín hiệu commit/rollback.

### Queue lỗi chưa phải dead-letter storage

`QueueChannel(20)` của ví dụ là queue trong bộ nhớ. Nó không giữ dữ liệu qua lần khởi động lại và không tự quản lý trạng thái “đã xem xét” hay “đã gửi lại”.

Nếu cần lưu lỗi để xử lý sau, hãy xác định nơi lưu bền, dữ liệu cần lưu, khóa nghiệp vụ và quy trình thay đổi trạng thái. Một kho lỗi có thể lưu các trường như:

| Dữ liệu | Mục đích |
| --- | --- |
| `businessEventId` | Liên kết với sự kiện nghiệp vụ, hỗ trợ chống xử lý trùng |
| Thời điểm và bước thất bại | Xác định phạm vi xảy ra lỗi |
| Loại lỗi / mã lỗi | Phân loại và tìm kiếm |
| Số lượt thử | Kiểm soát chính sách phục hồi |
| Dữ liệu đầu vào cần thiết hoặc tham chiếu tới nó | Hỗ trợ tái hiện và xử lý lại có kiểm soát |
| Trạng thái xử lý lỗi | Theo dõi lỗi đã được nhận, đang xử lý hay đã kết thúc |

Không mặc định gửi nguyên đồ thị đối tượng `Throwable` cùng các message Java qua mọi transport là một hợp đồng dữ liệu ổn định. Khi đi ra ngoài tiến trình, thường cần ánh xạ sang cấu trúc lỗi rõ ràng, có serializer và phiên bản dữ liệu phù hợp.

## 12. Bản thân đường xử lý lỗi cũng có thể thất bại

`ErrorMessage` là message nên việc gửi và xử lý nó có thể gặp vấn đề:

- Kênh lỗi `DirectChannel` không có subscriber.
- Queue lỗi đầy và thao tác gửi bị chặn hoặc hết thời gian chờ.
- Handler ghi lỗi ném exception khi database lỗi.
- Consumer lỗi phát lại cùng dữ liệu mà không có điều kiện kết thúc.

Một error flow được gọi qua kênh đồng bộ có thể chạy ngay trên thread đang báo lỗi. Việc tạo `ErrorMessage` không tự tạo thread mới và không bảo đảm tác vụ chính được giải phóng ngay.

Tránh cấu hình kiểu:

```text
errorEvents -> handler lỗi -> ném lỗi -> errorEvents -> ...
```

Hãy có điểm kết thúc và chính sách riêng cho trường hợp lưu hoặc gửi lỗi thất bại. Đồng thời, giữ đủ metadata để phân biệt lỗi nghiệp vụ ban đầu với lỗi của chính cơ chế ghi nhận.

Khi một thao tác xử lý lỗi có tác dụng phụ, chẳng hạn gửi yêu cầu bồi hoàn, dùng khóa nghiệp vụ và quy trình chống trùng phù hợp. Mỗi lần phát message lỗi mới có thể có message ID mới dù nó vẫn mô tả cùng một sự kiện ban đầu.

## 13. Chẩn đoán nhanh khi làm việc với ErrorMessage

| Biểu hiện | Cần kiểm tra |
| --- | --- |
| Có header `errorChannel` nhưng caller vẫn nhận exception | Đường thực thi có đang đồng bộ, và có component nào bắt/phát lỗi không? |
| Không ép được payload sang `Order` | Payload hiện tại là `Throwable`; dữ liệu nghiệp vụ nằm trong message liên quan |
| `getOriginalMessage()` trả `null` | Strategy hoặc publisher có nhận được ngữ cảnh gốc không? |
| `getFailedMessage()` trả `null` | Exception có được tạo kèm message không, và đang xem đúng wrapper chưa? |
| Không tìm thấy header nghiệp vụ trên error envelope | Header có nằm trên `failedMessage` hoặc `originalMessage` không? |
| Lỗi đi tới kênh khác với mặc định poller | Message thất bại có header `errorChannel` ghi đè không? |
| Lỗi được phát nhưng không có log | Kênh lỗi là loại gì, đã có consumer/logger chưa? |
| Test không nhận được message lỗi | Có consumer khác đang đọc cùng queue, hoặc đang kiểm tra trước khi poller xử lý không? |
| Đã có message lỗi nhưng dữ liệu không được gửi lại | Retry/recovery có được cấu hình, và dữ liệu nguồn còn ở đâu? |
| Message lỗi xuất hiện lặp lại | Nguồn đang gửi lại, retry phát nhiều lần, hay error flow đang tạo vòng lặp? |

Khi điều tra, lần lượt xác định **exception nào**, **message nào thất bại**, **component nào phát ErrorMessage** và **kênh nào nhận nó**. Bốn điểm này giúp nối thông tin kỹ thuật với sự kiện nghiệp vụ và chọn đúng nơi sửa luồng.
