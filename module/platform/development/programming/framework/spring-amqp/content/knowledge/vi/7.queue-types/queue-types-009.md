# Không đồng nhất classic durable queue với queue được sao chép

## 1. Vì sao một queue durable vẫn có thể mất tính sẵn sàng?

Giả sử ứng dụng Spring Boot dùng **Spring AMQP** để nhận đơn hàng:

1. `RabbitTemplate` publish sự kiện `OrderCreated` tới RabbitMQ.
2. Exchange dùng routing key và binding đưa sự kiện vào queue `orders.created.q`.
3. `@RabbitListener` nhận sự kiện, ghi dữ liệu và xác nhận đã xử lý.

Nhóm phát triển khai báo `orders.created.q` với `durable=true`. Khi khởi động lại RabbitMQ trên **cùng một node và dữ liệu trên đĩa còn nguyên**, queue được khôi phục. Từ kết quả đó, họ kết luận: “Queue đã durable, cluster có ba node, vậy mất một node cũng không ảnh hưởng”.

**Kết luận này sai.** `durable` trả lời câu hỏi *“queue có được khôi phục sau khi node khởi động lại không?”*. **Replication (sao chép)** trả lời câu hỏi *“khi node giữ dữ liệu queue không còn hoạt động, các node khác có bản sao đủ điều kiện để tiếp tục phục vụ không?”*.

Trong **RabbitMQ 4.x**, **classic queue không sao chép nội dung giữa các node**. Muốn dùng queue có khả năng sao chép và tiếp tục hoạt động khi mất một node, hãy đánh giá **quorum queue** với nhiều replica trên một cluster thích hợp. Việc chọn queue type là một quyết định kiến trúc, độc lập với việc producer dùng `RabbitTemplate` hay consumer dùng `@RabbitListener`.

Bài thuộc chương **Các loại hàng đợi** tập trung phân biệt **classic durable queue** và **replicated queue** để không đánh đồng lưu trữ bền vững với tính sẵn sàng cao. Cuối bài có ví dụ Spring AMQP, bảng phân tích sự cố, cách quan sát và bài thực hành.

## 2. Bốn khái niệm cần tách biệt

| Khái niệm | Bảo đảm/ý nghĩa | Không có nghĩa là |
| --- | --- | --- |
| **Durable queue** | Định nghĩa queue được lưu bền vững, có thể khôi phục sau broker/node restart khi dữ liệu cần thiết còn nguyên. | Dữ liệu queue đã được nhân bản sang node khác. |
| **Persistent message** | Producer đánh dấu message ở chế độ lưu bền vững, phù hợp với classic durable queue. | Message đã được broker ghi an toàn nếu chưa nhận publisher confirm. |
| **Replicated queue** | Nhiều thành viên trên các node khác nhau cùng duy trì trạng thái của queue theo cơ chế của queue type. | Mọi tình huống lỗi đều không gián đoạn hoặc mọi bản ghi đều có thể khôi phục khi mất đa số replica. |
| **Publisher confirm** | Broker xác nhận kết quả xử lý publish theo mức bảo đảm của queue đích. | Consumer đã xử lý nghiệp vụ hoặc đã gửi consumer acknowledgment. |

Ba câu hỏi kiểm tra khi đọc cấu hình:

- **Queue thuộc loại nào?** Classic, quorum hay một mô hình khác như stream?
- **Queue có những thành viên ở node nào?** Có đúng nhiều replica thực sự không?
- **Ứng dụng kiểm tra kết quả publish và xử lý delivery như thế nào?** Có publisher confirm, consumer ack và idempotency không?

Một hệ thống có thể đặt cả ba node RabbitMQ trong cùng cluster nhưng vẫn sử dụng **classic queue lưu trên một node**. Số lượng node trong cluster **không tự biến classic queue thành queue được sao chép**.

## 3. Classic durable queue: có lưu bền vững, không có bản sao message

### 3.1. Khi `durable=true` có tác dụng

Với AMQP 0-9-1, Spring AMQP thường khai báo một classic queue như sau:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;

@Bean
Queue classicOrdersQueue() {
    return QueueBuilder.durable("orders.classic.q")
            .withArgument("x-queue-type", "classic")
            .build();
}
~~~

Hai thành phần khác nhau ở đây:

- `durable("orders.classic.q")` yêu cầu **định nghĩa queue bền vững**; queue không tự mất sau một lần restart bình thường.
- `x-queue-type=classic` chọn **classic queue**, loại queue **không nhân bản dữ liệu** trong RabbitMQ 4.x.

Để những message đang chờ trong classic queue có cơ sở tồn tại sau restart, producer cần đặt **delivery mode = persistent** và theo dõi **publisher confirms**. Ví dụ, ở mức message properties:

