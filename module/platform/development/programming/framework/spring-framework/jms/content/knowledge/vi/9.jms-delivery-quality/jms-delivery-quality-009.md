# QoS cho phản hồi của listener trong Spring JMS

## 1. QoS của phản hồi listener là gì?

Trong Spring JMS, một phương thức `@JmsListener` có thể **nhận yêu cầu, xử lý và trả về kết quả**. Nếu có destination phản hồi phù hợp, Spring chuyển giá trị trả về thành JMS message rồi gửi về Queue hoặc Topic tương ứng. Message phản hồi này có **Quality of Service (QoS) riêng**, không nhất thiết giống message yêu cầu.

Ba tham số QoS cơ bản của JMS khi **gửi phản hồi** là:

- **Delivery mode:** `PERSISTENT` hoặc `NON_PERSISTENT`.
- **Priority:** độ ưu tiên từ `0` đến `9`.
- **Time-to-live (TTL):** thời gian tồn tại của response, tính bằng mili-giây kể từ lúc **response được gửi**; `0` nghĩa là không có hạn hết hạn dựa trên TTL.

Spring Framework cung cấp `org.springframework.jms.support.QosSettings` để gom ba tham số trên, và `DefaultJmsListenerContainerFactory.setReplyQosSettings(...)` để áp dụng chúng **cho message phản hồi do Spring tự gửi** từ listener của container đó.

```text
Producer yêu cầu                     Spring JMS listener
        |                                    |
        |  Request: TextMessage              |
        |  destination = demo.requests        |
        +----------------------------------->| @JmsListener
        |                                    | xử lý
        |                                    | return "APPROVED"
        |                                    v
        |                            Spring chuyển response
        |                            thành JMS TextMessage
        |                                    |
        |                                    | áp dụng QosSettings:
        |                                    |   priority=2
        |                                    |   TTL=10.000 ms
        |                                    |   PERSISTENT
        |                                    v
        |                              Response destination
        |                              (JMSReplyTo/@SendTo)
        |<-----------------------------------+
        |
Consumer phản hồi (hoặc client request-reply)
```

**Điểm quan trọng nhất:** cấu hình `replyQosSettings` điều khiển **message được gửi trả về từ listener**, không tự thay đổi QoS của request đang được consume; cũng không tự đặt QoS cho `JmsTemplate.convertAndSend(...)` ở bất kỳ service nào.

## 2. Điều kiện để Spring thực sự gửi một phản hồi

Cấu hình QoS chỉ có ý nghĩa khi listener **thực sự tạo response**.

### 2.1. Listener trả giá trị khác `void`

Ví dụ:

```java
@JmsListener(destination = "orders.requests")
@SendTo("orders.responses")
public String process(String request) {
    return "ACK:" + request;
}
```

Đoạn trên là **method trong một Spring bean**, cần import `org.springframework.jms.annotation.JmsListener` và `org.springframework.messaging.handler.annotation.SendTo`.

Spring có thể chuyển chuỗi `"ACK:..."` thành `TextMessage` thông qua `MessageConverter` phù hợp (với `SimpleMessageConverter` mặc định). Sau đó Spring gửi message này đến response destination.

- `@JmsListener(destination=...)`: Queue/Topic để **nhận** request.
- `@SendTo(...)`: response destination mặc định khi **gửi** reply.
- `return ...`: dữ liệu dùng để tạo **reply message**.
- `setReplyQosSettings(...)`: QoS của lần **gửi reply** trong listener container.

### 2.2. Destination của response được chọn theo thứ tự nào?

Với cơ chế phản hồi tự động thông thường, Spring có thể xác định đích theo:

1. **`JmsResponse`** được listener trả về: dùng khi muốn quyết định destination ở runtime.
2. Nếu không chỉ định đích riêng như trên, **`JMSReplyTo`** trên request (nếu có) là destination dành cho response.
3. Nếu request không có `JMSReplyTo`, Spring dùng **`@SendTo`** hoặc default response destination đã cấu hình cho listener adapter.
4. Nếu không có destination phản hồi nào phù hợp, việc gửi reply có thể thất bại với lỗi destination.

Vì vậy `@SendTo("orders.responses")` thường là **fallback** khi request không cung cấp `JMSReplyTo`. Trong request-reply sử dụng `TemporaryQueue`, client thường đặt `JMSReplyTo` vào request để nhận riêng response của mình.

**QoS và destination là hai quyết định tách biệt:** `QosSettings` không tạo Queue và không giải quyết việc request thiếu `JMSReplyTo` hay `@SendTo`.

### 2.3. Listener không trả reply

```java
@JmsListener(destination = "orders.requests")
public void consumeOnly(String request) {
    // Chỉ xử lý request, không tạo response tự động.
}
```

Không có kết quả để gửi, nên **`replyQosSettings` không có message nào để áp dụng**. Một listener có `void` nhưng **tự gọi `JmsTemplate` để gửi response** cũng không sử dụng cấu hình reply QoS của container cho lần gửi đó; xem mục 11.

## 3. `QosSettings` gồm những trường nào?

Class `org.springframework.jms.support.QosSettings` có constructor không tham số và constructor:

```java
QosSettings settings = new QosSettings(
        DeliveryMode.PERSISTENT,
        2,
        10_000L
);
```

Trong snippet này, `DeliveryMode` thuộc `jakarta.jms.DeliveryMode`, `QosSettings` thuộc `org.springframework.jms.support.QosSettings`.

Có thể dùng setter tương đương:

```java
QosSettings settings = new QosSettings();
settings.setDeliveryMode(DeliveryMode.PERSISTENT);
settings.setPriority(2);
settings.setTimeToLive(10_000L);
```

