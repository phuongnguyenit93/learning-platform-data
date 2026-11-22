# JMS header, thuộc tính ứng dụng và nội dung thông điệp

## 1. Ba phần của một JMS Message

Một JMS Message gồm ba nhóm thông tin có vai trò khác nhau:

1. **Header chuẩn JMS** mô tả cách message được gửi, định danh, tương quan hoặc phản hồi.
2. **Application properties** là các thuộc tính do ứng dụng định nghĩa để mang metadata, lọc message hoặc điều khiển xử lý.
3. **Body** chứa nội dung nghiệp vụ cần truyền giữa producer và consumer.

Ví dụ một sự kiện đơn hàng có thể có:

| Phần | Ví dụ | Mục đích |
|---|---|---|
| Header chuẩn | JMSCorrelationID = order-1001 | Ghép message với request hoặc luồng nghiệp vụ |
| Application property | eventType = order.created | Xác định loại sự kiện |
| Application property | schemaVersion = 2 | Chọn phiên bản schema |
| Body | JSON của đơn hàng | Dữ liệu nghiệp vụ thực tế |

Phân tách ba phần giúp consumer biết cách xử lý message mà không cần phân tích body chỉ để tìm metadata định tuyến hoặc tương quan. Đồng thời, body có thể thay đổi schema mà không buộc mọi quy tắc điều phối phải thay đổi theo.

JMS là API nhắn tin Java. Trong Spring Framework 6 và Spring Boot 3, JMS API sử dụng package jakarta.jms; các dự án cũ dùng javax.jms cần được chuyển đổi khi nâng cấp lên hệ Jakarta.

## 2. Header chuẩn JMS

JMS định nghĩa một tập header có tên và ý nghĩa thống nhất. Các header này được truy cập qua phương thức trên jakarta.jms.Message, không phải application properties tùy ý.

| Header | Ý nghĩa | Ai thường thiết lập |
|---|---|---|
| JMSDestination | Destination mà message được gửi đến | Provider khi gửi |
| JMSDeliveryMode | Persistent hoặc non-persistent | Producer hoặc cấu hình gửi |
| JMSExpiration | Thời điểm message hết hạn | Provider dựa trên time-to-live |
| JMSPriority | Mức ưu tiên từ 0 đến 9 | Producer hoặc cấu hình gửi |
| JMSMessageID | Định danh do provider cấp | Provider |
| JMSTimestamp | Thời điểm provider chấp nhận gửi | Provider, nếu bật timestamp |
| JMSCorrelationID | Định danh liên kết request/reply hoặc message liên quan | Ứng dụng |
| JMSReplyTo | Destination để gửi phản hồi | Ứng dụng |
| JMSType | Tên kiểu message theo quy ước ứng dụng | Ứng dụng |
| JMSRedelivered | Cho biết provider đang giao lại message | Provider |

Một số header được provider quản lý. Ví dụ JMSMessageID và JMSTimestamp thường được gán khi gửi; JMSDestination mô tả đích thực tế; JMSExpiration được tính từ time-to-live. Ứng dụng không nên tự giả định có thể gán tùy ý các giá trị do provider quản lý.

Các header thường được ứng dụng đặt gồm:

~~~java
message.setJMSCorrelationID("order-1001");
message.setJMSReplyTo(replyQueue);
message.setJMSType("OrderCreated");
~~~

JMSDeliveryMode, JMSPriority và JMSExpiration thường được điều khiển qua tham số gửi hoặc cấu hình JmsTemplate, thay vì sửa trực tiếp trên Message. Trong Spring, có thể cấu hình Quality of Service (QoS) trên JmsTemplate:

~~~java
jmsTemplate.setExplicitQosEnabled(true);
jmsTemplate.setDeliveryMode(DeliveryMode.PERSISTENT);
jmsTemplate.setPriority(5);
jmsTemplate.setTimeToLive(60_000);
~~~

Khi bật explicit QoS, các giá trị delivery mode, priority và time-to-live được áp dụng cho thao tác gửi. Provider sẽ hiển thị kết quả tương ứng trong header của message nhận được.

### 2.1. Persistent và non-persistent

