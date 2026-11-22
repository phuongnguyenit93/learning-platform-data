# Cấu hình Classic qua spring.activemq.* và Artemis qua spring.artemis.*

> **Chương:** Spring Boot  
> **Phạm vi:** Cấu hình kết nối Apache ActiveMQ Classic và ActiveMQ Artemis với Spring Boot; phân biệt hai namespace property, dependency, auto-configuration và các property Spring JMS dùng chung. Ví dụ đặt trên **Spring Boot 3.x, Java 17+ và Jakarta Messaging (`jakarta.jms`)**. Spring Boot 2.x dùng `javax.jms` và có khác biệt dependency/API; không trộn hai namespace.

## 1. Vấn đề: cùng Spring JMS, khác provider

Giả sử Order Service phát lệnh `InvoiceRequested` qua `JmsTemplate` tới queue `billing.commands`, còn Billing Service xử lý bằng `@JmsListener`. Ở tầng nghiệp vụ, code Spring JMS có thể giống nhau. Nhưng để kết nối chính xác phải chọn được **client provider**, **broker endpoint** và **destination semantics**.

| Nội dung | ActiveMQ Classic | ActiveMQ Artemis |
|---|---|---|
| Starter với Spring Boot 3.x | `spring-boot-starter-activemq` | `spring-boot-starter-artemis` |
| Namespace cấu hình provider | `spring.activemq.*` | `spring.artemis.*` |
| URL | `spring.activemq.broker-url` | `spring.artemis.broker-url` |
| Credentials | `spring.activemq.user/password` | `spring.artemis.user/password` |
| Broker riêng | Classic broker qua transport URL tương thích | `spring.artemis.mode=native` và Artemis broker |
| Hạ tầng Spring JMS | `spring.jms.*` | `spring.jms.*` |
| Kiểu JMS ở Boot 3.x | `jakarta.jms.*` và Classic Jakarta client phù hợp | `jakarta.jms.*` và Artemis Jakarta client phù hợp |
| Cấu trúc broker | Queue/topic và destination policy Classic | Address, anycast/multicast, queue và address settings |

**Không thể chuyển từ Classic sang Artemis chỉ bằng đổi host trong URL.** Spring Boot chọn auto-configuration dựa vào **dependency/classpath và các bean**; giao thức client, cấu hình queue/topic và security của broker cũng phải phù hợp.

### 1.1. Luồng cấu hình

~~~mermaid
flowchart TD
    D["Maven/Gradle: JMS starter"] --> P{"Provider dependency"}
    P -->|Classic| A["Bind spring.activemq.*"]
    P -->|Artemis| R["Bind spring.artemis.*"]
    A --> F["JMS ConnectionFactory"]
    R --> F
    F --> B["Spring Boot JMS auto-configuration"]
    B --> T["JmsTemplate"]
    B --> L["JMS listener container factory"]
    T --> Q["Broker: queue/topic"]
    Q --> L
    L --> C["Method @JmsListener"]
~~~

Sơ đồ là cách hiểu chức năng; auto-configuration có các điều kiện về bean/classpath nên bean tự khai báo có thể thay thế cấu hình mặc định.

## 2. Chọn dependency đúng trước khi sửa application.yml

### 2.1. Classic: spring-boot-starter-activemq

Trong dự án đã có Spring Boot parent/BOM, thêm một dependency:

~~~xml
<!-- pom.xml: dành cho ứng dụng dùng ActiveMQ Classic -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-activemq</artifactId>
</dependency>
~~~

Spring Boot quản lý phiên bản client phù hợp với nhánh đang dùng. Với Boot 3.x, mã ứng dụng phải dùng `jakarta.jms.ConnectionFactory`, `jakarta.jms.Message`… và bản ActiveMQ Classic client hỗ trợ Jakarta. Đừng thêm ngẫu nhiên một `activemq-client` cũ sử dụng `javax.jms` gây lỗi class/interface.

### 2.2. Artemis: spring-boot-starter-artemis

