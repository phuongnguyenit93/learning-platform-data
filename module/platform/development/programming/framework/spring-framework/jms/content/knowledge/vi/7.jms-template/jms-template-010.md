# Phân biệt cấu hình dùng chung với tùy chỉnh theo từng thao tác của JmsTemplate

## 1. Vấn đề cần giải quyết

Trong Spring JMS, một ứng dụng thường có nhiều service cùng gửi/nhận message thông qua `org.springframework.jms.core.JmsTemplate`. Câu hỏi quan trọng là: thuộc tính nào nên được cấu hình **một lần khi khởi tạo bean**, thuộc tính nào có thể **thay đổi theo mỗi lần gửi/nhận**, và khi nào phải dùng một template khác?

Ví dụ một hệ thống phát hóa đơn có ba yêu cầu:
- Mọi lệnh mặc định gửi đến Queue `billing.invoice.commands`, dùng chung `ConnectionFactory`, bộ chuyển đổi payload và receive timeout.
- Một lần gửi cụ thể phải thêm `correlationId` và property `eventType` để truy vết/phân loại.
- Một thông điệp khẩn cấp cần `priority=8` và `timeToLive=10_000 ms`; các lệnh bình thường dùng `priority=4` và `timeToLive=60_000 ms`.

Giải pháp không phải gọi `jmsTemplate.setPriority(8)` trước khi gửi rồi đổi lại `4`. Vì `JmsTemplate` được chia sẻ giữa nhiều luồng, kiểu chỉnh trạng thái như vậy tạo nguy cơ **race condition**: một service khác có thể gửi trong khoảng template đang bị thay đổi.

**Quy tắc cốt lõi: cấu hình đối tượng `JmsTemplate` hoàn tất lúc khởi tạo rồi dùng lại; tùy chỉnh từng message qua tham số phương thức/callback, hoặc dùng một template được cấu hình riêng cho chính sách ổn định khác.**

Bài dùng Spring Framework 6.x, Spring Boot 3.x, `jakarta.jms.*` và Java 17+. Từ “cấu hình chung” ở đây nói về trạng thái ổn định của template trong cùng Spring context, không có nghĩa mọi Queue, Topic hoặc listener trên broker phải chia sẻ chính sách giống nhau.

## 2. JmsTemplate làm gì?

`JmsTemplate` là lớp hỗ trợ truy cập JMS đồng bộ: nó lấy `Connection`/`Session` khi cần, tạo/gửi message hoặc nhận message, thu hồi tài nguyên, thực hiện chuyển đổi checked `JMSException` sang `JmsException` không kiểm tra của Spring. Nó không phải broker và không phải kho lưu trạng thái cuộc hội thoại.

~~~text
Service A ───────┐
                 │
Service B ───────┼──> JmsTemplate bean dùng chung
                 │        │
Service C ───────┘        ├── ConnectionFactory
                          ├── DestinationResolver
                          ├── MessageConverter
                          ├── Default destination / Queue-Topic mode
                          ├── Default QoS / receive timeout
                          │
                          └── send/receive -> JMS provider -> broker

Mỗi lời gọi có thể truyền:
    destination cụ thể
    payload / MessageCreator
    MessagePostProcessor (headers, properties)
    ProducerCallback (gửi bằng QoS riêng)
    selector (nhận có điều kiện)
~~~

Theo Spring Framework, `JmsTemplate` **thread-safe sau khi được cấu hình xong**. Nhiều service có thể inject cùng một bean và gọi `convertAndSend(...)` đồng thời. Điều kiện nằm ở phần “sau khi cấu hình”: các setter như `setDefaultDestinationName`, `setMessageConverter` hoặc `setTimeToLive` thay đổi chính template, vì vậy không dùng chúng như biến tạm của một request.

Tính thread-safe của template không có nghĩa một `jakarta.jms.Session` hoặc `MessageProducer` có thể tùy tiện chia sẻ qua các luồng. Chúng được framework/provider quản lý theo phạm vi phiên làm việc hoặc callback phù hợp.

## 3. Phân loại chính xác: dùng chung và theo thao tác

