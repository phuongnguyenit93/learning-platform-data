# basicAck, basicNack và basicReject

Giả sử một consumer nhận sự kiện đặt hàng từ RabbitMQ. Sau khi nhận, nó phải đọc dữ liệu, ghi database và quyết định: **xác nhận đã xử lý**, **yêu cầu giao lại**, hay **loại delivery khỏi queue để xử lý lỗi**? Trong giao thức AMQP 0-9-1, ba thao tác chủ chốt là `basicAck`, `basicNack` và `basicReject`.

Với **Spring AMQP**, container của `@RabbitListener` có thể ACK tự động sau khi listener thành công (`AcknowledgeMode.AUTO`), hoặc ứng dụng có thể tự gọi các lệnh trên `com.rabbitmq.client.Channel` (`MANUAL`). Lựa chọn này ảnh hưởng trực tiếp đến khả năng mất message, xử lý trùng, retry và dead-letter.

Bài thuộc chương **Xác nhận tiêu thụ** của module **SPRING_AMQP**. Chúng ta sẽ dùng `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding để thực hành, đồng thời phân biệt consumer ACK với publisher confirms, giao dịch và kết quả nghiệp vụ nhằm xây dựng xử lý bất đồng bộ đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vòng đời một **delivery chưa được ACK (Unacked)** và ý nghĩa của `deliveryTag`.
2. Giải thích chính xác tham số `multiple` của `basicAck`/`basicNack` và `requeue` của `basicNack`/`basicReject`.
3. Chọn lệnh phù hợp khi listener xử lý thành công, gặp lỗi tạm thời hoặc nhận message lỗi không thể khắc phục.
4. Phân biệt `AcknowledgeMode.AUTO`, `MANUAL` và `NONE` trong Spring AMQP.
5. Viết một `@RabbitListener` manual ACK với ba nhánh ACK, NACK + requeue và Reject + dead-letter.
6. Tránh ACK hai lần, ACK sai channel, vòng lặp requeue vô hạn và nhầm lẫn giữa ACK broker–producer với ACK consumer–broker.
7. Quan sát Ready/Unacked/DLQ trong RabbitMQ Management và thiết kế retry/idempotency phù hợp.

## 2. Consumer acknowledgment tồn tại để làm gì?

Khi producer publish tới một exchange, RabbitMQ định tuyến message qua binding vào queue phù hợp. Broker giao message cho consumer; nếu sử dụng **manual acknowledgment** ở mức RabbitMQ, broker giữ delivery ở trạng thái **chưa xác nhận** cho tới khi nhận ACK, NACK/reject hoặc channel/connection liên quan không còn tồn tại.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as RabbitTemplate / Producer
    participant X as Exchange + Binding
    participant Q as RabbitMQ Queue
    participant L as @RabbitListener / Consumer
    P->>X: basic.publish(message)
    X->>Q: Định tuyến vào queue
    Q-->>L: basic.deliver(tag=7)
    Note over Q,L: Delivery ở trạng thái Unacked
    L->>L: Validate và thực hiện nghiệp vụ
    L-->>Q: basic.ack(tag=7)
    Note over Q,L: Broker hoàn tất delivery sau ACK
~~~

Nếu listener **không ACK** vì đang xử lý lâu, message có thể vẫn ở trạng thái **Unacked**. Nếu channel hoặc connection đóng trong khi delivery chưa được xác nhận, broker có thể **đưa message trở lại queue và giao lại**. Vì vậy, cơ chế thông thường có thể dẫn đến **at-least-once delivery** và ứng dụng phải chuẩn bị cho trường hợp xử lý trùng.

**Consumer ACK không xác nhận giao dịch database một cách tự động.** Broker chỉ biết consumer đã gửi một lệnh xác nhận delivery. Nếu ứng dụng ACK trước rồi mới ghi database và bị crash, message có thể bị mất đối với nghiệp vụ. Thực hành an toàn thường là **xử lý, commit nghiệp vụ bền vững, rồi ACK**, kết hợp idempotency khi delivery bị giao lại.

## 3. `deliveryTag`: ACK đúng lần giao trên đúng channel

Khi broker giao một message trên AMQP channel, nó gán một **delivery tag tăng dần trong phạm vi channel đó**. Ví dụ:

~~~text
Consumer channel A: tag 1, 2, 3, ...
Consumer channel B: tag 1, 2, 3, ...
~~~

`deliveryTag=1` trên channel A không có cùng ý nghĩa với `deliveryTag=1` trên channel B. Cùng một sự kiện được giao lại sau khi consumer mất kết nối có thể nhận tag khác, thậm chí bắt đầu lại từ 1 trên channel mới.

Trong Spring AMQP:

~~~java
@RabbitListener(queues = "orders.created", ackMode = "MANUAL")
public void receive(Message message, Channel channel) throws IOException {
    long tag = message.getMessageProperties().getDeliveryTag();
    // Sử dụng channel của chính lần giao message này để ACK/NACK.
    channel.basicAck(tag, false);
}
~~~

Trong đoạn code trên, `Message` là `org.springframework.amqp.core.Message`, `Channel` là `com.rabbitmq.client.Channel` và `IOException` là `java.io.IOException`. Queue `orders.created` phải có sẵn hoặc được khai báo qua topology; ví dụ chỉ minh họa cách lấy tag.

### Vì sao không lưu delivery tag làm event ID?

| Định danh | Phạm vi | Có ổn định khi giao lại/reconnect? | Công dụng |
|---|---|---|---|
| `deliveryTag` | **Một channel** ở phía consumer | Không | ACK/NACK đúng delivery |
| `consumerTag` | Subscription consumer trên channel | Không nên giả định | Truy vết consumer nào nhận |
| `messageId` | Property thường do producer đặt | Có thể giữ nguyên khi broker redeliver; không bảo đảm nếu producer phát bản sao mới | Truy vết payload/message |
| `eventId` | Khóa nghiệp vụ do ứng dụng quy định | **Phải giữ ổn định qua retry cùng một event** | Idempotency, đối soát và log |

**ACK bằng tag không tồn tại, đã ACK rồi hoặc thuộc channel khác** có thể làm RabbitMQ đóng channel với lỗi giao thức như `PRECONDITION_FAILED - unknown delivery tag`. Khi channel đóng, những delivery khác chưa ACK trên channel đó có thể được broker giao lại.

## 4. Ba lệnh cơ bản: cú pháp và ý nghĩa

Đây là API trực tiếp của RabbitMQ Java client:

~~~java
channel.basicAck(deliveryTag, multiple);
channel.basicNack(deliveryTag, multiple, requeue);
channel.basicReject(deliveryTag, requeue);
~~~

| Lệnh | Ý nghĩa | Có `multiple`? | Có `requeue`? |
|---|---|---|---|
| **`basicAck`** | Consumer xác nhận delivery đã hoàn tất | Có | Không |
| **`basicNack`** | Consumer từ chối một hoặc nhiều delivery | Có | Có |
| **`basicReject`** | Consumer từ chối một delivery | **Không** | Có |

**`basicNack` là phần mở rộng của RabbitMQ cho negative acknowledgment**, hỗ trợ từ chối theo nhóm; `basicReject` tương ứng phương thức reject của AMQP 0-9-1 và chỉ áp dụng lên một delivery.

### 4.1. `basicAck(deliveryTag, multiple)`

Xác nhận rằng những delivery được chỉ định đã hoàn tất ở phía consumer.

~~~java
// ACK đúng một delivery:
channel.basicAck(deliveryTag, false);

// ACK mọi delivery CHƯA ACK trên cùng channel có tag <= deliveryTag:
channel.basicAck(deliveryTag, true);
~~~

Tham số `multiple=false` chỉ nhắm tới **một tag**. `multiple=true` nhắm tới **mọi delivery chưa ACK với tag nhỏ hơn hoặc bằng tag đã cho trên cùng channel**. Đây không phải thao tác “ACK đủ N message gần nhất” và cũng không bao giờ lan sang channel khác.

Ví dụ channel A có các delivery tag 5, 6, 7, 8 đang **Unacked**:

| Lệnh gọi | Tác động trên channel A |
|---|---|
| `basicAck(7, false)` | ACK tag 7, tag 5, 6, 8 vẫn chưa ACK |
| `basicAck(7, true)` | ACK mọi tag đang Unacked ≤ 7, tức 5, 6, 7 |
| `basicAck(8, false)` | ACK riêng tag 8 |

Không dùng `multiple=true` khi listener đang xử lý nhiều delivery **đồng thời nhưng chưa hoàn tất** trên cùng channel: một batch ACK có thể xác nhận nhầm những công việc vẫn đang chạy.

### 4.2. `basicNack(deliveryTag, multiple, requeue)`

Thông báo consumer **không hoàn tất** một hoặc nhiều delivery, đồng thời nêu có yêu cầu đưa lại vào queue hay không.

~~~java
// Từ chối một delivery và yêu cầu giao lại:
channel.basicNack(deliveryTag, false, true);

// Từ chối một delivery, KHÔNG đưa lại queue:
channel.basicNack(deliveryTag, false, false);

// Từ chối mọi delivery chưa ACK tới tag này trên cùng channel:
channel.basicNack(deliveryTag, true, false);
~~~

Nếu `requeue=true`, broker cố gắng đưa message trở lại queue để giao lại cho một consumer phù hợp (có thể là **chính consumer vừa NACK**). Thứ tự chính xác sau requeue phụ thuộc trạng thái queue và concurrency; đừng giả định message luôn được đặt vào cuối queue hoặc luôn tới consumer khác.

Nếu `requeue=false`, broker loại delivery khỏi luồng xử lý hiện tại; khi queue có **dead-letter exchange (DLX)** được cấu hình và định tuyến hợp lệ, message có thể được dead-letter; nếu không, message có thể bị loại.

### 4.3. `basicReject(deliveryTag, requeue)`

`basicReject` từ chối **đúng một delivery**, không có tham số `multiple`:

~~~java
// Lỗi dữ liệu cố định: reject, không requeue.
channel.basicReject(deliveryTag, false);

// Reject và yêu cầu đưa lại queue.
channel.basicReject(deliveryTag, true);
~~~

Với một delivery và cùng giá trị `requeue`, `basicNack(tag, false, requeue)` và `basicReject(tag, requeue)` thường dẫn tới hành vi broker tương tự. Khác biệt quan trọng là **`basicNack` có thể áp dụng theo nhóm thông qua `multiple=true`**, còn `basicReject` thì không.

**Không phải cứ lỗi là dùng `basicReject`, cứ retry là dùng `basicNack`.** Cả NACK và Reject đều có thể yêu cầu requeue hoặc không, tùy tham số. Chọn thao tác theo số delivery cần xử lý và mục tiêu nghiệp vụ.

## 5. Bảng quyết định ACK/NACK/Reject

| Tình huống | Lệnh gợi ý | Ý nghĩa / lưu ý |
|---|---|---|
| Xử lý thành công và đã commit kết quả nghiệp vụ phù hợp | `basicAck(tag, false)` | Broker có thể hoàn tất delivery |
| Message sai schema, thiếu trường bắt buộc, không thể xử lý | `basicReject(tag, false)` | Nếu có DLX, có thể đưa vào DLQ để điều tra |
| Một delivery lỗi tạm thời và chiến lược cho phép requeue | `basicNack(tag, false, true)` | Có nguy cơ redelivery ngay và lặp nóng; **phải giới hạn retry** |
| Một delivery cần chuyển sang dead-letter thay vì requeue | `basicNack(tag, false, false)` | DLX/binding phải được khai báo đúng |
| Từ chối nhiều delivery chưa ACK trên **cùng channel** | `basicNack(tag, true, false)` | Chỉ dùng khi thực sự kiểm soát được toàn bộ phạm vi tag |
| Xử lý từng delivery trên nhiều worker/thread | ACK/NACK từng tag với `multiple=false` | Không ACK hộ các tác vụ khác chưa hoàn tất |
| Consumer chưa hoàn thành, kết nối đứt | Không thể đảm bảo gửi được ACK | Broker có thể giao lại; cần xử lý trùng |

**Lệnh ACK/NACK được gửi từ client không phải một transaction chung với database.** Nếu đường truyền đứt đúng lúc ACK, producer/consumer có thể không biết broker đã nhận tín hiệu hay chưa. Vì vậy cần thiết kế để xử lý lại một event an toàn.

## 6. `requeue=true`, redelivery và DLX khác nhau thế nào?

~~~mermaid
flowchart TD
    Q["Queue có message"] --> D["Broker deliver cho consumer"]
    D --> H{"Kết quả xử lý?"}
    H -->|Thành công| A["basicAck(tag, false)"]
    H -->|Thử lại tạm thời| N["basicNack(tag, false, true)"]
    H -->|Lỗi cố định| R["basicReject(tag, false)"]
    N --> Q
    R --> DL{"Queue có DLX hợp lệ?"}
    DL -->|Có| DLQ["DLX định tuyến đến DLQ"]
    DL -->|Không| DROP["Message có thể bị loại"]
~~~

### 6.1. Redelivery không đồng nghĩa “đã xử lý một lần”

Khi broker giao lại message, metadata `redelivered` thường là `true`. Điều đó nghĩa là broker biết **message đã từng được giao**, nhưng **không chứng minh** nghiệp vụ đã chạy xong. Ví dụ: broker giao message, kết nối chết trước khi listener bắt đầu làm gì.

Ngược lại, `redelivered=false` **không chứng minh event nghiệp vụ là mới**. Producer có thể phát hai publication khác nhau mang cùng `eventId` sau khi timeout publisher confirm. Do đó, **`redelivered` không thay thế cơ chế idempotency**, cũng không phải bộ đếm retry.

### 6.2. Requeue nóng là lỗi thiết kế phổ biến

Ví dụ listener luôn gặp lỗi truy cập DB và gọi `basicNack(tag, false, true)`. Broker có thể giao lại ngay, consumer lại NACK, tạo vòng lặp:

~~~text
deliver → lỗi → NACK requeue=true
        → deliver → lỗi → NACK requeue=true
        → deliver → ...
~~~

Hậu quả là CPU, kết nối và log tăng cao, trong khi nghiệp vụ không tiến triển. Với lỗi tạm thời, nên có **retry hữu hạn và backoff**, ví dụ thông qua Spring Retry, delay queue/TTL+DLX, một worker retry được quản lý, hoặc chính sách queue phù hợp. Sau ngưỡng retry, chuyển sang DLQ/cảnh báo hoặc xử lý thủ công.

RabbitMQ **quorum queue** có các cơ chế giới hạn lượt giao và metadata đặc thù, nhưng điều đó phụ thuộc loại queue và chính sách broker; **không dựa vào cờ `redelivered` để đếm số lần thử**. Header `x-death` chủ yếu theo dõi những lần dead-letter, không phải mọi lần NACK requeue tại chỗ.

### 6.3. DLX chỉ hoạt động sau khi message đã vào queue

Khi message trong queue bị reject/NACK với `requeue=false`, hết TTL hoặc gặp điều kiện dead-letter tương ứng, queue có thể chuyển message tới **DLX**. DLX sẽ định tuyến theo routing key/binding tới DLQ nếu cấu hình phù hợp.

**Publisher return khác DLX:** một producer publish tới exchange nhưng không khớp binding nào có thể nhận `basic.return` khi bật `mandatory`; message không tự “đi vào DLQ của consumer” nếu chưa tới queue nguồn.

## 7. Spring AMQP: AUTO, MANUAL và NONE

Spring AMQP cung cấp ba chế độ `AcknowledgeMode`:

| Chế độ Spring | Hành vi | Khi nào cân nhắc |
|---|---|---|
| **`AUTO`** | Listener container **tự ACK** khi handler hoàn tất thành công; xử lý lỗi theo error handler/requeue/reject | Phù hợp với nhiều consumer xử lý đồng bộ |
| **`MANUAL`** | Ứng dụng tự gọi `basicAck`/`basicNack`/`basicReject` trên `Channel` được truyền vào listener | Cần chủ động quyết định ACK theo nghiệp vụ |
| **`NONE`** | Tương đương RabbitMQ consumer `autoAck`: broker không chờ ACK thủ công | Chỉ khi chấp nhận nguy cơ mất message khi consumer lỗi |

**Spring `AUTO` không giống RabbitMQ `autoAck=true`.** Chữ AUTO của Spring nghĩa là container quản lý ACK sau khi xử lý; chữ autoAck của RabbitMQ nói đến việc broker **không giữ delivery chờ consumer xác nhận**.

### 7.1. Trong Spring Boot

Cấu hình thường gặp:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: auto
        prefetch: 10
        default-requeue-rejected: false
~~~

Trong `AUTO`, **không tự gọi `channel.basicAck`** cho cùng delivery: container có thể ACK thêm lần nữa, gây `unknown delivery tag`. Với các lỗi handler, chính sách `default-requeue-rejected`, exception đặc biệt, error handler và retry interceptor ảnh hưởng quyết định reject/requeue; không phải mọi exception đều được xử lý giống nhau.

### 7.2. Trong `MANUAL`

Chọn bằng cấu hình container factory hoặc ngay trên annotation:

~~~java
@RabbitListener(queues = "orders.created", ackMode = "MANUAL")
public void receive(Message message, Channel channel) throws IOException {
    long tag = message.getMessageProperties().getDeliveryTag();

    // Xử lý nghiệp vụ; khi thành công:
    channel.basicAck(tag, false);
}
~~~

Mỗi đường xử lý phải đi tới một quyết định hợp lệ. **Quên ACK/NACK** có thể khiến delivery tiếp tục ở trạng thái Unacked khi channel còn sống và cuối cùng được giao lại sau channel/connection close. Cần tránh cả lỗi ACK trước commit lẫn lỗi ACK lặp.

### 7.3. Trong `NONE`

Broker không chờ consumer xác nhận. Hệ thống có thể giảm chi phí ack, nhưng nếu tiến trình mất kết nối sau khi broker giao message và trước khi database commit, message đã có thể biến mất khỏi queue. Không dùng `NONE` cho nghiệp vụ quan trọng nếu không có cơ chế khác bù đắp được rủi ro.

## 8. Lab hoàn chỉnh: thực hành đủ ba lệnh

Lab dùng **Spring Boot 3.x / Spring AMQP 3.x, Java 17+**, một direct exchange, một queue công việc và một DLQ. Listener `MANUAL` thực hiện:

- Message bắt đầu bằng `ORD-`: mô phỏng xử lý thành công rồi **ACK**.
- Message bắt đầu bằng `RETRY-`: **NACK + requeue đúng một lần trong bộ nhớ của demo**, lần giao sau ACK.
- Message bắt đầu bằng `BAD-` hoặc thiếu `messageId`: **Reject không requeue**, để message được dead-letter.

Bộ nhớ demo chỉ để quan sát hiệu ứng giao lại; **không phải chính sách retry bền vững**. Production cần retry giới hạn được lưu/kiểm soát phù hợp và idempotency.

### 8.1. Khởi động RabbitMQ

Nếu chưa có broker tại local, dùng:

~~~bash
docker run -d --name rabbitmq-ack-lab -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -e RABBITMQ_DEFAULT_USER=lab -e RABBITMQ_DEFAULT_PASS=lab123456 rabbitmq:4-management
~~~

RabbitMQ Management thường tại `http://localhost:15672`. Tài khoản `lab/lab123456` **chỉ dùng trong môi trường học tập**, không dùng mặc định cho triển khai thật. Nếu các cổng đã được sử dụng, dùng broker hiện có hoặc chỉnh port. Trong production, quản lý credentials qua secrets, giới hạn quyền vhost và bật TLS theo yêu cầu.

