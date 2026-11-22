# JmsListenerConfigurer và JmsListenerEndpointRegistrar trong Spring JMS

> **Ngữ cảnh:** Spring Framework JMS, đặc biệt cơ chế `@JmsListener` và đăng ký message listener endpoint bằng Java configuration.  
> **Mục tiêu:** Phân biệt `JmsListenerConfigurer`, `JmsListenerEndpointRegistrar`, `JmsListenerEndpointRegistry`, `JmsListenerEndpoint` và `JmsListenerContainerFactory`; biết lúc nào dùng annotation, lúc nào phải đăng ký endpoint theo code; tự viết ứng dụng Java 17+ có cả hai kiểu listener; hiểu transaction, quản lý ID, cấu hình method invocation, lifecycle và giới hạn của đăng ký động.

**Phiên bản minh họa:** Spring Framework 6.2.x, Spring Boot 3.5.x, Jakarta Messaging (`jakarta.jms`) và Apache ActiveMQ Artemis trong ví dụ thực hành. Spring 5.x dùng `javax.jms`; không trộn namespace cũ với Java 17+/Boot 3.x.

## 1. Vấn đề mà hai thành phần này giải quyết

Với trường hợp đơn giản, Spring cho phép khai báo một phương thức thành JMS consumer:

~~~java
@Component
class OrderConsumer {
    @JmsListener(destination = "orders.in")
    public void onOrder(String orderId) {
        // Xử lý message.
    }
}
~~~

Spring phát hiện annotation, tạo listener container và gọi phương thức khi có message. Nhưng ứng dụng thực tế có thể muốn:

- Thay **default listener container factory** cho tất cả endpoint không chỉ định `containerFactory`.
- Cấu hình cơ chế chuyển đổi/thẩm định tham số cho **phương thức có `@JmsListener`**.
- Đăng ký **endpoint mới bằng code** thay vì viết annotation tại một method cụ thể.
- Dùng những queue/selector/subscription được xác định từ cấu hình tin cậy khi khởi động.
- Gắn những endpoint khác nhau với những factory khác nhau (transaction, concurrency, destination resolver...).
- Lấy ID của listener container để quan sát, tạm dừng hoặc khởi động lại theo vận hành.

`JmsListenerConfigurer` và `JmsListenerEndpointRegistrar` được thiết kế cho phần **tùy biến và đăng ký lúc khởi tạo**, trong khi `JmsListenerEndpointRegistry` quản lý các container trong vòng đời của ứng dụng.

### Công thức ghi nhớ

~~~text
@JmsListener     -> cách khai báo endpoint trên method
JmsListenerConfigurer
                 -> nơi Spring gọi code tùy biến đăng ký endpoint
JmsListenerEndpointRegistrar
                 -> đối tượng nhận cấu hình và endpoint declarations
JmsListenerEndpoint
                 -> mô tả một endpoint (ID, destination, callback...)
JmsListenerContainerFactory
                 -> tạo MessageListenerContainer từ mô tả endpoint
JmsListenerEndpointRegistry
                 -> giữ, tra cứu và quản lý lifecycle containers
MessageListenerContainer
                 -> chạy JMS consumer, session, polling/callback và listener
~~~

**Sai lầm cần tránh:** registrar **không phải** một producer/consumer và **không phải** registry của những container đã chạy. Nó là cầu nối để **đưa khai báo endpoint vào quá trình tạo container**.

## 2. Phân biệt chính xác từng API

| Thành phần | Package Spring | Vai trò chính | Ví dụ thao tác |
| --- | --- | --- | --- |
| `@JmsListener` | `org.springframework.jms.annotation` | Gắn destination/ID/selector/factory vào Java method | `@JmsListener(destination="orders.in")` |
| `@EnableJms` | `org.springframework.jms.annotation` | Bật infrastructure phát hiện listener annotation | Đặt trên `@Configuration` hoặc app class |
| `JmsListenerConfigurer` | `org.springframework.jms.annotation` | Callback tùy biến listener registration | `configureJmsListeners(registrar)` |
| `JmsListenerEndpointRegistrar` | `org.springframework.jms.config` | Nhận các endpoint/factory và handler method factory | `registerEndpoint(endpoint, factory)` |
| `JmsListenerEndpoint` | `org.springframework.jms.config` | Mô hình endpoint, không trực tiếp là consumer | `getId()`, `getDestination()`... |
| `SimpleJmsListenerEndpoint` | `org.springframework.jms.config` | Endpoint dùng một JMS `MessageListener` thực | `setMessageListener(...)` |
| `MethodJmsListenerEndpoint` | `org.springframework.jms.config` | Mô hình endpoint gọi một Java method | Dùng trong hạ tầng method-based listener |
| `JmsListenerContainerFactory<?>` | `org.springframework.jms.config` | Chiến lược tạo container từ endpoint | `createListenerContainer(endpoint)` |
| `DefaultJmsListenerContainerFactory` | `org.springframework.jms.config` | Tạo `DefaultMessageListenerContainer` | `setSessionTransacted(true)` |
| `JmsListenerEndpointRegistry` | `org.springframework.jms.config` | Sở hữu/truy vấn/điều khiển các listener containers đã đăng ký | `getListenerContainer(id)`, `stop()` |

### 2.1. Registrar chỉ làm công việc đăng ký

Interface `JmsListenerConfigurer` có đúng một callback cần triển khai:

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    // Thiết lập default factory, method factory hoặc register endpoints.
}
~~~

Spring gọi callback này thông qua listener annotation infrastructure khi khởi tạo application context. Bạn **không** tự tạo một `JmsListenerEndpointRegistrar` tùy ý rồi kỳ vọng các listener được kích hoạt: Spring đã tạo và nối registrar với registry của context.

### 2.2. Endpoint không phải container

`SimpleJmsListenerEndpoint` chỉ mô tả endpoint. Các lời gọi:

~~~java
var endpoint = new SimpleJmsListenerEndpoint();
endpoint.setId("ordersDynamic");
endpoint.setDestination("orders.in");
endpoint.setMessageListener(message -> {
    // callback xử lý raw JMS Message
});
~~~

