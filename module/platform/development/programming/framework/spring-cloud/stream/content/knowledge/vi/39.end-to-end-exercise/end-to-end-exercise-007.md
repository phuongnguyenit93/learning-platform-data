# Đưa sự kiện lỗi vào DLQ và phát lại có kiểm soát

Trong một hệ thống Spring Cloud Stream, consumer có thể gặp lỗi khi xử lý event: dịch vụ thanh toán tạm thời không truy cập được, database hết connection, payload không còn tương thích schema, hoặc dữ liệu nghiệp vụ vi phạm quy tắc. Nếu message cứ được giao lại vô hạn, một event lỗi có thể chiếm consumer, làm backlog tăng và ảnh hưởng các event bình thường. Nếu message bị bỏ sau lỗi, hệ thống có nguy cơ mất tác dụng nghiệp vụ.

**Dead Letter Queue (DLQ)** là nơi lưu message đã thất bại sau chính sách retry để đội vận hành điều tra, đối soát và quyết định xử lý tiếp. Với Kafka, DLQ thường là một topic; với RabbitMQ là queue được gắn qua dead-letter exchange (DLX); với Pulsar là dead letter topic. DLQ giúp cô lập message lỗi, nhưng không tự sửa dữ liệu, không tự bảo đảm message sẽ được xử lý lại và cũng không tự cung cấp một quy trình replay an toàn.

Bài thực hành này xây một quy trình hoàn chỉnh: phân loại lỗi, retry có giới hạn, đưa event vào DLQ, lưu metadata để truy vết, sửa nguyên nhân, chọn một tập event được phép phát lại, kiểm soát tốc độ và thứ tự, ngăn lặp vô hạn, xác nhận kết quả rồi lưu event không thể khôi phục vào parking lot/quarantine. Ví dụ chính dùng Spring Cloud Stream với Kafka; các phần sau so sánh cách cấu hình và replay trên RabbitMQ và Pulsar.

Đây là bài thực hành tổng hợp trong module SPRING_CLOUD_STREAM, nơi ứng dụng event-driven được xây dựng bằng các hàm `Supplier`, `Function` và `Consumer`, kết nối qua binding/binder tới Kafka, RabbitMQ hoặc Pulsar. Quy trình DLQ/replay phải phù hợp với consumer group, partition/subscription, message schema, retry/DLQ và delivery guarantee của broker đang dùng.

## Mục tiêu thực hành

Hoàn thành bài này, bạn có thể:

- Phân biệt lỗi tạm thời, lỗi dữ liệu và lỗi nghiệp vụ không thể retry.
- Thiết kế retry có giới hạn và backoff trước khi đưa message vào DLQ.
- Bật DLQ cho consumer có group trong Kafka binder.
- Cấu hình DLX/DLQ, republish và retry cho RabbitMQ binder.
- Hiểu DLQ/retry topic và acknowledgment theo subscription của Pulsar.
- Bảo toàn event ID, destination, partition/key, schema version và thông tin lỗi.
- Viết một replay worker riêng, có giới hạn số lần phát lại.
- Chuyển event lỗi vĩnh viễn sang parking lot để không lặp vô hạn.
- Phát lại theo batch, filter, rate limit và thứ tự được phê duyệt.
- Bảo vệ side effect bằng idempotency và kiểm tra kết quả end-to-end.
- Vận hành, audit và kiểm thử tình huống publish lại thất bại.

## 1. Bối cảnh bài toán

Giả sử hệ thống nhận event `OrderCreated` từ topic `orders.created`. Function `processOrder` xác thực event, lưu đơn hàng và phát `OrderAccepted`.

~~~text
Producer
   |
   v
orders.created
   |
   v
Spring Cloud Stream consumer group: order-service
   |
   +--> validate --> persist order --> publish OrderAccepted
   |
   +--> lỗi tạm thời: retry có backoff
   |
   +--> retry hết / lỗi không retry: DLQ
                              |
                              v
                     Điều tra và phân loại
                              |
                    +---------+---------+
                    |                   |
                 Khắc phục          Không thể sửa
                    |                   |
                    v                   v
              Replay có kiểm soát   Parking lot
                    |
                    v
             orders.created
                    |
                    v
            Consumer xử lý lại
~~~

DLQ là một vùng cách ly. Replay là một hành động có chủ đích để đưa event từ vùng cách ly trở lại một luồng xử lý. Không nên coi DLQ như một retry queue tự động: retry thường diễn ra trong thời gian ngắn theo policy; DLQ thường giữ message để con người hoặc quy trình recovery quyết định.

### 1.1. Các khái niệm cần phân biệt

| Khái niệm | Mục đích | Câu hỏi cần trả lời |
|---|---|---|
| Retry | Thử lại một thao tác có khả năng thành công sau đó | Lỗi có thể tự hết trong một khoảng ngắn không? |
| Retry topic/queue | Lưu message chờ một khoảng thời gian trước lần thử tiếp | Có cần delay mà không giữ consumer thread không? |
| DLQ/DLT | Cách ly message đã vượt chính sách retry | Message nào thất bại và vì sao? |
| Parking lot/quarantine | Giữ message không còn được tự động replay | Ai sẽ quyết định sửa hoặc bỏ message? |
| Replay | Phát lại một event đã lưu trong DLQ/parking lot | Event nào được phép quay lại, khi nào và bao nhiêu lần? |
| Reconciliation | Đối chiếu trạng thái nghiệp vụ sau lỗi | Side effect đã xảy ra một phần hay chưa? |

Tên gọi DLQ, DLT, retry topic và parking lot khác nhau theo broker, nhưng cần giữ sự phân biệt về mục đích. Một DLQ có thể là nơi lưu lâu dài; retry topic có thể được tiêu thụ tự động theo lịch; parking lot là nơi dừng vòng lặp tự động sau khi đã hết chính sách replay.

## 2. Phân loại lỗi trước khi chọn retry