### 8.2. Maven dependencies

Trong dự án Spring Boot có parent/BOM quản lý phiên bản:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Ứng dụng có lớp `@SpringBootApplication` trong package bao trùm các lớp `@Configuration`, `@RestController` và `@Component` ở dưới. Spring Boot tự cấu hình `RabbitTemplate` và listener container factory trong trường hợp thông thường. Không cần tạo manual `ConnectionFactory` chỉ cho lab này.

### 8.3. `application.yml`

~~~yaml
server:
  port: 8080

spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: lab
    password: lab123456
    listener:
      type: simple
      simple:
        concurrency: 1
        max-concurrency: 1
        prefetch: 1
        acknowledge-mode: manual
~~~

**`concurrency=1` và `prefetch=1`** giúp lần giao đầu, requeue và lần giao tiếp theo dễ theo dõi trong log. Trong hệ thống thật, concurrency và prefetch phải được chọn theo tải, latency, năng lực downstream và bảo đảm thứ tự; không phải mọi ứng dụng đều nên đặt 1.

### 8.4. Exchange, queue, binding và DLQ

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AckLabTopology {

    @Bean
    DirectExchange ackEventsExchange() {
        return new DirectExchange("demo.ack.events", true, false);
    }

    @Bean
    DirectExchange ackDeadLetterExchange() {
        return new DirectExchange("demo.ack.dlx", true, false);
    }

    @Bean
    Queue ackWorkQueue() {
        return QueueBuilder.durable("demo.ack.work")
                .deadLetterExchange("demo.ack.dlx")
                .deadLetterRoutingKey("demo.ack.dead")
                .build();
    }

    @Bean
    Queue ackDeadLetterQueue() {
        return QueueBuilder.durable("demo.ack.dlq").build();
    }

    @Bean
    Binding ackWorkBinding(Queue ackWorkQueue,
                           DirectExchange ackEventsExchange) {
        return BindingBuilder.bind(ackWorkQueue)
                .to(ackEventsExchange)
                .with("order.created");
    }

    @Bean
    Binding ackDeadLetterBinding(Queue ackDeadLetterQueue,
                                 DirectExchange ackDeadLetterExchange) {
        return BindingBuilder.bind(ackDeadLetterQueue)
                .to(ackDeadLetterExchange)
                .with("demo.ack.dead");
    }
}
~~~

