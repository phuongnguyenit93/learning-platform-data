# Nhiều @JmsListener trên một phương thức trong Spring JMS

## 1. Mục tiêu và câu trả lời ngắn

Trong Spring Framework JMS, **`@JmsListener` là annotation có thể lặp lại (`@Repeatable`)**. Một phương thức Java có thể khai báo **hai hoặc nhiều `@JmsListener`**, mỗi annotation mô tả **một listener endpoint** riêng: có destination, ID, cấu hình container, selector và concurrency riêng. Khi message đến bất kỳ endpoint nào, Spring gọi **cùng một phương thức Java** để xử lý.

Ví dụ:

```java
@Component
class UnifiedEventHandler {

    @JmsListener(id = "orders-endpoint", destination = "orders.inbox")
    @JmsListener(id = "audit-endpoint", destination = "audit.inbox")
    public void handle(String body) {
        System.out.println("Handled: " + body);
    }
}
```

Kết quả ở tầng hạ tầng:

```text
                 Spring-managed UnifiedEventHandler bean
                               │
                      handle(String body)
                       ▲               ▲
                       │               │
           listener endpoint 1   listener endpoint 2
             id=orders-endpoint    id=audit-endpoint
                       ▲               ▲
                container A       container B
                       ▲               ▲
               orders.inbox        audit.inbox
                       ▲               ▲
                    JMS Broker / provider
```

**Không hiểu nhầm:** nhiều annotation trên một method **không** tạo một consumer duy nhất đăng ký nhiều queue, cũng **không** làm một message tự động được gọi N lần. Spring đăng ký **N endpoint** và thường tạo **N listener container** theo từng annotation. Mỗi container quản lý consumer/session, chuyển đổi payload và gọi chung method.

### Sau bài này, bạn sẽ:

1. Biết cú pháp lặp `@JmsListener` và cách dùng `@JmsListeners` khi cần.
2. Hiểu vì sao Spring tạo nhiều endpoint/container nhưng chỉ có một method business.
3. Phân biệt **hai queue khác nhau**, **hai listener trên cùng queue**, và **hai subscription vào topic**.
4. Biết dùng `id`, `destination`, `selector`, `concurrency`, `containerFactory` cho từng annotation.
5. Xem ví dụ Spring Boot 3.x + Artemis + Java 17+, có lệnh chạy và kiểm tra registry.
6. Tránh lỗi trùng ID, trùng xử lý, shared mutable state, khác message schema và sai transaction.

## 2. Cơ chế của repeatable annotation

Java hỗ trợ annotation lặp từ Java 8. Trong Spring JMS, `@JmsListener` mang metadata tương đương:

```java
@Repeatable(JmsListeners.class)
public @interface JmsListener {
    // Các thuộc tính như destination(), id(), containerFactory(), ...
}
```

Đây chỉ là **đoạn tóm tắt cấu trúc** để giải thích ý tưởng, **không phải bản source hoàn chỉnh của Spring Framework**. `@JmsListeners` là **container annotation** để chứa nhiều khai báo `@JmsListener`.

Hai cách viết tương đương về ý nghĩa:

**Cách A — khuyến nghị khi dùng Java 17+: lặp trực tiếp**

```java
@JmsListener(id = "listener-a", destination = "queue.a")
@JmsListener(id = "listener-b", destination = "queue.b")
public void consume(String payload) {
    process(payload);
}
```

**Cách B — dùng `@JmsListeners` rõ ràng**

```java
@JmsListeners({
    @JmsListener(id = "listener-a", destination = "queue.a"),
    @JmsListener(id = "listener-b", destination = "queue.b")
})
public void consume(String payload) {
    process(payload);
}
```

Cả hai snippet là **mảnh method** cần đặt trong Spring-managed bean và có imports:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.annotation.JmsListeners;
```

`@JmsListeners` không phải annotation tạo một listener “đa queue” đặc biệt: nó chỉ là cú pháp nhóm các `@JmsListener`. Java reflection `getAnnotationsByType(JmsListener.class)` có thể đọc các annotation đã lặp; Spring annotation processor cũng nhận ra từng khai báo.

**Phạm vi phiên bản:** Repeatable `@JmsListener` có ở các dòng Spring Framework hỗ trợ Jakarta/Java hiện đại; bài thực hành dùng Spring Framework 6.x thông qua Spring Boot 3.5.7. Với Spring Boot 3+, import JMS là `jakarta.jms.*` thay cho `javax.jms.*`.

## 3. Spring đăng ký các endpoint như thế nào?

Khi bean có các method được đánh dấu `@JmsListener`, hạ tầng annotation-driven do `@EnableJms` kích hoạt sẽ quét, đăng ký `MethodJmsListenerEndpoint` và tạo listener container thông qua `JmsListenerContainerFactory`.

Về khái niệm:

```text
Spring Boot / ApplicationContext
   │
   ├─ @EnableJms / JMS annotation infrastructure
   │     │
   │     ▼
   │  JmsListenerAnnotationBeanPostProcessor
   │     │
   │     ├─ tìm @JmsListener thứ nhất trên handle()
   │     │     └─ MethodJmsListenerEndpoint("listener-a", "queue.a")
   │     │
   │     └─ tìm @JmsListener thứ hai trên handle()
   │           └─ MethodJmsListenerEndpoint("listener-b", "queue.b")
   │
   ▼
 JmsListenerEndpointRegistry
   ├─ listener-a → MessageListenerContainer A
   └─ listener-b → MessageListenerContainer B
                          │
           cùng target bean, cùng handle(...)
