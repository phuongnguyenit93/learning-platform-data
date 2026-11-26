# Gửi thất bại trước khi kết nối, khi channel đóng hoặc khi broker từ chối

## 1. Vì sao một lời gọi gửi message không đủ chứng minh đã gửi thành công?

Với **Spring AMQP** và RabbitMQ, ứng dụng thường gọi `RabbitTemplate.convertAndSend(...)` để phát thông điệp, RabbitMQ dùng **exchange**, **routing key** và **binding** để định tuyến vào **queue**, rồi `@RabbitListener` xử lý bất đồng bộ.

Tuy nhiên, “gọi hàm gửi không ném exception” **không đồng nghĩa** “message đã vào đúng queue” hoặc “consumer đã xử lý xong”. Một lệnh publish có thể gặp lỗi ở nhiều thời điểm:

1. **Trước khi có connection dùng được:** không thể thiết lập TCP/AMQP connection hoặc không mượn được connection/channel.
2. **Khi channel đóng hoặc trở nên không hợp lệ:** broker đóng channel vì lỗi giao thức, sai exchange, sai quyền hoặc connection rớt trong lúc gửi.
3. **Khi broker không chấp nhận publish:** RabbitMQ gửi **publisher confirm NACK** cho một lần publish; đây không phải lỗi converter hay consumer ACK.
4. **Khi broker chấp nhận publish nhưng không định tuyến được:** message không có queue đích; với `mandatory=true`, RabbitMQ gửi **basic.return**. Publisher confirm vẫn có thể là **ACK**.
5. **Khi gửi có thể đã thành công nhưng mất kết nối trước khi nhận confirm:** ứng dụng ở trạng thái **chưa xác định** (*unknown outcome*). Retry mù có thể tạo bản sao thông điệp.

Mục tiêu của bài thuộc chương **Gửi thông điệp** là phân biệt chính xác những tình huống này, chọn tín hiệu quan sát phù hợp và xây quy trình gửi đáng tin cậy bằng **`RabbitTemplate`**, publisher confirms/returns, retry có kiểm soát, transactional outbox và consumer idempotent.

Các ví dụ sử dụng **RabbitMQ AMQP 0-9-1** và các API quen thuộc của Spring AMQP: `RabbitTemplate`, `CachingConnectionFactory`, `RabbitAdmin` và `@RabbitListener`. Không suy diễn các API xác nhận này áp dụng nguyên xi cho client AMQP 1.0.

## 2. Luồng gửi và các điểm có thể thất bại

~~~mermaid
flowchart TD
    A["Ứng dụng tạo event có eventId"]
    B{"Lấy connection/channel được?"}
    C["RabbitTemplate publish vào exchange"]
    D{"Broker chấp nhận publish?"}
    E{"Exchange định tuyến đến queue?"}
    F["Message vào queue"]
    G["Consumer nhận và xử lý"]
    H["Consumer ACK"]
    L1["Lỗi kết nối/checkout channel"]
    L2["Channel/connection bị đóng"]
    L3["Publisher confirm NACK"]
    L4["Unroutable: basic.return nếu mandatory"]
    U["Không nhận được confirm:<br/>outcome chưa rõ"]
    A --> B
    B -- "Không" --> L1
    B -- "Có" --> C
    C -. "Connection/channel mất" .-> L2
    C --> D
    D -- "NACK" --> L3
    D -- "Không rõ do mất confirm" --> U
    D -- "ACK" --> E
    E -- "Có queue đích" --> F --> G --> H
    E -- "Không có" --> L4
~~~

Sơ đồ thể hiện **các câu hỏi logic**, không phải cam kết thứ tự chính xác của từng frame AMQP. Ở AMQP 0-9-1, việc publish qua network và việc nhận confirm/return có thể diễn ra **bất đồng bộ**. Đặc biệt, một lần publish unroutable có thể phát sinh **basic.return trước khi confirm ACK**; lỗi channel cũng có thể được phát hiện sau khi lời gọi `convertAndSend` đã trả về.

### Ba tín hiệu không được đánh đồng

| Tín hiệu | Ai phát ra? | Cho biết điều gì? | Không bảo đảm điều gì? |
| --- | --- | --- | --- |
| **Exception khi gọi `convertAndSend`** | Spring/client Java | Lệnh gửi hoặc việc lấy connection/channel gặp lỗi ở phía client hoặc khi xử lý phản hồi lỗi. | Không luôn chứng minh broker chưa nhận message, nếu lỗi xảy ra sau khi bytes có thể đã được gửi. |
| **Publisher confirm ACK/NACK** | RabbitMQ → publisher | Broker xác nhận hoặc từ chối lần publish theo cơ chế publisher confirms. | Consumer đã hoàn thành nghiệp vụ; ACK cũng không tự chứng minh có queue đích nếu không kiểm tra routing. |
| **Returned message (`basic.return`)** | RabbitMQ → publisher | Khi publish có `mandatory=true`, broker không định tuyến được message theo điều kiện tương ứng. | Broker NACK; một return vẫn có thể đi kèm publisher confirm ACK. |
| **Consumer ACK/NACK** | Listener/container → RabbitMQ | Xác nhận hoặc từ chối **một delivery** phía consumer. | Trạng thái publisher confirm của producer. |

