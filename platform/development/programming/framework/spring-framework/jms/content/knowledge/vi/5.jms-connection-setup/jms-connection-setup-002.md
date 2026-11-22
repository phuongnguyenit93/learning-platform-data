# Khởi tạo ConnectionFactory bằng cấu hình Java

## 1. Mục tiêu và phạm vi

Trong Spring Framework JMS, `ConnectionFactory` là điểm truy cập để tạo kết nối tới **JMS broker**. Bài này hướng dẫn **khởi tạo và đăng ký `ConnectionFactory` bằng JavaConfig** — các class `@Configuration` và method `@Bean` — rồi inject bean đó vào `JmsTemplate`, listener và các thành phần khác. Ví dụ dùng Java 17+, Spring Boot 3.5.x (dựa trên Spring Framework 6.x) và Apache ActiveMQ Artemis; nguyên tắc về bean, injection và resource lifecycle vẫn áp dụng khi dùng Spring Framework thuần.

Sau bài này, bạn sẽ biết:
- Phân biệt interface chuẩn `jakarta.jms.ConnectionFactory` với implementation do broker cung cấp và wrapper của Spring.
- Viết `@Bean` tạo connection factory bằng URL, thông tin đăng nhập lấy từ cấu hình thay vì hardcode.
- Tách bean factory cho tác vụ gửi (có cache) và nhận (listener container tự quản lý tài nguyên), dùng `@Qualifier` để tránh nhầm bean.
- Chạy một ví dụ gửi/nhận hoàn chỉnh, hiểu thời điểm kết nối thực sự được mở, đóng khi ứng dụng dừng và cách kiểm tra lỗi.
- Nhận biết khác biệt giữa JavaConfig thủ công và Spring Boot auto-configuration, cũng như giới hạn transaction, pooling, bảo mật và reconnect.

**Phạm vi:** khởi tạo và nối dây `ConnectionFactory` trong ứng dụng Spring JMS. Đây chưa phải hướng dẫn cài đặt broker; một broker Artemis đang chạy là điều kiện của ví dụ tích hợp.

## 2. ConnectionFactory là gì? Vì sao có nhiều kiểu?

`jakarta.jms.ConnectionFactory` là **interface thuộc Jakarta Messaging**. Nó mô tả khả năng tạo `Connection` hoặc `JMSContext`; interface không quy định địa chỉ broker, giao thức hay cách quản lý socket. Các thông số ấy thuộc implementation của nhà cung cấp.

```text
@Configuration / @Bean (Spring quản lý vòng đời)
           |
           v
ActiveMQConnectionFactory       <-- implementation của Artemis
           |
           +--> Connection -> Session -> MessageProducer / MessageConsumer
           |
           +--> CachingConnectionFactory (wrapper do Spring cung cấp)
                           |
                           v
                       JmsTemplate
           |
           +--------------------> DefaultJmsListenerContainerFactory
                                        |
                                        v
                                    @JmsListener
```

| Thành phần | Package / vai trò | Cách hiểu |
| --- | --- | --- |
| `ConnectionFactory` | `jakarta.jms.ConnectionFactory` | Hợp đồng JMS độc lập nhà cung cấp. |
| `ActiveMQConnectionFactory` (Artemis) | `org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory` | Implementation biết URL/transport, tài khoản và cách nói chuyện với broker Artemis. |
| `CachingConnectionFactory` | `org.springframework.jms.connection.CachingConnectionFactory` | Wrapper Spring giữ lại connection và cache session/producer/consumer khi phù hợp; nó cũng implements `ConnectionFactory`. |
| `JmsTemplate` | `org.springframework.jms.core.JmsTemplate` | Thực hiện gửi/nhận đồng bộ, mượn và trả tài nguyên qua `ConnectionFactory` được cấu hình. |
| `DefaultJmsListenerContainerFactory` | `org.springframework.jms.config.DefaultJmsListenerContainerFactory` | Factory của listener container cho `@JmsListener`, tạo consumer, quản lý concurrency và recovery. |

**Không nhầm ActiveMQ Artemis và ActiveMQ Classic:** dù có tên gần giống nhau, package và cấu hình connection factory khác nhau. Ví dụ trong bài sử dụng **Artemis** (`org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory`), không dùng `org.apache.activemq.ActiveMQConnectionFactory` của ActiveMQ Classic.

### JavaConfig thực sự tạo gì?

