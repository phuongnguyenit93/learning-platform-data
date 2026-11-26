# Heartbeat, phát hiện mất kết nối và thời gian phục hồi

Trong một hệ thống dùng **RabbitMQ và Spring AMQP**, kết nối giữa ứng dụng và broker có thể mất bất cứ lúc nào: broker khởi động lại, mạng đứt ngắn hạn, thiết bị mạng âm thầm loại bỏ kết nối TCP nhàn rỗi, JVM bị dừng lâu do GC, hoặc broker không kịp phản hồi khi tài nguyên cạn. Một socket còn mở ở phía ứng dụng **không đồng nghĩa** đường truyền tới broker vẫn hoạt động.

Vấn đề vận hành không dừng ở “ứng dụng có kết nối lại được không”. Cần biết **khi nào phát hiện lỗi, bao lâu bắt đầu thử lại, khi nào consumer thực sự nhận message trở lại, và các message đang gửi hoặc đang xử lý có kết quả gì**. Những khoảng thời gian và trạng thái không chắc chắn này quyết định độ tin cậy đầu cuối.

Bài thuộc chương **Phục hồi kết nối** của module **SPRING_AMQP**. Nội dung liên kết cơ chế heartbeat RabbitMQ với `CachingConnectionFactory`, `RabbitTemplate`, `@RabbitListener`, exchange–queue–binding, publisher confirms, acknowledgment, retry, dead-letter và quan sát hệ thống. Mục tiêu là thiết kế phục hồi kết nối có thể đo lường, đồng thời xử lý an toàn nguy cơ **mất message, gửi lại trùng và xử lý trùng**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao TCP có thể rơi vào trạng thái *half-open* và heartbeat AMQP giúp phát hiện kết nối không còn hoạt động.
2. Phân biệt **heartbeat timeout**, **connection timeout**, **thời gian chờ thử kết nối lại**, **consumer recovery** và **message retry**.
3. Cấu hình heartbeat cho RabbitMQ/Spring Boot; hiểu cách hai phía thương lượng giá trị heartbeat.
4. Nêu rõ vai trò của Spring AMQP trong phục hồi connection, channel, listener và khai báo topology; tránh cấu hình hai cơ chế recovery chồng chéo.
5. Xây timeline đo **thời gian gián đoạn đầu cuối**, không đánh đồng thời gian mở lại socket với thời gian xử lý trở lại.
6. Nhận diện kết quả publish chưa xác định sau mất kết nối và thiết kế publisher confirms/returns cùng outbox.
7. Giải thích vì sao consumer có thể nhận lại message sau DB commit nhưng trước ACK, rồi sử dụng idempotency để ngăn tác dụng phụ trùng.
8. Kiểm thử restart broker, mất mạng, heartbeat false positive và phục hồi topology bằng các thước đo cụ thể.

## 2. Tình huống: kết nối trông vẫn bình thường nhưng message ngừng đi

Giả sử dịch vụ Order có hai thành phần:

- `RabbitTemplate` publish sự kiện `OrderPaid` đến `orders.events.exchange` theo routing key `order.paid`.
- `@RabbitListener` của Inventory đọc từ `inventory.order-paid.queue` và cập nhật tồn kho.

Một thiết bị mạng làm mất đường truyền trong lúc không có dữ liệu trao đổi. Ở thời điểm đó, cả JVM lẫn broker có thể chưa biết ngay rằng phía kia đã không còn liên lạc được.

~~~mermaid
sequenceDiagram
    participant P as Spring AMQP application
    participant N as Network
    participant B as RabbitMQ
    P->>B: Kết nối AMQP đã hoạt động
    Note over N: Đường truyền lỗi / half-open
    P--xB: TCP traffic không tới được broker
    Note over P,B: Heartbeat định kỳ hoặc traffic khác
    Note over P,B: Một phía phát hiện mất hoạt động
    P->>P: Đóng connection/channel lỗi
    P->>B: Thử thiết lập kết nối mới
    B-->>P: Kết nối AMQP mới thành công
    P->>P: Khôi phục listener và consumer
    B->>P: Delivery tiếp tục
~~~

Nếu không có heartbeat, một kết nối TCP half-open có thể tồn tại khá lâu tùy hệ điều hành và thiết bị mạng. **TCP keepalive** có thể hỗ trợ, nhưng các khoảng thời gian mặc định ở tầng hệ điều hành thường không được thiết kế cho phát hiện nhanh mất kết nối ứng dụng. Heartbeat AMQP là một công cụ bổ sung để nhận biết kết nối không còn trao đổi frame.

**Lưu ý:** không phải sự cố nào cũng chờ tới heartbeat. Lỗi socket rõ ràng, broker chủ động đóng connection, exception khi publish hoặc kết nối bị reset có thể được phát hiện ngay. Heartbeat chủ yếu giúp nhận diện trường hợp kết nối im lặng mà ứng dụng chưa nhận được tín hiệu đóng.

## 3. Heartbeat AMQP là gì?

RabbitMQ hỗ trợ **heartbeat** ở cấp **AMQP connection**. Sau khi connection được mở, hai phía có thể trao đổi heartbeat frames để chứng minh đường truyền còn hoạt động. Các frame AMQP thông thường cũng được tính là hoạt động của connection; khi liên tục có traffic, không nhất thiết phải gửi riêng một frame heartbeat đúng mỗi chu kỳ.

Một cách hiểu cơ bản:

- **Heartbeat timeout** là khoảng thời gian phát hiện mất hoạt động được các phía thương lượng, tính bằng giây.
- Heartbeat frames thường được gửi xấp xỉ **mỗi nửa heartbeat timeout** khi connection không có traffic khác.
- Nếu hai chu kỳ heartbeat liên tiếp không có tín hiệu hoạt động phù hợp, phía giám sát có thể kết luận peer không phản hồi và đóng connection.
- Thời gian phát hiện thực tế phụ thuộc vào thời điểm traffic cuối cùng, scheduler, tải hệ thống và tình huống mạng; **không phải một deadline chính xác tuyệt đối**.