Luồng xử lý:

~~~text
RabbitTemplate -> demo.ack.events (direct)
                  -> [routing key = order.created]
                  -> demo.ack.work
                       ├─ ACK                -> hoàn tất delivery
                       ├─ NACK requeue=true  -> quay lại demo.ack.work
                       └─ REJECT requeue=false
                            -> demo.ack.dlx
                            -> demo.ack.dlq
~~~

Spring Boot thường khai báo các bean exchange/queue/binding qua `RabbitAdmin` khi có kết nối và auto-declaration phù hợp. Nếu queue đã tồn tại với tham số DLX khác, RabbitMQ có thể báo lỗi `PRECONDITION_FAILED - inequivalent arg`; không xóa queue có dữ liệu chỉ để cho ví dụ chạy được.

### 8.5. Producer `RabbitTemplate`: đặt `messageId` ổn định

~~~java
import java.util.Map;
import java.util.UUID;

import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lab/ack")
public class AckLabPublisher {

    private final RabbitTemplate rabbitTemplate;

    public AckLabPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @PostMapping("/send")
    public ResponseEntity<Map<String, String>> send(
            @RequestParam(defaultValue = "ORD-1001") String orderId) {

        String eventId = UUID.randomUUID().toString();

        rabbitTemplate.convertAndSend(
                "demo.ack.events",
                "order.created",
                orderId,
                message -> {
                    var properties = message.getMessageProperties();
                    properties.setMessageId(eventId);
                    properties.setHeader("eventId", eventId);
                    properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    return message;
                });

        return ResponseEntity.accepted().body(
                Map.of("eventId", eventId, "orderId", orderId));
    }
}
~~~