~~~xml
<!-- pom.xml: dành cho ứng dụng dùng Artemis -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-artemis</artifactId>
</dependency>
~~~

Starter đưa Artemis JMS client và tích hợp auto-configuration phù hợp. Nó **không có nghĩa** broker production sẽ tự khởi chạy trong JVM của ứng dụng. Với broker Artemis chạy riêng, dùng `spring.artemis.mode=native`.

### 2.3. Vì sao không tự thêm cả hai starter?

Nếu cả Classic và Artemis client cùng trên classpath, một số auto-configuration có thể cạnh tranh điều kiện tạo `ConnectionFactory`. Không có bảo đảm Boot sẽ tự sinh hai connection factory độc lập và định tuyến chính xác cho mọi `@JmsListener`.

Ba lựa chọn an toàn:

1. **Một provider starter cho mỗi ứng dụng/artifact.** Cách phổ biến và dễ kiểm tra.
2. Dùng **Maven build profile/module riêng** để đóng gói artifact Classic hoặc Artemis. Spring profile runtime chỉ đổi properties, **không xóa dependency** đã có trong JAR.
3. Khi thực sự phải truy cập hai broker **đồng thời**, tự khai báo hai `ConnectionFactory`, đặt `@Qualifier` cho `JmsTemplate`/container factory và viết integration test cho từng route. Đây là bài toán multi-provider, không phải mặc định của hai namespace.

## 3. Classic: spring.activemq.* cấu hình như thế nào?

Với artifact dùng Classic starter và broker Classic lắng nghe `tcp://localhost:61616`:

~~~yaml
# application.yml, ứng dụng Classic
spring:
  activemq:
    broker-url: tcp://localhost:61616
    user: ${ACTIVEMQ_USER}
    password: ${ACTIVEMQ_PASSWORD}
  jms:
    pub-sub-domain: false
    listener:
      concurrency: 2
      max-concurrency: 4
~~~

Biến môi trường phải được cấp từ môi trường/secret manager. Không commit username/password production vào repository.

| Property | Công dụng | Điều cần xác minh |
|---|---|---|
| `spring.activemq.broker-url` | URL client Classic sử dụng để kết nối broker | Giao thức/port và hostname đúng từ process ứng dụng |
| `spring.activemq.user` | Tên đăng nhập JMS connection | Quyền send/consume trên destination |
| `spring.activemq.password` | Mật khẩu tương ứng | Không lộ qua log/config dump |
| `spring.jms.pub-sub-domain` | Default queue hoặc topic cho các Spring JMS component tôn trọng setting này | False đối với queue; không dùng true nếu vẫn gửi queue |
| `spring.jms.listener.concurrency` | Concurrency listener ban đầu | Số consumer kết nối, thứ tự xử lý, DB capacity |
| `spring.jms.listener.max-concurrency` | Giới hạn mở rộng concurrency | Không phải broker queue capacity hay worker partition |

### 3.1. Dạng application.properties

~~~properties
spring.activemq.broker-url=tcp://localhost:61616
spring.activemq.user=${ACTIVEMQ_USER}
spring.activemq.password=${ACTIVEMQ_PASSWORD}
spring.jms.pub-sub-domain=false
spring.jms.listener.concurrency=2
spring.jms.listener.max-concurrency=4
~~~

Khi viết cấu hình, chọn YAML **hoặc** properties theo dự án; đừng có hai giá trị mâu thuẫn từ nhiều config source mà không biết thứ tự precedence.

### 3.2. Failover Transport của Classic

Classic JMS client có Failover Transport URL. Ví dụ khi broker topology đã được thiết kế HA phù hợp:

~~~yaml
spring:
  activemq:
    broker-url: "failover:(tcp://classic-a:61616,tcp://classic-b:61616)?randomize=false"
~~~

**Failover URL không tự cấu hình replication/HA cho broker.** Client có thể reconnect nhưng kết quả `send/commit` bị timeout vẫn có thể là *unknown*. Producer cần giữ event ID ổn định và consumer cần idempotency khi retry.

