# Định tuyến gửi/nhận và tài nguyên tương ứng trên từng broker

Khi một ứng dụng Spring AMQP làm việc với một RabbitMQ broker, người lập trình thường chỉ quan tâm **exchange**, **routing key**, **queue** và **binding**. Tuy nhiên, nếu ứng dụng kết nối **nhiều broker độc lập**, một quyết định còn quan trọng hơn phải được thực hiện trước: *message này được gửi tới broker và virtual host nào?*

Ví dụ, Order Service gửi sự kiện `OrderChanged` tới broker A, còn Billing Service gửi lệnh `GenerateInvoice` tới broker B. Nếu dùng nhầm `RabbitTemplate` trỏ vào broker A để publish `GenerateInvoice`, việc ghi đúng tên exchange `billing.commands` và routing key `invoice.generate` **không khiến RabbitMQ tự chuyển message sang broker B**. Cùng tên exchange trên các broker khác nhau là các tài nguyên độc lập.

Bài học thuộc chương **Nhiều broker và khách hàng** của module **SPRING_AMQP**. Ta sẽ cấu hình nhiều `ConnectionFactory`, `RabbitTemplate`, `@RabbitListener`, `RabbitAdmin`, exchange–queue–binding, rồi phân tích xác nhận publish, ACK, retry, dead-letter, giao dịch chuyển tiếp và giám sát để xử lý bất đồng bộ đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **hai broker độc lập**, **nhiều node cùng RabbitMQ cluster** và **nhiều virtual host**.
2. Giải thích hai bước định tuyến: **chọn broker bằng connection factory** rồi **chọn queue bằng exchange, routing key và binding** trên broker đó.
3. Khai báo hai `CachingConnectionFactory` và hai `RabbitTemplate`, tiêm đúng bean bằng `@Qualifier`.
4. Khai báo hai listener container factory và chỉ định rõ `containerFactory` trong `@RabbitListener`.
5. Phân quyền khai báo `Queue`, `Exchange`, `Binding` cho đúng `RabbitAdmin` để không tạo nhầm tài nguyên trên broker khác.
6. Phân tách publisher confirms/returns, consumer ACK, retry, DLX/DLQ và phục hồi kết nối theo từng broker.
7. Nhận diện cửa sổ mất message/trùng khi ứng dụng chuyển tiếp dữ liệu từ broker A sang broker B.
8. Xây kịch bản kiểm thử gửi/nhận, định tuyến sai, broker down, recovery và replay an toàn.

## 2. “Nhiều broker” có thể có nghĩa khác nhau

| Mô hình | Phạm vi tài nguyên | Kết nối phù hợp |
| --- | --- | --- |
| **Một cluster nhiều node** | Exchange, queue, binding và virtual host thuộc một cluster logic; cách lưu và leader queue tùy loại queue | Thường **một connection factory** với nhiều địa chỉ node hoặc endpoint cluster |
| **Hai cluster/broker độc lập** | Hai hệ thống có exchange, queue, binding, vhost và vòng đời dữ liệu riêng | **Hai connection factory**, template và listener tương ứng |
| **Hai virtual host trên cùng broker/cluster** | Mỗi virtual host có namespace exchange/queue/binding độc lập | Thường cần connection factory riêng cho từng virtual host |
| **Hai broker có Shovel/Federation** | Vẫn tách biệt; có luồng chuyển message được cấu hình có chủ đích | Cần thiết kế rõ nơi publish, nơi tiêu thụ và cơ chế chuyển tiếp |

**Danh sách nhiều host trong cùng connection factory không đồng nghĩa gửi tới nhiều broker nghiệp vụ.** Danh sách host thường được dùng để kết nối/failover trong cùng một cluster. Nếu muốn Order và Billing có các miền tài nguyên độc lập, định tuyến bằng **bean connection factory riêng**, không dựa vào cơ chế đổi node của một connection.

Giả sử môi trường ví dụ:

| Luồng | RabbitMQ endpoint | Virtual host |
| --- | --- | --- |
| Order | `rabbit-orders.internal:5672` | `/orders` |
| Billing | `rabbit-billing.internal:5672` | `/billing` |

Tên host và vhost chỉ là minh họa. Một queue tên `orders.queue` trên broker A là **một queue khác** với queue cùng tên trên broker B.

## 3. Hai tầng định tuyến của message

~~~mermaid
flowchart TD
    APP["Spring Boot ứng dụng"]
    APP --> OT["ordersRabbitTemplate"]
    APP --> BT["billingRabbitTemplate"]
    subgraph O["Broker Order — /orders"]
      OE["orders.events exchange"] -->|"order.changed"| OQ["orders.events.queue"]
    end
    subgraph B["Broker Billing — /billing"]
      BE["billing.commands exchange"] -->|"invoice.generate"| BQ["billing.invoice.queue"]
    end
    OT -->|"ordersConnectionFactory"| OE
    BT -->|"billingConnectionFactory"| BE
    OQ -->|"ordersListenerFactory"| OL["@RabbitListener Order"]
    BQ -->|"billingListenerFactory"| BL["@RabbitListener Billing"]
~~~

Luồng publish có **hai tầng**:

1. **Ứng dụng chọn broker**: `RabbitTemplate` sử dụng `ConnectionFactory` nào thì publish đi qua broker/vhost mà connection đó mở.
2. **Broker chọn queue**: trên broker đã chọn, exchange xử lý routing key và binding để quyết định queue đích.

Nếu gọi:

~~~java
ordersTemplate.convertAndSend(
        "orders.events", "order.changed", event);
~~~

thì RabbitMQ sử dụng **exchange `orders.events` trên broker Order**.

Nếu gọi:

~~~java
billingTemplate.convertAndSend(
        "billing.commands", "invoice.generate", command);
~~~

thì RabbitMQ sử dụng **exchange `billing.commands` trên broker Billing**.

**Không có routing key toàn cục.** `"billing.commands"` không chứa địa chỉ broker, và `@RabbitListener(queues="billing.invoice.queue")` cũng không tự tìm broker đúng bằng tên queue.

