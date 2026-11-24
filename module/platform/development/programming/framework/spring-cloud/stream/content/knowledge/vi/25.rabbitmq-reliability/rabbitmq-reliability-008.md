# Tương tác giữa maxAttempts, requeueRejected và republishToDlq

Khi một message không xử lý được trong Spring Cloud Stream RabbitMQ Binder, ứng dụng có thể thử lại trong listener, yêu cầu RabbitMQ đưa message về queue, hoặc chuyển message sang Dead Letter Queue (DLQ). Ba thuộc tính maxAttempts, requeueRejected và republishToDlq điều khiển các phần khác nhau của quá trình này. Hiểu đúng thứ tự áp dụng của chúng giúp tránh vòng lặp vô hạn, message bị loại bỏ ngoài ý muốn và DLQ không nhận được dữ liệu lỗi.

maxAttempts giới hạn số lần Spring Cloud Stream gọi lại handler trong cơ chế retry nội bộ. requeueRejected quyết định broker có đưa một delivery bị reject trở lại queue hay không khi retry nội bộ đã tắt hoặc khi binder không republish message vào DLQ. republishToDlq quyết định binder tự publish message thất bại sang DLQ kèm metadata lỗi hay để RabbitMQ thực hiện dead-lettering sau khi message bị reject.

## 1. Ba thuộc tính thuộc ba giai đoạn khác nhau

| Thuộc tính | Phạm vi | Câu hỏi nó trả lời |
|---|---|---|
| maxAttempts | Retry nội bộ của Spring Cloud Stream | Handler được gọi tối đa bao nhiêu lần cho một lần delivery? |
| republishToDlq | Cách binder xử lý message sau khi retry thất bại | Binder có tự publish message lỗi sang DLQ và thêm header lỗi không? |
| requeueRejected | Cách listener từ chối delivery cuối cùng | RabbitMQ có đưa delivery trở lại queue gốc không? |

Một message có thể trải qua nhiều lần gọi handler bên trong cùng một delivery. Nếu lần thử cuối vẫn ném exception, binder/listener container mới quyết định republish, reject hoặc requeue theo cấu hình. Vì vậy, maxAttempts không phải tổng số lần RabbitMQ có thể giao message trong toàn bộ vòng đời của nó.

## 2. Luồng xử lý tổng quát

~~~mermaid
flowchart TD
    A["RabbitMQ giao message"] --> B["Spring Cloud Stream gọi handler"]
    B -->|Thành công| C["ACK delivery"]
    B -->|Ném exception| D{"Còn lượt maxAttempts?"}
    D -->|Có| E["Backoff theo RetryTemplate"]
    E --> B
    D -->|Hết lượt hoặc maxAttempts = 1| F{"republishToDlq?"}
    F -->|true và DLQ được cấu hình| G["Binder publish sang DLQ kèm header lỗi"]
    G --> H["Xác nhận publish rồi hoàn tất delivery gốc"]
    F -->|false| I{"requeueRejected?"}
    I -->|true| J["RabbitMQ requeue vào queue gốc"]
    J --> A
    I -->|false| K["Reject không requeue"]
    K --> L{"Queue có DLX?"}
    L -->|Có| M["RabbitMQ dead-letter sang DLQ"]
    L -->|Không| N["Message bị loại khỏi queue"]
~~~

Sơ đồ mô tả đường đi phổ biến của imperative message handler. Các exception đặc biệt, transaction, publisher confirm và cấu hình DLQ của broker có thể thay đổi hành vi cuối; các phần sau giải thích từng trường hợp.

## 3. maxAttempts: số lần gọi handler

maxAttempts là số lần thử xử lý một message, tính cả lần đầu tiên. Giá trị mặc định của consumer property trong Spring Cloud Stream là 3. Đặt maxAttempts bằng 1 sẽ tắt retry nội bộ.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
~~~

Với cấu hình này, handler được gọi tối đa bốn lần cho một delivery: lần đầu và ba lần retry. Các khoảng chờ dự kiến là 1 giây, 2 giây và 4 giây. Nếu có thêm lần retry, khoảng chờ tăng theo multiplier nhưng không vượt quá back-off-max-interval.

