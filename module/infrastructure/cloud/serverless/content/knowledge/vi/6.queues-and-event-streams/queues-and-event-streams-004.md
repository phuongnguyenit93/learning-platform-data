# Acknowledgment, visibility timeout và thời gian giữ thông điệp

Trong kiến trúc serverless, queue hoặc event stream thường nối producer với một hay nhiều consumer. Producer gửi message rồi có thể tiếp tục công việc; consumer nhận message vào thời điểm phù hợp và xử lý độc lập. Cách tách rời này giúp hấp thụ tải tăng đột biến, giới hạn tốc độ xử lý và phục hồi khi một thành phần tạm thời không sẵn sàng.

Tuy nhiên, gửi message thành công không có nghĩa message đã được xử lý xong. Hệ thống cần biết khi nào consumer đã hoàn tất, khi nào nên giao lại message, và message được lưu trong bao lâu trước khi hết hạn. Ba khái niệm cần hiểu rõ là **acknowledgment (ack)**, **visibility timeout hoặc acknowledgment deadline**, và **message retention**.

Ack xác nhận consumer đã xử lý message theo quy tắc của broker. Visibility timeout hoặc deadline xác định khoảng thời gian một message đang được consumer giữ xử lý trước khi có thể được giao lại. Retention xác định thời gian broker lưu message hoặc record. Cấu hình sai có thể gây mất message, xử lý trùng, retry quá sớm, backlog kéo dài hoặc message hết hạn trước khi được xử lý.

## 1. Vòng đời message trong queue

Một message thường trải qua các trạng thái khái niệm sau:

~~~mermaid
stateDiagram-v2
    [*] --> Available: Producer publish
    Available --> InFlight: Consumer nhận
    InFlight --> Completed: Ack / Complete
    InFlight --> Available: Nack / Release / Visibility hết hạn
    InFlight --> InFlight: Gia hạn visibility hoặc lock
    Available --> Expired: Hết retention
    InFlight --> Expired: Hết retention theo chính sách broker
    Available --> DeadLetter: Vượt giới hạn delivery
    InFlight --> DeadLetter: Lỗi không thể phục hồi / redrive policy
    Completed --> [*]
    Expired --> [*]
    DeadLetter --> [*]
~~~

Đây là mô hình tổng quát. Mỗi broker có tên trạng thái, cách xác nhận và quy tắc lưu trữ riêng. Ví dụ, một số queue xóa message sau khi ack; một event stream có thể giữ record đến hết retention ngay cả khi consumer đã commit offset.

Các bước cơ bản:

1. Producer publish message và broker xác nhận đã tiếp nhận.
2. Message ở trạng thái có thể được giao cho consumer.
3. Consumer nhận message; broker đánh dấu message đang được xử lý hoặc ghi nhận vị trí đọc.
4. Consumer thực hiện nghiệp vụ và lưu kết quả bền vững.
5. Consumer gửi ack, complete hoặc commit offset theo mô hình broker.
6. Nếu consumer thất bại hoặc không xác nhận đúng hạn, broker có thể giao lại hoặc tiếp tục cung cấp record theo vị trí đã commit.
7. Nếu message không được xử lý trong thời gian lưu trữ hoặc vượt chính sách delivery, broker có thể loại bỏ hoặc chuyển sang dead-letter queue.

Cần phân biệt **publish acknowledgment** với **consumer acknowledgment**. Publish acknowledgment xác nhận broker đã nhận message từ producer. Consumer acknowledgment xác nhận một bước xử lý ở phía nhận. Hai sự kiện này xảy ra ở hai thời điểm khác nhau và có ý nghĩa khác nhau.

## 2. Acknowledgment: xác nhận xử lý thành công

Acknowledgment là tín hiệu consumer gửi cho broker để báo rằng message đã được xử lý đến mức có thể xem là hoàn tất theo contract. Tùy dịch vụ, thao tác có thể tên là ack, delete, complete hoặc commit offset.

Thông thường, consumer chỉ nên ack sau khi kết quả nghiệp vụ đã được ghi bền vững. Nếu ack trước khi ghi dữ liệu, function có thể bị dừng sau ack nhưng trước khi commit nghiệp vụ; broker tin message đã hoàn tất và không giao lại, dẫn tới mất công việc.