~~~java
import org.springframework.amqp.core.MessageDeliveryMode;

rabbitTemplate.convertAndSend(
        "orders.events",
        "orders.classic",
        orderEvent,
        message -> {
            message.getMessageProperties()
                    .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
            return message;
        }
);
~~~

Đoạn này là phần thân method minh họa có sẵn biến `rabbitTemplate` và `orderEvent`. Delivery mode và publisher confirm là **hai việc khác nhau**: `PERSISTENT` thể hiện yêu cầu lưu; **confirm** là tín hiệu broker đã xử lý publish theo ngữ nghĩa queue đích. Nếu kết nối đứt trước confirm, trạng thái gửi có thể **chưa xác định**, chứ không mặc nhiên thất bại.

### 3.2. Một classic queue trong cluster

Giả sử cluster có ba node:

~~~text
RabbitMQ cluster

Node A                         Node B              Node C
+--------------------+         +-------------+      +-------------+
| orders.classic.q   |         | metadata    |      | metadata    |
| Queue data / index |         | cluster     |      | cluster     |
| Persistent messages|         |             |      |             |
+--------------------+         +-------------+      +-------------+

                          Khong co ban sao du lieu
                          classic queue tren B, C
~~~

Metadata của cluster (chẳng hạn định nghĩa queue, exchange, binding) được phân phối trong cluster theo mô hình metadata của RabbitMQ. Nhưng **metadata có queue** không đồng nghĩa **message trong classic queue đã được sao chép**.

Khi **Node A** là node giữ nội dung của classic queue và bị dừng:

- Node B và C có thể vẫn nhận kết nối, phục vụ các queue khác.
- `orders.classic.q` **không tiếp tục phục vụ bình thường chỉ nhờ B và C còn sống**.
- Nếu A khởi động lại với dữ liệu ổ đĩa còn nguyên, classic durable queue và những persistent message đã được lưu/confirm phù hợp có thể khôi phục.
- Nếu A hỏng ổ đĩa vĩnh viễn và không có bản sao/backup phù hợp, B và C không thể tự “đẻ ra” những message đã mất từ metadata.

Một cách diễn đạt chính xác: **classic durable queue giúp chịu được restart có khôi phục dữ liệu trên node sở hữu; nó không cung cấp queue-level high availability khi node đó biến mất**.

### 3.3. Classic mirrored queue là câu chuyện lịch sử

RabbitMQ từng có **classic mirrored queues** trên các phiên bản cũ, cho phép sao chép classic queue bằng chính sách mirroring. Tính năng này đã bị deprecated và **loại bỏ hoàn toàn từ RabbitMQ 4.0**.

Vì vậy, với RabbitMQ **4.x**, không dùng các bài hướng dẫn cũ về policy `ha-mode` / `ha-params` để kết luận classic queue được replicated. Nếu cần queue được sao chép, tài liệu RabbitMQ hiện đại hướng đến **quorum queues**; với nhu cầu dạng log có replay và nhiều subscriber, có thể cân nhắc **streams**.

## 4. Quorum queue: queue bền vững được sao chép qua Raft

### 4.1. Leader, follower và đa số thành viên

**Quorum queue** là một queue durable và replicated. Nó sử dụng **Raft consensus** để thống nhất trạng thái giữa những **member** của cùng một queue:

~~~mermaid
flowchart LR
    P["Spring AMQP producer"]
    A["RabbitMQ node A: leader<br/>orders.quorum.q"]
    B["RabbitMQ node B: follower<br/>orders.quorum.q"]
    C["RabbitMQ node C: follower<br/>orders.quorum.q"]
    L["Spring AMQP @RabbitListener"]
    P -->|"publish"| A
    A <-->|"Raft replication"| B
    A <-->|"Raft replication"| C
    A -->|"delivery"| L
~~~

Sơ đồ thể hiện cách suy nghĩ về replication, không buộc producer/consumer phải kết nối trực tiếp vào leader. Trong cluster RabbitMQ, client thường có thể kết nối tới node bất kỳ; broker chuyển các thao tác tới nơi quản lý queue phù hợp.

Với ba replica **A, B, C**, cần tối thiểu **hai replica** cùng tham gia để tạo đa số:

\[
\text{Số thành viên tối thiểu để có đa số}
=\left\lfloor\frac{N}{2}\right\rfloor+1
\]

| Số member của quorum queue | Đa số cần có | Số member có thể mất mà vẫn còn đa số |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |

Một **quorum queue trên RabbitMQ một node** vẫn có thể tạo được trong môi trường thử nghiệm, nhưng nó chỉ có **một member** và **không có khả năng chịu lỗi node**. Muốn kiểm chứng failover khi mất một node, cần tối thiểu **ba member trên ba node khác nhau**. Số member lẻ như **3 hoặc 5** thường hợp lý vì phù hợp nguyên tắc đa số và hạn chế chi phí replication không cần thiết.