Ví dụ, nếu negotiated heartbeat timeout là 30 giây thì heartbeat có thể được gửi khoảng 15 giây một lần trong thời gian nhàn rỗi. Đừng đọc cấu hình `30` thành “cứ 30 giây mới gửi một heartbeat” hoặc “chắc chắn phát hiện mọi lỗi sau đúng 30 giây”.

### 3.1. Giá trị heartbeat được thương lượng

RabbitMQ server và AMQP client đều có giá trị heartbeat đề xuất. Theo quy tắc thương lượng thường dùng của RabbitMQ:

- Nếu **cả hai giá trị khác 0**, chọn giá trị **nhỏ hơn**.
- Nếu **một phía bằng 0**, phía còn lại khác 0, dùng giá trị khác 0.
- Nếu **cả hai đều bằng 0**, heartbeat được tắt.

Bởi vậy, đặt heartbeat phía client bằng 30 giây **không nhất thiết** khiến connection dùng đúng 30 giây nếu phía server đề xuất một giá trị dương nhỏ hơn. Cần kiểm tra negotiated value trên connection thực, thay vì chỉ nhìn file cấu hình.

| Client đề xuất | Broker đề xuất | Heartbeat được thương lượng |
| ---: | ---: | ---: |
| 30 s | 60 s | 30 s |
| 60 s | 20 s | 20 s |
| 0 s | 60 s | 60 s |
| 0 s | 0 s | Tắt |

**Không nên tắt heartbeat** chỉ để che một sự cố thời gian chờ. Khi cả hai phía đặt 0, kết nối half-open có thể khó được nhận diện hơn, làm thời gian khôi phục tăng mạnh.

### 3.2. Vì sao heartbeat quá thấp có thể phản tác dụng?

Một timeout quá ngắn có thể làm RabbitMQ/người tiêu thụ báo mất kết nối trong khi mạng chỉ chậm tạm thời. Nguyên nhân thường gặp:

- JVM có các đợt **stop-the-world GC** kéo dài hoặc thread bị nghẽn CPU.
- Máy chạy container bị **CPU throttling**; ứng dụng không được lập lịch kịp để xử lý frame.
- Network packet bị trễ hoặc mất theo burst.
- Broker quá tải, I/O chậm hoặc tiến trình không được lập lịch đều.
- Hệ thống đang tạm bị nghẽn hoặc flow control, cần phân biệt với lỗi kết nối thật.

Một heartbeat timeout quá thấp dễ gây vòng **disconnect → reconnect → redeclare/consumer recovery → disconnect**, làm sự cố nặng hơn. Giá trị cực nhỏ như 1–2 giây thường có nguy cơ *false positive* cao trong hệ thống thông thường.

Ngược lại, timeout quá cao làm tăng thời gian phát hiện đứt đường truyền im lặng. Cần chọn theo **đặc điểm mạng, thời gian GC, tải broker, yêu cầu failover và độ trễ khôi phục thực tế**. Các giá trị như 20–60 giây là điểm bắt đầu thực dụng để thử nghiệm tùy môi trường, không phải cam kết chung cho mọi hệ thống.

### 3.3. Heartbeat không phải health check nghiệp vụ

Heartbeat chỉ cho biết **connection còn trao đổi được AMQP frames**. Nó không chứng minh:

- Exchange và binding đúng.
- Message đã route tới queue đích.
- Listener vẫn xử lý đủ nhanh.
- Database đích còn hoạt động.
- Có ACK cho mọi message nghiệp vụ.
- Queue không bị backlog hoặc DLQ không tăng.

Do đó cần đo heartbeat/connection **cùng với** publish confirm, consumer trạng thái, message lag và lỗi nghiệp vụ.

## 4. Phân biệt các khoảng thời gian liên quan phục hồi

Trong tài liệu vận hành, chữ “timeout” dễ bị dùng cho nhiều cơ chế không giống nhau:

| Thông số/cơ chế | Bắt đầu khi nào? | Ý nghĩa chính |
| --- | --- | --- |
| **Heartbeat timeout** | Trong connection AMQP đã thiết lập | Phát hiện peer không còn trao đổi frame |
| **Connection timeout** | Khi client cố mở TCP connection đến broker | Giới hạn thời gian mở một kết nối mới |
| **Connection retry/backoff** | Sau một lần thử mở kết nối hoặc khôi phục thất bại | Quy định khi nào thử lại và có thể tăng khoảng cách thử |
| **Listener recovery interval** | Khi listener container không thể tiếp tục tiêu thụ và cần recovery | Khoảng cách giữa các lần container phục hồi, tùy loại container |
| **Publisher confirm timeout** | Sau publish đang chờ xác nhận từ broker | Giới hạn thời gian caller chờ kết quả publish; timeout không suy ra chắc chắn broker chưa nhận |
| **Reply timeout** | Với `convertSendAndReceive()` hoặc request–reply | Thời gian client chờ reply của một request |
| **Message retry backoff** | Sau khi business handler xử lý message thất bại | Tạm chờ trước khi thử lại xử lý message |

**Heartbeat/reconnect retry không thay thế message retry.** Ví dụ kết nối hoạt động tốt nhưng database đích lỗi thì đó là **lỗi xử lý message**; còn consumer không thể mở socket đến broker là **lỗi connection**. Một cấu hình retry nghiệp vụ `RetryInterceptorBuilder` không tự giảm thời gian phát hiện mạng đứt.

## 5. Kiến trúc Spring AMQP khi kết nối bị mất

Trong ứng dụng Spring Boot dùng `spring-boot-starter-amqp`, thành phần phổ biến là:

- **`CachingConnectionFactory`**: quản lý RabbitMQ connection/channel và cache tài nguyên để tái sử dụng khi còn hợp lệ.
- **`RabbitTemplate`**: mở hoặc dùng channel phù hợp để publish/request–reply.
- **`SimpleMessageListenerContainer`** hoặc **`DirectMessageListenerContainer`**: tạo consumer, quản lý delivery, ACK và phục hồi tiêu thụ.
- **`RabbitAdmin`**: có thể tự khai báo lại các bean exchange, queue và binding được quản lý khi tạo connection mới.
- **RabbitMQ Java client**: tầng giao thức/socket mà Spring AMQP sử dụng.

### 5.1. Ai chịu trách nhiệm recovery?

RabbitMQ Java client có tính năng **automatic connection/topology recovery** riêng. Spring AMQP cũng có các cơ chế quản lý và phục hồi connection, consumer, topology của chính framework.

Khi dùng Spring AMQP theo cách thông thường, **để framework quản lý recovery** thay vì bật thêm một lớp auto-recovery độc lập rồi giả định hai lớp luôn phối hợp đúng. Spring AMQP thường vô hiệu hóa chức năng automatic recovery của RabbitMQ Java client khi quản lý connection qua `CachingConnectionFactory`. Cách hoạt động cụ thể cần kiểm chứng với phiên bản Spring AMQP/RabbitMQ Java client thực tế.

Hệ quả thực tiễn:

1. Khi connection hỏng, connection factory phải loại bỏ/không dùng lại connection/channel lỗi.
2. Listener container phát hiện consumer không còn hợp lệ và thử mở consumer/channel lại.
3. RabbitTemplate có thể tạo connection/channel mới cho các lần publish tiếp theo khi broker sẵn sàng.
4. RabbitAdmin (nếu được cấu hình/cho phép) có thể khai báo lại topology được quản lý.
5. Ứng dụng phải xử lý **kết quả publish/ACK không chắc chắn** và những message có thể được giao lại.

**Recovery không phải “tiếp tục chính xác vị trí cũ”.** Channel mới có delivery tag mới; bản tin chưa ACK có thể redeliver; confirm đang chờ trên channel cũ không thể mặc định là confirm thành công.

### 5.2. Cấu hình ví dụ trong Spring Boot

Ví dụ cấu hình cho Spring Boot 3.x; property cụ thể cần đối chiếu với phiên bản framework đang dùng:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672

    # Duration. Client yêu cầu heartbeat 30 giây;
    # giá trị thực vẫn phải thương lượng với RabbitMQ.
    requested-heartbeat: 30s

    # Giới hạn một lần thiết lập TCP connection.
    connection-timeout: 5s

    # Phục vụ phát hiện publish không chắc chắn/sai routing.
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true

    listener:
      simple:
        acknowledge-mode: auto
        prefetch: 20
        concurrency: 2
        max-concurrency: 4
~~~

Phần này **không** đặt `listener.simple.retry.enabled` vì retry xử lý message là một quyết định riêng. Thời gian connection recovery của listener có thể cần cấu hình qua container factory nếu mục tiêu là thử lại theo một lịch khác mặc định.

Nếu ứng dụng lấy địa chỉ broker từ nhiều node, load balancer hoặc cluster service, cần kiểm tra cơ chế DNS/định tuyến của môi trường. Reconnect vào cùng địa chỉ không chứng minh rằng broker đã sẵn sàng accept AMQP hoặc queue đã có leader hoạt động.

### 5.3. Listener factory với recovery interval có chủ đích

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitListenerRecoveryConfig {

    @Bean
    SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(4);
        factory.setPrefetchCount(20);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);

        // Khoảng cách giữa các lần consumer/container
        // thử khôi phục, không phải heartbeat timeout.
        factory.setRecoveryInterval(5_000L);
        return factory;
    }
}
~~~

Ví dụ trên dùng **Simple** listener container. Với `DirectMessageListenerContainer`, chiến lược quản lý consumer và các setter recovery khác, nên không sao chép tham số từ Simple container sang Direct container mà không kiểm tra API.

**Một điều quan trọng:** `recoveryInterval=5_000 ms` không có nghĩa “mất mạng đúng 5 giây là consumer hoạt động lại”. Nó chỉ tham gia lịch thử recovery, trong khi phát hiện lỗi, mở socket, AMQP handshake, topology và broker readiness cần thêm thời gian.

## 6. Phân rã thời gian phục hồi đầu cuối

Có thể chia thời gian gián đoạn từ lúc đường truyền thực sự hỏng đến khi một message mới được xử lý và commit thành công thành các đoạn:

~~~text
t0: Đường truyền hỏng
  |
  +-- T_detect ------> Ứng dụng nhận biết connection/channel không còn dùng được
  |
  +-- T_backoff -----> Tới lượt thử recovery
  |
  +-- T_connect -----> TCP + TLS (nếu có) + AMQP handshake thành công
  |
  +-- T_topology ----> Exchange/queue/binding cần thiết đã sẵn sàng
  |
  +-- T_consumer ----> Consumer đăng ký và bắt đầu nhận delivery
  |
  +-- T_process -----> Message được xử lý và DB commit
  v
t1: Luồng nghiệp vụ hoạt động trở lại
~~~

Để lập ngân sách thời gian (time budget), có thể ước tính:

\[
T_{\text{end-to-end}} \approx T_{\text{detect}} +
T_{\text{backoff}} + T_{\text{connect}} +
T_{\text{topology}} + T_{\text{consumer}} +
T_{\text{process}}
\]

Đây là mô hình để **phân tích**, không phải công thức bảo đảm thời gian khôi phục tuyệt đối. Các giai đoạn có thể chồng lấn, lặp lại hoặc chịu ảnh hưởng của nhiều retry. Nếu broker chưa sẵn sàng, `T_backoff + T_connect` có thể xảy ra nhiều vòng.

### 6.1. Một ví dụ đo được

Giả sử hệ thống đo thấy, trong **một lần thử nghiệm**:

| Mốc đo | Giá trị minh họa |
| --- | ---: |
| Network failure xảy ra | `t=0s` |
| Ứng dụng phát hiện failure | `t=24s` |
| Recovery attempt phù hợp bắt đầu | `t=27s` |
| AMQP connection mới hoạt động | `t=29s` |
| Consumer mới có delivery | `t=31s` |
| Transaction đầu tiên sau phục hồi commit | `t=32s` |

