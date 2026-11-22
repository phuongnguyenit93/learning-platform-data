# Không nuốt exception hoặc mất correlation trong Spring Integration Runtime

## Mục tiêu bài học

Trong **Spring Integration Runtime**, message đi qua channel, endpoint, consumer, poller và executor. Khi một handler lỗi, hệ thống phải biết **lỗi thuộc về message nào**, **có được xử lý thành công hay chưa**, **nên retry, rollback, chuyển vào hàng đợi lỗi hay báo cho bên gọi**. Nếu một thành phần bắt exception rồi bỏ qua, hoặc làm mất khóa tương quan khi biến đổi message, flow có thể báo thành công giả, xử lý trùng, gom sai message hoặc mất khả năng truy vết sự cố.

Sau bài này, bạn có thể:

- Nhận diện việc **nuốt exception** và phân biệt với xử lý lỗi có quyết định nghiệp vụ rõ ràng.
- Giải thích đường đi của lỗi trong **DirectChannel**, **ExecutorChannel**, **poller**, **gateway** và **errorChannel**.
- Đọc **ErrorMessage**, **MessagingException**, **failedMessage** và original message đúng cách để truy ra nguồn lỗi.
- Bảo toàn **correlationId**, business key và **idempotency key** qua transform, retry, split, aggregate và các ranh giới bất đồng bộ.
- Thiết kế retry, transaction, message store, quarantine/DLQ và khả năng quan sát để không vô tình tuyên bố thành công.
- Kiểm thử để chứng minh lỗi không bị mất và message có thể được liên kết với đúng nghiệp vụ.

> Nguyên tắc: **Mỗi lỗi phải có một kết cục có chủ đích**: trả lỗi cho caller, rollback để nguồn phát lại, retry có giới hạn, ghi nhận thất bại bền vững, chuyển quarantine/DLQ, hoặc đánh dấu một lỗi nghiệp vụ là đã được xử lý. Chỉ ghi log rồi tiếp tục thường không đủ.

## 1. Thế nào là “nuốt exception”?

**Nuốt exception** xảy ra khi code bắt lỗi nhưng không truyền lỗi đi tiếp, không trả trạng thái thất bại phù hợp và cũng không thực hiện một quy trình xử lý cuối có thể theo dõi.

Ví dụ service activator xử lý yêu cầu thanh toán:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;

// Ví dụ sai: log lỗi rồi để method kết thúc bình thường.
@ServiceActivator(inputChannel = "paymentRequests")
public void handle(Message<PaymentCommand> message) {
    try {
        paymentClient.charge(message.getPayload());
    } catch (RuntimeException ex) {
        log.error("Thanh toán thất bại", ex);
        // Không ném lại, không ghi nhận thất bại,
        // không chuyển sang một cơ chế retry/quarantine.
    }
}
~~~

Caller đồng bộ có thể không thấy exception. Với consumer/poller hoặc adapter, việc method trở về bình thường có thể khiến tầng trên xem lần xử lý này đã hoàn tất, tùy cấu hình acknowledgement và transaction. Việc **log lỗi** chỉ là quan sát; nó không tự phục hồi thao tác, không tạo retry và không bảo đảm message được giữ lại.

Các biến thể khác:

- Catch rồi trả về **null** trong bước vốn cần tạo reply, khiến nhánh downstream không có kết quả hoặc báo timeout mà không rõ nguyên nhân.
- Catch rồi trả về DTO mặc định như **success=true** hoặc đối tượng rỗng, che lấp lỗi nghiệp vụ.
- Future hoặc task chạy trên executor lỗi nhưng bên gọi không quan sát kết quả, không gắn error flow.
- Catch rồi tạo message mới nhưng làm rơi **correlationId**, requestId hoặc thông tin lỗi gốc.
- Error handler chỉ ghi log và kết thúc trong khi hệ thống vận hành tưởng rằng có cơ chế lưu/retry thất bại.

Ngược lại, **xử lý exception có chủ đích** là hợp lệ. Ví dụ một lệnh trùng đã được xác nhận trước đó có thể trả kết quả **already-processed** theo hợp đồng idempotency; một thông báo không quan trọng có thể được chấp nhận bỏ qua nếu chính sách đó đã được định nghĩa và đo lường.

## 2. Đường đi của exception phụ thuộc vào channel và thread

