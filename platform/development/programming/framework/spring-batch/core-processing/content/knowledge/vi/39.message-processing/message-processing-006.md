# Message key và correlation

Trong hệ thống xử lý message kết hợp Spring Batch, một message thường mang nhiều định danh khác nhau. Có định danh dùng để chọn partition hoặc queue, có định danh dùng để nhận diện message duy nhất, có khóa nghiệp vụ đại diện cho đối tượng đang xử lý và có correlation ID để liên kết nhiều message thuộc cùng một luồng công việc. Những giá trị này có thể trùng nhau trong một thiết kế đơn giản, nhưng chúng giải quyết các bài toán khác nhau.

Phân biệt đúng message key và correlation giúp hệ thống định tuyến message ổn định, giữ thứ tự khi cần, chống xử lý trùng, theo dõi một business workflow qua nhiều service và liên kết message với JobExecution của Spring Batch. Nếu dùng nhầm một ID làm tất cả, hệ thống có thể phân vùng dữ liệu sai, mất khả năng truy vết hoặc tạo duplicate khi broker gửi lại message.

## 1. Các loại định danh trong message processing

Một message có thể chứa các trường định danh sau:

| Định danh | Mục đích | Ví dụ |
|---|---|---|
| Message ID | Nhận diện một message cụ thể | msg-8f21 |
| Message key | Định tuyến, partition hoặc xác định nhóm message theo semantics của broker | customer-1042 |
| Business key | Nhận diện thực thể nghiệp vụ | customerId, orderId |
| Idempotency key | Nhận diện một thao tác để chống thực hiện lặp | payment-command-9001 |
| Correlation ID | Liên kết nhiều message thuộc cùng một workflow/request | corr-import-2026-11-15 |
| Causation ID | Cho biết message hiện tại được tạo ra bởi message nào | msg-8f21 |
| Batch ID | Nhận diện một lô dữ liệu hoặc lần import | batch-customer-20261115 |
| JobExecution ID | Nhận diện một lần thực thi Job trong Spring Batch | ID do JobRepository cấp |

Các khái niệm trên có thể được biểu diễn trong message headers, payload, broker metadata hoặc bảng inbox/outbox. Cần ghi rõ contract của hệ thống: field nào là bắt buộc, ai tạo, phạm vi duy nhất và thời gian lưu giữ.

## 2. Message key là gì?

Message key là một giá trị gắn với message để broker hoặc ứng dụng xác định cách định tuyến, phân vùng, nhóm hoặc xử lý message. Ý nghĩa cụ thể phụ thuộc middleware.

Ví dụ, trong Apache Kafka, record key thường được dùng bởi partitioner để chọn partition. Các record cùng key thường được gửi tới cùng partition theo partitioning strategy, nhờ đó Kafka có thể giữ thứ tự của chúng trong partition. Key không nhất thiết là ID duy nhất của từng message; nhiều record khác nhau có thể có cùng key.

Trong một hệ thống JMS, khái niệm message key không có semantics partition giống Kafka. Ứng dụng có thể dùng một property trong message để định tuyến hoặc tìm kiếm, trong khi JMSMessageID và JMSCorrelationID là các header có ý nghĩa riêng.

Vì vậy, không nên áp dụng quy tắc Kafka key cho mọi broker. Hãy xem key là một phần của contract middleware cụ thể và mô tả rõ broker sử dụng nó như thế nào.

## 3. Correlation ID là gì?

Correlation ID là định danh dùng để liên kết các message có liên quan trong cùng một request, business transaction hoặc workflow phân tán. Một correlation ID thường được tạo ở điểm bắt đầu luồng và được truyền qua các service hoặc message tiếp theo.

Ví dụ, một file import tạo ra nhiều message cho từng customer:

~~~text
Import request
  correlationId = corr-20261115-01
       |
       +--> Customer message 1
       |      messageId = msg-001
       |      customerId = C-001
       |
       +--> Customer message 2
       |      messageId = msg-002
       |      customerId = C-002
       |
       +--> Customer message 3
              messageId = msg-003
              customerId = C-003
~~~

Mỗi message có message ID riêng, nhưng chúng cùng correlation ID vì thuộc một lần import. Nhờ vậy, log, trace, audit và kết quả xử lý có thể được nhóm theo workflow.

