# Luân chuyển thông tin kết nối và khôi phục ứng dụng

Khi một ứng dụng Java sử dụng **RabbitMQ qua Spring AMQP** chạy lâu dài, nó thường giữ những connection AMQP đang mở để publish và consume message. Thông tin đăng nhập hoặc chứng chỉ TLS của connection đó vẫn cần thay đổi định kỳ theo chính sách bảo mật, hoặc ngay lập tức khi có dấu hiệu bị lộ. Nếu chỉ đổi mật khẩu trên broker mà không cập nhật đúng cách phía ứng dụng, một lần reconnect có thể khiến tất cả publisher và listener ngừng hoạt động.

**Credential rotation** là quy trình thay thế danh tính hoặc secret sử dụng để thiết lập kết nối. Quy trình này chỉ hoàn thành khi **kết nối mới thực sự sử dụng credential mới**, các chức năng publish/consume vẫn hoạt động, danh tính cũ được thu hồi an toàn và không có message nghiệp vụ bị mất hoặc xử lý trùng vì những lần ngắt kết nối.

Bài thuộc chương **Bảo mật** của module **SPRING_AMQP**. Ta sẽ liên hệ `RabbitTemplate`, `@RabbitListener`, `CachingConnectionFactory`, exchange, queue, binding, publisher confirms, consumer acknowledgments, retry, dead-letter, giao dịch và monitoring để xây dựng quy trình luân chuyển thông tin kết nối có thể vận hành và kiểm chứng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện credential cần rotate: username/password RabbitMQ, token xác thực, chứng chỉ TLS/mTLS, truststore.
2. Giải thích tại sao cập nhật secret trong Secret Manager hoặc Kubernetes **không tự động** đổi authentication của connection đang mở.
3. Thiết kế quy trình thay danh tính **blue/green** theo từng replica, có kiểm tra quyền và kế hoạch rollback.
4. Cấu hình Spring Boot nạp credential từ môi trường thay vì hard-code, đồng thời kiểm tra khả năng nạp lại connection.
5. Phân biệt lỗi authentication, authorization, TLS, connection, topology và message routing.
6. Xác định cửa sổ **publish chưa có confirm**, **DB commit nhưng ACK chưa tới broker** và các biện pháp outbox/idempotency.
7. Lên kế hoạch rolling deployment, drain, theo dõi backlog và đo phục hồi ứng dụng.
8. Kiểm thử những tình huống rotation lỗi trước khi thực hiện trên môi trường production.

## 2. Những loại bí mật khác nhau có vòng đời khác nhau

| Loại bí mật | Ví dụ | Điều cần thay đổi | Rủi ro chính |
| --- | --- | --- | --- |
| Password của user RabbitMQ | `orders_worker_blue` với password phiên bản A | Danh tính hoặc password được broker chấp nhận, cấu hình client | Pod cũ không reconnect được |
| Access token OAuth 2.0 | Token có thời hạn | Gia hạn token và cập nhật cơ chế auth theo khả năng broker/client | Hết hạn trước khi refresh |
| Server certificate TLS | Chứng chỉ cho `rabbitmq.internal` | Cert trên broker, trust chain phía client | Kết nối mới fail TLS handshake |
| Client certificate mTLS | Keystore có private key của ứng dụng | Cert và khóa ứng dụng, trust phía broker | Mất quyền xác thực, lộ private key |
| Truststore/CA | CA-old, CA-new | Tập CA đáng tin cậy trong SSL context | Client không tin chứng chỉ broker mới |
| Quyền đọc secret | Service account, IAM policy | Phân quyền runtime truy cập secret phiên bản mới | Ứng dụng khởi động nhưng không lấy được secret |

**Không coi các loại bí mật này là một thao tác giống nhau.** Password tĩnh thường được kiểm tra khi mở connection mới. Token có expiry và có thể có cơ chế refresh chuyên biệt. Chứng chỉ TLS liên quan SSL context và vòng đời TLS connection. Cách nạp lại phải phù hợp từng loại và phiên bản library.

### 2.1. Bảo mật ngay ở nguồn cấu hình

Không commit username/password thực, access token, private key hoặc keystore có khóa riêng vào Git. Secret nên được lưu trong cơ chế quản lý bí mật của tổ chức, trao cho workload bằng quyền tối thiểu và truy cập qua kết nối có bảo vệ.

Không in secret vào log, stack trace tùy biến, metric labels, dashboard hay command history. Khi cần đối soát rollout, chỉ ghi **mã phiên bản secret không nhạy cảm** (chẳng hạn `green-2026-11`), không ghi giá trị thực.

## 3. Credential được dùng lúc nào trong Spring AMQP?

Trong tích hợp RabbitMQ AMQP 0-9-1 truyền thống, client xác thực khi thiết lập **AMQP connection**. Sau đó các channel, publisher và consumer có thể sử dụng connection đó trong thời gian dài.