**Chưa tạo consumer** và chưa mở connection. Sau khi được `registrar.registerEndpoint(...)`, hạ tầng dùng factory xây dựng container và registry điều phối nó theo lifecycle. Một endpoint thường tương ứng một listener container; container có thể mở nhiều JMS consumers nếu cấu hình concurrency.

### 2.3. Registry là nơi nhìn thấy container thực sự

Bạn có thể inject `JmsListenerEndpointRegistry` và:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersDynamic");

if (container != null) {
    System.out.println("running=" + container.isRunning());
}
~~~

Đoạn là **mảnh code trong bean Spring**; cần imports của registry và `org.springframework.jms.listener.MessageListenerContainer`. Registry cũng chứa containers sinh từ `@JmsListener` có ID được đăng ký bởi hạ tầng. Những container này **không nhất thiết là Spring beans độc lập**, nên đừng tìm chúng bằng cách autowire một bean container theo tên endpoint.

## 3. Vòng đời từ annotation/configurer tới JMS consumer

Sơ đồ cơ chế:

~~~text
@SpringBootApplication / @EnableJms
                |
  JmsListenerAnnotationBeanPostProcessor
                |
       quét @JmsListener methods
                |
      nhận JmsListenerConfigurer
                |
  configureJmsListeners(registrar)
        |                |
        |                +--> registerEndpoint(SimpleJmsListenerEndpoint)
        |
        +--> setContainerFactory / setMessageHandlerMethodFactory
                |
      JmsListenerEndpointRegistrar
                |
        JmsListenerEndpointRegistry
                |
      JmsListenerContainerFactory
                |
        MessageListenerContainer
                |
       jakarta.jms.Consumer(s)
                |
           JMS broker
~~~

Cần tách **hai thời điểm**:

1. **Startup registration:** đọc annotations, gọi `configureJmsListeners`, gom endpoint definitions, tạo containers và quản lý chúng thông qua registry.
2. **Runtime operations:** tra cứu trạng thái, stop/start, và khi cần có thể đăng ký thêm một endpoint qua **registry** với factory cụ thể. Đây **không** phải lúc gọi lại startup registrar.

Đừng nghĩ callback `configureJmsListeners` được gọi cho mỗi message hoặc mỗi lần broker reconnect. Nó là callback **cấu hình infrastructure** trong quá trình bootstrap, không phải business handler.

### Ghi nhớ về Spring Boot

Spring Boot có thể tự cấu hình JMS infrastructure khi starter được bật, và trên những cấu hình chuẩn có thể phát hiện `@JmsListener` không cần tự khai báo `@EnableJms`. Trong tài liệu Java configuration và lab bên dưới vẫn đặt **`@EnableJms` tường minh** để chỉ ra cơ chế Spring. Không khai báo trùng những infrastructure beans đặc biệt nếu Boot đã cấu hình đủ.

## 4. Khi nào dùng @JmsListener, khi nào implement JmsListenerConfigurer?

| Tình huống | Cách thường phù hợp | Vì sao |
| --- | --- | --- |
| Một queue cố định và handler dạng Java method | `@JmsListener` | Ngắn gọn, type conversion/argument resolution thuận tiện |
| Nhiều listener cố định với factories khác nhau | `@JmsListener(containerFactory="...")` | Rõ quan hệ endpoint-factory |
| Thay default factory cho các listener chưa chỉ định | `JmsListenerConfigurer` + `registrar.setContainerFactory(...)` | Tập trung cấu hình |
| Cài đặt method argument conversion/validator | `registrar.setMessageHandlerMethodFactory(...)` | Tác động tới invocation của annotated method endpoints |
| Endpoint do cấu hình tin cậy xác định lúc khởi động | `JmsListenerConfigurer` + `registerEndpoint(...)` | Không phải biên dịch annotation riêng cho từng cấu hình |
| Xử lý JMS `MessageListener` callback raw | `SimpleJmsListenerEndpoint` | Không có method argument binding của `@JmsListener` |
| Quản lý stop/start container bằng ID | `JmsListenerEndpointRegistry` | Quản lý runtime lifecycle |
| Thêm/bỏ endpoint **khi app đang chạy** | Registry APIs + một coordinator được kiểm soát | Không dùng startup registrar như dynamic registry |
| Hệ thống nhiều tenant, hàng nghìn queue động | Cân nhắc topology + giới hạn broker và factory | Mỗi endpoint/container có chi phí; không tạo vô hạn theo user input |

**Không cần dùng cả ba thành phần mỗi khi có `@JmsListener`.** Annotation đơn giản có thể đủ; chỉ đưa configurer/registrar vào khi có yêu cầu cấu hình thật sự.

## 5. Callback configureJmsListeners và những phương thức quan trọng

Trong `JmsListenerConfigurer.configureJmsListeners(JmsListenerEndpointRegistrar registrar)`, có ba nhóm tùy biến chính:

### 5.1. Chọn default container factory

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    registrar.setContainerFactory(myFactory);
}
~~~

Khi endpoint được đăng ký **không kèm factory tường minh**, registrar dùng default. Bạn cũng có thể thiết lập theo tên:

~~~java
registrar.setContainerFactoryBeanName("jmsListenerContainerFactory");
~~~

Tên này phải tham chiếu **bean factory đã có** và resolver/bean factory context phải được nối đúng. Không coi chuỗi tên là một destination hay ID listener container.

Một endpoint đăng ký rõ factory có thể được tạo theo:

~~~java
registrar.registerEndpoint(endpoint, highReliabilityFactory);
~~~

Với lời gọi này, factory truyền vào **ưu tiên cho chính endpoint đó**, không phụ thuộc default. Đây là cách an toàn khi nhiều loại listener có transaction/concurrency khác nhau.

### 5.2. Đăng ký endpoint bằng code

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    SimpleJmsListenerEndpoint endpoint =
            new SimpleJmsListenerEndpoint();

    endpoint.setId("auditEvents");
    endpoint.setDestination("audit.events");
    endpoint.setMessageListener(message -> {
        // Đọc jakarta.jms.Message và xử lý.
    });

    registrar.registerEndpoint(endpoint, auditFactory);
}
~~~

