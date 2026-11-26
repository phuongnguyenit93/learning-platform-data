# Message TTL theo queue và theo từng thông điệp

Một hệ thống đặt hàng dùng RabbitMQ có thể nhận hàng nghìn yêu cầu trong vài phút. Nhưng một số yêu cầu chỉ còn giá trị trong một khoảng thời gian nhất định: mã xác thực chỉ hợp lệ 30 giây, yêu cầu báo giá hết giá trị sau 2 phút, hoặc tác vụ dự phòng không nên tiếp tục sau 10 phút chờ đợi. **Message Time-To-Live (TTL)** giúp broker giới hạn thời gian một message được phép **chờ trong queue** trước khi bị coi là hết hạn.

Trong **Spring AMQP**, bạn có thể đặt TTL **cho mọi message của một queue** thông qua `x-message-ttl` hoặc một **RabbitMQ policy**, và có thể đặt TTL **riêng cho một message** bằng thuộc tính AMQP `expiration` khi gửi bằng `RabbitTemplate`. Bài học thuộc chương **Chính sách hàng đợi** của module **SPRING_AMQP**, sử dụng exchange, queue, binding và `@RabbitListener` để thực hành. Chúng ta cũng sẽ theo dõi message hết hạn, dead-letter, acknowledgment, retry và khả năng quan sát để tránh nhầm TTL với một cơ chế hẹn giờ hoặc bảo đảm xử lý thành công.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt TTL **theo queue** và **theo từng message**, nêu đúng đơn vị và vị trí cấu hình.
2. Giải thích điều gì xảy ra khi hai loại TTL cùng áp dụng, khi không có consumer, khi message đã được giao nhưng chưa ack.
3. Thiết lập `x-message-ttl` bằng `QueueBuilder` hoặc policy của RabbitMQ; đặt `expiration` qua `RabbitTemplate`.
4. Khai báo dead-letter exchange (DLX) và queue để quan sát một message hết hạn.
5. Thực hành kiểm tra bằng RabbitMQ Management và phân tích các tình huống message không xuất hiện đúng thời điểm.
6. Chọn TTL hợp lý trong hệ thống bất đồng bộ, hiểu ảnh hưởng của retry, giao dịch và idempotency.

## 2. TTL giới hạn tuổi của message đang chờ

Một message đi qua luồng cơ bản:

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] -->|"publish"| X["Exchange<br/>orders.ttl.events"]
    X -->|"binding"| Q["Queue<br/>orders.ttl.work"]
    Q -->|"chưa hết hạn"| C["Consumer<br/>@RabbitListener"]
    Q -->|"hết hạn; có cấu hình DLX"| DX["Dead-letter exchange<br/>orders.ttl.dlx"]
    DX --> DQ["Dead-letter queue<br/>orders.ttl.expired"]
~~~

**TTL áp dụng khi message còn nằm trong queue, chờ được giao cho consumer.** Nếu message hết hạn trước khi được giao, broker sẽ loại nó khỏi queue nguồn khi xử lý trạng thái hết hạn; nếu queue có cấu hình dead-letter phù hợp, message có thể được chuyển tới DLX, từ đó vào một queue khác. Nếu không có đích dead-letter thích hợp, message có thể bị loại bỏ.

TTL không tự động thu hồi một message **đã được giao cho consumer và đang chờ ack**. Listener xử lý quá lâu vẫn phải quản lý timeout, hủy tác vụ, kiểm tra hạn nghiệp vụ và acknowledgment riêng. TTL cũng không tự đảm bảo một tác vụ được xử lý đúng trong khoảng hạn mong muốn.

Một điểm quan trọng khác: **message hết hạn không nhất thiết biến mất chính xác ở mili giây hết hạn**. Broker có thể kiểm tra và loại message trong những thời điểm nhất định. Với TTL riêng từng message, message đã hết hạn đôi khi còn ở phía sau các message chưa hết hạn trong queue và chỉ được loại khi đến lượt kiểm tra phù hợp. Vì vậy, TTL phù hợp để **giới hạn thời gian sống**, không phải dịch vụ hẹn giờ có độ chính xác tuyệt đối.