| Nhu cầu | Cấu hình dùng chung ở bean | Tùy chỉnh theo một lời gọi |
|---|---|---|
| Kết nối broker | `setConnectionFactory(...)`; credentials/TLS/pool bên dưới `ConnectionFactory` | Thông thường không đổi factory trong lời gọi; dùng bean khác cho broker/chính sách khác. |
| Kiểu destination | `setPubSubDomain(false)` cho Queue hoặc `true` cho Topic khi resolve tên động | `send(Destination, ...)` hoặc factory/template riêng khi cần loại đích khác. |
| Tên destination | `setDefaultDestinationName(...)` hoặc `setDefaultDestination(...)` | Truyền tên vào `convertAndSend("queue.name", ...)`, `send("queue.name", ...)` hoặc `receiveSelected("queue.name", ...)`. |
| Chuyển payload | `setMessageConverter(...)`, mặc định `SimpleMessageConverter` | `send(..., MessageCreator)` để tạo một `TextMessage`/`BytesMessage` cụ thể; `convertAndSend(..., MessagePostProcessor)` bổ sung sau chuyển đổi. |
| Headers/properties | Quy ước chung trong converter hoặc logic service | `MessagePostProcessor` sửa `JMSCorrelationID`, application properties như `eventType`, `tenantCode`. |
| QoS gửi | `setExplicitQosEnabled(true)` và `setDeliveryMode`, `setPriority`, `setTimeToLive` | `execute(destination, ProducerCallback)` và gọi `producer.send(message, deliveryMode, priority, timeToLive)` cho lần gửi cần đặc biệt; hoặc dùng bean template khác. |
| Độ trễ giao message | `setDeliveryDelay(...)` (cần provider/JMS API hỗ trợ) | Với API cấp thấp, dùng producer phù hợp trên phạm vi lời gọi; không thay setter của singleton theo request. |
| Timeout của receive | `setReceiveTimeout(milliseconds)` | `receive(destination)`/`receiveSelected(destination, selector)` chọn đích/selector; các overload này không nhận receive timeout riêng. Muốn chính sách timeout khác, cân nhắc template khác hoặc callback có timeout được quản lý cẩn thận. |
| Transaction/session | `setSessionTransacted(...)` và cấu hình `JmsTransactionManager`/transaction manager | Gắn phạm vi transaction ở tầng service; không bật/tắt `sessionTransacted` ngay giữa các lời gọi. |
| Listener | **Không do JmsTemplate quyết định**; thuộc `DefaultJmsListenerContainerFactory` và listener container | `@JmsListener` có đích/selector/subscription riêng; concurrency/acknowledgement thường ở listener factory. |

Hai lưu ý:
1. “Theo lời gọi” có thể là **tham số** hoặc **callback** chạy với tài nguyên do Spring tạo. Nó không có nghĩa gọi setter trên bean dùng chung.
2. Gửi message đến destination khác không tự biến Queue thành Topic. Với tên động, `pubSubDomain` và `DestinationResolver` vẫn quyết định cách tạo/resolve đích. Khi dùng destination object tường minh, loại đối tượng JMS quyết định ngữ nghĩa.

## 4. Cấu hình dùng chung: một bean ổn định

Đoạn Spring configuration dưới đây minh họa chính sách mặc định cho **Queue**. Mã là một lớp cấu hình có thể biên dịch khi dự án đã khai báo `spring-jms` và có một `jakarta.jms.ConnectionFactory` phù hợp.

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class SharedJmsConfiguration {

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);

        // Các thiết lập cố định cho mọi lời gọi sử dụng bean này.
        template.setDefaultDestinationName("billing.invoice.commands");
        template.setPubSubDomain(false);           // Queue
        template.setReceiveTimeout(3_000L);       // Nhận đồng bộ tối đa 3 giây

        // Dùng QoS được chỉ định ở template, thay vì default của provider.
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(4);
        template.setTimeToLive(60_000L);

        return template;
    }
}
~~~

Trong thực tế, Spring Boot có thể tự cấu hình `JmsTemplate` nếu có provider `ConnectionFactory` và chưa có bean thay thế. Tạo `@Bean` tường minh khi cần một chính sách nhất quán hoặc kiểm soát nguồn cấu hình; không bắt buộc tự cấu hình mọi thuộc tính.

**Ý nghĩa các setter:**
- `setDefaultDestinationName`: dùng khi gọi `convertAndSend(payload)`, `send(messageCreator)` hoặc `receive()` mà không truyền destination.
- `setPubSubDomain(false)`: tên được resolve ở chế độ Queue trong ví dụ. Tính chất Queue/Topic phải khớp hạ tầng broker.
- `setReceiveTimeout(3_000L)`: giới hạn chờ cho thao tác **receive đồng bộ** của template; không phải timeout kết nối broker, timeout xử lý `@JmsListener` hay timeout gửi message.
- `setExplicitQosEnabled(true)`: khiến các thông số `deliveryMode`, `priority`, `timeToLive` của template được dùng khi Spring gọi producer.send; nếu `false`, provider default có thể được dùng.
- `DeliveryMode.PERSISTENT` và TTL không đồng nghĩa message chắc chắn sống sót vô thời hạn: độ bền thực tế còn tùy broker persistence, transaction, retention, expire policy và destination/subscription.

Có thể để `MessageConverter` mặc định là `SimpleMessageConverter` cho `String`/`TextMessage`. Khi toàn ứng dụng dùng một chuẩn JSON, thay converter chung bằng converter đã cấu hình phù hợp là quyết định hợp lý, song đó là một hợp đồng payload riêng cần quản lý version.

## 5. Dùng chung một JmsTemplate trong nhiều service

Một service gửi bình thường không cần quan tâm chi tiết JMS:

~~~java
package example.jms;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoiceCommandPublisher {
    private final JmsTemplate jmsTemplate;

    public InvoiceCommandPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void requestIssue(String invoiceId) {
        // Sử dụng destination mặc định và QoS mặc định của bean.
        jmsTemplate.convertAndSend(invoiceId);
    }

    public void requestCancel(String invoiceId) {
        // Ghi đè destination CHỈ cho lời gọi này.
        jmsTemplate.convertAndSend(
                "billing.invoice.cancel", invoiceId);
    }
}
~~~

Hai lời gọi vẫn dùng cùng `ConnectionFactory`, converter và chính sách QoS. Lời gọi thứ hai không làm thay đổi `getDefaultDestinationName()` của template. Lần kế tiếp gọi `convertAndSend(invoiceId)` vẫn sử dụng `billing.invoice.commands`.