Điều kiện:
- `auditFactory` là `JmsListenerContainerFactory` đã được quản lý/cấu hình.
- `"auditEvents"` là **ID unique trong registry**, không phải tên queue.
- `"audit.events"` là **destination** broker, có thể có nhiều endpoints cùng destination nhưng sẽ tạo competing consumers nếu là Queue.
- Handler `MessageListener.onMessage(Message)` không được khai báo ném checked `JMSException`; nếu đọc `TextMessage.getText()` cần try/catch và chuyển thành unchecked exception phù hợp.
- Endpoint sẽ được registrar đăng ký và container xử lý lifecycle; **không** tự gọi `new Thread(...)` hoặc tự đóng JMS Session trong callback.

### 5.3. Cấu hình phương thức handler cho @JmsListener

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    registrar.setMessageHandlerMethodFactory(myHandlerMethodFactory);
}
~~~

`MessageHandlerMethodFactory` là abstraction để xây dựng invoker cho các **method-based endpoints**; default của Spring là `DefaultMessageHandlerMethodFactory`. Có thể cấu hình validator/conversion cho các annotated method, chẳng hạn `@Valid` payload và `@Header` argument.

Đây là **hai tầng khác nhau**:
- `MessageHandlerMethodFactory` kiểm soát cách **Java method** được gọi và arguments được resolve.
- `JmsListenerContainerFactory` kiểm soát **JMS listener container**: connection factory, transaction, concurrency, consumer caching, destination resolver, error handling...

**`setMessageHandlerMethodFactory` không tự cài một JMS `MessageConverter` vào mọi `SimpleJmsListenerEndpoint`.** Simple endpoint gọi trực tiếp raw `jakarta.jms.MessageListener`; muốn JSON DTO cần đọc body/parse chủ động hoặc thiết kế method-based endpoint có converter đúng.

## 6. Spring configuration: một default factory và endpoint tường minh

Mẫu gọn, phù hợp Spring Framework 6.x:

~~~java
@Configuration
@EnableJms
public class ConsumerConfig implements JmsListenerConfigurer {

    private final JmsListenerContainerFactory<?> criticalFactory;

    public ConsumerConfig(
            JmsListenerContainerFactory<?> criticalFactory) {
        this.criticalFactory = criticalFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        registrar.setContainerFactory(criticalFactory);

        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("auditPoller");
        endpoint.setDestination("audit.in");
        endpoint.setMessageListener(message -> {
            // Kiểm tra body/headers và xử lý theo hợp đồng.
        });

        registrar.registerEndpoint(endpoint, criticalFactory);
    }
}
~~~

Đây là **mảnh class cấu hình**, cần imports `@Configuration`, `@EnableJms`, `JmsListenerConfigurer`, `JmsListenerEndpointRegistrar`, `JmsListenerContainerFactory`, `SimpleJmsListenerEndpoint`. `criticalFactory` phải là bean tồn tại; nếu có nhiều factories, dùng `@Qualifier` để không injection mơ hồ. Khi factory được truyền tường minh trong `registerEndpoint`, phần `setContainerFactory` chỉ hữu ích cho những endpoint **không chỉ định factory** khác trong cùng registration setup.

**Không dùng cấu hình này nguyên xi để tạo container production** nếu chưa xác định error/retry, transaction, schema và quyền truy cập destination.

## 7. Tên, định danh và tính duy nhất

Có ba khái niệm thường bị lẫn:

| Tên | Ví dụ | Vai trò |
| --- | --- | --- |
| **Endpoint/container ID** | `"billingWorker"` | Định danh trong `JmsListenerEndpointRegistry` để quản lý |
| **Destination name** | `"billing.commands"` | Queue hoặc Topic broker mà endpoint tiêu thụ |
| **Container factory bean name** | `"businessListenerFactory"` | Tên Spring bean dùng để tạo container |

Ví dụ:

~~~java
@JmsListener(
    id = "billingWorker",
    destination = "billing.commands",
    containerFactory = "businessListenerFactory")
public void handle(String command) {
    // ...
}
~~~

`id` là khóa lookup:

~~~java
registry.getListenerContainer("billingWorker");
~~~

`destination` là nơi nhận message, không dùng để lookup container trừ khi bạn cố tình đặt ID trùng tên destination. Đặt ID khác nhau để dễ chẩn đoán.

### Chống ID collision

- Khi dùng nhiều `JmsListenerConfigurer`, xem xét tổng tập endpoint IDs trong **cùng registry**.
- Không tái dùng ID của một `@JmsListener` để đăng ký thêm programmatic endpoint.
- Nếu đăng ký endpoint từ danh sách cấu hình, chuẩn hóa và validate ID; đảm bảo duy nhất trước khi gọi registrar.
- Nếu không đặt `id` cho `@JmsListener`, Spring có thể tạo ID tự động; nó không phải contract ổn định để vận hành lâu dài.
- Không tự động xóa/ghi đè container cũ khi ID trùng; registry thường từ chối cấu hình trùng hoặc gây lỗi bootstrap.

### Nhiều endpoint trên cùng Queue có phải “nhân bản” message?

**Không.** Nếu là Queue, hai listener cùng destination thường trở thành **competing consumers**; mỗi message được phân phối tới một consumer phù hợp, không phát cho cả hai. Nếu cần hai nhóm độc lập mỗi nhóm nhận một bản, dùng Topic với subscription phù hợp hoặc kiến trúc queue per group.

Nếu là Topic, cần xem `pubSubDomain`, durable/shared subscription, client ID, subscription name, selector, retention và behavior broker; **registrar không tự biến Queue thành Topic**.

## 8. Chọn factory và kế thừa cấu hình Spring Boot

### 8.1. Tại sao factory quan trọng?

`DefaultJmsListenerContainerFactory` có thể cấu hình:
- `ConnectionFactory` và `DestinationResolver`.
- `pubSubDomain` cho Queue/Topic.
- `sessionTransacted` hoặc transaction manager phù hợp.
- `concurrency` (`"1"`, `"3-10"`...).
- JMS selector/subscription behavior do endpoint và container thỏa thuận.
- MessageConverter và request–reply behavior đối với adapter được Spring hỗ trợ.
- Error/recovery policy, caching, task executor, nhận message khi stop...

