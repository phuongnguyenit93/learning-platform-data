# Xây dựng quy trình sửa lỗi, phát lại và đối soát thông điệp

Trong hệ thống event-driven, không phải mọi message đều được xử lý thành công ngay lần đầu. Một dịch vụ phụ thuộc có thể tạm thời ngừng hoạt động, schema mới có thể chưa tương thích với consumer cũ, hoặc dữ liệu đầu vào có thể vi phạm quy tắc nghiệp vụ. Retry giúp xử lý lại lỗi tạm thời; Dead Letter Queue (DLQ) giữ những message không thể xử lý theo chính sách hiện tại. Nhưng đưa message vào DLQ mới chỉ là bước cách ly. Để khôi phục hệ thống, nhóm vận hành cần xác định nguyên nhân, sửa lỗi, phát lại có kiểm soát và đối soát kết quả.

Spring Cloud Stream cung cấp binding, binder, retry và các tích hợp DLQ tùy broker. Ứng dụng cần bổ sung quy trình nghiệp vụ để quản lý vòng đời message lỗi: lưu dấu vết, phân loại, quyết định phát lại, ngăn tác động trùng và xác minh trạng thái sau phục hồi. Bài học này trình bày quy trình đó với Kafka, RabbitMQ và Pulsar.

## 1. Phân biệt retry, DLQ, replay và reconciliation

Bốn thao tác thường đi cùng nhau nhưng giải quyết các vấn đề khác nhau:

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| Retry | Thử lại thao tác có khả năng thành công sau một khoảng chờ | API thanh toán timeout ngắn |
| DLQ | Cách ly message đã vượt chính sách xử lý hoặc không thể xử lý tự động | Payload không hợp lệ, lỗi lặp quá số lần |
| Replay | Phát lại message đã lưu để consumer xử lý lại sau khi nguyên nhân được khắc phục | Gửi lại các đơn hàng sau khi sửa lỗi mapping |
| Reconciliation | So sánh trạng thái thực tế với nguồn dữ liệu chuẩn để phát hiện và sửa sai lệch | Đối chiếu đơn hàng đã thanh toán với sổ cái |

Retry thường diễn ra gần thời điểm lỗi và có giới hạn. DLQ lưu message để con người hoặc quy trình phục hồi xem xét. Replay đưa message trở lại một đường xử lý. Reconciliation kiểm tra kết quả nghiệp vụ và tìm ra những trường hợp bị bỏ sót, trùng hoặc sai trạng thái.

Không phải mọi message trong DLQ đều nên replay ngay. Nếu nguyên nhân là dữ liệu sai vĩnh viễn, phát lại cùng payload sẽ lặp lại lỗi. Nếu nguyên nhân là lỗi phần mềm, cần triển khai bản sửa và kiểm thử trước. Nếu nghiệp vụ đã hoàn tất nhưng phản hồi bị mất, replay có thể gây tác động trùng nếu consumer không idempotent.

## 2. Quy trình phục hồi từ đầu đến cuối

Một quy trình vận hành rõ ràng có thể chia thành các trạng thái:

~~~text
DETECTED
   |
   v
TRIAGED -----> REJECTED / MANUAL_REVIEW
   |
   v
ROOT_CAUSE_FIXED
   |
   v
REPLAY_VALIDATED
   |
   v
REPLAYING
   |
   v
RECONCILING
   |
   v
VERIFIED
   |
   v
CLOSED
~~~

Ý nghĩa từng bước:

1. **Detected:** cảnh báo cho biết DLQ tăng, tỷ lệ lỗi vượt ngưỡng hoặc consumer lag bất thường.
2. **Triaged:** xác định loại lỗi, phạm vi message, destination, group và thời gian bị ảnh hưởng.
3. **Root cause fixed:** sửa cấu hình, dữ liệu, schema hoặc code gây lỗi; xác nhận phiên bản mới đã sẵn sàng.
4. **Replay validated:** chạy thử trên một tập nhỏ hoặc môi trường kiểm thử, xác nhận kết quả và tác động trùng.
5. **Replaying:** phát lại theo batch, có giới hạn tốc độ và checkpoint.
6. **Reconciling:** đối chiếu kết quả xử lý với nguồn dữ liệu chuẩn.
7. **Verified:** xác nhận không còn message thuộc phạm vi cần xử lý, không có sai lệch chưa giải quyết và các metric trở về ngưỡng bình thường.
8. **Closed:** lưu báo cáo, người thực hiện, nguyên nhân, số lượng message và kết quả.

Mỗi lần phục hồi nên có một mã đợt xử lý, người chịu trách nhiệm, điều kiện dừng và phạm vi message cụ thể. Không dùng một thao tác replay rộng cho toàn bộ DLQ nếu chỉ một nhóm message bị ảnh hưởng.

## 3. Lưu đủ metadata để điều tra

Khi đưa message vào DLQ hoặc kho cách ly, cần giữ dữ liệu gốc cùng thông tin giúp xác định nguồn và lịch sử xử lý. Một bản ghi phục hồi nên có:

- Payload gốc hoặc tham chiếu an toàn đến payload.
- Event ID và correlation ID nếu producer cung cấp.
- Tên destination, binding, consumer group hoặc subscription.
- Broker metadata như topic, partition, offset, routing key hoặc message ID nếu có.
- Thời điểm nhận, thời điểm lỗi và số lần thử.
- Loại exception, thông báo lỗi đã được làm sạch và phiên bản consumer.
- Content type, schema version hoặc schema ID khi định dạng sử dụng schema.
- Replay batch ID, trạng thái xử lý và thời điểm phục hồi.

Không ghi token, mật khẩu, thông tin xác thực hoặc dữ liệu cá nhân không cần thiết vào log và bảng DLQ. Nếu payload chứa dữ liệu nhạy cảm, áp dụng quyền truy cập, mã hóa, thời hạn lưu giữ và quy trình audit tương ứng.

Ví dụ envelope phục hồi do ứng dụng quản lý:

~~~java
import java.time.Instant;

record FailedEvent(
        String eventId,
        String destination,
        String consumerGroup,
        String contentType,
        String payload,
        String errorCode,
        String errorMessage,
        int attempts,
        Instant firstFailedAt,
        Instant lastFailedAt) {}
~~~

Đây là mô hình dữ liệu minh họa, không phải cấu trúc DLQ bắt buộc của mọi binder. Metadata thực tế có thể nằm trong header của broker, message gốc hoặc một bảng vận hành riêng. Khi lưu payload, cần bảo đảm có thể khôi phục đúng byte và schema cần thiết; không chỉ lưu một chuỗi đã chuyển đổi nếu điều đó làm mất thông tin wire cần cho giải mã.

## 4. Phân loại nguyên nhân trước khi phát lại

Trước khi replay, xác định lỗi thuộc nhóm nào:

| Nhóm lỗi | Dấu hiệu | Hành động |
|---|---|---|
| Tạm thời | Timeout, kết nối broker hoặc dịch vụ phụ thuộc gián đoạn | Retry có backoff; replay sau khi dependency ổn định |
| Cấu hình | Sai credential, destination, routing hoặc quyền truy cập | Sửa cấu hình, xác minh kết nối rồi replay |
| Schema/serialization | Không giải mã được, thiếu trường hoặc schema không tương thích | Sửa consumer/schema hoặc triển khai reader tương thích |
| Dữ liệu nghiệp vụ | Thiếu định danh, giá trị ngoài miền hợp lệ | Cách ly, sửa dữ liệu qua quy trình được phê duyệt hoặc từ chối |
| Lỗi code | NullPointerException, lỗi mapping hoặc logic | Sửa và triển khai code, chạy test rồi replay |
| Trạng thái không rõ | Timeout sau khi side effect có thể đã hoàn tất | Đối soát nguồn chuẩn trước khi quyết định replay |

