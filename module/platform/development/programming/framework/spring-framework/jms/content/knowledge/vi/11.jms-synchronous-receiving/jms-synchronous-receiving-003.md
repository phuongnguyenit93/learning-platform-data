# Kết quả null khi hết thời gian chờ khi nhận đồng bộ trong Spring JMS

## 1. Mục tiêu

Khi gọi `JmsTemplate.receive(...)` hoặc `JmsTemplate.receiveAndConvert(...)` để **nhận JMS message đồng bộ**, chương trình thường mong nhận được một thông điệp rồi tiếp tục xử lý. Nhưng điều gì xảy ra nếu không có message phù hợp trước khi hết khoảng chờ? Kết quả thông thường là **`null`**, không phải một JMS message rỗng và cũng không mặc định là một exception.

Đây là tình huống rất quan trọng trong polling, request/reply, worker chạy theo lịch và những ứng dụng phải giới hạn thời gian giữ một thread để chờ message.

Bài sẽ giúp bạn:
- Phân biệt `receive()`, `receive(timeout)` và `receiveNoWait()` ở Jakarta Messaging.
- Hiểu chính xác cách cấu hình `receiveTimeout` trong Spring `JmsTemplate`: **số dương = chờ hữu hạn; `0` = chờ vô hạn; số âm = không chờ**.
- Xử lý `null` đúng cách mà không nhầm với kết nối lỗi, message payload rỗng, Queue không tồn tại hoặc việc consumer bị đóng.
- Viết Java 17+ với cả JMS API gốc và Spring Boot; biết lúc nào cần dùng `receiveAndConvert` hoặc `receiveSelected`.
- Thiết kế retry, timeout policy, metric và transaction/acknowledgement hợp lý cho polling.
- Kiểm thử cả nhánh **có message**, **hết thời gian chờ** và **exception thật**.

Ví dụ dùng **Jakarta Messaging 3.x** (`jakarta.jms.*`), **Spring Framework 6.x** và **Spring Boot 3.5.x**; với Spring/JMS đời cũ có thể gặp namespace `javax.jms`. Các nguyên tắc về `null` và chờ đồng bộ vẫn tương tự, nhưng cần dùng đúng version dependency.

## 2. Nhận đồng bộ diễn ra như thế nào?

Hãy tưởng tượng một worker chỉ muốn đợi tối đa 2 giây để lấy công việc từ Queue `jobs.queue`.

```text
Worker thread                  JMS client / broker
     |                                 |
     | JmsTemplate.receive(...)        |
     |-------------------------------->|
     |  chờ message phù hợp            |
     |                                 +-- Có message trước deadline?
     |                                 |      |
     |                                 |      +-- CÓ -> trả Message
     |                                 |      |
     |                                 |      +-- KHÔNG -> hết thời gian chờ
     |<--------------------------------|
     | message != null ?               |
     |   xử lý message                  |
     | : chuyển qua nhánh "không có"   |
```

**Synchronous receive** có nghĩa thread gọi sẽ đợi theo quy tắc timeout. Nó **không có nghĩa broker chủ động tạo một “null message” rồi gửi đến Queue**. `null` là kết quả API phía client dùng để biểu thị không có message được trả cho lần nhận đó.

Một lần trả `null` không cho phép kết luận rằng Queue vĩnh viễn trống. Message có thể:
- Đến **ngay sau** khi timeout.
- Đã được consumer khác lấy trước.
- Không khớp **message selector** của lần nhận.
- Đang chờ theo delivery delay hoặc bị chính sách broker giữ lại.
- Không thể được giao cho consumer do kết nối chưa `start()` ở API gốc.
- Bị ảnh hưởng bởi lifecycle của consumer (ví dụ bị đóng khi đang chờ).

Điều đúng có thể nói là: **trong cửa sổ chờ của lời gọi cụ thể, không có JMS `Message` được trả về cho caller**.

## 3. Jakarta Messaging API: receive, receive(timeout), receiveNoWait

`jakarta.jms.MessageConsumer` cung cấp ba cách nhận đồng bộ:

| Lời gọi | Cách chờ | Kết quả khi chưa có message phù hợp |
| --- | --- | --- |
| `consumer.receive()` | Đợi cho đến khi có message hoặc consumer bị đóng | Thường tiếp tục chờ; có thể trả `null` khi consumer bị đóng đồng thời. |
| `consumer.receive(2_000)` | Đợi tối đa khoảng 2.000 ms cho message | Trả `null` khi hết thời gian hoặc consumer bị đóng đồng thời. |
| `consumer.receive(0)` | **Đợi vô hạn** (số 0 không phải polling) | Không tự hết timeout; có thể trả `null` khi consumer bị đóng. |
| `consumer.receiveNoWait()` | Kiểm tra message ngay tại thời điểm gọi | Trả `null` nếu chưa có message ngay lập tức. |

**Cực kỳ dễ nhầm:** Trong **JMS API gốc**, `receive(0)` không đồng nghĩa với `receiveNoWait()`. `0` là **không hết hạn**. Nếu bạn muốn kiểm tra tức thời, hãy gọi đúng `receiveNoWait()`.

Theo đặc tả Jakarta Messaging, `receive(long timeout)` chặn đến khi có message, timeout hết hoặc consumer đóng. `close()` trên consumer có thể làm một `receive` đang chờ trả về `null`, nên không phải mọi giá trị `null` đều chứng minh xảy ra timeout. Lỗi nội bộ của provider/transport thông thường được thông báo bằng `JMSException`, không phải bằng cách cố tình trả `null`.

### 3.1. Ví dụ Java JMS gốc có xử lý null

