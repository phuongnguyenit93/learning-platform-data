# Thông điệp không định tuyến được vẫn có thể nhận confirm ack

Khi xây hệ thống bất đồng bộ bằng **RabbitMQ và Spring AMQP**, một lỗi rất nguy hiểm là thấy **publisher confirm ACK** rồi kết luận: “Message đã vào đúng queue và sẽ được consumer xử lý.” Kết luận đó **không đúng**. Nếu publish đến **exchange có tồn tại** nhưng **không có binding khớp routing key**, RabbitMQ vẫn có thể gửi **publisher confirm ACK** cho một message mà **không queue nào nhận được**.

Lý do là publisher confirm và message routing trả lời hai câu hỏi khác nhau:

- **Confirm ACK/NACK:** RabbitMQ đã xử lý trách nhiệm của broker đối với lần publish này thành công hay thất bại?
- **Return (basic.return):** Message có bị **không định tuyến được đến queue** và được trả về publisher theo cơ chế **mandatory** hay không?

Bài học thuộc chương **Confirm và return**. Ta sẽ thử tình huống “ACK nhưng queue không có message”, bật **publisher returns** trong Spring AMQP, phối hợp **RabbitTemplate**, **CorrelationData**, **ReturnsCallback** và **ConfirmCallback**, rồi thiết kế cách xử lý đúng khi cần giao nhận đáng tin cậy.

## 1. Hiểu nghịch lý: ACK không đồng nghĩa “đã giao đến consumer”

Giả sử broker có **direct exchange** tên **demo.orders.events** và một queue:

~~~text
Exchange: demo.orders.events (direct)
  |
  +-- binding key = order.created
        |
        v
      Queue: demo.billing.orders
~~~

Publisher gửi message vào exchange cùng routing key **order.cancelled**, trong khi exchange **không có binding nào** cho key đó.

~~~mermaid
flowchart LR
    P["RabbitTemplate<br/>routingKey=order.cancelled"] --> E{"Direct exchange<br/>demo.orders.events"}
    E -->|"Không có binding khớp"| N["Không queue nào nhận"]
    E -.->|"Publisher confirm ACK"| P
~~~

**Điều gì xảy ra?**

1. RabbitMQ nhận và xử lý lệnh publish vào exchange hợp lệ.
2. Exchange kiểm tra routing key nhưng không tìm thấy queue phù hợp.
3. Không có cơ chế định tuyến thay thế nên message không được đưa vào queue.
4. Publisher vẫn có thể nhận **confirm ACK** vì broker đã hoàn thành xử lý publish theo topology hiện có.

Publisher confirm không phải xác nhận của **consumer**. Nó cũng không tự kiểm chứng exchange có binding đúng với ý định nghiệp vụ.

### Ba tầng cần tách biệt

| Tầng | Câu hỏi | Cơ chế quan sát |
| --- | --- | --- |
| **Publisher → broker** | Broker đã xử lý publish thành công chưa? | Publisher confirm ACK/NACK |
| **Exchange → queue** | Message có tới queue đích không? | Binding, routing key, **mandatory + return**, topology và metrics |
| **Queue → consumer** | Consumer đã nhận và xử lý hoàn tất chưa? | Consumer ACK/NACK, trạng thái nghiệp vụ, tracing |

Ngay cả khi message đã vào queue, publisher confirm ACK vẫn **không chứng minh** consumer đã ghi database hoặc hoàn tất nghiệp vụ. Confirm, return và consumer acknowledgement là **ba cơ chế độc lập**.

## 2. RabbitMQ xác nhận điều gì bằng publisher confirm?

Trong AMQP 0-9-1, sau khi channel bật **publisher confirm mode** bằng **confirm.select**, broker gửi **basic.ack** hoặc **basic.nack** cho các lần publish trên channel đó.

- **basic.ack** ở hướng publisher: broker đã xử lý publish thành công theo ngữ nghĩa broker, bao gồm các queue được định tuyến tới (nếu có).
- **basic.nack** ở hướng publisher: broker gặp lỗi khi xử lý publish trong một tình huống hỗ trợ NACK; publisher cần ghi nhận và xác định việc gửi lại.
- Kết quả được gửi **bất đồng bộ**. Đừng phụ thuộc thứ tự các callback xác nhận bằng thứ tự mọi lần gọi publish.

Đối với message **routable**, broker xác nhận theo tiêu chí chấp nhận message của queue nhận. Với persistent message tới durable queue, confirm còn gắn với cơ chế lưu bền của queue; với quorum queue, việc xác nhận gắn với trạng thái các replica quorum.

Đối với message **unroutable**, exchange có thể xác định ngay không có queue nào nhận. Broker vẫn gửi **ACK** sau khi hoàn thành quyết định đó. Đó không phải bằng chứng đã lưu message trong queue.

