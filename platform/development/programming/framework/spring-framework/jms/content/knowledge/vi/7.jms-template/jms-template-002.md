# Cấu hình ConnectionFactory và destination mặc định cho JmsTemplate

## 1. Hai cấu hình có vai trò khác nhau

Trong Spring JMS, **`JmsTemplate`** là đối tượng hỗ trợ gửi và nhận message đồng bộ. Để hoạt động, nó cần một **`jakarta.jms.ConnectionFactory`**. Ngoài ra, ứng dụng có thể cấu hình một **destination mặc định** để gọi những phương thức không truyền destination.

```text
Spring Application
       |
       v
   JmsTemplate  --------------------------+
       |                                  |
       | ConnectionFactory                 | Destination mặc định
       | (kết nối đến broker)              | (ví dụ orders.created)
       v                                  v
JMS Connection/Session  ------------>  Queue / Topic
       |                                  |
       +-------- producer/consumer -------+
```

Cần phân biệt:

- **ConnectionFactory** trả lời câu hỏi: *Làm thế nào để ứng dụng kết nối đến JMS provider?* Nó liên quan broker endpoint, xác thực, TLS, connection/session lifecycle, caching và có thể là transaction.
- **Destination** trả lời câu hỏi: *Message đi đến Queue hoặc Topic nào?* Nó có thể là tên `String` được Spring resolve hoặc một object `jakarta.jms.Destination`.
- **Default destination** là **cấu hình thuộc chính đối tượng `JmsTemplate`**, dùng khi method không nhận đối số destination. Nó **không phải** destination mặc định toàn broker, không tạo một Queue/Topic đặc biệt và không gán địa chỉ mặc định cho mọi listener.

Ví dụ:

```java
jmsTemplate.convertAndSend("ORDER-001");
```

Chỉ hoạt động khi chính `jmsTemplate` đã có default destination; payload `"ORDER-001"` là **nội dung message**. Ngược lại:

```java
jmsTemplate.convertAndSend("orders.audit", "AUDIT-001");
```

Đối số thứ nhất là destination tường minh `"orders.audit"`, đối số thứ hai mới là payload. Lệnh này **không dùng** default destination dù template đã cấu hình.

## 2. ConnectionFactory: tạo, lấy và đưa vào JmsTemplate

### 2.1. Interface và nguồn cấu hình

Spring Framework 6/Spring Boot 3 dùng interface **`jakarta.jms.ConnectionFactory`**. Đây là API chuẩn của Jakarta Messaging; instance do một JMS provider hoặc container quản lý cung cấp. Spring không thể tạo connection đến broker nếu không có factory phù hợp.

Các cách thường gặp để có factory:

| Môi trường | Nguồn `ConnectionFactory` | Ví dụ |
| --- | --- | --- |
| Spring Boot kết nối broker bên ngoài | Auto-configuration dựa trên JMS starter và thuộc tính provider | ActiveMQ Artemis với `spring-boot-starter-artemis` |
| Spring Framework cấu hình thủ công | Tự khai báo bean factory đã được cấu hình bằng API vendor | Một `ActiveMQConnectionFactory` phù hợp Jakarta JMS |
| Application server quản lý JMS | Tra cứu JNDI để nhận managed factory | `spring.jms.jndi-name` hoặc `JndiLocatorDelegate` |
| Test | Factory từ broker/test environment hoặc test double của lớp bao JMS | Broker tạm thời trong integration test |

**Cấu hình broker không nằm trong `setDefaultDestinationName`**. Nếu factory chỉ tới sai broker, việc đặt tên Queue đúng không giải quyết được lỗi kết nối. Tương tự, một factory dùng đúng broker cũng không thay thế việc chọn destination khi gửi.

### 2.2. Khai báo JmsTemplate trong Spring Framework

