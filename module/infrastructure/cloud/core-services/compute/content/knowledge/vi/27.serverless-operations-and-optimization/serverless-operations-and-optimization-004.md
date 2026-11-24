# Dead-letter queue và phục hồi sự kiện xử lý thất bại

## Mục tiêu bài học

Trong kiến trúc event-driven serverless, một sự kiện thường được chuyển từ producer tới queue, event bus hoặc dịch vụ kích hoạt function. Function có thể thất bại vì dependency tạm thời không sẵn sàng, dữ liệu đầu vào sai, timeout, giới hạn concurrency hoặc lỗi trong code. Nếu chỉ retry vô hạn, một sự kiện lỗi có thể chiếm tài nguyên, làm backlog tăng và ảnh hưởng các sự kiện tốt. Nếu bỏ sự kiện ngay sau lần lỗi đầu tiên, hệ thống có thể mất công việc hợp lệ.

Dead-letter queue (DLQ) cung cấp nơi cách ly sự kiện đã vượt quá chính sách xử lý hoặc không thể tiếp tục theo luồng bình thường. DLQ giúp giữ lại dữ liệu để điều tra và phục hồi có kiểm soát. Nó không tự sửa lỗi và cũng không tự bảo đảm sự kiện sẽ được xử lý lại thành công.

Sau bài học này, bạn có thể:

- Mô tả luồng xử lý sự kiện trong serverless và các điểm có thể thất bại.
- Phân loại lỗi tạm thời, lỗi dữ liệu và lỗi cấu hình.
- Thiết kế retry, backoff, jitter, timeout và giới hạn số lần thử.
- Phân biệt DLQ, retry queue, failure destination và event archive.
- Cấu hình chính sách chuyển sự kiện lỗi sang DLQ.
- Thiết kế idempotency để xử lý sự kiện trùng an toàn.
- Điều tra poison message và phục hồi sự kiện bằng redrive.
- Theo dõi backlog, age, failure rate và chi phí vận hành.
- Xây dựng runbook và kiểm thử phục hồi mà không tạo thêm sự cố.

## 1. Luồng xử lý sự kiện trong serverless

Một ứng dụng serverless thường nhận sự kiện từ queue, event bus, object storage, database stream, scheduler hoặc một dịch vụ khác. Nền tảng gọi function trực tiếp hoặc cung cấp sự kiện cho function thông qua event source mapping/poller.

Luồng tổng quát:

1. Producer tạo sự kiện và gửi tới nguồn sự kiện.
2. Nguồn sự kiện lưu hoặc định tuyến sự kiện theo cơ chế của dịch vụ.
3. Function được gọi hoặc poller lấy một batch sự kiện.
4. Handler xác thực, xử lý nghiệp vụ và ghi kết quả.
5. Khi xử lý thành công, sự kiện được acknowledge, xóa khỏi queue hoặc offset được commit theo semantics của nguồn.
6. Khi xử lý thất bại, nền tảng retry, giữ lại, chuyển sang DLQ hoặc ghi vào failure destination tùy cấu hình.

~~~mermaid
flowchart LR
    P["Producer"] --> S["Queue / Event bus / Stream"]
    S --> F["Serverless function"]
    F --> D["Dependency / Database"]
    F -->|Success / ack| C["Complete event"]
    F -->|Failure| R["Retry policy"]
    R -->|Retry succeeds| C
    R -->|Attempts exhausted| Q["Dead-letter queue"]
    Q --> O["Observe and investigate"]
    O --> X["Repair and redrive"]
    X --> S
~~~

Mỗi dịch vụ có quy tắc delivery, retry và acknowledgment khác nhau. Một function được gọi bất đồng bộ trực tiếp có thể dùng retry policy của nền tảng; một function poll queue có thể dựa trên visibility timeout và receive count; consumer của stream có thể bị ảnh hưởng bởi offset và checkpoint. Không áp dụng một cấu hình DLQ chung cho mọi nguồn sự kiện.

## 2. Vì sao sự kiện xử lý thất bại?

Lỗi cần được phân loại trước khi chọn hành động. Retry mọi lỗi như nhau có thể làm tình hình xấu hơn.

| Nhóm lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Tạm thời (transient) | Timeout mạng, database failover, throttling, dịch vụ phụ thuộc trả 503 | Retry có backoff và giới hạn |
| Dữ liệu không hợp lệ | Thiếu field bắt buộc, sai schema, payload hỏng | Cách ly hoặc DLQ sớm; không retry mù quáng |
| Lỗi nghiệp vụ không thể tự phục hồi | Tài khoản không tồn tại, trạng thái đơn hàng không hợp lệ | Ghi kết quả nghiệp vụ rõ ràng; DLQ/quarantine nếu cần điều tra |
| Lỗi cấu hình hoặc quyền | Credential hết hạn, IAM deny, endpoint sai | Dừng hoặc giảm retry, cảnh báo vận hành và sửa cấu hình |
| Lỗi tài nguyên | Hết memory, concurrency, quota hoặc timeout do tải | Giảm concurrency, tăng capacity hợp lý, retry có kiểm soát |
| Lỗi code | Null reference, bug không xử lý một loại event | DLQ sau giới hạn thử; sửa code rồi kiểm thử replay |

Một lỗi HTTP 429 có thể là tín hiệu throttling tạm thời và nên tuân theo Retry-After nếu có. Một lỗi xác thực 401/403 thường không được giải quyết bằng cách retry liên tục nếu credential hoặc policy chưa được sửa. Một payload không đúng schema thường sẽ tiếp tục lỗi ở mọi lần thử cho tới khi dữ liệu hoặc code được sửa.