Đoạn dưới là một class dùng lại được trong ứng dụng đã cung cấp `ConnectionFactory` của broker:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class ClassicTimedReceiver {

    public static String pollOnce(ConnectionFactory factory,
                                  String queueName,
                                  long timeoutMillis) throws JMSException {

        if (timeoutMillis <= 0) {
            throw new IllegalArgumentException(
                    "timeoutMillis must be greater than 0");
        }

        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageConsumer consumer =
                     session.createConsumer(session.createQueue(queueName))) {

            connection.start();  // Bắt đầu delivery cho consumer.

            Message message = consumer.receive(timeoutMillis);

            if (message == null) {
                return null;      // Không có message trong lần nhận này.
            }

            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalArgumentException(
                        "Expected TextMessage, got "
                        + message.getClass().getName());
            }

            return textMessage.getText();
        }
    }
}
```

Đây là class Java 17+ có cú pháp hợp lệ khi có Jakarta Messaging 3.x API/provider trên classpath; nó **chưa phải chương trình chạy độc lập** vì `ConnectionFactory` phải được inject hoặc tạo từ một provider cụ thể. Bất kỳ mã gọi nào cũng phải phân biệt nhánh `pollOnce(...) == null` với exception. Ở mức API, `TextMessage.getText()` có thể trả chuỗi rỗng hoặc thậm chí `null` nếu message không có text; vì thế trả `String` đơn thuần từ method này **chưa thể phân biệt mọi trạng thái**. Nếu bạn cần phân biệt chính xác “có TextMessage nhưng body null”, hãy trả `Message` (hoặc kiểu kết quả có cờ `received`) rồi kiểm tra body riêng. Phần `Message` của ví dụ cho thấy điều đó rõ ràng.

**Vì sao phải `connection.start()`?** Trong classic JMS, mặc định delivery đến consumer trên connection chưa được bắt đầu. Nếu quên `start()`, lần `receive(timeout)` có thể trả `null` dù broker có message chờ giao. Lệnh gửi message bằng producer không yêu cầu `start()`, nhưng nhận đồng bộ thông qua connection classic thường cần nó.

**Vì sao dùng `try-with-resources`?** `Connection`, `Session` và `MessageConsumer` là `AutoCloseable` trong Jakarta Messaging 3.x; ứng dụng tự tạo thì phải dọn. Không được giữ `Session` dùng chung tùy ý giữa nhiều thread.

### 3.2. Simplified API với JMSContext/JMSConsumer

Jakarta Messaging còn có `JMSContext` và `JMSConsumer`:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Message;

public final class ContextTimedReceiver {

    public static Message pollOnce(ConnectionFactory factory,
                                   String queueName) {
        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            JMSConsumer consumer =
                    context.createConsumer(context.createQueue(queueName));
            return consumer.receive(2_000L);
        }
    }
}
```

Đây cũng là method cần implementation `ConnectionFactory` ở runtime, chưa có `main`. Simplified API sử dụng chủ yếu `JMSRuntimeException` (unchecked) cho lỗi API, trong khi classic API sử dụng `JMSException` (checked). `JMSContext` mặc định tự bắt đầu connection khi cần (`autoStart` mặc định là `true`). Nếu bạn chủ động tắt auto-start, phải chú ý gọi `context.start()` trước khi chờ nhận.

**Lưu ý lifetime:** một lần `receive` hữu hạn là thao tác blocking; kết thúc `try` sẽ đóng `JMSContext`. Nếu muốn worker nhận liên tục, đừng tạo connection/context mới trong vòng lặp bận rộn mà không cân nhắc cache/pool và lifecycle.

## 4. Spring JmsTemplate: null xuất hiện ở đâu?

Trong Spring Framework, `org.springframework.jms.core.JmsTemplate` cung cấp các overload:

```java
jakarta.jms.Message message = jmsTemplate.receive("jobs.queue");
Object payload = jmsTemplate.receiveAndConvert("jobs.queue");
```

Đây là snippet trong một Spring-managed component có bean `jmsTemplate`. Cả hai đều **nhận đồng bộ**. Chúng sử dụng `ConnectionFactory`, `Session`, `MessageConsumer` và `DestinationResolver` phía dưới nhưng để Spring quản lý vòng đời của các tài nguyên đó.

Kết quả:
- `receive(...)` trả **`jakarta.jms.Message`** khi nhận được, hoặc **`null`** khi lần receive không có message.
- `receiveAndConvert(...)` nhận message rồi dùng `MessageConverter` để đổi sang object Java, hoặc trả **`null`** khi không nhận được message.
- Nếu provider ném checked `JMSException`, Spring thường chuyển thành họ unchecked `org.springframework.jms.JmsException`.
- Nếu JMS message tồn tại nhưng converter không xử lý được, chương trình có thể gặp **`MessageConversionException`** thay vì `null`. Với converter tùy chỉnh, cũng phải xem quy ước payload `null`; muốn phân biệt chắc chắn *không nhận được Message* với *payload không có giá trị*, hãy dùng `receive(...)` rồi kiểm tra `Message` trước khi chuyển đổi.

Một cách diễn đạt đúng:

> `null` của `JmsTemplate.receive(...)` là **không có message được trả về cho lần nhận đó**, thường do hết thời gian chờ; không phải exception và không phải xác nhận broker bị lỗi.

### 4.1. Cách viết an toàn

```java
Message message = jmsTemplate.receive("jobs.queue");

if (message == null) {
    // Không có message trong lần polling này.
    // Có thể trả NO_WORK hoặc lên lịch kiểm tra sau.
} else {
    // Có một JMS Message thật.
    // Chỉ xử lý/convert khi message không null.
}
```

Đây là snippet sử dụng `jakarta.jms.Message`. Không viết `message.getJMSMessageID()`, `message.getBody(...)` hoặc cast sang `TextMessage` trước khi kiểm tra `null`; nếu không bạn sẽ gặp `NullPointerException` vì thiếu message chứ không phải vì lỗi JMS.

Với `receiveAndConvert`:

```java
Object payload = jmsTemplate.receiveAndConvert("jobs.queue");

if (payload == null) {
    System.out.println("NO_WORK");
} else if (payload instanceof String text) {
    System.out.println("WORK=" + text);
} else {
    System.out.println("UNEXPECTED_PAYLOAD_TYPE");
}
```

`String text` là pattern matching `instanceof` của Java 17. Nếu broker gửi `BytesMessage` hay object khác, converter có thể trả kiểu khác hoặc báo lỗi; không giả định mọi payload luôn là `String`.

### 4.2. Nhận null là một nhánh kết quả, không nên dùng exception để thay thế

Mẫu **không phù hợp**:

```java
try {
    Message message = jmsTemplate.receive("jobs.queue");
    process(message); // Có thể NPE nếu hết timeout.
} catch (Exception e) {
    // Coi mọi lỗi đều là Queue rỗng.
}
```

Đây là **anti-pattern**, không phải chương trình hoàn chỉnh. Nó che giấu lỗi kết nối, lỗi cấu hình destination, lỗi converter và lỗi nghiệp vụ. Ngoài ra `process(message)` không được định nghĩa ở snippet này.

Mẫu **đúng ý nghĩa**: tách hai nhánh:

```java
try {
    Message message = jmsTemplate.receive("jobs.queue");
    if (message == null) {
        recordEmptyPoll();
        return;
    }
    process(message);
} catch (org.springframework.jms.JmsException ex) {
    recordReceiveFailure(ex);
    throw ex;
}
```

Đây là method-body minh họa; `recordEmptyPoll`, `recordReceiveFailure`, `process` cần do ứng dụng định nghĩa. Không cần ném exception cho lần nhận không có message nếu polling vốn là thao tác bình thường.

## 5. Cấu hình receiveTimeout: số 0 không có nghĩa “không đợi”

Một `JmsTemplate` dùng chung thường được cấu hình qua `@Bean` hoặc `application.properties`. `receiveTimeout` có đơn vị **millisecond** tại Java API.

| Giá trị `JmsTemplate.setReceiveTimeout(...)` | Hành vi dự kiến |
| --- | --- |
| `2_000L` | Đợi tối đa khoảng 2 giây để nhận một message. |
| `250L` | Đợi tối đa khoảng 250 ms. |
| `0L` | **Đợi vô hạn**; tương đương indefinite receive. |
| `JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT` | Hằng biểu thị `0L`: chờ không có deadline nhận message. |
| `JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT` | Hằng số âm: thử nhận ngay, không blocking chờ message. |
| Một số âm khác | Spring coi là **no-wait**; không truyền âm trực tiếp vào `MessageConsumer.receive(long)`. |

Theo Spring Framework, **mặc định của `JmsTemplate` là chờ vô hạn**. Nếu một endpoint HTTP dùng template mặc định để nhận mà Queue không có message, thread request có thể bị giữ không giới hạn. Vì vậy nên đặt timeout hữu hạn khi mô hình xử lý yêu cầu điều đó.

### 5.1. Set timeout bằng Java

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

public final class TimedTemplateFactory {
    public static JmsTemplate create(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000L);
        return template;
    }
}
```

Đây là class helper Java 17+ trong dự án có `spring-jms` và `ConnectionFactory` đã cấu hình. Method `create` trả một template được thiết lập trước khi đưa cho các thread sử dụng. Trong ứng dụng Spring, nên tạo bean một lần thay vì tạo template mới trên mỗi request.

### 5.2. Cấu hình trong Spring Boot

Với Spring Boot 3.5.x dùng auto-configured `JmsTemplate`, đặt:

```properties
spring.jms.template.receive-timeout=2s
```

Đây là property thời lượng của Spring Boot. `2s` được bind thành khoảng 2.000 ms cho `JmsTemplate`. Bạn có thể đặt `500ms` hoặc `5s` theo nhu cầu. Nếu tự tạo bean `JmsTemplate` tùy chỉnh thay cho auto-configuration, phải kiểm tra rằng bean đó đã được set timeout đúng; không mặc định mọi property của Boot đều tự áp dụng cho instance bạn tự `new`.

### 5.3. Không đợi (no-wait) là một chế độ riêng

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JmsDestinationAccessor;

JmsTemplate noWait = new JmsTemplate(connectionFactory);
noWait.setReceiveTimeout(
        JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT);

Object value = noWait.receiveAndConvert("jobs.queue");
```

Đoạn trên là snippet trong method đã có `connectionFactory`. Nó phù hợp với một lần kiểm tra nhanh, nhưng `null` vẫn có thể xuất hiện khi chưa có message **ngay thời điểm kiểm tra**, kể cả message sẽ đến ngay sau đó. Không cần đổi timeout của một `JmsTemplate` singleton dùng chung liên tục giữa các thread; các tham số template nên được cấu hình trước khi sử dụng đồng thời.

**So sánh trực tiếp hai API:**

```text
Jakarta MessageConsumer.receive(0)        = chờ vô hạn
Jakarta MessageConsumer.receiveNoWait()   = không chờ

Spring JmsTemplate.setReceiveTimeout(0)   = chờ vô hạn
Spring JmsTemplate.setReceiveTimeout(-1)  = không chờ
Spring JmsTemplate.setReceiveTimeout(2000)= đợi tối đa khoảng 2 giây
```

Trong code production, ưu tiên hằng `RECEIVE_TIMEOUT_NO_WAIT` thay vì một literal âm dễ gây nhầm.

### 5.4. receiveTimeout không phải deadline cho toàn bộ request

`receiveTimeout` chủ yếu điều khiển **thời gian chờ nhận message từ consumer**. Việc tạo connection, authentication, destination resolution, session setup, reconnect hoặc cleanup có thể có timeout khác. Vì vậy tổng thời gian method `JmsTemplate.receive(...)` có thể **lớn hơn** giá trị `receiveTimeout`.

Nếu SLA HTTP phải dưới 3 giây, đừng kết luận chỉ cần `receiveTimeout=3000` là endpoint chắc chắn hoàn tất đúng 3 giây. Hãy cấu hình kết nối/network timeout, circuit breaker, request deadline và thử tải với broker thực tế.

## 6. Ví dụ Spring Boot đầy đủ: quan sát timeout, có message và timeout lần nữa

Ví dụ dưới đây dùng:
- **Java 17+** và **Spring Boot 3.5.8**.
- **Apache ActiveMQ Artemis broker bên ngoài**, kết nối native qua TCP.
- `spring-boot-starter-artemis` để có JMS/Jakarta client và Spring JMS.
- `JmsTemplate` được Boot auto-configure với timeout **2 giây**.
- Queue `learning.timeout.queue` **được tạo sẵn** hoặc broker cho phép auto-create Queue theo chính sách.

Demo có ba bước: nhận khi Queue ban đầu trống, gửi một `TextMessage`, nhận message vừa gửi, rồi nhận thêm lần nữa khi Queue đã hết message.