`eventId` và `messageId` dùng để truy vết một sự kiện nghiệp vụ; chúng **không** là `deliveryTag`. Lệnh `RabbitTemplate.convertAndSend` trả về và HTTP `202 Accepted` **không phải** publisher confirm hoặc consumer ACK. Nếu cần biết broker xác nhận đúng publication và có queue nhận, producer phải cấu hình publisher confirms/returns riêng.

### 8.6. Consumer `MANUAL`: ACK, NACK, Reject

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import com.rabbitmq.client.Channel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class AckLabListener {

    private static final Logger log =
            LoggerFactory.getLogger(AckLabListener.class);

    // CHỈ CHO LAB: mất khi restart; không làm retry store ở production.
    private final Set<String> retrySeen = ConcurrentHashMap.newKeySet();

    @RabbitListener(queues = "demo.ack.work", ackMode = "MANUAL")
    public void receive(Message message, Channel channel) throws IOException {
        MessageProperties p = message.getMessageProperties();
        long tag = p.getDeliveryTag();
        String eventId = p.getMessageId();
        String orderId = new String(
                message.getBody(), StandardCharsets.UTF_8);

        log.info(
                "RECEIVED eventId={} orderId={} tag={} redelivered={} consumer={}",
                eventId, orderId, tag, p.isRedelivered(), p.getConsumerTag());

        // Nhánh 1: message lỗi cố định -> không requeue, chuyển DLQ.
        if (eventId == null || eventId.isBlank()
                || orderId.isBlank() || orderId.startsWith("BAD-")) {
            log.warn("REJECT eventId={}, tag={}", eventId, tag);
            channel.basicReject(tag, false);
            return;
        }

        // Nhánh 2: minh họa lỗi tạm thời một lần, rồi cho thử lại.
        if (orderId.startsWith("RETRY-") && retrySeen.add(eventId)) {
            log.warn("NACK + REQUEUE eventId={}, tag={}", eventId, tag);
            channel.basicNack(tag, false, true);
            return;
        }

        // Nhánh 3: mô phỏng nghiệp vụ hoàn tất.
        // Production: xử lý idempotent + commit DB bền vững trước khi ACK.
        log.info("ACK eventId={}, tag={}", eventId, tag);
        channel.basicAck(tag, false);
    }
}
~~~

