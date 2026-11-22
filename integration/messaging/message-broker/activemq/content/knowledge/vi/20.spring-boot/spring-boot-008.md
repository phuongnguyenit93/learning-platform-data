# Cấu hình nhiều broker hoặc nhiều ConnectionFactory trong một ứng dụng

> **Chương:** Spring Boot  
> **Phạm vi:** Spring Boot 3.x, Spring JMS/Jakarta Messaging và ActiveMQ Classic/Artemis. Ví dụ triển khai chính dùng **hai broker Artemis độc lập**; tích hợp Classic được giải thích riêng để không trộn API JMS hoặc wire protocol.

Một dịch vụ có thể nhận **OrderCreated** từ broker Orders, rồi phát lệnh **ChargePayment** sang broker Billing. Nếu ứng dụng chỉ dùng một **JmsTemplate** mặc định, hoặc một listener không chỉ rõ ConnectionFactory, rất dễ gửi nhầm broker khi hai phía có cùng tên queue. Nguy hiểm hơn, nếu Billing đã nhận lệnh còn Orders chưa commit ACK thì một lần crash có thể khiến lệnh được gửi lại.

Bài này giải quyết ba vấn đề thực hành: **định danh từng broker bằng nhóm bean riêng**, **gắn đúng producer và listener với từng nhóm**, và **quản lý lỗi/giao dịch ở ranh giới hai broker**. Không cần ôn lại toàn bộ JMS; các ví dụ chỉ dùng những API cần cho cấu hình nhiều nguồn kết nối.

## 1. Xác định bài toán: nhiều broker, nhiều factory hay nhiều queue?

| Tình huống | Cần tách ConnectionFactory? | Lý do |
|---|---|---|
| Orders và Billing là hai Artemis broker độc lập | **Có** | URL, credential, vòng đời kết nối và failure domain khác nhau |
| Một ActiveMQ Classic và một Artemis | **Có** | Cần client và protocol phù hợp từng broker |
| Một broker, hai JMS Queue, cùng tài khoản | **Thường không** | Một factory và JmsTemplate có thể gửi tới nhiều destination |
| Một broker nhưng hai tài khoản/quyền khác nhau | **Có thể** | Tách security principal và pool/timeout |
| Một logical broker có active/backup HA | **Không nhất thiết** | Dùng cơ chế failover/HA của client, không tùy tiện coi hai node là hai broker nghiệp vụ |
| Một broker có cả queue và topic | **Thường không** | Có thể tách JmsTemplate và listener container theo pubSubDomain nhưng dùng cùng ConnectionFactory |
| Broker được thêm/bớt động cho nhiều tenant | **Có thể cần registry động** | Hai bean tĩnh không đáp ứng lifecycle và isolation động |

**ConnectionFactory quyết định kết nối đến broker nào.** Một JMS Destination tên **orders.events.v1** không chứa thông tin host; hai broker có thể có hai queue cùng tên mà hoàn toàn độc lập.

~~~mermaid
flowchart LR
    APP["Spring Boot service"]
    APP --> OC["ordersConnectionFactory"]
    APP --> BC["billingConnectionFactory"]
    OC --> OB["Orders Artemis<br/>orders.events.v1"]
    BC --> BB["Billing Artemis<br/>billing.commands.v1"]
~~~

Đề xuất naming convention:

~~~text
Orders side:
    ordersConnectionFactory
    ordersJmsTemplate
    ordersListenerContainerFactory
    orders credentials + health + DLQ

Billing side:
    billingConnectionFactory
    billingJmsTemplate
    billingListenerContainerFactory
    billing credentials + health + DLQ
~~~

Nếu Billing chỉ nhận message từ ứng dụng mà không có @JmsListener phía ứng dụng, có thể không cần billingListenerContainerFactory. Nguyên tắc là **khai báo những tài nguyên cần dùng và đặt tên tường minh**, không nhân đôi cho đẹp sơ đồ.

## 2. Những điều Spring Boot auto-configuration không tự làm

Spring Boot có JMS auto-configuration thuận tiện cho trường hợp **một ConnectionFactory mặc định**. Khi làm việc với nhiều broker:

- Các thuộc tính **spring.artemis.*** hoặc **spring.activemq.*** thường phục vụ factory tự động mặc định; chúng **không tự sinh ra hai factory Orders/Billing**.
- Khi ứng dụng khai báo nhiều bean **jakarta.jms.ConnectionFactory** cùng kiểu, injection không có **@Qualifier** có thể báo **NoUniqueBeanDefinitionException**.
- Auto-configuration có thể **back off** khi đã có bean cùng loại do người dùng định nghĩa. Vì vậy không nên dựa vào việc Boot sẽ luôn tạo thêm một JmsTemplate hoặc listener factory ngầm.
- **@Primary** chỉ giúp chọn một bean mặc định ở những injection không có qualifier. Nó không làm mọi listener tự kết nối đúng broker theo tên destination.
- **@JmsListener** không chỉ rõ **containerFactory** thường cần một factory mặc định mang tên **jmsListenerContainerFactory**; nếu bean này vắng mặt, startup có thể lỗi; nếu trỏ sai broker, lỗi khó thấy hơn.