## 3. Thất bại trước khi có kết nối hoạt động

### 3.1. Các nguyên nhân thường gặp

`RabbitTemplate` thường lấy connection/channel từ `CachingConnectionFactory` khi cần gửi. Nếu không thể có tài nguyên kết nối, việc publish có thể thất bại đồng bộ.

| Tình huống | Dấu hiệu điển hình | Hướng kiểm tra |
| --- | --- | --- |
| RabbitMQ chưa chạy hoặc sai hostname/port | `AmqpConnectException`, lỗi socket/connection refused | Broker có chạy không, DNS, port, firewall, security group. |
| Không hoàn tất xác thực/vhost | Lỗi authentication/authorization khi mở connection, có thể bị broker đóng connection | Username/password, vhost, quyền truy cập, RabbitMQ logs. |
| TLS/certificate không hợp lệ | Lỗi TLS handshake, trust store hoặc hostname validation | Scheme/port, certificate, CA, trust store và hostname. |
| Broker/chặng mạng không trả lời kịp | Timeout kết nối, heartbeat/IO errors | Network latency, timeout cấu hình, mức tải broker. |
| Channel pool đang bị giới hạn và cạn | `AmqpTimeoutException` khi mượn channel | `channelCacheSize` kết hợp `channelCheckoutTimeout`, số channel in-use. |

Nếu **thực sự chưa thiết lập được connection**, message chưa thể được publish qua connection đó. Nhưng không nên gom mọi `AmqpException` vào nhóm “chắc chắn chưa gửi”: nếu lỗi xảy ra **trong hoặc sau lúc ghi lên socket**, broker có thể đã nhận dữ liệu.

### 3.2. Ví dụ cấu hình connection timeout

Với **Spring Boot 3.x** và RabbitMQ AMQP 0-9-1:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
~~~

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    virtual-host: /
    connection-timeout: 5s
    requested-heartbeat: 20s
~~~

`connection-timeout` giúp giới hạn thời gian chờ thiết lập connection; `requested-heartbeat` phục vụ phát hiện connection không còn hoạt động, **không phải timeout chờ publisher confirm**. Các giá trị cần điều chỉnh theo mạng, broker và yêu cầu hệ thống, không mặc nhiên sao chép sang production.

RabbitMQ mặc định thường chỉ cho `guest` đăng nhập qua loopback. Ở production phải dùng tài khoản/vhost/permission riêng, TLS và secret store thích hợp.

### 3.3. Mặc định RabbitTemplate không phải hàng đợi offline

Khi RabbitMQ chưa sẵn sàng, gọi `RabbitTemplate.convertAndSend` **không tự ghi message vào một durable buffer cục bộ** để “có mạng rồi gửi lại”. Spring có thể tái lập connection ở lần thao tác tiếp theo, nhưng event chưa gửi được phải được ứng dụng **giữ lại và lên lịch phát lại** nếu muốn không bỏ sót.

Các lựa chọn:

- Với thao tác tạm thời, có thể retry kết nối với **backoff, số lần hữu hạn** và timeout phù hợp.
- Với event nghiệp vụ không được mất, lưu event vào database/outbox trước; worker thử publish nhiều lần và chỉ đánh dấu hoàn tất khi có bằng chứng đủ mạnh từ broker.
- Nếu trạng thái gửi **chưa chắc chắn**, giữ cùng `eventId` khi retry và để consumer xử lý idempotent.

## 4. Channel đóng khi publish: nguyên nhân và hậu quả

Một TCP connection có thể mang nhiều **AMQP channel**. RabbitMQ có thể **đóng một channel** vì một số lỗi điều khiển giao thức mà không đóng toàn bộ connection; nhưng mất connection sẽ ảnh hưởng các channel nằm trên connection đó.

### 4.1. Những lỗi khai báo/định tuyến có thể làm đóng channel

| Lỗi | Ví dụ | Phản hồi thường gặp |
| --- | --- | --- |
| Publish đến exchange không tồn tại | `convertAndSend("missing.exchange", "order.created", payload)` | `404 NOT_FOUND`, broker đóng channel. |
| Không đủ quyền với exchange | Tài khoản có quyền login vhost nhưng không được publish vào exchange | `403 ACCESS_REFUSED` hoặc lỗi quyền tương ứng; có thể đóng channel. |
| Khai báo lại queue/exchange không tương đương | Queue đang `durable=true` nhưng code khai báo cùng tên với `durable=false` | `406 PRECONDITION_FAILED`, channel khai báo bị đóng. |
| Dùng channel đã mất hiệu lực | Connection rớt hoặc channel bị broker đóng trước đó | Client phát hiện shutdown/IO exception; Spring có thể tạo channel mới ở thao tác sau. |
| Chạm giới hạn channel do broker thương lượng | Mở quá nhiều channel trên connection | Lỗi mở channel/connection hoặc lỗi quản lý tài nguyên tùy thời điểm. |

**Phân biệt quan trọng:** Publish đến **exchange có tồn tại nhưng không có binding tới queue** thường **không làm broker đóng channel**. Đó là trường hợp **unroutable message**, được xử lý bằng `mandatory/basic.return`. Còn publish đến **exchange không tồn tại** là lỗi **NOT_FOUND**, thường làm đóng channel.

