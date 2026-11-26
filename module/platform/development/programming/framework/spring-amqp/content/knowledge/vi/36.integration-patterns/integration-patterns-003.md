# Routing key theo loại sự kiện, phiên bản hoặc khách hàng

## 1. Vì sao routing key là một phần của hợp đồng tích hợp?

Trong ứng dụng **Spring AMQP** với **RabbitMQ**, producer gửi message qua `RabbitTemplate` tới một **exchange**. Exchange so khớp **routing key** của message với các **binding** để chuyển message vào một hoặc nhiều **queue**; consumer xử lý bằng `@RabbitListener`. Khi hệ thống chỉ có sự kiện `order.created`, ta có thể dùng một routing key đơn giản. Nhưng hệ thống nhiều dịch vụ, nhiều phiên bản contract và nhiều nhóm khách hàng cần cách đặt tên có cấu trúc để:

- Dịch vụ Kế toán chỉ nhận sự kiện **đơn hàng đã thanh toán**, không phải mọi thay đổi đơn hàng.
- Consumer cũ và mới nhận đúng **phiên bản schema** mà chúng có thể giải mã.
- Một luồng nghiệp vụ xử lý riêng cho nhóm khách hàng **enterprise** hoặc tenant đã được phân vùng.
- Thêm loại sự kiện mới mà không phải sửa mọi producer/consumer.
- Quan sát được message đi đâu, tại sao không routable và khôi phục an toàn khi retry/DLQ.

Đó là **mẫu tích hợp theo routing key**: mã hóa thông tin *cần cho định tuyến* vào khóa có quy ước ổn định, thay vì để producer biết tên queue của từng consumer.

~~~text
                  Order Service
                 RabbitTemplate
                       |
       routingKey=orders.paid.v1.enterprise
                       |
                       v
               TopicExchange
              orders.events.x
                 /    |     \
                /     |      \
               v      v       v
         billing.v1  audit   enterprise
           queue     queue      queue
              |        |          |
              v        v          v
       @RabbitListener ...     @RabbitListener
~~~

Trong sơ đồ, **mỗi queue là một bản sao logic của một publish khi binding của queue đó khớp**. Nếu hai binding khác nhau của *cùng một queue* đều khớp, RabbitMQ không vì thế tạo hai bản sao của cùng publish trong queue đó. Điều này khác với message bị publish lại hoặc redeliver do lỗi ACK.

**Sau bài học**, bạn có thể:

1. Chọn `direct` hay `topic` exchange cho định tuyến sự kiện.
2. Thiết kế routing key theo **loại sự kiện, phiên bản và nhóm khách hàng** có kiểm soát.
3. Dùng `*` và `#` đúng với số phân đoạn trong topic exchange.
4. Khai báo exchange, queue và binding bằng Spring AMQP; publish bằng `RabbitTemplate` và nhận bằng `@RabbitListener`.
5. Tách yêu cầu **routing** khỏi **bảo mật tenant**; quản lý schema evolution và rollout v1/v2.
6. Kiểm thử routing, publisher confirms/returns, DLQ, idempotency và quan sát khi vận hành.

## 2. Nền tảng: routing key, binding key và exchange type

### 2.1. Routing key nằm trên message, binding key nằm trên topology

| Thành phần | Ví dụ | Ai cấu hình |
| --- | --- | --- |
| **Exchange** | `orders.events.x` | Chủ sở hữu topology/đội hạ tầng. |
| **Exchange type** | `topic` | Cách broker so khớp routing key. |
| **Routing key** của publish | `orders.paid.v1.enterprise` | Producer, theo contract sự kiện. |
| **Binding key/pattern** | `orders.paid.v1.*` | Consumer/topology owner. |
| **Queue** | `billing.order-paid.v1.q` | Tài nguyên broker chứa các message chờ xử lý. |
| **Consumer** | `@RabbitListener(queues=...)` | Dịch vụ sử dụng một queue cụ thể. |

Khi publish:

~~~java
rabbitTemplate.convertAndSend(
        "orders.events.x",
        "orders.paid.v1.enterprise",
        payload);
~~~

Producer **không chỉ định queue**. Broker nhìn vào exchange `orders.events.x`, tìm các binding phù hợp, rồi đưa message vào queue. Không có binding phù hợp thì publish có thể **unroutable**; nó không tự chuyển sang queue có tên gần giống routing key.

### 2.2. Direct, topic và fanout: chọn đúng công cụ

| Exchange type | Cách dùng routing key | Phù hợp khi |
| --- | --- | --- |
| **Direct** | Khớp **chính xác** chuỗi routing key với binding key. | Một tập loại sự kiện nhỏ, không cần wildcard. |
| **Topic** | So khớp các phân đoạn ngăn bằng dấu `.` với pattern `*` hoặc `#`. | Muốn lọc theo loại sự kiện, phiên bản, audience/tenant bằng quy ước nhiều phân đoạn. |
| **Fanout** | Bỏ qua routing key. | Phát cùng sự kiện tới mọi queue đã bind mà không cần phân loại. |
| **Headers** | So khớp headers theo điều kiện của exchange. | Routing dựa vào thuộc tính không thuận tiện mã hóa vào một chuỗi chủ đề; cân nhắc tính portable và độ phức tạp. |

RabbitMQ có **default exchange** tên `""`, một direct exchange đặc biệt tự bind các queue bằng tên queue. Ví dụ `rabbitTemplate.convertAndSend("", "billing.q", payload)` phát trực tiếp đến `billing.q`. Cách này hữu ích cho point-to-point, nhưng làm producer biết queue đích; không thay thế một **event topic exchange** dùng cho nhiều consumer độc lập.

**Điểm dễ nhầm:** binding `orders.*.v1.*` trên một **DirectExchange** là chuỗi literal có dấu `*`, *không* phải wildcard. Phải dùng **TopicExchange** để có ngữ nghĩa wildcard.

### 2.3. Cú pháp wildcard của RabbitMQ topic exchange

Routing key là một chuỗi gồm các **word/segment** phân cách bằng dấu chấm `.`. Hai wildcard chỉ có ý nghĩa trong **binding pattern**:

- `*` khớp **đúng một phân đoạn**.
- `#` khớp **không hoặc nhiều phân đoạn**.

Ví dụ:

| Binding key | Routing key | Khớp? | Giải thích |
| --- | --- | --- | --- |
| `orders.paid.v1.*` | `orders.paid.v1.enterprise` | **Có** | `*` khớp một từ `enterprise`. |
| `orders.paid.v1.*` | `orders.paid.v1` | **Không** | Thiếu một phân đoạn cuối. |
| `orders.*.v1.enterprise` | `orders.created.v1.enterprise` | **Có** | `*` khớp `created`. |
| `orders.*.v1.enterprise` | `orders.paid.v2.enterprise` | **Không** | Version khác. |
| `orders.paid.*.enterprise` | `orders.paid.v2.enterprise` | **Có** | Nhận cả v1, v2 nếu consumer xử lý được. |
| `orders.#` | `orders.paid.v1.enterprise` | **Có** | `#` khớp ba phân đoạn còn lại. |
| `orders.#` | `orders` | **Có** | `#` cũng có thể khớp **0** phân đoạn. |
| `orders.paid.v1.*` | `orders.paid.v1.tenant.t_acme` | **Không** | Pattern bốn phân đoạn, key có năm. |
| `orders.*.v1.tenant.*` | `orders.created.v1.tenant.t_acme` | **Có** | Pattern năm phân đoạn. |

Không dùng `*` hoặc `#` bên trong routing key do producer tạo như một cách “gửi tới tất cả”. Producer gửi **routing key cụ thể**; wildcard dành cho **binding của consumer**. Nếu muốn broadcast, bind queue phù hợp hoặc sử dụng fanout exchange.

**Giới hạn giao thức:** routing key của AMQP 0-9-1 là `shortstr`, tối đa **255 byte**, không phải 255 ký tự Unicode. Thiết kế segment ngắn, ổn định, dễ kiểm tra. Tránh dấu chấm bên trong một segment, segment rỗng, giá trị nhận trực tiếp từ người dùng và ký tự không được hợp đồng hỗ trợ.

## 3. Quy ước routing key khuyến nghị cho sự kiện

Với tập sự kiện đơn hàng, ta chọn **đúng bốn phân đoạn**:

~~~text
<aggregate>.<action>.<schema-version>.<audience>

orders.created.v1.standard
orders.created.v1.enterprise
orders.paid.v1.standard
orders.paid.v1.enterprise
orders.cancelled.v2.enterprise
~~~

| Phân đoạn | Nghĩa | Giá trị nên dùng |
| --- | --- | --- |
| `aggregate` | Nhóm nghiệp vụ/phạm vi sự kiện. | `orders`, `payments`, `shipments` theo registry. |
| `action` | Loại chuyển đổi/trạng thái nghiệp vụ. | `created`, `paid`, `cancelled`, `refunded`; thường là sự kiện **đã xảy ra**. |
| `schema-version` | Phiên bản hợp đồng payload của sự kiện đó. | `v1`, `v2`; đổi khi contract thay đổi theo quy tắc versioning. |
| `audience` | Nhóm khách hàng/luồng xử lý chung. | `standard`, `enterprise`, `internal`; **không phải customer ID bí mật**. |

