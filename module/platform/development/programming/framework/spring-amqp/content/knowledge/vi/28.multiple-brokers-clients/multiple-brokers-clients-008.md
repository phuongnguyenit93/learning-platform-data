# Connection name, metric và log cho từng broker hoặc khách hàng

## 1. Vì sao nhiều broker cần quan sát theo từng đích?

Trong **Spring AMQP**, ứng dụng gửi message bằng `RabbitTemplate`, định tuyến qua **exchange, queue, binding** và tiêu thụ qua `@RabbitListener`. Khi chỉ có một RabbitMQ broker, log “connection lost” hoặc “publisher timeout” có thể đủ để xác định nơi bắt đầu điều tra. Khi một ứng dụng phục vụ **nhiều broker hoặc nhiều khách hàng (tenant)**, các thông báo chung chung không trả lời được broker nào lỗi, nhóm khách hàng nào bị ảnh hưởng hoặc event nào chưa xử lý.

Ví dụ một hệ thống thanh toán dùng hai RabbitMQ cluster:

- **Orders**: nhận và phát sự kiện đơn hàng.
- **Audit**: lưu thông tin sự kiện kiểm toán.

Nếu Audit bị disk alarm, Orders có thể vẫn hoạt động. Nếu lập trình viên vô tình tiêm `auditRabbitTemplate` thay cho `ordersRabbitTemplate`, event có thể đến **sai broker** mà tên exchange và routing key vẫn trông hợp lệ. Nếu listener nối sai vhost, queue có thể không tồn tại hoặc nhận message của ngữ cảnh khác.

Ba lớp quan sát cần phối hợp:

| Lớp | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Connection name** | Nhìn vào broker và nhận diện ứng dụng, môi trường, vai trò, instance. | `payment/prod/audit/publisher/pod-03/1` |
| **Metrics** | Đo tỷ lệ lỗi, độ trễ và tải theo nhóm có số lượng hữu hạn. | `broker=audit`, `client_group=enterprise` |
| **Structured logs/tracing** | Tìm đúng lần gửi, lần nhận và event nghiệp vụ cần điều tra. | `eventId`, `traceId`, `routingKey` |

Bài học tập trung vào **connection name, metric và log cho từng broker hoặc khách hàng** trong Spring AMQP. Các ví dụ lồng ghép publisher confirms, returns, retry, dead-letter và đối soát để giữ độ tin cậy đầu cuối.

## 2. Phân biệt broker, vhost, connection và khách hàng

| Khái niệm | Ví dụ | Ranh giới |
| --- | --- | --- |
| **Broker/cluster alias** | `orders`, `audit` | Tên logic ứng dụng dùng để biết đi tới hệ RabbitMQ nào. |
| **RabbitMQ node** | `rabbit@node01` | Một tiến trình RabbitMQ; cluster có thể có nhiều node. |
| **Virtual host** | `/orders`, `/audit` | Namespace của exchange/queue/binding và quyền truy cập trong một broker/cluster. |
| **Connection** | Một TCP connection của client | Có user, vhost, node, client-provided name và nhiều channel. |
| **Channel** | AMQP channel | Các publish/consume và delivery tag hoạt động trên channel. |
| **Tenant/client** | Nhóm doanh nghiệp, gói dịch vụ hoặc khách hàng | Một tenant có thể dùng chung broker hoặc được cấp vhost/cluster riêng. |

Hai mô hình thường gặp:

~~~text
Mô hình A: hai cluster riêng
  Spring Boot
    +-- ordersConnectionFactory --> Orders cluster, /orders
    +-- auditConnectionFactory  --> Audit cluster,  /audit

Mô hình B: một cluster, nhiều vhost
  Spring Boot
    +-- tenantAConnectionFactory --> Shared cluster, /tenant-a
    +-- tenantBConnectionFactory --> Shared cluster, /tenant-b
~~~

Vhost tách topology và quyền, **không tạo một node vật lý riêng**. Nhiều vhost trên cùng cluster vẫn chia sẻ tài nguyên broker như RAM/đĩa; memory/disk resource alarm ở một node có thể ảnh hưởng publisher của cả cluster.

**Connection name chỉ là metadata, không phải định danh bảo mật.** Client có thể dùng tên trùng; RabbitMQ vẫn phân quyền theo user/vhost/permissions. Không được đưa password, token, email hoặc dữ liệu nhạy cảm vào connection name.

## 3. Đặt connection name bằng ConnectionNameStrategy

RabbitMQ AMQP 0-9-1 cho phép client khai báo **client-provided connection name**. Trên Spring AMQP, `CachingConnectionFactory.setConnectionNameStrategy(...)` nhận một chiến lược đặt tên được gọi khi tạo connection vật lý.

Quy ước tên dễ tra cứu:

~~~text
<service>/<env>/<broker-alias>/<role>/<instance>/<sequence>

