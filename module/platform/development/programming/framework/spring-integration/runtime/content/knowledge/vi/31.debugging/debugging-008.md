# Phân biệt lỗi runtime với lỗi adapter trong Spring Integration

## Mục tiêu bài học

Trong **SPRING_INTEGRATION_RUNTIME**, message đi qua **channel, endpoint, consumer, poller, executor**, có thể được lưu trong **MessageStore**, chịu **transaction/retry**, xử lý theo **correlation**, rồi giao tiếp với broker, HTTP service, hệ thống file hoặc database. Khi sự cố xuất hiện, thông báo như “message delivery failed”, “request timed out” hoặc “error in polling task” thường **chưa đủ** để xác định lỗi nằm ở phần nào.

Bài thuộc chương **Debugging**, với đề tài **Phân biệt lỗi runtime với lỗi adapter**. Mục tiêu là tìm **điểm phát sinh lỗi đầu tiên**, **cơ chế lan truyền lỗi** và **quyết định khôi phục phù hợp** thay vì sửa nhầm tầng.

Sau bài này, bạn có thể:

1. Phân biệt lỗi **điều phối nội bộ Spring Integration** và lỗi **biên tích hợp** của inbound/outbound adapter.
2. Phân loại lỗi theo **giai đoạn**: trước khi tạo Message, lúc dispatch/handle, trong lời gọi ra ngoài, lúc commit/ack và khi phục hồi.
3. Đọc **MessagingException**, **MessageHandlingException**, **MessageDeliveryException**, **ErrorMessage**, **failedMessage**, original message và cause chain mà không kết luận vội theo tên exception.
4. Giải thích ảnh hưởng của **DirectChannel, ExecutorChannel, QueueChannel, poller** đến đường lan truyền lỗi và transaction.
5. Dùng correlation, log, metrics, tracing, WireTap/QueueChannel trong test để tìm message mất hoặc xử lý trùng.
6. Chọn **retry/backoff, rollback/redelivery, quarantine/DLQ, reconciliation** theo nguyên nhân thực tế.
7. Thiết kế test tái hiện một lỗi runtime và một lỗi adapter, xác minh nơi lỗi xuất hiện và trạng thái message sau failure.

> **Nguyên tắc:** “Runtime” và “adapter” là **hai góc nhìn về nguyên nhân**, không phải hai nhóm exception tách biệt tuyệt đối. Lỗi adapter có thể được framework bọc trong MessagingException; một lỗi runtime như executor bị từ chối task cũng có thể hiển thị trong log của inbound adapter.

## 1. Ranh giới runtime và adapter ở đâu?

Spring Integration thực thi các **Enterprise Integration Patterns (EIP)**. Trong một IntegrationFlow, framework chịu trách nhiệm chuyển message qua channel, gọi handler, sắp lịch poll, quản lý endpoint lifecycle, chuyển thread, lưu group state và phát lỗi. Adapter là phần tiếp xúc với **hệ thống/protocol bên ngoài**.

~~~mermaid
flowchart LR
    EX["Broker / File / HTTP / DB"] --> IA["Inbound adapter"]
    IA --> CH["MessageChannel"]
    CH --> EP["Endpoint / handler"]
    EP --> EA["Outbound adapter"]
    EA --> EXT["External service"]
    CH -. "runtime" .-> RT["Dispatcher / Executor / Poller / Transaction"]
    EP -. "runtime" .-> RT
    IA -. "protocol / binding" .-> AD["Adapter layer"]
    EA -. "protocol / binding" .-> AD
~~~

### Lỗi runtime: cơ chế điều phối nội bộ không đáp ứng hợp đồng

Ví dụ:

- **Channel không có subscriber** hoặc gửi tới sai channel.
- **Executor bị saturated**, từ chối task hoặc ứng dụng không kiểm soát backpressure.
- **Polling endpoint bị stop**, không có lịch poll, scheduler không chạy hoặc poller bị kẹt.
- **Handler/transformer/router** ném exception do logic, schema giả định sai hoặc không có route phù hợp.
- **Aggregator** không release vì sai correlation key/sequence/ReleaseStrategy hoặc MessageGroupStore bị contention.
- **Transaction** chưa bao phủ đúng thread/resource, rollback không như kỳ vọng.
- **MessageStore** in-memory mất state sau restart, hoặc persistent store không đọc lại được payload đã serialize.
- **Error flow** chưa được kết nối, handler nuốt lỗi, recovery đánh dấu thành công sai hoặc retry lồng tầng.

### Lỗi adapter: đường giao tiếp biên không thực hiện được chức năng

Ví dụ:

- Kafka/AMQP/JMS consumer không authenticate được, broker không sẵn sàng hoặc partition/queue không được gán như kỳ vọng.
- HTTP outbound gateway timeout, DNS/TLS lỗi, upstream trả 401/403/429/5xx hoặc body response không convert được.
- File/FTP/SFTP inbound adapter thiếu quyền đọc, file đang bị khóa, remote server mất kết nối hoặc filter/checkpoint xử lý sai.
- JDBC inbound/outbound adapter không kết nối DB, SQL lỗi, schema thay đổi hoặc quyền trên bảng bị thu hồi.
- Adapter mapping **payload/header/content-type** sai với hợp đồng của hệ thống bên ngoài.
- Ack/offset/commit thất bại hoặc kết quả gửi **không xác định** khi kết nối đứt đúng thời điểm.

**Hai nhóm có thể giao nhau:** Một JdbcMessageStore không ghi được vì database bị downtime là sự cố hạ tầng DB tại **thành phần runtime persistence**. Một HTTP outbound adapter ném MessagingException là lỗi **gọi bên ngoài** được biểu diễn bằng **exception của runtime**. Vì vậy cần ghi nhận cả **vị trí** và **nguyên nhân gốc**.

## 2. Ma trận nhận diện ban đầu

| Tín hiệu đầu tiên | Nghi vấn runtime | Nghi vấn adapter/ngoại vi | Bằng chứng cần tìm |
| --- | --- | --- | --- |
| Gửi message không có người nhận | Sai channel, thiếu subscriber, endpoint stopped | Input adapter tạo message đúng nhưng downstream chưa cấu hình | Channel bean name, subscribers, endpoint state, MessageDeliveryException |
| Poller không có message | Scheduler/poller chưa start, filter bỏ hết | File/broker/DB không trả dữ liệu hoặc mất kết nối | Lượt poll, receive() result, adapter exception, source checkpoint |
| Worker chậm, backlog tăng | Executor queue đầy, lock contention, retry storm | Downstream HTTP/DB chậm, broker throttle | Queue depth, active threads, per-stage timers |
| Có ErrorMessage nhưng thiếu requestId | Transformer làm mất headers, exception ở thread khác | Failure xảy ra trước khi adapter tạo Spring Message | originalMessage, failedMessage, source logs |
| Outbound handler timeout | Handler deadline/RetryAdvice gây chồng lấn | DNS, network, TLS, remote SLA | Root cause, client timeout, remote request ID |
| Message bị giao lại sau restart | Ack/transaction boundary chưa hợp lệ | Broker at-least-once, visibility timeout, offset chưa commit | Delivery attempts, business eventId, commit/ack timeline |
| Aggregator chờ mãi | Sai correlation, missing sequence, release strategy | Một nguồn upstream không gửi phần bắt buộc | Group metadata, groupId, source deliveries |
| Flow không còn chạy sau deploy | Bean/endpoint lifecycle, autoStartup=false | Adapter thiếu cấu hình hoặc không subscribe kết nối nguồn | isRunning, application startup errors, transport health |
| Message payload không decode được | Sai transformer/converter trong flow | Adapter nhận content-type hoặc schema mới | Raw bytes ở ranh giới adapter, converter stack, contract version |

Một triệu chứng có thể xuất hiện do **nhiều nguyên nhân**. Ví dụ “QueueChannel không còn tăng” có thể vì inbound adapter bị stop, vì adapter không nhận được message từ broker, hoặc vì source đang hết dữ liệu. **Không dùng một metric làm kết luận cuối cùng.**