Persistent message yêu cầu provider lưu message theo cơ chế bảo đảm của broker trước khi xác nhận việc gửi theo chính sách của provider. Non-persistent message có thể được lưu tạm và thường có mức bảo đảm thấp hơn khi broker gặp sự cố.

Persistent không có nghĩa message chắc chắn được consumer xử lý đúng một lần. Message vẫn có thể được giao lại sau khi consumer lỗi, và ứng dụng vẫn phải xử lý duplicate nếu nghiệp vụ yêu cầu. Delivery mode cũng không thay thế transaction, acknowledgement hoặc idempotency.

### 2.2. Priority và expiration

JMS priority có giá trị từ 0 đến 9; giá trị cao hơn biểu thị mức ưu tiên cao hơn. Tuy nhiên, mức độ broker thực thi ưu tiên và thứ tự giao thực tế phụ thuộc provider, cấu hình queue và tải hệ thống. Không thiết kế SLA chỉ dựa vào việc gán priority.

Time-to-live (TTL) xác định khoảng thời gian message còn hiệu lực. Provider dùng TTL để tính JMSExpiration. Message hết hạn có thể bị loại bỏ mà không được giao cho consumer. Không dùng TTL như một cơ chế retry; retry cần lịch thử lại và chính sách xử lý lỗi riêng.

## 3. Application properties

Application properties là metadata do producer hoặc middleware định nghĩa. Chúng được lưu trong vùng property của JMS Message và có thể được consumer đọc qua các API get/set property.

Ví dụ:

~~~java
message.setStringProperty("eventType", "order.created");
message.setIntProperty("schemaVersion", 2);
message.setLongProperty("createdAtEpochMs", 1_800_000_000_000L);
message.setBooleanProperty("replay", false);
~~~

Tên property JMS phải tuân theo quy tắc tên định danh Java, phân biệt chữ hoa chữ thường. Vì vậy eventType hoặc schemaVersion là tên phù hợp; tên chứa dấu gạch ngang như event-type không hợp lệ theo quy tắc JMS property name.

Không dùng tiền tố JMSX hoặc JMS_ cho property tùy biến thông thường vì các tiền tố này được dành cho thuộc tính mở rộng hoặc thuộc tính do provider định nghĩa. Ví dụ JMSXDeliveryCount là một property mở rộng chuẩn mà provider cung cấp trong các phiên bản JMS hiện đại.

### 3.1. Các kiểu dữ liệu được hỗ trợ

JMS application property hỗ trợ các kiểu dữ liệu đơn giản như:

- boolean
- byte
- short
- int
- long
- float
- double
- String

Các phương thức thường dùng gồm setBooleanProperty, setIntProperty, setLongProperty, setStringProperty và các getter tương ứng. setObjectProperty chỉ nhận giá trị thuộc tập kiểu được JMS hỗ trợ; không thể tùy ý đặt một domain object hoặc một đối tượng Java bất kỳ vào property.

Ví dụ đọc property:

~~~java
String eventType = message.getStringProperty("eventType");
int schemaVersion = message.getIntProperty("schemaVersion");
boolean replay = message.getBooleanProperty("replay");
~~~

Nếu property không tồn tại, các getter primitive có thể trả giá trị mặc định như false hoặc 0. Hãy dùng propertyExists(name) khi cần phân biệt property bị thiếu với property có giá trị false hoặc 0:

~~~java
if (message.propertyExists("schemaVersion")) {
    int version = message.getIntProperty("schemaVersion");
}
~~~

Property name có phân biệt hoa thường. eventType và EventType là hai tên khác nhau. Hãy thống nhất quy ước đặt tên trong toàn bộ hệ thống.

### 3.2. Property và JMS selector

JMS selector cho phép broker lọc message dựa trên header chuẩn và application properties. Selector dùng cú pháp gần với biểu thức SQL92 và không đọc nội dung body.

Ví dụ:

~~~sql
eventType = 'order.created' AND schemaVersion >= 2
~~~

Một consumer có thể đăng ký nhận message thỏa điều kiện đó. Trong Spring JMS, có thể truyền selector khi tạo listener container hoặc dùng API nhận message có selector phù hợp.

