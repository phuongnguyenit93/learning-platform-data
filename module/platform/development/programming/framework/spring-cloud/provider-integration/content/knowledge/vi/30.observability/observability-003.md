# Theo dõi tuổi thông điệp, lượng tồn đọng và dead-letter và thời gian xử lý

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua các thư viện Spring Cloud và SDK tương ứng. Khi ứng dụng gửi công việc bất đồng bộ tới message broker, việc thấy producer gửi thành công chưa đủ để kết luận hệ thống đang xử lý tốt. Message có thể nằm chờ quá lâu, consumer có thể thiếu capacity, một nhóm message có thể liên tục thất bại hoặc bị chuyển sang dead-letter queue (DLQ).

Ví dụ: API nhận hồ sơ, lưu tài liệu vào object storage rồi gửi message để worker tạo bản xem trước. API vẫn trả HTTP 202 trong khi worker đang chậm. Nếu chỉ theo dõi request API, đội vận hành có thể thấy mọi thứ bình thường dù người dùng phải đợi nhiều phút mới có kết quả.

Bài học này tập trung vào bốn tín hiệu của hệ thống messaging:

- **Tuổi thông điệp (message age):** thời gian message đã chờ từ lúc được enqueue/publish đến khi consumer bắt đầu xử lý hoặc thời điểm quan sát.
- **Lượng tồn đọng (backlog):** số message đang chờ, đang được xử lý hoặc chưa được xác nhận, tùy trạng thái và cách đo.
- **Dead-letter:** số message bị cách ly sau khi không thể xử lý theo chính sách retry.
- **Thời gian xử lý (processing duration):** khoảng thời gian consumer thực hiện logic nghiệp vụ cho một message hoặc một batch.

Sau bài này, bạn có thể:

- Phân biệt message age, queue backlog, in-flight count, processing duration và end-to-end latency.
- Theo dõi queue/subscription và DLQ trên Amazon SQS, Azure Service Bus, Azure Queue Storage và Google Cloud Pub/Sub.
- Instrument consumer bằng Micrometer Timer/Counter và OpenTelemetry.
- Tính throughput, tốc độ tăng backlog và thời gian drain ước lượng.
- Thiết kế dashboard, SLO và alert dựa trên tuổi message cùng backlog.
- Vận hành DLQ, điều tra nguyên nhân và redrive/replay message có kiểm soát.

## 2. Các khái niệm không nên đánh đồng

Một hệ thống message có nhiều mốc thời gian và trạng thái. Nếu gọi tất cả là “queue latency”, dashboard sẽ khó chỉ ra điểm nghẽn.

| Tín hiệu | Cách hiểu | Mốc đo |
|---|---|---|
| **Message age khi bắt đầu xử lý** | Message đã chờ bao lâu trước khi consumer bắt đầu | consumerStart - enqueuedAt |
| **Backlog** | Số message chưa hoàn tất ở broker | Snapshot tại một thời điểm |
| **In-flight / unacked** | Message đã được giao cho consumer nhưng chưa ack/delete/complete | Từ receive đến settle |
| **Processing duration** | Consumer mất bao lâu để chạy handler | handlerFinish - handlerStart |
| **End-to-end latency** | Tổng thời gian từ lúc producer tạo message đến lúc nghiệp vụ hoàn tất | businessComplete - publishedAt |
| **DLQ count** | Số message đang nằm trong vùng dead-letter | Snapshot DLQ |
| **Retry/delivery attempts** | Số lần message được giao hoặc xử lý lại | Từng delivery/attempt |

Ví dụ:

~~~text
10:00:00  Producer publish message
10:00:12  Broker giao message cho consumer
10:00:15  Consumer bắt đầu handler
10:00:45  Handler hoàn tất
10:00:46  Consumer ack/complete message

Queue wait age       = 15 giây
Processing duration  = 30 giây
End-to-end latency   = 45 giây
Settlement delay     = 1 giây
~~~

**Message age không phải processing duration.** Nếu age tăng nhưng processing duration ổn định, vấn đề thường nằm ở capacity, scheduling, subscription backlog hoặc tốc độ producer. Nếu age thấp nhưng processing duration tăng, cần điều tra handler, database, storage hoặc downstream API.

## 3. Mô hình trạng thái và vòng đời message

~~~mermaid
flowchart LR
    P[Producer] -->|publish/send| Q[(Queue / Subscription)]
    Q -->|receive| I[In-flight / locked]
    I -->|success + ack/delete/complete| D[Completed]
    I -->|transient failure / nack / abandon| Q
    I -->|delivery limit exceeded| DLQ[(Dead-letter)]
    DLQ --> R[Inspect / repair / replay]
    R --> Q
~~~

Các trạng thái cần quan sát:

- **Available/active/visible:** message sẵn sàng được giao.
- **Delayed/scheduled:** message tồn tại nhưng chưa tới thời điểm được giao.
- **In-flight/locked/unacked:** message đã được giao và đang chờ xử lý/xác nhận.
- **Completed/acknowledged/deleted:** broker đã ghi nhận message hoàn tất.
- **Dead-lettered:** message được chuyển sang vùng cách ly để điều tra.
- **Expired:** message hết TTL/retention và không còn đủ điều kiện xử lý bình thường.

Tên và semantics cụ thể khác nhau giữa provider. Ví dụ SQS dùng visibility timeout và delete; Service Bus dùng Peek-Lock rồi complete/abandon/dead-letter; Pub/Sub dùng ack deadline và acknowledge/nack. Không so sánh các count nếu chưa chuẩn hóa trạng thái tương đương.

## 4. Backlog tăng có luôn là sự cố?

Không. Một queue có 100.000 message vẫn có thể hoạt động tốt nếu producer gửi 20.000 message/giây và consumer xử lý 25.000 message/giây. Ngược lại, một queue chỉ có 20 message nhưng message cũ nhất đã chờ 40 phút có thể là sự cố nghiêm trọng.

Hãy quan sát đồng thời:

1. **Backlog count:** có bao nhiêu message đang chờ?
2. **Oldest message age:** message cũ nhất đã chờ bao lâu?
3. **Ingress rate:** producer đưa message vào với tốc độ nào?
4. **Completion/ack rate:** consumer hoàn tất với tốc độ nào?
5. **In-flight count:** có bao nhiêu message đang được consumer giữ?
6. **Processing duration:** một message/batch mất bao lâu để xử lý?
7. **DLQ arrival rate và DLQ age:** lỗi có tích tụ và bị bỏ quên không?

### 4.1. Tốc độ tăng backlog

Có thể ước lượng:

~~~text
backlog_growth_rate = incoming_rate - completed_rate
~~~

- Nếu kết quả dương kéo dài, backlog đang tăng.
- Nếu gần bằng 0, hệ thống đang xử lý xấp xỉ tốc độ đến.
- Nếu âm, backlog có xu hướng giảm.

Đối với hệ thống có retry, redelivery, expiration, filter hoặc fan-out, incoming và completed cần được định nghĩa theo cùng một ranh giới nghiệp vụ. Không lấy messages sent trừ messages received một cách máy móc để kết luận message bị mất.

### 4.2. Ước lượng thời gian drain backlog

Khi completion rate cao hơn ingress rate:

\[
T_{drain} \approx \frac{Backlog}{CompletionRate - IngressRate}
\]

Ví dụ backlog có 120.000 message, consumer hoàn tất 1.000 message/giây và producer tiếp tục gửi 700 message/giây:

\[
T_{drain} \approx \frac{120.000}{1.000-700}=400\text{ giây}
\]

Nếu completion rate nhỏ hơn hoặc bằng ingress rate, backlog không thể tự giảm trong điều kiện hiện tại. Đây là ước lượng tuyến tính; nó không tính phân phối message size, retry, giới hạn concurrency, partition, burst hoặc thời gian xử lý thay đổi theo tải.

## 5. Theo dõi Amazon SQS

Amazon SQS tự gửi các metric queue vào CloudWatch trong namespace **AWS/SQS**. Một số metric là **approximate** vì SQS dùng kiến trúc phân tán; chúng phù hợp cho giám sát vận hành nhưng không phải số đếm giao dịch chính xác.

### 5.1. Metric quan trọng

| CloudWatch metric | Ý nghĩa | Dùng để |
|---|---|---|
| **ApproximateAgeOfOldestMessage** | Tuổi message cũ nhất chưa xử lý theo semantics của SQS | Phát hiện message chờ lâu |
| **ApproximateNumberOfMessagesVisible** | Message sẵn sàng nhận | Backlog có thể xử lý |
| **ApproximateNumberOfMessagesNotVisible** | Message đã nhận nhưng chưa xóa/hết visibility | In-flight, consumer đang giữ |
| **ApproximateNumberOfMessagesDelayed** | Message bị delay, chưa sẵn sàng nhận | Theo dõi scheduled/delayed work |
| **NumberOfMessagesSent** | Số message gửi thành công | Ingress volume |
| **NumberOfMessagesReceived** | Số lượt nhận message | Delivery activity, có thể bao gồm redelivery |
| **NumberOfMessagesDeleted** | Số message được xóa thành công | Completion activity |
| **NumberOfEmptyReceives** | Số lượt receive không có message | Đánh giá polling efficiency |

Số liệu queue count là gần đúng và có thể không xuất hiện khi queue không hoạt động. NumberOfMessagesReceived đếm lượt nhận, không phải số message duy nhất; một message được giao lại có thể tạo nhiều lượt nhận.

### 5.2. Theo dõi DLQ của SQS

DLQ là một SQS queue riêng được cấu hình làm redrive destination. Khi message ở source queue vượt maxReceiveCount, SQS chuyển nó sang DLQ theo redrive policy.

Đối với DLQ, theo dõi:

- ApproximateNumberOfMessagesVisible trên DLQ: số message đang chờ điều tra.
- ApproximateAgeOfOldestMessage trên DLQ: tuổi message theo semantics khi message tới DLQ.
- Tốc độ message được xử lý/redrive thủ công.
- Số message còn trong source queue và số in-flight ở source.

Không dùng NumberOfMessagesSent của DLQ để tính số message được tự động chuyển vào DLQ: SQS không tính automatic redrive vào metric gửi thủ công này. Hãy theo dõi visible count trên DLQ và metric age.

### 5.3. Hai điểm dễ hiểu sai về tuổi message

- Với **standard queue**, khi một poison message đã được nhận nhiều lần nhưng chưa xóa, SQS có thể đưa nó ra sau các message khác; ApproximateAgeOfOldestMessage phản ánh message tiếp theo chưa vượt ngưỡng receive, không nhất thiết là poison message già nhất.
- Khi message được chuyển sang DLQ, metric age trên DLQ phản ánh thời điểm chuyển vào DLQ. Với standard queue, enqueue timestamp gốc được giữ cho retention; với FIFO queue, enqueue timestamp được reset khi chuyển DLQ. Do đó cần lưu publishedAt/event timestamp ở payload nếu muốn tính tuổi nghiệp vụ từ lúc producer tạo.

Đặt retention của DLQ dài hơn source queue khi phù hợp, để có đủ thời gian điều tra và xử lý message lỗi.

## 6. Theo dõi Azure Service Bus

Azure Service Bus có message broker chuyên dụng, hỗ trợ queue, topic/subscription, dead-letter subqueue và các trạng thái như active, scheduled, deferred, completed hoặc abandoned.

### 6.1. Azure Monitor metrics

| Metric | Ý nghĩa | Dùng để |
|---|---|---|
| **Active Messages** | Message active sẵn sàng giao | Backlog có thể nhận |
| **Dead-lettered messages** | Message trong dead-letter subqueue | Theo dõi lỗi tích tụ |
| **Scheduled messages** | Message đã lên lịch | Theo dõi công việc chưa tới giờ |
| **Messages** | Tổng message ở các trạng thái được metric tính | Quan sát tổng thể entity |
| **Incoming Messages** | Message đi vào entity | Ingress |
| **Outgoing Messages** | Message được nhận từ entity | Delivery activity |
| **Completed Messages** | Số message được complete trong khoảng thời gian | Completion throughput |
| **Abandoned Messages** | Số message được abandon | Retry/redelivery pressure |
| **Size** | Kích thước entity | Dung lượng lưu trữ |