### 4.2. Publish được confirm khi nào?

Khi producer bật **publisher confirms**, đối với **quorum queue**, broker gửi confirm sau khi message được replica quorum chấp nhận và được xem là an toàn theo cơ chế consensus của queue. Với queue ba member, đây là ngữ nghĩa của **đa số**, không đòi hỏi mọi replica đều đã trực tiếp trả lời.

Quorum queue lưu message bền vững theo thiết kế của nó, không dựa vào việc producer chọn delivery mode transient hay persistent giống classic queue. Dù vậy, trong một ứng dụng có thể đưa message tới nhiều loại queue, dùng delivery mode phù hợp và publisher confirms vẫn là thói quen rõ ràng, dễ đối soát.

**Giới hạn quan trọng:** RabbitMQ không cam kết an toàn cho message **chưa được confirm**. Một publisher mất kết nối trước khi nhận confirm phải coi kết quả là **chưa xác định**: message có thể đã vào queue, hoặc chưa được nhận. Retry cần giữ **event ID ổn định** và consumer phải xử lý trùng.

### 4.3. Không đủ đa số thì điều gì xảy ra?

Quorum queue ưu tiên nhất quán dữ liệu. Nếu chỉ còn **một trong ba** member có thể liên lạc, không có đa số để bầu leader và commit những thay đổi mới; queue **không thể tiếp tục tiến hành các thao tác như khi còn quorum**.

Do vậy, “replicated” **không có nghĩa** “mọi node đều có thể hoạt động độc lập và tiếp tục nhận message”. Phần minority không được tự nhận mình là leader, tránh hai bên cùng ghi các phiên bản trạng thái không tương thích.

## 5. Cùng một sự cố, hai queue type cho kết quả khác nhau

Giả sử hệ thống có cluster A–B–C, classic queue lưu trên A; quorum queue có leader ở A và follower ở B, C.

| Tình huống | Classic durable queue trên A | Quorum queue có member A, B, C |
| --- | --- | --- |
| A restart bình thường, giữ nguyên đĩa | Tạm dừng khi A chưa sẵn sàng; có thể khôi phục queue và persistent message phù hợp khi A lên. | Trong khi A mất, B/C vẫn có đa số và có thể bầu leader mới; khi A trở lại sẽ đồng bộ theo cơ chế Raft. |
| A mất điện, B/C vẫn chạy | Queue classic trên A không khả dụng đến khi A phục hồi. | B/C có thể tiếp tục phục vụ sau quá trình bầu leader, nếu các điều kiện kết nối và quorum đáp ứng. |
| A hỏng ổ đĩa vĩnh viễn | Message chỉ có trên A có nguy cơ mất vĩnh viễn nếu không có backup/khôi phục khác. | Hai replica còn lại có thể tiếp tục phục vụ những message đã được quorum confirm. |
| B dừng, A vẫn chạy | Classic trên A vẫn có thể hoạt động. | A/C còn đa số: có thể tiếp tục hoạt động. |
| A và B cùng mất, chỉ C còn | Classic trên A không khả dụng. | C là minority: không thể tự bảo đảm tiến độ theo quorum. |
| Producer chỉ cấu hình kết nối tới A rồi A tắt | Producer bị mất kết nối dù queue classic/quorum là loại nào. | Queue quorum vẫn có thể sống trên B/C, nhưng producer cần cơ chế kết nối lại tới node còn hoạt động. |

**Lưu ý về điều kiện:** Những tình huống trên giả sử replica được phân bố đúng qua các node, cluster được cấu hình lành mạnh và dữ liệu đã được broker confirm theo chính sách thích hợp. Không nên mô tả failover là “không có độ trễ”: leader election, client reconnect và retry thường gây gián đoạn ngắn.

### Phân biệt ba kiểu chịu lỗi

| Cơ chế | Giải quyết tốt nhất vấn đề gì? |
| --- | --- |
| **Durability** | Node khởi động lại và khôi phục được dữ liệu bền vững cục bộ. |
| **Replication + quorum** | Một số node bị mất nhưng còn đa số replica có thể tiếp tục quản lý queue, tránh phụ thuộc một bản lưu đơn lẻ. |
| **Backup/DR đa vùng** | Khôi phục sau sự cố ảnh hưởng toàn cluster, thao tác xóa nhầm hoặc thảm họa lớn; replication trong cluster không thay thế backup và kế hoạch DR. |

## 6. So sánh classic durable và quorum queue để chọn thiết kế

