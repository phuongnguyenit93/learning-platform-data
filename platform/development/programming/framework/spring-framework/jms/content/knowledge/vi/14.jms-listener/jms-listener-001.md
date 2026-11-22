# Bật hạ tầng endpoint bằng @EnableJms

**Chủ đề:** Spring Framework - jms → @JmsListener

## 1. Vì sao chỉ viết @JmsListener chưa đủ?

Trong Spring JMS, một phương thức được đánh dấu `@JmsListener` có thể đóng vai trò consumer bất đồng bộ:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderConsumer {

    @JmsListener(destination = "orders.incoming")
    public void consume(String orderId) {
        System.out.println("RECEIVED=" + orderId);
    }
}
~~~

Tuy nhiên, một annotation trên phương thức **không tự kết nối tới broker**, không tự tạo thread nhận message và cũng không tự đăng ký consumer nếu ứng dụng thiếu hạ tầng annotation-driven JMS. Spring cần các thành phần nhận diện method, xây dựng endpoint, tạo message listener container và quản lý vòng đời container.

Đối với **Spring Framework thuần**, cách bật cơ chế ấy là đặt `@EnableJms` lên một class cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;

@Configuration
@EnableJms
public class JmsInfrastructureConfig {
    // Các JMS beans cần thiết được cung cấp tại đây hoặc nơi khác.
}
~~~

Đây là **đoạn cấu hình**; để listener thực sự chạy còn cần `ConnectionFactory`, ít nhất một `JmsListenerContainerFactory` phù hợp, bean chứa method `@JmsListener` và một JMS provider/broker khả dụng.

**Phân biệt quan trọng với Spring Boot:** Khi dùng Spring Boot 3.x có JMS starter và điều kiện auto-configuration phù hợp, Boot **tự bật/đăng ký support cho `@JmsListener`**, nên thông thường **không cần tự viết `@EnableJms`**. Việc thêm `@EnableJms` để minh họa cơ chế Framework là hợp lệ, nhưng không đồng nghĩa mọi ứng dụng Boot thiếu annotation này sẽ không nhận được message.

Bài này dùng Java 17+, Spring Framework 6.x / Spring Boot 3.x và namespace Jakarta Messaging `jakarta.jms.*`. Dự án Spring 5/JMS cũ có thể còn dùng `javax.jms.*`; phải dùng API và provider client tương thích, không trộn hai thế hệ.

## 2. @EnableJms thực sự kích hoạt những thành phần nào?

`org.springframework.jms.annotation.EnableJms` là annotation cấu hình Spring. Nó import hạ tầng nội bộ thông qua `JmsBootstrapConfiguration`, đăng ký những component cần thiết để khám phá listener endpoints.

Luồng khái niệm:

~~~text
         @Configuration + @EnableJms
                       |
                       v
             JmsBootstrapConfiguration
                       |
             +---------+----------+
             |                    |
             v                    v
  JmsListenerAnnotation      JmsListenerEndpointRegistry
  BeanPostProcessor
             |
     tìm @JmsListener trên
      Spring-managed beans
             |
             v
      JmsListenerEndpoint
             |
      JmsListenerEndpointRegistrar
             |
             v
     JmsListenerContainerFactory
             |
             v
      MessageListenerContainer
             |
             v
        JMS ConnectionFactory
             |
             v
       Queue / Topic trên broker
             |
             v
      @JmsListener method
~~~

Mỗi thành phần có trách nhiệm riêng:

| Thành phần | Vai trò |
| --- | --- |
| `@EnableJms` | Kích hoạt việc xử lý JMS listener annotations trong Spring Framework |
| `JmsListenerAnnotationBeanPostProcessor` | Phát hiện các phương thức được đánh dấu `@JmsListener` trên Spring-managed beans |
| `JmsListenerEndpoint` | Mô tả endpoint listener đã phát hiện (destination, ID, selector...) |
| `JmsListenerEndpointRegistrar` | Đăng ký endpoint với factory/registry phù hợp |
| `JmsListenerContainerFactory` | Tạo message listener container theo cấu hình |
| `DefaultJmsListenerContainerFactory` | Factory phổ biến, tạo các container nhận JMS bất đồng bộ |
| `JmsListenerEndpointRegistry` | Lưu và quản lý vòng đời container gắn với các annotated endpoints |
| `ConnectionFactory` | Cấp JMS connections/sessions tới provider |
| `MessageListenerContainer` | Thực hiện công việc nhận message và gọi listener method |

**@EnableJms không phải broker launcher.** Nó không thay cho `ConnectionFactory`, không cấp mật khẩu, không provision queue/topic và không bảo đảm message đang có sẵn. Nó chỉ làm Spring hiểu và đăng ký các endpoint được chú thích đúng cách.

### 2.1. Tại sao endpoint registry cần thiết?

Container tạo cho `@JmsListener` thường **không được đăng ký như các bean riêng lẻ thông thường trong ApplicationContext**. Thay vào đó, `JmsListenerEndpointRegistry` quản lý các container ấy, cung cấp cách tra cứu qua endpoint ID và điều khiển vòng đời.

Do đó, việc không tìm thấy bean tên `ordersListener` có kiểu `DefaultMessageListenerContainer` **không chứng minh** listener không hoạt động. Hãy xem `JmsListenerEndpointRegistry` hoặc metric/log của listener container.

### 2.2. Cái gì xảy ra khi ứng dụng khởi động?

Một trình tự thông dụng:

1. Spring tải `@Configuration` và các bean definitions.
2. `@EnableJms` đăng ký JMS annotation infrastructure.
3. Spring khởi tạo các bean thuộc component scan; post-processor tìm `@JmsListener` trên các bean đủ điều kiện.
4. Với mỗi annotation, Spring tạo endpoint definition.
5. Registrar tìm một `JmsListenerContainerFactory` phù hợp, tạo listener container và đưa nó vào registry.
6. Khi context hoàn tất khởi động và container được start theo lifecycle, container mở tài nguyên JMS để tiêu thụ message.
7. Mỗi message phù hợp destination/selector được đưa tới method xử lý.

Điểm 4–6 có thể khác ở chi tiết thứ tự khởi tạo/lifecycle tùy Spring version và factory. Đừng dựa vào một thứ tự log cố định để phát biểu rằng method đã nhận message nếu chưa kiểm chứng broker/consumer thực tế.

## 3. Cách bật trong Spring Framework thuần (không dựa vào Boot)

Với ứng dụng Spring Framework dùng Java Config, cách rõ nhất là:

~~~java
package com.example.config;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
@ComponentScan(basePackages = "com.example")
public class JmsInfrastructureConfig {

    @Bean
    public DefaultJmsListenerContainerFactory
            jmsListenerContainerFactory(
                    ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

Đây là **Java Config có thể biên dịch** khi có Spring Framework 6.x + Spring JMS/Jakarta Messaging dependencies, nhưng **chưa phải ứng dụng chạy độc lập**: cần một bean `jakarta.jms.ConnectionFactory` của JMS provider và một broker cấu hình đúng. `@ComponentScan` phải trỏ tới package chứa listener beans.

Chú ý tên bean được tạo từ method:

~~~java
@Bean
public DefaultJmsListenerContainerFactory
        jmsListenerContainerFactory(ConnectionFactory factory) {
    // ...
}
~~~

Bean có tên mặc định **`jmsListenerContainerFactory`**. Đó là tên mặc định mà infrastructure tìm khi một `@JmsListener` không chỉ rõ `containerFactory`.

### 3.1. Vì sao phải có JmsListenerContainerFactory?

Một `@JmsListener(destination = "orders.incoming")` chỉ cung cấp mô tả endpoint. Factory quyết định **cách tạo consumer**, bao gồm ConnectionFactory, queue/topic domain, concurrency, transaction, converter, error handling và recovery policy phù hợp.

Nếu cấu hình Spring Framework thuần chỉ có `@EnableJms` và `@JmsListener`, nhưng **không có default factory** hoặc custom factory tương ứng, Spring có thể báo lỗi khởi tạo endpoint vì không tìm được bean `jmsListenerContainerFactory`.

Giải pháp: khai báo factory mặc định với đúng tên, hoặc chọn custom factory bằng annotation hay `JmsListenerConfigurer`.

### 3.2. @EnableJms không giống @ComponentScan

Hai annotation làm hai việc khác nhau:

- `@ComponentScan` tìm các class như `@Component` và đăng ký thành **Spring beans**.
- `@EnableJms` bật processor nhận diện `@JmsListener` **trên những beans đã được Spring quản lý**.

Nếu một object được tạo bằng `new OrderConsumer()` nhưng không trở thành Spring bean, Spring không tự xử lý `@JmsListener` của instance đó, dù `@EnableJms` đã bật.

Một listener có thể được khai báo qua `@Component`, `@Service` hoặc thông qua method `@Bean`; điểm quyết định là **bean tồn tại trong context** và processor có thể thấy annotation trên method phù hợp.

## 4. Spring Boot 3.x: trường hợp không cần tự đặt @EnableJms

Spring Boot cung cấp auto-configuration cho JMS khi đã có dependency/provider phù hợp, bao gồm `ConnectionFactory`, `JmsTemplate` và listener infrastructure. Theo hướng dẫn chính thức của Spring, Boot **tự phát hiện các phương thức `@JmsListener`** khi có JMS hạ tầng hợp lệ: không bắt buộc thêm `@EnableJms` trong cấu hình Boot thông thường.

So sánh:

| Nội dung | Spring Framework thuần | Spring Boot với JMS starter |
| --- | --- | --- |
| Kích hoạt `@JmsListener` | Thường phải thêm `@EnableJms` | Boot thường tự kích hoạt |
| `ConnectionFactory` | Ứng dụng/container tự cung cấp | Boot có thể auto-configure nếu đủ điều kiện |
| `jmsListenerContainerFactory` | Thường tự khai báo | Boot có thể auto-configure |
| Bean scan | Phải cấu hình | `@SpringBootApplication` bao gồm component scan |
| Connection tới broker | Tự cấu hình | Dùng properties/autoconfig của provider |
| Tự tạo queue vật lý? | Không mặc định | Boot property cũng không cam kết broker tự provision |

Vì vậy, trong ứng dụng Boot, hai tình huống sau đều có thể hợp lệ:

~~~java
@SpringBootApplication
public class BootJmsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BootJmsApplication.class, args);
    }
}
~~~

và:

~~~java
@SpringBootApplication
@EnableJms
public class BootJmsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BootJmsApplication.class, args);
    }
}
~~~

**Đây là hai lựa chọn thay thế**, không phải hai class cùng tên đặt chung trong một source file. Trong Boot thông thường, cách thứ nhất đủ dùng nếu JMS support được auto-configured. Cách thứ hai thể hiện rõ ý định bật Framework JMS annotation support và phù hợp để học cơ chế. Không cần đặt trùng nhiều `@EnableJms` ở các nơi chỉ vì có nhiều listeners.

### 4.1. Những dependency và cấu hình Boot cần kiểm tra