| Thuộc tính | Ý nghĩa | Mặc định |
|---|---|---:|
| max-attempts | Tổng số lần xử lý, bao gồm lần đầu | 3 |
| back-off-initial-interval | Thời gian chờ trước retry đầu tiên, ms | 1000 |
| back-off-max-interval | Giới hạn trên của khoảng chờ, ms | 10000 |
| back-off-multiplier | Hệ số tăng khoảng chờ | 2.0 |
| default-retryable | Có retry exception không được liệt kê hay không | true |

Retry nội bộ giữ listener thread trong thời gian backoff. Với một consumer có concurrency thấp hoặc yêu cầu thứ tự nghiêm ngặt, điều này có thể làm các message khác phải chờ. Nếu lỗi là mất kết nối hoặc dịch vụ phụ thuộc đang gián đoạn trong thời gian dài, retry ngay trong listener có thể giữ delivery quá lâu.

### 3.1. Chỉ retry loại lỗi phù hợp

Không phải lỗi nào cũng có thể khắc phục bằng cách thử lại. Timeout hoặc lỗi kết nối tạm thời có thể phục hồi; lỗi schema, thiếu trường bắt buộc hoặc vi phạm quy tắc nghiệp vụ thường không thay đổi khi gọi lại cùng dữ liệu.

Có thể cấu hình retryable-exceptions để phân loại:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            max-attempts: 4
            default-retryable: false
            retryable-exceptions:
              java.net.SocketTimeoutException: true
              org.springframework.dao.TransientDataAccessException: true
              java.lang.IllegalArgumentException: false
~~~

Tên exception trong map là tên lớp đầy đủ. Hãy xác minh kiểu exception thực tế được ném ra hoặc được bọc bởi framework. Nếu default-retryable là false, chỉ các lớp được đánh dấu true mới được retry; các lớp đánh dấu false sẽ không được retry.

Không retry một thao tác có side effect không idempotent nếu lần thử trước có thể đã thực hiện một phần công việc. Ví dụ, thanh toán hoặc tạo bản ghi bên ngoài có thể đã thành công trước khi kết nối bị timeout. Cần idempotency key, unique constraint hoặc cơ chế deduplication.

## 4. requeueRejected: đưa delivery về queue gốc

requeueRejected là thuộc tính Rabbit consumer. Khi được đặt true, delivery bị reject có thể được RabbitMQ đưa lại vào queue ban đầu. Khi đặt false, delivery bị reject không được requeue; nếu queue có Dead Letter Exchange (DLX), RabbitMQ có thể chuyển message sang DLQ. Nếu không có DLX, message bị loại khỏi queue.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            max-attempts: 1
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              requeue-rejected: true
~~~

Ở đây retry nội bộ bị tắt. Khi handler ném exception, message bị reject và RabbitMQ đưa lại vào queue gốc. Message có thể được giao ngay cho consumer hiện tại hoặc consumer khác.

requeueRejected không tạo khoảng chờ. Vì vậy, nếu lỗi vẫn tồn tại, message có thể đi qua vòng lặp rất nhanh:

1. Consumer nhận message.
2. Handler ném exception.
3. RabbitMQ requeue message.
4. Consumer nhận lại message gần như ngay lập tức.
5. Chu trình tiếp tục.

Vòng lặp này tiêu thụ CPU, network và tài nguyên broker; nó cũng có thể khiến queue liên tục xử lý một poison message và làm các message khác bị đói. Chỉ dùng requeue trực tiếp khi lỗi rất ngắn hạn và có cơ chế kiểm soát rõ ràng.

### 4.1. Phân biệt retry nội bộ và requeue của broker