Trong một ứng dụng đã có bean `ConnectionFactory`, có thể khai báo:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsTemplateConfig {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDefaultDestinationName("orders.created");
        template.setPubSubDomain(false); // resolve String thành Queue
        return template;
    }
}
```

Lưu ý:

1. Spring inject bean `ConnectionFactory` vào phương thức `@Bean`. Mẫu này **giả định factory đã tồn tại**; nếu không, Spring báo lỗi dependency khi khởi động.
2. `new JmsTemplate(connectionFactory)` và `template.setConnectionFactory(connectionFactory)` là hai cách cung cấp factory. Không cần gọi cả hai.
3. `setDefaultDestinationName("orders.created")` thiết lập tên destination dùng cho các phương thức **không truyền đích**.
4. `setPubSubDomain(false)` yêu cầu resolver động xem tên đó là **Queue** (mặc định của Spring là Queue). Nếu dùng Topic và resolver động, đặt `true`.
5. Sau khi cấu hình, `JmsTemplate` được thiết kế **thread-safe** và thường nên dùng như **singleton bean**. Không tự đổi factory hoặc default destination trên một singleton đang phục vụ nhiều request để chuyển đích theo từng request.

Phương thức này không yêu cầu tự tạo `Connection`/`Session`: `JmsTemplate` làm việc với resource theo lifecycle Spring JMS và xử lý chuyển đổi exception. Vì vậy producer/service có thể inject bean `JmsTemplate` để tái sử dụng.

### 2.3. Managed factory từ JNDI

Trong application server có factory đã bind vào JNDI, có thể để Spring Boot tìm qua:

```yaml
spring:
  jms:
    jndi-name: "java:comp/env/jms/OrdersCF"
```

Hoặc cấu hình Spring thuần để lookup `jakarta.jms.ConnectionFactory`, sau đó truyền factory vào `JmsTemplate` như mục 2.2. Cấu hình JNDI này **chọn factory**, không đặt default destination; muốn gửi không truyền đích thì phải cấu hình thêm tên/đối tượng destination mặc định.

Lưu ý môi trường chạy ngoài application server thường **không có** `java:comp/env` nếu chưa chủ động cấu hình JNDI provider/binding.

## 3. Hai cách thiết lập destination mặc định

`JmsTemplate` hỗ trợ hai kiểu cấu hình cho cùng mục đích; thường chọn **một** cách:

### Cách A — `setDefaultDestinationName(String)`

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDefaultDestinationName("orders.created");
```

Khi gọi `send(MessageCreator)`, `convertAndSend(Object)`, `receive()` hoặc `receiveAndConvert()`, Spring lấy tên `"orders.created"` và gọi `DestinationResolver` để resolve. Với `DynamicDestinationResolver` mặc định, `Session.createQueue("orders.created")` thường được dùng nếu template ở Queue domain.

Đây là cách tiện dụng khi đã biết tên destination và broker cho phép resolve nó. **Resolve dynamic destination không có nghĩa broker nhất thiết tự tạo Queue**: provisioning và auto-create policy tùy provider.

### Cách B — `setDefaultDestination(Destination)`

```java
import jakarta.jms.Destination;
import org.springframework.jms.core.JmsTemplate;

// Giả định destination là object hợp lệ do JMS provider cấp.
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDefaultDestination(destination);
```

Cách này nhận trực tiếp object `jakarta.jms.Destination`, ví dụ `Queue` hoặc `Topic` đã được inject từ JNDI/container. Bạn không phải resolve lại String name cho các lệnh sử dụng mặc định.

**Đừng khởi tạo `new Destination()`**: `Destination` là interface. Object thật do provider tạo hoặc được lấy từ resource quản lý. Nếu cần, có thể dùng một `Queue` bean hợp lệ:

```java
@Bean
JmsTemplate ordersTemplate(
        ConnectionFactory connectionFactory,
        @Qualifier("ordersQueue") jakarta.jms.Queue ordersQueue) {
    var template = new JmsTemplate(connectionFactory);
    template.setDefaultDestination(ordersQueue);
    return template;
}
```

Đây là **đoạn bên trong class `@Configuration`**; cần import `@Bean`, `@Qualifier`, `ConnectionFactory`, `JmsTemplate` và có sẵn bean `ordersQueue`. Nếu provider không tương thích object destination với connection factory đang dùng, gửi message có thể thất bại; không nên lấy Queue object của broker A rồi dùng connection factory của broker B.

### So sánh hai phương án