| Thuộc tính | Phương thức | Phạm vi hợp lệ hoặc ý nghĩa |
| --- | --- | --- |
| Delivery mode | `setDeliveryMode(int)` | `DeliveryMode.PERSISTENT` hoặc `DeliveryMode.NON_PERSISTENT`. |
| Priority | `setPriority(int)` | `0..9`; 9 cao nhất, 0 thấp nhất. JMS default thường là 4. |
| Time-to-live | `setTimeToLive(long)` | Số mili-giây không âm; `10_000L` là 10 giây, `0` không hết hạn theo TTL. |

Các **giá trị mặc định bên trong một `new QosSettings()`** là JMS message defaults: `PERSISTENT`, priority `4`, TTL `0`. Đó là mặc định chuẩn của object cài đặt, **không phải cam kết rằng broker luôn dùng đúng các giá trị ấy** khi không cấu hình QoS tường minh; một JMS provider có thể có defaults quản trị riêng.

Tóm tắt:

```text
new QosSettings()
  deliveryMode = PERSISTENT
  priority     = 4
  timeToLive   = 0 ms

new QosSettings(PERSISTENT, 2, 10_000)
  deliveryMode = PERSISTENT
  priority     = 2
  timeToLive   = 10.000 ms
```

**`NON_PERSISTENT` không đồng nghĩa “mất message chắc chắn”; `PERSISTENT` cũng không tương đương exactly-once.** Delivery mode chỉ là một phần của hợp đồng JMS; crash recovery, acknowledgment, retry, transaction, broker policy và consumer idempotency vẫn quan trọng.

### Priority chỉ là gợi ý cho broker

Priority `2` là **thấp hơn** mặc định `4` (không phải “ưu tiên cao”). Provider có thể sử dụng priority để sắp lịch delivery, nhưng không hứa tuyệt đối message priority 9 luôn được xử lý trước mọi priority 4. Với nhiều consumer, transacted sessions, prefetch, retry và concurrency, thứ tự log thực tế có thể khác thứ tự gửi.

### TTL bắt đầu tính từ lúc gửi reply

`timeToLive=10_000L` không bắt đầu khi listener nhận request hoặc khi user gửi request. Nó là khoảng thời gian được áp dụng cho **message phản hồi tại thời điểm gửi**. Ví dụ listener xử lý request trong 5 giây, sau đó gửi reply có TTL 10 giây: về nguyên tắc response hết hạn khoảng 10 giây sau **lần gửi reply**, không phải 5 giây sau khi request đến.

Với provider chuẩn, bạn có thể kiểm tra header `JMSExpiration` trên reply; `0` thường chỉ không có expiration, còn timestamp dương là thời điểm dự kiến hết hạn (epoch milliseconds). Header có thể chịu chính sách broker/provider. TTL không phải client-side timeout chờ response.

## 4. Cấu hình đúng: `setReplyQosSettings` trên listener container factory

Spring Framework 6 cung cấp class `DefaultJmsListenerContainerFactory` để tạo các listener containers cho `@JmsListener`.

Ví dụ tối giản **trong ứng dụng Spring đã có bean `ConnectionFactory`**:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.QosSettings;

@Configuration
public class ReplyQosConfiguration {

    @Bean("replyQosFactory")
    public DefaultJmsListenerContainerFactory replyQosFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        var qos = new QosSettings();
        qos.setDeliveryMode(DeliveryMode.PERSISTENT);
        qos.setPriority(2);
        qos.setTimeToLive(10_000L);

        factory.setReplyQosSettings(qos);
        return factory;
    }
}
```

Và listener gắn **đúng tên factory**:

```java
@Component
public class OrderResponder {

    @JmsListener(
            destination = "orders.requests",
            containerFactory = "replyQosFactory"
    )
    @SendTo("orders.responses")
    public String respond(String request) {
        return "ACK:" + request;
    }
}
```

Đoạn `OrderResponder` cần các import `org.springframework.stereotype.Component`, `org.springframework.jms.annotation.JmsListener`, `org.springframework.messaging.handler.annotation.SendTo` và được đặt trong ứng dụng có config phía trên.

**Tác dụng:** các response **Spring tự tạo và gửi** qua listener container được sinh bởi `replyQosFactory` sẽ mang QoS đã khai báo. Cấu hình không áp dụng tự động cho mọi `@JmsListener` ở các factory khác.

Nếu muốn sử dụng factory mặc định cho các `@JmsListener` không khai báo `containerFactory`, đặt tên bean là `jmsListenerContainerFactory` (hoặc cấu hình default factory qua `JmsListenerConfigurer`). Khi dùng Spring Boot, có thể sử dụng configurer để giữ các defaults; xem mục 5.

### Không dùng nhầm API

Đối tượng `QosSettings` ở đây thuộc Spring JMS. Đây **không** phải `jakarta.jms.QosSettings` (API như vậy không tồn tại). `setReplyQosSettings` thuộc **listener container factory / listener container**, không phải một attribute của `@SendTo` hoặc `@JmsListener`. Spring không cung cấp các thuộc tính `priority`, `timeToLive` trực tiếp trên `@SendTo` của JMS.

## 5. Khi dùng Spring Boot: giữ lại cấu hình tự động

Trong Spring Boot 3, nếu tự tạo `DefaultJmsListenerContainerFactory`, nên dùng `DefaultJmsListenerContainerFactoryConfigurer` để áp dụng defaults từ Boot (converter, concurrency, transaction settings... nếu có), rồi mới override reply QoS.

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.QosSettings;

@Configuration(proxyBeanMethods = false)
public class ReplyQosConfiguration {

    @Bean("replyQosFactory")
    public DefaultJmsListenerContainerFactory replyQosFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        var reply = new QosSettings();
        reply.setDeliveryMode(DeliveryMode.PERSISTENT);
        reply.setPriority(2);
        reply.setTimeToLive(10_000L);
        factory.setReplyQosSettings(reply);

        return factory;
    }
}
```

