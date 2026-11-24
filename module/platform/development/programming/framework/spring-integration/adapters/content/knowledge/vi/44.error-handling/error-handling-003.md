# ErrorMessage và MessagingException trong Spring Integration

## 1. Hai khái niệm cốt lõi của xử lý lỗi bằng message

Khi kết nối hệ thống ngoài qua **Spring Integration**, ứng dụng thường có chuỗi xử lý **inbound adapter/gateway → MessageChannel → transformer hoặc service activator → outbound adapter/gateway**. Thông điệp mang payload và headers; hệ thống có thể xử lý đồng bộ trong luồng gọi ban đầu hoặc bất đồng bộ qua poller, queue, task executor hay listener.

Lỗi có thể xuất hiện ở bất kỳ giai đoạn nào: đọc file, kết nối SFTP, chuyển đổi JSON, gọi HTTP, nhận/gửi JMS, AMQP, Kafka hay lưu cơ sở dữ liệu. **ErrorMessage** và **MessagingException** giúp mang thông tin thất bại qua các ranh giới xử lý, nhưng có hai vai trò khác nhau:

- **MessagingException:** một **ngoại lệ Java** thuộc họ Spring Messaging, có thể gắn với **Message bị lỗi**. Nó mô tả một thất bại khi gửi, chuyển đổi, xử lý hay định tuyến message.
- **ErrorMessage:** một **Spring Message** có payload là **Throwable**, thường là MessagingException. Nó được sử dụng khi một cơ chế xử lý lỗi **chuyển ngoại lệ thành message và publish tới một MessageChannel**.

Một cách ghi nhớ:

~~~text
Ngoại lệ trong code                 Sự kiện lỗi đi qua message channel
┌─────────────────────┐              ┌────────────────────────────┐
│ MessagingException  │  --wrap-->   │ ErrorMessage               │
│  failedMessage?     │              │  payload: Throwable        │
│  cause?             │              │  originalMessage?          │
└─────────────────────┘              │  headers                   │
                                     └────────────────────────────┘
~~~

Mũi tên wrap là **một khả năng xử lý**, không phải một bước luôn xảy ra. Trong một flow đồng bộ dùng DirectChannel, ngoại lệ có thể được ném về caller mà **không phát sinh ErrorMessage**. Ngược lại, một poller hoặc task bất đồng bộ với error publisher có thể tạo ErrorMessage để thông báo thất bại qua channel.

### Mục tiêu bài học

Sau khi hoàn thành, người học có thể:

1. Phân biệt Message, Throwable, MessagingException và ErrorMessage.
2. Đọc **failedMessage**, **originalMessage**, các header và chuỗi cause một cách an toàn.
3. Giải thích khi nào lỗi được throw về sender và khi nào được publish tới error channel.
4. Tạo/nhận ErrorMessage, dùng MessagingException và các subclass đúng mục đích.
5. Hiểu **ErrorMessageStrategy**, header errorChannel và kênh lỗi toàn cục.
6. Phân loại lỗi trong File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC mà không nhầm exception với retry/ack.
7. Viết test kiểm tra hợp đồng lỗi và thiết kế logging, recovery, bảo mật, vận hành.

Trong phạm vi module **SPRING_INTEGRATION_ADAPTERS**, trọng tâm là cách hai kiểu dữ liệu này liên kết các adapter với **MessageChannel**, gateway, poller, hợp đồng message và vòng đời kết nối. Bài trình bày cơ chế chung trước; những hành vi chuyên biệt của từng adapter cần được kiểm chứng theo dependency và cách cấu hình thực tế.

## 2. Phân biệt ErrorMessage, MessagingException và các thành phần liên quan

| Khái niệm | Bản chất | Chứa gì? | Dùng ở đâu? |
|---|---|---|---|
| Message<?> | Hợp đồng thông điệp của Spring Messaging | Payload và headers | Giao tiếp giữa endpoint và channel |
| Throwable | Gốc phân cấp lỗi Java | Message, cause, stack trace | Biểu diễn lỗi Java |
| MessagingException | Runtime exception của Spring Messaging | Thông tin lỗi, cause và failedMessage tùy trường hợp | Báo thất bại của xử lý message |
| MessageHandlingException | Subclass của MessagingException | Ngữ cảnh thất bại khi handler xử lý | Service activator, transformer, handler |
| MessageDeliveryException | Subclass của MessagingException | Ngữ cảnh không gửi/phân phối message như mong đợi | Gửi tới channel/handler |
| MessageConversionException | Subclass của MessagingException | Ngữ cảnh conversion không hợp lệ | Message conversion |
| ErrorMessage | Message<Throwable> | Throwable payload, headers, optional originalMessage | Luồng xử lý lỗi bằng channel |
| ErrorMessageStrategy | Cách tạo ErrorMessage từ Throwable và context | Logic dựng message lỗi | Error publishing component |
| ErrorMessagePublisher | Hạ tầng publish ErrorMessage | Error destination và strategy | Recovery/error flow nếu được cấu hình |
| errorChannel | Tên message channel thông dụng | Chở ErrorMessage | Điểm đến xử lý lỗi |

**Phân biệt package:** MessagingException, MessageHandlingException và MessageDeliveryException thuộc **org.springframework.messaging**; ErrorMessage thuộc **org.springframework.messaging.support**; còn một số hạ tầng publish/strategy thuộc **org.springframework.integration.support** hoặc package tương ứng theo phiên bản.

### 2.1. Ngoại lệ không phải một Spring Message

Một IllegalStateException ném từ service activator vẫn là Throwable Java. Nó **không tự có headers**, không tự đi vào errorChannel và không tự chứa message đang xử lý. Spring Integration có thể bao bọc exception bằng MessagingException hoặc chuyển thành ErrorMessage tùy điểm xử lý. Cần kiểm tra luồng thực thi thay vì suy từ tên exception.

### 2.2. ErrorMessage là message về lỗi, không phải bản sao dữ liệu nghiệp vụ

Nếu input payload là OrderCommand và handler thất bại, ErrorMessage sẽ có payload là một Throwable — **không phải OrderCommand**. Muốn replay phải lấy dữ liệu nghiệp vụ từ failedMessage, originalMessage hoặc kho recovery đáng tin cậy; không gửi thẳng ErrorMessage vào input channel đang chờ OrderCommand.

### 2.3. Exception có thể không thuộc họ MessagingException

Payload của ErrorMessage được định nghĩa là **Throwable**. Nó có thể chứa MessagingException, IllegalArgumentException, IOException đã được đưa vào hoặc một Throwable khác. Do đó:

- Không ép kiểu mọi ErrorMessage payload sang MessagingException;
- Dùng instanceof trước khi gọi getFailedMessage();
- Không mặc định ErrorMessage luôn chứa originalMessage;
- Phân loại root cause phù hợp, không bỏ qua wrapper context.

## 3. Cấu trúc MessagingException

Theo Spring Messaging, MessagingException là nền tảng cho các lỗi messaging và kế thừa từ một loại **unchecked exception**. Nó có thể giữ tham chiếu tới message tại thời điểm thất bại thông qua phương thức **getFailedMessage()**; giá trị này có thể **null** nếu exception được tạo không kèm message.

### 3.1. Cây phân loại đơn giản

~~~mermaid
flowchart TD
    T["Throwable / RuntimeException"]
    M["MessagingException"]
    H["MessageHandlingException"]
    D["MessageDeliveryException"]
    C["MessageConversionException"]
    R["DestinationResolutionException"]
    O["Các subclass khác tùy phiên bản"]
    T --> M
    M --> H
    M --> D
    M --> C
    M --> R
    M --> O
~~~

Sơ đồ chỉ là rút gọn họ exception. Spring có thể bổ sung subclass ở các phiên bản và module khác. Một exception nghiệp vụ hoặc exception của thư viện adapter (HTTP client, JDBC driver, JMS API...) có thể nằm trong **cause chain** thay vì là subclass trực tiếp.

### 3.2. Cấu trúc constructor thường dùng

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

Message<String> input = MessageBuilder
        .withPayload("order-274")
        .setHeader("correlationId", "import-274")
        .build();

MessagingException withoutMessage =
        new MessagingException("No message context");

MessagingException withMessage =
        new MessagingException(input, "Import failed",
                new IllegalStateException("Database unavailable"));

System.out.println(withoutMessage.getFailedMessage()); // Có thể null
System.out.println(withMessage.getFailedMessage() == input); // true
System.out.println(withMessage.getCause().getClass().getSimpleName());
~~~

Vì failedMessage có thể null, code nhận exception không được truy cập getHeaders() trực tiếp nếu chưa kiểm tra. **getCause()** là cause Java, không phải nội dung của failedMessage.

### 3.3. MessageHandlingException và MessageDeliveryException