```

Một annotation thường tương ứng với **một endpoint** và **một listener container**. Container tạo hoặc quản lý các JMS consumer/session tùy loại container và `concurrency`; số consumer vật lý không luôn bằng số annotation. Ví dụ hai endpoint, mỗi endpoint concurrency 3, có thể có **sáu consumers**, chứ không chỉ hai.

### 3.1. Method chung, nhưng context endpoint riêng

Mỗi message sẽ đi qua container của một endpoint; container quyết định:

- `Destination` nào cần consume.
- Consumer selector, nhận theo queue hay topic.
- Độ đồng thời (concurrency) và session/ack/transaction.
- `MessageConverter` hoặc handler method adapter được factory cấp.
- Hành vi lỗi, recovery, lifecycle và các chính sách provider.

Chỉ **đích xử lý cuối** là method Java chung. Một `@JmsListener` không được “gọi” theo kiểu lặp `for` trong Spring; thay vào đó các container độc lập chờ messages từ broker và gọi method khi nhận.

### 3.2. `JmsListenerEndpointRegistry` để quản lý

Các container được tạo qua annotation được quản lý bởi `org.springframework.jms.config.JmsListenerEndpointRegistry`, **không nhất thiết là bean riêng** tự inject bằng tên container.

```java
// Mảnh code trong một Spring-managed component.
JmsListenerEndpointRegistry registry = ...;

boolean hasA = registry.getListenerContainer("listener-a") != null;
boolean hasB = registry.getListenerContainer("listener-b") != null;

System.out.println("A registered: " + hasA);
System.out.println("B registered: " + hasB);
```

`registry.getListenerContainer("listener-a")` trả về container theo ID hoặc `null` nếu không có; có thể dùng để kiểm tra/điều khiển lifecycle theo chính sách vận hành. Không đồng nghĩa kiểm tra non-null là broker chắc chắn đang kết nối và đã consume message thành công. Để kiểm tra delivery, cần integration test hoặc health/metrics của broker.

Đặt ID ổn định cho các endpoint quan trọng sẽ giúp giám sát/troubleshoot rõ hơn so với để Spring tự sinh ID.

## 4. Dùng khi nào: hai queue khác nhau

Trường hợp phổ biến nhất: hai queue chứa **payload cùng hợp đồng** và xử lý theo cùng logic, ví dụ `orders.created` và `orders.replayed` đều chứa `OrderCreatedV1` theo quy ước chung.

```java
@Component
class OrderCreatedHandler {

    @JmsListener(id = "orders-live", destination = "orders.created")
    @JmsListener(id = "orders-replay", destination = "orders.replayed")
    public void onOrder(String orderId) {
        // Cùng code xử lý, hai nguồn queue riêng biệt.
        System.out.println("Order: " + orderId);
    }
}
```

Ưu điểm:

- Tránh copy một đoạn business logic vào hai method.
- Có thể dùng **một nơi** để validate, map DTO và gọi business service.
- Có thể cấu hình concurrency hoặc container factory theo endpoint.
- Khi đổi logic, các endpoint cùng dùng code mới.

Nhược điểm:

- Nếu hai queue có schema/quy tắc bảo mật/ack khác nhau, một method có thể trở nên quá nhiều nhánh.
- Nếu đồng thời hai queue chứa **cùng event**, handler có thể xử lý event **hai lần**, không có dedupe chỉ vì method chung.
- Khi queue replay chứa sự kiện cũ, phải chú ý idempotency và kiểm soát business side effects.
- Vận hành khó biết lỗi đến từ queue nào nếu log không có destination/source header.

**Quy tắc thực dụng:** nhiều `@JmsListener` trên cùng method hợp lý khi **message contract và policy xử lý tương thích**. Nếu nghiệp vụ khác nhau, dùng các listener method riêng gọi **một service chung** thay vì ép mọi message qua một method.

### 4.1. Nếu schema khác nhau thì sao?

Ví dụ `orders.queue` nhận JSON `OrderCreatedV1`, còn `audit.queue` nhận JSON `AuditRecordV2`. Đặt cùng method `consume(OrderCreatedV1 order)` có thể khiến converter thất bại khi nhận audit message.

Cách hợp lý hơn:

```java
@Component
class DedicatedHandlers {
    private final BusinessProcessor processor;

    DedicatedHandlers(BusinessProcessor processor) {
        this.processor = processor;
    }

    @JmsListener(destination = "orders.queue")
    public void handleOrder(OrderCreatedV1 event) {
        processor.processOrder(event);
    }

    @JmsListener(destination = "audit.queue")
    public void handleAudit(AuditRecordV2 event) {
        processor.processAudit(event);
    }
}
```

Các tên `BusinessProcessor`, `OrderCreatedV1`, `AuditRecordV2` trong ví dụ này là **kiểu minh họa của ứng dụng**, không phải class có sẵn trong Spring. Đây là snippet kiến trúc, không phải một project độc lập. Với JSON DTO, còn cần `MessageConverter` được cấu hình cho schema tương ứng.

## 5. Hai annotation cùng một destination: không tự nhân đôi message

Đặt hai `@JmsListener` cùng đọc một **queue**:

```java
@JmsListener(id = "worker-a", destination = "jobs.queue")
@JmsListener(id = "worker-b", destination = "jobs.queue")
public void process(String body) {
    System.out.println(body);
}
```

Spring đăng ký **hai endpoint/consumer** đến `jobs.queue`. Với semantics point-to-point của JMS queue, **một message thông thường được phân phối cho một consumer**, chứ không phát bản sao đến cả hai chỉ vì có hai annotation. Chúng là **competing consumers**.

```text
Queue jobs.queue:  message-1, message-2, message-3
        │
        ├── Consumer A (endpoint worker-a) ──► process(...)
        └── Consumer B (endpoint worker-b) ──► process(...)