## 3. Chẩn đoán theo giai đoạn thay vì theo tên exception

Gắn mỗi sự cố vào một giai đoạn kiểm chứng được:

~~~mermaid
flowchart TD
    A["1. External source / protocol"] --> B["2. Adapter đọc và chuyển đổi"]
    B --> C["3. Spring Message được tạo"]
    C --> D["4. Channel dispatch"]
    D --> E["5. Handler / business logic"]
    E --> F["6. Outbound adapter / external effect"]
    F --> G["7. Commit / ack / checkpoint"]
    G --> H["8. Recovery / restart"]
    B -. "Lỗi có thể chưa có failedMessage" .-> X["Source error"]
    D -. "Dispatcher / task scheduling" .-> Y["Runtime error"]
    E -. "Exception của handler" .-> Y
    F -. "Protocol/network/remote" .-> Z["Adapter error"]
    G -. "Unknown outcome / redelivery" .-> Z
~~~

Đặt ba câu hỏi:

1. **Message đã tồn tại chưa?** Source có thể lỗi ở bước nhận file, poll DB, kết nối broker **trước khi tạo Spring Message**. Khi đó không chắc có failedMessage.
2. **Lỗi phát sinh trong thành phần nào?** Bean/channel/handler hay connection, protocol, parser và client bên ngoài? Xem cause sâu nhất và stack frame đầu tiên có nghĩa.
3. **Thành phần nào quan sát hoặc bọc lỗi?** MessagePublishingErrorHandler, poller, adapter listener, transaction interceptor hay gateway có thể làm lỗi cuối biểu hiện ở một lớp khác.

### Ví dụ: cùng một thông báo bọc nhưng hai nguyên nhân

~~~text
MessagingException: Failed to handle message
  caused by IllegalArgumentException: unsupported order status
  at OrderStatusTransformer...

→ Vấn đề logic/hợp đồng payload trong flow.
~~~

~~~text
MessagingException: Failed to handle message
  caused by ResourceAccessException
    caused by SocketTimeoutException: Read timed out
  at HTTP outbound gateway...

→ Vấn đề gọi dịch vụ ngoài, cần xem deadline và kết quả chưa xác định.
~~~

**Tên MessagingException chỉ nói lỗi đi qua Spring Messaging.** Phải đọc cause chain, bean endpoint, channel, stage và kết quả ngoại vi trước khi phân loại.

## 4. Các exception liên quan: nhìn cho đúng

Spring Messaging/Integration sử dụng nhiều exception ở các lớp khác nhau. Một số ví dụ:

| Exception / biểu hiện | Nó thường cho biết | Điều chưa thể kết luận |
| --- | --- | --- |
| **MessagingException** | Lỗi đang được biểu diễn trong ngữ cảnh messaging, có thể giữ failedMessage | Không có nghĩa root cause là runtime |
| **MessageDeliveryException** | Có vấn đề khi gửi/dispatch message | Có thể là thiếu subscriber, channel timeout hoặc handler downstream; phải xem cause |
| **MessageHandlingException** | Có lỗi khi một handler xử lý message | Handler có thể chính là outbound adapter gọi HTTP/DB |
| **MessageTransformationException** | Có vấn đề ở transformer | Gốc có thể là data contract hoặc service được transformer gọi |
| **MessageConversionException** | Conversion payload/header thất bại | Cần xem converter, content type, raw data và điểm xuất hiện |
| **MessageRejectedException** | Message bị handler/filter/router từ chối theo cơ chế cụ thể | Không tự có nghĩa phải retry |
| **TaskRejectedException/RejectedExecutionException** | Executor không nhận task | Không nhất thiết do bên ngoài chậm; cần xem pool/queue và tải |
| **TransactionException** hoặc rollback | Transaction/commit có lỗi | Resource DB có thể lỗi; check transaction manager và commit timeline |
| **IOException/SocketTimeoutException/SSLException** | Lỗi I/O/protocol ở tầng thấp | Không chắc remote side effect đã thất bại |

**Không chỉ grep tên class.** Một loại exception có thể được bọc thêm nhiều tầng, và phiên bản Spring Integration/adapter khác nhau có thể sử dụng lớp exception khác. Các ví dụ trên minh họa cách phân tích, **không phải bảng ánh xạ tuyệt đối** cho mọi connector.

### Đọc failedMessage và cause chain

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;

final class FailureInspector {

    static void inspect(Throwable failure) {
        Throwable cursor = failure;
        int depth = 0;

        while (cursor != null && depth < 20) {
            System.out.printf(
                    "cause[%d]=%s: %s%n",
                    depth,
                    cursor.getClass().getSimpleName(),
                    cursor.getMessage());

            if (cursor instanceof MessagingException messaging) {
                Message<?> failed = messaging.getFailedMessage();
                if (failed != null) {
                    System.out.println("failed message id="
                            + failed.getHeaders().getId());
                    System.out.println("correlation="
                            + failed.getHeaders().get("correlationId"));
                }
            }

            cursor = cursor.getCause();
            depth++;
        }
    }
}
~~~

Đây là utility minh họa, không nên in toàn bộ payload hoặc exception detail chứa secrets trong production. **failedMessage có thể null**, nhất là lỗi xảy ra trước khi adapter xây dựng Message. Ở case khác, failedMessage có thể là **message trung gian** của một transformer, không phải message source ban đầu.

**Duy trì context khi bọc exception:** Nếu handler muốn thêm thông tin nghiệp vụ, nên giữ nguyên cause và gắn business correlation vào log/diagnostic, thay vì tạo một IllegalStateException mới không có cause và làm mất đường truy vết.

## 5. Lỗi inbound adapter: trước và sau khi tạo message

Một inbound adapter chuyển sự kiện bên ngoài thành Spring Message. Tùy adapter, quá trình có thể gồm mở connection, nhận raw record, deserialize, map header, filter, tạo Message rồi send vào channel.

~~~text
Kafka/JMS/AMQP/File/HTTP source
  → connect/authenticate
  → poll/listen/read raw data
  → decode / convert / map headers
  → create Spring Message
  → send to input channel
~~~

### Nhóm lỗi trước khi có Spring Message

- Không kết nối được broker/remote host, DNS/TLS/authentication lỗi.
- File path không tồn tại, quyền truy cập thiếu, remote directory không đọc được.
- Lỗi đọc/deserialize raw bytes **trước khi framework tạo message**.
- Adapter container không start do config/bootstrap thất bại.

Trong nhóm này, **không được yêu cầu failedMessage luôn có mặt**. Cần dùng **source record metadata, remote filename, topic/partition/offset, request ID hoặc adapter-specific diagnostics** để truy ra sự kiện bị lỗi, tùy mức hỗ trợ của từng adapter.

### Nhóm lỗi sau khi có Spring Message

- Input channel không có subscriber.
- Transformer đầu tiên ném exception.
- Handler downstream không nhận type payload.
- ExecutorChannel từ chối task, QueueChannel đầy hoặc consumer bị stop.

Về **vị trí phát hiện**, log vẫn có thể xuất hiện ở inbound adapter vì adapter chính là bên gọi send(). Nhưng nguyên nhân có thể nằm ở **runtime flow phía sau**, không phải cấu hình kết nối của adapter.

### Ví dụ điển hình: poller file không thấy dữ liệu

Nếu FileReadingMessageSource không trả message, chưa vội kết luận “file adapter lỗi”:

1. Endpoint có **isRunning=true** không? Scheduler đang trigger poller không?
2. Có poll nhưng **receive() trả null** do thư mục rỗng hoặc filter đã nhận file trước đó?
3. File có tên/phần mở rộng phù hợp filter và file watcher không?
4. File có bị khóa hoặc thiếu permission khi đọc/di chuyển không?
5. Nếu restart, metadata/checkpoint của filter có khiến file bị bỏ qua không?
6. Input channel có thực sự nhận được Message sau khi source đọc file không?

Phân loại có thể là **lifecycle runtime**, **chính sách filter/metadata**, **file permissions**, hoặc **downstream dispatch**. Chỉ nhìn “không thấy file được xử lý” không đủ.