**MessageHandlingException** thường được dùng khi một handler xử lý message gặp lỗi, bao gồm trường hợp framework bao bọc exception từ logic nghiệp vụ. **MessageDeliveryException** diễn tả việc phân phối/gửi message gặp vấn đề. Không nên quyết định permanent/transient **chỉ** dựa vào class: một MessageHandlingException có thể bọc timeout tạm thời, còn một MessageDeliveryException có thể do kênh đích không tồn tại hoặc sai cấu hình lâu dài.

Ví dụ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.MessageDeliveryException;

MessageHandlingException handling = new MessageHandlingException(
        input, "Order validation failed",
        new IllegalArgumentException("Missing customerId"));

MessageDeliveryException delivery = new MessageDeliveryException(
        input, "Cannot deliver to outbound channel");
~~~

Các ví dụ minh họa kiểu exception và mục đích. Khi dùng phiên bản Spring Framework khác, cần đối chiếu constructor và package trong Javadoc tương ứng với dependency thực tế.

### 3.4. Giữ wrapper context và root cause

Thông tin hữu ích thường nằm ở hai tầng:

| Tầng | Ý nghĩa | Ví dụ |
|---|---|---|
| MessagingException | Flow/Message nào thất bại? | failedMessage ID, correlation |
| Cause gần nhất | Handler hoặc thư viện đã throw gì? | DataAccessException |
| Root cause | Nguyên nhân kỹ thuật sâu nhất khi có | SQLTransientConnectionException |

Không nên luôn bỏ lớp wrapper bằng cách chỉ log root cause: như vậy có thể mất failedMessage và địa điểm trong integration flow. Ngược lại, chỉ log tên MessageHandlingException có thể bỏ sót lỗi DB thật. Hướng phù hợp là lưu **exception type, safe context và cause chain**.

## 4. Cấu trúc ErrorMessage: payload, headers và originalMessage

**ErrorMessage** kế thừa từ GenericMessage<Throwable>. API của nó có getPayload(), getHeaders() và **getOriginalMessage()** (có thể null). Việc bổ sung originalMessage giúp giữ đầu vào lúc xây dựng error message nếu dữ liệu đã bị biến đổi trước khi exception xảy ra.

### 4.1. Ví dụ một flow biến đổi dữ liệu

~~~mermaid
sequenceDiagram
    participant F as File inbound
    participant T as Transformer
    participant H as JDBC handler
    participant E as Error publisher
    participant CH as errorChannel
    F->>T: M0: File payload + headers
    T->>H: M1: OrderCommand + headers
    H-->>E: MessagingException có failedMessage=M1
    E->>CH: ErrorMessage payload=exception
    Note over E,CH: originalMessage có thể là M0 hoặc input được strategy cung cấp
~~~

Sơ đồ mô tả **khả năng có originalMessage**, không cam kết rằng mọi flow và error strategy tự giữ M0. Nếu framework chỉ thấy input tại điểm handler đã biến đổi, originalMessage có thể là M1; nếu không có context, trường này có thể null.

### 4.2. So sánh ba bối cảnh khác nhau

| Giá trị | Nằm ở đâu? | Có bắt buộc? | Ý nghĩa |
|---|---|---|---|
| ErrorMessage.payload | error.getPayload() | Có, là Throwable | Ngoại lệ đã được publish |
| MessagingException.failedMessage | exception.getFailedMessage() | Không | Message gắn với exception tại vị trí lỗi |
| ErrorMessage.originalMessage | error.getOriginalMessage() | Không | Message gốc do error builder/strategy cung cấp |
| ErrorMessage.headers | error.getHeaders() | Có | Metadata của message lỗi, không nhất thiết là headers input |
| failedMessage.headers | failed.getHeaders() | Chỉ khi failedMessage tồn tại | Metadata tại vị trí message thất bại |
| exception.cause | throwable.getCause() | Không | Nguyên nhân sâu hơn trong chuỗi exception |

**Điểm dễ nhầm:** ErrorMessage không có phương thức getFailedMessage() riêng. Muốn lấy failedMessage, cần kiểm tra payload có phải MessagingException, rồi gọi **MessagingException.getFailedMessage()**. Ngược lại, originalMessage là phương thức trực tiếp của ErrorMessage.

### 4.3. Tạo ErrorMessage bằng constructor

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

Message<String> original = MessageBuilder
        .withPayload("raw-order-274")
        .setHeader("correlationId", "import-274")
        .build();

Message<Integer> transformed = MessageBuilder
        .withPayload(274)
        .setHeader("correlationId", "import-274")
        .build();

MessageHandlingException exception = new MessageHandlingException(
        transformed, "Could not persist order",
        new IllegalStateException("DB offline"));

ErrorMessage error = new ErrorMessage(exception, original);

System.out.println(error.getPayload() == exception);          // true
System.out.println(error.getOriginalMessage() == original);   // true
System.out.println(exception.getFailedMessage() == transformed); // true
~~~

Ở đây error message có **payload là exception**, exception chứa **failedMessage=transformed**, còn ErrorMessage giữ **originalMessage=original** vì code đã cung cấp rõ ràng. Constructor này **không** tự suy ra message gốc từ call stack.

### 4.4. Headers của ErrorMessage không thay headers gốc

Một ErrorMessage được tạo mới có metadata riêng như ID và timestamp. Dữ liệu trace/correlation của message nguồn **không nhất thiết** xuất hiện trực tiếp ở error.getHeaders(). Nếu cần correlation, kiểm tra originalMessage hoặc failedMessage và fallback theo thông tin recovery context. Không ép kiểu hoặc ghi toàn bộ headers vào log vì chúng có thể chứa credential, token hay thông tin nhạy cảm.

## 5. Khi nào ngoại lệ trở thành ErrorMessage?

Đây là câu hỏi cốt lõi trong hệ thống tích hợp. **Sự tồn tại của errorChannel không bảo đảm mọi exception được publish**.

### 5.1. DirectChannel đồng bộ

~~~text
Caller
  |
  v
DirectChannel ---> Service Activator ---> Exception
  ^                                       |
  |-------------- throw -----------------+
~~~

DirectChannel thường gọi handler trên luồng của sender. Exception không được bắt trong flow có thể lan ngược caller. Một gateway hoặc template có thể có cơ chế ánh xạ exception theo contract, nhưng **không mặc định có ErrorMessage**.

### 5.2. Poller hoặc xử lý bất đồng bộ

~~~text
Scheduler/Executor --> Poller/Handler --> Exception
                                           |
                                   Error handler bắt lỗi
                                           |
                                   ErrorMessageStrategy
                                           |
                                 ErrorMessage -> Channel
~~~

Trong cấu hình Spring Integration thông dụng, task chạy qua scheduler/executor và poller có thể sử dụng **MessagePublishingErrorHandler** để publish ErrorMessage. Khi không có error destination cụ thể, global **errorChannel** có thể được dùng làm fallback.

Điều này phụ thuộc **error strategy, task scheduler và adapter/container**. Không được suy rằng mọi lỗi ở JMS/AMQP/Kafka listener đều tự đi qua cùng errorChannel mà không cần cấu hình.

### 5.3. Gateway và lỗi trả về caller

Messaging gateway có contract request/reply. Theo mặc định, nhiều lỗi downstream có thể được **unwrap và ném trở lại người gọi**. Nếu gateway được cấu hình một error flow phù hợp, lỗi có thể được định tuyến thành message và kết quả được chuyển thành reply hoặc Throwable trả về caller, tùy cấu hình.

Khi một handler trả về một message có Throwable payload, gateway có thể coi đó là lỗi cần ném về caller theo cơ chế gateway. Đây là hành vi khác với một service activator tự ý trả ErrorMessage vào một kênh nghiệp vụ thông thường; cần đọc đúng gateway contract.

### 5.4. Hành vi tham khảo

| Tình huống | Exception ban đầu | Có ErrorMessage? | Điều cần kiểm chứng |
|---|---|---|---|
| DirectChannel + handler đồng bộ | Thường về sender | Không tự động | Caller/advice/gateway |
| Scheduler poller + error publisher | Bị handler của task bắt | Có thể publish | Error strategy và channel |
| ExecutorChannel | Exception ngoài sender thread | Có thể publish | Executor và error handler |
| QueueChannel với consumer poller | Consumer nhận và xử lý trên nhịp riêng | Có thể publish | Consumer poller policy |
| HTTP inbound gateway đồng bộ | Lỗi có thể ném về request | Không tự động vào global | HTTP status, response/error flow |
| JMS/AMQP inbound adapter | Có container/broker semantics | Tùy adapter/cấu hình | Ack, rollback, redelivery |
| Kafka inbound | Có container và offset | Tùy adapter/cấu hình | Commit, retry, DLT |

## 6. errorChannel và cách định tuyến ErrorMessage

### 6.1. Kênh toàn cục

Spring Integration cung cấp một kênh tên **errorChannel** trong cấu hình mặc định thông dụng. Theo tài liệu tham khảo, kênh mặc định là **PublishSubscribeChannel**, có **LoggingHandler** đăng ký để ghi lỗi. Các cấu hình ứng dụng có thể thay thế hoặc tùy chỉnh nó.

