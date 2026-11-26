# Kiểm chứng confirm, return và publish có kết quả chưa rõ

## 1. Bài toán thực hành: gửi message rồi phải kết luận như thế nào?

Trong **Spring AMQP**, producer dùng `RabbitTemplate` gửi sự kiện đến **exchange**; RabbitMQ định tuyến message theo **routing key và binding** vào **queue**; consumer xử lý bằng `@RabbitListener`. Với các luồng quan trọng như đơn hàng, thanh toán, giao hàng, một dòng code không ném exception **không đủ chứng minh** message đã đến đúng queue hoặc đã hoàn tất nghiệp vụ.

Ví dụ:

~~~java
rabbitTemplate.convertAndSend(
        "orders.events.x", "order.created", orderEvent);
// Không có exception: đã an toàn để đánh dấu DONE?
~~~

Câu trả lời là **chưa**. Có ít nhất bốn tình huống khác nhau:

1. Broker đã xác nhận publish **ACK**; message không bị trả về vì sai route.
2. Broker **ACK nhưng gửi return** vì không có queue nào khớp binding.
3. Broker hoặc framework báo **NACK/lỗi**, cho biết publish không được xác nhận thành công.
4. Client **không nhận được kết quả đủ rõ** trước deadline: mất kết nối, hết thời gian đợi, service crash hoặc callback đến muộn. Message **có thể đã tới broker hoặc chưa**.

Trong trường hợp (4), nếu producer đơn giản gửi lại với **eventId mới**, người tiêu thụ có thể xử lý hai lần. Nếu producer đơn giản bỏ qua, có thể bỏ sót tác vụ. Bài này xây một thí nghiệm có thể lặp lại để quan sát cả **confirm, return, unknown outcome** và cách khôi phục an toàn.

~~~text
             Producer / RabbitTemplate
                        |
            publish(exchange, routingKey)
                        |
                        v
                   RabbitMQ
                     /  \
                    /    \
         matching queue?  no matching queue
                |                  |
                v                  v
       route to queue(s)      basic.return (mandatory)
                |                  |
                +--------+---------+
                         |
                    basic.ack
                         |
                   CorrelationData
                     /       \
           getFuture()      getReturned()
               |                  |
               +---------+--------+
                         |
                  PublishOutcome
              (CONFIRMED / RETURNED /
                NACK / UNKNOWN)
                         |
                         v
                    Outbox state
                         |
                 Consumer @RabbitListener
                         |
                   business DB commit
                         |
                   consumer ACK
~~~

**Kết quả mong đợi:** tự chạy ba trường hợp xác định (ACK không return, ACK có return, NACK/error) và một trường hợp **không xác định** bằng deadline; lưu trạng thái producer chính xác, giữ business ID ổn định khi cần phát lại, và xác minh consumer xử lý idempotent.

> **Phạm vi:** đây là **RabbitMQ AMQP 0-9-1**, `RabbitTemplate` và `@RabbitListener`, không phải AMQP 1.0 generic ProtonJ2. Các ví dụ nhắm tới **Java 17+, Spring Boot 3.5.x, Spring AMQP 3.2.x, RabbitMQ 4.x**. Khi dùng Boot 4/Spring AMQP 4, cần chọn starter/API tương thích. Không đổi cấu hình exchange, queue và binding của hệ thống thật để làm thí nghiệm phá lỗi.

## 2. Ba loại “ACK” tuyệt đối không được gộp

| Tín hiệu | Ai phát ra? | Xác nhận điều gì? | Không xác nhận điều gì? |
| --- | --- | --- | --- |
| **Publisher confirm ACK** (`basic.ack` trên publisher confirm channel) | RabbitMQ → producer. | Broker đã xác nhận publish theo ngữ nghĩa confirms (với message routable, đã được các queue nhận theo điều kiện broker/queue type). | **Không xác nhận consumer đã chạy, DB đã commit**, cũng không tự khẳng định message không bị return. |
| **Publisher return** (`basic.return` khi `mandatory=true`) | RabbitMQ → producer. | Publish không định tuyến được tới queue phù hợp theo cơ chế mandatory, sau khi broker xét route. | **Không phải** consumer NACK và không phải lỗi schema trong `@RabbitListener`. |
| **Consumer ACK** (`basic.ack` trên consumer channel) | Consumer/container → RabbitMQ. | Consumer chấp nhận delivery để broker không giao lại physical message đó. | Không xác nhận độc lập các tác vụ downstream bất đồng bộ đã hoàn tất, nếu ứng dụng ACK sớm. |

**Câu cần nhớ:** một **publisher confirm ACK** có thể đi cùng **publisher return**. Với RabbitMQ, khi exchange tồn tại nhưng không route được message mandatory tới queue nào, broker gửi **`basic.return` trước `basic.ack`**. Vì vậy chỉ kiểm tra `confirm.isAck()` rồi đánh dấu `ROUTED` là **sai**.

### 2.1. Bảng quyết định ở phía producer

| `CorrelationData.getFuture()` | `CorrelationData.getReturned()` | Trạng thái bài học | Hành động |
| --- | --- | --- | --- |
| Hoàn tất với `ack=true` | `null` | **CONFIRMED_NO_RETURN** | Ghi broker publish accepted theo bằng chứng có sẵn; **chưa đánh dấu nghiệp vụ DONE**. |
| Hoàn tất với `ack=true` | Có `ReturnedMessage` | **RETURNED** | Kiểm tra exchange/binding/routing key/vhost, sửa route, sau đó retry có kiểm soát. |
| Hoàn tất với `ack=false` | Có hoặc không | **NACK** | Lưu reason/cause nếu có, xem broker/channel; có thể cần đối soát tùy thời điểm và lỗi. |
| Future lỗi hoặc chưa hoàn tất trước deadline | Chưa có kết quả đủ rõ | **UNKNOWN** | Không coi là mất; giữ outbox, đối soát và retry cùng business event ID khi an toàn. |
| `send()` ném exception trước/đang gửi | Chưa rõ message có đi ra socket không | **UNKNOWN** hoặc lỗi local đã chứng minh chưa publish | Phân biệt lỗi validate local với lỗi transport; không tự coi exception = broker chưa nhận. |

**CONFIRMED_NO_RETURN** là tên *thận trọng*: khi cấu hình đúng `mandatory` + `publisher-returns`, nó cho biết không có mandatory return tương ứng trước confirm. Nhưng **alternate exchange**, route sang queue khác, consumer không hoạt động, queue TTL/DLX, hoặc lỗi sau đó vẫn có thể làm kết quả nghiệp vụ khác mong muốn. Không ghi trạng thái `PROCESSED` từ confirm.

**NACK** là kết quả âm, không phải trạng thái UNKNOWN do timeout. Tuy nhiên nếu framework phát NACK khi channel/connection đóng, chi tiết timeline vẫn có thể không đủ để khẳng định mọi hiệu ứng broker đã hoặc chưa xảy ra. Thiết kế **at-least-once + idempotency** vẫn cần thiết.

### 2.2. Khi nào publisher return không xuất hiện?

Các trường hợp điển hình:

- `mandatory=false` (mặc định thường gặp), broker có thể loại bỏ message unroutable mà không return.
- `publisher-returns=false` hoặc template không xử lý return đúng cách.
- Publish tới **exchange không tồn tại**: broker thường đóng channel với lỗi `NOT_FOUND`, **không gửi `basic.return`** theo trường hợp no-binding.
- Exchange có **alternate exchange** và message được alternate exchange route thành công; không nhất thiết return tới producer.
- Message thực sự đã được route vào queue nhưng consumer về sau throw/ACK sai/DLQ: đó là vấn đề **sau routing**, không phải publisher return.

**Không nhầm publisher return với dead-letter queue.** DLQ nhận message khi broker dead-letter một delivery từ queue (reject/no-requeue, TTL, queue length, quorum limit...) theo cấu hình. Return diễn ra **ở giai đoạn publish tới exchange**, trước khi consumer xử lý.

## 3. Thiết kế lab: topology có thể chứng minh từng trạng thái

Ta tạo một exchange direct bền vững và **hai queue**:

~~~text
                         Exchange (direct)
                         orders.events.x
                               |
                 +-------------+-------------+
                 |                           |
            key=order.created          key=order.queued
                 |                           |
                 v                           v
           orders.work.q              orders.parked.q
                 |                           |
                 v                           |
           @RabbitListener              KHÔNG có listener
                 |
            store eventId
~~~

Ba routing key thí nghiệm:

| Publish | Binding hiện có | Kết quả dự kiến |
| --- | --- | --- |
| `order.created` | Có, dẫn tới `orders.work.q`. | Confirm ACK + không return; listener được gọi. |
| `order.queued` | Có, dẫn tới `orders.parked.q`, **không listener**. | Confirm ACK + không return, nhưng **không có business processing**. |
| `order.no-binding` | Không có binding. | Với `mandatory=true`: **return** (thường mã 312 `NO_ROUTE`) rồi confirm ACK. |

Với exchange **không tồn tại**, thực hiện **thí nghiệm riêng** vì broker có thể đóng channel và ảnh hưởng các publish khác trong cùng phiên test.

Các resource `orders.events.x` và queue trong bài chỉ phục vụ lab; khi triển khai thật, chọn tên theo convention, quản lý permission và topology qua IaC/RabbitAdmin đúng môi trường.

## 4. Khởi tạo dự án và dependency

### 4.1. Spring Boot 3.5.x / Spring AMQP 3.2.x

Một ứng dụng Spring Boot có thể dùng các dependency sau (version do Spring Boot BOM quản lý):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>rabbitmq</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu dùng Spring Boot 4.x, tên starter cho RabbitMQ AMQP 0-9-1 là `spring-boot-starter-rabbitmq`; không copy nguyên dependency Boot 3.x sang 4.x mà chưa kiểm tra BOM. `ObjectMapper`/Jackson cũng cần chỉnh theo dòng JSON library.

### 4.2. Cấu hình confirm, return và mandatory

~~~yaml
# application.yml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: ${RABBITMQ_USERNAME:guest}
    password: ${RABBITMQ_PASSWORD:guest}
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false
~~~

**Ba key không thể thiếu** đối với phép kiểm thử:

- `spring.rabbitmq.publisher-confirm-type=correlated`: cấu hình `CachingConnectionFactory.ConfirmType.CORRELATED`, cho phép kết nối confirm về đúng `CorrelationData`.
- `spring.rabbitmq.publisher-returns=true`: nhận publisher returns.
- `spring.rabbitmq.template.mandatory=true`: yêu cầu broker trả message **không định tuyến được**.