### 2.1. Phân biệt retryable và non-retryable

Handler hoặc lớp điều phối nên phân loại lỗi:

- Retryable: lỗi có khả năng tự hết sau một khoảng thời gian.
- Non-retryable: lỗi dữ liệu hoặc quy tắc nghiệp vụ không thể thay đổi chỉ bằng chờ.
- Unknown: lỗi chưa phân loại; áp dụng retry giới hạn và ghi đủ context để điều tra.

Không nên nuốt exception rồi trả success chỉ để tránh retry. Khi handler báo thành công nhưng chưa hoàn thành công việc, nền tảng có thể xóa/ack sự kiện và công việc bị mất.

### 2.2. Timeout và thời gian xử lý

Timeout của function, visibility timeout của queue, thời gian retry và thời hạn lưu message phải phối hợp với nhau.

Nếu visibility timeout ngắn hơn thời gian xử lý thực tế, message có thể xuất hiện lại khi lần xử lý trước vẫn đang chạy. Hai worker có thể cùng xử lý một sự kiện, gây duplicate side effect.

Đặt timeout theo phân phối thời gian xử lý p95/p99 và thêm khoảng đệm phù hợp. Với batch, tính tổng thời gian xử lý batch và thời gian ghi kết quả. Theo dõi các trường hợp timeout thay vì chỉ tăng timeout vô hạn.

## 3. Delivery semantics và xử lý trùng

Nhiều queue và event source cung cấp delivery theo kiểu **at-least-once**: sự kiện có thể được gửi lại nếu acknowledgment bị mất, consumer timeout hoặc nền tảng không xác định chắc chắn kết quả xử lý. Một số stream có cơ chế checkpoint/offset riêng. Một số dịch vụ cung cấp tùy chọn gần với exactly-once cho phạm vi nhất định, nhưng không nên giả định side effect của toàn bộ ứng dụng tự động exactly-once.

Các tình huống tạo duplicate:

- Function đã ghi database nhưng timeout trước khi acknowledge.
- Consumer xử lý xong nhưng mất kết nối trước khi commit offset.
- Queue visibility timeout hết hạn trong khi worker cũ còn chạy.
- Producer gửi lại vì không nhận được xác nhận.
- Redrive đưa sự kiện đã xử lý một phần trở lại luồng.
- Nền tảng retry một invocation sau lỗi tạm thời.

Do đó, handler cần idempotent: cùng một sự kiện được xử lý nhiều lần vẫn không tạo thêm tác động ngoài ý muốn.

### 3.1. Idempotency key

Mỗi sự kiện nên có một định danh ổn định, ví dụ eventId, transactionId hoặc khóa nghiệp vụ. Lưu trạng thái xử lý theo khóa này.

Một mô hình:

1. Nhận event và lấy idempotency key.
2. Kiểm tra bảng deduplication/inbox.
3. Nếu key đã hoàn tất, trả kết quả thành công mà không lặp side effect.
4. Nếu chưa có, xử lý trong transaction hoặc cơ chế đảm bảo nhất quán.
5. Ghi kết quả và đánh dấu key hoàn tất.
6. Chỉ acknowledge sau khi trạng thái bền vững.

Không dùng invocation ID mới của mỗi lần retry làm idempotency key, vì mỗi lần gọi có thể có ID khác nhau dù là cùng một sự kiện nghiệp vụ.

### 3.2. Transactional inbox và outbox

Khi consumer cần ghi database và phát event tiếp theo, có thể dùng inbox/outbox pattern:

- Inbox lưu event ID đã nhận và trạng thái xử lý trong transaction với thay đổi nghiệp vụ.
- Outbox ghi event cần phát trong cùng transaction với dữ liệu nghiệp vụ.
- Một publisher riêng đọc outbox và gửi event; gửi trùng vẫn được downstream xử lý idempotent.

Cách này giảm rủi ro cập nhật database thành công nhưng phát event thất bại, hoặc phát event thành công nhưng transaction nghiệp vụ rollback.

### 3.3. Ví dụ handler có idempotency

Đoạn mã minh họa bằng Java:

~~~java
public ProcessingResult handle(Event event) {
    String key = event.eventId();

    if (inbox.isCompleted(key)) {
        return ProcessingResult.success();
    }

    try {
        transaction.execute(() -> {
            if (inbox.isCompleted(key)) {
                return;
            }

            validate(event);
            applyBusinessChange(event);
            inbox.markCompleted(key);
        });

        return ProcessingResult.success();
    } catch (TransientDependencyException e) {
        return ProcessingResult.retry(e.getMessage());
    } catch (InvalidEventException e) {
        return ProcessingResult.permanentFailure(e.getMessage());
    }
}
~~~

Đây là mã khái niệm. Trong triển khai thật, thao tác kiểm tra inbox, thay đổi nghiệp vụ và đánh dấu hoàn tất cần cùng transaction hoặc có cơ chế khóa/unique constraint để tránh race condition giữa hai consumer.

## 4. Retry policy

Retry policy xác định khi nào thử lại, thử bao nhiêu lần và khoảng cách giữa các lần thử.

Một policy thường có:

- Maximum attempts hoặc maximum receives.
- Initial delay.
- Backoff multiplier.
- Maximum delay.
- Jitter.
- Maximum event age hoặc retention.
- Timeout cho từng invocation.
- Hành động khi hết retry.