Correlation ID không nhất thiết là khóa duy nhất của message hoặc khóa phân vùng. Nó có thể có cardinality rất lớn, đại diện cho một request, một file hoặc một workflow. Nếu dùng correlation ID làm Kafka key, tất cả message của workflow có thể đi vào cùng partition; điều này có thể hữu ích cho ordering nhưng cũng có thể tạo hot partition nếu workflow có lượng message lớn.

## 4. Phân biệt message key, message ID và correlation ID

Các định danh thường được dùng cùng nhau:

~~~text
Message:
  messageId       = msg-001
  key             = customer-C001
  correlationId   = corr-import-01
  causationId     = msg-import-start
  businessKey     = C-001
  idempotencyKey  = import-01-C001
~~~

| Câu hỏi | Field phù hợp |
|---|---|
| Đây là message cụ thể nào? | Message ID |
| Broker nên route/partition theo giá trị nào? | Message key theo broker semantics |
| Message thuộc workflow nào? | Correlation ID |
| Message nào đã tạo ra message này? | Causation ID |
| Thực thể nghiệp vụ nào được tác động? | Business key |
| Thao tác này đã được thực hiện chưa? | Idempotency key |

Một message ID mới có thể được tạo mỗi lần producer gửi lại cùng một business command. Vì vậy, message ID không phải lúc nào cũng đủ để chống duplicate. Idempotency key cần ổn định qua retry của cùng một thao tác nghiệp vụ.

## 5. Kafka record key và partitioning

Trong Kafka, producer có thể gửi record với key và value:

~~~java
ProducerRecord<String, CustomerEvent> record =
        new ProducerRecord<>(
                "customer-events",
                customerEvent.customerId(),
                customerEvent);

kafkaTemplate.send(record);
~~~

Với key là customerId, record của cùng customer thường được route tới cùng partition khi partitioner và số partition không thay đổi theo cách làm thay đổi mapping. Điều này giúp consumer xử lý các event của cùng customer theo thứ tự trong một partition.

Kafka key không tự đảm bảo thứ tự toàn cục giữa các partition. Nếu hai customer nằm ở hai partition khác nhau, không có thứ tự chung được đảm bảo giữa hai luồng đó.

Thay đổi số partition có thể làm key được map sang partition khác trong tương lai, tùy partitioner. Vì vậy, nếu ứng dụng phụ thuộc vào ordering lâu dài theo key, cần tính đến chiến lược partition expansion và migration.

Không dùng correlation ID làm key một cách tự động. Hãy chọn key theo entity hoặc aggregate mà các event cần được xử lý tuần tự. Ví dụ:

- Customer events: customerId.
- Order lifecycle: orderId.
- Account ledger: accountId.
- File import progress: batchId chỉ khi toàn bộ batch cần cùng partition và throughput cho phép.

## 6. JMS message ID và JMSCorrelationID

Trong JMS, provider thường gán JMSMessageID để nhận diện message đã gửi. JMSCorrelationID được dùng để liên kết message với một message khác hoặc một request/reply exchange.

Một request/reply pattern có thể hoạt động như sau:

~~~text
Requester
   |
   | Request
   | JMSMessageID = ID-REQ-01
   v
Request Queue
   |
   v
Worker
   |
   | Reply
   | JMSCorrelationID = ID-REQ-01
   v
Reply Queue
   |
   v
Requester matches reply to request
~~~

Trong mẫu này, reply đặt correlation ID bằng message ID của request để requester tìm đúng kết quả. Một số hệ thống sử dụng application-generated correlation ID thay vì JMSMessageID; điều quan trọng là hai phía thống nhất contract.

JMSCorrelationID không phải message ID của reply và cũng không phải business key. Nó liên kết reply với request. Với workflow có nhiều bước, application correlation ID có thể được giữ xuyên suốt nhiều message, trong khi mỗi message vẫn có JMSMessageID riêng.

## 7. Correlation trong Spring Messaging

Spring Messaging biểu diễn message bằng payload và headers. Ứng dụng có thể truyền correlation ID như một header:

~~~java
Message<CustomerEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader("correlationId", correlationId)
        .setHeader("messageKey", event.customerId())
        .setHeader("causationId", sourceMessageId)
        .build();
~~~

Header names trong ví dụ là application-defined. Broker adapter có thể ánh xạ một số header sang native broker properties, nhưng không nên giả định mọi header tùy chỉnh đều được truyền qua broker mà không cấu hình. Kiểm tra mapping của adapter và message converter đang dùng.

