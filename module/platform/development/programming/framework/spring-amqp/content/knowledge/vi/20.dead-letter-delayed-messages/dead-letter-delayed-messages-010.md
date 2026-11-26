# Delayed-message exchange plugin khi được hỗ trợ và cài đặt

## 1. Vì sao cần delayed-message exchange?

Trong hệ thống dùng **Spring AMQP và RabbitMQ**, có những thông điệp phải được xử lý **sau một khoảng thời gian** thay vì ngay khi phát sinh: nhắc thanh toán sau 15 phút, gửi thông báo sau vài giây để hệ thống khác kịp đồng bộ, hoặc kiểm tra lại trạng thái đơn hàng sau một khoảng chờ.

RabbitMQ thông thường chuyển message từ exchange tới queue theo binding ngay lúc publish. **RabbitMQ Delayed Message Exchange plugin** bổ sung loại exchange **x-delayed-message**: producer gửi message kèm header **x-delay** (đơn vị mili giây); exchange giữ message trong khoảng chờ, rồi mới định tuyến tới queue bằng routing key và các binding hiện có.

Plugin này là **tính năng tùy chọn của broker**. Mã Spring AMQP sử dụng delayed exchange chỉ chạy được khi phiên bản RabbitMQ tương thích với plugin và plugin đã được cài, bật trên những node cần thiết. Vì thế, quyết định kiến trúc phải bao gồm cả **phương án khi plugin không được hỗ trợ**.

Sau bài này, bạn có thể:

- Giải thích khác biệt giữa trì hoãn bằng delayed exchange và trì hoãn bằng TTL + dead-letter exchange (DLX).
- Kiểm tra điều kiện triển khai plugin, khai báo exchange/queue/binding bằng Spring AMQP và đặt độ trễ khi gửi bằng RabbitTemplate.
- Phân biệt việc message được broker nhận, hết thời gian chờ, được định tuyến và thực sự được consumer xử lý.
- Thiết kế retry, dead-letter, quan sát và phương án dự phòng phù hợp.

## 2. Cơ chế hoạt động

~~~text
Spring Boot / RabbitTemplate
         |
         | publish: exchange = orders.reminder.delayed
         | routing key = reminder
         | headers["x-delay"] = 15 * 60 * 1000
         v
RabbitMQ exchange: type = x-delayed-message
         |  tạm giữ message theo thời gian x-delay
         |  (chưa nằm trong queue đích)
         v
Hết thời gian chờ -> định tuyến theo x-delayed-type và binding
         |
         v
Queue: orders.reminder.q
         |
         v
@RabbitListener -> kiểm tra trạng thái đơn -> xử lý -> ACK
~~~

Một delayed exchange cần hai thông tin khác nhau:

| Thành phần | Ý nghĩa |
| --- | --- |
| Exchange type = **x-delayed-message** | Kích hoạt khả năng trì hoãn của plugin. |
| Exchange argument **x-delayed-type = direct** | Sau khi hết thời gian chờ, định tuyến như direct exchange. Có thể dùng kiểu định tuyến thích hợp khác mà plugin hỗ trợ, chẳng hạn topic. |
| Message header **x-delay = 900000** | Trì hoãn khoảng 900.000 ms, tương đương 15 phút, tính từ khi broker nhận và xử lý message. |
| Routing key **reminder** | Chỉ ra queue đích theo binding tại thời điểm message được định tuyến. |

Ví dụ: ứng dụng gửi nhắc thanh toán lúc **10:00** với x-delay = 900000. Khoảng **10:15**, plugin đưa message qua bước routing, sau đó consumer mới có thể lấy message từ queue. **10:15 không phải cam kết consumer bắt đầu đúng thời điểm đó**: broker, queue, tải xử lý, lịch chạy consumer và network đều có thể làm thời điểm thực tế muộn hơn.

**Đừng nhầm delayed exchange với DLX.** Delayed exchange trì hoãn việc định tuyến **ban đầu**. Dead-letter exchange nhận message bị từ chối, hết TTL, vượt giới hạn độ dài queue hoặc gặp một số tình huống dead-letter khác. Một hệ thống có thể dùng cả hai: delayed exchange để hẹn xử lý, còn DLX để tách message xử lý thất bại.

## 3. Điều kiện sử dụng và cài plugin

### 3.1. Kiểm tra trước khi chọn chiến lược

Việc có dùng plugin hay không phải được xác nhận ở **môi trường RabbitMQ thực tế** (dev, staging và production):

