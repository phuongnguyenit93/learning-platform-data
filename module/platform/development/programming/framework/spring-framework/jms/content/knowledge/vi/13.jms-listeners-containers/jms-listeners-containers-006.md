# Từ message nhận được đến gọi phương thức xử lý trong Spring JMS

## 1. Một message đi qua những lớp nào?

Giả sử producer đưa một `TextMessage` chứa `ORDER-1001` vào queue `orders.in`. Trong ứng dụng Spring, ta chỉ viết:

```java
@Component
public class OrderListener {
    @JmsListener(destination = "orders.in")
    public void onOrder(String orderId) {
        System.out.println("Processing " + orderId);
    }
}
```

Đây là **một Spring-managed bean**, không phải chương trình Java độc lập. Câu hỏi quan trọng: **ai nhận message từ broker, ai gọi `onOrder`, và vì sao tham số Java `String` lại nhận được nội dung của `TextMessage`?**

Câu trả lời là một đường ống (pipeline) có nhiều thành phần:

```text
                      KHỞI TẠO ỨNG DỤNG
@EnableJms / cấu hình Spring Boot
          |
          v
Tìm bean và method có @JmsListener
          |
          v
JmsListenerEndpoint (bean, method, destination, id, selector...)
          |
          v
JmsListenerContainerFactory tạo MessageListenerContainer
          |
          v
Container khởi động, quản lý Connection/Session/Consumer


                      KHI CÓ MESSAGE
Producer --> broker --> queue/topic --> JMS MessageConsumer
                                            |
                                            v
                                 MessageListenerContainer
                                            |
                                            v
                              MessagingMessageListenerAdapter
                                            |
                                            v
                    Chuyển JMS Message / ánh xạ headers-payload
                                            |
                                            v
                 Giải tham số bằng MessageHandlerMethodFactory
                                            |
                                            v
                      OrderListener.onOrder(String orderId)
                                            |
                                            v
                              Business service / database
                                            |
                                            v
                      ACK / commit hoặc rollback theo cấu hình
```

Hai phần của sơ đồ không chạy cùng thời điểm. **Phần khởi tạo** đăng ký listener và tạo hạ tầng; **phần runtime** chỉ kích hoạt khi consumer nhận message. Annotation `@JmsListener` không phải một lời gọi method ngay lúc Java đọc annotation.

> **Thông điệp chính:** Spring tạo và quản lý listener container, rồi dùng adapter và bộ xử lý tham số để biến một **JMS Message** thành lời gọi **method Java**. Method của bạn chỉ là phần nghiệp vụ cuối đường ống, nhưng lỗi trước hoặc sau lời gọi vẫn ảnh hưởng ACK, retry và transaction.

## 2. Tách vai trò để không nhầm các API

| Thành phần | Chịu trách nhiệm | Không phải |
| --- | --- | --- |
| Broker (ví dụ ActiveMQ Artemis) | Lưu/chuyển phát message theo queue/topic, quyền, selector và chính sách broker | Nơi gọi trực tiếp method Java của Spring bean |
| `jakarta.jms.ConnectionFactory` | Cung cấp khả năng tạo kết nối JMS tới provider | Một message consumer đang chạy |
| `jakarta.jms.Connection`/`Session`/`MessageConsumer` | Tài nguyên JMS để nhận message; cách quản lý tùy container | Object nghiệp vụ |
| `MessageListenerContainer` | Quản lý consumer, threading, lifecycle, receive, transaction/ack và recovery | Payload converter hoặc service nghiệp vụ |
| `JmsListenerContainerFactory` | **Tạo và cấu hình** listener container cho endpoint | Một consumer duy nhất nhận mọi message |
| `@JmsListener` | Khai báo method Java là một endpoint có destination/id/selector/factory | Một lệnh chủ động `receive()` |
| `MessagingMessageListenerAdapter` | Thích nghi JMS callback thành invocation của method được annotate | Spring `JmsTemplate` |
| `MessageConverter` và header mapper | Chuyển nội dung/metadata giữa JMS message và biểu diễn Spring | Cơ chế ACK |
| `MessageHandlerMethodFactory` | Xây dựng invoker và giải tham số method (payload, header, raw message, session, validation...) | Broker hoặc listener container |
| Method của bean | Xử lý nghiệp vụ, ném exception khi thất bại | Tự bảo đảm commit DB + JMS atomic |
| `JmsTemplate` | Chủ yếu gửi và nhận **đồng bộ** khi application tự gọi; có thể dùng trong producer | Cơ chế bắt buộc để `@JmsListener` tự được gọi |

Có hai nghĩa “listener” cần phân biệt:

- `jakarta.jms.MessageListener` là interface thấp của Jakarta Messaging, có callback `onMessage(Message)`.
- `@JmsListener` là annotation của Spring để đăng ký một **method bình thường** làm handler; method không cần implement `jakarta.jms.MessageListener`.

## 3. Giai đoạn A — Spring khám phá và đăng ký @JmsListener

### 3.1. Đăng ký hạ tầng listener

Trong Java configuration, dùng:

```java
@Configuration
@EnableJms
public class JmsConfiguration {
}
```

