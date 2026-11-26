# Retry/requeue vô hạn và DLQ không nhận được thông điệp

## 1. Bài toán thực tế: message chạy mãi nhưng DLQ vẫn rỗng

Trong hệ thống **Spring AMQP** sử dụng **RabbitMQ**, producer gửi message bằng `RabbitTemplate` tới exchange, broker áp dụng binding để định tuyến vào queue, còn consumer xử lý qua `@RabbitListener`. Khi listener ném exception, rất dễ gặp hai triệu chứng tưởng mâu thuẫn:

- **Thông điệp bị xử lý lại vô hạn**: cùng một `eventId` hoặc payload xuất hiện hàng nghìn lần trong log; CPU tăng, consumer không xử lý được các message khác, queue depth không giảm.
- **Dead-letter queue (DLQ) không có thông điệp**: dù listener liên tục lỗi, dashboard DLQ vẫn bằng 0; có khi queue chính cũng mất message.

Ví dụ một dịch vụ thanh toán gặp message JSON thiếu trường bắt buộc:

~~~text
RabbitTemplate
   |
   v
payments.events.x --binding--> payments.process.q
                                     |
                                     v
                                @RabbitListener
                                     |
                               parse JSON lỗi
                                     |
                       lỗi được xử lý theo policy
                          /                    \
                         v                      v
                 basic.nack/reject         ACK thành công
                     /      \                    |
                    /        \                   +--> DLQ không nhận
            requeue=true   requeue=false
                 |              |
                 v              v
          quay về queue     Dead-letter exchange
            ngay lập tức         |
                 |               v
                 +--loop--   binding --> payments.dead.q
                                         (DLQ)
~~~

**Chìa khóa chẩn đoán** là truy ra **ai quyết định ACK/NACK**, giá trị `requeue` là gì, rồi mới kiểm tra **dead-letter exchange (DLX), binding và queue đích**. Không có quy tắc “hễ listener throw là RabbitMQ tự đưa vào DLQ”.

Sau bài học, bạn có thể:

1. Phân biệt **Spring Retry tại client**, **broker requeue**, **delayed retry bằng TTL/DLX**, và **publisher retry**.
2. Tìm lý do message **requeue vô hạn** hoặc **biến mất** sau khi hết retry.
3. Cấu hình `defaultRequeueRejected`, `AmqpRejectAndDontRequeueException`, `RetryInterceptorBuilder` và `RejectAndDontRequeueRecoverer`.
4. Xác minh DLX, dead-letter routing key, binding, vhost, permissions, policy và queue arguments.
5. Đọc `redelivered`, `x-death` và các dấu hiệu quorum queue delivery limit đúng phạm vi.
6. Thực hành tái tạo lỗi bằng Spring Boot, RabbitMQ và Testcontainers, tránh mất message hoặc tạo poison loop khi sửa.

> **Bối cảnh phiên bản:** mã minh họa chính dùng **Java 17, Spring Boot 3.x, Spring AMQP 3.2.x, RabbitMQ 4.x**, AMQP **0-9-1**. Với Spring Boot 4/Spring AMQP 4 cần đối chiếu starter, API và phiên bản Jackson tương ứng. Phân biệt rõ tính năng quorum queue từ RabbitMQ 4.0 trở đi khi đọc các ví dụ.

## 2. Trước tiên phải hiểu vòng đời một delivery

Một message có ít nhất **ba trạng thái cần phân biệt**:

~~~text
[READY trong queue]
        |
        | broker deliver
        v
[UNACKED tại channel/consumer]
        |
        +---- basic.ack --------------------> [Removed from queue]
        |
        +---- basic.nack/reject(requeue=true) --> [Ready/redeliver]
        |                                          |
        |                                          +--> có thể tạo vòng lặp
        |
        +---- basic.nack/reject(requeue=false) --> [DLX nếu có]
                                                       |
                                                       +--> bound DLQ: chờ xử lý
                                                       +--> không có route/DLX: có thể mất
~~~

**Producer confirmation không nằm ở sơ đồ ACK của consumer**. Publisher confirm ACK nghĩa là broker xác nhận publish theo cơ chế xác nhận phía producer; nó **không chứng minh** listener đã xử lý hoặc ACK message. Tương tự, `RabbitTemplate.convertAndSend()` trả về không phải là consumer ACK.

| Tình huống | Broker thường làm gì | DLQ nhận? |
| --- | --- | --- |
| Listener hoàn tất bình thường, `AcknowledgeMode.AUTO` | Container ACK delivery. | **Không**, vì message đã hoàn tất. |
| Listener throw, container NACK với `requeue=true` | Message quay về ready/redeliver. | **Không** qua DLX tại bước đó. |
| Listener throw, container reject với `requeue=false` | Dead-letter nếu queue có DLX và route phù hợp. | **Có thể**, nếu đường DLX hợp lệ. |
| Consumer chết/mất connection khi delivery còn unacked | Broker tự requeue các delivery chưa ACK sau khi phát hiện mất channel/connection. | Không tự DLQ chỉ do disconnect. |
| Message hết TTL trong queue | Dead-letter theo policy nếu được cấu hình. | Có thể, với DLX/binding phù hợp. |
| Quorum queue vượt delivery limit | Broker drop hoặc dead-letter theo cấu hình. | Có thể, nếu DLX hợp lệ. |
| Recoverer Spring xử lý exception và trả về bình thường | Container thường ACK message vì lời gọi sau advice được coi đã xử lý. | **Không**, trừ khi recoverer tự publish tới error exchange. |

### 2.1. Phân biệt ACK mode

| Spring AMQP ACK mode | Ý nghĩa | Sai lầm thường gặp |
| --- | --- | --- |
| `AUTO` | Listener container quyết định ACK/NACK từ kết quả method/advice và error handler. | Nghĩ rằng method throw luôn dẫn đến DLQ. |
| `MANUAL` | Ứng dụng phải ACK/NACK đúng delivery tag trên đúng channel; có những tình huống lỗi fatal được error handler xử lý riêng. | Quên ACK, ACK hai lần, hoặc basicNack với `requeue=true` mãi. |
| `NONE` | Broker giao theo chế độ auto-ack; không chờ client ACK cho mỗi delivery. | Mong broker redrive message từ một exception của listener sau khi đã auto-ack. |

Trong `AUTO`, tên mode có thể gây hiểu nhầm: **AUTO không đồng nghĩa “luôn ACK”**. Nó nghĩa là container tự quyết định **ACK nếu method thành công** hoặc **NACK/reject nếu lỗi** tùy exception và cấu hình.

Với `MANUAL`, đừng tự viết `basicAck` rồi để container khác ACK lần nữa. Delivery tag có hiệu lực **trong channel nhận message**; double ACK hoặc ACK trên channel khác có thể làm broker đóng channel với lỗi `PRECONDITION_FAILED - unknown delivery tag`.

### 2.2. Cùng eventId xuất hiện nhiều lần chưa chắc là RabbitMQ redelivery

Cần xác định message lặp do:

1. Broker **redeliver** cùng physical delivery sau `requeue=true`, disconnect hoặc rollback.
2. Producer **publish lại** cùng business event vì publisher confirm timeout/outbox retry.
3. Một ứng dụng khác **republish** từ retry queue/DLQ.
4. Một scheduled job gửi lại công việc từ database.
5. Nhiều nguồn nghiệp vụ phát **các event khác nhau** nhưng body giống nhau.

Sử dụng `eventId`/`messageId` đã được thiết kế ổn định, nguồn publish, traceId, `consumerQueue` và header broker để phân biệt. Cờ `redelivered` là **gợi ý** broker đã giao trước đó, **không phải bộ đếm đủ tin cậy** và không thay thế idempotency.

## 3. Bốn cơ chế retry phải gọi đúng tên

### 3.1. Retry tại listener trong JVM: Spring Retry

Khi cấu hình retry interceptor, consumer có thể gọi **cùng phương thức xử lý nhiều lần trong một delivery**:

~~~text
broker sends one physical delivery
    |
    v
RetryOperationsInterceptor
    +--> attempt 1: DB timeout
    +--> sleep/backoff
    +--> attempt 2: DB timeout
    +--> sleep/backoff
    +--> attempt 3: success
    |
    v
container ACK once
~~~

Điểm mạnh: có số lần tối đa và backoff, không phát sinh một round-trip RabbitMQ cho mỗi lần thử nội bộ. Điểm hạn chế: **giữ consumer thread/delivery unacked** trong lúc retry; tăng latency và có thể cản trở message tiếp theo. Nếu container/process crash, các lần thử của delivery có thể bắt đầu lại từ đầu sau redelivery. Stateless retry **không** tạo một tổng số attempt toàn cục vĩnh viễn qua restart.

### 3.2. Broker immediate requeue: basic.nack(requeue=true)

~~~text
broker -> consumer -> exception -> nack(requeue=true)
   ^                                            |
   |--------------------------------------------+
~~~

Broker có thể cấp lại message ngay cho cùng consumer hoặc consumer khác, tùy thứ tự queue, prefetch và số consumer. **Đây không phải delayed retry**. Nếu mọi consumer cùng từ chối một poison message, vòng lặp gây tiêu tốn CPU, network và log rất nhanh.

### 3.3. Broker delayed retry: TTL/DLX hoặc cơ chế broker hỗ trợ

Một pattern cũ:

~~~text
work.q --reject(false)--> retry.exchange --> retry.5s.q
                                                |
                                           TTL 5 giây
                                                |
                                                v
                                     dead-letter về work.exchange
                                                |
                                                v
                                              work.q
~~~

Phương án này cần **đếm số vòng**, deadline, terminal DLQ và thiết kế loop breaker. Nếu không, message lỗi vĩnh viễn chỉ quay vòng với thời gian nghỉ giữa các lượt, chứ không tự biến thành lỗi đã xử lý.

RabbitMQ phiên bản mới cũng có các khả năng **delayed retry của quorum queue** theo tài liệu tương ứng. Không giả định mọi broker/queue type đều có cùng tính năng; kiểm tra version và policy thật trước khi dùng.

### 3.4. Producer-side retry / outbox republish

Khi producer không nhận publisher confirm, nó có thể publish lại message; consumer nhìn thấy **hai physical messages** nhưng cùng business event. Điều này **không phải** container requeue. Vì publish ban đầu có thể đã thành công dù producer timeout, downstream phải **idempotent**.

### 3.5. Bảng phân biệt nhanh

| Cơ chế | Nơi diễn ra | Có chờ giữa attempts? | DLQ xuất hiện khi nào? |
| --- | --- | --- | --- |
| Spring Retry stateless | Trong consumer JVM | Theo backoff. | Sau khi hết attempt **và** recoverer/container chọn reject(false), hoặc recoverer tự publish lỗi. |
| Broker requeue=true | RabbitMQ → consumer | **Không có delay bảo đảm**. | Không ở lần NACK này. |
| Broker TTL/DLX retry queue | Qua các queue/DLX | Theo TTL/đặc tính queue. | Chỉ khi một bước terminal chuyển sang DLX/queue lỗi hợp lệ. |
| Quorum delivery limit | Broker quorum queue | Theo delivery/requeue behavior. | Khi vượt limit **và** có đường dead-letter hợp lệ. |
| Producer retry | Producer/outbox | Tùy ứng dụng. | Không tự đưa original message vào DLQ consumer. |

**Luôn xác nhận retry đang nằm ở lớp nào trước khi chỉnh tham số.** Tăng `maxAttempts` của Spring Retry không ngăn được một vòng `nack(requeue=true)` vô hạn sau khi interceptor kết thúc nếu recoverer/policy vẫn yêu cầu requeue.

## 4. Sơ đồ quyết định: vì sao DLQ không nhận?