Trong thiết kế này:

- `orders.paid` là **event type** ổn định.
- `v1` là **schema version của event**, **không** phải version release của service, Java runtime hay RabbitMQ.
- `enterprise` là **nhóm xử lý/routing**, không chứng thực người gửi thuộc enterprise.

Tập giá trị cần có **registry/hợp đồng được kiểm soát**. Không để mọi producer tự đặt `order-paid`, `orders.payment.success`, `paidOrder` cho cùng một sự kiện; chúng tạo sự không tương thích khó phát hiện.

### 3.1. Vì sao nên giữ số phân đoạn cố định?

Pattern như `orders.*.v1.*` hoạt động chính xác khi routing key có bốn phân đoạn. Nếu một producer thêm `region` ở cuối:

~~~text
orders.paid.v1.enterprise.apac   // 5 phân đoạn
~~~

Nó **không còn khớp** binding `orders.*.v1.*`. Đây là **breaking change của topology**, ngay cả khi nội dung JSON không đổi. Khi cần chiều routing mới, phải:

1. Thiết kế contract mới và khai báo binding tương ứng trước khi phát.
2. Hoặc giữ routing key bốn phân đoạn, đặt region vào payload/header nếu consumer có thể tự lọc.
3. Hoặc dùng exchange khác/schema routing khác và triển khai migration có kiểm soát.

Đừng thêm/bớt segment theo giá trị tùy chọn mà không định nghĩa quy tắc rõ ràng. Với topic routing, **shape của routing key là một phần của API tích hợp**.

### 3.2. Những thông tin không nên đưa vào key

**Không đưa** email, số điện thoại, số tài khoản, số thẻ, địa chỉ, token, URL chứa secret hoặc raw payload vào routing key. Broker/operator và các công cụ Management, tracing, policy, DLQ có thể nhìn thấy key này. Cũng không nên dùng `orderId` hoặc `eventId` làm phân đoạn routing mặc định: chúng có cardinality rất cao, không giúp ích cho những queue đăng ký theo nhóm và dễ làm topology phức tạp.

Nếu cần định tuyến theo từng khách hàng riêng, dùng **opaque tenant routing alias** đã cấp phát và giới hạn, cộng với ACL riêng phù hợp (mục 7). Mã hóa payload không che được routing key.

## 4. Thiết kế bindings theo người đăng ký

Một producer phát:

~~~text
orders.paid.v1.enterprise
~~~

Những consumer có thể cần nhận:

| Consumer/queue | Binding | Có nhận publish trên? |
| --- | --- | --- |
| Billing v1 | `orders.paid.v1.*` | Có. |
| Enterprise workflow v1 | `orders.*.v1.enterprise` | Có. |
| Audit tất cả orders | `orders.#` | Có. |
| Billing v2 | `orders.paid.v2.*` | Không. |
| Created-only v1 | `orders.created.v1.*` | Không. |

Lợi thế chính: **producer không cần biết** ai đang subscribe. Khi Billing cần thêm sự kiện `orders.refunded.v1.enterprise`, đội Billing có thể thêm binding, không bắt producer gọi thẳng một queue mới.

Lưu ý:

- Nhiều **queue khác nhau** khớp → một publish được đưa tới từng queue khớp.
- Một **queue** có nhiều binding đều khớp → không tạo hai bản sao chỉ vì hai binding đó.
- Một queue có **nhiều consumer** → competing consumers, mỗi delivery thường chỉ đến một consumer trong nhóm đó.
- Cần hai dịch vụ xử lý độc lập → dùng **hai queue**, không dùng hai listener cùng đọc một queue rồi kỳ vọng broadcast.

### 4.1. Không dùng `#` vô tội vạ

Binding `orders.#` phù hợp cho audit có chủ đích, nhưng có thể kéo vào hàng loạt event/version/audience mà consumer chưa hiểu. Nó làm tăng bộ nhớ/disk do queue nhận quá nhiều, tăng rủi ro lộ thông tin giữa nhóm khách hàng và có thể làm consumer chậm vì payload lạ.

Với consumer chỉ hỗ trợ v1, nên bind `orders.paid.v1.*` thay vì `orders.paid.#`. Với consumer audit thực sự nhận tất cả, phải hỗ trợ schema evolution, quyền truy cập và khả năng xử lý tải tương ứng.

### 4.2. Binding thuộc consumer contract

Một consumer tốt nên **tuyên bố rõ** event type và schema version nó hỗ trợ. Đưa quy tắc này vào file cấu hình, IaC/topology declarations hoặc contract tests. Không để producer hard-code danh sách queue consumer. Với RabbitMQ, thêm binding mới chỉ cần thay topology của exchange/queue; queue cũ vẫn có thể giữ message chưa xử lý.

## 5. Ví dụ Spring AMQP: TopicExchange và các queue theo contract

Các ví dụ tiếp theo dùng **Java 17+, Spring Boot 3.x, Spring AMQP 3.x**, RabbitMQ AMQP 0-9-1. Tên module/starter hoặc converter JSON có thể khác ở dòng Spring Boot 4.x; ý nghĩa routing key, `TopicExchange`, `RabbitTemplate` và `@RabbitListener` vẫn tương ứng khi chọn đúng phiên bản.

### 5.1. Maven

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ví dụ dùng Jackson `ObjectMapper`, thường có sẵn qua dependency Spring Boot JSON/Web trong dự án; nếu chỉ dùng starter AMQP mà không có Jackson Databind, cần thêm dependency Jackson 2 tương thích với BOM. Không lạm dụng `MessageConverter` nếu chưa thống nhất content type/type mapping với consumer.

### 5.2. Khai báo topology

~~~java
// OrderEventTopology.java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderEventTopology {
    public static final String EVENTS_X = "orders.events.x";
    public static final String BILLING_V1_Q = "billing.order-paid.v1.q";
    public static final String BILLING_V2_Q = "billing.order-paid.v2.q";
    public static final String ENTERPRISE_V1_Q = "enterprise.orders.v1.q";
    public static final String AUDIT_Q = "orders.audit.q";
    public static final String DLX = "orders.dead.x";
    public static final String DLQ = "orders.billing.dead.q";

    @Bean
    Declarables orderEventDeclarables() {
        TopicExchange events = new TopicExchange(EVENTS_X, true, false);
        DirectExchange dead = new DirectExchange(DLX, true, false);

        Queue billingV1 = QueueBuilder.durable(BILLING_V1_Q)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey("billing.failed")
                .build();
        Queue billingV2 = QueueBuilder.durable(BILLING_V2_Q)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey("billing.failed")
                .build();
        Queue enterprise = QueueBuilder.durable(ENTERPRISE_V1_Q).build();
        Queue audit = QueueBuilder.durable(AUDIT_Q).build();
        Queue deadQueue = QueueBuilder.durable(DLQ).build();

        Binding b1 = BindingBuilder.bind(billingV1)
                .to(events).with("orders.paid.v1.*");
        Binding b2 = BindingBuilder.bind(billingV2)
                .to(events).with("orders.paid.v2.*");
        Binding b3 = BindingBuilder.bind(enterprise)
                .to(events).with("orders.*.v1.enterprise");
        Binding b4 = BindingBuilder.bind(audit)
                .to(events).with("orders.#");
        Binding dlqBinding = BindingBuilder.bind(deadQueue)
                .to(dead).with("billing.failed");

        return new Declarables(
                events, dead,
                billingV1, billingV2, enterprise, audit, deadQueue,
                b1, b2, b3, b4, dlqBinding);
    }
}
~~~

Trong topology này:

- Billing v1 chỉ nhận `orders.paid.v1.*`.
- Billing v2 chỉ nhận `orders.paid.v2.*`.
- Luồng Enterprise v1 nhận tất cả action orders với `audience=enterprise`.
- Audit nhận `orders.#`, bao gồm **cả v1 và v2**, nên cần bảo đảm quyền truy cập/schema hỗ trợ.
- Hai billing queues được đặt DLX; nếu reject không requeue, broker có thể dead-letter tới queue `orders.billing.dead.q`. Hai queue còn lại **chưa có DLX** trong ví dụ và cần policy/thiết kế lỗi riêng nếu dùng production.

`Declarables` là nhóm tài nguyên RabbitAdmin có thể khai báo khi khởi động ứng dụng; không có nghĩa broker xóa/ghi đè exchange và queue đang tồn tại với arguments khác. Trong production, topology và DLX/TTL thường được quản lý qua IaC/RabbitMQ policies. Thay arguments của queue đã tồn tại có thể gây `PRECONDITION_FAILED`, cần migration có kiểm soát.

**Lưu ý tên:** `orders.events.x` là **TopicExchange**, không phải fanout. Một binding `orders.paid.v1.*` không bắt được `orders.paid.v1.tenant.t_acme` vì routing key có thêm phân đoạn.

## 6. Producer: tạo routing key có kiểm tra và publish