Lỗi tạm thời có thể được thử lại sau một khoảng chờ. Lỗi dữ liệu vĩnh viễn không nên đưa vào retry liên tục. Lỗi trạng thái không rõ cần được đối chiếu trước vì hệ thống có thể đã thực hiện nghiệp vụ dù consumer chưa ghi nhận thành công.

## 5. Cấu hình retry và DLQ trong Spring Cloud Stream

Spring Cloud Stream có thể cấu hình số lần thử ở cấp binding. Với Kafka binder, DLQ được bật bằng cấu hình riêng của binder. Ví dụ minh họa:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.order-processor.dlq
~~~

Trong ví dụ, binding thử xử lý tối đa ba lần theo chính sách retry của framework trước khi áp dụng xử lý lỗi/DLQ đã cấu hình. Tên DLQ được chỉ định rõ để vận hành và cảnh báo dễ nhận biết. Thuộc tính cụ thể, cách tạo DLQ, số partition DLQ và điều kiện hỗ trợ phụ thuộc phiên bản Kafka binder.

Không dùng cấu hình trên như cấu hình chung cho RabbitMQ hoặc Pulsar. Rabbit binder có các thuộc tính dead-letter exchange/queue riêng; Pulsar binder có cấu hình dead letter topic và redelivery riêng. Hãy đối chiếu tài liệu đúng phiên bản binder trước khi đưa vào production.

Retry cần có backoff và giới hạn. Retry quá nhanh có thể làm tăng tải lên dependency đang gặp sự cố. Nếu lỗi không thể khắc phục bằng chờ, đưa message vào DLQ để điều tra thay vì retry vô hạn.

## 6. Phát lại message trong Kafka

Kafka lưu record theo topic, partition và offset. Khi consumer group đọc record, tiến độ thường được theo dõi bằng committed offset. Cần phân biệt hai cách phục hồi:

1. **Đọc lại từ topic gốc:** điều chỉnh offset của consumer group hoặc dùng một group mới để đọc lại phạm vi record.
2. **Phát lại từ DLQ:** một replay publisher đọc record từ DLQ rồi publish payload sang topic đích hoặc topic replay.

Đọc lại từ topic gốc có thể làm consumer xử lý lại cả record đã thành công trong phạm vi offset được tua lại. Việc thay đổi offset tác động đến tiến độ của group và có thể gây trùng side effect. Chỉ thực hiện khi đã xác định partition, offset, group và kế hoạch dừng/khởi động consumer.

Phát lại từ DLQ tạo record mới với offset mới. Không thể khôi phục offset gốc bằng cách publish lại. Nếu cần truy vết nguồn, lưu original topic, original partition, original offset và event ID dưới dạng metadata nghiệp vụ hoặc header được phép truyền.

Ví dụ cấu hình output binding dành riêng cho replay:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderReplay-out-0:
          destination: orders.replay
          content-type: application/json
~~~

Destination orders.replay chỉ là luồng đích cho message mới; consumer xử lý đơn hàng phải được cấu hình đọc luồng replay này hoặc một thành phần trung gian phải định tuyến nó vào cùng logic nghiệp vụ. Nếu publish trực tiếp về orders.created, mọi consumer group đang subscribe topic gốc có thể nhận lại bản sao, không chỉ group bị lỗi. Chọn đường replay theo phạm vi cần phục hồi và ghi rõ group/destination mục tiêu.

Replay publisher có thể dùng StreamBridge để phát message đã được xác minh:

~~~java
import java.time.Instant;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        long totalMinorUnits) {}

record ReplayMetadata(
        String replayBatchId,
        String originalEventId,
        String originalTopic,
        int originalPartition,
        long originalOffset,
        Instant replayedAt) {}

@Component
class OrderReplayPublisher {

    private final StreamBridge streamBridge;

    OrderReplayPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean replay(OrderCreated event, ReplayMetadata metadata) {
        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", metadata.originalEventId())
                .setHeader("replayBatchId", metadata.replayBatchId())
                .setHeader("originalTopic", metadata.originalTopic())
                .setHeader("originalPartition", metadata.originalPartition())
                .setHeader("originalOffset", metadata.originalOffset())
                .setHeader("replayedAt", metadata.replayedAt().toString())
                .build();

        return streamBridge.send("orderReplay-out-0", message);
    }
}
~~~

Ví dụ tạo message mới để replay; nó không khôi phục offset gốc và không tự bảo đảm record được ghi vào cùng partition. Nếu cần giữ partition theo orderId, output binding phải có partition key phù hợp và topic replay phải được cấu hình tương thích. Không sao chép mù quáng toàn bộ header broker từ DLQ sang topic mới; một số header chỉ có ý nghĩa trong lần giao nhận trước.

Payload OrderCreated trong ví dụ vẫn giữ eventId gốc. Header eventId được đặt cùng giá trị để hỗ trợ quan sát; consumer cần dùng cùng một định danh ổn định trong inbox/idempotency check, bất kể nó lấy định danh từ payload hay header.

Giá trị boolean của StreamBridge.send cho biết message được chấp nhận qua binding/channel; không nên coi riêng giá trị này là xác nhận broker đã lưu bền vững. Replay publisher cần dùng cơ chế xác nhận gửi phù hợp với binder (ví dụ publisher confirm của RabbitMQ hoặc kết quả gửi producer của Kafka/Pulsar) trước khi đánh dấu nguồn DLQ đã hoàn tất. Nếu binder/API không cung cấp xác nhận cần thiết ở đường gửi đang dùng, phải thiết kế checkpoint và khả năng gửi trùng theo hướng at-least-once.

## 7. Phát lại từ RabbitMQ

RabbitMQ thường dùng dead-letter exchange (DLX) để định tuyến message bị reject, hết TTL hoặc vượt điều kiện queue sang dead-letter queue. Replay có thể được thực hiện bằng cách:

- Sửa nguyên nhân khiến consumer reject message.
- Đọc một batch từ DLQ bằng công cụ hoặc publisher phục hồi.
- Publish message đến exchange đích với routing key đã xác định.
- Chỉ đánh dấu hoặc xác nhận message DLQ sau khi publisher đã gửi theo chính sách giao nhận đã chọn.

Nếu replay publisher xác nhận message DLQ trước khi publish thành công, có thể mất message. Nếu publish thành công nhưng publisher dừng trước khi xác nhận message DLQ, message có thể được gửi lại và tạo bản sao. Cần publisher confirms, acknowledgement phù hợp, event ID và consumer idempotent để quản lý khoảng trống này.

Không bật requeue vô hạn cho message lỗi vĩnh viễn. Một message bị requeue liên tục có thể tạo vòng lặp nóng, làm tăng CPU và che khuất các message hợp lệ. DLX/DLQ nên giữ message lỗi để phân loại và xử lý có kiểm soát.

## 8. Phát lại từ Pulsar

Pulsar có thể chuyển message không xử lý được sang dead letter topic theo cấu hình subscription và chính sách redelivery. Có thể dùng consumer đọc dead letter topic rồi phát lại đến topic xử lý sau khi nguyên nhân đã được khắc phục.

Khi phát lại, cần phân biệt:

- Redelivery trong subscription hiện tại: broker giao lại message chưa được acknowledge theo cơ chế subscription.
- Reconsume hoặc seek: consumer đọc lại dữ liệu theo cursor/subscription và vị trí đã xác định.
- Republish: ứng dụng tạo message mới từ DLQ và gửi vào topic đích hoặc replay topic.

Các cách này có ngữ nghĩa khác nhau về message ID, cursor và thứ tự. Nếu tạo subscription mới để đọc lại lịch sử, cần quản lý subscription và retention. Với Key_Shared hoặc partitioned topic, kiểm tra key, batching, redelivery và acknowledgement để không phá vỡ yêu cầu thứ tự theo khóa.