Khi một thành phần hỗ trợ error publishing, thường có hai nguồn chọn error destination:

1. **errorChannel header** của request Message (nếu được thành phần đó hỗ trợ và có thể phân giải);
2. **global errorChannel** khi không có destination riêng thích hợp.

Header dùng tên chuẩn **MessageHeaders.ERROR_CHANNEL**. Nó không phải Throwable và không phải một ErrorMessage. Header có thể chứa tên kênh hoặc tham chiếu được hỗ trợ bởi resolver; kết quả phụ thuộc cơ chế gửi lỗi cụ thể.

### 6.2. Ví dụ gắn header errorChannel

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<String> request = MessageBuilder
        .withPayload("order-274")
        .setHeader(MessageHeaders.ERROR_CHANNEL, "orderErrors")
        .setHeader("correlationId", "import-274")
        .build();
~~~

Đoạn code **chỉ gắn header**. Nó không tạo bean orderErrors, không tự bắt exception và không bảo đảm handler đồng bộ sẽ phát ErrorMessage. Cần tạo channel/consumer phù hợp và cấu hình error-publishing path thực sự đọc header.

### 6.3. Subscriber của PublishSubscribeChannel

~~~text
                      +--> LoggingHandler (nếu còn trong cấu hình)
ErrorMessage --> errorChannel
                      +--> Custom error observer
                      +--> Metrics/alerting observer
~~~

Nhiều subscriber có thể nhận cùng một ErrorMessage. Một handler bổ sung có thể làm **log lỗi trùng** nếu LoggingHandler mặc định vẫn hoạt động. Nếu handler có side effect như gửi email, ghi DB hoặc retry, cần thiết kế trách nhiệm và idempotency riêng, không tưởng rằng chỉ một handler sẽ nhận message.

Trong những phiên bản Spring Integration, global channel có thể có cấu hình **requireSubscribers** để không im lặng bỏ qua message khi không có subscriber; hành vi cụ thể phụ thuộc phiên bản và cấu hình ứng dụng. Đừng tự thay thế bean toàn cục chỉ để tiện đọc lỗi; một kênh riêng theo flow thường an toàn hơn khi recovery cần chính sách riêng.

## 7. Viết ErrorMessage handler an toàn

### 7.1. Lắng nghe kênh lỗi bằng Service Activator

Ví dụ dưới đây dùng **@ServiceActivator** để đăng ký handler cho những ErrorMessage được publish tới kênh mặc định. Nó phân biệt wrapper, failedMessage và originalMessage và tránh log thẳng payload nghiệp vụ.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class IntegrationFailureObserver {

    private static final Logger log =
            LoggerFactory.getLogger(IntegrationFailureObserver.class);

    @ServiceActivator(inputChannel = "errorChannel")
    public void onError(ErrorMessage error) {
        Throwable failure = error.getPayload();
        Message<?> failedMessage = null;

        if (failure instanceof MessagingException messagingFailure) {
            failedMessage = messagingFailure.getFailedMessage();
        }

        Message<?> original = error.getOriginalMessage();
        Message<?> contextMessage =
                failedMessage != null ? failedMessage : original;

        Object correlationId = contextMessage != null
                ? contextMessage.getHeaders().get("correlationId")
                : null;

        Throwable root = rootCause(failure);
        log.error(
                "Integration failure: type={}, rootType={}, correlationId={}, " +
                        "hasFailedMessage={}, hasOriginalMessage={}",
                failure.getClass().getSimpleName(),
                root.getClass().getSimpleName(),
                correlationId,
                failedMessage != null,
                original != null,
                failure);
    }

    private static Throwable rootCause(Throwable throwable) {
        Throwable cursor = throwable;
        for (int i = 0; i < 32 && cursor.getCause() != null; i++) {
            if (cursor.getCause() == cursor) {
                break;
            }
            cursor = cursor.getCause();
        }
        return cursor;
    }
}
~~~

**Điều kiện sử dụng:** có Spring Integration, component scanning, annotation endpoints và logging framework; ví dụ phù hợp với Java hỗ trợ pattern matching cho instanceof. Tên header correlationId là quy ước ứng dụng, không phải header được mọi adapter tự thêm. Trong production cần xét việc log stack trace có chứa thông tin nhạy cảm hay không.

### 7.2. Vì sao cần fallback từ failedMessage sang originalMessage?

Ví dụ handler ném IllegalStateException trực tiếp và error publisher không bao nó bằng MessagingException. Khi đó **getFailedMessage không có để gọi**, nhưng ErrorMessageStrategy có thể đã giữ input dưới originalMessage. Ngược lại, nếu exception đã được wrapper với failedMessage nhưng strategy không biết input gốc, originalMessage có thể null. Fallback giúp quan sát tốt hơn, **không phải bảo đảm khôi phục toàn bộ payload**.

### 7.3. Không đặt nghiệp vụ nặng trong observer

Một observer thường nên:

- Phân loại exception và ghi log/metric có cấu trúc;
- Truyền reference tới recovery workflow bền vững khi cần;
- Không thực hiện giao dịch ghi dữ liệu nguy hiểm theo mặc định;
- Không retry vô hạn cùng lỗi ở trong error handler;
- Có biện pháp nếu hệ thống alert/log bên ngoài bị lỗi;
- Giới hạn tần suất cảnh báo để tránh thông báo trùng.

Nếu dùng PublishSubscribeChannel, nhiều subscriber có thể gây nhiều side effect. Recovery cần policy rõ ràng: **ai thật sự chịu trách nhiệm retry, quarantine, nack hay DLQ**.

### 7.4. Khi handler không nhận ErrorMessage

Để debug, kiểm tra từng bước:

1. Exception có bị ném từ **DirectChannel đồng bộ** về caller không?
2. Task/executor/poller có sử dụng error publisher chưa?
3. Request có header errorChannel trỏ sang kênh riêng không?
4. Gateway có error flow riêng hoặc đã unwrap exception không?
5. Handler có subscribe đúng context và đúng bean channel không?
6. Loại channel có subscriber, yêu cầu subscriber và trạng thái running phù hợp không?
7. Nếu broker listener, exception có bị container xử lý trước khi vào integration error publisher không?

Việc không thấy message trên errorChannel **không có nghĩa là không có lỗi**.

## 8. ErrorMessageStrategy: ErrorMessage được xây dựng từ context thế nào?

Spring Integration cung cấp **ErrorMessageStrategy** để dựng ErrorMessage từ Throwable và một **AttributeAccessor context**. Triển khai **DefaultErrorMessageStrategy** có thể đọc input message được cung cấp qua **ErrorMessageUtils.INPUT_MESSAGE_CONTEXT_KEY**, dùng nó làm originalMessage nếu tồn tại.

### 8.1. Mục đích tách strategy khỏi publisher

| Thành phần | Trách nhiệm |
|---|---|
| ErrorMessageStrategy | Quyết định ErrorMessage chứa Throwable, originalMessage và metadata như thế nào |
| ErrorMessagePublisher | Xác định việc publish ErrorMessage theo cơ chế được tích hợp |
| MessagePublishingErrorHandler | Xử lý exception của task khi sử dụng, publish tới channel phù hợp |
| MessageChannel | Vận chuyển ErrorMessage tới subscriber |
| Recovery handler | Chọn log, retry, quarantine, alert hoặc một hành động khác |

Tách các lớp này giúp giữ hợp đồng lỗi nhất quán mà không buộc tất cả endpoint có cùng retry strategy.

### 8.2. Ví dụ dùng DefaultErrorMessageStrategy

~~~java
import org.springframework.integration.support.DefaultErrorMessageStrategy;
import org.springframework.integration.support.ErrorMessageUtils;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

Message<String> input = MessageBuilder
        .withPayload("raw-order-274")
        .build();

Message<Integer> atFailure = MessageBuilder
        .withPayload(274)
        .build();

MessageHandlingException failure = new MessageHandlingException(
        atFailure, "Persist failed", new IllegalStateException("DB offline"));

DefaultErrorMessageStrategy strategy = new DefaultErrorMessageStrategy();
ErrorMessage result = strategy.buildErrorMessage(
        failure,
        ErrorMessageUtils.getAttributeAccessor(input, atFailure));

System.out.println(result.getOriginalMessage() == input); // true
System.out.println(((MessageHandlingException) result.getPayload())
        .getFailedMessage() == atFailure); // true
~~~

Code trên minh họa việc **tạo ErrorMessage có context theo API Spring Integration**; bản thân nó **không gửi** message tới errorChannel. Để publish, phải dùng component/error publisher hoặc gửi message tới kênh phù hợp bằng cơ chế được ứng dụng kiểm soát.

### 8.3. Context khác với Java ThreadLocal