Ví dụ trình tự không an toàn:

~~~text
Receive message
    |
    v
Ack message
    |
    v
Write database
    |
    X  Function bị dừng
~~~

Message đã được broker xem là hoàn tất nhưng database chưa có kết quả.

Trình tự an toàn hơn:

~~~text
Receive message
    |
    v
Validate + process
    |
    v
Commit durable result
    |
    v
Ack message
~~~

Nếu function bị dừng sau khi commit database nhưng trước khi ack, message có thể được giao lại. Vì vậy, thứ tự này giảm nguy cơ mất công việc nhưng vẫn có thể tạo xử lý lặp. Consumer cần idempotency để một message được giao nhiều lần vẫn không tạo side effect trùng.

### Ack, nack và các lựa chọn xử lý

Các hệ thống queue thường cung cấp một số hành động tương đương:

| Hành động | Ý nghĩa | Kết quả thường gặp |
|---|---|---|
| Ack / Complete | Xác nhận xử lý xong | Broker loại message khỏi hàng đợi chờ xử lý hoặc ghi nhận đã đọc |
| Nack / Reject | Từ chối message | Có thể trả message về queue, dead-letter hoặc loại bỏ tùy cấu hình |
| Release / Abandon | Nhả message chưa xử lý xong | Message có thể được giao lại ngay hoặc sau delay |
| Extend / Renew | Gia hạn quyền giữ message | Consumer có thêm thời gian trước khi message có thể được giao lại |
| Không ack | Không gửi xác nhận | Broker xử lý khi visibility/lock/deadline hết hạn |

Không nên dùng nack cho mọi exception. Một lỗi dữ liệu vĩnh viễn như schema không hợp lệ có thể lặp lại mãi nếu chỉ trả message về queue. Ngược lại, một lỗi tạm thời như database timeout có thể cần retry sau một khoảng backoff. Hãy phân loại lỗi và cấu hình redrive hoặc dead-letter phù hợp.

### Ack không tạo ra exactly-once side effect

Ack thường không nằm trong cùng transaction với database hoặc API bên ngoài. Consumer có thể ghi database thành công nhưng ack thất bại; broker sau đó giao lại message. Hoặc consumer ack thành công nhưng kết quả ghi nghiệp vụ chưa thực sự bền vững do ứng dụng xử lý transaction sai.

Vì vậy, không nên suy luận rằng broker có ack thì nghiệp vụ tự động được xử lý đúng một lần. Hãy thiết kế consumer theo hướng chịu được duplicate delivery và dùng khóa idempotency hoặc deduplication ở nơi lưu trạng thái nghiệp vụ.

## 3. Visibility timeout và acknowledgment deadline

Với queue kiểu pull, khi consumer nhận message, broker thường tạm thời ẩn message khỏi các consumer khác. Khoảng thời gian đó được gọi là **visibility timeout**, **acknowledgment deadline** hoặc thời gian khóa (lock duration), tùy nền tảng.

Nếu consumer ack trước khi thời hạn kết thúc, message được xem là hoàn tất. Nếu consumer không ack và không gia hạn, message có thể trở lại trạng thái có thể giao để consumer khác xử lý.

Ví dụ:

~~~text
t = 0s       Consumer A nhận message
             Message chuyển sang InFlight

t = 10s      Consumer A vẫn đang xử lý
             Consumer khác chưa nhìn thấy message

t = 30s      Visibility timeout kết thúc
             Không có ack hoặc gia hạn

t = 31s      Message có thể được giao cho Consumer B
             Consumer A vẫn có thể còn chạy nếu chưa bị dừng
~~~

Điểm cuối rất quan trọng: visibility timeout không nhất thiết hủy invocation cũ. Nếu consumer A vẫn chạy sau khi message được giao lại cho B, hai consumer có thể cùng thực hiện side effect. Idempotency và conditional write vẫn cần thiết ngay cả khi đã cấu hình visibility timeout.

### Chọn visibility timeout

Visibility timeout cần đủ dài để consumer có cơ hội hoàn thành công việc bình thường, gồm cả thời gian xử lý và những dao động hợp lý của dependency. Nếu quá ngắn, message bị giao lại khi consumer cũ vẫn đang chạy, làm tăng concurrency và duplicate processing. Nếu quá dài, message bị lỗi phải chờ lâu mới có cơ hội retry.