Có thể dùng constant để tránh typo:

~~~java
public final class MessageHeaders {
    public static final String CORRELATION_ID = "correlationId";
    public static final String MESSAGE_KEY = "messageKey";
    public static final String CAUSATION_ID = "causationId";

    private MessageHeaders() {
    }
}
~~~

Trong ứng dụng lớn, nên có một envelope hoặc metadata object có schema rõ ràng thay vì để mỗi producer tự đặt tên header.

## 8. Truyền correlation ID xuyên suốt workflow

Correlation ID nên được tạo tại điểm bắt đầu luồng nếu request chưa có ID đáng tin cậy. Mỗi service nhận message cần giữ correlation ID khi tạo message tiếp theo.

~~~text
API request
   |
   v
Order Service
   | correlationId = corr-123
   v
OrderCreated event
   |
   v
Inventory Service
   | correlationId = corr-123
   v
InventoryReserved event
   |
   v
Billing Service
   | correlationId = corr-123
   v
PaymentRequested event
~~~

Nếu một service tạo workflow con độc lập, có thể tạo correlation ID mới và giữ correlation ID cha trong một header riêng. Không ghi đè correlation ID của workflow cha nếu cần truy vết quan hệ giữa các workflow.

Correlation ID nên được truyền qua:

- Message headers hoặc envelope.
- Log context.
- Distributed tracing context.
- Audit record.
- JobParameters/ExecutionContext khi message khởi chạy batch.
- Outbox/inbox record nếu có lưu bền vững.

Không tạo correlation ID mới ở mỗi bước nếu mục tiêu là theo dõi cùng một workflow. Nếu cần trace span riêng, dùng trace/span ID của tracing system và giữ correlation ID nghiệp vụ riêng.

## 9. Causation ID và quan hệ cha-con

Correlation ID cho biết các message thuộc cùng một workflow; causation ID cho biết message hiện tại được tạo bởi message nào.

Ví dụ:

~~~text
Message A: OrderCreated
  messageId = A
  correlationId = ORDER-FLOW-1

Message B: InventoryReserved
  messageId = B
  correlationId = ORDER-FLOW-1
  causationId = A

Message C: PaymentRequested
  messageId = C
  correlationId = ORDER-FLOW-1
  causationId = B
~~~

Correlation ID giúp truy vấn toàn bộ workflow. Causation ID giúp dựng chuỗi nguyên nhân. Hai field bổ sung cho nhau khi phân tích lỗi hoặc audit.

Nếu một message được tạo bởi nhiều input message (ví dụ aggregator), một causation ID đơn có thể không đủ. Có thể lưu danh sách parent message IDs trong metadata hoặc bảng quan hệ, với giới hạn kích thước và retention phù hợp.

## 10. Kết hợp message với Spring Batch Job

Một message có thể yêu cầu Spring Batch xử lý một file, một customer range hoặc một batch dữ liệu. Khi consumer nhận message, ứng dụng có thể chuyển metadata của message thành JobParameters.

Ví dụ:

~~~java
@Service
public class ImportJobLauncher {

    private final JobLauncher jobLauncher;
    private final Job customerImportJob;

    public ImportJobLauncher(
            JobLauncher jobLauncher,
            Job customerImportJob) {
        this.jobLauncher = jobLauncher;
        this.customerImportJob = customerImportJob;
    }

    public JobExecution launch(ImportRequest request) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchId", request.batchId(), true)
                .addString("inputUri", request.inputUri(), true)
                .addString("correlationId", request.correlationId(), false)
                .toJobParameters();

        return jobLauncher.run(customerImportJob, parameters);
    }
}
~~~

Ví dụ này dùng batchId và inputUri làm identifying parameters, còn correlationId là non-identifying metadata. Lựa chọn identifying/non-identifying phải phù hợp với semantics JobInstance.

Nếu cùng một batch được gửi lại, dùng cùng identifying parameters có thể khiến Spring Batch tìm lại JobInstance tương ứng và áp dụng quy tắc restart/already-complete. Nếu mỗi message là một yêu cầu import độc lập, cần một business batch ID riêng hoặc một identifying request ID phù hợp.

Không dùng correlation ID làm identifying parameter chỉ vì nó có mặt trong message. Một correlation ID có thể gom nhiều message hoặc nhiều batch; nếu dùng nó làm identity, các Job có thể vô tình đụng cùng JobInstance.

## 11. JobParameters và JobInstance identity