Nên **không** coi `JmsListenerEndpointRegistrar` là chỗ thay mọi thiết lập của listener container. Registrar chỉ chọn factory và gửi endpoint definition; **factory quyết định container hình thành thế nào**.

### 8.2. Tránh mất Boot defaults khi tự new factory

Với Spring Boot 3.5.x, cách tạo factory tùy chỉnh kế thừa auto-configuration:

~~~java
@Bean("demoFactory")
DefaultJmsListenerContainerFactory demoFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {

    var factory = new DefaultJmsListenerContainerFactory();

    configurer.configure(
        factory,
        ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

    factory.setSessionTransacted(true);
    factory.setConcurrency("1");
    return factory;
}
~~~

Các imports chính: `jakarta.jms.ConnectionFactory`; `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`; `org.springframework.boot.jms.ConnectionFactoryUnwrapper`; `org.springframework.jms.config.DefaultJmsListenerContainerFactory`; `org.springframework.context.annotation.Bean`.

Đây là **bean method**, không phải file Java độc lập. `ConnectionFactoryUnwrapper.unwrapCaching` (Boot 3.5) loại wrapper cache khi giao cho listener container, tránh một số vấn đề cache chia sẻ trong vòng đời polling/recovery. `configurer.configure(...)` áp dụng những setting Boot đã chuẩn bị; sau đó mới ghi đè transaction/concurrency theo mục tiêu.

### 8.3. Factory mặc định và override

Khi `@JmsListener` không khai báo `containerFactory`, Spring thường tìm bean tên `jmsListenerContainerFactory`. Registrar có thể đặt một **default factory khác** cho endpoint không chỉ định.

Với programmatic endpoint, cách rõ ràng nhất khi có nhiều factories:

~~~java
registrar.registerEndpoint(endpoint, demoFactory);
~~~

Đừng đoán Spring sẽ tự lấy factory có type phù hợp nếu trong context có nhiều bean tương tự. Trong hệ thống có nhiều policies, đặt tên factory rõ ràng và dùng `@Qualifier`/explicit registration.

## 9. Lab Java 17+ hoàn chỉnh: annotation + programmatic endpoint

Lab tạo **hai queue khác nhau**, mỗi queue một listener:
- `orders.annotation`: handler qua `@JmsListener`.
- `payments.programmatic`: raw `MessageListener` do `JmsListenerConfigurer` đăng ký qua `JmsListenerEndpointRegistrar`.

Một `OutcomeLog` đợi cả hai callback chạy rồi in tổng hợp theo thứ tự cố định. Lab cũng dùng `JmsListenerEndpointRegistry` để xác minh hai container đã được đăng ký.

### 9.1. Khởi tạo Maven project

Dùng https://start.spring.io/:
- Java 17+, Maven, Spring Boot **3.5.x**.
- Group `com.example`, artifact `jms-registrar-lab`.
- Java package `com.example.jmsregistrarlab`.
- Dependency **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).

Thêm vào phần `<dependencies>` của `pom.xml` (có Spring Boot parent/BOM):

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Dependency này bổ sung broker nhúng cho lab, không phải toàn bộ `pom.xml`. Giữ version Artemis do Boot BOM quản lý. Broker nhúng chỉ để học, không dùng chứng minh persistent backlog, high availability hoặc failover production.

### 9.2. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-registrar-lab
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.annotation,payments.programmatic
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.main.web-application-type=none
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Vì app không có web server, hai JMS listeners vẫn giữ các background tasks hoạt động sau runner. Dừng ứng dụng bằng Ctrl+C theo graceful shutdown thay vì giả định runner trả về là process tự thoát.

### 9.3. File 1 — Entry point, factory và sender

Lưu `src/main/java/com/example/jmsregistrarlab/JmsRegistrarLabApplication.java`:

~~~java
package com.example.jmsregistrarlab;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class JmsRegistrarLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsRegistrarLabApplication.class, args);
    }

    @Bean("demoFactory")
    DefaultJmsListenerContainerFactory demoFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }

    @Bean
    ApplicationRunner publishDemo(
            JmsTemplate template,
            JmsListenerEndpointRegistry registry,
            OutcomeLog results) {

        return args -> {
            if (registry.getListenerContainer("annotatedOrders") == null) {
                throw new IllegalStateException(
                        "Missing annotatedOrders listener container");
            }
            if (registry.getListenerContainer("programmaticPayments") == null) {
                throw new IllegalStateException(
                        "Missing programmaticPayments listener container");
            }

            template.convertAndSend("orders.annotation", "order-101");
            template.convertAndSend("payments.programmatic", "pay-202");

            if (!results.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listeners did not finish inside test budget");
            }

            System.out.println("HANDLED=" + results.snapshot());
        };
    }
}
~~~

**Tại sao có `@EnableJms`?** Nó minh họa Spring listener annotation infrastructure. Boot có thể auto-enable trong cấu hình chuẩn; việc khai báo một lần ở app class giúp code rõ ràng.

**Tại sao `setSessionTransacted(true)`?** Khi handler ném unchecked exception, container có thể rollback transaction JMS để broker redeliver theo policy. Chỉ đặt transaction JMS không đảm bảo DB transaction hoặc external side effects atomic.

### 9.4. File 2 — Ghi nhận kết quả từ hai listener

File `src/main/java/com/example/jmsregistrarlab/OutcomeLog.java`:

~~~java
package com.example.jmsregistrarlab;

import java.util.concurrent.ConcurrentSkipListSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

@Component
public class OutcomeLog {

    private final CountDownLatch latch = new CountDownLatch(2);
    private final ConcurrentSkipListSet<String> values =
            new ConcurrentSkipListSet<>();