Không giả định cấu hình DLQ của Kafka hoặc RabbitMQ áp dụng được cho Pulsar. Dùng đúng cấu hình dead letter topic, subscription type và redelivery policy của Pulsar binder/client đang triển khai.

## 9. Thiết kế replay an toàn và có thể tiếp tục

Một replay job cần có khả năng dừng, tiếp tục và chứng minh phạm vi đã xử lý. Trước khi chạy:

1. Chọn DLQ/topic/queue và khoảng thời gian hoặc danh sách event ID cần phục hồi.
2. Lưu truy vấn chọn message, số lượng dự kiến và mã replay batch.
3. Chạy dry-run để đếm, kiểm tra schema và phát hiện message không thuộc phạm vi.
4. Xác nhận nguyên nhân gốc đã được sửa và consumer mới có thể xử lý payload.
5. Chạy batch nhỏ, giới hạn tốc độ và quan sát lỗi/lag.
6. Lưu checkpoint sau mỗi batch; không đánh dấu hoàn tất trước khi xác nhận kết quả gửi.
7. Tạm dừng nếu tỷ lệ lỗi vượt ngưỡng, backlog tăng nhanh hoặc xuất hiện side effect trùng.
8. Đối soát kết quả rồi mới đóng đợt phục hồi.

Một bảng quản lý replay có thể chứa:

| Trường | Ý nghĩa |
|---|---|
| replayBatchId | Mã duy nhất của đợt replay |
| eventId | Định danh sự kiện gốc |
| sourceLocation | DLQ, topic/partition/offset hoặc queue |
| targetDestination | Nơi phát lại |
| status | PENDING, SENT, VERIFIED hoặc FAILED |
| attempts | Số lần publisher thử gửi |
| lastError | Lỗi gần nhất nếu gửi thất bại |
| updatedAt | Thời điểm cập nhật |

Checkpoint phải đủ bền vững để job tiếp tục sau restart. Nếu trạng thái SENT được ghi sau khi publish thành công, vẫn tồn tại cửa sổ publisher có thể dừng giữa hai thao tác. Replay có thể phát trùng; thiết kế phải chấp nhận at-least-once và dựa vào idempotency ở consumer.

## 10. Idempotency để chống tác động trùng

Replay thường tạo ra message được giao lại. Vì vậy, consumer cần phân biệt một sự kiện đã xử lý với một sự kiện mới. Một cách phổ biến là dùng eventId làm idempotency key và lưu trạng thái xử lý trong cùng transaction với side effect dữ liệu.

Ví dụ bảng inbox:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Pseudocode xử lý:

~~~java
import java.time.Instant;

import org.springframework.transaction.annotation.Transactional;

@Transactional
void handle(OrderCreated event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    orderRepository.apply(event);
    processedEventRepository.save(
            new ProcessedEvent(event.eventId(), Instant.now()));
}
~~~

Ví dụ minh họa nguyên tắc; để tránh race condition, cần dựa vào unique constraint của event_id và xử lý xung đột insert một cách an toàn. Việc kiểm tra exists rồi insert không đủ nếu hai consumer có thể xử lý cùng event đồng thời. Side effect và dấu processed phải nằm trong cùng transaction nếu cùng một cơ sở dữ liệu.

Nếu side effect là gọi dịch vụ ngoài hoặc cổng thanh toán, transaction cơ sở dữ liệu không thể tự làm thao tác đó nguyên tử. Dùng idempotency key mà dịch vụ ngoài hỗ trợ, outbox/inbox, hoặc quy trình đối soát trạng thái trước khi thử lại. Không coi eventId trong header là đủ nếu hệ thống không lưu và kiểm tra nó.

## 11. Sửa dữ liệu và schema trước khi replay

Một số message thất bại vì dữ liệu không còn phù hợp với schema hoặc quy tắc mới. Cần phân biệt:

- **Sửa consumer:** triển khai reader tương thích hoặc sửa mapping mà không thay payload gốc.
- **Chuẩn hóa dữ liệu:** chuyển đổi payload qua một bước migration được kiểm soát và lưu cả bản gốc lẫn bản đã sửa.
- **Từ chối nghiệp vụ:** đánh dấu message không thể xử lý, yêu cầu nguồn phát sửa và phát sự kiện mới theo hợp đồng.
- **Bổ sung dữ liệu:** tra cứu từ nguồn chuẩn theo khóa định danh, ghi rõ dữ liệu được bổ sung và nguồn tham chiếu.

Không sửa payload trong DLQ tại chỗ mà không có audit. Nếu cần biến đổi, tạo bản ghi repaired event có liên kết đến event gốc, ghi lại phiên bản transform, người thực hiện và lý do. Khi phát lại, consumer cần nhận biết event ID gốc hoặc một định danh xử lý ổn định để tránh coi bản đã sửa là nghiệp vụ hoàn toàn mới.

Nếu schema ID hoặc writer schema gốc cần thiết cho giải mã, phải giữ metadata đó. Không đổi content type hay schema version chỉ để converter chấp nhận payload nếu nội dung thực tế chưa được chuyển đổi tương ứng.

## 12. Đối soát sau khi replay

Replay thành công ở tầng broker chưa chứng minh trạng thái nghiệp vụ đã đúng. Reconciliation so sánh kết quả xử lý với một nguồn dữ liệu chuẩn, chẳng hạn database nghiệp vụ, sổ cái, hệ thống thanh toán hoặc snapshot được kiểm soát.

Quy trình đối soát:

1. Xác định nguồn chuẩn và khóa đối chiếu, ví dụ orderId, paymentId hoặc eventId.
2. Chọn khoảng thời gian và phạm vi dữ liệu khớp với replay batch.
3. So sánh số lượng sự kiện dự kiến, đã gửi, đã xử lý và trạng thái nghiệp vụ.
4. Phân loại thiếu, trùng, sai thứ tự hoặc sai giá trị.
5. Tạo danh sách sai lệch có thể tái lập và người chịu trách nhiệm.
6. Sửa bằng thao tác idempotent hoặc quy trình bù trừ được phê duyệt.
7. Chạy đối soát lại và lưu kết quả cuối cùng.

Ví dụ đối soát đơn hàng:

| Trạng thái nguồn chuẩn | Trạng thái projection | Kết luận |
|---|---|---|
| PAID | PAID | Khớp |
| PAID | PENDING | Có thể thiếu sự kiện PaymentCompleted |
| PENDING | PAID | Có thể phát trùng hoặc sai thứ tự |
| Không tồn tại | PAID | Cần điều tra dữ liệu mồ côi |

Không tự động sửa mọi sai lệch bằng cách ghi đè projection từ nguồn chuẩn nếu projection có quy tắc riêng hoặc nguồn chuẩn không chứa toàn bộ lịch sử. Với sổ cái tài chính, ưu tiên bút toán điều chỉnh/compensating event có audit thay vì sửa trực tiếp lịch sử giao dịch.

## 13. Đối soát có checkpoint và giới hạn tải

Đối soát tập dữ liệu lớn cần chia trang hoặc theo cửa sổ thời gian. Mỗi batch nên lưu:

- Phạm vi khóa bắt đầu và kết thúc.
- Snapshot hoặc thời điểm nguồn chuẩn được đọc.
- Số bản ghi kiểm tra, số bản ghi khớp và số sai lệch.
- Mã batch, thời điểm chạy và checkpoint.
- Trạng thái xử lý từng sai lệch.

Nếu nguồn chuẩn thay đổi trong lúc đối soát, kết quả có thể không nhất quán. Dùng snapshot isolation, watermark hoặc khoảng thời gian đã chốt theo khả năng của kho dữ liệu. Khi phải gọi API ngoài, giới hạn concurrency và rate để không gây sự cố mới trong lúc phục hồi.

Đối soát không nên chạy liên tục mà không có ngưỡng dừng. Nếu số sai lệch tăng bất thường, dừng batch và điều tra nguyên nhân thay vì tự động phát hàng loạt compensating event.