### 4.1. Exponential backoff

Exponential backoff tăng khoảng chờ sau mỗi lần thất bại:

~~~text
delay(n) = min(maxDelay, initialDelay * 2^n)
~~~

Ví dụ initial delay 1 giây, max delay 60 giây:

| Lần retry | Delay minh họa |
|---:|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 16 giây |
| 6 | 32 giây |
| 7 trở đi | Tối đa 60 giây |

Công thức thực tế có thể tính theo attempt index khác nhau. Đây là lịch minh họa, không phải mặc định của mọi nền tảng.

### 4.2. Jitter

Nếu nhiều function cùng lỗi do một dependency, chúng có thể retry cùng thời điểm và tạo một đợt tải mới. Jitter thêm độ ngẫu nhiên vào delay để phân tán retry.

Một cách thường dùng:

~~~text
delay = random(0, min(maxDelay, baseDelay * 2^attempt))
~~~

Có nhiều biến thể jitter; chọn cách phù hợp với hệ thống. Giữ max delay và maximum attempts để retry không kéo dài vô hạn.

### 4.3. Retry có giới hạn

Retry cần giới hạn bởi cả số lần thử và tuổi sự kiện. Một sự kiện đã quá cũ có thể không còn ý nghĩa nghiệp vụ, ví dụ cập nhật trạng thái đơn hàng sau khi cửa sổ thanh toán đã đóng.

Cần quyết định:

- Có retry toàn bộ lỗi hay chỉ lỗi transient?
- Số lần thử tối đa là bao nhiêu?
- Event được giữ trong queue tối đa bao lâu?
- Sau khi hết retry, gửi DLQ hay failure destination nào?
- Khi dependency lỗi diện rộng, có circuit breaker hoặc pause consumer không?
- Có thể làm chậm producer hoặc backpressure không?

Retry không thay thế backpressure. Nếu producer tạo event nhanh hơn consumer xử lý, queue backlog vẫn tăng dù retry được cấu hình tốt.

## 5. Dead-letter queue là gì?

Dead-letter queue là queue hoặc nơi lưu trữ riêng nhận message không thể được xử lý thành công theo chính sách của nguồn. Message được chuyển sang DLQ thường kèm payload và metadata đủ để điều tra, phục hồi hoặc quyết định loại bỏ.

DLQ giúp:

- Cách ly poison message để không chặn luồng chính.
- Giữ lại payload và metadata phục vụ điều tra.
- Cho phép tiếp tục xử lý các sự kiện khác.
- Đo tỷ lệ lỗi và phát cảnh báo.
- Phục hồi sau khi sửa code, dữ liệu hoặc dependency.
- Tách quy trình xử lý lỗi khỏi luồng nghiệp vụ bình thường.

DLQ không tự động xử lý hoặc sửa sự kiện. Nếu không có monitoring, retention, owner và runbook, DLQ có thể trở thành nơi tích tụ dữ liệu bị quên.

### 5.1. DLQ, retry queue và failure destination

| Cơ chế | Mục đích | Khi sử dụng |
|---|---|---|
| Retry queue | Giữ sự kiện chờ thử lại sau một khoảng thời gian | Lỗi transient, cần delay/backoff riêng |
| Dead-letter queue | Cách ly message đã vượt retry policy hoặc không thể xử lý | Poison message, lỗi kéo dài, cần điều tra |
| Failure destination | Ghi kết quả invocation thất bại, có thể gồm request/response context | Một số nền tảng function bất đồng bộ |
| Event archive | Lưu lịch sử sự kiện để audit hoặc replay theo thời gian | Event bus cần lưu giữ và phát lại sự kiện |
| Quarantine store | Lưu payload lỗi hoặc bị nghi ngờ ngoài luồng xử lý chính | Dữ liệu sai, rủi ro bảo mật hoặc cần review |

Tên gọi và cấu trúc khác nhau theo dịch vụ. Failure destination có thể lưu record phong phú hơn DLQ chỉ chứa message. Event archive thường lưu event theo retention dài hạn và không nhất thiết chỉ dành cho event lỗi.

### 5.2. DLQ cho queue và DLQ cho function bất đồng bộ

Cần phân biệt hai trường hợp:

**Queue có redrive policy:** message được consumer nhận nhiều lần nhưng chưa acknowledge/delete. Khi receive count vượt ngưỡng, queue service chuyển message sang DLQ.

**Function invocation bất đồng bộ:** nền tảng giữ invocation event và tự retry theo chính sách. Khi hết tuổi hoặc hết lần thử, có thể gửi tới DLQ hoặc failure destination tùy sản phẩm.

Với function poll queue, lỗi handler có thể khiến message không được xóa và được giao lại sau visibility timeout. Với function async invocation, retry do nền tảng điều khiển. Cùng một khái niệm DLQ nhưng vị trí và metadata khác nhau.

## 6. Poison message và vòng lặp lỗi

Poison message là sự kiện liên tục khiến consumer thất bại. Nguyên nhân có thể là:

- Payload malformed hoặc thiếu field bắt buộc.
- Schema version không tương thích.
- Một giá trị biên kích hoạt bug.
- Kích thước payload vượt giới hạn xử lý.
- Dependency luôn từ chối một loại yêu cầu.
- Event tham chiếu tới tài nguyên đã bị xóa.
- Consumer không tương thích với dữ liệu được phát từ phiên bản mới hơn.