Ở đây tên `replyQosFactory` là **factory bổ sung, có phạm vi rõ ràng**; Boot vẫn có thể tạo factory mặc định `jmsListenerContainerFactory` cho các listener khác. `@JmsListener(containerFactory = "replyQosFactory")` chọn cấu hình này.

**Thứ tự có ý nghĩa:** `configurer.configure(...)` trước, `setReplyQosSettings(...)` sau, để giá trị reply QoS tùy chỉnh không bị bước cấu hình tổng quát ghi đè.

### Vì sao không chỉ đặt `spring.jms.template.priority`?

Các thuộc tính sau điều khiển **`JmsTemplate` khi gửi outbound message**:

```yaml
spring:
  jms:
    template:
      priority: 8
      time-to-live: 5s
      qos-enabled: true
```

Chúng **không mặc nhiên đặt QoS cho phản hồi Spring tự phát từ listener**. Muốn có priority 2, TTL 10 giây cho reply của listener thì cấu hình **`setReplyQosSettings` trên factory tương ứng**.

Ngược lại, cấu hình reply QoS trên listener cũng **không** thay đổi QoS của mọi request được service gửi bằng `JmsTemplate`. Hai đường gửi dùng hai lớp cấu hình riêng. Không nên cấu hình priority 8 cho cả hệ thống chỉ để mong reply của một listener ưu tiên cao hơn.

## 6. Demo đầy đủ: Java 17 + Spring Boot + ActiveMQ Artemis

Mục tiêu của demo:

1. Producer gửi `"PING-001"` đến Queue `demo.reply.requests`.
2. `@JmsListener` nhận request và **return** `"ACK:PING-001"`.
3. Spring tự gửi reply vào `demo.reply.responses` nhờ `@SendTo`.
4. Reply được gửi với **priority 2, TTL 10 giây, PERSISTENT** qua `replyQosFactory`.
5. Một listener riêng đọc reply và in `JMSPriority`, `JMSDeliveryMode` và `JMSExpiration`.

Môi trường: **Java 17+, Spring Boot 3.3.13, Gradle 8.5+**, broker **Apache ActiveMQ Artemis** đang chạy tại `localhost:61616`. Ví dụ dùng Java/Jakarta JMS APIs, không trộn `javax.jms` cũ.

### 6.1. Khởi động broker thử nghiệm

Máy có Docker chạy được, dùng:

```bash
docker run --detach --rm --name artemis-reply-qos -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

Đợi broker sẵn sàng trước khi chạy ứng dụng. Tên Queue `demo.reply.requests` và `demo.reply.responses` cần tồn tại hoặc broker cho phép auto-create. Nếu broker tắt auto-create hoặc giới hạn quyền, quản trị viên phải provision hai Queue và cấp quyền trước. Credential demo chỉ dùng ở môi trường local.

Dừng broker khi hoàn tất:

```bash
docker stop artemis-reply-qos
```

### 6.2. Cấu trúc dự án

```text
reply-qos-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/jms/
    │   ├── ReplyQosApplication.java
    │   ├── ReplyQosConfiguration.java
    │   └── ReplyHandlers.java
    └── resources/
        └── application.yml
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'reply-qos-demo'
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
```

`pub-sub-domain: false` làm cho các destination name của demo được resolve theo **Queue**, không phải Topic. Hai Queue phải phù hợp với cấu hình broker.

### 6.3. Ứng dụng chính và producer yêu cầu

Tệp `src/main/java/demo/jms/ReplyQosApplication.java`:

```java
package demo.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ReplyQosApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReplyQosApplication.class, args);
    }

    @Bean
    ApplicationRunner sendOneRequest(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.convertAndSend(
                    "demo.reply.requests",
                    "PING-001"
            );
            System.out.println("Request submitted");
        };
    }
}
```

Ở đây request được gửi bằng `JmsTemplate` auto-configured với các defaults bình thường. Chưa đặt `JMSReplyTo`; listener sẽ dùng `@SendTo` để xác định reply queue. **Giá trị request message priority không liên quan trực tiếp đến reply priority=2**.

### 6.4. Listener container factory với reply QoS

Tệp `src/main/java/demo/jms/ReplyQosConfiguration.java`:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;

import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.QosSettings;

@Configuration(proxyBeanMethods = false)
public class ReplyQosConfiguration {

    @Bean("replyQosFactory")
    public DefaultJmsListenerContainerFactory replyQosFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        var replyQos = new QosSettings();
        replyQos.setDeliveryMode(DeliveryMode.PERSISTENT);
        replyQos.setPriority(2);
        replyQos.setTimeToLive(10_000L);

        factory.setReplyQosSettings(replyQos);
        return factory;
    }
}
```

`replyQosFactory` được chọn **chỉ** cho listener chỉ định `containerFactory="replyQosFactory"`. Tạo một bean factory có tên không có nghĩa tất cả listener trong ứng dụng đều chuyển sang dùng nó.

### 6.5. Xử lý request và quan sát reply

Tệp `src/main/java/demo/jms/ReplyHandlers.java`:

```java
package demo.jms;

import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class ReplyHandlers {

    @JmsListener(
            destination = "demo.reply.requests",
            containerFactory = "replyQosFactory"
    )
    @SendTo("demo.reply.responses")
    public String respond(String request) {
        return "ACK:" + request;
    }

    @JmsListener(destination = "demo.reply.responses")
    public void inspectResponse(TextMessage message)
            throws JMSException {

        String body = message.getText();
        int priority = message.getJMSPriority();
        boolean persistent =
                message.getJMSDeliveryMode() == DeliveryMode.PERSISTENT;
        boolean expiring = message.getJMSExpiration() > 0L;

        System.out.printf(
                "Reply body=%s, priority=%d, persistent=%s, expires=%s%n",
                body, priority, persistent, expiring
        );
    }
}
```

**Phân tích:**

- `respond` trả về `String`; Spring listener adapter chuyển nó thành JMS response message.
- `@SendTo` cung cấp tên response Queue vì request demo **không có `JMSReplyTo`**.
- `replyQosFactory` đặt QoS khi Spring gửi response.
- `inspectResponse` nhận raw `TextMessage` để đọc metadata, **không tự gửi phản hồi** vì method `void`; nó dùng factory mặc định của Boot.
- Thông tin `JMSPriority`, `JMSDeliveryMode` và `JMSExpiration` là **header của reply** do provider gán/xử lý; đây là cách quan sát tác dụng của QoS hơn là chỉ in cấu hình trong memory.

### 6.6. Cách chạy và output

Tại thư mục dự án, chạy:

```bash
gradle bootRun
```

Nếu đã có Gradle Wrapper, Linux/macOS dùng `./gradlew bootRun`, Windows dùng `gradlew.bat bootRun`.

Trong điều kiện broker sạch, Queue đã được provision/cho phép tạo, listener sẵn sàng và reply chưa hết hạn, ứng dụng có thể in:

```text
Request submitted
Reply body=ACK:PING-001, priority=2, persistent=true, expires=true
```

**Thứ tự hai dòng trên không bảo đảm**: listener xử lý bất đồng bộ và dòng `Reply body...` có thể xuất hiện trước `Request submitted`. Ngoài ra, console có log khác của Spring. Nếu provider áp chính sách riêng hoặc QoS không được gửi như dự kiến, giá trị header cần được điều tra thay vì coi output trên luôn cố định.

Vì TTL chỉ 10 giây, hãy để listener nhận response kịp thời; nếu broker giữ reply qua thời gian hết hạn, nó có thể không được giao tới `inspectResponse`. Thử tăng TTL để giảm ảnh hưởng thời gian khởi động/tải khi test.

### 6.7. Nếu demo không chạy được

Kiểm tra lần lượt:

1. Artemis đã sẵn sàng ở `tcp://localhost:61616`; đúng user/password.
2. Hai Queue có tồn tại hoặc broker cho phép tạo; application có quyền send/consume.
3. `spring-boot-starter-artemis` đã được resolve, không trộn client `javax.jms` với `jakarta.jms`.
4. `replyQosFactory` đúng tên bean, và `respond` chỉ định `containerFactory="replyQosFactory"`.
5. Listener `respond` thực sự trả `String`, converter tạo reply thành `TextMessage`, và `@SendTo` trỏ đúng response Queue.
6. Test trong một broker sạch để tránh message tồn từ lần chạy trước, message hết TTL, redelivery hoặc consumer khác.

Đây là ví dụ **có đủ mã nguồn và cấu hình để biên dịch/chạy trong môi trường phù hợp**; không khẳng định đã chạy trực tiếp trên một broker trong phiên đọc tài liệu.

## 7. `JMSReplyTo` và `@SendTo` tác động thế nào đến QoS?

### 7.1. Request có `JMSReplyTo`

Một producer có thể đặt destination reply ngay trên request:

```java
jmsTemplate.send("demo.reply.requests", session -> {
    TextMessage request = session.createTextMessage("PING-002");
    request.setJMSReplyTo(session.createQueue("client.private.replies"));
    return request;
});
```

Đây là snippet **trong method đã inject `JmsTemplate`**, cần import `jakarta.jms.TextMessage`. Với request này, listener `respond` có thể gửi response về **`client.private.replies`** thay vì `@SendTo("demo.reply.responses")`, bởi vì `JMSReplyTo` của request được ưu tiên trong cơ chế reply mặc định.

**QoS vẫn là QoS của reply**: `replyQosFactory` có thể gửi response đến reply Queue đã chọn với priority 2, TTL 10 giây, PERSISTENT. Không vì đổi destination mà Spring tự đổi `QosSettings`.

Chú ý: client cần có consumer nghe `client.private.replies`. Nếu không, có thể thấy request được xử lý nhưng không có log trong `demo.reply.responses` và tưởng reply bị mất.

### 7.2. Dùng `JmsResponse` khi destination phụ thuộc kết quả

Khi muốn chọn đích ngay trong method:

```java
@JmsListener(
        destination = "orders.requests",
        containerFactory = "replyQosFactory"
)
public JmsResponse<String> process(String request) {
    String destination =
            request.startsWith("VIP:")
                    ? "orders.vip.replies"
                    : "orders.standard.replies";

    return JmsResponse.forQueue("ACK:" + request, destination);
}
```

Đây là method trong Spring bean, cần import `org.springframework.jms.listener.adapter.JmsResponse` và `JmsListener`. `JmsResponse` cho phép reply destination động; cấu hình QoS vẫn thuộc factory của listener. Với phương án này, không cần `@SendTo` cố định.

**Không nhầm** `JmsResponse<T>` với `QosSettings`: `JmsResponse` nói **gửi đến đâu**, còn `QosSettings` nói **gửi bằng QoS nào**.

