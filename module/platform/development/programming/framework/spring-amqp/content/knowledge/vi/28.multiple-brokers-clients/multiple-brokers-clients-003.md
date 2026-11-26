# Nhiều ConnectionFactory, RabbitTemplate và container factory

Khi một ứng dụng phải làm việc với nhiều RabbitMQ broker, việc chỉ định đúng **nơi kết nối, nơi publish, nơi nhận và nơi khai báo topology** quan trọng không kém logic xử lý message. Ví dụ: dịch vụ bán hàng publish sự kiện đơn hàng lên **broker Orders**, đồng thời publish bản ghi kiểm toán lên **broker Audit**. Hai broker có host, virtual host, tài khoản, exchange, queue và chính sách giao nhận khác nhau.

Trong module **SPRING_AMQP**, bài này thuộc chương **Nhiều broker và khách hàng**. Ta kết hợp `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, publisher confirms, ACK/NACK, retry, dead-letter và quan sát để xây hệ thống xử lý bất đồng bộ đáng tin cậy.

Bốn đối tượng cần hiểu rõ:

- **`ConnectionFactory`:** tạo và quản lý kết nối tới một đích RabbitMQ. `CachingConnectionFactory` là loại thường dùng trong Spring AMQP.
- **`RabbitTemplate`:** dùng một connection factory để `send`, `convertAndSend`, request/reply và theo dõi publish.
- **`RabbitListenerContainerFactory`:** tạo listener container chạy `@RabbitListener`; quyết định connection, concurrency, prefetch, ACK/NACK và cơ chế xử lý lỗi.
- **`RabbitAdmin`:** khai báo exchange, queue, binding đúng broker/vhost. Với nhiều broker, cần giới hạn quyền khai báo của từng admin.

**Nguyên tắc xuyên suốt:** Mỗi đường xử lý phải chỉ rõ **factory nào kết nối**, **template nào publish**, **container factory nào consume** và **admin nào khai báo**. Tên exchange/queue **không tự chọn** broker.

## 1. Phân biệt các kiểu “nhiều broker”

| Tình huống | Kiến trúc phù hợp | Điểm cần nhớ |
|---|---|---|
| Một cluster, một virtual host, nhiều loại message | Có thể chỉ cần một `ConnectionFactory` và nhiều template/factory có cấu hình khác nhau | Không bắt buộc tạo connection mới chỉ vì nhiều queue |
| Một cluster có hai virtual host | Mỗi vhost dùng một `ConnectionFactory` | Các queue/exchange nằm trong namespace tách biệt |
| Hai RabbitMQ cluster độc lập | Hai `ConnectionFactory` với các template/listener/admin riêng | Một message gửi tới A không tự xuất hiện ở B |
| Nhiều node trong cùng một cluster | Một `CachingConnectionFactory` có danh sách endpoint cluster | `setAddresses` không phải fan-out sang nhiều broker |
| Muốn chuyển event từ broker A sang broker B | Bridge/relay riêng, có retry và deduplication | Không có AMQP transaction chung trên hai broker |

**Ví dụ:** `orders.events` ở broker A và `orders.events` ở broker B là **hai exchange khác nhau** dù trùng tên. Ngược lại, nhiều connection đến cùng cluster/vhost vẫn có thể chia sẻ cùng tên queue/exchange thuộc broker đó.

Sơ đồ của bài:

```text
                        Spring Boot application
       +---------------------------------------------------+
       |                                                   |
       | ordersConnectionFactory       auditConnectionFactory
       |        |                               |          |
       |   ordersTemplate                    auditTemplate |
       |   ordersListenerFactory             auditListenerFactory
       |   ordersAdmin                       auditAdmin    |
       +--------|------------------------------|----------+
                |                              |
                v                              v
        RabbitMQ A (/orders)              RabbitMQ B (/audit)
             orders.events                    audit.events
                  |                               |
           orders.created.work                audit.log.work
                  |                               |
           orders.created.dead                audit.log.dead