~~~mermaid
sequenceDiagram
    participant SM as Secret store
    participant APP as Spring AMQP
    participant RMQ as RabbitMQ

    APP->>SM: Lấy username/password blue
    SM-->>APP: Secret blue
    APP->>RMQ: TLS + AMQP authentication
    RMQ-->>APP: Connection established
    Note over APP,RMQ: Publisher và listener hoạt động
    SM->>SM: Xuất bản secret green
    Note over APP: Connection cũ chưa tự thành green
    APP->>APP: Rolling restart / refresh đã kiểm chứng
    APP->>SM: Lấy secret green
    APP->>RMQ: Mở connection mới với green
    RMQ-->>APP: Connection mới được chấp nhận
~~~

Đặt `RABBITMQ_PASSWORD` mới trong secret store **không bảo đảm** một process đang chạy đọc lại biến môi trường. Những connection đã được xác thực trước đó cũng không tự đổi danh tính chỉ nhờ file secret thay đổi.

Tùy broker và backend xác thực, một connection cũ **có thể tiếp tục hoạt động** sau khi mật khẩu cũ bị thay; nhưng khi buộc mở connection mới, credential cũ có thể bị từ chối. Không nên lấy việc message vẫn chảy trên connection cũ làm bằng chứng đợt rotation đã thành công.

### 3.1. Các mức khôi phục cần quan sát

| Mức | Thành công nghĩa là gì? |
| --- | --- |
| Secret | Workload đã đọc đúng phiên bản credential mới |
| TCP/TLS | Socket được mở và xác minh certificate/hostname hợp lệ |
| AMQP authentication | User/token/cert có thể xác thực vào đúng virtual host |
| Channel | Spring AMQP có thể mở channel publish/consume |
| Topology | Exchange, queue và binding cần thiết tồn tại, đúng quyền |
| Publisher | Message được route, kết quả confirm/return được kiểm soát |
| Consumer | `@RabbitListener` đăng ký lại và nhận delivery |
| Business | Message được xử lý, giao dịch dữ liệu đã commit |

**Socket mở thành công chưa phải là phục hồi nghiệp vụ.** Phải đo cả publish thành công và consumer commit sau rotation.

## 4. Cửa sổ nguy hiểm nếu đổi một mật khẩu trên cùng user

Giả sử ba instance cùng đăng nhập bằng `orders_worker`:

1. RabbitMQ đổi password của `orders_worker` sang phiên bản mới.
2. Instance A và B vẫn có connection cũ, nên có thể tiếp tục publish và consume.
3. Instance C bị restart hoặc đứt mạng.
4. C vẫn giữ password cũ trong environment, không mở lại AMQP connection được.
5. Khi A/B lần lượt reconnect, các instance khác cũng có thể thất bại.
6. Backlog tăng dù ngay sau khi đổi password hệ thống trông vẫn bình thường.

Điểm nguy hiểm là **trạng thái xác thực cũ bị che bởi các connection sống lâu**. Lỗi có thể bùng phát trong một đợt failover khác, không đúng thời điểm cập nhật secret.

**Không coi đổi password trước rồi “restart sau” là trình tự mặc định an toàn.** Với cùng user chỉ có một credential hợp lệ tại một thời điểm theo cấu hình cụ thể, cần cơ chế overlap/rollback riêng hoặc chấp nhận thời gian gián đoạn có kiểm soát.

## 5. Phương án khuyến nghị: hai danh tính chồng lấp

Nếu broker và chính sách bảo mật cho phép, hãy cấp hai danh tính cho cùng workload:

- **Blue:** `orders_worker_blue` đang phục vụ hệ thống.
- **Green:** `orders_worker_green` mới, có quyền tương đương ở phạm vi tối thiểu.
- Giữ blue còn hiệu lực trong khi các replica chuyển dần sang green.
- Thu hồi blue sau khi mọi client đã xác minh không còn phụ thuộc.

~~~mermaid
flowchart TD
    A["Blue đang chạy"] --> B["Tạo green + quyền đúng vhost"]
    B --> C["Smoke test green"]
    C --> D["Rollout canary"]
    D --> E{"Login, publish, consume, commit OK?"}
    E -->|"Không"| R["Dừng rollout, rollback blue"]
    E -->|"Có"| F["Rolling update các replica còn lại"]
    F --> G["Kiểm tra không còn client cần blue"]
    G --> H["Thu hồi blue"]
    H --> I["Hậu kiểm backlog, DLQ, outbox"]
~~~

Chiến lược này làm giảm rủi ro mất toàn bộ khả năng reconnect, vì blue còn tồn tại trong lúc green được thử nghiệm. Nhưng có một khoảng thời gian **hai user cùng được cấp quyền**; phải đặt lịch thu hồi và audit, không để danh tính cũ tồn tại vô hạn.

### 5.1. Runbook blue/green

| Giai đoạn | Hành động | Tiêu chí chuyển tiếp |
| --- | --- | --- |
| Kiểm kê | Liệt kê pod, worker, scheduled jobs, bridge, vhost, broker, secret versions | Không bỏ sót tác nhân dùng credential cũ |
| Tạo green | Cấp user/credential mới, gán đúng permissions | Green login đúng broker/vhost |
| Kiểm thử độc lập | Publish và consume một message thử có ID riêng | Route, ACK và business commit thành công |
| Canary | Một replica sử dụng green | Không có auth/TLS/permission lỗi |
| Rollout | Thay từng nhóm nhỏ, không dừng mọi consumer cùng lúc | Connection mới thực sự dùng green |
| Xác minh | Kiểm tra backlog, confirms/returns, DLQ, logs | Tất cả workload đã chuyển |
| Thu hồi blue | Vô hiệu hóa danh tính/secret cũ theo chính sách | Blue không mở được connection mới |
| Hậu kiểm | Đối soát dữ liệu và hệ thống giám sát | Không có message thất lạc hoặc backlog chưa xử lý |