## 6. Lỗi outbound adapter: command đã chạy hay chưa?

Outbound adapter/gateway gửi message ra hệ thống ngoài. Ví dụ HTTP outbound gateway:

~~~mermaid
sequenceDiagram
    participant H as Spring Integration handler
    participant A as HTTP outbound gateway
    participant R as Remote API
    H->>A: Send PaymentCommand
    A->>R: POST /charge
    R-->>A: Response / timeout / connection reset
    A-->>H: Result hoặc exception
~~~

Tách ba tình huống:

1. **Request chưa tới remote:** DNS, connect timeout, TLS handshake hoặc config URI sai; đôi khi có thể retry an toàn sau xác minh hợp đồng.
2. **Remote trả phản hồi lỗi rõ ràng:** 400 validation, 401 auth, 429 throttling, 5xx; cần phân loại theo hợp đồng và chính sách retry.
3. **Remote đã thực hiện side effect nhưng response bị mất:** Read timeout/connection reset **không chứng minh tác dụng chưa xảy ra**. Cần idempotency key và query/reconciliation.

### Tại sao đây là lỗi adapter dù handler bắt MessagingException?

Vì lỗi gốc nằm ở **đường HTTP/protocol hoặc hợp đồng response**. Spring Integration có thể bọc nó thành MessageHandlingException để gắn failedMessage. Việc nhìn thấy MessageHandlingException trong errorChannel không chuyển nguyên nhân thành “lỗi dispatcher”.

### Lỗi data contract ở ranh giới adapter

Ví dụ outbound HTTP gửi JSON theo DTO phiên bản cũ, còn remote yêu cầu trường mới:

~~~text
Spring Message<OrderCommand>
  → JSON converter
  → POST /orders
  ← HTTP 422: missing currency
~~~

Lỗi là **hợp đồng giao tiếp**, không nên retry vô hạn. Kiểm tra converter, content type, schema version, headers và response payload đã được sanitize. Nếu lỗi nằm ở transformer Java nội bộ tạo DTO sai trước adapter, vẫn nên ghi rõ cả **điểm gốc** và **điểm phát hiện**.

### Với outbound one-way adapter

Một outbound adapter có thể **không trả reply message**. Vì vậy test không nên xem “không nhận reply” là lỗi. Thay vào đó kiểm chứng việc gửi thành công theo adapter contract (ack callback, external broker event, mock HTTP server, DB state), và đường exception/recovery khi thất bại.

## 7. Lỗi runtime của channel và dispatcher

**MessageChannel** là ranh giới quan trọng trong Spring Integration:

- **DirectChannel** gọi handler đồng bộ trong thread gửi; exception thường truyền về sender nếu không được xử lý khác đi.
- **ExecutorChannel** dispatch tới worker thread; send có thể trả trước khi handler chạy xong, transaction/thread context không tự truyền.
- **QueueChannel** giữ message để consumer poll; state còn hay mất khi restart phụ thuộc store/transaction.
- **PublishSubscribeChannel** có thể phát cho nhiều subscriber theo cấu hình, với semantics lỗi tùy dispatcher/executor.

### Không có subscriber

~~~text
Source → DirectChannel("ordersInput") → (không có subscriber)

send() có thể ném MessageDeliveryException.
~~~

Đây là lỗi **wiring/runtime dispatcher**, không liên quan remote broker nếu source đã xây dựng Spring Message thành công. Hướng xử lý:

1. Kiểm tra bean channel thật sự có tên **ordersInput**.
2. Kiểm tra endpoint/consumer được đăng ký và subscribe đúng channel.
3. Kiểm tra lifecycle endpoint, application context, profile và conditional bean configuration.
4. Kiểm tra có thay DirectChannel thành channel khác khi refactor hoặc test không.

### ExecutorChannel bị bão hòa

~~~text
Producer send() → ExecutorChannel
  → ThreadPoolTaskExecutor
  → queue đầy / không còn worker
  → TaskRejectedException hoặc lỗi tương đương
~~~

Đây là lỗi **năng lực điều phối runtime**. Hướng xử lý là kiểm tra queue capacity, active workers, rejected tasks, thời gian handler, backpressure và retry; không chỉ tăng timeout HTTP bên ngoài.

**Một lỗi adapter có thể gây ra lỗi runtime thứ cấp:** Nếu outbound HTTP chậm 30 giây, worker bị giữ lâu, queue executor đầy, rồi inbound send bắt đầu thất bại. Root cause là downstream latency; triệu chứng trực tiếp ở input channel là task rejection. Báo cáo sự cố phải ghi **cả chuỗi nguyên nhân**.

### Lỗi router/filter

Một router không có mapping cho key có thể fail, drop hoặc định tuyến default tùy cấu hình. Một filter có thể chủ ý discard message. **Không nhận output** không đủ kết luận có exception; cần xem **discard channel, routing rules, endpoint metrics** và trạng thái message.

## 8. errorChannel: lỗi xuất hiện ở đâu phụ thuộc thread boundary

Spring Integration có khái niệm **ErrorMessage** để truyền Throwable qua message flow. Tuy nhiên **không phải mọi lỗi đều tự động trở thành ErrorMessage**. Đường lỗi phụ thuộc cách endpoint được gọi, channel, adapter và cấu hình error handling.

~~~mermaid
flowchart TD
    S["Producer / Adapter"] --> C{"Channel"}
    C -- "DirectChannel" --> D["Handler chạy trên sender thread"]
    C -- "ExecutorChannel" --> E["Worker thread"]
    C -- "QueueChannel" --> P["Polling consumer thread"]
    D -- "Exception không được bắt" --> CALL["Exception có thể quay về sender"]
    E -- "Nếu có ErrorMessage publisher phù hợp" --> ERR["errorChannel"]
    P -- "Nếu poller error handling publish" --> ERR
    ERR --> REC["Error flow: log / retry / DLQ / alert"]
~~~

### DirectChannel — lỗi đồng bộ có thể quay về người gửi

~~~text
test/send thread
   input.send(message)
     → DirectChannel
        → handler throws
   input.send(...) throws
~~~

Ở đây test có thể dùng **assertThrows** trên send. Nếu một inbound adapter gọi send trong cùng thread, lỗi downstream có thể truyền về adapter rồi được adapter container xử lý theo cơ chế ack/rollback riêng.

### ExecutorChannel — sender và handler ở thread khác

~~~text
producer thread: send() → accepted/enqueued → return
worker thread:   handle() → exception
~~~

Một exception sau handoff **không tự quay lại** thread gửi. Cần xem **error publisher/errorChannel của worker**, executor task lifecycle và policy recovery. Chỉ vì send() trả true không thể khẳng định business operation đã thành công.

### Poller — lỗi có thể xuất hiện ở poll task

~~~text
TaskScheduler
  → poller
      → source.receive()
      → handler
      → exception
  → configured error handling / logging / retry
~~~

Polling consumer có thể có error handling mà application cấu hình để publish ErrorMessage; cần kiểm tra error channel của endpoint/poller, transaction advice và scheduler. **Lỗi đọc nguồn trước khi tạo Message** có thể không mang failedMessage.

### ErrorMessage chứa gì?

**ErrorMessage** là một Spring Message có payload kiểu Throwable. Nó có thể giữ **originalMessage** nếu code/framework tạo nó cung cấp. Throwable có thể là MessagingException với **failedMessage**.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

final class ErrorMessageInspector {

    static void inspect(ErrorMessage error) {
        Throwable failure = error.getPayload();

        Message<?> original = error.getOriginalMessage();
        Message<?> failed = null;
        if (failure instanceof MessagingException messaging) {
            failed = messaging.getFailedMessage();
        }

        Message<?> related = failed != null ? failed : original;
        String correlation = related != null
                ? String.valueOf(related.getHeaders().get("correlationId"))
                : "UNKNOWN";

        System.out.println("errorType="
                + failure.getClass().getSimpleName());
        System.out.println("correlationId=" + correlation);
        FailureInspector.inspect(failure);
    }
}
~~~