## 4. Thiết kế bean theo broker

Đặt tên bean tường minh để ngăn cấu hình bị lẫn:

| Vai trò | Order | Billing |
| --- | --- | --- |
| Connection | `ordersConnectionFactory` | `billingConnectionFactory` |
| Publish | `ordersRabbitTemplate` | `billingRabbitTemplate` |
| Listener factory | `ordersListenerFactory` | `billingListenerFactory` |
| Khai báo topology | `ordersRabbitAdmin` | `billingRabbitAdmin` |
| Exchange chính | `orders.events` | `billing.commands` |
| Work queue | `orders.events.queue` | `billing.invoice.queue` |
| Binding key | `order.changed` | `invoice.generate` |

Ví dụ dưới đây dành cho Spring Boot 3.x và Spring AMQP 3.x, có dependency `spring-boot-starter-amqp`. Tùy phiên bản, cần kiểm tra API JSON converter và các option hỗ trợ. Các đoạn mã được đặt trong package giả định `com.example.multibroker`. Với nhiều connection factory do ứng dụng tự tạo, không được mặc định rằng toàn bộ property `spring.rabbitmq.*` sẽ được tự áp dụng cho cả hai.

### 4.1. Khai báo cấu hình ngoài mã nguồn

~~~yaml
app:
  rabbit:
    orders:
      host: rabbit-orders.internal
      port: 5672
      virtual-host: /orders
      username: ${ORDERS_RABBIT_USERNAME}
      password: ${ORDERS_RABBIT_PASSWORD}
    billing:
      host: rabbit-billing.internal
      port: 5672
      virtual-host: /billing
      username: ${BILLING_RABBIT_USERNAME}
      password: ${BILLING_RABBIT_PASSWORD}
~~~

`app.rabbit.*` là namespace **tự định nghĩa**. Spring Boot không tự tạo hai connection factory chỉ vì YAML có hai nhánh. Mã ở dưới sẽ nhận các giá trị này qua `@Value`. Trong production, credential nên nằm trong secret manager hoặc biến môi trường; từng broker cần phân quyền và TLS riêng nếu hệ thống yêu cầu.

### 4.2. Tạo hai `CachingConnectionFactory`

~~~java
package com.example.multibroker;

import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration
public class MultipleRabbitConnections {

    private static CachingConnectionFactory create(
            String host, int port, String vhost,
            String user, String password) {

        var factory = new CachingConnectionFactory(host, port);
        factory.setVirtualHost(vhost);
        factory.setUsername(user);
        factory.setPassword(password);

        // Kết quả publish được theo dõi riêng trên từng broker.
        factory.setPublisherConfirmType(
                CachingConnectionFactory.ConfirmType.CORRELATED);
        factory.setPublisherReturns(true);

        // Các tham số bên dưới thuộc RabbitMQ Java client.
        factory.getRabbitConnectionFactory().setRequestedHeartbeat(30);
        factory.getRabbitConnectionFactory().setConnectionTimeout(5_000);
        return factory;
    }

    @Bean("ordersConnectionFactory")
    @Primary
    CachingConnectionFactory ordersConnectionFactory(
            @Value("${app.rabbit.orders.host}") String host,
            @Value("${app.rabbit.orders.port}") int port,
            @Value("${app.rabbit.orders.virtual-host}") String vhost,
            @Value("${app.rabbit.orders.username}") String user,
            @Value("${app.rabbit.orders.password}") String password) {
        return create(host, port, vhost, user, password);
    }

    @Bean("billingConnectionFactory")
    CachingConnectionFactory billingConnectionFactory(
            @Value("${app.rabbit.billing.host}") String host,
            @Value("${app.rabbit.billing.port}") int port,
            @Value("${app.rabbit.billing.virtual-host}") String vhost,
            @Value("${app.rabbit.billing.username}") String user,
            @Value("${app.rabbit.billing.password}") String password) {
        return create(host, port, vhost, user, password);
    }
}
~~~

`@Primary` chỉ là quy tắc chọn bean mặc định khi một điểm tiêm cần một `ConnectionFactory` duy nhất. **Nó không thay thế định tuyến nghiệp vụ.** Các nơi publish, consume và khai báo tài nguyên phải chọn connection đúng bằng tên.

Nếu hai broker có heartbeat, TLS, cache, authentication hoặc network khác nhau, cần cấu hình mỗi factory theo profile riêng. Heartbeat chỉ hỗ trợ phát hiện kết nối chết; nó không bảo đảm mọi publish đang chờ được phát lại tự động và an toàn.

## 5. `RabbitTemplate` gửi đúng broker

Một `RabbitTemplate` làm việc với một connection factory cụ thể. Mỗi luồng nên có template được đặt tên và cấu hình converter độc lập hoặc dùng chung converter nếu định dạng message tương thích.

~~~java
package com.example.multibroker;

import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MultipleRabbitTemplates {

    @Bean
    Jackson2JsonMessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean("ordersRabbitTemplate")
    RabbitTemplate ordersRabbitTemplate(
            @Qualifier("ordersConnectionFactory") ConnectionFactory factory,
            Jackson2JsonMessageConverter converter) {
        var template = new RabbitTemplate(factory);
        template.setMessageConverter(converter);
        template.setMandatory(true);
        return template;
    }

    @Bean("billingRabbitTemplate")
    RabbitTemplate billingRabbitTemplate(
            @Qualifier("billingConnectionFactory") ConnectionFactory factory,
            Jackson2JsonMessageConverter converter) {
        var template = new RabbitTemplate(factory);
        template.setMessageConverter(converter);
        template.setMandatory(true);
        return template;
    }
}
~~~

`setMandatory(true)` cho phép broker trả về publish không route được trong các điều kiện áp dụng; nó cần đi cùng publisher returns nếu ứng dụng muốn nhận và xử lý sự kiện return. Publisher confirms/returns đã được bật trên hai connection factory ở mục 4.