1. Xác định **phiên bản RabbitMQ** và tải **bản phát hành plugin tương thích chính xác** với phiên bản đó, theo tài liệu phát hành của RabbitMQ/plugin. Không mặc định mọi RabbitMQ image đều tích hợp plugin.
2. Đưa tệp plugin **.ez** vào đường dẫn plugins của RabbitMQ nếu bản triển khai chưa có sẵn. Với container, đóng gói vào image hoặc mount một cách ổn định để lần khởi động sau không mất plugin.
3. Bật plugin trên node tương ứng. Với cluster, kiểm tra cấu hình trên từng node có thể phục vụ exchange này và kiểm thử cả tình huống chuyển node.
4. Xác nhận plugin đã bật, thử khai báo một exchange kiểu x-delayed-message, và kiểm thử độ trễ thực tế trước khi bật tính năng ở ứng dụng.

Các lệnh thực hiện **trên máy/container RabbitMQ**, sau khi đã cài tệp plugin tương thích:

~~~bash
rabbitmq-plugins enable rabbitmq_delayed_message_exchange
rabbitmq-plugins list -e

# Sau khi ứng dụng khai báo exchange, kiểm tra type và arguments:
rabbitmqctl list_exchanges name type arguments
~~~

Tên plugin là **rabbitmq_delayed_message_exchange**; tên loại exchange mà plugin cung cấp là **x-delayed-message**. Hai tên này không thay thế cho nhau.

Nếu RabbitMQ báo không nhận ra loại exchange **x-delayed-message**, cần kiểm tra plugin/version/node. Nếu exchange cùng tên đã tồn tại với **type khác**, RabbitMQ cũng không cho khai báo lại với type mới: hãy lập kế hoạch đổi tên hoặc chuyển topology và producer/consumer phù hợp, không sửa cấu hình cũ một cách tùy tiện.

### 3.2. Cấu hình tối thiểu phía ứng dụng

Ví dụ dưới đây dùng Spring Boot với dependency **spring-boot-starter-amqp** và một RabbitMQ broker đã bật plugin. Phần cấu hình kết nối (host, port, username, password, TLS...) được quản lý qua cấu hình ứng dụng như các dịch vụ Spring AMQP khác.

~~~xml
<!-- Maven: đặt trong <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Lưu ý: thêm starter chỉ cung cấp thư viện Spring AMQP; **nó không tự cài RabbitMQ plugin** lên broker.

## 4. Khai báo delayed exchange bằng Spring AMQP

Spring AMQP hỗ trợ đánh dấu một exchange là **delayed**. Khi **RabbitAdmin** khai báo exchange đó, nó sử dụng loại broker **x-delayed-message** cùng argument **x-delayed-type** tương ứng. Ví dụ dưới dùng hành vi định tuyến **direct**:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.ExchangeBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReminderAmqpConfig {
    public static final String EXCHANGE = "orders.reminder.delayed";
    public static final String QUEUE = "orders.reminder.q";
    public static final String ROUTING_KEY = "reminder";

    @Bean
    DirectExchange reminderDelayedExchange() {
        return ExchangeBuilder.directExchange(EXCHANGE)
                .durable(true)
                .delayed()
                .build();
    }

    @Bean
    Queue reminderQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding reminderBinding(Queue reminderQueue,
                            DirectExchange reminderDelayedExchange) {
        return BindingBuilder.bind(reminderQueue)
                .to(reminderDelayedExchange)
                .with(ROUTING_KEY);
    }
}
~~~

Ở phía Java, bean có kiểu **DirectExchange** vì ứng dụng muốn routing theo routing key. Trên broker, khi dùng khai báo delayed của Spring AMQP, exchange tương ứng có **type x-delayed-message** và argument **x-delayed-type = direct**. Queue và binding vẫn được khai báo theo cách thông thường.

Ví dụ khai báo thủ công trực tiếp qua RabbitMQ API cũng có thể dùng exchange type **x-delayed-message** và argument **x-delayed-type**. Trong Spring AMQP, cách dùng **ExchangeBuilder...delayed()** giúp giữ lại kiểu exchange quen thuộc và cách bind tương ứng.

**Lưu ý khi khởi động:** nếu plugin chưa bật, việc tự động khai báo exchange có thể thất bại. Không nên âm thầm bỏ qua lỗi rồi coi message đã được trì hoãn; ứng dụng cần chuyển sang cấu hình dự phòng đã được thiết kế, hoặc báo lỗi cấu hình rõ ràng.

## 5. Gửi message có độ trễ với RabbitTemplate