Không phải exception nào cũng nên được retry. Hãy phân loại theo khả năng khắc phục và tác động khi thử lại.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời (transient) | Timeout mạng, HTTP 503, broker/database failover | Retry có backoff và giới hạn |
| Quá tải (throttling) | HTTP 429, connection pool bão hòa | Retry sau thời gian chờ, giảm tốc độ |
| Dữ liệu/serialization | JSON thiếu field, schema không tương thích, payload hỏng | DLQ sớm để sửa dữ liệu hoặc code |
| Nghiệp vụ không hợp lệ | Đơn hàng tham chiếu khách hàng không tồn tại, trạng thái không cho phép | Quarantine hoặc yêu cầu đối soát |
| Xác thực/phân quyền | Token hết hạn, credential sai, ACL từ chối | Sửa cấu hình/quyền; không retry dày đặc |
| Lỗi code | Null handling, bug chuyển đổi, lỗi invariant | Giữ message trong DLQ, sửa release rồi replay |
| Không rõ nguyên nhân | Exception chưa phân loại | Retry rất hạn chế, sau đó DLQ và điều tra |

Một lỗi `TimeoutException` có thể là transient, nhưng không phải mọi timeout đều an toàn để retry. Request có thể đã được server xử lý nhưng response bị mất. Nếu retry tạo lại thanh toán hoặc gửi email, tác dụng phụ có thể lặp. Dùng idempotency key ở hệ thống đích và xác minh trạng thái trước khi phát lại.

### 2.1. Quy tắc retry

Một policy retry nên xác định:

- Tổng số lần thử, tính cả lần đầu hay chỉ các lần retry.
- Những exception được retry và những exception phải đi thẳng DLQ.
- Backoff ban đầu, backoff tối đa và hệ số tăng.
- Jitter để nhiều consumer không retry đồng loạt.
- Timeout tổng của một event.
- Giới hạn retry theo thời gian và tải của dependency.
- Hành vi khi chính thao tác publish sang DLQ thất bại.

Ví dụ backoff tăng dần:

| Lần thử | Thời gian chờ minh họa |
|---:|---:|
| 1 | Xử lý ngay |
| 2 | 1 giây |
| 3 | 2 giây |
| 4 | 4 giây |
| 5 | 8 giây |
| Sau đó | Chuyển DLQ hoặc retry topic theo policy |

Các thời gian trên chỉ là ví dụ. Thêm jitter và giới hạn thời gian tổng để tránh retry storm. Không giữ một consumer thread bị treo quá lâu chỉ để chờ dependency phục hồi.

### 2.2. Retry tại chỗ và retry qua broker

**Retry tại chỗ** (binder retry hoặc listener retry) thường đơn giản, giữ nguyên message trong consumer flow và phù hợp với số lần thử ít, thời gian ngắn. Trong một số cấu hình, consumer thread bị giữ trong backoff, làm message khác chờ.

**Retry qua topic/queue** đẩy message sang một destination chờ với TTL/delay. Consumer có thể tiếp tục xử lý event khác trong khi event lỗi đợi đến thời điểm thử lại. Cần thiết kế topology, header đếm lần thử, routing quay về queue gốc và giới hạn số vòng.

Không xếp chồng nhiều tầng retry mà không có ngân sách chung. Ví dụ binder retry 3 lần, HTTP client retry 3 lần và retry worker retry 3 vòng có thể tạo tới hàng chục lần gọi downstream cho một event.

## 3. Event envelope và metadata phục vụ recovery

Khi đưa message vào DLQ, phải giữ đủ thông tin để hiểu message đến từ đâu và có thể replay như thế nào. Không chỉ lưu exception message.

Ví dụ event envelope:

~~~json
{
  "eventId": "evt-01J8ORDER7K3",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "aggregateId": "order-1042",
  "aggregateSequence": 17,
  "occurredAt": "2026-11-24T09:10:00Z",
  "correlationId": "checkout-883",
  "tenantId": "tenant-a",
  "payload": {
    "orderId": "order-1042",
    "customerId": "customer-91",
    "currency": "VND",
    "total": 1250000
  }
}
~~~

Đây là envelope nghiệp vụ. Metadata vận chuyển và lỗi nên được lưu ở message headers hoặc một failure envelope riêng:

| Trường | Mục đích |
|---|---|
| `eventId` | Định danh ổn định để deduplicate |
| `eventType`, `schemaVersion` | Chọn deserializer/handler đúng |
| `aggregateId`, `aggregateSequence` | Khôi phục thứ tự theo entity |
| `originalDestination` | Destination ban đầu |
| `consumerGroup`/subscription | Consumer đã xử lý message |
| `originalPartition`, `originalOffset` hoặc message ID | Truy vết vị trí nguồn |
| `failedAt`, `occurredAt` | Tính tuổi message và thời gian tồn tại |
| `attemptCount` | Giới hạn vòng retry/replay |
| `exceptionType`, `errorCode` | Phân loại lỗi |
| `exceptionMessage` | Mô tả lỗi đã làm sạch |
| `stackTraceRef` | Tham chiếu log/trace, tránh header quá lớn |
| `replayBatchId`, `replayedBy` | Audit lần replay |

Giữ nguyên payload gốc. Nếu cần sửa payload, lưu cả bản gốc, bản đã sửa, người phê duyệt, lý do và version schema. Không ghi token, mật khẩu, dữ liệu thẻ thanh toán hoặc toàn bộ PII vào exception header.

### 3.1. Không đồng nhất event ID và broker message ID

Broker message ID, Kafka offset, Rabbit delivery tag hoặc Pulsar message ID là metadata vận chuyển. Chúng không thay thế `eventId` nghiệp vụ:

- Kafka offset chỉ có nghĩa trong một topic-partition.
- Rabbit delivery tag gắn với channel và lần delivery, có thể đổi khi redelivery.
- Pulsar message ID xác định vị trí trong ledger/topic, còn `eventId` theo hợp đồng event.

Khi replay, message mới có thể có broker ID mới. Hãy giữ event ID gốc để consumer nhận ra đây là cùng một tác dụng nghiệp vụ.

## 4. Quy trình xử lý lỗi tổng thể

~~~mermaid
flowchart TD
    A[Consumer nhận event] --> B[Validate và xử lý]
    B -->|Thành công| C[Commit offset / ACK]
    B -->|Lỗi transient| D{Còn retry budget?}
    D -->|Có| E[Backoff và thử lại]
    E --> B
    D -->|Không| F[Publish/route vào DLQ]
    B -->|Lỗi permanent| F
    F --> G{DLQ publish thành công?}
    G -->|Không| H[Giữ nguồn chưa ACK / retry recovery]
    H --> F
    G -->|Có| I[ACK nguồn theo semantics binder]
    I --> J[Điều tra, sửa nguyên nhân]
    J --> K{Được phê duyệt replay?}
    K -->|Không| L[Giữ trong quarantine/parking lot]
    K -->|Có| M[Replay batch có giới hạn]
    M --> N{Xử lý thành công?}
    N -->|Có| O[Đánh dấu recovered]
    N -->|Không| P{Đã hết replay budget?}
    P -->|Chưa| M
    P -->|Rồi| L
