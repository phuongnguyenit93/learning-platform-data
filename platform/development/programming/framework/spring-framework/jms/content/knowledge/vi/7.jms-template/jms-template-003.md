# JmsOperations như hợp đồng cho thành phần ứng dụng trong Spring JMS

## 1. Vấn đề: thành phần nghiệp vụ nên phụ thuộc vào điều gì?

Trong Spring JMS, cách gửi message quen thuộc là inject trực tiếp `JmsTemplate` và gọi `convertAndSend(...)`. Điều đó chạy tốt, nhưng đôi khi thành phần ứng dụng chỉ cần **khả năng gửi/nhận message**, không cần biết mọi chi tiết cấu hình của một template cụ thể.

Spring cung cấp interface **`org.springframework.jms.core.JmsOperations`** để diễn đạt hợp đồng này. `JmsTemplate` là implementation tiêu biểu của interface. Thay vì buộc mọi service khai báo `JmsTemplate`, ta có thể constructor-inject `JmsOperations`:

~~~java
private final JmsOperations jmsOperations;
~~~

Và gọi các hành vi trong hợp đồng:

~~~java
jmsOperations.convertAndSend("orders.events", "ORDER_CREATED:O-42");
~~~

Lợi ích thực tế: lớp ứng dụng tập trung vào thao tác JMS cần dùng; cấu hình kết nối, converter, QoS và vòng đời tài nguyên nằm ở phía Spring/implementation; khi unit test, có thể mock một interface duy nhất mà không cần mở broker.

**Phạm vi chính xác:** `JmsOperations` vẫn là **hợp đồng của Spring JMS**, không phải interface thuần nghiệp vụ và cũng không phải interface chuẩn `jakarta.jms`. Nó làm giảm phụ thuộc vào lớp cụ thể `JmsTemplate`, nhưng lớp ứng dụng vẫn phụ thuộc Spring. Nếu muốn domain hoàn toàn độc lập với JMS, cần thêm một cổng nghiệp vụ riêng, ví dụ `OrderEventPort`.

## 2. Vị trí của JmsOperations trong kiến trúc

~~~text
OrderEventPublisher (@Service)
  |
  | constructor dependency
  v
JmsOperations             <-- interface Spring JMS
  ^
  | implements
  |
JmsTemplate               <-- Spring implementation
  |
  +-- ConnectionFactory  <-- Artemis / broker provider
  +-- DestinationResolver
  +-- MessageConverter
  +-- QoS, transaction / timeout / resource management
  |
  v
Jakarta JMS Session / MessageProducer
  |
  v
Broker Queue / Topic
~~~

Trong application component, trách nhiệm thường là:

1. Chọn sự kiện hoặc command cần gửi theo kết quả xử lý nghiệp vụ.
2. Chọn destination hợp đồng đã được cấu hình.
3. Tạo payload và metadata ứng dụng cần thiết.
4. Gọi một thao tác `JmsOperations`.
5. Xử lý lỗi hoặc đưa ra kết quả theo chính sách nghiệp vụ.

Những việc như thiết lập host/port broker, username/password, pooling, caching hoặc chỉnh `JmsTemplate#setReceiveTimeout(...)` thuộc **cấu hình hạ tầng**, không phải trách nhiệm của service gửi sự kiện.

Ví dụ cách phân lớp:

| Thành phần | Vai trò |
| --- | --- |
| `OrderService` | Xác định lúc nào đơn hàng được tạo |
| `OrderEventPublisher` | Chuyển ý định nghiệp vụ thành payload/metadata và gọi `JmsOperations` |
| `JmsOperations` | Khai báo những thao tác JMS mà publisher được phép gọi |
| `JmsTemplate` | Thực thi thao tác, quản lý session/producer và chuyển đổi JMS exception thành Spring exception |
| `ConnectionFactory` | Tạo connection tới provider |
| Broker | Định tuyến, lưu giữ và phân phối message |

**Không nhầm:** interface `JmsOperations` không phải listener container. `@JmsListener` được xử lý bởi cơ chế listener của Spring; listener vẫn cần factory/container được cấu hình đúng.

## 3. JmsOperations là gì, JmsTemplate là gì?

`JmsOperations` nằm trong package:

~~~java
import org.springframework.jms.core.JmsOperations;
~~~

Nó cung cấp các hoạt động JMS ở mức template, trong đó có:

| Nhóm | API tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Gửi message JMS nguyên bản | `send(String, MessageCreator)` | Tạo `jakarta.jms.Message` qua callback rồi gửi |
| Chuyển đổi và gửi object | `convertAndSend(String, Object)` | Dùng `MessageConverter` tạo JMS message |
| Điều chỉnh message sau convert | `convertAndSend(String, Object, MessagePostProcessor)` | Bổ sung header/property trước khi gửi |
| Nhận đồng bộ | `receive(String)` | Nhận `jakarta.jms.Message` từ destination chỉ định |
| Nhận và convert | `receiveAndConvert(String)` | Nhận rồi chuyển JMS message thành object |
| Nhận có selector | `receiveSelected(String, String)` | Lọc message bằng JMS selector |
| Request/reply | `sendAndReceive(String, MessageCreator)` | Gửi request và chờ reply bằng temporary queue |
| Duyệt Queue | `browse(String, BrowserCallback<T>)` | Duyệt một queue mà không consume message |
| Callback cấp session/producer | `execute(...)` | Thao tác thấp hơn khi những method trên chưa đủ |

Có thêm overload nhận `Destination`, nhận default destination hoặc selector, tùy method. **Không nên ghi nhớ bảng như toàn bộ chữ ký**; khi cần API cụ thể hãy tra Javadoc đúng phiên bản Spring Framework của dự án.

`JmsTemplate` là lớp cụ thể cung cấp implementation của những lời gọi trên, và có các setter/getter dành cho cấu hình như `setDefaultDestinationName(...)`, `setReceiveTimeout(...)`, `setPubSubDomain(...)` và `setExplicitQosEnabled(...)`. Những setter này không phải thao tác được hứa bởi interface `JmsOperations`.

~~~java
// Lớp ứng dụng chỉ yêu cầu hợp đồng:
public OrderEventPublisher(JmsOperations operations) {
    this.operations = operations;
}
~~~

Spring sẽ inject bean triển khai interface, thường là `JmsTemplate` tự cấu hình bởi Spring Boot, miễn là trong container có **một candidate phù hợp**. Java không cần adapter phụ chỉ để ép kiểu, vì `JmsTemplate implements JmsOperations`.

### 3.1. So với JmsMessagingTemplate / JmsMessageOperations

Tên gần giống nhưng thuộc hai kiểu abstraction khác nhau:

- `JmsOperations`: làm việc với kiểu Jakarta JMS như `Message`, `Session`, `MessageCreator`.
- `JmsTemplate`: implementation của `JmsOperations`.
- `JmsMessageOperations`: giao diện mang phong cách Spring Messaging, sử dụng những khái niệm như `org.springframework.messaging.Message<?>`.
- `JmsMessagingTemplate`: implementation Spring Messaging dựa trên JMS, không phải tên gọi khác của `JmsTemplate`.

Nếu một service cần truy cập trực tiếp header JMS hay callback `MessagePostProcessor`, `JmsOperations` phù hợp. Nếu phần còn lại của ứng dụng đã chuẩn hóa trên Spring Messaging `Message<?>`, cân nhắc `JmsMessageOperations`. Việc chọn interface dựa trên ngôn ngữ abstraction mà lớp ứng dụng cần, không dựa vào tên ngắn hơn.

## 4. Vì sao inject interface giúp kiểm thử tốt hơn?

So sánh:

~~~java
// Phụ thuộc implementation cụ thể:
private final JmsTemplate jmsTemplate;

// Phụ thuộc hợp đồng thao tác:
private final JmsOperations jmsOperations;
~~~

Cả hai đều hợp lệ, và một `JmsTemplate` vẫn có thể mock được. Khác biệt hữu ích là với interface, đơn vị test có thể chỉ định rõ **lớp này cần khả năng nào**, tạo mock/stub của contract và verify request được gửi. Không cần mock cả `ConnectionFactory`, `Session`, `MessageProducer` hay mở một broker thật trong unit test.

Lợi ích cần hiểu đúng:

- **Thuận tiện mock**: kiểm tra destination, body, header/property mà service yêu cầu.
- **Giảm ràng buộc vào setter của implementation**: application service không được phép tùy ý đổi shared template.
- **Dễ thay cách cấu hình**: chỉnh cache, timeout, converter, broker mà không viết lại constructor/service nếu vẫn giữ hợp đồng.
- **Nêu ranh giới trách nhiệm**: service tạo thông điệp; hạ tầng thực hiện JMS.

**Không có phép màu:** unit test với mock `JmsOperations` **không chứng minh** JMS converter hoạt động, broker tồn tại, ACL đúng, message thực sự được nhận hay ACK thành công. Những điểm đó cần integration test có broker.

