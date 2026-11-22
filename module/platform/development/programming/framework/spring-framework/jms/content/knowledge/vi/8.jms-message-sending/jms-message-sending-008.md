# Truy cập MessageProducer qua ProducerCallback trong Spring JMS

## 1. ProducerCallback giải quyết bài toán gì?

Khi gửi thông điệp bằng **Spring JMS**, cách thông thường nhất là gọi `JmsTemplate.send(...)` hoặc `convertAndSend(...)`. Spring sẽ tạo/lấy `Connection`, `Session`, `MessageProducer`, gửi message rồi giải phóng tài nguyên theo lifecycle của framework.

Tuy nhiên có trường hợp mã gửi cần **điều khiển trực tiếp một `jakarta.jms.MessageProducer`**: gửi nhiều message trong cùng một lần thao tác, đặt Quality of Service (QoS) trên producer, tạo message phức tạp bằng một `Session`, hoặc lấy kết quả xử lý bên trong callback. Khi đó, **`org.springframework.jms.core.ProducerCallback<T>`** là API phù hợp.

```text
Service
  |
  | jmsTemplate.execute(destination, ProducerCallback<T>)
  v
JmsTemplate
  |-- lấy Connection qua ConnectionFactory
  |-- tạo/lấy JMS Session
  |-- resolve destination (nếu có tên)
  |-- tạo JMS MessageProducer
  |-- gọi callback.doInJms(session, producer)
  |       |-- session.createTextMessage(...)
  |       |-- producer.setPriority(...), setTimeToLive(...)
  |       |-- producer.send(message), có thể lặp nhiều lần
  |       +-- return kết quả T
  |-- đóng/release producer và session/connection theo contract
  v
Service nhận kết quả T (hoặc lỗi)
```

**ProducerCallback không phải một loại JMS message, không phải listener, và cũng không phải một class triển khai `MessageProducer`.** Nó chỉ là **functional interface của Spring**, nhận hai đối tượng JMS đã được chuẩn bị rồi thực hiện công việc trong phạm vi callback.

Sự khác biệt cốt lõi:

- `MessageCreator`: Spring cho **`Session`** để tạo **một `Message`**; `JmsTemplate.send` tự gửi message.
- `MessagePostProcessor`: sửa message **sau chuyển đổi** nhưng trước khi Spring gửi; thường dùng để đặt header/property.
- `SessionCallback<T>`: truy cập trực tiếp **`Session`** để làm thao tác JMS ở mức thấp.
- `ProducerCallback<T>`: truy cập **cả `Session` và `MessageProducer`**, đặc biệt thuận tiện khi cần trực tiếp gửi nhiều message hoặc cấu hình producer.

**Nguyên tắc:** chỉ dùng `ProducerCallback` khi thực sự cần điều khiển producer; không cần thay mọi lệnh `convertAndSend` bằng callback phức tạp.

## 2. API chính xác và cách đọc chữ ký

Trong **Spring Framework 6 / Jakarta Messaging 3.x**, interface được khai báo theo ý nghĩa:

```java
package org.springframework.jms.core;

@FunctionalInterface
public interface ProducerCallback<T> {
    T doInJms(
        jakarta.jms.Session session,
        jakarta.jms.MessageProducer producer
    ) throws jakarta.jms.JMSException;
}
```

Đây là **chữ ký đơn giản hóa để học API**, không phải file mã nguồn Spring dùng để compile lại framework. `T` là **kiểu kết quả**, có thể là `Integer`, `String`, record của ứng dụng hoặc `Void` (trả `null`).

Ba overload quan trọng của `JmsTemplate`:

```java
<T> T execute(ProducerCallback<T> action);

<T> T execute(
    String destinationName,
    ProducerCallback<T> action
);

<T> T execute(
    jakarta.jms.Destination destination,
    ProducerCallback<T> action
);
```

Những chữ ký này mô tả API; các API thực tế có annotation nullable và ném `org.springframework.jms.JmsException` nếu lỗi.

| Overload | Producer được tạo theo destination nào? | Trường hợp dùng |
| --- | --- | --- |
| `execute(callback)` | Dùng **default destination name/object** trên template nếu đã cấu hình; **nếu không có default, tạo producer không gắn destination**. | Có một đích mặc định, hoặc muốn unbound producer để gửi nhiều đích qua `send(destination, message)`. |
| `execute("orders.out", callback)` | Resolve chuỗi `orders.out` thành `Destination`, rồi tạo producer gắn đích đó. | Gửi tới một Queue/Topic được xác định theo tên. |
| `execute(destination, callback)` | Dùng `Destination` object đã có; nếu truyền `null` thì producer không gắn destination. | Destination đã được tạo/inject/JNDI lookup. |

### Lambda hoạt động thế nào?

```java
Integer sent = jmsTemplate.execute(
    "orders.out",
    (session, producer) -> {
        producer.send(session.createTextMessage("Xin chào JMS"));
        return 1;
    }
);
```