Mỗi message được một consumer xử lý trong một lượt delivery bình thường.
Nếu lỗi/retry/redelivery, cùng message có thể được giao lại.
```

Những hệ quả:

- Đặt cùng destination hai lần **không phải** cách “chạy hai handler cho mỗi message”.
- Nếu cần tăng throughput, có thể cấu hình `concurrency` của **một endpoint** thay vì nhân đôi annotation giống hệt nhau. Đây thường là cách rõ ràng hơn.
- Hai endpoint có thể cạnh tranh, và thời điểm xử lý không đảm bảo bằng thứ tự toàn cục của queue khi concurrency tăng.
- Khi broker redelivery sau transaction rollback, một message có thể đến consumer khác trong lần thử sau; **không suy rằng “mỗi message chính xác một lần”** chỉ từ queue semantics.

### 5.1. Muốn fan-out cho mọi subscriber: dùng topic hoặc tự phát nhiều bản

Với JMS topic và những subscription phù hợp, mỗi subscriber có thể nhận một bản message, khác với competing consumers của queue. Nhưng phải cấu hình **pub-sub domain**, subscription, durability/shared subscription và broker routing rõ ràng.

Không tự đổi `destination="jobs.queue"` thành tên topic rồi tin Spring biết đó là topic: container factory có thể mặc định queue mode. Cấu hình factory/topic phù hợp và test với provider. Hai listener trên cùng topic có thể là **hai subscriptions**, nhưng các hình thức shared/durable subscriptions lại có semantics phân phối riêng; không phát biểu đơn giản rằng luôn có chính xác hai bản ở mọi cấu hình.

**Nếu mục đích chỉ là cùng một event đi tới hai hệ thống khác nhau**, xem xét thiết kế publish–subscribe hoặc hai queues được route từ một address/topic; đây là quyết định topology, không phải tác dụng đặc biệt của repeatable annotation.

## 6. Dùng `selector` để phân luồng trên cùng queue

Hai endpoint có thể nhận những loại message khác nhau trên một queue dựa vào JMS message selector:

```java
@Component
class ClassifiedConsumer {

    @JmsListener(
        id = "orders-selector",
        destination = "events.queue",
        selector = "eventType = 'ORDER'"
    )
    @JmsListener(
        id = "audit-selector",
        destination = "events.queue",
        selector = "eventType = 'AUDIT'"
    )
    public void onEvent(String payload) {
        // Cùng method, khác selector.
    }
}
```

Producer phải đặt **JMS property**, không chỉ một field JSON:

```java
jmsTemplate.convertAndSend("events.queue", "order-42", message -> {
    message.setStringProperty("eventType", "ORDER");
    return message;
});
```

JMS selector lọc theo header/property chuẩn mà provider hỗ trợ; nó **không parse arbitrary JSON body**. Với hai selector không chồng lấn như `ORDER` và `AUDIT`, mỗi message hợp lệ thường chỉ phù hợp một consumer. Nếu selector chồng lấn, hai consumers trên cùng queue **vẫn cạnh tranh**, không biến queue thành topic.

### 6.1. Nếu message không khớp bất kỳ selector nào?

Message có thể nằm lại trong queue cho đến khi consumer phù hợp xuất hiện, hết TTL hoặc được chuyển theo broker policy. Đừng giả định Spring tự đưa nó vào DLQ chỉ vì không có listener khớp selector. Nên có quy tắc unknown event type và giám sát queue backlog.

### 6.2. Vì sao selector không thay validation?

Một producer có thể đặt property `eventType=ORDER` nhưng body JSON lại là schema của audit. Selector chỉ quyết định **consumer nào nhận**; handler vẫn phải validate content type, schema version, required fields và các ràng buộc nghiệp vụ. Nếu nhiều queue dùng chung handler, điều này càng quan trọng.

## 7. Thuộc tính `@JmsListener` cấu hình độc lập theo annotation

| Thuộc tính | Vai trò | Lưu ý với một method có nhiều annotation |
| --- | --- | --- |
| `destination` | Tên JMS destination mà endpoint nhận | Mỗi annotation có giá trị riêng; không truyền chuỗi `q1,q2` để hiểu là hai queues |
| `id` | ID container endpoint | **Phải duy nhất** giữa các endpoint trong cùng registry |
| `containerFactory` | Tên bean `JmsListenerContainerFactory` để tạo container | Mỗi annotation có thể dùng factory khác nếu policy khác |
| `selector` | JMS selector biểu thức lọc headers/properties | Được áp dụng riêng trên consumer của từng endpoint |
| `concurrency` | Giới hạn số consumer/container threads theo factory | Mỗi annotation tính **riêng**, tổng tài nguyên có thể tăng |
| `subscription` | Subscription name cho topic durable/shared phù hợp | Không tùy tiện dùng trùng với cấu hình không tương thích |

Ví dụ hai endpoint có giới hạn concurrency riêng:

```java
@JmsListener(
    id = "fast-orders",
    destination = "orders.fast",
    concurrency = "2-4"
)
@JmsListener(
    id = "slow-orders",
    destination = "orders.slow",
    concurrency = "1"
)
public void handle(String payload) {
    process(payload);
}
```

Ở đây `process(payload)` là **hàm nghiệp vụ minh họa** chưa khai báo trong snippet. Tùy container factory thực tế, `concurrency="2-4"` có thể dùng ít nhất hai và tối đa bốn consumers; không phải một method được gọi bốn lần cho mỗi message. Nếu factory không hỗ trợ scaling động thì interpretation có thể khác, cần kiểm tra API cụ thể.

### 7.1. Trùng `id` gây vấn đề gì?

```java
// KHÔNG NÊN: hai endpoint dùng cùng ID.
@JmsListener(id = "same-id", destination = "queue.a")
@JmsListener(id = "same-id", destination = "queue.b")
public void handle(String body) {
    // ...
}
```

Registry cần ID để quản lý mỗi container. Một ID bị đăng ký lại có thể làm startup lỗi với thông báo tương tự “Another endpoint is already registered with id ...”. Đặt các giá trị khác nhau, ví dụ `inbound-a-v1`, `inbound-b-v1`.

Nếu không đặt `id`, Spring có thể tự sinh ID. Điều này tránh trùng trong điều kiện bình thường nhưng không thuận tiện cho giám sát, alert và điều khiển lifecycle theo tên có nghĩa.

### 7.2. `containerFactory` có thể khác nhau

Một method đôi khi được gọi bởi một endpoint xử lý queue quan trọng và một endpoint xử lý workload test. Có thể chọn:

```java
@JmsListener(
    id = "critical-events",
    destination = "events.critical",
    containerFactory = "strictQueueFactory"
)
@JmsListener(
    id = "background-events",
    destination = "events.background",
    containerFactory = "batchQueueFactory"
)
public void onEvent(String body) {
    process(body);
}
```

Hai tên factory phải tồn tại như Spring beans kiểu `JmsListenerContainerFactory`, với `ConnectionFactory`, transaction, acknowledgement, concurrency/recovery, converter và broker security được cấu hình phù hợp. Nếu một annotation không khai `containerFactory`, Spring dùng default bean thường tên `jmsListenerContainerFactory` hoặc default được cấu hình bởi `JmsListenerConfigurer`.

**Cảnh báo:** factory khác nhau có thể dẫn đến **transaction semantics** và message conversion khác nhau dù cùng method. Đừng dùng chung handler cho hai payload/schema không tương thích hoặc nghĩ annotation đã tự xác định type converter.

### 7.3. Nếu khác destination nhưng cần biết nguồn?

Có thể truyền một metadata đáng tin từ broker/transport vào handler, ví dụ JMS destination header, hoặc chọn property `sourceSystem` được producer gắn theo contract. Với Spring method signature:

```java
import jakarta.jms.Message;
import jakarta.jms.JMSException;
import jakarta.jms.Queue;