Không thể suy luận đường đi của lỗi chỉ từ tên handler. Cần xác định message đang được xử lý **trong thread của sender hay thread khác**.

~~~mermaid
flowchart TD
    A["Producer / Gateway"] --> D["DirectChannel"]
    D --> H1["Handler đồng bộ"]
    H1 -- "throw" --> A
    B["Producer"] --> E["ExecutorChannel"]
    E --> H2["Handler trên worker thread"]
    H2 -- "throw" --> EM["ErrorMessage"]
    EM --> EC["errorChannel theo cấu hình"]
    EC --> EH["Error handler / retry / quarantine"]
~~~

Sơ đồ biểu diễn hai đường chạy điển hình, **không khẳng định mọi gateway và adapter luôn có cùng hành vi**. Một gateway có cấu hình error channel hoặc error reply riêng có thể chuyển lỗi thành reply theo hợp đồng; một adapter có cơ chế acknowledgement hoặc recovery đặc thù.

| Bối cảnh | Lỗi xuất hiện ở đâu? | Điều cần làm rõ |
| --- | --- | --- |
| **DirectChannel** | Handler thường chạy trên thread gọi send; exception có thể lan ngược tới sender | Caller có bắt rồi bỏ lỗi không? Gateway có quy tắc đổi exception thành reply không? |
| **ExecutorChannel** | Handler chạy trên thread của TaskExecutor; sender có thể đã hoàn tất send | Lỗi được publish về error channel nào, ai tiêu thụ, có đường lưu thất bại không? |
| **QueueChannel + polling endpoint** | Handler được gọi từ một lần poll; transaction và advice có thể bọc lời gọi đó | Poller có retry/transaction/error channel không? Message sẽ được lấy lại hay bị tiêu thụ? |
| **Inbound adapter / broker consumer** | Exception có thể xảy ra trong deserialization, trước hoặc sau khi tạo Spring Message | Broker có ack/nack, redelivery, DLQ và chính sách offset nào? |
| **Aggregator / resequencer** | Lỗi có thể nằm ở release strategy, message store hoặc processor | Group nào bị ảnh hưởng, state group có được giữ lại, timeout/late arrival xử lý ra sao? |

Trong Spring Integration, lỗi xử lý bất đồng bộ thường được bọc thành **ErrorMessage** và gửi tới error channel được xác định bởi header **errorChannel** hoặc cấu hình lỗi toàn cục. Nhưng đường đồng bộ truyền exception cho caller không nhất thiết tự gửi thêm ErrorMessage. Trước khi thiết kế xử lý lỗi, hãy kiểm tra chính xác endpoint/adapter có phải là **bên phát ErrorMessage** hay không.

### Error channel không tự động đồng nghĩa retry hoặc rollback

Một error channel nhận được ErrorMessage không có nghĩa message được phát lại. Nếu error handler nhận rồi chỉ log và trả về bình thường, thì đó có thể là **điểm kết thúc của lỗi**. Transaction có commit hay rollback, nguồn có redeliver hay không, còn phụ thuộc chỗ lỗi bị bắt và advice/transaction/adapter cụ thể.

Vì vậy phải phân biệt:

1. **Phát hiện lỗi**: handler ném exception.
2. **Truyền lỗi**: exception tới caller hoặc ErrorMessage tới error flow.
3. **Quyết định phục hồi**: retry/rollback/quarantine/trả lỗi nghiệp vụ.
4. **Ghi nhận trạng thái**: message đã xử lý, đã thất bại hay còn đang chờ.

Bốn bước này có thể ở các thành phần khác nhau; không được mặc định bước trước bảo đảm bước sau.

## 3. Viết handler không giấu lỗi và giữ được failedMessage

Trong Spring Messaging, **MessagingException** có thể mang **failedMessage**. Khi cần bọc lỗi để thêm ngữ cảnh, hãy **giữ exception gốc làm cause** và liên kết với chính message đang xử lý:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.stereotype.Component;

record PaymentCommand(String orderId, String requestId, long amount) {}

interface PaymentClient {
    void charge(PaymentCommand command);
}

@Component
class PaymentHandler {
    private final PaymentClient paymentClient;

    PaymentHandler(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }

    @ServiceActivator(inputChannel = "paymentRequests")
    public void handle(Message<PaymentCommand> message) {
        PaymentCommand command = message.getPayload();
        try {
            paymentClient.charge(command);
        } catch (RuntimeException cause) {
            throw new MessagingException(
                    message,
                    "Không thể thanh toán orderId=" + command.orderId(),
                    cause);
        }
    }
}
~~~

Khi caller hoặc error flow nhìn thấy **MessagingException**, họ có thể lấy:

- **getFailedMessage()**: message liên quan đến lỗi (nếu có).
- **getCause()**: nguyên nhân gốc để phân loại transient/permanent.
- **MessageHeaders** của failed message: correlationId, requestId, loại sự kiện, tên tenant nếu phù hợp chính sách dữ liệu.

Không tạo exception mới chỉ có thông báo ngắn như “Payment failed” rồi bỏ nguyên nhân và message ban đầu; điều đó cắt mất manh mối quan trọng. Tuy nhiên, **không phải mọi exception đều là MessagingException** và không phải mọi MessagingException đều có failedMessage. Consumer lỗi phải xử lý được trường hợp thiếu.

**Chú ý tính idempotent:** Code trên truyền lỗi đúng cách nhưng **chưa chống thanh toán lặp**. Nếu payment provider đã trừ tiền rồi bị timeout khi trả lời, retry có thể gọi lại. Phải truyền **requestId/idempotency key** được provider hỗ trợ, hoặc có cơ chế đối soát và bù trừ phù hợp.

## 4. Đọc ErrorMessage để truy ra lỗi và message liên quan

**ErrorMessage** là một Spring Message với payload là **Throwable**. Bản thân headers của ErrorMessage không nhất thiết chứa đầy đủ correlation headers của message nghiệp vụ. Cần xem cả **original message** (nếu có) và **failedMessage** của MessagingException.

Sơ đồ:

~~~text
ErrorMessage
  payload: Throwable
    └─ MessagingException (có thể nằm trong cause chain)
         ├─ failedMessage: Message<PaymentCommand>
         └─ cause: lỗi gốc
  originalMessage: có thể có, tùy bên publish lỗi
  headers: headers của chính ErrorMessage
~~~

Một error handler dành riêng cho nhánh lỗi:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

record FailedPayment(
        String requestId,
        String correlationId,
        String errorType) {}

interface FailureJournal {
    // Triển khai thực tế cần lưu bền vững và chống lưu trùng theo requestId.
    void record(FailedPayment failure);

    // Quarantine cả khi không thể xác định correlation.
    void quarantine(ErrorMessage error);
}

@Component
class PaymentErrorConsumer {
    private final FailureJournal journal;

    PaymentErrorConsumer(FailureJournal journal) {
        this.journal = journal;
    }

    @ServiceActivator(inputChannel = "paymentErrors")
    public void onError(ErrorMessage error) {
        Message<?> failed = error.getOriginalMessage();
        Throwable failure = error.getPayload();

        // Một số publisher không gắn originalMessage.
        // Tìm failedMessage của MessagingException trong chuỗi cause.
        if (failed == null) {
            for (Throwable current = failure;
                    current != null; current = current.getCause()) {
                if (current instanceof MessagingException messaging
                        && messaging.getFailedMessage() != null) {
                    failed = messaging.getFailedMessage();
                    break;
                }
            }
        }

        if (failed == null) {
            journal.quarantine(error);
            return; // Chỉ kết thúc khi quarantine đã ghi nhận thành công.
        }

        Object requestId = failed.getHeaders().get("requestId");
        Object correlationId = failed.getHeaders().get("correlationId");
        if (!(requestId instanceof String request) || request.isBlank()
                || !(correlationId instanceof String correlation)
                || correlation.isBlank()) {
            journal.quarantine(error);
            return;
        }

        journal.record(new FailedPayment(
                request,
                correlation,
                failure.getClass().getName()));
    }
}
~~~

Đây là **mẫu minh họa trách nhiệm của error consumer**: nó không dừng ở log mà chuyển thông tin thất bại tới **FailureJournal** có tính bền vững. Trong triển khai thật, journal có thể ghi DB, quarantine store hoặc phát event qua transactional outbox. Thêm trạng thái **pending / failed / quarantined**, timestamp, nguồn, số attempt và chính sách lưu giữ để có thể điều tra hoặc phát lại có kiểm soát.