## 3. Hai loại Message TTL

### 3.1. TTL theo queue: `x-message-ttl`

Đây là thời gian chờ tối đa áp dụng **cho từng message trong queue**. Ví dụ queue có `x-message-ttl=10000` nghĩa là mỗi message trong queue có TTL **10.000 mili giây = 10 giây**, tính theo thời gian nó ở queue đó.

~~~yaml
# Minh họa queue argument (x-argument)
x-message-ttl: 10000
~~~

Tên gọi “TTL theo queue” **không có nghĩa queue bị xóa sau 10 giây**: chỉ các **message đang chờ** trong queue chịu giới hạn này. Queue có thể tiếp tục tồn tại và tiếp nhận message mới.

Bạn có thể khai báo bằng mã:

~~~java
QueueBuilder.durable("orders.ttl.work")
        .ttl(10_000)
        .build();
~~~

Hoặc dùng **RabbitMQ policy** để cấu hình TTL linh hoạt hơn:

~~~json
{
  "message-ttl": 10000
}
~~~

**Tên khóa khác nhau:** Queue argument là `x-message-ttl`; trong **định nghĩa policy** là `message-ttl`. Giá trị là một **số nguyên không âm**, tính theo **mili giây**. Trong ứng dụng thực tế, ưu tiên policy cho các tham số cần thay đổi khi vận hành, bởi thay đổi `x-arguments` cố định của queue đã tồn tại có thể đòi hỏi triển khai/migration queue phù hợp.

### 3.2. TTL theo từng message: thuộc tính `expiration`

Producer có thể đặt hạn riêng lúc publish. Trong Spring AMQP:

~~~java
rabbitTemplate.convertAndSend(
        "orders.ttl.events",
        "orders.created",
        "ORD-1001",
        message -> {
            message.getMessageProperties().setExpiration("3000");
            return message;
        });
~~~

`setExpiration("3000")` thiết lập thuộc tính AMQP `expiration` là **chuỗi biểu diễn số mili giây**, tương ứng 3 giây. Lưu ý phân biệt:

- **TTL queue:** giá trị số nguyên tại `x-message-ttl` hoặc policy `message-ttl`.
- **TTL message:** giá trị chuỗi thập phân của thuộc tính AMQP `expiration`, chẳng hạn `"3000"`.

Đây là thuộc tính **message properties**, không phải một field `expiration` trong JSON body và cũng không phải một header thông thường để định tuyến qua `HeadersExchange`.

### 3.3. Nếu áp dụng cả hai, giới hạn nào có hiệu lực?

Khi một message vừa có `expiration` vừa nằm trong queue áp dụng `x-message-ttl`/policy, **giới hạn ngắn hơn sẽ quyết định hạn hết hiệu lực trong queue**.

Giả sử queue quy định 10 giây:

| TTL queue | TTL riêng của message | Hạn hiệu lực dự kiến khi chờ trong queue | Giải thích |
|---:|---:|---:|---|
| 10 giây | Không đặt | 10 giây | Chỉ áp dụng TTL queue |
| 10 giây | 3 giây | 3 giây | TTL message ngắn hơn |
| 10 giây | 20 giây | 10 giây | TTL queue ngắn hơn |
| 10 giây | 10 giây | 10 giây | Hai giới hạn bằng nhau |
| Không đặt | 3 giây | 3 giây | Chỉ áp dụng TTL message |
| Không đặt | Không đặt | Không có TTL từ hai cấu hình này | Có thể còn giới hạn/chính sách khác |

Các mốc trên mô tả **điều kiện hết hạn**, không bảo đảm chính xác thời điểm message được chuyển sang DLQ. Khi consumer nhận trước thời điểm hết hạn, luồng tiêu thụ và ack tiếp tục theo chế độ của consumer.

### 3.4. Một message được định tuyến tới nhiều queue

Giả sử cùng một message được exchange gửi vào **Queue A** (TTL 5 giây) và **Queue B** (TTL 60 giây). Mỗi queue quản lý bản sao của message và giới hạn chờ **theo queue của mình**. Message có thể đã hết hạn ở A nhưng vẫn chờ hoặc đã được xử lý ở B. TTL không phải một bộ đếm toàn cục điều khiển mọi bản sao trên các queue.