### 4.2. Vì sao exception có thể xuất hiện ở lệnh tiếp theo?

`basic.publish` gửi frame qua network. Broker có thể phản hồi lỗi channel bằng frame đóng channel *sau khi* phía Java đã ghi xong buffer. Bởi vậy:

~~~java
// Ví dụ lỗi: exchange không tồn tại trong vhost hiện tại.
rabbitTemplate.convertAndSend(
        "exchange.does.not.exist",
        "order.created",
        "ORD-1001"
);
~~~

Không được giả định câu lệnh trên **luôn ném exception tại đúng dòng này**. Tùy thời điểm và cấu hình, lỗi đóng channel có thể được ghi ở shutdown listener/log, được phản ánh vào publisher confirm hoặc tác động thao tác kế tiếp.

Để có tín hiệu đáng tin hơn, cần bật **publisher confirms** và gắn **CorrelationData** cho từng lần gửi. Vẫn phải chấp nhận trạng thái **UNKNOWN** nếu connection chết trước khi tín hiệu confirm đến.

### 4.3. Channel cache không cứu được một publish đã thất bại

`CachingConnectionFactory` tái sử dụng channel còn hợp lệ; channel bị đóng vật lý do lỗi sẽ không thể được tái sử dụng như channel lành mạnh. Spring có thể lấy/mở channel khác cho thao tác sau, nhưng điều đó **không chứng minh message của thao tác lỗi đã được broker lưu**.

Một phương thức retry “lấy channel mới rồi publish lại” cần dùng **cùng event ID** và biết mình đang retry một sự kiện chưa rõ outcome. Đừng tạo một message nghiệp vụ hoàn toàn mới cho mỗi lần retry cùng sự kiện.

## 5. Broker NACK khác với returned message

### 5.1. Publisher confirms: ACK và NACK

RabbitMQ AMQP 0-9-1 có publisher confirms để broker phản hồi kết quả xử lý publish. Trong Spring Boot, bật:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
~~~

Với `correlated`, ứng dụng có thể ghép confirm với `CorrelationData` của lệnh gửi. Hai kết quả chính:

- **ACK:** Broker đã xử lý publish theo ngữ nghĩa của exchange/queue đích. Với persistent message tới durable queue, broker đưa ra bảo đảm liên quan đến việc lưu theo loại queue và chính sách của nó.
- **NACK:** Broker không thể xử lý publish thành công; đây là một tình huống **không thường xuyên**, không phải tín hiệu mặc định cho mọi routing key sai. Cần ghi nhận reason/cause nếu có và điều tra trạng thái broker.

**NACK của publisher không phải `basic.nack` do consumer gửi để từ chối delivery.** Hai bên xác nhận hai giai đoạn khác nhau.

### 5.2. Unroutable message: thường là return, không phải NACK

Ví dụ exchange `orders.events` tồn tại nhưng không có binding phù hợp với routing key `unknown.key`. Nếu producer publish:

~~~java
rabbitTemplate.convertAndSend(
        "orders.events",
        "unknown.key",
        "ORD-1001"
);
~~~

Kết quả phụ thuộc `mandatory`:

| Cấu hình publish | Exchange có tồn tại | Có queue phù hợp | Kết quả |
| --- | --- | --- | --- |
| `mandatory=false` | Có | Không | Message thường bị loại bỏ nếu không có alternate exchange xử lý; publisher có thể nhận **confirm ACK**. |
| `mandatory=true` | Có | Không | Broker gửi **basic.return** (thường `312 NO_ROUTE`), rồi publisher confirm vẫn có thể là **ACK**. |
| `mandatory=true` | Có | Có | Message được định tuyến; không có `basic.return` vì lý do không có queue. |
| Bất kỳ `mandatory` | **Không** | Không áp dụng | Broker thường đóng channel với `404 NOT_FOUND`; đây **không** phải một `basic.return` thông thường. |

Nếu exchange được cấu hình **alternate exchange**, broker có thể định tuyến message theo đường thay thế; khi đó cần kiểm tra toàn bộ topology thay vì kết luận “không thấy return nghĩa là vào queue chính”. `mandatory` và publisher confirms là các cơ chế quan sát **khác nhau**.

### 5.3. Return và confirm ACK có thể cùng xuất hiện

~~~mermaid
sequenceDiagram
    autonumber
    participant P as RabbitTemplate publisher
    participant B as RabbitMQ exchange
    participant Q as Queue cần nhận
    P->>B: basic.publish mandatory=true<br/>routingKey=missing.key
    Note over B,Q: Không có binding phù hợp
    B-->>P: basic.return 312 NO_ROUTE
    B-->>P: publisher confirm ACK
    Note over P: Broker xử lý publish nhưng<br/>không route đến queue yêu cầu
~~~

Với Spring AMQP hỗ trợ correlated confirms, returned message cho cùng lần gửi được xử lý trước khi completion của confirm future tương ứng, cho phép kiểm tra cả **confirm** và **return**. Khi log, hãy dùng ID của **cùng một sự kiện** để tránh nhầm callback trả về từ hai lần publish khác nhau.

## 6. Thiết lập môi trường thực hành Spring AMQP

