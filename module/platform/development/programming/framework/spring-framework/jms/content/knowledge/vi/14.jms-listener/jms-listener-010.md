# Đăng ký SimpleJmsListenerEndpoint bằng mã trong Spring JMS

## 1. Mục tiêu và phạm vi

Khi ứng dụng Spring JMS nhận message, cách quen thuộc là đặt `@JmsListener(destination = "orders.queue")` trên một method. Nhưng không phải mọi endpoint đều phù hợp để khai báo bằng annotation. Có hệ thống đọc danh sách Queue từ cấu hình lúc khởi động, cần gắn `MessageListener` đã được tạo sẵn, hoặc phải thiết lập từng endpoint với một ID và bộ lọc riêng. Khi đó Spring Framework hỗ trợ **đăng ký JMS listener endpoint bằng Java code**.

Trọng tâm của bài là `org.springframework.jms.config.SimpleJmsListenerEndpoint` và quy trình:

1. Bật hạ tầng listener bằng `@EnableJms`.
2. Triển khai `JmsListenerConfigurer` để nhận `JmsListenerEndpointRegistrar`.
3. Tạo `SimpleJmsListenerEndpoint`, đặt `id`, `destination`, `MessageListener`.
4. Gọi `registrar.registerEndpoint(endpoint)` hoặc overload với factory chỉ định.
5. Để Spring tạo và quản lý listener container theo `JmsListenerContainerFactory`.
6. Tra cứu container đã đăng ký bằng `JmsListenerEndpointRegistry` khi cần giám sát hoặc điều khiển start/stop.

Sau bài này, bạn sẽ:
- Phân biệt **endpoint metadata**, **message listener**, **container factory**, **container runtime** và **endpoint registry**.
- Tạo một Spring Boot Java 17+ example gửi/nhận với Artemis broker và không cần `@JmsListener` trên receiver.
- Biết cách đặt nhiều endpoint, selector, concurrency, Queue/Topic và factory khác nhau.
- Phân biệt đăng ký trong giai đoạn khởi động với **đăng ký động sau khi ứng dụng chạy**.
- Tránh lỗi trùng ID, sai destination, thiếu factory, sai type listener, không có transaction, competing consumers và sai lifecycle.
- Kiểm tra chính xác liệu callback đã chạy, message đã commit, broker đã xác nhận và endpoint thực sự đã được registry sở hữu.

Bài dùng **Spring Framework 6.x** với **Spring Boot 3.5.8**, **Java 17+**, **Jakarta Messaging (`jakarta.jms.*`)** và **Apache ActiveMQ Artemis**. Ví dụ tích hợp yêu cầu broker bên ngoài đang chạy; việc có thể build Java không chứng minh đã kết nối được broker.

## 2. SimpleJmsListenerEndpoint là gì?

`SimpleJmsListenerEndpoint` là một implementation của `JmsListenerEndpoint`, kế thừa `AbstractJmsListenerEndpoint`. Nó giữ mô tả cách nhận message (ID, destination, selector, concurrency...) và một đối tượng **`jakarta.jms.MessageListener` thực tế** sẽ được gọi khi có message.

Một đoạn khai báo cơ bản:

```java
SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
endpoint.setId("orders-programmatic");
endpoint.setDestination("orders.queue");
endpoint.setMessageListener(message -> {
    // Business handling goes here.
});
```

Đây mới là **tạo model endpoint**, chưa tạo consumer kết nối tới broker. Đoạn trên là snippet cần import `org.springframework.jms.config.SimpleJmsListenerEndpoint` và API JMS liên quan. Muốn listener được kích hoạt, cần **đăng ký endpoint** vào infrastructure của Spring.

### 2.1. Một điểm dễ nhầm do tên class

**`SimpleJmsListenerEndpoint` KHÔNG phải `SimpleMessageListenerContainer`.**

- `SimpleJmsListenerEndpoint`: mô hình cấu hình endpoint, nắm ID/destination/`MessageListener`. Nó không sở hữu connection, consumer, executor hay transaction.
- `SimpleMessageListenerContainer`: một loại container runtime cụ thể của Spring, đăng ký `MessageConsumer.setMessageListener(...)` cho provider dispatch.
- `DefaultMessageListenerContainer`: một loại container khác; thường có worker thread gọi `receive`, tự dispatch cho listener và hỗ trợ recovery/concurrency linh hoạt.
- `DefaultJmsListenerContainerFactory`: factory tạo **`DefaultMessageListenerContainer`** từ metadata endpoint và tham số chung.

Vì vậy **đăng ký một `SimpleJmsListenerEndpoint` qua `DefaultJmsListenerContainerFactory` vẫn tạo một `DefaultMessageListenerContainer`**. Từ "Simple" trong tên endpoint không hề buộc bạn dùng container "Simple".

### 2.2. Sơ đồ hạ tầng

```text
@EnableJms
   |
   +--> JMS endpoint annotation infrastructure
             |
             +--> @JmsListener methods (nếu có)
             |
             +--> JmsListenerConfigurer.configureJmsListeners(...)
                         |
                         +--> JmsListenerEndpointRegistrar
                                  |
                                  +--> SimpleJmsListenerEndpoint
                                          id="orders-programmatic"
                                          destination="orders.queue"
                                          messageListener=<bean>
                                  |
                                  +--> JmsListenerContainerFactory
                                           |
                                           v
                                 DefaultMessageListenerContainer
                                           |
                                           v
                                 ConnectionFactory -> Artemis broker

JmsListenerEndpointRegistry
   |
   +--> ["orders-programmatic" -> container runtime]
   +--> quản lý lifecycle container của endpoint
```

`JmsListenerEndpointRegistry` quản lý các container được tạo qua hạ tầng endpoint. **Những container này thông thường không phải Spring bean độc lập để inject trực tiếp theo tên container**. Muốn xem chúng, dùng registry và endpoint ID, ví dụ `registry.getListenerContainer("orders-programmatic")`.

### 2.3. Các class và package cần nhớ

| Vai trò | Class/interface | Package |
| --- | --- | --- |
| Bật JMS listener infrastructure | `@EnableJms` | `org.springframework.jms.annotation` |
| Hook cấu hình programmatic | `JmsListenerConfigurer` | `org.springframework.jms.annotation` |
| Nhận đăng ký endpoint ở startup | `JmsListenerEndpointRegistrar` | `org.springframework.jms.config` |
| Mô hình endpoint đơn giản | `SimpleJmsListenerEndpoint` | `org.springframework.jms.config` |
| Contract endpoint | `JmsListenerEndpoint` | `org.springframework.jms.config` |
| Factory container thông dụng | `DefaultJmsListenerContainerFactory` | `org.springframework.jms.config` |
| Registry quản lý container | `JmsListenerEndpointRegistry` | `org.springframework.jms.config` |
| Callback JMS raw | `MessageListener` | `jakarta.jms` |
| Runtime container thường dùng | `DefaultMessageListenerContainer` | `org.springframework.jms.listener` |