Đây là cú pháp transport của Classic; **không sao chép nguyên** vào `spring.artemis.broker-url` của Artemis.

## 4. Artemis: spring.artemis.* với broker native

Ứng dụng dùng Artemis starter và một broker Artemis chạy độc lập:

~~~yaml
# application.yml, ứng dụng Artemis
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: ${ARTEMIS_USER}
    password: ${ARTEMIS_PASSWORD}
  jms:
    pub-sub-domain: false
    listener:
      concurrency: 2
      max-concurrency: 4
~~~

| Property | Ý nghĩa | Cạm bẫy |
|---|---|---|
| `spring.artemis.mode=native` | Chọn broker **chạy ngoài ứng dụng** | Đừng vô tình chạy embedded khi muốn kết nối production |
| `spring.artemis.broker-url` | Endpoint Artemis client | Broker phải có acceptor/protocol phù hợp |
| `spring.artemis.user` | User Artemis | Cần quyền consume/send/create theo ACL |
| `spring.artemis.password` | Secret của connection | Không hard-code trong source |
| `spring.jms.*` | Hành vi Spring JMS dùng chung | Không thay cho address settings của broker |

### 4.1. Native khác embedded ở đâu?

**Native** có broker riêng, client kết nối qua transport; dễ tách vòng đời ứng dụng và broker, phù hợp môi trường chia sẻ broker. **Embedded** chỉ có khi version/dependency server và chế độ cho phép; broker nằm trong cùng JVM, hữu ích trong một số test nhưng không tự bảo đảm persistence/HA production.

Trong môi trường tích hợp, đặt `spring.artemis.mode=native` **tường minh** tránh suy luận sai từ dependency hoặc behavior tự chọn mode.

### 4.2. Queue Artemis phải phù hợp address/routing

Artemis core sử dụng **address → routing type → queue**. Đối với JMS queue tên `billing.commands`, ví dụ provision trước anycast queue tại broker:

~~~xml
<!-- Fragment trong <addresses> của Artemis broker.xml -->
<address name="billing.commands">
  <anycast>
    <queue name="billing.commands" durable="true"/>
  </anycast>
</address>
~~~

Cấu hình Spring `@JmsListener(destination="billing.commands")` **không tự bảo đảm** broker có physical queue đúng routing. Nếu `auto-create-queues` hoặc `auto-create-addresses` bị tắt, resource/role không tồn tại có thể khiến client bị từ chối. Dùng management để xác nhận queue thực, không chỉ nhìn tên trong annotation.

Một topic JMS đòi routing multicast/subscription phù hợp; không dùng Classic `policyEntry` để cấu hình Artemis.

## 5. Nhóm spring.jms.* dùng chung cho Classic và Artemis

Spring JMS vận hành dựa trên `ConnectionFactory` đã được Boot tạo. Các property `spring.jms.*` ở Boot 3.x chủ yếu điều khiển template/listener/cache, **không điều khiển broker storage, DLQ hay topology**.

| Property | Tác dụng |
|---|---|
| `spring.jms.pub-sub-domain` | Default queue (false) hoặc topic (true) cho component Spring JMS tương ứng |
| `spring.jms.listener.concurrency` | Số listener consumers ban đầu theo container |
| `spring.jms.listener.max-concurrency` | Số consumers tối đa khi container scaling |
| `spring.jms.listener.auto-startup` | Có start listener container khi context khởi tạo |
| `spring.jms.listener.receive-timeout` | Thời gian receive timeout của listener infrastructure, không phải broker send timeout |
| `spring.jms.cache.enabled` | Bật cơ chế Spring JMS caching khi auto-configuration dùng nó |
| `spring.jms.cache.session-cache-size` | Số session cache theo factory |

Một cấu hình minh họa:

~~~yaml
spring:
  jms:
    cache:
      enabled: true
      session-cache-size: 5
    listener:
      auto-startup: true
      concurrency: 2
      max-concurrency: 4
~~~

### 5.1. Cache không phải pool, và cả hai không tạo queue