```

Hai broker có thể chết hoặc phục hồi vào thời điểm khác nhau. Một health check chung “RabbitMQ connected” là không đủ để nhận biết đường nào đang lỗi.

## 2. Danh sách bean cần cấu hình

Ta đặt tên rõ nghĩa để hạn chế nhầm lẫn:

| Vai trò | Broker Orders | Broker Audit |
|---|---|---|
| Connection | `ordersConnectionFactory` | `auditConnectionFactory` |
| Publisher | `ordersTemplate` | `auditTemplate` |
| Consumer factory | `ordersListenerFactory` | `auditListenerFactory` |
| Topology admin | `ordersAdmin` | `auditAdmin` |
| Exchange chính | `orders.events` | `audit.events` |
| Queue làm việc | `orders.created.work` | `audit.log.work` |
| DLX | `orders.dlx` | `audit.dlx` |
| Dead queue | `orders.created.dead` | `audit.log.dead` |

Các tên bean như `ordersTemplate` là **tên trong Spring ApplicationContext**. Các chuỗi `orders.events` và `orders.created.work` là **tên trong RabbitMQ**; cần nhìn chúng cùng broker/vhost mới xác định được đúng đích.

Mỗi loại có nhiều bean, vì vậy sử dụng `@Qualifier` khi inject và `containerFactory` trên `@RabbitListener`. Dùng `@Primary` đơn thuần chỉ chọn ứng viên mặc định, **không** tạo logic routing dựa trên exchange hay message.

## 3. Cấu hình mẫu với Spring Boot 3.x / Spring AMQP 3.x

Ví dụ Java 17+ bên dưới sử dụng **Spring Boot 3.x và Spring AMQP 3.x**. Cấu trúc nhiều factory vẫn áp dụng ở những phiên bản khác, nhưng cần kiểm tra package/API tương ứng khi nâng major version.

Để tránh vô tình sử dụng các bean RabbitMQ mặc định, bài thực hành khai báo mọi thành phần thủ công và loại trừ `RabbitAutoConfiguration` của Spring Boot:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.amqp.RabbitAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;

@SpringBootApplication(exclude = RabbitAutoConfiguration.class)
@EnableRabbit
@EnableConfigurationProperties(BrokerEndpoints.class)
public class MultiBrokerApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiBrokerApplication.class, args);
    }
}
```

Khi exclude auto-configuration, ứng dụng không dựa vào `RabbitTemplate` hoặc `rabbitListenerContainerFactory` mặc định; các bean cần thiết sẽ được khai báo dưới đây. Với dự án không exclude, phải rà soát bean do Boot tạo, `@Primary` và dependency injection để tránh bean ngoài ý muốn. Spring Boot có thể hỗ trợ cấu hình mặc định bằng `spring.rabbitmq.*` nhưng không tự tạo hai kết nối độc lập chỉ vì bạn thêm hai cấu hình tùy ý.

### 3.1. Khai báo thông tin hai broker

```yaml
app:
  rabbit:
    orders:
      host: rabbit-orders.internal
      port: 5672
      virtual-host: /orders
      username: __ORDERS_USER__
      password: __ORDERS_PASSWORD__
    audit:
      host: rabbit-audit.internal
      port: 5672
      virtual-host: /audit
      username: __AUDIT_USER__
      password: __AUDIT_PASSWORD__
```

Các chuỗi `__ORDERS_USER__`, `__ORDERS_PASSWORD__`, `__AUDIT_USER__`, `__AUDIT_PASSWORD__` là **placeholder cần thay bằng giá trị do secret manager hoặc biến môi trường cung cấp**. Khi dùng Spring property placeholders, có thể tham chiếu biến môi trường trong cấu hình triển khai. Không commit tài khoản thực hay mật khẩu vào repository.

`virtual-host` là namespace RabbitMQ, **không phải path HTTP**. Broker phải tạo các vhost và gán đúng quyền cho service account. Cổng 5672 minh họa AMQP TCP; môi trường production thường cần cấu hình TLS, xác minh certificate/hostname và cổng phù hợp.

