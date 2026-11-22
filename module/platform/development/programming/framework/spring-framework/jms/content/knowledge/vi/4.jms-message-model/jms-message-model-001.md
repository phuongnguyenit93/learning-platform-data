# Cấu trúc header, properties và body của JMS Message trong Spring Framework

## 1. Bức tranh tổng quan

Trong Jakarta Messaging (JMS), **message** là đơn vị dữ liệu được producer gửi vào **Destination** (Queue hoặc Topic) và consumer đọc từ broker. Một JMS message có **ba phần khác vai trò**:

1. **Header**: các trường chuẩn của JMS dùng để định danh, định tuyến, điều phối phân phối và theo dõi message.
2. **Properties**: các cặp tên–giá trị có kiểu, dùng làm metadata mở rộng của ứng dụng, của chuẩn JMS hoặc của provider; broker có thể dùng một số trường này để lọc.
3. **Body**: dữ liệu nghiệp vụ chính, chẳng hạn chuỗi JSON, văn bản, byte array hoặc dữ liệu dạng map.

~~~text
Producer / Spring JmsTemplate
        |
        v
+------------------ JMS Message ------------------+
| HEADER        JMSMessageID, JMSCorrelationID,    |
|               JMSDestination, JMSType, ...       |
+-------------------------------------------------+
| PROPERTIES    tenant="VN", schemaVersion=1,      |
|               requiresAudit=true, ...            |
+-------------------------------------------------+
| BODY          {"orderId":"O-42","total":125000}  |
+-------------------------------------------------+
        |
        v
      Broker  --- selector trên header/property được hỗ trợ
        |
        v
Consumer / @JmsListener  ---> xử lý body + metadata
~~~

Giả sử một hệ thống đơn hàng gửi sự kiện tạo đơn:

- **Body** mang nội dung `{"orderId":"O-42","total":125000}` để nghiệp vụ xử lý.
- **Property** `tenant="VN"` giúp consumer chỉ nhận message của một miền dữ liệu; `schemaVersion=1` giúp chọn cách giải mã.
- **Header** `JMSCorrelationID="checkout-O-42"` giúp đối chiếu với một luồng yêu cầu hoặc trace; `JMSMessageID` do provider sinh khi gửi.

Ba phần cùng thuộc **một JMS message**. Giá trị header/property không phải trường JSON nằm trong body, và broker không mặc nhiên hiểu nội dung JSON.

## 2. Header: những trường chuẩn mà mọi JMS Message đều hỗ trợ

Các trường header được định nghĩa trong `jakarta.jms.Message`; getter tương ứng có dạng `getJMSMessageID()`, `getJMSTimestamp()`, v.v. Trong bảng sau, “provider” là thư viện/broker triển khai JMS, còn “ứng dụng” là mã producer/consumer.

| Header | Vai trò | Ai thiết lập theo hợp đồng JMS? |
| --- | --- | --- |
| `JMSDestination` | Queue hoặc Topic đích của message | Provider khi gửi |
| `JMSMessageID` | Định danh kỹ thuật của message, thông thường do provider tạo | Provider khi gửi |
| `JMSTimestamp` | Thời điểm gửi tính bằng millisecond kể từ Unix epoch UTC | Provider khi gửi |
| `JMSDeliveryMode` | `PERSISTENT` hoặc `NON_PERSISTENT` | Provider phản ánh lựa chọn khi gửi |
| `JMSExpiration` | Thời điểm message hết hạn; `0` nghĩa là không hết hạn theo TTL | Provider tính từ TTL khi gửi |
| `JMSDeliveryTime` | Mốc sớm nhất provider được phép giao message; liên quan delivery delay | Provider khi gửi |
| `JMSPriority` | Mức ưu tiên từ `0` đến `9`, mặc định `4` | Provider phản ánh lựa chọn khi gửi |
| `JMSCorrelationID` | Mã liên hệ các message trong một cuộc trao đổi hoặc luồng xử lý | Ứng dụng có thể đặt trước khi gửi |
| `JMSReplyTo` | `Destination` gợi ý nơi nhận phản hồi cho message yêu cầu | Ứng dụng có thể đặt trước khi gửi |
| `JMSType` | Nhãn loại message theo quy ước của ứng dụng/provider | Ứng dụng có thể đặt trước khi gửi |
| `JMSRedelivered` | Dấu hiệu message đang được giao lại, không phải lần giao đầu | Provider trước khi giao |