~~~

Điểm quan trọng là không xác nhận message nguồn đã xử lý xong trước khi việc chuyển message lỗi sang DLQ được đảm bảo theo cơ chế của binder/broker. Nếu publish DLQ thất bại mà source vẫn được ACK, message có thể mất. Nếu publish DLQ thành công nhưng source ACK thất bại, có thể có bản sao trong DLQ; consumer recovery phải idempotent.

## 5. Cấu hình retry và DLQ chung trong Spring Cloud Stream

Spring Cloud Stream cung cấp các cơ chế xử lý lỗi ở tầng message handler, nhưng khả năng cụ thể phụ thuộc binder và middleware. Với imperative `Function<T,R>` hoặc `Consumer<T>`, exception từ handler được truyền về binder để áp dụng retry/error handler. Khi không cấu hình recovery phù hợp, lỗi có thể chỉ được log rồi message bị drop. Không mặc định rằng mọi binder đều có DLQ giống nhau.

Ví dụ binding input:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-service
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
~~~

Các thuộc tính consumer ở trên là cấu hình chung của binding. Tên `processOrder-in-0` phải khớp binding được suy ra từ function `processOrder`. `group` tạo consumer group ổn định; DLQ của Kafka binder yêu cầu group được khai báo rõ ràng.

### 5.1. Imperative và reactive function khác nhau

Với imperative handler, Spring Cloud Stream có thể áp dụng retry ở tầng message handler. Với reactive function như `Function<Flux<T>, Flux<R>>`, function nối Publisher thay vì được gọi độc lập cho từng message; retry/error handling phải được xây dựng bằng Reactor operators trong pipeline. Không sao chép `max-attempts` rồi cho rằng mọi lỗi bất đồng bộ trong `Flux` tự động đi vào DLQ. Xem lại phần reactive error handling và binder-specific semantics.

### 5.2. Không dùng custom ErrorMessage handler mà vẫn kỳ vọng binder DLQ

Nếu ứng dụng định nghĩa custom `Consumer<ErrorMessage>` cho binding, custom handler đó có thể thay thế framework/binder error handlers. Trong trường hợp này, cơ chế DLQ của binder không còn tự chạy như trước. Nếu cần custom error handling, hãy chủ động gửi message lỗi tới destination recovery và kiểm thử đường ACK/publish; không cấu hình đồng thời hai cơ chế mà không hiểu thứ tự xử lý.

## 6. Kafka binder: bật DLQ cho consumer group

Kafka binder không bật DLQ mặc định. Consumer phải có group tường minh và phải bật `enable-dlq` cho đúng binding.

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-service
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
~~~

Thuộc tính trên có đường dẫn đầy đủ `spring.cloud.stream.kafka.bindings.processOrder-in-0.consumer.enable-dlq`. Cần đặt đúng tên input binding; đặt property ở binding output hoặc một tên binding khác sẽ không bật DLQ cho consumer đang xử lý event.

Khi retry hết, record được gửi tới DLQ topic. Theo mặc định tên DLQ là:

~~~text
error.<destination>.<group>
~~~

Với ví dụ trên:

~~~text
error.orders.created.order-service
~~~

Có thể cấu hình tên bằng `dlq-name` hoặc bean `DlqDestinationResolver`. Kafka DLQ không áp dụng cho anonymous group và không được dùng khi `destinationIsPattern=true`.

### 6.1. Header lỗi và partition

Kafka binder bổ sung các header như:

- `x-original-topic`
- `x-exception-message`
- `x-exception-stacktrace`

Các header này được biểu diễn dưới dạng `byte[]` trong Kafka record. Mặc định record lỗi được gửi vào cùng số partition ở DLQ như partition nguồn. Đây là điểm hữu ích nếu replay cần giữ thứ tự tương đối theo partition.

Khi thay đổi số partition DLQ:

- Nếu không cấu hình `dlq-partitions`, binder thường tạo số partition tương ứng với topic nguồn.
- Nếu đặt `dlq-partitions: 1`, mọi record lỗi có thể đi vào partition 0 nếu không có `DlqPartitionFunction`.
- Nếu đặt số partition lớn hơn 1, cần cung cấp `DlqPartitionFunction` để quyết định partition.

Không tạo DLQ chỉ có một partition rồi giả định có thể giữ thứ tự cho mọi partition nguồn. Nếu thứ tự theo key là yêu cầu nghiệp vụ, thiết kế partitioning và replay phải được kiểm tra rõ.

### 6.2. Lưu ý về max-attempts

Khi DLQ được bật, retry của binder tôn trọng `max-attempts`. Nếu DLQ không bật, tài liệu Kafka binder hiện hành nêu rõ `max-attempts` không nhất thiết điều khiển retry theo cách mong đợi; lỗi có thể quay về container defaults của Spring for Apache Kafka. Vì vậy, hãy kiểm tra cả `enable-dlq` và error handler của container khi muốn xác định số lần thử chính xác.

## 7. Kafka: xây replay worker riêng

Spring Cloud Stream không tự quyết định cách xử lý record trong DLQ. Ứng dụng recovery phải đọc DLQ, kiểm tra message, quyết định phát lại hoặc chuyển parking lot. Có hai chiến lược thường dùng:

1. Chạy replay khi consumer chính đang dừng hoặc đã được tạm ngưng để tránh lỗi transient bị thử lại liên tục.
2. Dùng hai giai đoạn: DLQ → replay staging topic → original topic. Giai đoạn staging cho phép review, rate limit và audit trước khi message quay lại luồng chính.

### 7.1. Cấu hình binding cho replay

Ví dụ application replay:

~~~yaml
spring:
  cloud:
    function:
      definition: replayDlq
    stream:
      output-bindings: orders-replay-out-0;orders-parking-out-0
      bindings:
        replayDlq-in-0:
          destination: error.orders.created.order-service
          group: order-dlq-replay
        orders-replay-out-0:
          destination: orders.created
        orders-parking-out-0:
          destination: orders.created.parking-lot
~~~

`order-dlq-replay` là group riêng của worker recovery. Không dùng lại group `order-service`, vì worker đọc DLQ là một luồng xử lý khác. Đặt group riêng giúp offset của DLQ được quản lý độc lập.