### 6.1. Cấu trúc file

```text
spring-jms-timeout-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── jms/
        │           └── ReceiveTimeoutApplication.java
        └── resources/
            └── application.properties
```

### 6.2. Maven pom.xml

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
    <artifactId>spring-jms-timeout-demo</artifactId>
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

### 6.3. application.properties

```properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}

spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=2s
```

`native` ở đây nghĩa là sử dụng một **broker Artemis đang chạy ngoài ứng dụng**. File properties không khởi động broker. Các giá trị `JMS_USERNAME`/`JMS_PASSWORD` phải được cung cấp từ môi trường. Mật khẩu trong mã nguồn thực tế phải được bảo vệ bằng cơ chế quản lý secret phù hợp.

### 6.4. Java application

**`src/main/java/example/jms/ReceiveTimeoutApplication.java`**

```java
package example.jms;

import jakarta.jms.Message;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ReceiveTimeoutApplication {

    private static final String QUEUE = "learning.timeout.queue";

    public static void main(String[] args) {
        SpringApplication.run(ReceiveTimeoutApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JmsTemplate jmsTemplate) {
        return args -> {
            // Bước 1: Giả định Queue sạch và không có producer khác.
            Message before = jmsTemplate.receive(QUEUE);

            if (before == null) {
                System.out.println("first=NO_MESSAGE");
            } else {
                System.out.println("first=RECEIVED");
            }

            // Bước 2: Gửi một TextMessage bằng converter mặc định.
            jmsTemplate.convertAndSend(QUEUE, "hello-timeout");

            Object received = jmsTemplate.receiveAndConvert(QUEUE);
            if (received == null) {
                System.out.println("second=NO_MESSAGE");
            } else {
                System.out.println("second=" + received);
            }

            // Bước 3: Khi message đã được nhận và không có producer khác,
            // lần nhận tiếp theo thường đợi ~2 giây rồi trả null.
            Message after = jmsTemplate.receive(QUEUE);
            System.out.println(
                    after == null ? "third=NO_MESSAGE" : "third=RECEIVED");
        };
    }
}
```

Giải thích:
1. `@SpringBootApplication` tạo application context và kích hoạt JMS auto-configuration từ starter.
2. Boot inject `JmsTemplate` đã có `receiveTimeout=2s` do property.
3. `jmsTemplate.receive(QUEUE)` lấy một message hoặc trả `null`. Lần đầu trên Queue thật sự trống sẽ đi nhánh `NO_MESSAGE` sau khoảng chờ.
4. `convertAndSend` chuyển Java `String` thành JMS `TextMessage` theo `SimpleMessageConverter` mặc định rồi gửi.
5. `receiveAndConvert` nhận message rồi trả payload `String`, nên lần thứ hai trả `hello-timeout` nếu không có consumer khác giành message.
6. Lần receive cuối trả `null` khi không còn message nào, dùng được để minh họa timeout thêm lần nữa.
7. Không có `@JmsListener` trong ứng dụng này: demo chỉ dùng **nhận đồng bộ**.

### 6.5. Cách chạy

Đảm bảo broker đang hoạt động, Queue `learning.timeout.queue` đã tồn tại hoặc auto-create được bật, và không có publisher/consumer khác trên Queue khi thử nghiệm. **Nên làm sạch Queue trước khi chạy demo**; các lần chạy trước có thể để lại message.

PowerShell:

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"
mvn spring-boot:run
```

POSIX shell:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=dev-user \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Thay `dev-user`/`dev-password` bằng account thực tế có quyền gửi/nhận. Không có Artemis broker thì code có thể compile nhưng sẽ lỗi kết nối tại runtime.

**Stdout từ `System.out.println` khi Queue ban đầu sạch, broker hoạt động, không có consumer khác:**

```text
first=NO_MESSAGE
second=hello-timeout
third=NO_MESSAGE
```

Các log Spring Boot/Artemis sẽ xuất hiện thêm. Không coi 2 giây là thời gian thực thi chính xác tuyệt đối: scheduling, broker/network và thời gian tạo/đóng tài nguyên có thể gây chênh lệch. Nếu Queue có message cũ, bước 1 có thể in `first=RECEIVED`; nếu có consumer tranh nhận hoặc broker chưa sẵn sàng, bước 2 có thể là `NO_MESSAGE` hoặc phát sinh exception.

**Build không cần broker** (trong thư mục chứa `pom.xml`):

```bash
mvn -q -DskipTests package
```

Để xác minh đường đi message thật cần chạy với broker. Không dùng ví dụ để khẳng định “mọi lần chạy đều in ba dòng đúng thế” khi Queue không được cô lập.

## 7. Không nhầm message rỗng, payload null và timeout null

### 7.1. Message tồn tại nhưng payload là chuỗi rỗng

Giả sử broker gửi `TextMessage` có text `""`:

```java
Message message = jmsTemplate.receive("jobs.queue");

if (message == null) {
    // Không nhận được JMS Message.
} else if (message instanceof jakarta.jms.TextMessage text) {
    String body = text.getText();
    if ("".equals(body)) {
        // Đã nhận được Message thật, body là chuỗi rỗng.
    }
}
```

Đây là snippet bên trong method có thể khai báo `throws JMSException` hoặc catch `JMSException` tại `getText()`. Chuỗi rỗng **không** phải `null` của `receive`. Với một `TextMessage` chưa set text, body có thể là `null` dù `Message` tồn tại; kiểm tra `message != null` trước khi phân loại payload.

### 7.2. receiveAndConvert trả null là một abstraction khác

`JmsTemplate.receiveAndConvert` thường trả `null` khi `receive` không lấy được message. Nhưng nếu ứng dụng dùng `MessageConverter` tùy chỉnh có thể trả `null` cho một message hợp lệ, thì kết quả object `null` không còn phân biệt chắc chắn nhánh “không có message” với “converter trả không có giá trị”.

Nếu nghiệp vụ cần phân biệt nghiêm ngặt:
1. Gọi `jmsTemplate.receive(queueName)` để lấy `Message`.
2. Nếu message `null`, xử lý nhánh không nhận được.
3. Nếu message tồn tại, mới đọc header/body hoặc gọi converter theo quy tắc an toàn.
4. Nếu converter ném `MessageConversionException`, xử lý như **lỗi dữ liệu/chuyển đổi**, không phải Queue rỗng.

Trong nhiều service chỉ gửi/nhận `String` bằng `SimpleMessageConverter` mặc định, `receiveAndConvert` đủ tiện. Nhưng những ứng dụng giao thức hoặc audit cần biết chính xác sự tồn tại của Message nên giữ hai tầng phân loại.

### 7.3. Null không phải broker đã gửi “message null”

JMS `Message` là một object có header/properties và body. `null` được API Java dùng làm **sentinel** cho không có message trả về, không phải một message được đưa vào Queue. Không thử `producer.send(null)` như cách tạo một “empty poll” — đây là lỗi API, không phải tín hiệu broker.

## 8. Timeout với message selector và competing consumers

### 8.1. Message selector khiến nhận null dù Queue có message

`JmsTemplate` hỗ trợ `receiveSelected`:

```java
jmsTemplate.setReceiveTimeout(1_500L);