### 6.1. Topology bền vững cho ví dụ

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersMessagingTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String QUEUE = "orders.created.q";
    public static final String ROUTING_KEY = "order.created";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding ordersBinding(Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with(ROUTING_KEY);
    }
}
~~~

Một `RabbitAdmin` được cấu hình phù hợp có thể khai báo exchange, queue và binding từ các bean Spring khi có kết nối. Với lỗi kết nối ban đầu, cần kiểm tra **topology đã thực sự được tạo** trước khi khẳng định publish có đích. Khai báo queue durable chỉ giữ định nghĩa qua broker restart theo điều kiện dữ liệu vẫn còn; nó không thay thế bảo đảm replication của quorum queue.

### 6.2. Cấu hình publisher confirms và returns

Gộp vào một `application.yml`:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    virtual-host: /
    connection-timeout: 5s
    requested-heartbeat: 20s
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Ba thuộc tính phải đi cùng nhau khi cần phát hiện routing failure ở producer:

1. `publisher-confirm-type: correlated`: nhận outcome ACK/NACK được gắn với `CorrelationData`.
2. `publisher-returns: true`: bật đường xử lý returned message trong `RabbitTemplate`.
3. `template.mandatory: true`: yêu cầu broker trả về message không có queue đích theo cơ chế `basic.return`.

Đây là cấu hình **cho producer**, không phải cấu hình consumer ACK. Nếu dùng Spring Boot phiên bản khác, kiểm tra tên property tương ứng với phiên bản thực tế và tránh trộn starter AMQP 0-9-1 với starter AMQP 1.0.

## 7. Ví dụ phân loại kết quả của một lần publish

### 7.1. Gắn event ID và chờ future confirm

Ví dụ Java dưới đây dành cho Spring AMQP 3.x / Spring Boot 3.x (các API xác nhận tương ứng cũng có ở những bản Spring AMQP phù hợp khác). Ý tưởng là một logical event có `eventId` không đổi khi retry.

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ReliableOrderPublisher {

    private final RabbitTemplate template;

    public enum State {
        CONFIRMED_NOT_RETURNED,
        UNROUTABLE,
        NACKED,
        UNKNOWN
    }

    public record PublishOutcome(
            String eventId, State state, String detail) {}

    public ReliableOrderPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public CompletableFuture<PublishOutcome> publish(
            String orderId, String eventId) {

        CorrelationData data = new CorrelationData(eventId);

        try {
            template.convertAndSend(
                    OrdersMessagingTopology.EXCHANGE,
                    OrdersMessagingTopology.ROUTING_KEY,
                    orderId,
                    message -> {
                        var props = message.getMessageProperties();
                        props.setMessageId(eventId);
                        props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                        return message;
                    },
                    data
            );
        } catch (AmqpException sendError) {
            // Bảo thủ: lỗi đồng bộ không luôn chứng minh broker chưa nhận.
            return CompletableFuture.completedFuture(
                    new PublishOutcome(
                            eventId, State.UNKNOWN, sendError.toString()));
        }

        return data.getFuture().handle((confirm, error) -> {
            if (error != null || confirm == null) {
                return new PublishOutcome(
                        eventId, State.UNKNOWN,
                        error == null ? "No confirm" : error.toString());
            }

            if (!confirm.isAck()) {
                return new PublishOutcome(
                        eventId, State.NACKED, confirm.getReason());
            }

            if (data.getReturned() != null) {
                return new PublishOutcome(
                        eventId, State.UNROUTABLE,
                        data.getReturned().getReplyText());
            }

            return new PublishOutcome(
                    eventId, State.CONFIRMED_NOT_RETURNED,
                    "Broker confirmed; no basic.return received");
        });
    }
}
~~~

Đoạn code minh họa **phân loại tín hiệu gửi**, không tự triển khai scheduler, database outbox hay timeout cho một future treo quá lâu. Trong hệ thống thật, cần một **thời hạn xác nhận** theo chính sách ứng dụng: quá thời hạn mà chưa có confirm thì chuyển event về trạng thái cần đối soát (*UNKNOWN*) và xử lý lại an toàn. Không nên chờ vô hạn trong HTTP request thread.

**Vì sao dùng tên `CONFIRMED_NOT_RETURNED` thay vì `DELIVERED`?** ACK của broker + không có return chưa chứng minh `@RabbitListener` đã chạy xong, cũng không nhất thiết chứng minh một queue cụ thể đã nhận nếu hệ thống có topology thay thế hoặc cấu hình đặc biệt. Nó chỉ là kết quả quan sát được ở **giai đoạn publish**.

### 7.2. Dùng kết quả từ phía gọi

~~~java
// Bên trong service/controller có bean ReliableOrderPublisher publisher:
publisher.publish("ORD-1001", "evt-1001")
        .whenComplete((outcome, failure) -> {
            if (failure != null) {
                // Ghi UNKNOWN và đối soát; không tự bỏ event.
                return;
            }

            switch (outcome.state()) {
                case CONFIRMED_NOT_RETURNED ->
                        System.out.println("Publish confirmed: " + outcome.eventId());
                case UNROUTABLE ->
                        System.err.println("Check routing: " + outcome.detail());
                case NACKED ->
                        System.err.println("Broker NACK: " + outcome.detail());
                case UNKNOWN ->
                        System.err.println("Need reconcile: " + outcome.detail());
            }
        });
