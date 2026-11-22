# MessagingException, MessageDeliveryException và MessageHandlingException

Trong một luồng messaging, lỗi có thể xảy ra ở nhiều thời điểm: producer không gửi được message vào channel, transport không chuyển được message tới đích, hoặc consumer đã nhận message nhưng xử lý nghiệp vụ thất bại. Spring dùng các exception trong nhóm messaging để giữ ngữ cảnh của lỗi và message liên quan.

Ba kiểu thường gặp là **MessagingException**, **MessageDeliveryException** và **MessageHandlingException**. Chúng có quan hệ kế thừa, nhưng diễn tả những phạm vi lỗi khác nhau. Phân biệt đúng giúp xác định lỗi nằm ở bước gửi hay bước xử lý, giữ lại nguyên nhân gốc, chọn retry hợp lý và tránh đưa message lỗi vào vòng lặp vô hạn.

## 1. Vòng đời message và các điểm có thể phát sinh lỗi

Một luồng messaging điển hình gồm các bước:

1. Producer tạo payload và đóng gói thành Message, có thể kèm message ID, correlation ID và content type.
2. Producer gửi Message vào MessageChannel hoặc adapter của một transport.
3. Channel hoặc transport định tuyến và chuyển message đến nơi nhận.
4. Consumer nhận message và gọi handler.
5. Handler kiểm tra dữ liệu, thực hiện nghiệp vụ và ghi nhận kết quả.
6. Hạ tầng xác nhận message đã được tiếp nhận hoặc xử lý theo semantics của transport.

Lỗi có thể phát sinh ở từng bước. Ví dụ, channel không có subscriber, hàng đợi đầy, executor từ chối task, broker không kết nối được, payload không giải mã được hoặc handler ném exception khi cập nhật database.

~~~mermaid
flowchart LR
    P["Producer"] --> S["Send to channel"]
    S --> D["Delivery / transport"]
    D --> H["Consumer handler"]
    H --> B["Business processing"]
    S -. "send / dispatch error" .-> E["Messaging error"]
    D -. "delivery error" .-> E
    H -. "handling error" .-> E
~~~

Không phải mọi ứng dụng đều có đầy đủ các tầng trên. DirectChannel có thể gọi handler đồng bộ ngay trong thread gửi; một broker adapter có thể chuyển message qua mạng và xử lý bất đồng bộ. Vì vậy, cần phân loại exception dựa trên điểm phát sinh thực tế và contract của channel/adapter.

## 2. MessagingException: exception nền tảng cho lỗi messaging

**MessagingException** thuộc package **org.springframework.messaging**. Đây là exception nền tảng trong Spring Messaging, kế thừa từ **NestedRuntimeException**. Nó dùng để biểu diễn lỗi xảy ra trong quá trình thao tác với message.

Một MessagingException có thể chứa:

- **Failed message:** message liên quan đến lỗi, nếu tại thời điểm phát sinh đã xác định được message đó.
- **Description:** mô tả thao tác hoặc ngữ cảnh bị lỗi.
- **Cause:** exception gốc gây ra lỗi, nếu lỗi bắt nguồn từ một exception khác.

Thông tin failed message rất hữu ích khi điều tra: có thể xác định message ID, correlation ID hoặc payload type để tìm đúng luồng xử lý. Không nên log toàn bộ payload một cách mặc định vì payload có thể chứa dữ liệu cá nhân, token hoặc thông tin nghiệp vụ nhạy cảm.

Một số cách tạo exception thường gặp:

~~~java
throw new MessagingException(
        message,
        "Messaging operation failed",
        cause
);
~~~

Constructor cụ thể có thể có các overload khác nhau theo phiên bản Spring. Ý nghĩa chung là gắn message liên quan, mô tả và nguyên nhân gốc vào exception để tầng gọi có thể chẩn đoán.

MessagingException phù hợp khi lỗi thuộc hoạt động messaging nhưng chưa có subtype cụ thể hơn hoặc khi ứng dụng cần biểu diễn một lỗi messaging tổng quát. Nếu đã biết lỗi xảy ra ở bước delivery hay handling, nên dùng subtype tương ứng để thông tin rõ hơn.

## 3. MessageDeliveryException: lỗi gửi hoặc chuyển giao message

**MessageDeliveryException** cũng thuộc package **org.springframework.messaging** và là một subtype của MessagingException. Nó diễn tả lỗi khi không thể gửi hoặc chuyển giao message theo contract của channel/đường truyền đang dùng.

Các tình huống có thể dẫn đến lỗi delivery gồm:

- Channel không thể dispatch message đến subscriber theo cấu hình.
- Một bước gửi message thất bại hoặc timeout.
- Executor từ chối task vì đã đầy hoặc đang shutdown.
- Adapter không thể chuyển message tới transport hoặc destination.
- Lỗi hạ tầng ở tầng gửi khiến message không được tiếp nhận như mong đợi.

Ví dụ minh họa khi gửi qua một channel có timeout:

~~~java
boolean sent = outputChannel.send(message, 1_000);

if (!sent) {
    throw new MessageDeliveryException(
            message,
            "Message was not accepted before the send timeout"
    );
}
~~~

**MessageChannel.send(message, timeout)** trả về boolean. Giá trị false có thể biểu thị message không được channel chấp nhận trong thời gian chờ; không phải mọi trường hợp đều tự ném MessageDeliveryException. Đoạn code chủ động chuyển kết quả false thành exception để tầng gọi có một đường xử lý lỗi thống nhất.

Khi channel hoặc adapter tự ném exception, loại exception cụ thể phụ thuộc implementation. Một số lỗi transport có thể được bọc trong exception của RabbitMQ, Kafka, JMS hoặc thư viện mạng rồi mới được chuyển thành exception messaging. Không nên giả định mọi lỗi kết nối broker đều có đúng class MessageDeliveryException ở mọi adapter.

### 3.1. Delivery failure không đồng nghĩa message chắc chắn bị mất

Khi send thất bại, cần xác định message đã được tiếp nhận đến đâu:

- Nếu channel từ chối trước khi nhận message, producer có thể còn trách nhiệm gửi lại.
- Nếu transport timeout sau khi broker đã nhận message nhưng producer chưa nhận được xác nhận, kết quả có thể không rõ ràng.
- Nếu broker đã nhận message nhưng consumer chưa xử lý, message có thể vẫn đang chờ.
- Nếu publisher confirm hoặc acknowledgement thất bại, cần đọc semantics cụ thể của broker để biết điều gì đã được xác nhận.

Một timeout không luôn chứng minh broker chưa nhận message. Retry mù quáng có thể tạo duplicate. Vì vậy message nên có ID ổn định và consumer cần xử lý idempotent khi nghiệp vụ không cho phép tác dụng phụ lặp.

## 4. MessageHandlingException: lỗi trong quá trình xử lý message

**MessageHandlingException** là subtype của MessagingException, diễn tả lỗi xảy ra khi một message đang được handler hoặc endpoint xử lý.

Ví dụ:

- Payload không hợp lệ hoặc thiếu trường bắt buộc.
- Không thể chuyển đổi payload sang DTO mong muốn.
- Quy tắc nghiệp vụ từ chối message.
- Handler gọi database hoặc service khác và thao tác thất bại.
- Lỗi lập trình như NullPointerException hoặc IllegalStateException xuất hiện trong handler.

Ví dụ tạo exception có giữ message và nguyên nhân gốc:

~~~java
public void handle(Message<OrderCreated> message) {
    try {
        orderService.createOrder(message.getPayload());
    }
    catch (InvalidOrderException ex) {
        throw new MessageHandlingException(
                message,
                "Could not process OrderCreated",
                ex
        );
    }
}
~~~

Đây là cách minh họa khi ứng dụng chủ động chuyển một lỗi nghiệp vụ thành MessageHandlingException. Trong nhiều luồng Spring Integration, framework hoặc adapter có thể tự bọc exception từ handler và giữ failed message; không cần bọc lại mọi exception một cách máy móc.

### 4.1. Phân biệt lỗi dữ liệu và lỗi tạm thời

Không phải mọi MessageHandlingException đều có cùng chính sách xử lý:

- **Lỗi dữ liệu không thể sửa bằng retry:** thiếu field bắt buộc, enum không hợp lệ hoặc schema sai. Thường nên đưa vào error channel hoặc dead-letter queue để điều tra.
- **Lỗi tạm thời:** database tạm mất kết nối, dịch vụ phụ bị timeout hoặc lock contention. Có thể retry có giới hạn và backoff.
- **Lỗi nghiệp vụ:** đơn hàng đã bị hủy hoặc trạng thái không cho phép thao tác. Đây có thể là kết quả hợp lệ về nghiệp vụ, cần phản hồi hoặc ghi nhận theo quy tắc thay vì retry vô hạn.
- **Lỗi lập trình:** NullPointerException hoặc lỗi invariant. Cần ghi log, alert và sửa nguyên nhân; retry tự động thường chỉ lặp lại cùng lỗi.

MessageHandlingException phân loại vị trí lỗi, không tự quyết định lỗi có retry được hay không. Chính sách retry phải dựa trên cause, loại lỗi nghiệp vụ, trạng thái message và khả năng phục hồi của hệ thống.