## 4. Đừng nhầm Message TTL với Queue TTL

RabbitMQ còn có tham số `x-expires` cho **tuổi của queue khi không được sử dụng**, khác hoàn toàn `x-message-ttl`:

| Thuộc tính | Đối tượng chịu tác động | Hành vi |
|---|---|---|
| `x-message-ttl` / policy `message-ttl` | **Message trong queue** | Message chờ quá lâu được đánh dấu hết hạn và loại khỏi queue; có thể dead-letter |
| `expiration` của message | **Một message cụ thể** | Giới hạn thời gian chờ riêng cho message đó |
| `x-expires` / policy `expires` | **Bản thân queue** | Queue đủ điều kiện bị xóa sau khoảng thời gian không được sử dụng theo quy tắc broker |

Ví dụ `x-message-ttl=30000` không làm queue bị xóa sau 30 giây, và `x-expires=30000` không phải cơ chế đặt TTL 30 giây cho từng message. Khi queue bị xóa, message còn trong queue có thể mất cùng queue; cần hiểu tác động này trước khi cấu hình trong môi trường thực.

## 5. Ví dụ Spring AMQP: hết hạn rồi chuyển sang dead-letter

Chúng ta tạo một queue công việc có TTL **10 giây** và một queue riêng để tiếp nhận các message hết hạn. Khi công việc chưa có consumer, bạn sẽ thấy message chờ trong queue chính, sau đó chuyển qua DLX khi hết hạn.

### 5.1. Chuẩn bị kết nối RabbitMQ

Ứng dụng Spring Boot cần hai dependency; ví dụ Maven với phiên bản do Spring Boot dependency management quản lý:

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

Nếu bạn chưa có RabbitMQ, có thể dùng container cho môi trường học tập:

~~~bash
docker run -d --name rabbitmq-ttl-lab -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -e RABBITMQ_DEFAULT_USER=lab -e RABBITMQ_DEFAULT_PASS=lab123456 rabbitmq:4-management
~~~

Truy cập RabbitMQ Management tại `http://localhost:15672`; tài khoản minh họa là `lab` / `lab123456`. Nếu đã có broker trên các cổng này, sử dụng broker có sẵn hoặc đổi cổng ánh xạ. Trong triển khai thực tế, không dùng mật khẩu mẫu và không công khai Management ra Internet.

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
    listener:
      simple:
        acknowledge-mode: auto
~~~

### 5.2. Khai báo exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TtlTopologyConfig {
    @Bean
    DirectExchange workExchange() {
        return new DirectExchange("orders.ttl.events", true, false);
    }

    @Bean
    DirectExchange deadLetterExchange() {
        return new DirectExchange("orders.ttl.dlx", true, false);
    }

    @Bean
    Queue workQueue() {
        return QueueBuilder.durable("orders.ttl.work")
                .ttl(10_000)
                .deadLetterExchange("orders.ttl.dlx")
                .deadLetterRoutingKey("orders.expired")
                .build();
    }

    @Bean
    Queue expiredQueue() {
        return QueueBuilder.durable("orders.ttl.expired").build();
    }

    @Bean
    Binding workBinding(Queue workQueue, DirectExchange workExchange) {
        return BindingBuilder.bind(workQueue)
                .to(workExchange)
                .with("orders.created");
    }

    @Bean
    Binding expiredBinding(Queue expiredQueue,
                           DirectExchange deadLetterExchange) {
        return BindingBuilder.bind(expiredQueue)
                .to(deadLetterExchange)
                .with("orders.expired");
    }
}
~~~

Khi ứng dụng khai báo các tài nguyên lên RabbitMQ, queue `orders.ttl.work` có các arguments tương đương:

~~~yaml
x-message-ttl: 10000
x-dead-letter-exchange: orders.ttl.dlx
x-dead-letter-routing-key: orders.expired
~~~

Luồng hoạt động:

1. Producer publish vào `orders.ttl.events` với routing key `orders.created`.
2. Exchange đưa message vào `orders.ttl.work`.
3. Nếu message **chưa được consumer nhận** trước hạn, broker xử lý message hết hạn.
4. Broker chuyển message từ queue nguồn sang `orders.ttl.dlx` với routing key `orders.expired`.
5. DLX định tuyến vào `orders.ttl.expired`, nơi bạn có thể quan sát hoặc xử lý lỗi/hết hạn.

Queue `orders.ttl.expired` trong ví dụ **không có TTL riêng** để dễ quan sát. Nếu không có DLX/binding phù hợp, message hết hạn có thể bị loại mà không xuất hiện trong queue nào. Dead-letter là một cơ chế riêng; message không tự nhảy sang DLQ chỉ vì queue được đặt TTL.

**Trong hệ thống thực tế:** có thể quản lý TTL và DLX bằng **RabbitMQ policies** để thay đổi cấu hình dễ hơn. Phần mã trên dùng queue arguments cố định nhằm cho thấy trực tiếp cơ chế hoạt động.

### 5.3. Gửi message với TTL riêng bằng `RabbitTemplate`

Tạo endpoint HTTP để chủ động phát message. Trường `ttlMs` là tùy chọn; không truyền nghĩa là message chỉ chịu TTL của queue.

~~~java
import java.util.UUID;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/lab/ttl")
public class TtlPublishController {
    private final RabbitTemplate rabbitTemplate;

    public TtlPublishController(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @PostMapping("/send")
    public ResponseEntity<String> send(
            @RequestParam String orderId,
            @RequestParam(required = false) Integer ttlMs) {
        if (ttlMs != null && ttlMs < 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "ttlMs must be non-negative");
        }

        rabbitTemplate.convertAndSend(
                "orders.ttl.events",
                "orders.created",
                orderId,
                message -> {
                    if (ttlMs != null) {
                        message.getMessageProperties()
                                .setExpiration(Integer.toString(ttlMs));
                    }
                    message.getMessageProperties()
                            .setHeader("eventId", UUID.randomUUID().toString());
                    return message;
                });

        return ResponseEntity.accepted()
                .body("Da yeu cau publish don " + orderId);
    }
}
~~~

HTTP `202 Accepted` trong demo chỉ phản ánh rằng ứng dụng đã gọi API publish và không gặp exception ngay tại thời điểm trả lời; nó **không chứng minh message đã vào queue hoặc đã được consumer xử lý**. Muốn biết broker đã chấp nhận publication, cần dùng publisher confirms; muốn biết không có queue nhận, cân nhắc mandatory và publisher returns.

### 5.4. Listener để đọc message đã hết hạn

Trong lần quan sát đầu tiên, hãy **để queue công việc không có listener**. Có thể thêm listener cho queue dead-letter nhưng tạm tắt tự khởi động để còn thấy message trong RabbitMQ Management:

~~~java
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ExpiredOrderListener {
    private static final Logger log =
            LoggerFactory.getLogger(ExpiredOrderListener.class);

    @RabbitListener(
            id = "expiredOrdersListener",
            queues = "orders.ttl.expired",
            autoStartup = "false")
    public void onExpired(Message message) {
        String body = new String(
                message.getBody(), StandardCharsets.UTF_8);
        log.info("EXPIRED order={}, headers={}",
                body, message.getMessageProperties().getHeaders());
    }
}
~~~

Khi muốn thử consumer, đổi `autoStartup` thành `"true"` rồi khởi động lại ứng dụng; khi đó message còn ở DLQ sẽ được listener nhận. Trong ứng dụng thực tế, listener DLQ cần có xử lý hợp lý và idempotency; **không nên tự động tái publish vô hạn** từ DLQ về queue chính.

## 6. Thực hành với ba message có TTL khác nhau

Khởi động broker, ứng dụng và mở Management. Kiểm tra:

- **Exchanges** có `orders.ttl.events` và `orders.ttl.dlx`.
- **Queues and Streams** (hoặc **Queues**) có `orders.ttl.work` và `orders.ttl.expired`.
- Queue công việc có `x-message-ttl=10000` và DLX arguments chính xác.
- **Consumers = 0** cho `orders.ttl.work`; listener expired cũng chưa chạy.