Các count như Active, Dead-lettered, Scheduled và Messages là **point-in-time values**. Incoming và Outgoing không nhất thiết bằng nhau: duplicate detection, topic filters, TTL, dead-letter và auto-forwarding đều ảnh hưởng cách đếm. Khi truy vấn message counts bị throttling, một số dynamic count có thể được trả về rỗng; không diễn giải giá trị rỗng đó thành queue thực sự bằng 0.

### 6.2. Đo message age trong Service Bus

Azure Monitor cung cấp message counts và throughput metrics, nhưng không có metric oldest-message-age tương đương trực tiếp với SQS/Pub/Sub trong bảng metrics cơ bản. Có thể đo age ở consumer từ timestamp của message:

- EnqueuedTime/EnqueuedTimeUtc: thời điểm broker nhận message.
- consumerStart: thời điểm handler bắt đầu.
- handlerFinish: thời điểm xử lý xong.

Service Bus hỗ trợ **peek** để đọc snapshot message mà không xóa message. Peek có thể trả message active, locked, deferred và scheduled; message dead-letter cần peek trên DLQ riêng. Vì vậy, peek không phải phép đo chính xác đơn giản cho mọi trạng thái của queue. Dùng peek có giới hạn để chẩn đoán, còn theo dõi age liên tục nên instrument ở consumer hoặc producer/consumer envelope.

### 6.3. Dead-letter subqueue

Service Bus có dead-letter subqueue gắn với queue hoặc subscription. Message có thể vào DLQ vì:

- Consumer chủ động dead-letter khi lỗi payload hoặc nghiệp vụ không thể xử lý.
- Message vượt MaxDeliveryCount do abandon/lock expiry và redelivery.
- TTL hết hạn khi entity bật xử lý dead-letter message hết hạn.
- Một số lỗi forwarding hoặc filter/operation theo cấu hình.

Khi điều tra, đọc DeadLetterReason và DeadLetterErrorDescription, correlation ID, message ID, sequence number và application properties. Không đưa token hoặc nội dung nhạy cảm vào error description.

## 7. Theo dõi Azure Queue Storage

Azure Queue Storage là queue đơn giản trong Storage account. Nó có semantics khác Service Bus và **không có dead-letter subqueue tích hợp**.

### 7.1. Đếm message

Hai cách đo phổ biến:

- Azure Monitor metric **QueueMessageCount**: số message chưa hết hạn trong Queue service của Storage account. Metric này được refresh theo lịch thưa (có thể theo ngày), không phù hợp cho autoscaling tức thời.
- Queue metadata/Get Properties: trả ApproximateMessagesCount cho một queue. Giá trị là ước lượng, có thể lớn hơn số thực tế; phù hợp để quan sát backlog gần thời điểm truy vấn.

Không so sánh QueueMessageCount cấp account với active-message count cấp một queue của Service Bus như thể chúng có cùng phạm vi và độ mới.

### 7.2. Tuổi message và dequeue count

Message của Azure Queue Storage có metadata như InsertedOn, NextVisibleOn và DequeueCount qua SDK tương ứng. Consumer có thể tính:

~~~text
message_age = consumer_start_time - message.InsertedOn
~~~

DequeueCount cho biết message đã được dequeue bao nhiêu lần; nó hữu ích để phát hiện message lặp lỗi. Azure Queue Storage không tự cung cấp DLQ. Ứng dụng thường tạo queue riêng, ví dụ document-jobs-poison, rồi chuyển message sang đó khi DequeueCount vượt ngưỡng.

### 7.3. Giới hạn giám sát

Queue metadata count là approximate; Azure Monitor QueueMessageCount không phải tín hiệu realtime. Nếu cần age chính xác theo nghiệp vụ, hãy đưa publishedAt/createdAt vào message envelope và đo ở consumer. Có thể peek một lượng nhỏ message để điều tra, nhưng không biến việc đọc toàn queue thành tác vụ chạy liên tục.

## 8. Theo dõi Google Cloud Pub/Sub

Pub/Sub tổ chức backlog theo **subscription**. Cùng một topic có thể có nhiều subscription độc lập; mỗi subscription có backlog, acknowledgement và dead-letter behavior riêng.

### 8.1. Metric backlog quan trọng

| Cloud Monitoring metric | Ý nghĩa | Dùng để |
|---|---|---|
| **subscription/num_unacked_messages_by_region** | Số message chưa ack theo region | Backlog theo vùng |
| **subscription/oldest_unacked_message_age_by_region** | Tuổi message unacked lâu nhất theo region | Phát hiện consumer lag |
| **subscription/delivery_latency_health_score** | Điểm sức khỏe liên quan delivery latency | Phân tích nguyên nhân độ trễ |
| **subscription/expired_ack_deadlines_count** | Số lần ack deadline hết hạn | Phát hiện consumer xử lý/ack quá chậm |
| **subscription/dead_letter_message_count** | Số message được forward sang dead-letter topic | Theo dõi DLQ forwarding |
| **subscription/num_outstanding_messages** | Message push đã giao nhưng chưa ack | Theo dõi outstanding push delivery |

Nên dùng metric có hậu tố by_region cho backlog và oldest age. Metric global có thể tạo data gap khi một region không thể báo cáo; metric regional cho phép tiếp tục quan sát những vùng còn lại. Dữ liệu backlog cũng có thể trễ vài phút, nên không dùng một sample đơn lẻ làm tín hiệu tức thời.

### 8.2. Ack deadline và redelivery

Consumer phải acknowledge message trong thời hạn. Client library có thể tự gia hạn ack deadline trong một giới hạn cấu hình; nếu deadline hết hạn, message có thể được giao lại. Tỷ lệ expired ack deadline cao thường gợi ý:

- Consumer thiếu thread/process hoặc concurrency.
- Handler mất nhiều thời gian hơn ack deadline tối đa.
- Consumer crash hoặc message gây lỗi lặp.
- Ack bị chậm do network hoặc client không quản lý lease đúng cách.

Đo processing duration ở ứng dụng và theo dõi expired_ack_deadlines_count ở Pub/Sub để phân biệt handler chậm với ack/transport issue.