Cân nhắc các yếu tố:

- Thời gian xử lý p95/p99, không chỉ thời gian trung bình.
- Thời gian tối đa của invocation hoặc batch handler.
- Thời gian gọi database, API đối tác và lưu kết quả.
- Thời gian retry nội bộ trong một invocation.
- Thời gian shutdown hoặc timeout của function.
- Chính sách retry và thời gian chờ trước lần giao tiếp theo.

Không có một con số phù hợp cho mọi queue. Ví dụ, nếu một consumer thường xử lý trong vài giây nhưng đôi lúc cần vài chục giây để gọi dịch vụ đối tác, visibility timeout phải được chọn theo phân bố thời gian và giới hạn của nền tảng. Với tác vụ có thời lượng biến động lớn, gia hạn visibility có thể phù hợp hơn đặt một timeout rất dài cho mọi message.

### Gia hạn visibility hoặc lock

Nếu xử lý có thể vượt quá thời hạn ban đầu, consumer có thể gia hạn thời gian giữ message trước khi nó hết hạn. Một số nền tảng hỗ trợ thay đổi visibility timeout, gia hạn ack deadline hoặc renew lock.

Cần thiết kế việc gia hạn như một cơ chế có kiểm soát:

1. Xác định thời gian xử lý tối đa mà nghiệp vụ cho phép.
2. Gia hạn trước khi deadline hiện tại hết hạn, có đủ khoảng đệm cho network latency.
3. Dừng gia hạn khi xử lý hoàn tất hoặc đã quyết định từ bỏ message.
4. Giới hạn tổng thời gian giữ message theo policy và maximum execution time.
5. Nếu gia hạn thất bại, giả định message có thể được giao cho consumer khác; bảo vệ side effect bằng idempotency.
6. Theo dõi số lần gia hạn và message giữ lâu bất thường.

Không gia hạn vô hạn để che giấu một consumer bị treo. Nếu công việc vượt giới hạn hợp lý, nên chia nhỏ thành các bước, lưu checkpoint hoặc chuyển sang workflow orchestration.

## 4. Message retention: broker giữ message trong bao lâu?

**Message retention** là khoảng thời gian broker giữ message hoặc record trước khi hết hạn theo chính sách lưu trữ. Retention khác visibility timeout:

- Visibility timeout kiểm soát thời gian một message đang được giữ xử lý trước khi có thể được giao lại.
- Retention kiểm soát thời gian message tồn tại trong hệ thống lưu trữ của broker.

Một message có thể không hiển thị với consumer trong visibility timeout nhưng vẫn đang được lưu. Khi visibility hết hạn, message có thể được giao lại nếu retention chưa hết. Nếu retention hết trước khi consumer xử lý, message có thể bị xóa hoặc không còn khả dụng, tùy semantics của dịch vụ.

Ví dụ:

~~~text
Publish
  |
  +---- Message được broker lưu ------------------------------+
  |                                                            |
  |  Consumer nhận                                             |
  |      |                                                     |
  |      +-- Visibility timeout: message tạm ẩn                |
  |      |       |                                             |
  |      |       +-- Hết hạn: có thể giao lại                  |
  |      |                                                     |
  |      +-- Ack: hoàn tất theo mô hình queue                  |
  |                                                            |
  +---- Retention hết hạn: broker hết thời gian lưu message --+
~~~

### Chọn retention period

Retention phải phù hợp với khả năng phục hồi và thời gian gián đoạn mà hệ thống cần chịu được. Hãy xem xét:

- Consumer có thể ngừng hoạt động bao lâu mà doanh nghiệp vẫn chấp nhận xử lý bù?
- Có thời gian bảo trì hoặc triển khai kéo dài không?
- Backlog tối đa dự kiến khi traffic tăng đột biến là bao nhiêu?
- Tốc độ xử lý sau khi phục hồi có đủ nhanh để bắt kịp producer không?
- Message chứa dữ liệu nhạy cảm hoặc dữ liệu có yêu cầu xóa theo thời hạn nào?
- Có cần giữ event để replay, audit hoặc rebuild projection không?
- Dung lượng và chi phí lưu trữ tăng thế nào khi retention dài hơn?