Ta ánh xạ `app.rabbit` vào record:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.rabbit")
public record BrokerEndpoints(Broker orders, Broker audit) {
    public record Broker(
            String host,
            int port,
            String virtualHost,
            String username,
            String password) {
    }
}
```

Với cấu hình thực tế, bổ sung validation đầu vào để phát hiện thiếu endpoint/credential ngay khi startup, thay vì chờ lỗi kết nối đầu tiên.

### 3.2. Tạo hai CachingConnectionFactory

```java
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BrokerConnections {

    @Bean("ordersConnectionFactory")
    CachingConnectionFactory ordersConnectionFactory(BrokerEndpoints properties) {
        return create(properties.orders());
    }

    @Bean("auditConnectionFactory")
    CachingConnectionFactory auditConnectionFactory(BrokerEndpoints properties) {
        return create(properties.audit());
    }

    private static CachingConnectionFactory create(BrokerEndpoints.Broker b) {
        CachingConnectionFactory factory =
                new CachingConnectionFactory(b.host(), b.port());
        factory.setVirtualHost(b.virtualHost());
        factory.setUsername(b.username());
        factory.setPassword(b.password());

        // Publisher confirms và returns được bật cho TỪNG broker.
        factory.setPublisherConfirmType(
                CachingConnectionFactory.ConfirmType.CORRELATED);
        factory.setPublisherReturns(true);
        return factory;
    }
}
```

`CachingConnectionFactory` là đối tượng Spring AMQP bao bọc RabbitMQ Java client. Mỗi bean quản lý tài nguyên connection/channel của riêng đích RabbitMQ. Bật confirms/returns ở `ordersConnectionFactory` không tác động tới broker audit; ở ví dụ, helper bật trên cả hai.

**Không trộn địa chỉ độc lập trong một factory để giả lập hai đích.** Danh sách endpoint của cùng cluster hỗ trợ phục hồi kết nối, còn chọn broker theo nghiệp vụ là trách nhiệm riêng.

### 3.3. Khai báo hai RabbitTemplate

```java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BrokerTemplates {

    @Bean("ordersTemplate")
    RabbitTemplate ordersTemplate(
            @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
        RabbitTemplate template = new RabbitTemplate(factory);
        template.setMandatory(true);
        return template;
    }

    @Bean("auditTemplate")
    RabbitTemplate auditTemplate(
            @Qualifier("auditConnectionFactory") ConnectionFactory factory) {
        RabbitTemplate template = new RabbitTemplate(factory);
        template.setMandatory(true);
        return template;
    }
}
```

`mandatory=true` yêu cầu broker trả lại message không có route đến queue khi các điều kiện về return được đáp ứng. Điều này giúp phát hiện exchange nhận publish nhưng không có binding, song **chỉ bật property chưa có nghĩa ứng dụng đã xử lý return**.

Các template có thể có `MessageConverter`, request/reply timeout, retry và callbacks khác nhau. Chẳng hạn, nếu Orders giao tiếp bằng DTO JSON còn Audit nhận chuỗi văn bản, phải đảm bảo converter phía publisher và listener nhất quán với hợp đồng riêng.

### 3.4. Hai RabbitListenerContainerFactory

```java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BrokerListenersConfig {

    @Bean("ordersListenerFactory")
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            @Qualifier("ordersConnectionFactory") ConnectionFactory cf) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(4);
        factory.setPrefetchCount(10);
        factory.setDefaultRequeueRejected(false);
        return factory;
    }

    @Bean("auditListenerFactory")
    SimpleRabbitListenerContainerFactory auditListenerFactory(
            @Qualifier("auditConnectionFactory") ConnectionFactory cf) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setConcurrentConsumers(1);
        factory.setMaxConcurrentConsumers(2);
        factory.setPrefetchCount(5);
        factory.setDefaultRequeueRejected(false);
        return factory;
    }
}
```

`SimpleRabbitListenerContainerFactory` là **factory tạo container** cho method được gắn `@RabbitListener`. Nó không trực tiếp quyết định exchange/routing key lúc publish. Mỗi factory ở ví dụ trỏ tới connection tương ứng và có concurrency/prefetch độc lập.

`defaultRequeueRejected(false)` minh họa chính sách đưa lỗi đến DLQ khi có DLX đúng ở mục 4. Nếu không cấu hình DLX, message reject không requeue có thể bị loại mất; sản phẩm thực cần retry hữu hạn có backoff cho lỗi hạ tầng và phân loại lỗi nghiệp vụ.

## 4. Khai báo RabbitAdmin và topology đúng broker

Một bẫy lớn khi có hai `RabbitAdmin`: theo mặc định, các admin đang auto-startup có thể xem tất cả bean `Queue`, `Exchange`, `Binding` trong context và **đều cố khai báo chúng lên broker của mình**.

Spring AMQP hỗ trợ giới hạn này bằng:

- `RabbitAdmin#setExplicitDeclarationsOnly(true)`: admin chỉ khai báo tài nguyên được gắn với nó.
- `setAdminsThatShouldDeclare(admin)` trên `Queue`, `Exchange`, `Binding`: chọn admin có quyền khai báo.
- `Declarables`: nhóm các đối tượng topology trong Spring context.

### 4.1. Admin của từng broker

```java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BrokerAdmins {

    @Bean("ordersAdmin")
    RabbitAdmin ordersAdmin(
            @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
        RabbitAdmin admin = new RabbitAdmin(factory);
        admin.setExplicitDeclarationsOnly(true);
        return admin;
    }

    @Bean("auditAdmin")
    RabbitAdmin auditAdmin(
            @Qualifier("auditConnectionFactory") ConnectionFactory factory) {
        RabbitAdmin admin = new RabbitAdmin(factory);
        admin.setExplicitDeclarationsOnly(true);
        return admin;
    }
}
```

Nếu bật `explicitDeclarationsOnly` mà **quên gán admin** cho declarables, các tài nguyên chưa được đánh dấu có thể không được tự khai báo bởi hai admin này. Vì thế phải thực hiện đủ cả hai bước.

### 4.2. Topology ở broker Orders

```java
import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersTopology {

    @Bean
    Declarables ordersDeclarables(@Qualifier("ordersAdmin") RabbitAdmin admin) {
        DirectExchange main = new DirectExchange("orders.events");
        DirectExchange dlx = new DirectExchange("orders.dlx");

        Queue work = QueueBuilder.durable("orders.created.work")
                .deadLetterExchange("orders.dlx")
                .deadLetterRoutingKey("orders.failed")
                .build();
        Queue dead = QueueBuilder.durable("orders.created.dead").build();

        Binding in = BindingBuilder.bind(work)
                .to(main).with("orders.created");
        Binding error = BindingBuilder.bind(dead)
                .to(dlx).with("orders.failed");

        main.setAdminsThatShouldDeclare(admin);
        dlx.setAdminsThatShouldDeclare(admin);
        work.setAdminsThatShouldDeclare(admin);
        dead.setAdminsThatShouldDeclare(admin);
        in.setAdminsThatShouldDeclare(admin);
        error.setAdminsThatShouldDeclare(admin);

        return new Declarables(main, dlx, work, dead, in, error);
    }
}
```