Đây là **snippet nằm trong một method đã có bean `JmsTemplate jmsTemplate`**. Java suy ra tham số lambda gồm `Session` và `MessageProducer`; `return 1` trở thành kết quả của `execute`. Điều này **không đồng nghĩa** một consumer đã nhận message hay broker đã xử lý nghiệp vụ thành công.

### Dạng anonymous class tương đương

```java
Integer sent = jmsTemplate.execute(
    "orders.out",
    new ProducerCallback<Integer>() {
        @Override
        public Integer doInJms(
                Session session,
                MessageProducer producer) throws JMSException {
            producer.send(session.createTextMessage("Xin chào JMS"));
            return 1;
        }
    }
);
```

Snippet cần các import `jakarta.jms.Session`, `jakarta.jms.MessageProducer`, `jakarta.jms.JMSException`, `org.springframework.jms.core.ProducerCallback` và biến `jmsTemplate`. Với Java 17+, **lambda ngắn gọn hơn** nhưng ngữ nghĩa không đổi.

## 3. Session và MessageProducer có vai trò khác nhau

Callback nhận hai đối tượng:

**`Session`**:

- Tạo message: `session.createTextMessage(String)`, `createBytesMessage()`, `createMapMessage()`, v.v.
- Tạo destination động khi cần: `session.createQueue("name")` hoặc `session.createTopic("name")`.
- Mang ngữ cảnh JMS của một connection, và **có thể** tham gia local/JTA transaction tùy cấu hình.
- Không nên dùng đồng thời từ nhiều thread; đừng lưu `Session` bên ngoài callback để sử dụng sau.

**`MessageProducer`**:

- Thực hiện gửi: `producer.send(message)` khi producer đã gắn destination; hoặc `producer.send(destination, message)` khi producer không gắn destination.
- Có QoS producer như `setDeliveryMode`, `setPriority`, `setTimeToLive`, `setDeliveryDelay` (theo khả năng JMS/provider).
- Là đối tượng có lifecycle gắn với `Session`; Spring tạo và đóng nó trong `JmsTemplate.execute(ProducerCallback)`.
- Không được capture vào field, trả về như kết quả để sử dụng sau, hoặc truyền sang một thread khác làm việc sau callback.

Quan hệ giữa các đối tượng:

```text
ConnectionFactory -> Connection -> Session
                                    |
                                    +-> MessageProducer -> gửi Message
                                    |
                                    +-> createTextMessage(...)
```

**Không** dùng `new MessageProducer()` hay `new TextMessage()`: chúng là interface được provider triển khai. Spring tạo producer bằng `Session.createProducer(destination)`, còn message tạo từ session đang được cung cấp.

## 4. Producer gắn destination và producer không gắn destination

Đây là điểm quan trọng nhất khi đọc hoặc debug `ProducerCallback`.

### 4.1. Producer gắn destination

```java
jmsTemplate.execute("orders.out", (session, producer) -> {
    producer.send(session.createTextMessage("ORDER-1"));
    producer.send(session.createTextMessage("ORDER-2"));
    return null;
});
```

Spring resolve tên `"orders.out"`, tạo `producer` gắn với destination đó. Do đó `producer.send(message)` dùng **đích đã gắn** cho cả hai message. Với tên String, `pubSubDomain=false` và `DynamicDestinationResolver` mặc định thường resolve thành Queue; với `true` thường resolve thành Topic.

### 4.2. Producer dựa trên default destination

