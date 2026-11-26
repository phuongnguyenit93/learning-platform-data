# Thứ tự xử lý return và confirm cho cùng thông điệp

Giả sử dịch vụ đặt hàng phát một sự kiện qua `RabbitTemplate`. RabbitMQ gửi **publisher confirm ACK**, nhưng queue mà dịch vụ dự kiến lại không nhận message. Liệu ACK có chứng minh đã định tuyến thành công? **Không.** Khi producer publish với cờ `mandatory`, một message **không được exchange định tuyến tới queue nào** có thể được RabbitMQ **trả về (publisher return)** rồi vẫn được broker **ACK ở cấp publisher confirm**. Hai tín hiệu này trả lời hai câu hỏi khác nhau.

Bài thuộc chương **Confirm và return** của module **SPRING_AMQP**. Trọng tâm là **thứ tự xử lý return và confirm cho chính cùng một publication**, cách Spring AMQP đưa thông tin return vào `CorrelationData`, và cách producer đưa ra quyết định đúng khi gửi qua exchange, queue và binding. Ví dụ có `RabbitTemplate`, `@RabbitListener`, RabbitMQ Management, cùng các lưu ý về retry, dead-letter, giao dịch và quan sát để xây dựng xử lý bất đồng bộ đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **publisher return**, **publisher confirm ACK/NACK** và **consumer acknowledgment**.
2. Giải thích vì sao một message **unroutable** có thể tạo **return rồi confirm ACK**.
3. Diễn giải thứ tự tín hiệu đối với **một publication**, không suy thành thứ tự toàn cục giữa nhiều message đồng thời.
4. Cấu hình `publisher-confirm-type: correlated`, `publisher-returns: true` và `mandatory: true` bằng Spring Boot.
5. Dùng `CorrelationData.getReturned()` cùng `CorrelationData.getFuture()` để kết luận đúng cho từng `eventId`.
6. Thực hành hai kịch bản routing key đúng/sai, phân tích log và xử lý trạng thái `UNKNOWN` khi thiếu confirm.
7. Thiết kế quyết định retry, dead-letter/idempotency và trạng thái outbox dựa trên các tín hiệu phù hợp.

## 2. Hai luồng phản hồi độc lập ở phía producer

### 2.1. Publisher return: message không tới được queue nào

Khi producer gửi `basic.publish` với **`mandatory=true`**, nếu RabbitMQ không thể định tuyến publication tới **bất kỳ queue đích nào** theo các binding/quy tắc exchange có hiệu lực, broker có thể trả message qua **`basic.return`**. Return cung cấp thông tin về nguyên nhân, exchange, routing key và message được trả lại.

Ví dụ với một direct exchange:

~~~text
Exchange: orders.events
Binding:  orders.events --[routing key = order.created]--> orders.created

Publish key = "order.created" : có queue phù hợp → không return
Publish key = "order.unknown" : không queue phù hợp → basic.return nếu mandatory=true
~~~

Trong trường hợp không có **alternate exchange** hoặc một cơ chế định tuyến thay thế hữu hiệu, return cho producer biết message không có queue nhận. Nếu chỉ **queue dự kiến** bị thiếu nhưng vẫn có **queue khác** phù hợp, message có thể **không return**: return phát hiện trạng thái *không định tuyến được tới bất kỳ queue nào*, chứ không tự xác nhận “đã vào đúng queue nghiệp vụ”.

Không bật `mandatory`, message unroutable thông thường có thể bị broker loại mà **không có publisher return**. Khi đó publisher confirm ACK (nếu có) càng không đủ để biết message có queue đích hay không.

### 2.2. Publisher confirm: broker xác nhận publication

Khi bật publisher confirms trên channel, RabbitMQ gửi **`basic.ack`** hoặc **`basic.nack`** cho publication phía producer. Confirm có ý nghĩa ở **broker–producer**: broker ACK/NACK việc nhận và xử lý publication theo cơ chế confirm; **không phải** ACK do một `@RabbitListener` gửi sau xử lý nghiệp vụ.

| Tín hiệu | Phía phát sinh | Câu hỏi được trả lời |
|---|---|---|
| **Publisher return (`basic.return`)** | RabbitMQ → producer khi publication unroutable và có `mandatory` phù hợp | Message có **không được định tuyến tới queue nào** không? |
| **Publisher confirm ACK (`basic.ack`)** | RabbitMQ → producer trên confirm channel | Broker đã xác nhận publication chưa? |
| **Publisher confirm NACK (`basic.nack`)** | RabbitMQ → producer trên confirm channel | Broker đã từ chối xác nhận thành công publication chưa? |
| **Consumer ACK (`basic.ack`)** | Consumer → RabbitMQ trên **consumer channel** | Delivery cụ thể đã được consumer xác nhận chưa? |
| **Kết quả nghiệp vụ** | Ứng dụng/DB | Đơn hàng, giao dịch hoặc tác vụ đã hoàn tất đúng hợp đồng chưa? |

**Điểm dễ nhầm:** cả publisher confirm và consumer acknowledgment đều dùng tên `basic.ack` trong giao thức, nhưng xảy ra trên **những channel, ngữ cảnh và chiều giao tiếp khác nhau**.

### 2.3. Return và confirm không thay thế lẫn nhau

