# Bổ sung metadata bằng MessagePostProcessor trong Spring JMS

## 1. Vì sao cần MessagePostProcessor?

Khi gửi thông điệp qua JMS, một service thường phải truyền **hai nhóm thông tin**: (1) **body/payload** chứa dữ liệu nghiệp vụ; (2) **metadata** để định danh, theo dõi, phân loại, lọc, đối chiếu request–reply hoặc quản lý phiên bản. Chẳng hạn một sự kiện tạo đơn hàng có body JSON chứa mã đơn và tổng tiền, nhưng consumer còn cần biết `eventType=OrderCreated`, `schemaVersion=2`, `tenantId=tenant-demo`, `traceId` và `JMSCorrelationID`.

Trong Spring Framework, giao diện **`org.springframework.jms.core.MessagePostProcessor`** cho phép can thiệp vào **`jakarta.jms.Message` sau khi chuyển đổi payload nhưng trước khi gửi vào broker**. Đây là vị trí tự nhiên để bổ sung **JMS headers do producer được phép thiết lập** và **custom message properties** mà không cần tự quản lý `Session`/`MessageProducer` cho từng lệnh gửi.

Bài này thuộc phần **Gửi thông điệp** của Spring JMS. Sau khi học, bạn có thể:

- Nêu đúng thứ tự `convertAndSend` → `MessageConverter` → `MessagePostProcessor` → producer send.
- Gọi overload `JmsTemplate.convertAndSend(..., MessagePostProcessor)` với lambda hoặc class riêng.
- Phân biệt **body, JMS headers, JMS properties** và thời điểm từng giá trị được gán.
- Thêm `JMSCorrelationID`, `JMSType`, `JMSReplyTo` và property đúng kiểu (`String`, `int`, `boolean`, `long`, ...).
- Tránh tự sửa các header do JMS provider quản lý như `JMSMessageID`, `JMSTimestamp`, `JMSExpiration` và `JMSPriority` nhằm thay thế QoS.
- Chạy demo **Java 17+, Spring Boot 3.5.x, Artemis embedded**, đọc lại message để xác minh metadata và áp dụng message selector.

## 2. Luồng xử lý: sau conversion nhưng trước send

Phương thức thông dụng:

~~~java
void convertAndSend(String destinationName,
                    Object payload,
                    org.springframework.jms.core.MessagePostProcessor processor);
~~~

Các overload tương tự nhận `jakarta.jms.Destination` hoặc sử dụng default destination nếu đã được cấu hình. Đây là chữ ký được trình bày để giải thích; **không phải** một method cần tự triển khai trong project.

~~~mermaid
flowchart LR
    A["Java payload"] --> B["MessageConverter.toMessage"]
    B --> C["JMS Message"]
    C --> D["MessagePostProcessor.postProcessMessage"]
    D --> E["MessageProducer.send"]
    E --> F["Broker"]
    F --> G["JMS Consumer"]
~~~

Ví dụ ngắn:

~~~java
// Fragment trong Spring bean đã được inject JmsTemplate template.
template.convertAndSend("orders.events", "ORDER-105", message -> {
    message.setJMSCorrelationID("corr-O-105");
    message.setStringProperty("eventType", "OrderCreated");
    message.setIntProperty("schemaVersion", 2);
    return message;
});
~~~

Với `SimpleMessageConverter` mặc định, `String` đầu vào được chuyển thành `TextMessage`. Lambda nhận **JMS Message đã chuyển đổi**, gắn metadata rồi trả về Message để `JmsTemplate` gửi. Không có `Thread.sleep` và không phải tự tạo `Connection`/`Session`.

Cần tách rõ ba thời điểm:

1. **Chuyển đổi payload:** `MessageConverter.toMessage(..., session)` tạo body cùng loại JMS message.
2. **Post-process:** callback có thể chỉnh message **trước khi send**. Các trường do provider gán khi gửi có thể chưa tồn tại hoặc chưa mang giá trị cuối cùng.
3. **Send:** provider ghi các header được quản lý bởi JMS, xử lý QoS, transaction và việc đưa message vào broker.

Vì thế **post-processor chạy xong không có nghĩa broker đã lưu/giao message thành công**. Sau callback còn có thể xảy ra lỗi send, rollback hoặc kết nối.

## 3. Đúng interface, đúng package

`MessagePostProcessor` của Spring JMS là functional interface, với hợp đồng chính:

~~~java
// Hình thức API để tham khảo, không tạo file/interface này trong ứng dụng.
jakarta.jms.Message postProcessMessage(
        jakarta.jms.Message message) throws jakarta.jms.JMSException;
~~~

- Đối số là `jakarta.jms.Message` **do converter tạo**.
- Giá trị trả về là JMS Message **không được null**; thông thường chỉnh sửa và trả lại **chính message được nhận**.
- Callback được phép ném `JMSException`. `JmsTemplate` thường chuyển JMS checked exception thành `org.springframework.jms.JmsException` không kiểm tra.
- Vì chỉ có một phương thức trừu tượng nên có thể sử dụng lambda, method reference hoặc class riêng.