@JmsListener(id = "from-a", destination = "queue.a")
@JmsListener(id = "from-b", destination = "queue.b")
public void onMessage(Message raw) throws JMSException {
    if (raw.getJMSDestination() instanceof Queue queue) {
        String name = queue.getQueueName();
        System.out.println("Received on: " + name);
    }
}
```

Đây là snippet method với raw JMS Message; không có auto conversion sang String. Tên queue có thể là provider-specific và không nên dùng để quyết định quy tắc bảo mật nghiệp vụ mà không kiểm tra; giải pháp rõ ràng hơn khi logic khác nhau là hai method riêng cùng gọi một service.

Có thể dùng `@Header` với tên `JmsHeaders.DESTINATION` trong Spring message abstraction, nhưng kiểu runtime/header mapping phải được kiểm tra theo converter/provider; ví dụ trên chủ động dùng native `Message.getJMSDestination()` để tránh giả định về tên chuỗi header.

## 8. Ví dụ thực hành hoàn chỉnh: hai @JmsListener trên một method

Demo sau dùng **Java 17+**, **Maven**, **Spring Boot 3.5.7**, **Apache ActiveMQ Artemis** chạy local qua Docker. Nó gửi hai String messages vào **hai queue khác nhau**, và cùng một method `handle` nhận từ cả hai. Một component đếm **hai payload khác nhau** bằng `CountDownLatch` và ghi kết quả có sắp xếp để stdout ổn định dù listener chạy bất đồng bộ.

### 8.1. Khởi động Artemis broker cục bộ

Máy cần Docker và cổng localhost `61616` trống:

```bash
docker run --rm -d --name jms-repeatable-broker \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine

docker logs jms-repeatable-broker
```

Chờ broker sẵn sàng trước khi chạy ứng dụng. Đây là tài khoản **demo local**, tuyệt đối không dùng cùng credential ở production. Artemis image demo có thể cho phép auto-create queue theo policy mặc định; broker production có thể bắt buộc provision và cấp quyền từ trước.

### 8.2. Cấu trúc project

```text
repeatable-jms-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── resources/
    │   │   └── application.properties
    │   └── java/com/example/jms/
    │       └── RepeatableJmsApplication.java
    └── test/
        └── java/com/example/jms/
            └── RepeatableAnnotationTest.java
```

### 8.3. Maven `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>repeatable-jms-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-artemis` cung cấp client và Spring JMS infrastructure. Vì payload chỉ là String, converter mặc định có thể dùng `TextMessage`; ví dụ không cần custom JSON converter.

### 8.4. `src/main/resources/application.properties`

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
```

Đây là cấu hình **chỉ cho local lab**. Ở production không đưa mật khẩu thật vào source Git hoặc application.properties; cấp thông qua environment/secret manager, cấu hình TLS và ACL.

### 8.5. `RepeatableJmsApplication.java` — mã chạy đầy đủ

