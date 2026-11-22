# Phân biệt Spring Framework thuần và tự cấu hình Spring Boot khi thiết lập kết nối JMS

**Bối cảnh:** Trong một ứng dụng Java dùng Jakarta Messaging (JMS), cả **Spring Framework thuần** và **Spring Boot** đều có thể gửi bằng `JmsTemplate` và nhận bằng `@JmsListener`. Khác biệt chủ yếu nằm ở **ai tạo các bean cấu hình và theo quy tắc nào**. Hiểu ranh giới này giúp tránh tình trạng thêm một dependency nhưng không có kết nối, tự khai báo bean làm mất auto-configuration, hoặc chạy được ở development nhưng sai transaction/recovery khi triển khai.

**Phạm vi ví dụ:** Java 17+, Spring Framework 6.1.x và Spring Boot 3.3.x (Jakarta Messaging, package `jakarta.jms`), broker **ActiveMQ Artemis chạy bên ngoài ứng dụng**. Hai đường triển khai dùng cùng loại broker để so sánh. Những phiên bản Spring Boot/Spring Framework khác cần đối chiếu tài liệu phiên bản vì điều kiện auto-configuration và thuộc tính cấu hình có thể thay đổi.

## 1. Cùng một JMS API, hai cách dựng Spring container

Dù cấu hình theo cách nào, chuỗi phụ thuộc cốt lõi vẫn là:

~~~text
Ứng dụng
├─ JMS producer
│    └─ JmsTemplate
│         └─ jakarta.jms.ConnectionFactory ──► JMS client ──► broker Artemis
└─ JMS consumer
     └─ @JmsListener
          └─ JmsListenerContainerFactory
               └─ listener container
                    └─ jakarta.jms.ConnectionFactory ──► broker Artemis
~~~

**Spring Framework** cung cấp `JmsTemplate`, `@EnableJms`, `DefaultJmsListenerContainerFactory`, listener container, exception translation, message conversion, destination resolver và transaction integration. Nó **không tự quyết định** rằng bạn sẽ kết nối Artemis tại `tcp://localhost:61616`, dùng user nào hoặc tạo listener container với chính sách nào. Nếu chỉ thêm `spring-jms` vào ứng dụng Spring thuần, provider-specific `ConnectionFactory` chưa tự xuất hiện.

**Spring Boot** chạy trên Spring Framework và thêm **auto-configuration có điều kiện**. Với JMS starter, client provider phù hợp và các thuộc tính `spring.artemis.*` hoặc `spring.activemq.*`, Boot có thể tạo `ConnectionFactory`, bọc cache/pool và tạo `JmsTemplate` cùng default `JmsListenerContainerFactory`. Các bean ứng dụng chủ động khai báo vẫn có thể được dùng; Boot thường **back off** với một số bean đã tồn tại. Boot không tạo ra giao thức JMS mới và không thay broker thực.

> **Phân biệt rõ:** “Spring Boot tự cấu hình JMS” có nghĩa **tự cấu hình Spring-side infrastructure khi đủ điều kiện**. Nó **không** có nghĩa broker, queue, credential, TLS, HA, ACL, DLQ và persistence sẽ được tự cấp phát trong môi trường production. Embedded broker là khả năng riêng, chỉ hoạt động khi có dependency/mode thích hợp; bài này dùng broker ngoài.

## 2. Bảng đối chiếu: ai chịu trách nhiệm việc gì?

| Thành phần / quyết định | Spring Framework thuần | Spring Boot với Artemis starter |
| --- | --- | --- |
| JMS API và provider | Tự thêm `spring-jms`, `jakarta.jms` và JMS client tương thích | `spring-boot-starter-artemis` đưa phần lớn dependency phù hợp; BOM quản lý version |
| Broker endpoint và credential | Tự khởi tạo client `ConnectionFactory` hoặc lookup qua JNDI | Thường khai báo `spring.artemis.mode=native`, `broker-url`, `user`, `password` |
| Bean `ConnectionFactory` | Tự khai báo hoặc nhập từ cấu hình khác | Boot tạo theo điều kiện classpath/bean và provider |
| Caching/pooling connection, session | Tự chọn wrapper hoặc pool phù hợp | Mặc định Boot bọc bằng `CachingConnectionFactory`; pool cần dependency/properties riêng |
| `JmsTemplate` | Tự khai báo `@Bean`, chỉ định `ConnectionFactory` | Auto-configure khi điều kiện đáp ứng; có thể inject trực tiếp |
| `@JmsListener` | Thường cần `@EnableJms` để bật annotated endpoints | Boot kích hoạt hạ tầng listener khi JMS infrastructure hiện diện; thường không cần tự viết `@EnableJms` |
| Factory cho `@JmsListener` | Tự tạo bean tên `jmsListenerContainerFactory` hoặc chỉ định factory | Boot tạo default factory nếu chưa có bean phù hợp |
| Mode queue/topic | Tự cấu hình `pubSubDomain` trên template và container | `spring.jms.pub-sub-domain` điều khiển default (mặc định queue) |
| Transaction/ack listener | Tự chọn `sessionTransacted`, transaction manager, concurrency | Default factory Boot được cấu hình transactional; chi tiết phụ thuộc JTA hiện diện và overrides |
| Message converter và destination resolver | Tự đăng ký và gắn vào template/listener | Boot có thể gắn bean converter/resolver vào auto-configured infrastructure |
| Điều kiện thiếu dependency hoặc xung đột bean | Thường thấy dependency injection/startup failure trực tiếp | Condition report giúp nhìn auto-config “matched” hay “did not match” |
| Tuỳ biến phức tạp | Hoàn toàn chủ động từng bean | Cấu hình properties trước; bean/configurer cho phần vượt phạm vi properties |

**Nhận xét kỹ thuật:** Spring thuần không “thấp cấp hơn JMS” — hai bên dùng cùng `spring-jms` và `jakarta.jms`. Boot chủ yếu giúp giảm cấu hình lặp và quản lý version. Hiểu cấu hình thuần giúp biết chính xác Boot đang tạo gì để tránh ghi đè ngoài ý muốn.

## 3. Kiểm tra điều kiện trước khi viết code

Cần xác nhận bốn nhóm điều kiện:

1. **Java + API:** ứng dụng Spring 6+/Boot 3+ dùng `jakarta.jms.ConnectionFactory`, `jakarta.jms.Message`. Driver JMS cũ chỉ dùng `javax.jms` không thể đơn giản ép kiểu sang Jakarta.
2. **JMS provider client:** chọn thư viện tương thích broker và API Jakarta. Với Artemis dùng `artemis-jakarta-client`, tránh ghép nhầm `artemis-jms-client` legacy `javax.jms` với Spring 6.
3. **Broker thật:** URL phải dùng transport mà client hỗ trợ; broker cần bật listener/acceptor tương ứng, network tới được, credentials/permissions hợp lệ.
4. **Destination và consumption:** queue/topic tên gì, auto-create có bật không, security permissions, message TTL/retention, consumer ack/transactions, DLQ. Tạo Java object `Destination` không đồng nghĩa tạo durable broker resource theo policy.