Đừng import nhầm Rabbit `RabbitListenerEndpointRegistry` của Spring AMQP; đây là bài **Spring JMS**, dùng package `org.springframework.jms.*`.

## 3. Đăng ký ở startup qua JmsListenerConfigurer

Spring Framework document cách chuẩn:

```java
@Configuration
@EnableJms
public class JmsEndpointConfig implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        SimpleJmsListenerEndpoint endpoint =
                new SimpleJmsListenerEndpoint();
        endpoint.setId("orders-programmatic");
        endpoint.setDestination("orders.queue");
        endpoint.setMessageListener(message -> {
            // Xử lý message.
        });

        registrar.registerEndpoint(endpoint);
    }
}
```

Đây là **snippet cấu hình rút gọn**: cần imports của Spring, JMS provider, `ConnectionFactory` và một bean `JmsListenerContainerFactory` có thể tìm được. Một endpoint có đầy đủ ID/destination/listener mà không có container factory thích hợp vẫn không thể chạy.

**Vai trò từng bước:**

1. `@Configuration` đưa class vào Spring ApplicationContext.
2. `@EnableJms` đăng ký infrastructure xử lý endpoint, kể cả phương thức annotation và hook `JmsListenerConfigurer`. Không cần một method có `@JmsListener` mới sử dụng được hạ tầng này.
3. Spring gọi `configureJmsListeners(registrar)` trong quá trình khởi tạo endpoint infrastructure.
4. `endpoint.setId(...)` định danh **duy nhất** container/endpoint trong registry.
5. `endpoint.setDestination(...)` đặt **tên destination** theo `DestinationResolver` của container. Ví dụ đặt tên Queue broker trực tiếp, không dùng alias JNDI.
6. `endpoint.setMessageListener(...)` cung cấp callback Jakarta Messaging; Spring sẽ gọi nó với JMS `Message`, không tự động biến lambda thành method signature nhận `String`.
7. `registrar.registerEndpoint(endpoint)` yêu cầu registrar ghi nhận endpoint và dùng **default listener container factory** để tạo container.
8. Trong startup, registry tạo, khởi tạo và quản lý lifecycle container, kết nối JMS khi container bắt đầu chạy.

### 3.1. ID của endpoint dùng làm gì?

`setId("orders-programmatic")` là **ID runtime trong registry**, không phải JMSMessageID, Queue name hay tên bean listener. Khi nhận nhu cầu vận hành:

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-programmatic");

if (container != null) {
    System.out.println("running=" + container.isRunning());
}
```

Đoạn trên là snippet ở Spring bean có `JmsListenerEndpointRegistry registry`; `MessageListenerContainer` là type thuộc `org.springframework.jms.listener`.

**ID trùng** với endpoint khác (kể cả endpoint annotation có cùng `id`) sẽ gây lỗi đăng ký, thường `IllegalStateException`. Hãy dùng convention có namespace, chẳng hạn `billing-orders-consumer`, `audit-events-consumer`. Thêm prefix môi trường nếu application context thực sự chứa nhiều endpoint tương tự, nhưng không cần gắn hostname ngẫu nhiên vào ID khiến vận hành khó tra cứu.

### 3.2. Default factory được lấy từ đâu?

Khi gọi `registrar.registerEndpoint(endpoint)` không có đối số factory, registrar cần **một factory mặc định**. Theo convention của Spring, bean tên `jmsListenerContainerFactory` được dùng. Nếu không có factory phù hợp, startup có thể thất bại vì không resolve được factory.

Một factory bean đơn giản:

```java
@Bean(name = "jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(false);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-2");
    return factory;
}
```

Đây là snippet đặt bên trong class `@Configuration` với các imports tương ứng. `setSessionTransacted(true)` đặt local JMS transaction cho listener; `setConcurrency("1-2")` minh họa một đến hai concurrent consumer tùy tải.

Nếu đã có một factory bean với tên khác, có thể trong configurer chọn:

```java
registrar.setContainerFactoryBeanName("ordersJmsListenerContainerFactory");
registrar.registerEndpoint(endpoint);
```

Đây là **snippet cấu hình startup**, không phải thao tác đổi factory khi container đã chạy. Ngoài ra có overload:

```java
registrar.registerEndpoint(endpoint, specificFactory);
```

Trong đó `specificFactory` là instance `JmsListenerContainerFactory<?>` đã được cấu hình và có lifecycle phù hợp. Overload hữu ích nếu hệ thống có nhiều factory cho các broker/transaction mode khác nhau.

### 3.3. setMessageListener() nhận type gì?

`SimpleJmsListenerEndpoint.setMessageListener` nhận một **`jakarta.jms.MessageListener`**:

```java
endpoint.setMessageListener(message -> {
    if (!(message instanceof TextMessage text)) {
        throw new IllegalArgumentException(
                "Expected TextMessage");
    }
    try {
        process(text.getText());
    } catch (JMSException exception) {
        throw new IllegalStateException(
                "Cannot read JMS body", exception);
    }
});
```

Đây là snippet, `process` là business method của ứng dụng và cần import `TextMessage`/`JMSException`. `MessageListener.onMessage` **không khai báo checked `JMSException`**, nên không thể tự động `throws JMSException` từ lambda. Nếu muốn POJO method `void handle(String payload)` được Spring tự convert/resolve argument giống `@JmsListener`, cân nhắc `MethodJmsListenerEndpoint` hoặc `MessageListenerAdapter` thay vì tưởng `SimpleJmsListenerEndpoint` tự làm việc đó.

## 4. Ví dụ Spring Boot hoàn chỉnh: endpoint tự đăng ký bằng Java code

Ví dụ sử dụng **Java 17+, Spring Boot 3.5.8, Apache ActiveMQ Artemis**. Code sử dụng **`SimpleJmsListenerEndpoint` và `JmsListenerConfigurer`, hoàn toàn không dùng `@JmsListener` trên method nhận**.

Đặc điểm:
- Một bean `TrainingMessageListener` implement `jakarta.jms.MessageListener`.
- Một `EndpointRegistrationConfig` tạo `DefaultJmsListenerContainerFactory` và đăng ký endpoint `trainingOrders`.
- Một `ApplicationRunner` tra registry để xác nhận endpoint hiện diện, gửi message bằng `JmsTemplate` và đợi callback bằng `CountDownLatch`.
- Listener container sử dụng **JMS local transaction** (`sessionTransacted=true`).
- Toàn bộ ba Java class dùng chung package `example.jms`, giúp Spring Boot quét bean mà không phải cấu hình scan thủ công.

### 4.1. Điều kiện chạy

- JDK 17+ và Maven.
- Một **Artemis broker bên ngoài** đang chạy, lắng nghe `tcp://localhost:61616` hoặc endpoint được truyền bằng environment.
- Tài khoản broker có quyền gửi và nhận tại Queue `learning.programmatic.queue`.
- Queue này đã được tạo sẵn, **hoặc** broker cho phép auto-create Queue theo policy và routing phù hợp.
- Để output demo dễ xác định, Queue ban đầu cần sạch và không có consumer khác. Nếu có message cũ hoặc replica khác cùng nhận, kết quả có thể khác.
- Không dùng client `javax.jms` cũ bên cạnh Spring Framework 6.x sử dụng `jakarta.jms`.