```java
package com.example.jms;

import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class RepeatableJmsApplication {

    public static void main(String[] args) {
        SpringApplication.run(RepeatableJmsApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(
            JmsTemplate template,
            JmsListenerEndpointRegistry registry,
            ReceivedTracker tracker) {
        return args -> {
            boolean bothRegistered =
                    registry.getListenerContainer("orders-endpoint") != null
                    && registry.getListenerContainer("audit-endpoint") != null;
            if (!bothRegistered) {
                throw new IllegalStateException("Expected two JMS endpoints");
            }

            template.convertAndSend(
                    "demo.multi.orders", "order-42",
                    msg -> {
                        msg.setStringProperty("eventType", "ORDER");
                        return msg;
                    });

            template.convertAndSend(
                    "demo.multi.audit", "audit-9",
                    msg -> {
                        msg.setStringProperty("eventType", "AUDIT");
                        return msg;
                    });

            if (!tracker.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timeout waiting for both messages");
            }

            System.out.println("Endpoints registered: true");
            System.out.println("Messages: " + tracker.snapshot());
        };
    }
}

@Component
class MultiQueueHandler {

    private final ReceivedTracker tracker;

    MultiQueueHandler(ReceivedTracker tracker) {
        this.tracker = tracker;
    }

    @JmsListener(
            id = "orders-endpoint",
            destination = "demo.multi.orders",
            concurrency = "1"
    )
    @JmsListener(
            id = "audit-endpoint",
            destination = "demo.multi.audit",
            concurrency = "1"
    )
    public void handle(String payload,
                       @Header("eventType") String eventType) {
        if (!"ORDER".equals(eventType) && !"AUDIT".equals(eventType)) {
            throw new IllegalArgumentException("Unsupported eventType");
        }

        tracker.record(eventType + ":" + payload);
    }
}

@Component
class ReceivedTracker {

    private final Set<String> received = ConcurrentHashMap.newKeySet();
    private final CountDownLatch latch = new CountDownLatch(2);

    void record(String value) {
        // Đếm một lần cho mỗi dữ liệu khác nhau, tránh trừ latch vì duplicate.
        if (received.add(value)) {
            latch.countDown();
        }
    }

    boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    List<String> snapshot() {
        return received.stream().sorted().toList();
    }
}
```

**Giải thích phần quan trọng:**

1. `@EnableJms` chủ động bật annotation-driven endpoints. Với Spring Boot có starter JMS, Boot cũng cấu hình hạ tầng thích hợp; khai báo này giúp ví dụ rõ cơ chế.
2. `MultiQueueHandler` là **một bean** có **một method** `handle(...)`, nhưng **hai `@JmsListener`**.
3. Spring đăng ký `orders-endpoint` nhận từ `demo.multi.orders`, `audit-endpoint` nhận từ `demo.multi.audit`. `JmsListenerEndpointRegistry` cho phép kiểm tra từng endpoint theo ID.
4. `JmsTemplate.convertAndSend` phát hai String payload qua JMS `TextMessage`; post-processor đặt JMS property `eventType` nên `@Header("eventType") String eventType` đọc được ở listener.
5. Cả hai endpoint đều gọi cùng `handle(String, String)`; method xử lý message theo một schema đơn giản rồi ghi `eventType:payload` vào tracker thread-safe.
6. Listener containers thường xử lý trên threads khác nhau, không đảm bảo thứ tự. `ConcurrentHashMap.newKeySet()` xử lý truy cập đồng thời; `CountDownLatch(2)` giúp đợi hai giá trị khác nhau; `sorted()` khiến output ổn định.
7. Ví dụ dùng hai queue demo trống, chỉ một application làm consumer. Nếu queue đã có message cũ hoặc có competing consumers khác, kết quả có thể khác; hãy dùng broker sạch và tên queue riêng.
8. Để có bảo đảm nghiệp vụ quan trọng, cần transaction, retry/DLQ và idempotency chứ không chỉ dùng concurrent set trong memory. Tracker chỉ dùng cho bài thực hành.

### 8.6. Lệnh chạy và stdout dự kiến

Từ thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Nếu broker sẵn sàng và hai messages được nhận trước 10 giây, ứng dụng in:

```text
Endpoints registered: true
Messages: [AUDIT:audit-9, ORDER:order-42]
```

Spring/Artemis còn có startup logs và logs kết nối khác; hai dòng trên là **output do code demo in**, không phải toàn bộ stdout. Thứ tự nhận có thể thay đổi nhưng danh sách đã sắp xếp nên dòng `Messages` giữ thứ tự như trên.

Dừng broker:

```bash
docker stop jms-repeatable-broker
```

**Giới hạn:** Chưa mô phỏng TLS, secret manager, outbox, database transaction, broker failover hoặc duplicate redelivery. Không dùng cấu hình lab trong production.

## 9. Unit test kiểm tra repeatable annotation

Không cần broker để kiểm tra một method thực sự có hai `@JmsListener` với các ID/destination đã khai báo. Java reflection hỗ trợ `getAnnotationsByType()` cho annotation có `@Repeatable`.

### 9.1. `RepeatableAnnotationTest.java`

```java
package com.example.jms;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.jms.annotation.JmsListener;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RepeatableAnnotationTest {

    @Test
    void oneMethodDeclaresTwoDifferentListenerEndpoints()
            throws Exception {
        Method method = MultiQueueHandler.class.getDeclaredMethod(
                "handle", String.class, String.class);

        JmsListener[] listeners =
                method.getAnnotationsByType(JmsListener.class);

        assertEquals(2, listeners.length);

        Set<String> ids = Arrays.stream(listeners)
                .map(JmsListener::id)
                .collect(Collectors.toSet());
        Set<String> destinations = Arrays.stream(listeners)
                .map(JmsListener::destination)
                .collect(Collectors.toSet());

        assertEquals(
                Set.of("orders-endpoint", "audit-endpoint"), ids);
        assertEquals(
                Set.of("demo.multi.orders", "demo.multi.audit"),
                destinations);
    }
}
```

Chạy:

```bash
mvn test
```

