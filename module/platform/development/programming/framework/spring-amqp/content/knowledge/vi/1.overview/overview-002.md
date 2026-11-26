# Vai trò của producer, broker, consumer và ứng dụng nghiệp vụ

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt **producer**, **message broker** và **consumer**, đồng thời xác định trách nhiệm của mỗi thành phần trong một luồng xử lý bất đồng bộ.
- Giải thích vì sao khi dùng **Spring AMQP với RabbitMQ**, producer gửi message tới **exchange**, exchange định tuyến tới **queue** thông qua **binding**, còn consumer nhận message từ queue.
- Nhận biết sự khác nhau giữa **một queue có nhiều consumer** và **nhiều queue cùng nhận một sự kiện**, cũng như giữa **event** và **command**.
- Liên hệ kiến trúc với nghiệp vụ thực tế và xác định các điểm cần bảo đảm độ tin cậy: publisher confirm, consumer acknowledgement, retry, dead-letter và idempotency.

## 1. Vì sao cần tách producer, broker và consumer?

Giả sử khách hàng đặt hàng trên một hệ thống thương mại điện tử. Sau khi đơn hàng được ghi nhận, hệ thống cần gửi email xác nhận, cập nhật số liệu phân tích và có thể tạo tác vụ cho kho. Nếu dịch vụ đặt hàng gọi trực tiếp từng dịch vụ bằng HTTP trong cùng một request, thời gian phản hồi phụ thuộc vào tất cả dịch vụ phía sau. Khi dịch vụ email chậm hoặc tạm ngừng hoạt động, thao tác đặt hàng cũng có thể bị ảnh hưởng.

Một cách tổ chức khác là để dịch vụ đặt hàng **phát thông điệp** về việc đơn đã được tạo; các dịch vụ quan tâm sẽ **xử lý thông điệp** theo tốc độ và trách nhiệm riêng:

1. **Producer** (dịch vụ đặt hàng) phát sự kiện đơn hàng đã được tạo.
2. **Broker** (RabbitMQ) nhận thông điệp, định tuyến và giữ thông điệp trong các queue phù hợp.
3. **Consumer** (dịch vụ thông báo, phân tích, ...) nhận thông điệp từ queue và thực hiện công việc.

Mô hình này giúp giảm sự phụ thuộc về thời điểm chạy giữa các dịch vụ, cho phép xử lý nền và mở rộng nhóm consumer. Nó **không tự động bảo đảm** rằng mọi tác vụ sẽ thành công đúng một lần; ứng dụng vẫn phải thiết kế cách xác nhận, thử lại và chống xử lý trùng.

**Spring AMQP** là thư viện tích hợp phía ứng dụng Java/Spring, cung cấp các thành phần như **RabbitTemplate** để gửi message và **@RabbitListener** để nhận message. **RabbitMQ** mới là message broker chịu trách nhiệm về exchange, queue, binding và việc giao message. Hai tên này không chỉ cùng một thành phần.

## 2. Ba vai trò chính

| Vai trò | Ví dụ trong hệ thống đặt hàng | Trách nhiệm chính | Ranh giới trách nhiệm |
| --- | --- | --- | --- |
| **Producer / Publisher** | Order Service | Tạo message phù hợp với nghiệp vụ; chọn exchange, routing key; gửi bằng RabbitTemplate; theo dõi kết quả publish khi cần | Không chọn trực tiếp instance consumer nào xử lý; không mặc định biết email đã được gửi thành công |
| **Broker** | RabbitMQ | Nhận publish, dùng exchange và binding để định tuyến vào queue, lưu/đẩy message theo cấu hình, quản lý phân phối và acknowledgement | Không thực thi nghiệp vụ đặt hàng, gửi email hoặc cập nhật cơ sở dữ liệu của ứng dụng |
| **Consumer** | Notification Service, Audit Service | Nhận message từ queue, kiểm tra dữ liệu, thực hiện tác vụ nghiệp vụ, xử lý lỗi và chống trùng; xác nhận sau khi xử lý thành công | Không quyết định message ban đầu phải được publish khi nào; không coi việc nhận message là bằng chứng tác vụ đã thành công |

Trong RabbitMQ, ba khái niệm hạ tầng thường gặp đi cùng các vai trò trên là:

