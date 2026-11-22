# Quarantine, redrive và replay sự kiện sau sự cố

Trong chương **Độ tin cậy và phục hồi**, quarantine, redrive và replay là các kỹ thuật giữ lại công việc lỗi, điều tra nguyên nhân rồi xử lý lại có kiểm soát. Trong hệ thống serverless, một event có thể đi qua API, queue, event bus, stream và nhiều function. Khi một consumer gặp lỗi, cần giữ được dữ liệu gốc, biết lỗi xảy ra ở đâu, tránh retry vô hạn và có thể khôi phục mà không tạo side effect trùng lặp.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng theo mô hình serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Quarantine, redrive và replay giúp hệ thống phục hồi sau sự cố mà vẫn kiểm soát được tải, thứ tự, trạng thái và tính nhất quán dữ liệu.

## 1. Quarantine, redrive và replay là gì?

Ba khái niệm này có liên quan nhưng đại diện cho các bước khác nhau:

- **Quarantine:** cô lập event hoặc message không thể xử lý an toàn để nó không tiếp tục gây lỗi cho luồng chính. Dữ liệu được giữ lại cùng metadata phục vụ điều tra.
- **Redrive:** chuyển message đã bị đưa vào dead-letter queue (DLQ) trở lại một queue hoặc luồng xử lý để thử lại.
- **Replay:** phát lại sự kiện từ một nguồn lưu trữ hoặc log sự kiện trong một khoảng thời gian/phạm vi đã chọn.

Ví dụ, một Lambda consumer nhận message chứa schema version mới nhưng code hiện tại chưa hiểu. Message liên tục thất bại. Sau số lần retry được cấu hình, message được chuyển vào DLQ. Nhóm vận hành điều tra, triển khai phiên bản consumer đã sửa, rồi redrive một phần message từ DLQ với tốc độ giới hạn.

Một trường hợp khác: EventBridge đã lưu event vào archive. Một consumer bị lỗi trong 30 phút, nhưng event bus vẫn nhận các event. Sau khi sửa consumer, nhóm vận hành replay khoảng thời gian bị ảnh hưởng từ archive để consumer nhận lại các event đó.

Quarantine là cách ly và bảo toàn dữ liệu lỗi; redrive/replay là cách đưa dữ liệu trở lại quá trình xử lý. Không phải mọi event lỗi đều cần replay, và không phải mọi nguồn sự kiện đều có cơ chế replay giống nhau.

## 2. Vì sao cần cơ chế phục hồi?

Một hệ thống phân tán có thể gặp nhiều loại lỗi:

- Payload không hợp lệ hoặc thiếu field bắt buộc.
- Consumer chưa hỗ trợ schema version mới.
- Dependency tạm thời timeout hoặc throttling.
- Credential hết hạn hoặc IAM policy bị thay đổi.
- Database quá tải hoặc hết connection.
- Function vượt timeout hoặc hết memory.
- Một bug chỉ xuất hiện với một nhóm dữ liệu đặc biệt.
- Event bị giao nhiều lần hoặc sai thứ tự.
- Một deployment mới làm consumer xử lý lỗi một loại event trước đó vẫn hợp lệ.

Nếu chỉ retry, một message độc hại hoặc không hợp lệ có thể được giao lại nhiều lần mà không thể thành công. Nếu xóa message lỗi, dữ liệu nghiệp vụ có thể bị mất. Nếu replay toàn bộ event không có giới hạn, hệ thống có thể tạo một đợt tải lớn và lặp lại side effect.

Một quy trình phục hồi tốt cần trả lời:

1. Event nào thất bại?
2. Thất bại do lỗi tạm thời hay lỗi dữ liệu?
3. Dữ liệu gốc có được giữ nguyên không?
4. Có bao nhiêu lần thử và vì sao dừng retry?
5. Có thể sửa code hoặc cấu hình để xử lý lại không?
6. Phát lại sẽ tác động đến dữ liệu hoặc dịch vụ nào?
7. Làm sao giới hạn tốc độ và ngăn duplicate?
8. Làm sao xác nhận mọi event cần phục hồi đã được xử lý?

## 3. Phân biệt retry, DLQ, quarantine và archive

| Cơ chế | Mục đích | Vòng đời dữ liệu |
|---|---|---|
| Retry | Thử lại lỗi có khả năng tạm thời | Theo retry policy của nguồn |
| DLQ | Giữ message không xử lý được sau ngưỡng retry | Theo retention của queue |
| Quarantine store | Cô lập event cần điều tra hoặc xử lý thủ công | Theo retention và policy do hệ thống thiết kế |
| Event archive | Lưu event để tra cứu hoặc replay trong một khoảng thời gian | Theo retention của archive |
| Event log/stream | Giữ lịch sử event theo retention của nền tảng | Có thể replay theo offset/time nếu còn dữ liệu |

