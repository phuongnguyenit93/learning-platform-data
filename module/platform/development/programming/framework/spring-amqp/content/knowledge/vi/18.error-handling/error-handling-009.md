# Thông điệp poison, x-death và phòng tránh vòng lặp vô hạn trong Spring AMQP

Một message gây exception có thể được RabbitMQ giao lại nhiều lần. Nếu bản thân message sai cấu trúc, chứa schema không hỗ trợ hoặc liên tục kích hoạt một lỗi bất biến, việc **requeue ngay lập tức** không giúp hệ thống phục hồi. Thay vào đó, nó có thể làm CPU tăng, log tràn, consumer không xử lý được message lành và một tác vụ lỗi quay vòng hàng nghìn lần. Kiểu message như vậy thường được gọi là **poison message**.

Bài học thuộc chương **Xử lý lỗi** của module **SPRING_AMQP**. Khi tích hợp RabbitMQ bằng `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding, bạn cần thiết kế retry, consumer acknowledgement, dead-letter, giao dịch và giám sát sao cho **một message lỗi không phá khả năng phục vụ của toàn queue**. Hai kiến thức trọng tâm là: nhận diện **poison message** và hiểu chính xác **`x-death`** — lịch sử dead-letter do RabbitMQ ghi, **không phải** bộ đếm mọi lần listener thất bại.

## 1. Mục tiêu học tập

Hoàn thành bài, bạn có thể:

1. Phân biệt lỗi **vĩnh viễn**, lỗi **tạm thời** và lỗi có **kết quả không chắc chắn**.
2. Giải thích ba vòng lặp khác nhau: `requeue=true` trực tiếp, vòng **DLX → retry queue TTL → work queue**, và **republish thủ công**.
3. Đọc được `x-death`: `queue`, `reason`, `count`, `time`, `exchange`, `routing-keys`; biết cách RabbitMQ gộp lịch sử theo cặp queue/reason.
4. Không nhầm `x-death` với `redelivered`, `x-delivery-count`, message ID hoặc application retry count.
5. Hiểu `ConditionalRejectingErrorHandler` và hành vi `discardFatalsWithXDeath` trong Spring AMQP.
6. Chọn retry hữu hạn, backoff, quarantine/DLQ và idempotency cho luồng tiêu thụ.
7. Biết giới hạn của quorum queue `delivery-limit`, đặc biệt thay đổi semantics `basic.nack` từ RabbitMQ 4.3.
8. Cấu hình và kiểm chứng một mô hình xử lý poison message an toàn bằng Spring AMQP.

## 2. Poison message là gì?

**Poison message** là message liên tục khiến consumer không thể xử lý thành công trong điều kiện hiện tại, từ đó có nguy cơ bị nhận và thử lại không có điểm dừng. Nguyên nhân có thể nằm ở dữ liệu, code, môi trường hoặc cấu hình consumer.

| Nhóm lỗi | Ví dụ | Có nên thử lại cùng bytes ngay? |
|---|---|---|
| **Dữ liệu vĩnh viễn lỗi** | JSON không parse được, schema version không hỗ trợ, ID sai định dạng | Thường **không**; sửa producer/schema hoặc quarantine |
| **Lỗi nghiệp vụ bất biến** | Lệnh không hợp lệ theo rule không thay đổi | Thường **không**; cần quyết định reject/quarantine |
| **Phụ thuộc tạm thời lỗi** | Database timeout, HTTP 503, broker phụ trợ không sẵn sàng | Có thể retry **hữu hạn và có backoff** |
| **Kết quả không rõ** | Database commit thành công nhưng connection đứt trước consumer ack | Có thể redeliver; cần **idempotency** trước khi xử lý lại |
| **Lỗi triển khai** | Thiếu Jackson module, class mapping sai, thiếu quyền | Phải sửa ứng dụng/config; retry liên tục không giải quyết |

Không phải một message chỉ cần **thất bại lần đầu** đã được xác định là poison. Trái lại, một message có JSON sai cú pháp có thể được xác định là không thể xử lý với cùng converter ngay từ lần đầu. Quyết định retry cần dựa trên **khả năng lỗi có tự hết theo thời gian** và tính an toàn khi thực hiện lại nghiệp vụ.

### Vòng lặp poison tác động gì?

~~~mermaid
flowchart LR
    Q["Queue: work.q"] --> C["@RabbitListener"]
    C --> F["Lỗi không thể khắc phục"]
    F --> N["basic.nack / reject<br/>requeue=true"]
    N --> Q
    F -.-> M["CPU, network, logs tăng<br/>message khác bị đói"]
~~~

Một queue có thể có `messages_ready` không lớn nhưng tốc độ delivery/redelivery rất cao vì cùng một message đang quay vòng. Vì vậy không chỉ nhìn queue depth để kết luận hệ thống đang khỏe.

## 3. Nhận diện ba kiểu lặp thường gặp

| Kiểu lặp | Đường đi | Có sinh `x-death` không? | Rủi ro |
|---|---|---|---|
| **Requeue trực tiếp** | `work.q → consumer → requeue=true → work.q` | **Không chỉ vì requeue**; không có sự kiện dead-letter | Hot loop, cùng message được giao lại rất nhanh |
| **DLX + TTL retry queue** | `work.q → DLX → retry.q → TTL hết → DLX → work.q` | **Có**, trên những lần dead-letter qua từng queue | Vòng lặp có trì hoãn nhưng **vẫn vô hạn** nếu không có retry budget |
| **Republish thủ công** | Consumer publish lại message như một publish mới rồi ack bản cũ | Không tự động tăng `x-death` cho publish mới | Trùng message, mất trạng thái attempt, sai thời điểm ack |

### 3.1. Requeue=true không đồng nghĩa dead-letter

Nếu listener lỗi, container gửi `basic.reject(..., true)` hoặc `basic.nack(..., true)`, RabbitMQ **đưa delivery lại queue**. Không có bước chuyển tới dead-letter exchange, vì vậy **`x-death` không tăng chỉ từ hành động requeue trực tiếp**.

Điều này rất quan trọng: một message có thể được giao lại hàng trăm lần mà `x-death` **không tồn tại**. Việc kiểm tra `x-death == null` rồi kết luận “chưa retry lần nào” là sai.

### 3.2. Dead-letter mới cập nhật lịch sử

RabbitMQ dead-letter một message khi có điều kiện phù hợp, chẳng hạn:

1. Consumer `basic.reject` hoặc `basic.nack` với `requeue=false`.
2. Message hết TTL trong queue.
3. Queue loại message vì vượt giới hạn độ dài (`max-length`).
4. Quorum queue vượt `delivery-limit` theo semantics của phiên bản broker.

Các lần chuyển này được ghi vào **`x-death` trong AMQP 0-9-1** nếu message còn tiếp tục được định tuyến, với lịch sử và thông tin nguyên nhân. **Queue hết hạn và bị xóa** không có nghĩa mọi message trong queue đều được dead-letter như khi từng message hết TTL.

### 3.3. Republish là một lần publish mới

Nếu ứng dụng dùng `RabbitTemplate.convertAndSend` để gửi lại payload vào exchange, RabbitMQ xử lý đó như **một publish mới**. Application phải chủ động duy trì event ID/attempt metadata phù hợp. Từ RabbitMQ 4.0, broker không coi header `x-death` do client tự gửi là lịch sử broker hợp lệ; **không tự tạo hoặc chỉnh sửa `x-death`** để điều khiển retry.

## 4. x-death là gì và được lưu ở đâu?

`x-death` là **header do RabbitMQ tạo** trên message AMQP 0-9-1 khi message được dead-letter. Nó thường là **một mảng các bảng AMQP** (được Java client hiển thị dưới dạng `List` chứa các `Map`), không phải một số nguyên riêng lẻ.

Ví dụ minh họa đã đơn giản hóa thành JSON để dễ đọc:

~~~json
{
  "x-death": [
    {
      "queue": "orders.retry.q",
      "reason": "expired",
      "count": 2,
      "time": "2026-11-26T02:00:00Z",
      "exchange": "orders.retry.x",
      "routing-keys": ["retry"]
    },
    {
      "queue": "orders.work.q",
      "reason": "rejected",
      "count": 2,
      "time": "2026-11-26T01:59:30Z",
      "exchange": "orders.work.x",
      "routing-keys": ["work"]
    }
  ]
}
~~~

**Đây không phải literal wire JSON.** Trên RabbitMQ, header có kiểu dữ liệu AMQP; `time` là timestamp, `count` là kiểu số, `routing-keys` là mảng AMQP. Giá trị và thứ tự cụ thể của ví dụ chỉ dùng giải thích.

### Các trường thường gặp

| Trường trong mỗi phần tử | Ý nghĩa |
|---|---|
| `queue` | Queue **mà message rời đi khi bị dead-letter**; không nhất thiết là queue đang đọc hiện tại |
| `reason` | Lý do dead-letter: `rejected`, `expired`, `maxlen`, `delivery_limit` |
| `count` | Số lần dead-letter từ **queue đó với lý do đó** |
| `time` | Thời điểm đầu tiên dead-letter cho cặp queue/reason ở biểu diễn AMQP 0-9-1 hiện hành |
| `exchange` | Exchange trước lần dead-letter đầu tiên ở cặp queue/reason đó |
| `routing-keys` | Routing key trước lần dead-letter đầu tiên ở cặp đó |
| `original-expiration` | TTL per-message gốc, nếu có; có thể được broker lưu trước khi bỏ expiration khi dead-letter |

Khi cùng message bị dead-letter nhiều lần từ **cùng queue và cùng reason**, RabbitMQ **gộp lịch sử** thay vì thêm một phần tử mới cho mỗi lần. `count` tăng ở phần tử tương ứng. Vì thế:

- `x-death.length` **không phải** số lần message đã bị dead-letter.
- `x-death[0].count` **không phải** tổng retry mọi nơi.
- Thứ tự phần tử là theo **lần dead-letter gần đây nhất** ở cấp các cặp đã gộp.
- Trường `queue` là queue nguồn của dead-letter event, **không phải** exchange hoặc DLQ đích.

### Ví dụ diễn giải theo cặp queue/reason

Một message đi qua:

~~~text
Lần 1: work.q  --rejected--> retry.q
Lần 2: retry.q --expired-->  work.q
Lần 3: work.q  --rejected--> retry.q
Lần 4: retry.q --expired-->  work.q
~~~

Khi được trả lại `work.q`, `x-death` có thể có hai phần tử:

| queue | reason | count |
|---|---|---:|
| `retry.q` | `expired` | 2 |
| `work.q` | `rejected` | 2 |

Lịch sử này **không chứa** lần xử lý thành công cuối cùng, số lần gọi HTTP nội bộ của listener, hoặc số lần `requeue=true` giữa các lần dead-letter.

## 5. Phân biệt x-death với các dấu hiệu redelivery khác

| Tín hiệu | Ai đặt? | Nó đo điều gì? | Cạm bẫy |
|---|---|---|---|
| `redelivered` của delivery | RabbitMQ | Flag delivery có được giao lại sau lần trước hay không | Boolean, không cho biết số lần |
| `x-death` | RabbitMQ khi dead-letter | Lịch sử dead-letter, gộp theo queue/reason | Không đếm requeue trực tiếp |
| `x-first-death-queue/reason/exchange` | RabbitMQ | Thông tin lần dead-letter đầu tiên | Không phải attempt count |
| `x-last-death-queue/reason/exchange` | RabbitMQ | Thông tin lần dead-letter gần nhất, trên phiên bản hỗ trợ | Không tự chỉ ra toàn bộ lịch sử |
| `x-delivery-count` | Quorum queue trên phiên bản hỗ trợ | Số delivery thất bại theo semantics quorum | Khác `x-death.count`; phiên bản 4.3 đổi quy tắc |
| `x-acquired-count` | Quorum queue RabbitMQ 4.3+ | Số lần message được gán cho consumer | Gán không có nghĩa business method đã chạy |
| `retry-attempt` tự đặt | Ứng dụng | Số lần theo **hợp đồng retry của ứng dụng** | Phải chống giả mạo/thiếu header và bảo toàn khi republish |
| `eventId` / `messageId` | Producer/ứng dụng | ID logic của event/message | ID không phản ánh số lần giao |

Ví dụ: nhận được message có `redelivered=true`, không có `x-death`, vẫn hoàn toàn có thể là message đã được requeue trực tiếp. Ngược lại, một message mới đi từ retry queue qua DLX về work queue có `x-death` nhưng không nên suy ra nó là **cùng một delivery trên cùng channel**.

## 6. Đọc x-death an toàn trong Spring AMQP

Tại listener nhận raw Spring AMQP `Message`, có thể đọc headers:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.amqp.core.Message;

public final class DeadLetterHistory {

    private DeadLetterHistory() {}

    public static long countFor(
            Message message, String queue, String reason) {
        Object raw = message.getMessageProperties()
                .getHeaders().get("x-death");

        if (!(raw instanceof List<?> entries)) {
            return 0L; // Không có lịch sử broker nhìn thấy được.
        }

        long count = 0;
        for (Object entry : entries) {
            if (!(entry instanceof Map<?, ?> item)) {
                continue;
            }

            if (queue.equals(String.valueOf(item.get("queue")))
                    && reason.equals(String.valueOf(item.get("reason")))) {
                Object value = item.get("count");
                if (value instanceof Number number) {
                    count += number.longValue();
                }
            }
        }
        return count;
    }
}
~~~

Đoạn code dùng Java 17+ và kiểm tra kiểu dữ liệu trước khi đọc, tránh cast trực tiếp `List<Map<String, Object>>` hoặc `Long` cố định. Đọc:

~~~java
long rejectedFromWork = DeadLetterHistory.countFor(
        message, "orders.work.q", "rejected");

long expiredFromRetry = DeadLetterHistory.countFor(
        message, "orders.retry.q", "expired");
~~~

**Giới hạn của code này:** `0` có nghĩa **không tìm thấy lịch sử dead-letter tương ứng trong header**, không chứng minh message chưa bao giờ được xử lý lỗi. `countFor` là thống kê theo queue/reason, **không phải bộ đếm retry nghiệp vụ tổng quát**. Khi producer có thể republish message mới, lịch sử broker của bản mới có thể không tương đương bản trước; hãy quản lý attempt budget tường minh.

Nếu ứng dụng dùng AMQP 1.0 thay vì AMQP 0-9-1, cơ chế metadata là `x-opt-deaths` trong message annotation; đoạn Java trên dành cho Spring AMQP dùng RabbitMQ AMQP 0-9-1.

## 7. Vì sao chỉ dùng x-death để giới hạn retry là chưa đủ?

Một số hướng dẫn dùng quy tắc: “Nếu `x-death[0].count >= 3` thì dừng retry”. Quy tắc ấy **không tổng quát** vì:

1. Message chưa dead-letter lần nào sẽ không có `x-death`, dù đã `requeue=true` rất nhiều lần.
2. `x-death[0]` là sự kiện gần nhất theo queue/reason, không nhất thiết là `work.q/rejected` mà bạn muốn đo.
3. Một message có thể ghé qua nhiều retry queues với `reason=expired`; mỗi queue/reason có `count` riêng.
4. Republish thủ công có thể tạo message mới với metadata khác, không thể suy liên tục retry của cùng logical event từ header.
5. Một application có thể xử lý lại sau khi được operator replay từ DLQ, với chính sách attempt mới hoặc cũ.
6. `x-death` là metadata broker: dùng làm **bằng chứng lịch sử**, không nên bị sửa bởi client để “đặt lại retry”.

**Hướng khuyến nghị:** định nghĩa một **retry budget** tường minh theo loại lỗi, ví dụ:

~~~text
Transient database/API error:
  attempt 1: ngay
  attempt 2: sau 1 giây
  attempt 3: sau 5 giây
  sau đó: quarantine / DLQ + alert

Permanent schema/conversion error:
  attempt 1: reject không requeue → DLQ/quarantine
~~~

Bạn có thể dùng `x-death` làm **một nguồn thông tin** để tính lần đi qua retry queue trong topology cố định, nhưng cần viết và kiểm thử chính xác thuật toán đó. Nếu retry bao gồm republish, requeue trực tiếp và replay từ DLQ, nên dùng application attempt metadata cùng **event ID ổn định** và chiến lược xử lý duplicate.

## 8. ConditionalRejectingErrorHandler và poison message

Trong nhiều cấu hình Spring AMQP, `ConditionalRejectingErrorHandler` là error handler mặc định của listener container. Nó phân biệt những exception được xem là **fatal** ở tầng message conversion/method invocation để tránh retry vô hạn với dữ liệu không thể diễn giải.

Ví dụ nhóm lỗi thường được default fatal exception strategy nhận diện trên các phiên bản phù hợp:

- `org.springframework.amqp.support.converter.MessageConversionException`.
- `org.springframework.messaging.converter.MessageConversionException`.
- Lỗi binding/validation tham số như `MethodArgumentNotValidException` hoặc `MethodArgumentTypeMismatchException`.
- Một số lỗi chọn method hoặc ép kiểu như `NoSuchMethodException`, `ClassCastException`.

**Lưu ý:** đây không phải danh sách bao trùm mọi business validation. Một `IllegalArgumentException` tự ném trong nghiệp vụ không tự được coi fatal bởi mọi error strategy.

~~~mermaid
flowchart TD
    M["Delivery từ RabbitMQ"] --> C{"Conversion và listener"}
    C -->|"Thành công"| ACK["Ack theo container"]
    C -->|"Exception"| E["ConditionalRejectingErrorHandler"]
    E --> F{"Fatal theo strategy?"}
    F -->|"Không"| P["Container quyết định<br/>requeue/retry theo policy"]
    F -->|"Có, chưa có x-death"| N["Reject không requeue<br/>có thể DLX"]
    F -->|"Có, đã có x-death<br/>discardFatalsWithXDeath=true"| D["Log + discard<br/>không trả vào vòng DLX"]
~~~

### 8.1. Vì sao cần xử lý fatal riêng?

Nếu consumer nhận `{"orderId":}`, converter Jackson sẽ lỗi trước khi business handler được gọi. Retry lại chính những bytes đó trên cùng converter không thể giúp parse thành công. `ConditionalRejectingErrorHandler` có thể bọc lỗi fatal bằng `AmqpRejectAndDontRequeueException` để container reject không requeue, mặc dù `defaultRequeueRejected=true`.

Trường hợp này không chứng minh message chắc chắn vào DLQ: DLX có thể chưa tồn tại hoặc không có binding phù hợp. Luồng dead-letter cần kiểm thử end-to-end.

### 8.2. discardFatalsWithXDeath để cắt vòng quay DLQ → work

Từ Spring AMQP **2.1**, `ConditionalRejectingErrorHandler` nhận diện message đã có `x-death` và tiếp tục gặp exception được phân loại fatal. Trong cấu hình mặc định phù hợp, khi `discardFatalsWithXDeath=true`, handler **log và discard** thay vì tiếp tục đưa message quay vòng qua DLX và retry queue.

Giả sử:

~~~text
work.q (JSON lỗi) --reject không requeue--> retry.q
retry.q --TTL hết--> work.q
work.q (JSON vẫn lỗi) --fatal + x-death--> discard
~~~

**Đây là cơ chế ngăn lặp bảo vệ hệ thống, nhưng có thể làm mất message mà bạn muốn giữ để điều tra.** Do đó nếu cần audit/forensics, hãy tách đường **quarantine cuối cùng** khỏi một retry queue tự quay lại work queue. Đừng mặc định rằng fatal message có `x-death` sẽ được dead-letter lần nữa tới cùng DLQ.

Với các phiên bản Spring AMQP hỗ trợ, có thể thay hành vi này bằng `setDiscardFatalsWithXDeath(false)`; **không nên tắt chỉ để “không mất message”** nếu chưa có điểm dừng khác cho vòng lặp.

### 8.3. Fatal errors xảy ra trước method trong MANUAL mode

Từ Spring AMQP **2.1.9**, error handler có cơ chế `rejectManual` cho phép reject không requeue một số lỗi fatal **dù listener dùng MANUAL acknowledgement**, vì method nghiệp vụ không được gọi để ack/nack. Khi cấu hình `rejectManual=false` để đổi hành vi, cần kiểm chứng không để lại message unacked mãi.

Những hành vi này **phụ thuộc phiên bản**, và các bản mới có thể bổ sung lựa chọn dừng container khi fatal. Luôn đối chiếu docs/Javadoc của phiên bản Spring AMQP đang chạy.

## 9. Tránh hiểu sai defaultRequeueRejected

`defaultRequeueRejected` của listener container ảnh hưởng cách reject/nack khi listener lỗi và không có quy tắc đặc biệt ghi đè:

| Cấu hình/hành vi | Kết quả thường gặp |
|---|---|
| `AcknowledgeMode.AUTO`, exception thường, default `true` | Requeue trực tiếp, có nguy cơ vòng lặp |
| `AcknowledgeMode.AUTO`, exception thường, default `false` | Reject không requeue → DLX nếu có, không thì discard |
| Ném `AmqpRejectAndDontRequeueException` | Yêu cầu **không requeue** bất kể default |
| Ném `ImmediateRequeueAmqpException` | Yêu cầu **requeue** bất kể default; cẩn thận hot loop |
| Fatal conversion bị error handler chặn | Có thể reject hoặc discard theo `x-death` dù default `true` |
| `AcknowledgeMode.NONE` | Broker coi delivery đã ack lúc giao; không thể khôi phục bằng requeue từ exception |
| `AcknowledgeMode.MANUAL` | Code ứng dụng có trách nhiệm ack/nack; cần tính cả fatal trước method |

Chọn `defaultRequeueRejected=false` có thể ngăn hot loop, nhưng **không đồng nghĩa toàn bộ lỗi đều có DLQ** hoặc lỗi tạm thời được retry hữu hạn. Hãy xác định **đúng listener container**, retry advice và error handler đang hoạt động trước khi điều chỉnh.

## 10. Mô hình an toàn: queue nguồn → terminal DLQ

Thiết kế đơn giản nhất để ngăn một message lỗi vĩnh viễn quay vòng là:

~~~mermaid
flowchart LR
    P["RabbitTemplate producer"] --> X["lab.poison.x"]
    X -->|"work"| Q["lab.poison.work.q"]
    Q --> C["@RabbitListener"]
    C -->|"Success"| A["Consumer ack"]
    C -->|"Failure, không requeue"| D["lab.poison.dlx"]
    D -->|"dead"| DLQ["lab.poison.dlq<br/>quarantine cuối cùng"]
~~~

### 10.1. Khai báo exchange, work queue và DLQ

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PoisonLabTopology {

    @Bean
    DirectExchange poisonWorkExchange() {
        return new DirectExchange("lab.poison.x", true, false);
    }

    @Bean
    DirectExchange poisonDeadLetterExchange() {
        return new DirectExchange("lab.poison.dlx", true, false);
    }

    @Bean
    Queue poisonWorkQueue() {
        return QueueBuilder.durable("lab.poison.work.q")
                .deadLetterExchange("lab.poison.dlx")
                .deadLetterRoutingKey("dead")
                .build();
    }

    @Bean
    Queue poisonDeadLetterQueue() {
        return QueueBuilder.durable("lab.poison.dlq").build();
    }

    @Bean
    Binding poisonWorkBinding(Queue poisonWorkQueue,
                              DirectExchange poisonWorkExchange) {
        return BindingBuilder.bind(poisonWorkQueue)
                .to(poisonWorkExchange)
                .with("work");
    }

    @Bean
    Binding poisonDeadLetterBinding(Queue poisonDeadLetterQueue,
                                    DirectExchange poisonDeadLetterExchange) {
        return BindingBuilder.bind(poisonDeadLetterQueue)
                .to(poisonDeadLetterExchange)
                .with("dead");
    }
}
~~~

Topology này **không tự động retry**; nó có tuyến cuối để giữ lại những delivery bị reject không requeue, hết TTL hoặc chạm điều kiện broker phù hợp. `RabbitAdmin` hoặc hạ tầng quản lý queue/exchange/binding phải thực sự khai báo tài nguyên trong đúng virtual host. DLX được đặt bằng x-arguments trong ví dụ lab để dễ nhìn; trong production RabbitMQ thường khuyến nghị **policies** để dễ đổi mà không cần tạo lại queue.

Nếu queue đã tồn tại với arguments khác, redeclare bằng code mới có thể báo `PRECONDITION_FAILED`. Không xóa queue production còn message chỉ để áp dụng thử topology.

### 10.2. Listener có quyết định rõ ràng cho lỗi vĩnh viễn

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class PoisonLabListener {

    @RabbitListener(
        queues = "lab.poison.work.q",
        containerFactory = "poisonListenerFactory")
    public void onMessage(String body) {
        if (body.startsWith("INVALID:")) {
            throw new AmqpRejectAndDontRequeueException(
                    "Unsupported message contract");
        }

        if (body.startsWith("DB_DOWN:")) {
            throw new IllegalStateException(
                    "Database temporarily unavailable");
        }

        // Xử lý nghiệp vụ hoàn tất trước khi method return.
    }
}
~~~

Đây là payload `String` phục vụ lab. Khi dùng JSON converter, message có thể gặp lỗi **trước khi method được gọi**; lúc đó `ConditionalRejectingErrorHandler` xử lý thay vì `if (body.startsWith(...))`. Trong thực tế, phân biệt exception nghiệp vụ vĩnh viễn với lỗi tạm thời, không dùng cùng một fallback cho mọi trường hợp.

### 10.3. Cấu hình listener AUTO, tránh requeue vô hạn

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PoisonLabListenerConfiguration {

    @Bean
    SimpleRabbitListenerContainerFactory poisonListenerFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);
        factory.setConcurrentConsumers(1);
        factory.setPrefetchCount(1);
        return factory;
    }
}
~~~

`defaultRequeueRejected=false` khiến exception thông thường không được requeue khi không có retry/error handler ghi đè. Vì vậy `DB_DOWN:` ở ví dụ **sẽ vào DLQ ngay** nếu không cấu hình retry — đây là **hạn chế có chủ ý** của bước lab. Khi muốn retry lỗi tạm thời, phải bổ sung retry policy với điểm dừng, như phần kế tiếp.

**Lưu ý cấu hình Boot:** `SimpleRabbitListenerContainerFactoryConfigurer` dùng API của các nhánh Spring Boot phù hợp; tự tạo factory mà không dùng configurer có thể bỏ sót converter, retry, observation, transaction, ack và những properties của ứng dụng. Với phiên bản Boot khác, hãy kiểm tra API tương ứng.

## 11. Retry hữu hạn với Spring Retry và recoverer

Để xử lý `DB_DOWN:` có thể tự phục hồi, một lựa chọn là Spring Retry **trong listener thread**, với số lần thử và backoff hữu hạn. Sau khi vượt budget, `RejectAndDontRequeueRecoverer` yêu cầu reject không requeue, để queue nguồn dead-letter tới DLQ.

Ví dụ **minh họa nhánh Spring AMQP 3.2**:

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.retry.interceptor.RetryOperationsInterceptor;

RetryOperationsInterceptor retryAdvice =
        RetryInterceptorBuilder.stateless()
                .maxAttempts(3)
                .backOffOptions(500L, 2.0, 2000L)
                .recoverer(new RejectAndDontRequeueRecoverer())
                .build();

// Đặt vào listener factory trước khi container được tạo:
// factory.setAdviceChain(retryAdvice);
~~~

`maxAttempts(3)` trên API builder của nhánh minh họa biểu thị **tổng số lần thử theo cấu hình**, không phải “3 vòng broker redelivery mới”. Ở các phiên bản API khác, tên setter có thể là `maxRetries(...)` với semantics khác; phải đối chiếu Javadoc của version resolved. Điều quan trọng là **kiểm thử thực tế số lần gọi business method** thay vì suy từ tên hàm.

`stateless` phù hợp với trường hợp không có transaction bao ngoài cần rollback qua các lần thử. Nếu listener tham gia giao dịch bên ngoài cần rollback, hãy xem **stateful retry** và yêu cầu message identity; không copy stateless interceptor rồi mặc định transaction vẫn an toàn.

### 11.1. Phân loại transient và permanent

Mặc định một retry interceptor có thể retry nhiều loại exception, bao gồm cả lỗi không đáng retry nếu không có classifier. Vì vậy:

- Lỗi JSON/schema bất biến: reject/quarantine ngay hoặc cấu hình **không retry**.
- Lỗi database/API tạm thời: retry có backoff, giới hạn số lần và có timeout/circuit breaker.
- Outcome không chắc: dùng idempotency và xác định lại trạng thái tác động trước khi gửi lại.

Đừng dùng một cấu hình cố định “retry mọi lỗi 3 lần” để thay hoàn toàn phân loại lỗi. Nếu cần classifier theo cause, nhớ listener exception có thể được bọc trong `ListenerExecutionFailedException`; bộ phân loại phải xét cause chain đúng cách.

### 11.2. Recoverer có thể thay đổi đường dead-letter

| Recoverer | Kết quả thường gặp | Hệ quả |
|---|---|---|
| `RejectAndDontRequeueRecoverer` | Ném `AmqpRejectAndDontRequeueException` sau retry exhausted | Broker có thể dead-letter từ queue nguồn |
| `RepublishMessageRecoverer` | Publish một **message mới** tới error exchange, rồi có thể trả về bình thường | Delivery nguồn có thể được **ack**, không đi qua DLX của queue nguồn |
| `RepublishMessageRecovererWithConfirms` | Phiên bản hỗ trợ chờ broker confirms cho publish phục hồi | Giúp xử lý kết quả republish tốt hơn, không tạo transaction phân tán |
| Recoverer nuốt lỗi rồi return | Container coi recovery đã xử lý xong | Không có broker reject/DLX nếu không chủ động thực hiện |

Vì vậy, **DLQ trống không chứng minh listener không lỗi**: message có thể đã được republish sang error exchange khác và được ack tại nguồn. Quan sát cả retry advice/recoverer được gắn và routing của message.

## 12. TTL retry queue: mô hình hữu ích nhưng dễ thành vòng vô hạn

Một mẫu phổ biến là sử dụng queue chờ với TTL:

~~~mermaid
flowchart LR
    W["work.q<br/>consumer xử lý"] -->|"reject, requeue=false"| X1["retry.x<br/>DLX từ work.q"]
    X1 --> R["retry.q<br/>x-message-ttl = 30 giây"]
    R -->|"expired → DLX"| X2["work.x"]
    X2 --> W
~~~

### Tại sao TTL chưa phải retry policy?

Hình trên giúp **giãn thời gian** giữa các lần xử lý, nhưng **không giới hạn số vòng**. Nếu message sai schema vĩnh viễn, nó có thể đi qua DLX → TTL → DLX liên tục. Với mỗi vòng, `x-death` thường có cặp `work.q/rejected` và `retry.q/expired` tăng `count`; điều đó chỉ ghi lịch sử, **không tự chuyển sang terminal DLQ khi đạt một ngưỡng**.

Trong một topology thực, cần **thêm điểm quyết định** trước khi cho message quay lại:

~~~mermaid
flowchart TD
    M["Message lỗi transient"] --> B{"Retry budget còn?"}
    B -->|"Có"| WAIT["Chờ theo backoff<br/>retry queue / delayed retry"]
    WAIT --> WORK["Giao lại work consumer"]
    WORK -->|"Vẫn lỗi"| B
    WORK -->|"Thành công"| ACK["Consumer ack"]
    B -->|"Hết"| Q["Terminal quarantine / DLQ<br/>không tự route về work"]
~~~

Điểm quyết định có thể được triển khai bằng ứng dụng quản lý retry attempt và **republish có confirms**, hoặc thông qua cơ chế delayed retry/delivery limit **có hỗ trợ** của đúng RabbitMQ version. Nếu dùng một queue retry tự dead-letter về queue nguồn, hãy có logic chắc chắn để chuyển message tới terminal queue khi hết ngân sách, hoặc topology này **vẫn là vòng vô hạn**.

### 12.1. TTL có thể gây chậm và lệch thời gian

- TTL theo queue/message và hành vi expire phụ thuộc queue type/version.
- Message có thể không rời queue đúng từng mili giây; backlog và thứ tự có thể ảnh hưởng.
- TTL của retry queue khác **TTL của toàn nghiệp vụ**; message cũ có thể không còn hợp lệ sau nhiều lần trì hoãn.
- Khi dead-letter, broker có thể bỏ thuộc tính expiration của message và ghi vào `original-expiration` để tránh vô tình expire lặp ở queue đích.
- Retrying không được làm quá tải downstream đang gặp sự cố.

Đừng dùng hàng loạt queue TTL chỉ để có “retry 1s, 2s, 4s, 8s” mà không cân nhắc công sức vận hành, số queue, thứ tự, metric và cấu trúc DLX.

## 13. RabbitMQ tự chặn dead-letter cycle có đủ không?

RabbitMQ có cơ chế phát hiện một số vòng lặp dead-letter: khi cùng message quay lại **cùng queue** qua một dead-letter cycle mà **không có một lần rejection nào trong toàn bộ chu trình**, broker có thể **loại message** để tránh vòng lặp tự động vô tận.

Ví dụ một queue dead-letter sang default exchange rồi quay về chính nó mà không có consumer reject, broker có thể phát hiện cycle và drop. Nhưng **không được xem đây là retry budget đầy đủ**:

- Nếu có consumer reject trong vòng, điều kiện phát hiện cycle khác.
- Vòng requeue trực tiếp không phải dead-letter cycle mà cơ chế này kiểm soát.
- Đây có thể là **discard**, không phải bảo đảm mọi message vào terminal DLQ.
- Cơ chế không thay thế phân loại lỗi, backoff hay logic idempotent của ứng dụng.

Thiết kế production phải có **điểm dừng có chủ đích**, không dựa vào broker ngầm drop message khi topology vô tình tạo cycle.

## 14. Quorum queue và delivery-limit: bảo vệ riêng theo phiên bản

Quorum queues cung cấp cơ chế xử lý poison message ở tầng broker, nhưng phải đọc đúng **RabbitMQ version**.

| Phiên bản | Điều cần biết |
|---|---|
| RabbitMQ 3.13.x | Không có default delivery-limit 20 như các bản 4.x |
| RabbitMQ **4.0–4.2** | Quorum queue có default `delivery-limit=20`; counter và các thao tác return chịu semantics của nhánh đó |
| RabbitMQ **4.3+** | Delivery-limit dựa trên `delivery-count` thay vì `acquired-count`; `basic.nack(requeue=true)` không tăng `delivery-count` như trước |
| RabbitMQ **4.3+** | `x-acquired-count` theo dõi số lần được gán cho consumer; `x-delivery-count` theo dõi delivery failures theo định nghĩa của broker |

**Điểm đặc biệt quan trọng:** Trên RabbitMQ 4.3+, `basic.nack` với `requeue=true` có thể cho phép message được trả về **không giới hạn** mà **không chạm delivery-limit**, trong khi `basic.reject` đánh dấu failed delivery và được tính theo quy tắc broker tương ứng. Nếu ứng dụng đang kỳ vọng broker tự giới hạn các vòng `basic.nack`, **kiểm tra lại khi nâng cấp từ 4.2 trở xuống**.

Quorum queue 4.0+ có giới hạn 20 mặc định nhưng không nên dùng riêng con số này thay retry policy. Khi vượt delivery limit, message có thể được dead-letter nếu cấu hình DLX hoặc **bị drop** nếu không có đường xử lý. Với nhiều unacked messages bị requeue theo nhóm, cơ chế giới hạn có thể tác động tới nhiều delivery cùng lúc.

### 14.1. Cấu hình delivery-limit

Với quorum queue và broker hỗ trợ, giá trị `delivery-limit` có thể được đặt qua **policy** hoặc queue argument `x-delivery-limit`. Ví dụ về policy nên kiểm chứng theo vhost và priority:

~~~bash
rabbitmqctl set_policy --apply-to quorum_queues \
  "quorum-poison-limit" "^orders\.critical\.q$" \
  '{"delivery-limit":10}'
~~~

**Quan trọng:** cú pháp, `--apply-to` và cách đặt policy nên được kiểm tra với phiên bản `rabbitmqctl` đang chạy. Nếu CLI không hỗ trợ loại `apply-to` trong snippet của bản bạn, dùng giao diện/định dạng policy tương ứng được tài liệu version đó ghi nhận. Không tự áp dụng command vào broker production khi chưa kiểm tra hiệu lực trên queue thật.

Mặc định `20` chỉ áp dụng **quorum queues trong các version quy định**, không áp dụng như một cơ chế chung cho classic queue. Đặt `delivery-limit=-1` để tắt bảo vệ có thể phục vụ một số trường hợp tương thích ngược nhưng làm tăng nguy cơ vòng lặp vô hạn; không nên là lựa chọn mặc định.

### 14.2. Quorum delayed retry có thể thay TTL loop

Từ RabbitMQ 4.3, quorum queue hỗ trợ cơ chế delayed retry với linear backoff; tính năng này có thể giúp tránh hot requeue mà không cần topology DLX/TTL vòng lại. Cần kiểm tra đúng queue type, version và cách cấu hình delayed retry thay vì mặc định tính năng có ở mọi cluster.

Với phiên bản hỗ trợ, lựa chọn delayed retry + delivery-limit + terminal dead-letter là một hướng cần đánh giá. Vẫn phải xử lý **idempotency, lỗi dữ liệu vĩnh viễn và khả năng DLX chuyển message thành công**.

## 15. Không nhầm broker DLX với bảo đảm giao nhận tuyệt đối

Đường đi:

~~~text
work.q --(reject requeue=false)--> dead-letter exchange --> terminal DLQ
~~~

có thể thất bại nếu exchange đích không tồn tại, binding không khớp, queue đích bị lỗi hoặc cơ chế dead-letter không bảo đảm như bạn kỳ vọng. Với một số cấu hình, broker republish tới DLX theo chiến lược **at-most-once**, nên message có thể bị mất khi queue đích không nhận. Quorum queues hỗ trợ **at-least-once dead-lettering** khi cấu hình phù hợp, với điều kiện và chi phí vận hành riêng.

Vì vậy:

- DLX và DLQ phải được tạo, có binding hợp lệ, cùng virtual host và quyền phù hợp.
- Cần kiểm tra queue type và dead-letter strategy trong cluster thực tế.
- Có metric về dead-letter failures, DLQ depth/age và đường xử lý cuối.
- Bảo toàn message trong DLQ không tương đương nó đã được xử lý nghiệp vụ.
- Một terminal DLQ **không được tự động DLX về work queue** nếu chưa có quy trình replay có kiểm soát.

Nếu dùng `RepublishMessageRecoverer`, publisher confirms của bản republish cần được thiết kế thích hợp. Đừng ack message nguồn dựa trên lời gọi publish không xác nhận nếu mục tiêu là độ bền cao.

## 16. Quản lý replay từ DLQ mà không tạo lại vòng lặp

DLQ là nơi để **điều tra và quyết định**, không nên mặc định là queue “tự động thử lại đến khi được”.

Quy trình replay an toàn:

1. Xem message ID, schema version, reason, lịch sử `x-death`, thời gian lưu và nguyên nhân gốc.
2. Phân loại: payload không hợp lệ, bug đã được sửa, phụ thuộc tạm thời đã phục hồi, hoặc message quá cũ để xử lý.
3. Bảo đảm listener code/config đã được sửa trước khi replay message poison.
4. Phân biệt **logical event ID** và lần publish mới; giữ event ID để chống xử lý trùng, có thể gắn `replay-id`/audit metadata riêng.
5. Replay theo lô nhỏ với rate limit, publisher confirms/returns và metrics; không dump toàn bộ DLQ vào queue chính.
6. Theo dõi kết quả end-to-end; nếu message vẫn lỗi, đưa vào quarantine khác hoặc dừng replay theo budget.

### Ví dụ hợp đồng replay

~~~json
{
  "eventId": "evt-105",
  "schemaVersion": 2,
  "replayId": "incident-2026-11-26-batch-01",
  "retryAttempt": 1
}
~~~

Đây là **hợp đồng ứng dụng minh họa**, không phải header broker bắt buộc. `retryAttempt` trong body/header ứng dụng phải có semantics cụ thể và không được dùng thay `x-death` mà không thỏa thuận; `replayId` là ID của đợt replay, còn `eventId` là ID logic dùng cho idempotency.

**Không nên chỉnh `x-death` bằng tay trong công cụ replay** để làm “message trông như chưa từng lỗi”. Lịch sử do broker quản lý phải được quan sát như dữ liệu nguồn, và ứng dụng có thể lưu audit retry riêng để tính toán ngân sách xử lý.

## 17. Manual ack và xử lý lỗi an toàn

Với `AcknowledgeMode.MANUAL`, listener nắm quyền chọn settlement:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(
    queues = "lab.poison.work.q",
    containerFactory = "manualPoisonListenerFactory")
public void receive(Message message, Channel channel) throws IOException {
    long tag = message.getMessageProperties().getDeliveryTag();

    try {
        // Xử lý nghiệp vụ đồng bộ và idempotent.
        handleMessage(message);
        channel.basicAck(tag, false);
    } catch (InvalidPayloadException ex) {
        // Không thử lại cùng payload vô hạn.
        channel.basicReject(tag, false);
    } catch (TemporaryDependencyException ex) {
        // Đây chỉ là minh họa: KHÔNG requeue=true liên tục trong production.
        channel.basicNack(tag, false, true);
    }
}
~~~

`handleMessage`, `InvalidPayloadException` và `TemporaryDependencyException` là **thành phần ứng dụng minh họa**. Factory `manualPoisonListenerFactory` phải được tạo với `AcknowledgeMode.MANUAL` nếu sử dụng code trên; không đặt cùng listener chạy bằng factory AUTO rồi tự ack/nack để tránh settlement trùng.

Các quy tắc sống còn:

- Delivery tag chỉ hợp lệ trên **channel đã giao message**. Ack/nack trên channel khác có thể gây `PRECONDITION_FAILED`.
- Một delivery chỉ được settlement **một lần**. Gửi ack rồi lại nack cùng tag không hợp lệ.
- Với `requeue=true` trực tiếp, phải có **budget/backoff bên ngoài**, không dùng mã trên nguyên xi cho tải production.
- Nếu exception ngoài các nhánh catch thoát ra, phải hiểu chiến lược error handling/manual ack thực tế để không để `unacked` kẹt mãi.
- Mất connection trước ack khiến trạng thái delivery có thể không rõ; broker có thể redeliver dù business side effect đã hoàn tất.

## 18. Giao dịch và idempotency: chặn lỗi xử lý hai lần

Poison message không chỉ gây tải cao, mà việc consumer redelivery có thể tạo **side effect trùng**:

~~~text
T1: Consumer nhận eventId=evt-300
T2: Ghi database thành công
T3: Connection RabbitMQ đứt trước basicAck
T4: Broker giao lại evt-300
T5: Consumer thử ghi database lần thứ hai
~~~

Nếu handler không idempotent, dữ liệu có thể bị tạo trùng hoặc thanh toán bị thực thi hai lần. Một kỹ thuật phổ biến:

1. Message có `eventId` duy nhất và ổn định do producer tạo.
2. Trong **cùng transaction database** với side effect, lưu record `processed_event(event_id)` có unique constraint.
3. Nếu event ID đã xử lý, chỉ xác nhận delivery mà **không** thực hiện tác động nghiệp vụ lần nữa.
4. Khi transaction database commit, consumer ack RabbitMQ; nếu ack mất, redelivery vẫn an toàn do unique key.

Đây là thiết kế **at-least-once + idempotency**, không phải cam kết exactly-once toàn hệ thống. Một transaction RabbitMQ và một transaction JDBC **không tự trở thành** giao dịch phân tán atomic. Với publisher, transactional outbox có thể giúp đảm bảo ý định phát message không mất khi database commit nhưng broker chưa nhận.

## 19. Quan sát poison-message loop trong production

Nhìn queue depth riêng lẻ là chưa đủ. Một dashboard nên theo dõi:

| Chỉ số | Hỏi điều gì? | Dấu hiệu bất thường |
|---|---|---|
| Delivery/redelivery rate | Message có đang được giao lại quá nhanh không? | Redelivery tăng cao, business throughput không tăng |
| Listener exception rate theo loại | Lỗi schema hay downstream? | Một loại exception lặp trên cùng event ID |
| Queue `messages_ready` | Bao nhiêu message chưa giao? | Tăng liên tục hoặc dao động cao |
| Queue `messages_unacknowledged` | Bao nhiêu delivery đang chờ ack? | Bão hòa prefetch, listener treo hoặc thiếu ack |
| DLQ depth và oldest age | Có message cần can thiệp? | DLQ tăng, lâu không xử lý |
| `x-death` reason/queue được tổng hợp | Message rời queue vì nguyên nhân gì? | Cùng cặp `work.q/rejected` tăng bất thường |
| Retry attempted/exhausted | Budget có đang hết quá nhanh không? | Nhiều message tới terminal queue |
| Broker memory/disk alarms | Broker có bị quá tải không? | Publish/consume bị chậm hoặc blocked |
| Downstream latency/error rate | Database/API có đang lỗi không? | Retry làm tình hình tệ thêm |

Log tối thiểu nên gắn `eventId`, source queue, routing key, exception category, retry attempt **do ứng dụng quản lý**, `x-death` được tóm tắt nếu có, correlation ID và quyết định `ack/requeue/dead-letter`. Không log toàn bộ payload chứa dữ liệu nhạy cảm.

### Ba mẫu triệu chứng dễ nhầm

**A. Hot requeue:** queue depth không lớn, redelivery rate cực cao, CPU/log tăng. Kiểm tra `defaultRequeueRejected`, exception kiểu `ImmediateRequeueAmqpException`, manual `basicNack(true)` và broker quorum count semantics.

**B. DLX retry cycle:** không thấy hot loop ngay vì có TTL, nhưng `x-death` cho `work.q/rejected` và `retry.q/expired` tăng qua thời gian. Xác minh có terminal budget.

**C. Discard có chủ đích:** message fatal đã có `x-death` bị `ConditionalRejectingErrorHandler` discard; DLQ không tăng thêm dù listener báo fatal. Kiểm tra `discardFatalsWithXDeath`, queue type và log error handler.

## 20. Bài thực hành: cố ý tạo lỗi nhưng có điểm dừng

**Chỉ chạy trong môi trường RabbitMQ test** có queue, exchange và vhost riêng. Không cố tạo hot loop trên broker production hoặc queue dùng chung.

### Bước A — Kiểm tra reject vào terminal DLQ

1. Dùng topology ở mục 10, `defaultRequeueRejected=false`, listener `AcknowledgeMode.AUTO`.
2. Publish `OK:1001` và `INVALID:1002`.
3. Đợi `OK:1001` xử lý xong; xác nhận nó không vào DLQ.
4. Với `INVALID:1002`, kiểm tra `lab.poison.dlq` nhận message và `x-death` có cặp `lab.poison.work.q/rejected`.
5. Đọc `x-death.count` cho cặp tương ứng, **không xem đó là tổng số listener attempts**.

### Bước B — Thử một lỗi transient với retry hữu hạn

1. Thêm retry advice ở mục 11 cho một listener test riêng.
2. Tạo handler mô phỏng lỗi tạm thời đúng số lần, sau đó thành công; dùng bộ đếm thread-safe/latch.
3. Xác minh số lần gọi handler theo cấu hình, không suy từ `x-death`.
4. Thử tiếp lỗi không bao giờ hết; sau khi budget cạn, xác minh DLQ nhận message.
5. Kiểm tra broker không giao lại liên tục sau terminal reject.

### Bước C — Chứng minh x-death không đếm requeue=true

1. Tạo một listener test manual ack, cho phép **tối đa hai** lần nhận một message có ID riêng.
2. Sau lần đầu, `basicNack(tag,false,true)` rồi ghi lại `redelivered` và headers.
3. Lần hai, `basicReject(tag,false)` để **dừng**, không tạo vòng vô hạn.
4. Đối chiếu: `x-death` không tăng chỉ vì bước nack requeue; khi message dead-letter, lịch sử mới xuất hiện ở DLQ.
5. Với quorum queue, ghi **version RabbitMQ** và kiểm tra thêm `x-delivery-count`/`x-acquired-count` theo version.

### Bước D — TTL vòng lại và discard fatal

Chỉ tạo topology retry TTL trong môi trường test có giám sát và cơ chế **dừng vòng**. Cho một message JSON lỗi quay từ retry queue về work queue rồi ghi lại:

- `x-death` có record `rejected` và `expired` phù hợp hay không.
- Error handler nhận diện lỗi fatal trước listener như thế nào.
- Message bị discard bởi `discardFatalsWithXDeath` hay đi tới terminal quarantine.
- Có rủi ro mất message cần điều tra khi dùng default discard hay không.

**Không để TTL queue tự quay về work mãi mà không có kiểm soát**. Nếu cần test hàng chục vòng, hãy mock phần đếm hoặc dùng replay scheduler có budget, không đốt tài nguyên broker.

### Bước E — Quorum queue trên các version khác nhau

Nếu có hai broker test ở RabbitMQ 4.2 và 4.3+, dùng cùng một message lỗi và thử có giới hạn:

1. `basic.reject(requeue=true)`.
2. `basic.nack(requeue=true)`.
3. Ngắt connection khi có unacked delivery.

Ghi lại ảnh hưởng tới `x-delivery-count`, `x-acquired-count` (nếu có) và delivery-limit. Không suy hai lệnh reject/nack có semantics đếm giống nhau ở mọi bản.

## 21. Ma trận test tối thiểu

| Kịch bản | Hành vi mong đợi | Bằng chứng |
|---|---|---|
| Message xử lý thành công | Ack, không vào DLQ | Business outcome và queue |
| JSON hỏng, chưa có `x-death` | Fatal conversion được reject không requeue theo error handler | Container logs, DLQ nếu có |
| JSON hỏng đã có `x-death` | Có thể discard khi `discardFatalsWithXDeath=true` | Error-handler logs, không mặc định DLQ tăng |
| Exception transient với retry hữu hạn | Thử theo budget/backoff rồi thành công hoặc terminal | Counter business attempts, elapsed time |
| `basicNack(requeue=true)` | Message có thể redeliver | Redelivered flag; không giả định `x-death` tăng |
| Work → retry TTL → work | Mỗi dead-letter có lịch sử queue/reason | `x-death` cặp `rejected`/`expired` |
| Quorum delivery-limit | Drop hoặc DLX khi broker xác định vượt limit | Broker version, count semantics, terminal queue |
| DLX thiếu binding | Message không tới terminal queue | Kiểm tra topology/permissions, broker logs |
| Retry worker restart | Có thể redeliver message chưa ack | Event ID idempotency |
| Manual ack hai lần | Có thể đóng channel với unknown delivery tag | Channel log/exception |

Hãy đợi kết quả bất đồng bộ bằng latch/await thay vì assert ngay sau publish. Khi test DLQ, dùng queue test sạch và xác nhận có duy nhất listener test đang tiêu thụ để không bị cạnh tranh consumer làm sai kết quả.

## 22. Bài tập tự kiểm tra

### Bài 1 — x-death có đếm requeue?

Một message bị `basic.nack(requeue=true)` 100 lần trên classic queue, chưa từng qua DLX. Có bắt buộc `x-death.count = 100`?

**Đáp án:** không. Requeue trực tiếp không phải dead-letter; message có thể chưa có `x-death`.

### Bài 2 — Gộp lịch sử

Một message qua `work.q/rejected` 3 lần và `retry.q/expired` 3 lần. `x-death` nhất thiết có sáu phần tử?

**Đáp án:** không. RabbitMQ gộp theo `{queue, reason}`; thường có hai phần tử với `count=3` mỗi cặp.

### Bài 3 — Tại sao x-death[0].count không phải attempt?

Message có `x-death[0]` là `retry.q/expired` với count 2, và `x-death[1]` là `work.q/rejected` với count 2. Vì sao lấy `x-death[0].count` làm số lần xử lý là không an toàn?

**Gợi ý:** phần tử đầu mô tả một cặp queue/reason, không phải tổng business invocations; requeue/republish khác không được bao phủ.

### Bài 4 — Fatal đã có x-death

Sau retry TTL, message JSON lỗi quay về work queue và vẫn gây converter fatal. Vì sao Spring AMQP có thể discard nó mà không dead-letter thêm?

**Đáp án:** `ConditionalRejectingErrorHandler` với `discardFatalsWithXDeath=true` có thể log và discard fatal message có x-death để cắt vòng.

### Bài 5 — Lỗi database tạm thời

Database down trong 5 phút. Nên liên tục ném `ImmediateRequeueAmqpException` hay dùng backoff và giới hạn?

**Đáp án:** cần retry có backoff, giới hạn attempts, circuit breaker và terminal handling; immediate requeue có thể gây hot loop.

### Bài 6 — Quorum RabbitMQ 4.3

Ứng dụng dùng `basic.nack(requeue=true)` trên quorum queue RabbitMQ 4.3 và kỳ vọng default delivery-limit 20 tự chặn mọi vòng. Vì sao kỳ vọng này sai?

**Đáp án:** từ 4.3, `basic.nack` requeue không tăng `delivery-count` như trước, nên có thể lặp mà không chạm delivery-limit. Cần chiến lược retry rõ ràng và kiểm tra thay đổi semantics.

### Bài 7 — DLQ là tuyến cuối hay retry?

Một queue gọi là `orders.dlq` có TTL và dead-letter về `orders.work.q`. Đây có phải terminal quarantine?

**Đáp án:** không; đó là một retry loop theo thời gian. Terminal DLQ cần không tự động quay về work khi chưa có quyết định replay.

### Bài 8 — Republish recoverer

Vì sao `RepublishMessageRecoverer` có thể khiến DLQ của `x-dead-letter-exchange` trên queue nguồn trống dù listener lỗi?

**Đáp án:** recoverer có thể phát message mới tới exchange lỗi rồi return, sau đó container ack delivery nguồn. Đây không phải reject/DLX do broker.

### Bài 9 — Chống trùng

Consumer commit database thành công, nhưng mất kết nối trước ack. Message redeliver. `x-death` có đủ để tránh ghi trùng không?

**Đáp án:** không. Dùng event ID duy nhất và idempotency trong transaction database; `x-death` chỉ ghi lịch sử dead-letter.

## 23. Checklist trước khi đưa vào production

- [ ] Phân loại lỗi **permanent, transient, unknown outcome**; không retry mọi exception giống nhau.
- [ ] Kiểm tra `AcknowledgeMode`, `defaultRequeueRejected` và effective listener container factory.
- [ ] Không dùng `requeue=true` vô hạn làm retry strategy.
- [ ] Nếu dùng Spring Retry, cấu hình retry budget/backoff/recoverer và cách đếm attempts đúng phiên bản.
- [ ] Tách **retry queue có TTL** khỏi **terminal DLQ**; tránh vòng DLX vô hạn.
- [ ] Đọc `x-death` theo `queue + reason + count`, không dùng `x-death[0]` làm tổng retry count.
- [ ] Không tự ghi/đặt lại `x-death` từ producer để đánh lừa broker.
- [ ] Kiểm tra `ConditionalRejectingErrorHandler`, `discardFatalsWithXDeath` và fatal exceptions theo Spring AMQP version.
- [ ] Xác minh từ RabbitMQ version và queue type các semantics `x-delivery-count`, `x-acquired-count`, delivery-limit và nack/reject.
- [ ] Với quorum queue RabbitMQ 4.3+, không kỳ vọng `basic.nack(requeue=true)` tự làm tăng delivery-count.
- [ ] Khai báo và kiểm thử DLX/queue/binding/permissions, giám sát dead-letter failures.
- [ ] Không coi DLX/queue durable đồng nghĩa chuyển dead-letter luôn đảm bảo at-least-once; kiểm tra strategy tương ứng.
- [ ] Chỉ replay DLQ có chọn lọc, với eventId ổn định, rate limit và audit.
- [ ] Consumer xử lý idempotent và có timeout cho downstream; không ack trước khi side effect quan trọng hoàn tất.
- [ ] Giám sát redelivery rate, retry attempts/exhausted, DLQ depth/age, queue ready/unacked và exception types.
- [ ] Test với RabbitMQ thật: JSON lỗi, DB down, network loss, TTL cycle, broker restart, manual ack và thay đổi version.
- [ ] Đảm bảo không có message poison nào có thể kéo hệ thống vào vòng xử lý không dừng mà không có cảnh báo.

## 24. Tài liệu tham khảo chính thức

Những hành vi `x-death`, delivery-limit và error handler có thể thay đổi theo **RabbitMQ/Spring AMQP version**. Luôn đối chiếu với phiên bản được triển khai:

- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): các nguyên nhân dead-letter, `x-death`, gộp lịch sử, cycle detection và độ an toàn của republish.
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues): poison message handling, `delivery-limit`, `x-delivery-count`, `x-acquired-count` và khác biệt 4.3.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): `basic.ack`, `basic.reject`, `basic.nack`, redelivery và giao dịch.
- [RabbitMQ — Time-To-Live](https://www.rabbitmq.com/docs/ttl): message TTL, expired messages và retry queue.
- [RabbitMQ — Policies](https://www.rabbitmq.com/docs/parameters): cấu hình DLX và queue policies.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): `ConditionalRejectingErrorHandler`, fatal conversion, `discardFatalsWithXDeath`.
- [Spring AMQP 3.2 — Resilience / Recovering from Errors](https://docs.spring.io/spring-amqp/reference/3.2/amqp/resilience-recovering-from-errors-and-broker-failures.html): `RetryInterceptorBuilder`, `RejectAndDontRequeueRecoverer`, `RepublishMessageRecoverer`.
- [Spring AMQP — Listener Container Attributes](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): ack mode, `defaultRequeueRejected`, error handler và prefetch.

**Ghi nhớ:** `x-death` là **lịch sử message bị dead-letter**, không phải đồng hồ đếm mọi lần retry. `requeue=true` có thể tạo hot loop mà không tăng `x-death`; DLX/TTL có thể tạo vòng quay chậm nhưng vẫn vô hạn; republish thủ công có semantics riêng. Hãy sử dụng **retry hữu hạn, backoff, terminal DLQ, error handler có kiểm chứng và consumer idempotent**, đồng thời chú ý khác biệt quorum queue giữa RabbitMQ 4.2 và 4.3+, để một poison message không biến thành sự cố toàn hệ thống Spring AMQP.