## 5. Dự án mẫu Java 17 + Spring Boot 3.3 + Artemis

Ta xây ví dụ hoàn chỉnh: khi ứng dụng khởi chạy, `OrderEventPublisher` nhận `JmsOperations` qua constructor rồi gửi sự kiện đơn hàng tới Queue; `OrderEventListener` đọc và in kết quả. Sau đó viết **unit test không cần broker** để kiểm tra contract.

Phạm vi ví dụ: chỉ một Queue `orders.events`, một message dạng text, metadata minh họa. Không dùng JPA hoặc transaction DB để tránh lẫn với hợp đồng JMS.

### 5.1. Khởi động broker dành cho local

Máy cần Docker. Ví dụ với image Artemis chính thức:

~~~bash
docker run --detach --rm --name artemis-ops-demo -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Đợi broker khởi động xong:

~~~bash
docker logs artemis-ops-demo
~~~

Cấu hình `demo/demo` chỉ dành cho local. Nếu broker không cho tự tạo Queue, cần tạo `orders.events` và cấp quyền send/consume trước. Dùng container mẫu không chứng nhận chính sách persistence hoặc security cho production.

### 5.2. Build scripts

File `settings.gradle`:

~~~groovy
rootProject.name = 'jms-operations-contract'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

test {
    useJUnitPlatform()
}
~~~

Với Spring Boot 3, code JMS phải import `jakarta.jms.*`. Đừng trộn client thư viện `javax.jms.*` cũ. Dùng Gradle 8.x tương thích và JDK 17+. Version ở đây cố định để ví dụ nhất quán, không hàm ý đây là bản mới nhất.

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}

spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=2s
app.jms.orders-destination=orders.events
~~~

Spring thay thế những biểu thức `${KEY:default}` trong bài này theo cú pháp chuẩn `$` + `{KEY:default}`. Ở chuỗi Markdown đã lưu, các dòng trên mang đúng dạng property placeholder Spring. Trong production, bỏ các fallback credential `demo` và truyền thông tin từ secret manager.

`spring.jms.pub-sub-domain=false` thiết lập Queue mode. `spring.jms.template.receive-timeout=2s` áp dụng khi **nhận đồng bộ** bằng `JmsTemplate`; nó không biến việc publish thành thao tác chờ 2 giây và không phải listener timeout chung.

### 5.3. Entry point và tình huống chạy