Một task có thể chuyển thread khi đi qua executor hoặc async gateway. Không nên tin rằng ThreadLocal nghiệp vụ sẽ tự theo exception qua mọi ranh giới. Các thông tin cần thiết cho error processing nên được đưa vào **Message headers** hoặc **context được truyền rõ** với phân quyền/giới hạn phù hợp.

### 8.4. Khi nào cần strategy tùy biến?

Có thể thiết kế strategy tùy biến khi hệ thống cần gắn metadata chuẩn hóa như flowName, integrationStage, correlation ID và recovery reference; hoặc cần giảm dữ liệu nhạy cảm trước khi publish. Nhưng việc tùy biến phải tôn trọng:

- Payload của ErrorMessage là **Throwable**;
- originalMessage phải phản ánh dữ liệu input thực sự được cung cấp, không giả mạo;
- Context có thể null khi lỗi xảy ra trước lúc có message;
- Không để secret và PII lọt qua error channel hoặc kho lưu lỗi;
- Không biến error message thành kênh truyền lại payload nghiệp vụ quá lớn.

## 9. Phân loại exception mà không làm mất thông tin

### 9.1. Wrapper và root cause

Ví dụ flow JDBC nhận một OrderCommand và DB không khả dụng:

~~~text
MessageHandlingException
  failedMessage: OrderCommand(orderId=274)
  cause: DataAccessResourceFailureException
    cause: SQLException / connection failure
~~~

Nếu chỉ log SQLException, người vận hành mất thông tin về **message nào, endpoint nào** thất bại. Nếu chỉ log MessageHandlingException, họ không biết DB đang thiếu kết nối. Cần lưu đủ **wrapper context + nguyên nhân sâu nhất**.

### 9.2. Không phân loại tất cả MessageHandlingException giống nhau

| Exception ở tầng Spring | Cause / bối cảnh | Khả năng xử lý |
|---|---|---|
| MessageHandlingException | HTTP timeout | Có thể retry nếu an toàn và có idempotency |
| MessageHandlingException | Business validation failed | Thường không retry y nguyên |
| MessageHandlingException | Database unavailable | Có thể retry giới hạn/backoff |
| MessageDeliveryException | Channel không có subscriber | Sửa flow/config, không chỉ retry |
| MessageDeliveryException | Queue/channel tắc nghẽn | Cần backpressure/timeout/giới hạn |
| MessageConversionException | Payload không chuyển được | Sửa schema/content type hoặc quarantine |
| MessagingException không có failedMessage | Lỗi ở giai đoạn trước khi có Message hoặc được tạo thiếu context | Tìm context khác, không đọc null |

Đây là hướng phân loại, không phải quy tắc cố định cho mọi implementation. Ví dụ một timeout HTTP có thể đã gây side effect tại downstream dù caller không nhận phản hồi; retry phải kiểm soát trùng nghiệp vụ.

### 9.3. Nên giữ loại lỗi ở nhiều mức

Hệ thống error processing có thể giữ:

- **exceptionClass:** MessageHandlingException hoặc MessageDeliveryException;
- **rootCauseClass:** IOException, SQLException, v.v.;
- **errorCategory:** INVALID_INPUT, TRANSIENT, PERMISSION, CONFLICT, UNKNOWN;
- **stage:** RECEIVE, TRANSFORM, VALIDATE, PERSIST, OUTBOUND_SEND, ACK;
- **disposition:** RETRYING, QUARANTINED, DEAD_LETTERED, REJECTED, MANUAL_REVIEW;
- **attempt:** số lần thử và retry budget;
- **businessKey/correlationId:** tham chiếu giúp tra cứu mà không chứa dữ liệu nhạy cảm.

**Không đồng nhất exceptionClass với errorCategory.** Mapping cần biết cả dữ liệu, giao thức và hợp đồng nghiệp vụ.

### 9.4. Lỗi bị bọc nhiều lớp

Một error subscriber nhận ErrorMessage.payload là Throwable, nhưng chuỗi cause có thể chứa nhiều wrapper từ Spring Integration, HTTP client, driver hoặc broker. Chỉ kiểm tra failure.getClass() có thể không đủ. Ngược lại, duyệt cause không giới hạn có thể gây vòng lặp với Throwable bất thường; ví dụ code ở phần 7 giới hạn số tầng.

### 9.5. Thông điệp lỗi không luôn chứa dữ liệu có thể replay

Một MessagingException được tạo chỉ từ chuỗi description có thể có failedMessage=null. Một ErrorMessage được tạo từ Throwable đơn thuần có originalMessage=null. Nếu phục hồi sau sự cố là yêu cầu bắt buộc, phải có **durable recovery reference** và giữ input đúng contract trước khi làm mất quyền sở hữu nó.

## 10. Message headers và ranh giới bảo mật

### 10.1. Correlation ID không phải Message ID

| Giá trị | Công dụng | Đặc tính |
|---|---|---|
| MessageHeaders.ID | Định danh một message cụ thể do framework tạo | Có thể thay đổi khi tạo message mới |
| MessageHeaders.TIMESTAMP | Thời điểm message được tạo | Không phải thời điểm nghiệp vụ hoàn tất |
| correlationId | Liên kết các bước của một giao dịch nghiệp vụ | Thường do ứng dụng định nghĩa hoặc upstream cấp |
| errorChannel header | Chọn đích xử lý lỗi nếu error publisher hỗ trợ | Không phải bằng chứng quyền truy cập |
| failedMessage.headers | Metadata tại điểm lỗi | Có thể khác headers input |
| originalMessage.headers | Metadata của message được cung cấp khi build ErrorMessage | Có thể thiếu hoặc không còn hợp lệ |

Không nên suy correlation bằng cách tự ép các message ID khác nhau thành cùng một giá trị. Nếu tạo message mới qua nhiều transformer, cần truyền correlation ID có chủ đích.

### 10.2. Header errorChannel không nên lấy nguyên từ client không tin cậy

Nếu một HTTP request hoặc Kafka record ngoài hệ thống được phép cung cấp giá trị errorChannel tùy ý, nó có thể cố hướng lỗi sang một kênh nội bộ không dành cho caller. Cần giới hạn/loại bỏ header điều khiển do bên ngoài tự khai, chỉ thiết lập error destination trong integration flow đáng tin cậy.

### 10.3. Bảo vệ payload thất bại

failedMessage có thể chứa:

- Nội dung file có PII hoặc dữ liệu tài chính;
- HTTP body, token hoặc cookie;
- Lệnh SQL hoặc tham số chứa dữ liệu nhạy cảm;
- Event broker thuộc tenant khách hàng;
- Tham chiếu tới tài nguyên lớn.

**Không ghi thẳng failedMessage.toString() trong production** khi chưa hiểu cách payload và header được định dạng. Hãy log ID, loại lỗi, stage, correlation và dữ liệu đã masking. Chỉ lưu bản sao payload nếu có nhu cầu recovery rõ ràng, mã hóa, phân quyền và retention phù hợp.

## 11. ErrorMessage trong các adapter của Spring Integration

### 11.1. Bảng đối chiếu

| Adapter / gateway | Ngoại lệ nguồn | Bối cảnh ErrorMessage cần giữ | Điều không được suy ra |
|---|---|---|---|
| File inbound poller | I/O, parse, validation | File reference, filter state, correlation | File sẽ tự đọc lại |
| SFTP inbound/outbound | SSH/session, network, permission, rename | Remote path, stage, session failure | Remote file chưa bị thay đổi |
| HTTP inbound gateway | Validation, handler, mapping | Request context và status mapping | Có HTTP response đúng chỉ nhờ errorChannel |
| HTTP outbound gateway | Timeout, HTTP 4xx/5xx, conversion | URI định danh an toàn, method, status, idempotency key | Timeout nghĩa là server chưa xử lý |
| JMS inbound/outbound | Conversion, listener, broker | Message ID, destination, delivery attempt | ErrorMessage đồng nghĩa rollback |
| AMQP inbound/outbound | Consumer/producer, nack/requeue | Delivery metadata và broker disposition | Đã vào DLQ chỉ vì errorMessage |
| Kafka inbound/outbound | Deserialization, handler, offset, producer | Topic/partition/offset nếu có, event key | Offset được rewind hoặc đã gửi DLT |
| JDBC inbound/outbound | SQL, constraint, transaction | Row/business key, transaction outcome | DB chắc chắn rollback mọi side effect |

Mỗi adapter có **vòng đời kết nối, acknowledgment, retry và transaction** khác nhau. ErrorMessage là vỏ chứa sự kiện lỗi đã được publish, không phải một hợp đồng giao dịch chung cho tất cả.

### 11.2. File và SFTP: bối cảnh có thể chưa là Spring Message

Lỗi có thể xảy ra khi poller chưa đọc được file hoặc chưa tạo message; lúc đó không có failedMessage để tra cứu. Nếu file đã được nhận nhưng handler parse sai schema, failedMessage có thể chứa File hoặc payload đã chuyển đổi. Cần thiết kế thêm **file ready check, AcceptOnce/persistent filter, quarantine, replay policy** và idempotency để tránh mất hoặc xử lý trùng.

