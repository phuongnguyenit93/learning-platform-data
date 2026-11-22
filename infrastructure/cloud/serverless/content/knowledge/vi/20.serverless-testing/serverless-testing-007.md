# Kiểm thử batch lỗi một phần, retry và thông điệp trùng

Serverless event source thường gom nhiều record vào một batch để giảm số lần gọi function và tăng throughput. Một batch có thể chứa nhiều message độc lập, nhưng chỉ một message lỗi cũng có thể khiến cả batch được giao lại nếu function chỉ trả về thành công/thất bại ở mức invocation. Khi đó, các message đã xử lý thành công có thể bị chạy lại, tạo side effect trùng hoặc làm tăng chi phí.

Partial batch failure cho phép function báo chính xác record nào chưa xử lý thành công. Runtime có thể xác nhận các record còn lại và chỉ giao lại phần thất bại theo semantics của event source. Cơ chế này giảm công việc lặp, nhưng không biến hệ thống thành exactly-once. Message vẫn có thể được giao nhiều lần do timeout, crash, network failure, visibility timeout hoặc retry của producer. Vì vậy, consumer phải idempotent và kiểm thử cả batch response lẫn tác động nghiệp vụ.

Trong module **CLOUD_SERVERLESS**, người học xây dựng Java function kích hoạt bởi HTTP, message hoặc event, đồng thời xử lý retry, idempotency, trạng thái, mở rộng và chi phí. Bài này tập trung vào batch processing, partial batch failure, retry và message duplicate, với ví dụ AWS Lambda/SQS và phần đối chiếu Kinesis/DynamoDB Streams.

## 1. Batch processing và partial batch failure

Batch là một nhóm record được event source mapping hoặc runtime gửi đến function trong cùng một invocation. Ví dụ, một lần gọi nhận 10 message từ queue. Function xử lý từng message, sau đó trả kết quả cho runtime.

Có hai cách báo kết quả phổ biến:

- **Batch-level success/failure:** invocation thành công hoặc thất bại như một đơn vị. Nếu invocation thất bại, cả batch có thể được giao lại.
- **Partial batch response:** function trả danh sách record thất bại. Event source chỉ retry những record được chỉ định theo semantics của dịch vụ.

Ví dụ batch có 5 message:

~~~text
Batch:  [M1] [M2] [M3] [M4] [M5]
Result:  OK   OK   FAIL OK   FAIL

Batch-level failure:
         Retry M1 M2 M3 M4 M5

Partial batch response:
         Acknowledge M1 M2 M4
         Retry M3 M5
~~~

Partial batch response có ích khi record độc lập và một lỗi không nên làm lặp công việc của các record khác. Tuy nhiên, nếu các record phụ thuộc thứ tự hoặc cùng một transaction, việc xử lý riêng từng record cần được thiết kế cẩn thận.

Response contract phụ thuộc nền tảng và event source. Cấu trúc ReportBatchItemFailures trong ví dụ AWS không phải định dạng dùng chung cho Azure Functions, Google Cloud Functions hoặc mọi trigger khác; hãy dùng đúng contract của connector/runtime đang triển khai.

### Partial failure không phải cơ chế retry độc lập

Function vẫn được gọi theo batch. Partial response chỉ mô tả record nào chưa hoàn tất để event source xử lý tiếp. Nó không tự tạo retry policy, backoff, DLQ, idempotency hay transaction. Các cơ chế đó vẫn cần cấu hình và triển khai riêng.

## 2. Vì sao message bị giao nhiều lần?

Hệ thống queue và stream thường ưu tiên không làm mất event. Đổi lại, một record có thể được giao lại trong một số tình huống:

- Function đã cập nhật database nhưng crash trước khi xác nhận thành công.
- Function timeout trong khi một số record trong batch đã hoàn tất.
- Event source không nhận được response do lỗi mạng.
- Message hết visibility timeout trước khi lần xử lý cũ kết thúc.
- Producer gửi lại cùng một business event.
- Consumer bị throttling hoặc runtime restart.
- Stream checkpoint chưa tiến qua record đã xử lý.
- Một batch chứa record lỗi khiến các record trước đó bị chạy lại theo semantics của source.

Đây là lý do phải thiết kế theo **at-least-once delivery** khi dịch vụ công bố semantics đó. Không giả định một message chỉ được gọi đúng một lần.