payment-service/prod/orders/client/pod-03/1
payment-service/prod/audit/client/pod-03/1
~~~

Trong đó, `role` có thể là `publisher`, `consumer` hoặc `client` nếu một connection được dùng cho nhiều nhiệm vụ. Không ghi tên role sai với vai trò thực tế. `instance` giúp phân biệt replica, `sequence` phân biệt các connection được tạo bởi cùng một instance.

Ví dụ strategy dùng `AtomicInteger`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;

public final class RabbitConnectionNaming {
    private RabbitConnectionNaming() {
    }

    public static void setName(CachingConnectionFactory factory,
                               String prefix) {
        AtomicInteger connectionSequence = new AtomicInteger();
        factory.setConnectionNameStrategy(
                ignored -> prefix + "/" + connectionSequence.incrementAndGet());
    }
}
~~~

Tài liệu Spring AMQP gọi đây là **ConnectionNameStrategy**; nó **không chạy cho từng message hoặc channel**. `CachingConnectionFactory` có thể tái sử dụng một TCP connection cho nhiều channel. Sau reconnect, broker thấy connection mới, và strategy có thể tạo tên có sequence mới. Tên có thể trùng giữa những instance đặt cùng prefix; muốn phân biệt nên dùng instance ID duy nhất.

Một cách ngắn hơn:

~~~java
factory.setConnectionNameStrategy(
        ignored -> "payment-service/prod/orders/client");
~~~

Cách này đủ cho một số môi trường test; với nhiều replica/connection, nên thêm instance và sequence.

## 4. Cấu hình hai broker rõ ràng trong Spring Boot

Giả định dùng Spring Boot, Java 17+ và dependency `spring-boot-starter-amqp`. Ứng dụng dùng hai bộ kết nối riêng và chỉ định bean cụ thể cho producer/consumer. **Thông tin host và vhost dưới đây là minh họa**, thay bằng endpoint và credential của môi trường.

### 4.1. application.yml

~~~yaml
app:
  amqp:
    environment: prod
    instance-id: ${HOSTNAME:local}
    orders:
      host: orders-rmq.internal
      port: 5672
      vhost: /orders
      username: orders-app
      password: ${ORDERS_RABBIT_PASSWORD}
    audit:
      host: audit-rmq.internal
      port: 5672
      vhost: /audit
      username: audit-app
      password: ${AUDIT_RABBIT_PASSWORD}
~~~

`app.amqp.*` là namespace **tự định nghĩa**, không được Spring Boot tự áp dụng vào mọi `CachingConnectionFactory` như `spring.rabbitmq.*`. Các giá trị phải được bind/đọc trong Java. Với production, cấu hình TLS, hostname verification, secret rotation và quyền tối thiểu cho từng user.

### 4.2. Tạo hai CachingConnectionFactory có tên riêng

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MultiBrokerConnectionConfig {

    @Bean("ordersConnectionFactory")
    CachingConnectionFactory ordersConnectionFactory(
            @Value("${app.amqp.orders.host}") String host,
            @Value("${app.amqp.orders.port:5672}") int port,
            @Value("${app.amqp.orders.vhost:/}") String vhost,
            @Value("${app.amqp.orders.username}") String username,
            @Value("${app.amqp.orders.password}") String password,
            @Value("${app.amqp.environment:dev}") String env,
            @Value("${app.amqp.instance-id:local}") String instance) {
        return factory(host, port, vhost, username, password,
                "payment-service/" + env + "/orders/client/" + instance);
    }

    @Bean("auditConnectionFactory")
    CachingConnectionFactory auditConnectionFactory(
            @Value("${app.amqp.audit.host}") String host,
            @Value("${app.amqp.audit.port:5672}") int port,
            @Value("${app.amqp.audit.vhost:/}") String vhost,
            @Value("${app.amqp.audit.username}") String username,
            @Value("${app.amqp.audit.password}") String password,
            @Value("${app.amqp.environment:dev}") String env,
            @Value("${app.amqp.instance-id:local}") String instance) {
        return factory(host, port, vhost, username, password,
                "payment-service/" + env + "/audit/client/" + instance);
    }

    private static CachingConnectionFactory factory(
            String host, int port, String vhost,
            String username, String password, String namePrefix) {

        CachingConnectionFactory result =
                new CachingConnectionFactory(host, port);
        result.setVirtualHost(vhost);
        result.setUsername(username);
        result.setPassword(password);

        AtomicInteger sequence = new AtomicInteger();
        result.setConnectionNameStrategy(
                ignored -> namePrefix + "/" + sequence.incrementAndGet());

        // Tùy nhu cầu xác nhận publish trên hai broker.
        result.setPublisherConfirmType(
                CachingConnectionFactory.ConfirmType.CORRELATED);
        result.setPublisherReturns(true);
        return result;
    }
}
~~~