### 11.3. HTTP: exception và HTTP status là hai hợp đồng

Với inbound gateway đồng bộ, caller cần nhận HTTP response phù hợp. ErrorMessage tới một kênh bất đồng bộ có thể phục vụ audit, nhưng không thay cho việc ánh xạ 400/403/409/500/503 và body lỗi. Với outbound HTTP, HTTP 4xx/5xx có thể được client coi là exception hoặc response tùy cấu hình; không tự suy chúng luôn là MessageHandlingException.

### 11.4. JMS/AMQP: thông tin lỗi chưa quyết định acknowledgment

Broker cần biết message đã được ack, nacked, rejected, rolled back hoặc redelivered theo container và transaction mode. Nếu một handler swallow exception sau khi đã publish ErrorMessage, container có thể hiểu việc xử lý đã hoàn tất. Ngược lại, ném lại exception có thể kích hoạt redelivery. Quyết định cần tương thích **DLQ và poison-message handling**.

### 11.5. Kafka: vị trí record là bối cảnh quan trọng

Khi lỗi nằm ở Kafka listener, nguyên nhân có thể xuất hiện ở deserializer, converter, handler hoặc offset commit. **CommonErrorHandler/DefaultErrorHandler** và DLT của Kafka container là các cơ chế riêng, không đồng nhất với errorChannel. Nếu cần retry record hoặc điều chỉnh offset, phải kiểm tra hành vi container cùng adapter.

### 11.6. JDBC: transaction không nằm trong ErrorMessage

Một DataAccessException có thể xuất hiện trong cause của MessageHandlingException. Bản thân ErrorMessage không bảo đảm JDBC transaction rollback hoặc HTTP downstream được bù trừ. Các thao tác phân tán cần thiết kế transaction boundary, outbox/inbox, idempotency và reconciliation.

## 12. Từ ErrorMessage đến recovery: không nhầm quan sát lỗi với xử lý xong

### 12.1. Bốn câu hỏi phải trả lời

Khi nhận ErrorMessage, handler không nên lập tức “retry chính message đó”. Trước tiên cần xác định:

1. **Lỗi ở giai đoạn nào?** Chưa nhận được input, đã transform, đã ghi DB, đã gửi HTTP hay đã commit offset?
2. **Hành động đã tạo side effect chưa?** Một HTTP timeout có thể xảy ra sau khi phía đích ghi dữ liệu thành công.
3. **Có bản gốc bền vững để replay không?** failedMessage/originalMessage có thể chỉ là object trong bộ nhớ.
4. **Ai sở hữu quyền retry/ack?** Poller, transaction advice, broker container, Kafka listener, recovery worker hay hệ thống nghiệp vụ?

Một error observer toàn cục **không có đủ thông tin để tự quyết mọi giao thức**. Nên phân tuyến tới recovery policy theo flow và adapter.

### 12.2. Các trạng thái kết quả

| Trạng thái | Ý nghĩa | Bằng chứng nên có |
|---|---|---|
| OBSERVED | Đã nhận thông tin lỗi | ID và loại exception |
| CLASSIFIED | Đã xác định lỗi transient/permanent/unknown | Stage, cause, resource, context |
| RETRY_SCHEDULED | Có tác vụ retry theo lịch | Retry key, attempt, due time |
| RETRY_EXHAUSTED | Không thử tiếp theo policy | Số lần, lý do, destination phục hồi |
| QUARANTINED | Dữ liệu lỗi được lưu cách ly | Reference, owner, retention |
| DEAD_LETTERED | Broker/queue/topic lưu message theo cơ chế riêng | DLQ/DLT reference và disposition |
| COMPENSATING | Đang xử lý side effect cần bù trừ | Business transaction reference |
| RECOVERED | Kết quả nghiệp vụ đạt trạng thái mong muốn | Xác minh ở hệ thống đích |
| MANUAL_REVIEW | Chưa xác định được kết quả hay chưa an toàn retry | Owner, deadline, dữ liệu cần đối soát |

Những trạng thái này thuộc **workflow nghiệp vụ tự thiết kế**, không phải enum mặc định của ErrorMessage.

### 12.3. Retry có giới hạn và idempotency

Retry nên được đặt ở đúng lớp: Spring Integration advice, HTTP client, broker/container, retry worker hoặc một flow riêng. Đừng lặp cùng một thao tác ở nhiều lớp mà không tính **retry budget**.

Ví dụ: advice retry tối đa 3 lần, Kafka listener lại retry tối đa 5 lần. Tổng số lần gọi HTTP đích có thể lên tới 15 lần (chưa kể client-level retry), gây quá tải và side effect trùng.

Một yêu cầu retry an toàn thường gồm:

- Có điều kiện áp dụng theo loại lỗi, không retry validation/authorization sai vô hạn;
- Có số lần và thời gian tối đa, backoff và jitter;
- Có business key/idempotency key hoặc cơ chế kiểm tra duplicate;
- Có final disposition nếu hết retry;
- Có đầy đủ thông tin để điều tra và replay có kiểm soát.

### 12.4. ErrorMessageSendingRecoverer và retry advice

Spring Integration có các thành phần cho phép kết hợp retry/recovery, chẳng hạn **ErrorMessageSendingRecoverer**, có thể sử dụng trong recovery callback của retry advice để publish thông tin lỗi sau khi không thể hoàn tất thao tác. Điều này hữu ích khi muốn tạo một ErrorMessage **có ngữ cảnh request** cho recovery.

Tuy nhiên, **việc publish thành công không đồng nghĩa hệ thống ngoài đã rollback**. Đối với message-driven adapter cần xét mối quan hệ giữa callback, exception cuối cùng và broker/container acknowledgment.

### 12.5. Vì sao không nên “nuốt” exception?

Giả sử một JMS listener xử lý OrderCommand và JDBC insert thất bại. Handler bắt exception, gửi ErrorMessage, rồi return thành công. Nếu container dựa trên kết quả lời gọi để acknowledge, message có thể bị ack dù đơn hàng chưa được lưu.

Nếu mục tiêu là broker redelivery, phải thiết kế rõ khi nào cần **propagate/rethrow** để transaction hoặc container biết thất bại. Nếu mục tiêu là đưa message sang một durable retry store rồi ack nguồn, cần chứng minh việc lưu recovery đã hoàn tất trước khi ack.

## 13. Tạo hợp đồng error event phù hợp với hệ thống tích hợp

Spring ErrorMessage có payload Throwable, phù hợp trong phạm vi application runtime. Để truyền thông tin lỗi qua queue/topic ngoài hoặc lưu lâu dài, thường cần một **error event nghiệp vụ** đã được chuẩn hóa.

### 13.1. Ví dụ schema logic

~~~json
{
  "eventType": "integration.message.failed",
  "eventVersion": 1,
  "flowId": "sftp-orders-import",
  "adapter": "SFTP_INBOUND",
  "stage": "PERSIST",
  "sourceMessageId": "msg-274",
  "correlationId": "batch-2026-274",
  "businessKey": "order-274",
  "exceptionClass": "MessageHandlingException",
  "rootCauseClass": "SQLTransientConnectionException",
  "category": "TRANSIENT",
  "attempt": 3,
  "disposition": "MANUAL_REVIEW",
  "recoveryReference": "quarantine/item-274",
  "occurredAt": "2026-11-23T08:15:00Z"
}
~~~

Đây là **schema do ứng dụng định nghĩa**, không phải ErrorMessage được serialize nguyên dạng. Không đưa Throwable tùy ý hoặc đầy đủ stack trace/payload khách hàng vào sự kiện xuất ra ngoài vì vấn đề tương thích, bảo mật và kích thước.

### 13.2. Contract phải lưu được thông tin cần thiết cho replay

| Thành phần | Vai trò | Quy tắc |
|---|---|---|
| Business key | Xác định nghiệp vụ | Có thể dùng dedupe/idempotency |
| Correlation ID | Tìm các bước xử lý cùng chuỗi | Truyền xuyên flow khi có thể |
| Source reference | Trỏ đến file, topic/partition/offset, queue hoặc record | Không dùng reference ngoài quyền truy cập |
| Flow/stage | Xác định nơi lỗi | Dùng tên ổn định, có version |
| Error category | Quyết định retry hay quarantine | Có taxonomy và mapping |
| Retry attempt | Biết retry đã đến đâu | Cập nhật atomically theo workflow khi cần |
| Outcome | Đã retry, cách ly hay thất bại vĩnh viễn? | Không ghi RECOVERED nếu chưa xác minh |
| Data retention | Khi nào xóa event và bản lưu input | Theo quy định và chính sách |

### 13.3. Không coi ErrorMessage là durable queue

Một PublishSubscribeChannel thường nằm trong bộ nhớ application và gửi đến subscriber theo cấu hình. Nếu process dừng, ErrorMessage chưa được lưu bền vững có thể mất. Muốn bảo đảm xử lý lỗi sau restart, cần thiết kế **durable store/queue**, transaction/ack phù hợp và cơ chế đối soát.