### 7.2. Replay có giới hạn lần thử

Ví dụ sau minh họa quyết định giữa replay và parking lot. Trong triển khai thực tế, cần kiểm tra quyền replay, batch được phê duyệt, trạng thái sửa lỗi và kết quả publish trước khi ACK nguồn DLQ.

~~~java
@Configuration
class OrderDlqReplayConfiguration {

    private static final String REPLAY_COUNT = "x-replay-count";
    private static final int MAX_REPLAYS = 3;

    @Bean
    Consumer<Message<byte[]>> replayDlq(StreamBridge streamBridge) {
        return failed -> {
            Integer current = failed.getHeaders()
                    .get(REPLAY_COUNT, Integer.class);
            int replayCount = current == null ? 0 : current;

            String output = replayCount < MAX_REPLAYS
                    ? "orders-replay-out-0"
                    : "orders-parking-out-0";

            MessageBuilder<byte[]> builder =
                    MessageBuilder.fromMessage(failed)
                            .setHeader(REPLAY_COUNT, replayCount + 1);

            Object sourcePartition = failed.getHeaders()
                    .get(KafkaHeaders.RECEIVED_PARTITION_ID);
            if (sourcePartition instanceof Integer partition) {
                builder.setHeader(BinderHeaders.PARTITION_OVERRIDE, partition);
            }

            Message<byte[]> recoveryMessage = builder.build();
            boolean accepted = streamBridge.send(output, recoveryMessage);
            if (!accepted) {
                throw new IllegalStateException(
                        "Recovery publish was not accepted: " + output);
            }
        };
    }
}
~~~

Imports chính:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.cloud.stream.binder.BinderHeaders;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.kafka.support.KafkaHeaders;
import java.util.function.Consumer;
~~~

Đây là ví dụ luồng điều khiển, không phải bằng chứng rằng publish đã được broker lưu bền vững. `StreamBridge.send()` trả `true` cho biết message đã được chấp nhận bởi output channel; nó không chứng minh consumer đích đã xử lý. Production cần cấu hình producer confirmation/transaction phù hợp và chỉ ACK record DLQ sau khi output recovery được xác nhận theo semantics của binder. Nếu publish thất bại, consumer phải ném lỗi để record DLQ còn cơ hội redelivery.

Header `BinderHeaders.PARTITION_OVERRIDE` giữ số partition nguồn trong ví dụ. Chỉ sử dụng khi topic đích có partition tương thích và business ordering yêu cầu giữ partition. Nếu số partition thay đổi, cần mapping partition mới có chủ đích; không ép một số partition không tồn tại.

### 7.3. Giới hạn replay không phải giới hạn retry của consumer chính

`x-replay-count` là metadata của quy trình recovery. Consumer chính vẫn có retry budget riêng cho mỗi lần message được nhận. Nếu event được replay rồi tiếp tục lỗi, nó có thể quay lại DLQ. Replay worker đọc lại header và tăng bộ đếm cho đến khi chuyển sang parking lot.

Không dùng một header tùy ý do producer bên ngoài có thể tự đặt để quyết định vô hạn replay. Replay worker phải xác minh nguồn DLQ, batch ID và policy server-side; header chỉ là dữ liệu theo dõi.

## 8. RabbitMQ binder: DLX và DLQ

RabbitMQ binder ánh xạ destination thành exchange và queue theo consumer group. Với group đã khai báo, có thể yêu cầu binder tự tạo dead-letter exchange và dead-letter queue.

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-service
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              requeue-rejected: false
~~~

Các thuộc tính quan trọng:

- `auto-bind-dlq`: tạo DLQ và DLX/routing infrastructure cho binding.
- `republish-to-dlq`: binder publish message thất bại sang DLQ và thêm metadata exception.
- `requeue-rejected`: khi retry bị tắt hoặc republish không dùng, có requeue message về queue nguồn hay không.
- `dead-letter-queue-name`, `dead-letter-exchange`, `dead-letter-routing-key`: tùy chỉnh topology.
- `dlq-ttl`: TTL của DLQ khi dùng làm một tầng delayed retry.

Tên DLQ mặc định thường là destination cộng `.dlq` (với group/prefix theo topology). Khi `max-attempts > 1`, binder retry trước; sau khi hết retry, message được chuyển DLQ. Nếu `max-attempts=1`, cần để `requeue-rejected=false` để message không bị đưa lại queue vô hạn.

### 8.1. Tránh vòng lặp requeue vô hạn

Đặt `requeue-rejected=true` khi `republish-to-dlq=false` có thể làm message bị requeue và redeliver liên tục. Điều này chỉ phù hợp nếu nguyên nhân chắc chắn transient và có backoff/giới hạn khác. Với lỗi dữ liệu hoặc bug code, message sẽ chiếm consumer và tạo tải liên tục.

Một số exception đặc biệt như `ImmediateAcknowledgeAmqpException` có thể bypass DLQ và khiến message bị discard. Không ném exception này cho lỗi chưa được đối soát nếu chính sách yêu cầu giữ message.

### 8.2. Xác nhận publish sang DLQ

Với RabbitMQ binder, nếu consumer transacted, việc publish sang DLQ có thể tham gia transaction từ các phiên bản hỗ trợ tương ứng. Nếu connection factory bật publisher confirms/returns, binder có thể chờ xác nhận và kiểm tra message có bị return hay không. Nếu nhận negative ack hoặc returned message, binder có thể để broker thực hiện dead-letter theo đường reject.

Kiểm tra phiên bản Rabbit binder và cấu hình confirms trước khi dựa vào semantics này. Không giả định `republish-to-dlq=true` đồng nghĩa mọi lần publish luôn thành công.

## 9. RabbitMQ: phát lại từ DLQ

Spring Cloud Stream Rabbit binder không cung cấp một cơ chế chuẩn duy nhất để tiêu thụ DLQ và đưa message về queue gốc. Có thể xây một ứng dụng recovery bằng `@RabbitListener`, `RabbitTemplate`, hoặc một consumer binding riêng.

Với destination không partition, ví dụ đơn giản:

~~~java
@Component
class RabbitDlqReplayListener {

    private static final String DLQ = "orders.created.order-service.dlq";
    private static final String ORIGINAL_QUEUE = "orders.created.order-service";
    private static final String PARKING_LOT = "orders.created.order-service.parking";
    private static final int MAX_REPLAYS = 3;