| Tiêu chí | Default destination name | Default Destination object |
| --- | --- | --- |
| Đầu vào | `String` | `jakarta.jms.Destination` |
| API cấu hình | `setDefaultDestinationName(...)` | `setDefaultDestination(...)` |
| Resolution | Thông qua `DestinationResolver` | Object đã có sẵn |
| Queue/Topic domain khi dùng name | Phụ thuộc `pubSubDomain` và resolver | Kiểu thực tế của object `Queue`/`Topic` |
| Thích hợp | Broker/client resolve destination bằng tên | Resource được container/provisioning quản lý, inject sẵn |
| Sai sót thường gặp | Sai tên, sai Queue/Topic, policy không cho tạo | Lấy object không đúng provider hoặc binding |

Không cần đặt cả hai thuộc tính chỉ để dự phòng. Hãy chọn một nguồn sự thật cho đích mặc định.

## 4. Những phương thức nào dùng default destination?

Giả sử:

```java
JmsTemplate t = new JmsTemplate(connectionFactory);
t.setDefaultDestinationName("orders.created");
```

| Lệnh gọi | Destination thực sự được chọn | Diễn giải |
| --- | --- | --- |
| `t.send(session -> session.createTextMessage("A"))` | `orders.created` | Dùng default destination. |
| `t.convertAndSend("A")` | `orders.created` | Payload là một `String`, `SimpleMessageConverter` thường tạo `TextMessage`. |
| `t.convertAndSend("B", message -> message)` | `orders.created` | Overload có `MessagePostProcessor` nhưng không truyền destination. |
| `t.receive()` | `orders.created` | Nhận đồng bộ từ default destination. |
| `t.receiveAndConvert()` | `orders.created` | Nhận đồng bộ và chuyển đổi body. |
| `t.send("orders.audit", creator)` | `orders.audit` | Destination tường minh ghi đè lựa chọn mặc định cho lần gọi này. |
| `t.convertAndSend("orders.audit", "B")` | `orders.audit` | Tham số String đầu là destination, thứ hai là payload. |
| `t.receive("orders.audit")` | `orders.audit` | Nhận từ destination tường minh. |
| `t.convertAndSend(destinationObject, "B")` | `destinationObject` | Object `Destination` được truyền trực tiếp. |

Nếu không có default destination, phương thức không có destination sẽ báo lỗi (thường là `IllegalStateException` từ template trước khi gửi). Không nên “sửa” bằng cách nhét payload vào overload hai tham số hoặc đặt một tên giả định mà broker không có.

**Quan trọng:** `@JmsListener(destination = "orders.created")` **không** tự lấy default destination của `JmsTemplate`; listener được cấu hình bởi **listener container factory** và annotation riêng. Ngược lại, thay `JmsTemplate` default destination không làm listener đang nghe Queue khác tự chuyển sang đích mới.

## 5. Tên destination được resolve như thế nào?

Mặc định, `JmsTemplate` thường dùng `DynamicDestinationResolver`. Khi nhận tên `String`, nó dựa vào domain để tạo object `Queue` hoặc `Topic` phù hợp với `Session`:

```text
defaultDestinationName = "orders.created"
pubSubDomain = false
    -> resolve Queue("orders.created")

defaultDestinationName = "orders.created"
pubSubDomain = true
    -> resolve Topic("orders.created")
```

**Queue và Topic là hai domain khác nhau**. Một tên giống nhau không có nghĩa hai destination là cùng object. Nếu producer gửi Queue mà consumer nghe Topic cùng tên, chúng thường không chia sẻ message.

Nếu destination thực tế được quản lý qua JNDI, có thể cấu hình:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setResourceRef(true);
resolver.setFallbackToDynamicDestination(false);

JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDestinationResolver(resolver);
template.setDefaultDestinationName("jms/OrdersQueue");
```

Đây là đoạn cấu hình **nằm trong một method đã có `ConnectionFactory connectionFactory`**. Khi dùng `resourceRef=true`, Spring tra `java:comp/env/jms/OrdersQueue` trong container. Tắt fallback dynamic giúp tên JNDI sai không âm thầm được diễn giải thành tên dynamic khác. Nếu không cần JNDI lookup cho destination thì dùng resolver mặc định.

Cấu hình destination resolver của **`JmsTemplate`** riêng với resolver của **listener container**. Nếu hai bên dựa vào resource JNDI, cả hai cần được cấu hình tương thích hoặc dùng các object destination được inject đúng.

### Phân biệt ba kiểu “mặc định”

- `ConnectionFactory` bean mặc định: object mà Spring sẽ inject khi chỉ có một bean phù hợp (hoặc được đánh dấu `@Primary`).
- `JmsTemplate.defaultDestinationName`: đích được chọn cho **các method không nhận destination** trên template ấy.
- `@JmsListener(destination=...)`: đích cụ thể của listener; nó không suy ra từ default destination của template.

Không lấy khái niệm “default bean” của Spring để suy ra “default destination” của JMS.

## 6. Cấu hình bằng Spring Boot

Với Spring Boot 3 và JMS starter phù hợp, Boot có thể tự tạo bean `ConnectionFactory` và `JmsTemplate`. Thông thường bạn chỉ cần khai báo cấu hình, inject `JmsTemplate` và gửi message.

Ví dụ với **Apache ActiveMQ Artemis**:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
    template:
      default-destination: orders.created
      receive-timeout: 2s
```

Giải thích từng thuộc tính:

| Thuộc tính | Mục đích |
| --- | --- |
| `spring.artemis.mode=native` | Kết nối đến broker Artemis chạy ngoài ứng dụng. |
| `spring.artemis.broker-url` | Broker endpoint do provider dùng, ví dụ `tcp://localhost:61616`. |
| `spring.artemis.user/password` | Tài khoản demo của broker; production nên lấy từ secret/config an toàn. |
| `spring.jms.pub-sub-domain=false` | Cấu hình mặc định hướng tới Queue. Với Topic, cần điều chỉnh đồng bộ cho sender/listener. |
| `spring.jms.template.default-destination` | Tên đích cho các phương thức không truyền destination của auto-configured `JmsTemplate`. |
| `spring.jms.template.receive-timeout` | Giới hạn thời gian chờ khi gọi `receive()`/`receiveAndConvert()` đồng bộ. |

Cần phân biệt **Spring Boot property** `spring.jms.template.default-destination` với phương thức Java **`setDefaultDestinationName`**: chúng đặt cùng loại cấu hình khi Boot tạo template. Nếu bạn tự khai báo một bean `JmsTemplate` tùy chỉnh, cần tự cấu hình cho bean đó hoặc dùng các helper configuration phù hợp; đừng giả định mọi thuộc tính Boot sẽ tự áp dụng lên object do bạn `new` thủ công.

### Caching ConnectionFactory

Spring Boot có thể bọc native `ConnectionFactory` bằng `CachingConnectionFactory` với các thuộc tính `spring.jms.cache.*`. Caching factory giảm chi phí liên tục tạo session/producer trong một số workload; bản thân default destination không tác động chính sách caching.

Nếu factory do application server đã quản lý pooling hoặc XA, hãy xem xét transaction và lifecycle trước khi thêm lớp cache/pool nữa. Không tự gọi `close()` trên managed `ConnectionFactory`: đóng connection/session mà mã ứng dụng tự mở theo hợp đồng JMS, hoặc để `JmsTemplate`/container quản lý.

## 7. Demo đầy đủ: một default Queue và một Queue tường minh

Ví dụ này dùng **Java 17, Spring Boot 3.3.x, Spring JMS và Artemis broker ngoài ứng dụng**. Nó kiểm chứng ba cách gọi `JmsTemplate`:

1. `convertAndSend(payload)` tới Queue mặc định `orders.created`.
2. `send(creator)` tới **cùng Queue mặc định**.
3. `convertAndSend("orders.audit", payload)` tới **Queue tường minh khác**.

Hai listener xác định destination riêng trong `@JmsListener`.

### 7.1. Chuẩn bị broker

Cài Docker và chạy một Artemis thử nghiệm:

```bash
docker run --detach --rm --name jms-template-demo -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

Lệnh phù hợp cả PowerShell khi viết một dòng. Đợi broker khởi động và cho phép truy cập cổng 61616 trước khi chạy Spring. Broker dùng cho ví dụ cần có/cho phép tạo hai Queue `orders.created` và `orders.audit` (một số cấu hình Artemis bật auto-create address/queue; trên broker khác có thể phải provision trước). Sau khi học xong, dừng bằng `docker stop jms-template-demo`.

### 7.2. Tạo dự án Gradle

Tệp `settings.gradle`:

```groovy
rootProject.name = 'jms-default-destination-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
    template:
      default-destination: orders.created
      receive-timeout: 2s