### 7.3. Correlation ID

Trong cơ chế reply mặc định của Spring listener adapter, khi tạo reply, Spring thường đặt `JMSCorrelationID` của reply bằng `JMSCorrelationID` của request nếu có; nếu không, có thể dùng `JMSMessageID` của request. Mục tiêu là giúp client ghép response với request tương ứng.

`replyQosSettings` **không tự thiết lập correlation ID** và không thay thế chính sách request-reply correlation. Nếu cần truy vết ổn định qua retry hoặc nhiều hệ thống, bổ sung event/request ID nghiệp vụ, không chỉ dựa vào JMS message ID.

## 8. Queue/Topic cho reply là một cấu hình riêng

Cùng tên `"orders.responses"` có thể được provider coi là **Queue** hoặc **Topic** tùy cơ chế resolution.

- `pubSubDomain`: domain của destination mà listener **consume**.
- `replyPubSubDomain`: domain dùng để **resolve tên response** cho listener trong trường hợp sử dụng resolver động; khi không cấu hình riêng thường theo `pubSubDomain`.
- `replyQosSettings`: delivery mode, priority, TTL của **message response được gửi**.

Ba cấu hình không thể thay thế cho nhau.

Ví dụ một listener **nhận request từ Queue nhưng trả reply tới Topic** khi đã có naming/policy phù hợp:

```java
var factory = new DefaultJmsListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setPubSubDomain(false);      // nhận từ Queue
factory.setReplyPubSubDomain(true);  // resolve reply name theo Topic
factory.setReplyQosSettings(
        new QosSettings(DeliveryMode.PERSISTENT, 2, 10_000L)
);
```

Đây là snippet **bên trong phương thức cấu hình có bean `ConnectionFactory`**, cần import `DefaultJmsListenerContainerFactory`, `QosSettings`, `DeliveryMode`. Listener trả về phải có đích thích hợp, và người nhận phải subscribe Topic tương ứng. Với `JMSReplyTo` đã là một object `Destination`, kiểu object ấy quyết định destination thực tế; `replyPubSubDomain` chủ yếu ảnh hưởng resolution từ tên.

Đừng thay `setReplyPubSubDomain(true)` chỉ vì muốn nâng priority; hai vấn đề khác nhau.

## 9. Reply QoS khác QoS của request gửi bằng JmsTemplate

Bảng đối chiếu:

| Tiêu chí | Request gửi bằng JmsTemplate | Reply do @JmsListener tự gửi |
| --- | --- | --- |
| Điểm cấu hình | `JmsTemplate` hoặc `spring.jms.template.*` | `DefaultJmsListenerContainerFactory.setReplyQosSettings` |
| QoS container | Không tự lấy từ listener factory | Có nếu listener dùng factory đã cấu hình |
| Priority | `template.setPriority(...)` và explicit QoS | `QosSettings.setPriority(...)` |
| TTL | `template.setTimeToLive(...)` và explicit QoS | `QosSettings.setTimeToLive(...)` |
| Delivery mode | `template.setDeliveryMode(...)` và explicit QoS | `QosSettings.setDeliveryMode(...)` |
| Destination | Destination truyền vào `JmsTemplate` | `JmsResponse`, `JMSReplyTo`, `@SendTo` |
| Trường hợp không gửi gì | Không gọi send | Method listener `void`/không có response |

Ví dụ cấu hình yêu cầu priority 8, TTL 5 giây bằng Boot, nhưng phản hồi priority 2, TTL 10 giây bằng listener factory:

```yaml
spring:
  jms:
    template:
      priority: 8
      time-to-live: 5s
      qos-enabled: true
```

Khi producer dùng `JmsTemplate` từ Boot để gửi request, request có thể được gửi với QoS trên. Khi listener được cấu hình bằng `replyQosFactory` trả kết quả, reply được gửi với settings **priority 2/TTL 10 giây** của factory, không “thừa kế” priority 8/TTL 5 giây từ request.

**Không nhầm TTL request với reply timeout:** một request hết hạn trước khi listener nhận sẽ không sinh reply. Một reply được gửi có TTL 10 giây có thể hết hạn trước khi client chờ nhận, dù xử lý request đã xong.

## 10. Tác động thực tế của ba thông số QoS

### 10.1. Delivery mode

`DeliveryMode.PERSISTENT` yêu cầu provider đảm bảo mô hình persistent delivery theo hợp đồng JMS trong điều kiện hỗ trợ tương ứng. Nó thường phù hợp reply quan trọng cần không mất khi broker restart, nhưng có thêm chi phí I/O và có thể tương tác với transaction.

`DeliveryMode.NON_PERSISTENT` có thể giúp giảm overhead cho các reply tức thời, không quan trọng khi client đã hủy chờ hoặc có thể retry; nhưng mất message khi broker failure có thể chấp nhận được hoặc không tùy hệ thống.

Không thể suy luận từ delivery mode một mình về **exactly once** hoặc business transaction giữa database và JMS.

### 10.2. Priority

Priority là gợi ý sắp lịch giữa các message chờ trên cùng broker/destination và **không bảo đảm thứ tự tuyệt đối**. Với request-reply, việc đặt reply priority cao có thể hữu ích khi Queue phản hồi có backlog; nhưng luôn cần kiểm tra tình huống prefetch và nhiều consumer.

`QosSettings.setPriority(2)` là ví dụ từ tài liệu Spring để thấy cấu hình có hiệu lực, **không phải mức được khuyến nghị mặc định cho mọi hệ thống**. Priority 9 không phải công tắc “xử lý ngay” và có thể gây starvation cho công việc ưu tiên thấp trong một số hệ thống.