Dùng terminal (trên Windows PowerShell có thể chọn `curl.exe` thay vì alias `curl`) gửi lần lượt:

~~~bash
curl -X POST "http://localhost:8080/lab/ttl/send?orderId=ORD-3S&ttlMs=3000"
curl -X POST "http://localhost:8080/lab/ttl/send?orderId=ORD-20S&ttlMs=20000"
curl -X POST "http://localhost:8080/lab/ttl/send?orderId=ORD-DEFAULT"
~~~

Trong điều kiện phòng lab không có message khác:

| Message | TTL queue | TTL riêng | Hạn tối đa khi chờ | Dự kiến |
|---|---:|---:|---:|---|
| `ORD-3S` | 10 giây | 3 giây | 3 giây | Hết hạn trước, chuyển đến DLX |
| `ORD-20S` | 10 giây | 20 giây | 10 giây | Queue TTL quyết định |
| `ORD-DEFAULT` | 10 giây | Không đặt | 10 giây | Queue TTL quyết định |

Quan sát các cột **Ready / Unacked / Total** của queue công việc; về sau kiểm tra queue `orders.ttl.expired`. Các message hết hạn có thể chuyển sang DLQ và làm **Ready** của DLQ tăng. Vì Management cập nhật số liệu theo chu kỳ và RabbitMQ không hứa hẹn dead-letter chính xác tại mili giây TTL, các số đếm chỉ mang tính **quan sát tại thời điểm lấy mẫu**.

Một cách ghi kết quả:

| Mốc quan sát | Queue `orders.ttl.work` | Queue `orders.ttl.expired` |
|---|---|---|
| Ngay sau khi gửi | Có các message đang chờ | Thường còn trống |
| Sau khoảng 3 giây | `ORD-3S` đủ điều kiện hết hạn | Có thể nhận `ORD-3S` sau khi broker xử lý |
| Sau khoảng 10 giây | Hai message còn lại cũng đủ điều kiện hết hạn | Có thể nhận thêm `ORD-20S` và `ORD-DEFAULT` |

**Không kết luận chỉ từ thời điểm chụp màn hình.** Khi cần xác thực một message cụ thể, dùng metadata như `eventId`, log của consumer và thông tin dead-letter. Nếu cần xem nội dung message từ UI, đọc kỹ chế độ ack/requeue của thao tác **Get messages**, vì thao tác đó có thể thay đổi trạng thái queue.

### Thử khi có consumer đang hoạt động

Nếu thêm `@RabbitListener(queues = "orders.ttl.work")` và consumer nhận message trước khi TTL hết, message được giao để xử lý bình thường; **TTL không tự giết listener sau 3 hoặc 10 giây**. Message đang ở trạng thái **Unacked** cần được quản lý bằng ack, giới hạn thời gian xử lý và logic nghiệp vụ. Nếu message được ack thành công, nó sẽ biến mất khỏi queue và không được dead-letter chỉ vì TTL ban đầu đã trôi qua trong lúc xử lý.

## 7. Dùng RabbitMQ policy để cấu hình TTL theo queue

**Policy** là cách vận hành phù hợp khi muốn áp dụng hoặc điều chỉnh TTL theo mẫu tên queue mà không viết cứng thông số vào mã ứng dụng. Trong RabbitMQ Management, vào khu vực **Admin → Policies** (nhãn giao diện có thể thay đổi theo phiên bản) rồi tạo policy:

| Trường | Giá trị minh họa |
|---|---|
| Name | `ttl-work-10s` |
| Pattern | `^orders\.ttl\.work$` |
| Apply to | Queues |
| Definition | `{"message-ttl":10000}` |

Hoặc trên máy có CLI RabbitMQ và quyền phù hợp, cú pháp lệnh về mặt ý nghĩa là:

~~~bash
rabbitmqctl set_policy ttl-work-10s '^orders\.ttl\.work$' '{"message-ttl":10000}' --apply-to queues
~~~