Giả sử cấu hình:

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDefaultDestinationName("orders.out");
```

Khi đó:

```java
template.execute((session, producer) -> {
    producer.send(session.createTextMessage("ORDER-3"));
    return null;
});
```

Spring dùng default destination đã thiết lập để tạo producer gắn đích `orders.out`. Snippet nằm trong một method có `ConnectionFactory connectionFactory` hợp lệ, không phải chương trình standalone.

### 4.3. Không cấu hình default destination: producer có thể unbound

Khác với `jmsTemplate.send(MessageCreator)` thường yêu cầu default destination, `JmsTemplate.execute(ProducerCallback)` **có thể** chạy khi không có default destination. Spring tạo producer với destination `null` theo cơ chế tương ứng.

Khi producer **không gắn đích**:

```java
jmsTemplate.execute((session, producer) -> {
    Queue audit = session.createQueue("orders.audit");
    Queue notifications = session.createQueue("orders.notifications");

    producer.send(audit, session.createTextMessage("AUDIT-1"));
    producer.send(notifications,
                  session.createTextMessage("NOTIFY-1"));
    return null;
});
```

Đoạn trên giả định template **không có default destination** và resolver/provider cho phép các Queue này. Cần import `jakarta.jms.Queue`; khi producer là unbound, hãy sử dụng overload **`send(Destination, Message)`**. Gọi `producer.send(message)` trên unbound producer không có destination để gửi, thường gây `InvalidDestinationException`.

**Đừng nhầm** `execute(callback)` với `send(messageCreator)`: chúng có đường xử lý mặc định khác nhau. Nếu muốn gửi tới **một đích cụ thể**, dùng `execute("name", callback)` rõ ràng, dễ bảo trì hơn.

### 4.4. Chọn destination object

Nếu app đã có bean `jakarta.jms.Queue ordersQueue` tương thích với factory hiện tại:

```java
jmsTemplate.execute(ordersQueue, (session, producer) -> {
    producer.send(session.createTextMessage("ORDER-4"));
    return null;
});
```

Khác với String name, object `Queue` đã mang danh tính đích của provider. **Không** lấy object Queue của provider/broker A rồi dùng với Session của broker B và kỳ vọng luôn hoạt động.

## 5. Lần gửi đơn giản nhất với ProducerCallback

Khi cần trực tiếp đặt metadata và gửi một message, code điển hình:

```java
int submitted = jmsTemplate.execute("events.orders", (session, producer) -> {
    TextMessage message = session.createTextMessage(
            "{\"eventType\":\"ORDER_CREATED\",\"orderId\":42}"
    );
    message.setStringProperty("contentType", "application/json");
    message.setStringProperty("eventType", "ORDER_CREATED");
    message.setIntProperty("schemaVersion", 1);

    producer.send(message);
    return 1;
});
```

Đây là đoạn **trong method có `JmsTemplate` và import `jakarta.jms.TextMessage`**.

- `session.createTextMessage(...)` tạo một body kiểu `String`; JSON ở đây **vẫn là text**, JMS không tự parse thành Java object.
- Các `setXxxProperty` tạo metadata tùy biến; `contentType` không phải header MIME bắt buộc của JMS.
- `producer.send(message)` gửi tới destination đã gắn qua `execute("events.orders", ...)`.
- `return 1` là kết quả do code callback đặt (số lần gửi thành công **tới thời điểm không phát sinh exception**). Nó **không phải** count ACK, count consumer đã xử lý hoặc số message chắc chắn còn tồn tại sau sự cố.

Trong trường hợp này, `jmsTemplate.send("events.orders", session -> {...})` cũng làm được. Nếu chỉ muốn gửi một message với property, `convertAndSend(..., MessagePostProcessor)` có thể dễ đọc hơn. Điểm mạnh của `ProducerCallback` thể hiện rõ hơn khi **gửi nhiều lần trên cùng producer** hoặc tự điều chỉnh QoS.

## 6. Điều khiển QoS ngay trên MessageProducer

JMS producer có hai nhóm cách điều chỉnh QoS:

1. Đặt **mặc định cho producer**: `setDeliveryMode(...)`, `setPriority(...)`, `setTimeToLive(...)`. Các lệnh `producer.send(message)` tiếp theo sử dụng giá trị đó.
2. Chỉ định **trên từng lệnh gửi**: `producer.send(message, deliveryMode, priority, timeToLive)`.

Ví dụ đặt mặc định rồi gửi hai message:

```java
jmsTemplate.execute("events.important", (session, producer) -> {
    producer.setDeliveryMode(DeliveryMode.PERSISTENT);
    producer.setPriority(7);
    producer.setTimeToLive(120_000L); // 120 giây

    producer.send(session.createTextMessage("ALERT-1"));
    producer.send(session.createTextMessage("ALERT-2"));
    return null;
});
```

Snippet cần import `jakarta.jms.DeliveryMode`. Với Java 17, `120_000L` là giá trị `long` tính bằng **mili-giây**. Các giá trị phù hợp:

| Thuộc tính | API | Ý nghĩa / lưu ý |
| --- | --- | --- |
| Delivery mode | `producer.setDeliveryMode(DeliveryMode.PERSISTENT)` | Yêu cầu cơ chế persistent delivery; mức đảm bảo thực tế phụ thuộc JMS provider/broker, transaction và policy. |
| Priority | `producer.setPriority(7)` | Giá trị JMS trong khoảng 0–9 (mặc định thường là 4); không bảo đảm consumer quan sát thứ tự tuyệt đối nếu có concorrency, retry, priority policy. |
| Time-to-live | `producer.setTimeToLive(120_000L)` | Lifetime tính bằng ms; `0` thường biểu thị không hết hạn do TTL. |
| Delivery delay | `producer.setDeliveryDelay(5_000L)` | Theo Jakarta Messaging 3.x/JMS 2.0+, yêu cầu trì hoãn trước khi message đủ điều kiện delivery; kiểm tra provider hỗ trợ/chính sách. |

**Lưu ý Spring:** `JmsTemplate.setPriority(...)`, `setTimeToLive(...)` và `setExplicitQosEnabled(true)` chủ yếu điều khiển đường gửi tiện ích của **`JmsTemplate.send`/`convertAndSend`**. Khi đã vào **`ProducerCallback` và tự gọi `producer.send`**, code callback quyết định setter hoặc tham số QoS gửi. Không mặc định suy ra QoS template sẽ được copy sang producer do callback nhận.

Cũng có thể quy định QoS khác nhau cho từng message:

```java
jmsTemplate.execute("events.important", (session, producer) -> {
    producer.send(
        session.createTextMessage("STANDARD"),
        DeliveryMode.PERSISTENT,
        4,
        60_000L
    );
    producer.send(
        session.createTextMessage("URGENT"),
        DeliveryMode.PERSISTENT,
        9,
        10_000L
    );
    return null;
});
```

Không nên tăng mọi message lên priority 9 hoặc kéo TTL rất dài theo thói quen: điều đó có thể làm giảm công bằng xử lý và gây backlog. QoS phải dựa trên yêu cầu nghiệp vụ, provider behavior và khả năng vận hành.

## 7. Gửi nhiều message với cùng Session và MessageProducer

Tình huống một batch có 3 sự kiện. Dùng `convertAndSend` ba lần cũng hợp lệ, nhưng mỗi lần đi qua đường template gửi độc lập. Với `ProducerCallback`, cả batch dùng **một phạm vi callback với một session/producer**:

```java
List<String> events = List.of("ORDER-1", "ORDER-2", "ORDER-3");