Đoạn code dùng cùng **FailureInspector** ở phần trước và chỉ để minh họa cách lấy nguồn correlation. Trong ứng dụng thật cần:

- Gắn **eventId/operationId, flow, endpoint, transport context** khi còn sẵn, không dựa một mình vào correlationId.
- Tránh in raw payload, access token, password, payment info hoặc nội dung exception nhạy cảm.
- Chấp nhận **originalMessage/failedMessage null**, nhất là source failure xảy ra trước message creation.
- Dùng log có cấu trúc và MDC/tracing phù hợp; với thread boundary, MDC không tự được chuyển trừ khi có cơ chế context propagation.

**Không nhầm errorChannel với retry:** ErrorMessage được gửi đi chưa chắc khiến message gốc được broker giao lại. Nếu error flow log rồi hoàn tất bình thường, kết quả ack/commit còn tùy adapter, container và transaction boundary.

## 9. Transaction và acknowledgement làm sai lệch cảm nhận lỗi

Khi broker consumer, DB transaction và outbound API cùng xuất hiện trong flow, có nhiều mốc kết thúc khác nhau:

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Integration consumer
    participant D as Business DB
    participant H as Outbound HTTP API
    B->>C: Deliver eventId=EV-42
    C->>D: Update business state
    D-->>C: Transaction commit
    C->>H: POST with operationId=EV-42
    H-->>C: Read timeout
    Note over C: API có thể đã xử lý thành công
    C-->>B: Ack/nack theo adapter configuration
~~~

Một lỗi HTTP xuất hiện sau DB commit **không tự rollback** DB. Một lỗi DB rollback sau khi HTTP đã có side effect cũng **không thu hồi HTTP effect**. Vì vậy câu hỏi “adapter hay runtime?” cần kèm “**tài nguyên nào đã commit?**”.

### Bảng các nhầm lẫn thường gặp

| Hiện tượng | Kết luận vội thường sai | Điều cần xác minh |
| --- | --- | --- |
| Handler ném exception | Broker chắc chắn sẽ redeliver | Adapter ack mode, error handler, transaction rollback và container |
| DB save() trả thành công | DB đã commit | Transaction manager, commit, rollback-only, propagation |
| HTTP read timeout | Remote chưa thực hiện side effect | Remote idempotency/operation status, request ID và reconciliation |
| Message được enqueue | Business handler đã xử lý | Consumer state, queue persistence, worker execution |
| ErrorMessage được log | Error đã được recovery thành công | DLQ/outbox/retry state đã commit hay chưa |
| App restart và có duplicate | Spring Integration tự phát hai event | Source redelivery, producer retry, outbox replay, business idempotency |

### DirectChannel so với ExecutorChannel

Với DirectChannel, handler thường chạy trong **cùng thread** với sender và có thể tham gia transaction active ở đó nếu các resource/advice tương thích. Qua ExecutorChannel, code chạy trên thread khác; **transaction của sender không mặc định đi cùng task**.

Nếu poller mở transaction, gửi message vào ExecutorChannel rồi commit sau khi task được chấp nhận, một lỗi trong worker xảy ra **sau đó** có thể không rollback việc nhận message ở nguồn. Đó là **thiết kế transaction boundary/runtime**, dù log lỗi cụ thể xuất hiện trong outbound adapter ở worker.

### At-least-once và duplicate sau crash

Một consumer crash **sau khi side effect đã commit nhưng trước khi broker nhận ack** thường có thể được giao lại theo semantics at-least-once. Đây không nhất thiết là bug của broker hay adapter.

Giải pháp là **idempotency bền vững**:

- **Inbox/unique constraint** gắn eventId với thay đổi business DB trong cùng transaction.
- **Outbox** cho event outbound bắt buộc phát sau commit.
- **Idempotency key** ở provider HTTP/payment, cộng với đối soát khi outcome không rõ.
- **Correlation/tracing** xuyên retry để phân biệt các technical attempts của cùng operation.

Không dùng mỗi **Spring MessageHeaders.ID** hoặc tên ErrorMessage làm khóa chống lặp qua restart: adapter có thể tạo Message mới khi redeliver.

## 10. Retry đúng lớp, không retry tất cả lỗi

**Retry chỉ có ích nếu nguyên nhân có khả năng biến mất khi thử lại.** Phân loại nguyên nhân trước:

| Loại lỗi | Ví dụ | Chiến lược có thể chọn |
| --- | --- | --- |
| **Runtime configuration/wiring** | Không có subscriber, sai channel ID, không đăng ký endpoint | Sửa cấu hình/deploy; retry nóng không giúp |
| **Runtime saturation** | Executor queue đầy, lock contention | Backpressure, delayed retry có budget, điều chỉnh capacity |
| **Data contract/permanent** | JSON không hợp lệ, required field thiếu, route key sai | Quarantine/DLQ; sửa producer/schema |
| **Adapter auth/config** | 401/403, expired certificate, sai broker credentials | Sửa credentials/config; retry liên tục không có ích |
| **Transient network** | 503, connection reset, broker tạm gián đoạn | Retry có giới hạn, exponential backoff + jitter |
| **429/rate limit** | Downstream throttle | Respect Retry-After nếu có, giảm concurrency |
| **Unknown side effect outcome** | HTTP timeout sau POST charge | Idempotency key + query/reconciliation trước replay không an toàn |
| **Storage contention/transaction** | Deadlock/serialization conflict | Retry transaction có giới hạn và giữ nguyên business key |
| **Missing correlation/group part** | Aggregator thiếu event bắt buộc | Chờ theo SLA/timeout/recovery; retry message hiện tại không tạo được phần bị thiếu |

### Retry nhiều tầng gây bão

~~~text
Broker redelivery: 4 deliveries
Handler RetryAdvice: 3 attempts mỗi delivery
HTTP client retry: 2 attempts mỗi handler attempt

Tối đa 4 × 3 × 2 = 24 external call attempts
cho cùng một business operation.
~~~

Một lỗi adapter ở remote có thể làm runtime tăng CPU/thread/queue và phát sinh lỗi thứ cấp. Cần chỉ định **retry owner**, giới hạn số lần thử tổng, timeout đầu-cuối, backoff, recovery cuối và idempotency.

### Phân loại exception và root cause

Không nên chỉ viết “nếu instanceOf MessagingException thì retry”:

~~~java
static boolean isPotentiallyTransient(Throwable failure) {
    Throwable cause = failure;
    while (cause != null) {
        if (cause instanceof java.net.SocketTimeoutException) {
            // Chỉ là tín hiệu transient; side effect outcome có thể UNKNOWN.
            return true;
        }
        cause = cause.getCause();
    }
    return false;
}
~~~

Đoạn code **không phải retry policy hoàn chỉnh**. Một SocketTimeoutException sau thao tác có side effect vẫn cần **idempotency/reconciliation**; 401, validation error hoặc lỗi dữ liệu không nên được xếp retryable chỉ vì chúng bị bọc trong MessagingException.

## 11. MessageStore, correlation và trạng thái runtime

Không phải mọi lỗi “không có output” đều là exception. Với **aggregator/resequencer**, message có thể được lưu đúng nhưng chưa đủ điều kiện release:

~~~text
groupId = order:O-42:run-7
present steps = PAYMENT, INVENTORY
missing step = ADDRESS
group status = incomplete
~~~

**Đây là trạng thái chờ, không phải lỗi adapter** nếu flow được thiết kế phải chờ ba phần. Nhưng sau SLA, nó có thể trở thành timeout cần recovery.

### Kiểm tra MessageGroupStore metadata

~~~java
import org.springframework.integration.store.MessageGroupMetadata;
import org.springframework.integration.store.MessageGroupStore;

class GroupDiagnostics {
    private final MessageGroupStore store;

    GroupDiagnostics(MessageGroupStore store) {
        this.store = store;
    }