### Phân biệt ba loại trùng lặp

| Loại trùng | Ví dụ | Cách nhận diện |
|---|---|---|
| Redelivery cùng message | Cùng một queue message được giao lại | Transport message ID, receive/dequeue count |
| Producer gửi business event trùng | Hai message khác ID nhưng cùng OrderCreated event | Stable event ID hoặc business idempotency key |
| Side effect được lặp | Hai lần trừ tiền hoặc gửi email cho cùng một order | Idempotency ledger, unique constraint, provider idempotency key |

Transport message ID hữu ích để quan sát redelivery. Nhưng nếu producer gửi cùng một business event thành hai queue message khác nhau, mỗi message có thể có ID riêng. Consumer cần stable event ID hoặc business key để nhận ra cùng một nghiệp vụ.

## 3. AWS Lambda với SQS: bật partial batch response

Với AWS Lambda và Amazon SQS, mặc định nếu function trả lỗi hoặc throw exception thì cả batch được xem là thất bại và các message có thể được giao lại. Để báo record lỗi riêng, cần bật response type:

~~~hcl
resource "aws_lambda_event_source_mapping" "orders" {
  event_source_arn = aws_sqs_queue.orders.arn
  function_name    = aws_lambda_function.orders.arn
  batch_size       = 10

  function_response_types = [
    "ReportBatchItemFailures"
  ]
}
~~~

Đây là cấu hình Terraform minh họa. Với CloudFormation/SAM hoặc CLI, cần bật cùng chức năng ReportBatchItemFailures trên event source mapping. Chỉ viết code trả danh sách lỗi mà không bật response type tương ứng sẽ không tạo ra hành vi partial acknowledgement như mong đợi.

Khi được bật, function trả một cấu trúc chứa BatchItemFailures. Mỗi phần tử chỉ định message ID cần được retry. Những message không nằm trong danh sách được xem là đã xử lý thành công.

### Java handler cho SQS

Ví dụ dùng AWS Lambda Java Events library và handler nhận cả batch:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;

import java.util.ArrayList;
import java.util.List;

public final class OrderBatchHandler
        implements RequestHandler<SQSEvent, SQSBatchResponse> {

    @Override
    public SQSBatchResponse handleRequest(
            SQSEvent event,
            Context context) {

        List<SQSBatchResponse.BatchItemFailure> failures =
                new ArrayList<>();

        for (SQSEvent.SQSMessage message : event.getRecords()) {
            try {
                processIdempotently(message);
            } catch (RetryableMessageException ex) {
                context.getLogger().warning(
                    "retryable message failure; messageId="
                    + safeId(message.getMessageId())
                );

                failures.add(
                    SQSBatchResponse.BatchItemFailure.builder()
                        .withItemIdentifier(message.getMessageId())
                        .build()
                );
            } catch (Exception ex) {
                context.getLogger().severe(
                    "unexpected message failure; messageId="
                    + safeId(message.getMessageId())
                );

                failures.add(
                    SQSBatchResponse.BatchItemFailure.builder()
                        .withItemIdentifier(message.getMessageId())
                        .build()
                );
            }
        }

        return SQSBatchResponse.builder()
                .withBatchItemFailures(failures)
                .build();
    }

    private void processIdempotently(SQSEvent.SQSMessage message) {
        // Validate, claim idempotency key, execute business operation.
    }

    private String safeId(String value) {
        if (value == null || !value.matches("[A-Za-z0-9_-]{1,128}")) {
            return "unavailable";
        }
        return value;
    }
}
~~~

Tên class và builder cần khớp phiên bản AWS Lambda Java Events dependency trong project. Ví dụ minh họa phần điều phối batch; processIdempotently phải thực hiện nghiệp vụ, transaction và idempotency thực tế.

Các điểm quan trọng:

- Dùng message ID do SQS cung cấp làm item identifier trong response.
- Chỉ thêm message vào danh sách thất bại khi chưa xử lý xong và muốn event source giao lại.
- Không thêm message đã commit nghiệp vụ thành công vào danh sách lỗi.
- Nếu handler throw exception ra ngoài, invocation-level failure có thể khiến cả batch được retry.
- Không trả response thành công rỗng khi một record chưa xử lý, vì record đó có thể bị xóa khỏi queue.
- Không log message body hoặc exception message chưa được kiểm soát.