| Tiêu chí | Classic durable queue (RabbitMQ 4.x) | Quorum queue |
| --- | --- | --- |
| Định nghĩa và dữ liệu | Durable khi khai báo đúng; persistent message được lưu tại node quản lý queue. | Bắt buộc durable; message được lưu và sao chép qua các member. |
| Replication dữ liệu queue | **Không**. | **Có**, dựa trên Raft. |
| Hoạt động khi mất node chứa dữ liệu | Queue không khả dụng trong lúc node đó mất. | Có thể tiếp tục nếu còn **đa số** member và leader được bầu lại. |
| Số node cần để có chịu lỗi node | Không có HA ở cấp queue dù cluster nhiều node. | Thường chọn **3 hoặc 5 member trên các node khác nhau**. |
| Queue tạm/exclusive | Có hỗ trợ theo feature và cấu hình broker. | Không phù hợp; quorum queue không hỗ trợ non-durable/exclusive/auto-delete. |
| Kết quả publisher confirm | Với message persistent trên queue durable, confirm gắn với lưu bền vững trên node đích. | Confirm gắn với message đã được quorum replicas chấp nhận. |
| Tính năng riêng | Phù hợp nhiều nhu cầu queue thông dụng, kể cả queue tạm, priority và chính sách quen thuộc. | Có cơ chế handling message được giao lỗi nhiều lần, tùy phiên bản; có lựa chọn dead-letter tin cậy hơn khi cấu hình. |
| Chi phí | Một bản queue data; thường ít chi phí tài nguyên cho replication. | Cần thêm CPU, đĩa, mạng, vận hành replica và leader election. |
| Phù hợp | Queue có thể tái tạo, message ít quan trọng hoặc ưu tiên chi phí/đơn giản. | Queue công việc nghiệp vụ quan trọng cần bảo vệ dữ liệu trước lỗi node. |

Đừng dựa vào tên queue như `orders.durable.q` hoặc chỉ nhìn cờ `durable=true` để suy luận đã có replication. Cần xem **`type`**, số **member**, node leader/follower và trạng thái của chúng.

## 7. Khai báo classic và quorum queue bằng Spring AMQP

Queue type là lựa chọn **của RabbitMQ broker**, không yêu cầu thay `RabbitTemplate` bằng client AMQP 1.0. Ví dụ dưới đây vẫn sử dụng **Spring AMQP + RabbitMQ AMQP 0-9-1**.

### 7.1. Dependency và kết nối

Với **Spring Boot 3.x**, dependency phổ biến:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
~~~

Ví dụ `application.yml` cho môi trường thử nghiệm:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      simple:
        acknowledge-mode: auto
~~~

`guest/guest` chỉ phù hợp với RabbitMQ cục bộ và thường bị giới hạn kết nối loopback. Trong cluster thật, hãy dùng user/vhost/secret riêng, kết nối an toàn và cấu hình danh sách node hoặc endpoint có thể chuyển hướng sang node còn hoạt động. **Bài này không cấu hình cluster ba node bằng YAML trên**: cần tự triển khai RabbitMQ cluster để thực sự kiểm nghiệm failover.

### 7.2. Khai báo hai queue với kiểu rõ ràng

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
public class QueueTypeTopology {

    public static final String EXCHANGE = "orders.events";
    public static final String CLASSIC_QUEUE = "orders.classic.q";
    public static final String QUORUM_QUEUE = "orders.quorum.q";
    public static final String CLASSIC_KEY = "orders.classic";
    public static final String QUORUM_KEY = "orders.quorum";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue classicQueue() {
        return QueueBuilder.durable(CLASSIC_QUEUE)
                .withArgument("x-queue-type", "classic")
                .build();
    }

    @Bean
    Queue quorumQueue() {
        return QueueBuilder.durable(QUORUM_QUEUE)
                .withArgument("x-queue-type", "quorum")
                .build();
    }

    @Bean
    Binding classicBinding(
            @Qualifier("classicQueue") Queue queue,
            DirectExchange ordersExchange) {
        return BindingBuilder.bind(queue).to(ordersExchange)
                .with(CLASSIC_KEY);
    }

    @Bean
    Binding quorumBinding(
            @Qualifier("quorumQueue") Queue queue,
            DirectExchange ordersExchange) {
        return BindingBuilder.bind(queue).to(ordersExchange)
                .with(QUORUM_KEY);
    }
}
~~~

Khi `RabbitAdmin` tự khai báo Spring bean topology, hai queue có **tên khác nhau** nhưng chung exchange. Producer chọn `CLASSIC_KEY` hoặc `QUORUM_KEY` để gửi vào queue tương ứng.

**Vì sao đặt `x-queue-type` tường minh?** RabbitMQ có thể cấu hình **default queue type** ở cấp virtual host; nếu thiếu `x-queue-type`, không nên mặc nhiên suy ra mọi môi trường tạo classic queue. Cấu hình rõ loại queue cũng giúp đọc mã và đối soát khi migrate.