Spring Batch phân biệt JobInstance bằng Job name và identifying JobParameters. JobExecution là một lần thực thi của JobInstance. Một JobInstance có thể có nhiều JobExecution nếu lần trước thất bại và được restart.

Điều này quan trọng với message redelivery:

- Nếu message đại diện cho cùng một batch operation, identifying parameters cần ổn định qua redelivery.
- Nếu message đại diện cho một yêu cầu mới, cần identity mới.
- Correlation ID chỉ liên kết workflow, không nhất thiết là identity của batch.
- Message ID có thể thay đổi khi producer gửi lại, nên không phải lúc nào cũng là idempotency key.

Ví dụ:

~~~text
Message delivery 1:
  messageId = msg-A
  batchId = BATCH-900
  correlationId = FLOW-1

Message delivery 2 (redelivery):
  messageId = msg-A hoặc provider-specific redelivery identity
  batchId = BATCH-900
  correlationId = FLOW-1

Spring Batch:
  JobInstance = customerImportJob + batchId + inputUri
  JobExecution 1 = FAILED
  JobExecution 2 = RESTARTED
~~~

Không thêm timestamp ngẫu nhiên vào identifying parameters khi retry cùng message, vì điều đó tạo JobInstance mới thay vì restart instance cũ.

## 12. Idempotency key và chống xử lý message trùng

Message broker thường có thể giao lại message, đặc biệt khi consumer xử lý xong nhưng chưa acknowledge hoặc mất kết nối trước khi broker ghi nhận acknowledgment. Vì vậy, ứng dụng cần giả định có thể nhận cùng message nhiều lần.

Idempotency key đại diện cho một thao tác nghiệp vụ ổn định qua redelivery. Ví dụ:

~~~text
messageId       = msg-7781
businessKey     = order-900
idempotencyKey  = capture-payment-order-900
correlationId   = checkout-flow-900
~~~

Nếu producer retry tạo một message ID mới cho cùng thao tác capture payment, idempotency key vẫn cần giữ nguyên. Consumer có thể dùng unique constraint trên idempotency key để bảo đảm chỉ một thao tác được áp dụng.

Ví dụ bảng inbox:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    message_id VARCHAR(200),
    correlation_id VARCHAR(200),
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, idempotency_key)
);
~~~

Trong cùng transaction database, consumer ghi inbox key và thay đổi dữ liệu nghiệp vụ. Nếu key đã tồn tại, message được nhận diện là đã xử lý và có thể acknowledge mà không lặp side effect.

Chỉ lưu processed marker sau khi side effect nghiệp vụ đã commit cùng transaction. Nếu marker commit trước còn nghiệp vụ thất bại, message có thể bị coi là đã xử lý dù dữ liệu chưa được cập nhật. Nếu nghiệp vụ commit trước nhưng marker thất bại, redelivery có thể lặp side effect. Inbox và business update nên cùng transaction khi cùng database.

## 13. Message key không thay thế idempotency key

Kafka key thường được dùng để partition record. Nó không đảm bảo message chỉ được giao một lần và không phải lúc nào cũng duy nhất cho từng thao tác.

Ví dụ, tất cả event của customer C-001 có thể dùng cùng Kafka key:

~~~text
key=C-001, value=CustomerCreated
key=C-001, value=CustomerAddressChanged
key=C-001, value=CustomerStatusChanged
~~~

Ba record có cùng key nhưng là ba thao tác khác nhau. Nếu dùng key làm idempotency key, consumer có thể loại nhầm các event hợp lệ sau event đầu tiên.

Ngược lại, hai message có key khác nhau vẫn có thể đại diện cho cùng một thao tác nghiệp vụ nếu producer tạo key không ổn định. Idempotency cần một định danh thao tác riêng, có quy tắc tạo và retention rõ ràng.

## 14. Inbox pattern cho consumer

Inbox pattern lưu message đã tiếp nhận/xử lý để phát hiện redelivery và hỗ trợ audit. Một flow điển hình:

~~~text
Broker message
     |
     v
Consumer
     |
     v
Begin database transaction
     |
     +--> Insert inbox idempotency key
     |
     +--> Apply business update
     |
     +--> Store correlation/causation metadata
     |
     v
Commit
     |
     v
Acknowledge broker message
~~~