DLQ không mặc nhiên là kho lưu trữ lâu dài. Message có thể hết hạn theo retention. Archive cũng không nhất thiết lưu mọi dữ liệu cần thiết để tái tạo trạng thái nghiệp vụ; nó chỉ giữ những event đã được cấu hình lưu.

Quarantine store có thể là queue riêng, object storage hoặc database có trạng thái. Dùng loại nào tùy nhu cầu tìm kiếm, kích thước payload, retention, quyền truy cập và cách redrive.

## 4. Poison message và lỗi có thể phục hồi

Poison message là message liên tục làm consumer thất bại. Nguyên nhân thường gặp:

- Payload sai schema hoặc không parse được.
- Một giá trị làm code ném exception lặp lại.
- Event tham chiếu đến resource đã bị xóa.
- Business invariant không còn đúng.
- Một dependency luôn từ chối thao tác với dữ liệu đó.
- Message quá lớn hoặc vượt giới hạn xử lý.
- Consumer có bug chỉ kích hoạt với một trường hợp hiếm.

Cần phân biệt:

| Loại lỗi | Ví dụ | Hành động |
|---|---|---|
| Transient | HTTP 503, throttling, network timeout | Retry có backoff |
| Permanent data error | JSON hỏng, thiếu event type | Quarantine/DLQ và điều tra |
| Compatibility error | Consumer chưa hiểu schema version | Nâng consumer hoặc transform event |
| Authorization/configuration | AccessDenied, role sai | Sửa policy/config, không retry vô hạn |
| Business rejection | Đơn hàng đã hủy, trạng thái không hợp lệ | Ghi nhận kết quả nghiệp vụ, thường không retry |
| Unknown | Lỗi chưa phân loại | Retry có giới hạn rồi đưa vào DLQ |

Không nên coi mọi exception là transient. Nếu lỗi là AccessDenied hoặc payload không hợp lệ, retry liên tục chỉ tạo thêm invocation, log và tải lên dependency.

## 5. Chính sách retry trước khi đưa vào DLQ

Một retry policy nên định nghĩa:

- Số lần thử tối đa.
- Tổng thời gian event được phép tồn tại trước khi hết hạn.
- Khoảng delay giữa các lần thử.
- Backoff và jitter.
- Lỗi nào được retry.
- Lỗi nào phải quarantine ngay.
- Nơi gửi message sau khi hết retry.
- Cách cảnh báo và xử lý DLQ.

Exponential backoff có thể giảm tốc độ thử lại khi dependency đang phục hồi:

\[
delay_n = random(0,\ min(maxDelay,\ baseDelay \times 2^n))
\]

Jitter tránh việc nhiều worker retry đồng thời. Cần có max delay và retry budget để một event không chiếm tài nguyên vô hạn.

Retry ở nhiều tầng có thể nhân số lần gọi. Ví dụ SDK retry ba lần, handler tự retry ba lần và nguồn event retry năm lần có thể tạo số lần gọi lớn hơn nhiều so với dự kiến. Chỉ định rõ tầng nào chịu trách nhiệm retry và giới hạn tổng số lần thử.

## 6. Kiến trúc quarantine và phục hồi

Một kiến trúc cơ bản:

~~~mermaid
flowchart TD
    SRC["HTTP / Queue / Event / Stream"] --> CON["Java consumer"]
    CON --> DEC{"Process result"}
    DEC -->|"Success"| ACK["Acknowledge / checkpoint"]
    DEC -->|"Transient failure"| RET["Retry with backoff"]
    RET --> CON
    DEC -->|"Permanent or max attempts"| Q["DLQ / quarantine"]
    Q --> TRIAGE["Inspect and classify"]
    TRIAGE --> FIX["Fix code, data or configuration"]
    FIX --> CONTROL["Approve replay scope and rate"]
    CONTROL --> REPLAY["Redrive / replay"]
    REPLAY --> CON
~~~

Các thành phần quan trọng:

- Consumer xử lý event và phân loại lỗi.
- Retry policy giữ lỗi tạm thời trong giới hạn.
- DLQ/quarantine giữ event cần điều tra.
- Metadata hỗ trợ tìm nguồn gốc, số lần thử và lỗi cuối.
- Runbook hướng dẫn cách sửa nguyên nhân và chọn phạm vi replay.
- Replay controller giới hạn tốc độ và số lượng event được phát lại.
- Idempotency bảo vệ side effect khi event được giao lại.

Không để replay controller bỏ qua consumer và ghi trực tiếp vào database nghiệp vụ nếu mục tiêu là chạy lại cùng business logic. Phát lại qua đường xử lý đã được kiểm thử giúp giữ validation, authorization và observability nhất quán.