Retention quá ngắn có thể làm message hết hạn trong lúc consumer đang outage hoặc backlog lớn. Retention quá dài làm tăng chi phí, kéo dài thời gian dữ liệu nhạy cảm tồn tại và có thể khiến consumer đọc lại những event đã lỗi thời nếu quy trình replay không kiểm soát.

Không nên chọn retention chỉ dựa trên thời gian xử lý bình thường. Hãy tính cả thời gian outage, thời gian phát hiện, khắc phục và drain backlog. Nếu cần lưu trữ dài hạn cho audit, cân nhắc archive riêng thay vì dùng queue như kho lưu trữ lâu dài.

### Retention của queue và event stream khác nhau

Queue và event stream có thể dùng từ "retention" nhưng semantics khác nhau:

- **Queue:** message thường được loại khỏi tập message chờ sau khi consumer ack thành công; retention giới hạn thời gian message chưa hoàn tất có thể được giữ. Một số dịch vụ có retention riêng cho dead-letter queue.
- **Event stream/log:** record thường được giữ theo thời gian hoặc dung lượng kể cả khi consumer đã đọc. Consumer ghi offset để nhớ vị trí xử lý; commit offset không xóa record khỏi log.
- **Compacted log:** một số stream có thể giữ giá trị mới nhất theo key và loại bỏ record cũ theo chính sách compaction, khác với việc xóa ngay khi consumer xác nhận.

Vì vậy, đừng áp dụng trực tiếp cách hiểu visibility timeout của queue lên Kafka hoặc một log stream phân vùng. Hãy dùng khái niệm tương ứng của broker.

## 5. So sánh semantics ở một số nền tảng

Tên API và quy tắc cụ thể khác nhau giữa nhà cung cấp. Bảng dưới đây giúp ánh xạ khái niệm, không thay thế tài liệu cấu hình của dịch vụ đang dùng.

| Hệ thống | Xác nhận xử lý | Cơ chế giao lại / giữ message | Retention |
|---|---|---|---|
| Amazon SQS | Consumer xóa message bằng receipt handle sau khi xử lý | Visibility timeout; có thể thay đổi hoặc gia hạn visibility | Message được giữ đến retention cấu hình nếu chưa bị xóa |
| Google Cloud Pub/Sub | Consumer ack message | Ack deadline; có thể modify deadline hoặc để hết hạn | Message retention theo subscription/topic policy |
| Azure Service Bus | Consumer complete message | Message lock; abandon hoặc lock hết hạn để giao lại, có thể renew lock | TTL của message và policy của entity |
| Apache Kafka | Consumer commit offset cho partition | Record được đọc lại nếu offset chưa commit hoặc được reset; không có per-message visibility timeout kiểu queue | Retention theo thời gian/dung lượng; record không bị xóa chỉ vì consumer commit |

Một số lưu ý:

- SQS standard queue có thể giao message nhiều lần và không đảm bảo thứ tự tuyệt đối. FIFO queue có semantics thứ tự và deduplication riêng nhưng vẫn cần hiểu phạm vi deduplication.
- Pub/Sub có ack deadline và delivery attempt; cấu hình exactly-once delivery nếu có cũng cần hiểu phạm vi, giới hạn và khác biệt với side effect trong database.
- Azure Service Bus có lock token và các hành động complete, abandon, defer, dead-letter; lock duration và renew có giới hạn.
- Kafka quản lý tiến độ consumer bằng offset theo partition. Commit offset trước khi xử lý xong có thể làm bỏ qua record sau khi crash; commit sau khi xử lý có thể gây xử lý lặp. Việc phối hợp offset với side effect bên ngoài cần chiến lược riêng.

Trước khi triển khai, xác nhận rõ broker đang dùng, loại queue/subscription/stream, chế độ delivery, giới hạn thời gian và retention thực tế.

## 6. Quan hệ giữa ack, visibility, retry và dead-letter queue

Ack và visibility quyết định một message có tiếp tục được giao lại hay không. Retry policy quyết định hệ thống chờ bao lâu, thử lại bao nhiêu lần và khi nào dừng. Dead-letter queue (DLQ) là nơi cách ly message không thể xử lý sau các lần thử theo policy.