Đây là topology **chỉ được ordersAdmin khai báo lên broker A/vhost `/orders`**. `ordersTemplate` và `ordersListenerFactory` cũng dùng connection factory của A. Khi container nhận một delivery thất bại và reject không requeue, RabbitMQ A sẽ thử dead-letter theo binding `orders.dlx → orders.created.dead`.

### 4.3. Topology ở broker Audit

```java
@Configuration
public class AuditTopology {

    @Bean
    Declarables auditDeclarables(@Qualifier("auditAdmin") RabbitAdmin admin) {
        DirectExchange main = new DirectExchange("audit.events");
        DirectExchange dlx = new DirectExchange("audit.dlx");

        Queue work = QueueBuilder.durable("audit.log.work")
                .deadLetterExchange("audit.dlx")
                .deadLetterRoutingKey("audit.failed")
                .build();
        Queue dead = QueueBuilder.durable("audit.log.dead").build();

        Binding in = BindingBuilder.bind(work)
                .to(main).with("audit.recorded");
        Binding error = BindingBuilder.bind(dead)
                .to(dlx).with("audit.failed");

        main.setAdminsThatShouldDeclare(admin);
        dlx.setAdminsThatShouldDeclare(admin);
        work.setAdminsThatShouldDeclare(admin);
        dead.setAdminsThatShouldDeclare(admin);
        in.setAdminsThatShouldDeclare(admin);
        error.setAdminsThatShouldDeclare(admin);

        return new Declarables(main, dlx, work, dead, in, error);
    }
}
```

Ví dụ dùng các import `org.springframework.amqp.core.*`, `org.springframework.amqp.rabbit.core.RabbitAdmin`, `org.springframework.beans.factory.annotation.Qualifier`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration` như mục trước.

**Kết quả cần quan sát**:

| RabbitMQ | Exchange | Queue chính | DLQ |
|---|---|---|---|
| Broker A, vhost `/orders` | `orders.events` | `orders.created.work` | `orders.created.dead` |
| Broker B, vhost `/audit` | `audit.events` | `audit.log.work` | `audit.log.dead` |

Nếu thấy topology Orders trên broker Audit hoặc ngược lại, kiểm tra các bean `RabbitAdmin` khác, `explicitDeclarationsOnly`, `setAdminsThatShouldDeclare` và cơ chế khai báo annotation.

### 4.4. queues và queuesToDeclare không giống nhau

- `@RabbitListener(queues="orders.created.work")`: listener **đọc queue có tên này**; tên queue không tự tạo topology.
- `@RabbitListener(queuesToDeclare=@Queue("orders.created.work"))`: annotation yêu cầu khai báo queue và có thể phối hợp admin phù hợp.
- `@RabbitListener(bindings=@QueueBinding(...))`: annotation có thể định nghĩa queue/exchange/binding.
- Từ Spring AMQP 2.3, với nhiều broker, hạ tầng hỗ trợ quy ước tên bean admin **`<container-factory-name>-admin`** khi chọn admin khai báo tài nguyên tạo bởi `queuesToDeclare`/`bindings`. Cơ chế này **không áp dụng để tự khai báo một queue chỉ có `queues`**.

Ví dụ của bài đã khai báo bằng `Declarables`; listener bên dưới dùng `queues` để đọc tài nguyên có sẵn, tránh dựa vào quy ước admin ngầm.

## 5. Sử dụng @Qualifier để gửi và containerFactory để nhận

### 5.1. Publisher chọn đúng template

```java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class MultiBrokerPublisher {
    private final RabbitTemplate orders;
    private final RabbitTemplate audit;

    public MultiBrokerPublisher(
            @Qualifier("ordersTemplate") RabbitTemplate orders,
            @Qualifier("auditTemplate") RabbitTemplate audit) {
        this.orders = orders;
        this.audit = audit;
    }

    public void orderCreated(String orderId) {
        orders.convertAndSend(
                "orders.events", "orders.created", orderId);
    }

    public void auditRecorded(String text) {
        audit.convertAndSend(
                "audit.events", "audit.recorded", text);
    }
}
```

**Mã trên chưa đợi publisher confirm**. Nó minh họa chọn đúng broker bằng template; các message quan trọng cần sử dụng confirms/returns ở mục 6 hoặc message relay. Một lời gọi `convertAndSend` không phát song song tới cả hai broker.

### 5.2. Hai consumer chọn đúng factory

```java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class MultiBrokerConsumers {

    @RabbitListener(
            queues = "orders.created.work",
            containerFactory = "ordersListenerFactory")
    public void consumeOrder(String orderId) {
        System.out.println("Orders broker: " + orderId);
    }

    @RabbitListener(
            queues = "audit.log.work",
            containerFactory = "auditListenerFactory")
    public void consumeAudit(String auditText) {
        System.out.println("Audit broker: " + auditText);
    }
}
```

Mỗi `@RabbitListener` dùng tên bean `containerFactory` đã khai báo. Nếu quên thuộc tính, Spring thường tìm bean mặc định tên `rabbitListenerContainerFactory`; với cấu hình ở bài, factory mặc định không có nên endpoint có thể không khởi tạo. Trong ứng dụng có factory mặc định, thiếu `containerFactory` còn có thể làm consumer chạy **nhầm broker**.

Trong sản phẩm thật, thay `System.out.println` bằng service xử lý nghiệp vụ, observability, transaction và idempotency. Listener thành công và `AUTO` ack mode khiến container xác nhận delivery trên channel của **broker tương ứng**, không thể ACK message ở broker còn lại.

### 5.3. Ví dụ sai đích

```java
// Sai: queue Orders có trên A nhưng factory ở đây kết nối B.
@RabbitListener(
        queues = "orders.created.work",
        containerFactory = "auditListenerFactory")
