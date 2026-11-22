# ConnectionFactory là điểm vào của JMS provider

## 1. Mục tiêu của bài học

Trong **JMS (Java Message Service, nay thuộc Jakarta Messaging)**, ứng dụng không tự mở socket đến broker rồi tự đóng gói giao thức. Nó lấy một **`ConnectionFactory` do JMS provider triển khai hoặc do framework/container cung cấp**, sau đó dùng factory ấy để tạo tài nguyên cần thiết cho hoạt động gửi và nhận thông điệp.

Câu cần nhớ:

> **`ConnectionFactory` là điểm vào của client để kết nối với JMS provider.** Nó mô tả/cất giữ cấu hình kết nối và cung cấp các phương thức tạo `Connection` (API cổ điển) hoặc `JMSContext` (API đơn giản hóa); bản thân nó không phải là message, queue, session hay broker.

Trong ứng dụng Spring, `ConnectionFactory` thường là một **bean được inject** vào `JmsTemplate` và các message listener container. Hiểu đúng factory sẽ giúp cấu hình broker, credentials, TLS, cache/pool, transaction và chẩn đoán lỗi kết nối.

Bài dùng **Java 17+**, Spring Framework 6.x / Spring Boot 3.x và namespace `jakarta.jms.*`. Trong code đời cũ trước Jakarta EE 9 có thể thấy `javax.jms.*`. Không trộn API `javax.jms` với driver `jakarta.jms` trong cùng một cấu hình runtime không tương thích.

## 2. Phân biệt các đối tượng trong cùng một luồng

~~~text
                     ỨNG DỤNG JAVA / SPRING
                ┌──────────────────────────────────┐
                │  @JmsListener     JmsTemplate     │
                │         │                │        │
                │         └───────┬────────┘        │
                │                 ▼                 │
                │       ConnectionFactory bean     │
                │        (provider / wrapper)      │
                │                 │                 │
                │     createConnection()            │
                │          hoặc createContext()      │
                │                 ▼                 │
                │       Connection / JMSContext     │
                │                 │                 │
                │       Session / JMSProducer       │
                │       Producer / Consumer         │
                └─────────────────┼─────────────────┘
                                  │ provider protocol
                                  ▼
                       JMS PROVIDER / BROKER
                       queue / topic / routing
~~~

| Thành phần | Bản chất | Có nhiệm vụ gì? |
| --- | --- | --- |
| `ConnectionFactory` | Interface chuẩn `jakarta.jms.ConnectionFactory` và bản triển khai do provider hoặc wrapper cung cấp | Tạo connection/context theo cấu hình, thường chứa endpoint và các tùy chọn kết nối |
| `Connection` | Kết nối logic của client với JMS provider | Đại diện cho tài nguyên kết nối, có thể tạo một hoặc nhiều session và điều khiển việc nhận bằng `start()/stop()` |
| `Session` | Ngữ cảnh làm việc có thứ tự cho gửi/nhận trong API cổ điển | Tạo message, producer, consumer; quản lý acknowledge/transaction theo chế độ |
| `JMSContext` | API đơn giản hóa, kết hợp connection và session | Cung cấp đường đi ngắn để tạo producer/consumer và gửi/nhận |
| `MessageProducer` / `JMSProducer` | Thành phần phát | Gửi thông điệp đến `Destination` |
| `MessageConsumer` / `JMSConsumer` | Thành phần nhận | Nhận và đọc thông điệp của destination |
| `Queue` / `Topic` | Destination logic | Cho biết message được gửi vào đâu; **không phải** tài nguyên mạng tự thân |
| JMS provider | Phần mềm triển khai JMS API, thư viện client và cơ chế messaging | Cung cấp cách các giao diện JMS thực sự hoạt động |
| Broker | Thành phần hạ tầng trung chuyển, có thể chạy riêng | Tiếp nhận, định tuyến, giữ và phân phối message tùy mô hình/sản phẩm |
| `JmsTemplate` | Tiện ích do Spring cung cấp | Dùng `ConnectionFactory` để thực hiện gửi/nhận và quản lý mã lặp, không thay thế provider |