Đây là **đoạn cấu hình trong dự án đã có Spring JMS dependency**; imports:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
```

`@EnableJms` bật hạ tầng annotation-driven. Trong Spring Framework 6.x, `JmsBootstrapConfiguration` đăng ký `JmsListenerAnnotationBeanPostProcessor`; thành phần này phát hiện các method mang `@JmsListener` trên bean được Spring quản lý. Spring Boot có auto-configuration JMS tương ứng, nhưng ghi `@EnableJms` tường minh giúp thấy ranh giới hạ tầng.

Nếu tạo instance bằng `new OrderListener()` mà không đăng ký làm Spring bean, Spring không tự tìm thấy method của instance ấy để tạo endpoint. Ngoài ra, package chứa listener phải được component scan hoặc bean phải được đăng ký bằng `@Bean`.

### 3.2. Annotation được biến thành endpoint

Với annotation:

```java
@JmsListener(
        id = "ordersListener",
        destination = "orders.in",
        containerFactory = "ordersListenerFactory")
public void onOrder(String orderId) {
    // nghiệp vụ
}
```

Spring lưu thông tin endpoint (đối tượng đích là bean, method, tên destination, ID và các tùy chọn) vào mô hình như `MethodJmsListenerEndpoint`. `JmsListenerEndpointRegistrar`/`JmsListenerEndpointRegistry` phối hợp tạo và đăng ký container bằng factory thích hợp.

Các thuộc tính quan trọng:

| Thuộc tính `@JmsListener` | Công dụng |
| --- | --- |
| `destination` | Tên queue/topic để container đăng ký consumer, được giải qua `DestinationResolver` |
| `containerFactory` | Tên bean factory dùng tạo container; nếu bỏ trống, Spring tìm default `jmsListenerContainerFactory` trừ khi đã cấu hình default khác |
| `id` | ID endpoint/container, hỗ trợ tra cứu qua `JmsListenerEndpointRegistry` |
| `selector` | Biểu thức JMS selector lọc dựa trên header/property được broker/provider hỗ trợ |
| `concurrency` | Giới hạn số consumer ở endpoint, theo khả năng của implementation |
| `subscription` | Subscription name, chủ yếu dùng trong kịch bản topic/durable subscription |

Nhiều endpoint có thể cùng dùng **một factory**, nhưng mỗi method annotated thường được phục vụ bởi một **listener container riêng** được tạo từ factory. Factory là **bản thiết kế**, không phải một container thay nhau gọi tất cả method.

### 3.3. Factory và registry quản lý lifecycle

`DefaultJmsListenerContainerFactory` thường tạo `DefaultMessageListenerContainer`; Spring còn hỗ trợ `SimpleJmsListenerContainerFactory` và các hình thức đăng ký khác. `JmsListenerEndpointRegistry` lưu những container được tạo qua hạ tầng annotation để bạn quản lý theo ID.

Ví dụ kiểm tra lifecycle, **đoạn bên trong bean đã inject `JmsListenerEndpointRegistry registry`**:

```java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");
if (container != null) {
    System.out.println("Listener running = " + container.isRunning());
}
```

Imports cần có:

```java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
```

Đây không phải chương trình standalone. `getListenerContainer(...)` trả về null khi không có endpoint ID tương ứng. Container được quản lý qua registry không nhất thiết xuất hiện như một bean độc lập để inject trực tiếp theo cùng tên; factory và registry là những bean quản lý hạ tầng.

## 4. Giai đoạn B — listener container nhận JMS Message

Khi container bắt đầu, nó dùng `ConnectionFactory` và tên destination để tạo các tài nguyên JMS cần thiết: `Connection`, `Session`, `MessageConsumer` theo cách mà implementation/caching/transaction yêu cầu.

Với `DefaultMessageListenerContainer`, container có các worker thread thực hiện vòng nhận bằng JMS `MessageConsumer.receive(...)` và chuyển message vào callback phù hợp. Vì vậy:

- Về **góc nhìn method nghiệp vụ**, nhận là bất đồng bộ: method được gọi khi có message, không cần tự gọi `receive`.
- Về **cơ chế nội bộ**, implementation vẫn có thể dùng blocking receive trên thread của container. Đừng đồng nhất “annotation-driven” với “không có thread nào block” hoặc “broker gọi trực tiếp method Java”.

`SimpleMessageListenerContainer` có cách khác: dùng `MessageConsumer.setMessageListener(...)` để provider chủ động gọi callback và giữ số session/consumer cố định. Hai implementation có các khả năng scaling/transaction khác nhau. Bài này dùng `DefaultMessageListenerContainer` cho ví dụ.

### 4.1. Điều kiện message tới đúng consumer

Container chỉ nhận khi cấu hình có hiệu lực:

- Kết nối tới **đúng broker** (URL, credentials, quyền).
- `destination` được resolve thành đúng queue/topic và có tài nguyên tương ứng theo chính sách provider.
- Nếu có `selector`, message có property/header thỏa biểu thức.
- Nếu dùng topic, cấu hình `pubSubDomain`, subscription/durability/shared semantics phù hợp.
- Container đang chạy và consumer được đăng ký hợp lệ.

Ví dụ selector:

```java
@JmsListener(
        destination = "orders.in",
        selector = "eventType = 'ORDER_CREATED'")