### 2.1. Nhóm định danh và liên hệ

**`JMSMessageID`** là ID kỹ thuật của bản JMS message. Provider thường gán nó khi thao tác gửi hoàn tất; định dạng và tiền tố như `ID:...` phụ thuộc provider. Ứng dụng không nên tự đặt bằng `setJMSMessageID` trước khi gửi vì provider sẽ bỏ qua/ghi đè. Có thể tắt sinh ID trong một số cấu hình nhằm tối ưu; vì vậy không xây dựng logic nghiệp vụ dựa trên giả định ID luôn có giá trị.

**`JMSCorrelationID`** do producer chủ động gắn và được chuyển cho consumer. Hai cách sử dụng phổ biến:

- Gán business correlation ID, ví dụ `checkout-O-42`, cho các message của cùng một giao dịch.
- Trong mẫu request/reply, reply có `JMSCorrelationID` trỏ tới mã yêu cầu; có hệ thống chọn ID nghiệp vụ và có hệ thống chọn `JMSMessageID` của request. Hai đầu phải thỏa thuận cùng một quy tắc.

**`JMSReplyTo`** chỉ cung cấp địa chỉ phản hồi; nó **không tự sinh reply**. Ứng dụng nhận vẫn phải tạo/gửi reply, hoặc dùng chức năng hỗ trợ phản hồi của listener framework.

**`JMSType`** là nhãn phân loại, ví dụ `order.created.v1`. Nó **không bắt buộc** là tên Java class, kiểu MIME, hay một schema được broker tự giải mã. Nếu cần ghi `application/json`, thường dùng một property riêng (ví dụ `contentType`) hoặc contract rõ ràng của hệ thống.

### 2.2. Nhóm thời gian, ưu tiên và độ tin cậy phân phối

- **`JMSTimestamp`**: thời điểm gửi, **không phải** thời điểm consumer xử lý. Provider có thể được cấu hình bỏ timestamp khi phù hợp; không dùng nó như dấu thời gian nghiệp vụ duy nhất.
- **`JMSExpiration`**: giới hạn tồn tại do time-to-live (TTL). TTL = 0 nghĩa là không tự hết hạn bởi TTL; nó không đồng nghĩa với lưu trữ vĩnh viễn bất chấp broker quota/retention.
- **`JMSDeliveryTime`**: giới hạn *không được giao trước thời điểm này* khi có delivery delay; không cam kết sẽ giao chính xác đúng millisecond đó.
- **`JMSPriority`**: 0 thấp nhất, 9 cao nhất, giá trị mặc định 4; broker có thể ưu tiên nhưng JMS không cam kết sắp xếp tuyệt đối mọi message theo priority.
- **`JMSDeliveryMode`**: `PERSISTENT` là cơ chế bảo vệ message tốt hơn qua lỗi provider so với `NON_PERSISTENT`; kết quả vẫn chịu tác động của cấu hình broker, transaction và trạng thái subscription.
- **`JMSRedelivered`**: `true` nghĩa là message đã/đang được phát lại theo provider, hữu ích khi phát hiện lỗi và triển khai xử lý lặp.

Đừng dùng `message.setJMSPriority(...)`, `setJMSExpiration(...)` hay `setJMSDeliveryMode(...)` để ra lệnh QoS trước khi gửi. Theo JMS, provider xác lập các header này từ **tùy chọn send/producer**. Với `JmsTemplate`, phải bật `explicitQosEnabled` khi muốn cấu hình tường minh priority, TTL hoặc delivery mode được dùng khi gửi.

### 2.3. Header không phải “mọi thứ có tên JMS...”

Một message còn có **JMSX properties** như `JMSXDeliveryCount`. Chúng là **properties**, không thuộc 11 header chuẩn phía trên. Trong Jakarta Messaging 3.1, provider phải có `JMSXDeliveryCount` trên message được nhận; lần giao đầu là `1`, từ `2` trở lên thể hiện redelivery. Khi broker gặp lỗi nặng, giá trị đếm có thể không tuyệt đối chính xác. Các JMSX property khác có thể được provider hỗ trợ tùy mức độ.