### Vẫn phải dùng publisher confirms

Không nên vì giới hạn trên mà bỏ publisher confirms. Nếu publisher đã ghi bytes vào socket rồi mất kết nối, ứng dụng **không thể tự biết** broker đã nhận message hay chưa. Publisher confirms giúp phân biệt những lần publish được broker xác nhận với những lần thất bại hoặc chưa có kết quả rõ ràng.

Điểm quan trọng: **confirm ACK một mình không phát hiện routing key sai hoặc binding thiếu**.

## 3. mandatory và basic.return giải quyết điều gì?

Trong AMQP 0-9-1, publisher có thể đặt **mandatory=true**. Khi message **không thể được route tới queue**, RabbitMQ gửi **basic.return** cho publisher, kèm message và thông tin nguyên nhân như **NO_ROUTE**.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant E as RabbitMQ exchange
    participant Q as Queue
    P->>E: basic.publish (mandatory=true, routingKey sai)
    E-->>E: Không tìm được binding phù hợp
    E-->>P: basic.return (NO_ROUTE + message)
    E-->>P: publisher basic.ack
    Note over P,Q: Không có message trong queue
~~~

**Cùng một lần publish có thể sinh ra cả RETURN lẫn confirm ACK.** Chúng không mâu thuẫn:

- **RETURN:** message không vào queue theo điều kiện mandatory.
- **ACK:** broker đã hoàn tất xử lý publish, kể cả khi kết quả là không queue nào nhận.

Khi bật publisher returns, ứng dụng phải **thực sự tiếp nhận và xử lý** thông tin return. Cấu hình returns ở ConnectionFactory không tự khắc phục lỗi định tuyến.

### Khi mandatory=false

**mandatory=false** là mặc định nếu không cấu hình khác. Khi không có binding khớp và không có alternate exchange xử lý, RabbitMQ **loại bỏ message** mà vẫn có thể gửi **publisher confirm ACK**. Publisher **không nhận basic.return**.

Vì vậy, với hệ thống cần phát hiện message không tới queue, cần phối hợp:

1. Bật publisher confirms.
2. Bật publisher returns trên connection factory.
3. Đặt **mandatory=true** trên RabbitTemplate hoặc dùng mandatory expression phù hợp.
4. Xử lý **cả return lẫn confirm** theo đúng ngữ nghĩa.

## 4. Ma trận kết quả ACK, RETURN và routing

Giả sử publisher gửi tới một **direct exchange đang tồn tại**, có quyền publish, không có alternate exchange, broker hoạt động bình thường:

| Binding khớp? | mandatory | basic.return? | Publisher confirm | Ý nghĩa |
| --- | --- | --- | --- | --- |
| **Có** | false | Không | **ACK** sau khi queue chấp nhận message | Message đã được route tới queue |
| **Có** | true | Không | **ACK** theo quy tắc queue | Message có queue nhận |
| **Không** | false | **Không** | **ACK** | Message bị loại im lặng |
| **Không** | true | **Có**, thường **NO_ROUTE** | **ACK** | Message bị trả về trước khi broker ACK |

**Các ngoại lệ cần ghi nhớ:**

- **Exchange không tồn tại:** broker báo channel exception và đóng channel, **không phải** trường hợp exchange hợp lệ nhưng không có binding. Publisher có thể nhận exception hoặc confirm thất bại; không dựa vào mẫu callback cố định trong mọi tình huống.
- **Alternate exchange:** message không khớp có thể được đưa vào queue dự phòng. Khi đó không nhất thiết có return; ACK không chứng minh message đã vào queue đích ban đầu.
- **Queue không có consumer:** nếu queue có binding đúng và nhận message, đó **không phải unroutable**. Mandatory không yêu cầu return chỉ vì consumer count bằng 0.
- **Broker hoặc quyền lỗi:** outcome có thể là exception, NACK, timeout hoặc không rõ kết quả; không gộp chúng vào trường hợp ACK unroutable.

**Ghi nhớ:** Confirm ACK nói về xử lý publish của broker; return nói về message không route được theo mandatory; consumer ACK nói về giao nhận ở phía consumer.

## 5. Trình tự khi vừa có return vừa có confirm

Theo giao thức RabbitMQ, với message unroutable và **mandatory=true**, broker gửi **basic.return trước basic.ack** (hoặc basic.nack trong tình huống tương ứng). Vì thế application có thể kết hợp hai tín hiệu.

Với Spring AMQP dùng correlated publisher confirms/returns:

- **ReturnsCallback** nhận **ReturnedMessage**, chứa message trả về, reply code, reply text, exchange và routing key.
- **ConfirmCallback** nhận **CorrelationData**, ACK/NACK boolean và nguyên nhân nếu có.
- **CorrelationData.getFuture()** cho phép xử lý bất đồng bộ kết quả confirm.
- Khi cả confirms và returns bật, Spring AMQP gắn dữ liệu return vào CorrelationData trước khi hoàn tất future confirm. Tài liệu callback có giới hạn chờ để tránh việc một returns callback chạy mãi.

**Chỉ kiểm tra ACK boolean là sai.** Phân loại một lần gửi là “confirmed và không thấy return” khi:

~~~java
confirm.isAck() && correlationData.getReturn() == null
~~~

Đây là **mức kiểm tra publish/mandatory return** chứ không phải chứng minh consumer hoàn tất hoặc tới đúng queue khi tồn tại alternate exchange hay binding sai ngữ nghĩa.

### Phân biệt ba định danh

| Định danh | Phạm vi | Có thay đổi khi publish retry? |
| --- | --- | --- |
| **eventId** hoặc business messageId | Một sự kiện logic, phục vụ idempotency | **Không** nếu là cùng sự kiện |
| **CorrelationData.id** | Một lần publish cần đối chiếu confirm/return | **Có thể tạo mới cho mỗi attempt** |
| **AMQP deliveryTag** của consumer | Một lần giao trên channel | Có thể thay đổi khi redelivery |

Khi gửi lại cùng sự kiện sau timeout, giữ eventId ổn định và có thể dùng CorrelationData ID mới để phân biệt các lần gửi trong log.

## 6. Cấu hình Spring Boot cho confirms và returns

Sử dụng **spring-boot-starter-amqp** cùng RabbitMQ broker có tài khoản lab tương ứng.

Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-amqp")
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Ví dụ **application.yml** trên Spring Boot 3.x:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: local_dev_password
    virtual-host: /
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

| Thuộc tính | Tác dụng |
| --- | --- |
| **publisher-confirm-type: correlated** | Bật confirms có correlation, hỗ trợ CorrelationData/future/callback |
| **publisher-returns: true** | Cho framework nhận returned message |
| **template.mandatory: true** | Yêu cầu broker return nếu message không route được |

Thông tin user/password chỉ dùng trong lab; production nên quản lý bằng secret manager hoặc biến môi trường và cấp quyền tối thiểu.

**Không nhầm confirm-type simple với correlated:** dùng **correlated** cho việc ghép kết quả đến từng message/attempt. Nếu tự tạo CachingConnectionFactory hoặc RabbitTemplate, phải chắc các thuộc tính tương ứng đã được áp dụng vào **bean thực sự dùng**.

## 7. Tạo topology để tái hiện lỗi routing

Tạo exchange **demo.orders.events** loại direct, queue **demo.billing.orders** và binding chỉ nhận routing key **order.created**:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ConfirmReturnTopology {
    public static final String EXCHANGE = "demo.orders.events";
    public static final String QUEUE = "demo.billing.orders";
    public static final String ROUTABLE_KEY = "order.created";
    public static final String UNROUTABLE_KEY = "order.cancelled";

    @Bean
    DirectExchange orderExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue billingQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding billingBinding(Queue billingQueue, DirectExchange orderExchange) {
        return BindingBuilder.bind(billingQueue)
                .to(orderExchange)
                .with(ROUTABLE_KEY);
    }
}
~~~

Ví dụ **cố ý không có binding** cho **order.cancelled**. Nếu RabbitAdmin đang hoạt động và kết nối thành công, các bean có thể được auto-declare. Hãy kiểm tra topology trên RabbitMQ Management trước khi gửi thử, đặc biệt khi broker còn tài nguyên từ những buổi lab trước.

~~~text
demo.orders.events [direct]
  |
  +-- routing key "order.created"
          |
          v
       demo.billing.orders

routing key "order.cancelled"
  |
  +-- không có binding -> unroutable
~~~

Nếu broker đã có binding khác cho **order.cancelled**, phép thử sẽ không còn là unroutable; dùng routing key mới không được bind hoặc tạo topology sạch có tên riêng.

## 8. Dùng CorrelationData để kết hợp ACK và RETURN

Đây là ví dụ **theo từng lần publish**, phù hợp để hiểu cách một service hoặc outbox dispatcher phân loại kết quả. Ta sẽ:

1. Gắn **messageId** ổn định ở MessageProperties.
2. Tạo **CorrelationData** riêng cho publish attempt.
3. Đăng ký xử lý bất đồng bộ **CompletableFuture**.
4. Kiểm tra **return cùng confirm** trước khi đánh dấu trạng thái.