int submitted = jmsTemplate.execute(
        "orders.batch",
        (session, producer) -> {
            int count = 0;
            for (String event : events) {
                TextMessage msg = session.createTextMessage(event);
                msg.setStringProperty("batchId", "batch-42");
                producer.send(msg);
                count++;
            }
            return count;
        }
);
```

Đây là đoạn **trong method đã có `jmsTemplate`**, cần import `java.util.List` và `jakarta.jms.TextMessage`. Với broker hoạt động và tất cả lời gọi `send` thành công, `submitted == 3`.

**Ý nghĩa đúng của “cùng producer”:**

- Tránh tự tạo/đóng `MessageProducer` ở mỗi vòng lặp; Spring đóng producer khi callback kết thúc.
- Có thể đặt QoS producer một lần rồi gửi nhiều message.
- Cho phép nhóm nhiều thao tác trong một session; **không tự động biến chúng thành một transaction nguyên tử**.
- Nếu message thứ ba thất bại trong session **không transacted**, hai message đầu có thể đã được gửi; callback ném lỗi không hoàn tác tất cả message trước đó.
- Nếu cần atomic batch, thiết kế transaction/commit/rollback rõ ràng bằng transaction manager phù hợp. Xem phần 10.

Không nên giữ producer trong một biến bên ngoài, tạo async task và tiếp tục dùng nó sau khi `execute` trả về: producer/session đã được Spring quản lý và có thể bị đóng hoặc tái sử dụng theo pool.

## 8. Demo chạy được: Spring Boot 3 + Artemis + ProducerCallback

Ví dụ sau dùng **Java 17+**, **Spring Boot 3.3.13**, Spring JMS, Gradle 8.5+ và broker **Apache ActiveMQ Artemis** đang chạy ở `localhost:61616`. Mục tiêu: nhận một producer từ `JmsTemplate.execute(ProducerCallback)`, cấu hình QoS, gửi 3 `TextMessage`, trả về số lần gửi; một listener nhận chúng từ Queue demo.

### 8.1. Khởi chạy Artemis cho môi trường học

Nếu đã có Docker, chạy một broker test:

```bash
docker run --detach --rm --name artemis-producer-demo -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:2.57.0-alpine
```

Đợi broker sẵn sàng, kiểm tra log bằng `docker logs artemis-producer-demo`. Lệnh dùng image chính thức và credentials **chỉ dành cho môi trường local**. Broker phải cho phép tạo/đã provision Queue `demo.producer.orders`; với những server tắt auto-create, hãy tạo Queue trước. Dừng sau khi học: `docker stop artemis-producer-demo`.

### 8.2. Dự án Gradle

Tạo `settings.gradle`:

```groovy
rootProject.name = 'producer-callback-demo'
```

Tạo `build.gradle`:

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

Tạo `src/main/resources/application.yml`:

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
      default-destination: demo.producer.orders
```

Vì Boot có `spring.jms.template.default-destination`, `JmsTemplate.execute(ProducerCallback)` trong ví dụ **dùng producer gắn với Queue `demo.producer.orders`**. Không cần truyền String destination tại mỗi lần gọi.

### 8.3. File Java đầy đủ

Tạo `src/main/java/demo/jms/ProducerCallbackApplication.java`:

```java
package demo.jms;

import java.util.List;

import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;

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
public class ProducerCallbackApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProducerCallbackApplication.class, args);
    }

    @Bean
    ApplicationRunner sendAtStartup(BatchPublisher publisher) {
        return args -> {
            int sent = publisher.publish(
                    "batch-001",
                    List.of("ORDER-001", "ORDER-002", "ORDER-003")
            );
            System.out.println("Submitted via callback: " + sent);
        };
    }
}

@Component
class BatchPublisher {

    private final JmsTemplate jmsTemplate;

    BatchPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    int publish(String batchId, List<String> payloads) {
        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException("batchId is required");
        }
        if (payloads == null || payloads.isEmpty()) {
            throw new IllegalArgumentException("payloads are required");
        }

        // execute nhận ProducerCallback<Integer>; dùng default
        // destination từ application.yml.
        return jmsTemplate.execute((session, producer) -> {
            producer.setDeliveryMode(DeliveryMode.PERSISTENT);
            producer.setPriority(6);
            producer.setTimeToLive(120_000L);

            int count = 0;
            for (String payload : payloads) {
                TextMessage message =
                        session.createTextMessage(payload);
                message.setStringProperty("batchId", batchId);

                producer.send(message);
                count++;
            }
            return count;
        });
    }
}

@Component
class OrderMessageListener {

    @JmsListener(destination = "demo.producer.orders")
    public void onMessage(TextMessage message) throws JMSException {
        System.out.printf(
                "Received: %s [batch=%s]%n",
                message.getText(),
                message.getStringProperty("batchId")
        );
    }
}
```

**Đường đi thực tế:** `ApplicationRunner` gọi `BatchPublisher.publish` → `JmsTemplate.execute(ProducerCallback)` → Spring tạo producer gắn default Queue → callback đặt QoS và gửi ba message → callback trả số lần gửi → listener đọc `TextMessage`.

`@JmsListener` dùng destination được khai báo **độc lập** trên annotation; nó không tự đọc default destination từ `JmsTemplate`. Trong demo, hai tên Queue tình cờ giống nhau theo chủ đích.

### 8.4. Chạy và kết quả có thể quan sát

Có Gradle trên máy, từ thư mục dự án chạy:

```bash
gradle bootRun
```

Nếu đã tạo Gradle Wrapper: Linux/macOS dùng `./gradlew bootRun`, Windows dùng `gradlew.bat bootRun`. Ngoài log của Spring/Artemis, trong tình huống broker sạch, listener duy nhất và tất cả lần gửi thành công, bạn có thể thấy **bốn dòng nội dung** (thứ tự không được bảo đảm):

```text
Submitted via callback: 3
Received: ORDER-001 [batch=batch-001]
Received: ORDER-002 [batch=batch-001]
Received: ORDER-003 [batch=batch-001]
```

`Submitted via callback: 3` nghĩa là code callback đã gọi thành công `send` ba lần và trả `3`; nó **không xác nhận** listener đã xử lý đủ ba message. Dòng `Received` có thể xuất hiện trước dòng `Submitted`, và nếu có retry/backlog/consumer khác, số lượng hoặc thứ tự output có thể khác. Không dùng log demo làm bằng chứng giao nhận exactly-once.

### 8.5. Đổi sang overload chỉ định destination

Nếu không muốn phụ thuộc default destination trong YAML, thay trong `BatchPublisher`:

```java
return jmsTemplate.execute(
        "demo.producer.orders",
        (session, producer) -> {
            int count = 0;
            for (String payload : payloads) {
                TextMessage msg = session.createTextMessage(payload);
                msg.setStringProperty("batchId", batchId);
                producer.send(msg);
                count++;
            }
            return count;
        }
);
```

Snippet này thay **toàn bộ lệnh `return jmsTemplate.execute(...)`** trong `publish`, không dán cả hai cùng lúc. QoS đã đặt trong ví dụ chính sẽ không còn nếu dùng snippet rút gọn này; nếu muốn giữ QoS, thêm các setter y hệt bên trong callback.

## 9. Gửi nhiều destination bằng một ProducerCallback

Nếu muốn gửi hai loại sự kiện đến các destination khác nhau **trong cùng một callback**, bạn cần hiểu producer bound/unbound.

Tạo một `JmsTemplate` **không cấu hình default destination**, rồi gọi:

```java
jmsTemplate.execute((session, producer) -> {
    Queue orders = session.createQueue("events.orders");
    Queue audit = session.createQueue("events.audit");

    TextMessage order = session.createTextMessage("ORDER_CREATED");
    order.setStringProperty("eventId", "evt-001");
    producer.send(orders, order);

    TextMessage auditLog = session.createTextMessage("ORDER_CREATED");
    auditLog.setStringProperty("eventId", "evt-001");
    producer.send(audit, auditLog);

    return null;
});
```

Đoạn này cần `jakarta.jms.Queue` và một template không có default destination. Spring sẽ tạo producer **không gắn destination**; overload `send(Destination, Message)` chỉ rõ đích mỗi lần. Tùy provider và quyền, `session.createQueue` tạo một đối tượng đích theo tên, **không bảo đảm broker tự provision Queue**.