Mã minh họa chưa cấu hình TLS; không dùng nguyên cấu hình port 5672 không mã hóa nếu chính sách yêu cầu kết nối TLS. Cấu hình TLS trên từng underlying RabbitMQ Java client connection factory hoặc qua cách cấu hình Spring AMQP tương thích.

**Lưu ý:** một `CachingConnectionFactory` không nhất thiết chỉ có đúng một connection vật lý: số lượng còn phụ thuộc cache mode, listener, publisher connection riêng, reconnect và số instance ứng dụng.

### 4.3. Tạo RabbitTemplate và listener factory đúng broker

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MultiBrokerMessagingConfig {

    @Bean("ordersRabbitTemplate")
    RabbitTemplate ordersTemplate(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory cf) {
        RabbitTemplate template = new RabbitTemplate(cf);
        template.setMandatory(true);
        return template;
    }

    @Bean("auditRabbitTemplate")
    RabbitTemplate auditTemplate(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory cf) {
        RabbitTemplate template = new RabbitTemplate(cf);
        template.setMandatory(true);
        return template;
    }

    @Bean("ordersListenerFactory")
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory cf) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setDefaultRequeueRejected(false);
        return factory;
    }

    @Bean("auditListenerFactory")
    SimpleRabbitListenerContainerFactory auditListenerFactory(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory cf) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setDefaultRequeueRejected(false);
        return factory;
    }
}
~~~

`template.setMandatory(true)` cho phép nhận publisher returns với message không được route, khi factory và cơ chế callbacks/returns được cấu hình phù hợp. Confirm ACK vẫn chưa chứng minh listener đã xử lý message.

Nếu ứng dụng có nhiều bean cùng kiểu, dùng **`@Qualifier`** hoặc một cơ chế định tuyến rõ ràng. Tiêm `RabbitTemplate` không phân biệt có thể gây lỗi bean ambiguity hoặc chọn nhầm broker khi dùng `@Primary`. Không dùng `@Primary` để che giấu vấn đề thiết kế.

### 4.4. Consumer chỉ rõ broker bằng containerFactory

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BrokerConsumers {
    @RabbitListener(
        queues = "orders.inbox.q",
        containerFactory = "ordersListenerFactory"
    )
    public void onOrder(String payload) {
        // Đọc từ Orders broker và vhost /orders.
    }

    @RabbitListener(
        queues = "audit.inbox.q",
        containerFactory = "auditListenerFactory"
    )
    public void onAudit(String payload) {
        // Đọc từ Audit broker và vhost /audit.
    }
}
~~~

Các queue ở ví dụ **giả định đã được provision** đúng broker/vhost. Nếu ứng dụng quản lý exchange, queue và binding bằng `RabbitAdmin`, phải kiểm soát **admin nào khai báo topology nào**. Với nhiều `RabbitAdmin`, một `@Bean Queue` hoặc `Declarables` không được scope có thể bị khai báo ở nhiều broker ngoài ý muốn. Cần giới hạn declarable theo admin tương ứng hoặc provision bằng hạ tầng ngoài ứng dụng.

Tên queue chỉ có ý nghĩa trong vhost nơi connection đang hoạt động. Hai cluster có thể có queue cùng tên; chúng không tự chia sẻ message.

## 5. Kiểm tra connection name thực tế

Connection name chỉ xuất hiện khi underlying connection đã được tạo. Sau khi ứng dụng kết nối, mở **RabbitMQ Management → Connections** tại từng broker để kiểm tra:

~~~text
Orders cluster: payment-service/prod/orders/client/pod-03/1
               user=orders-app, vhost=/orders

Audit cluster:  payment-service/prod/audit/client/pod-03/1
               user=audit-app, vhost=/audit
~~~

Có thể dùng CLI RabbitMQ trên broker:

~~~bash
rabbitmqctl list_connections name user vhost state client_properties
~~~

Tùy phiên bản RabbitMQ/Management, client-provided name có thể hiện trong trường riêng hoặc trong client properties. Nếu không thấy tên mong đợi, kiểm tra strategy được cài **trước lần mở connection**, app có thực sự dùng đúng connection factory, và connection có đang được tái sử dụng từ cache không. Khi điều tra, kết hợp **node, vhost, user, peer address, client-provided name và thời điểm tạo connection**.

## 6. Thiết kế metric theo từng broker hoặc nhóm khách hàng

Một hệ thống có nhiều broker cần kết hợp dữ liệu từ **ba tầng**:

| Tầng | Điều cần quan sát | Nguồn dữ liệu |
| --- | --- | --- |
| **RabbitMQ broker** | Connection state, RAM/disk alarm, số connection/channel, messages ready/unacked, publish/deliver/ACK rate. | RabbitMQ Management API, Prometheus plugin hoặc CLI. |
| **Spring AMQP client** | Lượt gọi publish, confirm ACK/NACK, returned message, timeout, listener error/retry, duration. | Application metrics, Micrometer, callback/sự kiện Spring AMQP. |
| **Nghiệp vụ** | Outbox pending, số job hoàn tất, consumer lag, DLQ quá hạn, kết quả theo nhóm khách hàng. | Database, transaction outbox/inbox, reconciliation job, business metrics. |

Không đồng nhất `connection open` với broker khỏe, `publisher confirm ACK` với xử lý thành công, hoặc `queue depth = 0` với công việc hoàn thành. Một event có thể đã ACK khỏi queue nhưng tác vụ nghiệp vụ còn `RUNNING` ở database.

### 6.1. Tag hữu ích nhưng phải giới hạn cardinality

| Tag | Giá trị ví dụ | Khi nào dùng |
| --- | --- | --- |
| `broker` | `orders`, `audit` | Hầu hết metric do application tự định nghĩa. |
| `environment` | `dev`, `staging`, `prod` | Tách môi trường. |
| `operation` | `publish`, `consume` | Tách vai trò xử lý. |
| `client_group` | `internal`, `enterprise`, `standard` | Nhóm tenant có số lượng hạn chế. |
| `result` | `ack`, `nack`, `timeout`, `returned` | Phân loại kết quả một bước xử lý. |
| `listener` | `orders-inbox`, `audit-inbox` | Tên logic ổn định của listener. |

**Không đưa `eventId`, `customerId`, `orderId`, email, connection name có sequence hoặc raw exception message vào metric tags.** Nếu có nhiều event/khách hàng, mỗi giá trị có thể tạo time series mới, gây bùng nổ cardinality, bộ nhớ và chi phí lưu trữ. Những ID chi tiết nên nằm trong **log/tracing/audit store** với quyền truy cập phù hợp.

Nếu hệ thống chỉ có một số rất ít tenant cố định, việc gắn nhãn tenant cụ thể có thể chấp nhận sau khi đánh giá quy mô. Với sản phẩm phục vụ hàng chục nghìn tenant, nên gắn `client_group` hoặc `service_tier` ở metrics, rồi dùng eventId/tenantId trong log để truy ngược một trường hợp.

### 6.2. Ví dụ Micrometer counter do ứng dụng tự định nghĩa

Spring Boot Actuator và Micrometer có thể giúp tạo metric theo nhãn hữu hạn:

~~~xml
<!-- Maven, đặt trong <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<!-- Thêm registry Micrometer Prometheus tương thích với Spring Boot
     nếu muốn export qua /actuator/prometheus. -->
~~~

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class BrokerOperationMetrics {
    private final MeterRegistry registry;

    public BrokerOperationMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordPublishRequest(String broker, String clientGroup) {
        Counter.builder("app.amqp.publish.requests")
                .description("RabbitMQ publish requests initiated by application")
                .tag("broker", broker)
                .tag("client_group", clientGroup)
                .register(registry)
                .increment();
    }

    public void recordPublishOutcome(String broker, String result) {
        Counter.builder("app.amqp.publish.outcomes")
                .tag("broker", broker)
                .tag("result", result)
                .register(registry)
                .increment();
    }
}
~~~

Đây là **metric ứng dụng tự tạo**, không phải tên metric RabbitMQ hoặc Spring AMQP tự xuất mặc định. Trong code thật, `broker` và `clientGroup` phải đến từ danh sách đã định, không nhận chuỗi bất kỳ từ request HTTP; `result` giới hạn vào các giá trị như `ack`, `nack`, `returned`, `timeout`. Có thể dùng enum hoặc lớp mapping để tránh tag không kiểm soát.

**Phân biệt điểm đo:** `recordPublishRequest()` là số lần ứng dụng **cố publish**, không phải broker đã nhận. `recordPublishOutcome()` phải được gọi tại điểm thật sự biết kết quả confirm/return/timeout. Một confirm ACK nhưng có returned message không nên được báo thành công được route.

### 6.3. Micrometer Observation và trace

Các dòng Spring AMQP hiện đại có hỗ trợ **Micrometer Observation** cho `RabbitTemplate` và listener container. Ví dụ trên phiên bản hỗ trợ:

~~~java
// Bật trên đúng template cụ thể nếu sử dụng Observation.
ordersTemplate.setObservationEnabled(true);
auditTemplate.setObservationEnabled(true);
~~~

Với listener, thiết lập observation trên **listener container factory** tương ứng theo API của phiên bản Spring AMQP đang dùng. Khi được cấu hình cùng Micrometer Tracing, publish/consume có thể đóng góp spans để điều tra luồng end-to-end.