Một luồng retry thường gặp:

~~~mermaid
flowchart TD
    A["Message available"] --> B["Consumer nhận"]
    B --> C["Xử lý nghiệp vụ"]
    C --> D{"Thành công?"}
    D -->|"Có"| E["Commit kết quả bền vững"]
    E --> F["Ack / Complete"]
    D -->|"Lỗi tạm thời"| G["Nack / Release hoặc để timeout"]
    G --> H["Backoff / Delay"]
    H --> A
    D -->|"Lỗi vĩnh viễn"| I["Reject / Dead-letter"]
    D -->|"Vượt max delivery"| I
    I --> J["DLQ: điều tra và xử lý có kiểm soát"]
~~~

Phân loại lỗi trước khi retry:

| Loại lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Lỗi tạm thời | Timeout database, throttling, dependency 503 | Retry có giới hạn với backoff và jitter |
| Lỗi dữ liệu | JSON sai, thiếu field bắt buộc, schema không hỗ trợ | Dead-letter hoặc quarantine để điều tra |
| Lỗi nghiệp vụ | Đơn đã bị hủy, trạng thái không cho phép thao tác | Ghi nhận kết quả từ chối theo nghiệp vụ; không retry vô hạn |
| Lỗi cấu hình/quyền | Credential sai, thiếu IAM permission | Cảnh báo và dừng retry nhanh nếu lỗi cần sửa cấu hình |
| Lỗi không xác định | Crash, process bị kill, mất kết nối | Broker có thể giao lại; consumer phải idempotent |

DLQ cần có quy trình vận hành:

- Theo dõi số lượng và tuổi message trong DLQ.
- Lưu thông tin lỗi và delivery metadata cần thiết, tránh log payload nhạy cảm.
- Xác định nguyên nhân trước khi redrive.
- Sửa code, schema hoặc dữ liệu trước khi phát lại.
- Giữ event ID hoặc business key khi replay để idempotency tiếp tục hoạt động.
- Giới hạn tốc độ redrive để không tạo burst làm quá tải consumer hoặc database.
- Xác định ai có quyền đọc, sửa và phát lại message.

DLQ không tự động giải quyết lỗi. Nếu không có cảnh báo và quy trình xử lý, nó chỉ là nơi message bị bỏ quên.

## 7. Idempotency và duplicate delivery

At-least-once delivery nghĩa là broker có thể giao một message nhiều hơn một lần. Điều này có thể xảy ra khi consumer xử lý xong nhưng ack bị mất, invocation bị dừng, visibility hết hạn hoặc consumer mất quyền sở hữu partition trước khi commit offset.

Consumer nên có một định danh ổn định cho sự kiện, ví dụ eventId do producer tạo. Trước khi thực hiện side effect, consumer kiểm tra event đã được áp dụng hay chưa.

Một mô hình bảng deduplication:

| Field | Vai trò |
|---|---|
| consumerName | Phân biệt tiến độ của các consumer logic |
| eventId | Định danh duy nhất của event |
| status | PROCESSING hoặc COMPLETED |
| processedAt | Thời điểm hoàn tất |
| resultRef | Tham chiếu kết quả nếu cần |
| expiresAt | Thời điểm hết hạn bản ghi deduplication |

Khóa duy nhất có thể là (consumerName, eventId). Thao tác claim và ghi kết quả cần có transaction hoặc conditional write nguyên tử. Nếu hai invocation cùng nhận một event, chỉ một invocation được phép claim; invocation còn lại cần kiểm tra trạng thái và không thực hiện side effect lần nữa.

Khi database và side effect nằm ở hai hệ thống khác nhau, một transaction đơn lẻ không thể tự bảo đảm cả hai cùng hoàn tất. Ví dụ, consumer ghi database rồi gọi payment provider. Nếu function dừng giữa hai bước, trạng thái có thể không rõ. Hãy dùng idempotency key của provider nếu hỗ trợ, lưu trạng thái payment attempt và có quy trình đối soát. Với event phát sinh từ database transaction, transactional outbox giúp tránh khoảng trống giữa commit dữ liệu và publish event.