## 7. Thiết kế quarantine record

Quarantine record cần giữ đủ thông tin để tái xử lý nhưng không tạo thêm nơi rò rỉ dữ liệu.

Một cấu trúc tham khảo:

~~~json
{
  "quarantineId": "q-01J9EXAMPLE",
  "source": {
    "service": "orders-queue",
    "messageId": "msg-123",
    "eventSourceArn": "arn:aws:sqs:region:account:orders"
  },
  "event": {
    "eventId": "evt-456",
    "eventType": "OrderPlaced",
    "schemaVersion": 2,
    "occurredAt": "2026-11-17T10:00:00Z"
  },
  "failure": {
    "category": "SCHEMA_INCOMPATIBLE",
    "errorCode": "UNSUPPORTED_VERSION",
    "attempts": 5,
    "failedAt": "2026-11-17T10:02:00Z"
  },
  "recovery": {
    "status": "QUARANTINED",
    "replayCount": 0
  }
}
~~~

Đây là ví dụ minh họa. Tùy nguồn, message ID, event source ARN, receive count hoặc timestamp có thể không có sẵn. Không tự tạo giá trị giả để lấp field; hãy lưu field thực tế và biểu diễn rõ giá trị không có.

Nên lưu:

- Payload gốc hoặc reference tới payload bất biến.
- Event ID và message ID nếu nguồn cung cấp.
- Nguồn phát, queue, stream, partition hoặc event bus.
- Event type và schema version.
- Thời điểm xảy ra và thời điểm nhận.
- Số lần giao/attempt nếu có.
- Error category và error code đã làm sạch.
- Correlation ID/trace ID.
- Trạng thái quarantine và lịch sử replay.
- Người hoặc hệ thống phê duyệt thao tác phục hồi.

Không nhất thiết sao chép toàn bộ payload vào log. Payload lớn hoặc chứa PII nên được mã hóa trong object storage có kiểm soát truy cập; quarantine record chỉ lưu reference, checksum và metadata cần thiết.

## 8. Quản lý vòng đời quarantine

Một state machine giúp ngăn việc replay tùy tiện:

~~~mermaid
stateDiagram-v2
    [*] --> QUARANTINED
    QUARANTINED --> TRIAGING
    TRIAGING --> READY
    TRIAGING --> DISCARDED
    READY --> REPLAYING
    REPLAYING --> COMPLETED
    REPLAYING --> QUARANTINED: Failed again
    COMPLETED --> [*]
    DISCARDED --> [*]
~~~

Ý nghĩa các trạng thái:

- **QUARANTINED:** event đã được cô lập.
- **TRIAGING:** đang điều tra nguyên nhân và đánh giá tác động.
- **READY:** nguyên nhân đã được xử lý, event đủ điều kiện replay.
- **REPLAYING:** event đang được phát lại.
- **COMPLETED:** replay thành công và kết quả được xác nhận.
- **DISCARDED:** event được quyết định không xử lý lại, có lý do và audit record.

Không chuyển thẳng từ QUARANTINED sang replay chỉ vì queue đã có message. Phải xác nhận lỗi gốc đã được khắc phục; nếu không, event sẽ quay lại DLQ và tiếp tục tạo tải.

## 9. AWS SQS DLQ và redrive

Với SQS, redrive policy trên source queue quy định số lần message được nhận trước khi chuyển sang DLQ. Thuộc tính receive count tăng khi message được giao cho consumer; khi vượt ngưỡng cấu hình, message được chuyển vào DLQ theo cơ chế của SQS.

Một số điểm cần nhớ:

- DLQ nên cùng loại queue với source queue: Standard với Standard, FIFO với FIFO.
- DLQ có retention riêng; message không nên được giữ vô thời hạn nếu không có chính sách phù hợp.
- Với Standard queue, thời điểm enqueue ban đầu được giữ khi message chuyển sang DLQ; thời gian retention của DLQ vì vậy cần dài hơn source queue nếu cần đủ thời gian điều tra. FIFO có semantics timestamp khác, nên kiểm tra tài liệu queue type đang dùng.
- Source queue và DLQ cần cùng Region và được cấu hình quyền phù hợp.
- Cần kiểm tra redrive allow policy để kiểm soát queue nào được phép dùng DLQ.
- Redrive không sửa lỗi payload hoặc consumer.
- Message được redrive có thể được giao lại nhiều lần; consumer vẫn phải idempotent.

### 9.1. Cấu hình redrive policy

Ví dụ CloudFormation rút gọn:

~~~yaml
Resources:
  OrdersDeadLetterQueue:
    Type: AWS::SQS::Queue
    Properties:
      MessageRetentionPeriod: 1209600

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 180
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrdersDeadLetterQueue.Arn
        maxReceiveCount: 5