public void onCreated(String payload) {
    // Chỉ message có property eventType tương ứng mới phù hợp selector.
}
```

Selector là bộ lọc khi nhận, **không phải câu lệnh xóa message không phù hợp**. Với queue, message không khớp selector có thể chờ consumer khác; với topic, subscription semantics khác nhau. Không gắn selector để thay thế việc validate message trong business handler.

### 4.2. Queue không phát bản sao cho tất cả listener

Nếu hai endpoint cùng nghe queue `orders.in`, chúng là **competing consumers**; broker thường giao mỗi message cho một consumer phù hợp. Hai method cùng queue không tự chạy cho mọi message. Muốn fan-out, cần thiết kế topic/subscription hoặc phát các message riêng, không chỉ thêm annotation.

## 5. Giai đoạn C — adapter chuyển JMS callback thành lời gọi method Java

Spring không bắt bạn implement `jakarta.jms.MessageListener` trong mỗi class có `@JmsListener`. Với method annotated, Spring dùng mô hình `MethodJmsListenerEndpoint` và cơ chế `MessagingMessageListenerAdapter` để chuyển callback nhận message thành invocation phù hợp.

Luồng khái niệm:

```text
Nhận jakarta.jms.TextMessage
    body = "ORDER-1001"
    property eventType = "ORDER_CREATED"
    JMSMessageID, JMSCorrelationID, ...
                |
                v
DefaultMessageListenerContainer
                |
                v
MessagingMessageListenerAdapter.onMessage(jmsMessage, session)
                |
                v
JMS-to-Spring Message conversion + JMS header mapping
                |
                v
DefaultMessageHandlerMethodFactory / InvocableHandlerMethod
                |
                +--> @Payload String orderId
                +--> @Header("eventType") String eventType
                +--> jakarta.jms.Message raw / jakarta.jms.Session (nếu method khai báo)
                |
                v
OrderEventListener.consume(orderId, eventType)
```

Điểm cần hiểu:

1. **JMS message** là `jakarta.jms.Message` (`TextMessage`, `BytesMessage`, `MapMessage`...).
2. Spring có thêm abstraction **`org.springframework.messaging.Message<?>`** gồm payload và headers.
3. Adapter dùng các converter/header mapper được cấu hình để tạo nội dung có thể đưa vào handler.
4. `DefaultMessageHandlerMethodFactory` và các argument resolver xác định tham số method dựa trên kiểu/annotation, có thể chạy conversion/validation bổ sung.
5. Khi các tham số đã sẵn sàng, Spring gọi method được đăng ký trên bean; nếu handler ném exception, lỗi quay về cơ chế container/transaction.

Đây là **sơ đồ logic**, không phải cam kết mọi bản Spring/converter đều tạo đúng số bước hoặc class nội bộ như nhau. Khi cấu hình custom converter/handler method factory, chi tiết chuyển đổi có thể khác.

### 5.1. Các tham số method có thể nhận

```java
@JmsListener(destination = "orders.in")
public void consume(
        @Payload String orderId,
        @Header("eventType") String eventType,
        jakarta.jms.Message raw,
        jakarta.jms.Session session) throws jakarta.jms.JMSException {

    System.out.println(orderId);
    System.out.println(eventType);
    System.out.println(raw.getJMSMessageID());
}
```

Đây là **đoạn method minh họa** trong Spring bean, dùng imports:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
```

Giải thích:

- `@Payload String orderId`: dữ liệu message đã được converter chuyển thành `String`.
- `@Header("eventType") String eventType`: property JMS do producer đặt, được mapper đưa sang header tương ứng.
- `jakarta.jms.Message raw`: đối tượng message JMS gốc nếu method cần header/provider APIs mức thấp.
- `jakarta.jms.Session session`: session của thao tác nhận, có thể dùng khi cần gửi reply qua JMS API; **không được cache hoặc đóng tùy tiện**.

Không cần khai báo cả bốn tham số trong mọi method. Với case chỉ dùng payload, `public void consume(String orderId)` là đủ.

Với `org.springframework.messaging.Message<String>`, method có thể nhận đối tượng gồm **payload và headers** trong cùng tham số. Chú ý trùng tên `Message`: `jakarta.jms.Message` và `org.springframework.messaging.Message` là **hai interface khác nhau**; dùng fully qualified names khi cần đọc đồng thời.

### 5.2. Converter: TextMessage đến String không phải phép màu

Với `SimpleMessageConverter` thông thường của Spring JMS:

| Đầu vào JMS | Kiểu payload Java thường thấy |
| --- | --- |
| `TextMessage` | `String` |
| `BytesMessage` | `byte[]` |
| `MapMessage` | `Map` |
| `ObjectMessage` | Object được giải tuần tự hóa, cần kiểm soát trust/compatibility |

Kết quả thực tế phụ thuộc converter mà application đã cấu hình. Với JSON trong `TextMessage`, việc muốn map sang `record OrderCreated(String id)` hoặc DTO **không tự động được bảo đảm** bởi `SimpleMessageConverter`; phải cấu hình converter JSON phù hợp và thống nhất content type/type ID/schema.