Thời gian lưu deduplication record cần đủ dài so với khoảng thời gian message có thể được giao lại hoặc replay. Nếu retention message là 7 ngày nhưng dedup record hết hạn sau 1 ngày, một message replay vào ngày thứ 3 có thể thực hiện side effect lần nữa. Với nghiệp vụ tài chính hoặc side effect không thể đảo ngược, có thể cần lưu business operation ID lâu hơn thời gian broker giữ message.

## 8. Batch processing và partial acknowledgment

Một số trigger đưa nhiều message vào cùng một invocation để giảm overhead. Khi xử lý batch, cần xác định semantics ack của từng message hay của cả batch.

Nếu consumer xử lý 10 message và message thứ 8 lỗi, có hai cách xử lý phổ biến:

- **Ack cả batch sau khi tất cả thành công:** nếu batch bị retry, các message 1–7 có thể bị xử lý lại.
- **Partial batch response:** xác nhận những message đã xử lý thành công và chỉ yêu cầu giao lại message lỗi, nếu broker và event source mapping hỗ trợ.

Ví dụ logic khái niệm:

~~~java
List<String> failedMessageIds = new ArrayList<>();

for (Message message : batch) {
    try {
        processor.processIdempotently(message);
    } catch (RetryableException ex) {
        failedMessageIds.add(message.id());
    } catch (PermanentMessageException ex) {
        deadLetterPublisher.publish(message, ex);
        // Chỉ đánh dấu hoàn tất sau khi việc cách ly đã bền vững.
    }
}

return BatchResult.withFailures(failedMessageIds);
~~~

Đây là pseudocode minh họa; định dạng batch response thực tế phụ thuộc adapter của nhà cung cấp. Với nền tảng yêu cầu throw exception để retry cả batch, consumer phải idempotent cho từng message. Với partial acknowledgment, hãy xác minh chính xác ID cần trả về và cách broker xử lý phần tử không được liệt kê.

Batch lớn có thể tăng throughput nhưng cũng làm tăng thời gian invocation, memory và phạm vi retry. Cấu hình batch size theo thời gian xử lý, payload, concurrency và giới hạn dependency. Không nên gom quá nhiều message nếu một message chậm có thể giữ cả batch lâu.

## 9. Thiết kế consumer Java cho serverless

Consumer Java nên tách adapter của broker khỏi logic nghiệp vụ. Adapter chuyển message và context thành kiểu nội bộ; application service kiểm tra schema, quyền và trạng thái; repository ghi kết quả; adapter ack theo contract của trigger.

Ví dụ cấu trúc khái niệm:

~~~java
public final class OrderEventHandler {
    private final OrderProcessor processor;

    public OrderEventHandler(OrderProcessor processor) {
        this.processor = processor;
    }

    public void handle(Message message, MessageContext context) {
        try {
            OrderEvent event = eventMapper.validateAndMap(message.body());

            // Hàm này phải idempotent và ghi kết quả bền vững.
            processor.process(event);

            // Adapter chỉ ack sau khi process hoàn tất.
            context.ack();
        } catch (RetryableException ex) {
            context.retryLater(ex);
        } catch (PermanentMessageException ex) {
            context.deadLetter(ex);
        }
    }
}
~~~

Các kiểu Message, MessageContext, OrderEvent và cách ack/retry/DLQ là abstraction, không phải API chuẩn chung của mọi Java serverless runtime. Một số nền tảng quản lý acknowledgment tự động qua kết quả invocation hoặc event source mapping; khi đó adapter phải tuân theo contract cụ thể và không tự gọi một hàm ack giả định.

Một số nguyên tắc triển khai:

- Parse và validate envelope trước khi chạy nghiệp vụ.
- Dùng event ID ổn định để deduplicate.
- Ghi kết quả nghiệp vụ bền vững trước khi xác nhận.
- Không nuốt exception nếu runtime dựa vào exception để retry.
- Phân biệt lỗi retryable và permanent.
- Đặt timeout của dependency nhỏ hơn thời gian còn lại của invocation.
- Giữ message body nhỏ; với payload lớn, lưu object và truyền reference đã được kiểm soát quyền.
- Không lưu trạng thái xử lý duy nhất trong static field.
- Log event ID, correlation ID và kết quả xử lý mà không log secret hoặc toàn bộ payload.