Nếu message unroutable nhưng broker đã xử lý publication theo quy tắc của mình, publisher hoàn toàn có thể thấy:

~~~text
RETURN:  replyCode=312, replyText=NO_ROUTE, routingKey=order.unknown
CONFIRM: ACK
~~~

Đây **không phải mâu thuẫn**. Return nói rằng **không có queue nhận**. Confirm ACK nói rằng **broker đã xác nhận publication**. Vì thế, nếu nghiệp vụ yêu cầu message được đưa vào queue, kết quả **`ACK + returned` phải bị xem là thất bại về định tuyến**.

## 3. Thứ tự thực tế cho cùng một publication

### 3.1. Ở RabbitMQ: `basic.return` đi trước publisher confirm

Với một message unroutable được publish bằng `mandatory=true` trên channel có publisher confirms, RabbitMQ gửi **`basic.return` trước khi gửi `basic.ack` của publication tương ứng**.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer / RabbitTemplate
    participant X as RabbitMQ exchange
    participant Q as Queue mong muốn
    P->>X: basic.publish(mandatory=true, key=order.unknown)
    X--xQ: Không có binding khớp
    X-->>P: basic.return(312 NO_ROUTE, message)
    X-->>P: basic.ack (publisher confirm)
    Note over P,X: ACK publication dù message không tới queue
~~~

Ở mức protocol, thông tin `basic.return` chứa **nội dung message** và dữ liệu routing. Publisher confirm tham chiếu publication bằng **sequence number/delivery tag trong phạm vi publisher channel**, không phải bằng ID nghiệp vụ do ứng dụng tự tạo. Thư viện Spring AMQP giúp gắn confirm với `CorrelationData` của lần gửi.

**Không suy từ sơ đồ thành “broker luôn ACK mọi message”.** Publication có thể nhận NACK trong tình huống lỗi broker; lỗi channel hoặc mất connection có thể ngăn ứng dụng nhìn thấy phản hồi cuối cùng.

### 3.2. Ở Spring AMQP: return được gắn vào `CorrelationData` trước future confirm

Trong luồng **correlated publisher confirms** của Spring AMQP, một `CorrelationData` có thể chứa:

- `id`: mã tương quan do ứng dụng đặt cho **một lần publish**.
- `getReturned()`: thông tin message bị return, nếu có return được ghép với publication.
- `getFuture()`: future hoàn tất khi có kết quả publisher confirm của publication đó.

Khi Spring AMQP xử lý returns và correlated confirms phù hợp, **thông tin returned message được gắn vào `CorrelationData` trước khi future confirm hoàn tất**. Do vậy callback `whenComplete` của `getFuture()` có thể kiểm tra **cả** `confirm.isAck()` **và** `correlation.getReturned()` để phân loại kết quả cho chính publication.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Mã ứng dụng
    participant T as RabbitTemplate / ConnectionFactory
    participant B as RabbitMQ
    A->>T: convertAndSend(..., CorrelationData E-42)
    T->>B: basic.publish(mandatory=true)
    B-->>T: basic.return(NO_ROUTE)
    T->>T: Gắn ReturnedMessage vào CorrelationData E-42
    T-->>A: ReturnsCallback (nếu được cài)
    B-->>T: basic.ack publisher confirm
    T-->>A: Hoàn tất CorrelationData.getFuture()
    A->>A: ACK + returned != null => UNROUTABLE
~~~

Trên thực tế, callback return và confirm có thể được dispatch bất đồng bộ; **đừng viết mã phụ thuộc vào thứ tự xuất hiện của những dòng log từ nhiều thread**. Quy tắc an toàn ở ví dụ này là **ra quyết định trong confirm future bằng dữ liệu của chính `CorrelationData`**, không đối chiếu hai dòng log ngẫu nhiên theo thời gian.

Nếu callback return thực hiện công việc rất lâu, nó có thể trì hoãn xử lý/hoàn tất confirm tương ứng; vì vậy callback nên nhẹ và không chặn luồng để gọi API/DB chậm. Tránh dùng các thời điểm quan sát từ Management hoặc console làm cam kết về độ trễ.

### 3.3. Thứ tự giữa nhiều message không được cam kết toàn cục

Hai publication `E-42` và `E-43` có thể được gửi trên các channel khác nhau, hoặc có trạng thái/routing khác nhau. Một lịch sử log có thể như sau:

~~~text
E-42 -> RETURN
E-43 -> CONFIRM ACK
E-42 -> CONFIRM ACK
~~~

Điều này vẫn hợp lệ: **return của E-42 đi trước confirm của E-42**. Không có quy tắc rằng mọi return của tất cả message phải xảy ra trước mọi confirm của tất cả message. Khi ứng dụng publish đồng thời, luôn gắn **ID duy nhất** cho từng `CorrelationData` và cho log; không sử dụng biến `lastReturnedMessage` dùng chung để đoán kết quả message nào bị trả về.

## 4. Bảng quyết định: ACK/NACK kết hợp return

Giả sử producer dùng exchange đã tồn tại, publisher confirms và returns được bật đúng, `mandatory=true`. Kết quả cần phân loại:

| Publisher confirm | Return trên **cùng publication** | Ý nghĩa thực dụng | Hành động của producer |
|---|---|---|---|
| **ACK** | **Không** | Broker xác nhận publication; không phát hiện unroutable bằng return | Ghi nhận `BROKER_ACCEPTED`, tiếp tục theo dõi nghiệp vụ |
| **ACK** | **Có** | Broker xác nhận publication **nhưng không có queue đích** | Ghi `UNROUTABLE`, kiểm tra exchange/binding/routing key |
| **NACK** | Không hoặc có thể có trạng thái trả về cần xem xét | Broker không xác nhận publication thành công | Ghi `BROKER_NACK` và xử lý retry theo chính sách |
| **Chưa thấy / timeout** | Không có thông tin chắc chắn | Không biết publication đã được broker nhận hay confirm thất lạc | Ghi `UNKNOWN`, đối soát và retry an toàn |
| **Lỗi gửi đồng bộ / channel exception** | Không phải luồng return bình thường | Ví dụ exchange không tồn tại hoặc kết nối hỏng | Ghi lỗi riêng, kiểm tra broker/topology trước khi retry |

**Diễn giải ACK + không return có điều kiện:** điều này **không** bảo đảm consumer đã ACK, cũng không chứng minh message vào *đúng* queue mong muốn nếu exchange có nhiều binding hay alternate exchange. Nó chỉ cho biết publisher không nhận thông báo unroutable theo cấu hình, trong khi broker ACK publication.

### Một số kịch bản đối chứng

| Cấu hình / tình huống | Publisher return? | Confirm có thể là ACK? | Ghi chú |
|---|---|---|---|
| Routing key khớp ít nhất một queue, `mandatory=true` | Không | Có | Consumer chưa chắc đã chạy |
| Không routing tới queue nào, `mandatory=true` | **Có** | **Có** | Đúng trường hợp “return trước confirm” |
| Không routing tới queue nào, `mandatory=false` | Thường không | Có | Dễ mất message âm thầm |
| Exchange không tồn tại | Không phải `NO_ROUTE` thông thường | Có thể không có confirm bình thường | Broker có thể đóng channel do lỗi `NOT_FOUND` |
| Message được định tuyến qua alternate exchange đến một queue | Có thể không return | Có | Cần biết topology của alternate exchange |
| Consumer nhận rồi xử lý lỗi | Không phải publisher return | Có | Xử lý bởi consumer retry/NACK/DLX, độc lập publish |

**Không nhầm “publisher return” với “trả lại message vào queue”.** `basic.return` đưa message **về producer** khi không định tuyến; `basic.nack(..., requeue=true)` của **consumer** yêu cầu đưa delivery trở lại queue. Hai cơ chế không cùng mục đích.

## 5. Cấu hình lab Spring AMQP

### 5.1. Broker và dependency

Bạn có thể dùng RabbitMQ Management ở môi trường local:

~~~bash
docker run -d --name rabbitmq-confirm-return-lab -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -e RABBITMQ_DEFAULT_USER=lab -e RABBITMQ_DEFAULT_PASS=lab123456 rabbitmq:4-management
~~~

Địa chỉ quản trị mẫu: `http://localhost:15672`. Tài khoản `lab/lab123456` **chỉ dùng trong lab**, không đưa credentials cứng vào source production hay mở cổng Management cho Internet. Nếu có broker đang chạy trên cổng 5672/15672, sử dụng broker đó hoặc đổi cổng ánh xạ.

Ví dụ Java dưới đây dùng Spring Boot 3.x / Spring AMQP 3.x trên Java 17+:

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

### 5.2. Bật correlated confirms, returns và mandatory