Khi nhiều bean inject cùng singleton, không có vấn đề về **đọc trạng thái cấu hình bất biến theo quy ước**; vấn đề xuất hiện khi code gọi `setDefaultDestinationName(...)` để thay đổi đích trước một send. Thay vào đó, truyền đích ngay ở chữ ký phương thức.

### Tên vật lý và cấu hình môi trường

Trên môi trường `dev`, Queue có thể là `dev.billing.invoice.commands`; trên `prod` là `prod.billing.invoice.commands`. Đặt tên thực tế trong `application.yml`/biến môi trường và inject bằng `@Value` hoặc `@ConfigurationProperties`; business code không tự đoán môi trường hoặc ghép prefix từ request. Cấu hình destination mang tính triển khai, còn key logic trong ứng dụng cần ổn định.

Ví dụ có thể thay `setDefaultDestinationName("billing.invoice.commands")` bằng giá trị inject vào method `@Bean` qua một property. Việc này vẫn là **cấu hình một lần khi tạo template**, không phải thay tên sau mỗi request.

## 6. Tùy chỉnh một message bằng MessagePostProcessor

`JmsTemplate.convertAndSend(destination, payload, postProcessor)` làm hai bước: trước tiên `MessageConverter` chuyển payload Java thành JMS `Message`; sau đó `MessagePostProcessor` có cơ hội cập nhật headers/properties của **message vừa tạo**, ngay trước send.

Ví dụ gửi sự kiện mang correlation ID và thuộc tính để consumer lọc:

~~~java
package example.jms;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class EventPublisher {
    private final JmsTemplate jmsTemplate;

    public EventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String orderId, String correlationId) {
        jmsTemplate.convertAndSend(
                "billing.invoice.commands",
                "ISSUE:" + orderId,
                message -> {
                    message.setJMSCorrelationID(correlationId);
                    message.setStringProperty("eventType", "INVOICE_ISSUE");
                    message.setStringProperty("producer", "order-service");
                    return message;
                });
    }
}
~~~

Ví dụ này chạy khi có broker/provider và cấu hình Spring JMS; nó không phải một `main` độc lập. `MessagePostProcessor` có thể ném `jakarta.jms.JMSException`, và template chuyển checked exception khi bắt được sang `org.springframework.jms.JmsException`.

**Điểm mạnh:** callback được gọi cho một lần gửi, không đổi `MessageConverter` hoặc `defaultDestinationName` của bean. Các lời gọi song song có thể mang correlation ID khác nhau.

**Không dùng MessagePostProcessor để giả lập QoS per-send** bằng `message.setJMSPriority(8)` hoặc `message.setJMSExpiration(...)` rồi mong broker tôn trọng. `JMSPriority`, `JMSDeliveryMode`, `JMSExpiration` là những header chịu ảnh hưởng từ cách gọi `MessageProducer.send(...)`/quy tắc provider; việc đặt chúng trước send có thể bị cập nhật/ghi đè. Muốn chính sách per-send chắc chắn, truyền `deliveryMode, priority, timeToLive` vào overload `producer.send(...)` phù hợp hoặc dùng template chuyên biệt.

### Khi nào MessagePostProcessor không đủ?

- Muốn **đổi QoS gửi** theo một request, cần thao tác ở mức `MessageProducer` hoặc một template khác.
- Muốn đổi **toàn bộ converter mặc định** của ứng dụng, nên cấu hình bean. Với payload hiếm gặp, có thể dùng `MessageCreator` tạo message rõ kiểu mà không sửa converter.
- Muốn đổi **broker/credentials/TLS** cho một message, không thực hiện bằng cách sửa `ConnectionFactory` trong template đang được nhiều service dùng.

## 7. Dùng MessageCreator khi cần kiểm soát cấu trúc message

`send(destinationName, MessageCreator)` cho callback một `jakarta.jms.Session` để tạo message tùy trường hợp. Nó không tự chạy `MessageConverter` từ object của ứng dụng.

~~~java
jmsTemplate.send("billing.invoice.commands", session -> {
    jakarta.jms.TextMessage message =
            session.createTextMessage("ISSUE:inv-17");
    message.setJMSCorrelationID("request-17");
    message.setStringProperty("schema", "invoice-issue-v1");
    return message;
});
~~~

Đoạn trên là **mảnh code** chạy bên trong một phương thức có biến `jmsTemplate` được inject sẵn; không phải file Java đầy đủ. `TextMessage` vẫn đi qua cách gửi, transaction, destination resolution và QoS mặc định của template. Dùng nó khi cần tạo `BytesMessage`, `MapMessage`, `TextMessage` hoặc header phức tạp mà converter chung chưa hỗ trợ.

So sánh:
- `convertAndSend("queue", object)`: dùng converter được cấu hình.
- `convertAndSend("queue", object, postProcessor)`: convert rồi bổ sung property/header cho **message cụ thể**.
- `send("queue", session -> ...)`: tự tạo message qua JMS Session.
- `execute("queue", (session, producer) -> ...)`: thao tác chi tiết với producer để chọn QoS cho một send hoặc nhiều sends trong callback.