**Điều không nên làm:** giữ một default destination rồi cố sử dụng producer bound để gửi đến destination khác bằng overload dành cho anonymous producer; JMS provider có thể từ chối. Nếu chỉ cần gửi tới hai Queue và không cần một session/prod chung, hai lệnh `jmsTemplate.convertAndSend("...", payload)` thường đơn giản hơn.

**Transaction:** hai lần `producer.send` trong cùng callback **không tự đồng nghĩa** commit nguyên tử trên hai Queue. Nếu yêu cầu atomicity, cấu hình một transaction manager phù hợp; với hệ thống tích hợp database hoặc broker khác, phải xem xét JTA/XA, outbox hoặc idempotency.

## 10. Transaction, commit và những giới hạn cần hiểu

### 10.1. Callback không tự tạo transaction cho batch

`JmsTemplate.execute(ProducerCallback)` cung cấp tài nguyên JMS cho callback và chuyển đổi `JMSException` thành `JmsException` của Spring. Nó **không** tự khởi tạo một distributed transaction cho nhiều message hay nhiều hệ thống.

Khi dùng session mặc định không transacted, ba lời gọi `send` là ba thao tác có thể được provider thực hiện riêng lẻ. Nếu lần thứ ba ném exception, đừng giả định hai lần trước bị rollback.

Khi cần **một JMS local transaction** hoặc transaction kết hợp với database, hãy dùng cấu hình có transaction manager và resource participation được xác minh. **Không** tùy tiện gọi `session.commit()` bên trong callback nếu session đang thuộc một transaction của container/JTA.

### 10.2. Vì sao phải cẩn thận với `sessionTransacted=true`?

Ở Spring 6, đường xử lý tiện ích `JmsTemplate.send(...)` có phần logic commit cho **locally transacted session** khi thích hợp. Nhưng đường `execute(ProducerCallback)` chủ yếu tạo producer rồi gọi `doInJms` và đóng tài nguyên; **đừng mặc định cho rằng nó đi qua cùng logic auto-commit của `doSend`**.

Vì vậy, nếu tự bật `sessionTransacted=true` nhưng không cấu hình transaction manager/lifecycle phù hợp, có nguy cơ các message gửi trong callback không được commit như kỳ vọng. Hãy:

1. Xác định session đang là local hay JTA-managed.
2. Xác định transaction manager nào khởi tạo/commit/rollback.
3. Viết integration test gửi nhiều message, gây lỗi giữa chừng và xác minh rollback/redelivery.
4. Chỉ commit thủ công khi ứng dụng **thực sự sở hữu** local session và thiết kế không xung đột với Spring/JTA.

Bài học cốt lõi là: **cùng một `Session` không đồng nghĩa cùng một transaction đã được commit**. Nếu cần xử lý exactly-once ở tầng nghiệp vụ, phải kết hợp event ID, deduplication/idempotency và chiến lược transaction phù hợp.

### 10.3. Nhớ tách “gửi”, “broker lưu”, “consumer xử lý”

Có ít nhất ba mốc:

```text
producer.send(message) trả về
            |
            v
broker/provider tiếp nhận theo chế độ cấu hình
            |
            v
consumer nhận và xử lý/ACK/commit
```

Việc `execute` trả kết quả `Integer` không tự chứng minh cả ba mốc đã hoàn thành. Với retry, việc gửi có thể tạo message trùng. Dùng event ID nghiệp vụ và handler idempotent khi cần an toàn với redelivery hoặc client retry.

## 11. Quản lý resource và xử lý exception

`JmsTemplate.execute` được thiết kế để **quản lý tài nguyên**:

- Tạo/lấy session bằng connection factory và ràng buộc transaction đang có nếu phù hợp.
- Tạo producer cho đích đã chọn, truyền cho callback.
- Đóng `MessageProducer` trong `finally`; đóng/release session/connection theo lifecycle Spring.
- Bắt `jakarta.jms.JMSException` và chuyển thành Spring `org.springframework.jms.JmsException` unchecked để caller có thể xử lý theo kiến trúc ứng dụng.

Do đó, **không tự đóng `producer` hay `session`** bên trong callback thông thường. Nếu tự đóng rồi vẫn gửi tiếp, bạn có thể gặp `IllegalStateException` hoặc JMS error. Cũng không trả về `MessageProducer`/`Session` để dùng sau callback; giá trị trả về `T` nên là dữ liệu đơn giản hoặc đối tượng đã tách khỏi lifecycle JMS.

Ví dụ đặt ranh giới lỗi ở service:

```java
try {
    Integer count = jmsTemplate.execute(
            "orders.out",
            (session, producer) -> {
                producer.send(session.createTextMessage("ORDER-5"));
                return 1;
            }
    );
    System.out.println("Submitted: " + count);
} catch (org.springframework.jms.JmsException ex) {
    // Log eventId + loại lỗi, áp dụng retry/backoff phù hợp.
    // Không mặc định mọi JMS error là an toàn để retry vô hạn.
    throw ex;
}
```

