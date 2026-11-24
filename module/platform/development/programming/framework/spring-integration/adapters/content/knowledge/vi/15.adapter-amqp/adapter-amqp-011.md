# Dead-letter exchange và requeue

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **dead-lettering** là gì, vai trò riêng của **dead-letter exchange (DLX)**, **dead-letter queue (DLQ)**, binding và routing key.
- Phân biệt **basicAck**, **basicReject**, **basicNack**, cờ **requeue=true/false**, broker redelivery và thao tác **republish** một message mới.
- Mô tả các tình huống một message bị dead-letter: bị từ chối không requeue, hết TTL, vượt giới hạn độ dài hoặc đạt delivery limit của loại queue hỗ trợ.
- Thiết kế luồng **retry có giới hạn và backoff**, tránh vòng lặp requeue nóng, vòng lặp dead-letter và lưu trữ message lỗi vô thời hạn.
- Cấu hình RabbitMQ topology bằng **Spring AMQP**, rồi tích hợp Spring Integration **AMQP inbound channel adapter**, **MessageChannel**, service activator và error handling.
- Phân tích tác động của **AUTO/MANUAL ACK**, MessageConverter, listener container, prefetch, transaction database, idempotency và shutdown.
- Kiểm thử các tình huống reject, DLX thiếu binding, retry chậm, connection loss, consumer crash và redelivery bằng RabbitMQ thực.

## 1. Bài toán: một message lỗi liên tục sẽ đi đâu?

Giả sử queue **orders.created.q** chứa nhiều sự kiện **OrderCreated**. Phần lớn message hợp lệ, nhưng một message có JSON sai schema khiến WarehouseService luôn thất bại. Nếu consumer cứ **NACK và requeue=true**, RabbitMQ có thể giao đi giao lại rất nhanh. Consumer xử lý cùng lỗi nhiều lần, queue không có tiến độ nghiệp vụ, log tăng liên tục và các message hợp lệ bị ảnh hưởng.

Ngược lại, nếu consumer **NACK với requeue=false** nhưng queue không có cấu hình dead-lettering, message có thể bị loại bỏ thay vì nằm ở một nơi có thể điều tra và phát lại.

Một thiết kế thường thấy:

~~~mermaid
flowchart LR
    P["Order publisher"] --> X["orders.events<br/>exchange"]
    X --> Q["orders.created.q<br/>main queue"]
    Q --> L["AMQP inbound adapter<br/>listener container"]
    L --> H{"Warehouse handler"}
    H -->|"Thành công"| A["Consumer ACK"]
    H -->|"Lỗi cố định / hết retry"| N["Reject hoặc NACK<br/>requeue=false"]
    N --> D["orders.dead.exchange<br/>DLX"]
    D --> DQ["orders.created.dlq"]
    H -->|"NACK requeue=true"| Q
~~~

**DLX là exchange, không phải queue.** RabbitMQ gửi một message bị dead-letter đến **exchange đó**, rồi exchange tiếp tục dùng routing key và binding để quyết định queue nào nhận. Nếu không có route phù hợp, **việc cấu hình tên DLX không tự bảo đảm message tồn tại trong DLQ**.

Trong module **SPRING_INTEGRATION_ADAPTERS**, bài học thuộc chương **Adapter AMQP**. Nó tập trung vào ranh giới lỗi khi kết nối RabbitMQ với inbound/outbound adapter, gateway và MessageChannel. Tư duy tách lỗi nguồn, lỗi định tuyến, lỗi xử lý và điểm lưu bền cũng rất quan trọng khi xây luồng File, SFTP, HTTP, JMS, Kafka hoặc database.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Lưu ý quan trọng |
| --- | --- | --- |
| **Queue chính** | Queue consumer nhận delivery phục vụ nghiệp vụ | Chứa message ready/unacked theo trạng thái broker |
| **Dead-letter exchange (DLX)** | Exchange RabbitMQ nhận message bị dead-letter từ queue nguồn | Không lưu message như queue |
| **Dead-letter queue (DLQ)** | Queue bind vào DLX để giữ message lỗi | Phải có binding phù hợp, quyền và chính sách lưu giữ |
| **Dead-letter routing key** | Routing key dùng khi message được publish sang DLX | Có thể được queue cấu hình bằng x-dead-letter-routing-key |
| **Requeue** | Cho phép delivery quay lại trạng thái có thể nhận của queue | Không tự tạo delay hoặc giới hạn lượt retry |
| **Redelivery** | Một delivery được broker giao lại sau NACK/requeue hoặc mất consumer | Không đồng nghĩa producer đã publish lại |
| **Republish** | Ứng dụng phát một AMQP message mới tới exchange/queue | Cần publisher confirms, idempotency và phối hợp ACK nguồn |
| **Retry queue** | Queue có cơ chế giữ message trước khi giao lại để retry | Khác DLQ dành cho message cuối cùng không xử lý được |

### 2.1. DLX là một bước định tuyến thứ hai

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant E as orders.events
    participant Q as orders.created.q
    participant C as Consumer
    participant D as orders.dead.exchange
    participant F as orders.created.dlq
    P->>E: Publish orders.created
    E->>Q: Route message
    Q-->>C: Delivery
    C-->>Q: basicReject(tag, requeue=false)
    Q->>D: Dead-letter message
    D->>F: Route theo dead routing key
~~~

Điểm cần nhớ: consumer **không trực tiếp gửi message vào DLQ** chỉ bằng basicReject. Consumer từ chối delivery; RabbitMQ xét cấu hình dead-lettering của queue nguồn rồi publish message sang DLX. Nếu DLX hoặc binding không có, message có thể không được giữ như dự kiến.

### 2.2. Consumer ACK, publisher confirm và publisher return không giống nhau

| Cơ chế | Thời điểm | Trách nhiệm |
| --- | --- | --- |
| **Publisher confirm** | Publisher gửi message tới exchange | Broker xác nhận xử lý publish theo cơ chế confirms |
| **Publisher return** | Publish không route được trong điều kiện mandatory | Báo publisher về một message không được định tuyến |
| **Consumer ACK/NACK/reject** | Sau khi broker giao delivery cho consumer | Báo broker consumer hoàn tất hoặc từ chối delivery |
| **Dead-lettering** | Message đã vào queue, sau đó đáp ứng điều kiện dead-letter | Broker thực hiện publish sang DLX |

Nếu một producer publish vào exchange **không có binding**, message có thể bị **publisher return**; đó không phải consumer đã reject và cũng không mặc nhiên xuất hiện ở DLQ. **DLX không thay thế publisher returns**.

## 3. RabbitMQ xử lý basicAck, basicReject và basicNack

Đối với delivery được giao trong chế độ explicit acknowledgment, consumer có thể sử dụng API RabbitMQ Java client:

~~~java
import com.rabbitmq.client.Channel;

// Chi goi MOT trong nhung lenh sau cho mot delivery.
channel.basicAck(deliveryTag, false);
channel.basicReject(deliveryTag, true);
channel.basicReject(deliveryTag, false);
channel.basicNack(deliveryTag, false, true);
channel.basicNack(deliveryTag, false, false);
~~~

| Lệnh | Ý nghĩa chính | Kết quả ở broker |
| --- | --- | --- |
| **basicAck(tag, false)** | Consumer xác nhận delivery hoàn tất | Broker không tiếp tục chờ ACK của delivery đó |
| **basicReject(tag, true)** | Từ chối một delivery, yêu cầu requeue | Có thể được giao lại theo broker policy |
| **basicReject(tag, false)** | Từ chối một delivery, không requeue | Có thể dead-letter qua DLX hoặc bị loại bỏ |
| **basicNack(tag, false, true)** | NACK một delivery, requeue | Có thể redeliver, không tự chờ backoff |
| **basicNack(tag, false, false)** | NACK một delivery, không requeue | Có thể dead-letter qua DLX |
| **basicNack(tag, true, ...)** | NACK nhiều delivery chưa ACK tới tag trên cùng channel | Cần cực kỳ cẩn thận khi nhiều tác vụ in-flight |

**Delivery tag chỉ có ý nghĩa trên channel nhận delivery.** Không ACK/NACK trên một channel khác, không lưu tag để xác nhận sau khi reconnect và không sử dụng nó làm eventId. Trong ví dụ, **multiple=false** được dùng để không vô tình settle những message khác.

### 3.1. Requeue=true: quay lại queue, không phải retry có delay

Khi consumer thực hiện **basicNack(tag, false, true)**, broker có thể đưa delivery trở lại queue, có thể giữ vị trí gần vị trí ban đầu theo điều kiện concurrency và các thao tác đồng thời. Nếu consumer rảnh, message có thể được giao lại **ngay lập tức**.

~~~mermaid
flowchart TD
    Q["Queue"] --> C["Consumer"]
    C --> H{"Business handler"}
    H -->|"Lỗi"| N["basicNack(requeue=true)"]
    N --> Q
    H -->|"Thành công"| A["basicAck"]
~~~

Nếu message lỗi schema vĩnh viễn, vòng này có thể chạy rất nhanh. RabbitMQ **không mặc định thêm exponential backoff, giới hạn retry hoặc tự chuyển sang DLQ chỉ vì message đã bị requeue nhiều lần**. Một số **quorum queue** có thể có delivery limit được cấu hình/hỗ trợ, nhưng không áp một quy tắc đó cho mọi loại queue và phiên bản.

### 3.2. Requeue=false: không nhất thiết mất, nhưng phải có DLX

**basicReject(tag, false)** và **basicNack(tag, false, false)** không tự đặt tên DLQ. Nếu queue nguồn có DLX hợp lệ, broker dùng cấu hình đó để dead-letter. Nếu không có DLX phù hợp, một message bị reject không requeue có thể bị loại bỏ.

### 3.3. BasicNack và BasicReject khác nhau ở multiple

**basicReject** chỉ nhắm một delivery. **basicNack** hỗ trợ cờ **multiple** để NACK một nhóm delivery chưa ACK trên cùng channel. Không dùng **multiple=true** nếu những delivery trước đó có thể vẫn đang xử lý trên các task song song.

### 3.4. ACK không bảo đảm exactly-once

Nếu handler commit database rồi kết nối mất trước khi broker nhận ACK, delivery có thể được giao lại. Nếu handler ACK trước khi ghi bền business, rồi process chết, công việc có thể không được giao lại. Vì vậy:

1. Xác định rõ **điểm ACK sau mốc xử lý/lưu bền**.
2. Đảm bảo **eventId nghiệp vụ ổn định**.
3. Dùng **idempotent consumer** hoặc unique constraint/inbox để tránh side effect trùng.
4. Không xem ACK là một transaction nguyên tử chung với database.

## 4. Những lý do RabbitMQ dead-letter một message

Dead-lettering không chỉ xảy ra khi consumer reject. Các tình huống phổ biến gồm:

| Nguyên nhân | Tình huống | Điều cần chú ý |
| --- | --- | --- |
| **Reject/NACK với requeue=false** | Handler không xử lý được payload, đã hết retry | Cần DLX, binding và DLQ hợp lệ |
| **TTL hết hạn** | Message chờ quá thời gian sống được cấu hình | Đến DLX theo cấu hình queue, không phải do consumer |
| **Queue vượt max-length / max-length-bytes** | Broker phải loại bớt message vì giới hạn queue | Hành vi theo overflow/policy; có thể dead-letter |
| **Quorum queue delivery limit** | Message bị redeliver vượt ngưỡng mà quorum queue hỗ trợ | Phụ thuộc phiên bản, policy, cấu hình và loại queue |

### 4.1. Không nhầm TTL của queue và TTL của message

RabbitMQ có thể áp **message TTL** cho message bằng chính sách/argument ở queue, hoặc dùng expiration property của message. Message hết TTL có thể bị dead-letter nếu queue có DLX. **Queue expires/x-expires** lại liên quan tới vòng đời **chính queue**, không đồng nghĩa mọi message được chuyển sang DLX khi queue bị xóa.

TTL cũng không hứa một callback Java sẽ chạy đúng thời điểm hết hạn. Tốc độ xử lý expired messages, đặc biệt khi có nhiều message với TTL khác nhau, có thể chịu ảnh hưởng bởi vị trí message trong queue và cơ chế broker.

### 4.2. Không phải mọi cơ chế overflow đều giống nhau

Khi queue đầy, RabbitMQ có nhiều chính sách như drop-head hoặc reject-publish, tùy queue type và cấu hình. Một số tình huống vượt max-length có thể dead-letter message bị loại khỏi queue; tình huống reject publish ở ingress lại có cơ chế báo lỗi/confirm khác.

Không mô tả đơn giản “hễ queue đầy thì mọi message tự chạy sang DLQ”. Hãy kiểm tra kiểu queue, overflow policy, limits, publisher confirms/returns và broker version.

### 4.3. Quorum queue có cơ chế delivery limit riêng

Quorum queue có thể hỗ trợ **delivery limit** và cách xử lý message vượt giới hạn theo policy. Tuy nhiên không nên tự cho rằng một **classic queue** cũng có cùng mặc định hoặc rằng mọi lần ứng dụng republish đều tăng cùng một counter broker. Cần kiểm tra queue type, broker version và cách message đang được redeliver/republish.

## 5. Cấu hình DLX: exchange, routing key, binding và queue

Giả sử ứng dụng có:

~~~text
Exchange chính : orders.events
Routing key    : orders.created
Main queue     : orders.created.q
DLX            : orders.dead.exchange
DL routing key : orders.failed
DLQ            : orders.created.dlq
~~~

Để dead-letter hoạt động cần:

1. Queue chính có cấu hình **dead-letter exchange** và tùy chọn **dead-letter routing key**.
2. **orders.dead.exchange** tồn tại và có kiểu exchange phù hợp.
3. **orders.created.dlq** tồn tại.
4. DLQ được **bind** vào DLX bằng key **orders.failed** nếu DLX là direct exchange.
5. Connection/vhost, permission và policy broker cho phép đường dead-letter.

~~~mermaid
flowchart TD
    P["Publisher"] --> X["Direct exchange<br/>orders.events"]
    X -->|"orders.created"| Q["orders.created.q"]
    Q --> C["Consumer"]
    C -->|"Reject / NACK<br/>requeue=false"| D["DLX<br/>orders.dead.exchange"]
    D -->|"orders.failed"| F["DLQ<br/>orders.created.dlq"]
~~~

### 5.1. x-dead-letter-exchange và x-dead-letter-routing-key

Hai argument/policy thường gặp:

- **x-dead-letter-exchange**: tên exchange nhận message bị dead-letter.
- **x-dead-letter-routing-key**: routing key broker dùng khi đưa message sang DLX.

Nếu **không đặt x-dead-letter-routing-key**, RabbitMQ thường sử dụng routing key gốc trong dead-lettering theo cơ chế áp dụng, với những khác biệt cần xem khi có nhiều route/binding. Nếu bạn có một DLQ riêng cần key đơn giản và ổn định, có thể cấu hình dead-letter routing key rõ ràng.

### 5.2. DLX không tự tạo DLQ

DLX là **một exchange** và vẫn áp dụng quy tắc binding như direct/topic/fanout exchanges khác. Nếu không có queue nhận, hoặc binding key sai, message có thể không được lưu ở DLQ như kỳ vọng.

### 5.3. DLX routing và business routing tách biệt

**orders.created** mô tả loại sự kiện nghiệp vụ; **orders.failed** là định tuyến kỹ thuật đến DLQ. Event vẫn cần giữ **eventId**, **eventType** và **schemaVersion** trong payload/properties. Không thay đổi eventId khi message được dead-letter chỉ vì routing key đổi.

## 6. Policy hay hardcode x-arguments trên queue?

RabbitMQ hỗ trợ cấu hình DLX qua **policy** của broker hoặc qua **x-arguments** trong queue declaration. Đây là lựa chọn kiến trúc, không chỉ cú pháp.

| Tiêu chí | RabbitMQ policy | x-arguments trong queue declaration |
| --- | --- | --- |
| Quyền sở hữu | Đội vận hành/platform thường quản lý | Ứng dụng thường khai báo qua Queue bean |
| Thay đổi khi queue đang có | Nhiều setting có thể thay bằng policy tùy loại tham số | Nhiều argument cố định, thay đổi có thể cần migration |
| Tính nhất quán | Áp dụng theo pattern/phạm vi policy | Gắn trực tiếp từng queue |
| Ưu tiên | Có quy tắc precedence của broker với arguments/policies | Explicit x-arguments có thể ghi đè policy tùy tham số |
| Rủi ro | Policy quá rộng ảnh hưởng nhiều queue | Sai argument gây PRECONDITION_FAILED khi redeclare |

**Khuyến nghị vận hành:** Khi production topology do platform quản lý, thường nên trao đổi với đội RabbitMQ về policy để tránh hardcode những thuộc tính khó thay đổi. Trong lab hoặc test cô lập, x-arguments giúp cấu hình dễ nhìn và tự chứa.

### 6.1. Vì sao đổi DLX cần kiểm tra queue đã tồn tại?

Một queue có tên **orders.created.q** và x-arguments đã được khai báo trên broker không nhất thiết chấp nhận một khai báo khác cùng tên nhưng khác thuộc tính. RabbitMQ có thể trả **PRECONDITION_FAILED** và đóng channel declare. Đừng coi thay đổi Java bean rồi restart ứng dụng là migration luôn thành công.

### 6.2. Policy không thay quyền truy cập

Trong một hệ thống nhiều virtual host, DLX, main queue và DLQ phải được khai báo/routing trong đúng **vhost**. Tài khoản cần các quyền phù hợp với thao tác khai báo và đường dead-letter theo quy tắc RabbitMQ. Cũng phải cân nhắc quyền đọc DLQ vì nó có thể chứa payload nhạy cảm.

## 7. Những loại retry dễ bị nhầm với dead-lettering

| Cơ chế | Khi nào nên dùng? | Điểm mạnh | Rủi ro |
| --- | --- | --- | --- |
| **Immediate requeue** | Sự cố rất ngắn và có cơ chế kiểm soát rõ | Không tạo message mới | Có thể tạo hot loop vô hạn |
| **In-process retry** | Lỗi transient ngắn, vài lần thử trong listener | Dễ có backoff/classifier | Giữ delivery unacked, tốn worker |
| **DLX + retry queue có TTL** | Muốn trì hoãn giao lại qua broker | Không cần giữ worker ngủ lâu | Dễ tạo vòng lặp nếu không có max attempts |
| **Republish sang retry exchange** | Cần điều khiển số lần/đích/cấu trúc message | Linh hoạt về routing | Phải xác nhận publish mới trước ACK gốc |
| **Durable inbox/job + scheduler** | Retry kéo dài và cần kiểm soát trạng thái | Dễ theo dõi attempt/nextRetryAt | Thêm DB, worker và logic phục hồi |
| **Final DLQ** | Dữ liệu lỗi hoặc hết retry cần điều tra | Cách ly khỏi luồng chính | Cần owner/retention/replay có kiểm soát |

### 7.1. Retry trong listener không dùng DLX

Với **Spring Retry/RetryTemplate**, listener có thể thử lại một lỗi hạ tầng trước khi trả kết quả callback. Delivery vẫn đang **unacked** trong thời gian backoff. Nếu xử lý thành công, consumer ACK; nếu hết attempts, policy có thể reject không requeue để đưa sang DLX.

### 7.2. Retry queue không phải final DLQ

**Retry queue** là nơi **tạm giữ** message rồi đưa lại vào main queue khi đến hạn. **Final DLQ** là nơi cách ly message **đã quyết định không tiếp tục xử lý tự động**. Có thể dùng các tên và exchange khác nhau để người vận hành không nhầm hai đích.

### 7.3. Một queue có nhiều consumer vẫn chỉ là một queue

Tăng consumer trên main queue có thể tăng throughput, nhưng không tự tạo một bản message cho mỗi hệ thống. Nếu Warehouse và Analytics đều cần OrderCreated, hãy có **hai queue riêng** bind vào exchange; DLQ/retry cũng nên được thiết kế theo từng nhóm xử lý để không lẫn ownership.

## 8. Ví dụ thực hành: OrderCreated bị lỗi đi vào DLQ

Ta xây dựng luồng tối thiểu nhưng có thể mở rộng:

~~~text
Producer
   -> orders.events (direct exchange)
   -> orders.created (routing key)
   -> orders.created.q (main queue)
   -> SimpleMessageListenerContainer (AUTO ACK)
   -> AMQP inbound adapter
   -> DirectChannel
   -> RetryTemplate (3 attempts cho lỗi transient)
   -> OrderProcessingService

Nếu thành công:
   container ACK

Nếu lỗi dữ liệu hoặc hết retry:
   container reject/NACK không requeue
   -> orders.dead.exchange
   -> orders.failed (dead-letter routing key)
   -> orders.created.dlq
~~~

**Quyết định thiết kế cho ví dụ:** ta dùng **AcknowledgeMode.AUTO** và giữ handler đồng bộ, để listener container chịu trách nhiệm settlement. Handler sẽ ném exception khi không xử lý được. **Không** đồng thời gọi basicAck/basicNack thủ công trong ví dụ AUTO này.

Ở bài riêng về manual acknowledgment, ứng dụng có thể tự ACK/NACK bằng channel và delivery tag. Hai mô hình có cùng mục tiêu kiểm soát delivery nhưng **không được trộn quyền sở hữu acknowledgment**.

### 8.1. Dependencies

Với Spring Boot, các dependency minh họa:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.retry</groupId>
        <artifactId>spring-retry</artifactId>
    </dependency>
</dependencies>
~~~

Sử dụng các phiên bản tương thích theo **Spring Boot dependency management/BOM**, Java 17 trở lên cho ví dụ record ở phần sau. Môi trường cần một RabbitMQ broker test, ConnectionFactory phù hợp và quyền tạo hoặc dùng topology. **Không hardcode credentials thật**.