Nếu poison message nằm ở đầu queue FIFO hoặc partition stream, nó có thể ngăn các message sau được xử lý tùy semantics của nguồn. Với queue không bảo đảm thứ tự, nó vẫn tiêu tốn worker và tạo chi phí retry.

### 6.1. Nhận diện poison message

Các dấu hiệu:

- Cùng event ID hoặc cùng message group thất bại lặp lại.
- Receive count tăng nhanh.
- Một payload tạo cùng exception ở mọi lần thử.
- DLQ tăng trong khi queue chính không giảm.
- Một partition/ordering key có lag lớn bất thường.
- Tỷ lệ lỗi tập trung vào một schema version hoặc producer.

Ghi event ID, source, event type, schema version, attempt count, error class và correlation ID. Không log toàn bộ payload nếu có dữ liệu nhạy cảm.

### 6.2. Không retry lỗi vĩnh viễn vô hạn

Nếu payload không hợp lệ, retry sau 30 giây thường không làm dữ liệu hợp lệ hơn. Có thể route nhanh sang quarantine/DLQ sau khi xác thực. Nếu lỗi do code mới triển khai, pause consumer hoặc rollback release có thể phù hợp hơn việc để toàn bộ message đi qua retry cycle.

Cần tránh một rule quá rộng khiến lỗi transient bị chuyển DLQ quá sớm. Phân loại theo exception, error code và context của dependency.

## 7. Cấu hình redrive policy cho queue

Một queue có thể định nghĩa redrive policy để chuyển message sang DLQ sau số lần nhận tối đa. Các trường thường gặp:

- DLQ đích.
- Maximum receive count.
- Retention của queue nguồn và DLQ.
- Quyền truy cập để queue nguồn gửi message tới DLQ.
- Mã hóa và key policy.
- Redrive allow policy nếu dịch vụ hỗ trợ giới hạn queue nguồn nào được phép dùng DLQ.

Ví dụ cấu hình khái niệm, không gắn với schema API cụ thể:

~~~yaml
queue:
  name: orders-events
  visibilityTimeout: 120s
  messageRetention: 4d

  redrive:
    deadLetterQueue: orders-events-dlq
    maxReceiveCount: 5

deadLetterQueue:
  name: orders-events-dlq
  messageRetention: 14d
  encryption: enabled
  alertWhenVisibleMessagesAbove: 0
~~~

Các field trên chỉ minh họa ý tưởng. Tên thuộc tính, đơn vị, giới hạn và semantics phải theo dịch vụ queue thực tế. Đặc biệt, kiểm tra visibility timeout có lớn hơn thời gian xử lý tối đa hợp lý và queue có đủ retention để phục hồi.

### 7.1. Chọn maximum receive count

Ngưỡng quá thấp làm message hợp lệ bị đưa DLQ khi dependency chỉ chập chờn. Ngưỡng quá cao khiến poison message lặp lại lâu, tốn compute và gây backlog.

Chọn ngưỡng dựa trên:

- Tần suất lỗi transient.
- Thời gian recovery của dependency.
- Thời gian xử lý mỗi lần.
- Visibility timeout và backoff.
- Event age tối đa có ý nghĩa.
- Chi phí retry và khả năng phát hiện lỗi.

Nếu queue không hỗ trợ delay tăng dần cho mỗi message, có thể dùng retry queue theo các khoảng thời gian khác nhau hoặc orchestration riêng. Không tạo retry loop không giới hạn giữa nhiều queue.

### 7.2. Retention và thời gian phục hồi

DLQ cần giữ message đủ lâu để đội vận hành phát hiện, điều tra và sửa lỗi. Retention phải lớn hơn khoảng thời gian phản ứng thực tế, gồm cả ngày nghỉ hoặc thời gian chờ nhóm nghiệp vụ.

Cần xác minh cách dịch vụ tính tuổi message sau khi chuyển DLQ. Một số dịch vụ giữ timestamp gốc hoặc áp dụng retention theo quy tắc riêng; không giả định chuyển DLQ sẽ tự động đặt lại tuổi message.

Đặt cảnh báo trước khi message hết retention. Với sự kiện có thời hạn nghiệp vụ, lưu cả occurredAt và expiresAt để redrive không xử lý lại một event đã quá hạn.

## 8. Metadata cần giữ trong DLQ

Khi điều tra, payload thôi chưa đủ. Nên giữ metadata có thể truy vết:

| Trường | Mục đích |
|---|---|
| eventId/messageId | Định danh ổn định để deduplicate |
| source | Producer hoặc nguồn phát |
| eventType | Loại sự kiện nghiệp vụ |
| schemaVersion | Phiên bản cấu trúc payload |
| occurredAt | Thời điểm sự kiện phát sinh |
| enqueuedAt | Thời điểm đưa vào nguồn |
| correlationId/traceId | Liên kết log và trace |
| attemptCount | Số lần đã thử nếu nguồn cung cấp |
| firstFailureAt/lastFailureAt | Khoảng thời gian lỗi |
| errorCode/errorClass | Phân loại nguyên nhân |
| consumerVersion | Phiên bản code xử lý |
| tenantId/partitionKey | Phạm vi nghiệp vụ hoặc thứ tự |
| expiresAt | Thời điểm event không còn giá trị |

Không phải provider nào cũng tự thêm mọi trường này. Có thể cần đóng gói event envelope ở producer hoặc bổ sung metadata trong failure destination.

