# Tên mặc định jmsListenerContainerFactory

> **Chủ đề:** `@JmsListener` trong Spring Framework JMS. Nếu một phương thức được đánh dấu `@JmsListener` mà **không khai báo `containerFactory`**, cơ chế đăng ký listener của Spring theo mặc định sẽ tìm **một Spring bean có tên chính xác `jmsListenerContainerFactory`**. Đây là *quy ước tên bean để chọn factory*, không phải tên queue, không phải tên của một listener thread, và cũng không có nghĩa Spring Framework thuần luôn tự tạo sẵn bean ấy.

## 1. Câu trả lời cốt lõi

Ví dụ:

~~~java
@Component
public class OrderConsumer {

    @JmsListener(destination = "orders.inbox")
    public void onOrder(String body) {
        System.out.println(body);
    }
}
~~~

Ở đây không có `containerFactory = ...`. Với hạ tầng `@EnableJms` thông thường, Spring tra cứu bean tên:

~~~text
jmsListenerContainerFactory
~~~

Bean ấy triển khai `org.springframework.jms.config.JmsListenerContainerFactory<?>`; ví dụ điển hình là `org.springframework.jms.config.DefaultJmsListenerContainerFactory`. Factory tạo **message listener container cho endpoint**. Container quản lý JMS connection/session/consumer và gọi phương thức `onOrder` khi có message.

**Phân biệt ba tên:**

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Bean name của factory** | `jmsListenerContainerFactory` | Được `@JmsListener` dùng để tạo container khi không chỉ định tên khác |
| **Destination/queue name** | `orders.inbox` | Địa chỉ message trong broker mà consumer lắng nghe |
| **Listener endpoint ID** | `ordersListener` (nếu đặt `id`) | Dùng với `JmsListenerEndpointRegistry` để tìm/quản lý container của endpoint |

Một bean type đúng **nhưng tên khác**, ví dụ `myJmsFactory`, không tự động trở thành factory mặc định cho annotation bị bỏ trống `containerFactory` chỉ vì đó là bean duy nhất. Trong Spring JMS, nhánh lookup mặc định là **theo tên** trừ khi bạn cấu hình default riêng qua `JmsListenerConfigurer`. Đây cũng là lý do `@Primary` hoặc một `@Qualifier` dùng để inject field thông thường không thay thế quy tắc tên mặc định.

## 2. Cơ chế tìm factory diễn ra thế nào?

Spring kích hoạt hỗ trợ annotation bằng `@EnableJms` hoặc cơ chế auto-configuration của Spring Boot. Các phương thức có `@JmsListener` được phát hiện và đăng ký thành JMS listener endpoints.

~~~text
Spring ApplicationContext
   |
   +-- Bean: connectionFactory
   |      -> Jakarta JMS ConnectionFactory, kết nối đến broker
   |
   +-- Bean: jmsListenerContainerFactory
   |      -> DefaultJmsListenerContainerFactory
   |      -> cấu hình: connectionFactory, concurrency,
   |                    transaction, converter, error handling...
   |
   +-- Bean: orderConsumer
          |
          +-- @JmsListener(destination="orders.inbox")
                       |
                       v
          Spring tìm factory mặc định theo TÊN:
          "jmsListenerContainerFactory"
                       |
                       v
          factory.createListenerContainer(endpoint)
                       |
                       v
          JmsListenerEndpointRegistry
             -> quản lý một listener container cho endpoint
                       |
                       v
          Broker -> consumer -> orderConsumer.onOrder(...)
~~~

**Điểm dễ nhầm:** `JmsListenerContainerFactory` là **factory** để tạo container, không phải chính container đã chạy. Bean `JmsListenerEndpointRegistry` giữ các container được tạo cho annotated endpoints; chúng không nhất thiết xuất hiện như Spring beans độc lập có tên giống listener ID.

Khi chạy, đường xử lý thực tế gồm:
1. Spring tạo và cấu hình `ConnectionFactory` của JMS provider.
2. Spring nhận diện bean factory mặc định hoặc factory được chỉ định.
3. Hạ tầng annotation tạo listener endpoint từ method có `@JmsListener`.
4. Factory tạo một `MessageListenerContainer` cho endpoint.
5. Registry quản lý start/stop và tra cứu theo listener `id`.
6. Container nhận message từ broker và dispatch vào method Java.

`JmsListenerContainerFactory` **không liên quan** đến `JmsTemplate.convertAndSend` theo nghĩa chọn producer: `JmsTemplate` dùng `ConnectionFactory` để gửi, còn `@JmsListener` dùng listener container factory để nhận bất đồng bộ.

## 3. Quy tắc lựa chọn: ba đường đi

| Cách khai báo | Factory nào được chọn? | Khi nào dùng |
| --- | --- | --- |
| `@JmsListener(destination = "orders.inbox")` | Factory **mặc định**: thường bean `jmsListenerContainerFactory` | Phần lớn listener có chung policy |
| `@JmsListener(destination = "orders.inbox", containerFactory = "criticalJmsFactory")` | Bean có tên **`criticalJmsFactory`** | Listener cần policy khác về concurrency, transaction, converter... |
| `JmsListenerConfigurer.configureJmsListeners(registrar)` + `registrar.setContainerFactoryBeanName("businessFactory")` | `businessFactory` thành default cho các endpoints không chỉ định factory, nếu không bị factory cụ thể ghi đè | Muốn đổi default toàn ứng dụng thay vì đổi tên bean thành `jmsListenerContainerFactory` |