**Đọc kỹ các ràng buộc của ví dụ:**

- `@RabbitListener(ackMode = "MANUAL")` yêu cầu **ứng dụng** quyết định ACK/NACK. Không có auto-ACK sau khi listener trả về ở nhánh bình thường.
- `basicAck(tag, false)`, `basicNack(tag, false, true)` và `basicReject(tag, false)` dùng **tag của chính delivery đang được xử lý** và **channel được truyền vào listener**.
- Set `retrySeen` chỉ mô phỏng **một lần requeue**. Nếu chạy nhiều JVM/consumer, restart hoặc có event trùng, logic này **không kiểm soát retry toàn hệ thống** và có thể giữ ID trong bộ nhớ vô hạn. Không tái sử dụng cơ chế này cho production.
- Nếu gọi ACK/NACK gặp `IOException` do channel/connection hỏng, không tự đoán broker đã nhận thao tác hay chưa; tránh ACK lại trên channel khác. Delivery có thể được giao lại.
- Code chỉ mô phỏng xử lý thành công bằng log. Đừng ACK trước khi nghiệp vụ thật được ghi nhận; nếu xử lý bên ngoài có thể ném exception, cần chính sách xử lý lỗi và xác nhận rõ ràng.

## 9. Chạy thử và đối chiếu kết quả

### 9.1. Xử lý thành công: `basicAck`

~~~bash
curl -X POST "http://localhost:8080/lab/ack/send?orderId=ORD-1001"
~~~

Log dự kiến (giá trị ID/tag là minh họa):

~~~text
RECEIVED eventId=e-1 orderId=ORD-1001 tag=1 redelivered=false
ACK eventId=e-1 tag=1
~~~

Kết quả: queue `demo.ack.work` không giữ lại delivery đó ở trạng thái Unacked sau khi ACK được broker nhận. Không có message chuyển sang `demo.ack.dlq` vì listener không reject.

### 9.2. NACK + requeue: `basicNack`

~~~bash
curl -X POST "http://localhost:8080/lab/ack/send?orderId=RETRY-1002"
~~~

Log tương tự:

~~~text
RECEIVED eventId=e-2 orderId=RETRY-1002 tag=2 redelivered=false
NACK + REQUEUE eventId=e-2 tag=2
RECEIVED eventId=e-2 orderId=RETRY-1002 tag=3 redelivered=true
ACK eventId=e-2 tag=3
~~~

Điểm cần nhận ra:

1. `eventId` vẫn là một giá trị vì đây là **cùng message được giao lại**.
2. `deliveryTag` của lần thứ hai **khác lần đầu** nếu cùng channel; nếu channel thay đổi, chuỗi tag có thể bắt đầu lại.
3. `redelivered=true` cho biết broker đang giao lại, nhưng không phải bằng chứng dữ liệu nghiệp vụ đã ghi.
4. Phải ACK bằng **tag của delivery hiện tại**, không dùng tag cũ của lần giao đầu.

### 9.3. Reject không requeue: `basicReject`

~~~bash
curl -X POST "http://localhost:8080/lab/ack/send?orderId=BAD-1003"
~~~

Log:

~~~text
RECEIVED eventId=e-3 orderId=BAD-1003 tag=4 redelivered=false
REJECT eventId=e-3 tag=4
~~~

Nếu DLX/binding hợp lệ, message sẽ được broker dead-letter vào `demo.ack.dlq`. Không tạo listener tự động consume DLQ trong lab này: nhờ đó có thể mở **RabbitMQ Management → Queues and Streams → demo.ack.dlq** để quan sát message đang chờ điều tra.

### Bảng đối chiếu

| Message | Lệnh ở listener | `demo.ack.work` | `demo.ack.dlq` |
|---|---|---|---|
| `ORD-1001` | `basicAck(tag,false)` | Hoàn tất delivery | Không có message này |
| `RETRY-1002`, lần 1 | `basicNack(tag,false,true)` | Được đưa lại để giao tiếp | Không vào DLQ chỉ vì NACK requeue |
| `RETRY-1002`, lần 2 | `basicAck(tag2,false)` | Hoàn tất delivery mới | Không có message này |
| `BAD-1003` | `basicReject(tag,false)` | Bị loại khỏi đường xử lý hiện tại | Có thể có nếu DLX/binding đúng |