Lệnh dùng trích dẫn theo shell kiểu Unix; PowerShell/CMD có cách chuyển dấu nháy JSON khác nhau. Trên môi trường Windows, dùng giao diện Management nếu không muốn xử lý escaping của CLI.

**Rất quan trọng khi thử phương án policy:** trong phần mã `workQueue()` của mục 5.2 đã có `.ttl(10_000)`, tức queue được khai báo `x-message-ttl` ở phía client. Policy thông thường **không ghi đè một giá trị x-argument do client đã đặt**. Để thử policy theo đúng ý nghĩa, dùng **queue không khai báo `.ttl(...)`**:

~~~java
@Bean
Queue workQueue() {
    return QueueBuilder.durable("orders.ttl.work")
            .deadLetterExchange("orders.ttl.dlx")
            .deadLetterRoutingKey("orders.expired")
            .build(); // TTL do policy quản lý.
}
~~~

Nếu queue đã được broker khai báo với `x-message-ttl` cố định, không thể đơn giản đổi khai báo bất tương thích rồi khởi động lại để “sửa” queue tại chỗ: RabbitMQ có thể từ chối khai báo lại khi arguments xung đột. Trong lab sạch, có thể dùng **tên queue mới** để thử chính sách. Trong môi trường có dữ liệu thật, lập kế hoạch migration phù hợp trước khi thay đổi hoặc xóa queue.

Policy cũng có thể quản lý dead-letter, ví dụ thêm khóa `dead-letter-exchange` và `dead-letter-routing-key` vào definition. Hãy thống nhất một nơi chịu trách nhiệm cấu hình để tránh nhầm precedence giữa policy và application arguments. **Operator policies** của RabbitMQ có thể áp giới hạn riêng; nếu có, kiểm tra effective policy và quyền vận hành trước khi kết luận cấu hình nào thực sự có hiệu lực.

## 8. Khi TTL hết hạn: drop hay dead-letter?

TTL cho biết **khi nào một message không còn hợp lệ trong queue**, còn DLX quyết định **message đi đâu sau đó** nếu có cấu hình:

~~~mermaid
flowchart TD
    A["Message chờ trong queue"] --> B{"Message đã đủ điều kiện hết hạn?"}
    B -->|"Chưa"| C["Tiếp tục chờ hoặc được consumer nhận"]
    B -->|"Rồi"| D{"Queue có DLX phù hợp?"}
    D -->|"Có"| E["Dead-letter tới DLX"]
    E --> F["Định tuyến vào DLQ nếu có binding phù hợp"]
    D -->|"Không"| G["Message bị loại"]
~~~

Một vài điểm cần kiểm tra khi không tìm thấy message:

- Queue nguồn có cấu hình `x-dead-letter-exchange`/policy dead-letter hay chưa?
- DLX có tồn tại, đúng vhost, đúng loại exchange và có binding phù hợp với routing key dead-letter?
- Message có đang bị consumer nhận và **Unacked** thay vì còn chờ để hết TTL?
- Message còn nằm sau các message khác và broker chưa loại nó khỏi queue tại thời điểm bạn quan sát?
- Queue DLQ có đang có consumer lấy message nhanh nên số **Ready** luôn nhỏ hoặc bằng 0?
- Policy có áp dụng cho đúng tên queue, hay x-arguments hiện hữu đang được ưu tiên?

Message dead-letter thường có metadata về lịch sử dead-letter, ví dụ header `x-death`; các trường cụ thể cần kiểm tra theo phiên bản và tình huống. Log ứng dụng nên có `eventId`, tên queue, lý do xử lý thất bại và correlation ID để ghép vòng đời message, thay vì chỉ đo bằng số lượng queue.

## 9. Những giới hạn kỹ thuật cần hiểu trước khi dùng TTL

### 9.1. TTL không phải bộ hẹn giờ chính xác

Nếu đặt TTL 5 giây, **đừng thiết kế nghiệp vụ bắt buộc chạy đúng thời điểm 5,000 giây**. Việc loại message, chuyển DLX, scheduler của broker, backlog, publisher/consumer và chính sách queue đều có thể tạo sai lệch. Đặc biệt, TTL riêng từng message có thể gây tình huống **message hết hạn ở phía sau một message chưa hết hạn** và chưa được loại ngay. Việc dùng một queue với nhiều hạn khác nhau làm công cụ lập lịch có thể tạo độ trễ khó dự đoán.