**Chiến lược minh bạch:** tự khai báo hai ConnectionFactory, hai JmsTemplate và hai listener container factory; cấu hình ứng dụng nằm dưới **app.messaging.orders** và **app.messaging.billing**.

### 2.1. Không trộn javax.jms với jakarta.jms

| Stack | Namespace | Điều kiện |
|---|---|---|
| Spring Boot 3.x / Spring Framework 6 | **jakarta.jms** | Client phải triển khai Jakarta Messaging |
| Spring Boot 2.x / Spring Framework 5 | **javax.jms** | Dùng client thuộc thế hệ javax phù hợp |
| Artemis Jakarta client trong Boot 3 | **jakarta.jms** | Core protocol acceptor/client phù hợp |
| Classic trong Boot 3 | **jakarta.jms** | Cần Classic client có Jakarta support tương thích với phiên bản broker |

Hai namespace không phải hai alias của cùng kiểu Java. Không ép cast một **javax.jms.ConnectionFactory** vào Spring JMS 6. Nếu tích hợp cả Classic và Artemis, chọn đúng dependency và kiểm tra classpath trước khi khởi động.

## 3. Hai broker Artemis: dependency và application.yml

Giả sử môi trường lab có hai Artemis instance tách biệt:

~~~text
Orders  → tcp://127.0.0.1:61616 → queue lab.orders.events.v1
Billing → tcp://127.0.0.1:61626 → queue lab.billing.commands.v1
~~~

Hai cổng chỉ là **ví dụ**. Trên mỗi broker phải có acceptor Core phù hợp, queue ANYCAST tương ứng, user có quyền send/consume và chính sách redelivery/DLQ của riêng broker.

### 3.1. Dependency Maven dưới Spring Boot 3 BOM/parent

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-artemis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Starter Artemis giúp đưa Spring JMS và Artemis Jakarta client phù hợp với BOM của Boot. Actuator không bắt buộc để gửi/nhận, nhưng hữu ích cho vận hành; **health theo từng broker cần cấu hình chủ động**, không mặc định coi một health UP là cả hai khỏe.

### 3.2. Custom properties cho hai broker

~~~yaml
app:
  messaging:
    orders:
      broker-url: "${ORDERS_MQ_URL:tcp://127.0.0.1:61616}"
      username: "${ORDERS_MQ_USER}"
      password: "${ORDERS_MQ_PASSWORD}"
      queue: "lab.orders.events.v1"
    billing:
      broker-url: "${BILLING_MQ_URL:tcp://127.0.0.1:61626}"
      username: "${BILLING_MQ_USER}"
      password: "${BILLING_MQ_PASSWORD}"
      queue: "lab.billing.commands.v1"
~~~

**Chú ý:** không commit mật khẩu thật vào YAML. Hai password không có fallback; production nên cấp qua secret manager/environment. URI ví dụ chưa mã hóa, chỉ phù hợp lab cục bộ; production cần TLS, xác minh hostname/certificate và secret riêng cho hai broker.

Custom properties này được đọc bởi cấu hình Java ở mục kế tiếp. Thay đổi **spring.artemis.broker-url** mà không đổi **app.messaging.orders.broker-url** sẽ **không** đổi URL do code tự tạo trong ví dụ này.

### 3.3. Bind properties vào record

Tập tin **BrokerTopology.java**:

~~~java
package com.example.multijms;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.messaging")
public record BrokerTopology(Broker orders, Broker billing) {

    public record Broker(
            String brokerUrl,
            String username,
            String password,
            String queue) {
    }
}
~~~

Spring Boot 3 hỗ trợ constructor binding đối với record theo quy tắc ConfigurationProperties. Trong production nên bổ sung Bean Validation (**@NotBlank**, @Validated và dependency validation) hoặc validation riêng để phát hiện thiếu URL, username, password, queue **lúc startup**, không đợi đến khi nhận event mới thất bại.

## 4. Khai báo ConnectionFactory, template và listener factory

Tập tin **BrokerJmsConfiguration.java**:

~~~java
package com.example.multijms;

import jakarta.jms.ConnectionFactory;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
@EnableConfigurationProperties(BrokerTopology.class)
public class BrokerJmsConfiguration {

    @Bean("ordersConnectionFactory")
    public ConnectionFactory ordersConnectionFactory(
            BrokerTopology topology) {
        var p = topology.orders();
        return new ActiveMQConnectionFactory(
            p.brokerUrl(), p.username(), p.password());
    }

    @Bean("billingConnectionFactory")
    public ConnectionFactory billingConnectionFactory(
            BrokerTopology topology) {
        var p = topology.billing();
        return new ActiveMQConnectionFactory(
            p.brokerUrl(), p.username(), p.password());
    }