```

Tệp `src/main/java/demo/jms/JmsDefaultsApplication.java`:

```java
package demo.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsDefaultsApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsDefaultsApplication.class, args);
    }

    @Bean
    ApplicationRunner sendSamples(JmsTemplate jmsTemplate) {
        return args -> {
            // Dùng default destination: orders.created.
            jmsTemplate.convertAndSend("ORDER-1");

            // Vẫn dùng default destination: orders.created.
            jmsTemplate.send(session ->
                    session.createTextMessage("ORDER-2"));

            // Chọn destination tường minh, bỏ qua default.
            jmsTemplate.convertAndSend(
                    "orders.audit",
                    "AUDIT-1"
            );
        };
    }
}

@Component
class DemoListeners {

    @JmsListener(destination = "orders.created")
    public void onOrder(String payload) {
        System.out.println("ORDER: " + payload);
    }

    @JmsListener(destination = "orders.audit")
    public void onAudit(String payload) {
        System.out.println("AUDIT: " + payload);
    }
}
```

**Đọc code theo thứ tự:**

1. Spring Boot cấu hình `ConnectionFactory` từ Artemis starter và `spring.artemis.*`.
2. Boot tạo `JmsTemplate` và gắn `default-destination: orders.created`.
3. `ApplicationRunner` gửi hai message vào `orders.created`; lần gửi thứ ba dùng `orders.audit` tường minh.
4. Hai `@JmsListener` nghe đúng Queue riêng. `SimpleMessageConverter` thông thường chuyển `String` thành `TextMessage` khi gửi, và từ `TextMessage` thành `String` khi truyền vào handler.
5. Không có method `@JmsListener` nào dùng default destination của `JmsTemplate`; tên Queue listener được ghi trực tiếp trong annotation.

### 7.3. Chạy, output và giới hạn quan sát

Cần Gradle phù hợp với Spring Boot 3.3.x và JDK 17+, rồi chạy:

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper, Linux/macOS dùng `./gradlew bootRun`, Windows dùng `gradlew.bat bootRun`.

Trong một lần chạy sạch, broker hoạt động và các handler không lỗi, các dòng ứng dụng tự in gồm:

```text
ORDER: ORDER-1
ORDER: ORDER-2
AUDIT: AUDIT-1
```

**Thứ tự giữa các dòng không được bảo đảm** vì các listener chạy bất đồng bộ; đoạn trên là một thứ tự có thể xuất hiện, không phải một thứ tự được framework cam kết. Nếu broker giữ message chưa xử lý từ lần chạy trước, hoặc producer/consumer có retry, số dòng log có thể khác. Có thể xóa/tạo broker demo mới để quan sát sạch.

Nếu bỏ `spring.jms.template.default-destination` mà vẫn gọi `convertAndSend("ORDER-1")`, lệnh không còn biết đích và sẽ báo lỗi. Tuy vậy `convertAndSend("orders.audit", "AUDIT-1")` vẫn có thể hoạt động nếu factory/broker sẵn sàng, vì destination đã được truyền tường minh.

## 8. Cấu hình thủ công thay cho auto-configured JmsTemplate

Trong ứng dụng Spring Framework thuần hoặc khi cần cấu hình sâu hơn, khai báo bean theo kiểu Java. Ví dụ đầy đủ sau **là phương án thay thế cách Boot tự tạo template ở mục 7**, không thêm vào demo đó nếu chưa quyết định rõ cơ chế override:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class ManualJmsTemplateConfig {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate();
        template.setConnectionFactory(connectionFactory);
        template.setDefaultDestinationName("orders.created");
        template.setPubSubDomain(false);
        template.setReceiveTimeout(2_000);
        return template;
    }
}
```

Kết quả về mặt destination và cách gọi no-argument tương tự demo ở trên khi các bean/provider tương thích. Khác biệt là bạn **tự chịu trách nhiệm** cho các thuộc tính `JmsTemplate`, thay vì dựa vào `spring.jms.template.*` của auto-config. Không nên đồng thời có hai bean cùng tên `jmsTemplate` trừ khi thực sự có cấu hình bean override đã được kiểm soát.