Nếu bài toán cần lập lịch chính xác, hẹn giờ ở quy mô lớn hoặc thứ tự theo deadline, nên cân nhắc hệ thống scheduler, cơ chế trì hoãn chuyên dụng hoặc thiết kế queue phù hợp thay vì chỉ dựa vào TTL + DLX.

### 9.2. TTL không thay cho hạn nghiệp vụ trong consumer

Một message còn hợp lệ khi được giao có thể đã quá hạn nghiệp vụ lúc consumer bắt đầu một thao tác bên ngoài lâu dài. Nếu yêu cầu đơn hàng không được xử lý sau thời điểm `expiresAt`, hãy **đặt deadline trong payload** và kiểm tra ở consumer trước khi tạo hiệu ứng nghiệp vụ. Khi cần, kiểm tra lại deadline quanh thao tác quan trọng theo khả năng nhất quán của hệ thống.

### 9.3. TTL không tạo giao dịch nguyên tử

Nếu `Order Service` lưu database thành công nhưng publish message thất bại, TTL không giải quyết việc bỏ sót event. Gửi message thành công rồi lỗi giao dịch database cũng gây lệch dữ liệu. Một mô hình phổ biến là **transactional outbox**: ghi nghiệp vụ và event ra outbox trong cùng transaction, sau đó một tiến trình publish và retry phù hợp.

### 9.4. TTL và retry cần chính sách rõ ràng

Một số hệ thống triển khai retry bằng queue có TTL rồi dead-letter message về queue làm việc. Thiết kế đó cần **giới hạn số lần retry**, metadata đếm lượt, cảnh báo khi bị lặp và DLQ cuối để điều tra message lỗi cố định. Một chu kỳ dead-letter/TTL không được kiểm soát có thể gây vòng lặp và làm đầy broker. Message đã hết hạn ở queue công việc không đồng nghĩa **lỗi retry sẽ tự được xử lý**.

### 9.5. TTL không bảo đảm giao đúng một lần

Consumer có thể cập nhật database rồi mất kết nối trước khi ack, khiến message được giao lại. **Idempotency** dựa trên `eventId` hoặc khóa nghiệp vụ vẫn cần thiết. Publisher confirms, consumer acknowledgment, DLQ và TTL là các phần khác nhau của thiết kế xử lý tin cậy.

## 10. Gợi ý chọn cách đặt TTL

| Nhu cầu | Cấu hình nên cân nhắc | Lý do |
|---|---|---|
| Mọi message trong một queue không nên chờ quá 10 giây | Queue `x-message-ttl` hoặc policy `message-ttl` | Giới hạn thống nhất cho queue |
| Mỗi đơn hàng có thời gian chờ khác nhau | Message `expiration` | Producer đặt hạn riêng từng message |
| Queue quy định tối đa 10 giây nhưng một số message cần chỉ 3 giây | Kết hợp TTL queue + TTL message | Hạn ngắn hơn áp dụng |
| Muốn thay TTL theo môi trường hoặc khi vận hành | RabbitMQ policy | Có thể điều chỉnh tập trung với queue được thiết kế dùng policy |
| Cần biết message hết hạn để điều tra | TTL + DLX/DLQ + log | Có đường xử lý riêng cho message không còn hợp lệ |
| Cần thực hiện công việc đúng giờ hoặc kiểm soát deadline nghiệp vụ | Scheduler / kiểm tra `expiresAt` ở ứng dụng | TTL queue không có độ chính xác hoặc tính đảm bảo nghiệp vụ như timer |

**Đánh giá lựa chọn theo nghiệp vụ:** nếu message chỉ là thông báo có thể bỏ khi cũ, TTL có thể giúp kiểm soát backlog. Nếu message là lệnh chuyển tiền hoặc thay đổi trạng thái quan trọng, cần thiết kế trạng thái, xác nhận, retry và xử lý lỗi riêng; không nên để TTL lặng lẽ xóa công việc bắt buộc mà không có quy trình kiểm soát.