**Cảnh báo trùng tên:** Spring còn có `org.springframework.messaging.core.MessagePostProcessor`. Nó làm việc với `org.springframework.messaging.Message<?>`, **khác** `jakarta.jms.Message`. Khi dùng `JmsTemplate.convertAndSend`, cần import:

~~~java
import org.springframework.jms.core.MessagePostProcessor;
import jakarta.jms.Message;
import jakarta.jms.JMSException;
~~~

Với **Spring Boot 3.x / Spring Framework 6.x**, dùng `jakarta.jms.*`, **không** trộn với `javax.jms.*` từ Java EE/JMS cũ. IDE chọn nhầm import là nguyên nhân phổ biến của lỗi compiler hoặc callback không có phương thức `setJMSCorrelationID`.

## 4. Phân biệt body, standard JMS header và custom property

| Thành phần | Vai trò | Ví dụ | API |
| --- | --- | --- | --- |
| **Body** | Dữ liệu nghiệp vụ. | JSON đơn hàng, byte[], MapMessage. | `TextMessage.getText()`, converter... |
| **Header JMS chuẩn do client có thể đặt** | Liên kết và định danh logic. | `JMSCorrelationID`, `JMSType`, `JMSReplyTo`. | `setJMSCorrelationID`, `setJMSType`, `setJMSReplyTo`. |
| **Header do provider quản lý** | Thông tin thực của việc gửi/giao. | `JMSMessageID`, `JMSTimestamp`, `JMSExpiration`, `JMSDeliveryTime`, `JMSPriority`. | Chủ yếu đọc sau send/ở consumer; cấu hình QoS qua producer/template. |
| **Custom properties** | Metadata do ứng dụng tạo để lọc, phân loại, theo dõi. | `eventType`, `schemaVersion`, `traceId`, `tenantId`. | `setStringProperty`, `setIntProperty`, ... |

Hình dung một message:

~~~text
Headers:
    JMSMessageID     = ID:...             (provider gán)
    JMSCorrelationID = corr-O-105        (client đặt)
    JMSType          = order.created
    JMSTimestamp     = ...               (provider gán)
Properties:
    eventType        = "OrderCreated"    (String)
    schemaVersion    = 2                 (int)
    tenantId         = "tenant-demo"     (String)
    auditRequired    = true              (boolean)
Body:
    {"orderId":"O-105","status":"CREATED"}
~~~

Đây là **cách trình bày logic**, không phải định dạng serialization bắt buộc trên wire. Một custom property là **metadata độc lập**, không phải trường mà JMS tự tìm trong JSON body. Ví dụ selector `eventType = 'OrderCreated'` đọc JMS property; nó **không parse** `eventType` từ body.

### 4.1. JMSCorrelationID

~~~java
message.setJMSCorrelationID("corr-O-105");
~~~

Consumer đọc bằng `message.getJMSCorrelationID()`. Giá trị dùng để nối các message thuộc một request/reply hoặc transaction logic; ứng dụng quy định convention. **Không đánh đồng**:

- `eventId`: định danh **một sự kiện nghiệp vụ**, nên ổn định qua lần retry/republish cùng sự kiện để hỗ trợ idempotency.
- `JMSCorrelationID`: định danh để liên kết chuỗi trao đổi; một correlation có thể bao gồm nhiều event.
- `JMSMessageID`: ID do provider gán **cho lần gửi**; khi producer retry bằng message mới thường có ID khác.

**Không trông đợi `getJMSMessageID()` trong post-processor**: provider thường chỉ điền ID khi send. Đừng tự tạo chuỗi giả mạo bắt đầu `ID:` rồi xem đó là provider ID; dùng ID ứng dụng riêng như `corr-O-105` hoặc UUID khi cần.

### 4.2. JMSType

~~~java
message.setJMSType("order.created");
~~~

`JMSType` mô tả loại message theo quy ước nghiệp vụ. `JMSType="order.created"` **khác** việc message là `TextMessage`: một TextMessage có thể mang nhiều loại sự kiện. Giá trị cũng có thể dùng trong message selector, nhưng nên giữ naming convention nhất quán giữa producer và consumer.

### 4.3. JMSReplyTo

`JMSReplyTo` biểu diễn destination mà bên gửi mong đợi nhận phản hồi:

~~~java
// Fragment: replyDestination là jakarta.jms.Destination đã có.
message.setJMSReplyTo(replyDestination);
~~~

Nó nhận **Destination object**, không đơn giản là String. Vì `MessagePostProcessor` không có tham số `Session`, nếu chỉ biết tên queue và muốn tạo destination object trong cùng session, dùng `MessageCreator`:

~~~java
// Fragment: có JmsTemplate template.
template.send("orders.requests", session -> {
    jakarta.jms.TextMessage req =
            session.createTextMessage("STATUS? O-105");
    req.setJMSCorrelationID("req-O-105");
    req.setJMSReplyTo(session.createQueue("orders.replies"));
    return req;
});
~~~