~~~

`CompletableFuture` completion xảy ra bất đồng bộ; không mặc định thực hiện giao dịch database trong callback trên một thread tùy ý mà không có thiết kế transaction/executor rõ ràng. Một mô hình bền vững thường là **outbox record + publisher worker** để quản lý trạng thái gửi và retry.

### 7.3. Có cần ReturnsCallback và ConfirmCallback nữa không?

Spring `RabbitTemplate` còn hỗ trợ:

~~~java
template.setReturnsCallback(returned -> {
    System.err.printf(
            "RETURN exchange=%s routingKey=%s reply=%d %s%n",
            returned.getExchange(), returned.getRoutingKey(),
            returned.getReplyCode(), returned.getReplyText());
});

template.setConfirmCallback((correlation, ack, cause) -> {
    System.out.printf(
            "CONFIRM id=%s ack=%s cause=%s%n",
            correlation == null ? null : correlation.getId(),
            ack, cause);
});
~~~

Đây là các lời gọi minh họa **trong một method đã có biến `RabbitTemplate template`**, không phải một class Java độc lập. Với cấu hình publisher returns và mandatory, callback giúp log các tình huống không định tuyến được; confirm callback hỗ trợ giám sát ACK/NACK.

**Không gắn callback phân tán ở mỗi service** lên cùng một `RabbitTemplate`: setter có thể thay thế callback mà module khác đang sử dụng. Hãy đăng ký callback tập trung, hoặc dùng `CorrelationData`/future theo mỗi publish khi muốn liên hệ outcome với từng event.

## 8. Thất bại khi connection mất đúng lúc gửi: trạng thái UNKNOWN

Đây là tình huống quan trọng nhất về độ tin cậy. Giả sử producer gọi publish, ghi bytes ra socket rồi connection bị ngắt:

~~~text
Producer                   Network                  RabbitMQ
   |-- basic.publish --------X------------------------>|
   |                                                  |
   |  Có thể broker đã nhận message, cũng có thể chưa. |
   |<-- không nhận được publisher confirm -------------|
   |
   +-- retry?
~~~

Producer **không có bằng chứng kết quả cuối cùng** nếu confirm không đến. Có ít nhất hai khả năng:

- Message chưa tới broker: nếu không retry, **mất sự kiện**.
- Message đã tới queue và broker đã xử lý nhưng confirm bị mất: nếu retry, **có thể có hai bản**.

Vì vậy:

> Trong mô hình gửi đáng tin cậy, **retry với cùng event ID + consumer idempotent** quan trọng hơn kỳ vọng “network lỗi thì message chắc chắn chưa gửi”.

### Bảng quyết định khi retry

| Điều đã biết | Trạng thái nên ghi | Hành động hợp lý |
| --- | --- | --- |
| Chưa có connection thành công, chắc chắn không thể publish | `NOT_SENT` | Đợi broker phục hồi, retry có backoff. |
| Lỗi socket/channel trong lúc publish, không biết broker đã nhận chưa | `UNKNOWN` | Đối soát và retry cùng event ID; chuẩn bị xử lý trùng. |
| Broker confirm ACK, không có return | `CONFIRMED_NOT_RETURNED` | Đánh dấu giai đoạn publish hoàn thành theo contract; không suy ra business success. |
| Broker confirm NACK | `NACKED` | Ghi nguyên nhân, kiểm tra broker, retry theo policy. |
| Basic.return vì không định tuyến được | `UNROUTABLE` | Sửa exchange/binding/routing key/vhost; không retry nóng khi topology vẫn sai. |
| Chờ confirm quá deadline ứng dụng | `UNKNOWN` | Đối soát, tái gửi có kiểm soát và theo dõi khả năng duplicate. |

Không tự động chuyển mọi lỗi `AmqpException` sang trạng thái `NOT_SENT`. Chỉ khi chứng minh chắc lỗi xảy ra **trước khi có khả năng publish** mới dùng trạng thái này.

## 9. Retry, backoff và transactional outbox

### 9.1. Retry kỹ thuật khác retry nghiệp vụ

Retry kỹ thuật xử lý sự cố tạm thời như RabbitMQ vừa restart, DNS trễ hoặc mất connection. Retry nghiệp vụ xử lý một event có trạng thái chưa gửi xong và có thể đã được broker nhận ở lần trước.

| Lỗi | Có nên retry ngay? | Biện pháp |
| --- | --- | --- |
| Broker chưa chạy | Có thể retry sau **backoff**, giới hạn số lần trên một lượt gọi. | Health check, jitter/backoff, hàng đợi công việc hoặc outbox. |
| Authentication/permission sai | Không nên retry liên tục trước khi sửa cấu hình. | Kiểm tra credentials, vhost, quyền publish. |
| Exchange không tồn tại | Không nên retry nóng. | Khai báo topology hoặc sửa tên exchange. |
| Unroutable do sai key | Không nên retry y nguyên ngay. | Đối soát binding, key và alternate exchange. |
| Publisher NACK tạm thời | Có thể, sau khi phân tích nguyên nhân. | Theo dõi broker, sử dụng cùng event ID. |
| Không nhận confirm | **Outcome chưa rõ**; retry có rủi ro duplicate. | Outbox + idempotency + giới hạn/backoff. |