~~~text
                    Listener gặp lỗi
                           |
                           v
               Spring Retry / ErrorHandler
                           |
           +---------------+-----------------+
           |                                 |
    Exception bị recoverer              Exception còn lan ra
       xử lý và return                        |
           |                                 v
           v                        Container quyết định settle
       Container ACK                       |
           |                     +---------+-----------+
           |                     |                     |
      DLQ không nhận         requeue=true          requeue=false
                                 |                     |
                            requeue loop               v
                                                Queue có DLX?
                                                  /      \
                                                 /        \
                                               Không       Có
                                                |          |
                                            discard       DLX tồn tại?
                                                           /     \
                                                         Không     Có
                                                           |        |
                                                          drop   Có binding khớp?
                                                                    /   \
                                                                 Không   Có
                                                                   |      |
                                                                  drop  DLQ
~~~

Sơ đồ mô tả luồng mặc định **đơn giản hóa** cho AMQP 0-9-1; quorum queue `at-least-once dead-lettering` có thể **giữ lại message tại nguồn** khi mục tiêu không sẵn sàng thay vì mất ngay. Cần kiểm tra loại queue và chính sách broker trước khi kết luận một message bị drop.

| Quan sát | Hướng điều tra đầu tiên |
| --- | --- |
| Listener log lỗi liên tục; `redelivered=true`; queue ready/unacked dao động. | `defaultRequeueRejected=true`, `ImmediateRequeueAmqpException` hoặc `basicNack(true)`. |
| Listener log 4 lần cho một delivery, sau đó message biến mất; DLQ rỗng. | Retry recoverer **đã xử lý và trả về**, khiến container ACK. |
| Có NACK requeue=false nhưng DLQ rỗng. | Chưa cấu hình DLX trên **queue nguồn**, DLX không tồn tại, sai dead-letter routing key, thiếu binding hoặc DLQ ở vhost khác. |
| RabbitMQ log precondition/permission errors. | Queue khai báo không khớp arguments, user thiếu read/write cho DLX, exchange/queue chưa được provision đúng. |
| Main queue vẫn giữ message sau nhiều lần requeue, DLQ không có. | Chưa vượt delivery limit, queue classic không có giới hạn kiểu quorum, hoặc policy không áp dụng. |
| Quorum queue RabbitMQ 4.x rồi message mất sau nhiều attempts. | Có thể vượt **delivery-limit mặc định 20**, không cấu hình DLX hoặc DLX không route được. |
| DLQ tăng rồi giảm bất ngờ. | Có listener/TTL/purge/auto-delete/consumer khác đang đọc DLQ; không mặc định cho rằng DLQ chưa từng nhận. |
| Message lỗi bị ghi trong error exchange, broker DLQ vẫn rỗng. | `RepublishMessageRecoverer` dùng **application republish + ACK original**, không phải broker dead-letter. |

## 5. Runbook an toàn trong 10 phút đầu

Khi gặp retry loop ở production, ưu tiên **ngăn tác động phụ và giữ bằng chứng**, không xóa queue hoặc thay policy ngay.

1. **Khoanh vùng:** xác định broker, vhost, queue, consumer group, thời điểm bắt đầu, event ID, deployment/config thay đổi gần nhất.
2. **Bảo vệ tác vụ:** nếu side effect có nguy cơ bị thực hiện trùng (trừ tiền, gửi email, tạo shipment), ưu tiên xác thực idempotency hoặc tạm dừng **đúng consumer bị ảnh hưởng** theo runbook; không purge queue.
3. **Quan sát broker:** queue ready/unacked, publish/deliver/ack/redelivery rates, DLQ depth, consumer count, resource alarms và logs.
4. **Đọc chính sách đang hiệu lực:** `x-dead-letter-exchange`, `x-dead-letter-routing-key`, policy, queue type, delivery-limit; phân biệt queue arguments với policy.
5. **Lấy một mẫu an toàn:** từ log/tracing hoặc message đã có trong failure store. Nếu dùng Management “Get messages”, hiểu lựa chọn requeue/ack có thể thay đổi queue state; không lấy mẫu tùy tiện trên production.
6. **Phân loại exception:** parsing/validation/authorization vĩnh viễn hay DB/KMS/network lỗi tạm thời? Có xử lý trong Spring Retry hay bị convert trước khi vào listener?
7. **Xác định settle decision:** recoverer ACK, container reject(false), reject(true), manual ACK/NACK hay channel disconnect.
8. **Khắc phục có kiểm soát:** sửa config/error handler/retry policy hoặc DLX routing; kiểm thử bằng message giả ở môi trường test trước khi áp dụng.
9. **Redrive có giới hạn:** chỉ với event chưa hoàn tất, giữ event ID, theo dõi việc message vào đúng DLQ hoặc xử lý thành công.
10. **Đối soát nghiệp vụ:** kiểm tra database/outbox/inbox, số tác vụ thiếu/trùng; chỉ đóng incident khi kết quả đầu cuối đã xác minh.

**Không thực hiện** `rabbitmqctl purge_queue`, xóa/redeclare queue, tăng retry vô hạn hoặc disable ACK chỉ để “làm sạch” dashboard. Những thao tác đó có thể làm mất message và bằng chứng điều tra.

## 6. Spring AMQP: exception dẫn tới ACK, requeue hay reject?

### 6.1. defaultRequeueRejected mặc định là true

Với `SimpleMessageListenerContainer` hoặc `DirectMessageListenerContainer` và `AcknowledgeMode.AUTO`, thuộc tính `defaultRequeueRejected` điều khiển việc có requeue các message **bị từ chối do listener throw exception** hay không. Giá trị mặc định thường là **`true`**.

Ví dụ dễ gây vòng lặp:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BrokenPaymentsListener {

    @RabbitListener(queues = "payments.process.q")
    public void process(String body) {
        // Lỗi vĩnh viễn: message này KHÔNG thể parse dù thử bao nhiêu lần.
        throw new IllegalArgumentException("Unsupported payment schema");
    }
}
~~~

Nếu `IllegalArgumentException` này không được error handler phân loại thành fatal và container vẫn requeue, broker giao lại liên tục. **`IllegalArgumentException` do nghiệp vụ ném không tự động được mọi Spring AMQP phiên bản coi là fatal conversion error**.

Một cấu hình thận trọng để **chặn requeue vô hạn** khi có DLX:

~~~yaml
# application.yml — Spring Boot 3.x, standard auto-config listener factory
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false
~~~

Khi cấu hình qua Java:

~~~java
factory.setDefaultRequeueRejected(false);
~~~

**Cảnh báo:** đặt `defaultRequeueRejected=false` **không tự tạo DLQ**. Nếu queue nguồn không có DLX/route hợp lệ, broker có thể **discard message** sau reject(false). Đây là cách từ vòng lặp vô hạn chuyển sang **mất message không mong muốn** nếu triển khai thiếu bước cấu hình broker.

### 6.2. Hai exception đặc biệt ghi đè mặc định

| Exception | Tác động chính trong Spring AMQP | Khi dùng |
| --- | --- | --- |
| `AmqpRejectAndDontRequeueException` | Yêu cầu reject **không requeue** ngay cả khi `defaultRequeueRejected=true`. | Dữ liệu sai schema vĩnh viễn, nghiệp vụ bị từ chối theo contract, poison message. |
| `ImmediateRequeueAmqpException` | Yêu cầu **requeue** ngay cả khi `defaultRequeueRejected=false`. | Trường hợp hiếm, có lý do chắc chắn cần giao lại ngay. |

Ví dụ phân loại tối thiểu:

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentErrorClassificationExample {

    @RabbitListener(queues = "payments.process.q")
    public void process(String body) {
        if (body.startsWith("BAD:")) {
            throw new AmqpRejectAndDontRequeueException(
                    "Permanent schema violation");
        }

        // Các lỗi còn lại cần chính sách retry có giới hạn.
    }
}
~~~

Mã ở trên **minh họa cơ chế exception**, không nên bật đồng thời với listener `BrokenPaymentsListener` cùng queue: hai listener sẽ cạnh tranh message, gây nhiễu khi kiểm thử. Trong code production, validate payload và dùng exception/domain error phù hợp thay vì nhận diện bằng prefix string.

**Đừng lạm dụng `ImmediateRequeueAmqpException` cho lỗi tạm thời.** Khi downstream DB mất kết nối 10 phút, requeue ngay không giúp DB khôi phục; nó chỉ tạo retry storm. Dùng backoff giới hạn, pause, retry queue hoặc outbox/failure store tùy trường hợp.

### 6.3. ConditionalRejectingErrorHandler: có lỗi chết trước khi vào listener

Spring AMQP mặc định sử dụng **`ConditionalRejectingErrorHandler`** trong listener container. Nó có thể phân loại một số lỗi là **fatal**, ví dụ:

- `org.springframework.amqp.support.converter.MessageConversionException` khi converter không đọc được body.
- `org.springframework.messaging.converter.MessageConversionException` khi Spring conversion service không map được argument.
- Một số lỗi thiếu/không hợp lệ tham số, method argument validation và lỗi lời gọi listener mà framework nhận diện là không thể phục hồi.

Điều này giải thích hiện tượng:

~~~text
Message bytes không parse được
  |
  v
MessageConverter ném lỗi TRƯỚC method @RabbitListener
  |
  v
ConditionalRejectingErrorHandler phân loại fatal
  |
  v
reject(no requeue) nếu policy/ACK mode cho phép
  |
  v
DLX hoặc drop
~~~

Vì vậy **không thấy log trong body method listener** không có nghĩa consumer chưa nhận message. Hãy xem lỗi conversion/handler ở phía container và logger Spring AMQP.

Theo tài liệu Spring AMQP, handler này còn có cơ chế **discard fatal messages đã mang `x-death`** khi quay lại qua broker DLX cycle (thuộc tính `discardFatalsWithXDeath`, mặc định bật ở các dòng hỗ trợ). Với tình huống đó, message có thể **bị discard tại client** thay vì trở lại DLQ như bạn kỳ vọng. Không tự tắt bảo vệ để làm một poison message quay vòng; cần kiểm tra history và chỉnh thiết kế retry.

Với `AcknowledgeMode.MANUAL`, một số fatal exception xảy ra **trước listener** được framework reject riêng dù method không có cơ hội ACK/NACK; cách xử lý tùy Spring AMQP version và `ConditionalRejectingErrorHandler.rejectManual`. Không suy ra mọi exception trong manual mode được xử lý giống nhau.

### 6.4. Không trộn lỗi retryable và permanent

Ví dụ phân loại:

| Lỗi | Loại | Hành động ưu tiên |
| --- | --- | --- |
| JSON sai cấu trúc, thiếu field bắt buộc | Permanent nếu schema đã xác định | Không retry lặp; reject(false) vào DLQ/quarantine. |
| Event schema version không được consumer hỗ trợ | Permanent đối với consumer hiện tại | DLQ, contract alert hoặc triển khai decoder mới. |
| Tenant không có quyền | Security/permanent | Reject/quarantine, audit; không chuyển sang tenant khác. |
| DB timeout hoặc connection pool cạn | Transient | Retry có backoff/limit hoặc trì hoãn; đảm bảo idempotency. |
| Broker connection bị đứt | Transient transport | Connection/container recovery, outbox bảo vệ producer. |
| Rate limit từ API downstream | Transient | Retry trễ, jitter, giới hạn concurrency; không loop ngay. |
| Unique constraint báo eventId đã xử lý | Duplicate hợp lệ nếu business idempotent | Bỏ qua side effect và ACK có kiểm soát. |
| KMS outage khi decrypt | Transient infrastructure | Retry/backoff có giới hạn, giữ message. |
| AEAD tag không hợp lệ | Tampering/invalid payload | Reject/quarantine, alert; không thử mọi khóa. |