    void log(String groupId) {
        MessageGroupMetadata metadata = store.getGroupMetadata(groupId);
        if (metadata == null) {
            System.out.println("group missing: " + groupId);
            return;
        }

        System.out.printf(
                "group=%s size=%d complete=%s created=%d modified=%d%n",
                groupId,
                metadata.size(),
                metadata.isComplete(),
                metadata.getTimestamp(),
                metadata.getLastModified());
    }
}
~~~

**Lưu ý:** Metadata chỉ là một snapshot. Một thread hoặc instance khác có thể cập nhật group ngay sau khi đọc. **size()** cho biết số message trong group, không chứng minh đó là số **event nghiệp vụ duy nhất**, vì redelivery có thể tạo Spring Message ID khác.

### Lỗi persistent store

- **SimpleMessageStore** trong RAM mất dữ liệu qua JVM restart; đó là giới hạn thiết kế, không phải file/broker adapter “ăn mất message”.
- **Jdbc/Redis/Mongo MessageStore** có thể giữ state qua restart, nhưng cần serializer/schema/transaction và xử lý lỗi kết nối.
- Group đã complete có thể giữ metadata để nhận diện late message. Dọn metadata quá sớm có thể làm late delivery mở group mới.
- Hai instance cùng nhóm cần lock/concurrency control phù hợp; nếu release hai lần do race, cần kiểm tra cả **LockRegistry, MessageStore và idempotency downstream**.
- Một payload từ phiên bản cũ deserialize không được sau deploy là lỗi **persistence compatibility/runtime**, có thể liên quan schema dữ liệu nguồn.

### Phân biệt lỗi correlation với nguồn upstream thiếu dữ liệu

| Triệu chứng | Kiểm tra | Phân loại |
| --- | --- | --- |
| Không thấy group O-42 | groupId được dựng đúng chưa? | Correlation mapping/runtime hoặc producer contract |
| Group có hai phần, chờ phần thứ ba | Upstream có phát sự kiện đó không? | Có thể thiếu nguồn/adapter hoặc dữ liệu hợp lệ chưa tới |
| Group size đủ nhưng không release | ReleaseStrategy yêu cầu loại phần/sequence nào? | Logic runtime hoặc duplicate data |
| Group hoàn tất nhưng late message bị discard | Retention/expire policy được chọn thế nào? | Có thể đúng hợp đồng, không phải exception |
| Group bị tạo lại sau restart | Store persistent/metadata còn không? | Persistence/runtime recovery |

Không retry vô hạn một message PAYMENT chỉ vì ADDRESS chưa tới. Một retry của PAYMENT **không tạo ra ADDRESS**, nhưng có thể tạo duplicate và tăng backlog.

## 12. Quy trình điều tra: tìm ranh giới cuối còn hoạt động đúng

Một runbook hiệu quả đi **từ nguồn tới đích**, kết hợp dấu thời gian và correlation:

~~~mermaid
flowchart TD
    S["Có source event thật?"] -->|Không| A["Kiểm tra adapter connection, filter, source metadata"]
    S -->|Có| M["Đã tạo Spring Message?"]
    M -->|Không| B["Kiểm tra decode, conversion, source exception"]
    M -->|Có| C["Đã vào đúng channel?"]
    C -->|Không| D["Kiểm tra send, bean ID, dispatcher, endpoint state"]
    C -->|Có| H["Handler có bắt đầu?"]
    H -->|Không| E["Kiểm tra executor, poller, subscription, queue"]
    H -->|Có| O["Outbound effect/call có bắt đầu?"]
    O -->|Không| F["Kiểm tra route, filter, validator, transformer"]
    O -->|Có| R["Remote đã phản hồi/commit gì?"]
    R -->|Không rõ| U["UNKNOWN_OUTCOME: reconcile, không retry mù"]
    R -->|Có| ACK["Kiểm tra output, commit, ack, recovery"]
~~~

### Bước 1 — Xác định phạm vi và thời điểm

Ghi **flow name, endpoint ID, instance, environment, thời điểm, loại message, nguồn/đích**. Sự cố xảy ra với mọi message hay chỉ một nhóm orderId/eventId? Chỉ trong một replica hay toàn cluster?

### Bước 2 — Kiểm tra lifecycle và đường vào

Các endpoint có đang chạy không? Poller có tick? Inbound adapter đã kết nối và được cấp partition/queue? Có file hoặc raw record thật không? Check filter/checkpoint, không chỉ log của handler.

### Bước 3 — Xác nhận message qua ranh giới channel

Ghi dấu tại **input channel**, trước/sau transformer, trước outbound handler. Có thể dùng **WireTap**, logging channel interceptor hoặc metric theo endpoint; không nên tùy tiện thêm subscriber vào DirectChannel vì nó không tự broadcast và có thể thay đổi dispatch.

### Bước 4 — Xem điểm thất bại trong cause chain

Đọc **root cause**, failedMessage, originalMessage, bean ID, stack trace/endpoint name, trạng thái thread. Lỗi có xảy ra trước message creation, trong handler hay sau outbound call?

### Bước 5 — So khớp transaction và acknowledgement

Nguồn đã ack/commit offset? Business DB đã commit? Outbox event đã được publish? Remote service đã chấp nhận request? Nếu outcome chưa chắc chắn, đánh dấu **UNKNOWN** thay vì coi một timeout là thất bại chắc chắn.

### Bước 6 — Xác định recovery đã làm gì

Message được retry, redeliver, đưa vào DLQ, discard, lưu MessageStore hay bị error handler nuốt? Kiểm tra **điểm tăng retry attempts**; không chỉ tìm một log ERROR.

### Bước 7 — Tái hiện bằng test đúng tầng

Tạo một test thay đúng ranh giới gây lỗi: mock HTTP cho outbound failure, mock MessageSource cho source failure, channel/endpoint thật cho dispatch error, persistent store và broker thật cho crash/ack/restart.

**Kết quả mong muốn của runbook:** Một báo cáo ngắn ghi **triệu chứng**, **first failing stage**, **root cause**, **lỗi lan truyền**, **ảnh hưởng dữ liệu**, **recovery hiện tại** và **thao tác khắc phục**, cùng bằng chứng kiểm chứng.

## 13. Java test: phân biệt runtime dispatch failure và adapter failure

Một test có ích phải **chủ động tạo lỗi ở đúng ranh giới**, không chỉ giả lập một exception chung tại handler.

### Case A — lỗi runtime do DirectChannel không có subscriber

Đây là trường hợp có thể tái hiện hoàn toàn trong JVM:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.support.MessageBuilder;

class RuntimeDispatchFailureTest {

    @Test
    void failsToDeliverWhenChannelHasNoSubscriber() {
        DirectChannel orphanChannel = new DirectChannel();

        MessageDeliveryException error =
                assertThrows(MessageDeliveryException.class,
                        () -> orphanChannel.send(
                                MessageBuilder.withPayload("O-42")
                                        .setHeader("correlationId", "flow-42")
                                        .build()));

        assertNotNull(error.getFailedMessage());
        assertEquals("flow-42",
                error.getFailedMessage().getHeaders()
                        .get("correlationId"));
    }
}
~~~

**Phạm vi chứng minh:** Lỗi xảy ra ở **channel dispatcher**, không cần Kafka, HTTP hoặc DB. Nếu một adapter gọi send vào orphanChannel và log tương tự, nguyên nhân đầu tiên vẫn là thiếu subscriber/wiring runtime.

### Case B — lỗi adapter giả lập bằng một external port

Để phân biệt với lỗi dispatch, ta chủ động mô phỏng remote client từ chối kết nối:

~~~java
import java.net.SocketTimeoutException;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;

interface PaymentPort {
    void capture(String paymentId) throws SocketTimeoutException;
}

class PaymentOutboundHandler {
    private final PaymentPort paymentPort;

    PaymentOutboundHandler(PaymentPort paymentPort) {
        this.paymentPort = paymentPort;
    }

    @ServiceActivator(inputChannel = "paymentCommands")
    public void handle(Message<String> command)
            throws SocketTimeoutException {
        paymentPort.capture(command.getPayload());
    }
}
~~~

Với fake port:

~~~java
PaymentPort unavailable = paymentId -> {
    throw new SocketTimeoutException("Remote read timed out");
};

PaymentOutboundHandler handler = new PaymentOutboundHandler(unavailable);

SocketTimeoutException error = assertThrows(
        SocketTimeoutException.class,
        () -> handler.handle(
                MessageBuilder.withPayload("PAY-42").build()));
~~~

**Đây là unit test của port/handler**, chưa đi qua một Spring Integration endpoint thật. Nó kiểm tra **nguyên nhân gốc từ external boundary**, không kết luận framework sẽ giữ nguyên SocketTimeoutException khi lời gọi chạy qua ServiceActivator. Trong integration test thật, exception có thể được bọc trong MessagingException và liên quan errorChannel.

### Case C — cùng lỗi adapter nhưng quan sát ở Spring Integration endpoint

Để chứng minh wrapper/error propagation:

1. Tạo **paymentCommands DirectChannel**.
2. Đăng ký **PaymentOutboundHandler** như một @ServiceActivator bean.
3. Gửi Message có paymentId, eventId và correlationId.
4. Assert send() ném exception theo hợp đồng endpoint; duyệt cause chain để tìm **SocketTimeoutException**.
5. Kiểm tra **failedMessage hoặc originalMessage nếu framework giữ**.
6. Không gọi lại payment API tự động trong test khi outcome có thể đã xảy ra; dùng fake client và idempotency key.

Khi thay DirectChannel bằng ExecutorChannel, **đường quan sát thay đổi**: caller có thể thấy send() thành công, còn exception ở worker cần được ghi nhận bằng error flow/spy/latch. Không dùng chung một assertion assertThrows(send()) cho cả hai topology.

## 14. Test error flow của poller, executor và inbound adapter

Test một handler đồng bộ không bao phủ hết hành vi Spring Integration Runtime. Khi flow có **poller, executor hoặc broker adapter**, test cần tạo lỗi tại thời điểm đúng và quan sát đường lỗi thực.

### Test ExecutorChannel

Mô hình:

~~~text
JUnit thread
   → input.send()
   → ExecutorChannel accepts task
   → returns

Worker thread
   → handler throws
   → error handling / task completion
~~~

Một chiến lược test:

1. Dùng **ThreadPoolTaskExecutor** hoặc executor nhỏ được kiểm soát.
2. Dùng **CountDownLatch** để biết worker đã bắt đầu và khi nào được phép tiếp tục.
3. Inject exception có mã loại lỗi ổn định tại handler.
4. Gắn error flow test có QueueChannel hoặc mock handler **tại vị trí framework thực sự publish ErrorMessage**.
5. Assert **output success không được phát**, error được quan sát, failed/original message đúng khi có, và không có task mồ côi.
6. Dùng timeout hữu hạn, giải phóng latch và shutdown executor trong finally/test teardown.

**Đừng chỉ kiểm tra send() == true** vì đó có thể là kết quả **handoff**, không phải business success. Đồng thời **không mặc định** mọi task exception của ExecutorChannel sẽ xuất hiện ở một global errorChannel nếu ứng dụng chưa cấu hình phù hợp.

### Test poller thất bại trước khi Message được tạo

Một **MessageSource** giả lập có thể ném exception trong receive(), trước khi trả một Message:

~~~java
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.Message;

class FailingMessageSource implements MessageSource<String> {
    @Override
    public Message<String> receive() {
        throw new IllegalStateException(
                "Cannot read remote file metadata");
    }
}
~~~

Để test ở mức IntegrationFlow:

- Đăng ký source trên một polling endpoint có **ID tường minh**.
- Ngăn endpoint auto-start trước khi test sẵn sàng; dùng **@SpringIntegrationTest(noAutoStartup=...)** khi phù hợp.
- Trigger một lượt poll có kiểm soát hoặc cấu hình scheduler/test trigger.
- Quan sát error handling của polling endpoint; trong case này **không giả định có failedMessage** vì receive() chưa trả Message.
- Kiểm tra endpoint có tiếp tục chạy/được recovery hay bị stop theo policy.

### Test inbound adapter thật

Một test với Kafka, AMQP, JMS, SFTP hoặc JDBC adapter nên dùng môi trường integration test phù hợp nếu cần chứng minh:

- Authentication, topic/queue/directory/table mapping.
- Serialization và content-type/headers ở ranh giới ingress.
- Consumer/container lifecycle và assigned partitions.
- Ack/nack/offset/redelivery khi handler thất bại.
- Transaction behavior sau restart hoặc network disconnect.

Mock MessageSource có thể chứng minh flow logic và đường lỗi nguồn, nhưng **không chứng minh broker protocol semantics**. Với adapter ngoài JVM, cần test transport thật và fault injection nếu đây là yêu cầu reliability.

## 15. Observability: lấy bằng chứng thay vì đoán

Không thể phân biệt runtime và adapter nếu chỉ có một log “failed to handle message”. Nên instrument các **ranh giới** thay vì ghi toàn bộ payload tại mọi hop.

### Structured logs nên chứa gì?

~~~text
event=message_processing_failure
flow=orderImport
endpoint=paymentOutboundGateway
stage=OUTBOUND_ADAPTER
channel=paymentCommands
instance=payments-pod-2
messageId=3f9b...
eventId=EV-42
correlationId=checkout-O-42
attempt=2
exceptionType=MessageHandlingException
rootCauseType=SocketTimeoutException
externalSystem=payment-provider
outcome=UNKNOWN
~~~

Đây là **mẫu log ứng dụng tự thiết kế**, không phải format mặc định của Spring Integration. Không đưa access tokens, credentials, payment details hoặc toàn bộ payload vào logs. **eventId/correlationId** nên được kiểm soát về tính riêng tư; không nhất thiết đưa vào metric labels.

### Những metric giúp tìm tầng lỗi

| Metric / tín hiệu | Diễn giải |
| --- | --- |
| Inbound receive rate / poll count | Adapter có còn nhận/poll dữ liệu không? |
| Adapter connectivity and reconnect attempts | Nguồn/đích có bị ngắt kết nối hoặc lỗi xác thực? |
| Channel send failures / no subscriber | Message không tới được handler vì wiring/dispatch? |
| Executor active workers, queue depth, rejected tasks | Runtime có saturate không? |
| Handler duration P95/P99 | Xử lý nội bộ/DB/HTTP có bị chậm? |
| Outbound HTTP attempt latency, status class | Remote có tăng 5xx/429/timeout? |
| MessageStore read/write failures | State persistence có bị lỗi? |
| Retry attempts, recovery/DLQ outcomes | Lỗi có được giải quyết hay đang loop? |
| ErrorMessage delivered by endpoint | Đường error đang nhận những lỗi nào? |
| Incomplete/expired MessageGroups | Correlation/partial flow có chờ quá hạn? |
| Queue waiting age | Backpressure đang tích tụ ở đâu? |

**Metric names tùy phiên bản và cách instrument.** Spring Integration có tích hợp Micrometer/Observation ở những cấu hình phù hợp, nhưng không nên giả định mọi backend có sẵn cùng tên metric. Kiểm tra registry/Actuator/Prometheus của ứng dụng thật.

**Không cộng chồng đơn vị khác nhau:** Một inbound delivery có thể gây ba handler attempts và sáu HTTP calls do retry. Counter tại HTTP adapter không thể được gọi là “số đơn hàng”. Các metrics nên ghi rõ **delivery, attempt, message output hoặc business operation**.

### Logs, traces và metrics phối hợp ra sao?

~~~mermaid
flowchart TD
    M["Metric alert: HTTP latency P99 tăng"] --> T["Trace: outbound gateway span chậm"]
    T --> L["Logs theo correlationId/eventId"]
    L --> X["Root cause: remote 503 hoặc timeout"]
    X --> V["Kiểm tra ack/commit + idempotency"]
    V --> A["Fix adapter/remote policy hoặc runtime capacity"]
~~~

**Correlation ID không tự đi qua mọi ranh giới.** Một transformer có thể làm mất header, transport adapter có thể map không hết headers, hoặc task trên worker thread không nhận MDC. Test header propagation và tracing context riêng, không chỉ dùng một global log field.