    private final RabbitTemplate rabbitTemplate;

    RabbitDlqReplayListener(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @RabbitListener(queues = DLQ)
    void replay(Message failed) {
        long count = failed.getMessageProperties().getRetryCount();
        if (count < MAX_REPLAYS) {
            failed.getMessageProperties().incrementRetryCount();
            rabbitTemplate.send(ORIGINAL_QUEUE, failed);
        }
        else {
            rabbitTemplate.send(PARKING_LOT, failed);
        }
    }
}
~~~

Ví dụ minh họa retry counter và routing queue trực tiếp. Khi dùng topology exchange/routing key phức tạp, phải khôi phục đúng exchange và routing key gốc từ metadata:

- Nếu `republish-to-dlq=false`, RabbitMQ thường ghi thông tin dead-letter trong header `x-death` (queue, exchange, routing-keys, reason, count).
- Nếu `republish-to-dlq=true`, binder thêm header về original exchange/routing key cùng exception metadata.
- Với partitioned destination, nhiều partition có thể dùng chung một DLQ; replay phải lấy thông tin partition/routing từ header thay vì gửi mọi message vào một partition mặc định.

### 9.1. Delay replay bằng TTL hoặc delayed exchange

Có thể cấu hình DLQ có TTL và dead-letter exchange trỏ lại queue nguồn để tạo vòng retry có delay. Cách này phù hợp với lỗi transient có thể tự hết, nhưng phải có bộ đếm `x-death` hoặc retry counter và một điểm dừng. Nếu không có giới hạn, message poison có thể đi qua DLQ → queue gốc mãi mãi.

RabbitMQ Delayed Message Exchange yêu cầu plugin tương ứng trên broker. Nếu dùng plugin, cấu hình exchange type và routing key phải đồng nhất với topology. Không nhầm delayed delivery với một parking lot cho người vận hành.

### 9.2. Xác nhận khi replay RabbitMQ

Replay worker phải không ACK message DLQ cho đến khi message đã được publish sang queue đích và có xác nhận theo cấu hình publisher. Nếu worker chết sau publish nhưng trước ACK, message DLQ có thể được giao lại và publish duplicate. Vì vậy, event ID/idempotency vẫn cần thiết ngay cả khi có publisher confirms.

## 10. Pulsar binder: retry topic và dead letter topic

Spring Cloud Stream có binder cho Apache Pulsar. Binder dựa trên Spring for Apache Pulsar và sử dụng các cấu hình producer/consumer của Pulsar. Khả năng DLQ/retry cụ thể phụ thuộc version của binder, Spring Boot/Spring Pulsar, subscription type và cách consumer được tạo.

Ví dụ cấu hình consumer Pulsar ở cấp Spring Boot:

~~~yaml
spring:
  pulsar:
    consumer:
      retry-enable: true
      dead-letter-policy:
        max-redeliver-count: 5
        dead-letter-topic: persistent://public/default/orders-DLQ
        retry-letter-topic: persistent://public/default/orders-RETRY
        initial-subscription-name: orders-dlq-ops
~~~

Đây là nhóm property của Spring for Apache Pulsar. Nếu ứng dụng có nhiều input binding, cấu hình gốc có thể áp dụng cho tất cả consumer được tạo từ Boot auto-configuration. Dùng extended binding properties/customizer theo version binder để cô lập cấu hình từng binding và xác minh property nào thực sự được chuyển xuống consumer.

### 10.1. Subscription type ảnh hưởng DLQ

Với Spring for Apache Pulsar `PulsarListener`, DLQ theo `DeadLetterPolicy` tiêu chuẩn chỉ hỗ trợ `Shared` subscription. `Exclusive` và `Failover` được thiết kế với đảm bảo thứ tự; redelivery/DLQ có thể làm thay đổi thứ tự. Với các subscription khác, Spring for Apache Pulsar cung cấp `PulsarConsumerErrorHandler`/recoverer để ứng dụng tự điều khiển recovery.

Pulsar native client có thể hỗ trợ DLQ cho `Shared` và `Key_Shared` theo version/client. Không suy ra rằng mọi subscription type trong binder đều có cùng semantics. Đọc tài liệu đúng version và test với topic partitioned.

### 10.2. Negative acknowledgment và retry letter topic

Pulsar `negativeAcknowledge` yêu cầu broker redeliver message. Nhưng bộ đếm redelivery của negative acknowledgment được giữ trong memory; khi subscription dispatcher bị đóng, broker restart, topic unload hoặc consumer disconnect, bộ đếm có thể reset. Vì vậy `maxRedeliverCount` có thể không bao giờ đạt ngưỡng nếu chỉ dựa trên negative acknowledgment.

Với retry có giới hạn đáng tin cậy, Pulsar native client cung cấp `reconsumeLater` cùng `enableRetry(true)`. Số lần retry được lưu trong message property trên retry letter topic và tồn tại qua các lần restart/rebalance. Khi hết `maxRedeliverCount`, message chuyển tới dead letter topic. Retry letter topic khác với delayed delivery: nó biểu diễn vòng retry do lỗi xử lý.

### 10.3. Phát lại từ Pulsar DLQ

Replay worker đọc dead letter topic bằng subscription riêng, xác thực message, rồi publish về topic gốc hoặc replay topic. Chỉ ACK message DLQ sau khi publish đích đã thành công theo producer confirmation phù hợp. Giữ `eventId`, key, schema version và custom properties; broker MessageId mới sẽ được tạo khi publish lại.

Với `Shared` hoặc `Key_Shared`, chú ý acknowledgment cá thể và ordering theo key. Cumulative acknowledgment không phù hợp với `Shared`/`Key_Shared` khi nhiều consumer cùng truy cập subscription. Kiểm tra policy của subscription trước khi replay.

## 11. Replay có kiểm soát: chính sách vận hành

Trước khi phát lại, trả lời đủ các câu hỏi:

1. Nguyên nhân gốc đã được sửa hoặc có workaround an toàn chưa?
2. Event nào được chọn: toàn DLQ, theo khoảng thời gian, tenant, event ID hay error code?
3. Schema/version của event có được consumer hiện tại hỗ trợ không?
4. Side effect trước lần lỗi có thể đã xảy ra chưa?
5. Replay có ảnh hưởng thứ tự theo aggregate/partition/key không?
6. Consumer chính có đang chạy không? Nếu có, replay có làm retry budget cạn ngay không?
7. Tốc độ replay tối đa mà DB/API downstream chịu được là bao nhiêu?
8. Ai phê duyệt, ai chạy, batch nào và kết quả được ghi ở đâu?
9. Event nào sẽ đi vào parking lot nếu replay tiếp tục thất bại?

### 11.1. Chỉ phát lại event được chọn

Không replay toàn bộ DLQ theo mặc định. Hãy hỗ trợ filter:

- Khoảng `failedAt`.
- `eventId` hoặc danh sách ID đã duyệt.
- `errorCode`/`exceptionType`.
- `tenantId` đã xác thực.
- `schemaVersion`.
- Destination/group gốc.
- Replay batch ID.

Không cho người vận hành nhập tùy ý destination hoặc topic trong command nếu service có thể ánh xạ từ cấu hình allowlist. Không dùng dữ liệu header không đáng tin để định tuyến message ra ngoài phạm vi.

### 11.2. Rate limit và batch size

Replay nhanh có thể tạo burst lớn vào consumer và downstream. Đặt:

- Số message tối đa mỗi batch.
- Số message/giây.
- Số consumer replay đồng thời.
- Khoảng nghỉ giữa batch.
- Ngưỡng dừng khi error rate hoặc lag tăng.
- Giờ chạy được phép và giới hạn theo tenant.

Ví dụ kế hoạch:

| Giai đoạn | Số event | Tốc độ | Điều kiện tiếp tục |
|---|---:|---:|---|
| Smoke replay | 10 | 1 event/giây | Không có duplicate/lỗi mới |
| Pilot | 100 | 5 event/giây | Error rate và DB latency trong SLO |
| Batch chính | 1.000 | 20 event/giây | Lag không tăng vượt ngưỡng |
| Phần còn lại | Theo phê duyệt | Điều chỉnh động | Có người vận hành theo dõi |

Các con số chỉ là minh họa. Tốc độ thực tế phải dựa trên capacity của consumer và hệ thống downstream.

### 11.3. Không phá thứ tự nghiệp vụ

Kafka giữ thứ tự trong một partition, RabbitMQ phụ thuộc queue/consumer/prefetch/ack, Pulsar phụ thuộc subscription type và key. Replay có thể đưa event cũ vào sau event mới đã được xử lý.

Ví dụ `OrderCreated` ở sequence 10 bị DLQ, còn `OrderCancelled` sequence 11 đã được xử lý. Replay sequence 10 sau đó có thể làm trạng thái đơn hàng sai nếu handler không kiểm tra sequence.

Biện pháp:

- Replay theo `aggregateId` và `aggregateSequence`.
- Chặn hoặc tạm dừng event mới của cùng aggregate nếu nghiệp vụ cần strict ordering.
- Đưa replay vào staging topic để sắp thứ tự trước khi phát.
- Dùng version check/CAS ở database.
- Không mặc định khôi phục offset cũ là cách replay đúng; nó có thể phát lại toàn bộ partition.

### 11.4. Replay phải idempotent

Một replay worker có thể publish thành công rồi crash trước khi ACK message DLQ. Message sẽ được giao lại và có thể publish lần nữa. Consumer đích phải xử lý duplicate an toàn.

Mẫu bảng dedup:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một database transaction:

1. Insert `eventId` bằng unique constraint.
2. Nếu đã tồn tại, không lặp side effect.
3. Nếu mới, cập nhật trạng thái nghiệp vụ.
4. Commit marker và side effect cùng transaction.

Không dùng `SELECT` rồi `INSERT` tách rời vì hai consumer có thể cùng vượt qua bước kiểm tra. Với API bên ngoài, gửi idempotency key ổn định theo `eventId`; DB transaction cục bộ không bảo vệ một HTTP call.

## 12. Parking lot và quarantine

Parking lot là điểm dừng cuối cho event đã vượt retry/replay budget hoặc không thể tự sửa. Khác với DLQ, parking lot không được tự động đưa message về nguồn.

Nên chuyển vào parking lot khi:

- Schema không thể giải mã bằng version code hiện tại.
- Event nghiệp vụ không hợp lệ và cần người sở hữu dữ liệu sửa.
- Replay nhiều lần vẫn thất bại.
- Thiếu quyền hoặc thông tin để xử lý an toàn.
- Side effect đã xảy ra một phần và cần reconciliation.

Một record parking lot cần có payload gốc, event ID và metadata nguồn, số lần xử lý/replay, lý do cuối cùng, tham chiếu trace/log, người hoặc service đưa vào parking lot, thời điểm và replay batch ID, trạng thái xử lý thủ công.

Đặt retention và quyền truy cập riêng cho parking lot. Có thể chứa payload nhạy cảm hoặc dữ liệu không hợp lệ; chỉ cấp quyền cho nhóm vận hành cần thiết. Không purge chỉ để làm backlog về 0.

## 13. Ví dụ end-to-end: đơn hàng lỗi do currency chưa hỗ trợ

Ta triển khai consumer:

~~~java
@SpringBootApplication
public class OrderServiceApplication {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService service) {
        return service::process;
    }
}
~~~