Spring AMQP có thể cấu hình retry template cho những lỗi gửi **đồng bộ** của `RabbitTemplate`, nhưng retry đó **không tự xử lý** publisher confirm NACK hoặc asynchronous return theo một workflow hoàn chỉnh. Đừng bật retry rồi cho rằng đã có exactly-once publish.

### 9.2. Transactional outbox cho event quan trọng

Một mô hình phù hợp khi ứng dụng vừa cập nhật database vừa phát sự kiện:

~~~mermaid
flowchart LR
    HTTP["Đơn hàng được tạo"]
    TX["DB transaction<br/>orders + outbox_events"]
    WORKER["Publisher worker"]
    MQ["RabbitMQ exchange/queue"]
    CONF["Confirm + return outcome"]
    CON["Idempotent @RabbitListener"]
    HTTP --> TX --> WORKER --> MQ --> CON
    MQ --> CONF --> WORKER
~~~

Quy trình:

1. Trong **một transaction database**, ghi đơn hàng và một bản ghi outbox chứa `eventId` duy nhất, `payload`, `exchange` và `routingKey`.
2. Worker đọc bản ghi chưa gửi, dùng **cùng eventId** làm `messageId` và `CorrelationData` cho mỗi lần phát lại.
3. Khi nhận confirm ACK và không có return theo contract định tuyến, worker chuyển record sang trạng thái đã phát thành công; ghi timestamps và số lần thử.
4. Khi NACK/return hoặc timeout, record vẫn có thể được sửa lỗi/tái phát. Với UNKNOWN, không được giả định message chưa từng vào broker.
5. Consumer dùng `eventId` làm khóa chống trùng; ghi dấu đã xử lý trong cùng transaction với side effect nghiệp vụ khi khả thi.

Không coi outbox là một “transaction phân tán” giữa DB và RabbitMQ. Nó biến yêu cầu phát sự kiện thành một **công việc có thể retry**, còn idempotency giải quyết khả năng giao hoặc publish trùng.

### 9.3. Dead-letter không phải nơi mặc định của lỗi publisher

**Dead-letter exchange (DLX)** xử lý message **đã ở trong queue** rồi bị reject, hết TTL, vượt giới hạn độ dài hoặc điều kiện được broker hỗ trợ. Khi producer không kết nối được hoặc exchange không tồn tại, **không có message trong queue đó để DLX tự chuyển**.

Vì vậy phân biệt:

- **Publish failure:** lưu/tracking ở **producer/outbox**, giám sát confirms/returns.
- **Consumer processing failure:** xử lý bằng listener error handler, retry, reject/NACK, DLX/DLQ.

Nếu message bị return do không định tuyến, producer có thể lưu nó vào kho lỗi nghiệp vụ hoặc phát lại sau khi sửa topology; đó là **logic ứng dụng**, không phải broker tự dead-letter cho một message chưa vào queue.

## 10. Kiểm tra consumer để tránh hiểu nhầm kết quả gửi

Một listener tối giản:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersListener {

    @RabbitListener(queues = OrdersMessagingTopology.QUEUE)
    public void onOrderCreated(String orderId) {
        System.out.println("Processing " + orderId);
        // Production: xử lý idempotent theo messageId/eventId
        // và commit dữ liệu trước khi method hoàn tất.
    }
}
~~~

Mặc định phổ biến của listener container Spring khi dùng `acknowledge-mode=AUTO` là **container ACK sau khi method thành công**, không phải AMQP `autoAck=true` trước xử lý. Nếu consumer ném exception, việc reject/requeue/dead-letter phụ thuộc retry/error handler và cấu hình queue.

### Bốn sự kiện khác nhau

| Sự kiện | Có thể chứng minh điều gì? |
| --- | --- |
| `convertAndSend` không ném exception | Phần thao tác gửi đồng bộ không phát hiện lỗi tại thời điểm đó. |
| Publisher confirm ACK | Broker xác nhận giai đoạn publish. |
| Queue có message ready/unacknowledged | Message đã được định tuyến đến queue và đang chờ/được giao theo trạng thái quan sát. |
| Listener commit DB và ACK | Một lần xử lý đã hoàn thành theo quy trình; vẫn phải chuẩn bị cho duplicate/redelivery. |

Publisher confirm ACK không phải bằng chứng listener đã ghi DB. Ngược lại, khi listener mất ACK sau khi commit DB, message có thể được giao lại dù publisher đã nhận confirm từ lâu.

## 11. Quan sát và chẩn đoán theo từng lớp

Để phân biệt các dạng lỗi, cần log/metrics có thể liên kết một **logical event** từ producer tới RabbitMQ và consumer:

| Dữ liệu quan sát | Cách sử dụng |
| --- | --- |
| `eventId/messageId` | Theo dõi một sự kiện qua nhiều lần publish, retry và consumer delivery. |
| `correlationId` | Ghép các message thuộc cùng workflow/request. |
| `exchange, routingKey, vhost` | Đối chiếu đích publish với topology thật. |
| `publishAttempt` và timestamp | Biết đã thử bao nhiêu lần, có backoff hay không. |
| `connection/channel shutdown reason` | Tìm `NOT_FOUND`, `ACCESS_REFUSED`, `PRECONDITION_FAILED`, I/O lỗi. |
| `publisher confirm ACK/NACK` và reason | Biết broker xác nhận hay từ chối publish. |
| `return replyCode, replyText, routingKey` | Nhận diện unroutable; ví dụ `312 NO_ROUTE`. |
| `queue ready/unacknowledged/consumer count` | Phân biệt chưa route, chưa có consumer và listener xử lý chậm. |
| `outbox status` | Biết sự kiện nào đang PENDING, UNKNOWN, CONFIRMED hoặc cần sửa topology. |
| `DLQ length, redelivery count` | Điều tra lỗi tiêu thụ **sau** giai đoạn publish. |

### Bảng chẩn đoán nhanh

| Triệu chứng | Nghi vấn đầu tiên | Bước kiểm tra |
| --- | --- | --- |
| `AmqpConnectException` ngay khi gửi | Broker/network/config chưa sẵn sàng | Host, port, credentials, TLS, broker health. |
| `AmqpTimeoutException` khi mượn channel | Channel limiting/checkout timeout | `channelCacheSize`, `channelCheckoutTimeout`, số consumer/channel in-use. |
| Log shutdown channel `404 NOT_FOUND` | Exchange không tồn tại | Tên exchange, vhost, `RabbitAdmin` khai báo thành công chưa. |
| Log `403 ACCESS_REFUSED` | Sai quyền truy cập | RabbitMQ user permissions theo exchange/vhost. |
| `406 PRECONDITION_FAILED` | Khai báo queue/exchange không tương đương | So sánh durable, auto-delete, queue type và arguments. |
| Publisher confirm **ACK**, callback có **NO_ROUTE** | Không có binding/queue phù hợp | Routing key, exchange, vhost, alternate exchange. |
| Publisher confirm **NACK** | Broker không xử lý publish thành công | RabbitMQ logs, trạng thái queue/node, storage/resource alarms. |
| Không có confirm trước deadline | Mạng/connection lỗi hoặc phản hồi bị chậm/mất | Theo dõi connection, broker, mark UNKNOWN. |
| Confirm ACK, queue ready tăng | Broker đã có message nhưng consumer chưa xử lý | Consumer count, prefetch, xử lý chậm, listener logs. |
| Message xuất hiện hai lần ở listener | Retry producer hoặc redelivery sau ACK thất lạc | Kiểm tra event ID và idempotency. |

**Không đồng nhất memory/disk alarms với publisher NACK.** RabbitMQ có cơ chế resource alarm và connection blocking có thể làm publisher bị chậm hoặc block; không phải mọi áp lực broker đều tự động sinh NACK. Cần quan sát tín hiệu thực tế và giới hạn thời gian của ứng dụng.

## 12. Thực hành ba nhóm lỗi riêng biệt

Sử dụng một RabbitMQ và ứng dụng Spring Boot **trong môi trường thử nghiệm**, không dùng queue hoặc user production. Chuẩn bị topology và publisher có `CorrelationData` như mục 6–7.

| Bước | Thao tác | Kết quả cần kiểm tra |
| --- | --- | --- |
| 1 | Khởi động RabbitMQ và ứng dụng; gửi `ORD-1001` bằng exchange/key đúng. | Confirm ACK, không return; listener có thể nhận/ACK nếu đang chạy. |
| 2 | Dừng RabbitMQ **trước khi** gọi publish thử `evt-no-connection`. | Lỗi kết nối đồng bộ hoặc timeout; message chưa thể gửi qua connection chưa thiết lập. |
| 3 | Khởi động lại broker; kiểm tra ứng dụng khôi phục connection, topology được khai báo lại đúng. | Lần gửi mới hoạt động; event thất bại trước đó **không tự được RabbitTemplate phát lại** nếu không có retry/outbox. |
| 4 | Gửi tới exchange `exchange.does.not.exist`. | Quan sát `404 NOT_FOUND`/channel shutdown; không nhầm với basic.return unroutable. |
| 5 | Tạo exchange tồn tại nhưng gửi routing key không có binding, với `mandatory=true`. | Callback/data return xuất hiện, ví dụ `312 NO_ROUTE`; confirm **có thể ACK**. |
| 6 | Tắt mandatory rồi thử lại với key không có binding. | Có thể không thấy return; confirm ACK không chứng minh message đã vào queue. |
| 7 | Dừng consumer nhưng giữ queue; gửi bằng key đúng. | Confirm ACK, không return; message có thể ở **ready**, khác lỗi định tuyến. |
| 8 | Thử mất kết nối **trong lúc** có nhiều publish (chỉ trong test). | Một số event có trạng thái UNKNOWN, cần log confirm/return và đối soát. |
| 9 | Gửi lại cùng `eventId` hai lần và dùng consumer có kiểm tra unique event ID. | Side effect chỉ xảy ra một lần dù hai message có thể được giao. |
| 10 | Mô phỏng consumer lỗi có DLX/DLQ. | Đây là lỗi **xử lý phía consumer**, khác hoàn toàn lỗi publisher không kết nối. |