Nếu method đòi `OrderCreated` nhưng converter chỉ trả `String` và không có phép chuyển phù hợp, lỗi có thể xảy ra **trước khi vào body handler**. Khi đó không tìm thấy log đầu method không có nghĩa broker chưa gửi: kiểm tra lỗi conversion/argument resolution của listener container.

### 5.3. Header mapper, validation và quy tắc giải tham số

Các annotation hữu ích:

| Ký hiệu | Vai trò |
| --- | --- |
| `@Payload` | Xác định tham số chứa body đã chuyển đổi |
| `@Header("eventType")` | Lấy một header/property được ánh xạ theo tên |
| `@Headers Map<String, Object>` | Nhận tập các header được ánh xạ |
| `@Valid @Payload SomeDto` | Kiểm tra bean validation nếu có validator và conversion tương ứng |
| `jakarta.jms.Message` | Truy cập raw JMS message |
| `jakarta.jms.Session` | Truy cập raw session của lần nhận |
| `org.springframework.messaging.Message<T>` | Nhận cả payload và headers theo abstraction Spring |

Sử dụng bean validation cần dependency và cấu hình validator thích hợp; annotation `@Valid` một mình không tạo được business validation rules hoặc JSON converter. Việc không resolve được một `@Header` bắt buộc, header sai kiểu hoặc payload không thể chuyển có thể khiến method **không được gọi**.

## 6. Ví dụ hoàn chỉnh với Spring Boot 3.x và Java 17+

Ví dụ gửi một `TextMessage` đến queue `orders.in`, container nhận, adapter chuyển body và property, rồi gọi service xử lý. Dùng **Spring Boot 3.x / Spring Framework 6.x / Java 17+**, namespace `jakarta.jms` và broker ActiveMQ Artemis.

Điều kiện: project Gradle Spring Boot đã có plugin và dependency management; broker đang chạy; queue `orders.in` đã được provision hoặc broker cho phép tự tạo đúng chính sách; credentials và quyền receive/send hợp lệ. Các file bên dưới là mã cho **project Spring Boot**, không phải các class có thể biên dịch riêng bằng `javac` mà không có dependencies.

### 6.1. Dependency

Trong `build.gradle` Groovy DSL của project Spring Boot 3.x, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Plugin Spring Boot và Java toolchain 17+ cần có trong project. `spring-boot-starter-artemis` cung cấp các phần cần thiết để Spring dùng Jakarta JMS với Artemis; không nhập nhầm `javax.jms`.

### 6.2. application.yml

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"

app:
  jms:
    orders-queue: "${JMS_ORDERS_QUEUE:orders.in}"
```

Thay các biến môi trường bằng thông tin môi trường thực hành. Không hardcode mật khẩu thật vào repository. Tên `orders.in` phải trùng với queue thực tế; việc có chuỗi tên trong YAML **không đồng nghĩa đã tạo queue trên broker**.

### 6.3. Boot application bật listener annotations

File `src/main/java/demo/pipeline/PipelineApplication.java`:

```java
package demo.pipeline;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class PipelineApplication {
    public static void main(String[] args) {
        SpringApplication.run(PipelineApplication.class, args);
    }
}
```

Annotation `@EnableJms` thể hiện tường minh bước đăng ký hạ tầng listener. Class `PipelineApplication` nằm ở package cha `demo.pipeline` nên component scan mặc định tìm thấy các bean demo cùng package.

### 6.4. Cấu hình container factory

File `src/main/java/demo/pipeline/OrdersJmsConfiguration.java`:

```java
package demo.pipeline;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
public class OrdersJmsConfiguration {

    @Bean("ordersListenerFactory")
    public DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
```

Phân tích:

- `ConnectionFactory` kết nối broker, được Spring Boot cung cấp khi đã cấu hình Artemis.
- Factory tạo các `DefaultMessageListenerContainer` cho endpoint dùng `containerFactory = "ordersListenerFactory"`.
- `sessionTransacted(true)` yêu cầu **local JMS transaction**: nếu handler hoàn tất, JMS commit; nếu thất bại và exception truyền ra đúng ranh giới, container có thể rollback để provider redeliver.
- `concurrency("1")` chọn một concurrent consumer cho **container của endpoint này**; **không** giới hạn tổng số consumer khi chạy nhiều instance ứng dụng.
- Đây là factory riêng, không yêu cầu thay đổi `JmsTemplate` producer mặc định.

**Lưu ý:** JMS transaction không tự bao trùm transaction của một database khác. Nếu service cập nhật DB rồi JMS commit thất bại, có thể có redelivery; ứng dụng thật phải idempotent.

### 6.5. Business service được gọi sau chuyển đổi

File `src/main/java/demo/pipeline/OrderProcessingService.java`:

```java
package demo.pipeline;

import org.springframework.stereotype.Service;

@Service
public class OrderProcessingService {

    public void process(String orderId, String eventType) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is blank");
        }
        if (!"ORDER_CREATED".equals(eventType)) {
            throw new IllegalArgumentException(
                    "Unsupported eventType: " + eventType);
        }