## 3. Properties: metadata mở rộng có kiểu

Properties là tập các cặp `name -> value` gắn với message **ngoài body**. Chúng thường được dùng để định tuyến nghiệp vụ, chọn message, ghi phiên bản schema hoặc phục vụ quan sát.

~~~text
Properties của một message ví dụ
tenant         : String  = "VN"
schemaVersion  : int     = 1
requiresAudit  : boolean = true
sourceSystem   : String  = "checkout"
~~~

JMS cho phép property có giá trị thuộc đúng nhóm kiểu:

| Kiểu JMS property | Setter | Getter ví dụ |
| --- | --- | --- |
| `boolean` | `setBooleanProperty("requiresAudit", true)` | `getBooleanProperty("requiresAudit")` |
| `byte` | `setByteProperty(...)` | `getByteProperty(...)` |
| `short` | `setShortProperty(...)` | `getShortProperty(...)` |
| `int` | `setIntProperty("schemaVersion", 1)` | `getIntProperty("schemaVersion")` |
| `long` | `setLongProperty(...)` | `getLongProperty(...)` |
| `float` | `setFloatProperty(...)` | `getFloatProperty(...)` |
| `double` | `setDoubleProperty(...)` | `getDoubleProperty(...)` |
| `String` | `setStringProperty("tenant", "VN")` | `getStringProperty("tenant")` |

Phương thức `setObjectProperty` cũng tồn tại nhưng chỉ chấp nhận nhóm kiểu property hợp lệ, **không phải bất kỳ POJO** nào. Đừng đặt `Map`, `List` hay đối tượng DTO vào property. Dữ liệu nghiệp vụ cấu trúc lớn thuộc **body**.

### 3.1. Tên property và các nhóm namespace

- **Application-specific**: ví dụ `tenant`, `schemaVersion`, `eventType`. Nên dùng tên dễ đọc, ổn định, hợp lệ với cú pháp identifier của JMS selector.
- **JMS-defined**: tiền tố `JMSX` được chuẩn JMS giữ cho các property chuẩn, ví dụ `JMSXDeliveryCount`, `JMSXGroupID`. Không tự sáng tạo tên ứng dụng bắt đầu bằng `JMSX`.
- **Provider-specific**: tiền tố `JMS_<vendor>` dành cho provider. Không dựa vào trường riêng của broker nếu mục tiêu là portability.

Tên property **phân biệt hoa/thường**: `tenant` và `Tenant` là hai tên khác nhau. Đặt giá trị có kiểu nhất quán giữa các producer; nếu producer A gửi `schemaVersion` dạng `int` còn producer B gửi dạng `String`, phép so sánh selector và getter có thể không hoạt động như mong đợi.

### 3.2. Message selector chỉ lọc metadata được phép

JMS selector dùng biểu thức tương tự một phần cú pháp SQL-92, nhưng **không phải SQL hoàn chỉnh**. Ví dụ:

~~~sql
tenant = 'VN' AND schemaVersion >= 1
~~~

Broker dùng selector để quyết định một consumer/subscription có nhận message hay không. Điều kiện đọc được application properties và **một số header JMS được hỗ trợ trong selector**: `JMSDeliveryMode`, `JMSPriority`, `JMSMessageID`, `JMSTimestamp`, `JMSCorrelationID`, `JMSType`. Không tùy ý đưa các header còn lại vào selector; chẳng hạn `JMSRedelivered` không thuộc nhóm header selector chuẩn.

Quy tắc cần nhớ:

1. Selector **không duyệt body JSON**. Không thể viết `payload.orderId = 'O-42'` khi `payload` chỉ nằm trong `TextMessage`.
2. So sánh chuỗi dùng dấu nháy đơn: `tenant = 'VN'`. So sánh số dùng literal số: `schemaVersion >= 1`.
3. Nếu property bị thiếu hoặc biểu thức có kết quả **UNKNOWN** theo logic ba giá trị, selector không match.
4. Việc lọc bằng thuộc tính chỉ được provider gán **khi receive** (ví dụ `JMSXDeliveryCount`) có kết quả không xác định theo chuẩn; không dùng property đó để lập selector ổn định.
5. Thay đổi tên/kiểu property sau khi consumer đã triển khai có thể khiến message không còn được giao; quản lý chúng như hợp đồng API.

