# ErrorMessage và cách biểu diễn lỗi dưới dạng thông điệp

> Mục tiêu: hiểu cách Spring biểu diễn lỗi bằng `ErrorMessage`, đọc được exception và message gây lỗi, định tuyến lỗi qua error channel, phân biệt lỗi kỹ thuật với kết quả nghiệp vụ và thiết kế xử lý lỗi an toàn trong các luồng messaging.

## 1. Vì sao cần biểu diễn lỗi thành message?

Trong một lời gọi Java đồng bộ, lỗi thường được truyền bằng exception trên call stack. Bên gọi có thể bắt exception, quyết định rollback, trả kết quả lỗi hoặc chuyển tiếp lỗi lên tầng cao hơn.

Trong luồng messaging, producer và consumer có thể hoạt động ở các thời điểm khác nhau. Consumer có thể xử lý message sau khi producer đã kết thúc request ban đầu; lỗi vì thế không thể luôn được ném ngược về đúng luồng của producer. Hệ thống cần một cách chuyển thông tin lỗi đến thành phần chịu trách nhiệm quan sát, retry, ghi nhận hoặc xử lý tiếp.

Spring Messaging biểu diễn lỗi bằng `ErrorMessage`. Đây là một loại `Message` có payload là `Throwable` (exception hoặc error) và có thể giữ tham chiếu đến message gốc liên quan đến lỗi. Error message có thể được gửi đến một error channel để một handler khác xử lý.

Cần phân biệt ba việc:

- **Tạo lỗi:** một thành phần ném exception khi xử lý thất bại.
- **Biểu diễn và định tuyến lỗi:** hạ tầng tạo `ErrorMessage` và gửi nó đến error channel phù hợp.
- **Quyết định phục hồi:** một error handler, retry policy hoặc dead-letter mechanism quyết định ghi log, retry, chuyển tiếp, báo động hay kết thúc xử lý.

`ErrorMessage` giải quyết việc mang thông tin lỗi. Bản thân nó không tự retry, rollback database, gửi email hay bảo đảm message được lưu bền vững.

## 2. Cấu trúc của ErrorMessage

Trong Spring Framework, `org.springframework.messaging.support.ErrorMessage` là một message chuyên dùng cho lỗi. Các thành phần quan trọng:

- **Payload:** một đối tượng `Throwable`, thường là exception mô tả lỗi xảy ra.
- **Original message:** message ban đầu có liên quan đến lỗi, nếu có. Có thể truy cập bằng `getOriginalMessage()`.
- **Headers:** metadata của message lỗi, chẳng hạn ID và timestamp do message infrastructure cung cấp; các header tùy chỉnh có thể hỗ trợ correlation và quan sát.

Ví dụ tạo một error message từ một lỗi đã biết:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

Message<?> failedMessage = obtainFailedMessage();
Throwable cause = new IllegalStateException("Inventory service is unavailable");

MessagingException failure = new MessagingException(
        failedMessage,
        "Could not process order message",
        cause
);