| Đặc điểm | Retry nội bộ maxAttempts | Requeue bằng requeueRejected |
|---|---|---|
| Nơi thực hiện | Spring Retry / listener | RabbitMQ broker |
| Đếm lần thử | maxAttempts tính cả lần đầu | Không tăng maxAttempts trong cùng một vòng retry nội bộ |
| Backoff | Có thể cấu hình bằng các back-off property | Không có delay do requeueRejected |
| Delivery mới từ broker | Chưa cần cho từng lần retry nội bộ | Có redelivery từ queue |
| Có thể lặp vô hạn? | Có giới hạn theo maxAttempts | Có thể lặp liên tục nếu lỗi tiếp diễn |

Ví dụ maxAttempts=3 và requeueRejected=true: Spring gọi handler tối đa ba lần trong delivery hiện tại. Nếu cả ba lần đều lỗi, delivery cuối có thể bị requeue. Khi RabbitMQ giao lại, một chu kỳ maxAttempts mới bắt đầu. Tổng số lần gọi handler trong toàn bộ vòng đời message do đó có thể không giới hạn.

## 5. republishToDlq: binder tự publish message lỗi

republishToDlq điều khiển cách Rabbit binder chuyển message thất bại sang DLQ. Khi bật, binder dùng publisher để gửi lại message tới dead-letter destination và bổ sung thông tin lỗi vào headers, thường gồm exception message và stack trace.

Một số header hữu ích:

| Header | Nội dung |
|---|---|
| x-exception-message | Thông báo của exception cuối cùng |
| x-exception-stacktrace | Stack trace của nguyên nhân lỗi |
| x-original-exchange | Exchange ban đầu |
| x-original-routingKey | Routing key ban đầu |

Các header cụ thể có thể phụ thuộc phiên bản binder. Stack trace dài có thể vượt giới hạn frame_max của RabbitMQ; frameMaxHeadroom dành chỗ cho các header khác và binder có thể cắt ngắn stack trace nếu không đủ chỗ.

republishToDlq cho phép đưa message sang DLQ ngay cả khi maxAttempts=1. Vì vậy, bật thuộc tính này không đồng nghĩa phải bật retry nội bộ.

Để binder tự tạo DLQ và DLX, cần bật autoBindDlq. Chỉ đặt republishToDlq mà không có topology DLQ hợp lệ không thay thế việc khai báo queue/exchange đích.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 4
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              requeue-rejected: false
~~~

Khi bốn lần xử lý đều thất bại, binder publish message sang DLQ cùng metadata lỗi. Message gốc được hoàn tất theo đường xử lý republish; nó không bị đưa trở lại queue gốc bằng requeueRejected.

### 5.1. republishToDlq khác broker dead-lettering

Hai cơ chế có cùng đích DLQ nhưng đường đi khác nhau:

| Đặc điểm | republishToDlq=true | republishToDlq=false |
|---|---|---|
| Ai chuyển message? | Binder publish một message mới đến DLQ | Binder reject delivery; RabbitMQ áp dụng DLX |
| Header lỗi | Binder có thể thêm exception message và stack trace | RabbitMQ thêm metadata dead-letter như x-death |
| Message gốc | Được xử lý qua đường publish DLQ của binder | Được broker dead-letter theo cấu hình queue |
| requeueRejected | Không phải lựa chọn chính khi binder republish thành công | Quyết định delivery có quay về queue gốc hay không |
| Phụ thuộc topology | Cần DLQ đích mà binder có thể publish tới | Queue gốc cần DLX/routing hợp lệ |

Broker dead-lettering giữ message theo cơ chế định tuyến của RabbitMQ. Header x-death ghi nhận lý do, queue, exchange, routing key và số lần message bị dead-letter. republishToDlq hữu ích khi đội vận hành cần exception và stack trace trực tiếp trên message lỗi.

## 6. Kết hợp ba thuộc tính theo từng chiến lược

### 6.1. Retry có giới hạn rồi chuyển vào DLQ bằng binder

Đây là lựa chọn phổ biến khi muốn giữ lại stack trace và thông tin exception:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 4
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

Kết quả: tối đa bốn lần gọi handler trong một delivery. Khi hết lượt, binder republish message sang DLQ và đính kèm thông tin exception. requeueRejected được đặt false để thể hiện rõ ý định không đưa message lỗi quay lại queue gốc.