### 4.2. Cấu trúc thư mục

```text
programmatic-jms-endpoint/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── jms/
        │           ├── ProgrammaticEndpointApplication.java
        │           ├── EndpointRegistrationConfig.java
        │           └── TrainingMessageListener.java
        └── resources/
            └── application.properties
```

### 4.3. Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>programmatic-jms-endpoint</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
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

`spring-boot-starter-artemis` kéo các dependency Spring JMS/Jakarta client thích hợp theo dependency management của Spring Boot. Trong ứng dụng có quy định BOM riêng, kiểm tra xung đột phiên bản; không thêm `javax.jms-api` chỉ để sửa lỗi compile của Jakarta JMS.

### 4.4. Kết nối tới broker

**`src/main/resources/application.properties`**

```properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}

# Queue (point-to-point) thay vì Topic:
spring.jms.pub-sub-domain=false

# Ví dụ cố ý tránh một tầng session cache bên ngoài listener container:
spring.jms.cache.enabled=false
```

- `spring.artemis.mode=native` dùng broker Artemis ngoài ứng dụng. File Maven/config **không** tự khởi động Artemis.
- `JMS_USERNAME` và `JMS_PASSWORD` phải được cung cấp trước lúc khởi động; không commit credentials thật vào mã nguồn.
- `spring.jms.cache.enabled=false` làm ví dụ minh bạch: listener container tự quản lý việc cache/recovery resource JMS. Trong hệ thống thật, chọn raw/cached/pooled connection factory theo tải và tài liệu provider; không kết luận cache luôn sai.
- Nếu broker sử dụng TLS/HA/failover, thay endpoint và tham số bảo mật theo hướng dẫn Artemis, không bê nguyên cấu hình localhost lên production.

### 4.5. Bean MessageListener (không có @JmsListener)

**`src/main/java/example/jms/TrainingMessageListener.java`**

```java
package example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

import org.springframework.stereotype.Component;

@Component
public final class TrainingMessageListener implements MessageListener {

    private final CountDownLatch observed = new CountDownLatch(1);

    @Override
    public void onMessage(Message message) {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected a JMS TextMessage");
        }

        try {
            String body = textMessage.getText();
            if (!"demo-175".equals(body)) {
                throw new IllegalArgumentException(
                        "Unexpected body: " + body);
            }

            System.out.println("received=" + body);
            observed.countDown();
        } catch (JMSException exception) {
            throw new IllegalStateException(
                    "Cannot read TextMessage", exception);
        }
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return observed.await(timeout, unit);
    }
}
```

Bean `TrainingMessageListener` là singleton của Spring. Bản thân nó **không tự đăng ký** với Queue vì không có `@JmsListener` annotation. `EndpointRegistrationConfig` ở bước kế tiếp phải đưa bean này vào `SimpleJmsListenerEndpoint`.

`CountDownLatch` là cách demo đợi callback mà không dùng polling vô hạn; nó chỉ báo **đã vào callback và xử lý đến `countDown`**, không chứng minh JMS transaction đã commit. Trong production, đừng giữ một latch dùng một lần để điều phối mọi message; thay bằng metrics, event ID, idempotency và xử lý nghiệp vụ thực.

**Vì sao lambda không `throws JMSException`?** `MessageListener.onMessage` không khai báo checked exception. Code `textMessage.getText()` có `throws JMSException` nên cần catch và chuyển unchecked để Spring container thấy callback thất bại.

### 4.6. @EnableJms + JmsListenerConfigurer + SimpleJmsListenerEndpoint

**`src/main/java/example/jms/EndpointRegistrationConfig.java`**

```java
package example.jms;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;

@Configuration(proxyBeanMethods = false)
@EnableJms
public class EndpointRegistrationConfig implements JmsListenerConfigurer {

    public static final String DESTINATION = "learning.programmatic.queue";
    public static final String ENDPOINT_ID = "trainingOrders";

    private final TrainingMessageListener listener;

    public EndpointRegistrationConfig(TrainingMessageListener listener) {
        this.listener = listener;
    }

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-2");
        return factory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId(ENDPOINT_ID);
        endpoint.setDestination(DESTINATION);
        endpoint.setMessageListener(listener);

        // Sử dụng bean default tên jmsListenerContainerFactory.
        registrar.registerEndpoint(endpoint);
    }
}
```

**Đây là phần trung tâm của bài.** Nó dùng đúng API `SimpleJmsListenerEndpoint` và cơ chế programmatic endpoint registration của Spring, thay vì tự tạo `DefaultMessageListenerContainer` rồi gọi start thủ công.

Các điểm cần chú ý:

1. `@EnableJms` bật infrastructure endpoint. Nếu class cấu hình không được scan/nhập vào context, `configureJmsListeners` không chạy.
2. `JmsListenerConfigurer` là extension point gọi **khi Spring xây endpoint infrastructure**, không phải một callback gọi mỗi lần có message.
3. Constructor inject `TrainingMessageListener` đang là bean `@Component`, nên endpoint dùng đúng instance được Spring quản lý.
4. `setId(ENDPOINT_ID)` gắn ID `trainingOrders` để registry quản lý và tra cứu.
5. `setDestination(DESTINATION)` gắn Queue `learning.programmatic.queue`; vì factory `pubSubDomain=false` nên đây là Queue. Nếu cần JNDI alias, gắn `DestinationResolver` phù hợp lên factory.
6. `setMessageListener(listener)` đưa **`MessageListener` thực** vào endpoint. Spring không tự biến method `onMessage` thành annotation endpoint.
7. `registrar.registerEndpoint(endpoint)` dựa vào bean factory mặc định tên `jmsListenerContainerFactory`; nếu bean không tồn tại và không có factory khác, startup báo lỗi cấu hình.
8. `factory.setSessionTransacted(true)` để container commit khi listener hoàn tất bình thường, rollback khi lỗi thoát ra; broker có thể redeliver theo policy.
9. `factory.setConcurrency("1-2")` cho phép container chạy nhiều consumer khi phù hợp tải. Bean listener singleton phải thread-safe nếu nhiều worker gọi `onMessage` đồng thời.
10. Không gọi `session.commit()` thủ công trong `TrainingMessageListener` vì container sở hữu local JMS transaction.

### 4.7. Application main: gửi message và kiểm tra registry

**`src/main/java/example/jms/ProgrammaticEndpointApplication.java`**