Trong `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: lab
    password: lab123456

    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true

    listener:
      simple:
        acknowledge-mode: auto
~~~

Ý nghĩa:

| Cấu hình Spring Boot | Vai trò |
|---|---|
| `publisher-confirm-type: correlated` | Bật correlated publisher confirms của `CachingConnectionFactory` để dùng `CorrelationData` |
| `publisher-returns: true` | Cho Spring AMQP tiếp nhận message return từ broker |
| `template.mandatory: true` | Yêu cầu broker trả lại publication không có queue đích phù hợp |
| `listener.simple.acknowledge-mode: auto` | Container ACK delivery sau khi listener hoàn tất thành công, không liên quan ACK của producer |

Trong cấu hình Spring Boot thông thường, `spring-boot-starter-amqp` tự tạo **`CachingConnectionFactory`** và `RabbitTemplate` nếu chưa được ứng dụng thay bằng bean khác. Luồng `ConfirmType.CORRELATED` cần connection factory và template thực tế hỗ trợ correlated confirms; **đừng tự thay bằng `PooledChannelConnectionFactory` rồi mặc nhiên cho rằng mọi property trên sẽ hoạt động như với caching**.

Nếu ứng dụng tự tạo `RabbitTemplate`, cần bảo đảm `setMandatory(true)`, returns callback, confirm configuration và connection factory **đúng bean được sử dụng**; thay đổi YAML không có tác dụng lên một template hoàn toàn tùy chỉnh nếu ứng dụng bỏ qua auto-configuration.

### 5.3. Topology: có một routing key hợp lệ và một key sai

Để phân biệt có/không return, khai báo **một direct exchange**, **một durable queue** và **một binding**:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ConfirmReturnTopology {

    @Bean
    DirectExchange demoConfirmExchange() {
        return new DirectExchange("demo.confirm.events", true, false);
    }

    @Bean
    Queue demoAcceptedQueue() {
        return QueueBuilder.durable("demo.confirm.accepted").build();
    }

    @Bean
    Binding demoAcceptedBinding(Queue demoAcceptedQueue,
                                DirectExchange demoConfirmExchange) {
        return BindingBuilder.bind(demoAcceptedQueue)
                .to(demoConfirmExchange)
                .with("order.created");
    }
}
~~~

Routing key `order.created` **khớp** binding; `order.unknown` **không khớp** (giả sử không có binding khác và exchange không có alternate exchange). Spring AMQP thường khai báo các bean qua `RabbitAdmin` khi ứng dụng kết nối. Nếu broker đang có exchange/queue cùng tên với loại hoặc arguments khác, khai báo có thể thất bại; hãy thử trong vhost/tên lab sạch.

## 6. Producer: ghép return và confirm bằng `CorrelationData`

### 6.1. Đăng ký returns callback để quan sát sự kiện return

Bean sau dùng **một returns callback** trên `RabbitTemplate`. Nó chỉ ghi log, không quyết định rằng message đã thất bại hoặc thử gửi lại ngay trong callback.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class DemoReturnsObserver {
    private static final Logger log =
            LoggerFactory.getLogger(DemoReturnsObserver.class);

    public DemoReturnsObserver(RabbitTemplate rabbitTemplate) {
        rabbitTemplate.setReturnsCallback(returned -> {
            String messageId = returned.getMessage()
                    .getMessageProperties().getMessageId();
            log.warn(
                    "RETURN messageId={} replyCode={} replyText={} exchange={} key={}",
                    messageId, returned.getReplyCode(),
                    returned.getReplyText(),
                    returned.getExchange(), returned.getRoutingKey());
        });
    }
}
~~~

`getReplyCode()`, `getReplyText()`, `getExchange()` và `getRoutingKey()` giúp truy vết thông tin broker trả lại. Với unroutable message trên direct exchange, thường thấy `replyCode=312` và `replyText=NO_ROUTE`; đừng thiết kế nghiệp vụ chỉ dựa vào **chuỗi log** đó.

**Chú ý:** `RabbitTemplate` thường chỉ có **một returns callback** được đăng ký. Nếu hệ thống đã có callback khác, đừng âm thầm ghi đè; hãy tổ chức việc dispatch về một thành phần quan sát/thực thi tập trung. Callback nên ngắn, không blocking, không đẩy business retry trực tiếp vào đường callback.

### 6.2. Publish từng message với `CorrelationData` riêng

~~~java
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ConfirmReturnPublisher {
    private static final Logger log =
            LoggerFactory.getLogger(ConfirmReturnPublisher.class);

    private final RabbitTemplate rabbitTemplate;

    public ConfirmReturnPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public String publish(String orderId, String routingKey) {
        String eventId = UUID.randomUUID().toString();
        CorrelationData correlation = new CorrelationData(eventId);

        rabbitTemplate.convertAndSend(
                "demo.confirm.events",
                routingKey,
                orderId,
                message -> {
                    var properties = message.getMessageProperties();
                    properties.setMessageId(eventId);
                    properties.setHeader("eventId", eventId);
                    properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    return message;
                },
                correlation);

        // Lời gọi gửi có thể kết thúc trước khi broker trả confirm.
        correlation.getFuture().whenComplete((confirm, error) -> {
            if (error != null) {
                log.error("CONFIRM_ERROR eventId={}", eventId, error);
                return;
            }
            if (confirm == null) {
                log.error("CONFIRM_UNKNOWN eventId={}", eventId);
                return;
            }

            var returned = correlation.getReturned();

            if (!confirm.isAck()) {
                log.warn("BROKER_NACK eventId={} reason={} returned={}",
                        eventId, confirm.getReason(), returned != null);
            } else if (returned != null) {
                log.warn("UNROUTABLE eventId={} replyCode={} key={}",
                        eventId,
                        returned.getReplyCode(),
                        returned.getRoutingKey());
            } else {
                log.info("BROKER_ACCEPTED eventId={} routingKey={}",
                        eventId, routingKey);
            }
        });

        return eventId;
    }
}
~~~

Trong ví dụ này, các ID có mục đích khác nhau:

- `CorrelationData(eventId)` dùng cho **tương quan future confirm** của **một** publication.
- `messageId` trong AMQP properties giúp tìm publication khi returns callback nhận bản sao message được trả về.
- Header `eventId` giúp consumer ghi log/kiểm tra trùng sau khi message đến queue.
- **Delivery tag** trong consumer ack là định danh *lần giao trên consumer channel*, không phải ID của `CorrelationData`.

**Cách ra quyết định quan trọng nhất:** chỉ đánh dấu `BROKER_ACCEPTED` sau khi confirm **ACK và `getReturned()==null`**; nếu confirm ACK nhưng `getReturned()!=null`, đánh dấu **`UNROUTABLE`**. Với message nhận publisher NACK, không coi đó là thành công dù ứng dụng đã gọi `convertAndSend`.

`whenComplete` có thể chạy sau khi `publish` đã trả về, hoặc chạy ngay khi đăng ký nếu future hoàn tất rất nhanh. Vì thế đoạn code **không suy luận trình tự nghiệp vụ chỉ từ thứ tự ghi log**. Trong hệ thống thật, ghi kết quả vào một tiến trình xử lý trạng thái/outbox có kiểm soát, thay vì chỉ log.

### 6.3. Endpoint HTTP để thử hai routing key

~~~java
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lab/confirm-return")
public class ConfirmReturnDemoController {
    private final ConfirmReturnPublisher publisher;

    public ConfirmReturnDemoController(ConfirmReturnPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/send")
    public ResponseEntity<Map<String, String>> send(
            @RequestParam String routingKey,
            @RequestParam(defaultValue = "ORD-1001") String orderId) {

        String eventId = publisher.publish(orderId, routingKey);
        return ResponseEntity.accepted().body(Map.of(
                "eventId", eventId,
                "state", "PENDING_CONFIRM"));
    }
}
~~~

HTTP `202 Accepted` ở đây chỉ nghĩa là **ứng dụng nhận yêu cầu gửi** và việc publish chưa ném exception ngay trong lời gọi; trạng thái `PENDING_CONFIRM` **chưa phải** broker ACK hoặc consumer thành công. Lỗi gửi đồng bộ (chẳng hạn connection không kết nối được) cần được HTTP error handler xử lý riêng.

### 6.4. Consumer minh họa

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class AcceptedOrderListener {
    private static final Logger log =
            LoggerFactory.getLogger(AcceptedOrderListener.class);

    @RabbitListener(queues = "demo.confirm.accepted")
    public void onCreated(String orderId,
                          @Header("eventId") String eventId) {
        log.info("CONSUMER_RECEIVED orderId={} eventId={}",
                orderId, eventId);
        // Nghiệp vụ thật phải xử lý idempotent trước khi ACK.
    }
}
~~~

Với listener container Spring AMQP ở chế độ `AUTO`, broker nhận consumer ACK sau khi listener hoàn tất bình thường. **Consumer có thể chạy trước hoặc sau thời điểm producer ghi log publisher confirm**, tùy lịch điều phối. Không có cam kết rằng log `BROKER_ACCEPTED` phải xuất hiện trước `CONSUMER_RECEIVED`.

## 7. Chạy thử: hai tình huống để phân biệt return và confirm

### 7.1. Routing key khớp: ACK nhưng không return

Sau khi khởi động broker và ứng dụng Spring, chạy:

~~~bash
curl -X POST "http://localhost:8080/lab/confirm-return/send?routingKey=order.created&orderId=ORD-1001"
~~~

Trong Windows PowerShell, dùng `curl.exe` thay cho alias `curl` nếu cần cú pháp như trên.

Với binding `order.created`, dự kiến:

~~~text
HTTP: {"eventId":"<uuid>","state":"PENDING_CONFIRM"}

LOG:  BROKER_ACCEPTED eventId=<uuid> routingKey=order.created
LOG:  CONSUMER_RECEIVED orderId=ORD-1001 eventId=<uuid>
~~~

Hai dòng log có thể đổi thứ tự. Không có dòng `RETURN` cho publication đó vì message đã được route vào queue. `BROKER_ACCEPTED` chưa phải bằng chứng side effect nghiệp vụ (nếu có) đã commit.

### 7.2. Routing key sai: return trước, rồi confirm ACK

~~~bash
curl -X POST "http://localhost:8080/lab/confirm-return/send?routingKey=order.unknown&orderId=ORD-1002"
~~~

Vì exchange không có binding khớp key `order.unknown`, broker có thể trả về:

~~~text
HTTP: {"eventId":"<uuid>","state":"PENDING_CONFIRM"}

LOG:  RETURN messageId=<uuid> replyCode=312 replyText=NO_ROUTE
      exchange=demo.confirm.events key=order.unknown

LOG:  UNROUTABLE eventId=<uuid> replyCode=312 key=order.unknown
~~~

Ở cấp AMQP, publisher confirm cho publication này thường là **ACK** sau `basic.return`. Trong future confirm, code thấy `confirm.isAck()==true` **và** `correlation.getReturned()!=null` nên ghi `UNROUTABLE`; nếu chỉ đọc `isAck()` mà bỏ qua returned message, producer sẽ phân loại sai thành thành công.

Không có log `CONSUMER_RECEIVED` cho publication này, vì queue `demo.confirm.accepted` không nhận được nó.

### 7.3. Bảng kết quả thực nghiệm

| Bước | Key publish | Return callback | Confirm future | Queue nhận? | Kết luận |
|---|---|---|---|---|---|
| A | `order.created` | Không | Thường ACK, `getReturned()==null` | Có | Broker accepted / routed |
| B | `order.unknown` | Có (`NO_ROUTE`) | Thường ACK, `getReturned()!=null` | Không | Unroutable |
| C | `order.unknown`, **mandatory=false** | Không | Vẫn có thể ACK | Không | Thiếu tín hiệu nhận biết unroutable |

Muốn chạy bước C, chỉnh tạm `mandatory` của template trong một bản lab riêng rồi khởi động lại. **Không dùng bước C trong hệ thống thật** nếu yêu cầu producer phải phát hiện message không đến queue nào.

### 7.4. Xác minh RabbitMQ Management

Truy cập Management; kiểm tra:

1. **Exchanges → demo.confirm.events**: exchange loại `direct`, binding `order.created` trỏ tới `demo.confirm.accepted`.
2. **Queues and Streams → demo.confirm.accepted**: số `Consumers` và các chỉ số `Ready/Unacked` nếu listener đang chạy.
3. Quan sát `ORD-1001` qua consumer log; nếu listener nhanh, queue có thể về `Ready=0` trước khi UI kịp refresh.
4. Đảm bảo không có binding `order.unknown`; publisher return được xác nhận qua **log producer**, không dựa vào một bảng lịch sử returns trong Management.
5. Khi thay topology, chú ý đúng **vhost** và quyền khai báo/publish/consume. Một binding khác do người dùng tạo có thể làm kết quả thí nghiệm B thay đổi.

Management cho biết topology và trạng thái queue tại thời điểm xem; **không phải hệ thống lưu trữ lịch sử mọi publisher confirm hay return**. Để điều tra một event cần `eventId`/`messageId`, routing key, confirm ACK/NACK, returned reply, timestamp và correlation ID.

## 8. Những điều dễ hiểu sai về thứ tự

### 8.1. Return callback có phải là tín hiệu cuối cùng?

Không. Return cho biết broker không tìm thấy queue phù hợp để định tuyến publication khi `mandatory` được áp dụng; producer vẫn có thể chờ publisher confirm. **Không nên xóa trạng thái đang chờ confirm hoặc retry ngay trong returns callback** mà không có thiết kế chống trùng: confirm và callback khác của cùng event có thể đến sau, gây hai nhánh logic cập nhật trạng thái mâu thuẫn.

Trong ví dụ, returns callback chỉ ghi log; quyết định cuối về **kết quả publication** được thực hiện từ future confirm và `CorrelationData.getReturned()`. Nếu cần hành động sớm hơn, vẫn phải có một state machine đảm bảo chuyển trạng thái đúng một lần và xử lý tín hiệu confirm tiếp theo.

### 8.2. Confirm callback luôn chạy ngay sau returns callback?

Không nên dựa vào độ trễ chính xác hay thứ tự **dòng log** giữa threads. Ở phía broker, `basic.return` được gửi trước publisher confirm cho **publication unroutable mandatory tương ứng**. Phía Spring, cơ chế correlated returns/confirm đảm bảo dữ liệu returned liên quan có sẵn trong `CorrelationData` trước khi future confirm hoàn tất; đó mới là thuộc tính đáng dựa vào.

Nếu callback xử lý chậm, connection thay đổi, hoặc nhiều event đang in-flight, log thời gian có thể không phản ánh trực tiếp thứ tự trên wire. Giữ callback ngắn và dùng correlation ID.

### 8.3. Có return tức broker đã reject message giống consumer NACK?

Không. Publisher return xảy ra **trước khi message vào queue** vì không định tuyến được. Consumer NACK/reject xảy ra **sau khi broker đã giao một delivery** cho consumer. Retry của producer cần sửa cấu hình routing hoặc kiểm tra topology; retry của consumer cần xử lý lỗi nghiệp vụ/hạ tầng, backoff và DLQ.

### 8.4. Nếu confirm ACK nhưng không return, liệu queue có chắc đã lưu vĩnh viễn?

Đừng suy ra bảo đảm mạnh hơn cấu hình. Publisher confirms có ngữ nghĩa phụ thuộc loại queue, độ bền, routing và trạng thái broker. Cần durable queue, persistent message, cơ chế sao chép/lưu trữ broker phù hợp, theo dõi publisher confirms và chiến lược phục hồi. **ACK + không return không có nghĩa message đã được consumer xử lý hoặc vĩnh viễn không thể mất**.

### 8.5. Gửi vào exchange không tồn tại có giống unroutable không?

Không. `basic.publish` tới exchange không tồn tại thường dẫn tới lỗi **`NOT_FOUND`/channel exception**, không phải kịch bản return `NO_ROUTE` từ một exchange hiện hữu. Khi channel/connection đóng, confirm còn chờ có thể không đến bình thường; cần ghi lỗi/unknown riêng, kiểm tra exchange name và vhost.

### 8.6. Returns callback có đủ để đối chiếu concurrent publish không?

Không nên tự đối chiếu bằng một biến trạng thái chung. Khi nhiều message publish đồng thời, callback của các publication khác nhau có thể xen kẽ. Hãy tạo `CorrelationData` **riêng cho mỗi publication**, gắn `messageId`/`eventId` để log return, rồi kiểm tra `getReturned()` trong tương quan của chính event khi confirm hoàn tất.

## 9. Thiết kế trạng thái producer theo kết quả return/confirm

Trong hệ thống thật, producer nên có **state machine** để không ghi nhận giao nhận sai. Một mô hình tối giản:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Tạo event / outbox
    PENDING --> BROKER_ACCEPTED: confirm ACK + returned=null
    PENDING --> UNROUTABLE: confirm ACK + returned!=null
    PENDING --> BROKER_NACK: confirm NACK
    PENDING --> UNKNOWN: timeout / connection lost
    UNROUTABLE --> PENDING: Sửa routing rồi retry có kiểm soát
    BROKER_NACK --> PENDING: Retry có backoff
    UNKNOWN --> PENDING: Đối soát / retry idempotent
    BROKER_ACCEPTED --> [*]: Không đồng nghĩa consumer thành công
~~~

| Trạng thái | Điều kiện ghi nhận | Hành động nên cân nhắc |
|---|---|---|
| `PENDING` | Đã có event cần publish | Gửi với ID ổn định, theo dõi confirm và return |
| `BROKER_ACCEPTED` | Confirm ACK, không có return gắn với publication | Ngừng retry publication, theo dõi tiêu thụ/nghiệp vụ riêng |
| `UNROUTABLE` | Confirm ACK nhưng có returned message | Kiểm tra exchange/binding/routing key/vhost; không coi đã giao |
| `BROKER_NACK` | Broker NACK publication | Retry có giới hạn/backoff, cảnh báo theo mức độ |
| `UNKNOWN` | Lỗi mạng/timeout/chưa nhận đủ thông tin | Không kết luận chưa gửi; đối soát và retry an toàn |

Trạng thái trên **chỉ nói về producer publication**. Hệ thống cần một cơ chế khác để biết **consumer đã hoàn tất nghiệp vụ hay chưa**, chẳng hạn trạng thái database hoặc sự kiện kết quả. Không nên đánh dấu đơn hàng `FULFILLED` ngay khi nhận publisher ACK.

### Outbox và xử lý trùng

Nếu ứng dụng tạo đơn hàng trong DB rồi publish RabbitMQ, hai bước không tự trở thành một transaction nguyên tử. **Transactional outbox** ghi đơn hàng và event vào outbox trong cùng database transaction; một publisher riêng phát event và dùng confirm/return để cập nhật trạng thái outbox.

Nếu publisher timeout sau khi broker đã nhận message, retry có thể tạo **publication thứ hai của cùng một event**. Giữ **`eventId` nghiệp vụ ổn định qua các lần retry**, nhưng tạo đối tượng `CorrelationData` thích hợp cho **mỗi lần publish** để không nhầm phản hồi giữa các attempt. Consumer phải **idempotent** theo event ID/khóa nghiệp vụ để không thực hiện side effect hai lần.

**Không dùng consumer delivery tag làm event ID.** Delivery tag có phạm vi channel nhận và có thể đổi khi requeue/reconnect; nó không đối chiếu được một publication qua nhiều attempt.

### Dead-letter không tự xử lý producer returns

**DLX/DLQ** thường xử lý message **đã vào queue** rồi bị reject, hết TTL, vượt giới hạn hoặc gặp điều kiện dead-letter khác. Publication **unroutable** chưa tới queue nào nên **không tự chạy vào DLQ** chỉ vì đã bật DLX ở một queue.

Với producer returns, hãy sửa/cấu hình lại routing và retry có kiểm soát, hoặc sử dụng một **alternate exchange** được thiết kế để thu nhận unroutable publications nếu đó là yêu cầu hệ thống. Alternate exchange có thể khiến một message thay vì return được định tuyến đến queue dự phòng; cần phân biệt trạng thái “có queue nhận” với “queue nghiệp vụ mong muốn đã nhận”.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Publish key sai nhưng chỉ thấy confirm ACK | Chưa bật `mandatory` hoặc returns, hoặc đang chỉ đọc ACK | Kiểm tra `template.mandatory`, `publisher-returns` và return callback |
| Có dòng `RETURN` và `ACK`, trạng thái vẫn `SENT` | Đang đánh đồng ACK với định tuyến thành công | Kiểm tra `correlation.getReturned()` khi future hoàn tất; đánh dấu `UNROUTABLE` |
| Không thấy return dù queue mong muốn không nhận | Đã route sang queue khác/alternate exchange; khác vhost hoặc binding khác | Kiểm tra **toàn bộ bindings** và alternate exchange |
| Future confirm không hoàn tất | Connection/channel lỗi, pending confirm bị mất, cấu hình factory sai | Kiểm tra logs connection/channel; đặt timeout và trạng thái `UNKNOWN` |
| Callback không được gọi | Sai bean `RabbitTemplate`, không bật correlated confirms/returns, callback bị ghi đè | Đảm bảo cùng factory/template thực tế; cấu hình callback một nơi |
| Message không tới queue và broker đóng channel | Exchange không tồn tại hoặc cấu hình vhost/sai quyền | Xem lỗi `NOT_FOUND`/`ACCESS_REFUSED`; không coi đó là `NO_ROUTE` |
| Return callback xử lý rất chậm | Callback làm I/O nặng hoặc gọi API đồng bộ | Chỉ ghi metadata/đẩy việc sang hàng xử lý riêng; tránh chặn luồng phản hồi |
| Confirm ACK nhưng consumer không hoàn tất | Listener lỗi, bị dừng, backlog, thiếu ACK, hoặc thiếu logic nghiệp vụ | Kiểm tra Ready/Unacked, Consumers, retry/DLQ và log consumer |
| Retry sau timeout tạo sự kiện trùng | Publication đã tới broker nhưng confirm không tới producer | Giữ event ID ổn định, dùng outbox và idempotent consumer |

### Cách log tối thiểu cho một publication

~~~text
eventId, publishAttemptId, exchange, routingKey,
publishTimestamp, mandatory,
returnReceived, returnReplyCode, returnReplyText,
confirmAck, confirmReason, confirmTimestamp,
finalPublishState
~~~

Không log toàn bộ body nếu payload chứa thông tin nhạy cảm. Dùng `publishAttemptId` riêng với `eventId` nếu một event có thể được publish nhiều lần: `eventId` dùng phát hiện xử lý trùng, còn `publishAttemptId` dùng ghép kết quả ACK/NACK/return của **mỗi lần gửi**. Với nhiều thông điệp đồng thời, không tổng hợp kết quả dựa trên thứ tự timestamp đơn thuần.

## 11. Bài tập thực hành

**Bài tập A — Xác nhận thứ tự return rồi confirm.** Bật cấu hình ở mục 5, publish `order.unknown`. Ghi lại `eventId` ở returns callback và confirm future. Vì sao có thể có `confirm.isAck()==true` nhưng trạng thái cuối phải là `UNROUTABLE`?

**Bài tập B — Tắt mandatory.** Trong môi trường lab riêng, tắt `mandatory` nhưng giữ publisher confirms. Gửi lại routing key sai. Đối chiếu có/không return và giải thích vì sao chỉ kiểm tra confirm ACK có thể làm mất message mà producer không biết.

**Bài tập C — Publish đồng thời.** Gửi 100 sự kiện, xen kẽ `order.created` và `order.unknown`, mỗi publication có ID riêng. Xây bảng tổng kết theo `eventId` thay vì đếm dòng log theo thứ tự. Dự đoán: event key đúng không return; key sai return, kể cả khi các callback log xen kẽ.

**Bài tập D — Return callback xử lý chậm.** Trong một môi trường thử nghiệm không có traffic quan trọng, thêm độ trễ nhân tạo ngắn vào returns callback. Quan sát thời điểm future hoàn tất và giải thích vì sao callback không nên block; sau khi thử phải bỏ phần chờ này.

**Bài tập E — Outbox và retry.** Phác thảo bảng `outbox(eventId, publishAttemptId, status, lastError, updatedAt)`. Xác định chuyển trạng thái sau confirm ACK + no return, ACK + return, NACK và timeout. Thiết kế constraint idempotency của consumer cho cùng `eventId` được retry nhiều lần.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Với `mandatory=true`, một message không khớp bất kỳ binding nào của direct exchange tồn tại. Broker có thể gửi những gì theo thứ tự?

**Đáp án:** Broker gửi **`basic.return`** trước, rồi có thể gửi **publisher confirm ACK** cho cùng publication. ACK không phủ định việc message bị return.

**Câu 2.** Khi future `CorrelationData.getFuture()` hoàn tất với `isAck()==true`, vì sao vẫn phải kiểm tra `getReturned()`?

**Đáp án:** Vì publisher confirm ACK chỉ xác nhận publication ở broker; nếu `getReturned()!=null`, publication đó đã không tới queue nào theo routing hiện hành và phải xem là **UNROUTABLE**.

**Câu 3.** Có thể kết luận mọi `RETURN` log phải xuất hiện trước mọi `CONFIRM ACK` log trên toàn ứng dụng không?

**Đáp án:** Không. Thứ tự return trước confirm là cho **cùng một publication unroutable mandatory**. Tín hiệu từ các publication/channel khác nhau có thể xen kẽ.

**Câu 4.** Nếu `mandatory=false`, publisher confirm ACK mà không có return có chứng minh message đã vào queue không?

**Đáp án:** Không. Một message unroutable có thể bị loại âm thầm và vẫn được ACK ở cấp publisher confirm.

**Câu 5.** Nếu exchange không tồn tại, có nên chờ `basic.return(312 NO_ROUTE)` như khi key sai không?

**Đáp án:** Không. Exchange không tồn tại thường gây channel exception; đây là lỗi topology khác với một exchange tồn tại nhưng không có binding phù hợp.

**Câu 6.** Tại sao DLQ của consumer không tự nhận một publication đã bị publisher return?

**Đáp án:** Vì message chưa được exchange định tuyến vào queue nguồn; DLX/DLQ thường áp dụng sau khi message đã vào queue và có điều kiện dead-letter. Muốn lưu unroutable publication cần thiết kế xử lý return/alternate exchange riêng.

**Câu 7.** Timeout confirm có đồng nghĩa broker chắc chắn chưa nhận message không?

**Đáp án:** Không. Có thể broker đã xử lý publication nhưng phản hồi bị thất lạc. Trạng thái phù hợp là **UNKNOWN**; khi retry phải giữ event ID và xử lý idempotency.

## 13. Ghi nhớ

- **Với unroutable mandatory publication, `basic.return` được gửi trước publisher confirm** của cùng publication. Broker vẫn có thể **ACK**, dù không có queue nào nhận message.
- **`CorrelationData.getReturned()` được Spring AMQP điền trước khi future confirm tương ứng hoàn tất** trong luồng correlated returns/confirms. Dùng **ACK/NACK + returned** của **chính publication** để quyết định, không suy từ thứ tự các dòng log.
- **ACK + returned = UNROUTABLE**; **ACK + không returned** mới là publication được broker xác nhận và không bị return theo topology/cấu hình hiện tại, **không đồng nghĩa consumer xử lý xong**.
- **Publisher returns, publisher confirms, consumer ACK và kết quả nghiệp vụ là các tín hiệu khác nhau**. Sự tin cậy cần thêm binding chính xác, timeout/UNKNOWN, retry có giới hạn, DLQ, idempotency, transactional outbox và quan sát hệ thống.