~~~

Các giá trị retention, visibility timeout và maxReceiveCount chỉ là ví dụ. Cần chọn theo thời gian xử lý, retry policy, retention của nguồn và thời gian vận hành dự kiến. Visibility timeout quá ngắn có thể khiến message được giao đồng thời khi worker cũ vẫn xử lý; quá dài làm thời gian phục hồi chậm hơn.

Đối với SQS FIFO, đưa message vào DLQ có thể làm thay đổi chuỗi xử lý theo MessageGroupId. Nếu thứ tự tuyệt đối là yêu cầu nghiệp vụ, cần đánh giá tác động của DLQ và cách phục hồi theo từng message group.

### 9.2. Redrive có kiểm soát bằng AWS CLI

AWS CLI có thể khởi tạo message move task từ DLQ:

~~~bash
aws sqs start-message-move-task \
  --source-arn arn:aws:sqs:ap-southeast-1:123456789012:orders-dlq \
  --destination-arn arn:aws:sqs:ap-southeast-1:123456789012:orders-replay \
  --max-number-of-messages-per-second 25
~~~

Đây là command minh họa với ARN và tốc độ giả định. Khi dùng, cần xác nhận destination queue đúng loại, đúng Region và đã được kiểm soát consumer. Có thể bỏ destination để dùng source queue gốc theo khả năng API, nhưng queue replay riêng thường giúp tách tải phục hồi khỏi traffic mới.

Tốc độ 25 message/giây không phải giá trị khuyến nghị chung. Chọn rate dựa trên quota downstream, worker concurrency, queue age và traffic production hiện tại.

Có thể xem trạng thái move task qua API/CLI tương ứng và hủy task nếu hệ thống bắt đầu quá tải. Không chạy nhiều redrive task chồng lấn nếu chưa hiểu tác động lên thứ tự và tổng tốc độ phát.

## 10. Phân biệt SQS DLQ với Lambda asynchronous failure destination

Đây là hai cơ chế dễ bị nhầm.

### 10.1. Lambda asynchronous invocation

Khi Lambda được gọi bất đồng bộ, Lambda service quản lý hàng đợi nội bộ và retry theo cấu hình async invocation. Có thể cấu hình:

- Maximum retry attempts.
- Maximum event age.
- Dead-letter queue cho event thất bại.
- On-failure destination để gửi invocation record tới SQS, SNS, Lambda hoặc EventBridge theo hỗ trợ của Lambda.

Destination có thể chứa metadata invocation, request và response context hữu ích cho điều tra. DLQ truyền thống chủ yếu lưu event gốc. Chọn cơ chế theo nhu cầu quan sát và xử lý hậu sự cố.

### 10.2. Lambda event source mapping

Với SQS, Kinesis hoặc DynamoDB Streams, Lambda poll nguồn sự kiện qua event source mapping. Retry và checkpoint phụ thuộc loại nguồn.

- Với SQS, message được giữ trong queue và có thể chuyển sang DLQ theo redrive policy của queue.
- Với Kinesis/DynamoDB Streams, batch failure có thể ảnh hưởng checkpoint và việc đọc lại record; có các cấu hình retry, record age và on-failure destination phù hợp.
- Với Kafka, consumer offset và retention của topic ảnh hưởng khả năng đọc lại.

Không cấu hình Lambda asynchronous DLQ rồi kỳ vọng nó xử lý message của SQS event source mapping. Phải cấu hình đúng nơi quản lý retry của trigger.

## 11. EventBridge archive và replay

EventBridge archive cho phép lưu event từ event bus theo filter và retention đã cấu hình. Khi consumer hoặc rule gặp sự cố, có thể replay các event trong khoảng thời gian đã lưu trở lại event bus đích.

Quy trình khái quát:

1. Tạo archive và cấu hình event pattern phù hợp trước khi xảy ra sự cố.
2. Đặt retention đủ dài cho yêu cầu vận hành.
3. Khi phát hiện lỗi, xác định khoảng thời gian và loại event bị ảnh hưởng.
4. Sửa consumer/rule/permission.
5. Kiểm tra filter và destination của replay.
6. Bắt đầu replay theo phạm vi đã phê duyệt.
7. Theo dõi consumer, duplicate và downstream load.
8. Đối chiếu số event được replay với số event xử lý thành công.

Archive chỉ lưu event phù hợp với filter và thời gian retention. Nếu chưa bật archive trước sự cố hoặc event không khớp filter, không thể dựa vào archive để khôi phục event đó.

Replay gửi event trở lại event bus, sau đó rule và target hoạt động theo cấu hình hiện tại. Điều này có nghĩa replay có thể kích hoạt nhiều consumer, không chỉ consumer đang cần sửa. Hãy dùng event pattern, bus đích hoặc rule routing phù hợp để tránh tác động ngoài phạm vi.

