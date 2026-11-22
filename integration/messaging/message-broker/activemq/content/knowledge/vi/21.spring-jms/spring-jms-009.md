# Durable subscription, shared subscription và nhận diện client theo khả năng provider

> **Chương:** Spring JMS  
> **Bối cảnh:** Spring Boot 3.x/Spring Framework 6.x, Jakarta Messaging (`jakarta.jms`), ActiveMQ Artemis và ActiveMQ Classic.  
> **Mục tiêu:** Phân biệt *durable*, *shared*, *non-shared* trên **topic**, thiết kế định danh subscription đúng, cấu hình `DefaultJmsListenerContainerFactory`/`@JmsListener` và kiểm tra khả năng **JMS provider** trước khi mở rộng nhiều consumer/replica.

## 1. Một thay đổi concurrency có thể biến “một lần xử lý” thành “mỗi replica một lần xử lý”

Service `billing-projection` cần nhận sự kiện `OrderPlaced` từ topic `orders.events`, kể cả lúc service tắt để triển khai. Có hai yêu cầu riêng biệt:

1. **Durable:** khi không có consumer hoạt động, subscription vẫn giữ backlog để service nhận lại sau khi online.
2. **Shared:** nhiều consumer cùng tham gia **một subscription**, mỗi message của subscription chỉ được giao cho **một** consumer tại một thời điểm, thay vì mỗi instance nhận một bản sao.

Một cấu hình sai rất phổ biến:

```text
orders.events (topic)
   |
   +-- durable subscription billing-pod-A -> consumer A
   |
   +-- durable subscription billing-pod-B -> consumer B
   |
   +-- durable subscription billing-pod-C -> consumer C
```

Cả A/B/C đều là subscription riêng; mỗi message được gửi tới **mỗi subscription**. Nếu mục tiêu là ba replica **cùng chia tải một luồng xử lý**, kết quả này tạo xử lý nghiệp vụ lặp ba lần, cho dù `@JmsListener` và code của chúng giống nhau.

Cấu trúc mong muốn khi provider hỗ trợ shared durable:

```text
orders.events (topic)
   |
   +-- shared durable subscription "billing-projection-v1"
           |
           +-- consumer A (replica 1)
           +-- consumer B (replica 2)
           +-- consumer C (replica 3)

Mỗi event thuộc subscription được phân phối tới một consumer;
ACK/commit và redelivery quyết định vòng đời sau đó.
```

**Durable trả lời “có giữ dữ liệu khi offline không?”; shared trả lời “các consumer có cùng một subscription hay không?”** Không nên dùng hai tính từ thay thế nhau.

## 2. Ma trận bốn mô hình topic subscription

| Mô hình | Subscription tồn tại khi mọi consumer offline? | Có nhiều consumer hoạt động trên **một subscription**? | Ý nghĩa |
| --- | --- | --- | --- |
| Non-durable, non-shared | Không giữ backlog offline | Không | Consumer riêng chỉ nhận lúc đang hoạt động |
| **Durable, non-shared** | **Có** | **Không** | Một consumer hoạt động cho định danh subscription; phù hợp một logical subscriber |
| Non-durable, shared | Không giữ backlog offline | **Có** nếu JMS 2.0 provider hỗ trợ | Chia tải khi có consumer; không phải hàng đợi chờ offline |
| **Durable, shared** | **Có** | **Có** nếu JMS 2.0 provider hỗ trợ | Chia tải một backlog subscription, vẫn giữ dữ liệu khi không có consumer |

### 2.1. Điều kiện bắt buộc: phải là topic domain

JMS durable/shared subscription là khái niệm của **topic** (publish/subscribe). Trong Spring JMS, đặt:

```java
factory.setPubSubDomain(true);
```

Mặc định Spring JMS nhiều trường hợp dùng queue domain; nếu quên `pubSubDomain=true`, `destination="orders.events"` có thể được diễn giải như **Queue**, không phải Topic. Lúc đó hai consumer cạnh tranh trên queue, nhưng bài test “chạy được” **không chứng minh durable topic subscription đã được tạo**.

Với Artemis, topic JMS được ánh xạ vào **MULTICAST address** và subscription queue phù hợp. JMS Queue công việc thường gắn với **ANYCAST queue**. Không đánh giá chỉ qua tên `orders.events`: kiểm tra routing type/queue/subscription thực sự trên broker.

### 2.2. Shared không có nghĩa broadcast đến mọi replica

Ở một **shared** subscription, nhiều consumer chia một luồng message của subscription. Nếu cần cả hệ thống **billing** và **analytics** đều nhận một bản sao event, phải tạo **hai subscription khác tên**:

```text
orders.events
  +-- shared durable "billing-v1"   -> billing replicas chia tải
  +-- shared durable "analytics-v1" -> analytics replicas chia tải

Mỗi subscription nhận một bản sao logic của event.
Trong mỗi subscription, mỗi lần giao thuộc về một consumer.
```

**Một lần giao** không phải bảo đảm **xử lý nghiệp vụ đúng một lần**: consumer crash/ACK không chắc chắn có thể khiến event redeliver đến consumer khác trong cùng shared subscription. Luôn dùng `eventId`/idempotency khi có side effect.

## 3. Định danh durable subscription: `clientId`, `subscription name` và phạm vi provider

### 3.1. Durable non-shared: danh tính phải ổn định qua restart

Trong mô hình JMS truyền thống, durable subscription được nhận diện bằng bộ:

```text
JMS client identifier + durable subscription name
```

Ví dụ:

```text
clientId           = billing-service-eu
subscriptionName   = billing-orders-v1
topic              = orders.events
```