Với Artemis, dependency điển hình:

~~~text
org.springframework.boot:spring-boot-starter-artemis
~~~

Ngoài dependency Spring JMS, runtime cần provider client, broker URL/credentials hợp lệ và quyền truy cập queue/topic. Có thể dùng Spring Initializr để tạo Maven project đồng bộ version Spring Boot thay vì ghép ngẫu nhiên các phiên bản Spring JMS, Artemis và Jakarta JMS.

Ví dụ cấu hình kết nối:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

`mode=native` kết nối tới **Artemis broker chạy ngoài ứng dụng**; nó không tự khởi động một broker nhúng. `spring.jms.pub-sub-domain=false` dùng queue semantics trong ví dụ. Nếu ứng dụng cần topic, producer và listener container phải cùng cấu hình domain/destination phù hợp.

## 5. Ví dụ chạy được: Spring Boot + @EnableJms + @JmsListener

Ví dụ này cố ý đặt `@EnableJms` để thể hiện chính xác mục tiêu bài học, mặc dù một ứng dụng Boot có đầy đủ auto-configuration thường hoạt động mà không cần annotation đó.

### 5.1. Chuẩn bị

Tạo dự án trên [Spring Initializr](https://start.spring.io/):

- Java **17+**, Spring Boot **3.x**, build system Maven.
- Group `com.example`, artifact `jms-enable-demo`.
- Dependency **Spring for Apache ActiveMQ Artemis** (Maven `org.springframework.boot:spring-boot-starter-artemis`).
- Một Artemis broker đang chạy ở `tcp://localhost:61616`.
- Tài khoản broker được phép kết nối, gửi và tiêu thụ queue `demo.jms.orders`.
- Queue `demo.jms.orders` đã provision hoặc broker cho phép auto-create phù hợp.

Cấp biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD` theo broker. Không đưa thông tin đăng nhập thật vào source control.

Tạo `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}

spring.jms.pub-sub-domain=false
~~~

Với broker native, Spring Boot **không tự tạo** Artemis server. Việc khởi động broker, tạo địa chỉ/queue, cấu hình security nằm ngoài mã Spring của ví dụ.

Tạo file `src/main/java/com/example/EnableJmsDemoApplication.java`:

~~~java
package com.example;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class EnableJmsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(EnableJmsDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner publish(
            JmsTemplate template,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            boolean registered =
                    registry.getListenerContainer("ordersEndpoint") != null;
            System.out.println("ENDPOINT_REGISTERED=" + registered);

            if (!registered) {
                throw new IllegalStateException(
                        "JMS listener endpoint not registered");
            }

            // Producer thêm property để selector của listener khớp.
            template.convertAndSend(
                    "demo.jms.orders",
                    "order-42",
                    message -> {
                        message.setStringProperty(
                                "eventType", "ORDER_CREATED");
                        return message;
                    });

            System.out.println("SENT=order-42");
        };
    }
}

@Component
class OrderEndpoint {

    @JmsListener(
            id = "ordersEndpoint",
            destination = "demo.jms.orders",
            selector = "eventType = 'ORDER_CREATED'")
    public void onOrder(Message message) throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected TextMessage");
        }

        System.out.println("RECEIVED=" + textMessage.getText());
        System.out.println("EVENT_TYPE="
                + message.getStringProperty("eventType"));
    }
}
~~~

**Lý do code có thể biên dịch:**

1. File chỉ có một public class `EnableJmsDemoApplication` trùng với filename. `OrderEndpoint` package-private nhưng là Spring-managed component trong cùng package scan.
2. `@SpringBootApplication` đăng ký configuration, component scanning và auto-configuration.
3. `@EnableJms` bật bộ nhận diện các phương thức `@JmsListener`.
4. Spring Boot tạo `ConnectionFactory`/`JmsTemplate`/default listener factory nếu starter và cấu hình đáp ứng điều kiện; không cần tự thêm một factory trong ví dụ này.
5. `@JmsListener(id = "ordersEndpoint", ...)` tạo endpoint có ID dùng để tra cứu từ `JmsListenerEndpointRegistry`.
6. Producer đặt property `eventType = ORDER_CREATED` để selector match. Listener đọc raw `jakarta.jms.Message`, nên có thể truy cập body và property.
7. AppRunner bắt đầu sau khi context được khởi tạo; registry đã có metadata endpoint được đăng ký. Container phải start và kết nối thành công để nhận message thực sự.

### 5.2. Chạy chương trình

Trong thư mục root của project Maven:

~~~bash
mvn spring-boot:run
~~~

Với Maven Wrapper trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Nếu broker, credentials, queue, listener factory và các permission đều hợp lệ, các dòng nghiệp vụ kỳ vọng:

~~~text
ENDPOINT_REGISTERED=true
SENT=order-42
RECEIVED=order-42
EVENT_TYPE=ORDER_CREATED
~~~

**Đây là một cách trình bày stdout kỳ vọng, không phải thứ tự thời gian bất biến.** Spring Boot còn có startup logs; hai dòng listener `RECEIVED`/`EVENT_TYPE` có thể xuất hiện **trước hoặc sau** `SENT=order-42` vì listener chạy bất đồng bộ. Dòng `ENDPOINT_REGISTERED=true` được in trước thao tác send bởi chính AppRunner.

Nếu application có message cũ trong queue, listener có thể in thêm dữ liệu, hoặc nhận message cũ trước khi AppRunner gửi. Nếu broker không kết nối được, ứng dụng có thể lỗi startup hoặc send; chỉ có endpoint registry không chứng minh broker đang hoạt động.