### 8.3. Dead-letter topic

Pub/Sub hỗ trợ cấu hình dead-letter topic cho subscription. Khi message vượt số lần delivery attempt theo cấu hình, service có thể forward message sang topic đó. Metric subscription/dead_letter_message_count đếm số message được forward.

Để quan sát backlog của DLQ, tạo một subscription gắn với dead-letter topic và theo dõi num_unacked_messages_by_region cùng oldest_unacked_message_age_by_region của subscription đó. Với Java client, delivery attempt thường có trong message attribute googclient_deliveryattempt khi dead-letter policy được bật. Số lần giao là tín hiệu hỗ trợ chẩn đoán, không thay thế idempotency.

## 9. Bảng đối chiếu giữa các provider

| Nhu cầu | Amazon SQS | Azure Service Bus | Azure Queue Storage | Google Cloud Pub/Sub |
|---|---|---|---|---|
| Backlog count | Approximate visible messages | Active Messages; count details | ApproximateMessagesCount; account metric QueueMessageCount | num_unacked_messages_by_region |
| In-flight | ApproximateNumberOfMessagesNotVisible | Locked/active state; broker metrics tùy cách quan sát | Message invisible trong visibility window; tự instrument nếu cần | Outstanding/unacked và ack deadline |
| Oldest message age | ApproximateAgeOfOldestMessage | Tự đo từ EnqueuedTime/peek | Tự đo từ InsertedOn hoặc publishedAt | oldest_unacked_message_age_by_region |
| Processing duration | Instrument ở consumer | Instrument ở consumer | Instrument ở consumer | Instrument ở subscriber |
| DLQ | DLQ queue riêng | Dead-letter subqueue tích hợp | Tự tạo poison queue | Dead-letter topic + subscription |
| Delivery attempts | Approximate receive count/system attribute | DeliveryCount | DequeueCount | googclient_deliveryattempt (Java) |
| Độ chính xác count | Approximate, distributed | Snapshot/counts có semantics riêng | Approximate; account metric cập nhật thưa | Metrics có chu kỳ lấy mẫu và độ trễ |

Không có một metric duy nhất giống hệt giữa bốn dịch vụ. Xây dashboard chung ở tầng ứng dụng bằng cách chuẩn hóa định nghĩa; vẫn giữ metric native để điều tra provider-specific behavior.

## 10. Thiết kế message envelope để đo tuổi xuyên suốt

Để đo end-to-end age và điều tra DLQ, nên có metadata nghiệp vụ ổn định:

~~~json
{
  "eventId": "evt-2026-0042",
  "jobId": "preview-42",
  "eventType": "DocumentPreviewRequested",
  "schemaVersion": 1,
  "publishedAt": "2026-11-24T09:00:00Z",
  "correlationId": "req-8f12",
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "payloadRef": {
    "provider": "azure",
    "container": "documents",
    "blobName": "incoming/doc-42.pdf"
  }
}
~~~

Các trường quan trọng:

- eventId: định danh duy nhất của message/event; hỗ trợ deduplication và idempotency.
- jobId: khóa nghiệp vụ để tra cứu trạng thái xử lý.
- eventType và schemaVersion: xác định cách consumer đọc payload.
- publishedAt: thời điểm nghiệp vụ phát sinh message theo UTC; dùng để đo end-to-end age.
- correlationId: nối log của API, producer và consumer.
- traceparent: truyền trace context theo W3C Trace Context khi hệ thống hỗ trợ.
- payloadRef: tham chiếu dữ liệu lớn, tránh nhúng file vào message.

Timestamp do producer ghi và timestamp do broker ghi có ý nghĩa khác nhau. publishedAt phản ánh lúc nghiệp vụ tạo event; enqueuedAt/publishTime của broker phản ánh lúc message được broker nhận. Lưu cả hai khi cần tách producer delay khỏi queue wait.

Không đưa access token, SAS URL dài hạn, account key hoặc nội dung nhạy cảm vào envelope. Consumer lấy payload bằng managed identity/workload identity có quyền tối thiểu.

## 11. Instrument consumer bằng Micrometer

Provider-native metrics cho biết queue đang có bao nhiêu message. Metric ứng dụng cần đo thời gian handler thực sự chạy, tuổi message lúc bắt đầu xử lý và outcome của mỗi attempt.

Một bộ metric chuẩn hóa có thể gồm:

| Metric ứng dụng | Loại | Định nghĩa |
|---|---|---|
| messaging.message.age | Timer | Từ broker enqueue/publish time tới lúc consumer bắt đầu handler |
| messaging.process.duration | Timer | Thời gian handler xử lý message |
| messaging.messages.processed | Counter | Số message xử lý thành công |
| messaging.messages.failed | Counter | Số processing attempts thất bại |
| messaging.messages.dead_lettered | Counter | Số message ứng dụng chuyển vào DLQ/poison |
| messaging.consumer.inflight | Gauge | Số message handler đang xử lý trong instance |
| messaging.consumer.batch.size | DistributionSummary | Số message trong một batch |

Tên metric là quy ước ứng dụng minh họa. Nếu dùng OpenTelemetry messaging semantic conventions, có các metric messaging.process.duration, messaging.client.operation.duration, messaging.client.consumed.messages và messaging.client.sent.messages. Tại thời điểm viết bài, một số convention messaging vẫn ở trạng thái Development; cần kiểm tra phiên bản instrumentation và quy ước đang phát ra trước khi áp dụng.