public void wrongConsumer(String payload) {
}
```

Lỗi này có thể dẫn đến consumer không tìm thấy queue hoặc khởi động thất bại. `ordersTemplate` vẫn gửi đúng A, nhưng listener đang nghe B: hai thành phần không gặp nhau. Thử nghiệm đúng phải kiểm tra **host/vhost của cả publisher và consumer**, bên cạnh tên exchange/queue.

## 6. Confirm, return, ACK và DLQ ở từng broker

### 6.1. Publish và chờ xác nhận

Với `CachingConnectionFactory.ConfirmType.CORRELATED`, `setPublisherReturns(true)` và `RabbitTemplate.setMandatory(true)` đã được cấu hình, có thể sử dụng `CorrelationData`:

```java
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.amqp.rabbit.connection.CorrelationData;

CorrelationData correlation =
        new CorrelationData(UUID.randomUUID().toString());

ordersTemplate.convertAndSend(
        "orders.events", "orders.created", "ORDER-100", correlation);

CorrelationData.Confirm confirm =
        correlation.getFuture().get(10, TimeUnit.SECONDS);

if (!confirm.isAck()) {
    throw new IllegalStateException(
            "Broker A từ chối publish: " + confirm.getReason());
}

if (correlation.getReturn() != null) {
    throw new IllegalStateException(
            "Broker A nhận publish nhưng không định tuyến tới queue");
}
```

Với Spring AMQP 3.x, correlated publisher returns có thể được gắn vào `CorrelationData` trước khi future confirm hoàn tất. `confirm.isAck()` báo rằng broker đã xác nhận publish theo cơ chế confirms; **không bảo đảm** consumer đã xử lý nghiệp vụ, và một ACK có thể xuất hiện cả khi message không có route.

**Timeout không đồng nghĩa broker chưa nhận message.** Nếu retry, giữ `messageId`/business ID ổn định và thiết kế consumer idempotent. Đối với broker Audit, phải kiểm tra confirm/return trên **`auditTemplate`** riêng.

### 6.2. ACK/NACK của listener và dead-letter

Với `AcknowledgeMode.AUTO`:

- Listener hoàn tất bình thường: container ACK delivery của broker gắn với factory đó.
- Listener ném lỗi: container áp dụng reject/requeue theo chính sách; trong ví dụ `defaultRequeueRejected(false)` nên broker có thể chuyển message tới DLX riêng nếu topology đúng.
- Lỗi tạm thời: nên có retry hữu hạn/backoff; không đưa mọi exception vào DLQ ngay và không bật requeue vô hạn.
- Mất connection ngay trước ACK: message có thể được redeliver, phải chống xử lý trùng ở service/DB.

Các cặp DLX được tách biệt: `orders.dlx` trên A và `audit.dlx` trên B. Không có cơ chế mặc định nào chuyển dead-letter từ A sang B.

### 6.3. Không có distributed AMQP transaction giữa hai factory

Giả sử một listener ở A chuyển message sang B:

```java
@RabbitListener(
        queues = "orders.created.work",
        containerFactory = "ordersListenerFactory")