Nếu credential cũ đã bị lộ nghiêm trọng, ưu tiên **thu hồi khẩn cấp** theo chính sách an ninh. Khi đó có thể phải chấp nhận gián đoạn có kiểm soát; không nên kéo dài khoảng chồng lấp chỉ để cố đạt zero downtime.

## 6. Quyền RabbitMQ: đăng nhập được chưa phải dùng được

RabbitMQ thường phân quyền theo **virtual host** và thao tác `configure`, `write`, `read` đối với tài nguyên. Một principal có thể xác thực thành công nhưng không có quyền làm việc trên queue hoặc exchange.

| Tác vụ | Thao tác broker | Quyền cần kiểm chứng |
| --- | --- | --- |
| `RabbitTemplate` publish | Ghi vào exchange | `write` trên exchange |
| `@RabbitListener` nhận | Đọc và ACK delivery từ queue | `read` trên queue |
| `RabbitAdmin` declare topology | Tạo/kiểm tra exchange, queue, binding | `configure` và những quyền liên quan theo thao tác |
| DLQ replayer | Consume DLQ, publish lại vào exchange | `read` DLQ, `write` exchange đích |
| Giám sát broker | Truy cập management/metrics | Quyền quan sát riêng |

Tài khoản green nên có **quyền tối thiểu cần thiết**, không phải quyền quản trị toàn hệ thống. Nếu topology đã được provision bởi hạ tầng, ứng dụng có thể không cần quyền declare; lúc đó phải tránh để `RabbitAdmin` tự khai báo ngoài dự kiến.

Trong smoke test cần kiểm tra:

- Có vào được **đúng virtual host** không?
- Có publish được **đúng exchange** không?
- Message có vào đúng queue qua **binding** không?
- Listener có consume/ACK thành công không?
- Ứng dụng có tự declare topology không, nếu có thì quyền green đã đủ chưa?

Phân biệt **authentication failed** (không xác thực được) với **authorization failed** (đã xác thực nhưng thiếu quyền). Hai loại này cần hành động khắc phục khác nhau.

## 7. Cấu hình Spring Boot bằng secret bên ngoài

Ví dụ Spring Boot 3.x với `spring-boot-starter-amqp`:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5672
    virtual-host: /orders

    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}

    requested-heartbeat: 30s
    connection-timeout: 5s

    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true

    listener:
      simple:
        acknowledge-mode: auto
        concurrency: 2
        max-concurrency: 4
        prefetch: 20
~~~

Giá trị `RABBITMQ_USERNAME`/`RABBITMQ_PASSWORD` phải được inject an toàn bởi môi trường chạy. Đoạn cấu hình **không** cho phép tự hot-reload mật khẩu khi Secret Manager thay đổi. Nếu process đọc environment lúc khởi động, thay secret bên ngoài thường phải đi kèm **rolling redeploy/restart** để tạo process và connection mới.

### 7.1. Từng nguồn secret có hành vi khác nhau

| Nguồn | Khi secret được cập nhật | Cách nạp mới |
| --- | --- | --- |
| Environment variables | Environment của process đang chạy không tự đổi | Restart/redeploy process |
| Kubernetes Secret mount dạng volume | File có thể được cập nhật theo cơ chế/khoảng trễ của Kubernetes | App cần đọc lại file và mở connection phù hợp |
| Kubernetes Secret mount bằng `subPath` | Không có cơ chế cập nhật tự động tương đương mount thông thường | Thiết kế rollout/restart |
| Secret Manager SDK | SDK có thể trả về secret version mới | Phải cập nhật connection authentication, không chỉ SDK cache |
| Keystore/truststore TLS | File mới có thể đã xuất hiện | SSL context/connection mới cần nạp file |

**Không giả định** thay một file trên disk sẽ thay credential đang dùng trong JVM. Về nguyên tắc cần cả **đọc secret mới** và **chuyển sang connection mới hoặc cơ chế refresh được hỗ trợ**.

### 7.2. Restart so với refresh tại runtime

Có hai mô hình:

**Rolling restart:** từng instance dừng/drain, process mới đọc secret green và tạo connection mới. Đây là đường tương đối dễ kiểm tra khi dùng password tĩnh.

**Dynamic credential refresh:** một credential provider/token manager lấy secret mới rồi dùng cơ chế refresh/re-authentication hoặc mở lại connection theo API thư viện. Cách này phải được xác minh với **RabbitMQ, RabbitMQ Java client và Spring AMQP version cụ thể**; không tự giả định mọi loại credential đều có thể thay trên connection đang sống.

Đừng tùy tiện sửa password trên bean `CachingConnectionFactory` rồi cho rằng mọi channel, listener và publisher confirms sẽ chuyển nguyên tử sang identity mới. Nếu muốn hot reload, cần thiết kế và kiểm thử lifecycle đầy đủ.

## 8. Cấu hình topology và kiểm chứng đường gửi/nhận