**Không chỉ định retryable dựa vào lớp exception ở tầng ngoài** nếu Spring wrap bằng `ListenerExecutionFailedException`. Khi dùng Spring Retry classifier, kiểm tra cause chain bằng tùy chọn tương ứng (ví dụ `traverseCauses=true` trên `SimpleRetryPolicy`) và viết test cho cả wrapped exceptions.

## 7. Spring Retry: hết lần thử rồi mà DLQ vẫn rỗng

### 7.1. “Retry có giới hạn” chưa nói rõ kết thúc ra sao

Ví dụ sơ đồ:

~~~text
listener advice:
  retry attempt #1 FAIL
  retry attempt #2 FAIL
  retry attempt #3 FAIL
  retry attempt #4 FAIL
          |
          v
   MessageRecoverer
          |
          +--> returns normally ---> listener container ACK ---> DLQ rỗng
          |
          +--> throws ARADRE -----> container reject(false) ---> DLX
          |
          +--> RepublishMessageRecoverer ---> app publish tới error exchange
                                               + container ACK original
~~~

Spring AMQP **default recoverer** của retry interceptor có thể **log cảnh báo rồi consume message** khi hết attempts. Container lúc đó coi delivery đã được xử lý nên ACK. **Đây là nguyên nhân quan trọng nhất cần kiểm tra khi retry kết thúc mà DLQ vẫn trống.**

Nếu muốn **broker dead-letter** sau khi hết retry, cấu hình recoverer **ném `AmqpRejectAndDontRequeueException`**:

~~~java
new RejectAndDontRequeueRecoverer()
~~~

Nếu muốn **application tự republish vào error exchange** để ghi stack/error headers, dùng `RepublishMessageRecoverer`, nhưng hiểu rằng **original delivery được ACK** khi recoverer thành công. Đường này **khác** broker DLX; không nên mong broker DLQ cũng tự nhận một bản nữa.

### 7.2. Cấu hình bounded retries với RejectAndDontRequeueRecoverer

Đoạn sau dùng Spring AMQP 3.2 với dependency `spring-retry`. `maxAttempts(4)` nghĩa là **tối đa bốn lần thực thi method trong một lượt retry**, gồm lần đầu, không phải “bốn lần retry cộng lần đầu”.

~~~java
// BoundedPaymentListenerConfiguration.java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.interceptor.RetryOperationsInterceptor;

@Configuration(proxyBeanMethods = false)
public class BoundedPaymentListenerConfiguration {

    @Bean
    RetryOperationsInterceptor paymentRetryInterceptor() {
        return RetryInterceptorBuilder.stateless()
                .maxAttempts(4)
                .backOffOptions(200, 2.0, 1000)
                .recoverer(new RejectAndDontRequeueRecoverer())
                .build();
    }

    @Bean("boundedPaymentListenerFactory")
    SimpleRabbitListenerContainerFactory boundedPaymentListenerFactory(
            ConnectionFactory connectionFactory,
            RetryOperationsInterceptor paymentRetryInterceptor) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setDefaultRequeueRejected(false);
        factory.setConcurrentConsumers(1);
        factory.setAdviceChain(paymentRetryInterceptor);
        return factory;
    }
}
~~~

~~~xml
<!-- Maven, Spring Boot 3.x; chọn version do Spring BOM quản lý. -->
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>
~~~

Listener dùng đúng bean:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BoundedPaymentListener {

    @RabbitListener(
        id = "boundedPayments",
        queues = "payments.process.q",
        containerFactory = "boundedPaymentListenerFactory"
    )
    public void process(Message message) {
        String body = new String(
                message.getBody(), StandardCharsets.UTF_8);
        if (body.startsWith("BAD:")) {
            throw new IllegalArgumentException(
                    "Permanently invalid payment test payload");
        }
        if (body.startsWith("TEMP:")) {
            throw new IllegalStateException(
                    "Simulated temporary DB outage");
        }
        // Production: validate, dedupe eventId, business DB transaction.
    }
}
~~~

**Kết quả mẫu:**

- `BAD:...`: trong cấu hình đơn giản này cũng bị retry tối đa bốn lượt (chưa tối ưu), sau đó recoverer yêu cầu reject(false) → broker DLX.
- `TEMP:...`: thử tối đa bốn lượt với backoff tăng; nếu vẫn lỗi thì cũng reject(false) → DLX.
- Message hợp lệ → method hoàn tất, container ACK → **không vào DLQ**.

Trong production, không nên tốn bốn lần cho lỗi **BAD/permanent**. Thêm **`RetryPolicy` phân loại exception** và duyệt cause chain, hoặc tách listener handling sao cho lỗi permanent được reject không qua retry interceptor. Điều quan trọng của ví dụ là **đường terminal** sau retry không làm message biến mất khi có DLX.

**Giới hạn state:** đây là **stateless retry** trong một invocation/delivery; khi process crash rồi broker redeliver, bộ đếm attempts có thể bắt đầu lại. Nếu cần ngân sách retries xuyên restart, dùng stateful retry với **message ID** ổn định hoặc một bảng trạng thái retry trong DB/broker retry policy có hạn. Không coi `maxAttempts(4)` là “tối đa bốn lần suốt đời message” khi message có thể được giao lại.

### 7.3. Vì sao đổi sang RepublishMessageRecoverer không có x-death?

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.retry.RepublishMessageRecoverer;
import org.springframework.retry.interceptor.RetryOperationsInterceptor;

RetryOperationsInterceptor republishOnFailure(
        org.springframework.amqp.rabbit.core.RabbitTemplate template) {
    return RetryInterceptorBuilder.stateless()
            .maxAttempts(4)
            .recoverer(new RepublishMessageRecoverer(
                    template, "payments.errors.x", "payment.failed"))
            .build();
}
~~~

Ở đây recoverer **tự publish** message lỗi đến `payments.errors.x`, có thể bổ sung error headers, sau đó ACK original delivery khi hoàn tất bình thường. Broker **không trực tiếp dead-letter** message, vì vậy **`x-death` do DLX thường không xuất hiện** chỉ vì republish kiểu này.

**Yêu cầu độ tin cậy:** nếu republish lỗi thất bại hoặc không routable, hệ thống có nguy cơ mất/nhân bản tác vụ tùy outcome. Khi thực sự cần bảo đảm có xác nhận ở đường error republish, cân nhắc `RepublishMessageRecovererWithConfirms` với publisher confirms/returns và idempotency; theo dõi kết quả và kiểm tra version/API tương ứng.

Không bật `RejectAndDontRequeueRecoverer` **đồng thời** với một ý tưởng “RepublishMessageRecoverer rồi vẫn mong broker tự DLX” trong cùng một nhánh recovery mà không thiết kế rõ. Hai cơ chế là **hai chiến lược terminal khác nhau**.

### 7.4. Stateful retry, transaction và messageId

Với transaction bắt đầu ở tầng trên interceptor hoặc yêu cầu rollback giữa các lần thử, Spring AMQP có **stateful retry**:

~~~java
RetryOperationsInterceptor statefulRetry =
        RetryInterceptorBuilder.stateful()
                .maxAttempts(4)
                .backOffOptions(500, 2.0, 5000)
                .recoverer(new RejectAndDontRequeueRecoverer())
                .build();
~~~

Đoạn trên thay thế interceptor stateless, **không dùng cả hai cùng lúc**. Stateful retry cần xác định message identity, thường qua `MessageProperties.messageId`. Nếu message không có ID, behavior có thể dừng consumer hoặc reject theo cấu hình `statefulRetryFatalWithNullMessageId` và phiên bản Spring AMQP. Kiểm tra cụ thể trước production. Nếu cần retry state sống qua restart/process, bản thân stateful interceptor có thể vẫn chỉ lưu retry context trong JVM; dùng persistent attempts hoặc broker policy nếu đó là hợp đồng bắt buộc.

Khi có `channelTransacted` hoặc DB transaction, **rollback không đồng nghĩa từ chối không requeue**: giá trị `defaultRequeueRejected`, exception, recoverer, container transaction và RabbitMQ transaction có thể tương tác. Chạy test ở **đúng cấu hình transaction** thay vì suy từ kết quả ví dụ stateless đơn giản.

### 7.5. Retry của batch listener là bài toán khác

Nếu producer đóng **nhiều logical events thành một physical message**, một reject(false) có thể dead-letter **toàn bộ physical batch**. Với consumer-created batch, retry interceptor khó biết event nào gây lỗi; Spring AMQP khuyến cáo cẩn trọng khi dùng retry với batch listeners và recovery có thể không hỗ trợ như listener một message.

Khi điều tra “10 message hợp lệ cũng vào DLQ theo 1 poison event”, hãy kiểm tra `BatchingRabbitTemplate` và batch listener settings. Idempotency theo `eventId` là bắt buộc nếu cả lô bị redeliver.

## 8. DLX và DLQ: phải có đủ chuỗi exchange–binding–queue

**DLX (Dead Letter Exchange)** là một exchange RabbitMQ bình thường, được queue nguồn dùng để **republish message bị dead-letter**. **DLQ (Dead Letter Queue)** chỉ là queue được bind vào DLX với key phù hợp; RabbitMQ không tự tạo queue tên `<original>.dlq`.

~~~text
Producer
  |
  | exchange=payments.events.x
  | routingKey=payment.created
  v
DirectExchange payments.events.x
  |
  | binding payment.created
  v
Queue payments.process.q
  |  x-dead-letter-exchange = payments.dead.x
  |  x-dead-letter-routing-key = payment.failed
  |
  | reject(false) / expired / maxlen / delivery_limit
  v
DirectExchange payments.dead.x
  |
  | binding payment.failed
  v
Queue payments.dead.q
~~~

Muốn DLQ có message thì **đồng thời cần**:

1. Queue nguồn cấu hình DLX có hiệu lực.
2. Có sự kiện dead-letter **thật** ở queue nguồn, ví dụ reject/NACK với `requeue=false`.
3. DLX **tồn tại trong cùng vhost** và có exchange type đúng.
4. Routing key dùng khi dead-letter khớp binding tới DLQ.
5. Queue DLQ tồn tại và không bị consumer/TTL/policy làm giảm ngay.
6. Quyền, queue type, target availability và chiến lược dead-lettering cho phép chuyển message.

Chỉ khai báo `QueueBuilder.durable("payments.dead.q")` **không đủ**; queue đó phải có **binding từ DLX**.

### 8.1. Topology Java đầy đủ để thử nghiệm

~~~java
// PaymentDeadLetterTopology.java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PaymentDeadLetterTopology {
    public static final String EVENTS_X = "payments.events.x";
    public static final String EVENTS_KEY = "payment.created";
    public static final String MAIN_Q = "payments.process.q";
    public static final String DLX = "payments.dead.x";
    public static final String DL_KEY = "payment.failed";
    public static final String DLQ = "payments.dead.q";

    @Bean
    Declarables paymentDeclarables() {
        DirectExchange events = new DirectExchange(EVENTS_X, true, false);
        DirectExchange dead = new DirectExchange(DLX, true, false);

        // Dùng x-arguments để demo một topology hoàn chỉnh.
        // Production nên ưu tiên RabbitMQ policies cho DLX có thể cập nhật.
        Queue main = QueueBuilder.durable(MAIN_Q)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DL_KEY)
                .build();
        Queue failed = QueueBuilder.durable(DLQ).build();

        Binding workBinding = BindingBuilder.bind(main)
                .to(events).with(EVENTS_KEY);
        Binding deadBinding = BindingBuilder.bind(failed)
                .to(dead).with(DL_KEY);

        return new Declarables(
                events, dead, main, failed, workBinding, deadBinding);
    }
}
~~~