`ConnectionFactory` là **điểm khởi đầu về mặt API**: một factory instance có thể được nhiều thành phần dùng lại, nhưng không có nghĩa mọi lời gọi luôn tạo một kết nối TCP hoàn toàn mới. Một factory hoặc decorator có thể có cơ chế cache, pooling, lazy connection hoặc failover. Hành vi cụ thể phụ thuộc cấu hình.

## 3. Hợp đồng API của `jakarta.jms.ConnectionFactory`

### 3.1. API cổ điển: `createConnection()`

`ConnectionFactory` cung cấp:

~~~java
Connection createConnection() throws JMSException;
Connection createConnection(String userName, String password)
        throws JMSException;
~~~

Sơ đồ thao tác cơ bản:

~~~text
ConnectionFactory
    └── createConnection() -> Connection
                                └── createSession(...) -> Session
                                                           ├── createProducer(...)
                                                           └── createConsumer(...)
~~~

`Connection` ban đầu ở trạng thái **stopped** đối với việc nhận message. Nếu viết consumer bằng JMS classic API, cần gọi `connection.start()` trước khi mong đợi message được giao; producer vẫn có thể gửi trước khi `start()`. Lời gọi `close()` giải phóng tài nguyên của connection và các tài nguyên con theo hợp đồng JMS.

**Đoạn ví dụ dưới đây là một phương thức độc lập về logic nhưng cần `factory` đã được cung cấp**; nó không tự tạo broker hoặc factory:

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public class ClassicJmsReceiver {

    public static String receiveOne(ConnectionFactory factory)
            throws JMSException {
        try (Connection connection = factory.createConnection()) {
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            Queue queue = session.createQueue("training.orders");
            MessageConsumer consumer = session.createConsumer(queue);

            connection.start(); // Bắt đầu cho phép nhận message.
            Message message = consumer.receive(2_000);

            if (message == null) {
                return "NO_MESSAGE";
            }
            if (message instanceof TextMessage textMessage) {
                return textMessage.getText();
            }
            return "UNEXPECTED_MESSAGE_TYPE";
        }
    }
}
~~~

Biên dịch lớp trên cần thư viện `jakarta.jms-api` trong classpath, và **muốn chạy thành công** cần một `ConnectionFactory` thật, provider driver, broker cùng destination phù hợp. Lệnh `javac` chỉ hợp lệ khi API JAR nằm trong classpath; thực tế dự án Maven/Gradle sẽ quản lý dependency thay vì biên dịch thủ công từng JAR. Lệnh build chạy cho ví dụ Spring Boot ở phần 6 được trình bày đầy đủ hơn.

Điểm kỹ thuật: `receive(2_000)` chờ tối đa xấp xỉ 2 giây rồi trả `null` nếu chưa nhận được message; `NO_MESSAGE` là kết quả hợp lệ, không tự suy luận rằng `ConnectionFactory` hỏng. Một message có thể đã được consumer khác lấy trước.

### 3.2. API đơn giản hóa: `createContext()`

Từ JMS 2.0, `ConnectionFactory` có thêm các biến thể:

~~~java
JMSContext createContext();
JMSContext createContext(int sessionMode);
JMSContext createContext(String userName, String password);
JMSContext createContext(
        String userName, String password, int sessionMode);
~~~

`JMSContext` gom khái niệm **connection + session** và hỗ trợ `try-with-resources`:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

public class SimpleJmsSender {

    public static void sendOne(ConnectionFactory factory) {
        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue("training.orders");
            context.createProducer().send(queue, "order-42");
        }
    }
}
~~~

Phương thức này có thể được dùng khi đã inject/lookup một `factory` hợp lệ. Trong ngữ cảnh Java SE, `createContext()` mặc định dùng session không giao dịch với `AUTO_ACKNOWLEDGE`. Khi ứng dụng tạo consumer bằng `JMSContext`, cơ chế tự khởi động nhận được bật theo API (trừ khi đã gọi `setAutoStart(false)`).