Trong Windows PowerShell, dùng `curl.exe` thay cho alias `curl` nếu cú pháp trên không hoạt động.

**Dòng log là minh họa, không phải chuỗi tag cố định.** RabbitMQ có thể sử dụng những tag lớn hơn hoặc đổi consumer/channel sau reconnect. Sau khi listener ACK rất nhanh, Management có thể hiển thị `Ready=0, Unacked=0` trước khi bạn kịp xem; log có `eventId` giúp truy vết chính xác hơn.

## 10. Tham số `multiple` và bẫy ACK hàng loạt

### 10.1. Những delivery trên cùng channel

Giả sử channel có ba delivery chưa ACK: 10, 11 và 12. Công việc cho tag 10 và 12 đã hoàn tất, nhưng tag 11 vẫn xử lý database.

~~~text
Channel X:
  tag=10 -> DONE
  tag=11 -> IN_PROGRESS
  tag=12 -> DONE
~~~

Nếu gọi:

~~~java
channel.basicAck(12, true);
~~~

Broker sẽ ACK **cả các delivery chưa ACK có tag ≤ 12**, bao gồm tag 11 **dù nghiệp vụ chưa hoàn tất**. Nếu tiến trình chết ngay sau đó, message tag 11 có thể không được giao lại dù công việc chưa commit.

Ngược lại:

~~~java
channel.basicAck(10, false);
channel.basicAck(12, false);
// Chỉ sau khi tag 11 thực sự xong:
channel.basicAck(11, false);
~~~

Đây là lý do dùng **`multiple=false`** là lựa chọn đơn giản/an toàn để bắt đầu, nhất là khi xử lý đồng thời hoặc cơ chế async/batch có nhiều delivery chưa hoàn thành. Chỉ dùng `multiple=true` khi bạn kiểm soát chính xác rằng **tất cả delivery chưa ACK đến tag đó đã hoàn tất** trên cùng channel.

### 10.2. `basicNack` hàng loạt còn tác động mạnh hơn

~~~java
channel.basicNack(12, true, false);
~~~

Lệnh này từ chối **mọi delivery chưa ACK với tag ≤ 12** trên channel, và `requeue=false` có thể đưa nhiều message cùng lúc vào đường dead-letter/discard. Nếu bạn chỉ muốn từ chối tag 12:

~~~java
channel.basicNack(12, false, false);
~~~

`basicReject` **không** hỗ trợ tác động hàng loạt. Điều quan trọng không phải chọn lệnh ngắn hơn, mà là biết **chính xác những delivery nào bị ảnh hưởng**.

## 11. Đường lỗi production: retry có giới hạn, idempotency, giao dịch

### 11.1. Phân loại lỗi thay vì requeue tùy tiện

| Loại lỗi | Ví dụ | Hướng xử lý thường phù hợp |
|---|---|---|
| **Lỗi dữ liệu cố định** | JSON sai định dạng, thiếu ID, version schema không hỗ trợ | Reject không requeue → DLQ/kiểm tra |
| **Lỗi hạ tầng tạm thời** | DB timeout, dịch vụ downstream gián đoạn ngắn | Retry hữu hạn với backoff; sau ngưỡng chuyển DLQ/cảnh báo |
| **Không rõ kết quả nghiệp vụ** | Database commit được nhưng connection consumer mất trước ACK | Redelivery có thể xảy ra; consumer phải idempotent |
| **Lỗi topology/publish** | Exchange/binding sai làm publication không vào queue | Xử lý ở producer bằng publisher returns/confirm; không phải consumer NACK |
| **Lỗi logic không phục hồi tự động** | Quy tắc nghiệp vụ bất khả thi | Ghi trạng thái nghiệp vụ phù hợp, reject hoặc ACK theo hợp đồng thiết kế |

Không thể lấy một chính sách duy nhất cho mọi exception. Ví dụ, lỗi validation không nên thử vô hạn; lỗi DB tạm thời lại có thể cần thử sau một khoảng delay thay vì loại bỏ ngay.

### 11.2. Một mẫu xử lý nghiệp vụ theo thứ tự an toàn

~~~text
1. Nhận delivery và đọc eventId
2. Validate schema, version, dữ liệu bắt buộc
3. Kiểm tra eventId đã xử lý chưa (idempotency store)
4. Thực hiện business transaction và ghi nhận eventId bền vững
5. Sau khi transaction hoàn tất, basicAck(tag, false)

Nếu lỗi dữ liệu không phục hồi:
  -> basicReject(tag, false), DLQ nếu có

Nếu lỗi hạ tầng tạm thời:
  -> retry/backoff hữu hạn theo thiết kế
  -> chỉ NACK requeue=true khi không tạo vòng lặp nóng
~~~

**Không có transaction nguyên tử mặc định giữa database và consumer ACK.** Nếu transaction đã commit nhưng ACK thất lạc, broker có thể giao lại. Khi đó cơ chế idempotency phải phát hiện `eventId` đã xử lý và ACK delivery mới mà không lặp side effect.

Nếu consumer còn phát sự kiện tiếp theo, cần xem xét mô hình **transactional outbox** để tránh tình huống ghi DB thành công nhưng publish event tiếp theo thất bại. `basicAck` không tự kích hoạt publisher confirms cho `RabbitTemplate`, và AMQP transaction không tự bao trùm transaction database.

### 11.3. Async listener: không ACK khi công việc nền chưa xong

Mẫu sai:

~~~java
@RabbitListener(queues = "orders.created")
public void receive(String orderId) {
    CompletableFuture.runAsync(() -> processOrder(orderId));
    // Listener trả về; container chế độ AUTO có thể ACK trước khi
    // processOrder() thật sự hoàn tất.
}
~~~