**Các điểm cần kiểm tra trong đoạn code:**

- `events` và `dead` là **hai exchange**, không được đổi tên nhầm.
- `main` có **hai arguments** liên quan DLX; `failed` là queue đích, không tự động cần DLX riêng.
- `deadBinding` phải dùng `DL_KEY` trùng với `deadLetterRoutingKey(DL_KEY)`.
- Broker/router không quan tâm Java class name, chỉ nhìn **exchange, routing key, queue và vhost**.
- Listener `BoundedPaymentListener` ở mục 7 nhận từ `MAIN_Q` sau khi queue đã tồn tại.

**Cảnh báo về production:** RabbitMQ khuyến nghị cấu hình DLX bằng **policy** thay vì hard-code queue `x-arguments`. Arguments đã khai báo trên một queue hiện có thường không đổi được bằng redeclare; sửa Java rồi restart có thể dẫn tới `PRECONDITION_FAILED - inequivalent arg` chứ không tự cập nhật DLX.

### 8.2. Cách cấu hình DLX bằng RabbitMQ policy

Khi queue **không khai báo cứng** `x-dead-letter-exchange`/`x-dead-letter-routing-key`, có thể áp policy:

~~~bash
# Ví dụ vhost mặc định / và queue payments.process.q.
# Lệnh dành cho môi trường demo/test; cần tài khoản quản trị thích hợp.
rabbitmqctl set_policy payment-dlx '^payments\.process\.q$' \
  '{"dead-letter-exchange":"payments.dead.x","dead-letter-routing-key":"payment.failed"}' \
  --apply-to queues --priority 10
~~~

**Quan trọng:** lệnh trên chỉ là **minh họa**, không dùng trên production nếu chưa kiểm tra những policy khác. Regex `^payments\.process\.q$` nhắm đúng queue mẫu. Phải tạo DLX và DLQ binding trước khi có message bị dead-letter.

Nếu queue đã khai báo `x-dead-letter-exchange` cứng trong arguments, **arguments thường có ưu tiên hơn policy**. Thêm policy mới nhưng queue vẫn sử dụng DLX cũ là tình huống chẩn đoán rất phổ biến.

Không tự xóa queue production để “áp policy”; muốn chuyển từ x-arguments sang policy, cần **migration dữ liệu/topology** có kế hoạch và downtime/rollback phù hợp.

### 8.3. Bảng lỗi cấu hình DLX thường gặp

| Sai cấu hình | Kết quả dễ thấy | Cách xác minh |
| --- | --- | --- |
| Có DLQ nhưng queue nguồn không có DLX | Reject(false) có thể discard. | Kiểm tra **arguments/policy của queue nguồn**, không chỉ DLQ. |
| DLX không tồn tại lúc message bị dead-letter | RabbitMQ at-most-once DLX có thể **drop âm thầm**. | `list_exchanges` đúng vhost, broker logs. |
| Có DLX nhưng không có binding khớp key | DLQ không nhận do unroutable. | `list_bindings`, compare routing key. |
| DLX type sai: fanout/direct/topic | Key match khác thiết kế. | `list_exchanges name type`. |
| `x-dead-letter-routing-key` bị sai | DLX dùng key mới sai, DLQ có binding khác. | Queue arguments/policy hiệu lực và binding. |
| Không chỉ định dead-letter routing key | DLX dùng routing key cũ. | Kiểm tra DLQ binding có match key gốc. |
| DLQ ở vhost khác | DLX trong vhost nguồn không thể route qua vhost khác bằng binding thông thường. | `rabbitmqctl ... -p /vhost`, xác minh vhost. |
| User thiếu quyền đọc source queue/ghi DLX | Queue declaration có thể thất bại theo RabbitMQ permission checks. | Logs `ACCESS_REFUSED`, `list_permissions`. |
| Sửa arguments của queue đã tồn tại | Redeclare bị `PRECONDITION_FAILED`. | Startup logs, queue effective arguments. |
| DLQ có consumer đang hoạt động | DLQ depth thấp/0 dù từng có message. | Kiểm tra consumers và ACK rate trên DLQ. |
| DLQ có TTL/max length/auto-delete | Message có thể expire/drop hoặc queue biến mất. | Queue policies, TTL, limits, consumer lifecycle. |
| Error recoverer của Spring ACK trước | Không có sự kiện dead-letter ở broker. | Kiểm tra retry advice và recoverer. |
| Manual mode code gọi `basicAck` trong catch | Original delivery được ACK. | Đọc code ACK path và log settlement, không chỉ exception. |

### 8.4. Khi dùng DLX, thiếu route có thể làm mất message

RabbitMQ mặc định dead-letter bằng **at-most-once republishing**; trong một cluster, nếu target không sẵn sàng hoặc không nhận được message, có trường hợp message **bị mất**. Một DLX/binding tồn tại đúng tên **chưa phải bảo đảm lưu trữ tuyệt đối**.

RabbitMQ **quorum queue** có tùy chọn **at-least-once dead-lettering** để giữ message ở source đến khi target xác nhận, nhưng cần cấu hình các điều kiện riêng (ví dụ `dead-letter-strategy=at-least-once`, `overflow=reject-publish`, DLX tồn tại và các yêu cầu của phiên bản). Không áp cùng policy cho mọi classic/quorum queue một cách máy móc; xem thêm mục 12.

### 8.5. Không để DLQ tự dead-letter quay lại nguồn nếu chưa giới hạn

Một cấu hình sai:

~~~text
payments.process.q
   |
   +-- reject(false) --> retry.exchange --> payments.retry.q
                                              |
                                              +-- TTL --> payments.events.x
                                                          |
                                                          v
                                                  payments.process.q
~~~

Đây là **retry cycle**, không phải terminal DLQ. Nếu message luôn lỗi, nó quay vòng mãi. RabbitMQ có phát hiện một số **dead-letter cycles không có rejection trong vòng**, nhưng không được dựa vào đó như cơ chế giới hạn attempts: những vòng retry có consumer reject vẫn có thể tiếp tục, và message có thể bị drop theo điều kiện khác.

Nếu muốn delayed retries, thiết kế:

~~~text
attempt 1 -> retry 5s -> attempt 2
                       -> retry 30s -> attempt 3
                                     -> terminal DLQ
~~~

**Chọn một nơi quản lý bộ đếm retry tin cậy** và đặt giới hạn, không cho mọi message quay lại queue chính vô hạn.

## 9. Kiểm tra RabbitMQ trực tiếp bằng CLI và Management

### 9.1. Thu thập trạng thái đúng vhost

Với ví dụ vhost mặc định `/`:

~~~bash
# Kiểm tra queue type, trạng thái message, consumer và queue arguments.
rabbitmqctl list_queues -p / name messages_ready \
  messages_unacknowledged consumers arguments policy

# Kiểm tra exchange có tồn tại và đúng type.
rabbitmqctl list_exchanges -p / name type durable

# Kiểm tra source exchange, destination queue, binding routing key.
rabbitmqctl list_bindings -p / source_name destination_name routing_key

# Kiểm tra các policy trên vhost.
rabbitmqctl list_policies -p /

# Kiểm tra các resource alarms trên node.
rabbitmq-diagnostics alarms
~~~

Lệnh minh họa dành cho CLI tại broker/container RabbitMQ; phiên bản cụ thể có thể hỗ trợ cách hiển thị/trường khác nhau. Dùng `rabbitmqctl help <command>` khi cần. Trên môi trường có vhost khác, thay `-p /` bằng vhost **thực mà connection của ứng dụng sử dụng**; queue cùng tên ở hai vhost là hai queue khác nhau.

Giao diện RabbitMQ Management có thể kiểm tra:

1. **Queues** → queue nguồn → **Arguments/Policy**, `Ready`, `Unacked`, `Consumers`.
2. **Exchanges** → dead-letter exchange → **Bindings**.
3. **Queues** → DLQ → number of messages/consumer count/TTL/arguments.
4. **Connections/Channels** → application connection, activity, blocked state.
5. **Overview/Metrics** → deliver, redeliver, ack, nack, publish, drop và node alarms.

**Đừng nhầm queue depth với lịch sử DLQ.** Nếu một DLQ consumer đã ACK liên tục, `messages_ready=0` không chứng minh DLQ chưa từng nhận.

### 9.2. Ý nghĩa một mẫu message “redelivered”

Message có thể mang `redelivered=true` khi broker gửi lại một delivery đã được giao trước đó. Cờ này **không mang số lần thử**, không cho biết lần nào diễn ra trong Spring Retry và không đủ để xác định message chắc chắn từng bị xử lý nghiệp vụ.

Khi RabbitMQ dead-letter, AMQP 0-9-1 message thường có `x-death` header chứa history với `queue`, `reason`, `count`, `exchange`, `routing-keys` và thời gian theo format/phiên bản. Từ đó có thể suy ra message từng **được dead-letter từ queue nào vì lý do gì**.

Ví dụ rút gọn:

~~~text
headers:
  x-first-death-queue: payments.process.q
  x-first-death-reason: rejected
  x-first-death-exchange: payments.events.x
  x-last-death-queue: payments.process.q
  x-last-death-reason: rejected
  x-death:
    - queue: payments.process.q
      reason: rejected
      count: 2
      exchange: payments.events.x
      routing-keys: [payment.created]
~~~

`x-death` **không tăng cho mỗi lần `basic.nack(requeue=true)`** — nó ghi các **sự kiện dead-letter**, không phải mọi redelivery. Nó cũng có thể được nén theo cặp **(queue, reason)** thay vì lưu một entry cho từng vòng. Do đó:

- `x-death.count=2` không chứng minh listener chỉ được gọi hai lần.
- `redelivered=true` mà không có `x-death` không phải bằng chứng DLX hỏng; message có thể chỉ bị requeue.
- Cần đối chiếu cả **consumer attempts, broker outcomes, producer republish và business eventId**.

### 9.3. Từ RabbitMQ 4.0: đừng tự giả mạo x-death từ client

RabbitMQ 4.0 trở đi **không coi `x-death` do client tự publish là một broker-generated dead-letter history đáng tin cậy**. Với ứng dụng tự republish message để delayed retry, không nên copy/chỉnh `x-death` rồi dùng nó làm bộ đếm kiểm soát.

Từ **Spring AMQP 3.2**, `MessageProperties` có thuộc tính `retryCount` (header `retry_count`) hỗ trợ use case retry qua broker: khi header chưa có và có history DLX phía server, framework có thể ánh xạ dữ liệu liên quan từ `x-death`; khi **ứng dụng tự republish**, phải **chủ động tăng retry count** trong luồng đã kiểm soát.

Ví dụ ý tưởng:

~~~java
Long attempts = message.getMessageProperties().getRetryCount();
if (attempts < 3L) {
    message.getMessageProperties().incrementRetryCount();
    // Republish có kiểm soát + confirm + outbox nếu cần.
} else {
    // Terminal: reject(false) hoặc republish vào failure store
    // nhưng không tạo retry cycle vô hạn.
}
~~~

**Lưu ý:** API trên có mặt ở các phiên bản Spring AMQP hỗ trợ `retry_count`; không copy vào ứng dụng cũ rồi đoán nó hoạt động. Đây chỉ là **đoạn thuật toán**, chưa có persistence/confirm/ACK. Nếu tự republish thành công rồi ACK original, phải xử lý rủi ro publisher/consumer crash giữa hai bước, tránh mất hoặc nhân bản công việc.

## 10. Manual ACK: một dòng code sai cũng đủ tạo retry storm

Trong `AcknowledgeMode.MANUAL`, consumer tự gọi `basicAck`, `basicNack` hoặc `basicReject` theo **delivery tag** của message đã nhận. Một lỗi tiêu biểu:

~~~java
try {
    paymentService.process(payload);
    channel.basicAck(tag, false);
} catch (Exception ex) {
    channel.basicNack(tag, false, true);  // requeue=true cho MỌI lỗi
}
~~~

Nếu `payload` luôn sai schema, broker nhận `basicNack(..., requeue=true)` mãi. **DLX không được kích hoạt** vì message đang được yêu cầu requeue; đặt DLQ chính xác tên cũng không giúp gì.

Lỗi ngược lại:

~~~java
try {
    paymentService.process(payload);
} catch (Exception ex) {
    log.error("Failure", ex);
}
channel.basicAck(tag, false);   // ACK kể cả khi business failure
~~~

Message bị xóa khỏi queue; **DLQ rỗng** vì bạn đã ACK nó.

### 10.1. Mẫu manual ACK có nhánh rõ ràng

~~~java
// ManualPaymentListenerConfig.java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ManualPaymentListenerConfig {
    @Bean("manualPaymentListenerFactory")
    SimpleRabbitListenerContainerFactory manualPaymentListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        factory.setPrefetchCount(10);
        return factory;
    }
}
~~~

~~~java
// ManualPaymentListener.java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import com.rabbitmq.client.Channel;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ManualPaymentListener {

    @RabbitListener(
        queues = "payments.process.q",
        containerFactory = "manualPaymentListenerFactory"
    )
    public void handle(Message message, Channel channel)
            throws IOException {
        long tag = message.getMessageProperties().getDeliveryTag();
        String body = new String(
                message.getBody(), StandardCharsets.UTF_8);

        // Chỉ minh họa; production phải validate schema đầy đủ.
        if (body.startsWith("BAD:")) {
            // Poison message -> DLX khi queue có cấu hình hợp lệ.
            channel.basicReject(tag, false);
            return;
        }

        // Nếu lỗi transient từ DB: KHÔNG mặc định nack(true) vô hạn.
        // Cho phép exception lan ra nếu policy/container đã kiểm thử,
        // hoặc thiết kế đường delayed retry có confirm và terminal DLQ.
        processBusinessOnce(body);
        channel.basicAck(tag, false);
    }

    private void processBusinessOnce(String body) {
        // Thay bằng DB transaction + unique eventId/inbox.
    }
}
~~~

**Các lưu ý an toàn:**

- Ví dụ này là **alternative** cho `BoundedPaymentListener` ở mục 7; **không chạy cả hai listener trên cùng queue** nếu muốn test hành vi deterministic.
- Nếu `processBusinessOnce` throw, container sẽ xử lý exception theo policy/error handler thực tế; manual mode cần được test riêng để tránh delivery bị unacked hoặc requeue trái ý muốn.
- Khi đã `basicReject` hoặc `basicAck`, **không tiếp tục throw** cùng lỗi nếu có nguy cơ container settle delivery thêm lần nữa.
- Với `basicNack(tag, multiple, requeue)`, giá trị `multiple=true` có thể xử lý cả các delivery tag chưa ACK **tới tag đó** trên cùng channel. Không dùng `multiple=true` tùy tiện khi consumer xử lý đồng thời.
- `AcknowledgeMode.NONE` hoàn toàn khác: broker auto-ack, exception trong listener không tạo broker DLX một cách tự động.

**Trong phần lớn ứng dụng nghiệp vụ**, `AUTO` cộng retry interceptor/exception classifier dễ kiểm soát hơn manual ACK tự viết, trừ khi bạn có yêu cầu settlement đặc biệt và test đầy đủ.

### 10.2. Catch exception rồi return cũng gây “DLQ rỗng”

Kể cả trong `AUTO`:

~~~java
@RabbitListener(queues = "payments.process.q")
public void onMessage(String event) {
    try {
        paymentService.process(event);
    } catch (Exception ex) {
        log.warn("Payment processing failed", ex);
        // Bỏ qua exception và RETURN bình thường.
    }
}
~~~

Container thấy listener **return thành công** và thường ACK message. Nếu yêu cầu retry/DLQ, không được swallow lỗi như vậy mà không lưu trạng thái thất bại vào một persistent failure store đã được xác minh.

### 10.3. Error handler và Retry Advice có thể che mất exception gốc

Một `@RabbitListener(errorHandler = "...")` hoặc container `ErrorHandler` có thể:

- Chuyển exception thành một kết quả/reply.
- Ném một loại exception khác.
- Quyết định rằng lỗi đã được xử lý.
- Ảnh hưởng reject/requeue tùy cơ chế và phiên bản.

Khi điều tra, đọc **cả listener code, retry advice chain, RabbitListenerErrorHandler và container errorHandler**. Không chỉ nhìn stacktrace bên trong business service rồi suy luận broker nhận `basic.reject`.

## 11. Case study: nhận diện từng kiểu sự cố

### Case A — Requeue ngay sau mỗi exception

**Dấu hiệu:**

~~~text
10:00:00.100 process eventId=evt-17 failed: IllegalArgumentException
10:00:00.103 process eventId=evt-17 failed: IllegalArgumentException
10:00:00.106 process eventId=evt-17 failed: IllegalArgumentException
...
RabbitMQ: deliver/redeliver rate tăng cao, DLQ depth = 0
~~~

**Giả thuyết:** `defaultRequeueRejected=true` và exception không được phân loại fatal; hoặc manual `basicNack(..., true)`. **Cách xác nhận:** kiểm tra factory, error handler, ACK mode, code/manual channel và chỉ số redelivery; thử một poison message trên broker test.

**Khắc phục:** phân loại permanent/transient; với permanent reject(false), bổ sung DLX/DLQ và idempotency. Với transient, backoff có giới hạn; không requeue ngay hàng nghìn lần.

### Case B — Spring Retry chạy bốn lần rồi message biến mất

**Dấu hiệu:**

~~~text
evt-21 attempt=1 error=DBTimeout
evt-21 attempt=2 error=DBTimeout
evt-21 attempt=3 error=DBTimeout
evt-21 attempt=4 error=DBTimeout
retry exhausted, WARN logged
main queue decreases; DLQ remains empty
~~~

**Giả thuyết:** default `MessageRecoverer` hoặc custom recoverer log rồi return; container ACK original delivery.

**Khắc phục:** nếu muốn broker DLX, dùng `RejectAndDontRequeueRecoverer` (và DLX hợp lệ). Nếu muốn application republish, dùng error exchange rõ ràng, xác nhận publish và biết rằng broker DLQ của source có thể rỗng.

### Case C — Container reject(false), DLX ghi sai tên

**Dấu hiệu:** trên log container thấy reject/no requeue, queue chính giảm, DLQ không nhận. Queue arguments chỉ tới `payments.dead.events` trong khi exchange hiện tại là `payments.dead.x`.

**Nguyên nhân:** broker cố dead-letter đến exchange không tồn tại. Ở chế độ at-most-once, message có thể bị drop.

**Khắc phục:** xác minh **effective queue arguments/policy**, sửa tên DLX bằng quy trình topology migration có kiểm soát, đảm bảo exchange và DLQ binding được provision trước. **Không thể khôi phục message đã drop chỉ bằng sửa binding**; cần outbox/replay từ nguồn đáng tin cậy nếu tồn tại.

### Case D — DLX tồn tại nhưng không có binding phù hợp

~~~text
source queue x-dead-letter-routing-key = payment.failed
DLX type: direct
DLQ binding routing key = payment.failure  <-- sai!
~~~

Publisher và listener đều hoạt động, broker có thể drop message dead-letter vì **DLX không route được**. Sửa binding thành `payment.failed`; không đổi thành fanout để “cho chắc” nếu sẽ phát dữ liệu sang queue không được phép.

### Case E — Restart app sau sửa YAML nhưng DLX vẫn cũ

**Dấu hiệu:** Java `QueueBuilder` được đổi sang `payments.dead.v2.x`; startup log có `PRECONDITION_FAILED - inequivalent arg 'x-dead-letter-exchange'`, consumer không mở channel như mong đợi.

**Nguyên nhân:** queue đã tồn tại với arguments khác. RabbitMQ không cho redeclare một queue cùng tên nhưng thuộc tính không tương thích.

**Khắc phục:** không xóa/purge production queue để ép đổi. Ưu tiên policy cho DLX ở triển khai mới, hoặc tạo queue mới và migration có quản lý. Ghi nhận state message cũ và rollback.

### Case F — DLQ thực ra là retry queue có TTL

~~~text
work.q -> retry.q (TTL = 5s) -> work.q -> retry.q -> ...
~~~

Queue `retry.q` có thể rỗng phần lớn thời gian vì message hết TTL rồi quay lại `work.q`; nhưng không có **terminal DLQ** nào. Đó là delayed-retry loop vô hạn.

**Khắc phục:** tách **retry queue** và **terminal DLQ**, giới hạn attempts bằng metadata/persistent state hoặc cơ chế broker hỗ trợ; khi hết attempts chuyển vào terminal DLQ, không quay lại work.

### Case G — Quorum queue vượt delivery limit mà không có DLX

RabbitMQ **4.0+ quorum queues** có **delivery limit mặc định 20** theo tài liệu RabbitMQ. Nếu message bị giao lại nhiều lần và vượt giới hạn, broker có thể **drop message** nếu không có DLX. Vì vậy cùng một ứng dụng chạy với classic queue và quorum queue có thể biểu hiện rất khác nhau.

**Khắc phục:** kiểm tra queue type, phiên bản broker, `delivery-limit` đang hiệu lực và cấu hình DLX. Khi cần bảo vệ việc dead-letter tới target, đánh giá at-least-once DLX riêng.

### Case H — Fatal conversion error đã có x-death

Một message từng từ retry/DLX quay về queue chính và có `x-death`; JSON/content encoding vẫn sai. `ConditionalRejectingErrorHandler` có thể **discard fatal message có x-death** để ngăn một vòng DLX vĩnh viễn. Đội vận hành chỉ thấy message “biến mất” và DLQ rỗng, dù handler đã có log.

**Khắc phục:** xác định nguồn poison message, kiểm tra warning của Spring, dừng retry cycle không giới hạn, lưu failure record có kiểm soát. Đừng tắt `discardFatalsWithXDeath` mà không thiết kế đường xử lý terminal.

### Case I — DLQ nhận rồi consumer khác ACK ngay

DLQ có `Consumers > 0` và một “DLQ processor” tự ACK hoặc republish message. Queue depth bằng 0 ở thời điểm quan sát không chứng minh DLX không hoạt động.

**Khắc phục:** tạm quan sát log/metric của DLQ processor, bảng failure store, redrive history và ACK rates. Không dừng consumer DLQ production bừa bãi nếu nó đang phục vụ workflow bắt buộc.

### Case J — Hai cấp retry nhân số lượt thực thi

~~~text
Spring Retry: 4 attempts per delivery
RabbitMQ broker retry: 5 deliveries
Potential listener invocations: up to 4 x 5 = 20
~~~

Đây chỉ là phép đếm **minh họa khi chính sách đúng như trên**, chưa tính reconnect/replay/producer retry. Không hạ tầng nào tự biết tổng “ngân sách retry toàn hệ thống” nếu mỗi lớp giữ bộ đếm riêng.

**Khắc phục:** định nghĩa một **retry budget** cho event, liệt kê từng cấp và điều kiện terminal; đo theo eventId/logical operation thay vì chỉ đo broker redelivery flag.

## 12. Quorum queue: delivery limit và at-least-once dead-lettering

### 12.1. Khác classic queue ở điểm nào?