### 10.3. Time-to-live

Giả sử server gửi response lúc 10:00:00.000 với TTL 10.000 ms:

```text
10:00:00.000 reply được gửi
10:00:01.000 client nhận -> còn hạn
10:00:08.000 client nhận -> còn hạn
10:00:10.000 reply đến mốc hết hạn
10:00:12.000 client mới thử nhận -> reply có thể đã bị expire
```

Các mốc này chỉ là minh họa; xử lý expiration cụ thể phụ thuộc JMS provider và broker clock/policy. `JMSExpiration` là **mốc thời gian tuyệt đối**, không phải “còn bao nhiêu ms”. Khi TTL = 0, header expiration thường là 0.

TTL nên được chọn dựa trên **thời gian còn hữu ích của phản hồi**, backlog, SLA và cơ chế retry, không dựa đơn giản vào thời gian xử lý của listener.

## 11. Nếu listener tự gửi phản hồi bằng JmsTemplate/MessageProducer thì sao?

Cần phân biệt hai đường phản hồi:

**Đường A — Spring gửi tự động:**

```java
@JmsListener(
        destination = "demo.requests",
        containerFactory = "replyQosFactory"
)
@SendTo("demo.responses")
public String handle(String input) {
    return "ACK:" + input;
}
```

`return` được Spring chuyển thành JMS message và gửi. **`replyQosSettings` được dùng** trong cơ chế này.

**Đường B — ứng dụng tự gửi:**

```java
@JmsListener(
        destination = "demo.requests",
        containerFactory = "replyQosFactory"
)
public void handle(String input) {
    myJmsTemplate.convertAndSend("demo.responses", "ACK:" + input);
}
```

Trong snippet B, `myJmsTemplate` là bean đã inject và method không trả reply. Lần gửi này **đi theo cấu hình QoS của `myJmsTemplate`**, không tự lấy `replyQosSettings` từ factory của listener. Cần cấu hình `myJmsTemplate.setExplicitQosEnabled(true)`, `setPriority`, `setTimeToLive`... hoặc sử dụng `MessageProducer.send(..., mode, priority, ttl)` phù hợp.

Tương tự, listener tự dùng `SessionAwareMessageListener` và tạo `MessageProducer` rồi `send` thì chính code đó phải chịu trách nhiệm QoS/lifecycle; không mặc định được listener adapter áp `replyQosSettings`.

**Tránh gửi hai reply ngoài ý muốn:** nếu một method vừa tự gọi `JmsTemplate.convertAndSend` vừa **return một giá trị khác void** được Spring tự xử lý, có thể xuất hiện hai response khác nhau. Hãy chọn một mô hình gửi reply, trừ khi thiết kế cố ý phát hai sự kiện.

## 12. Chọn phạm vi cấu hình cho nhiều listener

Có thể có nhiều listener với yêu cầu reply QoS khác nhau:

- Listener nghiệp vụ trả trạng thái đơn hàng: cần reply có TTL ngắn vì client chỉ chờ vài giây.
- Listener kiểm toán trả biên nhận: có thể cần persistent delivery với TTL dài hơn.
- Listener chỉ consume và lưu database: không tạo reply, `replyQosSettings` không có ý nghĩa trực tiếp.

Thay vì dùng một cấu hình cho mọi listener, đặt **nhiều factory có tên rõ ràng**:

```java
@Bean("fastReplyFactory")
DefaultJmsListenerContainerFactory fastReplyFactory(
        ConnectionFactory cf,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {
    var f = new DefaultJmsListenerContainerFactory();
    configurer.configure(f, cf);
    f.setReplyQosSettings(
            new QosSettings(DeliveryMode.NON_PERSISTENT, 6, 3_000L));
    return f;
}

@Bean("durableReplyFactory")
DefaultJmsListenerContainerFactory durableReplyFactory(
        ConnectionFactory cf,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {
    var f = new DefaultJmsListenerContainerFactory();
    configurer.configure(f, cf);
    f.setReplyQosSettings(
            new QosSettings(DeliveryMode.PERSISTENT, 4, 60_000L));
    return f;
}
```

Đây là **hai bean methods minh họa trong một `@Configuration`**, cần các import cùng tên class ở mục 5. Sau đó dùng:

```java
@JmsListener(
        destination = "billing.fast.requests",
        containerFactory = "fastReplyFactory")
@SendTo("billing.fast.replies")
public String fastResponse(String payload) {
    return "ACK:" + payload;
}
```

Nếu không chỉ định `containerFactory`, Spring dùng default factory (thường tên `jmsListenerContainerFactory`) chứ không đoán bean nào có QoS “đúng”. Nếu có nhiều bean `ConnectionFactory`, cần dùng `@Qualifier` để tránh trỏ sai provider.

Không nên tạo `new QosSettings()` và thay priority tại runtime tùy request trên một listener container dùng chung: cấu hình này thiết kế để được đặt trước khi container chạy. Nếu từng reply cần QoS khác nhau theo nghiệp vụ, cân nhắc tự gửi qua publisher chuyên trách hoặc cấu hình nhiều listener/factory phù hợp.