- **Exchange:** điểm nhận message do producer publish và quyết định queue đích dựa trên loại exchange cùng các binding.
- **Queue:** nơi message chờ được giao cho consumer; một queue có thể có nhiều consumer đang cạnh tranh nhận việc.
- **Binding:** quy tắc nối exchange với queue. Với topic exchange, binding key có thể chứa ký tự đại diện.

**Routing key** là chuỗi producer gắn vào lần publish. Đối với **direct exchange**, một binding thường khớp chính xác routing key; đối với **topic exchange**, dấu **\*** khớp đúng một thành phần ngăn cách bằng dấu chấm và **#** khớp không hoặc nhiều thành phần. **Fanout exchange** chuyển tới tất cả queue đã bind mà không xét routing key. **Headers exchange** có thể định tuyến theo header.

## 3. Luồng đi của một message trong RabbitMQ

Ví dụ: Order Service phát sự kiện với routing key **order.created.v1** vào topic exchange **commerce.events**. Hai queue **notification.order-created** và **audit.order-created** đều có binding phù hợp.

~~~mermaid
flowchart LR
    P["Order Service<br/>Producer<br/>RabbitTemplate"]
    subgraph RMQ["RabbitMQ broker"]
        X{"Topic exchange<br/>commerce.events"}
        Q1[("notification.order-created")]
        Q2[("audit.order-created")]
        X -->|"binding: order.created.v1"| Q1
        X -->|"binding: order.created.v1"| Q2
    end
    N["Notification Service<br/>Consumer<br/>@RabbitListener"]
    A["Audit Service<br/>Consumer<br/>@RabbitListener"]
    P -->|"publish: order.created.v1"| X
    Q1 --> N
    Q2 --> A
~~~

Các bước cần hiểu chính xác:

1. Order Service xây dựng message chứa thông tin cần thiết, ví dụ mã đơn hàng và mã sự kiện.
2. RabbitTemplate publish message tới exchange **commerce.events** với routing key **order.created.v1**. Producer thông thường **không publish trực tiếp tới một consumer**.
3. Exchange đối chiếu binding và đưa **một bản sao vào mỗi queue khớp**. Vì vậy hai queue trên có thể xử lý độc lập cùng một sự kiện.
4. Listener container của Spring AMQP nhận message từ queue và gọi phương thức được đánh dấu **@RabbitListener**.
5. Khi listener xử lý thành công, acknowledgement cho broker biết lần giao message đó có thể được hoàn tất. Nếu consumer lỗi trước khi xác nhận, message có thể được giao lại tùy cấu hình.

Exchange và queue phục vụ hai mục đích khác nhau. **Exchange định tuyến**, còn **queue chứa các message chờ xử lý**. Nếu không có binding phù hợp, message có thể trở thành *unroutable*; việc có lưu hay trả lại cho producer phụ thuộc cấu hình như **mandatory**, **returns** hoặc **alternate exchange**. Không nên giả định cứ gọi publish là chắc chắn có consumer nhận được.

### Một queue có nhiều consumer khác với nhiều queue

| Cách tổ chức | Hành vi | Khi nào dùng |
| --- | --- | --- |
| **Một queue, nhiều instance consumer** | Thông thường mỗi message trong queue được giao cho **một** consumer tại một thời điểm; các instance cùng chia tải | Nhiều worker tạo ảnh, gửi thông báo hoặc thực hiện tác vụ nền |
| **Nhiều queue bind cùng exchange/routing key** | Mỗi queue khớp nhận **bản sao riêng** của message; mỗi nhóm nghiệp vụ tự xử lý | Notification, Audit và Analytics đều cần biết đơn hàng đã tạo |

Consumer nhận lại message do lỗi hoặc reconnect vẫn có thể xảy ra. Vì vậy cụm từ “mỗi message được giao cho một consumer” trong trường hợp chia tải **không đồng nghĩa** với “chỉ được xử lý đúng một lần”.

## 4. Gắn vai trò với ngôn ngữ nghiệp vụ: event và command

RabbitMQ chuyển **message**, nhưng nội dung message nên phản ánh đúng ý nghĩa nghiệp vụ:

| Loại message | Ý nghĩa | Ví dụ | Tổ chức phổ biến |
| --- | --- | --- | --- |
| **Event** | Một sự thật **đã xảy ra**; producer không ra lệnh cho dịch vụ cụ thể | **OrderCreated**, **PaymentCompleted** | Publish lên exchange, nhiều queue nghiệp vụ có thể subscribe qua binding |
| **Command / Job** | Yêu cầu một công việc **cần được thực hiện** | **SendOrderConfirmation**, **GenerateInvoicePdf** | Định tuyến tới queue xử lý công việc, có thể có nhiều worker chia tải |