## 16. Các tình huống điều tra thực tế

### Tình huống A — inbound Kafka vẫn nhận, nhưng channel báo không deliver được

**Triệu chứng:** Listener log cho thấy nhận record. Lỗi gần nhất là MessageDeliveryException.

**Chuỗi kiểm tra:**

1. Adapter đã decode record và gọi send chưa? Nếu có, đây không còn là lỗi kết nối Kafka.
2. Channel ID có đúng không? Có subscriber không? Endpoint có được tạo bởi profile/conditional bean mong đợi?
3. Endpoint có bị stop bởi Control Bus hoặc flow lifecycle không?
4. Error có ở sender thread và ảnh hưởng ack/offset thế nào? Kiểm tra container/adapter cụ thể.

**Chẩn đoán có khả năng:** **Runtime wiring/lifecycle** làm dispatch thất bại, với biểu hiện tại inbound Kafka adapter.

**Cách sửa:** Khôi phục subscription/endpoint bean và kiểm tra ack/redelivery; đừng đổi broker credentials nếu log cho thấy consumer vẫn đọc record thành công.

### Tình huống B — HTTP remote chậm, rồi executor bị reject task

**Triệu chứng:** Ban đầu outbound gateway timeout. Sau vài phút, input channel bị task rejection.

**Chuỗi nhân quả:**

~~~text
Remote API latency tăng
    → worker giữ thread lâu
    → executor queue tích tụ
    → pool đạt giới hạn
    → ExecutorChannel bắt đầu từ chối task
~~~

**Root cause ban đầu:** Adapter/downstream latency. **Lỗi thứ cấp:** Saturation tại runtime executor. Nếu chỉ tăng thread pool vô hạn, áp lực lên remote có thể tệ hơn.

**Cách xử lý:** Timeouts hợp lý, backpressure, rate limit, circuit breaker, retry hữu hạn, queue capacity, và hợp đồng idempotency; quan sát throughput, worker occupancy và remote status.

### Tình huống C — file inbound adapter “không đọc được file”

**Triệu chứng:** File nằm trên disk nhưng không có output.

Các trường hợp khác nhau:

- Poller **isRunning=false**: lỗi lifecycle/runtime.
- Poller chạy, source receive() trả null do **AcceptOnceFileListFilter/metadata** đã đánh dấu file: cần điều tra filter/checkpoint, không phải lỗi đọc hệ điều hành.
- Source receive() ném **AccessDeniedException**: lỗi quyền filesystem ở adapter boundary.
- File đã thành Message nhưng transformer parse sai: lỗi business data contract/transformer.
- Message vào QueueChannel nhưng consumer bị stop: runtime backlog.

**Giải pháp:** Chèn quan sát tại mỗi ranh giới, thay vì xóa metadata store hoặc restart liên tục khi chưa hiểu tác động tới duplicate.

### Tình huống D — Kafka redelivery gây double charge

**Triệu chứng:** Có hai payment transactions cho cùng paymentId sau pod restart.

**Không đủ kết luận:** “Kafka adapter có bug gửi hai lần”.

Timeline cần xác minh:

~~~text
Delivery #1
  → HTTP charge thực hiện thành công ở provider
  → App crash trước khi consumer ack/commit offset
Delivery #2
  → message được nhận lại
  → handler không sử dụng stable idempotency key
  → HTTP charge lần hai
~~~

**Phân loại:** Redelivery thuộc semantics nguồn; lỗi nghiệp vụ là thiếu idempotency/reconciliation tại outbound side effect, còn crash window/ack boundary là một yếu tố runtime quan trọng.

**Cách sửa:** Dùng provider idempotency key, durable inbox/outbox khi thích hợp, đối soát UNKNOWN_OUTCOME, kiểm thử crash **sau effect trước ack**.

### Tình huống E — aggregator chưa phát kết quả dù mọi service “đều đã gửi”

**Triệu chứng:** Ba service đều log đã publish event nhưng aggregator không ra output.

Kiểm tra:

1. **Publish accepted** có đồng nghĩa broker đã lưu và consumer đã nhận chưa?
2. CorrelationStrategy có tạo **cùng groupId** cho cả ba message không?
3. Message đi qua adapter/transformer có bị mất **correlationId/sequence headers**?
4. ReleaseStrategy cần **ba loại bước duy nhất** hay chỉ size=3? Có duplicate?
5. MessageGroupStore có đầy đủ state chưa; timeout/reaper có chạy không?

**Phân loại:** Có thể là adapter delivery, header mapping, logic release runtime hoặc nguồn thật sự thiếu một phần. Chỉ số publish ở producer không đủ để chứng minh “đã đến aggregator”.

### Tình huống F — lỗi chỉ xảy ra sau redeploy

**Triệu chứng:** Trước deploy hệ thống bình thường, sau deploy persistent QueueChannel/MessageGroupStore không đọc lại được message.

**Điều tra:** Serializer, payload class/package thay đổi, schema, custom headers, connection/backend version, migration và đọc message từ code cũ. Nếu source broker vẫn healthy nhưng MessageStore deserialization fail, lỗi nằm ở **persistence compatibility/runtime**, không phải broker.

**Cách xử lý:** Schema evolution, migration/quarantine có kiểm soát, kiểm thử restart với dữ liệu phiên bản trước. Không xóa kho message thật chỉ để “hết lỗi” nếu chưa kiểm tra khả năng phục hồi nghiệp vụ.

## 17. Bài thực hành: tìm nguyên nhân lỗi trong một flow có nhiều tầng

**Đề bài:** Một dịch vụ Order Import dùng Spring Integration:

~~~text
Kafka inbound adapter
  → ordersInput (DirectChannel)
  → validateAndMapOrder (Transformer)
  → validatedOrders (ExecutorChannel)
  → orderHandler
  → business DB
  → HTTP outbound gateway
  → orderConfirmed
  ↘ error flow / DLQ
~~~

Trong production xuất hiện:

- Một số đơn không có output, dù Kafka consumer vẫn đọc được record.
- Một số handler có MessageHandlingException bọc SocketTimeoutException.
- Executor rejection tăng sau khi HTTP P95 từ 300 ms lên 8 giây.
- Sau restart, một số eventId xuất hiện hai lần trong log.

### Nhiệm vụ 1 — Chọn đúng vị trí đo

Thêm quan sát **có kiểm soát** tại:

1. **Inbound adapter received:** record source ID, partition/offset khi có, eventId.
2. **ordersInput:** kiểm tra message đã được dispatch.
3. **Transformer output:** kiểm tra payload type, business key và correlation headers.
4. **Executor queue/handler start:** đo queue wait và số rejected tasks.
5. **DB commit:** nguồn sự thật của business update.
6. **Outbound HTTP:** request/response status, latency, external operation ID.
7. **Error flow:** exception chain, failed/original message, recovery outcome.
8. **Broker ack/offset:** message đã được xác nhận hay còn khả năng redelivery.

Không ghi full payload chứa dữ liệu khách hàng. Dùng WireTap hoặc channel interceptor ở test profile cho những ranh giới cần quan sát, tránh vô tình đổi DirectChannel thành broadcast.

### Nhiệm vụ 2 — Phân loại ba lỗi khác nhau

| Quan sát | Nhóm nguyên nhân chính | Bằng chứng cần bổ sung |
| --- | --- | --- |
| Record đã nhận, Transformer chưa chạy, channel thiếu subscriber | Runtime wiring/lifecycle | DirectChannel subscriptions, endpoint IDs, conditional beans |
| Transformer chạy, handler gọi HTTP và remote timeout | Adapter/external boundary | Remote request ID, timeout config, root cause, side effect outcome |
| HTTP chậm, queue đầy, executor reject | Runtime saturation do external latency kích hoạt | Thread dump, active/queued/rejected metrics, rate/retry load |

Điều quan trọng là **mối quan hệ nhân quả**, không đặt một nhãn chung “adapter broken” cho cả ba.