Snippet trên thuộc method có `JmsTemplate jmsTemplate`. `JMSException` bên trong callback được Spring chuyển; exception runtime do code nghiệp vụ ném có thể được truyền ra như runtime exception chứ không nhất thiết đổi thành `JmsException`.

**Không** dùng catch-all rồi trả 0 khi callback có lỗi sau một số lần gửi: như vậy người gọi tưởng batch không gửi gì, trong khi một số message có thể đã đến broker. Trả kết quả cần có hợp đồng rõ: *đã thực hiện bao nhiêu lời gọi send trong callback*, không phải *đã xử lý thành công bao nhiêu sự kiện*.

## 12. ProducerCallback hay MessageCreator, MessagePostProcessor, SessionCallback?

| Nhu cầu | API thường phù hợp | Lý do |
| --- | --- | --- |
| Gửi một `String` hoặc DTO qua converter | `convertAndSend(destination, payload)` | Đơn giản, dùng `MessageConverter`. |
| Tạo một JMS `Message` tùy biến | `send(destination, MessageCreator)` | Có `Session`; Spring lo bước gửi. |
| Đặt header/property sau khi converter tạo message | `convertAndSend(..., MessagePostProcessor)` | Không cần tự xử lý producer. |
| Gửi nhiều message từ một `Session`/`MessageProducer` | `execute(destination, ProducerCallback<T>)` | Có cả session và producer. |
| Thiết lập QoS đặc biệt trên producer trong một scope | `ProducerCallback` | Trực tiếp gọi `MessageProducer` API. |
| Thao tác JMS đa dạng ở cấp Session, tự tạo producer/consumer | `execute(SessionCallback<T>)` | Chỉ cấp Session, ứng dụng tự quản lý resource tạo thêm. |
| Nhận message bất đồng bộ liên tục | `@JmsListener` | Listener container phù hợp hơn producer callback. |

**Một hiểu nhầm phổ biến:** `ProducerCallback` tự dùng `MessageConverter` của `JmsTemplate` để biến DTO thành message. Không: callback nhận **raw `Session`** và tự gọi `createTextMessage`, `createObjectMessage`, v.v. Nếu cần converter, tự sử dụng đúng `MessageConverter` và đảm bảo type/schema tương thích, hoặc chọn API `convertAndSend` để Spring xử lý.

### Callback có phải async không?

Không. Đây là **một callback được gọi trong luồng thực thi của `execute`**. Tuy JMS provider có thể tối ưu đường truyền, việc gọi callback không tương đương đưa tác vụ vào thread pool. Một thao tác gửi có thể block do broker flow control, network hay tài nguyên. Đừng làm công việc CPU dài hoặc gọi HTTP blocking hàng loạt trong callback khi không cần thiết.

### Vì sao không cache producer để dùng mãi?

`MessageProducer` gắn với `Session` và có lifecycle JMS. Spring có thể cache/reuse JMS session theo cấu hình connection factory, nhưng điều đó **không cho phép ứng dụng giữ một producer được cấp trong callback rồi dùng sau khi callback đóng**. Muốn tối ưu, kiểm tra `CachingConnectionFactory`/pool config và thực hiện benchmark thay vì thay đổi lifecycle sai contract.

## 13. Các lỗi thường gặp

| Lỗi/triệu chứng | Nguyên nhân dễ gặp | Hướng xử lý |
| --- | --- | --- |
| `InvalidDestinationException` khi `producer.send(message)` | Producer không gắn destination do template không có default. | Dùng `execute("queue", callback)`, đặt default, hoặc `producer.send(destination, message)` trên unbound producer. |
| Callback gửi vào Queue khác dự tính | Sai `defaultDestinationName`, `pubSubDomain` hoặc `DestinationResolver`. | Xác nhận template instance, tên đích và Queue/Topic domain. |
| `NullPointerException` hoặc lỗi khi dùng producer sau callback | Giữ reference producer/session sau khi Spring đóng. | Chỉ dùng bên trong callback; trả DTO/result, không trả resource. |
| Chỉ vài message trong batch xuất hiện | Lỗi giữa chừng, transaction/rollback, broker policy, listener cạnh tranh, retry. | Xem log, gửi/commit/ACK thực tế; không giả định batch atomic. |
| Priority/TTL không giống cấu hình `JmsTemplate` | Tự gửi qua raw `MessageProducer` nên không qua `doSend` tiện ích. | Đặt QoS trên producer hoặc từng lệnh send; test provider behavior. |
| Có exception nhưng count vẫn bị ghi như success | Code catch và bỏ qua exception. | Phân biệt số lần send, ACK của broker và xử lý downstream; không nuốt lỗi. |
| Không compile do import `javax.jms` | Dùng thư viện JMS cũ với Spring 6/Boot 3. | Import `jakarta.jms.*`; giữ `javax.naming` riêng nếu có JNDI. |
| `JMSException` không compile ngoài callback | Phương thức ném checked exception khi tự gọi JMS API. | Đặt code trong callback (`doInJms throws JMSException`) hoặc khai báo/catch đúng. |
| Template chạy nhưng không có consumer nhận | Destination không tồn tại, sai domain, quyền/broker lỗi, listener chưa sẵn sàng. | Kiểm tra broker logs/management, destination và listener config. |
| Producer gửi nhiều lần rồi transaction không commit | Hiểu sai lifecycle `execute` và local transaction. | Kiểm tra transaction manager, `sessionTransacted` và commit/rollback bằng integration test. |