### 3.1. Những dependency khác nhau

Ở **Spring thuần**, cần tự quản lý library versions tương thích, tối thiểu `spring-context`, `spring-jms`, Jakarta JMS API (thường được kéo qua Spring/Artemis) và Artemis Jakarta client. Có thể dùng Spring Framework BOM để quản lý version Spring, pin provider version tương thích.

Ở **Spring Boot**, dependency tối thiểu cho ví dụ là `spring-boot-starter-artemis` cùng Spring Boot core starter (được kéo transitively). Plugin/BOM của Boot quản lý version Spring và JMS client; không pin thêm `spring-jms` hay Artemis phiên bản riêng trừ khi có lý do và đã kiểm tra dependency graph.

**Đừng suy luận** rằng có một class tên `ConnectionFactory` trên classpath là đồng nghĩa bean `ConnectionFactory` đã được đăng ký. **Classpath** cho Spring biết loại implementation nào có thể dùng; **bean definition** mới là thứ được inject vào `JmsTemplate`/listener.

## 4. Ví dụ A — Spring Framework thuần: tự lắp toàn bộ JMS infrastructure

Đây là một **ứng dụng Java SE dùng Spring ApplicationContext**, không dùng `@SpringBootApplication`, không có auto-configuration của Boot. Mục tiêu là thấy rõ từng điểm phải khai báo.

### 4.1. build.gradle

Ví dụ độc lập minh họa với Gradle Groovy, Java 17 và các phiên bản đã được phát hành. Trong dự án thực tế, chọn cùng một dải versions đã kiểm thử với broker:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework:spring-framework-bom:6.1.20')
    implementation 'org.springframework:spring-context'
    implementation 'org.springframework:spring-jms'
    implementation 'org.apache.activemq:artemis-jakarta-client:2.42.0'

    runtimeOnly 'org.slf4j:slf4j-simple:2.0.17'
}

application {
    mainClass = 'example.jmsmanual.ManualJmsApp'
}
~~~

Sử dụng **Jakarta client** với Spring 6. Nếu muốn cập nhật những phiên bản được hỗ trợ lâu dài hơn, hãy chọn bộ Spring/provider tương ứng và chạy kiểm thử tích hợp; không mặc định các version nêu trên là bản mới nhất hay bộ production được chứng nhận.

### 4.2. Toàn bộ mã Java (một tệp có thể biên dịch)

Tệp `src/main/java/example/jmsmanual/ManualJmsApp.java`:

~~~java
package example.jmsmanual;

import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

public final class ManualJmsApp {
    public static void main(String[] args) throws InterruptedException {
        try (var context = new AnnotationConfigApplicationContext(
                ManualJmsConfig.class)) {

            JmsTemplate template = context.getBean(JmsTemplate.class);
            template.convertAndSend("orders.inbox", "order-42");
            System.out.println("Producer sent order-42");

            // Chỉ để quan sát listener trước khi chương trình kết thúc.
            Thread.sleep(3_000L);
        }
    }
}

@Configuration
@EnableJms
class ManualJmsConfig {
    @Bean(destroyMethod = "close")
    ActiveMQConnectionFactory connectionFactory() {
        String url = System.getenv().getOrDefault(
                "JMS_BROKER_URL", "tcp://localhost:61616");
        String user = System.getenv().getOrDefault(
                "JMS_USER", "demo");
        String password = System.getenv("JMS_PASSWORD");

        if (password == null || password.isBlank()) {
            throw new IllegalStateException(
                    "JMS_PASSWORD environment variable is required");
        }
        return new ActiveMQConnectionFactory(url, user, password);
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false); // "orders.inbox" là queue.
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }

    @Bean
    OrderListener orderListener() {
        return new OrderListener();
    }
}

class OrderListener {
    @JmsListener(destination = "orders.inbox")
    public void onMessage(String body) {
        System.out.println("Consumer received " + body);
    }
}
~~~

**Chú thích chính xác từng bean:**

- `connectionFactory()` tạo **provider-specific** Artemis factory; Spring không thể đoán URL hoặc tài khoản. `@Bean(destroyMethod = "close")` để container đóng nguồn tài nguyên khi shutdown.
- `jmsTemplate(...)` đưa cùng `ConnectionFactory` vào Spring JMS abstraction. Đây là đường **gửi**; không cần tạo tay `Connection`/`Session` trong từng business method.
- `@EnableJms` bật xử lý annotation `@JmsListener` trong Spring Framework thuần.
- Bean tên **`jmsListenerContainerFactory`** là default factory mà annotated endpoint infrastructure tìm. `setConnectionFactory` quyết định nơi consumer kết nối; `setPubSubDomain(false)` xác định queue semantics; `setSessionTransacted(true)` để lỗi listener dẫn đến rollback local JMS thay vì tự ý xác nhận.
- `orderListener()` đăng ký listener object như một Spring bean. Không có `@ComponentScan` trong ví dụ nên bean này phải được khai báo tường minh.
- `AnnotationConfigApplicationContext` quản lý lifecycle các bean và container; `Thread.sleep` chỉ phục vụ demo để ứng dụng không đóng trước khi có cơ hội nhận message, **không** phải kỹ thuật chờ message đáng dùng trong hệ thống thật.

**Chuẩn bị trước khi chạy:** broker Artemis phải đang nghe tại URL, tồn tại (hoặc cho phép auto-create) queue `orders.inbox` và chấp nhận credential có quyền gửi/nhận. Tại terminal, thiết lập `JMS_PASSWORD`, `JMS_USER` và `JMS_BROKER_URL` theo hệ điều hành/môi trường đang dùng; không hard-code mật khẩu vào mã. Sau đó chạy:

~~~bash
./gradlew run
~~~

Ví dụ log khi broker sẵn sàng có thể có:

~~~text
Producer sent order-42
Consumer received order-42
~~~

**Không cam kết stdout đúng thứ tự:** listener chạy bất đồng bộ, có thể log nhận trước log gửi, hoặc không nhận kịp trong cửa sổ demo. Nếu broker không kết nối được, `convertAndSend` có thể ném `JmsException` và không có dòng “sent” thành công. Log framework/provider có thể xuất hiện thêm.

**Trade-off của ví dụ:** dùng native `ConnectionFactory` trực tiếp cho cả publisher và listener để dễ thấy đồ thị bean. Với lưu lượng lớn, `JmsTemplate` thường hưởng lợi từ caching/pooling. Khi tối ưu, cấu hình cache/pool cho đường gửi và **native factory cho listener container**, hoặc nghiên cứu recovery/concurrency của wrapper. Không thay đổi ngầm trong bài demo để tránh che mất bản chất.