**Lưu ý về lỗi:** API classic thường báo `jakarta.jms.JMSException` (checked exception). API rút gọn thường báo `jakarta.jms.JMSRuntimeException` cùng các subtype (unchecked). Trong Spring, `JmsTemplate` chuyển phần lớn JMS checked exception sang hệ phân cấp `org.springframework.jms.JmsException` (runtime exception).

### 3.3. Chọn API nào?

| Mong muốn | Lựa chọn |
| --- | --- |
| Code Java thuần mới, gửi/nhận đơn giản | `createContext()` + `JMSProducer/JMSConsumer` |
| Tích hợp thư viện/hệ thống dựa trên API JMS cổ điển | `createConnection()` + `Session` |
| Ứng dụng Spring gửi message trong service | `JmsTemplate` được inject với `ConnectionFactory` |
| Ứng dụng Spring nhận bất đồng bộ | `@JmsListener` + message listener container |
| Cần cache, pool, transaction và recovery | Cấu hình factory/listener container đúng chuẩn cho provider và Spring |

`QueueConnectionFactory` và `TopicConnectionFactory` là những giao diện theo domain tồn tại từ API cũ; các ứng dụng hiện đại thường dùng `ConnectionFactory` tổng quát cho cả queue và topic, rồi cấu hình destination/consumer phù hợp.

## 4. Factory đến từ đâu, và nó đang kết nối tới provider nào?

### 4.1. Do JMS provider cung cấp

Trong một ứng dụng Java độc lập, nhà cung cấp JMS có thể đưa ra lớp factory riêng, chẳng hạn một Artemis-specific connection factory. Cách khởi tạo, broker URL, TLS, failover, prefetch, retry và credentials thường là chi tiết riêng của provider.

**Không thể viết** `new ConnectionFactory()` vì đây là interface. Một biến kiểu `ConnectionFactory` có thể trỏ tới triển khai provider hoặc decorator:

~~~java
import jakarta.jms.ConnectionFactory;

// factory thực tế phải lấy từ cấu hình/provider/container trước:
ConnectionFactory factory = obtainConfiguredFactory();
~~~

Đoạn trên chỉ biểu diễn **kiểu biến**, không phải chương trình hoàn chỉnh; `obtainConfiguredFactory()` là ký hiệu cho bước cấu hình/lookup của từng môi trường, không phải API JMS có sẵn. Trong dự án thật nên dùng một cơ chế cấp phát factory rõ ràng, ví dụ injection của Spring.

### 4.2. Do Spring Boot auto-configure

Nếu dự án có starter JMS tương ứng, broker connection settings hợp lệ và không có bean tùy chỉnh cản trở điều kiện tự cấu hình, Spring Boot có thể tạo sẵn bean `ConnectionFactory`.

Ví dụ dùng **Apache ActiveMQ Artemis**:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

- `native` nghĩa là kết nối tới **broker ngoài**; nó không tự chạy một Artemis server.
- `broker-url` là địa chỉ broker, không phải địa chỉ producer/consumer cụ thể.
- Credentials phải khớp broker; trong thực tế nên cấp qua biến môi trường hoặc secret manager, tránh ghi mật khẩu thật trong repository.
- `pub-sub-domain=false` hướng ví dụ Spring sử dụng **queue**; phần lựa chọn queue/topic không biến factory thành hai loại kết nối mạng khác nhau.

Khi đã có bean, ứng dụng nhận nó qua constructor hoặc tham số bean method:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.stereotype.Service;

@Service
class JmsConnector {
    private final ConnectionFactory connectionFactory;

    JmsConnector(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }
}
~~~

Lợi thế của DI: code nghiệp vụ phụ thuộc **interface** `jakarta.jms.ConnectionFactory`, còn việc chọn driver, địa chỉ và quyền truy cập nằm ở cấu hình.

### 4.3. Do application server quản lý qua JNDI

Trong Jakarta EE server, người vận hành thường cấu hình ConnectionFactory thành **administered object** rồi ứng dụng lookup/inject. Ví dụ minh họa Java:

~~~java
import jakarta.jms.ConnectionFactory;
import javax.naming.InitialContext;
import javax.naming.NamingException;