### 6.1. Không nối routing key từ dữ liệu đầu vào tùy ý

Routing key phải do **hợp đồng nghiệp vụ** quyết định. Ví dụ có tập sự kiện đã được duyệt:

~~~java
// OrderRoutingKey.java
import java.util.Set;

public final class OrderRoutingKey {
    private static final Set<String> TYPES = Set.of(
            "orders.created", "orders.paid", "orders.cancelled");
    private static final Set<String> AUDIENCES = Set.of(
            "standard", "enterprise", "internal");
    private static final Set<Integer> VERSIONS = Set.of(1, 2);

    private OrderRoutingKey() {
    }

    public static String of(String eventType, int schemaVersion,
                            String audience) {
        if (!TYPES.contains(eventType)) {
            throw new IllegalArgumentException("Unsupported event type");
        }
        if (!VERSIONS.contains(schemaVersion)) {
            throw new IllegalArgumentException("Unsupported schema version");
        }
        if (!AUDIENCES.contains(audience)) {
            throw new IllegalArgumentException("Unsupported audience");
        }
        return eventType + ".v" + schemaVersion + "." + audience;
    }
}
~~~

`OrderRoutingKey.of("orders.paid", 1, "enterprise")` tạo `orders.paid.v1.enterprise`. Nếu nhận chuỗi audience từ API không tin cậy, **phải xác định nhóm đã được cấp quyền từ ngữ cảnh nghiệp vụ tin cậy** trước khi gọi. Việc giá trị nằm trong whitelist không có nghĩa caller được phép chọn nó.

### 6.2. Payload có cùng event type/version với routing key

~~~java
// OrderEvent.java
public record OrderEvent(
        String eventId,
        String eventType,
        int schemaVersion,
        String audience,
        String orderId,
        long occurredAtEpochMillis) {
}
~~~

Phân biệt:

- **Routing key** cho broker chọn queue.
- **Message body** là hợp đồng dữ liệu nghiệp vụ. `eventType` và `schemaVersion` cần khớp route.
- **AMQP headers/properties** như `messageId`, `correlationId`, `contentType` giúp correlation và conversion, nhưng có thể bị producer không tin cậy giả mạo.

Nếu cần bảo vệ nội dung khỏi broker, body có thể được mã hóa tại tầng ứng dụng. Routing key vẫn **không mã hóa** và không nên chứa bí mật. Nếu cần chống sửa contract giữa các service không tin cậy, cân nhắc chữ ký/MAC theo chính sách bảo mật phù hợp; chỉ so khớp trường JSON không phải xác thực mật mã.

### 6.3. Gửi bằng RabbitTemplate

~~~java
// OrderEventPublisher.java
import java.util.Objects;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;
    private final ObjectMapper objectMapper;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate,
                               ObjectMapper objectMapper) {
        this.rabbitTemplate = rabbitTemplate;
        this.objectMapper = objectMapper;
    }

    public CorrelationData publish(OrderEvent event)
            throws JsonProcessingException {
        Objects.requireNonNull(event);
        Objects.requireNonNull(event.eventId());
        Objects.requireNonNull(event.orderId());

        String routingKey = OrderRoutingKey.of(
                event.eventType(), event.schemaVersion(), event.audience());

        MessageProperties properties = new MessageProperties();
        properties.setContentType("application/json");
        properties.setMessageId(event.eventId());
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setHeader("eventType", event.eventType());
        properties.setHeader("schemaVersion", event.schemaVersion());
        properties.setHeader("audience", event.audience());

        byte[] json = objectMapper.writeValueAsBytes(event);
        Message message = new Message(json, properties);

        CorrelationData correlation = new CorrelationData(event.eventId());
        rabbitTemplate.send(
                OrderEventTopology.EVENTS_X, routingKey,
                message, correlation);
        return correlation;
    }
}
~~~

Trong ví dụ này, producer **không biết tên queue**. Nó chỉ biết event contract, exchange và routing key. `OrderEventPublisher.publish` trả `CorrelationData` để caller theo dõi publisher confirm khi được bật; **không có nghĩa broker đã xác nhận message** ngay khi phương thức trả về.

Lưu ý `ObjectMapper` do Spring Boot cung cấp trong cấu hình Jackson 2 phù hợp. Nếu dự án chuyển sang Spring Boot 4/Jackson 3, cập nhật import/converter theo BOM đang dùng. Việc publish body dưới dạng `Message` byte[] giúp nêu rõ content type và tránh nhập nhằng converter mặc định.

## 7. Consumer: ràng buộc schema với queue và kiểm tra message nhận được

Một queue bind `orders.paid.v1.*` chỉ nên nhận **orders.paid schema v1**. Broker bảo đảm phân loại theo routing key; tuy nhiên, consumer vẫn cần xác thực dữ liệu, vì producer có thể gửi **body phiên bản 2** cùng routing key `v1` do bug hoặc hành vi không đáng tin cậy.

~~~java
// BillingOrderPaidV1Listener.java
import java.io.IOException;
import java.util.Objects;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BillingOrderPaidV1Listener {
    private final ObjectMapper objectMapper;
    private final BillingService billingService;

    public BillingOrderPaidV1Listener(ObjectMapper objectMapper,
                                      BillingService billingService) {
        this.objectMapper = objectMapper;
        this.billingService = billingService;
    }

    @RabbitListener(queues = OrderEventTopology.BILLING_V1_Q)
    public void onOrderPaid(Message message) throws IOException {
        String actualRoutingKey = message.getMessageProperties()
                .getReceivedRoutingKey();
        OrderEvent event;
        try {
            event = objectMapper.readValue(
                    message.getBody(), OrderEvent.class);
        } catch (IOException malformed) {
            throw new AmqpRejectAndDontRequeueException(
                    "Invalid order event JSON", malformed);
        }

        if (!"orders.paid".equals(event.eventType())
                || event.schemaVersion() != 1) {
            throw new AmqpRejectAndDontRequeueException(
                    "Unsupported event contract for billing v1");
        }

        String expectedKey;
        try {
            expectedKey = OrderRoutingKey.of(
                    event.eventType(), event.schemaVersion(), event.audience());
        } catch (IllegalArgumentException unsupported) {
            throw new AmqpRejectAndDontRequeueException(
                    "Unsupported routing key fields", unsupported);
        }
        if (!expectedKey.equals(actualRoutingKey)
                || !Objects.equals(
                        event.eventId(),
                        message.getMessageProperties().getMessageId())) {
            throw new AmqpRejectAndDontRequeueException(
                    "Routing key, headers or eventId mismatch");
        }

        // acceptOnce ghi inbox(eventId) + nghiệp vụ cùng DB transaction.
        billingService.acceptOnce(event.eventId(), event.orderId());
    }
}
~~~

`BillingService` là service ứng dụng cần tự triển khai, không phải class có sẵn trong Spring AMQP. Nó nên dùng transaction database với **unique constraint trên event ID hoặc business operation ID** để chống xử lý trùng khi broker redeliver.

**Về lỗi:** `AmqpRejectAndDontRequeueException` có thể khiến container reject không requeue; khi queue cấu hình DLX phù hợp, broker có thể chuyển delivery sang DLQ. Với lỗi database tạm thời, không nên biến mọi exception thành reject vĩnh viễn: dùng retry có giới hạn/backoff và DLQ. Nếu có `@Transactional`, transaction manager hoặc manual ACK, phải kiểm tra cấu hình container vì kết quả thực tế còn phụ thuộc cách xử lý exception/rollback.

**Về bảo mật:** so sánh `actualRoutingKey` với JSON chỉ phát hiện **không nhất quán**, không chống producer có quyền publish gửi một event giả mạo hợp lệ về mặt định dạng. Consumer phải dựa vào danh tính/permissions đáng tin cậy và, nếu threat model yêu cầu, chữ ký hoặc MAC.

### 7.1. Queue gắn với event version, không gắn với phiên bản ứng dụng

Một service Billing release `2.5.0` có thể hỗ trợ cả `orders.paid.v1` và `orders.paid.v2`. Ngược lại, producer release `7.3.0` vẫn có thể phát `orders.paid.v1` nếu hợp đồng chưa đổi.

Không tự xây route:

~~~text
orders.paid.payment-service-2.5.0.enterprise  // Không phù hợp
~~~

Nên dùng **schema version có ý nghĩa với consumer**:

~~~text
orders.paid.v1.enterprise
orders.paid.v2.enterprise
~~~

Nếu payload v1 và v2 khác nhau đáng kể, tạo DTO hoặc decoder riêng theo từng version:

~~~text
billing.order-paid.v1.q --> V1 decoder / upcaster --> domain handler
billing.order-paid.v2.q --> V2 decoder             --> domain handler
~~~

Khi đã chuẩn hóa thành **domain command nội bộ**, cả hai version có thể gọi cùng một business service idempotent.

## 8. Version routing và tiến hóa event contract

### 8.1. Version không phải cứ thêm field là phải tăng

Cần có quy tắc compatibility rõ ràng:

| Thay đổi event | Có thể giữ v1? | Cân nhắc |
| --- | --- | --- |
| Thêm field tùy chọn, consumer cũ bỏ qua field lạ. | **Thường có thể**. | Kiểm thử Jackson/converter thật có bỏ qua unknown fields không. |
| Thêm field bắt buộc mà consumer cũ không hiểu. | **Thường không**. | Có thể cần v2 hoặc rollout consumer trước. |
| Đổi tên field, đổi kiểu hoặc đơn vị số tiền. | **Có khả năng breaking**. | Dùng v2, upcaster hoặc migration tương thích. |
| Đổi nghĩa của `orders.paid` thành “đang chờ thanh toán”. | **Không nên**. | Đổi event type/semantics; version schema không cứu nghĩa sai. |
| Thêm consumer mới hỗ trợ v1. | Không cần tăng version. | Thêm queue/binding và triển khai consumer. |
| Đổi version release của service. | Không cần. | Contract event độc lập release ứng dụng. |

Đừng dựa vào việc Kafka/JSON/Java cho phép field tùy chọn để khẳng định mọi thay đổi là backward-compatible. **Consumer contract test** mới xác nhận mức tương thích.

### 8.2. Ba chiến lược triển khai

**Chiến lược A — Một event type, consumer nâng cấp trước:** nếu thay đổi tương thích, tiếp tục phát `v1`. Mở rộng schema/consumer có kiểm soát, ít phức tạp topology.

**Chiến lược B — Version riêng theo routing key:** producer phát `orders.paid.v2.enterprise` cho luồng v2; queue v1 và v2 có binding riêng. Dùng khi schema thực sự breaking hoặc cần di trú từ từ.

**Chiến lược C — Upcasting tại consumer:** queue vẫn nhận event v1 cũ, nhưng consumer adapter biến v1 thành domain model mới trước khi xử lý. Phù hợp khi phải replay dữ liệu cũ; yêu cầu quy tắc mapping rõ và test trường thiếu/mặc định.

### 8.3. Rollout v1 → v2 không bỏ sót sự kiện

Một quy trình có kiểm soát:

1. **Định nghĩa v2** trong event registry, payload schema và routing-key format.
2. **Provision queue v2, binding** và consumer có khả năng xử lý v2; kiểm tra quyền, retry, DLQ, monitoring.
3. Chạy **contract tests** giữa v1/v2, bao gồm lỗi JSON và trường bắt buộc.
4. Chuyển publisher sang v2 theo kế hoạch, hoặc **dual publish** tạm thời khi thật sự cần để di trú.
5. Theo dõi số event v1/v2, queue backlog, missing events và consumer completion.
6. Chờ v1 queue drain và xử lý DLQ/outbox liên quan trước khi ngừng v1.
7. Xóa binding/queue cũ **sau khi đã xác minh** không còn consumer/rollback cần dùng v1.

**Đặc biệt về dual publish:** nếu hai representation v1 và v2 cùng mô tả **một business event**, nên giữ **business operation ID ổn định** để consumer bắt trùng khi có cơ hội nhận cả hai. Nếu mỗi version dùng eventId khác nhau, cần một field `logicalOperationId` chung hoặc cơ chế tương đương. Tránh chuyển toàn bộ sự kiện thành hai tác dụng phụ nghiệp vụ chỉ vì muốn nâng schema.

~~~text
Business operation: payment-123-paid
          |
          +--> orders.paid.v1.enterprise  --> billing.v1.q
          |
          +--> orders.paid.v2.enterprise  --> billing.v2.q
                                            |
                                        old/new consumers
                                        idempotent by operation ID
~~~

**Dual publish không nguyên tử** nếu gọi hai lần `RabbitTemplate.send` độc lập. Publish v1 có thể thành công nhưng v2 thất bại. Nếu cả hai luồng là yêu cầu bắt buộc, dùng outbox ghi **hai delivery intents** theo cùng business operation ID, có trạng thái và xác nhận riêng, sau đó đối soát. Khi consumer mới xử lý đồng thời cả hai version, phải tránh trùng tác dụng phụ.

### 8.4. Khi nào chỉ dùng header version, không đưa vào key?

Routing `orders.paid.enterprise` + header `schemaVersion=2` có thể đủ nếu **mọi consumer** của queue có khả năng nhận, phân loại và chuyển đổi cả v1/v2. Nhưng RabbitMQ **topic exchange không lọc theo header** với binding topic; nó không thể tự đưa v1/v2 vào queue khác dựa trên `schemaVersion` trong body.

| Yêu cầu | Chọn lựa thường phù hợp |
| --- | --- |
| V1 và v2 có consumer/queue riêng, không đọc nhầm schema | **Version trong routing key**. |
| Queue một consumer xử lý nhiều schema với upcaster | Version trong body/header được xác thực; routing có thể không chứa version. |
| Version chỉ biểu thị code release, không đổi payload | Không đưa version code vào route. |
| Chuyển schema breaking và rollback cần kiểm soát | Route v1/v2 + contract tests + migration. |

Đừng dùng `#` chỉ để “tự hỗ trợ mọi phiên bản” nếu consumer chưa có decoder tương ứng. Binding rộng hơn không tự làm schema tương thích.

## 9. Routing theo nhóm khách hàng và tenant cụ thể

### 9.1. Nhóm khách hàng: đơn giản và ít cardinality

Nếu yêu cầu là “Enterprise workflow nhận các sự kiện orders của nhóm Enterprise”, routing bốn phân đoạn:

~~~text
orders.created.v1.enterprise
orders.paid.v1.enterprise
orders.paid.v1.standard
~~~

Binding:

~~~text
enterprise.orders.v1.q -> orders.*.v1.enterprise
standard.orders.v1.q   -> orders.*.v1.standard
~~~

Ưu điểm: số binding và queue tương đối ít; dễ quản lý SLA theo nhóm. Nhưng **không có cô lập theo từng customer**: mọi tenant thuộc nhóm Enterprise đều có thể đi vào cùng queue. Consumer cần kiểm tra tenant ID và quyền ở tầng nghiệp vụ.

### 9.2. Tenant-specific routing: dùng phân đoạn thứ năm có chủ đích

Nếu một số tenant phải có queue riêng (ví dụ để ưu tiên xử lý hoặc định tuyến tới hệ thống riêng), xác định **schema khác có đúng năm phân đoạn**:

~~~text
<aggregate>.<action>.<version>.tenant.<tenant-routing-alias>

orders.paid.v1.tenant.t_acme
orders.created.v1.tenant.t_blue
~~~

Binding:

~~~text
t_acme.orders.v1.q -> orders.*.v1.tenant.t_acme
t_blue.orders.v1.q -> orders.*.v1.tenant.t_blue
~~~

**Những lưu ý quan trọng:**

- `t_acme` phải là **opaque alias được cấp phát bởi hệ thống**, không phải raw tenant email/ID bí mật; không có dấu chấm.
- Binding `orders.paid.v1.*` **không khớp** routing năm phân đoạn; phải khai báo binding cho cả hai sơ đồ nếu đang hỗ trợ song song.
- Một binding `orders.*.v1.tenant.*` nhận **mọi tenant v1**, không phù hợp cho consumer chỉ có quyền một tenant.
- Số queue/binding tăng theo số tenant; hàng nghìn tenant có thể làm topology và resource overhead trở nên đắt đỏ.
- Một producer có quyền publish vào topic exchange không tự bị cấm chọn `t_acme` chỉ vì nó đại diện cho tenant khác. Phải có **authorization thật**.

### 9.3. Không dùng routing key làm hàng rào bảo mật

**Topic binding chỉ chọn nơi message đi**, không đảm bảo bên gửi có đúng danh tính tenant. Nếu producer có thể publish với key `orders.paid.v1.tenant.t_other`, nó có thể thử đưa message sang luồng tenant khác nếu không có các biện pháp bảo vệ thích hợp.

Các lớp bảo vệ cần xem xét:

1. **RabbitMQ user/vhost permissions** theo vai trò, sử dụng tài khoản/service identity riêng, cấp quyền tối thiểu cho exchange/queue.
2. **RabbitMQ topic authorisation**, nơi phù hợp, giới hạn **routing key** được publish/bind bằng regexp và cơ chế authorization backend. Regexp này **khác** cú pháp wildcard `*`/`#` của binding topic.
3. **Application-level tenant authorization** từ identity đáng tin cậy trước publish và khi consumer xử lý; không mặc nhiên tin `tenantId` trong message hoặc route do client chọn.
4. **Tách vhost/cluster** khi cần cô lập chặt về credentials, traffic hoặc compliance; vhost cùng cluster vẫn chia sẻ tài nguyên node.
5. **KMS/encryption** nếu payload không được lộ cho broker/consumer khác; mã hóa body vẫn không che routing key.

**Cẩn trọng với topic authorisation:** cấu hình cụ thể phụ thuộc RabbitMQ backend, quyền thường và vhost. Nó là lớp **bổ sung**, không thay thế các quyền configure/write/read của RabbitMQ và validation ở application. Không dùng regexp `.*` như một ví dụ “khóa chặt” — đó là cho phép mọi routing key.