Trong lần thử này, mất khoảng **32 giây** để phục hồi đường xử lý nghiệp vụ. Không thể kết luận từ đó “heartbeat=30s nghĩa là downtime luôn 32s”; đây chỉ là số liệu của một scenario với tải và thời điểm ngắt mạng cụ thể.

Nên ghi riêng:

- `time_to_detect_connection_failure`;
- `time_to_open_new_connection`;
- `time_to_first_consumer_delivery`;
- `time_to_first_successful_processing`;
- `oldest_queued_message_age` sau khi khôi phục.

Nếu queue tích backlog lớn khi ngắt mạng, thời gian **xử lý hết backlog** còn dài hơn thời gian có delivery đầu tiên.

### 6.2. Downtime và thời gian bắt kịp backlog

Giả sử trong lúc mất kết nối, producer vẫn gửi vào broker được với tốc độ 100 message/s và consumer ngừng 30 giây. Queue tích thêm khoảng:

\[
B = 100 \times 30 = 3{,}000\ \text{message}
\]

Khi consumer phục hồi và xử lý 150 message/s, trong khi producer vẫn gửi 100 message/s, tốc độ xử lý phần tồn đọng ròng chỉ là 50 message/s. Thời gian lý tưởng để xóa backlog:

\[
T_{\text{drain}} \approx \frac{3{,}000}{150 - 100}
= 60\ \text{giây}
\]

Do đó, **phát hiện và kết nối lại nhanh** chưa chắc đã làm message trở về độ trễ bình thường ngay. Cần đo backlog, throughput, thời gian xử lý DB và khả năng scale consumer.

## 7. Điều gì xảy ra với message đang publish khi connection chết?

Đây là cửa sổ không chắc chắn quan trọng nhất phía producer:

~~~text
Ứng dụng gửi PUBLISH(eventId=E42)
               |
               +---- Có thể broker đã nhận và route được
               |
       Connection mất trước khi ứng dụng nhận publisher confirm
               |
       Caller không biết chắc kết quả
~~~

Có hai cách xử lý cực đoan đều nguy hiểm:

- **Coi là thành công** dù chưa có bằng chứng: có thể làm mất event nếu broker chưa nhận.
- **Gửi một event hoàn toàn mới với eventId khác**: có thể tạo hai tác dụng nghiệp vụ vì lần publish đầu thực ra đã thành công.

Đường đi phù hợp là giữ **một eventId ổn định**, dùng **publisher confirms** để biết broker ACK/NACK publish, dùng **publisher returns** để phát hiện message không route được, và lưu nguồn event bền vững để có thể thử lại.

### 7.1. Publisher confirm khác consumer ACK

- **Publisher confirm**: broker xác nhận đã xử lý publish theo điều kiện bảo đảm của broker/queue.
- **Publisher return**: với `mandatory=true` và returns bật, publisher được thông báo khi message không thể route tới queue theo các điều kiện áp dụng.
- **Consumer ACK**: broker biết một delivery đã được consumer xác nhận xử lý.
- **Business commit**: tác dụng nghiệp vụ được DB hoặc hệ thống đích ghi lại.

Một exchange có thể chấp nhận publish và xác nhận bằng confirm ACK, trong khi message **không route được** nếu không có binding phù hợp. Khi `mandatory` được bật, publisher return là bằng chứng cần xem thêm. Confirm ACK **không thay cho** business commit.

### 7.2. Ví dụ dùng CorrelationData khi publish

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public final class ReliablePublisher {

    private final RabbitTemplate rabbitTemplate;

    public ReliablePublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void send(OrderEvent event) throws Exception {
        // eventId phải ổn định khi retry cùng sự kiện.
        String id = event.eventId().toString();
        var correlation = new CorrelationData(id);

        rabbitTemplate.convertAndSend(
                "orders.events.exchange",
                "order.paid",
                event,
                message -> {
                    message.getMessageProperties().setMessageId(id);
                    message.getMessageProperties().setDeliveryMode(
                            MessageDeliveryMode.PERSISTENT);
                    return message;
                },
                correlation);

        var confirm = correlation.getFuture()
                .get(5, TimeUnit.SECONDS);

        if (!confirm.isAck()) {
            throw new IllegalStateException(
                    "Broker NACK: " + confirm.getReason());
        }

        if (correlation.getReturned() != null) {
            throw new IllegalStateException(
                    "Publish không route được tới queue");
        }
    }

    public record OrderEvent(
            java.util.UUID eventId,
            String orderId,
            String status) {}
}
~~~

Ví dụ này cần `RabbitTemplate` được cấu hình converter phù hợp với DTO, `publisher-confirm-type: correlated`, `publisher-returns: true` và `template.mandatory: true` như ở trên. Nó minh họa cách **kiểm tra kết quả publish**, không phải một outbox hoàn chỉnh.

**Quan trọng:** timeout của `correlation.getFuture().get(...)` tạo ra **unknown outcome**. Khi mất kết nối sau publish, không khẳng định chắc chắn event chưa tới queue. Nếu event có ý nghĩa nghiệp vụ cần phát lại, phải giữ một bản bền vững cùng `eventId`, chẳng hạn transactional outbox.

### 7.3. Transactional outbox khi không thể mất event

Nếu ứng dụng cập nhật đơn hàng trong database rồi phát sự kiện, cần xử lý cửa sổ:

~~~text
COMMIT orders.status='PAID'
        ↓ ứng dụng crash
PUBLISH OrderPaid chưa hề xảy ra
~~~