public class ManagedFactoryLookup {

    public static ConnectionFactory lookup(String jndiName)
            throws NamingException {
        return (ConnectionFactory) new InitialContext().lookup(jndiName);
    }
}
~~~

`jndiName` phải là tên thật được server thiết lập, ví dụ `java:/JmsXA` trong một số môi trường; tên này **không phải một tên chuẩn duy nhất áp dụng cho mọi provider**. `javax.naming` vẫn là package JNDI của Java SE; việc dùng `jakarta.jms` không yêu cầu đổi `javax.naming` thành `jakarta.naming`.

Khi server quản lý connection factory, pooling, security và transaction có thể được điều phối ở server. Không tự đóng hủy bean factory do container quản lý; chỉ quản lý vòng đời tài nguyên mình tạo theo mô hình ứng dụng.

### 4.4. Do Spring Framework thuần tự khai báo

Với Spring Framework không dùng Boot, có thể khai báo một provider-specific `ConnectionFactory` dưới dạng bean; từ bean đó tạo `JmsTemplate` và listener container. **Lớp factory cụ thể phụ thuộc thư viện của provider**, không có một constructor JMS chuẩn chung cho mọi broker.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
class JmsTemplateConfig {

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }
}
~~~

Đoạn này giả định bean `ConnectionFactory` đã tồn tại; nó **không tự cung cấp** bean đó. Trong Spring Boot đã auto-configure `JmsTemplate`, thông thường không cần định nghĩa lại bean như trên.

## 5. Factory hoạt động thế nào khi có kết nối, session và luồng?

### 5.1. Vòng đời điển hình

1. **Khởi tạo/cấp phát factory:** ứng dụng nhận một object đã cấu hình provider endpoint, các thuộc tính transport và authentication. Tạo factory **không bảo đảm** có thể liên lạc broker ngay lúc đó; một số client kết nối lười (lazy).
2. **Yêu cầu connection/context:** `createConnection()` hoặc `createContext()` kích hoạt việc cấp phát tài nguyên phù hợp. Có thể phát sinh lỗi kết nối, xác thực hoặc cấu hình ở bước này, hoặc ở lần thao tác tiếp theo tùy provider/wrapper.
3. **Tạo session/producer/consumer:** với API classic, `Connection.createSession(...)`; với API simplified, thao tác qua `JMSContext`.
4. **Trao đổi message:** gửi tới destination hoặc nhận từ queue/topic; với classic consumer phải gọi `connection.start()`.
5. **Đóng tài nguyên đúng thời điểm:** đóng session/connection hoặc `JMSContext` do chính mình tạo. Trong Spring, giao phần quản lý thường ngày cho `JmsTemplate` và listener container.

Cần phân biệt **factory có thể tái sử dụng** và **connection có thể tốn kém để khởi tạo**. Quá nhiều connection sinh ra liên tục gây tăng overhead của handshake/auth/network, nhưng việc có đúng một kết nối vật lý cho mọi workload cũng không phải quy tắc bất biến.

### 5.2. Tính an toàn luồng (thread safety)

- Theo Jakarta Messaging, **`ConnectionFactory` hỗ trợ dùng đồng thời**; thường khai báo nó thành bean singleton và cho nhiều service cùng inject.
- `Connection` có thể hỗ trợ truy cập đồng thời, nhưng **`Session` và `JMSContext` có giới hạn luồng**. Không giữ một `JMSContext`/`Session` dùng chung rồi cho nhiều request thread gửi nhận song song.
- `JmsTemplate` được thiết kế để dùng lại sau khi cấu hình; Spring tạo/lấy tài nguyên phù hợp cho từng thao tác. Không tự tái sử dụng `Session` thủ công giữa các `@JmsListener`.
- Lưu `JMSContext` trong trường `static` của singleton service là cách dễ tạo lỗi concurrency và quản lý vòng đời.

**Mô hình ưu tiên trong ứng dụng Spring:**