### 6.2. Retry có giới hạn rồi để RabbitMQ dead-letter

Nếu muốn broker thực hiện dead-lettering và giữ metadata x-death:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 4
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: false
              requeue-rejected: false
~~~

Khi retry nội bộ hết lượt, binder reject message không requeue. RabbitMQ dùng DLX được gắn với queue để chuyển message sang DLQ. Nếu DLX hoặc routing key không đúng, message có thể bị loại bỏ; cần kiểm tra topology trước khi triển khai.

### 6.3. Không retry nội bộ, đưa lỗi thẳng vào DLQ

Khi lỗi dữ liệu không thể khắc phục bằng retry:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            max-attempts: 1
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              requeue-rejected: false
~~~

Handler được gọi một lần. Nếu ném exception, binder republish message sang DLQ. Chiến lược này tránh lặp lại các lỗi schema hoặc validation chắc chắn không tự phục hồi.

### 6.4. Requeue ngay khi lỗi

Chỉ dùng khi lỗi có thể biến mất rất nhanh, ví dụ một tài nguyên tạm thời vừa khởi động lại:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            max-attempts: 1
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              republish-to-dlq: false
              requeue-rejected: true
~~~

Message được requeue vào queue gốc và có thể được giao lại ngay. Cấu hình này không có backoff, không giới hạn số vòng requeue và không tự chuyển poison message sang DLQ. Trước khi dùng, cần có cơ chế giám sát và điều kiện dừng vòng lặp.

## 7. Bảng quyết định theo cấu hình

| maxAttempts | republishToDlq | requeueRejected | Hành vi mong đợi khi handler cuối cùng vẫn lỗi |
|---:|---|---|---|
| Lớn hơn 1 | true | false | Retry nội bộ; sau cùng binder publish sang DLQ |
| Lớn hơn 1 | false | false | Retry nội bộ; sau cùng reject không requeue để broker dead-letter nếu có DLX |
| 1 | true | false | Một lần xử lý; binder publish sang DLQ |
| 1 | false | false | Một lần xử lý; reject không requeue; broker dead-letter nếu có DLX |
| 1 | false | true | Một lần xử lý cho mỗi delivery; RabbitMQ requeue, có thể lặp liên tục |
| Lớn hơn 1 | false | true | Retry nội bộ trước; sau cùng requeue, bắt đầu một chu kỳ delivery mới |

Bảng giả định có topology DLQ/DLX hợp lệ khi cần dead-letter. Nếu không có DLQ hoặc DLX, reject không requeue có thể làm message biến mất khỏi queue mà không có nơi lưu giữ.

Trong tài liệu Rabbit binder hiện hành, republishToDlq được mô tả với mặc định true; các tài liệu/release cũ từng ghi mặc định false. requeueRejected mặc định false và autoBindDlq mặc định false. Vì mặc định đã thay đổi giữa các thế hệ tài liệu, hãy khai báo tường minh cả ba thuộc tính trong ứng dụng và đối chiếu đúng phiên bản Spring Cloud Stream BOM đang dùng.

## 8. DLQ cần được cấu hình như thế nào?

autoBindDlq yêu cầu binder khai báo DLQ, dead-letter exchange và binding tương ứng. Tên DLQ mặc định thường được tạo từ destination với hậu tố .dlq; có thể tùy chỉnh bằng deadLetterQueueName. DLX và dead-letter routing key cũng có thuộc tính riêng.

Ví dụ tùy chỉnh tên DLQ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              dead-letter-queue-name: orders.submitted.order-service.dlq
              republish-to-dlq: true
              requeue-rejected: false
~~~

Tên thực tế và phạm vi queue có thể phụ thuộc prefix, destination, group, partition và phiên bản binder. Hãy kiểm tra queue được tạo trong RabbitMQ Management UI hoặc bằng rabbitmqctl thay vì giả định tên.