Kết quả mong đợi: **test pass** nếu code/dependency hợp lệ. Nó kiểm tra **annotation metadata**, không chứng minh Spring đã tạo hai containers hoặc broker đã phân phối hai message. Để kiểm tra lifecycle và delivery cần integration test khởi tạo Spring context với broker thật, ví dụ chạy project demo ở phần 8 hoặc dùng Testcontainers và assert registry + message flow.

### 9.2. Hai loại test nên phân biệt

| Loại test | Có broker thật? | Kiểm chứng |
| --- | --- | --- |
| Reflection/JUnit test | Không | Có hai annotations, IDs/destinations riêng |
| Spring context test + registry | Có thể cần broker tùy cấu hình | Bean post-processing đăng ký endpoints/containers |
| Integration test Artemis | Có | Message thực đến từ từng queue, conversion, ack/retry |
| Failure/redelivery test | Có | Transaction rollback, duplicate, DLQ, retry policy |
| Load/concurrency test | Có | Backpressure, throughput, thread safety, ordering |

Không dùng **chỉ** một unit test annotation để kết luận toàn bộ hệ thống messaging hoạt động ổn định.

## 10. `@JmsListeners` wrapper và custom composed annotations

Java cho phép viết trực tiếp:

```java
@JmsListeners({
    @JmsListener(id = "orders-a", destination = "orders.a"),
    @JmsListener(id = "orders-b", destination = "orders.b")
})
public void onOrder(String body) {
    // Xử lý...
}
```

**Mục đích:** diễn đạt một danh sách annotations trong một container; nó không có thuộc tính `destination` chung và không thay đổi số endpoints được đăng ký. Vì Spring `@JmsListener` là repeatable, ở Java 17+ cách lặp trực tiếp thường ngắn, dễ đọc hơn.

Spring cũng hỗ trợ sử dụng `@JmsListener` như **meta-annotation** trong một số trường hợp muốn định nghĩa annotation domain-specific. Ví dụ `@OrdersListener` có thể cấu hình sẵn destination/converter/factory, nhưng phải cẩn thận Spring annotation scanning, attribute aliasing, naming convention và endpoint IDs. Nếu chỉ muốn nghe hai queue, **không cần** tạo custom composed annotation; lặp trực tiếp là đủ.

### 10.1. Khi danh sách queue thay đổi ở runtime

Repeatable annotations được gắn ở **compile time** và endpoint được Spring đăng ký khi context khởi động. Nếu muốn runtime đọc một danh sách queue từ config/service discovery và thêm/bớt endpoints, cần hạ tầng **programmatic endpoint registration** hoặc điều khiển lifecycle/registry có kiểm soát; không mong Spring tự “thêm annotation” trên method Java đang chạy.

Spring cung cấp `JmsListenerConfigurer`, `JmsListenerEndpointRegistrar`, `SimpleJmsListenerEndpoint` và `JmsListenerEndpointRegistry`. Đây là một lựa chọn kiến trúc khác; không nên dùng động khi yêu cầu chỉ là hai destination cố định.

## 11. Transaction, acknowledge và retry: nhiều endpoint không dùng chung transaction

Mỗi annotation có container riêng với session/transaction riêng. Khi broker gửi một message tới `orders.queue`, và một message khác tới `audit.queue`, hai lần gọi cùng method **không tự chia sẻ cùng JMS transaction** chỉ vì chung Java function.

```text
orders.queue  → endpoint orders → Session/transaction A ─┐
                                                         ├─ shared Java method
audit.queue   → endpoint audit  → Session/transaction B ─┘
```

Điều này có nghĩa:

- Nếu `orders` xử lý thành công còn `audit` thất bại, không tự rollback cả hai queues.
- Nếu hai endpoint dùng hai `containerFactory` khác nhau, acknowledgement và redelivery policy có thể khác.
- Với `AUTO_ACKNOWLEDGE`, không mặc định một exception trong business sẽ khiến broker redeliver theo yêu cầu; xem loại listener container/provider và ack timing.
- Với `sessionTransacted=true` hoặc transaction manager phù hợp, container có thể rollback receive khi handler ném lỗi và broker redeliver theo policy.
- Không dùng `@Transactional` cho database rồi suy rằng cả DB và JMS cùng một distributed atomic transaction. Với dual-write, cân nhắc outbox/JTA-XA đúng cấu hình, idempotency và DLQ.

### 11.1. Cấu hình transacted factory

Đây là **mảnh code cấu hình** tùy chọn, không phải một phần của file demo chạy ở phần 8:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Bean("transactedQueueFactory")
DefaultJmsListenerContainerFactory transactedQueueFactory(
        ConnectionFactory connectionFactory) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-4");
    return factory;
}
```

Sau đó có thể gán `containerFactory="transactedQueueFactory"` cho các annotations cần dùng. Với Spring Boot, cân nhắc dùng `DefaultJmsListenerContainerFactoryConfigurer` và cấu hình factory theo Boot để không vô tình mất các settings đã có, đồng thời kiểm tra wrapper/pooling/CachingConnectionFactory của `ConnectionFactory`. Ví dụ trên chỉ cho thấy ý tưởng local JMS transaction và concurrency, không trình bày mọi khía cạnh production (recovery, timeout, DLQ, metrics).

### 11.2. Đừng nuốt lỗi rồi trả về thành công

Nếu handler bắt exception và không ném tiếp, container có thể coi message đã xử lý và commit/ack:

```java
// Anti-pattern, chỉ minh họa:
try {
    doBusinessWork(payload);
} catch (RuntimeException ex) {
    logger.warn("failed", ex);
    // Không rethrow/đánh dấu rollback: container có thể ack.
}
```

Không phải mọi lỗi đều nên retry mãi: JSON sai schema hoặc không có quyền là loại lỗi cần phân loại, cảnh báo và có DLQ/quarantine. Repeatable annotation không tự giải quyết retry hay poison messages.

## 12. Concurrency và thread safety của một method chung

**Cùng một bean method không có nghĩa xử lý tuần tự.** Hai endpoint có thể được gọi **cùng lúc** trên hai thread và một endpoint có thể có nhiều consumer theo concurrency. Những lỗi hay gặp:

```java
@Component
class UnsafeHandler {