Không nhét dữ liệu nghiệp vụ lớn vào property để có thể lọc. Property nên ngắn, có kiểu rõ ràng và phục vụ định tuyến, phân loại, tương quan hoặc lọc. Body vẫn là nơi chứa dữ liệu nghiệp vụ.

## 4. Nội dung body của JMS Message

JMS định nghĩa một số loại message theo kiểu body:

| Loại message | Body | Trường hợp sử dụng |
|---|---|---|
| Message | Không có body | Chỉ mang header và property hoặc tín hiệu điều khiển |
| TextMessage | Chuỗi văn bản | JSON, XML, văn bản hoặc payload có cấu trúc |
| BytesMessage | Chuỗi byte | Nội dung nhị phân, file, payload đã mã hóa |
| MapMessage | Tập cặp tên/giá trị đơn giản | Dữ liệu dạng map với các kiểu JMS hỗ trợ |
| StreamMessage | Chuỗi giá trị có thứ tự | Giao tiếp theo cấu trúc tuần tự đã biết |
| ObjectMessage | Một đối tượng Serializable | Tương thích hệ thống Java cũ; cần kiểm soát chặt |

Các loại body không thể hoán đổi tùy ý. Consumer phải đọc đúng kiểu message đã được producer gửi.

### 4.1. TextMessage

TextMessage phù hợp với JSON, XML hoặc nội dung văn bản. Ví dụ:

~~~java
TextMessage message = session.createTextMessage(
    "{\"orderId\":\"ORD-1001\",\"total\":125000}"
);
message.setStringProperty("eventType", "order.created");
~~~

Consumer đọc body bằng getText():

~~~java
String json = ((TextMessage) message).getText();
~~~

TextMessage không tự xác thực JSON. Nếu payload phải là JSON, ứng dụng vẫn cần JSON parser hoặc message converter để kiểm tra cấu trúc và kiểu dữ liệu.

### 4.2. BytesMessage

BytesMessage dùng cho dữ liệu nhị phân. Producer ghi byte vào body:

~~~java
BytesMessage message = session.createBytesMessage();
message.writeBytes(fileBytes);
message.setStringProperty("contentKind", "invoice-pdf");
~~~

Consumer đọc byte theo giao thức đã thỏa thuận. Với payload lớn, cần cân nhắc giới hạn kích thước message, bộ nhớ, streaming và chính sách lưu trữ broker.

### 4.3. MapMessage và StreamMessage

MapMessage cho phép truy cập body theo tên trường:

~~~java
MapMessage message = session.createMapMessage();
message.setString("orderId", "ORD-1001");
message.setLong("total", 125000L);
~~~

StreamMessage lưu các giá trị theo thứ tự ghi. Consumer phải đọc đúng thứ tự và đúng kiểu mà producer đã thỏa thuận. Thay đổi thứ tự ghi có thể phá vỡ tương thích giữa phiên bản producer và consumer.

### 4.4. ObjectMessage và rủi ro serialization

ObjectMessage mang đối tượng Java Serializable. Cách này có thể tiện cho hệ thống Java đóng, nhưng tạo phụ thuộc vào class, serialVersionUID và Java serialization.

Không nên dùng ObjectMessage cho dữ liệu đến từ nguồn không đáng tin cậy. Deserialization đối tượng Java có thể mở ra rủi ro thực thi hành vi không mong muốn nếu classpath và filter không được kiểm soát. Với hệ thống mới, thường nên ưu tiên JSON hoặc định dạng schema rõ ràng qua TextMessage/BytesMessage.

Nếu phải duy trì ObjectMessage để tương thích hệ thống cũ, hãy giới hạn class được phép deserialize, quản lý phiên bản class và chỉ nhận message từ broker đã được xác thực, phân quyền.

## 5. Phân biệt header, property và body

Một ví dụ thực tế:

- JMSCorrelationID xác định message thuộc luồng xử lý đơn hàng nào.
- eventType cho biết message biểu diễn sự kiện order.created.
- schemaVersion cho biết consumer cần đọc payload theo schema phiên bản 2.
- Body JSON chứa orderId, customerId, total và các trường nghiệp vụ khác.

Có thể hình dung:

~~~text
JMS Message
├── Standard headers
│   ├── JMSMessageID
│   ├── JMSCorrelationID
│   ├── JMSReplyTo
│   ├── JMSDeliveryMode
│   └── JMSRedelivered
├── Application properties
│   ├── eventType = "order.created"
│   ├── schemaVersion = 2
│   └── traceId = "trace-1001"
└── Body
    └── TextMessage: JSON order payload
~~~

Một quy tắc hữu ích:

- Nếu broker/provider cần metadata để giao nhận hoặc quản lý message, hãy xem header chuẩn JMS.
- Nếu ứng dụng cần metadata để phân loại, lọc, tương quan hoặc xử lý, hãy dùng application property.
- Nếu dữ liệu mô tả đối tượng nghiệp vụ, hãy đặt trong body.

Đừng lặp toàn bộ body vào property. Điều đó làm tăng kích thước header, gây khó tương thích và có thể vượt giới hạn property table của broker.

## 6. Spring JMS và MessageConverter

Spring JMS cung cấp JmsTemplate để gửi/nhận message và MessageConverter để chuyển đổi giữa đối tượng Java với jakarta.jms.Message.

SimpleMessageConverter mặc định hỗ trợ các ánh xạ cơ bản:

| Java object | JMS Message |
|---|---|
| String | TextMessage |
| byte[] | BytesMessage |
| Map | MapMessage |
| Serializable | ObjectMessage |

Vì vậy, khi gọi convertAndSend với một String, Spring thường tạo TextMessage. Khi truyền byte[], Spring tạo BytesMessage. Với Map, Spring tạo MapMessage.

Ví dụ:

~~~java
jmsTemplate.convertAndSend("orders.queue", jsonString);
~~~

Nếu cần chuyển một domain object thành JSON, hãy cấu hình một JSON MessageConverter phù hợp. Converter chịu trách nhiệm chuyển đổi body và có thể thêm metadata kiểu dữ liệu để consumer khôi phục đúng kiểu. Không nên dựa vào Java serialization cho một giao thức cần tương thích lâu dài giữa nhiều ngôn ngữ.

Spring JMS MessageConverter khác với Spring AMQP MessageConverter. Dù hai abstraction có tên giống nhau, một bên tạo jakarta.jms.Message, bên còn lại tạo org.springframework.amqp.core.Message.

## 7. Bổ sung header và property sau chuyển đổi trong Spring JMS

Spring JMS có interface org.springframework.jms.core.MessagePostProcessor. Với overload convertAndSend có processor, luồng xử lý là:

1. Đối tượng Java được chuyển đổi thành jakarta.jms.Message bằng MessageConverter.
2. MessagePostProcessor nhận message đã chuyển đổi.
3. Processor bổ sung hoặc điều chỉnh header/property.
4. JmsTemplate gửi message đến destination.

Ví dụ:

~~~java
jmsTemplate.convertAndSend(
    "orders.queue",
    "{\"orderId\":\"ORD-1001\"}",
    message -> {
        message.setStringProperty("eventType", "order.created");
        message.setIntProperty("schemaVersion", 2);
        message.setJMSCorrelationID("order-ORD-1001");
        message.setJMSType("OrderCreated");
        return message;
    }
);
~~~

MessagePostProcessor của Spring JMS làm việc với jakarta.jms.Message. Đây là API khác với MessagePostProcessor của Spring AMQP, dù cùng tên và cùng ý tưởng xử lý message sau conversion.

Nếu cần tạo message hoàn toàn thủ công, có thể dùng JmsTemplate.send với MessageCreator và Session:

~~~java
jmsTemplate.send("orders.queue", session -> {
    TextMessage message = session.createTextMessage(
        "{\"orderId\":\"ORD-1001\"}"
    );
    message.setStringProperty("eventType", "order.created");
    message.setJMSCorrelationID("order-ORD-1001");
    return message;
});
~~~

Dùng MessageCreator khi cần kiểm soát việc tạo TextMessage, BytesMessage hoặc Destination cụ thể. Dùng convertAndSend khi đã có object/payload và muốn converter thực hiện bước chuyển đổi.

