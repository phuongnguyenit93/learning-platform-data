# Quan sát luồng thông điệp qua RabbitMQ Management

Khi ứng dụng Spring AMQP gửi thông điệp thành công mà phía nhận không thấy dữ liệu, câu hỏi đầu tiên thường là: **message đã tới RabbitMQ chưa, đã vào queue nào, đang chờ xử lý hay đã được consumer nhận?** RabbitMQ Management cung cấp giao diện web và HTTP API để quan sát broker, exchange, queue, binding, connection, channel, consumer cùng các số liệu thông điệp. Đây là công cụ quan trọng khi học và vận hành hệ thống xử lý bất đồng bộ bằng **RabbitTemplate**, **@RabbitListener** và RabbitMQ.

Bài này xây một phòng thực hành nhỏ, sau đó theo dấu một message qua toàn bộ đường đi: **producer → exchange → binding → queue → consumer → acknowledgment (ack)**. Đồng thời, bạn sẽ học cách nhận diện message bị tồn đọng, xử lý chậm, không được định tuyến hoặc có nguy cơ được giao lại.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Khởi chạy RabbitMQ có bật Management và truy cập giao diện quản trị.
- Xác định exchange, queue, binding, connection, channel và consumer trong giao diện.
- Quan sát ba chỉ số quan trọng: **Ready**, **Unacked** và **Total**.
- Phân biệt publish, deliver, acknowledge và kết quả nghiệp vụ của một listener Spring AMQP.
- Kiểm chứng một số tình huống: không có consumer, consumer xử lý chậm, routing key sai.
- Đọc các tín hiệu ban đầu phục vụ chẩn đoán retry, dead-letter, lỗi cấu hình và giám sát hệ thống.

## 2. RabbitMQ Management nhìn thấy những gì?

RabbitMQ gồm hai mặt giao tiếp khác nhau:

- **AMQP**, thường qua cổng **5672**, phục vụ ứng dụng gửi và nhận message. **RabbitTemplate** và **@RabbitListener** sử dụng kết nối này.
- **Management**, thường qua **HTTP 15672**, phục vụ người vận hành xem trạng thái, tạo/kiểm tra tài nguyên, thực hiện thao tác thử nghiệm và truy vấn số liệu bằng HTTP API.

Giao diện Management **không thay thế consumer** và cũng **không phải nhật ký lưu trữ tất cả message từng đi qua broker**. Khi message đã được consumer ack và bị xóa khỏi queue, bạn thường không thể mở Management để đọc lại nội dung của message đó. Biểu đồ là số liệu vận hành tại thời điểm hoặc khoảng lấy mẫu, không phải bằng chứng kiểm toán đầy đủ cho từng sự kiện nghiệp vụ.

~~~mermaid
flowchart LR
    P["Spring Boot Producer<br/>RabbitTemplate"] -->|"publish: demo.created"| X["Direct exchange<br/>demo.events"]
    X -->|"binding: demo.created"| Q["Queue<br/>demo.audit"]
    Q -->|"deliver"| C["Spring Boot Consumer<br/>@RabbitListener"]
    C -.->|"ack sau khi xử lý thành công"| Q
    M["RabbitMQ Management<br/>HTTP :15672"] -.->|"quan sát exchange / routing"| X
    M -.->|"Ready / Unacked / Total"| Q
    M -.->|"connection / consumer"| C
~~~

Thông thường, message được producer phát vào **exchange** cùng một **routing key**. Exchange đối chiếu **binding** để định tuyến message tới queue phù hợp. Consumer nhận từ queue và gửi ack theo cấu hình. Trong sơ đồ, đường nét đứt biểu thị việc quan sát hoặc ack; Management không nằm trên đường dữ liệu AMQP thực tế.

## 3. Chuẩn bị môi trường

### 3.1. Chạy RabbitMQ Management bằng Docker