Đoạn trên chỉ minh họa **anti-pattern**, không phải ví dụ nên đưa vào production. Nếu cần xử lý bất đồng bộ, chọn cơ chế async listener/acknowledgment mà phiên bản Spring AMQP hỗ trợ hoặc tự quản lý `MANUAL` một cách an toàn, theo dõi future completion, lỗi, timeout và channel lifecycle. Không giữ `Channel` rồi tùy ý ACK từ nhiều thread vì RabbitMQ Java client channel không phải đối tượng an toàn để chia sẻ không kiểm soát.

### 11.4. Confirm ở producer khác consumer ACK

| Phía | Tín hiệu | Nó chứng minh điều gì? |
|---|---|---|
| Producer → broker | Publisher confirm ACK/NACK | Broker xác nhận publication ở mức giao thức publisher confirm |
| Broker → producer | Publisher return | Với mandatory phù hợp, publication không định tuyến tới queue nào |
| Consumer → broker | `basicAck`/`basicNack`/`basicReject` | Consumer xác nhận/từ chối **delivery** |
| Business service / database | Business status | Công việc nghiệp vụ hoàn tất hay cần xử lý tiếp |

Đặc biệt, publisher có thể nhận **confirm ACK nhưng message bị return** khi không có queue đích. Điều đó khác hoàn toàn với consumer `basicNack`, vì consumer chỉ có thể NACK **delivery đã được broker giao**.

## 12. Quan sát bằng RabbitMQ Management và log

Trong Management (thường ở `http://localhost:15672` nếu bật plugin), mở queue `demo.ack.work` và `demo.ack.dlq`:

| Thông số | Cách hiểu | Điều không nên suy diễn |
|---|---|---|
| **Ready** | Message đang chờ được giao tới consumer | Không nhất thiết là tổng công việc chưa xong |
| **Unacked** | Delivery broker đã giao nhưng chưa nhận ACK/NACK/reject kết thúc phù hợp | Không chứng minh từng tác vụ đang chạy CPU; có thể đã đệm hoặc chờ I/O |
| **Consumers** | Số consumer đang đăng ký trên queue | Không bảo đảm tất cả listener đều đang xử lý thành công |
| **Deliver / Ack rate** | Tốc độ giao/ACK message | Không đo trực tiếp transaction business |
| **Redeliver rate** | Mức độ giao lại | Không tự phân biệt lỗi mạng với retry chủ động |
| **DLQ Ready** | Message đang chờ điều tra ở DLQ | Không thể mặc định mọi lỗi đều đến đây |

Thêm các trường vào log ứng dụng:

~~~text
timestamp, eventId, orderId, consumerTag, deliveryTag,
redelivered, queue, ackAction, exceptionClass, processingLatency
~~~

`deliveryTag` **không duy nhất trên toàn hệ thống**; nếu muốn truy vết delivery cần gắn thêm channel/connection hoặc thông tin phiên. Để theo dõi cùng sự kiện qua producer, retries và consumer, dùng `eventId` là khóa chính.

**Kiểm tra DLQ:** message bị reject không requeue có thể mang header lịch sử dead-letter `x-death`. Header này thường ghi thông tin lý do, queue nguồn và các sự kiện dead-letter tương ứng; nó **không phải số lần `basicNack(..., requeue=true)` ở cùng queue**.

### Nếu Unacked cứ tăng

Kiểm tra thứ tự:

1. Listener có dùng `MANUAL` nhưng quên ACK/NACK ở một nhánh exception không?
2. Có xử lý blocking I/O hoặc database transaction bị treo không?
3. `prefetch` và concurrency có quá cao so với downstream không?
4. Có consumer chết/chuyển connection làm message bị redeliver không?
5. Có sử dụng `multiple=true`/channel sai khiến channel bị đóng và tạo vòng lặp recovery không?

Tăng concurrency chưa chắc giải quyết nghẽn nếu bottleneck nằm ở database hoặc một downstream API. Đo throughput, thời gian xử lý và lỗi trước khi điều chỉnh.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
|---|---|---|
| Message nằm ở **Unacked** lâu | Quên ACK trong MANUAL; handler bị treo | Bổ sung quyết định ACK/NACK cho mọi đường; kiểm tra thread dump và timeout |
| Channel bị đóng với `unknown delivery tag` | ACK lặp, ACK tag cũ, ACK trên channel khác, chồng AUTO+manual | Dùng tag/channel của delivery hiện tại, chỉ ACK một lần |
| Message nhận lại nhiều lần rất nhanh | `basicNack(..., requeue=true)` liên tục hoặc error handler requeue | Retry có giới hạn và backoff, tránh hot loop |
| Dữ liệu lỗi biến mất, DLQ trống | Reject không requeue nhưng không có DLX/binding hợp lệ | Khai báo và xác minh DLX/DLQ; theo dõi lỗi |
| Message lỗi vẫn nằm queue thay vì DLQ | Đã NACK/Reject với `requeue=true` | Đổi thành `requeue=false` khi quyết định dead-letter |
| Một số message mất sau listener bắt đầu | Dùng `NONE`/autoAck ở mức broker hoặc ACK trước commit | Chọn AUTO/MANUAL phù hợp và ACK sau công việc |
| Đã ACK nhưng nghiệp vụ thực thi hai lần | Commit xong, ACK thất lạc và delivery được giao lại | Idempotency theo event ID, transaction và ràng buộc DB |
| `multiple=true` khiến dữ liệu mất | ACK các delivery đang xử lý song song chưa hoàn tất | Ưu tiên `multiple=false` hoặc thiết kế batch ACK thật chặt |
| Message bị lỗi sau khi publisher confirm ACK | Confirm chỉ xác nhận phía publish, consumer vẫn có thể fail | Theo dõi consumer error, queue, DLQ và business status riêng |
| Message chưa vào queue dù `RabbitTemplate` không lỗi | Sai exchange/routing key/binding, mandatory/returns chưa bật | Kiểm tra topology, publisher returns/confirm; không sửa bằng consumer ACK |
| ACK không thành công khi connection mất | Trạng thái broker nhận ACK có thể không biết chắc | Không ACK lại trên channel mới; hỗ trợ redelivery và idempotency |