## 8. Ví dụ hoàn chỉnh với Spring Boot và ActiveMQ Artemis

Ví dụ dùng Java 17, Spring Boot 3.3.13, Spring JMS và ActiveMQ Artemis. Ứng dụng gửi một chuỗi JSON; SimpleMessageConverter tạo TextMessage; MessagePostProcessor thêm JMSCorrelationID, JMSType và application properties; test nhận raw Message để xác minh cả metadata lẫn body.

### 8.1. Cấu trúc dự án

~~~text
jms-message-demo/
├── compose.yaml
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/jms/
    │       └── JmsMessageDemoApplication.java
    └── test/
        └── java/com/example/jms/
            └── JmsMessageMetadataTest.java
~~~

### 8.2. Khởi chạy Artemis

Tạo compose.yaml:

~~~yaml
services:
  artemis:
    image: apache/activemq-artemis:2.37.0
    container_name: jms-message-demo-artemis
    environment:
      ARTEMIS_USER: demo
      ARTEMIS_PASSWORD: demo123
      ANONYMOUS_LOGIN: "false"
    ports:
      - "127.0.0.1:61616:61616"
      - "127.0.0.1:8161:8161"
~~~

Cổng 61616 là cổng broker mà JMS client sử dụng trong ví dụ; 8161 là giao diện quản trị web. Tài khoản demo chỉ dùng cho local lab, không dùng trên broker dùng chung.

Khởi động broker:

~~~bash
docker compose up -d
~~~

### 8.3. Maven dependencies

Tạo pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jms-message-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Spring Boot quản lý phiên bản Spring JMS, Jakarta Messaging và Artemis client tương thích với nhau.

### 8.4. Cấu hình kết nối

Tạo src/main/resources/application.properties:

~~~properties
spring.application.name=jms-message-demo

spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=demo
spring.artemis.password=demo123

spring.jms.pub-sub-domain=false
~~~

mode=native yêu cầu ứng dụng kết nối đến broker Artemis đang chạy bên ngoài tiến trình. pub-sub-domain=false cấu hình JmsTemplate dùng queue theo mặc định. Nếu dùng topic, cần cấu hình pub-sub-domain hoặc destination/listener tương ứng.

### 8.5. Lớp ứng dụng

Tạo JmsMessageDemoApplication.java:

~~~java
package com.example.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmsMessageDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            JmsMessageDemoApplication.class,
            args
        );
    }
}
~~~

### 8.6. Integration test

Tạo JmsMessageMetadataTest.java:

~~~java
package com.example.jms;

import java.util.UUID;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.MessagePostProcessor;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class JmsMessageMetadataTest {

    @Autowired
    private JmsTemplate jmsTemplate;

    @Test
    void sendsStandardHeadersApplicationPropertiesAndTextBody()
            throws JMSException {

        String destination =
            "demo.jms.metadata." + UUID.randomUUID();

        String payload =
            "{\"orderId\":\"ORD-1001\",\"total\":125000}";

        MessagePostProcessor processor = message -> {
            message.setJMSCorrelationID("order-ORD-1001");
            message.setJMSType("OrderCreated");

            message.setStringProperty(
                "eventType",
                "order.created"
            );
            message.setIntProperty("schemaVersion", 2);
            message.setBooleanProperty("replay", false);

            return message;
        };

        jmsTemplate.convertAndSend(
            destination,
            payload,
            processor
        );

        jmsTemplate.setReceiveTimeout(5_000);
        Message received = jmsTemplate.receive(destination);

        assertThat(received).isNotNull();
        assertThat(received).isInstanceOf(TextMessage.class);

        assertThat(received.getJMSCorrelationID())
            .isEqualTo("order-ORD-1001");
        assertThat(received.getJMSType())
            .isEqualTo("OrderCreated");
        assertThat(received.getStringProperty("eventType"))
            .isEqualTo("order.created");
        assertThat(received.getIntProperty("schemaVersion"))
            .isEqualTo(2);
        assertThat(received.getBooleanProperty("replay"))
            .isFalse();

        String actualBody = ((TextMessage) received).getText();
        assertThat(actualBody).isEqualTo(payload);
    }
}
~~~