Để smoke test sau rotation, xây một đường đi cụ thể từ exchange tới listener. Ví dụ:

~~~java
package com.example.rabbit.security;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersTopology {

    static final String EXCHANGE = "orders.events.exchange";
    static final String KEY = "order.changed";
    static final String QUEUE = "orders.events.queue";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(QUEUE)
                .deadLetterExchange("orders.dlx")
                .deadLetterRoutingKey("order.failed")
                .build();
    }

    @Bean
    Binding ordersBinding(
            DirectExchange ordersExchange, Queue ordersQueue) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with(KEY);
    }

    @Bean
    DirectExchange ordersDlx() {
        return new DirectExchange("orders.dlx", true, false);
    }

    @Bean
    Queue ordersDlq() {
        return QueueBuilder.durable("orders.events.dlq").build();
    }

    @Bean
    Binding ordersDlqBinding(
            DirectExchange ordersDlx, Queue ordersDlq) {
        return BindingBuilder.bind(ordersDlq)
                .to(ordersDlx)
                .with("order.failed");
    }
}
~~~

Các bean trên có thể được `RabbitAdmin` khai báo nếu được cấu hình. Trong rotation, green cần quyền phù hợp để sử dụng hoặc khai báo tài nguyên. Một lỗi `PRECONDITION_FAILED` do queue argument không tương đương **không phải lỗi password**, và không thể chữa bằng việc retry authentication.

Nếu đã có topology production, không redeclare queue với arguments khác chỉ để thử secret. Dùng một queue thử biệt lập hoặc kiểm tra bằng thao tác không làm thay đổi tài nguyên đang chạy.

## 9. Producer: publisher confirms không tự cứu message khi reconnect

Ví dụ event:

~~~java
package com.example.rabbit.security;

import java.util.UUID;

public record OrderChanged(
        UUID eventId, String orderId, long version, String status
) {}
~~~

Khi `RabbitTemplate` gửi event rồi connection bị đóng ngay trong đợt rotation, có thể xảy ra:

- Broker **chưa nhận** message.
- Broker **đã nhận** nhưng publisher chưa thấy confirm.
- Broker đã nhận nhưng **không route được** tới queue vì binding/permission.
- Client bị timeout và không thể biết chắc trạng thái cuối cùng.

Vì vậy `convertAndSend()` trả về không exception **không đủ** để khẳng định event đã được consumer xử lý.

### 9.1. Ví dụ xác nhận publish

~~~java
package com.example.rabbit.security;

import java.util.concurrent.TimeUnit;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ConfirmedOrderPublisher {

    private final RabbitTemplate template;

    public ConfirmedOrderPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void send(OrderChanged event) throws Exception {
        String id = event.eventId().toString();
        var cd = new CorrelationData(id);

        template.convertAndSend(
                OrdersTopology.EXCHANGE,
                OrdersTopology.KEY,
                event,
                message -> {
                    message.getMessageProperties().setMessageId(id);
                    message.getMessageProperties().setDeliveryMode(
                            MessageDeliveryMode.PERSISTENT);
                    return message;
                },
                cd);

        var confirm = cd.getFuture().get(5, TimeUnit.SECONDS);

        if (!confirm.isAck()) {
            throw new IllegalStateException(
                    "Publisher NACK: " + confirm.getReason());
        }

        if (cd.getReturned() != null) {
            throw new IllegalStateException(
                    "Message không route được vào queue");
        }
    }
}
~~~

Đoạn mã minh họa kiểm tra publish, chưa phải toàn bộ outbox relay. Để chuyển DTO thành JSON cần cấu hình message converter phù hợp. Đồng thời cần bật correlated confirms, publisher returns và mandatory như ví dụ YAML.

**Timeout của `getFuture().get(...)` tạo ra kết quả chưa chắc chắn.** Đừng phát lại bằng một `eventId` mới. Một outbox giữ event ID/payload bền vững giúp relay thử lại an toàn.

### 9.2. Outbox bảo vệ cửa sổ trước publish

Nếu cập nhật Order DB và publish RabbitMQ là hai thao tác riêng:

~~~text
COMMIT orders.status = PAID
         |
         | process bị restart vì rotation
         v
RabbitTemplate.publish chưa xảy ra
~~~

Event có thể **mất hoàn toàn**. Phương án thường dùng là ghi bảng `outbox_events` trong **cùng database transaction** với thay đổi nghiệp vụ; relay đọc outbox, publish bằng `eventId` ổn định và chỉ đánh dấu đã publish sau khi quan sát xác nhận phù hợp.

Nếu relay bị restart sau broker confirm nhưng trước lúc mark outbox, nó có thể publish lại. Do đó outbox hướng đến **at-least-once publish**, cần consumer chống trùng.

## 10. Consumer: sau DB commit nhưng trước ACK

Listener `AcknowledgeMode.AUTO` của Spring AMQP thường ACK khi listener xử lý thành công theo cơ chế container. Nó **không giống** `autoAck=true` vô điều kiện của RabbitMQ Java client.

~~~java
package com.example.rabbit.security;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersListener {

    private final IdempotentOrdersService service;

    public OrdersListener(IdempotentOrdersService service) {
        this.service = service;
    }

    @RabbitListener(queues = OrdersTopology.QUEUE)
    public void on(OrderChanged event) {
        service.applyOnce(event);
        // Đợi DB transaction commit rồi listener mới return.
    }
}
~~~