### 3.3. Khi nào nên đưa thông tin vào properties?

Chọn property nếu broker/consumer cần truy cập metadata **mà không giải mã body**. Ví dụ `tenant` để lọc; `schemaVersion` để chọn decoder; `eventId` để theo dõi xử lý.

Đừng đẩy toàn bộ JSON nghiệp vụ thành hàng chục properties: có overhead chuyển/đọc, phụ thuộc provider và nguy cơ làm lộ metadata khi ghi log. Body vẫn là nguồn dữ liệu chính.

## 4. Body: nội dung do ứng dụng quyết định

JMS định nghĩa các kiểu message body qua các interface kế thừa `jakarta.jms.Message`:

| Kiểu | Nội dung body | Khi nào dùng |
| --- | --- | --- |
| `TextMessage` | Một chuỗi `String` | Văn bản, JSON, XML; phù hợp tích hợp đa ngôn ngữ |
| `BytesMessage` | Chuỗi byte đọc/ghi tuần tự | Protobuf, Avro, payload nhị phân có schema riêng |
| `MapMessage` | Tập trường tên–giá trị có kiểu JMS hỗ trợ | Dữ liệu key/value nhỏ theo hợp đồng JMS |
| `StreamMessage` | Dãy các giá trị primitive/chuỗi theo thứ tự | Payload dạng stream tuần tự, ít phổ biến |
| `ObjectMessage` | Đối tượng Java `Serializable` | Chỉ cân nhắc trong hệ thống kiểm soát hoàn toàn kiểu đối tượng và bảo mật |
| `Message` | Không có body | Tín hiệu/điều khiển khi nội dung nghiệp vụ nằm ở metadata |

Lưu ý:

- `TextMessage` chứa **chuỗi**, không tự hiểu JSON. Producer và consumer phải thống nhất encoding, schema, cách xử lý null và version.
- `BytesMessage` phù hợp định dạng nhị phân; consumer cần đúng schema/decoder. Vấn đề endian, version, kích thước payload do hợp đồng dữ liệu xử lý.
- `MapMessage` **khác** message properties: trường trong map thuộc body, không mặc nhiên truy cập được trong selector.
- `ObjectMessage` dựa vào Java serialization; có rủi ro deserialization, tương thích classpath và chia sẻ class giữa dịch vụ. Trong hệ thống phân tán, ưu tiên JSON/Avro/Protobuf và kiểm soát decoder.
- `Message#getBody(String.class)` cho phép đọc body có thể gán sang `String` (điển hình `TextMessage`). Nếu body có kiểu khác, lệnh có thể báo lỗi không chuyển được.

Trong Spring, `MessageConverter` quyết định Java object biến thành JMS message kiểu nào. Bộ chuyển đổi đơn giản thường dùng `String -> TextMessage`, `byte[] -> BytesMessage`, `Map -> MapMessage`, đối tượng `Serializable -> ObjectMessage`. Với DTO, nên cấu hình converter JSON tường minh thay vì trông chờ Java serialization.

## 5. Cơ chế tạo, gửi, nhận và quyền chỉnh sửa

Một chu kỳ điển hình:

1. **Producer tạo message** với body; có thể đặt `JMSCorrelationID`, `JMSReplyTo`, `JMSType` và các properties hợp lệ.
2. **Ứng dụng gửi** qua `JmsTemplate` / `MessageProducer`; delivery mode, priority, TTL, delay được lấy từ tùy chọn gửi. Provider xác lập các header liên quan như `JMSMessageID`, `JMSTimestamp`, `JMSDestination`.
3. **Broker định tuyến** tới Queue/Topic, cân nhắc selector, expiration, trạng thái subscription và chính sách phân phối.
4. **Consumer đọc** header, properties và body; provider gắn các thông tin nhận như `JMSRedelivered`, `JMSXDeliveryCount`.
5. **ACK/transaction** xác nhận việc tiêu thụ; khi lỗi trước xác nhận, message có thể được giao lại.

**Trạng thái read-only:** properties và body của **message vừa được nhận** ở trạng thái chỉ đọc. Việc gọi setter để thay đổi trực tiếp có thể gây `MessageNotWriteableException`. `clearProperties()` hoặc `clearBody()` có thể chuyển phần tương ứng sang writable, nhưng khi xử lý nghiệp vụ thường nên tạo **message mới** để phản hồi hoặc chuyển tiếp, tránh vô tình phá metadata của message nhận.