Nếu dùng framework có listener container, hãy hiểu ack mode: auto acknowledgment, manual acknowledgment, batch acknowledgment hoặc commit offset. Cấu hình sai có thể khiến framework ack trước khi transaction hoàn tất hoặc commit offset quá sớm.

## 10. Cấu hình timeout và retention theo tải thực tế

Visibility timeout, invocation timeout, dependency timeout và retention liên quan nhưng có mục đích khác nhau.

| Thông số | Câu hỏi cần trả lời |
|---|---|
| Function timeout | Một invocation được phép chạy tối đa bao lâu? |
| Visibility/lock/ack deadline | Broker chờ consumer xác nhận hoặc gia hạn trong bao lâu trước khi giao lại? |
| Dependency timeout | Một lời gọi database hoặc API ngoài được chờ tối đa bao lâu? |
| Retry delay/backoff | Khi lỗi tạm thời, consumer chờ bao lâu trước lần thử tiếp theo? |
| Max delivery/receive count | Message được thử tối đa bao nhiêu lần trước khi dead-letter? |
| Message retention | Broker giữ message chưa hoàn tất tối đa bao lâu? |
| DLQ retention | Message đã cách ly được giữ để điều tra hoặc replay trong bao lâu? |
| Deduplication retention | Hệ thống nhớ một event đã được áp dụng trong bao lâu? |

Một nguyên tắc cấu hình là visibility/lock phải đủ dài cho thời gian xử lý hợp lệ và phần đệm, hoặc được gia hạn đúng cách. Function timeout nên giới hạn thời gian invocation; dependency timeout phải nhỏ hơn thời gian còn lại để function có thể lưu trạng thái hoặc xử lý lỗi. Retention cần đủ dài để chịu outage và backlog dự kiến.

Ví dụ minh họa, giả sử p99 xử lý message là 18 giây, dependency timeout tổng cộng được giới hạn trong 8 giây và phần lưu kết quả/ack cần khoảng 2 giây. Nhóm có thể chọn visibility lớn hơn đáng kể thời gian xử lý thông thường, ví dụ 30–45 giây, rồi kiểm tra lại dưới tải và với invocation timeout thực tế. Đây chỉ là điểm khởi đầu cho thử nghiệm; không phải giá trị mặc định cho mọi nền tảng.

### Backlog và thời gian drain

Retention phải được so sánh với thời gian cần để xử lý backlog. Nếu producer gửi 100 message/giây trong khi consumer chỉ xử lý 80 message/giây, backlog tăng 20 message/giây. Khi producer dừng hoặc giảm tải, consumer cần năng lực dư để xử lý backlog trước khi message hết retention.

Có thể ước tính thời gian drain đơn giản:

\[
T_{drain} \approx \frac{N_{backlog}}{R_{consumer} - R_{producer}}
\]

Công thức chỉ có ý nghĩa khi tốc độ consumer lớn hơn producer trong giai đoạn drain và throughput tương đối ổn định. Nếu hai tốc độ bằng nhau hoặc consumer thấp hơn producer, backlog không giảm. Thực tế cần tính retry, batch, throttling, partition, dependency và phân bố thời gian xử lý.

Hãy theo dõi oldest message age hoặc lag, không chỉ queue depth. Một queue có ít message nhưng message cũ có thể báo hiệu consumer bị kẹt hoặc một partition không tiến triển.

## 11. Thứ tự message và xử lý song song

Visibility timeout và ack có thể ảnh hưởng thứ tự xử lý. Với queue cho phép song song, message sau có thể được xử lý trước message trước. Nếu nghiệp vụ yêu cầu thứ tự, cần chọn cơ chế ordering của broker, partition key hoặc message group phù hợp.

Ví dụ, các sự kiện cập nhật cùng một tài khoản có thể cần theo thứ tự theo account ID. Có thể dùng account ID làm partition key hoặc group key để broker định tuyến các message liên quan vào cùng luồng có thứ tự. Điều này thường giảm mức song song trong cùng một partition/group nhưng giúp giữ thứ tự.

Ngay cả khi broker bảo đảm thứ tự giao, xử lý song song hoặc retry có thể làm thứ tự hoàn tất khác thứ tự nhận. Consumer nên kiểm tra sequence/version của aggregate và từ chối event cũ nếu nó làm trạng thái quay ngược.