### Phân loại lỗi trước khi trả partial response

Ví dụ trên gom lỗi chưa xử lý vào retry. Trong production nên phân biệt:

- Lỗi tạm thời: timeout, throttling, network reset, dependency 503. Thường nên retry.
- Lỗi dữ liệu vĩnh viễn: schema không hợp lệ, field bắt buộc thiếu, loại event không hỗ trợ. Có thể quarantine hoặc để DLQ nhận sau số lần thử hữu hạn.
- Lỗi cấu hình: thiếu quyền, sai endpoint, secret hết hạn. Retry liên tục thường không sửa được nguyên nhân; cần alert và xử lý cấu hình.
- Lỗi nghiệp vụ: order đã hủy hoặc trạng thái không cho phép. Có thể là kết quả hợp lệ cần ghi nhận, không nhất thiết là retry.

Nếu quyết định bỏ qua một message lỗi vĩnh viễn, phải lưu thông tin quarantine an toàn và có thể audit trước khi xác nhận message gốc. Nếu chỉ muốn dùng SQS redrive policy, tiếp tục trả message là failed cho đến khi vượt maxReceiveCount và được chuyển sang DLQ.

## 4. SQS standard và FIFO có semantics khác nhau

### Standard queue

SQS Standard ưu tiên throughput và khả năng scale. Message có thể được giao ít nhất một lần và thứ tự không được bảo đảm tuyệt đối. Partial batch response giúp một record lỗi không buộc các record độc lập khác phải chạy lại.

Nếu batch có M1 đến M5 và M3 lỗi, function có thể trả M3 trong danh sách thất bại. M1, M2, M4 và M5 được xác nhận; M3 được giao lại theo queue policy.

### FIFO queue

SQS FIFO bảo đảm thứ tự trong cùng message group, nên xử lý partial failure phải giữ nguyên thứ tự nghiệp vụ. Khi một record trong batch lỗi, không nên tiếp tục xử lý các record sau cùng group như thể record lỗi đã hoàn tất.

Một chiến lược an toàn nhất là dừng xử lý batch tại record lỗi đầu tiên và đưa record đó cùng các record chưa xử lý còn lại vào danh sách thất bại. Nếu muốn tiếp tục xử lý message group khác trong cùng batch, phải chứng minh chúng độc lập và vẫn giữ đúng thứ tự trong từng group; không tiếp tục xử lý message phía sau record lỗi trong cùng group.

~~~text
FIFO message group G1:
  M1 -> M2 -> M3(fail) -> M4 -> M5

Xử lý:
  M1, M2: success
  M3: failure
  M4, M5: chưa xử lý, phải retry cùng M3

Không xử lý M4/M5 vượt qua M3 nếu điều đó phá thứ tự.
~~~

Với FIFO, việc tiếp tục xử lý sau lỗi có thể khiến một thao tác sau được áp dụng trước thao tác trước nó. Kiểm tra kỹ message group ID và thứ tự trong batch; không áp dụng logic standard queue một cách máy móc.

## 5. Kinesis và DynamoDB Streams: checkpoint thay cho queue acknowledgement

Kinesis Data Streams và DynamoDB Streams được Lambda đọc qua event source mapping. Mỗi record có sequence number và stream shard có thứ tự. Khi bật partial batch response, function trả item identifier tương ứng sequence number của record thất bại.

Cấu hình event source mapping cần response type ReportBatchItemFailures. Ví dụ Terraform khái quát:

~~~hcl
resource "aws_lambda_event_source_mapping" "orders_stream" {
  event_source_arn  = aws_kinesis_stream.orders.arn
  function_name     = aws_lambda_function.stream_consumer.arn
  starting_position = "LATEST"
  batch_size        = 100

  function_response_types = [
    "ReportBatchItemFailures"
  ]

  maximum_retry_attempts        = 5
  maximum_record_age_in_seconds = 3600
  bisect_batch_on_function_error = true
}
~~~

Các thuộc tính retry và bisect được hỗ trợ tùy event source mapping/stream type và provider version. Hãy xác nhận schema Terraform và giới hạn của đúng loại source trước khi áp dụng. Với DynamoDB Streams, ARN và các cấu hình có thể khác; không sao chép nguyên cấu hình Kinesis nếu provider yêu cầu thuộc tính riêng.

### Java response cho stream