Header có hợp đồng setter khác với properties: các setter header do provider quản lý không phải API để ép lại kết quả gửi.

## 6. Ví dụ thực hành Spring Boot 3.x + ActiveMQ Artemis (Java 17)

Bài thực hành gửi **một TextMessage chứa JSON** vào Queue `orders.demo`. Producer gắn các header do ứng dụng kiểm soát và ba property có kiểu; listener dùng selector, đọc **toàn bộ ba phần** để thấy rõ mỗi thông tin sống ở đâu.

### 6.1. Chạy broker

Cần Docker và Java 17+. Dùng image chính thức của Apache Artemis:

~~~bash
docker run --detach --rm --name jms-message-demo -p 61616:61616 -p 8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
~~~

Broker nhận kết nối JMS trên `localhost:61616`; giao diện quản trị ở `localhost:8161`. Ví dụ dùng tài khoản demo **chỉ trong môi trường học**. Dữ liệu container mất sau khi xóa container trừ khi có volume; không dùng cấu hình mẫu này làm tiêu chuẩn vận hành sản xuất.

Nếu broker không tự tạo destination, hãy tạo Queue `orders.demo` với định tuyến JMS phù hợp trên broker trước khi chạy ứng dụng. Cấu hình auto-create phụ thuộc broker.

### 6.2. Dự án Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-message-demo'
~~~

`build.gradle`:

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
}
~~~

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=demo
spring.artemis.password=demo
spring.jms.pub-sub-domain=false
~~~

`pub-sub-domain=false` định tuyến theo **Queue**. Bài này học cấu trúc JMS message nên không cần Topic; cả Queue và Topic đều dùng cùng mô hình header/properties/body.

### 6.3. Entry point