Nếu FailureJournal thất bại, **không được mặc định** lỗi này sẽ tự retry: cần định nghĩa retry/transaction của **chính error flow** và phương án dự phòng khi hạ tầng ghi lỗi hỏng. Đồng thời tránh thiết kế error handler gửi thất bại ngược về chính error channel vô hạn.

### Nối một error channel có chủ đích

Giả sử flow dùng **ExecutorChannel** trước payment handler, và có một bean channel tên **paymentErrors**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
class PaymentErrorChannels {
    @Bean
    MessageChannel paymentErrors() {
        return new DirectChannel();
    }
}

// Ở producer, khi tạo Spring Message để đưa vào flow bất đồng bộ:
Message<PaymentCommand> message = MessageBuilder
        .withPayload(new PaymentCommand("O-42", "pay-42", 125000))
        .setHeader("requestId", "pay-42")
        .setHeader("correlationId", "checkout-42")
        .setHeader(MessageHeaders.ERROR_CHANNEL, "paymentErrors")
        .build();
~~~

Trong bối cảnh có publisher lỗi bất đồng bộ hỗ trợ header **errorChannel**, header này chỉ định địa chỉ nhận ErrorMessage. Đây là **mảnh cấu hình minh họa**, cần nối producer, channel, executor và handler thực tế. Nếu đường chạy vẫn là **DirectChannel** đồng bộ và exception lan về caller, header errorChannel **không tự kích hoạt** error consumer.

Khi cấu hình global **errorChannel**, lưu ý subscriber mặc định có thể chỉ logging; cần kiểm tra nơi lỗi thật sự được xử lý và tránh cạnh tranh hoặc xử lý trùng giữa các subscriber với side effect khác nhau.

## 5. Correlation là gì và tại sao dễ mất?

**Correlation** là khả năng liên kết message, kết quả và lỗi với đúng một luồng công việc hoặc thực thể nghiệp vụ. Cần phân biệt các ID:

| Trường | Ý nghĩa phổ biến | Có ổn định qua retry/transform không? |
| --- | --- | --- |
| **MessageHeaders.ID** | Định danh kỹ thuật của một Spring Message | Không nên giả định ổn định khi tạo message mới hoặc chuyển qua hệ thống khác |
| **correlationId** | Khóa liên kết các message cùng nhóm/flow | Có thể ổn định nếu chủ động chuyển tiếp; cũng có thể bị splitter/aggregator thiết lập theo quy tắc riêng |
| **requestId / idempotencyKey** | Định danh một yêu cầu nghiệp vụ cần xử lý tối đa một lần về mặt tác dụng | Nên giữ ổn định qua retry/redelivery; dùng kiểm soát duplicate |
| **orderId / businessKey** | Định danh thực thể nghiệp vụ | Có thể chung cho nhiều yêu cầu khác nhau; không thay thế requestId |
| **traceId / spanId** | Truy vết một execution phân tán | Span có thể đổi qua bước xử lý; trace context cần propagate theo chuẩn quan sát |
| **sequenceNumber / sequenceSize** | Metadata thứ tự/kích thước nhóm, thường dùng với splitter/aggregator | Phụ thuộc EIP và cấu hình sequencing; không nên coi là khóa nghiệp vụ |

**Không dùng message ID làm idempotency key** nếu yêu cầu cần chống trùng xuyên adapter, broker hoặc các lần retry tạo message mới. Tương tự, chỉ có orderId thường không đủ: một đơn hàng có thể trải qua nhiều thao tác hợp lệ như tạo, thanh toán, hoàn tiền.

### Ba nơi correlation hay bị đánh rơi

**1. Transformer tạo Message mới nhưng quên header**

~~~java
// Dễ mất metadata nếu chủ động tạo message mới chỉ từ payload.
return MessageBuilder.withPayload(normalizedOrder).build();
~~~

Khắc phục bằng chính sách header rõ ràng:

~~~java
return MessageBuilder.withPayload(normalizedOrder)
        .setHeader("correlationId", incoming.getHeaders().get("correlationId"))
        .setHeader("requestId", incoming.getHeaders().get("requestId"))
        .build();
~~~