## 14. Bài tập thực hành

**Bài A — So sánh ba lệnh.** Chạy lab và gửi ba event `ORD-1001`, `RETRY-1002`, `BAD-1003`. Ghi lại `eventId`, `deliveryTag`, `redelivered`, thao tác ACK/NACK/Reject và trạng thái queue/DLQ. Giải thích vì sao chỉ `BAD-1003` đi vào DLQ ở cấu hình lab.

**Bài B — Phân tích `multiple`.** Giả sử một channel có tag 1, 2, 3 chưa ACK, trong đó tag 2 vẫn đang xử lý. So sánh `basicAck(3, true)` và `basicAck(3, false)`. Câu hỏi: lệnh nào có thể xác nhận nhầm tag 2? Không cần thử ACK nhầm trên một broker có dữ liệu thật.

**Bài C — Không có DLX.** Trong một môi trường lab khác, tạo queue không có DLX rồi reject message với `requeue=false`. Quan sát message có còn ở queue không; nêu lý do phải thiết kế DLQ và cảnh báo phù hợp cho poison messages.

**Bài D — Requeue nóng.** Phác thảo tình huống DB luôn timeout. Điều gì sẽ xảy ra nếu mọi lần đều gọi `basicNack(tag, false, true)`? Thiết kế thay thế có retry tối đa, backoff và một lối ra DLQ rõ ràng.

**Bài E — Restart sau business commit.** Cho một event được ghi DB thành công nhưng chưa ACK, rồi mô phỏng consumer mất kết nối trong lab. Khi broker giao lại, kiểm tra `eventId` đã xử lý và quyết định có cần chạy lại side effect không. Phân biệt `redelivered` và idempotency key.

**Bài F — AUTO so với MANUAL.** Chuyển một listener test độc lập sang `AUTO`, loại bỏ lời gọi ACK thủ công, rồi thử handler thành công và handler ném lỗi. Ghi lại hành vi container và thiết kế retry/DLQ. Không chạy đồng thời hai listener đối chiếu trên cùng queue nếu muốn quan sát chính xác một handler.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `basicAck(deliveryTag, false)` khác `basicAck(deliveryTag, true)` thế nào?

**Trả lời:** `false` ACK một delivery đúng tag; `true` ACK tất cả delivery **chưa ACK** với tag nhỏ hơn hoặc bằng tag chỉ định trên **cùng channel**.

**Câu 2.** `basicNack(tag, false, false)` và `basicReject(tag, false)` có gì giống và khác?

**Trả lời:** Cả hai từ chối **một delivery** và **không yêu cầu requeue**; message có thể vào DLX/DLQ nếu được cấu hình phù hợp. `basicNack` còn có tùy chọn `multiple` để từ chối theo nhóm, `basicReject` không có.

**Câu 3.** Nếu chỉ muốn RabbitMQ giao lại một message, dùng gì?

**Trả lời:** `basicNack(tag, false, true)` hoặc `basicReject(tag, true)` đều có thể yêu cầu requeue một delivery. Phải kiểm soát số lần thử, vì message có thể được giao lại ngay.

**Câu 4.** Khi listener dùng Spring `AUTO`, có cần gọi `basicAck` ở cuối phương thức không?

**Trả lời:** Không. Container quản lý ACK khi listener thành công. Tự ACK lại cùng delivery có thể gây lỗi double-ack/unknown delivery tag.

**Câu 5.** `redelivered=true` có chứng minh lần xử lý trước đã commit database?

**Trả lời:** Không. Nó chỉ cho biết broker đang giao lại một message đã từng được giao. Cần idempotency và trạng thái nghiệp vụ bền vững để biết side effect nào đã xảy ra.

**Câu 6.** Producer đã nhận publisher confirm ACK, có nghĩa consumer nên gọi `basicAck` ngay mà chưa xử lý không?

**Trả lời:** Không. Publisher confirm và consumer acknowledgment là hai luồng độc lập. Consumer chỉ ACK khi điều kiện hoàn tất công việc của nó đã được đáp ứng.

**Câu 7.** Vì sao message bị `basicReject(tag, false)` đôi khi không xuất hiện ở DLQ?

**Trả lời:** Queue có thể chưa cấu hình DLX, DLX không tồn tại, binding/routing key sai hoặc có lỗi quyền và cấu hình broker. `requeue=false` không tự tạo một DLQ.

**Câu 8.** Có nên lưu `deliveryTag` để một worker khác ACK vào ngày hôm sau không?

**Trả lời:** Không. Tag chỉ hợp lệ trên channel của delivery hiện tại. Nếu cần theo dõi dài hạn, lưu `eventId`/trạng thái nghiệp vụ và dùng delivery tag mới khi message được giao lại.

## 16. Ghi nhớ

- **`basicAck(tag, multiple)`** xác nhận delivery; với `multiple=true`, nó ACK tất cả delivery chưa ACK có tag ≤ tag chỉ định **trên cùng channel**.
- **`basicNack(tag, multiple, requeue)`** từ chối một hoặc nhiều delivery. **`basicReject(tag, requeue)`** từ chối đúng một delivery. `requeue=false` có thể dead-letter khi queue có DLX hợp lệ; `requeue=true` có thể giao lại.
- **`deliveryTag` thuộc về channel của lần giao, không phải định danh message nghiệp vụ.** ACK đúng tag, đúng channel, đúng một lần; với xử lý song song, ưu tiên `multiple=false`.
- **Spring `AUTO` khác `NONE`; `MANUAL` đòi hỏi ứng dụng quản lý ACK/NACK.** Tránh ACK trước commit, ACK hai lần và vô tình để Unacked tồn đọng.
- **Giao nhận đáng tin cậy cần nhiều hơn ba lệnh:** exchange/queue/binding đúng, publisher confirms/returns, retry có giới hạn, DLQ, idempotency, transaction/outbox và quan sát Ready/Unacked cùng trạng thái nghiệp vụ.