Không dùng callback để giữ `Session`/`MessageProducer` rồi gọi sau khi callback kết thúc. Spring quản lý vòng đời của tài nguyên callback; giữ lại tham chiếu có thể gây lỗi, rò rỉ hoặc sử dụng session sai thread.

## 8. QoS: cấu hình chung không đồng nhất với tùy chỉnh từng gửi

Trong JMS, `MessageProducer` có hai nhóm send thường gặp:

~~~java
producer.send(message);                          // default QoS
producer.send(message, deliveryMode, priority, timeToLive);
~~~

`deliveryMode` là `DeliveryMode.PERSISTENT` hoặc `NON_PERSISTENT`; `priority` là số nguyên từ 0 đến 9; `timeToLive` tính bằng mili giây, 0 biểu thị không hết hạn do TTL (nhưng broker vẫn có thể áp dụng chính sách riêng).

Ở `JmsTemplate`, các setter:

~~~java
template.setExplicitQosEnabled(true);
template.setDeliveryMode(DeliveryMode.PERSISTENT);
template.setPriority(4);
template.setTimeToLive(60_000L);
~~~

đặt **chính sách cho những lời gửi thông thường của template**. Nếu `explicitQosEnabled=false`, việc chỉ gọi `setPriority(8)` không bảo đảm producer sẽ dùng mức ưu tiên 8. JMS provider có thể cấu hình default riêng.

Một yêu cầu cấp thiết lại muốn dùng `NON_PERSISTENT, priority=8, TTL=10 giây` **cho riêng một send**. Đừng sửa `template.setPriority(...)` trong method nghiệp vụ, vì setter thay đổi trạng thái của singleton chung.

### Cách 1 — ProducerCallback với QoS riêng (không sửa template)

~~~java
jmsTemplate.execute("billing.invoice.commands", (session, producer) -> {
    jakarta.jms.TextMessage urgent =
            session.createTextMessage("ISSUE:inv-urgent");
    urgent.setStringProperty("eventType", "INVOICE_ISSUE");
    urgent.setJMSCorrelationID("request-urgent-1");

    producer.send(
            urgent,
            jakarta.jms.DeliveryMode.NON_PERSISTENT,
            8,       // priority của lời gửi này
            10_000L  // TTL 10 giây cho lời gửi này
    );
    return null;
});
~~~

Đây là mảnh mã trong một service có biến `jmsTemplate`. Overload `execute(String, ProducerCallback<T>)` cung cấp `Session` và `MessageProducer` đã gắn với destination cần gửi. Câu lệnh `producer.send(...)` trực tiếp sử dụng bộ QoS truyền **ngay trong lời gọi**, trong khi các lần `convertAndSend(...)` khác tiếp tục theo QoS mặc định của template. Checked `JMSException` trong callback được Spring quản lý/chuyển đổi tại biên template.

**Lưu ý về phạm vi:** với `ProducerCallback`, phần send tùy chỉnh của bạn chịu trách nhiệm chọn overload và thông số producer. Spring quản lý connection/session/producer theo callback, nhưng business code vẫn phải xử lý idempotency, retry và transaction đúng. Đừng giả định có exactly-once chỉ vì send trả về bình thường.

### Cách 2 — Tạo hai template cấu hình sẵn cho hai chính sách ổn định

Nếu hệ thống thường xuyên có hai nhóm QoS (chẳng hạn lệnh thanh toán và telemetry), hai bean đặt tên có thể rõ ràng hơn callback lặp lại:

~~~java
@Configuration
class MessagingTemplates {
    @Bean("standardJmsTemplate")
    JmsTemplate standard(ConnectionFactory factory) {
        JmsTemplate t = new JmsTemplate(factory);
        t.setDefaultDestinationName("billing.invoice.commands");
        t.setExplicitQosEnabled(true);
        t.setDeliveryMode(DeliveryMode.PERSISTENT);
        t.setPriority(4);
        t.setTimeToLive(60_000L);
        return t;
    }

    @Bean("expiringJmsTemplate")
    JmsTemplate expiring(ConnectionFactory factory) {
        JmsTemplate t = new JmsTemplate(factory);
        t.setDefaultDestinationName("billing.invoice.commands");
        t.setExplicitQosEnabled(true);
        t.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
        t.setPriority(8);
        t.setTimeToLive(10_000L);
        return t;
    }
}
~~~