        System.out.printf(
                "HANDLER_CALLED orderId=%s eventType=%s%n",
                orderId, eventType);
    }
}
```

Service demo chỉ kiểm tra dữ liệu và in log. Nó chưa ghi database và không đại diện cho logic exactly-once. Việc tách service khỏi listener giúp test nghiệp vụ độc lập với hạ tầng JMS.

### 6.6. Listener nhận payload và header

File `src/main/java/demo/pipeline/OrderEventListener.java`:

```java
package demo.pipeline;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {
    private final OrderProcessingService service;

    public OrderEventListener(OrderProcessingService service) {
        this.service = service;
    }

    @JmsListener(
            id = "ordersListener",
            destination = "${app.jms.orders-queue}",
            containerFactory = "ordersListenerFactory")
    public void consume(
            @Payload String orderId,
            @Header("eventType") String eventType) {
        service.process(orderId, eventType);
    }
}
```

Khi nhận `TextMessage` body `ORDER-1001` có property `eventType = ORDER_CREATED`, adapter/argument resolver biến dữ liệu thành hai `String` và gọi `consume("ORDER-1001", "ORDER_CREATED")`. Method sau đó gọi `OrderProcessingService.process(...)`.

`@JmsListener` không tự tạo ra Java thread cho từng method; listener container điều phối thread nhận. Với singleton `@Component`, nhiều thread container (nếu tăng concurrency) **có thể cùng gọi method trên cùng bean**. Không đặt trạng thái mutable trong field của listener mà thiếu cơ chế thread safety.

### 6.7. Producer tạo message để thử đường đi

File `src/main/java/demo/pipeline/DemoPublisher.java`:

```java
package demo.pipeline;

import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class DemoPublisher {
    private final JmsTemplate jmsTemplate;
    private final String queue;

    public DemoPublisher(
            JmsTemplate jmsTemplate,
            @Value("${app.jms.orders-queue}") String queue) {
        this.jmsTemplate = jmsTemplate;
        this.queue = queue;
    }

    public void publish(String orderId) {
        jmsTemplate.send(queue, session -> {
            TextMessage msg = session.createTextMessage(orderId);
            msg.setStringProperty("eventType", "ORDER_CREATED");
            return msg;
        });
    }
}
```

`MessageCreator` của producer nhận một `Session` **để tạo outgoing message**, còn `MessagingMessageListenerAdapter` của consumer **xử lý incoming message**. Đừng đánh đồng hai chỗ có chữ callback.

### 6.8. Runner gửi một message khi bật profile demo

File `src/main/java/demo/pipeline/DemoRunner.java`:

```java
package demo.pipeline;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("demo-publish")
public class DemoRunner implements ApplicationRunner {
    private final DemoPublisher publisher;

    public DemoRunner(DemoPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        publisher.publish("ORDER-1001");
        System.out.println("PUBLISH_REQUESTED ORDER-1001");
    }
}
```

Chạy khi broker đã khởi động và queue có quyền send/receive:

```bash
./gradlew bootRun --args='--spring.profiles.active=demo-publish'
```

Nếu JMS gửi và nhận thành công, **hai dòng do ứng dụng tự in** có thể xuất hiện:

```text
PUBLISH_REQUESTED ORDER-1001
HANDLER_CALLED orderId=ORDER-1001 eventType=ORDER_CREATED
```

**Thứ tự hai dòng trên không được bảo đảm.** Consumer có thể chạy trước khi producer in dòng `PUBLISH_REQUESTED`, và console còn có các log Spring Boot/broker khác. Khi broker không kết nối được, thiếu quyền, queue không tồn tại hoặc conversion thất bại, không mong đợi cả hai dòng xuất hiện.

Do runner gửi một message mỗi lần khởi động với profile `demo-publish`, không bật profile này trong production.

## 7. Khi nào handler thật sự được gọi — và khi nào không?

Có nhiều điểm hỏng **trước** dòng đầu tiên trong handler:

| Bước | Lỗi ví dụ | Dấu hiệu |
| --- | --- | --- |
| Khởi tạo Spring context | Listener không phải Spring bean hoặc thiếu hạ tầng `@EnableJms` | Không có endpoint được đăng ký |
| Tạo listener container | `containerFactory` sai tên bean | Startup/configuration failure |
| Kết nối | Sai broker URL/credentials, broker down | Container recovery/reconnect; không gọi handler |
| Resolve destination | Sai tên queue, queue/topic mismatch, ACL thiếu | Consumer không nhận được message phù hợp |
| Selector | `selector` không khớp property | Message không được chuyển đến endpoint đó |
| Convert | JMS message type/schema không hợp converter | Method chưa được gọi, conversion failure |
| Map header | `@Header("eventType")` không có hoặc sai kiểu | Argument resolution failure trước body |
| Invoke method | Handler ném `IllegalArgumentException`/lỗi DB | Lỗi chạy **trong** handler |
| Commit/ACK | Transaction commit/connection bị lỗi | Handler có thể đã chạy nhưng JMS outcome khác mong đợi |

Vì vậy **“không thấy log trong `onMessage`” không có nghĩa broker chưa có message**. Hãy xem logs của container, exception converter, destination, selector và metrics broker trước khi quy lỗi cho business service.

### 7.1. Vì sao lỗi converter cũng ảnh hưởng retry?

`@Payload` và `@Header` được resolve trong đường đi trước khi gọi method nghiệp vụ. Nếu không chuyển đổi được message, adapter có thể ném exception ra container mặc dù method không hề được gọi. Với session transacted và exception được container xử lý theo cơ chế rollback, message có thể được **redeliver** và tiếp tục lỗi lặp.

Không nên đợi đến lúc vào service mới bắt “schema invalid” rồi kết luận đã xử lý mọi trường hợp poison message. Cần có chính sách DLQ, giới hạn redelivery và quan sát lỗi conversion/validation.

### 7.2. Vì sao nuốt exception có thể làm mất cơ hội retry?

Phản ví dụ:

```java
@JmsListener(destination = "orders.in")
public void broken(String body) {
    try {
        businessService.process(body);
    }
    catch (Exception ignored) {
        // Phản ví dụ: không báo thất bại cho listener container.
    }
}
```

Đây là **đoạn minh họa không độc lập**, giả định `businessService` có method tương ứng. Với một listener container có local JMS transaction, khi handler trở về bình thường, container có thể **commit JMS session**. Nếu business thất bại nhưng exception bị nuốt, message có thể bị đánh dấu hoàn tất sai.

Nên phân loại lỗi:

- Transient (DB tạm mất kết nối): để transaction rollback và retry/backoff theo chính sách.
- Permanent (payload/schema không hợp lệ): tránh lặp vô hạn; route tới DLQ/quarantine có kiểm soát.
- Duplicate: phát hiện qua eventId/business key để bỏ qua tác động lặp một cách an toàn.

Không phải container nào cũng tự tạo DLQ. Việc redelivery, số lần thử và destination DLQ thường phụ thuộc **cấu hình JMS provider/broker và application**.

## 8. Sau handler: ACK, commit, rollback không phải việc của annotation

Khi method `consume(...)` hoàn thành, container tiếp tục xử lý transaction/acknowledgment theo cấu hình. Với factory demo `setSessionTransacted(true)`:

```text
Broker giao message cho consumer
    |
    v