`src/main/java/demo/jms/DemoApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 6.4. Producer đặt đúng header và property

`src/main/java/demo/jms/MessagePublisher.java`:

~~~java
package demo.jms;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class MessagePublisher implements ApplicationRunner {

    private final JmsTemplate jmsTemplate;

    public MessagePublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        String json = "{\"orderId\":\"O-42\",\"total\":125000}";

        jmsTemplate.convertAndSend("orders.demo", json, message -> {
            // HEADER ứng dụng được phép đặt:
            message.setJMSCorrelationID("checkout-O-42");
            message.setJMSType("order.created.v1");

            // PROPERTIES có kiểu:
            message.setStringProperty("tenant", "VN");
            message.setIntProperty("schemaVersion", 1);
            message.setBooleanProperty("requiresAudit", true);
            return message;
        });

        System.out.println("SENT order O-42");
    }
}
~~~

Ý nghĩa:

- `convertAndSend` dùng `MessageConverter` để biến `String json` thành JMS `TextMessage`.
- `MessagePostProcessor` nhận message sau bước convert nhưng **trước bước send**, nên có thể đặt header ứng dụng và properties.
- Producer **không** gán `JMSMessageID` / `JMSTimestamp` bằng tay. Provider tạo các giá trị đó khi gửi.
- `tenant="VN"` và `schemaVersion=1` có kiểu thực (String và int), nhờ vậy selector có thể lọc đúng.

### 6.5. Consumer đọc nguyên bản JMS Message

`src/main/java/demo/jms/MessageInspector.java`:

~~~java
package demo.jms;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class MessageInspector {

    @JmsListener(
        destination = "orders.demo",
        selector = "tenant = 'VN' AND schemaVersion = 1"
    )
    public void inspect(Message message) throws JMSException {
        // BODY: TextMessage được đọc như String
        String body = message.getBody(String.class);

        // HEADER:
        String messageId = message.getJMSMessageID();
        String correlationId = message.getJMSCorrelationID();
        String type = message.getJMSType();

        // PROPERTIES:
        String tenant = message.getStringProperty("tenant");
        int version = message.getIntProperty("schemaVersion");
        boolean audit = message.getBooleanProperty("requiresAudit");

        System.out.println("BODY=" + body);
        System.out.println("JMSType=" + type);
        System.out.println("JMSCorrelationID=" + correlationId);
        System.out.println("tenant=" + tenant);
        System.out.println("schemaVersion=" + version);
        System.out.println("requiresAudit=" + audit);
        System.out.println("JMSMessageID present=" + (messageId != null));
        System.out.println("JMSXDeliveryCount=" +
                message.getIntProperty("JMSXDeliveryCount"));
    }
}
~~~

Vì Spring hỗ trợ tham số **`jakarta.jms.Message` nguyên bản** trong `@JmsListener`, người học đọc được đầy đủ JMS header, property, body mà không phải đoán tên trường sau khi ánh xạ sang `org.springframework.messaging.Message<?>`.

Khi consumer nhận message, 6 dòng dữ liệu có giá trị xác định là:

~~~text
BODY={"orderId":"O-42","total":125000}
JMSType=order.created.v1
JMSCorrelationID=checkout-O-42
tenant=VN
schemaVersion=1
requiresAudit=true
~~~

Hai dòng còn lại phụ thuộc provider/trạng thái gửi: với cấu hình thông thường `JMSMessageID present=true` và `JMSXDeliveryCount=1` khi giao lần đầu. Broker tạo ID riêng; không thể đoán trước chuỗi ID. Dòng `SENT order O-42` và các dòng consumer có thể xen kẽ tùy lịch thread.

### 6.6. Chạy và quan sát

Trong thư mục dự án có Gradle 8.x và JDK 17+:

~~~bash
gradle bootRun
~~~

Sau khi kết nối broker, listener được khởi tạo và `ApplicationRunner` publish một message. Quan sát log `SENT order O-42` và các dòng `BODY=...`, `tenant=...`, `JMSType=...` từ listener. Dừng ứng dụng bằng Ctrl+C. Có thể dùng `gradle bootJar` và `java -jar build/libs/jms-message-demo-1.0.0.jar` thay cho `bootRun`.

Nếu selector được thay thành `tenant = 'US'` trong consumer mà producer vẫn gắn `tenant="VN"`, consumer sẽ không nhận message đó. Khôi phục selector, dùng message mới để thử lại; message cũ có thể vẫn đang ở queue và trạng thái phân phối còn phụ thuộc provider.

## 7. Tùy chọn gửi ảnh hưởng header như thế nào?

Với Spring `JmsTemplate`, ví dụ minh họa cấu hình QoS cho template **trước khi gửi**:

~~~java
// Đặt một lần trong cấu hình khởi tạo JmsTemplate,
// không gọi lại giữa các luồng đang dùng chung template.
jmsTemplate.setExplicitQosEnabled(true);
jmsTemplate.setTimeToLive(60_000L);   // 60 giây
jmsTemplate.setPriority(7);            // Ưu tiên cao hơn mặc định
jmsTemplate.setDeliveryPersistent(true);
~~~

Đây là **đoạn cấu hình minh họa bổ sung**, không phải file Java độc lập. `setExplicitQosEnabled(true)` buộc `JmsTemplate` dùng các tùy chọn QoS đã thiết lập khi gửi. Broker phản ánh chúng trong `JMSExpiration`, `JMSPriority` và `JMSDeliveryMode`; provider/admin có thể áp quy tắc override theo chính sách. Không gán `setJMSExpiration` trực tiếp trên `TextMessage` để đạt TTL.

Với JMS API thuần, cấu hình tương ứng nằm ở `MessageProducer` / `JMSProducer` hoặc tham số send. Delivery delay là một tùy chọn gửi khác, không phải một property tự đặt tùy ý rồi hy vọng broker hoãn giao.

## 8. Ví dụ request/reply: ba header hay bị lẫn

Trong yêu cầu `checkout` gửi để kiểm tra trạng thái:

~~~text
Request:
  JMSMessageID      = ID do broker cấp, ví dụ ID:request-...
  JMSCorrelationID  = checkout-O-42
  JMSReplyTo        = queue:checkout.replies
  JMSType           = checkout.status.request

Reply:
  JMSMessageID      = ID mới của reply
  JMSCorrelationID  = checkout-O-42 (theo hợp đồng ví dụ)
  JMSDestination    = queue:checkout.replies
  JMSType           = checkout.status.reply
~~~

Mã đặt `JMSReplyTo` khi tạo một request bằng Spring:

~~~java
// Minh họa trong một bean đã inject JmsTemplate:
jmsTemplate.send("checkout.requests", session -> {
    var request = session.createTextMessage("{\"orderId\":\"O-42\"}");
    request.setJMSCorrelationID("checkout-O-42");
    request.setJMSReplyTo(session.createQueue("checkout.replies"));
    request.setJMSType("checkout.status.request");
    request.setStringProperty("tenant", "VN");
    return request;
});
~~~

Code này mới **gửi request**. Consumer phía server cần tạo một reply mới và gửi đến destination từ `request.getJMSReplyTo()`. Một số tính năng Spring như return value của `@JmsListener` hỗ trợ phản hồi, nhưng không được giả định request tự sinh reply.

Điểm phân biệt:

- `JMSMessageID`: ID của **từng** JMS message, thường khác nhau giữa request và reply.
- `JMSCorrelationID`: mã **liên hệ nhiều message** cùng tiến trình xử lý, tùy quy ước của hai đầu.
- `JMSReplyTo`: địa chỉ **nên gửi phản hồi**, không phải correlation ID.

## 9. Xem tất cả properties và phân biệt với body

Khi không biết trước bộ property, có thể liệt kê:

~~~java
// Minh họa trong method đã nhận jakarta.jms.Message message:
var names = message.getPropertyNames();
while (names.hasMoreElements()) {
    String name = names.nextElement().toString();
    Object value = message.getObjectProperty(name);
    System.out.println(name + "=" + value);
}
~~~

`getPropertyNames()` và `getObjectProperty()` chỉ duyệt **properties**; chúng không tự bao gồm toàn bộ 11 JMS header và không giải mã body. Để đọc `JMSType` phải gọi `getJMSType()`; để đọc JSON TextMessage gọi `getText()` hoặc `getBody(String.class)`.

Consumer có thể kiểm tra `propertyExists("schemaVersion")` trước khi gọi typed getter. Với metadata tùy chọn, phân biệt rõ **không có property**, **có property sai kiểu**, và **giá trị hợp lệ**. Không dùng giá trị 0 hoặc false làm tín hiệu duy nhất cho “property không tồn tại”.

## 10. Lưu ý thực tế: bảo mật, schema và xử lý lại

**Contract dữ liệu:** mô tả rõ cả 3 lớp trong tài liệu giữa các dịch vụ, ví dụ:

~~~yaml
destination: orders.demo
messageType: TextMessage
headers:
  JMSType: order.created.v1
  JMSCorrelationID: checkout-O-42
properties:
  tenant: VN               # String
  schemaVersion: 1         # int
  requiresAudit: true      # boolean
body: '{"orderId":"O-42","total":125000}'
~~~

Đây là **tài liệu contract YAML minh họa**, không phải file cấu hình Spring để ứng dụng tự tải. Trong hệ thống thật, cần chuẩn hóa các trường bắt buộc, kiểu dữ liệu, quyền truy cập, sự thay đổi schema và chính sách tương thích ngược.

**Bảo mật:** header/properties thường xuất hiện trong broker management, trace hoặc log. Không đặt mật khẩu, access token hay thông tin cá nhân nhạy cảm vào các property chỉ để dễ lọc. Nếu bắt buộc mang dữ liệu nhạy cảm, cần chính sách mã hóa, phân quyền và hạn chế logging phù hợp.

**Redelivery:** khi xử lý lỗi hoặc rollback, cùng message có thể được giao lại với `JMSRedelivered=true` và `JMSXDeliveryCount>=2`. Đây là tín hiệu chẩn đoán, **không thay thế xử lý idempotent**. Nếu nghiệp vụ phải chống xử lý lặp, lưu một `eventId` ổn định của nghiệp vụ trong body/property và kiểm soát hiệu ứng bằng khóa đó; không chỉ phụ thuộc `JMSMessageID`.

**Transaction:** “message đã giao đến listener” khác với “message đã được ACK/commit sau xử lý”. Nếu cập nhật DB rồi tiến trình crash trước ACK, có thể có redelivery; local JMS transaction không tự đồng bộ giao dịch DB ngoài broker.

**Tương thích:** đổi tên property `tenant` thành `region` mà quên sửa selector có thể khiến consumer không còn nhận message. Tương tự, thay body từ JSON text sang Java serialized object mà không công bố contract có thể làm consumer không giải mã được hoặc gặp rủi ro bảo mật.

## 11. Lỗi phổ biến và cách kiểm tra

| Triệu chứng | Giả thuyết cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Listener chạy nhưng không có message | Sai destination, Queue/Topic mode hoặc selector không match | So lại destination, `pub-sub-domain` và giá trị/kiểu property |
| `schemaVersion >= 1` không match | Producer gửi version dưới dạng String hoặc đặt sai tên | Đặt `int` nhất quán; kiểm tra property thực bằng broker/consumer |
| `JMSMessageID` khác ID nghiệp vụ | Nhầm ID kỹ thuật với `eventId` | Gắn ID nghiệp vụ riêng, không ép `JMSMessageID` bằng setter |
| TTL đặt nhưng message không hết hạn | Chỉ đổi header, quên bật explicit QoS hoặc broker override | Cấu hình producer/template QoS và quan sát `JMSExpiration` |
| `JMSReplyTo` đã set nhưng không có trả lời | Chưa có handler gửi reply; response destination chưa tồn tại | Tạo request/reply handler, xác nhận reply được gửi và correlation đúng |
| Body không đọc được thành String | Message không phải TextMessage hoặc converter khác contract | Kiểm tra kiểu message, dùng converter/decoder đúng |
| DTO Java gây lỗi deserialization | Dùng ObjectMessage với classpath hoặc whitelist khác nhau | Ưu tiên TextMessage JSON/BytesMessage với schema, decoder được kiểm soát |
| Lỗi `MessageNotWriteableException` | Đang sửa properties/body của message nhận | Tạo message mới hoặc hiểu rõ `clearProperties` / `clearBody` |
| Một message xử lý hai lần | Rollback, crash trước ACK hoặc retry | Idempotency, retry/DLQ và quan sát `JMSXDeliveryCount` |

## 12. Câu hỏi tự đánh giá

1. Khi producer gửi chuỗi JSON qua `convertAndSend`, JSON là property hay body? **Body**, thường trong `TextMessage`; nó không tự trở thành bộ properties.
2. Dùng `message.setJMSExpiration(now+60000)` trước khi gửi để đặt TTL được không? **Không**; cấu hình TTL qua producer/send, với `JmsTemplate` dùng explicit QoS.
3. Có thể viết selector `tenant = 'VN'` nếu `tenant` nằm bên trong JSON body mà không có property tương ứng? **Không**.
4. `JMSXDeliveryCount` thuộc header hay property? **Property JMS-defined**; trên message nhận, lần giao đầu là 1.
5. Trong request/reply, ID của reply có bắt buộc bằng ID của request? **Không**; mỗi message có `JMSMessageID` riêng, còn `JMSCorrelationID` thể hiện cách ghép cặp đã thỏa thuận.
6. `MapMessage` và message properties có giống nhau không? **Không**; map fields nằm trong body, properties là metadata riêng dùng được trong selector.
7. Tại sao cần dùng `eventId` nghiệp vụ thay vì chỉ `JMSMessageID` để idempotency? Vì retry/tái publish có thể tạo message transport mới dù cùng sự kiện nghiệp vụ.
8. Consumer có thể đọc `JMSType` bằng `getStringProperty("JMSType")` như mọi custom property không? **Không nên**; `JMSType` là header chuẩn, hãy dùng `getJMSType()`.

## 13. Tài liệu chính thức để tra cứu

- Jakarta Messaging 3.1 — **Message model, Header fields, Properties, Body, Message selection**: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 API — **`jakarta.jms.Message`**: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
- Spring Framework — **Sending a Message / MessagePostProcessor**: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework — **Annotation-driven Listener Endpoints**: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot — **JMS / ActiveMQ Artemis Support**: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Apache Artemis — **Official Docker Images**: https://artemis.apache.org/components/artemis/documentation/latest/docker.html

**Ghi nhớ:** Header = trường **chuẩn JMS**; properties = **metadata có kiểu** để ứng dụng/broker truy cập; body = **payload nghiệp vụ**. Thiết kế tốt phải định nghĩa cả ba phần và phân biệt rõ trường do producer đặt với trường do provider xác lập.