**MessagePostProcessor** cho phép gắn độ trễ riêng lên từng message. Trong Spring AMQP, gọi **MessageProperties.setDelay(int)** để đặt x-delay. Mẫu bên dưới dùng payload String để tập trung vào cơ chế trì hoãn; nếu chuyển sang DTO JSON, cần cấu hình message converter và hợp đồng dữ liệu phù hợp.

~~~java
import java.time.Duration;

import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ReminderPublisher {
    private final RabbitTemplate rabbitTemplate;

    public ReminderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void schedulePaymentReminder(String orderId, Duration delay) {
        long delayMillis = delay.toMillis();
        if (delayMillis < 0 || delayMillis > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Unsupported delay: " + delay);
        }

        rabbitTemplate.convertAndSend(
                ReminderAmqpConfig.EXCHANGE,
                ReminderAmqpConfig.ROUTING_KEY,
                orderId,
                message -> {
                    message.getMessageProperties()
                            .setDelay((int) delayMillis);
                    message.getMessageProperties()
                            .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    return message;
                }
        );
    }
}
~~~

Ví dụ gọi từ business logic:

~~~java
reminderPublisher.schedulePaymentReminder(
        "ORDER-123",
        Duration.ofMinutes(15)
);
~~~

Hai message gửi cùng routing key nhưng lần lượt có độ trễ 5 giây và 15 phút sẽ có thời điểm được đưa vào queue khác nhau; không phải tạo một queue riêng cho mỗi thời gian chờ.

Trong ví dụ trên, **int** của API setDelay giới hạn giá trị có thể truyền qua phương thức này (tối đa khoảng 24,8 ngày). Giới hạn của plugin/broker và các bảo đảm lưu trữ còn phụ thuộc phiên bản triển khai; tránh dùng delayed exchange như bộ lập lịch dài hạn, nhất là khi cần thời điểm thực thi nghiêm ngặt hoặc khả năng hủy lịch.

Độ bền exchange, queue và cờ persistent của message hữu ích cho tính tin cậy, nhưng **không thay thế việc kiểm thử khả năng khôi phục message đang chờ của chính plugin** khi node restart, failover hoặc nâng cấp.

## 6. Nhận message và xử lý nghiệp vụ an toàn

Consumer chỉ nhận message **sau khi nó đã được chuyển vào queue**:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentReminderListener {
    private final OrderService orderService;

    public PaymentReminderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @RabbitListener(queues = ReminderAmqpConfig.QUEUE)
    public void onReminder(String orderId) {
        // Ví dụ nghiệp vụ: chỉ nhắc nếu đơn vẫn chưa thanh toán.
        // OrderService là thành phần nghiệp vụ do ứng dụng cung cấp.
        if (orderService.isUnpaid(orderId)) {
            orderService.sendReminderOnce(orderId);
        }
    }
}
~~~

Ở đây, **OrderService** là interface/dịch vụ nghiệp vụ minh họa, không phải lớp có sẵn của Spring. Hàm **sendReminderOnce** cần bảo đảm idempotency, ví dụ lưu dấu đã gửi theo khóa gồm mã đơn và loại nhắc. Nếu đơn đã thanh toán trong 15 phút chờ, listener kiểm tra trạng thái mới và bỏ qua message.

Các điểm thiết kế cần nhớ:

- **ACK không đồng nghĩa publish thành công:** publisher confirm chỉ liên quan việc broker nhận/xử lý publish theo cơ chế xác nhận được cấu hình; consumer ACK xác nhận xử lý tại phía consumer. Không có một tín hiệu duy nhất bao phủ cả vòng đời.
- **Idempotency:** RabbitMQ và retry có thể dẫn tới xử lý lại. Không gửi email/trừ tiền/lập hóa đơn hai lần chỉ vì message được phát lại.
- **Retry có giới hạn và DLQ:** xử lý lỗi tạm thời bằng retry/backoff phù hợp; khi vượt ngưỡng, đưa message sang dead-letter queue để kiểm tra. Tránh requeue vô hạn gây vòng lặp tiêu thụ CPU.
- **Không có thao tác hủy lịch tổng quát theo message trong plugin:** khi cần hủy tác vụ đã hẹn, dùng trạng thái nghiệp vụ hoặc bảng lịch tác vụ để quyết định bỏ qua lúc consumer nhận.

Nếu consumer ném exception, cách ACK/NACK/requeue thực tế phụ thuộc cấu hình listener container và retry của ứng dụng. Không nên mặc định mọi exception đều tự chuyển vào DLQ: muốn dead-letter cần khai báo DLX và đặt chính sách từ chối/retry thích hợp.