## 13. Lỗi và tình huống dễ nhầm

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Không có reply | Method `void` hoặc không có response destination. | Kiểm tra return type, `JMSReplyTo`, `@SendTo`, Queue/Topic. |
| Có reply nhưng priority mặc định | Listener chạy bằng factory khác; thiếu `setReplyQosSettings`. | Xem `containerFactory` và bean được lựa chọn. |
| Đặt `spring.jms.template.priority=8` mà reply vẫn priority 4 | Thuộc tính đó áp dụng cho `JmsTemplate`, không phải auto-reply của listener. | Cấu hình `replyQosSettings` trên listener factory. |
| Reply có priority 2 nhưng request có priority 8 | Hai message có QoS độc lập. | Đọc headers của request và reply riêng. |
| Reply biến mất sau vài giây | TTL quá ngắn hoặc client đến sau `JMSExpiration`. | Kiểm tra `JMSExpiration`, queue backlog, clock và TTL policy. |
| Reply vào destination khác `@SendTo` | Request đã đặt `JMSReplyTo`; hoặc listener trả `JmsResponse`. | Xem header request và logic quyết định đích. |
| Có reply nhưng không thấy ở Queue | Sai Queue/Topic domain hoặc broker auto-create/ACL. | Kiểm tra `replyPubSubDomain`, resolver, destination mapping. |
| Cấu hình `replyQosFactory` không có hiệu lực | `@JmsListener` thiếu `containerFactory="replyQosFactory"`. | Kiểm tra tên bean chính xác, startup logs. |
| Reply không persistent như kỳ vọng | Provider/broker policy hoặc code gửi thủ công bằng template khác. | Kiểm tra JMSDeliveryMode trên reply, broker và đường gửi. |
| Test lúc được lúc không | Concurrency, prefetch, retry, broker cũ còn backlog hoặc response hết hạn. | Dùng Queue sạch, một consumer, TTL đủ lớn, assert headers. |
| Reply được gửi hai lần | Code vừa tự gửi bằng template vừa trả object cho Spring auto-reply. | Chọn một con đường gửi phản hồi. |
| Listener ném lỗi sau khi có side effect | Transaction/ACK/retry xử lý request và send reply không đồng bộ về tính nhất quán. | Thiết kế transaction, idempotency và integration test. |

### `setReplyQosSettings(null)` nghĩa là gì?

Trong Spring, nếu `replyQosSettings` là `null`, cơ chế gửi reply sử dụng **defaults của JMS producer/provider**; chúng có thể được cấu hình ở broker/application server. Không nên đọc đó thành “priority=0” hay “TTL=0 bắt buộc” trong mọi runtime.

Nếu muốn QoS reply cố định, truyền một `QosSettings` không null; nếu muốn sử dụng defaults quản trị, để null và ghi rõ kỳ vọng bằng integration test.

## 14. Quan hệ với transaction, ACK, redelivery và client timeout

### 14.1. QoS không bảo đảm request-reply exactly-once

`DeliveryMode.PERSISTENT` và TTL 10 giây không bảo đảm client nhận **đúng một reply**. Một listener có thể xử lý request, gửi response, rồi transaction/ACK gặp lỗi; broker redeliver request và ứng dụng có thể tạo reply mới. Producer cũng có thể retry do lỗi network mà không biết lần gửi trước đã tới broker hay chưa.

Thiết kế chắc chắn thường gồm request ID/correlation ID, idempotency ở phía xử lý, timeout của client, chính sách retry/backoff và (nếu cần) transaction manager phù hợp. Khi kết hợp JMS với database, cần xác minh atomicity thực tế hoặc dùng transactional outbox/inbox; không suy diễn từ QoS rằng DB và broker commit cùng lúc.

### 14.2. Reply TTL và thời gian client chờ khác nhau

| Khái niệm | Nơi đặt | Khi nào tính? |
| --- | --- | --- |
| Request TTL | Producer gửi request | Từ lúc request được gửi. |
| Reply TTL | `replyQosSettings.setTimeToLive(...)` | Từ lúc listener gửi reply. |
| Client receive timeout | `JmsTemplate.receiveTimeout` hoặc request-reply API | Thời gian thread client chờ response. |
| Server processing timeout | Logic xử lý nghiệp vụ / orchestrator | Thời gian xử lý request, không phải thuộc tính JMS QoS. |

Ví dụ client chỉ chờ 2 giây nhưng listener xử lý 4 giây: dù reply có TTL 10 giây sau lúc gửi, client vẫn có thể **đã timeout trước khi reply được phát**. Khi đó response còn sống trên broker không có nghĩa client sẽ xử lý nó.

Ngược lại, client chờ 30 giây nhưng reply TTL 5 giây, nếu broker backlog khiến reply quá hạn, client vẫn không nhận được.

### 14.3. Transaction trên listener container

Nếu listener container dùng session transacted, việc ACK request và gửi reply có thể chịu chi phối bởi transaction đó, tùy adapter và cấu hình broker/JTA. Tuy nhiên cấu hình QoS **không tự bật transaction**, và không tự gộp các side effect bên ngoài (database, HTTP) vào cùng một giao dịch. Kiểm tra `sessionTransacted`, `transactionManager` và hành vi rollback/redelivery của môi trường triển khai.

## 15. Kiểm thử có ý nghĩa

Không nên chỉ assert `getReplyQosSettings().getPriority() == 2` rồi coi hệ thống đã đúng; điều đó mới xác nhận giá trị bean, **chưa chứng minh đường auto-reply đã dùng nó**.

### 15.1. Unit test cấu hình

Kiểm tra bean `replyQosFactory` được khởi tạo và rằng listener có `containerFactory="replyQosFactory"`. Nếu test annotation mapping trực tiếp, xác nhận handler có return value và destination hợp lệ. Unit test này giúp phát hiện lỗi tên bean nhưng không thay thế broker test.

### 15.2. Integration test với broker thật