Trong một số transformer của Spring Integration, framework có thể tự hỗ trợ chuyển tiếp headers khi method trả payload. Tuy nhiên khi **tự tạo Message**, dùng converter/adapter đặc biệt hoặc map headers outbound, hãy kiểm tra kết quả thực tế. Chỉ copy các header có ý nghĩa; **contentType**, ACK handle, routing metadata hoặc header của giao thức cũ có thể không còn đúng sau khi đổi biểu diễn.

**2. Chuyển thread và phát lỗi bất đồng bộ**

Sau **ExecutorChannel**, sender có thể không còn đợi handler. ErrorMessage do worker tạo có headers riêng; lấy correlation từ **failed/original message**, không chỉ từ ErrorMessage.headers. Nếu một endpoint dùng **errorChannel** trong header, hãy bảo đảm header được bảo toàn hoặc thay thế bằng cấu hình error channel tương đương.

**3. Split, aggregate, retry và redelivery**

- **Splitter** có thể sinh nhiều message con và thiết lập correlation/sequence headers. Nếu custom splitter ghi đè khóa nhóm tùy tiện, aggregator có thể gom nhầm hoặc để group chờ mãi.
- **Aggregator** gom message theo correlation strategy và release strategy; một lỗi trong message con cần giữ cả **business key** lẫn **group key** để điều tra.
- **Retry** thực thi lại xử lý; một lần thử mới không phải yêu cầu nghiệp vụ mới. Giữ idempotency key ổn định, có thể gắn thêm attemptNumber riêng cho chẩn đoán.
- **Redelivery từ broker** có thể tạo đối tượng Spring Message mới. Chỉ dựa vào ID kỹ thuật để so sánh hai lần nhận sẽ dễ bỏ sót duplicate.

~~~mermaid
flowchart TD
    REQ["requestId=pay-42\ncorrelationId=checkout-42"] --> T["Transformer"]
    T --> E["ExecutorChannel"]
    E --> H["Payment handler"]
    H -- "exception" --> ERR["ErrorMessage"]
    ERR --> EX["Trích failed/original message"]
    EX --> J["FailureJournal / DLQ"]
    J --> O["Tra cứu được pay-42\ntrong checkout-42"]
~~~

Mục tiêu là **có thể lần ngược từ lỗi tới hành động nghiệp vụ gốc**, ngay cả khi qua nhiều thread, nhiều message nội bộ hoặc khi app restart.

## 6. Quyết định retry, rollback, DLQ và trạng thái xử lý

Không phải mọi lỗi đều nên retry; không phải lỗi nào cũng có cùng ranh giới transaction.

| Loại lỗi | Ví dụ | Hành động thường phù hợp |
| --- | --- | --- |
| **Tạm thời** | Timeout dịch vụ ngoài, kết nối DB chập chờn, rate limit | Retry có giới hạn, backoff/jitter; kiểm soát idempotency |
| **Dữ liệu không hợp lệ** | JSON sai schema, trường bắt buộc thiếu, amount âm | Ghi lỗi và quarantine/DLQ; chờ sửa dữ liệu, không retry vô hạn |
| **Vi phạm bất biến / xung đột** | Đơn đã thanh toán, version quá cũ | Quy tắc nghiệp vụ cụ thể; đôi khi trả kết quả đã xử lý, đôi khi conflict |
| **Lỗi lập trình** | NullPointerException, mapping không hỗ trợ | Báo động, cô lập message gây lỗi, sửa code; tránh retry nóng vô hạn |
| **Không xác định kết quả của side effect** | API bên ngoài đã thực hiện nhưng response timeout | Dùng idempotency key/đối soát trước khi quyết định retry |

### Retry không xóa side effect đã xảy ra

~~~text
1. Handler gọi payment provider → provider xử lý thành công.
2. Kết nối bị timeout trước khi handler nhận response.
3. Handler ném exception → retry lần 2.
4. Nếu không có idempotency key, provider có thể thu tiền lần 2.
~~~

Giữ **requestId=pay-42** xuyên suốt các attempt là điều kiện cần để chống duplicate; phía provider hoặc kho dữ liệu phải **thực thi** cơ chế idempotency. Chỉ log cùng requestId không tạo ra tính idempotent.

### Transaction với DirectChannel và ExecutorChannel

Với một chuỗi **DirectChannel** đồng bộ, handler có thể tham gia transaction đang gắn với thread, nếu các advice và resource được cấu hình tương thích. Exception được ném ra có thể kích hoạt rollback theo chính sách transaction. Tuy nhiên rollback DB không hoàn tác tự động email, HTTP hay API thanh toán đã gọi.