Tên tag, khả năng context propagation và tương tác giữa **Micrometer timers cũ** với Observation phụ thuộc phiên bản Spring AMQP/Spring Boot. Không giả định bật Observation sẽ tự gắn nhãn broker theo alias của ứng dụng; bổ sung metadata hoặc custom convention phù hợp phiên bản, và tránh instrument hai lần làm metric trùng.

### 6.4. Dashboard nên có gì?

| Panel | Phân tách hữu ích | Cảnh báo khi |
| --- | --- | --- |
| Connection blocked/reconnect | broker, node, environment | Một broker bị block kéo dài hoặc reconnect tăng bất thường. |
| Confirm ACK/NACK/timeout | broker, result, client_group | Timeout/NACK tăng hoặc publish không có confirm trong SLA. |
| Publisher returns | broker, exchange/routing loại cố định | Message không được route do topology sai. |
| Queue ready/unacked, consumer count | broker, vhost, queue trọng yếu | Backlog liên tục tăng, consumer mất. |
| Listener failures và retry | broker, listener, error_category | Lỗi tăng theo nhóm hoặc xuất hiện poison loop. |
| Outbox oldest age, DLQ age | broker, client_group | Event tồn quá thời gian nghiệp vụ cho phép. |
| End-to-end completion latency | service, client_group | P95/P99 vượt SLA, dù queue đang rỗng. |

RabbitMQ Prometheus plugin có các metric ở cấp node/queue tùy cấu hình; **không mặc định tên tag `broker` giống tag ứng dụng**. Có thể thêm nhãn cluster tại tầng scrape/monitoring cho từng RabbitMQ target; kiểm tra cách đặt label trong hệ thống đang dùng.

## 7. Structured log cho từng broker và khách hàng

Log nên hỗ trợ truy vấn: “Trong 10 phút vừa qua, sự kiện nào của nhóm Enterprise đã publish đến broker Audit nhưng chưa có confirm hoặc consumer không tạo task?”. Để trả lời, cần các trường **ổn định và có ý nghĩa**:

~~~json
{
  "level": "WARN",
  "event": "amqp.publish.confirm_timeout",
  "service": "payment-service",
  "environment": "prod",
  "broker": "audit",
  "vhost": "/audit",
  "clientGroup": "enterprise",
  "eventId": "evt-1385",
  "exchange": "audit.events.x",
  "routingKey": "audit.payment",
  "result": "unknown",
  "traceId": "trace-example"
}
~~~

Đây là **schema log đề xuất**, không phải payload RabbitMQ hoặc Spring AMQP tự xuất đầy đủ. Trong nhiều tổ chức, log theo tenant cần chính sách truy cập và thời hạn lưu phù hợp; không lưu password, access token hoặc toàn bộ nội dung message chứa dữ liệu nhạy cảm.

Phân biệt:

- **Broker alias**: hệ RabbitMQ nào đang xử lý.
- **Business event ID**: định danh ổn định cho retry, idempotency và đối soát.
- **Trace ID**: đường đi một request qua nhiều dịch vụ và message.
- **AMQP correlation ID**: hữu ích cho request–reply; không mặc nhiên thay cho business ID.
- **AMQP delivery tag**: chỉ có ý nghĩa trên một channel, không phải ID duy nhất toàn hệ thống.

### 7.1. Gắn MDC tại publisher

SLF4J `MDC` cho phép ghi ngữ cảnh theo luồng thực thi. Ví dụ:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class OrdersPublisher {
    private static final Logger log =
            LoggerFactory.getLogger(OrdersPublisher.class);

    private final RabbitTemplate ordersTemplate;
    private final BrokerOperationMetrics metrics;

    public OrdersPublisher(
            @Qualifier("ordersRabbitTemplate") RabbitTemplate ordersTemplate,
            BrokerOperationMetrics metrics) {
        this.ordersTemplate = ordersTemplate;
        this.metrics = metrics;
    }

    public void publish(String eventId, String jsonBody) {
        try (MDC.MDCCloseable broker =
                     MDC.putCloseable("broker", "orders");
             MDC.MDCCloseable group =
                     MDC.putCloseable("clientGroup", "internal");
             MDC.MDCCloseable event =
                     MDC.putCloseable("eventId", eventId)) {

            metrics.recordPublishRequest("orders", "internal");
            CorrelationData correlation = new CorrelationData(eventId);
            log.info("Publish requested exchange={} routingKey={}",
                    "orders.events.x", "order.created");

            ordersTemplate.convertAndSend(
                    "orders.events.x",
                    "order.created",
                    jsonBody,
                    message -> {
                        message.getMessageProperties().setMessageId(eventId);
                        return message;
                    },
                    correlation
            );

            correlation.getFuture().whenComplete((confirm, error) -> {
                // Callback có thể chạy trên thread khác và không có MDC.
                if (error != null || confirm == null) {
                    metrics.recordPublishOutcome("orders", "error");
                    log.warn("Publish outcome unknown broker={} eventId={}",
                            "orders", eventId, error);
                } else if (!confirm.isAck()) {
                    metrics.recordPublishOutcome("orders", "nack");
                    log.warn("Publish NACK broker={} eventId={}",
                            "orders", eventId);
                } else if (correlation.getReturned() != null) {
                    metrics.recordPublishOutcome("orders", "returned");
                    log.warn("Publish returned broker={} eventId={}",
                            "orders", eventId);
                } else {
                    metrics.recordPublishOutcome("orders", "ack");
                    log.info("Publish confirmed broker={} eventId={}",
                            "orders", eventId);
                }
            });
        }
    }
}
~~~