Việc đặt tên phản ánh mục đích. **OrderCreated** cho biết đơn hàng đã hình thành và có thể được nhiều hệ thống sử dụng. **SendOrderConfirmation** giao một trách nhiệm cụ thể cho nhóm xử lý thông báo. Hai kiểu vẫn đều có thể được gửi bằng RabbitTemplate và nhận bằng @RabbitListener; khác nhau chủ yếu ở hợp đồng nghiệp vụ và cách thiết kế topology.

Với event, producer nên phát **dữ kiện ổn định** và tránh gắn chặt vào hành vi của một consumer. Với command, producer cần mô tả chính xác công việc mong muốn, yêu cầu đầu vào và điều kiện thành công/thất bại.

## 5. Ví dụ Spring AMQP tối giản từ producer tới consumer

Ví dụ sau dùng Java với **spring-boot-starter-amqp**, RabbitMQ đang chạy tại máy phát triển và ứng dụng được cấp quyền khai báo exchange/queue. Để tập trung vào đường đi của message, payload trước tiên chỉ là **orderId** dạng String; ở hệ thống thực tế nên dùng event có định danh riêng và schema rõ ràng như phần tiếp theo.

### 5.1. Khai báo topology

~~~xml
<!-- pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

~~~java
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;

@Configuration
@EnableRabbit
public class OrderAmqpConfig {
    @Bean
    public Declarables orderTopology() {
        TopicExchange exchange = new TopicExchange("commerce.events", true, false);
        Queue notificationQueue =
                QueueBuilder.durable("notification.order-created").build();
        Queue auditQueue =
                QueueBuilder.durable("audit.order-created").build();

        return new Declarables(
                exchange,
                notificationQueue,
                auditQueue,
                BindingBuilder.bind(notificationQueue)
                        .to(exchange).with("order.created.v1"),
                BindingBuilder.bind(auditQueue)
                        .to(exchange).with("order.created.v1")
        );
    }
}
~~~

Ở đây **topic exchange** được khai báo durable, hai **queue** cũng durable, và cả hai cùng bind với routing key **order.created.v1**. Spring AMQP có thể khai báo các thành phần này qua cơ chế RabbitAdmin khi kết nối và quyền truy cập cho phép. **Durable** nghĩa là định nghĩa exchange/queue có thể tồn tại qua lần khởi động lại broker; để bảo vệ dữ liệu message còn cần cân nhắc **message persistence**, xác nhận publish và cấu hình broker phù hợp.

### 5.2. Producer gửi message

~~~java
import java.util.UUID;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishOrderCreated(UUID orderId) {
        rabbitTemplate.convertAndSend(
                "commerce.events",      // exchange
                "order.created.v1",     // routing key
                orderId.toString()      // payload String để minh họa
        );
    }
}
~~~

Phương thức **convertAndSend(exchange, routingKey, payload)** chuyển đổi payload thành AMQP message rồi gửi đi. Lời gọi kết thúc **không có nghĩa** Notification Service đã xử lý xong. Nếu cần biết broker đã chấp nhận publish hoặc thông điệp không tìm được queue đích, producer phải cấu hình và **xử lý** publisher confirms/returns.

### 5.3. Consumer nhận message

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class NotificationConsumer {
    private static final Logger log =
            LoggerFactory.getLogger(NotificationConsumer.class);

    @RabbitListener(queues = "notification.order-created")
    public void onOrderCreated(String orderId) {
        log.info("Da nhan su kien tao don hang: {}", orderId);
        // Trong ứng dụng thật: gọi lớp nghiệp vụ tạo/gửi thông báo
        // và áp dụng cơ chế chống xử lý lặp.
    }
}
~~~

Một consumer tương tự trong Audit Service có thể lắng nghe queue **audit.order-created**. Khi publish một sự kiện khớp binding, **cả hai queue** đều có message của riêng mình. Nếu một dịch vụ đang tắt, queue của dịch vụ đó có thể tích lũy message chờ; việc giữ được message qua sự cố phụ thuộc cấu hình durability, persistence và chính sách broker.