Với **ExecutorChannel**, xử lý chạy trên thread khác; transaction/ThreadLocal của sender không tự chuyển sang consumer. Muốn transaction bảo vệ đoạn ghi DB tại handler, hãy thiết lập ranh giới transaction ở phía consumer hoặc nguồn phù hợp. Đừng suy luận transaction từ việc producer gửi message thành công.

### Retry advice và recovery

Spring Integration có các cơ chế advice/retry cho endpoint, trong đó **RequestHandlerRetryAdvice** có thể bao bọc việc gọi handler. Sau khi cạn lần thử, **recovery callback** có thể chuyển lỗi vào error channel thông qua cơ chế như **ErrorMessageSendingRecoverer**.

Khi dùng retry advice, cần định nghĩa cụ thể:

- Retry bao quanh **bước nào** (handler, poller, adapter), có side effect nào đã xảy ra trước đó?
- Những exception nào đáng retry và backoff tối đa ra sao?
- Hết retry thì exception được **ném tiếp**, chuyển thành ErrorMessage, lưu thất bại hay DLQ?
- Khi recovery tiêu thụ lỗi, **transaction và acknowledgement** phản ứng thế nào theo adapter?
- Hệ thống có thông tin **requestId, correlationId, attempt** để điều tra không?

Không gắn error handler chỉ để trả về bình thường rồi mặc định broker sẽ redeliver. Nếu cần broker redelivery, phải kiểm tra đường ném lỗi, chính sách ack/nack và transaction của chính adapter.

## 7. Correlation qua message store, restart và nhiều instance

Correlation được giữ trong header hoặc payload ở một thời điểm **chưa đủ** để vận hành bền vững:

- **QueueChannel** hoặc **MessageGroupStore** dùng bộ nhớ có thể mất message/state khi process dừng; persistent store có thể giữ qua restart nhưng cần schema/serializer và transaction phù hợp.
- Message có header chứa object không serialize được, ví dụ một channel hoặc callback trong JVM, có thể gặp vấn đề khi lưu bền vững. Cần chính sách header mapping và đăng ký channel phù hợp thay vì copy mọi header tùy tiện.
- **Aggregator** có thể sử dụng correlationId để định nhóm; khi scale nhiều instance cần xem xét lock registry, shared store, timeout, incomplete group và xử lý late arrivals.
- **FailureJournal** hoặc DLQ nên lưu **businessId, requestId, correlationId, error category, thời điểm, attempt, trạng thái**, cùng payload đã làm sạch hoặc tham chiếu an toàn để replay. Không dựa hoàn toàn vào log RAM.
- Khi replay message cũ, cần giữ **idempotency key**, nhưng có thể cấp **execution/trace span mới** để quan sát lần phát lại.
- Việc dừng/khởi động **IntegrationFlow** không đảm bảo lỗi đang xử lý đã được ghi nhận, cũng không tự tạo retry. Phải xem lifecycle, trạng thái store, executor in-flight và điểm đóng nhận message.

Một mẫu bản ghi thất bại:

~~~json
{
  "requestId": "pay-42",
  "correlationId": "checkout-42",
  "businessId": "O-42",
  "flow": "payment",
  "stage": "paymentHandler",
  "attempt": 3,
  "status": "QUARANTINED",
  "errorType": "PAYMENT_TIMEOUT",
  "occurredAt": "2026-01-15T10:00:00Z"
}
~~~

Đây là **ví dụ định dạng**, không phải schema mặc định của Spring Integration. Không ghi dữ liệu thẻ thanh toán hoặc bí mật vào journal. Nếu lưu payload, cân nhắc mã hóa, kiểm soát quyền truy cập, TTL và phiên bản schema.

## 8. Quan sát lỗi mà không mất ngữ cảnh

Mỗi thông điệp log/trace quan trọng nên trả lời được:

1. **Message nào?** requestId, correlationId, businessId, message type.
2. **Ở đâu?** flow name, channel, endpoint, consumer, thread, application instance.
3. **Đã xảy ra gì?** exception class, cause chain, attempt, bước xử lý và kết quả side effect đã xác định hay chưa.
4. **Tiếp theo ra sao?** RETRYING, FAILED, QUARANTINED, REPLAYED, COMPLETED.