### 13.4. Chuẩn hóa exception khi ranh giới API thay đổi

Ở một flow nội bộ, có thể truyền Java Throwable. Nhưng với REST hoặc event external, nên chuyển sang mã lỗi, mô tả có kiểm soát, request ID và status đúng hợp đồng. Không đưa tên class nội bộ, stacktrace hoặc thông tin kết nối DB ra cho caller ngoài.

## 14. Quan sát lỗi: log, metric và tracing

### 14.1. Ghi log có thể truy vết

Log nên chứa flowId, endpointId, adapter, correlationId, messageId, exception type, root cause type, stage, attempt, disposition và timestamp. Nếu có failedMessage, lấy **metadata được phép công bố**, không log nguyên payload.

Ví dụ:

~~~text
level=ERROR
flow=sftp-orders-import
stage=parse-csv
correlationId=batch-274
exceptionType=MessageHandlingException
rootCauseType=IllegalArgumentException
errorCategory=INVALID_INPUT
disposition=QUARANTINED
~~~

### 14.2. Các metric hữu ích

| Chỉ số | Ý nghĩa |
|---|---|
| error_messages_published_total | Số ErrorMessage được publish theo scope quan sát |
| integration_failures_total | Lỗi thực tế theo flow/stage/category |
| recovery_attempts_total | Số lần retry |
| recovery_exhausted_total | Lỗi hết retry và cần disposition |
| error_handler_failures_total | Sự cố trong chính handler xử lý lỗi |
| quarantine_backlog | Số dữ liệu chưa thể xử lý |
| dlq_depth hoặc dlt_lag | Backlog message đã dead-letter |
| last_successful_poll | Phát hiện poller không còn đọc message |
| processing_latency | Độ trễ xử lý thành công và thất bại |

**Không dùng messageId, orderId hoặc correlationId làm metric label** vì cardinality cao. Giữ chúng trong log/trace có phân quyền, còn metrics chỉ gắn nhãn flow/type/status giới hạn.

### 14.3. Tracing qua các ranh giới

Khi message đi File → transformer → HTTP → Kafka, code cần propagate trace/correlation context phù hợp. ErrorMessage.originalMessage hoặc failedMessage có thể giúp tra header, nhưng **không đảm bảo toàn bộ span context được giữ** sau mỗi chuyển đổi hoặc ranh giới thread.

### 14.4. Không phát sinh ErrorMessage không có nghĩa flow khỏe mạnh

Một file poller ngừng chạy hoặc SFTP directory không còn file vì cấu hình sai có thể không ném exception. Metrics cần đo heartbeat, lần poll thành công, tuổi message lâu nhất và backlog; chỉ dựa vào số ErrorMessage sẽ bỏ sót lỗi im lặng.

## 15. Case study: ErrorMessage khi import đơn hàng từ SFTP

### 15.1. Luồng giả định

Công ty A nhận file CSV qua SFTP từ đối tác B. Spring Integration lấy file theo poller, transformer tạo OrderCommand, service activator ghi JDBC rồi HTTP outbound gửi xác nhận đơn hàng. Kết quả được đưa tới Kafka.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound poller"]
    FILE["File / CSV"]
    CMD["OrderCommand transformer"]
    JDBC["JDBC persist"]
    HTTP["HTTP outbound"]
    KAFKA["Kafka producer"]
    EP["Error publisher / strategy"]
    ERR["errorChannel hoặc flow-specific channel"]
    REC["Quarantine / retry / alert"]
    SFTP --> FILE --> CMD --> JDBC --> HTTP --> KAFKA
    JDBC -. "exception" .-> EP
    CMD -. "exception" .-> EP
    EP --> ERR --> REC
~~~

Trong thực tế, lỗi có đi qua EP hay không tùy poller/error strategy và topology. Sơ đồ cho thấy **một đường lỗi đã được cấu hình**, không khẳng định mọi message pipeline tự publish lỗi.

### 15.2. Trường hợp A: file không tải được

Poller chưa tạo Message nhưng kết nối SFTP timeout. Error publisher nhận Throwable với bối cảnh task, **failedMessage có thể null**, originalMessage có thể null. Cần dùng log kết nối, flow name và target path an toàn để điều tra. Hướng xử lý là retry có backoff, cảnh báo khi quá hạn, kiểm tra remote/local file state.

### 15.3. Trường hợp B: parse CSV thất bại

Message ban đầu M0 mang File, transformer đọc CSV và gặp cột không hợp lệ. Một MessageHandlingException có thể chứa failedMessage liên quan File hoặc message tại transformer. Nếu ErrorMessageStrategy biết M0, originalMessage=M0; không đảm bảo nó chứa toàn bộ bytes file.

Vì lỗi schema là permanent, nên chuyển file vào quarantine và báo bên gửi sửa thay vì retry liên tục. Phải xét filter/metadata của File/SFTP adapter để không mất hoặc đọc trùng file.

### 15.4. Trường hợp C: JDBC insert thất bại

Message M1 chứa OrderCommand; JDBC không kết nối được. ErrorMessage.payload có thể chứa MessageHandlingException, failedMessage=M1, cause=DataAccessException. Lúc này retry có thể thích hợp nhưng phải biết đã có dòng nào commit, tránh tạo order trùng. Nếu một số row đã lưu, cần idempotency key hoặc đối soát trước replay.

### 15.5. Trường hợp D: HTTP outbound timeout

Message đã ghi DB; HTTP request gửi đi nhưng caller mất response. ErrorMessage chứa exception timeout **không chứng minh đối tác chưa nhận request**. Phải dùng idempotency key hoặc truy vấn trạng thái, tránh xác nhận đơn hàng hai lần. Nếu kết quả không rõ, chuyển sang MANUAL_REVIEW hoặc workflow reconciliation.

### 15.6. Trường hợp E: Kafka publish lỗi

JDBC và HTTP có thể đã thành công nhưng Kafka producer báo lỗi. ErrorMessage không rollback được các bước trước. Có thể dùng transactional outbox gắn với DB để ghi “ý định phát event”, sau đó publisher thử lại; consumer cần idempotent khi delivery lặp. Kafka DLT/retry policy là cơ chế riêng, không tự được tạo từ errorChannel.

### 15.7. Ba bài học

1. **Lớp lỗi:** MessagingException giúp liên kết lỗi với failedMessage tại vị trí xử lý.
2. **Đường lỗi:** ErrorMessage giúp chuyển Throwable và context qua channel khi cơ chế publish được kích hoạt.
3. **Khôi phục:** phải kiểm tra side effect ở file, DB, HTTP và Kafka; chỉ nhận ErrorMessage không đủ chứng minh message đã được retry hay giải quyết.

## 16. Unit test hợp đồng ErrorMessage và MessagingException

### 16.1. Test tạo ErrorMessage có originalMessage và failedMessage

Đây là test độc lập ở mức API Spring Messaging để chứng minh hai message reference khác nhau. Không cần file system hay broker.

~~~java
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

class ErrorMessageContractTest {

    @Test
    void keepsOriginalAndFailedMessagesSeparate() {
        Message<String> input = MessageBuilder
                .withPayload("raw-order")
                .setHeader("correlationId", "batch-274")
                .build();

        Message<Integer> transformed = MessageBuilder
                .withPayload(274)
                .build();

        MessageHandlingException failure = new MessageHandlingException(
                transformed,
                "JDBC write failed",
                new IllegalStateException("database unavailable"));

        ErrorMessage error = new ErrorMessage(failure, input);

        assertSame(failure, error.getPayload());
        assertSame(input, error.getOriginalMessage());
        assertTrue(error.getPayload() instanceof MessagingException);
        assertSame(transformed,
                ((MessagingException) error.getPayload()).getFailedMessage());
    }
}
~~~

**Ý nghĩa:** ErrorMessage có originalMessage vì constructor được cấp input; MessagingException có failedMessage vì constructor được cấp transformed. Đây là cách xác minh API dữ liệu, **chưa phải kiểm thử một error publisher hay adapter thật**.

### 16.2. Test trường hợp không có context

~~~java
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

class MissingErrorContextTest {

    @Test
    void allowsMissingMessageReferences() {
        MessagingException failure =
                new MessagingException("Task failed before message creation");
        ErrorMessage error = new ErrorMessage(failure);

        assertSame(failure, error.getPayload());
        assertNull(failure.getFailedMessage());
        assertNull(error.getOriginalMessage());
    }
}
~~~

**Ý nghĩa:** null là một trường hợp bình thường. Production error handler phải có fallback để vẫn ghi stage, flow hoặc scheduler metadata từ nguồn khác nếu có.

### 16.3. Test strategy khi có context