## 5. Vì sao các bean A phải hiện diện khi dùng Spring thuần?

Nếu bỏ từng thành phần trong ví dụ A:

| Bỏ hoặc khai báo sai | Hệ quả dễ quan sát | Cách sửa |
| --- | --- | --- |
| Không có Artemis client/provider `ConnectionFactory` | Không có cách mở JMS connection; template/factory thiếu dependency | Thêm client tương thích và khai báo `@Bean ConnectionFactory` |
| Không có `JmsTemplate` bean | Inject `JmsTemplate` thất bại, nếu không ai khác tự khai báo | Tạo `new JmsTemplate(connectionFactory)` trong `@Bean` |
| Thiếu `@EnableJms` | `@JmsListener` không được kích hoạt tự động chỉ vì có annotation trên class | Bật `@EnableJms` hoặc đăng ký listener container thủ công |
| Không có default `jmsListenerContainerFactory` | Listener endpoints không có container factory thích hợp; có thể thất bại lúc đăng ký | Tạo đúng bean tên mặc định hoặc ghi `containerFactory` trong annotation |
| Không đăng ký `OrderListener` thành Spring bean | Annotation trên object chưa được Spring quản lý không được phát hiện | `@Bean`, `@ComponentScan` hoặc registration tương đương |
| Sai queue/topic semantics | Có producer/consumer nhưng destination không khớp; broker có thể phân nhánh sai | Đồng bộ `pubSubDomain`/destination resolver và policy |
| Dùng sai username/URL | Connection/authentication/reconnect lỗi; producer/consumer không trao đổi được | Sửa network, TLS, ACL và provider-specific properties |

**Lưu ý:** `@EnableJms` chỉ phục vụ **listener annotation infrastructure**. Spring JMS `JmsTemplate` có thể **gửi** mà không có `@EnableJms` nếu bạn đã tạo và inject đúng bean `JmsTemplate`/`ConnectionFactory`. Đừng dùng “có @EnableJms” làm phép kiểm tra đủ cho cả send và receive.

## 6. Ví dụ B — Spring Boot: cùng nghiệp vụ, ít boilerplate hơn

Ở đây Boot phát hiện Artemis starter/provider và kết hợp `application.yaml` để tạo/đưa các bean JMS vào ApplicationContext.

### 6.1. build.gradle của một ứng dụng Spring Boot độc lập

Ví dụ dùng Spring Boot 3.3.13 (một phiên bản có thật trong nhánh 3.3). Với dự án mới, dùng release line còn được hỗ trợ theo chính sách đội ngũ thay vì coi 3.3.13 là “latest”:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

**Không cần** khai báo `spring-jms`, `jakarta.jms-api` và `artemis-jakarta-client` riêng cho bài này: starter/BOM chịu trách nhiệm bộ dependency tương thích. Bắt đầu từ dependency tối thiểu rồi dùng `./gradlew dependencies --configuration runtimeClasspath` để kiểm tra những gì thực sự được kéo vào.

### 6.2. application.yaml: cấu hình broker ngoài