~~~text
Nhiều thread/request
      │
      ├── Service A ──> JmsTemplate ──┐
      └── Service B ──> JmsTemplate ──┤
                                     ▼
                            ConnectionFactory bean
                                     │
                     provider + Spring cache/pool
                                     │
                            broker queue / topic
~~~

Factory chung; tài nguyên phiên làm việc phải tuân thủ scope và threading của provider/Spring.

### 5.3. CachingConnectionFactory không phải một broker mới

Spring cung cấp một số **wrapper `ConnectionFactory`**:

- `SingleConnectionFactory` cho phép các thao tác sử dụng cùng một shared connection logic; phù hợp các tình huống kiểm thử hoặc đơn giản.
- `CachingConnectionFactory` kế thừa cách tiếp cận đó, cache thêm session/producer/consumer để giảm khối lượng tạo và hủy tài nguyên JMS trong các thao tác lặp lại.
- Factory pool của bên thứ ba/provider có thể duy trì **nhiều** kết nối vật lý với giới hạn riêng. Chọn pool dựa trên concurrency, giới hạn broker, transaction và đặc điểm workload, không dựa vào tên wrapper.

Trong nhiều cấu hình Spring Boot Artemis, factory thực tế được inject có thể mang kiểu `CachingConnectionFactory` vì Spring bọc driver factory của Artemis. Do đó `connectionFactory.getClass().getName()` có thể cho thấy wrapper Spring; nó **không chứng minh** underlying provider là Spring.

Ví dụ thuộc tính tuning tùy phiên bản Spring Boot:

~~~properties
spring.jms.cache.session-cache-size=5
~~~

Tăng cache size không phải càng lớn càng tốt. Với listener container, consumer caching và durable subscriptions cần được xem xét cùng cấu hình container, ack/transaction và chính sách broker. Đóng resource đúng hợp đồng JMS vẫn cần thiết để cache có cơ hội tái sử dụng.

## 6. Ví dụ chạy được: Spring Boot inject ConnectionFactory và gửi message

Ví dụ này minh họa **factory là điểm vào thật sự**: mã nghiệp vụ nhận `jakarta.jms.ConnectionFactory` từ Spring rồi gọi `createContext()` để gửi. Một listener trong cùng ứng dụng nhận message. Khi tách hai service độc lập, cách cấp phát factory vẫn tương tự.

### 6.1. Chuẩn bị

- JDK **17 trở lên** và Maven (hoặc Maven wrapper do Spring Initializr tạo).
- Tạo dự án Spring Boot **3.x** từ [start.spring.io](https://start.spring.io), Group = `com.example`, Artifact = `connection-factory-demo`, chọn dependency **Spring for Apache ActiveMQ Artemis** (starter `org.springframework.boot:spring-boot-starter-artemis`).
- Có một **Artemis broker bên ngoài ứng dụng** chạy, cho phép kết nối tại `tcp://localhost:61616` và cho phép gửi/nhận queue `training.orders`. Broker cần được cấu hình có destination này hoặc bật auto-create thích hợp. `JMSContext.createQueue(...)` chỉ tạo đối tượng `Queue` ở phía Java, **không có bảo đảm provider sẽ tự provision queue vật lý**.
- Đặt biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD` theo tài khoản broker được cấp.

Tệp `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

Tệp `src/main/java/com/example/ConnectionFactoryDemoApplication.java`:

~~~java
package com.example;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class ConnectionFactoryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConnectionFactoryDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner sendExample(ConnectionFactory factory) {
        return args -> {
            try (JMSContext context =
                         factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
                Queue queue = context.createQueue("training.orders");
                context.createProducer().send(queue, "order-42");
            }
            System.out.println("SENT order-42");
        };
    }
}

@Component
class TrainingOrderConsumer {

    @JmsListener(destination = "training.orders")
    public void receive(String payload) {
        System.out.println("RECEIVED " + payload);
    }
}
~~~

Chạy tại thư mục gốc dự án:

~~~bash
mvn spring-boot:run
~~~

Hoặc trên Windows nếu dự án có Maven wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

**Các dòng nghiệp vụ mong đợi** khi broker/destination/config đúng và chưa có message cũ:

~~~text
SENT order-42
RECEIVED order-42
~~~

Đây là **ví dụ về nội dung log**, không phải một thứ tự log bảo đảm: listener nhận bất đồng bộ nên `RECEIVED` có thể xuất hiện trước `SENT`; Spring cũng ghi thêm startup logs. Nếu broker không cho kết nối, không tự tạo destination hoặc thiếu quyền, chương trình sẽ báo lỗi thay vì hai dòng trên.

**Giải phẫu ví dụ:**

1. Spring Boot tạo/inject `ConnectionFactory` từ Artemis starter và cấu hình `spring.artemis.*`.
2. `ApplicationRunner` được Spring gọi sau khi application context khởi tạo; tham số `factory` là điểm vào JMS của sender.
3. `factory.createContext(...)` nhận ngữ cảnh JMS; `createProducer().send(...)` thực hiện gửi, rồi `try-with-resources` gọi `close()`.
4. `@JmsListener` khai báo consumer. Spring tạo listener container và dùng JMS infrastructure phù hợp; trong setup auto-configure đúng, **không cần tự viết `connection.start()` cho listener**.
5. Artemis broker nhận và phân phối message của queue `training.orders`.

Ví dụ dùng một Java app vừa phát vừa nhận để dễ quan sát; trong hệ thống thật có thể chia sender/receiver thành hai process, cùng hoặc khác `ConnectionFactory` tùy hạ tầng.

### 6.2. Khi dùng JmsTemplate thì ConnectionFactory vẫn ở đó

Đối với code nghiệp vụ Spring, thường nên dùng API cấp cao:

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(String orderId) {
        jmsTemplate.convertAndSend("training.orders", orderId);
    }
}
~~~

Đây là **đoạn service minh họa**, không phải chương trình khởi động độc lập. `JmsTemplate` vẫn phụ thuộc vào `ConnectionFactory` ở dưới để có connection/session; Spring chỉ giấu đi các bước quản lý lặp lại. Với Boot, thường factory và template đều có sẵn dưới dạng bean khi điều kiện auto-configure JMS thỏa mãn.

So sánh:

~~~text
Dùng JMS trực tiếp:
ConnectionFactory -> JMSContext -> JMSProducer -> send(...)

Dùng Spring:
OrderPublisher -> JmsTemplate -> ConnectionFactory
                                 -> Connection/Session -> send(...)
~~~

Hai cách đều dùng JMS provider. Chọn cách Spring khi muốn code service gọn, kiểm soát resource/transaction/convert message thống nhất giữa các nơi.

## 7. Kết nối, xác thực, transaction: factory chịu trách nhiệm đến đâu?

### 7.1. Kết nối mạng và xác thực

`ConnectionFactory` thường encapsulate endpoint và một phần cấu hình bảo mật của provider. Các overload `createConnection(username, password)` / `createContext(username, password)` cho phép truyền credentials khi tạo connection; tuy nhiên cách cấu hình TLS, failover URL, reconnect, certificate truststore và timeout vẫn mang tính provider-specific.

**Không nên** ghi mật khẩu hoặc khóa TLS vào source code, cũng không log chuỗi cấu hình nhạy cảm. Khi dùng TLS, kiểm tra certificate/truststore và hostname verification theo tài liệu vendor. Broker có thể yêu cầu phân quyền riêng cho connect, send và consume.

### 7.2. Session mode và giao dịch

Factory cho phép chỉ định session mode khi tạo `JMSContext`:

| Mode trong Java SE | Ý nghĩa thực tế |
| --- | --- |
| `JMSContext.AUTO_ACKNOWLEDGE` | Provider tự acknowledge message đã được giao theo semantics JMS |
| `JMSContext.CLIENT_ACKNOWLEDGE` | Ứng dụng gọi acknowledge theo cơ chế JMS |
| `JMSContext.DUPS_OK_ACKNOWLEDGE` | Cho phép lazy acknowledgment; có thể tăng khả năng nhận lặp trong một số tình huống |
| `JMSContext.SESSION_TRANSACTED` | Session được commit/rollback cục bộ cho các thao tác JMS thuộc transaction |