### 11.1. Wrapper đo age và processing duration

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.Callable;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class MessageProcessingMetrics {
    private final MeterRegistry registry;

    public MessageProcessingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T process(
            String provider,
            String destination,
            Instant enqueuedAt,
            Callable<T> handler) throws Exception {

        Duration messageAge = Duration.between(enqueuedAt, Instant.now());
        if (messageAge.isNegative()) {
            registry.counter(
                    "messaging.message.timestamp_anomalies",
                    "provider", provider,
                    "destination", destination,
                    "reason", "timestamp_in_future")
                .increment();
            messageAge = Duration.ZERO;
        }

        Timer.builder("messaging.message.age")
                .tag("provider", provider)
                .tag("destination", destination)
                .publishPercentileHistogram()
                .register(registry)
                .record(messageAge);

        long started = System.nanoTime();
        String outcome = "success";

        try {
            T result = handler.call();
            registry.counter(
                    "messaging.messages.processed",
                    "provider", provider,
                    "destination", destination)
                .increment();
            return result;
        } catch (Exception ex) {
            outcome = "error";
            registry.counter(
                    "messaging.messages.failed",
                    "provider", provider,
                    "destination", destination,
                    "error_type", classify(ex))
                .increment();
            throw ex;
        } finally {
            Timer.builder("messaging.process.duration")
                    .tag("provider", provider)
                    .tag("destination", destination)
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(registry)
                    .record(System.nanoTime() - started, TimeUnit.NANOSECONDS);
        }
    }

    private String classify(Exception ex) {
        if (ex instanceof java.util.concurrent.TimeoutException) {
            return "timeout";
        }
        if (ex instanceof IllegalArgumentException) {
            return "invalid_message";
        }
        return "other";
    }
}
~~~

Gọi wrapper sau khi consumer nhận message và trước khi handler chạy. enqueuedAt phải được chuyển từ timestamp broker tương ứng hoặc từ envelope publishedAt. Kiểm tra timezone/clock synchronization; nếu timestamp ở tương lai do clock skew, xử lý dữ liệu bất thường thay vì ghi age âm.

Wrapper trên đo mỗi processing attempt. Nếu một message bị redelivery ba lần, processing duration được ghi ba lần, tương ứng với ba lần handler chạy. processed chỉ tăng khi handler thành công; failed tăng mỗi lần handler thất bại. Nếu application chuyển message vào DLQ, tăng dead_lettered tại nhánh quyết định dead-letter, không tăng cho mọi lỗi retryable.

### 11.2. Batch consumer

Nếu handler xử lý batch 100 message trong 2 giây, không nên gán 2 giây thành processing duration của từng message nếu semantics là thời gian xử lý từng item. Có thể đo:

- messaging.process.batch.duration: thời gian xử lý batch.
- messaging.consumer.batch.size: số message trong batch.
- messaging.message.age: age riêng của từng message tại lúc batch bắt đầu.
- Per-message processing duration nếu handler có thể đo từng item độc lập.

Ghi rõ metric đo batch hay item để không so sánh sai giữa consumer pull và push.

## 12. Đo tuổi message chính xác và an toàn

### 12.1. Chọn timestamp phù hợp

| Provider | Timestamp broker thường dùng | Ý nghĩa |
|---|---|---|
| Amazon SQS | SentTimestamp system attribute | Thời điểm message được gửi vào SQS; cần hiểu semantics khi redrive/DLQ |
| Azure Service Bus | EnqueuedTime | Thời điểm message được enqueue vào entity |
| Azure Queue Storage | InsertedOn | Thời điểm message được insert vào queue |
| Google Pub/Sub | publishTime | Thời điểm Pub/Sub nhận message publish |

Đo queue age bằng broker timestamp khi câu hỏi là “message đã chờ trong broker bao lâu?”. Đo business age bằng publishedAt khi câu hỏi là “từ lúc nghiệp vụ tạo event tới giờ đã bao lâu?”. Hai số có thể khác nhau do producer buffering, retry gửi message hoặc forward giữa entity.

### 12.2. Redelivery không tạo message mới

Một message được giao lại có thể có delivery count tăng, nhưng eventId/jobId vẫn giữ nguyên. Đừng đặt lại publishedAt mỗi lần consumer retry; nếu làm vậy, age sẽ trở về gần 0 và che giấu message bị kẹt lâu.

### 12.3. Đo age khi nhận và age của message cũ nhất

Metric age trong consumer chỉ được ghi khi message được giao. Nó không phản ánh message vẫn đang nằm trong backlog mà chưa được nhận. Vì vậy:

- Dùng provider metric oldest-message-age nếu có.
- Với provider không có native age metric, instrument publishedAt/broker timestamp khi consumer nhận và cân nhắc bounded peek/periodic sampling để chẩn đoán.
- Dùng backlog count cùng ingress/completion rate để nhận biết queue đang tăng dù chưa có message được giao.

Không peek toàn bộ queue liên tục để tính oldest age. Peek là thao tác chẩn đoán có giới hạn, có thể tốn request và không phản ánh chính xác mọi trạng thái như locked, deferred, scheduled hoặc DLQ.

## 13. Dead-letter: quan sát, điều tra và replay

DLQ là vùng cách ly, không phải nơi “để message lỗi tự biến mất”. Một DLQ không được giám sát có thể trở thành backlog bị lãng quên.

### 13.1. Metric cần có

- DLQ current count.
- DLQ oldest age.
- Số message mới vào DLQ theo phút/giờ.
- Số message được redrive/replay và tỷ lệ replay thành công.
- Số message đã hết retention hoặc bị xóa thủ công.
- Nhóm nguyên nhân: invalid payload, schema mismatch, permission, dependency failure, business rejection, delivery limit.

Tách **DLQ arrival rate** khỏi **DLQ backlog**. Arrival rate cho biết lỗi mới đang phát sinh; backlog cho biết lượng lỗi chưa được xử lý.

### 13.2. Metadata phục vụ điều tra

Khi dead-letter, giữ lại metadata tối thiểu:

- Original message ID và event/job ID.
- Source queue/topic/subscription.
- First published/enqueued timestamp.
- Delivery/dequeue attempt count.
- Dead-letter timestamp.
- Error type/reason đã chuẩn hóa.
- Correlation ID/trace ID.
- Schema version và application version.

Tránh ghi toàn bộ payload nhạy cảm vào log. Nếu cần lưu bản gốc, dùng kho lưu trữ có quyền truy cập và retention phù hợp.

### 13.3. Quy trình xử lý DLQ

1. **Alert:** phát hiện DLQ count hoặc arrival rate vượt ngưỡng.
2. **Inspect:** lấy một mẫu nhỏ, phân loại reason và xác định source.
3. **Fix:** sửa code, dữ liệu, schema, permission hoặc dependency.
4. **Validate:** replay một số message trong môi trường kiểm thử/canary.
5. **Redrive:** replay theo batch có giới hạn tốc độ và theo dõi outcome.
6. **Reconcile:** xác minh không tạo side effect trùng; cập nhật trạng thái nghiệp vụ.