`@Bean` tạo **đối tượng cấu hình dùng chung trong ApplicationContext** theo scope mặc định là singleton. Khởi tạo bean provider factory không nhất thiết đã tạo một kết nối TCP thành công. Thường chỉ khi `JmsTemplate` gửi/nhận hoặc listener bắt đầu hoạt động thì framework/provider mới mở connection thực sự. Vì thế “Spring khởi động không lỗi bean” chưa phải bằng chứng broker sẵn sàng.

Đồng thời, **singleton `ConnectionFactory` không có nghĩa toàn hệ thống chỉ có một JMS `Connection`**: raw provider factory có thể sinh nhiều connection; wrapper `CachingConnectionFactory` có chính sách chia sẻ/cache riêng. Số connection vật lý phụ thuộc topology và cấu hình.

## 3. Chọn dependency, phiên bản và namespace

Ví dụ chạy được bằng Java 17+ và Maven sử dụng **Spring Boot 3.5.8** để quản lý phiên bản tương thích của Spring Framework, Jakarta JMS và Artemis client. Trong dự án dùng Spring Framework trực tiếp, tối thiểu cần `spring-context`, `spring-jms`, `spring-tx` và client tương thích broker; bạn phải quản lý BOM/version nhất quán.

**`pom.xml`**

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
    <artifactId>jms-java-config</artifactId>
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

`spring-boot-starter-artemis` đưa JMS/Spring JMS và client Artemis tương thích vào classpath theo dependency management của Spring Boot. Không trộn thêm client `javax.jms` đời cũ với ứng dụng đang sử dụng `jakarta.jms`. Khi dùng Artemis client trực tiếp ngoài Boot, artifact cho Jakarta Messaging 3.x là `org.apache.activemq:artemis-jakarta-client` (xem tài liệu Artemis); chọn phiên bản được hệ thống dependency management của dự án hỗ trợ.

## 4. JavaConfig hoàn chỉnh: tạo bean provider và nối vào Spring

Ta sẽ tạo bốn bean với các trách nhiệm rõ ràng:

1. `artemisConnectionFactory`: provider factory gốc, lấy URL/user/password từ property.
2. `outboundConnectionFactory`: wrapper cache dành cho thao tác gửi bằng template.
3. `jmsTemplate`: gửi tới Queue qua wrapper.
4. `jmsListenerContainerFactory`: listener dùng trực tiếp provider factory, để container tự quản lý connection/session/consumer và khôi phục khi broker lỗi.

Cách tách này đặc biệt hữu ích khi cần kiểm soát caching của publisher mà không làm mất cơ chế recovery của listener.

### 4.1. Tách tham số kết nối khỏi Java source

**`src/main/resources/application.properties`**

```properties
app.jms.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
app.jms.username=${JMS_USERNAME}
app.jms.password=${JMS_PASSWORD}
```

Ở đây `app.jms.*` là **namespace cấu hình do ví dụ tự đặt**, không phải các key của Spring Boot auto-configuration. `JMS_USERNAME` và `JMS_PASSWORD` phải được cung cấp khi chạy; nếu thiếu, Spring sẽ báo không resolve được placeholder. Chỉ `JMS_BROKER_URL` có default cho môi trường phát triển. Không ghi mật khẩu production trực tiếp trong file source hoặc commit vào VCS. Giá trị account phải khớp với cấu hình broker.

Các thông số như endpoint, SSL, failover URL, timeouts, truststore và policy HA **phụ thuộc provider**; cách truyền vào bean vẫn như nhau, nhưng tên thuộc tính/method cấu hình của Artemis không áp dụng nguyên xi cho broker khác.

### 4.2. Class @Configuration

**`src/main/java/example/jms/JmsJavaConfiguration.java`**

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.connection.CachingConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration(proxyBeanMethods = false)
@EnableJms
public class JmsJavaConfiguration {

    @Bean(name = "artemisConnectionFactory", destroyMethod = "close")
    ActiveMQConnectionFactory artemisConnectionFactory(
            @Value("${app.jms.broker-url}") String brokerUrl,
            @Value("${app.jms.username}") String username,
            @Value("${app.jms.password}") String password) {

        // Thứ tự constructor Artemis: URL, user, password.
        return new ActiveMQConnectionFactory(brokerUrl, username, password);
    }