Nếu hạ tầng đã tạo DLX/DLQ bằng Terraform, Helm hoặc quy trình quản trị riêng, có thể dùng cấu hình topology có sẵn và tắt khai báo tương ứng của binder. Khi đó cần bảo đảm exchange, queue và binding routing key đã được tạo đúng; binder không thể tự sửa topology bên ngoài nếu đã tắt provisioning.

## 9. Broker dead-lettering và header x-death

Khi message bị reject với requeue=false và queue có DLX, RabbitMQ chuyển message sang dead-letter exchange. Với AMQP 0-9-1, broker ghi lịch sử vào header x-death. Header này là một danh sách các mục; mỗi mục chứa thông tin như:

- queue: tên queue đã dead-letter message.
- reason: lý do, chẳng hạn rejected, expired hoặc maxlen.
- count: số lần dead-letter theo cặp queue/reason.
- exchange: exchange gốc tại thời điểm dead-letter.
- routing-keys: routing key liên quan.
- time: thời điểm dead-letter.

count trong x-death thường được biểu diễn dưới dạng số nguyên dài. Không nên ép kiểu tùy tiện hoặc giả định header chỉ chứa một mục.

Ví dụ đọc header trong Consumer:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderSubmitted>> inspectDeadLetterHistory() {
    return message -> {
        Object raw = message.getHeaders().get("x-death");
        if (raw instanceof List<?> deaths) {
            for (Object item : deaths) {
                if (item instanceof Map<?, ?> death) {
                    Object queue = death.get("queue");
                    Object reason = death.get("reason");
                    Object count = death.get("count");
                    System.out.printf(
                        "queue=%s reason=%s count=%s%n",
                        queue, reason, count
                    );
                }
            }
        }
    };
}
~~~

Đoạn code minh họa cách đọc dữ liệu header; trong ứng dụng thật, cần kiểm tra header mapping và kiểu dữ liệu sau khi message đi qua binder. OrderSubmitted là kiểu payload nghiệp vụ của ví dụ và cần được khai báo trong ứng dụng.

x-death chỉ được RabbitMQ bổ sung khi broker thực hiện dead-lettering. Nếu binder tự republish với republishToDlq=true, message có thêm metadata exception do binder tạo; không nên coi x-death là bộ đếm duy nhất cho mọi loại retry.

## 10. Ngoại lệ đặc biệt có thể bỏ qua DLQ

Spring AMQP có một số exception điều khiển hành vi acknowledge/requeue:

| Exception | Hành vi |
|---|---|
| AmqpRejectAndDontRequeueException | Reject delivery và không requeue; broker có thể dead-letter nếu queue có DLX |
| ImmediateRequeueAmqpException | Yêu cầu requeue delivery |
| ImmediateAcknowledgeAmqpException | Acknowledge message ngay, bỏ qua DLQ và loại message khỏi queue |

ImmediateAcknowledgeAmqpException có thể được dùng khi ứng dụng quyết định message cần bị bỏ qua có chủ đích. Không dùng nó cho lỗi nghiệp vụ cần điều tra vì message sẽ không đi vào DLQ.

Nếu handler ném AmqpRejectAndDontRequeueException, nó thể hiện rõ ý định không requeue ngay cả khi cấu hình chung có thể khác. Nếu ném ImmediateRequeueAmqpException, message có thể quay lại queue và lặp. Chỉ dùng các exception này khi hiểu rõ tác động với maxAttempts và cấu hình binder.

## 11. Retry có độ trễ bằng DLQ và TTL

Retry nội bộ giữ listener thread trong thời gian backoff. Một lựa chọn khác là dead-letter message sang queue trung gian có TTL, sau đó để RabbitMQ dead-letter trở lại queue chính khi TTL hết hạn.

Luồng:

~~~mermaid
flowchart LR
    A["Queue chính"] -->|"Reject, requeue=false"| B["DLX"]
    B --> C[("Retry queue<br/>TTL 5 giây")]
    C -->|"Message hết hạn"| D["Retry DLX"]
    D --> E["Queue chính"]
~~~

Ví dụ cấu hình ý tưởng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 1
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: false
              requeue-rejected: false
              dlq-ttl: 5000
              dlq-dead-letter-exchange: ""
              dlq-dead-letter-routing-key: orders.submitted.order-service