Đừng suy ra đặt `SESSION_TRANSACTED` là toàn bộ thao tác JMS và ghi SQL sẽ atomic. Transaction JMS cục bộ không tự gộp được database transaction. Spring có `JmsTransactionManager` cho JMS resource transaction; giao dịch phân tán xuyên JMS và database cần giải pháp phù hợp như JTA/XA, hoặc kiến trúc outbox/inbox cùng idempotency.

Trong môi trường Jakarta EE có JTA transaction đang hoạt động, semantics `createContext(sessionMode)` có thể do container quy định thay vì giống ứng dụng Java SE; đọc tài liệu nền tảng đang dùng trước khi suy luận về ack mode.

### 7.3. Chọn nhiều provider/broker

Một service có thể kết nối hai JMS provider khác nhau. Khi đó phải xác định rõ **factory nào** cấp connection cho từng `JmsTemplate` và từng listener container (thường qua `@Qualifier` hoặc container factory cấu hình riêng). Nếu có nhiều bean cùng kiểu `ConnectionFactory` mà không có `@Primary` hay qualifier, Spring có thể không biết inject bean nào.

Không trông chờ vào một factory kết nối broker A để tự động đọc queue ở broker B. Không có cam kết hai provider sẽ tương thích về giao thức mạng chỉ vì cả hai tuân theo JMS API.