1. Dựng broker test và provision Queue request/reply, chỉ một consumer reply.
2. Gửi request không có `JMSReplyTo`, kiểm tra response xuất hiện ở `@SendTo`.
3. Đọc raw JMS response, assert `getJMSPriority()==2`, `getJMSDeliveryMode()==DeliveryMode.PERSISTENT` và `getJMSExpiration()>0` với TTL dương.
4. Gửi request có `JMSReplyTo` khác; kiểm tra destination được ưu tiên, nhưng QoS reply vẫn như cấu hình.
5. Thử TTL ngắn với delay có kiểm soát, xác minh expiration theo policy của broker. Đừng dựa vào `Thread.sleep` tùy tiện để suy ra bảo đảm thời gian thực.
6. Thử listener `void` và listener gửi thủ công bằng `JmsTemplate` để xác nhận `replyQosSettings` không bị áp dụng nhầm cho những đường không auto-reply.
7. Kiểm tra redelivery khi listener ném exception/rollback và correlation ID khi có nhiều request song song.

Nếu kiểm thử có thể bị ảnh hưởng bởi broker clock, queue backlog hoặc concurrency, thu thập headers, logs, message IDs và business request IDs; tránh khẳng định test flaky là do Spring khi chưa xác định được điểm hỏng.

### 15.3. Theo dõi vận hành

Nên đo số response gửi, queue depth, expired replies, latency xử lý request, latency client nhận reply, retry, DLQ và consumer errors. Không log toàn bộ nội dung reply nếu chứa PII/token. Theo dõi correlation ID đã được chuẩn hóa và che dữ liệu nhạy cảm.

## 16. Bài tập tự luyện

**Bài 1.** Listener có `@SendTo("q.response")`, trả `String`, nhưng request đặt `JMSReplyTo=q.client`. Response được gửi đến đâu trong cơ chế mặc định?

**Đáp án:** `q.client` qua `JMSReplyTo`, không phải `q.response`. Nếu listener trả `JmsResponse` có destination cụ thể thì cần xét lựa chọn đó trước.

**Bài 2.** `QosSettings` có priority=2, TTL=10.000 ms. Đây là QoS của request hay reply khi được đặt bằng `factory.setReplyQosSettings(qos)`?

**Đáp án:** QoS của **reply được Spring tự gửi** từ listener container do factory đó tạo, không tự tác động request.

**Bài 3.** Vì sao không thể dựa vào `jmsTemplate.setPriority(9)` để kết luận reply của một `@JmsListener` có priority 9?

**Đáp án:** `JmsTemplate` và listener auto-reply là hai đường gửi khác nhau. Listener cần `replyQosSettings` trên đúng factory, trừ khi ứng dụng tự dùng chính template ấy để gửi reply.

**Bài 4.** Một request mất 8 giây để xử lý, response được gửi với TTL=10 giây. Response có hết hạn sau 2 giây nữa vì request đã xử lý 8 giây không?

**Đáp án:** Không. Reply TTL bắt đầu từ khi **reply được gửi**, nên về nguyên tắc vẫn có ~10 giây kể từ thời điểm gửi, dù thời gian xử lý request là 8 giây.

**Bài 5.** Nếu listener trả `void` và tự gửi message bằng `myJmsTemplate.convertAndSend(...)`, `setReplyQosSettings` có tự override `myJmsTemplate` không?

**Đáp án:** Không. QoS gửi thủ công theo cấu hình `myJmsTemplate` hoặc `MessageProducer` trực tiếp.

**Bài 6.** Khi cần reply đến Topic nhưng listener nhận request từ Queue, thiết lập nào liên quan domain và thiết lập nào liên quan priority?

**Đáp án:** `setReplyPubSubDomain(true)` cho **domain resolve reply name**, `QosSettings.setPriority(...)` cho **priority gửi reply**. Hai cài đặt độc lập.

**Bài 7.** Có phải `DeliveryMode.PERSISTENT` cộng TTL dài đảm bảo hệ thống nhận và xử lý mỗi reply đúng một lần?

**Đáp án:** Không. Cần xét ACK/transaction, client timeout, redelivery, duplicate và idempotency.

## 17. Tài liệu chính thức

- [Spring Framework – Annotation-driven Listener Endpoints, phần Response Management](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework 6.2 – DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [Spring Framework 6.2 – AbstractJmsListenerContainerFactory.setReplyQosSettings](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/AbstractJmsListenerContainerFactory.html)
- [Spring Framework 6.2 – QosSettings](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/QosSettings.html)
- [Spring Framework 6.2 – AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 6.2 – AbstractAdaptableMessageListener](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/adapter/AbstractAdaptableMessageListener.html)
- [Spring Boot – Messaging with JMS (hướng dẫn cấu hình listener factory)](https://spring.io/guides/gs/messaging-jms/)
- [Spring Boot – Common Application Properties](https://docs.spring.io/spring-boot/3.3/reference/application-properties.html)
- [Jakarta Messaging 3.1 – MessageProducer và JMS message headers](https://jakarta.ee/specifications/messaging/3.1/)

**Ghi nhớ:** `@JmsListener` có giá trị trả về và có destination phản hồi hợp lệ thì **Spring có thể tự tạo và gửi reply**. Muốn điều khiển **delivery mode, priority, TTL của reply ấy**, cấu hình `QosSettings` qua **`DefaultJmsListenerContainerFactory.setReplyQosSettings(...)`** trên đúng factory được listener sử dụng. Đừng nhầm reply QoS với request QoS của `JmsTemplate`, destination lựa chọn bởi `JMSReplyTo/@SendTo`, hoặc yêu cầu transaction/idempotency của hệ thống.