```java
package example.jms;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ProgrammaticEndpointApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProgrammaticEndpointApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(
            JmsTemplate template,
            TrainingMessageListener listener,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            if (registry.getListenerContainer(
                    EndpointRegistrationConfig.ENDPOINT_ID) == null) {
                throw new IllegalStateException(
                        "Programmatic JMS endpoint is not registered");
            }

            System.out.println("endpointRegistered=true");

            template.convertAndSend(
                    EndpointRegistrationConfig.DESTINATION,
                    "demo-175");

            boolean invoked = listener.await(10, TimeUnit.SECONDS);
            System.out.println("listenerInvoked=" + invoked);

            if (!invoked) {
                throw new IllegalStateException(
                        "JMS listener was not invoked within 10 seconds");
            }
        };
    }
}
```

`@SpringBootApplication` quét package `example.jms` nên nhận ra cả `@Component` listener và `@Configuration` configurer. `ApplicationRunner` chạy sau khi context khởi động để gửi một message và đợi callback.

**Tại sao kiểm tra registry trước khi gửi?** Để phân biệt rõ hai lỗi: endpoint **không được Spring đăng ký** với endpoint đã đăng ký nhưng **không kết nối/không nhận message**. Registry có container **không chứng minh broker sẵn sàng**; đó chỉ là kiểm tra wiring nội bộ.

**Tại sao không có `@JmsListener`?** Vì bài đang dùng `SimpleJmsListenerEndpoint.setMessageListener`. Nếu vừa thêm `@JmsListener` lên method nhận cùng Queue, Spring có thể tạo consumer thứ hai, trở thành competing consumer, khiến demo không nhận được message ở instance mong đợi.

### 4.8. Chạy thử

PowerShell (Windows):

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"

mvn spring-boot:run
```

Shell POSIX:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=dev-user \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Điền tài khoản thực tế do broker cung cấp. Nếu Queue chưa provision và broker không cho auto-create, application có thể gặp lỗi destination. Không có broker thì Maven vẫn có thể biên dịch code nhưng chạy JMS sẽ lỗi kết nối.

Khi broker/Queue/tài khoản đều hợp lệ và không có consumer khác, ba dòng do code chủ động in trong happy path:

```text
endpointRegistered=true
received=demo-175
listenerInvoked=true
```

Các log Spring Boot, Artemis client hoặc container vẫn có thể xen giữa. Thứ tự các dòng của ứng dụng ở ví dụ này đã được điều phối: kiểm tra endpoint trước khi gửi; listener in body trước khi `countDown`; runner in kết quả sau khi `await` thành công. Vì vậy kết quả hợp lệ **trong môi trường cô lập** là ba dòng trên theo thứ tự tương đối.

**Cảnh báo quan trọng:** `received=demo-175` và `listenerInvoked=true` xác nhận listener đã chạy. `CountDownLatch` được giảm **bên trong** callback, có thể trước khi container commit local JMS transaction. Do đó demo **không dùng latch để khẳng định commit hoặc processing exactly once**. Muốn kiểm thử transaction phải dùng integration test/metrics của broker và redelivery scenario.

Build mà không cần broker:

```bash
mvn -q -DskipTests package
```

Chạy project bằng `mvn spring-boot:run` chỉ có thể thành công end-to-end khi có broker/credentials hợp lệ. Không giả định quy trình đã được kiểm chứng trên môi trường không có Artemis test broker.

## 5. Phân tích cơ chế đăng ký từ đầu đến cuối

Có bốn thời điểm riêng:

| Giai đoạn | Điều gì xảy ra | Ai thực hiện |
| --- | --- | --- |
| Tạo bean Java | `TrainingMessageListener`, `EndpointRegistrationConfig`, `ConnectionFactory`, container factory được tạo | Spring IoC / Spring Boot |
| Đăng ký metadata | `configureJmsListeners` tạo `SimpleJmsListenerEndpoint`, gọi `registerEndpoint` | Spring JMS annotation infrastructure + configurer |
| Tạo container runtime | Factory thiết lập `DefaultMessageListenerContainer` với destination/listener/transaction/concurrency | `JmsListenerEndpointRegistry` / factory |
| Khởi động và chạy | Container bắt đầu tiêu thụ từ broker, gọi `onMessage` khi có message | Spring container + JMS provider |

`JmsListenerConfigurer` không tự implement một poll loop. Nó mô tả endpoint cho registrar. Sau khi đăng ký, **registry sở hữu lifecycle container**; trong `onMessage` không cần mở/đóng `Connection` hay `Session`.

### 5.1. Registry và container được quản lý thế nào?

Spring tạo `JmsListenerEndpointRegistry` để theo dõi các container đã được đăng ký qua endpoint infrastructure. Có thể lấy IDs:

```java
Set<String> ids = registry.getListenerContainerIds();

MessageListenerContainer container =
        registry.getListenerContainer("trainingOrders");

if (container != null) {
    boolean running = container.isRunning();
    // Đưa running vào health/metrics nếu cần.
}
```

Đây là snippet bên trong Spring-managed component có field/parameter `registry`. Cần import `java.util.Set` và `org.springframework.jms.listener.MessageListenerContainer`.

**Không nhầm registry container với bean container:**

- `TrainingMessageListener` là Spring bean thông thường.
- `DefaultJmsListenerContainerFactory` là Spring bean.
- Container được **registry tạo theo endpoint** không nhất thiết là Spring bean riêng và thường không inject được trực tiếp theo tên.
- Vì vậy để stop/start listener đã đăng ký programmatically, dùng `registry.getListenerContainer(endpointId)` rồi gọi lifecycle method trên container tương ứng, không tìm kiếm `@Qualifier("trainingOrders") DefaultMessageListenerContainer`.

### 5.2. Start/stop đúng lúc

```java
MessageListenerContainer container =
        registry.getListenerContainer("trainingOrders");