Khi service dừng rồi chạy lại với **đúng danh tính subscription** và broker vẫn giữ state, backlog được giao tiếp. Nếu đổi `clientId` hoặc `subscriptionName`, provider có thể tạo subscription **mới**; backlog của subscription cũ vẫn nằm lại, dù destination vẫn đúng tên.

`clientId` còn có ràng buộc quan trọng: trong các provider/JMS mode áp dụng uniqueness, **không thể đồng thời dùng cùng client identifier trên nhiều connection đang hoạt động**. Vì vậy ba pod cùng cấu hình một `clientId` cố định để chạy **non-shared** durable listener có thể gặp lỗi client ID duplicate hoặc tranh chấp subscription, thay vì mở rộng được throughput.

Với **non-shared durable**:

- Giữ `clientId` và `subscription` ổn định giữa các lần restart của cùng một logical consumer.
- Chỉ cho **một consumer đang hoạt động** trên durable subscription đó.
- Nếu muốn active–standby, chỉ kích hoạt một bên theo cơ chế điều phối phù hợp; đừng dùng `concurrency=3` rồi kỳ vọng broker tự biến thành shared.
- Không đặt tên subscription theo pod UID hoặc timestamp nếu cần khôi phục backlog cũ.

### 3.2. Shared durable: cẩn trọng với `clientId` trên nhiều replica

JMS 2.0 bổ sung API tạo **shared durable consumer**. Trong mô hình nhiều connection/replica muốn dùng **một shared subscription**, phương án dễ vận hành là:

- Dùng **cùng topic và subscription name** cho các replica.
- Không tự đặt `clientId` khác nhau theo từng pod **nếu mục tiêu là cùng một subscription**: client ID khác nhau có thể tạo các durable subscription khác nhau.
- Không cố cấu hình **cùng clientId** cho nhiều connection đồng thời nếu provider ràng buộc client ID phải duy nhất.
- Dựa vào kiểu shared durable **không có explicit client ID** khi được provider/broker hỗ trợ; kiểm tra chính xác identity thực tế trong broker console và thử nhiều process.

Lưu ý: quy tắc định danh subscription không có client ID, cách tạo durable queue và hỗ trợ multi-connection là **điểm phải thử trên đúng provider/protocol/version**. Không coi chỉ một câu `setSubscriptionShared(true)` là bằng chứng ba pod đã dùng chung backlog.

### 3.3. Subscription name là định danh lâu dài, không chỉ là một “consumer label”

Ví dụ đổi tên:

```text
Release v1: subscription="billing-orders-v1"
Release v2: subscription="billing-orders-v2"
```

Có thể xảy ra:

1. Subscription cũ `billing-orders-v1` còn tồn tại, giữ message chưa ACK.
2. Subscription mới `billing-orders-v2` bắt đầu theo thời điểm tạo và có backlog riêng.
3. Trong giai đoạn song song, mỗi subscription nhận bản sao mới.
4. Sau khi xóa pod v1, broker có thể vẫn giữ durable queue cũ.

Muốn thay subscription name/selector/topic, phải lập **kế hoạch migration**: quyết định drain backlog cũ, giai đoạn dual-run và thời điểm unsubscribe/delete subscription cũ. Xóa durable subscription để “dọn” có thể **mất message chưa xử lý**.

### 3.4. Các thuộc tính cấu thành contract

| Thành phần | Vì sao cần ổn định? | Hậu quả nếu thay không kiểm soát |
| --- | --- | --- |
| `topic`/destination | Quy định nguồn message subscription nhận | Đọc sai luồng hoặc tạo subscription khác |
| `subscriptionName` | Định danh subscription theo JMS | Backlog cũ không còn được đọc bởi deployment mới |
| `clientId` nếu áp dụng | Phần định danh durable/non-shared; phải quản lý uniqueness | Duplicate client ID, tạo subscription riêng hoặc lỗi kết nối |
| `messageSelector` | Quyết định message nào được subscription nhận | Thay selector có thể gây lỗi/recreate/mất backlog tùy provider |
| `noLocal` (nếu dùng) | Lọc message phát từ connection có liên quan | Thay semantics của subscription |
| `durable/shared` | Quy định retention và concurrency | Đổi mode có thể không tương thích subscription đã tồn tại |
| Broker identity/namespace | Subscription thuộc broker hoặc topology cụ thể | Đổi cluster/tenant có thể là một subscription khác |

Một subscription hiện hữu được tạo với selector/topic khác không phải lúc nào cũng có thể “thay tại chỗ” khi consumer đang chạy. Một số provider từ chối; những đường thay thế/recreate có thể bỏ backlog. **Không đổi selector trong rollout mà chưa kiểm chứng cách provider xử lý subscription đã tồn tại.**

## 4. Phần nào là JMS chuẩn, phần nào là extension của broker?

### 4.1. Chuẩn JMS 1.1 so với JMS 2.0/Jakarta Messaging

API durable truyền thống:

```java
// Kiểu API JMS 1.1: durable, non-shared.
TopicSubscriber sub =
        session.createDurableSubscriber(topic, "billing-orders-v1");
```

Mô hình JMS 2.0:

```java
// JMS 2.0: durable non-shared.
MessageConsumer nonShared =
        session.createDurableConsumer(topic, "billing-orders-v1");

// JMS 2.0: shared non-durable.
MessageConsumer shared =
        session.createSharedConsumer(topic, "audit-live-v1");

// JMS 2.0: shared durable.
MessageConsumer sharedDurable =
        session.createSharedDurableConsumer(topic, "billing-shared-v1");
```