### 5.1. Producer tiêm đúng template bằng `@Qualifier`

~~~java
package com.example.multibroker;

import java.util.UUID;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class MultiBrokerPublisher {

    private final RabbitTemplate ordersTemplate;
    private final RabbitTemplate billingTemplate;

    public MultiBrokerPublisher(
            @Qualifier("ordersRabbitTemplate") RabbitTemplate ordersTemplate,
            @Qualifier("billingRabbitTemplate") RabbitTemplate billingTemplate) {
        this.ordersTemplate = ordersTemplate;
        this.billingTemplate = billingTemplate;
    }

    public void orderChanged(OrderChanged event) {
        ordersTemplate.convertAndSend(
                "orders.events", "order.changed", event);
    }

    public void generateInvoice(GenerateInvoice command) {
        billingTemplate.convertAndSend(
                "billing.commands", "invoice.generate", command);
    }

    public record OrderChanged(
            UUID eventId, String orderId, long version) {}

    public record GenerateInvoice(
            UUID commandId, String orderId) {}
}
~~~

Hai message là hai DTO có **định danh ổn định**. Mỗi lần tạo một sự kiện mới có thể sinh UUID mới, nhưng nếu retry **cùng sự kiện** sau timeout thì phải phát lại với `eventId`/`commandId` ban đầu. Khi cần bảo đảm không mất event sau DB commit, nên lưu message trong transactional outbox rồi relay publish.

### 5.2. Điều gì xảy ra khi dùng nhầm template?

~~~java
// SAI: dùng connection broker Order để publish lệnh Billing.
ordersTemplate.convertAndSend(
        "billing.commands", "invoice.generate", command);
~~~

Trên **broker Order**, có thể xảy ra:

- Không có exchange `billing.commands`: broker trả lỗi publish vào exchange không tồn tại và có thể đóng channel.
- Có exchange nhưng không có binding `invoice.generate`: message không tới queue nào; với mandatory/returns được cấu hình, ứng dụng có thể thấy returned message.
- Có exchange và binding **trùng tên**: message đi vào **queue trên broker Order**, khiến hệ thống khó phát hiện hơn.

Trong cả ba trường hợp, tên exchange `billing.commands` không làm message tự nhảy sang broker Billing. Do đó nên đo kết quả **trên broker/vhost đích**, không chỉ dựa vào việc `convertAndSend()` trả về không có exception.

## 6. `@RabbitListener` nhận đúng broker

Annotation:

~~~java
@RabbitListener(queues = "orders.events.queue")
~~~

chỉ định queue **theo tên**, không chứa host hay virtual host. Nếu ứng dụng dùng hai connection factory, listener cần một container factory xác định rõ broker. Không nên dựa vào factory mặc định tên `rabbitListenerContainerFactory` để tự suy ra từ tên queue.

### 6.1. Khai báo hai container factory

~~~java
package com.example.multibroker;

import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MultipleRabbitListeners {

    private static SimpleRabbitListenerContainerFactory create(
            ConnectionFactory factory,
            Jackson2JsonMessageConverter converter) {

        var listenerFactory = new SimpleRabbitListenerContainerFactory();
        listenerFactory.setConnectionFactory(factory);
        listenerFactory.setMessageConverter(converter);
        listenerFactory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        listenerFactory.setPrefetchCount(20);
        listenerFactory.setConcurrentConsumers(1);
        listenerFactory.setMaxConcurrentConsumers(3);
        return listenerFactory;
    }

    @Bean("ordersListenerFactory")
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            @Qualifier("ordersConnectionFactory") ConnectionFactory factory,
            Jackson2JsonMessageConverter converter) {
        return create(factory, converter);
    }

    @Bean("billingListenerFactory")
    SimpleRabbitListenerContainerFactory billingListenerFactory(
            @Qualifier("billingConnectionFactory") ConnectionFactory factory,
            Jackson2JsonMessageConverter converter) {
        return create(factory, converter);
    }
}
~~~

Bộ cấu hình trên có `AcknowledgeMode.AUTO`, nghĩa là **Spring listener container** ACK sau khi xử lý thành công theo cơ chế của container. Đây không phải broker auto-ack vô điều kiện. Trong production, hai factory có thể cần prefetch, concurrency, retry advice, error handler và giới hạn khác nhau.

### 6.2. Listener gắn rõ `containerFactory`

~~~java
package com.example.multibroker;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class MultiBrokerConsumers {

    private final OrdersService ordersService;
    private final BillingService billingService;

    public MultiBrokerConsumers(
            OrdersService ordersService,
            BillingService billingService) {
        this.ordersService = ordersService;
        this.billingService = billingService;
    }

    @RabbitListener(
            queues = "orders.events.queue",
            containerFactory = "ordersListenerFactory")
    public void onOrderChanged(MultiBrokerPublisher.OrderChanged event) {
        ordersService.applyIdempotently(event);
    }

    @RabbitListener(
            queues = "billing.invoice.queue",
            containerFactory = "billingListenerFactory")
    public void onGenerateInvoice(
            MultiBrokerPublisher.GenerateInvoice command) {
        billingService.generateIdempotently(command);
    }
}
~~~

`OrdersService` và `BillingService` ở đây là các service nghiệp vụ cần triển khai. Với cơ chế AUTO ACK, listener nên **chờ** nghiệp vụ commit rồi mới return. Nếu nó chỉ gửi công việc vào thread pool và return ngay, container có thể ACK trước khi side effect hoàn tất.

**ACK và commit không nguyên tử xuyên RabbitMQ và database**. Nếu DB đã commit nhưng ACK chưa tới broker, message có thể được giao lại sau reconnect; cần idempotency theo `eventId`/`commandId`.

## 7. `RabbitAdmin`: quản lý topology tương ứng từng broker

Tạo đúng hai template/listener vẫn chưa đủ. Trong Spring AMQP, các bean `Queue`, `Exchange`, `Binding` mô tả topology nhưng **không tự chứa broker address**. `RabbitAdmin` mới sử dụng một connection factory để khai báo tài nguyên thực tế.