Không redrive hàng loạt khi chưa sửa nguyên nhân. Nếu message lỗi do schema cũ, replay không thay đổi payload sẽ chỉ tạo thêm vòng lặp lỗi.

### 13.4. Idempotency và duplicate

Consumer có thể xử lý xong nghiệp vụ nhưng chết trước khi ack/delete/complete. Broker sẽ giao lại message. Khi replay từ DLQ, khả năng duplicate càng rõ hơn. Dùng eventId hoặc jobId làm idempotency key và lưu trạng thái xử lý bền vững trước khi xác nhận message.

## 14. Dashboard và truy vấn quan sát

Một dashboard cho từng queue/subscription nên có bốn nhóm panel:

| Nhóm | Panel | Câu hỏi |
|---|---|---|
| Backlog | Visible/active/unacked count | Có bao nhiêu message đang chờ? |
| Age | Oldest age và age-at-start p50/p95 | Message chờ lâu nhất và phân phối thời gian chờ ra sao? |
| Consumer | Processing duration p50/p95, success/failure rate, in-flight | Consumer có chậm, lỗi hoặc thiếu concurrency không? |
| DLQ | DLQ count, oldest DLQ age, arrival/redrive rate | Message lỗi có tích tụ và được xử lý không? |

### 14.1. PromQL cho metric ứng dụng

Giả sử Micrometer export histogram messaging_process_duration_seconds_bucket:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, provider, destination) (
    rate(messaging_process_duration_seconds_bucket[5m])
  )
)
~~~

Query này tính p95 processing duration từ histogram đã tổng hợp. Nếu muốn p95 message age lúc bắt đầu handler, dùng histogram tương ứng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, provider, destination) (
    rate(messaging_message_age_seconds_bucket[5m])
  )
)
~~~

Tỷ lệ xử lý thất bại theo attempt:

~~~promql
sum by (provider, destination) (
  rate(messaging_messages_failed_total[5m])
)
/
sum by (provider, destination) (
  rate(messaging_messages_failed_total[5m])
  +
  rate(messaging_messages_processed_total[5m])
)
~~~

Đây là tỷ lệ failed attempts trong các lần handler kết thúc; nếu cần tỷ lệ message unique thất bại cuối cùng, phải đo logical job/event outcome bằng idempotency key ở tầng nghiệp vụ. Không dùng attempt error rate thay cho tỷ lệ job thất bại.

### 14.2. Tín hiệu backlog native theo provider

- **SQS:** biểu đồ ApproximateNumberOfMessagesVisible, ApproximateNumberOfMessagesNotVisible, ApproximateAgeOfOldestMessage và DLQ visible count.
- **Service Bus:** Active Messages, Dead-lettered messages, Incoming/Outgoing, Completed/Abandoned. Thêm app metric age vì không có oldest age native tương đương.
- **Queue Storage:** ApproximateMessagesCount qua queue metadata để xem gần thời điểm truy vấn; Azure Monitor QueueMessageCount chỉ dùng xu hướng account-level dài hạn.
- **Pub/Sub:** num_unacked_messages_by_region, oldest_unacked_message_age_by_region, expired_ack_deadlines_count, dead_letter_message_count.

Đừng gộp mọi count vào một panel queue_size mà không ghi rõ đó là visible, active, unacked, scheduled hay in-flight.

## 15. SLO và cảnh báo

Đặt SLO theo thời gian nghiệp vụ mà người dùng chấp nhận, không chỉ theo throughput broker.

Ví dụ cho luồng tạo bản xem trước tài liệu:

- 99% message bắt đầu xử lý trong vòng 60 giây từ lúc enqueue.
- 99% handler hoàn tất trong vòng 20 giây.
- DLQ arrival rate dưới 0,1% message được xử lý.
- Không có message DLQ quan trọng tồn tại quá 15 phút mà chưa được điều tra.
- Backlog phải giảm khi completion rate vượt ingress rate trong một cửa sổ đủ dài.

Các ngưỡng trên chỉ là ví dụ; workload, priority và SLA thực tế có thể khác.

### 15.1. Alert gợi ý

| Điều kiện | Diễn giải | Hành động |
|---|---|---|
| Oldest age vượt SLO liên tục | Consumer lag hoặc message bị kẹt | Kiểm tra consumer capacity, in-flight và dependency latency |
| Backlog tăng cùng oldest age | Consumer không theo kịp producer | Scale có kiểm soát, kiểm tra processing duration và throughput |
| Backlog cao nhưng age thấp | Burst ngắn hoặc throughput lớn | Theo dõi xu hướng, không nhất thiết page ngay |
| Age cao nhưng backlog thấp | Một vài poison/stuck messages | Tìm event ID, delivery count và handler exception |
| In-flight cao, completion thấp | Consumer giữ message quá lâu hoặc ack bị chậm | Kiểm tra lock/visibility/ack deadline và thread pool |
| DLQ arrival rate tăng | Lỗi dữ liệu/schema/quyền hoặc dependency | Phân loại reason, dừng redrive tự động nếu cần |
| DLQ oldest age vượt retention/SLA | Message lỗi bị bỏ quên | Escalate và thực hiện runbook điều tra |
| Expired ack deadline tăng | Consumer xử lý quá lâu hoặc không gia hạn lease | Điều chỉnh concurrency, deadline/renewal và handler |

### 15.2. Autoscaling theo backlog

Có thể scale consumer theo backlog hoặc backlog trên mỗi worker:

~~~text
backlog_per_worker = visible_or_unacked_backlog / active_workers
~~~

Nhưng scale chỉ hiệu quả khi:

- Provider cho phép tăng số consumer/partition/concurrency.
- Downstream database/storage không bị quá tải khi consumer tăng.
- Message có thể xử lý song song mà không vi phạm ordering/session.
- In-flight/lock/ack deadline được quản lý đúng.