Message urgent = jmsTemplate.receiveSelected(
        "jobs.queue", "priorityGroup = 'URGENT'");

if (urgent == null) {
    // Không có Message khớp selector trong lần chờ này.
    // Không suy ra jobs.queue trống hoàn toàn.
}
```

Đây là snippet khi template chưa được dùng đồng thời; với singleton production, configure timeout trước startup. `priorityGroup` là một JMS message property do producer tự đặt, không phải header priority hệ thống. Nếu Queue chỉ có message `priorityGroup = 'NORMAL'`, consumer lọc `URGENT` có thể chờ đến timeout và nhận `null`, trong khi Queue vẫn có pending message khác.

Nếu bạn dùng `JMSCorrelationID` để đợi reply, tương tự:

```java
String id = java.util.UUID.randomUUID().toString();
String selector = "JMSCorrelationID = '" + id + "'";
Message reply = jmsTemplate.receiveSelected("replies.queue", selector);

if (reply == null) {
    // Reply theo correlation ID chưa đến trong timeout này.
}
```

Ví dụ giả định producer/responder đã biết id và set JMSCorrelationID tương ứng. `UUID` không chứa dấu nháy đơn nên selector được dựng đúng trong ví dụ; nếu nhận ID từ user, cần tránh selector injection/escaping sai. **Timeout reply** có thể do responder chậm hoặc reply đến sau; nó không hủy request đã gửi.

### 8.2. Nhiều consumer trên một Queue

Trong mô hình competing consumers, một message thường được giao cho **một** consumer tại một thời điểm để xử lý theo semantics broker. Nếu worker A và B cùng gọi `receive`:

```text
Queue có đúng một message
       |
       +---- Worker A nhận được Message
       |
       +---- Worker B hết thời gian chờ -> null