Khi Spring context có **hai `RabbitAdmin`**, nếu cả hai cùng tự khai báo tất cả `Declarable` mà không lọc, topology Order có thể bị khai báo nhầm trên Billing và ngược lại. Ngay cả khi tên tài nguyên khác nhau, điều này gây lãng phí, rủi ro quyền hoặc lỗi khai báo.

### 7.1. Dùng hai admin với explicit declarations

~~~java
package com.example.multibroker;

import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MultipleRabbitAdmins {

    @Bean("ordersRabbitAdmin")
    RabbitAdmin ordersRabbitAdmin(
            @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
        var admin = new RabbitAdmin(factory);
        admin.setExplicitDeclarationsOnly(true);
        return admin;
    }

    @Bean("billingRabbitAdmin")
    RabbitAdmin billingRabbitAdmin(
            @Qualifier("billingConnectionFactory") ConnectionFactory factory) {
        var admin = new RabbitAdmin(factory);
        admin.setExplicitDeclarationsOnly(true);
        return admin;
    }
}
~~~

`setExplicitDeclarationsOnly(true)` yêu cầu admin chỉ tự khai báo `Declarable` **được gắn rõ admin đó**. Điều này hữu ích khi một Spring context có nhiều connection factory và nhiều bộ tài nguyên.

### 7.2. Gắn từng `Exchange`, `Queue`, `Binding` vào admin chính xác

~~~java
package com.example.multibroker;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MultipleBrokerTopology {

    @Bean("ordersExchange")
    DirectExchange ordersExchange() {
        var exchange = new DirectExchange("orders.events", true, false);
        exchange.setAdminsThatShouldDeclare("ordersRabbitAdmin");
        return exchange;
    }

    @Bean("ordersQueue")
    Queue ordersQueue() {
        var queue = QueueBuilder.durable("orders.events.queue").build();
        queue.setAdminsThatShouldDeclare("ordersRabbitAdmin");
        return queue;
    }

    @Bean("ordersBinding")
    Binding ordersBinding(
            @Qualifier("ordersQueue") Queue queue,
            @Qualifier("ordersExchange") DirectExchange exchange) {
        var binding = BindingBuilder.bind(queue).to(exchange)
                .with("order.changed");
        binding.setAdminsThatShouldDeclare("ordersRabbitAdmin");
        return binding;
    }

    @Bean("billingExchange")
    DirectExchange billingExchange() {
        var exchange = new DirectExchange("billing.commands", true, false);
        exchange.setAdminsThatShouldDeclare("billingRabbitAdmin");
        return exchange;
    }

    @Bean("billingQueue")
    Queue billingQueue() {
        var queue = QueueBuilder.durable("billing.invoice.queue").build();
        queue.setAdminsThatShouldDeclare("billingRabbitAdmin");
        return queue;
    }

    @Bean("billingBinding")
    Binding billingBinding(
            @Qualifier("billingQueue") Queue queue,
            @Qualifier("billingExchange") DirectExchange exchange) {
        var binding = BindingBuilder.bind(queue).to(exchange)
                .with("invoice.generate");
        binding.setAdminsThatShouldDeclare("billingRabbitAdmin");
        return binding;
    }
}
~~~

Sau khi ứng dụng tạo kết nối và RabbitAdmin thực hiện khai báo:

| Broker | Exchange | Queue | Binding |
| --- | --- | --- | --- |
| Order | `orders.events` | `orders.events.queue` | `order.changed` |
| Billing | `billing.commands` | `billing.invoice.queue` | `invoice.generate` |

Không chỉ gắn admin cho queue mà quên binding. Một queue tồn tại nhưng không được bind đúng thì message vẫn không thể đi vào từ exchange nghiệp vụ.

### 7.3. Khi nào RabbitAdmin không thể “tự sửa” topology?

- Queue có cùng tên nhưng **arguments khác nhau** (ví dụ queue type, DLX, TTL) có thể làm broker báo `PRECONDITION_FAILED` khi redeclare.
- Exchange có cùng tên nhưng type khác sẽ xung đột.
- Permission của user có thể cho phép consume nhưng không cho declare.
- Tài nguyên tồn tại ở **vhost khác** vẫn không xuất hiện trong vhost của connection hiện tại.
- Khi broker mất dữ liệu/tài nguyên, việc declare lại queue **không phục hồi message cũ** đã mất.

Nếu topology được quản lý bởi Terraform/operator hoặc đội platform, có thể tắt auto-declare ở ứng dụng; dù vậy phải kiểm tra sự tồn tại của exchange, queue, binding trước khi publish/consume.

### 7.4. Khôi phục listener khi có nhiều admin

Listener container có thể sử dụng RabbitAdmin trong quá trình khôi phục/redeclare queue khi cần. Với **nhiều admin trong cùng Spring context**, nên cấu hình rõ admin tương ứng cho container khi sử dụng tính năng auto-declare, hoặc quản lý topology ngoài ứng dụng và vô hiệu hành vi khai báo của container theo thiết kế. Không mặc định container sẽ biết đúng admin chỉ từ tên queue.

Đây là lý do việc gắn declarable cho đúng admin và kiểm tra recovery sau broker restart đều quan trọng: *tài nguyên được khai báo ban đầu đúng* chưa chắc đã đủ nếu một đường redeclare khi phục hồi chọn sai broker.

## 8. DLX, retry và các tài nguyên lỗi trên từng broker

DLX hoạt động **bên trong RabbitMQ broker/vhost đang giữ message**. Khi một consumer Order reject với `requeue=false`, message có thể được dead-letter tới DLX trên **broker Order**; nó không tự tới queue DLQ của Billing.

Ví dụ bổ sung DLX cho Order:

~~~java
@Bean("ordersDlx")
DirectExchange ordersDlx() {
    var exchange = new DirectExchange("orders.dlx", true, false);
    exchange.setAdminsThatShouldDeclare("ordersRabbitAdmin");
    return exchange;
}