Test dùng destination có UUID để tránh đọc nhầm message còn sót từ lần chạy trước. Broker Artemis trong cấu hình local cho phép tự tạo queue khi producer gửi đến destination mới; nếu chính sách broker tắt auto-create, hãy tạo queue trước khi chạy test.

Vì payload là String và dùng SimpleMessageConverter mặc định, message nhận được là TextMessage. Test đọc raw jakarta.jms.Message để kiểm tra trực tiếp header chuẩn, application properties và body. Nó không chuyển message thành String trước khi assertion nên có thể xác minh đúng loại message.

Chạy:

~~~bash
mvn test
~~~

Điều kiện là Docker daemon hoạt động và broker Artemis đang lắng nghe tại localhost:61616. Test xác minh đường gửi/nhận qua broker; nó chưa kiểm tra redelivery, transaction rollback hoặc request/reply.

## 9. Nhận message và đọc metadata

Consumer có thể đọc header chuẩn và application properties trước khi xử lý body:

~~~java
public void inspect(Message message) throws JMSException {
    String correlationId = message.getJMSCorrelationID();
    String eventType = message.getStringProperty("eventType");
    int schemaVersion = message.getIntProperty("schemaVersion");

    if ("order.created".equals(eventType) && schemaVersion == 2) {
        // Chuyển tiếp tới handler dành cho schema phiên bản 2.
    }
}
~~~

Trong Spring, listener có thể nhận raw Message nếu cần truy cập tất cả header/property:

~~~java
@JmsListener(destination = "orders.queue")
public void handle(Message message) throws JMSException {
    String eventType = message.getStringProperty("eventType");
    String correlationId = message.getJMSCorrelationID();

    if (message instanceof TextMessage textMessage) {
        String body = textMessage.getText();
        // Parse và xử lý body theo eventType/schemaVersion.
    }
}
~~~

Để dùng @JmsListener, bật JMS listener infrastructure bằng @EnableJms trong cấu hình ứng dụng hoặc cấu hình auto-configuration phù hợp. Không để nhiều consumer cùng nhận một queue trong khi integration test cũng đang đọc trực tiếp queue đó, nếu không chúng có thể cạnh tranh và lấy mất message của nhau.

## 10. Message selector và lọc theo property

JMS selector cho phép consumer chỉ nhận message phù hợp với điều kiện trên header/property. Ví dụ:

~~~sql
eventType = 'order.created' AND schemaVersion >= 2
~~~

Trong Spring, có thể gắn selector vào listener:

~~~java
@JmsListener(
    destination = "orders.queue",
    selector = "eventType = 'order.created' AND schemaVersion >= 2"
)
public void handleV2(TextMessage message) {
    // Xử lý sự kiện order.created từ schema 2 trở lên.
}
~~~

Selector đánh giá property và các header được JMS cho phép; nó không parse JSON body để tìm trường. Nếu cần lọc theo dữ liệu chỉ có trong body, producer nên đưa một metadata ngắn, không nhạy cảm và ổn định vào property hoặc chia destination theo loại message.

Không dùng selector như cơ chế bảo mật. Producer có thể tự đặt application property; consumer vẫn phải xác thực danh tính, quyền và nội dung nghiệp vụ.

## 11. Correlation ID và request/reply

JMSCorrelationID thường dùng để ghép reply với request. Producer tạo request có correlation id ổn định; consumer phản hồi bằng cách đặt correlation id tương ứng vào reply.

Ví dụ thiết lập request:

~~~java
message.setJMSCorrelationID("request-1001");
message.setJMSReplyTo(replyQueue);
~~~

Consumer nhận request và tạo reply:

~~~java
TextMessage reply = session.createTextMessage("accepted");
reply.setJMSCorrelationID(request.getJMSCorrelationID());
producer.send(request.getJMSReplyTo(), reply);
~~~

Trong thực tế, Spring JmsTemplate hỗ trợ request/reply thông qua sendAndReceive hoặc convertSendAndReceive. Framework có thể quản lý temporary reply destination và correlation metadata. Khi dùng API request/reply có sẵn, tránh ghi đè correlation id hoặc reply-to mà framework thiết lập nếu chúng cần để ghép đúng response.