| Đặc điểm | Classic queue | Quorum queue |
| --- | --- | --- |
| Broker có `delivery-limit` mặc định 20 ở RabbitMQ 4.0+? | Không theo cùng ngữ nghĩa quorum. | **Có**, theo tài liệu RabbitMQ 4.0+. |
| Nhiều lần NACK requeue=true | Có thể gây vòng lặp nếu không có giới hạn ứng dụng. | Có cơ chế delivery limit, nhưng phải xem policy/loại lỗi và version. |
| Dead-letter qua DLX thông thường | At-most-once theo cơ chế mặc định. | At-most-once mặc định; có thể cấu hình at-least-once. |
| Tự bảo đảm DLQ không mất message? | **Không.** | **Không tự động**, cần config at-least-once và các điều kiện phù hợp. |

**Đặc biệt về bản nâng cấp:** RabbitMQ 3.x quorum queues có hành vi delivery-limit mặc định khác so với RabbitMQ 4.0. Vì vậy một môi trường staging dùng 3.x có thể requeue “vô hạn”, còn production 4.x thì drop sau một giới hạn. Ghi **broker version + queue type + effective policy** trong mỗi báo cáo sự cố.

### 12.2. Cấu hình at-least-once dead-lettering cần điều kiện riêng

RabbitMQ quorum queues có thể giữ dead-letter message tại nguồn và **chỉ xóa sau khi dead-letter target xác nhận**. Một policy theo ví dụ của RabbitMQ có thể yêu cầu:

~~~json
{
  "dead-letter-exchange": "payments.dead.x",
  "dead-letter-routing-key": "payment.failed",
  "dead-letter-strategy": "at-least-once",
  "overflow": "reject-publish",
  "max-length": 100000
}
~~~

Đây là **định nghĩa policy minh họa**, không phải application.yml. Điều kiện đầy đủ tùy version còn liên quan feature flag cần thiết, source phải là quorum queue và target DLX/queue hợp lệ. Không copy áp trực tiếp lên production mà chưa xác minh khả năng hỗ trợ, giới hạn queue và tình trạng target.

**Đánh đổi quan trọng:** khi DLQ/target không nhận message, source quorum queue có thể **giữ lại các dead-letter deliveries**; chúng vẫn chiếm tài nguyên và được tính vào giới hạn queue. Nếu target outage kéo dài, source có thể đầy và từ chối publish mới. At-least-once dead-lettering giảm nguy cơ mất message khi chuyển nhưng **không miễn phí**.

### 12.3. Khi DLQ đích không có quorum hoặc route

Với at-least-once, broker có thể ghi log không forward được dead-letter vì:

- DLX đã bị xóa.
- DLX không có binding tới queue đích.
- Quorum của target không khả dụng.
- Source/target vượt giới hạn hoặc trạng thái mạng/node không cho xác nhận.

Message có thể **được giữ tại source** và retry forward sau, không xuất hiện ngay ở DLQ. Quan sát **broker logs, dead-letter pending, source queue metrics, target availability**, không chỉ DLQ depth.

**Không đồng nhất** delivery limit của quorum queue với `RetryInterceptorBuilder.maxAttempts`. Một bộ đếm ở broker, một bộ đếm ở consumer JVM; nếu muốn giới hạn nghiệp vụ đầu cuối phải thiết kế rõ cách phối hợp.

## 13. Kiểm thử tích hợp: poison message phải tới DLQ

### 13.1. Chuẩn bị môi trường cô lập

Một bài test chẩn đoán đúng phải dùng **broker test** và một topology nhỏ, không dùng production queue. Để tái tạo, dùng:

- Java 17, Spring Boot **3.1+**, `spring-boot-starter-amqp` và `spring-retry`.
- `spring-boot-starter-test` (JUnit 5), `spring-boot-testcontainers`.
- `org.testcontainers:rabbitmq` và `org.testcontainers:junit-jupiter` phiên bản tương thích.
- RabbitMQ 4.x trong Testcontainers.

Maven test dependencies minh họa:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.retry</groupId>
        <artifactId>spring-retry</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>rabbitmq</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Các ví dụ Java ở mục 7 và 8 nên được đặt trong demo/test module. **Chỉ bật `BoundedPaymentListener`** khi chạy bài test này, không cùng lúc với các listener minh họa `BrokenPaymentsListener`, `PaymentErrorClassificationExample` hoặc `ManualPaymentListener` trên queue `payments.process.q`.

### 13.2. Testcontainers với context chỉ import thành phần cần thiết

~~~java
// PaymentRetryDlqIntegrationTest.java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Import;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest(classes = PaymentRetryDlqIntegrationTest.TestApp.class)
class PaymentRetryDlqIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4.1-management");

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableRabbit
    @Import({
        PaymentDeadLetterTopology.class,
        BoundedPaymentListenerConfiguration.class,
        BoundedPaymentListener.class
    })
    static class TestApp {
    }

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Test
    void poisonMessageIsDeadLetteredAfterBoundedRetries() {
        String payload = "BAD:evt-501";

        rabbitTemplate.convertAndSend(
                PaymentDeadLetterTopology.EVENTS_X,
                PaymentDeadLetterTopology.EVENTS_KEY,
                payload);

        // DLQ không có @RabbitListener trong test; polling chỉ dành cho test.
        Message dead = rabbitTemplate.receive(
                PaymentDeadLetterTopology.DLQ, 15_000);

        assertNotNull(dead, "Poison message did not arrive at DLQ");
        assertEquals(payload,
                new String(dead.getBody(), StandardCharsets.UTF_8));

        // Header do RabbitMQ thêm khi broker DLX, không phải app republish.
        Object deaths = dead.getMessageProperties()
                .getHeaders().get("x-death");
        assertNotNull(deaths, "Expected broker-generated x-death history");
    }
}
~~~

**Điều kiện chạy:** Docker/Testcontainers khả dụng và có quyền tạo container. Trong test đơn giản, RabbitAdmin do Boot cấu hình sẽ khai báo exchange/queue/binding trước khi listener nhận; nếu startup/declaration lỗi, cần sửa topology chứ không thêm `Thread.sleep(30000)`.

**Lưu ý cực kỳ quan trọng:** `RabbitTemplate.receive(DLQ, timeout)` là **consumer polling**, sẽ lấy message ra khỏi DLQ và theo chế độ template có thể **ACK/xóa delivery**. Điều này phù hợp **test cô lập**, không dùng để “xem thử” thông điệp trên **production DLQ** nếu không có quy trình bảo vệ bằng chứng.

### 13.3. Kết quả mong đợi

| Điều kiện | Đường message | Assertion |
| --- | --- | --- |
| `BAD:evt-501` | Listener lỗi → retry interceptor tối đa 4 attempts → `RejectAndDontRequeueRecoverer` → broker DLX. | DLQ có body và `x-death` do broker thêm. |
| `GOOD:evt-502` | Listener hoàn tất bình thường → container ACK. | Queue nguồn drain; DLQ không có event này. |
| `TEMP:evt-503` và DB giả lập luôn lỗi | Retry có backoff → hết attempts → reject(false). | DLQ nhận event, không hot-loop vô hạn. |
| Cấu hình recoverer chỉ log rồi return | Retry hết nhưng container ACK. | Main queue drain, **DLQ không nhận**. |
| Bỏ `deadBinding` hoặc đổi sai `DL_KEY` | Broker không route được dead-letter. | DLQ không nhận; test phát hiện topology lỗi. |
| Đổi `defaultRequeueRejected=true` và bỏ retry/recoverer terminal | Poison có thể requeue ngay liên tục. | Redelivery rate tăng; test **phải có timeout và cách dừng consumer**. |

**Không cố tạo vòng lặp vô hạn trên shared test broker** chỉ để chứng minh vấn đề. Có thể so sánh ít attempts có đo bằng `AtomicInteger`, hoặc chạy trong container có giới hạn resource và ngừng consumer ngay khi đã quan sát. Không đặt các test thử lỗi phá hoại vào CI chạy trên môi trường dùng chung.

### 13.4. Thêm test để phân biệt DLX và application republish

Một test riêng (context/bean recovery riêng) có thể thay `RejectAndDontRequeueRecoverer` bằng `RepublishMessageRecoverer`:

~~~text
Original queue: payments.process.q
Error exchange: payments.errors.x
Error queue: payments.errors.q

Expected:
  error queue receives message with application-added exception headers
  original delivery is ACKed if republish succeeds
  original broker DLQ remains empty for this failure path
~~~

Với ứng dụng quan trọng, nên dùng `RepublishMessageRecovererWithConfirms` hoặc cơ chế tương đương có kiểm tra outcome, sau đó assert application error queue và failure record. Không coi `x-death` là bắt buộc trong đường republish này.

### 13.5. Test transaction và fail-after-commit

Một test quan trọng khác:

1. Consumer nhận event có `eventId=evt-600`.
2. Database transaction lưu payment và dấu inbox thành công.
3. Giả lập consumer crash/mất channel **trước khi broker nhận ACK**.
4. Broker requeue/redeliver event.
5. Consumer dùng unique eventId để nhận ra đã xử lý; không trừ tiền lần nữa; ACK delivery mới.

Test harness chỉ chứng minh method được gọi; để bảo đảm độ tin cậy phải **assert database side effect**. Khi mô phỏng crash, không hard-code sleep; sử dụng test hooks/latches hoặc kiểm soát tiến trình test để tạo đúng thời điểm.

## 14. Observability: phải nhìn được từng lớp retry

### 14.1. Ghi log có cấu trúc

Ví dụ event chẩn đoán:

~~~json
{
  "timestamp": "2026-11-26T03:40:00Z",
  "level": "WARN",
  "event": "amqp.consumer.delivery_failed",
  "service": "payments-service",
  "broker": "orders",
  "vhost": "/",
  "queue": "payments.process.q",
  "eventId": "evt-501",
  "messageId": "evt-501",
  "redelivered": true,
  "ackMode": "AUTO",
  "retryLayer": "spring-retry",
  "errorCategory": "invalid_schema",
  "action": "reject_without_requeue"
}
~~~

Đây là **schema log do ứng dụng đề xuất**, không phải RabbitMQ/Spring AMQP tự sinh đầy đủ. Không log body chứa số tài khoản, token, thông tin định danh, exception nguyên văn có PII hoặc toàn bộ payload trong DLQ. `eventId` có thể cần masking/opaque ID theo chính sách bảo mật.

**Nên có cùng các trường** `queue`, `eventId`, `exception_class`, `retryLayer` và `action` trong đoạn retry listener, recoverer, consumer settlement và DLQ redrive. Nếu mỗi lớp dùng tên biến khác nhau, chẩn đoán sẽ dựa vào việc đọc hàng trăm dòng stacktrace mà vẫn không biết lần lỗi nào dẫn đến requeue.

### 14.2. Các metric cần đo

| Metric đề xuất (custom application) | Tag ít cardinality | Mục đích |
| --- | --- | --- |
| `app_amqp_listener_attempts_total` | queue_group, error_category, result | Số lượt gọi xử lý thực, có thể lớn hơn deliveries. |
| `app_amqp_retry_exhausted_total` | queue_group, retry_strategy | Số lần hết Spring Retry budget. |
| `app_amqp_recoverer_outcomes_total` | recoverer_type, outcome | Phát hiện default log-and-ACK vs reject/republish. |
| `app_amqp_terminal_reject_total` | queue_group, reason | Theo dõi đường reject(false). |
| `app_amqp_business_duplicates_total` | operation_group | Phát hiện redelivery không tạo side effect trùng. |
| `app_amqp_business_pending_age_seconds` | operation_group | Xác định tác vụ bỏ dở dù queue đã ACK. |

Đây là **tên metric minh họa do ứng dụng tự định nghĩa**, không phải tên có sẵn trong Spring Boot hoặc RabbitMQ exporter. Đừng đặt `eventId`, raw `customerId` hoặc exception message làm metric tag vì số time series sẽ tăng vô hạn.