Ví dụ một log có cấu trúc:

~~~text
level=ERROR flow=payment endpoint=paymentHandler
requestId=pay-42 correlationId=checkout-42 businessId=O-42
thread=payment-worker-3 attempt=2 errorType=PAYMENT_TIMEOUT
nextAction=RETRY outcome=UNKNOWN
~~~

**Không đồng nhất trace ID với correlation ID.** Trace/span được hệ thống quan sát tạo và propagate theo ngữ cảnh thực thi; business correlation thường cần tồn tại lâu hơn một lần thử hoặc một request HTTP. Có thể ghi cả hai với vai trò riêng.

Theo dõi các chỉ số:

- Số lần xử lý thành công/thất bại theo endpoint, phân loại exception, số attempt.
- Retry rate, lỗi sau cạn retry, DLQ/quarantine size và tuổi lâu nhất.
- Độ dài hàng đợi executor, số task bị từ chối, độ trễ xử lý và backlog poller.
- Aggregator group chưa release, group timeout, message trùng và late arrivals.
- Số lỗi **không truy được requestId/correlationId** — đây là tín hiệu chất lượng metadata, không nên bỏ qua.

Với hệ thống xử lý lỗi tập trung, cần thêm giới hạn dung lượng và thông tin PII; không log nguyên payload bí mật chỉ để thuận tiện debug.

## 9. Kiểm thử đảm bảo lỗi và correlation không bị mất

### A. Unit test cho handler đồng bộ

Giả lập payment client ném exception; xác minh handler ném **MessagingException** có **cause** và **failedMessage** đúng:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

class PaymentHandlerTest {
    @Test
    void propagatesFailureWithOriginalMessage() {
        RuntimeException providerTimeout =
                new RuntimeException("provider timeout");
        PaymentClient client = command -> {
            throw providerTimeout;
        };
        PaymentHandler handler = new PaymentHandler(client);

        Message<PaymentCommand> input = MessageBuilder
                .withPayload(new PaymentCommand("O-42", "pay-42", 125000))
                .setHeader("requestId", "pay-42")
                .setHeader("correlationId", "checkout-42")
                .build();

        MessagingException error = assertThrows(
                MessagingException.class,
                () -> handler.handle(input));

        assertSame(input, error.getFailedMessage());
        assertSame(providerTimeout, error.getCause());
        assertEquals("checkout-42",
                error.getFailedMessage()
                        .getHeaders().get("correlationId"));
    }
}
~~~

Test này xác minh handler giữ lỗi và metadata **khi gọi trực tiếp**. Nó chưa chứng minh toàn bộ flow xử lý đúng khi qua executor/adapter, nên cần kiểm thử tích hợp.

### B. Integration test cho flow bất đồng bộ

Tạo channel đầu vào, **ExecutorChannel**, handler cố tình ném lỗi và error consumer nhận ErrorMessage. Dùng cơ chế đồng bộ trong test như CountDownLatch để chờ event thay vì **sleep** theo thời gian tùy ý. Kiểm tra:

- Producer send xong, lỗi **được chuyển tới error flow** đúng như cấu hình.
- ErrorMessage có nguyên nhân gốc; original/failed message cho phép lấy **requestId và correlationId**.
- Journal ghi **đúng một kết quả thất bại có chủ đích** theo idempotency key; không nhầm thành success.
- Nếu không có correlation, message đi vào **quarantine** và tạo cảnh báo; không tự gán một ID tùy tiện.
- Sau khi retry, requestId giữ nguyên; attempt khác nhau nhưng không sinh nhiều charge nghiệp vụ.

### C. End-to-end test cho transaction, redelivery và restart

Thử từng tình huống:

| Tình huống giả lập | Bằng chứng cần thu |
| --- | --- |
| Handler ném lỗi ngay khi bắt đầu | Caller/error flow nhìn thấy lỗi; trạng thái success không được ghi sai |
| Lỗi DB trong transaction | Rollback thực sự xảy ra; redelivery theo cấu hình nguồn |
| Timeout sau khi external API đã xử lý | Idempotency/đối soát ngăn side effect trùng |
| Message đi qua transformer tự tạo Message mới | Correlation/requestId còn đúng, contentType được điều chỉnh nếu cần |
| Splitter tạo nhiều phần và aggregator chờ kết quả | Mỗi phần có group key/sequence phù hợp, lỗi xác định được nhóm |
| Executor quá tải hoặc rejected task | Error/metric phản ánh lỗi dispatch, không lặng lẽ mất message |
| Restart khi có message in-flight/persistent store | Trạng thái, khóa tương quan và chính sách replay được giữ đúng |
| Error journal/DLQ tạm không khả dụng | Có retry/fallback được xác định; lỗi của chính error handler được quan sát |