**Phải bật đủ cả ba.** Nếu chỉ đặt `mandatory=true` nhưng không bật returns hoặc nếu dùng factory không hỗ trợ confirm, kết quả test dễ bị đọc sai. Nếu tự khai báo `RabbitTemplate` hay `CachingConnectionFactory` riêng thay vì dùng Boot auto-configuration, phải cấu hình các thuộc tính tương ứng trên đúng bean được dùng.

`default-requeue-rejected=false` là chính sách consumer ví dụ: không requeue vô hạn khi listener lỗi. Nó **không cấu hình DLQ** và không liên quan trực tiếp đến publisher return; trong lab này không cố tình ném exception từ listener.

**Chỉ dùng `guest/guest` cho môi trường RabbitMQ local mặc định**, không dùng khi kết nối từ service ngoài host hoặc production. Production cần tài khoản riêng, TLS và permissions tối thiểu.

### 4.3. Chạy RabbitMQ local (tùy chọn)

Khi chạy thủ công bằng Docker:

~~~bash
docker run --rm --name spring-amqp-confirm-lab \
  -p 5672:5672 -p 15672:15672 rabbitmq:4.1-management
~~~

RabbitMQ Management UI thường có tại `http://localhost:15672`, dùng tài khoản của broker test. Nếu đang có RabbitMQ tại cổng 5672/15672, dùng port khác và cập nhật `application.yml`.

**Trong kiểm thử tự động**, ưu tiên **Testcontainers** để khởi động broker riêng, không phụ thuộc vào local port và không dùng tài nguyên production. Mục 10 trình bày test theo cách này.

## 5. Khai báo exchange, queues và bindings bằng Spring AMQP

~~~java
// OrderConfirmTopology.java
package example.confirm;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderConfirmTopology {
    public static final String EXCHANGE = "orders.events.x";
    public static final String WORK_QUEUE = "orders.work.q";
    public static final String PARKED_QUEUE = "orders.parked.q";
    public static final String WORK_KEY = "order.created";
    public static final String PARKED_KEY = "order.queued";
    public static final String MISSING_KEY = "order.no-binding";

    @Bean
    Declarables confirmLabDeclarables() {
        DirectExchange exchange = new DirectExchange(EXCHANGE, true, false);
        Queue work = QueueBuilder.durable(WORK_QUEUE).build();
        Queue parked = QueueBuilder.durable(PARKED_QUEUE).build();
        Binding toWork = BindingBuilder.bind(work)
                .to(exchange).with(WORK_KEY);
        Binding toParked = BindingBuilder.bind(parked)
                .to(exchange).with(PARKED_KEY);
        return new Declarables(exchange, work, parked, toWork, toParked);
    }
}
~~~

`DirectExchange` so khớp routing key **chính xác**. Trong topology trên không có binding nào tới `MISSING_KEY`, nên publish mandatory tới key này là cách chủ động kiểm tra publisher return.

**Điều kiện triển khai:** Spring Boot có thể tạo `RabbitAdmin` và khai báo các `Declarables` khi kết nối broker. Nếu queue/exchange đã tồn tại với arguments không tương thích, RabbitMQ có thể báo `PRECONDITION_FAILED`; không xóa queue thật để làm lab.

### 5.1. DTO sự kiện và quy ước correlation

~~~java
// OrderCreated.java
package example.confirm;

public record OrderCreated(
        String eventId,
        String orderId,
        long occurredAtEpochMillis) {
}
~~~

Chúng ta dùng **hai ID khác nhau**:

| ID | Tồn tại trong | Ý nghĩa | Khi retry |
| --- | --- | --- | --- |
| `eventId` | Business payload, `MessageProperties.messageId`, outbox. | Xác định **một sự kiện nghiệp vụ**. | **Giữ nguyên** nếu đó là cùng sự kiện. |
| `attemptId` | `CorrelationData.id`, log/outbox attempt. | Xác định **một lần publish vật lý**. | **Tạo mới** cho mỗi attempt, kể cả khi eventId không đổi. |

Với `CorrelationData`, ID duy nhất của mỗi attempt đặc biệt quan trọng khi bật returns để Spring gắn `basic.return` với publish tương ứng. Không nên dùng cùng một correlation ID cho hai publish **đang bay đồng thời** chỉ vì có chung business eventId.

## 6. Xây Publisher phân loại ACK, RETURNED, NACK và UNKNOWN

### 6.1. Định nghĩa trạng thái xuất bản

Để log và ghi outbox không nhầm lẫn, định nghĩa enum trạng thái **theo bằng chứng về publish**, không dùng một boolean `success` chung cho tất cả các bước:

~~~java
// PublishState.java
package example.confirm;

public enum PublishState {
    CONFIRMED_NO_RETURN,
    RETURNED,
    NACK,
    UNKNOWN
}
~~~

~~~java
// PublishResult.java
package example.confirm;

public record PublishResult(
        String eventId,
        String attemptId,
        PublishState state,
        String detail) {
}
~~~

~~~java
// PublishAttempt.java
package example.confirm;

import java.util.concurrent.CompletableFuture;

public record PublishAttempt(
        String eventId,
        String attemptId,
        CompletableFuture<PublishResult> completion) {
}
~~~

`PublishAttempt` giữ future **để có thể nhận kết quả đến muộn** sau deadline. Một lần chờ bị timeout **không được xóa business event** khỏi outbox hay hủy một phép publish đã bắt đầu.

### 6.2. Publisher dùng CorrelationData cho từng attempt

~~~java
// ConfirmAwarePublisher.java
package example.confirm;

import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.core.ReturnedMessage;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ConfirmAwarePublisher {
    private final RabbitTemplate template;
    private final ObjectMapper mapper;

    public ConfirmAwarePublisher(RabbitTemplate template, ObjectMapper mapper) {
        this.template = template;
        this.mapper = mapper;
    }

    public PublishAttempt publish(String routingKey, OrderCreated event)
            throws JsonProcessingException {
        return publish(routingKey, event, UUID.randomUUID().toString());
    }

    // Dispatcher outbox có thể tạo và ghi bền vững attemptId TRƯỚC send.
    public PublishAttempt publish(
            String routingKey, OrderCreated event, String attemptId)
            throws JsonProcessingException {

        Objects.requireNonNull(routingKey, "routingKey");
        Objects.requireNonNull(event, "event");
        if (attemptId == null || attemptId.isBlank()) {
            throw new IllegalArgumentException("attemptId is required");
        }
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }

        // Local serialization xảy ra TRƯỚC send.
        // Nếu lỗi JSON tại đây, chưa bắt đầu publish attempt.
        byte[] json = mapper.writeValueAsBytes(event);

        MessageProperties props = new MessageProperties();
        props.setContentType("application/json");
        props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        props.setMessageId(event.eventId());

        Message message = new Message(json, props);

        // Một eventId có thể có nhiều attempts; correlation ID phải riêng.
        // Trong production, attemptId được persist trước khi gọi hàm này.
        CorrelationData correlation = new CorrelationData(attemptId);
        CompletableFuture<PublishResult> completion =
                new CompletableFuture<>();

        // Đăng ký callback trước send để không bỏ lỡ confirm nhanh.
        correlation.getFuture().whenComplete((confirm, error) ->
                completion.complete(classify(
                        event.eventId(), attemptId, correlation,
                        confirm, error)));

        try {
            template.send(
                    OrderConfirmTopology.EXCHANGE,
                    routingKey,
                    message,
                    correlation);
        } catch (AmqpException sendError) {
            // Lỗi transport/channel có thể xảy ra trước hoặc sau khi
            // một số byte đã đến broker. Chọn UNKNOWN bảo thủ.
            completion.complete(new PublishResult(
                    event.eventId(),
                    attemptId,
                    PublishState.UNKNOWN,
                    "send_exception:" + sendError.getClass().getSimpleName()));
        }

        return new PublishAttempt(event.eventId(), attemptId, completion);
    }

    static PublishResult classify(
            String eventId,
            String attemptId,
            CorrelationData correlation,
            CorrelationData.Confirm confirm,
            Throwable error) {

        if (error != null || confirm == null) {
            return new PublishResult(
                    eventId, attemptId, PublishState.UNKNOWN,
                    "confirm_future_error_or_missing");
        }

        // Xem NACK trước. Lý do có thể rỗng đối với broker NACK.
        if (!confirm.isAck()) {
            return new PublishResult(
                    eventId, attemptId, PublishState.NACK,
                    "confirm_nack:" + String.valueOf(confirm.getReason()));
        }

        ReturnedMessage returned = correlation.getReturned();
        if (returned != null) {
            return new PublishResult(
                    eventId, attemptId, PublishState.RETURNED,
                    "return_code=" + returned.getReplyCode()
                            + ",reason=" + returned.getReplyText()
                            + ",routingKey=" + returned.getRoutingKey());
        }

        return new PublishResult(
                eventId, attemptId, PublishState.CONFIRMED_NO_RETURN,
                "broker_confirm_ack_without_return");
    }
}
~~~

Đây là mã **phân loại publish outcome**, không phải một producer transactional outbox hoàn chỉnh. Trong ứng dụng production, handler của `completion` phải cập nhật bảng outbox/publish attempts có điều kiện, ghi log và metric, hạn chế callback làm tác vụ chặn lâu.

**Giải thích những điểm dễ bỏ sót:**

1. **Serialize trước send:** lỗi `JsonProcessingException` là lỗi local, không phải trạng thái UNKNOWN do mất confirm. Ứng dụng có thể từ chối message không hợp lệ trước khi tạo attempt.
2. **Correlation ID khác event ID:** mỗi lần publish có `attemptId` mới; vẫn giữ `eventId` gốc trong payload và AMQP message properties.
3. **Callback đăng ký trước send:** nếu broker trả confirm rất nhanh, future vẫn được xử lý đúng; cũng có thể đăng ký sau vì `CompletableFuture` nhớ kết quả, nhưng trước send giúp code rõ lifecycle.
4. **Ưu tiên NACK:** nếu confirm báo NACK, không gán trạng thái thành công chỉ vì tình cờ có một return; cần giữ cả metadata trong log khi điều tra case đặc biệt.
5. **Kiểm tra return sau ACK:** tài liệu Spring AMQP bảo đảm `CorrelationData.getReturned()` được điền **trước khi confirm future hoàn tất** khi confirms/returns hoạt động đúng, nên đoạn `classify` có thể đọc cả hai cùng lúc.
6. **Synchronous send exception:** một exception transport không luôn chứng minh broker chưa từng nhận byte; trạng thái bảo thủ là `UNKNOWN`. Nếu lỗi local chắc chắn chưa gửi (validation/serialization), xử lý trước `template.send` và **không** ghi publish attempt.
7. **Không tự log message body:** returned message có thể chứa payload nhạy cảm; hãy chỉ ghi mã phản hồi, exchange, routing key có giới hạn và correlation ID, không dump `ReturnedMessage.getMessage()`.