`CachingConnectionFactory` có thể tái sử dụng một số connection/session/client resource để giảm overhead. Một **pooled JMS connection factory** có cơ chế pooling khác và có thể được bật bằng các property provider-specific ở phiên bản tương ứng, với dependency pool bổ sung (ví dụ `org.messaginghub:pooled-jms` khi stack hỗ trợ).

Đừng cùng lúc bật cache/pool chỉ vì throughput tăng trong một benchmark ngắn. Cần kiểm tra timeout, limit của session, close lifecycle, transaction và số lượng connection thực tế khi nhiều `@JmsListener` chạy.

### 5.2. Spring JMS không ghi cấu hình broker

Dù cấu hình `spring.jms.listener.max-concurrency=12`, nó **không**:

- Tạo 12 queue, bảo đảm 12 partition hoặc global FIFO.
- Bật Classic KahaDB/`destinationPolicy`/`deadLetterStrategy`.
- Đặt Artemis `address-settings`/journal/paging/HA policy.
- Bảo đảm downstream database được commit đúng một lần.
- Điều chỉnh quyền security manager ở broker.

Các chính sách này phải được cấu hình trên broker và kiểm thử độc lập.

## 6. Java Spring Boot 3.x: producer và listener dùng chung

Sau khi có đúng **một** provider starter, có thể viết code Spring JMS **không import factory native** của Classic hay Artemis. Boot sẽ inject bean `ConnectionFactory` phù hợp.

### 6.1. Spring Boot application

~~~java
package example.messaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class MessagingApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
~~~

`@EnableJms` bật hạ tầng xử lý `@JmsListener`. Không cần tự tạo một `ConnectionFactory` mới nếu để Boot auto-configure từ provider starter.

### 6.2. Producer qua JmsTemplate

~~~java
package example.messaging;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoicePublisher {

    private final JmsTemplate jmsTemplate;

    public InvoicePublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publishInvoiceRequested(String eventId, String orderId) {
        // Để tập trung JMS, dùng String -> TextMessage theo converter mặc định.
        String json = "{\"eventId\":\"" + eventId
                + "\",\"orderId\":\"" + orderId + "\"}";

        jmsTemplate.convertAndSend(
                "billing.commands",
                json,
                message -> {
                    message.setStringProperty("eventId", eventId);
                    message.setJMSType("invoice.requested.v1");
                    return message;
                });
    }
}
~~~

Ý nghĩa:

- `JmsTemplate` sử dụng `ConnectionFactory` Boot cung cấp; cùng code có thể chạy với Classic/Artemis nếu destination semantics và dependency đúng.
- `convertAndSend` với `String` và default `SimpleMessageConverter` thường tạo `TextMessage`. Đừng suy rằng một Java object tùy ý được tự JSON-serialize an toàn.
- `JMSType` là header do ứng dụng đặt. `eventId` là property/ID nghiệp vụ cần được giữ qua retry để chống duplicate.
- `send()` hoàn tất không có nghĩa consumer đã xử lý hoặc database Billing đã commit.

Ví dụ JSON nối chuỗi là **minh họa**; production nên dùng serializer chuẩn để escape đúng ký tự từ `eventId`/`orderId`.

### 6.3. Consumer đơn giản

~~~java
package example.messaging;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class InvoiceListener {

    @JmsListener(destination = "billing.commands")
    public void onMessage(
            String payload,
            @Header("eventId") String eventId) {

        System.out.println("Received eventId=" + eventId
                + ", payload=" + payload);
        // Demo chưa ghi database.
    }
}
~~~

Header `eventId` phải được producer đặt; nếu có nguồn gửi khác, kiểm tra trường bắt buộc và schema/selector đúng.

**Không chạy nhiều listener minh họa cùng queue rồi kỳ vọng mỗi listener nhận tất cả message.** Các JMS queue consumers cạnh tranh nhau, không tự fan-out.

## 7. Cấu hình transaction của listener theo mục tiêu nghiệp vụ

Các phương thức `@JmsListener` thực hiện nghiệp vụ có thể ném exception hoặc crash sau khi nhận. Không nên mặc định ACK của mọi listener đang được gửi **sau** database commit nếu chưa chỉ rõ transaction.