JMS local transaction của lần nhận
    |
    v
Adapter -> convert -> resolve arguments -> handler
    |
    +-- thành công ----------> commit JMS session
    |                               |
    |                               v
    |                          hoàn tất ACK theo provider
    |
    +-- exception -----------> rollback JMS session
                                    |
                                    v
                              có thể redelivery
                              theo broker policy
```

Đây là hành vi **ở mức JMS transaction**, không phải bảo đảm rằng business database đã commit atomically cùng JMS.

### 8.1. Các acknowledgment mode không giống nhau

- Với `sessionTransacted = true`, commit/rollback của JMS session quyết định kết quả cho message và các thao tác JMS trong transaction.
- Với `AUTO_ACKNOWLEDGE` và `DefaultMessageListenerContainer` không transacted, acknowledgment có thể thực hiện **trước khi** listener chạy, nên handler exception không mặc nhiên kích hoạt redelivery.
- Với `CLIENT_ACKNOWLEDGE`, thời điểm acknowledgment và sự tương tác với toàn bộ session phải được thiết kế cẩn thận; không tự cho rằng mỗi lời gọi ACK chỉ xác nhận một message.
- `DUPS_OK_ACKNOWLEDGE` cho phép acknowledgment lười; không giải quyết exactly-once.
- Khi dùng transaction manager ngoài hoặc provider-specific configuration, phải kiểm tra lại ranh giới thực tế của listener container.

**Không dựa vào giả định “Spring Boot mặc định transaction thế nào” nếu app định nghĩa factory custom.** Ví dụ đã cấu hình tường minh `setSessionTransacted(true)` để hành vi nhận rõ ràng.

### 8.2. Database transaction vẫn là ranh giới khác

Có thể xảy ra:

1. Service xử lý và commit database.
2. JMS commit không thành công do lỗi broker.
3. Provider redeliver message.
4. Service xử lý lặp nếu không có idempotency.

Vì vậy cần sự kiện có `eventId` hoặc khóa nghiệp vụ ổn định, deduplication/inbox/version-check theo transaction DB. Khi cần hợp đồng DB + JMS mạnh hơn, cân nhắc outbox, XA/JTA phù hợp hoặc cơ chế reconciliation; **`@JmsListener` và local JMS transaction không tự cung cấp exactly-once business**.

### 8.3. Acknowledgment không đồng nghĩa đã trả kết quả cho producer

JMS ACK của consumer là một phần protocol nhận. Nó **không tự gửi “OrderProcessed” về producer**. Nếu cần phản hồi nghiệp vụ, tạo destination phản hồi, correlation ID, timeout và mô hình retry/dedup phù hợp.

## 9. Một method Java có thể nhận gì ngoài String?

### 9.1. Nhận raw TextMessage để truy cập provider headers

```java
@JmsListener(destination = "orders.in")
public void receiveRaw(jakarta.jms.TextMessage raw)
        throws jakarta.jms.JMSException {
    String body = raw.getText();
    String id = raw.getJMSMessageID();
    boolean redelivered = raw.getJMSRedelivered();
    System.out.printf(
            "messageId=%s redelivered=%s body=%s%n",
            id, redelivered, body);
}
```

Đoạn này nằm trong bean có import `org.springframework.jms.annotation.JmsListener`. Method chỉ hỗ trợ `TextMessage`; nếu nhận kiểu khác thì việc bind thất bại. `JMSRedelivered` có thể giúp quan sát thử lại nhưng **không thay thế eventId và deduplication**. Metadata provider có thể khác nhau tùy cấu hình.

### 9.2. Spring Messaging Message

```java
@JmsListener(destination = "orders.in")
public void receiveSpringMessage(
        org.springframework.messaging.Message<String> message) {
    String body = message.getPayload();
    Object eventType = message.getHeaders().get("eventType");
    System.out.println(body + " / " + eventType);
}
```

Spring Messaging wrapper mang payload và headers. Nó **không phải** raw `jakarta.jms.Message`. Nếu muốn dùng trực tiếp API `getJMSCorrelationID()`, nhận raw JMS message như ví dụ 9.1 hoặc đọc header được mapper ánh xạ theo chuẩn.

### 9.3. Nhận DTO từ JSON có converter phù hợp

Ý tưởng:

```java
record OrderCreated(String orderId, String customerId) {}