Correlation ID là metadata của message. Nó không đồng nghĩa với một định danh xác nhận publish của broker hoặc transaction id. Hãy xác định rõ mục đích của từng ID và không tái sử dụng một giá trị cố định cho mọi request đồng thời.

## 12. Redelivery, delivery count và idempotency

Khi consumer nhận message nhưng không hoàn tất transaction hoặc không acknowledge theo cơ chế của provider, broker có thể giao lại message. JMSRedelivered cho biết message đã từng được giao trước đó. JMSXDeliveryCount cung cấp số lần giao theo hỗ trợ của provider/JMS version.

Ví dụ kiểm tra:

~~~java
boolean redelivered = message.getJMSRedelivered();
int deliveryCount = message.propertyExists("JMSXDeliveryCount")
    ? message.getIntProperty("JMSXDeliveryCount")
    : 1;
~~~

Không phải mọi provider hoặc cấu hình đều cung cấp mọi thuộc tính mở rộng giống nhau; kiểm tra khả năng hỗ trợ của broker đang dùng. Dù delivery count có sẵn, nó chỉ là tín hiệu quan sát và không thay thế retry policy.

Consumer nên xử lý message theo cách idempotent. Một eventId ổn định trong application property hoặc body có thể được ghi vào bảng processed event với unique key. Nếu event đã được xử lý, consumer bỏ qua hiệu ứng lặp và kết thúc message theo đúng transaction/ack policy.

Không dùng JMSRedelivered làm khóa chống trùng. Nó chỉ cho biết message đã được giao lại; cùng một sự kiện có thể bị gửi trùng ngay từ producer mà cờ redelivered không phản ánh điều đó.

## 13. Transaction và thời điểm xác nhận

JMS session có thể hoạt động trong transaction hoặc non-transactional acknowledgement mode. Với transacted session, việc nhận message và các thao tác gửi trong cùng session có thể commit hoặc rollback cùng nhau theo transaction JMS.

Spring có thể quản lý JMS transaction qua JmsTransactionManager hoặc kết hợp transaction manager phù hợp với ứng dụng. Tuy nhiên, transaction JMS và transaction database không tự động trở thành một transaction phân tán chỉ vì cùng được gọi trong một phương thức có @Transactional.

Nếu consumer cập nhật database rồi commit nhưng message rollback hoặc được giao lại, nghiệp vụ có thể chạy lặp. Nếu message được xác nhận trước khi dữ liệu database commit, có nguy cơ mất công việc. Dùng inbox/outbox, idempotency key và chiến lược transaction rõ ràng khi cần nhất quán giữa broker và database.

## 14. Versioning và tương thích schema

Application property schemaVersion giúp consumer chọn cách giải mã body. Ví dụ eventType=order.created, schemaVersion=1 có thể có cấu trúc khác schemaVersion=2.

Một chiến lược versioning tốt cần:

- Giữ tên event ổn định và có quy ước rõ ràng.
- Đặt schemaVersion dưới dạng số nguyên, không dùng chuỗi tùy ý nếu cần so sánh.
- Xác định trường nào có thể thêm, xóa hoặc đổi kiểu mà không phá consumer cũ.
- Duy trì khả năng đọc message cũ trong khoảng thời gian queue có thể lưu message.
- Có kế hoạch nâng cấp producer và consumer theo từng bước.
- Không dùng JMSType hoặc một property tùy biến thay thế hoàn toàn schema validation.

Property chỉ nói consumer nên dùng schema nào; body vẫn phải được kiểm tra bằng parser hoặc schema validator. Không tin schemaVersion từ nguồn không xác thực như bằng chứng rằng payload là hợp lệ.

## 15. Bảo mật và lỗi thường gặp

### 15.1. Không đặt secret trong header/property

Header và property có thể được ghi log, hiển thị trong console quản trị, lưu trong dead-letter queue hoặc chuyển tiếp qua hệ thống trung gian. Không đặt password, access token, API key hay dữ liệu cá nhân nhạy cảm trong chúng.

### 15.2. Không tin property để xác định quyền