if (container != null) {
    container.stop();  // Tạm ngưng listener.
    // Khi cần mở lại:
    container.start();
}
```

Đây là **snippet vận hành**, không phải logic chạy cho mỗi message. Nếu container có message đang xử lý, stop/shutdown có semantics và thời gian chờ phụ thuộc container; cần test graceful drain theo workload và provider. Stop **không đồng nghĩa xóa endpoint khỏi registry hoặc xóa Queue trên broker**. Hãy bảo vệ các thao tác start/stop bằng quyền vận hành, auditing và concurrency control.

### 5.3. Vì sao không tạo @Bean DefaultMessageListenerContainer cho cùng endpoint?

Có hai cách giải cùng bài toán nhưng sở hữu khác nhau:

1. **Programmatic endpoint registration:** tạo `SimpleJmsListenerEndpoint`, đăng ký với registrar/registry, để factory/registry quản lý container.
2. **Manual container bean:** tự trả `DefaultMessageListenerContainer` từ `@Bean`, tự set connection factory/destination/listener để Spring quản lý bean đó.

Chúng **không tự đồng nghĩa hoặc chia sẻ registration**. Nếu dùng đồng thời hai cách lên cùng Queue, ứng dụng có thể vô tình tạo **hai competing consumers**, khiến quan sát sai và tăng concurrency ngoài ý định.

## 6. Các tùy chọn của endpoint: ID, selector, concurrency, subscription

Ngoài ba thông số bắt buộc trong ví dụ, `SimpleJmsListenerEndpoint` kế thừa các setter của `AbstractJmsListenerEndpoint`:

| Setter | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `setId(String)` | ID endpoint trong registry | Duy nhất trong cùng registry; không phải tên Queue. |
| `setDestination(String)` | Tên destination | Được resolve bởi resolver của container; cần phù hợp Queue/Topic. |
| `setMessageListener(MessageListener)` | Callback nhận JMS message | Không tự convert sang method payload kiểu `String`. |
| `setSelector(String)` | JMS selector lọc theo headers/properties | Không lọc trực tiếp nội dung JSON body. |
| `setConcurrency(String)` | Override concurrency cho endpoint | Ví dụ `"2-5"`; khả năng scale phụ thuộc container thực. |
| `setSubscription(String)` | Tên subscription cho Topic | Chỉ hợp lệ với subscription mode và client ID tương ứng. |

### 6.1. Chọn selector theo property

```java
endpoint.setSelector("eventType = 'ORDER_CREATED'");
```

Khi publisher gửi message, cần đặt đúng JMS property:

```java
jmsTemplate.send("orders.queue", session -> {
    var message = session.createTextMessage("order-created");
    message.setStringProperty("eventType", "ORDER_CREATED");
    return message;
});
```

Đây là hai snippet độc lập: snippet đầu đặt trong `configureJmsListeners` **trước khi đăng ký**; snippet thứ hai nằm trong service có `JmsTemplate jmsTemplate`. Nếu Queue có message khác selector, endpoint không nhận chúng. Đừng coi “listener không chạy” là broker down trước khi kiểm tra selector.

### 6.2. Concurrency theo từng endpoint

Có thể đặt concurrency chung ở factory:

```java
factory.setConcurrency("1-2");
```

Hoặc chỉ định trên endpoint:

```java
endpoint.setConcurrency("2-4");
```

Đoạn thứ hai có thể override mức factory phù hợp cho endpoint đó. Với `DefaultMessageListenerContainer`, range biểu thị số consumer lõi và giới hạn tối đa theo tải; **không bảo đảm luôn có đúng bốn thread đang nhận**. Với một số container không hỗ trợ scale động, range có thể được diễn giải khác.

**Thận trọng về order:** Queue có nhiều competing consumers có thể xử lý song song; business completion order không được cam kết giống thứ tự gửi. Nếu cần thứ tự theo `orderId`, cân nhắc grouping/partitioning phù hợp broker và cấu hình consumer.

### 6.3. Queue và Topic

Ví dụ chính dùng Queue:

```java
factory.setPubSubDomain(false);
endpoint.setDestination("orders.queue");
```

Nếu dùng Topic, cần một **factory khác** hoặc factory được cấu hình `pubSubDomain=true`:

```java
topicFactory.setPubSubDomain(true);
topicEndpoint.setDestination("orders.events");
```

Đây là snippets; `topicFactory` và `topicEndpoint` phải được tạo riêng và register bằng factory Topic. Nếu dùng durable subscription, cần cấu hình `clientId`/subscription name và lifecycle đúng theo provider. Không chỉ đổi tên Queue sang tên Topic rồi giả định semantics competing consumers giữ nguyên.

## 7. Nhiều endpoint được tạo từ cấu hình tại startup

Một use case quan trọng của programmatic registration là một ứng dụng cần nhiều Queue, nhưng tên Queue chỉ có trong cấu hình lúc deployment.

Giả sử service phải tiêu thụ `orders.created` và `orders.cancelled`. Code có thể chạy một vòng tạo endpoint:

```java
record EndpointSpec(String id, String queue) {}

List<EndpointSpec> specs = List.of(
        new EndpointSpec("orders-created", "orders.created"),
        new EndpointSpec("orders-cancelled", "orders.cancelled")
);

for (EndpointSpec spec : specs) {
    SimpleJmsListenerEndpoint endpoint =
            new SimpleJmsListenerEndpoint();

    endpoint.setId(spec.id());
    endpoint.setDestination(spec.queue());
    endpoint.setMessageListener(message -> {
        // Chuyển message đến handler theo loại endpoint.
        handle(spec.id(), message);
    });

    registrar.registerEndpoint(endpoint);
}
```

Đây là **snippet bên trong `configureJmsListeners`**, giả định `registrar` đã có và `handle(String, Message)` là method do ứng dụng định nghĩa. Cần imports `java.util.List`, `SimpleJmsListenerEndpoint`, và nếu dùng `Message` là `jakarta.jms.Message`.

Lợi ích:
- Dùng chung cơ chế cấu hình và listener container factory.
- Tạo ID riêng cho từng endpoint.
- Có thể bật/tắt endpoint bằng cấu hình **tại thời điểm khởi động** thay vì biên dịch annotation vào mọi method.
- Dễ gắn selector hoặc concurrency khác nhau theo loại Queue.

**Nhưng** tránh tự làm mất quyền kiểm soát cấu hình:
- Validate tên Queue, ID duy nhất và số endpoint trước khi register.
- Giới hạn số Queue được tạo; một Queue/endpoint có thể tiêu thụ nhiều connection/session/threads.
- Tránh lấy ID/destination trực tiếp từ input không tin cậy khi runtime đã có quyền broker.
- Không dùng một `MessageListener` singleton với state mutable không thread-safe cho hàng chục endpoint/concurrent consumers.
- Nếu hàng trăm Queue đồng thời, tính toán tải broker, connection/session pool, retry và monitoring trước khi dùng một loop không giới hạn.

### 7.1. Nhận config qua @ConfigurationProperties

Trong Spring Boot, có thể bind danh sách endpoint từ `application.yml` vào một class `@ConfigurationProperties` rồi inject class đó vào configurer. Sau đó loop trên danh sách trong `configureJmsListeners` như trên.

Ý tưởng:

```yaml
app:
  jms:
    endpoints:
      - id: orders-created
        destination: orders.created
      - id: orders-cancelled
        destination: orders.cancelled
```

Đây là cấu hình mẫu **không tự hoạt động nếu chưa định nghĩa/bật binding `@ConfigurationProperties`**. Khi dùng, phải có validation cho unique IDs, tên destination không trống và allowlist theo broker policy.

**Cần phân biệt** hai kiểu thay đổi: sửa config rồi **restart Spring context** khác với đăng ký endpoint **sau startup**. `JmsListenerConfigurer` được gọi khi infrastructure khởi tạo, không phải callback tự động mỗi khi file config thay đổi trên filesystem.

## 8. Đăng ký sau startup: dùng JmsListenerEndpointRegistry

Đây là trường hợp khác với `configureJmsListeners`. Nếu hệ thống **thực sự cần tạo thêm một endpoint sau khi ApplicationContext đã chạy**, Spring cung cấp method:

```java
registry.registerListenerContainer(
        endpoint, listenerContainerFactory, true);