### 9.4. Chọn mức phân vùng hợp lý

| Nhu cầu | Gợi ý topology | Đánh đổi |
| --- | --- | --- |
| Hàng nghìn tenant nhỏ, SLA tương đồng | Queue theo nhóm hoặc shared queue; tenant ID ở payload đáng tin cậy. | Consumer phải áp dụng multi-tenant authorization/fairness. |
| Vài tenant lớn có tải/SLA riêng | Queue hoặc vhost riêng theo tenant alias; binding cụ thể. | Tăng queue/connection/metric count, bù lại dễ điều tiết. |
| Compliance yêu cầu phân tách tài nguyên | Vhost hoặc cluster riêng, credential/TLS/KMS phù hợp. | Chi phí vận hành và triển khai lớn hơn. |
| Consumer cần nhận mọi tenant để tính tổng hợp | Binding nhóm hoặc `orders.*.v1.tenant.*` cho consumer **được cấp phép**. | Có quyền rộng và nguy cơ lộ dữ liệu nếu thiết kế sai. |

**Đừng tạo queue per tenant hoặc binding per eventId** chỉ vì topic exchange làm điều đó có vẻ dễ. Với số lượng lớn, chi phí queue, binding, channel, monitoring, retention và policy khó quản lý; nhóm tenant hoặc dịch vụ routing riêng thường hợp lý hơn.

## 10. Publisher confirms, returns và thông điệp không định tuyến được

Khi dùng nhiều binding/pattern, rủi ro phổ biến là producer phát một routing key **không có queue nào khớp**. Điều này có thể xảy ra khi:

- Gõ sai `orders.paid` thành `order.paid`.
- Đổi `v1` thành `v2` trước khi deploy binding/consumer v2.
- Thêm phân đoạn `tenant` thứ năm nhưng consumer chỉ bind pattern bốn phân đoạn.
- Chọn audience chưa được phép hoặc không có consumer.
- Publish nhầm exchange, vhost hoặc broker.

Nếu publish vào exchange tồn tại nhưng không định tuyến được, message có thể bị **loại bỏ** theo hành vi mặc định nếu không có mandatory/alternate exchange thích hợp. Để phát hiện điều này:

### 10.1. Bật publisher confirm và return

Với Spring Boot 3.x:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Các cấu hình này có mục đích khác nhau:

| Tín hiệu | Nghĩa | Giới hạn |
| --- | --- | --- |
| **Publisher confirm ACK** | Broker đã xác nhận publish theo publisher confirms. | Không chứng minh có consumer xử lý, và có thể **ACK một publish bị return**. |
| **Publisher confirm NACK** | Broker không thể xử lý publish thành công theo cơ chế confirm. | Cần retry/điều tra; không phải consumer reject. |
| **Publisher return** | Message mandatory không routable theo cơ chế routing của broker. | Không phải mọi lỗi consumer tạo return; DLQ sau này là chuyện khác. |
| **Consumer ACK** | Delivery được consumer/container xác nhận. | Không chứng minh mọi tác vụ bất đồng bộ phía sau đã hoàn tất. |

Để tránh hiểu sai `CorrelationData`:

~~~java
// Sử dụng CorrelationData trả về từ OrderEventPublisher.publish(...).
CorrelationData correlation = publisher.publish(event);

correlation.getFuture().whenComplete((confirm, error) -> {
    if (error != null || confirm == null) {
        // Không có kết quả đủ rõ: cần đối soát/retry an toàn.
        return;
    }
    if (!confirm.isAck()) {
        // Publisher NACK: theo dõi nguyên nhân và retry có giới hạn.
        return;
    }
    if (correlation.getReturned() != null) {
        // Broker có thể ACK publish nhưng return vì UNROUTABLE.
        // Kiểm tra exchange, key shape, binding, vhost.
        return;
    }
    // Publish được broker xác nhận và không bị return.
    // CHƯA chứng minh business processing hoàn tất.
});
~~~

`getReturned()` áp dụng khi đã bật correlated confirms, returns và mandatory phù hợp. Với một custom `RabbitTemplate` bean, hãy kiểm tra các properties Boot đã thực sự được áp dụng; các bean do app tự khai báo có thể cần gọi `setMandatory(true)` và cấu hình factory trực tiếp. Callback có thể chạy trên thread khác; cập nhật trạng thái outbox phải có transaction/ràng buộc concurrency riêng.

**Thêm binding mới không làm những publish đã bị bỏ trước đó tự xuất hiện.** Nếu cần không mất dữ liệu, phải lưu **transactional outbox** ở producer rồi retry/đối soát sau khi topology được sửa. Alternate exchange có thể dùng làm đường giữ event unroutable, nhưng cần thiết kế topology, quyền và monitoring rõ; nó không tự thay cho kiểm soát contract.

### 10.2. RabbitTemplate dùng routing key theo eventType/version

Đoạn gọi minh họa:

~~~java
OrderEvent event = new OrderEvent(
        "evt-order-123-paid",
        "orders.paid",
        1,
        "enterprise",
        "ORD-123",
        System.currentTimeMillis());

CorrelationData correlation = publisher.publish(event);
// Theo dõi future confirm/return trước khi đánh dấu outbox PUBLISHED.
~~~

Nếu client hỏi “đã phát thành công chưa?”, câu trả lời cần phân biệt **DB source commit**, **outbox persisted**, **broker accepted/routed** và **consumer processed**. Không đồng nhất trả về từ `RabbitTemplate.send()` với kết quả nghiệp vụ đầu cuối.

## 11. Retry, DLQ và routing key sau dead-letter

### 11.1. Đừng để một version mới làm poison loop

Giả sử Billing v1 nhận body của v2 vì publisher gửi sai key v1. Listener v1 không giải mã được payload hoặc nhận sai version. Nếu container luôn requeue, cùng message sẽ được giao lại liên tục, tăng CPU, log và làm nghẽn queue.

Đường xử lý an toàn:

1. **Validate eventType/version/routing key** ở consumer.
2. Phân biệt **invalid contract** (thường là lỗi không phục hồi bằng retry ngay) với **DB/network transient**.
3. Retry transient errors có giới hạn/backoff.
4. Với invalid contract, reject không requeue vào **DLX/DLQ** nếu đã cấu hình.
5. Trong DLQ, giữ **eventId, loại/version thực tế và bằng chứng lỗi** để điều tra.
6. Khi đã sửa schema/topology, redrive có kiểm soát, tránh dùng key DLQ như key business ban đầu.

Ở topology ví dụ, message reject ở billing queue được dead-letter tới:

~~~text
Original publish:
  exchange     = orders.events.x
  routing key  = orders.paid.v1.enterprise

Billing queue:
  x-dead-letter-exchange    = orders.dead.x
  x-dead-letter-routing-key = billing.failed

DLQ:
  orders.billing.dead.q
~~~

Đây là ví dụ DLX dùng **DirectExchange** và routing key mới `billing.failed`. Điều này có nghĩa **routing key của message tại DLQ không còn là key ban đầu**. Không thiết kế replay bằng cách đọc `getReceivedRoutingKey()` từ DLQ rồi publish trở lại `orders.events.x`, vì nó có thể là `billing.failed` và không khớp binding business.

Muốn replay, dùng **event type/version/audience trong body đã kiểm tra**, hoặc metadata gốc được lưu bền vững trong outbox/audit, xác định routing key ban đầu một cách đáng tin cậy. RabbitMQ có header `x-death` phục vụ điều tra dead-letter, nhưng không nên coi một cấu trúc header ngẫu nhiên là hợp đồng nghiệp vụ duy nhất và không tự ý xóa/sửa death history để lặp vòng vô hạn.

### 11.2. Redrive nên ràng buộc phiên bản và tenant

Một message cũ từ `orders.paid.v1.tenant.t_acme` không được tùy ý đổi thành `orders.paid.v2.tenant.t_other` chỉ vì một script tìm thấy queue khác đang rỗng. Nếu chuyển v1 sang v2, phải dùng **upcaster/schema migration hợp lệ**, xác thực tenant và có audit trail. Nếu tenant bị xóa/quyền thay đổi, phải kiểm tra trạng thái nghiệp vụ hiện tại trước khi retry.

**Một message vào DLQ không tự động đồng nghĩa toàn bộ nghiệp vụ chưa xảy ra.** Consumer có thể đã commit DB nhưng chết trước ACK. Redrive phải giữ **business operation ID** để consumer idempotent.

### 11.3. Idempotency đặt ở business operation, không ở routing key

Hai event có cùng key `orders.paid.v1.enterprise` là rất bình thường: đó có thể là hai đơn hàng khác nhau. Routing key **không duy nhất cho từng message**. Cần `eventId` hoặc `businessOperationId` bền vững:

~~~sql
-- PostgreSQL: consumer ghi dấu theo business event ID.
CREATE TABLE billing_event_inbox (
    consumer_name TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khi nhận message, dùng transaction database để **insertIfAbsent(eventId)** và ghi side effect cùng transaction; nếu đã tồn tại thì không tạo side effect mới. Khi producer retry sau confirm timeout, giữ nguyên `eventId`, không sinh event ID mới cho mỗi lần publish lại.

## 12. Quan sát hệ thống: routing key giúp debug nhưng không phải metric ID

Một bộ observability hữu ích cần giải quyết câu hỏi: “Sự kiện `orders.paid.v2.enterprise` vì sao không đến Billing v2?”.

### 12.1. Logs có cấu trúc

~~~json
{
  "event": "amqp.publish",
  "broker": "orders",
  "exchange": "orders.events.x",
  "routingKey": "orders.paid.v2.enterprise",
  "eventType": "orders.paid",
  "schemaVersion": 2,
  "audience": "enterprise",
  "eventId": "evt-order-123-paid",
  "publishOutcome": "returned",
  "reason": "NO_BINDING_FOR_VERSION",
  "traceId": "trace-example"
}
~~~

JSON trên là **log ứng dụng minh họa**, không phải log RabbitMQ tự xuất. Nên phân biệt `returned`, `nack`, `timeout`, `consumer_rejected` và `dlq_redrive`; chúng xảy ra ở các bước khác nhau. Nếu body có PII, không log nguyên payload; nếu tenant alias cũng nhạy cảm, áp dụng masking/opaque key.

### 12.2. Metrics cần cardinality thấp

| Metric | Nhãn hữu ích | Tránh |
| --- | --- | --- |
| `app.amqp.publish.requests` | event_type, schema_version, audience, broker | Raw eventId. |
| `app.amqp.publish.returns` | event_type, schema_version, reason_category | Raw routing key do user điều khiển nếu vô hạn biến thể. |
| `app.amqp.publisher.confirm_latency` | broker, result | Correlation ID/message ID. |
| `app.amqp.consumer.completed` | listener, event_type, version | Order ID. |
| `app.amqp.consumer.rejected` | listener, error_category | Stacktrace làm label. |
| `app.amqp.dlq.oldest_age` | queue_group, broker | Event ID hoặc raw tenant ID số lượng lớn. |
| `app.amqp.business.completion_latency` | event_type, audience | Customer/email/địa chỉ. |

Không dùng `routingKey` nguyên văn làm Prometheus/Micrometer tag nếu key chứa **tenant alias tùy số lượng lớn**. Với quy ước bốn phân đoạn và tập giá trị hữu hạn, có thể tách `eventType`, `version`, `audience` thành các label có ngân sách cardinality được kiểm soát.

### 12.3. CLI giúp kiểm tra binding

Trên broker RabbitMQ (quyền CLI thích hợp):

~~~bash
# Các exchange trong vhost /orders.
rabbitmqctl list_exchanges -p /orders name type durable

# Kiểm tra binding pattern giữa exchange và queue.
rabbitmqctl list_bindings -p /orders source_name destination_name routing_key

# Queue và số message đang chờ/đang được giao chưa ACK.
rabbitmqctl list_queues -p /orders name messages_ready messages_unacknowledged consumers
~~~

Các option và trường CLI có thể khác theo version; cần chạy đúng node/vhost mà ứng dụng đang kết nối. RabbitMQ Management UI cũng cho phép xem bindings của exchange/queue. Khi message không tới queue, kiểm tra **exchange type = topic**, key shape, version, binding, queue tồn tại và quyền access trước khi đổ lỗi cho listener.

## 13. Kiểm thử định tuyến bằng RabbitMQ thật

### 13.1. Unit test routing key builder

~~~java
// OrderRoutingKeyTest.java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderRoutingKeyTest {

    @Test
    void createsStableFourSegmentKey() {
        assertEquals(
                "orders.paid.v1.enterprise",
                OrderRoutingKey.of("orders.paid", 1, "enterprise"));
    }

    @Test
    void refusesUnknownEventVersionOrAudience() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderRoutingKey.of("orders.deleted", 1, "enterprise"));
        assertThrows(IllegalArgumentException.class,
                () -> OrderRoutingKey.of("orders.paid", 99, "enterprise"));
        assertThrows(IllegalArgumentException.class,
                () -> OrderRoutingKey.of("orders.paid", 1, "unknown.tenant"));
    }
}
~~~

Unit test builder giúp phát hiện sai quy ước trước khi message đến broker, nhưng chưa kiểm chứng binding/topic exchange thực. Không viết matcher mô phỏng topic bằng một `String.startsWith` đơn giản rồi coi đó là bằng chứng RabbitMQ sẽ route đúng; `*`/`#` có ngữ nghĩa phân đoạn cụ thể.

### 13.2. Integration test bằng Testcontainers

Với **Spring Boot 3.1+**, dependency `spring-boot-testcontainers`, `org.testcontainers:rabbitmq` và `org.testcontainers:junit-jupiter` (các version đồng bộ qua BOM), dùng `@ServiceConnection`. Trong ứng dụng có topology `OrderEventTopology` từ mục 5, tạo thêm **hai queue test độc lập**, không có `@RabbitListener` tranh message:

~~~java
// TopicRoutingIntegrationTest.java - imports rút gọn.
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.AnonymousQueue;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest
@Import(TopicRoutingIntegrationTest.RoutingTestConfig.class)
class TopicRoutingIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer broker =
            new RabbitMQContainer("rabbitmq:4.1-management");

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Autowired
    @Qualifier("routingTestV1Queue")
    Queue v1;

    @Autowired
    @Qualifier("routingTestV2Queue")
    Queue v2;

    @Test
    void routesVersionToDifferentQueues() {
        rabbitTemplate.convertAndSend(
                OrderEventTopology.EVENTS_X,
                "orders.paid.v1.enterprise",
                "event-v1");

        Message onlyV1 = rabbitTemplate.receive(v1.getName(), 5000);
        assertNotNull(onlyV1);
        assertNull(rabbitTemplate.receive(v2.getName(), 250));

        rabbitTemplate.convertAndSend(
                OrderEventTopology.EVENTS_X,
                "orders.paid.v2.standard",
                "event-v2");

        Message onlyV2 = rabbitTemplate.receive(v2.getName(), 5000);
        assertNotNull(onlyV2);
        assertNull(rabbitTemplate.receive(v1.getName(), 250));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class RoutingTestConfig {
        @Bean("routingTestV1Queue")
        Queue routingTestV1Queue() {
            return new AnonymousQueue();
        }

        @Bean("routingTestV2Queue")
        Queue routingTestV2Queue() {
            return new AnonymousQueue();
        }

        @Bean
        Binding routingTestV1Binding(
                @Qualifier("routingTestV1Queue") Queue queue) {
            return BindingBuilder.bind(queue)
                    .to(new TopicExchange(OrderEventTopology.EVENTS_X,
                            true, false))
                    .with("orders.paid.v1.*");
        }

        @Bean
        Binding routingTestV2Binding(
                @Qualifier("routingTestV2Queue") Queue queue) {
            return BindingBuilder.bind(queue)
                    .to(new TopicExchange(OrderEventTopology.EVENTS_X,
                            true, false))
                    .with("orders.paid.v2.*");
        }
    }
}
~~~

**Điều kiện chạy:** cần một `@SpringBootApplication` được Spring Boot test tìm thấy, `spring-boot-starter-amqp` và các module Testcontainers tương ứng. `OrderEventTopology` đã khai báo exchange `orders.events.x` cùng độ bền/type, và RabbitAdmin phải khai báo hai queue test/binding. Nếu app test chứa listener khác, không cho các listener đó consume **hai anonymous queues của test**; các listener sản phẩm có thể vẫn chạy trên queue riêng.

Không dùng `Thread.sleep()` để “chờ binding”, thay vào đó bảo đảm topology đã được RabbitAdmin khai báo trước publish và dùng `receive(queue, timeout)` hữu hạn. Lưu ý test trên chỉ khẳng định **routing tới hai queue test**, chưa kiểm chứng consumer business logic hoặc publisher confirm. Muốn test tính tin cậy, thêm assertion độc lập tương ứng.

### 13.3. Ma trận test contract bắt buộc

| Tình huống | Expected route | Cần khẳng định |
| --- | --- | --- |
| `orders.paid.v1.enterprise` | Billing v1, enterprise v1, audit. | Không đến Billing v2. |
| `orders.paid.v2.standard` | Billing v2, audit. | Không đến Billing v1, enterprise v1. |
| `orders.created.v1.enterprise` | Enterprise v1, audit. | Không đến Billing v1/v2 nếu chỉ subscribe `paid`. |
| `orders.paid.v1.tenant.t_acme` | Chỉ những queue có binding năm phân đoạn tương ứng, audit `orders.#`. | Không bị nhận nhầm bởi `orders.paid.v1.*`. |
| `orders.paid.v3.enterprise` | Audit; các consumer v1/v2 không nhận. | Nếu v3 chưa được phép phát, builder từ chối trước publish. |
| `payments.paid.v1.enterprise` | Không match các binding orders. | Không vô tình đưa event thuộc domain khác vào orders queues. |
| Key mới không có binding | Return/unroutable hoặc đi alternate exchange theo topology. | Publisher không báo “hoàn tất nghiệp vụ” chỉ vì confirm ACK. |
| Message đúng route nhưng body version sai | Đến queue theo key, consumer reject/quarantine. | Không bỏ qua kiểm tra schema. |
| Replay cùng `eventId` | Được route như trước. | Inbox ngăn duplicate side effect. |