Trong Spring Boot 3.x, ta có thể tạo factory riêng dùng local JMS transaction:

~~~java
package example.messaging;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class ListenerTransactionConfig {

    @Bean("txJmsListenerFactory")
    public DefaultJmsListenerContainerFactory txJmsListenerFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        configurer.configure(factory, connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-4");
        return factory;
    }
}
~~~

Listener dùng container factory đó:

~~~java
package example.messaging;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class TransactionalInvoiceListener {

    @JmsListener(
            destination = "billing.commands",
            containerFactory = "txJmsListenerFactory")
    public void handle(String payload) {
        processIdempotently(payload);
        // Return: container có thể commit JMS session.
        // Ném exception: container rollback theo transaction policy.
    }

    private void processIdempotently(String payload) {
        // Production: ghi unique eventId vào inbox + thay đổi business
        // trong cùng DB transaction; hàm demo chỉ in log.
        System.out.println("Business processed: " + payload);
    }
}
~~~

**Chọn một trong `InvoiceListener` và `TransactionalInvoiceListener` khi chạy test**, không để hai lớp cùng hoạt động nếu mục tiêu là xác minh một luồng nhận duy nhất.

### 7.1. Giới hạn của local JMS transaction

- `factory.setSessionTransacted(true)` quy định local JMS receive transaction.
- Nó **không tự** gộp thay đổi SQL database vào cùng transaction JMS.
- Nếu DB đã commit nhưng process chết trước JMS commit, broker có thể giao lại message.
- Consumer cần unique `eventId`/inbox transaction để không tạo hóa đơn trùng.
- Nếu muốn tích hợp JTA/XA, phải cấu hình manager/resources và kiểm tra chuẩn transaction riêng; không suy ra từ mỗi `@Transactional`.
- Concurrency nhiều hơn một consumer có thể thay đổi thứ tự hoàn thành. Không xem một queue với 4 consumers là FIFO xử lý toàn cục.

Khi dùng factory tùy biến, gọi Boot configurer trước rồi đặt rõ `sessionTransacted`/`concurrency` nếu muốn các override đó có hiệu lực.

## 8. Queue và topic: tác động của spring.jms.pub-sub-domain

### 8.1. Queue là trường hợp thông dụng

~~~yaml
spring:
  jms:
    pub-sub-domain: false
~~~

Spring JMS sử dụng queue semantics ở các component phù hợp: nhiều consumers cùng queue chia công việc; một message thường do một consumer hoàn tất.

### 8.2. Topic là publish-subscribe

~~~yaml
spring:
  jms:
    pub-sub-domain: true
~~~

Dùng default topic khi ứng dụng thật sự thiết kế các destination của nó là topic. **Không bật global true** nếu producer `billing.commands` vẫn muốn gửi vào queue.

Khi ứng dụng cần dùng đồng thời queue và topic, hãy cấu hình template dành riêng cho topic:

~~~java
package example.messaging;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class TopicConfig {
    @Bean("topicJmsTemplate")
    public JmsTemplate topicJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate t = new JmsTemplate(connectionFactory);
        t.setPubSubDomain(true);
        return t;
    }
}
~~~

Dùng `@Qualifier("topicJmsTemplate")` để inject nơi phát event topic. Topic listener cũng cần một listener factory với `setPubSubDomain(true)`, không chỉ tạo template bên producer.

**Topic subscriber non-durable** offline lúc publish không có backlog lịch sử. Nếu cần nhận sau khi offline, cần durable subscription hợp lệ. Trong Artemis, destination topic phải ánh xạ multicast; JMS queue ánh xạ anycast phù hợp.

## 9. Profile Spring Boot và secrets

Profiles rất hữu ích để đổi endpoint và concurrency **của cùng một provider**. Ví dụ artifact Artemis:

`application-dev.yml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: ${ARTEMIS_USER:dev}
    password: ${ARTEMIS_PASSWORD:dev}
~~~

`application-prod.yml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://artemis.internal:61616
    user: ${ARTEMIS_USER}
    password: ${ARTEMIS_PASSWORD}
  jms:
    listener:
      concurrency: 4
      max-concurrency: 12
~~~

Placeholder dạng `${VAR:default}` dùng giá trị mặc định khi biến không có. Chỉ nên đặt default credentials ở dev/test; production phải có secret thật.

Chọn profile qua `SPRING_PROFILES_ACTIVE`/runtime phù hợp. Khi giá trị không đúng, kiểm tra config precedence (file cấu hình, environment, command line, external config) và tránh log secret.

### 9.1. Profile không thay classpath

Artifact chỉ có starter Classic sẽ không tự có Artemis client khi bật profile đặt `spring.artemis.*`. Nếu build có cả hai starter, cũng không có bảo đảm Boot chọn chính xác connection factory theo profile một cách mặc định.

**Thay provider là quyết định dependency + bean + broker**, không chỉ lựa chọn tập property.

### 9.2. localhost trong container

`tcp://localhost:61616` trỏ tới network namespace **của process Spring Boot**. Nếu app và broker chạy hai container khác nhau, `localhost` của app không trỏ tới container broker. Dùng service DNS và port phù hợp, ví dụ:

~~~yaml
spring:
  artemis:
    broker-url: tcp://artemis-broker:61616
~~~

Kiểm tra port được expose, acceptor protocol, TLS, firewall và credential; không giải quyết lỗi DNS/port bằng cách bật embedded broker không chủ ý.

## 10. Smoke test kết nối và gửi/nhận end-to-end

Một test tối thiểu với mỗi provider:

1. Chạy broker đúng phiên bản, có `billing.commands` queue và user đủ quyền.
2. Khởi động ứng dụng với **đúng một** provider starter và đúng namespace.
3. Kiểm tra Spring context tạo `jakarta.jms.ConnectionFactory` và `JmsTemplate`.
4. Gửi message chứa `eventId` mới; quan sát listener nhận text và property.
5. Xem management console: message thêm, delivered, acknowledged; đối chiếu queue/address.
6. Dừng broker trong môi trường lab, xem listener reconnect, lỗi và khả năng redelivery.
7. Thử **sai password** và **sai tên queue**; kết quả phụ thuộc ACL và auto-create broker, không phải chỉ Boot.
8. Nếu cần xác minh transaction, gây lỗi ở consumer rồi kiểm tra rollback/redelivery và idempotency.

Ví dụ runner chỉ bật ở profile smoke:

~~~java
package example.messaging;

import java.util.UUID;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("smoke")
public class JmsSmokeRunner implements ApplicationRunner {
    private final InvoicePublisher publisher;

    public JmsSmokeRunner(InvoicePublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        String eventId = "smoke-" + UUID.randomUUID();
        publisher.publishInvoiceRequested(eventId, "smoke-order");
        System.out.println("SMOKE_SENT " + eventId);
    }
}
~~~

Không bật `smoke` trong production nếu mỗi lần instance restart không được phép gửi test business event. Nếu listener đã chạy, message có thể bị consume quá nhanh để nhìn thấy trong console; phải quan sát log/counter hoặc dùng queue riêng cho test.

**SMOKE_SENT không đồng nghĩa downstream xử lý thành công.** Nó chỉ chứng minh code producer đã trở về bình thường theo cấu hình template tại thời điểm đó.