ErrorMessage errorMessage = new ErrorMessage(failure, failedMessage);
Throwable errorPayload = errorMessage.getPayload();
Message<?> originalMessage = errorMessage.getOriginalMessage();
```

Đây là đoạn mã minh họa, trong đó `obtainFailedMessage()` đại diện cho message đã được nhận trước đó. Ứng dụng thực tế thường để Spring Integration hoặc adapter tạo error message theo error handling strategy của endpoint; không cần tự tạo `ErrorMessage` cho mọi exception.

Tên `ErrorMessage` có thể gây nhầm với `java.lang.Error`. `ErrorMessage` là kiểu message của Spring; payload có kiểu `Throwable`. Không nên bắt mọi `Throwable` chỉ để chuyển thành message rồi tiếp tục chạy, vì các lỗi JVM nghiêm trọng như `OutOfMemoryError` thường không phải lỗi nghiệp vụ có thể phục hồi.

## 3. MessagingException và message gây lỗi

`MessagingException` là exception cơ sở trong Spring Messaging để mô tả lỗi liên quan đến message. Nó có thể giữ message gây lỗi qua `getFailedMessage()` và nguyên nhân gốc qua `getCause()`.

Một số exception chuyên biệt thường gặp trong hệ sinh thái Spring Messaging/Integration:

| Exception | Tình huống thường gặp |
|---|---|
| `MessagingException` | Lỗi tổng quát liên quan đến xử lý hoặc gửi message |
| `MessageHandlingException` | Handler nhận message nhưng xử lý thất bại |
| `MessageDeliveryException` | Không thể gửi hoặc chuyển message đến nơi nhận |
| `MessageTransformationException` | Không thể chuyển đổi payload hoặc message theo yêu cầu |
| `MessageConversionException` | Chuyển đổi dữ liệu giữa payload và kiểu đích thất bại |

Các exception cụ thể giúp phân loại nơi phát sinh lỗi. Khi xử lý, nên giữ nguyên cause chain để tìm nguyên nhân thực sự thay vì chỉ ghi lại thông báo ngoài cùng.

Ví dụ đọc thông tin lỗi:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

void inspect(ErrorMessage errorMessage) {
    Throwable payload = errorMessage.getPayload();
    Message<?> original = errorMessage.getOriginalMessage();

    if (payload instanceof MessagingException messagingException) {
        Message<?> failed = messagingException.getFailedMessage();
        Throwable rootCause = messagingException.getCause();
        // Ghi nhận failed, original và rootCause theo chính sách log.
    }
}
```

`originalMessage` và `failedMessage` có thể trùng nhau, nhưng không nên mặc định chúng luôn giống nhau. Trong một flow có transform hoặc enrich, message ban đầu và message tại bước thất bại có thể khác nhau. Giữ cả hai thông tin giúp xác định dữ liệu đầu vào và trạng thái tại điểm lỗi.

## 4. Error channel trong Spring Integration

Spring Integration dùng message channel để định tuyến cả message nghiệp vụ lẫn error message. Error channel là nơi các `ErrorMessage` được gửi đến để handler chuyên trách xử lý.

Khi hạ tầng xử lý bất đồng bộ phát hiện exception, error handling mechanism có thể tạo `ErrorMessage` và publish nó đến error channel. Một channel toàn cục thường được đặt tên `errorChannel`; endpoint hoặc message cụ thể cũng có thể được cấu hình để dùng error channel riêng. Cơ chế chính xác phụ thuộc loại endpoint, poller, adapter và cấu hình error handling.

Ví dụ một handler lắng nghe error channel mặc định trong ứng dụng Spring Integration đã bật hạ tầng tương ứng:

```java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
class GlobalMessagingErrorHandler {
    @ServiceActivator(inputChannel = "errorChannel")
    public void handle(ErrorMessage errorMessage) {
        Throwable cause = errorMessage.getPayload();
        // Phân loại, ghi log có kiểm soát và phát cảnh báo nếu cần.
    }
}
```

Handler trên chỉ nhận error message đã được định tuyến vào channel. Việc khai báo một method nghe `errorChannel` không tự bắt mọi exception trong toàn bộ JVM. Cần xác nhận endpoint phát lỗi có kết nối với channel đó và không có cấu hình riêng ghi đè.

### Error channel riêng cho một luồng

Một luồng xử lý đơn hàng có thể cần chính sách lỗi riêng với luồng email. Ví dụ, lỗi thanh toán cần cảnh báo và đối soát; lỗi gửi email có thể retry chậm hơn. Có thể tạo channel riêng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.MessageChannel;
import org.springframework.integration.channel.DirectChannel;