@Bean("ordersDlq")
Queue ordersDlq() {
    var queue = QueueBuilder.durable("orders.events.dlq").build();
    queue.setAdminsThatShouldDeclare("ordersRabbitAdmin");
    return queue;
}

@Bean("ordersDlqBinding")
Binding ordersDlqBinding(
        @Qualifier("ordersDlq") Queue queue,
        @Qualifier("ordersDlx") DirectExchange exchange) {
    var binding = BindingBuilder.bind(queue).to(exchange)
            .with("orders.failed");
    binding.setAdminsThatShouldDeclare("ordersRabbitAdmin");
    return binding;
}
~~~

Để queue nguồn thật sự dùng DLX, **thay phần thân** `ordersQueue()` ở mục 7 bằng:

~~~java
var queue = QueueBuilder.durable("orders.events.queue")
        .deadLetterExchange("orders.dlx")
        .deadLetterRoutingKey("orders.failed")
        .build();
queue.setAdminsThatShouldDeclare("ordersRabbitAdmin");
return queue;
~~~

**Không tạo thêm một queue bean cùng tên với arguments khác**. Đối với queue đã tồn tại, thay đổi DLX argument có thể yêu cầu migration hoặc RabbitMQ policy phù hợp. Broker Billing cần DLX và DLQ **riêng** nếu luồng Billing có yêu cầu xử lý lỗi tương tự.

| Chính sách | Order | Billing |
| --- | --- | --- |
| Lỗi tạm thời | Retry với backoff theo DB Order | Retry theo Billing API hoặc DB Billing |
| Poison message | `orders.events.dlq` | `billing.invoice.dlq` |
| ID replay | `eventId` | `commandId` |
| Monitor | DLQ Order, tuổi message | DLQ Billing, tuổi message |
| Điều tra | Tác động trạng thái đơn hàng | Nguy cơ xuất hóa đơn trùng |

Không để một poison message quay vòng mãi giữa queue retry và queue chính. Mỗi hệ thống cần **retry budget** và **terminal DLQ**. Việc replay từ DLQ phải giữ ID nghiệp vụ và kiểm tra idempotency.

## 9. Publisher confirms/returns theo broker

Publisher confirms và returns thuộc **connection/channel nơi publish**. Confirm ACK từ broker Order không nói gì về tình trạng broker Billing.

Ví dụ xác nhận publish command Billing:

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class ConfirmedBillingPublisher {

    private final RabbitTemplate billingTemplate;

    public ConfirmedBillingPublisher(
            @Qualifier("billingRabbitTemplate") RabbitTemplate billingTemplate) {
        this.billingTemplate = billingTemplate;
    }

    public void send(MultiBrokerPublisher.GenerateInvoice command)
            throws Exception {
        var correlation = new CorrelationData(
                command.commandId().toString());

        billingTemplate.convertAndSend(
                "billing.commands",
                "invoice.generate",
                command,
                message -> {
                    message.getMessageProperties().setMessageId(
                            command.commandId().toString());
                    return message;
                },
                correlation);

        var confirm = correlation.getFuture()
                .get(5, TimeUnit.SECONDS);

        if (!confirm.isAck()) {
            throw new IllegalStateException(
                    "Broker Billing NACK: " + confirm.getReason());
        }
        if (correlation.getReturned() != null) {
            throw new IllegalStateException(
                    "Billing command không route được");
        }
    }
}
~~~

Ví dụ này cần `ConfirmType.CORRELATED` trên `billingConnectionFactory`, publisher returns và `billingTemplate.setMandatory(true)` như các mục trước. Đây là cách minh họa trạng thái publish; trong hệ thống throughput cao có thể xử lý confirm bất đồng bộ.

**Không đánh đồng:**

- **Confirm ACK**: broker xác nhận xử lý publish theo khả năng và chính sách lưu trữ của broker.
- **Return**: message không route được trong các điều kiện mandatory áp dụng.
- **Consumer ACK**: consumer đã xác nhận delivery với broker.
- **Business commit**: side effect đã được lưu bền vững trong hệ thống nghiệp vụ.

Khi connection đứt sau publish nhưng trước khi caller nhận confirm, **kết quả không xác định**. Retry cùng message với ID ổn định là chiến lược an toàn hơn; consumer phải chặn duplicate effect.

### 9.1. Ma trận sự cố publish

| Triệu chứng | Khả năng | Cần kiểm tra |
| --- | --- | --- |
| Không kết nối được broker Billing | Host, port, TLS, vhost, credentials hoặc outage | `billingConnectionFactory`, logs kết nối |
| Publish lỗi exchange không tồn tại | Sai exchange hoặc RabbitAdmin chưa declare đúng broker | Topology Billing, channel exception |
| Confirm ACK nhưng có return | Exchange tồn tại nhưng binding không route được | Routing key, queue, mandatory |
| Confirm timeout | Broker/mạng gặp sự cố hoặc confirm thất lạc | Correlation, outbox, trạng thái unknown |
| Queue có message nhưng listener không nhận | Container factory dùng sai connection, consumer chưa active | `containerFactory`, broker/vhost |
| Message được nhận nhưng nghiệp vụ lỗi | JSON/schema/DB/service | Retry, consumer logs và DLQ |

## 10. Phục hồi kết nối: tách hai miền lỗi

Giả sử broker Billing bị ngắt kết nối, còn broker Order vẫn hoạt động. Hai connection factory cho phép duy trì hai tập connection/channel độc lập:

~~~mermaid
sequenceDiagram
    participant O as Orders RabbitTemplate
    participant B as Billing RabbitTemplate
    participant R1 as Broker Order
    participant R2 as Broker Billing

    O->>R1: Publish OrderChanged
    B--xR2: Publish GenerateInvoice (mất kết nối)
    O->>R1: Tiếp tục xử lý Order
    Note over B,R2: Billing retry/reconnect
    B->>R2: Kết nối lại
    B->>R2: Publish lại cùng commandId