## 5. Quan hệ giữa ba exception

Có thể nhìn quan hệ theo hướng tổng quát đến cụ thể:

~~~text
NestedRuntimeException
        |
MessagingException
        |----------------------|
MessageDeliveryException   MessageHandlingException
~~~

| Exception | Phạm vi | Ví dụ điển hình |
|---|---|---|
| MessagingException | Lỗi messaging tổng quát | Thao tác message thất bại nhưng không phân loại cụ thể hơn |
| MessageDeliveryException | Gửi hoặc chuyển giao message | Channel không nhận message, dispatch hoặc send timeout |
| MessageHandlingException | Handler xử lý message | Handler lỗi khi validate hoặc thực hiện nghiệp vụ |

Cả hai subtype đều có thể mang failed message và cause thông qua lớp cha. Việc một exception là subtype nào không tự chứng minh message đã được broker lưu, đã được consumer nhận hay đã được xử lý thành công.

Khi bắt exception, có thể bắt subtype trước để áp dụng chính sách riêng rồi bắt MessagingException để xử lý lỗi chung:

~~~java
try {
    sendOrProcess(message);
}
catch (MessageDeliveryException ex) {
    handleDeliveryFailure(ex);
}
catch (MessageHandlingException ex) {
    handleHandlingFailure(ex);
}
catch (MessagingException ex) {
    handleOtherMessagingFailure(ex);
}
~~~

Nếu chỉ bắt MessagingException, các subtype vẫn được bắt vì quan hệ kế thừa, nhưng ứng dụng sẽ mất cơ hội phân biệt chính sách xử lý. Cần tránh bắt RuntimeException quá rộng rồi bỏ qua lỗi mà không giữ lại cause hoặc trạng thái thất bại.

## 6. Failed message và cause: giữ đủ ngữ cảnh để điều tra

Khi xử lý exception, nên giữ lại ít nhất ba thông tin:

1. **Failed message:** message nào gây lỗi?
2. **Cause:** exception gốc là gì?
3. **Failure stage:** lỗi xảy ra khi gửi, chuyển giao hay xử lý?

Ví dụ:

~~~java
catch (MessagingException ex) {
    Message<?> failedMessage = ex.getFailedMessage();

    String messageId = failedMessage == null
            ? "unknown"
            : failedMessage.getHeaders().getId().toString();

    log.error(
            "Messaging failed; messageId={}",
            messageId,
            ex
    );

    throw ex;
}
~~~

Đây là code minh họa; cần kiểm tra null an toàn vì failed message có thể không được gắn trong mọi constructor hoặc tình huống. Khi log, truyền exception object để logger giữ stack trace và cause. Không chỉ log **ex.getMessage()**, vì cách đó thường làm mất stack trace và thông tin nguyên nhân gốc.

Một số quy tắc thực tế:

- Tạo message ID hoặc correlation ID trước khi gửi để có thể liên kết log giữa producer và consumer.
- Giữ cause khi bọc exception; không thay thế lỗi gốc bằng một thông báo chung không có cause.
- Không tạo nhiều lớp bọc lặp lại nếu không thêm ngữ cảnh hữu ích.
- Tránh log toàn bộ payload hoặc headers nhạy cảm.
- Khi đưa message sang error channel hoặc DLQ, giữ lại message ID, failure stage, timestamp và số lần thử.

## 7. Lỗi đồng bộ và lỗi bất đồng bộ đi lên đâu?

Cách exception quay lại caller phụ thuộc loại channel và transport.

### 7.1. Luồng đồng bộ

Với channel dispatch đồng bộ như DirectChannel trong Spring Integration, handler có thể chạy trong thread gọi send. Nếu handler ném exception và không có tầng xử lý lỗi chặn lại, exception có thể truyền ngược về producer.

Điều đó cho phép caller quyết định rollback transaction, trả lỗi hoặc thực hiện xử lý tiếp. Tuy nhiên, tác dụng phụ ngoài transaction như gửi email hoặc gọi HTTP không tự được hoàn tác khi database rollback.

### 7.2. Luồng bất đồng bộ

Với ExecutorChannel, poller hoặc broker listener, handler có thể chạy trên thread khác hoặc trong tiến trình khác. Producer thường đã kết thúc lời gọi trước khi lỗi handling xảy ra. Exception không thể tự quay lại stack frame của producer ban đầu.

Trong Spring Integration, lỗi ở luồng bất đồng bộ có thể được chuyển thành **ErrorMessage** và gửi đến error channel theo cấu hình. Payload của ErrorMessage thường là Throwable; nếu đó là MessagingException, ứng dụng có thể lấy failed message qua getFailedMessage().