Với Kafka, thứ tự được bảo đảm trong một partition. Consumer group phân chia partition giữa consumer; khi rebalance, quyền sở hữu partition có thể thay đổi. Consumer cần xử lý commit offset cẩn thận và không để một worker cũ commit tiến độ sai sau khi mất quyền sở hữu.

## 12. Quan sát và cảnh báo vòng đời message

Cần quan sát toàn bộ vòng đời từ publish đến hoàn tất, không chỉ số invocation của function.

Các metric nên theo dõi:

- Số message được publish và số message được xử lý thành công.
- Ack rate, nack/release rate và số lần delivery.
- Approximate age của message cũ nhất hoặc consumer lag.
- Queue depth hoặc backlog theo partition.
- Visibility expiration, lock loss hoặc ack deadline extension.
- Retry count, max delivery reached và DLQ depth.
- Thời gian xử lý p50/p95/p99.
- Tỷ lệ duplicate bị idempotency chặn.
- Số message hết retention hoặc bị loại bỏ.
- Lỗi database, throttling, timeout và dependency error.
- Thời gian drain backlog sau một đợt outage.

Dùng event ID, correlation ID hoặc trace ID để nối log producer, broker, consumer và downstream service. Tránh ghi payload nhạy cảm vào log; có thể ghi schema version, event type, tenant reference đã được kiểm soát và kết quả xử lý.

Cảnh báo nên dựa trên hành vi có ý nghĩa:

- Oldest message age vượt ngưỡng SLA.
- DLQ xuất hiện message mới hoặc tăng nhanh.
- Ack rate giảm trong khi publish rate không đổi.
- Retry hoặc visibility expiration tăng bất thường.
- Consumer lag tăng liên tục.
- Message sắp hết retention trước khi được xử lý.
- Một partition hoặc message group không tiến triển.

## 13. Checklist thiết kế acknowledgment và retention

Trước khi đưa consumer vào production, hãy kiểm tra:

1. Broker đang dùng queue, subscription hay event stream? Semantics ack/offset cụ thể là gì?
2. Ack xảy ra sau khi kết quả nghiệp vụ đã bền vững chưa?
3. Nếu commit nghiệp vụ thành công nhưng ack thất bại, consumer có chịu được duplicate không?
4. Visibility timeout, lock duration hoặc ack deadline có đủ cho p95/p99 processing không?
5. Consumer có gia hạn thời gian giữ message khi cần không, và có giới hạn tổng thời gian không?
6. Function timeout và dependency timeout có phối hợp hợp lý không?
7. Retention có chịu được thời gian outage, backlog và drain không?
8. DLQ và retry policy có phân biệt lỗi tạm thời với lỗi vĩnh viễn không?
9. Deduplication record có được lưu lâu hơn cửa sổ retry/replay cần thiết không?
10. Batch acknowledgment có hỗ trợ partial failure không?
11. Thứ tự event có quan trọng theo entity hoặc partition key không?
12. Có metric và cảnh báo cho oldest message age, lag, retry, ack và DLQ không?
13. Quy trình redrive có kiểm tra nguyên nhân và giới hạn tốc độ không?
14. Payload, secret, retention và quyền truy cập có đáp ứng yêu cầu bảo vệ dữ liệu không?

## Kết luận

Acknowledgment cho broker biết consumer đã hoàn tất xử lý theo contract; visibility timeout hoặc lock deadline quyết định khi nào message chưa được xác nhận có thể được giao lại; retention quyết định broker giữ message hoặc record trong bao lâu. Ba thông số này phối hợp với retry policy, DLQ và timeout của function để quyết định khả năng phục hồi của luồng dữ liệu.

Trong Java serverless, hãy ghi kết quả nghiệp vụ bền vững trước khi ack, thiết kế idempotency để chịu duplicate delivery, gia hạn visibility khi công việc cần thêm thời gian và chọn retention đủ cho outage cùng backlog dự kiến. Khi hiểu đúng semantics của broker và theo dõi oldest message age, delivery count, lag, retry và DLQ, nhóm có thể vận hành consumer đáng tin cậy mà vẫn kiểm soát concurrency, độ trễ và chi phí.