### 6.3. Vì sao không chỉ dùng ConfirmCallback?

Bạn cũng có thể đăng ký:

~~~java
template.setConfirmCallback((correlation, ack, cause) -> {
    // Được gọi khi producer nhận publisher confirm.
});
template.setReturnsCallback(returned -> {
    // Được gọi khi mandatory message không routable.
});
~~~

Đây là API hợp lệ, nhưng **mỗi RabbitTemplate chỉ hỗ trợ một `ConfirmCallback` và một `ReturnsCallback`**. Nhiều module cùng gọi setter có thể ghi đè nhau. Với một publish cần correlation chính xác, `CorrelationData.getFuture()` + `getReturned()` thường tiện hơn, trong khi template-level callbacks có thể phục vụ ghi log/metrics tập trung nếu phối hợp đúng.

**Không làm việc nặng hoặc block hàng chục giây trong return callback.** Spring AMQP bảo đảm return được đưa vào correlation trước confirm với điều kiện xử lý return callback kết thúc trong cửa sổ thời gian được tài liệu nêu (**60 giây** trong Spring AMQP 3.2). Một callback chậm làm khó quan sát và có thể trì hoãn confirm.

### 6.4. Chờ kết quả có deadline nhưng không hủy future gốc

Ở CLI/test, ta có thể chờ một thời gian hữu hạn:

~~~java
// PublishOutcomeWaiter.java
package example.confirm;

import java.time.Duration;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class PublishOutcomeWaiter {
    private PublishOutcomeWaiter() {
    }

    public static PublishResult await(
            PublishAttempt attempt, Duration deadline) {
        try {
            return attempt.completion().get(
                    deadline.toMillis(), TimeUnit.MILLISECONDS);
        } catch (TimeoutException timeout) {
            return unknown(attempt, "deadline_elapsed");
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return unknown(attempt, "waiting_thread_interrupted");
        } catch (ExecutionException | CancellationException error) {
            return unknown(attempt, "completion_failed");
        }
    }

    private static PublishResult unknown(
            PublishAttempt attempt, String reason) {
        return new PublishResult(
                attempt.eventId(),
                attempt.attemptId(),
                PublishState.UNKNOWN,
                reason);
    }
}
~~~

**Lợi thế của `Future.get(timeout)`:** khi deadline hết, nó **không tự hủy hoặc hoàn tất** `attempt.completion()`. Nếu confirm đến sau, future vẫn có thể chuyển sang kết quả cuối. Điều này quan trọng cho reconciliation. Khi dùng `CompletableFuture.orTimeout(...)` **trực tiếp trên future gốc**, bạn có thể làm nó hoàn tất với timeout exception và **mất khả năng ghi kết quả confirm đến muộn** thông qua future đó.

`await` **chặn thread** và chỉ dành cho demo/CLI/test hoặc dispatcher có ngân sách thread rõ. Trong HTTP reactive/event loop không nên block request thread; thay bằng nonblocking stage và scheduled deadline riêng, vẫn lưu trạng thái UNKNOWN vào hệ thống bền vững.

**Kết quả UNKNOWN là phát biểu về mức hiểu biết tại deadline**, không phải chứng minh publish thất bại hoặc queue đã mất message.

## 7. Consumer quan sát và xác minh điểm dừng của publisher confirm

Ta thêm listener để chứng minh **phần publish và phần xử lý consumer là hai giai đoạn tách biệt**:

~~~java
// OrderListenerProbe.java
package example.confirm;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListenerProbe {
    private final ObjectMapper mapper;
    private final BlockingQueue<String> observedEventIds =
            new LinkedBlockingQueue<>();

    public OrderListenerProbe(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @RabbitListener(
        id = "confirmedOrdersListener",
        queues = OrderConfirmTopology.WORK_QUEUE
    )
    public void onOrderCreated(Message message) throws IOException {
        OrderCreated order = mapper.readValue(
                message.getBody(), OrderCreated.class);
        observedEventIds.offer(order.eventId());
    }

    public String awaitEvent(Duration timeout) throws InterruptedException {
        return observedEventIds.poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

`LinkedBlockingQueue` ở đây **chỉ để quan sát trong test**. Nó không thay thế database transaction và không cung cấp idempotency bền vững; nếu listener return, container thường ACK delivery, dù bản ghi trong `observedEventIds` mất khi ứng dụng restart.

**Đừng dùng prototype này trong production để phát biểu “đơn hàng hoàn tất”.** Trong luồng thực, listener phải validate, ghi inbox `eventId` cùng transaction nghiệp vụ, đảm bảo side effect đã commit trước ACK (hoặc dùng một workflow có cơ chế phục hồi tương đương).

### 7.1. Spring Boot application

~~~java
// ConfirmLabApplication.java
package example.confirm;

import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableRabbit
public class ConfirmLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfirmLabApplication.class, args);
    }
}
~~~

Đặt các lớp Java trong package `example.confirm` như phần chú thích và cấu hình Maven/Gradle theo cách xây dựng ứng dụng Spring Boot thông thường. `OrderConfirmTopology` sẽ được scan và các resource được RabbitAdmin khai báo nếu auto-configuration/permissions phù hợp.

## 8. Thực nghiệm bằng tay: 4 kết quả khác nhau

### 8.1. Case A — Confirm ACK và không return

~~~java
OrderCreated event = new OrderCreated(
        "evt-created-1001", "ORDER-1001", System.currentTimeMillis());

PublishAttempt attempt =
        publisher.publish(OrderConfirmTopology.WORK_KEY, event);
PublishResult outcome =
        PublishOutcomeWaiter.await(attempt, Duration.ofSeconds(10));

System.out.println(outcome);
~~~

Kỳ vọng:

~~~text
state=CONFIRMED_NO_RETURN
detail=broker_confirm_ack_without_return
~~~

Sau đó xác minh listener:

~~~java
String consumed = probe.awaitEvent(Duration.ofSeconds(10));
assert "evt-created-1001".equals(consumed);
~~~

**Giải thích:** confirm ở producer cho biết broker xác nhận publish; listener test chứng minh một consumer method nhận event. Nếu bỏ bước chờ listener, bạn **không thể kết luận** consumer đã chạy chỉ từ confirm.

### 8.2. Case B — Confirm ACK nhưng publisher return

~~~java
OrderCreated event = new OrderCreated(
        "evt-unroutable-1002", "ORDER-1002", System.currentTimeMillis());

PublishAttempt attempt =
        publisher.publish(OrderConfirmTopology.MISSING_KEY, event);
PublishResult outcome =
        PublishOutcomeWaiter.await(attempt, Duration.ofSeconds(10));

System.out.println(outcome);
~~~

Kỳ vọng:

~~~text
state=RETURNED
detail=return_code=312,reason=NO_ROUTE,routingKey=order.no-binding
~~~

RabbitMQ vẫn thường gửi **publisher confirm ACK**, vì exchange đã xử lý publish và xác định không có route; nhưng `mandatory=true` làm broker trả message, Spring đặt `ReturnedMessage` vào `CorrelationData` trước khi future ACK hoàn tất.

**Điều cần kiểm chứng:** không có queue nào mang message này; đây là lỗi định tuyến, **không phải lỗi listener**. Nếu bạn đang sử dụng alternate exchange, kết quả có thể khác vì message có thể đã được AE route.

### 8.3. Case C — Confirm ACK trong khi không có listener

~~~java
OrderCreated event = new OrderCreated(
        "evt-parked-1003", "ORDER-1003", System.currentTimeMillis());
PublishAttempt attempt =
        publisher.publish(OrderConfirmTopology.PARKED_KEY, event);
PublishResult outcome =
        PublishOutcomeWaiter.await(attempt, Duration.ofSeconds(10));
~~~

Kỳ vọng `CONFIRMED_NO_RETURN`. Tuy nhiên, `orders.parked.q` không có `@RabbitListener`, nên event chỉ được **lưu trong queue** chờ người tiêu thụ. Đây là cách trực quan chứng minh **publisher confirm không phải consumer ACK**.

Có thể dùng RabbitMQ Management xem `messages_ready` tăng. Trên broker demo riêng, có thể nhận thử:

~~~java
Message queued = rabbitTemplate.receive(
        OrderConfirmTopology.PARKED_QUEUE, 5000);
assert queued != null;
~~~

`RabbitTemplate.receive` **lấy/ACK message theo chế độ phù hợp**, nên **chỉ làm trên queue test**; không dùng polling để “xem thử” queue production rồi vô tình xóa delivery.

### 8.4. Case D — Không có kết quả đủ rõ trước deadline

Case này **không nên dùng broker crash tùy thời điểm để tạo test unit ổn định**, vì khả năng nhận confirm tùy lịch CPU/network. Ta mô phỏng một future chưa hoàn tất rồi kiểm tra **quy tắc phân loại**:

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<PublishResult> pending = new CompletableFuture<>();
PublishAttempt attempt = new PublishAttempt(
        "evt-unknown-1004", "attempt-1004", pending);

PublishResult byDeadline =
        PublishOutcomeWaiter.await(attempt, Duration.ofMillis(20));

assert byDeadline.state() == PublishState.UNKNOWN;
assert !pending.isDone();

// Sau deadline, có thể nhận bằng chứng đến muộn:
pending.complete(new PublishResult(
        "evt-unknown-1004", "attempt-1004",
        PublishState.CONFIRMED_NO_RETURN, "late_confirm"));
assert pending.join().state() == PublishState.CONFIRMED_NO_RETURN;
~~~

Case D chứng minh **logic xử lý unknown** một cách deterministic. Trong thực tế, broker restart, channel shutdown, network partition, ứng dụng quá tải hoặc deadline quá ngắn cũng có thể khiến caller chưa thấy kết quả dù broker đã nhận message.

**Không dùng `Thread.sleep` rồi kill RabbitMQ giữa mọi test chỉ để “ép UNKNOWN”**: điều kiện race khó lặp lại và dễ làm hỏng các test khác. Phần chaos test có kiểm soát ở mục 12 sẽ kiểm tra hành vi thực khi mất kết nối.