~~~

Tách connection giúp lỗi transport của broker Billing **không trực tiếp đóng connection Order**. Tuy nhiên ứng dụng vẫn chung JVM, CPU, heap, executor và có thể chung database: reconnect storm ở Billing vẫn gây ảnh hưởng gián tiếp tới Order.

Vì thế cần đo riêng theo broker:

- Connection/channel count, heartbeat timeout, reconnect attempts, time to first delivery.
- Publisher confirm timeout/nack/return.
- Listener registered/active, số message ready/unacked, redelivery.
- DLQ size và tuổi message tồn đọng.
- Outbox pending age cho destination Billing hoặc Order.
- Processing latency và tỷ lệ lỗi nghiệp vụ.

Tránh một cờ `rabbitConnected=true` chung khi thực tế chỉ có một trong hai broker đang sẵn sàng. Với ứng dụng có HTTP endpoint, readiness cần phản ánh dependency của **luồng traffic cụ thể**; không nhất thiết restart toàn ứng dụng mỗi khi một broker có sự cố ngắn hạn.

## 11. Chuyển tiếp giữa broker A và broker B

Ứng dụng đôi khi đóng vai trò **bridge**:

1. Consume `OrderChanged` từ broker Order.
2. Chuyển thành `GenerateInvoice`.
3. Publish command tới broker Billing.
4. ACK delivery trên broker Order.

Thứ tự các bước trên chứa rủi ro vì ACK ở A và publish ở B **không thuộc một AMQP transaction nguyên tử xuyên hai broker**.

~~~mermaid
flowchart LR
  OA["Broker Order: orders.events.queue"] --> L["Bridge consumer"]
  L --> DB["Inbox + Billing outbox trong database"]
  DB --> R["Billing relay + publisher confirms"]
  R --> BB["Broker Billing: billing.invoice.queue"]
  BB --> BC["Billing consumer có dedup"]
~~~

Nếu bridge chỉ làm:

~~~java
@RabbitListener(
        queues = "orders.events.queue",
        containerFactory = "ordersListenerFactory")
public void bridge(MultiBrokerPublisher.OrderChanged event) {
    billingTemplate.convertAndSend(
            "billing.commands", "invoice.generate",
            convertToCommand(event));
}
~~~

thì cần phân tích:

| Cửa sổ | Rủi ro |
| --- | --- |
| ACK Order trước publish Billing | Publish thất bại → **mất lệnh Billing** |
| Publish Billing thành công, chưa ACK Order | Source redeliver → **publish command lần nữa** |
| Publish Billing timeout không có confirm | Không biết broker Billing đã nhận chưa |
| Billing consumer DB commit nhưng ACK chưa tới broker | Consumer có thể nhận lại và gây side effect trùng |
| Billing down lâu, bridge cứ requeue ngay ở Order | Retry liên tục, backlog và áp lực broker tăng |

### 11.1. Mẫu inbox + transactional outbox

Nếu bridge có database, có thể bảo đảm một bước trung gian bền vững:

1. Listener Order nhận event `E42` với `eventId` từ nguồn.
2. **Trong cùng DB transaction**, insert `bridge_inbox(E42)` (unique) và insert `billing_outbox(C42, sourceEventId=E42)`.
3. Sau DB commit, listener return để container ACK Order.
4. Relay lấy outbox, publish command `C42` sang broker Billing và đợi confirms/returns.
5. Khi xác nhận phù hợp, cập nhật outbox đã gửi. Timeout/connection lỗi thì giữ outbox để retry.
6. Consumer Billing xử lý **idempotent theo commandId C42**.

~~~sql
CREATE TABLE bridge_inbox (
    consumer_name   VARCHAR(80) NOT NULL,
    source_event_id UUID NOT NULL,
    received_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, source_event_id)
);