`IdempotentOrdersService` là service cần triển khai. Nếu app bị dừng vì rolling deployment **sau DB commit nhưng trước khi broker nhận ACK**, message có thể được redeliver sau reconnect. Consumer phải bảo vệ side effect bằng khóa ổn định.

Ví dụ bảng inbox:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Cách xử lý phù hợp là **insert marker và cập nhật nghiệp vụ trong cùng DB transaction**, có unique constraint để hai consumer đồng thời không thể thực thi effect hai lần. Nếu marker đã tồn tại, return thành công mà không áp dụng lại side effect; container có thể ACK delivery trùng.

Không dùng RabbitMQ delivery tag làm event ID. Tag thay đổi theo channel và không phù hợp làm khóa dedup xuyên reconnect/republish.

## 11. Ma trận những cửa sổ lỗi do credential rotation

| Cửa sổ | Hậu quả có thể xảy ra | Cách giảm rủi ro |
| --- | --- | --- |
| W1 — DB nguồn commit, publish chưa thực hiện | Event chưa từng vào broker | Transactional outbox |
| W2 — Publish đã gửi, confirm chưa nhận | Unknown outcome; retry có thể trùng | Cùng eventId, confirms/returns, outbox |
| W3 — Green login thành công nhưng quyền write thiếu | Publish thất bại dù connection mở | Kiểm tra authorization trên exchange |
| W4 — Green có quyền consume nhưng không đủ quyền declare | Listener không start/recover được | Smoke test `RabbitAdmin` và queue permissions |
| W5 — Listener đang xử lý thì pod dừng | DB có thể rollback, delivery redeliver | ACK sau commit, transaction hợp lệ |
| W6 — DB đã commit nhưng ACK chưa tới broker | Duplicate delivery | Inbox/idempotency |
| W7 — Secret store đã cập nhật, app vẫn dùng blue | Reconnect sau revoke thất bại | Rolling restart và kiểm chứng connection mới |
| W8 — TLS trust chưa cập nhật trước server cert | Handshake thất bại | Chồng lấp CA trust trước khi đổi cert |
| W9 — Đồng loạt restart mọi consumer | Backlog và recovery storm | Rolling rollout và capacity headroom |
| W10 — Retry liên tục khi auth sai | Kết nối không bao giờ thành công; log quá tải | Phân loại lỗi và rollback/correct secret |

**Authentication retry khác business retry.** Nếu credential sai, việc retry cùng mật khẩu vĩnh viễn không giải quyết vấn đề. Nếu message nghiệp vụ lỗi do DB tạm thời, có thể dùng retry có giới hạn và dead-letter theo chính sách. Không đánh đồng hai cơ chế trong một vòng lặp.

## 12. Triển khai rolling update và drain

Một đợt rotate credential trên nhiều replica nên hạn chế số consumer bị dừng cùng lúc:

1. Tạo green và smoke test từ đúng môi trường network.
2. Cập nhật secret nguồn và trigger deployment của canary.
3. Xác minh canary đã **mở connection mới** bằng green.
4. Theo dõi publisher confirm, listener, queue depth và lỗi authorization.
5. Rollout các replica còn lại theo từng nhóm.
6. Đợi các công việc đang chạy đạt trạng thái bền vững hoặc chấp nhận redelivery an toàn.
7. Đối chiếu số instance/connection còn dùng blue.
8. Thu hồi blue và theo dõi hậu kiểm.

### 12.1. Trên Kubernetes

Các thành phần cần cân nhắc:

- `Deployment` rolling strategy với `maxUnavailable`, `maxSurge`.
- `PodDisruptionBudget` nếu có để kiểm soát gián đoạn tự nguyện.
- `terminationGracePeriodSeconds` đủ cho listener xử lý một tác vụ có giới hạn.
- Shutdown hook hoặc listener stop lifecycle phù hợp, không nhận thêm delivery khi đang drain.
- Readiness/liveness đúng mục đích, tránh restart liên tục chỉ vì broker outage ngắn.
- Cơ chế trigger rollout khi secret thay đổi nếu ứng dụng chỉ nạp environment lúc startup.

**Kubernetes Secret cập nhật không mặc định restart các pod**. Environment của process đang chạy không thay đổi theo Secret update. Secret volume có thể cập nhật file, nhưng ứng dụng vẫn phải đọc lại và sử dụng credential trên connection phù hợp; mount qua `subPath` có hành vi cập nhật khác.

### 12.2. Có drain cũng phải chịu được redelivery

Không thể bảo đảm mọi in-flight message đều xử lý xong trước lúc process bị kill. Ví dụ transaction DB mất 20 giây trong khi termination grace chỉ 10 giây; pod có thể bị dừng giữa chừng.

Một hệ thống đúng phải chịu được cả:

- DB rollback trước ACK → xử lý lại.
- DB commit trước ACK → phát hiện duplicate và không lặp effect.
- Publish thành công nhưng confirm chưa đến → relay thử lại từ outbox.

Vì vậy rotation có downtime rất thấp **không đồng nghĩa** không có duplicate delivery.