~~~

Ví dụ giả định queue gốc có tên mặc định orders.submitted.order-service, không có prefix và không dùng queueNameGroupOnly. dlq-dead-letter-exchange rỗng chỉ định default exchange; dlq-dead-letter-routing-key phải là đúng tên queue gốc để message hết TTL được route trở lại. Nếu đổi prefix hoặc queue name, phải cập nhật routing key tương ứng. TTL một mình không tạo vòng retry; DLQ phải có dead-letter exchange/routing key đưa message trở lại queue gốc. Nếu message luôn lỗi, vòng lặp có thể kéo dài vô hạn. Có thể đọc x-death để giới hạn số vòng, rồi chuyển message sang parking-lot queue hoặc giữ lại để điều tra.

RabbitMQ quorum queues có hỗ trợ delivery limit và delayed retry riêng ở các phiên bản broker phù hợp. Tính năng và mặc định phụ thuộc phiên bản RabbitMQ; không suy ra rằng requeueRejected=true luôn bị giới hạn bởi x-death. Hãy kiểm tra delivery-count, delivery-limit và chính sách dead-lettering của loại queue đang dùng.

## 12. Transaction và độ tin cậy khi publish DLQ

Nếu consumer được cấu hình transacted, binder có thể tham gia việc publish DLQ trong transaction. Theo tài liệu Rabbit binder, từ phiên bản 3.1.2, việc publish DLQ có thể tham gia transaction của consumer. Nếu publish thất bại, transaction có thể rollback thay vì âm thầm hoàn tất delivery gốc.

Nếu ConnectionFactory bật publisher confirms hoặc returns, binder có thể chờ confirm và kiểm tra message bị returned. Nếu broker trả negative acknowledgement hoặc message bị returned, binder có thể ném AmqpRejectAndDontRequeueException để RabbitMQ thực hiện dead-lettering theo đường broker-native.

Điều này quan trọng khi principal của ứng dụng thiếu quyền publish vào DLX hoặc routing key không khớp. Hãy cấp quyền publish cần thiết, kiểm tra publisher confirms/returns và theo dõi log khi DLQ không nhận message.

Không nên coi việc handler ném exception là bằng chứng message đã được lưu vào DLQ. Cần xác minh kết quả publish hoặc broker dead-lettering, đặc biệt khi dùng transaction.

## 13. DLQ không tự động có consumer xử lý lại

Rabbit binder có thể khai báo DLQ và DLX, nhưng Spring Cloud Stream không tự cung cấp một chính sách chung để tiêu thụ hoặc phát lại mọi message trong DLQ. Ứng dụng và đội vận hành phải quyết định:

- Chỉ đọc và điều tra message lỗi.
- Sửa dữ liệu rồi phát lại thủ công.
- Tự động retry sau một khoảng thời gian.
- Chuyển sang parking-lot queue sau số lần thử tối đa.
- Bỏ message khi lỗi đã được xác định là không thể phục hồi và có phê duyệt nghiệp vụ.

Nếu xây dựng consumer đọc DLQ, cần bảo toàn correlation ID, event ID, routing key và các header điều tra. Khi phát lại, nên thêm metadata lần replay, người thực hiện hoặc thời điểm replay; tránh xóa dấu vết dead-letter ban đầu.

## 14. Kiểm thử tương tác giữa ba thuộc tính

Nên dùng RabbitMQ thật qua Testcontainers hoặc môi trường integration test. Test Binder có thể kiểm tra function wiring nhưng không xác minh đầy đủ requeue, DLX và x-death của broker.

Các kịch bản cần kiểm tra:

1. Handler thành công ngay lần đầu: không retry, không có DLQ.
2. Handler lỗi hai lần rồi thành công: số lần gọi bằng ba, message được acknowledge sau thành công.
3. Handler lỗi hết maxAttempts với republishToDlq=true: DLQ nhận message cùng header exception.
4. Handler lỗi hết maxAttempts với republishToDlq=false và requeueRejected=false: broker dead-letter message và có x-death.
5. maxAttempts=1, requeueRejected=true: message được redeliver vào queue gốc; xác minh không tạo vòng lặp kéo dài trong test.
6. Không cấu hình DLX/DLQ và reject không requeue: xác minh message bị loại khỏi queue để nhận diện rủi ro mất message.
7. DLQ publish bị từ chối do quyền hoặc routing: xác minh lỗi được ghi nhận và delivery không bị acknowledge sai.
8. ImmediateAcknowledgeAmqpException: xác minh message bị bỏ qua và không xuất hiện trong DLQ.
9. Exception không retryable: xác minh handler chỉ được gọi một lần trước khi chuyển sang đường xử lý cuối.
10. Message có payload lớn: xác minh stack trace header không vượt frame_max hoặc bị cắt ngoài dự kiến.

Một test đếm lần gọi handler có thể dùng bộ đếm trong service giả. Với test DLQ, kiểm tra queue thực tế và message headers; không chỉ xác minh log có dòng lỗi.

## 15. Theo dõi và vận hành

Trong production, nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Số lần retry nội bộ | Lỗi tạm thời có đang tăng hay không |
| Số delivery redelivered | Message có bị broker giao lại nhiều lần không |
| Độ sâu queue chính | Consumer có xử lý kịp lưu lượng không |
| Độ sâu DLQ | Có bao nhiêu message cần điều tra |
| Tốc độ vào DLQ | Lỗi mới phát sinh theo thời gian |
| Tỷ lệ publish DLQ thất bại | Binder có gửi được message lỗi hay không |
| Số message trong parking lot | Message đã vượt quá chính sách retry |
| Thời gian xử lý trung bình và p95/p99 | Backoff và retry có làm nghẽn consumer không |

Không chỉ theo dõi số lượng message ở queue chính. Một queue chính có thể luôn ngắn vì message liên tục bị requeue, trong khi CPU và log tăng cao. Kết hợp redelivered, retry count, DLQ rate và exception type để nhận biết vòng lặp.

Stack trace và exception message có thể chứa tên lớp, câu truy vấn hoặc dữ liệu đầu vào. Hạn chế quyền đọc DLQ, thời gian lưu giữ và nội dung log theo chính sách bảo mật. Không đưa token, mật khẩu hoặc dữ liệu cá nhân vào header chẩn đoán.

## 16. Checklist chọn cấu hình

- [ ] Xác định lỗi nào có thể retry và lỗi nào cần đưa thẳng vào DLQ.
- [ ] Đặt maxAttempts tường minh; nhớ giá trị này bao gồm lần đầu.
- [ ] Chọn backoff phù hợp với thời gian phục hồi của dependency.
- [ ] Bật autoBindDlq nếu muốn binder tạo DLX/DLQ.
- [ ] Chọn rõ republishToDlq true hoặc false theo nhu cầu metadata.
- [ ] Đặt requeueRejected=false cho đường lỗi cuối cùng cần dead-letter.
- [ ] Chỉ dùng requeueRejected=true khi có lý do cụ thể và giới hạn vòng lặp.
- [ ] Kiểm tra phiên bản binder vì mặc định republishToDlq thay đổi giữa các tài liệu/release.
- [ ] Xác minh quyền publish, DLX, routing key và queue DLQ.
- [ ] Kiểm thử message thành công, retry hết lượt, requeue và dead-letter.
- [ ] Có quy trình điều tra, replay hoặc parking-lot cho DLQ.
- [ ] Theo dõi retry, redelivery, DLQ depth và lỗi publish DLQ.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html): thuộc tính autoBindDlq, maxAttempts, requeueRejected, republishToDlq, retry và DLQ.
- [Spring Cloud Stream - Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html): RetryTemplate, maxAttempts, backoff và phân loại exception.
- [Spring Cloud Stream - Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): consumer retry properties và giá trị mặc định.
- [RabbitMQ - Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): dead-letter routing, x-death và lý do message bị dead-letter.
- [RabbitMQ - Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues): delivery limit, redelivery và delayed retry của quorum queue.