## 9. Testcontainers: kiểm chứng routing/confirm/return trên broker thật

Unit test thuần Java không chứng minh RabbitMQ đã thực sự gửi `basic.return` trước `basic.ack`. Để kiểm tra điều đó, chạy integration test với **RabbitMQ Testcontainers** và cấu hình **Spring Boot `@ServiceConnection`**.

### 9.1. Integration test hoàn chỉnh

~~~java
// ConfirmLabIntegrationTest.java
package example.confirm;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest(
    classes = ConfirmLabApplication.class,
    properties = {
        "spring.rabbitmq.publisher-confirm-type=correlated",
        "spring.rabbitmq.publisher-returns=true",
        "spring.rabbitmq.template.mandatory=true"
    }
)
class ConfirmLabIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4.1-management");

    @Autowired
    ConfirmAwarePublisher publisher;

    @Autowired
    OrderListenerProbe probe;

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Test
    void matchingBindingConfirmsAndListenerReceives() throws Exception {
        OrderCreated event = new OrderCreated(
                "evt-ok-2001", "ORDER-2001", System.currentTimeMillis());

        PublishAttempt attempt =
                publisher.publish(OrderConfirmTopology.WORK_KEY, event);
        PublishResult result =
                PublishOutcomeWaiter.await(attempt, Duration.ofSeconds(10));

        assertEquals(PublishState.CONFIRMED_NO_RETURN, result.state());
        assertEquals(event.eventId(),
                probe.awaitEvent(Duration.ofSeconds(10)));
    }

    @Test
    void missingBindingGetsReturnEvenWhenPublisherIsAcked()
            throws Exception {

        OrderCreated event = new OrderCreated(
                "evt-return-2002", "ORDER-2002",
                System.currentTimeMillis());
        PublishAttempt attempt =
                publisher.publish(OrderConfirmTopology.MISSING_KEY, event);

        PublishResult result =
                PublishOutcomeWaiter.await(attempt, Duration.ofSeconds(10));

        assertEquals(PublishState.RETURNED, result.state());
        assertTrue(result.detail().contains("return_code=312"));
        assertTrue(result.detail().contains("order.no-binding"));
    }

    @Test
    void acceptedByQueueDoesNotMeanBusinessListenerRan()
            throws Exception {

        OrderCreated event = new OrderCreated(
                "evt-parked-2003", "ORDER-2003",
                System.currentTimeMillis());
        PublishAttempt attempt =
                publisher.publish(OrderConfirmTopology.PARKED_KEY, event);

        PublishResult result =
                PublishOutcomeWaiter.await(attempt, Duration.ofSeconds(10));

        assertEquals(PublishState.CONFIRMED_NO_RETURN, result.state());

        // Parked queue không có business @RabbitListener.
        // Test tự poll để xác minh message đã được broker lưu.
        Message stored = rabbitTemplate.receive(
                OrderConfirmTopology.PARKED_QUEUE, 5_000);
        assertNotNull(stored);
        assertEquals(event.eventId(),
                stored.getMessageProperties().getMessageId());
    }
}
~~~

**Điều kiện:** Docker/Testcontainers khả dụng; Spring Boot 3.1+ có `spring-boot-testcontainers` và `@ServiceConnection`. Các lớp từ mục 5–7 nằm trong `example.confirm` để `@SpringBootApplication` scan được; code ở `src/test/java` chỉ chứa test. Testcontainers cung cấp connection details cho RabbitMQ container, không cần hard-code cổng 5672 trong test.

**Vì sao test ổn định hơn việc gọi `Thread.sleep`?** Các phép chờ dùng **future confirm có deadline** và **queue listener có timed poll**. Test không suy đoán broker sẽ mất đúng 100 ms hay consumer sẽ start xong trong một số mili giây cố định.

**Nếu test `RETURNED` bị `CONFIRMED_NO_RETURN`:** kiểm tra:

- `spring.rabbitmq.publisher-returns` đã bật trên **CachingConnectionFactory thực sự được inject**.
- `mandatory=true` được đặt trên **RabbitTemplate thực sự gọi send**.
- `CorrelationData.id` riêng cho mỗi attempt.
- `orders.events.x` đúng là direct exchange và **không có binding `order.no-binding`**.
- Exchange có alternate exchange đang route message thay thế hay không.
- Spring Boot có một custom `RabbitTemplate` bean bỏ qua cấu hình `template.mandatory` không.

Nếu test `CONFIRMED_NO_RETURN` nhưng không thấy listener event: kiểm tra queue/binding/consumer, converter và startup lỗi của `@RabbitListener`; đừng tự kết luận publisher confirm sai.

### 9.2. Test riêng UNKNOWN: không đòi broker crash

~~~java
// PublishOutcomeWaiterTest.java
package example.confirm;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PublishOutcomeWaiterTest {

    @Test
    void noConfirmBeforeDeadlineIsUnknownNotNack() {
        CompletableFuture<PublishResult> actual =
                new CompletableFuture<>();
        PublishAttempt attempt =
                new PublishAttempt("evt-3001", "attempt-A", actual);

        PublishResult snapshot =
                PublishOutcomeWaiter.await(attempt, Duration.ofMillis(20));

        assertEquals(PublishState.UNKNOWN, snapshot.state());
        assertFalse(actual.isDone());

        // Một ACK có thể đến MUỘN sau khi caller ghi UNKNOWN.
        actual.complete(new PublishResult(
                "evt-3001", "attempt-A",
                PublishState.CONFIRMED_NO_RETURN, "late-ack"));

        assertEquals(PublishState.CONFIRMED_NO_RETURN,
                actual.join().state());
    }
}
~~~

**Ý nghĩa:** deadline của ứng dụng và confirm từ broker **không phải cùng một đồng hồ**. Caller có thể báo UNKNOWN trong khi broker đã nhận message và đang gửi ACK, hoặc ACK đến sau. Nếu hệ thống dùng database/outbox, cần cập nhật bằng chứng đến muộn **theo attemptId** và theo trạng thái chuyển hợp lệ.

### 9.3. Test riêng NACK classifier

Broker NACK thực tế không dễ ép theo cách deterministic; nó thường liên quan lỗi nội bộ và các sự cố channel. **Không tạo lỗi mạng hủy hoại để chỉ kiểm tra một nhánh `if (!confirm.isAck())`**. Dùng unit test:

~~~java
// ConfirmAwarePublisherClassificationTest.java
package example.confirm;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.connection.CorrelationData;

import static org.junit.jupiter.api.Assertions.*;

class ConfirmAwarePublisherClassificationTest {

    @Test
    void brokerNackIsNotSuccess() {
        CorrelationData correlation = new CorrelationData("attempt-B");
        CorrelationData.Confirm simulatedNack =
                new CorrelationData.Confirm(false, "simulated-failure");

        PublishResult result = ConfirmAwarePublisher.classify(
                "evt-3002", "attempt-B", correlation,
                simulatedNack, null);

        assertEquals(PublishState.NACK, result.state());
        assertTrue(result.detail().contains("simulated-failure"));
    }

    @Test
    void futureExceptionDoesNotProveMessageWasLost() {
        PublishResult result = ConfirmAwarePublisher.classify(
                "evt-3003",
                "attempt-C",
                new CorrelationData("attempt-C"),
                null,
                new IllegalStateException("connection interrupted"));

        assertEquals(PublishState.UNKNOWN, result.state());
    }
}
~~~

Phép thử NACK này **mô phỏng callback** để xác nhận logic ứng dụng, **không chứng minh RabbitMQ sẽ NACK với mọi lỗi**. Thí nghiệm publisher return ở mục 9.1 mới là phép kiểm tra broker thật.

### 9.4. Case exchange không tồn tại: thí nghiệm cô lập

Publish tới một **exchange không tồn tại** khác với publish tới exchange tồn tại nhưng không có binding:

~~~java
// Chỉ chạy ở BROKER TEST riêng; không chạy trong cùng bộ test
// đang kiểm tra các publish khác nếu không kiểm soát channel.
CorrelationData correlation = new CorrelationData("attempt-missing-ex");
rabbitTemplate.send(
        "orders.exchange.does-not-exist",
        OrderConfirmTopology.WORK_KEY,
        new Message("test".getBytes(java.nio.charset.StandardCharsets.UTF_8)),
        correlation);
~~~

RabbitMQ sẽ báo **channel exception**, thường `404 NOT_FOUND`, rồi đóng channel; **không có `basic.return` cho trường hợp exchange không tồn tại**. Tùy timing, API send có thể ném exception, hoặc correlation future nhận NACK/lỗi do framework xử lý; **không assert cố định mọi phiên bản đều nhận đúng một kiểu Java exception**.

Trong lab chính, `ConfirmAwarePublisher` khóa exchange name thành `orders.events.x`, nên đoạn này phải dùng `RabbitTemplate` trực tiếp hoặc thêm một method **chỉ dành cho môi trường kiểm thử**. Sau khi gây lỗi channel, hãy để connection/container recovery hoạt động và quan sát broker logs trước khi chạy case khác.

### 9.5. Ma trận kết quả lab

| Kịch bản | Broker | Confirm | Return | Kết luận |
| --- | --- | --- | --- | --- |
| Route `order.created` vào work queue | Exchange + binding hợp lệ | ACK | Không | `CONFIRMED_NO_RETURN`; listener test nhận event. |
| Route `order.queued` vào queue không consumer | Exchange + binding hợp lệ | ACK | Không | `CONFIRMED_NO_RETURN`, **nghiệp vụ chưa xử lý**. |
| Route `order.no-binding` | Exchange tồn tại, không binding | ACK thường gặp | **Có**, thường 312 NO_ROUTE | `RETURNED`. |
| Exchange không tồn tại | Channel error | Có thể lỗi/NACK theo framework | **Không** | Điều tra lỗi channel, không nhầm với return. |
| Caller chờ 20 ms, future còn pending | Chưa biết | Chưa nhận | Chưa đủ dữ liệu | **UNKNOWN** tại deadline. |
| Framework trả NACK | Thường lỗi publish/channel | NACK | Có thể có metadata return liên quan | **NACK**, không ghi thành công. |
| Consumer xử lý lỗi sau broker ACK | Broker đã định tuyến | ACK | Không | Publisher thành công **không đồng nghĩa consumer thành công**. |

**Lưu ý:** NACK/lỗi do framework phát sau connection shutdown có thể chứa một số thông tin không đủ để xác định chính xác trạng thái lưu trữ thực của broker. Khi không chắc, ưu tiên giữ sự kiện và dùng idempotent replay thay vì coi NACK hoặc exception là chứng cứ có thể publish lại vô điều kiện mà không kiểm soát trùng.