    private int processedCount = 0; // Không thread-safe.

    @JmsListener(destination = "queue.a")
    @JmsListener(destination = "queue.b")
    public void onMessage(String payload) {
        processedCount++; // Race khi hai containers gọi đồng thời.
    }
}
```

Nên dùng handler stateless, hoặc cập nhật state qua cơ chế thread-safe/transaction:

```java
@Component
class SafeHandler {
    private final AtomicLong processed = new AtomicLong();

    @JmsListener(id = "a", destination = "queue.a")
    @JmsListener(id = "b", destination = "queue.b")
    public void onMessage(String payload) {
        process(payload);  // business service phải thread-safe.
        processed.incrementAndGet();
    }
}
```

Đây là **mảnh code kiến trúc**: `AtomicLong` cần `java.util.concurrent.atomic.AtomicLong`, còn `process` là business method chưa khai báo. Atomic counter **chỉ** giải quyết race của bộ đếm, không thay thế transaction DB hoặc idempotency khi redelivery.

**Tổng số consumers** có thể tăng hơn dự kiến: ba annotation với concurrency `"2-5"` có thể tạo tối đa **15 consumer instances**, tùy factory scaling và khả năng provider. Đừng chỉ nhìn tên method mà bỏ qua từng endpoint khi tính connection/session/thread và sức chịu tải của broker.

### 12.1. Ordering giữa nhiều queue

Ngay cả khi message trên từng queue được broker đưa theo thứ tự, xử lý ở hai endpoints **không có một thứ tự toàn cục**. Nếu cần business ordering theo orderId/aggregateId, dùng partition/grouping/serialization phù hợp và concurrency có chủ đích. Tăng consumers thường làm tăng throughput nhưng giảm khả năng suy luận processing order.

### 12.2. Idempotency khi hai queue cùng gửi một event

Nếu `orders.created` và `orders.replayed` đều có eventId `evt-42`, handler chung có thể nhận hai lần. Không phải framework bug. Handler cần dedupe theo eventId/business key nếu chỉ được thực hiện side effect một lần, hoặc phân biệt các loại message nếu replay có mục đích khác.

## 13. Giám sát, cấu hình, lifecycle và troubleshooting

### 13.1. Kiểm tra endpoint IDs

Có thể hiển thị IDs với registry:

```java
Set<String> ids = registry.getListenerContainerIds();
System.out.println(ids);
```

Đây là snippet trong bean có inject `JmsListenerEndpointRegistry`, cần import `java.util.Set`. **Thứ tự Set không được đảm bảo**; đừng dùng output chưa sắp xếp làm assert cố định. Dùng `getListenerContainer("orders-endpoint")` để lấy một container cụ thể; có thể gọi `start()`/`stop()` trong công cụ vận hành có kiểm soát, nhưng dừng một endpoint không tự ngừng các endpoint còn lại.

### 13.2. Metrics nên tách theo endpoint/destination

Theo dõi:

- Endpoint/container ID, destination, runtime state.
- Số consumers active, concurrency, session/connection count, worker thread pool.
- Queue depth, consumer lag, redelivery, DLQ, timeout/recovery.
- Lỗi decode/schema/version, business exceptions, retry count.
- Thời gian xử lý và throughput theo endpoint.

Nếu chỉ log tên method `handle`, các lỗi từ hai queue khác nhau có thể bị trộn; thêm source/destination hợp lệ đã được sanitize vào log. Không dùng toàn bộ payload hoặc token bí mật làm metric label vì rủi ro cardinality và quyền riêng tư.

### 13.3. Lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Method không được gọi | Thiếu `@EnableJms`/auto-config, bean chưa được scan | Kiểm tra bean, annotation infrastructure và registry |
| Chỉ queue A hoạt động | Destination B sai tên, broker không route, thiếu quyền | Kiểm tra ID/container, destination, ACL và broker queue depth |
| Hai annotations nhưng chỉ một message được xử lý | Cả hai đang cùng đọc một **queue** | Đây là competing consumers; dùng topic/fan-out nếu cần |
| Hai messages nhưng handler lỗi decode ở một queue | Hai queues có schema khác nhau | Tách handler hoặc thống nhất conversion/schema |
| Startup lỗi duplicate endpoint ID | Hai annotations dùng cùng `id` | Dùng ID riêng |
| Không có listener container factory | Không có default hoặc `containerFactory` trỏ bean sai | Khai báo factory đúng tên |
| `@JmsListener(destination="a,b")` không nghe hai queue | Destination string là một tên, không phải danh sách | Viết hai annotations |
| Một annotation dùng selector nhưng message không đến | Producer không đặt đúng JMS property | Kiểm tra selector và properties, không chỉ JSON body |
| Tưởng `concurrency=5` xử lý mỗi message 5 lần | Concurrency là số consumers, không phải fan-out | Kiểm tra semantics queue/topic |
| Count/sum trong listener bị sai | Shared mutable field và concurrent callbacks | Stateless handler/atomic/transaction-safe state |
| Một queue redeliver nhiều, queue kia bình thường | Factory/ack/transaction hoặc message validity khác | So sánh configuration từng endpoint |
| Không biết source trong log | Method chung không ghi metadata | Ghi destination/source/correlation đã sanitize |
| Producer gửi thành công nhưng handler không chạy | Broker chưa có consumer hoặc topic subscription chưa sẵn sàng | Kiểm tra readiness và delivery; không nhầm send với processing |
| Retry mãi poison message | Sai schema/logic, không có DLQ policy | DLQ/quarantine, bounded retry, alert |
| Khác endpoint ID giữa môi trường | Để Spring auto-generate ID | Đặt `id` cố định có nghĩa |
| Listener không nhận sau khi đổi broker password | Cached connection/credential chưa xoay vòng đúng | Kiểm tra security, recreate connection theo runbook |

### 13.4. Khi nào không nên dùng repeatable `@JmsListener`?

Tách method nếu:

- Các queues có message contracts/validation khác nhau.
- Mỗi queue có transaction, retry, DLQ hoặc response semantics rất khác.
- Phải ghi log và nghiệp vụ riêng theo source, dễ nhầm khi gom chung.
- Cần phân quyền/multi-tenant context khác nhau có thể không phân biệt an toàn bằng payload.
- Có nhiều chủ sở hữu nghiệp vụ khác nhau: một method chung sẽ thành điểm coupling.

Có thể vẫn tái dùng code bằng hai adapter methods gọi cùng `BusinessService.process(...)`, thay vì đặt nhiều annotations lên một method trực tiếp.

## 14. Checklist triển khai và code review

- [ ] Mọi `@JmsListener` trên cùng method thực sự cần dùng chung một payload contract/handler.
- [ ] Đã xác định rõ từng destination là **queue hay topic**.
- [ ] Mỗi annotation có `id` riêng (hoặc chấp nhận auto-generated IDs có chủ ý).
- [ ] `containerFactory` của mỗi endpoint tồn tại, đúng provider/ack/transaction/recovery.
- [ ] `concurrency` được tính theo **từng endpoint**; đã tính tổng consumers/threads.
- [ ] Nếu dùng selectors, producer có đúng JMS headers/properties.
- [ ] Không kỳ vọng hai consumers trên cùng queue nhận hai bản sao một message.
- [ ] Không dùng `destination="q1,q2"` làm danh sách queue.
- [ ] Handler thread-safe và không giữ JMS Session, producer hoặc mutable state sai scope.
- [ ] Có business schema validation, versioning và xử lý unknown event type.
- [ ] Có idempotency, redelivery/retry limits, DLQ/quarantine.
- [ ] Có monitoring theo endpoint ID và destination, không chỉ theo method name.
- [ ] Test registry IDs, nhận message từ **tất cả destinations**, xử lý failure.
- [ ] Với production, cấu hình secrets, TLS, ACL và broker provisioning.

## 15. Câu hỏi ôn tập

**1. Có thể đặt hai `@JmsListener` trên một method không?**  
Có. `@JmsListener` là repeatable annotation và Spring tạo riêng một listener endpoint/container cho mỗi khai báo.

**2. Có cần dùng `@JmsListeners` không?**  
Không trên Java 17+. Hai `@JmsListener` lặp trực tiếp là đủ; `@JmsListeners({...})` chỉ là container annotation tương đương.

**3. Hai annotations trên một method có phải một consumer đọc hai queue không?**  
Không. Hai endpoint có container/consumer riêng, nhưng gọi chung method.

**4. Hai listeners trên một queue có làm mỗi message chạy hai lần không?**  
Không theo semantics queue thông thường; chúng cạnh tranh nhận. Redelivery/duplicates vẫn có thể xảy ra do lỗi/transaction, không phải do annotation lặp.

**5. Nếu muốn hai hệ thống độc lập đều nhận event thì làm thế nào?**  
Thiết kế topic/subscriptions hoặc broker routing/fan-out phù hợp; không nhân đôi annotation trên queue và mong broadcast.

**6. `id` cần khác nhau không?**  
Có, nếu chỉ định; ID container trong registry phải duy nhất. Spring có thể tự sinh khi bỏ qua.

**7. Có thể dùng `containerFactory` khác nhau cho hai annotations không?**  
Có. Nhưng converter, ack/transaction và recovery policy khác nhau có thể ảnh hưởng cùng method.

**8. `concurrency="2-4"` có nghĩa gì?**  
Là giới hạn consumers của **endpoint tương ứng** theo khả năng factory, không phải số lượt xử lý mỗi message.

**9. `selector` có đọc `eventType` trong JSON body không?**  
Không tùy ý. JMS selector lọc header/property; producer nên đặt property phù hợp.

**10. Vì sao method chung cần thread-safe?**  
Hai containers có thể gọi cùng bean đồng thời trên các threads khác nhau; không dùng mutable field không bảo vệ.

**11. Có thể nhận message khác schema tại cùng method không?**  
Có thể về kỹ thuật nếu adapter/converter và validation xử lý được, nhưng dễ lỗi. Nếu business khác, nên tách method gọi chung service.

**12. Khi nào dùng dynamic endpoint registration?**  
Khi danh sách destinations thực sự cần thay đổi ở runtime; repeatable annotations chỉ định endpoints tĩnh trong mã.

## 16. Tài liệu tham khảo chính thức

1. [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
2. [Spring Framework — JmsListener annotation API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
3. [Spring Framework — JmsListeners container annotation API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/annotation/JmsListeners.html)
4. [Spring Framework — JmsListenerEndpointRegistry API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html)
5. [Spring Framework — JMS Overview](https://docs.spring.io/spring-framework/reference/6.2/integration/jms.html)
6. [Spring Framework — JMS Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
7. [Spring Boot 3.5 — JMS with Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
8. [Spring — Getting Started: Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
9. [Jakarta Messaging 3.1 Specification: Queue and Topic semantics, message selectors](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
10. [Apache ActiveMQ Artemis — Docker guide](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)