## 14. Theo dõi và báo cáo đợt phục hồi

Một đợt replay/reconciliation cần metric và log có thể truy vết:

- Số message trong DLQ theo destination, group và loại lỗi.
- Tuổi của message cũ nhất trong DLQ.
- Số message đã phân loại, được duyệt replay, gửi lại và xác minh.
- Tỷ lệ replay thành công, lỗi mới và số lần retry.
- Consumer lag, throughput và độ trễ sau replay.
- Số event bị bỏ qua do idempotency.
- Số sai lệch reconciliation theo loại và thời gian tồn đọng.

Log cần có replayBatchId, eventId, original location, target destination và trạng thái. Tránh ghi toàn bộ payload nếu payload chứa dữ liệu nhạy cảm. Báo cáo cuối nên nêu tổng số message trong phạm vi, số đã replay, số bị loại có lý do, số còn chờ và số sai lệch đã xử lý.

## 15. Kiểm thử quy trình phục hồi

Kiểm thử không chỉ xác nhận consumer xử lý một message hợp lệ. Cần kiểm tra các tình huống vận hành:

1. Message lỗi vượt max attempts và được đưa vào DLQ đúng destination.
2. Message DLQ giữ đủ event ID và metadata cần truy vết.
3. Replay publisher chỉ gửi các message đã được duyệt trong phạm vi batch.
4. Publisher dừng giữa lúc gửi và cập nhật checkpoint; khi chạy lại không làm mất message.
5. Consumer nhận cùng event ID hai lần nhưng side effect chỉ xảy ra một lần.
6. Message không tương thích schema được cách ly và không retry vô hạn.
7. Reconciliation phát hiện một projection bị thiếu hoặc trùng.
8. Replay bị dừng khi lỗi mới vượt ngưỡng và có thể tiếp tục từ checkpoint.
9. Kiểm thử broker thật xác nhận semantics DLQ, redelivery, acknowledgement và routing.

Spring Cloud Stream test binder hữu ích để kiểm tra logic hàm và binding ở cấp ứng dụng. Nó không thay thế integration test cho Kafka offset, RabbitMQ DLX/acknowledgement hoặc Pulsar dead letter topic/subscription. Các thao tác replay và đối soát nên được kiểm thử với broker và kho dữ liệu tương ứng.

## 16. Checklist vận hành

- Có cảnh báo khi DLQ tăng, message tồn đọng lâu hoặc consumer lỗi lặp.
- Mỗi message lỗi giữ event ID và metadata nguồn cần thiết.
- Nguyên nhân gốc được phân loại và khắc phục trước khi replay.
- Replay có mã batch, phạm vi, dry-run, giới hạn tốc độ và checkpoint.
- Không thay đổi consumer offset hoặc republish hàng loạt khi chưa hiểu phạm vi tác động.
- Replay chấp nhận khả năng giao ít nhất một lần và consumer có idempotency.
- Payload sửa đổi có audit và liên kết với message gốc.
- Đối soát dùng nguồn chuẩn, khóa đối chiếu và checkpoint rõ ràng.
- Sai lệch nghiệp vụ được sửa bằng thao tác an toàn hoặc compensating event.
- Báo cáo cuối lưu số lượng, kết quả, nguyên nhân và các trường hợp còn mở.

DLQ là nơi cách ly message để xử lý có chủ đích, không phải điểm kết thúc của quy trình. Một quy trình phục hồi đáng tin cậy cần phân loại nguyên nhân, sửa lỗi, replay theo phạm vi nhỏ và có thể tiếp tục, ngăn tác động trùng bằng idempotency, rồi đối soát với nguồn dữ liệu chuẩn. Khi phối hợp đúng cơ chế của Kafka, RabbitMQ hoặc Pulsar với binding và binder của Spring Cloud Stream, nhóm vận hành có thể phục hồi message lỗi mà vẫn kiểm soát được trạng thái nghiệp vụ.