Quorum queue cần replica trên nhiều node để chịu lỗi. Chỉ tạo `quorumQueue()` trên RabbitMQ một node **không biến broker đó thành cluster HA**. Khi khai báo quorum queue trên cluster ba node lành mạnh, broker thường tạo tối đa ba member ban đầu theo cấu hình mặc định; cần kiểm tra trạng thái thật trong Management UI/CLI.

Nếu hệ thống yêu cầu chọn group size:

~~~java
@Bean
Queue quorumOrdersThreeMembers() {
    return QueueBuilder.durable("orders.quorum.three.q")
            .withArgument("x-queue-type", "quorum")
            .withArgument("x-quorum-initial-group-size", 3)
            .build();
}
~~~

Ví dụ này phù hợp khi đã có **ít nhất ba node** sẵn sàng để phân bố member. `x-quorum-initial-group-size=3` chỉ nêu **số lượng mong muốn lúc khởi tạo**; phải kiểm tra số replica hoạt động thực tế. Thay đổi group size hoặc membership của một queue đang tồn tại cần thao tác vận hành phù hợp, không chỉ sửa argument trong code.

### 7.3. Publish và theo dõi publisher confirm

~~~java
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrdersPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrdersPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishToQuorum(String eventId) {
        CorrelationData correlation = new CorrelationData(eventId);

        rabbitTemplate.convertAndSend(
                QueueTypeTopology.EXCHANGE,
                QueueTypeTopology.QUORUM_KEY,
                eventId,
                message -> {
                    message.getMessageProperties().setMessageId(eventId);
                    message.getMessageProperties()
                            .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    return message;
                },
                correlation
        );

        correlation.getFuture().whenComplete((confirm, error) -> {
            if (error != null) {
                // Chưa xác định được kết quả: cần log và đối soát.
                return;
            }
            if (confirm.isAck()) {
                // Broker đã xác nhận publish, không phải consumer đã xử lý.
            } else {
                // Broker NACK; ghi nhận nguyên nhân và xử lý theo chính sách.
            }
        });
    }
}
~~~

Với cấu hình `mandatory=true`, khi message không có queue đích, RabbitMQ có thể **return message** dù publisher confirm là ACK. Do đó phải kết hợp `RabbitTemplate.ReturnsCallback` hoặc thông tin returned message từ `CorrelationData` (tùy phiên bản) nếu ứng dụng cần xác nhận **message đã định tuyến đúng**.

Đối với classic durable queue, mẫu publish có thể dùng `QueueTypeTopology.CLASSIC_KEY`. Sự khác biệt đáng chú ý nằm ở **broker sẽ confirm theo ngữ nghĩa nào của queue đích**; không thể tạo replication bằng cách đổi tên routing key.

### 7.4. Consumer vẫn đọc theo tên queue

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class QuorumOrdersListener {

    @RabbitListener(queues = QueueTypeTopology.QUORUM_QUEUE)
    public void consume(String eventId) {
        // Trong ứng dụng thật:
        // 1. Kiểm tra eventId bằng ràng buộc unique.
        // 2. Ghi thay đổi nghiệp vụ và dấu đã xử lý trong cùng transaction DB.
        // 3. Chỉ hoàn tất method khi xử lý thành công.
        System.out.println("Xu ly order event: " + eventId);
    }
}
~~~

Trong chế độ `acknowledge-mode: auto` của **Spring listener container**, container gửi consumer ACK sau khi method chạy thành công. Đây **không phải** chế độ AMQP broker auto-ack trước xử lý. Nếu method ném exception, cơ chế reject/requeue còn phụ thuộc container, loại lỗi, retry và cấu hình.

Quorum queue giúp bảo vệ dữ liệu message trước lỗi node, nhưng **không bảo đảm side effect nghiệp vụ chỉ chạy một lần**. Nếu listener ghi database xong rồi mất connection trước khi ACK đến broker, message có thể được **giao lại**. Vì thế cần **idempotent consumer** dựa trên `eventId`.

## 8. Publisher confirm, consumer ACK và replication là ba lớp độc lập

~~~mermaid
sequenceDiagram
    autonumber
    participant P as RabbitTemplate
    participant L as Quorum leader A
    participant F as Follower B
    participant C as @RabbitListener
    P->>L: Publish eventId=evt-1001
    L->>F: Raft replication
    F-->>L: Replica tham gia xác nhận
    L-->>P: Publisher confirm ACK khi đạt quorum
    L->>C: Delivery
    C->>C: Ghi nghiệp vụ, chống trùng
    C-->>L: Consumer ACK
~~~