~~~java
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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

    public void publish(String eventId, String routingKey, String payload) {
        // ID của attempt để đối chiếu confirm và return:
        CorrelationData correlation =
                new CorrelationData(UUID.randomUUID().toString());

        // Gắn handler trước khi gửi, tránh bỏ lỡ confirm nhanh.
        correlation.getFuture().whenComplete((confirm, failure) -> {
            if (failure != null) {
                log.error("PUBLISH_UNKNOWN eventId={} attemptId={}",
                        eventId, correlation.getId(), failure);
                return;
            }

            if (!confirm.isAck()) {
                log.error("PUBLISH_NACK eventId={} attemptId={} reason={}",
                        eventId, correlation.getId(), confirm.getReason());
                return;
            }

            // Một ACK vẫn có thể đi kèm returned message!
            var returned = correlation.getReturn();
            if (returned != null) {
                log.warn(
                        "PUBLISH_UNROUTABLE eventId={} attemptId={} " +
                        "reply={} exchange={} routingKey={}",
                        eventId,
                        correlation.getId(),
                        returned.getReplyText(),
                        returned.getExchange(),
                        returned.getRoutingKey()
                );
                return;
            }

            log.info("PUBLISH_CONFIRMED_NO_RETURN eventId={} attemptId={}",
                    eventId, correlation.getId());
        });

        rabbitTemplate.convertAndSend(
                ConfirmReturnTopology.EXCHANGE,
                routingKey,
                payload,
                message -> {
                    message.getMessageProperties().setMessageId(eventId);
                    message.getMessageProperties().setType("order.event");
                    return message;
                },
                correlation
        );
    }
}
~~~

**Giải thích ví dụ:**

- **getFuture()** có ý nghĩa khi connection factory bật **CORRELATED confirms**.
- **correlation.getReturn()** chứa returned message khi broker gửi basic.return và Spring AMQP ghép được với attempt.
- Nhánh **PUBLISH_UNROUTABLE** nằm **sau** điều kiện ACK: đây chính là trường hợp message bị return nhưng vẫn ACK.
- Nhánh **PUBLISH_CONFIRMED_NO_RETURN** chỉ chứng minh không ghi nhận return trong cơ chế đã cấu hình, **không xác nhận consumer xử lý**.
- **convertAndSend** có thể ném exception **đồng bộ** (ví dụ lỗi kết nối). Caller production phải xử lý lỗi đó; không thể chỉ dựa vào future. Để tránh mất event sau crash, dùng outbox hoặc trạng thái publish bền vững.

### Thử gửi hai routing key

Giả sử tầng nghiệp vụ đã tạo hai eventId độc lập, gọi:

~~~java
publisher.publish(
        "f22ca2d5-91da-4c69-a1c4-26aeb10a2320",
        ConfirmReturnTopology.ROUTABLE_KEY,
        "order.created:O-1001"
);

publisher.publish(
        "51a03e8e-75a0-4b30-a4c5-f43a2995b348",
        ConfirmReturnTopology.UNROUTABLE_KEY,
        "order.cancelled:O-1001"
);
~~~

Trong điều kiện bình thường, log có thể tương tự:

~~~text
PUBLISH_CONFIRMED_NO_RETURN eventId=f22ca2d5-... attemptId=...
PUBLISH_UNROUTABLE eventId=51a03e8e-... attemptId=... reply=NO_ROUTE exchange=demo.orders.events routingKey=order.cancelled
~~~

Thông điệp đầu có binding hợp lệ nên queue nhận; thông điệp sau **có thể vừa được RETURN vừa nhận confirm ACK**. Thứ tự hai dòng log không được bảo đảm vì confirms bất đồng bộ.

**Chú ý phiên bản:** đối với các phiên bản Spring AMQP hiện đại theo tài liệu tham khảo, **CorrelationData.getReturn()** cung cấp thông tin trả về; các ví dụ Spring AMQP cũ có thể dùng tên callback hoặc API khác.

## 9. ReturnsCallback và ConfirmCallback trực tiếp

Ngoài future trên CorrelationData, có thể đăng ký callback ở RabbitTemplate. Đoạn dưới đặt **trong phần cấu hình có sẵn RabbitTemplate**:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

rabbitTemplate.setReturnsCallback(returned -> {
    System.err.printf(
            "RETURN reply=%s exchange=%s routingKey=%s%n",
            returned.getReplyText(),
            returned.getExchange(),
            returned.getRoutingKey()
    );
});

rabbitTemplate.setConfirmCallback((correlationData, ack, cause) -> {
    String attemptId = correlationData == null
            ? "unknown"
            : correlationData.getId();

    if (!ack) {
        System.err.printf(
                "NACK attemptId=%s cause=%s%n",
                attemptId, cause
        );
    } else {
        System.out.printf("ACK attemptId=%s%n", attemptId);
    }
});
~~~