### Nhiệm vụ 3 — Kiểm tra dữ liệu sau lỗi

- DB đã commit order update chưa? Nếu có, handler retry có tạo update lặp không?
- Outbound HTTP đã thực hiện side effect chưa? Read timeout cần đối soát, không mặc định failure.
- Kafka offset đã commit trước hay sau khi handler hoàn tất? Điều này phụ thuộc adapter/container và thread boundary.
- DLQ có ghi thành công message cùng eventId chưa, hay chỉ log dự định gửi?
- Nếu retry nhiều tầng, tổng external attempts có vượt budget không?

### Nhiệm vụ 4 — Chạy bộ test tái hiện

| Test | Cách kích hoạt | Assertion |
| --- | --- | --- |
| Không có subscriber | DirectChannel không có consumer | MessageDeliveryException, failedMessage/correlation nếu có |
| Transformer lỗi payload | Đưa input không đúng schema | Exception xuất hiện ở transformer; outbound không được gọi |
| Remote HTTP 503 | Fake HTTP server trả 503 | Classify transient/contract, retry có giới hạn |
| Remote timeout sau side effect | Fake provider lưu operation rồi cắt response | Outcome UNKNOWN, cùng idempotencyKey khi đối soát/retry |
| Executor saturated | Latch giữ worker, lấp queue | Rejection quan sát được; không ack thành công giả |
| Poller receive() ném lỗi | Mock MessageSource throws | Error handling ghi được source failure, không yêu cầu failedMessage |
| Async handler throws | ExecutorChannel + fake handler throws | Sender có thể hoàn tất send; error flow phù hợp được xác minh |
| Error flow nuốt lỗi | Error handler log rồi return | Kiểm tra ack/commit thực tế, không suy ra sẽ redeliver |
| Duplicate delivery | Hai Message khác ID cùng eventId | Business effect idempotent, correlation ổn định |
| Restart sau commit trước ack | Broker + DB thật, fault injection | Redelivery có thể có; business effect chỉ một lần |
| MessageStore serializer lỗi | Lưu message phiên bản cũ, nâng code | Đọc lại hoặc có migration/quarantine an toàn |
| Correlation thiếu một phần | Chỉ gửi 2/3 loại message | Không release thành công trước điều kiện; timeout/recovery rõ ràng |

**Lưu ý mức độ kiểm thử:** Test bằng DirectChannel và fake HTTP trong JVM không chứng minh broker ack, DB transaction hay crash recovery. Những yêu cầu này cần integration/end-to-end test với adapter và kho lưu trữ phù hợp.

## 18. Checklist khi trực sự cố

### Trước khi sửa cấu hình

- Có timestamp, endpoint ID, channel ID, instance và **correlation/eventId** để truy vết?
- Biết lỗi đầu tiên xảy ra **trước hay sau khi tạo Spring Message**?
- Có bằng chứng source adapter **đã thật sự nhận dữ liệu** hay chỉ producer báo đã gửi?
- Có kiểm tra **endpoint.isRunning**, poller schedule, subscriptions, executor capacity?
- Có đọc **root cause** và stack trace, không chỉ phần đầu của MessagingException?
- Nếu error là ErrorMessage, đã kiểm tra originalMessage/failedMessage **nếu có**?
- Có phân biệt HTTP/DB remote error với exception wrapper của handler?
- Với connection reset/timeout, có xác minh **unknown outcome** trước khi replay side effect?
- Retry và recovery có ở những tầng nào; một operation có thể bị gọi bao nhiêu lần?
- MessageStore/MetadataStore có đủ bền vững và tương thích serializer sau restart?
- Transaction commit, broker ack/offset và outbound publish diễn ra theo thứ tự nào?
- Có xác minh rate/metrics của queue, executor, poller và external system thay vì suy đoán từ một log?

### Trước khi tuyên bố đã khắc phục

- Có test tái hiện được failure cũ và PASS sau thay đổi không?
- Retry permanent error đã được giới hạn hoặc chuyển quarantine?
- Không có message bị “mất” do error handler catch rồi ack thành công giả?
- Không có double business side effect khi redelivery hoặc restart?
- Error path còn correlationId/eventId và có observable recovery outcome?
- Metric cảnh báo cho root cause và lỗi thứ cấp đã trở lại mức mong đợi?
- Endpoint/adapter có tiếp tục chạy và throughput đã phục hồi ổn định?
- Nếu phải replay thủ công, có kế hoạch idempotency và đối soát kết quả?

## 19. Câu hỏi tự kiểm tra

**1. Log hiển thị MessageHandlingException tại HTTP outbound gateway. Có thể kết luận lỗi nằm trong handler logic Java không?**

**Không.** Handler có thể là adapter gọi external service. Cần xem cause chain và trạng thái remote. Một SocketTimeoutException do external HTTP call có thể được bọc thành MessageHandlingException.

**2. Kafka adapter báo lỗi khi send vào input channel, nhưng broker connection vẫn bình thường. Ưu tiên kiểm tra gì?**

**Wiring/subscriber/endpoint lifecycle, channel dispatch và downstream handler**, sau khi xác nhận adapter đã tạo Message và bắt đầu send. Lỗi hiển thị tại adapter không nhất thiết do Kafka.

**3. Một Exception từ handler sau ExecutorChannel có nhất định ném về producer thread không?**

**Không.** Worker chạy thread khác. Phải xác minh error handling, task completion, transaction và nguồn ack riêng.

**4. Vì sao polling source lỗi trước khi tạo Message thường thiếu failedMessage?**

**Vì** chưa có Spring Message để tham chiếu. Cần source metadata, adapter diagnostics và root cause, không được suy luận mất correlation là do transformer.

**5. HTTP read timeout có cho phép gửi lại lệnh thu tiền với operationId mới không?**

**Không nên.** Outcome có thể đã thành công. Dùng **idempotency key ổn định** được provider hỗ trợ, tra cứu/reconciliation và retry theo hợp đồng.

**6. Aggregator có group size=2 khi đang chờ 3 bước. Đó là lỗi runtime hay adapter?**

**Chưa thể kết luận.** Nhóm có thể đang chờ hợp lệ; cần kiểm tra SLA, message nguồn thứ ba, correlation mapping, release condition và timeout policy.

**7. Sau khi xử lý được lỗi kết nối HTTP, executor vẫn đầy. Có phải root cause chưa hết không?**

**Có thể** backlog/retry storm đã tích lũy. Cần giảm tải có kiểm soát, quan sát queue wait, active workers, retry budget và capacity; sửa connection không tự làm biến mất mọi lỗi thứ cấp.

## Kết luận

**Phân biệt lỗi runtime với lỗi adapter** không có nghĩa chỉ dựa vào một exception class để chọn nhãn. Trong Spring Integration, **runtime** đảm nhiệm dispatch, endpoint lifecycle, poller, executor, transaction, retry, message store và correlation; **adapter** nối những cơ chế đó với nguồn/đích ngoài qua các protocol. Lỗi có thể bắt đầu ở một tầng nhưng được phát hiện hoặc bọc ở tầng khác.

Hãy chẩn đoán theo **giai đoạn**, từ **source → adapter → Spring Message → channel → handler → outbound adapter → commit/ack → recovery**, đồng thời giữ **cause chain**, **failed/original message nếu có**, **correlationId/eventId**, metrics theo ranh giới và trạng thái của từng resource. Sau đó mới chọn cách sửa: cấu hình/lifecycle, backpressure, data contract, retry hữu hạn, DLQ/quarantine, idempotency hoặc đối soát external outcome.

Một hệ thống dễ debug không chỉ có nhiều log; nó có **bằng chứng đúng tại từng ranh giới**, test tái hiện sự cố và chính sách phục hồi rõ ràng để lỗi adapter không kéo sập runtime, còn lỗi runtime không bị nhầm thành vấn đề kết nối.

## Tài liệu tham khảo

- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Testing](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Framework API — MessagingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html)
- [Spring Framework API — ErrorMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html)
- [Spring Framework API — MessageDeliveryException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageDeliveryException.html)