Không sửa payload gốc khi đưa vào DLQ. Nếu cần chuyển đổi để phục hồi, giữ bản gốc và lưu bản đã biến đổi cùng thông tin mapping/version để có thể audit.

## 9. Quy trình điều tra DLQ

Khi DLQ có message, cần xác định mức độ ảnh hưởng trước khi redrive.

Một quy trình:

1. Xác nhận cảnh báo và phạm vi nguồn queue/function/target.
2. Đo số message, oldest message age và tốc độ tăng.
3. Nhóm theo event type, error code, schema version và consumer version.
4. Chọn một số message đại diện để điều tra.
5. Kiểm tra log, trace, deployment history và dependency health.
6. Xác định lỗi dữ liệu, lỗi code, lỗi cấu hình hay dependency.
7. Quyết định sửa producer, sửa consumer, chuyển đổi payload hoặc bỏ event theo quy trình nghiệp vụ.
8. Kiểm thử bản sửa với message lỗi trong môi trường an toàn.
9. Chọn tập message có thể phục hồi.
10. Redrive có giới hạn và theo dõi kết quả.

### 9.1. Phân loại hành động

| Kết quả điều tra | Hành động |
|---|---|
| Dependency đã phục hồi, payload hợp lệ | Redrive theo batch và rate limit |
| Bug consumer đã sửa | Kiểm thử phiên bản mới rồi redrive |
| Schema cũ có thể chuyển đổi | Chạy migration/reprocessor có version, giữ bản gốc |
| Payload không hợp lệ | Quarantine, yêu cầu producer sửa hoặc xử lý thủ công |
| Event trùng đã hoàn tất | Deduplicate và đánh dấu đã xử lý |
| Event đã hết hạn nghiệp vụ | Không redrive; ghi nhận quyết định và audit |
| Lỗi bảo mật hoặc dữ liệu nhạy cảm | Hạn chế truy cập, xử lý theo quy trình bảo mật |

Không redrive toàn bộ DLQ chỉ vì queue chính đang trống. Trước tiên cần xác nhận nguyên nhân đã được sửa và các message trong DLQ vẫn hợp lệ.

## 10. Redrive và phục hồi sự kiện

Redrive là quá trình đưa message từ DLQ trở lại queue nguồn hoặc một luồng phục hồi để xử lý lại.

Redrive an toàn cần:

- Chọn đúng message và event type.
- Xác minh nguyên nhân lỗi đã được sửa.
- Kiểm tra event còn trong thời hạn nghiệp vụ.
- Bảo đảm idempotency và deduplication.
- Giới hạn tốc độ để không gây overload.
- Chọn batch nhỏ và theo dõi kết quả.
- Lưu audit log về ai, khi nào và vì sao redrive.
- Có thể dừng ngay nếu lỗi lặp lại.

### 10.1. Redrive theo batch

Không đưa hàng nghìn message trở lại queue chính trong một lần nếu consumer và dependency chưa được kiểm chứng.

Một cách làm:

1. Chạy thử một message đại diện.
2. Quan sát xử lý, kết quả và duplicate.
3. Redrive một batch nhỏ.
4. Theo dõi queue depth, DLQ depth, age, error và downstream load.
5. Tăng batch/rate từng bước khi ổn định.
6. Dừng redrive nếu message tiếp tục quay lại DLQ hoặc SLO bị ảnh hưởng.

Nếu provider hỗ trợ redrive task có rate limit, dùng giới hạn phù hợp. Nếu không, tạo consumer phục hồi riêng để đọc DLQ và publish sang queue nguồn có kiểm soát.

### 10.2. Không tạo vòng lặp DLQ

Cần tránh cấu hình queue A gửi lỗi sang DLQ B, rồi consumer của B lại gửi không giới hạn về A. Redrive nên là hành động có chủ đích, có giới hạn và có khả năng dừng.

Đặt metadata replay như replayRunId, replayedAt và replaySource. Giữ event ID gốc để idempotency vẫn hoạt động. Không thay event ID chỉ để né deduplication.

### 10.3. Thứ tự sự kiện

Với queue FIFO hoặc stream có ordering key, redrive có thể làm thay đổi thứ tự tương đối. Nếu event sau phụ thuộc event trước, không phát lại ngẫu nhiên các message trong cùng group.

Cần:

- Giữ partition key hoặc message group.
- Xác định sequence/version.
- Phục hồi theo thứ tự hoặc theo aggregate.
- Dừng replay khi thiếu predecessor quan trọng.
- Kiểm tra consumer có thể phát hiện event cũ hoặc event đến muộn.

Với event độc lập, có thể parallelize nhiều hơn; với event có thứ tự, ưu tiên tính đúng đắn hơn tốc độ.

## 11. Batch processing và partial failure

Một số event source gửi nhiều record trong một invocation. Nếu một record lỗi nhưng handler trả thất bại cho cả batch, toàn bộ batch có thể được retry. Các record đã xử lý thành công có thể chạy lại và tạo duplicate.

Có hai cách xử lý:

- **Batch-level failure:** bất kỳ record lỗi nào khiến cả batch retry. Cách đơn giản nhưng có thể lặp nhiều record.
- **Partial batch response:** handler trả danh sách record thất bại để nền tảng chỉ retry phần cần thiết, nếu event source và tích hợp hỗ trợ.

Ví dụ phản hồi khái niệm:

~~~json
{
  "batchItemFailures": [
    { "itemIdentifier": "message-id-17" },
    { "itemIdentifier": "message-id-22" }
  ]
}
~~~