## 13. Token rotation và refresh tại runtime

Với token OAuth 2.0 có thời hạn, rotation có thể diễn ra thường xuyên hơn password. Kế hoạch cần:

- Lấy token bằng identity provider đáng tin cậy, không hard-code vào source code.
- Refresh **trước khi token hết hạn**, có khoảng dự phòng cho jitter và network latency.
- Không để tất cả instance đồng loạt gọi token endpoint gây load spike.
- Theo dõi token refresh failure riêng với RabbitMQ connection failure.
- Kiểm tra thư viện AMQP/client và broker có hỗ trợ cập nhật credentials trên connection đang hoạt động hay phải reconnect.
- Khi chưa có token hợp lệ, không âm thầm drop event: giữ trong outbox và phát lại sau recovery.

Không nên khẳng định một phương thức refresh cụ thể tồn tại trong mọi phiên bản `CachingConnectionFactory` hoặc mọi auth backend. Khi dùng cơ chế runtime credentials provider, cần kiểm thử compatibility và khả năng phục hồi những channel, listener, pending publisher confirms trong phiên bản triển khai.

## 14. Luân chuyển TLS server cert, client cert và CA

**Password/token rotation và TLS certificate rotation có các thành phần khác nhau.** Thay chứng chỉ server còn liên quan hostname validation, trust chain và SSL context của client.

### 14.1. Thay CA cho broker

Một trình tự an toàn khi broker sắp sử dụng cert ký bởi CA mới:

~~~text
Giai đoạn 1: client tin CA-old
Giai đoạn 2: client tin CA-old và CA-new
Giai đoạn 3: broker chuyển sang server cert từ CA-new
Giai đoạn 4: buộc client mở connection mới và xác minh TLS
Giai đoạn 5: khi mọi client đã chuyển, bỏ CA-old
~~~

Nếu broker dùng CA mới **trước khi client tin CA đó**, connection mới có thể fail TLS handshake. Các connection TLS đang mở bằng chứng chỉ cũ có thể vẫn hoạt động trong một thời gian; như trường hợp password, điều này **che giấu rủi ro reconnect**.

### 14.2. Thay client certificate (mTLS)

Với mTLS, ứng dụng cần:

1. Cấp client certificate và private key mới.
2. Bảo đảm broker chấp nhận chain và mapping identity của certificate mới.
3. Cập nhật keystore được bảo vệ của ứng dụng.
4. Tạo SSL context/connection mới đã nạp cert mới hoặc dùng cơ chế reload đã kiểm chứng.
5. Xác minh connection mới và publish/consume.
6. Thu hồi client certificate cũ theo chính sách.

Không ghi private key hoặc nội dung keystore ra log. Không vô hiệu hostname verification hoặc certificate validation chỉ để “cho rotation chạy được”.

### 14.3. Phân loại lỗi TLS

| Hiện tượng | Khả năng chính |
| --- | --- |
| TLS handshake fail, unknown CA | Truststore chưa có CA mới |
| Hostname mismatch | SAN/hostname hoặc DNS không phù hợp |
| Client cert rejected | mTLS certificate, chain hoặc identity mapping không hợp lệ |
| TLS OK nhưng AMQP auth fail | Username/password/token/vhost sai |
| AMQP auth OK nhưng declare fail | Quyền `configure` thiếu hoặc topology xung đột |
| Connection cũ OK nhưng mở mới fail | Secret/trust/SSL context chưa được refresh |

## 15. Monitoring và tiêu chí hoàn thành

Để tránh báo “rotation thành công” quá sớm, cần đo **connection mới bằng credential nào** cùng tiến độ message:

| Chỉ số / sự kiện | Lý do cần |
| --- | --- |
| Số connection đang hoạt động theo principal/version | Xác minh green đã tiếp quản |
| Authentication failures | Phát hiện credential sai hoặc hết hạn |
| Authorization failures | Phát hiện thiếu quyền queue/exchange/vhost |
| TLS handshake failures | Phát hiện cert/CA/hostname mismatch |
| Reconnect attempts, connection churn | Nhận biết recovery storm |
| Listener registered/active | Biết consumer đã phục hồi |
| Publisher confirm ACK/NACK/timeout | Phân biệt publish đã xác nhận và chưa rõ |
| Publisher returns | Phát hiện binding/routing sai |
| Queue ready/unacked và thời gian chờ | Đo backlog, in-flight workload |
| Redelivery count và dedup hits | Đo tác động của rolling restart |
| Outbox pending, oldest age | Nhận biết message còn kẹt trước publish |
| DLQ size/oldest age | Nhận biết poison message chưa xử lý |
| Time to first successful business commit | Đo phục hồi nghiệp vụ |

Các tên trên là **khái niệm metric**, không mặc định Spring Boot tự xuất tất cả. Nhãn nên gồm broker/vhost, workload, instance và **credential version không nhạy cảm**. Không đưa password/token vào metric labels.

### 15.1. Những điều phải đúng trước khi thu hồi blue