File `src/main/java/demo/jms/JmsOperationsApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class JmsOperationsApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsOperationsApplication.class, args);
    }

    @Bean
    CommandLineRunner publishDemo(OrderEventPublisher publisher) {
        return args -> publisher.publishOrderCreated("O-42");
    }
}
~~~

`CommandLineRunner` ở đây chỉ là cách kích hoạt một lần khi khởi động để người học thấy message di chuyển. Ứng dụng production nên gọi publisher tại thời điểm nghiệp vụ thực sự xảy ra, không tự phát lại một sự kiện mỗi lần restart.

### 5.4. Thành phần ứng dụng phụ thuộc JmsOperations

File `src/main/java/demo/jms/OrderEventPublisher.java`:

~~~java
package demo.jms;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsOperations;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final JmsOperations operations;
    private final String destination;

    public OrderEventPublisher(
            JmsOperations operations,
            @Value("${app.jms.orders-destination}") String destination) {
        this.operations = operations;
        this.destination = destination;
    }

    public void publishOrderCreated(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }

        String body = "ORDER_CREATED:" + orderId;

        operations.convertAndSend(destination, body, message -> {
            message.setStringProperty("eventType", "order.created");
            message.setJMSCorrelationID("order-" + orderId);
            return message;
        });
    }
}
~~~

Trong code này, điều quan trọng là field và constructor **nhận `JmsOperations`**, không yêu cầu `JmsTemplate`. Spring Boot tự cấu hình `JmsTemplate` làm implementation khi Artemis starter và ConnectionFactory khả dụng.

Diễn giải dòng mã:

1. `@Value(...)` lấy tên destination từ cấu hình; service không cần biết Queue host/port là gì.
2. Validate `orderId` trước khi gọi broker; dữ liệu không hợp lệ gây exception ngay ở application layer.
3. `convertAndSend(String, Object, MessagePostProcessor)` thuộc interface `JmsOperations`. Nó dùng converter của template để biến `String` thành JMS `TextMessage`.
4. Callback `MessagePostProcessor` gắn property `eventType` và header `JMSCorrelationID` **sau chuyển đổi, trước gửi**.
5. Provider sinh những header do broker kiểm soát như `JMSMessageID`. Không đặt thủ công chúng trong service.

Cách gọi qua interface cho phép viết test kiểm tra chính xác ý định “gửi sự kiện đơn hàng với body và metadata nào” mà không mở network.

### 5.5. Listener bên nhận hoạt động độc lập

File `src/main/java/demo/jms/OrderEventListener.java`:

~~~java
package demo.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @JmsListener(destination = "${app.jms.orders-destination}")
    public void onOrderEvent(String body) {
        System.out.println("RECEIVED: " + body);
    }
}
~~~

Listener thuộc cơ chế `@JmsListener` của Spring; **không** bắt buộc inject `JmsOperations` để tiêu thụ message theo kiểu listener bất đồng bộ. Spring Boot + `@EnableJms` tạo hạ tầng nhận cần thiết, còn `JmsOperations` phục vụ những thao tác chủ động của thành phần gửi/nhận đồng bộ.

### 5.6. Chạy và quan sát

~~~bash
gradle test
gradle bootRun
~~~

Với broker đang hoạt động, Queue có thể tạo/đã tồn tại và user có quyền, console của ứng dụng sẽ có:

~~~text
RECEIVED: ORDER_CREATED:O-42
~~~

Đây là **dòng do listener của ví dụ in ra**; thứ tự của log Spring và broker khác nhau theo môi trường. Phần publisher không tự in thêm một dòng success. Một lần start có một lần gọi publish bởi `CommandLineRunner`; nếu có consumer khác tranh Queue, listener của ví dụ không nhất thiết là consumer nhận được message.

Khi xong:

~~~bash
docker stop artemis-ops-demo
~~~

**Ý nghĩa kiểm tra:** log nhận được cho thấy kết nối, gửi, định tuyến và callback listener đã hoạt động trong điều kiện thử. Việc listener in log chưa thay thế xác nhận giao dịch nghiệp vụ và chính sách idempotency.

## 6. Unit test tập trung vào hợp đồng, không cần broker

Đây là điểm thể hiện rõ lợi ích của `JmsOperations`. Test chỉ kiểm tra **dịch vụ sử dụng contract**; không tạo Spring ApplicationContext, không inject connection factory và không cần Docker.

File `src/test/java/demo/jms/OrderEventPublisherTest.java`:

~~~java
package demo.jms;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.jms.core.JmsOperations;
import org.springframework.jms.core.MessagePostProcessor;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderEventPublisherTest {

    @Test
    void publishesCorrectDestinationBodyAndMetadata()
            throws JMSException {
        JmsOperations operations = mock(JmsOperations.class);
        var publisher = new OrderEventPublisher(
                operations, "orders.events");

        publisher.publishOrderCreated("O-42");

        ArgumentCaptor<MessagePostProcessor> captor =
                ArgumentCaptor.forClass(MessagePostProcessor.class);

        verify(operations).convertAndSend(
                eq("orders.events"),
                eq("ORDER_CREATED:O-42"),
                captor.capture());

        // Kích hoạt callback đã truyền tới JmsOperations:
        Message message = mock(Message.class);
        assertSame(message, captor.getValue()
                .postProcessMessage(message));

        verify(message).setStringProperty(
                "eventType", "order.created");
        verify(message).setJMSCorrelationID("order-O-42");
    }

    @Test
    void rejectsBlankOrderIdBeforeSending() {
        JmsOperations operations = mock(JmsOperations.class);
        var publisher = new OrderEventPublisher(
                operations, "orders.events");

        assertThrows(IllegalArgumentException.class,
                () -> publisher.publishOrderCreated("  "));

        verifyNoInteractions(operations);
    }
}
~~~

Lệnh:

~~~bash
gradle test
~~~

**Hai test trên không khởi tạo broker.** Test thứ nhất verify đúng overload có `MessagePostProcessor`, kiểm tra tên destination, body và kích hoạt callback với JMS `Message` mock để xác minh header/property. Test thứ hai bảo đảm dữ liệu đầu vào sai bị từ chối trước khi có JMS call.

Khi pass, Gradle báo hoàn thành task test; chi tiết log phụ thuộc cấu hình Gradle. Không cần đưa một `JMSMessageID` giả hoặc giả lập ACK, vì chúng không thuộc contract mà service đang kiểm thử.

### 6.1. Vì sao không mock JMS Session trực tiếp?

Nếu service tự gọi:

~~~java
// Minh họa API thô, chưa bao gồm phần quản lý resource:
Connection connection = connectionFactory.createConnection();
Session session = connection.createSession();
MessageProducer producer = session.createProducer(destination);
~~~

Một unit test sẽ phải dựng nhiều mock và mô phỏng vòng đời connection/session/producer, dễ tập trung vào chi tiết kỹ thuật thay vì ý định nghiệp vụ. `JmsOperations` che phần này dưới một thao tác gửi có thể xác minh qua Mockito.

Tuy nhiên, nếu ứng dụng cần một tính năng JMS cụ thể chưa được cung cấp ở mức template, `JmsOperations.execute(SessionCallback<T>)` vẫn cho phép dùng callback cấp session. Chỉ dùng khi cần, vì thao tác thấp hơn làm tăng chi tiết hạ tầng trong service.

## 7. Phân biệt kiểm thử đơn vị, tích hợp và end-to-end

| Kiểu kiểm thử | Thành phần thật | Điều thực sự chứng minh |
| --- | --- | --- |
| Unit test với mock `JmsOperations` | Chỉ publisher và test doubles | Service gọi đúng destination, body và metadata |
| Integration test với `JmsTemplate` và broker thật | Spring JMS + converter + broker | Message có thể được gửi/nhận và converter hoạt động |
| End-to-end với DB, consumer và retry/ACK | Quy trình nghiệp vụ hoàn chỉnh | Toàn bộ xử lý/commit/idempotency theo hợp đồng |

Nếu unit test pass mà consumer không nhận message, cần kiểm tra cấu hình broker, Queue/Topic mode, permission, selector, converter và listener container. Đó không phải thất bại của unit test; đơn giản là test chỉ có một phạm vi giới hạn.

Khi cần test tích hợp, dùng broker độc lập trong môi trường thử hoặc Testcontainers phù hợp. Tránh mô phỏng toàn bộ broker bằng Mockito rồi kết luận delivery semantics đã đúng.

## 8. Khi nào dùng convertAndSend, send, receive và sendAndReceive?

### 8.1. convertAndSend cho dữ liệu đơn giản

~~~java
operations.convertAndSend("orders.events", "ORDER_CREATED:O-42");
~~~

Dùng `MessageConverter` của `JmsTemplate`. Mặc định String thường thành `TextMessage`; nếu truyền DTO chưa có JSON converter phù hợp, có thể dùng Java serialization hoặc thất bại theo kiểu object/provider. **Đừng giả định POJO luôn thành JSON.**

Khi cần schema JSON, hãy định nghĩa converter rõ ràng và kiểm tra tương thích nội dung giữa producer/consumer. Cấu hình converter nằm ở infrastructure, không phải setter trên `JmsOperations`.

### 8.2. send khi tự tạo JMS Message

~~~java
operations.send("orders.events", session -> {
    var message = session.createTextMessage("ORDER_CREATED:O-42");
    message.setStringProperty("eventType", "order.created");
    return message;
});
~~~

Đây là **đoạn mã minh họa bên trong một method đã có biến `operations`**; không phải một file Java độc lập. `send` cho quyền tạo `TextMessage`, `BytesMessage` hoặc message type khác qua JMS `Session`.

Cân nhắc `send` khi cần kiểm soát chính xác kiểu message/body. Với dữ liệu String thông thường, `convertAndSend` ngắn và thể hiện ý định hơn.

### 8.3. receive / receiveAndConvert là đồng bộ

~~~java
Object payload = operations.receiveAndConvert("orders.events");
if (payload == null) {
    // Không nhận được message trước khi hết timeout.
}
~~~

`receiveAndConvert` và `receive` có thể **block thread**. Nếu timeout hết, kết quả có thể là `null`; phải xử lý case này. Tránh gọi trong luồng HTTP request khi không có SLA hoặc timeout phù hợp, vì nó có thể chặn thread lâu.

Cấu hình nhận đồng bộ, ví dụ:

~~~properties
spring.jms.template.receive-timeout=2s
~~~

Với dịch vụ nhận message liên tục, listener container + `@JmsListener` thường phù hợp hơn vòng lặp `receive` thủ công. Không dùng `receiveAndConvert` như cách “đọc kiểm tra” một Queue production, vì thao tác này **tiêu thụ message**.

### 8.4. receiveSelected và selector

~~~java
Object selected = operations.receiveSelectedAndConvert(
        "orders.events", "eventType = 'order.created'");
~~~

JMS selector lọc trên **properties và một số header chuẩn hỗ trợ**, không lọc trực tiếp bên trong JSON body. Property `eventType` trong ví dụ producer được đặt đúng kiểu String nên selector có thể dùng nó.

Như `receiveAndConvert`, lệnh này **nhận và consume** message, có thể block tới timeout. Nếu nhiều consumer cùng Queue, selector của một consumer quyết định message nào nó có thể nhận.

### 8.5. browse không consume message

~~~java
Integer count = operations.browse("orders.events",
        (session, browser) -> {
            int result = 0;
            var messages = browser.getEnumeration();
            while (messages.hasMoreElements()) {
                messages.nextElement();
                result++;
            }
            return result;
        });
~~~

Đây là snippet minh họa. `browse` hoạt động với **Queue** và không loại message như `receive`. Tuy nhiên nội dung Queue có thể đổi trong lúc duyệt; số đếm từ `QueueBrowser` không phải snapshot/metric chính xác dưới tải đồng thời. Để giám sát backlog production, ưu tiên chỉ số broker.

### 8.6. sendAndReceive cho request/reply

~~~java
Message response = operations.sendAndReceive(
        "inventory.requests",
        session -> session.createTextMessage("CHECK:O-42"));
~~~

Đây cũng là snippet trong method có biến `operations`. Phương thức gửi request và chờ response qua temporary queue do template tạo; phía nhận phải có listener thực sự gửi reply về `JMSReplyTo`. Kết quả có thể `null` nếu không có reply trước timeout.

Đừng dùng request/reply chỉ để xác minh rằng broker “đã nhận message” nếu nghiệp vụ thực sự chỉ cần publish event. `sendAndReceive` là mô hình trao đổi khác, tốn tài nguyên chờ và cần quản lý timeout, lỗi, correlation.

## 9. Hợp đồng không bao gồm cấu hình JmsTemplate

Một `JmsOperations` parameter **không** cung cấp những setter này:

~~~java
// Chỉ khi đang cấu hình chính JmsTemplate:
jmsTemplate.setPubSubDomain(false);
jmsTemplate.setReceiveTimeout(2_000L);
jmsTemplate.setDefaultDestinationName("orders.events");
~~~

Đây là **snippet cấu hình**, không dùng trong `OrderEventPublisher`. Các option có thể được thiết lập từ Spring Boot application properties hoặc một `@Bean JmsTemplate` được quản lý tập trung.

Việc service “ép kiểu ngược” để chỉnh cấu hình là dấu hiệu sai ranh giới:

~~~java
// Không nên làm trong code nghiệp vụ:
((JmsTemplate) operations).setReceiveTimeout(2_000L);
~~~

Nó làm mất lợi ích của interface và có thể thay đổi shared singleton đang được nhiều thread sử dụng. Nếu service thật sự cần một thao tác chỉ có ở implementation, hoặc cấu hình riêng, đưa yêu cầu đó vào infrastructure adapter/bean phù hợp.

### 9.1. Nếu Spring có nhiều bean cùng là JmsOperations

Trong ứng dụng một broker, `JmsTemplate` tự cấu hình thường là candidate đủ dùng. Trong hệ thống có nhiều broker/destination group, có thể có nhiều `JmsOperations` bean. Khi đó injection chỉ theo type có thể gây `NoUniqueBeanDefinitionException`.

Ví dụ **khi bean đã có tên `orderJmsTemplate`**:

~~~java
public OrderEventPublisher(
        @org.springframework.beans.factory.annotation.Qualifier(
                "orderJmsTemplate") JmsOperations operations,
        @Value("${app.jms.orders-destination}") String destination) {
    this.operations = operations;
    this.destination = destination;
}
~~~

Snippet trên minh họa việc chọn bean. Nó sẽ thay **constructor hiện tại** nếu dự án thật có nhiều factory; không thêm cả hai constructor vào cùng sample mà không điều chỉnh wiring. `@Qualifier` chỉ hoạt động nếu bean name/qualifier được định nghĩa thực sự trong container; nó không tự tạo bean.

Nên quản lý `ConnectionFactory`, converters và destination naming tại một nơi, để ứng dụng không vô tình gửi message sang broker khác.

## 10. JmsOperations và ranh giới nghiệp vụ sạch hơn

Inject `JmsOperations` thường là bước hợp lý khi application layer chấp nhận phụ thuộc Spring. Nếu mục tiêu là domain/service **không phụ thuộc framework messaging**, hãy định nghĩa interface theo **ngôn ngữ nghiệp vụ**:

~~~java
// Cổng domain/application riêng, minh họa:
public interface OrderEventPort {
    void publishOrderCreated(String orderId);
}
~~~

Adapter JMS:

~~~java
// Chỉ minh họa quan hệ kiến trúc, không thay thế
// dự án mẫu ở trên nếu chưa tạo OrderEventPort.
public final class JmsOrderEventAdapter implements OrderEventPort {
    private final JmsOperations operations;

    public JmsOrderEventAdapter(JmsOperations operations) {
        this.operations = operations;
    }

    @Override
    public void publishOrderCreated(String orderId) {
        operations.convertAndSend(
                "orders.events", "ORDER_CREATED:" + orderId);
    }
}
~~~

Giờ một `OrderService` có thể inject `OrderEventPort` mà không biết JMS. Adapter triển khai bằng `JmsOperations`; nếu về sau chuyển sang Kafka, việc thay adapter không tác động đến business service, miễn là hợp đồng nghiệp vụ được giữ.

**Ba mức phụ thuộc:**

| Mức | Component phụ thuộc vào | Mục đích |
| --- | --- | --- |
| Implementation | `JmsTemplate` | Muốn dùng cả API cấu hình/implementation cụ thể |
| Spring contract | `JmsOperations` | Muốn dùng tập thao tác JMS, dễ mock và không biết lớp concrete |
| Domain port | `OrderEventPort` | Muốn business code độc lập framework/broker |

Không nhất thiết mọi ứng dụng đều cần thêm một domain port. Với project nhỏ, `JmsOperations` là ranh giới nhẹ và rõ. Khi cần thay đổi messaging stack hoặc unit test domain độc lập hoàn toàn, domain port có giá trị rõ hơn.

## 11. Lỗi, transaction, retry: giới hạn của interface

Những lời gọi như `convertAndSend` có thể ném `org.springframework.jms.JmsException` (unchecked), do `JmsTemplate` chuyển đổi từ lỗi provider/JMS. Service có thể bắt lỗi khi thật sự có chính sách phản ứng, nhưng không nên che lỗi rồi báo nghiệp vụ thành công.

~~~java
// Snippet minh họa trong một method:
try {
    operations.convertAndSend("orders.events", "ORDER_CREATED:O-42");
} catch (org.springframework.jms.JmsException failure) {
    // Ghi log an toàn và áp chính sách retry/dead-letter/outbox phù hợp.
    throw failure;
}
~~~

**Đừng suy ra** phương thức return bình thường nghĩa là consumer đã xử lý/ACK. Nó chỉ thể hiện thao tác gửi hoàn tất theo hợp đồng template/provider tại thời điểm đó.

Cần đặc biệt thận trọng ở các tình huống:

- **Network đứt ngay lúc send**: producer có thể không chắc broker đã nhận message hay chưa; retry có thể gây duplicate.
- **Consumer ném exception**: transaction/ACK mode quyết định message có bị giao lại hay không.
- **DB commit rồi JMS send thất bại**: nếu không có transaction/outbox phù hợp, có thể có trạng thái DB đã đổi mà message chưa gửi.
- **JMS send xong rồi DB rollback**: cũng có thể làm lệch trạng thái nếu hai thao tác không nằm trong giao dịch được phối hợp.
- **Thread safety**: `JmsTemplate` là singleton dùng chung phù hợp sau cấu hình; không chỉnh setter động trên từng request.

Với sự kiện nghiệp vụ quan trọng, cân nhắc **transactional outbox**, idempotency key, retry/backoff và dead-letter policy. Interface `JmsOperations` không tự bảo đảm exactly-once xuyên hệ thống.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Inject interface thì không còn phụ thuộc Spring” | `JmsOperations` vẫn thuộc `org.springframework.jms.core` |
| “JmsOperations tự tạo kết nối JMS” | `JmsTemplate` và `ConnectionFactory` thực thi và quản lý tài nguyên |
| “Service phải tạo bean JmsOperations riêng” | Một `JmsTemplate` bean phù hợp đã thỏa mãn interface; Boot có thể auto-configure |
| “JmsOperations và JmsMessagingTemplate là một” | Khác abstraction: Jakarta JMS message so với Spring Messaging message |
| “convertAndSend với DTO sẽ luôn thành JSON” | Phụ thuộc `MessageConverter` được cấu hình |
| “Mock test pass nghĩa là broker đã nhận” | Mock chỉ xác minh tương tác với contract |
| “receiveAndConvert là đọc thử không làm mất message” | Nó thực sự consume từ destination |
| “receive không thể block vì thuộc interface” | Nó là thao tác nhận đồng bộ, cần timeout |
| “sendAndReceive chỉ gửi request không cần response listener” | Cần bên nhận gửi reply và cần timeout |
| “JMS send trả về là người nhận đã commit” | Gửi, nhận và ACK/commit là các bước khác nhau |
| “Qualifier tự chọn broker theo destination” | Qualifier chọn bean đã đăng ký; không định tuyến message dựa trên tên |
| “Bắt JmsException rồi bỏ qua thì không mất dữ liệu” | Có thể âm thầm làm mất sự kiện; cần policy xử lý lỗi |

## 13. Gợi ý lựa chọn API trong từng tình huống

- **Application service chỉ publish thông báo**: inject `JmsOperations`, gọi `convertAndSend` hoặc `send`, dùng destination ngoài cấu hình.
- **Cần header/property**: dùng overload `convertAndSend(..., MessagePostProcessor)` hoặc `send(..., MessageCreator)`.
- **Worker tiêu thụ liên tục**: dùng `@JmsListener` thay cho một vòng lặp `receiveAndConvert` tự viết.
- **Tác vụ thỉnh thoảng cần poll Queue**: dùng `JmsOperations.receiveAndConvert` nhưng phải đặt timeout và xử lý `null`.
- **Yêu cầu request/reply rõ ràng**: cân nhắc `sendAndReceive`, cấu hình timeout và consumer reply.
- **Business code phải độc lập Spring**: định nghĩa domain/application port và để adapter JMS phụ thuộc `JmsOperations`.
- **Muốn chỉnh QoS/caching/transaction**: làm ở cấu hình factory, `JmsTemplate` và listener, không chỉnh từ service gửi.
- **Muốn chứng minh có delivery thực tế**: viết integration test với broker, bên cạnh unit test mock interface.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao constructor nhận `JmsOperations` vẫn có thể được inject một `JmsTemplate`?

Vì `JmsTemplate` implements `JmsOperations`; Spring inject bean có kiểu tương thích.

**Câu 2.** Inject `JmsOperations` có khiến lớp ứng dụng độc lập Spring Framework không?

Không. Đây là interface của Spring JMS. Muốn độc lập framework ở domain, tạo port riêng.

**Câu 3.** Một unit test mock `JmsOperations` xác minh được điều gì?

Xác minh service gọi đúng method/destination/payload/metadata và hành vi lỗi tại lớp ứng dụng; không chứng minh kết nối broker.

**Câu 4.** Tại sao `receiveAndConvert` phải có timeout?

Nó là lời gọi đồng bộ có thể block nếu queue không có message; trả về `null` khi quá thời gian chờ.

**Câu 5.** `@JmsListener` có phải method của interface `JmsOperations` không?

Không. Đó là endpoint do listener infrastructure của Spring quản lý riêng.

**Câu 6.** Có nên cast `JmsOperations` sang `JmsTemplate` để chỉnh timeout trong từng request?

Không. Đưa timeout vào hạ tầng/configuration; shared template không nên bị thay đổi động bởi nghiệp vụ.

**Câu 7.** `JmsOperations.sendAndReceive` có cần consumer phản hồi?

Có. Nó tạo temporary queue nhận reply nhưng vẫn cần đầu nhận thực sự gửi response.

**Câu 8.** Nếu một lệnh publish thành công, ta có thể bỏ logic chống trùng lặp ở consumer không?

Không. Redelivery/retry, transaction và các lỗi mạng có thể tạo xử lý lặp; cần idempotency phù hợp.

## 15. Tài liệu chính thức

- Spring Framework 6.1 — Javadoc `JmsOperations` (hợp đồng và đầy đủ chữ ký): https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/jms/core/JmsOperations.html
- Spring Framework — Javadoc `JmsTemplate`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework — Sử dụng Spring JMS, JmsTemplate và listener: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — `@JmsListener`: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot — JMS support và auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Spring Boot — Application properties (JMS template/listener): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/

**Ghi nhớ:** `JmsOperations` là **interface hành vi** mà application service có thể phụ thuộc; `JmsTemplate` là **implementation** quản lý công việc JMS thực tế; mock interface giúp unit test tập trung vào ý định gửi/nhận. Nếu muốn ứng dụng hoàn toàn độc lập JMS, hãy bổ sung **domain port** của riêng hệ thống.