### 5.4. Cấu hình kết nối và xác nhận cơ bản

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

Tài khoản **guest/guest** chỉ phù hợp cho ví dụ RabbitMQ chạy cục bộ theo thiết lập mặc định; môi trường triển khai cần tài khoản riêng, quản lý secret và kết nối được bảo vệ. Các thuộc tính confirms/returns ở trên **bật khả năng nhận tín hiệu**; ứng dụng còn phải đăng ký callback hoặc dùng cơ chế chờ xác nhận và có hành động thích hợp khi publish thất bại. Ví dụ mã tối giản phía trên chưa triển khai bước đó.

Với **acknowledge-mode: auto** của listener container, Spring AMQP thường ACK sau khi phương thức listener hoàn tất thành công; khi phương thức ném lỗi, việc reject/nack/requeue còn phụ thuộc cấu hình container và xử lý lỗi. **AUTO ở đây không có nghĩa broker xác nhận trước khi code nghiệp vụ chạy.**

## 6. Thiết kế nội dung message như một hợp đồng

Payload chỉ có orderId giúp ví dụ ngắn, nhưng không đủ cho hệ thống cần quan sát, mở rộng và chống trùng. Một **event envelope** thực tế có thể là:

~~~json
{
  "eventId": "a17cc0da-6974-4dce-a2ef-73d2a98de712",
  "eventType": "order.created",
  "schemaVersion": 1,
  "occurredAt": "2026-11-26T01:00:00Z",
  "orderId": "7607b2cf-a2f7-41c2-a60d-3c46dbe39df4",
  "customerId": "customer-1042",
  "correlationId": "checkout-8dd4"
}
~~~

Trong tình huống này, **routing key** có thể là **order.created.v1**; **eventType** nói sự kiện gì đã xảy ra; **schemaVersion** phục vụ tiến hóa dữ liệu; **eventId** dùng để phát hiện message trùng; **correlationId** giúp truy vết một thao tác từ request đến các consumer.

Khi dùng object Java/JSON thay cho String, cần cấu hình **MessageConverter** tương thích ở cả phía gửi và nhận, đồng thời thỏa thuận kiểu dữ liệu, format thời gian và quy tắc tương thích schema giữa các dịch vụ. Không nên phụ thuộc vào Java serialization như một hợp đồng liên dịch vụ, và cũng không nên đưa dữ liệu nhạy cảm không cần thiết vào message. Consumer phải kiểm tra dữ liệu đầu vào và có cách xử lý version chưa hỗ trợ.

Một hợp đồng tốt trả lời được: ai phát message, điều gì đã xảy ra, bản tin có thể được nhận lại không, consumer cần trường nào, thay đổi schema sẽ ảnh hưởng hệ thống cũ ra sao?

## 7. Ba mức “đã xong” rất khác nhau

Khi xử lý bất đồng bộ, cần phân biệt:

| Tín hiệu | Ai phát ra? | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- | --- |
| **Lệnh gửi của RabbitTemplate đã chạy** | Thư viện phía producer | Ứng dụng đã thực hiện thao tác publish theo cách gọi hiện tại | Broker chắc chắn đã lưu/định tuyến message |
| **Publisher confirm (ACK)** | Broker trả về cho producer | Broker đã chấp nhận lần publish theo cơ chế confirm | Consumer đã xử lý xong; message chắc chắn có queue đích nếu không kiểm tra routing |
| **Publisher return** khi mandatory và không định tuyến được | Broker trả về cho producer | Message không được route tới queue phù hợp | Đây là lỗi xử lý của consumer |
| **Consumer acknowledgement (ACK)** | Consumer/container gửi về broker | Lần giao message đã được xác nhận, broker có thể loại message khỏi queue | Producer đã nhận phản hồi nghiệp vụ; một thao tác bên ngoài chắc chắn không từng chạy trùng |

Ví dụ, dịch vụ đặt hàng nhận publisher confirm nhưng dịch vụ email có thể vẫn đang chờ trong queue. Ngược lại, email có thể đã được gửi rồi nhưng consumer sập trước khi ACK: broker giao lại message, và email có nguy cơ bị gửi hai lần nếu thiếu idempotency.

**Mặc định nên thiết kế consumer theo hướng chịu được giao lại (at-least-once)** khi dùng xác nhận và retry. Không xây nghiệp vụ dựa trên giả định “exactly once” xuyên suốt từ database, broker tới email hoặc API bên ngoài.