Nếu insert inbox key vi phạm unique constraint, consumer biết thao tác đã được xử lý trước đó. Cần xác định trạng thái marker: RECEIVED, PROCESSING, COMPLETED hay FAILED. Một marker RECEIVED không đồng nghĩa business operation đã hoàn tất.

Với xử lý dài bằng Spring Batch, consumer có thể tạo một batch request record bền vững rồi launch Job. Bảng request cần có unique key theo batch operation để redelivery không launch một batch độc lập ngoài ý muốn.

Không giữ database transaction mở trong suốt một Job dài chỉ để bao quanh broker acknowledgment. Thay vào đó, ghi nhận yêu cầu và trạng thái launch trong transaction ngắn, sau đó Job quản lý chunk transaction riêng.

## 15. Outbox pattern khi phát message từ batch

Nếu Spring Batch cập nhật database rồi publish event trực tiếp tới broker, có thể xảy ra dual-write problem:

- Database commit thành công nhưng publish thất bại.
- Publish thành công nhưng database transaction rollback.

Outbox pattern ghi event vào bảng outbox trong cùng transaction với business update. Một publisher riêng đọc outbox và gửi message tới broker:

~~~text
Spring Batch chunk transaction
     |
     +--> Update business table
     |
     +--> Insert outbox event
     |
     v
   Commit

Outbox publisher
     |
     v
   Broker
~~~

Outbox record nên lưu message ID, message key, correlation ID, causation ID, event type, payload và created timestamp. Publisher cần idempotency/retry vì có thể gửi lại event nếu crash sau khi broker nhận nhưng trước khi outbox marker được cập nhật.

Consumer vẫn cần inbox/idempotency vì outbox thường cung cấp at-least-once publication, không tự bảo đảm end-to-end exactly-once cho mọi side effect.

## 16. Correlation ID và distributed tracing

Correlation ID nghiệp vụ giúp nhóm log và audit theo workflow. Distributed tracing sử dụng trace ID và span ID để biểu diễn quan hệ thời gian giữa các thao tác.

Hai khái niệm có liên quan nhưng không giống nhau:

- Correlation ID có thể tồn tại lâu theo business workflow và xuất hiện trong database, message, report.
- Trace ID thường đại diện một trace quan sát và có thể thay đổi khi tạo trace mới hoặc tiếp tục qua sampling boundary.
- Span ID nhận diện một operation trong trace.
- Baggage/context propagation mang metadata qua service boundary theo chuẩn tracing.

Không nên thay trace ID bằng business correlation ID hoặc ngược lại. Có thể ghi cả hai trong log:

~~~text
timestamp=...
service=customer-import
correlationId=FLOW-2026-001
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
jobExecutionId=142
batchId=BATCH-900
~~~

Khi nhận message, cần cấu hình instrumentation hoặc adapter để tiếp tục trace context theo chuẩn W3C Trace Context/OpenTelemetry. Chỉ truyền correlation ID tùy chỉnh không tự tạo distributed trace hoàn chỉnh.

## 17. Correlation khi gom nhiều message

Một workflow có thể phát nhiều message con rồi chờ kết quả. Correlation ID giúp gom các message cùng nhóm:

~~~text
Batch request corr=B-01
   |
   +--> Part 1 completed corr=B-01
   |
   +--> Part 2 completed corr=B-01
   |
   +--> Part 3 completed corr=B-01
              |
              v
        Aggregator
              |
              v
        Batch completed
~~~

Aggregator có thể cần thêm expected count, sequence number hoặc partition ID để biết đã nhận đủ kết quả. Chỉ có correlation ID không đủ để xác định workflow đã hoàn tất nếu không có thông tin số lượng hoặc completion marker.

Trong Spring Integration, correlation strategy, release strategy và message group store có thể được dùng để nhóm message. Cần cấu hình group timeout, expiry và persistent MessageGroupStore nếu nhóm phải sống qua restart. Correlation key phải được tạo nhất quán giữa các message.

Không dùng một correlation ID chung cho nhiều workflow độc lập nếu aggregator dựa vào nó để gom nhóm, vì các message có thể bị trộn vào cùng group.

## 18. Sequence number và thứ tự trong cùng correlation

Nếu các message cùng workflow cần được xử lý theo thứ tự, có thể mang sequence number:

~~~json
{
  "messageId": "msg-002",
  "correlationId": "FLOW-01",
  "sequence": 2,
  "eventType": "CustomerAddressChanged",
  "payload": {
    "customerId": "C-001"
  }
}
~~~