Đây là ví dụ của một kiểu partial batch response cụ thể, không phải schema dùng chung cho mọi queue/stream. Xác minh event source mapping có hỗ trợ và định dạng identifier cần trả về.

Với stream theo partition, một record lỗi có thể ảnh hưởng checkpoint và các record tiếp theo trong partition. Cần hiểu semantics của batch bisect, retry và checkpoint trước khi bật partial response.

### 11.1. Batch bisect

Một số nền tảng hỗ trợ chia batch thất bại thành các phần nhỏ hơn để tìm record gây lỗi. Cơ chế này hữu ích khi chỉ một record poison trong batch lớn, nhưng làm tăng số invocation và không thay thế idempotency.

Theo dõi batch size, retry count, record age và checkpoint lag. Chọn batch size cân bằng giữa throughput, timeout và khả năng cách ly lỗi.

## 12. DLQ cho các loại event source

Mỗi loại nguồn có cách lưu và xác nhận sự kiện khác nhau.

| Event source | Cơ chế lỗi cần hiểu |
|---|---|
| Queue polling | Visibility timeout, receive count, ack/delete và redrive policy |
| Function async invocation | Retry của nền tảng, maximum event age, maximum attempts và failure destination/DLQ |
| Event bus | Retry delivery tới target, event age, retry policy và target DLQ |
| Stream/partition | Offset/checkpoint, shard/partition lag, batch retry và poison record |
| Object event | Event notification có thể duplicate hoặc đến trễ; object key/version cần idempotency |
| Database change stream | Checkpoint, resume token, retention của log và thứ tự thay đổi |
| Scheduler/timer | Missed invocation, retry window và idempotency theo scheduled time |

### 12.1. Queue polling

Với queue polling, consumer thường nhận message trong một khoảng visibility lease. Nếu xử lý thành công, consumer xóa/ack message. Nếu thất bại, message trở lại trạng thái có thể nhận sau khi visibility timeout hết hoặc được release theo API.

Receive count có thể tăng qua các lần nhận. Khi vượt maximum receive count, dịch vụ chuyển message sang DLQ theo redrive policy. Chi tiết thời điểm tăng count và xử lý timeout phụ thuộc provider.

### 12.2. Function async invocation

Với invocation bất đồng bộ, nền tảng có thể giữ event và tự retry khi function trả lỗi hoặc timeout. Chính sách có thể giới hạn số lần thử hoặc tuổi tối đa. Sau khi hết policy, sự kiện có thể được gửi đến DLQ hoặc failure destination.

Một failure destination có thể chứa metadata invocation và response context nhiều hơn payload ban đầu. Cần bảo vệ dữ liệu đó tương tự log nhạy cảm.

### 12.3. Event bus

Event bus có thể retry việc gửi event tới target khi target không nhận được hoặc trả lỗi. Retry policy và DLQ thường gắn với target rule. Một event có thể thành công với target này nhưng thất bại ở target khác; theo dõi failure theo từng target thay vì chỉ đếm tổng event bus.

### 12.4. Stream và partition

Với stream, consumer thường lưu checkpoint/offset để tiếp tục đọc. Một record lỗi có thể giữ checkpoint ở phía trước và làm tăng lag. DLQ có thể được dùng để chuyển record lỗi sang luồng riêng rồi tiếp tục checkpoint, nếu tích hợp hỗ trợ.

Khi bỏ qua record lỗi để tiến checkpoint, cần bảo đảm record đã được lưu bền vững ở nơi khác và có quy trình replay. Nếu không, có thể mất dữ liệu.

## 13. Bảo mật DLQ và dữ liệu sự kiện

DLQ thường chứa payload lỗi, stack/error metadata và thông tin nghiệp vụ. Dữ liệu này có thể nhạy cảm hơn log thông thường vì chứa request gốc hoặc nội dung chưa được xử lý.

Các nguyên tắc:

- Mã hóa khi lưu trữ và truyền tải.
- Giới hạn quyền đọc DLQ cho đúng nhóm vận hành.
- Dùng IAM/workload identity và quyền tối thiểu.
- Tách quyền xem payload khỏi quyền redrive/xóa message nếu nền tảng hỗ trợ.
- Không log toàn bộ payload hoặc secret khi điều tra.
- Mask dữ liệu cá nhân và token trong dashboard/log.
- Đặt retention và lifecycle policy.
- Ghi audit log cho receive, purge, redrive và thay đổi policy.
- Kiểm tra quyền key encryption và quyền gửi từ source queue.
- Không cho producer tùy ý ghi trực tiếp vào DLQ nếu không cần.

DLQ có thể chứa dữ liệu cũ hoặc event độc hại. Trước khi redrive, xác minh nguồn phát và schema; không thực thi payload như code hoặc lệnh.

## 14. Monitoring và cảnh báo DLQ

Một hệ thống DLQ cần monitoring liên tục. Chỉ biết queue tồn tại là chưa đủ.

Các metric quan trọng:

| Metric | Ý nghĩa |
|---|---|
| dlq_visible_messages | Số message đang chờ trong DLQ |
| dlq_oldest_message_age_seconds | Tuổi message lâu nhất |
| dlq_incoming_rate | Tốc độ message đi vào DLQ |
| source_queue_depth | Backlog ở queue nguồn |
| source_oldest_message_age | Tuổi message lâu nhất ở nguồn |
| event_processing_success_rate | Tỷ lệ xử lý thành công |
| event_retry_count | Số lần retry |
| event_processing_duration | Thời gian xử lý |
| redrive_count | Số message được phục hồi |
| redrive_success_rate | Tỷ lệ redrive thành công |
| duplicate_detection_count | Số event bị deduplicate |
| stream_consumer_lag | Độ trễ consumer đối với stream |