## 7. Kiểm chứng hành vi và quan sát hệ thống

Một cách thử nghiệm nhanh trên môi trường đã cài plugin:

1. Khởi động ứng dụng, xác minh RabbitMQ đã có exchange **orders.reminder.delayed**, queue **orders.reminder.q** và binding với routing key **reminder**.
2. Gửi message A với delay = **10.000 ms** và ghi log thời điểm publish, ví dụ **10:00:00**.
3. Kiểm tra queue đích ngay sau publish: message A thường **chưa xuất hiện trong queue** do còn đang chờ ở exchange/plugin.
4. Quan sát listener: message chỉ sẵn sàng xử lý sau khoảng **10 giây**; log thời điểm nhận và độ lệch so với hạn dự kiến.
5. Thử delay khác nhau (1 giây và 10 giây), nhiều message, consumer tạm dừng, publish khi thiếu binding, rồi kiểm thử retry/DLQ, restart/failover theo chính sách vận hành.

Một số phiên bản/đường xử lý của plugin có thể chuyển header **x-delay** thành giá trị âm khi message được giao, biểu thị rằng độ trễ đã được áp dụng. Spring AMQP cũng có thể bộc lộ metadata độ trễ nhận được qua **receivedDelay** tùy phiên bản. **Đừng dựa vào header này như đồng hồ chính xác**; hãy chủ động ghi các trường nghiệp vụ như **eventId**, **scheduledAt** và **notBefore** nếu cần đo độ trễ thực tế.

Nên theo dõi ít nhất: số message producer gửi thành công/thất bại; lỗi khai báo exchange; độ trễ giữa **notBefore** và thời điểm consumer bắt đầu; số lần xử lý lại; số message ở DLQ; tình trạng node/plugin và khả năng khôi phục sau sự cố. **Queue depth của queue đích không đại diện cho số message còn đang chờ trong delayed exchange**.

Lưu ý thêm: binding được áp dụng khi plugin định tuyến message sau khoảng chờ. Việc thay đổi hoặc xóa binding/queue trong lúc message đang chờ có thể khiến kết quả định tuyến khác dự kiến. Cần kiểm thử trường hợp không còn đường định tuyến; tránh dựa vào publisher return tại thời điểm gửi ban đầu để phát hiện mọi trường hợp này.

## 8. Khi không thể cài plugin: TTL kết hợp DLX

Nếu tổ chức không cho cài plugin, phiên bản RabbitMQ không tương thích hoặc chính sách vận hành yêu cầu chỉ dùng tính năng broker có sẵn, có thể dùng **TTL + dead-letter exchange**:

~~~text
Producer -> queue chờ "orders.wait.10s" (TTL = 10.000 ms)
             |
             | message hết TTL, được dead-letter
             v
         direct exchange "orders.work"
             |
             | routing key = reminder
             v
         queue "orders.reminder.q" -> @RabbitListener
~~~

Minh họa khai báo một queue chờ có TTL cố định 10 giây:

~~~java
@Bean
Queue waitingQueue() {
    return QueueBuilder.durable("orders.wait.10s")
            .ttl(10_000)
            .deadLetterExchange("orders.work")
            .deadLetterRoutingKey("reminder")
            .build();
}
~~~

Để ví dụ này chạy, phải khai báo thêm **orders.work** (direct exchange), queue nhận **orders.reminder.q** và binding **reminder**; producer publish vào queue chờ (qua default exchange với routing key là tên queue, hoặc qua exchange riêng). **Không đặt consumer trực tiếp trên queue chờ**, vì consumer có thể lấy message trước khi hết TTL.

| Tiêu chí | Delayed-message exchange plugin | TTL + DLX |
| --- | --- | --- |
| Điều kiện triển khai | Cần plugin đúng phiên bản và được bật. | Dùng các tính năng chuẩn của RabbitMQ. |
| Độ trễ từng message | Đặt bằng x-delay khi publish, có thể khác nhau trên cùng exchange. | Dùng TTL ở queue hoặc message; nhiều TTL trên cùng queue có thể gây chặn ở đầu hàng đợi. |
| Thời điểm tới queue làm việc | Sau khi plugin kết thúc thời gian chờ rồi routing. | Sau khi message hết TTL và được dead-letter/routing. |
| Điểm cần vận hành | Tương thích plugin, khôi phục message đang chờ, quan sát plugin. | Topology queue chờ/DLX, TTL, thứ tự và head-of-line blocking. |
| Tính chính xác thời gian | Best-effort; không phải bộ lập lịch chính xác tuyệt đối. | Best-effort; có thể trễ do TTL, thứ tự queue và tải broker. |