### Nhiều template cho nhiều destination

Một ứng dụng có thể gửi tới nhiều Queue/Topic. Thay vì sửa `setDefaultDestinationName` của một singleton theo từng request, bạn có thể:

- Gọi overload có destination tường minh trên một template khi các đích dùng cùng provider và cùng domain.
- Hoặc định nghĩa **nhiều template có tên bean rõ ràng**, mỗi template có một default destination cố định; inject qua `@Qualifier`.

Ví dụ trong một class `@Configuration` đã có `ConnectionFactory`:

```java
@Bean("orderTemplate")
JmsTemplate orderTemplate(ConnectionFactory cf) {
    var template = new JmsTemplate(cf);
    template.setDefaultDestinationName("orders.created");
    return template;
}

@Bean("auditTemplate")
JmsTemplate auditTemplate(ConnectionFactory cf) {
    var template = new JmsTemplate(cf);
    template.setDefaultDestinationName("orders.audit");
    return template;
}
```

Với hai bean cùng kiểu `JmsTemplate`, injection không chỉ rõ tên có thể gây **`NoUniqueBeanDefinitionException`**. Sử dụng:

```java
public OrderPublisher(
        @Qualifier("orderTemplate") JmsTemplate orderTemplate) {
    this.orderTemplate = orderTemplate;
}
```

Đây là constructor **minh họa nằm trong class `OrderPublisher` có field `JmsTemplate orderTemplate`**, cần import `@Qualifier` và `JmsTemplate`. Nếu các template dùng **hai broker khác nhau**, hãy gắn mỗi template với đúng `ConnectionFactory` tương ứng; chỉ đổi default destination không thể chuyển kết nối sang broker khác.

## 9. Queue, Topic và domain cấu hình

`JmsTemplate` mặc định dùng Point-to-Point domain (**Queue**). Khi sử dụng tên `String` và `DynamicDestinationResolver`, `setPubSubDomain(true)` chuyển việc resolve sang **Topic**:

```java
JmsTemplate topicPublisher = new JmsTemplate(connectionFactory);
topicPublisher.setPubSubDomain(true);
topicPublisher.setDefaultDestinationName("orders.events");

topicPublisher.convertAndSend("ORDER_CREATED");
```

Đây là ví dụ **trong một method có `ConnectionFactory connectionFactory`**, không tự độc lập chạy nếu chưa có provider. Với một Topic, mỗi subscription phù hợp nhận phần message của riêng nó; với Queue, các consumer cạnh tranh trên một luồng công việc. **Default destination không thay đổi quy tắc phân phối của Queue/Topic.**

Nếu dùng `@JmsListener` cho Topic, phải bảo đảm listener container factory cũng được cấu hình `pubSubDomain=true`. Chỉ chỉnh template gửi thành Topic rồi để listener mặc định nghe Queue cùng tên là lỗi thường gặp.

`spring.jms.pub-sub-domain=true` trong Spring Boot có thể cấu hình domain mặc định cho hạ tầng JMS được tự tạo; khi trộn Queue và Topic trong cùng ứng dụng, nên có template và listener factories phân biệt rõ domain để không gửi/nhận nhầm.

### Destination tường minh thắng default destination

```java
topicPublisher.convertAndSend("orders.events", "E1");
topicPublisher.convertAndSend("shipping.events", "E2");
```

Dù template có default destination `orders.events`, lời gọi thứ hai vẫn gửi tới `shipping.events`. Tuy nhiên cả hai tên `String` vẫn được resolve dưới Topic domain của template. Nếu gửi vào Queue bằng cùng template Topic, hãy dùng một template Queue riêng hoặc truyền object `Queue` tương thích và kiểm tra provider. **Không** xem việc truyền tên khác là cách chuyển Queue ↔ Topic.

## 10. Nhận đồng bộ và tác động của default destination

`JmsTemplate` không chỉ gửi message mà còn có `receive()` và `receiveAndConvert()`. Khi đã đặt default destination, lời gọi không truyền đích sẽ nhận **đồng bộ** trên đích đó:

```java
JmsTemplate t = new JmsTemplate(connectionFactory);
t.setDefaultDestinationName("orders.created");
t.setReceiveTimeout(2_000); // 2000 ms

Object result = t.receiveAndConvert();
if (result == null) {
    System.out.println("Chưa có message trong thời gian chờ");
} else {
    System.out.println("Nhận: " + result);
}
```

Đây là **snippet trong một method đã có `ConnectionFactory`**, không phải chương trình độc lập. `receiveAndConvert()` trả `null` khi hết thời gian chờ mà không nhận message. Giá trị timeout dương tính bằng **mili-giây**; mặc định của `JmsTemplate` có thể chờ **vô thời hạn**, vì vậy nên đặt `receiveTimeout` phù hợp nếu dùng nhận đồng bộ trong request/worker.

**Cảnh báo về Queue:** nếu bạn dùng `receiveAndConvert()` và `@JmsListener` cùng nghe `orders.created`, hai consumer **cạnh tranh**. Không bảo đảm `receiveAndConvert()` lấy được message vừa gửi; listener có thể đã nhận. Demo mục 7 chỉ dùng listener cho Queue mặc định để dễ quan sát và tránh nhầm này.

Khi cần xử lý liên tục bất đồng bộ, dùng `@JmsListener` thay vì vòng lặp `receive()` chặn thread tùy ý. Với Topic, ngữ nghĩa subscription/online/offline cũng phải được tính tới; gọi `receive()` không tự tạo durable subscription lâu dài.

## 11. Default destination không quyết định delivery semantics

Cấu hình đích mặc định chỉ chọn **nơi gửi hoặc nhận**. Các vấn đề còn lại độc lập:

- **Message body:** `convertAndSend(String)` dùng `MessageConverter` (mặc định thường là `SimpleMessageConverter`); `send(MessageCreator)` cho phép tự tạo `TextMessage`, `BytesMessage`, v.v.
- **JMS headers/properties:** có thể đặt trong `MessageCreator` hoặc qua `MessagePostProcessor`; `setDefaultDestinationName` không điền content type/schema/event ID.
- **Transaction và acknowledgment:** do `JmsTemplate`, session, listener container và transaction manager quyết định. Nếu xử lý rollback, broker có thể redeliver; template default không tự bảo đảm exactly-once cho side effect.
- **Delivery mode, priority, TTL:** có thể cấu hình qua QoS khi thích hợp; Spring `JmsTemplate` có `setExplicitQosEnabled`, `setDeliveryMode`, `setPriority`, `setTimeToLive`. Việc áp dụng phụ thuộc cấu hình explicit QoS và provider.
- **Bảo mật và quota:** factory credentials, broker authorization, destination policy, DLQ, retries và max size đều cần cấu hình riêng.

Nếu dùng bean template chia sẻ trên nhiều thread, hãy đặt các thuộc tính **một lần khi khởi tạo**. Thay đổi default destination, `MessageConverter` hoặc `pubSubDomain` trong lúc request đang gửi có thể dẫn đến routing ngoài ý định. Chọn overload có destination hoặc nhiều template cố định nếu cần route khác nhau.

## 12. Lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Khả năng cao | Kiểm tra |
| --- | --- | --- |
| `JmsTemplate` bean không tạo được | Thiếu `ConnectionFactory`, thiếu starter/client JMS hoặc bean bị xung đột. | Kiểm tra dependency và Spring context; xem root cause. |
| Lệnh `convertAndSend("A")` báo thiếu default | Chưa đặt `defaultDestinationName`/`defaultDestination` cho template đang dùng. | Đọc bean được inject, cấu hình Boot và tên bean. |
| Lệnh gửi có destination tường minh lại chạy được | Factory có thể tốt, chỉ thiếu cấu hình default. | Phân biệt overload `convertAndSend(Object)` và `convertAndSend(String,Object)`. |
| Không thấy message ở Queue kỳ vọng | Gửi Topic thay Queue, sai tên, gửi broker khác hoặc listener cạnh tranh. | Kiểm tra `pubSubDomain`, destination resolver, endpoint và ACL. |
| `@JmsListener` không dùng default template | Listener có factory/annotation riêng. | Đọc `@JmsListener(destination=...)` và listener container factory. |
| JNDI lookup destination thất bại | Tên resource chưa bind hoặc `resourceRef` sai. | Kiểm tra server naming context và `JndiDestinationResolver`. |
| Provider từ chối gửi | Queue/Topic chưa tạo, thiếu quyền, TLS/broker lỗi hoặc connection pool cạn. | Kiểm tra broker log, ACL, health, resource provisioning. |
| `receive()` “treo” | Gọi nhận đồng bộ không đặt timeout hoặc không có message. | Dùng `setReceiveTimeout`/Boot property và kiểm tra consumer khác. |
| Gửi theo template A nhưng thực tế dùng B | Có nhiều bean `JmsTemplate`, injection thiếu `@Qualifier`/`@Primary`. | Kiểm tra bean graph và unit/integration test. |
| Chạy lại demo thấy log trùng | Broker giữ backlog, producer chạy lại, hoặc redelivery. | Kiểm tra message ID, event ID, session/ack và transaction. |