Sequence giúp consumer phát hiện message thiếu, trùng hoặc đến sai thứ tự. Tuy nhiên, sequence chỉ có ý nghĩa nếu producer định nghĩa phạm vi đếm, cách xử lý gap và reset/version.

Kafka ordering chỉ được bảo đảm trong một partition. Nếu các record cùng aggregate key được đưa vào cùng partition, thứ tự append của partition có thể hỗ trợ xử lý tuần tự. Consumer vẫn cần xử lý retry, rebalances và side effects idempotent.

Không suy luận thứ tự từ timestamp đơn thuần. Clock giữa các producer có thể lệch và nhiều message có cùng timestamp.

## 19. Correlation và message redelivery

Khi broker giao lại message, correlation ID thường giữ nguyên vì message vẫn thuộc cùng workflow. Message ID có thể được giữ nguyên hoặc thay đổi tùy producer/provider và cách ứng dụng tạo lại message. Idempotency key phải giữ ổn định cho cùng thao tác.

Một consumer nên ghi log:

- Message ID hoặc provider delivery metadata.
- Correlation ID.
- Idempotency key.
- Delivery attempt/redelivery indicator nếu broker cung cấp.
- Business key.
- Batch ID và JobExecution ID nếu message khởi chạy batch.

Nếu redelivery tạo JobExecution mới không mong muốn, hãy kiểm tra identifying JobParameters và bảng inbox. Không tạo timestamp mới làm JobInstance identity cho mỗi lần nhận lại cùng request.

## 20. Kết hợp correlation với partitioning trong Spring Batch

Correlation ID có thể được lưu trong JobParameters hoặc ExecutionContext để theo dõi các Step và partition của một batch. Ví dụ, Job nhận batchId và correlationId:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", request.batchId(), true)
        .addString("correlationId", request.correlationId(), false)
        .toJobParameters();
~~~

Khi partitioner tạo worker context, có thể copy correlation ID vào từng partition:

~~~java
ExecutionContext context = new ExecutionContext();
context.putString("partitionName", partitionName);
context.putString("correlationId", correlationId);
context.putLong("minId", minId);
context.putLong("maxId", maxId);
~~~

Worker Step có thể dùng correlation ID trong log hoặc audit:

~~~java
@Bean
@StepScope
ItemProcessor<Customer, CustomerResult> customerProcessor(
        @Value("#{stepExecutionContext['correlationId']}") String correlationId,
        CustomerService customerService) {

    return customer -> customerService.process(customer, correlationId);
}
~~~

Correlation ID ở đây phục vụ truy vết. Không nên dùng nó thay cho partition key hoặc business key nếu semantics của chúng khác nhau.

## 21. Batch ID và correlation ID

Batch ID và correlation ID có thể bằng nhau trong hệ thống đơn giản, nhưng cần phân biệt:

- Batch ID nhận diện một tập dữ liệu hoặc lần import.
- Correlation ID liên kết các message/operation trong một workflow phân tán.

Một workflow có thể chứa nhiều batch:

~~~text
Correlation FLOW-77
   |
   +--> Batch CUSTOMER-01
   |
   +--> Batch ORDER-01
   |
   +--> Batch INVOICE-01
~~~

Ngược lại, một batch có thể được xử lý bởi nhiều JobExecution hoặc partition, nhưng vẫn thuộc cùng batch ID. Correlation ID có thể liên kết request khởi chạy batch với các event hoàn tất và thông báo downstream.

Chọn field nào làm JobInstance identity phải dựa trên semantics restart của batch. Không dùng correlation ID nếu một correlation có thể chứa nhiều lần chạy độc lập.

## 22. Thiết kế message envelope

Một envelope chuẩn giúp các producer và consumer dùng định danh nhất quán:

~~~json
{
  "metadata": {
    "messageId": "msg-001",
    "messageKey": "customer-C001",
    "correlationId": "corr-import-01",
    "causationId": "msg-import-start",
    "idempotencyKey": "import-01-C001",
    "batchId": "batch-20261115",
    "schemaVersion": 1,
    "createdAt": "2026-11-15T10:00:00Z",
    "producer": "customer-import-service"
  },
  "payload": {
    "customerId": "C-001",
    "fullName": "An Nguyen"
  }
}
~~~

Envelope nên có contract version, quy tắc nullability, độ dài tối đa của ID và quy tắc propagation. Tránh cho phép payload tùy ý ghi đè metadata đã được xác thực.