Cần theo dõi theo source, event type, consumer version và tenant ở mức cardinality hợp lý. Không dùng payload hoặc message ID làm label metric có số lượng vô hạn; giữ định danh chi tiết trong log/trace.

### 14.1. Cảnh báo

Các cảnh báo thường dùng:

- DLQ có message mới, đặc biệt với luồng nghiệp vụ quan trọng.
- DLQ visible count tăng liên tục.
- Oldest message age tiến gần retention.
- Source queue backlog hoặc age vượt SLO.
- Retry rate tăng bất thường.
- Một consumer version tạo nhiều lỗi hơn phiên bản trước.
- Redrive làm DLQ tăng trở lại.
- Consumer lag không giảm dù capacity đã tăng.
- Quyền truy cập hoặc mã hóa DLQ thất bại.

Với một số luồng có thể chấp nhận message lỗi, cảnh báo có thể theo ngưỡng và event type. Với payment, identity hoặc dữ liệu quan trọng, một message vào DLQ có thể cần cảnh báo ngay.

### 14.2. Dashboard theo vòng đời

Dashboard nên cho thấy chuỗi:

Producer rate → source queue depth/age → invocation rate → success/failure → retry → DLQ → redrive → successful completion.

Nhìn toàn chuỗi giúp phân biệt producer tăng tải, consumer thiếu capacity, dependency lỗi và poison message. Nếu chỉ nhìn DLQ, có thể bỏ qua backlog đang tăng ở queue nguồn.

## 15. Runbook phục hồi DLQ

Một runbook nên chỉ rõ ai chịu trách nhiệm, điều kiện dừng và bằng chứng hoàn tất.

### Khi phát hiện DLQ tăng

1. Xác nhận tên queue/function/target và mức độ ảnh hưởng.
2. Kiểm tra source queue depth, oldest age và consumer health.
3. Nhóm lỗi theo event type, schema version và error code.
4. Xác định có phải lỗi diện rộng của dependency hay không.
5. Nếu lỗi diện rộng, giảm concurrency hoặc tạm dừng consumer theo runbook để tránh làm nặng dependency.
6. Nếu lỗi dữ liệu, cách ly nhóm payload lỗi và báo owner producer.
7. Nếu lỗi code, rollback hoặc phát hành bản sửa đã kiểm thử.
8. Xác minh permission, key và network nếu lỗi cấu hình.

### Khi chuẩn bị redrive

1. Xác nhận nguyên nhân đã được khắc phục.
2. Xác minh event còn hạn nghiệp vụ và schema tương thích.
3. Kiểm tra idempotency và duplicate protection.
4. Chọn một event đại diện để replay.
5. Chạy thử trong môi trường an toàn nếu có thể.
6. Chọn batch nhỏ, đặt rate limit và thời gian chạy.
7. Theo dõi source queue, DLQ, downstream load và SLO.
8. Dừng ngay nếu event tiếp tục thất bại hoặc dependency quá tải.
9. Ghi audit record về số lượng, phạm vi, người thực hiện và kết quả.

### Khi quyết định không redrive

Một số message cần được đóng theo quyết định nghiệp vụ thay vì replay:

- Event đã hết hạn.
- Event duplicate đã được xử lý.
- Payload không hợp lệ và không thể sửa an toàn.
- Producer xác nhận event không còn hiệu lực.
- Sự kiện bị giữ vì yêu cầu bảo mật hoặc điều tra.

Purge DLQ là thao tác có thể mất dữ liệu. Chỉ thực hiện khi có retention/audit policy, bản lưu cần thiết và phê duyệt tương ứng. Không dùng purge để làm dashboard về 0 mà không giải quyết nguyên nhân.

## 16. Ví dụ thiết kế luồng xử lý đơn hàng

Một dịch vụ nhận OrderCreated từ queue và cập nhật hệ thống fulfillment.

Thiết kế:

- Producer phát event có eventId, orderId, schemaVersion và occurredAt.
- Queue chính giữ event cho worker serverless.
- Worker kiểm tra schema và idempotency key.
- Worker đọc trạng thái đơn hàng và ghi fulfillment trong transaction.
- Khi dependency timeout, worker trả lỗi retryable.
- Khi payload sai schema, worker phân loại permanent failure.
- Sau số lần nhận tối đa, queue chuyển message sang DLQ.
- Dashboard cảnh báo khi DLQ có message hoặc oldest age vượt ngưỡng.
- Sau khi sửa lỗi, operator chọn một batch để redrive.
- Inbox/deduplication ngăn tạo fulfillment trùng nếu event đã được xử lý trước đó.

~~~mermaid
sequenceDiagram
    participant P as Order service
    participant Q as Orders queue
    participant W as Serverless worker
    participant DB as Fulfillment DB
    participant DLQ as Orders DLQ
    P->>Q: OrderCreated(eventId)
    Q->>W: Deliver event
    W->>DB: Validate and apply
    alt Processing succeeds
        DB-->>W: Commit
        W-->>Q: Acknowledge
    else Transient failure
        W-->>Q: Retry later
        Q->>W: Redeliver
    else Attempts exhausted
        Q->>DLQ: Move message
        DLQ-->>DLQ: Retain for investigation
    end