public void forwardToAudit(String orderId) {
    auditTemplate.convertAndSend(
            "audit.events", "audit.recorded", "Created " + orderId);
}
```

Sau lời gọi publish B, listener A trở về và container ACK A. Đây là **hai thao tác trên hai broker độc lập**, không phải một giao dịch nguyên tử:

| Điểm lỗi | Điều có thể xảy ra |
|---|---|
| B nhận event nhưng A không ACK thành công | A redeliver; B có thể nhận duplicate |
| A ACK khi B chưa thực sự nhận/bảo đảm routing | B có thể thiếu audit event |
| B down nhưng A vẫn hoạt động | Bridge phải retry hoặc lưu ý định gửi; không có tự động đồng bộ |
| Cùng bật `channelTransacted=true` ở A và B | Vẫn là hai local AMQP transactions, không tự hợp thành XA |

Để cải thiện, có thể chờ confirm/return ở B trước khi ACK A, đồng thời giữ event ID/idempotency. Với tính nhất quán nghiệp vụ cao, dùng **transactional outbox/relay** để lưu ý định chuyển tiếp bền vững và retry; hoặc đánh giá cơ chế Shovel/Federation theo mục tiêu hạ tầng. Khi bridge A→B, phải phân biệt broker B đã nhận message với service B đã ACK và nghiệp vụ B đã commit.

## 7. Định tuyến động bằng SimpleRoutingConnectionFactory

Nếu ứng dụng có rất nhiều broker có hợp đồng tương đương và cần chọn đích lúc chạy, Spring AMQP hỗ trợ `SimpleRoutingConnectionFactory` và `ConnectionFactoryContextWrapper`:

```java
@Bean
SimpleRoutingConnectionFactory routingConnectionFactory(
        @Qualifier("ordersConnectionFactory") ConnectionFactory orders,
        @Qualifier("auditConnectionFactory") ConnectionFactory audit) {
    SimpleRoutingConnectionFactory routing =
            new SimpleRoutingConnectionFactory();
    routing.setDefaultTargetConnectionFactory(orders);
    routing.setTargetConnectionFactories(
            Map.of("orders", orders, "audit", audit));
    return routing;
}

@Bean("routedTemplate")
RabbitTemplate routedTemplate(SimpleRoutingConnectionFactory routing) {
    return new RabbitTemplate(routing);
}

@Bean
ConnectionFactoryContextWrapper routingContext(
        SimpleRoutingConnectionFactory routing) {
    return new ConnectionFactoryContextWrapper(routing);
}
```

Các import liên quan: `java.util.Map`, `org.springframework.amqp.rabbit.connection.ConnectionFactory`, `org.springframework.amqp.rabbit.connection.SimpleRoutingConnectionFactory`, `org.springframework.amqp.rabbit.connection.ConnectionFactoryContextWrapper` và `org.springframework.amqp.rabbit.core.RabbitTemplate`.

Khi cần gửi:

```java
routingContext.run("orders", () ->
        routedTemplate.convertAndSend(
                "orders.events", "orders.created", "ORDER-200"));

routingContext.run("audit", () ->
        routedTemplate.convertAndSend(
                "audit.events", "audit.recorded", "ORDER-200 created"));