Mã minh họa dùng `CorrelationData.getFuture()` theo API Spring AMQP tương thích và yêu cầu **publisher confirm/returns** được bật như cấu hình trên. Nó chưa có outbox, bộ hẹn timeout và xử lý mọi nhánh lỗi khi `convertAndSend` ném exception; production cần bổ sung các trường hợp này và ghi kết quả vào persistent store.

Trong callback, log ghi `broker`/`eventId` **tường minh** vì callback có thể chạy trên thread khác. Một `MDC.put(...)` ở thread HTTP không được bảo đảm tự truyền tới callback `CompletableFuture`, thread scheduler, `@Async` hoặc `@RabbitListener`. Dùng context propagation từ tracing framework hoặc truyền các giá trị cần thiết làm dữ liệu. `MDC.putCloseable` giúp khôi phục/xóa context sau mỗi request, tránh rò thông tin giữa các lần dùng thread pool.

**Không ghi `convertAndSend` trả về thành công nghiệp vụ.** Nó mới cho biết việc gọi API ở phía ứng dụng đã kết thúc; confirm, return và consumer ACK thuộc các bước khác nhau.

### 7.2. Gắn MDC tại listener

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersLoggedListener {
    private static final Logger log =
            LoggerFactory.getLogger(OrdersLoggedListener.class);

    @RabbitListener(
        queues = "orders.inbox.q",
        containerFactory = "ordersListenerFactory"
    )
    public void handle(Message message) {
        String eventId = message.getMessageProperties().getMessageId();
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("Missing messageId");
        }

        try (MDC.MDCCloseable broker =
                     MDC.putCloseable("broker", "orders");
             MDC.MDCCloseable event =
                     MDC.putCloseable("eventId", eventId)) {
            log.info("Message received queue={} routingKey={}",
                    "orders.inbox.q",
                    message.getMessageProperties().getReceivedRoutingKey());

            // Xử lý trong database transaction, dùng eventId để dedupe.
            log.info("Listener returned normally");
        }
    }
}
~~~

Listener trên minh họa log và kiểm tra `eventId`. Nếu message không có ID hợp lệ, exception cần được xử lý bằng **retry giới hạn/DLX/DLQ** hoặc error handler phù hợp; chỉ đặt `defaultRequeueRejected=false` mà queue không có DLX có thể làm message bị loại bỏ. Không bật đồng thời `BrokerConsumers.onOrder` và `OrdersLoggedListener` trên cùng queue khi chạy thử, vì hai listener cạnh tranh message.

Log “listener returned normally” cũng **chưa xác nhận ACK đã được broker ghi nhận**, vì listener container thực hiện ACK theo cấu hình sau khi lời gọi xử lý.

## 8. Nhiều khách hàng và nguy cơ tăng số connection/metric

Không phải lúc nào một tenant cũng cần một `CachingConnectionFactory`:

| Quy mô và yêu cầu | Thiết kế thường cân nhắc | Điểm cần kiểm soát |
| --- | --- | --- |
| Ít tenant, cô lập rõ ràng | Mỗi tenant có vhost hoặc cluster và factory riêng. | Connection/channel count, quyền, RAM, lifecycle. |
| Rất nhiều tenant dùng chung hệ thống | Chia sẻ factory theo broker/nhóm, truyền tenant context ở tầng ứng dụng. | Không lộ dữ liệu chéo tenant, fairness, giới hạn tốc độ. |
| Tenant yêu cầu cô lập cao | Cluster riêng, credential/TLS/network riêng khi cần. | Chi phí, vận hành, disaster recovery và SLA. |

Nếu có 100 tenant, 20 instance ứng dụng và mỗi instance mở một connection cho từng tenant, số connection có thể đã ở mức hàng nghìn trước khi tính connection phụ dành cho publisher/listener. Mỗi connection và channel tốn bộ nhớ và tài nguyên broker. Trước khi chọn thiết kế, cần đo giới hạn RabbitMQ và kịch bản tăng trưởng.