## 10. UNKNOWN là trạng thái nghiệp vụ cần quản lý, không chỉ một exception

### 10.1. Timeline chứng minh ambiguity

~~~text
Producer                        Network                       RabbitMQ
   |                               |                              |
   |--- publish evt-5001 --------->|---- message ---------------->|
   |                               |                              |
   |                               |                    queue stores evt-5001
   |                               |                              |
   |<-- connection broken --------X----- confirm ACK -------------|
   |                               |                              |
   | await timeout                 |                              |
   | status = UNKNOWN              |                              |
   |                               |                              |
   |--- retry SAME eventId ------->|---- message ---------------->|
   |                               |                              |
   |                               |                    queue receives again
   |                               |                              |
   v                               v                              v
Consumer có thể thấy hai physical deliveries cho cùng một business event
~~~

Ở mốc timeout, producer không thể biết chắc message đầu tiên đã được broker chấp nhận hay chưa chỉ từ việc không nhận confirm. Đây là bản chất **ambiguous outcome** của hệ phân tán.

### 10.2. Hai sai lầm đối lập

**Sai lầm A: “Timeout nghĩa là chưa gửi”.**

~~~java
if (timedOut) {
    publishWithNewEventId(); // Có nguy cơ business side effect trùng.
}
~~~

**Sai lầm B: “Đã gọi send nghĩa là chắc chắn có message”.**

~~~java
template.send(...);
outbox.delete(eventId); // Có nguy cơ mất tác vụ khi publish thực sự thất bại.
~~~

**Cách làm phù hợp:** persist business event trước publish, chờ confirm/return, ghi trạng thái theo bằng chứng, nếu UNKNOWN thì giữ event để đối soát và **retry cùng eventId** khi chính sách cho phép; consumer phải kiểm tra eventId theo một transaction/idempotency contract.

### 10.3. Không dùng callback đến muộn để ghi đè trạng thái mới một cách mù quáng

Ví dụ:

~~~text
attempt-A    send evt-5001 --> timeout --> event marked UNKNOWN
attempt-B    retry evt-5001 --> confirm ACK --> event marked PUBLISHED
attempt-A    late NACK callback --------------------> ?
~~~

Nếu callback attempt-A **ghi đè** `PUBLISHED` của attempt-B thành `NACK`, hệ thống sẽ đưa ra trạng thái sai. Cần lưu mỗi attempt một bản ghi và cập nhật outbox bằng **compare-and-set theo attemptId + state version**, hoặc tính trạng thái tổng hợp dựa trên tất cả outcome mà không ghi đè mất bằng chứng.

Một consumer idempotent giúp chịu được việc cả attempt-A và attempt-B đã được broker nhận. Nhưng outbox vẫn phải quản lý retention, tốc độ retry và đối soát để không tạo retry storm.

## 11. Hoàn chỉnh giải pháp bằng transactional outbox và idempotent consumer

### 11.1. Vì sao cần outbox trước khi gọi RabbitTemplate?

Giả sử ứng dụng cập nhật trạng thái đơn hàng trong database rồi publish:

~~~text
BEGIN DB transaction
UPDATE orders SET state = 'PAID' ...
COMMIT
       |
       +-- process crash --> chưa RabbitTemplate.send()
                            => DB đã PAID, sự kiện không tồn tại
~~~

Đổi thứ tự publish trước commit cũng không giải quyết hoàn toàn: broker có thể nhận event nhưng DB rollback. **Database transaction và AMQP publish không phải một transaction nguyên tử chung chỉ vì chúng chạy trong cùng một method Java.**

**Transactional outbox** lưu ý định phát sự kiện **cùng transaction với thay đổi nghiệp vụ**:

~~~text
Order API / domain logic
     |
     +-- DB transaction ----------------------------------+
     |     UPDATE orders                                  |
     |     INSERT outbox_events(eventId, body, route)     |
     |     COMMIT                                         |
     +----------------------------------------------------+
                             |
                   Outbox dispatcher
                             |
                   lease pending event
                   insert publish_attempt
                             |
                      RabbitTemplate
                             |
                 CorrelationData future
                             |
              +--------------+-------------+
              |              |             |
       ACK no return       RETURNED    NACK / UNKNOWN
              |              |             |
       broker accepted   repair route   backoff/reconcile
              |              |             |
              +--------------+-------------+
                             |
                   Consumer idempotent inbox
                             |
                       Business DB commit
~~~

**Không xóa event gốc chỉ vì `send()` trả về** hoặc vì future chờ quá hạn. Phải giữ durable intent cho đến khi có bằng chứng đủ theo hợp đồng.