## 8. Xử lý lỗi và bảo đảm độ tin cậy theo đúng vai trò

| Vấn đề | Nơi cần xử lý | Hướng giải quyết |
| --- | --- | --- |
| Đơn hàng đã commit vào DB nhưng chưa publish được event | Producer và DB | **Transactional outbox**: lưu dữ kiện cần publish cùng giao dịch với đơn hàng, sau đó worker gửi và đánh dấu đã chuyển |
| Publish bị từ chối, mất kết nối hoặc routing không khớp | Producer + broker | Publisher confirms, returns/mandatory, giám sát và thử publish lại với chính sách phù hợp |
| Consumer sập trước khi ACK | Broker + consumer | Cho phép redelivery; consumer nhận diện message trùng dựa trên **eventId** |
| API phụ trợ tạm thời lỗi, xử lý chưa thành công | Consumer | Retry có giới hạn, thời gian giãn cách hoặc delayed retry; không requeue vô hạn gây vòng lặp nóng |
| Payload sai hoặc lỗi không thể tự phục hồi | Consumer + broker | Chuyển sang **dead-letter queue (DLQ)**, lưu lý do, cảnh báo và có quy trình xử lý lại |
| Queue tồn đọng nhiều message | Vận hành broker + consumer | Theo dõi độ dài queue, tốc độ publish/consume, số message unacked, thời gian xử lý; điều chỉnh concurrency/prefetch khi phù hợp |

**Transactional outbox** giải quyết khe hở giữa việc commit dữ liệu nghiệp vụ và việc publish: cùng một transaction lưu cả đơn hàng và bản ghi outbox. Một tiến trình khác gửi các bản ghi chưa gửi tới RabbitMQ. Outbox vẫn có thể gửi lặp nếu tiến trình sập sau publish nhưng trước khi đánh dấu đã gửi, nên **consumer vẫn cần idempotency**.

**Idempotency** có nghĩa là nhận lại cùng một message không tạo thêm tác dụng nghiệp vụ. Chẳng hạn consumer ghi eventId vào bảng có khóa duy nhất cùng giao dịch với việc tạo bản ghi thông báo. Nếu eventId đã tồn tại thì bỏ qua phần ghi trùng. Với tác động ngoài DB như gửi email hoặc gọi nhà cung cấp thanh toán, cần thêm thiết kế phù hợp, chẳng hạn yêu cầu idempotency key từ nhà cung cấp hoặc một workflow kiểm soát trạng thái gửi.

**Retry** chỉ nên áp dụng cho lỗi có khả năng phục hồi, chẳng hạn timeout tạm thời. Message độc hại, schema không hỗ trợ hoặc thiếu dữ liệu bắt buộc thường cần chuyển sang nhánh lỗi/DLQ thay vì thử lại mãi. Một dead-letter exchange và dead-letter queue phải được khai báo/bind, đồng thời cấu hình chính sách dead-letter ở queue nguồn để message thực sự có nơi đến.

Ngoài ra, khi chạy nhiều consumer, tăng concurrency hoặc đưa message vào retry, **không nên suy luận rằng mọi sự kiện liên quan một đơn hàng sẽ luôn được xử lý theo đúng thứ tự**. Nếu nghiệp vụ phụ thuộc thứ tự, cần thiết kế khóa phân vùng, phiên bản trạng thái hoặc cơ chế tuần tự hóa phù hợp.

## 9. Những ứng dụng nghiệp vụ phù hợp

| Bài toán | Producer phát gì? | Queue/consumer làm gì? | Giá trị nhận được |
| --- | --- | --- | --- |
| **Gửi thông báo đơn hàng** | Event **OrderCreated** | Notification Service tạo yêu cầu email/SMS | Đặt hàng phản hồi nhanh, dịch vụ thông báo xử lý độc lập |
| **Ghi nhận audit** | Event **PaymentCompleted** | Audit Service lưu dấu vết nghiệp vụ | Có kênh quan sát riêng, không cài chặt logic audit vào thanh toán |
| **Xử lý file/ảnh** | Command **GenerateThumbnail** | Nhiều worker chia tải trên một queue | Có thể tăng số worker theo khối lượng xử lý |
| **Đồng bộ chỉ mục tìm kiếm** | Event **ProductUpdated** | Search Indexer cập nhật chỉ mục | Thay đổi dữ liệu gốc không phải chờ lập chỉ mục |
| **Quy trình nhiều bước** | Event/command theo từng bước | Các consumer điều phối trạng thái, xử lý lỗi/bù trừ | Phù hợp quy trình dài nhưng đòi hỏi thiết kế trạng thái, timeout và bù trừ |