Với AWS Lambda Java Events, Kinesis/DynamoDB partial response dùng cấu trúc tương tự nhưng item identifier là sequence number:

~~~java
import com.amazonaws.services.lambda.runtime.events.KinesisEvent;
import com.amazonaws.services.lambda.runtime.events.StreamsEventResponse;

import java.util.ArrayList;
import java.util.List;

public StreamsEventResponse handle(KinesisEvent event) {
    List<StreamsEventResponse.BatchItemFailure> failures =
            new ArrayList<>();

    for (KinesisEvent.KinesisEventRecord record : event.getRecords()) {
        String sequenceNumber =
                record.getKinesis().getSequenceNumber();

        try {
            processStreamRecord(record);
        } catch (Exception ex) {
            failures.add(
                new StreamsEventResponse.BatchItemFailure(sequenceNumber)
            );
        }
    }

    return new StreamsEventResponse(failures);
}
~~~

Đây là ví dụ minh họa response type; xác nhận constructor/class phù hợp với phiên bản aws-lambda-java-events đang dùng. Đối với DynamoDB Streams, event record type và cách lấy sequence number khác với KinesisEvent.

Với stream, Lambda dùng sequence number thấp nhất được báo lỗi làm checkpoint cho lần retry. Các record sau checkpoint có thể được đọc lại dù lần xử lý trước đã thành công. Do đó, partial response giảm phạm vi retry so với cả batch, nhưng không loại bỏ yêu cầu idempotency cho các record sau điểm lỗi.

### Bisect batch

BisectBatchOnFunctionError cho phép Lambda chia batch lỗi thành các phần nhỏ hơn để khoanh vùng record gây lỗi. Nó có thể hữu ích khi chưa biết record nào trong batch làm handler thất bại. Kết hợp với partial batch response có thể cải thiện xử lý, nhưng cần hiểu cách checkpoint, retry attempts và record age tương tác để tránh kéo dài thời gian xử lý poison record.

## 6. Retry policy và dead-letter handling

Retry phải có giới hạn và phù hợp với loại event source. Không có một cấu hình retry duy nhất áp dụng cho tất cả queue và stream.

| Thành phần | Vai trò | Cần kiểm tra |
|---|---|---|
| Visibility timeout (SQS) | Khoảng thời gian message tạm ẩn sau khi được nhận | Đủ dài cho function, batch window và retry behavior |
| maxReceiveCount | Số lần nhận trước khi redrive | Đặt hữu hạn để poison message không quay vòng mãi |
| Dead-letter queue | Lưu message không xử lý được | Quyền đọc, retention, alert và redrive |
| MaximumRetryAttempts (stream) | Giới hạn retry record/batch theo event source mapping | Chọn theo yêu cầu không mất dữ liệu và backlog |
| MaximumRecordAgeInSeconds | Giới hạn tuổi record được retry | Tránh giữ record quá cũ vô thời hạn |
| On-failure destination | Đích lưu thông tin khi stream event thất bại theo cấu hình | Đảm bảo có thể điều tra và phục hồi |
| BisectBatchOnFunctionError | Chia nhỏ batch khi function error | Cân nhắc chi phí invocation và thời gian retry |

Với SQS Lambda event source mapping, queue visibility timeout cần được đặt đủ dài so với function timeout. AWS khuyến nghị ít nhất sáu lần function timeout; nếu có batching window, cần tính thêm thời gian đó. Nếu timeout quá ngắn, message có thể xuất hiện lại khi invocation trước vẫn đang xử lý, tạo concurrency và duplicate.

SQS redrive policy dùng maxReceiveCount để chuyển message sang DLQ sau số lần nhận thất bại. DLQ cần alarm theo số message và tuổi message. Không chỉ tạo DLQ rồi quên theo dõi.

### Backoff và retry storm

Khi dependency gặp sự cố, nhiều function có thể retry đồng thời và tạo retry storm. Dùng exponential backoff, jitter và giới hạn số lần thử ở tầng ứng dụng khi phù hợp. Với retry do event source quản lý, hiểu rõ cơ chế visibility, polling và scaling của provider để không chồng thêm retry loop vô hạn bên trong handler.

Không retry lỗi vĩnh viễn như schema sai hoặc permission denied mãi mãi. Phân loại lỗi và đưa poison message vào quarantine/DLQ để điều tra.