### 11.2. Schema SQL minh họa

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE outbox_events (
    event_id          TEXT PRIMARY KEY,
    event_type        TEXT NOT NULL,
    exchange_name     TEXT NOT NULL,
    routing_key       TEXT NOT NULL,
    payload_json      JSONB NOT NULL,
    state             TEXT NOT NULL DEFAULT 'NEW',
    state_version     BIGINT NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE publish_attempts (
    attempt_id        UUID PRIMARY KEY,
    event_id          TEXT NOT NULL REFERENCES outbox_events(event_id),
    state             TEXT NOT NULL DEFAULT 'IN_FLIGHT',
    detail_code       TEXT,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at        TIMESTAMPTZ
);

CREATE INDEX idx_outbox_events_dispatch
    ON outbox_events (state, created_at);

CREATE INDEX idx_publish_attempts_event
    ON publish_attempts (event_id, started_at);
~~~

`outbox_events` mô tả **business event cần publish**. `publish_attempts` mô tả **mỗi lần gửi vật lý**. Một event có thể có nhiều attempts, nhưng tất cả phải mang cùng **eventId** ở payload. Chi tiết timeout/return/NACK được lưu theo attempt, tránh mất bằng chứng khi callback đến trễ.

**Bảo mật:** `payload_json` chỉ là ví dụ. Nếu payload có thông tin nhạy cảm, bảo vệ outbox bằng RBAC, mã hóa lưu trữ hoặc application-level encryption theo threat model; không lưu thẳng PII vào bảng chỉ vì ví dụ đơn giản.

### 11.3. Trạng thái nào được phép cập nhật?

| Mức | Trạng thái | Ý nghĩa |
| --- | --- | --- |
| Outbox event | `NEW` | Đã commit intent, chưa publish. |
| Publish attempt | `IN_FLIGHT` | Đã ghi nhận attempt ID, đang gửi/chờ confirm. |
| Publish attempt | `CONFIRMED_NO_RETURN` | Broker confirm ACK và không có return tương ứng. |
| Publish attempt | `RETURNED` | Unroutable; cần sửa topology/route/contract. |
| Publish attempt | `NACK` | Publish không được broker xác nhận thành công. |
| Publish attempt | `UNKNOWN` | Không có kết quả đủ rõ trong deadline hoặc transport lỗi. |
| Outbox event | `BROKER_CONFIRMED` | Có attempt được confirm đủ điều kiện của producer; **không có nghĩa consumer processed**. |
| Business/inbox | `PROCESSED` | Consumer đã commit xử lý nghiệp vụ theo hợp đồng. |

**Phân tách rõ:** `BROKER_CONFIRMED` và `PROCESSED` không phải cùng một trạng thái. Nếu chỉ cần bảo đảm broker nhận sự kiện, outbox có thể kết thúc ở `BROKER_CONFIRMED` sau khi đánh giá confirms/returns đúng; nếu cần xác nhận nghiệp vụ đầu cuối, phải có **application-level completion event/reconciliation**.

### 11.4. Lưu attemptId trước khi gửi

Đoạn **thuật toán minh họa**:

~~~java
// Pseudocode: OutboxDispatcher, không phải file Java độc lập.
// Một worker đã lease outbox row bằng transaction/lock hợp lệ.

String attemptId = UUID.randomUUID().toString();

// Transaction nhỏ riêng: persist attempt trước network I/O.
attemptRepository.insertInFlight(attemptId, event.eventId());

// Hàm overload ở mục 6 nhận attemptId đã tạo.
PublishAttempt attempt = publisher.publish(
        routingKey, event, attemptId);

attempt.completion().whenComplete((result, error) -> {
    // Callback có thể chạy trên thread khác.
    // Mở transaction RIÊNG, không giữ DB lock xuyên send.
    PublishResult resolved = error == null
            ? result
            : new PublishResult(event.eventId(), attemptId,
                    PublishState.UNKNOWN, "callback_exception");

    attemptRepository.recordIfInFlight(
            attemptId, resolved.state().name(), resolved.detail());

    // Nếu là ACK_NO_RETURN, cập nhật trạng thái tổng hợp theo
    // state_version / CAS / sự kiện có ít nhất một successful attempt.
    // Không cho NACK của attempt cũ ghi đè event đã BROKER_CONFIRMED.
});
~~~

`attemptRepository` là abstraction do ứng dụng phải triển khai. Đoạn trên chỉ truyền tải **trình tự**; production cần xử lý callback throw, database outage, retry update attempt, giới hạn số outstanding futures, scheduler và phân tán nhiều dispatcher replicas.

**Một vấn đề race thường gặp:** nếu gọi `publisher.publish` rồi **mới insert attempt row**, broker có thể confirm trước khi database có row; callback update không tìm thấy attempt. Vì vậy trong thiết kế outbox thực sự, **ghi attemptId bền vững trước khi gửi**. Đó là lý do `ConfirmAwarePublisher.publish(..., attemptId)` cho phép truyền attempt ID từ dispatcher.

### 11.5. Tránh hai dispatcher cùng publish không kiểm soát

Một dispatcher phân tán thường:

1. Chọn một nhóm outbox rows chưa hoàn tất bằng lock/lease, ví dụ `SELECT ... FOR UPDATE SKIP LOCKED` trong PostgreSQL.
2. Ghi lease owner/deadline hoặc trạng thái hợp lệ rồi commit, **không giữ transaction DB suốt thời gian RabbitMQ confirm**.
3. Tạo attempt ID, insert row `IN_FLIGHT` bền vững.
4. Publish qua `RabbitTemplate` và cập nhật attempt outcome theo callback.
5. Nếu lease hết mà không có outcome, phân loại `UNKNOWN`; có thể retry **cùng eventId** với attempt ID mới sau backoff.
6. Dùng state version/CAS để kết quả attempt cũ không ghi đè trạng thái đã được chứng minh bởi attempt mới.

**Không giả định lease bảo đảm exactly-once publish.** Worker có thể pause sau khi publish, lease hết, worker khác retry; broker nhận hai physical messages. Thiết kế at-least-once chấp nhận khả năng này rồi khống chế bằng inbox/idempotency.

### 11.6. Bảng hành động đối với từng outcome

| Outcome | Outbox/dispatcher nên làm | Cảnh báo |
| --- | --- | --- |
| `CONFIRMED_NO_RETURN` | Ghi attempt success và event broker-confirmed nếu hợp đồng phù hợp. | Không đánh dấu consumer processed hoặc xóa dữ liệu đối soát quá sớm. |
| `RETURNED` | Giữ event, phân loại routing failure; alert topology/schema; retry **sau khi sửa route**. | Retry cùng wrong key vô hạn không giúp gì. |
| `NACK` | Lưu cause; retry có backoff, hoặc điều tra broker/channel. | Framework NACK sau connection close đôi khi vẫn cần idempotent replay do timeline không rõ. |
| `UNKNOWN` | Giữ intent, chờ grace period/late callback, đối soát rồi retry cùng eventId nếu cần. | Không phát lại liên tục; backoff/jitter và retry budget. |
| Local serialization/validation error | Đánh dấu invalid input, không publish. | Đừng trộn lỗi chưa gửi vào trạng thái UNKNOWN. |

Đối với một luồng thanh toán, việc “broker-confirmed” chỉ nói thông điệp được broker chấp nhận theo confirms, **không thay thế response/business event xác nhận thanh toán được xử lý**. Quy định SLO end-to-end phải theo trạng thái của hệ thống nghiệp vụ đích.

### 11.7. Consumer inbox/idempotency

Ví dụ schema:

~~~sql
CREATE TABLE processed_order_events (
    consumer_name TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong cùng **database transaction** với thay đổi nghiệp vụ:

~~~sql
INSERT INTO processed_order_events(consumer_name, event_id)
VALUES ('fulfillment-service', :event_id)
ON CONFLICT DO NOTHING;
~~~

Chỉ thực hiện side effect khi **insert thêm một hàng mới**; nếu conflict, đã xử lý trước đó nên không tạo tác dụng phụ mới. Nếu transaction thất bại, **cả dấu inbox và tác động nghiệp vụ phải rollback**. Với side effect bên ngoài database như email, thanh toán hoặc HTTP downstream, cần idempotency key tương ứng hoặc workflow/compensation; unique DB record không tự làm email hay API call ngoài DB exactly-once.

**Cần giữ eventId qua retry:** `evt-order-1001` vẫn là `evt-order-1001` ở attempt mới; chỉ `attemptId` đổi. Nếu mỗi lần gửi lại tạo eventId mới, inbox không nhận ra trùng lặp.

## 12. Fault injection: mất kết nối, callback muộn và kết quả khó biết

### 12.1. Vì sao fault injection không có một kết quả Java cố định?

Giả sử ta dừng RabbitMQ hoặc cắt mạng **đúng trong lúc publish**. Kết quả phụ thuộc thời điểm:

| Thời điểm sự cố | Kết quả có thể quan sát | Ý nghĩa |
| --- | --- | --- |
| Trước khi producer mở channel | `AmqpConnectException` hoặc exception local; có thể chưa gửi byte nào. | Có thể chứng minh local send chưa thực hiện, nhưng phải đọc dấu vết thật. |
| Sau khi producer gửi message, trước khi RabbitMQ ghi queue | Timeout, connection close, NACK từ framework. | Producer có thể không biết broker đã làm gì trước khi channel đóng. |
| Sau khi RabbitMQ chấp nhận message, trước khi producer nhận confirm | Timeout hoặc mất callback; **broker vẫn có message**. | Trường hợp điển hình của **UNKNOWN**. |
| Sau khi producer nhận confirm nhưng trước khi ghi outbox status | Process crash; database vẫn ghi `IN_FLIGHT`. | Cần đối soát/retry và idempotent consumer. |
| Sau khi consumer commit DB nhưng trước consumer ACK | RabbitMQ có thể redeliver message. | Producer confirm đã đúng nhưng vẫn có duplicate delivery. |

Chính vì các race này, phép thử **tạo future chưa hoàn tất ở mục 9.2** là cách ổn định để unit-test **quyết định UNKNOWN**. Fault injection thật dành cho môi trường tích hợp, nhằm quan sát hệ thống có phục hồi đúng hay không, **không assert một trạng thái transport cụ thể ở mọi lần chạy**.

### 12.2. Quy trình thử mất broker an toàn

Chỉ sử dụng RabbitMQ container riêng của lab:

1. Khởi động broker, xác nhận exchange/queue/binding sẵn sàng và phép thử ACK bình thường đã PASS.
2. Tạo một tập business event có `eventId` cố định và ghi bền vững vào outbox test.
3. Publish nhiều events song song với correlated confirms; ghi lại `attemptId`/outcome, không chờ/block từng publish một nếu muốn tạo concurrency.
4. Tại một thời điểm có chủ đích, dừng/cắt kết nối **container test** hoặc tạm ngưng mạng tới broker. Ví dụ có thể thao tác bằng Docker Desktop hoặc `docker pause` đối với container demo, **không phải môi trường thật**.
5. Ghi nhận các kết quả: một số ACK, một số exception/NACK, một số timeout/UNKNOWN. **Không ép mong đợi số lượng từng loại** vì lịch xử lý là nondeterministic.
6. Khởi động/resume broker; đợi client/container recovery theo cấu hình.
7. Cho dispatcher đối soát các event chưa `BROKER_CONFIRMED` rồi retry cùng `eventId` khi cần; sinh `attemptId` mới cho mỗi publish.
8. Quan sát queue và consumer. Với inbox có unique eventId, xác minh mỗi business event chỉ tạo **một** tác dụng phụ, dù có thể có nhiều physical deliveries.
9. Đối chiếu outbox events, publish attempts, processed inbox và terminal failure store; không chỉ dựa vào độ sâu queue.

Với `docker pause`, heartbeat/timeouts có thể cần thời gian mới báo lỗi; việc pause ngắn không chắc làm mất confirm. `docker stop` làm TCP đóng có thể dẫn tới kết quả khác. **Điều cần kiểm chứng là chính sách khôi phục**, không phải một mã lỗi hoặc số milliseconds cố định.

### 12.3. Điều xảy ra khi kết nối bị blocked do resource alarms

RabbitMQ có thể **block connection của publisher** khi thiếu RAM hoặc dung lượng đĩa. Trong khi block, publish có thể bị giữ/chậm và future không hoàn tất đúng deadline. Đây không nhất thiết là exchange không tồn tại hay no-binding.

Khi gặp hàng loạt UNKNOWN:

- Kiểm tra RabbitMQ alarms, memory/disk usage, queue backlog, connection blocked/unblocked events.
- Không spawn hàng nghìn producer threads chỉ vì future pending.
- Không bật retry dồn dập làm tăng tải broker; dùng backpressure, giới hạn in-flight và exponential backoff.
- Sau khi broker hồi phục, kiểm tra cả **late confirms** và outbox pending; dự phòng duplicate bằng eventId ổn định.

**Đặc biệt:** consumer có thể tiếp tục xử lý một số messages trong khi publisher connection bị block. Không suy từ “producer không nhận confirm ngay” rằng toàn bộ hệ thống đã ngừng nhận message.

## 13. Chẩn đoán xác nhận và trả lại thông điệp khi gặp lỗi

### 13.1. Quy trình kiểm tra nhanh

Khi một publisher báo `send` chạy nhưng consumer không nhận:

1. **Xác định eventId + attemptId**, exchange, routing key, vhost, thời điểm và phiên bản ứng dụng.
2. Kiểm tra `publisher-confirm-type=correlated`, `publisher-returns=true` và `template.mandatory=true` có hiệu lực trên đúng bean `RabbitTemplate`.
3. Phân biệt **future complete ACK/NACK** và **`CorrelationData.getReturned()`**. Không chỉ grep chuỗi `ACK` trong log.
4. Kiểm tra exchange tồn tại và đúng type; nếu không có exchange, tìm channel error/`NOT_FOUND`, không tìm `NO_ROUTE` ở return.
5. Kiểm tra queue và binding khớp routing key/vhost. Với topic exchange, nhớ `*` khớp một segment và `#` khớp nhiều segment; ở bài này là direct exchange, cần **exact match**.
6. Xem RabbitMQ `messages_ready`, `messages_unacknowledged`, consumers, queue type, TTL/DLX, permissions, resource alarms.
7. Nếu queue đã có message nhưng không xử lý, điều tra `@RabbitListener`/converter/ACK/retry/DLQ, **không đổ cho publisher confirm**.
8. Nếu outcome UNKNOWN, xem outbox và attempts bền vững; tránh xóa/retry không kiểm soát. Theo dõi callback đến muộn.
9. Xác minh DB/inbox nghiệp vụ; khi cần replay, giữ `eventId` và ghi attempt mới.
10. Kết thúc incident khi đã đối soát số tác vụ nguồn với số tác vụ đích **hoàn tất hoặc terminal failure**, không chỉ vì queue trở về rỗng.

### 13.2. RabbitMQ CLI tham khảo

Trên broker/container test hoặc máy quản trị có quyền tương ứng:

~~~bash
# Exchange và loại exchange đúng vhost?
rabbitmqctl list_exchanges -p / name type durable

# Binding nào nối exchange đến queue?
rabbitmqctl list_bindings -p / source_name destination_name routing_key

# Queue đã nhận message chưa? Có consumer không?
rabbitmqctl list_queues -p / \
  name messages_ready messages_unacknowledged consumers

# Broker có block publishers vì RAM/đĩa?
rabbitmq-diagnostics alarms
~~~

Các lệnh minh họa vhost mặc định `/`. Trong hệ thống thật, phải dùng đúng vhost; một exchange hoặc queue cùng tên ở vhost khác **không liên quan**. Cú pháp/fields tùy version RabbitMQ; có thể dùng Management UI và tài liệu CLI khi cần.

**Không dùng `purge_queue`, xóa/redeclare production queue hoặc thay binding vô tội vạ chỉ để “chứng minh return”**. Dùng exchange/queue riêng trong Testcontainers. Nếu publisher trả return, sửa topology/route rồi **publish lại từ outbox**; thêm binding sau sự cố không tự làm message trước đó xuất hiện.

### 13.3. Những lỗi thiết lập Spring AMQP thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| Future không hoàn tất | Confirm type NONE/SIMPLE, connection blocked, channel close, lỗi network, callback deadlock. | Dùng CORRELATED; xem logs/factory và pending confirms, deadline. |
| ACK nhưng không thấy return với key sai | `mandatory=false`, returns disabled, AE route khác hoặc binding thực tế đã tồn tại. | Kiểm tra cấu hình effective, binding và alternate exchange. |
| `getReturned()` khác null sau confirm ACK | **Bình thường** cho unroutable mandatory publish. | Phân loại RETURNED, không coi thành công. |
| `getReturned()` luôn null dù template callback có return | ID correlation bị trùng/thiếu, dùng bean/template khác hoặc logic callback can thiệp. | Đặt attemptId duy nhất, kiểm tra thực tế config/callback. |
| Gửi tới exchange không tồn tại | RabbitMQ đóng channel với NOT_FOUND. | Kiểm tra exchange/vhost, khai báo topology trước publish. |
| Confirm ACK nhưng consumer không chạy | Queue không có consumer, listener crash, schema decode lỗi hoặc queue khác. | Kiểm tra ready/unacked, listener logs và chính sách retry. |
| UI báo queue trống sau ACK | Consumer đã ACK nhanh hoặc queue TTL/DLX, không nhất thiết publish sai. | Xem consumer metrics, DLQ và business DB. |
| Publish callback ghi đè trạng thái mới | Late result của attempt cũ, không có attemptId/CAS. | Bảng attempts và versioned state transitions. |
| UNKNOWN tăng vọt khi broker quá tải | Memory/disk alarm, blocked connection, nhiều outstanding publishes. | Backpressure, hạ tải, xử lý broker alarm, không retry storm. |
| Confirm NACK thiếu reason | Broker-generated NACK không nhất thiết có detail. | Giữ correlation/timeline và tra broker logs. |
| Custom RabbitTemplate không có returns | Boot properties không áp vào bean tự khai báo như mong đợi. | Cấu hình trực tiếp hoặc qua `RabbitTemplateConfigurer`. |
| Callback chậm và confirm bị trì hoãn | Blocking return/confirm callback. | Ghi log nhanh, chuyển DB/network work sang executor có giới hạn. |

### 13.4. Không dùng transaction AMQP để che sự khác nhau

RabbitMQ **publisher confirms** và **AMQP channel transactions** là hai cơ chế khác nhau; trên cùng AMQP channel, `confirm.select` và `tx.select` không phải cách kết hợp tùy ý để “chắc chắn hơn”. `RabbitTemplate.setChannelTransacted(true)` có trade-off hiệu năng và settlement khác, **không biến RabbitMQ publish thành transaction nguyên tử với business database**.

Nếu mục tiêu là ứng dụng không mất message khi DB commit và producer crash, dùng **transactional outbox**. Nếu mục tiêu là biết publish có được broker xác nhận, dùng **publisher confirms**. Nếu mục tiêu là biết message có đi tới queue phù hợp không, dùng **mandatory returns**. Ba yêu cầu đó khác nhau.

### 13.5. Cẩn trọng với RabbitTemplate.invoke / SIMPLE confirms

Spring AMQP còn hỗ trợ `RabbitTemplate.invoke(...)` với `waitForConfirmsOrDie(...)` trên dedicated channel cho các scoped operations; dùng `ConfirmType.SIMPLE` khi chỉ cần một cơ chế chờ confirm của nhóm publish theo scope. Tuy nhiên **không thay thế trực tiếp khả năng tương quan từng event/attempt và `ReturnedMessage`** của correlated confirms trong bài.

Không bật đồng thời nhiều kiểu confirm và suy ra chúng cộng thêm độ an toàn. Chọn API theo nhu cầu: **CORRELATED + CorrelationData** khi theo dõi kết quả của từng publish trong outbox, còn scoped wait-for-confirms khi thiết kế quy trình chờ nhóm có kiểm soát.

## 14. Quan sát từng publish attempt mà không làm quá tải metric

### 14.1. Structured log theo eventId và attemptId

Ví dụ log ứng dụng khi nhận confirm/return:

~~~json
{
  "timestamp": "2026-11-26T08:15:00Z",
  "service": "order-service",
  "event": "amqp.publish.outcome",
  "eventType": "order.created",
  "eventId": "evt-created-2001",
  "attemptId": "54b2a0b7-8aa0-42ef-b4ca-a810d496abf1",
  "exchange": "orders.events.x",
  "routingKey": "order.created",
  "result": "CONFIRMED_NO_RETURN",
  "detailCode": "broker_confirm_ack_without_return",
  "elapsedMs": 12,
  "traceId": "trace-example"
}
~~~

Đây là **mẫu do ứng dụng tạo**, không phải JSON RabbitMQ tự phát. Khi có `RETURNED`, nên ghi thêm mã `replyCode` và `replyText` đã được làm sạch; nếu `UNKNOWN`, ghi deadline và việc retry đã được lên lịch hay chưa.

**Không log raw body hoặc `ReturnedMessage.getMessage()`.** Return thường chứa **nguyên message**, có thể chứa PII, token hoặc dữ liệu tài chính. Nếu routing key cũng chứa tenant ID nhạy cảm, phải masking/opaque alias theo chính sách. Không viết password, TLS key hoặc connection URI có credential vào log.

### 14.2. Metric ứng dụng nên có

| Metric đề xuất | Tag cardinality thấp | Điều cần phân biệt |
| --- | --- | --- |
| `app_amqp_publish_attempts_total` | service, exchange_alias | Số **lần thử**, khác số business events duy nhất. |
| `app_amqp_publish_outcomes_total` | outcome, event_type | `CONFIRMED_NO_RETURN`, `RETURNED`, `NACK`, `UNKNOWN`. |
| `app_amqp_confirm_latency_seconds` | exchange_alias, outcome | Từ publish attempt tới confirm, không đo business processing. |
| `app_amqp_inflight_attempts` | broker_alias | Backpressure, futures đang đợi. |
| `app_amqp_outbox_pending_age_seconds` | event_type | Công việc chưa broker-confirmed và đã chờ bao lâu. |
| `app_amqp_consumer_processed_total` | consumer_name, event_type | Business events đã commit ở đích. |
| `app_amqp_consumer_duplicates_total` | consumer_name | Duplicate event IDs được inbox chặn. |
| `app_amqp_dlq_oldest_age_seconds` | queue_group | Message lỗi ở consumer, **không phải publisher return**. |

Đây là **tên metric tùy chỉnh**, không phải tất cả đều có sẵn từ Spring Boot Actuator hay RabbitMQ exporter. **Không đặt eventId hoặc attemptId vào Prometheus/Micrometer tags** vì cardinality rất cao; chúng thuộc structured logs/traces/outbox database.

### 14.3. Ba dashboard nên tách

1. **Publisher dashboard:** sent attempts, ACK, NACK, returned, unknown, p95/p99 confirm latency, pending confirms, blocked connections.
2. **Broker dashboard:** exchange route rates, queue ready/unacked, bindings, memory/disk alarms, publisher confirms, channel closures.
3. **Business dashboard:** outbox oldest pending age, inbox processed events, duplicate suppressions, terminal failures, end-to-end business latency.

**Không lấy “publisher ACK 100%” làm chỉ số “xử lý đơn hàng 100%”**. Khi queue không có consumer, mọi publish `order.queued` trong lab vẫn có thể được confirm ACK nhưng business completion bằng 0.

## 15. Checklist kết quả và bằng chứng phải thu thập

Sau khi chạy bài, điền bảng bằng **kết quả thực**:

| Test | eventId | attemptId | Confirm? | Return? | Queue nào nhận? | Consumer processed? | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A — matched key | *tự ghi* | *tự ghi* | *đo* | *đo* | *đo* | *đo* | *đo* |
| B — no binding | *tự ghi* | *tự ghi* | *đo* | *đo* | *đo* | *đo* | *đo* |
| C — queue không consumer | *tự ghi* | *tự ghi* | *đo* | *đo* | *đo* | *đo* | *đo* |
| D — future pending | *tự ghi* | *tự ghi* | *chưa rõ* | *chưa rõ* | *chưa rõ* | *chưa rõ* | `UNKNOWN` |
| E — missing exchange | *tự ghi* | *tự ghi* | *đo* | *đo* | *đo* | *đo* | *đo* |
| F — late confirm / retry | *tự ghi* | *hai attempts* | *đo* | *đo* | *đo* | *đo* | *đo* |

**Không tự điền các ô “đo” bằng con số dự đoán.** Sự khác nhau giữa broker, queue type, phiên bản, network và timeline làm kết quả NACK/timeout không hoàn toàn cố định.

### 15.1. Checklist kỹ thuật trước khi chạy

- [ ] Đang dùng **RabbitMQ AMQP 0-9-1** và đúng dependency Spring Boot/Spring AMQP.
- [ ] Broker Testcontainers hoặc môi trường demo có permissions và đã khai báo exchange/queues/bindings.
- [ ] `publisher-confirm-type=correlated`, `publisher-returns=true` và `template.mandatory=true` có hiệu lực trên đúng template/factory.
- [ ] Mỗi publish dùng **CorrelationData riêng** với `attemptId` duy nhất.
- [ ] Cùng `eventId` được giữ khi retry, không dùng attemptId làm business dedup key.
- [ ] Logic kết luận xem **cả confirm.isAck() lẫn correlation.getReturned()**.
- [ ] Callback không block dài hoặc thực hiện tác vụ không giới hạn trên I/O/executor thread.
- [ ] Future deadline không phá hủy khả năng nhận confirm muộn và không xóa outbox.
- [ ] Exchange không tồn tại được phân biệt với exchange tồn tại nhưng không có matching binding.
- [ ] **Publisher confirm** và **consumer ACK** được theo dõi/đánh giá riêng.
- [ ] Test đặt tại broker/vhost riêng, không purge/delete production resources.

### 15.2. Checklist độ tin cậy trước production

- [ ] Business event được ghi bằng **transactional outbox** cùng transaction nghiệp vụ nguồn.
- [ ] Attempt được persist trước khi gọi publish, có eventId/attemptId, deadline và trạng thái.
- [ ] Event state được cập nhật bằng version/CAS, tránh callback cũ ghi đè kết quả mới.
- [ ] `RETURNED` là routing incident, không retry vô hạn cùng một key sai.
- [ ] `NACK` được phân loại theo cause/broker health và retry có backoff.
- [ ] `UNKNOWN` được lưu, đối soát và retry cùng business ID theo chính sách.
- [ ] Giới hạn số in-flight futures, retry rate, queue backlog và callback work.
- [ ] Consumer có **inbox/idempotency** và business transaction thật.
- [ ] Consumer errors có retry hữu hạn, DLQ/quarantine và redrive có kiểm soát.
- [ ] Có alert cho returned/nack/unknown/outbox oldest age và business completion lag.
- [ ] Audit và retention bảo vệ PII/secret trong payload, log, outbox và returned messages.

## 16. Bài tập mở rộng

### Bài tập 1 — Đổi topic exchange

Thay `DirectExchange` bằng `TopicExchange`. Dùng routing key `orders.created.v1.enterprise` và binding `orders.created.v1.*`. Gửi một key có thêm segment `region`; dùng publisher return để chứng minh binding `*` khớp **đúng một** segment. Thử binding `orders.created.#` rồi so sánh. Dùng queue test độc lập cho từng pattern để tránh nhầm dữ liệu cũ.

### Bài tập 2 — Chứng minh ACK không đồng nghĩa xử lý thành công

Tạo một listener cố tình throw sau khi broker đã confirm publish. Phân biệt:

- Producer: `CONFIRMED_NO_RETURN` vì message đã vào queue.
- Consumer: exception, retry hoặc DLQ tùy policy.
- Nghiệp vụ: chưa hoàn tất thành công nếu DB rollback.

Không đặt `defaultRequeueRejected=true` cho một poison message không có retry budget trên broker dùng chung; nếu muốn kiểm tra DLQ, provision DLX/binding riêng.

### Bài tập 3 — Cố tình thiếu binding

Gửi `order.no-binding` tới exchange hợp lệ rồi xác nhận `ReturnedMessage.replyCode=312` trong lab. Thêm binding cho key đó và gửi **event mới**; quan sát không còn return. Không kỳ vọng message đã return trước đó tự được broker giữ và phát lại khi binding mới xuất hiện.

### Bài tập 4 — Kiểm tra hai attempts của một event

Tạo outbox với `eventId=evt-repeat-7001`. Publish hai lần với `attemptId` khác nhau nhưng cùng eventId, consumer lưu inbox theo eventId. Xác minh có thể nhận hai physical deliveries, nhưng DB chỉ ghi một tác dụng phụ. Dùng SQL query/constraint để chứng minh, không chỉ đếm `@RabbitListener` method invocations.

### Bài tập 5 — Replay UNKNOWN sau restart

Trong môi trường test, tạo một attempt `IN_FLIGHT` và giả lập process crash trước khi callback update DB. Khi dispatcher khởi động lại, đánh dấu attempt cũ `UNKNOWN` sau lease/deadline; gửi attempt mới với cùng eventId, theo dõi confirm và đối soát consumer. Không bắt buộc broker thực sự crash để kiểm tra logic trạng thái outbox.

### Bài tập 6 — Quan sát callback đến trễ

Thêm một executor giả lập trì hoãn việc **ghi trạng thái outbox** sau callback (không trì hoãn xử lý giao thức AMQP/return callback thực). Gửi hai attempts, nhận outcome theo thứ tự đảo. Viết CAS để sự kiện đã `BROKER_CONFIRMED` không bị attempt cũ `NACK`/`UNKNOWN` ghi đè.

### Bài tập 7 — Lỗi exchange không tồn tại

Trong Testcontainers riêng, publish tới exchange không tồn tại. Thu thập broker error log, Java exception/correlation future và channel recovery. Giải thích tại sao **không có publisher return `NO_ROUTE`** và không được coi đây là một thông điệp đã đi vào DLQ.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `RabbitTemplate.send()` trả về mà không ném exception. Có thể đánh dấu outbox event `BROKER_CONFIRMED` ngay không?

**Đáp án:** Không. `send()` là thao tác publish bất đồng bộ; phải chờ publisher confirm và kiểm tra return. Nếu chưa nhận được kết quả, trạng thái có thể là `IN_FLIGHT` hoặc `UNKNOWN` theo deadline.

**Câu 2.** Broker gửi `basic.return` rồi `basic.ack` cho cùng một message. Đó có phải lỗi mâu thuẫn?

**Đáp án:** Không. Với mandatory publish không route được vào queue, broker có thể gửi return trước confirm ACK. **ACK không đồng nghĩa routed**; ứng dụng phải ghi trạng thái `RETURNED`.

**Câu 3.** Tại sao cần `CorrelationData.id` duy nhất cho mỗi attempt?

**Đáp án:** Để Spring tương quan confirm/return đúng lần publish, tránh nhầm giữa hai attempts đang bay. Business `eventId` vẫn cần giữ nguyên khi gửi lại cùng một nghiệp vụ.

**Câu 4.** Publish vào `orders.parked.q` không có consumer nhưng confirm ACK và không return. Đã hoàn tất đơn hàng chưa?

**Đáp án:** Chưa. Broker nhận message vào queue; `@RabbitListener` chưa xử lý và business DB chưa commit. Cần tách trạng thái broker accepted với business processed.

**Câu 5.** Future chưa hoàn tất trước timeout 2 giây. Có thể khẳng định RabbitMQ không nhận message không?

**Đáp án:** Không. Confirm có thể bị trễ/mất trên đường về hoặc broker đang block publishers; **UNKNOWN** chỉ là trạng thái thiếu bằng chứng tại deadline.

**Câu 6.** Khi retry một message UNKNOWN, nên tạo mới eventId hay attemptId?

**Đáp án:** Giữ **eventId** để consumer idempotent và tạo **attemptId mới** cho mỗi lần publish. Lưu outcome từng attempt để đối soát.

**Câu 7.** Publisher gửi vào exchange không tồn tại; có phải RabbitMQ sẽ return với code 312?

**Đáp án:** Không. Trường hợp exchange không tồn tại thường là lỗi **channel `NOT_FOUND`**. Code 312 `NO_ROUTE` phổ biến khi exchange tồn tại nhưng không có route cho mandatory publish.

**Câu 8.** Dùng `CompletableFuture.orTimeout(...)` trực tiếp trên correlation future có nhược điểm gì trong bài học này?

**Đáp án:** Nó có thể hoàn tất future gốc bằng timeout exception, không còn giữ bằng chứng confirm đến muộn thông qua future đó. Dùng `get(timeout)` để lấy **snapshot UNKNOWN** mà không hủy future, hoặc thiết kế deadline stage riêng.

**Câu 9.** Tại sao cần hai bảng `outbox_events` và `publish_attempts`?

**Đáp án:** Vì một business event có thể trải qua nhiều lần publish vật lý, kết quả từng attempt có thể đến muộn hoặc đảo thứ tự. Tách bảng giúp giữ lịch sử và tránh callback cũ ghi đè trạng thái mới.

**Câu 10.** Consumer nhận hai lần cùng eventId; có phải publisher confirms bị lỗi?

**Đáp án:** Không nhất thiết. At-least-once delivery, ACK bị mất, producer retry UNKNOWN hoặc outbox dispatcher restart đều có thể dẫn tới duplicate. Cần idempotent consumer/inbox và đối soát theo business ID.

**Câu 11.** Có thể biết message unroutable bằng việc quan sát DLQ không?

**Đáp án:** Không đầy đủ. Publisher return xảy ra ở giai đoạn exchange không route được; DLQ liên quan dead-letter từ queue theo chính sách khác. Dùng publisher returns/mandatory để phát hiện unroutable publish.

**Câu 12.** Vì sao `CONFIRMED_NO_RETURN` không được gọi là `BUSINESS_SUCCESS`?

**Đáp án:** Nó chỉ là bằng chứng publish trên đường producer/broker. Consumer có thể chưa nhận, nhận rồi thất bại, hoặc nghiệp vụ chưa commit. Trạng thái thành công nghiệp vụ cần tín hiệu hoặc kết quả bền vững ở service đích.

## 18. Tổng kết

Bài thực hành đã tạo được cách **phân loại publish theo bằng chứng** trong Spring AMQP:

- **Correlated publisher confirms** giúp biết RabbitMQ đã gửi **ACK/NACK** cho một `CorrelationData` của **attempt** nào.
- **Mandatory publisher returns** phát hiện message **không định tuyến được**; một publish **ACK vẫn có thể RETURNED**.
- **UNKNOWN** là trạng thái khi producer **không có câu trả lời đủ rõ trước deadline**, không phải `NACK` và không tự chứng minh message chưa tới broker.
- **Consumer ACK** và business completion là bước độc lập, không được suy từ publisher confirm.

Để xử lý **at-least-once một cách đáng tin cậy**, lưu business event vào **transactional outbox**, lưu **attemptId riêng cho mỗi lần publish**, giữ **eventId ổn định** khi retry, dùng **idempotent inbox** tại consumer và đối soát đầu cuối. Khi lỗi xuất hiện, kiểm tra exchange, queue, binding, publisher returns, confirms, connection alarms và trạng thái nghiệp vụ trước khi phát lại. Như vậy ta tránh cả **mất message âm thầm** lẫn **tác dụng phụ trùng lặp** trong những trường hợp publish có kết quả chưa rõ.

### Tài liệu tham khảo chính thức

- [Spring AMQP 3.2 — RabbitTemplate: Correlated Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/3.2/amqp/template.html): `mandatory`, `publisherReturns`, `ConfirmCallback`, `ReturnsCallback`, `CorrelationData` và future.
- [Spring AMQP 3.2 — Sending Messages](https://docs.spring.io/spring-amqp/reference/3.2/amqp/sending-messages.html): overload `send/convertAndSend` với `CorrelationData`.
- [Spring AMQP 3.2 — CorrelationData Javadoc](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/connection/CorrelationData.html): `getFuture()`, `getReturned()`, ID uniqueness.
- [Spring AMQP 3.2 — RabbitTemplate Javadoc](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/core/RabbitTemplate.html): publisher confirm/return APIs.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.rabbitmq.publisher-confirm-type` và `publisher-returns`.
- [Spring Boot — Testcontainers and Service Connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `RabbitMQContainer`, `@ServiceConnection`.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): thời điểm broker confirm, thứ tự return trước ACK và phân biệt consumer ACK.
- [RabbitMQ — Publishers](https://www.rabbitmq.com/docs/publishers): lỗi exchange không tồn tại, unroutable mandatory messages, alternate exchanges.
- [RabbitMQ — Exchanges](https://www.rabbitmq.com/docs/exchanges): direct/topic/fanout và routing qua bindings.
- [RabbitMQ — Memory and Disk Alarms](https://www.rabbitmq.com/docs/alarms): blocked publisher connections khi thiếu tài nguyên.