### 5.3. Bằng chứng endpoint tồn tại khác với message đã được xử lý

Kết quả `ENDPOINT_REGISTERED=true` chứng minh **endpoint đã được đăng ký** với registry. Nó không bảo đảm:

- Listener container đang `running`; có thể bị dừng/disable.
- Broker đang online hoặc queue tồn tại.
- Selector đã có message phù hợp.
- Handler chạy thành công, transaction được commit hay dữ liệu nghiệp vụ đã được lưu.

Muốn kiểm tra container được start, có thể tra `registry.getListenerContainer("ordersEndpoint").isRunning()` khi lifecycle đã khởi động. Khi monitor production, kiểm tra thêm logs, metrics broker, JMS consumer count và xử lý nghiệp vụ thực tế.

### 5.4. Thử bỏ @EnableJms

Trong Spring Boot demo với JMS auto-configuration bình thường, xóa `@EnableJms` rồi chạy lại: annotation-driven listener **vẫn thường được phát hiện** bởi Boot. Đây là kiểm chứng hữu ích về sự khác biệt **giữa việc Spring Framework yêu cầu kích hoạt rõ và Boot chủ động auto-configure**.

Nếu chuyển demo sang dự án **Spring Framework thuần không có Boot auto-configuration**, bạn phải cung cấp `@EnableJms`, bean factory và ConnectionFactory theo phần 3.

## 6. Factory mặc định và chọn factory riêng cho từng endpoint

### 6.1. Tên bean mặc định là jmsListenerContainerFactory

Khi annotation không đặt `containerFactory`:

~~~java
@JmsListener(destination = "orders.incoming")
public void receive(String body) {
    System.out.println(body);
}
~~~

infrastructure tìm **factory mặc định**, thông thường một bean có tên:

~~~text
jmsListenerContainerFactory
~~~

Điều này khác tên `ConnectionFactory` và khác tên `JmsTemplate`. `JmsListenerContainerFactory` **không phải** một đối tượng `ConnectionFactory`; nó nhận JMS ConnectionFactory làm dependency để tạo listener containers.

### 6.2. Cấu hình factory cụ thể

Ví dụ Spring Java Config dùng khi muốn kiểm soát transaction/concurrency:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class OrdersListenerConfig {

    @Bean("ordersListenerFactory")
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-5");
        return factory;
    }
}
~~~

Đây là **cấu hình phụ thuộc vào ConnectionFactory bean**, không phải chương trình độc lập. Khi có nhiều listeners với nhu cầu khác nhau, chỉ định factory trên annotation:

~~~java
@JmsListener(
        destination = "orders.incoming",
        containerFactory = "ordersListenerFactory")
public void onOrder(String body) {
    System.out.println(body);
}
~~~

Tên thuộc tính annotation chính xác là **`containerFactory`**, không phải `factory` hay `connectionFactory`. Giá trị là **tên bean** loại `JmsListenerContainerFactory`; bean phải tồn tại và tương thích với destination/provider.

Nếu một annotation **không** chỉ định factory và không có factory mặc định thì cần định nghĩa thêm `jmsListenerContainerFactory` hoặc cấu hình default qua `JmsListenerConfigurer`. Có một custom bean tên `ordersListenerFactory` không tự khiến mọi listener dùng bean ấy.

### 6.3. Những cấu hình nên xác định tại factory

| Thiết lập | Tác dụng | Cần lưu ý |
| --- | --- | --- |
| `setConnectionFactory(...)` | Chọn JMS provider/kết nối | Đúng URL, credentials, JMS namespace |
| `setConcurrency("2-5")` | Cho phép nhiều consumer/threads theo container implementation | Tải broker, ordering, competing consumers |
| `setSessionTransacted(true)` | Sử dụng local JMS session transaction | Rollback/redelivery; không tự bao trùm database |
| `setPubSubDomain(true/false)` | Chọn Topic hoặc Queue khi resolve tên | Consumer cần đúng domain |
| `setDestinationResolver(...)` | Cách chuyển destination name thành object | Dynamic resolver/JNDI theo provider |
| `setMessageConverter(...)` | Ánh xạ JMS Message với method payload | Có thể khác converter của `JmsTemplate` |
| `setErrorHandler(...)` | Xử lý lỗi ngoài luồng nhận theo container | Không thay thế transaction/redelivery policy |
| `setAutoStartup(false)` | Không tự start listener container | Cần start chủ động qua lifecycle/registry |

Một số setting phụ thuộc loại listener container được factory tạo; cần xem Javadoc phiên bản đang dùng, đặc biệt khi chỉnh recovery, cache và transaction manager. Đừng copy toàn bộ tuning của một broker/provider sang môi trường khác mà không kiểm chứng.

## 7. JmsListenerEndpointRegistry: quan sát và điều khiển listener

Registry là thành phần được annotation-driven infrastructure đăng ký. Có thể inject nó vào một bean Spring:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;

class RegistryInspector {

    private final JmsListenerEndpointRegistry registry;