Trong Spring config thực tế, thêm import `jakarta.jms.ConnectionFactory`, `jakarta.jms.DeliveryMode`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration` và `org.springframework.jms.core.JmsTemplate`. Đoạn trên là **mảnh lớp minh họa cấu hình**; nếu đưa vào dự án cùng ví dụ mục 4, tránh tạo nhiều bean trùng tên hoặc injection mơ hồ. Service nên inject bean bằng `@Qualifier("standardJmsTemplate")` hoặc `@Qualifier("expiringJmsTemplate")`.

Template được chia sẻ theo **chính sách** chứ không theo request. Hai template có thể dùng cùng `ConnectionFactory` nhưng khác QoS, converter hoặc destination mặc định. Khi số chính sách nhỏ và ổn định, đây là cách dễ kiểm thử và ít sai hơn sửa setter theo request.

### Cách 3 — Policy được suy ra từ nghiệp vụ

Nếu QoS phụ thuộc cấp ưu tiên của từng sự kiện, service nên xác định policy bằng một enum hoặc value object rồi truyền bộ QoS vào producer callback. Đừng cho caller gửi tùy ý mọi số priority/TTL từ request HTTP nếu chưa có validation: `priority` phải nằm trong 0..9, TTL không âm, hạn chế bản tin tồn quá lâu và ưu tiên cao gây starvation.

## 9. Ví dụ chạy đầy đủ: một template, hai kiểu gửi

Ví dụ **Java 17 + Spring Boot 3.3.5 + Artemis embedded** minh họa hai lần gửi vào cùng Queue:
1. Message thường dùng QoS chung của template: `priority=4, TTL=60_000 ms`.
2. Message khẩn cấp dùng `ProducerCallback` và QoS per-send: `priority=8, TTL=10_000 ms`.

Mỗi message có property `kind` riêng. Khi nhận, dùng selector để lựa chọn từng bản **không phụ thuộc thứ tự broker phân phối**; xác minh priority/correlation ID thực tế. Broker embedded dùng `persistent: false` để phục vụ lab, vì vậy ví dụ không dùng để chứng minh độ bền sau restart.

### Cấu trúc dự án

~~~text
jms-template-policy/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/application.yml
    └── java/example/jms/SharedPerCallDemo.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'jms-template-policy'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

Spring Boot BOM quản lý các phiên bản Spring/Artemis đã được thử cùng nhau. Với dự án đang chạy phiên bản Boot khác, ưu tiên dependency management tương ứng của **chính phiên bản dự án**, không tự ghép các JAR Jakarta/Artemis ngẫu nhiên.

### src/main/resources/application.yml

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.orders
      persistent: false
~~~

### src/main/java/example/jms/SharedPerCallDemo.java

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SharedPerCallDemo {

    public static void main(String[] args) {
        SpringApplication.run(SharedPerCallDemo.class, args);
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setDefaultDestinationName("demo.orders");
        template.setPubSubDomain(false); // Queue
        template.setReceiveTimeout(3_000L);

        // Chính sách chung cho convertAndSend / send thường.
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
        template.setPriority(4);
        template.setTimeToLive(60_000L);
        return template;
    }

    @Bean
    ApplicationRunner demonstrate(JmsTemplate template) {
        return args -> {
            // Lần 1: vẫn dùng QoS chung, chỉ thêm property/header.
            template.convertAndSend("regular", message -> {
                message.setStringProperty("kind", "STANDARD");
                message.setJMSCorrelationID("cid-normal");
                return message;
            });

            // Lần 2: bộ QoS được truyền riêng cho lần send này.
            // Không đổi bất kỳ setter nào trên JmsTemplate singleton.
            template.execute("demo.orders", (session, producer) -> {
                TextMessage msg = session.createTextMessage("urgent");
                msg.setStringProperty("kind", "URGENT");
                msg.setJMSCorrelationID("cid-urgent");

                producer.send(
                        msg, DeliveryMode.NON_PERSISTENT, 8, 10_000L);
                return null;
            });

            // Selector tránh phụ thuộc thứ tự phân phối do priority.
            Message standardMessage = template.receiveSelected(
                    "demo.orders", "kind = 'STANDARD'");
            Message urgentMessage = template.receiveSelected(
                    "demo.orders", "kind = 'URGENT'");

            if (!(standardMessage instanceof TextMessage standard)) {
                throw new IllegalStateException(
                        "STANDARD message not received");
            }
            if (!(urgentMessage instanceof TextMessage urgent)) {
                throw new IllegalStateException(
                        "URGENT message not received");
            }

            System.out.println("STANDARD|" + standard.getText()
                    + "|priority=" + standard.getJMSPriority()
                    + "|cid=" + standard.getJMSCorrelationID());
            System.out.println("URGENT|" + urgent.getText()
                    + "|priority=" + urgent.getJMSPriority()
                    + "|cid=" + urgent.getJMSCorrelationID());
        };
    }
}
~~~

`ApplicationRunner.run` cho phép `throws Exception`, vì vậy việc gọi các phương thức đọc header/payload JMS có checked `JMSException` ở đây vẫn biên dịch được. Trong service thông thường, Spring template xử lý checked JMSException trong callback và ném ra `JmsException` unchecked khi cần.

### Chạy và quan sát

Tại thư mục `jms-template-policy`, dùng JDK 17+ và Gradle tương thích. Nếu dự án có Gradle Wrapper thì chạy `./gradlew bootRun`; nếu chưa có, dùng:

~~~bash
gradle bootRun
~~~

Trong PowerShell, Wrapper (nếu có) là:

~~~powershell
.\gradlew.bat bootRun
~~~

Sau log startup của Spring/Artemis, hai dòng **do mã ứng dụng tự in** dự kiến là:

~~~text
STANDARD|regular|priority=4|cid=cid-normal
URGENT|urgent|priority=8|cid=cid-urgent
~~~

Thứ tự các dòng trên **được chương trình ấn định** khi nó nhận theo selector, không phải lời bảo đảm rằng broker luôn giao STANDARD trước URGENT. Các trường như `JMSMessageID`, `JMSTimestamp`, `JMSExpiration` được provider thiết lập/diễn giải, nên không in các giá trị phụ thuộc thời gian/implementation vào output cố định.

Nếu message không đến trước 3 giây, phép kiểm tra sẽ thất bại với thông điệp rõ ràng. Lab này giúp xác nhận cả hai đường gửi sử dụng cùng `ConnectionFactory`/Queue, trong khi QoS per-send hoạt động độc lập với trạng thái mặc định. Mức priority thực tế là một **gợi ý về ưu tiên phân phối** theo JMS/provider, không phải bảo đảm business task khẩn luôn hoàn tất trước task thường.

### Kiểm tra thêm mà không sửa template

Trong test tích hợp, có thể xác nhận trước và sau hai lời gọi:
- `template.getDefaultDestinationName()` vẫn bằng `demo.orders`.
- `template.getPriority()` vẫn là `4`.
- `template.getTimeToLive()` vẫn là `60_000L`.
- `template.isExplicitQosEnabled()` vẫn là `true`.

Những getter này phản ánh cấu hình bean; header priority ở message nhận được xác nhận hiệu lực của từng lời gửi. Đừng chỉ kiểm tra getter rồi suy ra broker đã nhận đúng thông điệp; cần round-trip thực.

## 10. Nhận đồng bộ: chọn destination/selector theo lời gọi, timeout theo template

`JmsTemplate` có các overload như:
- `receive()`: nhận từ default destination.
- `receive("billing.invoice.commands")`: nhận từ destination chỉ định cho lần gọi.
- `receiveSelected("billing.invoice.commands", "kind = 'STANDARD'")`: chỉ nhận message có JMS property/header khớp selector.
- `receiveAndConvert("billing.invoice.commands")`: nhận rồi chuyển JMS Message về object ứng dụng bằng converter.

**Selector không đọc field JSON trong body.** Nó áp dụng cho JMS headers/properties theo cú pháp JMS selector; nếu cần lọc `kind`, publisher phải ghi property đó lên JMS Message.

`setReceiveTimeout(3_000L)` là cấu hình trên đối tượng template, không phải tham số `receiveSelected(...)`. Cách sai:

~~~java
template.setReceiveTimeout(100L);
Message m = template.receive("billing.invoice.commands");
template.setReceiveTimeout(3_000L);
~~~

Nếu nhiều thread dùng chung template, lời gọi thứ hai của thread khác có thể vô tình dùng timeout 100 ms. Các phép cập nhật setter liên tục còn khiến việc kiểm thử không ổn định.

Cách đúng khi có hai chính sách ổn định: khai báo hai template với timeout khác nhau, hoặc tổ chức một adapter/consumer chuyên biệt dùng `SessionCallback` với JMS `MessageConsumer.receive(timeout)` và quản lý consumer/resource cẩn thận. Chọn cách đơn giản nhất đáp ứng nhu cầu.

**Nhận bằng template không phải listener lâu dài.** Trong ứng dụng có xử lý bất đồng bộ liên tục, thường dùng `@JmsListener`; nhận đồng bộ phù hợp một số workflow request/reply, tool kiểm thử hoặc trường hợp tiêu thụ theo nhịp do ứng dụng quyết định.

## 11. Listener container có cấu hình riêng với JmsTemplate

Một nhầm lẫn phổ biến: “Đã gọi `jmsTemplate.setSessionTransacted(true)`, mọi `@JmsListener` sẽ rollback cùng kiểu.” Điều này sai vì listener container dùng **factory riêng**.

~~~java
@Configuration
@EnableJms
class ListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);        // Queue
        factory.setSessionTransacted(true);    // Cho JMS listener session
        factory.setConcurrency("1-3");        // Tài nguyên listener
        return factory;
    }
}
~~~

Các import cần trong một lớp Spring đầy đủ là `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration`, `org.springframework.jms.annotation.EnableJms` và `org.springframework.jms.config.DefaultJmsListenerContainerFactory`. Ví dụ trên là mảnh cấu hình minh họa, không phải chương trình standalone.

Trong listener:

~~~java
@JmsListener(destination = "billing.invoice.commands")
public void handle(String payload) {
    processInvoice(payload);
}
~~~

`processInvoice` ở đây là phương thức nghiệp vụ do ứng dụng cung cấp. `@JmsListener` chỉ chịu ảnh hưởng của template khi code trong listener **chủ động inject/call template để gửi hoặc nhận tiếp**; hoạt động tiêu thụ message của listener do container factory/transaction manager riêng quản lý.

Đừng áp dụng một `receiveTimeout` rất nhỏ của template rồi mong listener container tự thay đổi polling timeout hoặc scheduling. Các thiết lập container và template có phạm vi khác nhau.

## 12. Transaction và việc chia sẻ ConnectionFactory

Cấu hình “dùng chung” không đồng nghĩa transaction sẽ tự động gộp mọi thao tác với database hoặc nhiều broker.

- `JmsTemplate` có thể tham gia transaction JMS do Spring quản lý nếu được cấu hình với transaction manager/resource phù hợp. `setSessionTransacted(true)` quyết định local session transaction khi không có transaction manager cấp cao tương ứng; xem trạng thái transaction đang hoạt động.
- `@Transactional` chỉ có tác dụng đối với transaction manager được áp dụng cho lời gọi. Một DB transaction và một JMS transaction thường là **hai tài nguyên**; commit của một tài nguyên không tự động bảo đảm commit nguyên tử ở tài nguyên kia.
- Nếu nghiệp vụ cần atomicity DB + publish, xem transactional outbox hoặc giải pháp transaction phù hợp; đừng coi việc cùng inject một `ConnectionFactory` là bảo đảm XA.
- Khi listener xử lý lỗi rồi **nuốt exception**, container có thể ACK/commit message như đã thành công. Chính sách rollback/redelivery/DLQ cần được cấu hình và kiểm thử thực tế.
- Khi producer timeout, kết quả gửi có thể không xác định: broker đã nhận message nhưng response thất lạc. Thiết kế event ID/idempotent consumer để chống duplicate, bất kể dùng template chung hay callback riêng.

**Một template có thể dùng lại từ nhiều thread** nhưng không tự biến các lời gửi thành cùng một transaction. Transaction gắn với tài nguyên và phạm vi thread/transaction manager, không phải “lịch sử” lưu trong singleton template.

## 13. Thiết kế cấu hình theo độ ổn định của yêu cầu

| Tình huống | Giải pháp phù hợp | Vì sao |
|---|---|---|
| Tất cả command cùng broker, converter, QoS | Một singleton `JmsTemplate` | Đơn giản, tái sử dụng cấu hình ổn định. |
| Mỗi message có correlation ID/tenant tag khác nhau | `convertAndSend(..., MessagePostProcessor)` | Header/property gắn đúng message, không ảnh hưởng lời gọi khác. |
| Một lần gửi cần destination khác | Overload `convertAndSend(destinationName, ...)` | Không đổi default destination của bean. |
| Payload đặc biệt không qua converter chung | `send(..., MessageCreator)` | Tạo đúng JMS message cho lời gọi. |
| Một lần gửi cần priority/TTL khác | `execute(..., ProducerCallback)` với `producer.send(msg, mode, priority, ttl)` | QoS được truyền trực tiếp vào send cụ thể. |
| Hai loại thông điệp có QoS ổn định khác nhau | Hai bean template và `@Qualifier` | Chính sách rõ ràng, không chỉnh trạng thái runtime. |
| Hai broker khác nhau | Hai `ConnectionFactory` + template được đặt tên | Tách connection/auth/transaction và định tuyến. |
| Mỗi consumer listener cần concurrency/ack khác | Nhiều `JmsListenerContainerFactory` hoặc config theo endpoint | Listener không dùng chính sách receive của template để vận hành. |
| Một luồng cần timeout nhận ngắn hơn | Template riêng hoặc callback nhận thích hợp | Tránh đổi `setReceiveTimeout` khi ứng dụng đang chạy. |

Nếu một method chứa nhiều đoạn đổi setter rồi gửi, đó là tín hiệu cần refactor. Việc truyền cấu hình “theo request” vào callback giúp behavior đọc được ngay tại call site và tránh phụ thuộc thứ tự các thread.

## 14. Sai lầm thường gặp và hệ quả

### Sai lầm 1 — Mutate shared JmsTemplate trước mỗi lần gửi

~~~java
// Không dùng: có race khi nhiều luồng cùng dùng bean.
jmsTemplate.setPriority(9);
jmsTemplate.convertAndSend("urgent");
jmsTemplate.setPriority(4);
~~~

Với `explicitQosEnabled=false`, đoạn này còn không chắc có hiệu lực. Với `true`, các thread khác có thể gửi nhầm priority 9. Ngay cả `try/finally` đặt lại priority vẫn không làm thao tác trở thành thread-safe.

**Sửa:** `ProducerCallback` có QoS riêng hoặc bean template chính sách riêng.

### Sai lầm 2 — Đặt JMSPriority trong MessagePostProcessor và coi là QoS thực

~~~java
// Không nên dùng như cách bắt buộc priority khi producer.send.
jmsTemplate.convertAndSend("urgent", message -> {
    message.setJMSPriority(9);
    return message;
});
~~~

Provider/template có thể gán lại header JMSPriority theo QoS của producer.send. **Sửa:** chọn overload `producer.send` với priority cụ thể.

### Sai lầm 3 — Nhầm message converter và message post processor

`MessageConverter` định nghĩa cách chuyển **kiểu dữ liệu**: ví dụ String → TextMessage, object domain → JSON TextMessage. `MessagePostProcessor` chỉnh một **message đã được converter tạo** (header/property, correlation ID, metadata). Không viết một converter mới chỉ để thêm một property thay đổi trên từng request.

### Sai lầm 4 — Tin rằng @JmsListener chịu cấu hình của JmsTemplate

Một listener vẫn có thể chạy concurrency 1 và auto-ack dù publisher template đã dùng `setSessionTransacted(true)`. **Sửa:** đọc cấu hình `DefaultJmsListenerContainerFactory`, transaction manager và policy broker.

### Sai lầm 5 — Mở rộng scope callback ra ngoài phạm vi chạy

`Session` và `MessageProducer` không được giữ trong field rồi tái sử dụng sau khi `execute(...)` return. Các object JMS cấp thấp có vòng đời do container/provider quản lý. Dùng callback trọn vẹn trong một lời gọi.

### Sai lầm 6 — Cho mọi service tự sửa receive timeout/default destination

Thay setter trực tiếp trên injected singleton gây side effect liên service. **Sửa:** truyền destination/selector per-call, template khác cho timeout khác, hoặc chuyên biệt hóa adapter.

### Sai lầm 7 — Coi TTL, priority, persistent là cam kết xử lý nghiệp vụ

TTL liên quan tính hợp lệ của message; priority là gợi ý phân phối; persistent delivery còn phụ thuộc broker và chính sách lưu trữ. Không có thiết lập nào tự bảo đảm exactly-once trong database hoặc thứ tự hoàn tất của business handler.

## 15. Checklist kiểm thử khi đưa vào dự án thật

1. **Bean wiring:** xác nhận chỉ một bean mặc định khi service inject `JmsTemplate` không có qualifier; nếu nhiều bean, dùng `@Qualifier` hoặc cấu hình primary rõ ràng.
2. **Concurrency:** gọi hai luồng gửi các payload có correlation ID khác nhau; xác nhận không rò property sang message khác và không có setter runtime ở service.
3. **Destination:** gửi với đích mặc định và đích chỉ định; kiểm tra Queue/Topic/routing type và ACL trên broker.
4. **QoS:** so sánh `JMSPriority`, `JMSDeliveryMode`, `JMSExpiration` ở message nhận được, cùng policy TTL phía broker; đừng chỉ kiểm getter template.
5. **Callback exceptions:** giả lập `JMSException` trong provider, xác minh Spring đưa ra `JmsException` và tài nguyên được giải phóng.
6. **Receive:** test timeout, selector khớp và không khớp, xử lý `null` khi hết thời gian chờ.
7. **Transactions:** thử rollback consumer, redelivery, DLQ và gửi lại sau timeout; đảm bảo nghiệp vụ idempotent.
8. **Môi trường:** test đúng version JDK/Spring/broker, xác thực TLS/credentials, cấu hình ở dev/staging/prod; không lấy kết quả embedded làm bằng chứng về production.
9. **Observability:** log correlation ID, logical destination, delivery attempt và cause; tránh log thông tin nhạy cảm trong payload.

Khi review code, hãy hỏi: **“Thao tác này đang thay đổi trạng thái của bean hay chỉ cấu hình message được gửi?”** Nếu đang gọi setter trên singleton bên trong handler/request, thường cần chuyển logic sang tham số, callback hoặc bean riêng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Hai service cùng inject `JmsTemplate`. Service A muốn gửi vào `billing.invoice.cancel` thay vì Queue mặc định. Có cần gọi `setDefaultDestinationName` không?

**Đáp án:** Không. Dùng `convertAndSend("billing.invoice.cancel", payload)`; template vẫn giữ tên mặc định cho các lời gọi khác.

**Câu 2.** Một sự kiện phải có `JMSCorrelationID` theo request và property `eventType`. Nên chọn gì?

**Đáp án:** `convertAndSend(destination, payload, message -> { ...; return message; })` với `MessagePostProcessor`. Cần kiểm tra/giới hạn độ dài và định dạng property nếu lấy từ nguồn bên ngoài.

**Câu 3.** Một message cần TTL 5 giây, các message còn lại dùng TTL 60 giây. Tại sao `setTimeToLive(5_000L)` rồi trả về `60_000L` có thể sai?

**Đáp án:** Setter sửa trạng thái template dùng chung. Thread khác có thể gửi khi TTL đang là 5 giây, làm message của nó hết hạn sớm. Dùng `ProducerCallback` với TTL tham số trong `send` hoặc template được cấu hình chính sách riêng.

**Câu 4.** Đã gọi `setPriority(9)` nhưng message nhận vẫn priority mặc định. Cần kiểm tra gì?

**Đáp án:** `setExplicitQosEnabled(true)` và đường send thực tế, cùng provider/broker policy. Nếu per-send, kiểm tra chính xác `producer.send(msg, mode, priority, ttl)` thay vì chỉ setter.

**Câu 5.** `@JmsListener` không rollback khi handler thất bại mặc dù publisher dùng `JmsTemplate.setSessionTransacted(true)`. Vì sao?

**Đáp án:** Publisher template và listener container có cấu hình riêng; phải xác minh `JmsListenerContainerFactory`, transaction manager, handler exception và chính sách redelivery.

**Câu 6.** Khi hai consumer cùng dùng shared template, các message có `JMSCorrelationID` khác nhau nhưng một hàng đợi nhận ưu tiên đảo thứ tự. Đó có phải bằng chứng race trên template không?

**Đáp án:** Không. Priority và provider policy có thể ảnh hưởng thứ tự giao. Kiểm tra nội dung và header từng message, không dựa vào thứ tự log giữa nhiều producer/consumer.

## 17. Tài liệu chính thức

- [Spring Framework 6.2 — Using JMS: JmsTemplate, cấu hình QOS và thread safety](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html).
- [Spring Framework 6.2 — Sending a Message: MessageCreator và MessagePostProcessor](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html).
- [Spring Framework 6.2.14 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html).
- [Spring Framework 6.2 — ProducerCallback Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/ProducerCallback.html).
- [Spring Framework — Annotation-driven JMS listener containers](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html).
- [Spring Boot 3.3 — JMS and Artemis configuration](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html).
- [Jakarta Messaging 3.1 — JMS MessageProducer send and Quality of Service](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1).