- Các instance/công việc nền đã có version green.
- Đã chủ động xác minh connection **mở mới** bằng green.
- Publisher publish đúng exchange, có confirms/returns phù hợp.
- Listener nhận và xử lý message đến DB commit.
- Không còn phiên bản ứng dụng cũ phụ thuộc blue để reconnect.
- Outbox/DLQ không có backlog bất thường không giải thích được.
- Đã chừa phương án rollback hoặc xác nhận có thể thu hồi an toàn.

Sau khi blue bị thu hồi, cần kiểm chứng **new connection bằng blue bị từ chối** và **green vẫn hoạt động**.

## 16. Kịch bản kiểm thử rotation

Chỉ thực hiện trên môi trường thử nghiệm với broker, vhost và message riêng. Không áp dụng thao tác vô hiệu hóa user/cert lên production ngoài quy trình change management.

### A. Happy path blue → green

1. Tạo green user, cấp quyền tối thiểu.
2. Kết nối thử từ đường mạng ứng dụng.
3. Publish một event với ID thử và xác minh confirm/route.
4. Cho listener green xử lý, ACK và ghi kết quả.
5. Rolling deployment các replica.
6. Xác minh green được dùng bởi tất cả instance; thu hồi blue.

**Kỳ vọng:** luồng message tiếp tục vận hành và không còn phụ thuộc blue.

### B. Secret đã đổi nhưng process chưa reload

1. Chạy pod bằng blue.
2. Cập nhật secret trong Secret Manager/Kubernetes.
3. Giữ process đang chạy, không restart.
4. Xác minh vẫn có thể tồn tại connection blue.
5. Thử mở connection mới với thông tin process thực đang giữ.

**Kỳ vọng:** nhận thấy secret store update không đồng nghĩa application/connection update.

### C. Thu hồi blue trước khi rollout xong

1. Giữ một replica vẫn dùng blue.
2. Thu hồi blue trong broker test.
3. Buộc replica đó reconnect.
4. Quan sát authentication failure và backlog.
5. Khôi phục hoặc chuyển replica sang green đúng cách.

**Kỳ vọng:** phân biệt connection cũ vẫn sống với khả năng reconnect thực sự.

### D. Green có password đúng nhưng quyền thiếu

1. Cấp user green có thể login nhưng thiếu quyền publish/consume/declare.
2. Thử từng tác vụ.
3. Quan sát authorization failures.
4. Chỉ cấp lại quyền tối thiểu cần thiết, chạy lại test.

**Kỳ vọng:** connection healthy không đồng nghĩa topology/consumer healthy.

### E. Publish đã tới broker nhưng confirm mất

1. Ghi event `E42` trong outbox.
2. Publish rồi gây disconnect trước khi caller có confirm.
3. Giữ trạng thái outbox có thể retry.
4. Sau reconnect, publish lại cùng `E42`.
5. Xác minh consumer chặn duplicate side effect.

**Kỳ vọng:** không làm mất event và không áp dụng effect trùng.

### F. Consumer DB commit nhưng ACK bị mất

1. Consumer nhận `E43`, commit DB và marker inbox.
2. Dừng connection trước ACK broker nhận.
3. Cho E43 redeliver sau recovery.
4. Xác minh marker chặn cập nhật lần hai.

**Kỳ vọng:** xử lý đúng redelivery trong rolling update.

### G. CA rollover

1. Cài cả CA-old và CA-new vào truststore client.
2. Thay cert broker trong môi trường test bằng cert ký CA-new có SAN đúng.
3. Mở connection TLS mới, xác minh auth và listener.
4. Sau khi chuyển đủ client mới bỏ CA-old.

**Kỳ vọng:** không có TLS handshake window bị hở.

### H. Token provider lỗi

1. Giả lập provider không cấp token mới.
2. Để token cũ gần expiry.
3. Quan sát refresh failure và reconnect.
4. Xác minh publisher giữ event trong outbox.
5. Phục hồi provider, đo thời gian hoạt động trở lại.

**Kỳ vọng:** token lỗi không làm mất message chưa publish.

### I. Rolling restart so với restart đồng loạt

1. Phát tải cố định và đo throughput.
2. Dừng mọi consumer đồng thời trong test rồi đo backlog.
3. So sánh với rolling restart từng replica.
4. Đo thời gian bắt kịp backlog, redelivery và confirm timeout.

**Kỳ vọng:** thấy lợi ích của drain/capacity headroom và giới hạn của nó.

### J. Sai binding sau rotation

1. Đăng nhập bằng green thành công.
2. Cố tình làm sai binding trong môi trường test.
3. Publish với mandatory/returns.
4. Xác minh message return hoặc route failure được ghi nhận.
5. Khôi phục topology và retry outbox.

**Kỳ vọng:** biết phân biệt auth success với routing success.

## 17. Runbook khi rotation thất bại

Khi rotation gây ngừng publish hoặc backlog, điều tra theo thứ tự:

1. **Khoanh vùng:** broker/vhost nào, workload nào, credential version nào?
2. **Phân loại lỗi:** TLS handshake, authentication, authorization, topology, routing hay business handler.
3. **Dừng rollout tiếp:** đừng lan rộng cấu hình lỗi sang mọi instance.
4. **Giữ dữ liệu:** không xóa outbox, queue hoặc DLQ chỉ để giảm số liệu backlog.
5. **Smoke test green:** dùng đúng network/vhost/permission của ứng dụng.
6. **Khôi phục hoặc rollback:** quay về blue còn hiệu lực nếu an toàn, hoặc sửa green.
7. **Giảm reconnect storm:** backoff hợp lý, tránh liveness restart loop.
8. **Xác nhận business recovery:** publisher confirm, listener delivery và DB commit.
9. **Đối soát trùng/mất:** theo event ID trong outbox, consumer inbox và DLQ.
10. **Hậu kiểm:** cập nhật kế hoạch rotation, danh sách instance và thời điểm thu hồi.