| Lớp | Ai xác nhận? | Tín hiệu nói điều gì? |
| --- | --- | --- |
| **Publisher confirm** | Broker → producer | Publish đã được broker xử lý theo mức bảo đảm của queue: với quorum queue, bao gồm điều kiện đa số replica. |
| **Consumer acknowledgment** | Consumer/container → broker | Delivery đã được consumer chấp nhận sau khi xử lý theo chính sách. |
| **DB transaction/idempotency** | Ứng dụng nghiệp vụ | Thay đổi dữ liệu cuối cùng nhất quán, xử lý an toàn khi message được giao lại. |

Một số tình huống thường gặp:

- **Producer chưa nhận confirm**: không rõ publish đã thành công hay chưa; ghi trạng thái chưa chắc chắn, đối soát và retry có kiểm soát.
- **Publisher confirm ACK nhưng consumer không chạy**: kiểm tra routing/binding, returned message, queue ready/unacknowledged, consumer count và log listener.
- **Consumer đã commit DB nhưng mất ACK**: message có thể được giao lại; cần xử lý trùng.
- **Queue đã được sao chép nhưng hai trong ba member cùng mất**: không có quorum để tiếp tục xử lý, dù producer và consumer code đều còn hoạt động.

Những lớp này phối hợp để tạo **xử lý bất đồng bộ đáng tin cậy**; không lớp nào có thể thay thế hoàn toàn các lớp còn lại.

## 9. Retry, dead-letter và giao dịch khi dùng quorum queue

Quorum queue có các cơ chế hữu ích để xử lý message bị giao lại nhiều lần, nhưng cần xem chính sách của **phiên bản RabbitMQ đang chạy**:

- **Delivery limit / poison message handling**: giới hạn các lần redelivery không thành công, giảm nguy cơ một message lỗi bị requeue vô hạn. RabbitMQ 4.x có các mặc định và chi tiết kiểm đếm phụ thuộc phiên bản; phải đo trên hệ thống thực.
- **Dead-letter exchange (DLX)**: định tuyến message bị reject hoặc vượt giới hạn sang nơi điều tra nếu cấu hình phù hợp. Quorum queue hỗ trợ các chiến lược dead-letter khác nhau, trong đó có chế độ **at-least-once** khi thỏa điều kiện cấu hình của broker.
- **Retry với backoff**: không nên dùng `basicNack(requeue=true)` lặp mãi trong listener, vì tạo vòng nóng, tiêu hao tài nguyên. Có thể phối hợp retry hữu hạn trong Spring, DLX, TTL/delay hoặc cơ chế retry của broker theo phiên bản.
- **DB và broker không chung một transaction**: commit DB không tự đồng thời commit publish RabbitMQ. Với yêu cầu không bỏ sót event sau khi ghi DB, cân nhắc **transactional outbox**.

**Không nên tự suy ra** rằng quorum queue làm message “exactly once”. Sau failover, message chưa được ACK có thể được giao lại; ứng dụng phải có business key/event ID và ràng buộc chống xử lý trùng.

Ví dụ với event `evt-1001`: consumer đã tạo lệnh thanh toán rồi mất kết nối. Khi message được giao lại, listener phải nhận ra event đã hoàn tất. Một bảng ghi dấu event với unique constraint, được cập nhật trong cùng transaction với thay đổi nghiệp vụ, có thể giúp duy trì tính đúng đắn.

## 10. Không thể chuyển classic thành quorum bằng cách đổi mỗi flag

Queue type là một thuộc tính được quyết định **lúc khai báo queue**. Nếu `orders.classic.q` đã tồn tại với `x-queue-type=classic`, đổi mã Spring sang:

~~~java
QueueBuilder.durable("orders.classic.q")
        .withArgument("x-queue-type", "quorum")
        .build();
~~~

**Không biến queue đã tồn tại thành quorum queue.** Broker có thể báo các tham số khai báo không tương đương, thường là `PRECONDITION_FAILED`. Một số phiên bản có cấu hình nới lỏng kiểm tra queue type khi redeclare, nhưng điều đó **không chuyển đổi nội dung và cơ chế lưu trữ** của queue đang tồn tại.

### Cách chuyển đổi có kiểm soát

1. **Kiểm kê** tên queue, vhost, type, số message ready/unacknowledged, producer/consumer, binding và chính sách retry/DLX.
2. **Tạo queue quorum mới** với tên mới (ví dụ `orders.quorum.q`) và topology riêng; xác minh số member, leader và follower.
3. **Chuẩn bị producer/consumer** cho đường mới, kiểm tra tương thích tính năng, publisher confirms, consumer ack và idempotency.
4. **Chuyển lưu lượng có kiểm soát**, xác định thời điểm producer ngừng phát sang queue cũ; cân nhắc việc dual-publish có thể tạo bản sao nghiệp vụ.
5. **Xử lý hết hoặc di chuyển an toàn backlog** của queue cũ; đối soát lượng message/ID và trạng thái nghiệp vụ.
6. **Thử failover** khi còn nhiều member và bảo đảm client có thể kết nối vào node còn hoạt động; sau đó mới gỡ queue cũ.