Các property như userId, role, tenantId hoặc isAdmin do producer gửi không phải bằng chứng xác thực. Consumer cần xác minh nguồn gửi và quyền truy cập bằng security context hoặc cơ chế tin cậy của hệ thống.

### 15.3. Tránh ObjectMessage cho dữ liệu không đáng tin

Java deserialization có thể thực thi logic trong quá trình khôi phục đối tượng. Ưu tiên JSON hoặc định dạng có schema. Nếu phải dùng ObjectMessage, giới hạn class được deserialize và kiểm soát chặt nguồn message.

### 15.4. Các lỗi phổ biến

- Đưa metadata định tuyến vào body khiến broker không thể dùng selector.
- Đưa payload nghiệp vụ lớn vào application property thay vì body.
- Đặt tên property có dấu gạch ngang hoặc bắt đầu bằng tiền tố dành riêng.
- Nhầm JMSCorrelationID với application property correlationId.
- Tự gán header do provider quản lý như JMSMessageID hoặc JMSDestination.
- Giả định priority luôn bảo đảm thứ tự giao.
- Dùng TTL để thay cho retry/backoff.
- Giả định persistent message đồng nghĩa exactly-once.
- Dùng ObjectMessage với nguồn dữ liệu không đáng tin.
- Viết selector dựa vào trường JSON trong body.
- Không kiểm tra message type trước khi ép kiểu TextMessage/BytesMessage.
- Đọc application property bằng getter primitive mà không kiểm tra propertyExists khi cần phân biệt giá trị mặc định với property bị thiếu.
- Để test consumer và ứng dụng thật cùng đọc một queue, làm message bị lấy mất bởi consumer khác.

## 16. Checklist thiết kế message

- [ ] Xác định rõ message dùng queue hay topic.
- [ ] Chọn đúng loại body: TextMessage, BytesMessage, MapMessage hoặc loại phù hợp.
- [ ] Dùng header chuẩn cho correlation, reply-to, delivery mode, priority và expiration.
- [ ] Dùng application property cho event type, schema version, trace id và metadata ngắn.
- [ ] Đặt tên property theo quy tắc JMS và tránh tiền tố dành riêng.
- [ ] Chọn kiểu property thuộc tập kiểu JMS hỗ trợ.
- [ ] Đặt schema version rõ ràng và kiểm tra body theo schema.
- [ ] Xác định TTL, delivery mode và priority theo SLA thực tế.
- [ ] Có idempotency và xử lý redelivery.
- [ ] Không tin property từ producer như thông tin xác thực.
- [ ] Không đưa secret hoặc payload nhạy cảm vào header/property.
- [ ] Kiểm thử message type, headers, properties và body qua broker thật.
- [ ] Có chính sách tương thích cho message cũ còn tồn tại trong queue.

## 17. Tổng kết

JMS Message tách metadata giao nhận, metadata ứng dụng và dữ liệu nghiệp vụ thành ba phần rõ ràng. Header chuẩn như JMSCorrelationID, JMSReplyTo, JMSDeliveryMode và JMSExpiration có ngữ nghĩa được JMS định nghĩa. Application properties như eventType và schemaVersion do ứng dụng quản lý, có thể dùng cho selector và điều phối xử lý. Body chứa payload thực tế dưới dạng TextMessage, BytesMessage, MapMessage, StreamMessage, ObjectMessage hoặc Message rỗng.

Trong Spring JMS, MessageConverter ánh xạ đối tượng Java sang loại JMS Message phù hợp; MessagePostProcessor có thể bổ sung header/property sau chuyển đổi. Hãy dùng đúng API cho từng loại metadata, giữ body độc lập với quy tắc định tuyến, xử lý redelivery theo hướng idempotent và kiểm thử message sau khi đi qua broker.

## Tài liệu tham khảo

- Jakarta Messaging 3.1 Specification: https://jakarta.ee/specifications/messaging/3.1/
- Jakarta Messaging API — Message: https://jakarta.ee/specifications/platform/10/apidocs/jakarta/jms/message
- Spring Framework — JMS: https://docs.spring.io/spring-framework/reference/integration/jms.html
- Spring Framework — JmsTemplate: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework — MessagePostProcessor: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/core/MessagePostProcessor.html