## 8. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân hay gặp | Cách kiểm tra |
| --- | --- | --- |
| Spring báo không tìm thấy `ConnectionFactory` bean | Thiếu starter/driver, auto-config condition không thỏa, chưa khai báo bean cho Spring Framework thuần | Kiểm tra dependencies, bean definitions, cấu hình auto-configuration và hồ sơ active |
| Lỗi kết nối khi tạo context hoặc lần gửi đầu | Broker chưa chạy, host/port sai, firewall, TLS mismatch, timeout | Kiểm tra broker health, `broker-url`, network và log driver/provider |
| `JMSSecurityException` / `JMSSecurityRuntimeException` | Credentials sai hoặc không có quyền | Kiểm tra user, secret, quyền connect/send/consume và policy của broker |
| Gửi được nhưng listener không nhận | Sai tên destination, dùng topic trong khi listener cấu hình queue, consumer chưa start (classic), message đã đi tới consumer khác | Đối chiếu queue/topic, tên destination, broker metrics, listener container và `Connection.start()` |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` liên quan `javax.jms`/`jakarta.jms` | Trộn dependency namespace/API hoặc driver không tương thích | Đồng bộ Spring, API và provider client dependency |
| Tăng connection/socket, memory hoặc thread | Tạo factory/connection mới mỗi message, leak resource, cache/pool không phù hợp | Kiểm tra resource ownership, `close()`, cache size, broker connection count |
| Chạy được lúc đầu rồi lỗi sau broker restart | Recovery/failover phụ thuộc factory wrapper, client và listener settings | Kiểm tra retry/backoff, broker HA, logs và test chuyển đổi kết nối |
| Message được xử lý hai lần | Redelivery sau rollback, network failure hoặc consumer retry | Thiết kế handler idempotent, dùng business/event ID và policy DLQ/retry |

**Quy trình chẩn đoán ngắn:** xác định bean `ConnectionFactory` đang được inject → xác minh provider driver/endpoint → thử kết nối và quyền → đối chiếu destination → kiểm tra cách tạo session, listener container, ack/transaction → đo kết nối, retry và backlog trên broker.

Một factory object được tạo thành công **không tự chứng minh** broker đang hoạt động; nhiều lỗi chỉ xuất hiện khi ứng dụng thực sự mở connection hoặc gửi/nhận message.

## 9. Các ngộ nhận cần tránh

1. **“ConnectionFactory là kết nối.”** Sai. Factory *tạo/cấp phát* connection; `Connection`/`JMSContext` đại diện cho ngữ cảnh kết nối đã được yêu cầu.
2. **“ConnectionFactory là broker.”** Sai. Factory nằm phía client hoặc được container cấp phát; broker là dịch vụ messaging.
3. **“Phải tạo ConnectionFactory mới mỗi lần gửi.”** Sai. Factory thường được chia sẻ; việc quản lý connection/session và cache/pool là vấn đề riêng.
4. **“Dùng ConnectionFactory ở nhiều thread là sai.”** Không đúng: factory hỗ trợ concurrent use, nhưng một `Session`/`JMSContext` không dành để chia sẻ tùy tiện giữa nhiều thread.
5. **“Gọi createQueue đã tạo queue trên broker.”** Không thể suy ra; có provider hỗ trợ auto-create, có provider đòi provision trước.
6. **“Spring Boot tự tạo broker khi inject ConnectionFactory.”** Không đúng khi dùng `spring.artemis.mode=native`; cần broker ngoài hoạt động.
7. **“JmsTemplate bỏ qua ConnectionFactory.”** Sai. Template sử dụng factory dưới lớp abstraction.
8. **“JMS API chuẩn nghĩa là URL, TLS, HA, pool của mọi provider giống nhau.”** Sai. Chuẩn hóa API và nhiều semantics; cấu hình kết nối/protocol vẫn phụ thuộc vendor.
9. **“Tạo context và quên đóng là vô hại.”** Sai. Context có thể giữ session, consumer và connection; đóng đúng vòng đời là trách nhiệm của bên tạo, trừ tài nguyên do container quản lý.
10. **“Factory báo gửi thành công tức là consumer commit database.”** Sai. Kết quả gửi và xử lý nghiệp vụ ở consumer là hai sự kiện khác nhau.

## 10. Tự kiểm tra

**Câu 1.** Một `@Service` có hai phương thức gửi message qua `JmsTemplate`. Nó có cần khởi tạo hai `ConnectionFactory` không?

Trả lời: Không. Các phương thức có thể dùng chung template và factory do Spring quản lý; resource nội bộ do framework/provider cấp phát theo từng thao tác và cấu hình cache/pool.

**Câu 2.** Vì sao `ConnectionFactory` có thể là singleton nhưng `JMSContext` không nên được lưu như một singleton dùng chung cho mọi request?

Trả lời: Factory hỗ trợ concurrent use; `JMSContext` chứa một session chịu giới hạn thread và có vòng đời tài nguyên cần đóng.

**Câu 3.** Trong API cổ điển, tạo connection và consumer xong nhưng chưa gọi `start()`. Có chắc nhận được message qua `receive()` không?

Trả lời: Không. Connection classic mới tạo ở trạng thái stopped đối với message delivery; cần `connection.start()`.

**Câu 4.** Bạn đổi từ Artemis sang provider JMS khác. Có chắc chỉ cần thay dependency là xong?

Trả lời: Không. Hợp đồng Java JMS giúp giảm thay đổi của code nghiệp vụ, nhưng cách khởi tạo/config factory, endpoint/protocol, queue provisioning, auth/TLS, HA và các chính sách broker cần được cấu hình và kiểm thử lại.

**Câu 5.** In ra `CachingConnectionFactory` khi debug nghĩa là Spring đang đóng vai trò JMS broker?

Trả lời: Không. Đó là wrapper của client-side `ConnectionFactory`; phía dưới vẫn có JMS provider client và dịch vụ messaging tương ứng.

## Nguồn tham khảo chính thức

- [Jakarta Messaging 3.1 Specification — Connection factories (mục 5.3) và Connections (mục 6.1)](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — hợp đồng, tính concurrent, `Connection` và `JMSContext`.
- [Jakarta Messaging 3.1 API — ConnectionFactory](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/jms/connectionfactory) — overloads `createConnection()/createContext()`, error model và session mode.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — `ConnectionFactory` với `JmsTemplate`, `SingleConnectionFactory` và `CachingConnectionFactory`.
- [Spring Boot Reference — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html) — auto-configuration của Artemis, provider configuration và caching/pooling.
- [Spring — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/) — ví dụ thực tế `JmsTemplate` và `@JmsListener`.