Các fragment trên dùng biến `session` và `topic` đã được tạo phù hợp, chỉ minh họa tên API. Với Spring Boot 3.x, import chuẩn thuộc `jakarta.jms`; với JMS 2.0 cũ thuộc `javax.jms`. Tránh trộn client `javax` với interface `jakarta` vì tên class nhìn tương tự nhưng kiểu Java khác.

**Không phải provider nào có `ConnectionFactory` mang tên ActiveMQ cũng hỗ trợ API `createSharedDurableConsumer`.** Nhiều deployment ActiveMQ Classic 5.x tập trung vào JMS 1.1; Spring đặt `subscriptionShared=true` không thể tự bổ sung giao thức và khả năng server còn thiếu.

### 4.2. Ma trận chọn provider

| Stack | Mô hình durable non-shared | Shared durable | Phải xác minh |
| --- | --- | --- | --- |
| Spring Boot 3.x + Artemis Jakarta JMS client + Artemis broker | Có, với cấu hình đúng | **Có khi client/broker hỗ trợ JMS 2.0 shared APIs** | Version Artemis, client artifact `jakarta.jms`, subscription queue |
| Spring Framework 6.x + Apache Qpid JMS **phiên bản Jakarta-compatible** + Artemis AMQP 1.0 | Theo JMS provider | Theo mức hỗ trợ JMS 2.0/Jakarta provider | Mapping AMQP link/terminus, shared identity, durable semantics |
| ActiveMQ Classic 5.x client/broker thông dụng (JMS 1.1) | Có | **Không giả định hỗ trợ** | Kiểm tra API thực tế; không chỉ nhìn JAR tên ActiveMQ |
| ActiveMQ Classic 6.x và các tổ hợp client/broker mới | Theo version | **Cần xác minh tính năng thực tế** | Namespace Jakarta, broker capability, tests nhiều consumer |

Dù hai provider đều implement `jakarta.jms.ConnectionFactory`, behavior của shared durable subscription khi reconnect, tạo subscription không client ID, selector, session transaction và listener concurrency **vẫn phải được xác nhận bằng integration test**.

### 4.3. Broker Artemis không đồng nghĩa mọi client đều có cùng JMS capabilities

Artemis có thể hỗ trợ nhiều wire protocol: Core, AMQP 1.0, OpenWire, STOMP, MQTT. Khi Spring JMS dùng:

- **Artemis native JMS client**: thường nói **Artemis Core protocol**.
- **Qpid JMS provider**: nói **AMQP 1.0**.
- **ActiveMQ Classic JMS client**: thường nói **OpenWire**.

Shared durable ở phía Spring chỉ hoạt động nếu **JMS provider triển khai API cần thiết** và broker/protocol **có cách biểu diễn subscription tương thích**. Broker hỗ trợ MULTICAST không tự khiến một JMS 1.1 client hiểu JMS 2.0 shared subscription.

## 5. Cấu hình Artemis broker: address MULTICAST cho topic

Để tập trung vào subscription, provision topic address riêng trong Artemis `broker.xml`:

```xml
<!-- Fragment bên trong <addresses> của broker.xml -->
<address name="orders.events">
    <multicast/>
</address>
```

Đây là **địa chỉ multicast**, không phải queue ANYCAST đặt tên `orders.events`. Khi tạo durable subscription qua Artemis JMS provider, broker có thể tạo **queue bền vững liên quan tới subscription** với tên nội bộ theo quy tắc provider và cách nhận diện client. Không tự viết giả định về tên queue vật lý trong business code; hãy đọc console/management để xác định:

- Address: `orders.events`.
- Routing type: `MULTICAST`.
- Subscription queue(s) đã tạo.
- `durable`, consumer count, message count, delivering count.
- Định danh và selector của từng subscription.

Bảo mật của broker có thể yêu cầu quyền **create durable queue**, `consume`, hoặc `delete durable queue` khi unsubscribe. Trong môi trường production, không cấp quyền tạo/xóa vô hạn cho mọi service nếu chỉ cần consume một subscription đã provision.

### 5.1. Thứ tự quan trọng khi kiểm thử offline retention

```text
(1) Start subscriber lần đầu: broker tạo durable subscription.
(2) Đóng subscriber/connection nhưng KHÔNG unsubscribe.
(3) Publish event A, B khi subscriber offline.
(4) Start lại bằng đúng subscription identity.
(5) Nhận và commit A, B.
```

Nếu publish ở bước (3) **trước khi subscription được tạo lần đầu**, không thể dựa vào cơ chế durable để “truy xuất các message lịch sử chưa từng có subscription”. Durable lưu cho một subscription **đã được tạo**; nó không biến topic thành event log có replay từ đầu tùy ý.

Để kiểm tra sống qua restart **broker**, còn cần delivery mode persistent, storage/HA đúng và transaction commit được xác nhận. Chỉ test ứng dụng dừng/bật mà broker vẫn chạy **chưa chứng minh** dữ liệu sống qua crash broker.

## 6. Spring JMS: một durable **non-shared** subscription có định danh rõ ràng

Ví dụ Spring Boot 3.x và Spring Framework 6.x, client Artemis Jakarta và broker ngoài. Spring quản lý `JMS ConnectionFactory` qua `spring-boot-starter-artemis`; logic listener chỉ khai báo subscription.

### 6.1. Maven và cấu hình kết nối

Nếu project đã dùng Spring Boot BOM/parent:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-artemis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`application.yml` cho **external broker**:

```yaml
spring:
  artemis:
    mode: native
    broker-url: ${ARTEMIS_BROKER_URL:tcp://localhost:61616}
    user: ${ARTEMIS_USER}
    password: ${ARTEMIS_PASSWORD}
```