@Configuration
class OrdersErrorConfiguration {
    @Bean
    MessageChannel ordersErrorChannel() {
        return new DirectChannel();
    }
}
```

Channel này chỉ tạo điểm nhận message trong ứng dụng. Endpoint cần được cấu hình để publish lỗi vào `ordersErrorChannel`; nếu không có producer gửi vào, handler đăng ký trên channel sẽ không nhận được lỗi. Có thể cấu hình error channel tại endpoint, poller hoặc theo header phù hợp với integration đang sử dụng.

`DirectChannel` gọi subscriber trong luồng gửi. Nếu cần phân phối đến nhiều subscriber hoặc xử lý bất đồng bộ, hãy chọn loại channel và executor phù hợp, đồng thời hiểu rõ cách exception của subscriber được truyền lại.

## 5. Lỗi đồng bộ và lỗi bất đồng bộ

Cách lỗi đi đến nơi xử lý phụ thuộc luồng thực thi:

| Tình huống | Cách lỗi thường được quan sát |
|---|---|
| Gọi phương thức đồng bộ | Exception truyền ngược qua call stack đến caller nếu không được bắt |
| Gửi qua `DirectChannel` | Handler chạy trong luồng gửi; exception có thể truyền ngược đến sender |
| Poller hoặc executor bất đồng bộ | Không có call stack của request ban đầu để trả lỗi; error handler/channel có thể nhận `ErrorMessage` |
| Message-driven adapter | Adapter/container và cấu hình transaction, acknowledgement, error handler quyết định lỗi được ném lại, chuyển đến error channel hay xử lý theo broker |
| Consumer ở tiến trình khác | Producer không thể nhận exception Java từ consumer; cần reply, event lỗi, trạng thái hoặc cơ chế dead-letter riêng |

Đây là lý do không nên giả định mọi exception đều tự động xuất hiện trên `errorChannel`. Với lời gọi đồng bộ, caller thường nhận exception trực tiếp. Với xử lý bất đồng bộ, lỗi cần một đường quan sát độc lập. Với broker ở tiến trình khác, lỗi của consumer là một kết quả ở phía consumer và phải được truyền về nếu nghiệp vụ cần biết.

## 6. Tạo và xử lý ErrorMessage trong một flow

Một flow có thể tạo error message từ exception và chuyển nó đến error channel. Ví dụ sau minh họa phần xử lý lỗi ở cấp ứng dụng:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

void publishProcessingFailure(
        Message<?> failedMessage,
        Throwable cause,
        MessageChannel errorChannel) {

    MessagingException failure = new MessagingException(
            failedMessage,
            "Order processing failed",
            cause
    );

    ErrorMessage errorMessage = new ErrorMessage(failure, failedMessage);
    errorChannel.send(errorMessage);
}
```

Đoạn mã trên là minh họa cho việc đóng gói và gửi lỗi thủ công. Trong ứng dụng thực tế, hãy cân nhắc error handling có sẵn của Spring Integration trước khi tự publish để tránh gửi trùng hoặc làm mất ngữ nghĩa transaction. Giá trị trả về của `send` phản ánh việc channel chấp nhận message theo hợp đồng của channel; nó không chứng minh lỗi đã được khắc phục.

Một error handler nên thực hiện các bước có chủ đích:

1. Lấy exception từ payload và xác định nguyên nhân gốc.
2. Lấy `failedMessage` và `originalMessage` nếu có.
3. Phân loại lỗi tạm thời, lỗi dữ liệu, lỗi cấu hình, lỗi nghiệp vụ hoặc lỗi không thể phục hồi.
4. Quyết định retry, reject, chuyển dead-letter, phát cảnh báo hoặc ghi nhận để xử lý thủ công.
5. Ghi lại correlation/message ID để có thể truy vết từ log và metrics.

Tránh để error handler ném lại cùng một lỗi theo cách khiến nó quay vòng vô hạn về chính error channel đó. Nếu handler xử lý lỗi cũng thất bại, cần có fallback như log có giới hạn, metric hoặc cơ chế vận hành khác.

## 7. ErrorMessage không đồng nghĩa với business error response

Không phải mọi tình huống không thành công đều là exception kỹ thuật. Ví dụ khách hàng nhập mã giảm giá đã hết hạn là một kết quả nghiệp vụ có thể dự đoán; dịch vụ thanh toán không kết nối được là lỗi kỹ thuật.

| Loại kết quả | Ví dụ | Cách biểu diễn phù hợp |
|---|---|---|
| Lỗi kỹ thuật | Timeout khi gọi database hoặc broker | Exception; có thể được đóng gói thành `ErrorMessage` trong error flow |
| Từ chối nghiệp vụ | Không đủ hàng, đơn đã hủy, coupon hết hạn | Kết quả hoặc reply có kiểu rõ ràng, ví dụ `ReservationRejected` |
| Sự kiện thất bại đã xảy ra | Thanh toán bị từ chối bởi nhà cung cấp | Event nghiệp vụ như `PaymentDeclined`, nếu đó là sự thật đã được ghi nhận |
| Không xử lý được message sau retry | Payload hỏng hoặc vi phạm schema | Dead-letter message hoặc quy trình cách ly theo chính sách broker |