```

Trong đó:
- `endpoint` là `JmsListenerEndpoint` đã cấu hình đủ (ID/destination/listener).
- `listenerContainerFactory` là factory để tạo container.
- `true` yêu cầu start ngay nếu thích hợp với lifecycle.
- Registry giữ container vừa tạo để quản lý bằng ID.

**Ví dụ service tối giản:**

```java
package example.jms;

import jakarta.jms.MessageListener;

import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;
import org.springframework.stereotype.Service;

@Service
public class RuntimeEndpointRegistration {

    private final JmsListenerEndpointRegistry registry;
    private final DefaultJmsListenerContainerFactory factory;

    public RuntimeEndpointRegistration(
            JmsListenerEndpointRegistry registry,
            DefaultJmsListenerContainerFactory factory) {
        this.registry = registry;
        this.factory = factory;
    }

    public void register(
            String endpointId, String destination, MessageListener listener) {

        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId(endpointId);
        endpoint.setDestination(destination);
        endpoint.setMessageListener(listener);

        registry.registerListenerContainer(endpoint, factory, true);
    }
}
```

Đây là class Java **độc lập về cú pháp** trong Spring project có các bean registry/factory đã cấu hình, nhưng không tự chạy một mình; không có `main` hay broker provisioning. Với example startup mục 4, nếu tạo thêm class này, đừng gọi `register("trainingOrders",...)` vì ID đã tồn tại: registry sẽ báo duplicate ID.

**Tại sao runtime API không dùng registrar?** `JmsListenerEndpointRegistrar` là điểm gom endpoint **trong pha cấu hình**, trong khi registry chịu trách nhiệm tạo/quản lý container thực tế và có API `registerListenerContainer`. Không cất registrar vào singleton rồi tùy tiện gọi `registerEndpoint` từ HTTP request sau khi startup.

### 8.1. Điều kiện an toàn khi đăng ký động

Việc gọi trực tiếp registry có trách nhiệm vận hành lớn hơn so với startup config:
- Bảo vệ bằng quyền quản trị và audit: không cho request không tin cậy tùy tiện tạo consumer trên destination bất kỳ.
- Validate ID/selector/destination và không trùng với container đã đăng ký.
- Cân nhắc concurrency khi nhiều thread cùng thêm endpoint.
- Có strategy khi đăng ký thất bại sau khi broker mất kết nối.
- Tính cách dừng/restart và lifetime của endpoint; `stop()` không đồng nghĩa xóa khỏi registry.
- Quy trình thay đổi tên Queue nên quản lý draining, old message và rollout theo thực tế, không đổi thông tin của endpoint object đã đăng ký rồi mong container tự thay đổi.
- Đảm bảo không tạo endpoint song song ở mọi replica nếu mục tiêu chỉ cần một consumer tại một thời điểm. Với Queue, nhiều replica sẽ trở thành competing consumers; điều này có thể đúng hoặc sai tùy nghiệp vụ.

**Đừng tự suy rằng registry phiên bản bạn dùng có API remove/unregister tương tự Spring AMQP.** Các interface registry giữa các công nghệ không giống nhau. Khi cần dynamic lifecycle phức tạp, đọc Javadoc đúng Spring Framework và thiết kế cleanup/stop riêng.

## 9. Giao dịch, acknowledge và xử lý lỗi

### 9.1. Endpoint không tự quyết định transaction

`SimpleJmsListenerEndpoint` chỉ mô tả cách phân phối message. **Acknowledge và transaction** chủ yếu do listener container/factory quyết định:

```java
factory.setSessionTransacted(true);
```

Trong ví dụ mục 4, factory tạo container có **JMS local transaction**. Sau khi `MessageListener.onMessage` trả về thành công, container commit. Nếu callback ném exception ra ngoài, container có thể rollback và broker redeliver.

Không gắn `@Transactional` vào class configurer để mong các callback tự nằm trong transaction; cấu hình transaction phải ở **container factory, transaction manager hoặc listener business boundary** đúng cách. Một transaction của database không tự atomic với local JMS transaction.

### 9.2. Spring DMLC và raw MessageListener khác nhau

`DefaultMessageListenerContainer` có thể invoke một `MessageListener` nhưng làm việc nhận message ở worker thread của Spring, không nhất thiết đăng ký raw provider callback `MessageConsumer.setMessageListener`. Vì vậy ứng dụng nên theo quy tắc **transaction của container** thay vì tưởng callback luôn chạy dưới một raw async provider handler.

Nếu factory dùng `SimpleJmsListenerContainerFactory` (nếu môi trường cung cấp loại này), cơ chế callback có thể gần với JMS provider hơn; khả năng recovery/concurrency và transaction restrictions khác nhau. **Không chọn factory chỉ dựa vào chữ "Simple" trong endpoint name**.

### 9.3. Không nuốt exception khi cần rollback

```java
@Override
public void onMessage(Message message) {
    try {
        processOrder(message);
    } catch (RuntimeException ex) {
        logger.error("Unable to process", ex);
        // Trả bình thường -> container có thể COMMIT.
    }
}
```

Đây là **anti-pattern minh họa**, `processOrder`/`logger` không được định nghĩa và đoạn này không phải chương trình chạy độc lập. Nếu logic business thất bại và cần broker redeliver, **để exception thoát ra** khi sử dụng transacted container hoặc dùng policy rollback đúng. Nếu muốn dừng retry poison message, cấu hình DLQ/parking queue hay ghi lỗi bền vững; không nên cứ catch mọi exception rồi commit ngầm.

### 9.4. JMS transaction và database không phải một

Ví dụ listener đã ghi order vào SQL rồi JVM chết trước JMS commit. Broker có thể redeliver event, khiến handler ghi SQL lần nữa. Đừng coi `setSessionTransacted(true)` là giao dịch phân tán.

Các giải pháp thường gặp:
- **Idempotent consumer** với business `eventId` làm khóa dedup.
- **Inbox table** ghi event đã xử lý cùng transaction database.
- **Transactional outbox** phía publisher nếu cần bảo đảm DB thay đổi dẫn tới message được gửi.
- JTA/XA khi có hạ tầng thật sự và yêu cầu phù hợp, với chi phí vận hành đáng kể.

### 9.5. Selector không cứu được lỗi nghiệp vụ

Nếu endpoint đặt `selector` sai, listener có thể không nhận bất kỳ message nào dù Queue có backlog. Nếu đặt quá rộng, nhiều loại payload đổ vào một listener và lỗi convert. Sử dụng property schema rõ ràng, metrics theo từng destination/type, và kiểm thử selector với broker.

## 10. So sánh các cách đăng ký listener trong Spring

| Cách | Ví dụ | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| `@JmsListener` | Annotate method `handle(String body)` | Gọn, converter và parameter resolver của Spring hỗ trợ POJO | Tên endpoint gắn trực tiếp vào code/annotation, ít linh hoạt hơn cho danh sách cấu hình động. |
| `SimpleJmsListenerEndpoint` + registrar | `registrar.registerEndpoint(endpoint)` | Đăng ký bằng code ở startup, tùy biến ID/destination/listener | Tự cung cấp raw `MessageListener` và cấu hình factory. |
| `MethodJmsListenerEndpoint` | Mô tả bean + method + handler factory | Có thể đăng ký programmatically một method có argument resolution | API setup phức tạp hơn, không phải `SimpleJmsListenerEndpoint`. |
| Bean `DefaultMessageListenerContainer` thủ công | Tự `new` container trong `@Bean` | Kiểm soát cụ thể container bean | Phải nối nhiều property/lifecycle thủ công, không dùng endpoint registry tự động theo cùng cách. |
| Runtime `registry.registerListenerContainer(...)` | Thêm endpoint khi context đã chạy | Hỗ trợ yêu cầu runtime do quản trị quyết định | Cần quyền, validation, duplicate prevention, audit và shutdown strategy. |

### Ví dụ annotation tương đương về ý tưởng

```java
@Component
public class OrdersAnnotatedReceiver {