Với tenant chia sẻ connection, **connection name nên biểu thị broker/role/instance**, không cố nhồi mọi customer ID vào một tên. Metrics chỉ tag `client_group` hoặc lớp dịch vụ có số lượng hữu hạn; log/tracing ghi tenant alias an toàn và business event ID. Không tin một header `tenantId` do producer không đáng tin cậy gửi tới như cơ chế xác thực: service phải kiểm tra quyền tenant bằng nguồn đáng tin cậy.

## 9. Khi broker lỗi: metric và log phải hỗ trợ phục hồi đúng

Giả sử vào 10:00 broker Audit gặp disk alarm. Dashboard hiển thị:

~~~text
broker=orders: confirm p95 bình thường; consumer vẫn ACK.
broker=audit:  publish confirm timeout tăng; connection blocked.
RabbitMQ Audit: node-02 disk_free xuống dưới disk limit.
Business: audit outbox pending age tăng.
~~~

Cách xử lý:

1. Xác nhận alarm và node bị ảnh hưởng qua RabbitMQ Management, `rabbitmq-diagnostics alarms` và metric tài nguyên.
2. Giảm tốc hoặc tạm hoãn publisher Audit; giữ message quan trọng trong outbox bền vững. Tránh làm gián đoạn Orders nếu hai hệ có thể hoạt động độc lập.
3. Khôi phục nguyên nhân thiếu đĩa/bộ nhớ; không dùng vòng lặp reconnect để che resource alarm.
4. Khi broker Audit trở lại, xử lý outbox theo tốc độ có giới hạn, giữ nguyên eventId khi retry vì kết quả publish cũ có thể chưa rõ.
5. Consumer Audit phải idempotent; đối soát dữ liệu nghiệp vụ trước khi kết luận đã phục hồi.

**Không tự động chuyển message Audit sang Orders** chỉ để tránh lỗi nếu chưa có thiết kế fallback rõ ràng. Hai broker có thể phục vụ mục đích, quyền truy cập và consumers khác nhau.

### 9.1. Phân biệt các loại bằng chứng

| Bằng chứng | Biết được | Chưa biết được |
| --- | --- | --- |
| `convertAndSend` được gọi | Ứng dụng đã yêu cầu publish. | Broker đã lưu hoặc route message chưa. |
| Publisher confirm ACK | Broker xác nhận publish theo cơ chế confirm. | Đã có consumer xử lý chưa. |
| Publisher return | Message publish với mandatory không định tuyến được. | Không phải mọi lỗi consumer đều sinh return. |
| Queue có message | Message hiện đang chờ xử lý. | Kết quả nghiệp vụ đã hoàn tất chưa. |
| Consumer ACK | Delivery được xác nhận theo cơ chế ACK. | Mọi side effect ngoài RabbitMQ đã hoàn tất nguyên tử chưa. |
| Outbox/inbox/task records | Có dấu vết để đối soát đầu cuối. | Chưa chắc hệ thống bên ngoài đã tạo đúng một tác dụng phụ nếu không có idempotency. |

Muốn độ tin cậy đầu cuối, kết hợp **transactional outbox, eventId ổn định, publisher confirm/return, idempotent inbox, retry có giới hạn, DLQ và reconciliation**. Connection name và metric giúp xác định nơi lỗi, còn dữ liệu nghiệp vụ mới xác định công việc có thực sự hoàn tất.

## 10. Bảng sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không thấy connection name mong đợi | Connection chưa mở, strategy cài muộn hoặc app dùng factory khác. | Kiểm tra factory đang được dùng và connection hiện có trong broker. |
| Hai broker có connection name giống nhau | Cùng cấu hình tên nhưng endpoint khác. | Kiểm tra node, vhost, username và địa chỉ kết nối. |
| Một factory xuất hiện nhiều connection | Reconnect, nhiều replica, publisher connection riêng hoặc cache mode. | Xem lifecycle và cấu hình factory. |
| Queue Audit tăng dù code ghi gửi Orders | Tiêm nhầm template hoặc listener/admin trỏ sai broker. | Đối chiếu bean name, host/vhost và correlation eventId. |
| Metrics không có tag `broker` | Exporter chưa có label này. | Thêm nhãn cluster ở tầng scrape hoặc custom application metrics. |
| Số time series tăng rất nhanh | Gắn tenantId/eventId/connection name vào metric tags. | Gỡ nhãn cardinality cao và chuyển ID sang logs/traces. |
| Confirm callback log mất tenant/broker | Thread callback không giữ MDC của thread gọi. | Capture context và truyền tường minh hoặc dùng context propagation. |
| Broker A lỗi làm cả service ngừng | Thread pool/transaction/retry/connection dùng chung không được cô lập. | Xem bulkhead, timeout, queue và outbox cho từng broker. |
| Đã có tên connection nhưng publish không tới queue | Routing sai hoặc topology chưa khai báo đúng vhost. | Kiểm tra mandatory returns, exchange–binding–queue và RabbitAdmin. |

## 11. Bài thực hành