- **ReturnsCallback** báo message không route được khi mandatory/returns đáp ứng yêu cầu.
- **ConfirmCallback** báo ACK/NACK; chỉ in “ACK” không đủ để quyết định đã tới queue.
- Mỗi RabbitTemplate chỉ hỗ trợ **một** callback confirm và **một** callback returns tại một thời điểm; một cấu hình khác gọi setter có thể thay thế callback trước.
- Khi dùng callback cùng CorrelationData future, tránh **xử lý thay đổi trạng thái nghiệp vụ hai lần** từ hai đường thông báo. Chọn một luồng tổng hợp kết quả làm nguồn quyết định.

Trong Spring Boot 3.x, có thể giữ template được auto-configure bằng **RabbitTemplateCustomizer**:

~~~java
import org.springframework.boot.autoconfigure.amqp.RabbitTemplateCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ConfirmReturnCallbackConfig {

    @Bean
    RabbitTemplateCustomizer confirmReturnCallbacks() {
        return template -> {
            template.setReturnsCallback(returned ->
                    System.err.println("RETURN " + returned.getReplyText()));

            template.setConfirmCallback((correlation, ack, cause) ->
                    System.out.println("CONFIRM ack=" + ack));
        };
    }
}
~~~

Ví dụ callback để **quan sát bổ sung**, không thay thế kiểm tra outcome chi tiết ở phần 8. Trong ứng dụng thực, dùng logger có cấu trúc, correlation ID và metric; kiểm tra vị trí package customizer theo phiên bản Spring Boot đang chạy.

## 10. Khi tắt mandatory, vì sao ACK dễ gây hiểu nhầm?

Xét các lần gửi **cùng exchange và routing key không khớp**:

| Thiết lập | Publisher thường quan sát | Rủi ro |
| --- | --- | --- |
| **confirm=correlated**, **returns=true**, **mandatory=false** | ACK, **không RETURN** | Message bị loại nhưng code dễ đánh dấu “thành công” |
| **confirm=correlated**, **returns=true**, **mandatory=true** | **RETURN (NO_ROUTE)** rồi ACK | Có bằng chứng lỗi định tuyến |
| **confirm=none**, **returns=true**, **mandatory=true** | Có thể thấy RETURN nhưng không có correlated confirm ACK/NACK | Không đủ tín hiệu về trách nhiệm broker |
| **confirm=correlated**, **returns=false**, **mandatory=true** | Có ACK nhưng không có dữ liệu return theo cơ chế Spring | Ứng dụng có thể bỏ lỡ unroutable |

**Không có một cờ riêng lẻ nào giải quyết toàn bộ.** Cần phối hợp **correlated confirms + publisher returns + mandatory**, rồi đọc cả kết quả confirm và returned message.

Mandatory **không làm RabbitMQ tạo queue mới**. Nếu exchange có binding sai, mandatory chỉ giúp publisher biết lỗi; cần sửa topology hoặc chọn routing key đúng.

## 11. Exchange không tồn tại là trường hợp khác

Exchange có tồn tại nhưng không có binding khớp là tình huống RabbitMQ **có thể xử lý hợp lệ** và trả ACK. Nếu publisher gửi tới **exchange không tồn tại**, broker báo **channel exception** và đóng channel.

| Trường hợp | Loại vấn đề | Hướng xử lý |
| --- | --- | --- |
| Exchange tồn tại, routing key không khớp | **Unroutable** | Mandatory + return, kiểm tra binding và key |
| Exchange không tồn tại | **Channel exception** | Khai báo exchange qua RabbitAdmin/hạ tầng, kiểm tra vhost và quyền |
| Queue có binding nhưng chưa có consumer | **Không phải unroutable** | Quan sát queue Ready, consumer count và backlog |
| Exchange có alternate exchange nhận message | Message có thể được route sang queue fallback | Kiểm tra topology; ACK không chứng minh tới queue đích ban đầu |

Không nên coi mọi lỗi exchange missing là **basic.return(NO_ROUTE)**. Return chỉ áp dụng vào cơ chế định tuyến của exchange hợp lệ.

## 12. Alternate exchange khiến ACK + không RETURN chưa phải đủ

RabbitMQ hỗ trợ **alternate exchange (AE)**: nếu exchange chính không thể route message đến queue, nó có thể chuyển message sang exchange dự phòng.

~~~mermaid
flowchart TD
    P["Publisher"] --> E{"Orders exchange"}
    E -->|"Binding khớp"| Q[("Billing queue")]
    E -->|"Không khớp, có alternate exchange"| AE{"Alternate exchange"}
    AE --> FQ[("Fallback queue")]
    E -.->|"Publisher confirm ACK khi broker xử lý thành công"| P
~~~

Trong cấu hình này, publisher có thể thấy **ACK và không RETURN**, nhưng message thực tế đi đến **fallback queue** thay vì Billing. Do đó:

- Mandatory + return giúp phát hiện các message không tới queue nào trong tình huống áp dụng, nhưng **không chứng minh đã đến đúng queue nghiệp vụ**.
- Confirm ACK không mang danh sách queue cuối cùng nhận message.
- Nếu hợp đồng yêu cầu một queue cụ thể, cần kiểm soát exchange/binding, thử nghiệm routing, giám sát fallback queue và xử lý message thất lạc khỏi đường đi dự kiến.

Không nên đánh dấu công việc Billing đã hoàn tất chỉ vì broker xác nhận publish vào alternate exchange.

## 13. Phân loại kết quả publish để ra quyết định đúng

~~~mermaid
flowchart TD
    S["Gửi message<br/>mandatory=true"] --> C{"Có confirm trong thời gian quy định?"}
    C -->|"Không / lỗi connection"| U["UNKNOWN<br/>Đối chiếu hoặc retry an toàn"]
    C -->|"Có NACK"| N["NACK<br/>Ghi lỗi, retry có kiểm soát"]
    C -->|"Có ACK"| R{"Có returned message?"}
    R -->|"Có"| F["UNROUTABLE<br/>Sửa topology/routing key"]
    R -->|"Không"| OK["CONFIRMED_NO_RETURN<br/>Chưa phải consumer success"]
~~~

| Kết quả | Có thể đánh dấu đã xử lý nghiệp vụ chưa? | Hành động gợi ý |
| --- | --- | --- |
| **ACK + RETURN** | **Không** | Ghi lỗi định tuyến, cảnh báo, sửa binding/routing key hoặc xử lý fallback |
| **ACK + không RETURN** | **Chưa đủ** | Có thể đánh dấu broker-accepted theo hợp đồng publish, tiếp tục theo dõi consumer |
| **NACK** | Không | Ghi nguyên nhân, retry có kiểm soát hoặc chuyển xử lý thủ công |
| **Timeout/không có kết quả** | **Không xác định** | Giữ eventId, theo dõi và retry an toàn |
| **Exception khi gửi** | Không mặc nhiên | Phân loại network, authentication, topology và bảo toàn event gốc |

### Retry đúng khi kết quả không rõ

Một lần publish có thể **đã vào queue** nhưng publisher mất connection trước khi nhận confirm. Nếu gửi lại, queue có thể nhận **hai bản** của cùng sự kiện.

Để bảo vệ nghiệp vụ:

1. Tạo **eventId** trước khi publish và **giữ nguyên** khi retry.
2. Lưu event/envelope trong **transactional outbox** nếu cần không mất sự kiện sau khi service crash.
3. Dùng **CorrelationData.id riêng cho từng publish attempt** để đối chiếu kết quả.
4. Consumer lưu khóa **(consumerName, eventId)** hoặc cơ chế idempotency tương đương **cùng transaction của side effect** khi có thể.
5. Không retry mù vô hạn lỗi **NO_ROUTE** khi topology chưa sửa; cảnh báo và đánh dấu trạng thái “routing failure”.

**Timeout không có nghĩa message chắc chắn chưa được broker nhận.** Retry có thể tạo bản sao. Confirm giảm trạng thái bất định; **idempotency** giúp ứng dụng chịu được bản sao còn lại.

### Tách trách nhiệm các thành phần

| Thành phần | Chịu trách nhiệm chính |
| --- | --- |
| **RabbitTemplate** | Publish đúng exchange, routing key, MessageProperties và CorrelationData |
| **Exchange + binding** | Quyết định queue nào nhận message |
| **Publisher confirms** | Xác nhận broker đã xử lý publish như thế nào |
| **Publisher returns** | Báo message không định tuyến được khi mandatory và điều kiện phù hợp |
| **Consumer ACK/NACK** | Xác nhận/không xác nhận xử lý một delivery |
| **Retry + dead-letter** | Điều khiển vòng đời message lỗi |
| **Transactional outbox + idempotency** | Giảm nguy cơ mất event và tác dụng phụ lặp khi gửi/giao lại |
| **Observability** | Tìm publish NACK, returns, backlog, DLQ và lỗi nghiệp vụ |

## 14. Publisher ACK khác consumer ACK và dead-letter

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant X as Exchange
    participant Q as Queue
    participant C as Consumer
    P->>X: Publish (routing key hợp lệ)
    X->>Q: Route message
    X-->>P: Publisher confirm ACK
    Q->>C: Deliver message
    C-->>Q: Consumer basic.ack khi xử lý xong
~~~

Publisher confirm và consumer ACK diễn ra ở **hai vai trò khác nhau**, thường trên channel khác nhau. Publisher không tự nhận consumer ACK chỉ vì đã bật **publisher-confirm-type: correlated**.

Message đã vào queue vẫn có thể:

- Bị consumer xử lý lỗi rồi **NACK/requeue**, dẫn đến redelivery.
- Bị **dead-letter** vì reject/nack không requeue, TTL hoặc các điều kiện queue khác.
- Nằm trong trạng thái **Ready** lâu khi consumer count bằng 0.
- Được consumer ACK dù side effect bên ngoài chưa hoàn tất nếu code ứng dụng xác nhận quá sớm.

Với yêu cầu nghiệp vụ quan trọng, cần theo dõi **eventId** từ publisher, broker, consumer đến kết quả xử lý thực tế. Không nên chỉ dựa vào ACK ở một tầng duy nhất.

## 15. Thực hành: tái hiện ACK nhưng không định tuyến được

Chuẩn bị RabbitMQ với plugin Management và ứng dụng Spring Boot theo các ví dụ ở phần 6–8.

### Bước 1. Kiểm tra topology

Trong RabbitMQ Management, xác nhận:

- Exchange **demo.orders.events** tồn tại, loại **direct**.
- Queue **demo.billing.orders** tồn tại.
- Binding từ exchange tới queue có routing key **order.created**.
- Không có binding cho **order.cancelled** và không cấu hình alternate exchange trong bài thực hành.

Nếu đã dùng broker cho các lab trước, có thể còn binding khác; hãy kiểm tra hoặc đặt bộ tên exchange/queue mới để kết quả có thể tái hiện.

### Bước 2. Publish routing key hợp lệ

Gửi **order.created** và quan sát log:

~~~text
PUBLISH_CONFIRMED_NO_RETURN eventId=... attemptId=...
~~~

Nếu chưa có consumer, queue **Ready** có thể tăng. Nếu listener đang chạy, message có thể được nhận và ACK rất nhanh khiến Ready về 0. **Ready=0 không tự chứng minh publish thất bại**.

### Bước 3. Publish routing key không có binding

Gửi **order.cancelled**. Khi bật mandatory và publisher returns, log thường là:

~~~text
PUBLISH_UNROUTABLE eventId=... attemptId=... reply=NO_ROUTE exchange=demo.orders.events routingKey=order.cancelled
~~~

Đây là ví dụ **return nhưng publisher confirm có thể ACK**. Message không xuất hiện trong queue Billing vì routing key không khớp.

### Bước 4. Tạm tắt mandatory, chỉ trong lab

Đổi thuộc tính:

~~~yaml
spring:
  rabbitmq:
    template:
      mandatory: false
~~~

Gửi lại **order.cancelled** với toàn bộ điều kiện khác giữ nguyên. Nếu không có alternate exchange, message vẫn không vào queue nhưng app có thể chỉ thấy:

~~~text
PUBLISH_CONFIRMED_NO_RETURN eventId=... attemptId=...
~~~

Đây là hiện tượng nguy hiểm: publisher thấy **ACK + không RETURN**, rồi có thể nhầm rằng việc giao đến queue đã thành công.

### Bước 5. Khôi phục cấu hình

Trả **template.mandatory=true** và bật lại cả confirms/returns sau khi kết thúc phép thử.

### Bước 6. So sánh với exchange thiếu

Chỉ trong lab, thử publish tới exchange chưa tồn tại. Kiểm tra channel exception và log lỗi; tình huống này **khác** message gửi đến exchange hợp lệ mà không có binding.

### Quan sát bằng RabbitMQ Management và CLI

Trong Docker Compose có service tên **rabbitmq**, có thể xem topology:

~~~bash
docker compose exec rabbitmq rabbitmqctl list_exchanges -p / name type
docker compose exec rabbitmq rabbitmqctl list_bindings -p /
docker compose exec rabbitmq rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers
~~~

Kết hợp kết quả **return callback của ứng dụng** với số liệu broker về publish/confirm/unroutable, queue Ready/Unacked và consumer count. Giao diện Management UI có thể biểu diễn kết quả publish thủ công khác với cách RabbitTemplate ghép confirm/return; để kiểm tra logic Java, ưu tiên chạy producer có **CorrelationData**.