Không xóa queue production khi chưa đối soát dữ liệu chỉ để làm mất lỗi `PRECONDITION_FAILED`. Và đừng coi việc queue mới có cùng tên routing key là đủ: phải kiểm tra **đích định tuyến**, **vhost**, **binding** và **trạng thái dữ liệu cũ**.

## 11. Quan sát queue type và replica đang chạy

### 11.1. RabbitMQ Management UI

Khi xem queue, cần phân biệt:

| Trường/chỉ số | Ý nghĩa cần kiểm tra |
| --- | --- |
| **Type** | `classic` hay `quorum`? Không kết luận từ tên hoặc `durable`. |
| **Durable** | Có khôi phục queue sau restart không? Đây không phải replication factor. |
| **Leader / members** | Với quorum queue, leader ở node nào? Có đủ follower trên node khác nhau không? |
| **Members online** | Đa số member có đang hoạt động để bảo đảm tiến độ không? |
| **Messages ready** | Có bao nhiêu message đang chờ consumer? |
| **Messages unacknowledged** | Bao nhiêu delivery chưa được consumer ACK? |
| **Publish confirm latency / errors** | Producer có nhận confirm đều đặn, timeout hoặc NACK không? |
| **DLQ / redelivery** | Có message lỗi bị đưa vào DLQ hoặc giao lại quá nhiều lần không? |

### 11.2. Ví dụ lệnh CLI trên máy RabbitMQ

~~~bash
# Liệt kê các queue, loại queue, cờ durable và arguments trong vhost "/".
rabbitmqctl list_queues -p / name type durable arguments

# Kiểm tra leader/member của một quorum queue.
rabbitmq-queues quorum_status -p / orders.quorum.q

# Xem các node RabbitMQ trong cluster.
rabbitmq-diagnostics cluster_status

# Kiểm tra liệu việc dừng node hiện tại có thể khiến mất quorum.
rabbitmq-diagnostics check_if_node_is_quorum_critical
~~~

Lệnh trên cần chạy trong môi trường có quyền quản trị RabbitMQ. Một số tùy chọn CLI có thể khác nhau giữa bản RabbitMQ; hãy tra `--help` trên đúng máy đang chạy. Dù CLI hiển thị `durable=true`, chỉ khi thấy **type=quorum** cùng số member thực tế mới có cơ sở kết luận queue đang được sao chép.

Một chỉ số đáng chú ý nữa là **disk free, memory alarm, network partition và tốc độ đồng bộ member**. Khi broker hoặc mạng đang chịu áp lực, failover có thể cần nhiều thời gian hơn và publisher confirm có thể bị chậm.

## 12. Bài thực hành: ba node và hai queue

Thực hành này yêu cầu **cluster RabbitMQ ba node A, B, C trong môi trường phát triển**, cùng một vhost và quyền kết nối phù hợp. Không thực hiện thao tác dừng node trên production.

| Bước | Thao tác | Điều cần xác minh |
| --- | --- | --- |
| 1 | Khai báo `orders.classic.q` và `orders.quorum.q` bằng cấu hình Spring ở mục 7. | Management UI hiển thị hai **type khác nhau**; cả hai có `durable=true`. |
| 2 | Kiểm tra membership của `orders.quorum.q`. | Có **3 member trên 3 node khác nhau**; biết leader hiện tại ở đâu. |
| 3 | Publish message có `eventId` tới từng queue, bật publisher confirms. | Nhận confirm, consumer có thể nhận/ACK; lưu log correlation ID. |
| 4 | Dừng consumer và publish thêm message đến từng queue. | Messages ready tăng; consumer tạm dừng không làm durable queue biến mất. |
| 5 | Xác định node chứa classic queue và node leader quorum; dừng node đó trong môi trường test. | Classic queue trên node ấy không khả dụng. Quorum queue còn B/C đủ đa số và có thể bầu leader mới. |
| 6 | Chuyển producer/consumer sang node còn sống nếu kết nối cũ bị mất. | Có thể tiếp tục publish/consume quorum queue sau recovery; lưu ý độ trễ bầu leader. |
| 7 | Khởi động lại node bị dừng với dữ liệu đĩa còn nguyên. | Classic queue có thể khôi phục; member quorum quay lại và đồng bộ. |
| 8 | Tại môi trường cô lập, thử tình huống quorum mất hai member. | Chỉ còn 1/3 thì không đủ đa số; queue quorum không thể tiếp tục nhận/commit như bình thường. |
| 9 | Kiểm tra duplicate event sau reconnect và lặp lại delivery. | Listener sử dụng event ID để tránh áp dụng side effect hai lần. |