## 7. Idempotency: lớp bảo vệ bắt buộc cho consumer

Idempotency nghĩa là xử lý cùng một business operation nhiều lần nhưng chỉ tạo một hiệu ứng nghiệp vụ được chấp nhận. Đây là biện pháp bảo vệ khi duplicate delivery xảy ra.

### Chọn idempotency key

Ưu tiên một key ổn định do producer tạo, ví dụ event ID hoặc operation ID. Nếu không có, có thể xây dựng từ business key và loại operation, nhưng phải bảo đảm hai event hợp lệ khác nhau không bị gộp nhầm.

Ví dụ:

~~~text
idempotency_key = tenant_id + ":" + event_type + ":" + event_id
~~~

Không dùng payload hash tùy tiện nếu payload có thể thay đổi thứ tự field, timestamp hoặc metadata. Cũng không dùng chỉ SQS message ID khi producer có thể gửi lại cùng event thành một message mới với ID khác.

### Inbox/idempotency table

Một bảng lưu event đã xử lý có thể gồm:

| Field | Mục đích |
|---|---|
| idempotency_key | Unique key của business operation |
| status | PROCESSING, COMPLETED hoặc FAILED |
| result_ref | Tham chiếu kết quả đã tạo |
| first_seen_at | Thời điểm nhận lần đầu |
| completed_at | Thời điểm hoàn tất |
| attempt_count | Số lần ứng dụng quan sát |
| expires_at | Thời điểm hết hạn record deduplication |

Tạo unique constraint trên idempotency_key. Khi message được giao lại, consumer kiểm tra key:

- Đã COMPLETED: trả success mà không lặp side effect.
- Đang PROCESSING: xử lý theo chính sách lease/lock; tránh hai invocation cùng làm một việc.
- Chưa tồn tại: claim key và thực hiện nghiệp vụ.
- FAILED: xác định lỗi có thể retry hay cần can thiệp.

Retention của idempotency record phải dài hơn khoảng thời gian message có thể được redrive hoặc replay. Nếu xóa key quá sớm, một message cũ được phát lại có thể thực hiện side effect lần nữa.

### Transaction cho database side effect

Nếu business update và idempotency record cùng nằm trong một database, thực hiện chúng trong cùng transaction:

~~~java
@Transactional
public void handle(OrderCreated event) {
    boolean firstDelivery =
            inboxRepository.insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        // Chỉ acknowledge nếu invariant bảo đảm row đã tồn tại nghĩa là COMPLETED.
        // Nếu row có thể đang PROCESSING/FAILED, phải đọc trạng thái và quyết định retry.
        return;
    }

    orderRepository.markCreated(event.orderId());
    inboxRepository.markCompleted(event.eventId());
}
~~~

Đây là pseudocode: insertIfAbsent phải dựa trên unique constraint và transaction isolation phù hợp. Trong mô hình một transaction duy nhất, chỉ commit inbox row cùng business update và COMPLETED; transaction rollback thì cả inbox insert và business update rollback cùng nhau. Nếu event được claim ở transaction riêng với trạng thái PROCESSING, duplicate không được tự động acknowledge: cần đọc trạng thái, lease/timeout và cơ chế phục hồi claim bị bỏ dở.

Không chỉ kiểm tra bằng một SELECT rồi mới INSERT. Hai invocation đồng thời có thể cùng thấy key chưa tồn tại và cùng thực hiện nghiệp vụ. Dùng unique constraint, atomic insert hoặc conditional write.

## 8. External side effect và transactional outbox

Một transaction database không thể tự động bao trùm API payment provider, email service hoặc hệ thống bên ngoài. Nếu gọi provider thành công rồi function crash trước khi đánh dấu COMPLETED, lần retry có thể gọi provider lần nữa.

Các lựa chọn:

- Truyền idempotency key ổn định đến provider nếu API hỗ trợ.
- Dùng transactional outbox để commit business state và event cần gửi trong cùng database transaction.
- Một dispatcher đọc outbox và gửi event; dispatcher cũng phải idempotent.
- Lưu provider operation reference để reconciliation khi response bị mất.
- Dùng workflow/durable orchestration khi quy trình nhiều bước cần trạng thái bền vững.

Luồng outbox:

~~~mermaid
sequenceDiagram
    participant C as Queue consumer
    participant DB as Database
    participant O as Outbox dispatcher
    participant P as External provider

    C->>DB: Transaction: inbox + business update + outbox
    DB-->>C: Commit
    C-->>C: Acknowledge message
    O->>DB: Read pending outbox event
    O->>P: Call with stable idempotency key
    P-->>O: Result / provider reference
    O->>DB: Mark outbox delivered
~~~

Nếu dispatcher crash sau khi provider đã xử lý nhưng trước khi đánh dấu delivered, nó sẽ gửi lại. Idempotency key ở provider hoặc reconciliation bằng provider reference giúp tránh lặp side effect.

## 9. Xử lý batch có record phụ thuộc nhau

Partial batch response phù hợp nhất khi mỗi record có thể xử lý độc lập. Nếu record B phụ thuộc kết quả record A, việc xử lý song song hoặc xác nhận A trong khi B lỗi có thể làm sai thứ tự nghiệp vụ.

Cần xác định:

- Các record có cùng aggregate/order/customer không?
- Có yêu cầu thứ tự theo message group hoặc partition key không?
- Có thể commit từng record độc lập không?
- Có transaction bao trùm cả batch không?
- Nếu một record lỗi, record sau có được phép chạy không?
- Khi retry, record thành công trước đó có thể bị chạy lại không?

Nếu cả batch là một transaction logic, có thể cần xử lý tất cả trong transaction và chỉ xác nhận toàn batch khi commit. Nếu record độc lập, xử lý và commit riêng từng record để partial response có ý nghĩa.

Đối với SQS FIFO, giữ thứ tự theo message group. Đối với stream, tôn trọng shard/partition ordering và checkpoint. Không tăng concurrency chỉ để tối đa throughput nếu điều đó phá thứ tự hoặc aggregate consistency.

## 10. Timeout, batch size và concurrency

Batch size lớn giảm số invocation nhưng tăng thời gian xử lý một batch, memory sử dụng và phạm vi ảnh hưởng khi lỗi. Batch size nhỏ tăng overhead nhưng giới hạn số record bị ảnh hưởng trong một lần gọi.

| Tham số | Tăng lên có thể mang lại | Rủi ro cần kiểm tra |
|---|---|---|
| Batch size | Ít invocation hơn, throughput cao hơn | Memory, duration, partial failure complexity |
| Maximum batching window | Gom được nhiều record hơn | Tăng latency trước khi xử lý |
| Function timeout | Cho phép batch xử lý lâu hơn | Tăng thời gian giữ message và chi phí |
| Event source concurrency | Nhiều batch song song hơn | Downstream overload, ordering và duplicate |
| Visibility timeout | Giảm khả năng message hiện lại sớm | Tăng thời gian chờ retry khi function crash |
| Max receive count | Có thêm cơ hội xử lý thành công | Poison message tồn tại lâu hơn |

Chọn batch size từ benchmark và giới hạn downstream. Một batch có 10 record nhưng mỗi record gọi database nhiều lần có thể tạo tải lớn hơn dự kiến. Đo p95/p99 duration, memory, số connection, error rate và backlog.

## 11. Quan sát partial failure và duplicate

Invocation có thể được xem là thành công ở mức Lambda vì handler đã trả partial response hợp lệ, dù một vài record bị đánh dấu failed. Do đó, chỉ theo dõi metric invocation Errors có thể bỏ sót record-level failure.

Nên tạo metric và log có cấu trúc cho từng kết quả:

- Batch records received.
- Records succeeded.
- Records failed retryable.
- Records quarantined/permanent.
- Duplicate detected.
- Idempotency conflict hoặc operation already completed.
- Retry attempt count.
- DLQ ingress và backlog.
- Age of oldest message/record.
- Processing duration theo event type.

Với SQS, theo dõi ApproximateAgeOfOldestMessage, ApproximateNumberOfMessagesVisible, DLQ depth, Lambda Duration, Throttles và custom record failure metrics. Với Kinesis/DynamoDB Streams, theo dõi IteratorAge, retry, throughput và shard-level lag.

Không đưa raw payload, email hoặc token vào metric dimension. Dùng event type, error code, queue name, function name và status class có cardinality giới hạn.

## 12. Kiểm thử partial batch response

Kiểm thử cần xác nhận cả response kỹ thuật lẫn hiệu ứng nghiệp vụ. Một handler có thể trả đúng message ID thất bại nhưng vẫn commit side effect sai hoặc lặp.