    @Bean(name = "outboundConnectionFactory")
    CachingConnectionFactory outboundConnectionFactory(
            @Qualifier("artemisConnectionFactory")
            ConnectionFactory providerFactory) {

        var cached = new CachingConnectionFactory(providerFactory);
        cached.setSessionCacheSize(5);
        cached.setCacheProducers(true);
        cached.setCacheConsumers(false);
        return cached;
    }

    @Bean
    JmsTemplate jmsTemplate(
            @Qualifier("outboundConnectionFactory")
            ConnectionFactory outboundFactory) {

        var template = new JmsTemplate(outboundFactory);
        template.setPubSubDomain(false); // Queue; không phải Topic.
        return template;
    }

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            @Qualifier("artemisConnectionFactory")
            ConnectionFactory providerFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(providerFactory);
        factory.setPubSubDomain(false);
        factory.setConcurrency("2-4");
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

**Phân tích từng dòng cốt lõi:**

- `@Configuration` yêu cầu Spring đưa các `@Bean` vào application context. `proxyBeanMethods = false` phù hợp vì các bean được liên kết bằng **tham số method và dependency injection**, không gọi trực tiếp từ method `@Bean` này sang method `@Bean` khác.
- `@Value` lấy URL/tài khoản từ `application.properties` sau khi placeholder môi trường được resolve. Tách credentials khỏi code cho phép thay đổi theo môi trường.
- `@Bean(name = "artemisConnectionFactory", destroyMethod = "close")` giữ provider factory dưới quyền quản lý vòng đời của Spring. Khi context shutdown, Spring gọi `close()` của factory Artemis để dọn locator/resource nền. Đây là cách dùng **cụ thể cho class Artemis có method `close()`**; không giả định interface chuẩn `ConnectionFactory` luôn có method đó.
- `@Qualifier` xác định bean chính xác, vì context lúc này có **hai bean implements `ConnectionFactory`** (raw provider và wrapper). Nếu inject mỗi `ConnectionFactory` không qualifier, Spring có thể báo `NoUniqueBeanDefinitionException`.
- `CachingConnectionFactory` dùng một underlying shared connection và cache các session/producer theo cấu hình. `sessionCacheSize(5)` là mức cache cho mỗi loại session/ack mode, **không phải giới hạn cứng tối đa 5 connection/socket hay giới hạn toàn bộ concurrency**.
- `setCacheConsumers(false)` không cần thiết cho luồng chỉ gửi, nhưng làm rõ wrapper này dành cho publisher. Listener được nối qua raw provider factory và tự quản lý consumer.
- `@EnableJms` bật xử lý endpoint `@JmsListener`; đặt `@Bean` với tên mặc định `jmsListenerContainerFactory` để listener không khai báo factory riêng vẫn tìm thấy.
- `setConcurrency("2-4")` minh họa listener mở nhiều consumer khi có tải. Nếu yêu cầu xử lý global FIFO theo nghiệp vụ, concurrency lớn hơn 1 cần được cân nhắc.
- `setSessionTransacted(true)` cho phép container commit/rollback việc nhận trong **JMS local transaction**. Nó không tự đưa các thao tác database vào cùng một transaction.

Với Spring Boot, `@EnableJms` có thể là không bắt buộc khi Boot đã tự bật hạ tầng listener; trong ví dụ JavaConfig chủ động khai báo để dễ nhận diện điểm cấu hình.

### 4.3. Ứng dụng gửi và nhận message

**`src/main/java/example/jms/JmsJavaConfigApplication.java`**

```java
package example.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsJavaConfigApplication {

    private static final String QUEUE = "learning.java-config.queue";

    public static void main(String[] args) {
        SpringApplication.run(JmsJavaConfigApplication.class, args);
    }

    @Bean
    ApplicationRunner sendSample(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.convertAndSend(QUEUE, "hello-from-java-config");
            System.out.println("sent=hello-from-java-config");
        };
    }

    @Component
    public static class SampleReceiver {

        @JmsListener(destination = QUEUE)
        public void receive(String body) {
            System.out.println("received=" + body);
        }
    }
}
```

Hai Java file phải ở đúng package `example.jms` để `@SpringBootApplication` scan được `JmsJavaConfiguration` và `SampleReceiver`.

Điều gì xảy ra khi chạy:
1. Spring tạo `artemisConnectionFactory` từ ba property, sau đó tạo wrapper, template và listener factory.
2. `@EnableJms` đăng ký endpoint cho `SampleReceiver.receive`; listener container kết nối tới Queue bằng provider factory.
3. Sau khi ứng dụng khởi tạo, `ApplicationRunner` gọi template gửi một `TextMessage` chứa `hello-from-java-config`.
4. Broker gửi message cho một consumer của Queue. Listener in payload rồi kết thúc; JMS transaction của lần nhận được commit khi xử lý thành công.
5. Khi ứng dụng dừng đúng cách, Spring dừng listener, hủy wrapper/cache và đóng provider factory do container quản lý.

**Không tự gọi `connectionFactory.close()` trong service gửi:** nếu đóng provider factory bean ở giữa vòng đời ứng dụng, các component dùng chung có thể lỗi kết nối. Tương tự, không lưu một `Session` hoặc `JMSContext` mutable do factory tạo thành singleton dùng chung giữa nhiều thread.

## 5. Chạy ví dụ và quan sát kết quả

### Điều kiện đầu vào

- Java 17+ và Maven, cấu trúc file như trên.
- Một **Apache ActiveMQ Artemis broker đang chạy ngoài ứng dụng** và nghe `tcp://localhost:61616`, hoặc sửa URL đúng endpoint.
- Broker chấp nhận username/password bạn truyền. Queue `learning.java-config.queue` được tạo sẵn **hoặc** broker bật auto-create Queue. Cấu hình Spring chỉ truyền tên Queue; nó không bảo đảm broker sẽ tạo Queue khi auto-create bị tắt.

Ví dụ trong PowerShell (điều chỉnh tài khoản theo broker bạn đang chạy):

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "devuser"
$env:JMS_PASSWORD = "dev-password"

mvn spring-boot:run
```

Trên shell POSIX, thay bằng các biến môi trường tương ứng:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=devuser \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Giả sử broker sẵn sàng, tài khoản đúng và message được giao nhận thành công, output ứng dụng có thể chứa:

```text
sent=hello-from-java-config
received=hello-from-java-config
```

**Không bảo đảm thứ tự hai dòng**, vì listener chạy trên thread khác. Spring Boot và broker client còn ghi log riêng; bạn không nên kỳ vọng toàn bộ stdout chỉ có hai dòng. Mỗi lần khởi động lại, `ApplicationRunner` tạo **thêm một message mới**. Nếu có replica khác đang nhận cùng Queue, message có thể tới replica đó thay vì `SampleReceiver` trong process này.

Dòng `sent=...` chỉ nói lệnh gửi đã trả về thành công từ góc nhìn client; không chứng minh consumer xử lý đúng một lần trong mọi kịch bản lỗi. Muốn đo tính bền vững, kiểm thử persisted delivery, broker restart, commit/rollback và idempotency theo yêu cầu nghiệp vụ.

### Kiểm tra một cấu hình khởi tạo đúng

- `@Bean` có thực sự được nạp? Nếu `JmsJavaConfiguration` nằm ngoài package scan của ứng dụng, Spring có thể thiếu bean; đặt class trong cùng package hoặc dùng `@Import`.
- URL có đúng transport của Artemis? `tcp://localhost:61616` là ví dụ broker Artemis native; không tự thay bằng URL của ActiveMQ Classic rồi kỳ vọng cùng semantics.
- Tài khoản có truy cập broker và quyền tạo/gửi/nhận Queue không? Phân biệt lỗi authentication với lỗi authorization.
- Có bao nhiêu `ConnectionFactory` bean? Với hai bean, inject qua `@Qualifier` hoặc thiết kế một bean `@Primary` có chủ đích.
- Listener có hoạt động khi application startup? Với `@EnableJms`, `@JmsListener` và bean factory đúng tên, Spring tạo listener container; broker không khả dụng có thể khiến container liên tục thử reconnect.
- Broker có cho phép auto-create Queue không? Nếu không, admin phải tạo đúng address/queue và routing phù hợp.

## 6. Phiên bản tối giản: chỉ cần một ConnectionFactory Bean

Không phải ứng dụng nào cũng cần cache và listener custom. Để thấy **nguyên tắc khởi tạo JavaConfig cốt lõi** mà không bị các wrapper che khuất, đây là một phương án rút gọn thay cho cấu hình ở mục 4:

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration(proxyBeanMethods = false)
public class MinimalJmsConfig {