## 16. Lỗi và ngộ nhận thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Confirm ACK nhưng queue không có message | Routing key sai, mandatory=false hoặc consumer đã lấy | Kiểm tra binding, returns, consumer, Ready/Unacked |
| Bật publisher returns nhưng không thấy return | **mandatory=false** hoặc message được route | Bật mandatory; dùng routing key thật sự không khớp |
| Bật mandatory nhưng không thấy callback | Chưa bật **publisher-returns** hoặc callback chưa đăng ký/đã bị thay thế | Kiểm tra template và connection factory thực |
| Có RETURN nhưng confirm ACK | Đúng ngữ nghĩa với unroutable mandatory publish | Phân loại **UNROUTABLE**, không coi ACK là thành công |
| Publish tới exchange thiếu mà mong NO_ROUTE | Exchange không tồn tại gây channel exception | Khai báo exchange; phân biệt lỗi topology và lỗi routing |
| ACK nhưng consumer không xử lý | Queue còn backlog, không có consumer hoặc consumer lỗi | Theo dõi listener, ACK, retry và DLQ |
| ACK + không RETURN, message vào queue khác | Alternate exchange hoặc binding không đúng ý định | Kiểm tra topology và queue fallback |
| Confirm chậm hoặc timeout | Broker tải cao, I/O lưu bền hoặc vấn đề kết nối | Đo lường latency, điều chỉnh timeout và retry giữ eventId |
| Retry publish tạo dữ liệu trùng | Broker đã nhận lần đầu nhưng confirm bị thất lạc | Outbox + idempotent consumer |
| Không ghép được confirm với event | Thiếu CorrelationData/attemptId hoặc log không đủ | Dùng ID attempt duy nhất và eventId ổn định |
| Callback quá chậm | Logic nặng đặt trên đường callback | Giữ callback nhẹ; chuyển công việc nặng sang worker |
| Mong transaction và confirms cùng hoạt động trên một channel | AMQP confirm mode và transaction mode không dùng đồng thời trên cùng channel | Chọn mô hình phù hợp và phân biệt cơ chế |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Publisher gửi tới direct exchange có tồn tại với routing key không khớp. **mandatory=false**, không alternate exchange. Publisher có thể nhận confirm ACK không?

**Câu 2.** Cũng tình huống đó nhưng **mandatory=true** và returns đã bật. Có thể vừa nhận RETURN vừa nhận confirm ACK không? Tín hiệu nào đến trước trên giao thức?

**Câu 3.** Một queue có binding đúng nhưng chưa có consumer. Message có bị return chỉ vì không có consumer không?

**Câu 4.** Với Spring Boot, ba thuộc tính nào cần bật để quan sát confirms/returns theo từng publish?

**Câu 5.** Vì sao **ACK + không RETURN** vẫn chưa chứng minh nghiệp vụ xử lý thành công?

**Câu 6.** Publisher retry cùng event sau timeout nhưng tạo CorrelationData.id mới. Định danh nào phải ổn định và consumer cần làm gì?

**Đáp án gợi ý:**

1. **Có.** Broker có thể ACK sau khi quyết định message không route tới queue; message bị loại khi mandatory=false và không có AE.
2. **Có.** Broker gửi **basic.return trước basic.ack** với unroutable mandatory publish.
3. **Không.** Queue có thể giữ message dù không có consumer.
4. **publisher-confirm-type: correlated**, **publisher-returns: true**, **template.mandatory: true**; đồng thời code đọc CorrelationData/callback.
5. Publisher confirm không phải consumer ACK; alternate exchange hoặc binding sai còn có thể đưa message tới queue không mong muốn.
6. Giữ **eventId/messageId logic** bất biến; dùng CorrelationData.id mới cho attempt và idempotency ở consumer.

## 18. Checklist trước khi triển khai

Hãy xác nhận:

1. Exchange, queue và binding đúng hợp đồng routing chưa?
2. Có **publisher-confirm-type: correlated** để xử lý kết quả theo message/attempt chưa?
3. Có **publisher-returns: true** và **template.mandatory: true** chưa?
4. Logic có phân biệt **ACK + RETURN**, **ACK + không RETURN**, **NACK**, **timeout**, **exception** chưa?
5. CorrelationData.id phân biệt được attempt, còn eventId giữ nguyên qua retry chưa?
6. Có alternate exchange/fallback queue cần theo dõi riêng không?
7. Có transactional outbox và idempotent consumer cho luồng quan trọng chưa?
8. Có giám sát publisher confirms, returns, unroutable rate, queue Ready/Unacked, consumer errors và DLQ chưa?
9. Gặp **NO_ROUTE** có cảnh báo sửa topology thay vì retry vô hạn không?
10. Đã thử routing key sai, exchange không tồn tại và queue không có consumer chưa?

**Kết luận:** **Message không định tuyến được vẫn có thể nhận publisher confirm ACK** vì ACK chỉ xác nhận broker đã xử lý publish, không phải bằng chứng có queue đích hoặc consumer hoàn tất. Để tránh im lặng mất message, cần dùng **mandatory + publisher returns** bên cạnh **publisher confirms**, rồi đọc đúng cả hai tín hiệu. Với **Spring AMQP**, hãy phối hợp **RabbitTemplate, CorrelationData, callbacks/future, exchange/queue/binding, retry có kiểm soát, idempotency và observability** để xây pipeline bất đồng bộ đáng tin cậy.

### Tài liệu đọc thêm

- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ – Publishers và Unroutable Message Handling](https://www.rabbitmq.com/docs/publishers)
- [Spring AMQP – Correlated Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html)
- [Spring Boot – AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html)