    @JmsListener(
            id = "orders-programmatic",
            destination = "orders.queue")
    public void handle(String body) {
        System.out.println("received=" + body);
    }
}
```

Đây là **phương án thay thế**, không nên đưa cùng vào một ApplicationContext đã đăng ký `SimpleJmsListenerEndpoint` với **cùng ID**. Nếu đăng ký trùng ID, registry sẽ báo lỗi. Nếu dùng ID khác nhưng cùng Queue, hai consumer cạnh tranh nhận message, khiến kỳ vọng log một nơi không còn chắc chắn.

`@JmsListener` có thể tự gọi converter để map JMS `TextMessage` sang `String`, trong khi raw `MessageListener` của `SimpleJmsListenerEndpoint` phải tự đọc/cast `Message` hoặc dùng `MessageListenerAdapter` do bạn cấu hình.

## 11. Những lỗi thường gặp khi đăng ký bằng mã

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `configureJmsListeners` không chạy | Thiếu `@EnableJms` hoặc cấu hình ngoài component scan | Đảm bảo config được load, annotation infrastructure được bật. |
| Startup báo thiếu listener container factory | `registrar.registerEndpoint(endpoint)` không tìm được default factory | Khai báo bean `jmsListenerContainerFactory` hoặc chỉ định factory qua registrar. |
| `Another endpoint is already registered with id ...` | Trùng ID giữa code/annotation/runtime | Dùng ID duy nhất và thống nhất convention. |
| `getListenerContainer(id) == null` | ID sai hoặc endpoint chưa đăng ký | Kiểm tra exact ID, timing startup và configurer đã được gọi. |
| Registry có endpoint nhưng không nhận message | Broker offline, Queue sai, credentials/quyền, consumer khác, selector không khớp | Kiểm tra broker health, address/queue routing, metrics, destination và selector. |
| `ClassCastException`/`IllegalArgumentException` từ listener | Raw `MessageListener` nhận kiểu message khác kỳ vọng | Dùng `instanceof`, schema validation và converter/adaptor phù hợp. |
| Không truy cập được `DefaultMessageListenerContainer` bằng `@Autowired` | Container do registry quản lý không phải bean trực tiếp | Lấy `registry.getListenerContainer(endpointId)`. |
| Dùng `SimpleJmsListenerEndpoint` nhưng tưởng sẽ là SMLC | Nhầm endpoint metadata với container type | Xác định container factory; `DefaultJmsListenerContainerFactory` tạo DMLC. |
| Listener exception nhưng message không redeliver | AUTO_ACKNOWLEDGE, hoặc callback catch rồi bỏ qua lỗi | Bật JMS local transaction nếu cần; để exception tới container. |
| Message bị xử lý hai lần | JMS rollback/redelivery, broker restart, publisher retry | Dùng eventId/idempotency; kiểm tra delivery count và DLQ. |
| Concurrency tăng mà thứ tự xử lý thay đổi | Nhiều session/competing consumers | Thử nghiệm ordering/message grouping; không hứa global FIFO business processing. |
| Endpoint được tạo hai lần khi triển khai | Hai cách đăng ký hoặc hai configurer cùng tạo ID | Chỉ đăng ký một nguồn quản lý endpoint; QA danh sách IDs. |
| Sửa cấu hình endpoint object khi chạy nhưng listener không đổi | Container đã được tạo với metadata cũ | Thực hiện rolling restart hoặc quy trình re-registration có kiểm soát. |
| Runtime thêm endpoint nhưng không start | Gọi overload `registerListenerContainer` không yêu cầu start ngay | Dùng cờ `startImmediately=true` khi phù hợp hoặc khởi động container theo lifecycle. |
| Kết nối broker nhưng không có Queue vật lý | Tên destination Java không tự bảo đảm Queue đã provision | Admin tạo Queue hoặc cho phép auto-create theo broker policy. |
| Nhầm Spring JMS với Spring AMQP | Import sai `RabbitListenerEndpointRegistry` | Dùng `org.springframework.jms.config.JmsListenerEndpointRegistry`. |

## 12. Kiểm thử programmatic endpoint thực tế

### 12.1. Unit test cấu hình endpoint không cần broker

Có thể dùng Mockito để mock `JmsListenerEndpointRegistrar` hoặc kiểm tra class configurer trong một ApplicationContext test. Một hướng đơn giản là xác minh:
- `configureJmsListeners` được gọi.
- Endpoint đăng ký có `id`, `destination`, `MessageListener` chính xác.
- Default factory được chỉ định/khai báo đúng.

Pseudo-test:

```java
// Snippet JUnit + Mockito; không phải class test độc lập.
var registrar = mock(JmsListenerEndpointRegistrar.class);
var configurer = new EndpointRegistrationConfig(listener);

configurer.configureJmsListeners(registrar);

verify(registrar).registerEndpoint(
        argThat(endpoint ->
                "trainingOrders".equals(endpoint.getId())
                && "learning.programmatic.queue".equals(
                        endpoint.getDestination())));