    RegistryInspector(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    void inspect() {
        var container =
                registry.getListenerContainer("ordersEndpoint");
        if (container == null) {
            System.out.println("NOT_REGISTERED");
            return;
        }
        System.out.println("REGISTERED");
        System.out.println("RUNNING=" + container.isRunning());
    }
}
~~~

Đây là **class minh họa**: muốn Spring inject constructor, phải đăng ký class làm bean qua `@Component` hoặc `@Bean`. ID `ordersEndpoint` phải trùng với `@JmsListener(id = "ordersEndpoint", ...)`.

Các khả năng điển hình:

- `getListenerContainer(String id)` — lấy container theo endpoint ID, hoặc `null` nếu không tồn tại.
- `getListenerContainers()` — duyệt các listener containers do registry quản lý.
- `isRunning()` — kiểm tra registry/container đang hoạt động theo lifecycle.
- `start()`, `stop()` — thao tác lifecycle ở cấp registry hoặc container tương ứng.

### 7.1. Dừng/start đúng endpoint, không dừng nhầm tất cả

Ví dụ khi bạn chủ động triển khai một chức năng pause/resume:

~~~java
var container = registry.getListenerContainer("ordersEndpoint");
if (container == null) {
    throw new IllegalArgumentException("Unknown endpoint id");
}

// Chỉ pause listener ứng với id này.
container.stop();

// Sau khi có quyết định resume hợp lệ:
container.start();
~~~

Đây là **đoạn service quản trị minh họa**, cần `registry` bean và cơ chế authorization/operational controls nếu expose qua HTTP. Đừng gọi stop/start tùy tiện trong code nghiệp vụ cho mỗi message: listener lifecycle thuộc vận hành và có thể ảnh hưởng các message đang xử lý.

Khi container `isRunning() == true`, nó đã được start theo Spring lifecycle; điều đó vẫn không đảm bảo broker cung cấp message, credential luôn hợp lệ hoặc listener processing thành công.

### 7.2. Tránh thay đổi hạ tầng bằng cách new trực tiếp một @JmsListener class

~~~java
OrderEndpoint endpoint = new OrderEndpoint();
~~~

Đoạn trên là Java code hợp lệ **nhưng không đăng ký listener JMS**: Spring chưa hề quản lý object đó. Registry không biết method `@JmsListener` của instance tự tạo. Cần đăng ký bean qua component scanning/@Bean để post-processor xử lý.

## 8. @JmsListener có thể mô tả nhiều thứ hơn destination

`@EnableJms` bật infrastructure. Mỗi `@JmsListener` định nghĩa endpoint cụ thể. Những thuộc tính thường dùng:

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `destination` | `"orders.incoming"` | Tên queue/topic để nhận |
| `id` | `"ordersEndpoint"` | ID duy nhất để tra trong registry |
| `containerFactory` | `"ordersListenerFactory"` | Bean factory tạo container |
| `selector` | `"eventType = 'ORDER_CREATED'"` | JMS selector lọc headers/properties |
| `concurrency` | `"2-5"` | Override concurrency nếu factory/container hỗ trợ |
| `subscription` | `"billingService"` | Tên subscription cho topic theo semantics có liên quan |

Không nhất thiết đặt mọi thuộc tính. Một method đơn giản:

~~~java
@JmsListener(destination = "orders.incoming")
public void handle(String text) {
    System.out.println(text);
}
~~~

đã có thể được infrastructure xử lý nếu Spring quản lý bean và factory/kết nối hoạt động. Với payload String, Spring handler adapter sẽ chuyển JMS message thành tham số theo converter phù hợp. Nếu nhận raw JMS message:

~~~java
@JmsListener(destination = "orders.incoming")
public void handleRaw(jakarta.jms.Message message)
        throws jakarta.jms.JMSException {
    System.out.println(message.getJMSMessageID());
}
~~~

bạn có thể đọc trực tiếp headers/properties. Cả hai là **trích đoạn method trong Spring-managed bean**, không phải code độc lập. Đừng khai báo hai method listener tiêu thụ cùng queue chỉ để mong **mỗi message được xử lý hai lần**: trên queue chúng có thể là competing consumers.

### 8.1. Một endpoint được gọi khi nào?

Không phải thời điểm Java method khai báo hay class nạp vào JVM. Nó được gọi khi:

1. Spring bean đã được phát hiện.
2. `@JmsListener` đã được processor nhận diện và endpoint đăng ký.
3. Container đã start và kết nối đến destination.
4. Broker giao một message đủ điều kiện.
5. Container/adapter chuyển message thành method arguments và gọi handler.

Nếu method signature cần DTO nhưng converter chưa biết deserialize payload, message có thể tới container rồi thất bại trước khi vào body method. Điều đó khác với tình huống endpoint hoàn toàn chưa được đăng ký.

### 8.2. Repeatable @JmsListener

Spring cho phép lặp `@JmsListener` trên cùng một method để mô tả nhiều endpoints:

~~~java
@JmsListener(
        id = "ordersAEndpoint",
        destination = "orders.a")
@JmsListener(
        id = "ordersBEndpoint",
        destination = "orders.b")
public void handleMany(String payload) {
    System.out.println(payload);
}
~~~

Đây là **trích đoạn trong bean**, cần Java imports và JMS hạ tầng. Mỗi annotation mô tả một endpoint/container tương ứng với destination riêng. ID nên khác nhau để registry quản lý rõ. Không coi repeatable annotation là cơ chế gộp hai JMS queues thành một queue.

## 9. Tùy biến default factory bằng JmsListenerConfigurer

Khi factory mặc định không có tên `jmsListenerContainerFactory`, hoặc muốn chủ động đăng ký endpoint, Spring có interface `JmsListenerConfigurer` và callback `configureJmsListeners(JmsListenerEndpointRegistrar)`.

Ví dụ rút gọn:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;

@Configuration
@EnableJms
class RegistrarConfig implements JmsListenerConfigurer {

    private final JmsListenerContainerFactory<?> factory;