```

Worker B không thể suy ra Queue “chưa từng có message”. Chỉ có thể kết luận **B không lấy được message trong khoảng nó chờ**. Prefetch, consumer priority, transaction rollback và chính sách redelivery có thể ảnh hưởng tiến trình phân phối; “message phải được chia đều giữa các worker” không phải cam kết của một lần polling.

### 8.3. Topic và subscription

Với Topic, message được phát theo subscription, không giống một Queue lưu đơn vị công việc cho worker. Nếu subscriber chưa hoạt động khi publisher phát message, non-durable subscription có thể không nhận message cũ. Một lần nhận đồng bộ trên Topic trả `null` không nhất thiết đồng nghĩa Topic chưa hề có publication.

Để dùng Topic với Spring JMS cần `pubSubDomain=true` và cấu hình subscription/durable nếu cần replay theo cơ chế provider; không chỉ thay chuỗi tên destination rồi suy ra semantics Queue vẫn giữ nguyên.

## 9. Timeout không phải JMSException: xử lý nghiệp vụ thế nào?

Bảng sau rất hữu ích khi thiết kế service polling:

| Trạng thái | Java/Spring trả về | Ý nghĩa hợp lý | Phản ứng nên cân nhắc |
| --- | --- | --- | --- |
| Message đến trước deadline | `Message != null` | Có một message được nhận | Xử lý payload và acknowledgement/transaction theo thiết kế. |
| Không có message phù hợp trước deadline | `Message == null` | Lần poll hiện tại không nhận được message | Trả `NO_WORK`, lên lịch poll sau hoặc giữ response rỗng. |
| Consumer bị đóng khi đang chờ | Có thể `Message == null` | Lời gọi bị kết thúc vì lifecycle | Phân biệt với shutdown/cancellation bằng trạng thái ứng dụng. |
| Broker/connection/JMS provider lỗi | Thường `JMSException` hoặc `JmsException` | Failure thật, không phải Queue rỗng | Log, retry/backoff, cảnh báo và health monitoring. |
| Destination/permission sai | Thường exception | Cấu hình hoặc quyền truy cập có vấn đề | Sửa config/authorization, không polling lại vô hạn. |
| Nhận message nhưng converter lỗi | `MessageConversionException` | Có message nhưng payload không hợp lệ với converter | Xử lý poison message/transaction và DLQ. |
| Nhận body là `""` | `Message != null`, text rỗng | Có message thực, body rỗng | Áp dụng validation nghiệp vụ, không coi là timeout. |

Không nên map mọi `null` thành HTTP `500`, vì poll không có dữ liệu thường là trạng thái bình thường. Nhưng cũng không nên map mọi lỗi broker thành HTTP `204 No Content`: client cần nhận biết service lỗi để retry hoặc cảnh báo. Mã HTTP phụ thuộc API contract; ví dụ một endpoint polling có thể trả `204` khi không có công việc, `200` khi có công việc và `503` khi broker tạm unavailable.

**Quan trọng:** nhận `null` không tạo một “negative acknowledgement”. Không có JMS message nào được giao cho caller để ack/commit, nên không có “message rỗng” cần gửi DLQ.

## 10. Transaction và acknowledgement: null có làm mất message không?

Thông thường **không**. Timeout không làm một message chưa được giao biến mất khỏi Queue. Một message có thể đến sau và được nhận ở lần poll kế tiếp; tuy nhiên expiry, purge, competing consumers, DLQ, routing và broker policy vẫn có thể tác động tới những message thực tế đang tồn tại.

Bạn cần phân biệt **timeout trước khi nhận được** với **lỗi sau khi đã nhận một message**:

### 10.1. AUTO_ACKNOWLEDGE

Trong classic `Session.AUTO_ACKNOWLEDGE`, acknowledgement diễn ra theo semantics của JMS provider/receive. Nếu một `receive(timeout)` trả `null`, không có message được chuyển cho ứng dụng nên không có message nào cần acknowledge cho lần gọi đó.

Nhưng khi `receive` trả **một message thực**, ứng dụng phải cẩn trọng: nếu tiếp tục ghi database ngoài transaction rồi thất bại, AUTO_ACKNOWLEDGE không tự biến kết quả database thành JMS rollback. Đừng kỳ vọng ném exception trong method Java sau khi đã nhận có thể khiến broker phát lại message theo ý muốn trong mọi chế độ ack.

### 10.2. CLIENT_ACKNOWLEDGE

Với classic API, consumer có thể dùng `Session.CLIENT_ACKNOWLEDGE` để điều khiển việc xác nhận sau xử lý phù hợp. Nhưng với `JmsTemplate.receive(...)`, Spring template có xử lý acknowledge theo lifecycle của chính nó khi nhận được message; không nên coi việc gọi `receive` trên template giống hệt một vòng client-managed raw `Session` kéo dài qua nhiều bước nghiệp vụ.

Nếu cần xử lý business logic trước ack/commit, hãy chọn một mô hình listener transacted hoặc session/transaction được quản lý rõ ràng. Đừng copy một đoạn mã `message.acknowledge()` từ raw JMS rồi kỳ vọng cùng hiệu quả khi message đã được template receive và dọn session.

### 10.3. Local JMS transaction

Với `Session.SESSION_TRANSACTED` hoặc `JmsTransactionManager`, một message đã nhận sẽ được quyết định bởi **commit/rollback** của session/transaction. Nếu `receive(timeout)` trả `null`, về cơ bản không có message mới được nhận trong lần đó để rollback. Có thể có những thao tác khác đang thuộc cùng session transaction; không tự kết luận “transaction hoàn toàn không có gì” chỉ từ một lần receive null.

**Cảnh báo:** `JmsTransactionManager` chỉ quản lý JMS resource; transaction database không mặc nhiên atomic cùng JMS. Nếu hệ thống cần kết hợp ghi SQL và xử lý message an toàn, cân nhắc outbox/inbox, idempotency hoặc XA/JTA được cấu hình thực sự.

## 11. Thiết kế polling hiệu quả và tránh busy loop

Một sai lầm thường gặp là đặt timeout không đợi rồi lặp liên tục:

```java
while (true) {
    Object payload = jmsTemplate.receiveAndConvert("jobs.queue");
    if (payload == null) {
        continue; // Busy spin nếu receiveTimeout là no-wait.
    }
    handle(payload);
}
```

Đây là **anti-pattern**: không có chính sách dừng, không có backoff và method `handle` chưa được định nghĩa. Với `receiveTimeout < 0`, vòng lặp có thể tạo áp lực CPU, connection/session và broker rất lớn khi Queue rỗng.

### 11.1. Polling hữu hạn với backoff và shutdown flag

Một mẫu định hướng rõ hơn:

```java
public void pollLimited(int maxAttempts) throws InterruptedException {
    for (int attempt = 0; attempt < maxAttempts; attempt++) {
        Object payload = jmsTemplate.receiveAndConvert("jobs.queue");

        if (payload != null) {
            handle(payload);
            return;
        }

        // Không có message: chờ trước lần poll tiếp theo.
        Thread.sleep(500L);
    }
}
```

Đây là snippet thuộc service có field `jmsTemplate`, method `handle` do ứng dụng định nghĩa, và chỉ phù hợp cho thread worker chuyên dụng; **không** nên dùng nguyên dạng trong HTTP request thread, vì nó có thể giữ thread lâu. Template nên có timeout hữu hạn và `maxAttempts` được giới hạn. Trong ứng dụng production, cần cờ shutdown/interrupt và chính sách backoff theo tải.

Nếu cứ polling liên tục để xử lý công việc, thường lựa chọn tốt hơn là **`@JmsListener` + Spring listener container**. Container quản lý vòng đời consumer, concurrency, acknowledge, recovery và chờ message; code nghiệp vụ chỉ định nghĩa xử lý khi có message.

### 11.2. Không đổi timeout của bean chung theo từng request

`JmsTemplate` được thiết kế để dùng chung sau khi cấu hình. Việc một request gọi `setReceiveTimeout(100)` rồi request khác gọi `setReceiveTimeout(5000)` trên cùng singleton có thể tạo hành vi khó dự đoán dưới concurrency.

Cách rõ hơn:
- Một template dùng cho batch worker với timeout khoảng vài giây.
- Một template khác đã cấu hình **no-wait** cho quick check.
- Hoặc dùng provider API cho trường hợp cần kiểm soát consumer/timeout theo từng invocation.

Không tạo một connection factory mới mỗi lần chỉ để đổi timeout. Cấu hình resource và caching/pooling cần tách khỏi mục tiêu thời gian chờ từng worker.

### 11.3. Timeout cho request/reply

Với request/reply, một lần `null` từ Queue reply theo correlation ID thường chỉ có nghĩa **reply chưa đến trước hạn**. Request có thể vẫn đang được xử lý ở phía responder.

Vì vậy cần:
- Correlation ID hoặc request ID ổn định.
- Deadline được trao đổi rõ trong hợp đồng API.
- Xử lý **late reply** (đến sau khi caller bỏ chờ).
- Retry request chỉ khi đã phân tích tính idempotent của responder.
- Metrics riêng cho reply timeout và request failures.

Không tự động gửi lại một tác vụ có tác dụng phụ khi thiếu reply, vì request đầu tiên có thể đã được xử lý thành công.

## 12. Logging, monitoring và phân biệt nguyên nhân

### 12.1. Nên ghi gì khi null?

Ví dụ log theo structured fields:

```text
event=jms_receive_timeout destination=jobs.queue wait_ms=2000 outcome=no_message
```

Nên dùng `DEBUG` hoặc metric cho những timeout polling bình thường, thay vì spam `ERROR` mỗi khi Queue trống. Nếu tỷ lệ timeout tăng đột ngột tại một workflow vốn phải có nhiều công việc, có thể tạo cảnh báo dựa trên **SLO/throughput kỳ vọng**, không chỉ dựa trên một lần null.

Các chỉ số hữu ích:
- `jms_receive_attempt_total` và `jms_receive_timeout_total`.
- `jms_receive_success_total`, `jms_receive_error_total`.
- Thời gian thực của `receive` (p50/p95/p99).
- Queue depth/pending, consumer count, in-flight và redelivery count từ broker.
- Số lần message không khớp selector hoặc reply hết hạn.
- Thời gian kết nối, authentication failures và broker reconnect.

### 12.2. Dùng elapsed time để chẩn đoán, không dùng để thay thế API status

Một `receive` trả `null` sau khoảng 2 giây là phù hợp với timeout 2.000 ms. Nhưng nếu trả `null` sớm bất thường, hãy kiểm tra no-wait config, concurrent close/shutdown, selector, connection start hoặc cấu hình timeout bị đổi. Nếu elapsed time lớn hơn 2 giây nhiều, kiểm tra connection/setup/recovery và thread scheduling.

Không dựa vào `System.currentTimeMillis()` để tạo deadline chính xác trong code nhạy thời gian vì đồng hồ wall clock có thể thay đổi; đo khoảng thời gian với `System.nanoTime()` hoặc metrics timer. Dù đo chính xác, nó không giúp xác định nguyên nhân cụ thể nếu không có trạng thái consumer và broker.

## 13. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `receive(0)` được coi là no-wait | JMS và Spring dùng `0` cho chờ vô hạn | Dùng `receiveNoWait()` hoặc hằng `RECEIVE_TIMEOUT_NO_WAIT` của Spring. |
| Không cấu hình timeout ở request thread | Template mặc định có thể block vô hạn | Đặt `spring.jms.template.receive-timeout` hữu hạn. |
| `message.getBody(...)` khi message null | Gây `NullPointerException` | Kiểm tra message khác null trước khi đọc. |
| Ném `JMSException` khi Queue chưa có message | Timeout là trạng thái bình thường trong polling | Nhánh `NO_WORK`/empty result, log/metric phù hợp. |
| Nuốt mọi `JmsException` rồi trả empty | Che lỗi broker, destination, permission | Tách đường exception và null; có retry/backoff theo loại lỗi. |
| Dùng `receiveAndConvert` rồi cast ngay | Null hoặc kiểu payload khác gây NPE/CCE | Kiểm tra null và kiểu payload; xử lý lỗi converter riêng. |
| Suy ra Queue trống vì `receiveSelected` null | Message không khớp selector vẫn có thể tồn tại | Kiểm tra selector, Queue depth và chính sách provider. |
| Không `connection.start()` trong classic API | Delivery không bắt đầu, nhận có thể timeout | Gọi `start` trước khi receive. |
| Thấy null rồi liên tục retry không chờ | Busy loop/CPU và tăng broker load | Timeout hữu hạn, backoff hoặc `@JmsListener`. |
| Chia sẻ và sửa `receiveTimeout` trong nhiều request | Race cấu hình, độ trễ không dự đoán | Cấu hình template bất biến sau startup. |
| Dùng timeout làm cam kết API response time | Setup/cleanup/network có thể lâu hơn | Áp deadline tổng thể, kiểm soát connection và circuit breaker. |
| Coi timeout như message bị mất | Có thể message đến sau hoặc bị consumer khác lấy | Phân biệt polling result và queue state. |
| Coi null là đồng nghĩa “broker offline” | Broker offline thường có exception | Theo dõi connection health và exception riêng. |
| Nhầm null của body và null của Message | TextMessage có thể tồn tại nhưng text trống/null | Kiểm tra Message trước rồi mới kiểm tra body. |
| Đổi sang Topic nhưng giữ assumptions Queue | Non-durable subscription có delivery semantics khác | Cấu hình subscription và domain đúng. |

## 14. Kiểm thử: bốn kịch bản tối thiểu

### Kịch bản A: Queue trống → timeout null

1. Provision Queue test độc lập và bảo đảm không có producer/consumer khác.
2. Set `receiveTimeout=500ms` hoặc `2s`.
3. Gọi `jmsTemplate.receive(queue)`.
4. Xác minh trả `null`, **không phải JMS exception**.
5. Đo khoảng chờ xấp xỉ timeout; chừa sai số scheduling/network.

Không viết test khẳng định elapsed time chính xác tuyệt đối bằng 500.000.000 ns. Kiểm tra theo khoảng hợp lý, hoặc dùng provider giả lập trong unit test để không phụ thuộc clock/broker.

### Kịch bản B: Message đến trước timeout → nhận thành công

1. Tạo/gửi `TextMessage` tới Queue.
2. Gọi `receive` trong thời gian còn message.
3. Kiểm tra `Message != null` và body phù hợp.
4. Kiểm tra queue/consumer count theo broker và ack mode. Nếu có consumer khác, kết quả cần được đánh giá theo cơ chế competing consumers.

### Kịch bản C: Message đến sau timeout → lần đầu null, lần sau có message

Ví dụ: worker đợi 500 ms, producer cố ý gửi sau 900 ms. Lần đầu có thể `null`, nhưng lần nhận tiếp theo có thể lấy message (nếu không bị consumer khác lấy/expire). Điều này chứng minh timeout **không hủy việc publish** và không tự xóa message sẽ đến sau.

Đừng làm test phụ thuộc chính xác vào `Thread.sleep(900)` dưới CI rất bận rồi cho rằng race luôn lặp lại; nên dùng đồng bộ hóa/fake clock/test harness và thời gian đủ xa nhau.

### Kịch bản D: Broker lỗi → exception khác null

1. Dùng endpoint sai hoặc tắt broker khi test.
2. Gọi `receive`.
3. Kiểm tra đường exception hoặc health/recovery mà provider đưa ra.
4. Đảm bảo application không biến lỗi kết nối thành “Queue trống”.
5. Kiểm tra retry/backoff/alert không khiến hệ thống tạo request storm.

### Unit test nhánh null không cần broker

Tách policy vào một method đơn giản và mock `JmsTemplate`:

```java
// Snippet minh họa trong test đã khai báo Mockito và service tương ứng.
when(jmsTemplate.receive("jobs.queue")).thenReturn(null);