### Debug theo thứ tự

1. Xác định **đúng instance `JmsTemplate`** mà service đang inject; nếu có nhiều, kiểm tra `@Qualifier`.
2. Xác định **factory nào** gắn vào template, provider và broker endpoint nào.
3. Kiểm tra default destination được set bằng **name hay object**, và method đang gọi có destination tường minh không.
4. Kiểm tra `pubSubDomain` và `DestinationResolver`; với listener cũng kiểm tra container factory riêng.
5. Kiểm tra broker log/management console, quyền, destination tồn tại, delivery/ack/transaction.
6. Chạy smoke test với Queue sạch, payload nhỏ có event ID, một consumer, rồi mở rộng concurrency sau khi routing đúng.

Không nên debug bằng cách thêm nhiều Queue hoặc đổi hàng loạt thuộc tính cùng lúc. Thay đổi một cấu hình, xác minh message thực sự đi đến đâu, rồi mới tiếp tục.

## 13. Tự kiểm tra

**Câu 1.** Template có default `orders.created`. `convertAndSend("hello")` gửi đi đâu?

**Đáp án:** Tới default destination `orders.created` vì đây là overload chỉ có payload.

**Câu 2.** `convertAndSend("orders.audit", "hello")` có gửi tới `orders.created` không?

**Đáp án:** Không. `orders.audit` là destination tường minh, ghi đè lựa chọn default của lời gọi.

**Câu 3.** Vì sao cấu hình `spring.jms.template.default-destination=orders.created` không tự khiến `@JmsListener` bắt đầu nghe `orders.created`?

**Đáp án:** Default chỉ thuộc `JmsTemplate`; listener xác định destination thông qua annotation và container factory.

**Câu 4.** Một `JmsTemplate` có `setPubSubDomain(true)` và default name `orders.created`. Tên ấy được diễn giải thành Queue hay Topic nếu dùng resolver động mặc định?

**Đáp án:** **Topic**. Với `false` là Queue; nếu truyền object `Destination`, loại object ấy quyết định.

**Câu 5.** Khi ứng dụng có hai `ConnectionFactory` tới hai broker, thay `setDefaultDestinationName` có chuyển sang broker khác không?

**Đáp án:** Không. Template vẫn dùng factory đã được gắn; muốn đổi broker cần chọn template/factory phù hợp.

**Câu 6.** `receiveAndConvert()` với timeout 2 giây có chắc lấy được message vừa gửi nếu có một `@JmsListener` cạnh tranh cùng Queue?

**Đáp án:** Không. Hai consumer cạnh tranh; listener có thể nhận trước. Nếu hết thời gian chờ, phương thức có thể trả `null`.

## 14. Tài liệu đối chiếu

- [Spring Framework 6.2: JmsTemplate JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework: Sending a Message với JmsTemplate](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework: Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework: DynamicDestinationResolver](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/DynamicDestinationResolver.html)
- [Spring Framework: JndiDestinationResolver](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html)
- [Spring Boot 3: JMS configuration và auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html)
- [Jakarta Messaging 3.1 API](https://jakarta.ee/specifications/messaging/3.1/)

**Ghi nhớ:** `ConnectionFactory` quyết định **cách kết nối provider**; default destination trong `JmsTemplate` quyết định **đích cho những lệnh không truyền destination**; Queue/Topic, listener routing, delivery QoS và transaction là các cấu hình khác cần được quản lý nhất quán.