Service:

~~~java
@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void process(OrderCreated event) {
        if (!Set.of("VND", "USD", "EUR").contains(event.currency())) {
            throw new UnsupportedCurrencyException(event.currency());
        }
        repository.createIfAbsent(
                event.eventId(),
                event.orderId(),
                event.currency(),
                event.total());
    }
}
~~~

Giả sử producer gửi `currency=XYZ`. Consumer retry theo policy, sau đó Kafka binder đưa record vào `error.orders.created.order-service`. Đội vận hành kiểm tra event và xác nhận đây là lỗi dữ liệu từ producer. Producer được sửa để phát currency hợp lệ; event cũ được chọn theo `eventId` và phê duyệt replay.

### 13.1. Checklist trước replay

- [ ] Xác nhận producer đã sửa.
- [ ] Kiểm tra consumer version đã hỗ trợ schema.
- [ ] Kiểm tra event chưa tạo order thành công trước đó.
- [ ] Kiểm tra event ID và tenant.
- [ ] Xác định partition/key cần giữ.
- [ ] Chọn batch ID và tập event.
- [ ] Chọn replay rate và max replay count.
- [ ] Kiểm tra parking lot destination.
- [ ] Ghi người phê duyệt và người vận hành.

### 13.2. Sau replay

- [ ] Số event được publish lại bằng số event đã phê duyệt trừ các event chuyển parking lot.
- [ ] Consumer xử lý thành công và dedup không phát sinh side effect trùng.
- [ ] Kafka lag/queue depth/backlog trở lại mức bình thường.
- [ ] DLQ không tiếp tục nhận cùng event do lỗi chưa sửa.
- [ ] Event không thể khôi phục có lý do và owner trong parking lot.
- [ ] Báo cáo replay lưu batch ID, thời gian, số thành công/thất bại và danh sách event.