    @Bean("ordersJmsTemplate")
    public JmsTemplate ordersJmsTemplate(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return queueTemplate(connectionFactory);
    }

    @Bean("billingJmsTemplate")
    public JmsTemplate billingJmsTemplate(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {
        return queueTemplate(connectionFactory);
    }

    @Bean("ordersListenerContainerFactory")
    public DefaultJmsListenerContainerFactory ordersListeners(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {

        var factory = queueListenerFactory(connectionFactory);
        factory.setConcurrency("1-3");
        return factory;
    }

    @Bean("billingListenerContainerFactory")
    public DefaultJmsListenerContainerFactory billingListeners(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {

        var factory = queueListenerFactory(connectionFactory);
        factory.setConcurrency("1-2");
        return factory;
    }

    private static JmsTemplate queueTemplate(
            ConnectionFactory connectionFactory) {

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        template.setSessionTransacted(true);
        return template;
    }

    private static DefaultJmsListenerContainerFactory
            queueListenerFactory(ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

### 4.1. Vì sao không đặt @Primary trong ví dụ?

Khi có hai ConnectionFactory/JmsTemplate ngang hàng, không có broker mặc định an toàn. **@Primary** có thể che một lỗi injection: service định gửi Billing nhưng quên qualifier lại gửi Orders. Để lập trình viên phải chỉ định rõ ranh giới, bài này **không dùng @Primary**.

Nếu một thư viện thực sự yêu cầu default ConnectionFactory, có thể chọn @Primary có chủ đích và ghi rõ phạm vi; mọi listener nghiệp vụ vẫn nên khai báo **containerFactory** cụ thể.

### 4.2. Hai local JMS transactions là hai tài nguyên

**setSessionTransacted(true)** trên listener container khiến việc nhận message từ **broker của factory đó** được commit/rollback theo callback. **setSessionTransacted(true)** trên JmsTemplate khiến việc send qua template có local JMS transaction phù hợp. Hai transaction cục bộ **không tự kết hợp thành một transaction phân tán** khi factory trỏ tới hai broker độc lập.

Ngoài ra, **setConcurrency("1-3")** có thể tạo nhiều sessions/consumers. Không hứa giữ đúng total order của queue khi callback xử lý song song. Nếu xử lý yêu cầu ordering theo orderId hoặc paymentAttemptId, phải thiết kế phân vùng/serialization và idempotency phù hợp.

### 4.3. Khi nào cần cấu hình thêm?

Mẫu trên dùng queue và String/TextMessage. Nếu ứng dụng dùng topic, phải cấu hình **pubSubDomain=true** trên template/container thích hợp. Nếu muốn parse JSON thẳng thành object, cài **MessageConverter** được kiểm soát và cấu hình cho **đúng template và đúng listener factory**; một converter gắn cho Orders không tự áp sang Billing.

## 5. Gửi đúng broker qua JmsTemplate có qualifier

Tập tin **OrderEventPublisher.java**:

~~~java
package com.example.multijms;

import java.util.UUID;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final JmsTemplate ordersTemplate;
    private final BrokerTopology topology;

    public OrderEventPublisher(
            @Qualifier("ordersJmsTemplate") JmsTemplate ordersTemplate,
            BrokerTopology topology) {
        this.ordersTemplate = ordersTemplate;
        this.topology = topology;
    }

    public String publishDemoOrderEvent(String jsonPayload) {
        String eventId = UUID.randomUUID().toString();

        ordersTemplate.convertAndSend(
            topology.orders().queue(),
            jsonPayload,
            message -> {
                message.setStringProperty("eventId", eventId);
                return message;
            }
        );

        return eventId;
    }
}
~~~

**JmsTemplate là bean được cấu hình sẵn, có thể được gọi từ nhiều service/thread theo mô hình Spring;** không chia sẻ trực tiếp một raw **jakarta.jms.Session** giữa các thread. Tên destination của phương thức **convertAndSend** là queue **trên broker mà ordersTemplate đã gắn qua ConnectionFactory**.

Ví dụ tạo eventId cho một sự kiện demo. Trong production, khi retry vì timeout, phải **giữ lại eventId đã được lưu** (outbox hoặc nguồn dữ liệu nghiệp vụ). Gọi lại method và sinh UUID mới cho cùng một event logic sẽ phá idempotency.

## 6. Gắn @JmsListener với broker đúng bằng containerFactory

~~~mermaid
sequenceDiagram
    participant P as OrderEventPublisher
    participant O as Orders broker
    participant L as Orders listener
    participant T as Billing JmsTemplate
    participant B as Billing broker
    P->>O: Send OrderCreated(eventId=evt-42)
    O->>L: Deliver evt-42
    L->>T: convertAndSend bill-evt-42
    T->>B: Send command to Billing
    B-->>T: Billing local TX commit
    T-->>L: Return
    L->>O: Orders listener local TX commit
~~~

### 6.1. Listener phía Orders chuyển tiếp sang Billing

Tập tin **OrdersToBillingBridge.java**:

~~~java
package com.example.multijms;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrdersToBillingBridge {
    private final JmsTemplate billingTemplate;
    private final BrokerTopology topology;

    public OrdersToBillingBridge(
            @Qualifier("billingJmsTemplate") JmsTemplate billingTemplate,
            BrokerTopology topology) {
        this.billingTemplate = billingTemplate;
        this.topology = topology;
    }

    @JmsListener(
        destination = "${app.messaging.orders.queue}",
        containerFactory = "ordersListenerContainerFactory"
    )
    public void onOrder(
            String orderJson,
            @Header("eventId") String eventId) {

        String commandId = "bill-" + eventId;

        // Lab chỉ chuyển tiếp body để minh họa wiring.
        // Production phải validate schema và chuyển đổi event
        // thành command nghiệp vụ, không charge trực tiếp từ raw JSON.
        billingTemplate.convertAndSend(
            topology.billing().queue(),
            orderJson,
            message -> {
                message.setStringProperty("eventId", eventId);
                message.setStringProperty("commandId", commandId);
                message.setJMSCorrelationID(eventId);
                message.setStringProperty(
                    "_AMQ_DUPL_ID", "billing-bridge-" + eventId);
                return message;
            }
        );
    }
}
~~~

Hai ranh giới độc lập:

- **@JmsListener.containerFactory** xác định consumer nhận từ **Orders**. Chỉ ghi **destination=orders queue** không đủ vì queue name không chứa broker.
- **billingJmsTemplate** được inject bằng qualifier, nên send đi **Billing**. Nhầm template sẽ gửi sang broker khác dù destination string nhìn hợp lý.

**_AMQ_DUPL_ID** là thuộc tính duplicate detection của Artemis, chỉ dùng để giảm bản publish trùng khi ID còn trong cache đúng address. Không dùng nó làm bằng chứng một hiệu ứng thanh toán được thực hiện đúng một lần; Billing consumer vẫn phải có business idempotency.

### 6.2. Listener phía Billing nhận qua factory khác

Tập tin **BillingCommandsListener.java**:

~~~java
package com.example.multijms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class BillingCommandsListener {

    @JmsListener(
        destination = "${app.messaging.billing.queue}",
        containerFactory = "billingListenerContainerFactory"
    )
    public void onCommand(
            String body,
            @Header("commandId") String commandId) {

        // Chỉ là lab. Production: idempotent inbox/commandId,
        // commit side effect an toàn rồi trả về để container
        // commit JMS receive của Billing.
        System.out.println("Billing commandId=" + commandId
            + ", payload length=" + body.length());
    }
}
~~~

Spring JMS xử lý TextMessage → String qua converter phù hợp và đưa JMS properties vào Spring message headers để **@Header** truy cập. Với payload class JSON, cần converter/schema được cài trên **từng container factory** thay vì giả định converter của template khác được chia sẻ.

### 6.3. Lỗi rất dễ mắc

~~~java
// Không rõ default listener factory trỏ tới broker nào:
@JmsListener(destination = "lab.orders.events.v1")
public void onMessage(String body) {
    // ...
}
~~~

Annotation không chỉ rõ containerFactory sẽ cần **default jmsListenerContainerFactory**. Nếu thiếu, application có thể lỗi startup; nếu trỏ sang Billing, listener có thể tiêu thụ nhầm queue cùng tên trên Billing. Trong hệ multi-broker nên yêu cầu mọi listener ghi rõ **containerFactory**.

Đến đây ứng dụng đã có **hai ConnectionFactory, hai template và hai listener containers độc lập**; phần tiếp theo đánh giá điều gì xảy ra nếu một broker hoặc một transaction thất bại.


## 7. Hai local JMS transactions không tạo distributed transaction

**setSessionTransacted(true)** trên Orders listener và Billing JmsTemplate tạo ra **hai local JMS transactions** ở hai broker độc lập. Trong ví dụ ở mục 6:

1. Orders dispatch event trong session nhận của listener Orders.
2. Listener gọi billingTemplate để gửi command. Billing send hoàn tất transaction cục bộ trước khi lệnh convertAndSend trả về bình thường.
3. Listener Orders trở về; container Orders mới commit receive trên Orders.

**Có cửa sổ lỗi sau bước 2, trước bước 3.** Nếu process crash, Billing đã có command nhưng Orders có thể giao lại event.

~~~mermaid
sequenceDiagram
    participant O as Orders broker
    participant S as Spring bridge
    participant B as Billing broker
    O->>S: Deliver evt-42 (Orders TX)
    S->>B: Send bill-evt-42 (Billing TX)
    B-->>S: Billing commit OK
    Note over S,O: JVM crash trước Orders commit
    O->>S: Redeliver evt-42
    S->>B: Send bill-evt-42 lần hai
    Note over B: Có thể có duplicate command
~~~

### 7.1. Ma trận lỗi

| Tình huống | Orders | Billing | Phương án |
|---|---|---|---|
| Billing không kết nối được, send throw | Listener Orders rollback theo transaction container | Không có commit Billing được xác nhận | Orders redelivery/backoff có giới hạn |
| Billing commit rồi app crash | Orders receive chưa commit; có thể redeliver | Đã nhận command | Giữ commandId và Billing idempotency |
| Billing send bị timeout, kết quả chưa rõ | Orders có thể rollback | **Không biết chắc** command đã được nhận chưa | Retry cùng business ID, reconcile |
| Orders commit, Billing consumer lỗi | Orders đã ACK | Billing retry/DLQ độc lập | Quan sát trên broker Billing |
| Billing outage kéo dài | Orders backlog/DLQ tăng | Không xử lý | Timeout, backpressure, kế hoạch recovery |

### 7.2. @Transactional có giải quyết được không?

Một annotation **@Transactional** thông thường chỉ chọn một **PlatformTransactionManager**. Nó không tự gom:

- Orders JMS session.
- Billing JMS session.
- Transaction PostgreSQL.
- Lời gọi external payment API.

Có thể dùng **JmsTransactionManager** cho từng ConnectionFactory nhưng hai local managers không tương đương **XA two-phase commit**. Nếu thật sự cần atomicity xuyên broker phải đánh giá **XA-capable connection factories, JTA coordinator, transaction recovery, broker support và chi phí vận hành**. Không coi đây là một thay đổi chỉ cần thêm một annotation.

### 7.3. Thiết kế at-least-once + idempotency

Trong nhiều dịch vụ, cách tiếp cận thực tế là:

- Tạo **eventId** ổn định trước publish; giữ nguyên qua retry/redelivery.
- Tạo **commandId** ổn định cho Billing, ví dụ **bill-evt-42**, không sinh UUID mới trong mỗi callback.
- Với Artemis, dùng **_AMQ_DUPL_ID** trên lần publish Billing để chặn resend khi ID còn trong duplicate cache của address. Cơ chế này có giới hạn, **không thay business idempotency**.
- Billing consumer lưu commandId hoặc paymentAttemptId vào inbox/unique constraint cùng transaction cập nhật nghiệp vụ.
- Với payment API ngoài database, truyền idempotency key khi có hỗ trợ, lưu trạng thái và đối soát lúc timeout/commit chưa rõ.
- Nếu database và publish phải phối hợp an toàn, dùng **transactional outbox** thay vì giả định hai local commits là nguyên tử.

~~~sql
CREATE TABLE processed_billing_commands (
    consumer_name TEXT NOT NULL,
    command_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, command_id)
);
~~~

**Chú ý:** marker đã xử lý và update nghiệp vụ trong cùng database phải commit chung một transaction. Nếu side effect đi qua payment provider bên ngoài, SQL transaction không tự bao trùm provider; cần idempotency/reconciliation ở tầng đó.

## 8. Error handling và DLQ tách theo broker

Không có một DLQ toàn cục cho Spring Boot application khi dùng hai broker.

~~~text
Orders:
  orders.events.v1
     → Orders listener rollback
     → Orders redelivery policy
     → Orders DLQ nếu đạt ngưỡng

Billing:
  billing.commands.v1
     → Billing listener rollback
     → Billing redelivery policy
     → Billing DLQ nếu đạt ngưỡng
~~~

Nếu Billing đã nhận command nhưng consumer ở Billing bị lỗi, Orders không tự rollback một event đã commit. Khi Orders listener thất bại trước commit, broker Orders quản lý việc giao lại event theo policy riêng.

### 8.1. Không bắt exception rồi trả về bình thường

~~~java
try {
    billingTemplate.convertAndSend(targetQueue, body);
} catch (Exception failure) {
    log.error("Billing unavailable", failure);
    // Nếu không có outbox đã ghi bền vững thì return
    // ở đây làm Orders listener có thể commit sai.
}
~~~

Với mẫu listener transacted, nếu send sang Billing lỗi mà chưa có nguồn recovery bền vững, hãy để exception thoát khỏi callback để container rollback receive của Orders. Nếu đã lưu công việc vào outbox bền vững thì có thể ACK Orders sau khi commit outbox, để publisher riêng xử lý retry.

### 8.2. Chặn retry nóng và resource exhaustion

- Đặt **connection timeout, reconnect/backoff** cho Billing theo client/version. Nếu Billing down, một send không nên chiếm listener thread vô thời hạn.
- Giới hạn **Orders listener concurrency** theo năng lực Billing; concurrency quá cao khi down chỉ nhân thêm số thread bị block.
- Cấu hình **redelivery policy/DLQ Orders** để không đưa cùng message vào callback liên tục.
- Không chồng **@Retryable vô hạn** trong callback lên broker redelivery mà không tính tổng số lần thử.
- Khi Billing phục hồi, replay Orders DLQ có kiểm soát và kiểm tra commandId đã được xử lý hay chưa.
- Theo dõi riêng backlog, consumer lag, DLQ, failover của Orders và Billing.

**setSessionTransacted(true)** trên DefaultJmsListenerContainerFactory giúp rollback local JMS receive khi listener thất bại; khoảng redelivery, số lượt thử và DLQ còn do broker policy quyết định. Không giả định một thuộc tính **spring.jms.listener.acknowledge-mode** sẽ tự áp cho factory tùy chỉnh ở mục 4.

## 9. Khi dùng đồng thời ActiveMQ Classic và Artemis

Ví dụ trước dùng hai broker Artemis với cùng class **org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory**. Trường hợp Classic + Artemis, phần kết nối phải dùng client/protocol tương ứng.

| Phía | Client phù hợp | Không được giả định |
|---|---|---|
| Artemis + Spring Boot 3 | Artemis Jakarta client với Core acceptor (hoặc protocol tương thích) | Không copy URI failover của Classic |
| Classic + Spring Boot 3 | Classic Jakarta-compatible client được phiên bản Classic hỗ trợ | Không trộn artifact chỉ dùng javax.jms với Spring JMS 6 |
| Classic + Spring Boot 2 | Classic javax.jms client | Không dùng thẳng import jakarta.jms của bài này |
| AMQP/bridge | Client, header mapping, routing đã kiểm chứng | JMSReplyTo, selector, transaction không tự bảo toàn mọi trường hợp |

**Bean graph vẫn giống nhau** nếu mỗi client cung cấp đúng interface **jakarta.jms.ConnectionFactory**:

~~~text
classicConnectionFactory
  → classicJmsTemplate
  → classicListenerContainerFactory

artemisConnectionFactory
  → artemisJmsTemplate
  → artemisListenerContainerFactory
~~~

Nhưng constructor/URI của Classic phải theo Classic client; **không sử dụng Artemis Core client để kết nối một Classic broker chỉ chấp nhận OpenWire**. Với Spring Boot 3, một số phiên bản Classic có dòng **activemq-client-jakarta**; xác minh Jakarta support, OpenWire, TLS và các giới hạn tính năng của phiên bản cụ thể trước khi chọn.

Thêm đồng thời hai starter **không có nghĩa** Boot tự sinh hai named ConnectionFactory chính xác. Khai báo bean theo namespace rõ ràng như bài mẫu và kiểm tra dependency conflict.

### 9.1. Hai queue cùng tên ở hai broker là hai tài nguyên khác nhau

~~~text
Orders broker:  events.incoming
Billing broker: events.incoming
~~~

Destination string **events.incoming** không chứa địa chỉ broker. Nếu service inject nhầm template hoặc listener factory, code có thể gửi thành công sang broker sai và khó phát hiện. Log cần cả **logicalBrokerName** và destination, ngoài message/business ID.

## 10. Connection/session caching và HA

Nhiều ConnectionFactory không có nghĩa mỗi message phải khởi tạo TCP socket mới. Spring JmsTemplate và listener container có lifecycle riêng; có thể dùng connection/session caching hoặc pool nhưng phải tách theo broker.

### 10.1. Helper minh họa CachingConnectionFactory

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.connection.CachingConnectionFactory;

public final class JmsConnectionCache {
    public static CachingConnectionFactory wrap(
            ConnectionFactory nativeFactory) {
        CachingConnectionFactory cache =
            new CachingConnectionFactory(nativeFactory);
        cache.setSessionCacheSize(8);
        return cache;
    }

    private JmsConnectionCache() {
    }
}
~~~

Helper trên **không tự được đăng ký trong BrokerJmsConfiguration**. Nếu chọn dùng, tạo một wrapper Orders và một wrapper Billing, truyền đúng wrapper đến template/listener tương ứng. Kiểm tra bean destruction, reconnect/failover và giới hạn sessions.

**DefaultMessageListenerContainer** đã có caching/recovery riêng. Chồng pool/cache lên có thể gây stale sessions/consumer, đặc biệt khi restart broker. Benchmark và fault-test trước khi dùng. **JmsTemplate** được thiết kế dùng như bean được chia sẻ sau khi cấu hình, nhưng raw **JMS Session/JMSContext** không nên bị nhiều thread dùng đồng thời.

### 10.2. HA node không phải broker nghiệp vụ thứ hai

Nếu Orders có hai node active/backup của **cùng logical broker**, dùng cấu hình HA/failover theo **Artemis client**. Với Classic, cú pháp và hành vi failover khác. Không thêm Billing URL vào danh sách failover của Orders để “không mất kết nối”: broker đó sở hữu queue và nghĩa nghiệp vụ khác.


## 11. Health, security và observability phải có tên broker

### 11.1. Một health JMS UP chưa đủ

Spring Boot Actuator hoặc custom health indicator có thể chỉ theo dõi một ConnectionFactory mặc định, tùy phiên bản và cách wiring. Trong ứng dụng hai broker phải có bằng chứng từng kết nối đều khỏe:

| Kiểm tra | Orders | Billing |
|---|---|---|
| TCP/TLS/hostname verification | Riêng | Riêng |
| JMS connection/session/authentication | ordersConnectionFactory | billingConnectionFactory |
| Queue tồn tại và ACL | orders.events.v1 | billing.commands.v1 |
| Send latency/error count | ordersJmsTemplate | billingJmsTemplate |
| Listener backlog, delivering, ACK | Orders consumer | Billing consumer |
| DLQ/oldest message age | Orders | Billing |
| Certificate rotation | Orders truststore/cert | Billing truststore/cert |

Không chạy health probe bằng cách gửi message vào queue thanh toán thật. Nếu muốn kiểm tra end-to-end, dùng queue health test riêng với tần suất và retention có giới hạn.

### 11.2. Tách secret và quyền

- **ORDERS_MQ_USER/PASSWORD** và **BILLING_MQ_USER/PASSWORD** thuộc hai miền bảo mật độc lập.
- Cấp quyền send/consume tối thiểu trên từng destination; không dùng tài khoản admin chung.
- Với TLS, broker có thể cần truststore/CA, hostname verification và client certificate khác nhau.
- Không ghi password trong URL, process arguments, trace hoặc exception message được đưa lên dashboard.
- Nếu một consumer phục vụ nhiều tenant, kiểm tra **business authorization** trước khi route, dù JMS ACL đã đúng.

### 11.3. Log theo nguồn, đích và business ID

~~~json
{
  "stage": "bridge-send",
  "sourceBroker": "orders",
  "sourceQueue": "lab.orders.events.v1",
  "targetBroker": "billing",
  "targetQueue": "lab.billing.commands.v1",
  "eventId": "evt-42",
  "commandId": "bill-evt-42",
  "result": "billing-local-tx-completed"
}
~~~

**JMSMessageID** trên Orders và JMSMessageID của command mới trên Billing không nhất thiết giống nhau. Dùng **eventId/commandId/JMSCorrelationID** ổn định để liên hệ hành trình xuyên broker. Các ID có cardinality cao thuộc **log/trace**, không nên thành label metric Prometheus; label ổn định nên là **logicalBroker, operation, destinationGroup, outcome**.

## 12. Bài lab kiểm chứng toàn bộ cấu hình

Chuẩn bị hai broker Artemis **sandbox** độc lập, mỗi broker một cổng và data directory, queue ANYCAST được provision. Không dùng credentials, queue hoặc payment provider production.

### Lab A — Kiểm tra bean wiring trước khi gửi

1. Khởi động Spring Boot với **ORDERS_MQ_*** và **BILLING_MQ_*** đúng.
2. Kiểm tra có bean **ordersConnectionFactory**, **billingConnectionFactory** riêng.
3. Đọc **ordersJmsTemplate.getConnectionFactory()** và **billingJmsTemplate.getConnectionFactory()**; đối chiếu tới đúng bean.
4. Kiểm tra mọi @JmsListener đều chỉ rõ **containerFactory** đúng.
5. Kiểm tra không có injection ConnectionFactory/JmsTemplate mơ hồ thiếu @Qualifier.

**Đạt:** tên broker–template–listener tạo thành hai chuỗi wiring riêng. Khi test bean mà chưa chạy broker, có thể cần cấu hình listener không auto-start hoặc test context giới hạn, vì full listener container có thể chủ động kết nối lúc startup.

### Lab B — Gửi event qua hai broker

1. Start Orders broker và Billing broker, xác nhận broker identity.
2. Gọi **OrderEventPublisher.publishDemoOrderEvent** với payload JSON demo, ghi eventId được trả.
3. Quan sát listener **OrdersToBillingBridge** nhận từ queue Orders.
4. Quan sát **BillingCommandsListener** nhận commandId dạng **bill-eventId** trên Billing.
5. Đọc enqueue/dequeue counters của hai broker.
6. Kiểm tra không có command tương ứng trên một queue cùng tên ở broker sai.

**Đạt:** message thực sự qua hai network endpoints khác nhau, không chỉ qua hai queue trên một broker.

### Lab C — Billing outage

1. Dừng **chỉ Billing broker** trong sandbox.
2. Gửi event mới vào Orders.
3. Quan sát billingTemplate send fail; Orders listener rollback/redelivery theo policy.
4. Ghi backlog, DLQ, retry delay và số thread Orders bị chờ.
5. Khởi động lại Billing; đối chiếu kết quả bằng eventId/commandId.
6. Xác minh consumer Billing không tạo side effect trùng.

**Đạt:** không nuốt lỗi Billing làm Orders ACK sai, có giới hạn retry và backoff.

### Lab D — Crash giữa hai commits

1. Trong test, cho Billing nhận và commit command.
2. Dừng JVM trước khi Orders listener commit receive.
3. Khởi động lại app để Orders redeliver event.
4. Ghi nhận commandId xuất hiện lại trong callback; Billing có thể thấy resend.
5. Bật inbox/unique constraint ở Billing và chứng minh chỉ có **một hiệu ứng nghiệp vụ**.

**Đạt:** giải thích được ranh giới của local JMS transaction thay vì mặc định giao dịch nguyên tử.

### Lab E — Sai containerFactory, hai broker có queue trùng tên

1. Tạo queue test **events.incoming** trên cả hai broker.
2. Cố ý cho một listener test tham chiếu billingListenerContainerFactory dù dự định đọc Orders.
3. Quan sát message tới sai phía hoặc listener không nhận event Orders.
4. Sửa containerFactory, thêm assertion và log logical broker.

**Đạt:** xác nhận **Destination string không quyết định connection**.

### Lab F — Restart một broker và kiểm tra isolation

1. Restart Orders khi Billing vẫn hoạt động, ghi thời gian hồi phục của Orders.
2. Restart Billing khi Orders vẫn hoạt động, kiểm tra send timeout/backoff.
3. Đo connection/session count, threads, memory và health indicators theo broker.
4. Lặp lại nếu dùng cache/pool; tìm stale sessions hoặc session leaks.
5. Đối soát business ID sau recovery.

**Đạt:** một broker outage không kéo theo resource exhaustion không kiểm soát ở broker còn lại.

## 13. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
|---|---|---|
| **NoUniqueBeanDefinitionException** | Nhiều bean cùng interface, injection thiếu qualifier | Thêm **@Qualifier** rõ từng service |
| @JmsListener không khởi động | Thiếu default factory hoặc tên containerFactory sai | Khai báo đúng factory trong annotation |
| Listener đọc nhầm queue | Queue trùng tên, chọn ConnectionFactory sai | Xem broker URL/identity và bean graph |
| Đổi spring.artemis.broker-url mà không có tác dụng | Bean custom đọc **app.messaging.*** | Sửa đúng custom properties |
| Billing nhận command trùng sau crash | Billing commit trước Orders commit | Idempotent Billing và commandId ổn định |
| Orders event mất khi Billing lỗi | Callback catch rồi return, Orders commit | Throw để rollback hoặc ghi outbox trước ACK |
| Outage làm cạn listener threads | Reconnect/send timeout dài, retry quá nhanh | Timeout, concurrency, backoff và DLQ |
| Code không compile với Spring JMS 6 | Trộn **javax.jms** và **jakarta.jms** | Chọn client Jakarta đúng phiên bản |
| TLS Orders UP, Billing FAIL | Truststore/hostname/credential khác nhau | Kiểm tra cấu hình Billing riêng |
| Health báo UP nhưng Billing down | Indicator chỉ quan sát factory mặc định | Health checks riêng từng broker |
| Tăng concurrency làm lệch thứ tự | Nhiều consumer/session xử lý song song | Ordering strategy và idempotency |
| Reconnect sang broker sai domain | Coi hai broker độc lập là HA endpoints | Phân lại topology/URI theo logical broker |

## 14. Checklist trước triển khai production

- [ ] Phân biệt **hai broker độc lập** với **hai node thuộc cùng HA logical broker**.
- [ ] Mỗi broker có ConnectionFactory/JmsTemplate/listener factory được đặt tên nhất quán khi cần.
- [ ] Mọi injection cần phân biệt broker đều dùng **@Qualifier**; không có default mơ hồ.
- [ ] Mọi **@JmsListener** chỉ rõ **containerFactory** và destination đúng broker.
- [ ] Spring Boot 3 dùng **jakarta.jms**, Artemis/Classic client đúng wire protocol và phiên bản.
- [ ] Custom properties, TLS, credentials và quyền được tách theo broker; không hardcode secret.
- [ ] Queue/topic/routing/ACL được provision và xác minh trên đúng broker.
- [ ] Hai local JMS transactions không bị diễn giải thành distributed XA transaction.
- [ ] Có ID nghiệp vụ ổn định cho retry/replay, inbox/outbox hoặc idempotency khi chuyển broker.
- [ ] Redelivery, DLQ, timeout, reconnect và concurrency được đo/cấu hình riêng.
- [ ] Caching/pooling được kiểm thử với restart từng broker; không chia sẻ raw Session đa luồng.
- [ ] Health, logs và metrics có nhãn **logical broker** rõ ràng.
- [ ] Đã thử Billing outage, crash giữa hai commit, sai factory, queue trùng tên và duplicate.
- [ ] Nếu dùng Classic và Artemis chung JVM, đã kiểm tra classpath, namespace JMS và mapping protocol.

**Kết luận:** Nhiều broker trong Spring Boot là bài toán **định danh connection resources và quản lý các failure domain**, không đơn giản là thêm URL. Khi mỗi broker có ConnectionFactory, JmsTemplate và listener container rõ ràng, ứng dụng tránh được việc gửi/nhận nhầm destination. Nhưng chuyển từ Orders sang Billing vẫn đi qua **hai local transactions độc lập**; một thiết kế đáng tin cậy phải giữ business ID qua retry, chống lặp ở consumer, có backoff/DLQ và kiểm chứng phục hồi từng broker.