Bạn cần Docker đang hoạt động và một môi trường chạy được ứng dụng Spring Boot. Lệnh sau dùng image RabbitMQ có kèm Management, chỉ mở hai cổng cho máy cục bộ:

~~~bash
docker run -d --name rabbitmq-ui-lab -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -e RABBITMQ_DEFAULT_USER=lab -e RABBITMQ_DEFAULT_PASS=lab123456 rabbitmq:4-management
~~~

Kiểm tra container:

~~~bash
docker ps
docker logs rabbitmq-ui-lab
~~~

Truy cập **http://localhost:15672** và đăng nhập bằng tài khoản **lab / lab123456**. Đây chỉ là tài khoản minh họa trên máy học tập. Khi triển khai thật, phải dùng thông tin xác thực an toàn, giới hạn quyền, HTTPS/reverse proxy phù hợp và không công khai giao diện quản trị trên Internet.

| Thành phần | Địa chỉ cục bộ | Mục đích |
|---|---|---|
| AMQP broker | localhost:5672 | Spring AMQP kết nối để publish/consume |
| Management UI | http://localhost:15672 | Trình duyệt quan sát và quản trị RabbitMQ |
| Spring Boot demo | http://localhost:8080 | HTTP endpoint để yêu cầu publish thử |

Nếu đã có broker RabbitMQ khác, có thể dùng môi trường đó với điều kiện **Management plugin** đã bật, tài khoản có quyền phù hợp và các cổng được truy cập đúng. Không nhất thiết phải tạo container mới.

### 3.2. Cấu hình ứng dụng Spring Boot

Trong dự án Spring Boot đang có, thêm starter AMQP và Web. Với Maven, hai dependency tương ứng là:

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

Đặt cấu hình sau trong **src/main/resources/application.yml** của ứng dụng:

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
      simple:
        acknowledge-mode: auto
        concurrency: 1
        max-concurrency: 1
        prefetch: 1
~~~

Trong ví dụ, mỗi listener container chỉ xử lý tối đa một message chưa ack trên mỗi consumer vì **prefetch = 1**. Với **acknowledge-mode: auto**, Spring AMQP listener container thông thường ack **sau khi phương thức listener chạy thành công**. Đây là một chế độ của Spring AMQP, không phải chế độ RabbitMQ tự động ack ngay lúc giao message. Nếu phương thức ném exception, cách reject, requeue hay retry còn phụ thuộc cấu hình.

### 3.3. Khai báo exchange, queue và binding

Đặt các lớp Java dưới đây trong package được Spring Boot quét component. Ví dụ này sử dụng **direct exchange**, phù hợp để quan sát một routing key khớp chính xác.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DemoRabbitTopology {

    @Bean
    DirectExchange demoExchange() {
        return new DirectExchange("demo.events", true, false);
    }

    @Bean
    Queue demoQueue() {
        return QueueBuilder.durable("demo.audit").build();
    }

    @Bean
    Binding demoBinding(Queue demoQueue, DirectExchange demoExchange) {
        return BindingBuilder.bind(demoQueue)
                .to(demoExchange)
                .with("demo.created");
    }
}
~~~

Spring AMQP có thể tự khai báo các bean này với broker thông qua **RabbitAdmin** khi ứng dụng kết nối. Queue và exchange trong ví dụ được khai báo **durable** để vẫn tồn tại khi ứng dụng dừng. Lưu ý rằng độ bền queue không tự nó bảo đảm mọi message đều được lưu an toàn; trong thực tế còn cần chính sách message persistence, publisher confirms và cấu hình broker phù hợp.

### 3.4. Tạo producer phát message

Tạo endpoint HTTP để kích hoạt **RabbitTemplate**. Giá trị body ở đây là một chuỗi đơn giản để tránh phải thiết lập JSON converter:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lab")
public class DemoPublishController {
    private final RabbitTemplate rabbitTemplate;