## 14. Kiểm thử DLQ và replay

Unit test service chỉ chứng minh business exception; cần integration test với broker để xác minh DLQ, retry, ACK và replay.

### 14.1. Test tình huống cơ bản

| Kịch bản | Kết quả mong đợi |
|---|---|
| Handler thành công | Message không vào DLQ |
| Lỗi transient, dependency phục hồi trước hết retry | Xử lý thành công sau retry |
| Lỗi permanent | Sau policy, message vào DLQ |
| Publish DLQ thất bại | Source không bị ACK theo cách làm mất message |
| Replay publish thành công | DLQ source được xác nhận theo semantics đã chọn |
| Replay publish thất bại | Message DLQ có thể được redeliver |
| Replay cùng event hai lần | Consumer đích không lặp side effect |
| Replay vượt giới hạn | Message chuyển parking lot |
| Replay partition/key | Thứ tự/partition được giữ theo yêu cầu |
| DLQ schema cũ | Recovery đọc và chuyển đổi được hoặc quarantine |

### 14.2. Kafka integration test

Với Kafka Testcontainers hoặc cluster test:

1. Tạo topic `orders.created` và consumer group tường minh.
2. Bật `enable-dlq`.
3. Gửi event hợp lệ và xác nhận output.
4. Gửi event gây exception, quan sát retry count.
5. Xác nhận record xuất hiện trong `error.orders.created.order-service`.
6. Kiểm tra `x-original-topic`, exception headers và partition.
7. Chạy replay worker với một event được chọn.
8. Xác nhận message quay về topic gốc và consumer xử lý lại.
9. Gửi event lỗi lại quá giới hạn và xác nhận parking lot.
10. Kill replay worker giữa publish và source ACK để kiểm tra duplicate/idempotency.

### 14.3. RabbitMQ integration test

Với RabbitMQ Testcontainers:

1. Khai báo exchange, queue và group.
2. Bật `auto-bind-dlq`.
3. Kiểm tra DLX, DLQ và routing key được tạo.
4. Gây lỗi handler và xác nhận message vào DLQ sau retry.
5. Kiểm tra `x-death` hoặc original exchange/routing headers.
6. Replay một message về queue nguồn.
7. Xác minh giới hạn retry và parking lot.
8. Thử publisher nack/return khi gửi DLQ/replay để xác minh nguồn không bị mất.

### 14.4. Pulsar integration test

Với Pulsar Testcontainers hoặc cluster test:

1. Tạo topic và subscription type phù hợp.
2. Bật dead letter policy với topic DLQ rõ ràng.
3. Gửi message gây lỗi và xác nhận retry/redelivery.
4. Xác minh DLQ nhận message sau số lần tối đa.
5. Thử broker restart/consumer reconnect để kiểm tra retry count persistence.
6. Replay từ DLQ với subscription riêng.
7. Xác nhận message đích được publish trước khi ACK nguồn.
8. Kiểm tra thứ tự/key với Shared/Key_Shared.

### 14.5. Test Binder không thay thế broker integration

Spring Cloud Stream Test Binder phù hợp để kiểm tra function, binding và luồng message trong ứng dụng. Nó không thay thế test các đặc tính riêng như Kafka partition/offset, RabbitMQ DLX/confirm, Pulsar retry-letter topic/subscription type. Dùng Test Binder cho logic nhanh và Testcontainers/cluster test cho semantics broker.

## 15. Quan sát và vận hành

Một quy trình DLQ cần dashboard và alert:

| Tín hiệu | Mục đích |
|---|---|
| DLQ depth theo destination/group | Phát hiện message lỗi đang tích tụ |
| Số event mới vào DLQ mỗi phút | Phát hiện lỗi mới sau release |
| Tuổi message cũ nhất | Phát hiện DLQ bị bỏ quên |
| Error type/code | Phân nhóm nguyên nhân |
| Retry attempts trung bình/tối đa | Phát hiện retry storm |
| Replay success/failure | Đo hiệu quả recovery |
| Parking lot depth | Đo backlog cần người xử lý |
| Duplicate/dedup count | Phát hiện side effect lặp |
| Replay throughput và downstream latency | Bảo vệ hệ thống đích |

Không dùng event ID hoặc customer ID làm Prometheus label vì cardinality tăng không giới hạn. Đưa định danh cụ thể vào structured log/trace có kiểm soát.

### 15.1. Audit log của replay

Mỗi lần replay cần ghi:

- `replayBatchId`.
- Người/phê duyệt hoặc service identity.
- Filter và số event dự kiến.
- Destination nguồn/đích.
- Event ID hoặc danh sách tham chiếu.
- Số event đã gửi, thành công, thất bại, parking lot.
- Tốc độ và khoảng thời gian chạy.
- Version consumer được dùng.
- Kết quả cuối cùng và liên kết dashboard/runbook.

Không ghi payload nhạy cảm hoặc credential vào audit log. Cần có khả năng dừng batch đang chạy và tiếp tục từ checkpoint rõ ràng.

## 16. Runbook: message tăng trong DLQ

### Bước 1 — Xác định phạm vi

- Xác định broker, topic/queue, group/subscription.
- Kiểm tra thời điểm DLQ bắt đầu tăng.
- Tìm release/deployment gần thời điểm đó.
- Đo DLQ depth, tốc độ vào và tuổi message.

### Bước 2 — Phân loại lỗi

- Đọc error code/exception type và log/trace tham chiếu.
- Tách lỗi dữ liệu, schema, nghiệp vụ, credential, dependency và bug code.
- Kiểm tra có nhiều event cùng lỗi hay chỉ một event poison.
- Xác minh side effect có thể đã xảy ra trước khi handler thất bại.

### Bước 3 — Khắc phục nguyên nhân

- Phục hồi dependency hoặc credential.
- Sửa consumer/serializer/schema.
- Sửa dữ liệu theo quy trình có audit.
- Triển khai phiên bản đã kiểm thử.
- Xác nhận event lỗi mẫu xử lý thành công trong môi trường test.