EventBridge replay không tự bảo đảm consumer xử lý exactly-once. Event đã từng được xử lý trước sự cố có thể được giao lại. Consumer cần idempotency và kiểm soát side effect.

## 12. Replay từ Kinesis và DynamoDB Streams

Stream lưu event theo shard/partition và cho phép consumer đọc lại trong giới hạn retention.

Với Kinesis Data Streams, consumer có thể bắt đầu đọc từ vị trí như TRIM_HORIZON, LATEST hoặc timestamp được hỗ trợ. Nếu record đã hết retention, stream không còn dữ liệu để replay. Retention của Kinesis có thể được cấu hình trong giới hạn dịch vụ.

DynamoDB Streams có retention cố định 24 giờ; vì vậy không nên coi stream là kho lưu trữ lâu dài. Nếu cần replay dài hạn, lưu event vào archive hoặc event store riêng.

Khi dùng Lambda event source mapping:

- Starting position chỉ xác định điểm bắt đầu đọc của mapping mới hoặc mapping được tạo lại theo cơ chế hỗ trợ.
- Batch retry và checkpoint có thể làm một số record được đọc lại.
- Bisect batch on function error giúp chia batch lỗi để cô lập record gây lỗi với nguồn hỗ trợ.
- Partial batch response có thể báo record lỗi cụ thể khi nguồn hỗ trợ.
- On-failure destination có thể lưu thông tin batch lỗi theo cấu hình và khả năng của nguồn.

Replay stream cần giữ partition key và sequence context khi nghiệp vụ yêu cầu thứ tự. Nếu tạo consumer mới hoặc mapping mới, tránh để hai consumer cùng thực hiện side effect lên một tập record mà không có cơ chế phối hợp.

## 13. Replay từ Kafka và các nguồn khác

Với Kafka, khả năng replay phụ thuộc topic retention và offset của consumer group. Có thể tạo consumer group mới để đọc lại từ đầu trong retention, hoặc điều chỉnh offset của group hiện tại theo quy trình được kiểm soát. Thay đổi offset của consumer production đang chạy có thể làm phát lại nhiều event hoặc bỏ qua event chưa xử lý.

Với S3 notification, không nên giả định có archive/replay chung như EventBridge. Nếu cần phục hồi, có thể dựa vào object inventory, metadata của object, event log riêng hoặc quy trình batch reprocessing. Cần thiết kế từ trước cách xác định object đã xử lý và object còn thiếu.

Với HTTP webhook, nếu provider không giữ lịch sử hoặc không hỗ trợ redelivery, consumer cần lưu event envelope bền vững ngay khi nhận. Nếu provider có retry window hữu hạn, cần biết thời hạn đó và không phụ thuộc webhook provider như kho lưu trữ.

## 14. Giữ nguyên event gốc và metadata

Khi quarantine, nên giữ payload gốc bất biến để có thể xác minh và so sánh sau này. Nếu cần transform schema, lưu kết quả transform như một artifact mới, không ghi đè payload ban đầu.

Một event envelope có thể gồm:

~~~java
import java.time.Instant;
import java.util.Map;

public record EventEnvelope<T>(
        String eventId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String aggregateId,
        long sequence,
        String correlationId,
        Map<String, String> metadata,
        T payload) {

    public EventEnvelope {
        metadata = Map.copyOf(metadata);
    }
}
~~~

Envelope này là ví dụ nội bộ. Không phải nguồn nào cũng cung cấp aggregate ID hoặc sequence; các field đó cần đến từ contract của producer. Event ID phải ổn định qua retry và replay của cùng một event.

Không thêm timestamp mới vào occurredAt khi replay. Nếu cần ghi thời điểm phát lại, thêm replayedAt hoặc replayRunId trong metadata vận hành để giữ nguyên thời điểm nghiệp vụ ban đầu.

## 15. Idempotency khi redrive và replay

Replay có thể gửi lại event mà consumer đã xử lý thành công trước đó nhưng không ACK được do timeout hoặc mất kết nối. Nếu handler tạo invoice, trừ tồn kho hoặc thu tiền, xử lý trùng có thể gây hậu quả lớn.

Cần dùng idempotency key ổn định, thường dựa trên event ID và operation/version. Ví dụ:

~~~java
public record ProcessingKey(
        String eventId,
        String operationName,
        int operationVersion) {

    public String value() {
        return eventId + ":" + operationName + ":" + operationVersion;
    }
}
~~~

Khi xử lý:

1. Kiểm tra idempotency record.
2. Nếu đã COMPLETED, trả kết quả đã lưu mà không lặp side effect.
3. Nếu chưa có, claim xử lý bằng conditional write hoặc lease.
4. Thực hiện side effect theo transaction/outbox hoặc API hỗ trợ idempotency.
5. Ghi kết quả hoàn tất bền vững.
6. ACK/checkpoint sau khi trạng thái đã được lưu.

Chỉ kiểm tra key rồi ghi side effect ở hai thao tác riêng rẽ có thể tạo race condition. Hai worker cùng thấy key chưa tồn tại và cùng thực hiện side effect. Cần atomic claim, transaction hoặc cơ chế deduplication ở nơi tạo side effect.

Nếu cố ý replay để chạy một phép tính mới hoặc tạo lại một projection, có thể dùng operationVersion mới. Không thay eventId của event gốc chỉ để né idempotency; phải xác định rõ thao tác nào được phép chạy lại và side effect nào cần được bảo vệ.

## 16. Thứ tự sự kiện khi phục hồi

Không phải mọi event đều độc lập. Ví dụ OrderCreated, PaymentAuthorized và OrderCancelled có thể phải xử lý theo thứ tự nghiệp vụ.

Replay toàn bộ event theo thời gian phát lại có thể thay đổi thứ tự so với thứ tự gốc. Nhiều hệ thống phân tán cũng không bảo đảm thứ tự toàn cục giữa partition hoặc message group.

Cần:

- Xác định aggregate ID hoặc partition key.
- Ghi sequence/version ở producer nếu cần thứ tự nghiệp vụ.
- Kiểm tra sequence trước khi áp dụng event.
- Replay theo từng aggregate/partition khi có thể.
- Không trộn live traffic và replay nếu consumer không xử lý được event đến muộn.
- Có chính sách xử lý stale event và event đến sai thứ tự.
- Với FIFO queue, giữ MessageGroupId và hiểu tác động khi message bị chuyển vào DLQ.

Nếu event version 12 đã được áp dụng, replay event version 10 không nên ghi đè trạng thái mới. Consumer có thể bỏ qua event cũ, rebuild projection từ snapshot hoặc chạy quy trình reconciliation tùy domain.

## 17. Schema evolution và transform trước khi replay

Một event lỗi có thể do consumer chưa hỗ trợ schema version. Trước khi replay, cần quyết định:

- Nâng consumer để đọc schema cũ và mới.
- Transform event cũ sang schema nội bộ hiện tại.
- Chạy compatibility adapter/upcaster.
- Giữ nguyên event và xử lý bằng consumer version tương ứng.
- Loại bỏ event nếu producer phát sai contract và không thể khôi phục an toàn.

Không sửa payload gốc trong DLQ bằng tay rồi redrive mà không lưu audit. Nếu cần transform, tạo bản replay mới có nguồn gốc từ event gốc, lưu transformer version, checksum và kết quả validation.

Một consumer bền vững nên hỗ trợ backward compatibility trong khoảng thời gian replay có thể xảy ra. Nếu event có thể được phát lại sau nhiều tháng, contract và schema registry cần giữ đủ metadata để diễn giải event cũ.

## 18. Điều tiết tốc độ replay

Replay một triệu event cùng lúc có thể gây call storm tương tự fan-out không giới hạn. Trước khi replay, ước lượng:

- Số event cần phát.
- Tốc độ xử lý an toàn của consumer.
- Quota downstream.
- Traffic live đang sử dụng bao nhiêu capacity.
- Thời gian hoàn tất mong muốn.
- Chi phí invocation, queue, storage và downstream.
- Khả năng rollback hoặc pause replay.

Các biện pháp kiểm soát:

- Replay theo batch hoặc time window nhỏ.
- Dùng queue replay riêng để tách live traffic.
- Giới hạn SQS redrive rate nếu API hỗ trợ.
- Giới hạn event source mapping concurrency.
- Dùng rate limiter chia sẻ theo quota downstream.
- Bắt đầu với canary nhỏ, kiểm tra kết quả rồi tăng dần.
- Pause khi error rate, queue age, 429 hoặc p99 vượt guardrail.
- Đặt replay budget theo tenant hoặc event type.

Không phải mọi replay service có rate control tích hợp. Với EventBridge archive replay, hãy kiểm soát sức tải ở target consumer, queue hoặc downstream rate limiter; đừng giả định replay API có thể giới hạn RPS theo ý muốn.

### 18.1. Tách replay khỏi traffic mới

Một queue replay riêng có thể giúp:

- Dành concurrency riêng cho phục hồi.
- Giữ traffic mới không bị backlog replay chiếm hết.
- Theo dõi số lượng event phục hồi riêng.
- Tạm dừng replay mà không dừng consumer live.
- Điều chỉnh rate theo ưu tiên nghiệp vụ.