```

`listener`, `mock`, `verify` và `argThat` đến từ fixture/test library tương ứng. Đây là kiểm thử **wiring**, không chứng minh JMS delivery thật. Nếu dùng Mockito strict typing và `argThat` cần type phù hợp với overload, cấu hình mock/test imports tương ứng.

### 12.2. Integration: một endpoint, một Queue

1. Khởi động Artemis broker test, có Queue `learning.programmatic.queue`.
2. Nạp Spring context của ví dụ; chỉ tồn tại **một** endpoint ID `trainingOrders`.
3. Assert `registry.getListenerContainer("trainingOrders") != null`.
4. Gửi một message có eventId/payload kiểm soát.
5. Chờ callback bằng Awaitility hoặc CountDownLatch tối đa khoảng vài giây.
6. Kiểm tra body/header, không có exception từ listener.
7. Nếu cần khẳng định transaction commit, quan sát broker và thử failure/rollback riêng; không dùng latch làm bằng chứng commit.

### 12.3. Negative test: trùng ID và thiếu factory

- Tạo thêm một endpoint cùng ID ở một configurer khác và kiểm tra startup thất bại thay vì âm thầm thay thế.
- Xóa bean `jmsListenerContainerFactory` khỏi test context và không khai báo default factory; xác nhận lỗi cấu hình.
- Thử đăng ký endpoint thiếu `destination` hoặc `messageListener`, kiểm tra validation/initialization báo lỗi theo API.

### 12.4. Broker failure và redelivery

- Dừng broker rồi khởi động lại; xác minh DMLC recovery/backoff.
- Để callback ném exception trong transacted container; broker cần redeliver theo policy, có thể có delay/DLQ.
- Giả lập listener xử lý SQL thành công rồi lỗi commit JMS; ứng dụng cần xử lý duplicate eventId.
- Kiểm tra listener lifecycle: start, stop và graceful shutdown mà không tạo thêm duplicate consumer.

### 12.5. Multi-endpoint và selector

- Đăng ký hai endpoint ID khác nhau, mỗi endpoint trỏ một Queue riêng; gửi payload với selector property.
- Xác minh mỗi listener nhận đúng loại message.
- Nếu nhiều endpoint cùng Queue, kiểm tra nhận **competing consumer** thay vì kỳ vọng mỗi endpoint nhận một bản.
- Theo dõi số session/consumer mở trên broker và latency nếu cấu hình tăng số endpoint.

## 13. Checklist trước production

- Bật `@EnableJms` và bảo đảm `JmsListenerConfigurer` được Spring scan.
- Đặt `id` duy nhất, `destination` chính xác, `MessageListener` phù hợp cho từng endpoint.
- Cấu hình default container factory tên `jmsListenerContainerFactory` hoặc chỉ định factory tường minh.
- Đừng nhầm `SimpleJmsListenerEndpoint` với `SimpleMessageListenerContainer`; container type do factory quyết định.
- Để Spring registry quản lý lifecycle; không tự đóng connection/session trong callback.
- Cân nhắc `sessionTransacted=true` cho Queue công việc quan trọng và hiểu redelivery/DLQ/poison message.
- Test listener bean thread-safe dưới concurrency được chọn; không dựa vào thứ tự xử lý global nếu có nhiều consumer.
- Có eventId, idempotency và cơ chế dedup khi database/API downstream có tác dụng phụ.
- Hạn chế đăng ký runtime bằng quyền quản trị, validate inputs, không tạo endpoint không giới hạn.
- Kiểm tra broker URL, credentials, Queue/Topic, selector và TLS thay vì suy từ registry != null.
- Quan sát registry IDs, container running state, Queue depth, message redelivery và error counters.
- Kiểm thử startup, missing factory, duplicate ID, broker outage, restart, stop/start và commit semantics.

## 14. Câu hỏi tự kiểm tra

**1.** Vì sao một `new SimpleJmsListenerEndpoint()` không tự tạo consumer trên broker?

Vì nó là **endpoint metadata**. Phải gọi `registrar.registerEndpoint` (startup) hoặc API registry (runtime) để factory tạo container và bắt đầu nhận.

**2.** `SimpleJmsListenerEndpoint` có buộc dùng `SimpleMessageListenerContainer` không?

Không. Chọn `DefaultJmsListenerContainerFactory` sẽ tạo `DefaultMessageListenerContainer` dù endpoint có từ “Simple”.

**3.** Method nào Spring gọi để code tự đăng ký endpoint ở startup?

`JmsListenerConfigurer.configureJmsListeners(JmsListenerEndpointRegistrar registrar)`, sau đó code gọi `registrar.registerEndpoint(endpoint)`.

**4.** Nếu gọi `registrar.registerEndpoint(endpoint)` mà không truyền factory, cần gì?

Cần default `JmsListenerContainerFactory`, thường là bean tên `jmsListenerContainerFactory` hoặc factory mặc định do configurer chỉ định.

**5.** Muốn lấy một container đã đăng ký theo ID, dùng API nào?

`JmsListenerEndpointRegistry.getListenerContainer(endpointId)`. Container do registry quản lý không nhất thiết là bean có thể inject trực tiếp.

**6.** Muốn tạo thêm endpoint sau khi Spring context đã chạy, có nên gọi lại `configureJmsListeners` thủ công không?

Không. Dùng `JmsListenerEndpointRegistry.registerListenerContainer(endpoint, factory, true)` với policy và authorization phù hợp.

**7.** Callback đã log `received=demo-175` thì đã chắc chắn transaction JMS và database cùng commit chưa?

Không. Log/callback có thể xuất hiện trước JMS commit; local JMS transaction không bao gồm transaction database.

**8.** Có thể cùng một Queue và hai ID khác nhau thì cả hai endpoint đều nhận mỗi message không?

Không trong mô hình Queue competing consumers thông thường. Mỗi message được giao cho một consumer vào một thời điểm; muốn broadcast cần Topic/subscription phù hợp.

## Kết luận

`SimpleJmsListenerEndpoint` cho phép mô tả **listener endpoint bằng Java code**: tạo endpoint, đặt **ID**, **destination** và **MessageListener**, sau đó đăng ký qua **`JmsListenerConfigurer` / `JmsListenerEndpointRegistrar`**. Spring dùng **`JmsListenerContainerFactory`** để tạo container runtime và quản lý nó trong **`JmsListenerEndpointRegistry`**. Cách này đặc biệt hữu ích khi danh sách listener hoặc cấu hình endpoint phải được quyết định **khi khởi động**, thay vì khai báo từng method bằng `@JmsListener`.

Trong production, tách rõ cấu hình startup và đăng ký runtime; kiểm soát unique IDs, destination/selector, transaction, concurrency và lifecycle. Việc endpoint xuất hiện trong registry chứng minh đăng ký thành công, **không tự chứng minh broker/Queue có thể nhận message hoặc business work đã commit**. Hãy bổ sung integration test, idempotency và giám sát vận hành.

## Tài liệu tham khảo

- Spring Framework 6.2 — *Annotation-driven Listener Endpoints*, mục *Programmatic Endpoint Registration*: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — `SimpleJmsListenerEndpoint` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/SimpleJmsListenerEndpoint.html
- Spring Framework 6.2 — `AbstractJmsListenerEndpoint` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/AbstractJmsListenerEndpoint.html
- Spring Framework 6.2 — `JmsListenerConfigurer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListenerConfigurer.html
- Spring Framework 6.2 — `JmsListenerEndpointRegistrar` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistrar.html
- Spring Framework 6.2 — `JmsListenerEndpointRegistry` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Framework — *Using Spring JMS* / listener containers: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Boot 3.5 — JMS & Artemis integration: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Boot 3.5 — Common application properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Jakarta Messaging 3.1 — `MessageListener` API: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messagelistener
- Apache ActiveMQ Artemis — Using JMS: https://artemis.apache.org/components/artemis/documentation/latest/using-jms