    public void record(String entry) {
        values.add(entry);
        latch.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    public String snapshot() {
        return String.join("|", values);
    }
}
~~~

`ConcurrentSkipListSet` tạo thứ tự có thể lặp lại để in stdout, bất kể thread của listener annotation hay programmatic chạy trước. `CountDownLatch` giúp runner chờ hai callbacks thay vì đoán lịch thread. Lab có hai message không trùng; trong production **không** dùng một latch đếm cố định để quản lý queue vô hạn.

### 9.5. File 3 — Listener dùng @JmsListener

File `src/main/java/com/example/jmsregistrarlab/AnnotatedOrders.java`:

~~~java
package com.example.jmsregistrarlab;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class AnnotatedOrders {

    private final OutcomeLog results;

    public AnnotatedOrders(OutcomeLog results) {
        this.results = results;
    }

    @JmsListener(
            id = "annotatedOrders",
            destination = "orders.annotation",
            containerFactory = "demoFactory")
    public void onOrder(String orderId) {
        results.record("ANNOTATION:" + orderId);
    }
}
~~~

Spring chuyển `TextMessage` body do `convertAndSend(String)` tạo thành tham số `String` của annotated method theo converter mặc định, và container quản lý việc nhận. Không tự lấy/đóng JMS connection trong method này.

### 9.6. File 4 — Configurer và registrar

File `src/main/java/com/example/jmsregistrarlab/ProgrammaticListeners.java`:

~~~java
package com.example.jmsregistrarlab;

import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;

@Configuration(proxyBeanMethods = false)
public class ProgrammaticListeners implements JmsListenerConfigurer {

    private final OutcomeLog results;
    private final DefaultJmsListenerContainerFactory demoFactory;

    public ProgrammaticListeners(
            OutcomeLog results,
            @Qualifier("demoFactory")
            DefaultJmsListenerContainerFactory demoFactory) {

        this.results = results;
        this.demoFactory = demoFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("programmaticPayments");
        endpoint.setDestination("payments.programmatic");

        endpoint.setMessageListener(message -> {
            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalArgumentException(
                        "Expected TextMessage");
            }

            try {
                results.record("PROGRAM:" + textMessage.getText());
            } catch (JMSException ex) {
                throw new IllegalStateException(
                        "Cannot read JMS TextMessage", ex);
            }
        });

        // Dùng factory tường minh, không dựa vào bean mặc định.
        registrar.registerEndpoint(endpoint, demoFactory);
    }
}
~~~

**Điểm kiểm tra API:**
- `ProgrammaticListeners` implement `org.springframework.jms.annotation.JmsListenerConfigurer` đúng package.
- Phương thức callback nhận `org.springframework.jms.config.JmsListenerEndpointRegistrar`, không phải một `JmsListenerEndpointRegistry`.
- `SimpleJmsListenerEndpoint` nhận **`jakarta.jms.MessageListener`**, nên lambda thấy raw JMS `Message`. Nó **không tự bind tham số `String` như `@JmsListener`**.
- `TextMessage.getText()` có checked `JMSException`; ví dụ bắt và chuyển sang unchecked exception để có thể truyền qua interface `MessageListener`.
- `registrar.registerEndpoint(endpoint, demoFactory)` chỉ rõ factory được dùng cho endpoint.
- `"programmaticPayments"` là ID trong registry; `"payments.programmatic"` là queue name.
- Mọi tệp Java có đúng một public top-level class trùng tên file; package/imports đầy đủ.

### 9.7. Chạy và kết quả

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Khi Artemis embedded chạy đúng, hai queue bắt đầu trống, không có consumer khác cạnh tranh và cả hai callbacks hoàn tất trong 10 giây, ứng dụng in dòng:

~~~text
HANDLED=ANNOTATION:order-101|PROGRAM:pay-202
~~~

Log khởi động của Spring/Artemis có thể xuất hiện ở trước/sau dòng này; không khẳng định toàn bộ stdout của Spring chỉ có một dòng. `ConcurrentSkipListSet` sắp xếp hai kết quả theo tên, nên không phụ thuộc listener nào xử lý trước.

**Cảnh báo về tính đúng đắn:** `OutcomeLog.record` được gọi **trong** callback, có thể trước JMS session commit cuối cùng. Dòng `HANDLED` chứng minh callback chạy, **không phải** bằng chứng chính xác rằng broker đã commit message, dữ liệu DB đã ghi hoặc side effect được thực hiện đúng một lần. Muốn test transaction/retry phải quan sát broker/DB state trong integration test riêng.

### 9.8. Kịch bản tự thử

1. Tạm gỡ annotation `@EnableJms` trong lab; nếu Boot tự bật JMS listener infrastructure, code có thể vẫn hoạt động. Không tự kết luận annotation là “vô dụng” ở dự án Spring Framework thuần không có Boot.
2. Thay queue `payments.programmatic` bằng một queue không tồn tại và tắt auto-create ở broker staging; xem lỗi startup/recovery và sửa mapping destination.
3. Thay `endpoint.setId("programmaticPayments")` bằng `"annotatedOrders"` để quan sát lỗi trùng ID trong test; khôi phục trước khi đưa code vào production.
4. Cho programmatic listener cố tình ném exception trước `record`; xem broker redelivery/rollback với `sessionTransacted=true` và retry policy.
5. Gửi một `BytesMessage` vào `payments.programmatic`; handler phải reject vì chỉ chấp nhận `TextMessage`.
6. Thêm JMS selector vào endpoint (`endpoint.setSelector("kind = 'payment'")`) rồi gán đúng JMS property `kind` trên producer; message thiếu property sẽ không khớp.
7. Thay factory thành một bean không transacted; kiểm tra sự khác nhau trong khả năng redelivery khi callback lỗi, không dựa vào đúng tên endpoint.
8. Dùng registry in `getListenerContainerIds()` để xem ID khác với destination; không thay tên container đang vận hành mà không sửa monitoring.

## 10. Registrar và Registry: khác biệt cần nhớ khi vận hành

### 10.1. Giai đoạn khởi tạo với registrar

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    registrar.registerEndpoint(endpoint, factory);
}
~~~

Đây là cách khai báo một endpoint cho infrastructure **trước khi chạy bình thường**. Registrar có thể tiếp nhận:
- Endpoint model.
- Factory dùng để tạo container.
- Default factory.
- Handler method factory cho annotated method invocation.

Nó không phải danh sách trạng thái active/idle của các JMS consumer đang chạy.

### 10.2. Giai đoạn chạy với registry

~~~java
// Mảnh code trong Spring service được inject registry.
MessageListenerContainer running =
        registry.getListenerContainer("programmaticPayments");