Có thể dùng một test khác tạo MessageHandlerException, truyền context qua ErrorMessageUtils và assert getOriginalMessage() như phần 8. Khi không truyền INPUT_MESSAGE_CONTEXT_KEY, DefaultErrorMessageStrategy có thể tạo ErrorMessage không có originalMessage.

### 16.4. Phạm vi unit test

Các test API trên kiểm tra đúng cấu trúc object nhưng **không** chứng minh:

- Exception trong DirectChannel có được publish hay throw hay không;
- Poller có error handler chưa;
- JMS/AMQP/Kafka broker ack hoặc rollback thế nào;
- Khi gửi ErrorMessage lỗi, thông điệp nghiệp vụ có được lưu lại hay không;
- Retry có làm trùng bản ghi database không.

Những trường hợp đó cần **integration tests** với endpoint và cấu hình thực tế.

## 17. Integration test đường lỗi của adapter

### 17.1. Case A — DirectChannel và caller

Tạo flow đồng bộ với handler ném IllegalStateException. Gửi một message bằng gateway hoặc MessagingTemplate. Xác minh exception đến caller theo thiết kế hoặc được gateway ánh xạ. Không assert rằng global errorChannel luôn nhận message nếu không có error publisher.

### 17.2. Case B — Poller publish ErrorMessage

Tạo inbound source được poll định kỳ; handler ném exception. Cấu hình kênh lỗi riêng để test, chẳng hạn **QueueChannel testErrors**, và chỉ rõ endpoint/poller sử dụng kênh đó.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;

@Configuration
class ErrorTestChannels {

    @Bean
    QueueChannel testErrors() {
        return new QueueChannel();
    }
}
~~~

Trong test, sau khi poller chạy, lấy bean testErrors và kiểm tra nhận được ErrorMessage. Đoạn assert minh họa:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

// Giả định QueueChannel testErrors được inject từ Spring context.
Message<?> received = testErrors.receive(5_000);
if (!(received instanceof ErrorMessage error)) {
    throw new AssertionError("Expected ErrorMessage");
}
if (error.getPayload() == null) {
    throw new AssertionError("Expected Throwable payload");
}
~~~

**Quan trọng:** ví dụ assert không phải một file test độc lập; flow, poller và testErrors phải được cấu hình/inject trước. Không nên thay thế global errorChannel production bằng QueueChannel chỉ để tiện test.

### 17.3. Case C — Header errorChannel có được tôn trọng?

Tạo message với MessageHeaders.ERROR_CHANNEL trỏ tới testErrors; dùng một endpoint/error publisher có hỗ trợ header đó, cố tình gây lỗi. Kiểm tra ErrorMessage tới đúng channel. Chạy một test tương tự với DirectChannel đồng bộ để thấy **gắn header đơn lẻ không tự bắt exception**.

### 17.4. Case D — Handler lỗi trong chính error flow

Cho subscriber của error channel ném exception hoặc giả lập dịch vụ logging/alerting không khả dụng. Cần biết:

- ErrorMessage có được delivery tới các subscriber khác không;
- Lỗi của handler có bị bỏ qua hoặc làm hỏng flow chính không;
- Có tạo vòng lặp xử lý lỗi không;
- Có thể phục hồi mà không nhân đôi notification không;
- Dữ liệu nghiệp vụ có còn trong nguồn bền vững để replay?

Các câu trả lời phụ thuộc PublishSubscribeChannel, order của subscriber và cấu hình dispatch/error handling.

### 17.5. Ma trận test theo adapter

| Adapter | Lỗi chủ động tạo | Assert ngoài ErrorMessage |
|---|---|---|
| File | Sai CSV | File state, quarantine và replay |
| SFTP | Timeout hoặc permission | Reconnect/backoff, remote file không bị xử lý sai |
| HTTP inbound | Payload không hợp lệ | HTTP 4xx/5xx và response contract |
| HTTP outbound | Timeout hoặc 503 | Retry budget, idempotency, outcome |
| JMS | Handler throw | Ack/rollback, redelivery và DLQ |
| AMQP | Poison message | Nack/requeue/DLX/DLQ |
| Kafka | Deserialize/processing failure | Container error policy, offset và DLT |
| JDBC | DB unavailable | Transaction, row state và duplicate prevention |

Đọc một ErrorMessage chỉ xác nhận **đường thông báo lỗi**; assert trạng thái ở hệ thống nguồn/đích mới cho thấy **semantics vận hành**.

## 18. Runbook điều tra một ErrorMessage

### Bước 1: xác định đường đến

Kiểm tra ErrorMessage được publish bởi **poller**, **task executor**, **gateway error flow**, **retry recoverer** hay **adapter listener/container**. Cần biết bean/endpoint, channel, timestamp, message ID và cách nó chọn destination (per-message, per-endpoint hay global).

### Bước 2: đọc đúng cấu trúc

~~~text
if ErrorMessage:
    failure = payload
    original = getOriginalMessage()  // có thể null

if failure instanceof MessagingException:
    failed = failure.getFailedMessage()  // có thể null
    inspect cause chain
else:
    failed = null

use metadata safely; do not log secrets
~~~

Xác định payload của failedMessage thuộc File, byte[], String, JSON document, OrderCommand, JMS/Kafka record hay kiểu khác. Tránh cast theo giả định từ adapter đầu tiên; payload có thể đã được transformer thay đổi.

### Bước 3: phân loại nguyên nhân và tác động

- Lỗi input vĩnh viễn hay hạ tầng tạm thời?
- Message đã được ack, commit, move/delete hay chưa?
- Downstream HTTP/DB/Kafka đã tạo side effect nào?
- Nếu retry, có idempotency hoặc dedupe không?
- Có mất correlation, owner hay recovery reference không?

### Bước 4: chọn disposition

| Điều kiện | Xử lý |
|---|---|
| Transient và retry an toàn | Retry có backoff/giới hạn |
| Payload không hợp lệ | Quarantine hoặc báo producer sửa dữ liệu |
| Authentication/permission sai | Sửa trust/credential, không retry dồn dập |
| HTTP outcome không rõ | Đối soát trạng thái nghiệp vụ |
| Broker poison message | DLQ/DLT theo container/broker policy |
| Side effect đã commit một phần | Compensation hoặc idempotent replay |
| Thiếu failedMessage/originalMessage | Truy lại source reference, logs và state, không suy đoán |

### Bước 5: xác minh sau recovery

Kiểm chứng số message đã retry, message nào thành công, message nào được cách ly, số record/đơn hàng còn dang dở và backlog. Không đóng sự cố chỉ vì đã có error log hoặc một handler gửi notification thành công.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Ép kiểu mọi ErrorMessage.payload thành MessagingException | ClassCastException tại error handler | Kiểm tra instanceof |
| Gọi getFailedMessage không null-check | NullPointerException | Xử lý trường hợp thiếu context |
| Cho rằng originalMessage luôn là message đầu tiên của toàn flow | Replay nhầm payload/phase | Xác minh strategy/context |
| Đọc error.getHeaders như headers của input | Sai correlation và metadata | Kiểm tra original/failed headers |
| Cho rằng mọi throw đều tới errorChannel | Bỏ sót lỗi DirectChannel đồng bộ | Phân biệt throw và publish |
| Gắn errorChannel header và tưởng xong | Không có error publisher, không có handler | Cấu hình endpoint và kiểm thử |
| Ghi thẳng Throwable/failedMessage cùng payload nhạy cảm | Rò rỉ dữ liệu hoặc secret | Masking, safe metadata và giới hạn log |
| Coi ErrorMessage là durable retry message | Mất dữ liệu sau process restart | Durable recovery storage và ack phù hợp |
| Gửi ErrorMessage vào business input | Sai schema, tạo lỗi mới | Replay đúng business command |
| Retry tất cả MessageHandlingException | Poison message lặp vô hạn | Phân loại nguyên nhân và retry budget |
| Bắt exception rồi return success trong listener | Broker có thể ack dù DB chưa ghi | Thiết kế container/transaction error policy |
| Tin ErrorMessage tạo DLQ hoặc Kafka DLT | Hiểu sai delivery semantics | Cấu hình broker/container riêng |
| Chỉ log root cause, bỏ failedMessage | Thiếu thông tin flow và business key | Giữ wrapper context |
| Dùng PublishSubscribeChannel nhưng tưởng chỉ một subscriber | Log/alert/recovery bị lặp | Phân chia trách nhiệm và idempotency |
| Không test handler xử lý lỗi bị lỗi tiếp | Mất quan sát hoặc lặp notification | Test error-of-error, fallback |
| Chỉ giám sát số ErrorMessage | Không phát hiện poller dừng im lặng | Health, last-successful-poll, backlog |

## 20. Checklist triển khai ErrorMessage và MessagingException

### A. Hợp đồng thông điệp

- [ ] Biết payload ở từng stage và kiểu Message được chuyển đổi ra sao.
- [ ] Có business key/correlation ID để liên hệ các bước xử lý.
- [ ] Hiểu failedMessage có thể null, originalMessage có thể null.
- [ ] ErrorMessage payload được xử lý như Throwable, không ép kiểu tùy ý.
- [ ] Header errorChannel chỉ được thiết lập từ nguồn tin cậy.
- [ ] Không lưu credential, token hoặc payload nhạy cảm không cần thiết.