**Bối cảnh:** Spring Boot service dùng Orders broker và Audit broker; khách hàng thuộc nhóm Standard hoặc Enterprise. Cần quan sát được broker nào lỗi, nhóm nào bị ảnh hưởng và event nào chưa được xử lý.

1. Tạo hai `CachingConnectionFactory` với host/vhost/credential riêng, đặt `ConnectionNameStrategy` theo quy ước `service/env/broker/role/instance/sequence`.
2. Tạo `ordersRabbitTemplate`, `auditRabbitTemplate` và các listener factory riêng. Provision exchange, queue, binding đúng từng broker; tránh khai báo nhầm qua RabbitAdmin.
3. Khởi động ứng dụng và publish/consume thử mỗi broker. Kiểm tra client-provided connection name, user và vhost trong Management UI.
4. Thêm metrics `app.amqp.publish.requests` và `app.amqp.publish.outcomes` với `broker`, `client_group`, `result`; xác nhận không chứa eventId/customerId trong metric tags.
5. Dùng MDC để log `broker`, `eventId`, `exchange`, `routingKey` ở cả publisher/consumer; kiểm tra callback bất đồng bộ vẫn có broker và eventId tường minh.
6. Cấu hình correlated confirms và publisher returns. Gửi một message tới routing key **không có binding** tại broker Audit; quan sát trường hợp broker confirm ACK nhưng message được return.
7. Trong môi trường test, dừng consumer Audit hoặc ngắt kết nối Audit có kiểm soát; xác minh metric/log xác định đúng `broker=audit` còn Orders vẫn xử lý độc lập.
8. Thêm outbox với eventId cố định và retry có giới hạn; kiểm tra consumer idempotency khi publish lại event cũ.
9. Sinh nhiều eventId mới và chứng minh series count của metric không tăng theo eventId vì không dùng eventId làm nhãn.

### Câu hỏi tự kiểm tra

**Câu 1.** Hai connection cùng tên `payment-service` có chắc thuộc cùng một broker không?

**Đáp án:** Không. Tên do client cung cấp, có thể trùng. Kiểm tra node, endpoint, user và vhost.

**Câu 2.** Vì sao không gắn `customerId` và `eventId` làm Prometheus tag ở hệ thống SaaS lớn?

**Đáp án:** Vì số lượng giá trị không giới hạn tạo ra cardinality rất cao; nên dùng nhóm cố định cho metric, lưu ID chi tiết ở log/tracing và bảng đối soát.

**Câu 3.** Broker Audit xác nhận ACK nhưng consumer Audit không nhận message. Đã giao thành công chưa?

**Đáp án:** Chưa thể kết luận. Kiểm tra publisher return, mandatory, exchange–binding–queue, consumer và trạng thái downstream. Confirm ACK không xác nhận nghiệp vụ đã xử lý.

**Câu 4.** MDC đặt ở thread HTTP có chắc tồn tại trong callback `CompletableFuture` không?

**Đáp án:** Không. Callback có thể chạy trên thread khác; truyền context cần thiết tường minh hoặc dùng tracing/context propagation.

**Câu 5.** Khi Audit broker không sẵn sàng, có nên tự dùng template Orders để gửi cùng message không?

**Đáp án:** Không nếu chưa thiết kế fallback. Phải tôn trọng routing/permissions của từng broker, ghi bền vững vào outbox và retry an toàn với eventId cũ.

## 12. Ghi nhớ

Với Spring AMQP nhiều RabbitMQ broker hoặc nhiều khách hàng, **đặt connection name có cấu trúc**, cấu hình **ConnectionFactory–RabbitTemplate–listener factory–RabbitAdmin** đúng từng broker, và thống nhất broker alias xuyên metric/log/tracing. **Metric tags** cần ít giá trị, còn **tenantId, eventId, traceId** phù hợp cho log hoặc audit có quyền kiểm soát. Kết hợp quan sát với **publisher confirms/returns, consumer ACK, retry, DLQ, outbox/inbox và đối soát** để phát hiện và phục hồi sự cố giao message. Connection name giúp định vị, không thay thế bảo đảm xử lý nghiệp vụ.

### Tài liệu tham khảo để đối chiếu theo phiên bản

- [Spring AMQP – Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): CachingConnectionFactory, naming và kết nối publisher.
- [Spring AMQP – RabbitTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html): confirms, returns và publish.
- [Spring AMQP – Receiving Messages](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): listener container factory.
- [Spring AMQP – Micrometer Observation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/micrometer-observation.html): observation/tracing; xác nhận API theo phiên bản.
- [RabbitMQ – Connections](https://www.rabbitmq.com/docs/connections): trạng thái, properties và quản trị kết nối.
- [RabbitMQ – Prometheus Monitoring](https://www.rabbitmq.com/docs/prometheus): metric broker, node và queue.