Không nên dùng exception cho mọi nhánh nghiệp vụ bình thường. Nếu thiếu hàng là kết quả hợp lệ của nghiệp vụ, trả một kết quả có kiểu giúp consumer xử lý rõ ràng hơn. Ngược lại, không nên biến lỗi kết nối hoặc lỗi lập trình thành một reply “thành công nhưng thất bại” làm che khuất sự cố.

## 8. ErrorMessage, error channel và dead-letter queue khác nhau thế nào?

- **ErrorMessage:** đối tượng message trong Spring, payload là `Throwable`, có thể mang message liên quan đến lỗi.
- **Error channel:** đường định tuyến trong ứng dụng Spring để chuyển error message đến một handler.
- **Dead-letter queue (DLQ):** tài nguyên của broker hoặc messaging platform để giữ message không thể xử lý theo chính sách retry/reject/expiry.
- **Error event:** một hợp đồng nghiệp vụ hoặc vận hành được phát đi để thông báo một lỗi đã xảy ra; payload thường là DTO có schema ổn định.

Error channel thường là một phần của luồng xử lý trong tiến trình. Nó không tự có độ bền của broker và không tự thay thế DLQ. DLQ giữ message để điều tra hoặc phát lại tùy nền tảng; ErrorMessage chứa exception Java và không nên mặc định serialize trực tiếp để chuyển qua một hệ thống khác.

Nếu cần thông báo lỗi giữa các dịch vụ, nên thiết kế payload độc lập với class exception nội bộ, ví dụ:

```java
import java.time.Instant;

record ProcessingFailedEvent(
        String eventId,
        String correlationId,
        String messageId,
        String operation,
        String errorCode,
        String safeDescription,
        Instant occurredAt
) {}
```

DTO này có thể được serialize theo schema đã thống nhất. Không đưa stack trace, mật khẩu, access token hoặc dữ liệu nhạy cảm vào event. Hãy phân biệt thông tin phục vụ chẩn đoán nội bộ với thông tin có thể chia sẻ cho consumer khác.

## 9. Retry, acknowledgement và tính lặp an toàn

`ErrorMessage` không tự quyết định retry. Retry phụ thuộc nơi lỗi xảy ra và cơ chế đang dùng:

- Với lời gọi đồng bộ, caller có thể retry nếu lỗi có khả năng phục hồi và thao tác an toàn khi lặp.
- Với Spring Integration, retry có thể được cấu hình bằng advice hoặc cơ chế xử lý lỗi của endpoint/poller.
- Với broker, acknowledgement, reject, requeue, visibility timeout hoặc offset commit quyết định message có được giao lại hay không; tên và hành vi cụ thể tùy công nghệ.
- Sau số lần retry hữu hạn, message có thể được chuyển sang DLQ hoặc vùng cách ly để xử lý thủ công.

Thiết kế consumer idempotent để một message được giao lại không tạo side effect trùng. Có thể lưu message ID hoặc business key đã xử lý cùng với kết quả trong một transaction phù hợp. Chỉ retry lỗi tạm thời như mất kết nối ngắn hạn; lỗi schema, dữ liệu không hợp lệ hoặc vi phạm quy tắc nghiệp vụ thường cần sửa dữ liệu hoặc xử lý riêng.

Nếu consumer ghi database rồi mới xác nhận message, cần hiểu transaction và acknowledgement của broker có thực sự phối hợp hay không. Không giả định một transaction database đơn lẻ bao trùm cả việc xử lý broker. Với yêu cầu nhất quán cao, thiết kế outbox/inbox hoặc cơ chế deduplication phù hợp.

## 10. Quan sát và bảo mật khi xử lý lỗi

Error handler cần cung cấp đủ dữ liệu để điều tra nhưng không làm lộ thông tin:

- Ghi message ID, correlation ID, destination, handler, thời điểm và số lần giao lại.
- Giữ cause chain và loại exception; tránh chỉ ghi một thông báo chung như “processing failed”.
- Ghi payload đã lọc hoặc chỉ các định danh cần thiết; tránh log toàn bộ payload nếu chứa dữ liệu cá nhân hoặc bí mật.
- Đặt giới hạn độ dài stack trace và mô tả để tránh log quá lớn.
- Dùng metrics cho số lỗi theo loại, retry count, DLQ depth và tuổi message cũ nhất.
- Tạo cảnh báo theo ngưỡng và xu hướng, không gửi một cảnh báo riêng cho mọi lần retry thông thường.

Một message lỗi có thể chứa cả payload gốc và exception. Vì vậy, error channel cũng là ranh giới dữ liệu cần kiểm soát quyền truy cập và chính sách lưu trữ.

## 11. Lỗi thường gặp

- **Nghĩ rằng `ErrorMessage` tự xử lý exception:** nó chỉ đóng gói lỗi; cần error handler hoặc cơ chế khác quyết định bước tiếp theo.
- **Cho rằng mọi exception đều đến `errorChannel`:** lỗi đồng bộ có thể truyền thẳng về caller; lỗi bất đồng bộ phụ thuộc endpoint và cấu hình.
- **Nhầm `ErrorMessage` với DLQ:** error message trong Spring không tự lưu bền vững trên broker.
- **Bỏ qua message gây lỗi:** chỉ ghi stack trace mà không giữ message ID hoặc failed message làm việc điều tra khó khăn.
- **Chỉ đọc `getOriginalMessage()` và bỏ qua `getFailedMessage()`:** trong flow có transform, hai message có thể khác nhau.
- **Retry vô hạn:** có thể khóa consumer và làm queue tăng liên tục.
- **Retry cả lỗi nghiệp vụ không thể phục hồi:** tạo tải và log lặp mà không giải quyết nguyên nhân.
- **Ném exception từ error handler mà không có fallback:** có thể tạo vòng lặp lỗi hoặc làm mất thông tin ban đầu.
- **Serialize trực tiếp exception Java qua broker:** làm hợp đồng phụ thuộc class nội bộ, phiên bản thư viện và dữ liệu nhạy cảm trong stack trace.
- **Coi xác nhận broker là xử lý nghiệp vụ thành công:** acknowledgement chỉ có ý nghĩa theo giao thức và thời điểm xác nhận đã cấu hình.

## 12. Quy trình thiết kế một error flow

1. Xác định lỗi phát sinh ở đâu: sender, channel, transformer, handler, adapter hay broker.
2. Xác định luồng đồng bộ hay bất đồng bộ và nơi có thể quan sát exception.
3. Giữ lại `Throwable`, `failedMessage`, `originalMessage` và correlation ID khi có.
4. Phân loại lỗi kỹ thuật, lỗi nghiệp vụ, lỗi tạm thời và lỗi không thể phục hồi.
5. Chọn error channel trong ứng dụng, reply lỗi có kiểu, event lỗi hoặc DLQ theo phạm vi cần truyền thông tin.
6. Đặt retry có giới hạn, backoff, idempotency và quy tắc acknowledgement phù hợp.
7. Ghi log/metrics có kiểm soát và cung cấp cách điều tra hoặc phát lại message.
8. Kiểm thử cả đường thành công, lỗi đồng bộ, lỗi bất đồng bộ, timeout, redelivery và lỗi của chính error handler.

## 13. Kết luận

`ErrorMessage` là abstraction của Spring để biểu diễn một lỗi dưới dạng message: payload mang `Throwable`, còn original message và headers giúp liên kết lỗi với dữ liệu đã gây ra nó. Trong Spring Integration, error channel cho phép chuyển lỗi bất đồng bộ đến handler chuyên trách.

Hãy tách rõ việc ném exception, đóng gói và định tuyến lỗi, rồi quyết định retry hoặc dead-letter. Dùng business reply cho kết quả nghiệp vụ có thể dự đoán, dùng error flow cho lỗi kỹ thuật, và dùng error event có schema ổn định khi cần thông báo lỗi qua ranh giới dịch vụ. Thiết kế như vậy giúp hệ thống quan sát được lỗi, xử lý lại có kiểm soát và không nhầm xác nhận giao nhận với kết quả nghiệp vụ.