Một **transactional outbox** lưu `orders` và `outbox_events` **trong cùng DB transaction**. Relay lấy event từ outbox và publish. Chỉ đánh dấu đã phát khi nhận kết quả publish phù hợp. Nếu relay crash sau broker confirm nhưng trước khi đánh dấu, event có thể được publish lại; người nhận phải idempotent.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant O as Order service
    participant DB as Orders DB + Outbox
    participant R as Outbox relay
    participant B as RabbitMQ
    O->>DB: BEGIN / update order / insert eventId=E42 / COMMIT
    R->>DB: Đọc E42 chưa publish
    R->>B: Publish E42 với CorrelationData
    Note over R,B: Mất kết nối hoặc confirm không tới
    R->>DB: Giữ E42 để retry
    R->>B: Publish lại CÙNG E42
    B-->>R: Confirm + routing hợp lệ
    R->>DB: Mark published
~~~

Phương án này hướng tới **at-least-once publish**, không phải exactly-once. Dữ liệu outbox phải được giữ đủ lâu, có cảnh báo bản ghi kẹt và có cách xử lý khi publish liên tục thất bại.

## 8. Điều gì xảy ra với message consumer đã nhận khi connection chết?

Mất connection khiến channel gắn với delivery không còn hợp lệ. Message đã giao nhưng **chưa được broker ACK** thường có thể được broker đưa về trạng thái sẵn sàng và redeliver cho consumer sau khi phục hồi, miễn queue/message chưa bị loại theo các chính sách khác.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C as @RabbitListener
    participant DB as Business DB

    B->>C: Delivery E42
    C->>DB: BEGIN / update / COMMIT
    Note over B,C: Connection đứt trước khi ACK tới broker
    Note over B: E42 chưa được ACK
    B->>C: Sau recovery: redelivery E42
    C->>DB: Kiểm tra eventId E42
    DB-->>C: Đã xử lý; bỏ qua side effect
    C-->>B: ACK
~~~

Có ba cửa sổ cơ bản:

| Thời điểm lỗi | Trạng thái nghiệp vụ có thể xảy ra | Xử lý đúng |
| --- | --- | --- |
| Trước DB commit và trước ACK | Transaction có thể rollback; delivery chưa được ACK | Redelivery xử lý lại |
| Sau DB commit nhưng trước ACK broker nhận | Side effect đã xảy ra, message có thể redeliver | Dedup theo `eventId`; không áp dụng hai lần |
| ACK được gửi **trước** DB commit | Broker có thể loại message dù database rollback | **Tránh ACK sớm**; commit trước ACK |

Vì vậy cơ chế recovery thành công **không** đảm bảo “mỗi message chỉ chạy một lần”. Thiết kế nên chấp nhận duplicate delivery mà vẫn bảo vệ business effect.

### 8.1. Phân biệt ACK mode của Spring AMQP

| Mode | Thời điểm/đơn vị ACK | Lưu ý |
| --- | --- | --- |
| `AcknowledgeMode.AUTO` | Listener container ACK sau khi listener xử lý thành công theo cơ chế container | Không phải auto-ack vô điều kiện của RabbitMQ Java client |
| `AcknowledgeMode.MANUAL` | Code ứng dụng tự `basicAck`, `basicNack` hoặc `basicReject` | Dễ ACK sớm hoặc quên ACK nếu xử lý exception không đầy đủ |
| `AcknowledgeMode.NONE` | Broker coi delivery được ACK khi giao theo auto-ack | Không phù hợp khi cần redelivery lúc consumer chưa xử lý xong |