Mẫu test topic cần được chạy lại khi thêm event type/version/audience, đổi tên exchange, thêm tenant scheme hoặc thay chính sách phân quyền. Một thay đổi về **routing** có thể phá vỡ hệ thống ngay cả khi tất cả unit tests JSON đều PASS.

## 14. Tình huống thực tế: triển khai luồng Enterprise v2

Giả sử hiện tại:

~~~text
Order Service publishes:
  orders.paid.v1.standard
  orders.paid.v1.enterprise

Billing v1 queue:
  orders.paid.v1.*

Enterprise v1 queue:
  orders.*.v1.enterprise

Audit queue:
  orders.#
~~~

Nay Enterprise yêu cầu field `paymentMethodDetails` mới và thay đổi cách tính thuế. Nếu thay thẳng payload v1 thành v2 nhưng giữ routing key v1, Billing cũ có thể parse sai và ghi sai nghiệp vụ. Một kế hoạch triển khai:

**Giai đoạn 1 — Thiết kế hợp đồng**

- Quy định rõ `orders.paid.v2.enterprise` có những field gì, tính backward/forward compatibility và điều kiện nghiệp vụ mới.
- Định nghĩa `eventId` và `logicalOperationId` dùng khi producer có thể phát song song v1/v2.
- Không đưa chi tiết thanh toán nhạy cảm vào routing key. Nếu payload có PII, dùng mã hóa tầng ứng dụng khi yêu cầu broker-blind encryption.
- Chốt rollback: phiên bản nào vẫn phải đọc được dữ liệu cũ, và trong bao lâu.

**Giai đoạn 2 — Chuẩn bị topology và consumer**

- Provision queue `billing.order-paid.v2.q` và binding `orders.paid.v2.*`.
- Consumer v2 dùng DTO/decoder v2, không để consumer v1 đọc nhầm payload v2.
- Thêm retry có giới hạn, DLQ, metric theo schema version, log eventId và alert publisher returns.
- Kiểm tra ACL theo vhost/user/tenant. Nếu chỉ Enterprise được phát v2, whitelist trong producer và quyền bổ sung ở broker nơi phù hợp.

**Giai đoạn 3 — Cutover**

- Test publish `orders.paid.v2.enterprise` qua topic exchange; dùng broker test xác minh Billing v2 và Audit nhận, Billing v1 không nhận.
- Khi producer v2 được bật, theo dõi cả queue v1 và v2. Nếu dual publish, giữ một operation ID và xử lý duplicate-safe.
- Theo dõi end-to-end completion, không chỉ `publisher confirm ACK`.

**Giai đoạn 4 — Dọn dẹp**

- Chờ các sự kiện v1 đang chờ được xử lý hoặc đưa vào đường khôi phục đã kiểm chứng.
- Kiểm tra DLQ, outbox, backup/replay và consumer rollback trước khi xóa binding v1.
- Cập nhật tài liệu contract, dashboard và test để phiên bản mới có cùng mức độ quan sát.

### 14.1. Nếu route đổi sớm hơn consumer thì sao?

~~~text
10:00  Producer bật v2
10:01  Chưa provision binding orders.paid.v2.*
10:02  Broker confirm ACK
10:02  Message bị return do không có queue (nếu mandatory bật)
10:03  Outbox vẫn chưa nên đánh dấu xử lý thành công
10:05  Triển khai binding v2
10:06  Retry cùng eventId và routing key đúng
~~~

Nếu không bật mandatory returns hoặc alternate exchange, publish có thể biến mất khỏi luồng consumer mà producer không nhận diện. **Thứ tự an toàn là provision consumer/topology trước, rồi mới bật publish v2**; nếu kết quả không rõ, outbox và idempotency là cơ sở phục hồi.

### 14.2. Nếu customer được chuyển từ standard sang enterprise thì sao?

Một event được tạo trước khi đổi nhóm có thể mang key `orders.paid.v1.standard`, nhưng khi tiêu thụ thì tenant đã thuộc nhóm Enterprise. **Routing key biểu thị ngữ cảnh khi event được tạo theo contract**, không tự động theo trạng thái hiện tại của customer.

Ứng dụng cần quy định:

- Có xử lý theo **audience tại thời điểm sự kiện** hay audience hiện tại không?
- Nếu phải đổi luồng cho công việc đang chờ, có quy trình **reclassification/replay** riêng và audit không?
- Có tránh tạo hai kết quả khi cùng business operation được gửi lại theo audience khác không?

Không sửa trực tiếp headers/body trong queue đang vận hành hoặc publish lại cùng event với một routing key mới mà không kiểm tra side effect. Routing key không thay thế quy tắc nghiệp vụ về chuyển hạng khách hàng.

## 15. Runbook: khi message không vào đúng queue

### 15.1. Trình tự điều tra

Khi một team báo “sự kiện orders.paid không tới Billing”:

1. **Xác định eventId, eventType, version, audience/tenant alias**, thời điểm publish và broker/vhost. Không cần lộ payload nhạy cảm.
2. **Xem trạng thái outbox** tại nguồn: đã có dữ liệu bền vững chưa, đang pending/sending/published hay chưa rõ kết quả?
3. **Kiểm tra RabbitTemplate** thực sự gửi tới exchange `orders.events.x` và routing key nào; không suy từ log Java method name.
4. **Kiểm tra exchange type và bindings** bằng RabbitMQ Management/CLI. Binding `orders.paid.v1.*` không khớp v2 hoặc key có thêm phân đoạn tenant.
5. **Xem publisher confirm và return**. ACK + return là dấu hiệu publish được broker xử lý nhưng không được route đến queue như mong đợi.
6. **Xem queue ready/unacked**, consumer count, connection và resource alarms. Message có thể đã vào queue nhưng consumer chậm/hỏng.
7. **Xem listener errors, retry và DLQ**. Với DLX thay routing key, lấy original event contract từ nguồn đáng tin cậy trước redrive.
8. **Đối soát kết quả nghiệp vụ** theo eventId/logicalOperationId; nếu consumer đã commit nhưng ACK mất, không tự tạo hiệu ứng trùng.
9. **Sửa theo nguyên nhân**: topology, schema mapping, permissions, producer key builder hoặc consumer logic. Thực hiện replay có giới hạn và audit.
10. **Đóng incident khi hoàn tất đầu cuối**, không chỉ khi queue depth trở về 0.

### 15.2. Bảng chẩn đoán nhanh

| Hiện tượng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| Exchange tồn tại, không queue nào có message | Sai key shape/version, thiếu binding, sai vhost. | So sánh publish key với từng binding; kiểm tra return. |
| Message vào Audit nhưng không vào Billing | Audit bind `orders.#`, Billing chỉ v1. | Kiểm tra version và consumer support. |
| Enterprise queue nhận event standard | Binding quá rộng (`orders.#`), audience do producer đặt sai. | Thu hẹp binding, kiểm soát audience ở producer, xác thực consumer. |
| Consumer nhận body version không khớp key | Producer xây route/payload từ hai nguồn logic khác nhau. | Dùng builder và một event contract thống nhất; reject/quarantine. |
| Không có publisher return nhưng consumer không thấy message | Return/mandatory chưa bật, alternate exchange, lỗi consumer, queue khác. | Kiểm tra cấu hình RabbitTemplate, AE, queue state, confirms. |
| DLQ có routing key `billing.failed` | DLX đã rewrite routing key. | Khôi phục original contract từ payload/outbox, không redrive mù. |
| Một event được xử lý hai lần | Retry sau timeout, consumer crash sau DB commit trước ACK, dual publish. | Inbox/idempotency theo operation ID. |
| Rất nhiều queue/binding theo tenant | Topology phân mảnh quá mức. | Đánh giá grouping, shared queues và budget resource. |
| Vhost riêng nhưng tenant vẫn ảnh hưởng nhau khi broker hết RAM | Vhost không cô lập tài nguyên node. | Capacity planning/cluster isolation theo SLA. |
| Customer data lộ trong routing key | Producer đưa email/ID nhạy cảm vào key. | Đổi sang opaque alias/nhóm, sửa log/retention và xử lý dữ liệu đã lộ. |

## 16. Bài thực hành tự triển khai

**Bối cảnh:** hệ thống xử lý đơn hàng có Billing Service, Enterprise Service và Audit Service. Producer phát `orders.created`, `orders.paid`, `orders.cancelled`. Hai version v1/v2 cùng tồn tại trong giai đoạn chuyển đổi.

**Mục tiêu:** Consumer nhận đúng loại sự kiện, phiên bản và nhóm khách hàng mà không biết trực tiếp producer nào gửi; có cơ chế phát hiện routing sai và không tạo tác dụng phụ trùng khi retry.

### 16.1. Yêu cầu triển khai