    public DemoPublishController(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @PostMapping("/publish")
    public ResponseEntity<String> publish(
            @RequestParam(defaultValue = "hello") String body) {
        rabbitTemplate.convertAndSend("demo.events", "demo.created", body);
        return ResponseEntity.accepted()
                .body("Da goi RabbitTemplate de publish: " + body);
    }
}
~~~

**Chú ý:** phản hồi HTTP **202** của endpoint mẫu chỉ nói rằng phương thức gửi đã được gọi mà không ném lỗi ngay tại thời điểm đó; nó **không xác nhận consumer đã xử lý thành công**, và bản thân lời gọi **convertAndSend** cũng không thay thế publisher confirm hay publisher return.

### 3.5. Tạo consumer xử lý chậm có chủ đích

Listener tạm ngủ 5 giây để bạn kịp nhìn thấy trạng thái **Unacked** trên giao diện:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class DemoMessageListener {
    private static final Logger log =
            LoggerFactory.getLogger(DemoMessageListener.class);

    @RabbitListener(queues = "demo.audit")
    public void receive(String body) throws InterruptedException {
        log.info("START handling message: {}", body);
        Thread.sleep(5_000); // Chỉ để quan sát trong bài thực hành.
        log.info("DONE handling message: {}", body);
    }
}
~~~

Không dùng **Thread.sleep** như phương pháp xử lý chậm trong ứng dụng thật. Đoạn mã chủ động tạo độ trễ để minh họa: khi listener đang xử lý, message đã được giao cho consumer nhưng chưa ack; sau khi phương thức kết thúc bình thường, container mới gửi ack.

Khởi động Spring Boot bằng cách quen thuộc của dự án (chẳng hạn **mvnw spring-boot:run** với Maven Wrapper). Lúc ứng dụng kết nối tới RabbitMQ, cấu hình topology sẽ được khai báo, sau đó listener bắt đầu nhận message.

## 4. Khám phá giao diện RabbitMQ Management

Các nhãn có thể khác đôi chút giữa các phiên bản Management; hãy tìm các khu vực cùng chức năng:

| Khu vực | Quan sát điều gì? | Cách dùng trong bài |
|---|---|---|
| **Overview** | Tổng quan kết nối, queue, message và tốc độ xử lý | Xác minh broker đang nhận hoạt động, xem biểu đồ chung |
| **Connections** | Các kết nối TCP/AMQP tới broker | Kiểm tra ứng dụng Spring Boot đã kết nối chưa |
| **Channels** | Channel AMQP trên các kết nối | Quan sát hoạt động publish/consumer và trạng thái channel |
| **Exchanges** | Exchange, loại exchange, binding, thao tác publish thử | Tìm **demo.events**, xem routing key |
| **Queues and Streams** (hoặc **Queues**) | Queue, message counts, consumer, rates, chi tiết binding | Tìm **demo.audit** để theo dấu message |
| **Admin** | Users, permissions, vhosts, policies tùy quyền | Kiểm tra quyền khi bị từ chối truy cập |

Vào **Exchanges → demo.events** và xác minh loại exchange là **direct**; phần bindings cần thể hiện đường đi từ **demo.events** tới queue **demo.audit** với routing key **demo.created**.

Vào **Queues and Streams → demo.audit**. Khi ứng dụng đang chạy và chưa publish message, bạn thường thấy **Ready = 0**, **Unacked = 0**, **Total = 0** và **Consumers = 1**. Nếu có ứng dụng hoặc consumer khác đang dùng chung queue, các con số có thể khác.

## 5. Thực hành 1 — Theo dấu một message khi consumer đang hoạt động

Giữ RabbitMQ và Spring Boot cùng chạy. Từ terminal, gọi endpoint:

~~~bash
curl -X POST "http://localhost:8080/lab/publish?body=first-message"
~~~

Trên Windows PowerShell, có thể dùng **curl.exe** thay cho **curl** nếu máy đang ánh xạ **curl** thành lệnh riêng của PowerShell.

Chuyển đến **Queues and Streams → demo.audit** và quan sát:

1. Message được publish tới **demo.events** với key **demo.created**.
2. Binding phù hợp đưa message vào **demo.audit**.
3. Listener nhận message; log xuất hiện **START handling message**.
4. Trong khoảng xử lý 5 giây, message **có thể hiện ở Unacked = 1** và không còn trong Ready.
5. Khi log xuất hiện **DONE handling message** và Spring AMQP ack, message rời queue; **Ready**, **Unacked** và **Total** trở về 0.

Nhấn refresh nếu cần. Management lấy mẫu theo thời gian, nên với message xử lý nhanh hoặc giao diện cập nhật chậm bạn có thể không nhìn thấy mọi trạng thái trung gian. **Không thấy Unacked = 1 không đủ để kết luận listener không hoạt động.** Luôn đối chiếu log và số liệu.

### Hiểu đúng ba bộ đếm

| Chỉ số trong queue | Ý nghĩa | Không có nghĩa là |
|---|---|---|
| **Ready** | Message đang chờ được giao cho consumer | Tổng số message từng publish |
| **Unacked** | Message đã được giao nhưng broker đang chờ acknowledgment | Consumer đã xử lý nghiệp vụ thành công |
| **Total** | Tổng message hiện nằm trong hai nhóm Ready và Unacked | Tổng message lịch sử của hệ thống |
| **Consumers** | Số consumer đang đăng ký với queue | Số bản sao message hoặc số lần xử lý thành công |

Trong một ảnh chụp trạng thái của queue, thông thường **Total = Ready + Unacked**; ở biểu đồ tổng quan và các lần refresh gần nhau có thể có chênh lệch tạm thời do thời điểm lấy mẫu.

## 6. Thực hành 2 — Consumer tạm ngừng, message xếp hàng

Để quan sát backlog, trước tiên **dừng ứng dụng Spring Boot**, nhưng **giữ container RabbitMQ hoạt động**. Vì queue và exchange đã được khai báo durable, chúng vẫn tồn tại trên broker sau khi ứng dụng dừng trong điều kiện bình thường.

Vào **Exchanges → demo.events**. Tìm khu vực **Publish message**, điền:

- **Routing key:** demo.created
- **Payload:** hello-from-management-1
- **Payload encoding/properties:** giữ mặc định cho bài thực hành nếu không có yêu cầu riêng.

Nhấn **Publish message**. Lặp lại với **hello-from-management-2** và **hello-from-management-3**. Một số phiên bản giao diện báo thông tin message được publish hoặc định tuyến, nhưng đừng chỉ dựa vào lời báo đó; hãy mở queue để kiểm chứng.

Ở **Queues and Streams → demo.audit**, với môi trường bài lab chỉ có một producer và một queue nhận message, kỳ vọng:

| Thời điểm | Ready | Unacked | Consumers | Diễn giải |
|---|---:|---:|---:|---|
| Sau khi dừng ứng dụng, trước lúc gửi | 0 | 0 | 0 | Queue trống, không có consumer |
| Sau khi publish 3 message từ giao diện | 3 | 0 | 0 | Ba message chờ được giao |
| Khởi động lại ứng dụng, một message đang xử lý | Khoảng 2 | Khoảng 1 | 1 | Prefetch = 1; consumer xử lý có độ trễ |
| Sau khi cả ba message xử lý và được ack | 0 | 0 | 1 | Queue đã hết message chờ và chưa ack |

Các giá trị là **kỳ vọng trong lab sạch**, không phải con số cố định tại mọi ảnh chụp. Khi khởi động lại ứng dụng, listener lần lượt nhận ba message; xem log **START/DONE** để xác minh thứ tự xử lý theo thực nghiệm. Nếu một listener gặp lỗi trước ack, message có thể được giao lại thay vì biến mất khỏi queue.

Thí nghiệm cho thấy RabbitMQ có thể **tách thời điểm producer phát thông điệp khỏi thời điểm consumer xử lý**. Tuy nhiên, broker vẫn có giới hạn bộ nhớ, đĩa, tốc độ và cấu hình; queue tăng vô hạn không phải một thiết kế an toàn.

## 7. Thực hành 3 — Routing key sai thì message đi đâu?

Giữ queue **demo.audit** và binding đã tạo. Trong **Exchanges → demo.events → Publish message**, thử:

- **Routing key:** demo.unknown
- **Payload:** wrong-routing-key

Vì **demo.events** là direct exchange và binding hiện tại chỉ khớp **demo.created**, message với key **demo.unknown** **không được định tuyến tới demo.audit**. Nếu không có binding hoặc alternate exchange nào khác phù hợp, RabbitMQ có thể loại message không định tuyến được. Hãy đối chiếu **Ready/Unacked** của queue trước và sau thao tác; chúng không nên tăng chỉ do message sai key.

Điều này lý giải vì sao **publish không lỗi** vẫn chưa chứng minh queue đích đã nhận message. Khi xây producer tin cậy cần cân nhắc:

- **Publisher confirms:** broker báo kết quả xác nhận publication ở mức broker; không phải xác nhận của consumer.
- **Mandatory flag và publisher returns:** giúp ứng dụng phát hiện thông điệp không định tuyến được trong trường hợp phù hợp.
- **Binding/routing key đúng:** kiểm tra exchange type, tên queue, routing key và vhost khi message không đến nơi.

Management giúp quan sát để chẩn đoán, nhưng việc tự động xử lý trường hợp publish thất bại hoặc message không định tuyến phải được thiết kế ở phía ứng dụng.

## 8. Quan sát tốc độ và trạng thái xử lý

Ngoài số message tại một thời điểm, queue và trang Overview thường cung cấp **message rates**. Một số chỉ số bạn có thể gặp:

| Tín hiệu | Diễn giải khi quan sát | Gợi ý kiểm tra |
|---|---|---|
| **Publish** | Tốc độ message được publish | Có traffic từ producer tới exchange/broker hay không? |
| **Deliver / Get** | Tốc độ message được giao hoặc lấy từ queue | Consumer có đang nhận message không? |
| **Ack** | Tốc độ message được consumer ack | Listener xử lý và xác nhận có theo kịp không? |
| **Ready tăng liên tục** | Message chờ ngày càng nhiều | Thiếu consumer, consumer quá chậm, tốc độ publish quá cao |
| **Unacked cao kéo dài** | Message đã được giao nhưng chưa ack | Công việc chậm, blocked, prefetch lớn, listener/connection gặp vấn đề |
| **Consumers = 0** | Queue không có consumer đang đăng ký | Ứng dụng dừng, listener chưa khởi tạo, queue/vhost sai |

**Publish rate cao không đồng nghĩa xử lý nghiệp vụ thành công.** Ngược lại, **Ready = 0** cũng không chứng minh mọi message đã xử lý đúng: message có thể đang Unacked, bị consumer ack nhưng nghiệp vụ chưa được lưu đúng, bị đưa tới queue khác hoặc đã bị loại theo chính sách.

Số liệu Management thường được **lấy mẫu/tổng hợp**, có thể trễ, bị làm mịn hoặc không hiển thị nếu tính năng thu thập statistics bị tắt. Khi cần đo hệ thống trong thời gian dài, nên xuất metrics qua hệ thống giám sát phù hợp, ví dụ RabbitMQ Prometheus plugin kết hợp dashboard và cảnh báo.

## 9. Khi có lỗi, nhìn ở đâu trước?

| Hiện tượng | Kiểm tra nhanh trên Management | Khả năng cần điều tra |
|---|---|---|
| Spring Boot không kết nối được | **Connections** không có ứng dụng; kiểm tra broker và vhost | Sai host/port, user/password, quyền, TLS, broker chưa sẵn sàng |
| Producer nói đã gửi nhưng queue không tăng | **Exchanges → bindings**; kiểm tra exchange/routing key/vhost | Không định tuyến, queue khác, consumer tiêu thụ quá nhanh, message bị loại |
| **Ready** tăng, **Consumers = 0** | **Queues and Streams → demo.audit** | Listener chưa chạy, dùng sai tên queue/vhost, chưa tạo subscription |
| **Ready** tăng, **Consumers > 0** | Xem **Deliver/ack rates**, log và năng lực consumer | Consumer chậm hơn producer, xử lý lỗi lặp, giới hạn concurrency/prefetch |
| **Unacked** tăng hoặc đứng yên quá lâu | Queue details, channel/connection, log listener | Listener treo, xử lý lâu, chưa ack, tài nguyên bị nghẽn |
| Message liên tục quay lại queue | Trạng thái ready/unacked, log retry/requeue | Consumer exception, nack/requeue lặp, thiếu giới hạn retry |
| Message xuất hiện ở DLQ | Kiểm tra queue đích dead-letter, binding và lý do lỗi trong header nếu có | Retry hết lượt, reject không requeue, TTL, giới hạn queue hoặc chính sách dead-letter |

Một số lưu ý khi phân tích:

1. **Không suy kết quả nghiệp vụ từ ack.** Ack cho broker biết message đã được xác nhận tiêu thụ; việc cập nhật database, gọi API ngoài và giao dịch có thành công theo yêu cầu hay không cần bằng chứng riêng.
2. **Không suy lịch sử từ queue hiện tại.** Message đã ack sẽ không còn trong queue; Management không lưu toàn bộ payload từng message đi qua.
3. **Cẩn thận với Get messages.** Chức năng lấy message thủ công trong giao diện có chế độ acknowledgment/requeue khác nhau. Đây là thao tác có thể **làm thay đổi trạng thái message**; nếu chỉ muốn quan sát traffic, ưu tiên bộ đếm, rates và log.
4. **Để ý tên vhost.** Exchange và queue thuộc vhost cụ thể. Hai queue trùng tên trong hai vhost khác nhau là hai tài nguyên khác nhau.

## 10. Liên hệ với retry, dead-letter và giao dịch

Trong Spring AMQP, khi listener lỗi, các lựa chọn như retry trong ứng dụng, reject, requeue, dead-letter hoặc xử lý bù sẽ quyết định đường đi của message. Management có thể giúp bạn thấy **message còn trong queue chính hay đã vào DLQ**, nhưng không thể tự biết toàn bộ nguyên nhân lỗi nếu ứng dụng không ghi log và metadata đầy đủ.

Một luồng xử lý tin cậy thường cần kết hợp:

- **Producer:** ghi log event ID, correlation ID; theo dõi publisher confirm/return; cân nhắc **transactional outbox** khi cần đồng bộ việc lưu DB với phát sự kiện.
- **Broker:** exchange, queue và binding đúng; độ bền và chính sách lưu trữ phù hợp; chính sách dead-letter và giới hạn tài nguyên rõ ràng.
- **Consumer:** idempotency để tránh xử lý trùng; ack đúng thời điểm; retry có giới hạn và ghi lý do lỗi hữu ích.
- **Quan sát:** metrics Ready/Unacked/Consumers, backlog theo thời gian, độ trễ xử lý, số message trong DLQ, log có event ID để ghép các giai đoạn.

Ví dụ khi consumer giữ hàng lỗi giữa chừng, broker có thể giao lại message chưa ack. Nếu ứng dụng không có **idempotency**, cùng một đơn hàng có nguy cơ bị xử lý nhiều lần. Nếu message không thể xử lý được, chính sách retry và DLQ giúp tách lỗi ra để điều tra; chỉ nhìn thấy queue trống không phải đủ để kết luận quy trình đã thành công.

## 11. Bài tập mở rộng

**Bài tập A — Thay đổi tốc độ tiêu thụ.** Tăng độ trễ listener từ 5 lên 10 giây, gửi 10 message, rồi quan sát **Ready** giảm dần và **Unacked** khi **prefetch = 1**. Ghi lại thời gian tương đối để xử lý hết hàng đợi.

**Bài tập B — Hai consumer dùng chung một queue.** Chạy thêm một instance consumer hợp lệ kết nối cùng vhost/queue (tránh xung đột cổng HTTP giữa các instance). Quan sát **Consumers** thay đổi và thông điệp được phân chia giữa các consumer thay vì mỗi consumer nhận tất cả bản sao. Đừng kết luận việc chia tải lúc nào cũng theo tỷ lệ bằng nhau.

**Bài tập C — Nhiều queue nhận cùng sự kiện.** Tạo thêm queue **demo.notifications** với binding **demo.created** tới cùng exchange **demo.events**. Publish một message và quan sát **cả hai queue** có thể nhận một bản sao riêng, vì exchange định tuyến tới từng queue khớp binding.

**Bài tập D — Consumer lỗi.** Cho listener ném exception có chủ đích và so sánh trạng thái queue khi đã cấu hình retry/requeue/DLQ. Ghi rõ cấu hình đang dùng, vì hành vi mặc định không thay thế một chính sách retry an toàn.

## 12. Tự kiểm tra

**Câu 1.** Ready = 8, Unacked = 2, Consumers = 1. Có thể hiểu điều gì?

> Có 8 message đang chờ giao, 2 message đã được giao nhưng chưa ack, và 1 consumer đang đăng ký trên queue. Tổng số message đang trong queue theo hai trạng thái là khoảng 10 tại thời điểm quan sát. Chưa thể khẳng định hai message đã xử lý thành công.

**Câu 2.** Endpoint gọi RabbitTemplate trả HTTP 202 nhưng queue đích không tăng. Các khả năng là gì?

> Routing key/binding không khớp, sai exchange hoặc vhost, message được consumer lấy quá nhanh, message vào queue khác, hoặc publication chưa được xác nhận như mong đợi. Cần đối chiếu exchange, binding, queue và publisher confirms/returns.

**Câu 3.** RabbitMQ Management có cho phép xem toàn bộ nội dung các message đã xử lý hôm qua không?

> Không. Đây là giao diện quản trị và số liệu vận hành. Message đã ack thường bị xóa khỏi queue. Muốn tra cứu lịch sử cần thiết kế log, tracing hoặc hệ thống lưu trữ sự kiện phù hợp.

**Câu 4.** Tại sao cần quan sát cả Ready lẫn Unacked?

> Ready cho biết số message chờ giao; Unacked cho biết số message đang chờ consumer xác nhận. Chỉ nhìn Ready có thể bỏ sót các consumer đang xử lý quá chậm hoặc không ack.

## 13. Ghi nhớ

- **Exchanges và Bindings** giúp xác minh message có đường vào queue đúng hay không; **Queues and Streams** cho biết message đang chờ hoặc đã giao nhưng chưa ack.
- **Ready, Unacked, Total, Consumers** là các chỉ số căn bản để chẩn đoán lưu lượng RabbitMQ. Kết hợp với publish/deliver/ack rates và log ứng dụng để hiểu đúng diễn biến.
- **RabbitTemplate gửi thông điệp**, **@RabbitListener xử lý**, **RabbitMQ Management quan sát trạng thái broker**. Sự kiện publish, consumer ack và hoàn tất nghiệp vụ là **ba mốc khác nhau**.
- Management hữu ích trong phòng thực hành và xử lý sự cố. Độ tin cậy thực tế còn cần publisher confirms/returns, retry có giới hạn, DLQ, idempotency, giao dịch phù hợp và giám sát dài hạn.