NACK của publisher là sự kiện **không dễ tái hiện một cách an toàn và có kiểm soát**. Không nên cố gây hỏng storage, thay đổi cluster production hoặc phá broker chỉ để “nhìn thấy NACK”. Khi không có NACK thực tế, có thể **unit test** nhánh xử lý outcome NACK bằng một kết quả giả lập trong logic ứng dụng; phần broker integration chỉ xác minh ACK, return và shutdown.

### Mẫu ghi chép

~~~text
Event ID:
Publish attempt:
Exchange / routing key / vhost:
Connection available before send?:
Synchronous exception:
Channel shutdown reply code / reason:
Publisher confirm: ACK / NACK / NONE
Basic.return reply code / reply text:
RabbitMQ queue ready/unacknowledged:
Listener processed / ACK?:
Producer classification: NOT_SENT / UNKNOWN / NACKED / UNROUTABLE / CONFIRMED
Action: RETRY / REPAIR TOPOLOGY / RECONCILE / DONE
~~~

## 13. Tự kiểm tra

**Câu 1.** RabbitMQ chưa chạy và `RabbitTemplate.convertAndSend` ném lỗi kết nối. Có thể xem đây là lỗi do consumer `@RabbitListener` xử lý thất bại không?

**Trả lời:** Không. Producer chưa có connection để publish; consumer chưa thể nhận delivery từ lần gửi này.

**Câu 2.** Broker đóng channel với `404 NOT_FOUND` khi publish đến `missing.exchange`. Có nên chờ `basic.return 312 NO_ROUTE` như trường hợp routing key sai không?

**Trả lời:** Không. Exchange không tồn tại là lỗi channel/`NOT_FOUND`; unroutable return xảy ra khi publish đến exchange hợp lệ nhưng không có queue đích theo điều kiện mandatory.

**Câu 3.** Publisher nhận confirm ACK nhưng `ReturnsCallback` báo `NO_ROUTE`. Message đã vào queue công việc chưa?

**Trả lời:** Không. Broker đã xử lý publish nhưng không định tuyến được đến queue đích; ACK không mâu thuẫn với return.

**Câu 4.** Khi mất connection ngay sau khi ghi bytes publish, producer không nhận confirm. Có thể mặc định message chưa tới broker không?

**Trả lời:** Không. Outcome chưa rõ. Retry cùng event ID và có consumer idempotent để an toàn trước khả năng gửi trùng.

**Câu 5.** Bật `template.mandatory=true` nhưng không bật/đăng ký publisher returns. Có bảo đảm ứng dụng sẽ nhận diện mọi message không định tuyến được không?

**Trả lời:** Không. Cần xử lý đường return qua cấu hình và callback/tương quan phù hợp, đồng thời quan sát confirms. Nếu không đọc return, ứng dụng vẫn có thể hiểu nhầm confirm ACK là routed.

**Câu 6.** Dead-letter queue có tự nhận những message mà producer không gửi được vì broker chưa kết nối không?

**Trả lời:** Không. DLX áp dụng với message đã ở queue và đủ điều kiện dead-letter; lỗi publisher cần được quản lý ở producer/outbox.

**Câu 7.** Nếu consumer đã ghi DB rồi mất ACK, publisher confirm trước đó có ngăn được message được giao lại không?

**Trả lời:** Không. Hai loại ACK thuộc hai giai đoạn khác nhau. Consumer cần xử lý trùng theo event ID và transaction DB phù hợp.

## 14. Tài liệu tham khảo

- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/publisher-confirms-returns.html): cấu hình `RabbitTemplate`, `CorrelationData`, xác nhận và returned messages.
- [Spring AMQP — Sending Messages](https://docs.spring.io/spring-amqp/reference/amqp/sending-messages.html): các overload `convertAndSend`, publisher và exchange/routing key.
- [Spring AMQP — Connections](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): `CachingConnectionFactory`, channel cache, đóng channel và connection recovery.
- [Spring AMQP — RabbitTemplate Javadoc](https://docs.spring.io/spring-amqp/api/org/springframework/amqp/rabbit/core/RabbitTemplate.html): API publish, callback và confirms.
- [RabbitMQ — Publisher Confirms and Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms): semantics ACK/NACK cho publisher và consumer.
- [RabbitMQ — Publishers](https://www.rabbitmq.com/docs/publishers): cơ chế publish, mandatory và broker resource alarm.
- [RabbitMQ — Exchanges](https://www.rabbitmq.com/docs/exchanges): đường định tuyến message, binding và alternate exchange.
- [RabbitMQ — Reliability Guide](https://www.rabbitmq.com/docs/reliability): connection failure, confirms, redelivery và các giới hạn bảo đảm khi có lỗi.

**Ghi nhớ:** **Không kết nối được**, **channel bị đóng**, **broker NACK** và **unroutable return** là những tình huống gửi thất bại **khác nhau**, đòi hỏi cách quan sát và xử lý riêng. `RabbitTemplate.convertAndSend(...)` không ném exception chỉ là tín hiệu của thao tác đồng bộ; hãy kết hợp **publisher confirms + mandatory returns**, theo dõi **UNKNOWN** khi mất confirm, lưu event bằng **outbox**, retry với **event ID ổn định** và xây `@RabbitListener` **idempotent**. Những bước đó kết nối định tuyến, xác nhận giao nhận, retry, dead-letter, giao dịch và quan sát hệ thống thành một luồng xử lý bất đồng bộ đáng tin cậy.