### 8.2. Java configuration: topology chính và dead-letter

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersDlxTopology {

    public static final String EVENTS_EXCHANGE = "orders.events";
    public static final String EVENTS_KEY = "orders.created";
    public static final String MAIN_QUEUE = "orders.created.q";

    public static final String DEAD_EXCHANGE = "orders.dead.exchange";
    public static final String DEAD_KEY = "orders.failed";
    public static final String DEAD_QUEUE = "orders.created.dlq";

    @Bean
    public DirectExchange ordersEventsExchange() {
        return new DirectExchange(EVENTS_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersQueue() {
        return QueueBuilder.durable(MAIN_QUEUE)
            .deadLetterExchange(DEAD_EXCHANGE)
            .deadLetterRoutingKey(DEAD_KEY)
            .build();
    }

    @Bean
    public Binding ordersEventsBinding(
            @Qualifier("ordersQueue") Queue queue,
            @Qualifier("ordersEventsExchange") DirectExchange exchange) {

        return BindingBuilder.bind(queue)
            .to(exchange)
            .with(EVENTS_KEY);
    }

    @Bean
    public DirectExchange ordersDeadExchange() {
        return new DirectExchange(DEAD_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersDeadQueue() {
        return QueueBuilder.durable(DEAD_QUEUE).build();
    }

    @Bean
    public Binding ordersDeadBinding(
            @Qualifier("ordersDeadQueue") Queue queue,
            @Qualifier("ordersDeadExchange") DirectExchange exchange) {

        return BindingBuilder.bind(queue)
            .to(exchange)
            .with(DEAD_KEY);
    }
}
~~~

Hai **Queue beans** và hai **DirectExchange beans** tồn tại trong cùng ApplicationContext, nên ví dụ dùng **@Qualifier** tại các điểm inject để tránh phụ thuộc vào khả năng suy tên tham số hoặc chọn nhầm bean.

**Phạm vi:** Đây là topology dành cho broker test hoặc queue mới. Nếu main queue đã tồn tại không có DLX arguments, thay đổi declaration có thể thất bại. Trong production, phối hợp với đội vận hành và xem xét broker policy/migration.

### 8.3. Topology không tự bảo đảm một lần xử lý

- **Exchange durable** và **queue durable** mô tả khả năng tồn tại của tài nguyên.
- **Message persistence**, publisher confirms, loại queue và broker policy quyết định thêm những bảo đảm lưu bền của message.
- **Consumer ACK** xác nhận delivery; không chứng minh business side effect được thực hiện đúng một lần.
- **DLX/DLQ** giúp cách ly trong điều kiện phù hợp; không thay business transaction/idempotency.

Nếu các ứng dụng chia nhiều virtual host, các exchange và queue cùng tên ở hai virtual host khác nhau **không phải một topology chung**.

## 9. Listener container và ACK/NACK trong Spring Integration

Đối với AMQP inbound dạng message-driven, Spring AMQP listener container nhận delivery của RabbitMQ; Spring Integration inbound adapter tạo Spring Message và gửi vào MessageChannel.

~~~mermaid
flowchart LR
    MQ["orders.created.q"] --> LC["SimpleMessageListenerContainer"]
    LC --> IA["Amqp.inboundAdapter"]
    IA --> CH["ordersInput<br/>DirectChannel"]
    CH --> H["Service activator"]
    H --> DB[("Warehouse DB")]
    LC -. "ACK hoặc reject" .-> MQ
~~~

### 9.1. Cấu hình SimpleMessageListenerContainer

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersListenerConfig {

    @Bean("ordersListenerContainer")
    public SimpleMessageListenerContainer ordersListenerContainer(
            ConnectionFactory connectionFactory) {

        SimpleMessageListenerContainer container =
            new SimpleMessageListenerContainer(connectionFactory);

        container.setQueueNames(OrdersDlxTopology.MAIN_QUEUE);
        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(4);
        container.setPrefetchCount(10);
        container.setAcknowledgeMode(AcknowledgeMode.AUTO);

        // Luu y: fallback requeue policy, KHONG tu tao DLX/DLQ.
        container.setDefaultRequeueRejected(false);

        return container;
    }
}
~~~

**AcknowledgeMode.AUTO** trong Spring AMQP có nghĩa container chủ động ACK khi callback listener xử lý thành công hoặc reject/NACK theo policy khi thất bại. Nó **không** phải chế độ không cần explicit acknowledgment của RabbitMQ.

**defaultRequeueRejected(false)** khiến lỗi được container xử lý theo cơ chế mặc định sẽ không bị requeue mãi. Tuy nhiên phải kiểm tra **listener error handler**, các exception đặc biệt, errorChannel và cách lỗi lan về container; không kết luận mọi lỗi đều vào DLQ chỉ vì setter này có giá trị false.

### 9.2. Prefetch và concurrency tác động tới requeue

Ở mức hai consumer và prefetch 10, cửa sổ in-flight có thể khoảng **20 delivery chưa ACK** trong điều kiện QoS per-consumer thông dụng. Nếu container scale tới bốn consumer, cửa sổ lý thuyết tăng tới **40**.

Khi consumer chết hoặc connection đóng, những delivery chưa ACK có thể được giao lại. Prefetch cao có thể làm số message phải redeliver nhiều hơn. Đừng tăng prefetch chỉ để làm queue ready giảm trong khi handler chưa xử lý kịp.

### 9.3. SMLC và DMLC

**SimpleMessageListenerContainer** dùng **concurrentConsumers/maxConcurrentConsumers** và cơ chế điều chỉnh consumer của nó. **DirectMessageListenerContainer** có mô hình listener/threads khác và dùng **consumersPerQueue**. Cả hai có thể nhận delivery, áp dụng prefetch và ACK policy, nhưng không copy tham số của một container sang container còn lại mà không kiểm tra.

**DirectMessageListenerContainer không phải DirectChannel.** Một bên thuộc RabbitMQ consumer/client, một bên là Spring Integration MessageChannel đồng bộ.

## 10. Phân loại lỗi nghiệp vụ trước khi retry

Thay vì retry mọi RuntimeException, nên phân loại:

- **InvalidOrderEventException:** payload không đúng contract, không thể tự sửa sau vài lần nhận.
- **TransientOrderException:** lỗi tạm thời như DB timeout có khả năng hồi phục.
- **Lỗi cấu hình/quyền:** không được lặp vô hạn, cần cảnh báo và sửa nguyên nhân.
- **Kết quả transaction không rõ:** cần đối soát bằng eventId và idempotency trước khi thử lại.

### 10.1. Exception classes

~~~java
public class InvalidOrderEventException extends RuntimeException {

    public InvalidOrderEventException(String message) {
        super(message);
    }

    public InvalidOrderEventException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
public class TransientOrderException extends RuntimeException {

    public TransientOrderException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

### 10.2. RetryTemplate chỉ retry transient exception

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.retry.support.RetryTemplateBuilder;

@Configuration
public class OrdersRetryConfig {

    @Bean
    public RetryTemplate ordersRetryTemplate() {
        return new RetryTemplateBuilder()
            .maxAttempts(3)
            .exponentialBackoff(200L, 2.0, 1200L)
            .retryOn(TransientOrderException.class)
            .build();
    }
}
~~~

**maxAttempts(3)** thường bao gồm **lần thực hiện đầu tiên và tối đa hai lần thử lại**. Nếu một delivery bị redeliver sau crash, một vòng retry mới có thể được bắt đầu; RetryTemplate trong tiến trình không phải một bộ đếm bền vững cho toàn đời event.

Trong thời gian RetryTemplate đợi backoff, delivery có thể vẫn **unacked** và giữ quota prefetch. Nếu lỗi hạ tầng kéo dài nhiều phút, thay vì giữ nhiều listener threads ngủ, hãy cân nhắc một retry queue có delay hoặc durable job store.

### 10.3. Vì sao phải phân loại lỗi?

| Kết quả handler | Nhóm lỗi | Hành động hợp lý trong ví dụ |
| --- | --- | --- |
| Parse hợp lệ, business thành công | Thành công | AUTO ACK |
| JSON/text malformed | Lỗi dữ liệu cố định | Không retry, reject không requeue |
| SchemaVersion không hỗ trợ | Lỗi contract | Không requeue nóng; cách ly và cảnh báo |
| DB tạm không sẵn sàng | Transient | Retry giới hạn với backoff; hết retry thì dead-letter |
| Quyền database sai | Cấu hình cố định | Alert/sửa hạ tầng; tránh retry vô hạn |
| EventId đã xử lý | Duplicate hợp lệ | Bỏ qua side effect trùng, trả thành công để ACK |
| Broker connection mất gần ACK | Kết quả không rõ | Có thể redeliver; idempotency bảo vệ nghiệp vụ |

**Dead-letter không nên là phản xạ duy nhất với mọi lỗi.** Nếu DB gặp sự cố tạm thời, một **retry delay** có kiểm soát có thể giảm lượng message cần vận hành thủ công. Nếu lỗi schema cố định, tiếp tục retry lại cùng dữ liệu sai thường không có ích.

## 11. Service nghiệp vụ: validation, transaction và idempotency

Để minh họa xử lý thật thay vì chỉ in log, ta dùng một event OrderCreated và service cập nhật projection Warehouse. Mục tiêu là **một eventId chỉ áp dụng side effect một lần**, ngay cả khi broker giao lại delivery.

### 11.1. Record và parser

~~~java
public record OrderCreatedEvent(
    String eventId,
    String orderId,
    long totalVnd
) {}
~~~

~~~java
public final class OrderEventParser {

    private OrderEventParser() {}

    public static OrderCreatedEvent parse(String payload) {
        if (payload == null || payload.length() > 1024) {
            throw new InvalidOrderEventException(
                "Payload empty or too large");
        }

        String[] fields = payload.split("\\|", -1);
        if (fields.length != 3
                || !fields[0].matches("[A-Za-z0-9_-]{1,80}")
                || !fields[1].matches("[A-Za-z0-9_-]{1,80}")) {
            throw new InvalidOrderEventException(
                "Expected eventId|orderId|totalVnd");
        }

        final long total;
        try {
            total = Long.parseLong(fields[2]);
        } catch (NumberFormatException ex) {
            throw new InvalidOrderEventException(
                "totalVnd is not an integer", ex);
        }

        if (total <= 0) {
            throw new InvalidOrderEventException(
                "totalVnd must be positive");
        }
        return new OrderCreatedEvent(fields[0], fields[1], total);
    }
}
~~~

Đây là **payload text mẫu** để tập trung vào requeue. Production nên dùng JSON/Avro/Protobuf có schemaVersion, validation và giới hạn kích thước. Không tự giả định mọi AMQP inbound message đều là String phân cách bằng dấu gạch đứng.

### 11.2. Repository contract

~~~java
public interface WarehouseProjectionRepository {

    // Atomic insert with UNIQUE(consumer_name, event_id).
    // Returns false when the event was already processed.
    boolean insertInboxIfAbsent(String consumerName, String eventId);

    // Must participate in the same database transaction.
    void updateOrderProjection(String orderId, long totalVnd);
}
~~~

Đây là interface **cần tự triển khai** bằng JDBC/JPA/driver phù hợp. Cần bảng inbox, unique constraint và transaction manager; Spring không tự tạo implementation chỉ vì method có tên trên.

### 11.3. Business service đồng bộ

~~~java
import org.springframework.dao.TransientDataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProcessingService {

    private final WarehouseProjectionRepository repository;

    public OrderProcessingService(
            WarehouseProjectionRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void process(String payload) {
        OrderCreatedEvent event = OrderEventParser.parse(payload);

        try {
            boolean firstTime = repository.insertInboxIfAbsent(
                "warehouse", event.eventId());

            if (!firstTime) {
                return; // Duplicate: no repeated side effect.
            }
            repository.updateOrderProjection(
                event.orderId(), event.totalVnd());
        } catch (TransientDataAccessException ex) {
            throw new TransientOrderException(
                "Temporary database failure", ex);
        }
    }
}
~~~

Các điều kiện quan trọng:

- OrderProcessingService được gọi qua **Spring bean/proxy** để transaction advice hoạt động.
- Inbox insert và update projection phải cùng transaction nếu cùng database.
- Unique constraint chống race giữa các consumer; **check-then-insert** đơn thuần không đủ.
- Khi update lỗi, transaction rollback cả dấu inbox, cho phép retry đúng.
- Khi DB commit rồi ACK thất bại, redelivery thấy eventId đã có và bỏ qua side effect.

**@Transactional không tự tạo transaction nguyên tử giữa database và RabbitMQ ACK**. Nếu handler gọi API ngoài hoặc phát Kafka/JMS trong lúc transaction chạy, side effect đó cần thiết kế idempotency/đối soát riêng.

## 12. Spring Integration Java DSL: inbound → retry → DLX

Flow nối container **ordersListenerContainer** với **Amqp.inboundAdapter**. Handler chạy đồng bộ trong listener callback; container AUTO ACK nếu thành công, hoặc reject theo chính sách khi thất bại.

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class OrdersInboundFlowConfig {

    @Bean
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersInboundFlow(
            @Qualifier("ordersListenerContainer")
            SimpleMessageListenerContainer container,
            RetryTemplate ordersRetryTemplate,
            OrderProcessingService orderProcessingService) {

        return IntegrationFlow
            .from(Amqp.inboundAdapter(container))
            .channel("ordersInput")
            .handle(String.class, (payload, headers) -> {
                try {
                    ordersRetryTemplate.execute(context -> {
                        orderProcessingService.process(payload);
                        return null;
                    });
                } catch (RuntimeException ex) {
                    // Permanent error OR transient retries exhausted.
                    throw new AmqpRejectAndDontRequeueException(
                        "OrderCreated cannot be processed", ex);
                }
                return null;
            })
            .get();
    }
}
~~~

### 12.1. Lưu ý exception translation

Exception từ Spring Integration handler có thể được bọc trong **MessagingException** trước khi quay về Spring AMQP listener container. Container có cơ chế xác định requeue, nhưng chi tiết phụ thuộc phiên bản và error handler.

Trong mẫu này, **setDefaultRequeueRejected(false)** là chính sách dự phòng để tránh requeue vô hạn và **AmqpRejectAndDontRequeueException** thể hiện rõ yêu cầu không requeue. **Phải kiểm thử với RabbitMQ thật** để chắc rằng exception đã lan qua adapter và container thực sự reject/NACK với kết quả mong muốn.

**Không tự basicNack trong handler này:** container đang ở **AUTO**. Nếu chuyển sang MANUAL, phải thiết kế lại chủ sở hữu ACK/NACK và kiểm chứng không có double settlement.

### 12.2. Hành vi kỳ vọng theo loại lỗi

| Kết quả | RetryTemplate | Handler | RabbitMQ |
| --- | --- | --- | --- |
| Business thành công | Hoàn tất | Trả về bình thường | Container AUTO ACK |
| EventId đã xử lý | Không lặp side effect | Trả về bình thường | Container AUTO ACK |
| InvalidOrderEventException | Không retry | Ném reject-not-requeue | Dead-letter nếu topology hợp lệ |
| TransientOrderException hồi phục trong ba attempts | Retry có giới hạn | Cuối cùng bình thường | Container AUTO ACK |
| TransientOrderException hết attempts | Thất bại | Ném reject-not-requeue | Dead-letter nếu topology hợp lệ |
| Converter lỗi trước flow | Handler có thể không chạy | Error handler của container | Kiểm chứng reject/requeue/DLQ riêng |

### 12.3. Vì sao dùng DirectChannel?

**DirectChannel** gọi handler đồng bộ trong đường xử lý từ listener. Khi OrderProcessingService hoàn tất transaction rồi handler return, container có cơ sở ACK theo listener outcome.

Nếu thay bằng **ExecutorChannel**, listener có thể trả về sau khi giao task cho executor **trước khi business worker hoàn tất**. Nếu container AUTO ACK ở thời điểm đó, broker không còn cơ hội redelivery do lỗi bất đồng bộ phía sau.

**QueueChannel** mặc định cũng không tự mang tính bền vững. Nếu bắt buộc tách xử lý dài, có thể chọn lưu **durable inbox/job** bằng transaction trước ACK, sau đó worker xử lý bền vững và idempotent.

### 12.4. Converter và hợp đồng payload

Flow giả định SimpleMessageConverter nhận String dạng text/plain. Nếu producer gửi JSON hoặc binary, inbound adapter có thể phát byte[] hay DTO; handler yêu cầu kiểu String khi đó không còn phù hợp.

Cần kiểm tra contentType, charset, schemaVersion, header mapper và MessageConverter ở **biên AMQP**. Khi converter ném lỗi trước khi có Spring Message, lỗi không nhất thiết đi qua đoạn handler bên trên; phải kiểm tra container error handler.

## 13. Gửi thử và quan sát đường dead-letter

Với RabbitTemplate được cấu hình cùng broker/vhost:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class OrdersTestPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrdersTestPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendValid() {
        rabbitTemplate.convertAndSend(
            OrdersDlxTopology.EVENTS_EXCHANGE,
            OrdersDlxTopology.EVENTS_KEY,
            "evt-1001|O-1001|150000");
    }

    public void sendInvalid() {
        rabbitTemplate.convertAndSend(
            OrdersDlxTopology.EVENTS_EXCHANGE,
            OrdersDlxTopology.EVENTS_KEY,
            "event-without-required-fields");
    }
}
~~~

Với event hợp lệ, kỳ vọng: broker route main queue, inbound flow parse và cập nhật projection, transaction commit, container AUTO ACK và DLQ không nhận message này.

Với payload sai: parser ném InvalidOrderEventException, RetryTemplate không retry, handler ném reject-not-requeue, container từ chối delivery, broker chuyển qua DLX/DLQ **nếu** cấu hình dead-letter hoạt động.

### 13.1. Đọc DLQ chỉ ở môi trường cô lập

Trong một integration test, RabbitTemplate.receiveAndConvert có thể lấy message khỏi DLQ để xác minh:

~~~java
Object dead = rabbitTemplate.receiveAndConvert(
    OrdersDlxTopology.DEAD_QUEUE, 2000L);

// Mong doi: String "event-without-required-fields",
// khi converter text phu hop va khong co consumer khac.
~~~

**receive không phải peek**: thao tác này tiêu thụ message. Chỉ chạy trên broker/queue test; không dùng nó để kiểm tra DLQ production nếu không muốn thay đổi dữ liệu đang chờ điều tra.

### 13.2. Test retry trước khi dead-letter

Có thể dùng repository test giả lập:

- Attempt 1 ném TransientOrderException.
- Attempt 2 thành công.
- Xác minh handler return bình thường và container ACK; DLQ không nhận message.

Khi cả ba attempts đều lỗi:

- Handler ném reject-not-requeue.
- Broker dead-letter tới DLQ theo topology.
- Log/metric ghi nhận **retry exhausted** để phân biệt với lỗi payload.

**Một delivery có thể được thử xử lý nhiều lần trong listener**, nên số lần callback từ RabbitMQ không phải bằng chứng RetryTemplate chỉ chạy một attempt.

### 13.3. Test nên dùng topology riêng

Nếu một application khác đang tiêu thụ cùng queue, consumer cạnh tranh có thể lấy message trước test. Hãy tạo queue/vhost hoặc broker test riêng. Nếu queue đã có message cũ, cần cô lập dữ liệu test và phân biệt eventId để kết quả xác định.

## 14. Retry queue có TTL: trì hoãn nhưng không được lặp vô hạn

Khi downstream hỏng vài phút, giữ delivery unacked trong listener để RetryTemplate sleep quá lâu không phải lúc nào cũng hợp lý. Một thiết kế thường gặp là **retry queue có TTL**:

~~~mermaid
flowchart TD
    MQ["orders.created.q<br/>main queue"] --> C["Consumer"]
    C -->|"Thành công"| ACK["ACK"]
    C -->|"Lỗi transient cần trì hoãn"| RX["orders.retry.exchange"]
    RX --> RQ["orders.retry.q<br/>message TTL"]
    RQ -->|"TTL hết hạn, dead-letter"| EX["orders.events"]
    EX --> MQ
    C -->|"Lỗi cố định / hết lượt"| DX["orders.dead.exchange"]
    DX --> DQ["orders.created.dlq"]
~~~

**Hai đường rẽ khác nhau:** error cố định/hết retry phải đi tới **final DLQ**; lỗi transient có thể đi tới **retry queue** để thử sau. Việc chia nhánh có thể do ứng dụng republish, broker policy hoặc các queue trung gian. Nếu mọi NACK không requeue từ main queue đều đi vào retry queue và message đó luôn lỗi, nó có thể quay về main queue mãi.

### 14.1. Cấu hình một retry queue riêng

Ví dụ Java configuration sau là **thành phần bổ sung tùy chọn**: tạo exchange/queue/binding phục vụ một delay đơn giản.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersDelayedRetryTopology {

    public static final String RETRY_EXCHANGE = "orders.retry.exchange";
    public static final String RETRY_QUEUE = "orders.retry.q";
    public static final String RETRY_KEY = "orders.retry";

    @Bean
    public DirectExchange ordersRetryExchange() {
        return new DirectExchange(RETRY_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersRetryQueue() {
        return QueueBuilder.durable(RETRY_QUEUE)
            .ttl(30_000)
            .deadLetterExchange(OrdersDlxTopology.EVENTS_EXCHANGE)
            .deadLetterRoutingKey(OrdersDlxTopology.EVENTS_KEY)
            .build();
    }

    @Bean
    public Binding ordersRetryBinding(
            @Qualifier("ordersRetryQueue") Queue queue,
            @Qualifier("ordersRetryExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
            .to(exchange)
            .with(RETRY_KEY);
    }
}
~~~

**Ý nghĩa:** Message đi vào retry queue sẽ chờ một khoảng thời gian chịu chi phối bởi TTL và broker. Khi hết TTL, message có thể dead-letter trở lại exchange chính với key orders.created. **TTL không phải đồng hồ đảm bảo giao lại chính xác tại từng mili-giây**; còn phụ thuộc broker scheduling, queue state, load và cách expiration được xử lý.

### 14.2. Đưa message vào retry queue bằng cách nào?

Mã ở trên **chưa tự đưa message từ main queue vào retry queue**. Cần một trong các phương án thiết kế:

**Phương án A — DLX của main queue trỏ sang retry exchange:** broker chuyển các message bị reject không requeue vào retry queue. Tuy nhiên mọi message bị dead-letter vì lý do phù hợp sẽ đi theo đường này; nếu không có cơ chế phân loại và giới hạn số lượt, message lỗi schema có thể quay vòng vô hạn. Khi chọn cách này phải **thay đổi topology main queue có chủ đích**, không đồng thời giữ hai khai báo main queue cùng tên nhưng khác DLX.

**Phương án B — Application republish sang retry exchange:** handler phân loại lỗi transient, publish **một message mới** sang retry exchange theo retry key và chỉ ACK nguồn khi đã đạt mốc tiếp nhận bền vững theo hợp đồng. Khi không thể chắc chắn lần republish thành công, phải xử lý trạng thái UNKNOWN, idempotency và khả năng duplicate.

**Phương án C — Durable inbox/job scheduler:** handler lưu job vào database trong transaction, ACK sau mốc lưu bền, worker riêng retry theo nextRetryAt. Phù hợp khi cần theo dõi attempts, delay và kết quả dài hạn.

**Không** copy cấu hình main queue đang khai báo deadLetterExchange = orders.dead.exchange rồi kỳ vọng một lệnh NACK tự chuyển sang orders.retry.exchange. Main queue có một cấu hình dead-letter route đang áp dụng; nếu cần chia đường, phải thiết kế một cơ chế routing hoặc republish rõ ràng.

### 14.3. Vấn đề TTL, queue head-of-line và thứ tự

TTL của message có thể chịu ảnh hưởng bởi cơ chế broker xác định message đã hết hạn. Nếu nhiều message có TTL khác nhau trong cùng queue, quá trình rời queue không nên được xem là bộ hẹn giờ chuẩn xác từng message trong mọi trường hợp.

Đối với nhiều mức backoff, có thể dùng những retry queues khác nhau theo khoảng thời gian (ví dụ 10 giây, một phút, năm phút) hoặc một scheduler bền vững. Mỗi phương án cần đo memory/disk, queue count, throughput và khả năng xử lý message lỗi hàng loạt.

### 14.4. Tránh dead-letter cycle

~~~text
main queue
  -> DLX
  -> retry queue có TTL
  -> DLX
  -> main queue
  -> ...
~~~

Nếu không có **attempt limit**, **final DLQ** và người sở hữu việc kết thúc vòng lặp, một message lỗi cố định có thể đi qua chu trình này nhiều lần. RabbitMQ có một số cơ chế phát hiện vòng dead-letter và xử lý phụ thuộc kiểu chu trình, lý do dead-letter, phiên bản; **không nên dựa vào broker tự cắt mọi vòng lặp** thay chính sách retry của ứng dụng.

### 14.5. Retry queue không bảo đảm republish đến broker đích

Nếu worker cần chủ động republish từ queue A sang retry exchange, có ít nhất hai hành động: **publish message mới** và **ACK message gốc**. Chúng không tự thuộc một transaction nguyên tử với database/business. Một cách tiếp cận thận trọng:

1. Giữ **eventId** ổn định, có thể tạo attemptId riêng.
2. Publish sang retry exchange với **publisher confirms** và xử lý **returns** nếu cần phát hiện không route được.
3. Chỉ ACK delivery gốc sau khi đạt mốc được chấp nhận trong thiết kế.
4. Nếu publish mới **UNKNOWN**, không suy ra chắc chắn chưa gửi; phải có khả năng đối soát/retry idempotent.
5. Consumer về sau phải chống trùng vì một event có thể xuất hiện hai lần trong trường hợp lỗi kết nối.

Đừng hiểu publisher confirm ACK là dấu hiệu consumer retry đã xử lý xong; nó chỉ là xác nhận ở cấp broker/publish.

## 15. X-death và thông tin lịch sử dead-letter

RabbitMQ có thể thêm/cập nhật metadata dead-letter, thường gồm **x-death** hoặc các thông tin **x-first-death** / **x-last-death** tương ứng theo phiên bản và policy. Những thông tin đó giúp điều tra:

- Queue nào đã dead-letter message.
- Lý do, ví dụ **rejected**, **expired**, **maxlen** hoặc **delivery_limit** trong bối cảnh được hỗ trợ.
- Exchange và routing thông tin liên quan.
- Thống kê/lịch sử được broker duy trì theo định dạng của phiên bản.

Ví dụ ý nghĩa logic:

~~~text
eventId = evt-1001
dead-letter history:
  queue = orders.created.q
  reason = rejected
  count = ... (theo broker representation)
~~~

**Không tự tạo x-death trong payload và coi đó là chứng cứ đáng tin.** Metadata có định dạng và quy tắc cập nhật do RabbitMQ quản lý; một lần republish bởi ứng dụng có thể làm thay đổi/loại bỏ metadata cũ. Với các phiên bản broker mới, việc chấp nhận các header x-death được client gửi cũng có thể bị hạn chế.

### 15.1. Vì sao x-death count không phải luôn là số lần business đã xử lý?

- Một message có thể được handler retry **ba lần trong một listener callback** rồi chỉ dead-letter **một lần**.
- Message có thể được republish với body mới nhưng vẫn là cùng eventId.
- Một message có thể được dead-letter qua nhiều queue khác nhau với các lý do khác nhau.
- Broker có thể gộp/biểu diễn lịch sử theo nhóm queue/reason, không phải lưu một dòng cho mọi business attempt.

Vì vậy không suy ra **tổng số lần xử lý nghiệp vụ = một trường count bất kỳ**. Nếu yêu cầu giới hạn tổng attempts qua restart/requeue, dùng **attempt counter bền vững** được cập nhật có kiểm soát hoặc cơ chế delivery limit của queue type đã được kiểm chứng.

### 15.2. Header metadata không phải quyền truy cập

Không dùng một header **retryCount=0** do producer ngoài gửi để luôn reset số lần thử. Nếu application cho phép replay, phải kiểm soát quyền replay và tính toàn vẹn của eventId/schema, không để client tùy ý yêu cầu vô hạn.

### 15.3. Dead-letter routing key không giống original business key

Một message ban đầu đi theo **orders.created** rồi dead-letter theo **orders.failed**. Consumer DLQ cần biết **eventType=ORDER_CREATED** và eventId từ payload/headers nghiệp vụ, không chỉ nhìn routing key của DLX rồi suy ra business event là “FAILED” hay đổi event type.

## 16. Giới hạn độ tin cậy của dead-lettering

DLX/DLQ rất hữu ích nhưng **không nên được mô tả là một phép chuyển message luôn nguyên tử và không bao giờ mất**. Broker thực hiện dead-letter publish theo những cơ chế và mức bảo đảm phụ thuộc **queue type, broker version và cấu hình**.

### 16.1. Có thể xảy ra điều gì?

- DLX không tồn tại hoặc bị xóa sau khi queue được khai báo.
- DLX tồn tại nhưng **không có binding nào nhận** message theo routing key.
- Queue đích không còn khả dụng hoặc áp dụng policy overflow/TTL đặc biệt.
- Có lỗi quyền/kết nối nội bộ hoặc tài nguyên broker quá tải.
- Trong một số cấu hình dead-lettering, việc chuyển không cung cấp cùng mức xác nhận/lưu bền với một application publisher có confirms.

**Kết luận:** chỉ gọi basicReject không requeue rồi thấy lệnh Java thành công **chưa chứng minh DLQ đã lưu message**. Cần kiểm thử và giám sát kết quả định tuyến, broker logs, queue metrics và mức bảo đảm của loại queue đang dùng.

### 16.2. Quorum queue và at-least-once dead-lettering

Một số phiên bản RabbitMQ hỗ trợ mô hình **at-least-once dead-lettering** cho **quorum queues** khi đáp ứng cấu hình yêu cầu. Cơ chế này khác với hành vi dead-letter thông thường và có ràng buộc về queue/policy/tài nguyên.

Nếu ứng dụng có SLA không mất message dead-letter, nên **đánh giá tính năng phù hợp ở phiên bản RabbitMQ thực tế**, thiết kế quyền, policy, monitoring và test failover. Không khẳng định mọi classic queue hoặc mọi quorum queue mặc nhiên có at-least-once dead-letter delivery.

### 16.3. DLQ cũng phải có retention và capacity

DLQ có thể đầy, chứa payload nhạy cảm, có chính sách TTL/overflow hoặc bị consumer replay lấy mất message. Không coi DLQ là nơi lưu vô hạn chắc chắn không mất dữ liệu. Cần:

- Owner vận hành rõ ràng.
- Quyền đọc/ghi và audit.
- Capacity/retention.
- Cảnh báo số lượng và tuổi message.
- Chính sách backup/export nếu nghiệp vụ yêu cầu.
- Replay được kiểm soát và test khả năng xử lý trùng.

### 16.4. Nguyên tắc không sửa lỗi bằng cách tăng prefetch

Nếu message liên tục bị reject rồi quay lại queue, tăng prefetch/concurrency có thể **tăng số retry và tốc độ lỗi**, không sửa schema hoặc database. Tối ưu thông lượng phải đi sau việc kiểm soát error classification, retry budget và DLQ correctness.

## 17. AUTO ACK, MANUAL ACK và errorChannel

Trong Spring AMQP + Spring Integration, một lần xử lý lỗi có thể đi qua nhiều lớp:

~~~mermaid
flowchart TD
    B["RabbitMQ delivery"] --> C["MessageConverter"]
    C -->|"Decode OK"| A["AMQP inbound adapter"]
    C -->|"Decode lỗi"| CE["Listener error handler"]
    A --> CH["MessageChannel"]
    CH --> H["Handler / RetryTemplate"]
    H -->|"Success"| ACK["AUTO ACK"]
    H -->|"Exception lan về container"| REJ["Reject / NACK theo policy"]
    CH -. "ErrorMessage nếu được cấu hình" .-> EC["Integration errorChannel"]
    EC --> P["Error flow / logging"]
~~~

### 17.1. Lỗi MessageConverter xảy ra trước handler

Nếu AMQP body bị lỗi JSON hoặc type mapping, converter có thể ném exception trước khi Spring Integration tạo được Message cho flow. Khi đó **service activator và RetryTemplate trong ví dụ mục 12 không chạy**.

Cần kiểm tra **listener error handler**, fatal exception classification và AcknowledgeMode. Trong một số phiên bản/cấu hình, lỗi conversion fatal có thể bị reject không requeue. Nhưng **không hứa mọi lỗi converter đều tự động vào DLQ**, vì DLX topology và chính sách xử lý exception vẫn có vai trò riêng.

### 17.2. errorChannel có thể hấp thụ exception

Khi lỗi handler được đưa vào errorChannel và error flow kết thúc thành công, listener container có thể không thấy exception như khi handler ném trực tiếp.

**Hậu quả có thể có:**

- **AUTO:** container có thể ACK nếu callback được coi là hoàn tất.
- **MANUAL:** nếu error flow không settle delivery, message có thể nằm unacked.
- Nếu error flow thực hiện ACK/NACK và một nơi khác cũng làm, có thể xảy ra double acknowledgment.

Vì thế phải xác định **ai sở hữu quyết định settlement cuối cùng** cho từng nhánh. Không chỉ log exception rồi trả về bình thường mà chưa biết broker đã ACK/NACK hay chưa.

### 17.3. Một ví dụ điều tra lỗi không vào DLQ

Một application có:

~~~text
Listener AUTO
  -> inbound adapter
  -> DirectChannel
  -> handler ném IllegalArgumentException
  -> custom errorChannel
  -> error handler ghi log rồi return
~~~

Nếu custom error handler được cấu hình làm mất đường exception lan về container, broker có thể nhận ACK thay vì reject. Muốn có **DLQ cho lỗi dữ liệu**, phải kiểm tra hợp đồng error flow: có return thông thường không, có ném lại exception không, và container thực sự gửi loại ACK/NACK nào.

### 17.4. MANUAL ACK cần một chủ sở hữu

Nếu chọn MANUAL, handler có thể lấy channel/delivery tag qua các **AMQP headers** được expose bởi endpoint phù hợp và thực hiện:

~~~java
// Chi minh hoa lenh settle trong MANUAL ACK.
// Channel va tag phai thuoc CHINH delivery nay.
channel.basicAck(deliveryTag, false);           // Success
channel.basicNack(deliveryTag, false, true);    // Requeue
channel.basicReject(deliveryTag, false);        // Dead-letter if DLX
~~~

**Chỉ một trong các lệnh trên được dùng cho cùng delivery.** Delivery tag thuộc channel, không thể tái sử dụng trên channel khác. Đừng chuyển native Channel hoặc tag tùy ý qua thread bất đồng bộ/JSON/HTTP rồi kỳ vọng ACK vẫn hợp lệ sau reconnect.

Đừng dùng đoạn MANUAL này đồng thời với container AUTO ở ví dụ mục 9–12. Đây là **phương án khác**, cần cấu hình AcknowledgeMode.MANUAL, kiểm thử header mapping và viết lại các đường settlement.

### 17.5. ExecutorChannel làm thay đổi ranh giới ACK

Với DirectChannel, handler được gọi đồng bộ; lỗi có khả năng lan về listener trước khi AUTO ACK. Với ExecutorChannel:

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant L as Listener AUTO
    participant E as ExecutorChannel
    participant W as Async worker
    L->>E: Send Spring Message
    E-->>L: Executor nhận task
    L-->>B: ACK theo listener outcome
    E->>W: Task chạy sau đó
    W--xW: Business processing fails
    Note over B,W: Delivery có thể đã ACK trước khi lỗi business xảy ra
~~~

Nếu business xử lý lâu và cần bất đồng bộ, cân nhắc **ghi durable inbox/job trước ACK**, rồi worker xử lý sau với trạng thái và retry riêng. QueueChannel mặc định trong bộ nhớ **không phải durable inbox**.

## 18. Redelivery, idempotency và transaction

**Dead-lettering không sửa được vấn đề xử lý trùng**. Một delivery có thể được giao lại vì:

- Consumer NACK requeue=true.
- Consumer chết trước ACK.
- Connection/channel đóng khi còn delivery unacked.
- Producer phát lại sau khi mất publisher confirm.
- Một operator replay từ DLQ hoặc retry queue.

### 18.1. Hai khoảng crash quan trọng

~~~text
Trường hợp A:
  Delivery nhận -> ACK -> process crash -> DB chưa commit
  => Có nguy cơ mất tác động nghiệp vụ.

Trường hợp B:
  Delivery nhận -> DB commit -> process crash trước ACK
  => Broker có thể giao lại và side effect có nguy cơ bị lặp.
~~~

Giữ điểm ACK **sau mốc xử lý/lưu bền** để giảm rủi ro A, và dùng **unique eventId/inbox** để ngăn side effect trùng ở B.

### 18.2. EventId khác routing key, delivery tag và x-death

| Dữ liệu | Chức năng | Có dùng làm idempotency key? |
| --- | --- | --- |
| **eventId** | Định danh sự kiện nghiệp vụ ổn định | Có, nếu contract đảm bảo tính duy nhất/phạm vi |
| **routingKey** | Định tuyến tới queue qua exchange | Không; nhiều sự kiện chung một key |
| **deliveryTag** | ACK/NACK trên một AMQP channel | Không; chỉ hợp lệ trong channel đó |
| **redelivered flag** | Gợi ý message đã được broker giao trước | Không; chưa chứng minh business commit |
| **x-death metadata** | Mô tả lịch sử dead-letter | Không; không phải danh tính nghiệp vụ |
| **CorrelationData ID** | Liên kết một lần publisher confirm với attempt | Không mặc nhiên; retry có thể sinh attemptId mới |

### 18.3. Unique constraint phải được thiết kế đúng

Một bảng inbox có thể dùng khóa:

~~~text
processed_events
  consumer_name VARCHAR
  event_id      VARCHAR
  payload_hash  VARCHAR
  processed_at  TIMESTAMP

UNIQUE (consumer_name, event_id)
~~~

Nếu eventId đã tồn tại, consumer không lặp side effect. Nếu eventId trùng nhưng payload_hash khác, cần báo conflict/điều tra chứ không mặc nhiên bỏ qua như duplicate hợp lệ.

**Đừng làm:** kiểm tra tồn tại eventId rồi update DB mà không có transaction và unique constraint. Khi hai consumer xử lý đồng thời, cả hai có thể thấy chưa tồn tại và cùng thực hiện side effect.

### 18.4. Gắn retry với nghiệp vụ ngoài database

Nếu consumer gọi HTTP API thanh toán hoặc phát Kafka/JMS, transaction JDBC của inbox không tự bao phủ side effect ngoài. Có thể cần idempotency key trên API, transactional outbox, trạng thái workflow và đối soát khi timeout gần lúc hệ thống đích commit.

Đừng tuyên bố exactly-once end-to-end chỉ vì đã bật DLX, queue durable hoặc AUTO/MANUAL ACK.

## 19. Lỗi vận hành thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Việc cần kiểm tra |
| --- | --- | --- |
| Message sai bị giao lặp liên tục | NACK requeue=true; thiếu retry limit/backoff | Log requeue, error classification, broker redelivery |
| Message bị reject nhưng DLQ rỗng | DLX không tồn tại, binding sai, thiếu quyền, queue đích lỗi | Topology thực tế, broker logs, routing key |
| Message vào DLQ quá nhanh | defaultRequeueRejected=false nhưng chưa có retry transient | Exception classes, retry advice, downstream |
| Queue ready tăng đều | Consumer chậm/offline; flow nghẽn downstream | Consumer count, ACK rate, handler latency |
| Queue unacked cao | Handler giữ delivery lâu, RetryTemplate sleep, ACK thiếu | Prefetch, thread dump, DB latency, MANUAL ACK |
| DLQ tăng sau deploy | Schema/MessageConverter thay đổi | contentType, schemaVersion, DTO compatibility |
| DLQ liên tục quay về main | Retry queue TTL/DLX loop không có điểm kết thúc | Retry topology, x-death, attempt budget |
| Broker publish confirm tốt nhưng consumer không xử lý | Message route sai hoặc consumer lỗi | Returns, queue ready/unacked, consumer DLQ |
| Message trùng sau restart | Redelivery/producer retry | Inbox unique constraint, transaction order |
| Retry queue trả message trễ | TTL semantics, queue load, nhiều TTL khác nhau | Queue policy, expiration, broker metrics |
| PRECONDITION_FAILED khi khởi động | Queue bean x-arguments khác queue đã tồn tại | Policy, queue type, DLX arguments, migration |

### 19.1. Cách tìm nguyên nhân một message biến mất

Hãy đặt các câu hỏi theo thứ tự:

1. Producer đã publish vào **exchange và routing key nào**?
2. Có **publisher confirm/return** tương ứng không?
3. Broker có **binding** tới main queue tại thời điểm đó không?
4. Delivery có tới consumer, có **ACK/NACK/reject** nào không?
5. Nếu reject không requeue, main queue có DLX nào đang được áp dụng?
6. DLX có route tới DLQ hay không, DLQ có TTL/overflow policy gì?
7. Nếu đã replay, message có eventId gì; consumer có bỏ qua duplicate không?

Đừng bắt đầu bằng “tăng số consumer” khi chưa biết message mất **trước route**, **tại consumer ACK** hay **trong dead-lettering**.

### 19.2. Thời điểm xác nhận business

Một message ở DLQ thường có nghĩa **chưa được xử lý thành công theo đường chính**, nhưng phải xem policy cụ thể; nó không tự chứng minh dữ liệu business đã rollback. Nếu handler đã commit DB rồi một lỗi xảy ra trước ACK, broker có thể redeliver và sau đó message đi DLQ do lỗi thứ hai. Cần đối soát bằng **eventId/business state**, không chỉ vị trí hiện tại của message.

## 20. Quan sát, cảnh báo và ownership của DLQ

Một hệ thống có DLQ nhưng không ai xem, không có retention và không có quy trình replay vẫn có thể mất tính chính xác nghiệp vụ theo thời gian.

| Lớp | Metric nên theo dõi | Câu hỏi trả lời |
| --- | --- | --- |
| Producer | publish attempts, confirms, returns, unknown outcomes | Message đã vào broker/route chưa? |
| Main queue | ready, unacked, oldest age, consumer count | Consumer có đang theo kịp không? |
| Consumer | ACK/NACK/reject/requeue, handler latency, error classes | Vì sao message không hoàn tất? |
| Retry | attempt count, retry exhausted, backoff duration, delayed queue depth | Có lặp quá nhiều hay chờ quá lâu không? |
| DLX/DLQ | dead-letter ingress, DLQ depth/age, DLQ replay rate | Bao nhiêu message đang cần điều tra? |
| Database/inbox | commits, rollbacks, duplicate ignored, payload conflicts | Business side effect có đúng không? |
| Runtime | connections/channels, threads, memory, GC, reconnect | Có quá tải hoặc sự cố tài nguyên không? |

**Tên metric cụ thể** phụ thuộc RabbitMQ management, Spring AMQP, Micrometer và instrumentation của ứng dụng. Những mục ở bảng là yêu cầu quan sát, không phải lời hứa framework tự xuất tất cả tên tương ứng.

### 20.1. Log an toàn cho một message lỗi

~~~text
queue=orders.created.q
eventId=evt-1001
eventType=ORDER_CREATED
schemaVersion=1
errorCategory=INVALID_SCHEMA
retryable=false
disposition=REJECT_NO_REQUEUE
deadLetterTarget=orders.created.dlq
~~~

**disposition=REJECT_NO_REQUEUE** chỉ nói code đã lựa chọn hành vi từ chối. Nó **không tự chứng minh DLQ đã lưu message**. Nếu cần xác nhận đường đi, đối chiếu broker metrics/topology và test end-to-end. Không log toàn bộ payload chứa PII, thông tin thanh toán, token hoặc credentials.

### 20.2. Quy trình xử lý DLQ

1. Xác định owner của queue, SLA phản hồi và loại dữ liệu được lưu.
2. Phân loại nguyên nhân: schema, business rule, downstream, permissions, topology.
3. Kiểm tra eventId đã hoàn tất nghiệp vụ một phần hay chưa.
4. Sửa nguyên nhân gốc trước khi replay.
5. Replay một số message test hoặc một batch nhỏ có kiểm soát, giữ nguyên eventId.
6. Quan sát duplicate skips, business success, retry và DLQ mới.
7. Ghi audit về ai đã replay, lúc nào, vì sao và kết quả thế nào.

**Đừng tự động replay toàn bộ DLQ sang main queue mỗi phút** nếu dữ liệu vẫn sai; thao tác này có thể biến DLQ thành một retry queue vô hạn không được kiểm soát.

### 20.3. Bảo mật DLQ

Dead-letter message thường giữ body nghiệp vụ. Cần bảo vệ:

- Quyền đọc DLQ theo vhost/ACL.
- TLS trên đường kết nối.
- Retention, backup và chính sách xóa dữ liệu nhạy cảm.
- Quyền thực hiện replay hoặc tải message ra ngoài.
- Masking khi hiển thị payload trong dashboard và log.

Một DLQ lưu dữ liệu lỗi nhiều ngày có thể chứa thông tin nhạy cảm mà consumer chính thường chỉ giữ rất ngắn. Đưa DLQ vào đánh giá bảo mật và compliance của hệ thống.

## 21. Ma trận kiểm thử tích hợp trước production

Không thể chứng minh DLX/requeue chỉ bằng một unit test mock service activator. Cần **RabbitMQ broker thật trong môi trường test** (chẳng hạn broker test riêng hoặc Testcontainers), topology được provision đúng và test các tình huống broker/consumer thực.

| Bài thử | Tác động cần tạo | Kết quả cần xác minh |
| --- | --- | --- |
| **Thành công bình thường** | Publish event hợp lệ | Business transaction thành công, ACK, DLQ không có event đó |
| **Sai payload** | Publish text sai contract | Không retry nóng; reject không requeue và DLQ nhận nếu route đúng |
| **Transient thành công lần hai** | Repository fail attempt 1, success attempt 2 | RetryTemplate thử lại, listener ACK, DLQ không nhận |
| **Transient hết retry** | Repository fail cả ba attempts | Reject không requeue, DLQ nhận, có metric retry exhausted |
| **DLX thiếu** | Khai báo queue nguồn với DLX trỏ exchange không tồn tại trong test | Phát hiện message không tới DLQ; báo lỗi topology |
| **DLX có, binding sai** | Dead routing key không khớp binding | Message không vào queue mong đợi; không giả định DLX đủ |
| **Requeue nóng** | NACK requeue=true với handler luôn lỗi trong test ngắn | Nhiều redelivery, chứng minh cần bounded retry |
| **Manual ACK quên xác nhận** | Consumer MANUAL không settle trong test riêng | Unacked tăng gần prefetch, delivery mới bị giới hạn |
| **Consumer crash trước DB commit** | Kill process giữa transaction | DB rollback; broker có thể giao lại |
| **Consumer crash sau DB commit** | Kill trước ACK | Redelivery; inbox ngăn side effect trùng |
| **Producer gửi trùng eventId** | Publish cùng eventId hai lần | Business side effect đúng một lần |
| **Converter lỗi trước handler** | JSON không parse được, handler chưa được gọi | Listener error handler xử lý và không treo message vô hạn |
| **ErrorChannel hấp thụ exception** | Error flow log rồi return | Phát hiện ACK/NACK không đúng ý định nếu có |
| **ExecutorChannel** | Đổi xử lý sang thread khác | Xác minh ranh giới ACK; không mất việc sau ACK sớm |
| **Retry queue TTL** | Publish tới retry queue | Message quay lại main sau thời gian thích hợp, không đòi độ chính xác từng mili-giây |
| **Retry cycle** | Cho một event lỗi cố định đi qua retry topology | Có điểm kết thúc tại final DLQ |
| **Retry nhiều tầng** | Test 2 hoặc 3 mức backoff | Attempts được đếm đúng sau restart và republish |
| **DLQ overflow/TTL** | Dùng policy giới hạn ở broker test | Biết điều kiện DLQ tiếp tục giữ hoặc loại message |
| **Nhiều consumer** | Chạy 2–4 consumer cùng queue | Competing consumers, không nhầm là broadcast |
| **Graceful shutdown** | Dừng ứng dụng khi có unacked | Có thể phục hồi, không báo sai business completed |
| **Quorum queue delivery limit** | Cấu hình loại queue/phiên bản phù hợp | Dead-letter khi vượt limit theo policy thực |
| **Security** | Dùng tài khoản thiếu quyền | Thấy lỗi ACL/configure/read/write, không lộ dữ liệu |
| **Replay DLQ** | Replay event đã xử lý một phần | Giữ eventId, idempotency bảo vệ side effect |

### 21.1. Unit test service và retry

Một unit test có thể giả lập repository:

~~~text
Given: event evt-1001 hợp lệ
When : repository ném TransientOrderException ở attempt 1
       và thành công ở attempt 2
Then : RetryTemplate trả thành công
       OrderProcessingService hoàn tất transaction
       handler không yêu cầu reject-not-requeue
~~~

Một bài khác:

~~~text
Given: event thiếu orderId
When : parser ném InvalidOrderEventException
Then : RetryTemplate không retry thêm
       handler yêu cầu reject-not-requeue
~~~

Đây mới là **kiểm thử logic ứng dụng**. Nó không chứng minh broker có DLX, x-death hoặc binding. Phải có test tích hợp quan sát RabbitMQ để xác minh message thực sự đến **orders.created.dlq**.

### 21.2. Kịch bản crash sau DB commit

~~~mermaid
sequenceDiagram
    participant Q as RabbitMQ queue
    participant L as Warehouse listener
    participant S as Business service
    participant DB as Warehouse DB
    Q->>L: Delivery eventId=evt-1001
    L->>S: process(evt-1001)
    S->>DB: Insert inbox + update order
    DB-->>S: Commit
    Note over L: Process crash before broker receives ACK
    Q-->>L: Redelivery after consumer recovery
    L->>S: process(evt-1001) again
    S->>DB: Inbox detects duplicate
    DB-->>S: No repeated business mutation
    L-->>Q: ACK
~~~

Test này chứng minh **khả năng phục hồi nghiệp vụ**, chứ không chỉ kiểm tra số lần gọi Java method trong một JVM. Cần điều khiển được thời điểm crash/connection close và quan sát trạng thái DB sau restart.

### 21.3. Lỗi không route ở phía publisher

Đừng đưa một test **publish vào exchange nhưng không có binding phù hợp** vào nhóm “consumer DLQ”. Message chưa vào main queue thì không có consumer reject. Trong test, kiểm tra **publisher returns/mandatory** hoặc alternate exchange theo cấu hình, không chờ DLQ của consumer.

### 21.4. Dữ liệu test cần cách ly

Không publish malformed payload vào queue production. Khi chạy integration test, sử dụng queue/vhost test, tránh consumer khác lấy mất message, tránh xóa queue production và đảm bảo test không dùng credentials có quyền quản trị vượt phạm vi cần thiết.

## 22. Tình huống thiết kế: kết hợp DLQ và retry có giới hạn

Một nền tảng thương mại cần xử lý OrderCreated nhưng downstream Warehouse có hai nhóm lỗi:

- **Payload sai schemaVersion hoặc totalVnd không hợp lệ:** cần điều tra, không retry.
- **Database bị timeout trong ít phút:** nên retry chậm, không gây requeue loop.

Một thiết kế khả thi:

~~~mermaid
flowchart TD
    MQ["orders.created.q"] --> C["Warehouse consumer"]
    C --> V{"Validate payload"}
    V -->|"Lỗi cố định"| FD["Final DLQ<br/>orders.created.dlq"]
    V -->|"Hợp lệ"| DB{"DB transaction"}
    DB -->|"Commit thành công"| ACK["ACK"]
    DB -->|"Lỗi transient"| SHORT["Short local retry"]
    SHORT -->|"Hồi phục"| ACK
    SHORT -->|"Chưa hồi phục"| B{"Retry budget còn?"}
    B -->|"Còn"| RQ["Durable retry queue/job<br/>delay + nextAttempt"]
    RQ --> MQ
    B -->|"Hết"| FD
~~~

### 22.1. Các quyết định cần chốt

| Câu hỏi | Lựa chọn đề xuất cần kiểm chứng |
| --- | --- |
| Điều kiện coi đã xử lý? | DB transaction commit và inbox có trạng thái nhất quán |
| Lỗi cố định đi đâu? | Final DLQ có ownership, alert, replay manual |
| Lỗi transient retry ra sao? | Vài lần local retry, rồi delayed retry có giới hạn |
| Total attempts lưu ở đâu? | Durable inbox/job hoặc cơ chế broker đã kiểm chứng |
| Trước ACK bản gốc cần gì? | Business commit hoặc bản retry được nhận trách nhiệm bền vững |
| Khi republish UNKNOWN? | Giữ trạng thái, retry idempotent với eventId cũ |
| Nếu retry queue đầy? | Alert/backpressure, không âm thầm đánh dấu thành công |
| Khi consumer crash? | Redelivery cùng eventId, duplicate-safe |
| Khi DLQ đầy/hết retention? | Giám sát capacity và chính sách xử lý dữ liệu |
| Ai có quyền replay? | Operator/service được ủy quyền, có audit |

### 22.2. Không đặt một kiểu DLX cho mọi vấn đề

Một message có thể đi qua:

~~~text
RabbitMQ exchange
  -> queue chính
  -> listener
  -> service activator
  -> downstream database
~~~

**Lỗi ở từng ranh giới cần chính sách khác nhau**:

- Exchange không route: publisher returns/alternate exchange.
- Consumer nhận nhưng converter lỗi: listener error handler, reject và DLQ.
- DB tạm lỗi: retry hữu hạn/backoff.
- Business rule từ chối: final error state hoặc DLQ nếu hợp đồng yêu cầu.
- Network mất gần ACK: redelivery/idempotency.
- Republish sang retry exchange thất bại: confirms/returns/outbox hoặc durable state.

Chỉ có một DLX không thể giải quyết tất cả các loại lỗi trên.

### 22.3. Một event cho nhiều dịch vụ

Nếu Warehouse và Analytics đều cần OrderCreated, chúng có thể có **hai queue riêng** bind vào orders.events. Mỗi consumer group nên có retry/DLQ và policy theo nhu cầu của mình. Warehouse lỗi DB không nhất thiết làm Analytics ngừng nhận event, và Analytics replay DLQ không nên cập nhật nhầm inbox của Warehouse.

## 23. Những sai lầm phổ biến

**“DLX và DLQ là cùng một tài nguyên.”** DLX là exchange định tuyến; DLQ là queue nhận message qua binding.

**“Đặt x-dead-letter-exchange là đủ để lưu message lỗi.”** Cần DLX tồn tại, routing key/binding/queue đích hoạt động và mức bảo đảm phù hợp.

**“NACK requeue=true sẽ tự đưa vào DLQ.”** Không; requeue có thể giao lại nhanh, không có backoff mặc định.

**“NACK requeue=false chắc chắn không mất message.”** Nếu DLX không tồn tại hoặc không có route, message có thể không nằm trong DLQ.

**“Publisher return chính là dead-letter.”** Return báo publish không route được tại exchange; dead-lettering diễn ra sau khi message ở queue đáp ứng điều kiện.

**“Mọi lỗi đều nên được requeue để khỏi mất dữ liệu.”** Lỗi schema cố định có thể tạo hot loop vô hạn; phải phân loại.

**“RetryTemplate maxAttempts=3 giới hạn tổng số lần xử lý qua mọi redelivery.”** Nó chỉ giới hạn vòng retry của lần gọi trong tiến trình; restart/republish có thể tạo vòng mới.

**“TTL retry queue bảo đảm message được giao đúng sau 30 giây.”** TTL/dead-letter có độ trễ phụ thuộc broker/queue, không phải timer chính xác từng message.

**“Một retry queue tự động phân biệt transient và permanent.”** Phân loại phải có ở listener/application hoặc topology được thiết kế có chủ đích.

**“Dead-letter cycle sẽ luôn được RabbitMQ cắt theo số lần thử mong muốn.”** Không dựa vào điều đó; cần retry budget/final DLQ.

**“x-death count bằng tổng số lần service đã chạy.”** Retry trong listener, republish và các lý do dead-letter làm nghĩa của count khác business attempt.

**“Consumer ACK chứng minh transaction database đã commit.”** Nếu ACK quá sớm, DB có thể chưa commit; phải xác định mốc thực sự.

**“Có DLQ thì không cần idempotency.”** Crash sau DB commit trước ACK và replay DLQ vẫn có thể tạo duplicate.

**“Đặt defaultRequeueRejected(false) tự tạo DLQ.”** Nó chỉ ảnh hưởng hành vi requeue trong một số đường lỗi của listener container; topology phải có riêng.

**“Lỗi JSON luôn đi qua service activator.”** Converter có thể lỗi trước khi Spring Message được tạo.

**“ErrorChannel log lỗi rồi return vẫn chắc chắn NACK.”** Error flow có thể hấp thụ exception, làm listener được coi hoàn tất; phải test ACK/NACK.

**“Chuyển DirectChannel sang ExecutorChannel không ảnh hưởng ACK.”** Handler bất đồng bộ có thể thất bại sau khi container đã ACK.

**“QueueChannel trong bộ nhớ là durable retry queue.”** Không có bảo đảm tương đương broker queue hay database inbox nếu chưa cấu hình MessageStore bền vững.

**“Thay QueueBuilder arguments rồi restart sẽ sửa được main queue đã khai báo.”** Có thể gặp PRECONDITION_FAILED; cần migration/policy tương thích.

**“Quorum queue mặc nhiên có mọi bảo đảm dead-letter at-least-once.”** Cần queue type, broker version và cấu hình tính năng phù hợp.

**“DLQ không cần giám sát vì message đã an toàn.”** DLQ có thể đầy, hết TTL, bị replay nhầm hoặc chứa dữ liệu nhạy cảm.

**“Các consumer cùng main queue đều nhận mọi event.”** Chúng thường cạnh tranh delivery; broadcast giữa các hệ thống cần queue riêng.

**“Gọi basicAck trên channel khác vẫn được nếu biết delivery tag.”** Tag chỉ có nghĩa trên channel nguồn; ACK sai channel có thể gây protocol error.

**“Có thể ACK bản gốc ngay khi bắt đầu republish sang retry queue.”** Nếu lần publish retry thất bại hoặc UNKNOWN, có nguy cơ mất event; cần mốc chuyển trách nhiệm bền vững rõ ràng.

## 24. Câu hỏi tự kiểm tra

1. Dead-letter exchange và dead-letter queue khác nhau ở đâu? Tại sao DLX phải có binding tới DLQ?
2. Một message từ orders.created.q bị **basicReject(tag, false)** sẽ được xử lý ra sao khi queue có DLX hợp lệ? Còn khi DLX không tồn tại?
3. **basicNack(tag, false, true)** và **basicNack(tag, false, false)** khác nhau thế nào?
4. Vì sao requeue=true không nên được coi là một cơ chế retry có backoff?
5. Publisher return khác consumer reject/dead-letter ở giai đoạn nào của đường đi message?
6. RabbitMQ có những nguyên nhân phổ biến nào khiến một message bị dead-letter ngoài consumer reject?
7. TTL của message khác expiration của chính queue như thế nào?
8. Có thể dùng dead-letter routing key khác routing key nghiệp vụ ban đầu không? Vì sao cần giữ eventType/eventId?
9. Trong ví dụ OrdersDlxTopology, message lỗi đi qua những exchange, routing key và queue nào?
10. Vì sao Queue bean khai báo DLX không chứng minh broker đã có queue đích đúng binding?
11. Khi nào nên chọn RabbitMQ policy thay cho hardcode x-arguments trên QueueBuilder?
12. Nếu broker báo PRECONDITION_FAILED khi khai báo queue, bạn kiểm tra những cấu hình nào trước?
13. Với Spring AMQP AcknowledgeMode.AUTO, ai chịu trách nhiệm ACK và khi nào handler exception có thể dẫn đến reject?
14. setDefaultRequeueRejected(false) có tự tạo DLQ không? Nó cần phối hợp với thành phần nào?
15. RetryTemplate.maxAttempts(3) biểu thị bao nhiêu lần gọi xử lý trong một vòng retry?
16. Nếu DB lỗi hai lần rồi thành công ở attempt 3, delivery nên ACK hay đi DLQ?
17. Nếu dữ liệu sai schema cố định, vì sao nên tránh retry ba lần rồi requeue thêm vô hạn?
18. Trong Spring Integration, lỗi MessageConverter xảy ra trước khi tạo Spring Message có chắc đi vào handler của flow không?
19. Nếu errorChannel hấp thụ exception và return bình thường, kết quả ACK/NACK có thể thay đổi ra sao?
20. DirectChannel và ExecutorChannel khác nhau thế nào đối với thời điểm listener hoàn tất và AUTO ACK?
21. Vì sao delivery tag không thể dùng như eventId và không thể ACK trên một channel khác?
22. Một retry queue có TTL được đưa vào thiết kế như thế nào để message quay về main queue?
23. Cấu hình một retry queue có TTL có tự quyết định lỗi nào phải retry và lỗi nào đến final DLQ không?
24. Vì sao một vòng **main queue → retry queue → main queue** phải có điểm kết thúc?
25. Metadata x-death có thể giúp điều tra điều gì? Vì sao không dùng một giá trị count làm toàn bộ số attempts nghiệp vụ?
26. Nếu process chết sau DB commit nhưng trước ACK, điều gì xảy ra và idempotent consumer bảo vệ ra sao?
27. Tại sao transactional inbox cần unique constraint khi có nhiều consumer cùng queue?
28. Nếu consumer republish message sang retry exchange, vì sao cần publisher confirm/returns trước khi ACK delivery gốc?
29. Những điều kiện nào có thể khiến message đã bị dead-letter không xuất hiện trong DLQ như kỳ vọng?
30. Khi nào một quorum queue có thể cung cấp mức bảo đảm dead-letter khác một queue thông thường? Cần kiểm tra những gì?
31. Những metric nào giúp phân biệt requeue loop, downstream chậm và DLQ tăng do schema mismatch?
32. Tại sao việc DLQ có message không đồng nghĩa side effect database chắc chắn chưa từng diễn ra?
33. Nếu Warehouse và Analytics cần nhận cùng OrderCreated, thiết kế queue và DLQ theo từng hệ thống như thế nào?
34. Khi replay từ DLQ, nên giữ eventId hay sinh eventId mới? Có cần kiểm tra payload conflict không?
35. Bài test nào chứng minh manual/auto ACK, dead-letter routing và DB commit thực sự hoạt động đúng dưới lỗi kết nối?

## Tổng kết

**Dead-letter exchange (DLX)** là một **exchange RabbitMQ** dùng để định tuyến message bị dead-letter từ queue nguồn; **dead-letter queue (DLQ)** là queue được bind để tiếp nhận những message đó. Các nguyên nhân thường gồm **consumer reject/NACK với requeue=false**, hết **message TTL**, một số trường hợp queue vượt giới hạn và **delivery limit** của loại queue hỗ trợ. DLX không tự tạo queue đích, không thay publisher returns và không tự bảo đảm mọi message lỗi đều được lưu an toàn trong mọi cấu hình.

**Requeue=true** có thể làm broker giao lại delivery rất nhanh, chứ không mặc nhiên tạo delay hay giới hạn số lượt. Retry cần **phân loại lỗi, backoff, retry budget**, và một điểm kết thúc như **final DLQ**. Khi dùng **retry queue TTL**, phải thiết kế đường vào retry queue, đường trở lại main queue và cách chống vòng lặp; nếu republish sang queue khác, cần phân biệt xác nhận publish mới với ACK delivery gốc.

Trong **Spring Integration**, AMQP inbound channel adapter đưa delivery từ Spring AMQP listener container vào **MessageChannel**; service activator xử lý nghiệp vụ, còn **AcknowledgeMode.AUTO/MANUAL**, error handler và cách exception lan truyền quyết định ACK/NACK. Các yếu tố **DirectChannel hay ExecutorChannel, MessageConverter, prefetch, transaction, lifecycle và errorChannel** làm thay đổi ranh giới xử lý, nên phải được kiểm thử trên broker thật.

Cuối cùng, một thiết kế đáng tin cậy không chỉ có DLQ: nó còn cần **eventId ổn định, idempotent consumer, unique constraint/inbox, đối soát khi kết quả không rõ, monitoring ready/unacked/retry/DLQ, bảo mật và quy trình replay có owner**. Với những nguyên tắc đó, hệ thống có thể cô lập dữ liệu lỗi, retry an toàn và phục hồi khi RabbitMQ hoặc downstream gặp sự cố mà không nhầm **đã giao message**, **đã dead-letter** và **đã hoàn thành nghiệp vụ**.