```

`routingContext.run("audit", ...)` chọn **connection factory/broker B**. Sau đó routing key `audit.recorded` mới được broker B sử dụng để quyết định binding. Đây là **hai cấp định tuyến khác nhau**.

Context routing có liên quan đến luồng thực thi: không mặc định được mang qua `@Async`, task executor hoặc completion chạy trên thread khác. Nếu dùng template dynamic, phải bảo đảm context được đặt đúng scope mỗi lần publish, default target được chọn có chủ đích, và số liệu được gắn theo đích. Với hai broker cố định trong ví dụ, **hai RabbitTemplate dùng `@Qualifier`** là lựa chọn dễ đọc và kiểm thử hơn.

## 8. Những lỗi thực tế và cách nhận biết

| Lỗi cấu hình | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Tạo hai `ConnectionFactory` nhưng chỉ một listener factory | Listener chạy tại broker không mong muốn | Gắn `containerFactory` rõ ràng cho mỗi `@RabbitListener` |
| Quên `@Qualifier` khi inject `RabbitTemplate` | `NoUniqueBeanDefinitionException` hoặc bị chọn template mặc định | Đặt tên bean và qualifier nhất quán |
| Nhầm broker/vhost ở một factory | Queue không tồn tại, sai quyền hoặc publish tới namespace khác | Kiểm tra host/vhost/tài khoản ở từng factory |
| Quên scope `RabbitAdmin` | Topology A/B xuất hiện ở cả hai broker hoặc lỗi permission | `explicitDeclarationsOnly=true` và `setAdminsThatShouldDeclare` |
| Admin khai báo ở A, template gửi B | B báo exchange không tồn tại, channel có thể đóng | Kiểm tra tam giác admin–template–listener cùng factory |
| Dùng `queues` nhưng không tạo queue | Container không tìm được queue | Khai báo bằng `Declarables` hoặc annotation declaration |
| Bật confirm nhưng không xem publisher return | Message unroutable vẫn bị đánh dấu đã gửi | Bật `mandatory`, kiểm tra returns theo CorrelationData |
| Trùng tên queue ở A/B | Log khó phân biệt consumer đang đọc nơi nào | Gắn tên logical broker, vhost, queue vào structured log |
| B down nhưng A up | Chỉ audit lỗi, orders vẫn có thể chạy | Health/alert riêng theo broker và retry/outbox |
| Retry/ACK không nhất quán khi bridge A→B | Message thiếu hoặc trùng | Chờ confirm B, giữ event ID, idempotent consumer |
| Nhiều queue/consumer cạnh tranh | Prefetch/unacked cao, backlog tăng | Đo số consumer, channel cache và tải từng broker |
| Thay đổi cấu hình TLS/password | Reconnect thất bại ở một factory | Theo dõi lỗi xác thực, certificate, rotation secret |

**Không log password, URI có mật khẩu hoặc payload nhạy cảm.** Để debug, ưu tiên log tên broker logic, vhost, exchange, queue, event ID/correlation ID và exception gọn; tránh thêm event ID thành nhãn metrics có cardinality cao.

## 9. Bảo mật và vận hành hai bộ kết nối

### 9.1. Tài khoản và quyền truy cập

Mỗi RabbitMQ service account nên có quyền tối thiểu theo vhost. Publisher cần quyền publish tới exchange phù hợp; consumer cần quyền đọc queue; admin cần quyền configure khi ứng dụng thực sự auto-declare topology. Nếu tổ chức tạo topology qua IaC hoặc operator có sẵn, có thể tách quyền khai báo khỏi tài khoản runtime và điều chỉnh `RabbitAdmin`/auto-declaration cho phù hợp.

Ở production nên kết nối TLS với xác minh máy chủ, dùng secret manager để xoay credential, và đặt timeout/reconnect policy hợp lý cho từng broker. Không tạo một connection factory duy nhất để “tiết kiệm kết nối” khi hai broker có ranh giới bảo mật khác nhau.

### 9.2. Health và metrics theo từng broker

| Chỉ số | Ý nghĩa |
|---|---|
| Connection available/reconnect count A/B | Phát hiện broker/vhost cụ thể đang lỗi |
| Số active listener containers A/B | Kiểm tra consumer có đang chạy đúng đích |
| Messages ready/unacknowledged trên từng queue | Tắc nghẽn và số delivery chưa ACK |
| Publish ACK/NACK và returns A/B | Broker nào xác nhận publish thất bại hoặc không route |
| DLQ depth và retry attempts A/B | Lỗi nghiệp vụ, poison message hoặc hạ tầng |
| Publisher confirm latency | Broker/network chậm; điều chỉnh timeout theo đích |
| Channel count/cache hit/miss | Kích thước tài nguyên mỗi connection factory |
| Backlog bridge/outbox A→B | Độ trễ và độ tin cậy khi chuyển tiếp giữa hai broker |

RabbitMQ Management UI hoặc Prometheus exporter phản ánh số liệu **ở broker**; Micrometer/Actuator và logs của Spring phản ánh **ở application**. Cần gắn nhãn broker logic trong metrics/logs để phân biệt, nhưng tránh ghi dữ liệu có cardinality cao vào nhãn.

### 9.3. Startup và shutdown

Một broker không khả dụng khi startup có thể làm listener liên quan liên tục reconnect hoặc gặp lỗi tùy thiết lập container. Hãy xác định nghiệp vụ nào bắt buộc cả hai broker sẵn sàng, nghiệp vụ nào vẫn có thể chạy khi một miền lỗi. Readiness check không nên đánh đồng “Orders broker down” với “Audit broker down” nếu ý nghĩa vận hành khác nhau.

Khi shutdown, cần dừng nhận message mới, xử lý những delivery đang chạy, chờ publish còn outstanding confirm theo thời hạn vận hành, và đóng các factory đúng vòng đời Spring. Với bridge, shutdown giữa publish B và ACK A là một ca quan trọng để kiểm thử duplicate.

## 10. Thực hành kiểm chứng có hai broker

Chuẩn bị hai RabbitMQ độc lập (hoặc hai vhost tách biệt để mô phỏng), có tài khoản và quyền phù hợp. Chạy ứng dụng Spring Boot với cấu hình trên, mở RabbitMQ Management UI cho từng nơi.

### Bài 1 — Kiểm tra topology

Trên A tìm `orders.events`, `orders.created.work`, `orders.dlx`, `orders.created.dead`. Trên B tìm `audit.events`, `audit.log.work`, `audit.dlx`, `audit.log.dead`. Xác nhận không có exchange/queue của bên kia trừ khi đã được khai báo bởi một hệ thống khác có chủ đích.

### Bài 2 — Gửi và nhận độc lập

Gọi `publisher.orderCreated("ORDER-101")` và `publisher.auditRecorded("Created ORDER-101")`. Orders listener phải đọc từ A; Audit listener phải đọc từ B. Đối chiếu queue counters tại từng broker và log có broker alias.

### Bài 3 — Chọn sai listener factory

Trong môi trường test, tạm gắn `orders.created.work` vào `auditListenerFactory`. Quan sát queue không tồn tại tại B (hoặc không tiêu thụ đúng). Khôi phục factory đúng và xác nhận message từ broker A được nhận.

### Bài 4 — Tắt broker Audit

Tạm dừng B, thử publish Audit và kiểm tra timeout/lỗi/confirm không chắc chắn. Trong lúc đó, luồng Orders của A vẫn có thể hoạt động. Sau khi B trở lại, kiểm tra reconnect, backlog và chính sách retry/outbox.

### Bài 5 — Thử routing không có binding

Publish vào `audit.events` với routing key sai. Với `mandatory=true` và returns được cấu hình, ứng dụng phải phát hiện unroutable; không đánh dấu gửi thành công chỉ dựa trên publisher confirm ACK.

### Bài 6 — Dead-letter riêng biệt

Cho orders listener ném exception; xác nhận message vào `orders.created.dead` trên A. Cho audit listener ném exception; xác nhận message vào `audit.log.dead` trên B. Kiểm tra `x-death` tại từng DLQ và xác nhận không chuyển chéo broker.

### Bài 7 — Bridge và duplicate

Tạo listener A chuyển message sang B với publisher confirm. Giả lập B nhận thành công nhưng mất ACK tại A. A có thể redeliver; xác nhận consumer đích dùng business/event ID không tạo tác dụng phụ lần hai.

### Bài 8 — Kiểm tra qualifier và quan sát

Thử bỏ `@Qualifier` ở injection có hai `RabbitTemplate`, quan sát Spring không xác định được bean phù hợp khi không có `@Primary`. Sửa bằng qualifier, sau đó kiểm tra metrics/logs phân biệt A và B.

**Tiêu chí đạt:** Mỗi template, listener và admin đều chọn đúng broker/vhost; lỗi một broker không tự làm message xuất hiện ở broker kia; đường publish có confirms/returns; ACK/NACK/DLQ chính xác; bridge có chiến lược retry/idempotency.

## 11. Câu hỏi tự kiểm tra

1. Vai trò của `ConnectionFactory`, `RabbitTemplate`, `RabbitListenerContainerFactory` và `RabbitAdmin` khác nhau thế nào?
2. Tại sao `CachingConnectionFactory.setAddresses` chứa hai host không thay cho việc publish vào hai RabbitMQ độc lập?
3. Nếu `ordersTemplate` gửi A nhưng `ordersListenerFactory` trỏ B, consumer sẽ nhận ở đâu?
4. Nếu cả hai `RabbitAdmin` mặc định khai báo mọi `Declarable`, hệ thống có thể gặp rủi ro gì?
5. `@RabbitListener(queues="...")` khác `queuesToDeclare` về cơ chế tạo queue ra sao?
6. Vì sao `@Primary` không đủ để bảo đảm đúng broker trong hệ thống nhiều template?
7. Publisher confirm ACK có chứng minh message đã vào một queue phù hợp không?
8. Khi bridge A→B, điều gì xảy ra nếu B đã nhận message nhưng ACK A thất bại?
9. `SimpleRoutingConnectionFactory` chọn broker hay chọn binding trong một broker?
10. Những metric nào nên gắn theo broker logic?

**Đáp án gợi ý:** (1) quản lý connection, publish, container nhận, khai báo topology; (2) danh sách endpoint chỉ hỗ trợ kết nối, không fan-out; (3) B; (4) khai báo chéo/sai quyền; (5) `queues` tham chiếu queue có sẵn, `queuesToDeclare` tạo declaration; (6) chỉ chọn bean mặc định; (7) không, cần kiểm tra return; (8) A có thể redeliver khiến B nhận trùng; (9) broker/factory, không phải exchange binding; (10) connection, confirms/returns, ready/unacked, retry, DLQ, consumer, latency.

## 12. Tổng kết

Khi ứng dụng Spring AMQP cần giao tiếp với nhiều RabbitMQ broker hoặc vhost, hãy khai báo **mỗi đích một `ConnectionFactory`**, sau đó gắn đúng `RabbitTemplate`, `RabbitListenerContainerFactory` và `RabbitAdmin`. Dùng `@Qualifier` và `@RabbitListener(containerFactory=...)` để đường gửi/nhận được chọn rõ ràng; giới hạn `RabbitAdmin` bằng `explicitDeclarationsOnly` và `adminsThatShouldDeclare` để không khai báo sai broker.

Một broker có thể lỗi trong khi broker kia vẫn hoạt động. Các cơ chế publisher confirms/returns, ACK/NACK, retry/DLX và giám sát phải được đánh giá **theo từng broker**. Khi cần chuyển event qua hai broker, không thể dựa vào transaction AMQP cục bộ để có exactly-once; cần event ID bền vững, idempotency và, khi phù hợp, transactional outbox/relay.

### Tài liệu tham khảo

- [Spring AMQP — Multiple Broker (or Cluster) Support](https://docs.spring.io/spring-amqp/reference/3.2/amqp/multi-rabbit.html): nhiều connection factories, listener factories, quy ước RabbitAdmin và routing connection.
- [Spring AMQP — Configuring the Broker](https://docs.spring.io/spring-amqp/reference/amqp/broker-configuration.html): conditional declarations, `explicitDeclarationsOnly`, `adminsThatShouldDeclare`.
- [Spring AMQP — Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): `CachingConnectionFactory` và connection/channel cache.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): tự động cấu hình RabbitMQ, `@RabbitListener` và listener container factories.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): confirm, return, acknowledgment và ranh giới độ tin cậy.