if (running != null && running.isRunning()) {
    running.stop();
}

// Muốn resume sau khi người vận hành cho phép:
if (running != null && !running.isRunning()) {
    running.start();
}
~~~

`stop()` của container yêu cầu dừng nhận theo lifecycle, **không có nghĩa đã huỷ khỏi registry**. `start()` có thể resume nếu container còn hợp lệ; nhưng một số provider/cache/subscription cần kiểm thử khởi động lại và timing. Không gọi stop/start cho mỗi message từ chính callback vì có thể gây block hoặc race; để thread quản trị hoặc coordinator xử lý.

`JmsListenerEndpointRegistry` tham gia **`SmartLifecycle`**, quản lý start/stop/destroy khi Spring `ApplicationContext` đóng. Các container này thường không phải bean độc lập để autowire từng cái; tra ID qua registry là cách chính thống.

### 10.3. Runtime register qua registry, không qua startup registrar

Khi thật sự phải thêm endpoint sau khi context đã chạy:

~~~java
// Mảnh Java trong một admin service được kiểm soát.
// registry: JmsListenerEndpointRegistry bean
// factory : JmsListenerContainerFactory<?> bean đã cấu hình

var endpoint = new SimpleJmsListenerEndpoint();
endpoint.setId("newQueueConsumer");
endpoint.setDestination("new.queue");
endpoint.setMessageListener(message -> {
    // Xử lý message theo hợp đồng.
});

registry.registerListenerContainer(endpoint, factory, true);
~~~

`true` cho biết **startImmediately** nếu container đang ở tình trạng cho phép chạy. Đây là API registry khác với `registrar.registerEndpoint`. Không gọi từ một vòng loop không kiểm soát, không xây endpoint ID/destination trực tiếp từ HTTP input không tin cậy, và phải bảo đảm permission, uniqueness, lifecycle cleanup.

**Giới hạn:** register runtime không biến các endpoint đó thành bean business được Spring quản lý riêng; callback vẫn cần dependency injection/cấu trúc đã chuẩn bị, transaction/metrics và owner quản lý container ID. Việc “unregister” không nên suy ra chỉ từ `stop()`: dừng không tự loại bỏ ID khỏi registry.

## 11. Cấu hình MessageHandlerMethodFactory cho method-based endpoint

Spring hỗ trợ annotated method có tham số:

~~~java
@JmsListener(destination = "payments.in")
public void accept(
        PaymentCommand command,
        @Header("tenantId") String tenantId) {
    // Validate rồi xử lý.
}
~~~

Đây là mảnh code; các import gồm Spring `@JmsListener`, `@Header`; cần converter và DTO phù hợp. `MessageHandlerMethodFactory` chịu trách nhiệm tạo phương thức gọi với resolved arguments, validation, payload conversion support.

Mẫu cấu hình validator:

~~~java
@Bean
DefaultMessageHandlerMethodFactory handlerMethodFactory(
        Validator validator) {

    var factory = new DefaultMessageHandlerMethodFactory();
    factory.setValidator(validator);
    return factory;
}
~~~

Sau đó trong `JmsListenerConfigurer`:

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    registrar.setMessageHandlerMethodFactory(handlerMethodFactory);
}
~~~

Đây là **mảnh cấu hình**: `DefaultMessageHandlerMethodFactory` nằm trong `org.springframework.messaging.handler.annotation.support`; `Validator` là `org.springframework.validation.Validator`. Đảm bảo bean đã có và được inject, không khai báo cùng method factory nhiều nơi theo cách ghi đè bất ngờ.

Phân biệt:
- **JMS `MessageConverter`** chuyển raw JMS message ⇄ Java/Spring payload theo cấu hình listener adapter/template.
- **Handler method factory** cấu hình invoker, argument resolvers và validation trong pipeline method.
- **SimpleJmsListenerEndpoint** dùng raw `jakarta.jms.MessageListener` callback nên không tự có `@Valid` method parameter binding.

Nếu JSON message chứa DTO, phải đảm bảo converter, Jackson allowlist/type mapping, validator và exception policy đồng nhất ở hai đầu. Một annotation method có kiểu `PaymentCommand` **không tự làm message chưa rõ schema trở nên an toàn**.

## 12. Nhiều configurers, custom registry và thứ tự cấu hình

### 12.1. Có thể có nhiều JmsListenerConfigurer

Khi các module Spring khác nhau đều cung cấp configurer, mỗi cái có thể thêm endpoint hoặc sửa default factory/method factory. Những phần **đăng ký endpoint độc lập** có thể cùng tồn tại, nhưng nhiều configurers cùng đặt **một default factory** làm cấu hình khó dự đoán nếu không kiểm soát thứ tự.

**Khuyến nghị:** gom các quy tắc mặc định vào một configurer rõ owner; để các module còn lại đăng ký endpoint kèm factory tường minh. Nếu bắt buộc có nhiều configurers, xác định bean ordering theo Spring và viết integration test để đảm bảo đúng policy.

### 12.2. Có nên tự tạo JmsListenerEndpointRegistry?

Thông thường **không cần**. Spring annotation-driven infrastructure có registry mặc định để quản lý tất cả annotated/programmatically registered endpoints. `registrar.setEndpointRegistry(...)` tồn tại cho trường hợp tích hợp nâng cao, nhưng thay registry mà không hiểu infrastructure ownership/initialization có thể làm mất khả năng tra cứu/stop các container như dự kiến.

Trước khi custom registry, trả lời:
- Vì sao registry mặc định không đáp ứng được?
- Bean registry có tham gia ApplicationContext lifecycle và được destroy đúng cách không?
- Monitoring/actuator/admin code tìm đúng registry nào?
- IDs có bị trùng giữa annotation và programmatic endpoints không?
- Có tránh tạo hai registries quản lý cùng một destination nhưng đội vận hành chỉ thấy một registry không?

### 12.3. Không tự đăng ký lặp cả annotation và programmatic