Với Pub/Sub, ưu tiên metric regional backlog và xem xét delivery latency health score. Với SQS FIFO hoặc Service Bus Sessions, throughput có thể bị giới hạn bởi số message group/session đang hoạt động; tăng replica không nhất thiết tăng throughput nếu chỉ có một group.

## 16. Trace, log và cardinality

Metrics trả lời “đang có vấn đề gì trên diện rộng”; trace/log trả lời “message cụ thể nào gặp vấn đề và tại sao”.

Khi producer gửi message:

- Tạo correlation ID/event ID ổn định.
- Propagate W3C traceparent hoặc context theo instrumentation hỗ trợ.
- Ghi span cho send/publish.

Khi consumer xử lý:

- Tạo process/consumer span và liên kết với context của producer.
- Ghi destination, operation, delivery attempt và outcome.
- Ghi exception type và error category; tránh log secret hoặc toàn payload.
- Dùng event ID trong log/trace để điều tra; không dùng event ID làm metric label.

OpenTelemetry messaging conventions khuyến nghị span link giữa producer và consumer trong nhiều mô hình messaging, vì một message có thể được fan-out tới nhiều consumer hoặc được xử lý bất đồng bộ. Metric messaging.process.duration dành cho thời gian xử lý; messaging.client.operation.duration dành cho thao tác client như send/receive/ack. Kiểm tra trạng thái/version semantic convention và instrumentation đang dùng trước khi chuẩn hóa.

Giữ metric labels ở tập hữu hạn:

- provider: aws, azure, gcp.
- system: sqs, servicebus, storage_queue, pubsub.
- destination: queue/topic/subscription có tên ổn định và ít giá trị.
- outcome: success, error, dead_lettered.
- error_type: invalid_message, timeout, authorization, dependency, other.

Không gắn messageId, eventId, correlationId, traceId, customer ID hoặc blob/object name vào metric label. Những giá trị này thuộc trace/log.

## 17. Kiểm thử và diễn tập sự cố

Một bộ kiểm thử cần xác minh cả consumer và broker metrics:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Message được xử lý ngay | Age thấp; processing duration được ghi; success tăng |
| Producer gửi burst lớn | Backlog tăng rồi giảm khi consumer theo kịp |
| Handler chậm | Processing duration tăng; in-flight/age phản ánh đúng |
| Handler lỗi tạm thời | Message được retry/redeliver theo policy |
| Message lỗi vĩnh viễn | Chuyển DLQ/poison theo giới hạn delivery |
| Ack/complete thất bại sau khi xử lý | Có thể redelivery; idempotency ngăn side effect trùng |
| DLQ có message mới | DLQ count và arrival metric tăng; alert kích hoạt |
| Replay DLQ sau khi sửa lỗi | Message xử lý thành công và trạng thái nghiệp vụ được reconcile |
| Consumer scale out | Throughput tăng nếu partition/group/concurrency cho phép |
| Một region Pub/Sub mất metric | Dashboard regional vẫn thể hiện các region còn lại |
| Azure Service Bus count query bị throttle | Không diễn giải dynamic count rỗng thành backlog bằng 0 |
| SQS poison message bị nhận lặp | Đọc đúng semantics ApproximateAgeOfOldestMessage và DLQ |

### 17.1. Unit test cho processing metrics

Có thể dùng SimpleMeterRegistry để kiểm tra Timer/Counter:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MessageProcessingMetricsTest {
    @Test
    void recordsSuccessfulProcessing() throws Exception {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        MessageProcessingMetrics metrics =
                new MessageProcessingMetrics(registry);

        String result = metrics.process(
                "azure",
                "document-jobs",
                Instant.now().minusSeconds(2),
                () -> "done");

        assertEquals("done", result);
        assertEquals(
                1.0,
                registry.get("messaging.messages.processed")
                        .tag("provider", "azure")
                        .tag("destination", "document-jobs")
                        .counter()
                        .count());
        assertEquals(
                1L,
                registry.get("messaging.process.duration")
                        .tag("provider", "azure")
                        .tag("destination", "document-jobs")
                        .tag("outcome", "success")
                        .timer()
                        .count());
    }
}
~~~

Thêm test cho exception, age, error tag và batch. Test integration với broker thật hoặc emulator phù hợp để xác minh delivery count, visibility/lock/ack deadline, DLQ và native metrics. Mock không thể chứng minh behavior redelivery của dịch vụ managed.

### 17.2. Game day

Trong môi trường staging:

1. Tăng tốc độ producer có kiểm soát để backlog tăng.
2. Giảm số worker hoặc tăng processing duration để tạo consumer lag.
3. Gửi một message payload sai để kiểm tra DLQ/poison policy.
4. Ngắt quyền truy cập dependency để xem lỗi permission có được phân loại.
5. Khôi phục dependency, sửa nguyên nhân và replay một nhóm message nhỏ.
6. Xác minh age, backlog, processing duration, DLQ và alert trở về trạng thái bình thường.

Không diễn tập bằng cách gây tải hoặc cố tình làm hỏng queue production.

## 18. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Backlog count cao nhưng người dùng chưa thấy chậm | Throughput cao, backlog là burst ngắn | So sánh oldest age, ingress và completion rate |
| Backlog thấp nhưng oldest age rất cao | Một số message bị kẹt hoặc poison | Tìm delivery count, message ID và lỗi handler |
| Processing duration thấp nhưng age tăng | Consumer capacity thấp hoặc không nhận đủ message | Kiểm tra số worker, polling, subscription và concurrency |
| In-flight tăng liên tục | Consumer không ack/delete/complete hoặc handler treo | Kiểm tra lease/visibility/ack deadline và exception path |
| DLQ count tăng nhưng NumberOfMessagesSent không tăng trên SQS | Automatic redrive không được tính như manual send | Dùng visible count và age trên DLQ |
| Service Bus message count hiển thị 0 khi bị throttling | Dynamic counts có thể rỗng trong response | Đối chiếu Azure Monitor metrics, retry query và log throttle |
| Queue Storage metric không phản ánh backlog tức thời | QueueMessageCount cấp account cập nhật thưa | Dùng ApproximateMessagesCount của queue và app-side age |
| Pub/Sub backlog metric bị gap | Metric global phụ thuộc dữ liệu nhiều region | Dùng metric hậu tố by_region |
| DLQ replay tạo side effect trùng | Consumer không idempotent | Dùng eventId/jobId và trạng thái xử lý bền vững |
| Message age âm hoặc nhảy bất thường | Clock skew hoặc timestamp bị reset khi retry | Dùng UTC, đồng bộ clock, giữ publishedAt gốc |
| Batch processing duration bị hiểu là per-message | Metric ghi cùng thời gian batch cho từng item | Tách batch duration và per-message duration |
| Autoscaling không cải thiện throughput | FIFO group/session/partition giới hạn song song | Tăng số group/partition hợp lý hoặc thay đổi mô hình xử lý |