Ví dụ listener đồng bộ nhận sự kiện và gọi service transactional:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class InventoryListener {

    private final InventoryService inventoryService;

    public InventoryListener(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @RabbitListener(
            queues = "inventory.order-paid.queue",
            containerFactory = "rabbitListenerContainerFactory")
    public void onOrderPaid(OrderEvent event) {
        // Chờ transaction của service kết thúc trước khi return.
        inventoryService.applyOnce(event);
    }
}
~~~

Ở đây `InventoryService.applyOnce()` cần dùng một database transaction để vừa cập nhật dữ liệu vừa ghi marker xử lý theo khóa `(consumerName, eventId)` có unique constraint. Nếu marker đã tồn tại, service kết thúc mà không thực hiện side effect lần nữa. Listener **chỉ return sau khi service đã commit**, để container `AUTO` có thể ACK sau đó.

Nếu listener gọi `executor.submit(...)` rồi return ngay, ACK có thể đến trước khi tác vụ nền kết thúc. Đây là một lỗi thiết kế đặc biệt nguy hiểm khi mạng không ổn định.

### 8.2. ACK trên channel cũ không thể gửi lại tùy tiện

Delivery tag chỉ có ý nghĩa **trên channel mà RabbitMQ đã giao delivery đó**. Khi channel bị đóng và được tạo mới, không thể dùng một delivery tag cũ để ACK trên channel mới. Với `AcknowledgeMode.AUTO`, container quản lý channel/tag; trong chế độ MANUAL, code phải đặc biệt thận trọng với lifecycle của channel và exception khi ACK.

Một ACK bị mất không phải lý do để “tạo ACK mới bằng số tag đã nhớ”. Hãy để broker redeliver và để handler idempotent xác minh event đã được xử lý.

## 9. Exchange, queue, binding có tự phục hồi không?

Khôi phục connection chỉ là một bước. Producer còn cần exchange/routing, consumer còn cần queue và quyền subscribe.

Spring AMQP có `RabbitAdmin` để khai báo exchange, queue và binding theo bean ứng dụng khi điều kiện cho phép; cơ chế này thường chạy khi tạo được connection và có thể khai báo lại topology trên connection mới. Nhưng đừng coi `RabbitAdmin` là phép sửa mọi sai lệch topology:

- **Durable queue/exchange** có thể vẫn tồn tại sau restart broker; không nhất thiết phải tạo mới trong mỗi lần reconnect.
- **Exclusive/auto-delete queue** có vòng đời đặc biệt; sau disconnect có thể bị xóa và tạo lại, đồng thời message cũ không mặc nhiên được bảo toàn.
- **Queue arguments không tương đương** (queue type, DLX, quorum arguments…) có thể khiến redeclare thất bại với lỗi protocol. Recovery lặp lại sẽ không sửa được mâu thuẫn cấu hình.
- **Binding không đúng routing key** có thể gây publisher return hoặc message không tới queue dù connection đã healthy.
- **Quyền truy cập, virtual host, credentials, TLS** sai vẫn làm recovery thất bại cho tới khi cấu hình được sửa.
- Nếu một queue đã bị xóa vì lỗi vận hành, tự khai báo lại không phục hồi những message cũ vốn đã mất.

Ví dụ topology durable:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderEventsTopology {

    @Bean
    DirectExchange ordersEventsExchange() {
        return new DirectExchange("orders.events.exchange", true, false);
    }

    @Bean
    Queue inventoryOrderPaidQueue() {
        return QueueBuilder.durable("inventory.order-paid.queue")
                .build();
    }

    @Bean
    Binding inventoryOrderPaidBinding() {
        return BindingBuilder.bind(inventoryOrderPaidQueue())
                .to(ordersEventsExchange())
                .with("order.paid");
    }
}
~~~

Trong hệ thống production có DLX/DLQ, cần khai báo queue lỗi và binding tương ứng; nếu listener reject một message không requeue, nó phải có đường điều tra phù hợp. **DLX không chữa được lỗi không có kết nối**: dead-letter chỉ xảy ra khi broker có message và có sự kiện dead-letter tương ứng.

## 10. Kết hợp heartbeat với các cơ chế phòng mất và trùng

Một kiến trúc recovery đáng tin cậy gồm nhiều lớp:

| Lớp | Công cụ | Vấn đề được giải quyết |
| --- | --- | --- |
| Phát hiện lỗi liên lạc | AMQP heartbeat, TCP/socket errors | Nhận biết connection không còn dùng được |
| Kết nối lại | Spring AMQP connection factory + listener container | Mở lại connection/channel/consumer |
| Khôi phục định tuyến | RabbitAdmin/topology được quản lý | Có exchange, queue, binding phù hợp |
| Xác nhận publish | Publisher confirms + mandatory returns | Phân biệt broker xác nhận và không route được |
| Giữ sự kiện nguồn | Transactional outbox | Không mất event sau DB commit và trước publish |
| Bảo toàn delivery | Durable queue, persistent message, consumer ACK | Message chưa xử lý có cơ hội redeliver trong phạm vi bảo đảm của queue |
| Xử lý trùng | Inbox/unique constraint + idempotent handler | Redelivery hoặc republish không gây side effect hai lần |
| Xử lý lỗi nghiệp vụ | Retry budget, DLX và terminal DLQ | Không tạo vòng xử lý poison message vô hạn |
| Quan sát và đối soát | Metrics, logs, trace, reconciliation | Biết khi nào phục hồi thật sự và dữ liệu có bị lệch không |

**Không gộp tất cả vào từ “recovery”.** Việc tạo connection mới chỉ giải quyết khả năng liên lạc. Khôi phục message đang gửi, đang ACK hoặc nghiệp vụ đã commit cần những cơ chế khác.

## 11. Giám sát: đo mất kết nối và phục hồi như thế nào?

Nên đo ít nhất **ba góc nhìn**: AMQP connection, consumer và tiến độ nghiệp vụ.

### 11.1. Chỉ số về connection và channel

| Chỉ số/sự kiện | Mục đích |
| --- | --- |
| Connection open/close và nguyên nhân | Biết recovery có thực sự bắt đầu hay không |
| Channel shutdown / protocol exception | Phân biệt lỗi socket với lỗi channel/topology |
| Heartbeat timeout / missed heartbeat | Nhận diện failure hoặc false positive |
| Connection attempts, failures, success | Quan sát chu kỳ retry/backoff |
| Negotiated heartbeat và thời gian sống connection | Kiểm chứng cấu hình đang có hiệu lực |
| Broker connection count, channel count, churn | Phát hiện reconnect storm |
| Resource alarms, disk/memory pressure, network latency | Tránh chẩn đoán nhầm quá tải thành lỗi heartbeat đơn thuần |

### 11.2. Chỉ số về producer và consumer

| Chỉ số | Phát hiện |
| --- | --- |
| `publish_confirm_ack`, `publish_confirm_nack`, `confirm_timeout` | Publish thành công hoặc trạng thái chưa rõ |
| `publisher_return_count` theo exchange/routing key | Binding/route không hợp lệ |
| `consumer_count` và listener state | Consumer đã đăng ký sau reconnect chưa |
| `messages_ready`, `messages_unacknowledged` | Queue backlog và delivery chưa ACK |
| Redelivery rate | Crash/ACK thất lạc hoặc requeue lặp |
| Time to first delivery/commit | Độ trễ phục hồi thực tế ở tầng nghiệp vụ |
| Outbox pending age | Event nguồn đang chờ publish |
| DLQ size/oldest age | Lỗi nghiệp vụ vẫn tồn tại sau recovery |
| Deduplication hits | Số message trùng đã được chặn |

Tên metric cụ thể phụ thuộc Micrometer, RabbitMQ management/Prometheus exporter và instrumentation của ứng dụng; những tên mô tả ở đây là **khái niệm cần đo**, không phải cam kết mọi metric đều được Spring Boot xuất sẵn.

### 11.3. Log theo mốc thời gian

Nên ghi các thời điểm có nghĩa:

~~~text
2026-11-26T10:00:00.000+07:00 connection_unreachable broker=rabbit-1
2026-11-26T10:00:24.200+07:00 connection_closed cause=heartbeat_timeout
2026-11-26T10:00:27.200+07:00 reconnect_attempt attempt=1
2026-11-26T10:00:29.000+07:00 connection_open broker=rabbit-2
2026-11-26T10:00:30.100+07:00 consumer_registered queue=inventory.order-paid.queue
2026-11-26T10:00:31.700+07:00 first_event_committed eventId=E42
~~~

Đây là **log ví dụ**, không phải định dạng Spring AMQP phát tự động. Trường `cause` phải lấy từ exception/diagnostics thực; không tự gắn nhãn heartbeat timeout cho mọi lần disconnect.

Khi log từng event, dùng `eventId`, queue, routing key, correlation, thời gian publish/receive/commit. Không log nguyên payload có dữ liệu nhạy cảm chỉ để điều tra connection.

## 12. Liveness, readiness và thời điểm cho instance nhận traffic

Khi dùng Kubernetes hoặc hệ thống orchestration, phải phân biệt hai câu hỏi:

- **Liveness**: tiến trình còn hoạt động và có khả năng tự phục hồi hay không?
- **Readiness**: instance hiện có đáp ứng được loại traffic nghiệp vụ dự kiến hay không?

Không nên mặc định **một lần mất kết nối RabbitMQ làm liveness fail rồi restart mọi pod**. Nếu Spring AMQP đang phục hồi bình thường, restart liên tục có thể kéo dài downtime, tạo vòng kết nối mới và gây reconnect storm.

Với HTTP endpoint phụ thuộc hoàn toàn vào publish đồng bộ sang RabbitMQ, readiness có thể cân nhắc phản ánh broker chưa sẵn sàng. Với một worker chỉ nhận từ queue, không có HTTP traffic để load balancer điều hướng, readiness cần được thiết kế theo mục đích orchestration thực tế; kiểm tra connection bằng một ping độc lập cũng không chứng minh listener đang tiêu thụ message.

Chỉ báo sẵn sàng nên dựa trên nhu cầu sản phẩm: có connection phù hợp, listener đã đăng ký, queue đúng, backlog trong giới hạn và dịch vụ phụ thuộc đáp ứng. Liveness nên kiểm tra tiến trình có bị deadlock hoặc không còn khả năng tự phục hồi, thay vì biến mỗi lỗi mạng ngắn hạn thành yêu cầu restart.

## 13. Kịch bản kiểm thử phục hồi

Cần thực hiện ở môi trường thử nghiệm với RabbitMQ và Spring Boot thật. Dùng cùng `eventId` từ producer tới consumer để theo dõi hậu quả. Đo riêng **T_detect**, **T_connect**, **T_first_delivery** và **T_first_commit**.

### Kịch bản A — broker restart có chủ đích

1. Tạo exchange, queue durable và binding như mục 9.
2. Khởi động producer/consumer, gửi event thử và xác nhận đã commit.
3. Restart RabbitMQ broker trong môi trường thử nghiệm.
4. Quan sát connection/channel đóng, listener thử recovery và consumer đăng ký lại.
5. Publish event mới sau khi broker sẵn sàng; xác minh xử lý thành công.

**Kỳ vọng:** ứng dụng tự nối lại và có delivery mới. Thời gian đo được bao gồm cả thời gian broker khởi động và sẵn sàng, không chỉ recovery interval.

### Kịch bản B — mạng blackhole (half-open)

1. Cho connection hoạt động bình thường và ở trạng thái ít traffic.
2. Trong môi trường thử nghiệm, chặn traffic ở tầng mạng nhưng không gửi TCP FIN/RST.
3. Quan sát mất bao lâu client/broker phát hiện connection không còn hoạt động.
4. Khôi phục đường truyền và đo thời gian consumer nhận/commit message mới.

**Kỳ vọng:** heartbeat giúp phát hiện kết nối im lặng không còn sử dụng được. Kết quả có thể chênh lệch so với một lỗi `connection refused` tức thì.

### Kịch bản C — heartbeat quá thấp và tải hệ thống

1. Đo heartbeat đang thương lượng.
2. Trên môi trường thử, thử một cấu hình heartbeat ngắn hơn bình thường.
3. Tạo tải CPU/GC hoặc network latency có kiểm soát.
4. Quan sát disconnect false positive, reconnect rate và backlog.
5. Trả lại giá trị phù hợp đã kiểm chứng.

**Kỳ vọng:** thấy trade-off giữa thời gian phát hiện và độ ổn định; không chọn heartbeat thấp chỉ để đẹp biểu đồ failover.

### Kịch bản D — publish thành công nhưng mất confirm

1. Lưu event `E42` trong outbox.
2. Cho relay publish E42; mô phỏng mất connection ở thời điểm không nhận được confirm.
3. Khởi động relay, cho phép thử lại **cùng E42**.
4. Quan sát event có thể xuất hiện hơn một lần.
5. Xác minh consumer idempotent chỉ áp dụng side effect một lần.

**Kỳ vọng:** không mất event do unknown outcome; không tạo duplicate effect.

### Kịch bản E — sai routing sau recovery

1. Trong môi trường thử, cố tình bỏ binding `order.paid`.
2. Publish với mandatory/returns đã bật.
3. Xác minh publisher return hoặc giám sát nhận biết route lỗi, dù connection và broker vẫn healthy.
4. Khôi phục binding rồi thử lại.

**Kỳ vọng:** phân biệt recovery của connection với tính đúng đắn của topology.

### Kịch bản F — consumer crash sau DB commit, trước ACK

1. Consumer nhận `E43`, ghi marker inbox và side effect trong cùng transaction.
2. Mô phỏng crash sau commit nhưng trước khi ACK tới broker.
3. Cho container/instance khác phục hồi và nhận lại E43.
4. Kiểm tra unique constraint chặn side effect lần hai.

**Kỳ vọng:** có thể duplicate delivery nhưng không duplicate business effect.

### Kịch bản G — broker chưa sẵn sàng trong nhiều chu kỳ recovery

1. Tắt broker trong khoảng thời gian đủ để listener thử lại nhiều lần.
2. Theo dõi số lần attempt, khoảng backoff và mức độ log spam.
3. Khởi động broker trở lại.
4. Xác minh listener khôi phục mà không phải restart ứng dụng.

**Kỳ vọng:** quá trình retry ổn định, có cảnh báo nhưng không gây busy loop hoặc reconnect storm ngoài tầm kiểm soát.

### Kịch bản H — queue arguments không tương đương

1. Tạo queue với một bộ arguments.
2. Thay đổi bean khai báo queue cùng tên sang một bộ arguments khác không tương thích.
3. Cho ứng dụng reconnect/redeclare.
4. Quan sát lỗi channel/precondition failure và việc consumer không thể sẵn sàng.
5. Khôi phục topology theo kế hoạch migration thích hợp.

**Kỳ vọng:** không đánh đồng “AMQP connection open” với “topology hợp lệ”.

### Kịch bản I — backlog sau gián đoạn

1. Dừng consumer nhưng giữ producer tiếp tục publish vào queue bền vững.
2. Đo backlog tạo ra theo thời gian.
3. Cho consumer recovery; đo time to first delivery và time to drain backlog.
4. So sánh với latency SLO của event.

**Kỳ vọng:** đánh giá được khôi phục ở tầng giao thức lẫn ở tầng nghiệp vụ.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “Socket đang mở nên RabbitMQ chắc còn kết nối tốt” | TCP half-open có thể chưa được phát hiện; heartbeat là một tín hiệu hoạt động |
| “Heartbeat 30s là chắc chắn reconnect xong trong 30s” | Heartbeat chủ yếu phát hiện mất liên lạc; còn backoff, handshake, topology, consumer và DB |
| “Heartbeat thấp nhất sẽ luôn tốt nhất” | Timeout quá ngắn có thể gây false positive và reconnect storm |
| “Mất mạng thì RabbitTemplate sẽ tự phát lại tất cả publish chưa confirm” | Kết quả publish có thể không xác định; ứng dụng cần outbox/confirm/retry phù hợp |
| “Publisher confirm ACK nghĩa là consumer đã xử lý” | Confirm publish và consumer ACK là hai ranh giới độc lập |
| “Reconnected nghĩa là mọi queue và binding đã đúng” | Topology có thể sai, bị xóa hoặc redeclare thất bại |
| “AUTO ACK của Spring AMQP giống autoAck=true ở RabbitMQ client” | AUTO của listener container ACK sau khi listener hoàn tất thành công |
| “Đã xử lý E42 một lần thì E42 không thể tới lần nữa” | DB commit trước ACK có thể tạo redelivery khi connection chết |
| “Retry business message giúp mở lại connection nhanh hơn” | Retry handler và retry connection là hai cơ chế khác nhau |
| “Restart pod là cách tốt nhất khi broker chập chờn” | Restart có thể phá chu kỳ tự phục hồi và tăng áp lực hạ tầng |
| “Queue rỗng tức là không mất message” | Publish có thể chưa từng được route hoặc consumer có thể ACK sớm |
| “Connection hồi phục là SLO hồi phục” | Cần đo first committed event và thời gian drain backlog |

## 15. Checklist triển khai

- [ ] Biết RabbitMQ/Spring Boot đang chạy phiên bản nào và cơ chế recovery nào thực sự quản lý connection, listener, topology.
- [ ] Đã chọn `requested-heartbeat` dựa trên thời gian GC/network và đo **giá trị negotiated**, không chỉ dựa trên YAML.
- [ ] Có `connection-timeout`, listener recovery interval/backoff và log ở mức đủ để xác định các lần thử.
- [ ] Không bật hai cơ chế auto-recovery chồng chéo nếu chưa hiểu hệ quả.
- [ ] Exchange, queue, binding, vhost, credentials, TLS và queue arguments đã được xác minh sau restart.
- [ ] Queue/message dùng durability phù hợp yêu cầu; publisher confirms, returns và mandatory được thiết lập khi cần.
- [ ] Event phát sau DB commit có transactional outbox hoặc cơ chế tương đương để không mất trong cửa sổ chưa publish.
- [ ] Khi publish timeout/connection reset, ứng dụng giữ `eventId` và xử lý **unknown outcome** an toàn.
- [ ] Consumer ACK sau business transaction; có inbox/dedup unique constraint để chịu redelivery.
- [ ] Retry nghiệp vụ có giới hạn; DLX/DLQ không tạo vòng lặp và được giám sát.
- [ ] Đo T_detect, T_connect, T_first_delivery, T_first_commit và T_drain_backlog riêng.
- [ ] Readiness/liveness phù hợp vòng đời ứng dụng; broker outage tạm thời không tự gây restart loop.
- [ ] Có cảnh báo cho reconnect storm, publisher return, outbox backlog, redelivery và tuổi message.
- [ ] Đã thực hiện test broker restart, network blackhole, missed confirm, ACK lost và lỗi topology.

## 16. Tổng kết

**Heartbeat** giúp RabbitMQ và client phát hiện connection AMQP không còn trao đổi frame, nhất là khi TCP rơi vào trạng thái im lặng. Nhưng thời gian phục hồi có nhiều đoạn: **phát hiện lỗi → đợi retry → mở connection mới → có topology hợp lệ → đăng ký consumer → xử lý/commit message → bắt kịp backlog**. Vì vậy, mục tiêu vận hành phải dựa trên thời gian **nghiệp vụ hoạt động trở lại**, không chỉ log “connected”.

Trong **SPRING_AMQP**, `CachingConnectionFactory` và listener container giúp phục hồi connection/consumer, còn `RabbitAdmin` hỗ trợ quản lý topology. Tuy nhiên, recovery cấp connection **không thể giải quyết kết quả publish chưa rõ hoặc ACK bị mất**. Muốn xử lý bất đồng bộ đáng tin cậy, vẫn phải kết hợp **publisher confirms/returns, transactional outbox, consumer idempotency, ACK sau commit, retry/DLQ và giám sát đầu cuối**.

Khi trả lời được ba câu hỏi — *mất bao lâu để phát hiện? bao lâu để xử lý message trở lại? và message đang ở giữa chừng được bảo vệ như thế nào?* — hệ thống mới có một chiến lược phục hồi kết nối đủ rõ để kiểm thử, đo lường và vận hành.