Tệp `src/main/resources/application.yaml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
    cache:
      session-cache-size: 5
~~~

Đặt mật khẩu qua environment **`SPRING_ARTEMIS_PASSWORD`** trong môi trường chạy (Spring Boot relaxed binding), hoặc qua secret store/config system được tổ chức cho phép. Nếu broker cần authentication và chưa có credential đúng, kết nối sẽ thất bại; cấu hình YAML trên không tự cung cấp mật khẩu.

- `spring.artemis.mode=native`: yêu cầu nối tới **broker đang chạy bên ngoài** thay vì kỳ vọng embedded server.
- `spring.artemis.broker-url`, `user`, `password`: đầu vào để Artemis auto-configuration tạo client connection factory.
- `spring.jms.pub-sub-domain=false`: mặc định diễn giải tên destination như **queue**. Nếu muốn topic, thay đổi policy phù hợp ở cả producer và listener hoặc dùng các template/factory riêng.
- `spring.jms.cache.session-cache-size`: thiết lập cache session của Boot `CachingConnectionFactory` ở đường gửi; nó **không** phải số consumer hay số connection đồng thời được phép.
- Không có `@Bean ConnectionFactory` ở ví dụ này: chính đó là phần Boot giúp loại bỏ.

### 6.3. Toàn bộ mã Java ứng dụng Boot

Tệp `src/main/java/example/jmsboot/BootJmsApp.java`:

~~~java
package example.jmsboot;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class BootJmsApp {
    public static void main(String[] args) {
        SpringApplication.run(BootJmsApp.class, args);
    }

    @Bean
    ApplicationRunner sendOne(JmsTemplate template) {
        return args -> {
            template.convertAndSend("orders.inbox", "order-42");
            System.out.println("Producer sent order-42");
        };
    }
}

@Component
class BootOrderListener {
    @JmsListener(destination = "orders.inbox")
    public void onMessage(String body) {
        System.out.println("Consumer received " + body);
    }
}
~~~

Chạy:

~~~bash
./gradlew bootRun
~~~

**Điều kiện giống ví dụ A:** broker thật phải sẵn sàng, queue tồn tại/được phép auto-create và credential/quyền hợp lệ. Khi có kết nối, listener có thể in thông điệp nhưng thứ tự log giữa producer/consumer không xác định. Khi chạy lại, `ApplicationRunner` sẽ **gửi một message mới mỗi lần khởi động**; trong production, sự kiện nên phát ra từ thao tác nghiệp vụ chứ không đặt trong startup runner.

**Điều Boot làm giúp:**

1. Tạo Artemis `ConnectionFactory` theo dependency và properties khi các điều kiện auto-configuration đáp ứng.
2. Mặc định bọc native provider factory bằng Spring `CachingConnectionFactory` cho đường `JmsTemplate`; cấu hình qua `spring.jms.cache.*`.
3. Tạo `JmsTemplate` có khả năng inject vào `sendOne`; dựa trên `ConnectionFactory` phù hợp.
4. Tự kích hoạt hạ tầng phát hiện `@JmsListener` và tạo default listener factory/container khi không có bean tự định nghĩa.
5. Gắn một số `MessageConverter`, `DestinationResolver` và cấu hình listener từ context/properties khi phù hợp.

**Điều Boot không làm giúp:** không xác thực schema nghiệp vụ, không đảm bảo tiêu thụ exactly-once, không tạo external broker và không tự cấp quyền network/TLS/ACL/retention/DLQ. Cấu hình mặc định vẫn phải được kiểm chứng bằng lỗi thực tế và transaction tests.

## 7. Điểm dễ nhầm nhất: @EnableJms và tự động tìm @JmsListener

### Spring Framework thuần

~~~java
@Configuration
@EnableJms
class ListenerConfiguration {
    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Đây là **snippet** có import `@Configuration`, `@Bean`, `@EnableJms`, `ConnectionFactory` và `DefaultJmsListenerContainerFactory` như ví dụ A. `@EnableJms` nhập JMS listener annotation infrastructure; khi thấy bean có `@JmsListener`, Spring sử dụng factory mặc định tên `jmsListenerContainerFactory` nếu annotation không chỉ rõ factory khác.

### Spring Boot

Boot JMS auto-configuration thường đã nhập đúng phần listener infrastructure khi cần, nên trong ví dụ B **không có `@EnableJms`** vẫn hoạt động. Thêm `@EnableJms` đơn thuần không thay thế `ConnectionFactory`, và không nên coi đó là cách sửa mặc định cho mọi lỗi listener.

Cách phân tích khi listener không chạy:

- Bean listener có thuộc package được `@SpringBootApplication` component scan hoặc được tạo qua `@Bean` không?
- Có `ConnectionFactory` và đúng broker/destination không?
- Có `DefaultJmsListenerContainerFactory` phù hợp? `@JmsListener(containerFactory="...")` có trỏ đúng tên không?
- Destination là queue hay topic? Có message chờ, TTL/selector, ACL, durable subscription chưa?
- Listener container có đang reconnect hoặc đã stop vì lỗi kết nối/transaction/conversion không?

**Sai điển hình:** một class có `@JmsListener` nhưng được tạo bằng `new` ngoài Spring container; khi đó Boot cũng không phát hiện annotation trên instance không được quản lý.

## 8. Phân biệt ConnectionFactory, CachingConnectionFactory và pool

### 8.1. Native ConnectionFactory

`jakarta.jms.ConnectionFactory` là interface chuẩn. `ActiveMQConnectionFactory` của Artemis là implementation của provider; nó biết broker URL, user, password, TLS/transport, failover và cách tạo JMS `Connection`. Trong ví dụ A, ứng dụng trực tiếp khai báo bean loại này.

### 8.2. Spring CachingConnectionFactory

`org.springframework.jms.connection.CachingConnectionFactory` là Spring wrapper cho native connection factory: có thể giữ một shared Connection và cache `Session`, `MessageProducer`, `MessageConsumer` theo cấu hình; số cache session mặc định của wrapper là nhỏ, cần điều chỉnh theo concurrency. Điều này không tương đương một **pool of physical connections** với limit, fairness, validation và blocking semantics đầy đủ.

Lưu ý quan trọng: listener container kiểu `DefaultMessageListenerContainer` thường cần quản lý recovery connection riêng và các session/consumer theo vòng đời container. Tài liệu Boot đề nghị **listener factory sử dụng native ConnectionFactory**, còn cached wrapper phù hợp hơn cho nhiều tác vụ send ngắn thông qua `JmsTemplate`. Boot có cơ chế unwrap cache wrapper khi cấu hình listener mặc định.

Trong Spring thuần, cách chia vai trò có thể là:

~~~java
// Snippet cấu hình: nativeCf là một Artemis ConnectionFactory bean.
CachingConnectionFactory sendCache =
        new CachingConnectionFactory(nativeCf);
sendCache.setSessionCacheSize(5);

JmsTemplate sender = new JmsTemplate(sendCache);

DefaultJmsListenerContainerFactory listenerFactory =
        new DefaultJmsListenerContainerFactory();
listenerFactory.setConnectionFactory(nativeCf); // native cho listener
listenerFactory.setSessionTransacted(true);
~~~

Đây là **đoạn minh họa ý tưởng**, không phải chương trình chạy độc lập: nếu đưa vào Spring thì khai báo lifecycle `sendCache` thành bean quản lý, tránh tạo cache rồi không đóng khi shutdown. Khi có cả native và cached bean cùng implement `ConnectionFactory`, cần `@Qualifier` hoặc `@Primary` rõ ràng để tránh inject nhầm.

### 8.3. Native pool

Nếu load cao đòi hỏi **nhiều physical connection** với capacity controls, cân nhắc pool được provider/adapter hỗ trợ. Ví dụ với Boot 3.x và Artemis, khi có dependency `org.messaginghub:pooled-jms` thì có thể dùng:

~~~yaml
spring:
  artemis:
    pool:
      enabled: true
      max-connections: 20
~~~

Đây là **lựa chọn cấu hình thay thế**, không thêm vào ví dụ B cùng lúc với mong đợi cache wrapper hoạt động y hệt. Cần đọc broker/provider docs về session pooling, transaction boundaries, health checks và connection lifetime. Đừng dùng tên `spring.jms.cache.session-cache-size` để suy ra `max-connections` của pool.

### 8.4. “Có bean ConnectionFactory” chưa chắc “kết nối đã được chứng minh”

Khởi tạo bean JMS client có thể chỉ lưu endpoint/credentials và chưa mở kết nối ngay. Không xem **Spring context khởi động thành công** là bằng chứng đã đăng nhập broker thành công, đã xác thực queue hay message đi qua mạng. Phải thực hiện phép send/receive thực tế và quan sát broker.

## 9. Transaction và acknowledgment: hai kiểu cấu hình có thể khác mặc định

### 9.1. Spring Framework thuần phải tự quyết định

`DefaultJmsListenerContainerFactory` do bạn tạo trong Spring thuần sẽ nhận những thiết lập bạn cung cấp. Nếu không bật transaction, listener container có thể dùng `AUTO_ACKNOWLEDGE`, trong đó tùy loại container ACK xảy ra trước hoặc sau handler; với `DefaultMessageListenerContainer`, exception ở listener trong mode mặc định không đảm bảo redelivery. Với tác vụ quan trọng, bắt đầu bằng:

~~~java
factory.setSessionTransacted(true);
~~~

Lúc ấy mỗi lần nhận/handler chạy trong **local JMS transaction**. Handler thành công thì JMS commit; exception phù hợp khiến rollback và message có thể được broker redeliver theo policy. Bạn phải xác nhận delay, retry limit, DLQ thực tế ở provider.

### 9.2. Spring Boot mặc định cài đặt transactional listener

Tài liệu Spring Boot 3.x nói **default `JmsListenerContainerFactory` là transactional**:

- Nếu có `JtaTransactionManager` phù hợp, Boot liên kết nó tới listener container theo mặc định.
- Nếu không có JTA, Boot bật `sessionTransacted=true` trên default listener factory.

Điều này không có nghĩa một `@Transactional` bất kỳ tự biến JMS + JDBC + HTTP thành **một transaction phân tán**. Với một local DB transaction, Boot/Spring có thể đồng bộ thời điểm JMS ack sau khi transaction DB kết thúc thành công, nhưng vẫn tồn tại **cửa sổ failure** giữa DB commit và JMS commit; consumer phải chịu được replay.

**Rủi ro so sánh:** copy phương thức `@JmsListener` từ Boot sang Spring thuần mà không copy/hiểu cấu hình listener factory có thể làm đổi ack/rollback semantics dù code handler không hề thay đổi.

### 9.3. Transaction của producer cũng là chuyện riêng

- `JmsTemplate.convertAndSend` thông thường gửi thông qua session không transacted ngoài transaction context, trừ khi template hoặc một transaction manager/JMS session đang hoạt động được cấu hình phù hợp.
- `JmsTemplate` có thể tham gia JMS transaction do Spring quản lý; `JmsTransactionManager` quản lý **một JMS resource**, không tự gộp cùng DB.
- Muốn xuất sự kiện theo transaction DB mà tránh “DB commit thành công nhưng chưa gửi JMS”, nên thiết kế **transactional outbox**, publisher retry có giới hạn và consumer idempotent. XA/JTA chỉ khi thật sự cần và hạ tầng hỗ trợ.

**Điểm kiểm thử:** cố tình ném exception từ listener, quan sát queue depth/redelivery; thử crash sau DB commit nhưng trước JMS commit để thấy vì sao duplicate detection vẫn cần có.

## 10. Auto-configuration là các điều kiện, không phải một phép màu

Khi Boot khởi động, các lớp auto-configuration được xét theo **classpath, bean definitions, properties và tình trạng hạ tầng**. Tùy provider, Boot cần thấy client tương thích, JMS API và chưa có bean mà configuration tương ứng phải tạo.

Giả sử bạn đang dùng ví dụ B:

1. Thêm `spring-boot-starter-artemis` → Spring Boot có Artemis driver và Spring JMS.
2. Thêm `spring.artemis.mode=native` cùng broker URL → Boot chọn cấu hình native client.
3. Khi chưa tự khai báo `ConnectionFactory` theo điều kiện của Artemis config → Boot có thể đăng ký provider factory và cache/pool wrapper.
4. Khi chưa tự khai báo `JmsTemplate` hoặc `JmsOperations` bean theo điều kiện có liên quan → Boot có thể tạo template.
5. Khi chưa có default `JmsListenerContainerFactory` thích hợp → Boot cung cấp factory để listener annotation dùng.

Các bước trên là **hành vi có điều kiện**, không phải cam kết mọi bean sẽ được tạo bằng cùng một tên/type trong mọi version. Nếu bạn khai báo **một bean ConnectionFactory riêng**, phần tự tạo provider connection của Boot có thể back off; template/listener của Boot vẫn có thể dùng bean bạn khai báo nếu autowiring không mơ hồ. Nếu tự khai báo `JmsTemplate`, Boot thường không ghi đè template đó. Khi có nhiều `ConnectionFactory` hoặc nhiều factories cho listener, dùng `@Qualifier`/tên rõ ràng.

### 10.1. Có thể custom Boot từng phần, không cần viết lại hết

Tình huống: cần chọn message converter khác nhưng muốn Boot tiếp tục quản lý broker/client/template:

~~~java
@Bean
org.springframework.jms.support.converter.MessageConverter
messageConverter() {
    return new org.springframework.jms.support.converter.SimpleMessageConverter();
}
~~~

Đây là snippet minh họa registration; `SimpleMessageConverter` đã là default thông thường nên đổi sang chính nó **không tạo tác dụng nghiệp vụ mới**. Khi dùng converter thực sự tùy biến như JSON converter, phải định nghĩa schema/type mapping, lỗi deserialize và interoperability. Boot có thể gắn bean converter vào những thành phần auto-configured theo điều kiện của phiên bản.

Tình huống: muốn thay đổi một listener factory nhưng giữ default Boot settings. Trên Boot 3.x dùng `DefaultJmsListenerContainerFactoryConfigurer` để áp dụng những thiết lập Boot có sẵn, sau đó tùy biến:

~~~java
@Configuration
class CustomListenerConfig {

    @Bean
    DefaultJmsListenerContainerFactory criticalQueueFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setConcurrency("2-5");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Snippet trên cần import:
- `org.springframework.context.annotation.Bean` và `Configuration`.
- `jakarta.jms.ConnectionFactory`.
- `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`.
- `org.springframework.boot.jms.ConnectionFactoryUnwrapper`.
- `org.springframework.jms.config.DefaultJmsListenerContainerFactory`.

Dùng với `@JmsListener(destination = "critical.orders", containerFactory = "criticalQueueFactory")` ở một bean listener. **Tên factory tự chọn** không tự thay default `jmsListenerContainerFactory` của Boot nếu bạn không chỉ định. `ConnectionFactoryUnwrapper.unwrapCaching` giữ cách Boot tránh dùng cache wrapper trực tiếp cho listener. Với phiên bản Boot khác, xác minh package/API thay vì copy mù.

### 10.2. Đọc Condition Evaluation Report

Khi “starter có rồi mà không thấy bean”, chạy ứng dụng Boot với debug để xem **positive/negative matches**:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Trong báo cáo, tìm nhóm auto-configuration liên quan `Artemis`, `Jms`, `JmsAnnotationDriven` và điều kiện `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`. Tên class cụ thể có thể khác giữa các release; giá trị của báo cáo là **lý do condition matched hoặc không matched**, không phải thuộc lòng tên auto-config class.

Trong production, không bật verbose debug logs vô hạn. Nếu có Actuator và cho phép exposure phù hợp, endpoint conditions/beans có thể hỗ trợ quan sát, nhưng đừng mở endpoint nhạy cảm công khai.

## 11. Cấu hình properties hay code: chọn theo phạm vi thay đổi

| Nhu cầu | Ưu tiên ở Boot | Khi nên tự khai báo bean |
| --- | --- | --- |
| Đổi Artemis broker URL/user/password | `spring.artemis.*` hoặc biến môi trường tương đương | Provider topology hoặc security config vượt scope properties |
| Chọn queue hay topic mặc định | `spring.jms.pub-sub-domain` | Ứng dụng đồng thời dùng queue và topic với chính sách khác nhau |
| Điều chỉnh cache session | `spring.jms.cache.session-cache-size` | Muốn kiểm soát pool/wrapper chi tiết theo profile |
| Điều chỉnh listener concurrency / ack / transaction | `spring.jms.listener.*` nếu phiên bản hỗ trợ | Cần factory riêng, policy riêng cho từng loại queue |
| JSON schema/message converter | Bean converter + cấu hình thích hợp | Cần converter phức tạp và mapping/versioning cụ thể |
| Nhiều brokers hoặc nhiều credentials | Cấu hình đa factory do ứng dụng sở hữu | Thường cần `@Qualifier`, nhiều template, nhiều listener factory |
| TLS/client failover provider-specific | Kiểm tra support của Boot properties + transport URI | Cần thư viện client hoặc builder/provider bean tùy chỉnh |
| XA/JTA và phối hợp resource | Phần hạ tầng JTA được chọn rõ | Cần cấu hình XA ConnectionFactory/transaction manager và bằng chứng tích hợp |

**Nguyên tắc cấu hình:** ứng dụng Boot nên bắt đầu từ properties + bean có mục tiêu rõ ràng. Định nghĩa lại toàn bộ `ConnectionFactory` hoặc `JmsTemplate` chỉ để đổi một endpoint thường khiến bạn vô tình bỏ mất cache, converter, retry/error handling hoặc điều kiện khác của auto-config.

## 12. ConnectionFactory trong application server, JNDI và multiple providers

Không phải ứng dụng nào cũng tạo Artemis client bằng `new ActiveMQConnectionFactory(...)`. Nếu chạy trong **Jakarta EE application server**, `ConnectionFactory` có thể được quản lý bởi container và tìm qua **JNDI**:

- Trong Spring thuần, có thể tự tạo `JndiObjectFactoryBean` hoặc lookup thích hợp, rồi inject `jakarta.jms.ConnectionFactory`.
- Trong Spring Boot 3.x, property `spring.jms.jndi-name` có thể được dùng để lookup JMS ConnectionFactory thay vì để Boot tạo provider CF từ URL (khi điều kiện môi trường đáp ứng).

**Tránh cấu hình mâu thuẫn:** đồng thời cấu hình JNDI factory, Artemis native factory và một custom provider factory mà không xác định bean nào là nguồn dùng cho template và listener. Với XA/JTA, native client đơn thuần và connection quản lý bởi application server có thể có semantics transaction khác nhau. Luôn kiểm chứng **actual bean graph**.

### Khi nhiều broker cùng xuất hiện

Ví dụ kết nối riêng tới broker “payments” và “notifications”:

~~~text
paymentsConnectionFactory
    ├─ paymentsJmsTemplate
    └─ paymentsListenerFactory

notificationsConnectionFactory
    ├─ notificationsJmsTemplate
    └─ notificationsListenerFactory
~~~

Ở đây **Spring Boot auto-config không thể tự đoán** queue nào thuộc broker nào. Dùng bean names, `@Qualifier`, cấu hình destination rõ, và `containerFactory` trong `@JmsListener`; có thể giữ auto-config cho một default factory nhưng nên kiểm soát toàn bộ routing có chủ đích.

Không chia sẻ `Session` hoặc `MessageProducer` từ JMS classic API giữa nhiều thread; dùng `JmsTemplate` hoặc tài nguyên được framework quản lý đúng lifetime.

## 13. Destination, pub-sub, converter và listener routing

### 13.1. Mặc định là queue, không phải topic

Ở ví dụ B, `spring.jms.pub-sub-domain=false` (default) làm cho tên `orders.inbox` được resolve theo **queue** trong template và default listener factory. Muốn topic, có thể bật `spring.jms.pub-sub-domain=true` khi **toàn bộ default flow** thực sự cần topic. Nếu một ứng dụng dùng cả hai, thiết kế **hai template/listener factories** với `setPubSubDomain(...)` tương ứng; thay đổi global property có thể làm hỏng đường queue cũ.

Tên destination không chứng minh broker đã provision xong; có provider tự tạo tài nguyên, có provider yêu cầu quyền và cấu hình trước. Lưu ý durable topic subscription còn cần client/subscription identity, retention và policy riêng.

### 13.2. MessageConverter ảnh hưởng dữ liệu, không thay network

`JmsTemplate.convertAndSend(...)` dùng converter để tạo JMS `Message` từ object Java; listener có thể chuyển payload ngược thành `String`/object. Khi chỉ gửi String, `SimpleMessageConverter` thường tạo `TextMessage`. Khi gửi POJO, **đừng giả định tự động thành JSON** mà chưa có JSON converter và type mapping rõ ràng.

Trong Spring thuần bạn tạo/đăng ký `MessageConverter` cho template và listener factory như cần thiết. Trong Boot, có thể đăng ký converter bean để auto-configured template/default listener sử dụng, nhưng custom factory/template do bạn tự tạo có thể cần tự gắn lại converter.

### 13.3. Listener container là thành phần có lifecycle riêng

Một `@JmsListener` hoạt động thông qua container quản lý consumer và connection; nó có thể bắt đầu khi context refresh, retry khi broker mất kết nối và dừng khi shutdown. Việc publisher gửi thành công khi startup không có nghĩa consumer đã sẵn sàng trong cùng thời điểm. Để kiểm tra readiness, quan sát listener container status, broker connections, queue depth và xử lý message thật.

## 14. Bảng kiểm thực nghiệm: chứng minh sự tương đương và khác biệt

Lần lượt thực hiện với **hai ứng dụng độc lập** từ ví dụ A/B và cùng broker/queue:

| Thử nghiệm | Spring thuần | Spring Boot | Điều cần thấy |
| --- | --- | --- | --- |
| Tắt broker trước startup | ConnectionFactory bean có thể tạo; listener có thể báo reconnect; send lỗi | Cũng có thể khởi tạo context nhưng send/listener lỗi tùy thời điểm kết nối | Bean tồn tại **khác** broker reachable |
| Broker chạy, queue hợp lệ | Gửi và listener nhận | Gửi và listener nhận | Bản chất JMS traffic giống nhau |
| Bỏ cấu hình ConnectionFactory ở A | Thiếu bean → wiring lỗi | B vẫn có thể tự tạo CF từ starter/properties | Khác biệt chủ sở hữu bean |
| Bỏ `@EnableJms` ở A | Annotated listener không được kích hoạt | B không cần khai báo `@EnableJms` riêng trong setup chuẩn | Khác biệt bootstrap hạ tầng listener |
| Bỏ listener factory ở A | Infrastructure thiếu default factory nếu không đăng ký cách khác | B có default factory auto-config khi đủ điều kiện | Khác biệt auto-registration |
| Ném exception trong handler | Local JMS transaction A rollback | Default Boot transactional factory rollback (nếu không override) | Kiểm tra redelivery/DLQ tùy broker |
| Đổi broker credentials | Sửa env/client bean của A | Sửa `SPRING_ARTEMIS_*`/properties của B | Hai cách inject cấu hình |
| Thêm custom `JmsTemplate` bean ở B | Không áp dụng Boot auto-config | Boot có thể back off template mặc định | Tự cấu hình có điều kiện |

**Thực hiện an toàn:** dùng queue test, broker test, message có `eventId` rõ, không thử lỗi bằng dữ liệu production. Mỗi thử nghiệm ghi lại classpath, cấu hình, stack trace, thời điểm listener nhận và message còn trong broker.

## 15. Debugging cụ thể từ triệu chứng tới nguyên nhân

| Triệu chứng | Nguồn gốc khả dĩ | Cách xác minh, không đoán |
| --- | --- | --- |
| `No qualifying bean of type 'jakarta.jms.ConnectionFactory'` | Thiếu provider bean ở Spring thuần; hoặc Boot auto-config không match vì thiếu starter/bean conflict | Kiểm tra dependency graph, bean definitions, condition report |
| `No qualifying bean of type 'JmsTemplate'` | Spring thuần chưa định nghĩa template; Boot không match điều kiện template | Kiểm tra `@Bean JmsTemplate` hoặc Boot report |
| `No bean named 'jmsListenerContainerFactory'` | Annotation infrastructure không có default container factory phù hợp | Kiểm tra bean name, `@EnableJms`, `containerFactory` |
| Boot khởi động nhưng listener không xử lý | Bean scan thiếu, sai destination, broker unreachable, ACL, selector, topic/queue mismatch | Đọc logs container + broker, xác nhận destination/consumer count |
| `ClassNotFoundException: javax.jms...` hoặc `jakarta.jms...` | Trộn client API JMS cũ/mới | Xem runtimeClasspath; chọn Artemis Jakarta client phù hợp Spring 6 |
| `UnknownHostException`, connect timeout, refused | URL/DNS/firewall/acceptor sai hoặc broker chưa chạy | Kiểm tra endpoint thật, listener trên broker và TCP/TLS |
| `JMSSecurityException` | User/password/roles/ACL sai | Kiểm tra secret binding và broker auth logs, không in credential |
| Không nhận dù gửi thành công | Sai queue/topic, consumer chưa start, listener khác nhận, TTL hết, broker route khác | Kiểm tra queue depth, subscriptions, routing type, JMSDestination |
| Message bị xử lý hai lần khi retry | JMS local transaction retry/redelivery hoặc publisher send lặp | Stable event ID, dedupe unique constraint, transaction + DLQ |
| Boot mất cấu hình sau khi thêm custom bean | Bean mới làm back off auto-config, hoặc @Primary/@Qualifier đổi wiring | Condition report, bean graph và hiệu lực properties |
| Listener nhiều thread hơn dự kiến | `concurrency`/provider dispatch semantics | Xem factory thực dùng và số consumer thực trên broker |
| Đổi `spring.jms.cache.*` không đổi pool | Cache session khác với physical connection pool | Kiểm tra wrapper/pool class thật và metrics |

**Nên bắt đầu bằng câu hỏi kỹ thuật cụ thể:** “Container có bean ConnectionFactory nào? Class của nó là gì? Bean factory nào đã được chọn cho listener? Broker có kết nối thật không?”. Trả lời từng câu bằng runtime evidence rồi mới thay cấu hình.

## 16. Các kiểu override Boot thường gặp

### 16.1. Tự khai báo ConnectionFactory trong ứng dụng Boot

~~~java
@Configuration
class ExternalJmsConfiguration {
    @Bean(destroyMethod = "close")
    ActiveMQConnectionFactory connectionFactory() {
        return new ActiveMQConnectionFactory(
                "tcp://localhost:61616", "demo", readSecret());
    }

    private String readSecret() {
        String password = System.getenv("JMS_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalStateException("JMS_PASSWORD required");
        }
        return password;
    }
}
~~~

Snippet này cần import `@Configuration`, `@Bean` và `ActiveMQConnectionFactory` như ví dụ A. Nếu đặt vào ứng dụng Boot, **bean provider ConnectionFactory tự viết** có thể khiến Artemis auto-config không tạo factory như trước. Tùy cách định nghĩa/names, Boot vẫn có thể tự tạo `JmsTemplate` và listener factory **dựa vào bean bạn tạo**. Không mong `spring.artemis.broker-url` tự override constructor hard-coded: code và properties nay có **hai nguồn cấu hình**, trong đó custom bean quyết định client thực.

Cách sửa thường hợp lý hơn nếu chỉ muốn đổi host/user là **bỏ custom ConnectionFactory** và dùng `spring.artemis.*`. Chỉ giữ bean riêng khi cần nhiều brokers, custom TLS/failover/provider options, JNDI hoặc các chính sách mà auto-config không biểu diễn đủ.

### 16.2. Tự khai báo JmsTemplate

~~~java
@Bean
JmsTemplate specialTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setPubSubDomain(true);
    return template;
}
~~~

Nếu đây là bean `JmsTemplate` duy nhất, có thể làm Boot không tạo template tự động như mặc định. Lúc đó app dùng template do bạn tạo; các thuộc tính `spring.jms.template.*` sẽ **không tự bảo đảm** được áp dụng cho bean ấy. Nếu muốn một template queue mặc định và một template topic riêng, đặt tên bean rõ, dùng `@Qualifier` ở chỗ inject, và kiểm tra conditional auto-config/`@Primary`.

### 16.3. Tự khai báo listener factory

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-4");
    return factory;
}
~~~

Với bean **đúng tên default**, Boot có thể không tạo default factory của nó. Trường hợp đó, listener sẽ dùng cấu hình bạn viết; nếu quên `sessionTransacted` hay `MessageConverter`, semantics có thể khác trước. Với custom factory **tên riêng**, dùng `@JmsListener(containerFactory="...")` để chọn chính xác. Khi muốn kế thừa logic Boot, dùng `DefaultJmsListenerContainerFactoryConfigurer` thay vì tự gán từng thuộc tính dễ bỏ sót.

## 17. Chiến lược di chuyển Spring thuần ↔ Spring Boot

### 17.1. Từ Spring thuần sang Boot

1. **Chụp cấu hình đang hoạt động:** provider/version, URL/TLS, security, destination resolver, pub-sub, converters, connection caching/pooling, transaction, concurrency, retries và DLQ.
2. **Thêm Boot starter đúng provider** và dùng dependency management. Loại dependency Spring/provider phiên bản trùng, nhưng chỉ sau khi xem dependency graph.
3. **Di chuyển các thuộc tính đơn giản** sang `spring.artemis.*`, `spring.jms.*` và environment/secret manager. Không ghi secrets vào source control.
4. **Loại bean trùng có thể thay bằng auto-config**: thường là `ConnectionFactory`, `JmsTemplate` và default listener factory; giữ custom bean thực sự có giá trị.
5. **Xem condition report + bean graph** để biết Boot đang tạo gì và điểm nào back off; đừng chỉ dựa vào app khởi động.
6. **Đối chiếu transaction defaults**: nếu cấu hình cũ là AUTO_ACK nhưng Boot default transacted, hành vi khi listener lỗi sẽ thay đổi — đây là thay đổi nghiệp vụ cần kiểm thử.
7. **Chạy integration tests với broker thật**: gửi/nhận, queue/topic, retry/DLQ, restart broker, idempotency, redelivery và shutdown.

### 17.2. Từ Boot sang Spring thuần

1. Liệt kê những bean đã **được Boot auto-config** khi chạy: `ConnectionFactory` (native/wrapper), `JmsTemplate`, `JmsListenerContainerFactory`, converters/resolvers.
2. Tạo lại **rõ ràng** các bean cần thiết trong `@Configuration` và `@EnableJms`; ghi tên/qualifier của factory.
3. Chuyển `spring.artemis.*` và `spring.jms.*` thành cơ chế property binding phù hợp môi trường Spring thuần; chúng không tự có nghĩa nếu không còn Boot binder/configurer.
4. Tạo đúng classpath (Spring 6/Jakarta provider) và quản lý dependency versions có kiểm chứng.
5. So sánh **ack/transaction, cache/pool, listener recovery, concurrency** trước khi coi migration hoàn thành. Dùng test broker và phép thử lỗi giống Boot.

**Cảnh báo nguồn cấu hình:** giá trị `spring.artemis.broker-url` đặt trong một ứng dụng **Spring thuần** không tự tạo Artemis ConnectionFactory chỉ vì tên property “có vẻ đúng Spring”. Bạn phải có code/binder đọc property đó và tạo bean. Ngược lại, code `@Bean ActiveMQConnectionFactory` tự tạo trong Boot có thể không nghe `spring.artemis.*` nếu bạn không truyền values vào constructor.

## 18. Bài tập kiểm chứng hiểu bản chất

**Bài 1 — Vẽ bean graph:** Với ví dụ A, tự vẽ `ConnectionFactory → JmsTemplate` và `ConnectionFactory → jmsListenerContainerFactory → @JmsListener`. Liệt kê từng `@Bean` cần khai báo và lý do.

**Bài 2 — Bỏ từng bean:** Trong Spring thuần, lần lượt bỏ `JmsTemplate`, `ConnectionFactory` và `jmsListenerContainerFactory` ở môi trường thử nghiệm. Đọc exception và giải thích đúng bean đang thiếu.

**Bài 3 — Chứng minh Boot auto-config:** Chạy ví dụ B có `spring-boot-starter-artemis`, in condition report bằng `--debug`. Kiểm tra runtime bean types, chứng minh cả template và listener factory được Boot cấu hình.

**Bài 4 — Thử backing off:** Thêm một custom `JmsTemplate` vào B, quan sát bean types và `spring.jms.template.*` có còn tác dụng lên template custom không. Không phỏng đoán trước; dùng condition report và hành vi gửi thực tế.

**Bài 5 — So sánh queue/topic:** Tạo queue và topic test riêng; thử `pubSubDomain` mặc định và custom factories. Quan sát broker routing/subscription thay vì chỉ đọc tên destination.

**Bài 6 — Cố tình lỗi listener:** Ném exception trong `@JmsListener` để quan sát redelivery dưới local JMS transaction. So sánh nếu factory Spring thuần không bật `sessionTransacted`; giải thích tại sao Boot default có thể khác.

**Bài 7 — Broker restart:** Khi broker unavailable, theo dõi startup, reconnect logs, producer send exception, listener recovery và thời gian nhận lại. Chứng minh **bean khởi tạo được** không đồng nghĩa **broker kết nối được**.

**Bài 8 — Phân biệt cache/pool:** Gửi nhiều message đồng thời trong test; quan sát cache session, số consumer, số physical connection. Thay `session-cache-size` và so sánh với một pool có `max-connections` để hiểu hai tham số đo gì.

**Bài 9 — Đa broker:** Thiết kế hai `ConnectionFactory` và hai listener factories, dùng qualifier tường minh; thử injected bean ambiguity rồi giải quyết bằng bean names. Không dùng một `@Primary` ngầm làm cơ chế routing nghiệp vụ.

**Bài 10 — Kiểm thử migration:** Thực hiện cùng 5 phép thử (send, listener receive, exception rollback, restart broker, malformed payload) ở cả ứng dụng Spring thuần và Boot. Ghi cấu hình ứng dụng/broker và kết quả thực tế; kết luận khác biệt nào đến từ auto-configuration, khác biệt nào đến từ bạn đã chọn setting khác.

## 19. Checklist hoàn tất thiết lập kết nối

- [ ] Xác định đúng **JMS provider** và dependency Jakarta tương thích Spring 6+/Boot 3+.
- [ ] Biết broker chạy ngoài ứng dụng hay embedded; kiểm tra URL, DNS, port, TLS, credential và ACL.
- [ ] Có thể chỉ ra **bean ConnectionFactory đang dùng**, nguồn tạo ra bean đó và native/wrapper thực tế.
- [ ] Có thể giải thích vì sao Spring thuần cần cấu hình `@Bean`/`@EnableJms` còn Boot có thể cung cấp chúng theo điều kiện.
- [ ] Biết khi nào Boot auto-config **back off** và vì sao custom bean có thể bỏ qua `spring.jms.*`.
- [ ] Có `JmsTemplate` cho publisher và factory/listener container đúng tên cho `@JmsListener`.
- [ ] Thống nhất queue/topic và cấu hình resolver, converter cùng destination broker.
- [ ] Xác minh default listener transaction/ack trên **runtime thực**; thử exception/redelivery và hiểu giới hạn khi DB transaction độc lập.
- [ ] Có cơ chế caching/pooling phù hợp, phân biệt session cache size với pool max connections.
- [ ] Có log/metrics/health để biết kết nối thật, queue depth, listener hoạt động, lỗi auth và retry/DLQ.
- [ ] Kiểm thử ít nhất một vòng gửi/nhận và một kịch bản broker outage, không dựa vào việc startup thành công.

**Năng lực cần đạt:** Bạn có thể lấy cùng một yêu cầu “gửi và nhận message từ một queue” rồi chủ động **lắp đủ cấu hình trong Spring Framework thuần**, hoặc **giải thích chính xác bean nào Spring Boot tự cấu hình và khi nào nó không được tạo**, đồng thời kiểm chứng connection, listener và transaction bằng hệ thống thực.

## Tài liệu chính thức để đối chiếu

1. [Spring Framework Reference — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@EnableJms`, default `jmsListenerContainerFactory`, `@JmsListener`.
2. [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, `CachingConnectionFactory`, destination converter, transaction.
3. [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener container lifecycle, `sessionTransacted`, reliability.
4. [Spring Boot 3.4 Reference — JMS](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html): cơ chế Artemis auto-configuration, connection caching/pooling, JNDI, template/listener factory và transactional defaults (đối chiếu với Boot 3.3 nếu dùng ví dụ).
5. [Spring Boot 3.3 Reference — JMS](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html): API/properties tương ứng nhánh 3.3.
6. [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): ứng dụng Boot gửi/nhận đơn giản, không cần tự tạo `ConnectionFactory` và `JmsTemplate`.
7. [Apache ActiveMQ Artemis — Using JMS](https://artemis.apache.org/components/artemis/documentation/latest/using-jms): provider, transport và destination behavior.
8. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): hợp đồng JMS API, session, acknowledgment và transaction.

**Giới hạn áp dụng:** Các settings đặc thù broker (authentication/TLS, address-routing, auto-create, redelivery, DLQ, HA) cần đọc **tài liệu của provider và bản broker đang chạy**, không suy ra chỉ từ Spring auto-configuration.