CREATE TABLE billing_outbox (
    command_id      UUID PRIMARY KEY,
    source_event_id UUID NOT NULL UNIQUE,
    payload         TEXT NOT NULL,
    state           VARCHAR(16) NOT NULL DEFAULT 'NEW',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Khi Order event `E42` redeliver, unique constraint giúp không tạo thêm một command mới. `commandId` được tạo một lần cùng bản ghi outbox; nếu retry publish, relay dùng **cùng commandId**, không cấp UUID mới. Dữ liệu của inbox và outbox phải commit/rollback **cùng transaction và cùng database transaction manager**.

Ngay cả khi relay publish thành công rồi chết trước khi mark `PUBLISHED`, việc gửi lại vẫn có thể xảy ra. Vì thế mẫu này hướng tới **at-least-once publish + idempotent processing**, không phải “exactly once” tự động xuyên hai broker.

### 11.2. Bridge bằng Shovel hoặc Federation

RabbitMQ hỗ trợ các cơ chế bridge như **Shovel** hoặc **Federation**. Đây là cấu hình chủ động nối các broker, với ngữ nghĩa delivery và recovery cần được xác minh theo version và policy thực tế:

- Hai broker **không tự đồng bộ** exchange/queue chỉ vì cùng tên.
- Cần định nghĩa rõ source, destination, acknowledgment, retry và quyền truy cập.
- Cơ chế bridge không mặc định bảo đảm không trùng hay giữ thứ tự toàn cục khi một phía lỗi.
- Nếu message có side effect nghiệp vụ, consumer đích vẫn cần idempotency.

Chọn application bridge khi cần validate/transform/enrich và trạng thái nghiệp vụ bền vững; chọn broker bridge khi bài toán chủ yếu là truyền dữ liệu ở tầng messaging. Đừng gộp trách nhiệm này vào DLX mặc định.

## 12. Request–reply với nhiều broker

`RabbitTemplate.convertSendAndReceive()` gửi request và chờ reply **trên connection factory của template đã gọi**. Trong mô hình thông thường, reply-to/correlation được quản lý trong cùng hệ thống RabbitMQ. Gửi request tới broker Order rồi hy vọng reply tự quay về từ broker Billing là giả định sai nếu không có đường reply bridge được thiết kế trước.

Nếu thực sự cần RPC đi qua nhiều broker, phải xác định:

- `requestId`, `correlationId` và message ID ổn định xuyên hai phía;
- điểm nhận request, điểm gửi reply, reply queue/route trên từng broker;
- giới hạn `replyTimeout` và trường hợp reply đến muộn;
- idempotency khi caller retry sau timeout;
- trách nhiệm xử lý lệnh đã thành công trong khi caller không còn đợi.

Với tác vụ kéo dài hoặc cần đảm bảo cao, mô hình **command + event kết quả** thường dễ vận hành hơn một lời gọi RPC đồng bộ đi qua nhiều broker.

## 13. Quan sát đúng tài nguyên của từng broker

Vì cùng một queue name có thể tồn tại trên nhiều broker/vhost, mọi metric và log cần tối thiểu nhãn **broker/vhost/queue** hoặc destination đủ rõ ràng.

| Kiểm tra | Broker Order | Broker Billing |
| --- | --- | --- |
| Endpoint/vhost | `rabbit-orders.internal /orders` | `rabbit-billing.internal /billing` |
| Connection bean | `ordersConnectionFactory` | `billingConnectionFactory` |
| Admin bean | `ordersRabbitAdmin` | `billingRabbitAdmin` |
| Exchange | `orders.events` | `billing.commands` |
| Work queue | `orders.events.queue` | `billing.invoice.queue` |
| Binding key | `order.changed` | `invoice.generate` |
| Producer | `ordersRabbitTemplate` | `billingRabbitTemplate` |
| Consumer factory | `ordersListenerFactory` | `billingListenerFactory` |
| DLQ nếu bật | `orders.events.dlq` | `billing.invoice.dlq` |

Khi điều tra message không tới nơi, theo vết:

~~~text
eventId / commandId
  → Bean RabbitTemplate
  → Bean ConnectionFactory
  → Broker host + virtual host
  → Exchange + routing key
  → Binding + queue
  → Listener containerFactory
  → Consumer ACK / business commit
~~~

Không chỉ xem `convertAndSend()` có ném exception hay không. Quan sát **publisher return**, confirm, queue ingress, delivery, ACK, DLQ và database commit để biết message đã đi đến đâu.

## 14. Kịch bản kiểm thử thực hành

Các tình huống dưới đây nên chạy với **hai RabbitMQ độc lập**. Dùng broker/vhost cố định và kiểm tra trực tiếp tài nguyên trên từng bên.

### Kịch bản A — gửi và nhận đúng broker

1. Khởi động hai broker, vhost và tài khoản đã phân quyền.
2. Cho RabbitAdmin khai báo topology tương ứng.
3. Publish `OrderChanged` và `GenerateInvoice` bằng hai template.
4. Kiểm tra event Order chỉ tới queue Order và command Billing chỉ tới queue Billing.
5. Xác minh listener tương ứng xử lý và ACK thành công.

**Kỳ vọng:** đường đi của message trùng với bảng mapping bean ở mục 4.

### Kịch bản B — cố tình gửi bằng template sai

1. Trong môi trường thử, publish `invoice.generate` bằng `ordersRabbitTemplate`.
2. Quan sát lỗi exchange không tồn tại, publisher return hoặc queue không mong muốn.
3. Kiểm tra queue Billing không tự nhận message từ broker Order.
4. Khôi phục template đúng.

**Kỳ vọng:** chứng minh exchange/routing key chỉ có ý nghĩa trong broker/vhost đã chọn.

### Kịch bản C — RabbitAdmin không khai báo chéo

1. Dùng tài nguyên thử nghiệm có thể tạo lại.
2. Khởi động ứng dụng và để admin tự khai báo.
3. Kiểm tra trên broker Order chỉ có topology Order do `ordersRabbitAdmin` quản lý.
4. Kiểm tra trên broker Billing chỉ có topology Billing do `billingRabbitAdmin` quản lý.
5. Xác minh bindings tương ứng, không chỉ sự tồn tại của queue.

**Kỳ vọng:** `explicitDeclarationsOnly` kết hợp `adminsThatShouldDeclare` hoạt động đúng.

### Kịch bản D — trùng tên exchange trên hai broker

1. Cố ý dùng cùng một tên exchange trên cả hai broker trong môi trường test.
2. Publish bằng template Order.
3. Kiểm tra message vẫn chỉ đi vào các queue có binding trên broker Order.
4. Đối chiếu trạng thái broker Billing.

**Kỳ vọng:** tên exchange không phải định danh tài nguyên toàn cục.

### Kịch bản E — broker Billing down, Order còn chạy

1. Dừng hoặc chặn kết nối Billing.
2. Publish sự kiện mới lên Order; kiểm tra luồng này vẫn chạy.
3. Gửi Billing command, quan sát lỗi/timeout.
4. Nếu dùng outbox, xác minh command còn lưu và được phát lại sau reconnect.
5. Đo thời gian Billing hồi phục và backlog.

**Kỳ vọng:** có cơ chế phục hồi riêng, dữ liệu nguồn không bị mất vì broker Billing ngừng hoạt động.

### Kịch bản F — confirm chưa xác định

1. Ghi command Billing với `commandId=C42` vào outbox.
2. Gây mất kết nối sau publish nhưng trước confirm.
3. Cho relay retry **cùng C42**.
4. Kiểm tra consumer Billing không xuất hóa đơn hai lần.

**Kỳ vọng:** trạng thái unknown được xử lý bằng retry an toàn và idempotency.

### Kịch bản G — sai binding trên broker đích

1. Tạm bỏ binding `invoice.generate` của queue Billing.
2. Publish với mandatory/returns đã bật.
3. Xác minh message được return hoặc quan sát được lỗi routing phù hợp.
4. Khôi phục binding, retry với cùng ID.

**Kỳ vọng:** confirm ACK không được hiểu thành “consumer đã xử lý”.

### Kịch bản H — bridge chết trước ACK nguồn

1. Bridge nhận `E42`, ghi inbox và billing outbox trong một DB transaction.
2. Commit rồi mô phỏng tiến trình chết trước ACK Order.
3. Khi Order redeliver E42, unique constraint ngăn tạo command thứ hai.
4. Relay vẫn publish từ outbox và Billing xử lý idempotent.

**Kỳ vọng:** không mất command và không có duplicate business effect.

### Kịch bản I — wrong vhost/credential

1. Cấu hình Billing dùng vhost không tồn tại hoặc user thiếu quyền trong môi trường thử.
2. Quan sát connection/admin/listener Billing thất bại.
3. Kiểm tra Order vẫn có connection riêng.
4. Khôi phục cấu hình và kiểm tra tài nguyên sau recovery.

**Kỳ vọng:** phân biệt lỗi kết nối/quyền với lỗi routing key.

### Kịch bản J — DLQ riêng trên từng broker

1. Khai báo DLX/DLQ cho hai broker và binding đúng.
2. Publish message lỗi vào queue nguồn ở mỗi broker.
3. Hết retry budget, reject với `requeue=false`.
4. Kiểm tra poison message Order vào DLQ Order, Billing vào DLQ Billing.
5. Xác minh không có dead-letter tự chuyển qua broker khác.

**Kỳ vọng:** xử lý lỗi có thể quan sát và replay theo từng hệ thống.

## 15. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng một `RabbitTemplate` cho tất cả luồng | Publish vào broker không mong muốn | Template riêng + `@Qualifier` |
| Có hai connection nhưng listener dùng factory mặc định | Consumer đăng ký vào broker sai | Chỉ định `containerFactory` trên từng listener |
| Hai RabbitAdmin khai báo mọi bean `Declarable` | Topology bị tạo chéo, lỗi quyền hoặc sai route | `setExplicitDeclarationsOnly(true)` và chỉ định declaring admin |
| Nhầm cluster node với broker độc lập | Dùng failover address thay cho routing nghiệp vụ | Xác định rõ phạm vi cluster/vhost |
| Cùng tên exchange được hiểu là cùng tài nguyên | Message không tự đến broker khác | Bridge có chủ đích |
| Chỉ xét confirm ACK | Bỏ sót sai binding hoặc lỗi nghiệp vụ | Returns/mandatory, consumer ACK, business commit |
| Retry event với UUID mới | Dễ gây duplicate effect | Giữ ID ổn định, outbox, inbox |
| ACK source trước publish destination bền vững | Có thể mất message khi bridge lỗi | Transactional inbox/outbox và relay confirms |
| Dùng chung health flag cho hai broker | Không phát hiện một bên down | Metric và readiness theo broker |
| Coi DLQ là tuyến chuyển message liên broker | Message vẫn bị xử lý trong broker đang giữ | DLX/DLQ riêng, Shovel/Federation/bridge khi cần |
| Đổi queue argument và chỉ restart ứng dụng | Redeclare thất bại vì resource không tương đương | Migration topology có kế hoạch |

## 16. Checklist trước production

- [ ] Xác định đang dùng hai broker độc lập, hai vhost hay các node của một cluster.
- [ ] Tạo connection factory riêng, gồm host/vhost/credentials/TLS/heartbeat phù hợp.
- [ ] Tiêm `RabbitTemplate` bằng `@Qualifier` thay vì phụ thuộc mặc định.
- [ ] Mỗi `@RabbitListener` chỉ rõ `containerFactory` kết nối tới broker tương ứng.
- [ ] Mỗi broker có RabbitAdmin riêng; declarable được gán đúng admin.
- [ ] Kiểm tra exchange, queue và **binding** trên broker/vhost đích.
- [ ] Publisher confirms/returns và mandatory được bật, giám sát theo từng broker.
- [ ] Consumer ACK sau commit; handler idempotent để chịu duplicate delivery.
- [ ] Retry có giới hạn và DLX/DLQ riêng cho từng luồng; replay dùng cùng ID nghiệp vụ.
- [ ] Khi chuyển message liên broker, đã thiết kế inbox/outbox hoặc bridge có ngữ nghĩa delivery rõ ràng.
- [ ] Có metric theo broker/vhost: connection, queue, unacked, redelivery, DLQ, outbox pending, E2E lag.
- [ ] Đã kiểm thử broker đích down, sai template/factory, admin khai báo chéo, wrong binding/vhost và bridge crash.
- [ ] Có kế hoạch migration khi thay đổi queue type, DLX hoặc arguments không tương đương.

## 17. Tổng kết

Đối với **nhiều RabbitMQ broker độc lập**, định tuyến luôn có **hai tầng**: ứng dụng chọn **broker/vhost** qua `ConnectionFactory` và `RabbitTemplate` hoặc listener factory, sau đó broker dùng **exchange, routing key, binding** để định tuyến tới queue. **Tên exchange hay tên queue không thể tự thay thế lựa chọn connection factory.**

Trong **SPRING_AMQP**, cấu hình cần minh bạch: mỗi broker có `CachingConnectionFactory`, `RabbitTemplate`, `SimpleRabbitListenerContainerFactory` và `RabbitAdmin` tương ứng, còn các `Queue`, `Exchange`, `Binding` chỉ được khai báo trên broker chủ sở hữu. Nếu ứng dụng chuyển message giữa broker A và B, hãy coi đây là một luồng nghiệp vụ có **cửa sổ mất/trùng độc lập**, cần confirms/returns, inbox/outbox và consumer idempotent.

Một hệ thống đa broker đáng tin cậy phải trả lời được: **Message được gửi qua connection nào? Topology đích nằm trên broker/vhost nào? Listener nào nhận? Ai khai báo tài nguyên đó? Và message sẽ được phục hồi ra sao khi chỉ một broker gặp sự cố?** Khi các câu trả lời rõ ràng, việc vận hành, retry, dead-letter và quan sát đầu cuối mới có thể kiểm chứng.