**Câu hỏi bắt buộc trước khi kết luận thí nghiệm thành công:** Producer có thực sự cấu hình kết nối tới **hơn một node hoặc endpoint có failover** chưa? Queue quorum còn khả dụng trên broker không đủ nếu ứng dụng chỉ biết một địa chỉ node đã chết.

### Mẫu ghi chép kết quả

~~~text
RabbitMQ version:
Cluster nodes:
Classic queue: name / type / host node / durable:
Quorum queue: name / type / leader / followers / members online:
Event ID:
Publisher confirm before failure:
Node stopped:
Classic queue behavior:
Quorum queue behavior:
Publisher reconnect / confirm after failover:
Consumer ack / redelivery after failover:
Outstanding messages and final business state:
~~~

Nên ghi cả mốc thời gian và số message trước/sau sự cố. Nếu muốn đánh giá độ an toàn dữ liệu, cần kiểm tra **những message đã được confirm**, thay vì chỉ nhìn message count tại một thời điểm.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Queue `orders.q` có `durable=true` và `x-queue-type=classic` trên cluster ba node. Khi node giữ nội dung queue bị dừng, hai node còn lại có tự phục vụ message trong queue không?

**Trả lời:** Không. Classic queue trong RabbitMQ 4.x không có message replication; số node trong cluster không đủ để biến nó thành queue replicated.

**Câu 2.** Classic durable queue có thể khôi phục sau khi node restart không?

**Trả lời:** Có, nếu dữ liệu lưu bền vững trên node vẫn còn; khả năng khôi phục message còn phụ thuộc delivery mode, publisher confirms và tình trạng dữ liệu tại thời điểm lỗi.

**Câu 3.** Quorum queue có ba replica A/B/C. A mất, B/C còn liên lạc. Queue có thể hoạt động tiếp không?

**Trả lời:** Có thể, vì B/C còn **đa số 2/3**, có thể bầu leader mới; client vẫn cần kết nối tới node khả dụng.

**Câu 4.** Quorum queue ba replica chỉ còn C. Có nên tiếp tục nhận ghi mới vào C để tăng availability không?

**Trả lời:** Không. C chỉ là **1/3**, không có đa số; cơ chế Raft không cho phép một minority tự quyết định commit một cách an toàn.

**Câu 5.** Publisher nhận confirm ACK cho một message đến quorum queue. Điều đó có nghĩa listener đã cập nhật database?

**Trả lời:** Không. Publisher confirm phản ánh broker đã xử lý publish theo ngữ nghĩa quorum; consumer acknowledgment và transaction nghiệp vụ là bước riêng.

**Câu 6.** Nếu muốn chuyển classic queue sang quorum queue, có thể chỉ thêm `x-queue-type=quorum` vào khai báo cùng tên không?

**Trả lời:** Không. Queue type không được chuyển đổi tại chỗ bằng cách redeclare; cần migration topology và backlog có kiểm soát.

## 14. Tài liệu tham khảo

- [RabbitMQ — Classic Queues](https://www.rabbitmq.com/docs/classic-queues): classic queue, đặc điểm lưu trữ và việc classic queue không replicated từ RabbitMQ 4.0.
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues): Raft, replication, quorum majority, tính năng và giới hạn.
- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): queue durability, queue type, cluster và vòng đời.
- [RabbitMQ — Reliability Guide](https://www.rabbitmq.com/docs/reliability): sự khác biệt giữa clustering, queue replication, khôi phục và sự cố node.
- [RabbitMQ — Publisher Confirms and Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms): ngữ nghĩa xác nhận khi publish/consume.
- [RabbitMQ — Classic Queue Mirroring (legacy)](https://www.rabbitmq.com/docs/3.13/ha): tài liệu lịch sử cho tính năng đã bị gỡ ở RabbitMQ 4.0.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): khai báo `QueueBuilder`, `RabbitTemplate`, `@RabbitListener` và xử lý xác nhận/lỗi.

Trong kiến trúc **Spring AMQP** với RabbitMQ, một **classic queue có `durable=true`** có thể khôi phục trên node còn dữ liệu nhưng **không đồng nghĩa queue được sao chép giữa các node**. **Quorum queue** bổ sung replication và khả năng chịu mất node khi vẫn còn đa số member. Để hệ thống xử lý bất đồng bộ đáng tin cậy, cần kết hợp lựa chọn queue type với publisher confirms, consumer acknowledgments, định tuyến đúng, retry/dead-letter, idempotency, giao dịch ứng dụng và giám sát trạng thái replica.