Nếu method có `@JmsListener` rồi bạn tạo thêm `SimpleJmsListenerEndpoint` trỏ cùng queue/callback, Spring sẽ có **hai consumer containers**, không “nâng cấp” endpoint cũ. Trên Queue, chúng cạnh tranh message. Trên Topic, chúng có thể nhận những bản độc lập nếu subscription phù hợp. Chỉ đăng ký những endpoint thực sự cần và test số containers cuối cùng.

## 13. Selector, Topic, durable subscription trong programmatic endpoint

`SimpleJmsListenerEndpoint` kế thừa các thuộc tính endpoint như `id`, `destination`, `selector` và `subscription` theo Spring API; có thể cấu hình:

~~~java
var endpoint = new SimpleJmsListenerEndpoint();
endpoint.setId("apacInvoices");
endpoint.setDestination("invoices.in");
endpoint.setSelector("region = 'APAC' AND priorityGroup >= 2");
endpoint.setMessageListener(message -> {
    // MessageListener raw
});
registrar.registerEndpoint(endpoint, factory);
~~~

Đây là mảnh cấu hình ở startup; **selector lọc JMS properties**, không đọc JSON body. Producer cần đặt `region` và `priorityGroup` qua JMS setters đúng kiểu. Dùng SQL92 subset, có thể có logic ba giá trị `TRUE/FALSE/UNKNOWN`; missing properties không tự match.

Nếu destination là Topic:
- Factory/container phải cấu hình `pubSubDomain=true`.
- Durable subscription cần định danh/clientID/subscription name đúng theo JMS/provider và broker policy.
- `setSubscription(...)` là tên subscription, **không** tự bật durable trên mọi factory; phải cấu hình chế độ subscription tương ứng.
- Scaling nhiều replicas với shared/unshared durable subscriptions cần kiểm tra provider support, IDs và retention.
- Selector trên durable subscription có thể ảnh hưởng backlog và khả năng thay đổi selector; test trước rolling deploy.

Không chọn Topic chỉ vì có một endpoint registrar; endpoint API **không quyết định** queue-vs-topic. Điều này nằm ở factory/connection/destination.

## 14. Transaction, exception và rollback cho hai kiểu listener

### 14.1. @JmsListener và raw MessageListener có cùng container không?

Chúng có thể được tạo bởi **cùng `DefaultJmsListenerContainerFactory`** và có transaction/connection/concurrency policy giống nhau. Khác biệt chính ở adapter invocation:
- Annotated method nhận payload đã convert, có thể lấy `@Header`, validation.
- Simple endpoint nhận **raw JMS `Message`** và tự đọc body/headers/properties.

Nếu cùng factory `setSessionTransacted(true)`:
- Listener thực thi thành công thì container có thể commit JMS session.
- Listener ném exception thì container có thể rollback để message được redeliver theo broker policy.
- Session transacted không tự bao gồm transaction ghi database hoặc HTTP side effects; dùng idempotency/outbox khi cần.

### 14.2. Bắt ngoại lệ đúng cách trong MessageListener

Không viết:

~~~java
endpoint.setMessageListener(message -> {
    try {
        processPayment(message);
    } catch (Exception ex) {
        logError(ex);
        // Trả về bình thường: container có thể coi là thành công!
    }
});
~~~

Đây là **phản ví dụ minh họa**, cần các hàm bên ngoài. Nếu lỗi làm nghiệp vụ chưa hoàn tất và cần rollback, ném unchecked exception để container xử lý theo transaction policy, không chỉ log rồi bỏ qua.

Cách có kiểm soát:

~~~java
endpoint.setMessageListener(message -> {
    try {
        performIdempotentOperation(message);
    } catch (JMSException ex) {
        throw new IllegalStateException(
                "Could not read JMS message", ex);
    }
});
~~~

Đây là mảnh code: `performIdempotentOperation` khai báo có thể ném `JMSException`; business error unchecked vẫn được truyền ra ngoài. Với poison message lỗi cố định, không retry vô hạn: dùng backoff, giới hạn số lần và DLQ/quarantine.

### 14.3. Đóng ứng dụng có kiểm soát

`JmsListenerEndpointRegistry` tham gia Spring lifecycle. Khi SIGTERM/`ApplicationContext.close()` xảy ra:
- Container ngừng nhận message mới theo pha lifecycle.
- Handler đang chạy có cơ hội hoàn tất trong thời gian shutdown configured.
- Các session/consumer/connection được container và connection factory quản lý dọn sau khi dừng.
- Nếu process bị kill cưỡng bức hoặc hết budget, broker transaction/redelivery và idempotency là lớp phục hồi.

Không đóng connection/session của container từ bên trong `onMessage`; không gọi `registrar.registerEndpoint` để “khởi động lại” khi broker reconnect — container có cơ chế recovery riêng.

## 15. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `@JmsListener` không hoạt động | Chưa bật JMS infrastructure, không scan bean, thiếu factory/connection | Kiểm tra `@EnableJms`/Boot config, component scan, starter, bean names |
| Callback `configureJmsListeners` không chạy | Configurer không là Spring bean, sai package interface, chưa bật annotation infrastructure | Đảm bảo `@Configuration` và đúng interface `org.springframework.jms.annotation.JmsListenerConfigurer` |
| Đăng ký endpoint nhưng không thấy container | Sai factory, lỗi startup, registry khác, thiếu ID/destination | Đọc startup logs và `registry.getListenerContainerIds()` |
| `NoSuchBeanDefinitionException` cho factory | `containerFactory` hoặc `setContainerFactoryBeanName` tham chiếu tên bean sai | So sánh bean names thực tế |
| ID trùng giữa endpoints | Hai `@JmsListener`/programmatic endpoints dùng cùng ID | Đặt unique stable ID, test bootstrap |
| Listener nhận raw `TextMessage` thay vì `String` | Dùng `SimpleJmsListenerEndpoint` | Raw MessageListener phải đọc JMS body hoặc chọn method-based listener |
| `@Valid` không chạy trên simple callback | Handler method factory không áp cho raw JMS MessageListener | Thực hiện validation tường minh hoặc dùng annotated method pipeline |
| Dùng `registrar.registerEndpoint` sau context init | Registrar là bootstrap mechanism | Runtime dùng `registry.registerListenerContainer(...)` với factory rõ |
| Consumer không nhận message vì selector | Selector chỉ đọc JMS properties, property thiếu/sai kiểu | Kiểm tra selector và properties producer |
| Có hai consumers cùng queue ngoài ý muốn | Vừa dùng annotation vừa đăng ký programmatic cùng destination | Kiểm tra IDs và topology; tránh đăng ký trùng |
| Stop một endpoint không làm queue hết backlog | Stop chỉ ảnh hưởng container; broker giữ message theo policy | Quan sát queue metrics, competing consumers |
| Handler ném lỗi nhưng không redeliver | ACK mode, transaction boundary hoặc catch nuốt exception | Cấu hình session transacted/rollback, broker DLQ |
| Startup treo khi broker lỗi | Recovery, connection timeout, provider config | Kiểm tra broker URL/recoveryInterval, timeout và fail-fast policy |
| Redeploy nhận message trùng | Side effect đã commit trước JMS commit | Idempotent consumer và inbox/unique business key |
| Listener vẫn hoạt động khi tưởng đã destroy | Nhiều registries/containers, custom thread hoặc broker connection khác | Quan sát registry IDs, active connections và shutdown logs |
| Dùng factory không đúng queue/topic domain | `pubSubDomain` không khớp destination | Kiểm tra factory, connection resolver, broker address |