1. Tạo `TopicExchange("orders.events.x")`, các queue `billing.v1`, `billing.v2`, `enterprise.v1`, `audit` và binding theo quy ước bốn phân đoạn.
2. Viết `OrderRoutingKey.of(...)` có whitelist event type, schema version và audience; cấm giá trị tùy ý có dấu chấm hoặc dữ liệu nhạy cảm.
3. Dùng `RabbitTemplate` publish sự kiện v1 và v2; payload chứa `eventId`, `eventType`, `schemaVersion`, `audience`, `orderId`.
4. Tại `@RabbitListener`, so sánh body contract với received routing key; từ chối dữ liệu sai version hoặc sai event type.
5. Bật publisher correlated confirms, mandatory returns. Cố tình publish một routing key chưa có binding và quan sát **return**.
6. Thêm một queue consumer tenant cụ thể với binding `orders.*.v1.tenant.t_demo`, sau đó kiểm tra nó không nhận `tenant.t_other`.
7. Cấu hình DLX/DLQ và tạo một event sai JSON hoặc sai schema; kiểm tra nó **không hot-loop** và không được xử lý nghiệp vụ.
8. Thêm bảng inbox với unique event ID; publish cùng một event hai lần rồi xác minh chỉ có **một tác dụng phụ**.
9. Mô phỏng v1 → v2 rollout: deploy queue/binding mới trước publisher, sau đó chuyển publish; ghi lại các kiểm thử trước/sau.
10. Xây dashboard với `publish_return_total`, `routing_mismatch_total`, queue backlog, DLQ age và business completion latency theo event type/version/audience.

### 16.2. Câu hỏi tự kiểm tra

**Câu 1.** Binding `orders.*.v1.enterprise` có nhận `orders.paid.v1.enterprise` không? Có nhận `orders.paid.v2.enterprise` không?

**Đáp án:** Có với v1 vì `*` khớp phân đoạn `paid`; không với v2 vì segment version khác.

**Câu 2.** Binding `orders.paid.v1.*` có nhận `orders.paid.v1.tenant.t_acme` không?

**Đáp án:** Không. `*` khớp đúng một phân đoạn; key năm phân đoạn phải dùng binding shape phù hợp như `orders.paid.v1.tenant.*` hoặc cụ thể tenant alias.

**Câu 3.** Hai binding của cùng một queue đều khớp một publish. Queue có nhận hai bản sao không?

**Đáp án:** Không chỉ vì hai binding cùng khớp. Với RabbitMQ, một publish được route tới **mỗi queue phù hợp** một lần; các lần publish lại hoặc redelivery là nguyên nhân trùng riêng.

**Câu 4.** RabbitTemplate nhận publisher confirm ACK với key v2 mới nhưng Billing không thấy message. Có thể kết luận đã xử lý nghiệp vụ không?

**Đáp án:** Không. Broker có thể ACK publish nhưng message **unroutable** và bị return; phải kiểm tra mandatory returns, binding, queue, consumer và kết quả nghiệp vụ.

**Câu 5.** Có nên đưa `email` khách hàng vào routing key để dễ tạo queue riêng không?

**Đáp án:** Không. Routing key thường lộ trong broker và công cụ vận hành. Dùng audience hoặc opaque alias đã kiểm soát; tenant isolation cần ACL và authorization thật.

**Câu 6.** Nếu v2 chỉ thêm một field tùy chọn, có nhất thiết phải tạo route v2 không?

**Đáp án:** Không nhất thiết. Nếu consumer v1 chịu được thay đổi, có thể giữ version theo quy tắc compatibility. Cần contract tests với converter thật để chứng minh.

**Câu 7.** Khi dead-letter từ Billing queue sang DLX với key `billing.failed`, có thể publish nguyên key đó vào `orders.events.x` khi redrive không?

**Đáp án:** Không. Key DLQ có thể đã được viết lại; cần xác định lại original event type/version/audience từ dữ liệu đáng tin cậy và kiểm soát replay.

**Câu 8.** Chỉ dùng routing key `orders.paid.v1.tenant.t_acme` có bảo đảm producer của tenant khác không giả mạo được `t_acme` không?

**Đáp án:** Không. Routing key là dữ liệu định tuyến. Phải kết hợp identity, RabbitMQ permissions/topic authorization, tenant validation và bảo mật payload theo threat model.

**Câu 9.** Vì sao thêm một segment `region` vào routing key có thể là breaking change?

**Đáp án:** Vì pattern topic so khớp theo **số và thứ tự phân đoạn**; binding `orders.*.v1.enterprise` bốn đoạn không nhận key năm đoạn `orders.paid.v1.enterprise.apac`.

## 17. Checklist thiết kế trước production

- [ ] Có **event routing registry**: aggregate/action/version/audience và owner rõ ràng.
- [ ] Shape, số phân đoạn, alphabet, độ dài và whitelist được kiểm tra ở producer.
- [ ] Routing key không chứa PII, credential, eventId hay raw tenant ID nhạy cảm.
- [ ] Chọn **TopicExchange** khi cần wildcard, không dùng DirectExchange nhầm cú pháp `*`/`#`.
- [ ] Consumer subscribe đúng event type/schema version, tránh wildcard `#` quá rộng không có lý do.
- [ ] Queue riêng cho mỗi consumer cần xử lý độc lập; không nhầm competing consumers với pub/sub.
- [ ] Đã định nghĩa compatibility, migration v1/v2, upcaster và rollback.
- [ ] Khi dual publish, có business operation ID/idempotency và theo dõi trạng thái hai publish.
- [ ] Tenant routing có ACL/identity validation, không giả định binding là ranh giới bảo mật.
- [ ] Có cơ chế quản trị topology, binding, DLX/DLQ và migration queue arguments.
- [ ] Publisher confirms **và** returns/mandatory được kiểm tra; có outbox khi không được mất sự kiện.
- [ ] Consumer kiểm tra eventType/version/key/body; không xử lý dữ liệu không đúng hợp đồng.
- [ ] Retry có giới hạn, DLQ/quarantine và redrive không dùng nhầm DLX routing key.
- [ ] Consumer idempotent với eventId/logicalOperationId được lưu bền vững.
- [ ] Dashboard theo **event type/version/audience** có cardinality thấp, logs giữ correlation IDs có kiểm soát.
- [ ] Unit test key builder và integration test RabbitMQ thật cho binding/wildcard/version/tenant.
- [ ] Đối soát business source → outbox → broker → consumer → tác vụ nghiệp vụ sau rollout.

## 18. Tổng kết

**Routing key theo loại sự kiện, phiên bản hoặc khách hàng** là một **hợp đồng tích hợp** giữa producer, exchange và các consumer của hệ thống Spring AMQP. Quy ước như `orders.paid.v1.enterprise` giúp một **TopicExchange** định tuyến linh hoạt bằng `*` và `#`, trong khi producer chỉ cần phát sự kiện theo contract chứ không cần biết tên queue.

Thiết kế tốt phải giữ **số phân đoạn ổn định, tách rõ schema version khỏi application version, kiểm soát event taxonomy**, quản lý lifecycle v1/v2 và không để thông tin nhạy cảm vào routing key. Khi cần tenant-specific routing, hãy dùng alias và quyền thực sự; **routing không đồng nghĩa authorization**.

Cuối cùng, **đúng route không đồng nghĩa đúng kết quả nghiệp vụ**. Bài học này gắn routing với **RabbitTemplate, @RabbitListener, publisher confirm/return, retry, DLX/DLQ, idempotency và đối soát** để một message không chỉ đến đúng queue mà còn được xử lý một cách đáng tin cậy.

### Tài liệu tham khảo

- [RabbitMQ – Topics tutorial (Spring AMQP)](https://www.rabbitmq.com/tutorials/tutorial-five-spring-amqp): topic exchange, `*`/`#` và Java/Spring patterns.
- [RabbitMQ – Exchanges](https://www.rabbitmq.com/docs/exchanges): direct, topic, fanout, default exchange và binding semantics.
- [RabbitMQ – AMQP 0-9-1 Model Explained](https://www.rabbitmq.com/tutorials/amqp-concepts): exchange–binding–queue, routing và xác nhận.
- [RabbitMQ – Limits and Timeouts](https://www.rabbitmq.com/docs/limits): routing key tối đa 255 byte và giới hạn broker.
- [RabbitMQ – Access Control and Topic Authorisation](https://www.rabbitmq.com/docs/access-control): user/vhost permissions và quyền theo topic.
- [RabbitMQ – Virtual Hosts](https://www.rabbitmq.com/docs/vhosts): namespace và quyền tách vhost.
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): publish confirmations và consumer acknowledgements.
- [RabbitMQ – Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): DLX, dead-letter routing key và x-death.
- [Spring AMQP – Configuring the Broker](https://docs.spring.io/spring-amqp/reference/amqp/broker-configuration.html): TopicExchange, queues, bindings và RabbitAdmin.
- [Spring AMQP – RabbitTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `convertAndSend`/`send`, correlated confirms và returns.
- [Spring AMQP – Asynchronous Consumers](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): `@RabbitListener`, container, ACK và error handling.