## 19. Bài tập thực hành và câu hỏi tự kiểm tra

**Tình huống A — SQS backlog:** ApproximateNumberOfMessagesVisible tăng liên tục, ApproximateAgeOfOldestMessage cũng tăng và NotVisible thấp. Hãy phân tích vì sao consumer có thể chưa nhận đủ message, kiểm tra polling/worker capacity và đề xuất cách scale.

**Tình huống B — SQS DLQ:** DLQ có 500 message nhưng NumberOfMessagesSent gần bằng 0. Hãy giải thích automatic redrive không được tính vào metric gửi thủ công và chọn metric phù hợp để theo dõi DLQ.

**Tình huống C — Service Bus:** Active Messages tăng, Dead-lettered Messages tăng và Completed Messages giảm. Hãy kiểm tra consumer errors, delivery count, lock expiry và DeadLetterReason; xây dựng kế hoạch sửa lỗi rồi replay.

**Tình huống D — Azure Queue Storage:** Azure Monitor QueueMessageCount không thay đổi trong khi queue metadata count tăng. Hãy giải thích độ mới/độ chính xác của hai phép đo và thiết kế age metric ở consumer từ InsertedOn.

**Tình huống E — Pub/Sub:** num_unacked_messages_by_region và oldest_unacked_message_age_by_region tăng cùng lúc; expired_ack_deadlines_count cũng tăng. Hãy kiểm tra processing duration, subscriber concurrency và ack deadline extension.

**Tình huống F — Message age và processing duration:** Dashboard cho thấy age p95 là 5 phút nhưng processing duration p95 chỉ 2 giây. Hãy xác định bottleneck nằm ở thời gian chờ trong broker hay handler và đề xuất cách xử lý.

**Tình huống G — DLQ replay:** Một nhóm message bị đưa vào DLQ do consumer dùng sai schema. Sau khi deploy bản sửa, hãy thiết kế canary replay, idempotency, rate limit và reconciliation.

### Câu hỏi tự kiểm tra

1. **Message age khác processing duration thế nào?** Age đo thời gian chờ từ lúc enqueue/publish tới khi consumer bắt đầu; processing duration đo thời gian handler chạy.
2. **Backlog count cao luôn là sự cố không?** Không; cần so sánh với throughput và oldest age.
3. **SQS metric nào đo message sẵn sàng nhận?** ApproximateNumberOfMessagesVisible.
4. **SQS DLQ nên theo dõi metric nào cho số message đang chờ?** ApproximateNumberOfMessagesVisible trên DLQ.
5. **Azure Service Bus có DLQ native không?** Có, dưới dạng dead-letter subqueue cho queue/subscription.
6. **Azure Queue Storage có DLQ native không?** Không; ứng dụng tự tạo poison queue và chuyển message theo policy.
7. **Azure Queue Storage QueueMessageCount có phù hợp autoscaling realtime không?** Không; metric account-level được cập nhật thưa. Dùng approximate count của từng queue và metric ứng dụng.
8. **Pub/Sub nên dùng backlog metric nào khi cần resilience theo vùng?** num_unacked_messages_by_region và oldest_unacked_message_age_by_region.
9. **Vì sao cần đo expired ack deadline?** Nó cho biết message có thể bị redelivery do consumer không ack kịp.
10. **Khi nào nên replay DLQ?** Sau khi đã xác định và sửa nguyên nhân, thử nghiệm một nhóm nhỏ và bảo đảm consumer idempotent.

## 20. Tổng kết

Theo dõi messaging cần kết hợp **backlog, oldest message age, in-flight/unacked, processing duration và DLQ**. Backlog cho biết khối lượng công việc đang chờ; age cho biết người dùng phải chờ lâu đến đâu; processing duration cho biết handler chậm hay nhanh; DLQ cho biết các message không thể xử lý đang tích tụ.

AWS SQS có CloudWatch metrics về oldest age, visible, not-visible và DLQ queue; Azure Service Bus có active/dead-letter counts và cần đo message age ở consumer; Azure Queue Storage cung cấp approximate count với độ mới khác nhau và cần tự xây poison queue; Google Pub/Sub có regional backlog/oldest-age metrics, ack deadline và dead-letter topic. Chuẩn hóa định nghĩa ở tầng ứng dụng, dùng Micrometer/OpenTelemetry, giữ timestamp gốc và idempotency key, rồi redrive message chỉ sau khi đã sửa nguyên nhân.

### Tài liệu tham khảo chính thức

- [AWS — Available CloudWatch metrics for Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [AWS — Using dead-letter queues in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Azure — Monitoring data reference for Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/monitor-service-bus-reference)
- [Azure — Get message counters for Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/message-counters)
- [Azure — Browse or peek Service Bus messages](https://learn.microsoft.com/azure/service-bus-messaging/message-browsing)
- [Azure — Best practices for monitoring Queue Storage](https://learn.microsoft.com/azure/storage/queues/queues-storage-monitoring-scenarios)
- [Azure — Queue Storage monitoring data reference](https://learn.microsoft.com/azure/storage/queues/monitor-queue-storage-reference)
- [Google Cloud — Monitor Pub/Sub subscriptions](https://docs.cloud.google.com/pubsub/docs/monitoring)
- [Google Cloud — Dead-letter topics](https://docs.cloud.google.com/pubsub/docs/dead-letter-topics)
- [OpenTelemetry — Semantic conventions for messaging metrics](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-metrics/)
- [OpenTelemetry — Semantic conventions for messaging spans](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/)