Nếu middleware có native key/header, adapter có thể map messageKey sang native field. Correlation ID và idempotency key có thể nằm trong headers hoặc envelope tùy khả năng broker và yêu cầu lưu trữ. Cần test round-trip qua serializer/deserializer để bảo đảm không mất header.

## 23. Quy tắc tạo ID

ID nên được tạo bởi thành phần có quyền sở hữu semantics của nó:

- Producer tạo message ID cho từng message.
- Workflow initiator tạo correlation ID cho workflow.
- Producer/command handler tạo idempotency key ổn định cho thao tác nghiệp vụ.
- Domain entity sở hữu business key.
- Batch orchestration tạo batch ID cho lô dữ liệu.
- Spring Batch JobRepository cấp JobExecution ID.

UUID/ULID có thể phù hợp cho ID phân tán, nhưng format không tự định nghĩa uniqueness scope hoặc retention. Với business key, ưu tiên khóa miền nghiệp vụ ổn định. Với idempotency key, tránh tạo ngẫu nhiên mới mỗi lần retry cùng một command.

Không nhúng dữ liệu nhạy cảm như email, số tài khoản hoặc token vào correlation ID. ID thường xuất hiện trong log, metrics, trace và broker metadata nên cần được xem là dữ liệu có thể bị quan sát rộng.

## 24. Bảo mật và quyền riêng tư

Correlation ID và message key thường được ghi vào log và hệ thống monitoring. Chúng không nên chứa secret hoặc dữ liệu cá nhân trực tiếp.

Các nguyên tắc:

- Không dùng access token, session token hoặc credential làm message key/correlation ID.
- Tránh đưa PII vào ID nếu có thể dùng opaque identifier.
- Giới hạn độ dài key/header để tránh message phình to hoặc bị từ chối.
- Xác thực correlation ID từ nguồn bên ngoài nếu nó ảnh hưởng đến routing hoặc truy vấn.
- Không tin correlation ID do client gửi để cấp quyền truy cập dữ liệu.
- Kiểm soát quyền đọc inbox/outbox và message audit.
- Có retention policy cho message metadata và trace data.

Correlation ID là công cụ truy vết, không phải bằng chứng xác thực danh tính hoặc quyền sở hữu một workflow.

## 25. Kiểm thử message key và correlation

Nên kiểm thử contract ở nhiều tầng:

### Unit test

- Message builder giữ đúng message key và correlation header.
- Correlation ID được truyền từ request sang event tiếp theo.
- Causation ID tham chiếu đúng message nguồn.
- Idempotency key ổn định khi retry cùng command.
- Business key không bị nhầm với message ID.

### Broker integration test

- Kafka record có key được ghi vào partition như mong đợi theo cấu hình test.
- Các record cùng key có ordering trong cùng partition.
- JMSCorrelationID được giữ đúng trong request/reply.
- Header tùy chỉnh được serialize/deserialize qua adapter.
- Redelivery giữ metadata theo contract.

### Spring Batch integration test

- Message khởi chạy Job với identifying parameters ổn định.
- Redelivery không tạo JobInstance ngoài ý muốn.
- Correlation ID xuất hiện trong log/audit của Step và partition.
- Restart cùng batch giữ batch ID và input identity.
- Job completion event giữ correlation ID ban đầu.
- Inbox/outbox không tạo duplicate side effect.

Không chỉ test object Message trong memory. Cần integration test với broker hoặc embedded/test container phù hợp để xác nhận mapping native headers và delivery semantics.

## 26. Ví dụ consumer khởi chạy batch từ message

Một listener có thể chuyển message payload thành JobParameters:

~~~java
@Component
public class ImportRequestListener {

    private final ImportJobLauncher launcher;
    private final InboxService inboxService;

    public ImportRequestListener(
            ImportJobLauncher launcher,
            InboxService inboxService) {
        this.launcher = launcher;
        this.inboxService = inboxService;
    }

    @JmsListener(destination = "customer-import-requests")
    public void receive(
            ImportRequest request,
            @Header(name = "correlationId", required = false)
            String correlationId,
            @Header(name = "idempotencyKey")
            String idempotencyKey) throws Exception {

        inboxService.executeOnce(idempotencyKey, () ->
                launcher.launch(request.withCorrelationId(correlationId)));
    }
}
~~~