~~~

Nếu event đã ghi fulfillment nhưng acknowledgment bị mất, queue có thể giao lại. Idempotency key giúp worker nhận ra event đã hoàn tất và acknowledge an toàn.

## 17. Kiểm thử retry và DLQ

Không đợi sự cố production mới kiểm tra DLQ. Nên có test cho các loại failure chính:

| Kịch bản | Kỳ vọng |
|---|---|
| Dependency timeout một lần | Retry và xử lý thành công sau khi dependency phục hồi |
| Dependency lỗi kéo dài | Retry có giới hạn rồi chuyển DLQ |
| Payload sai schema | Không retry vô hạn; cách ly và giữ metadata |
| Duplicate event | Side effect chỉ xảy ra một lần theo idempotency |
| Worker timeout sau commit | Redelivery không tạo kết quả trùng |
| Batch có một record lỗi | Chỉ retry record lỗi nếu tích hợp hỗ trợ partial response |
| DLQ permission sai | Cảnh báo rõ, message không âm thầm mất |
| DLQ retention gần hết | Cảnh báo trước khi message hết hạn |
| Redrive tốc độ cao | Rate limit bảo vệ dependency và queue chính |
| Replay event cũ | Expiry/business validation ngăn tác động lỗi thời |

Sau test, xác minh dữ liệu nghiệp vụ, queue depth, DLQ, logs và audit records. Không chỉ kiểm tra message có rời DLQ hay không; cần chứng minh event đã hoàn tất đúng và không tạo side effect trùng.

## 18. Các lỗi vận hành thường gặp

**Retry vô hạn:** poison message tiêu tốn compute và làm backlog tăng. Giới hạn attempt và event age.

**DLQ không có cảnh báo:** message lỗi nằm lâu tới khi hết retention. Cảnh báo theo count và oldest age.

**Không phân loại lỗi:** lỗi schema bị retry như timeout. Phân loại transient/permanent.

**Handler trả success khi chưa commit:** event bị ack và công việc mất. Chỉ acknowledge sau khi trạng thái bền vững.

**Không có idempotency:** redelivery hoặc redrive tạo side effect trùng. Dùng event ID ổn định và inbox/deduplication.

**Visibility timeout quá ngắn:** message được giao lại khi worker cũ còn chạy. Đặt timeout theo thời gian xử lý và buffer.

**DLQ retention quá ngắn:** đội vận hành chưa kịp điều tra thì message đã hết hạn. Đặt retention theo thời gian phản ứng và yêu cầu audit.

**Redrive toàn bộ cùng lúc:** consumer và dependency bị quá tải. Chạy batch nhỏ, rate limit và theo dõi.

**Replay không giữ thứ tự:** event sau chạy trước event trước và làm sai trạng thái aggregate. Giữ partition/message group và sequence.

**Không phân biệt DLQ với failure destination:** thiếu metadata hoặc cấu hình sai nơi nhận lỗi. Kiểm tra semantics của trigger.

**Log toàn bộ payload:** lộ dữ liệu cá nhân hoặc token. Mask và giới hạn truy cập.

**Purge để xóa cảnh báo:** mất bằng chứng và có thể mất công việc. Điều tra, redrive hoặc đóng event theo quy trình.

**DLQ không có owner:** không ai chịu trách nhiệm xử lý message. Gắn owner, SLA và runbook cho từng luồng.

## 19. Checklist thiết kế và vận hành DLQ

- [ ] Đã xác định event source và delivery semantics của dịch vụ.
- [ ] Đã phân loại transient, permanent, configuration và code failure.
- [ ] Retry có maximum attempts, maximum age, backoff và jitter phù hợp.
- [ ] Timeout, visibility timeout và thời gian xử lý batch được phối hợp.
- [ ] DLQ/failure destination được cấu hình và có quyền ghi phù hợp.
- [ ] Retention đủ cho thời gian điều tra và phục hồi.
- [ ] Payload và metadata có event ID, source, schema version và correlation ID.
- [ ] Handler idempotent; deduplication được lưu bền vững.
- [ ] Side effect và acknowledgment có thứ tự an toàn.
- [ ] Poison message được cách ly mà không chặn toàn bộ luồng.
- [ ] Batch partial failure được bật nếu event source hỗ trợ và cần thiết.
- [ ] Replay kiểm tra event expiry, schema và business state.
- [ ] Redrive có batch size, rate limit, audit và điều kiện dừng.
- [ ] Ordering key/partition được giữ khi replay event có thứ tự.
- [ ] DLQ được mã hóa, giới hạn quyền và có retention policy.
- [ ] Dashboard theo dõi count, oldest age, retry, success và redrive.
- [ ] Cảnh báo có owner và SLA xử lý.
- [ ] Đã kiểm thử dependency failure, poison event, duplicate và mất máy.
- [ ] Có runbook điều tra, phục hồi và quyết định không redrive.

DLQ là cơ chế cách ly sự kiện đã thất bại sau chính sách retry; giá trị của nó nằm ở khả năng giữ bằng chứng, phát hiện lỗi và phục hồi công việc có kiểm soát. Hãy phân loại lỗi trước khi retry, giới hạn backoff và event age, thiết kế handler idempotent, rồi redrive theo batch sau khi nguyên nhân đã được sửa. Kết hợp monitoring, retention, quyền truy cập và runbook có owner giúp hệ thống serverless tiếp tục xử lý sự kiện tốt trong khi các message lỗi được điều tra và phục hồi an toàn.