### Bước 4 — Chuẩn bị replay

- Chọn event ID hoặc batch theo filter đã phê duyệt.
- Xác minh idempotency và ordering.
- Tạm dừng consumer chính nếu chiến lược yêu cầu.
- Đặt rate limit, max attempts và parking lot.
- Xác minh producer confirms/transaction/ACK theo broker.

### Bước 5 — Replay theo từng đợt

- Chạy smoke batch nhỏ.
- Kiểm tra kết quả và downstream.
- Tăng dần tốc độ trong giới hạn SLO.
- Dừng khi error rate, lag, latency hoặc duplicate vượt ngưỡng.
- Chuyển event lỗi lặp vào parking lot.

### Bước 6 — Đóng sự cố

- Xác nhận DLQ backlog được giải quyết hoặc có owner.
- Đối soát dữ liệu nghiệp vụ.
- Lưu audit report.
- Xóa hoặc đóng replay job theo retention.
- Cập nhật runbook/alert nếu phát hiện khoảng trống.

## 17. Những sai lầm thường gặp

1. **Không cấu hình DLQ mà cho rằng retry sẽ giữ message mãi:** lỗi có thể chỉ được log rồi drop tùy binder/error handler. Hãy xác minh recovery policy.
2. **Dùng anonymous Kafka group:** Kafka binder không hỗ trợ DLQ cho anonymous consumer group. Khai báo group ổn định.
3. **Retry vô hạn:** poison message có thể chặn consumer và tạo backlog. Đặt max attempts và parking lot.
4. **Requeue RabbitMQ liên tục:** `requeue-rejected=true` có thể gây vòng redelivery vô hạn. Chỉ dùng khi transient và có backoff/giới hạn.
5. **Cho rằng mọi binder dùng cùng property:** Kafka `enable-dlq`, Rabbit `auto-bind-dlq`, Pulsar `DeadLetterPolicy` có semantics khác nhau.
6. **Replay toàn bộ DLQ ngay lập tức:** có thể tạo burst và tái tạo lỗi. Dùng filter, batch và rate limit.
7. **Replay khi consumer chính đang chạy mà không tính retry budget:** lỗi transient có thể bị thử hết rất nhanh. Dùng pause hoặc two-stage replay.
8. **Không giữ event ID:** replay duplicate tạo side effect lặp. Giữ event ID và idempotency key.
9. **ACK nguồn trước khi publish đích được xác nhận:** có thể mất message khi publish thất bại. Phối hợp confirm/transaction/ack.
10. **Cho rằng publish một lần là xử lý một lần:** consumer đích có thể nhận duplicate. Thiết kế at-least-once và idempotent.
11. **Không giữ partition/key:** replay có thể đảo thứ tự hoặc thay đổi routing. Bảo toàn metadata theo policy.
12. **Không giới hạn replay count:** message lỗi vĩnh viễn quay vòng vô hạn. Đặt max replay và parking lot.
13. **Chỉ sửa payload trong DLQ:** mất bản gốc và audit. Lưu raw event cùng bản sửa và lý do.
14. **Dựa vào stack trace header làm hồ sơ duy nhất:** header có thể bị truncate hoặc không có ở broker. Giữ trace/log tham chiếu.
15. **Coi Pulsar negative-ack count luôn bền vững:** bộ đếm có thể reset khi dispatcher đóng. Dùng retry letter topic khi cần retry limit bền vững.
16. **Dùng DLQ Pulsar với subscription không được hỗ trợ:** xác minh Shared/Key_Shared và binder/client version.
17. **Purge DLQ để giảm cảnh báo:** có thể xóa dữ liệu cần đối soát. Chỉ xóa sau khi có quyết định và audit.
18. **Không kiểm thử lỗi publish sang DLQ:** source có thể bị ACK sai thời điểm. Test broker outage và negative confirm.

## 18. Checklist hoàn thành bài thực hành

- [ ] Function consumer được bind tới đúng destination và group.
- [ ] Retry policy có giới hạn, backoff và phân loại lỗi.
- [ ] DLQ được bật rõ ràng theo binder đang sử dụng.
- [ ] Event lỗi vào đúng DLQ sau khi hết retry.
- [ ] Metadata nguồn, event ID, schema và lỗi được giữ.
- [ ] Replay worker dùng group/subscription riêng.
- [ ] Chỉ event đã được chọn/phê duyệt mới được replay.
- [ ] Replay có rate limit, max attempts và parking lot.
- [ ] Publish đích được xác nhận trước khi ACK DLQ nguồn theo semantics broker.
- [ ] Consumer đích idempotent và giữ thứ tự theo yêu cầu.
- [ ] Có dashboard, alert và audit batch.
- [ ] Integration test có broker thật đã bao gồm duplicate và failure injection.

## Kết luận

DLQ là nơi cách ly message thất bại để điều tra và phục hồi, còn replay là một quy trình vận hành có kiểm soát. Spring Cloud Stream cung cấp các extension point và cấu hình DLQ theo binder, nhưng Kafka, RabbitMQ và Pulsar có cách định tuyến lỗi, acknowledgment, retry và metadata khác nhau. Không có một property chung có thể thay thế hiểu biết về broker.

Một quy trình recovery an toàn phải giữ event ID và metadata nguồn, retry có giới hạn, không ACK message nguồn trước khi chuyển DLQ/replay được bảo đảm, và xử lý duplicate bằng idempotency. Chỉ replay sau khi nguyên nhân được sửa, event được chọn và phê duyệt, tốc độ/partition/thứ tự được kiểm soát. Event không thể phục hồi phải dừng trong parking lot với audit và owner rõ ràng. Kiểm thử publish thất bại, consumer crash và replay duplicate là điều kiện cần trước khi đưa quy trình vào production.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.1 — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream 5.1 — Kafka Dead-Letter Topic Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — RabbitMQ Binder Usage and Properties](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/README.html)
- [Spring Cloud Stream — RabbitMQ Dead-Letter Queue Processing](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_dlq.html)
- [Spring Cloud Stream 5.1 — Apache Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring for Apache Pulsar — Message Consumption and Error Handling](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Spring Boot — Pulsar Consumer Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Apache Pulsar — Messaging, Redelivery and Dead Letter Topics](https://pulsar.apache.org/docs/5.0.x/concepts-messaging/)