PollResult result = service.pollOnce();

assertEquals(PollResult.NO_WORK, result);
verify(jmsTemplate).receive("jobs.queue");
```

Đây không phải test class tự chạy: `PollResult` và `service` là kiểu của ứng dụng, `when/verify` đến từ Mockito, `assertEquals` từ JUnit. Mục tiêu là khẳng định **nhánh null được xử lý**, không chứng minh broker đã timeout đúng thời lượng. Integration test mới kiểm tra hành vi provider thật.

## 15. Checklist triển khai production

- Xác định nghiệp vụ có cho phép “không có message” như trạng thái bình thường hay không.
- Set `receiveTimeout` hữu hạn cho các thread cần giữ SLA; không để mặc định vô hạn mà không biết.
- Xử lý `Message == null` trước khi đọc headers/body, cast hoặc convert.
- Không gọi `receive(0)` với ý nghĩ “kiểm tra ngay”; dùng `receiveNoWait` hoặc hằng no-wait tương ứng.
- Phân biệt `null`, lỗi broker, thiếu quyền, sai destination, lỗi converter và consumer shutdown.
- Nếu dùng selector, giải thích `null` là không có message **phù hợp selector** trong lần chờ.
- Nếu có competing consumers, không suy trạng thái toàn Queue từ kết quả của một worker.
- Thiết kế acknowledge/transaction để không mất message khi xử lý business lỗi **sau khi đã nhận**.
- Đặt backoff/giới hạn retry cho polling; ưu tiên `@JmsListener` khi cần tiêu thụ liên tục.
- Đo timeout rate, success/error rate, receive latency và Queue backlog tách biệt.
- Kiểm tra contract request/reply, late reply và idempotency trước khi tự động gửi lại.
- Kiểm thử với broker thật và cả nhánh null, có message, lỗi, shutdown; làm sạch Queue test để tránh flaky.

## 16. Tự kiểm tra

**Câu 1.** `JmsTemplate.setReceiveTimeout(0)` có nghĩa kiểm tra Queue ngay lập tức không?

**Không.** Giá trị `0` mang nghĩa chờ vô hạn; dùng `RECEIVE_TIMEOUT_NO_WAIT` hoặc số âm trong Spring để không chờ.

**Câu 2.** `consumer.receive(1500)` trả null thì chắc chắn broker bị ngắt mạng?

**Không.** Trường hợp thường gặp là không có message phù hợp trong khoảng 1,5 giây. Lỗi broker/provider thông thường được ném `JMSException`; concurrent consumer close cũng có thể trả null.

**Câu 3.** Nếu dùng `receiveSelected("jobs.queue", "type = 'A'")` trả null, có thể kết luận Queue trống không?

**Không.** Queue vẫn có thể chứa message loại B; selector chỉ nhận loại A.

**Câu 4.** Vì sao cần `connection.start()` khi dùng classic JMS `MessageConsumer`?

Vì delivery đến consumer trên classic connection không tự bắt đầu trước `start()`; quên gọi có thể khiến `receive(timeout)` trả null dù có message đang chờ.

**Câu 5.** `receiveAndConvert` trả null có đồng nghĩa ứng dụng đã xử lý được message rỗng không?

**Không.** Với converter thông thường, null biểu thị không nhận được message; nếu cần phân biệt triệt để null payload/converter với null Message, hãy dùng `receive` và kiểm tra object trước.

**Câu 6.** Null do timeout có làm Queue message bị chuyển vào DLQ không?

**Không trực tiếp.** Không có message được giao trong lần đó để bị reject/rollback. DLQ liên quan chính sách lỗi xử lý, redelivery, expiry hoặc broker-specific routing.

**Câu 7.** Làm sao tránh worker bận rộn khi polling liên tục mà Queue trống?

Dùng receive timeout thích hợp, giới hạn lần thử/backoff, shutdown policy; hoặc chuyển sang `@JmsListener` để container quản lý vòng đời consumer.

## Kết luận

Trong **nhận đồng bộ Spring JMS**, `null` là kết quả hợp lệ khi một lần `receive` không lấy được `Message`, thường do **hết thời gian chờ**. Nó không phải JMS message rỗng, không tự chứng minh Queue trống tuyệt đối và không thay thế một exception kết nối/provider.

Điểm kỹ thuật quan trọng nhất: **`receiveTimeout > 0` chờ hữu hạn; `receiveTimeout = 0` chờ vô hạn; giá trị âm trong `JmsTemplate` là không chờ**. Hãy kiểm tra `null` trước khi truy cập message, xử lý exceptions riêng, phân biệt selector/competing consumers, và thiết kế retry/acknowledgement theo yêu cầu nghiệp vụ. Một lần timeout chỉ kết thúc **lần chờ đó**, không xác nhận một công việc chưa tồn tại hoặc sẽ không tới về sau.

## Tài liệu tham khảo

- Spring Framework — Receiving a Message, `receive` và `receiveTimeout`: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework 6.2 — `JmsTemplate` API, `setReceiveTimeout`/`receive`/`receiveAndConvert`: https://www.javadoc.io/static/org.springframework/spring-jms/6.2.13/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.2 — `JmsDestinationAccessor` timeout constants và `receiveFromConsumer`: https://www.javadoc.io/static/org.springframework/spring-jms/6.2.13/org/springframework/jms/support/destination/JmsDestinationAccessor.html
- Jakarta Messaging 3.1 — `MessageConsumer` API: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer
- Jakarta Messaging 3.1 — Specification, synchronous receive và message acknowledgement: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework — `JmsOperations` API: https://www.javadoc.io/static/org.springframework/spring-jms/6.2.13/org/springframework/jms/core/JmsOperations.html
- Spring Boot 3.5 — Artemis JMS integration: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Boot 3.5 — Common properties, `spring.jms.template.receive-timeout`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/