    RegistrarConfig(
            @Qualifier("ordersListenerFactory")
            JmsListenerContainerFactory<?> factory) {
        this.factory = factory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        registrar.setContainerFactory(factory);
    }
}
~~~

Đây là **cấu hình minh họa**, giả định đã tồn tại bean `ordersListenerFactory` hợp lệ. Registrar sẽ sử dụng factory này làm default cho các endpoints không nêu `containerFactory`. Đặt tên bean một cách nhất quán để tránh lỗi injection hoặc chọn nhầm factory.

Một tình huống nâng cao là đăng ký `SimpleJmsListenerEndpoint` bằng code thay vì annotation, chẳng hạn khi endpoint definitions được xây từ cấu hình. Tuy nhiên điều này vẫn cần registrar, registry, factory và ConnectionFactory đúng cách; không làm thay đổi quy tắc JMS queue/topic.

### 9.1. Khi nào KHÔNG cần JmsListenerConfigurer?

Nếu dự án chỉ có một factory tên `jmsListenerContainerFactory`, và mọi method dùng cấu hình chung, không cần interface nâng cao. Với Spring Boot, nhiều trường hợp cũng không cần tự khai báo factory. Hãy bắt đầu bằng cấu hình tối giản hoạt động được rồi chỉ tùy biến khi thật sự cần transaction, concurrency, message conversion hoặc factory riêng.

## 10. @EnableJms, @JmsListener và JmsTemplate không giống nhau

| Thành phần | Thuộc tầng | Trách nhiệm |
| --- | --- | --- |
| `@EnableJms` | Spring configuration | Bật annotation-driven JMS endpoint processing |
| `@JmsListener` | Method endpoint | Khai báo consumer sẽ gọi method khi có message |
| `JmsListenerContainerFactory` | Infrastructure configuration | Tạo và cấu hình listener container |
| `JmsListenerEndpointRegistry` | Lifecycle/registry | Tra cứu/quản lý containers của annotated endpoints |
| `JmsTemplate` | Client operations | Gửi message; hoặc receive đồng bộ khi được gọi |
| `ConnectionFactory` | JMS provider | Cấp connections/sessions/context |
| JMS broker | Hạ tầng messaging | Chứa/định tuyến messages theo queue/topic, chính sách provider |

Một ứng dụng có thể **chỉ gửi message** bằng `JmsTemplate.convertAndSend(...)` mà **không cần `@EnableJms`**, vì nó không sử dụng annotation-driven listeners. Ngược lại, một ứng dụng consumer có `@JmsListener` có thể không trực tiếp gọi `JmsTemplate.receive()` ở đâu cả.

Không nhầm với:

- `@EnableScheduling`: bật xử lý Spring scheduled methods (khác JMS).
- `@EnableAsync`: bật xử lý `@Async` methods (khác listener container).
- `@EnableRabbit`: hạ tầng listener cho RabbitMQ theo Spring AMQP (không phải JMS API).
- `@EnableKafka`: hạ tầng listener cho Kafka (không phải JMS).
- `@EnableJms`: chỉ dành cho annotation-driven **JMS** endpoints.

Nếu ứng dụng có nhiều công nghệ messaging, mỗi loại có cấu hình, factory và quy tắc lifecycle riêng. Đừng áp dụng tên property/factory của RabbitMQ hay Kafka lên `@JmsListener`.

## 11. Transaction, concurrency và lifecycle sau khi kích hoạt

Bật `@EnableJms` chỉ tạo **khả năng đăng ký endpoints**. Độ tin cậy của việc xử lý message phụ thuộc listener container configuration.

### 11.1. Concurrency

Với một queue, `factory.setConcurrency("2-5")` thường cho phép container quản lý số lượng concurrent consumers theo implementation. Điều đó tăng throughput trong một số workload nhưng có hệ quả:

- Message có thể được xử lý đồng thời; thứ tự hoàn tất không nhất thiết là thứ tự gửi.
- Database/HTTP dependencies chịu thêm concurrency.
- Nếu nhiều instance cùng consume một queue, chúng cùng cạnh tranh phân phối message.
- Các hành vi ordering đặc biệt như JMS message groups cần cấu hình/kiểm chứng ở provider.
- `@JmsListener(concurrency="...")` có thể override factory setting cho endpoint nếu container hỗ trợ.

Đừng tăng concurrency chỉ để “bật @JmsListener”. Nên kiểm tra handler idempotency, thread-safety và broker quota.

### 11.2. Transaction và acknowledgment

Khi listener method ném exception, broker có redeliver hay không **phụ thuộc cấu hình ack/transaction**. Không phải cứ có `@EnableJms` là auto rollback.

Ví dụ:

~~~java
factory.setSessionTransacted(true);
~~~

Đây là một cấu hình **JMS local session transaction** thường dùng khi muốn container rollback JMS session nếu xử lý thất bại. Tuy nhiên:

- Transaction JMS không tự bao gồm commit database của ứng dụng.
- Listener có thể được gọi lại khi redelivery; business logic nên idempotent.
- Provider có chính sách retry/DLQ riêng; cần giám sát poison messages.
- Nếu sử dụng external transaction manager/JTA, cần cấu hình tương ứng chứ không chỉ đặt `sessionTransacted=true`.

Với AUTO_ACKNOWLEDGE và một số loại listener container, thời điểm ack có thể diễn ra trước lúc business method hoàn tất; vì vậy không được hứa mọi lỗi method đều được redeliver khi chưa kiểm thử config thực tế.

### 11.3. Auto-startup và chủ động start

Factory có thể được cấu hình:

~~~java
factory.setAutoStartup(false);
~~~

Khi đó endpoint vẫn có thể **được đăng ký** nhưng container chưa start; `registry.getListenerContainer("ordersEndpoint")` có thể trả object hợp lệ dù `isRunning() == false`.

Khi môi trường/broker đã sẵn sàng và ứng dụng có quyền điều khiển lifecycle, có thể gọi `container.start()`. Không đưa điều khiển start/stop vào mỗi business event một cách tùy tiện. Với hệ thống production, cần cơ chế shutdown/graceful drain và giám sát consumer health.

### 11.4. Khác biệt Queue và Topic

Trong Spring, một factory/container có thể cấu hình `pubSubDomain`:

~~~java
factory.setPubSubDomain(false); // queue
factory.setPubSubDomain(true);  // topic
~~~

Hai dòng là **hai lựa chọn thay thế**, không phải một cấu hình chạy cùng lúc. Với Topic, cần xem subscription (durable/shared), client identity và vòng đời; consumer chỉ hiện diện khi subscription được thiết lập tương ứng. Không suy luận rằng đặt tên destination có chữ `"topic"` tự thay đổi JMS domain.

## 12. Các lỗi thường gặp khi bật @EnableJms

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Spring Framework thuần không nhận ra `@JmsListener` | Chưa bật `@EnableJms` | Đặt trên `@Configuration` được context import/scan |
| Boot không có `@EnableJms` nhưng listener vẫn hoạt động | Boot JMS auto-configuration đã bật infrastructure | Đây có thể là hành vi bình thường |
| Có `@EnableJms` nhưng không nhận message | Chưa có factory, ConnectionFactory, broker hoặc endpoint bean | Kiểm tra đầy đủ các tầng; annotation không tự nối broker |
| Báo không tìm thấy `jmsListenerContainerFactory` | Endpoint không chỉ rõ factory, default factory chưa tồn tại | Định nghĩa bean đúng tên hoặc dùng `JmsListenerConfigurer` |
| `@JmsListener(containerFactory="ordersFactory")` báo lỗi | Tên bean không tồn tại hoặc bean sai loại | Kiểm tra chính xác bean name và kiểu `JmsListenerContainerFactory` |
| `registry.getListenerContainer("ordersEndpoint")` trả `null` | ID sai, listener bean chưa được scan/đăng ký | Kiểm tra component scan, ID, processor, context |
| Registry thấy endpoint nhưng `isRunning=false` | Factory tắt autoStartup hoặc container bị stop | Xem lifecycle, start đúng container khi phù hợp |
| Endpoint đang running nhưng queue không được nhận | Sai destination, queue chưa provision, ACL, broker offline, selector không match | Kiểm tra broker/queue metrics, network và selector |
| Dùng `javax.jms.Message` với Spring Boot 3 | Namespace không khớp Jakarta JMS | Dùng `jakarta.jms.Message`/client tương thích |
| Listener nhận body lỗi convert | Converter không khớp message type hoặc DTO | Kiểm tra listener converter và JMS Message thực |
| Listener không thấy class trong component scan | Class không được quản lý bởi Spring hoặc ngoài base package | Đăng ký bean/điều chỉnh component scan |
| Message được xử lý nhiều lần | Rollback/redelivery/restart consumer hoặc lỗi ack | Thiết kế idempotency, kiểm tra transaction/DLQ |
| Consumer quá tải khi concurrency cao | Quá nhiều consumers/threads | Đo throughput, giảm concurrency, backpressure |
| Không thấy message phát tới Topic | Sai domain/subscription lifecycle | Kiểm tra `pubSubDomain` và durable/shared subscription |
| Đổi annotation runtime nhưng container không đổi | Endpoint được đăng ký lúc khởi tạo | Reload config/restart container đúng cách, tránh mutate annotation |

### 12.1. Quy trình điều tra theo từng tầng

~~~text
@JmsListener method đã nằm trong Spring-managed bean?
     |
     +-- Không --> kiểm tra @ComponentScan/@Bean
     |
     v
Spring Framework có @EnableJms hoặc Boot auto-configuration hợp lệ?
     |
     +-- Không --> bật annotation infrastructure
     |
     v
Có JmsListenerContainerFactory phù hợp?
     |
     +-- Không --> khai báo bean jmsListenerContainerFactory/custom bean
     |
     v
Registry có endpoint ID?
     |
     +-- Không --> kiểm tra processing annotation, bean scan, ID
     |
     v
Container có start và kết nối được tới broker?
     |
     +-- Không --> connection/ACL/autostart/recovery
     |
     v
Queue/topic đúng và có message phù hợp?
     |
     +-- Không --> destination, pubSubDomain, selector, TTL, competing consumers
     |
     v
Method argument conversion và business processing có thành công?
     |
     +-- Không --> converter, exception, transaction, redelivery, DLQ
     |
     v
Hoạt động
~~~

Đường chẩn đoán này phân biệt lỗi **hạ tầng annotation chưa bật** với lỗi **broker/message delivery** và lỗi **business method**. Đó là mục đích lớn nhất của việc hiểu `@EnableJms`, thay vì chỉ thêm annotation cho hết cảnh báo.

## 13. Checklist triển khai production

1. **Đúng namespace:** Spring Framework 6/Boot 3 sử dụng `jakarta.jms.*`, không pha với `javax.jms.*` cũ.
2. **Đúng cơ chế kích hoạt:** Spring thuần có `@EnableJms`; Spring Boot xác minh auto-configuration thay vì thêm annotation theo thói quen.
3. **Spring-managed bean:** `@JmsListener` ở class được scan hoặc đăng ký qua `@Bean`.
4. **Factory rõ ràng:** có `jmsListenerContainerFactory` mặc định hoặc custom factory được chỉ định bằng `containerFactory`.
5. **ConnectionFactory:** đúng broker URL, credentials, TLS, provider client, quyền connect/send/consume.
6. **Destination:** đúng tên, Queue/Topic domain; provision/auto-create theo chính sách broker.
7. **Endpoint ID:** đặt ID duy nhất nếu cần vận hành qua registry.
8. **Selector:** dùng typed properties đúng; sai kiểu có thể làm listener không nhận message.
9. **Concurrency:** xác định mức phù hợp với workload và ordering/idempotency.
10. **Transactions:** kiểm tra ack/commit/rollback/redelivery thực tế; thiết kế DLQ và retry.
11. **Converter:** handler String/DTO/raw Message có đường convert đúng, schema tương thích.
12. **Lifecycle:** biết lúc nào container start/stop, hỗ trợ graceful shutdown.
13. **Observability:** đo số consumers, queue depth, message age, conversion errors và handler failures.
14. **Bảo mật:** tránh log secrets/payload nhạy cảm, áp dụng ACL và authorization ngoài selector.
15. **Kiểm thử tích hợp:** không chỉ unit-test annotation; chạy với broker thử nghiệm hoặc JMS test infrastructure để xác thực đăng ký/gửi/nhận.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Trong Spring Framework thuần, annotation nào kích hoạt việc phát hiện các phương thức `@JmsListener`?

**Đáp án:** `@EnableJms` trên một class `@Configuration` được Spring nạp; đồng thời phải có các bean JMS/factory cần thiết.

**Câu 2.** Vì sao một Spring Boot 3 app có `@JmsListener` vẫn có thể chạy khi không viết `@EnableJms`?

**Đáp án:** Spring Boot với JMS starter và auto-configuration hợp lệ có thể tự bật JMS listener annotation infrastructure.

**Câu 3.** `@EnableJms` có tạo `ConnectionFactory` hoặc chạy broker không?

**Đáp án:** Không. Nó chỉ kích hoạt xử lý annotated endpoints. ConnectionFactory/provider và broker cần được cấu hình độc lập.

**Câu 4.** Infrastructure tìm factory nào nếu `@JmsListener` không có thuộc tính `containerFactory`?

**Đáp án:** Thông thường bean tên `jmsListenerContainerFactory`, trừ khi default được cấu hình riêng qua `JmsListenerConfigurer`.

**Câu 5.** `@EnableJms` có làm Spring nhận ra một listener object được tạo thủ công bằng `new` không?

**Đáp án:** Không. Bean phải được Spring quản lý để post-processor phát hiện method annotation.

**Câu 6.** Muốn dùng một factory có bean name `ordersListenerFactory` cho một listener, annotation viết gì?

**Đáp án:** `@JmsListener(destination="...", containerFactory="ordersListenerFactory")`.

**Câu 7.** `JmsListenerEndpointRegistry.getListenerContainer("id")` được dùng để làm gì?

**Đáp án:** Tra cứu container của endpoint ID để quan sát và quản lý lifecycle; không phải để trực tiếp lấy JMS Message.

**Câu 8.** `registry.getListenerContainer(id) != null` có chắc message sẽ đến method không?

**Đáp án:** Không. Nó chỉ xác nhận đăng ký. Container phải running, broker/queue/quyền đúng và có message phù hợp.

**Câu 9.** Hai `@JmsListener` cùng consume một queue có làm mọi message được xử lý hai lần không?

**Đáp án:** Không. Queue thường dùng competing consumers; mỗi delivery chỉ giao một consumer đủ điều kiện. Topic/subscription mới phục vụ fan-out.

**Câu 10.** Vì sao bật `setSessionTransacted(true)` ở factory không tự bảo đảm database và JMS commit atomic?

**Đáp án:** Đó là JMS session transaction, không tự mở transaction toàn cục qua cả database; cần thiết kế transaction/outbox hoặc JTA/XA thích hợp.

**Câu 11.** Nếu listener đã được đăng ký nhưng không chạy do `setAutoStartup(false)`, phải sửa annotation `@EnableJms` không?

**Đáp án:** Không. Đây là vấn đề lifecycle/startup của container; dùng registry hoặc cấu hình factory để start đúng lúc.

**Câu 12.** Tại sao cần tách lỗi bean discovery, JMS connection và handler conversion khi debug?

**Đáp án:** Vì ba lỗi xảy ra ở ba tầng khác nhau: endpoint chưa đăng ký, container không kết nối/nhận được message, hoặc message đến rồi nhưng convert/business method thất bại.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html): `@EnableJms`, factory mặc định, JMS endpoint registration, lifecycle registry và tham số listener.
- [Spring Framework 6.2 Javadoc — EnableJms](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/EnableJms.html): annotation, `JmsBootstrapConfiguration`, cơ chế phát hiện `@JmsListener`, `JmsListenerConfigurer`.
- [Spring Framework 6.2 Javadoc — JmsListener](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/JmsListener.html): `id`, `destination`, `selector`, `containerFactory`, `concurrency`, `subscription`.
- [Spring Framework 6.2 Javadoc — JmsListenerEndpointRegistry](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html): quản lý container bằng endpoint ID và lifecycle.
- [Spring Framework 6.2 Javadoc — DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): factory configuration cho listener.
- [Spring Boot 3.5 — JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): Artemis, auto-configured JMS resources và listener.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): ví dụ Spring Boot auto-discover `@JmsListener` không yêu cầu thêm `@EnableJms`.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): queue/topic semantics, consumers, connection/session và acknowledgments.