Ví dụ một error handler:

~~~java
@Component
public class MessagingErrorHandler {

    @ServiceActivator(inputChannel = "errorChannel")
    public void handle(ErrorMessage errorMessage) {
        Throwable error = errorMessage.getPayload();

        if (error instanceof MessagingException messagingException) {
            Message<?> failed = messagingException.getFailedMessage();
            // Ghi nhận message ID và phân loại lỗi.
        }

        // Ghi log hoặc định tuyến đến quy trình xử lý lỗi phù hợp.
    }
}
~~~

Đây là ví dụ theo Spring Integration khi error channel và infrastructure tương ứng được cấu hình. Spring Messaging core không tự tạo error channel toàn cục cho mọi MessageChannel. Với RabbitMQ, Kafka hoặc JMS, error handling còn phụ thuộc listener container, adapter, acknowledgement mode và broker.

Không nên giả định rằng mọi lỗi bất đồng bộ đều tự xuất hiện ở errorChannel. Cần kiểm tra đúng cấu hình integration và nơi exception được phát sinh.

## 8. Retry, backoff và dead-letter queue

Retry hữu ích khi lỗi có khả năng tự phục hồi, nhưng retry vô hạn có thể làm tắc queue và lặp lại tác dụng phụ.

### 8.1. Retry có giới hạn

Một chính sách retry nên xác định:

- Exception hoặc cause nào được retry.
- Số lần thử tối đa.
- Khoảng chờ giữa các lần thử.
- Backoff tăng dần và jitter nếu nhiều consumer cùng retry.
- Timeout tổng thể và thời hạn xử lý message.
- Hành vi sau khi hết số lần thử.

Ví dụ, một lỗi kết nối tạm thời có thể được retry với backoff. Lỗi validation hoặc schema không hợp lệ thường không được giải quyết bằng cách gửi lại cùng payload.

### 8.2. Dead-letter queue

Sau khi retry hết giới hạn hoặc gặp lỗi không thể phục hồi, message có thể được chuyển đến dead-letter queue (DLQ) hoặc vùng cách ly tương đương. DLQ giúp giữ message lỗi để kiểm tra, sửa dữ liệu hoặc phát lại có kiểm soát.

DLQ không tự có trong mọi MessageChannel. Đây thường là tính năng của broker hoặc quy trình error handling được cấu hình trong Spring Integration/adapter. Cần lưu thông tin nguyên nhân lỗi, số lần thử và message gốc để người vận hành hiểu vì sao message bị chuyển vào DLQ.

### 8.3. Idempotency khi retry hoặc redelivery

Một message có thể được giao lại sau timeout, consumer crash hoặc acknowledgement thất bại. Consumer nên dùng message ID hoặc khóa nghiệp vụ để chống thực hiện tác dụng phụ hai lần.

Ví dụ, nếu event yêu cầu tạo hóa đơn, có thể lưu event ID đã xử lý trong cùng transaction với dữ liệu hóa đơn. Khi message được giao lại, consumer kiểm tra khóa đó và bỏ qua tác vụ đã hoàn tất.

Không nên dựa vào việc chỉ nhìn thấy MessageDeliveryException hoặc MessageHandlingException để quyết định message có được gửi lại hay không. Cần kết hợp trạng thái broker, acknowledgement, transaction và idempotency.

## 9. Ví dụ Java 17: phân loại lỗi delivery và handling

Ví dụ sau dùng JDK thuần để minh họa cách giữ failed message và cause, đồng thời phân biệt lỗi gửi với lỗi xử lý. Các class có tiền tố **Demo** do chương trình tự định nghĩa; chúng chỉ mô phỏng ý nghĩa của các exception Spring, không thay thế hoặc kế thừa các class thật của Spring.

Tạo file **MessageFailureDemo.java**:

~~~java
public class MessageFailureDemo {

    record Message(String id, String payload) {}

    static class DemoMessagingException extends RuntimeException {
        private final Message failedMessage;

        DemoMessagingException(
                Message failedMessage,
                String description,
                Throwable cause) {
            super(description, cause);
            this.failedMessage = failedMessage;
        }

        Message getFailedMessage() {
            return failedMessage;
        }
    }

    static class DemoMessageDeliveryException
            extends DemoMessagingException {
        DemoMessageDeliveryException(
                Message message,
                String description,
                Throwable cause) {
            super(message, description, cause);
        }
    }

    static class DemoMessageHandlingException
            extends DemoMessagingException {
        DemoMessageHandlingException(
                Message message,
                String description,
                Throwable cause) {
            super(message, description, cause);
        }
    }