@JmsListener(destination = "orders.json")
public void onJson(@Payload OrderCreated event) {
    orderService.create(event.orderId(), event.customerId());
}
```

Đây là **đoạn ý tưởng**, chưa phải file Java biên dịch độc lập; `orderService` là dependency được inject. Cần cấu hình `MessageConverter` phù hợp (ví dụ chuyển JSON text thành DTO bằng Jackson) và quy tắc xác định type, schema và header tương ứng. Không chỉ đặt body JSON trong `TextMessage` rồi mặc định mong `SimpleMessageConverter` tạo được `OrderCreated`.

### 9.4. Method trả kết quả không tự động đồng nghĩa business reply hoàn tất

Với handler trả một giá trị thay vì `void`, Spring có hỗ trợ gửi phản hồi đến destination `JMSReplyTo` hoặc destination được chỉ định bằng `@SendTo`, tùy cấu hình. Ví dụ ý tưởng:

```java
@JmsListener(destination = "orders.requests")
@SendTo("orders.responses")
public String handleRequest(String orderId) {
    return "RECEIVED:" + orderId;
}
```

Cần import `org.springframework.messaging.handler.annotation.SendTo` và thiết lập đúng destinations. Đây không phải behavior tự phát sinh từ một method `void` và cũng không phải bằng chứng database đã commit. Nếu cần business response đáng tin cậy, thiết kế rõ transaction và correlation giữa request/reply.

## 10. Container concurrency, threading và thứ tự

`@JmsListener` không tạo một object handler riêng cho mỗi message. Bean `@Component` thường là singleton; nhiều consumer threads có thể cùng invoke **cùng method trên cùng instance**.

Ví dụ factory:

```java
factory.setConcurrency("3-10");
```

Nghĩa là container `DefaultMessageListenerContainer` có thể duy trì ít nhất 3 concurrent consumers và mở rộng đến 10 theo điều kiện/chính sách. Giá trị hợp lệ và khả năng thay đổi động phụ thuộc container implementation.

Hệ quả cần chủ động giải quyết:

- Không sử dụng field mutable như `lastOrderId` trong singleton listener mà không có đồng bộ.
- Nhiều consumer có thể xử lý các message khác nhau và **commit kết quả không cùng thứ tự producer send**.
- Nhiều application replicas tạo thêm consumer, dù mỗi endpoint ở mỗi replica có `concurrency = 1`.
- Connection/session thuộc container và được dùng theo phạm vi thread/transaction thích hợp; không cache `Session` vào field hoặc đưa sang executor khác.
- Nếu handler chuyển việc sang `CompletableFuture.runAsync(...)` rồi trả về ngay, container có thể ACK/commit **trước khi việc nghiệp vụ nền hoàn thành**.

Khi cần thứ tự theo đối tượng, cân nhắc `aggregateId`/`sequence`, kiểm soát version trong DB, message grouping nếu broker hỗ trợ và giới hạn concurrency phù hợp. **JMS priority và một listener thread đơn lẻ không thay thế hợp đồng thứ tự nghiệp vụ**.

## 11. Quan sát đường đi khi lỗi: checklist gỡ rối

| Hiện tượng | Nên kiểm tra trước |
| --- | --- |
| Application boot nhưng không thấy handler | `@EnableJms`, bean được scan, tên factory, container running, queue, credentials |
| Có message trong broker nhưng listener không nhận | Sai broker URL/namespace, queue/topic mismatch, selector, consumer permissions, subscription |
| Không có log đầu method nhưng broker đã dequeue | Converter lỗi, header bắt buộc thiếu, argument resolver/validation lỗi trước invocation |
| Method được gọi nhưng payload không đúng | Type của JMS message, `MessageConverter`, charset/schema, producer encoding |
| Header trong method là null | Property không được producer set, tên header sai, mapper/converter custom |
| Handler ném exception, message quay lại liên tục | Local JMS rollback, redelivery limit, poison message, DLQ/backoff |
| Handler ném exception nhưng message mất | ACK xảy ra trước invocation, exception bị nuốt, policy broker/provider |
| Xử lý một event nhiều lần | JMS redelivery, duplicate publish, commit JMS thất bại sau DB commit, thiếu idempotency |
| Tăng concurrency rồi DB overload | Số consumer/replicas quá cao, pool database, handler latency, backpressure |
| Một queue nhưng hai listener không cùng nhận một message | Competing consumers semantics, không phải broadcast |
| Khi shutdown mất công việc đang xử lý | Graceful stop/drain in-flight, JMS transaction outcome, redelivery |

Các số liệu vận hành nên có (tên do ứng dụng tự định nghĩa): `listener_container_running`, `consumer_count`, `queue_depth`, `oldest_message_age`, `received_total`, `handler_success_total`, `handler_failure_total`, `redelivery_total`, `dlq_depth`, `processing_latency`. Đừng chỉ dựa vào log từ `System.out` ở ví dụ.

## 12. Kiểm thử đường đi từ message đến method

### 12.1. Unit test — xác nhận method gọi đúng service

File `src/test/java/demo/pipeline/OrderEventListenerTest.java`:

```java
package demo.pipeline;