Đây là khung minh họa; cách bind JMS headers, acknowledgment mode, transaction và exception handling cần khớp cấu hình listener container. Nếu listener acknowledge message trước khi yêu cầu batch được lưu bền vững, request có thể bị mất khi ứng dụng crash. Nếu listener giữ transaction quá lâu trong khi Job chạy, có thể giữ broker/database resource không cần thiết.

Một thiết kế thường dùng là ghi request vào bảng inbox trong transaction ngắn, commit rồi acknowledge message. Một dispatcher khác launch Job từ request chưa được launch. Trạng thái request phải cho phép recovery nếu process dừng giữa lúc ghi request và gọi JobLauncher.

## 27. Theo dõi trạng thái batch bằng correlation

Job có thể phát event khi bắt đầu, hoàn tất hoặc thất bại. Mỗi event giữ correlation ID và batch ID:

~~~json
{
  "eventType": "BatchCompleted",
  "messageId": "msg-complete-01",
  "correlationId": "corr-import-01",
  "causationId": "msg-import-request-01",
  "batchId": "batch-20261115",
  "jobExecutionId": 142,
  "status": "COMPLETED",
  "processedCount": 25000
}
~~~

Downstream có thể liên kết event hoàn tất với request ban đầu và các event trung gian. Nếu Job restart, JobExecution ID có thể khác nhưng batch ID/correlation ID vẫn giữ nguyên nếu đó là cùng workflow.

Không phát BatchCompleted trước khi dữ liệu thực sự commit và mọi output cần thiết đã sẵn sàng. Nếu publish event trong cùng transaction database, dùng outbox để tránh dual-write. Nếu event được phát trong listener sau commit, cần xử lý trường hợp publish thất bại sau khi Job đã hoàn tất.

## 28. Các lỗi thường gặp

**Dùng message key như message ID:** nhiều message hợp lệ có thể dùng cùng key, đặc biệt khi key phục vụ Kafka partitioning. Không dùng key để deduplicate nếu semantics không phải unique per operation.

**Dùng correlation ID như idempotency key:** một workflow có thể chứa nhiều thao tác khác nhau. Dùng khóa idempotency riêng cho từng thao tác.

**Tạo correlation ID mới ở mỗi service:** các message cùng workflow bị tách khỏi nhau trong log và audit. Propagate ID ban đầu hoặc ghi rõ parent correlation.

**Dùng correlation ID làm Kafka key không cân nhắc partition load:** một workflow lớn có thể dồn vào một partition. Chọn key theo aggregate cần ordering.

**Dùng message ID làm JobInstance identity:** redelivery có thể tạo identity không ổn định tùy producer. Chọn identifying JobParameters theo batch operation.

**Thêm timestamp mới vào identifying parameters khi retry:** tạo JobInstance mới thay vì restart JobInstance cũ.

**Không giữ correlation header qua message converter:** trace bị đứt khi adapter không map custom headers. Kiểm thử round-trip với broker.

**Acknowledge trước khi request được lưu bền vững:** message có thể mất nếu consumer crash. Dùng inbox/request record và recovery.

**Coi broker delivery là exactly-once:** redelivery vẫn có thể xảy ra. Dùng inbox, unique constraint và idempotent side effect.

**Ghi outbox nhưng không deduplicate publisher:** publisher crash sau send có thể gửi lại event. Consumer vẫn cần idempotency.

**Đưa PII hoặc secret vào correlation ID:** metadata xuất hiện rộng trong log/trace. Dùng opaque ID.

**Dùng correlation để cấp quyền:** correlation ID không xác thực caller và không chứng minh quyền truy cập workflow.

## Kết luận

Message key, message ID, business key, idempotency key và correlation ID giải quyết các bài toán khác nhau. Key có thể phục vụ partition/routing theo semantics của broker; message ID nhận diện một message; business key nhận diện thực thể; idempotency key chống lặp thao tác; correlation ID liên kết các message trong cùng workflow; causation ID ghi nhận quan hệ nguyên nhân. Khi kết hợp message với Spring Batch, hãy chọn identifying JobParameters theo batch operation và semantics restart, truyền correlation ID qua headers/ExecutionContext/logs, đồng thời dùng inbox/outbox để xử lý redelivery và dual-write. Kiểm thử mapping header trên broker thật, ordering theo key, restart JobInstance và duplicate delivery để bảo đảm định danh vẫn nhất quán từ lúc nhận request đến khi batch hoàn tất.