### Unit test cho handler

Dùng batch giả lập có:

- Tất cả record thành công.
- Một record lỗi tạm thời ở đầu, giữa và cuối batch.
- Nhiều record lỗi.
- Message không hợp lệ.
- Duplicate event ID trong cùng batch.
- Record đã hoàn tất từ invocation trước.
- Exception không dự kiến.

Xác nhận response chỉ chứa đúng message ID/sequence number cần retry. Đồng thời kiểm tra service nghiệp vụ chỉ được gọi đúng số lần theo idempotency.

### Integration test với event source

Cần kiểm thử trong môi trường có semantics gần thực tế:

1. Tạo queue/stream test và event source mapping với partial response enabled.
2. Gửi batch có nhiều message.
3. Cho một record thất bại có chủ đích.
4. Xác nhận record thành công không bị giao lại ngoài dự kiến.
5. Xác nhận record thất bại được giao lại.
6. Gửi cùng business event hai lần với transport ID khác nhau.
7. Xác nhận idempotency chặn side effect trùng.
8. Làm function timeout/crash ở các điểm trước và sau commit.
9. Kiểm tra DLQ/quarantine sau số lần retry.
10. Đo backlog và downstream concurrency khi có burst.

Local emulator có thể hữu ích cho vòng lặp phát triển, nhưng không nên giả định mô phỏng hoàn toàn visibility timeout, scaling, ordering, retry và checkpoint của cloud provider. Chạy integration test trên account/stack thử nghiệm trước khi phát hành.

## 13. Test matrix cho batch, retry và duplicate

| Tình huống | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Batch thành công | Tất cả record hợp lệ | Không có record failure; side effect một lần |
| Một record lỗi tạm thời | Một message timeout, các message khác thành công | Chỉ message lỗi được retry nếu partial response đúng |
| Nhiều record lỗi | Hai record độc lập lỗi | Response liệt kê đúng cả hai |
| Function throw ngoài handler | Invocation-level exception | Toàn batch có thể retry; idempotency bảo vệ side effect |
| Crash sau DB commit | Message chưa được acknowledge | Redelivery không lặp cập nhật DB |
| Duplicate cùng batch | Hai message cùng business event ID | Chỉ một business operation được commit |
| Duplicate khác batch | Cùng event được gửi lại sau đó | Inbox/unique key nhận ra event đã hoàn tất |
| Dependency throttling | Downstream trả 429/503 | Retry hữu hạn, backoff, không tạo retry storm |
| Poison message | Dữ liệu không thể xử lý | Quarantine hoặc DLQ sau chính sách hữu hạn |
| FIFO record lỗi | Một record trong message group thất bại | Dừng phần sau theo thứ tự; retry record lỗi và phần chưa xử lý |
| Stream checkpoint | Record giữa batch lỗi | Retry từ checkpoint thấp nhất; record sau có thể chạy lại |
| Visibility timeout quá ngắn | Invocation lâu hơn visibility | Test phát hiện redelivery/concurrent duplicate |
| DLQ redrive | Replay message đã xử lý trước đó | Idempotency ngăn side effect lặp |
| Batch lớn | Nhiều record và dependency chậm | Memory/duration/concurrency nằm trong giới hạn |

## 14. Ví dụ kiểm thử idempotency

Một test minh họa cho cùng event được giao hai lần:

~~~java
@Test
void duplicateEventDoesNotCreateSecondOrder() {
    OrderCreated event = new OrderCreated("evt-1001", "order-42");

    handler.process(event);
    handler.process(event);

    assertEquals(1, orderRepository.countByOrderId("order-42"));
    assertEquals(1, inboxRepository.countByEventId("evt-1001"));
}
~~~

Test này cần database hoặc repository test double có unique constraint semantics phù hợp. Một mock chỉ đếm số lần gọi method không chứng minh tính nguyên tử khi có hai invocation song song.

Cũng cần test race condition:

~~~java
@Test
void concurrentDuplicateDeliveryCommitsOnce() {
    // Chạy hai consumer đồng thời với cùng event ID.
    // Xác nhận unique constraint/conditional write chỉ cho một consumer claim.
    // Xác nhận business side effect chỉ commit một lần.
}
~~~