`createQueue("orders.replies")` tạo **đối tượng tham chiếu** tới Queue; việc queue vật lý có tồn tại hay được auto-create tùy broker. Nếu dùng `JmsTemplate.sendAndReceive`/các abstraction request–reply sẵn có, đừng tự thêm JMSReplyTo trái với cơ chế correlation/reply destination của template.

## 5. Custom properties: tên, kiểu dữ liệu và selector

JMS hỗ trợ các loại value property: `boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, `String`. Đặt đúng kiểu từ producer:

~~~java
// Fragment trong MessagePostProcessor callback:
msg.setStringProperty("eventType", "OrderCreated");
msg.setIntProperty("schemaVersion", 2);
msg.setBooleanProperty("auditRequired", true);
msg.setLongProperty("createdAtMillis", 1793328000000L);
msg.setDoubleProperty("riskScore", 0.35);
~~~

Consumer đọc đúng getter:

~~~java
String eventType = msg.getStringProperty("eventType");
int schemaVersion = msg.getIntProperty("schemaVersion");
boolean auditRequired = msg.getBooleanProperty("auditRequired");
long createdAt = msg.getLongProperty("createdAtMillis");
double riskScore = msg.getDoubleProperty("riskScore");
~~~

Đây là **code fragment**, giả định có `jakarta.jms.Message msg`. Các phương thức property có thể ném `JMSException`; xử lý exception theo API/ngữ cảnh.

**Tên property tuân thủ identifier của JMS selector:** ký tự đầu là Java identifier start, ký tự tiếp theo là Java identifier part; tên phân biệt chữ hoa/chữ thường. Tránh khoảng trắng, dấu gạch nối, keyword như `AND`, `OR`, `TRUE`, `NULL`. Dùng `traceId` thay cho `trace-id`. Property `schemaVersion` khác `schemaversion`.

**Không set arbitrary POJO/Map/List làm một property**: JMS properties chỉ hỗ trợ nhóm kiểu đơn giản trên. Muốn truyền object, dùng body/converter. Nếu cần metadata phức tạp, thiết kế body JSON hoặc tách thành một số property nhỏ có mục đích rõ.

### 5.1. Lọc theo property tại broker

~~~java
// Fragment: session và queue đã được tạo.
jakarta.jms.MessageConsumer consumer = session.createConsumer(
        queue,
        "eventType = 'OrderCreated' AND schemaVersion >= 2");
~~~

Selector sử dụng `eventType` dạng String, `schemaVersion` dạng numeric property. Nếu producer gọi `setStringProperty("schemaVersion", "2")`, phép so sánh số có thể không match như mong muốn. Selector **không đọc JSON body** và không thay thế phân quyền bảo mật.

### 5.2. Các property JMSX

Prefix `JMSX` do Jakarta Messaging dành cho property chuẩn. Những trường có thể liên quan:

- `JMSXGroupID` và `JMSXGroupSeq`: producer có thể dùng để mô tả message group khi ứng dụng/broker áp dụng message grouping.
- `JMSXDeliveryCount`: provider đặt khi receive để mô tả số lần delivery (1 ở lần đầu, từ 2 trở lên khi redelivery).
- Các JMSX khác có thể optional hoặc do provider quản lý.

Ví dụ message group:

~~~java
template.convertAndSend("orders.events", "ORDER-105", msg -> {
    msg.setStringProperty("JMSXGroupID", "customer-42");
    msg.setIntProperty("JMSXGroupSeq", 1);
    return msg;
});
~~~

Chỉ sử dụng group ID/sequence khi đã hiểu quy tắc message grouping của provider; nó không tự bảo đảm exactly-once processing hoặc thứ tự hoàn tất của các giao dịch DB độc lập. **Không tự set `JMSXDeliveryCount`** để mô phỏng retry.

**Bảo mật:** `tenantId`, `role`, `userId` là dữ liệu do publisher đặt, nên consumer không được chỉ dựa vào chúng để xác thực quyền truy cập. Cần kết hợp broker ACL, xác thực producer và kiểm chứng nghiệp vụ. Không chứa access token, mật khẩu hoặc dữ liệu khách hàng không cần thiết trong properties/log.

## 6. Lambda, class riêng và reusable processor

Lambda là cách gọn nhất cho một lần gửi:

~~~java
template.convertAndSend("orders.events", "ORDER-105", msg -> {
    msg.setJMSType("order.created");
    msg.setStringProperty("eventType", "OrderCreated");
    return msg;
});
~~~

Khi logic metadata dùng lại nhiều nơi, viết class có tham số bất biến:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.core.MessagePostProcessor;

public final class OrderMetadataProcessor implements MessagePostProcessor {

    private final String correlationId;
    private final int schemaVersion;

    public OrderMetadataProcessor(String correlationId, int schemaVersion) {
        this.correlationId = correlationId;
        this.schemaVersion = schemaVersion;
    }

    @Override
    public Message postProcessMessage(Message message) throws JMSException {
        message.setJMSCorrelationID(correlationId);
        message.setJMSType("order.created");
        message.setIntProperty("schemaVersion", schemaVersion);
        return message;
    }
}
~~~

Đây là **nội dung tệp `OrderMetadataProcessor.java`** (thêm package theo project). Gọi:

~~~java
template.convertAndSend(
        "orders.events",
        "ORDER-105",
        new OrderMetadataProcessor("corr-O-105", 2));
~~~

Bất kỳ metadata nào thay đổi theo request phải được truyền qua constructor/method hoặc lambda capture một biến cục bộ **không đổi**. Không tạo singleton processor với field mutable `currentCorrelationId` rồi set trước mỗi `convertAndSend`: nhiều request song song có thể ghi đè nhau, làm message mang ID của request khác.

Callback phải **trả lại Message không null**. Thông thường dùng `return message;`. Nếu cần thay đổi định dạng body hàng loạt, ưu tiên cấu hình `MessageConverter`, thay vì tạo thủ công Message khác trong callback mà không rõ loại và session của nó.

## 7. Ví dụ chạy được: Java 17+, Spring Boot, Artemis embedded

Demo này không cần cài broker riêng. Spring Boot tạo `ConnectionFactory` và `JmsTemplate`, ActiveMQ Artemis chạy embedded. Ta gửi một chuỗi JSON, gắn metadata, sau đó **nhận raw JMS Message** từ Queue để kiểm chứng.

Yêu cầu: **JDK 17+** và **Maven 3.6.3+**. Cấu trúc:

~~~text
jms-postprocessor-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmspost/
    │   └── JmsPostProcessorDemoApplication.java
    └── resources/
        └── application.properties
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-postprocessor-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
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
~~~

Spring Boot parent quản lý version thư viện tương thích. `spring-boot-starter-artemis` mang JMS client; `artemis-jakarta-server` cho phép broker nhúng.

### 7.2. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.metadata
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=5s
spring.main.banner-mode=off
~~~

- Queue `demo.metadata` được broker nhúng provision khi khởi động.
- `receive-timeout=5s` giúp demo không treo vô thời hạn.
- `persistent=false` chỉ để thử nghiệm; không chứng minh message có thể sống qua restart.
- `pub-sub-domain=false` dùng semantics Queue thay vì Topic.

### 7.3. Java source hoàn chỉnh

Tạo `src/main/java/com/example/jmspost/JmsPostProcessorDemoApplication.java`:

~~~java
package com.example.jmspost;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsPostProcessorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsPostProcessorDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(JmsTemplate jmsTemplate) {
        return args -> {
            String body =
                    "{\"orderId\":\"O-105\",\"status\":\"CREATED\"}";

            jmsTemplate.convertAndSend("demo.metadata", body, message -> {
                message.setJMSCorrelationID("corr-O-105");
                message.setJMSType("order.created");
                message.setStringProperty("eventType", "OrderCreated");
                message.setIntProperty("schemaVersion", 2);
                message.setBooleanProperty("auditRequired", true);
                message.setStringProperty("tenantId", "tenant-demo");
                return message;
            });

            Message incoming = jmsTemplate.receive("demo.metadata");
            if (!(incoming instanceof TextMessage received)) {
                throw new IllegalStateException(
                        "Không nhận được TextMessage trong 5 giây");
            }

            System.out.println("BODY=" + received.getText());
            System.out.println(
                    "CORRELATION=" + received.getJMSCorrelationID());
            System.out.println("TYPE=" + received.getJMSType());
            System.out.println(
                    "EVENT_TYPE=" + received.getStringProperty("eventType"));
            System.out.println(
                    "SCHEMA_VERSION="
                            + received.getIntProperty("schemaVersion"));
            System.out.println(
                    "AUDIT_REQUIRED="
                            + received.getBooleanProperty("auditRequired"));
            System.out.println(
                    "TENANT=" + received.getStringProperty("tenantId"));
        };
    }
}
~~~

**Phân tích chính xác luồng gửi/nhận:**

1. `ApplicationRunner` thực thi khi Spring đã khởi động context; Boot đã tạo `JmsTemplate` và embedded broker.
2. Body là `String` chứa JSON, nên converter mặc định biến nó thành **TextMessage**. Không cần thêm JSON converter để gửi một chuỗi đã serialize.
3. `MessagePostProcessor` đặt header `JMSCorrelationID`, `JMSType`, rồi bốn custom properties với type phù hợp.
4. Callback trả `message`; `JmsTemplate` thực hiện JMS send tới `demo.metadata`.
5. `JmsTemplate.receive` lấy lại **raw `jakarta.jms.Message`**, không mất metadata như khi chỉ lấy body bằng `receiveAndConvert`.
6. Pattern matching `instanceof TextMessage` xác nhận loại message trước khi gọi `getText`.
7. Vì chỉ có một producer và một consumer đồng bộ trong demo, chương trình không cần xử lý cạnh tranh giữa nhiều consumers. Production phải kiểm soát transaction, idempotency và retry theo yêu cầu.

Chạy ở thư mục `jms-postprocessor-demo`:

~~~bash
mvn spring-boot:run
~~~

Các dòng được in bởi mã ứng dụng (bỏ qua log Maven/Spring/Artemis) phải có nội dung:

~~~text
BODY={"orderId":"O-105","status":"CREATED"}
CORRELATION=corr-O-105
TYPE=order.created
EVENT_TYPE=OrderCreated
SCHEMA_VERSION=2
AUDIT_REQUIRED=true
TENANT=tenant-demo
~~~

Dòng timestamp/JMSMessageID không được in vì chúng **phụ thuộc mỗi lần gửi**, còn payload và custom metadata được đặt cố định trong ví dụ nên dễ kiểm chứng. Đây là output kỳ vọng từ chương trình được trình bày, không phải lời khẳng định đã thực thi Maven ở mọi môi trường.

## 8. Khi nào header được provider gán?

Trong `MessagePostProcessor`, các header client có quyền đặt như `JMSCorrelationID`, `JMSType`, `JMSReplyTo` có thể được chỉnh sửa. Nhưng **một số header khác do provider tính tại thời điểm send hoặc receive**:

| Header | Ai quyết định khi gửi/nhận? | API thực tế |
| --- | --- | --- |
| `JMSMessageID` | Provider gán khi send. | Đọc `getJMSMessageID()` sau send hoặc ở consumer. |
| `JMSTimestamp` | Provider gán khi send, có thể bị tắt theo thiết lập phù hợp. | Đọc `getJMSTimestamp()`. |
| `JMSDestination` | Provider ghi destination thực đã gửi. | Chọn destination qua `convertAndSend(destination,...)`. |
| `JMSDeliveryMode` | Chính sách delivery mode khi send. | Đặt qua `JmsTemplate`/producer QoS. |
| `JMSPriority` | Giá trị priority hiệu lực khi send. | Đặt qua QoS, không trông chờ `setJMSPriority` trong callback. |
| `JMSExpiration` | Provider tính từ time-to-live. | Đặt TTL trên producer/`JmsTemplate`. |
| `JMSDeliveryTime` | Provider tính từ send time + delivery delay. | Đặt delivery delay trên producer/`JmsTemplate`. |
| `JMSRedelivered` | Provider xác định trạng thái redelivery. | Consumer đọc; không dùng để giả mạo retry. |

Có thể thêm đoạn sau **ở phía nhận** trong demo:

~~~java
System.out.println("MESSAGE_ID=" + received.getJMSMessageID());
System.out.println("TIMESTAMP=" + received.getJMSTimestamp());
System.out.println("DESTINATION=" + received.getJMSDestination());
System.out.println("PRIORITY=" + received.getJMSPriority());
~~~

Giá trị cụ thể do broker định, không hardcode để assert. `JmsTemplate.convertAndSend` có kết quả trả về `void`, không trả trực tiếp `JMSMessageID` sau gửi; nên với nghiệp vụ cần đối soát, tạo `eventId` riêng trước khi gửi.

**Lỗi cần tránh:** viết trong callback:

~~~java
// Không dùng callback để thay QoS của send:
message.setJMSPriority(9);
message.setJMSExpiration(System.currentTimeMillis() + 60_000L);
message.setJMSDeliveryTime(System.currentTimeMillis() + 5_000L);
~~~

Provider có thể ghi đè các trường này khi send; đây không phải API portable để cấu hình priority, TTL hay delay.

## 9. Cấu hình QoS đúng cách thay vì sửa JMS header

Đặt QoS bằng producer hoặc `JmsTemplate` được cấu hình:

~~~java
// Fragment: ConnectionFactory connectionFactory đã có.
org.springframework.jms.core.JmsTemplate highPriority =
        new org.springframework.jms.core.JmsTemplate(connectionFactory);

highPriority.setExplicitQosEnabled(true);
highPriority.setPriority(8);
highPriority.setDeliveryMode(jakarta.jms.DeliveryMode.PERSISTENT);
highPriority.setTimeToLive(120_000L);

highPriority.convertAndSend("orders.urgent", "ORDER-105", msg -> {
    msg.setStringProperty("eventType", "UrgentOrder");
    return msg;
});
~~~

Trong Spring Boot 3.5 có thể cấu hình qua `application.properties`:

~~~properties
spring.jms.template.qos-enabled=true
spring.jms.template.priority=8
spring.jms.template.delivery-mode=persistent
spring.jms.template.time-to-live=2m
~~~

Đây là **cấu hình cho template**, không phải metadata được tự thêm vào một message cụ thể bằng callback. Với `JmsTemplate`, priority/delivery mode/TTL được dùng để gọi send khi bật **explicit QoS** (Spring Boot có thể tự bật khi tùy biến một số giá trị QoS). Delivery delay có cấu hình riêng `spring.jms.template.delivery-delay` hoặc `template.setDeliveryDelay(...)`.

**Quy tắc quan trọng:** `JmsTemplate` có thể dùng chung nhiều thread sau khi đã cấu hình ổn định. Không gọi `setPriority`/`setTimeToLive` liên tục trên shared singleton trước từng `convertAndSend`, vì request đồng thời có thể “mượn” policy của nhau. Nếu từng loại message cần QoS khác nhau, dùng template/producer riêng hoặc API gửi per-message rõ ràng.

## 10. MessageConverter khác MessagePostProcessor

`MessageConverter` là nơi định nghĩa **cách chuyển body** thành JMS Message. `MessagePostProcessor` chỉnh thông tin trên JMS Message **sau conversion**.

| Việc cần làm | API phù hợp |
| --- | --- |
| `String` → `TextMessage`; `byte[]` → `BytesMessage`; `Map` → `MapMessage`. | `MessageConverter` |
| POJO → JSON text, kiểm soát serializer/schema. | Custom `MessageConverter` và JSON library. |
| Đặt `JMSCorrelationID`, `JMSType`. | `MessagePostProcessor`. |
| Đặt `eventId`, `schemaVersion`, `tenantId`. | `MessagePostProcessor`. |
| Đặt destination thực gửi. | `convertAndSend(destinationName,...)` hoặc resolver. |
| Đặt priority/TTL/delivery mode. | QoS của `JmsTemplate` hoặc JMS producer. |
| Quản lý transaction/commit. | `Session`, transaction manager, container. |

`SimpleMessageConverter` mặc định hỗ trợ `String`, `byte[]` và `Map`. Nó **không có nghĩa mọi Java POJO bất kỳ đều tự thành JSON TextMessage**.

Ví dụ body `Map` kèm property:

~~~java
java.util.Map<String, Object> body = java.util.Map.of(
        "orderId", "O-105",
        "total", 420000);

template.convertAndSend("orders.events", body, msg -> {
    msg.setStringProperty("eventType", "OrderCreated");
    msg.setJMSCorrelationID("corr-O-105");
    return msg;
});
~~~

Đây là fragment; `body` trở thành MapMessage theo converter phù hợp, **không** tự động thành chuỗi JSON. Custom property `eventType` không phải field của MapMessage. Nếu cần POJO JSON, hãy cấu hình converter và kiểm thử cả conversion lẫn metadata.

## 11. Metadata và message selector trong Spring JMS

Một lợi ích của custom properties là broker có thể lọc message mà không cần parse body. Producer:

~~~java
template.convertAndSend("orders.events", "ORDER-105 created", msg -> {
    msg.setStringProperty("eventType", "OrderCreated");
    msg.setIntProperty("schemaVersion", 2);
    return msg;
});

template.convertAndSend("orders.events", "ORDER-105 cancelled", msg -> {
    msg.setStringProperty("eventType", "OrderCancelled");
    msg.setIntProperty("schemaVersion", 2);
    return msg;
});
~~~

Consumer chỉ nhận loại cần:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @JmsListener(
            destination = "orders.events",
            selector = "eventType = 'OrderCreated' AND schemaVersion >= 2")
    public void onCreated(String body) {
        System.out.println("Created: " + body);
    }
}
~~~

Đây là **class Spring-managed**, yêu cầu hạ tầng listener đang chạy, broker và Queue tồn tại. Một Queue còn message `OrderCancelled` mà không có consumer matching có thể tồn đọng; khi dùng Topic thì semantics subscription khác. **Selector chỉ là lọc message, không thay thế xác thực/authorization**.

### 11.1. Đọc metadata qua @Header

Spring listener có thể nhận custom JMS property như header nếu listener adapter hỗ trợ mapping tương ứng:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class VersionedOrderListener {

    @JmsListener(destination = "orders.events")
    public void handle(
            String body,
            @Header("eventType") String eventType,
            @Header("schemaVersion") int schemaVersion) {

        System.out.println(
                eventType + " v" + schemaVersion + ": " + body);
    }
}
~~~

Ví dụ giả định các message được giao có hai property đúng kiểu. Với property tùy chọn, nên xử lý trường hợp vắng mặt, ví dụ dùng kiểu nullable và `@Header(required=false)`, hoặc nhận raw `jakarta.jms.Message` rồi kiểm tra `propertyExists`. Khi dùng custom converter/adapter, phải xác minh mapping JMS properties sang messaging headers.

## 12. Thiết kế metadata ổn định cho production

Một contract tối thiểu cho sự kiện `OrderCreated`:

| Tên | Kiểu | Mục đích |
| --- | --- | --- |
| `eventId` | String property | Idempotency và đối chiếu lần republish cùng sự kiện. |
| `JMSCorrelationID` | JMS header | Liên kết request–reply/giao dịch logic. |
| `JMSType` | JMS header | Ký hiệu `order.created` trong hệ thống. |
| `eventType` | String property | Selector và phân loại. |
| `schemaVersion` | int property | Phân nhánh xử lý body theo phiên bản. |
| `sourceService` | String property | Ghi nhận dịch vụ phát hành. |
| `tenantId` | String property | Định danh tenant, cần được consumer xác minh. |
| `traceId` | String property | Liên kết log; khi dùng tracing chuẩn, ưu tiên propagation của thư viện. |

Ví dụ publisher giữ metadata cố định cho từng lời gọi:

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final JmsTemplate template;

    public OrderEventPublisher(JmsTemplate template) {
        this.template = template;
    }

    public void publish(
            String eventId,
            String correlationId,
            String jsonBody) {

        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId required");
        }
        if (correlationId == null || correlationId.isBlank()) {
            throw new IllegalArgumentException("correlationId required");
        }

        template.convertAndSend("orders.events", jsonBody, msg -> {
            msg.setJMSCorrelationID(correlationId);
            msg.setJMSType("order.created");
            msg.setStringProperty("eventId", eventId);
            msg.setStringProperty("eventType", "OrderCreated");
            msg.setIntProperty("schemaVersion", 2);
            msg.setStringProperty("sourceService", "order-service");
            return msg;
        });
    }
}
~~~

Đây là class Spring cần đặt trong package project và có cấu hình kết nối JMS. `eventId` do nghiệp vụ sinh **trước send**, nên có thể giữ ổn định nếu producer retry cùng sự kiện. Đừng tạo event ID mới trong lambda cho mỗi lần thử gửi nếu mục đích là idempotency.

**Đừng tin hoàn toàn metadata do producer cung cấp:** role/tenant ID phải gắn với identity đã xác thực và được validate; JMS properties có thể đi vào log, DLQ hoặc công cụ quản trị nên cần tránh dữ liệu bí mật. Nếu đã dùng OpenTelemetry/Micrometer, nên dùng context propagation đúng định dạng của thư viện thay vì tự coi một `traceId` property là distributed tracing đầy đủ.

## 13. Lỗi, retry và ranh giới transaction

`postProcessMessage` có thể ném `JMSException` khi gọi các setter JMS. Một lỗi `IllegalArgumentException` khi validate `eventId` cũng có thể chặn send.

~~~java
// Fragment trong Spring service:
try {
    template.convertAndSend("orders.events", payload, msg -> {
        msg.setStringProperty("eventType", "OrderCreated");
        return msg;
    });
} catch (org.springframework.jms.JmsException ex) {
    // Ghi log có cấu trúc, không lộ payload nhạy cảm.
    // Xác định retry theo chính sách nghiệp vụ.
    throw ex;
}
~~~

`template` và `payload` cần được cung cấp bởi service; đoạn trên không phải chương trình độc lập.

Điểm chính:

- Nếu callback ném lỗi, lời gọi send thông thường không được thực hiện thành công.
- Nếu callback chạy xong nhưng broker từ chối send hoặc transaction rollback, message có thể không được công bố.
- Nếu DB đã commit nhưng JMS send chưa hoàn tất hoặc ngược lại, metadata **không tự phối hợp** hai transaction. Xem xét transactional outbox nếu cần tính nhất quán.
- Nếu consumer xử lý thành công nhưng ack/commit JMS thất bại, message có thể được giao lại; `eventId` giúp thiết kế idempotency.
- Không `catch` lỗi bắt buộc bên trong callback rồi `return message` như thể hoàn tất; điều này có thể khiến message thiếu metadata quan trọng lọt vào broker.

`MessagePostProcessor` **không phải** cơ chế gửi lại, DLQ, retry/backoff hoặc xác nhận consumer đã xử lý. Trách nhiệm của nó là chỉnh JMS Message trước send.

## 14. Kiểm thử và chẩn đoán

### 14.1. Test đơn vị

Với class `OrderMetadataProcessor`, có thể mock `jakarta.jms.Message` bằng Mockito và kiểm tra:

1. `setJMSCorrelationID` được gọi đúng giá trị.
2. `setIntProperty("schemaVersion", 2)` được gọi đúng kiểu.
3. Hàm `postProcessMessage` trả về **chính Message đầu vào**, không null.
4. Constructor nhận metadata riêng của từng send, không dùng mutable global state.
5. Lỗi setter/validation được bộc lộ cho caller.

Mock chỉ kiểm tra callback; **không** chứng minh broker thực lưu/đọc header. Dùng integration test với Artemis cho điều đó.

### 14.2. Test tích hợp

Theo demo mục 7:

1. Tạo queue test riêng và gửi một message có `JMSCorrelationID`, `JMSType` và properties.
2. Nhận **raw** `Message` bằng `JmsTemplate.receive` có timeout hữu hạn.
3. Assert getter trả đúng giá trị và type property.
4. Thử một message khác, xác minh metadata không “dính” từ send trước.
5. Nếu có selector, assert đúng message match và hiểu hành vi của message không match.
6. Với `JMSMessageID`/`JMSTimestamp`, kiểm tra giá trị hợp lệ theo provider, **không hardcode**.
7. Với QoS, kiểm tra config template/producer và hành vi broker; không chỉ mock `setJMSPriority`.
8. Dọn queue và giữ cô lập môi trường test; consumer khác không được tranh message làm test flaky.

### 14.3. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| Không compile lambda | Import nhầm `MessagePostProcessor` hoặc `javax.jms`/ `jakarta.jms` lẫn nhau. | Dùng `org.springframework.jms.core.MessagePostProcessor`, `jakarta.jms.*`. |
| Callback không chạy | Dùng overload `convertAndSend` không có processor hoặc chỉ dùng `send(MessageCreator)`. | Gọi đúng overload có processor. |
| `JMSMessageID` chưa có trong callback | Message chưa send. | Đọc sau send theo API phù hợp hoặc tại consumer. |
| Custom property mất | Đọc nhầm message, khác chữ hoa/thường, converter/adapter khác, broker không nhận send. | Nhận raw JMS Message và kiểm tra getter/queue. |
| Selector không nhận | `schemaVersion` gửi String nhưng so sánh số; expression sai. | Dùng `setIntProperty` và đúng property name. |
| Priority/TTL không hoạt động | Đặt header trong callback thay vì cấu hình QoS. | `setExplicitQosEnabled(true)`, `setPriority`, `setTimeToLive`. |
| Code trả `null` từ callback | Vi phạm hợp đồng `postProcessMessage`. | Trả về message hợp lệ. |
| POJO không convert được | `SimpleMessageConverter` không biết cách chuyển domain object. | Cài custom `MessageConverter`. |
| Nhiều request dùng nhầm correlation ID | Singleton processor giữ field mutable theo request. | Dùng immutable lambda/processor per send. |
| Metadata chứa thông tin nhạy cảm | Đẩy token, session key hoặc PII vào property. | Giảm dữ liệu, kiểm soát log/ACL/DLQ và masking. |
| Post-processor log “OK”, consumer không nhận | Send lỗi, chưa commit, destination sai, selector không match, TTL hết hạn. | Kiểm tra broker metrics, transaction và exception chain. |

### 14.4. Test âm tính nên làm

- Thử callback cố ý ném `JMSException` và kiểm tra không có message hợp lệ bị gửi.
- Gửi property `schemaVersion` sai kiểu rồi thấy selector số không match như dự kiến.
- Thử `eventId` trống và xác minh service fail fast trước send.
- Thử hai lần gửi với correlation IDs khác nhau, xác minh mỗi message giữ ID riêng.
- Kiểm tra trường metadata được yêu cầu nhưng thiếu: consumer phải báo rõ hoặc đưa vào quy trình xử lý lỗi, không giả định tất cả message luôn có metadata.

## 15. Câu hỏi tự luyện

1. **MessagePostProcessor chạy trước hay sau MessageConverter?** Sau conversion, trước producer send.
2. **Nó làm việc với `jakarta.jms.Message` hay `org.springframework.messaging.Message`?** Với `JmsTemplate` là `jakarta.jms.Message` từ `org.springframework.jms.core.MessagePostProcessor`.
3. **Muốn thêm `eventType` để dùng selector phải làm gì?** Gọi `setStringProperty("eventType", "...")` trước send.
4. **Có nên đặt `JMSMessageID` bằng client UUID trong callback không?** Không; ID này do provider tạo. Dùng `eventId` riêng.
5. **Tại sao `setJMSPriority(9)` không thay thế `setPriority(9)` trên producer/template?** Provider xác định priority khi send theo QoS.
6. **`JMSCorrelationID` và `eventId` có nhất thiết giống nhau không?** Không. Correlation liên kết luồng; eventId định danh sự kiện để xử lý trùng.
7. **Vì sao không set `schemaVersion="2"` bằng String khi selector so sánh số?** JMS selector phân biệt type; cần numeric property.
8. **Muốn gắn reply queue bằng tên, post-processor có Session trực tiếp không?** Không; truyền Destination đã có hoặc dùng `MessageCreator` nhận Session.
9. **Trả `null` từ `postProcessMessage` có hợp lệ không?** Không.
10. **Callback hoàn tất có xác nhận DB và consumer đã commit không?** Không; callback chỉ chuẩn bị metadata trước send.

## 16. Nguồn tài liệu chính thức

- [Spring Framework 6.2 — Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html): `MessageConverter`, ví dụ `MessagePostProcessor` và cách đặt headers/properties.
- [Spring Framework 6.2 — MessagePostProcessor API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/MessagePostProcessor.html): chữ ký, `JMSException`, hợp đồng trả về không null.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): overloads `convertAndSend`, QoS, `receive`, transaction.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): message headers/properties, selector identifiers, `JMSXGroupID` và `JMSXDeliveryCount`.
- [Jakarta Messaging 3.1 Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): getter/setter và kiểu property.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): broker nhúng và auto-configuration.
- [Spring Boot 3.5 — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.jms.template.receive-timeout`, QoS và Artemis.

**Tóm lược:** `MessagePostProcessor` là bước **chỉnh sửa JMS Message sau conversion nhưng trước send**. Dùng nó để gắn `JMSCorrelationID`, `JMSType` và **typed properties** nhất quán; không dùng để mạo danh provider hoặc thay thế QoS/transaction. Một contract metadata tốt giúp lọc sự kiện, tracing và idempotency, nhưng vẫn cần xử lý bảo mật, retry và kiểm tra dữ liệu ở consumer.