import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class OrderEventListenerTest {

    @Test
    void delegatesConvertedPayloadAndHeaderToService() {
        OrderProcessingService service =
                mock(OrderProcessingService.class);

        OrderEventListener listener = new OrderEventListener(service);
        listener.consume("ORDER-1001", "ORDER_CREATED");

        verify(service).process("ORDER-1001", "ORDER_CREATED");
    }
}
```

Chạy:

```bash
./gradlew test --tests demo.pipeline.OrderEventListenerTest
```

Test đạt nếu mock nhận đúng lời gọi; Gradle có thể in `BUILD SUCCESSFUL`, nhưng toàn bộ stdout tùy cấu hình Gradle/JUnit. **Giới hạn quan trọng:** test này gọi method Java trực tiếp. Nó **không** chứng minh `@JmsListener` đã được đăng ký, broker đã giao `TextMessage`, adapter đã map `@Header` hay JMS transaction đã commit.

### 12.2. Integration test — phải có broker

Để kiểm tra **toàn bộ chuỗi**, cần môi trường có broker thực hoặc embedded/Testcontainers setup tương thích:

1. Khởi động context với `@EnableJms` và factory đã cấu hình, xác minh `JmsListenerEndpointRegistry.getListenerContainer("ordersListener")` trả container đang chạy.
2. Gửi một `TextMessage` với body `ORDER-1001` và string property `eventType = ORDER_CREATED`.
3. Dùng latch/probe/mock service với timeout để xác minh listener method thực sự được gọi. Không dùng `Thread.sleep` cố định làm oracle.
4. Gửi message thiếu `eventType`, quan sát lỗi **trước handler** và rollback/redelivery hoặc DLQ theo chính sách.
5. Cho service ném exception, xác minh JMS transaction policy và broker redelivery theo cấu hình.
6. Khởi động nhiều consumer/replica, xác minh handler thread-safe và business idempotency; quan sát queue depth, retries.
7. Tắt/mở broker để kiểm tra recovery, graceful shutdown và không mất sự kiện ngoài mong đợi.

**Kết quả kiểm thử nên tách:** “message gửi được”, “listener container nhận được”, “method được invoke”, “business state commit”, “JMS ACK/commit” và “producer có business reply”. Đây là các mốc khác nhau.

## 13. Tóm tắt bằng một bảng trách nhiệm

| Giai đoạn | Thành phần chủ đạo | Điều cần kiểm chứng |
| --- | --- | --- |
| Bean được tạo | Spring IoC | `@Component`/`@Bean` và component scan |
| Endpoint đăng ký | `@EnableJms` + annotation processor + registrar | Destination, factory, ID, selector |
| Container chạy | `JmsListenerContainerFactory`, registry và container | ConnectionFactory, lifecycle, consumer count |
| JMS message được nhận | Broker + JMS Session/Consumer | Queue/topic, quyền, selector, retry |
| Message được thích nghi | `MessagingMessageListenerAdapter` | Converter, payload, header mapping |
| Phương thức được chọn/gọi | `MessageHandlerMethodFactory`/invoker | `@Payload`, `@Header`, types, validation |
| Business xử lý | Service của ứng dụng | Logic đúng, idempotency, transaction DB |
| Message được ACK/rollback | Listener container/JMS transaction | ACK mode, rollback, redelivery, DLQ |

**Ghi nhớ:** “Từ message nhận được đến gọi phương thức xử lý” là một đường ống có hai vòng đời: **đăng ký listener lúc khởi tạo**, và **nhận → chuyển đổi → invoke → ACK/commit/rollback khi chạy**. Khi quan sát lỗi, phải xác định nó nằm ở bước nào; đặc biệt, lỗi converter có thể xảy ra trước method và việc method chạy xong chưa đồng nghĩa transaction hay nghiệp vụ đã hoàn tất ở mọi hệ thống.

### Tài liệu tham khảo

- Spring Framework 6.2 — Annotation-driven Listener Endpoints, `@JmsListener`, method signatures và `@SendTo`: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — Receiving a Message, message listener container, `MessageListenerAdapter` và transactions: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework API — `MessagingMessageListenerAdapter`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/adapter/MessagingMessageListenerAdapter.html
- Spring Framework API — `JmsListenerAnnotationBeanPostProcessor`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListenerAnnotationBeanPostProcessor.html
- Spring Framework API — `JmsListenerEndpointRegistry`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Boot 3.4 — JMS auto-configuration và listener factory: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