Ví dụ log có ý nghĩa, không chứa secret:

~~~text
workload=orders-consumer broker=rabbitmq.internal
vhost=/orders credentialVersion=green-2026-11
event=amqp_authentication_failed

workload=orders-consumer broker=rabbitmq.internal
vhost=/orders credentialVersion=green-2026-11
event=listener_recovered queue=orders.events.queue

workload=orders-publisher broker=rabbitmq.internal
credentialVersion=green-2026-11
event=publisher_confirmed eventId=E42
~~~

Đây là định dạng **minh họa instrumentation riêng**, không phải mọi log Spring AMQP mặc định đều có trường `credentialVersion`.

## 18. Sai lầm phổ biến và checklist

| Sai lầm | Hậu quả | Phòng tránh |
| --- | --- | --- |
| Đổi password cùng user trước khi update pod | Reconnect với secret cũ thất bại | Blue/green hoặc runbook đồng bộ có kiểm chứng |
| Coi Secret update là connection refresh | App vẫn dùng danh tính cũ | Rolling restart hoặc refresh đã kiểm thử |
| Thấy connection đang mở rồi cho rằng đã dùng green | Connection có thể vẫn là blue | Buộc mở connection mới và xác minh |
| Thu hồi blue ngay sau canary | Job/pod cũ không reconnect được | Kiểm kê tất cả workload |
| Cấp green quyền quản trị quá mức | Tăng blast radius khi lộ secret | Least privilege |
| Quên kiểm tra RabbitAdmin | Login OK nhưng declare fail | Kiểm tra configure/read/write |
| Tắt TLS verify vì đổi CA lỗi | Rủi ro kết nối broker giả | Dual trust/hostname check |
| Restart mọi pod cùng lúc | Queue backlog, reconnect storm | Rolling update, drain |
| Retry publish với ID mới | Duplicate business effect | Outbox + stable event ID |
| ACK trước DB commit | Mất side effect khi crash | Commit trước ACK |
| Không có inbox/dedup | Redelivery gây tác dụng trùng | Unique key và transaction |
| Xóa DLQ hoặc outbox khi lỗi | Mất dữ liệu điều tra/replay | Giữ và đối soát |

### Checklist production

- [ ] Xác định secret type, broker, vhost và tất cả workload dùng credential hiện tại.
- [ ] Không lưu bí mật trong source, log, command history hoặc telemetry.
- [ ] Đã có danh tính green/chiến lược overlap và rollback phù hợp chính sách.
- [ ] Green có quyền tối thiểu, đúng exchange, queue, binding và vhost.
- [ ] Secret mới được **nạp trong process** và **sử dụng để mở connection mới**.
- [ ] Có canary, rolling update, drain và giám sát connection/consumer.
- [ ] Có publisher confirms/returns, transactional outbox cho message quan trọng.
- [ ] Consumer commit trước ACK, idempotency bảo vệ redelivery.
- [ ] Retry connection và business retry được phân biệt; DLQ có điểm dừng.
- [ ] TLS certificate/CA rotation không tắt xác minh certificate.
- [ ] Có metric auth errors, broker readiness, queue depth, outbox, DLQ và duplicate suppression.
- [ ] Đã kiểm thử mất confirm, mất ACK, secret stale, blue revoke sớm, thiếu permission và TLS mismatch.
- [ ] Danh tính cũ chỉ bị thu hồi khi hoàn tất xác minh hoặc khi security incident đòi hỏi thu hồi khẩn.

## 19. Tổng kết

**Luân chuyển thông tin kết nối RabbitMQ** liên quan đến ba vấn đề: **secret mới được chấp nhận**, **ứng dụng thực sự sử dụng secret đó trên connection mới**, và **message đang xử lý vẫn được bảo vệ trong khoảng ngắt kết nối**. Một thay đổi trong Secret Manager hoặc Kubernetes chưa hoàn thành rotation nếu các process còn giữ credential cũ hoặc không thể reconnect.

Trong **SPRING_AMQP**, quy trình đáng tin cậy thường là **chuẩn bị green → smoke test → canary/rolling rollout → xác minh publisher, listener và kết quả nghiệp vụ → thu hồi blue**. Cơ chế `CachingConnectionFactory` và listener container giúp phục hồi connection/channel, nhưng không thể tự loại bỏ cửa sổ publish chưa confirm hoặc commit DB trước ACK. Vì thế vẫn cần **outbox, confirms/returns, consumer idempotency, retry/DLQ và giám sát đầu cuối**.

Đánh giá rotation hoàn tất bằng ba câu hỏi: **Kết nối mới sử dụng credential nào? Những message dở dang được phục hồi ra sao? Và đã chứng minh không còn workload phụ thuộc credential cũ trước khi thu hồi chưa?**