Nếu dùng cùng consumer code, nên dùng cùng validation và business rules nhưng cấu hình concurrency/priority khác nhau. Tránh bỏ qua các bước bảo mật chỉ vì event đến từ replay queue.

## 19. Runbook phục hồi sau sự cố

Một runbook nên có các bước có thể thực hiện và kiểm tra được:

1. **Phát hiện:** alert từ DLQ depth, event age, failure rate hoặc consumer lag.
2. **Khoanh vùng:** xác định nguồn, event type, schema version, thời gian và phạm vi tenant.
3. **Ngăn khuếch đại:** giảm concurrency, pause consumer hoặc dừng producer nếu cần.
4. **Bảo toàn dữ liệu:** xác nhận DLQ/archive/quarantine còn giữ event và metadata.
5. **Phân loại:** lỗi transient, permanent, schema, authorization hay business.
6. **Khắc phục nguyên nhân:** sửa code, policy, dependency, dữ liệu hoặc cấu hình.
7. **Xác minh:** chạy test với một nhóm event đại diện và xác nhận side effect.
8. **Lập replay plan:** xác định event IDs/time range, rate, concurrency, owner và rollback.
9. **Canary replay:** phát một lượng nhỏ và đối chiếu kết quả.
10. **Mở rộng:** tăng dần theo guardrail, theo dõi queue age và downstream.
11. **Đối soát:** so số event đủ điều kiện, thành công, duplicate, còn lỗi và bị loại.
12. **Đóng sự cố:** lưu audit, root cause, quyết định discard và bài học vận hành.

Không redrive hàng loạt trước khi xác nhận consumer đã được sửa. Nếu lỗi gốc vẫn tồn tại, DLQ có thể đầy lại rất nhanh.

## 20. Java consumer: phân loại lỗi và ghi nhận quarantine

Một lớp phân loại lỗi giúp handler quyết định retry hay quarantine:

~~~java
public enum FailureCategory {
    TRANSIENT,
    INVALID_PAYLOAD,
    UNSUPPORTED_SCHEMA,
    AUTHORIZATION,
    BUSINESS_REJECTION,
    UNKNOWN
}

public record ProcessingFailure(
        FailureCategory category,
        String errorCode,
        String safeMessage) {
}

public final class FailureClassifier {
    private FailureClassifier() {
    }

    public static boolean shouldRetry(
            ProcessingFailure failure,
            int attemptsSoFar,
            int maxAttempts) {

        if (attemptsSoFar >= maxAttempts) {
            return false;
        }

        return failure.category() == FailureCategory.TRANSIENT
                || failure.category() == FailureCategory.UNKNOWN;
    }
}
~~~

Ví dụ này chỉ minh họa quyết định cơ bản. Production cần phân loại exception theo loại dependency, status code, error code và semantics nghiệp vụ. UNKNOWN có thể retry một số lần giới hạn, sau đó quarantine; không retry vô hạn.

Khi ghi quarantine record, chỉ lưu error code và thông điệp đã làm sạch. Không lưu stack trace hoặc raw payload chứa token, password hay dữ liệu cá nhân vào nơi có quyền truy cập rộng.

Với SQS partial batch response, handler có thể báo các message ID thất bại để chỉ những message đó được giao lại. Với stream, cần dùng response format đúng với event source mapping và bật chức năng tương ứng trong cấu hình. Không dùng cùng một response contract cho mọi trigger.

## 21. Bảo mật và quyền truy cập quarantine

DLQ và archive thường chứa dữ liệu gốc, có thể nhạy cảm hơn log thông thường. Cần bảo vệ như dữ liệu production:

- Mã hóa khi lưu và truyền.
- IAM policy chỉ cho phép nhóm vận hành cần thiết đọc/quarantine/redrive.
- Tách quyền xem payload khỏi quyền khởi chạy replay.
- Audit ai đã đọc, export, sửa metadata hoặc redrive.
- Không public bucket hoặc queue.
- Hạn chế payload trong log và alert.
- Đặt retention và lifecycle phù hợp.
- Kiểm soát export dữ liệu ra môi trường local.
- Dùng KMS key policy và secret reference đúng phạm vi.

Một người có quyền redrive có thể kích hoạt lại hàng nghìn side effect. Vì vậy quyền replay là quyền vận hành có tác động lớn. Production replay có thể cần approval, change ticket hoặc giới hạn theo role.

## 22. Quan sát và đối soát quá trình phục hồi

Nên có metric riêng cho đường phục hồi:

- DLQ message count và oldest message age.
- Quarantine count theo failure category.
- Số event READY, REPLAYING, COMPLETED và FAILED.
- Replay throughput và số event còn lại.
- Retry count và redrive count.
- Duplicate/idempotency hit rate.
- Event age từ occurredAt đến processedAt.
- Downstream 429/5xx, latency và connection count.
- Số event bị discard và lý do.
- Cost trên mỗi event phục hồi thành công.