## 11. Thực hành và tự kiểm tra

### Bài thực hành A — TTL queue và TTL riêng

Giữ queue có TTL 10 giây, không chạy consumer trên queue nguồn. Publish ba message với `expiration` lần lượt là `3000`, `20000` và không đặt. Trước khi chạy, dự đoán message nào đủ điều kiện hết hạn sớm nhất. Sau đó quan sát `orders.ttl.work` và `orders.ttl.expired`, ghi thời gian thực tế, và giải thích sự khác biệt giữa dự đoán theo TTL với thời điểm broker thực hiện dead-letter.

### Bài thực hành B — TTL theo policy

Tạo queue demo mới **không hardcode `x-message-ttl`** (chẳng hạn `orders.ttl.policy-lab`) và policy chỉ khớp queue đó. Đặt `message-ttl=5000`, gửi message, rồi đổi policy thành `15000` và gửi message mới. Ghi lại trạng thái và giải thích tại sao nên dùng policy cho những tham số cần cập nhật khi vận hành.

### Bài thực hành C — Consumer chậm

Thêm một listener cố tình xử lý 15 giây (chỉ để làm thí nghiệm), trong khi message được đặt TTL 3 giây. Đảm bảo listener nhận message **trước** thời điểm hết hạn. Quan sát trạng thái **Unacked** và chứng minh TTL không tự ngắt mã đang xử lý. Sau đó bỏ cơ chế làm chậm giả lập và xây kiểm tra deadline nghiệp vụ.

### Câu hỏi kiểm tra nhanh

**Câu 1.** Queue có `x-message-ttl=10000`, message có `expiration="2500"`. Giới hạn chờ nào có hiệu lực?

**Đáp án:** 2.500 ms (2,5 giây) vì đây là giới hạn ngắn hơn. Thời điểm broker thực tế loại/chuyển message có thể không trùng tuyệt đối mốc đó.

**Câu 2.** Queue có `x-message-ttl=10000`, một message không đặt `expiration`. Message có tự hết hạn sau 10 giây dù không có consumer?

**Đáp án:** có, message đủ điều kiện hết hạn sau khoảng 10 giây chờ trong queue. Nếu cấu hình DLX/binding phù hợp, nó có thể chuyển vào DLQ; nếu không, có thể bị loại bỏ.

**Câu 3.** `x-expires=30000` có nghĩa message chỉ được chờ 30 giây?

**Đáp án:** không. `x-expires` liên quan đến tuổi của **queue không được sử dụng**, không phải TTL của từng message.

**Câu 4.** Một listener đã nhận message lúc giây thứ nhất, xử lý 20 giây và sau đó ack. TTL 3 giây của message có tự cắt listener ở giây thứ ba không?

**Đáp án:** không. TTL giới hạn thời gian **chờ được giao trong queue**. Thời gian xử lý sau khi giao cần được quản lý ở consumer.

**Câu 5.** Message hết hạn nhưng không thấy trong DLQ: kiểm tra điều gì?

**Đáp án:** cấu hình DLX của queue nguồn, exchange/binding/routing key/vhost đích, consumer của DLQ, trạng thái Ready/Unacked và sự chậm trễ khi broker dọn message hết hạn.

## 12. Ghi nhớ

- **TTL theo queue:** dùng `x-message-ttl` hoặc policy `message-ttl` với số **mili giây**; mỗi message chờ trong queue chịu giới hạn này.
- **TTL theo message:** đặt thuộc tính `expiration`, trong Spring AMQP qua `MessageProperties.setExpiration("3000")`; giá trị là **chuỗi số mili giây**.
- **Khi có cả hai, giới hạn ngắn hơn áp dụng**. Message đã giao cho consumer không tự bị TTL hủy trong lúc listener đang xử lý.
- **Dead-letter cần được cấu hình riêng**. Management, log và metrics giúp quan sát; TTL không phải scheduler chính xác, và không thay cho ack, retry/DLQ, idempotency hay giao dịch nhất quán.