### B. Đường lỗi

- [ ] Phân biệt DirectChannel/gateway đồng bộ với poller/async.
- [ ] Biết endpoint/error strategy nào thực sự publish ErrorMessage.
- [ ] Global errorChannel và dedicated channels có owner rõ ràng.
- [ ] Subscriber logging/alerting có kiểm soát xử lý trùng.
- [ ] Có cách xử lý khi error handler hoặc error channel bị lỗi.

### C. Phục hồi và dữ liệu

- [ ] Phân loại lỗi transient/permanent/unknown có căn cứ.
- [ ] Retry có giới hạn, backoff, idempotency và final disposition.
- [ ] File/SFTP có filter, trạng thái file và quarantine.
- [ ] HTTP có timeout, response mapping và idempotency.
- [ ] JMS/AMQP/Kafka có ack/offset/retry/DLQ/DLT theo container.
- [ ] JDBC có transaction, tránh partial commit và replay trùng.
- [ ] Recovery state lưu bền vững nếu cần xử lý sau restart.

### D. Kiểm thử và vận hành

- [ ] Unit test phân biệt originalMessage và failedMessage.
- [ ] Test trường hợp không có message context.
- [ ] Test DirectChannel ném exception và poller publish ErrorMessage.
- [ ] Test trường hợp error handler tự thất bại.
- [ ] Test side effect, ack/commit và restart ở adapter quan trọng.
- [ ] Có metric theo flow/stage/type, retry exhausted và backlog.
- [ ] Có runbook, owner và audit trail để replay an toàn.

## 21. Câu hỏi tự kiểm tra

**Câu 1. ErrorMessage và MessagingException khác nhau ở điểm cơ bản nào?**

**Đáp án:** MessagingException là một RuntimeException thuộc Spring Messaging; ErrorMessage là một Message có payload kiểu Throwable, thường chứa một MessagingException. Ngoại lệ có thể được ném trực tiếp mà không tạo ErrorMessage.

**Câu 2. ErrorMessage có getFailedMessage() trực tiếp không?**

**Đáp án:** Không. getFailedMessage() thuộc MessagingException. Cần lấy ErrorMessage.getPayload(), kiểm tra có phải MessagingException rồi mới lấy getFailedMessage().

**Câu 3. Khi nào ErrorMessage.getOriginalMessage() có giá trị?**

**Đáp án:** Khi constructor hoặc ErrorMessageStrategy được cung cấp input message để giữ lại. Không đảm bảo luôn tồn tại hoặc luôn trỏ tới message đầu tiên trong toàn bộ flow.

**Câu 4. Có thể tạo ErrorMessage từ IOException mà không dùng MessagingException không?**

**Đáp án:** Có. ErrorMessage nhận Throwable payload, không bắt buộc là MessagingException. Khi đó không thể lấy failedMessage qua payload trừ khi cơ chế khác cung cấp bối cảnh.

**Câu 5. Vì sao failedMessage và originalMessage có thể khác nhau?**

**Đáp án:** Input có thể đã đi qua transformer trước khi handler lỗi. MessagingException ghi nhận message ở điểm thất bại, còn ErrorMessageStrategy có thể giữ input tại điểm bắt exception dưới originalMessage.

**Câu 6. Khi một DirectChannel handler ném IllegalStateException, global errorChannel có chắc nhận được lỗi không?**

**Đáp án:** Không. Đường đồng bộ thường throw về sender. Chỉ khi có cơ chế catch/publish tương ứng mới có ErrorMessage trên channel.

**Câu 7. Header MessageHeaders.ERROR_CHANNEL có thể thay thế việc cấu hình error publisher không?**

**Đáp án:** Không. Nó là thông tin chọn destination cho thành phần có hỗ trợ phân giải header; bản thân header không bắt exception hoặc tạo ErrorMessage.

**Câu 8. Global errorChannel thường là loại channel nào?**

**Đáp án:** Trong cấu hình mặc định thông dụng là PublishSubscribeChannel và có LoggingHandler; ứng dụng có thể tùy chỉnh. Nhiều subscriber có thể cùng nhận một message.

**Câu 9. Vì sao không được log toàn bộ failedMessage một cách vô điều kiện?**

**Đáp án:** failedMessage có thể chứa file, dữ liệu khách hàng, token, thông tin cá nhân hoặc message rất lớn. Nên log metadata an toàn, correlation ID và loại lỗi; chỉ lưu payload khi có cơ chế bảo mật phù hợp.

**Câu 10. Một ErrorMessage được publish từ JMS listener có chứng minh broker sẽ redeliver message không?**

**Đáp án:** Không. Redelivery, acknowledgment và transaction do listener/container và broker policy quyết định. Phải kiểm thử propagation/rollback và cách xử lý exception của error handler.

**Câu 11. Kafka có ErrorMessage thì đã có dead-letter topic chưa?**

**Đáp án:** Chưa. DLT cần cấu hình Kafka container/recovery riêng. ErrorMessage là một Spring Message, không phải Kafka record hay topic.

**Câu 12. Có nên retry mọi MessageHandlingException không?**

**Đáp án:** Không. Cần xét cause, stage và nghiệp vụ. Lỗi validation thường cần sửa dữ liệu, timeout hạ tầng có thể retry nếu an toàn, còn HTTP timeout có thể đã tạo side effect và cần idempotency/reconciliation.

**Câu 13. Vì sao unit test tạo ErrorMessage bằng constructor không đủ cho production?**

**Đáp án:** Nó chỉ xác nhận object model. Production cần kiểm tra error publisher, error destination, polling/async, broker acknowledgment, transaction, retry và dữ liệu thực tế sau thất bại.

**Câu 14. Nếu error.getOriginalMessage() là null và MessagingException.getFailedMessage() cũng null, có thể làm gì?**

**Đáp án:** Dùng thông tin từ flow/task metadata, log, exception cause, correlation ở nguồn hoặc recovery reference. Không tự tạo một failedMessage không có căn cứ rồi replay.

**Câu 15. Kết quả nào chứng minh lỗi đã được xử lý xong?**

**Đáp án:** Có bằng chứng nghiệp vụ: dữ liệu xử lý thành công, được lưu an toàn để retry, đưa vào quarantine/DLQ đúng chính sách hoặc ghi nhận cần can thiệp với owner. Sự xuất hiện của ErrorMessage hoặc một dòng log không đủ.

## 22. Kết luận và tài liệu tham khảo

### Tóm tắt bản chất

**MessagingException** bổ sung **ngữ cảnh message bị lỗi** vào ngoại lệ Java. **ErrorMessage** là một **Spring Message với Throwable payload** để chuyển thông tin lỗi qua các message channel khi cơ chế xử lý được cấu hình publish.

Ba cấu trúc cần ghi nhớ:

~~~text
ErrorMessage
    payload: Throwable
        -> có thể là MessagingException
              -> failedMessage: Message<?> (nullable)
              -> cause: Throwable (nullable)
    originalMessage: Message<?> (nullable)
    headers: MessageHeaders
~~~

Khi đọc lỗi, cần xác định **loại Throwable**, **message tại điểm lỗi**, **input được strategy giữ lại**, **channel được chọn** và **nguyên nhân trong chuỗi cause**. Khi xử lý hậu quả, phải phân biệt lỗi đồng bộ, poller/bất đồng bộ, acknowledgment của broker, transaction của DB và các side effect bên ngoài.

Việc thiết kế tốt không dừng ở catch exception hoặc phát ErrorMessage. Nó cần bảo đảm **message contract, error classification, idempotency, retry có giới hạn, recovery bền vững, logging an toàn và kiểm thử end-to-end**. Đối với các adapter File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC, ErrorMessage giúp quan sát và điều phối lỗi, nhưng **khả năng retry, rollback, ack, cách ly và khôi phục vẫn phải được thiết kế cho từng loại tích hợp**.

### Tài liệu chính thức nên đọc tiếp

- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): phân biệt exception đồng bộ/bất đồng bộ, errorChannel, MessagePublishingErrorHandler và ErrorMessageStrategy.
- [Spring Framework Javadoc — ErrorMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html): API payload, constructors và originalMessage.
- [Spring Framework Javadoc — MessagingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html): constructors, getFailedMessage() và phân cấp ngoại lệ.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): exception/reply behavior và error flow tại gateway.

**Ghi chú về phiên bản:** Các ví dụ sử dụng Spring Messaging/Spring Integration API phổ biến và Java hiện đại. Trước khi đưa vào dự án thực tế, cần đối chiếu Javadoc với phiên bản Spring Framework, Spring Integration và Spring Boot đang sử dụng; không giả định mọi adapter, gateway hoặc listener có cùng cách publish lỗi.