Dùng replayRunId hoặc recoveryBatchId để liên kết log/trace của một đợt phục hồi. Không dùng ID duy nhất của từng event làm metric dimension có cardinality cao; để ID trong log hoặc trace.

Đối soát cần phân biệt:

- Số event được chọn để replay.
- Số event đã được phát lại.
- Số event được consumer nhận.
- Số event xử lý thành công.
- Số event bị duplicate và bỏ qua.
- Số event vẫn lỗi hoặc bị đưa lại quarantine.

Không coi replay task hoàn tất là bằng chứng mọi business side effect đã hoàn tất. Cần kiểm tra kết quả ở hệ thống đích hoặc projection nghiệp vụ.

## 23. Những lỗi thường gặp

**Retry vô hạn poison message:** Một payload lỗi làm worker liên tục thất bại. Đặt max attempts và DLQ.

**Xem DLQ là archive lâu dài:** Message có thể hết retention. Dùng archive/event store nếu cần lịch sử dài hạn.

**Redrive ngay khi thấy DLQ:** Lỗi gốc chưa được sửa nên message quay lại DLQ. Triaging và test trước.

**Replay toàn bộ archive:** Tạo tải lớn và kích hoạt nhiều consumer không liên quan. Chọn time range, event pattern và destination rõ ràng.

**Nhầm Lambda async DLQ với SQS DLQ:** Cấu hình sai nơi retry được quản lý. Xác định trigger và semantics trước.

**Không idempotent:** Replay tạo hóa đơn, trừ kho hoặc gửi email trùng. Dùng idempotency key và atomic claim.

**Không giữ event gốc:** Không thể xác minh payload hoặc điều tra transform. Lưu payload bất biến và checksum.

**Thay eventId khi replay:** Bỏ qua deduplication và có thể lặp side effect. Giữ eventId gốc; dùng replayRunId riêng.

**Bỏ qua thứ tự:** Event cũ ghi đè trạng thái mới. Kiểm tra aggregate sequence/version và partition.

**Redrive quá nhanh:** Downstream bị quá tải lần nữa. Rate limit, canary và queue replay riêng.

**Không bảo vệ quarantine:** Payload có thể chứa PII hoặc credential. Mã hóa, giới hạn IAM và audit.

**Không đối soát:** Replay báo thành công nhưng business result vẫn thiếu. So sánh event count với trạng thái nghiệp vụ.

## 24. Checklist trước khi redrive hoặc replay

- [ ] Đã xác định đúng loại trigger và nơi quản lý retry.
- [ ] DLQ/archive/quarantine đã được cấu hình trước sự cố và còn dữ liệu.
- [ ] Payload gốc và metadata nguồn được giữ bất biến.
- [ ] Đã phân loại lỗi transient, permanent, schema và authorization.
- [ ] Nguyên nhân gốc đã được khắc phục và kiểm thử.
- [ ] Đã xác định phạm vi event ID, time window, partition hoặc tenant.
- [ ] Consumer có idempotency và xử lý duplicate an toàn.
- [ ] Có chính sách thứ tự, sequence và event đến muộn.
- [ ] Schema cũ được hỗ trợ hoặc có transform/upcaster đã kiểm chứng.
- [ ] Replay rate và worker concurrency nằm trong capacity downstream.
- [ ] Có canary, pause/stop và guardrail cho error, latency, queue age.
- [ ] Replay được tách khỏi live traffic khi cần.
- [ ] Quyền đọc payload và quyền replay được giới hạn, có audit.
- [ ] Có replayRunId/recoveryBatchId để truy vết.
- [ ] Có đối soát event được chọn, phát lại, thành công, duplicate và còn lỗi.
- [ ] Có runbook và owner chịu trách nhiệm đóng đợt phục hồi.

## Kết luận

Quarantine giữ lại event không thể xử lý an toàn; DLQ và retry kiểm soát lỗi ở queue/consumer; redrive đưa message trở lại luồng xử lý; archive hoặc stream retention cho phép replay theo phạm vi và thời gian. Mỗi dịch vụ có semantics riêng: SQS DLQ, Lambda asynchronous destinations, EventBridge archive và Kinesis/Kafka offset không thể thay thế lẫn nhau.

Trước khi phát lại, cần sửa nguyên nhân gốc, giữ event gốc, xác định thứ tự, schema và phạm vi ảnh hưởng, sau đó kiểm soát tốc độ bằng queue, concurrency cap và rate limiter. Java consumer cần idempotency key ổn định, atomic state transition và logging an toàn. Cuối cùng, đối soát kết quả nghiệp vụ và lưu audit để chứng minh quá trình phục hồi đã hoàn tất.