Kiểm thử concurrency nên dùng database thật hoặc container test phù hợp để xác nhận transaction isolation, unique constraint và conditional write.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Quên bật ReportBatchItemFailures | Runtime coi response như batch success/failure thông thường | Kiểm tra event source mapping cùng code |
| Trả response rỗng dù record chưa xử lý | Message có thể bị xác nhận và mất cơ hội retry | Chỉ ack record sau khi hoàn tất/quarantine bền vững |
| Throw exception sau khi đã xử lý một số record | Cả batch có thể retry | Catch lỗi theo record và trả partial response khi phù hợp |
| Dùng SQS message ID làm business idempotency key duy nhất | Producer gửi event trùng thành message ID mới | Stable event ID/business key |
| Không có unique constraint | Hai invocation đồng thời cùng xử lý một event | Atomic insert/conditional write |
| Gọi external API trước khi ghi idempotency | Retry có thể tạo side effect lặp | Provider idempotency key hoặc outbox/reconciliation |
| FIFO tiếp tục xử lý sau record lỗi | Phá thứ tự nghiệp vụ | Dừng tại lỗi đầu tiên trong group và báo phần chưa xử lý |
| Không tính stream checkpoint | Record sau checkpoint bị chạy lại | Idempotent consumer và test sequence number |
| Visibility timeout quá ngắn | Message hiện lại khi invocation cũ còn chạy | Đặt timeout theo function duration và batch window |
| Không có DLQ/quarantine | Poison message retry vô hạn hoặc bị bỏ quên | Redrive policy, alert và runbook |
| Retry mọi lỗi giống nhau | Lãng phí invocation và làm outage kéo dài | Phân loại transient/permanent/configuration |
| Chỉ xem Lambda Errors | Bỏ sót partial record failures | Custom metrics cho từng record |
| Log raw body khi retry | Nhân bản dữ liệu nhạy cảm | Log event reference và error code |
| Batch size quá lớn | Tăng memory, timeout và blast radius | Benchmark và giới hạn batch/concurrency |

## 16. Quy trình thiết kế và vận hành

Khi triển khai một batch consumer:

1. **Chọn event source:** xác định queue hay stream, ordering và delivery semantics.
2. **Xác định batch boundary:** record có độc lập không, có transaction chung không?
3. **Bật partial response:** cấu hình event source mapping và response schema đúng provider.
4. **Phân loại lỗi:** transient, permanent, configuration và business outcome.
5. **Thiết kế idempotency:** stable event ID, unique constraint và transaction.
6. **Bảo vệ external side effect:** provider idempotency key, outbox hoặc reconciliation.
7. **Cấu hình retry:** visibility timeout, max receive/retry attempts, DLQ và record age.
8. **Giới hạn tải:** batch size, batching window, concurrency và downstream capacity.
9. **Kiểm thử:** partial failures, duplicate, crash, timeout, FIFO order và stream checkpoint.
10. **Quan sát:** custom record failure metrics, backlog, oldest age, iterator lag và duplicate rate.
11. **Chuẩn bị phục hồi:** runbook DLQ inspection, redrive, poison message và replay.
12. **Đánh giá sau triển khai:** theo dõi throughput, latency, cost và tỷ lệ retry để điều chỉnh.

## 17. Kết luận

Partial batch failure giúp function chỉ yêu cầu retry những record chưa xử lý thành công, giảm công việc lặp khi một batch có nhiều record độc lập. Nhưng semantics phụ thuộc event source: SQS dùng message ID và acknowledgement/visibility; FIFO cần giữ thứ tự; Kinesis và DynamoDB Streams dùng sequence number và checkpoint, nên record sau điểm lỗi có thể được xử lý lại.

Retry và duplicate là hành vi bình thường của hệ thống phân tán. Consumer cần stable idempotency key, unique constraint hoặc conditional write, transaction cho database side effect và provider idempotency/outbox cho external side effect. Kiểm thử phải bao gồm partial response, crash sau commit, duplicate đồng thời, poison message, DLQ redrive, ordering và checkpoint. Theo dõi record-level failure bên cạnh invocation metrics để biết batch đang thực sự hoạt động ra sao.

Khi partial acknowledgement, retry policy, idempotency và observability được thiết kế cùng nhau, Java function có thể xử lý batch hiệu quả mà không đánh đổi tính đúng đắn của nghiệp vụ khi message bị giao lại.