Dùng URL/DNS/secret thực tế của lab. Trong container, `localhost` là container ứng dụng, **không mặc nhiên** là broker container.

### 6.2. Factory cho non-shared durable topic

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.autoconfigure.jms
        .DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class NonSharedDurableJmsConfig {

    @Bean
    DefaultJmsListenerContainerFactory nonSharedDurableTopicFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        // Giữ các tùy chọn do Spring Boot quản lý: converter, QoS,
        // ErrorHandler/transaction nếu đã cấu hình trong Boot.
        configurer.configure(factory, connectionFactory);

        factory.setPubSubDomain(true);
        factory.setSubscriptionDurable(true);
        factory.setSubscriptionShared(false);
        factory.setClientId("billing-service-eu");
        factory.setConcurrency("1");

        // JMS transaction để ACK chỉ sau khi listener hoàn tất.
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

`DefaultJmsListenerContainerFactoryConfigurer` thuộc Spring Boot auto-configuration của nhánh ví dụ. Nếu dự án dùng Spring thuần, có thể cấu hình factory bằng các setter tương đương mà không dùng configurer của Boot.

**Ràng buộc:** `clientId="billing-service-eu"` phải **ổn định**, và chỉ một logical consumer/connection dùng định danh ấy tại một thời điểm. Không deploy ba replicas cùng factory này rồi set `concurrency="3"` để biến non-shared durable thành shared; đó là một mô hình khác.

### 6.3. Listener nhận message

```java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class BillingDurableListener {

    @JmsListener(
        destination = "orders.events",
        subscription = "billing-orders-v1",
        containerFactory = "nonSharedDurableTopicFactory"
    )
    public void handle(String json) {
        // Parse/validate JSON, xử lý nghiệp vụ idempotent.
        // Nếu ném exception với session transacted,
        // container có thể rollback và broker redeliver.
        System.out.println("Billing event: " + json);
    }
}
```

Cần `@EnableJms` trên một `@Configuration`/Spring Boot application nếu chưa được kích hoạt; Boot hỗ trợ JMS infrastructure nhưng không nên giả định listener annotation luôn được đăng ký khi config chưa bật.

`@JmsListener.subscription` chính là subscription name, **không phải queue name**. `destination` phải là Topic vì factory đã `setPubSubDomain(true)`.

**Không chạy đồng thời non-shared và shared listener cho cùng business requirement trừ khi đang thử có chủ đích.** Hai subscription khác tên trên một topic đều nhận message — dễ gây double processing nếu cùng cập nhật DB.

### 6.4. Lưu ý khi dùng connection cache

Spring Boot có thể wrap provider `ConnectionFactory` bằng `CachingConnectionFactory` hoặc sử dụng cấu hình pooling, tùy version/properties. Client ID là thuộc tính ở **connection level**, trong khi một số factory có thể cache/reuse kết nối. Khi có **nhiều durable non-shared listeners với clientID khác nhau**:

- Không giả định mọi listener có thể chia một physical JMS connection mà vẫn tự đặt hai client IDs khác nhau.
- Cần cấu hình/bean ConnectionFactory hoặc listener container tương ứng để kiểm soát ownership và clientId.
- Kiểm tra broker console: client ID thực tế, connection count và subscription identity.
- Đừng dùng một `setClientId` chung trên tất cả factory cho nhiều ứng dụng độc lập, trừ khi đó là mô hình single-active được điều phối.

## 7. Spring JMS: **shared durable** cho nhiều consumer và replica

Dùng provider hỗ trợ JMS 2.0/Jakarta shared durable. Cấu hình khác biệt là `subscriptionShared=true`, `subscriptionDurable=true` và **không ép clientId theo từng replica**.

### 7.1. Factory shared durable

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.autoconfigure.jms
        .DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class SharedDurableJmsConfig {

    @Bean
    DefaultJmsListenerContainerFactory sharedDurableTopicFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        factory.setPubSubDomain(true);
        factory.setSubscriptionDurable(true);
        factory.setSubscriptionShared(true);

        // Không setClientId khác nhau theo POD_NAME:
        // mục tiêu là cùng shared durable subscription.
        // Để provider/broker tạo shared identity không client ID
        // khi tổ hợp phiên bản hỗ trợ.
        factory.setConcurrency("2");
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

`setConcurrency("2")` yêu cầu container tạo hai consumer đồng thời cho một listener endpoint; nhiều instance ứng dụng còn có thể tăng tổng số consumer. Điều đó **chỉ hợp lệ** nếu provider hỗ trợ nhiều consumer trên shared durable subscription; nếu không, khởi động listener có thể lỗi.

Từ Spring `DefaultMessageListenerContainer`, shared durable subscription gắn với **cấu hình subscription + provider**, không phải một flag phía broker tự động phát sinh dù dùng nhầm queue domain.

### 7.2. Listener dùng tên subscription cố định giữa các replica

```java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class SharedBillingListener {

    @JmsListener(
        destination = "orders.events",
        subscription = "billing-shared-v1",
        containerFactory = "sharedDurableTopicFactory"
    )
    public void handle(String body) {
        System.out.printf(
            "handled by %s: %s%n",
            java.lang.management.ManagementFactory
                .getRuntimeMXBean().getName(),
            body);
    }
}
```

Khi triển khai nhiều replicas:

```text
Replica A: subscription="billing-shared-v1"
Replica B: subscription="billing-shared-v1"
Replica C: subscription="billing-shared-v1"

Không dùng:
Replica A: subscription="billing-shared-pod-A"
Replica B: subscription="billing-shared-pod-B"
Replica C: subscription="billing-shared-pod-C"
```

Nhóm thứ hai tạo **các subscription riêng**, mỗi nhóm nhận bản sao của event. Tên subscription là **tên logic của nhóm consumer**, không phải instance ID.

### 7.3. Shared durable và việc đặt client ID

Trong nhiều runtime, JMS client ID cần duy nhất trên từng active connection. Vì vậy:

- Một shared durable subscription **không client ID** là lựa chọn tự nhiên khi muốn nhiều replica cùng truy cập một subscription chung, nếu provider hỗ trợ.
- Nếu mỗi replica có một clientID riêng, **đừng mặc định** chúng vẫn tham gia một subscription cùng identity chỉ vì cùng `subscriptionName`.
- Nếu cả ba replica cố dùng cùng clientID, provider có thể từ chối do trùng client ID, bất kể `subscriptionShared=true`.
- Luôn **kiểm tra queue/subscription count trên broker**: nếu có ba durable queue thay vì một, bạn đang nhân bản luồng event.

Nếu tổ hợp provider/version **đòi hỏi client ID** cho loại subscription mà dự án đang dùng hoặc không hỗ trợ shared durable không client ID, hãy **fail fast** và chọn phương án tương thích. Không lặng lẽ fallback sang non-shared durable.

### 7.4. Lưu ý về tiêu thụ song song và thứ tự

Shared durable giúp tăng concurrency nhưng **không bảo đảm thứ tự xử lý toàn cục** giữa các consumer. Ví dụ:

```text
M1 -> consumer A (gọi DB chậm)
M2 -> consumer B (xử lý nhanh)
M2 commit trước M1
```

Nếu order event cần theo thứ tự `orderId`, cân nhắc message grouping/partition strategy và idempotency ở business layer; không chỉ giảm `max-concurrency` rồi khẳng định mọi event across cluster giữ thứ tự trong mọi lỗi/reconnect.

## 8. Producer topic: phát message persistent và theo dõi `eventId`

Cả non-shared durable và shared durable đều là **consumer-side subscription choices**. Publisher không cần biết số consumer, nhưng phải gửi tới **Topic** và có delivery mode phù hợp nếu muốn dữ liệu tồn tại qua broker restart.

```java
package example.jms;

import jakarta.jms.DeliveryMode;
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class TopicProducerConfig {

    @Bean
    JmsTemplate topicJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);

        // Bật explicit QoS để delivery mode được áp dụng khi send.
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        return template;
    }
}
```

```java
package example.jms;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class OrderEventPublisher {
    private final JmsTemplate topicJmsTemplate;

    public OrderEventPublisher(
            @Qualifier("topicJmsTemplate") JmsTemplate template) {
        this.topicJmsTemplate = template;
    }

    public String publish(String orderId) {
        String eventId = UUID.randomUUID().toString();
        String json = "{\"eventType\":\"OrderPlaced\","
                + "\"eventId\":\"" + eventId + "\","
                + "\"orderId\":\"" + orderId + "\"}";

        topicJmsTemplate.convertAndSend(
                "orders.events",
                json,
                message -> {
                    message.setStringProperty("eventId", eventId);
                    message.setStringProperty("eventType", "OrderPlaced");
                    return message;
                });

        return eventId;
    }
}
```

Đây là ví dụ **lab** với `orderId` giả định chỉ chứa ký tự an toàn; production phải serialize JSON bằng thư viện (Jackson) để tránh lỗi escaping/injection và validate schema. `eventId` dùng đối chiếu redelivery/dedup, không thay `JMSMessageID` của provider.

**PERSISTENT không tự bảo đảm exactly-once:** có thể producer mất phản hồi `send/commit`, retry tạo event trùng; consumer có thể xử lý DB xong nhưng JMS ACK thất bại. Thiết kế idempotency vẫn bắt buộc.

## 9. Lab: chứng minh ba semantics khác nhau bằng một topic

Chạy trên **Artemis broker riêng** đã provision address `orders.events` MULTICAST, Spring Boot 3.x/Artemis Jakarta JMS client phù hợp. Dùng **mỗi kịch bản một subscription name mới** để không làm bẩn kết quả từ bài test trước. Không chạy đồng thời các listener của những ví dụ production khác lên cùng topic khi đo.

### 9.1. Test A — non-shared durable giữ message lúc offline

1. Start app với `nonSharedDurableTopicFactory`, `clientId=billing-service-eu`, `subscription=billing-orders-v1`.
2. Kiểm tra broker đã tạo durable subscription.
3. Stop **listener container/app**, **không unsubscribe**.
4. Publish hai event `A`, `B` khi subscriber offline; producer gửi persistent.
5. Khởi động lại app với **đúng client ID, subscription name và topic**.
6. Xác minh đã nhận A/B và commit thành công.

Kỳ vọng: A/B được đưa vào backlog durable subscription khi consumer offline rồi được phát lại khi online. Nếu test không nhận, kiểm tra subscription đã **được tạo từ trước** bước publish và broker đang sử dụng đúng destination/routing.

### 9.2. Test B — shared durable chia tải, không broadcast trong nhóm

1. Start hai app instances (hoặc hai listener consumers) cùng `subscription=billing-shared-v1`, shared durable = true, không đặt clientId xung đột.
2. Kiểm tra broker chỉ có **một durable subscription logic** với hai consumers hoạt động.
3. Publish 100 event có `eventId` khác nhau.
4. Ghi lại cặp `eventId, consumerInstance` ở cả hai instances và số commit.
5. Hợp nhất tập ID đã xử lý; với lab không có lỗi/retry, kỳ vọng **100 event độc nhất**, không phải 200.
6. Stop cả hai; publish thêm 10 event; start lại hai app cùng identity; kiểm tra 10 event đó được xử lý.

Không yêu cầu phân phối **50/50** giữa hai consumer — broker scheduling/credit/prefetch và tốc độ handler có thể lệch nhau. Kết luận đúng là **một subscription được chia tải**, không phải bảo đảm round-robin tuyệt đối.

### 9.3. Test C — hai durable subscription khác tên đều nhận bản sao

1. Tạo subscription `billing-v1` và `analytics-v1` trên `orders.events`.
2. Start một consumer cho mỗi subscription.
3. Publish một event `E1`.
4. Kỳ vọng cả billing và analytics đều nhận `E1` (mỗi subscription một bản sao).
5. So sánh với test B: hai shared consumers **trong cùng subscription** không tương đương hai subscription khác nhau.

### 9.4. Test D — provider không hỗ trợ shared durable

Chuyển qua provider/client không triển khai JMS 2.0 shared durable, nhưng giữ `subscriptionShared=true`:

- Khởi động listener có thể thất bại khi container cố tạo shared consumer.
- Một lỗi như `UnsupportedOperationException`, `JMSException` hoặc provider-specific exception phải được ghi nhận **như không tương thích**, không xử lý bằng cách đổi lại `pubSubDomain=false`.
- Nếu code tự fallback, test phải xác minh fallback đã được **phê duyệt về semantics**; tốt hơn là fail startup với thông báo rõ: “shared durable topic subscription required”.

Đây là **test contract/provider**, không phải một test “thử chạy đến khi hết lỗi”.

## 10. Lập trình một consumer JMS trực tiếp để kiểm tra khả năng provider

Spring che giấu lời gọi tạo consumer ở bên dưới listener container. Khi cần xác định provider có hỗ trợ shared durable hay không, có thể viết phép thử API ngắn, độc lập với Spring:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Session;
import jakarta.jms.Topic;

public final class SharedDurableCapabilityProbe {

    public static void check(ConnectionFactory factory) throws Exception {
        try (Connection connection = factory.createConnection()) {
            Session session = connection.createSession(
                    false, Session.CLIENT_ACKNOWLEDGE);
            Topic topic = session.createTopic("orders.events");

            // API Jakarta Messaging/JMS 2.0:
            MessageConsumer consumer =
                    session.createSharedDurableConsumer(
                            topic, "capability-probe-v1");

            connection.start();
            Message message = consumer.receive(500);

            if (message != null) {
                System.out.println("Received: "
                        + message.getJMSMessageID());
                message.acknowledge();
            }

            consumer.close();
            // Không unsubscribe: để lại subscription durable cố ý
            // chỉ cho lab kiểm tra offline retention; dọn bằng
            // quy trình cleanup riêng sau test.
        }
    }
}
```

Ví dụ này **chỉ chứng minh client có thể gọi API tạo shared durable consumer và broker chấp nhận**, chưa chứng minh nhiều connection cùng dùng chung backlog. Để kiểm chứng shared thực sự, chạy đồng thời **hai connection** dùng cùng subscription name và so sánh tập `eventId`, số subscription queues trên broker.

**Cẩn trọng:** nếu giữ tên `capability-probe-v1` giữa nhiều test hoặc thay selector/topic, có thể gây xung đột durable subscription tồn tại từ lần trước. Dùng namespace lab/unique test ID và dọn subscription bằng operation có quyền sau khi chắc chắn không còn backlog cần giữ.

### 10.1. Probe về unique client ID

Đối với durable non-shared, thử hai JMS connections đồng thời với cùng `setClientID("billing-service-eu")` trên provider:

```java
// Pseudocode: chỉ thực hiện trong LAB.
Connection c1 = factory.createConnection();
c1.setClientID("billing-service-eu");

Connection c2 = factory.createConnection();
c2.setClientID("billing-service-eu"); // thường bị provider từ chối
```

Mục tiêu là hiểu ràng buộc **client identifier uniqueness**, không tạo cách “giành” active durable subscriber bằng cách retry liên tục. Trong Spring, container quản lý connection nên lỗi có thể xuất hiện khi listener khởi động, không nhất thiết ngay trong constructor factory.

## 11. Spring listener concurrency, session và ACK khi shared

### 11.1. `subscriptionShared=true` không phải tính năng cân bằng tải Spring tự tạo

Spring chỉ yêu cầu JMS provider tạo shared consumer theo cấu hình. Chính broker/protocol quyết định dispatch và xử lý redelivery. Nếu provider không hỗ trợ, tăng `factory.setConcurrency("2-8")` cũng không tạo shared durable subscription hợp lệ.

| Cấu hình | Tác động | Điều không được suy |
| --- | --- | --- |
| `pubSubDomain=true` | Destination là Topic | Tự động durable |
| `subscriptionDurable=true` | Yêu cầu durable subscription | Tự động shared |
| `subscriptionShared=true` | Yêu cầu shared subscription | Provider nào cũng hỗ trợ |
| `subscription="billing-shared-v1"` | Chỉ ra subscription name | Tự động tránh trùng tên với app khác |
| `setClientId(...)` | Cấu hình client ID trên connection | Cho phép nhiều connection dùng chung một ID |
| `concurrency="2"` | Container yêu cầu hai consumers/threads | Bảo đảm event chia đều hoặc xử lý đúng một lần |
| `sessionTransacted=true` | JMS transaction local cho listener | Atomically commit cả DB ngoài JMS |

### 11.2. Transaction và redelivery trong shared durable

Giả sử `M1` đến consumer A:

```text
Broker -> shared durable "billing-shared-v1"
        -> consumer A: M1
A: cập nhật DB
A: crash trước JMS commit
Broker: M1 chưa ACK/commit -> redelivery theo policy
        -> consumer B: có thể nhận M1
```

Dù subscription shared, JMS local transaction không tự gộp DB transaction. Nếu DB đã commit và M1 redeliver sang B, B cần tra cứu `eventId` để tránh side effect trùng.

Với Spring `@JmsListener` và `setSessionTransacted(true)`, listener ném exception thường khiến container rollback JMS session để broker retry theo policy. **Đừng bắt exception rồi return bình thường** nếu nghiệp vụ chưa hoàn tất; container có thể commit/ACK. Nếu cần DLQ/quarantine, cấu hình retry/redelivery của broker và phân loại lỗi có kiểm soát.

### 11.3. Thứ tự, slow consumer và backlog

- Shared subscription xử lý song song có thể **đảo thứ tự hoàn tất** giữa consumer.
- Một consumer chậm có thể giữ message in-flight; những consumer khác tiếp tục.
- Khi **mọi consumer shared durable offline**, backlog tiếp tục tích tụ và có thể gây **paging** trên Artemis.
- Nếu một deployment tạo **subscription riêng per-pod**, lượng backlog và journal/page references tăng theo số subscription, không phải chỉ tăng concurrency.
- Khi thu hồi consumer, `close` không đồng nghĩa unsubscribe/delete durable subscription; backlog còn lại vẫn cần owner vận hành.

## 12. Lỗi thực tế và cách xác định đúng tầng

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Test chạy như queue nhưng không có durable subscription | Quên `pubSubDomain=true` | Kiểm tra destination object và MULTICAST/queue trên broker |
| Mọi pod nhận cùng event | Mỗi pod tạo subscription riêng, clientID/subName khác | Broker console: số durable queues/subscriptions |
| Replica thứ hai không start listener | Non-shared durable hoặc duplicate `clientId` | Provider exception, active connections/consumer count |
| Dừng app rồi publish; start lại không nhận | Subscription chưa tạo trước đó, đổi clientID/name, non-durable | So sánh identity trước/sau restart |
| Shared durable chạy trên Artemis native nhưng lỗi qua Classic client | Client/provider không hỗ trợ JMS 2.0 shared API | Provider dependency, namespace, protocol, capability probe |
| Đổi selector làm app fail khởi động | Subscription cũ có selector/topic khác, không thể thay động | Broker subscription metadata, migration plan |
| Queue “mất” sau chuyển broker | Subscription thuộc broker/topology cũ | HA/migration, persistence và broker identity |
| Backlog tăng dù worker chạy | Consumer xử lý chậm, rollback/redelivery, paging hoặc lỗi không ACK | Queue metrics, consumer count, DLQ, transaction logs |
| Không thấy `@JmsListener` được chạy | `@EnableJms` thiếu, container không start, connection error | Listener registration, startup/health logs |
| Cấu hình Boot bị bỏ qua | Tự tạo `ConnectionFactory` hoặc sai active profile | Bean actual type, profile, URL không log secret |
| Một message xử lý hai lần | Redelivery sau lỗi ACK/JMS commit, producer duplicate | Business `eventId`, idempotency DB |

### 12.1. Đặc biệt tránh “fix” lỗi bằng cách đổi sang queue domain

Nếu topic shared durable không hoạt động vì provider thiếu API, đổi `setPubSubDomain(false)` có thể khiến listener hoạt động trên **một queue khác cùng tên**. Nó làm mất tính chất topic broadcast tới **các logical subscription khác**, không phải cách sửa tương đương.

Phương án hợp lệ cần được thiết kế: nâng provider/broker, dùng Artemis JMS native phù hợp hoặc **tạo một subscription consumer bridge** đưa message topic vào một queue công việc được quản lý riêng. Đây là thay đổi kiến trúc, không phải chỉ đổi một boolean.

## 13. Khi migration giữa Classic và Artemis

### 13.1. Migration phải xét cả namespace và feature set

- **ActiveMQ Classic 5.x** chủ yếu chạy JMS 1.1 trong nhiều deployment Java cũ (`javax.jms`). Durable non-shared là mô hình thường gặp; không mặc nhiên có `createSharedDurableConsumer`.
- **Spring Boot 3.x** sử dụng Jakarta Messaging (`jakarta.jms`), nên không thể dùng trực tiếp một client chỉ implement `javax.jms`.
- **Artemis Jakarta JMS client** cung cấp JMS API phù hợp trong tổ hợp version hỗ trợ shared durable.
- Dùng Classic OpenWire client trỏ Artemis broker không tự chuyển client đó thành Artemis Core JMS provider có đầy đủ shared subscription semantics.

Một kế hoạch migration cần trả lời:

1. Subscription cũ mang identity gì (`clientId + subscriptionName`)?
2. Backlog của subscription cũ nằm trên broker/store nào?
3. Sau cutover, subscription mới bắt đầu tại thời điểm nào; có cần replay backlog không?
4. Shared durable có được hỗ trợ bởi **client và broker** đích không?
5. Có thay selector/topic/clientID/durable flag hoặc số replica đồng thời không?
6. Cách tránh double processing trong giai đoạn dual-run?
7. Khi nào mới được unsubscribe/delete subscription cũ?

**Không mount store KahaDB của Classic vào Artemis** để chuyển backlog subscription; hai sản phẩm dùng hệ lưu trữ khác. Cần quy trình migration/replay có kiểm tra event ID.

### 13.2. Khi provider chỉ có non-shared durable

Nếu yêu cầu là **một logical subscription** nhưng muốn scale nhiều workers, có thể dùng:

```text
Topic -> một durable non-shared consumer/bridge
      -> queue công việc chung -> nhiều workers
```

Trade-off: bridge thành thành phần cần quản lý throughput, persistence, transaction và failover. Đây là **phương án kiến trúc** khi shared durable không sẵn có, không phải triển khai mặc định bằng `@JmsListener`. Cần tránh cửa sổ “đã ACK topic nhưng chưa gửi vào queue”; dùng transaction cùng broker khi thích hợp hoặc outbox/reliable forwarding.

## 14. Checklist nghiệm thu

- [ ] Đã xác định ứng dụng nhận **Topic**, và `pubSubDomain=true`.
- [ ] Mục đích đã rõ: durable giữ offline backlog; shared cho phép nhiều active consumers cùng một subscription.
- [ ] `@JmsListener.subscription` có tên logic ổn định, không dựa vào pod UID.
- [ ] Với durable non-shared, clientID/subscription name ổn định qua restart và **chỉ một consumer active**.
- [ ] Với shared durable multi-replica, không vô tình tạo clientID khác nhau khiến mỗi replica có subscription riêng.
- [ ] Không cố dùng cùng clientID trên các active connections nếu provider yêu cầu uniqueness.
- [ ] Kiểm tra **JMS provider version**, `javax`/`jakarta` namespace và hỗ trợ `createSharedDurableConsumer`.
- [ ] Broker Artemis có MULTICAST address, subscription queues và quyền phù hợp.
- [ ] Đã tạo durable subscription **trước** giai đoạn publish offline cần retention.
- [ ] Không nhầm nhiều shared consumers với nhiều subscriptions độc lập.
- [ ] Có test hai active consumer, đo **tập eventId**, không đòi chia đều 50/50.
- [ ] Có test stop-all/publish/start-all, xác minh backlog được nhận đúng.
- [ ] Đã kiểm thử ném exception/crash để hiểu rollback/redelivery giữa các consumer.
- [ ] Listener có JMS transaction/ACK rõ ràng và business idempotency.
- [ ] Thay selector, subscription name hoặc clientID có runbook migration backlog.
- [ ] Không unsubscribe durable subscription chỉ để “dọn” mà chưa kiểm tra pending messages.
- [ ] Nếu migration Classic ↔ Artemis, đối chiếu client API, wire protocol và store riêng.

## 15. Câu hỏi tự kiểm tra

1. Tại sao ba replica dùng ba `subscriptionName` khác nhau trên cùng topic đều có thể nhận cùng một event?
2. Durable non-shared và shared durable khác nhau ở hai trục nào?
3. Vì sao `concurrency="3"` không tự hợp pháp hóa một non-shared durable subscription?
4. Với hai Spring Boot replicas, đặt `clientId=pod-1` và `clientId=pod-2` nhưng cùng `subscriptionName` có chắc chắn tạo một shared durable subscription không?
5. Tại sao một client chỉ hỗ trợ JMS 1.1 không thể được Spring “nâng cấp” thành shared durable bằng `setSubscriptionShared(true)`?
6. Nếu publish event khi durable subscription chưa được tạo lần đầu, có được broker giữ message cho subscription tương lai không?
7. Vì sao `pubSubDomain=true` là điều kiện cốt lõi?
8. Shared durable có bảo đảm đúng một lần xử lý business khi consumer A crash sau DB commit, trước JMS commit không?
9. Đổi selector trên durable subscription đang có backlog có thể làm thay đổi điều gì?
10. Trường hợp nào bạn nên tách topic subscription và queue công việc qua một bridge?

**Gợi ý:** (1) đó là các subscription độc lập, mỗi subscription có bản sao; (2) giữ backlog offline và chia active consumers; (3) API non-shared chỉ có một active consumer; (4) không, clientID có thể là phần identity; (5) thiếu API/capability của provider; (6) không, subscription cần được tạo từ trước; (7) để tạo topic subscriber chứ không phải queue consumer; (8) không, còn redelivery/idempotency; (9) provider có thể reject/recreate hoặc thay tập message, cần migration; (10) khi provider không hỗ trợ shared durable nhưng cần chia tải nhiều workers.

## 16. Tài liệu tham khảo

- [Spring Framework — JMS Annotated Endpoint Methods](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, `subscription` và cấu hình listener container.
- [Spring Framework — JMS Listener Container Features](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): durable subscribers, shared subscriptions, transaction và lifecycle.
- [Spring API — DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): các setter của listener container factory.
- [Jakarta Messaging API — Session](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session): durable/shared consumers và `unsubscribe`.
- [Apache ActiveMQ Artemis — JMS](https://artemis.apache.org/components/artemis/documentation/latest/using-jms.html): JMS/Jakarta client và durable subscriptions.
- [Apache ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): multicast address, queue và topic subscription.
- [Apache ActiveMQ Classic — How do Durable Subscribers Work](https://activemq.apache.org/components/classic/documentation/how-do-durable-subscribers-work): durable non-shared model trong Classic.
- [Spring Boot — JMS Messaging](https://docs.spring.io/spring-boot/reference/messaging/jms.html): Artemis starter và auto-configuration.

> **Ghi nhớ:** **Durable** giữ trạng thái subscription và backlog khi consumer offline; **shared** cho phép nhiều consumer chia **cùng một subscription**; `clientId` và `subscriptionName` quyết định identity, không phải nhãn trang trí. Trong Spring JMS, phải cấu hình **Topic + subscriptionDurable + subscriptionShared** đúng mục tiêu, rồi xác nhận provider hỗ trợ API, broker có **một hay nhiều subscription queue**, kiểm chứng offline backlog và idempotency khi redelivery.