Với nhiều TTL khác nhau trên **cùng một queue**, message hết hạn phía sau có thể bị giữ bởi message chưa hết hạn phía trước (**head-of-line blocking**). Có thể dùng các queue chờ theo nhóm độ trễ cố định hoặc một scheduler/bảng tác vụ riêng nếu yêu cầu phức tạp. Nếu cần lập lịch nhiều ngày/tháng, hủy, sửa lịch, audit hoặc cam kết thực thi ở thời điểm xác định, nên cân nhắc **scheduler bền vững chuyên dụng** hoặc database-backed job scheduling.

## 9. Những lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Ứng dụng không tạo được delayed exchange | Plugin chưa được cài/bật, không tương thích, node không có plugin. | Kiểm tra rabbitmq-plugins, phiên bản plugin/broker và log khai báo exchange. |
| Lỗi PRECONDITION_FAILED khi khai báo | Exchange cùng tên đã tồn tại nhưng type/argument khác. | Kiểm tra topology hiện hữu; lập kế hoạch đổi tên/migration thay vì khai báo đè. |
| Message đến queue ngay lập tức | Không gắn x-delay, gửi nhầm exchange hoặc exchange khai báo không delayed. | Kiểm tra MessagePostProcessor, tên exchange, type thực tế và routing key. |
| Đợi hết delay vẫn không nhận được message | Binding sai, queue/consumer chưa sẵn sàng, plugin gặp sự cố, message không routable. | Kiểm tra exchange, binding, queue, consumer, broker log và test đường định tuyến. |
| Message xử lý nhiều lần | Retry, redelivery hoặc consumer chết trước ACK. | Thiết lập idempotency, retry có giới hạn và dead-letter. |
| Thấy queue depth = 0 dù vừa publish | Message còn trong phần lưu trữ chờ của plugin, chưa routing tới queue. | Ghi log thời điểm publish/notBefore; không dùng riêng queue depth để đo message pending. |

## 10. Bài thực hành

**Bối cảnh:** Khi tạo đơn hàng chưa thanh toán, hệ thống muốn nhắc sau 30 giây. Nếu đơn được thanh toán trong lúc chờ, không gửi nhắc. Khi gửi nhắc gặp lỗi tạm thời, phải retry có giới hạn; nếu vẫn thất bại, cần DLQ.

**Yêu cầu thực hiện:**

1. Trên broker đã cài plugin, khai báo delayed direct exchange, queue nhận và binding.
2. Publish ID đơn hàng với delay 30.000 ms bằng RabbitTemplate; log **orderId**, **publishedAt**, **notBefore**.
3. Ở listener, tra trạng thái đơn mới nhất; chỉ gửi nhắc cho đơn chưa thanh toán; đảm bảo chỉ gửi một lần theo mã nghiệp vụ.
4. Giả lập lỗi xử lý và kiểm tra cơ chế retry + DLQ đã cấu hình, tránh requeue vô hạn.
5. Thử lại trên môi trường **không có plugin** bằng topology TTL + DLX được khai báo riêng, rồi so sánh thời điểm nhận và độ phức tạp vận hành.

**Câu hỏi tự kiểm tra:** Nếu message A có x-delay 30 giây nhưng binding bị xóa ở giây thứ 20, việc producer đã nhận publisher confirm có chứng minh A sẽ tới queue không? **Không.** Publisher confirm không phải bằng chứng consumer đã nhận hoặc xử lý thành công; routing được thực hiện khi delay kết thúc, lúc đó topology đã thay đổi.

## 11. Ghi nhớ

**Delayed-message exchange** phù hợp khi RabbitMQ đã được quản trị hỗ trợ plugin và ứng dụng cần độ trễ linh hoạt cho từng message. Với Spring AMQP, khai báo exchange bằng **ExchangeBuilder...delayed()**, gửi qua **RabbitTemplate** với **setDelay(...)**, nhận bằng **@RabbitListener** và kiểm tra kết quả theo thời điểm nghiệp vụ. Để dùng đáng tin cậy, phải xác minh version/plugin, kiểm thử hoạt động khi broker lỗi, bảo đảm idempotency, có retry/DLQ và một giải pháp khác như **TTL + DLX** khi plugin không sẵn có.