    @Bean(destroyMethod = "close")
    ActiveMQConnectionFactory connectionFactory(
            @Value("${app.jms.broker-url}") String url,
            @Value("${app.jms.username}") String user,
            @Value("${app.jms.password}") String password) {
        return new ActiveMQConnectionFactory(url, user, password);
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }
}
```

Đây là **lựa chọn thay thế** khi bạn muốn có một bean `ConnectionFactory` duy nhất. Nếu dùng code mục 4 thì **không thêm cùng lúc** `MinimalJmsConfig` vào một context; như vậy sẽ tạo các bean trùng vai trò và gây mơ hồ. Trong phiên bản tối giản, `JmsTemplate` có thể được inject trực tiếp vào service, ví dụ:

```java
public final class OrderPublisher {
    private final JmsTemplate template;

    public OrderPublisher(JmsTemplate template) {
        this.template = template;
    }

    public void publish(String orderId) {
        template.convertAndSend("orders.queue", orderId);
    }
}
```

`OrderPublisher` là **class minh họa**; để Spring quản lý nó, đăng ký bằng `@Component` hoặc `@Bean`. Với minimal config, template hoạt động dù không bật listener vì nó chỉ gửi message.

**Khi nào nâng lên cache:** gửi nhiều message tần suất cao, chi phí mở/đóng connection hoặc session đáng kể, kết quả đo cho thấy caching có lợi. Không mặc định mỗi ứng dụng phải tạo cache riêng; Spring Boot có thể đã tự cấu hình cache dựa trên properties khi bạn dùng auto-configuration.

## 7. JavaConfig thủ công so với Spring Boot auto-configuration

Cả hai đều tạo bean để các service inject; khác nhau ở **ai chọn implementation, địa chỉ broker và cơ chế cache**.

| Nhu cầu | JavaConfig thủ công | Spring Boot auto-configuration |
| --- | --- | --- |
| Chọn provider class cụ thể | Viết `new ActiveMQConnectionFactory(...)` trong `@Bean` | Starter, classpath và auto-configuration chọn factory tương ứng. |
| Cấp URL/credentials | `@Value`, `@ConfigurationProperties` hoặc bean cấu hình tùy chọn | Property như `spring.artemis.mode`, `spring.artemis.broker-url`, `spring.artemis.user/password`. |
| Tạo `JmsTemplate` | Tự khai báo `@Bean` khi muốn kiểm soát wiring | Boot thường tạo template khi điều kiện auto-config thỏa mãn. |
| Cache / lifecycle | Tự bao `CachingConnectionFactory` và xác định điểm hủy | Boot có các tùy chọn `spring.jms.cache.*` và cấu hình nền phù hợp. |
| Nhiều broker / custom failover | Có thể tạo bean theo tên và inject `@Qualifier` | Thường cần cấu hình bổ sung khi không còn một factory đơn giản. |
| Tối ưu theo tính năng vendor | Truy cập API riêng trong method cấu hình | Một phần qua properties/customizer, phần đặc biệt vẫn cần custom bean. |

**Ví dụ phương án Boot tự cấu hình (thay thế JavaConfig mục 4):**

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}
```

Với starter tương ứng trên classpath, Boot có thể tự tạo `ConnectionFactory` và `JmsTemplate`; không phải viết `new ActiveMQConnectionFactory`. Nhưng vì đề bài đang học **khởi tạo factory bằng JavaConfig**, ví dụ chính ở mục 4 dùng `app.jms.*` và `@Bean` tự quản lý. **Không trộn hai cách để kiểm soát cùng một factory mà không hiểu thứ tự điều kiện auto-configuration.** Khi bạn tự khai báo bean `ConnectionFactory`, Artemis auto-configuration của Boot thường **back off** theo `@ConditionalOnMissingBean`; cấu hình `spring.artemis.*` lúc đó không nhất thiết còn được áp dụng cho factory tự tạo.

### Dự án chỉ dùng Spring Framework, không dùng Spring Boot

`@Configuration`, `@Bean`, `@Value` và `JmsTemplate` hoạt động tương tự trong Spring Framework thuần. Bạn phải chủ động:
- Tạo `ApplicationContext` (ví dụ `AnnotationConfigApplicationContext` hoặc context web).
- Cấp nơi đọc property (`@PropertySource`/PropertySourcesPlaceholderConfigurer hoặc môi trường container).
- Khai báo dependency `spring-context`, `spring-jms` và provider client tương thích, cấu hình logging và lifecycle.
- Bật `@EnableJms` nếu dùng listener annotation.

Spring Boot thuận tiện vì đã cung cấp bootstrap, quản lý dependency và xử lý `application.properties`. Nguyên tắc khởi tạo bean vẫn là Spring JavaConfig.

## 8. Caching, pooling, listener và ranh giới tài nguyên

### 8.1. ConnectionFactory vs Connection: phân biệt đúng

`ConnectionFactory` là đối tượng cấu hình được tạo lâu dài, còn `Connection` là kết nối runtime do factory trả về. Nếu ứng dụng dùng API gốc:

```java
try (var connection = connectionFactory.createConnection();
     var session = connection.createSession(
             jakarta.jms.Session.AUTO_ACKNOWLEDGE)) {
    // Tạo producer/consumer và dùng trong đúng scope.
}
```

Đây là mã minh họa bên trong một method đã inject `connectionFactory`; sử dụng `try-with-resources` để tránh rò rỉ connection/session. Với `JmsTemplate`, bạn không tự gọi `createConnection()`/`close()` trong logic gửi vì template quản lý scope cho mỗi thao tác.

`CachingConnectionFactory` của Spring giữ một shared connection và cache `Session` theo acknowledgement/transaction mode; kích thước cache là **theo từng mode**, không giới hạn tổng số session đang hoạt động và không tương đương một connection pool độc lập. Tùy tải, có lúc wrapper phải tạo session tạm rồi đóng khi cache đầy. Factory này có cơ chế reconnect khi kết nối báo lỗi, nhưng vẫn cần test behavior thực tế của broker/provider trong tình huống network partition.

**Đóng Spring context đúng cách** là một phần của quản lý kết nối: listener container dừng nhận, cached connection được đóng, raw Artemis factory `close()` tài nguyên locator. Không gọi `close()` thủ công trên singleton provider bean đang được dùng bởi các luồng khác.

### 8.2. Vì sao listener không dùng wrapper cache của publisher?

`DefaultMessageListenerContainer` tự quản lý session, consumer, lifecycle và retry khi broker tạm thời unavailable. Tài liệu Spring cảnh báo dùng một `CachingConnectionFactory` ngoài listener container có thể hạn chế restart/dynamic scaling và để lại consumer cache không còn gắn với container. Vì vậy ví dụ mục 4 dùng **raw Artemis factory cho listener**, dùng cache wrapper chỉ cho template gửi.

Điều này không có nghĩa “listener tuyệt đối không thể dùng caching factory”; đó là lựa chọn thiết kế giúp ownership rõ ràng và ít bất ngờ khi reconnect. Khi dùng pool hoặc factory do application server quản lý, cần xem hướng dẫn chính thức tương ứng thay vì sao chép cấu hình bất kể môi trường.

### 8.3. Khi nào dùng pool thực sự?

Một pool provider-specific có thể quản lý nhiều connection, giới hạn số phiên mượn, idle timeout và max concurrent resources; trong khi `CachingConnectionFactory` chủ yếu là wrapper chia sẻ connection và cache tài nguyên JMS. Nếu cần nhiều kết nối vật lý, giới hạn sức chứa và metrics rõ ràng, cân nhắc connection pool có hỗ trợ JMS/Jakarta đúng phiên bản.

Đặt các giới hạn dựa trên số producer/consumer thực tế, thông lượng và tải broker. Tránh cấu hình “100 connection” mà broker chỉ cho phép 20 hoặc tạo một consumer mới ở mỗi request không được đóng. Với listener, dùng concurrency hợp lý và đo load.

## 9. Transaction và acknowledge không tự xuất hiện khi khởi tạo bean

Tạo `ConnectionFactory` chính xác là bước đầu; **transaction là cấu hình khác**:

- `JmsTemplate.convertAndSend` không mặc nhiên gom nhiều lời gọi vào cùng một transaction JMS. Muốn một nhóm send cùng commit/rollback, dùng `JmsTransactionManager` và biên `@Transactional` phù hợp, hoặc API JMS transacted trong phạm vi riêng.
- `factory.setSessionTransacted(true)` trong listener factory giúp nhận message trong một **local JMS transaction**; nếu listener ném exception và container rollback, broker có thể redeliver message.
- `JmsTransactionManager` thường quản lý tài nguyên của **một `ConnectionFactory`**. Nếu khai báo nhiều factory, phải chọn đúng bean bằng `@Qualifier` và dùng cùng đối tượng với template tham gia transaction.
- Local JMS transaction không tự atomic với database. Nếu ghi DB thành công nhưng JVM chết trước khi commit JMS, message có thể quay lại; consumer cần idempotency và quy trình retry/DLQ.

Ví dụ **snippet bổ sung** để gắn transaction manager với publisher factory ở mục 4:

```java
@Bean
org.springframework.jms.connection.JmsTransactionManager jmsTransactionManager(
        @Qualifier("outboundConnectionFactory")
        ConnectionFactory outboundFactory) {

    return new org.springframework.jms.connection.JmsTransactionManager(outboundFactory);
}
```

Nếu sử dụng `@Transactional(transactionManager = "jmsTransactionManager")` trên một method Spring-managed service và gọi `JmsTemplate` trong biên đó, các send có thể sử dụng JMS session được Spring ràng buộc với transaction. **Snippet trên không phải một class Java chạy độc lập**: đặt vào class `@Configuration` với import `ConnectionFactory`, `@Qualifier` và `@Bean` từ ví dụ chính.

Không thêm JTA/XA chỉ vì đã tạo `ConnectionFactory` bằng code; XA đòi hỏi XA-capable provider factory và transaction manager thích hợp, kéo theo chi phí vận hành.

## 10. Bảo mật và cấu hình theo môi trường

Một method JavaConfig là vị trí phù hợp để kiểm soát toàn bộ cách tạo connection factory, nhưng không nên nhồi bí mật và tham số vận hành cố định vào Java source:

1. **Credentials:** nhận từ environment/secret manager. Giới hạn quyền account theo Queue cần gửi/nhận. Tránh in password hoặc toàn bộ URI chứa credential ra log.
2. **Transport bảo mật:** `tcp://localhost:61616` chỉ minh họa phát triển trên máy cục bộ. Ở môi trường thật cần cấu hình TLS/mTLS, CA/truststore, certificate hostname verification và endpoint phù hợp tài liệu Artemis/broker.
3. **Kết nối có dự phòng:** cluster/failover/reconnect URI và timeout là tính năng provider-specific. Tạo bean bằng Java không tự tạo HA.
4. **Shutdown:** cho container cơ hội dừng listener trước khi hủy factory; với Spring bean đơn lẻ, dùng `destroyMethod` khi provider có phương thức hủy, hoặc cơ chế `DisposableBean` cho wrapper.
5. **Fail-fast/health check:** tạo `@Bean` thành công không đồng nghĩa broker đang reachable. Nếu cần health signal, thử kết nối/gửi-nhận trên broker test hoặc dùng health indicator được cấu hình; không coi một phép thử mở socket là kiểm chứng queue routing, quyền hay transaction.

Với nhiều broker, đặt tên bean rõ ràng như `ordersConnectionFactory`, `auditConnectionFactory` rồi inject chính xác vào từng `JmsTemplate`. Đừng sử dụng một bean mặc định mơ hồ khi hai broker có credential và destination hoàn toàn khác nhau.

## 11. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: ConnectionFactory` | Chưa đăng ký `@Bean`/không scan config hoặc thiếu starter/client | Kiểm tra package scan, dependency, kiểu bean và JavaConfig đã nạp. |
| `NoUniqueBeanDefinitionException` | Có nhiều bean implements `ConnectionFactory` | Dùng `@Qualifier` chính xác hoặc chọn `@Primary` có chủ đích. |
| `Could not resolve placeholder 'JMS_USERNAME'` | Chưa cấp biến môi trường | Cấp credential trước khi start; không thay bằng mật khẩu hardcode trong repo. |
| `Connection refused`, timeout | Broker/port sai, mạng/firewall, TLS mismatch | Kiểm tra URL/transport, cổng thực tế, DNS, broker logs và profile. |
| Lỗi authentication/authorization | Account sai hoặc không được quyền gửi/nhận/tạo Queue | Kiểm tra quyền với admin broker, tránh log password. |
| Không thấy `received=...` | Listener chưa chạy, Queue khác, message được replica khác nhận, broker thiếu Queue | Xem listener registration, tên destination, Queue depth và broker routing. |
| Listener khó restart/recover | Wrapper cache ngoài container, cấu hình retry/transport không phù hợp | Ưu tiên raw/provider factory cho listener; test broker restart. |
| Có bean nhưng không kết nối được | Việc tạo factory chưa thực hiện network handshake | Tách kiểm tra bean injection khỏi integration test thật. |
| `javax.jms` và `jakarta.jms` không tương thích | Trộn thư viện Jakarta với driver JMS đời cũ | Đồng bộ major version Spring, Jakarta API và client provider. |
| Hai lần gửi không commit cùng nhau | Chỉ tạo `JmsTemplate` mà không có biên JMS transaction | Thêm `JmsTransactionManager`/transaction boundary đúng nhu cầu. |

### Bài kiểm thử có giá trị

- **Bean wiring:** xác nhận ApplicationContext có đúng `artemisConnectionFactory`, `outboundConnectionFactory`, `jmsTemplate` và `jmsListenerContainerFactory`; kiểm tra template trỏ đúng wrapper.
- **Integration:** chạy với broker test, gửi một ID duy nhất rồi chờ listener ghi nhận đúng Queue. Không kiểm thử bằng sleep cứng nếu có thể chờ một signal/condition xác định.
- **Failure:** dừng broker rồi bật lại, quan sát listener reconnect và publisher báo lỗi/khôi phục ra sao. Đừng mặc định mất kết nối không tạo ra send có trạng thái mơ hồ.
- **Security:** chạy với tài khoản không được quyền gửi/nhận để bảo đảm lỗi rõ ràng và không lộ credentials.
- **Shutdown:** đóng context và kiểm tra không còn consumer/session bị treo trên broker theo metrics của provider.
- **Concurrency:** gửi nhiều message với 2–4 consumer, kiểm tra việc xử lý idempotent; không giả định message tự động chia đều hoặc commit theo thứ tự.

## 12. Checklist ghi nhớ

- Chọn đúng **JMS provider implementation**, dùng interface `jakarta.jms.ConnectionFactory` để inject vào các tầng Spring.
- Tạo provider bean trong `@Configuration` và trả implementation cụ thể; tham số kết nối đi qua properties/env.
- Dùng `@Qualifier` khi có nhiều `ConnectionFactory`, nhất là raw factory và cache wrapper.
- Dùng `JmsTemplate` cho publisher, `@JmsListener` + `DefaultJmsListenerContainerFactory` cho consumer; cân nhắc raw factory cho listener.
- Để Spring sở hữu vòng đời các bean; đóng connection/session do **chính application code tự mở**, không đóng bean factory singleton trong business method.
- Kiểm chứng broker, quyền Queue, TLS, reconnect và transaction bằng integration test thực; việc tạo `@Bean` chưa đủ.
- Phân biệt cache với pool, transaction JMS với transaction database, và một lần phát message với kết quả nghiệp vụ đúng một lần.

**Tự kiểm tra:** (1) Vì sao `ActiveMQConnectionFactory` trong `@Bean` không nhất thiết đã kết nối broker? (2) Vì sao hai bean `ConnectionFactory` cần `@Qualifier`? (3) Vì sao `@JmsListener` được nối qua raw provider factory thay vì wrapper gửi? (4) Ai đóng bean factory khi context dừng? (5) Cần thêm thành phần nào khi nhiều thao tác `JmsTemplate` phải cùng một transaction JMS?

**Đáp án định hướng:** (1) Factory có thể chỉ nắm cấu hình, kết nối mở khi cần thao tác. (2) Spring phải chọn bean đích duy nhất. (3) Listener container có lifecycle/caching/recovery riêng. (4) Spring container thực hiện destroy callback; với Artemis có `close()`. (5) Một `JmsTransactionManager` gắn đúng factory và biên transaction phù hợp.

## Tài liệu tham khảo

- Jakarta Messaging 3.1 — chuẩn `ConnectionFactory` và resource model: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework — Using Spring JMS, ConnectionFactory và Caching: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework — Annotation-driven listener endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework — `CachingConnectionFactory` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html
- Spring Framework — `DefaultMessageListenerContainer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Boot — JMS và Artemis: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
- Apache ActiveMQ Artemis — Client classpath và Jakarta client: https://artemis.apache.org/components/artemis/documentation/latest/client-classpath
- Apache ActiveMQ Artemis — Using JMS: https://artemis.apache.org/components/artemis/documentation/latest/using-jms