**Thứ tự ưu tiên thực dụng:** factory được chỉ định trực tiếp trên annotation → default được cấu hình rõ cho registrar → quy ước bean name `jmsListenerContainerFactory`.

Ví dụ hai listener trong cùng một class:

~~~java
// Snippet: đặt trong một bean Spring được component scan.
@JmsListener(destination = "orders.normal")
public void normal(String body) {
    // Dùng default factory.
}

@JmsListener(
    destination = "orders.urgent",
    containerFactory = "criticalJmsFactory")
public void urgent(String body) {
    // Dùng bean có tên criticalJmsFactory.
}
~~~

Đây là **snippet minh họa**, không phải một class Java độc lập. Một ứng dụng có cả hai listener phải có default factory phù hợp và bean `criticalJmsFactory` thực sự tồn tại. Đổi `containerFactory` trên annotation **không đổi queue**; tên destination vẫn đến từ `destination`.

## 4. Spring Framework thuần so với Spring Boot

### 4.1. Spring Framework thuần: quy ước tên không tự tạo bean

Khi cấu hình một ứng dụng Spring Framework không có Spring Boot auto-configuration, có thể dùng:

~~~java
package demo;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory defaultFactory(
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

**Điều kiện:** `ConnectionFactory` phải có bean riêng do ứng dụng cung cấp; đoạn này không tự cấu hình broker/credentials. Code minh họa đầy đủ về định nghĩa factory nhưng **không phải ứng dụng chạy một mình** khi chưa có provider JMS.

Ở đây tên phương thức Java là `defaultFactory`, **không phải `jmsListenerContainerFactory`**, nhưng nhờ `@Bean("jmsListenerContainerFactory")`, Spring tạo đúng **bean name** mà hạ tầng tìm kiếm.

Tương đương, nếu dùng:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    return factory;
}
~~~

thì tên bean mặc định lấy từ tên method `jmsListenerContainerFactory`. Đây cũng là mẫu thường xuất hiện trong Spring reference documentation.

**Sai lầm thường gặp:** viết:

~~~java
@Bean
public DefaultJmsListenerContainerFactory factory(
        ConnectionFactory connectionFactory) {
    DefaultJmsListenerContainerFactory result =
            new DefaultJmsListenerContainerFactory();
    result.setConnectionFactory(connectionFactory);
    return result;
}
~~~

Bean tên `factory` này **không có tên mặc định**. Nếu một listener không chỉ rõ `containerFactory = "factory"` và không có default khác được cấu hình, Spring có thể báo lỗi khi đăng ký endpoints. Không nên sửa bằng cách đặt `@Primary` rồi kỳ vọng lookup mặc định theo tên sẽ tự đổi.

### 4.2. Spring Boot: thường tự cung cấp factory mặc định

Với Spring Boot có starter/hạ tầng JMS và một `ConnectionFactory` hợp lệ, Boot có thể tự tạo `DefaultJmsListenerContainerFactory` mặc định để những `@JmsListener` không có `containerFactory` hoạt động mà không cần viết bean thủ công.

Ví dụ dependency dùng Spring Boot 3.3.5 và Artemis:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

Trong application có `@SpringBootApplication` và listener bean:

~~~java
@Component
public class MyListener {
    @JmsListener(destination = "demo.default.queue")
    public void receive(String payload) {
        System.out.println(payload);
    }
}
~~~

Với điều kiện auto-configuration phù hợp, Boot cung cấp bean `jmsListenerContainerFactory`. Khi đó chỉ cần cấu hình Artemis `ConnectionFactory` và queue.

**Giới hạn quan trọng:** không được kết luận “Spring Boot **luôn** tạo bean đó”. Khi thiếu starter/JMS API/provider/ConnectionFactory, auto-configuration bị loại trừ, profile không phù hợp, hoặc có custom `JmsListenerContainerFactory` khiến điều kiện “missing bean” không còn thỏa, bean default có thể không xuất hiện. Spring Boot documentation mô tả rằng **nếu chưa định nghĩa `JmsListenerContainerFactory`, default factory sẽ được auto-configure**; do vậy tạo một factory khác tên mà không kiểm tra điều kiện auto-config cũng có thể làm listener mặc định hỏng.

Khi dùng Boot, cấu hình factory custom nên được tạo bằng `DefaultJmsListenerContainerFactoryConfigurer` nếu muốn giữ hành vi mặc định đã được Boot áp dụng (transaction/converter/resolver/recovery). Không nên cấu hình thủ công một factory mới rồi **giả định** nó giống 100% factory auto-configured.

### 4.3. Hai nhóm cấu hình độc lập

- **Producer:** `JmsTemplate` / `JmsMessagingTemplate` gửi message, được cấu hình thông qua `ConnectionFactory` và các thiết lập riêng của template.
- **Consumer:** `@JmsListener` / `DefaultMessageListenerContainer` nhận message, chịu ảnh hưởng từ `JmsListenerContainerFactory`.

Cả hai có thể dùng cùng loại `ConnectionFactory` từ nhà cung cấp JMS, nhưng không có chuyện đổi tên `jmsListenerContainerFactory` làm mọi producer tự động dùng listener factory.