## 14. Kiểm thử thiết kế

### Unit test

Đơn vị trách nhiệm ở service nên là “khi cần gửi batch, gọi `JmsTemplate.execute` với destination/callback phù hợp”. Có thể dùng mock `JmsTemplate` để kiểm tra overload được gọi; nếu muốn kiểm tra nội dung message/QoS chi tiết thì mock `Session` và `MessageProducer` rồi **thực thi callback đã capture** trong test. Đừng giả định mock `JmsTemplate` tự thực thi callback: không có code test tương ứng thì lời gọi mock chỉ trả giá trị mặc định.

### Integration test

Chạy broker thật hoặc container test gần tương đương với production, đồng thời kiểm chứng:

1. Factory kết nối đúng broker và Queue/Topic được provision.
2. Đếm message nhận được khi không có consumer cạnh tranh.
3. Properties (`batchId`), priority, TTL và delivery mode thực tế.
4. Lỗi giữa batch, rollback/retry, duplicate handling theo transaction setup.
5. Đường đi của `execute(callback)` **có default destination** và **không có default destination**.
6. Resource lifecycle/caching khi nhiều publisher đồng thời.

Cần kiểm tra **với provider cụ thể** vì behavior liên quan redelivery, expiration, priority scheduling, flow control và pooling thường có chi tiết khác nhau.

### Bài tập thực hành

**Bài 1.** Dùng `ProducerCallback<Integer>` để gửi 5 `TextMessage` đến Queue `demo.orders`, trả số lời gọi `send` đã hoàn thành. Hãy thêm property `batchId` và kiểm tra ở consumer.

**Gợi ý:** dùng `jmsTemplate.execute("demo.orders", (session, producer) -> {...})`, tạo message trong `for`, `return count`.

**Bài 2.** Một template không có default destination. Điều gì xảy ra nếu gọi `execute((session, producer) -> { producer.send(session.createTextMessage("A")); return null; })`?

**Đáp án:** Producer có thể không gắn đích, nên `send(message)` không có destination và có thể ném `InvalidDestinationException`. Dùng overload có destination hoặc `producer.send(explicitDestination, message)` trên unbound producer.

**Bài 3.** Tại sao `execute` trả `3` nhưng dashboard consumer chỉ thấy hai sự kiện đã xử lý?

**Đáp án:** `3` là giá trị callback tự đếm các lần gửi không báo lỗi; chưa chứng minh consumption/ACK. Cần kiểm tra backlog, consumer concurrency, filtering, expiry, errors, rollback và transaction.

**Bài 4.** Một người cấu hình `jmsTemplate.setPriority(8)` rồi tự dùng `producer.send(message)` trong callback. Có thể mặc định message được gửi priority 8 không?

**Đáp án:** Không nên giả định. Đường callback tự gọi producer không nhất thiết áp dụng QoS qua `JmsTemplate.doSend`. Đặt `producer.setPriority(8)` hoặc truyền priority trong `producer.send(message, mode, 8, ttl)`.

**Bài 5.** Có nên gọi `producer.close()` và `session.close()` trong callback để tránh rò rỉ?

**Đáp án:** Không trong sử dụng `JmsTemplate.execute` thông thường; template quản lý lifecycle. Chủ động đóng resource Spring đang cấp có thể làm hỏng phần còn lại của callback hoặc transaction.

## 15. Tài liệu gốc và nơi đọc thêm

- [Spring Framework – Sending a Message, SessionCallback và ProducerCallback](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework 6.2 – ProducerCallback API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/ProducerCallback.html)
- [Spring Framework 6.2 – JmsTemplate.execute overloads](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Jakarta Messaging 3.1 – MessageProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer)
- [Jakarta Messaging 3.1 – Session](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session)
- [Spring Boot – ActiveMQ Artemis / JMS auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html)
- [Apache ActiveMQ Artemis – Docker images và broker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)

**Ghi nhớ:** `ProducerCallback<T>` cho phép **truy cập trực tiếp `Session` và `MessageProducer` trong phạm vi `JmsTemplate.execute`**, đặc biệt hữu ích khi gửi nhiều message hoặc kiểm soát QoS. Hãy xác định rõ producer **bound hay unbound**, để Spring quản lý lifecycle, và thiết kế **transaction/ACK/idempotency riêng** khi cần độ tin cậy nghiệp vụ.