Tầng RabbitMQ cần xem thêm:

- Ready, unacked, consumers cho **source và DLQ**.
- Deliver, redeliver, ack, nack và reject rates.
- Queue ingress/egress, DLX routing activity khi exporter/Management cung cấp.
- Quorum source queue delivery limit/dead-letter pending khi có hỗ trợ.
- Memory/disk alarms, connection blocked, channel closures và node availability.

Tên metric chính xác khác nhau theo RabbitMQ exporter/Prometheus plugin và phiên bản. Không giả định mọi hệ thống có sẵn metric tên `rabbitmq_queue_redeliver_total` hoặc tag `broker`; đối chiếu exporter đang cài, thêm label ổn định khi scrape nếu cần.

### 14.3. Cảnh báo có ý nghĩa

| Tín hiệu | Gợi ý cảnh báo |
| --- | --- |
| Redelivery rate tăng kéo dài, nhưng business completion không tăng | Nghi **requeue loop** hoặc downstream outage; điều tra ngay. |
| `retry_exhausted_total` tăng nhưng DLQ ingress = 0 | Kiểm tra default recoverer ACK, manual ack, DLX/binding và DLQ consumer. |
| DLQ oldest message age vượt SLA | Tác vụ lỗi không được triage/redrive kịp thời. |
| Message ready/unacked tăng mạnh cùng DB errors | Downstream bottleneck; áp backpressure/backoff. |
| Fatal conversion errors và `discardFatalsWithXDeath` tăng | Schema/encoding sai, broker retry cycle; ngăn message drop không quan sát. |
| Quorum at-least-once dead-letter pending tăng | DLX target unavailable/unroutable hoặc quyền/tài nguyên bị giới hạn. |
| Rất nhiều duplicate events trong DB inbox | Broker redelivery/producer republish đang xảy ra; cần xem retry budget và kết quả confirm. |

**Đừng đặt cảnh báo chỉ theo “DLQ = 0 là khỏe”.** Một DLQ rỗng có thể là dấu hiệu chưa có lỗi, cũng có thể là dấu hiệu **message đã bị ACK hoặc bị drop**. Kết hợp nguồn metrics, số event nguồn, outbox/inbox và trạng thái nghiệp vụ để biết điều nào đúng.

## 15. Khôi phục và redrive an toàn sau khi đã sửa lỗi

Đưa message từ DLQ về queue chính không đơn giản là publish lại body:

~~~text
Business source/outbox
          |
          v
     Producer eventId
          |
          v
       Main queue
          |
          +---- temporary outage ------> retry with budget
          |
          +---- permanent failure -----> terminal DLQ
                                           |
                                           v
                                   Triage + diagnosis
                                           |
                                  fix schema/service/config
                                           |
                                           v
                                 Controlled redrive job
                                           |
                             confirm + audit + rate limit
                                           |
                                           v
                                Main queue, same eventId
                                           |
                                           v
                                  Idempotent consumer
~~~

### 15.1. Trước khi redrive một message

1. Xác minh **nguyên nhân gốc đã được sửa**; nếu không, message sẽ tiếp tục thất bại và quay lại DLQ.
2. Xác định business event còn cần xử lý không; có event đã hoàn thành nhưng ACK bị mất, hoặc đã bị hủy theo nghiệp vụ.
3. Kiểm tra `eventId`/`businessOperationId`, tenant, eventType/schemaVersion, thời hạn nghiệp vụ và quyền của đích.
4. Xác định **exchange và routing key gốc** từ nguồn đáng tin cậy. Nếu DLX đã thay key thành `payment.failed`, không dùng nhầm key đó để publish đến main exchange.
5. Giữ nguyên business ID để consumer idempotent. Nếu cần chuyển schema, dùng **upcaster/migration rõ ràng**, không tự đổi meaning của event.
6. Giới hạn rate/concurrency và số attempts, tránh DLQ storm khi tất cả message được phát lại cùng lúc.
7. Theo dõi publisher confirms/returns và một **persistent redrive audit record**; không coi API call thành công là consumer xử lý xong.
8. Ghi nhận outcome **success**, **already processed**, **still failing**, **quarantined**, **unknown** rồi đối soát.

### 15.2. Inbox idempotency ngăn side effect trùng

Ví dụ bảng PostgreSQL:

~~~sql
CREATE TABLE processed_payment_events (
    consumer_name TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khi xử lý:

~~~sql
INSERT INTO processed_payment_events(consumer_name, event_id)
VALUES ('payment-processor', :event_id)
ON CONFLICT DO NOTHING;
~~~

Nếu insert được **một dòng**, xử lý thay đổi nghiệp vụ và dấu inbox **trong cùng DB transaction**. Nếu không insert vì đã có khóa, coi đó là duplicate và không tạo side effect mới. Nếu transaction rollback, cả inbox và nghiệp vụ phải rollback.

**Không tạo bảng inbox rồi insert sau khi gửi email/trừ tiền**, vì crash ở giữa vẫn có thể tạo side effect trùng. Với side effect bên ngoài DB, cần idempotency key ở downstream hoặc một workflow có đối soát/compensation phù hợp.

### 15.3. DLQ redrive không được tạo một message mới về mặt nghiệp vụ

Ví dụ:

~~~text
eventId                = evt-900
original exchange      = payments.events.x
original routing key   = payment.created
business operation     = authorize-payment-900

DLQ delivery route     = payments.dead.x / payment.failed

Redrive:
  new AMQP publish attempt -> payments.events.x / payment.created
  same eventId             -> evt-900
  same business operation  -> authorize-payment-900
~~~

Nếu publish thành công nhưng consumer tiếp tục reject, kiểm tra nguyên nhân và tránh tự động re-drive cùng message vô hạn. Số lần redrive cần một **budget có kiểm soát**; audit record phải tồn tại độc lập với `x-death` và local memory.

### 15.4. Quarantine khác với DLQ

DLQ thường là queue error chung dùng cho điều tra, nhưng không phải mọi message lỗi đều được phép tự động retry. Những message liên quan:

- Giao dịch bị nghi gian lận.
- Sai chữ ký/MAC hoặc GCM authentication tag.
- Tenant không có quyền xử lý.
- Dữ liệu business quá hạn hoặc bị hủy.
- Event schema chưa có cách chuyển đổi đáng tin cậy.

...nên được chuyển sang **quarantine** hoặc persistent failure store có quyền truy cập hạn chế và bước phê duyệt/điều tra trước khi redrive. Không tự động đưa message không đáng tin cậy về main queue chỉ vì queue đã rỗng.

## 16. Bài thực hành chẩn đoán có kiểm soát

**Bối cảnh:** ứng dụng `payments-service` dùng `RabbitTemplate`, exchange `payments.events.x`, queue `payments.process.q` và `@RabbitListener`. Nhóm vận hành báo hai sự cố: message `BAD:evt-701` được xử lý hàng nghìn lần, còn `TEMP:evt-702` sau bốn lần retry biến mất nhưng DLQ rỗng.

### 16.1. Thiết lập

1. Tạo RabbitMQ test bằng Testcontainers, dùng exchange/queue/binding từ `PaymentDeadLetterTopology`.
2. Viết một listener cố ý throw `IllegalArgumentException` khi nhận `BAD:...` và throw `IllegalStateException` khi nhận `TEMP:...`.
3. Đặt listener container ở `AUTO`; bật các metric/log tại `eventId` và `error_category`.
4. Xác định loại queue **classic hoặc quorum**, RabbitMQ version và các policy đang áp dụng.

### 16.2. Thử nghiệm 1 — Requeue vô hạn

Trong **môi trường test riêng**, dùng một listener **không có retry interceptor** và để `defaultRequeueRejected=true`. Publish một message `BAD:evt-701`.

Quan sát trong **một cửa sổ ngắn và giới hạn**:

- Listener gọi liên tục.
- Redelivery rate tăng.
- `redelivered=true` có thể xuất hiện sau lần giao đầu.
- `x-death` chưa tăng nếu chỉ dùng NACK với `requeue=true`.
- DLQ trống vì chưa có dead-letter event.

**Ngừng consumer sau khi quan sát**, không để thử nghiệm chạy mãi. Sau đó đặt `defaultRequeueRejected=false` và bảo đảm DLX/binding đã cấu hình; publish **event ID mới** để xác minh message chuyển vào DLQ.

### 16.3. Thử nghiệm 2 — Retry hết nhưng ACK original

Đổi listener factory sang `RetryInterceptorBuilder.stateless().maxAttempts(4)`, nhưng thử với default recoverer hoặc một recoverer log rồi return.

Quan sát:

- Method được gọi tối đa bốn lần trong lượt retry.
- Sau khi recoverer xử lý và return, container ACK original.
- `payments.dead.q` không nhận message dù listener đã thất bại.

Đổi sang `RejectAndDontRequeueRecoverer`, chạy lại với **event ID mới**, xác minh:

- Original delivery được reject(false) sau exhaustion.
- DLQ có message và `x-death` với reason `rejected`.
- Không còn retry vô hạn cho một lần giao (trong topology không có retry cycle).

### 16.4. Thử nghiệm 3 — Sai dead-letter binding

Trên broker test, dùng một DLX có binding key `payment.failure` nhưng queue nguồn đặt dead-letter routing key `payment.failed`. Publish poison event.

Quan sát DLQ không nhận, dù message không được requeue. Kiểm tra `list_bindings` và `x-dead-letter-routing-key` để nhận ra sai khác. **Không thử xóa một queue production hiện có** để đổi arguments; dùng vhost/queue mới cho kịch bản test.

### 16.5. Thử nghiệm 4 — Retry queue TTL quay vòng

Thiết kế một `retry.1s.q` có TTL và dead-letter về main exchange. Cố ý không có terminal DLQ để quan sát việc message quay lại queue chính. Trong test, giữ **attempt cap** ở tầng ứng dụng hoặc tự dừng sau vài vòng.

Sau đó bổ sung **terminal DLQ** và đếm attempts bằng metadata/persistent state đáng tin cậy. Kiểm tra lỗi vĩnh viễn chấm dứt tại DLQ sau số vòng đã định, không trở lại main queue.

### 16.6. Thử nghiệm 5 — Quorum delivery limit

Tạo **quorum queue** riêng trong môi trường RabbitMQ 4.x, cấu hình `delivery-limit` thấp **chỉ để thử nghiệm**, đặt DLX/binding tới terminal DLQ. Tạo listener cố ý reject/requeue và kiểm tra khi vượt giới hạn.

So sánh với classic queue thử nghiệm có cùng producer/consumer, và viết ra khác biệt. Không suy từ test quorum “chặn loop giúp mình” để bỏ toàn bộ cơ chế idempotency/retry budget ở application.

### 16.7. Ma trận kết quả mong đợi

| Kịch bản | Source queue | DLQ | Dấu hiệu quyết định |
| --- | --- | --- | --- |
| NACK requeue=true vô hạn | Message có thể liên tục ready/unacked | Rỗng | Redeliver rate, listener attempts tăng. |
| Retry + default recoverer log/return | Giảm sau exhaustion | Rỗng | ACK original; không có broker DLX event. |
| Retry + RejectAndDontRequeueRecoverer + DLX hợp lệ | Giảm sau exhaustion | Có message | `x-death.reason=rejected`. |
| Reject(false) nhưng DLX không tồn tại | Giảm; có nguy cơ drop | Rỗng | Queue arguments trỏ exchange sai. |
| Reject(false) nhưng DLX binding sai | Giảm; có nguy cơ drop | Rỗng | Dead-letter key không khớp binding. |
| DLQ có consumer tự ACK | DLQ có thể rỗng ngay | Rỗng tại thời điểm nhìn | DLQ consumer/ACK rate tăng. |
| TTL retry cycle không giới hạn | Quay lại liên tục | Terminal DLQ rỗng | `x-death` phản ánh dead-letter qua queue. |
| Quorum delivery limit có DLX | Message kết thúc sau broker limit | Có thể có | `delivery_limit`, broker policy/version. |
| Quorum at-least-once, DLQ target unavailable | Source có thể giữ dead-letter pending | Chưa tới DLQ | Broker logs và source queue resources. |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Listener liên tục ném exception và RabbitMQ liên tục giao lại message. Vì sao DLQ có thể rỗng?

**Đáp án:** Nếu container hoặc manual code gửi `basicNack/basicReject` với `requeue=true`, message quay lại queue chính chứ **chưa dead-letter**. Cần kiểm tra ACK mode, `defaultRequeueRejected` và exception/retry policy.

**Câu 2.** `defaultRequeueRejected=false` có bảo đảm message vào DLQ không?

**Đáp án:** **Không.** Nó chỉ ảnh hưởng đến quyết định requeue sau lỗi; queue nguồn còn cần DLX, exchange tồn tại, routing key/binding đúng và target available. Nếu thiếu, message có thể bị discard.

**Câu 3.** Spring Retry đã `maxAttempts(4)`; tại sao sau đó message biến mất nhưng DLQ vẫn không có?

**Đáp án:** Retry interceptor có thể gọi recoverer mặc định **log rồi return**, khiến container ACK delivery gốc. Muốn broker dead-letter sau exhaustion, cần recoverer như `RejectAndDontRequeueRecoverer`; muốn application error queue thì dùng `RepublishMessageRecoverer` với cơ chế xác nhận phù hợp.

**Câu 4.** Có thể dùng `redelivered=true` để biết message đã retry bao nhiêu lần không?

**Đáp án:** Không. Nó là boolean hint, không phải counter. `x-death` ghi history dead-letter, **không đếm mọi immediate requeue**; dùng attempt metrics và eventId để quan sát toàn diện.

**Câu 5.** Broker đã dead-letter từ source với key `payment.failed`, nhưng DLQ bind `payment.failure`. Điều gì xảy ra?

**Đáp án:** Với direct DLX, không có binding khớp nên message **không được route tới DLQ**. Ở chế độ at-most-once, nó có thể bị mất. Sửa binding/key và kiểm tra policy/arguments đang hiệu lực.

**Câu 6.** Khi DLQ không nhận, có nên tạo thêm `@RabbitListener` đọc DLQ để “kích hoạt” nó không?

**Đáp án:** Không. Queue có thể nhận message **mà không cần consumer**; thêm listener còn có thể ACK ngay, làm dashboard DLQ rỗng và che bằng chứng. Trước tiên kiểm tra DLX, binding và dead-letter event.

**Câu 7.** Tại sao lỗi `MessageConversionException` có thể làm message bị reject dù method `@RabbitListener` chưa chạy?

**Đáp án:** Conversion xảy ra trước method; `ConditionalRejectingErrorHandler` có thể phân loại fatal và reject không requeue. Cần xem container logs/error handler thay vì chỉ xem log bên trong listener.

**Câu 8.** Vì sao nên tránh `basicNack(tag, false, true)` cho mọi exception?

**Đáp án:** Lỗi dữ liệu vĩnh viễn không tự khỏi, và requeue ngay tạo vòng lặp tiêu tốn CPU/network, cản trở message khác. Phân loại lỗi, giới hạn attempts và chọn DLQ/quarantine.

**Câu 9.** RabbitMQ 4.x quorum queue có default delivery limit; vậy có thể bỏ DLQ không?

**Đáp án:** Không. Khi vượt limit mà không cấu hình DLX, message có thể **bị drop**. Delivery limit giới hạn requeue nhưng không thay cho lưu giữ, điều tra và phục hồi công việc.

**Câu 10.** Tại sao `RepublishMessageRecoverer` không nhất thiết tạo `x-death`?

**Đáp án:** Đây là **application-level republish** đến error exchange; original delivery được ACK sau khi recoverer thành công, không đi qua broker DLX path. `x-death` do broker tạo khi dead-letter, không chỉ vì một ứng dụng publish message lỗi.

**Câu 11.** Một message đã vào DLQ và sau đó được redrive, có nên cấp eventId mới?

**Đáp án:** Thông thường **không** khi đó vẫn là cùng business operation. Giữ eventId/operation ID để idempotent consumer không tạo side effect trùng, đồng thời ghi redrive attempt riêng để theo dõi.

**Câu 12.** Queue `payments.dead.q` đang có `messages_ready=0`. Có thể kết luận không có dead-letter event?

**Đáp án:** Không. DLQ có thể đã được consumer ACK, TTL khiến message expire, queue bị purge hoặc không được route. Xem DLQ consumers, publish/ack history, failure store và broker logs.

## 18. Checklist phòng ngừa retry loop và mất dead-letter

### 18.1. Tại producer

- [ ] `RabbitTemplate` publish đúng exchange, routing key, vhost và queue contract.
- [ ] Bật **publisher confirms/returns** phù hợp; không coi `convertAndSend()` trả về là message đã xử lý.
- [ ] Với sự kiện không thể mất, có **transactional outbox** hoặc lưu bền vững tương đương.
- [ ] Event có `eventId`/business operation ID ổn định, không cấp ID mới mỗi lần retry.
- [ ] Không tự copy hoặc sửa `x-death` như một bộ đếm từ client.

### 18.2. Tại consumer Spring AMQP

- [ ] Xác định chính xác `AcknowledgeMode.AUTO/MANUAL/NONE` và hành vi ACK/NACK tương ứng.
- [ ] Kiểm tra `defaultRequeueRejected` đang có hiệu lực trên **đúng listener container factory**.
- [ ] Lỗi **permanent** không bị `basicNack(..., true)` vô hạn.
- [ ] Lỗi **transient** có backoff/jitter, giới hạn attempts và biện pháp chống retry storm.
- [ ] `AmqpRejectAndDontRequeueException`, `ImmediateRequeueAmqpException` chỉ dùng khi hiểu semantics.
- [ ] Kiểm tra `ConditionalRejectingErrorHandler`, fatal exceptions, `discardFatalsWithXDeath` và manual-mode behavior.
- [ ] Nếu có Spring Retry, xác định **recoverer khi exhaustion**: log/ACK, reject(false) hay republish.
- [ ] Với `RepublishMessageRecoverer`, kiểm tra error exchange, confirms/returns và trạng thái original ACK.
- [ ] Nếu có stateful retry, messageId có mặt/ổn định và state/restart behavior đã được test.
- [ ] Consumer không swallow exception rồi return thành công khi nghiệp vụ vẫn thất bại.
- [ ] ACK không được gửi hai lần hoặc gửi trên channel sai.
- [ ] Consumer dùng inbox/idempotency để chống side effect trùng sau redelivery.
- [ ] Với batch listener, hiểu phạm vi reject/ACK và duplicate amplification.

### 18.3. Tại RabbitMQ broker

- [ ] Queue nguồn có DLX/policy hiệu lực; không chỉ mới tạo DLQ.
- [ ] DLX **tồn tại**, đúng type, cùng vhost với source.
- [ ] `x-dead-letter-routing-key` hoặc original routing key **khớp binding DLQ**.
- [ ] Queue target còn tồn tại và không bị consumer/TTL/max length xóa message ngoài dự kiến.
- [ ] User có permissions phù hợp để khai báo/use source queue và DLX.
- [ ] Không có x-arguments cứng ghi đè policy mới một cách ngoài ý muốn.
- [ ] Không sửa queue arguments không tương thích bằng redeclare production; có migration plan.
- [ ] Không có vòng DLX/TTL quay lại main vô hạn mà thiếu terminal DLQ và retry budget.
- [ ] Với quorum queue, kiểm tra `delivery-limit`, dead-letter strategy, overflow policy và khả năng target nhận.
- [ ] Có metric/alert cho redelivery, retry exhaustion, DLQ oldest age, dead-letter failures và source backlog.

### 18.4. Tại vận hành và khôi phục

- [ ] Runbook ưu tiên **khoanh vùng, giảm tác hại, giữ bằng chứng**, không purge queue.
- [ ] Mỗi lần redrive đều giữ business event ID, có authorization, audit, rate limit và deadline.
- [ ] Failure store phân biệt `permanent`, `transient`, `security` và `unknown`.
- [ ] Có test Testcontainers cho **reject(true)**, **reject(false)**, **recoverer ACK**, **DLX misroute** và **quorum delivery limit**.
- [ ] Đối soát công việc **source → outbox → broker → consumer/inbox → kết quả nghiệp vụ**, không chỉ queue depth.
- [ ] Đã xác nhận cấu hình sau restart/deploy bằng RabbitMQ Management/CLI, không suy từ application.yml đơn thuần.

## 19. Tổng kết

Khi gặp **retry/requeue vô hạn và DLQ không nhận được thông điệp**, không nên vội kết luận RabbitMQ hoặc dead-letter exchange bị hỏng. Cần chia bài toán thành **hai câu hỏi độc lập**:

1. **Message có thực sự bị dead-letter không?** Nếu consumer gửi `requeue=true`, nếu Spring Retry recoverer **return bình thường** hoặc nếu listener **ACK sau catch**, thì broker **không có reject(false)** để chuyển message qua DLX.
2. **Nếu đã dead-letter, đường DLX có hoạt động không?** Kiểm tra DLX trên **queue nguồn**, exchange type, routing key/binding, vhost, permissions, x-arguments/policy, queue target, consumer DLQ và chiến lược dead-letter theo loại queue.

Trong **Spring AMQP**, phối hợp `defaultRequeueRejected`, `AmqpRejectAndDontRequeueException`, **retry interceptor có giới hạn** và **recoverer terminal phù hợp**. Với RabbitMQ, phân biệt broker **immediate requeue**, **TTL/DLX retry cycle**, **quorum delivery limit** và **at-least-once dead-lettering** theo phiên bản. Cuối cùng, dùng **eventId ổn định, outbox, inbox/idempotency, retry budget, monitoring và đối soát nghiệp vụ** để thông điệp không bị xử lý vô hạn và cũng không bị mất âm thầm khi cố khắc phục sự cố.

### Tài liệu tham khảo chính thức

- [Spring AMQP – Resilience: Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): `defaultRequeueRejected`, `AmqpRejectAndDontRequeueException`, `ImmediateRequeueAmqpException`, Spring Retry và recoverers.
- [Spring AMQP – Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): `ConditionalRejectingErrorHandler`, fatal exceptions, `x-death` và manual ACK.
- [Spring AMQP – Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): `defaultRequeueRejected`, container ACK mode, consumer behavior.
- [Spring AMQP 3.2 – RetryInterceptorBuilder Javadoc](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/config/RetryInterceptorBuilder.html): `maxAttempts`, `backOffOptions`, `recoverer`.
- [Spring AMQP – Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): publish confirms/returns và kết quả gửi.
- [RabbitMQ – Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): dead-letter conditions, policies, routing key, failure modes, `x-death` và at-least-once.
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): basic.ack/nack/reject, requeue loops, delivery tags và redelivery.
- [RabbitMQ – Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues): delivery limit, delayed retries và at-least-once dead-lettering.
- [RabbitMQ – Limits and Timeouts](https://www.rabbitmq.com/docs/limits): quorum queue delivery limit và queue policies.
- [RabbitMQ – Access Control](https://www.rabbitmq.com/docs/access-control): quyền người dùng, vhost, exchange và queue.
- [Spring Boot – Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` và broker test.