## 5. Ví dụ chạy được: chứng minh tên default ngay trong Spring Boot

Ví dụ này dùng **Java 17 + Spring Boot 3.3.5 + ActiveMQ Artemis**. Ta chủ động **không định nghĩa bất kỳ bean `JmsListenerContainerFactory` nào** để Spring Boot có thể tạo factory mặc định. Chương trình kiểm tra sự hiện diện của bean tên `jmsListenerContainerFactory`, dùng `@JmsListener` không khai báo `containerFactory` và gửi một String message vào queue thử.

### 5.1. Điều kiện cần

- JDK 17+; Gradle đã cài hoặc có Gradle wrapper.
- Broker ActiveMQ Artemis ở `tcp://localhost:61616` và tài khoản `demo/demo` cho **môi trường học cách ly**.
- Queue **anycast** `demo.default.factory` đã được provision hoặc broker test cho phép auto-create queue. Không dùng queue sản xuất.
- Quyền send và consume cho user của demo; đảm bảo không có consumer khác tranh message trên queue test.
- Nếu cài broker bằng Docker, kiểm tra cổng 61616 được publish và broker đã sẵn sàng. Username/password `demo/demo` là ví dụ do người học tự cấu hình, không phải mặc định của tất cả image.

### 5.2. Cấu trúc thư mục

~~~text
jms-default-factory/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── DefaultFactoryApplication.java
    │   └── DemoListener.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-default-factory'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "demo"
    password: "demo"
~~~

`mode: native` giúp không vô tình nhắm vào broker nhúng. Khi dùng credentials thực, cung cấp qua `SPRING_ARTEMIS_USER`/`SPRING_ARTEMIS_PASSWORD` hoặc secret management, không commit secret vào repo.

### 5.3. Application tạo message và kiểm tra registry

`src/main/java/demo/DefaultFactoryApplication.java`:

~~~java
package demo;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.JmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class DefaultFactoryApplication {

    private static final String QUEUE = "demo.default.factory";

    public static void main(String[] args) {
        SpringApplication.run(DefaultFactoryApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(
            ApplicationContext applicationContext,
            JmsTemplate jmsTemplate,
            JmsListenerEndpointRegistry registry,
            DemoListener demoListener) {

        return args -> {
            Object bean = applicationContext.getBean(
                    "jmsListenerContainerFactory");

            if (!(bean instanceof JmsListenerContainerFactory<?>)) {
                throw new IllegalStateException(
                        "Unexpected default factory bean type");
            }
            if (registry.getListenerContainer("default-demo-listener")
                    == null) {
                throw new IllegalStateException(
                        "Listener endpoint not registered");
            }

            String runId = UUID.randomUUID().toString();
            demoListener.expect(runId);

            jmsTemplate.convertAndSend(QUEUE, "probe:" + runId);

            if (!demoListener.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "No matching message received within 10s");
            }

            System.out.println(
                    "DEFAULT_FACTORY_BEAN=jmsListenerContainerFactory");
            System.out.println(
                    "LISTENER_ID=default-demo-listener");
            System.out.println("LISTENER_RECEIVED=true");
        };
    }
}
~~~

`src/main/java/demo/DemoListener.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class DemoListener {

    private final CountDownLatch received = new CountDownLatch(1);
    private volatile String expected;

    public void expect(String runId) {
        expected = "probe:" + runId;
    }

    @JmsListener(
            id = "default-demo-listener",
            destination = "demo.default.factory")
    public void onMessage(String body) {
        String expectedNow = expected;
        if (expectedNow != null && expectedNow.equals(body)) {
            received.countDown();
        }
    }

    public boolean await(long time, TimeUnit unit)
            throws InterruptedException {
        return received.await(time, unit);
    }
}
~~~

**Những điểm quyết định giúp phép thử có ý nghĩa:**

1. Chương trình **không có `@Bean jmsListenerContainerFactory`**; nếu Boot đủ điều kiện auto-configure, bean đó phải tồn tại.
2. `@EnableJms` được ghi rõ để minh bạch việc kích hoạt xử lý `@JmsListener`, dù trong cấu hình Boot thông thường có thể đã được auto-enable.
3. `ApplicationRunner` chỉ chạy sau khi Spring context khởi tạo. Nó kiểm tra bean **theo tên**, rồi kiểm tra `JmsListenerEndpointRegistry` theo `id` của annotation — hai phép kiểm khác nhau.
4. `DemoListener` không đặt `containerFactory`. Do đó nó dùng mặc định đã xác minh.
5. `runId` tạo riêng mỗi lần chạy, body `probe:<UUID>` giúp listener chỉ count down khi nhận đúng message của đợt thử.
6. `CountDownLatch` giúp `ApplicationRunner` chờ có giới hạn 10 giây để quan sát message đã đến callback; không phải một lệnh `JmsTemplate.receive` chặn trong HTTP.
7. `@JmsListener` dùng listener worker/background thread do container quản lý. Đây là **nhận bất đồng bộ** ở tầng application code.
8. Queue thử phải riêng vì các message cũ hoặc consumer khác có thể làm nhiễu kết quả. Listener demo không dùng JMS selector nên có thể tiêu thụ message cũ trong queue test dù không làm latch hoàn thành.
9. Không có database hay nghiệp vụ bên ngoài, nên output chỉ chứng minh bean/factory selection và một message được xử lý trong demo, **không** chứng minh end-to-end exactly-once.
10. Không in UUID trong output chuẩn để giữ các dòng kết quả ổn định qua mỗi lần chạy.

### 5.4. Chạy và kết quả

Tại root project với broker đã sẵn sàng:

~~~bash
gradle bootRun
~~~

Khi đủ điều kiện, các dòng **do ứng dụng in ra** sẽ là:

~~~text
DEFAULT_FACTORY_BEAN=jmsListenerContainerFactory
LISTENER_ID=default-demo-listener
LISTENER_RECEIVED=true
~~~

Log của Spring Boot, broker và listener container có thể xuất hiện thêm, không có yêu cầu thứ tự so với log hệ thống. Nếu bean mặc định không tồn tại, chương trình thất bại ở `getBean(...)` thay vì in PASS. Nếu broker hoặc ACL sai, message không được nhận và chương trình báo lỗi timeout/lỗi JMS. Mẫu **không tuyên bố đã chạy thực tế** ở bất kỳ môi trường cụ thể nào.

Vì listener container là thành phần sống lâu dài, ứng dụng có thể vẫn giữ process chạy sau khi các dòng PASS xuất hiện; dừng bằng `Ctrl+C` khi kết thúc demo.

### 5.5. Khi nào dùng ID của listener?

Trong code `@JmsListener(id = "default-demo-listener")`:
- `id` là tên endpoint/container theo registry;
- `destination` là queue;
- `containerFactory` nếu khai báo sẽ là **tên bean factory**.

`registry.getListenerContainer("default-demo-listener")` tìm container cho endpoint, **không** tìm bean `jmsListenerContainerFactory`. Nếu không đặt `id`, Spring sinh ID tự động; khi muốn start/stop riêng một listener hoặc kiểm thử registry, nên đặt ID ổn định.

## 6. Định nghĩa factory mặc định thủ công với tên chính xác

Nếu không muốn dùng factory auto-configured, tạo bean rõ ràng theo tên quy ước. Trong Spring Boot 3.x, nên dùng `DefaultJmsListenerContainerFactoryConfigurer` để thừa hưởng cấu hình thường áp dụng của Boot, sau đó ghi đè thông số cần thiết.

Ví dụ **snippet thay thế**, không thêm cùng lúc vào demo mục 5 nếu bạn đang chứng minh Boot tự tạo:

~~~java
package demo;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class FactoryConfiguration {

    @Bean("jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory createDefaultFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

Tên method `createDefaultFactory` **khác** tên bean nhưng không sao vì `@Bean("jmsListenerContainerFactory")` đặt tên chính xác. Với Spring Boot 3.3, import configurer là `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`. Ở Spring Boot 4, package tự động cấu hình đã đổi sang `org.springframework.boot.jms.autoconfigure...`, nên cần đổi imports khi nâng major version.

`ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory)` cho listener có cơ hội dùng native connection factory thay vì một cached wrapper do Boot tạo; điều này phù hợp cách Boot auto-configure container trong các phiên bản có helper ấy. Không unwrap mọi wrapper/pool một cách tùy tiện: hãy kiểm tra khả năng tương thích và hạ tầng transaction của broker.

**Lợi ích của configurer:** nó áp dụng những mặc định của Spring Boot phù hợp với `spring.jms.listener.*`, converter, transaction manager và các bean JMS liên quan (khi có và khi điều kiện thỏa). Nếu tự gọi `factory.setConnectionFactory(...)` mà bỏ qua configurer, bạn có thể làm mất một số behavior mặc định của Boot.

Không đặt concurrency tùy ý lên mức hàng trăm chỉ vì muốn xử lý nhanh hơn: mỗi consumer có tài nguyên session/connection, và database downstream có giới hạn riêng.

## 7. Muốn dùng hai factory khác nhau thì làm sao?

Giả sử message thường và message ưu tiên cao cần cấu hình listener khác nhau. Ta tạo **hai beans với hai tên rõ ràng**, đồng thời xác định chính xác listener dùng bean nào.

~~~java
// Snippet @Configuration trong Spring Boot 3.x.
// Cần import ConnectionFactory, @Bean, @Configuration,
// DefaultJmsListenerContainerFactory, và Boot configurer/unwrapper.
@Configuration
public class MultiListenerFactoryConfig {

    @Bean("jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory defaultFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setConcurrency("1-2");
        return factory;
    }

    @Bean("criticalJmsFactory")
    DefaultJmsListenerContainerFactory criticalFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setConcurrency("2-4");
        return factory;
    }
}
~~~

Đây là snippet minh họa; nếu tạo file thật, phải bổ sung các imports tương ứng như mục 6. Trong ví dụ, hai factory được đặt tên tường minh để không phụ thuộc vào chuyện Spring Boot có tiếp tục auto-configure default khi custom factory hiện diện hay không.

Listener:

~~~java
// Snippet trong một @Component đã được Spring phát hiện.
@JmsListener(destination = "orders.normal")
public void normal(String body) {
    // Bean jmsListenerContainerFactory.
}

@JmsListener(
        destination = "orders.critical",
        containerFactory = "criticalJmsFactory")
public void critical(String body) {
    // Bean criticalJmsFactory.
}
~~~

**Kết luận:** `containerFactory = "criticalJmsFactory"` là **String bean name** của factory, không phải tên class. Nó cũng không thay đổi tính chất của destination: nếu cần queue riêng phải khai báo riêng `destination`. Một factory có thể được dùng để tạo **nhiều containers** cho nhiều listener methods.

**Quan sát về tài nguyên:** concurrency `"2-4"` là mức config cho listener containers hỗ trợ scale; nó không bảo đảm broker luôn có bốn consumer hoạt động, không bảo đảm thứ tự message, và không phải SLA. Cần benchmark, kiểm tra JMS prefetch, transaction và mức tải DB.

## 8. Đổi factory mặc định bằng `JmsListenerConfigurer`

Nếu muốn các `@JmsListener` **không ghi `containerFactory`** mặc định sử dụng một bean tên khác `businessFactory`, Spring cung cấp `org.springframework.jms.annotation.JmsListenerConfigurer`. Nó cho phép tùy chỉnh `JmsListenerEndpointRegistrar`:

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;

@Configuration
@EnableJms
public class ListenerDefaultSelection
        implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        registrar.setContainerFactoryBeanName("businessFactory");
    }
}
~~~

**Yêu cầu:** một bean `JmsListenerContainerFactory<?>` có tên `businessFactory` **phải tồn tại** và đã được cấu hình với `ConnectionFactory`, transaction, converter và các chính sách phù hợp. Nếu không, Spring không thể tạo container cho endpoint không có factory riêng.

Bạn cũng có thể gọi `registrar.setContainerFactory(instance)` để thiết lập factory trực tiếp. Chỉ định `@JmsListener(containerFactory = "otherFactory")` ở một method vẫn cho phép chọn factory riêng cho method ấy.

**Khi nào nên dùng `JmsListenerConfigurer`?** Khi bạn đang xây framework tích hợp trong nội bộ ứng dụng, muốn thay đổi default theo policy thống nhất hoặc đăng ký endpoint programmatically. Với ứng dụng đơn giản, tên bean mặc định `jmsListenerContainerFactory` thường dễ hiểu, dễ debug và ít cấu hình hơn.

## 9. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Startup báo không tìm thấy `jmsListenerContainerFactory` | Không có bean mang tên đó, listener không đặt `containerFactory` và không có registrar default khác | Tạo `@Bean("jmsListenerContainerFactory")` hoặc chỉ định factory rõ |
| Có bean `myFactory` nhưng `@JmsListener` mặc định lỗi | Bean name khác; Boot có thể không tạo default do đã có factory | Đổi tên bean hoặc viết `containerFactory = "myFactory"` |
| Đánh dấu `@Primary` nhưng vẫn không tìm thấy default | Fallback mặc định lookup theo tên, không phải chọn primary bean | Đặt đúng bean name hoặc `JmsListenerConfigurer` |
| `@JmsListener(containerFactory = "criticalFactory")` lỗi | Bean `criticalFactory` thiếu hoặc không phải `JmsListenerContainerFactory<?>` | Kiểm tra exact bean name và type |
| Có `jmsListenerContainerFactory` nhưng không có message | Broker/destination/ACL/selector/autoStartup/transaction vấn đề, không nhất thiết do tên bean | Xác minh queue, quyền, registry, broker log |
| Chỉ thêm `spring-jms` nhưng listener không được phát hiện | Chưa bật hạ tầng annotation (`@EnableJms` hoặc Boot auto setup) hoặc class không là Spring bean | Bật annotation support và component scan |
| Tạo factory thủ công rồi mất transaction behavior | Không dùng Boot configurer, không cấu hình transacted session | Dùng `DefaultJmsListenerContainerFactoryConfigurer` hoặc cấu hình rõ |
| Bean listener tồn tại nhưng container chưa start | `autoStartup=false`, registry bị stop, context đang shutdown | Kiểm tra `JmsListenerEndpointRegistry`, startup policy |
| Đổi tên method `@Bean` tưởng không ảnh hưởng | Bean name mặc định lấy từ method name khi không chỉ định name | Dùng `@Bean("jmsListenerContainerFactory")` để ổn định |
| Có bean factory tên đúng nhưng chỉ listener khác chạy | Một số endpoints đặt `containerFactory` khác; selector/concurrency khác | Đọc từng annotation và factory tương ứng |
| Lỗi deserialize payload sau khi nhận | Factory dùng converter không tương thích body DTO | Cấu hình MessageConverter và schema riêng |
| Chuyển Boot 3 sang Boot 4 bị lỗi import configurer | Package auto-config của Boot 4 đổi | Cập nhật import, dependency BOM và kiểm thử |
| `registry.getListenerContainer("x")` trả null | `id` sai hoặc endpoint không được đăng ký | Đặt `@JmsListener(id="x", ...)` và kiểm tra annotation scan |

**Đừng chẩn đoán bằng cách đoán exception class cố định.** Spring Framework/Boot có thể báo lỗi lúc cấu hình endpoint hoặc refresh context với exception được wrap. Hãy tìm thông tin “bean name”, “container factory”, “listener endpoint” trong chuỗi nguyên nhân, không gán mọi startup error thành lỗi broker.

## 10. Debug cụ thể trong ApplicationContext

Khi nghi ngờ thiếu factory, nên kiểm tra **tên và type** theo đúng bean:

~~~java
// Snippet: ApplicationContext được inject vào một Spring bean.
boolean exists =
        applicationContext.containsBean(
                "jmsListenerContainerFactory");

String[] factoryNames =
        applicationContext.getBeanNamesForType(
                JmsListenerContainerFactory.class);

System.out.println("DEFAULT_EXISTS=" + exists);
System.out.println("FACTORY_NAMES="
        + java.util.Arrays.toString(factoryNames));
~~~

Cần imports `org.springframework.context.ApplicationContext`, `org.springframework.jms.config.JmsListenerContainerFactory` và `java.util.Arrays` (hoặc dùng fully qualified như trên). Đây là **snippet**, không phải file Java độc lập.

**Cách đọc kết quả:**

| `DEFAULT_EXISTS` | Danh sách `FACTORY_NAMES` | Cách hiểu |
| --- | --- | --- |
| `true` | Có `jmsListenerContainerFactory` | Bean mặc định tồn tại, nhưng phải kiểm tra tiếp cấu hình/registry |
| `false` | Chỉ có `myFactory` | Có custom factory, thiếu bean theo tên default; cần đổi mapping |
| `false` | Rỗng | Chưa có factory bean, có thể thiếu JMS auto-configuration/dependency |
| `true` | Có nhiều factory | Các listener không khai báo factory thường dùng default; listener có `containerFactory` dùng tên chỉ định |

**Chú ý:** `containsBean` chỉ xác minh có bean cùng tên; để bảo đảm type, dùng `getBean(name, JmsListenerContainerFactory.class)` hoặc kiểm tra `instanceof`. Có bean sai kiểu trùng tên cũng gây lỗi.

### 10.1. Kiểm tra listener endpoint đã được tạo

~~~java
// Snippet: registry là JmsListenerEndpointRegistry đã inject.
// Annotation của method nên đặt id="ordersListener".
var container = registry.getListenerContainer("ordersListener");

if (container == null) {
    throw new IllegalStateException("Listener is not registered");
}
System.out.println("LISTENER_RUNNING=" + container.isRunning());
~~~

Cần bean `JmsListenerEndpointRegistry` từ JMS annotation infrastructure. `container.isRunning()` báo trạng thái lifecycle, **không** khẳng định broker đang giao message hoặc handler đã xử lý nghiệp vụ thành công. Khi cần xem số containers, dùng `registry.getListenerContainers()` hoặc `getListenerContainerIds()` theo phiên bản Spring.

### 10.2. Kiểm tra auto-configuration của Boot

Khi ứng dụng Boot không tạo bean như mong đợi:
1. Kiểm tra dependency thực tế có `spring-jms` và một client/broker starter hay không.
2. Xác minh `ConnectionFactory` bean đã được tạo từ đúng broker configuration.
3. Xem `@EnableJms` hoặc hạ tầng JMS annotation đã được kích hoạt chưa.
4. Kiểm tra custom `JmsListenerContainerFactory` trong toàn bộ application context: **có bean type khác tên có thể làm Boot back off**.
5. Kiểm tra `@Profile`, `@ConditionalOn...`, component scan, exclusions và application configuration.
6. Dùng Spring Boot condition evaluation report (ví dụ chạy với `--debug`) để biết auto-configuration nào match/không match.
7. Kiểm tra registry xem endpoint có đăng ký và container có chạy không.

Không sửa mặc định của Spring bằng cách đặt bean tên `jmsListenerContainerFactory` nhưng bỏ `setConnectionFactory` hoặc bỏ configurer: đặt đúng tên chỉ là **một điều kiện**, factory vẫn cần cấu hình đúng.

## 11. Ưu tiên dùng Spring Boot configurer khi custom factory

Đối với Spring Boot 3.x, `DefaultJmsListenerContainerFactoryConfigurer` giúp factory custom dùng những setting mà Boot có thể áp dụng tự động:

- `ConnectionFactory` (thường là native underlying connection factory cho listener);
- `DestinationResolver` nếu được cung cấp;
- `MessageConverter` nếu có bean phù hợp;
- `ExceptionListener` hoặc các cấu hình lỗi/recovery liên quan khi được Boot hỗ trợ;
- Các cài đặt `spring.jms.listener.*` và transaction strategy theo Boot version;
- Sau đó, bạn có thể tinh chỉnh concurrency, receive timeout, backoff hoặc custom error handler.

**Không suy ra** rằng có bean tên default thì luôn transacted; đó còn phụ thuộc cách factory được tạo và cấu hình. Factory tự tạo không dùng configurer và chỉ gọi `setConnectionFactory` sẽ có những default của Spring Framework, có thể khác default có transaction của Spring Boot.

Khi dùng local JMS transaction (ví dụ `sessionTransacted=true`), listener ném exception có thể dẫn đến rollback/redelivery theo policy. Nó **không tự tạo transaction phân tán với database**. Những business handlers quan trọng cần idempotency và chiến lược retry/DLQ riêng.

## 12. Câu hỏi thực tế: đổi tên factory có làm đổi hành vi message không?

Ví dụ:

~~~java
// Cách 1: @Bean("jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory createFactory(...) { ... }

// Cách 2: @Bean("myFactory")
DefaultJmsListenerContainerFactory createFactory(...) { ... }
~~~

Hai factory có thể cùng Java class và cùng cấu hình, nhưng **annotation không chỉ định factory chỉ tự nhận ra Cách 1** theo quy ước tên. Nếu một method có `containerFactory = "myFactory"`, nó chọn Cách 2.

Tên bean chỉ là **cơ chế chọn cấu hình container**, không quyết định:
- Message có vào đúng queue hay không (do destination/broker routing).
- User có quyền consume hay không (do JMS provider authorization).
- Payload có chuyển đúng DTO hay không (do MessageConverter/config).
- Message có được xử lý exactly-once trên database không (do transaction/idempotency).
- Một consumer có xử lý nhiều message song song hay không (do concurrency và broker/runtime).

Vì vậy, khi gặp lỗi “listener không chạy”, cần xác định hai bước riêng: **factory đã được tìm thấy và container đã được tạo chưa?** Sau đó mới xem **container có start, kết nối broker và nhận message đúng destination không?**

## 13. Các tình huống kiểm thử nên có

| Test | Cấu hình | Kết quả kỳ vọng |
| --- | --- | --- |
| Default bean được Boot tạo | Boot JMS starter + ConnectionFactory, không tự khai factory | `ApplicationContext` có `jmsListenerContainerFactory` khi auto-config điều kiện đúng |
| Listener không ghi `containerFactory` | Có bean default tên chuẩn | Endpoint đăng ký và nhận message trên queue thử |
| Bean khác tên nhưng listener không khai factory | Chỉ có `myFactory`, không có default khác | Thiếu default; startup/registration có thể lỗi |
| Listener ghi `containerFactory = "myFactory"` | Có bean `myFactory` | Endpoint dùng đúng factory được nêu |
| Factory bean sai type | Tên `jmsListenerContainerFactory` nhưng class không implement factory interface | Lỗi cấu hình, không silently chấp nhận |
| Factory chưa có `ConnectionFactory` | Tên bean đúng nhưng thiếu cấu hình kết nối | Container không khởi tạo/hoạt động bình thường |
| Có hai factories | Default và critical khác tên | Endpoint chọn theo annotation hoặc default |
| Dùng `JmsListenerConfigurer` | Registrar chọn `businessFactory` làm default | Endpoint không ghi factory dùng default mới |
| Listener `autoStartup=false` | Factory tồn tại, endpoint đã đăng ký | Registry thấy container nhưng `isRunning()` false |
| Wrong destination / ACL | Factory có, container có | Không nhận message hoặc lỗi broker; không suy là sai tên |
| Retry/error handling | Listener ném exception, policy transacted/recovery phù hợp | Xem rollback/redelivery theo provider và cấu hình |
| Boot upgrade | Thay Boot major, giữ contract bean names | Compile imports, auto-config và listener registration test lại |

### 13.1. Vì sao unit test chỉ nhìn type là chưa đủ?

Một test `context.getBean(DefaultJmsListenerContainerFactory.class)` thành công có thể chưa chứng minh bean có tên đúng. Để kiểm tra quy tắc default, cần assert:

~~~java
// Snippet trong integration test dùng Spring context.
assert context.containsBean("jmsListenerContainerFactory");
assert context.getBean("jmsListenerContainerFactory")
        instanceof JmsListenerContainerFactory;
~~~

Đây là cú pháp minh họa cho kiểm tra context; dùng `Assertions.assertTrue(...)`/AssertJ tùy test framework thực tế. Sau đó kiểm tra `JmsListenerEndpointRegistry` có listener ID và gửi message thử qua broker cô lập để xác minh đường runtime. **Không** gọi trực tiếp method được đánh dấu `@JmsListener` để “chứng minh” containerFactory hoạt động: gọi Java method bỏ qua toàn bộ JMS infrastructure.

### 13.2. Không thao tác trên queue sản xuất chỉ để kiểm tra tên bean

Để kiểm tra bean selection, không cần consume message thật. Dùng queue test, dữ liệu giả và ID riêng. Nếu listener chạy trên queue production, khởi động Spring context chỉ để test có thể khiến nó nhận/ACK message thật. Dùng test profile và tắt autoStartup ở môi trường chỉ inspect context nếu cần, hoặc tách cấu hình test khỏi business endpoint.

## 14. Những câu hỏi hay bị hỏi khi phỏng vấn hoặc review code

**Hỏi: Tên mặc định là gì?** — `jmsListenerContainerFactory`, đúng từng chữ hoa/thường theo bean name.

**Hỏi: Đây là class hay bean?** — Đây là **tên bean**; class thường dùng là `DefaultJmsListenerContainerFactory` và interface là `JmsListenerContainerFactory`.

**Hỏi: Nếu không định nghĩa bean này thì sao?** — Spring Framework thuần không tự đảm bảo có bean. Spring Boot có thể auto-configure khi đầy đủ điều kiện; nếu thiếu, listener không chỉ định factory có thể không đăng ký được.

**Hỏi: Có thể đặt tên khác không?** — Có. Dùng `@JmsListener(containerFactory = "otherFactory")` hoặc cấu hình registrar default qua `JmsListenerConfigurer`.

**Hỏi: Vì sao `@Primary` không đủ?** — Lookup default dựa vào **bean name**, không phải chọn bean được ưu tiên trong autowiring theo type.

**Hỏi: `@JmsListener(id = "foo")` có thay factory không?** — Không. `id` dùng định danh container endpoint cho registry/management.

**Hỏi: `@JmsListener(destination = "foo")` và `containerFactory = "foo"` có thể là cùng String không?** — Có thể trùng chữ tình cờ, nhưng **hai ý nghĩa khác nhau**: một là JMS destination, một là Spring factory bean name.

**Hỏi: Có cần `@EnableJms` không?** — Trong Spring Framework thuần, đó là cách tiêu chuẩn kích hoạt processing annotation. Spring Boot có thể cấu hình tự động hạ tầng listener; việc đặt rõ `@EnableJms` vẫn có ích trong demo để biểu thị ý định. Kiểm tra thực tế context thay vì phỏng đoán.

**Hỏi: Factory có phải là consumer thread không?** — Không. Factory tạo listener container; container mới quản lý threads, connections, sessions, polling/dispatch tùy implementation.

**Hỏi: Có nên tạo nhiều factory không?** — Khi thực sự có nhu cầu cấu hình policy khác nhau, ví dụ destination, concurrency, converter, transaction/recovery. Nếu mọi listener tương đương, một factory default giúp đơn giản hóa.

## 15. Checklist khi dùng `@JmsListener` trong dự án

- [ ] Có dependency JMS phù hợp với Spring Framework/Boot đang dùng; Spring 6/Boot 3 sử dụng `jakarta.jms`.
- [ ] Có `ConnectionFactory` hoạt động với broker và credentials đúng.
- [ ] Listener class được component scan/đăng ký thành Spring bean.
- [ ] Hạ tầng JMS annotation được bật qua `@EnableJms` hoặc Boot auto-configuration phù hợp.
- [ ] Nếu bỏ trống `containerFactory`, bean default `jmsListenerContainerFactory` tồn tại hoặc registrar default khác được cấu hình rõ.
- [ ] Nếu khai báo `containerFactory = "name"`, đúng bean name và type `JmsListenerContainerFactory<?>`.
- [ ] Khi tạo factory thủ công trong Boot, cân nhắc `DefaultJmsListenerContainerFactoryConfigurer`.
- [ ] Factory có connection factory, transaction policy, converter, concurrency/recovery phù hợp.
- [ ] `destination` là tên queue/topic thật; đúng quyền consume, routing type và selector.
- [ ] Listener có `id` ổn định nếu cần quản lý qua registry.
- [ ] Đã xác minh container được đăng ký, `isRunning()` phù hợp và broker thực sự giao message.
- [ ] Có integration test trên queue riêng, không ACK message production.
- [ ] Có retry/DLQ/idempotency nếu xử lý message liên quan dữ liệu nghiệp vụ.
- [ ] Không nhầm tên bean với JMS queue hay tên của `ConnectionFactory`.

### Câu hỏi tự kiểm tra

1. Với `@JmsListener(destination = "orders")`, Spring tìm factory mặc định tên gì?
2. Vì sao `@Bean public DefaultJmsListenerContainerFactory myFactory(...)` chưa chắc phục vụ listener không ghi `containerFactory`?
3. Làm thế nào đặt bean name mặc định dù phương thức Java tên `createDefaultFactory`?
4. Khác biệt giữa `@JmsListener(id = "ordersListener")`, `destination = "orders"` và `containerFactory = "factoryA"` là gì?
5. Spring Boot 3 có thể tự tạo bean default trong điều kiện nào? Nếu bạn tự định nghĩa factory custom khác tên, cần kiểm tra gì?
6. Khi nào nên sử dụng `JmsListenerConfigurer` thay vì `@Bean("jmsListenerContainerFactory")`?
7. Nếu factory được tìm đúng nhưng message không đến, cần kiểm tra các lớp nào tiếp theo?
8. Vì sao registry `getListenerContainer("ordersListener")` không có nghĩa đang truy cập một Spring bean tên `ordersListener`?
9. Vì sao cấu hình `@Primary` không thay tên default lookup?
10. Nếu cần factory riêng cho một queue có quy tắc transaction khác, nên khai báo annotation và bean thế nào?

**Ghi nhớ:** **`jmsListenerContainerFactory` là tên bean mặc định mà `@JmsListener` sử dụng khi không chỉ định factory**. Với Spring Framework thuần, bạn cần cung cấp/configure factory; Spring Boot có thể auto-configure khi đáp ứng điều kiện. Đổi tên bean phải đi kèm đổi `containerFactory` trên annotation hoặc cấu hình default registrar. Đặt đúng tên giúp listener **tìm được factory**, nhưng để nhận message thành công còn cần broker, destination, permissions, lifecycle, converter và transaction phù hợp.

## Tài liệu tham khảo

1. Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
2. Spring Framework 6.1 — `@JmsListener` API (containerFactory default): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/annotation/JmsListener.html
3. Spring Framework 6.1 — `JmsListenerEndpointRegistrar` API: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistrar.html
4. Spring Framework — Using Spring JMS (listener containers, transactions): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
5. Spring Boot 3.x — JMS integration and listener factory auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
6. Spring Boot 3.x — `DefaultJmsListenerContainerFactoryConfigurer`: https://docs.spring.io/spring-boot/docs/3.0.8/api/org/springframework/boot/autoconfigure/jms/DefaultJmsListenerContainerFactoryConfigurer.html
7. Jakarta Messaging 3.1 Specification — JMS messaging and consumers: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