Không phải thao tác nào cũng nên chuyển sang message. Nếu caller bắt buộc cần **kết quả tức thời** để quyết định bước tiếp theo, giao tiếp đồng bộ như HTTP/gRPC hoặc thao tác trong transaction có thể dễ hiểu hơn. Khi chọn bất đồng bộ, API nên thể hiện rõ trạng thái: ví dụ tạo đơn hàng trả về orderId và trạng thái **PENDING**, còn trạng thái gửi email hoặc chuẩn bị hàng được theo dõi riêng. Cần xác định rõ dữ liệu nào là nguồn sự thật và mức độ chấp nhận được của **eventual consistency**.

## 10. Các dấu hiệu cần theo dõi khi vận hành

- **Ready messages:** số message còn chờ; tăng liên tục có thể do consumer chậm hoặc ngừng hoạt động.
- **Unacked messages:** message đã giao nhưng chưa ACK; cao bất thường có thể do xử lý lâu, treo hoặc cấu hình prefetch/concurrency không phù hợp.
- **Publish, deliver, acknowledge rates:** tốc độ vào, giao, hoàn tất; giúp nhận ra điểm nghẽn.
- **Redeliveries và dead-letter:** dấu hiệu lỗi lặp, dữ liệu không hợp lệ hoặc dịch vụ phụ trợ không ổn định.
- **Publisher confirms/returns và logs theo correlationId:** giúp phân biệt lỗi publish/routing với lỗi xử lý nghiệp vụ.

Độ dài queue bằng 0 **không đủ** để kết luận quy trình đã thành công: message có thể đang unacked, đã chuyển sang DLQ hoặc đã ACK nhưng tác động nghiệp vụ chưa được kiểm soát đúng. Nên đặt chỉ số theo cả broker **và** kết quả nghiệp vụ, ví dụ số thông báo gửi thành công/thất bại.

## 11. Bài tập kiểm tra hiểu biết

1. Khởi chạy RabbitMQ, khai báo topology ở phần 5, publish một orderId. Xác định queue nào nhận message; bổ sung một listener cho **audit.order-created** và quan sát cả hai nhóm xử lý.
2. Chạy thêm một instance consumer cùng lắng nghe **notification.order-created**, rồi publish nhiều message. Quan sát cách các instance chia tải trong **một queue**; đối chiếu với trường hợp **hai queue** cùng bind exchange.
3. Tạm dừng Notification Service trong khi vẫn publish. Quan sát các message chờ trong queue; khởi động lại consumer và kiểm tra việc xử lý tiếp tục. Lặp lại với lỗi ném ra trước ACK và nghiên cứu vì sao có thể nhận lại message.
4. Gỡ một binding, publish lại và kiểm tra trường hợp không định tuyến được; phân biệt **publisher return** với **consumer exception**.
5. Thiết kế payload có **eventId**, giả lập nhận hai lần cùng một event, rồi mô tả cách dùng khóa duy nhất trong database để ngăn tạo trùng bản ghi nghiệp vụ. Xác định thêm trường hợp phải cần outbox.

**Câu hỏi tự đánh giá:** Nếu Order Service publish thành công nhưng Notification Service đang tắt, ai giữ message? Nếu có hai instance Notification Service nghe cùng một queue, mỗi instance có nhận một bản sao không? Nếu publisher đã nhận confirm, có thể báo người dùng email đã được gửi thành công chưa? Hãy trả lời bằng vai trò của exchange, queue, producer, broker và consumer trong mô hình trên.

---

**Ghi nhớ:** Producer phát thông điệp nghiệp vụ; RabbitMQ định tuyến qua exchange và binding vào queue; consumer nhận và thực hiện nghiệp vụ. **RabbitTemplate** và **@RabbitListener** là hai điểm tích hợp Spring AMQP ở hai đầu luồng. Muốn hệ thống bất đồng bộ đáng tin cậy, phải thiết kế cả đường **publish**, **route**, **process**, **ack/retry** và **xử lý trùng lặp**.