## 10. Bài thực hành: tìm lỗ hổng trong một flow

Giả sử có flow:

~~~text
HTTP gateway
  → DirectChannel
  → JSON transformer
  → ExecutorChannel
  → payment handler
  → outbound event

errorChannel
  → logger
~~~

Điều kiện ban đầu:

- JSON transformer **tự tạo** Message mới chỉ từ payload.
- Payment handler có catch(Exception) rồi chỉ log.
- Outbound event dùng **MessageHeaders.ID** để chống trùng.
- Error channel toàn cục chỉ có logging subscriber.

Hãy phân tích các lỗi có thể xuất hiện:

1. **Mất correlation:** transformer không chủ động giữ requestId/correlationId nên error flow thiếu khóa truy vết.
2. **Mất tín hiệu thất bại:** payment handler kết thúc bình thường; error publisher có thể không nhận được exception để đưa lên error channel.
3. **Chống trùng sai khóa:** message ID kỹ thuật có thể đổi khi chuyển đổi hoặc replay, khiến cùng request bị tính là nhiều nghiệp vụ.
4. **Phục hồi không xác định:** nếu lỗi còn được phát tới logger, chỉ log không chứng minh đã retry, rollback hay quarantine.

Một phương án sửa:

- Giữ **business correlation và requestId** khi biến đổi, xác minh headers qua integration test.
- Để handler **ném lỗi có cause và failedMessage**, chỉ chuyển thành business outcome khi có quy tắc rõ ràng.
- Thiết kế error flow lưu **FailureJournal/DLQ** và phát cảnh báo, có cách phát lại an toàn.
- Áp dụng idempotency key ở tầng thực thi side effect, với retry/backoff và transaction đúng ranh giới.
- Đo số message thất bại **không có correlation** để phát hiện regression.

## 11. Checklist trước khi vận hành

- **Propagation:** Mọi catch block xử lý lỗi bằng kết quả cụ thể hoặc ném lại với cause; không log rồi bỏ qua vô điều kiện.
- **Thread boundary:** Với DirectChannel, ExecutorChannel và poller, biết lỗi đi về caller hay error flow nào.
- **Error flow:** Có consumer thực sự xử lý ErrorMessage, có trạng thái cuối và cơ chế thất bại của chính error handler.
- **Identity:** Dùng business key, requestId/idempotency key và correlationId đúng vai trò; không lẫn với message ID hoặc trace ID.
- **Header contract:** Transformer, gateway, adapter, splitter và aggregator giữ/mapping correlation theo kiểm thử.
- **Retry:** Phân loại lỗi, giới hạn số lần, backoff và kết cục khi hết retry; tránh lặp side effect.
- **Transaction:** Biết transaction bắt đầu/kết thúc ở đâu, đặc biệt tại executor và external API.
- **Persistence:** Message store, FailureJournal hoặc DLQ giữ được trạng thái cần thiết khi restart.
- **Observability:** Có log/trace/metric cho lost correlation, exception cause và quarantine tồn đọng.
- **Verification:** Unit test kiểm tra cause/failedMessage; integration test kiểm tra async error path và replay.

## Kết luận

Trong Spring Integration, **để exception tiếp tục có ý nghĩa** và **giữ correlation xuyên suốt message flow** là hai điều kiện cốt lõi để runtime đáng tin cậy. Channel quyết định đường thực thi, endpoint và advice quyết định cách truyền lỗi, transaction/retry quyết định phục hồi, còn business correlation giúp gắn mọi kết quả với đúng yêu cầu. Thiết kế tốt không dừng ở bắt lỗi: nó **làm rõ trạng thái cuối của message** và cho phép điều tra, sửa chữa hoặc phát lại mà không nhân đôi tác dụng nghiệp vụ.

## Tài liệu tham khảo

- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Framework API — MessagingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html)
- [Spring Framework API — ErrorMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html)