    static void send(Message message) {
        throw new DemoMessageDeliveryException(
                message,
                "Channel did not accept the message",
                new IllegalStateException("channel is full")
        );
    }

    static void handle(Message message) {
        throw new DemoMessageHandlingException(
                message,
                "Handler rejected the payload",
                new IllegalArgumentException("quantity must be positive")
        );
    }

    public static void main(String[] args) {
        Message message = new Message("msg-42", "quantity=0");

        try {
            send(message);
        } catch (DemoMessageDeliveryException ex) {
            System.out.println(
                    "Delivery failure: " + ex.getFailedMessage().id());
            System.out.println("Cause: " + ex.getCause().getMessage());
        }

        try {
            handle(message);
        } catch (DemoMessageHandlingException ex) {
            System.out.println(
                    "Handling failure: " + ex.getFailedMessage().id());
            System.out.println("Cause: " + ex.getCause().getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac MessageFailureDemo.java
java MessageFailureDemo
~~~

Kết quả:

~~~text
Delivery failure: msg-42
Cause: channel is full
Handling failure: msg-42
Cause: quantity must be positive
~~~

Ví dụ cho thấy cùng một message có thể thất bại ở hai giai đoạn khác nhau. Cả hai exception đều giữ message ID và cause, giúp tầng xử lý biết cần điều tra channel hay logic handler. Trong code Spring thực tế, hãy sử dụng các class trong package org.springframework.messaging thay vì tự tạo class trùng tên.

## 10. Kiểm thử exception và error handling

Nên kiểm thử theo từng giai đoạn thay vì chỉ xác nhận rằng một exception đã được ném ra:

- **Delivery test:** channel không có subscriber, queue đầy hoặc executor từ chối task; xác nhận producer nhận đúng kết quả false/exception theo contract.
- **Handling test:** handler ném lỗi validation hoặc lỗi phụ thuộc; xác nhận failed message và cause được giữ.
- **Cause test:** kiểm tra exception gốc không bị mất khi framework hoặc ứng dụng bọc lỗi.
- **Synchronous flow test:** xác nhận exception có truyền ngược về caller hay bị error handler xử lý.
- **Asynchronous flow test:** xác nhận ErrorMessage/error channel hoặc adapter error handler nhận được lỗi theo cấu hình.
- **Retry test:** kiểm tra số lần thử, backoff và exception nào được retry.
- **DLQ test:** xác nhận message không thể xử lý được chuyển đến đúng nơi và vẫn giữ thông tin cần điều tra.
- **Idempotency test:** gửi cùng message nhiều lần và xác nhận tác dụng phụ nghiệp vụ chỉ xảy ra một lần.

Với broker, nên kiểm thử acknowledgement, requeue, redelivery, publisher confirm và dead-letter policy trên đúng loại broker đang sử dụng. Các semantics này không thể được suy ra chỉ từ class exception.

## 11. Quy trình xử lý một messaging failure

Khi nhận được lỗi, hãy thực hiện theo thứ tự:

1. Xác định exception cụ thể và package của nó.
2. Xác định failed message, message ID, correlation ID và điểm phát sinh.
3. Đọc cause gốc và stack trace để tìm lỗi hạ tầng, lỗi dữ liệu hay lỗi nghiệp vụ.
4. Kiểm tra message đã được channel/broker tiếp nhận chưa và acknowledgement đang ở trạng thái nào.
5. Phân loại lỗi tạm thời, lỗi vĩnh viễn hoặc lỗi lập trình.
6. Chọn retry có giới hạn, error channel, DLQ hoặc xử lý nghiệp vụ tương ứng.
7. Đảm bảo consumer idempotent trước khi bật redelivery/retry.
8. Ghi log/metric đủ để theo dõi mà không làm lộ payload nhạy cảm.

## 12. Ghi nhớ

**MessagingException** là exception nền tảng cho lỗi messaging và có thể giữ failed message cùng cause. **MessageDeliveryException** mô tả lỗi khi gửi hoặc chuyển giao message. **MessageHandlingException** mô tả lỗi trong lúc handler xử lý message.

Phân loại exception giúp định vị giai đoạn lỗi, nhưng không tự quyết định message đã được lưu, có được retry hay đã bị mất. Những quyết định đó phụ thuộc channel, transport, transaction và acknowledgement. Hãy giữ failed message và cause, xử lý lỗi theo khả năng phục hồi, giới hạn retry, dùng DLQ khi phù hợp và thiết kế consumer idempotent để hệ thống messaging hoạt động ổn định khi có sự cố.