## 11. Chẩn đoán lỗi theo từng tầng

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra |
|---|---|---|
| Không có `ConnectionFactory` bean | Thiếu starter, auto-config không thỏa điều kiện | Xem dependency tree và condition report |
| `JmsTemplate` không có bean | Chưa có Spring JMS/factory hoặc bị custom config thay thế | Kiểm tra bean, @ConditionalOnMissingBean |
| Lỗi `javax.jms`/`jakarta.jms` | Trộn Boot 3.x với client JMS cũ | Dùng đúng starter/BOM/Jakarta API |
| Classic kết nối nhầm broker | Sai `spring.activemq.broker-url` hoặc config override | Kiểm tra environment và runtime host/port |
| Artemis chạy embedded ngoài ý muốn | Không ép native, classpath/auto-mode | Dùng `spring.artemis.mode=native` |
| Artemis address/queue không tồn tại | Auto-create false, provision/routing sai | Kiểm tra anycast queue, ACL, broker.xml |
| Authentication failed | User/password sai hoặc thiếu quyền | Kiểm tra credential và broker security logs |
| Producer send được nhưng listener không nhận | Queue/topic lệch, listener chưa start, selector hoặc consumer khác lấy | Kiểm tra pub-sub-domain, container state, queue counters |
| Topic offline không nhận lịch sử | Non-durable subscription | Cấu hình durable subscriber thích hợp |
| Message xuất hiện lại sau exception | Transaction rollback/redelivery | Idempotency, broker redelivery/DLQ |
| `@Transactional` không gom DB + JMS | Manager chỉ quản lý một resource | Outbox/inbox hoặc coordinator phù hợp |
| Connection refused trong Docker | Dùng localhost sai | Dùng service DNS, port, network |
| Cả hai starter cùng classpath | Auto-config ambiguity | Chọn một provider hoặc tự đặt named beans |
| Producer chậm | Broker full/paging/flow control hoặc network | Đo send latency, disk, backlog, timeouts |

### 11.1. Condition evaluation report

Trong lab, có thể chạy Spring Boot với `--debug` để xem lý do các auto-configuration được kích hoạt/bỏ qua, đặc biệt khi `ConnectionFactory` không có. Báo cáo này hỗ trợ xác định **bean nào được tạo**, không thay thế kiểm tra broker queue hoặc ACL.

Đừng log mật khẩu, token, hoặc connection URI có secret. Nếu có Actuator JMS health indicator, xem nó như một dấu hiệu connectivity, **không phải bằng chứng rằng event đã được xử lý nghiệp vụ đúng cách**.

## 12. Phạm vi vận hành của cấu hình Spring Boot

Kết nối được broker mới giải quyết tầng transport. Khi đưa vào production, còn cần:

- **Provision queue/topic:** Classsic destination policy hoặc Artemis address/routing/queue chính xác.
- **Persistence:** PERSISTENT send, broker persistent store/journal, durable subscriber nếu topic cần offline backlog.
- **Acknowledgment:** transacted listener nếu cần rollback/redelivery, tránh ACK trước business commit.
- **Redelivery/DLQ:** chính sách ở broker/client theo Classic/Artemis, không thể chỉ dựa vào `spring.jms.listener.max-concurrency`.
- **Idempotency:** producer giữ eventId qua retry, consumer dùng inbox/unique event ID, không suy từ JMSMessageID rằng một event chỉ xuất hiện một lần.
- **Observability:** connection failures, queue lag, listener errors, redelivery count, DLQ, broker disk/paging, end-to-end latency.
- **Secret management:** tách cấu hình dev/prod, có TLS, auth và rotation.
- **HA/recovery:** failover của client và topology broker riêng; retry sau timeout có thể gửi trùng khi commit response bị mất.

**Không dùng Spring profiles hay YAML như bằng chứng rằng các yêu cầu HA/DLQ đã được broker thực thi.** Cần đọc effective runtime config và chạy thử lỗi.

## 13. Bài tập suy luận có đáp án

### A — Sai namespace

Ứng dụng chỉ dùng starter Artemis nhưng có `spring.activemq.broker-url=tcp://localhost:61616`.

**Đáp án:** Property Classic không phải cấu hình kết nối chuẩn của Artemis auto-configuration. Thêm `spring.artemis.mode=native`, `spring.artemis.broker-url` và user/password theo Artemis, kiểm tra client/acceptor.

### B — Chỉ đổi profile

JAR build với Classic starter; production profile chứa `spring.artemis.*`.

**Đáp án:** Profile không tải Artemis client. Cần đổi artifact/dependency hoặc tự cấu hình factory/provider có điều kiện rồi test.