## 16. Checklist review trước production

- **Registration owner:** endpoint được tạo bởi `@JmsListener` hay `JmsListenerConfigurer`? Có tạo hai lần không?
- **Endpoint ID:** có unique, ổn định, ý nghĩa với monitoring/admin không?
- **Factory:** endpoint có dùng đúng `DefaultJmsListenerContainerFactory` và kế thừa Boot defaults khi cần?
- **Fallback:** có biết default factory cho endpoint không chỉ định `containerFactory`/không truyền factory?
- **Registry:** app tra cứu đúng registry và containers không phải bean trực tiếp?
- **Dynamic:** nếu tạo runtime, có giới hạn số endpoints và policy stop/start/cleanup?
- **Concurrency:** số session/consumer phù hợp queue/topic và ordering không?
- **Conversion:** annotated method và Simple callback dùng đúng body/DTO contract?
- **Validation:** cấu hình `MessageHandlerMethodFactory` và validator có áp đúng nơi?
- **Selector:** property name/type, SQL92 syntax và NULL handling đã test chưa?
- **Reliability:** sessionTransacted, ACK, retry, redelivery, DLQ, idempotency có khớp SLA?
- **Topology:** queue cạnh tranh consumer hay topic có durable subscriptions?
- **Security:** broker authentication/TLS/ACL và tenant authorization không phụ thuộc chỉ vào selector?
- **Shutdown:** registry/connection pool dừng đúng thứ tự, không đóng resource giữa handler?
- **Tests:** đã kiểm tra startup IDs, two-queue lab, runtime stop/start, listener exception và redeploy backlog?
- **Versioning:** listener mới đọc được message cũ trong queue/DLQ chưa?

## 17. Bài tập củng cố

1. Phân biệt `JmsListenerConfigurer` với `JmsListenerEndpointRegistrar` và `JmsListenerEndpointRegistry` bằng một sơ đồ riêng.
2. Tại sao gọi `new SimpleJmsListenerEndpoint()` không khiến broker có thêm một consumer ngay?
3. Đăng ký `auditEvents` vào queue `audit.in` và factory `auditFactory`; cái nào là endpoint ID, destination, bean name?
4. Một endpoint dùng `@JmsListener(containerFactory="criticalFactory")`; registrar đặt default `commonFactory`. Endpoint dùng factory nào?
5. Viết configurer đăng ký hai `SimpleJmsListenerEndpoint` vào hai queue khác nhau; làm cách nào đảm bảo ID không trùng?
6. Cho một `MessageListener` nhận `TextMessage`. Vì sao không thể khai báo ném `JMSException` ra ngoài lambda? Viết cách catch/rethrow phù hợp.
7. Một method annotation nhận `@Header("tenantId")` và `@Valid` DTO, simple endpoint nhận raw `Message`. Vì sao method factory không tự áp vào simple endpoint?
8. Khi app đã chạy mà phải thêm một consumer, vì sao nên dùng `registry.registerListenerContainer` thay vì startup registrar?
9. Hai nhóm nghiệp vụ đăng ký cùng queue với khác endpoint IDs. Cả hai có tự được nhận mỗi message một bản không? Khi nào cần Topic?
10. Trong lab, bỏ `sessionTransacted=true` và cho programmatic listener ném exception. Hãy lên kế hoạch kiểm thử redelivery trên broker thay vì suy luận chỉ từ log.
11. Thay selector cho endpoint programmatic thành `kind = 'payment'`; producer cần đặt property nào, kiểu gì?
12. Thử tạo một endpoint runtime với ID đã tồn tại. Kỳ vọng về registry uniqueness và cách test an toàn.
13. Mô tả thứ tự khi SIGTERM đến trong lúc listener xử lý, và giới hạn của graceful shutdown so với process crash.
14. Nếu app dùng 3 `JmsListenerConfigurer` khác nhau, cần quy ước gì để không ghi đè default factory hoặc trùng ID?
15. Hãy giải thích tại sao `registrar.setMessageHandlerMethodFactory` không thay thế việc cấu hình JMS `MessageConverter` trên listener container.

## 18. Tài liệu tham khảo chính thức

- Spring Framework 6.2 — **Annotation-driven Listener Endpoints**, gồm phần **Programmatic Endpoint Registration**: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — **JmsListenerConfigurer** Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListenerConfigurer.html
- Spring Framework 6.2 — **JmsListenerEndpointRegistrar** Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistrar.html
- Spring Framework 6.2 — **SimpleJmsListenerEndpoint** Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/SimpleJmsListenerEndpoint.html
- Spring Framework 6.2 — **JmsListenerEndpointRegistry** Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Framework 6.2 — **Receiving a Message**: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Boot 3.5 — **JMS configuration and listener container factory configurer**: https://docs.spring.io/spring-boot/3.5/how-to/messaging.html
- Spring Boot 3.5 — **Messaging with JMS** integration guide: https://spring.io/guides/gs/messaging-jms/