### C — Artemis auto-create tắt

Listener đọc `billing.commands`, nhưng broker chỉ có một address multicast tên đó, không có queue anycast phù hợp.

**Đáp án:** Kiểm tra mapping JMS queue, provision anycast queue đúng routing và ACL. Tăng listener concurrency không sửa được.

### D — Queue và topic trong cùng service

Một ứng dụng dùng queue `billing.commands` và topic `orders.events`; developer đặt global `spring.jms.pub-sub-domain=true`.

**Đáp án:** Có thể khiến sender/listener queue bị giải quyết như topic. Giữ queue default, tạo topic-specific `JmsTemplate` và listener factory.

### E — DB commit rồi crash trước JMS ACK

Billing nhận message lần hai và tạo invoice trùng.

**Đáp án:** Local JMS transaction không phải transaction SQL. Consumer cần inbox với unique event ID và ghi dữ liệu trong cùng transaction; ACK/commit JMS sau DB commit.

### F — Có cả hai starter

Hai starters xuất hiện trên classpath, ứng dụng chỉ có một `@JmsListener`, kỳ vọng Boot tự chọn đúng broker theo URL.

**Đáp án:** Không có cam kết như vậy. Mỗi runtime một provider, hoặc khai báo named connection factory, template và container factory có qualifier.

### G — localhost trong container

App Spring Boot container A, broker Artemis container B; URL `tcp://localhost:61616`.

**Đáp án:** Localhost là container A. Sửa sang DNS/service name của B và kiểm tra port, network, acceptor/credentials. Không bật embedded để “chữa” lỗi kết nối.

## 14. Checklist production

- [ ] Chọn đúng một JMS starter/provider hoặc khai báo multi-provider có tên.
- [ ] Boot 3.x dùng client Jakarta JMS tương thích, không trộn `javax.jms` cũ.
- [ ] Classic dùng `spring.activemq.*`, Artemis dùng `spring.artemis.*` đúng namespace.
- [ ] Artemis broker riêng có `mode=native` và acceptor phù hợp.
- [ ] Secrets lấy từ environment/secret store, không hard-code.
- [ ] URL đúng hostname từ process/container chạy Spring Boot.
- [ ] Queue/topic, routing type, ACL được provision và kiểm tra ở broker.
- [ ] `spring.jms.pub-sub-domain` đúng semantics; app kết hợp queue/topic dùng factory riêng.
- [ ] Listener transaction/ACK, rollback, redelivery/DLQ được kiểm chứng.
- [ ] Concurrency/cache/pool được tune bằng số đo broker + DB.
- [ ] Producer có eventId/outbox, consumer có idempotency/inbox khi nghiệp vụ quan trọng.
- [ ] Đã smoke test gửi/nhận, sai credential, sai destination và broker restart.
- [ ] Có monitoring connection, listener, backlog, DLQ, paging/disk và queue lag.
- [ ] Đã ghi rõ phiên bản Boot, client, broker và kế hoạch migration khi đổi provider.

## 15. Tổng kết

Spring Boot dùng **hai namespace tách biệt** cho hai provider JMS:

- ActiveMQ Classic: `spring.activemq.broker-url`, `spring.activemq.user` và `spring.activemq.password`.
- ActiveMQ Artemis: `spring.artemis.mode=native`, `spring.artemis.broker-url`, `spring.artemis.user` và `spring.artemis.password`.
- Cấu hình Spring JMS dùng chung: `spring.jms.*` như `pub-sub-domain`, listener concurrency và cache.

Muốn ứng dụng hoạt động đúng phải đồng bộ **provider dependency**, **Spring Boot auto-configuration**, **destination/routing thực tế của broker**. Khi ba lớp phù hợp, cùng mã `JmsTemplate` và `@JmsListener` có thể được tái sử dụng giữa Classic và Artemis. Khi một lớp sai, việc chỉ đổi URL hoặc tăng concurrency không giải quyết được; phải xác minh kết nối, queue/topic, transaction và kịch bản gửi/nhận thực tế.
